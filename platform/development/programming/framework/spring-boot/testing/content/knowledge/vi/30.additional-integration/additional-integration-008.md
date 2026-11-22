# Email với mail server giả lập: xác nhận người nhận, nội dung và thư MIME trong Spring Boot Test

## 1. Bài toán: test gửi email thật về mặt SMTP nhưng không gửi thư ra Internet

Một ứng dụng Spring Boot thường gửi email xác nhận đăng ký, đặt lại mật khẩu, thông báo đơn hàng hoặc báo cáo có tệp đính kèm. Nếu unit test chỉ viết `verify(javaMailSender).send(...)`, ta có thể biết một phương thức Java đã được gọi, nhưng **chưa biết SMTP transport thực sự gửi gì**: địa chỉ người nhận, subject có dấu tiếng Việt, body HTML có đúng nội dung, Cc/Bcc có nhận được không, tệp đính kèm có nguyên vẹn hay không.

Ngược lại, không nên dùng tài khoản Gmail, SMTP của doanh nghiệp hoặc người nhận thật trong CI. Gửi email thật khi chạy test gây rò thông tin, spam, chi phí, rate limits và kết quả phụ thuộc mạng.

Giải pháp ở bài này: chạy một **SMTP server giả lập trên `127.0.0.1` với cổng động** bằng GreenMail. Để chính `JavaMailSender` của Spring Boot kết nối tới server ấy qua giao thức SMTP, GreenMail lưu thư vào các mailboxes sandbox; sau đó JUnit đọc những thư đã nhận và xác minh **envelope recipient**, **To/Cc**, **From**, **Subject**, **plain text/HTML MIME parts**, **tệp đính kèm**, **UTF-8** và **số lần gửi**. Không có SMTP external provider.

~~~text
Spring Boot ApplicationContext
     |
     | NotificationMailer
     | (SimpleMailMessage / MimeMessageHelper)
     v
JavaMailSender (Spring Boot mail auto-configuration)
     |
     | SMTP TCP tới 127.0.0.1:<dynamic-port>
     v
GreenMail embedded SMTP server (chỉ dùng trong test)
     |
     +--> mailbox alice@sample.test
     +--> mailbox manager@sample.test
     +--> mailbox audit@sample.test (Bcc)
              |
              v
       JUnit xác minh nội dung và recipient delivery
~~~

**Mục tiêu học tập:**
1. Hiểu `JavaMailSender`, `SimpleMailMessage`, `MimeMessageHelper`, Jakarta Mail và Spring Boot mail auto-configuration.
2. Phân biệt **unit test mock JavaMailSender** với **integration test SMTP server giả lập**: hai tầng kiểm những hợp đồng khác nhau.
3. Cấu hình **GreenMail 2.1.x** tương thích Jakarta Mail của **Spring Boot 3.3.5 / Java 17**; tránh dùng GreenMail 1.6/Javamail `javax.mail` cho code `jakarta.mail`.
4. Khởi động SMTP sandbox ở **port 0 / dynamic port**, truyền `spring.mail.port` bằng `@DynamicPropertySource` trước khi tạo Spring ApplicationContext.
5. Gửi một email plain text bằng `SimpleMailMessage`, kiểm **đúng người nhận, địa chỉ gửi, tiêu đề, UTF-8 body**.
6. Gửi thư nhiều người nhận **To, Cc và Bcc** và xác minh rằng **Bcc mailbox thực sự nhận thư**; không nhầm MIME Bcc header với SMTP envelope recipient.
7. Tạo email **multipart/alternative + attachment** bằng `MimeMessageHelper`, đọc MIME nested parts đúng thay vì cast trực tiếp `MimeMessage.getContent()` thành String.
8. Kiểm **0/1/2 emails** và đảm bảo không có thư lọt vào mailbox ngoài dự kiến.
9. Thêm các test âm tính: notification bị tắt, recipient không hợp lệ, subject có CR/LF, input không hợp lệ đều **không gửi SMTP**.
10. Giải thích giới hạn: GreenMail kiểm app giao message cho sandbox SMTP, **không** chứng minh email đã tới inbox Gmail/Outlook, SPF/DKIM/DMARC hay delivery cuối cùng.
11. Bổ sung cách kiểm lỗi SMTP, timeout, retry/idempotency, async email và dữ liệu nhạy cảm trong môi trường production.
12. Tự chạy một Gradle project độc lập có **15 JUnit Jupiter `@Test` methods**, không cần Docker và không truy cập mạng ngoài localhost.

**Ngữ cảnh cha “Tích hợp bổ sung”:** Đây là bài **kiểm thử tích hợp email**. Nó không thay thế toàn bộ module Notification/Marketing, không dựng login thật hoặc server HTTP. Điều quan trọng là phân biệt bằng chứng ở ranh giới SMTP với việc chỉ nhìn mock invocation.

**Phiên bản ví dụ:** Java 17, Spring Boot **3.3.5**, Spring Framework 6.1/Spring Mail, Jakarta Mail 2.x, GreenMail **2.1.14**, Gradle và JUnit Jupiter. GreenMail 2.1.x sử dụng **`jakarta.mail.*`** và phiên bản 2.1.14 đã có trên Maven Central. Nếu nâng Spring Boot hoặc GreenMail, đối chiếu API/dependency của version thực tế; không trộn `javax.mail.internet.MimeMessage` với `jakarta.mail.internet.MimeMessage`.

## 2. Định nghĩa đúng: send, accept, deliver và receive là những mốc khác nhau

| Mốc | Quan sát được ở đâu? | Test này có chứng minh? |
|---|---|---|
| Service gọi `JavaMailSender.send(...)` | Mockito verify hoặc code path | **Có**, nhưng đây chưa phải SMTP delivery |
| Jakarta Mail tạo MIME đúng | MIME parts/headers trong mock server | **Có** |
| Client kết nối được TCP/SMTP tới server | GreenMail nhận và lưu message | **Có**, đối với sandbox localhost |
| SMTP envelope RCPT TO đúng | GreenMail mailbox của từng recipient | **Có**, kể cả Bcc |
| Server giả lập đã accept SMTP DATA | Message hiện trong GreenMail mailbox | **Có** |
| Mail server doanh nghiệp nhận thành công | Integration với provider thật | **Không** |
| DNS MX, SPF, DKIM, DMARC đúng | DNS/provider/tool chuyên dụng | **Không** |
| Email tới inbox người nhận ngoài Internet | Provider/webhook/seed inbox | **Không** |
| Người nhận mở email, link truy cập được | Email tracking và functional end-to-end | **Không** |

Trong SMTP, thông tin gửi đi gồm **envelope** (MAIL FROM, RCPT TO) và **MIME message** (headers/body). Chúng liên quan nhưng không đồng nhất:

~~~text
Envelope:
  MAIL FROM:<no-reply@sample.test>
  RCPT TO:<alice@sample.test>
  RCPT TO:<manager@sample.test>
  RCPT TO:<audit@sample.test>

MIME headers/body:
  From: no-reply@sample.test
  To: alice@sample.test
  Cc: manager@sample.test
  Subject: Báo cáo tháng 11
  MIME-Version: 1.0
  Content-Type: multipart/mixed; ...

  (multipart/alternative plain+html)
  (attachment summary.txt)
~~~

**Bcc có ý nghĩa riêng:** Bcc recipient thường vẫn có **SMTP RCPT TO** nên mailbox nhận thư, nhưng **Bcc không nhất thiết xuất hiện trong headers của thư được phát đến những người nhận khác**. Vì vậy một test chỉ gọi `mimeMessage.getRecipients(Message.RecipientType.BCC)` có thể nhận `null` dù Bcc đã được gửi thành công. Ví dụ runnable xác minh **mailbox của Bcc trên GreenMail**, không ép một Bcc header xuất hiện hay biến mất theo cách phụ thuộc implementation.

**Không coi SMTP `250 OK` là sự bảo đảm inbox delivery**: một provider thật còn có spam filters, reputation, bounce, delayed delivery, routing và domain policies. GreenMail chủ ý làm sandbox để kiểm application-side contract và không phát thư ra bên ngoài.

## 3. Chọn công cụ: mock JavaMailSender, GreenMail hay Mailpit/MailHog?

| Cách | SMTP TCP thật? | Kiểm được | Không kiểm được |
|---|---|---|---|
| Mockito `@MockBean JavaMailSender` | **Không** | Gọi send đúng số lần, dữ liệu đối tượng xây trước khi send | Serialization MIME cuối cùng, SMTP connection, mailbox delivery |
| **GreenMail embedded** | **Có, tới localhost** | JavaMailSender auto-config, SMTP send, MIME, To/Cc/Bcc delivery, attachments | Internet deliverability, provider auth/TLS policy trọn vẹn |
| Mailpit / MailHog (container/standalone) | Có | SMTP sandbox, web UI/API inspect, CI e2e | Inbox deliverability thật |
| SMTP provider sandbox API | Có tới provider test env | Một số policy/provider integration | Không tương đương inbox cuối |
| Gửi qua SMTP production | Có | Chỉ phù hợp smoke tests được phép có guardrails | Rủi ro gửi sai, chi phí/rate limits, flaky |

**Tại sao không chỉ Mockito?** Một test kiểu:

~~~java
verify(mailSender, times(1)).send(any(MimeMessage.class));
~~~

có thể xanh khi To/Cc/Bcc bị điền sai, body HTML là nội dung cũ, hoặc file đính kèm mất bytes. Nó cũng không kiểm được Spring Boot có cấu hình đúng `spring.mail.host`, `spring.mail.port` hay không.

**Tại sao không cần Docker?** GreenMail có thể chạy **embedded trong cùng JVM**. SMTP vẫn là giao thức qua socket loopback, nhưng không cần container runtime, tải image hoặc external SMTP credentials. Đây là lựa chọn hợp lý cho integration test mail nhanh. Với pipeline cần kiểm mail server ở một process/container độc lập, Mailpit/MailHog/GreenMail standalone vẫn có giá trị.

**Tại sao phải phân biệt server giả lập và fake JavaMailSender?** Fake JavaMailSender có thể chỉ ghi lại đối tượng `MimeMessage`, bỏ qua serialization/transmission. GreenMail kết nối qua SMTP là tầng tích hợp sâu hơn; các lỗi encoding, request body và port configuration có thể xuất hiện tại đây.

## 4. Auto-configuration của Spring Boot Mail

Thêm dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
~~~

Spring Boot có thể tự cấu hình một `JavaMailSenderImpl` khi các thư viện mail phù hợp có mặt và `spring.mail.host` được đặt (trừ khi ứng dụng tự định nghĩa sender bean). Các properties thông dụng:

| Property | Ý nghĩa |
|---|---|
| `spring.mail.host` | Host SMTP; ví dụ test dùng **127.0.0.1** |
| `spring.mail.port` | SMTP port; bài test lấy **cổng động của GreenMail** |
| `spring.mail.username`, `spring.mail.password` | SMTP auth credentials khi server yêu cầu; không cần trong GreenMail test mặc định |
| `spring.mail.protocol` | Thường là `smtp` |
| `spring.mail.default-encoding` | Mặc định UTF-8 cho MIME message nếu cấu hình |
| `spring.mail.properties[mail.smtp.auth]` | Có dùng SMTP AUTH hay không |
| `spring.mail.properties[mail.smtp.starttls.enable]` | Có yêu cầu kích hoạt STARTTLS trong JavaMail không |
| `spring.mail.properties[mail.smtp.connectiontimeout]` | Timeout kết nối, milliseconds |
| `spring.mail.properties[mail.smtp.timeout]` | Timeout đọc |
| `spring.mail.properties[mail.smtp.writetimeout]` | Timeout ghi |

**Lưu ý cực kỳ quan trọng:** Một số timeouts của JavaMail có thể vô hạn nếu không cấu hình. Test nên đặt các timeouts hữu hạn để lỗi SMTP không khiến CI treo lâu. Các giá trị 3000 ms trong bài dùng cho mạng loopback; production phải cân nhắc SLO, retry và provider limits.

**STARTTLS và SMTP AUTH:** Server GreenMail trong ví dụ **không bật auth/TLS** để tập trung kiểm nội dung/recipient; điều đó **không có nghĩa nên tắt STARTTLS/auth cho SMTP production**. Thử STARTTLS/SMTPS, certificate trust và credentials cần một nhóm integration tests khác với cấu hình server SSL/auth rõ.

**Không hard-code port 3025:** `ServerSetupTest.SMTP` thông thường có test port riêng, nhưng nếu nhiều test chạy song song/Windows reserved port ranges, port cố định dễ va chạm. `ServerSetupTest.SMTP.dynamicPort()` cho server chọn port còn trống. Test lấy `GREEN_MAIL.getSmtp().getPort()` sau khi server đã start để đăng ký vào Spring Environment.

### 4.1. @DynamicPropertySource giải quyết bootstrap order

Với `@SpringBootTest`, ApplicationContext phải biết SMTP host/port **trước khi tạo JavaMailSender**. Vì port được chọn lúc khởi động GreenMail, dùng:

~~~java
@DynamicPropertySource
static void smtpProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.mail.port",
            () -> GREEN_MAIL.getSmtp().getPort());
}
~~~

Đây là snippet trong **test class có `static GreenMail GREEN_MAIL` đã start**, không phải toàn bộ source. Spring Test đăng ký supplier cho property động trong quá trình context setup; không cần sửa application.yml sản xuất hay dùng một port cố định.

**Không chờ tới `@BeforeEach` rồi mới đổi `spring.mail.port`:** Khi đó ApplicationContext và sender bean có thể đã được tạo. Trong runnable example, GreenMail được start ở static initializer **trước khi** dynamic property supplier được sử dụng; port đã có giá trị. `@AfterAll` stop server một lần khi test class hoàn tất.

**Giới hạn ApplicationContext cache:** Nếu nhiều test classes cùng tái sử dụng một Spring context chứa mail sender trỏ tới port của một GreenMail instance đã stop, lớp sau có thể gặp connection refused. Với nhiều classes, thiết kế shared lifecycle/config cache tường minh, dùng `@DirtiesContext` có chọn lọc hoặc mỗi class một isolated context. Project mẫu chỉ có **một Spring Boot integration test class** để không lẫn lifecycle.

## 5. Các khái niệm email cần kiểm

### 5.1. Plain email vs multipart MIME

**Plain:** `SimpleMailMessage` có các trường from, to, cc, bcc, subject, text. Thích hợp email văn bản thuần không attachment. Không thể tự nó diễn tả toàn bộ cấu trúc HTML/multipart hay binary attachments.

**MIME:** `JavaMailSender.createMimeMessage()` và Spring `MimeMessageHelper` dùng `jakarta.mail.internet.MimeMessage`. Có thể tạo:
- `multipart/alternative` chứa **text/plain** và **text/html**.
- `multipart/mixed` bao nhiều MIME parts, ví dụ alternative part và attachment.
- File đính kèm với `Content-Disposition: attachment` và filename.
- Nội dung/subject UTF-8, encoded headers, Content-Type/charset.

**Không so raw MIME string tuyệt đối** nếu hợp đồng không yêu cầu: JavaMail tự sinh MIME boundaries, Message-ID, encoding (Base64/quoted-printable), Date và thứ tự một số headers. Một test raw-string dễ vỡ sau update thư viện. Hãy parse `MimeMessage` và kiểm **nội dung đã decode** cùng **recipient list**.

### 5.2. To/Cc/Bcc không giống nhau

- **To**: người nhận chính, thường được hiển thị.
- **Cc**: người nhận công khai được copy; địa chỉ thường xuất hiện trong header.
- **Bcc**: người nhận copy ẩn; SMTP delivery vẫn phải tới Bcc recipient, nhưng các recipient khác không nên biết danh sách Bcc nhờ cấu trúc message họ nhận được.
- **Envelope recipient**: SMTP RCPT TO được server sử dụng để route mail. Nó là bằng chứng đáng tin hơn việc đọc một Bcc header tùy implementation.

**Test mail server giả lập cần kiểm cả hai góc:** To/Cc headers cho đúng loại người nhận, đồng thời **mỗi mailbox dự kiến** nhận đúng một bản message. Nếu test chỉ thấy `greenMail.getReceivedMessages().length == 3` mà không biết ba bản tới ai, có thể bỏ sót mail bị gửi nhầm vào một địa chỉ khác. Ví dụ dùng `GreenMail.findReceivedMessages(userPredicate,messagePredicate)` để truy vấn **riêng mailbox theo địa chỉ**.

### 5.3. Nội dung có dấu tiếng Việt và Unicode

Hãy test với strings có dấu: `"Xác nhận đơn #42"`, `"Xin chào, đơn hàng đã được ghi nhận."`, `"Báo cáo tháng 11"`. Đừng chỉ test ASCII `"hello"`; các lỗi về charset, encoded subject hoặc MIME decoding chỉ lộ ra khi có Unicode.

Trong test, `MimeMessage.getSubject()` trả **chuỗi đã decode** nếu Jakarta Mail đọc encoding; với text MIME, `Part.getContent()` trả text đã giải mã theo charset. Nếu body dùng nhiều dòng, SMTP có thể canonicalize line endings thành CRLF; assert **semantic text** hoặc chuẩn hóa line endings theo contract thay vì so từng byte raw MIME.

### 5.4. Tệp đính kèm

Kiểm ít nhất:
- Có một MIME part `Content-Disposition: attachment`.
- `getFileName()` đúng tên dự kiến, ví dụ `summary.txt`.
- Bytes khi đọc `getInputStream().readAllBytes()` **khớp hoàn toàn** với bytes fixture.
- Content-Type phù hợp nếu đó là yêu cầu hợp đồng.
- Không lẫn attachment vào `text/plain` body content khi parse nested MIME.

**Đừng chỉ assert `message.isMimeType("multipart/*")`:** Điều đó không bảo đảm attachment có đúng filename và bytes. Body HTML, plain text, attachment có thể nằm ở nhiều tầng multipart nên phải traverse đệ quy.

## 6. Dự án chạy được: Spring Boot 3.3.5 + GreenMail 2.1.14

### 6.1. Cấu trúc thư mục

~~~text
settings.gradle
build.gradle
src/main/java/demo/mail/MailDemoApplication.java
src/main/java/demo/mail/NotificationMailer.java
src/test/java/demo/mail/NotificationMailerSmtpTest.java
~~~

Không cần `application.properties` vì test class cung cấp SMTP host, timeout và sender config, còn port do `@DynamicPropertySource`. Không cần HTTP controller hoặc real database.

**settings.gradle**

~~~groovy
rootProject.name = 'spring-mail-greenmail-contract-tests'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.icegreen:greenmail:2.1.14'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Vì sao dùng `com.icegreen:greenmail` mà không `greenmail-junit5`?** Ví dụ tự quản lý `GreenMail.start()/stop()` trong một class để **chắc chắn SMTP đã start trước khi Spring Boot đọc dynamic port**. GreenMail có `greenmail-junit5`/`GreenMailExtension` để quản lý lifecycle, nhưng tích hợp extension với Spring context có bootstrap order và cache scope cần được hiểu rõ. Ta dùng **core library** và JUnit Jupiter từ starter-test để tránh có hai lifecycle managers cùng điều khiển một server.

**Tương thích:** GreenMail 2.1.14 thuộc nhánh Jakarta Mail 2.1.x, phù hợp imports `jakarta.mail.*` của Spring Boot 3.3.x. Không dùng artifact GreenMail 1.6 (`javax.mail`) trong project này. Gradle/Maven vẫn phải tải dependencies qua repository ở lần chạy đầu tiên; mock SMTP không đòi Internet, nhưng dependency resolution có thể cần kết nối repository trừ khi cache sẵn.

### 6.2. Application class

**src/main/java/demo/mail/MailDemoApplication.java**

~~~java
package demo.mail;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MailDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MailDemoApplication.class, args);
    }
}
~~~

Ứng dụng không khai báo `spring-boot-starter-web`; vì vậy Spring Boot context không cần khởi động HTTP server. Mail được gửi bởi Spring-managed service qua `JavaMailSender` auto-configured.

### 6.3. Service gửi email có validation và MIME

**src/main/java/demo/mail/NotificationMailer.java**

~~~java
package demo.mail;

import java.nio.charset.StandardCharsets;
import java.util.Objects;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailer {

    private final JavaMailSender sender;
    private final String from;

    public NotificationMailer(
            JavaMailSender sender,
            @Value("${app.mail.from:no-reply@sample.test}")
            String from) {
        this.sender = sender;
        this.from = from;
    }

    private static void requireAddress(String email) {
        if (email == null || email.isBlank()
                || email.indexOf('\r') >= 0
                || email.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(
                    "A mailbox address is required");
        }

        try {
            InternetAddress address = new InternetAddress(email, true);
            address.validate();

            if (!email.equals(address.getAddress())
                    || !email.contains("@")) {
                throw new IllegalArgumentException(
                        "Only a single mailbox address is allowed");
            }
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Invalid mailbox address", ex);
        }
    }

    private static void requireSubject(String subject) {
        if (subject == null || subject.isBlank()
                || subject.indexOf('\r') >= 0
                || subject.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(
                    "Subject must be nonblank and single-line");
        }
    }

    public void sendPlain(
            String to, String subject, String body) {

        requireAddress(to);
        requireSubject(subject);
        Objects.requireNonNull(body, "body");

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(body);

        sender.send(message);
    }

    public boolean sendIfEnabled(
            boolean enabled,
            String to,
            String subject,
            String body) {

        if (!enabled) {
            return false;
        }

        sendPlain(to, subject, body);
        return true;
    }

    public void sendSummary(
            String to,
            String cc,
            String bcc,
            String subject,
            String plainText,
            String htmlText,
            byte[] attachment) {

        requireAddress(to);
        if (cc != null && !cc.isBlank()) {
            requireAddress(cc);
        }
        if (bcc != null && !bcc.isBlank()) {
            requireAddress(bcc);
        }
        requireSubject(subject);
        Objects.requireNonNull(plainText, "plainText");
        Objects.requireNonNull(htmlText, "htmlText");
        Objects.requireNonNull(attachment, "attachment");

        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message, true, StandardCharsets.UTF_8.name());

            helper.setFrom(from);
            helper.setTo(to);

            if (cc != null && !cc.isBlank()) {
                helper.setCc(cc);
            }
            if (bcc != null && !bcc.isBlank()) {
                helper.setBcc(bcc);
            }

            helper.setSubject(subject);
            // Multipart alternative: text/plain và text/html.
            helper.setText(plainText, htmlText);

            // Multipart mixed: file được gắn độc lập với body.
            helper.addAttachment(
                    "summary.txt",
                    new ByteArrayResource(attachment),
                    "text/plain; charset=UTF-8");

            sender.send(message);
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Could not prepare MIME email", ex);
        }
    }
}
~~~

**Giải thích từng lựa chọn:**

- **JavaMailSender được inject**: dùng implementation do Spring Boot cấu hình từ `spring.mail.*`, thay vì `new Session(...)` hoặc `new JavaMailSenderImpl()` trong service. Nhờ vậy test thực hiện đúng luồng production-like qua SMTP.
- **From cố định bằng property `app.mail.from`**: tránh để caller thay sender identity tùy tiện. Test dùng email ở domain `.test`.
- **Validation địa chỉ**: `InternetAddress` với strict parsing và `.validate()` ngăn nhiều lỗi syntax/CRLF. Kiểm `email.equals(address.getAddress())` giúp không nhận input dạng display-name hoặc danh sách nhiều địa chỉ trong API chỉ cho phép một mailbox. Đây là validation **cú pháp cơ bản**, không kiểm rằng domain có MX record hoặc người dùng sở hữu mailbox.
- **Subject không cho CR/LF**: giảm header injection. Chính sách subject cho phép Unicode nhưng không cho một chuỗi nhiều dòng lẫn các headers giả.
- **sendPlain**: sử dụng `SimpleMailMessage` khi chỉ cần plain text.
- **sendIfEnabled**: là nhánh nghiệp vụ cho test **không gửi email**. Return false nếu feature disabled; không có SMTP side effect.
- **sendSummary**: dùng `MimeMessageHelper(..., true, "UTF-8")` để tạo MIME multipart; `.setText(plain,html)` tạo hai representations phù hợp; attachment là bytes và filename rõ.
- **Cc/Bcc là optional**: null hoặc blank nghĩa không có recipient đó. Các địa chỉ được cung cấp được validate trước khi tạo/gửi MIME.
- **MailPreparationException**: bao lỗi tạo message `MessagingException`, còn lỗi SMTP transport khi `sender.send(...)` thực sự thất bại có thể là `MailException` khác. Không “catch rồi nuốt” exception ở đây.
- **Không gửi tới domain thật**: `.test` là domain dành cho testing; địa chỉ tồn tại trong sandbox mailboxes chứ không được route ra Internet.

**Giới hạn của validation:** Code demo chưa có chính sách canonicalization quốc tế hóa địa chỉ, IDN/punycode, danh sách allowed domains, recipient count cap hay risk scoring. Nếu app cho phép gửi đến địa chỉ tùy ý từ user input, cần validation/authorization/business limits và bảo vệ chống spam. `InternetAddress.validate()` không xác minh inbox tồn tại; test nên tách rõ syntax validation và thật sự deliverability.

## 7. Lớp JUnit tích hợp SMTP: đọc từng mailbox và parse MIME

**src/test/java/demo/mail/NotificationMailerSmtpTest.java**

~~~java
package demo.mail;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;
import jakarta.mail.Address;
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = {
        "spring.mail.host=127.0.0.1",
        "spring.mail.protocol=smtp",
        "spring.mail.default-encoding=UTF-8",
        "spring.mail.properties.mail.smtp.auth=false",
        "spring.mail.properties.mail.smtp.starttls.enable=false",
        "spring.mail.properties.mail.smtp.connectiontimeout=3000",
        "spring.mail.properties.mail.smtp.timeout=3000",
        "spring.mail.properties.mail.smtp.writetimeout=3000",
        "app.mail.from=no-reply@sample.test"
})
class NotificationMailerSmtpTest {

    private static final String ALICE = "alice@sample.test";
    private static final String MANAGER = "manager@sample.test";
    private static final String AUDIT = "audit@sample.test";

    // Test-only SMTP server: loopback + random port.
    private static final GreenMail GREEN_MAIL =
            new GreenMail(
                    ServerSetupTest.SMTP.dynamicPort());

    static {
        GREEN_MAIL.start();
    }

    @DynamicPropertySource
    static void smtpPort(DynamicPropertyRegistry properties) {
        properties.add(
                "spring.mail.port",
                () -> GREEN_MAIL.getSmtp().getPort());
    }

    @Autowired
    NotificationMailer mailer;

    @Autowired
    JavaMailSender sender;

    @BeforeEach
    void clearMailboxes() throws Exception {
        GREEN_MAIL.purgeEmailFromAllMailboxes();
    }

    @AfterAll
    static void stopSmtpServer() {
        GREEN_MAIL.stop();
    }

    private long countMail(String mailbox) {
        return GREEN_MAIL.findReceivedMessages(
                user -> mailbox.equalsIgnoreCase(user.getEmail()),
                message -> true
        ).count();
    }

    private MimeMessage singleMail(String mailbox) {
        List<MimeMessage> messages =
                GREEN_MAIL.findReceivedMessages(
                        user -> mailbox.equalsIgnoreCase(
                                user.getEmail()),
                        message -> true
                ).toList();

        assertEquals(
                1, messages.size(),
                "Expected exactly one mail in " + mailbox);

        return messages.get(0);
    }

    private static List<String> mailboxes(Address[] addresses) {
        if (addresses == null) {
            return List.of();
        }
        return Arrays.stream(addresses)
                .map(address ->
                        ((InternetAddress) address).getAddress())
                .toList();
    }

    private static String findTextPart(
            Part part, String expectedMimeType)
            throws Exception {

        if (Part.ATTACHMENT.equalsIgnoreCase(
                part.getDisposition())) {
            return null;
        }

        if (part.isMimeType(expectedMimeType)) {
            return (String) part.getContent();
        }

        if (part.isMimeType("multipart/*")) {
            Multipart multipart = (Multipart) part.getContent();

            for (int i = 0; i < multipart.getCount(); i++) {
                String result = findTextPart(
                        multipart.getBodyPart(i), expectedMimeType);
                if (result != null) {
                    return result;
                }
            }
        }

        return null;
    }

    private static Part findAttachment(
            Part part, String filename)
            throws Exception {

        if (Part.ATTACHMENT.equalsIgnoreCase(
                part.getDisposition())
                && filename.equals(part.getFileName())) {
            return part;
        }

        if (part.isMimeType("multipart/*")) {
            Multipart multipart = (Multipart) part.getContent();

            for (int i = 0; i < multipart.getCount(); i++) {
                Part result = findAttachment(
                        multipart.getBodyPart(i), filename);
                if (result != null) {
                    return result;
                }
            }
        }

        return null;
    }

    @Test
    void plainMailHasToFromSubjectAndUtf8Body()
            throws Exception {

        mailer.sendPlain(
                ALICE,
                "Xác nhận đơn #42",
                "Xin chào, đơn hàng đã được ghi nhận.");

        MimeMessage received = singleMail(ALICE);

        assertEquals(
                List.of(ALICE),
                mailboxes(received.getRecipients(
                        Message.RecipientType.TO)));
        assertEquals(
                List.of("no-reply@sample.test"),
                mailboxes(received.getFrom()));
        assertEquals(
                "Xác nhận đơn #42",
                received.getSubject());
        assertEquals(
                "Xin chào, đơn hàng đã được ghi nhận.",
                ((String) received.getContent()).strip());
        assertTrue(received.isMimeType("text/plain"));
    }

    @Test
    void twoDifferentRecipientsDoNotLeakIntoOtherMailbox() {
        mailer.sendPlain(ALICE, "One", "Message one");
        mailer.sendPlain(MANAGER, "Two", "Message two");

        assertEquals(1L, countMail(ALICE));
        assertEquals(1L, countMail(MANAGER));
        assertEquals(0L, countMail(AUDIT));
        assertEquals(0L, countMail("stranger@sample.test"));
    }

    @Test
    void twoSendsToSameRecipientCreateTwoMessages() {
        mailer.sendPlain(ALICE, "First", "One");
        mailer.sendPlain(ALICE, "Second", "Two");

        assertEquals(2L, countMail(ALICE));
        assertEquals(0L, countMail(MANAGER));
    }

    @Test
    void disabledNotificationDoesNotSendAnyMail() {
        boolean sent = mailer.sendIfEnabled(
                false,
                ALICE,
                "Feature disabled",
                "This must not be sent");

        assertFalse(sent);
        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void enabledNotificationSendsExactlyOneMail()
            throws Exception {

        boolean sent = mailer.sendIfEnabled(
                true,
                ALICE,
                "Đã bật thông báo",
                "Chào bạn!");

        assertTrue(sent);
        assertEquals(1L, countMail(ALICE));
        assertEquals(
                "Đã bật thông báo",
                singleMail(ALICE).getSubject());
    }

    @Test
    void invalidToIsRejectedBeforeSmtp() {
        assertThrows(
                IllegalArgumentException.class,
                () -> mailer.sendPlain(
                        "not-an-email",
                        "Invalid recipient",
                        "No email should be sent"));

        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void headerInjectionInSubjectIsRejectedBeforeSmtp() {
        assertThrows(
                IllegalArgumentException.class,
                () -> mailer.sendPlain(
                        ALICE,
                        "Subject\r\nBcc: wrong@sample.test",
                        "No message"));

        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void summaryIsDeliveredToToCcAndBccMailboxes()
            throws Exception {

        byte[] content =
                "Nội dung tệp".getBytes(StandardCharsets.UTF_8);

        mailer.sendSummary(
                ALICE, MANAGER, AUDIT,
                "Báo cáo tháng 11",
                "Bản thuần văn bản",
                "<html><body><strong>Báo cáo</strong></body></html>",
                content);

        assertEquals(1L, countMail(ALICE));
        assertEquals(1L, countMail(MANAGER));
        assertEquals(1L, countMail(AUDIT));
        assertEquals(0L, countMail("stranger@sample.test"));

        MimeMessage toCopy = singleMail(ALICE);
        assertEquals(
                List.of(ALICE),
                mailboxes(toCopy.getRecipients(
                        Message.RecipientType.TO)));
        assertEquals(
                List.of(MANAGER),
                mailboxes(toCopy.getRecipients(
                        Message.RecipientType.CC)));

        // Bcc xác minh bằng DELIVERY tới mailbox,
        // KHÔNG assert Bcc header phải có trên To copy.
        assertEquals(
                "Báo cáo tháng 11", toCopy.getSubject());
    }

    @Test
    void summaryHasUtf8PlainAndHtmlAlternatives()
            throws Exception {

        mailer.sendSummary(
                ALICE, MANAGER, AUDIT,
                "Thông tin tháng 11",
                "Xin chào, nội dung tiếng Việt.",
                "<html><body><b>Xin chào, báo cáo!</b></body></html>",
                "Tệp mẫu".getBytes(StandardCharsets.UTF_8));

        MimeMessage received = singleMail(ALICE);

        String plain = findTextPart(received, "text/plain");
        String html = findTextPart(received, "text/html");

        assertNotNull(plain);
        assertNotNull(html);
        assertEquals(
                "Xin chào, nội dung tiếng Việt.",
                plain.strip());
        assertTrue(html.contains("Xin chào, báo cáo!"));
        assertTrue(received.isMimeType("multipart/*"));
    }

    @Test
    void summaryAttachmentHasNameAndIdenticalBytes()
            throws Exception {

        byte[] expected =
                "Báo cáo số 42\nHợp lệ."
                        .getBytes(StandardCharsets.UTF_8);

        mailer.sendSummary(
                ALICE, null, null,
                "Tệp báo cáo",
                "Có file đính kèm.",
                "<p>Có file đính kèm.</p>",
                expected);

        Part attachment = findAttachment(
                singleMail(ALICE), "summary.txt");

        assertNotNull(attachment);
        assertEquals("summary.txt", attachment.getFileName());
        assertArrayEquals(
                expected,
                attachment.getInputStream().readAllBytes());
    }

    @Test
    void omittedCcAndBccProduceOnlyOneMailbox()
            throws Exception {

        mailer.sendSummary(
                ALICE, null, null,
                "Chỉ To",
                "Nội dung thuần",
                "<p>Nội dung HTML</p>",
                "File".getBytes(StandardCharsets.UTF_8));

        MimeMessage received = singleMail(ALICE);

        assertEquals(
                List.of(ALICE),
                mailboxes(received.getRecipients(
                        Message.RecipientType.TO)));
        assertEquals(
                List.of(),
                mailboxes(received.getRecipients(
                        Message.RecipientType.CC)));
        assertEquals(0L, countMail(MANAGER));
        assertEquals(0L, countMail(AUDIT));
    }

    @Test
    void invalidCcIsRejectedBeforeAnyDelivery() {
        assertThrows(
                IllegalArgumentException.class,
                () -> mailer.sendSummary(
                        ALICE,
                        "invalid-cc",
                        AUDIT,
                        "Bad Cc",
                        "Plain",
                        "<p>HTML</p>",
                        "File".getBytes(StandardCharsets.UTF_8)));

        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void senderUsesDynamicLoopbackSmtpPort() {
        assertTrue(GREEN_MAIL.isRunning());

        JavaMailSenderImpl impl =
                assertInstanceOf(JavaMailSenderImpl.class, sender);

        assertEquals("127.0.0.1", impl.getHost());
        assertEquals(GREEN_MAIL.getSmtp().getPort(),
                impl.getPort());
        assertTrue(impl.getPort() > 0);
        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void emptySubjectIsRejectedWithoutSending() {
        assertThrows(
                IllegalArgumentException.class,
                () -> mailer.sendPlain(
                        ALICE,
                        "   ",
                        "No message"));

        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void nullAttachmentIsRejectedWithoutSending() {
        assertThrows(
                NullPointerException.class,
                () -> mailer.sendSummary(
                        ALICE, MANAGER, AUDIT,
                        "Missing attachment",
                        "Plain",
                        "<p>HTML</p>",
                        null));

        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }
}
~~~

**Đếm chính xác: 15 phương thức `@Test`** trong một lớp. `@BeforeEach`, `@AfterAll`, `@DynamicPropertySource` và helper methods **không** tính vào JUnit test count. Test class dùng `@SpringBootTest` để Boot tạo `JavaMailSender` thật, `GreenMail` giả SMTP server; mọi thư được gửi qua **loopback socket**, không ra Internet.

**Chú ý một chi tiết test quan trọng:** `GreenMail.findReceivedMessages(...)` lọc theo `GreenMailUser.getEmail()` (mailbox được server lưu). `getReceivedMessages()` có thể gồm một MIME copy trên **mỗi mailbox recipient**; việc kiểm số thư ở một mailbox cần dùng `countMail(mailbox)` thay vì suy từ tổng số MIME messages. Đây là lý do test To/Cc/Bcc không đơn thuần assert một `MimeMessage.getAllRecipients()` hay một aggregate count.

### 7.1. Giải thích các helpers

**`clearMailboxes()`**: gọi `purgeEmailFromAllMailboxes()` trước mỗi test để không có thư cũ. Nếu một test gửi hai thư, test kế tiếp vẫn bắt đầu với mailbox trống. Test class chạy tuần tự theo JUnit mặc định; nếu một build bật JUnit parallelism toàn cục, phải cô lập GreenMail instance/context cho mỗi test class hoặc dùng `@Execution(SAME_THREAD)` để tránh việc test đồng thời purge mail của nhau.

**`singleMail(address)`**: đòi **đúng một message** trong mailbox được chọn. Nó kết hợp kiểm call count và recipient identity. Nếu message đến nhầm recipient, helper không tìm thấy và test fail.

**`mailboxes(Address[])`**: chuyển Jakarta Mail `InternetAddress` thành string addresses để kiểm nội dung header To/Cc/From. `getRecipients(...)` có thể trả `null` khi không có header; helper chuyển thành `List.of()` để so sánh.

**`findTextPart(...)`**: đi đệ quy qua các `Multipart` lồng nhau. Nó bỏ qua part có disposition `attachment` để không nhầm file `.txt` với plain body. `MimeMessageHelper.setText(plain,html)` tạo alternative part chứa plain và HTML; `helper.addAttachment` thêm MIME part riêng. Vì MIME tree có thể là mixed → alternative → text, chỉ cast trực tiếp `received.getContent()` thành `String` sẽ sai.

**`findAttachment(...)`**: tìm part có `Content-Disposition: attachment` và filename như kỳ vọng; test đọc **bytes** qua `getInputStream()` (Jakarta Mail tự decode transfer encoding). So bytes chính xác, không dùng `.toString()` trên Java byte[].

**Không test trực tiếp RFC raw bytes** trong bài: JavaMail có thể encode subject và body tự động; ứng dụng cần hợp đồng nội dung đã decode. Với hệ thống ký S/MIME hoặc DKIM, phải có test riêng ở tầng canonicalization/signature raw bytes.

### 7.2. Nhóm test plain text và negative cases

| Test | Điều kiểm |
|---|---|
| `plainMailHasToFromSubjectAndUtf8Body` | To, From, Subject có dấu, plain body UTF-8 |
| `twoDifferentRecipientsDoNotLeakIntoOtherMailbox` | Hai recipients đúng, người không liên quan không nhận |
| `twoSendsToSameRecipientCreateTwoMessages` | Cùng recipient nhận hai lần, không gộp nhầm |
| `disabledNotificationDoesNotSendAnyMail` | Feature disabled → **0** mail |
| `enabledNotificationSendsExactlyOneMail` | Enabled → đúng một mail |
| `invalidToIsRejectedBeforeSmtp` | Invalid email syntax → exception + **0** mail |
| `headerInjectionInSubjectIsRejectedBeforeSmtp` | Subject chứa CR/LF → exception + 0 mail |
| `emptySubjectIsRejectedWithoutSending` | Subject blank → exception + 0 mail |

Các negative cases kiểm **không có SMTP side effect** sau khi validation fail. Nếu chỉ assert exception mà không kiểm mailbox count, một implementation gửi email trước rồi mới ném lỗi vẫn có thể làm test xanh giả.

**Không khẳng định một `InternetAddress` validate syntax nghĩa là domain có MX record.** GreenMail tự lưu mailboxes và không gửi tới DNS/MX. Production cần chính sách gửi email và handling bounce riêng.

### 7.3. Nhóm test MIME/recipients

| Test | Điều kiểm |
|---|---|
| `summaryIsDeliveredToToCcAndBccMailboxes` | Từng mailbox To/Cc/Bcc nhận đúng 1; headers To/Cc |
| `summaryHasUtf8PlainAndHtmlAlternatives` | Body text/plain và text/html chứa nội dung tiếng Việt |
| `summaryAttachmentHasNameAndIdenticalBytes` | File `summary.txt` có bytes nguyên vẹn |
| `omittedCcAndBccProduceOnlyOneMailbox` | Optional Cc/Bcc vắng, không phát nhầm |
| `invalidCcIsRejectedBeforeAnyDelivery` | Cc sai → 0 mail |

**Test Bcc phải kiểm nhận thực tế ở mailbox riêng.** Một Bcc header có thể bị loại khỏi thư được phát cho recipient khác, theo privacy semantics. Nếu test chỉ so `getRecipients(BCC)`, nó có thể thất bại dù application đã gửi thành công, hoặc xanh nhưng mailbox Bcc chưa nhận do vấn đề envelope routing. Mailbox test giải quyết đúng điều cần kiểm.

**Thư multipart** có thể sử dụng nhiều MIME boundaries/transfer encodings. Dùng `getContent()` và walk body parts; đừng so nguyên raw SMTP transaction giữa các lần chạy vì Message-ID/Date/boundary có thể khác.

### 7.4. Nhóm test cấu hình

`senderUsesDynamicLoopbackSmtpPort` xác minh Boot thực sự tạo **`JavaMailSenderImpl`**, host là `127.0.0.1` và port trùng cổng của GreenMail đang chạy. Nếu một test vô tình ghi `spring.mail.host=smtp.prod.example.com`, assertion này sẽ fail trước khi có gửi email; đây là một guardrail hữu ích.

**Tại sao không assert port nhất thiết khác 3025?** Random port có thể tình cờ bằng một giá trị cụ thể. Điều cần kiểm là **port thực tế do GreenMail chọn** và **port của JavaMailSender khớp nhau**, không phải random port phải khác một số tùy ý.

## 8. Chạy Gradle, kết quả kỳ vọng và bằng chứng

**Điều kiện:** Java 17, Gradle tương thích và khả năng tải Maven dependencies ở lần đầu nếu cache chưa có. Không cần Docker, PostgreSQL, Mailpit, Gmail/Outlook credentials hoặc public SMTP network. Nếu firewall địa phương chặn TCP loopback, test báo lỗi connection ngay; không mở SMTP public.

Nếu project có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu chỉ copy các source files và `build.gradle` mà **chưa có Gradle Wrapper scripts/JAR**, `./gradlew` chưa tồn tại. Dùng Gradle phù hợp để tạo wrapper hoặc chạy:

~~~bash
gradle test
~~~

Chạy riêng class:

~~~bash
./gradlew test --tests demo.mail.NotificationMailerSmtpTest
~~~

Báo cáo Gradle thông thường ở:

~~~text
build/reports/tests/test/index.html
~~~

**Kết quả thiết kế dự kiến:** **15 JUnit Jupiter tests** được phát hiện và được thiết kế PASS khi môi trường Gradle/Java/socket hoạt động đúng. Không có `@Disabled` hoặc mock “always succeeds” trong project. Đó là **expected behavior từ source và API**, không phải lời tuyên bố Gradle đã được thực thi trong môi trường của người đọc.

**Các kết quả có thể kiểm thực tế:**
- Plain mail: Alice mailbox có đúng một thư; From/To/Subject/Body đọc ra đúng Unicode.
- Two recipients: Alice và Manager mỗi người một thư; Audit và stranger không có thư.
- Disable: không có mail trong bất cứ mailbox nào.
- Summary: To/Cc/Bcc mỗi mailbox nhận một bản; headers To/Cc đúng; subject UTF-8.
- HTML: MIME alternatives chứa cả text/plain và text/html.
- Attachment: filename `summary.txt`, bytes đúng.
- Invalid inputs: exception xảy ra **trước** `sender.send`; GreenMail không nhận email.
- Dynamic SMTP: `JavaMailSenderImpl.getPort()` đúng GreenMail SMTP port thực tế.

**Lưu ý về thời điểm:** `JavaMailSender.send` ở đây là lời gọi đồng bộ, nên khi phương thức gửi trả về thành công, message thường đã được SMTP sandbox chấp nhận và lưu. Với một `@Async` mail service, cần chờ `CompletableFuture`/event hoặc GreenMail `waitForIncomingEmail(...)` với timeout, không assert ngay sau submit mà tưởng async mail đã đến.

## 9. Chú ý về UTF-8, HTML và tệp đính kèm

### 9.1. Subject MIME encoded-word

Khi subject chứa ký tự ngoài ASCII, Jakarta Mail có thể serialize header dưới dạng RFC 2047 encoded-word, ví dụ chuỗi raw bắt đầu bằng `=?UTF-8?...?=`. Đây là **cơ chế truyền chuẩn**; test nên gọi `MimeMessage.getSubject()` và so **giá trị đã decode**, không so raw bytes của Subject.

Với email body, `MimeMessage.getContent()` có thể trả `String` hoặc `Multipart` tùy Content-Type. Khi plain email thì nội dung thường là String; khi MIME mixed/alternative thì phải traverse Multipart. Cùng một logical string có thể được truyền bằng quoted-printable hoặc base64; MIME parser sẽ decode về nội dung để test so sánh.

### 9.2. HTML escaping là một hợp đồng riêng

Đoạn code:

~~~java
String html = "<p>Xin chào, <strong>Lan</strong>!</p>";
mailer.sendSummary(
        "alice@sample.test",
        null,
        null,
        "Thông báo HTML",
        "Xin chào, Lan!",
        html,
        "tệp".getBytes(StandardCharsets.UTF_8));
~~~

Đây là **snippet phụ trợ** dùng service có trong ví dụ. Nếu HTML được render từ template Thymeleaf/Freemarker hoặc nối dữ liệu user, cần bảo đảm **escape HTML đúng**, không để người dùng chèn script/link độc hại. Thư HTML còn bị email clients lọc nội dung, giới hạn CSS, external images; test GreenMail chỉ thấy content mà application gửi, **không chứng minh UI hiển thị giống Gmail/Outlook**.

Đối với link xác thực/đổi mật khẩu, kiểm:
- Scheme HTTPS, host allowlist, path đúng, token không log.
- Expiry và one-time use thuộc nghiệp vụ authentication, test riêng.
- Không đưa token thật hoặc thông tin nhạy cảm vào fixture.
- Có plain-text alternative nếu hợp đồng/khả năng truy cập yêu cầu.
- Template locale `vi-VN`, placeholder values và subject đúng.

### 9.3. File attachments và Content-Disposition

MIME attachment có filename, media type, transfer encoding và body bytes. Với file có dung lượng lớn, không nên load toàn bộ vào `byte[]` nếu production có memory constraints; dùng `InputStreamSource`/`FileSystemResource` phù hợp, test dòng dữ liệu và limit. Trong project demo, ByteArrayResource chứa vài bytes để test deterministic và tránh filesystem path.

**Đừng lưu snapshot MIME của một thư thật có PII.** Dùng nội dung giả như `"Báo cáo số 42"` và domain `.test`. Nếu attachment là PDF/CSV có dữ liệu nghiệp vụ, test cả nội dung file bằng parser chuyên dụng hoặc so bytes của fixture đã biết. Không khẳng định file hợp lệ chỉ vì filename `.pdf` đúng: phần bytes cũng phải đúng định dạng.

### 9.4. Bcc privacy

Bcc không nên bị công khai trong To/Cc headers của người nhận khác. Cách xử lý header Bcc cụ thể tùy thư viện và RFC-compliant transport: ứng dụng có thể gửi một MIME variant cho từng nhóm recipient và loại header khi chuyển. Vì vậy test:
1. **Bcc mailbox đã nhận** (envelope delivery).
2. **To/Cc headers có đúng addresses**.
3. Không vô tình đưa địa chỉ Bcc vào **body/template** hay các headers công khai khác (có thể kiểm raw headers hoặc text content khi policy yêu cầu).
4. Không yêu cầu `getRecipients(BCC)` phải có giá trị trong copy tới To.

Trong môi trường doanh nghiệp, email có nhiều external recipients còn cần giới hạn gửi nhầm (data-loss prevention, approved domains, audit). GreenMail test là một lớp bảo vệ, không thay chính sách bảo mật dữ liệu.

## 10. Test không gửi nhầm email và không đụng SMTP thật

### 10.1. Cấu hình cổng/host cách ly

Trong bài, `spring.mail.host=127.0.0.1` và `spring.mail.port` lấy từ GreenMail, không đọc `SMTP_HOST`/`SMTP_PASSWORD` production. Toàn bộ addresses kết thúc bằng `.test`. Một guard test kiểm port/host khớp GreenMail; đây là bằng chứng tích hợp thật vào sandbox.

Để tăng an toàn CI, có thể:
- Đặt profile test với một bean/config bắt buộc local SMTP host.
- Chặn egress network ở test runner/container, trừ loopback.
- Dùng credentials giả (hoặc không auth) riêng cho sandbox.
- Không mount production secrets vào test environment.
- Không dùng real customer emails làm test recipients.
- Tách smoke test provider thật vào pipeline riêng, có allowlist và phê duyệt.

**Không chạy GreenMail trên địa chỉ `0.0.0.0` nếu không cần thiết.** Bind loopback để server giả chỉ phục vụ test process/máy cục bộ. Dynamic port giúp giảm collision; không cố định 25/465/587 trong môi trường developer.

### 10.2. Nếu test cần mail bị từ chối

Ví dụ runnable chủ yếu dùng **validation fail trước SMTP**. Muốn kiểm transport errors:
- Cho `JavaMailSenderImpl` kết nối tới một SMTP server giả lập **được cấu hình chủ động trả mã lỗi** như 421, 450, 550 hoặc từ chối một recipient.
- Assert Spring `MailException` phù hợp, **không chỉ assert log có lỗi**.
- Kiểm retry classifier: 4xx transient có thể retry theo policy, 5xx permanent không nên retry vô hạn.
- Chờ và kiểm không có mail được chấp nhận ở mailbox khi SMTP reject trước DATA.
- Đảm bảo mock server được start/stop trong test scope và không làm lệch Spring context cache.

**Không đề xuất test bằng cách trỏ tới SMTP production với mật khẩu sai** để kích hoạt lỗi: đó vẫn là external dependency nguy hiểm và làm CI không ổn định.

### 10.3. Retry và idempotency trong email

Mail server có thể **chấp nhận SMTP DATA** nhưng network đứt trước khi application nhận response. Nếu application retry ngay, người nhận có thể nhận **hai thư**. Bởi vậy:
- Đừng đồng nhất `JavaMailSender.send()` ném exception với “mail chắc chắn chưa được accept”.
- Gắn business notification ID/idempotency key trong outbox/DB nếu quy trình gửi phải được track.
- Dùng durable outbox worker để khắc phục giao dịch nghiệp vụ commit nhưng email chưa được gửi.
- Có state: pending → sending → accepted/failed, retry budget, backoff, logging/correlation.
- Không tạo email xác thực/đổi mật khẩu nhiều token tùy tiện khi retry.
- `Message-ID` có ích cho tracing nhưng không đảm bảo mọi SMTP client/provider deduplicate theo nó.
- Một bài test có GreenMail có thể kiểm **hai lần send tạo hai messages**, như test `twoSendsToSameRecipientCreateTwoMessages`. Từ đó xác định nghiệp vụ cần dedup ở đâu.

**Đây là giới hạn quan trọng của “exactly-once email”:** Không có giao dịch phân tán mặc định giữa database ứng dụng và provider SMTP. Thực tế thường hướng tới **at-least-once attempt + dedup theo business notification** hoặc reconcile với provider API, trong giới hạn bên ngoài.

## 11. Email bất đồng bộ và test timing

Nếu production gửi email bằng `@Async`:

~~~java
@Async
public CompletableFuture<Void> sendLater(
        String recipient, String subject, String body) {

    mailer.sendPlain(recipient, subject, body);
    return CompletableFuture.completedFuture(null);
}
~~~

Đây là **snippet**, cần `@EnableAsync` và phải gọi qua Spring proxy; nó không nằm trong project runnable ở trên. Đối với async test, đừng gọi `mailer.sendLater(...)` rồi assert mailbox count ngay lập tức vì worker thread có thể chưa chạy.

Hai chiến lược hợp lệ:

1. Dùng **`CompletableFuture.get(timeout)`** chờ completion và exception, rồi đọc GreenMail mailboxes.
2. Nếu không có Future mà có worker độc lập, dùng **`greenMail.waitForIncomingEmail(timeoutMillis, expectedCount)`** hoặc Awaitility với deadline để chờ tín hiệu mail đến.

~~~java
CompletableFuture<Void> sent = asyncMailer.sendLater(
        "alice@sample.test", "Đã xử lý", "Xin chào");

sent.get(5, TimeUnit.SECONDS);

assertEquals(1L, countMail("alice@sample.test"));
~~~

Đây là snippet minh họa, `asyncMailer`/`countMail` phải thuộc test thích hợp và imports cần đầy đủ. `Future.get` giúp thấy exception trong worker; khi sử dụng `@Async void` mà không có Future, lỗi có thể chỉ đến `AsyncUncaughtExceptionHandler` hoặc logs nên test khó chứng minh.

**Lưu ý transaction:** Nếu một `@Transactional` test thay async executor bằng SyncTaskExecutor, email có thể được gửi trong test thread/transaction còn mở; với worker thật ở thread khác, context/transaction không tự được truyền. Một SMTP message đã accept **không thể rollback bằng JDBC transaction**. Tránh gửi email trước khi business transaction commit; cân nhắc transactional outbox hoặc event after-commit đã có failure recovery.

## 12. Xác minh template, locale và link trong email

SMTP sandbox giúp kiểm bytes/headers cuối cùng, nhưng một sản phẩm thực tế còn cần kiểm business template:

| Thuộc tính | Assertion nên có | Rủi ro |
|---|---|---|
| To address | Khớp normalized account contact/email được ủy quyền | Gửi nhầm người |
| Cc/Bcc | Đúng role/opt-in, không leak | Lộ danh sách nhận |
| Subject | Locale, variables, không CRLF injection | Thư khó hiểu hoặc header injection |
| Plain text | Có nội dung bắt buộc, placeholder được thay | Khả năng truy cập/clients chặn HTML |
| HTML | Nội dung, escape, link scheme/domain | Injection/phishing |
| Attachment | Filename, MIME type, bytes, size cap | Dữ liệu sai hoặc rò nhạy cảm |
| Number of sends | 0/1/N theo sự kiện | Spam, duplicates |
| From/Reply-To | Sender được phép, reply routing hợp lệ | Impersonation/feedback mất |
| Unsubscribe/consent | Chính sách theo loại email | Vi phạm opt-out/quyền riêng tư |
| Trace/correlation | Message/event ID, logs không lộ token | Không điều tra được gửi lỗi |

Nếu email xác nhận đặt hàng cần một số tiền, hãy format locale/currency đúng và kiểm text **đã render**; không assert mỗi lần `templateEngine.process(...)` được gọi là đủ. Với các link chứa one-time tokens, test bằng tokens giả và kiểm URL encoding; không lưu snapshot real tokens.

**Template unit test và SMTP integration test bổ trợ nhau:** Một test template có thể kiểm escaping/layout logic nhanh, còn GreenMail test xác nhận cuối cùng `JavaMailSender` gửi đúng header/body/attachment tới recipients. Nếu email có điều kiện “chỉ gửi sau payment success”, cũng cần test negative case không gửi khi payment thất bại.

## 13. Những lỗi hay gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách sửa/test |
|---|---|---|
| `NoSuchBeanDefinitionException: JavaMailSender` | Thiếu starter-mail hoặc `spring.mail.host` | Thêm dependency, cấu hình host trong test |
| `Connection refused: localhost:3025` | GreenMail chưa start/port cứng sai | Dynamic port từ GreenMail, @DynamicPropertySource |
| Test cố gửi ra SMTP công ty | `spring.mail.host` bị override bởi profile/env | Guard host/port, network egress policy |
| `javax.mail` không compile với Boot 3.3 | Dùng GreenMail nhánh 1.6 hoặc imports cũ | Jakarta Mail + GreenMail 2.1.x |
| Message có subject đúng nhưng sai To | Chỉ kiểm subject, không đọc mailbox | Verify mailbox theo recipient |
| Bcc không thấy trong MIME headers | SMTP transport có thể loại Bcc header | Kiểm Bcc mailbox được deliver |
| Tổng messages=3 nhưng có recipient sai | Aggregate count không kiểm identity | countMail(mailbox), negative mailbox |
| `getContent()` cast String thất bại | Multipart HTML/attachment, không phải text đơn | Parse Multipart nested |
| HTML có nhưng plain text thiếu | Chỉ gọi helper.setText(html,true) | Dùng helper.setText(plain, html) |
| Unicode hiển thị lỗi | Charset/encoding MIME sai hoặc test raw bytes | UTF-8 config, decoded getSubject/getContent |
| Attachment tồn tại nhưng sai bytes | Chỉ kiểm tên file | `getInputStream().readAllBytes()`, assertArrayEquals |
| Test bị ảnh hưởng mail của test trước | Không purge mailbox | @BeforeEach purge, test isolation |
| @DynamicPropertySource không thấy đúng port | Server start sau Spring context | Start GreenMail trước dynamic supplier |
| Test @Async đôi lúc thấy mailbox rỗng | Assert trước khi worker hoàn thành | Future.get/GreenMail wait with timeout |
| SMTP timeout khiến CI treo | JavaMail timeouts vô hạn | Cấu hình connection/read/write timeout |
| Mail send exception bị nuốt | `catch MailException` chỉ log rồi return | Retry/failure policy rõ; tests assert lỗi |
| 550 bị retry liên tục | Không phân loại lỗi permanent | Bounded retries, DLQ/failed notification record |
| Mail gửi 2 lần sau retry | Provider accept rồi connection mất | Idempotency/outbox/reconciliation |
| Test pass nhưng Gmail không nhận | GreenMail không kiểm external delivery | Provider sandbox/webhook/smoke test riêng |
| Email lộ PII trong logs | Log full MimeMessage/token | Redaction; dummy recipients/data |
| Test mở SMTP trên 0.0.0.0 | Bind public interfaces | Bind 127.0.0.1 trong test |
| Cc/Bcc nhận nhầm HTML content | Template/personalization dùng chung sai | Verify body mỗi mailbox theo policy |
| Spring context cache trỏ port đã stop | GreenMail lifecycle theo class nhưng context còn cache | Align scopes, isolate contexts |
| STARTTLS production fail, GreenMail pass | Sandbox tắt TLS/auth | Test TLS/auth/cert riêng |
| Mailpit container cần Docker nhưng CI không có | Dùng external mock server | Embedded GreenMail thay thế khi phù hợp |

### 13.1. Quy trình debug từng bước

1. Kiểm test **thực sự có `spring-boot-starter-mail`** và bean `JavaMailSender`.
2. Kiểm `spring.mail.host` là loopback; `spring.mail.port` phải bằng `GREEN_MAIL.getSmtp().getPort()`.
3. Kiểm GreenMail `isRunning()` trước send.
4. Kiểm sender đã bật hay tắt SMTP auth/TLS phù hợp với sandbox.
5. Nếu `JavaMailSender.send` thất bại, đọc exception chain và protocol status code; không xoá assertions để “chạy xanh”.
6. Nếu send thành công nhưng không thấy mail, kiểm đúng mailbox user chứ không chỉ aggregate count.
7. Nếu body plain/HTML lỗi, parse MIME multipart theo cây, không ép `getContent()` thành String.
8. Nếu Bcc không có header, kiểm delivery tại Bcc mailbox.
9. Nếu nội dung Unicode sai, kiểm Jakarta Mail version và MIME charset.
10. Nếu test fail khi chạy suite, kiểm purge mail trước method, JUnit parallelism và Spring context cache.
11. Nếu async, chờ Future/GreenMail wait; không `Thread.sleep(1000)` cố định.
12. Nếu tests yêu cầu điều kiện business, assert **0 mail** trong những nhánh không được gửi.
13. Kiểm không gửi tới real recipient/domain, không có secrets production trong config.
14. Nếu production dùng provider thật, thêm integration tests riêng cho auth, TLS, bounce và provider API.
15. Báo cáo kết quả chỉ là **SMTP sandbox accepted**, không là “đã gửi đến inbox thực”.

## 14. Checklist review trước khi merge code email

1. **Recipient correctness:** To đúng identity, Cc/Bcc đúng scope; xét trường hợp 0/1/nhiều recipients.
2. **Privacy:** Không lộ Bcc/PII trong headers công khai, body hoặc logs.
3. **Content:** Subject, plain text, HTML, locale, placeholders được kiểm sau render.
4. **Attachment:** Filename, media type, bytes, kích thước và retention hợp lệ.
5. **Transport:** Host/port/test mode thật sự trỏ sandbox, không real SMTP.
6. **Spring bean:** JavaMailSender auto-configured hoặc custom sender có kiểm chứng wiring.
7. **Timeout:** SMTP connect/read/write timeouts hữu hạn.
8. **Negative paths:** Disabled/validation failures không gửi email.
9. **Count:** Xác minh đúng 0/1/N mails và những mailbox ngoài dự kiến rỗng.
10. **Async:** Chờ completion, quan sát exceptions; không dùng sleep như tín hiệu.
11. **Retry:** Budget, backoff, idempotency, outbox và trạng thái accepted/failed rõ.
12. **Failure injection:** SMTP 4xx/5xx, connection reset, provider outage được test ở tầng phù hợp.
13. **Security:** Không chứa real tokens, PII, SMTP passwords trong test fixtures/logs.
14. **Lifecycle:** Khởi động server trước Spring context, purge giữa tests, stop sau lớp.
15. **Compatibility:** Java 17, Spring Boot 3.3.5, Jakarta Mail, GreenMail 2.1.x khớp API.
16. **Claims:** Không nhầm sandbox acceptance với external delivery/inbox placement.

## 15. Bài tập mở rộng

**Bài 1 — Kiểm sai To:** Đổi `sendPlain(ALICE,...)` thành `sendPlain(MANAGER,...)`. Test nào báo sai? Nếu chỉ `getReceivedMessages()[0].getSubject()`, vì sao có thể bỏ sót?

**Bài 2 — Hai người nhận:** Gửi hai thư đến Alice và Manager; xác minh mỗi mailbox có 1 thư và Audit không nhận. Nếu tất cả đều vào Alice, test nào phát hiện?

**Bài 3 — Cc/Bcc:** Bỏ `helper.setBcc(bcc)` trong service. Vì sao test phải kiểm Bcc mailbox thay vì chỉ tìm Bcc header?

**Bài 4 — Unicode:** Thay title bằng `"Thông báo: Đã thanh toán – tháng 11"` và body có dấu tiếng Việt. Kiểm subject/body đã decode; đừng so raw RFC 2047 encoded header.

**Bài 5 — Multipart:** Bỏ `.setText(plain,html)` và chỉ gửi HTML. Khi MIME parser tìm text/plain, kết quả nào? Test nào cần fail?

**Bài 6 — Attachment:** Thay nội dung bytes nhưng giữ filename `summary.txt`. Vì sao test chỉ kiểm file name vẫn xanh giả?

**Bài 7 — Validation:** Gửi subject có CRLF hoặc địa chỉ không hợp lệ. Assert **exception và 0 mail**, không chỉ exception.

**Bài 8 — Unsubscribe:** Giả lập email marketing bị opt-out. Bảo đảm `sendIfEnabled(false)` không có SMTP effect; thêm audit về lý do skip.

**Bài 9 — Dynamic port:** Thử hai test suites chạy đồng thời trên máy CI. Vì sao dùng random port an toàn hơn 3025, nhưng vẫn cần cách ly ApplicationContext cache/cleanup?

**Bài 10 — SMTP auth:** Cấu hình GreenMail có user/password và bật AUTH. Test thành công với credentials giả và thất bại với mật khẩu sai. Không làm test trên SMTP thật.

**Bài 11 — TLS:** Thêm SMTPS/STARTTLS sandbox, kiểm kết nối TLS và certificate policy riêng. Vì sao không dùng TLS disabled test để tuyên bố security transport production ổn?

**Bài 12 — Async:** Bọc `sendPlain` trong `@Async` trả `CompletableFuture`. Test chờ completion và đảm bảo exactly 1 mail, thêm case worker exception.

**Bài 13 — Retry:** Mô phỏng SMTP 451 temporary failure một lần rồi 250. Xác minh retry policy không gửi hai thư trong trường hợp server đã accept DATA trước network reset.

**Bài 14 — Outbox:** Ghi notification event vào database trong cùng transaction nghiệp vụ, relay gửi email sau commit; test crash trước/giữa send để kiểm idempotency.

**Bài 15 — Template engine:** Dùng Thymeleaf/Freemarker render thông báo theo locale, chèn URL/token giả; kiểm HTML escaping và link host allowlist trong email đã được GreenMail nhận.

**Bài 16 — Attachment type:** Thay txt bằng PDF/CSV; kiểm content-type, filename, bytes và không lộ tài liệu của người dùng khác.

**Bài 17 — Provider callbacks:** Nếu provider gửi event delivered/bounced/complained, kiểm webhook signature, idempotency và state machine riêng. GreenMail embedded không mô phỏng inbox/complaint lifecycle.

**Bài 18 — QA checklist:** Viết một bảng requirement gồm To/Cc/Bcc, subject, locale, template body, attachment, no-send branches, SMTP failure và retry; ánh xạ từng yêu cầu tới một test name cụ thể.

## 16. Tài liệu chính thức

- [Spring Boot 3.3 — Sending Email](https://docs.spring.io/spring-boot/3.3/reference/io/email.html): `JavaMailSender`, `spring.mail.*`, timeout và auto-configuration.
- [Spring Framework 6.1 — Email](https://docs.spring.io/spring-framework/reference/integration/email.html): `MailSender`, `JavaMailSender`, `SimpleMailMessage`, `MimeMessageHelper`.
- [Spring Framework — MimeMessageHelper API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/mail/javamail/MimeMessageHelper.html): To/Cc/Bcc, multipart, text/plain/text/html, attachments, encoding.
- [Spring Framework — JavaMailSenderImpl API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/mail/javamail/JavaMailSenderImpl.html): host, port, protocol, send.
- [Spring Test — @DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): dynamic properties trước ApplicationContext creation.
- [GreenMail Official Documentation](https://greenmail-mail-test.github.io/greenmail/): embedded SMTP, Jakarta Mail compatibility, dynamic port, JUnit test examples.
- [GreenMail 2.1 — GreenMail API](https://javadoc.io/static/com.icegreen/greenmail/2.1.0/com/icegreen/greenmail/util/GreenMail.html): received messages, findReceivedMessages, purge, start/stop.
- [GreenMail 2.1 — ServerSetup API](https://javadoc.io/static/com.icegreen/greenmail/2.1.0/com/icegreen/greenmail/util/ServerSetup.html): `dynamicPort`, `getPort`, binding.
- [Jakarta Mail — Message API](https://jakarta.ee/specifications/mail/2.1/apidocs/jakarta.mail/jakarta/mail/message): `RecipientType`, `getRecipients`, `getFrom`, MIME.
- [Jakarta Mail — Part API](https://jakarta.ee/specifications/mail/2.1/apidocs/jakarta.mail/jakarta/mail/part): multipart/body parts, attachment, content.
- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.4/user-guide/): lifecycle annotations, assertions, Gradle/JUnit Platform.
- [IETF RFC 5321 — SMTP](https://www.rfc-editor.org/rfc/rfc5321): SMTP envelope và delivery.
- [IETF RFC 5322 — Internet Message Format](https://www.rfc-editor.org/rfc/rfc5322): message headers To/Cc/Bcc.
- [IETF RFC 2045/2046 — MIME](https://www.rfc-editor.org/rfc/rfc2045): content types, transfer encoding, multipart semantics.

**Ghi nhớ:** Kiểm thử email tốt phải trả lời **“đã gửi gì, tới mailbox nào, bao nhiêu bản, với bytes/nội dung nào?”**. `JavaMailSender` + **GreenMail SMTP sandbox** cho bằng chứng mạnh hơn mock method invocation: test có thể xác minh **To/Cc/Bcc envelope delivery, subject và body Unicode, multipart HTML/plain, attachment và zero-send scenarios**. Tuy nhiên GreenMail chỉ xác nhận hành vi tới **SMTP server giả lập trong test**, không phải delivery tới Gmail/Outlook. Luôn dùng localhost + dynamic port, cleanup mailboxes, timeouts, và thiết kế riêng các kiểm thử provider auth/TLS, bounce, retry/idempotency khi hệ thống cần reliability thật.
