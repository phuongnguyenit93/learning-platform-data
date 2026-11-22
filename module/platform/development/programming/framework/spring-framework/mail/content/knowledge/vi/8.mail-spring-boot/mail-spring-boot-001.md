# Auto-configuration cho mail sender

## 1. Spring Boot tự cấu hình mail sender là gì?

Trong **Spring Framework Mail**, ứng dụng thường sử dụng interface **MailSender** hoặc **JavaMailSender** để gửi email. Một triển khai phổ biến là **JavaMailSenderImpl**, sử dụng Jakarta Mail để giao tiếp với SMTP server. Nếu chỉ dùng Spring Framework thuần, lập trình viên phải tự tạo và cấu hình bean gửi thư hoặc dùng một cơ chế cấu hình tương đương.

**Spring Boot auto-configuration** giúp thực hiện phần lớn công việc lắp ghép ban đầu: khi ứng dụng có các thư viện cần thiết, có cấu hình mail thích hợp và chưa khai báo bean gửi thư thay thế, Boot có thể tự tạo một bean **JavaMailSender** cho Spring container. Service chỉ cần yêu cầu interface qua dependency injection.

Ví dụ cách sử dụng:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class RegistrationMailService {

    private final JavaMailSender mailSender;

    public RegistrationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.com");
        message.setTo(recipient);
        message.setSubject("Chào mừng bạn");
        message.setText("Tài khoản đã được tạo thành công.");
        mailSender.send(message);
    }
}
~~~

Trong ví dụ, **RegistrationMailService không tự khởi tạo JavaMailSenderImpl**. Nếu điều kiện auto-configuration được đáp ứng, Spring Boot tạo bean và Spring inject nó vào constructor. Mã nghiệp vụ không phải biết SMTP host, port, cách tạo Jakarta Mail Session hay chi tiết kết nối.

Tuy nhiên, **auto-configuration không đồng nghĩa đã có sẵn một SMTP server**, và cũng không có nghĩa cứ thêm dependency là email sẽ tự gửi. Ứng dụng vẫn cần thông tin máy chủ, quyền gửi, kết nối mạng và chính sách gửi thư phù hợp.

## 2. Vai trò của Spring Framework, Jakarta Mail và Spring Boot

Để hiểu đúng phạm vi auto-configuration, cần tách ba tầng:

| Tầng | Thành phần | Trách nhiệm |
|---|---|---|
| **Mã nghiệp vụ** | RegistrationMailService, NotificationService | Quyết định gửi email gì, cho ai, vào thời điểm nào. |
| **Spring Framework Mail** | MailSender, JavaMailSender, JavaMailSenderImpl, MimeMessageHelper | Cung cấp API tạo và gửi thông điệp; triển khai gửi qua nền tảng mail. |
| **Jakarta Mail** | Session, MimeMessage và SMTP transport | API/cơ chế xử lý MIME, phiên gửi thư và giao tiếp với máy chủ. |
| **Spring Boot** | Mail auto-configuration, MailProperties, starter | Đưa dependency và cấu hình lại với nhau, tự đăng ký bean khi điều kiện phù hợp. |
| **Hạ tầng bên ngoài** | SMTP relay, email service provider, mail server đích | Chấp nhận, định tuyến, chuyển phát và xử lý thông điệp qua các chặng. |

Hình dung quan hệ:

~~~text
                  Spring Boot application
                           |
                  @Service / Controller
                           |
                    JavaMailSender
                           ^
                           | tự cấu hình bean
                           |
               Spring Boot Mail auto-config
                           |
                           v
                   JavaMailSenderImpl
                           |
                           v
                       Jakarta Mail
                           |
                       SMTP/TLS
                           |
                           v
                SMTP relay hoặc email provider
                           |
                           v
                    Mail server người nhận
~~~

**JavaMailSender là interface của Spring Framework**, còn **Spring Boot tạo và cấu hình bean** từ thuộc tính môi trường. Từ đó, công việc gửi thư thông thường vẫn do JavaMailSenderImpl/Jakarta Mail thực hiện.

## 3. Thêm dependency spring-boot-starter-mail

Với ứng dụng **Spring Boot 3.x** dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Hoặc trong Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
~~~

Thông thường, phiên bản starter được quản lý bởi Spring Boot dependency management của dự án. Starter kéo theo các thành phần cần dùng cho Spring Mail và triển khai Jakarta Mail tương thích, giúp auto-configuration có các class cần thiết trên classpath.

Trong hệ sinh thái Spring Boot 3 / Spring Framework 6, các lớp thư tín bên dưới dùng **jakarta.mail**, ví dụ:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
~~~

Nếu dự án cũ đang dùng Spring Boot 2 và **javax.mail**, không sao chép lẫn lộn import giữa hai thế hệ. Namespace của Jakarta Mail phải khớp với framework và dependencies đang sử dụng.

**Chỉ thêm starter chưa đủ để cấu hình host SMTP.** Trong cấu hình phổ biến, phải đặt ít nhất thông tin máy chủ gửi qua **spring.mail.host**, hoặc cấu hình nguồn **Jakarta Mail Session** phù hợp như JNDI nếu môi trường sử dụng JNDI.

## 4. Những điều kiện Boot cần để tạo JavaMailSender

Auto-configuration trong Boot có nguyên tắc **chỉ áp dụng khi thích hợp và không ghi đè cấu hình do ứng dụng chủ động khai báo**. Với cấu hình mail thông dụng của Spring Boot 3.x, có thể hình dung các điều kiện chính:

1. **Các class cần thiết có trên classpath**, bao gồm Spring Mail và các API Jakarta Mail cần thiết. Starter mail là cách thông dụng để đáp ứng.
2. **Có thông tin để cấu hình sender**, thường là **spring.mail.host** hoặc **spring.mail.jndi-name** với một Jakarta Mail Session từ JNDI.
3. **Chưa có bean MailSender do ứng dụng hoặc thư viện khác khai báo**, để Boot có thể cung cấp một bean mặc định mà không xung đột với lựa chọn của ứng dụng.
4. **Auto-configuration mail không bị loại trừ** khỏi quá trình khởi động ứng dụng.

Tên lớp auto-configuration trong Spring Boot 3.x là **MailSenderAutoConfiguration**. Boot liên kết các thuộc tính dưới tiền tố **spring.mail** qua **MailProperties**, sau đó cấu hình sender bằng các thuộc tính đó hoặc một Session được tìm qua JNDI. Các annotation và điều kiện cụ thể có thể thay đổi giữa phiên bản Boot, nhưng nguyên tắc classpath + cấu hình + bean chưa tồn tại là trọng tâm cần nắm.

### Bảng tình huống

| Tình huống | Kết quả thường gặp |
|---|---|
| Có starter mail, có spring.mail.host, không khai báo MailSender riêng | Boot có thể tạo bean JavaMailSenderImpl và đăng ký theo interface JavaMailSender. |
| Có starter mail nhưng không có host/JNDI Session phù hợp | Không đủ điều kiện cho sender mặc định; service cần inject JavaMailSender có thể báo thiếu bean. |
| Thiếu dependency Spring Mail/Jakarta Mail phù hợp | Không có đủ class cho auto-configuration; ứng dụng không thể dùng API mail như mong đợi. |
| Ứng dụng tự khai báo bean MailSender hoặc JavaMailSender | Boot có thể **back off**, ưu tiên bean do ứng dụng cung cấp. |
| Có nhiều JavaMailSender do ứng dụng khai báo | Injection chỉ theo kiểu có thể bị mơ hồ; thường cần @Qualifier hoặc @Primary. |
| Auto-configuration đã tạo bean nhưng SMTP không truy cập được | Có thể khởi động được nếu không kiểm tra kết nối lúc startup; lỗi xuất hiện khi gửi hoặc khi bật kiểm tra kết nối. |

**Back off** nghĩa là Boot không cố tạo một sender mặc định khi đã phát hiện bean phù hợp do ứng dụng tự cung cấp. Nó không có nghĩa Spring sẽ tự sửa hay hoàn thiện cấu hình của bean tùy chỉnh.

### Một sơ đồ điều kiện khái quát

~~~text
                  Ứng dụng Spring Boot khởi động
                               |
                    Có thư viện mail cần thiết?
                           /             \
                         Không            Có
                          |                |
                    Không tạo sender    Có mail host/JNDI?
                                         /         \
                                       Không        Có
                                        |            |
                                  Không tạo       Đã có MailSender
                                  sender          bean khác?
                                                  /       \
                                                Có        Không
                                                 |           |
                                            Back off      Tạo sender
                                                         mặc định
~~~

Đây là cách diễn giải logic để học, không phải mã nguồn nguyên văn của auto-configuration.

## 5. Cấu hình SMTP bằng application.yml

Ví dụ phổ biến sử dụng SMTP submission qua cổng **587** và STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
~~~

Trong cấu hình này, **smtp.example.com** là địa chỉ minh họa; phải thay bằng SMTP host thật của nhà cung cấp. **SMTP_USERNAME** và **SMTP_PASSWORD** là các biến môi trường được cung cấp an toàn tại runtime. Không đưa mật khẩu thật vào file commit hoặc log.

Giải thích:

| Thuộc tính | Mục đích |
|---|---|
| **spring.mail.host** | SMTP server mà ứng dụng kết nối tới. |
| **spring.mail.port** | Cổng kết nối tới SMTP server. |
| **spring.mail.username** | Tên tài khoản đăng nhập nếu SMTP server yêu cầu xác thực. |
| **spring.mail.password** | Credential gửi email; cần quản lý bằng secret. |
| **spring.mail.default-encoding** | Charset mặc định sử dụng khi xây dựng thư, ví dụ UTF-8. |
| **spring.mail.properties.mail.smtp.auth** | Bật cơ chế SMTP AUTH ở Jakarta Mail. |
| **spring.mail.properties.mail.smtp.starttls.enable** | Cho phép nâng cấp kết nối sang TLS bằng STARTTLS. |
| **spring.mail.properties.mail.smtp.starttls.required** | Yêu cầu STARTTLS thành công thay vì chấp nhận gửi không nâng cấp. |
| **spring.mail.properties.mail.smtp.connectiontimeout** | Giới hạn thời gian chờ thiết lập kết nối, đơn vị mili giây. |
| **spring.mail.properties.mail.smtp.timeout** | Giới hạn thời gian chờ đọc từ SMTP server, đơn vị mili giây. |
| **spring.mail.properties.mail.smtp.writetimeout** | Giới hạn thời gian chờ thao tác ghi qua SMTP, đơn vị mili giây. |

Thuộc tính nằm trong **spring.mail.properties** được chuyển thành **Jakarta Mail properties**. Ví dụ đường dẫn YAML **properties.mail.smtp.auth** trở thành khóa **mail.smtp.auth** trong Session. Đây là cách Boot chuyển cấu hình transport bên dưới mà không yêu cầu ứng dụng tự khởi tạo Session.

### Vì sao timeout quan trọng?

Nếu không giới hạn thời gian chờ phù hợp, một sự cố mạng hoặc SMTP server không phản hồi có thể khiến luồng gửi bị giữ lâu ngoài dự kiến. Với service HTTP gửi email đồng bộ, điều này gây tăng độ trễ hoặc cạn tài nguyên khi có nhiều request.

Thiết lập timeout nên phù hợp với yêu cầu dịch vụ, độ trễ mạng và chính sách retry. **Timeout không bảo đảm email chưa được server nhận**: nếu kết nối đứt sau khi server đã xử lý DATA nhưng trước khi trả xác nhận, ứng dụng có thể không biết chắc kết quả.

### Không dùng nhầm cấu hình TLS

Ví dụ trên là mô hình **STARTTLS trên cổng 587**. Một số dịch vụ sử dụng **implicit TLS trên cổng 465**, cần cấu hình giao thức tương ứng, điển hình:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
~~~

Không mặc định đổi riêng **port** mà giữ nguyên cơ chế TLS. Hãy đối chiếu host, port, STARTTLS/SSL, chứng chỉ và cơ chế xác thực theo hướng dẫn của SMTP provider.

## 6. Quy trình từ thuộc tính tới bean được inject

Khi các điều kiện phù hợp:

~~~text
application.yml / environment / secrets
                    |
                    | Externalized Configuration
                    v
              spring.mail.*
                    |
                    v
              MailProperties
                    |
                    v
        MailSenderAutoConfiguration
                    |
                    v
           JavaMailSenderImpl bean
                    |
                    | Dependency Injection
                    v
         @Service NotificationService
                    |
                    v
            mailSender.send(...)
~~~

Điều này phù hợp với nguyên tắc dependency inversion: mã nghiệp vụ chỉ biết **JavaMailSender**; cấu hình transport được đặt ở môi trường triển khai. Khi đổi SMTP server, phần lớn thay đổi chỉ nằm trong cấu hình, không nằm trong service gửi thư.

**Lưu ý:** Spring Boot tạo được bean không có nghĩa đã tự chọn địa chỉ **From** cho mọi email. Địa chỉ header From thường được service thiết lập bằng **SimpleMailMessage.setFrom(...)**, **MimeMessageHelper.setFrom(...)** hoặc một lớp cấu hình nghiệp vụ riêng.

## 7. Ví dụ gửi plain text với sender được auto-configure

Sau khi cấu hình starter và SMTP, service sau có thể sử dụng sender được Boot inject:

~~~java
package com.example.notification;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class PasswordResetNotificationService {

    private final JavaMailSender mailSender;

    public PasswordResetNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendResetLink(String recipient, String resetUrl) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("support@example.com");
        message.setTo(recipient);
        message.setSubject("Đặt lại mật khẩu");
        message.setText("""
                Bạn đã yêu cầu đặt lại mật khẩu.

                Truy cập liên kết sau để tiếp tục:
                %s

                Nếu không yêu cầu, bạn có thể bỏ qua email này.
                """.formatted(resetUrl));

        mailSender.send(message);
    }
}
~~~

**JavaMailSender** kế thừa **MailSender**, nên có thể dùng **send(SimpleMailMessage)** dù service phụ thuộc vào interface JavaMailSender. Trường hợp cần email đơn giản, API này giúp tránh phải dựng cây MIME thủ công.

Mẫu này phục vụ giải thích cách auto-configuration được tiêu thụ. Trong ứng dụng thật, link reset phải là token có thời hạn, khó đoán và được kiểm soát quyền; không đưa token vào log. Dịch vụ cũng cần giới hạn tần suất gửi và tránh tiết lộ sự tồn tại của tài khoản nếu có yêu cầu bảo mật.

## 8. Ví dụ gửi HTML bằng JavaMailSender và MimeMessageHelper

Spring Boot không giới hạn sender được tạo tự động ở thư văn bản thuần. Bean **JavaMailSender** có thể gửi thông điệp MIME với HTML, bản text thay thế và file đính kèm.

~~~java
package com.example.notification;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceNotificationService {

    private final JavaMailSender mailSender;

    public InvoiceNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoiceNotice(String recipient, String invoiceCode)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Thông báo hóa đơn " + invoiceCode);

        String plainText = "Hóa đơn " + invoiceCode
                + " đã được phát hành. Truy cập cổng khách hàng để xem chi tiết.";
        String htmlText = "<html><body>"
                + "<h2>Hóa đơn đã được phát hành</h2>"
                + "<p>Vui lòng truy cập cổng khách hàng để xem chi tiết.</p>"
                + "</body></html>";

        helper.setText(plainText, htmlText);
        mailSender.send(message);
    }
}
~~~

Trong ví dụ:

1. **createMimeMessage()** tạo đối tượng MIME theo cấu hình gửi.
2. **MimeMessageHelper** cấu hình người gửi, người nhận, tiêu đề và nội dung.
3. Overload **setText(plainText, htmlText)** tạo hai biểu diễn thay thế theo MIME, phù hợp với email client hiển thị plain text hoặc HTML.
4. **send(message)** thực hiện yêu cầu gửi thư thông qua bean đã được Boot cấu hình.

Nếu muốn thêm attachment, sử dụng **helper.addAttachment(...)** khi đã bật chế độ multipart; nếu muốn ảnh inline, có thể sử dụng **helper.addInline(...)** theo cấu trúc MIME thích hợp. Chức năng này thuộc Spring Framework Mail, còn Boot giúp đăng ký và cấu hình sender.

## 9. Tùy chỉnh một số giá trị qua cấu hình ngoài

Không nên hardcode địa chỉ From trong nhiều service khi tất cả đều dùng chung một danh tính gửi. **spring.mail** chủ yếu dùng cho cấu hình mail transport; ứng dụng có thể định nghĩa thuộc tính riêng, chẳng hạn:

~~~yaml
app:
  notification:
    from: no-reply@example.com
    reply-to: support@example.com
~~~

Sau đó inject vào service:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class StatusMailService {

    private final JavaMailSender sender;
    private final String from;
    private final String replyTo;

    public StatusMailService(
            JavaMailSender sender,
            @Value("${app.notification.from}") String from,
            @Value("${app.notification.reply-to}") String replyTo
    ) {
        this.sender = sender;
        this.from = from;
        this.replyTo = replyTo;
    }

    public void sendStatus(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setReplyTo(replyTo);
        message.setTo(recipient);
        message.setSubject("Trạng thái xử lý");
        message.setText("Yêu cầu của bạn đã được xử lý.");
        sender.send(message);
    }
}
~~~

Thuộc tính **app.notification** là namespace do ứng dụng tự định nghĩa; Spring Boot không tự biến nó thành header mail. Service cần dùng nó để đặt header **From** và **Reply-To**.

Điều này cũng cho thấy phải phân biệt:

- **SMTP username**: thông tin xác thực khi ứng dụng nộp thư.
- **Header From**: địa chỉ gửi được người nhận nhìn thấy.
- **Reply-To**: nơi email client thường hướng câu trả lời.
- **SMTP envelope sender / return path**: thông tin gửi dùng trong vận chuyển và xử lý bounce.

Các giá trị có thể khác nhau nhưng phải phù hợp với chính sách của SMTP provider, quyền dùng địa chỉ và cấu hình xác thực miền.

## 10. Nếu đã có một JavaMailSender do ứng dụng tự khai báo

Auto-configuration thường áp dụng nguyên tắc **back off** khi phát hiện bean sender phù hợp. Điều này hữu ích vì ứng dụng có thể tự quyết định cấu hình khi yêu cầu đặc biệt.

Ví dụ tự đăng ký sender:

~~~java
import java.util.Properties;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class CustomMailConfiguration {

    @Bean
    public JavaMailSender javaMailSender(
            @Value("${app.smtp.host}") String host,
            @Value("${app.smtp.port}") int port,
            @Value("${app.smtp.username}") String username,
            @Value("${app.smtp.password}") String password
    ) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.setProperty("mail.smtp.auth", "true");
        properties.setProperty("mail.smtp.starttls.enable", "true");
        properties.setProperty("mail.smtp.starttls.required", "true");
        properties.setProperty("mail.smtp.connectiontimeout", "5000");
        properties.setProperty("mail.smtp.timeout", "5000");
        properties.setProperty("mail.smtp.writetimeout", "5000");
        return sender;
    }
}
~~~

Với cách này ứng dụng phải tự cung cấp các thuộc tính **app.smtp.***, ví dụ từ cấu hình môi trường. Các giá trị này **không phải spring.mail.*** nên chúng không tự nhận giá trị từ phần auto-configuration mặc định. Khi đã tạo bean thủ công, hãy chịu trách nhiệm đầy đủ cho TLS, timeout, tài khoản và những lựa chọn vận hành của bean đó.

Ví dụ trên phù hợp với SMTP submission dùng STARTTLS. Nếu hệ thống sử dụng JNDI Session, implicit TLS hoặc một provider yêu cầu cấu hình riêng, cách tạo sender phải được điều chỉnh.

**Khi nào cần bean thủ công?** Khi có nhiều sender, muốn dùng một Jakarta Mail Session được quản lý đặc biệt, cần tùy biến transport sâu, hoặc muốn kiểm soát rõ việc chọn bean. Với một SMTP account thông dụng, auto-configuration của Boot thường là lựa chọn đơn giản và dễ bảo trì.

## 11. Nhiều sender và @Qualifier

Nếu ứng dụng có nhiều loại thư, ví dụ transactional và campaign, có thể khai báo hai bean **JavaMailSender**. Spring không tự suy đoán bean nào nên xử lý từng loại email.

~~~java
@Bean("transactionalMailSender")
JavaMailSender transactionalMailSender() {
    // Trả về JavaMailSenderImpl đã cấu hình cho thư giao dịch.
    throw new UnsupportedOperationException("Configuration example");
}

@Bean("campaignMailSender")
JavaMailSender campaignMailSender() {
    // Trả về JavaMailSenderImpl đã cấu hình cho chiến dịch.
    throw new UnsupportedOperationException("Configuration example");
}
~~~

Đoạn trên **chỉ minh họa tên bean và chủ đích cấu hình**; không phải phương thức có thể chạy để gửi thư. Trong code thực tế, mỗi phương thức phải trả về sender đã được cấu hình, không ném ngoại lệ như placeholder.

Các service nên inject rõ tên:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class TransactionalEmailGateway {

    private final JavaMailSender sender;

    public TransactionalEmailGateway(
            @Qualifier("transactionalMailSender") JavaMailSender sender
    ) {
        this.sender = sender;
    }
}
~~~

Với nhiều bean cùng kiểu, injection chỉ theo interface **JavaMailSender** có thể không chọn được bean duy nhất và báo **NoUniqueBeanDefinitionException**. Có thể dùng **@Qualifier**, **@Primary** khi cố tình định nghĩa một sender mặc định, hoặc tạo router để định tuyến theo mục đích nghiệp vụ.

**Hai bean gửi mail không tự sinh hai queue, retry policy hoặc giới hạn tốc độ.** Muốn tách tài nguyên gửi thật sự, cần cấu hình transport, worker, quota và hạ tầng nhà cung cấp phù hợp.

## 12. Tận dụng Jakarta Mail Session từ JNDI

Một số môi trường có application server hoặc hạ tầng quản lý **Jakarta Mail Session** ngoài ứng dụng. Trong trường hợp đó, Spring Boot có thể cấu hình lấy Session từ **JNDI**:

~~~yaml
spring:
  mail:
    jndi-name: java:comp/env/mail/Session
~~~

Tên JNDI chỉ mang tính ví dụ. Môi trường chạy phải thực sự cung cấp resource với tên đó và cấu hình Session phù hợp. Nếu ứng dụng chạy như một Spring Boot executable JAR thông thường mà không có mail Session được đăng ký ở JNDI, đặt thuộc tính này sẽ không tự tạo ra resource.

**Khi spring.mail.jndi-name được sử dụng, Session lấy từ JNDI được ưu tiên hơn các thuộc tính tạo Session thông thường.** Những cấu hình SMTP phía container/JNDI cần được kiểm tra ở nơi resource được định nghĩa.

JNDI có ích khi đơn vị vận hành muốn quản lý kết nối mail tập trung tại application server. Với phần lớn microservice chạy độc lập trên container, cấu hình trực tiếp qua **spring.mail.host** và biến môi trường thường dễ vận hành hơn.

## 13. spring.mail.test-connection làm gì?

Trong Spring Boot, có thể bật kiểm tra kết nối SMTP khi ứng dụng khởi động:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

Khi chức năng kiểm tra được áp dụng với sender phù hợp, Boot thử kết nối đến hệ thống mail lúc startup. Nếu máy chủ không truy cập được hoặc cấu hình transport thất bại, việc khởi động có thể báo lỗi sớm thay vì đợi đến email đầu tiên.

| test-connection | Hành vi kỳ vọng |
|---|---|
| **false** (mặc định thông dụng) | Không chủ động kiểm tra kết nối SMTP lúc startup; vấn đề kết nối có thể chỉ bộc lộ khi gửi. |
| **true** | Yêu cầu kiểm tra kết nối mail khi khởi động, giúp phát hiện lỗi cấu hình/khả dụng sớm. |

**Giới hạn của phép kiểm tra:** Kết nối thành công không chứng minh SMTP server sẽ cho phép mọi địa chỉ From, người nhận hay nội dung thư. Nó cũng không chứng minh DNS SPF/DKIM/DMARC đúng, email đã được chuyển phát hoặc thư sẽ vào Inbox. Nhà cung cấp có thể từ chối tại lệnh MAIL FROM, RCPT TO hoặc DATA dù kết nối ban đầu thành công.

Việc bật kiểm tra lúc khởi động cũng ảnh hưởng đến khả năng sẵn sàng của dịch vụ: một SMTP outage tạm thời có thể khiến ứng dụng không khởi động được. Nên chọn hành vi theo yêu cầu hệ thống, đặc biệt khi gửi email chỉ là chức năng phụ và hệ thống vẫn cần phục vụ các API khác.

## 14. Cách nhận biết auto-configuration có hoạt động

Nếu service báo không tìm thấy bean **JavaMailSender**, hãy kiểm tra theo thứ tự:

1. **Dependency**: dự án có starter mail hoặc các thư viện Spring Mail/Jakarta Mail tương thích không?
2. **Thuộc tính host/JNDI**: môi trường đang chạy có nhận **spring.mail.host** hoặc **spring.mail.jndi-name** hay không?
3. **Profile và file cấu hình**: ứng dụng có đang chạy đúng Spring profile, đúng file và đúng biến môi trường không?
4. **Bean do ứng dụng khai báo**: có MailSender bean nào khiến auto-configuration back off hay không?
5. **Loại bean cần inject**: service yêu cầu JavaMailSender nhưng dự án chỉ cung cấp một MailSender khác, hoặc có nhiều JavaMailSender chưa phân biệt qualifier?
6. **Auto-configuration exclusions**: có cấu hình loại trừ MailSenderAutoConfiguration hay không?
7. **Điều kiện khởi tạo**: kiểm tra condition evaluation report của Boot để biết điều kiện nào phù hợp hoặc không phù hợp.

Spring Boot có **condition evaluation report** để giải thích vì sao từng auto-configuration được áp dụng hoặc bị bỏ qua. Khi cần chẩn đoán trong môi trường phát triển, có thể bật chế độ debug của Boot, ví dụ:

~~~properties
debug=true
~~~

Hoặc sử dụng công cụ quan sát điều kiện cấu hình được cung cấp trong môi trường có Spring Boot Actuator và endpoint thích hợp. Không nên bật logging quá chi tiết dài hạn ở production; các thông tin cấu hình hoặc SMTP debug có thể chứa dữ liệu nhạy cảm.

### Bean có rồi nhưng không gửi được

Khi injection thành công mà lệnh send() vẫn thất bại, lỗi có thể nằm ở SMTP:

- Host hoặc port sai, DNS không phân giải được.
- Firewall hoặc chính sách mạng chặn kết nối.
- STARTTLS/implicit TLS không khớp, chứng chỉ không hợp lệ.
- Credential sai, bị thu hồi hoặc chưa có quyền SMTP AUTH.
- Tài khoản không được phép dùng địa chỉ From.
- SMTP server từ chối relay, địa chỉ người nhận, kích thước thư hoặc tần suất gửi.
- Hệ thống nhận chặn spam, SPF/DKIM/DMARC hoặc xử lý thư vào Junk/Spam.

Những vấn đề này không nhất thiết là lỗi của auto-configuration. **Tạo được JavaMailSender bean chỉ là bước cấu hình một client gửi thư.**

## 15. Các exception thường gặp khi gửi qua auto-configured sender

Spring Mail cung cấp một nhóm exception ở tầng ứng dụng:

| Exception | Tình huống thường gặp | Hướng điều tra |
|---|---|---|
| **MailAuthenticationException** | SMTP AUTH thất bại | Kiểm tra credential, quyền tài khoản, yêu cầu xác thực provider. |
| **MailSendException** | Thất bại trong quá trình gửi | Xem nguyên nhân gốc, SMTP reply, lỗi theo từng recipient nếu có. |
| **MailPreparationException** | Lỗi chuẩn bị MimeMessage hoặc callback | Kiểm tra dữ liệu, template, attachment, cách dựng MIME. |
| **MailParseException** | Không thể tạo hoặc diễn giải thông điệp hợp lệ | Kiểm tra địa chỉ, header và cấu trúc message. |

Trong luồng MIME, **jakarta.mail.MessagingException** cũng có thể phát sinh khi xây dựng nội dung, ví dụ qua MimeMessageHelper. Hãy phân biệt **lỗi chuẩn bị thông điệp** và **lỗi vận chuyển SMTP** trước khi áp dụng retry.

Một lỗi network hoặc timeout đúng thời điểm nộp dữ liệu có thể khiến trạng thái **đã được SMTP server chấp nhận hay chưa** không rõ ràng. Gửi lại ngay có nguy cơ gây thư trùng. Với chức năng quan trọng, nên quản lý attempt ID, notification ID và đối chiếu log nhà cung cấp.

## 16. Gửi mail đồng bộ, queue và môi trường triển khai

Auto-configuration của Boot tạo và cấu hình bean gửi thư; nó **không tự tạo queue**, không tự chạy worker nền, không đảm bảo retry và không tạo giao dịch phân tán với database. Theo cách dùng thông thường:

~~~java
mailSender.send(message);
~~~

Lời gọi này là **đồng bộ đối với thread đang gọi**: thread chờ việc chuẩn bị/giao tiếp với hệ thống gửi hoàn thành hoặc nhận exception. Sự thành công của send() thường chỉ cho biết SMTP server ở chặng nộp thư đã chấp nhận yêu cầu; nó không bảo đảm người nhận thấy thư trong Inbox.

Nếu cần gửi lượng lớn hoặc tránh làm chậm HTTP request, hệ thống có thể dùng queue hoặc transactional outbox:

~~~text
HTTP request / business event
               |
               v
   Ghi dữ liệu nghiệp vụ + outbox
               |
             COMMIT
               |
               v
          Mail worker
               |
               v
      Auto-configured JavaMailSender
               |
               v
          SMTP relay
               |
               v
         Mail server đích
~~~

Outbox giúp ghi lại **ý định gửi thư** cùng dữ liệu nghiệp vụ một cách nhất quán khi dùng transaction database phù hợp. Tuy vậy, nó không tự tạo bảo đảm exactly-once: worker có thể gửi thư rồi dừng trước khi cập nhật trạng thái. Cần chính sách retry, chống gửi trùng và xử lý kết quả chưa rõ ở tầng ứng dụng.

### Cấu hình cho từng môi trường

Trong hệ thống thật, thông số SMTP giữa local, staging và production có thể khác nhau:

| Môi trường | Lựa chọn thường dùng |
|---|---|
| **Local development** | SMTP test inbox hoặc mail server giả lập; không gửi email cho khách hàng thật. |
| **Integration testing** | Fake JavaMailSender hoặc SMTP test server có thể quan sát thư đã tạo. |
| **Staging** | SMTP sandbox hoặc tài khoản thử nghiệm với domain/người nhận kiểm soát. |
| **Production** | SMTP/ESP thực, credentials an toàn, TLS, timeout, giám sát, rate limit và chính sách retry. |

Cấu hình được phân tách bằng **Spring profiles**, biến môi trường hoặc nền tảng quản lý cấu hình. Tránh để profile phát triển sử dụng credential và danh sách người nhận production.

## 17. Kiểm thử logic gửi email không cần SMTP thật

Auto-configuration hữu ích khi chạy ứng dụng thật; nhưng trong unit test của service, không bắt buộc kết nối SMTP. Vì service phụ thuộc vào interface **JavaMailSender**, có thể cung cấp fake hoặc mock để quan sát nội dung thông điệp.

Ví dụ ý tưởng với Mockito:

~~~java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

class RegistrationMailServiceTest {

    @Test
    void createsWelcomeMessage() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RegistrationMailService service = new RegistrationMailService(sender);

        service.sendWelcome("learner@example.net");

        ArgumentCaptor<SimpleMailMessage> captured =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captured.capture());

        SimpleMailMessage message = captured.getValue();
        assertEquals("learner@example.net", message.getTo()[0]);
        assertEquals("Chào mừng bạn", message.getSubject());
    }
}
~~~

Đoạn minh họa giả định dự án có JUnit 5 và Mockito. Nó kiểm tra service tạo thông điệp và gọi interface, **không kiểm tra khả năng kết nối SMTP**. Muốn kiểm tra binding **spring.mail** và bean được auto-configured trong ApplicationContext, cần integration test riêng. Muốn kiểm tra quá trình gửi thực, dùng test SMTP server hoặc sandbox phù hợp.

## 18. Những hiểu nhầm thường gặp

**“Có spring-boot-starter-mail là dùng được JavaMailSender ngay?”** Chưa chắc. Auto-configuration còn phụ thuộc vào điều kiện cấu hình như host/JNDI và bean đang tồn tại. Thêm dependency không cung cấp một máy chủ SMTP.

**“Auto-configuration tạo sẵn mọi header From, To và Subject?”** Không. Boot cấu hình cơ chế gửi. Ứng dụng vẫn chịu trách nhiệm xây nội dung và những header cụ thể cho từng email.

**“Cài đặt spring.mail.host bảo đảm thư đến Inbox?”** Không. Host chỉ là nơi ứng dụng nộp thư; nhà cung cấp, DNS, máy chủ nhận và bộ lọc thư quyết định nhiều chặng tiếp theo.

**“Khai báo JavaMailSenderImpl thủ công thì Boot sẽ trộn spring.mail.* vào bean đó?”** Không nên giả định. Khi tự tạo bean, ứng dụng phải cấu hình bean và hiểu cơ chế back off; các thuộc tính của Boot không tự được áp vào mọi bean do người dùng viết.

**“Hai bean JavaMailSender có thể inject tự động mà không cần chỉ định?”** Nếu có nhiều candidate, Spring có thể báo injection mơ hồ. Hãy dùng @Qualifier hoặc một chiến lược lựa chọn bean rõ ràng.

**“test-connection=true kiểm chứng khả năng phát thư đến người nhận?”** Không. Nó chỉ kiểm tra kết nối ở phạm vi hỗ trợ của sender và cấu hình; SMTP acceptance, spam, bounce hoặc Inbox là những bước khác.

**“JavaMailSender.send() tự động chạy nền?”** Không. Lời gọi thông thường đồng bộ. Nếu cần async, queue hoặc outbox phải thiết kế riêng.

**“Spring Boot luôn sử dụng javax.mail?”** Không với Spring Boot 3 / Spring Framework 6; API mail nền sử dụng namespace jakarta.mail.

## 19. Ghi nhớ

**Spring Boot auto-configuration cho mail sender** giúp ứng dụng tạo bean **JavaMailSender** mà không phải tự viết lớp cấu hình SMTP thông thường. Với **spring-boot-starter-mail**, thuộc tính **spring.mail.host**, **spring.mail.port**, **spring.mail.username**, **spring.mail.password** và các **spring.mail.properties.mail.smtp.***, Boot có thể cấu hình **JavaMailSenderImpl** rồi inject vào service thông qua interface.

Auto-configuration chỉ hoạt động khi đáp ứng các điều kiện về classpath, cấu hình và sự hiện diện của bean. Khi ứng dụng tự đăng ký MailSender/JavaMailSender hoặc cần nhiều sender, phải chủ động tổ chức bean, qualifier và cấu hình tương ứng. JNDI Session và **spring.mail.test-connection** là những lựa chọn bổ sung cho các môi trường đặc thù.

Cuối cùng, **tự cấu hình sender không đồng nghĩa tự vận hành toàn bộ hệ thống email**. Ứng dụng vẫn phải tạo nội dung chính xác, quản lý credentials, TLS, timeout và phản hồi SMTP; nếu cần độ tin cậy cao, phải bổ sung cơ chế queue, retry, giám sát và xử lý trạng thái gửi không chắc chắn.
