# Giới hạn của cấu hình mặc định trong hệ thống nhiều sender

Một ứng dụng Spring Boot thông thường chỉ cần gửi email từ một tài khoản SMTP: cấu hình `spring.mail.host`, `spring.mail.port`, `spring.mail.username`, `spring.mail.password` rồi tiêm `JavaMailSender` vào service. Cách này đơn giản và phù hợp với nhiều hệ thống nhỏ.

Nhưng khi sản phẩm phát triển, một ứng dụng có thể cần nhiều nguồn gửi: email giao dịch đi qua tài khoản A, hóa đơn đi qua tài khoản B, thông báo nội bộ dùng SMTP relay của công ty, còn email marketing đi qua một nhà cung cấp riêng. Nếu cố đặt tất cả vào một cấu hình `spring.mail.*`, ứng dụng sẽ gặp giới hạn về **định tuyến, xác thực, quyền gửi, cách ly cấu hình và quản trị vận hành**.

Bài học này giải thích **giới hạn của cấu hình mặc định Spring Boot Mail trong hệ thống nhiều sender**, phân biệt các nghĩa của “sender”, và trình bày cách thiết kế nhiều `JavaMailSender` có kiểm soát bằng Spring configuration, `@Qualifier` và tầng chọn tuyến gửi.

> **Ý chính:** `spring.mail.*` mặc định mô tả **một cấu hình gửi thư**, không phải cơ chế tự động quản lý nhiều tài khoản SMTP hay tự chọn nhà cung cấp cho từng message. Nhiều địa chỉ `From` chưa chắc cần nhiều sender; nhiều credential hoặc nhiều SMTP transport mới thường đòi hỏi cách cấu hình khác.

## 1. “Nhiều sender” có thể mang những nghĩa khác nhau

Trước khi chọn cách triển khai, phải biết “sender” đang chỉ điều gì.

| Nhu cầu | Ví dụ | Có cần nhiều `JavaMailSender` không? |
| --- | --- | --- |
| **Nhiều địa chỉ From nhưng một tài khoản SMTP** | `notification@example.org` và `support@example.org` cùng dùng relay A | **Không nhất thiết.** Một sender có thể đủ nếu nhà cung cấp cho phép tất cả địa chỉ From đó. |
| **Nhiều tài khoản SMTP** | Tài khoản gửi thông báo và tài khoản gửi hóa đơn có username/password khác nhau | **Thường có.** Cần cách cấu hình và chọn đúng credential cho từng luồng. |
| **Nhiều SMTP host / provider** | Thư giao dịch qua provider A, marketing qua provider B | **Có thể cần nhiều sender** hoặc một tầng adapter chuyên dụng. |
| **Nhiều thương hiệu / tenant** | Khách hàng X gửi bằng miền của X; khách hàng Y gửi bằng miền của Y | **Phụ thuộc quy mô và quy tắc tenant.** Có thể dùng registry, factory hoặc dịch vụ gửi tập trung. |
| **Nhiều người nhận của cùng một message** | Một thư gửi tới ba địa chỉ To và một địa chỉ Cc | **Không.** Đây là nhiều recipient, không phải nhiều SMTP sender. |

Sự phân biệt này giúp tránh tạo thêm hạ tầng không cần thiết. Nếu chỉ muốn đổi tên người gửi hiển thị trong cùng một relay, việc gọi `helper.setFrom(...)` có thể đủ. Nhưng nếu nhà cung cấp đòi **đăng nhập tài khoản khác, host khác hoặc chính sách TLS khác**, thay `From` không làm thay đổi kết nối SMTP đang được sử dụng.

### Ví dụ: cùng một ứng dụng, ba loại email

Giả sử hệ thống có:

- **Thông báo tài khoản:** `notify@example.org`, đi qua SMTP provider dành cho email giao dịch.
- **Hóa đơn:** `billing@example.org`, đi qua tài khoản SMTP khác để quản lý quyền gửi và log riêng.
- **Chăm sóc khách hàng:** `support@example.org`, có thể cùng relay với thông báo tài khoản nếu nhà cung cấp cho phép dùng bí danh đó.

Trong thiết kế này, số địa chỉ From là ba nhưng số kết nối SMTP cần cấu hình có thể là **hai**, không phải ba.

## 2. Spring Boot tự cấu hình mail như thế nào?

Khi có starter mail và điều kiện cấu hình phù hợp, Spring Boot có thể tạo bean gửi thư, thường là `JavaMailSenderImpl`, dựa trên nhóm thuộc tính `spring.mail.*`.

Ví dụ một cấu hình đơn:

~~~properties
spring.mail.host=smtp.main.example
spring.mail.port=587
spring.mail.username=${MAIN_SMTP_USERNAME}
spring.mail.password=${MAIN_SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
~~~

Khi ứng dụng chỉ có một sender, service thường chỉ cần:

~~~java
@Service
public class NoticeService {

    private final JavaMailSender mailSender;

    public NoticeService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // mailSender.send(...) sử dụng cấu hình chung ở trên.
}
~~~

Có thể hình dung:

~~~mermaid
flowchart TD
    A["spring.mail.*"] --> B["Spring Boot Mail Auto-configuration"]
    B --> C["Một JavaMailSender"]
    D["Service thông báo"] --> C
    E["Service hóa đơn"] --> C
    F["Service khác"] --> C
    C --> G["Một cấu hình SMTP transport"]
~~~

Cách này có lợi vì cấu hình ngắn, dễ tiêm dependency và phù hợp cho một tuyến gửi. Nhưng **mặc định không có khái niệm** “`spring.mail.notification.host` và `spring.mail.billing.host` sẽ tự tạo hai sender”. Những tên đó không phải cơ chế tạo bean nhiều sender có sẵn của Spring Boot.

### Điều kiện của auto-configuration cần được hiểu đúng

Spring Boot thường chỉ tự tạo sender khi có thư viện và nguồn cấu hình phù hợp, đồng thời chưa có bean gửi mail do ứng dụng tự cung cấp đáp ứng điều kiện của auto-configuration. Khi tự định nghĩa bean kiểu `MailSender`/`JavaMailSender`, cơ chế tự cấu hình mặc định có thể **nhường quyền cho cấu hình thủ công**.

Vì vậy, nếu ứng dụng khai báo sender riêng cho hóa đơn, **đừng giả định** Spring Boot vẫn tự tạo một sender thứ hai từ `spring.mail.*` cho thông báo. Hãy xác định rõ toàn bộ những sender cần dùng trong ApplicationContext.

Điểm cụ thể có thể khác theo phiên bản Spring Boot hoặc cấu hình đặc biệt như JNDI mail session. Nguyên tắc thiết kế vẫn là: **đừng dùng một thuộc tính đơn để suy ra rằng framework đã tự quản lý nhiều sender độc lập**.

## 3. Những giới hạn khi dùng một cấu hình mặc định

### 3.1. Chỉ có một tập host, port và credential

Nhóm `spring.mail.*` thường cung cấp một tổ hợp:

~~~text
host + port + username + password + SMTP properties
~~~

Các giá trị này có thể dùng lại cho nhiều message, nhưng không tự thay đổi theo “email hóa đơn” hoặc “email thông báo”. Nếu hai luồng yêu cầu hai username/password khác nhau, một sender duy nhất sẽ không phân biệt được chúng chỉ dựa trên Subject hoặc địa chỉ người nhận.

### 3.2. Không có router theo nghiệp vụ

Framework không tự biết một message có Subject “Hóa đơn” phải dùng SMTP A, còn một message có Subject “Xác thực tài khoản” phải dùng SMTP B. **Việc chọn tuyến phải được ứng dụng quy định.**

Không nên suy tuyến chỉ bằng cách tìm từ khóa trong Subject: tiêu đề thay đổi theo locale, có thể trùng lặp và không phải khóa nghiệp vụ ổn định. Một tham số như `MailPurpose.BILLING` hoặc `MailPurpose.NOTIFICATION` rõ ràng hơn.

### 3.3. Một cấu hình TLS/timeout chung

Hai SMTP provider có thể yêu cầu khác nhau:

| Yếu tố | Provider A | Provider B |
| --- | --- | --- |
| Host | `smtp.notify.example` | `smtp.billing.example` |
| Port | `587` | `465` |
| TLS | STARTTLS | Implicit TLS |
| Username/password | Credential A | Credential B |
| Timeout | Theo nhu cầu thông báo | Theo SLA phát hành hóa đơn |

Một bộ `spring.mail.properties.mail.smtp.*` đơn không thể đồng thời biểu diễn hai kiểu kết nối độc lập mà không có một tầng cấu hình riêng.

### 3.4. Không tách biệt quota, kết quả gửi và lỗi theo provider

Các nhà cung cấp có thể có giới hạn gửi, trạng thái xác thực miền, chính sách từ chối recipient và kênh nhận bounce khác nhau. Dùng cùng service mà không lưu **sender/provider được chọn** gây khó khăn khi chẩn đoán một luồng gửi bị chặn, trong khi các luồng khác vẫn bình thường.

### 3.5. Không giải quyết tự động quyền gửi từ nhiều miền

Có nhiều địa chỉ `From` trong code không chứng minh SMTP provider cho phép gửi từ những miền đó. Nhà cung cấp có thể yêu cầu xác minh địa chỉ/miền, DKIM, SPF, hoặc áp dụng chính sách chống giả mạo.

`JavaMailSender` không thể tự vượt qua những quy tắc này bằng cách đổi `setFrom(...)`. Danh tính được phép gửi là một phần của **hợp đồng với hạ tầng SMTP**, không chỉ là thuộc tính Java.

### 3.6. Thiếu ngữ cảnh tenant và trách nhiệm bảo mật

Nếu một ứng dụng đa tenant dùng chung một sender được cấu hình bằng credential của tenant A rồi thay `From` thành miền tenant B, đó có thể là hành vi sai quyền. Với hệ thống nhiều khách hàng, cần ràng buộc **tenant được phép dùng sender nào**, không chỉ kiểm tra cú pháp địa chỉ email.

## 4. Phân biệt From, Reply-To, SMTP account và envelope sender

Trong hệ thống nhiều sender, bốn danh tính sau có thể khác nhau:

| Thành phần | Vai trò | Cách đặt thường gặp |
| --- | --- | --- |
| **SMTP account** | Danh tính đăng nhập vào relay | `JavaMailSenderImpl.setUsername(...)` và `setPassword(...)` |
| **From header** | Địa chỉ người gửi mà người nhận nhìn thấy | `MimeMessageHelper.setFrom(...)` |
| **Reply-To header** | Nơi gợi ý gửi câu trả lời | `MimeMessageHelper.setReplyTo(...)` |
| **Envelope sender** | Danh tính được gửi trong `MAIL FROM` ở phiên SMTP; thường dùng cho bounce | Do SMTP transport/provider xác định theo cấu hình và chính sách |

Ví dụ:

~~~text
SMTP account:    smtp-notification-account
From:            Notification Team <notify@example.org>
Reply-To:        helpdesk@example.org
Envelope sender: bounce-route-123@mailer.example.org
~~~

Đây là những thông tin có thể cùng tồn tại trong một luồng gửi. **Không nên coi `spring.mail.username` luôn là `From`**, và cũng không nên cho rằng thay `From` sẽ đổi tài khoản SMTP.

Đặc biệt, nếu chọn sai sender nhưng đặt đúng From, message có thể bị từ chối, bị viết lại thông tin người gửi hoặc tạo lỗi xác thực miền. Cần lựa chọn đúng **cả transport** và **danh tính hiển thị**.

## 5. Ba hướng thiết kế cho hệ thống nhiều sender

Tùy số lượng tài khoản, tốc độ thay đổi cấu hình và yêu cầu vận hành, có thể chọn một trong ba cách phổ biến.

| Thiết kế | Ý tưởng | Phù hợp |
| --- | --- | --- |
| **Một sender, nhiều From được phép** | Dùng một `JavaMailSender`, thay `From` theo thông báo | Một relay cho phép nhiều alias/miền gửi |
| **Nhiều bean JavaMailSender** | Mỗi SMTP account/provider là một bean riêng, tiêm bằng `@Qualifier` | Một số ít tuyến gửi cố định |
| **Sender registry/factory** | Chọn một cấu hình đã được cấp quyền từ registry, rồi dùng sender phù hợp | Nhiều tenant hoặc sender thay đổi theo thời gian |

Với hệ thống chỉ có hai hoặc ba nhà cung cấp cố định, **nhiều bean có tên rõ ràng** thường đủ. Với hàng trăm tenant, việc khai báo hàng trăm bean tĩnh trong code có thể trở nên khó bảo trì; khi đó cần tầng registry, cache, quản lý secret và chính sách giới hạn tài nguyên.

Bất kỳ hướng nào cũng nên giữ một nguyên tắc: **service nghiệp vụ yêu cầu gửi thư theo mục đích**, thay vì tự ý lựa chọn tài khoản SMTP từ một chuỗi do người dùng cung cấp.

## 6. Ví dụ: cấu hình hai sender độc lập bằng Spring Boot

Giả sử ứng dụng dùng hai tài khoản SMTP:

- `notification`: gửi thông báo trạng thái tài khoản;
- `billing`: gửi hóa đơn và biên nhận.

Hai tài khoản này có hostname, credential và địa chỉ From khác nhau. Để tập trung vào giới hạn nhiều sender, ví dụ dưới đây giả định **cả hai SMTP relay hỗ trợ submission qua STARTTLS trên cổng 587**. Nếu một provider dùng implicit TLS trên cổng 465, phải thay cấu hình TLS của riêng sender đó.

### 6.1. Phụ thuộc Spring Boot

Trong Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Starter đưa các thành phần Spring Mail/Jakarta Mail vào ứng dụng. Từ đây, thay vì yêu cầu framework tự tạo nhiều sender từ `spring.mail.*`, ta sẽ **tự khai báo hai bean**.

### 6.2. application.yml: namespace cấu hình của ứng dụng

~~~yaml
app:
  mail:
    notification:
      host: smtp.notify.example
      port: 587
      username: ${NOTIFY_SMTP_USERNAME}
      password: ${NOTIFY_SMTP_PASSWORD}
      from: notify@example.org
    billing:
      host: smtp.billing.example
      port: 587
      username: ${BILLING_SMTP_USERNAME}
      password: ${BILLING_SMTP_PASSWORD}
      from: billing@example.org
~~~

Tên `app.mail.notification.*` và `app.mail.billing.*` là **khóa cấu hình tự định nghĩa của ứng dụng**, không phải thuộc tính mà Spring Boot tự hiểu để tạo nhiều `JavaMailSender`.

Dữ liệu minh họa dùng những hostname giả định. Khi vận hành cần sử dụng thông số thực do SMTP provider cấp. Biến môi trường phải được cấp qua môi trường chạy hoặc hệ thống quản lý bí mật; không lưu mật khẩu vào repository.

### 6.3. Khai báo hai bean JavaMailSender

Một cách triển khai tối giản dùng `@Value` là:

~~~java
import java.util.Properties;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration(proxyBeanMethods = false)
public class MultiSenderConfiguration {

    @Bean("notificationMailSender")
    public JavaMailSender notificationMailSender(
            @Value("${app.mail.notification.host}") String host,
            @Value("${app.mail.notification.port}") int port,
            @Value("${app.mail.notification.username}") String username,
            @Value("${app.mail.notification.password}") String password) {

        return newStartTlsSender(host, port, username, password);
    }

    @Bean("billingMailSender")
    public JavaMailSender billingMailSender(
            @Value("${app.mail.billing.host}") String host,
            @Value("${app.mail.billing.port}") int port,
            @Value("${app.mail.billing.username}") String username,
            @Value("${app.mail.billing.password}") String password) {

        return newStartTlsSender(host, port, username, password);
    }

    private static JavaMailSenderImpl newStartTlsSender(
            String host,
            int port,
            String username,
            String password) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();

        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");

        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
~~~

**Điểm cần chú ý trong cấu hình:**

1. `@Bean("notificationMailSender")` và `@Bean("billingMailSender")` tạo **hai bean khác tên**, cùng thực hiện giao diện `JavaMailSender`.
2. Mỗi bean giữ một bộ `host/port/username/password` riêng.
3. Phương thức factory dùng lại phần logic tạo kết nối thay vì sao chép toàn bộ thuộc tính SMTP.
4. Hai sender cùng dùng STARTTLS vì **ví dụ cố tình chọn hai provider có giao thức tương thích**.
5. `getJavaMailProperties()` chứa cấu hình dành cho Jakarta Mail. Những thuộc tính được đặt khi tạo bean, không được thay đổi tùy tiện ở mỗi lần gửi.
6. Giá trị `from` chưa được áp dụng ở bước tạo transport. Nó sẽ được dùng khi **tạo message**, vì `From` là một phần của thông điệp chứ không phải username của kết nối.

Cần chú ý: **khai báo hai bean cùng kiểu không có nghĩa Spring tự biết bean nào dùng cho service nào**. Đây là trách nhiệm của bước tiêm dependency và định tuyến.

### 6.4. Nếu hai provider dùng hai kiểu TLS khác nhau

Khi provider notification dùng STARTTLS 587 và provider billing dùng implicit TLS 465, không nên gọi chung factory STARTTLS như ví dụ trên cho cả hai.

Có thể xây dựng factory nhận một kiểu kết nối đã được quy định:

~~~java
private static void configureTls(
        JavaMailSenderImpl sender,
        boolean implicitTls) {

    Properties props = sender.getJavaMailProperties();
    props.put("mail.smtp.auth", "true");
    props.put("mail.smtp.ssl.checkserveridentity", "true");

    if (implicitTls) {
        // Ví dụ khi server hỗ trợ TLS ngay từ kết nối TCP.
        props.put("mail.smtp.ssl.enable", "true");
    } else {
        // Ví dụ khi server hỗ trợ STARTTLS.
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
    }
}
~~~

Đoạn trên là một **phần helper minh họa thay thế việc đặt TLS trong factory**; không phải phần cần gọi thêm sau khi đã gắn cả hai kiểu TLS xung đột. Điều quan trọng là cấu hình **mỗi sender** theo bộ thông số riêng do provider cung cấp.

## 7. Tiêm đúng sender bằng @Qualifier

Khi có hai bean cùng kiểu `JavaMailSender`, một constructor như sau không còn chỉ rõ ý định:

~~~java
public BillingService(JavaMailSender mailSender) {
    this.mailSender = mailSender;
}
~~~

Nếu không có tiêu chí phân giải bean duy nhất, Spring có thể báo lỗi vì **có nhiều bean phù hợp** (ví dụ `NoUniqueBeanDefinitionException` trong quá trình tạo bean). Có thể dùng `@Qualifier` để chỉ định chính xác:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class BillingService {

    private final JavaMailSender billingMailSender;

    public BillingService(
            @Qualifier("billingMailSender")
            JavaMailSender billingMailSender) {

        this.billingMailSender = billingMailSender;
    }
}
~~~

Tương tự, `NotificationService` dùng `@Qualifier("notificationMailSender")`.

Có thể gắn `@Primary` cho một sender để ứng dụng biết bean mặc định khi tiêm không có qualifier. Nhưng `@Primary` **chỉ quyết định ưu tiên lựa chọn bean khi dependency injection**, không tự chuyển email hóa đơn sang tài khoản billing khi code gọi nhầm sender chính.

Nếu thiết kế cần chọn đúng theo nghiệp vụ, cách rõ ràng là dùng qualifier hoặc một service/router có API theo mục đích.

## 8. Tầng định tuyến gửi thư theo mục đích

Khi service nghiệp vụ phải gửi nhiều loại email, việc tiêm một sender riêng vào mỗi service có thể đủ. Nhưng nếu một luồng có thể gửi các loại email khác nhau, có thể tạo **MailRouter** để gom chính sách chọn sender tại một điểm.

### 8.1. Định nghĩa mục đích gửi

~~~java
public enum MailPurpose {
    NOTIFICATION,
    BILLING
}
~~~

Đây là enum do ứng dụng định nghĩa, không phải enum chuẩn của Spring Mail. Nó mô tả **ý định nghiệp vụ**, tránh phải suy đoán sender qua nội dung Subject hay tên miền người nhận.

### 8.2. Router sử dụng hai bean và hai địa chỉ From

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailRouter {

    private final JavaMailSender notificationSender;
    private final JavaMailSender billingSender;

    private final String notificationFrom;
    private final String billingFrom;

    public MailRouter(
            @Qualifier("notificationMailSender")
            JavaMailSender notificationSender,
            @Qualifier("billingMailSender")
            JavaMailSender billingSender,
            @Value("${app.mail.notification.from}")
            String notificationFrom,
            @Value("${app.mail.billing.from}")
            String billingFrom) {

        this.notificationSender = notificationSender;
        this.billingSender = billingSender;
        this.notificationFrom = notificationFrom;
        this.billingFrom = billingFrom;
    }

    public void send(
            MailPurpose purpose,
            String recipient,
            String subject,
            String plainText) throws MessagingException {

        if (purpose == null) {
            throw new IllegalArgumentException(
                    "Cần chỉ định mục đích gửi email"
            );
        }

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Người nhận không được để trống"
            );
        }

        if (subject == null || subject.isBlank()
                || plainText == null || plainText.isBlank()) {
            throw new IllegalArgumentException(
                    "Subject và nội dung không được để trống"
            );
        }

        JavaMailSender selected;
        String from;

        switch (purpose) {
            case NOTIFICATION -> {
                selected = notificationSender;
                from = notificationFrom;
            }
            case BILLING -> {
                selected = billingSender;
                from = billingFrom;
            }
            default -> throw new IllegalArgumentException(
                    "Mục đích gửi chưa được hỗ trợ"
            );
        }

        // Tạo message bằng chính sender đã chọn.
        MimeMessage message = selected.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom(from);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plainText, false);

        selected.send(message);
    }
}
~~~

Cách sử dụng:

~~~java
mailRouter.send(
        MailPurpose.BILLING,
        "buyer@example.net",
        "Hóa đơn của bạn đã sẵn sàng",
        "Bạn có thể xem hóa đơn trong tài khoản."
);

mailRouter.send(
        MailPurpose.NOTIFICATION,
        "member@example.net",
        "Đăng nhập từ thiết bị mới",
        "Hệ thống ghi nhận một lần đăng nhập mới."
);
~~~

Các đoạn gọi ở trên giả định đang nằm trong service có dependency `MailRouter mailRouter`. Hai email sử dụng **hai transport khác nhau** mà tầng nghiệp vụ không phải tự đọc host/password.

### Vì sao chọn sender trước khi tạo MimeMessage?

Một đối tượng `MimeMessage` chứa nội dung và header, nhưng nó không mang một hợp đồng nghiệp vụ rằng **bắt buộc phải gửi qua sender nào**. Chọn sender trước, rồi tạo message qua `selected.createMimeMessage()`, giúp code dễ theo dõi nguồn cấu hình và tránh sử dụng nhầm một `Session` hoặc giá trị mặc định khác.

Nếu sử dụng các API ở mức thấp của Jakarta Mail, có thể quản lý riêng `Session` và `Transport`; nhưng với Spring Mail thông thường, nên để `JavaMailSender` đã chọn bao trọn phần tương tác SMTP.

### Router không nên tự động thử nhà cung cấp khác khi gặp mọi lỗi

Đổi sang sender thứ hai để “cứu” một yêu cầu gửi không phải lúc nào cũng đúng. Sender thứ hai có thể không được phép dùng cùng địa chỉ `From`, không có DKIM phù hợp hoặc không được phép gửi nội dung thuộc loại đó. Nếu có kế hoạch failover, cần định nghĩa **trước** những cặp sender có quyền thay thế nhau, điều kiện chuyển tuyến và cơ chế tránh gửi trùng.

## 9. Vì sao không đổi host, username và password trên một singleton mỗi lần gửi?

Một cách làm dễ nghĩ tới nhưng nguy hiểm là chỉ khai báo một `JavaMailSenderImpl`, rồi trước mỗi lần gửi thay đổi:

~~~java
// Ví dụ cần TRÁNH trong dịch vụ đồng thời:
sender.setHost(hostForCurrentRequest);
sender.setUsername(userForCurrentRequest);
sender.setPassword(secretForCurrentRequest);
sender.send(message);
~~~

Vấn đề không nằm ở cú pháp Java mà ở **đối tượng dùng chung có trạng thái thay đổi được**.

Hình dung hai request chạy đồng thời:

~~~text
Request A: setHost(smtp-a.example)
Request B: setHost(smtp-b.example)
Request A: setUsername(user-a)
Request B: setPassword(password-b)
Request A: send(...)
~~~

Khi đó, request A có nguy cơ sử dụng **tổ hợp host/username/password không thuộc cùng một tài khoản**. Tùy cách thực thi và thời điểm đọc cấu hình, việc sửa đồng thời có thể gây lỗi xác thực, gửi nhầm provider hoặc lộ thông tin giữa các tenant.

Các rủi ro khác gồm:

- `JavaMailSenderImpl` có thể giữ hoặc tạo `Session` và các thành phần liên quan; sửa thuộc tính trong lúc có thao tác gửi tạo trạng thái khó dự đoán.
- Các luồng gửi mail bất đồng bộ khiến thời điểm cấu hình và thời điểm thực thi không trùng nhau.
- Credential của tenant A có thể bị giữ trong đối tượng dùng chung khi request B đến.
- Khi vận hành, khó truy vết sender nào đã được dùng tại thời điểm gửi.

**Khuyến nghị:** tạo sender với cấu hình hoàn chỉnh, dùng ổn định cho tuyến mà nó phụ trách; khi có nhu cầu thay đổi tài khoản, chọn một sender khác hoặc xây dựng một sender mới theo quy trình an toàn. Không dùng thao tác mutate trên singleton để làm router cho mỗi request.

## 10. Khi số lượng sender tăng: Registry và factory

Hai bean cố định dễ hiểu nhưng không lý tưởng khi hệ thống có hàng chục hoặc hàng trăm tenant. Khi đó, có thể đặt một tầng trừu tượng:

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ có tenantId, purpose"] --> B["Mail routing policy"]
    B --> C["Kiểm tra quyền của tenant"]
    C --> D["Sender registry"]
    D --> E["Cấu hình và secret đã được phê duyệt"]
    E --> F["JavaMailSender phù hợp"]
    F --> G["SMTP provider"]
~~~

Một router ở quy mô này cần trả lời:

1. **Tenant nào được phép dùng sender nào?**
2. **Cấu hình gửi lấy từ đâu, được kiểm tra và cập nhật thế nào?**
3. **Credential được giải mã/lấy từ secret manager vào thời điểm nào?**
4. **Có cache sender không, cache giữ bao lâu và giải phóng khi nào?**
5. **Thay đổi credential có ảnh hưởng các request đang gửi không?**
6. **Giới hạn kết nối và tốc độ gửi của từng tenant/provider là bao nhiêu?**
7. **Có cần tách riêng bounce/địa chỉ phản hồi/sự kiện chuyển phát không?**

### Ví dụ interface của một tầng chọn sender

~~~java
public interface SenderRegistry {

    MailRoute resolve(String tenantId, MailPurpose purpose);
}

public record MailRoute(
        JavaMailSender sender,
        String fromAddress) {
}
~~~

Phần interface trên thể hiện **hợp đồng ứng dụng**, không phải API có sẵn của Spring. Một triển khai có thể tìm sender trong map cấu hình tin cậy hoặc cache những instance đã khởi tạo. Nó không nên chấp nhận bất kỳ chuỗi hostname/credential nào từ HTTP request rồi kết nối ngay.

Khi số lượng sender quá lớn hoặc chính sách gửi cần theo dõi quota, bounce và failover phức tạp, việc tách thành **mail delivery service chuyên dụng** hoặc dùng API của provider có thể phù hợp hơn việc tự nhân bản vô hạn các cấu hình SMTP trong một ứng dụng web.

### Cảnh báo về host động và SSRF

Nếu cho tenant nhập tùy ý SMTP host, port và dùng ứng dụng tạo kết nối mạng trực tiếp, hệ thống có thể bị lạm dụng như một cơ chế kết nối đến địa chỉ mạng nội bộ hoặc dịch vụ nhạy cảm. Nên giới hạn các endpoint được chấp nhận, kiểm soát egress network, kiểm tra quyền cấu hình và không trả chi tiết credential trong lỗi. Đây là vấn đề bảo mật của **hệ thống nhiều sender cấu hình động**, không thể được giải quyết chỉ bằng `JavaMailSender`.

## 11. Quản lý @Primary, @Qualifier và bean mặc định

Giả sử đã có hai bean:

~~~text
notificationMailSender: JavaMailSender
billingMailSender:      JavaMailSender
~~~

Nếu một service tiêm:

~~~java
public ReportService(JavaMailSender sender) { ... }
~~~

Spring cần biết chọn bean nào. Một số phương án:

| Phương án | Ý nghĩa | Điều cần cẩn trọng |
| --- | --- | --- |
| `@Qualifier("billingMailSender")` | Chọn đúng bean theo tên hoặc qualifier | Tên phải khớp cấu hình, phù hợp với mục đích |
| `@Primary` trên một bean | Chọn bean ưu tiên khi không có qualifier cụ thể | Có thể che việc service quên chọn sender theo nghiệp vụ |
| Tầng `MailRouter` | Dùng mục đích gửi để chọn sender | Router phải có policy rõ ràng, không chọn tùy ý |
| Tiêm một collection/map bean | Nhận nhiều bean, chọn theo key | Cần giới hạn key và quyền sử dụng |

Một ví dụ dùng map do Spring tiêm:

~~~java
@Service
public class SenderInspector {

    private final Map<String, JavaMailSender> senders;

    public SenderInspector(Map<String, JavaMailSender> senders) {
        this.senders = senders;
    }
}
~~~

`Map<String, JavaMailSender>` thường có key là **tên bean**. Kiểu injection này tiện cho tầng quản trị/registry đơn giản, nhưng không nên để client web truyền thẳng tên bean rồi tự chọn SMTP credential. Hãy ánh xạ từ **mục đích nghiệp vụ đã được cho phép** sang bean cụ thể.

### Có cần giữ spring.mail.* khi đã tự khai báo hai sender?

Nếu toàn bộ sender do ứng dụng tự định nghĩa bằng `app.mail.*`, có thể **không cần** dùng `spring.mail.host/port/username/password` cho cùng mục tiêu. Giữ hai nguồn cấu hình song song mà không có quy ước rõ ràng dễ gây hiểu lầm người vận hành.

Nếu cố ý duy trì một sender “mặc định” từ `spring.mail.*` cùng các sender khác, cần kiểm tra chính xác điều kiện auto-configuration và xác định bean được tạo như thế nào. Cách dễ dự đoán nhất trong hệ thống nhiều sender thường là **khai báo tường minh tất cả tuyến gửi quan trọng**.

## 12. Ràng buộc From, Reply-To và domain verification theo sender

Sau khi chọn đúng SMTP account, còn phải kiểm tra **From được phép dùng trên account đó**.

Ví dụ một router có thể định nghĩa:

~~~text
notificationMailSender:
  allowedFrom:
    - notify@example.org
    - support@example.org

billingMailSender:
  allowedFrom:
    - billing@example.org
~~~

Đây là dữ liệu chính sách minh họa, không phải một property chuẩn của Spring Boot. Khi service yêu cầu gửi bằng địa chỉ ngoài danh sách, router nên từ chối sớm theo hợp đồng của ứng dụng.

Một số nhà cung cấp áp dụng chính sách:

- Yêu cầu xác minh miền hoặc địa chỉ gửi.
- Cấu hình DKIM để ký thư bằng miền gửi.
- Kiểm tra SPF và chính sách DMARC cho khả năng xác thực miền.
- Giới hạn `From` hoặc `Reply-To` được sử dụng.
- Tạo địa chỉ envelope sender riêng phục vụ xử lý bounce.

Việc chọn đúng tài khoản SMTP mới chỉ là bước đầu. **Danh tính thư và cấu hình miền phải tương thích với nhà cung cấp đã chọn.**

Nếu có hai miền thương hiệu độc lập, không nên mặc định rằng cả hai có thể dùng chung một tài khoản chỉ vì kỹ thuật cho phép đổi `setFrom(...)`.

## 13. Tách cấu hình bí mật giữa các sender

Hệ thống nhiều sender có nhiều credential. Thay vì đặt tất cả vào một file chung dưới dạng văn bản, nên dùng biến môi trường hoặc secret manager cho từng tuyến.

Ví dụ tên biến:

~~~text
NOTIFY_SMTP_USERNAME
NOTIFY_SMTP_PASSWORD

BILLING_SMTP_USERNAME
BILLING_SMTP_PASSWORD
~~~

Các nguyên tắc:

1. Mỗi sender sử dụng **credential và quyền gửi phù hợp** với mục đích.
2. Tách credential giữa môi trường local, staging và production.
3. Quản lý xoay vòng/thu hồi credential theo từng provider để tránh một lỗi ảnh hưởng tất cả.
4. Không ghi username/password, nội dung MIME hoặc toàn bộ danh sách người nhận vào log nếu không cần thiết.
5. Không đưa credential thật vào repository, tài liệu huấn luyện hay biến đầu ra của exception.
6. Khi có tenant, kiểm tra quyền truy cập cấu hình để tenant A không đọc hoặc dùng secret của tenant B.
7. Nếu cache sender, có cơ chế thay thế/loại bỏ cache khi credential thay đổi.

Thay `username/password` trên một sender singleton theo từng request không phải cách quản lý secret an toàn. Với hệ thống thay đổi credential thường xuyên, cần một quy trình **cập nhật sender theo phiên bản cấu hình** và định nghĩa rõ lúc nào instance cũ không còn được sử dụng.

## 14. Vận hành nhiều sender: quota, timeout, retry và quan sát

Hai SMTP provider có thể có những chính sách rất khác nhau. Thêm nhiều bean không tự tạo hệ thống điều phối đáng tin cậy.

### 14.1. Cần giới hạn theo từng provider

Ví dụ:

| Chỉ tiêu | Sender thông báo | Sender hóa đơn |
| --- | --- | --- |
| Mức ưu tiên | Cao | Cao |
| Chính sách tốc độ | Theo quota notification provider | Theo quota billing provider |
| Timeout | Ngắn, theo SLA ứng dụng | Theo chính sách xử lý hóa đơn |
| Retry | Cho lỗi tạm thời | Cho lỗi tạm thời, kèm đối soát |
| Theo dõi bounce | Kênh notification | Kênh billing |

Bảng chỉ minh họa cách tư duy, không mô tả giới hạn của một nhà cung cấp cụ thể. **Số lượng sender tăng không đồng nghĩa tổng quota được chia đều hoặc được Spring tự theo dõi**.

### 14.2. Cần phân loại lỗi theo tuyến

Một email có thể thất bại vì:

- DNS hoặc kết nối tới SMTP host lỗi.
- Cấu hình port/TLS không tương thích.
- Username/password không hợp lệ hoặc credential hết hiệu lực.
- Sender không được phép dùng địa chỉ From.
- SMTP server tạm từ chối hoặc giới hạn tốc độ.
- Địa chỉ người nhận bị từ chối.
- Message bị trả lại sau khi relay chấp nhận.

Khi ghi nhận lỗi, hãy gắn **mã yêu cầu**, **mục đích gửi**, **senderId/providerId** và loại lỗi. Không cần ghi password hoặc raw email để truy vết được nguồn phát sinh.

### 14.3. Một lần send không chứng minh đã DELIVERED

`JavaMailSender.send(...)` trả về bình thường thông thường phản ánh việc thao tác nộp thư cho hạ tầng gửi đã hoàn tất theo phản hồi nhận được. Điều đó không bảo đảm người nhận đã có thư trong Inbox.

Muốn theo dõi chuyển phát theo sender/provider, có thể cần webhook, bounce mailbox, dashboard hoặc API sự kiện của nhà cung cấp. Hệ thống nhiều sender phải biết **sự kiện thuộc tài khoản nào**, tránh trộn trạng thái của các tuyến gửi.

### 14.4. Retry phải tôn trọng sender ban đầu và tính đúng đắn nghiệp vụ

Nếu hóa đơn được tạo từ sender billing nhưng lần retry lại chọn sender notification, việc thay tuyến có thể vi phạm quyền gửi hoặc tạo email không nhất quán. Trong hệ thống có hàng đợi, nên lưu các thuộc tính như:

~~~text
mail_request_id: 93f...
purpose: BILLING
sender_id: billing
recipient: buyer@example.net
template_id: invoice-ready
status: RETRY_WAITING
attempt_count: 2
~~~

Đây là một mô hình dữ liệu ứng dụng minh họa. `sender_id` giúp worker biết tuyến gửi đã được phê duyệt; khi failover có chủ đích, ứng dụng cần lưu **quyết định chọn tuyến thay thế** và lý do.

SMTP không có cam kết exactly-once cho việc gửi qua API ứng dụng. Nếu kết nối mất sau khi server đã nhận thư nhưng trước khi client thấy phản hồi cuối, việc gửi lại có thể tạo thư trùng. Nên sử dụng **outbox, khóa idempotency nghiệp vụ, giới hạn số lần retry và trạng thái UNKNOWN khi cần**.

## 15. Kiểm thử nhiều sender mà không gửi thư thật

Bài toán cần xác minh quan trọng nhất thường là **định tuyến đúng**:

- Thông báo tài khoản phải gọi sender notification.
- Hóa đơn phải gọi sender billing.
- Header From phù hợp với sender được chọn.
- Không có request nào dùng sai credential hoặc nhà cung cấp do một biến cấu hình dùng chung.
- Khi sender thông báo lỗi, hệ thống chỉ retry/failover theo chính sách được cho phép.

Có thể kiểm tra tầng router bằng cách thay các `JavaMailSender` bằng fake/mock riêng, rồi xác nhận sender nào nhận lệnh `send(...)`. Không cần mở kết nối SMTP thật cho những phép kiểm tra logic chọn tuyến.

Ví dụ mô hình:

~~~text
given:  purpose = BILLING
when:   mailRouter.send(...)
then:   billingMailSender.send(...) được gọi
and:    notificationMailSender.send(...) không được gọi
and:    From phù hợp billing
~~~

Khi muốn kiểm tra giao thức SMTP và TLS, có thể dùng SMTP test server hoặc sandbox do hệ thống kiểm thử quản lý. Cấu hình kiểm thử nên tách credential thật, tránh gửi thư ngoài ý muốn cho khách hàng.

Không dùng một mock duy nhất cho cả hai sender nếu muốn chứng minh router thực sự chọn đúng tuyến; cần hai đối tượng phân biệt và các assertion tương ứng.

### Tách ba lớp kiểm tra

| Lớp | Điều cần xác định |
| --- | --- |
| **Unit test của router** | Chọn đúng bean, đúng From, đúng purpose |
| **Integration test với SMTP test server** | Mỗi sender sử dụng host/port và cấu hình bảo mật đúng, message được tạo như mong muốn |
| **Vận hành thật** | Credential, quota, domain verification, bounce và khả năng chuyển phát của từng provider |

Mỗi lớp trả lời câu hỏi khác nhau. Một router hoạt động trong unit test không tự chứng minh SMTP provider ngoài Internet cho phép gửi.

## 16. Các lỗi thiết kế thường gặp

### 16.1. Dùng nhiều From rồi nghĩ đã có nhiều SMTP sender

~~~java
helper.setFrom("billing@example.org");
mailSender.send(message);
~~~

Đổi From **không đổi** `mailSender` đang được sử dụng. Nếu ứng dụng vẫn tiêm sender thông báo mặc định, message vẫn đi qua relay đó.

### 16.2. Tự đặt app.mail.billing.host mà không tạo bean

~~~properties
app.mail.billing.host=smtp.billing.example
~~~

Một khóa tùy chỉnh không tự làm Spring Boot sinh `billingMailSender`. Cần code hoặc cơ chế cấu hình của ứng dụng đọc khóa này và tạo sender tương ứng.

### 16.3. Có hai JavaMailSender nhưng tiêm không rõ bean

Một service có `JavaMailSender` không qualifier có thể nhận lỗi nhiều bean, hoặc nhận bean `@Primary` không đúng nghiệp vụ. Hãy sử dụng qualifier hoặc router.

### 16.4. Sửa JavaMailSenderImpl dùng chung theo mỗi request

Việc sửa host/credential trên đối tượng singleton có thể tạo race condition và lẫn dữ liệu giữa các request đồng thời. Dùng sender cố định theo tuyến hoặc registry có kiểm soát.

### 16.5. Cố gắng cấu hình cổng 465 bằng STARTTLS 587

Nếu một provider dùng implicit TLS và một provider dùng STARTTLS, phải cấu hình **riêng cho từng sender**. Không dùng một factory STARTTLS cho tất cả mà không kiểm tra loại kết nối.

### 16.6. Dùng router theo Subject hoặc tên miền người nhận

Subject có thể đổi vì dịch thuật, template hoặc dữ liệu người dùng; miền người nhận thường không nói lên mục đích nghiệp vụ. Nên truyền explicit `purpose`/`senderId` đã được kiểm soát thay vì suy đoán.

### 16.7. Chọn SMTP host động hoàn toàn từ input người dùng

Đây không chỉ là lỗi logic; nó có thể tạo đường kết nối mạng không được phép và lộ credential. Cần allowlist, quyền cấu hình, egress policy và xác thực tuyến được chọn.

### 16.8. Failover vô điều kiện qua một tài khoản khác

Một provider khác chưa chắc được phép gửi cùng From/domain. Tránh tự động chuyển tuyến chỉ vì provider đầu gặp lỗi; failover phải có ràng buộc về danh tính gửi và trạng thái đã nộp thư.

### 16.9. Dùng chung log và trạng thái rồi không biết sender nào lỗi

Khi có nhiều account, cần xác định provider và route trong log/metric. Không cần lộ credential để có khả năng quan sát tốt.

### 16.10. Nghĩ một lần gửi thành công nghĩa đã giao thư

Nhiều sender không làm thay đổi ý nghĩa của `JavaMailSender.send(...)`. Muốn biết DELIVERED/BOUNCED cần nguồn sự kiện chuyển phát đáng tin cậy.

## 17. Bài tập suy luận

**Câu 1.** Ứng dụng có ba địa chỉ From nhưng cả ba được SMTP relay xác minh và cho phép gửi qua cùng một tài khoản. Có bắt buộc tạo ba bean `JavaMailSender`?

**Không.** Có thể dùng một sender và đặt From thích hợp trên từng message, miễn đáp ứng chính sách của relay và cách ly dữ liệu nghiệp vụ.

**Câu 2.** `spring.mail.host=smtp.a.example` và ứng dụng thêm `app.mail.billing.host=smtp.b.example`. Spring Boot có tự tạo thêm sender billing không?

**Không.** `app.mail.billing.host` là khóa tùy chỉnh, cần cơ chế đọc cấu hình và tạo bean/registry tương ứng.

**Câu 3.** Có hai bean `notificationMailSender` và `billingMailSender`. Service nào cũng constructor-inject `JavaMailSender` không qualifier. Vấn đề có thể xảy ra?

Spring có thể không phân giải được bean phù hợp, hoặc dùng một bean mặc định không đúng luồng gửi. Dùng `@Qualifier` hoặc một router rõ ràng.

**Câu 4.** Muốn gửi hóa đơn từ tài khoản B nhưng chỉ gọi `helper.setFrom("billing@example.org")` trên message tạo từ sender A. Đã đổi tài khoản SMTP chưa?

**Chưa.** Thay header From không thay username/password, host hoặc SMTP transport.

**Câu 5.** Có nên sửa `setHost`/`setPassword` của một sender singleton mỗi request để tiết kiệm bộ nhớ?

**Không nên.** Đây là cấu hình mutable dùng chung; request đồng thời có thể làm lẫn thông số và gây lỗi gửi nhầm tuyến. Nên dùng sender được cấu hình độc lập hoặc factory/registry có quản lý.

**Câu 6.** Hệ thống có 200 tenant và mỗi tenant có SMTP credential riêng. Có nên viết 200 phương thức `@Bean` thủ công?

Thường không phải hướng dễ bảo trì. Một registry/factory được kiểm soát, chính sách tenant, quản lý secret, cache có giới hạn và monitoring theo provider phù hợp hơn.

**Câu 7.** Sender billing gặp timeout, sender notification đang khỏe. Có thể tự động gửi hóa đơn qua notification?

Chỉ khi đã có **chính sách failover được cho phép**, sender thay thế có quyền dùng From/domain liên quan và tình trạng gửi trước đó đã được xử lý để giảm trùng thư. Không nên tự ý chuyển.

**Câu 8.** Một message đã được relay tiếp nhận. Có thể ghi nhận `DELIVERED` cho người nhận chưa?

**Chưa.** Cần bằng chứng chuyển phát riêng, thường từ provider hoặc hạ tầng nhận. `send(...)` không tự cung cấp bảo đảm cuối cùng này.

## 18. Mô hình ghi nhớ

Trong Spring Boot, `spring.mail.*` là một **điểm khởi đầu tốt cho cấu hình SMTP đơn giản**, nhưng không phải hệ thống điều phối nhiều tài khoản gửi thư.

~~~mermaid
flowchart TD
    A["Yêu cầu gửi email"] --> B{"Mục đích và tenant?"}
    B --> C["Chính sách định tuyến"]
    C --> D["Sender thông báo"]
    C --> E["Sender hóa đơn"]
    C --> F["Sender khác được cấp quyền"]
    D --> G["SMTP provider A"]
    E --> H["SMTP provider B"]
    F --> I["SMTP provider N"]
~~~

Hãy ghi nhớ bốn ranh giới:

1. **From không phải SMTP account.** Đổi From chỉ đổi thông tin hiển thị của message, không tự đổi host và credential.
2. **Một `spring.mail.*` không tự tạo nhiều sender.** Muốn nhiều tuyến, hãy cấu hình các bean `JavaMailSender` hoặc một registry/factory rõ ràng.
3. **Nhiều bean cần cơ chế lựa chọn.** Dùng `@Qualifier`, `@Primary` có chủ đích, hoặc router theo mục đích/tenant đã được kiểm soát.
4. **Định tuyến đúng chưa đủ để bảo đảm gửi thành công.** Mỗi sender vẫn cần cấu hình TLS, quyền dùng From, secret, quota, retry và theo dõi chuyển phát riêng.

Khi hệ thống có ít tuyến cố định, hai hoặc ba bean được cấu hình độc lập thường dễ đọc và vận hành. Khi hệ thống có nhiều tenant hoặc thay đổi sender thường xuyên, hãy nâng cấp lên registry/factory và tầng quản trị tương ứng, thay vì biến một `JavaMailSenderImpl` dùng chung thành đối tượng bị sửa host/password trước mỗi lần gửi.

