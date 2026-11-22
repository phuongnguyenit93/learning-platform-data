# Kiểm thử TLS và xác thực trong môi trường cô lập

Khi một ứng dụng Spring gửi email qua SMTP, tính đúng đắn không chỉ nằm ở nội dung thư hoặc việc **JavaMailSender.send(...)** trả về bình thường. Hệ thống còn phải bảo đảm rằng kết nối tới SMTP server thực sự sử dụng TLS khi được yêu cầu, chứng chỉ máy chủ được kiểm tra đúng, thông tin đăng nhập không bị chấp nhận sai và ứng dụng không âm thầm hạ cấp về kết nối không mã hóa khi cấu hình bảo mật bị thiếu.

Các hành vi đó cần được **kiểm thử tích hợp trong môi trường cô lập**: ứng dụng kết nối đến một SMTP server thử nghiệm do test kiểm soát, không kết nối tới tài khoản mail thật, không phụ thuộc Internet hoặc gửi email tới người nhận ngoài ý định. Bài học này tập trung vào cách xây dựng môi trường kiểm thử, phân biệt **STARTTLS** và **SMTPS (implicit TLS)**, kiểm thử xác thực SMTP AUTH, xác minh certificate trust/hostname, kiểm soát lỗi âm tính và thiết kế các test có tính lặp lại.

**Nguyên tắc cốt lõi:** Một test “đã gửi được thư” chưa chứng minh TLS hay xác thực đã được thực thi. Test phải cố tình cấu hình những trường hợp không an toàn và xác nhận rằng client hoặc server **từ chối** chúng.

## 1. Mục tiêu của kiểm thử tích hợp SMTP bảo mật

Unit test có thể mock **JavaMailSender** để kiểm tra service gọi send đúng một lần, đúng Subject và recipient. Nhưng mock không thể quan sát handshake TLS hay xác thực giao thức:

~~~text
Unit test
    OrderMailService
          |
          v
    Mock JavaMailSender
          |
          v
      verify(send)

Không có network, SMTP greeting, TLS handshake hay AUTH.
~~~

Integration test bảo mật cần chạy với transport thật:

~~~text
Spring service / JavaMailSenderImpl
                |
                | TCP qua loopback/container network
                v
       SMTP test server có kiểm soát
                |
          +-----+------+
          |            |
       STARTTLS       SMTP AUTH
          |            |
          v            v
     Certificate    Credentials/
     verification    auth policy
                |
                v
     Captured MIME message
~~~

Một bộ test tốt cần trả lời được:

1. Client có kết nối **đúng endpoint thử nghiệm**, không phải SMTP production?
2. Với STARTTLS, server có quảng bá STARTTLS và client có nâng cấp kết nối trước khi gửi thông tin nhạy cảm?
3. Nếu server không hỗ trợ STARTTLS nhưng policy yêu cầu TLS, thao tác có **thất bại**?
4. Chứng chỉ do CA thử nghiệm tin cậy có được chấp nhận?
5. Chứng chỉ không tin cậy, hết hạn hoặc sai hostname có bị từ chối?
6. Khi SMTP AUTH được yêu cầu, đúng credentials được chấp nhận và credentials sai bị từ chối?
7. Nếu server bắt buộc AUTH nhưng client không cấu hình AUTH, việc gửi có thất bại?
8. Nếu handshake hoặc AUTH thất bại, test server có nhận bất kỳ thông điệp nào không?
9. Các lỗi có bị ghi log theo cách làm lộ password, token hoặc nội dung email không?
10. Test có ổn định khi chạy lặp lại, chạy song song hoặc khi CI không có kết nối Internet?

## 2. Ba cấu hình SMTP phải phân biệt

Trong môi trường mail, cùng từ “SMTP TLS” có thể chỉ những cách kết nối khác nhau.

| Chế độ | Cách thiết lập | Cổng thường gặp | Thuộc tính Jakarta Mail trọng tâm |
| --- | --- | --- | --- |
| **SMTP không TLS** | Kết nối TCP thường, không nâng cấp TLS | 25 hoặc cổng thử nghiệm | Không bật ssl.enable/starttls |
| **SMTP + STARTTLS** | Kết nối SMTP thường rồi nâng cấp bằng lệnh STARTTLS | 587 | mail.smtp.starttls.enable, mail.smtp.starttls.required |
| **SMTPS / implicit TLS** | TLS handshake ngay khi mở socket, sau đó mới trao đổi SMTP | 465 | mail.smtp.ssl.enable |

Các cổng trong bảng là thông lệ triển khai, **không phải cơ chế bảo mật**. Test server có thể dùng cổng động bất kỳ. Bảo mật phụ thuộc vào giao thức thực sự được đàm phán và chính sách client, không phải việc gắn số 465 hoặc 587.

### STARTTLS

STARTTLS thường có luồng:

~~~text
Client                                  SMTP server
   |                                         |
   |-- TCP connect ------------------------->|
   |<----------------------- 220 greeting ---|
   |-- EHLO client.example ----------------->|
   |<----------------------- 250-STARTTLS ---|
   |-- STARTTLS ---------------------------->|
   |<----------------------- 220 Ready ------|
   |===== TLS handshake + cert verify ======|
   |-- EHLO lại trên kết nối TLS ---------->|
   |<----------------------- 250-AUTH -------|
   |-- AUTH ... ---------------------------->|
   |<----------------------- auth result ----|
   |-- MAIL FROM / RCPT TO / DATA --------->|
~~~

Lệnh SMTP trước TLS như greeting và lần EHLO ban đầu không được bảo mật bằng TLS. Sau STARTTLS, client thường EHLO lại để lấy khả năng mới được server công bố trên kênh mã hóa.

### Chỉ enable STARTTLS chưa đủ cho policy bắt buộc

Khi client cấu hình:

~~~properties
mail.smtp.starttls.enable=true
~~~

điều này cho phép sử dụng STARTTLS nếu server hỗ trợ. Nếu policy yêu cầu **không được gửi khi thiếu TLS**, phải thêm:

~~~properties
mail.smtp.starttls.required=true
~~~

Test âm tính quan trọng là kết nối tới server **không quảng bá STARTTLS** và xác nhận send thất bại thay vì âm thầm gửi không mã hóa.

### SMTPS / implicit TLS

Trong SMTPS, client khởi tạo TLS trước khi có SMTP greeting:

~~~text
Client                                      Server
   |                                          |
   |===== TLS handshake + cert verify =======|
   |<---------------------- 220 greeting -----|
   |-- EHLO --------------------------------->|
   |-- AUTH / MAIL FROM / DATA ... ---------->|
~~~

Đối với Jakarta Mail SMTP transport, **mail.smtp.ssl.enable=true** yêu cầu implicit TLS. Không cần đồng thời dùng STARTTLS như một thủ tục bắt buộc trên cùng kết nối.

### AUTH không phải TLS

**SMTP AUTH** xác nhận danh tính người gửi với server. **TLS** bảo vệ kênh truyền và xác minh máy chủ mà client kết nối. Một test xác thực thành công qua kết nối plaintext không chứng minh an toàn; nhiều cơ chế AUTH truyền credentials theo cách không phù hợp với mạng không được mã hóa.

Vì thế, cần tách hai nhóm kiểm thử:

- **Authentication correctness:** đúng/sai/missing credentials; cơ chế AUTH có được áp dụng?
- **Transport security:** TLS bắt buộc, certificate trust/hostname, không downgrade.

Sau đó có test kết hợp để chứng minh **AUTH chỉ được thực hiện theo chính sách TLS**.

## 3. Thuộc tính JavaMailSenderImpl cần kiểm thử

Spring Framework cung cấp **JavaMailSenderImpl** để cấu hình host, port, username, password và các thuộc tính của Jakarta Mail.

Ví dụ kết nối STARTTLS:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("localhost");
sender.setPort(1587);          // Cổng fixture, không phải production
sender.setUsername("mailer");
sender.setPassword("test-password");

Properties props = sender.getJavaMailProperties();
props.put("mail.transport.protocol", "smtp");
props.put("mail.smtp.auth", "true");
props.put("mail.smtp.starttls.enable", "true");
props.put("mail.smtp.starttls.required", "true");
props.put("mail.smtp.ssl.checkserveridentity", "true");
props.put("mail.smtp.connectiontimeout", "2000");
props.put("mail.smtp.timeout", "2000");
props.put("mail.smtp.writetimeout", "2000");
~~~

Đây là ví dụ cấu hình client. Để test kết nối thành công, fixture phải thật sự quảng bá STARTTLS, cung cấp certificate có tên phù hợp và được client tin cậy, và hỗ trợ cơ chế AUTH đã cấu hình.

### Ý nghĩa các thuộc tính

| Property | Ý nghĩa | Lưu ý khi test |
| --- | --- | --- |
| **mail.smtp.auth** | Client dùng SMTP AUTH | Server cần thực thi AUTH để test sai credentials có ý nghĩa |
| **mail.smtp.starttls.enable** | Cho phép nâng cấp STARTTLS | Một mình không phải chính sách fail-closed |
| **mail.smtp.starttls.required** | Bắt buộc STARTTLS khi dùng SMTP | Test server không hỗ trợ STARTTLS phải bị từ chối |
| **mail.smtp.ssl.enable** | Dùng TLS ngay từ đầu (implicit TLS) | Không nhầm với STARTTLS |
| **mail.smtp.ssl.checkserveridentity** | Kiểm tra danh tính hostname trong chứng chỉ | Không nên tắt để làm test xanh |
| **mail.smtp.ssl.protocols** | Giới hạn TLS protocol versions được phép | Chọn theo JDK/server thực tế, tránh giao thức lỗi thời |
| **mail.smtp.connectiontimeout** | Thời gian chờ mở kết nối | Tránh test kẹt lâu khi fixture không chạy |
| **mail.smtp.timeout** | Thời gian chờ đọc trên socket | Test server ngừng phản hồi sẽ thất bại có giới hạn |
| **mail.smtp.writetimeout** | Thời gian chờ ghi socket | Hữu ích khi server/network bị kẹt |
| **mail.debug** | Debug giao thức Jakarta Mail | Không bật tùy tiện vì có thể lộ thông tin nhạy cảm |

Các timeout trên tính bằng **mili giây**. Giá trị ví dụ 2000 ms chỉ phù hợp với một số môi trường CI; khi test trên máy quá tải có thể cần giới hạn điều chỉnh được. Không đặt timeout vô hạn nếu test phải thất bại có kiểm soát.

### Cấu hình Spring Boot tương ứng

~~~yaml
spring:
  mail:
    host: localhost
    port: 1587
    username: mailer
    password: test-password
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 2000
      mail.smtp.timeout: 2000
      mail.smtp.writetimeout: 2000
~~~

Không dùng những thông số test này cho production. Với Spring Boot, tính sẵn có của **JavaMailSender** còn phụ thuộc các dependency, mail configuration và auto-configuration đã được bật.

## 4. Nguyên tắc cô lập môi trường

Một SMTP integration test bảo mật nên có các đặc điểm:

1. **Chạy local/container:** SMTP server là fixture được start/stop bởi test hoặc CI.
2. **Không dùng credentials thật:** username/password là dữ liệu test và không có quyền gửi mail ngoài.
3. **Không gửi Internet:** cổng mạng và firewall/egress được hạn chế; server chỉ capture message hoặc giao thư trong hộp thư test.
4. **Cổng riêng hoặc cổng động:** tránh tranh chấp với server khác và các test chạy song song.
5. **Certificate test:** CA/server cert tạo riêng, không sử dụng khóa private của production.
6. **Dọn trạng thái:** reset mailbox/received messages, users và queues giữa các test.
7. **Timeout hữu hạn:** tránh CI treo nếu server không trả lời.
8. **Không tắt bảo mật để cho test qua:** không dùng trust-all/allow-any-credentials làm bằng chứng TLS/AUTH đúng.
9. **Có negative tests:** certificate sai, hostname sai, credentials sai và không có STARTTLS.
10. **Quan sát được:** test kiểm tra cả kết quả phía client và message được capture phía server.

### Sơ đồ network phù hợp

~~~text
Test JVM / Spring context
          |
          | TCP tới localhost:dynamicPort
          v
SMTP fixture
          |
          +-- Local test users
          +-- Test TLS keypair
          +-- Message capture
          +-- Protocol capability configuration
          |
          X Không relay tới Internet
~~~

Không thiết kế integration test bằng cách gửi email tới Gmail, Outlook hoặc SMTP provider thật rồi kiểm tra Inbox. Cách đó kém ổn định, tốn thời gian, phụ thuộc rate limit/network và dễ gây phát tán thư ngoài ý định.

## 5. Chọn công cụ test phù hợp

Các công cụ SMTP test có đặc điểm khác nhau. Không nên coi tất cả đều đủ khả năng kiểm chứng TLS và AUTH.

| Loại công cụ | Phù hợp kiểm tra | Giới hạn cần lưu ý |
| --- | --- | --- |
| **Mock JavaMailSender** | Service gọi API gửi, tạo MIME đúng | Không có SMTP/TLS/AUTH thực |
| **GreenMail** (embedded SMTP) | Gửi/nhận và quản lý test mailboxes; một số cấu hình hỗ trợ SSL/auth | Cần kiểm tra fixture thật sự enforce TLS/AUTH theo mục tiêu test |
| **Mailpit/MailHog** hoặc SMTP capture server | Bắt và xem message, API kiểm tra payload | Một cấu hình capture mặc định có thể nhận mail không AUTH hoặc không TLS |
| **SMTP server riêng trong container** | Chủ động policy STARTTLS, SMTPS, users và cert | Tốn công cấu hình, cần quản lý chứng chỉ |
| **Provider test/sandbox API** | Kiểm tra hợp đồng với nhà cung cấp cụ thể | Có thể phụ thuộc mạng, quota và tính năng sandbox, không cô lập tuyệt đối |

**GreenMail** là lựa chọn dễ bắt đầu cho integration tests trong JVM. Với những tình huống buộc phải kiểm tra **certificate chain/hostname verification, TLS downgrade hoặc cơ chế AUTH cụ thể**, có thể cần một fixture SMTP được cấu hình chặt hơn hoặc một server container do test quản lý.

Không dùng một SMTP capture server **mặc định chấp nhận mọi credential** để kết luận ứng dụng đã kiểm tra đúng SMTP AUTH. Test đó có thể xanh dù username hoặc password sai.

## 6. Ví dụ test SMTP AUTH bằng GreenMail

**GreenMail** là SMTP/IMAP/POP3 server phục vụ kiểm thử. Có thể nhúng nó vào JUnit 5 để gửi message qua socket và kiểm tra mailbox nhận được, không cần SMTP Internet.

Giả sử dự án dùng Spring Mail, Jakarta Mail, JUnit Jupiter và dependency GreenMail tương thích với phiên bản Spring đang dùng. Nhóm dependency GreenMail dành cho Jakarta cần được chọn đúng để tránh trộn **javax.mail** và **jakarta.mail** trong cùng test.

### Khởi động test server với cổng động

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.junit.jupiter.api.Assertions.*;

class SmtpAuthIntegrationTest {

    private GreenMail smtp;

    @BeforeEach
    void startServer() {
        smtp = new GreenMail(
                new ServerSetup(
                        0,
                        "127.0.0.1",
                        ServerSetup.PROTOCOL_SMTP
                )
        );
        smtp.start();
        smtp.setUser(
                "recipient@local.test",
                "recipient",
                "recipient-secret"
        );
        smtp.setUser(
                "mailer@local.test",
                "mailer",
                "mailer-secret"
        );
    }

    @AfterEach
    void stopServer() {
        if (smtp != null) {
            smtp.stop();
        }
    }

    private JavaMailSenderImpl sender(
            String username,
            String password
    ) {
        JavaMailSenderImpl result = new JavaMailSenderImpl();
        result.setHost("127.0.0.1");
        result.setPort(smtp.getSmtp().getPort());
        result.setUsername(username);
        result.setPassword(password);

        result.getJavaMailProperties().put(
                "mail.smtp.auth", "true"
        );
        result.getJavaMailProperties().put(
                "mail.smtp.connectiontimeout", "2000"
        );
        result.getJavaMailProperties().put(
                "mail.smtp.timeout", "2000"
        );
        result.getJavaMailProperties().put(
                "mail.smtp.writetimeout", "2000"
        );
        return result;
    }

    @Test
    void correctCredentialsCanSendMessage() throws Exception {
        JavaMailSenderImpl client =
                sender("mailer", "mailer-secret");

        MimeMessage message = client.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("mailer@local.test");
        helper.setTo("recipient@local.test");
        helper.setSubject("Kiểm thử SMTP AUTH");
        helper.setText("Thông điệp chỉ ở môi trường test.");

        client.send(message);

        assertTrue(smtp.waitForIncomingEmail(5000, 1));
        assertEquals(1, smtp.getReceivedMessages().length);
        assertEquals(
                "Kiểm thử SMTP AUTH",
                smtp.getReceivedMessages()[0].getSubject()
        );
    }

    @Test
    void wrongCredentialsAreRejected() {
        JavaMailSenderImpl client =
                sender("mailer", "wrong-password");

        assertThrows(
                MessagingException.class,
                client::testConnection
        );
        assertEquals(0, smtp.getReceivedMessages().length);
    }
}
~~~

Ví dụ trên chạy SMTP **chưa mã hóa trên loopback**, chỉ nhằm minh họa test xác thực độc lập. **Không gửi credentials thật qua SMTP plaintext** và không coi nó là test TLS. Mỗi test tạo fixture mới, dùng cổng động, tạo tài khoản thử nghiệm và dừng server trong **@AfterEach**.

**Điều kiện của bài test sai credentials:** fixture phải **thật sự yêu cầu SMTP AUTH và từ chối mật khẩu sai**. Nếu phiên bản/cấu hình GreenMail đang dùng cho phép relay không xác thực hoặc chấp nhận mọi credentials, test negative phải thất bại hoặc fixture cần cấu hình lại; không được coi một server permissive là bằng chứng hệ thống có kiểm soát AUTH. API và hành vi GreenMail có thể khác theo phiên bản, nên chọn dependency/test setup tương ứng với Jakarta Mail của dự án.

### Vì sao dùng testConnection() cho xác thực?

**JavaMailSenderImpl.testConnection()** thiết lập transport connection và thực hiện handshake/authentication theo cấu hình của client nhưng **không gửi một MIME message**. Nhờ vậy, test credentials sai có thể xác nhận lỗi mà không tạo email ngoài ý định.

Trong trường hợp cần kiểm tra toàn bộ quá trình SMTP submission, hãy dùng **send(...)** với test recipient và kiểm tra phía server. Cả hai loại test có vai trò khác nhau.

## 7. Kiểm thử AUTH không được chấp nhận khi thiếu credentials

Cần phân biệt hai hướng:

1. **Client yêu cầu auth** và cung cấp username/password.
2. **Server yêu cầu auth** trước khi cho phép gửi.

Một test chỉ đặt **mail.smtp.auth=true** ở client nhưng test server cho anonymous relay có thể che đi lỗ hổng cấu hình server.

### Ma trận AUTH cơ bản

| Cấu hình client | Chính sách server | Kết quả mong đợi |
| --- | --- | --- |
| Username/password đúng, AUTH bật | Yêu cầu AUTH | Kết nối thành công |
| Password sai, AUTH bật | Yêu cầu AUTH | Từ chối authentication |
| Username không tồn tại | Yêu cầu AUTH | Từ chối authentication |
| Không có username/password | Yêu cầu AUTH | Từ chối gửi hoặc connect ở bước được server yêu cầu |
| AUTH bị tắt ở client | Yêu cầu AUTH | Không relay mail được |
| Đúng credential nhưng thiếu TLS, server yêu cầu TLS trước AUTH | Bảo vệ credential bằng TLS | Không được gửi credential trên kênh plaintext |

Tình huống cuối cần fixture hỗ trợ TLS policy thật; không thể chứng minh bằng một capture SMTP server chỉ nhận thư mà không enforce STARTTLS.

### Không kiểm tra lỗi bằng một message cố định

Tùy thư viện/transport và giai đoạn lỗi, test có thể thấy **AuthenticationFailedException**, **MessagingException** hoặc một wrapper của Spring Mail. Không nên buộc mọi lỗi auth chỉ xuất hiện dưới một chuỗi message tiếng Anh cố định như “535 Authentication failed”.

Một test robust nên kiểm tra:

- Operation thất bại theo loại lỗi/nhóm lỗi phù hợp.
- Message không được server chấp nhận.
- Không có fallback sang anonymous relay.
- Credentials không xuất hiện trong log của test.

Nếu có mã phản hồi SMTP rõ ràng, có thể bổ sung assertion theo mã ở test dành riêng cho fixture đó.

## 8. Kiểm thử STARTTLS bắt buộc và chống downgrade

STARTTLS là trường hợp thường gặp nhất khi client kết nối cổng SMTP submission. Một điểm nhạy cảm: nếu **mail.smtp.starttls.enable=true** nhưng **mail.smtp.starttls.required** không được bật, client có thể tiếp tục qua plaintext khi server không quảng bá STARTTLS.

### Hai chế độ cần thử

~~~text
TEST A — SMTP server có STARTTLS
  SMTP greeting -> EHLO -> 250-STARTTLS
  -> TLS handshake
  -> authenticate
  -> send
  Expected: SUCCESS nếu certificate/credentials hợp lệ

TEST B — SMTP server không quảng bá STARTTLS
  SMTP greeting -> EHLO -> không có 250-STARTTLS
  -> client được cấu hình starttls.required=true
  Expected: FAIL, không gửi message
~~~

### Cấu hình fail-closed

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("localhost");
sender.setPort(smtpFixturePort);

sender.getJavaMailProperties().put(
        "mail.smtp.starttls.enable", "true"
);
sender.getJavaMailProperties().put(
        "mail.smtp.starttls.required", "true"
);
sender.getJavaMailProperties().put(
        "mail.smtp.ssl.checkserveridentity", "true"
);
~~~

### Mẫu integration test theo hợp đồng fixture

Giả sử test fixture có API khởi động chế độ SMTP hỗ trợ hoặc không hỗ trợ STARTTLS, test có thể tổ chức:

~~~java
@Test
void refusesServerWithoutStartTls() {
    // Fixture riêng do dự án triển khai:
    try (SmtpFixture fixture =
                 SmtpFixture.startWithoutStartTls()) {

        JavaMailSenderImpl client = senderFor(
                "localhost",
                fixture.port(),
                true  // require STARTTLS
        );

        assertThrows(
                Exception.class,
                client::testConnection
        );
        assertEquals(0, fixture.acceptedMessageCount());
    }
}
~~~

**SmtpFixture** và **senderFor** là lớp helper giả định của dự án, **không phải API có sẵn của Spring hay GreenMail**. Mẫu test diễn đạt yêu cầu thực thi: khi server không có STARTTLS, client phải thất bại. Implementation thực tế có thể dùng SMTP container chuyên dụng hoặc fixture nhúng có thể kiểm soát EHLO capabilities.

### Tại sao đây là test bảo mật thực sự?

Nếu bỏ thuộc tính required, hệ thống có thể vẫn gửi message tới SMTP server mặc dù policy muốn TLS. Test âm tính bắt được cấu hình fail-open trước khi triển khai. Một test chỉ gửi thành công qua server hỗ trợ STARTTLS sẽ không phát hiện việc client âm thầm chấp nhận plaintext trong môi trường khác.

### Lưu ý về STARTTLS stripping

Một kẻ tấn công có thể cố làm mất STARTTLS capability ở giai đoạn EHLO chưa mã hóa. Với client buộc **required=true**, việc không thấy STARTTLS phải dẫn tới **thất bại**. Kết hợp kiểm tra hostname/certificate sau khi nâng cấp TLS giúp giảm nguy cơ bị giả máy chủ.

Không nên kết luận đã chống được mọi hình thức MITM chỉ vì test một trường hợp EHLO thiếu STARTTLS. Tính an toàn còn phụ thuộc truststore, DNS, network, TLS implementation và cấu hình server.

## 9. Kiểm thử implicit TLS (SMTPS)

Trong chế độ implicit TLS, client phải bắt đầu bằng TLS handshake. Một client kết nối plaintext tới cổng implicit TLS hoặc ngược lại thường không thể giao tiếp đúng giao thức.

### Cấu hình client

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("localhost");
sender.setPort(smtpsFixturePort);
sender.setUsername("mailer");
sender.setPassword("test-password");

sender.getJavaMailProperties().put(
        "mail.smtp.ssl.enable", "true"
);
sender.getJavaMailProperties().put(
        "mail.smtp.ssl.checkserveridentity", "true"
);
sender.getJavaMailProperties().put(
        "mail.smtp.auth", "true"
);
~~~

### Các case cần thử

| Case | Fixture | Client | Kết quả |
| --- | --- | --- | --- |
| Implicit TLS hợp lệ | TLS server/cert đúng | ssl.enable=true, trust đúng | Kết nối và AUTH thành công |
| Chứng chỉ không tin cậy | TLS server/cert lạ | ssl.enable=true, trust mặc định | TLS handshake bị từ chối |
| Sai hostname | TLS server/cert đúng CA nhưng tên sai | checkserveridentity=true | Bị từ chối |
| Client không bật TLS | Server yêu cầu TLS ngay | ssl.enable=false | Giao thức không tương thích; không gửi được |
| TLS đúng nhưng password sai | Server enforce AUTH | ssl.enable=true, password sai | Authentication thất bại |

Không cần đặt đồng thời **mail.smtp.starttls.required=true** để thay thế **mail.smtp.ssl.enable=true**. Đó là hai flow giao thức khác nhau. Chọn chế độ theo server được kiểm thử.

## 10. Kiểm thử chứng chỉ và truststore

Một TLS test có ý nghĩa phải kiểm tra **chain of trust** và **hostname identity**, không chỉ mã hóa socket.

### Chứng chỉ thử nghiệm

Một fixture phù hợp có thể cung cấp:

- Server certificate chứa **Subject Alternative Name (SAN)** trùng hostname test, ví dụ **localhost**.
- Private key chỉ dùng trong fixture.
- Truststore phía client chứa test CA hoặc certificate được tin cậy.
- Cấu hình server dùng certificate đó trong STARTTLS hoặc implicit TLS.

Trong môi trường test, có thể tạo **self-signed certificate** hoặc test CA riêng. Self-signed không phải vấn đề nếu test client đã được cấu hình tin đúng certificate/CA; điều quan trọng là không bật cơ chế trust-all.

### Ví dụ tạo PKCS#12 bằng keytool

Những lệnh sau minh họa tạo một certificate dùng cho fixture local. Chạy trong môi trường test, **không chia sẻ private key/certificate production**.

~~~bash
keytool -genkeypair \
  -alias smtp-local \
  -keyalg RSA -keysize 3072 \
  -validity 7 \
  -storetype PKCS12 \
  -keystore smtp-server.p12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost"

keytool -exportcert \
  -alias smtp-local \
  -storetype PKCS12 \
  -keystore smtp-server.p12 \
  -storepass changeit \
  -rfc -file smtp-server.crt

keytool -importcert -noprompt \
  -alias smtp-local \
  -file smtp-server.crt \
  -storetype PKCS12 \
  -keystore smtp-client-trust.p12 \
  -storepass changeit
~~~

Các password **changeit** chỉ minh họa trong fixture cô lập. Không dùng password hard-code hoặc file private key thử nghiệm ở production. Một số công cụ/phiên bản Java có lựa chọn khác về key algorithms, PKCS#12 và cipher suites; điều chỉnh theo JDK đang dùng.

Vì SAN chứa **dns:localhost**, client kết nối bằng hostname **localhost** có thể khớp identity. Client kết nối bằng IP **127.0.0.1** không nhất thiết khớp certificate này: muốn hỗ trợ kết nối IP, certificate phải có SAN dạng IP tương ứng, hoặc test hostname mismatch một cách có chủ đích.

### Truststore không có nghĩa bỏ qua hostname validation

Hai bước khác nhau:

1. **Trust validation:** certificate chain có dẫn tới trust anchor được chấp nhận không?
2. **Identity validation:** certificate có đại diện cho hostname mà client đã định kết nối không?

Nếu một certificate tự ký được import vào truststore, nó có thể qua bước trust. Nhưng nếu SAN là **localhost** trong khi client kết nối **127.0.0.1**, hostname validation phải thất bại khi được bật.

### Không dùng trust-all để làm cho test xanh

Các cấu hình như:

~~~properties
mail.smtp.ssl.trust=*
mail.smtp.ssl.checkserveridentity=false
~~~

có thể làm giảm hoặc bỏ qua những kiểm tra TLS quan trọng. **Không dùng chúng để chứng minh TLS an toàn**. Trong một số môi trường local, người ta dùng trust-all để bắt message nhanh, nhưng đây không phải cấu hình phù hợp cho bài test chứng chỉ và không được sao chép sang production.

## 11. Cấu hình truststore riêng cho client thử nghiệm

Một cách nhanh là chạy test JVM với các JVM properties **javax.net.ssl.trustStore**, **javax.net.ssl.trustStorePassword** và **javax.net.ssl.trustStoreType**. Tuy nhiên, chúng ảnh hưởng tới TLS của **cả process** và có thể gây tương tác không mong muốn khi nhiều integration test chạy song song.

Đối với test cần cô lập từng client, có thể tạo **SSLSocketFactory** dùng đúng truststore thử nghiệm rồi cung cấp factory đó cho Jakarta Mail.

### Nạp truststore PKCS#12 bằng JSSE

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManagerFactory;

public final class SmtpTestTls {

    private SmtpTestTls() {
    }

    public static SSLSocketFactory socketFactory(
            Path truststorePath,
            char[] truststorePassword
    ) throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");

        try (InputStream input =
                     Files.newInputStream(truststorePath)) {
            trustStore.load(input, truststorePassword);
        }

        TrustManagerFactory trustManagerFactory =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm()
                );
        trustManagerFactory.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
                null,
                trustManagerFactory.getTrustManagers(),
                new SecureRandom()
        );
        return sslContext.getSocketFactory();
    }
}
~~~

Hàm trên dùng Java Secure Socket Extension (JSSE) để lấy trust managers dựa trên PKCS#12 mà test tạo. Nó **không** cài một trust manager chấp nhận mọi chứng chỉ. Chỉ certificate chain hợp lệ với truststore đó được chấp nhận theo chính sách của trust manager.

### Gắn socket factory vào JavaMailSenderImpl

~~~java
import javax.net.ssl.SSLSocketFactory;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpTestSenders {

    private SmtpTestSenders() {
    }

    public static JavaMailSenderImpl startTls(
            String hostname,
            int port,
            SSLSocketFactory sslSocketFactory
    ) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(hostname);
        sender.setPort(port);
        sender.setUsername("mailer");
        sender.setPassword("test-password");

        sender.getJavaMailProperties().put(
                "mail.smtp.auth", "true"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.starttls.enable", "true"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.starttls.required", "true"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.ssl.checkserveridentity", "true"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.ssl.socketFactory",
                sslSocketFactory
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.connectiontimeout", "2000"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.timeout", "2000"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.writetimeout", "2000"
        );
        return sender;
    }
}
~~~

Ở các phiên bản Jakarta Mail/Angus Mail hỗ trợ thuộc tính **mail.smtp.ssl.socketFactory** dưới dạng object, factory sẽ được dùng cho kết nối TLS. Khi sử dụng một version khác, cần xác nhận support và property name theo implementation đang chạy. **mail.smtp.ssl.checkserveridentity=true** phải tiếp tục được bật để truststore riêng không thay thế kiểm tra hostname.

Lợi ích của cách này là test có thể tạo nhiều client với các truststore khác nhau trong cùng JVM, không cần thay JVM-wide properties rồi gây ảnh hưởng lẫn nhau.

### Đừng gắn một global SSLSocketFactory tùy tiện

Các lời gọi như **SSLContext.setDefault(...)** hoặc thay truststore system properties tại runtime có thể tác động tới kết nối HTTPS/SMTP khác của ứng dụng và làm test phụ thuộc thứ tự chạy. Nếu dùng cấu hình toàn process, nên chạy những integration tests đó trong **JVM fork riêng** với startup options cố định.

## 12. Test positive/negative cho chứng chỉ

Một fixture TLS có thể tạo hai máy chủ logic:

- **Server A:** certificate được ký bởi test CA, SAN là localhost.
- **Server B:** certificate do một test CA khác ký, hoặc không nằm trong truststore client.

Khi đó, cùng một client kiểm tra được cả trust validation và hostname validation.

### Test chứng chỉ hợp lệ

~~~text
Fixture A:
  Hostname: localhost
  Certificate SAN: dns:localhost
  Client truststore: chứa test CA/certificate của A
  STARTTLS: advertised and required
  AUTH: đúng credentials

Expected:
  JavaMailSenderImpl.testConnection() thành công
~~~

### Test chứng chỉ không đáng tin

~~~text
Fixture B:
  Hostname: localhost
  Certificate SAN: dns:localhost
  Certificate CA: không nằm trong client truststore

Expected:
  TLS handshake bị từ chối
  Không gửi AUTH credentials hoặc MIME message
~~~

### Test sai hostname

~~~text
Fixture A:
  Bind address: 127.0.0.1
  Certificate SAN: dns:localhost (không có IP SAN)
  Client host: 127.0.0.1
  Client truststore: tin cậy certificate A
  checkserveridentity: true

Expected:
  Certificate chain được tin,
  nhưng identity check bị từ chối
~~~

Điểm quan trọng của test này: **đừng dùng cùng một lỗi để giả lập hai điều khác nhau**. Nếu truststore không chứa certificate thì test hostname mismatch có thể thất bại ở bước trust, chưa chứng minh hostname validation. Hãy cố ý tin certificate rồi thay hostname kết nối.

### Test chứng chỉ hết hạn

Một server certificate đã hết hạn phải không được chấp nhận, ngay cả khi certificate chain dẫn tới trust anchor đáng tin. Trong CI, có thể dùng fixture certificate với thời gian hiệu lực được tạo có chủ đích hoặc test TLS fixture hỗ trợ đưa certificate hết hạn vào handshake.

Tránh phụ thuộc vào một certificate tạm thời mà test “sẽ bắt đầu thất bại sau ba tháng”; test phải có input/fixture kiểm soát được và không phụ thuộc ngẫu nhiên vào ngày chạy.

### Test certificate khác sau khi đổi server

Thay fixture certificate nhưng giữ hostname và user credentials. Nếu client truststore chỉ tin certificate/CA cũ, kết nối phải thất bại. Test này phát hiện trường hợp code bất ngờ chuyển sang **trust-all** trong quá trình sửa cấu hình.

### Mẫu assert cho TLS failure

~~~java
JavaMailSenderImpl client = SmtpTestSenders.startTls(
        "127.0.0.1",
        tlsFixture.port(),
        trustedTestSocketFactory
);

assertThrows(Exception.class, client::testConnection);
assertEquals(0, tlsFixture.acceptedMessageCount());
~~~

Trong ví dụ trên, **tlsFixture** và **trustedTestSocketFactory** là fixture do dự án cấp; không có một biến toàn cục như vậy trong Spring. Khi viết test thực, nên assert nhóm exception gốc phù hợp, không chỉ **Exception.class**, và cung cấp failure message cho biết đang test trust hay hostname. Đoạn mã minh họa cấu trúc kiểm tra: lỗi TLS không được dẫn đến message được chấp nhận.

## 13. Đặt TLS protocol versions phù hợp

TLS 1.2 và TLS 1.3 là các phiên bản thường được dùng với JDK/server hiện đại. Có thể giới hạn protocol được phép:

~~~java
sender.getJavaMailProperties().put(
        "mail.smtp.ssl.protocols",
        "TLSv1.2 TLSv1.3"
);
~~~

Danh sách này chỉ minh họa; client/server/JDK phải hỗ trợ những phiên bản đó. Nếu production chỉ cho TLS 1.3, test fixture cũng phải hỗ trợ và cấu hình policy tương đương. Không ép một protocol chỉ vì nó được ghi trong bài mà không kiểm tra môi trường chạy.

### Một test chống protocol downgrade

~~~text
Client policy: chỉ TLSv1.2/TLSv1.3
Fixture: chỉ hỗ trợ protocol cũ không được client cho phép
Expected: handshake thất bại
~~~

Test tương ứng:

~~~text
Client policy: TLSv1.2/TLSv1.3
Fixture: hỗ trợ TLSv1.3, cert hợp lệ
Expected: handshake thành công
~~~

Trong điều kiện fixture hỗ trợ quan sát TLS session, ghi nhận **negotiated protocol** và cipher suite để xác nhận kết quả. Không cần in session secrets hoặc application data.

### Không chỉ kiểm tra có biểu tượng ổ khóa

Trong integration test Java, việc thành công với **ssl.enable=true** hoặc **starttls.required=true** là một phần bằng chứng. Muốn chứng minh phiên bản TLS và cipher đã đàm phán, cần dữ liệu từ TLS session hoặc instrumentation của fixture. Không suy ra TLS version chỉ từ cấu hình property của client.

## 14. SMTP AUTH trên kết nối TLS

Một test kết hợp quan trọng là server **chỉ cho phép AUTH sau khi TLS đã được thiết lập**.

Kịch bản mong muốn:

~~~text
Kết nối SMTP
    |
    v
EHLO -> STARTTLS capability
    |
    v
Client STARTTLS + verify cert/hostname
    |
    v
EHLO lại trên kênh mã hóa
    |
    v
Server advertise/accept AUTH
    |
    v
Credentials đúng
    |
    v
MAIL FROM / RCPT TO / DATA
~~~

### Những phép thử đáng có

| Test | Fixture | Kết quả mong đợi |
| --- | --- | --- |
| AUTH sau TLS, đúng password | Server yêu cầu TLS trước AUTH | Thành công |
| AUTH sau TLS, sai password | Server enforce AUTH | Thất bại |
| Không STARTTLS, có username/password | Server chỉ cho AUTH trên TLS | Bị từ chối; không gửi credentials qua plaintext |
| AUTH bị tắt ở client | Server bắt buộc AUTH | Không gửi message |
| Chứng chỉ không tin cậy, password đúng | TLS handshake thất bại | Không đi tới AUTH |
| Server chỉ quảng bá cơ chế AUTH không được client hỗ trợ/cho phép | Policy cơ chế không khớp | Thất bại có kiểm soát |

Với Jakarta Mail, có thể giới hạn các AUTH mechanisms khi cần:

~~~java
sender.getJavaMailProperties().put(
        "mail.smtp.auth.mechanisms",
        "PLAIN LOGIN"
);
~~~

**PLAIN** và **LOGIN** không nên được hiểu là an toàn trên plaintext. Chúng chỉ có thể phù hợp khi chạy trên một kênh TLS đã được xác minh đúng. Nếu provider dùng OAuth 2.0/XOAUTH2 hoặc cơ chế khác, test phải theo hợp đồng cụ thể của provider và implementation Jakarta Mail.

### Đừng dùng credentials production trong test

Với SMTP username/password hoặc OAuth token:

- Sinh tài khoản fixture riêng và không có quyền gửi Internet.
- Đưa password test vào cấu hình test-only, không vào artifact production.
- Nếu dùng provider sandbox, lấy secret từ CI secret store và giới hạn quyền.
- Không log câu lệnh AUTH hoặc token khi bật debug.
- Chủ động revoke/rotate credential test nếu có rò rỉ.

Một test auth bằng username đúng và password sai chỉ chứng minh server fixture từ chối credentials sai. Nó không chứng minh cấu hình production đang dùng SMTP AUTH nếu hệ thống production có một đường gửi khác.

## 15. Tích hợp với Spring Boot bằng @DynamicPropertySource

Khi cần kiểm thử một service sử dụng **JavaMailSender** được Spring Boot auto-configure, chỉ tạo JavaMailSenderImpl bằng new có thể bỏ qua lỗi binding properties. Một test chạy Spring context sẽ xác minh thêm rằng cấu hình **spring.mail.*** được áp vào sender thực tế.

Một server thử nghiệm dùng cổng động giúp không phải hard-code địa chỉ trên máy CI. **@DynamicPropertySource** cho phép đăng ký port/host được biết sau khi fixture start.

### Ví dụ kiểm thử wiring tới GreenMail

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class SpringMailWiringIntegrationTest {

    private static final GreenMail SMTP = new GreenMail(
            new ServerSetup(
                    0,
                    "127.0.0.1",
                    ServerSetup.PROTOCOL_SMTP
            )
    );

    static {
        SMTP.start();
        SMTP.setUser(
                "recipient@local.test",
                "recipient",
                "recipient-secret"
        );
        SMTP.setUser(
                "mailer@local.test",
                "mailer",
                "mailer-secret"
        );
    }

    @DynamicPropertySource
    static void smtpProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.mail.host", () -> "127.0.0.1");
        registry.add(
                "spring.mail.port",
                () -> SMTP.getSmtp().getPort()
        );
        registry.add("spring.mail.username", () -> "mailer");
        registry.add(
                "spring.mail.password",
                () -> "mailer-secret"
        );
        registry.add(
                "spring.mail.properties.mail.smtp.auth",
                () -> "true"
        );
        registry.add(
                "spring.mail.properties.mail.smtp.connectiontimeout",
                () -> "2000"
        );
        registry.add(
                "spring.mail.properties.mail.smtp.timeout",
                () -> "2000"
        );
    }

    @Autowired
    private JavaMailSender mailSender;

    @Test
    void springBeanSendsToIsolatedServer() throws Exception {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("mailer@local.test");
        helper.setTo("recipient@local.test");
        helper.setSubject("Mail context test");
        helper.setText("Nội dung trong môi trường cô lập.");

        mailSender.send(message);

        assertTrue(SMTP.waitForIncomingEmail(5000, 1));
        assertEquals(1, SMTP.getReceivedMessages().length);
    }

    @AfterAll
    static void stopServer() {
        SMTP.stop();
    }
}
~~~

Đây là bài kiểm tra **Spring context wiring và SMTP AUTH qua loopback**, chưa phải test STARTTLS. Để kiểm thử TLS, thay fixture bằng SMTP server cung cấp certificate/STARTTLS và đăng ký thêm các thuộc tính TLS theo mục tiêu test. Trong môi trường production, Spring Boot mail properties phải đến từ cấu hình deployment/secret store, không lấy từ fixture.

### Chọn profile cho integration test

Một profile thử nghiệm có thể đặt:

~~~yaml
# application-it.yml
spring:
  mail:
    host: localhost
    username: mailer
    password: local-test-secret
    properties:
      mail.smtp.connectiontimeout: 2000
      mail.smtp.timeout: 2000
      mail.smtp.writetimeout: 2000
~~~

Trong integration test, **@DynamicPropertySource** vẫn có thể ghi đè host/port và những property khác để trỏ đúng fixture. Không nên có một file test profile vô tình chứa host SMTP production làm giá trị fallback.

### Vòng đời fixture và chạy song song

Nếu mỗi test class quản lý SMTP server riêng, cần:

- Tạo server trước khi Spring context khởi tạo MailSender.
- Đăng ký port sau khi server đã bind.
- Dừng server khi test suite/class kết thúc.
- Tránh chia sẻ cổng cố định giữa các test đang chạy song song.
- Không để mailbox/received messages từ test khác ảnh hưởng assertion.
- Nếu dùng static fixture với Spring context caching, bảo đảm lifecycle của fixture không ngắn hơn thời gian context tái sử dụng.

Một lựa chọn khác là sử dụng JUnit 5 extension phù hợp với GreenMail hoặc Testcontainers lifecycle để giảm boilerplate. Khi chọn extension, cần xác nhận phiên bản tương thích với JUnit/Spring/Jakarta Mail.

## 16. Kiểm thử SSL certificate với Spring context

Với test TLS, cấu hình trong Spring Boot có thể bật:

~~~yaml
spring:
  mail:
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
~~~

Việc **bật các property** là điều kiện cần, nhưng không đủ để chứng minh TLS được thực thi. Test còn phải xác nhận:

1. Fixture thực sự quảng bá và triển khai STARTTLS.
2. Client nhận và kiểm tra certificate từ fixture.
3. AUTH diễn ra sau TLS theo policy.
4. Cấu hình sai certificate/hostname làm thao tác thất bại.
5. Không có plaintext fallback.

### Tách client policy khỏi transport implementation

Một thiết kế dễ test là có lớp cấu hình mail riêng hoặc **JavaMailSenderImpl** được Spring quản lý, cho phép injection một test-specific socket factory/truststore **chỉ ở test profile**. Không nên viết code nhúng truststore test vào main application hoặc tự động bật trust-all nếu chạy dưới profile test.

### Lưu ý về properties và placeholder

Nếu ứng dụng sử dụng profile-specific properties, chắc chắn **hostname trong certificate** tương ứng với hostname được resolve khi test. Trong Docker/Testcontainers, client có thể kết nối qua **localhost** (port được map) hoặc hostname trong Docker network. Certificate SAN phải phù hợp với hostname **mà client thấy**, không phải hostname nội bộ được ghi cho tiện.

Ví dụ test từ JVM host qua mapped port **localhost** nên dùng certificate chứa SAN **localhost**. Nếu test chạy trong container A và kết nối tới service tên **smtp** trong cùng network, certificate có thể cần SAN **smtp**. Không sửa test bằng cách tắt checkserveridentity khi gặp lỗi mismatch.

## 17. Kiểm thử server không rò rỉ AUTH trên plaintext

Để kiểm tra chính sách “chỉ AUTH sau TLS”, một fixture SMTP lý tưởng cần kiểm soát:

- Những EHLO capabilities được quảng bá trước STARTTLS.
- Những capabilities được quảng bá sau STARTTLS.
- Việc cho/không cho phép AUTH khi connection chưa được mã hóa.
- Kết quả của AUTH sai/đúng.

Một luồng test:

~~~text
Client A:
  auth=true
  starttls.enable=true
  starttls.required=true
  certificate trusted
Expected:
  TLS established
  then AUTH success
  then message accepted

Client B:
  auth=true
  starttls.enable=false
Expected:
  No successful submission
  No authentication secret accepted in plaintext
~~~

Nếu fixture ghi protocol transcript để xác nhận thứ tự, transcript đó có thể chứa sensitive AUTH data. Hãy cấu hình test logger **redact credentials** hoặc chỉ ghi các sự kiện trạng thái như “TLS_UPGRADED”, “AUTH_ATTEMPTED”, “AUTH_SUCCEEDED”; không in raw base64/auth payload.

### Không dựa vào thuộc tính debug làm chứng cứ duy nhất

Một số người bật **mail.debug=true** để thấy EHLO/STARTTLS/AUTH. Log hữu ích nhưng dễ chứa dữ liệu không mong muốn và có thể khác theo Jakarta Mail implementation. Bài test nên khẳng định outcome bằng server fixture và client exception; protocol logging chỉ là công cụ hỗ trợ khi điều tra.

### AUTH mechanism không quyết định sender authorization

Ngay cả khi AUTH thành công, server có thể có chính sách chỉ cho tài khoản mailer gửi bằng địa chỉ From được phép. Nếu fixture hỗ trợ sender authorization, nên thử:

- AUTH với user hợp lệ, From được cho phép: accepted.
- AUTH với user hợp lệ nhưng From giả mạo user khác: rejected theo fixture policy.

Test này khác với việc kiểm tra **SMTP AUTH**. Một server có thể xác thực đúng username/password nhưng không kiểm tra địa chỉ From, và những rủi ro giả mạo vẫn tồn tại. Với provider production, nên kiểm tra cả sender identities đã được xác minh và chính sách From/envelope.

## 18. Không gửi email thật khi test thất bại

Test âm tính dễ vô tình gây network leakage nếu client rơi về cấu hình mặc định hoặc test code tự động retry qua SMTP provider thật.

Các biện pháp quan trọng:

1. **Không để production host là fallback** trong application-it/test properties.
2. **Không dùng credential sản xuất** trong CI hoặc local test.
3. **Chặn egress SMTP** ra Internet ở môi trường test nếu hạ tầng cho phép.
4. Dùng recipient thuộc domain thử nghiệm/fixture, không dùng mailbox thật.
5. Kiểm tra host/port thực tế của bean JavaMailSender được inject.
6. Reset caches/sessions khi đổi cấu hình sender giữa các test.
7. Không thiết kế retry worker tự tìm transport khác nếu fixture tạm thời lỗi.
8. Khi fixture không start được, **fail test** thay vì chạy bằng cấu hình mặc định.

### Có thể assert host/port của JavaMailSenderImpl

~~~java
import org.springframework.mail.javamail.JavaMailSenderImpl;

JavaMailSenderImpl implementation =
        (JavaMailSenderImpl) mailSender;

assertEquals("127.0.0.1", implementation.getHost());
assertEquals(
        SMTP.getSmtp().getPort(),
        implementation.getPort()
);
~~~

Đoạn cast chỉ dùng khi Spring context thực sự inject **JavaMailSenderImpl**. Nếu bean là một decorator/proxy tùy biến, test nên kiểm tra cấu hình qua interface/fixture hoặc một diagnostic adapter phù hợp thay vì cast mù.

### SMTP capture server không được relay ra ngoài

Một container MTA cấu hình sai có thể trở thành open relay hoặc gửi thư test ra Internet. Chỉ expose cổng tới test network, không công bố public endpoint và chủ động tắt relay. Với Docker Compose/Testcontainers, ưu tiên network cô lập và chỉ map những cổng test cần.

## 19. Kiểm thử message vẫn đúng sau TLS/AUTH

TLS và AUTH là điều kiện về transport, nhưng trong cùng integration test có thể kiểm tra rằng message được nộp đúng nội dung. Điều này giúp phát hiện lỗi cấu hình encoding/multipart khi chuyển từ SMTP không TLS sang server TLS thực.

Ví dụ với **GreenMail** hoặc SMTP fixture có capture:

~~~java
MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("mailer@local.test");
helper.setTo("recipient@local.test");
helper.setSubject("Xác nhận đơn hàng có dấu");
helper.setText(
        "Đơn hàng đã xác nhận.",
        "<p>Đơn hàng <strong>đã xác nhận</strong>.</p>"
);

sender.send(message);

MimeMessage received = fixture.receivedMessages()[0];
assertEquals(
        "Xác nhận đơn hàng có dấu",
        received.getSubject()
);
assertTrue(received.isMimeType("multipart/*"));
~~~

**fixture.receivedMessages()** ở đây là API adapter do test xây dựng, không phải phương thức có sẵn trên Spring JavaMailSender. Với GreenMail, có thể dùng **greenMail.getReceivedMessages()**.

### Vì sao không so sánh toàn bộ raw MIME?

Một **MimeMessage** sau khi được serialize có thể có Message-ID, Date, MIME boundaries, header folding và transfer encoding được tạo bởi thư viện. Những chi tiết này có thể thay đổi hợp lệ. Nên kiểm tra các thuộc tính có nghĩa:

- From và recipient đúng.
- Subject được decode đúng Unicode.
- Text/plain và text/html có nội dung phù hợp.
- Inline images/attachments đúng Content-Type và Content-Disposition.
- Không xuất hiện recipient ngoài ý định.

Đừng coi thay đổi một MIME boundary hay transfer encoding là lỗi TLS. Việc nộp message và việc bảo vệ transport là hai nhóm kiểm tra khác nhau.

### “Server captured” chưa phải “Delivered”

Nếu GreenMail hoặc fixture nhận được message, test chỉ chứng minh SMTP submission tới server thử nghiệm. Nó không chứng minh khả năng vào Inbox của provider thực, DKIM/SPF/DMARC, spam filtering hoặc delivery webhook. Những việc đó thuộc các lớp kiểm thử khác.

## 20. Test các trường hợp lỗi và fail-closed behavior

Một bộ kiểm thử TLS/AUTH nên có **cả happy path và negative path**. Các trường hợp negative có giá trị cao vì phát hiện việc bảo mật bị vô hiệu khi sửa cấu hình.

### Ma trận tối thiểu

| Mã test | Điều kiện | Kết quả bắt buộc |
| --- | --- | --- |
| **TLS-01** | STARTTLS, certificate hợp lệ, hostname đúng | Kết nối thành công |
| **TLS-02** | Client yêu cầu STARTTLS, server không hỗ trợ | Fail, không gửi |
| **TLS-03** | Certificate không tin cậy | Fail, không AUTH/send |
| **TLS-04** | Certificate có hostname không khớp | Fail |
| **TLS-05** | Chỉ có TLS protocol bị policy cấm | Handshake fail |
| **TLS-06** | SMTPS client tới SMTPS server, cert đúng | Kết nối thành công |
| **TLS-07** | Plain SMTP client tới server implicit TLS | Fail, không gửi |
| **AUTH-01** | TLS đúng, credentials đúng | Authenticate thành công |
| **AUTH-02** | TLS đúng, password sai | Authenticate bị từ chối |
| **AUTH-03** | TLS đúng, username không tồn tại | Authenticate bị từ chối |
| **AUTH-04** | Server yêu cầu AUTH, client không cấu hình | Không gửi được |
| **AUTH-05** | Server yêu cầu TLS trước AUTH, client không TLS | Không gửi credential thành công trên plaintext |
| **SEC-01** | Host SMTP của Spring bean khác fixture | Test fail trước khi phát thư |
| **SEC-02** | Lỗi handshake/auth | Không có message trong mailbox capture |
| **SEC-03** | Bật negative test | Logs không chứa password hoặc token |

Không nhất thiết một lớp test chạy hết ma trận. Có thể tách thành:

1. **Fast SMTP integration tests:** GreenMail/capture server, verify message và AUTH cơ bản.
2. **Transport security integration tests:** container/fixture có certificate, STARTTLS và implicit TLS.
3. **Provider contract tests:** sandbox hoặc môi trường thử nghiệm của provider, nếu có yêu cầu đặc thù.

### Một test chỉ có assertThrows chưa đủ

Ví dụ:

~~~java
assertThrows(Exception.class, client::testConnection);
~~~

Lỗi có thể do fixture **chưa start**, port sai hoặc DNS không resolve, chứ không phải do certificate mismatch mà test muốn kiểm chứng.

Để phân biệt nguyên nhân, test nên xác nhận:

- Fixture đã start và đang lắng nghe.
- Certificate và hostname được cấu hình theo kịch bản.
- Client kết nối đúng fixture port.
- Exception chain phản ánh failure tương ứng, ví dụ SSLHandshakeException hoặc certificate identity validation.
- Không có accepted message phía server.

Điều này giúp test âm tính không “xanh giả” vì một lỗi setup không liên quan.

### Assertion theo root cause

Trong Spring Mail, lỗi network/Jakarta Mail có thể được wrap trong **MailException**. Một helper test có thể duyệt cause chain:

~~~java
public static boolean hasCause(
        Throwable error,
        Class<? extends Throwable> expectedType
) {
    Throwable current = error;
    while (current != null) {
        if (expectedType.isInstance(current)) {
            return true;
        }
        current = current.getCause();
    }
    return false;
}
~~~

Với một fixture gây **SSLHandshakeException**, test có thể dùng helper để xác định lỗi TLS nằm trong cause chain nếu transport implementation giữ nguyên cause tương ứng. Tuy nhiên, không nên tạo một assertion quá phụ thuộc vào thông điệp lỗi hay cấu trúc cause cụ thể khi version/provider thay đổi.

## 21. Kiểm thử timeout và phản hồi lỗi có giới hạn

TLS handshake và SMTP AUTH có thể bị kẹt khi server ngừng phản hồi. Một môi trường CI đáng tin cậy phải có timeout ở cả network client và test runner.

### Các trường hợp nên có

~~~text
CASE A: server không nghe cổng
  -> connection refused/timeout nhanh, không retry vô hạn

CASE B: server nhận TCP nhưng không gửi greeting
  -> read timeout

CASE C: server quảng bá STARTTLS rồi không hoàn tất handshake
  -> handshake/read timeout

CASE D: TLS thành công nhưng server không phản hồi AUTH
  -> read timeout
~~~

Cấu hình:

~~~java
sender.getJavaMailProperties().put(
        "mail.smtp.connectiontimeout", "2000"
);
sender.getJavaMailProperties().put(
        "mail.smtp.timeout", "2000"
);
sender.getJavaMailProperties().put(
        "mail.smtp.writetimeout", "2000"
);
~~~

JUnit còn có thể giới hạn thời gian kiểm thử:

~~~java
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;

assertTimeoutPreemptively(
        Duration.ofSeconds(10),
        () -> client.testConnection()
);
~~~

**Lưu ý:** assertTimeoutPreemptively chạy phần kiểm tra trong thread khác; nếu test đang dựa vào transaction context, Spring TestContext ThreadLocal hoặc cấu hình thread-bound, hãy cân nhắc dùng **assertTimeout** hoặc deadline của runner thay vì preemptive timeout. Việc cắt một thread cũng không thay thế socket timeouts thực tế.

### Timeout không chứng minh server đã từ chối

Khi gửi email thật, read timeout có thể xảy ra sau khi SMTP server đã nhận message nhưng client không nhận được phản hồi cuối. Trong bài test tập trung TLS/AUTH, dùng **testConnection()** để kiểm tra handshake/auth không tạo message; trong bài test SMTP submission, cần phân biệt **accepted**, **rejected** và **unknown outcome** khi kiểm tra retry.

Không tự retry vô hạn một lần gửi MIME chỉ vì exception network; nó có thể tạo email trùng nếu server đã chấp nhận.

## 22. Isolation khi dùng Testcontainers hoặc Docker

Với những test certificate policy chi tiết, một SMTP server chạy trong container thường dễ cấu hình hơn một server nhúng đơn giản:

~~~text
Test runner / JUnit
       |
       v
Start SMTP test container
       |
       +-- Test users
       +-- Test certificate/key
       +-- STARTTLS / SMTPS policy
       +-- AUTH required policy
       +-- Local captured mailbox
       |
       v
Read mapped host/port
       |
       v
Inject Spring mail properties
       |
       v
Run tests and inspect server evidence
       |
       v
Stop/remove container
~~~

### Cấu hình container cần kiểm soát

- **Port mapping:** cổng động hoặc cổng dành riêng; test lấy port thực tế sau khi container ready.
- **Wait strategy:** chờ server thực sự có thể chấp nhận kết nối; không chỉ kiểm tra process đang chạy.
- **TLS material:** chỉ mount certificate/private key test vào container, đặt quyền file phù hợp.
- **Network egress:** không relay ra Internet; chỉ trao đổi giữa test JVM và fixture.
- **Auth config:** user/password test, server không cho anonymous relay khi muốn kiểm tra AUTH.
- **Certificate SAN:** khớp hostname client sử dụng qua mapped port hoặc Docker network.
- **Mailbox reset:** mỗi test hoặc test class có trạng thái sạch.
- **Resource cleanup:** đảm bảo container dừng sau suite, kể cả khi test thất bại.

### Đừng dựa vào image tag floating

Để test ổn định, pin image version hoặc digest theo chính sách dự án. Nếu cứ dùng tag latest, nhà cung cấp image có thể thay đổi TLS defaults, AUTH behavior hoặc cổng được expose và gây thất bại không liên quan tới code.

Không có một Docker image SMTP duy nhất được giả định là hỗ trợ mọi tình huống TLS/AUTH. Chọn image/server được dự án kiểm soát và xác minh capabilities của fixture.

### Testcontainers không tự làm TLS test bảo mật

Một container chỉ chạy một SMTP catcher accepting-all có thể nhận được email và giúp kiểm tra nội dung, nhưng không chứng minh certificate validation, server identity hay AUTH enforcement. Môi trường test cần được **cấu hình cố ý để có thể từ chối cấu hình sai**.

## 23. Tách kiểm thử TLS khỏi kiểm thử logic gửi email

Một hệ thống có thể có cấu trúc:

~~~text
OrderService
    |
    v
OrderMailComposer
    |
    v
JavaMailSender
    |
    v
SMTP transport
~~~

Không cần mọi test ở OrderService đều khởi động TLS fixture. Chiến lược kiểm thử nhiều lớp giúp nhanh và chính xác hơn:

| Lớp | Mục tiêu | Công cụ |
| --- | --- | --- |
| **Unit test nghiệp vụ** | Có tạo thông báo khi đúng nghiệp vụ? | Mock mail port, JUnit/Mockito |
| **MIME composition test** | Header, address, multipart, encoding đúng? | Jakarta Mail parser, captured MIME |
| **SMTP integration test** | Có nộp message tới local fixture? | GreenMail/SMTP capture |
| **TLS/AUTH integration test** | Client và server enforce policy? | Fixture TLS/AUTH thật |
| **Provider contract test** | Provider cụ thể có nhận đúng configuration? | Sandbox/API test có kiểm soát |
| **Delivery/operational test** | Webhook, bounce, reputation, routing | Test environment chuyên dụng |

Một test fail vì certificate mismatch phải phản ánh lỗi bảo mật transport, không bị che bởi logic template. Ngược lại, một unit test subject không cần thực hiện TLS handshake qua network.

### Một số test nên chạy trong mỗi CI build

Test nhanh có thể bao gồm:

- Compose MIME message đúng.
- GreenMail local SMTP AUTH và kiểm tra sai password.
- Một STARTTLS positive/negative path với fixture nhanh.

Những test nặng hơn như nhiều protocol versions, expired certificate và provider sandbox có thể chạy trong pipeline bảo mật hoặc integration stage riêng. Tuy vậy, nếu ứng dụng thay đổi cấu hình TLS trực tiếp, nên có test transport security tương ứng trong điều kiện bắt buộc trước khi release.

## 24. Những lỗi thường gặp khi kiểm thử TLS/AUTH

### Lỗi 1 — Chỉ kiểm tra gửi mail thành công

Test thấy **greenMail.getReceivedMessages()** có một email và kết luận “TLS và AUTH hoạt động”.

**Vấn đề:** SMTP catcher có thể chấp nhận plaintext hoặc anonymous relay. Gửi thành công không chứng minh bảo mật.

**Cách xử lý:** có test riêng cho STARTTLS required, certificate identity và wrong credentials.

### Lỗi 2 — Có starttls.enable nhưng thiếu starttls.required

Một số server không quảng bá STARTTLS; client vẫn có thể cố tiếp tục theo cấu hình cho phép downgrade.

**Cách xử lý:** với chính sách bắt buộc TLS, đặt **mail.smtp.starttls.required=true**, test server không có STARTTLS và xác nhận fail-closed.

### Lỗi 3 — Tắt hostname verification để sửa certificate error

~~~properties
mail.smtp.ssl.checkserveridentity=false
~~~

**Vấn đề:** kết nối có thể được mã hóa nhưng client không xác minh server có đúng tên được yêu cầu không.

**Cách xử lý:** tạo certificate có SAN khớp hostname test, bật **checkserveridentity=true** và kiểm tra sai hostname bị từ chối.

### Lỗi 4 — Dùng trust-all trong test bảo mật

~~~properties
mail.smtp.ssl.trust=*
~~~

**Vấn đề:** test không còn khả năng phát hiện chứng chỉ giả/không được tin cậy.

**Cách xử lý:** dùng CA/cert test riêng với truststore có giới hạn.

### Lỗi 5 — Dùng SMTP server cho phép mọi password

Test username/password sai vẫn gửi được vì server capture không enforce AUTH.

**Cách xử lý:** chọn fixture yêu cầu xác thực thật và bắt buộc kiểm tra negative case trước khi dùng nó để đánh giá auth.

### Lỗi 6 — Tạo certificate SAN khác hostname thực

Fixture có SAN **smtp-test**, nhưng test JVM kết nối tới **localhost** qua mapped port.

**Vấn đề:** hostname verification thất bại mặc dù certificate thuộc test CA.

**Cách xử lý:** cấp certificate khớp hostname mà client thực sự gọi, không vô hiệu hóa identity check.

### Lỗi 7 — Trộn STARTTLS với implicit TLS

Client cấu hình SSL ngay khi mở socket vào SMTP server chỉ hỗ trợ nâng cấp bằng STARTTLS.

**Vấn đề:** client/server chờ những byte giao thức khác nhau, dẫn tới handshake failure hoặc timeout.

**Cách xử lý:** chọn đúng **mail.smtp.ssl.enable** cho SMTPS, hoặc **starttls.enable + required** cho STARTTLS.

### Lỗi 8 — Dùng chung truststore global giữa các test song song

Test A thay **javax.net.ssl.trustStore**, trong lúc test B đang mở kết nối TLS.

**Vấn đề:** test trở nên phụ thuộc thứ tự và state toàn process.

**Cách xử lý:** truyền SSLSocketFactory riêng, hoặc chạy từng nhóm test trong JVM fork riêng.

### Lỗi 9 — Dùng certificate sắp hết hạn làm fixture

Test đột ngột thất bại sau một thời gian dù code không đổi.

**Cách xử lý:** tự tạo TLS fixture với thời hạn kiểm soát, hoặc quản lý rotation certificate test có chủ đích; giữ một test expired-certificate riêng.

### Lỗi 10 — Log SMTP AUTH transcript

Khi test fail, debug log có thể chứa username, password được mã hóa bằng Base64 hoặc token.

**Cách xử lý:** tránh raw auth logs; nếu cần protocol debug, redaction và giới hạn quyền truy cập log. Base64 không phải mã hóa bảo mật của secret.

### Lỗi 11 — Dùng credentials production trong CI

Một lỗi cấu hình có thể khiến integration test gửi email thật hoặc làm lộ credential.

**Cách xử lý:** user/password test tách biệt; không cho fixture relay Internet; block egress khi có thể.

### Lỗi 12 — Negative test xanh vì fixture không chạy

Test **assertThrows** qua khi kết nối bị từ chối, dù mục tiêu là kiểm tra certificate không tin cậy.

**Cách xử lý:** xác nhận fixture ready và có TLS handshake đi tới bước kỳ vọng, sau đó mới kiểm tra exception phù hợp.

### Lỗi 13 — Chỉ test sai password sau khi SMTP đã nhận message

Test có thể gây gửi ngoài ý định hoặc trộn kết quả với mailbox cũ.

**Cách xử lý:** dùng **testConnection()** cho handshake/auth và fixture cô lập cho bài test submit.

### Lỗi 14 — Giữ cổng SMTP cố định trong tất cả test

Khi CI chạy song song, hai fixture cùng bind một port; một test có thể kết nối nhầm server của test khác.

**Cách xử lý:** dùng dynamic ports, lấy port từ fixture sau start và dừng đúng instance.

### Lỗi 15 — Cho test fallback tới production host

SMTP fixture không chạy, Spring Boot dùng host được cấu hình mặc định cho deployment.

**Cách xử lý:** test profile phải có host cô lập, assert host/port thực tế, và chặn egress tới SMTP ngoài nếu có thể.

### Lỗi 16 — Nghĩ SMTP AUTH đồng nghĩa From được phép

Đúng credentials chưa chắc server kiểm tra người gửi header From/envelope sender theo chính sách.

**Cách xử lý:** test sender identity riêng khi cần, sử dụng verified identities và provider settings phù hợp.

### Lỗi 17 — Dùng TLS protocol setting làm bằng chứng đã đàm phán

Chỉ nhìn **mail.smtp.ssl.protocols** rồi kết luận kết nối dùng TLS 1.3.

**Cách xử lý:** nếu cần bằng chứng phiên bản/cipher, lấy negotiated TLS session từ fixture hoặc instrumentation, không chỉ đọc cấu hình.

### Lỗi 18 — Gửi thành công nhưng test nhận nhầm thư cũ

Fixture dùng chung mailbox giữa các test, không reset message cũ.

**Cách xử lý:** fixture mới cho từng test hoặc dọn mailbox một cách có kiểm soát trước khi gửi; kiểm tra unique message marker trong captured MIME.

## 25. Quy trình điều tra lỗi TLS trong integration test

Khi JavaMailSender không kết nối được, có thể điều tra theo thứ tự để tránh bật trust-all quá sớm.

~~~text
1. Fixture đã start và bind cổng?
       |
       v
2. Host/port trong sender có trỏ đúng fixture?
       |
       v
3. Server là STARTTLS hay implicit TLS?
       |
       v
4. Client dùng đúng mode?
       |
       v
5. STARTTLS advertised, required và handshake được bắt đầu?
       |
       v
6. Certificate chain hợp lệ với test truststore?
       |
       v
7. SAN khớp hostname mà client kết nối?
       |
       v
8. Client và server có protocol/cipher tương thích?
       |
       v
9. TLS xong: server advertise AUTH?
       |
       v
10. User/password hoặc mechanism có đúng?
       |
       v
11. SMTP sender/recipient được phép?
       |
       v
12. MESSAGE ACCEPTED và captured đúng?
~~~

### Đọc loại lỗi như một dấu hiệu, không phải kết luận tuyệt đối

| Hiện tượng | Nghi vấn nên kiểm tra |
| --- | --- |
| Connection refused | Fixture không chạy, port sai hoặc network mapping sai |
| Read timed out trước SMTP greeting | Server nhận TCP nhưng không phản hồi, mode/cổng không khớp |
| Could not convert socket to TLS | STARTTLS handshake, certificate, protocol hoặc truststore |
| PKIX path building failed | Certificate chain không được truststore chấp nhận |
| No subject alternative names matching | Hostname identity mismatch |
| AuthenticationFailedException | Credentials, AUTH mechanism, server auth policy |
| Server does not support STARTTLS | EHLO capability không có STARTTLS trong khi client yêu cầu |
| 530 Authentication required | Server không cho gửi chưa xác thực; xem cấu hình AUTH |
| SMTP success nhưng mailbox rỗng | Recipient, fixture capture, acceptance semantics hoặc test state |

Thông điệp lỗi phụ thuộc implementation và phiên bản nên không nên dùng bảng làm logic phân loại production. Đọc cause chain và server-side test evidence để xác định giai đoạn thất bại.

### JSSE handshake debugging có giới hạn

Trong lúc điều tra, JDK có cơ chế log TLS handshake (chẳng hạn tùy chọn JSSE debug) để nhìn certificate chain, negotiated protocol và handshake stages. Chỉ bật trong test môi trường hạn chế; log có thể rất dài và chứa metadata nhạy cảm. Không bật toàn bộ TLS/network debug trong production chỉ để test một certificate.

Không cần in nội dung SMTP AUTH hoặc password để chẩn đoán một lỗi certificate; TLS handshake xảy ra trước khi gửi credentials trong policy an toàn.

## 26. Tình huống luyện tập

### Tình huống A — Test gửi được email, nhưng TLS tắt

SMTP catcher local nhận message ngay cả khi client chỉ kết nối plaintext.

**Hỏi:** test xanh có chứng minh TLS không?

**Đáp:** không. Cần một fixture hỗ trợ TLS thực và test client từ chối khi thiếu STARTTLS hoặc cert không hợp lệ.

### Tình huống B — STARTTLS enable nhưng server không quảng bá

Client cấu hình starttls.enable=true, thiếu required=true.

**Hỏi:** rủi ro?

**Đáp:** có thể tiếp tục gửi bằng plaintext tùy cấu hình và server. Với policy bắt buộc TLS, bật required và kiểm tra fail-closed.

### Tình huống C — Test tin certificate tự ký

Client import certificate test vào truststore rồi kết nối **localhost** với certificate SAN=localhost.

**Hỏi:** đây có phải vô hiệu hóa TLS verification?

**Đáp:** không nếu truststore chỉ tin certificate/CA test được chỉ định và hostname checking vẫn bật. Đây là cách kiểm thử trust có kiểm soát, khác trust-all.

### Tình huống D — Kết nối bằng IP, SAN chỉ có DNS

Certificate được cấp cho localhost, client gọi 127.0.0.1.

**Hỏi:** vì sao lỗi dù đã import cert?

**Đáp:** trust chain và hostname identity là hai bước khác nhau. IP không khớp DNS-only SAN; sửa hostname hoặc cấp certificate có IP SAN phù hợp.

### Tình huống E — Test password sai vẫn thành công

GreenMail/capture server trong test chấp nhận gửi dù credentials sai.

**Hỏi:** có nên kết luận JavaMailSender lỗi?

**Đáp:** chưa. Cần xác minh fixture có thực sự bật/enforce AUTH không. Một permissive SMTP catcher không đủ làm oracle cho authentication.

### Tình huống F — User đúng nhưng không bật mail.smtp.auth

Server bắt buộc AUTH.

**Hỏi:** kết quả đúng là gì?

**Đáp:** không thể nộp message như user đã xác thực. Test phải thấy bị từ chối, không tự fallback anonymous relay.

### Tình huống G — Port 465 nhưng không dùng TLS

Client gửi SMTP plaintext tới server implicit TLS.

**Hỏi:** sửa bằng cách bật STARTTLS?

**Đáp:** không nhất thiết. Nếu server là implicit TLS, cần **mail.smtp.ssl.enable=true**; STARTTLS là một mode khác.

### Tình huống H — Test certificate mismatch pass vì connection refused

Fixture TLS chưa start nhưng assertThrows được thỏa.

**Hỏi:** test có chứng minh hostname validation không?

**Đáp:** không. Phải bảo đảm fixture ready và exception xuất phát từ certificate identity check.

### Tình huống I — Gửi email test qua SMTP production

CI dùng credentials thật và recipient thuộc hộp thư nội bộ.

**Hỏi:** vì sao vẫn không phải môi trường cô lập?

**Đáp:** phụ thuộc mạng/provider, có thể tác động quota/danh tiếng, rò rỉ secrets và gửi ngoài ý định. Dùng local test fixture và chỉ dùng provider sandbox khi cần contract test riêng.

### Tình huống J — Test thay JVM truststore giữa hai thread

Test A dùng cert CA1, test B dùng CA2 và cả hai sửa system property.

**Hỏi:** test có thể không ổn định không?

**Đáp:** có. JVM-wide truststore settings tạo shared mutable state. Dùng per-client SSLContext/socket factory hoặc chạy JVM forks.

### Tình huống K — AUTH thành công qua plaintext

SMTP server nhận user/password trên kết nối chưa mã hóa.

**Hỏi:** đã đạt yêu cầu bảo mật chưa?

**Đáp:** chưa nếu policy yêu cầu bảo vệ credentials bằng TLS. Phải kiểm tra AUTH chỉ được thực hiện sau TLS và client từ chối server thiếu STARTTLS.

### Tình huống L — SMTP server chỉ hỗ trợ TLS cũ

Client policy chỉ cho TLSv1.2/1.3.

**Hỏi:** có nên hạ cấp policy trong test để gửi thành công?

**Đáp:** không nếu mục đích là xác nhận protocol cũ bị chặn. Kết quả đúng là handshake failure; cập nhật fixture/server nếu muốn happy path.

### Tình huống M — Email đã accepted nhưng người nhận không thấy

SMTP fixture báo nhận mail, còn một provider thật đưa thư vào spam.

**Hỏi:** integration test TLS/AUTH có thể chứng minh deliverability không?

**Đáp:** không. Nó chứng minh transport tới fixture, không kiểm tra mail reputation, DNS authentication, spam filtering hay provider delivery events.

### Tình huống N — Debug log chứa credentials

Một developer bật mail.debug trong pipeline và log ghi lại thông tin nhạy cảm.

**Hỏi:** nên làm gì?

**Đáp:** tắt raw protocol debug mặc định, redact dữ liệu, dùng test secrets và hạn chế quyền xem log. Khi cần điều tra, bật logging có kiểm soát trong test ngắn hạn.

### Tình huống O — Test AUTH đúng nhưng From giả mạo được chấp nhận

SMTP fixture kiểm tra password nhưng không kiểm tra sender identity.

**Hỏi:** có nên kết luận toàn bộ sender security đã đúng?

**Đáp:** không. AUTH và authorization của From/envelope sender là hai chính sách khác nhau; cần một fixture/provider test kiểm tra verified sender identity khi nghiệp vụ yêu cầu.

### Tình huống P — Cổng động của fixture bị thay đổi

Test dùng hard-coded port 3025 trong khi server được start trên một port khác.

**Hỏi:** cách tránh?

**Đáp:** lấy port thực tế từ fixture và inject vào Spring context bằng @DynamicPropertySource hoặc test configuration. Không dùng fallback ra host khác.

## 27. Quy trình thiết lập bộ kiểm thử trong dự án Spring Mail

Một triển khai có thể đi theo các bước:

~~~text
1. Xác định SMTP policy cần bảo vệ
   |
   +-- STARTTLS hay implicit TLS?
   +-- TLS bắt buộc hay opportunistic?
   +-- Certificate trust/hostname verification?
   +-- SMTP AUTH mechanism và sender permissions?
   |
   v
2. Chọn test fixture đủ khả năng thực thi policy
   |
   +-- GreenMail cho SMTP/auth/capture cơ bản
   '-- Container hoặc fixture TLS cho certificate/downgrade
   |
   v
3. Tạo tài khoản và TLS material test
   |
   +-- Test users/passwords
   +-- Certificate SAN khớp hostname
   '-- Truststore chỉ tin test CA/certificate
   |
   v
4. Khởi động fixture và lấy dynamic host/port
   |
   v
5. Ghi đè spring.mail.* ở test context
   |
   +-- Bật auth
   +-- Bật starttls.required hoặc ssl.enable
   +-- Bật hostname checking
   +-- Đặt socket timeouts
   |
   v
6. Chạy positive tests
   |
   +-- Handshake TLS thành công
   +-- AUTH đúng
   '-- Message được fixture capture
   |
   v
7. Chạy negative tests
   |
   +-- Không STARTTLS
   +-- Certificate sai trust
   +-- Hostname sai
   +-- Password/user sai
   +-- Mechanism/protocol không phù hợp
   '-- Không có accepted message khi thất bại
   |
   v
8. Xác nhận cleanup
   |
   +-- Fixture stop
   +-- Không có external SMTP traffic
   '-- Test state/credentials không rò sang test khác
   |
   v
9. Đưa vào CI với logging/secret policy rõ ràng
~~~

### Gợi ý phân chia test classes

| Test class/nhóm | Phạm vi |
| --- | --- |
| **SmtpAuthIntegrationTest** | Đúng/sai username/password, AUTH bắt buộc |
| **StartTlsIntegrationTest** | STARTTLS positive và required negative |
| **SmtpsIntegrationTest** | Implicit TLS positive, mode mismatch |
| **SmtpCertificateIntegrationTest** | Trust chain, wrong hostname, expired certificate |
| **SpringMailWiringIntegrationTest** | Spring Boot property binding và dynamic endpoint |
| **MimeSubmissionIntegrationTest** | MIME message sau khi đi qua SMTP fixture |
| **MailIsolationIntegrationTest** | Không dùng production host/credentials và không relay ngoài |

Đây là cách phân nhóm minh họa; không bắt buộc tạo đúng bảy class. Quan trọng là test failure cho biết **cấu hình và ranh giới nào đã hỏng**.

### Một tiêu chí nghiệm thu rõ ràng

Một bộ test có thể được coi là kiểm chứng policy TLS/AUTH tốt khi:

- Client thực sự kết nối tới server cô lập có chính sách TLS/AUTH đang kiểm thử.
- Happy path chỉ thành công với certificate, hostname và credentials hợp lệ.
- Ít nhất một test xác minh fail-closed nếu STARTTLS bị thiếu.
- Không tin cậy certificate lạ và không chấp nhận hostname sai.
- AUTH sai/thiếu bị từ chối khi server yêu cầu.
- Những lần handshake/auth thất bại không tạo accepted message.
- Test không sử dụng mail account sản xuất, không yêu cầu Internet, có timeout và cleanup.

Các tiêu chí này xác nhận hành vi trong môi trường kiểm thử có kiểm soát; vẫn cần đảm bảo cấu hình triển khai thật không khác chính sách đã test.

## 28. Phân biệt kiểm thử tích hợp với giám sát production

Kiểm thử cô lập giúp phát hiện lỗi cấu hình trong code/deployment templates. Nhưng môi trường production có thể thay đổi:

- Provider xoay vòng TLS certificate hoặc thay CA chain.
- Server thay TLS protocol/cipher policy.
- SMTP credentials hết hạn hoặc bị revoke.
- AUTH mechanism được provider thay đổi.
- DNS/network firewall gặp sự cố.
- Thay đổi relay permissions hoặc sender identity.

Vì thế, hệ thống nên kết hợp integration tests với **monitoring các lỗi SMTP/TLS** ở production, nhưng không gửi mail test tràn lan hoặc bật protocol debug chứa secrets.

Một số tín hiệu hữu ích:

| Tín hiệu | Hướng điều tra |
| --- | --- |
| TLS handshake failure tăng | Certificate/CA chain, hostname, protocol compatibility |
| Authentication failures tăng | Credentials, mechanism, account lock/revocation |
| Connection timeout tăng | Network, DNS, firewall, provider outage |
| Submission rejected do sender | Verified sender identity, envelope/From policy |
| Mail send latency tăng | SMTP provider, throughput, queue và worker pool |

**Không giải quyết sự cố certificate bằng cách tự động tắt verification trong production**. Thay vào đó, xác minh server certificate mới, CA trust và tên miền; cập nhật truststore/cấu hình theo quy trình kiểm soát thay đổi.

### Test không thay thế xác thực DNS và deliverability

Ngay cả khi integration test TLS/AUTH đã hoàn chỉnh, production còn cần quản lý:

- SPF, DKIM và DMARC nếu gửi qua domain của tổ chức.
- Bounce và complaint suppression.
- Sender reputation, rate limit và nội dung thư.
- Retry policy đối với SMTP lỗi tạm thời.
- Các tình huống timeout không rõ SMTP server đã accepted hay chưa.

Đây là các bài toán khác với việc TLS handshake và SMTP AUTH có được thực thi đúng hay không.

## 29. Tổng kết

~~~text
Mock JavaMailSender             -> Không chứng minh TLS/AUTH
SMTP capture thành công         -> Không tự chứng minh bảo mật
STARTTLS enable                 -> Không chắc fail-closed
STARTTLS required               -> Từ chối server thiếu STARTTLS
Implicit TLS                    -> mail.smtp.ssl.enable=true
Certificate trusted             -> Vẫn cần hostname identity check
Trust-all                       -> Không phải kiểm thử trust đúng
SMTP AUTH thành công            -> Chưa chắc From được phép
mail.debug                      -> Có thể làm lộ credentials
Spring test profile             -> Phải trỏ đúng SMTP fixture
SMTP server accepted            -> Không chứng minh Inbox delivered
~~~

**Kiểm thử TLS và xác thực trong môi trường cô lập** đòi hỏi một SMTP fixture có khả năng **thực thi và từ chối** các tình huống bảo mật tương ứng. Với Spring Framework Mail, có thể dùng **JavaMailSenderImpl** hoặc **JavaMailSender** được Spring Boot cấu hình, kết hợp GreenMail/SMTP container, truststore thử nghiệm và cổng động. Một bộ test có giá trị không chỉ xác nhận gửi email thành công, mà còn phải chứng minh rằng client **không downgrade sang plaintext khi TLS bắt buộc**, **không tin certificate sai**, **không bỏ qua hostname mismatch** và **không gửi khi SMTP AUTH thất bại**. Khi fixture được cô lập khỏi Internet, không dùng credentials production và có timeout/cleanup rõ ràng, những bài kiểm tra này sẽ là hàng rào thực tế chống hồi quy cấu hình bảo mật trước khi triển khai ứng dụng gửi mail.
