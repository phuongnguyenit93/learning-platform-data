# Thread naming, uncaught exception và shutdown

Trong Spring Integration, `TaskExecutor` đưa công việc sang worker thread để tách thời điểm gửi message hoặc kích hoạt poller khỏi thời gian xử lý thực tế. Khi flow chạy trên nhiều thread, việc quan sát và quản lý vòng đời trở nên quan trọng: tên thread giúp tìm đúng công việc trong log và thread dump; cơ chế xử lý exception giúp phát hiện lỗi không còn nằm trên call stack của producer; shutdown có kiểm soát giúp task đang chạy được hoàn tất trong giới hạn thời gian.

Ba chủ đề này liên quan trực tiếp đến độ tin cậy của runtime. Một thread pool có thể vẫn hoạt động nhưng log không cho biết task nào đang chạy; exception có thể bị giữ trong `Future` nên không xuất hiện ở uncaught handler; hoặc ứng dụng đóng context trong khi executor còn task đang chờ. Cần hiểu đúng từng đường đi của task trước khi cấu hình.

Sau bài này, bạn có thể:

- Đặt tên thread có ý nghĩa bằng `ThreadPoolTaskExecutor`.
- Truyền correlation/MDC context qua ranh giới thread bằng `TaskDecorator`.
- Phân biệt exception từ `execute()`, `submit()`, `@Async` và scheduled task.
- Chọn cơ chế xử lý exception và rejection phù hợp.
- Cấu hình executor shutdown, thời gian chờ và cách xử lý task còn tồn đọng.
- Chẩn đoán thread pool bị nghẽn, task bị từ chối hoặc shutdown kéo dài.

## 1. Thread pool trong Spring Integration

`TaskExecutor` là abstraction thực thi `Runnable`. Spring cung cấp các implementation và adapter để ứng dụng dùng executor mà không phụ thuộc trực tiếp vào một thư viện thread pool cụ thể. `ThreadPoolTaskExecutor` là lựa chọn phổ biến khi cần cấu hình core/max pool size, queue capacity, thread name prefix và lifecycle do Spring quản lý.

Trong Spring Integration, executor có thể được dùng ở nhiều vị trí:

- `ExecutorChannel` chuyển việc dispatch message sang worker thread.
- Poller có thể dùng executor để tách công việc poll khỏi scheduler thread.
- Các service bất đồng bộ hoặc `@Async` có thể dùng executor riêng.
- Một số adapter và component tích hợp có executor nội bộ hoặc nhận executor do ứng dụng cấu hình.

Không nên gom mọi loại công việc vào một pool duy nhất mà không xem xét tải. Nếu xử lý HTTP chậm chiếm hết worker, task khác như cập nhật trạng thái hoặc gửi thông báo có thể phải chờ. Tách pool theo loại công việc giúp giới hạn ảnh hưởng, nhưng cũng làm tăng số queue, số thread và chi phí vận hành cần quan sát.

## 2. Đặt tên thread để quan sát runtime

Tên thread mặc định như `pool-3-thread-2` không cho biết thread thuộc flow hay executor nào. Đặt prefix riêng giúp nhận diện thread trong log, thread dump, profiler và công cụ giám sát.

Ví dụ cấu hình `ThreadPoolTaskExecutor`:

```java
@Bean
ThreadPoolTaskExecutor integrationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("si-orders-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    return executor;
}
```

Worker thread sẽ có tên bắt đầu bằng `si-orders-`; phần số phía sau do thread factory quản lý. Prefix nên thể hiện vai trò hoặc nhóm công việc, chẳng hạn `si-poller-`, `si-inventory-`, `si-notification-`. Tránh đặt tên quá dài hoặc chứa thông tin động như order ID vì thread được tái sử dụng cho nhiều task khác nhau.

Ví dụ log tên thread:

```java
log.info("Processing order {} on thread {}",
        order.getId(), Thread.currentThread().getName());
```

Tên thread trả lời câu hỏi “task đang chạy trên worker nào?”. Nó không phải định danh message hay correlation ID. Một worker thread có thể lần lượt xử lý nhiều message khác nhau, nên không dùng thread name để suy ra quan hệ nghiệp vụ hoặc thứ tự message.

### 2.1. Khi cần tùy chỉnh ThreadFactory

`setThreadNamePrefix()` đủ cho hầu hết trường hợp. Nếu cần cài `UncaughtExceptionHandler` riêng cho từng worker, có thể cung cấp `ThreadFactory`. Khi dùng factory riêng, hãy tự đặt tên thread trong factory vì cách đặt tên của factory sẽ thay thế cơ chế tạo thread mặc định của executor.

```java
AtomicInteger sequence = new AtomicInteger();

executor.setThreadFactory(task -> {
    Thread thread = new Thread(
            task,
            "si-orders-worker-" + sequence.incrementAndGet());
    thread.setUncaughtExceptionHandler((worker, error) ->
            log.error("Uncaught error on {}", worker.getName(), error));
    return thread;
});
```

Đây là cách minh họa một factory tùy chỉnh; trong ứng dụng thực tế, cần giữ các thuộc tính thread phù hợp với môi trường, ví dụ daemon status, thread group và class loader context. Không tạo thread mới cho từng message bằng tay khi đã có executor quản lý pool.

## 3. Thread name và MDC không giống nhau

Logging framework thường hỗ trợ MDC (Mapped Diagnostic Context) để gắn metadata vào log, ví dụ `traceId`, `correlationId`, `tenantId` hoặc `messageId`. MDC thường dựa trên `ThreadLocal`. Khi task chuyển sang worker thread, MDC từ thread gửi không tự động được sao chép sang worker.

Nếu chỉ đặt tên thread, log có thể cho biết `si-orders-2` đang chạy nhưng không cho biết task đó thuộc đơn hàng hay trace nào. Hãy dùng MDC để lưu thông tin theo từng lần xử lý và truyền context qua ranh giới executor một cách có kiểm soát.

`TaskDecorator` cho phép bọc `Runnable` trước khi executor thực thi. Ví dụ sau chụp MDC của thread gửi, cài nó trên worker trong thời gian chạy task và khôi phục context cũ sau khi hoàn tất:

```java
public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(captured);
                }
                task.run();
            }
            finally {
                if (previous == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
```

Đăng ký decorator với executor:

```java
executor.setTaskDecorator(new MdcTaskDecorator());
```

Phần `finally` rất quan trọng. Worker thread được tái sử dụng; nếu không khôi phục hoặc xóa MDC, metadata của message trước có thể rò sang log của message sau. `TaskDecorator` chỉ truyền những context được code chụp và cài đặt; nó không tự động truyền mọi `ThreadLocal`, transaction hay security context. Với tracing/security, hãy dùng cơ chế context propagation phù hợp của framework tương ứng.

## 4. Exception đi theo đường nào?

Không phải exception nào xảy ra trên worker thread cũng được gửi đến cùng một handler. Cách quan sát lỗi phụ thuộc cách task được thực thi:

| Cách chạy task | Exception được quan sát ở đâu? |
|---|---|
| `execute(Runnable)` | Exception thoát khỏi `run()` có thể kết thúc worker hiện tại và đi đến `UncaughtExceptionHandler` của thread. |
| `submit(Runnable/Callable)` | Exception được lưu trong `Future`; caller thấy nó khi gọi `get()` dưới dạng `ExecutionException`. |
| `@Async` trả về `Future`/`CompletableFuture` | Caller quan sát lỗi qua kết quả bất đồng bộ. |
| `@Async` trả về `void` | Dùng `AsyncUncaughtExceptionHandler` để xử lý exception không có future trả về. |
| Scheduled task | Dùng `ErrorHandler` của scheduler; chính sách log/propagate/suppress phụ thuộc cấu hình và loại lịch. |
| Spring Integration message flow | Xem exception propagation và error channel/error flow được cấu hình cho endpoint. |

Vì vậy, chỉ cài `UncaughtExceptionHandler` không đủ để bắt mọi lỗi từ executor. Đặc biệt, task chạy qua `submit()` thường được bọc trong `FutureTask`; exception được giữ trong future và không thoát ra khỏi `run()` để kích hoạt uncaught handler.

## 5. execute(): exception thoát khỏi worker thread

`execute()` giao một `Runnable` cho executor nhưng không trả về `Future`. Nếu `Runnable.run()` ném exception không được bắt bên trong task, exception có thể thoát khỏi worker thread. Với `ThreadPoolExecutor`, worker đang chạy task lỗi có thể kết thúc và pool tạo worker thay thế khi cần. `UncaughtExceptionHandler` của thread có thể ghi nhận lỗi này.

```java
integrationExecutor.execute(() -> {
    processOrder(order); // Có thể ném RuntimeException
});
```

Nếu muốn quan sát lỗi tại ranh giới task, có thể bọc xử lý trong `try/catch` và ghi log hoặc chuyển lỗi sang cơ chế recovery của ứng dụng:

```java
integrationExecutor.execute(() -> {
    try {
        processOrder(order);
    }
    catch (Exception ex) {
        log.error("Order processing failed: {}", order.getId(), ex);
        throw ex;
    }
});
```

Ví dụ trên ghi log rồi ném lại để exception tiếp tục đi theo cơ chế của executor. Nếu chỉ ghi log rồi nuốt exception, hệ thống có thể coi task đã hoàn tất dù nghiệp vụ thất bại. Hãy quyết định rõ task cần retry, đưa vào error flow hay đánh dấu thất bại trong kho dữ liệu.

## 6. submit(): exception được giữ trong Future

`submit()` trả về `Future`. Executor bọc task trong đối tượng có khả năng lưu kết quả và exception. Vì exception được ghi nhận trong future, nó thường không trở thành uncaught exception của worker thread.

```java
Future<?> future = integrationExecutor.submit(() -> processOrder(order));

try {
    future.get();
}
catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    log.error("Order task failed: {}", order.getId(), cause);
}
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    log.warn("Waiting for order task was interrupted", ex);
}
```

`get()` chờ task hoàn tất và ném `ExecutionException` nếu task thất bại. Trong luồng xử lý bất đồng bộ, tránh gọi `get()` ngay trên thread gửi nếu mục tiêu là không block thread đó; có thể dùng callback hoặc composition của `CompletableFuture` để xử lý kết quả khi hoàn tất.

Nếu caller bỏ qua `Future`, exception có thể không được quan sát ở nơi mong muốn. Hãy giữ và xử lý future, hoặc dùng API callback có cơ chế ghi nhận lỗi rõ ràng.

## 7. Exception của @Async và scheduled task

### 7.1. @Async

Với phương thức `@Async` trả về `Future` hoặc `CompletableFuture`, lỗi được phản ánh trong kết quả bất đồng bộ. Với phương thức `@Async void`, không có future để caller đọc, nên Spring dùng `AsyncUncaughtExceptionHandler`.

```java
@Configuration
@EnableAsync
class AsyncConfiguration implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, params) ->
                log.error("Async method {} failed",
                        method.toGenericString(), error);
    }
}
```

Handler này dành cho exception từ phương thức `@Async` trả về `void`. Nó không phải handler chung cho mọi `Runnable` chạy trên `ThreadPoolTaskExecutor` và cũng không thay thế error channel của Spring Integration.

### 7.2. Scheduled task

Với `TaskScheduler`, có thể cấu hình `ErrorHandler` để quyết định cách ghi nhận exception từ scheduled callback:

```java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(2);
scheduler.setThreadNamePrefix("si-scheduler-");
scheduler.setErrorHandler(error ->
        log.error("Scheduled task failed", error));
```

Chính sách xử lý lỗi lặp lại có thể khác với one-shot task và tùy scheduler/trigger. Một số cấu hình mặc định ghi log rồi tiếp tục lịch lặp; cấu hình khác có thể để exception lan ra làm tác vụ định kỳ không tiếp tục theo semantics của scheduler. Nếu việc chạy tiếp hay dừng lịch có ý nghĩa nghiệp vụ, hãy cấu hình `ErrorHandler` tường minh và kiểm thử.

### 7.3. Spring Integration error channel

Trong message flow, exception từ handler có thể được xử lý qua error channel/error flow theo cấu hình endpoint và message header tương ứng. Đây là đường xử lý lỗi ở tầng message. Nó không tự động thay thế `Future.get()`, `AsyncUncaughtExceptionHandler` hoặc `TaskScheduler.ErrorHandler`; cần xác định task đang chạy trong cơ chế nào trước khi tìm lỗi.

## 8. RejectedExecutionHandler khi pool quá tải

Executor có giới hạn về số worker và queue capacity. Khi không thể nhận thêm task, `ThreadPoolExecutor` áp dụng `RejectedExecutionHandler`.

| Chính sách | Hành vi | Lưu ý |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException`. | Thất bại rõ ràng; caller cần xử lý hoặc báo lỗi. |
| `CallerRunsPolicy` | Thread gửi tự chạy task nếu executor chưa shutdown. | Tạo back-pressure tự nhiên nhưng có thể làm chậm producer hoặc scheduler thread. |
| `DiscardPolicy` | Bỏ task mới mà không báo lỗi. | Nguy cơ mất công việc âm thầm. |
| `DiscardOldestPolicy` | Bỏ task cũ nhất đang chờ rồi thử submit task mới. | Có thể làm mất công việc cũ; cần cân nhắc thứ tự và tính toàn vẹn. |

Với message nghiệp vụ, chính sách bỏ task âm thầm thường nguy hiểm. `AbortPolicy` làm lỗi dễ quan sát nhưng cần recovery ở producer hoặc error flow. `CallerRunsPolicy` có thể hữu ích như back-pressure khi caller có thể chịu việc chạy đồng bộ; tuy nhiên, nếu caller là scheduler thread, nó có thể đưa công việc dài quay lại scheduler và gây trễ lịch.

Hãy đo active thread, queue depth và số lần rejection. Queue quá lớn không làm executor xử lý nhanh hơn; nó chỉ cho phép backlog và thời gian chờ tăng thêm.

## 9. Cấu hình executor có quan sát và shutdown

Một cấu hình mẫu kết hợp prefix, MDC propagation, queue có giới hạn, rejection rõ ràng và graceful shutdown:

```java
@Configuration
class IntegrationExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor integrationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("si-runtime-");
        executor.setTaskDecorator(new MdcTaskDecorator());
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

Đây là giá trị minh họa, không phải sizing khuyến nghị cho mọi hệ thống. Core/max pool size cần dựa trên loại task (CPU-bound hay I/O-bound), thời gian xử lý, giới hạn database/API và số task đồng thời. Queue capacity cần đủ để hấp thụ dao động ngắn nhưng không quá lớn đến mức che giấu quá tải.

`ThreadPoolTaskExecutor` được Spring quản lý khi khai báo thành bean. Tránh tự gọi `initialize()` hoặc `shutdown()` tùy tiện từ service nghiệp vụ; để lifecycle của ApplicationContext quản lý executor, trừ khi ứng dụng có một flow quản trị riêng được thiết kế rõ ràng.

## 10. Graceful shutdown: dừng nhận task và chờ task hoàn tất

Khi ứng dụng đóng ApplicationContext, executor cần biết xử lý thế nào với task đang chạy và task đang nằm trong queue. `ThreadPoolTaskExecutor` kế thừa các tùy chọn lifecycle từ `ExecutorConfigurationSupport`.

Hai thuộc tính thường dùng:

- `setWaitForTasksToCompleteOnShutdown(true)`: yêu cầu executor shutdown theo cách cho phép task đã nhận, gồm task đang chạy và task chờ trong queue, tiếp tục hoàn tất thay vì hủy ngay lập tức.
- `setAwaitTerminationSeconds(30)`: giới hạn khoảng thời gian chờ executor kết thúc trong quá trình shutdown.

Khi không chờ task hoàn tất, executor có thể dùng cơ chế shutdown mạnh hơn, yêu cầu interrupt task đang chạy và không tiếp tục task đang chờ. Interrupt chỉ là yêu cầu; task phải hợp tác bằng cách xử lý `InterruptedException` hoặc kiểm tra interrupt status. Một lời gọi I/O không có timeout hoặc code bỏ qua interrupt có thể vẫn chạy lâu.

### 10.1. Thứ tự shutdown trong message flow

Nên dừng nguồn tạo thêm công việc trước, sau đó mới đóng executor mà các endpoint đang sử dụng:

```text
1. Stop producer / inbound adapter / poller
                    |
                    v
2. Ngừng submit message/task mới
                    |
                    v
3. Chờ worker xử lý task đang chạy và task đã nhận
                    |
                    v
4. Đóng executor sau khi component phụ thuộc đã dừng
                    |
                    v
5. Hoàn tất shutdown ApplicationContext
```

Thứ tự cụ thể còn phụ thuộc lifecycle phase và component. Nếu executor dừng trước endpoint vẫn đang gửi task, các lần submit tiếp theo có thể bị từ chối. Ngược lại, nếu chờ vô hạn task trong queue nhưng task không thể hoàn tất vì downstream đã đóng, shutdown có thể kéo dài đến timeout.

### 10.2. Task còn chờ sau timeout

Nếu hết thời gian chờ mà worker chưa kết thúc, ứng dụng cần có chính sách rõ ràng cho task chưa hoàn tất. Không nên giả định task đã xử lý xong chỉ vì context đã bắt đầu shutdown. Với công việc quan trọng, hãy thiết kế tính idempotent, lưu trạng thái hoặc sử dụng broker bền vững để có thể phục hồi sau restart.

Queue của `ThreadPoolTaskExecutor` thường là queue trong bộ nhớ. Task còn nằm trong queue khi process dừng không tự động được lưu để chạy lại sau khi ứng dụng khởi động. Nếu cần bảo đảm công việc tồn tại qua restart, dùng message broker hoặc persistent store phù hợp thay vì dựa vào executor queue.

## 11. Quan sát executor trong runtime

`ThreadPoolTaskExecutor` cung cấp quyền truy cập đến `ThreadPoolExecutor` sau khi khởi tạo. Có thể đọc một số thông tin vận hành:

```java
ThreadPoolExecutor pool = integrationExecutor.getThreadPoolExecutor();

log.info("poolSize={}, active={}, queued={}, completed={}",
        pool.getPoolSize(),
        pool.getActiveCount(),
        pool.getQueue().size(),
        pool.getCompletedTaskCount());
```

Các số liệu nên được quan sát theo thời gian, không chỉ đọc một lần:

- Pool size và active count cho biết worker đang sử dụng.
- Queue size và queue wait cho biết backlog tích tụ.
- Completed task count cho biết lượng công việc đã hoàn tất.
- Rejected execution count cần được ghi nhận riêng trong rejection handler hoặc metric phù hợp.
- Task duration và lỗi theo loại công việc cho biết worker đang bị chiếm bởi đâu.

Nếu active count thường xuyên bằng max pool size và queue tăng đều, executor đang thiếu năng lực hoặc downstream bị chậm. Nếu active count thấp nhưng task vẫn trễ, điểm nghẽn có thể nằm ở scheduler, upstream hoặc queue khác.

## 12. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Log chỉ có `pool-1-thread-1` | Chưa đặt thread name prefix. | Đặt prefix theo vai trò executor. |
| Log worker thiếu trace/correlation ID | MDC không tự truyền qua thread. | Dùng `TaskDecorator` hoặc context propagation phù hợp. |
| Uncaught handler không thấy exception từ `submit()` | Exception nằm trong `Future`. | Đọc `Future.get()` hoặc gắn completion callback. |
| `@Async void` lỗi nhưng caller không biết | Không có Future để nhận kết quả. | Cấu hình `AsyncUncaughtExceptionHandler`. |
| Scheduled task ngừng hoặc lỗi không rõ | Chưa cấu hình `ErrorHandler` và chưa phân biệt periodic/one-shot. | Cấu hình error policy cho scheduler. |
| Task bị mất khi executor quá tải | Dùng discard rejection policy. | Chọn rejection rõ ràng và thiết kế back-pressure/recovery. |
| Producer bị chậm bất ngờ | `CallerRunsPolicy` thực thi task trên caller thread. | Xác định caller là scheduler, request thread hay producer. |
| Shutdown kéo dài | Task chờ I/O, queue backlog hoặc không phản hồi interrupt. | Đặt timeout, dừng producer trước và theo dõi await termination. |
| Task không chạy lại sau restart | Executor queue chỉ nằm trong bộ nhớ. | Dùng broker/persistent store nếu cần độ bền. |

## 13. Quy trình chẩn đoán

Khi task chạy bất đồng bộ bị lỗi hoặc executor shutdown không đúng kỳ vọng, thực hiện theo trình tự:

1. **Xác định executor.** Tìm bean name, thread prefix và component đang sử dụng executor.
2. **Xác định cách submit.** Task được gọi bằng `execute`, `submit`, `@Async`, scheduler hay Spring Integration endpoint?
3. **Tìm đúng nơi nhận lỗi.** Kiểm tra uncaught handler, Future, async exception handler, scheduler ErrorHandler hoặc error channel.
4. **Đọc thread dump và metrics.** Xem worker nào đang chạy, queue có tăng, pool có chạm max hay không.
5. **Kiểm tra rejection.** Xác nhận task có bị từ chối hoặc bị discard khi pool quá tải không.
6. **Kiểm tra shutdown policy.** Xác nhận producer đã dừng trước executor, wait flag và timeout phù hợp.
7. **Xác nhận khả năng phục hồi.** Task quan trọng có được lưu bền vững hoặc có thể retry/idempotent sau restart không?

## 14. Tự kiểm tra

**Tình huống:** Một `ExecutorChannel` dùng `ThreadPoolTaskExecutor`. Log cho thấy thread `si-runtime-2` xử lý nhiều message khác nhau. Một task ném exception nhưng `UncaughtExceptionHandler` không ghi nhận. Khi ứng dụng shutdown, queue còn 40 task.

1. Vì sao thread name không thể dùng để xác định message cụ thể?
2. Nếu task được gửi bằng `submit()`, exception nằm ở đâu?
3. Cần cấu hình gì để trace ID từ thread gửi xuất hiện trong log worker?
4. Làm thế nào để chờ task đã nhận hoàn tất khi shutdown?
5. Executor queue còn task có tự được phục hồi sau khi process restart không?

**Gợi ý trả lời:** (1) Worker thread được tái sử dụng cho nhiều task; dùng message ID/correlation ID trong MDC. (2) Exception được giữ trong `Future` và caller cần đọc kết quả. (3) Dùng `TaskDecorator` để chụp/cài/khôi phục MDC hoặc cơ chế context propagation. (4) Cấu hình `waitForTasksToCompleteOnShutdown` và thời gian chờ phù hợp, đồng thời dừng producer trước executor. (5) Không; queue executor thường ở bộ nhớ, cần broker hoặc persistent store nếu cần phục hồi.

**Bài tập thực hành:** Tạo hai executor có prefix khác nhau cho hai nhóm công việc. Gửi một task bằng `execute()` và một task bằng `submit()`; cố ý ném exception để quan sát hai đường xử lý. Thêm MDC `correlationId`, cấu hình `TaskDecorator`, rồi kiểm tra log ở worker. Cuối cùng, tạo backlog và shutdown với hai chính sách chờ/không chờ để quan sát thời gian kết thúc và task còn lại.

## Tài liệu tham khảo

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadoc — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework Javadoc — TaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework Javadoc — AsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html)
- [Java Javadoc — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
