# Gửi message qua SMTP và đọc lại message nhận được trong Spring Framework Mail

Trong Spring Framework Mail, một lời gọi `JavaMailSender.send(...)` thành công cho biết thư viện đã hoàn tất thao tác gửi tới SMTP server theo hợp đồng của transport. Nhưng nếu chỉ mock `JavaMailSender` rồi xác nhận method được gọi, ta chưa biết liệu một message thực tế có được SMTP server tiếp nhận hay không, subject có được mã hóa đúng hay không, HTML và plain text có được đóng gói thành MIME phù hợp hay attachment có bị mất dữ liệu hay không.

**Kiểm thử tích hợp gửi rồi đọc lại message** giải quyết khoảng trống đó: ứng dụng gửi bằng SMTP client thật tới một SMTP server kiểm thử, sau đó test đọc message mà server nhận được để xác minh nội dung, header, người nhận và cấu trúc MIME.

Trong hệ sinh thái Java/Spring, có thể dùng GreenMail chạy trong cùng process với JUnit, hoặc Mailpit/MailHog chạy trong container. Bài này sử dụng **GreenMail** cho ví dụ chính vì server có API trả về `MimeMessage[]`, tương thích cách làm việc của Jakarta Mail. Ngoài ra, bài còn giải thích cách đọc mailbox qua IMAP, kiểm thử Spring Boot context, xử lý async và những trường hợp không thể suy ra chỉ từ một SMTP capture test.

## 1. Mục tiêu kiểm thử

Một bài integration test gửi rồi đọc lại message nên kiểm chứng:

1. SMTP client đã kết nối tới một server kiểm thử thực sự, không phải mock.
2. Server nhận đúng số message mong đợi.
3. From, To, Cc, Reply-To và các header cần thiết được thiết lập đúng.
4. Subject có dấu tiếng Việt được giải mã đúng.
5. Plain text hoặc HTML có nội dung phù hợp.
6. MIME structure chứa đủ alternative parts, attachments và inline resources nếu use case cần.
7. Tài nguyên test được dọn sạch; không bị message của test khác làm sai kết quả.
8. Các workflow bất đồng bộ có cách chờ tín hiệu đến hạn, không dùng sleep cố định.

Sơ đồ:

~~~text
JUnit 5
  |
  v
Application mail service
  |
  v
JavaMailSender (không mock)
  |
  v
SMTP connection tới localhost
  |
  v
GreenMail SMTP server
  |
  v
Captured MimeMessage[]
  |
  v
JUnit assertions trên message server nhận
~~~

Khi kiểm tra message phía server, ta kiểm thử cả quá trình chuyển object ứng dụng thành dữ liệu gửi đi, thay vì chỉ đọc lại object đầu vào của chính mình.

## 2. Các mức kiểm thử mail khác nhau

| Mức | Hạ tầng sử dụng | Xác minh được | Không xác minh được |
| --- | --- | --- | --- |
| Unit test với mock sender | Mock `JavaMailSender` | Logic gọi gửi và tham số | SMTP transport và MIME thực sự |
| Test dựng MIME | `MimeMessageHelper`, Jakarta Mail | Header, body và MIME tree | Server có nhận thư không |
| **SMTP integration test** | Sender thật + SMTP server test | Server nhận message và có thể đọc MIME | Provider Internet có giao thư không |
| SMTP + IMAP test | Mail server test có mailbox | Có thể nhận qua SMTP và truy xuất qua IMAP | Inbox placement bên ngoài môi trường test |
| Provider sandbox | Account/SMTP provider kiểm thử | TLS, AUTH, quota/provider behavior | Tất cả mailbox providers sẽ xử lý như nhau |
| Production events | ESP/webhook/bounce/DSN | Phản hồi vận hành theo nguồn dữ liệu | Người thật chắc chắn đã đọc thư |

GreenMail rất phù hợp cho SMTP integration test; một unit test không nên phải chạy cả Spring Boot context nếu chỉ cần kiểm tra thuật toán xây subject hay nội dung.

## 3. Vì sao không dùng hộp thư thật để test trong CI?

Một test gửi tới tài khoản ngoài Internet có nhiều yếu tố không ổn định:

- Kết nối Internet, DNS, firewall và độ trễ SMTP.
- Credential, quota, account status, MFA và provider policy.
- Spam filter, quarantine hoặc quy tắc mailbox.
- Inbox có thư cũ hoặc thư bị xóa bởi người khác.
- Dữ liệu test có thể tới người dùng không mong muốn.
- Provider outage khiến build thất bại dù code ứng dụng không đổi.
- Test chạy song song có thể tranh cùng hộp thư và quota.

Một SMTP server cục bộ tạo môi trường có thể lặp lại, không phát email ra ngoài và cho phép đọc message ngay bằng test code.

~~~text
Môi trường test:
  host      = 127.0.0.1
  port      = cổng động của test server
  auth      = tắt hoặc dùng credential giả
  recipient = user@example.test

Môi trường production:
  host      = SMTP provider đã cấu hình
  auth      = credential/token được quản lý an toàn
  recipient = người nhận thực
~~~

Không commit credential production trong test source hoặc bật debug SMTP lộ password khi chạy pipeline.

## 4. GreenMail, Mailpit và MailHog

### GreenMail

GreenMail là một mail server dùng trong Java test. Nó hỗ trợ SMTP, cùng các giao thức truy xuất mailbox theo cấu hình. Với trường hợp đơn giản, có thể start server, gửi bằng `JavaMailSenderImpl`, rồi gọi `getReceivedMessages()`.

Ưu điểm:

- Chạy trong cùng JVM, không bắt buộc Docker.
- Trả về object Jakarta Mail `MimeMessage`.
- Thuận tiện kiểm tra MIME parts, header và attachment.
- Phù hợp JUnit 5 và Spring Boot integration tests.

### Mailpit / MailHog

Mailpit/MailHog là SMTP capture server thường chạy thành process/container riêng, có web UI và API tra message. Chúng hữu ích khi nhiều ngôn ngữ hoặc microservices cùng cần một endpoint test, hoặc developer muốn xem bản HTML trên giao diện.

Một test dùng Mailpit có thể:

~~~text
Spring JavaMailSender --> Mailpit SMTP:1025
                              |
                              v
                    Mailpit HTTP API/UI
                              |
                              v
                       Read captured mail
~~~

Port và API endpoint phụ thuộc công cụ/container được sử dụng. Khi thực thi, cần tuân theo schema API đúng phiên bản, không mặc định response HTTP là một `MimeMessage` của Jakarta Mail.

## 5. Dependencies cho Spring Mail, JUnit và GreenMail

Ví dụ Maven, chọn phiên bản GreenMail tương thích hệ Jakarta Mail của dự án:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.icegreen</groupId>
        <artifactId>greenmail</artifactId>
        <version>${greenmail.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`greenmail.version` là property do dự án đặt, không phải một version có sẵn. Với Spring Boot 3/Spring Framework 6, code dùng package `jakarta.mail.*` và cần GreenMail release tương thích Jakarta Mail. Những dự án Spring Boot 2 thường còn dùng `javax.mail.*`; không trộn namespace và dependency không tương thích.

Gradle tương tự:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-mail"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
    testImplementation "com.icegreen:greenmail:<compatible-version>"
}
~~~

Dòng cuối là placeholder phiên bản, cần thay bằng release thực tế theo project. Ví dụ code trong bài giả sử có JUnit 5, Java 17+ và Jakarta Mail.

## 6. Test đầu tiên: gửi plain text qua SMTP rồi đọc lại

Ví dụ này dùng một SMTP server nhúng trên cổng động. `JavaMailSenderImpl` thật sẽ gửi qua socket TCP; sau đó test lấy `MimeMessage` từ GreenMail.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;

import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.util.Properties;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class PlainMailSmtpIntegrationTest {

    private GreenMail smtp;
    private JavaMailSenderImpl sender;

    @BeforeEach
    void setUp() {
        ServerSetup setup = new ServerSetup(
            0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP
        );

        smtp = new GreenMail(setup);
        smtp.start();

        sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(smtp.getSmtp().getPort());
        sender.setProtocol("smtp");
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "false");
        props.put("mail.smtp.starttls.enable", "false");
        props.put("mail.smtp.connectiontimeout", "3000");
        props.put("mail.smtp.timeout", "3000");
        props.put("mail.smtp.writetimeout", "3000");
    }

    @AfterEach
    void tearDown() {
        if (smtp != null) {
            smtp.stop();
        }
    }

    @Test
    void sendsAndReadsMessageFromSmtpServer() throws Exception {
        SimpleMailMessage outgoing = new SimpleMailMessage();
        outgoing.setFrom("sender@example.test");
        outgoing.setTo("recipient@example.test");
        outgoing.setSubject("Xác nhận đơn hàng");
        outgoing.setText("Đơn hàng #A123 đã được xác nhận.");

        sender.send(outgoing);

        assertTrue(smtp.waitForIncomingEmail(5_000, 1));

        MimeMessage[] received = smtp.getReceivedMessages();
        assertEquals(1, received.length);

        MimeMessage actual = received[0];

        assertEquals(
            "sender@example.test",
            ((InternetAddress) actual.getFrom()[0]).getAddress()
        );

        assertEquals(
            "recipient@example.test",
            ((InternetAddress) actual.getRecipients(
                Message.RecipientType.TO)[0]).getAddress()
        );

        assertEquals("Xác nhận đơn hàng", actual.getSubject());
        assertTrue(actual.isMimeType("text/plain"));

        String text = (String) actual.getContent();
        assertTrue(text.contains(
            "Đơn hàng #A123 đã được xác nhận."
        ));
    }
}
~~~

Code này trực tiếp kiểm tra **message được SMTP server nhận**, chứ không phải chỉ đọc lại `SimpleMailMessage` ban đầu.

### Giải thích các thao tác

1. `new ServerSetup(0, "127.0.0.1", ...)` yêu cầu mở một SMTP server trên loopback với cổng tự chọn.
2. `smtp.start()` khởi động server trước khi client kết nối.
3. `smtp.getSmtp().getPort()` lấy cổng đang sử dụng.
4. `JavaMailSenderImpl` cấu hình gửi tới loopback, không phải provider thật.
5. `sender.send(outgoing)` truyền message bằng SMTP.
6. `waitForIncomingEmail(...)` có deadline, tránh phụ thuộc sleep cố định.
7. `getReceivedMessages()` trả object MIME đã được server ghi nhận.
8. JUnit kiểm tra số thư, from, to, subject và body.
9. `smtp.stop()` dọn tài nguyên sau test.

Nếu phiên bản mail server không hỗ trợ cổng động theo cách constructor trên, có thể dùng server setup test port cố định của GreenMail hoặc extension/container phù hợp, nhưng test song song phải tránh port collision.

## 7. Vì sao đọc lại MimeMessage thay vì object ban đầu?

Đây là assertion sai về mặt mục tiêu integration test:

~~~java
SimpleMailMessage outgoing = new SimpleMailMessage();
outgoing.setSubject("Hello");
sender.send(outgoing);

assertEquals("Hello", outgoing.getSubject());
~~~

Nó chỉ xác nhận object đã được gán subject trước đó. Nó không xác minh message đã tới SMTP server.

Cách đúng:

~~~java
MimeMessage actual = smtp.getReceivedMessages()[0];
assertEquals("Hello", actual.getSubject());
~~~

Nếu cần kiểm tra địa chỉ:

~~~java
InternetAddress from =
    (InternetAddress) actual.getFrom()[0];

assertEquals(
    "sender@example.test",
    from.getAddress()
);
~~~

Dùng `InternetAddress.getAddress()` thay vì `toString()` khi chỉ muốn email address, vì `toString()` có thể bao gồm display name và quoting.

## 8. Đợi email khi gửi bất đồng bộ

Với `JavaMailSender.send(...)` đồng bộ, email thường đã được SMTP test server nhận trước khi method trả về. Nhưng nếu gửi qua `@Async`, event listener, worker hoặc queue, caller có thể trả về khi message chưa được truyền.

Không nên:

~~~java
Thread.sleep(2000);
assertEquals(1, smtp.getReceivedMessages().length);
~~~

Test có thể vừa chậm vừa flaky do timing CI.

Tốt hơn:

~~~java
assertTrue(smtp.waitForIncomingEmail(5_000, 1));
assertEquals(1, smtp.getReceivedMessages().length);
~~~

Nếu workflow có nhiều trạng thái, có thể dùng Awaitility hoặc polling có deadline:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals(1, smtp.getReceivedMessages().length)
    );
~~~

Ví dụ Awaitility cần test dependency tương ứng. Không cần Awaitility khi `waitForIncomingEmail` đã đủ cho điều kiện test. Test phải giới hạn thời gian chờ để phát hiện lỗi thay vì treo vô hạn.

## 9. Đọc To, Cc, Reply-To và display name

Một message có thể chứa nhiều người nhận. Đọc qua Jakarta Mail:

~~~java
Address[] toAddresses = actual.getRecipients(
    Message.RecipientType.TO
);

Address[] ccAddresses = actual.getRecipients(
    Message.RecipientType.CC
);

Address[] replyToAddresses = actual.getReplyTo();
~~~

Ví dụ kiểm tra địa chỉ:

~~~java
InternetAddress to =
    (InternetAddress) toAddresses[0];

assertEquals("recipient@example.test", to.getAddress());
~~~

Nếu sender có display name:

~~~java
helper.setFrom(new InternetAddress(
    "sender@example.test",
    "Cửa hàng Ví dụ",
    "UTF-8"
));
~~~

Có thể xác nhận `getPersonal()` đã được giải mã:

~~~java
InternetAddress from =
    (InternetAddress) actual.getFrom()[0];

assertEquals("Cửa hàng Ví dụ", from.getPersonal());
~~~

Với danh sách nhiều người nhận, so sánh theo tập địa chỉ nếu thứ tự không phải yêu cầu nghiệp vụ.

### Bcc không nhất thiết xuất hiện trong MIME header

Bcc thường được gửi qua **SMTP envelope** và bị bỏ khỏi header message phát tới người nhận. Vì vậy, không phải lúc nào đọc `actual.getRecipients(Message.RecipientType.BCC)` cũng trả Bcc. Nếu cần chứng minh Bcc được SMTP server chấp nhận, hãy dùng cơ chế envelope/recipient capture của test server hoặc kiểm tra đúng mailbox đích, thay vì dựa duy nhất vào header Bcc.

## 10. Test Unicode và charset UTF-8

Subject, sender display name và body tiếng Việt rất dễ gặp lỗi encoding.

Ví dụ:

~~~java
String expectedSubject =
    "Xác nhận thanh toán – Đơn hàng #123";

String expectedBody =
    "Xin chào, hóa đơn của bạn đã được phát hành.";
~~~

Sau khi gửi và nhận lại:

~~~java
assertEquals(expectedSubject, actual.getSubject());

String content = (String) actual.getContent();
assertTrue(content.contains(expectedBody));
~~~

`MimeMessage.getSubject()` giải mã MIME encoded-word. Đừng so sánh raw Subject header với chuỗi Unicode trực tiếp: header có thể được biểu diễn dưới dạng `=?UTF-8?...?=` theo quy tắc RFC.

Cũng nên chú ý:

- SMTP thường chuẩn hóa xuống dòng thành CRLF.
- Body có thể được chuyển mã bằng quoted-printable hoặc Base64.
- Charset được khai báo trong `Content-Type`.
- Jakarta Mail `getContent()` giúp giải mã text part.
- Với newline, chỉ normalize nếu khác biệt không thuộc contract cần test.

Bài test nên so sánh **ngữ nghĩa nội dung đã giải mã** thay vì đòi raw message bytes cố định ở mọi lần chạy.

## 11. Tạo HTML email có plain-text alternative

Email HTML có thể cần một phần plain text để phù hợp client không hiển thị HTML.

~~~java
MimeMessage outgoing = sender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(outgoing, true, "UTF-8");

helper.setFrom("sender@example.test");
helper.setTo("recipient@example.test");
helper.setSubject("Hóa đơn điện tử");

helper.setText(
    "Hóa đơn của bạn đã được tạo.",
    "<html><body>"
        + "<h1>Hóa đơn</h1>"
        + "<p>Hóa đơn của bạn đã được tạo.</p>"
        + "</body></html>"
);

sender.send(outgoing);

assertTrue(smtp.waitForIncomingEmail(5_000, 1));
MimeMessage actual = smtp.getReceivedMessages()[0];
~~~

Vì dùng multipart, `actual.getContent()` có thể trả về `Multipart` thay vì String. Không viết assertion giả định top-level luôn là `text/html`.

MIME tree thường có các lớp:

~~~text
multipart/mixed hoặc multipart/related
  |
  +--> multipart/alternative
  |       |
  |       +--> text/plain
  |       +--> text/html
  |
  +--> attachment hoặc inline resource
~~~

Cấu trúc chính xác phụ thuộc helper mode và các phần đã thêm. Test nên tìm part theo loại nội dung, không phụ thuộc cố định vào index trong một cây MIME.

## 12. Helper tìm text/plain và text/html

Ví dụ hàm đệ quy duyệt MIME tree:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

static String findTextPart(
        Part part,
        String wantedMimeType) throws Exception {

    if (Part.ATTACHMENT.equalsIgnoreCase(
            part.getDisposition())) {
        return null;
    }

    if (part.isMimeType(wantedMimeType)) {
        Object content = part.getContent();
        if (content instanceof String text) {
            return text;
        }
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();

        for (int i = 0; i < multipart.getCount(); i++) {
            String text = findTextPart(
                multipart.getBodyPart(i),
                wantedMimeType
            );

            if (text != null) {
                return text;
            }
        }
    }

    return null;
}
~~~

Assertions:

~~~java
String plain = findTextPart(actual, "text/plain");
String html = findTextPart(actual, "text/html");

assertNotNull(plain);
assertNotNull(html);

assertTrue(plain.contains(
    "Hóa đơn của bạn đã được tạo."
));
assertTrue(html.contains("<h1>Hóa đơn</h1>"));
~~~

Helper trả phần đầu tiên phù hợp và đủ cho message đơn giản. Với nested `message/rfc822`, multipart alternative nhiều nhánh hoặc forwarded email, có thể cần helper trả danh sách parts và kiểm tra cấu trúc kỹ hơn.

Không khẳng định multipart boundary cụ thể hoặc thứ tự các MIME parts luôn giống nhau giữa mọi phiên bản Jakarta Mail.

## 13. Gửi attachment và kiểm tra bytes nhận được

Ví dụ attach một CSV nhỏ:

~~~java
byte[] expectedBytes =
    "id,total\nA123,250000\n".getBytes(
        StandardCharsets.UTF_8
    );

MimeMessage outgoing = sender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(outgoing, true, "UTF-8");

helper.setFrom("sender@example.test");
helper.setTo("recipient@example.test");
helper.setSubject("Báo cáo");
helper.setText("Đính kèm file báo cáo.", false);

helper.addAttachment(
    "report.csv",
    new ByteArrayResource(expectedBytes),
    "text/csv"
);

sender.send(outgoing);
assertTrue(smtp.waitForIncomingEmail(5_000, 1));

MimeMessage actual = smtp.getReceivedMessages()[0];
~~~

Helper tìm part theo filename:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

static Part findAttachment(
        Part part,
        String expectedName) throws Exception {

    if (expectedName.equals(part.getFileName())) {
        return part;
    }

    if (part.isMimeType("multipart/*")) {
        Multipart mp = (Multipart) part.getContent();

        for (int i = 0; i < mp.getCount(); i++) {
            Part found = findAttachment(
                mp.getBodyPart(i),
                expectedName
            );
            if (found != null) {
                return found;
            }
        }
    }

    return null;
}
~~~

Kiểm tra:

~~~java
Part attachment = findAttachment(actual, "report.csv");

assertNotNull(attachment);
assertTrue(attachment.isMimeType("text/csv"));

try (InputStream stream = attachment.getInputStream()) {
    byte[] receivedBytes = stream.readAllBytes();
    assertArrayEquals(expectedBytes, receivedBytes);
}
~~~

So sánh bytes phù hợp hơn ép attachment thành String đối với PDF, PNG hoặc file nhị phân. Với attachment lớn, có thể kiểm tra digest và kích thước thay vì tải toàn bộ nội dung vào memory.

Cần import `org.springframework.core.io.ByteArrayResource`, `java.nio.charset.StandardCharsets` và `java.io.InputStream` cho ví dụ trên.

## 14. Inline image với CID

Một HTML email có thể dùng Content-ID reference:

~~~java
MimeMessage outgoing = sender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(outgoing, true, "UTF-8");

helper.setFrom("sender@example.test");
helper.setTo("recipient@example.test");
helper.setSubject("Logo cửa hàng");

helper.setText(
    "<html><body>"
        + "<img src=\"cid:brandLogo\">"
        + "<p>Xin chào!</p>"
        + "</body></html>",
    true
);

helper.addInline(
    "brandLogo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

sender.send(outgoing);
~~~

Fixture `mail/logo.png` phải tồn tại trong test resources. Khi dựng message, nên đặt HTML text trước rồi thêm inline resources theo hướng dẫn của `MimeMessageHelper`.

Sau khi đọc lại:

1. Tìm `text/html` có `cid:brandLogo`.
2. Tìm MIME part có `Content-ID` tương ứng.
3. Xác nhận `Content-Type` là `image/png`.
4. Kiểm tra image bytes nếu yêu cầu.
5. Không cố định multipart boundary hay index part.

Header Content-ID có thể được đặt giữa dấu góc như `<brandLogo>`, còn HTML dùng `cid:brandLogo`. Cần normalize hình thức này nếu test so sánh ID.

## 15. Header có ý nghĩa trong integration test

Có thể kiểm tra:

~~~java
String subject = actual.getSubject();
String messageId = actual.getMessageID();
String[] contentTypes = actual.getHeader("Content-Type");
String customId =
    actual.getHeader("X-Notification-ID", null);
~~~

Nếu ứng dụng cần correlation, trước khi gửi có thể đặt custom header:

~~~java
outgoing.setHeader(
    "X-Notification-ID",
    notificationId.toString()
);
~~~

Rồi kiểm tra bên nhận:

~~~java
assertEquals(
    notificationId.toString(),
    actual.getHeader("X-Notification-ID", null)
);
~~~

Những header thường có ích:

| Header | Kiểm tra |
| --- | --- |
| `From` | Danh tính người gửi |
| `To` / `Cc` | Người nhận hiển thị |
| `Reply-To` | Địa chỉ phản hồi |
| `Subject` | Tiêu đề và encoding |
| `Content-Type` | MIME type, charset, multipart |
| `Content-Disposition` | Inline/attachment |
| `Content-ID` | Tham chiếu nội dung inline |
| `Message-ID` | Correlation của message |
| `X-Notification-ID` | ID ứng dụng tự định nghĩa |

Không cố định Message-ID, Date hoặc MIME boundary trong test nếu chúng có thể được thư viện sinh động. Chỉ assert những trường thuộc contract thực sự cần thiết.

## 16. SMTP capture không phải IMAP hoặc POP3

“Đọc lại message nhận được” có thể có hai nghĩa:

**A. Đọc trực tiếp từ SMTP capture server:**

~~~java
MimeMessage[] messages = smtp.getReceivedMessages();
~~~

Cách này chứng minh test SMTP server đã capture nội dung. Nó **không** thực thi một phiên IMAP/POP3.

**B. Đọc một mailbox qua giao thức retrieval:**

~~~text
JavaMailSender --SMTP--> Test mail server
                              |
                              v
                        Mailbox storage
                              |
                       IMAP / POP3
                              |
                              v
                         Jakarta Mail Store
~~~

Cách B cần server có bật IMAP/POP3 và mailbox user. Nó hữu ích khi ứng dụng thực sự có tính năng đọc inbox, nhưng không bắt buộc đối với test gửi SMTP.

## 17. Ví dụ gửi SMTP rồi đọc lại bằng IMAP

GreenMail có thể chạy SMTP và IMAP cùng lúc:

~~~java
ServerSetup smtpSetup = new ServerSetup(
    0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP
);

ServerSetup imapSetup = new ServerSetup(
    0, "127.0.0.1", ServerSetup.PROTOCOL_IMAP
);

GreenMail server = new GreenMail(
    new ServerSetup[] { smtpSetup, imapSetup }
);

server.start();

try {
    server.setUser(
        "reader@example.test",
        "reader",
        "secret"
    );

    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("127.0.0.1");
    sender.setPort(server.getSmtp().getPort());

    SimpleMailMessage mail = new SimpleMailMessage();
    mail.setFrom("sender@example.test");
    mail.setTo("reader@example.test");
    mail.setSubject("Kiểm thử SMTP + IMAP");
    mail.setText("Nội dung trong mailbox.");

    sender.send(mail);
    assertTrue(server.waitForIncomingEmail(5_000, 1));

    Session session = Session.getInstance(new Properties());
    Store store = session.getStore("imap");

    try {
        store.connect(
            "127.0.0.1",
            server.getImap().getPort(),
            "reader",
            "secret"
        );

        Folder inbox = store.getFolder("INBOX");

        try {
            inbox.open(Folder.READ_ONLY);

            Message[] messages = inbox.getMessages();
            assertEquals(1, messages.length);

            assertEquals(
                "Kiểm thử SMTP + IMAP",
                messages[0].getSubject()
            );
        } finally {
            if (inbox.isOpen()) {
                inbox.close(false);
            }
        }
    } finally {
        store.close();
    }
} finally {
    server.stop();
}
~~~

Ví dụ dùng các class Jakarta Mail `Session`, `Store`, `Folder`, `Message` và các class đã được import ở ví dụ trước. Đây là cách đọc **mailbox của test server**, không phải mailbox bên ngoài Internet.

Nếu test server yêu cầu SMTP AUTH, phải cấu hình credential cho SMTP client riêng; example local này tập trung vào luồng nhận rồi đọc IMAP.

### IMAP khác POP3 như thế nào?

- IMAP có folders, flags và khả năng đồng bộ mailbox.
- POP3 chủ yếu cho việc tải message từ mailbox, với mô hình folder hạn chế.
- SMTP là giao thức submit/relay email, không phải giao thức đọc inbox.

`JavaMailSender` không được thiết kế để đọc thư. Phần retrieval dùng Jakarta Mail `Store`/`Folder` cho IMAP hoặc POP3.

## 18. Kiểm thử Spring Boot context với @SpringBootTest

Các ví dụ trước tạo sender thủ công. Nếu muốn kiểm tra Spring Boot auto-configuration, dependency injection và service thật, có thể dùng `@SpringBootTest`.

Điều quan trọng là SMTP server phải chạy **trước khi Spring context lấy host/port**.

~~~java
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class SpringBootMailIntegrationTest {

    private static final GreenMail SMTP = new GreenMail(
        new ServerSetup(
            0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP
        )
    );

    static {
        SMTP.start();
    }

    @DynamicPropertySource
    static void overrideMailProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
            "spring.mail.host",
            () -> "127.0.0.1"
        );
        registry.add(
            "spring.mail.port",
            () -> SMTP.getSmtp().getPort()
        );
        registry.add(
            "spring.mail.properties.mail.smtp.auth",
            () -> "false"
        );
        registry.add(
            "spring.mail.properties.mail.smtp.starttls.enable",
            () -> "false"
        );
    }

    @Autowired
    private OrderMailService orderMailService;

    @AfterAll
    static void stopMailServer() {
        SMTP.stop();
    }

    @Test
    void applicationServiceSubmitsMail() throws Exception {
        orderMailService.sendConfirmation(
            "buyer@example.test",
            "ORDER-123"
        );

        assertTrue(SMTP.waitForIncomingEmail(5_000, 1));

        MimeMessage[] messages = SMTP.getReceivedMessages();
        assertEquals(1, messages.length);

        assertEquals(
            "Xác nhận đơn hàng ORDER-123",
            messages[0].getSubject()
        );
    }
}
~~~

`OrderMailService` là service của ứng dụng, giả định có method `sendConfirmation` và bean tương ứng. Các import Spring Test `@SpringBootTest`, `@DynamicPropertySource`, `DynamicPropertyRegistry`, `@DirtiesContext`, JUnit `@AfterAll`, `@Test`, `@Autowired` và GreenMail cần được thêm vào test source.

Static initialization bảo đảm GreenMail đã start trước khi Spring Boot resolve dynamic property. `@DirtiesContext` giúp tránh reuse Spring context đã trỏ đến server bị stop sau class. Với suite lớn, nên quản lý lifecycle bằng test extension hoặc container để giảm rủi ro static server không được dọn nếu context bootstrap thất bại.

### Không cần @SpringBootTest cho mọi test

Nếu đang test riêng transport và MIME, JUnit + GreenMail + `JavaMailSenderImpl` có thể nhanh và đơn giản hơn. Chỉ bật toàn bộ context khi cần kiểm tra Spring wiring, property binding, business service hoặc workflow.

## 19. Test profile và cấu hình tránh SMTP production

Có thể dùng profile test:

~~~yaml
# application-test.yml
spring:
  mail:
    host: 127.0.0.1
    username:
    password:
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
~~~

Port được override động từ GreenMail hoặc container. Với `@ActiveProfiles("test")`, đảm bảo test thực sự nạp đúng profile và không bị environment variable production ghi đè host hoặc credentials.

Các biện pháp an toàn:

- Không nạp secret SMTP production vào CI test.
- Chỉ dùng recipient domain thử nghiệm.
- Chặn endpoint production ở môi trường test khi cần.
- Không in MIME body/credential vào test log vô tội vạ.
- Không gửi email thật chỉ để có một integration test passing.
- Cân nhắc kiểm tra host/port runtime trước khi chạy test nếu project có nhiều config sources.

## 20. Các trường hợp test SMTP âm tính

Một SMTP integration test không chỉ có happy path. Có thể xây các kịch bản:

| Tình huống | Dấu hiệu | Assertion mong đợi |
| --- | --- | --- |
| SMTP server chưa start | Connection refused | Sender ném lỗi gửi, không có message |
| Host/port sai | Connection timeout/refused | Lỗi transport rõ ràng |
| SMTP AUTH không hợp lệ | Server từ chối AUTH | Không submit message |
| Recipient bị từ chối | RCPT TO rejection | Lỗi được phân loại theo recipient/transport |
| Message quá lớn | DATA/policy rejection | Không đánh dấu SUBMITTED |
| MIME preparation lỗi | Invalid address/attachment source | Failure được phát hiện |
| Gửi trùng cùng business event | Hai lần gọi application | Chỉ một logical notification nếu có idempotency |
| Gửi qua @Async | Caller trả trước worker | Test đợi server capture với deadline |
| Outbox retry sau SMTP tạm lỗi | First attempt fail | Đến hạn retry mới có message |
| Bcc | Header Bcc có thể bị bỏ | Kiểm tra đúng envelope/mailbox |
| Charset không đúng | Nội dung dấu Việt lỗi | Assertion subject/body fail |
| Attachment sai | Bytes/filename lệch | Assertion MIME fail |

Không phải SMTP test server nào cũng hỗ trợ tiêm lỗi tại mọi phase. Nếu muốn mô phỏng mất phản hồi cuối DATA, có thể cần một SMTP stub/proxy điều khiển protocol hoặc một server cho phép custom responses.

## 21. Khi dùng @Async hoặc @TransactionalEventListener

Một ứng dụng có thể phát event sau commit rồi gửi email bằng một listener:

~~~java
@Component
public class OrderMailListener {

    private final OrderMailService mailService;

    public OrderMailListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @Async("mailTaskExecutor")
    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onConfirmed(OrderConfirmedEvent event) {
        mailService.sendConfirmation(
            event.recipient(),
            event.orderCode()
        );
    }
}
~~~

Test cần kích hoạt một **transaction thực sự commit** thì listener AFTER_COMMIT mới chạy. Một test method có `@Transactional` mặc định rollback ở cuối sẽ không tạo after-commit event như production.

Do đó:

- Không mặc định gắn `@Transactional` cho toàn bộ test nếu đang kiểm tra AFTER_COMMIT.
- Gọi use case thực qua Spring proxy để transaction mở/commit như production.
- Đợi message bằng deadline.
- Không nhầm task được executor nhận với SMTP message đã tới server.
- Nếu dùng outbox, kiểm tra business data và outbox row cùng commit trước khi worker gửi.
- Tránh dùng sleep cố định để chờ listener.

Với outbox worker có retry, một test có thể kiểm tra cả trạng thái durable job và message GreenMail nhận, nhưng không nên phụ thuộc vào lịch scheduler production quá dài; cấu hình test timing riêng cho phép test kết thúc nhanh.

## 22. Kiểm thử số message và tránh state leakage

Nếu một test giả định chỉ có một message:

~~~java
assertEquals(1, smtp.getReceivedMessages().length);
~~~

nó chỉ có ý nghĩa khi mailbox/capture server sạch hoặc khi lọc theo correlation ID của test.

Các nguồn state leakage:

- Test trước đã gửi thư vào cùng GreenMail instance.
- Test chạy song song dùng chung server.
- Scheduler/background worker vẫn đang chạy.
- Một listener gửi thêm notification không mong muốn.
- Outbox có records cũ từ test database.
- Các test sử dụng cùng recipient và cùng subject.

Nên chọn một cách cô lập:

1. Start/stop GreenMail cho mỗi test.
2. Dùng server riêng cho mỗi test class.
3. Purge mailbox/captured messages bằng API phù hợp khi tái sử dụng server.
4. Gắn custom `X-Notification-ID` để lọc message đúng test.
5. Dùng test database sạch hoặc fixtures riêng.
6. Đảm bảo async tasks đã hoàn tất trước teardown.

Không dựa vào thứ tự test của JUnit hoặc giả định `getReceivedMessages()[0]` luôn là message đúng nếu có nhiều message phát sinh.

## 23. Correlation ID để tìm đúng message

Khi test workflow phức tạp, nên thêm ID ổn định:

~~~java
mime.setHeader(
    "X-Notification-ID",
    notificationId.toString()
);
~~~

Test có thể lọc message theo header này thay vì thứ tự:

~~~java
MimeMessage matched = null;

for (MimeMessage candidate : smtp.getReceivedMessages()) {
    String id = candidate.getHeader(
        "X-Notification-ID",
        null
    );

    if (notificationId.toString().equals(id)) {
        matched = candidate;
        break;
    }
}

assertNotNull(matched);
~~~

Không phải mọi provider production sẽ giữ nguyên custom header, nhưng trong SMTP capture test nó hữu ích khi cấu hình và test server cho phép.

Message-ID là định danh riêng của email; không nên giả định nó là provider queue ID hoặc đảm bảo SMTP deduplication. Với business idempotency, dùng notification/event ID riêng.

## 24. SMTP acceptance và delivery thực tế khác nhau

Một test nhận được message qua GreenMail chứng minh **SMTP server test đã chấp nhận và lưu message**. Nó không chứng minh:

- Recipient cuối trên Internet đã nhận email.
- Thư vào Inbox thay vì Spam.
- DKIM/SPF/DMARC được provider Internet đánh giá đạt.
- Attachment không bị downstream filter chặn.
- Người nhận đã mở hoặc đọc thư.
- SMTP provider production cho phép sender/account hiện tại.

Muốn kiểm tra những yếu tố đó, cần provider sandbox, deliverability monitoring, bounce/delivery events hoặc một quy trình kiểm thử thực tế có kiểm soát.

Không nên viết test assertion hoặc báo cáo “đã delivered” chỉ từ `JavaMailSender.send()` hay GreenMail capture. Trạng thái đúng thường là `SUBMITTED_TO_TEST_SMTP` hoặc `CAPTURED_BY_TEST_SERVER`.

## 25. Kiểm thử TLS và SMTP AUTH

Test plaintext cục bộ thường tắt AUTH/STARTTLS để tập trung vào message. Tuy nhiên, production có thể yêu cầu port 587 STARTTLS, port 465 implicit TLS hoặc OAuth2/XOAUTH2.

Có thể tạo test riêng cho:

- Server yêu cầu AUTH và client có username/password test.
- Credential sai phải tạo authentication error.
- STARTTLS required không cho gửi nếu server thiếu TLS.
- Certificate hostname/trust hợp lệ trong test environment.
- SMTP connection/read/write timeout được cấu hình rõ.
- Client chọn đúng cơ chế AUTH khi provider yêu cầu.

Không dùng TLS bypass kiểu trust-all trên production chỉ để test pass. Nếu test cần certificate tự ký, hãy dùng test trust store được quản lý riêng.

Không nên kỳ vọng GreenMail mặc định mô phỏng mọi chính sách OAuth2, quota, throttling hoặc TLS của provider thật. Những điều đó cần sandbox/contract test riêng.

## 26. Dùng Mailpit container thay thế GreenMail

Nếu đội phát triển đã dùng Docker/Testcontainers, có thể chạy một Mailpit SMTP capture container với các port SMTP và HTTP API phù hợp.

Luồng:

~~~text
@Testcontainers / Docker
          |
          v
Mailpit container
     |       |
     |       +--> HTTP API / Web UI
     |
     +--> SMTP endpoint
             ^
             |
      JavaMailSender
~~~

Các bước:

1. Start container trước Spring Boot context.
2. Đọc host và SMTP mapped port của container.
3. Override `spring.mail.host` và `spring.mail.port`.
4. Gọi application service thật để gửi.
5. Đợi captured message xuất hiện qua HTTP API.
6. Đọc JSON/raw MIME và assert subject, recipients, body.
7. Stop container và dọn dữ liệu test.

Endpoint HTTP, format JSON và cách tải raw MIME cần bám theo version Mailpit đang dùng, không hard-code một endpoint không được chứng minh. Khi test chỉ cần Java `MimeMessage` trực tiếp, GreenMail thường ít bước hơn.

## 27. Lỗi thiết kế test thường gặp

| Anti-pattern | Vấn đề | Cách làm tốt hơn |
| --- | --- | --- |
| Mock JavaMailSender rồi gọi là SMTP integration test | Không kiểm tra transport thật | Dùng SMTP server test |
| Assert lại object SimpleMailMessage trước send | Không chứng minh server nhận | Đọc MimeMessage từ server |
| Gửi tới Gmail/account thật trong CI | Flaky, leak, quota và chi phí | SMTP capture cục bộ |
| Hard-code SMTP port cho mọi test | Xung đột khi test song song | Port động |
| Không stop test server | Rò thread/socket | Lifecycle/teardown rõ |
| Sleep cố định 5 giây | Test chậm và flaky | Wait/poll có deadline |
| Đọc index 0 khi mailbox có thư khác | Assertion nhầm | Clear state/correlation ID |
| Cast top-level multipart thành String | ClassCastException | Duyệt MIME tree |
| Chỉ kiểm tra tên attachment | Không phát hiện file sai | So sánh bytes/digest |
| So sánh raw encoded Subject | Charset encoding linh hoạt | Dùng getSubject() |
| So sánh raw MIME boundary | Boundary động | Assert semantics/parts |
| Đọc Bcc từ header mà coi là bắt buộc | Bcc có thể bị loại khỏi header | Kiểm tra envelope/mailbox |
| Đánh đồng captured với delivered | Kết luận quá mức | Phân biệt submission/delivery |
| @Transactional test rollback nhưng kỳ vọng AFTER_COMMIT | Listener không chạy | Commit thật trong test workflow |
| Dùng SMTP debug log có credentials | Rò thông tin nhạy cảm | Tắt/sanitize debug |
| Không isolate async scheduler | Message ngoài dự kiến | Test scope và lifecycle |
| Trộn javax.mail với jakarta.mail | Lỗi type/dependency | Chọn version tương thích |

## 28. Quy trình triển khai trong dự án Spring

Một lộ trình thực tế:

1. **Xác định service gửi mail** cần kiểm tra, ví dụ gửi xác nhận đơn hàng.
2. **Đảm bảo sender đi qua một interface/adapter rõ ràng**; unit test có thể mock, integration test dùng real sender.
3. **Thêm GreenMail test dependency** tương thích Jakarta Mail.
4. **Start SMTP server cục bộ** trên loopback, ưu tiên port động.
5. **Cấu hình JavaMailSender** trỏ tới host/port test; không dùng credential production.
6. **Gọi use case** thay vì dựng message thủ công nếu muốn kiểm tra toàn bộ wiring.
7. **Đợi message tới server** bằng timeout hữu hạn.
8. **Đọc MimeMessage nhận được**, assert From/To/Subject/Text.
9. **Nếu HTML/multipart**, duyệt MIME tree và kiểm tra plain text/HTML.
10. **Nếu attachment/inline**, kiểm tra filename, MIME type, Content-ID và bytes.
11. **Nếu async/event**, bảo đảm transaction commit và worker đã chạy.
12. **Cô lập test state**, dọn server và các background tasks.
13. **Thêm negative cases**: AUTH failure, recipient rejection, timeout, duplicate.
14. **Dùng provider sandbox** khi cần kiểm tra cấu hình thực của provider, thay vì kỳ vọng GreenMail mô phỏng mọi đặc điểm.

## 29. Ghi nhớ

- Integration test gửi email cần **JavaMailSender thực + SMTP server test**, không chỉ mock.
- GreenMail cho phép gọi `getReceivedMessages()` để lấy `MimeMessage[]` đã được server nhận.
- Gửi qua SMTP rồi đọc từ capture server khác với đọc Inbox qua IMAP/POP3.
- Dùng port động và loopback để tránh xung đột/nhầm server thật.
- Dùng timeout/poll có deadline thay vì `Thread.sleep` cố định.
- Kiểm tra message **phía server**, không chỉ object đầu vào.
- `getSubject()` và `getContent()` giúp kiểm tra văn bản đã giải mã.
- Multipart HTML/alternative/attachment cần duyệt MIME tree.
- Với attachment, so sánh bytes hoặc digest để phát hiện file sai/cắt cụt.
- Với inline content, kiểm tra `cid:...` và Content-ID part.
- Bcc không phải lúc nào cũng nằm trong header message đã nhận.
- Trong `@SpringBootTest`, SMTP server phải chạy trước khi context resolve dynamic port.
- Một test `@Transactional` rollback mặc định có thể không kích hoạt AFTER_COMMIT listener.
- Test có async/outbox cần chờ message theo correlation ID và cô lập background tasks.
- GreenMail capture chứng minh SMTP test server nhận message, **không chứng minh email thật đã vào Inbox**.
- Test phải stop server và không dùng production credentials hoặc recipient thật.

**Cốt lõi của bài học:** hãy gửi một email qua SMTP client thật đến server test, sau đó đọc **chính MIME message mà server tiếp nhận**. Kiểm tra các phần có ý nghĩa đối với người dùng và ứng dụng—người nhận, subject, nội dung, cấu trúc MIME, attachment, encoding—thay vì chỉ kiểm tra rằng một method đã được gọi. Đó là ranh giới giúp kiểm thử tích hợp Spring Framework Mail có giá trị thực tế mà vẫn nhanh, an toàn và có thể lặp lại.
