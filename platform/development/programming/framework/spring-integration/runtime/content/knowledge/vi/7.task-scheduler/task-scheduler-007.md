# Error handler của scheduled task

Spring Integration dùng scheduler để kích hoạt poller và các tác vụ định kỳ. Ứng dụng Spring cũng có thể dùng `@Scheduled` hoặc `TaskScheduler` để chạy công việc nền. Khi một scheduled task ném exception, điều quan trọng là xác định **lớp nào đang nhận exception, chính sách đó có cho lần chạy tiếp theo tiếp tục hay không, và lỗi có đủ ngữ cảnh để xử lý nghiệp vụ hay chưa**.

`ErrorHandler` của Spring TaskScheduler và `errorChannel` của Spring Integration có liên quan nhưng không cùng vai trò. `ErrorHandler` xử lý exception thoát ra khỏi một scheduled `Runnable`; `errorChannel` đưa lỗi trong message flow thành `ErrorMessage` để một flow khác có thể phân loại, lưu hoặc cảnh báo. Chọn đúng lớp xử lý giúp tránh việc task âm thầm ngừng chạy hoặc lỗi chỉ được ghi log mà không có quy trình phục hồi.

## 1. Scheduled task chạy ở đâu?

`TaskScheduler` chịu trách nhiệm lên lịch thực thi một `Runnable` vào thời điểm cụ thể, theo fixed rate, fixed delay hoặc một `Trigger`. Với `ThreadPoolTaskScheduler`, scheduler sử dụng một nhóm thread để chạy các tác vụ đã đến hạn.

Trong Spring Integration, poller là một ví dụ của scheduled task. Scheduler kích hoạt polling consumer; consumer nhận message từ `PollableChannel` hoặc gọi message source; sau đó message được chuyển vào các bước của flow. Ứng dụng cũng có thể có những tác vụ độc lập như đồng bộ dữ liệu, dọn dẹp trạng thái hoặc kiểm tra kết nối.

```text
TaskScheduler
    |
    +-- @Scheduled method
    |
    +-- Scheduled Runnable của ứng dụng
    |
    +-- Poller của Spring Integration
            |
            +-- receive message
            +-- dispatch vào endpoint
            +-- xử lý message
```

Không phải mọi endpoint Spring Integration đều là scheduled task. `DirectChannel`, `ExecutorChannel` hoặc inbound message-driven adapter có thể dispatch message theo cơ chế khác. Vì vậy, chính sách `ErrorHandler` của scheduler chỉ áp dụng cho tác vụ thực sự chạy qua scheduler đó.

## 2. ErrorHandler của Spring TaskScheduler

Spring cung cấp interface `org.springframework.util.ErrorHandler` với một phương thức nhận `Throwable`:

```java
public interface ErrorHandler {
    void handleError(Throwable t);
}
```

`ThreadPoolTaskScheduler` cho phép cấu hình error handler bằng `setErrorHandler(...)`. Error handler được gọi khi exception thoát ra khỏi scheduled task và không được xử lý bên trong task hoặc một lớp bọc phía trên.

`ErrorHandler.handleError(Throwable)` chỉ nhận exception, không nhận trực tiếp tên task, registration ID hay message headers. Nếu một scheduler phục vụ nhiều tác vụ, hãy thêm ngữ cảnh bằng logger/metric riêng cho từng tác vụ hoặc bọc `Runnable` bằng một wrapper có tên và khóa nghiệp vụ. Với lỗi gắn với message, poller `errorChannel` thường cung cấp ngữ cảnh tốt hơn.

Ví dụ cấu hình scheduler có error handler riêng:

```java
@Configuration
@EnableScheduling
public class SchedulerConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(SchedulerConfiguration.class);

    @Bean("integrationTaskScheduler")
    public ThreadPoolTaskScheduler integrationTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(4);
        scheduler.setThreadNamePrefix("si-scheduler-");
        scheduler.setErrorHandler(error ->
            log.error("Scheduled task failed", error));
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(30);
        return scheduler;
    }
}
```

Trong ví dụ, error handler ghi nhận exception rồi trả về bình thường. Với scheduled task lặp lại, cách xử lý này cho phép scheduler tiếp tục những lần chạy tiếp theo. Bean scheduler cũng có thể được dùng cho những task khác được cấu hình rõ ràng để sử dụng nó.

Nếu ứng dụng có nhiều `TaskScheduler`, hãy đặt tên bean và chọn scheduler phù hợp cho từng nhóm công việc. Đừng mặc định tất cả `@Scheduled` method và mọi poller đều sử dụng cùng một scheduler nếu ứng dụng đã cấu hình nhiều pool hoặc custom scheduler.

## 3. Chính sách mặc định: suppress và propagate

Spring có `TaskUtils` để cung cấp error handler mặc định cho scheduled task. Hai chính sách quan trọng là:

| Chính sách | Hành vi khi task ném exception | Hệ quả với task lặp lại |
|---|---|---|
| Log and suppress | Ghi log exception rồi không ném lại | Lịch chạy tiếp tục ở lần kế tiếp. |
| Log and propagate | Ghi log rồi ném exception ra ngoài | Exception có thể làm scheduled future kết thúc; những lần chạy tiếp theo của tác vụ lặp có thể bị ngăn. |

`TaskUtils.getDefaultErrorHandler(true)` trả về chính sách log-and-suppress cho tác vụ lặp lại. `TaskUtils.getDefaultErrorHandler(false)` trả về chính sách log-and-propagate cho tác vụ chỉ chạy một lần. Các hằng `LOG_AND_SUPPRESS_ERROR_HANDLER` và `LOG_AND_PROPAGATE_ERROR_HANDLER` cũng thể hiện hai lựa chọn này.

Lý do có hai chính sách là task định kỳ thường cần tiếp tục thử ở lần kế tiếp, còn task chạy một lần thường cần để exception được quan sát như một lần thực thi thất bại. Đây là mặc định của Spring scheduler; ứng dụng có thể thay đổi bằng custom `ErrorHandler`.

### Suppress không có nghĩa là xử lý thành công

Khi error handler ghi log rồi trả về, scheduler chỉ biết exception đã được xử lý ở lớp error handler. Nó không biết tác vụ nghiệp vụ có hoàn thành hay không. Nếu tác vụ đồng bộ dữ liệu thất bại, lần chạy tiếp theo có thể thử lại nhưng trạng thái nghiệp vụ vẫn cần được ghi nhận là thất bại hoặc chưa hoàn tất.

Do đó, task định kỳ nên có cơ chế quan sát riêng: số lần lỗi, thời điểm thành công gần nhất, thời điểm lỗi gần nhất, số lần retry và trạng thái backlog. Không nên dựa vào việc lịch vẫn chạy để kết luận dữ liệu đã được xử lý đúng.

## 4. Custom ErrorHandler: ghi log, metric và cảnh báo

Một error handler tùy chỉnh có thể ghi log có cấu trúc, tăng counter và phát tín hiệu cảnh báo. Handler cần nhanh, an toàn và không tạo thêm một chuỗi lỗi mới.

```java
@Bean
public ErrorHandler scheduledTaskErrorHandler(MeterRegistry registry) {
    return error -> {
        registry.counter("app.scheduled.errors").increment();
        LoggerFactory.getLogger("scheduled-task")
            .error("Scheduled execution failed", error);
    };
}
```

Sau đó inject error handler vào scheduler:

```java
@Bean("integrationTaskScheduler")
public ThreadPoolTaskScheduler integrationTaskScheduler(
        ErrorHandler scheduledTaskErrorHandler) {

    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("si-scheduler-");
    scheduler.setErrorHandler(scheduledTaskErrorHandler);
    return scheduler;
}
```

Đây là ví dụ minh họa với Micrometer `MeterRegistry`; cần có dependency Micrometer và bean registry trong ứng dụng. Nếu dùng một scheduler cho nhiều tác vụ, counter tổng hợp chỉ cho biết có lỗi. Để biết task nào lỗi, có thể tạo metric riêng theo nhóm task hoặc bọc từng `Runnable` với tên tác vụ trước khi đăng ký.

Không nên gửi email, gọi webhook chậm hoặc thực hiện I/O đồng bộ kéo dài ngay trong scheduler error handler. Việc đó giữ scheduler thread và có thể làm trễ các tác vụ khác. Nếu cần cảnh báo qua hệ thống bên ngoài, hãy đẩy một sự kiện ngắn vào kênh/queue chuyên dụng và để thành phần khác gửi cảnh báo.

Nếu custom error handler tự ném exception, exception mới có thể thoát ra scheduler. Với task lặp lại, điều đó có thể làm lịch của task bị ngừng. Hãy bảo vệ cả chính error handler: nếu metric hoặc logging phụ trợ gặp lỗi, vẫn cần ghi nhận fallback và tránh làm mất kiểm soát vòng đời scheduled future.

## 5. ErrorHandler và errorChannel trong Spring Integration poller

Poller không chỉ là một `Runnable` chung. Nó chạy trong ngữ cảnh message flow và có thể biết message nào vừa được nhận, endpoint nào đang xử lý và error channel nào được cấu hình. Vì vậy, Spring Integration hỗ trợ định tuyến lỗi của poller vào một error channel.

Ví dụ cấu hình poller có error channel:

```java
@Bean
public MessageChannel pollerErrors() {
    return new DirectChannel();
}

@Bean
public IntegrationFlow ordersPollingFlow(
        @Qualifier("ordersQueue") PollableChannel ordersQueue,
        OrderHandler orderHandler) {

    return IntegrationFlow.from(ordersQueue, endpoint -> endpoint.poller(
            Pollers.fixedDelay(1_000)
                .maxMessagesPerPoll(10)
                .errorChannel("pollerErrors")))
        .handle(orderHandler, "handle")
        .get();
}
```

Channel `pollerErrors` cần có subscriber đang hoạt động. Khai báo bean channel tường minh giúp xác định rõ nơi nhận lỗi và tránh phụ thuộc vào việc framework tự tạo channel theo tên.

Một handler có thể tiếp nhận `ErrorMessage` từ channel đó:

```java
@Component
public class PollerErrorHandler {

    @ServiceActivator(inputChannel = "pollerErrors")
    public void handle(ErrorMessage error) {
        Throwable failure = error.getPayload();
        Message<?> original = error.getOriginalMessage();

        // Phân loại lỗi, ghi nhận message và đưa vào quy trình phục hồi.
    }
}
```

`ErrorMessage` có payload là `Throwable`; nó có thể mang `originalMessage` nếu lỗi gắn với một message đã được nhận. Nếu lỗi xảy ra trước khi có message, chẳng hạn lỗi khi đọc nguồn polling, original message có thể không tồn tại.

`errorChannel` là một phần của xử lý lỗi message flow. `ErrorHandler` của `TaskScheduler` là lớp xử lý exception thoát khỏi scheduled `Runnable`. Khi poller đã bắt và publish lỗi thành `ErrorMessage`, exception có thể không đi tiếp đến scheduler error handler. Ngược lại, lỗi xảy ra bên ngoài cơ chế poller error handling vẫn có thể thoát ra lớp scheduler. Vì vậy, không nên cấu hình hai cơ chế rồi giả định cả hai đều nhận cùng một exception.

Nếu không khai báo error channel riêng cho poller, hãy xác minh cấu hình error handling mặc định và global `errorChannel` của ứng dụng theo phiên bản Spring Integration đang dùng. Một channel không có subscriber phù hợp hoặc error flow tự ném exception vẫn có thể khiến việc xử lý lỗi thất bại.

## 6. Phân biệt lỗi khi receive và lỗi khi xử lý message

Trong một polling endpoint, exception có thể phát sinh ở nhiều giai đoạn:

1. **Message source / receive:** lỗi khi truy cập nguồn dữ liệu hoặc lấy message từ channel.
2. **Message conversion:** lỗi chuyển đổi payload hoặc header.
3. **Handler:** lỗi nghiệp vụ khi gọi service hoặc xử lý message.
4. **Downstream send:** lỗi khi chuyển message sang channel tiếp theo.
5. **Error flow:** lỗi khi chính handler xử lý `ErrorMessage` thực thi.

Các lỗi này có thể có ngữ cảnh khác nhau. Nếu handler lỗi sau khi đã có message, `ErrorMessage` thường có thể mang message liên quan. Nếu nguồn polling lỗi trước khi tạo message, không có payload nghiệp vụ để redrive. Nếu downstream send lỗi, cần xác định message đã được xử lý một phần hay chưa.

Đừng chỉ ghi nhận tên exception. Hãy ghi loại endpoint, tên channel, message ID/correlation ID nếu có, exception class, cause gốc và giai đoạn lỗi. Tránh ghi toàn bộ payload hoặc thông tin nhạy cảm vào log.

## 7. Error handling không tự động là retry

Một error handler có thể ghi log, gửi cảnh báo, lưu message lỗi hoặc chuyển `ErrorMessage` sang một flow khác. Những hành động đó không tự động gọi lại handler nghiệp vụ.

Retry cần được cấu hình rõ bằng retry advice hoặc cơ chế retry phù hợp với ranh giới cần bảo vệ. Với lỗi tại một request handler, `RequestHandlerRetryAdvice` có thể bọc thao tác handler. Với lỗi ở quá trình poll hoặc nhận message, cần chọn advice và transaction boundary phù hợp cho poller/adapter.

Khi thiết kế retry:

- Chỉ retry lỗi có khả năng phục hồi, ví dụ timeout tạm thời hoặc dịch vụ phụ thuộc đang gián đoạn.
- Giới hạn số lần thử và dùng backoff để tránh tạo tải lớn hơn khi hệ thống phụ thuộc đang lỗi.
- Không retry vô hạn lỗi dữ liệu sai hoặc lỗi nghiệp vụ không thể tự khắc phục.
- Bảo đảm handler idempotent hoặc có cơ chế chống xử lý trùng.
- Sau khi hết retry, lưu message và thông tin lỗi vào nơi có thể điều tra hoặc redrive.

Nếu custom `ErrorHandler` suppress exception để lịch tiếp tục, đó là chính sách tiếp tục schedule, không phải retry cùng message. Với poller, message đã được receive khỏi `QueueChannel` có thể không còn nằm trong queue; nếu cần phát lại, ứng dụng phải lưu message hoặc dùng nguồn hỗ trợ redelivery.

## 8. Lỗi của @Scheduled method

`@Scheduled` method cũng chạy qua cơ chế scheduler. Ví dụ:

```java
@Component
public class PartnerSyncJob {

    @Scheduled(fixedDelay = 30_000)
    public void synchronize() {
        // Đồng bộ một phần dữ liệu với đối tác.
    }
}
```

Nếu method ném exception, chính sách error handler của scheduler được dùng để xử lý exception thoát khỏi scheduled invocation. Với scheduler mặc định của Spring, tác vụ lặp thường dùng log-and-suppress để lịch tiếp tục; có thể cấu hình custom `TaskScheduler` để kiểm soát chính sách và pool.

Nếu một scheduled method có nhiều nhóm công việc, nên tách chúng thành các task có tên và metric riêng. Một lỗi trong tác vụ đồng bộ đối tác không nên làm mất khả năng quan sát một tác vụ dọn dẹp khác. Cũng cần đặt timeout cho các lời gọi mạng để một lần chạy không chiếm scheduler thread quá lâu.

## 9. Lỗi trong scheduler có thể làm lịch ngừng chạy

Với scheduled task lặp lại, nếu exception thoát ra khỏi task và bị propagate tới scheduler, cơ chế scheduled executor có thể đánh dấu lần chạy định kỳ đó là thất bại và không chạy những lần tiếp theo. Đây là lý do một custom error handler cần có chính sách rõ ràng.

Ví dụ một task lặp lại có thể tiếp tục sau lỗi:

```java
scheduler.setErrorHandler(error -> {
    log.error("Periodic refresh failed; next run remains scheduled", error);
});
```

Vì handler trả về bình thường, scheduler không nhận exception thoát ra. Nếu muốn một task dừng hẳn sau lỗi nghiêm trọng, có thể dùng chính sách propagate hoặc hủy `ScheduledFuture` một cách chủ động. Không nên vô tình tạo hành vi dừng lịch chỉ vì error handler gửi cảnh báo rồi ném lỗi phụ.

Đối với tác vụ một lần, propagate có thể là lựa chọn phù hợp vì không có lần chạy kế tiếp cần duy trì. Tuy nhiên, cần lưu kết quả và trạng thái thất bại ở nơi mà hệ thống vận hành có thể tra cứu.

## 10. Transaction và shutdown của scheduled task

Transaction advice có thể bao quanh việc poller nhận và xử lý message, tùy cấu hình endpoint. Scheduler error handler không thay thế transaction manager và không quyết định rollback. Nếu exception bị bắt và suppress trước khi transaction interceptor quan sát được, transaction có thể commit theo đường xử lý hiện tại.

Với flow bất đồng bộ, transaction gắn với thread không tự truyền sang executor thread. Nếu scheduled task gửi message vào `ExecutorChannel`, transaction bao quanh lời gọi gửi không mặc nhiên bao phủ công việc downstream. Hãy đặt transaction tại consumer thực sự thực hiện thao tác dữ liệu và xác định rõ ack/commit của nguồn message.

Khi context đóng, scheduler phải ngừng tạo lần chạy mới và các tác vụ đang thực hiện cần kết thúc theo ngân sách shutdown. Nếu error handler thực hiện lưu lỗi hoặc publish message, nó cũng cần hoàn tất trước khi các dependency như database, message broker hoặc error channel bị đóng. Hãy cấu hình timeout I/O, graceful shutdown và thứ tự lifecycle phù hợp.

## 11. Chẩn đoán khi scheduled task ngừng chạy

Khi một tác vụ định kỳ không còn chạy, kiểm tra theo thứ tự:

1. **Scheduler còn hoạt động không?** Kiểm tra bean scheduler, thread pool và trạng thái ApplicationContext.
2. **Task có còn được schedule không?** Với `ScheduledFuture`, kiểm tra task đã bị cancel hoặc completed bất thường chưa.
3. **Lần chạy trước có ném exception không?** Tìm stack trace và xác định error handler đã suppress hay propagate.
4. **Error handler có tự lỗi không?** Kiểm tra lỗi logging, metrics, cảnh báo hoặc thao tác phụ trợ trong handler.
5. **Poller có error channel không?** Xác minh channel tồn tại, có subscriber và error flow đang hoạt động.
6. **Task có bị block không?** Kiểm tra thread dump, I/O timeout, lock và thời gian thực thi.
7. **Có task nào chiếm hết scheduler pool không?** Đối chiếu active threads, queue và thời gian chạy của từng nhóm task.
8. **Context có đang shutdown không?** Kiểm tra `RejectedExecutionException`, lifecycle phase và thời điểm bean bị destroy.

Metrics hữu ích gồm số lần chạy, số lần lỗi, thời điểm chạy thành công gần nhất, thời lượng task, số task đang active, queue depth và số lần scheduler từ chối task. Với poller, bổ sung số message nhận được, số lần poll rỗng và số `ErrorMessage` đã publish.

## 12. Kiểm thử ErrorHandler

Có thể kiểm tra chính sách error handler bằng một task lặp lại có chủ đích ném exception ở lần đầu và thành công ở lần tiếp theo. Dùng latch để đồng bộ thay vì chờ bằng `Thread.sleep()`:

```java
AtomicInteger attempts = new AtomicInteger();
CountDownLatch succeeded = new CountDownLatch(1);

Runnable task = () -> {
    if (attempts.incrementAndGet() == 1) {
        throw new IllegalStateException("temporary failure");
    }
    succeeded.countDown();
};

ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(1);
scheduler.setErrorHandler(error -> log.warn("Scheduled task failed", error));
scheduler.initialize();

ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
    task,
    100L
);

assertTrue(succeeded.await(2, TimeUnit.SECONDS));
future.cancel(false);
scheduler.shutdown();
```

Đây là ví dụ minh họa; test thực tế cần đặt cleanup trong `finally` hoặc teardown để luôn cancel future và shutdown scheduler kể cả khi assertion thất bại. Có thể tạo test đối chứng với error handler propagate để xác minh future không tiếp tục chạy sau exception.

Với poller, tạo một `QueueChannel`, cấu hình `errorChannel`, gửi message làm handler ném exception và xác minh error flow nhận được `ErrorMessage`. Bổ sung trường hợp receive/source ném exception để kiểm tra khi không có original message. Test cần kiểm soát thời điểm và timeout, tránh phụ thuộc vào tốc độ máy chạy.

## 13. Những lỗi thiết kế thường gặp

- **Cho rằng log-and-suppress nghĩa là task thành công.** Lịch tiếp tục nhưng nghiệp vụ có thể vẫn thất bại.
- **Để error handler ném exception phụ.** Một lỗi trong cảnh báo hoặc metrics có thể làm lịch lặp dừng.
- **Dùng scheduler error handler để xử lý mọi lỗi message.** Lỗi đã được poller chuyển thành `ErrorMessage` có thể không thoát ra scheduler.
- **Chỉ ghi log mà không lưu trạng thái.** Không thể biết task đã lỗi bao nhiêu lần hoặc dữ liệu nào chưa được xử lý.
- **Nhầm error handling với retry.** Ghi log hoặc publish `ErrorMessage` không tự chạy lại message gốc.
- **Retry vô hạn.** Có thể gây quá tải, lặp side effect và che giấu lỗi cấu hình.
- **Dùng một scheduler pool quá nhỏ.** Task chậm hoặc error handler chặn lâu có thể làm các poller khác trễ.
- **Không kiểm tra error channel subscriber.** ErrorMessage có thể không được xử lý như mong muốn.
- **Không kiểm thử trường hợp task lặp bị exception.** Một lỗi có thể khiến lịch dừng mà không được phát hiện sớm.

## 14. Checklist thiết kế

Trước khi đưa scheduled task hoặc poller vào vận hành, hãy xác định:

- Task chạy một lần hay lặp lại?
- Scheduler nào thực thi task và error handler nào được gắn với scheduler đó?
- Chính sách mặc định là suppress hay propagate?
- Khi lỗi xảy ra, task tiếp tục lần sau hay phải dừng có chủ đích?
- Nếu là poller, lỗi được publish vào error channel nào và ai tiêu thụ `ErrorMessage`?
- Error flow có giữ message gốc, exception cause và correlation ID khi có thể không?
- Retry áp dụng ở ranh giới nào, có giới hạn và backoff ra sao?
- Metric nào cho biết lần thành công gần nhất và số lần lỗi?
- Error handler có thể tự lỗi hoặc block scheduler thread không?
- Khi context shutdown, scheduler và error flow có đủ thời gian hoàn tất không?

Khi phân biệt được scheduler-level `ErrorHandler`, poller `errorChannel`, retry advice và transaction boundary, scheduled task có thể vừa tiếp tục hoạt động sau lỗi tạm thời vừa giữ được dấu vết cần thiết để phục hồi. Điều quan trọng là mỗi lớp chịu trách nhiệm đúng phần của nó: scheduler điều khiển lịch, error handler xử lý exception thoát ra khỏi task, còn error flow quản lý lỗi gắn với message và nghiệp vụ.
