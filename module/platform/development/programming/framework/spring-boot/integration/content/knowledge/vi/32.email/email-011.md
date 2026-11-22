# Kiểm thử bằng máy chủ thư giả lập và tránh gửi tới người nhận thật

## 1. Vì sao kiểm thử email cần một máy chủ giả lập?

Trong một dịch vụ **Spring Boot Integration**, gửi email chỉ là một trong nhiều điểm tích hợp: một request HTTP tạo đơn hàng có thể ghi PostgreSQL, đẩy sự kiện qua Kafka rồi yêu cầu gửi email xác nhận; một job định kỳ có thể gửi báo cáo, cảnh báo lỗi đồng bộ hoặc liên kết đặt lại mật khẩu. Nếu môi trường phát triển và CI kết nối thẳng SMTP thật, một lần chạy test, replay sự kiện hoặc khởi động nhầm scheduler có thể gửi thư đến khách hàng dù thao tác chưa được kiểm chứng.

**Máy chủ thư giả lập** (SMTP sandbox/capture server) tiếp nhận lệnh gửi thư như một SMTP server ở cấp giao thức, lưu lại nội dung để kiểm tra và **không tự phát thư ra Internet** khi chưa được cấu hình relay. Hai lựa chọn phổ biến là:

- **Mailpit:** chạy như một dịch vụ riêng trong Docker hoặc máy cục bộ; cung cấp SMTP endpoint, giao diện web và HTTP API để xem email nhận được.
- **GreenMail:** máy chủ email giả lập chạy cùng JVM/test process hoặc dạng dịch vụ; phù hợp cho integration test cần chủ động khởi động, kiểm tra thư nhận được và dọn trạng thái giữa các test.

MailHog và các SMTP capture server khác cũng có thể dùng nếu đáp ứng yêu cầu. Khả năng dùng SMTP không đồng nghĩa chúng mô phỏng được toàn bộ quá trình deliver qua nhiều mail server, spam filter, mailbox của người nhận hay mọi chính sách xác thực của nhà cung cấp thật.

### Luồng kiểm thử mong muốn

~~~mermaid
flowchart LR
    Test["JUnit / HTTP test / consumer test"] --> Service["Spring Boot: EmailService"]
    Service --> Guard["Recipient guard + enable switch"]
    Guard --> Sender["JavaMailSender"]
    Sender --> Capture["Mailpit SMTP :1025"]
    Capture --> UI["Mailpit UI / API :8025"]
    Guard -. "Từ chối địa chỉ ngoài sandbox" .-> Blocked["To/Cc/Bcc không hợp lệ"]
    Capture -. "Không cấu hình outbound relay" .-> Internet["Internet / hộp thư thật"]
~~~

Mục tiêu kiểm thử là chứng minh **ứng dụng tạo đúng email, chuyển đúng SMTP giả lập, có thể xử lý lỗi và không gửi tới người thật**. Giao diện Mailpit giúp kiểm tra thủ công; HTTP API hoặc GreenMail giúp kiểm tra tự động. Để bảo vệ nhiều lớp, ngoài cấu hình SMTP local còn cần rào chắn tại mã nguồn và hạ tầng mạng.

## 2. Phân biệt unit test, integration test và kiểm thử giao nhận thực

| Cấp độ | Phương pháp | Có thể khẳng định | Không nên kết luận |
|---|---|---|---|
| Unit test | Mock/fake `JavaMailSender`, template renderer, policy | Payload đầu vào, nội dung, người nhận, guard và trường hợp lỗi giả lập | SMTP thật được kết nối hoặc MIME được server chấp nhận |
| Integration test với SMTP capture | Mailpit/GreenMail chạy thật, ứng dụng gửi qua SMTP | Kết nối SMTP, envelope, header, subject, HTML/text, file đính kèm, lỗi mô phỏng | Email đã tới hộp thư Internet hoặc vượt qua spam filter |
| End-to-end với mail provider sandbox | Tài khoản test riêng của dịch vụ cung cấp email | Cấu hình/provider API/SMTP gần production hơn | Khả năng deliver tới mọi hộp thư thật |
| Kiểm thử giao nhận production có kiểm soát | Hộp thư test do tổ chức sở hữu, môi trường được phê duyệt | Giao nhận thực tế trên các hệ thống đích đã chọn | Không có email thất lạc/trễ tại mọi nhà cung cấp |

`JavaMailSender.send(...)` trả về thành công thường cho biết ứng dụng đã trao thư tới SMTP server và được chấp nhận ở bước giao tiếp tương ứng. **Nó không chứng minh người nhận đã đọc, hay email đã vào Inbox.** Đây là ranh giới hợp đồng giữa ứng dụng và SMTP server.

## 3. Khởi động Mailpit cô lập cho môi trường local

Ví dụ `compose.yaml`:

~~~yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "127.0.0.1:1025:1025" # SMTP capture
      - "127.0.0.1:8025:8025" # Web UI và HTTP API
~~~

Chạy trong thư mục có file Compose:

~~~bash
docker compose up -d mailpit
~~~

Truy cập `http://127.0.0.1:8025` để xem inbox giả lập. SMTP endpoint từ ứng dụng chạy **trên máy host** là `127.0.0.1:1025`. Nếu Spring Boot chạy trong **container khác cùng Docker network**, host cần là tên service `mailpit` và port `1025` (không dùng `localhost` của chính container ứng dụng).

Ví dụ dùng `latest` cho thao tác thử nhanh; trong CI/production-like test cần **ghim tag/digest ảnh Docker đã kiểm chứng** để tránh thay đổi hành vi ngoài ý muốn giữa những lần chạy.

Mặc định Mailpit là công cụ **bắt và giữ thư để xem**, không cần SMTP account nhà cung cấp thật và không cấu hình SMTP relay. Không bật bất kỳ tùy chọn forward/relay nào trong môi trường kiểm thử nếu mục đích là ngăn thư thoát ra ngoài. Chỉ bind giao diện quản trị vào loopback trong ví dụ local; ở hệ thống CI hoặc máy dùng chung, cô lập mạng và kiểm soát quyền xem thư đã bắt vì nội dung có thể chứa dữ liệu nhạy cảm.

### Cấu hình Spring Boot profile `email-sandbox`

Thư viện Maven dùng với các phiên bản Spring Boot hỗ trợ starter Mail:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
~~~

`src/main/resources/application-email-sandbox.yml`:

~~~yaml
spring:
  mail:
    host: ${MAIL_CAPTURE_HOST:127.0.0.1}
    port: ${MAIL_CAPTURE_PORT:1025}
    test-connection: false
    properties:
      mail:
        smtp:
          auth: false
          starttls:
            enable: false
          connectiontimeout: 2000
          timeout: 3000
          writetimeout: 3000

app:
  email:
    enabled: true
    sandbox: true
    allowed-domain: example.test
~~~

Kích hoạt chỉ cho local/test, ví dụ với `SPRING_PROFILES_ACTIVE=email-sandbox`. Địa chỉ `example.test` là **domain dành cho kiểm thử** theo quy ước tên miền dự trữ, thuận tiện để tạo fixture như `customer-1@example.test`. Trong môi trường này, không cấu hình `spring.mail.username`, `spring.mail.password` của nhà cung cấp thật. Các thuộc tính SMTP timeout dùng để tránh request bị giữ vô hạn khi server mô phỏng không sẵn sàng.

Trên đường chạy của ứng dụng, profile chỉ xác định một tập cấu hình. Profile có thể bị bật nhầm hoặc bị ghi đè bởi biến môi trường; vì vậy **profile riêng chưa đủ làm hàng rào bảo vệ duy nhất**.

## 4. Thiết kế hàng rào chặn người nhận thật trong ứng dụng

Một email có thể chứa người nhận trong **To, Cc và Bcc**, và các tác vụ tích hợp khác nhau có thể gọi sender từ HTTP, message consumer hoặc scheduler. Nếu chỉ kiểm tra tham số `to` của một controller nhưng một đường xử lý khác thêm `bcc` trực tiếp, địa chỉ thật vẫn có thể bị gửi.

Thiết kế một gateway trung tâm: tất cả code nghiệp vụ phải tạo và gửi email qua gateway đó. Gateway **mặc định tắt outbound**, khi chế độ sandbox được bật thì kiểm tra **toàn bộ recipients** ngay trước `JavaMailSender.send`.

~~~java
package example.integration.email;

import jakarta.mail.Address;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.util.Locale;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public final class GuardedMailGateway {
    private final JavaMailSender sender;
    private final boolean enabled;
    private final boolean sandbox;
    private final String allowedDomain;

    public GuardedMailGateway(
            JavaMailSender sender,
            @Value("${app.email.enabled:false}") boolean enabled,
            @Value("${app.email.sandbox:true}") boolean sandbox,
            @Value("${app.email.allowed-domain:example.test}") String allowedDomain) {
        this.sender = sender;
        this.enabled = enabled;
        this.sandbox = sandbox;
        this.allowedDomain = allowedDomain.toLowerCase(Locale.ROOT);
    }

    public MimeMessage newMessage() {
        return sender.createMimeMessage();
    }

    public void send(MimeMessage message) throws MessagingException {
        if (!enabled) {
            throw new IllegalStateException("Email outbound is disabled");
        }
        if (sandbox) {
            Address[] recipients = message.getAllRecipients(); // To + Cc + Bcc
            if (recipients == null || recipients.length == 0) {
                throw new IllegalArgumentException("No recipients");
            }
            for (Address address : recipients) {
                if (!(address instanceof InternetAddress email)) {
                    throw new IllegalArgumentException("Unsupported address type");
                }
                email.validate();
                String raw = email.getAddress();
                int at = raw == null ? -1 : raw.lastIndexOf('@');
                if (at <= 0 ||
                    !raw.substring(at + 1).toLowerCase(Locale.ROOT)
                        .equals(allowedDomain)) {
                    throw new IllegalArgumentException(
                        "Recipient outside email sandbox");
                }
            }
        }
        sender.send(message);
    }
}
~~~

Chỉ chấp nhận domain **khớp chính xác** `example.test`; địa chỉ `user@example.test.evil.invalid` bị từ chối. Việc so sánh chuỗi kiểu `endsWith("test")` hoặc tìm `contains("example.test")` dễ bị lách và không đủ để bảo vệ. `InternetAddress.validate()` kiểm tra cú pháp cơ bản, không kiểm chứng chủ sở hữu domain hay khả năng giao nhận.

Trạng thái an toàn mặc định trong ví dụ là `enabled=false` và `sandbox=true`. Ở môi trường production, việc cho phép gửi ra ngoài phải được bật **chủ động** và đi kèm cấu hình SMTP thật, quyền hạ tầng, quy trình triển khai và kiểm soát người nhận. Không dùng một giá trị mặc định “bật gửi thật” cho mọi profile.

Code nghiệp vụ chỉ thao tác với gateway:

~~~java
package example.integration.email;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderEmailService {
    private final GuardedMailGateway gateway;

    public OrderEmailService(GuardedMailGateway gateway) {
        this.gateway = gateway;
    }

    public void sendConfirmation(String recipient, String orderCode)
            throws MessagingException {
        MimeMessage message = gateway.newMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");
        helper.setFrom("no-reply@example.test");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + orderCode);
        helper.setText("Đơn hàng " + orderCode + " đã được ghi nhận.", false);
        gateway.send(message);
    }
}
~~~

Địa chỉ `From` là fixture cho sandbox; ứng dụng thực phải lấy từ cấu hình đã được duyệt và xác thực danh tính người gửi theo nhà cung cấp mail. Để bảo đảm **mọi** luồng đều được bảo vệ, không để các service khác tự inject `JavaMailSender` rồi gửi trực tiếp bỏ qua gateway. Việc hạn chế quyền truy cập SMTP bằng network policy là tuyến bảo vệ độc lập nếu một đường code vẫn vô tình bypass gateway.

### Những trường hợp dễ bỏ sót

- **Bcc:** không xuất hiện trong header email thông thường nhưng vẫn là recipient ở lệnh SMTP; phải được kiểm tra trước khi gửi.
- **Reply-To:** không phải đích nhận ngay của lần gửi hiện tại, nhưng có thể lộ địa chỉ thật hoặc dẫn người dùng trả lời sai chỗ; dùng fixture trong test và rà soát riêng.
- **Nhiều recipient:** nếu danh sách có cả `tester@example.test` và `someone@real-domain.invalid`, toàn bộ lần gửi phải thất bại, không tự gửi cho một phần danh sách rồi báo thành công.
- **Template:** địa chỉ trích từ dữ liệu thử nghiệm/khách hàng được import có thể là email thật; cần thay thế hoặc ẩn danh dữ liệu trước khi dựng notification.
- **Tệp đính kèm:** hóa đơn, CSV, ảnh và báo cáo có thể chứa PII; nội dung bị bắt trong Mailpit cũng cần quyền truy cập, chính sách dọn dữ liệu và tránh dùng fixture nhạy cảm.
- **Các kênh gửi khác:** nếu hệ thống còn sử dụng API email của bên thứ ba, SMTP gateway không bao phủ API đó; cần kiểm soát tương tự tại cổng tích hợp tương ứng.

## 5. Kiểm tra email bằng giao diện Mailpit và HTTP API

Sau khi ứng dụng gửi một email vào SMTP sandbox:

1. Mở `http://127.0.0.1:8025`, xác nhận có message mới.
2. Kiểm tra **To/Cc/Bcc** theo góc nhìn SMTP/server, From, Reply-To, Subject và content type.
3. Xem **plain text** và **HTML** nếu message là multipart; chú ý Unicode tiếng Việt và ký tự đặc biệt.
4. Kiểm tra liên kết trong thư, dữ liệu template, file đính kèm, tên file, kiểu MIME và kích thước.
5. Xóa/dọn inbox giả lập trước ca test độc lập để không đọc nhầm message từ lần trước.

Mailpit cung cấp HTTP API; ví dụ để xem danh sách message đang được bắt:

~~~bash
curl --fail --silent http://127.0.0.1:8025/api/v1/messages
~~~

Trong test tự động, hãy truy vấn API bằng JSON parser, lọc message theo `eventId`/test correlation ID hoặc subject duy nhất, rồi kiểm tra dữ liệu. Không dựa vào việc “lấy email mới nhất” nếu nhiều test chạy đồng thời vì dễ đọc chéo ca test. Khi chạy container, URL HTTP API phải dùng host/port đã publish hoặc mapped port tương ứng.

**Lưu ý:** UI/API quan sát email sau khi SMTP capture server đã nhận; giao diện không có nhiệm vụ chứng minh email đã được gửi tới Gmail/Outlook. Dọn message trước hoặc sau test để giữ môi trường độc lập, tránh chứa thông tin nhạy cảm quá lâu.

## 6. Unit test cho policy: địa chỉ ngoài sandbox bị chặn

Một unit test tối thiểu phải bảo đảm việc từ chối xảy ra **trước khi gọi SMTP sender**. Ví dụ với JUnit 5 + Mockito:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class GuardedMailGatewayTest {

    @Test
    void rejectsExternalBccBeforeSending() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        GuardedMailGateway gateway =
            new GuardedMailGateway(sender, true, true, "example.test");

        MimeMessage message =
            new MimeMessage(Session.getInstance(new Properties()));
        message.setRecipients(
            Message.RecipientType.TO, "tester@example.test");
        message.setRecipients(
            Message.RecipientType.BCC, "real-person@other.invalid");

        assertThrows(
            IllegalArgumentException.class,
            () -> gateway.send(message));
        verify(sender, never()).send(any(MimeMessage.class));
    }

    @Test
    void outboundIsDisabledByDefault() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        GuardedMailGateway gateway =
            new GuardedMailGateway(sender, false, true, "example.test");
        MimeMessage message =
            new MimeMessage(Session.getInstance(new Properties()));
        message.setRecipients(
            Message.RecipientType.TO, "tester@example.test");

        assertThrows(
            IllegalStateException.class,
            () -> gateway.send(message));
        verify(sender, never()).send(any(MimeMessage.class));
    }
}
~~~

Hai test này không phụ thuộc Mailpit: chúng chứng minh logic guard chặn địa chỉ ngoài sandbox và chặn khi outbound bị tắt. Nên bổ sung ca `To` sai, `Cc` sai, recipient trống, danh sách trộn hợp lệ/không hợp lệ, chữ hoa ở domain, địa chỉ có display name và domain gần giống `example.test`.

Đây là kiểm thử policy ở mức đơn vị. Để chứng minh message **thực sự truyền qua SMTP**, cần integration test độc lập sử dụng Mailpit/GreenMail. Không thay thế các phép kiểm tra đó chỉ bằng xác nhận `send()` được gọi trên mock.

## 7. Integration test với máy chủ SMTP thật trong phạm vi sandbox

### 7.1. Kịch bản sử dụng Mailpit trong CI

Một bài test HTTP → email có thể thực hiện như sau:

1. Khởi động Mailpit độc lập, không cấu hình relay và chỉ cho ứng dụng test truy cập SMTP endpoint của container.
2. Khởi động Spring Boot với profile sandbox, trỏ `spring.mail.host/port` tới Mailpit; cấp `app.email.enabled=true`, `sandbox=true`, domain `example.test`.
3. Gửi request hoặc kích hoạt message consumer với fixture chứa recipient `alice@example.test`.
4. Đợi có message phù hợp trong inbox qua API của Mailpit với timeout hữu hạn, không dùng `Thread.sleep` cố định làm đồng bộ.
5. Kiểm tra đúng một nội dung dự kiến, subject, sender, recipient, HTML/text, MIME, attachment; đối chiếu correlation ID hoặc mã đơn hàng.
6. Lặp lại cùng request/event và kiểm tra chính sách chống trùng: ứng dụng không tạo notification nghiệp vụ thứ hai nếu yêu cầu là idempotent.
7. Thử recipient ngoài sandbox và xác nhận **không có message mới** trong Mailpit, đồng thời ứng dụng trả về lỗi/ghi nhận trạng thái bị chặn đúng thiết kế.

Với Testcontainers có thể chạy Mailpit trong `GenericContainer` và lấy SMTP/API port động từ container, sau đó đưa vào `@DynamicPropertySource`. Không hardcode `127.0.0.1:1025` trong test nếu CI ánh xạ cổng động. Cần pin image version trong pipeline và dọn dữ liệu nhận giữa các test để tránh tương tác bất ngờ.

### 7.2. GreenMail cho integration test JVM

GreenMail có thể chạy **in-process**, hữu ích khi muốn chủ động khởi tạo server mỗi lớp test, lấy danh sách thư, assert số lượng và làm sạch sau test. Ví dụ khái quát:

~~~java
// Ví dụ chủ đích: quản lý lifecycle ở test fixture.
GreenMail greenMail = new GreenMail(
    new ServerSetup(3025, "127.0.0.1", ServerSetup.PROTOCOL_SMTP));
greenMail.start();
try {
    // Cấu hình JavaMailSender của ứng dụng:
    // host = 127.0.0.1; port = 3025; không dùng account thật.
    // Gọi service gửi email và assert:
    // greenMail.waitForIncomingEmail(...);
    // greenMail.getReceivedMessages();
} finally {
    greenMail.stop();
}
~~~

Các class trong ví dụ là `com.icegreen.greenmail.util.GreenMail`, `ServerSetup`; thư viện và API test cần khớp phiên bản GreenMail đang sử dụng. Cổng cố định chỉ phù hợp khi chắc chắn không có test chạy song song chiếm cùng cổng. Trong hệ thống CI nhiều worker, nên cấu hình **port tự do/port động** theo khả năng framework hoặc cấp instance riêng cho từng test suite.

Mailpit phù hợp khi cần **giao diện để QA nhìn thư** và API cho test hộp đen. GreenMail phù hợp khi cần **điều khiển server trong test JVM** và xác minh nhiều tình huống SMTP/IMAP tương ứng. Có thể kết hợp: unit test với Mockito, integration test với GreenMail, thử luồng toàn hệ thống với Mailpit.

### 7.3. Các ca tích hợp nên có

| Nhóm kiểm thử | Kịch bản | Kết quả kỳ vọng |
|---|---|---|
| Happy path | Gửi email thông báo tới `alice@example.test` | SMTP capture có đúng email với subject/body đã định |
| To/Cc/Bcc | Gửi tới nhiều địa chỉ test | Tất cả recipient đúng, Bcc được truyền ở envelope nhưng không bị rò vào header |
| Chặn người thật | Có địa chỉ ngoài `example.test` ở To/Cc/Bcc | Gateway từ chối trước send, inbox không tăng |
| Tắt gửi | `app.email.enabled=false` | Không kết nối SMTP và không gửi message |
| HTML + text | Gửi multipart alternative | Có phần text/plain và text/html đúng encoding |
| Unicode | Tiêu đề/nội dung có dấu tiếng Việt | Decode đúng UTF-8, không lỗi font/ký tự |
| Attachment | Gửi hóa đơn PDF giả định | Kiểm tra file name, MIME type, nội dung/size fixture |
| SMTP unavailable | Tắt Mailpit hoặc đổi port sai | Ứng dụng báo lỗi có kiểm soát, timeout hữu hạn; job có thể retry |
| SMTP response lỗi | Mô phỏng 4xx/5xx khi hỗ trợ | Phân loại lỗi tạm thời/vĩnh viễn theo policy, không báo đã gửi |
| Duplicate event | Consumer nhận lại cùng `eventId` | Không sinh hai notification nghiệp vụ theo contract |
| Crash giữa gửi và ghi trạng thái | SMTP đã nhận nhưng worker chưa commit trạng thái | Retry có thể tạo email lặp; theo dõi/giảm trùng bằng khóa nghiệp vụ |
| Độc lập test | Chạy hai test song song/tuần tự | Không đọc lẫn message và không tái dùng inbox bẩn |

## 8. Tránh gửi nhầm người nhận thật: phòng vệ nhiều lớp

Ứng dụng không nên dựa vào một cờ `spring.profiles.active` hoặc một `if` đơn lẻ. Có thể kết hợp các rào chắn sau:

1. **SMTP endpoint cô lập:** local/CI luôn trỏ vào Mailpit/GreenMail, không dùng SMTP hostname hoặc token của nhà cung cấp thật.
2. **Email dispatch mặc định tắt:** chỉ bật khi đã chỉ định đích SMTP và chế độ bảo vệ; ở môi trường không gửi email, không khởi chạy worker gửi thư.
3. **Allowlist toàn bộ To/Cc/Bcc:** chỉ nhận domain test hoặc tập địa chỉ test đã cấp; từ chối toàn bộ lần gửi khi có bất kỳ địa chỉ không thuộc allowlist.
4. **Dữ liệu thử nghiệm sạch:** email trong fixture dùng `example.test`; ẩn danh data import từ production và các URL/action token nhạy cảm.
5. **Giới hạn mạng:** cấm egress SMTP/HTTPS email provider từ job test bằng firewall/network policy, chỉ cho phép SMTP capture được khai báo.
6. **Bảo vệ công cụ capture:** không bật relay, hạn chế truy cập UI/API, xóa inbox/attachments khi test kết thúc, không lưu secret.
7. **Kiểm chứng negative path:** test chủ động thử địa chỉ thật giả lập `person@other.invalid` và xác nhận không có request tới SMTP thật; chạy test này trong pipeline.

Không nên **thay mọi recipient thành một email chung rồi âm thầm gửi** nếu yêu cầu kiểm thử là phát hiện mapping người nhận sai. Có thể cung cấp chế độ rewrite recipient cho QA, nhưng phải lưu recipient gốc dưới dạng dữ liệu đã bảo vệ, đánh dấu sandbox rõ ràng và tránh đưa PII/địa chỉ thật vào header hoặc body. Với test tự động, **từ chối ngoài allowlist** giúp phát hiện lỗi cấu hình sớm hơn.

### Nếu ứng dụng có nhiều kênh gửi

Một dịch vụ tích hợp có thể có:

- `JavaMailSender` qua SMTP;
- email provider REST API;
- message broker đưa event tới email worker khác;
- scheduled retry chạy các bản ghi email outbox;
- cơ chế xử lý sự kiện từ hệ thống bên ngoài.

Khi đó guard cần được thực thi tại **điểm gửi cuối cùng** của từng kênh. Chặn ở controller không đủ nếu consumer hoặc retry worker vẫn nhận được yêu cầu gửi. Đối với broker, một event chứa email người nhận thật trong dữ liệu thử nghiệm có thể được xử lý bởi consumer production nếu topic/cluster bị cấu hình nhầm; phải tách environment, topic, credentials và quyền truy cập.

## 9. Quản lý giao dịch, retry và email trùng lặp

Email là một **tác dụng phụ ngoài database transaction**. Nếu một request vừa ghi PostgreSQL vừa gửi SMTP, hai thao tác không nằm trong cùng một giao dịch ACID:

~~~mermaid
sequenceDiagram
    participant A as HTTP / Worker
    participant D as PostgreSQL
    participant S as SMTP Sandbox
    A->>D: Ghi trạng thái email PENDING (COMMIT)
    A->>S: SMTP send
    S-->>A: Accepted
    Note over A,D: Worker có thể crash tại đây
    A->>D: Ghi trạng thái SENT (COMMIT)
~~~

Nếu worker chết **sau khi SMTP nhận thư nhưng trước khi ghi `SENT`**, retry có thể gửi lại. SMTP không có một giao dịch chung với PostgreSQL để rollback email đã được chấp nhận. Kể cả khi thêm `@Transactional` quanh hàm Java, rollback database cũng không thu hồi một email đã giao cho SMTP.

Để giảm mất thư, có thể dùng **email outbox**:

1. Trong cùng DB transaction với nghiệp vụ, ghi một dòng `email_outbox` chứa `notification_key`, template/version, dữ liệu tham chiếu và trạng thái `PENDING`.
2. Worker claim theo lô bằng khóa/lease, dựng email, gọi gateway (trong test thì trỏ SMTP sandbox).
3. Sau khi được SMTP xác nhận, ghi `SENT`; lỗi tạm thời chuyển về retry với exponential backoff và giới hạn số lần thử.
4. Dùng unique key theo ý định nghiệp vụ (ví dụ `orderId + notificationType + version`) để tránh sinh hai yêu cầu gửi cho cùng một sự kiện khi HTTP/Kafka retry.
5. Ghi nhận `eventId`, `notificationKey`, `attempt`, SMTP outcome và correlation ID để đối soát.

**Giới hạn quan trọng:** unique key và outbox ngăn trùng **lệnh gửi được tạo trong database**, nhưng không bảo đảm một lần **giao nhận SMTP** duy nhất nếu worker crash trong cửa sổ sau accepted. Một số provider API hỗ trợ idempotency key; nếu dùng SMTP thuần, cần chấp nhận khả năng thư lặp, thiết kế nội dung chịu được retry và có quy trình đối soát/cảnh báo. `Message-ID` ổn định có thể hỗ trợ chẩn đoán hoặc xử lý tùy hệ thống, nhưng không phải cam kết mọi mail server sẽ dedup.

Trong test, giả lập timeout **sau khi server đã nhận email** cũng quan trọng như giả lập kết nối thất bại trước khi gửi. Nếu mock luôn ném exception trước send, test sẽ bỏ sót trường hợp retry gây thư trùng trong thực tế.

## 10. Kiểm thử tình huống SMTP lỗi và quan sát hệ thống

Mailpit chủ yếu phục vụ nhận và kiểm tra message. Để mô phỏng chính xác lỗi SMTP 4xx/5xx, timeout sau lệnh `DATA`, ngắt kết nối hoặc server từ chối người nhận, có thể cần một **SMTP stub/proxy có lập trình** hoặc công cụ hỗ trợ cấu hình phản hồi lỗi. Đừng gán cho Mailpit khả năng giả lập mọi lỗi SMTP nếu chưa kiểm chứng phiên bản/cấu hình dùng trong dự án.

Các nhánh lỗi cần phân biệt:

- **Không kết nối được SMTP:** `connection refused`, DNS, timeout; thường phù hợp retry có giới hạn.
- **SMTP 4xx tạm thời:** có thể retry theo backoff; tránh retry tức thì với số lượng lớn.
- **SMTP 5xx vĩnh viễn:** ví dụ người nhận không hợp lệ; thường không retry vô hạn, chuyển trạng thái cần xử lý.
- **Đã accepted nhưng client timeout/mất kết nối:** kết quả không chắc chắn; retry có thể phát lặp.
- **Nội dung email sai:** lỗi template/MIME/encoding cần phát hiện trong test trước khi gửi, không nên retry vô hạn một payload luôn sai.

Nên theo dõi metric và log với dữ liệu tối thiểu:

| Tín hiệu | Mục đích |
|---|---|
| `mail_send_attempts_total{outcome=...}` | Đếm thành công, lỗi tạm thời, lỗi vĩnh viễn, bị guard chặn |
| `mail_send_duration_seconds` | Phát hiện SMTP chậm hoặc timeout |
| `mail_outbox_pending`, `mail_outbox_oldest_age` | Phát hiện backlog và notification bị kẹt |
| `mail_retry_attempts` | Quan sát tăng retry, tránh vòng lặp |
| `mail_recipient_rejected_total` | Cảnh báo cấu hình sai môi trường/sai domain |
| `notificationKey`, `eventId`, `traceId` | Liên kết HTTP request, DB row, broker event và email |

Không đưa email người dùng, access token, nội dung thư, mật khẩu SMTP hoặc file đính kèm vào metric label/log. Metric label cardinality cao (ví dụ per recipient, per eventId) cũng gây chi phí và làm khó giám sát.

Để kiểm thử luồng HTTP/DB/Kafka → email một cách ổn định, cần biết **trạng thái được coi là hoàn thành**: request đã tạo outbox, worker đã gửi tới SMTP, hay downstream đã nhận? Mỗi mốc có thể được assert độc lập và có latency khác nhau.

## 11. Quy trình CI đề xuất

Một pipeline kiểm thử thông báo email cho dịch vụ tích hợp có thể gồm:

1. Tạo PostgreSQL/broker và Mailpit hoặc GreenMail **dành riêng cho test job**; vô hiệu outbound SMTP/HTTP email provider ở cấp mạng.
2. Khởi chạy ứng dụng với fixture domain `example.test`, không cấp secret của hệ thống email production.
3. Chạy unit test cho template, recipient guard, trạng thái disabled và việc phân loại lỗi.
4. Chạy integration test với SMTP giả lập, xác minh content, header, MIME, attachment, UTF-8, số lượng thư và key tương quan.
5. Chạy thử API/job/consumer lặp lại cùng dữ liệu và lỗi mạng; xác minh outbox/retry/duplicate theo hợp đồng.
6. Kiểm tra không có email gửi tới domain ngoài allowlist; dọn inbox, container và dữ liệu chứa nội dung email sau test.
7. Xuất báo cáo lỗi theo `notificationKey`, loại exception và bước xử lý; tuyệt đối không xuất credential hoặc dữ liệu cá nhân.

Khi chạy song song, nên tạo **một SMTP capture server per test worker** hoặc có quy tắc phân vùng dữ liệu rõ ràng; tránh dùng chung một inbox giữa nhiều pipeline và assert “chỉ có đúng một email toàn server” trong khi các test khác đang chạy.

## 12. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Profile test nghĩa là không thể gửi email thật.” | Profile có thể bị override; cần endpoint sandbox, allowlist và chặn egress. |
| “Mock `JavaMailSender` đủ chứng minh SMTP hoạt động.” | Mock chỉ kiểm tra lệnh gọi; cần SMTP capture cho kiểm thử tích hợp. |
| “Server đã nhận mail tức là khách hàng nhận được.” | SMTP accepted và inbox delivery là hai mốc khác nhau. |
| “Chặn trường To là đủ.” | Cần kiểm tra To, Cc, Bcc và các đường gửi khác nhau. |
| “Mailpit là nơi lưu dữ liệu vô hại.” | Thư và attachment có thể chứa dữ liệu nhạy cảm; cần hạn chế truy cập và xóa. |
| “Đánh dấu `SENT` sau `send()` đảm bảo không có email trùng.” | Crash giữa send/commit có thể tạo retry và duplicate. |
| “Thêm `@Transactional` làm SMTP rollback cùng database.” | SMTP là hệ thống ngoài DB transaction. |
| “Môi trường staging có thể dùng SMTP production nếu đặt subject [TEST].” | Subject không ngăn deliver; cần tách account/endpoint/recipient và hạ tầng. |

## 13. Câu hỏi tự kiểm tra

1. Tại sao một bài test dùng mock `JavaMailSender` vẫn có thể chạy xanh khi cấu hình SMTP trong ứng dụng sai hoàn toàn?
2. Trường `Bcc` khác `To` và `Cc` ở góc nhìn giao nhận SMTP; vì sao recipient guard phải kiểm tra cả ba?
3. Nếu CI trỏ nhầm vào SMTP production nhưng `app.email.sandbox=true`, các lớp bảo vệ nào vẫn giúp không gửi tới người thật?
4. Nếu một consumer Kafka nhận lại cùng `eventId`, cách nào tránh tạo hai dòng email outbox?
5. Nếu SMTP đã chấp nhận email nhưng worker chết trước khi cập nhật trạng thái, retry có thể tạo kết quả gì?
6. Cần assert những gì trong một email HTML có tệp đính kèm và nội dung tiếng Việt?
7. Vì sao một SMTP capture server mặc định không thể xác nhận inbox delivery/spam placement của người nhận bên ngoài?

**Kết luận kỹ thuật:** Kiểm thử email trong Spring Boot Integration cần kết hợp **SMTP capture server** để kiểm tra đường gửi thực, **recipient guard** và chặn egress để bảo vệ người nhận, cùng các test về nội dung, lỗi và retry ở ranh giới database/broker/SMTP. Mailpit/GreenMail giúp xác minh thông điệp mà không tạo email thật; muốn chịu được crash và phát lặp vẫn phải có outbox, idempotency và trạng thái giao nhận rõ ràng.

### Tài liệu tham khảo

- [Spring Boot — Sending Email](https://docs.spring.io/spring-boot/reference/io/email.html): tự động cấu hình `JavaMailSender`, `spring.mail.*` và SMTP timeout.
- [Spring Framework — Email Integration](https://docs.spring.io/spring-framework/reference/integration/email.html): `JavaMailSender`, `MimeMessageHelper` và cách tạo email MIME.
- [Mailpit Documentation](https://mailpit.axllent.org/): SMTP capture, giao diện web và API.
- [GreenMail](https://greenmail-mail-test.github.io/greenmail/): máy chủ mail in-memory cho kiểm thử Java.
- [RFC 2606 — Reserved Top Level DNS Names](https://www.rfc-editor.org/rfc/rfc2606): các tên miền dành cho ví dụ và kiểm thử.
