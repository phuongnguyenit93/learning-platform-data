# Mail server giả lập hoặc SMTP test container

## 1. Vì sao cần mail server giả lập khi kiểm thử tích hợp?

Trong **Spring Framework Mail**, lập trình viên thường gọi `JavaMailSender.send(...)` để nộp email cho SMTP server. Một unit test có thể mock `JavaMailSender` và xác nhận method được gọi, nhưng điều đó **chưa chứng minh ứng dụng tạo được MIME message hợp lệ, kết nối SMTP đúng host/port hoặc truyền nội dung tới một SMTP server**.

Kiểm thử tích hợp khắc phục khoảng trống này bằng cách cho ứng dụng giao tiếp với một **mail server thử nghiệm** qua giao thức SMTP thật, nhưng **không chuyển email ra Internet tới người nhận thực**.

~~~text
                  Application Under Test
                            |
                            | Spring Mail / JavaMailSender
                            | SMTP protocol
                            v
                Fake SMTP server / container
                            |
                   +--------+---------+
                   |                  |
                   v                  v
              Captured MIME     Test API / UI / IMAP
                   |                  |
                   +--------+---------+
                            v
                    Test assertions
            recipient, subject, body, headers,
                   HTML, text, attachment
~~~

Một SMTP server giả lập có thể giúp phát hiện:

- `spring.mail.host` hoặc `spring.mail.port` trỏ sai môi trường.
- SMTP client không kết nối được hoặc timeout.
- Địa chỉ người gửi/người nhận, header và subject được đặt sai.
- Email tiếng Việt bị lỗi charset hoặc encoding.
- HTML/plain text không đúng cấu trúc MIME.
- File đính kèm bị thiếu, sai tên hoặc sai content type.
- `@Async`/worker/outbox không thật sự gửi email.
- Một sự kiện nghiệp vụ vô tình tạo nhiều email giống nhau.

Điểm cần giới hạn rõ: **SMTP server thử nghiệm xác nhận ứng dụng gửi tới server đó, không chứng minh khả năng giao vào inbox thật**. Test này không thay thế việc kiểm tra DNS/SPF/DKIM/DMARC, bounce, spam filtering, reputation hoặc quota provider production.

## 2. Phân tầng kiểm thử trong một ứng dụng gửi email

Không nên dùng SMTP container cho mọi test. Các cấp kiểm thử phục vụ mục tiêu khác nhau:

| Cấp kiểm thử | Thay thế/thành phần thật | Kiểm tra được | Không kiểm tra được |
| --- | --- | --- | --- |
| Unit test với mock `JavaMailSender` | Không mở SMTP | Business flow, dữ liệu truyền vào, số lần gọi | Kết nối SMTP, MIME serialization thực |
| Unit test xây `MimeMessage` | Jakarta Mail object thật; sender mock/fake | Header, MIME tree, text/HTML/attachment | SMTP handshake và truyền qua mạng |
| Integration test với fake SMTP | Spring Mail + SMTP protocol thật; server giữ thư | Kết nối, acceptance, nội dung thu được | Giao thư qua Internet |
| Integration test với SMTP container | Server thử nghiệm chạy trong Docker/Testcontainers | Tính lặp lại, network boundary, cấu hình runtime | Các chính sách đặc thù của provider thật |
| Staging với provider được phép | Mail provider thực và địa chỉ kiểm thử | Credential, TLS, domain, quota/API trong phạm vi staging | Không đại diện tuyệt đối cho mọi mailbox/inbox |

**Lời khuyên:** Hãy dùng mock để kiểm tra các nhánh nghiệp vụ thuần và dùng một số bài integration test với fake SMTP để xác nhận toàn bộ đường đi từ `JavaMailSender` tới thư được giữ lại trên server giả lập.

### 2.1. Mock khác fake SMTP thế nào?

Ví dụ unit test:

~~~java
@Test
void requestsMailSend() {
    JavaMailSender sender = mock(JavaMailSender.class);
    NotificationService service = new NotificationService(sender);

    service.notifyOrderConfirmed("order-123");

    verify(sender).send(any(SimpleMailMessage.class));
}
~~~

Nếu `NotificationService` chỉ tạo `SimpleMailMessage`, test này kiểm tra **lời gọi tương tác**. Nó không thực hiện handshake SMTP hoặc gửi bytes sang server.

Trong một integration test, bean `JavaMailSender` thật được Spring Boot cấu hình. Server giả lập nhận message và cho test truy xuất dữ liệu để assert. Hai loại test bổ sung cho nhau, không cần chọn một bỏ một.

## 3. Những lựa chọn mail server thử nghiệm

Một số công cụ thường được dùng:

| Công cụ | Mô hình | Cách quan sát thư | Phù hợp khi |
| --- | --- | --- | --- |
| **Mailpit** | SMTP sink, thường chạy container/tiến trình độc lập | Web UI và HTTP API | Thử email local, integration test, xem MIME trực quan |
| **MailHog** | SMTP sink cho môi trường phát triển | Web UI và HTTP API | Dự án đã dùng MailHog, kiểm tra SMTP nhanh |
| **GreenMail** | Mail server giả lập bằng Java, có thể chạy in-process hoặc container | Java API, IMAP/POP3/SMTP tùy cấu hình | Test tích hợp Java/Jakarta Mail, xác nhận nội dung thư trực tiếp |
| **Wiser / SubEthaSMTP** | SMTP server nhỏ trong tiến trình test | API Java nhận message | Test gửi SMTP nhẹ, không cần web UI |
| **SMTP test container tự cấu hình** | Container chạy service SMTP phục vụ test | Theo API/log/protocol của server | Cần mô phỏng policy hoặc handshake riêng |

Lựa chọn phụ thuộc yêu cầu kiểm thử, khả năng chạy Docker trong CI và việc có cần đọc thư qua API, IMAP hay chỉ cần nhận SMTP.

### 3.1. Mailpit và MailHog là SMTP sink

SMTP sink là một mail server **nhận và giữ email ở môi trường kiểm thử** thay vì gửi tiếp ra Internet. Nhờ đó, developer có thể xem thư trong UI, còn test tự động có thể gọi API để kiểm tra.

Không nên mặc định tất cả SMTP sink hỗ trợ cùng API. Chẳng hạn API của Mailpit và MailHog không giống nhau; code test cần theo tài liệu của công cụ và phiên bản đang dùng.

### 3.2. GreenMail khi cần tương tác bằng Java

GreenMail thường phù hợp khi muốn:

- Khởi động một server SMTP trong process test.
- Lấy danh sách `MimeMessage` đã nhận qua Java API.
- Kiểm tra các phần multipart, attachment, header.
- Dùng thêm IMAP/POP3 trong bài test yêu cầu nhận mail.

Chú ý chọn **GreenMail version tương thích với Jakarta Mail hoặc JavaMail API** của ứng dụng. Với Spring Boot 3 trở lên, nhiều import là `jakarta.mail.*`; một dependency cũ chỉ dùng `javax.mail.*` có thể gây xung đột loại dữ liệu.

### 3.3. Khi nào dùng container?

Container hữu ích nếu muốn:

- Mail server chạy độc lập với JVM test.
- Sử dụng image/server giống nhau ở máy lập trình và CI.
- Không để server in-process ảnh hưởng các classloader/test khác.
- Test cài đặt `spring.mail.*` qua network host/port thật.
- Có thể tái lập hạ tầng bằng Docker Compose hoặc Testcontainers.

Container không tự động làm test “thật hơn” ở mọi khía cạnh. Nếu chỉ cần kiểm tra `MimeMessage` đã được dựng đúng và không cần network, GreenMail/Wiser in-process có thể nhẹ hơn.

## 4. Chạy Mailpit cục bộ bằng Docker Compose

Một cách thuận tiện là chạy Mailpit trên máy phát triển:

~~~yaml
# compose.yaml
services:
  mailpit:
    image: axllent/mailpit:v1.27.5
    ports:
      - "127.0.0.1:1025:1025"   # SMTP từ host
      - "127.0.0.1:8025:8025"   # Web UI / API từ host
~~~

Tag `v1.27.5` là **phiên bản minh họa được pin**; dự án cần chọn một tag đã kiểm tra và chủ động cập nhật theo chính sách dependency của mình. Trong CI, tránh dùng `latest` nếu yêu cầu build có tính tái lập cao.

Chạy môi trường local:

~~~bash
docker compose up -d mailpit
~~~

Với mapping này:

- `localhost:1025` trên máy host: SMTP của Mailpit.
- `http://localhost:8025` trên máy host: giao diện xem email và API.
- Các cổng được bind vào `127.0.0.1` để hạn chế truy cập từ mạng bên ngoài máy.

Nếu ứng dụng Spring cũng chạy **bên trong Docker Compose**, không sử dụng `localhost` của container ứng dụng để trỏ sang container Mailpit. Trong mạng Compose, dùng hostname service:

~~~yaml
spring:
  mail:
    host: mailpit
    port: 1025
~~~

Còn khi ứng dụng chạy trực tiếp trên máy host, dùng `127.0.0.1` hoặc `localhost`.

### 4.1. Cấu hình Spring Boot cho local

Tạo cấu hình profile test/local không chứa credential production:

~~~yaml
# application-local.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

Đây là ví dụ **dành riêng cho SMTP sink chạy trên máy local hoặc mạng thử nghiệm cô lập**. Không copy `auth=false` và TLS disabled sang SMTP production trên mạng công cộng. Với provider thực, cần cấu hình AUTH/TLS theo chính sách bảo mật.

Trong Spring Boot, `spring.mail.properties` là một map các thuộc tính Jakarta Mail. Dấu ngoặc vuông trong key YAML giúp bảo toàn phần có dấu chấm như `mail.smtp.timeout` khi binding map.

### 4.2. Gửi thử một email

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class DemoMailService {

    private final JavaMailSender mailSender;

    public DemoMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendDemo() {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.test");
        message.setTo("student@example.test");
        message.setSubject("Thử gửi email qua SMTP giả lập");
        message.setText("Nội dung email tiếng Việt được gửi tới Mailpit.");
        mailSender.send(message);
    }
}
~~~

Sau khi gọi method, vào Web UI Mailpit ở `http://localhost:8025` để xem thư được giữ lại. Không có lý do phải gửi một email thật ra Internet để kiểm tra bước này.

### 4.3. Những điểm UI giúp developer quan sát

Tùy phiên bản server, UI/API có thể giúp xem:

- Địa chỉ To, Cc, Bcc và From của message.
- Subject, nội dung plain text, HTML render và HTML source.
- Cấu trúc MIME, attachment và content type.
- Các header như Message-ID, Reply-To, Date.
- Thời điểm server giả lập nhận email.

Không nhầm “Mailpit đã nhận email” với “mailbox đích trên Internet đã nhận được”. Mailpit đang đóng vai trò nơi nhận cuối của bài test.

## 5. Tích hợp SMTP test container vào JUnit với Testcontainers

Với integration test tự động, có thể để **Testcontainers** khởi tạo Mailpit theo vòng đời test. Test không phải phụ thuộc vào việc developer đã chạy `docker compose up` trước đó.

Các thành phần thường cần:

~~~text
Spring Boot application
    ├── spring-boot-starter-mail
    └── spring-boot-starter-test

Integration test
    ├── Testcontainers JUnit 5 integration
    ├── Testcontainers core
    └── Docker-compatible container runtime
~~~

Quản lý phiên bản dependency bằng BOM của Spring Boot/Testcontainers phù hợp dự án. Không nên copy các version khác nhau một cách tùy tiện giữa Spring Boot, Jakarta Mail và thư viện test.

### 5.1. Testcontainers ánh xạ port động

Trong Testcontainers, port ở **bên trong container** thường ổn định (`1025` cho SMTP), nhưng port được expose ở máy host là port **ngẫu nhiên** để tránh xung đột giữa nhiều test suite:

~~~text
Test JVM                           Mailpit container

localhost:randomHostPort  ------->  1025/tcp SMTP
localhost:randomApiPort   ------->  8025/tcp HTTP API
~~~

Vì vậy, test không được hard-code port host `1025`. Dùng `container.getHost()` và `container.getMappedPort(1025)`. Cách truy cập này hoạt động tốt hơn với cả Docker cục bộ và các môi trường chạy container từ xa được Testcontainers hỗ trợ.

### 5.2. Cấu hình bean JavaMailSender bằng @DynamicPropertySource

Một ví dụ Spring Boot integration test dùng JUnit 5 và Testcontainers:

~~~java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class MailpitSmtpIntegrationTest {

    private static final int SMTP_PORT = 1025;
    private static final int API_PORT = 8025;

    @Container
    static final GenericContainer<?> mailpit =
            new GenericContainer<>(
                    DockerImageName.parse("axllent/mailpit:v1.27.5"))
                    .withExposedPorts(SMTP_PORT, API_PORT)
                    .waitingFor(
                            Wait.forHttp("/api/v1/messages")
                                    .forPort(API_PORT)
                                    .forStatusCode(200));

    @DynamicPropertySource
    static void configureMail(DynamicPropertyRegistry registry) {
        registry.add("spring.mail.host", mailpit::getHost);
        registry.add("spring.mail.port",
                () -> mailpit.getMappedPort(SMTP_PORT));
        registry.add("spring.mail.properties.mail.smtp.auth",
                () -> false);
        registry.add("spring.mail.properties.mail.smtp.starttls.enable",
                () -> false);
        registry.add("spring.mail.properties.mail.smtp.connectiontimeout",
                () -> 5000);
        registry.add("spring.mail.properties.mail.smtp.timeout",
                () -> 5000);
    }

    @Autowired
    JavaMailSender mailSender;

    @Test
    void canSubmitMailToSmtpTestContainer() {
        String subject = "SMTP test " + UUID.randomUUID();

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.test");
        message.setTo("student@example.test");
        message.setSubject(subject);
        message.setText("Xin chào từ Spring Mail!");

        mailSender.send(message);

        // Bước tiếp theo: truy xuất captured email từ HTTP API
        // của Mailpit và xác nhận subject/recipient/body.
    }
}
~~~

Test ví dụ trên chứng minh đường gọi gửi không ném exception khi SMTP sink hoạt động; để test thực sự xác nhận **đã nhận đúng email**, cần thêm assertion với Mailpit API như phần tiếp theo. Các import/assertion không dùng trong snippet có thể bỏ khi chép vào dự án.

**Điểm kỹ thuật:** `@DynamicPropertySource` cung cấp host/port **trước khi** Spring tạo `JavaMailSender`. `@Container` và `@Testcontainers` quản lý lifecycle container khi test bắt đầu/kết thúc.

Nếu Spring context trước đó đã cache một `JavaMailSender` với property khác, cần tổ chức các lớp test và context caching phù hợp; không sửa bean singleton sau khi context đã tạo để “đổi port” một cách ngẫu nhiên.

## 6. Đọc email đã nhận qua Mailpit HTTP API

Một integration test tốt cần xác nhận **SMTP server thật sự giữ lại đúng message**, thay vì chỉ xác nhận `send(...)` không ném exception.

Mailpit có HTTP API để truy xuất các email được capture. Ở các phiên bản có endpoint `GET /api/v1/messages`, response JSON chứa danh sách messages, trong đó thường có ID, subject và metadata người gửi/nhận. Hãy pin image/test adapter theo **API version đang dùng**; không assume API MailHog tương thích Mailpit.

Một helper Java đơn giản:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class MailpitApiClient {

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();
    private final URI messagesUri;

    public MailpitApiClient(String host, int apiPort) {
        this.messagesUri = URI.create(
                "http://" + host + ":" + apiPort + "/api/v1/messages");
    }

    public JsonNode listMessages() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(messagesUri)
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Mailpit API returned " + response.statusCode());
        }

        return mapper.readTree(response.body());
    }
}
~~~

Helper chỉ truy xuất danh sách thư. Những trường JSON cụ thể và endpoint đọc chi tiết MIME/header cần kiểm tra trong API của **phiên bản Mailpit được pin**.

### 6.1. Assertion theo subject duy nhất

Để tránh ảnh hưởng giữa các test chia sẻ cùng container, có thể tạo một subject duy nhất cho mỗi test rồi tìm đúng message đó:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.stream.StreamSupport;

@Test
void smtpContainerCapturesTheMessage() {
    String subject = "Kiểm thử SMTP " + UUID.randomUUID();

    SimpleMailMessage email = new SimpleMailMessage();
    email.setFrom("notifications@example.test");
    email.setTo("student@example.test");
    email.setSubject(subject);
    email.setText("Nội dung test gửi bằng Spring Mail");

    mailSender.send(email);

    MailpitApiClient api = new MailpitApiClient(
            mailpit.getHost(),
            mailpit.getMappedPort(API_PORT));

    await()
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(200))
            .untilAsserted(() -> {
                var response = api.listMessages();
                boolean found = StreamSupport.stream(
                        response.path("messages").spliterator(), false)
                        .anyMatch(item ->
                                subject.equals(
                                        item.path("Subject").asText()));
                assertThat(found).isTrue();
            });
}
~~~

Ví dụ này nằm trong lớp `MailpitSmtpIntegrationTest` ở phần trước, dùng các field `mailSender`, `mailpit` và `API_PORT` đã khai báo. `Awaitility` thường có trong bộ test dependency Spring Boot; nếu dự án chưa có, bổ sung dependency test tương ứng.

Ưu điểm của cách này:

- Không dùng `Thread.sleep(2000)` cố định.
- Cho phép một độ trễ nhỏ khi message xuất hiện trong API.
- Phân biệt thư của các bài test bằng subject ngẫu nhiên.
- Khi quá thời hạn, test thất bại rõ ràng thay vì chạy vô hạn.

Nếu server giả lập trả message ID ổn định, có thể tiếp tục truy vấn nội dung chi tiết và kiểm tra recipient, plain text, HTML hoặc attachment. Không nên assert toàn bộ response JSON như một chuỗi bất biến vì nó có timestamp, ID và metadata thay đổi theo lần chạy.

### 6.2. Đặt tên test API adapter tập trung

Đừng copy code đọc JSON Mailpit vào hàng chục bài test. Nên tạo một test support class như `MailpitApiClient` có các thao tác:

~~~text
listMessages()
findByUniqueSubject(subject)
readMessage(id)
readRawMessage(id)
clearMailboxForIsolatedTest()
~~~

Những method trên là **thiết kế helper đề xuất**, không phải chữ ký có sẵn của Mailpit. Implementation cần dùng các endpoint được tài liệu Mailpit phiên bản đã chọn hỗ trợ.

Việc tập trung adapter giúp thay đổi Mailpit API version hoặc chuyển công cụ dễ hơn mà không sửa toàn bộ test case.

## 7. Kiểm thử MIME message: HTML, plain text và charset

Một email giao dịch thường có cả HTML và plain text:

~~~text
MimeMessage
  |
  +-- multipart/alternative
        |
        +-- text/plain; charset=UTF-8
        |
        +-- text/html; charset=UTF-8
~~~

Khi thêm attachment, MIME tree có thể lồng thêm `multipart/mixed` hoặc `multipart/related`, tùy cách `MimeMessageHelper` cấu hình multipart. Không nên assert cứng rằng mọi email có đúng **một cấu trúc MIME tree duy nhất**, vì implementation và việc có inline resource/attachment có thể thay đổi nesting hợp lệ.

### 7.1. Tạo email HTML/plain text bằng MimeMessageHelper

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendWelcomeMail(String recipient)
        throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message, true, "UTF-8");

    helper.setFrom("notifications@example.test");
    helper.setTo(recipient);
    helper.setReplyTo("support@example.test");
    helper.setSubject("Chào mừng đến với hệ thống");

    String plain = "Xin chào Lan! Tài khoản của bạn đã được tạo.";
    String html = """
            <html>
              <body>
                <h1>Xin chào Lan!</h1>
                <p>Tài khoản của bạn đã được tạo.</p>
              </body>
            </html>
            """;

    helper.setText(plain, html);
    mailSender.send(message);
}
~~~

Đoạn code dùng Java text block; nếu dự án sử dụng phiên bản Java thấp hơn, có thể dùng chuỗi thường hoặc template engine. Mục tiêu test là xác nhận MIME chứa hai biến thể nội dung và ký tự tiếng Việt được giữ đúng khi đi qua SMTP.

### 7.2. Những assertion có giá trị

Với một công cụ cho phép lấy `MimeMessage` hoặc raw MIME, có thể kiểm tra:

- Header `From` chính xác với sender ứng dụng.
- Danh sách `To`, `Cc`, `Bcc` phù hợp với delivery được tạo.
- `Reply-To` nếu sản phẩm yêu cầu.
- Subject giải mã đúng Unicode.
- Có phần `text/plain`.
- Có phần `text/html`.
- Nội dung tiếng Việt và ký tự như `&`, `<`, `>` không bị sai encoding.
- Template variables đã được map đúng thành giá trị.
- Header hoặc attachment không chứa token nhạy cảm ngoài dự kiến.

Không so sánh raw message byte-for-byte nếu không có lý do rõ ràng: MIME boundary, Message-ID, header folding và Date có thể được tạo khác nhau giữa các lần gửi.

### 7.3. Hàm tìm nội dung theo MIME type

Với Jakarta Mail, một helper test có thể duyệt MIME tree:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public final class MimeTestSupport {

    public static String findTextPart(Part part, String mimeType)
            throws Exception {

        if (part.isMimeType(mimeType)) {
            Object content = part.getContent();
            return content instanceof String text ? text : null;
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                String found = findTextPart(child, mimeType);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }
}
~~~

Đây là helper đơn giản cho test đã kiểm soát nội dung. Trong test production-grade, có thể cần xử lý `message/rfc822` lồng bên trong, attachment, exception và giới hạn độ sâu/bộ nhớ nếu input không đáng tin cậy.

Không dùng `message.getContent().toString()` để kiểm tra HTML; `getContent()` của một MIME message có thể là `Multipart` chứ không phải `String`.

### 7.4. Ký tự đặc biệt trong subject và body

Các trường hợp nên có:

~~~text
Subject: Hóa đơn tháng 11 – tài khoản Nguyễn Ánh
Plain: Xin chào, số tiền thanh toán là 1.250.000 ₫.
HTML: <p>Xin chào Nguyễn Ánh &amp; gia đình!</p>
~~~

Với HTML, cần phân biệt **escaping** và **encoding**:

- UTF-8 xử lý ký tự Unicode.
- HTML escaping xử lý `&`, `<`, dấu nháy theo context hiển thị.
- MIME transfer encoding (base64/quoted-printable) là cách vận chuyển nội dung qua giao thức, không phải chỉ dấu dữ liệu bị sai.

Test nên kiểm tra **nội dung sau khi giải mã MIME** thay vì đòi raw SMTP phải chứa ký tự tiếng Việt ở dạng nguyên văn.

## 8. Kiểm thử file đính kèm và inline resources

Email có PDF, CSV hoặc logo inline cần kiểm tra thêm:

~~~java
import org.springframework.core.io.ByteArrayResource;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");

helper.setFrom("invoices@example.test");
helper.setTo("customer@example.test");
helper.setSubject("Hóa đơn kiểm thử");
helper.setText(
        "Hóa đơn được gửi kèm theo email.",
        "<p>Hóa đơn được gửi kèm theo email.</p>");

byte[] fakePdf = new byte[] {
        0x25, 0x50, 0x44, 0x46, 0x2D,
        0x31, 0x2E, 0x34, 0x0A
};

helper.addAttachment(
        "invoice-test.pdf",
        new ByteArrayResource(fakePdf),
        "application/pdf");

mailSender.send(message);
~~~

Mảng bytes chỉ là **dữ liệu giả có prefix giống PDF**, không phải một file PDF hợp lệ để mở. Dùng nó khi muốn kiểm tra việc gắn tên/content-type và truyền bytes thử nghiệm. Nếu test cần mở hoặc đọc PDF, phải dùng fixture PDF hợp lệ do test kiểm soát.

Những assertion nên có:

| Thuộc tính | Mong đợi |
| --- | --- |
| Filename | `invoice-test.pdf` |
| Content-Type | `application/pdf` hoặc media type tương ứng |
| Attachment count | Đúng số file theo nghiệp vụ |
| Bytes | Khớp fixture đầu vào sau khi decode |
| HTML/plain text | Vẫn tồn tại và đúng nội dung |
| Inline logo | Có Content-ID và tham chiếu `cid:...` phù hợp nếu dùng |

Không tạo attachment lớn nhiều megabyte trong mọi unit test. Dùng fixture nhỏ cho test thường xuyên và test dung lượng lớn riêng khi cần kiểm tra timeout/size limit.

### 8.1. Thứ tự setText và addInline

Nếu dùng resource inline:

~~~java
helper.setText(
        "<html><img src=\"cid:brand-logo\" /></html>",
        true);
helper.addInline(
        "brand-logo",
        new ByteArrayResource(logoBytes),
        "image/png");
~~~

Theo cách sử dụng thông dụng của `MimeMessageHelper`, đặt nội dung text trước khi thêm inline resource giúp cấu trúc MIME được dựng đúng. Test integration nên xác nhận mail client/test MIME parser có thể tìm được `Content-ID` trùng với tham chiếu trong HTML.

## 9. GreenMail: nhận email qua Java API trong test

Mailpit phù hợp khi cần container và HTTP API. GreenMail là một lựa chọn khác để thử trực tiếp trong JVM, thường cho phép lấy message nhận được như `MimeMessage`.

Ví dụ khung test Java/JUnit:

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;

import static org.assertj.core.api.Assertions.assertThat;

class GreenMailExample {

    private GreenMail server;

    @BeforeEach
    void startMailServer() {
        ServerSetup setup = new ServerSetup(
                3025, "127.0.0.1", "smtp");
        server = new GreenMail(setup);
        server.start();
    }

    @AfterEach
    void stopMailServer() {
        server.stop();
    }

    @Test
    void capturesMail() throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(3025);

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("sender@example.test");
        message.setTo("receiver@example.test");
        message.setSubject("Gửi đến GreenMail");
        message.setText("Nội dung thử nghiệm");

        sender.send(message);

        assertThat(server.waitForIncomingEmail(5000, 1))
                .isTrue();
        MimeMessage[] received = server.getReceivedMessages();
        assertThat(received).hasSize(1);
        assertThat(received[0].getSubject())
                .isEqualTo("Gửi đến GreenMail");
    }
}
~~~

Đây là ví dụ **server in-process**, tạo `JavaMailSenderImpl` trực tiếp nên không khởi động Spring context. Nó kiểm tra SMTP transport và nội dung nhận ở mức integration, nhưng không xác nhận toàn bộ auto-configuration của Spring Boot. Chọn GreenMail artifact/version tương thích `jakarta.mail.*`.

Port `3025` là ví dụ cố định. Để chạy test song song đáng tin cậy, nên dùng port động hoặc phân tách server riêng giữa các test và inject port vào sender. Tránh test suite cạnh tranh cùng cổng. Với GreenMail extension của JUnit 5 hoặc cấu hình Spring context, cần lưu ý server phải khởi động **trước khi** các property tạo mail sender được resolve.

### 9.1. GreenMail khác Testcontainers Mailpit ở đâu?

GreenMail in-process:

- Không đòi Docker runtime.
- Dễ lấy `MimeMessage` bằng Java API.
- Có thể rất nhanh với test nhỏ.
- Cần quản lý port, server lifecycle và compatibility Jakarta Mail.

Testcontainers Mailpit:

- SMTP service độc lập với JVM.
- Cấu hình hạ tầng gần giống service chạy qua network.
- Dễ xem thư bằng UI/API khi debug local.
- Cần Docker-compatible runtime và thời gian khởi tạo container.

Không có công cụ nào luôn tối ưu cho mọi dự án. Một bộ test có thể dùng **mock** cho unit test, **GreenMail** cho test MIME và **Mailpit container** cho một số bài kiểm tra cấu hình end-to-end.

## 10. Kiểm thử @Async: đợi kết quả theo điều kiện thay vì sleep

Trong ứng dụng thật, email có thể được gửi bởi một method `@Async`:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public void sendWelcome(String recipient, String correlationId) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("welcome@example.test");
        message.setTo(recipient);
        message.setSubject("Welcome " + correlationId);
        message.setText("Chào mừng bạn tới ứng dụng!");
        mailSender.send(message);
    }
}
~~~

Lời gọi `sendWelcome(...)` có thể trả về cho test trước khi worker gửi xong. Vì vậy cách sau không ổn định:

~~~java
welcomeMailService.sendWelcome(recipient, id);
assertThat(mailpitMessages()).hasSize(1);
~~~

Ngay tại thời điểm assert, executor có thể chưa xử lý job.

### 10.1. Dùng Awaitility để poll mail server

~~~java
String correlation = UUID.randomUUID().toString();
welcomeMailService.sendWelcome(
        "student@example.test",
        correlation);

await()
        .atMost(Duration.ofSeconds(15))
        .pollInterval(Duration.ofMillis(250))
        .untilAsserted(() -> {
            boolean exists = mailpitApi
                    .findBySubject("Welcome " + correlation)
                    .isPresent();
            assertThat(exists).isTrue();
        });
~~~

`mailpitApi.findBySubject(...)` là helper test đề xuất, không phải API có sẵn của Spring/Mailpit. Nó có thể được xây từ endpoint danh sách message của Mailpit như phần trước.

Cách chờ theo **điều kiện có timeout** tốt hơn một `Thread.sleep` cố định, vì:

- Test không ngủ quá lâu khi mail đến nhanh.
- Test có thời hạn rõ khi worker bị kẹt.
- CI chậm hơn máy local vẫn có khoảng thời gian hợp lý.
- Phân biệt lỗi “không gửi được” với race giữa worker và assertion.

Không dùng một subject cố định cho nhiều test chạy song song rồi assert “có một email bất kỳ”; message từ test khác có thể khiến bài test pass giả.

### 10.2. Nếu @Async trả CompletableFuture

Một service có thể trả `CompletableFuture<MailSubmission>` để caller biết **SMTP submission** đã hoàn tất:

~~~java
CompletableFuture<MailSubmission> future =
        asyncMailService.submit(command);

MailSubmission submission =
        future.get(10, TimeUnit.SECONDS);

assertThat(submission.deliveryId())
        .isEqualTo(command.deliveryId());
~~~

Đoạn này chỉ phù hợp cho test hoặc ranh giới thật sự cần chờ kết quả. Trong request path production, gọi `get()` ngay sau `submit(...)` có thể khiến người dùng vẫn phải đợi SMTP.

Ngay cả khi Future thành công, nên dùng mail server giả lập để xác nhận message thực sự đã được nhận với đúng nội dung và recipient. Future của service chỉ phản ánh logic lập trình của service.

### 10.3. @Async void và lỗi bị bỏ qua

Với `@Async void`, exception trong worker không tự động ném lại cho thread đang chạy test. Một bài test chỉ gọi method và không kiểm tra server/handler có thể pass dù SMTP send đã thất bại.

Trong integration test:

- Sử dụng mail sink để assert message xuất hiện.
- Dùng `AsyncUncaughtExceptionHandler` có thể quan sát được nếu cần test lỗi.
- Tốt hơn, với email quan trọng, lưu trạng thái job/outbox và assert trạng thái đó.
- Không dựa vào việc HTTP request đã trả response để kết luận email gửi xong.

## 11. Kiểm thử transactional outbox cùng SMTP container

Trong một ứng dụng thương mại, việc gửi email giao dịch thường tách khỏi HTTP transaction bằng **transactional outbox**:

~~~text
Business service
  |
  | transaction
  +--> save order
  +--> insert mail_outbox(PENDING)
  |
  v
COMMIT
  |
  v
Outbox worker
  |
  +--> claim row (PROCESSING)
  +--> send via JavaMailSender
  +--> mark SENT after SMTP accepted
  |
  v
Mailpit container stores message
  |
  v
Integration test queries DB + Mailpit API
~~~

Đây là integration test có **hai hệ thống**:

1. Database thực hoặc test container (ví dụ PostgreSQL) lưu domain và outbox.
2. SMTP test container giữ email được gửi ra.

Mock riêng repository hoặc mail sender có thể không bắt được lỗi transaction/concurrency/connection ở ranh giới tích hợp này.

### 11.1. Testcontainers cho PostgreSQL và Mailpit

Ví dụ khung cấu hình nhiều container:

~~~java
@SpringBootTest
@Testcontainers
class OrderOutboxMailIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>(
                    DockerImageName.parse("postgres:16-alpine"))
                    .withDatabaseName("mail_test")
                    .withUsername("test")
                    .withPassword("test");

    @Container
    static final GenericContainer<?> mailpit =
            new GenericContainer<>(
                    DockerImageName.parse("axllent/mailpit:v1.27.5"))
                    .withExposedPorts(1025, 8025)
                    .waitingFor(
                            Wait.forHttp("/api/v1/messages")
                                    .forPort(8025));

    @DynamicPropertySource
    static void dynamicProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);

        registry.add("spring.mail.host", mailpit::getHost);
        registry.add("spring.mail.port",
                () -> mailpit.getMappedPort(1025));
        registry.add("spring.mail.properties.mail.smtp.auth",
                () -> false);
        registry.add(
                "spring.mail.properties.mail.smtp.starttls.enable",
                () -> false);
    }

    // Autowire application service, outbox repository và test API.
    // Test chạy use case rồi xác nhận DB state và captured email.
}
~~~

Đây là khung code; cần dependency `org.testcontainers:postgresql`, JDBC driver phù hợp, Spring Data/transaction support và các import. Test dự án phải tạo schema bằng migration hoặc test setup được kiểm soát.

Các version image được dùng để **minh họa cách pin tag**, không có nghĩa đó là phiên bản mới nhất. Chọn tag đã được nhóm xác minh. Dùng Testcontainers để kiểm thử đúng loại database production khi hành vi transaction, locking và SQL dialect quan trọng.

### 11.2. Test: chỉ gửi sau commit

Kịch bản:

1. Mở transaction nghiệp vụ.
2. Lưu đơn hàng và outbox row.
3. Trước commit, worker không được xử lý email của transaction chưa commit.
4. Sau commit, kích hoạt worker hoặc đợi poll.
5. Kiểm tra outbox chuyển từ `PENDING` sang `SENT`.
6. Kiểm tra Mailpit giữ một message có correlation ID chính xác.

Với Spring test, `@Transactional` trên **chính test method** có thể làm toàn bộ dữ liệu được tạo chỉ commit khi test hoàn tất (hoặc rollback mặc định), khiến worker khác không thấy dữ liệu. Vì vậy, khi test luồng outbox sau commit, hãy chủ động điều khiển transaction của application service hoặc dùng `TransactionTemplate`/`TestTransaction` phù hợp, **đừng mặc định bọc toàn bộ test trong một transaction rollback**.

### 11.3. Test gửi lại và idempotency

Nếu worker retry khi một task gặp lỗi, test cần phân biệt:

- Một sự kiện nghiệp vụ được insert đúng một outbox row (`deliveryKey` duy nhất).
- Worker gửi message rồi cập nhật `SENT`.
- Một lần poll tiếp theo không gửi thêm message đã `SENT`.
- Hai worker đồng thời không claim cùng một outbox row khi lease còn hiệu lực.
- Nếu send ném lỗi rõ ràng trước SMTP acceptance, outbox chuyển `RETRY`/`FAILED` theo policy.
- Nếu database update `SENT` thất bại sau SMTP acceptance, có nguy cơ duplicate; **không tuyên bố exactly-once**.

Fake SMTP giúp kiểm tra số message thực tế được nhận. Ví dụ một workflow đúng có thể assert `1` message với một unique correlation ID trong điều kiện không cố ý tạo crash window.

### 11.4. Đừng đồng nhất SENT với DELIVERED

Nếu outbox ghi:

~~~text
status = SENT
smtpAcceptedAt = ...
~~~

ý nghĩa thường là `JavaMailSender.send` hoàn tất, tức thư đã được SMTP server mà ứng dụng kết nối chấp nhận. Trong integration test, SMTP server đó là **Mailpit**. Không nên tạo assertion `DELIVERED_TO_INBOX` từ dữ liệu Mailpit vì nó không giao thư tới mailbox Internet.

Kiểm thử bounce/DSN hoặc webhook của provider là một nhóm test khác, cần mô phỏng phản hồi giao thư hoặc dùng môi trường provider staging được phép.

## 12. Khi cần kiểm thử lỗi SMTP

Mailpit/MailHog mặc định chủ yếu nhằm **nhận thư và hiển thị nội dung**. Chúng rất hữu ích cho happy path, nhưng không nhất thiết cung cấp giao diện đầy đủ để giả lập mọi lỗi SMTP, ví dụ:

- `421` server tạm thời không sẵn sàng.
- `450/451` từ chối tạm thời người nhận.
- `550/553` từ chối vĩnh viễn.
- SMTP authentication thất bại.
- STARTTLS bị thiếu hoặc handshake certificate lỗi.
- Connection drop giữa DATA.
- Timeout sau khi relay đã chấp nhận message.

Không nên mặc định một SMTP sink có thể mô phỏng tất cả những tình huống trên chỉ bằng config flag. Có thể dùng:

1. **Mock `JavaMailSender`** cho test application-level retry/classifier.
2. **Fake SMTP server có thể script response** cho protocol-level failure.
3. **GreenMail với auth/TLS đúng cấu hình** cho các tình huống nó hỗ trợ.
4. **Provider staging/test mode** nếu cần xác nhận một phản hồi cụ thể của vendor.

### 12.1. Tách hai loại lỗi: preparation và transport

| Loại lỗi | Ví dụ | Cách test |
| --- | --- | --- |
| MIME preparation | Template lỗi, địa chỉ sai, attachment resource không đọc được | Unit test MimeMessageHelper/renderer |
| Executor overload | Task bị từ chối khi queue đầy | Test với executor giả hoặc bounded executor |
| SMTP connect timeout | Không tới được endpoint | Test transport failure có kiểm soát |
| SMTP auth failure | Sai credentials hoặc server yêu cầu auth | SMTP fake có auth hoặc staging |
| SMTP rejection | 4xx/5xx theo command | Scripted SMTP server/test harness |
| Database state update failure | Sau `send` không ghi được `SENT` | Outbox integration test với transaction failure |

Lỗi ở bước dựng MIME xảy ra **trước** khi gửi SMTP. Nếu một test chỉ kiểm tra fake SMTP không có thư nào, cần thêm assertion về exception/trạng thái để biết vì sao message không xuất hiện.

### 12.2. Mockito cho chính sách retry

Ví dụ kiểm tra lớp điều phối:

~~~java
@Test
void recordsRetryWhenTransportIsTemporarilyUnavailable() {
    JavaMailSender sender = mock(JavaMailSender.class);
    MailOutboxStateService stateService =
            mock(MailOutboxStateService.class);

    doThrow(new MailSendException("SMTP temporary failure"))
            .when(sender).send(any(SimpleMailMessage.class));

    MailDispatcher dispatcher = new MailDispatcher(
            sender,
            stateService,
            new RetryPolicy(/* test config */));

    dispatcher.dispatch(testDelivery());

    verify(stateService).scheduleRetry(
            any(),
            any(),
            eq("SMTP_TEMPORARY"));
}
~~~

Các lớp `MailDispatcher`, `MailOutboxStateService` và `RetryPolicy` là **abstraction minh họa** do ứng dụng triển khai. Việc tạo một `MailSendException` trong mock **không xác nhận** SMTP server thật sẽ trả mã lỗi cụ thể; nó chỉ kiểm tra cách ứng dụng xử lý exception đã được giả lập.

Đừng phân loại retryable chỉ dựa trên tên `MailSendException` trong production: exception có thể bao bọc lỗi khác nhau, gồm từ chối người nhận hoặc kết quả gửi chưa rõ ràng.

### 12.3. Network failure và timeout cần diễn giải thận trọng

Một timeout trước khi mở kết nối SMTP thường chứng tỏ message chưa được truyền. Nhưng nếu kết nối mất sau khi app đã gửi DATA, SMTP server có thể đã chấp nhận message dù client không nhận được phản hồi cuối.

Thử lại ngay trong tình huống kết quả chưa rõ có thể tạo duplicate. Integration test có thể kiểm tra **chính sách trạng thái UNKNOWN/reconciliation** của ứng dụng, nhưng không thể tự chứng minh exactly-once giữa database và một SMTP server không tham gia cùng transaction.

Trong test, không nên cố gây timeout ngẫu nhiên bằng cách làm mạng CI chập chờn; hãy dùng một fake server có hành vi lỗi xác định và timeout có giới hạn để bài test lặp lại được.

## 13. Cô lập dữ liệu giữa các integration test

Một test container có thể được sử dụng cho nhiều method trong cùng test class. Nếu mailbox của server giả lập vẫn chứa email từ test trước, assertion kiểu “có đúng một email” sẽ dễ thất bại khi chạy lại hoặc chạy song song.

Ba chiến lược thường gặp:

| Chiến lược | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Container riêng cho từng test | Cô lập mạnh, giảm nhiễu | Chậm, tốn tài nguyên |
| Container theo test class + clear mailbox | Tái sử dụng server trong class | Cần API xóa message và đồng bộ cleanup |
| Container dùng chung + correlation ID duy nhất | Ít khởi động lại, nhanh hơn | Phải lọc message chính xác, concurrency phức tạp |

Không có một lựa chọn đúng cho mọi bộ test. Với vài bài kiểm tra email tích hợp, container theo class và subject/correlation ID riêng cho từng test thường là điểm cân bằng hữu ích.

### 13.1. Không chỉ dựa vào vị trí trong danh sách message

Tránh:

~~~java
JsonNode first = api.listMessages()
        .path("messages")
        .get(0);
assertThat(first.path("Subject").asText())
        .isEqualTo("Order Confirmed");
~~~

`messages[0]` có thể thuộc test khác hoặc thứ tự danh sách có thể thay đổi. Thay bằng:

~~~text
deliveryId = UUID do test tạo
subject = "Order Confirmed [test:" + deliveryId + "]"
search captured messages by exact subject or correlation header
assert expected recipient + content
~~~

Nếu muốn dùng custom header `X-Test-Correlation-ID`, chỉ dùng trong môi trường test hoặc khi header đó được policy ứng dụng cho phép:

~~~java
mimeMessage.setHeader("X-Test-Correlation-ID", deliveryId);
~~~

Header chỉ giúp tìm message; test vẫn cần kiểm tra email thuộc đúng recipient và nội dung mong đợi.

### 13.2. Xóa mailbox trước test

Nếu API server hỗ trợ xóa message, có thể clear mailbox trong `@BeforeEach` và đặt server/test class ở chế độ không chạy đồng thời. Nhưng với parallel test dùng chung container:

~~~text
Test A: sends message
Test B: clears mailbox
Test A: asserts message exists -> FAIL
~~~

Vì vậy, **không dùng clear-all endpoint khi nhiều test cùng dùng mailbox song song**. Nên:

- Tắt parallel cho nhóm test dùng chung mailbox.
- Hoặc dùng container/namespace riêng.
- Hoặc chỉ dùng correlation ID và không xóa message của test khác.

Nếu cần xoá dữ liệu để tiết kiệm bộ nhớ, thực hiện cleanup sau test trong môi trường cô lập và có quy tắc rõ ràng.

### 13.3. Tránh cache context trỏ tới container đã dừng

Spring test framework có cơ chế cache application context giữa các test. Một lớp có `@Container static` có thể dừng container sau khi lớp hoàn tất, nhưng context được cache vẫn giữ bean `JavaMailSender` với host/port cũ nếu một lớp khác tái sử dụng context không đúng cách.

Vì vậy:

- Tổ chức integration test SMTP cùng một cấu hình context/container phù hợp.
- Tránh share context giữa những lớp có property động nhưng lifecycle server khác nhau.
- Khi thật sự cần, dùng `@DirtiesContext` để ngăn reuse không phù hợp, đổi lại chi phí khởi động lại context.
- Không tái sử dụng một `JavaMailSenderImpl` đã tạo với port của container cũ rồi mong nó tự cập nhật.
- Đừng bật global reusable container mode chỉ để tăng tốc nếu isolation/cleanup của CI chưa được thiết kế.

### 13.4. Một test nên kiểm tra đúng một delivery

Khi giao dịch gửi nhiều email, nên xác định rõ test đang assert:

~~~text
Create order
  -> customer confirmation: one email to customer
  -> internal audit notice: one email to audit mailbox
~~~

Không assert tổng số message là `1` nếu nghiệp vụ hợp lệ tạo hai email. Có thể lọc theo `deliveryId`/recipient/subject và kiểm tra từng delivery độc lập.

## 14. Tổ chức cấu hình test và tránh gửi mail ra ngoài

Một nguy cơ nghiêm trọng là test vô tình sử dụng SMTP production hoặc credential thật khi file cấu hình/profile bị override sai.

### 14.1. Cấu hình tách biệt theo môi trường

Ví dụ:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-prod.yml

src/test/resources/
  application-test.yml
~~~

`application-test.yml` có thể có fallback host local cho những test không dùng Testcontainers:

~~~yaml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 3000
      "[mail.smtp.writetimeout]": 3000
~~~

Với Testcontainers, `@DynamicPropertySource` override host/port bằng những giá trị thực tế của container. Không sử dụng cùng credential production trong test profile.

### 14.2. Dùng @ActiveProfiles

~~~java
@SpringBootTest
@ActiveProfiles("test")
@Testcontainers
class MailIntegrationTest {
    // Test setup...
}
~~~

Điều này giúp tải các property đặc thù của môi trường test. Tuy nhiên, **profile không phải ranh giới bảo mật duy nhất**. Biến môi trường hoặc tham số command line có precedence cao hơn có thể override property test nếu máy CI vô tình inject `SPRING_MAIL_HOST` hoặc credential production.

Đối với test gửi mail:

- Đặt host/port động từ container qua test infrastructure.
- Giới hạn network egress của job nếu có thể.
- Không cấp SMTP production credential cho test job.
- Gắn tag rõ cho integration test và chỉ chạy với runtime container có quyền phù hợp.
- Kiểm tra mail sender không trỏ sang domain production theo policy test.

### 14.3. Fail closed khi test không có fake SMTP

Một test cần SMTP container nên **thất bại rõ** nếu Docker daemon không khả dụng hoặc server không startup. Không tự fallback sang SMTP thật do một profile khác hoặc secret từ môi trường.

Ví dụ policy:

~~~text
Integration test requires SMTP sink
  |
  +-- Container is available -> run test
  |
  +-- Container unavailable -> fail/skip by explicit test policy
      (never fall back to smtp.production.example)
~~~

Với môi trường CI không có Docker, có thể chạy nhóm unit test mà không cần Testcontainers và tách integration test sang job khác. Đừng âm thầm biến một integration test thành “mocked success” rồi coi nó đã kiểm tra SMTP.

## 15. Chạy Testcontainers trong CI

Để chạy SMTP container trên CI, runner cần một container runtime tương thích và các quyền cần thiết để Testcontainers tạo/dừng container.

Pipeline khái quát:

~~~text
Checkout source
       |
       v
Build / compile / unit tests
       |
       v
Start container runtime in CI
       |
       v
Testcontainers starts fake SMTP
       |
       v
Spring Boot test context gets mapped host/port
       |
       v
Run integration tests
       |
       v
Collect test report / sanitized diagnostics
       |
       v
Stop test containers
~~~

Một số lưu ý:

- Pin image tag, tránh phụ thuộc `latest` hoặc network thay đổi bất ngờ.
- Bảo đảm runner có thể pull image theo chính sách registry/mirror của tổ chức.
- Không yêu cầu đặc quyền container rộng hơn mức cần để test.
- Không expose SMTP test container ra Internet.
- Không dùng test account/password production hoặc gửi tới người nhận thật.
- Có timeout startup và timeout cho assertion để CI không kẹt vô thời hạn.
- Cân nhắc job cache cho dependency/image, nhưng không cache mailbox chứa dữ liệu nhạy cảm.
- Nếu chạy song song, dự trù CPU/RAM/container count.
- Chỉ xuất test report/log đã loại credential/PII.

### 15.1. Phân chia unit và integration test

Một pipeline có thể chia:

| Job | Chạy gì? | Cần Docker? |
| --- | --- | --- |
| Unit | Logic chọn người nhận, render model, mock `JavaMailSender` | Không |
| MIME test | Tạo `MimeMessage` với fake sender | Không nhất thiết |
| SMTP integration | Spring Mail + Mailpit/Testcontainers | Có |
| Database + outbox integration | PostgreSQL + SMTP container | Có |
| Provider staging smoke | Cấu hình SMTP/provider thử nghiệm đã được phép | Theo môi trường |

Không nên bắt mọi developer chạy toàn bộ provider staging test mỗi lần sửa template. Đặt nhãn/nhóm test rõ giúp feedback nhanh và chi phí hợp lý.

### 15.2. Test khi Docker không khả dụng

Nếu muốn giữ một đường kiểm thử SMTP thật nhưng không có Docker trong môi trường chạy, có thể:

- Khởi động GreenMail/Wiser trong JVM test.
- Dùng một fake SMTP service do CI cung cấp trong mạng nội bộ.
- Chạy nhóm Testcontainers ở một runner khác phù hợp.

Tuyệt đối không đổi sang provider production làm “phương án dự phòng”.

### 15.3. Cleanup và dữ liệu nhạy cảm trong mail capture

Mailpit và các fake server thường giữ bản sao nội dung email. Nếu integration test gửi dữ liệu cá nhân thật, mailbox test cũng trở thành nơi lưu PII. Nên:

- Chỉ dùng recipient giả, fixture tổng hợp và token không có quyền thật.
- Giới hạn thời gian tồn tại container/volume.
- Không mount một persistent volume chứa thư test thật trừ khi cần có retention.
- Hạn chế quyền truy cập Web UI/API và port mapping.
- Không lưu raw EML của các email chứa dữ liệu nhạy cảm vào CI artifact mặc định.
- Cẩn thận khi chụp màn hình email để báo bug.

Mục tiêu của test server là giúp kiểm thử, không phải tạo thêm một kho lưu nội dung thư sản xuất.

## 16. Chẩn đoán lỗi khi integration test không gửi được

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Connection refused` | Server chưa startup hoặc host/port sai | Chờ readiness, dùng mapped port |
| `UnknownHostException` | Dùng hostname `mailpit` khi app chạy ngoài Compose | Dùng host thích hợp từng network |
| Testcontainers không chạy | Docker daemon không sẵn, quyền/runner không phù hợp | Kiểm tra cấu hình container runtime của CI |
| Container chạy nhưng gửi đến SMTP production | Profile/env override sai | Tách test properties, không cấp production credentials |
| `MailAuthenticationException` | App bật AUTH nhưng fake SMTP không yêu cầu/hỗ trợ như cấu hình | Dùng `mail.smtp.auth=false` chỉ trong môi trường test cô lập |
| STARTTLS error | App yêu cầu TLS với SMTP sink chưa bật TLS | Test plain SMTP ở local hoặc cấu hình fake TLS-capable riêng |
| Timeout dù server chạy | Firewall/container network, sai port hoặc server không ready | Readiness và kiểm tra host/port/runtime |
| `JavaMailSender.send` không lỗi nhưng test không thấy thư | Đọc nhầm server/API, event async chưa hoàn tất, filter subject sai | Poll theo unique correlation ID |
| Test flake khi chạy song song | Mailbox dùng chung, clear-all, port cố định | Container/test isolation, dynamic port |
| Message có nhưng subject hiển thị lạ | Encoding/charset hoặc cách assert raw header | Decode MIME đúng cách |
| Plain text biến mất | Helper chỉ set HTML hoặc MIME nesting khác dự kiến | Dùng `setText(plain, html)`, duyệt MIME tree |
| File đính kèm không đọc được | Resource không thể mở lại stream hoặc fixture lỗi | Dùng `ByteArrayResource`/resource lặp lại được |
| Sau khi chạy một lớp khác test lỗi port cũ | Spring context cache trỏ container đã dừng | Tổ chức lifecycle/cache hoặc `@DirtiesContext` |
| Lúc pass lúc fail với email async | Assert trước khi worker xử lý xong | Chờ theo điều kiện, có timeout |
| Test tự động gửi trùng | Worker/outbox retry, event trùng hoặc poll đồng thời | Kiểm tra idempotency/lease và đếm theo delivery ID |

### 16.1. Connection refused và port mapping

Trong Testcontainers, không nên viết:

~~~java
registry.add("spring.mail.host", () -> "localhost");
registry.add("spring.mail.port", () -> 1025);
~~~

vì `1025` chỉ là cổng **bên trong container**. Thay bằng:

~~~java
registry.add("spring.mail.host", mailpit::getHost);
registry.add("spring.mail.port",
        () -> mailpit.getMappedPort(1025));
~~~

Đây là một trong những lỗi phổ biến nhất khi chuyển từ Docker Compose local sang Testcontainers.

### 16.2. Không dùng SMTP debug vô hạn

Nếu test lỗi SMTP protocol, có thể bật debug ở một môi trường thử nghiệm được kiểm soát, nhưng không cần và không nên bật log chi tiết authentication trên production. Jakarta Mail debug hoặc application log có thể chứa địa chỉ email/header, và tùy cấu hình có thể lộ thông tin nhạy cảm.

Khi debug:

1. Dùng credential và địa chỉ thử nghiệm.
2. Giới hạn thời gian và nơi lưu log.
3. Không in SMTP password/token.
4. Đọc exception cause và error code được phân loại.
5. Tắt debug khi hoàn tất.

Test container giúp chẩn đoán mà không cần bật log provider thật hoặc gửi thư tới bên ngoài.

## 17. Kiểm thử luồng nghiệp vụ thực tế: xác nhận đăng ký tài khoản

Xét một ứng dụng gửi email chào mừng khi người dùng hoàn tất đăng ký. Một bài integration test có thể kết hợp Spring application service, database và Mailpit.

### 17.1. Kết quả nghiệp vụ cần kiểm tra

Giả sử yêu cầu:

1. Người dùng đăng ký thành công.
2. Ứng dụng tạo một ý định gửi email chào mừng.
3. Worker dùng template để tạo HTML/plain text.
4. SMTP server thử nghiệm chấp nhận email.
5. Nội dung phải chứa tên người nhận và URL xác minh hợp lệ trong môi trường test.

Luồng:

~~~text
POST /registrations
       |
       v
RegistrationService
  +--> save user
  +--> save mail outbox
       |
       v
   DB commit
       |
       v
 MailOutboxWorker
       |
       v
Thymeleaf template + MimeMessageHelper
       |
       v
JavaMailSender
       |
       v
Mailpit SMTP port (mapped dynamically)
       |
       v
Mailpit API: captured email
       |
       v
Test asserts:
  - account created
  - outbox transitioned correctly
  - exactly expected captured messages
  - To/subject/body/URL correct
~~~

Nên dùng dữ liệu test độc lập, không sử dụng token xác minh thật có quyền trong production. Nếu URL chứa token chỉ dành cho test, có thể kiểm tra **đường dẫn và định dạng hợp lệ**, không cần in token ra test report.

### 17.2. Dùng correlation ID để tìm đúng message

Một mẫu phổ biến:

~~~java
String uniqueEmail =
        "student+" + UUID.randomUUID() + "@example.test";

registrationService.register(
        new RegistrationCommand(
                uniqueEmail,
                "Nguyễn An"));

await()
        .atMost(Duration.ofSeconds(15))
        .untilAsserted(() -> {
            var captured = mailpitApi.findByRecipient(uniqueEmail);
            assertThat(captured).hasSize(1);
            assertThat(captured.get(0).subject())
                    .contains("Chào mừng");
            assertThat(captured.get(0).plainText())
                    .contains("Nguyễn An");
        });
~~~

`registrationService.register`, `mailpitApi.findByRecipient` và các model trong ví dụ là **pseudocode hướng thiết kế test**, không phải API có sẵn của Spring. Cần implement test client theo schema của Mailpit và nghiệp vụ của ứng dụng.

Nếu một đợt đăng ký hợp lệ gửi nhiều email, assertion phải xác định rõ loại email cần kiểm tra, không chỉ đếm tất cả message đến địa chỉ đó.

### 17.3. Kiểm tra email không gửi khi transaction rollback

Một tình huống quan trọng:

~~~text
Begin registration transaction
    |
    +--> save user
    +--> save outbox
    |
    v
Business validation fails
    |
    v
ROLLBACK
    |
    v
No committed outbox row
    |
    v
No email submitted to Mailpit
~~~

Nếu ứng dụng gọi `@Async` hoặc gửi trực tiếp **trước khi transaction commit**, email có thể đã được server giả lập nhận dù transaction cuối cùng rollback. Đây là một lỗi tích hợp mà unit test chỉ mock mail sender có thể không phát hiện trong bối cảnh transaction thật.

Test nên xác nhận:

- Giao dịch thất bại không tạo outbox row đã commit.
- Worker không gửi mail cho một sự kiện chưa commit.
- Không có captured message tương ứng với unique registration ID.

Khi test điều kiện **không có email**, không chỉ kiểm tra ngay lập tức rồi pass: worker async có thể chạy sau đó. Có thể dùng cơ chế đồng bộ worker/queue rõ ràng, chờ một khoảng quan sát theo SLA test hoặc kích hoạt poll theo cách xác định để chứng minh không có job đủ điều kiện được gửi.

### 17.4. Kiểm tra retry không gây gửi trùng trên happy path

Sau khi một delivery đã chuyển `SENT`:

1. Gọi poll worker lần nữa.
2. Xác nhận không có SMTP submission mới cho cùng delivery.
3. Xác nhận delivery/outbox vẫn ở trạng thái cuối đúng.
4. Xác nhận database không tạo một outbox row mới cho cùng business event nếu deduplication được yêu cầu.

Đây là test idempotency của ứng dụng trong tình huống bình thường. Nó không chứng minh **exactly-once khi JVM crash sau SMTP accepted**; trường hợp đó vẫn có duplicate window nếu provider không hỗ trợ idempotency.

## 18. Các tình huống cần test thêm ngoài happy path

Một bộ integration test chất lượng không chỉ có “gửi một message thành công”. Nên xác định test cases theo yêu cầu của sản phẩm:

| Kịch bản | Cấp test phù hợp | Kết quả mong đợi |
| --- | --- | --- |
| Plain text đơn giản | SMTP sink | Server capture đúng From/To/subject/body |
| HTML + plain alternative | MIME + SMTP sink | Cả hai phần nội dung tồn tại và giải mã đúng |
| Tiếng Việt/Unicode | MIME + SMTP sink | Subject/body không lỗi encoding |
| Attachment/inline image | MIME + SMTP sink | Filename, content type, bytes/CID đúng |
| Gửi một recipient | SMTP sink | Chỉ recipient được phép nhận |
| Cc/Bcc | MIME + SMTP sink | Envelope recipients đúng và Bcc không lộ ngoài ý muốn trong header |
| Invalid recipient format | Unit/MIME | Bị từ chối hoặc báo lỗi đúng tầng |
| SMTP 4xx | Scripted SMTP/mock | Retry với backoff và max attempts |
| SMTP 5xx | Scripted SMTP/mock | Policy permanent failure/suppression phù hợp |
| SMTP connect timeout | Test failure có kiểm soát | Báo transport failure, không treo vô hạn |
| AUTH/TLS bắt buộc | Fake có AUTH/TLS hoặc staging | Không gửi credential qua kênh không được phép |
| Worker @Async | SMTP sink + Awaitility | Message xuất hiện trong timeout cho phép |
| Transaction rollback | DB + SMTP sink | Không gửi email cho event rollback |
| Outbox retry/success | DB + SMTP sink | Trạng thái và số message hợp lệ |
| Hai worker claim song song | DB integration | Không cùng claim một row khi lease còn hiệu lực |
| Trùng business event | DB + SMTP sink | Không phát nhiều delivery nếu dedup policy cấm |
| Shutdown/restart giữa job | DB/outbox integration | Job chưa hoàn thành có thể phục hồi theo policy |
| Feedback/bounce sau gửi | Provider webhook simulator/DSN fixture | Cập nhật delivery status, không nhầm với SMTP acceptance |

### 18.1. Kiểm tra Bcc

`Bcc` có tính chất đặc biệt: recipient thuộc envelope delivery nhưng header gửi đi không nên phơi bày danh sách Bcc. Khi dùng SMTP test sink, có thể cần kiểm tra cả:

- Recipient mà server nhận theo SMTP envelope.
- Header của message sau khi serialize.

Chỉ nhìn header `To` hoặc Web UI có thể không đủ chứng minh Bcc được xử lý đúng. Hãy dùng test server/harness cho phép quan sát envelope recipient và xác nhận không vô tình đưa Bcc thành `To`/`Cc`.

### 18.2. Test giới hạn dung lượng

Một email lớn có attachment có thể:

- Tốn bộ nhớ khi tạo MIME và encode.
- Bị SMTP server từ chối do giới hạn SIZE.
- Vượt timeout/đường truyền của ứng dụng.

Kiểm thử có thể dùng fixture kích thước vừa đủ và một môi trường giả lập có giới hạn định trước. Không tạo hàng trăm megabyte dữ liệu trong test chạy sau mỗi commit nếu chỉ cần kiểm tra một chính sách giới hạn; tách các bài performance/size test.

### 18.3. Kiểm thử TLS/AUTH khác với SMTP sink không bảo mật

Ở local, `mail.smtp.auth=false` và STARTTLS disabled là cấu hình tiện để test nội dung. Nó không chứng minh ứng dụng production sử dụng TLS an toàn.

Nếu yêu cầu tích hợp TLS/AUTH, hãy dùng:

- Fake SMTP server hỗ trợ AUTH/STARTTLS hoặc implicit TLS.
- Chứng chỉ test và truststore test riêng.
- Test xác nhận handshake thất bại khi server certificate không đáng tin.
- Test fail-closed nếu server không hỗ trợ STARTTLS nhưng client yêu cầu.
- Staging provider được cấp quyền và credential không dùng chung production.

**Không dùng `mail.smtp.ssl.trust=*` hoặc vô hiệu hóa hostname verification trong production** chỉ để test pass. Nếu dùng truststore tự ký trong test, cấu hình truststore test riêng và không đưa chính sách trust rộng sang môi trường thật.

## 19. Test slice và Spring Boot auto-configuration

Một lỗi hay gặp là viết unit test tự tạo `JavaMailSenderImpl` rồi cho rằng đã kiểm thử auto-configuration của Spring Boot.

Ví dụ:

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost(mailpit.getHost());
sender.setPort(mailpit.getMappedPort(1025));
~~~

Lời gọi này **không chứng minh** Spring đã bind `spring.mail.host`, `spring.mail.port` và các property SMTP như mong muốn.

Nếu muốn xác nhận cấu hình ứng dụng:

~~~java
@SpringBootTest
@Testcontainers
class MailAutoConfigurationIT {

    @Autowired
    JavaMailSender mailSender;

    // @Container + @DynamicPropertySource như phần trước.

    @Test
    void sendsUsingBootConfiguredSender() {
        // Sử dụng bean đã được Spring inject.
        // Assert kết quả trong SMTP sink qua test API.
    }
}
~~~

Kiểu test này có chi phí startup lớn hơn nhưng xác nhận **Spring container, bean selection, property binding và SMTP transport** cùng hoạt động.

### 19.1. Khi có nhiều JavaMailSender

Ứng dụng có thể cấu hình nhiều sender cho transactional, support hoặc marketing. Nếu có nhiều bean cùng kiểu, injection không có `@Qualifier` có thể bị mơ hồ; hoặc test gửi bằng sender không phải sender của nghiệp vụ đang kiểm tra.

Test cần xác định:

~~~java
@Autowired
@Qualifier("transactionalMailSender")
JavaMailSender transactionalSender;
~~~

Nếu cấu hình custom sender trong application, `spring.mail.*` có thể không tự động áp dụng lên bean tự tạo trừ khi code cấu hình đã bind nó. Test với bean thật giúp phát hiện nhầm lẫn giữa auto-configuration và cấu hình riêng.

### 19.2. Đường truyền fake không thay thế template test

Nếu Spring service dùng Thymeleaf/FreeMarker hoặc renderer riêng, test kết nối tới fake SMTP nên dùng **renderer thật** cho ít nhất một email mẫu. Nếu thay template engine bằng mock trong integration test, bài test không phát hiện key variable sai hoặc HTML render thất bại.

Tuy nhiên, test nội dung của từng template có thể nằm ở lớp riêng, không cần mỗi lần đều khởi động container. Giữ một vài bài end-to-end representative thay vì lặp lại toàn bộ test template trên SMTP container.

## 20. Hiệu năng và độ ổn định của test suite

Testcontainers giúp tái lập môi trường nhưng cũng tiêu thụ thời gian và tài nguyên. Một số cách tổ chức:

- Đặt nhóm integration test rõ ràng để CI có thể chạy sau unit tests.
- Dùng một container theo class hoặc một test fixture được quản lý có lifecycle rõ.
- Chỉ tạo database+SMTP combo cho các test cần ranh giới transaction thật.
- Tránh `Thread.sleep` dài; dùng readiness và Awaitility.
- Giới hạn timeout khởi động server/container theo môi trường CI.
- Dùng correlation ID để test có thể chạy lặp lại mà không đụng message cũ.
- Không tự động xóa mailbox giữa các test chạy song song.
- Sử dụng fixture nhỏ, deterministic và không chứa dữ liệu thật.
- Khi test thất bại, báo correlation ID/loại lỗi nhưng không in toàn bộ nội dung thư.

### 20.1. Không nên sử dụng container singleton toàn cục tùy tiện

Một container duy nhất cho cả test suite có thể giảm startup time nhưng cũng có thể gây:

- Message tồn đọng giữa các lớp.
- Cross-test interference khi chạy parallel.
- Spring context cache giữ host/port sai.
- Khó cleanup sau khi một lớp test fail.

Nếu chọn singleton, cần một test infrastructure rõ ràng về lifecycle, isolation và mapping context. Không xem bật `withReuse(true)` là cách sửa mặc định cho mọi bài test chậm.

### 20.2. Không nên kiểm thử bằng thời gian tuyệt đối

Ví dụ sau dễ flaky:

~~~java
assertThat(mailpitLastMessageReceivedAt())
        .isEqualTo(Instant.now());
~~~

Thời gian nhận có độ trễ, khác timezone/clock và độ chính xác. Tốt hơn:

- Assert message có correlation ID chính xác.
- Kiểm tra timestamp nằm trong một khoảng hợp lý nếu cần.
- Dùng `Clock` được inject cho logic deadline/retry.
- Dùng event/polling có timeout thay vì dựa vào số millisecond cố định.

## 21. Các câu hỏi thường gặp

**“Mock `JavaMailSender` đã đủ để kiểm thử gửi mail chưa?”**  
Đủ cho một số unit test về nghiệp vụ và số lần gọi, nhưng chưa xác nhận kết nối SMTP, MIME serialization hoặc server đã nhận đúng thư. Nên có ít nhất một integration test với fake SMTP cho đường gửi quan trọng.

**“Mailpit khác MailHog ở điểm nào?”**  
Cả hai có thể làm SMTP sink và cung cấp UI/API để quan sát message. Chúng khác về implementation, API, khả năng và vòng đời dự án. Hãy chọn công cụ phù hợp hạ tầng và dùng API của đúng phiên bản; không assume endpoint hoặc schema giống nhau.

**“GreenMail có cần Docker không?”**  
Khi chạy GreenMail in-process từ Java/JUnit, không cần Docker. GreenMail cũng có thể được chạy ở mô hình riêng/container tùy nhu cầu. Chọn artifact tương thích với Jakarta Mail/JavaMail của ứng dụng.

**“SMTP sink có gửi email tới Gmail hoặc Outlook thật không?”**  
Thông thường không; mục đích của sink là nhận và giữ mail trong môi trường test. Nếu thấy email thật rời khỏi hệ thống, cần kiểm tra ngay host/port và network policy vì test có thể đang dùng nhầm SMTP provider thật.

**“Testcontainers có cần docker-compose.yaml không?”**  
Không bắt buộc. Ví dụ `GenericContainer` có thể start trực tiếp từ image qua Testcontainers. Docker Compose phù hợp cho local development; Testcontainers phù hợp để JUnit quản lý lifecycle.

**“Tại sao container dùng port 1025 nhưng Spring phải dùng một port khác?”**  
`1025` là port bên trong container; Testcontainers expose nó ra một port host được cấp động. Ứng dụng test phải dùng `getMappedPort(1025)` và `getHost()`.

**“Có nên luôn dùng port cố định 1025 cho mọi test?”**  
Không nếu chạy nhiều test instance/container song song. Port động tránh conflict và thường phù hợp với CI hơn.

**“Spring Boot đọc host/port Testcontainers như thế nào?”**  
`@DynamicPropertySource` cung cấp property cho Spring test context trước khi bean được tạo. Có thể đăng ký `spring.mail.host` và `spring.mail.port` dựa trên container.

**“@ActiveProfiles(test) đã đủ để đảm bảo không gửi tới SMTP thật?”**  
Chưa. Environment variables hoặc các nguồn property khác có thể override test profile. Nên cấp host/port từ container và không cho CI integration job quyền sử dụng credential production.

**“Tại sao `send(...)` thành công nhưng test không thấy message?”**  
Có thể đang đọc nhầm server/API, subject filter không đúng, message bị giữ ở một container khác, hoặc thao tác async chưa hoàn tất. Dùng correlation ID duy nhất, timeout polling và kiểm tra mapped port.

**“Có nên dùng Thread.sleep để đợi email?”**  
Không nên làm cách chính. `Awaitility` hoặc cơ chế poll theo điều kiện có timeout thường ổn định hơn và nhanh hơn khi email tới sớm.

**“Mailpit nhận thư có nghĩa email đã được giao tới inbox thật chưa?”**  
Chưa. Nó chỉ xác nhận SMTP sink thử nghiệm nhận message. Deliverability thực tế còn phụ thuộc mail provider, DNS, reputation, spam filtering, server đích và cơ chế bounce.

**“Tại sao email HTML bị lỗi khi test chỉ đọc getContent().toString()?”**  
`MimeMessage.getContent()` có thể trả về `Multipart`. Cần duyệt MIME tree và giải mã đúng phần `text/html` hoặc `text/plain`.

**“Có cần so sánh toàn bộ raw MIME byte-for-byte không?”**  
Thông thường không. MIME boundary, Date và Message-ID có thể thay đổi hợp lệ. Hãy kiểm tra các thuộc tính và nội dung có ý nghĩa với nghiệp vụ.

**“Kiểm thử tiếng Việt qua SMTP nên assert gì?”**  
Kiểm tra subject và body **sau khi giải mã MIME**, bảo đảm dấu tiếng Việt và ký tự đặc biệt đúng. Không đòi raw wire format phải hiển thị Unicode nguyên văn vì message có thể dùng quoted-printable/base64.

**“GreenMail có thể lấy MimeMessage trực tiếp không?”**  
Có với API tương ứng của GreenMail, giúp test dễ assert subject/MIME tree. Phiên bản GreenMail cần tương thích Jakarta Mail trong ứng dụng.

**“Có thể dùng Mailpit mặc định để test lỗi SMTP 550 không?”**  
Không nên giả định. Một SMTP sink chủ yếu nhận thư; để test 4xx/5xx/auth/TLS có thể cần fake SMTP có khả năng script response, GreenMail được cấu hình phù hợp hoặc provider staging.

**“Có nên mock MailSendException để kiểm tra retry không?”**  
Có, khi mục tiêu là kiểm tra logic retry/backoff của ứng dụng. Nhưng mock không chứng minh server thật sẽ tạo đúng exception/cause trong một tình huống giao thức cụ thể.

**“Có thể dùng container SMTP để kiểm tra @Async không?”**  
Có. Gọi service async thật rồi poll server hoặc trạng thái outbox đến khi điều kiện được đáp ứng với timeout. Không mong đợi `@Async void` truyền exception trực tiếp trở lại test thread.

**“Outbox SENT có nghĩa thư đã vào inbox chưa?”**  
Nếu `SENT` được định nghĩa là SMTP submission thành công thì chưa. Trong integration test, nó chỉ chứng minh fake SMTP nhận message. Delivery/bounce status phải được theo dõi riêng.

**“Nên chạy Testcontainers ở mọi pull request không?”**  
Tùy chi phí và yêu cầu chất lượng. Thường hữu ích khi có một nhóm integration test trọng yếu chạy trong CI có container runtime, còn unit test chạy nhanh hơn ở mỗi lần thay đổi.

**“Có nên dùng image :latest?”**  
Trong CI cần khả năng tái lập, nên pin một tag/digest đã được nhóm xác minh. Có thể chủ động nâng cấp image theo lịch rồi chạy lại test.

**“Có cần login SMTP trên Mailpit local không?”**  
Một SMTP sink local cơ bản thường không yêu cầu SMTP AUTH. Nếu dùng `auth=false`, chỉ áp dụng cho môi trường test cô lập; production phải dùng chính sách xác thực và TLS của provider.

**“CI không có Docker thì làm sao?”**  
Tách nhóm Testcontainers sang runner khác, hoặc dùng GreenMail/Wiser in-process cho những bài test có thể đáp ứng được. Đừng tự fallback sang SMTP production.

**“Khi cần test bounce thì Mailpit có đủ không?”**  
Không nhất thiết. SMTP sink mặc định không giao Internet nên không mô phỏng toàn bộ bounce/DSN. Có thể dùng DSN fixtures, webhook simulator hoặc mail relay/provider staging có khả năng tạo phản hồi lỗi.

## 22. Checklist thiết kế và triển khai SMTP integration test

### Mục tiêu kiểm thử

1. Xác định bài test cần xác minh logic nghiệp vụ, MIME, SMTP acceptance hay provider deliverability.
2. Không dùng mock như bằng chứng SMTP server thật đã nhận message.
3. Chọn Mailpit/MailHog, GreenMail hoặc test server khác dựa trên tính năng thực sự cần.
4. Test ít nhất một happy path đi qua bean `JavaMailSender` thật của Spring.

### Cấu hình và môi trường

5. Sử dụng profile test/local tách khỏi production.
6. Không cấp SMTP production password cho test job.
7. Với Testcontainers, dùng `getHost()` và `getMappedPort(...)`.
8. Dùng `@DynamicPropertySource` hoặc một cơ chế test property tương đương trước khi Spring tạo sender.
9. Pin image/dependency version đã được kiểm chứng.
10. Chờ container readiness trước khi thực hiện assertion.
11. Không expose SMTP sink/API ra mạng công cộng.
12. Nếu Docker không khả dụng, fail/skip theo policy test rõ ràng, không gửi ra provider thật.

### Nội dung email

13. Kiểm tra recipient/From/Reply-To/subject đúng.
14. Kiểm tra Unicode/UTF-8 của subject và body sau khi decode MIME.
15. Nếu có HTML và plain text, xác nhận cả hai phiên bản.
16. Với attachment/inline resource, kiểm tra filename, media type, bytes và CID.
17. Dùng dữ liệu tổng hợp, token giả, không đưa PII production vào mailbox test.

### Tính lặp lại và độ tin cậy

18. Mỗi test có correlation ID hoặc subject/recipient duy nhất.
19. Dùng polling có timeout thay vì sleep cố định khi test asynchronous.
20. Không clear mailbox chung trong lúc test khác đang chạy.
21. Kiểm soát lifecycle container, Spring context cache và parallel execution.
22. Không assert raw MIME nguyên bytes nếu phần thay đổi như boundary/date không quan trọng.
23. Test transaction rollback/outbox theo commit boundary thực sự.
24. Tách SMTP synchronous failure, async job failure và database state-write failure.

### An toàn và vận hành

25. Có SMTP timeouts để test không treo vô hạn.
26. Không bật SMTP auth/debug logs chứa secret trong CI.
27. Không đưa raw email nhạy cảm vào test report/artifact.
28. Dừng/cleanup container sau test theo lifecycle phù hợp.
29. Có nhóm test riêng cho TLS/AUTH/provider-specific failure nếu yêu cầu.
30. Không coi test SMTP sink là bằng chứng SPF/DKIM/DMARC hay inbox delivery.

## 23. Sơ đồ quyết định chọn công cụ

~~~text
Cần kiểm thử gửi email?
            |
            v
Chỉ cần logic gọi send / dữ liệu truyền vào?
            |
      +-----+-----+
      |           |
     Có          Không
      |           |
      v           v
Mockito/mock   Cần MIME/charset/attachment?
                  |
            +-----+-----+
            |           |
           Có          Không
            |           |
            v           v
     MimeMessage     Cần SMTP network/protocol?
     test trực tiếp        |
                       +--+--+
                       |     |
                      Có    Không
                       |     |
                       v     v
                Fake SMTP    Unit test phù hợp
                       |
               +-------+--------+
               |                |
           Có Docker?        Không Docker?
               |                |
               v                v
      Mailpit/Testcontainers  GreenMail/Wiser
               |
               v
      Cần DB transaction/outbox?
               |
         +-----+-----+
         |           |
        Có          Không
         |           |
         v           v
   DB container +  SMTP container
   SMTP container  đơn lẻ
~~~

Đây là gợi ý chọn công cụ theo mục tiêu chính; GreenMail cũng có thể chạy qua container, và Mailpit có thể chạy dưới dạng process local. Không cần bó buộc một công cụ vào một hình thức triển khai duy nhất.

## 24. Tổng kết luồng kiểm thử Spring Framework Mail

Một kiến trúc kiểm thử cân đối có thể được tổ chức:

~~~text
                           Unit tests
                               |
               +---------------+----------------+
               |                                |
               v                                v
      Business logic + mock              MIME builder/renderer
      JavaMailSender call                charset / text / HTML
               |                                |
               +---------------+----------------+
                               |
                               v
                       Integration tests
                               |
                               v
                 Spring Boot JavaMailSender
                               |
                               v
                   SMTP fake/test container
                               |
                               v
                      Captured messages
                               |
                               v
                API/Java assertion with unique ID
                               |
                  +------------+------------+
                  |                         |
                  v                         v
           Message correctness      @Async/outbox/DB state
                  |                         |
                  +------------+------------+
                               |
                               v
                    Separate provider staging
                    when production-like TLS,
                    auth or deliverability is needed
~~~

**Các điểm cần nhớ:**

- **Mock sender** kiểm tra tương tác; **SMTP fake** kiểm tra đường truyền và message nhận được.
- **Mailpit/MailHog** tiện cho local và Testcontainers; **GreenMail** hữu ích khi cần API Java hoặc server in-process.
- Trong Testcontainers, dùng **mapped host/port động**, không hard-code cổng host.
- Với email HTML, attachment và tiếng Việt, kiểm tra **MIME sau khi giải mã**, không chỉ số lần gọi `send`.
- Với `@Async`, dùng **polling có timeout** và correlation ID; với outbox, kiểm tra cả transaction và trạng thái.
- **SMTP accepted không phải inbox delivered**; bounce/DSN và các đặc tính provider cần bài test riêng.
- Cách ly SMTP test khỏi Internet/credential production để tránh gửi nhầm và lộ dữ liệu.

## Kết luận

**Mail server giả lập hoặc SMTP test container** là thành phần quan trọng khi kiểm thử tích hợp Spring Framework Mail. Nó cho phép ứng dụng dùng `JavaMailSender` thật, thực hiện kết nối SMTP và kiểm tra thư thực tế được nhận trong một môi trường kiểm soát được. Nhờ đó, nhóm phát triển có thể phát hiện vấn đề cấu hình host/port, MIME, Unicode, attachment, async flow và outbox trước khi triển khai.

Thiết kế thực tế thường bắt đầu bằng **unit test với mock**, bổ sung **MIME test**, rồi dùng **Mailpit/Testcontainers hoặc GreenMail** cho các luồng gửi trọng yếu. Khi cần xác minh đặc tính của provider, TLS/AUTH hoặc deliverability, hãy có một lớp kiểm thử staging riêng được cấp quyền. Cách phân tầng này đem lại phản hồi nhanh, kết quả tái lập và giảm tối đa nguy cơ vô tình gửi email thật trong quá trình phát triển và CI.
