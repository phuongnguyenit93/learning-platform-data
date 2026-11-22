# Không phụ thuộc mail server thật trong unit test

Một ứng dụng **Spring Framework Mail** có thể dùng `JavaMailSender` để gửi email xác minh tài khoản, hóa đơn, cảnh báo hoặc thông báo đơn hàng. Khi viết unit test cho những chức năng này, không nên yêu cầu có một SMTP server đang hoạt động, không nên dùng tài khoản email thật và càng không nên để test vô tình gửi thư tới người dùng thật.

Một test chỉ cần xác minh “service đã chuẩn bị đúng email và yêu cầu gửi” không cần kết nối mạng. Ta có thể dùng **Mockito** để thay `JavaMailSender` bằng mock, trả về một **`MimeMessage` thật nhưng nằm trong bộ nhớ**, sau đó kiểm tra địa chỉ nhận, tiêu đề, nội dung plain text/HTML, attachment và cách xử lý lỗi. Khi dùng `SimpleMailMessage`, còn có thể xác minh trực tiếp đối tượng đã chuyển cho `MailSender`.

Bài học tập trung vào nguyên tắc **không phụ thuộc mail server thật trong unit test**, cách thiết kế ranh giới kiểm thử, ví dụ JUnit 5/Mockito/AssertJ, kiểm thử MIME bằng Jakarta Mail, phân biệt test unit với test integration và các biện pháp bảo vệ môi trường CI khỏi tác dụng phụ ngoài ý muốn.

## 1. Vì sao unit test không nên gửi SMTP thật?

Giả sử một test gọi nguyên service đang sử dụng `JavaMailSenderImpl` đã cấu hình từ môi trường:

```text
JUnit test
   |
   v
OrderService
   |
   v
NotificationService
   |
   v
JavaMailSenderImpl
   |
   | TCP / TLS / SMTP AUTH / DATA
   v
SMTP provider ngoài hệ thống
   |
   v
Hộp thư người nhận
```

Khi đó kết quả test có thể phụ thuộc vào:
- mạng có kết nối được tới SMTP host hay không;
- DNS, firewall, proxy và TLS certificate;
- mật khẩu hoặc token SMTP còn hợp lệ hay không;
- quota/rate limit hoặc tình trạng provider;
- tốc độ phản hồi của relay;
- tên miền/địa chỉ người nhận trong dữ liệu thử nghiệm;
- chính sách chống spam và suppression list.

Một thay đổi nhỏ trong nội dung email có thể bị che khuất bởi sự cố mạng. Ngược lại, test có thể pass dù email sai nội dung vì SMTP chấp nhận message mà không kiểm tra thông tin nghiệp vụ.

**Unit test cần nhanh, cô lập, lặp lại được và không tạo side effect bên ngoài.** Nó kiểm tra logic do nhóm phát triển kiểm soát, không dùng availability của một hệ thống SMTP bên thứ ba làm điều kiện thành công.

## 2. Đặt ranh giới kiểm thử ở đâu?

Với Spring Mail, một kiến trúc dễ kiểm thử:

```text
Business use case
      |
      v
Notification / mail application service
      |
      +--> Validate recipient and business data
      |
      +--> Render subject/plain/HTML
      |
      +--> Build MimeMessage
      |
      v
JavaMailSender interface     <-- thay bằng Mockito mock
      |
      v
JavaMailSenderImpl           <-- chỉ dùng trong integration
      |
      v
SMTP server
```

Cần phân biệt:
- **Renderer unit test:** kiểm tra chuỗi text và HTML dựa trên dữ liệu nghiệp vụ.
- **Service unit test:** kiểm tra thông điệp nào được gửi, ai nhận, khi nào gửi và phản ứng trước lỗi.
- **MIME construction test:** dùng Jakarta Mail thật trong bộ nhớ để kiểm tra MIME parts, charset, header và attachment.
- **SMTP integration test:** kiểm tra kết nối tới một SMTP sandbox/test server, STARTTLS, AUTH và hành vi giao thức.
- **End-to-end test:** kiểm tra provider nhận message và mailbox thử nghiệm nhận thư.

Ba lớp đầu không cần SMTP server thật.

| Câu hỏi | Unit test | SMTP integration/E2E |
|---|---|---|
| `send` được gọi đúng một lần? | Có, bằng Mockito | Không bắt buộc |
| Đúng `To`, `Subject`, `From`? | Có, capture/inspect message | Có thể kiểm tra bổ sung |
| Plain text và HTML có dữ kiện đúng? | Có | Có thể kiểm tra bổ sung |
| Attachment đúng tên/nội dung? | Có, dùng MIME in-memory | Có thể kiểm tra bổ sung |
| Có tạo side effect khi dữ liệu không hợp lệ? | Có, verify không gọi sender | Không cần |
| SMTP credentials và TLS hoạt động? | Không | Có |
| Relay/provider chấp nhận DATA? | Không | Có |
| SPF/DKIM/DMARC pass? | Không | Cần tuyến gửi/receiver thật |
| Thư vào Inbox hay bị spam? | Không | E2E/quan sát thực tế |

**Không phát biểu rằng “email đã được giao” chỉ vì unit test xác minh `send(...)` được gọi.**

## 3. JavaMailSender là điểm thay thế phù hợp

Spring cung cấp những abstraction quan trọng:

- `MailSender`: gửi `SimpleMailMessage`, phù hợp email văn bản đơn giản.
- `JavaMailSender`: mở rộng `MailSender`, có thể tạo và gửi `MimeMessage`, cũng như gửi qua `MimeMessagePreparator`.
- `JavaMailSenderImpl`: triển khai sử dụng Jakarta Mail SMTP transport và có thể kết nối tới server thật.

Một service nên phụ thuộc vào **interface**:

```java
@Service
public class NotificationService {
    private final JavaMailSender mailSender;

    public NotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
```

Không nên tự khởi tạo một sender thật bên trong phương thức:

```java
// Không thuận lợi cho unit test:
public void sendMail() {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("smtp.example.com");
    // ...
    sender.send(message);
}
```

Cách thứ hai tạo một dependency ẩn: test không dễ thay thế nó bằng mock. Constructor injection làm dependencies rõ ràng, dễ kiểm soát và không cần cấu hình hệ thống SMTP trong unit test.

## 4. Công cụ kiểm thử và dependency

Với ứng dụng Spring Boot dùng Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` thường cung cấp JUnit Jupiter, Mockito, AssertJ và các tiện ích kiểm thử Spring thông qua dependency management của phiên bản dự án.

Các ví dụ trong bài dùng:
- Spring Framework 6+/Spring Boot 3+, vì thế dùng `jakarta.mail.*` thay cho các package `javax.mail.*` cũ;
- Java 17+ để dùng record và text blocks;
- JUnit 5 để chạy assertions;
- Mockito để thay thế sender;
- AssertJ để kiểm tra dữ liệu dễ đọc.

**Không cần một SMTP service trong Docker, username/password hoặc Internet connection** cho các ví dụ unit test.

### 4.1. Không nhất thiết khởi động Spring ApplicationContext

Với service có constructor injection đơn giản, unit test có thể tạo đối tượng bằng `new`:

```java
JavaMailSender sender = mock(JavaMailSender.class);
NotificationService service = new NotificationService(sender);
```

Đây là test nhỏ, không cần `@SpringBootTest`. Chỉ dùng Spring test context nếu hành vi cần test liên quan trực tiếp đến dependency wiring/configuration hoặc framework integration.

### 4.2. @Mock, @InjectMocks và @MockitoBean khác nhau

| Công cụ | Phạm vi | Khi nên dùng |
|---|---|---|
| `Mockito.mock(...)` | Plain JUnit test | Muốn chủ động tạo mock. |
| `@Mock` + `MockitoExtension` | Plain JUnit test | Muốn Mockito khởi tạo mock qua annotation. |
| `@InjectMocks` | Plain JUnit test | Constructor/field injection của đối tượng test khi phù hợp. |
| `@MockitoBean` | Spring test ApplicationContext trong các phiên bản Spring hỗ trợ | Thay bean trong Spring context để test wiring/use case. |
| `@MockBean` | Một số phiên bản Spring Boot cũ hơn | Cách thay bean ở các dự án dùng API đó; lưu ý khả năng deprecated theo phiên bản. |

Không lấy `@SpringBootTest` + mock sender làm cách mặc định cho mọi unit test vì khởi động context thường chậm hơn và đưa nhiều yếu tố không cần thiết vào bài kiểm tra.

## 5. Trường hợp đơn giản nhất: SimpleMailMessage

Nếu email chỉ có subject và plain text, `SimpleMailMessage` thường đủ dùng.

### 5.1. Service được kiểm thử

```java
package com.example.mail;

import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

public class WelcomeMailService {

    private final MailSender sender;

    public WelcomeMailService(MailSender sender) {
        this.sender = sender;
    }

    public void sendWelcome(String to, String displayName) {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setFrom("no-reply@example.com");
        message.setTo(to);
        message.setSubject("Chào mừng " + displayName);
        message.setText(
            "Xin chào " + displayName + ",\n"
                + "Tài khoản của bạn đã được tạo thành công."
        );

        sender.send(message);
    }
}
```

`SimpleMailMessage` không hỗ trợ phần HTML, inline image và MIME attachment theo cách `MimeMessage` làm. Không dùng nó khi email cần nhiều MIME representations.

### 5.2. Unit test hoàn toàn không có SMTP

```java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

class WelcomeMailServiceTest {

    @Test
    void sendsExpectedPlainText() {
        MailSender sender = mock(MailSender.class);
        WelcomeMailService service =
            new WelcomeMailService(sender);

        service.sendWelcome(
            "customer@example.net",
            "Nguyễn Thị Ánh"
        );

        ArgumentCaptor<SimpleMailMessage> captor =
            ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender).send(captor.capture());

        SimpleMailMessage actual = captor.getValue();

        assertThat(actual.getFrom())
            .isEqualTo("no-reply@example.com");

        assertThat(actual.getTo())
            .containsExactly("customer@example.net");

        assertThat(actual.getSubject())
            .isEqualTo("Chào mừng Nguyễn Thị Ánh");

        assertThat(actual.getText())
            .contains("Xin chào Nguyễn Thị Ánh")
            .contains("Tài khoản của bạn đã được tạo");
    }
}
```

Ở đây Mockito chỉ **ghi nhận lời gọi**. Không có socket, SMTP AUTH, gửi thư thật hoặc môi trường mail server.

### 5.3. Tại sao không chỉ verify send được gọi?

Test quá yếu:

```java
verify(sender).send(any(SimpleMailMessage.class));
```

Nó pass ngay cả khi subject rỗng, địa chỉ To bị đảo nhầm hoặc nội dung gửi sai. Khi hành vi nghiệp vụ là “gửi thư chào mừng đúng người, đúng thông tin”, nên capture và assert các field quan trọng.

## 6. MimeMessage khác SimpleMailMessage như thế nào?

Email có HTML, cả plain + HTML, ảnh inline hoặc file đính kèm thường dùng `MimeMessage` cùng `MimeMessageHelper`.

Ví dụ service:

```java
MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo(recipient);
helper.setSubject("Xác nhận đơn hàng ORD-001");
helper.setText(plainText, htmlText);

sender.send(message);
```

Khó khăn trong unit test: `JavaMailSender.createMimeMessage()` nếu gọi trên Mockito mock mà chưa stub sẽ trả `null`. `MimeMessageHelper` khi nhận null sẽ lỗi trước khi tới bước gửi.

Giải pháp là **mock sender nhưng dùng MimeMessage thật trong bộ nhớ**.

## 7. Tạo MimeMessage in-memory, không cần server

Jakarta Mail cung cấp `Session` dùng để tạo và quản lý thông điệp MIME. Chỉ tạo `Session` và `MimeMessage` **không kết nối SMTP**:

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.util.Properties;

Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
```

Không cần SMTP host, port hoặc credentials trong `Properties`.

`Session` ở đây là cấu hình và trạng thái Jakarta Mail liên quan đến message; **nó không phải phiên TCP SMTP đang hoạt động**. Kết nối mạng chỉ phát sinh khi gọi các thao tác transport thực tế, chẳng hạn gửi qua `JavaMailSenderImpl`.

### 7.1. Stub createMimeMessage của mock sender

```java
JavaMailSender sender = mock(JavaMailSender.class);

MimeMessage inMemory = new MimeMessage(
    Session.getInstance(new Properties())
);

when(sender.createMimeMessage())
    .thenReturn(inMemory);
```

Khi service gọi `sender.createMimeMessage()`, nó nhận một thông điệp thật để xây dựng và có thể inspect sau đó. Khi gọi `sender.send(message)`, Mockito **không gửi đi đâu**.

### 7.2. Vì sao không mock luôn MimeMessage?

Có thể mock `MimeMessage`, nhưng khi đó các method như `setRecipients`, `getContent`, `setText`, `saveChanges` và MIME multipart không có hành vi thực trừ khi test tự stub từng bước.

Nếu mục tiêu là kiểm tra **thông điệp đã được xây đúng**, sử dụng `MimeMessage` in-memory thật thường đáng tin và đơn giản hơn. Ta mock **ranh giới I/O** chứ không phải mọi đối tượng dữ liệu.

## 8. Ví dụ service Spring Mail có thể kiểm thử

### 8.1. Model và nội dung email

```java
package com.example.mail;

public record OrderMailData(
    String customerName,
    String orderId,
    String orderUrl,
    String amountText
) {}

public record RenderedMail(
    String plain,
    String html
) {}
```

Tạo renderer đơn giản:

```java
package com.example.mail;

public class OrderMailRenderer {

    public RenderedMail render(OrderMailData data) {
        String plain = """
            Xin chào %s,

            Đơn hàng %s đã được xác nhận.
            Tổng tiền: %s

            Xem đơn hàng:
            %s
            """.formatted(
                data.customerName(),
                data.orderId(),
                data.amountText(),
                data.orderUrl()
            );

        // Minh họa một renderer HTML tĩnh; khi nhận dữ liệu
        // không tin cậy, dùng template engine escaping
        // đúng ngữ cảnh text và URL attribute.
        String html = """
            <html><body>
              <h1>Xác nhận đơn hàng</h1>
              <p>Đơn hàng đã được xác nhận.</p>
              <p>Xem nội dung chi tiết ở bản text tương ứng.</p>
            </body></html>
            """;

        return new RenderedMail(plain, html);
    }
}
```

Ví dụ trên cho thấy việc tách renderer khỏi sender. Trong một sản phẩm thực tế, **cả plain và HTML phải chứa thông tin nghiệp vụ quan trọng**, sử dụng chung view model để tránh mâu thuẫn. Renderer HTML thực tế nên đưa mã đơn hàng, số tiền và link vào template với escaping phù hợp.

### 8.2. Service chỉ biết abstraction JavaMailSender

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class OrderMailService {

    private final JavaMailSender sender;
    private final OrderMailRenderer renderer;

    public OrderMailService(
            JavaMailSender sender,
            OrderMailRenderer renderer) {
        this.sender = sender;
        this.renderer = renderer;
    }

    public void send(String recipient, OrderMailData data)
            throws MessagingException {

        RenderedMail content = renderer.render(data);

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("orders@example.com");
        helper.setTo(recipient);
        helper.setSubject(
            "Xác nhận đơn hàng " + data.orderId()
        );
        helper.setText(content.plain(), content.html());

        sender.send(message);
    }
}
```

Không có `JavaMailSenderImpl` bên trong service. Việc thay sender bằng mock không đòi hỏi sửa production code.

## 9. Unit test Mockito capture MimeMessage

```java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

import java.util.Properties;

class OrderMailServiceTest {

    @Test
    void preparesAndRequestsExpectedMessage()
            throws Exception {

        JavaMailSender sender = mock(JavaMailSender.class);
        MimeMessage message = new MimeMessage(
            Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage()).thenReturn(message);

        OrderMailService service = new OrderMailService(
            sender,
            new OrderMailRenderer()
        );

        OrderMailData order = new OrderMailData(
            "Nguyễn Thị Ánh",
            "ORD-2026-001",
            "https://shop.example.com/orders/ORD-2026-001",
            "450.000 ₫"
        );

        service.send("customer@example.net", order);

        ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender).send(captor.capture());

        MimeMessage sent = captor.getValue();
        sent.saveChanges();

        assertThat(sent.getSubject())
            .isEqualTo("Xác nhận đơn hàng ORD-2026-001");

        assertThat(
            ((InternetAddress) sent.getFrom()[0]).getAddress()
        ).isEqualTo("orders@example.com");

        assertThat(
            ((InternetAddress) sent.getAllRecipients()[0]).getAddress()
        ).isEqualTo("customer@example.net");
    }
}
```

Điểm chính:
- `JavaMailSender` là mock.
- `MimeMessage` là đối tượng Jakarta Mail thật nhưng **nằm trong bộ nhớ**.
- `send(...)` không được thực thi qua `JavaMailSenderImpl`.
- Có thể xác minh dữ liệu email mà không tạo side effect SMTP.

### 9.1. Capture argument thay vì verify một boolean chung

Nếu service gửi hai email hoặc gọi sender nhiều lần, cần phân biệt các message bằng mã nghiệp vụ, recipient hoặc message key. Không nên chỉ kiểm tra số lần gửi rồi mặc định mọi message đều đúng.

### 9.2. Đừng lưu đối tượng mutable rồi sửa sau khi đã gửi

`MimeMessage` là mutable. Nếu production code tái sử dụng cùng đối tượng cho nhiều recipient hoặc nhiều lần gửi, test capture có thể nhìn thấy trạng thái cuối đã bị sửa, làm che mất lỗi.

Tốt nhất là tạo **một MimeMessage riêng cho mỗi email logic/lần gửi phù hợp**, không chia sẻ qua thread. Khi cần snapshot chính xác, serialize message tại thời điểm gọi `send` trong test stub/answer rồi parse lại để kiểm tra.

## 10. Kiểm tra plain text và HTML bên trong MIME tree

Với `helper.setText(plain, html)`, `MimeMessage` thường chứa `multipart/alternative`, có thể lồng trong `multipart/mixed` và `multipart/related` tùy chế độ multipart.

```text
MimeMessage
  |
  +-- multipart/mixed
       |
       +-- multipart/related
            |
            +-- multipart/alternative
                 |
                 +-- text/plain; charset=UTF-8
                 |
                 +-- text/html; charset=UTF-8
```

Cấu trúc cụ thể phụ thuộc cách tạo message. Không nên giả định `message.getContent()` là `String` hoặc plain part luôn nằm trực tiếp ở root.

### 10.1. Helper duyệt MIME parts đệ quy

```java
package com.example.mail;

import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.util.ArrayList;
import java.util.List;

public final class MimePartFinder {

    private MimePartFinder() {}

    public static List<Part> find(
            Part root,
            String mimeType) throws Exception {

        List<Part> matches = new ArrayList<>();
        visit(root, mimeType, matches);
        return matches;
    }

    private static void visit(
            Part part,
            String mimeType,
            List<Part> matches) throws Exception {

        if (part.isMimeType(mimeType)) {
            matches.add(part);
            return;
        }

        Object content = part.getContent();

        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                visit(multipart.getBodyPart(i), mimeType, matches);
            }
        }
    }
}
```

Đây là helper phù hợp với MIME multipart thông thường trong bài học. Khi hệ thống có forwarded `message/rfc822` hoặc file đính kèm dạng `text/plain`, cần lọc `Content-Disposition` hoặc giới hạn vị trí của **body** chính để tránh nhầm part trong attachment với plain fallback.

### 10.2. Test có cả plain/HTML, không có SMTP

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.util.List;
import java.util.Properties;

class MimeBodyUnitTest {

    @Test
    void containsBothBodyAlternatives() throws Exception {
        MimeMessage message = new MimeMessage(
            Session.getInstance(new Properties())
        );

        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        String plain =
            "Xin chào Nguyễn Thị Ánh,\nTổng tiền: 450.000 ₫";
        String html =
            "<html><body><p>Xin chào Nguyễn Thị Ánh</p>"
                + "<p>Tổng tiền: 450.000 ₫</p></body></html>";

        helper.setText(plain, html);
        message.saveChanges();

        List<Part> plainParts =
            MimePartFinder.find(message, "text/plain");
        List<Part> htmlParts =
            MimePartFinder.find(message, "text/html");

        assertThat(plainParts).hasSize(1);
        assertThat(htmlParts).hasSize(1);

        assertThat((String) plainParts.get(0).getContent())
            .isEqualTo(plain);

        assertThat((String) htmlParts.get(0).getContent())
            .isEqualTo(html);
    }
}
```

Test này không gọi sender, không cần SMTP host. Nó xác minh khả năng xây MIME body của Spring/Jakarta Mail.

### 10.3. Test charset thay vì phụ thuộc transfer encoding

Có thể kiểm tra `Content-Type`:

```java
import jakarta.mail.internet.ContentType;

Part plainPart =
    MimePartFinder.find(message, "text/plain").get(0);

ContentType type =
    new ContentType(plainPart.getContentType());

assertThat(type.getBaseType())
    .isEqualToIgnoringCase("text/plain");

assertThat(type.getParameter("charset"))
    .isEqualToIgnoringCase("UTF-8");
```

Đừng yêu cầu raw MIME luôn dùng một dạng Base64 hoặc quoted-printable cố định. Cả hai đều có thể hợp lệ khi Jakarta Mail decode trả đúng nội dung.

## 11. Serialize và parse lại MIME để kiểm tra kỹ hơn

Một `MimeMessage` tạo trong bộ nhớ có thể được viết thành raw MIME bytes rồi parse lại bằng Jakarta Mail, **không cần mạng**.

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;

Session session = Session.getInstance(new Properties());
MimeMessage original = new MimeMessage(session);

// Populate headers and body via MimeMessageHelper.
MimeMessageHelper helper =
    new MimeMessageHelper(original, false, "UTF-8");
helper.setSubject("Hóa đơn của Ánh 🎉");
helper.setText("Tổng tiền: 450.000 ₫", false);

original.saveChanges();

ByteArrayOutputStream bytes = new ByteArrayOutputStream();
original.writeTo(bytes);

MimeMessage decoded = new MimeMessage(
    session,
    new ByteArrayInputStream(bytes.toByteArray())
);
```

Assertion:

```java
assertThat(decoded.getSubject())
    .isEqualTo("Hóa đơn của Ánh 🎉");

assertThat(decoded.isMimeType("text/plain")).isTrue();

assertThat((String) decoded.getContent())
    .isEqualTo("Tổng tiền: 450.000 ₫");
```

Điều này kiểm tra cả serialization và decoding ở tầng MIME mà vẫn không có SMTP. Nếu message có nhiều parts, dùng helper duyệt MIME tree thay vì ép `getContent()` về `String`.

### 11.1. Không nhầm raw MIME với decoded content

Raw MIME có thể chứa:

```text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64
```

Khi đó câu `Tổng tiền: 450.000 ₫` sẽ không nằm nguyên dạng UTF-8 dễ đọc trong raw source. Test nên đọc `getContent()` sau parse, không tìm literal tiếng Việt trong raw bytes đã transfer-encode.

### 11.2. Đừng hardcode Message-ID và MIME boundary

`saveChanges()` có thể tạo `Message-ID`, `Date`, boundary và các headers. Những giá trị này có thể thay đổi theo thư viện, thời điểm và môi trường.

Unit test nội dung không nên so sánh toàn bộ raw MIME byte-for-byte trừ khi mục tiêu trực tiếp là kiểm tra serialization contract có chủ đích. Hãy assert theo ý nghĩa: sender, recipient, subject, part types, body và attachment.

## 12. Test attachment mà không cần file thật hoặc SMTP

Một email có hóa đơn PDF hoặc báo cáo có thể được kiểm tra bằng **tài nguyên in-memory**. Với Spring, `ByteArrayResource` phù hợp khi dữ liệu nhỏ và được tạo ngay trong test.

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.nio.charset.StandardCharsets;
import java.util.Properties;

MimeMessage message = new MimeMessage(
    Session.getInstance(new Properties())
);

MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn tháng 11");
helper.setText(
    "Hóa đơn được đính kèm trong email.",
    "<p>Hóa đơn được đính kèm trong email.</p>"
);

byte[] attachmentBytes =
    "invoice,amount\nINV-001,450000\n"
        .getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
    "invoice.csv",
    new ByteArrayResource(attachmentBytes),
    "text/csv; charset=UTF-8"
);

message.saveChanges();
```

Nội dung CSV chỉ là dữ liệu giả. Không dùng hóa đơn hoặc tài liệu chứa thông tin khách hàng thật trong unit test.

### 12.1. Tìm attachment theo disposition

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.util.ArrayList;
import java.util.List;

static void findAttachments(Part part, List<Part> result)
        throws Exception {

    String disposition = part.getDisposition();

    if (Part.ATTACHMENT.equalsIgnoreCase(disposition)) {
        result.add(part);
        return;
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            findAttachments(multipart.getBodyPart(i), result);
        }
    }
}
```

Sau đó:

```java
List<Part> attachments = new ArrayList<>();
findAttachments(message, attachments);

assertThat(attachments).hasSize(1);
assertThat(attachments.get(0).getFileName())
    .isEqualTo("invoice.csv");
```

Trong thực tế, một số MIME parts có filename nhưng disposition không đúng hoặc bị thiếu; nếu ứng dụng phải xử lý mail từ bên ngoài, cần một parser tổng quát hơn. Với message do chính service của bạn tạo, test này đủ minh họa việc kiểm tra attachment đã được khai báo.

### 12.2. Không dùng InputStream một lần rồi bỏ qua lifecycle

`MimeMessageHelper.addAttachment(...)` và `addInline(...)` có thể cần mở lại resource stream trong quá trình xử lý. `ByteArrayResource` có thể tạo nhiều stream mới từ bytes đã có. Một `InputStreamResource` bọc stream dùng một lần có thể không phù hợp với một số luồng tạo MIME. Kiểm thử với resource có thể đọc lại để tránh lỗi khó tái hiện khi gửi.

## 13. Test inline images mà không gửi email thật

Nếu HTML có:

```html
<img src="cid:brand-logo" alt="Logo cửa hàng">
```

Có thể kiểm tra:
- HTML chứa tham chiếu `cid:brand-logo`;
- MIME có image part với `Content-ID` tương ứng;
- plain-text fallback không phụ thuộc ảnh;
- resource được thêm đúng thứ tự sau `setText`.

Ví dụ:

```java
MimeMessage message = new MimeMessage(
    Session.getInstance(new Properties())
);

MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

String plain = "Thông báo từ Example Store.";
String html =
    "<html><body><img src=\"cid:brand-logo\" alt=\"Logo\">"
        + "<p>Thông báo từ Example Store.</p></body></html>";

helper.setText(plain, html);

byte[] smallPngBytes = loadTestPngBytes();

helper.addInline(
    "brand-logo",
    new ByteArrayResource(smallPngBytes),
    "image/png"
);
```

`loadTestPngBytes()` là fixture helper do test định nghĩa và cần trả về PNG hợp lệ nếu kiểm tra nội dung ảnh. Khi chỉ kiểm tra MIME relationship, dữ liệu bytes có thể do fixture kiểm soát mà không gọi network.

**Chỉ kiểm tra MIME bằng unit test không chứng minh mọi mail client sẽ hiển thị CID image**, vì hành vi client và policy hình ảnh là vấn đề compatibility test.

## 14. Test không gọi sender khi dữ liệu không hợp lệ

Unit test có thể kiểm chứng những trường hợp service phải **từ chối trước khi gửi**.

Ví dụ service:

```java
public void sendToVerifiedRecipient(
        String recipient,
        boolean verified,
        String content) {

    if (!verified) {
        throw new IllegalArgumentException(
            "Recipient must be verified"
        );
    }

    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("security@example.com");
    message.setTo(recipient);
    message.setSubject("Thông báo bảo mật");
    message.setText(content);

    sender.send(message);
}
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void doesNotSendToUnverifiedRecipient() {
    MailSender sender = mock(MailSender.class);
    SecurityMailService service = new SecurityMailService(sender);

    assertThatThrownBy(() ->
        service.sendToVerifiedRecipient(
            "unverified@example.net",
            false,
            "Thông báo"
        )
    ).isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(sender);
}
```

`SecurityMailService` là lớp minh họa chứa phương thức tương ứng. Ở hệ thống thật, xác thực và phân quyền recipient cần được kiểm soát ở service/repository thích hợp. Test này chỉ bảo đảm **không phát sinh lời gọi gửi** trong nhánh bị từ chối.

Các trường hợp có thể kiểm tra tương tự:
- không có quyền gửi cho đơn hàng;
- địa chỉ recipient không được phép theo business policy;
- người dùng đã hủy đăng ký marketing;
- yêu cầu gửi trùng bị idempotency guard chặn;
- template data thiếu trường bắt buộc.

Đừng dùng mock sender để biện minh rằng validation input nào cũng là “an toàn”; việc xác thực recipient và domain là logic riêng cần được test.

## 15. Test xử lý MailException mà không gây lỗi mạng thật

Muốn biết service phản ứng ra sao khi gửi thất bại, không cần chặn firewall hoặc làm SMTP provider offline. Có thể điều khiển mock ném exception.

### 15.1. MailSendException giả lập

```java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;

JavaMailSender sender = mock(JavaMailSender.class);

doThrow(new MailSendException("Simulated send failure"))
    .when(sender)
    .send(any(MimeMessage.class));
```

Đây là exception **giả lập có chủ đích**, không phải một SMTP reply thật. Service có thể ghi trạng thái lỗi, tái ném exception hoặc trả kết quả theo contract.

### 15.2. Verify service xử lý lỗi theo chính sách

Giả sử service được thiết kế:

```java
public enum SubmissionStatus {
    ACCEPTED,
    FAILED
}

public SubmissionStatus sendAndReport(MimeMessage message) {
    try {
        sender.send(message);
        return SubmissionStatus.ACCEPTED;
    } catch (MailException ex) {
        return SubmissionStatus.FAILED;
    }
}
```

Test có thể:

```java
@Test
void reportsFailureWhenSenderThrows() {
    JavaMailSender sender = mock(JavaMailSender.class);

    doThrow(new MailSendException("Test failure"))
        .when(sender)
        .send(any(MimeMessage.class));

    SubmissionService service = new SubmissionService(sender);

    MimeMessage message = new MimeMessage(
        Session.getInstance(new Properties())
    );

    assertThat(service.sendAndReport(message))
        .isEqualTo(SubmissionStatus.FAILED);
}
```

`SubmissionService` là class minh họa bao bọc logic phía trên. Tên trạng thái `ACCEPTED` trong ví dụ chỉ có nghĩa thao tác `send` hoàn tất không lỗi đồng bộ; không phải email delivered hay opened.

### 15.3. Cẩn thận khi coi mọi lỗi đều chắc chắn chưa gửi

SMTP có những tình huống **không rõ kết quả**, ví dụ relay đã nhận DATA nhưng mạng đứt trước khi client thấy response. Nếu production system có outbox/retry, unit test cần kiểm tra việc phân loại lỗi thay vì giả định mọi exception là `FAILED` chắc chắn.

Một policy có thể phân loại:
- lỗi validation/preparation: không retry nguyên input;
- lỗi tạm thời được xác định trước submission: retry có backoff;
- lỗi không xác định đã được SMTP tiếp nhận hay chưa: `UNKNOWN`, cần reconciliation;
- lỗi xác thực/configuration: không retry dồn dập.

Unit test có thể truyền các exception hoặc outcomes giả lập vào **classifier thuần** và kiểm tra quyết định. Không cần tạo sự cố mạng thật để test state transition.

## 16. Test idempotency, outbox và queue worker không cần SMTP

Các ứng dụng gửi mail quan trọng thường không gọi SMTP trực tiếp trong HTTP request mà tạo outbox job, sau đó background worker gửi.

```text
HTTP request
    |
    v
Application service
    |
    | insert email_outbox(messageKey, PENDING)
    v
Database / queue
    |
    v
Worker
    |
    | JavaMailSender.send(...)
    v
SMTP provider
```

Unit test nên kiểm tra:
1. Yêu cầu nghiệp vụ hợp lệ tạo đúng một outbox item.
2. Request cùng idempotency key không tạo item thứ hai.
3. Worker chỉ gửi job được claim thành công.
4. Job `PENDING` chuyển sang trạng thái phù hợp.
5. Khi sender ném exception, retry policy được gọi và trạng thái được lưu.
6. Không có SMTP request thật.

### 16.1. Ví dụ worker giả lập repository và sender

```java
public class OutboxWorker {

    private final OutboxRepository repository;
    private final JavaMailSender sender;

    public OutboxWorker(
            OutboxRepository repository,
            JavaMailSender sender) {
        this.repository = repository;
        this.sender = sender;
    }

    public void process(OutboxJob job, MimeMessage mimeMessage) {
        sender.send(mimeMessage);
        repository.markAccepted(job.messageKey());
    }
}
```

Test:

```java
@Test
void marksAcceptedAfterSendReturns() {
    OutboxRepository repository = mock(OutboxRepository.class);
    JavaMailSender sender = mock(JavaMailSender.class);

    OutboxWorker worker = new OutboxWorker(repository, sender);

    OutboxJob job = new OutboxJob("msg-001");
    MimeMessage mime = new MimeMessage(
        Session.getInstance(new Properties())
    );

    worker.process(job, mime);

    InOrder calls = inOrder(sender, repository);
    calls.verify(sender).send(mime);
    calls.verify(repository).markAccepted("msg-001");
}
```

Cần import `org.mockito.InOrder`, `Mockito.inOrder` và các lớp repository/job của ứng dụng. `OutboxJob` ở ví dụ là model tối giản có `messageKey()`, không phải class được Spring cung cấp.

Test này kiểm tra **thứ tự lời gọi trong code**, không chứng minh outbox transaction hoặc SMTP delivery. Những bảo đảm về locking, concurrency, database transaction và broker ack cần thêm integration tests với hạ tầng tương ứng.

### 16.2. Tránh logic retry chạy thật lâu trong unit test

Nếu worker dùng exponential backoff, không nên để JUnit ngủ 2, 4, 8, 16 giây rồi mới assert. Thay bằng:
- test `RetryPolicy` như hàm thuần trả delay/nextAttemptAt;
- inject `Clock` hoặc scheduler có thể kiểm soát;
- mock repository/scheduler;
- verify số attempt được lên lịch, không chờ wall clock;
- kiểm tra giới hạn retry budget và trạng thái `UNKNOWN`.

Không thiết kế unit test phụ thuộc chính xác thời gian JVM scheduler và tốc độ CPU CI.

## 17. Trường hợp service dùng MimeMessagePreparator

`JavaMailSender` còn có overload nhận `MimeMessagePreparator`, giúp ứng dụng truyền một callback chuẩn bị email.

Ví dụ production:

```java
public void sendReceipt(String recipient, String text) {
    sender.send(mime -> {
        MimeMessageHelper helper =
            new MimeMessageHelper(mime, false, "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");
        helper.setText(text, false);
    });
}
```

Nếu chỉ mock `sender.send(preparator)`, callback **không tự chạy**, nên test không thể kiểm tra email đã chuẩn bị.

### 17.1. Dùng Mockito Answer để chạy preparator trên message in-memory

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessagePreparator;

import java.util.Properties;
import java.util.concurrent.atomic.AtomicReference;

JavaMailSender sender = mock(JavaMailSender.class);
AtomicReference<MimeMessage> captured = new AtomicReference<>();

doAnswer(invocation -> {
    MimeMessagePreparator preparator = invocation.getArgument(0);

    MimeMessage mime = new MimeMessage(
        Session.getInstance(new Properties())
    );

    preparator.prepare(mime);
    mime.saveChanges();
    captured.set(mime);
    return null;
}).when(sender).send(any(MimeMessagePreparator.class));

// Gọi service thật dùng sender mock.
service.sendReceipt(
    "customer@example.net",
    "Xin chào Nguyễn Thị Ánh."
);

assertThat(captured.get()).isNotNull();
assertThat(captured.get().getSubject())
    .isEqualTo("Hóa đơn của bạn");
assertThat((String) captured.get().getContent())
    .contains("Nguyễn Thị Ánh");
```

Trong ví dụ, `service` là đối tượng có phương thức `sendReceipt` đã được cấu hình sử dụng `sender` mock. `doAnswer` chạy preparator trong bộ nhớ, không chuyển sang SMTP.

### 17.2. Không vô tình gọi transport thật trong Answer

Chỉ gọi `prepare(mime)`, `saveChanges` và inspect MIME. Không gọi `Transport.send(mime)` hoặc tạo `JavaMailSenderImpl` để “giả lập gửi”, vì như vậy sẽ mở lại network boundary mà test định cô lập.

## 18. Có nên viết FakeJavaMailSender thay cho Mockito?

Không phải bài test nào cũng cần Mockito. Khi nhiều test cùng kiểm tra email đã yêu cầu gửi, một **in-memory fake sender** có thể thuận tiện. Fake có thể giữ danh sách các message đã được gửi ở mức API nhưng không gửi SMTP thật.

Ví dụ khái niệm:

```text
Production:
MailService -> JavaMailSenderImpl -> SMTP

Unit tests:
MailService -> InMemoryMailSender -> captured messages
```

Fake cần tuân theo contract tối thiểu:
- `createMimeMessage()` trả message hợp lệ.
- `send(...)` chỉ ghi nhận, không mở socket.
- Mỗi message lưu một snapshot nếu code có nguy cơ sửa message sau gửi.
- Có cách reset giữa các test.
- Không silently “thành công” ở các overload chưa hỗ trợ nếu điều đó che lỗi; có thể ném `UnsupportedOperationException` cho phần không dùng.

Mockito thường phù hợp hơn khi:
- cần xác minh số lần gọi và thứ tự;
- muốn giả lập `MailSendException`;
- service có ít test cases;
- không muốn bảo trì implementation của toàn bộ `JavaMailSender`.

Fake có ích khi:
- nhiều test cần đọc danh sách email từ một use case;
- team muốn DSL như `sentEmails()`;
- đã thống nhất hợp đồng snapshot và overload.

### 18.1. Đừng dùng spy trên sender thật để “an toàn”

`spy(new JavaMailSenderImpl())` **không đồng nghĩa** ngăn network. Nếu một lời gọi không được stub, spy có thể chạy implementation thật và gửi SMTP. Khi mục tiêu là không phụ thuộc mail server, ưu tiên mock thuần hoặc fake in-memory được thiết kế rõ ràng.

### 18.2. Embedded SMTP server có phải unit test không?

Các công cụ SMTP sandbox chạy trong tiến trình hoặc trong container có thể rất hữu ích để kiểm tra giao thức. Nhưng khi service thực hiện SMTP/TCP dù chỉ tới `localhost`, đó thường là **integration test** đối với network protocol và SMTP transport, không phải unit test cô lập như Mockito.

Không có gì sai khi dùng embedded/test SMTP; hãy đặt nó vào bộ kiểm thử phù hợp và không yêu cầu nó chạy cho mọi unit test.

## 19. Ngăn test vô tình gửi mail thật

Không nên chỉ tin rằng “trong CI chắc không có SMTP credential”. Một máy developer hoặc CI agent có thể vô tình có biến môi trường thật.

Các biện pháp quan trọng:
- Dùng constructor injection cho sender.
- Unit tests luôn dùng mock/fake sender.
- Không gọi `JavaMailSenderImpl.send` trong unit test.
- Không dùng người nhận thật trong fixture; sử dụng domain ví dụ như `example.com` và `example.net`.
- Không copy API keys, SMTP passwords hoặc token thật vào source test.
- Tách rõ cấu hình `test` với `dev/staging/production`.
- Không tự khởi động job gửi email theo lịch trong các test không yêu cầu.
- Giới hạn egress network của môi trường test nếu hạ tầng cho phép.
- Integration tests dùng provider sandbox/test SMTP được cấp phép.

### 19.1. Nếu Spring context tự cấu hình sender thật

Một test có `@SpringBootTest` và mail starter có thể tạo sender thật nếu nhận đủ properties. Bản thân việc tạo bean chưa chắc mở socket, nhưng:
- bean khác có thể gửi mail khi được khởi tạo;
- application event listener có thể gửi khi context startup;
- scheduled job có thể chạy;
- `spring.mail.test-connection=true` có thể kiểm tra kết nối lúc khởi động.

Vì vậy, với **unit test**, không khởi động full context nếu không cần. Với test Spring context, thay sender bằng một test double và vô hiệu hóa các nguồn side effect không thuộc phạm vi test.

### 19.2. Test profile không phải lớp bảo vệ duy nhất

Giả sử có:

```yaml
# application-test.yml (minh họa)
spring:
  mail:
    host: localhost
    port: 2525
```

Nếu service gọi thật mà không có server `localhost:2525`, test vẫn fail vì connection refused. Nếu có một process khác lắng nghe cổng đó, test có thể phát sinh side effect ngoài ý muốn. **Đổi host không phải là mock**.

Unit test không cần đi tới cổng SMTP nào cả.

### 19.3. Kiểm soát @Async và @Scheduled

Nếu ứng dụng gửi email bằng `@Async` hoặc scheduler:
- unit test gọi trực tiếp logic worker/service thay vì phụ thuộc thread pool thật;
- inject executor/scheduler hoặc tách logic gửi khỏi entry point bất đồng bộ;
- vô hiệu hóa scheduler trong test context không cần nó;
- không để test kết thúc trước khi job gửi hoàn thành;
- chỉ kiểm tra concurrent scheduling ở một bộ test chuyên dụng với đồng bộ rõ ràng.

Việc một method có annotation `@Async` không đảm bảo test đang gọi qua Spring proxy hoặc thực sự kiểm tra asynchronous behavior. Đừng suy ra quá mức từ một plain Java unit test gọi trực tiếp method.

## 20. Thiết kế test deterministic và dễ bảo trì

### 20.1. Giữ fixture cố định

Ví dụ dữ liệu test:

```text
Recipient: customer@example.net
Customer: Nguyễn Thị Ánh
Order ID: ORD-2026-001
Amount: 450.000 ₫
Action URL: https://shop.example.com/orders/ORD-2026-001
```

Chọn ID giả, URL giả và dữ liệu không nhạy cảm. Khi cần timestamp, dùng `Clock.fixed(...)` thay vì `Instant.now()` trong renderer/business logic. Nếu cần locale, inject `Locale.forLanguageTag("vi-VN")` thay vì dùng locale mặc định máy.

### 20.2. Không assert chi tiết MIME ngẫu nhiên

Tránh assert trực tiếp:
- boundary string;
- Message-ID do thư viện tạo;
- Date header theo đồng hồ thực;
- thứ tự các header không quan trọng;
- raw Content-Transfer-Encoding cố định;
- số tầng multipart nếu API chỉ cam kết có plain/HTML.

Ưu tiên assert:
- decoded subject và body;
- MIME type và charset;
- recipients;
- tên file đính kèm;
- URL hành động và dữ kiện nghiệp vụ.

### 20.3. Test exception và retry ở lớp thích hợp

Test unit của `MailRetryPolicy` có thể nhận `FailureCategory` do classifier cung cấp, rồi trả:
- `RETRY_AFTER`;
- `FAILED_PERMANENT`;
- `UNKNOWN_REQUIRES_RECONCILIATION`.

Không cần cố tái hiện handshake TLS thật hoặc SMTP timeout thật. Các điều kiện giao thức cụ thể nên nằm ở integration/contract tests.

### 20.4. Tránh sự phụ thuộc giữa các test

Mỗi test nên tạo sender mock, message và fixture riêng. Không dùng biến static chứa `MimeMessage` mutable chia sẻ cho nhiều test; không để test A sửa message của test B. Với fake sender giữ danh sách, reset state mỗi test.

## 21. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Test cần mạng và SMTP credential | Service dùng `JavaMailSenderImpl` thật | Inject `JavaMailSender`, thay bằng mock. |
| `NullPointerException` ở `MimeMessageHelper` | Mock `createMimeMessage()` mặc định trả null | Stub trả `MimeMessage` in-memory thật. |
| Test pass dù gửi sai địa chỉ | Chỉ verify `send(any())` | Capture và inspect `To`/`From`. |
| Test pass dù body sai | Không kiểm tra MIME parts | Duyệt plain/HTML và assert decoded content. |
| Test fail vì thiếu localhost SMTP | Đổi host sang localhost nhưng vẫn gọi transport thật | Mock sender hoặc tách SMTP integration test. |
| Test chạy chậm/ngẫu nhiên | Dùng `@SpringBootTest`, queue/scheduler và mạng cho mọi test | Giữ unit test plain Java, mock I/O. |
| Test mã hóa Unicode fail | Charset, normalization hoặc raw MIME parsing sai | Dùng UTF-8 và decoded MIME assertions. |
| Test phụ thuộc giá trị boundary | Assert raw MIME nguyên văn | Assert MIME semantics. |
| `MimeMessagePreparator` không tạo content trong test | Mock send callback mà không thực thi preparator | Dùng Mockito Answer để gọi `prepare` trên message in-memory. |
| Test chạy SMTP thật dù đã dùng spy | Spy gọi method thật nếu chưa stub | Dùng mock thuần/fake. |
| Test gọi email thật tới khách hàng | Dữ liệu fixture/credentials thật | Domain giả và sender không có network. |
| Test race condition | Async/scheduler hoạt động ngoài phạm vi unit test | Cô lập worker; test concurrency riêng. |
| Email fail nhưng test lại ghi “delivered” | Nhầm send invocation với provider delivery | Gọi trạng thái theo đúng contract, dùng integration/events cho delivery. |
| Retry test ngủ nhiều giây | Test chạy backoff thật | Inject clock/scheduler, test delay như giá trị. |
| Fake sender cho qua mọi overload | Fake quá đơn giản, che lỗi API | Thực thi contract cần dùng hoặc fail fast với overload chưa hỗ trợ. |
| Test nhầm attachment với plain body | Chỉ tìm part theo `text/plain` | Giới hạn MIME body, kiểm tra disposition. |

## 22. Chiến lược test pyramid cho Spring Framework Mail

Không phụ thuộc SMTP server thật trong **unit test** không có nghĩa bỏ SMTP integration tests. Một bộ kiểm thử cân đối:


```text
            ┌─────────────────────────┐
            │ End-to-end mailbox test │
            │ ít, có kiểm soát        │
            └───────────┬─────────────┘
               ┌────────┴────────┐
               │ SMTP integration│
               │ test server /   │
               │ provider sandbox│
               └────────┬────────┘
         ┌──────────────┴──────────────┐
         │ Unit tests (nhiều nhất)     │
         │ renderer, service, MIME,    │
         │ validation, retry policy    │
         └─────────────────────────────┘
```

### 22.1. Unit tests

- Không mạng và không secrets.
- Mock/fake `JavaMailSender`.
- In-memory `MimeMessage` với Jakarta Mail thật.
- Test plain text/HTML, charset, Unicode, attachments.
- Test các nhánh validation, business rules và retry decision.

### 22.2. SMTP integration tests

- Kết nối tới SMTP sandbox hoặc test SMTP server do team kiểm soát.
- Kiểm tra TLS mode, AUTH khi cần, SMTP submission và response.
- Có thể kiểm tra SMTP envelope/header và raw message được server nhận.
- Không dùng recipient thật hoặc gửi email marketing thật.
- Có cơ chế khởi tạo/dọn dẹp và tách riêng khỏi unit-test suite.

### 22.3. End-to-end tests

- Chạy ít và có mục tiêu rõ ràng.
- Dùng mailbox thử nghiệm và domain/recipient được cấp quyền.
- Kiểm tra việc provider nhận/giao message và kết quả mail client.
- Đánh giá các tình huống deliverability, spam/quarantine hoặc bounce khi cần.
- Không bắt mọi commit code phải chờ một provider bên ngoài hoạt động.

**Một unit test xanh cho biết logic đã qua kiểm tra, không phải chứng nhận toàn bộ hệ thống SMTP đang hoạt động.**

## 23. Bài tập thực hành

### Bài 1 — Đổi service sang constructor injection

Một service đang tự tạo `JavaMailSenderImpl`. Hãy refactor phụ thuộc vào `JavaMailSender` được inject, rồi test gửi thông báo bằng Mockito mà không cấu hình SMTP.

### Bài 2 — Capture SimpleMailMessage

Viết service gửi lời chào; test `To`, `From`, `Subject` và plain text bằng `ArgumentCaptor<SimpleMailMessage>`.

### Bài 3 — MimeMessage in-memory

Dùng `Session.getInstance(new Properties())` tạo `MimeMessage` rồi stub `createMimeMessage()`. Gọi service và capture message qua `send(...)`.

### Bài 4 — Plain và HTML alternatives

Tạo `MimeMessageHelper(message, true, "UTF-8")`, gọi `setText(plain, html)`. Duyệt MIME tree để xác nhận `text/plain` và `text/html` tồn tại mà không gọi SMTP.

### Bài 5 — Unicode

Dùng tên `Nguyễn Thị Ánh`, số tiền `450.000 ₫` và emoji `🚀`. Serialize MIME ra bytes rồi parse lại và assert decoded content vẫn chính xác.

### Bài 6 — Attachment từ ByteArrayResource

Thêm `invoice.csv` từ bytes giả, assert tên file, MIME type và dữ liệu cần thiết. Không đọc file dữ liệu thật hoặc tải qua mạng.

### Bài 7 — MimeMessagePreparator

Service dùng `sender.send(preparator)`. Dùng `doAnswer` chạy `prepare` trên MimeMessage in-memory rồi kiểm tra recipient/subject/body.

### Bài 8 — Test lỗi SMTP giả lập

Dùng Mockito `doThrow(new MailSendException("Simulated failure"))`, kiểm tra service cập nhật outcome phù hợp mà không làm server SMTP thật bị lỗi.

### Bài 9 — Validation

Khi người nhận chưa được xác minh hoặc không có quyền nhận hóa đơn, assert exception phù hợp và `verifyNoInteractions(sender)`.

### Bài 10 — Retry policy không ngủ

Viết `MailRetryPolicy` trả delay/backoff và số attempt tối đa. Dùng `Clock.fixed` hoặc input timestamp cố định để test kết quả mà không gọi `Thread.sleep`.

### Bài 11 — Outbox worker

Mock repository và sender; verify worker chỉ gọi `markAccepted` sau `send(...)` thành công. Với lỗi, kiểm tra trạng thái retry/unknown mà không kết nối SMTP.

### Bài 12 — Test profile an toàn

Một `@SpringBootTest` đang gửi mail thật khi startup. Xác định listener/scheduler/test-connection gây side effect, thay sender bằng test double và vô hiệu hóa tác vụ không thuộc phạm vi test.

### Bài 13 — Ranh giới test

Giải thích vì sao `verify(sender).send(any(MimeMessage.class))` không thể chứng minh:
- SPF/DKIM/DMARC pass;
- SMTP relay đã nhận;
- email vào Inbox;
- người dùng đã mở thư.

Đề xuất integration/end-to-end test tương ứng.

### Bài 14 — Fake và mock

So sánh một `InMemoryMailSender` tự ghi nhận message với Mockito mock. Chỉ ra ưu điểm, điểm phải bảo trì và rủi ro khi dùng spy trên sender thật.

### Bài 15 — Kiểm tra test không rò rỉ network

Thiết kế quy tắc cho bộ unit-test suite: không sử dụng `JavaMailSenderImpl.send`, không có secrets, không phụ thuộc hostname SMTP, không bắt buộc local mail server. Mô tả cách CI tách bộ integration tests khỏi unit tests.

## 24. Tổng kết

**Không phụ thuộc mail server thật trong unit test** là nguyên tắc quan trọng để kiểm thử Spring Framework Mail nhanh, đáng tin cậy và an toàn:

1. Thiết kế service phụ thuộc **`MailSender` hoặc `JavaMailSender` interface**, không tự tạo sender SMTP thật bên trong nghiệp vụ.
2. Dùng **Mockito mock** tại ranh giới gửi; với `SimpleMailMessage`, capture và assert trực tiếp các field.
3. Với MIME, stub `createMimeMessage()` trả một **`MimeMessage` thật trong bộ nhớ**, rồi capture đối tượng truyền tới `send(...)`.
4. Dùng `MimeMessageHelper` và Jakarta Mail thật để kiểm tra plain text, HTML, Unicode, charset, MIME tree, inline resources và attachment **mà không mở kết nối SMTP**.
5. Với `MimeMessagePreparator`, chủ động chạy callback bằng Mockito `Answer` nếu cần inspect message.
6. Dùng mock exception và test policy thuần để kiểm tra nhánh lỗi, retry, idempotency và outbox; không cần tạo outage của SMTP provider.
7. Tránh `JavaMailSenderImpl` thật, spy, startup listener hoặc scheduler chạy ngoài dự kiến trong unit tests.
8. Giữ test deterministic với fixture không nhạy cảm, clock/locale cố định, không so sánh MIME boundary ngẫu nhiên.
9. Tách **SMTP integration** và **end-to-end deliverability** thành các bộ test riêng để kiểm tra những điều unit test không thể chứng minh.

Nhờ đó, một thay đổi trong logic render hoặc gửi mail có thể được phát hiện ngay tại unit test, không bị nhiễu bởi network, credential hay trạng thái provider, đồng thời không có nguy cơ vô tình phát email thử nghiệm tới người nhận thật.
