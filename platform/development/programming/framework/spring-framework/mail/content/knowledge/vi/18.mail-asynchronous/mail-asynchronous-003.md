# TaskExecutor và thread pool cho mail trong Spring Framework Mail

Gửi email qua SMTP là một thao tác I/O: ứng dụng phải kết nối tới mail server, gửi dữ liệu MIME và chờ phản hồi từ mạng. Nếu thực hiện ngay trên thread đang xử lý HTTP request, thời gian chờ SMTP có thể làm response chậm, giữ thread của web server và giảm khả năng phục vụ các request khác. Spring cung cấp `TaskExecutor` cùng các implementation thread pool để chuyển công việc gửi mail sang những thread được quản lý riêng.

Một thread pool giúp kiểm soát số tác vụ chạy đồng thời, hàng đợi công việc đang chờ, cách xử lý khi quá tải và vòng đời thread khi ứng dụng shutdown. Tuy nhiên, **bất đồng bộ không đồng nghĩa với bền vững**. Task được đưa vào hàng đợi trong bộ nhớ có thể mất khi process dừng đột ngột. Với email giao dịch quan trọng, thread pool thường là cơ chế thực thi worker; transactional outbox hoặc message broker mới là nơi lưu yêu cầu gửi bền vững.

Bài học này trình bày cách cấu hình `ThreadPoolTaskExecutor`, chọn kích thước pool, dùng `@Async` với mail service, xử lý queue/rejection, truyền context, quản lý shutdown, quan sát tải và kết hợp executor với outbox.

## 1. Vì sao cần thread pool cho gửi mail?

Một request xác nhận đơn hàng có thể thực hiện:

1. Đọc và cập nhật đơn hàng trong database.
2. Tạo nội dung email.
3. Tạo MIME message.
4. Kết nối SMTP, truyền message và chờ server phản hồi.
5. Trả HTTP response.

Nếu bước 4 mất vài giây, thread xử lý request bị giữ trong suốt thời gian đó. Khi nhiều request cùng gửi mail, số thread web server đang bận có thể tăng lên dù CPU không sử dụng nhiều.

Ví dụ:

~~~text
Không dùng executor riêng

HTTP request thread
      |
      +--> cập nhật database
      |
      +--> dựng email
      |
      +--> chờ SMTP response
      |
      +--> trả HTTP response
~~~

Khi chuyển việc gửi sang executor:

~~~text
HTTP request thread
      |
      +--> cập nhật database
      |
      +--> submit mail task
      |
      +--> trả HTTP response
                  |
                  v
             Mail thread pool
                  |
                  +--> dựng MIME
                  +--> gọi JavaMailSender
                  +--> ghi nhận kết quả
~~~

Thread của request chỉ cần submit tác vụ rồi tiếp tục. Các thread trong pool thực hiện việc gửi và chờ SMTP độc lập.

Lợi ích:

- Không giữ web request thread trong thời gian chờ SMTP.
- Giới hạn số email được gửi đồng thời.
- Điều tiết tải tới SMTP provider.
- Tách tài nguyên của mail khỏi các tác vụ nền khác.
- Có thể đặt tên thread, cấu hình shutdown và theo dõi queue.
- Có thể áp dụng backpressure khi hệ thống nhận yêu cầu nhanh hơn khả năng gửi.

Nhưng executor không tự giải quyết transaction consistency, retry bền vững hoặc gửi đúng một lần. Những vấn đề đó cần thiết kế ở tầng application và persistence.

## 2. TaskExecutor là gì?

`TaskExecutor` là abstraction của Spring cho việc thực thi một `Runnable`. Nó tương tự `Executor` của Java nhưng thuộc hệ sinh thái Spring và có nhiều implementation tích hợp với lifecycle, async processing và cấu hình ứng dụng.

Ví dụ contract đơn giản:

~~~java
public interface TaskExecutor extends Executor {
    void execute(Runnable task);
}
~~~

Application có thể phụ thuộc vào `TaskExecutor` thay vì tự tạo thread bằng `new Thread(...)`.

Spring có các implementation thường gặp:

| Implementation | Đặc điểm | Trường hợp sử dụng |
| --- | --- | --- |
| `SyncTaskExecutor` | Chạy task ngay trên thread gọi | Test hoặc xử lý đồng bộ |
| `SimpleAsyncTaskExecutor` | Tạo thread mới cho task, không phải pool tái sử dụng theo cách thông thường | Tác vụ ít, không phù hợp làm pool có giới hạn tải |
| `ThreadPoolTaskExecutor` | Bọc Java `ThreadPoolExecutor`, cấu hình core/max/queue | Mail workload cần giới hạn concurrency |
| `ConcurrentTaskExecutor` | Adapter cho Java Executor hiện có | Tích hợp executor được tạo ở nơi khác |
| `TaskExecutorAdapter` | Adapter từ Java Executor sang Spring abstraction | Kết nối code dùng Java concurrency với Spring |

Với gửi mail, `ThreadPoolTaskExecutor` thường là lựa chọn phù hợp vì có thể giới hạn thread và queue. Không nên tạo một thread mới cho mỗi email; khi traffic tăng, số thread không được kiểm soát có thể làm cạn tài nguyên hệ điều hành, connection và SMTP quota.

### TaskExecutor không phải message queue bền vững

`ThreadPoolTaskExecutor` có queue trong bộ nhớ của process. Khi ứng dụng bị kill, restart hoặc mất máy, các task chưa chạy trong queue có thể mất. Queue của executor chỉ điều phối công việc trong thời gian process đang hoạt động.

| Thành phần | Vai trò |
| --- | --- |
| TaskExecutor | Chọn thread thực thi task và điều tiết concurrency |
| In-memory task queue | Giữ task đang chờ trong process |
| Database outbox | Lưu yêu cầu gửi bền vững cùng transaction nghiệp vụ |
| Message broker | Lưu/chuyển message giữa các process theo durability và delivery semantics của broker |
| SMTP provider | Nhận email và xử lý việc gửi tiếp |

Nếu email chỉ là thông báo best-effort, executor trong bộ nhớ có thể đủ. Nếu email xác nhận giao dịch, hóa đơn hoặc thông báo cần retry sau restart, hãy lưu yêu cầu vào outbox/broker rồi dùng executor để thực thi worker.

## 3. Thread pool hoạt động như thế nào?

Một thread pool thường có ba phần:

- **Worker threads**: các thread đang thực thi task.
- **Task queue**: các task chờ tới lượt chạy.
- **Rejection policy**: cách xử lý khi pool không thể nhận thêm task.

Với `ThreadPoolExecutor`, thứ tự xử lý khi submit task về cơ bản là:

1. Nếu số worker đang chạy ít hơn core pool size, tạo worker để chạy task.
2. Nếu đã đạt core pool size, thử đưa task vào queue.
3. Nếu queue không nhận thêm được task, tạo thêm worker tới maximum pool size.
4. Nếu đã đạt maximum và queue cũng đầy, áp dụng rejection handler.

Sơ đồ:

~~~text
Submit task
    |
    v
Worker count < corePoolSize?
    |
   Yes -----------------> Tạo worker chạy task
    |
   No
    |
    v
Queue còn chỗ?
    |
   Yes -----------------> Đưa task vào queue
    |
   No
    |
    v
Worker count < maxPoolSize?
    |
   Yes -----------------> Tạo worker bổ sung
    |
   No
    |
    v
Rejection policy
~~~

Một điểm quan trọng: khi queue còn chỗ, pool thường ưu tiên queue thay vì tăng thread vượt core size. Vì vậy, nếu queue quá lớn hoặc không giới hạn, `maxPoolSize` có thể hầu như không được sử dụng. Chỉ tăng max size mà giữ queue không giới hạn thường không giải quyết được backlog.

## 4. Ba thông số chính của ThreadPoolTaskExecutor

### corePoolSize

Số worker cơ bản mà pool cố duy trì. Các thread core thường được giữ để xử lý task tiếp theo, tùy cấu hình allowCoreThreadTimeOut.

Ví dụ core size bằng 4 có nghĩa pool có thể chạy tối thiểu khoảng bốn task đồng thời khi tải ổn định.

### maxPoolSize

Giới hạn trên số worker. Khi queue đã đầy, executor có thể tạo thêm worker cho tới mức này.

Không nên đặt max quá lớn chỉ để xử lý backlog. Với mail, mỗi worker có thể giữ một kết nối hoặc một thao tác SMTP đang chờ. Nhiều kết nối đồng thời có thể vượt quota provider hoặc làm tăng lỗi rate limit.

### queueCapacity

Số task tối đa có thể chờ trong queue của `ThreadPoolTaskExecutor`. Queue hữu hạn giúp ứng dụng có giới hạn rõ ràng cho lượng công việc đang chờ.

Nếu queue capacity bằng 100, pool có thể giữ tối đa 100 task chờ theo cấu hình queue đó, ngoài các task đang chạy. Khi queue đầy và worker đạt max, task mới bị xử lý theo rejection policy.

### keepAliveSeconds

Thời gian worker vượt core size có thể nhàn rỗi trước khi được thu hồi. Giá trị này hữu ích khi có tải tăng đột biến rồi giảm xuống.

### Ví dụ cấu hình

~~~java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean(name = "mailTaskExecutor")
    public ThreadPoolTaskExecutor mailTaskExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("mail-");

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);

        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy()
        );

        return executor;
    }
}
~~~

Spring quản lý lifecycle của bean và khởi tạo executor. Không cần gọi `initialize()` thủ công khi bean được đăng ký theo cách thông thường.

Các con số 4, 8 và 100 chỉ là ví dụ. Cấu hình production cần dựa trên throughput mong muốn, thời gian SMTP, quota provider, tài nguyên máy và mức backlog có thể chấp nhận.

## 5. Queue hữu hạn và vì sao không nên dùng queue vô hạn

Một queue vô hạn có vẻ giúp không bao giờ từ chối task, nhưng nó có thể che giấu việc hệ thống đang nhận công việc nhanh hơn tốc độ gửi.

Giả sử:

- Ứng dụng nhận 100 yêu cầu email mỗi giây.
- SMTP worker chỉ gửi được 20 email mỗi giây.
- Chênh lệch 80 task mỗi giây tích lũy vào queue.

Sau một phút, backlog có thể tăng thêm khoảng 4.800 task. Queue càng dài, email càng trễ và memory càng bị chiếm dụng.

~~~text
Tốc độ nhận: 100 email/giây
Tốc độ gửi:   20 email/giây
Chênh lệch:   80 email/giây

Sau 60 giây:
  backlog tăng khoảng 4.800 email
~~~

Queue hữu hạn giúp xác định một điểm quá tải. Khi đạt giới hạn, ứng dụng phải chọn hành vi rõ ràng: từ chối để retry sau, chạy task trên caller thread để tạo backpressure trong điều kiện phù hợp, hoặc chuyển yêu cầu vào durable queue/outbox.

### Queue capacity ảnh hưởng độ trễ

Queue lớn có thể giảm rejection ngắn hạn nhưng tăng thời gian chờ. Với email OTP hoặc thông báo thời gian nhạy cảm, một task nằm trong queue vài phút có thể đã hết giá trị.

Nên chọn capacity theo:

- Thời gian chờ tối đa mà nghiệp vụ chấp nhận.
- Tốc độ task được submit.
- Throughput thực tế của worker.
- Dung lượng heap.
- Giới hạn rate/concurrent connections của provider.
- Cơ chế retry khi executor từ chối.

Không coi queue càng lớn càng tốt.

## 6. Chọn rejection policy khi pool quá tải

Khi queue đầy và số worker đã đạt max, Java thread pool phải quyết định cách xử lý task mới.

| Policy | Hành vi | Lưu ý với gửi mail |
| --- | --- | --- |
| `AbortPolicy` | Ném exception khi không nhận task | Dễ phát hiện quá tải; caller phải xử lý và lưu/retry yêu cầu |
| `CallerRunsPolicy` | Thread submit tự chạy task nếu executor vẫn hoạt động | Tạo backpressure, nhưng có thể khiến HTTP request thread gửi mail đồng bộ |
| `DiscardPolicy` | Bỏ task mới mà không báo lỗi | Rất nguy hiểm với email vì yêu cầu có thể mất im lặng |
| `DiscardOldestPolicy` | Bỏ task cũ nhất trong queue rồi thử submit task mới | Có thể làm mất thông báo cũ; hiếm khi phù hợp với mail giao dịch |

### AbortPolicy

Đây thường là lựa chọn dễ quan sát nhất cho mail workload:

~~~java
executor.setRejectedExecutionHandler(
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Khi không nhận được task, lời gọi submit/async có thể thất bại bằng exception rejection. Application boundary cần bắt lỗi đó hoặc để nó đi tới nơi có thể ghi nhận, rồi quyết định retry/lưu yêu cầu.

Nếu yêu cầu gửi chỉ tồn tại trong request hiện tại, rejection có thể làm mất ý định gửi nếu caller không xử lý. Với outbox, worker có thể giữ record ở trạng thái pending/retry để thử lại sau.

### CallerRunsPolicy

~~~java
executor.setRejectedExecutionHandler(
    new ThreadPoolExecutor.CallerRunsPolicy()
);
~~~

Policy này chạy task trên thread gọi submit khi executor đang hoạt động. Nó làm chậm producer và tạo backpressure tự nhiên. Tuy nhiên:

- HTTP request thread có thể phải chờ SMTP.
- Một tác vụ submit từ transaction thread có thể chạy gửi mail ngay trên thread đó.
- Response time có thể tăng mạnh trong lúc pool quá tải.
- Khi executor đã shutdown, hành vi của CallerRunsPolicy không bảo đảm task được chạy; task có thể không được thực thi.

Do đó, không dùng CallerRunsPolicy với giả định rằng task chắc chắn được gửi bằng một thread khác hoặc luôn được chạy. Cần hiểu rõ nguồn submit và lifecycle.

### Không dùng Discard policy cho mail quan trọng

Discard policy có thể khiến task biến mất mà không có exception rõ ràng. Với email xác nhận giao dịch, hóa đơn hoặc reset password, điều này tạo ra lỗi khó truy tìm. Chỉ cân nhắc drop nếu nghiệp vụ thực sự cho phép bỏ thông báo và có metrics để quan sát.

## 7. Dùng @Async với executor được đặt tên

Spring hỗ trợ annotation `@Async` để chạy method trên executor. Bật tính năng bằng `@EnableAsync`:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Khai báo executor có tên:

~~~java
@Bean(name = "mailTaskExecutor")
public ThreadPoolTaskExecutor mailTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("mail-");
    return executor;
}
~~~

Service gửi mail:

~~~java
@Service
public class AsyncMailService {

    private final JavaMailSender mailSender;

    public AsyncMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailTaskExecutor")
    public void send(String recipient, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo(recipient);
        message.setSubject(subject);
        message.setText(body);

        mailSender.send(message);
    }
}
~~~

Khi một bean khác gọi method `send` qua Spring proxy, lời gọi được chuyển sang executor có tên `mailTaskExecutor`.

### Vì sao nên đặt tên executor?

Một ứng dụng có thể có nhiều loại công việc bất đồng bộ:

- Gửi email.
- Tạo báo cáo.
- Xử lý ảnh.
- Đồng bộ dữ liệu.
- Gửi webhook.

Nếu tất cả dùng chung một pool, tác vụ tạo báo cáo nặng có thể chiếm hết thread và làm mail bị trễ. Đặt executor riêng giúp quản lý concurrency, queue và rejection theo workload.

~~~text
Application
    |
    +--> @Async("mailTaskExecutor")
    |        +--> mail-1
    |        +--> mail-2
    |        +--> mail-3
    |
    +--> @Async("reportTaskExecutor")
             +--> report-1
             +--> report-2
~~~

Không cần tạo một pool cho mọi method. Tách khi workload có đặc tính hoặc SLA khác nhau.

## 8. Những giới hạn quan trọng của @Async

`@Async` hoạt động thông qua Spring proxy ở chế độ mặc định. Vì vậy, cách gọi method có ảnh hưởng trực tiếp đến việc task có thực sự chạy bất đồng bộ hay không.

### Method phải được gọi qua proxy

Ví dụ dễ gây hiểu nhầm:

~~~java
@Service
public class MailService {

    public void confirmOrder() {
        sendAsync(); // self-invocation
    }

    @Async("mailTaskExecutor")
    public void sendAsync() {
        // Gửi email.
    }
}
~~~

Lời gọi nội bộ từ method này sang method khác trên cùng instance không đi qua proxy Spring trong proxy mode mặc định. Vì vậy, annotation có thể không tạo async behavior như mong đợi.

Tách method async sang bean riêng:

~~~java
@Service
public class MailAsyncDispatcher {

    @Async("mailTaskExecutor")
    public void sendAsync(OutgoingMail mail) {
        // Gửi email.
    }
}
~~~

Bean nghiệp vụ inject và gọi `MailAsyncDispatcher` qua Spring.

### Không gọi async method bằng cách tự tạo object

Đoạn sau không đi qua Spring container:

~~~java
MailAsyncDispatcher dispatcher = new MailAsyncDispatcher(...);
dispatcher.sendAsync(mail);
~~~

Hãy inject bean do Spring quản lý. Nếu tự tạo object bằng `new`, annotation không được proxy áp dụng.

### Không giả định transaction được truyền sang thread khác

Transaction context của Spring thường gắn với thread hiện tại. Khi `@Async` chuyển method sang thread khác, transaction của caller không tự truyền sang worker.

Ví dụ:

~~~java
@Transactional
public void updateOrderAndSend(Long orderId) {
    updateOrder(orderId);
    asyncMailDispatcher.sendAsync(...);
}
~~~

Mail task có thể bắt đầu trước khi transaction của caller commit. Không dùng async dispatch như một cách bảo đảm gửi sau commit. Nếu cần đợi commit, dùng transaction event phù hợp hoặc tốt hơn là outbox cho yêu cầu bền vững.

## 9. Chọn kiểu trả về cho @Async

Có hai kiểu phổ biến: method trả về `void` hoặc `Future`/`CompletableFuture`.

### Method trả về void

~~~java
@Async("mailTaskExecutor")
public void send(OutgoingMail mail) {
    mailDeliveryPort.send(mail);
}
~~~

Caller không nhận được kết quả hoàn tất trực tiếp. Exception phát sinh trong method không thể ném ngược về request thread sau khi request đã tiếp tục.

Với method void, có thể cấu hình `AsyncUncaughtExceptionHandler` để ghi nhận exception:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    private final Executor mailTaskExecutor;

    public AsyncConfiguration(
            @Qualifier("mailTaskExecutor") Executor mailTaskExecutor) {
        this.mailTaskExecutor = mailTaskExecutor;
    }

    @Override
    public Executor getAsyncExecutor() {
        return mailTaskExecutor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, parameters) -> {
            // Ghi log/metrics với method và correlation ID.
        };
    }
}
~~~

Đây là handler cho exception của async method trả về void. Nó không thay thế việc lưu trạng thái, retry hay xử lý nghiệp vụ.

### Method trả về CompletableFuture

Khi caller cần quan sát kết quả, có thể trả về `CompletableFuture`:

~~~java
@Async("mailTaskExecutor")
public CompletableFuture<Void> send(OutgoingMail mail) {
    mailDeliveryPort.send(mail);
    return CompletableFuture.completedFuture(null);
}
~~~

Caller:

~~~java
CompletableFuture<Void> result = asyncMailService.send(mail);

result.whenComplete((ignored, exception) -> {
    if (exception != null) {
        // Ghi nhận lỗi hoặc phát tín hiệu xử lý phù hợp.
    }
});
~~~

Nếu method ném exception, future được hoàn tất ở trạng thái exceptional. Caller có thể dùng `whenComplete`, `handle` hoặc `exceptionally` để quan sát.

Không gọi `get()` hoặc `join()` ngay sau khi submit nếu mục tiêu là không chờ task; làm vậy sẽ biến luồng gọi thành đồng bộ về mặt thời gian chờ.

### Future không phải durable record

`CompletableFuture` cho phép quan sát kết quả trong vòng đời process. Nó không lưu task xuống database và không giúp phục hồi công việc sau khi process crash. Nếu kết quả gửi cần được theo dõi lâu dài, lưu trạng thái bằng outbox hoặc bảng notification.

## 10. Không dùng chung pool mặc định cho mọi tác vụ

Nếu không chỉ rõ executor, Spring cần chọn executor phù hợp theo cấu hình async. Trong một ứng dụng có nhiều workload, dựa vào executor mặc định khiến hành vi phụ thuộc vào cấu hình auto-configuration hoặc `AsyncConfigurer`.

Với mail, nên chỉ rõ:

~~~java
@Async("mailTaskExecutor")
public void send(OutgoingMail mail) {
    // ...
}
~~~

Điều này giúp người đọc thấy rõ tác vụ thuộc pool nào và tránh vô tình chạy mail trên executor dùng cho công việc khác.

Có thể cấu hình bean mặc định qua `AsyncConfigurer`, nhưng annotation có qualifier cụ thể thường dễ hiểu hơn khi ứng dụng có nhiều pool.

Không nên dùng `ForkJoinPool.commonPool()` cho SMTP chỉ vì nó có sẵn. Common pool được thiết kế cho một số dạng parallel computation; I/O blocking kéo dài có thể chiếm worker và ảnh hưởng các tác vụ khác dùng chung pool.

## 11. Chọn kích thước thread pool cho mail

Không có một công thức cố định áp dụng cho mọi SMTP provider. Gửi email thường là I/O-bound: thread dành nhiều thời gian chờ kết nối, ghi dữ liệu và phản hồi. Điều đó có thể cho phép concurrency cao hơn tác vụ CPU-bound, nhưng số thread vẫn bị giới hạn bởi:

- SMTP provider cho phép bao nhiêu kết nối đồng thời.
- Rate limit theo account, sender hoặc domain.
- Thời gian kết nối và gửi message.
- Kích thước email và attachment.
- Connection timeout, read timeout và write timeout.
- Tài nguyên CPU, heap, file descriptor và network.
- Mức độ quan trọng và độ trễ tối đa của email.

### Ước lượng throughput

Nếu một worker trung bình mất 2 giây cho một email và có 4 worker chạy đồng thời, throughput lý thuyết trong điều kiện ổn định khoảng:

~~~text
4 workers / 2 seconds per email
= 2 emails per second
~~~

Đây chỉ là phép tính minh họa. Thực tế còn phụ thuộc provider latency, rate limit, retry, message size và thời gian dựng template.

Nếu tăng lên 20 worker, throughput không nhất thiết tăng gấp 5. Provider có thể throttle, từ chối connection hoặc giới hạn số session. Pool lớn hơn có thể chỉ làm tăng lỗi và queue downstream.

### Công thức tham khảo cho I/O-bound

Một ước lượng khởi đầu trong bài toán thread pool tổng quát là:

~~~text
threads ≈ CPU cores × target CPU utilization
           × (1 + wait time / compute time)
~~~

Công thức này chỉ là heuristic cho workload hỗn hợp, không phải quy tắc chọn số thread SMTP. Mail provider thường có quota riêng nên cần giới hạn theo mức concurrency được phép, sau đó đo latency và throughput thật.

### Cách chọn thực tế

1. Bắt đầu với core size nhỏ.
2. Đặt max size theo giới hạn kết nối/rate của provider và tài nguyên ứng dụng.
3. Dùng queue hữu hạn theo latency budget.
4. Chạy load test với kích thước email đại diện.
5. Theo dõi active threads, queue depth, task wait time và SMTP errors.
6. Điều chỉnh từng tham số một.
7. Kiểm tra cả giờ cao điểm và lúc provider chậm.

Ví dụ pool 4 core, 8 max, queue 100 là điểm khởi đầu để thử nghiệm, không phải cấu hình chuẩn cho mọi ứng dụng.

## 12. Tách pool theo loại email và SLA

Một ứng dụng có thể gửi nhiều loại email:

| Loại email | Đặc điểm | Cách ưu tiên |
| --- | --- | --- |
| OTP/reset password | Nhạy cảm thời gian, nội dung ngắn | Pool riêng hoặc quota ưu tiên, queue nhỏ |
| Xác nhận đơn hàng | Quan trọng, cần retry | Outbox và worker có giám sát |
| Hóa đơn/attachment | Có thể lớn, thời gian truyền dài | Concurrency thấp hơn, giới hạn size |
| Newsletter | Số lượng lớn, có rate limit | Campaign queue riêng và batch throttling |
| Báo cáo định kỳ | Có thể tạo nội dung tốn CPU | Tách render/report khỏi mail delivery |

Nếu newsletter tạo hàng nghìn task vào cùng pool với OTP, nó có thể chiếm queue và làm OTP chậm. Tách workload theo SLA hoặc dùng một scheduler/dispatcher có priority rõ ràng.

Không nên tạo quá nhiều pool nhỏ khiến thread bị phân mảnh. Chỉ tách khi có lý do về latency, quota, mức ưu tiên hoặc tài nguyên.

## 13. Giới hạn rate gửi mail bên cạnh thread pool

Thread pool giới hạn số task chạy đồng thời, nhưng không trực tiếp đặt giới hạn số email mỗi giây.

Ví dụ, một pool 5 thread có thể gửi rất nhanh nếu provider phản hồi trong 50 ms; concurrency 5 vẫn có thể tạo ra throughput cao. Nếu provider cho phép 10 email/giây, ứng dụng cần rate limiter hoặc dispatcher điều tiết tốc độ.

Phân biệt:

- **Concurrency limit**: tối đa bao nhiêu email đang được gửi cùng lúc.
- **Rate limit**: tối đa bao nhiêu email được submit trong một đơn vị thời gian.
- **Queue capacity**: tối đa bao nhiêu task đang chờ trong process.
- **Provider quota**: giới hạn do nhà cung cấp áp dụng theo account/domain/API plan.

Có thể dùng rate limiter trong worker trước khi gọi adapter. Với nhiều instance ứng dụng, rate limit cần được phối hợp toàn hệ thống; một limiter cục bộ trên từng JVM có thể khiến tổng throughput vượt quota.

## 14. Tránh giữ transaction database trong mail worker

Worker gửi email nên đọc/claim dữ liệu trong transaction ngắn, sau đó đóng transaction trước khi gọi SMTP.

Không nên:

~~~java
@Transactional
public void processMail(OutboxMessage message) {
    message.markProcessing();
    outboxRepository.save(message);

    mailDeliveryPort.send(buildMail(message));

    message.markSubmitted();
}
~~~

Trong ví dụ này, transaction có thể giữ connection và lock trong suốt thời gian SMTP hoạt động.

Cách tách rõ hơn:

~~~text
Transaction A:
  claim outbox row
  set PROCESSING + lease
  COMMIT

Không có DB transaction:
  build MIME
  gọi JavaMailSender
  chờ SMTP response

Transaction B:
  set SUBMITTED hoặc RETRY_WAIT/FAILED
  COMMIT
~~~

Thread pool chỉ cung cấp thread để chạy worker. Transaction boundary vẫn phải được thiết kế riêng.

Nếu worker dùng @Async, transaction không tự được kế thừa từ thread submit. Nếu cần cập nhật trạng thái, gọi service khác có transaction rõ ràng.

## 15. Kết hợp @TransactionalEventListener và @Async

Với thông báo best-effort, có thể chạy listener sau commit rồi chuyển việc gửi sang executor:

~~~java
@Component
public class OrderMailListener {

    private final AsyncMailService asyncMailService;

    public OrderMailListener(AsyncMailService asyncMailService) {
        this.asyncMailService = asyncMailService;
    }

    @Async("mailTaskExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        OutgoingMail mail = buildMail(event);
        asyncMailService.send(mail);
    }
}
~~~

Tùy thiết kế, có thể chỉ đặt @Async trên listener hoặc chỉ gọi một async dispatcher. Tránh xếp nhiều lớp async không cần thiết vì sẽ làm khó xác định queue, exception và executor thực sự xử lý task.

Một phương án khác là listener AFTER_COMMIT gọi thẳng adapter trong thread của listener; nếu method listener có @Async thì việc gửi đã chạy trong executor đó.

Nhưng cần nhớ:

- Event mặc định ở bộ nhớ và có thể mất khi process crash.
- Executor queue cũng ở bộ nhớ và có thể mất khi process crash.
- Nếu pool đầy, submission có thể bị reject.
- SMTP lỗi cần được quan sát và xử lý.
- AFTER_COMMIT không tự tạo retry bền vững.

Với email quan trọng, nên tạo outbox row trong transaction và dùng worker đọc outbox. Có thể dùng event chỉ để đánh thức worker sớm, nhưng polling/recovery vẫn phải tồn tại.

## 16. Thread pool và transactional outbox

Outbox lưu yêu cầu gửi bền vững; executor chạy các task lấy từ outbox. Hai thành phần giải quyết hai vấn đề khác nhau.

~~~text
Business transaction
      |
      +--> Update order
      +--> Insert mail_outbox
      |
      v
COMMIT
      |
      v
Outbox poller / dispatcher
      |
      v
Claim bounded batch
      |
      v
Mail TaskExecutor
   |       |       |
   v       v       v
 worker  worker  worker
   |       |       |
   +-------+-------+
           |
           v
    MailDeliveryPort
           |
           v
    JavaMailSender
           |
           v
    Update outbox result
~~~

Một thiết kế thực tế:

1. Transaction nghiệp vụ insert outbox row.
2. Poller claim một batch nhỏ, đặt lease và commit.
3. Dispatcher submit các record vào mail executor.
4. Worker render message và gửi qua mail adapter.
5. Worker cập nhật trạng thái trong transaction ngắn.
6. Lỗi tạm thời được lên lịch retry.
7. Record hết lease được reclaim nếu worker chết.

### Đừng claim nhiều task hơn pool có thể xử lý

Nếu poller claim 1.000 record rồi chỉ có 4 worker và queue capacity 100, một phần record có thể nằm ở trạng thái PROCESSING quá lâu trong khi chưa được thực thi. Lease có thể hết hạn trước khi task bắt đầu, dẫn tới worker khác claim lại và tạo cạnh tranh.

Nên giới hạn batch theo khả năng active + queue của executor, hoặc thiết kế lease bắt đầu từ lúc worker thực sự claim/nhận task. Không chuyển record sang PROCESSING quá sớm nếu nó chỉ đang nằm trong queue.

Một cách an toàn hơn là:

- Claim batch vừa với capacity thực thi.
- Chỉ submit khi còn slot/queue phù hợp.
- Nếu submit bị rejection, trả record về trạng thái retry/pending bằng transaction.
- Đặt lease đủ dài cho thời gian queue wait + send, hoặc gia hạn lease.
- Không giữ DB lock trong lúc chờ executor.

## 17. Xử lý rejection khi dùng outbox

Khi executor từ chối task, record outbox vẫn phải được giữ để xử lý lại. Không đánh dấu SUBMITTED hoặc xóa record.

Ví dụ logic dispatcher khái niệm:

~~~java
try {
    mailTaskExecutor.execute(() -> mailWorker.process(outboxId));
} catch (TaskRejectedException exception) {
    outboxResultService.releaseForRetry(
        outboxId,
        "Mail executor is saturated"
    );
}
~~~

Tùy loại executor và API submit, exception có thể là Spring `TaskRejectedException` hoặc rejection exception được wrap. Hãy xử lý theo exception thực tế của implementation và tránh bắt quá rộng rồi coi mọi lỗi là overload.

Nếu record đã được claim và đánh dấu PROCESSING trước khi submit, khi submit thất bại cần cập nhật lại trạng thái/lease để record không bị kẹt. Nếu dùng một transaction claim/dispatch, hãy cân nhắc việc submit task là side effect ngoài transaction; database rollback không thể thu hồi task đã được executor nhận.

Outbox worker cần có chiến lược reconcile các record PROCESSING bị bỏ dở, không phụ thuộc duy nhất vào catch block của dispatcher.

## 18. Truyền context qua thread pool

Thread pool tái sử dụng thread. Thread-local data từ task trước có thể còn tồn tại nếu code không dọn đúng cách. Đồng thời, context của request thread không tự động xuất hiện ở worker thread.

Các context thường gặp:

- MDC logging: correlation ID, trace ID, tenant ID.
- SecurityContext: thông tin xác thực/quyền.
- Locale hoặc thông tin ngôn ngữ.
- Tracing context từ Micrometer/OpenTelemetry.
- Request metadata cần thiết để ghi log.

Không nên truyền toàn bộ HTTP request object hoặc transaction context sang worker. Hãy truyền các giá trị cần thiết trong command/event hoặc dùng cơ chế context propagation được quản lý.

### Dùng TaskDecorator cho MDC

Ví dụ decorator lưu context MDC tại thời điểm submit và khôi phục context sau khi task hoàn thành:

~~~java
public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> submittedContext =
            MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previousContext =
                MDC.getCopyOfContextMap();

            try {
                if (submittedContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(submittedContext);
                }

                task.run();
            } finally {
                if (previousContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previousContext);
                }
            }
        };
    }
}
~~~

Gắn vào executor:

~~~java
executor.setTaskDecorator(new MdcTaskDecorator());
~~~

Cần import các class MDC/TaskDecorator phù hợp với logging framework đang dùng. Nếu dùng Logback, MDC thường đến từ SLF4J API.

Decorator phải khôi phục hoặc xóa context trong finally để không làm rò context giữa các task trên cùng thread. Không giữ context cũ vô thời hạn.

### Security context

Nếu worker cần quyền hoặc danh tính để truy cập storage, không nên mặc định truyền toàn bộ security context. Có thể truyền user ID/tenant ID cần thiết và kiểm tra quyền ở worker. Nếu cần Spring Security context propagation, dùng executor wrapper phù hợp như `DelegatingSecurityContextAsyncTaskExecutor` và xác định rõ lifecycle của authentication.

Transaction context không nên được truyền sang worker; worker cần transaction mới cho thao tác database riêng.

## 19. Graceful shutdown và vòng đời executor

Khi ứng dụng shutdown, Spring container sẽ destroy các bean executor. Nếu không cấu hình rõ, task đang chờ hoặc đang chạy có thể không hoàn thành theo mong muốn.

Các thuộc tính thường dùng:

- `setWaitForTasksToCompleteOnShutdown(true)`: yêu cầu executor chờ task đã nhận hoàn tất trong quá trình shutdown.
- `setAwaitTerminationSeconds(...)`: thời gian tối đa chờ termination.
- `setThreadNamePrefix(...)`: giúp nhận diện thread trong log và thread dump.

Ví dụ:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(30);
executor.setThreadNamePrefix("mail-");
~~~

Graceful shutdown vẫn có giới hạn:

- Container/orchestrator có thể gửi SIGKILL sau grace period.
- Task SMTP có thể treo tới timeout.
- Queue lớn có thể không xử lý xong trước deadline shutdown.
- Process crash hoặc mất máy không chạy được shutdown hook.
- Task trong in-memory queue không được phục hồi sau restart.

Với outbox, task chưa hoàn tất vẫn có thể được worker khác xử lý sau khi lease hết hạn hoặc ứng dụng khởi động lại. Vì vậy, graceful shutdown bổ trợ cho outbox chứ không thay thế durability.

### Timeout cần thống nhất

SMTP connection/read/write timeout nên nằm trong ngân sách thời gian xử lý worker và shutdown. Nếu timeout SMTP dài hơn nhiều so với termination grace period, ứng dụng có thể bị dừng khi worker còn đang gửi.

Cần thiết kế thời gian:

~~~text
SMTP connect timeout
+ SMTP read/write timeout
+ trạng thái cập nhật
< worker lease / shutdown budget (có margin)
~~~

Đây là quan hệ lập kế hoạch, không phải công thức bắt buộc. Thời gian thực tế cần đo và cân nhắc provider behavior.

## 20. Quan sát thread pool

Một thread pool production cần có metrics và cảnh báo. Chỉ nhìn log exception là chưa đủ, vì backlog có thể tăng lâu trước khi xuất hiện lỗi.

Các số liệu quan trọng:

| Metric | Ý nghĩa |
| --- | --- |
| Pool size | Số worker hiện có |
| Active count | Số worker đang chạy task |
| Core/max size | Giới hạn cấu hình |
| Queue size | Số task đang chờ |
| Queue remaining capacity | Số slot queue còn lại |
| Completed task count | Số task đã hoàn tất |
| Rejected task count | Số task bị từ chối |
| Task execution duration | Thời gian thực thi |
| Queue wait duration | Thời gian từ submit tới lúc bắt đầu |
| SMTP failure/timeout rate | Chất lượng vận chuyển |
| Outbox oldest age | Tuổi record chưa được xử lý lâu nhất |

Có thể lấy một số thông tin trực tiếp từ `ThreadPoolTaskExecutor` sau khi khởi tạo:

~~~java
int active = executor.getActiveCount();
int poolSize = executor.getPoolSize();
int queueSize = executor.getThreadPoolExecutor()
    .getQueue()
    .size();
long completed = executor.getThreadPoolExecutor()
    .getCompletedTaskCount();
~~~

Không gọi các accessor trước khi executor được khởi tạo. Các con số là snapshot và có thể thay đổi ngay sau khi đọc; dùng metrics để theo dõi xu hướng thay vì coi một lần đọc là trạng thái tuyệt đối.

### Metrics và alert

Có thể tạo cảnh báo khi:

- Queue liên tục gần đầy.
- Active count thường xuyên bằng max size.
- Rejection tăng.
- Queue wait vượt SLA email.
- SMTP timeout/error rate tăng.
- Outbox pending age tăng.
- Số record PROCESSING hết lease tăng.

Spring Boot Actuator/Micrometer có thể hỗ trợ expose metrics cho executor tùy phiên bản và cách đăng ký. Nếu tự instrument, đặt tag giới hạn như executor name, provider hoặc mail category; tránh tag recipient/email ID gây cardinality cao và lộ dữ liệu cá nhân.

## 21. Cấu hình pool qua Spring Boot properties

Với ứng dụng Spring Boot, có thể cấu hình executor mặc định bằng các thuộc tính task execution của phiên bản đang dùng. Tuy nhiên, nếu mail cần pool riêng, một bean có tên rõ ràng thường dễ kiểm soát hơn.

Ví dụ cấu hình riêng bằng @ConfigurationProperties:

~~~yaml
app:
  mail:
    executor:
      core-pool-size: 4
      max-pool-size: 8
      queue-capacity: 100
      keep-alive-seconds: 60
      await-termination-seconds: 30
~~~

Properties class:

~~~java
@ConfigurationProperties(prefix = "app.mail.executor")
public record MailExecutorProperties(
    int corePoolSize,
    int maxPoolSize,
    int queueCapacity,
    int keepAliveSeconds,
    int awaitTerminationSeconds
) {}
~~~

Executor bean:

~~~java
@Bean(name = "mailTaskExecutor")
public ThreadPoolTaskExecutor mailTaskExecutor(
        MailExecutorProperties properties) {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(properties.corePoolSize());
    executor.setMaxPoolSize(properties.maxPoolSize());
    executor.setQueueCapacity(properties.queueCapacity());
    executor.setKeepAliveSeconds(properties.keepAliveSeconds());
    executor.setThreadNamePrefix("mail-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(
        properties.awaitTerminationSeconds()
    );

    executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy()
    );

    return executor;
}
~~~

Cần đăng ký properties bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Có thể thêm validation để bảo đảm core size dương, max không nhỏ hơn core, queue capacity không âm và timeout hợp lý.

Ví dụ trên cấu hình một pool riêng, không phụ thuộc các giá trị mặc định của auto-configured application executor.

## 22. Kiểm thử async mail service

Unit test không nên phải chờ SMTP thật. Có thể mock mail adapter hoặc dùng fake implementation, sau đó kiểm tra method được gọi.

Ví dụ service phụ thuộc port:

~~~java
@Service
public class AsyncMailDispatcher {

    private final MailDeliveryPort mailDeliveryPort;

    public AsyncMailDispatcher(MailDeliveryPort mailDeliveryPort) {
        this.mailDeliveryPort = mailDeliveryPort;
    }

    @Async("mailTaskExecutor")
    public CompletableFuture<Void> send(OutgoingMail mail) {
        mailDeliveryPort.send(mail);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Integration test với Spring context có thể gọi method và đợi future:

~~~java
@Test
void sendsMailOnConfiguredExecutor() throws Exception {
    OutgoingMail mail = new OutgoingMail(
        "customer@example.com",
        "Order confirmed",
        "Your order is confirmed.",
        "<p>Your order is confirmed.</p>"
    );

    CompletableFuture<Void> future = dispatcher.send(mail);

    future.get(5, TimeUnit.SECONDS);

    verify(mailDeliveryPort).send(mail);
}
~~~

Test này xác nhận method hoàn tất và port được gọi. Nó chưa chứng minh SMTP provider nhận thư.

### Test executor rejection

Có thể cấu hình pool rất nhỏ và queue capacity thấp trong test để mô phỏng quá tải. Kiểm tra rằng rejection được quan sát và outbox record không bị đánh dấu thành công.

Không dùng sleep cố định để đo timing nếu có thể đồng bộ bằng latch/future. Test concurrency nên kiểm tra hành vi có ý nghĩa như số task chạy đồng thời tối đa, không chỉ kiểm tra tên thread.

### Test lỗi trong CompletableFuture

Nếu mail adapter ném exception, future cần hoàn tất exceptional:

~~~java
CompletableFuture<Void> future = dispatcher.send(mail);

assertThrows(
    ExecutionException.class,
    () -> future.get(5, TimeUnit.SECONDS)
);
~~~

Cần cấu hình fake/mock để ném exception trước assertion. Với method trả về void, kiểm tra thông qua AsyncUncaughtExceptionHandler hoặc error recorder.

## 23. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tạo thread mới cho từng email | Thread tăng không giới hạn khi burst | Dùng bounded ThreadPoolTaskExecutor |
| Queue không giới hạn | Backlog và memory tăng mãi, độ trễ khó kiểm soát | Dùng queue hữu hạn |
| Chỉ tăng maxPoolSize nhưng queue rất lớn | Pool không mở rộng như kỳ vọng | Hiểu thứ tự queue/core/max |
| Dùng chung pool cho mail và CPU-heavy task | Một workload làm nghẽn workload khác | Tách pool theo SLA/tài nguyên |
| Dùng common pool cho SMTP blocking | Chiếm worker dùng chung | Dùng executor riêng |
| Dùng @Async nhưng tự gọi method trong cùng class | Proxy không được đi qua, task vẫn đồng bộ | Tách bean và gọi qua Spring proxy |
| Tự new service có @Async | Annotation không được Spring proxy quản lý | Inject bean từ container |
| Trông chờ exception async void quay về caller | Lỗi bị bỏ sót | AsyncUncaughtExceptionHandler hoặc CompletableFuture |
| Gọi future.get() ngay sau submit | Caller vẫn chờ task | Xử lý callback hoặc trả response phù hợp |
| Nghĩ @Async truyền transaction sang worker | Worker chạy ngoài transaction caller | Thiết kế transaction riêng |
| Dùng CallerRuns mà không hiểu caller | HTTP request có thể gửi mail đồng bộ | Chọn rejection theo nguồn submit |
| Dùng DiscardPolicy | Email biến mất không báo lỗi | Abort/retry qua outbox |
| Claim nhiều outbox row hơn pool capacity | Record PROCESSING nằm chờ, lease hết hạn | Batch theo capacity và quản lý lease |
| Gửi SMTP trong DB transaction | Giữ connection/lock khi chờ network | Claim/commit, gửi ngoài transaction |
| Nghĩ executor queue là durable | Process crash làm mất task | Outbox hoặc broker |
| Không có graceful shutdown | Task đang chạy có thể bị dừng khi deploy | Cấu hình termination và timeout |
| Không theo dõi queue depth/rejection | Chỉ phát hiện sự cố khi người dùng báo | Metrics, logs và alerts |

## 24. Quy trình triển khai TaskExecutor cho mail

Một lộ trình có thể áp dụng:

1. **Đo workload hiện tại**: số email/giây, SMTP latency, kích thước message và provider quota.
2. **Tách mail dispatcher** khỏi controller/use case để có một điểm thực thi rõ ràng.
3. **Đăng ký ThreadPoolTaskExecutor riêng** với core/max/queue hữu hạn và thread prefix.
4. **Dùng @Async("mailTaskExecutor")** hoặc gọi TaskExecutor trực tiếp; không trộn hai cách không cần thiết.
5. **Chọn rejection policy** dựa trên nguồn submit và khả năng lưu/retry task.
6. **Thiết lập timeout SMTP** và shutdown budget phù hợp.
7. **Giới hạn rate/concurrency** theo provider, không chỉ theo số CPU.
8. **Truyền correlation context có kiểm soát** và không truyền transaction thread-local.
9. **Instrument pool**: active, queue, rejected, wait time, execution duration và SMTP errors.
10. **Với email quan trọng, dùng outbox** để lưu yêu cầu bền vững; executor chỉ chạy worker lấy task từ outbox.
11. **Kiểm thử saturation, rejection, exception, shutdown và process restart** trong môi trường phù hợp.

Sơ đồ kiến trúc:

~~~text
Business transaction
       |
       v
Insert mail_outbox
       |
       v
COMMIT
       |
       v
Outbox dispatcher
       |
       v
Bounded TaskExecutor
   |       |       |
   v       v       v
mail-1  mail-2  mail-3
   |       |       |
   +-------+-------+
           |
           v
    MailDeliveryPort
           |
           v
     JavaMailSender
           |
           v
      SMTP provider
           |
           v
Update outbox result
~~~

## 25. Ghi nhớ

`TaskExecutor` và thread pool giúp kiểm soát cách ứng dụng thực thi tác vụ gửi mail bất đồng bộ:

- `TaskExecutor` là abstraction Spring cho việc thực thi task.
- `ThreadPoolTaskExecutor` phù hợp khi cần giới hạn thread và queue.
- Core size, max size và queue capacity phối hợp với nhau; queue lớn có thể khiến max size ít được dùng.
- Queue hữu hạn giúp tạo giới hạn backlog và làm lộ tình trạng quá tải.
- Rejection policy phải được chọn theo nghiệp vụ; tránh drop task mail im lặng.
- Dùng `@Async("mailTaskExecutor")` để chọn pool rõ ràng.
- `@Async` hoạt động qua Spring proxy; self-invocation và object tự tạo không đi qua proxy mặc định.
- Dùng `CompletableFuture` khi caller cần quan sát kết quả; với method void cần handler cho exception.
- Transaction context không tự truyền sang thread khác.
- Chọn pool size theo SMTP latency, provider quota, message size và throughput thực tế, không chỉ dựa vào CPU cores.
- Thread pool giới hạn concurrency; rate limiter mới điều tiết số email mỗi giây.
- Cấu hình graceful shutdown và timeout để task có cơ hội hoàn thành khi deploy.
- Dùng TaskDecorator hoặc cơ chế context propagation cho MDC/tracing/security khi cần; không để ThreadLocal rò giữa task.
- Executor queue nằm trong memory, không phải durable queue.
- Với email giao dịch quan trọng, lưu yêu cầu bằng transactional outbox; worker dùng thread pool để xử lý và retry.
- Theo dõi active threads, queue depth, rejection, wait time, SMTP errors và tuổi outbox.

Thread pool là cơ chế điều phối tài nguyên thực thi. Nó giúp mail workload chạy có giới hạn và không chiếm thread xử lý request, nhưng độ tin cậy của thông báo vẫn phụ thuộc vào cách lưu yêu cầu, transaction boundary, retry và khả năng phục hồi sau sự cố. Khi kết hợp bounded `ThreadPoolTaskExecutor` với outbox worker, ứng dụng vừa kiểm soát concurrency SMTP vừa giữ được những email cần xử lý sau khi process restart.
