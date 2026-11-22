# Spring hỗ trợ tạo và gửi thư ở lớp trừu tượng nào?

## 1. Câu trả lời trực tiếp

Trong **Spring Framework Mail**, Spring cung cấp **tầng trừu tượng gửi email (mail-sending abstraction)** thông qua hai interface chính trong gói **org.springframework.mail**:

- **MailSender**: hợp đồng gửi thư đơn giản, thường là email văn bản thuần (plain text), sử dụng đối tượng **SimpleMailMessage**.
- **JavaMailSender**: interface mở rộng **MailSender**, cho phép tạo và gửi email theo chuẩn MIME, gồm HTML, nhiều người nhận, tệp đính kèm và nội dung phức tạp. Các API liên quan nằm trong gói **org.springframework.mail.javamail**.

Một triển khai thông dụng là **JavaMailSenderImpl**. Lớp này thực hiện các hợp đồng Spring Mail và giao tiếp với hệ thống email thông qua **Jakarta Mail** và máy chủ SMTP.

Vì vậy, nếu câu hỏi dùng cụm “lớp trừu tượng” theo nghĩa thiết kế phần mềm thì câu trả lời chính xác là **tầng abstraction ở phía ứng dụng, được biểu diễn chủ yếu bằng các interface MailSender và JavaMailSender**. Đây là các *interface*, không phải hai abstract class. **SimpleMailMessage** và **MimeMessageHelper** là các kiểu hỗ trợ tạo nội dung thư; chúng không thay thế hợp đồng gửi thư.

## 2. Tại sao Spring cần tầng trừu tượng gửi thư?

Ứng dụng thường cần gửi email xác nhận tài khoản, thông báo đơn hàng, đặt lại mật khẩu hoặc báo cáo. Nếu mã nghiệp vụ trực tiếp khởi tạo kết nối SMTP, cấu hình phiên gửi thư, dựng định dạng MIME và xử lý lỗi thư viện bên dưới, mỗi chức năng sẽ phụ thuộc chặt vào chi tiết hạ tầng.

Spring tách hai trách nhiệm:

1. **Mã nghiệp vụ** quyết định *gửi thư gì, cho ai, vào lúc nào*.
2. **Thành phần gửi thư** chịu trách nhiệm *biểu diễn thông điệp và chuyển thông điệp tới hệ thống email*.

Ứng dụng có thể khai báo phụ thuộc vào **JavaMailSender** thay vì trực tiếp tạo **JavaMailSenderImpl**. Khi đổi máy chủ SMTP, thông tin xác thực hoặc cách cấu hình, phần lớn mã nghiệp vụ không cần thay đổi. Trong kiểm thử, có thể thay đối tượng gửi thật bằng một đối tượng giả để ghi nhận lời gọi.

### Luồng xử lý

~~~text
Controller / Domain Service / Scheduled Job
                  |
                  v
             EmailService
                  |
                  v
       MailSender / JavaMailSender     <- Hợp đồng của Spring
                  |
                  v
          JavaMailSenderImpl           <- Triển khai phổ biến
                  |
                  v
             Jakarta Mail             <- API/thư viện email nền
                  |
                  v
           Máy chủ SMTP                <- Hạ tầng chuyển phát
                  |
                  v
          Hệ thống thư người nhận
~~~

**Phạm vi của abstraction:** Spring giúp ứng dụng tạo, gửi và xử lý lỗi khi chuyển giao thư cho hệ thống gửi. Nó **không** tự cung cấp một máy chủ SMTP, không bảo đảm thư chắc chắn vào hộp thư đến và không tự thực hiện hàng đợi hay cơ chế gửi lại đáng tin cậy.

## 3. Các thành phần cần phân biệt

| Thành phần | Vai trò | Khi nào dùng? |
|---|---|---|
| **MailSender** | Interface gửi **SimpleMailMessage**; hợp đồng cơ bản cho thư đơn giản | Chỉ cần thư văn bản thuần |
| **SimpleMailMessage** | Đối tượng dữ liệu mô tả địa chỉ gửi/nhận, tiêu đề và nội dung text | Chuẩn bị thư plain text nhanh gọn |
| **JavaMailSender** | Interface mở rộng MailSender, hỗ trợ **MimeMessage** và các phương thức chuẩn bị thư MIME | HTML, đính kèm, inline image, định dạng phức tạp |
| **JavaMailSenderImpl** | Triển khai JavaMailSender thường được cấu hình làm Spring bean | Kết nối dịch vụ email thông qua Jakarta Mail/SMTP |
| **MimeMessage** | Kiểu thông điệp MIME của Jakarta Mail | Biểu diễn email nhiều phần, HTML và tệp đính kèm |
| **MimeMessageHelper** | Tiện ích Spring hỗ trợ thiết lập MimeMessage | Giảm mã thao tác trực tiếp với MIME |
| **MimeMessagePreparator** | Callback để chuẩn bị MimeMessage khi gửi qua JavaMailSender | Muốn tách bước dựng thư khỏi lệnh gửi |
| **MailException** | Hệ thống exception của Spring Mail | Bắt hoặc xử lý lỗi gửi email ở tầng ứng dụng |

Các tên dễ gây nhầm lẫn:

- **MailSender** là *interface gửi*, còn **SimpleMailMessage** là *dữ liệu của thư*; không có thao tác gửi trên SimpleMailMessage.
- **JavaMailSender** là *hợp đồng của Spring*, còn **JavaMailSenderImpl** là *một lớp triển khai* hợp đồng đó.
- **MimeMessage** thuộc Jakarta Mail; **MimeMessageHelper** thuộc Spring và giúp sử dụng MimeMessage dễ hơn.
- Tên “JavaMailSender” được giữ trong Spring API dù những ứng dụng Spring Framework 6 / Spring Boot 3 hiện đại sử dụng namespace **jakarta.mail** thay cho **javax.mail** ở API email bên dưới.

### Quan hệ interface và triển khai

~~~text
               MailSender
                  ^
                  | extends
             JavaMailSender
                  ^
                  | implements
           JavaMailSenderImpl
~~~

Nhờ quan hệ này, một bean **JavaMailSenderImpl** có thể được sử dụng qua kiểu **MailSender** cho tác vụ đơn giản hoặc qua kiểu **JavaMailSender** khi cần MIME.

## 4. Ví dụ 1: Tạo và gửi email văn bản thuần

Ví dụ sau cho thấy service chỉ phụ thuộc vào interface **MailSender**. Đây là cách thể hiện rõ nhất ý nghĩa abstraction khi chức năng không cần HTML hay tệp đính kèm.

~~~java
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final MailSender mailSender;

    public WelcomeMailService(MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.com");
        message.setTo(recipient);
        message.setSubject("Chào mừng bạn");
        message.setText("Tài khoản của bạn đã được tạo thành công.");

        mailSender.send(message);
    }
}
~~~

Ở đây:

1. **SimpleMailMessage** chứa các trường của email.
2. **MailSender.send(...)** thực hiện yêu cầu gửi.
3. Service không cần biết chi tiết kết nối SMTP, phiên Jakarta Mail hay lớp triển khai thực tế.

Đoạn mã giả định ứng dụng đã cấu hình bean gửi thư. Giá trị địa chỉ người gửi phải phù hợp với chính sách của tài khoản/dịch vụ SMTP thực tế.

## 5. Ví dụ 2: Gửi email HTML qua JavaMailSender

Khi cần định dạng nội dung hoặc gửi file đính kèm, sử dụng **JavaMailSender**. Ví dụ tạo email HTML:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendHtmlNotice(String recipient) throws MessagingException {
        MimeMessage mimeMessage = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage,
                false,
                StandardCharsets.UTF_8.name()
        );
        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Thông báo tài khoản");
        helper.setText(
                "<h2>Xin chào!</h2><p>Tài khoản của bạn đã sẵn sàng.</p>",
                true
        );

        mailSender.send(mimeMessage);
    }
}
~~~

**Giải thích những điểm quan trọng:**

- **createMimeMessage()** yêu cầu JavaMailSender tạo thông điệp Jakarta Mail phù hợp với cấu hình gửi thư.
- **MimeMessageHelper** thiết lập From, To, Subject và nội dung dễ dàng hơn so với thao tác trực tiếp với MIME.
- Tham số **true** ở **setText(html, true)** đánh dấu nội dung là HTML.
- Tham số **false** trong constructor ở ví dụ trên cho biết không bật chế độ multipart; nếu cần tệp đính kèm hoặc tài nguyên inline thì sử dụng chế độ multipart thích hợp.
- **mailSender.send(mimeMessage)** thực hiện việc gửi. **MessagingException** có thể xuất hiện trong bước chuẩn bị thông điệp; lỗi gửi do Spring Mail có thể được báo qua các subtype của **MailException**.

Ví dụ khi cần đính kèm tài liệu:

~~~java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mimeMessage, true, StandardCharsets.UTF_8.name()
);

helper.setFrom("no-reply@example.com");
helper.setTo("recipient@example.com");
helper.setSubject("Báo cáo");
helper.setText("Xem báo cáo trong tệp đính kèm.");
helper.addAttachment("report.pdf", reportFile); // reportFile là java.io.File có sẵn

mailSender.send(mimeMessage);
~~~

Phần tạo nội dung báo cáo, quản lý file và kiểm soát kích thước/loại tệp là trách nhiệm riêng của ứng dụng.

## 6. Cấu hình tầng gửi thư trong Spring Boot

Với ứng dụng Spring Boot, có thể bổ sung dependency **spring-boot-starter-mail** để sử dụng cơ chế tự cấu hình email của Boot. Đây là phần **tích hợp thuận tiện do Spring Boot cung cấp**, còn các interface **MailSender** và **JavaMailSender** vẫn thuộc Spring Framework.

Ví dụ với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Ví dụ cấu hình trong **application.yml**:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: mail-account@example.com
    password: REPLACE_WITH_SECRET
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
~~~

Trong dự án thực tế, **không đưa mật khẩu SMTP thật vào mã nguồn hoặc tệp cấu hình được commit**. Hãy lấy thông tin xác thực từ biến môi trường hoặc hệ thống quản lý bí mật. Các tham số SMTP (TLS, cổng, cơ chế xác thực) cần phù hợp với nhà cung cấp email.

Khi điều kiện tự cấu hình được đáp ứng, Spring Boot có thể đăng ký một bean **JavaMailSender**. Nhờ dependency injection, các service ở ví dụ trên nhận bean này qua constructor. Nếu dùng Spring Framework thuần, ứng dụng cần tự cấu hình một triển khai **JavaMailSender**, thường là **JavaMailSenderImpl**.

### Nếu muốn cấu hình thủ công

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setDefaultEncoding("UTF-8");
        // Credentials và các JavaMail properties cần được cấp từ cấu hình an toàn.
        return sender;
    }
}
~~~

Đây là đoạn minh họa cách ánh xạ **interface → implementation**, chưa phải cấu hình hoàn chỉnh để gửi qua một SMTP server yêu cầu đăng nhập/TLS. Trong một ứng dụng Boot đã dùng tự cấu hình, thông thường không cần tạo bean thủ công như trên.

## 7. Điều gì xảy ra khi gọi send()?

Với luồng đơn giản, service dựng **SimpleMailMessage**, sau đó gọi **MailSender.send(message)**. Với thư MIME, service dựng **MimeMessage** (thường qua **MimeMessageHelper**) rồi gọi **JavaMailSender.send(message)**.

Một triển khai như **JavaMailSenderImpl** sử dụng Jakarta Mail để kết nối và gửi dữ liệu tới SMTP server. Nếu SMTP server chấp nhận yêu cầu, lệnh gọi có thể kết thúc thành công; điều này **không đồng nghĩa người nhận đã đọc được thư**, vì thư vẫn có thể bị từ chối ở các chặng sau, rơi vào spam hoặc bị trả lại.

Spring Mail chuyển các lỗi gửi thành những ngoại lệ thuộc họ **MailException** (chẳng hạn **MailAuthenticationException** khi xác thực thất bại hoặc **MailSendException** khi gửi thất bại). Mã ứng dụng nên phân biệt lỗi tạm thời với lỗi cấu hình, đồng thời tránh log mật khẩu, token hoặc nội dung nhạy cảm.

**Việc gọi send() theo cách thông thường là đồng bộ:** luồng đang thực hiện phải đợi quá trình gửi hoặc lỗi từ hạ tầng. Với tác vụ có yêu cầu phản hồi nhanh hoặc cần bảo đảm xử lý lại, ứng dụng có thể đưa yêu cầu gửi thư vào hàng đợi và giao cho worker xử lý, có quy tắc retry và chống gửi trùng. Spring Mail tự nó không cung cấp bảo đảm gửi đúng một lần hay hàng đợi bền vững.

## 8. Chọn mức trừu tượng phù hợp

| Nhu cầu của bài toán | API được ưu tiên | Lý do |
|---|---|---|
| Email chỉ có văn bản thuần | **MailSender** + **SimpleMailMessage** | Hợp đồng gọn, dễ hiểu và dễ thay thế khi kiểm thử |
| Email HTML, nhiều phần, đính kèm | **JavaMailSender** + **MimeMessageHelper** | Hỗ trợ định dạng MIME |
| Muốn xây dựng MIME bằng callback | **JavaMailSender** + **MimeMessagePreparator** | Gom logic chuẩn bị thư trong một callback |
| Muốn đổi SMTP provider | Cấu hình **JavaMailSenderImpl**/bean gửi thư | Mã nghiệp vụ tiếp tục phụ thuộc vào interface |
| Muốn xử lý yêu cầu gửi không đồng bộ, retry | Service/queue bao ngoài **JavaMailSender** | Đây là chính sách ứng dụng, không phải tính năng tự động của interface |

Trong thiết kế lớn hơn, ứng dụng có thể định nghĩa interface nghiệp vụ riêng như **NotificationSender** hoặc **AccountEmailPort**, còn adapter email sử dụng **JavaMailSender** ở phía hạ tầng. Cách này hữu ích nếu hệ thống cần thay kênh thông báo hay thực hiện quy tắc nghiệp vụ rộng hơn gửi email. Tuy nhiên, nó là một lớp thiết kế tùy chọn của ứng dụng, không phải lớp bắt buộc của Spring Mail.

## 9. Những hiểu nhầm thường gặp

**“Spring Mail chính là SMTP server?”** Không. Spring Mail là API phía ứng dụng để tạo và gửi thông điệp; nó cần một hệ thống gửi mail thực tế (thường qua SMTP).

**“JavaMailSender là class?”** Không. JavaMailSender là một **interface** của Spring. JavaMailSenderImpl là class triển khai phổ biến.

**“MimeMessageHelper gửi email?”** Không. Helper hỗ trợ thiết lập thông điệp; thao tác gửi được gọi qua JavaMailSender.

**“Chỉ dùng JavaMailSender khi muốn gửi thư HTML?”** Không. JavaMailSender còn kế thừa MailSender, nên cũng có thể gửi SimpleMailMessage. Việc chọn interface phụ thuộc vào mức năng lực mà service cần.

**“Cứ gọi send() thành công là thư đã được giao tận tay người nhận?”** Không. Thành công ở phía client/SMTP không xác nhận thư đã đến inbox hay đã được đọc.

**“Spring Boot starter và Spring Mail là cùng một API?”** Không. Starter giúp đưa dependency và cấu hình phù hợp vào ứng dụng Boot; hợp đồng gửi thư nằm trong Spring Framework.

## 10. Kết luận

Ở mức nhập môn, hãy ghi nhớ chuỗi trách nhiệm: **Spring Framework Mail cung cấp MailSender và JavaMailSender làm abstraction; SimpleMailMessage/MimeMessageHelper giúp tạo nội dung; JavaMailSenderImpl dùng Jakarta Mail để thực hiện gửi qua SMTP**. Mã nghiệp vụ phụ thuộc vào interface để dễ cấu hình, kiểm thử và thay đổi hạ tầng. Với thư đơn giản, dùng **MailSender**; với MIME/HTML/đính kèm, dùng **JavaMailSender**.
