# Xử lý exception trong tác vụ bất đồng bộ

## 1. Vì sao exception trong tác vụ gửi mail bất đồng bộ khó xử lý hơn?

Trong ứng dụng **Spring Framework Mail**, gửi email qua SMTP là thao tác I/O có thể mất thời gian vì phải mở kết nối, xác thực, trao đổi dữ liệu và chờ phản hồi từ mail server. Thay vì buộc HTTP request hoặc luồng nghiệp vụ đợi thao tác gửi hoàn tất, ứng dụng thường dùng `@Async`, `CompletableFuture`, executor hoặc hàng đợi để xử lý email ngoài luồng gọi chính.

Nhưng **bất đồng bộ không làm exception biến mất**; nó chỉ chuyển nơi và thời điểm exception xuất hiện:

~~~text
HTTP request / business thread
           |
           | submit task
           v
      Async executor
           |
           v
   Prepare MIME message
           |
           v
   JavaMailSender.send(...)
           |
       +---+---+
       |       |
       v       v
    Success  Exception
       |       |
       v       v
   completion  CompletableFuture/handler/
               retry state/monitoring
~~~

Ví dụ, controller đã trả HTTP `202 Accepted` nhưng vài giây sau SMTP từ chối địa chỉ người nhận. Exception xuất hiện trên thread của executor, **không thể tự động quay về một HTTP response đã gửi**. Nếu không có cơ chế nhận và lưu kết quả xử lý, ứng dụng có thể báo “đã gửi” dù email thực tế chưa được SMTP chấp nhận.

Một hệ thống gửi mail bất đồng bộ cần trả lời được:

1. Exception được chuyển tới đâu: caller, `Future`, `CompletableFuture` hay handler?
2. Lỗi phát sinh khi **submit task**, khi **dựng MIME** hay khi **gửi SMTP**?
3. Lỗi có thể retry hay cần dừng?
4. Ai lưu lại trạng thái để lần xử lý sau không bị mất?
5. Nếu kết quả SMTP không rõ ràng, retry có nguy cơ gửi trùng hay không?

> **Nguyên tắc:** Đừng coi “đã nhận việc gửi email” là “email đã gửi thành công”. Tách rõ `QUEUED/SUBMITTED`, `SMTP_ACCEPTED`, `RETRY` và `FAILED` theo mô hình vận hành của ứng dụng.

## 2. Hai ranh giới exception trong @Async

Một lời gọi `@Async` có hai ranh giới lỗi khác nhau:

**Ranh giới 1 — submit task ở caller thread:** Executor có thể từ chối ngay khi hàng đợi đầy hoặc đang shutdown. Ví dụ Spring `TaskRejectedException` có thể được ném tại thời điểm gọi proxy. Khi đó tác vụ **chưa được xếp hàng**.

**Ranh giới 2 — chạy task ở worker thread:** Exception có thể phát sinh khi render template, dựng `MimeMessage`, kết nối SMTP hoặc gửi thư. Exception này xảy ra **sau** khi method bất đồng bộ đã được submit, và phải được quan sát bằng kênh kết quả riêng.

| Thời điểm | Ví dụ | Nơi xử lý |
| --- | --- | --- |
| Trước khi executor nhận task | `TaskRejectedException` | Caller tại lệnh gọi async |
| Trong khi tạo nội dung | Template không tồn tại, thiếu dữ liệu, `MessagingException` | Worker; chuyển thành failed future hoặc trạng thái lỗi |
| Trong khi gửi | `MailAuthenticationException`, `MailSendException`, lỗi mạng | Worker; phân loại, lưu retry/failure |
| Sau khi gửi thành công | Database không ghi được `SENT` | Thành phần cập nhật trạng thái; cảnh báo vì SMTP có thể đã chấp nhận thư |
| Khi đọc kết quả | `ExecutionException` hoặc `CompletionException` | Caller/consumer chờ Future |

Điều này giải thích vì sao một khối `try/catch` chỉ đặt quanh lời gọi `asyncService.send(...)` **không thể bắt mọi lỗi phát sinh trong executor thread**.

## 3. Cách Spring @Async vận hành

Spring cho phép đánh dấu method bằng `@Async` và bật cơ chế bất đồng bộ với `@EnableAsync`. Một cấu hình cơ bản:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfig {

    @Bean(name = "mailExecutor")
    public TaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mail-worker-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Sau đó một service có thể chọn executor theo tên:

~~~java
@Async("mailExecutor")
public CompletableFuture<MailSubmission> submit(MailCommand command) {
    // Code chạy trên executor thread khi được gọi qua Spring proxy.
}
~~~

Các giá trị 4/8 thread và queue capacity 200 chỉ là ví dụ. Kích thước pool phải phụ thuộc SMTP timeout, giới hạn kết nối/provider và tải gửi mail thực tế. Executor có queue giới hạn giúp bộc lộ quá tải thay vì tích lũy vô hạn.

### 3.1. @Async chạy qua Spring proxy

Ở chế độ proxy thông dụng, lời gọi phải đi qua bean do Spring quản lý:

~~~java
@Service
public class OrderService {
    private final AsyncMailService asyncMailService;

    public OrderService(AsyncMailService asyncMailService) {
        this.asyncMailService = asyncMailService;
    }

    public void onOrderConfirmed(MailCommand command) {
        asyncMailService.submit(command);
    }
}
~~~

Nếu một method trong cùng class gọi method `@Async` bằng `this.submit(...)`, lời gọi nội bộ có thể **bỏ qua proxy** và chạy đồng bộ. Tương tự, tự tạo object với `new AsyncMailService(...)` không kích hoạt `@Async`. Vì vậy, nên tách service điều phối và service chạy async thành các Spring bean riêng.

### 3.2. @Async không tự tạo giao dịch hay chuyển thread context

Thread của executor là một execution context khác. Transaction JDBC/JPA gắn với thread gọi ban đầu không tự động đi theo worker; các dữ liệu dựa trên `ThreadLocal` như MDC, security context, locale context cũng không được mặc định mang theo theo mọi cấu hình.

Nếu cần dữ liệu nghiệp vụ, hãy truyền **DTO/snapshot rõ ràng**; nếu cần transaction database trong worker, mở transaction riêng. Không truyền entity JPA lazy chưa tải vào method async rồi giả định persistence context của request vẫn còn.

## 4. Ba kiểu trả về và cách nhận exception

Spring `@Async` thường được dùng với method trả `void`, `Future<T>` hoặc `CompletableFuture<T>`. Kênh lỗi khác nhau:

| Kiểu trả về | Kết quả khi worker ném exception | Cách nhận lỗi |
| --- | --- | --- |
| `void` | Không có đối tượng kết quả để caller theo dõi | `AsyncUncaughtExceptionHandler` cho exception không được bắt, và/hoặc xử lý ngay trong worker |
| `Future<T>` | Future hoàn tất với lỗi | `future.get()` ném `ExecutionException`, cause là lỗi gốc |
| `CompletableFuture<T>` | Future hoàn tất exceptionally | `whenComplete`, `handle`, `exceptionally`, `join` hoặc `get` |

Với gửi email cần ghi nhận kết quả, **`CompletableFuture<T>` thường dễ điều phối hơn `void`**. Nhưng Future trong memory không thay thế một outbox/queue bền vững nếu ứng dụng phải bảo đảm phục hồi sau restart.

### 4.1. Vì sao @Async void dễ làm mất tín hiệu lỗi?

Ví dụ:

~~~java
@Async("mailExecutor")
public void sendLater(MimeMessage message) {
    mailSender.send(message);
}
~~~

Caller không có `Future` để quan sát. Exception chưa bắt từ method `void` sẽ được chuyển cho `AsyncUncaughtExceptionHandler` của Spring. Nếu handler chỉ log, không có cơ chế khác lưu kết quả, ứng dụng không biết bản gửi nào cần retry.

Trường hợp này phù hợp hơn với việc phụ trợ không quan trọng hoặc khi **worker tự quản lý trạng thái bền vững**. Với email giao dịch, không nên chỉ dựa vào log của handler.

### 4.2. Exception trong Future không tự động xuất hiện ở caller

~~~java
CompletableFuture<MailSubmission> future =
        asyncMailService.submit(command);

// future có thể đang chạy. Lời gọi trên thường đã trả về.
~~~

Nếu worker ném exception sau đó, exception được biểu diễn thành **future hoàn tất lỗi**. Chỉ có `try/catch` quanh dòng gọi `submit(...)` không đủ để nhận lỗi ấy; phải quan sát Future.

## 5. Ví dụ hoàn chỉnh: gửi HTML và plain text với CompletableFuture

Định nghĩa command và kết quả:

~~~java
package com.example.mail;

import java.time.Instant;
import java.util.UUID;

public record MailCommand(
        UUID deliveryId,
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}

public record MailSubmission(
        UUID deliveryId,
        Instant smtpAcceptedAt) {
}
~~~

`deliveryId` là khóa correlation của một lần gửi, không nên dùng email người nhận hoặc token nhạy cảm làm correlation ID. Command đã được tầng ứng dụng chuẩn bị/validate trước khi submit.

Service gửi qua Spring Mail:

~~~java
package com.example.mail;

import java.time.Instant;
import java.util.concurrent.CompletableFuture;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncMailService {

    private final JavaMailSender mailSender;

    public AsyncMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public CompletableFuture<MailSubmission> submit(MailCommand command) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom("notifications@example.com");
            helper.setTo(command.recipient());
            helper.setSubject(command.subject());
            helper.setText(command.plainText(), command.htmlText());

            // Đây là lời gọi I/O đồng bộ, nhưng chạy trên mailExecutor.
            mailSender.send(message);

            return CompletableFuture.completedFuture(
                    new MailSubmission(
                            command.deliveryId(), Instant.now()));
        } catch (MessagingException ex) {
            // Lỗi tạo MIME là checked exception; chuyển thành
            // exception nghiệp vụ để Future hoàn tất lỗi.
            throw new MailContentBuildException(
                    command.deliveryId(), ex);
        }
        // MailException (runtime) từ JavaMailSender được truyền ra,
        // nên proxy @Async có thể complete Future exceptionally.
    }
}
~~~

Exception ứng dụng:

~~~java
package com.example.mail;

import java.util.UUID;

public class MailContentBuildException extends RuntimeException {
    private final UUID deliveryId;

    public MailContentBuildException(UUID deliveryId, Throwable cause) {
        super("Cannot prepare MIME message", cause);
        this.deliveryId = deliveryId;
    }

    public UUID deliveryId() {
        return deliveryId;
    }
}
~~~

Điểm cần hiểu:

1. `@Async("mailExecutor")` chuyển thực thi method sang thread pool nếu được gọi qua Spring proxy.
2. `JavaMailSender.createMimeMessage()` và `MimeMessageHelper` dựng thông điệp MIME.
3. `setText(plainText, htmlText)` tạo bản thay thế text/HTML.
4. `mailSender.send(message)` vẫn là I/O blocking, nhưng không giữ request thread.
5. Chỉ sau khi `send` hoàn tất bình thường, service tạo kết quả `MailSubmission`.
6. Nếu `MessagingException` xảy ra khi tạo message, worker ném `MailContentBuildException`; nếu transport ném `MailException`, lỗi cũng khiến Future hoàn tất lỗi.

**Quan trọng:** Kết quả thành công ở đây nghĩa là phương thức gửi qua transport hoàn thành, không có nghĩa thư đã vào inbox. SMTP server có thể chấp nhận message rồi sau đó thư vẫn bounce, bị spam filter hoặc không được người nhận mở.

### 5.1. Tại sao method @Async trả về completedFuture?

Trong method đã được `@Async` đánh dấu, code thực sự chạy trên worker thread. Implementation có thể trả về một `CompletableFuture.completedFuture(result)` như giá trị nội bộ; **Spring proxy** trả cho caller một Future biểu diễn việc thực thi bất đồng bộ.

Không cần tự gọi `CompletableFuture.supplyAsync(...)` bên trong method `@Async`. Nếu làm vậy mà không chỉ định executor, tác vụ bổ sung có thể chạy trên `ForkJoinPool.commonPool`, làm phân tán việc quản lý thread và exception.

## 6. Caller quan sát kết quả và exception

Caller nên đăng ký callback hoặc tích hợp Future vào một luồng điều phối có trạng thái:

~~~java
try {
    CompletableFuture<MailSubmission> future =
            asyncMailService.submit(command);

    CompletableFuture<Void> observed = future.whenComplete(
            (submission, failure) -> {
                if (failure == null) {
                    logger.info(
                            "Mail submitted to SMTP deliveryId={}",
                            submission.deliveryId());
                } else {
                    Throwable root = unwrapCompletionException(failure);
                    logger.warn(
                            "Async mail failed deliveryId={} errorType={}",
                            command.deliveryId(),
                            root.getClass().getSimpleName());
                }
            }).thenApply(ignored -> null);

    // Nếu cần phối hợp nhiều công việc, giữ và quan sát observed.
} catch (org.springframework.core.task.TaskRejectedException rejected) {
    // Executor chưa nhận task, cần lưu trạng thái/đưa vào queue.
    logger.warn(
            "Mail executor rejected deliveryId={}",
            command.deliveryId());
}
~~~

Hàm mở wrapper:

~~~java
static Throwable unwrapCompletionException(Throwable failure) {
    Throwable cause = failure;
    while ((cause instanceof java.util.concurrent.CompletionException
            || cause instanceof java.util.concurrent.ExecutionException)
            && cause.getCause() != null) {
        cause = cause.getCause();
    }
    return cause;
}
~~~

Trong thực tế có thể bỏ biến `observed` nếu chỉ cần logging, nhưng khi cập nhật trạng thái database trong callback, phải **quan sát cả kết quả cập nhật**. Nếu callback ném exception rồi dependent Future bị bỏ mặc, lỗi state update có thể không được xử lý. Một dispatcher có outbox bền vững đáng tin cậy hơn callback thuần trong request.

### 6.1. Phân biệt whenComplete, exceptionally và handle

| Phương thức | Vai trò | Điều cần lưu ý |
| --- | --- | --- |
| `whenComplete((result, error) -> ...)` | Quan sát thành công/thất bại mà thường giữ kết quả gốc | Nếu callback ném lỗi, dependent Future có thể thất bại |
| `exceptionally(error -> fallback)` | Phục hồi bằng một giá trị thay thế khi thất bại | Dễ vô tình che giấu lỗi nếu trả “thành công giả” |
| `handle((result, error) -> value)` | Biến đổi kết quả của cả hai nhánh | Có thể dùng cho kết quả tổng hợp có kiểu |
| `thenCompose(...)` | Xâu chuỗi một tác vụ async khác | Failure được truyền xuống nếu không phục hồi |
| `allOf(...)` | Chờ nhóm Future | Cần xử lý kết quả từng message, không chỉ trạng thái tổng |

**Đừng dùng `exceptionally(ex -> null)` chỉ để làm biến mất exception**. Với email giao dịch, cần lưu thất bại vào hệ thống theo dõi hoặc outbox để quyết định retry.

### 6.2. get() và join() khác gì?

~~~java
try {
    MailSubmission submission = future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted while waiting", ex);
} catch (ExecutionException ex) {
    Throwable root = ex.getCause();
    // Xử lý lỗi gốc.
}
~~~

`Future.get()` chờ tác vụ hoàn tất và có thể ném `InterruptedException` / `ExecutionException`. `CompletableFuture.join()` cũng chờ nhưng bọc lỗi bằng `CompletionException` không checked. Cả hai đều **block caller thread**. Nếu HTTP request gọi `get()` ngay sau khi submit, lợi ích giảm thời gian phản hồi của async có thể mất đi.

Nên dùng callback, event hoặc outbox worker khi không cần chờ; chỉ chờ Future ở những ranh giới thật sự cần kết quả.

## 7. AsyncUncaughtExceptionHandler cho @Async void

Khi method `@Async` trả về `void` và ném exception chưa được xử lý, Spring có thể chuyển lỗi tới `AsyncUncaughtExceptionHandler`. Ta có thể tùy chỉnh handler qua `AsyncConfigurer`.

~~~java
import java.lang.reflect.Method;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.stereotype.Component;

@Component
public class MailAsyncExceptionHandler
        implements AsyncUncaughtExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(MailAsyncExceptionHandler.class);

    @Override
    public void handleUncaughtException(
            Throwable ex,
            Method method,
            Object... params) {

        log.error(
                "Unhandled async exception method={} type={}",
                method.getName(),
                ex.getClass().getSimpleName());
        // Có thể tăng counter/alert; không log toàn bộ params
        // vì chúng có thể chứa email, token hoặc dữ liệu cá nhân.
    }
}
~~~

Đăng ký handler:

~~~java
import java.util.concurrent.Executor;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncHandlerConfig implements AsyncConfigurer {

    private final MailAsyncExceptionHandler handler;

    public AsyncHandlerConfig(MailAsyncExceptionHandler handler) {
        this.handler = handler;
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return handler;
    }
}
~~~

Đây là ví dụ cấu hình handler tách khỏi cấu hình executor ở trên. Trong một ứng dụng thực tế, chỉ cần tổ chức `@EnableAsync` và các bean cấu hình phù hợp, tránh tạo những cấu hình trùng lặp không cần thiết.

**Giới hạn quan trọng:** Handler này chủ yếu xử lý exception chưa bắt của method `@Async void`. Nếu method trả `Future` hoặc `CompletableFuture`, lỗi thường được giữ trong đối tượng kết quả; cần quan sát Future chứ không chờ handler nhận mọi lỗi.

Ngoài ra, `AsyncUncaughtExceptionHandler` không tự tạo retry, không cập nhật outbox và không bảo đảm exception đã được lưu bền vững. Handler phù hợp cho logging/alerting hoặc dispatch tới một cơ chế quản lý lỗi có kiểm soát.

## 8. Exception khi executor từ chối task

Nếu thread pool bận và hàng đợi đạt giới hạn, executor có thể từ chối công việc. Với `ThreadPoolTaskExecutor`, caller thường nhận `TaskRejectedException` tại lúc gọi method `@Async`:

~~~java
try {
    asyncMailService.submit(command);
} catch (TaskRejectedException ex) {
    // Chưa có bằng chứng task đã được executor nhận.
    // Cập nhật PENDING/RETRY hoặc trả lỗi phù hợp.
    handleSubmissionFailure(command.deliveryId(), ex);
}
~~~

Không nên nhầm với `MailSendException`: khi task bị reject, `JavaMailSender.send` **chưa chạy**. Đây là vấn đề capacity/backpressure của ứng dụng.

### 8.1. Những chiến lược khi quá tải

- **Outbox/queue bền vững:** giữ event ở trạng thái chờ, worker lấy khi còn capacity. Đây thường là cách tốt cho email nghiệp vụ.
- **Reject có kiểm soát:** trả lỗi hệ thống tạm quá tải hoặc lịch retry rõ ràng nếu có thể phản hồi caller.
- **Giới hạn tốc độ sản sinh job:** giảm batch, giới hạn số công việc được submit đồng thời.
- **Tăng capacity có đo lường:** điều chỉnh pool/queue theo độ trễ SMTP và quota provider.

Không nên dùng một hàng đợi vô hạn chỉ để tránh exception. Nếu SMTP chậm kéo dài, memory và độ trễ có thể tăng không kiểm soát. Chính sách như `CallerRunsPolicy` có thể khiến tác vụ chạy ngay trên caller thread, làm request bị block và thay đổi giả định về async; chỉ dùng khi đó là backpressure có chủ đích.

### 8.2. Lỗi khi submit không thay thế lỗi khi chạy

Với Future, vẫn phải xử lý **cả hai**:

~~~text
asyncService.submit(...)
        |
        +--> TaskRejectedException (caller)
        |
        +--> accepted by executor
                   |
                   +--> successful completion
                   |
                   +--> exceptional completion (worker)
~~~

Chỉ catch `TaskRejectedException` không giúp quan sát SMTP failure; chỉ đăng ký `whenComplete` không đủ nếu submit bị từ chối trước khi trả Future.

## 9. Nhận diện các nhóm exception khi gửi email

Một tác vụ email có nhiều công đoạn; vì vậy cần phân biệt nơi lỗi xảy ra trước khi quyết định retry:

| Công đoạn | Exception/vấn đề có thể gặp | Nhận định ban đầu |
| --- | --- | --- |
| Tạo model và render template | Thiếu dữ liệu bắt buộc, template không tìm thấy, dữ liệu không hợp lệ | Thường cần sửa dữ liệu hoặc code, retry nguyên trạng hiếm khi có ích |
| Tạo MIME bằng Jakarta Mail | `MessagingException`, địa chỉ không hợp lệ hoặc cấu trúc MIME lỗi | Cần xem nguyên nhân; thường thuộc khâu chuẩn bị |
| Xác thực SMTP | `MailAuthenticationException` | Thường là credential/cấu hình hoặc chính sách nhà cung cấp |
| Gửi qua SMTP | `MailSendException`, lỗi kết nối hoặc phản hồi SMTP | Có thể tạm thời, vĩnh viễn hoặc kết quả chưa chắc chắn |
| Xử lý Spring mail chung | `MailException` | Chỉ là lớp cơ sở; chưa đủ để phân loại |
| Executor | `TaskRejectedException` | Task chưa được nhận, vấn đề capacity |
| Cập nhật trạng thái kết quả | Lỗi database, optimistic lock conflict | Không có nghĩa gửi SMTP đã thất bại |

### 9.1. Checked MessagingException và runtime MailException

`jakarta.mail.MessagingException` là checked exception thường gặp trong quá trình dựng MIME message hoặc gọi trực tiếp Jakarta Mail API. `MimeMessageHelper` có nhiều method khai báo checked exception này.

Ngược lại, API `JavaMailSender.send(...)` của Spring sử dụng hệ thống exception runtime `org.springframework.mail.MailException`. Các loại thường gặp:

- `MailAuthenticationException`: lỗi xác thực mail server.
- `MailSendException`: lỗi gửi một hoặc nhiều message; có thể chứa thông tin chi tiết theo message.
- `MailPreparationException`: lỗi chuẩn bị nội dung/message trong một quy trình tạo message.
- `MailParseException`: lỗi parse mail, ví dụ địa chỉ/cú pháp không hợp lệ trong ngữ cảnh tương ứng.

Không nên viết `catch (Exception ex) { return completedFuture(success); }` để giữ ứng dụng “chạy tiếp”. Một email không gửi được phải được phản ánh bằng trạng thái thất bại rõ ràng.

### 9.2. Lỗi SMTP 4xx, 5xx và kết quả không rõ ràng

Phản hồi SMTP ở nhóm 4xx thường mang ý nghĩa lỗi tạm thời; nhóm 5xx thường biểu thị yêu cầu bị từ chối lâu dài. Nhưng phân loại ở mức ứng dụng còn phụ thuộc lệnh SMTP nào gây lỗi, chính sách provider và thông tin lỗi chi tiết.

Ví dụ:

- Kết nối không mở được vì nhà cung cấp đang ngừng dịch vụ: có thể thử lại.
- Hàng đợi hoặc hạn mức gửi tạm thời bị giới hạn: cần chờ theo chỉ dẫn provider.
- Recipient không tồn tại hoặc sender không được phép: retry cùng dữ liệu thường không giúp gì.
- Không xác thực được SMTP: cần sửa credential/cấu hình; không retry dồn dập.
- Connection timeout **sau khi gửi DATA**, trước khi nhận phản hồi cuối: không biết chắc server đã chấp nhận message hay chưa.

Điểm cuối đặc biệt quan trọng: exception **không luôn chứng minh rằng email chưa được gửi**. Worker nên lưu kết quả ở nhóm `UNKNOWN` hoặc dùng policy thận trọng với rủi ro duplicate khi cần retry.

### 9.3. Phân loại dựa trên cause thay vì một class duy nhất

Ví dụ abstraction:

~~~java
public enum FailureKind {
    RETRYABLE,
    PERMANENT,
    UNKNOWN
}

public record FailureDecision(
        FailureKind kind,
        String errorCode) {
}
~~~

Classifier ở tầng ứng dụng:

~~~java
public class MailFailureClassifier {

    public FailureDecision classify(Throwable error) {
        Throwable cause = unwrapCompletionException(error);

        if (cause instanceof MailContentBuildException) {
            return new FailureDecision(
                    FailureKind.PERMANENT, "MIME_PREPARATION");
        }

        if (cause instanceof MailAuthenticationException) {
            return new FailureDecision(
                    FailureKind.PERMANENT, "SMTP_AUTH");
        }

        if (cause instanceof TaskRejectedException) {
            return new FailureDecision(
                    FailureKind.RETRYABLE, "EXECUTOR_REJECTED");
        }

        // MailSendException có thể bọc nhiều loại nguyên nhân.
        // Cần mở cause, mã SMTP và giai đoạn trao đổi với server.
        return new FailureDecision(
                FailureKind.UNKNOWN, "SMTP_UNCLASSIFIED");
    }
}
~~~

Đây là ví dụ một policy **bảo thủ**, không phải classifier production hoàn chỉnh. Lỗi xác thực được xếp permanent cho lần gửi hiện tại nhưng có thể redrive sau khi sửa cấu hình. Với `MailSendException`, cần bổ sung phân tích phản hồi SMTP/provider thay vì kết luận mọi trường hợp đều retryable.

**Phân loại UNKNOWN là hợp lệ.** Thà ghi nhận sự không chắc chắn để đối soát hơn là khẳng định email chưa gửi rồi retry vô hạn.

## 10. Retry có kiểm soát thay vì nuốt exception

Một chiến lược retry hữu ích phải có:

1. **Điều kiện retry:** lỗi nào là tạm thời và có cơ hội thành công nếu thử lại?
2. **Giới hạn:** tối đa bao nhiêu lần hoặc tới deadline nào?
3. **Backoff:** đợi bao lâu giữa các lần?
4. **Jitter:** làm lệch thời điểm retry giữa các worker để tránh dồn tải.
5. **Trạng thái bền vững:** lần thử hiện tại và lần thử tiếp theo được lưu ở đâu?
6. **Duplicate policy:** nếu SMTP đã nhận message nhưng kết quả không được ghi nhận, retry có chấp nhận gửi lại không?

### 10.1. Exponential backoff

Một mô hình cơ bản:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Trong đó `d_0` là thời gian chờ ban đầu, `n` là số lần thử vừa thất bại và `d_{\max}` là giới hạn thời gian chờ. Thêm jitter ngẫu nhiên giúp tránh nhiều worker cùng retry.

Ví dụ một lịch retry minh họa:

| Lần thất bại | Delay cơ sở |
| --- | --- |
| 1 | 30 giây |
| 2 | 1 phút |
| 3 | 2 phút |
| 4 | 4 phút |
| 5 | 8 phút |
| Sau giới hạn | Chuyển trạng thái cuối hoặc chờ redrive |

Đây chỉ là chính sách ví dụ. Email có thời hạn ngắn (như mã xác minh) không nên được retry sau khi token hết hạn; báo cáo định kỳ có thể có thời gian retry dài hơn.

### 10.2. Không retry bằng vòng lặp vô hạn trong cùng worker

Tránh:

~~~java
while (true) {
    try {
        mailSender.send(message);
        break;
    } catch (MailException ex) {
        // Không đợi, không giới hạn và không phân loại.
    }
}
~~~

Vòng lặp này chiếm worker thread, tăng tải SMTP và có thể spam người nhận nếu server đã chấp nhận một số lần gửi trước timeout. Thay vào đó, cập nhật trạng thái `RETRY` với `nextAttemptAt` rồi nhường worker cho tác vụ khác.

### 10.3. Retry ngắn trong memory và retry bền vững

Có thể áp dụng một số retry ngắn cho lỗi rõ ràng xảy ra trước khi gửi message, nhưng **không nên coi retry trong memory là cơ chế phục hồi duy nhất**. Nếu JVM dừng, mọi Future và retry đang chờ trong memory đều mất.

Với email giao dịch, nên ưu tiên:

~~~text
Outbox row
  attempt_count = 2
  status = RETRY
  next_attempt_at = 2026-11-12T10:30:00Z
        |
        v
Scheduler/worker claim khi đến hạn
        |
        v
Gửi mail hoặc cập nhật RETRY/FAILED/SENT
~~~

Ví dụ thời gian trong sơ đồ là dữ liệu minh họa. Worker chỉ lấy lại bản ghi sau `next_attempt_at`, có giới hạn số lần thử và policy xử lý lỗi không rõ kết quả.

## 11. Outbox và trạng thái lỗi bền vững

`@Async` chuyển tác vụ sang thread khác, nhưng **không tự tạo hàng đợi bền vững**. Nếu ứng dụng dừng sau khi trả HTTP response nhưng trước khi worker gửi xong, công việc ở executor có thể mất.

Transactional outbox giúp gắn việc ghi ý định gửi email với transaction nghiệp vụ:

~~~text
Business transaction
   ├── Update order/payment
   └── Insert mail_outbox(status=PENDING)
              |
            COMMIT
              |
              v
      Outbox worker claims row
              |
              v
       Send via SMTP
          /       \
         /         \
     success       error
        |            |
        v            v
      SENT        RETRY / FAILED
~~~

Các trạng thái điển hình:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `PENDING` | Đã lưu ý định gửi, chờ worker |
| `PROCESSING` | Worker đang xử lý và giữ lease |
| `RETRY` | Gửi thất bại có thể thử lại sau một thời điểm |
| `SENT` | Lời gọi gửi SMTP đã hoàn tất thành công |
| `FAILED` | Đã dừng retry tự động hoặc lỗi không thể xử lý theo policy |
| `UNKNOWN` (nếu có) | Kết quả gửi không rõ, cần retry thận trọng hoặc đối soát |

### 11.1. Cập nhật trạng thái sau send

Một worker gửi email ngoài transaction database rồi cập nhật trạng thái trong transaction ngắn:

~~~java
try {
    MimeMessage message = mailMessageFactory.create(claimed);
    mailSender.send(message);

    // Transaction riêng, có điều kiện owner/version.
    boolean marked = stateService.markSent(claimed);

    if (!marked) {
        reportStateConflict(claimed.deliveryId());
    }
} catch (MailException ex) {
    FailureDecision decision = classifier.classify(ex);
    stateService.markFailure(claimed, decision);
}
~~~

Đây là pseudocode minh họa. Một implementation thực phải phân biệt exception phát sinh ở `send` với exception phát sinh ở `markSent`. **Không bọc cập nhật database sau gửi trong cùng `catch (MailException)` rồi mặc định retry SMTP**. Lỗi state update không có nghĩa gửi thất bại; gửi lại có thể tạo duplicate.

### 11.2. Crash window và giới hạn exactly-once

Giữa SMTP và database không có transaction chung:

~~~text
Worker calls JavaMailSender.send(message)
             |
             v
SMTP accepts message
             |
             v
Worker crashes before markSent()
             |
             v
Outbox still PROCESSING / lease expires
             |
             v
Another worker retries -> email may duplicate
~~~

Vì vậy **transactional outbox + SMTP thường có ngữ nghĩa at-least-once, không phải exactly-once delivery**. Đánh dấu `SENT` trước khi gửi có nguy cơ làm mất email; đánh dấu sau khi gửi có thể bị duplicate nếu cập nhật trạng thái thất bại.

Một `Message-ID` ổn định giúp correlation nhưng không bảo đảm mọi SMTP server/mail client deduplicate. Nếu provider có API riêng hỗ trợ idempotency key, có thể tận dụng theo hợp đồng provider; SMTP thuần không có cơ chế exactly-once chung.

### 11.3. Lease và worker đồng thời

Nếu nhiều worker poll cùng bảng, cần claim nguyên tử và lease/owner hoặc fencing token. Một worker đã mất lease không được cập nhật `SENT`, `RETRY` hay `FAILED` của hàng đã được worker khác claim lại.

Ví dụ điều kiện cập nhật:

~~~sql
UPDATE mail_outbox
SET status = 'SENT',
    sent_at = CURRENT_TIMESTAMP,
    lease_owner = NULL,
    lease_until = NULL
WHERE id = :id
  AND status = 'PROCESSING'
  AND lease_owner = :worker_id
  AND version = :claimed_version;
~~~

Phải kiểm tra **số hàng được cập nhật**. Nếu bằng 0, có thể worker không còn quyền giữ lease hoặc version đã thay đổi. Nếu SMTP send trước đó thành công, cần ghi nhận tình trạng này để đối soát, không đơn giản báo “email chưa gửi”.

## 12. Transaction và sự kiện sau commit

Trong nhiều nghiệp vụ, email chỉ được gửi khi transaction database commit. Nếu gọi `@Async` bên trong transaction:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    repository.confirm(orderId);
    asyncMailService.submit(buildCommand(orderId));
}
~~~

worker có thể bắt đầu chạy **trước khi transaction commit**. Nó có thể không đọc được dữ liệu mới hoặc gửi email cho một transaction cuối cùng bị rollback.

### 12.1. @TransactionalEventListener AFTER_COMMIT

Một phương án cho tác vụ không yêu cầu durability cao là lắng nghe event sau commit:

~~~java
public record OrderConfirmedEvent(
        String publicOrderId,
        String recipientEmail) {
}
~~~

Publisher:

~~~java
@Transactional
public void confirmOrder(String id) {
    orderRepository.confirm(id);
    eventPublisher.publishEvent(
            new OrderConfirmedEvent(id, recipientEmail));
}
~~~

Listener:

~~~java
@Component
public class OrderMailListener {

    private final AsyncMailService mailService;

    public OrderMailListener(AsyncMailService mailService) {
        this.mailService = mailService;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        MailCommand command = makeCommand(event);
        mailService.submit(command);
    }
}
~~~

`AFTER_COMMIT` giúp listener chỉ chạy sau khi transaction được commit. Tuy nhiên listener/future vẫn phụ thuộc tiến trình đang chạy. Nếu JVM chết sau commit nhưng trước khi task được submit hoặc executor bị quá tải, email vẫn có thể mất. Đối với email quan trọng, **outbox ghi trong transaction nghiệp vụ** là giải pháp mạnh hơn.

### 12.2. @Async và @Transactional không chia sẻ transaction gốc

Nếu method `@Async` có `@Transactional`, transaction ấy bắt đầu trong thread worker theo proxy Spring, **không phải transaction của caller**. Đừng dựa vào việc entity lazy của request còn gắn persistence context trong worker.

Khi dùng outbox, nên tách thành:

1. Transaction ngắn để claim công việc.
2. SMTP send ngoài transaction database.
3. Transaction ngắn để lưu kết quả.

Không giữ row lock hoặc JDBC connection suốt một thao tác SMTP có thể chậm hàng giây/phút.

## 13. Timeout, cancellation và interruption

Một tác vụ gửi mail chạy trên executor vẫn sử dụng network I/O. Nếu không cấu hình timeout, worker có thể bị giữ quá lâu khi SMTP server phản hồi chậm.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Các giá trị tính bằng millisecond, chỉ mang tính minh họa:

- `mail.smtp.connectiontimeout`: giới hạn thời gian mở kết nối.
- `mail.smtp.timeout`: giới hạn thời gian chờ đọc dữ liệu từ SMTP server.
- `mail.smtp.writetimeout`: giới hạn thời gian ghi khi transport hỗ trợ cấu hình này.

Timeout giúp tránh giữ thread vô hạn và hỗ trợ lease timeout của outbox. Nhưng một exception timeout **không tự khẳng định phía server chưa nhận message**: cần xem nó xảy ra trước hay sau khi DATA đã được chuyển tới SMTP.

### 13.1. CompletableFuture.orTimeout không bảo đảm hủy SMTP send

Ví dụ:

~~~java
CompletableFuture<MailSubmission> future =
        asyncMailService.submit(command)
                .orTimeout(15, TimeUnit.SECONDS);
~~~

`orTimeout` giúp Future hoàn tất exceptionally với `TimeoutException` nếu quá thời gian, nhưng **không bảo đảm** dừng thread hoặc thu hồi yêu cầu SMTP đang được thực hiện ở nền. Server có thể tiếp tục chấp nhận message sau khi caller đã coi Future là timeout.

Do đó, không nên dùng timeout ở Future như bằng chứng để gửi lại ngay. Cần cấu hình timeout ở transport và có chính sách xử lý kết quả không chắc chắn.

### 13.2. Không nuốt InterruptedException

Nếu worker có thao tác chờ, sleep hoặc Future.get, cần xử lý interruption:

~~~java
try {
    MailSubmission result = future.get(20, TimeUnit.SECONDS);
    recordSuccess(result);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Interrupted while waiting for mail task", ex);
} catch (TimeoutException ex) {
    recordUnknownResult(command.deliveryId());
} catch (ExecutionException ex) {
    recordFailure(
            command.deliveryId(), ex.getCause());
}
~~~

Khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` cho phép tầng điều phối tiếp tục xử lý tín hiệu shutdown/cancellation. Cách ghi nhận `UNKNOWN` khi timeout là ví dụ policy bảo thủ; nếu ứng dụng biết chắc chưa kết nối SMTP, policy có thể chọn retry.

### 13.3. Shutdown không bảo đảm mọi Future hoàn tất

Khi ứng dụng tắt hoặc deploy phiên bản mới, executor có thể vẫn còn task đang xếp hàng. Cần xác định chính sách shutdown:

- Dừng nhận task mới.
- Cho các tác vụ đang chạy hoàn tất trong giới hạn thời gian.
- Đặt timeout hợp lý cho SMTP.
- Nếu dùng outbox, để các hàng chưa xác nhận `SENT` có thể được claim lại sau lease hết hạn.

Các tùy chọn của `ThreadPoolTaskExecutor` như `setWaitForTasksToCompleteOnShutdown` và `setAwaitTerminationSeconds` cần được chọn theo yêu cầu deploy. Chờ executor hoàn tất chỉ hỗ trợ shutdown êm; **không biến tác vụ trong memory thành dữ liệu bền vững** nếu process bị kill đột ngột.

## 14. Truyền context và dữ liệu sang worker an toàn

Mỗi thread có state riêng. Không nên giả định context của HTTP request hoặc business transaction được chuyển nguyên sang async worker.

### 14.1. Truyền snapshot thay vì truy cập request/session

Không nên:

~~~java
@Async("mailExecutor")
public void sendLater(HttpServletRequest request, OrderEntity order) {
    String recipient = request.getUserPrincipal().getName();
    String orderNumber = order.getOrderNumber();
    // order có thể đã detach và request có thể đã kết thúc.
}
~~~

Thay bằng DTO có đủ dữ liệu cần thiết:

~~~java
public record MailCommand(
        UUID deliveryId,
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}
~~~

Application service chọn recipient hợp lệ và dựng snapshot trong ranh giới transaction thích hợp, sau đó submit command bất biến. Với job cần lưu bền vững, chỉ serialize những trường được phép vào outbox/queue.

### 14.2. Logging context bằng MDC

`MDC` thường dùng `ThreadLocal`, vì thế correlation ID ở request thread có thể không tự có trong executor thread. Có thể:

- Truyền `deliveryId` như một field của command và log tường minh.
- Dùng Spring `TaskDecorator` để copy MDC nếu hệ thống yêu cầu.
- Dùng cơ chế context propagation được application chọn để mang trace/span theo chuẩn quan sát.

Ví dụ TaskDecorator minh họa:

~~~java
executor.setTaskDecorator(runnable -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }

            runnable.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
});
~~~

Đoạn này được đặt trong method cấu hình executor trước khi khởi chạy thread pool, với import `java.util.Map` và `org.slf4j.MDC`. Cần khôi phục/clear MDC trong `finally` vì thread pool tái sử dụng thread. Nếu không làm sạch, dữ liệu log của người nhận trước có thể bị gắn sang email sau.

### 14.3. SecurityContext và LocaleContext

Nếu tác vụ cần biết người dùng yêu cầu gửi, nên truyền một định danh hoặc quyền đã được kiểm tra rõ ràng thay vì đọc `SecurityContextHolder` từ worker và giả định nó giống request thread. Spring Security có các executor wrapper hỗ trợ truyền security context trong trường hợp cần thiết, nhưng phải cân nhắc quyền tối thiểu và tránh sử dụng context đã hết hiệu lực.

Tương tự, template đa ngôn ngữ nên nhận `Locale` hoặc mã locale từ command/mail model. Đừng phụ thuộc vào `LocaleContextHolder` của HTTP request trong thread nền nếu chưa có cơ chế truyền context được kiểm soát.

## 15. Logging, metrics và báo lỗi mà không lộ dữ liệu

Lỗi gửi mail có thể chứa địa chỉ người nhận, subject, tên host, message body hoặc credential trong chuỗi nested cause. Vì vậy, quan sát lỗi cần đủ hữu ích nhưng tránh log dữ liệu nhạy cảm.

Nên log/đo lường:

| Trường | Mục đích |
| --- | --- |
| `deliveryId` / `outboxId` | Correlation |
| `templateName` | Xác định loại thông báo gặp vấn đề |
| `attemptCount` | Số lần gửi đã thử |
| `failureKind` | RETRYABLE / PERMANENT / UNKNOWN |
| `errorCode` | Mã lỗi đã chuẩn hóa |
| `executorName` | Xác định thread pool |
| `duration` | Thời gian xử lý từ claim tới kết quả |
| `nextAttemptAt` | Lịch retry tiếp theo |

Không nên log nguyên:

- Body email HTML/plain text.
- Token đặt lại mật khẩu/xác minh hoặc URL chứa token.
- SMTP password, credential, authorization header.
- Toàn bộ đối số của method `@Async` hoặc payload outbox.
- `Throwable.getMessage()` khi chưa biết message có chứa PII hay không.

Ví dụ log sự kiện đã được chuẩn hóa:

~~~text
deliveryId=9c...
template=order-confirmation
attempt=3
result=RETRY
errorCode=SMTP_TEMPORARY
nextAttemptAt=...
~~~

Một số metric hữu ích:

- `mail_async_submitted_total` và `mail_async_rejected_total`.
- `mail_smtp_accepted_total`, `mail_smtp_failed_total`.
- `mail_async_duration_seconds`.
- `mail_executor_active_threads` và `mail_executor_queue_depth`.
- `mail_outbox_pending_age_seconds`.
- `mail_outbox_retry_total`, `mail_outbox_failed_total`.
- `mail_outbox_state_conflict_total`.

Không dùng địa chỉ email hoặc delivery ID làm label metric vì có thể lộ dữ liệu và tạo cardinality quá lớn. Dùng template, provider, nhóm lỗi và môi trường làm dimension phù hợp.

### 15.1. HTTP response nên thể hiện điều gì?

Nếu request chỉ tạo một job bất đồng bộ, một phản hồi kiểu “đã tiếp nhận” phù hợp hơn “đã gửi thành công”. Ví dụ:

~~~json
{
  "requestId": "generated-delivery-id",
  "status": "QUEUED"
}
~~~

`QUEUED` chỉ nên được sử dụng khi công việc thật sự đã được nhận vào queue hoặc outbox theo hợp đồng hệ thống. Nếu chỉ submit task in-memory, cần hiểu rằng công việc có thể mất sau restart. Một response `202 Accepted` không tự tạo durability hoặc retry.

Nếu cần người dùng kiểm tra tiến trình, có thể cung cấp endpoint trạng thái dựa trên ID không lộ thông tin nhạy cảm và phân quyền truy cập phù hợp. Không nên tiết lộ địa chỉ email hoặc chi tiết lỗi SMTP tùy ý cho client công cộng.

## 16. Kiểm thử xử lý exception bất đồng bộ

Với `@Async`, việc test không chỉ xác nhận method có gọi `JavaMailSender.send`, mà còn cần kiểm tra **kênh lỗi** phù hợp và trạng thái sau lỗi.

### 16.1. Test khi transport trả lỗi

Một integration test nhỏ qua Spring context có thể mock mail sender và gọi bean `@Async` thật:

~~~java
@SpringBootTest
class AsyncMailServiceTest {

    @Autowired
    private AsyncMailService asyncMailService;

    @MockBean
    private JavaMailSender mailSender;

    @Test
    void failedMailSendCompletesFutureExceptionally() throws Exception {
        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties()));

        when(mailSender.createMimeMessage()).thenReturn(message);
        doThrow(new MailSendException("SMTP unavailable"))
                .when(mailSender).send(any(MimeMessage.class));

        CompletableFuture<MailSubmission> future =
                asyncMailService.submit(sampleCommand());

        ExecutionException exception = assertThrows(
                ExecutionException.class,
                () -> future.get(5, TimeUnit.SECONDS));

        assertThat(exception.getCause())
                .isInstanceOf(MailSendException.class);
    }
}
~~~

Đây là mã test minh họa với JUnit 5, Mockito, AssertJ và Spring Boot test support; cần bổ sung import, cấu hình test và `sampleCommand()` cho dự án. Tùy phiên bản Spring Boot, annotation mock bean có thể dùng API tương ứng được framework khuyến nghị. Mục tiêu là **lấy lỗi từ Future qua proxy thật**, không trực tiếp gọi một instance tự tạo bằng `new`.

### 16.2. Test lỗi ngay khi submit

Một executor cấu hình queue cực nhỏ và được cố ý làm bão hòa có thể gây `TaskRejectedException`. Test cần kiểm tra caller bắt được lỗi và hệ thống không tuyên bố job đã được nhận.

Để test ổn định, có thể dùng một `Executor` giả luôn reject hoặc một `TaskExecutor` test có hành vi từ chối xác định, thay vì trông chờ race condition của thread pool thật.

### 16.3. Test AsyncUncaughtExceptionHandler

Với method `@Async void`, test nên:

1. Gọi qua Spring proxy.
2. Làm method ném một exception có kiểm soát.
3. Ghi nhận handler được gọi với method và loại lỗi tương ứng.
4. Xác nhận không có giả định rằng caller nhận được exception trực tiếp.

Không dùng `Thread.sleep(...)` cố định làm bằng chứng handler đã chạy; dùng `CountDownLatch` hoặc cơ chế đồng bộ test có timeout phù hợp.

### 16.4. Test trạng thái outbox và crash window

Với luồng cần độ tin cậy cao, bổ sung những trường hợp:

| Kịch bản | Kết quả cần xác nhận |
| --- | --- |
| Worker gửi thành công | Sau send, cập nhật `SENT` |
| SMTP trả lỗi tạm thời | `RETRY`, `attemptCount` và `nextAttemptAt` được cập nhật |
| Lỗi dữ liệu/template vĩnh viễn | `FAILED`, không retry vô hạn |
| Executor từ chối task | Công việc vẫn `PENDING` hoặc được lên lịch lại |
| Worker chết khi PROCESSING | Lease hết hạn, hàng được reclaim |
| SMTP thành công, DB markSent thất bại | Có cảnh báo duplicate risk, không tuyên bố gửi thất bại chắc chắn |
| Hai worker cùng poll | Atomic claim ngăn claim trùng cùng lúc |
| Worker mất lease | Conditional update theo owner/version không ghi đè |
| Request transaction rollback | Không tạo outbox row đã commit |

Repository/concurrency test nên chạy trên database phù hợp production (ví dụ Testcontainers PostgreSQL khi dùng `SKIP LOCKED`), vì H2 hoặc mock repository có thể không tái hiện đầy đủ locking semantics.

### 16.5. SMTP sink trong integration test

Mailpit hoặc MailHog có thể nhận email trong môi trường thử nghiệm để quan sát message đã gửi. Với hệ thống bất đồng bộ, xác nhận:

- Worker thật sự xử lý job được tạo.
- HTML và plain text được tạo đúng.
- Exception/result được phản ánh trong trạng thái outbox.
- Attachment nếu có không bị mất.
- Không gửi email test tới địa chỉ khách hàng thật.

SMTP sink không chứng minh provider production sẽ giao thư thành công hoặc không có spam filtering. Đây là tầng kiểm thử luồng gửi, không phải bằng chứng giao thư tới inbox.

## 17. Gửi nhiều email: partial failure và exception tổng hợp

Khi một job gửi nhiều message, có thể xảy ra tình huống một số message thành công, số khác thất bại. Nếu chỉ trả về một boolean `success` cho cả batch, ứng dụng khó biết message nào cần retry.

Ví dụ:

~~~text
Batch of 3 emails
├── delivery A -> SMTP accepted
├── delivery B -> SMTP rejected
└── delivery C -> SMTP accepted
~~~

Nếu retry toàn bộ batch, người nhận A và C có thể nhận trùng. Vì vậy, với email giao dịch, nên cân nhắc **một delivery ID và một outbox record cho mỗi người nhận/message**.

`MailSendException` có thể cung cấp thông tin về các message bị thất bại tùy cách gửi và transport implementation. Cần phân tích ở cấp message khi dispatch batch; không nên mặc định mọi email trong batch cùng thất bại hoặc cùng thành công.

### 17.1. CompletableFuture.allOf không thay trạng thái từng email

Ví dụ:

~~~java
List<CompletableFuture<MailSubmission>> futures =
        commands.stream()
                .map(asyncMailService::submit)
                .toList();

CompletableFuture<Void> all = CompletableFuture.allOf(
        futures.toArray(new CompletableFuture[0]));
~~~

Nếu một Future thất bại, `allOf` có thể hoàn tất exceptionally. Nhưng kết quả tổng không mô tả trực tiếp delivery nào đã thành công hoặc thất bại. Cần giữ mapping giữa `deliveryId` và từng Future để cập nhật kết quả riêng.

Ngoài ra, `stream().map(asyncMailService::submit)` có thể dừng sớm khi executor reject một lần gọi. Với batch nghiệp vụ, hãy chủ động kiểm soát việc submit từng item và giữ trạng thái PENDING cho phần chưa được nhận.

### 17.2. Exception trong callback phụ

Giả sử:

~~~java
CompletableFuture<MailSubmission> f =
        asyncMailService.submit(command);

CompletableFuture<MailSubmission> tracked = f.whenComplete(
        (submission, error) -> stateRepository.updateState(
                command.deliveryId(), submission, error));
~~~

Nếu SMTP thành công nhưng `stateRepository.updateState` ném exception, dependent Future `tracked` có thể thất bại. Không được diễn giải thất bại đó là “SMTP chưa gửi”; nguyên nhân nằm ở bước lưu state.

Hãy phân biệt hai kết quả:

- **Dispatch result**: SMTP có chấp nhận message hay không?
- **Persistence result**: trạng thái đó đã được lưu thành công hay chưa?

Một dispatcher/outbox worker có boundary rõ ràng sẽ tách hai bước này tốt hơn một callback được gắn vào Future mà không theo dõi kết quả.

## 18. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `try/catch` quanh lệnh gọi async rồi nghĩ đã bắt toàn bộ lỗi | Không nhận exception trên worker thread | Quan sát Future hoặc dùng handler cho `void` |
| Method `@Async void` chỉ log lỗi | Không có kết quả bền vững để retry | Trả Future khi cần điều phối, hoặc lưu outbox state |
| Gọi `this.sendAsync()` trong cùng class | Bỏ qua proxy; method có thể chạy đồng bộ | Gọi qua Spring bean/proxy |
| Bắt mọi `Exception` và trả kết quả thành công | Che giấu thất bại | Hoàn tất exceptionally hoặc cập nhật trạng thái lỗi |
| Dùng `exceptionally(ex -> null)` không lưu lỗi | Failure bị mất trong chuỗi Future | Ghi nhận outcome rồi mới quyết định recovery |
| Gọi `future.get()` ngay trong HTTP request | Caller bị block | Dùng callback/event/outbox nếu không cần chờ |
| `CompletableFuture.supplyAsync` không chỉ định executor | Chạy trên common pool ngoài cấu hình | Dùng Spring executor hoặc `@Async` có tên |
| Không giới hạn queue | Memory/backlog tăng vô hạn khi SMTP chậm | Bounded queue, backpressure hoặc outbox |
| Retry mọi lỗi ngay lập tức | Gây quá tải SMTP và nguy cơ duplicate | Phân loại lỗi, backoff, jitter, max attempts |
| Coi timeout là chắc chắn chưa gửi | Retry có thể tạo email trùng | Xem giai đoạn SMTP, hỗ trợ trạng thái unknown |
| `@Async` chạy trước transaction commit | Có thể gửi email cho dữ liệu rollback | AFTER_COMMIT hoặc transactional outbox |
| Truyền JPA entity lazy vào worker | `LazyInitializationException`, dữ liệu không nhất quán | Dùng DTO/snapshot |
| Giữ transaction DB khi gọi SMTP | Giữ lock/connection lâu | Tách claim, send và update state |
| Mark `SENT` trước khi gửi | Process chết có thể làm mất email | Gửi trước rồi cập nhật với duplicate policy |
| Không kiểm tra state update conflict | Worker cũ ghi đè hoặc mất lịch sử xử lý | Lease owner/version/fencing token |
| Dùng chung `MimeMessage` giữa nhiều worker | Lẫn nội dung/recipient và race condition | Tạo message mới cho từng delivery |
| Log nguyên params hoặc exception message | Rò rỉ PII/token | Log ID, loại lỗi và mã đã chuẩn hóa |
| Giả định HTTP 202 là SMTP accepted | Trả thông tin sai cho người dùng | Phân biệt QUEUED và SMTP_ACCEPTED |

## 19. Lựa chọn kiến trúc theo mức độ quan trọng

Không phải mọi email đều cần cùng mức độ bảo đảm. Có thể chọn theo nhu cầu:

| Mức độ | Ví dụ | Cơ chế xử lý exception nên cân nhắc |
| --- | --- | --- |
| Best-effort | Thông báo phụ trợ, không cần audit | `@Async CompletableFuture` + quan sát/log lỗi và backpressure |
| Cần biết kết quả trong phiên làm việc | Tác vụ quản trị gửi thông báo một lần | Future + trạng thái gửi được lưu, retry có giới hạn |
| Email giao dịch quan trọng | Hóa đơn, xác nhận giao dịch, thông báo bảo mật | Transactional outbox + worker + retry/backoff + audit |
| Gửi khối lượng lớn | Thông báo hàng loạt cho nhiều người | Queue bền vững, xử lý theo delivery, rate limit và giám sát provider |

**`@Async` là công cụ thực thi bất đồng bộ, không phải cơ chế bảo đảm giao email.** Khi cần durability, at-least-once, audit và retry sau restart, hãy dùng outbox hoặc message broker có ack/retry phù hợp.

### 19.1. Một luồng đề xuất cho email giao dịch

~~~text
Business service
  |
  | @Transactional
  +--> Save business state
  +--> Save mail outbox (PENDING)
  |
  v
COMMIT
  |
  v
Outbox polling worker / durable consumer
  |
  +--> Claim delivery atomically (PROCESSING + lease)
  |
  +--> Build MimeMessage
  |
  +--> JavaMailSender.send
  |       |
  |       +--> successful return: mark SENT
  |       |
  |       +--> exception: classify
  |                       |
  |                       +--> RETRY with nextAttemptAt
  |                       +--> FAILED
  |                       +--> UNKNOWN / reconciliation
  |
  v
Metrics, audit, alerts
~~~

Nếu cần song song hóa nhiều delivery, có thể sử dụng executor có giới hạn phía worker. Tuy nhiên nguồn sự thật vẫn là bản ghi outbox, không phải `CompletableFuture` trong memory. Sau restart, lease/retry giúp tiếp tục xử lý các hàng chưa ở trạng thái cuối.

## 20. Câu hỏi thường gặp

**“Tại sao exception trong @Async không chạy vào catch ở controller?”**  
Vì worker chạy trên thread khác sau khi task đã được submit. Controller chỉ có thể bắt lỗi submit đồng bộ (ví dụ executor reject); lỗi khi worker thực thi phải được nhận qua Future hoặc handler.

**“Khi dùng @Async void, exception đi đâu?”**  
Exception chưa được bắt thường được chuyển tới `AsyncUncaughtExceptionHandler`. Caller không có Future để lấy exception. Handler nên phục vụ quan sát, không phải cơ chế retry bền vững duy nhất.

**“CompletableFuture.failedFuture và ném exception khác gì?”**  
Cả hai có thể làm kết quả async hoàn tất exceptionally khi được dùng đúng chỗ. Trong method `@Async`, có thể ném runtime exception để Spring proxy hoàn tất Future lỗi; hoặc trả failed future phù hợp. Điều quan trọng là không chuyển failure thành kết quả thành công giả.

**“Tại sao method @Async trả completedFuture mà caller vẫn không nhận kết quả ngay?”**  
Giá trị `completedFuture` được tạo bên trong method đã chạy trên worker thread. Spring proxy trả Future đại diện cho quá trình chạy bất đồng bộ; caller nhận kết quả sau khi worker hoàn tất.

**“Có cần catch MailException ngay trong method @Async không?”**  
Không bắt buộc nếu Future được quan sát và tầng điều phối có chính sách xử lý lỗi. Nên catch khi cần phân loại, bổ sung correlation hoặc cập nhật trạng thái; không catch chỉ để log rồi bỏ qua.

**“TaskRejectedException có nghĩa SMTP gửi thất bại không?”**  
Không. Nó thường có nghĩa executor chưa nhận task. Đây là lỗi submit/capacity, xảy ra trước khi SMTP send được thực hiện.

**“Có nên retry ngay khi gặp MailSendException không?”**  
Không nên mặc định. Cần phân tích nguyên nhân và phản hồi SMTP. Nếu message có thể đã được chấp nhận trước timeout, retry có nguy cơ gửi trùng.

**“Timeout ở CompletableFuture có ngắt được SMTP không?”**  
Không được bảo đảm. Future có thể báo timeout trong khi thao tác SMTP vẫn chạy. Nên có timeout ở transport, lease và chính sách trạng thái UNKNOWN khi kết quả không rõ.

**“Có thể dùng @Transactional trong @Async không?”**  
Có thể tạo transaction riêng trong worker qua Spring proxy, nhưng transaction gốc của caller không được mang sang thread khác. Không nên giữ transaction mở trong lúc chờ SMTP.

**“AFTER_COMMIT listener đã đủ tin cậy chưa?”**  
Nó ngăn gửi trước commit nhưng không tạo hàng đợi bền vững. Nếu process chết sau commit, event/task chưa được ghi vào outbox có thể mất.

**“Outbox có bảo đảm không gửi trùng không?”**  
Không hoàn toàn. Nó hỗ trợ at-least-once; nếu SMTP đã nhận email nhưng worker chết trước khi ghi `SENT`, lần retry có thể tạo duplicate.

**“Có nên log exception đầy đủ không?”**  
Cần đủ thông tin cho vận hành, nhưng phải kiểm soát dữ liệu nhạy cảm. Nên dùng delivery ID, error code và loại exception, đồng thời cấu hình logging phù hợp với chính sách bảo mật.

**“Khi nào nên trả HTTP 202?”**  
Khi ứng dụng đã tiếp nhận yêu cầu để xử lý tiếp theo theo hợp đồng API. Với nghiệp vụ cần độ tin cậy, nên ghi job bền vững trước khi trả QUEUED. Không gọi trạng thái này là đã giao email tới inbox.

## 21. Ghi nhớ khi xử lý exception trong tác vụ bất đồng bộ

Quy trình tư duy:

~~~text
Gọi @Async method
       |
       +--> Reject ngay?
       |       |
       |       +--> TaskRejectedException: xử lý ở caller
       |
       +--> Executor nhận task
               |
               +--> MIME/template lỗi
               |       |
               |       +--> Future exceptionally / FAILED
               |
               +--> SMTP send lỗi
               |       |
               |       +--> Phân loại RETRYABLE / PERMANENT / UNKNOWN
               |       +--> Lưu kết quả, backoff, giới hạn retry
               |
               +--> SMTP send thành công
                       |
                       +--> Ghi SMTP_ACCEPTED/SENT
                       +--> Xử lý nếu state update thất bại
~~~

Khi dùng Spring Framework Mail:

1. Xác định exception phát sinh ở **caller khi submit** hay **worker khi chạy**.
2. Với `@Async void`, cấu hình `AsyncUncaughtExceptionHandler`; với `Future/CompletableFuture`, phải quan sát completion.
3. Phân biệt lỗi dựng MIME, xác thực SMTP, transport, executor và database state update.
4. Retry có giới hạn, backoff và policy xử lý kết quả mơ hồ; không retry vô hạn.
5. Cấu hình SMTP timeout, executor capacity và shutdown hợp lý.
6. Truyền DTO/snapshot, correlation ID và locale rõ ràng qua ranh giới thread.
7. Với email giao dịch, lưu outbox trong transaction nghiệp vụ và cập nhật `SENT/RETRY/FAILED` bằng transaction riêng, có điều kiện owner/version.
8. Không nhầm “SMTP accepted” với “đã tới inbox”, và không tuyên bố exactly-once chỉ dựa vào `@Async` hoặc outbox.

**Kết luận:** Xử lý exception trong gửi mail bất đồng bộ không chỉ là thêm `try/catch`. Cần thiết kế kênh nhận kết quả, phân loại lỗi, giới hạn retry, bảo vệ dữ liệu nhạy cảm và lưu tiến trình bền vững khi nghiệp vụ yêu cầu. Làm rõ các ranh giới này giúp ứng dụng không đánh mất lỗi, không báo thành công sai và phục hồi có kiểm soát khi SMTP hoặc worker gặp sự cố.
