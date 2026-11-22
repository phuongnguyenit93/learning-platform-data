# @Async và ranh giới proxy của lời gọi bất đồng bộ

Khi một ứng dụng Spring xác nhận đơn hàng, phần xử lý HTTP thường không nên phải chờ toàn bộ thời gian kết nối SMTP, gửi nội dung và nhận phản hồi từ mail server. Spring cung cấp annotation `@Async` để yêu cầu thực thi một phương thức trên thread do `TaskExecutor` quản lý, thay vì tiếp tục chạy trực tiếp trên thread của lời gọi.

Tuy nhiên, **`@Async` không đơn thuần là gắn annotation lên một phương thức rồi mọi lời gọi tự động chạy nền**. Với cơ chế mặc định của Spring, `@Async` dựa trên **Spring AOP proxy**: lời gọi phải đi **qua đối tượng proxy của Spring** để được chặn và chuyển sang executor. Nếu một phương thức trong cùng object tự gọi phương thức có `@Async`, lời gọi thường đi thẳng tới `this`, bỏ qua proxy và chạy đồng bộ.

Điều này đặc biệt quan trọng trong **Spring Framework Mail**, vì `JavaMailSender.send(...)` vốn là thao tác gửi SMTP có thể chặn thread trong lúc kết nối hoặc trao đổi dữ liệu. Khi dùng `@Async` đúng cách, caller có thể quay về sớm, nhưng **công việc gửi SMTP vẫn là thao tác blocking trên thread của executor**. Annotation không làm SMTP thành một giao thức non-blocking, cũng không cung cấp hàng đợi bền vững hay bảo đảm email cuối cùng tới inbox.

Bài học này giải thích `@EnableAsync`, ranh giới proxy, self-invocation, executor, kiểu trả về, xử lý lỗi, giao dịch, context giữa các thread và các thiết kế gửi email bất đồng bộ dễ kiểm soát.

## 1. Đồng bộ và bất đồng bộ khác nhau ở đâu?

Một luồng gửi thư đồng bộ có thể diễn ra như sau:

~~~text
HTTP request
  → Controller
  → OrderApplicationService
  → JavaMailSender.send(...)
  → SMTP server phản hồi
  → Controller trả response
~~~

Trong luồng này, request thread có thể phải chờ đến khi `send(...)` hoàn thành hoặc ném lỗi. Thời gian chờ chịu ảnh hưởng của kết nối mạng, TLS, xác thực, tốc độ SMTP relay và dung lượng message.

Khi chuyển phần gửi sang executor:

~~~text
HTTP request thread
  → Controller
  → OrderApplicationService
  → gọi MailWorker proxy
  → công việc được giao cho executor
  → Controller có thể trả response

Executor thread
  → MailWorker.send(...)
  → JavaMailSender.send(...)
  → SMTP relay
~~~

**Bất đồng bộ ở đây là thay đổi thread thực thi và thời điểm caller nhận quyền điều khiển**, không thay đổi bản chất của SMTP.

Điểm phân biệt:

| Khía cạnh | Gửi đồng bộ | Gửi bằng `@Async` |
| --- | --- | --- |
| Thread thực hiện `JavaMailSender.send` | Thread đang gọi | Thread của executor |
| Caller chờ toàn bộ thao tác gửi | Thường có | Không nhất thiết |
| Thấy exception khi gọi trực tiếp | Có thể bắt ngay trong caller | Phụ thuộc kiểu trả về và cách quan sát future |
| Công việc sống sót khi ứng dụng chết | Không tự bảo đảm | Cũng không tự bảo đảm |
| SMTP có trở thành non-blocking không | Không | Không |
| Cần quản lý tải và lỗi | Có | Càng cần vì có thêm executor và queue |

Với phương thức `void` có `@Async`, caller thường chỉ biết công việc đã được lên lịch thành công. Với phương thức trả `CompletableFuture`, caller có thể quan sát việc hoàn thành hoặc thất bại thông qua future. Cả hai đều khác với việc SMTP relay xác nhận phát thư tới hộp thư người nhận.

## 2. Vai trò của Spring AOP proxy

Khi bật khả năng async, Spring có thể tạo proxy bao quanh bean có phương thức được đánh dấu `@Async`. Proxy đóng vai trò trung gian:

~~~mermaid
flowchart LR
    A["Bean khác / Controller"] --> B["Spring proxy của MailWorker"]
    B --> C["Async interceptor"]
    C --> D["TaskExecutor"]
    D --> E["MailWorker thực"]
    E --> F["JavaMailSender.send"]
~~~

Khi gọi một phương thức qua proxy, interceptor xác định executor, tạo hoặc giao công việc, và để thread của executor gọi phương thức thực.

Một luồng khái quát:

1. Spring khởi tạo bean và áp dụng async infrastructure.
2. Một bean khác nhận reference tới bean đã được proxy.
3. Caller gọi phương thức được đánh dấu `@Async` qua reference đó.
4. Interceptor giao nhiệm vụ cho executor phù hợp.
5. Executor thread thực hiện body của phương thức.
6. Kết quả/lỗi được trả hoặc công bố theo hợp đồng return type.

**Điều kiện cốt lõi:** lời gọi phải đi qua proxy. Chỉ có annotation trên mã nguồn chưa đủ nếu object được tạo bằng `new` hoặc được gọi nội bộ qua `this`.

### Phân biệt bean thật và bean proxy

Giả sử:

~~~java
@Service
public class MailWorker {

    @Async
    public void sendNotice() {
        // Công việc gửi mail.
    }
}
~~~

Object mà Spring inject vào một bean khác có thể là proxy. Nhưng bên trong `MailWorker`, từ khóa `this` vẫn tham chiếu instance đang chạy phương thức; việc tự gọi không đi qua proxy.

Proxy không có nghĩa Spring thay đổi bytecode của mọi lời gọi tới phương thức đó. Với chế độ mặc định `AdviceMode.PROXY`, Spring chủ yếu chặn những lời gọi đi vào qua proxy.

## 3. Bật @Async với @EnableAsync

Trong một ứng dụng Spring, khai báo cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Hoặc đặt `@EnableAsync` trên một configuration class thích hợp trong ứng dụng.

Chỉ thêm `spring-boot-starter-mail` không đồng nghĩa các phương thức có `@Async` đã được kích hoạt. `@EnableAsync` bật infrastructure để xử lý annotation async.

Ví dụ bean:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class MailWorker {

    @Async
    public void sendNotice() {
        System.out.println(
                "Thread gửi mail: "
                        + Thread.currentThread().getName()
        );
    }
}
~~~

Nếu bean được gọi **qua proxy** từ bean khác, phương thức có thể chạy trên executor thread. Nếu gọi trực tiếp từ chính bean hoặc tạo bằng `new MailWorker()`, annotation không tự tạo background execution.

### Executor mặc định không phải cấu hình production mặc nhiên tối ưu

Khi `@Async` không chỉ rõ executor, Spring cần tìm executor phù hợp trong context. Quy tắc chọn executor phụ thuộc cấu hình Spring, bean `TaskExecutor` có sẵn, tên bean được quy ước và Spring Boot auto-configuration. Nếu không có executor phù hợp, framework có cơ chế fallback; không nên suy ra ứng dụng chắc chắn có thread pool được giới hạn theo ý muốn.

Trong một luồng gửi mail production, nên tạo executor chuyên dụng hoặc cấu hình executor được dùng một cách tường minh, kiểm soát số thread, hàng chờ, timeout, shutdown và hành vi khi quá tải.

## 4. Ranh giới proxy: external call và self-invocation

Đây là điểm dễ gây nhầm lẫn nhất.

### 4.1. Lời gọi từ một bean khác — thông thường được proxy chặn

~~~java
@Service
public class OrderNotificationService {

    private final MailWorker mailWorker;

    public OrderNotificationService(MailWorker mailWorker) {
        this.mailWorker = mailWorker;
    }

    public void requestMail(OrderMailCommand command) {
        // mailWorker là bean được Spring inject.
        mailWorker.sendOrderConfirmation(command);
    }
}
~~~

Nếu `MailWorker.sendOrderConfirmation` được đánh dấu `@Async`, async infrastructure đã bật và Spring inject proxy thích hợp, lời gọi này đi qua proxy và được chuyển sang executor.

### 4.2. Tự gọi trong cùng bean — thường KHÔNG bất đồng bộ

Ví dụ sai về kỳ vọng:

~~~java
@Service
public class OrderService {

    public void confirmOrder(OrderMailCommand command) {
        // Xử lý đơn hàng ...

        sendEmail(command);
    }

    @Async
    public void sendEmail(OrderMailCommand command) {
        // JavaMailSender.send(...).
    }
}
~~~

`confirmOrder` gọi `sendEmail` trên cùng instance. Về mặt thực thi, đó là lời gọi tương đương `this.sendEmail(command)`, không phải lời gọi đi qua proxy.

Kết quả thường là:

- Phương thức `sendEmail` chạy trên thread hiện tại.
- `confirmOrder` vẫn phải chờ SMTP.
- `@Async` không tạo ra tác dụng bất đồng bộ như mong đợi.
- Cơ chế bắt lỗi cũng có thể khác kỳ vọng vì interceptor async đã bị bỏ qua.

Đây là hiện tượng **self-invocation**.

~~~mermaid
flowchart TD
    A["Caller"] --> B["OrderService proxy"]
    B --> C["confirmOrder trên target"]
    C --> D["this.sendEmail"]
    D --> E["Target method chạy trực tiếp"]
    E --> F["Không qua async interceptor"]
~~~

Thậm chí nếu controller gọi `confirmOrder` qua proxy, **lời gọi bên trong `confirmOrder` tới `sendEmail` vẫn là lời gọi nội bộ**. Proxy chỉ chặn điểm vào bên ngoài tương ứng với phương thức được advise; nó không tự chặn mọi lệnh gọi giữa các method của target object.

## 5. Cách sửa self-invocation: tách bean thực hiện công việc

Cách rõ ràng nhất là đưa phương thức async sang bean khác:

~~~java
@Service
public class OrderService {

    private final MailWorker mailWorker;

    public OrderService(MailWorker mailWorker) {
        this.mailWorker = mailWorker;
    }

    public void confirmOrder(OrderMailCommand command) {
        // Cập nhật đơn hàng / kiểm tra nghiệp vụ.
        mailWorker.sendOrderConfirmation(command);
    }
}
~~~

~~~java
@Service
public class MailWorker {

    @Async("mailExecutor")
    public CompletableFuture<Void> sendOrderConfirmation(
            OrderMailCommand command) {

        // Tạo MIME message và gửi SMTP.
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Lúc này `OrderService` gọi một Spring bean khác qua reference được inject. Proxy của `MailWorker` có cơ hội chặn lời gọi và giao công việc cho `mailExecutor`.

Ưu điểm:

- Ranh giới sync → async hiện rõ trong cấu trúc lớp.
- Có thể kiểm thử application service và mail worker riêng.
- `MailWorker` chỉ phụ trách công việc được giao.
- Dễ đặt executor, timeout, logging, retry policy và đo lường cho mail.
- Tránh workaround khó theo dõi như lấy proxy của chính bean từ application context.

### Không khuyến khích tự tiêm bean vào chính nó

Một số ví dụ dùng self-injection hoặc `AopContext.currentProxy()` để gọi lại qua proxy. Những cách này có thể phụ thuộc cấu hình proxy, làm mã khó hiểu hoặc gây vấn đề dependency cycle. Nếu kiến trúc cho phép, **tách bean** là lựa chọn dễ bảo trì hơn.

### Trường hợp đặc biệt: AspectJ weaving

`@EnableAsync` hỗ trợ chế độ mặc định `PROXY` và có thể cấu hình `ASPECTJ` khi đã tích hợp weaving và các dependency tương ứng. Weaving có khả năng áp dụng advice vào lời gọi nội bộ theo cách khác proxy. Tuy nhiên, đó là một cơ chế triển khai và vận hành riêng; không nên đổi sang AspectJ chỉ để tránh tách một bean gửi mail.

## 6. Những phương thức nào nên gắn @Async?

Trong thiết kế dùng Spring proxy thông thường, nên đánh dấu **public method không final** trên bean được Spring quản lý.

~~~java
@Service
public class MailWorker {

    @Async("mailExecutor")
    public CompletableFuture<Void> send(OrderMailCommand command) {
        // ...
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Các tình huống dễ gây nhầm:

| Tình huống | Điều cần nhớ |
| --- | --- |
| Phương thức gọi qua Spring bean proxy | Có thể được async interceptor xử lý |
| Gọi bằng `this.method()` | Bỏ qua proxy trong proxy mode |
| Object tạo bằng `new` | Không phải Spring-managed proxy |
| `private` method | Không phải điểm vào proxy để chặn thông thường |
| `final` method khi dùng class-based proxy | Không thể override để chặn bằng subclass proxy |
| `final` class khi cần class-based proxy | Không thể tạo subclass proxy |
| Gọi trong constructor hoặc `@PostConstruct` | Không nên kỳ vọng async proxy đã có tác dụng tại thời điểm đó |
| Method không được expose bởi JDK interface proxy | Caller không thể truy cập method đó qua interface proxy tương ứng |

Spring AOP có thể tạo **JDK dynamic proxy** cho interface hoặc **class-based proxy** trong những cấu hình nhất định. Khả năng interception phụ thuộc loại proxy, visibility và cách method được gọi. Với mail worker, dùng public non-final method và inject qua một interface/bean phù hợp là lựa chọn đơn giản.

### Annotation trên interface và implementation

Có thể gặp dự án đặt `@Async` trên interface hoặc implementation. Cách nhận diện annotation và áp dụng proxy có thể phụ thuộc chế độ proxy/weaving; khi muốn hành vi rõ ràng trong một application service cụ thể, nên đánh dấu implementation method được Spring quản lý và kiểm tra cấu hình proxy đang dùng.

Không coi lời gọi từ một object Java bất kỳ là lời gọi được AOP intercept. Dependency injection và Spring bean lifecycle là một phần của hợp đồng sử dụng `@Async`.

## 7. Cấu hình mailExecutor chuyên dụng

Gửi SMTP là công việc I/O blocking. Nếu dùng chung executor với những việc khác như tạo báo cáo, resize ảnh hoặc tác vụ CPU nặng, một nhóm công việc có thể chiếm hết thread và ảnh hưởng phần còn lại.

Có thể tạo `ThreadPoolTaskExecutor` riêng cho gửi mail:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean(name = "mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);

        executor.initialize();
        return executor;
    }
}
~~~

Các con số `4`, `8`, `100` và `20` chỉ là ví dụ để giải thích cấu hình; giá trị phù hợp phải dựa trên lưu lượng, độ trễ SMTP, giới hạn provider và bộ nhớ ứng dụng.

Dùng executor đã định danh:

~~~java
@Async("mailExecutor")
public CompletableFuture<Void> sendOrderConfirmation(
        OrderMailCommand command) {
    // ...
}
~~~

Tên `"mailExecutor"` trong `@Async` phải xác định được executor tương ứng trong Spring context.

### 7.1. Hiểu thứ tự tăng tải của ThreadPoolTaskExecutor

Với một thread pool có queue dung lượng hữu hạn, hành vi khái quát là:

1. Tạo thread tới `corePoolSize` khi có công việc.
2. Khi core threads bận, nhiệm vụ thường được đưa vào queue.
3. Khi queue đầy và số thread chưa đạt `maxPoolSize`, pool có thể tạo thêm thread.
4. Khi cả pool và queue đều đạt giới hạn, executor áp dụng chính sách rejection.

Vì vậy, tăng `maxPoolSize` không bảo đảm pool sẽ luôn tăng tới giới hạn đó trước khi queue đầy. Đây là chi tiết thường bị hiểu nhầm khi cấu hình queue lớn.

### 7.2. Rejection không phải SMTP failure

Nếu queue đầy, tác vụ có thể bị từ chối **ngay lúc caller cố lên lịch**, trước khi body phương thức `@Async` được thực hiện. Caller cần xử lý tình huống này riêng với lỗi xảy ra trong executor thread.

Spring có thể biểu diễn rejection bằng `TaskRejectedException` hoặc exception liên quan tới executor và chính sách rejection. Không giả định mọi lời gọi `@Async` đều được nhận rồi sẽ chạy.

### 7.3. Không dùng CallerRunsPolicy một cách vô thức

Chính sách `CallerRunsPolicy` có thể khiến tác vụ bị từ chối được thực hiện ngay trên caller thread thay vì trong pool. Đây là một hình thức backpressure nhưng **có thể làm request thread chạy SMTP đồng bộ**, trái với kỳ vọng độ trễ.

Nếu mục tiêu là request nhanh và tải có giới hạn, cần một chiến lược saturation rõ ràng: từ chối có kiểm soát, ghi job bền vững, trả trạng thái phù hợp, hoặc chấp nhận backpressure. Không che giấu cơ chế này bằng việc chỉ tăng queue vô hạn.

## 8. Ví dụ hoàn chỉnh: Spring Mail với @Async đúng ranh giới

Giả sử ứng dụng muốn gửi email xác nhận đơn hàng. Chúng ta tách:

- `OrderNotificationService`: nhận yêu cầu nghiệp vụ, xác định người nhận và tạo snapshot nội dung.
- `AsyncMailWorker`: một Spring bean khác, chứa method `@Async`.
- `JavaMailSender`: thực hiện SMTP blocking bên trong worker thread.
- `mailExecutor`: quản lý các worker thread và queue.

### 8.1. Phụ thuộc Spring Mail

Trong Spring Boot với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

`@EnableAsync`, `@Async` và `ThreadPoolTaskExecutor` thuộc các module Spring framework liên quan mà ứng dụng Spring Boot thông thường đã cung cấp. Không cần thêm một thư viện mail bất đồng bộ riêng chỉ để dùng `@Async`.

### 8.2. Dữ liệu đầu vào bất biến

~~~java
public record OrderMailCommand(
        String recipient,
        String customerName,
        String orderCode) {
}
~~~

Đây là snapshot dữ liệu mà worker dùng để gửi email. Các giá trị cần được xác minh trước khi đưa vào command: recipient thuộc đúng người nhận, orderCode được lấy từ domain có thẩm quyền và customerName phù hợp quy tắc nghiệp vụ. Không lưu một mutable JPA entity hoặc HTTP request object vào command để thread nền dùng sau.

### 8.3. Async mail worker

~~~java
import java.util.concurrent.CompletableFuture;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncMailWorker {

    private final JavaMailSender mailSender;

    public AsyncMailWorker(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public CompletableFuture<Void> sendOrderConfirmation(
            OrderMailCommand command) {

        try {
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");

            helper.setFrom("orders@example.org");
            helper.setTo(command.recipient());
            helper.setSubject(
                    "Đơn hàng " + command.orderCode()
                    + " đã được xác nhận"
            );

            String body = """
                    Xin chào %s,

                    Đơn hàng %s đã được xác nhận.
                    Cảm ơn bạn đã sử dụng dịch vụ.
                    """.formatted(
                    command.customerName(),
                    command.orderCode()
            );

            helper.setText(body);
            mailSender.send(message);

            // Giá trị hoàn thành từ body; proxy quản lý
            // CompletableFuture mà caller nhận được.
            return CompletableFuture.completedFuture(null);

        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Không thể chuẩn bị MIME message", ex
            );
        }
    }
}
~~~

Đây là ví dụ gửi `text/plain` để tập trung vào async boundary. Với HTML và plain text song song, có thể dùng helper ở chế độ multipart và `setText(plainText, htmlText)`. Khi dùng HTML, escape dữ liệu động đúng ngữ cảnh hoặc dùng template engine có escaping thích hợp.

`JavaMailSender.send(message)` có thể ném `MailException` không kiểm tra; exception đó sẽ xảy ra trên worker thread và cần được quan sát qua future hoặc cơ chế báo lỗi phù hợp.

### 8.4. Application service gọi qua proxy

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.stereotype.Service;

@Service
public class OrderNotificationService {

    private final AsyncMailWorker mailWorker;

    public OrderNotificationService(AsyncMailWorker mailWorker) {
        this.mailWorker = mailWorker;
    }

    public CompletableFuture<Void> notifyConfirmedOrder(
            String verifiedRecipient,
            String customerName,
            String orderCode) {

        OrderMailCommand command = new OrderMailCommand(
                verifiedRecipient,
                customerName,
                orderCode
        );

        // Gọi sang bean khác: lời gọi đi qua proxy.
        return mailWorker.sendOrderConfirmation(command);
    }
}
~~~

`OrderNotificationService` không tự gọi method `@Async` trong cùng instance. Bean `AsyncMailWorker` được Spring inject và được proxy theo cấu hình. Điều đó làm ranh giới chuyển sang executor rõ ràng.

Ở code thật, application service nên tải và kiểm tra dữ liệu từ domain/repository, áp dụng authorization/recipient policy trước khi tạo command. Không xem tham số tên `verifiedRecipient` là bằng chứng kiểm tra đã được thực thi.

### 8.5. Caller quan sát future

~~~java
CompletableFuture<Void> future =
        orderNotificationService.notifyConfirmedOrder(
                recipient,
                customerName,
                orderCode
        );

future.whenComplete((ignored, error) -> {
    if (error != null) {
        // Ghi nhận lỗi với request ID, không log credential
        // hoặc toàn bộ nội dung email.
        reportMailFailure(error);
    }
});
~~~

`whenComplete` không bắt buộc caller phải chờ, nhưng cho phép quan sát kết quả về sau. Callback có thể chạy trên thread hoàn thành future hoặc thread đăng ký callback nếu future đã hoàn tất, tùy thời điểm; không giả định callback luôn chạy trên request thread.

Với tác vụ cần đảm bảo được theo dõi bền vững, future nằm trong bộ nhớ tiến trình chưa đủ. Khi ứng dụng restart, future và queue trong process không được tự phục hồi.

## 9. Kiểu trả về của phương thức @Async

Spring hỗ trợ những kiểu trả về đặc trưng cho method async, phổ biến nhất là:

- `void`: caller không nhận future để theo dõi hoàn thành.
- `Future<T>`: caller có thể chờ và lấy kết quả.
- `CompletableFuture<T>`: caller có thể kết hợp callback và xử lý lỗi theo kiểu completion stage.

Ví dụ:

~~~java
@Async("mailExecutor")
public void sendNotice(NoticeCommand command) {
    // Gửi mail; caller không có future để quan sát.
}
~~~

~~~java
@Async("mailExecutor")
public CompletableFuture<String> sendWithReference(
        NoticeCommand command) {

    String providerReference = sendAndGetReference(command);
    return CompletableFuture.completedFuture(providerReference);
}
~~~

Một phương thức `@Async` khai báo trả `String` trực tiếp không đúng hợp đồng return type của Spring async interceptor:

~~~java
// Không phù hợp với Spring @Async:
@Async("mailExecutor")
public String sendMail(NoticeCommand command) {
    return "sent";
}
~~~

Chọn `CompletableFuture<Void>` khi không cần giá trị nhưng cần trạng thái hoàn thành hoặc thất bại.

### 9.1. Vì sao body trả completedFuture ngay sau gửi?

Trong ví dụ worker, `JavaMailSender.send` chạy trên thread của executor. Sau khi gửi xong, method trả `CompletableFuture.completedFuture(null)`. Đó là **kết quả tạm của method body** để khớp chữ ký. Future mà caller nhận được là future do Spring async infrastructure tạo/quản lý để phản ánh việc thực thi tác vụ nền.

Không cần tự gọi `CompletableFuture.runAsync(...)` bên trong phương thức đã có `@Async` chỉ để tạo thêm một thread pool khác. Việc lồng hai cơ chế có thể làm khó xác định executor, trace lỗi và kiểm soát saturation.

### 9.2. Future hoàn thành có nghĩa gì?

Nếu worker hoàn thành bình thường sau `mailSender.send`, future thường biểu thị **thao tác gửi ở tầng ứng dụng đã hoàn tất**. Nó không chứng minh email đã được giao vào inbox hoặc đã được người nhận mở.

Nhiều SMTP relay chỉ xác nhận đã chấp nhận message để xử lý tiếp. Bounce hoặc delivery failure có thể xảy ra sau đó. Cần cơ chế provider callback, bounce handling hoặc hệ thống theo dõi delivery nếu sản phẩm cần biết trạng thái phát thực tế.

## 10. Ngoại lệ khi dùng @Async: caller không bắt được như lời gọi đồng bộ

Một ví dụ dễ gây hiểu lầm:

~~~java
try {
    mailWorker.sendOrderConfirmation(command);
} catch (MailException ex) {
    // Không phải nơi bắt các lỗi SMTP xảy ra về sau
    // bên trong executor thread.
}
~~~

Nếu lời gọi đã được chuyển sang executor, exception từ `JavaMailSender.send` xảy ra sau đó trên worker thread. `try/catch` quanh lời gọi lên lịch không tự bắt được lỗi bất đồng bộ.

Phân biệt hai nhóm:

| Nhóm lỗi | Thời điểm | Cách quan sát |
| --- | --- | --- |
| Lỗi lên lịch / executor reject | Trong lúc caller giao task | Có thể xuất hiện ngay tại caller |
| Lỗi chạy trong async method | Trên worker thread | Future exceptional completion, handler hoặc ghi nhận trạng thái job |
| Lỗi SMTP gửi tạm thời | Khi worker gọi `send` | Xử lý qua future/job và retry policy |
| Bounce sau khi relay đã nhận | Sau phản hồi SMTP ban đầu | Provider feedback/bounce processing riêng |

### 10.1. Trường hợp trả CompletableFuture

~~~java
CompletableFuture<Void> future =
        mailWorker.sendOrderConfirmation(command);

future.exceptionally(error -> {
    recordFailure(command.orderCode(), error);
    return null;
});
~~~

Đây là cách quan sát lỗi của future trong cùng tiến trình. Không nên bỏ qua future trong những luồng mà lỗi gửi phải được phát hiện.

Nếu dùng `join()` hoặc `get()` ngay trong controller để đợi hoàn thành, caller sẽ chờ kết quả và làm mất lợi ích về latency của bất đồng bộ. Có thể chờ có chủ đích trong một số use case, nhưng cần hiểu lựa chọn đó.

### 10.2. Trường hợp trả void

Với `@Async void`, caller không có future. Spring có cơ chế `AsyncUncaughtExceptionHandler` để xử lý các exception không được bắt từ method trả `void`. Nếu không cấu hình, framework có thể dùng handler mặc định để log exception.

Có thể cấu hình một handler phù hợp bằng `AsyncConfigurer`:

~~~java
@Configuration
@EnableAsync
public class AsyncErrorConfiguration
        implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler
    getAsyncUncaughtExceptionHandler() {

        return (error, method, params) -> {
            // Ghi log/metric có kiểm soát;
            // tránh dump params chứa token hoặc PII.
            recordAsyncFailure(method.getName(), error);
        };
    }
}
~~~

`recordAsyncFailure` là hàm minh họa do ứng dụng tự cài đặt. Handler này không tự biến task thành durable job, không thay thế retry và không nhận exception như một giá trị trả về cho HTTP request đã hoàn thành.

Nếu mail cần theo dõi thất bại một cách rõ ràng, dùng `CompletableFuture` hoặc job record bền vững thường dễ thiết kế hơn việc chỉ dựa vào log của `void`.

## 11. @Async không kế thừa transaction của caller

Một thread khác không tự mang theo transaction của request thread. Ví dụ:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    orderRepository.markConfirmed(orderId);
    mailWorker.sendOrderConfirmation(createCommand(orderId));
}
~~~

Nếu `mailWorker` được gọi qua async proxy, executor có thể bắt đầu chạy **trước khi transaction của `confirmOrder` commit**. Vì thế:

- Worker có thể đọc trạng thái cũ nếu query database lại.
- Đơn hàng chưa commit có thể chưa hiển thị cho transaction khác.
- Caller rollback sau khi task đã được giao, nhưng email vẫn có thể đã gửi.
- Có thể gửi email thông báo thành công cho một nghiệp vụ cuối cùng bị rollback.

Đây là lỗi về **ranh giới transaction và thời điểm side effect**, không chỉ là lỗi thread.

~~~mermaid
sequenceDiagram
    participant C as Application service
    participant DB as Database
    participant E as Async executor
    participant S as SMTP
    C->>DB: Update order trong transaction
    C->>E: Schedule mail
    E->>S: Có thể gửi trước commit
    C-->>DB: Commit hoặc rollback về sau
~~~

### 11.1. @Transactional trên worker không “mang transaction sang”

Có thể đặt `@Transactional` trên một phương thức được gọi qua proxy ở worker thread để **tạo transaction riêng tại nơi thực thi**, tùy cấu hình Spring và thứ tự advice. Nhưng đó không phải cùng transaction đang mở trên request thread.

Không nên giữ một transaction database mở trong suốt thời gian SMTP blocking nếu không cần thiết. Thường tốt hơn là đọc dữ liệu cần thiết thành snapshot, kết thúc transaction, rồi gửi mail ngoài transaction.

### 11.2. Sau commit và outbox

Nếu chỉ gửi sau khi giao dịch thành công, có thể tổ chức luồng theo sự kiện sau commit. Ví dụ Spring hỗ trợ `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` cho listener được kích hoạt khi giao dịch đã commit. Có thể kết hợp xử lý bất đồng bộ theo cấu hình đúng, nhưng cần hiểu listener after-commit chỉ làm thay đổi thời điểm xử lý, **không bảo đảm job tồn tại khi process chết**.

Với yêu cầu không được bỏ sót thông báo, mô hình **transactional outbox** thường phù hợp hơn:

1. Trong cùng transaction với thay đổi nghiệp vụ, lưu một outbox record.
2. Commit database.
3. Worker đọc outbox record đã commit.
4. Resolve dữ liệu cần thiết, render và gửi.
5. Cập nhật trạng thái, retry theo chính sách, tránh gửi trùng khi có thể.

Outbox cũng có vấn đề giao hàng “at least once” và cần idempotency; không nên tuyên bố nó bảo đảm SMTP gửi đúng một lần tuyệt đối.

## 12. Thread context: SecurityContext, MDC và request data

Spring và nhiều thư viện dùng `ThreadLocal` để lưu context gắn với thread, ví dụ:

- Security context của người dùng đang đăng nhập.
- MDC/trace ID cho logging.
- Request attributes.
- Transaction context.
- Locale hoặc các thông tin khác được ràng buộc với thread.

Khi chuyển từ request thread sang executor thread, **không được giả định toàn bộ thread-local context tự động đi theo**.

Ví dụ lỗi tiềm ẩn:

~~~java
@Async("mailExecutor")
public void sendNotice(UUID orderId) {
    Authentication auth =
            SecurityContextHolder.getContext()
                    .getAuthentication();

    // auth có thể không có hoặc không phải context mong đợi.
}
~~~

Tương tự, đọc `RequestContextHolder.currentRequestAttributes()` trong background worker có thể thất bại vì HTTP request đã kết thúc.

### 12.1. Truyền dữ liệu cần thiết qua command

Một cách dễ hiểu là truyền dữ liệu đã xác định trước khi dispatch:

~~~java
public record MailJobCommand(
        UUID orderId,
        UUID requestedBy,
        UUID recipientContactId,
        Locale locale,
        String correlationId) {
}
~~~

Application service kiểm tra quyền và lấy thông tin cần thiết trước khi giao việc. Nếu worker cần kiểm tra lại quyền hoặc recipient policy tại thời điểm gửi, nó có thể tải dữ liệu qua ID có thẩm quyền, thay vì phụ thuộc vào SecurityContext gắn với request thread.

Không đưa password, session token hoặc toàn bộ principal vào command chỉ để “giữ context”.

### 12.2. Khi cần propagation có chủ đích

Spring Security có những wrapper executor như `DelegatingSecurityContextAsyncTaskExecutor` để truyền security context theo cấu hình cụ thể. Logging có thể dùng `TaskDecorator` hoặc cơ chế observability để chuyển một số metadata như correlation ID.

Propagation phải là quyết định có chủ đích, xét tới quyền riêng tư, tuổi đời context và nguy cơ tái sử dụng thread. Không mặc định rằng mọi `ThreadLocal` đều phù hợp để sao chép sang worker.

### 12.3. Đừng đọc dữ liệu request sau khi dispatch

Một `MultipartFile`, `HttpServletRequest`, input stream hoặc entity gắn persistence context có thể không còn hợp lệ khi request đã hoàn thành. Với email có attachment, trước khi giao việc nên lưu file vào storage được quản lý, kiểm tra quyền và pass một file ID/storage key có thể resolve lại.

## 13. Ranh giới dữ liệu bất biến giữa các thread

Vì caller và worker chạy ở các thời điểm khác nhau, object truyền qua async boundary nên có hợp đồng rõ ràng và hạn chế mutable state.

Ví dụ không lý tưởng:

~~~java
public void requestMail(MutableOrderDto dto) {
    mailWorker.send(dto);
    dto.setRecipient("another@example.org");
}
~~~

Nếu worker bắt đầu sau khi caller sửa object, nội dung/recipient có thể khác với thời điểm yêu cầu gửi. Đây là race condition do chia sẻ mutable object.

Dùng một snapshot bất biến:

~~~java
public record MailSnapshot(
        String recipient,
        String subject,
        String plainText,
        String html) {
}
~~~

~~~java
MailSnapshot snapshot = new MailSnapshot(
        approvedRecipient,
        subject,
        plainText,
        html
);

mailWorker.send(snapshot);
~~~

Nếu record chứa `List` hoặc object mutable, cần defensive copy:

~~~java
public record BulkMailCommand(
        List<String> recipientAddresses,
        String messageCode) {

    public BulkMailCommand {
        recipientAddresses = List.copyOf(recipientAddresses);
    }
}
~~~

`List.copyOf` tạo list không sửa đổi được qua reference đó, nhưng không làm các object phần tử trở nên bất biến nếu chúng có trạng thái mutable. Nên dùng value object/ID cho dữ liệu đi qua ranh giới async.

## 14. Transaction và việc gửi email thuộc hai hệ thống khác nhau

Một số người hiểu sai rằng thêm `@Transactional` vào service gửi mail sẽ khiến SMTP rollback cùng database. Điều này không đúng với SMTP thông thường.

Database transaction quản lý thay đổi trong database. Lời gọi `JavaMailSender.send(...)` là side effect tới SMTP relay, không tham gia transaction database theo kiểu có thể rollback cùng database.

Ví dụ nếu SMTP relay đã chấp nhận mail nhưng sau đó transaction DB rollback, hệ thống không thể tự “thu hồi” mail bằng rollback.

Do đó cần quyết định:

- Email nào chỉ là best-effort notification?
- Email nào phải gắn với trạng thái đã commit?
- Email nào cần retry và audit bền vững?
- Email nào không được gửi trùng hoặc cần deduplication?
- Dữ liệu hiển thị cần snapshot tại thời điểm nào?

`@Async` chỉ giải quyết việc giao công việc cho executor thread. **Nó không thay thế thiết kế consistency giữa database và hệ thống gửi thư.**

## 15. Những giới hạn vận hành của @Async

### 15.1. Hàng đợi nằm trong bộ nhớ

`ThreadPoolTaskExecutor` sử dụng thread pool và queue trong process JVM. Khi ứng dụng bị kill, host restart hoặc deploy mới, công việc đang chờ chưa chắc được giữ lại hay tự phát lại. Cấu hình graceful shutdown có thể đợi một số task trong điều kiện shutdown bình thường nhưng không bảo đảm tồn tại qua mất điện hoặc crash.

Nếu thông báo quan trọng phải có khả năng phục hồi, cần persisted job/outbox hoặc message broker theo yêu cầu.

### 15.2. Tốc độ producer và SMTP provider

HTTP request có thể tạo công việc nhanh hơn SMTP relay xử lý. Queue có thể tăng, độ trễ gửi kéo dài hoặc executor reject task. Không nên chỉ tăng số thread để “đẩy nhanh” khi provider có quota/throttling; có thể làm tăng lỗi tạm thời và tải hệ thống.

Cần đặt giới hạn đồng thời, queue capacity, rate limit và retry có backoff.

### 15.3. SMTP timeout

Nếu một worker mắc kẹt lâu trong thao tác kết nối hoặc ghi dữ liệu, thread pool có thể bị chiếm hết. Nên cấu hình timeout của mail transport:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

Hostname minh họa cần thay bằng SMTP relay thật. Các biến môi trường cần được quản lý bằng secret handling phù hợp; không commit credential vào mã nguồn. Timeout là giá trị ví dụ (mili giây), phải phù hợp đặc tính mạng và provider.

### 15.4. Theo dõi trạng thái

Nên đo:

- Số task active và queue size của executor.
- Số task được nhận/từ chối.
- Thời gian chờ trong queue.
- Thời gian chuẩn bị MIME và thời gian SMTP.
- Số mail send success/failure theo loại.
- Loại lỗi tạm thời/vĩnh viễn, số lần retry.
- Thời gian từ event nghiệp vụ tới khi request gửi được relay chấp nhận.

Không ghi SMTP password, token email, toàn bộ nội dung thư hoặc thông tin cá nhân vào log chỉ để debug.

## 16. Khi nào @Async là đủ, khi nào cần queue/outbox?

| Yêu cầu | `@Async` với executor | Queue/outbox bền vững |
| --- | --- | --- |
| Muốn HTTP trả nhanh hơn SMTP | Phù hợp | Phù hợp nhưng phức tạp hơn |
| Số lượng mail nhỏ, chấp nhận mất vài notification khi crash | Thường đủ | Có thể quá mức |
| Cần phục hồi job sau restart | Không tự bảo đảm | Thiết kế để đáp ứng |
| Cần retry với lịch, backoff và audit | Phải tự triển khai thêm | Dễ tổ chức hơn với persisted state |
| Cần theo dõi trạng thái theo request ID | Future trong process hoặc hệ thống phụ | Job record rõ ràng |
| Cần chống gửi trùng qua redelivery | Không tự bảo đảm | Vẫn phải thiết kế idempotency |
| Cần giới hạn tải SMTP | Executor + rate limiting | Worker concurrency + queue controls |

**Không có một giải pháp đúng cho mọi hệ thống.** Với email thông báo không quan trọng và lưu lượng thấp, `@Async` có thể đủ. Với xác nhận giao dịch quan trọng, hóa đơn, thông báo phải theo dõi hoặc có nghĩa vụ vận hành, persisted outbox/job thường đáng cân nhắc.

Một luồng outbox có thể vẫn dùng `@Async` nội bộ để tăng concurrency ở worker, nhưng khi đó outbox mới là nguồn trạng thái bền vững. Không nhầm hai vai trò này.

## 17. Controller trả HTTP gì khi gửi bất đồng bộ?

Khi controller gọi application service và service giao tác vụ cho executor, cần diễn đạt response đúng mức bảo đảm.

Ví dụ controller:

~~~java
@PostMapping("/orders/{id}/email-confirmation")
public ResponseEntity<Void> requestMail(
        @PathVariable UUID id,
        @AuthenticationPrincipal AppPrincipal principal) {

    notificationService.requestConfirmation(
            id,
            principal.userId()
    );

    return ResponseEntity.accepted().build();
}
~~~

HTTP `202 Accepted` có thể phù hợp để nói **yêu cầu đã được tiếp nhận để xử lý**, không phải email đã phát thành công tới inbox.

Tuy nhiên:

- Nếu chỉ gọi `@Async` và queue trong bộ nhớ, “accepted” không đồng nghĩa persisted job.
- Nếu executor reject ngay khi submit, controller không nên vẫn trả 202 như thể job đã được nhận.
- Nếu policy từ chối recipient hoặc actor không có quyền, phải trả kết quả phù hợp với lỗi nghiệp vụ.
- Nếu client cần tra cứu trạng thái về sau, nên có request/job ID và endpoint đọc trạng thái từ storage.
- Nếu dùng transaction/outbox, điểm trả 202 cần phù hợp thời điểm commit thành công.

Không gọi `future.join()` ngay trước khi trả response nếu mục tiêu là không chờ SMTP. Khi ứng dụng thực sự cần xác nhận hoàn tất gửi ở thời điểm HTTP response, hãy cân nhắc lời gọi đồng bộ hoặc một hợp đồng API khác.

## 18. Kiểm thử đúng ranh giới proxy

Có thể kiểm thử chức năng email ở ba mức khác nhau.

### 18.1. Unit test method body

Tạo `AsyncMailWorker` bằng constructor thông thường rồi gọi method:

~~~java
AsyncMailWorker worker = new AsyncMailWorker(fakeMailSender);
worker.sendOrderConfirmation(command);
~~~

Test này có thể kiểm tra logic dựng MIME, nhưng **không kiểm tra `@Async` đã hoạt động**. Object được tạo bằng `new` không qua Spring proxy.

### 18.2. Spring integration test kiểm tra thread boundary

Một test chạy với Spring context và `@EnableAsync` có thể inject bean async đã được proxy. Dùng một executor riêng trong môi trường test hoặc một đối tượng đồng bộ hóa như `CountDownLatch` để quan sát thread.

Ví dụ phần thân một bean phục vụ test:

~~~java
@Service
public class AsyncProbe {

    @Async("mailExecutor")
    public CompletableFuture<String> threadName() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName()
        );
    }
}
~~~

Test khi inject Spring bean:

~~~java
@Autowired
AsyncProbe asyncProbe;

@Test
void runsOnExecutorThread() {
    String thread = asyncProbe.threadName().join();

    assertTrue(thread.startsWith("mail-worker-"));
}
~~~

Ví dụ giả định executor test dùng prefix `mail-worker-`. Trong một hệ thống chạy test với nhiều executor, cần cấu hình test context kiểm soát rõ bean được chọn. Kiểm tra tên thread chỉ là cách minh họa; synchronization/latch có thể cung cấp kiểm chứng mạnh hơn khi cần xác nhận non-blocking behavior.

### 18.3. Test self-invocation

Có thể đặt một phương thức gọi nội bộ và đo thread hoặc thời điểm hoàn thành để chứng minh self-invocation không qua proxy trong chế độ mặc định.

Ví dụ:

~~~java
@Service
public class SelfInvocationExample {

    public String callInternally() {
        return annotatedMethod();
    }

    @Async("mailExecutor")
    public CompletableFuture<String> annotatedMethod() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName()
        );
    }
}
~~~

Ví dụ trên minh họa kiểu trả về `CompletableFuture` nhưng `callInternally` phải xử lý future chứ không trả thẳng chuỗi; một phiên bản hợp lệ:

~~~java
public CompletableFuture<String> callInternally() {
    return annotatedMethod(); // Bỏ qua proxy ở self-call.
}
~~~

Khi test, so sánh lời gọi `callInternally()` với `annotatedMethod()` qua bean proxy và quan sát thread. Mục tiêu là nhận biết **đường đi của lời gọi**, không phải chỉ thấy annotation trong mã nguồn.

### 18.4. Test SMTP không cần gửi thư thật

Tách kiểm thử proxy boundary khỏi kiểm thử SMTP. Có thể dùng fake `JavaMailSender`, SMTP test server hoặc test mail transport phù hợp để xác nhận MIME, subject, recipient và xử lý lỗi. Không để integration test vô tình gửi email tới địa chỉ production.

## 19. Những hiểu lầm phổ biến

### 19.1. “Cứ gắn @Async là method sẽ luôn chạy nền”

Sai với proxy mode. Phương thức phải được gọi qua proxy của Spring. Self-invocation và object tạo bằng `new` bỏ qua cơ chế đó.

### 19.2. “Gọi method @Async từ method khác trong cùng class là được”

Thường không. Lời gọi nội bộ dùng `this`, không qua proxy. Tách bean async worker để lời gọi được intercept.

### 19.3. “Gắn @Async trên private method vẫn được”

Private method không phải điểm vào hợp lệ để proxy thông thường intercept. Nên dùng public non-final method của Spring-managed bean.

### 19.4. “Spring Boot đã có mail starter thì @Async tự bật”

Không nên giả định như vậy. Cần bật async support bằng `@EnableAsync` trong cấu hình phù hợp.

### 19.5. “@Async giúp SMTP send trở thành non-blocking”

Không. `JavaMailSender.send` vẫn blocking trên executor thread. Nó chỉ không chặn caller thread sau khi task được dispatch.

### 19.6. “Future completed nghĩa người nhận đã nhận thư”

Không. Nó chỉ phản ánh kết quả thao tác application/SMTP relay ở thời điểm tương ứng; delivery cuối cùng có thể xảy ra sau đó.

### 19.7. “try/catch quanh lời gọi @Async bắt được lỗi SMTP sau này”

Không. Lỗi trong executor thread không tự quay về call stack đồng bộ. Quan sát `CompletableFuture` hoặc trạng thái job; xử lý rejection lúc submit riêng.

### 19.8. “@Transactional từ controller tự đi theo worker thread”

Không. Transaction context không tự di chuyển giữa thread. Worker có thể chạy trước commit và đọc dữ liệu cũ hoặc gửi trước khi caller rollback.

### 19.9. “SecurityContext và RequestContextHolder luôn còn trong worker”

Không. Các thread-local context không tự truyền theo. Dùng command rõ dữ liệu hoặc propagation được cấu hình có chủ đích.

### 19.10. “Executor queue lớn nghĩa hệ thống xử lý khỏe hơn”

Không nhất thiết. Queue lớn có thể làm tăng thời gian chờ và giữ nhiều object trong bộ nhớ, trong khi SMTP provider vẫn là nút thắt cổ chai.

### 19.11. “@Async có hàng đợi bền vững”

Không. Queue thông thường của executor nằm trong process. Crash hoặc restart có thể mất công việc chưa xử lý.

### 19.12. “Gọi method @Async trong @PostConstruct là cách khởi chạy nền đáng tin cậy”

Không nên. Việc khởi tạo bean và áp dụng proxy có trình tự lifecycle riêng; self-call ở giai đoạn khởi tạo không phải đường đi hợp lệ qua proxy. Nếu cần khởi động công việc sau khi app sẵn sàng, dùng lifecycle hook/event phù hợp và một Spring bean khác gọi qua proxy.

### 19.13. “Đặt maxPoolSize lớn là giải quyết saturation”

Không. Với queue capacity dương, pool có thể chờ queue đầy trước khi tăng quá core size. Cần hiểu mô hình queue, giới hạn provider, timeout và backpressure.

## 20. Tình huống thực hành

**Tình huống A — Đơn hàng được xác nhận trong transaction**

Service thực hiện:

~~~java
@Transactional
public void confirm(UUID id) {
    orderRepository.confirm(id);
    mailWorker.sendOrderConfirmation(createCommand(id));
}
~~~

Điều gì có thể sai?

Worker có thể chạy trước commit và gửi dựa trên trạng thái chưa được xác nhận bền vững. Nếu transaction rollback, email có thể đã gửi. Với yêu cầu quan trọng, dùng after-commit event hoặc outbox được thiết kế đúng semantics.

**Tình huống B — @Async nằm trong cùng class**

~~~java
public void createAndNotify() {
    notifyAsync();
}

@Async("mailExecutor")
public void notifyAsync() {
    // ...
}
~~~

Vì sao lời gọi có thể chạy đồng bộ?

Vì đó là self-invocation, đi qua `this` thay vì proxy. Chuyển `notifyAsync` sang bean worker và inject worker vào service.

**Tình huống C — Gọi qua new**

~~~java
MailWorker worker = new MailWorker(mailSender);
worker.sendOrderConfirmation(command);
~~~

`@Async` có tự hoạt động không?

Không theo Spring proxy mode, vì object này không được Spring quản lý và không phải proxy.

**Tình huống D — Executor bị quá tải**

Nếu queue đầy và executor reject, caller có được trả 202 vô điều kiện không?

Không. Cần xử lý rejection và chọn HTTP response/trạng thái job phù hợp; không báo đã tiếp nhận công việc nếu thực tế chưa được nhận.

**Tình huống E — Controller cần báo kết quả ngay**

Controller gọi `future.join()` trước khi trả response. Điều đó có còn non-blocking đối với request không?

Không. Request thread chờ future hoàn thành. Đây có thể là lựa chọn có chủ đích nhưng mất lợi ích về latency của chuyển SMTP sang worker.

**Tình huống F — Method trả void**

Nếu SMTP ném exception trên worker thread, nơi nào quan sát được?

Không phải `try/catch` thông thường tại caller. Có thể dùng `AsyncUncaughtExceptionHandler` và logging/metrics; nếu cần theo dõi có cấu trúc, chọn `CompletableFuture` hoặc persisted job.

**Tình huống G — Worker cần user ID**

Nên đọc `SecurityContextHolder` trong worker hay truyền ID vào command?

Thường nên truyền một ID và metadata đã được xác định/ủy quyền tại application boundary, rồi kiểm tra lại khi cần. Không giả định request-thread context đã đi theo executor.

**Tình huống H — Ảnh đính kèm từ request**

Controller truyền `MultipartFile` trực tiếp cho worker rồi trả HTTP 202. Có rủi ro gì?

Dữ liệu upload có thể phụ thuộc vòng đời request hoặc stream đã đóng. Cần kiểm tra, lưu vào storage được quản lý và truyền file ID để worker đọc lại; không giữ tham chiếu tới request-scoped resource.

**Tình huống I — Nhà cung cấp SMTP giới hạn số message**

Có nên tăng pool lên 100 thread để gửi nhanh hơn?

Không mặc định. Nếu provider giới hạn tốc độ, nhiều thread hơn có thể gây throttling/rejection. Cần rate limiting, concurrency control và retry phù hợp.

**Tình huống J — Ứng dụng restart khi queue còn 500 mail**

`@Async` có tự tiếp tục gửi 500 mail sau restart không?

Không. Với executor thông thường, queue chỉ ở bộ nhớ. Muốn phục hồi cần persisted jobs, outbox hoặc message broker theo thiết kế.

## 21. Mô hình ranh giới cần ghi nhớ

~~~mermaid
flowchart TD
    A["HTTP / Event / Scheduler"] --> B["Application service"]
    B --> C["Validate quyền, recipient, dữ liệu"]
    C --> D["Snapshot command"]
    D --> E["Spring bean proxy"]
    E --> F["Async interceptor"]
    F --> G["mailExecutor"]
    G --> H["AsyncMailWorker"]
    H --> I["JavaMailSender.send (blocking)"]
    I --> J["SMTP relay"]
    E -. "Future / kết quả lên lịch" .-> B
~~~

Các nguyên tắc cốt lõi:

1. **`@Async` trong Spring proxy mode cần lời gọi qua proxy.** Annotation không tác động lên self-invocation hay object tạo bằng `new`.
2. **Tách worker thành Spring bean riêng**, gọi từ application service qua dependency injection để ranh giới bất đồng bộ rõ ràng.
3. **Dùng `@EnableAsync` và executor có giới hạn**, ưu tiên executor riêng cho mail nếu cần quản lý tải.
4. **SMTP vẫn blocking trên worker thread**; xử lý timeout, saturation và rate limit.
5. **Chọn return type phù hợp**: `void` cho fire-and-forget có xử lý lỗi riêng, `CompletableFuture` để quan sát hoàn thành/thất bại.
6. **Phân biệt lỗi schedule với lỗi runtime**; exception trong worker không tự bị bắt bởi caller.
7. **Transaction, SecurityContext, MDC và request data không tự chuyển thread**; quyết định rõ snapshot, propagation và thời điểm commit.
8. **Không dùng `@Async` như một durable queue**; với nhu cầu phục hồi/retry/audit quan trọng, dùng persisted job hoặc outbox.
9. **Kiểm thử qua Spring context** khi muốn xác nhận proxy thật sự được áp dụng; gọi đối tượng tạo bằng `new` chỉ test method body.
10. **Không coi “SMTP accepted” là “delivered”**; future và kết quả gửi chỉ phản ánh trạng thái ở tầng tương ứng.

Trong ứng dụng Spring Framework Mail, hãy để application service quyết định **gửi email gì, cho ai và sau trạng thái nghiệp vụ nào**, rồi giao một command rõ dữ liệu cho `AsyncMailWorker` qua Spring proxy. `@Async` và `TaskExecutor` chuyển công việc sang worker thread; `JavaMailSender` thực hiện SMTP; còn cơ chế job/outbox và monitoring quyết định khả năng phục hồi, theo dõi và retry khi hệ thống vận hành thực tế.
