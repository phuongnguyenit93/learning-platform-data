# Không tự gọi phương thức @Async trong cùng bean

Trong Spring Framework Mail, gửi email là một thao tác I/O: ứng dụng phải tạo nội dung MIME, kết nối tới SMTP server hoặc dịch vụ gửi thư, truyền dữ liệu và chờ phản hồi từ transport. Nếu làm tất cả trong luồng xử lý HTTP request, thời gian phản hồi có thể tăng đáng kể khi SMTP chậm hoặc mạng gặp sự cố. Spring hỗ trợ **@Async** để chuyển lời gọi phương thức sang một **TaskExecutor**, giúp luồng gọi không phải chờ toàn bộ thao tác gửi mail.

Tuy nhiên, có một lỗi rất phổ biến: **một phương thức trong bean gọi trực tiếp một phương thức khác có @Async của chính bean đó**. Dù phương thức được đánh dấu @Async, lời gọi nội bộ này thường vẫn **chạy đồng bộ trong thread hiện tại**, vì không đi qua Spring AOP proxy.

Bài học giải thích nguyên nhân self-invocation, cách sửa bằng cách tách tác vụ gửi mail sang bean riêng, cách cấu hình executor và kiểm tra phương thức thực sự chạy bất đồng bộ, cùng các lưu ý về transaction, exception, ThreadLocal và độ tin cậy khi gửi email.

## 1. Vấn đề: có @Async nhưng gửi mail vẫn chặn request

Giả sử service đăng ký tài khoản vừa lưu người dùng vừa gửi thư chào mừng:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final UserRepository userRepository;
    private final JavaMailSender mailSender;

    public RegistrationService(
            UserRepository userRepository,
            JavaMailSender mailSender
    ) {
        this.userRepository = userRepository;
        this.mailSender = mailSender;
    }

    public void register(RegisterCommand command) {
        User user = userRepository.save(User.from(command));

        // Gọi phương thức khác của chính object hiện tại.
        sendWelcomeEmailAsync(user.getEmail());
    }

    @Async("mailExecutor")
    public void sendWelcomeEmailAsync(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("welcome@example.test");
        message.setTo(recipient);
        message.setSubject("Chào mừng");
        message.setText("Tài khoản của bạn đã được tạo.");
        mailSender.send(message);
    }
}
~~~

Các import mail tương ứng:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
~~~

Thoạt nhìn, phương thức **sendWelcomeEmailAsync(...)** đã có @Async, và ứng dụng có thể đã cấu hình executor đúng. Nhưng dòng:

~~~java
sendWelcomeEmailAsync(user.getEmail());
~~~

là lời gọi từ một phương thức tới một phương thức khác trên **cùng instance**. Nó tương đương:

~~~java
this.sendWelcomeEmailAsync(user.getEmail());
~~~

Trong chế độ proxy mặc định của Spring, lời gọi này **không được Spring proxy chặn để chuyển sang executor**. Kết quả là **mailSender.send(...) chạy ngay trên thread đang thực hiện register(...)**. Nếu SMTP mất ba giây để phản hồi, thread hiện tại có thể bị chặn gần ba giây.

### Dấu hiệu nhận biết

Các dấu hiệu thường gặp của lỗi self-invocation:

- Phương thức có @Async nhưng request vẫn chờ tới khi gửi email xong.
- Log bên trong phương thức gửi mail có cùng tên thread với phương thức gọi.
- Exception SMTP xuất hiện trực tiếp trên luồng gọi, thay vì được xử lý bởi cơ chế async.
- Executor đã cấu hình nhưng không thấy task tương ứng được submit.
- Khi gọi phương thức @Async từ **một bean khác**, hành vi lại đúng như mong đợi.

Đây không phải lỗi của JavaMailSender hoặc SMTP. Nguyên nhân nằm ở **đường đi của lời gọi phương thức qua Spring AOP proxy**.

## 2. Spring @Async hoạt động như thế nào?

Với **annotation-driven asynchronous execution** ở chế độ proxy, Spring tạo một proxy quanh bean có phương thức phù hợp với @Async. Khi một component khác gọi phương thức qua proxy:

1. Proxy nhận lời gọi.
2. Interceptor của @Async xác định executor cần dùng.
3. Công việc được submit vào executor.
4. Một worker thread thực hiện phương thức thực tế.
5. Luồng gọi được trả về theo hợp đồng của phương thức async mà không phải chờ tác vụ hoàn tất.

Sơ đồ lời gọi qua proxy:

~~~text
Controller / Service A
         |
         | gọi mailDispatchService.sendAsync(...)
         v
    Spring AOP proxy
         |
         | @Async interceptor
         v
      TaskExecutor
         |
         | submit task
         v
    Worker thread
         |
         v
    Target MailDispatchService
         |
         v
      JavaMailSender
         |
         v
       SMTP
~~~

Đối tượng mà một bean khác nhận được qua dependency injection thường là **proxy**, không nhất thiết là instance đích trực tiếp. Proxy tạo điểm chặn để Spring áp dụng hành vi @Async.

### Vì sao self-invocation bỏ qua proxy?

Khi Spring proxy gọi vào phương thức đích của bean, bên trong phương thức đó, **this** trỏ tới đối tượng đang thực thi logic của bean. Một lời gọi tới phương thức khác trên **this** không phải một lời gọi mới đi từ bên ngoài qua proxy.

~~~text
Service A
    |
    v
Spring proxy của RegistrationService
    |
    v
RegistrationService.register(...)
    |
    | this.sendWelcomeEmailAsync(...)
    v
RegistrationService.sendWelcomeEmailAsync(...)
    |
    v
JavaMailSender.send(...)

Không có lần đi qua @Async interceptor thứ hai.
~~~

Điểm cốt lõi: **@Async không làm thay đổi bản chất một phương thức Java**. Annotation là metadata để hạ tầng Spring áp dụng interceptor khi lời gọi đi qua cơ chế phù hợp. Nếu đi vòng qua proxy, annotation không tự tạo thread mới.

### Có phải cứ phương thức có @Async là chạy trong thread khác?

Không. Cần đồng thời có những điều kiện phù hợp:

- Bean được Spring quản lý.
- Hạ tầng xử lý @Async được kích hoạt.
- Phương thức có chữ ký phù hợp và có thể được proxy intercept.
- Lời gọi đi qua proxy (trong chế độ proxy mặc định).
- Executor chấp nhận task.

Nếu thiếu một trong các điều kiện trên, hành vi thực tế có thể khác kỳ vọng.

## 3. Kiểm tra thread để thấy lỗi xảy ra

Tên thread giúp minh họa đường đi của lời gọi, dù không phải tiêu chí duy nhất để chứng minh async.

~~~java
public void register(RegisterCommand command) {
    log.info(
            "register thread={}",
            Thread.currentThread().getName()
    );

    sendWelcomeEmailAsync(command.email());
}

@Async("mailExecutor")
public void sendWelcomeEmailAsync(String recipient) {
    log.info(
            "sendWelcomeEmailAsync thread={}",
            Thread.currentThread().getName()
    );
    // Gửi thư...
}
~~~

Khi self-invocation bỏ qua proxy, log có thể giống:

~~~text
register thread=http-nio-8080-exec-3
sendWelcomeEmailAsync thread=http-nio-8080-exec-3
~~~

Khi lời gọi đi qua proxy và executor xử lý:

~~~text
register thread=http-nio-8080-exec-3
sendWelcomeEmailAsync thread=mail-1
~~~

Tên thread cụ thể phụ thuộc web server, executor, cấu hình thread factory và môi trường chạy. Không nên viết logic nghiệp vụ phụ thuộc chuỗi tên thread. Test nên kiểm tra tín hiệu hoàn thành, lời gọi executor hoặc hành vi không chặn, thay vì bắt buộc tên thread phải là một chuỗi cố định.

## 4. Cách sửa ưu tiên: tách mail sender sang bean khác

Để tránh self-invocation, tách trách nhiệm **đăng ký tài khoản** và **gửi email bất đồng bộ** thành hai Spring beans. Bean đăng ký gọi bean gửi mail được inject qua Spring; lời gọi được chuyển qua proxy của bean gửi mail.

### Bean thực hiện gửi email

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncWelcomeMailService {

    private final JavaMailSender mailSender;

    public AsyncWelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public void sendWelcomeEmail(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("welcome@example.test");
        message.setTo(recipient);
        message.setSubject("Chào mừng");
        message.setText("Tài khoản của bạn đã được tạo.");

        mailSender.send(message);
    }
}
~~~

### Bean gọi tác vụ async

~~~java
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final UserRepository userRepository;
    private final AsyncWelcomeMailService asyncWelcomeMailService;

    public RegistrationService(
            UserRepository userRepository,
            AsyncWelcomeMailService asyncWelcomeMailService
    ) {
        this.userRepository = userRepository;
        this.asyncWelcomeMailService = asyncWelcomeMailService;
    }

    public void register(RegisterCommand command) {
        User user = userRepository.save(User.from(command));

        // Lời gọi đi qua Spring bean đã được inject.
        asyncWelcomeMailService.sendWelcomeEmail(user.getEmail());
    }
}
~~~

Luồng sau khi tách:

~~~text
RegistrationService.register()
         |
         v
AsyncWelcomeMailService proxy
         |
         v
@Async interceptor
         |
         v
mailExecutor.submit(...)
         |
         v
Worker thread gọi JavaMailSender
~~~

Đây là cách thiết kế dễ hiểu và dễ bảo trì: service nghiệp vụ không cần tự xử lý SMTP, còn mail service có thể nhận test mock và executor riêng.

### Tại sao việc tách bean có ích ngoài @Async?

- **Ranh giới trách nhiệm:** nghiệp vụ đăng ký không phụ thuộc cách tạo MIME message.
- **Dễ test:** có thể mock AsyncWelcomeMailService khi test đăng ký; test gửi mail ở lớp riêng.
- **Dễ giám sát:** các tác vụ mail có executor và logging riêng.
- **Dễ thay thế:** có thể chuyển từ SMTP trực tiếp sang queue/outbox mà ít ảnh hưởng service nghiệp vụ.
- **Tránh vòng phụ thuộc:** không phải self-inject hoặc hỏi ApplicationContext để lấy proxy của chính mình.

**Lưu ý quan trọng:** ví dụ này mới chỉ sửa đúng vấn đề self-invocation. Nếu phương thức đăng ký chạy trong một database transaction và email chỉ được gửi sau commit, cần thêm ranh giới **AFTER_COMMIT**, được giải thích ở phần sau. Tách bean và dùng @Async **không tự bảo đảm transaction đã commit trước khi email được gửi**.

## 5. Bật @Async và cấu hình executor rõ ràng

Để dùng @Async theo cách annotation-driven, ứng dụng cần kích hoạt hạ tầng asynchronous execution. Trong cấu hình Spring Java, có thể dùng **@EnableAsync**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean(name = "mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mail-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.initialize();
        return executor;
    }
}
~~~

Khi phương thức có:

~~~java
@Async("mailExecutor")
public void sendWelcomeEmail(String recipient) {
    // ...
}
~~~

Spring tìm executor với qualifier/tên phù hợp và submit công việc vào đó. Các giá trị **2/8/200** ở trên chỉ minh họa, không phải cấu hình tối ưu sẵn cho mọi dịch vụ gửi mail. Cần điều chỉnh dựa trên tốc độ SMTP, giới hạn kết nối, memory, tải và chính sách provider.

### Ý nghĩa những tham số chính

| Tham số | Ý nghĩa | Cần cân nhắc |
| --- | --- | --- |
| **corePoolSize** | Số worker cốt lõi | Công việc gửi mail chờ I/O có thể cần nhiều worker hơn tác vụ CPU |
| **maxPoolSize** | Số worker tối đa | Giới hạn concurrency, tránh quá tải SMTP/provider |
| **queueCapacity** | Số tác vụ chờ | Queue quá lớn làm tăng độ trễ và sử dụng bộ nhớ |
| **threadNamePrefix** | Tiền tố tên worker | Hữu ích khi đọc log và thread dump |
| **waitForTasksToCompleteOnShutdown** | Chính sách chờ task khi shutdown | Không bảo đảm cứu các task khi process bị kill đột ngột |

Với ThreadPoolTaskExecutor dùng queue có dung lượng dương, executor thường ưu tiên dùng các core workers và xếp task vào queue trước khi mở rộng tới maxPoolSize. Vì vậy, cấu hình queue rất lớn có thể khiến maxPoolSize hiếm khi được sử dụng. Không nên đặt queue vô hạn chỉ để tránh rejection.

### Nếu không cấu hình mailExecutor thì sao?

Một phương thức **@Async("mailExecutor")** cần có executor được Spring resolve theo qualifier đó. Nếu không tìm được executor phù hợp, quá trình thực thi có thể thất bại do cấu hình. Nếu bỏ qualifier và dùng **@Async**, Spring sẽ chọn executor theo cơ chế phân giải mặc định của hạ tầng async. Tùy môi trường và Spring Boot auto-configuration, executor mặc định có thể khác nhau.

Với luồng gửi mail production, **đặt tên executor riêng** thường giúp cấu hình giới hạn tải và theo dõi dễ hơn việc phụ thuộc vào executor dùng chung của ứng dụng.

### Có @EnableAsync không có nghĩa mọi @Async đều được áp dụng

@EnableAsync kích hoạt hạ tầng xử lý annotation nhưng **không sửa được self-invocation**. Sau khi cấu hình đủ executor, lời gọi **this.sendWelcomeEmailAsync(...)** vẫn đi thẳng vào target trong proxy mode. Cần sửa đường đi của lời gọi, không chỉ thêm annotation hoặc mở rộng pool.

## 6. Điều kiện để phương thức được intercept

Trong chế độ Spring AOP proxy thường dùng, proxy phải có khả năng chặn lời gọi phương thức.

### Phương thức public là lựa chọn an toàn

Đối với @Async, hãy ưu tiên phương thức **public** trên Spring-managed bean và gọi qua bean đó từ component khác.

~~~java
@Service
public class AsyncMailSender {

    @Async("mailExecutor")
    public void sendReceipt(String recipient) {
        // Gửi thư...
    }
}
~~~

Không dựa vào @Async gắn trên phương thức **private**, vì proxy không intercept được lời gọi private theo cơ chế thông thường. Phương thức **final** hoặc class **final** có thể ngăn class-based proxy override và intercept. Với JDK dynamic proxy, phương thức cần xuất hiện trên interface mà proxy cung cấp. Các chi tiết chính xác còn phụ thuộc kiểu proxy và phiên bản Spring.

### JDK dynamic proxy và class-based proxy

Spring có thể dùng hai kiểu proxy phổ biến:

| Kiểu proxy | Cách hoạt động chính | Lưu ý |
| --- | --- | --- |
| **JDK dynamic proxy** | Proxy triển khai các interface của bean | Gọi qua interface được proxy cung cấp |
| **Class-based proxy** (CGLIB) | Proxy dựa trên lớp đích | Khó/không thể intercept một số phương thức final, private |

Điểm chung: **self-invocation không đi qua ranh giới proxy từ bên ngoài**. Chuyển từ JDK proxy sang CGLIB không phải cách sửa cơ bản cho lời gọi this.method().

### Gọi trong constructor hoặc @PostConstruct

Không nên kỳ vọng @Async áp dụng khi gọi từ constructor hoặc trong quá trình khởi tạo bean:

~~~java
@PostConstruct
void init() {
    sendWelcomeEmail("admin@example.test");
}

@Async("mailExecutor")
public void sendWelcomeEmail(String recipient) {
    // ...
}
~~~

Đây vẫn là lời gọi nội bộ trong cùng bean, và thời điểm initialization còn có thể diễn ra trước khi mọi proxy/lifecycle component sẵn sàng. Nếu cần khởi tạo công việc sau khi ứng dụng sẵn sàng, hãy dùng cơ chế lifecycle/event phù hợp và gọi bean async riêng. Không nên dùng phương thức tạo bean làm nơi gửi email giao dịch.

### Object tự new không phải Spring bean

Ví dụ:

~~~java
AsyncWelcomeMailService sender = new AsyncWelcomeMailService(mailSender);
sender.sendWelcomeEmail("user@example.test");
~~~

Đây là object Java tạo bằng new, không phải bean được Spring quản lý, nên không có AOP proxy cho @Async. Hãy nhận dependency qua constructor injection từ Spring container.

### Annotation trên phương thức được gọi nội bộ không tạo thread riêng

Thêm @Async nhiều lần không thay đổi đường gọi:

~~~java
@Async
public void first() {
    second(); // vẫn là lời gọi trên this
}

@Async
public void second() {
    // ...
}
~~~

Nếu bean khác gọi **first()** qua proxy, toàn bộ method first chạy trong worker thread. Nhưng khi **first()** gọi **second()** nội bộ, lời gọi second thường chạy **trong cùng worker thread đang chạy first**, chứ không được submit thành task async thứ hai.

Điều này không nhất thiết sai nếu mục tiêu chỉ là chạy toàn bộ chuỗi công việc trong background. Nhưng nếu mong muốn **second()** độc lập, có executor hoặc chính sách lỗi riêng, cần gọi qua một proxy phù hợp.

## 7. Hợp đồng trả về của @Async

Một phương thức @Async không nên trả một kiểu tùy ý chỉ vì Java cho phép. Trong cơ chế annotation-driven proxy, các kiểu trả về phổ biến được hỗ trợ là:

- **void**: caller không nhận trực tiếp kết quả gửi.
- **Future<T>**: caller có handle cho kết quả bất đồng bộ.
- **CompletableFuture<T>**: caller có thể kết hợp, xử lý lỗi và theo dõi hoàn thành.

### Dùng void cho email không cần caller chờ

~~~java
@Async("mailExecutor")
public void sendWelcomeEmail(String recipient) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setTo(recipient);
    message.setSubject("Chào mừng");
    message.setText("Xin chào!");
    mailSender.send(message);
}
~~~

Caller gọi:

~~~java
asyncWelcomeMailService.sendWelcomeEmail(email);
// Caller tiếp tục nếu task đã được executor chấp nhận.
~~~

Khi worker ném exception, caller không có Future để bắt lỗi đó. Cần cấu hình xử lý exception cho **void-return async method** hoặc bắt và ghi nhận lỗi ngay trong worker.

### Dùng CompletableFuture để nhận kết quả

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;

@Async("mailExecutor")
public CompletableFuture<Void> sendReceiptAsync(String recipient) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setTo(recipient);
    message.setSubject("Biên nhận");
    message.setText("Biên nhận được tạo thành công.");

    mailSender.send(message);
    return CompletableFuture.completedFuture(null);
}
~~~

Lời gọi từ bean khác:

~~~java
CompletableFuture<Void> result =
        asyncMailSender.sendReceiptAsync(recipient);

result.whenComplete((ignored, error) -> {
    if (error != null) {
        log.error("Không thể nộp email biên nhận", error);
    }
});
~~~

Spring proxy trả về một handle đại diện cho tác vụ đã submit. Trong worker, phương thức đích có thể trả **CompletableFuture.completedFuture(null)** sau khi mailSender.send(...) hoàn tất; nếu mailSender ném lỗi, handle bên ngoài hoàn thành theo trạng thái lỗi.

**Không gọi result.join() hoặc result.get() ngay trong HTTP request** nếu mục tiêu là không chặn request. Hai phương thức đó chờ tác vụ hoàn thành, khiến lợi ích của async giảm hoặc mất. Có thể chờ có chủ đích ở test, batch job hoặc khi nghiệp vụ thực sự cần kết quả trước khi đi tiếp.

### Không dùng @Async để biến lỗi thành thành công

Nếu caller trả HTTP 200 sau khi task vừa được submit, điều đó chỉ cho biết request đã được xử lý tới bước gửi task, **không chứng minh email đã được SMTP chấp nhận**. Thiết kế API nên phân biệt các trạng thái:

~~~text
REQUEST_ACCEPTED
      |
      v
ASYNC_TASK_QUEUED
      |
      v
SMTP_SUBMISSION_ATTEMPTED
      |
      +-- SUCCESS (transport accepted)
      |
      '-- FAILURE (retry/alert)
~~~

Chọn response/status tương ứng với hợp đồng nghiệp vụ, không ghi “email đã gửi thành công” ngay khi phương thức async được gọi.

## 8. Kết hợp @Async với @Transactional: không gửi thư trước commit

Sửa self-invocation giúp @Async thực sự submit task sang executor. Nhưng đó **không phải giải pháp đầy đủ cho tính nhất quán transaction**.

Xét trường hợp:

~~~java
@Transactional
public void register(RegisterCommand command) {
    User user = userRepository.save(User.from(command));

    // Lời gọi đi qua proxy @Async, có thể chạy trên worker ngay.
    asyncWelcomeMailService.sendWelcomeEmail(user.getEmail());

    // Một bước phía sau có thể thất bại.
    validateRegistrationLimit(command);
}
~~~

Nếu executor chạy task nhanh, thư có thể được gửi **trước khi transaction database commit**. Nếu validateRegistrationLimit(...) sau đó ném exception khiến transaction rollback, người dùng vẫn có thể nhận email xác nhận tài khoản không tồn tại trong database.

### Hai ranh giới độc lập

**@Async** trả lời câu hỏi: *tác vụ chạy trên thread nào, có chặn caller không?*

**Transaction commit** trả lời câu hỏi: *dữ liệu đã được ghi bền vững và công việc sau commit có được phép chạy chưa?*

Hai yếu tố này không đồng nhất:

~~~text
HTTP thread
    |
    v
BEGIN TRANSACTION
    |
    v
Save user
    |
    +-- submit async mail task ---> Worker thread
    |                                   |
    |                                   v
    |                              SMTP accepted
    v
Validation fails
    |
    v
ROLLBACK

Mail đã gửi nhưng user chưa được commit.
~~~

Tách mail service sang bean riêng giải quyết proxy; **chờ commit trước khi submit tác vụ** giải quyết tình huống email cho transaction rollback.

### Cách kết hợp: publish event trong transaction, gọi async bean sau commit

Service đăng ký phát event:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountRegistrationService {

    private final UserRepository userRepository;
    private final ApplicationEventPublisher eventPublisher;

    public AccountRegistrationService(
            UserRepository userRepository,
            ApplicationEventPublisher eventPublisher
    ) {
        this.userRepository = userRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Long register(RegisterCommand command) {
        User user = userRepository.save(User.from(command));

        eventPublisher.publishEvent(
                new AccountRegisteredEvent(
                        user.getId(),
                        user.getEmail()
                )
        );

        return user.getId();
    }
}

public record AccountRegisteredEvent(Long userId, String email) {
}
~~~

Listener chờ transaction commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AccountRegisteredMailListener {

    private final AsyncWelcomeMailService asyncWelcomeMailService;

    public AccountRegisteredMailListener(
            AsyncWelcomeMailService asyncWelcomeMailService
    ) {
        this.asyncWelcomeMailService = asyncWelcomeMailService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onRegistered(AccountRegisteredEvent event) {
        // Gọi sang bean @Async riêng, qua proxy của bean đó.
        asyncWelcomeMailService.sendWelcomeEmail(event.email());
    }
}
~~~

Luồng thực thi:

~~~text
AccountRegistrationService.register()
        |
        v
BEGIN TRANSACTION
        |
        v
Save user + publish AccountRegisteredEvent
        |
        +----- rollback ------> Không chạy AFTER_COMMIT listener
        |
        '-- commit thành công
                   |
                   v
           @TransactionalEventListener
                   |
                   v
           AsyncWelcomeMailService proxy
                   |
                   v
                mailExecutor
                   |
                   v
              JavaMailSender
~~~

Cách này kết hợp ba trách nhiệm tách biệt:

- Service nghiệp vụ quyết định lúc nào tài khoản được tạo.
- Transactional event listener chờ **AFTER_COMMIT**.
- Async mail bean chuyển tác vụ gửi thư sang executor.

**Lưu ý:** event listener sau commit không tự làm cho lời gọi async bền vững. Nếu process dừng ngay sau commit nhưng trước khi mail task chạy, thông báo trong bộ nhớ có thể mất. Với email giao dịch cần retry chắc chắn, dùng transactional outbox hoặc durable messaging.

### Transaction context không tự đi sang worker thread

Spring transaction trong mô hình imperative thường được bind với thread. Worker thread của @Async không tự tham gia transaction gốc của HTTP thread.

Điều này có nghĩa:

- Không truyền JDBC Connection hoặc EntityManager đang thuộc transaction cũ sang worker.
- Không dựa vào JPA lazy-loading từ entity được giữ trong event.
- Chỉ truyền ID hoặc DTO bất biến chứa những thông tin cần cho email.
- Nếu worker phải đọc database, hãy gọi service/repository với ranh giới transaction phù hợp.
- Nếu cần ghi trạng thái gửi sau commit từ listener đồng bộ, lưu ý tài nguyên của transaction vừa commit có thể vẫn đang bind; dùng một transaction mới khi cần ghi riêng.

Việc kết hợp @Async và @Transactional trên cùng phương thức cũng dễ làm khó hiểu ranh giới transaction do các advisor proxy. Với nhu cầu gửi mail, nên để transaction nghiệp vụ và worker gửi mail ở các component có trách nhiệm rõ ràng.

## 9. Xử lý lỗi khi tác vụ @Async gửi email

Chuyển công việc sang background làm cho lỗi không còn nhất thiết xuất hiện ở caller. Nếu SMTP timeout hoặc JavaMailSender ném **MailException**, worker phải có chiến lược xử lý.

### Với phương thức void

Ví dụ:

~~~java
@Async("mailExecutor")
public void sendWelcomeEmail(String recipient) {
    mailSender.send(createMessage(recipient));
}
~~~

Nếu mailSender.send(...) ném runtime exception, caller đã trở về và không có Future để bắt lỗi đó. Spring hỗ trợ **AsyncUncaughtExceptionHandler** cho những exception không được bắt trong phương thức @Async trả về void.

Ví dụ cấu hình:

~~~java
import java.lang.reflect.Method;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncErrorConfiguration implements AsyncConfigurer {

    private static final Logger log =
            LoggerFactory.getLogger(AsyncErrorConfiguration.class);

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (Throwable ex, Method method, Object... params) -> {
            log.error(
                    "Async method {} thất bại",
                    method.getName(),
                    ex
            );
        };
    }
}
~~~

Đây là minh họa cấu hình handler; trong ứng dụng chỉ nên có cấu hình @EnableAsync phù hợp, tránh vô tình tạo nhiều nơi bật/cấu hình async không cần thiết. Nếu đã có một class cấu hình @EnableAsync ở phần trước, có thể tích hợp AsyncConfigurer vào đó.

**AsyncUncaughtExceptionHandler không phải cơ chế retry.** Nó giúp ghi nhận exception của phương thức void. Muốn retry cần một cơ chế riêng và quy định rõ giới hạn, khoảng cách thử lại, phân loại lỗi tạm thời/vĩnh viễn.

### Với CompletableFuture

Caller có thể xử lý lỗi trên Future:

~~~java
CompletableFuture<Void> task =
        asyncMailSender.sendReceiptAsync(recipient);

task.exceptionally(error -> {
    log.error("Không thể gửi biên nhận", error);
    return null;
});
~~~

Hoặc:

~~~java
task.whenComplete((unused, error) -> {
    if (error == null) {
        metrics.recordMailSubmissionSuccess();
    } else {
        metrics.recordMailSubmissionFailure(error);
    }
});
~~~

Các hàm trên là ví dụ xử lý trên Future; **metrics** là component do ứng dụng định nghĩa. Phương thức whenComplete có thể chạy trên thread hoàn tất Future; nếu callback xử lý nặng, nên chuyển sang executor phù hợp bằng các biến thể async của CompletableFuture.

### Phân biệt các loại lỗi

| Lỗi | Xảy ra ở đâu | Hướng xử lý |
| --- | --- | --- |
| Không resolve được executor | Trước/khi submit task | Sửa cấu hình bean/qualifier |
| Executor từ chối task | Lúc submit | Backpressure, queue bền vững, phản hồi rõ ràng |
| SMTP timeout | Trong worker | Giới hạn timeout, retry theo chính sách |
| Địa chỉ email không hợp lệ | Khi chuẩn bị hoặc gửi | Validate và phân loại lỗi không nên retry vô hạn |
| Template render thất bại | Trong worker hoặc trước submit, tùy thiết kế | Ghi nhận template/data issue |
| Provider chấp nhận rồi bounce | Sau SMTP submission | Theo dõi event/bounce từ provider |

Một điểm quan trọng: **executor rejection có thể ném exception ngay tại lời gọi proxy**, trước khi worker được tạo. Vì vậy, không nên mặc định mọi loại lỗi của async đều chỉ xuất hiện về sau trong worker.

### Timeout quan trọng hơn chỉ thêm thread

@Async không làm SMTP nhanh hơn. Nếu một worker bị chặn chờ mạng quá lâu, pool sẽ mất dần worker rảnh và queue có thể đầy.

Ví dụ cấu hình timeout của JavaMailSender/Spring Boot:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Các giá trị trên là mili giây và chỉ là ví dụ cần điều chỉnh theo yêu cầu hệ thống. Còn cần cấu hình SMTP authentication/TLS phù hợp với server; không đưa password vào source code.

### Đừng ghi thông tin nhạy cảm vào log

Exception hoặc tham số async có thể chứa địa chỉ email, token khôi phục mật khẩu hoặc nội dung cá nhân. Handler nên log loại lỗi, mã event/correlation ID và metadata tối thiểu cần điều tra; tránh dump toàn bộ body, credentials hoặc secret link.

## 10. Các cách thay thế và những cách sửa dễ gây rắc rối

**Tách bean riêng** là lựa chọn ưu tiên khi cần @Async theo kiểu proxy. Một số cách khác tồn tại, nhưng cần hiểu rõ đánh đổi.

### Cách A — Gọi TaskExecutor trực tiếp

Không bắt buộc phải dùng @Async. Có thể inject TaskExecutor và tự submit công việc:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailPublisher {

    private final TaskExecutor mailExecutor;
    private final BlockingWelcomeMailSender blockingSender;

    public WelcomeMailPublisher(
            @Qualifier("mailExecutor") TaskExecutor mailExecutor,
            BlockingWelcomeMailSender blockingSender
    ) {
        this.mailExecutor = mailExecutor;
        this.blockingSender = blockingSender;
    }

    public void enqueueWelcomeEmail(String recipient) {
        mailExecutor.execute(
                () -> blockingSender.sendWelcomeEmail(recipient)
        );
    }
}
~~~

Trong trường hợp này, việc submit task xảy ra **tường minh**. Không có vấn đề self-invocation của @Async vì không trông chờ vào AOP interceptor. Đây là lựa chọn hợp lý khi muốn kiểm soát task scheduling, executor và chính sách lỗi ngay tại nơi gọi.

Nhưng cách này vẫn có các giới hạn của executor trong bộ nhớ: có thể từ chối task, mất task nếu process chết, không tự chờ database commit và không tự retry khi SMTP lỗi.

### Cách B — Self-injection (không nên chọn làm mặc định)

Một số ví dụ cố gắng inject chính bean vào bean đó:

~~~java
@Service
public class RegistrationService {

    private final RegistrationService selfProxy;

    // ...
}
~~~

Mục tiêu là gọi **selfProxy.sendAsync(...)** thay vì **this.sendAsync(...)** để đi qua proxy. Tuy nhiên:

- Dễ tạo circular dependency và làm việc khởi tạo bean phức tạp.
- Phụ thuộc proxy type, cách injection và cách quản lý vòng đời bean.
- Khi class thay đổi, khó hiểu vì sao một component phải tự inject chính nó.
- Dễ bị copy thành pattern chung cho cả @Async và @Transactional.

Có thể dùng một số kỹ thuật như lazy injection hoặc truy vấn proxy từ container, nhưng đó thường là giải pháp kỹ thuật cho trường hợp đặc biệt. Với gửi mail, **tách một bean async riêng rõ ràng hơn**.

### Cách C — Lấy bean từ ApplicationContext

Ví dụ:

~~~java
RegistrationService proxy =
        applicationContext.getBean(RegistrationService.class);
proxy.sendWelcomeEmailAsync(recipient);
~~~

Kỹ thuật này có thể đi qua proxy trong những cấu hình phù hợp, nhưng khiến service phụ thuộc trực tiếp container và kiểu proxy. Nếu bean được proxy bằng interface, việc lookup theo concrete class có thể không đúng như kỳ vọng. Nó cũng làm test và dependency tracing khó hơn.

**Constructor injection qua một bean khác** tốt hơn trong hầu hết thiết kế ứng dụng.

### Cách D — AopContext.currentProxy()

Spring AOP có cơ chế truy cập proxy hiện tại khi bật cấu hình exposeProxy phù hợp. Tuy nhiên, cách này tạo phụ thuộc trực tiếp vào Spring AOP và có thể ném lỗi nếu lời gọi hiện tại không đi trong ngữ cảnh có proxy được expose.

Không nên dùng nó như lời giải mặc định cho việc gửi email; chỉ cân nhắc khi có lý do kỹ thuật rõ ràng và chấp nhận chi phí coupling.

### Cách E — AspectJ weaving

**@EnableAsync** có thể được cấu hình dùng chế độ AspectJ thay vì proxy, nếu ứng dụng có các dependency và compile-time/load-time weaving phù hợp. Vì advice được weave vào bytecode, cơ chế này có thể xử lý cả self-invocation theo cách khác với proxy.

Tuy nhiên, AspectJ yêu cầu cấu hình build/runtime riêng, làm tăng độ phức tạp khi triển khai và debug. Không cần đổi toàn bộ AOP mode chỉ để chữa một chỗ gọi email trong cùng bean nếu tách bean đã đáp ứng yêu cầu.

### So sánh lựa chọn

| Giải pháp | Điểm mạnh | Hạn chế |
| --- | --- | --- |
| **Bean async riêng** | Rõ ràng, dễ test, hợp Spring DI | Cần thêm một class/bean |
| **TaskExecutor.execute(...)** | Submit tường minh, không phụ thuộc proxy | Tự quản lý lỗi và lifecycle task |
| **Self-injection** | Có thể gọi proxy của chính bean | Circular dependency, coupling, khó đọc |
| **ApplicationContext lookup** | Có thể lấy proxy từ container | Service locator, phụ thuộc proxy/config |
| **AopContext.currentProxy()** | Có thể gọi lại qua proxy khi cấu hình phù hợp | Coupling mạnh với AOP, cấu hình đặc biệt |
| **AspectJ weaving** | Có thể áp dụng advice ở self-call | Tăng độ phức tạp build và runtime |

## 11. Kiểm thử rằng lời gọi thật sự đi qua proxy

Để kiểm thử @Async, cần kiểm tra hành vi ở **Spring context có kích hoạt async**, không chỉ gọi trực tiếp một object Java tạo bằng new.

### Test với một bean thăm dò thread

Một component đơn giản để quan sát worker thread:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class AsyncThreadProbe {

    @Async("mailExecutor")
    public CompletableFuture<String> workerThreadName() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName()
        );
    }

    public CompletableFuture<String> callWithinSameBean() {
        // Lời gọi nội bộ không đi qua proxy của @Async.
        return workerThreadName();
    }
}
~~~

Integration test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class AsyncProxyIntegrationTest {

    @Autowired
    private AsyncThreadProbe probe;

    @Test
    void externalCallUsesMailExecutor() throws Exception {
        String workerName =
                probe.workerThreadName().get(5, TimeUnit.SECONDS);

        assertTrue(workerName.startsWith("mail-"));
    }

    @Test
    void selfInvocationDoesNotUseAsyncInterceptor() throws Exception {
        String currentThread = Thread.currentThread().getName();

        String invokedThread =
                probe.callWithinSameBean().get(5, TimeUnit.SECONDS);

        assertEquals(currentThread, invokedThread);
    }
}
~~~

Test giả định đã có **mailExecutor** với tiền tố **mail-** trong Spring context. Nó minh họa hai đường gọi:

- Từ test qua proxy tới **workerThreadName()**: tác vụ được thực hiện trên worker.
- Từ test qua **callWithinSameBean()**, rồi target tự gọi workerThreadName(): lời gọi nội bộ chạy trong thread hiện tại.

Kiểu kiểm tra này hữu ích để xác nhận hiểu đúng cơ chế proxy. Trong test ứng dụng thật, nên kiểm tra thêm **mailSender.send(...)** có được gọi đúng, lỗi được ghi nhận và nghiệp vụ không tuyên bố mail đã giao nếu chỉ mới submit task.

### Test đơn vị của RegistrationService

Khi đã tách **AsyncWelcomeMailService**:

~~~java
@Test
void registerRequestsWelcomeMail() {
    UserRepository repository = mock(UserRepository.class);
    AsyncWelcomeMailService mail = mock(AsyncWelcomeMailService.class);

    User savedUser = sampleUser("learner@example.test");
    when(repository.save(any(User.class))).thenReturn(savedUser);

    RegistrationService registration =
            new RegistrationService(repository, mail);

    registration.register(sampleRegisterCommand());

    verify(mail).sendWelcomeEmail("learner@example.test");
}
~~~

Trong unit test, mail là mock và không có Spring AOP proxy. Test này chỉ kiểm tra **service nghiệp vụ đã gọi đúng dependency**; nó không chứng minh method có @Async chạy trên thread khác. Vì vậy nên kết hợp unit test dependency và integration test proxy/executor ở hai cấp độ riêng.

### Test gửi email không cần SMTP thật

Có thể mock JavaMailSender để xác nhận nội dung message hoặc dùng SMTP test server/capture trong integration test. Tránh gửi email thật tới địa chỉ ngoài khi chạy test tự động.

Nếu test cần chờ tác vụ async hoàn thành, dùng **CompletableFuture.get(timeout, unit)**, **CountDownLatch** hoặc công cụ chờ với timeout. Không dùng Thread.sleep cố định với giả định worker luôn hoàn thành sau đúng một số mili giây; cách này dễ tạo test không ổn định.

### Test @TransactionalEventListener

Nếu đăng ký email theo **AFTER_COMMIT**, cần test riêng:

- Event được publish trong transaction, nhưng mail task chưa được submit trước commit.
- Transaction commit thành công: listener gọi bean async.
- Transaction rollback: listener AFTER_COMMIT không gọi bean async.
- Publish ngoài transaction với fallbackExecution mặc định false: listener không chạy.

Lưu ý một test Spring được đánh dấu **@Transactional** thường rollback khi test kết thúc. Vì thế, muốn kiểm tra AFTER_COMMIT phải chủ động commit bằng TransactionTemplate hoặc công cụ TestTransaction phù hợp; nếu không, listener không chạy là hành vi đúng của rollback, không phải lỗi @Async.

## 12. ThreadLocal, SecurityContext và dữ liệu truyền vào tác vụ async

Khi @Async hoạt động đúng, worker thực thi trên một thread khác. Điều này ảnh hưởng tới các thông tin được lưu trong **ThreadLocal** ở request thread.

Ví dụ dữ liệu thường liên quan đến execution context:

| Dữ liệu | Lưu ý với @Async |
| --- | --- |
| **Transaction context** | Không tự chuyển sang worker thread |
| **SecurityContext** | Không tự được bảo đảm có cùng authentication nếu không cấu hình truyền context |
| **MDC/correlation ID** | Cần cơ chế truyền context nếu muốn log worker có cùng trace |
| **Locale/timezone** | Nên truyền tường minh để render nội dung email nhất quán |
| **Request-scoped bean** | Có thể không tồn tại hoặc không an toàn khi worker chạy sau request |
| **JPA entity/lazy association** | Có thể không còn persistence context phù hợp |

### Đừng truyền HttpServletRequest vào async worker

Không nên thiết kế:

~~~java
@Async("mailExecutor")
public void sendWelcomeEmail(HttpServletRequest request) {
    String recipient = request.getParameter("email");
    // ...
}
~~~

Worker có thể chạy sau khi request đã hoàn tất. Request object, session hoặc security state có vòng đời và tính đồng bộ không phù hợp để chia sẻ tùy tiện.

Nên chuẩn bị dữ liệu ở service trước khi submit:

~~~java
public record WelcomeMailCommand(
        String recipient,
        String displayName,
        String localeTag,
        String correlationId
) {
}
~~~

~~~java
WelcomeMailCommand command = new WelcomeMailCommand(
        user.getEmail(),
        user.getDisplayName(),
        locale.toLanguageTag(),
        correlationId
);

asyncWelcomeMailService.sendWelcomeEmail(command);
~~~

Worker tự tạo Locale từ localeTag, chuẩn bị template context và gửi mail. Nếu command là record bất biến chứa những giá trị cần thiết, worker không cần phụ thuộc request thread.

### Chú ý SecurityContext

Nếu worker cần truy cập tài nguyên chỉ dành cho người dùng hiện tại, không nên mặc định SecurityContext từ HTTP thread sẽ có trong worker. Có các wrapper/delegating executor hỗ trợ truyền security context theo cấu hình Spring Security. Tuy nhiên, với email giao dịch, thường tốt hơn là **xác định quyền truy cập trước khi enqueue và truyền ID/dữ liệu đã được cho phép** vào tác vụ, thay vì cho worker phụ thuộc vào phiên đăng nhập của người dùng.

### Chú ý MDC

Log MDC có thể dùng correlation ID để ghép log HTTP và log SMTP. Nếu cần giữ correlation ID trên worker, cấu hình TaskDecorator hoặc cơ chế context propagation phù hợp. Khi sao chép MDC, cần **restore/clear context** sau tác vụ để tránh dữ liệu của request trước còn trên thread tái sử dụng trong pool.

Tránh truyền toàn bộ request headers hoặc thông tin cá nhân nhạy cảm vào MDC. Chỉ dùng mã truy vết và metadata an toàn.

## 13. Executor trong bộ nhớ không phải durable queue

Một lỗi hiểu nhầm là: sau khi sửa self-invocation, email “chắc chắn sẽ được gửi”. Trên thực tế, @Async thường chỉ chuyển task vào một executor **trong process đang chạy**.

### Các trường hợp task có thể không hoàn tất

- Executor hết queue capacity và từ chối task.
- Ứng dụng bị kill, máy chủ mất điện hoặc container restart.
- SMTP server timeout khiến worker bị kẹt lâu.
- Worker ném exception và không có retry.
- Application shutdown trước khi các task queued hoàn thành.
- Task bị cancel theo chính sách ứng dụng.

**@Async giải quyết concurrency, không tự giải quyết durability.**

### Giải pháp cho email quan trọng: transactional outbox

Nếu email chứa hóa đơn, thông báo thanh toán hoặc liên kết kích hoạt mà hệ thống cần retry, một thiết kế bền vững hơn là:

~~~text
Business transaction
      |
      +-- Lưu đơn hàng/tài khoản
      |
      '-- Ghi OutboxEvent(PENDING)
                |
                v
              COMMIT
                |
                v
         Background outbox worker
                |
                v
         Render + gửi email
                |
          +-----+------+
          |            |
        SUCCESS       FAILURE
          |            |
          v            v
       Mark SENT    Retry/backoff
~~~

Outbox event được ghi trong cùng transaction với dữ liệu nghiệp vụ. Nếu transaction rollback, event cũng rollback; nếu commit, event tồn tại bền vững để worker xử lý sau khi ứng dụng khởi động lại.

Một mail worker có thể dùng @Async nội bộ để song song hóa xử lý, nhưng **nguồn công việc bền vững** là outbox/queue chứ không phải Java thread pool.

### Gửi trùng và idempotency

Giả sử SMTP đã nhận email, nhưng ứng dụng chết trước khi cập nhật outbox thành SENT. Sau khi restart, worker đọc event PENDING và gửi lại. Người nhận có thể nhận hai thư.

Vì vậy, không nên tuyên bố outbox bảo đảm **exactly-once email delivery**. Thông thường cần:

- Event ID duy nhất.
- Cơ chế claim công việc tránh nhiều worker cùng gửi.
- Retry có backoff và giới hạn số lần.
- Ghi nhận trạng thái gửi tách khỏi trạng thái nghiệp vụ.
- Idempotency key khi provider/API gửi email hỗ trợ.
- Quy tắc xử lý duplicate khi không thể bảo đảm một lần duy nhất.

### Khi nào chỉ @Async là đủ?

Một email ít quan trọng như thông báo chào mừng không bắt buộc có thể dùng async trực tiếp nếu sản phẩm chấp nhận khả năng bỏ lỡ và có cơ chế vận hành phù hợp. Với email có yêu cầu pháp lý, giao dịch hoặc bảo mật, nên cân nhắc outbox/durable messaging từ đầu.

## 14. Bảng lỗi thường gặp khi tự gọi @Async

| Triệu chứng hoặc cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Gọi this.sendEmailAsync() | Bỏ qua Spring proxy | Gọi bean async riêng |
| Bỏ this nhưng vẫn gọi sendEmailAsync() nội bộ | Vẫn là self-invocation | Tách bean |
| Chỉ thêm @EnableAsync | Không sửa đường đi lời gọi | Cấu hình async **và** gọi qua proxy |
| Dùng new AsyncMailService(...) | Object không do Spring proxy quản lý | Inject Spring-managed bean |
| Gắn @Async lên private method | Proxy thông thường không intercept private | Dùng public method trên bean riêng |
| Gắn @Async lên final method với class-based proxy | Không thể override để intercept | Bỏ final hoặc thiết kế lại |
| Tự inject bean vào chính nó | Dễ circular dependency/coupling | Tách trách nhiệm |
| Chuyển proxy từ JDK sang CGLIB để sửa this-call | Self-call vẫn bypass proxy | Đổi ranh giới bean/lời gọi |
| @Async thực sự chạy nhưng gửi trước commit | Transaction chưa xong | AFTER_COMMIT hoặc outbox |
| Gọi CompletableFuture.get() ngay lập tức | Caller bị chặn chờ kết quả | Chỉ chờ khi nghiệp vụ yêu cầu |
| Void @Async ném lỗi nhưng không thấy ở HTTP | Lỗi xảy ra trên worker | Handler, log, metrics, retry |
| Executor đầy | Task bị từ chối | Capacity/backpressure/durable queue |
| Task không thấy SecurityContext/MDC | Không tự truyền ThreadLocal | Truyền context có kiểm soát |
| Unit test bằng new rồi khẳng định async lỗi | Không có Spring proxy trong test | Integration test với Spring context |
| SMTP accept nhưng sau đó bounce | Delivery là giai đoạn khác | Theo dõi provider events |

### Không nên dựa vào annotation để che thiết kế chưa rõ

Một service vừa xác nhận giao dịch, render HTML, tạo MIME message, mở SMTP connection, ghi audit và quản lý retry sẽ rất khó phân biệt phạm vi transaction với phạm vi async. Tách các vai trò giúp @Async trở thành một ranh giới thực thi có ý nghĩa, thay vì một annotation đặt lên phương thức bất kỳ.

## 15. Quy trình điều tra khi @Async không chạy

Khi thấy một lời gọi gửi mail có @Async nhưng vẫn mất thời gian như chạy đồng bộ, có thể kiểm tra theo thứ tự:

1. **Tìm đúng đường gọi**: caller có gọi một bean được inject hay gọi this.method() trong chính object?
2. **Xác nhận bean do Spring quản lý**: không phải object được tạo thủ công bằng new.
3. **Xác nhận @EnableAsync**: hạ tầng async được kích hoạt trong context phù hợp.
4. **Xác nhận method visibility/proxy**: phương thức public, không bị giới hạn bởi final/private theo cơ chế proxy.
5. **Kiểm tra executor**: qualifier có resolve đúng, queue có đầy hoặc executor bị shutdown không?
6. **Quan sát thread**: log tên thread và một correlation ID ở cả caller lẫn worker.
7. **Xác nhận caller không chờ Future ngay**: get/join có thể làm luồng gọi bị chặn.
8. **Xem SMTP timeout**: worker bất đồng bộ vẫn có thể bị I/O chặn.
9. **Xem transaction boundary**: nếu gửi sau commit, kiểm tra event phase và callback registration.
10. **Kiểm tra test đúng tầng**: unit test logic riêng; integration test AOP proxy và executor.

### Sơ đồ quyết định ngắn

~~~text
Phương thức có @Async
          |
          v
Bean do Spring quản lý?
     |              |
    Không           Có
     |              |
     v              v
   Không có      @EnableAsync đã bật?
   proxy             |          |
                    Không       Có
                     |          |
                     v          v
                  Cấu hình    Lời gọi qua proxy?
                                  |          |
                                 Không       Có
                                  |          |
                                  v          v
                              Self-call    Executor resolve?
                              chạy sync       |          |
                                            Không       Có
                                             |          |
                                             v          v
                                          Sửa config  Task được submit
                                                        |
                                                        v
                                                 Kiểm tra queue/lỗi
~~~

Nếu TaskExecutor được gọi nhưng HTTP vẫn chờ, kiểm tra caller có đồng bộ chờ Future, có bước xử lý nặng **trước** lời gọi async hoặc có một thao tác gửi email khác chạy trực tiếp hay không. Không phải mọi độ trễ HTTP đều do self-invocation.

## 16. Tình huống thực hành

### Tình huống A — Bỏ từ khóa this có sửa được không?

Code ban đầu:

~~~java
this.sendWelcomeEmailAsync(email);
~~~

Đổi thành:

~~~java
sendWelcomeEmailAsync(email);
~~~

**Đáp:** không. Cả hai là lời gọi trên cùng instance. Trong proxy mode, cả hai bypass @Async interceptor.

### Tình huống B — Đã bật @EnableAsync và cấu hình 10 worker

Lời gọi vẫn chạy trong HTTP thread.

**Hỏi:** nên tăng maxPoolSize không?

**Đáp:** không phải bước sửa đầu tiên. Hãy kiểm tra self-invocation và xác nhận lời gọi có đi qua Spring proxy không. Pool lớn hơn không giúp một lời gọi chưa từng được submit.

### Tình huống C — Tách bean async rồi nhưng gửi email cho transaction rollback

RegistrationService có @Transactional và gọi bean async trước khi commit.

**Hỏi:** vấn đề còn lại là gì?

**Đáp:** task đã chạy bất đồng bộ nhưng có thể bắt đầu trước commit. Hãy phát event trong transaction, xử lý ở AFTER_COMMIT rồi mới gọi bean async, hoặc dùng outbox nếu cần độ bền.

### Tình huống D — @Async trong cùng bean gọi một @Async khác

Một bean được gọi từ ngoài qua proxy vào firstAsync(), bên trong firstAsync() gọi secondAsync().

**Hỏi:** secondAsync() có được submit thành task độc lập không?

**Đáp:** thường không trong proxy mode. firstAsync() có thể chạy trên worker, nhưng lời gọi secondAsync() nội bộ vẫn thực hiện trên cùng worker đó.

### Tình huống E — Mail method trả CompletableFuture nhưng request vẫn chậm

Caller dùng:

~~~java
asyncMailSender.sendReceiptAsync(email).join();
~~~

**Hỏi:** vì sao request chờ?

**Đáp:** join() chờ Future hoàn thành. Nếu mục tiêu là trả phản hồi ngay, không chờ kết quả trong request; xử lý trạng thái sau đó.

### Tình huống F — Gửi mail thất bại nhưng HTTP không thấy exception

Phương thức async trả void và gửi thư thất bại trên worker.

**Hỏi:** nên làm gì?

**Đáp:** dùng AsyncUncaughtExceptionHandler hoặc bắt lỗi trong worker để log/ghi nhận/retry. HTTP request trước đó không nên mặc định nhận được exception của worker.

### Tình huống G — Test tự new MailService rồi gọi @Async

Test thấy phương thức chạy trên test thread.

**Hỏi:** có chứng minh annotation không hoạt động trong ứng dụng thật không?

**Đáp:** không. Object tạo bằng new không có Spring proxy. Muốn kiểm tra interception phải lấy bean từ Spring context với @EnableAsync phù hợp.

### Tình huống H — Worker không đọc được thông tin người dùng

Service gửi HttpServletRequest hoặc JPA entity có lazy properties tới worker.

**Hỏi:** nên sửa thế nào?

**Đáp:** truyền một mail command bất biến chứa dữ liệu cần thiết hoặc ID. Nếu phải truy vấn lại, mở transaction ở worker, không dựa vào request/transaction context cũ.

### Tình huống I — Process bị kill sau khi task đã enqueue

**Hỏi:** @Async có tự khôi phục task sau khi restart không?

**Đáp:** không. Thread pool trong bộ nhớ không phải durable queue. Dùng outbox hoặc một hàng đợi bền vững khi thông báo không được phép mất.

### Tình huống J — Có thể dùng TaskExecutor thay @Async không?

**Đáp:** có. Submit task tường minh bằng TaskExecutor.execute(...) không phụ thuộc @Async proxy, nhưng caller phải tự thiết kế lỗi, backpressure, cancellation và ranh giới transaction.

## 17. Nguyên tắc triển khai Spring Mail bất đồng bộ

~~~text
LỜI GỌI ĐÚNG

BusinessService
      |
      v
Spring proxy của AsyncMailService
      |
      v
TaskExecutor
      |
      v
Worker thread
      |
      v
JavaMailSender


LỜI GỌI SAI

BusinessService.methodA()
      |
      v
this.methodB()   <-- @Async trên methodB bị bypass
      |
      v
JavaMailSender chạy đồng bộ
~~~

Đối với email gắn với giao dịch database, dùng thêm một ranh giới:

~~~text
Business transaction COMMIT
          |
          v
AFTER_COMMIT listener
          |
          v
AsyncMailService proxy
          |
          v
mailExecutor / worker
          |
          v
JavaMailSender
~~~

**Không tự gọi phương thức @Async trong cùng bean** là quy tắc quan trọng của Spring AOP proxy mode. Một lời gọi nội bộ qua **this** không đi qua proxy nên annotation @Async không được áp dụng như mong đợi. Hãy đặt tác vụ gửi mail trong **Spring bean riêng**, inject bean đó và gọi qua proxy; cấu hình executor có giới hạn rõ ràng, kiểm tra thread/lỗi ở đúng tầng và dùng AFTER_COMMIT nếu thư chỉ được gửi sau khi transaction thành công. Khi cần khả năng phục hồi sau crash và retry bền vững, hãy dùng transactional outbox hoặc durable queue thay vì chỉ dựa vào @Async.
