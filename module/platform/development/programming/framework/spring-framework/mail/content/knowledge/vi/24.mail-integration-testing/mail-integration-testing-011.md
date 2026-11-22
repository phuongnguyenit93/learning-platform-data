# Tránh test phụ thuộc thứ tự hoặc mailbox dùng chung

Trong ứng dụng **Spring Framework Mail**, kiểm thử tích hợp thường tạo một yêu cầu gửi email, để `JavaMailSender` làm việc với SMTP test server, rồi đọc các message đã được thu nhận và kiểm tra người nhận, tiêu đề, nội dung. Cách kiểm thử này hữu ích vì nó đi qua nhiều thành phần thật hơn unit test. Tuy nhiên, nếu các test cùng sử dụng một mailbox hoặc dựa vào việc test khác đã gửi/xóa thư trước đó, kết quả có thể thay đổi theo thứ tự và mức độ chạy song song.

Những dấu hiệu quen thuộc là: chạy một test đơn lẻ thì thành công nhưng chạy cả suite lại thất bại; lúc thấy một thư, lúc thấy ba thư; email xác nhận đơn hàng bị nhầm với email reset password; hoặc CI thất bại ngẫu nhiên vì một test khác vừa xóa toàn bộ inbox. Đây là vấn đề **test isolation**, không đơn giản là SMTP server quá chậm.

Một integration test đáng tin cậy phải **tự tạo tiền điều kiện, thực hiện hành động, quan sát đúng message của mình, và dọn tài nguyên mình sở hữu**. Nó không được dựa vào thứ tự các method, một mailbox có trạng thái không kiểm soát, hoặc thời gian chờ cố định.

Bài này giải thích các kiểu phụ thuộc thứ tự, những ranh giới cần cô lập, ví dụ JUnit 5 và Spring Boot, SMTP test server GreenMail/Mailpit, correlation ID, xử lý `@Async` và outbox, Spring Test context caching, parallel tests và cách xây dựng những bài kiểm thử có thể chạy ổn định trên CI.

## 1. Mục tiêu của một integration test email

Tùy phạm vi, integration test có thể kiểm tra:

- Application service đã chuyển một business event thành yêu cầu email phù hợp.
- Spring cấu hình đúng `JavaMailSender` và các bean liên quan.
- `MimeMessageHelper` tạo subject Unicode, recipient và các phần MIME chính xác.
- SMTP test server thực sự nhận được email.
- Worker xử lý outbox đã commit và cập nhật trạng thái.
- Lỗi kết nối, timeout hoặc retry được phản ánh đúng ở tầng ứng dụng.

Luồng phổ biến:

~~~mermaid
flowchart LR
    A["JUnit test"] --> B["Application service"]
    B --> C["Mail gateway / worker"]
    C --> D["JavaMailSender"]
    D --> E["SMTP test server"]
    E --> F["Captured messages"]
    F --> G["Assert message của test"]
~~~

Test có thể xác nhận email đã được SMTP test server **chấp nhận**. Nó không chứng minh thư đã tới hộp thư Internet của khách hàng hay đã được đọc; delivery là hợp đồng khác.

Một test ở lớp chọn template không cần SMTP; một unit test MIME có thể dùng `MimeMessage` thật trong bộ nhớ và fake sender. Chỉ đưa SMTP test server vào khi thật sự muốn kiểm tra ranh giới transport hoặc luồng tích hợp có side effect.

## 2. Phụ thuộc thứ tự test nghĩa là gì?

Một test bị **phụ thuộc thứ tự** nếu kết quả của nó thay đổi khi những test khác chạy trước hoặc sau.

Ví dụ sai:

~~~java
@Test
void createOrderAndSendEmail() {
    orderService.createAndNotify();
}

@Test
void readMailAndVerify() {
    MimeMessage last =
            sharedInbox.getReceivedMessages()[0];

    assertEquals(
            "Đơn hàng đã được tạo",
            last.getSubject()
    );
}
~~~

Test thứ hai đang giả định test thứ nhất đã chạy và đã gửi xong. Nó cũng giả định không có test khác gửi hoặc xóa thư, không có retry, và vị trí phần tử 0 luôn thuộc email mong đợi.

Nếu chạy test thứ hai riêng bằng IDE, nó có thể fail vì không có thư. Nếu chạy song song, test khác có thể gửi message vào cùng mailbox trước khi assertion thực hiện.

**Cách tốt hơn:** mỗi test bao trọn một hành vi:

~~~java
@Test
void sendsOrderConfirmation() {
    Order order = fixtures.createConfirmedOrder();

    orderMailService.requestConfirmation(
            order.getId()
    );

    MimeMessage actual =
            inbox.findConfirmationFor(order.getId());

    assertEquals(
            expectedSubject(order),
            actual.getSubject()
    );
}
~~~

Các helper `fixtures` và `inbox` ở đây là abstraction minh họa, phải được cài đặt sao cho dữ liệu và message thuộc đúng test hiện tại.

## 3. Vì sao @TestMethodOrder không phải giải pháp?

JUnit 5 hỗ trợ `@TestMethodOrder` và `@Order`:

~~~java
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class FragileMailIT {

    @Test
    @Order(1)
    void send() {
        // Tạo email.
    }

    @Test
    @Order(2)
    void verify() {
        // Đọc email do test trước tạo.
    }
}
~~~

Dù đã định thứ tự, test vẫn giòn vì:

- Một method bị chạy riêng.
- Method đầu bị disable hoặc ném exception.
- Các class khác cùng dùng mailbox.
- Một CI job khác chạy trên JVM khác.
- SMTP worker chưa xử lý xong khi test thứ hai bắt đầu.
- Cleanup/scheduler làm thay đổi trạng thái.

`@TestMethodOrder` có thể dùng cho những trường hợp đặc biệt khi thứ tự chính là đối tượng cần kiểm thử, nhưng **không nên dùng để vá việc test chia sẻ trạng thái ngầm**.

Nếu cần kiểm thử một workflow nhiều bước, hãy đặt các bước trong **một test scenario** với setup và assertion rõ ràng, thay vì phân chia thành những test method phụ thuộc nhau.

## 4. Mailbox dùng chung làm test sai theo cách nào?

Giả sử cả suite gửi tới:

~~~text
integration-test@example.test
~~~

Và dùng chung SMTP catcher:

~~~text
Test A: gửi "Order confirmed A"
Test B: gửi "Password reset B"
Test C: assert inbox có đúng 1 message
Test D: xóa toàn bộ inbox
~~~

Kết quả của test C phụ thuộc vào lịch thực thi. Test D có thể xóa thư mà A/B đang đợi.

| Dấu hiệu | Nguyên nhân thường gặp |
| --- | --- |
| Pass riêng nhưng fail cả suite | Còn thư từ test trước |
| Số message thay đổi ngẫu nhiên | Các test gửi đồng thời |
| Không thấy email dù SMTP log báo accepted | Test khác xóa inbox |
| Subject không đúng | Test đọc thư của test khác |
| CI fail, local pass | Có nhiều runner cùng dùng server/mailbox |
| Test reset token đôi lúc lấy token cũ | Dùng last message hoặc message index |
| Chạy lại vài lần thì pass | Race condition, residual state hoặc timing |

Thêm `Thread.sleep` chỉ thay đổi thời điểm quan sát, không giải quyết ownership của mailbox.

## 5. Các cấp độ isolation cần xem xét

| Ranh giới | Trạng thái cần cô lập | Cách làm |
| --- | --- | --- |
| Test method | Input ID, recipient, correlation | ID duy nhất theo test |
| SMTP server | Captured messages, listener, port | Server per test/per class |
| Mailbox | Message được lưu, trạng thái đã đọc | Mailbox riêng, namespace hoặc filter |
| Database/outbox | Entity, job, idempotency key | Fixture riêng, DB/schema riêng |
| Spring context | Bean, mail host/port, scheduler | Lifecycle và dynamic properties nhất quán |
| JVM/CI runner | Port, container, account test | Ephemeral resources hoặc namespace run |

Một correlation ID chỉ giúp **nhận diện** thư; nó không tự ngăn test khác xóa inbox. Một SMTP server riêng giúp cô lập email nhưng không tự làm một database order ID dùng chung trở nên an toàn.

Nên hiểu isolation là tổng hợp của **quyền sở hữu tài nguyên**, **dữ liệu riêng** và **điều kiện quan sát đúng**.

## 6. Nguyên tắc Arrange → Act → Assert → Cleanup

Một integration test độc lập nên có các giai đoạn:

**Arrange**

1. Tạo tài nguyên nghiệp vụ riêng.
2. Tạo `testRunId` / `correlationId` riêng.
3. Chọn SMTP test server hoặc namespace thuộc test.
4. Bảo đảm Spring mail sender trỏ đúng host/port.
5. Kiểm soát background worker và dữ liệu đã commit.

**Act**

Gọi đúng application use case hoặc worker đang kiểm thử.

**Assert**

Đợi message có correlation ID tương ứng, kiểm tra subject, recipient, MIME parts, attachment hoặc trạng thái outbox thích hợp.

**Cleanup**

Giải phóng server, container, dữ liệu test và các tài nguyên **do chính test sở hữu**. Không xóa thư của một test hoặc runner khác.

Một test tốt có thể chạy riêng, chạy lặp lại, chạy trước/sau các test khác mà vẫn có cùng ý nghĩa.

## 7. SMTP test server riêng cho từng method

Cách cô lập mạnh là tạo server trong `@BeforeEach` và dừng tại `@AfterEach`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;

class MailTransportIsolationIT {

    private GreenMail greenMail;

    @BeforeEach
    void startSmtp() {
        greenMail = new GreenMail(
                new ServerSetup(
                        0,
                        "127.0.0.1",
                        ServerSetup.PROTOCOL_SMTP
                )
        );

        greenMail.start();
    }

    @AfterEach
    void stopSmtp() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }

    @Test
    void sendsMail() {
        // Tạo JavaMailSender trỏ tới port của
        // GreenMail instance này, gửi và assert.
    }
}
~~~

Trong ví dụ, port `0` yêu cầu cấp port động. Cần dùng phiên bản GreenMail hỗ trợ cách cấu hình này và đọc lại port thực tế sau khi server đã start. Nếu môi trường không hỗ trợ, có thể dùng SMTP test container với port mapping động.

**Ưu điểm:** Test method không thể đọc mail cũ từ một server khác. Không cần global inbox cleanup.

**Đánh đổi:** Mỗi test phải khởi động SMTP listener, làm suite lớn chậm hơn. Có thể dùng server per class nếu vẫn giữ correlation riêng và lifecycle chính xác.

## 8. Ví dụ integration test với GreenMail và JavaMailSenderImpl

Mẫu sau tạo một SMTP server riêng cho mỗi test, dùng `JavaMailSenderImpl` thật kết nối loopback và lọc email bằng correlation header.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;
import java.util.Properties;
import java.util.UUID;

import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;

class SpringSmtpIntegrationTest {

    private GreenMail smtp;
    private JavaMailSenderImpl sender;

    @BeforeEach
    void setUp() {
        smtp = new GreenMail(
                new ServerSetup(
                        0, "127.0.0.1",
                        ServerSetup.PROTOCOL_SMTP
                )
        );

        smtp.start();

        sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(smtp.getSmtp().getPort());
        sender.setDefaultEncoding("UTF-8");

        Properties properties =
                sender.getJavaMailProperties();

        properties.put("mail.smtp.auth", "false");
        properties.put(
                "mail.smtp.connectiontimeout", "3000"
        );
        properties.put(
                "mail.smtp.timeout", "3000"
        );
        properties.put(
                "mail.smtp.writetimeout", "3000"
        );
    }

    @AfterEach
    void tearDown() {
        if (smtp != null) {
            smtp.stop();
        }
    }

    @Test
    void sendsMailForOwnCorrelationId()
            throws Exception {

        String id = UUID.randomUUID().toString();
        String recipient = "it-" + id + "@example.test";

        MimeMessage outgoing =
                sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        outgoing, false, "UTF-8"
                );

        helper.setFrom("orders@example.test");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + id);
        helper.setText("Đơn hàng của " + id);

        outgoing.setHeader(
                "X-Test-Correlation-Id", id
        );

        sender.send(outgoing);

        assertTrue(
                smtp.waitForIncomingEmail(5000, 1)
        );

        MimeMessage[] matches =
                Arrays.stream(smtp.getReceivedMessages())
                        .filter(message -> {
                            try {
                                return id.equals(
                                        message.getHeader(
                                            "X-Test-Correlation-Id",
                                            null
                                        )
                                );
                            } catch (MessagingException ex) {
                                throw new IllegalStateException(ex);
                            }
                        })
                        .toArray(MimeMessage[]::new);

        assertEquals(1, matches.length);

        MimeMessage actual = matches[0];

        assertEquals(
                "Xác nhận đơn hàng " + id,
                actual.getSubject()
        );

        InternetAddress to = (InternetAddress)
                actual.getRecipients(
                        Message.RecipientType.TO
                )[0];

        assertEquals(recipient, to.getAddress());
    }
}
~~~

Đây là ví dụ tích hợp theo API GreenMail/Jakarta Mail thường gặp; dependency và cách khởi tạo port động cần khớp phiên bản thực tế của dự án.

Ý nghĩa quan trọng:

- SMTP server và captured inbox chỉ thuộc test method.
- Recipient và correlation ID được sinh mới cho mỗi lần chạy.
- Không có credential production hoặc địa chỉ khách hàng thật.
- Test không chọn message theo index cố định.
- `waitForIncomingEmail` là bước đợi SMTP capture; việc lọc theo ID xác nhận đúng **message của test**.
- Test không cần biết các test khác đã chạy hay chưa.

### Dependency test minh họa

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'com.icegreen:greenmail:<pinned-version>'
}
~~~

`<pinned-version>` là chỗ cần thay bằng phiên bản có thật, được dự án pin và tương thích với Jakarta Mail/Spring Boot đang dùng. Không coi placeholder là tọa độ dependency có thể tải ngay.

## 9. Server per class: đánh đổi tốc độ và isolation

Nếu mỗi method tạo server quá tốn thời gian, có thể start một server tại `@BeforeAll` và stop tại `@AfterAll`. Khi đó, tất cả method trong class nhìn thấy cùng một captured inbox, nhưng khác class có thể có server riêng.

~~~text
OrderMailIT:
  SMTP server A
  test #1 correlation X
  test #2 correlation Y

SecurityMailIT:
  SMTP server B
  test #1 correlation Z
~~~

Cần giữ:

- Mỗi method dùng recipient/correlation riêng.
- Không xóa toàn inbox khi method khác có thể đang gửi.
- Không assert toàn bộ inbox có đúng một message.
- Không chọn “newest” message.
- Không stop server khi các tác vụ async của class vẫn đang gửi.

| Server lifecycle | Điểm mạnh | Rủi ro |
| --- | --- | --- |
| Per method | Cô lập message mạnh | Startup nhiều |
| Per class | Ít startup hơn | Methods chung captured inbox |
| Per suite/JVM | Hiệu quả tài nguyên | Nhiều class cần namespace và cleanup |
| External shared service | Dễ dùng chung | Rủi ro giữa JVM và CI pipelines |

Không có một scope đúng cho mọi suite. Khi tối ưu tốc độ, phải giữ test-scoped correlation và quy tắc ownership.

## 10. Correlation ID quan trọng hơn “email cuối cùng”

Một test có thể sinh:

~~~java
String testRunId =
        UUID.randomUUID().toString();

String recipient =
        "it+" + testRunId + "@example.test";
~~~

Các trường có thể dùng để lọc:

- Recipient riêng.
- Header `X-Correlation-Id` hoặc `X-Test-Correlation-Id`.
- Business event ID / outbox job ID.
- Template/purpose đi kèm event.
- Subject marker đặc trưng.
- Provider message reference nếu có hợp đồng tương ứng.

Ví dụ:

~~~text
testRunId: run-72bc
orderId: ORD-IT-72bc
recipient: it+run-72bc@example.test
X-Correlation-Id: run-72bc
~~~

Test cần **lọc trước khi đếm và assert**:

~~~java
List<MimeMessage> own =
        inbox.findByCorrelationId(testRunId);

assertEquals(1, own.size());
~~~

Không nên:

~~~java
MimeMessage last =
        inbox.allMessages().getLast();
~~~

Nếu nhiều worker gửi đồng thời, thứ tự capture không nhất thiết phản ánh thứ tự domain event.

### Message-ID không phải thay thế hoàn toàn correlation ID

Header `Message-ID` có thể do thư viện/provider phát sinh hoặc sửa trong quá trình gửi. Nó hữu ích cho tracing, nhưng nếu muốn test tìm theo một ID do ứng dụng kiểm soát, hãy truyền correlation ID rõ ràng qua command/job/header hoặc metadata phù hợp.

Một số provider thật có thể loại bỏ custom header, nên test provider integration phải dựa vào những trường/cơ chế mà provider thực sự bảo đảm.

## 11. Đừng xóa toàn bộ mailbox dùng chung

Một anti-pattern:

~~~java
@BeforeEach
void clearInbox() {
    sharedSmtpServer.deleteAllMessages();
}
~~~

Khi chạy song song:

~~~text
Test A: gửi message có ID A
Test B: @BeforeEach xóa toàn inbox
Test A: không tìm thấy message ID A
~~~

Đây là **race condition gây mất bằng chứng của test khác**.

Cách an toàn hơn, theo mức ưu tiên:

1. Test có SMTP server riêng và được phép reset toàn server riêng đó.
2. Test dùng mailbox/namespace riêng và cleanup trong phạm vi đó.
3. Test dùng correlation ID, chỉ xóa message do mình tạo nếu API cho phép.
4. Nếu bắt buộc dùng inbox chung, cần một cơ chế đồng bộ giữa những tác nhân thật sự chia sẻ resource; tốt nhất vẫn là loại bỏ chia sẻ.

Không xóa “tất cả email trong 5 phút gần nhất” vì một CI run khác có thể đang sử dụng mailbox ở cùng thời điểm.

### Cleanup là trách nhiệm của chủ sở hữu

`@AfterEach` hoặc `try-finally` nên dọn server/container/fixture mà chính test đã tạo:

~~~java
@AfterEach
void cleanup() {
    if (smtp != null) {
        smtp.stop();
    }
}
~~~

Nếu có async worker còn đang chạy, cần bảo đảm tác vụ liên quan đã kết thúc hoặc bị hủy theo policy trước khi đóng server. Cleanup sớm có thể tự gây connection refused cho thao tác gửi còn dang dở.

## 12. Shared static inbox không phải test isolation

Ví dụ:

~~~java
public final class TestMailStore {
    static final List<MimeMessage> MESSAGES =
            new ArrayList<>();
}
~~~

Các test dùng chung list có thể gặp:

- State từ test trước.
- Data race nếu nhiều thread thêm/xóa.
- Test này xóa dữ liệu test kia.
- Count phụ thuộc thứ tự.
- Test pass do vô tình thấy thư cũ.

Chuyển sang `CopyOnWriteArrayList` hoặc `ConcurrentLinkedQueue` chỉ giải quyết một phần **thread safety**. Nó không giải quyết việc “message của ai”. Cần mỗi test có capturing store riêng hoặc filter theo owner ID.

## 13. Spring Boot context caching và SMTP dynamic port

`@SpringBootTest` có thể tái sử dụng Spring ApplicationContext cho các test có cấu hình tương đương. Đây là tối ưu tốt về thời gian nhưng gây lỗi khi sender bean còn giữ SMTP port của một server đã dừng.

Ví dụ:

~~~text
Class A:
  SMTP server A chạy port 31021
  Spring context tạo JavaMailSender(port 31021)
  Class A kết thúc và stop SMTP A

Class B:
  Server B chạy port 31055
  Spring tái sử dụng context cũ
  JavaMailSender vẫn dùng port 31021
  Connection refused
~~~

Cần quản lý **vòng đời server cùng với vòng đời Spring context**:

- Cấp runtime host/port bằng `@DynamicPropertySource` khi context khởi tạo.
- Không stop test server trước khi context cuối cùng sử dụng nó xong.
- Cẩn thận với static server được các subclass dùng chung.
- Cân nhắc `@DirtiesContext` khi dynamic endpoints hoặc singleton state khác nhau khiến context không thể reuse.
- Nếu cần SMTP server per method, không dùng một sender singleton được tạo với port method trước.

Không giải quyết bằng cách gán một SMTP port cố định cho mọi test, vì điều đó gây xung đột khi chạy parallel/CI.

## 14. Testcontainers và @DynamicPropertySource

Với SMTP catcher chạy trong container, port mapping động tránh xung đột giữa những CI run trên cùng host.

Ví dụ cấu trúc sử dụng Mailpit:

~~~java
@Testcontainers
@SpringBootTest
class MailFlowIT {

    @Container
    static GenericContainer<?> mailpit =
            new GenericContainer<>(
                    DockerImageName.parse(
                            "axllent/mailpit:<pinned-version>"
                    )
            ).withExposedPorts(1025, 8025);

    @DynamicPropertySource
    static void configureSmtp(
            DynamicPropertyRegistry registry) {

        registry.add(
                "spring.mail.host",
                mailpit::getHost
        );

        registry.add(
                "spring.mail.port",
                () -> mailpit.getMappedPort(1025)
        );

        registry.add(
                "spring.mail.properties.mail.smtp.auth",
                () -> "false"
        );
    }

    @Autowired
    OrderMailService service;

    @Test
    void sendsOrderConfirmation() {
        // Tạo order/correlation ID riêng.
        // Trigger service.
        // Dùng test HTTP client đọc API Mailpit
        // tại mapped port 8025, lọc đúng ID.
    }
}
~~~

`<pinned-version>` là placeholder cần thay bằng version image thật được dự án quản lý. Khi áp dụng, cần bảo đảm thứ tự start container và Spring context phù hợp Testcontainers/Spring Boot đang dùng, đồng thời client đọc Mailpit API phải dùng schema đúng phiên bản.

Mẫu này nhấn mạnh:

1. SMTP service thuộc test.
2. Port được ánh xạ động.
3. Spring sender nhận đúng port.
4. Message được tìm theo correlation ID.
5. Không phụ thuộc một mailbox production.

### Khi nào nên dùng @DirtiesContext?

Nếu test làm context trở nên không còn hợp lệ, `@DirtiesContext` có thể buộc Spring tạo context mới. Nhưng annotation này:

- Không tự xóa mailbox ngoài JVM.
- Không tự rollback database commit ngoài transaction test.
- Không làm các CI runner khác ngừng gửi.
- Có thể làm suite chậm vì context phải khởi tạo lại.

Hãy dùng nó đúng ranh giới context, không thay thế thiết kế mail isolation.

## 15. Các công cụ SMTP test phục vụ mục tiêu gì?

| Công cụ | Cách dùng phổ biến |
| --- | --- |
| GreenMail | SMTP/IMAP/POP3 test server nhúng JVM, API Java đọc message |
| Mailpit | SMTP catcher có web UI/HTTP API, thường chạy container |
| MailHog | SMTP catcher và API, phù hợp hệ thống đã sử dụng nó |
| Wiser/lightweight SMTP | Thu message trong test JVM |
| Fake `MailGateway` | Test application layer mà không mở SMTP |
| Mock `JavaMailSender` | Test gateway/MIME mà không gửi qua network |
| Provider sandbox | Test hành vi riêng của provider theo hợp đồng |

Unit test mapping template/recipient không cần SMTP. Test MIME có thể dùng `MimeMessage` thật + mocked sender. Test SMTP protocol cần server, còn test AUTH/TLS thực tế với provider cần sandbox riêng.

Không nên sử dụng provider thật cho mọi phép assert đơn giản vì làm test chậm, dễ flaky và tiêu thụ quota.

## 16. Gửi bất đồng bộ: đợi điều kiện thay vì Thread.sleep

Với `@Async`, outbox, scheduler hoặc message consumer, email có thể được gửi **sau** lúc application method trả về.

Cách dễ gây flaky:

~~~java
mailService.requestConfirmation(orderId);

Thread.sleep(1000);

assertEquals(
        1,
        sharedInbox.getReceivedMessages().length
);
~~~

Một giây có thể thừa trên máy nhanh, nhưng không đủ khi CI tải cao. Inbox toàn cục còn có thể chứa message không liên quan.

Dùng cách đợi theo điều kiện, ví dụ Awaitility:

~~~java
String correlationId =
        UUID.randomUUID().toString();

mailService.requestConfirmation(
        orderId,
        correlationId
);

await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {

        List<CapturedMail> own =
                testInbox.findByCorrelationId(
                        correlationId
                );

        assertEquals(1, own.size());

        assertEquals(
                expectedSubject,
                own.get(0).subject()
        );
    });
~~~

`testInbox.findByCorrelationId` là helper/adapter test do dự án tạo; `await()` minh họa API Awaitility.

Ưu điểm:

- Không cần ngủ một thời gian cố định.
- Điều kiện đủ thì kết thúc.
- Timeout cung cấp lỗi rõ.
- Chỉ quan sát message của test.

### Đợi có điều kiện khác với “chờ càng lâu càng tốt”

Nếu worker chưa thể gửi vì job đang `RETRY` hoặc recipient policy từ chối, test nên thất bại với diagnostic cụ thể thay vì ngủ tới nhiều phút. Khi kiểm tra behavior “không gửi”, cần một trạng thái kết thúc đáng tin cậy hơn việc thấy inbox rỗng ngay tức thì.

## 17. Correlation ID xuyên suốt request → outbox → MIME

Một ID có thể bắt đầu từ test và đi qua pipeline:

~~~mermaid
flowchart LR
    A["Test tạo correlation ID"] --> B["Command"]
    B --> C["Outbox job"]
    C --> D["Worker"]
    D --> E["MIME X-Correlation-Id"]
    E --> F["SMTP capture"]
    F --> G["Test tìm đúng message"]
~~~

Command minh họa:

~~~java
public record RequestConfirmationMail(
        UUID orderId,
        String correlationId) {
}
~~~

Trong gateway, sau khi dựng message:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message, true, "UTF-8"
        );

// Set To, From, Subject, plain text và HTML.

message.setHeader(
        "X-Correlation-Id",
        correlationId
);

mailSender.send(message);
~~~

Test có thể đọc header này nếu SMTP capture server giữ lại. Trong sản phẩm thật, correlation ID có thể là `requestId` hoặc `outboxJobId` do ứng dụng sinh, không nhất thiết cho HTTP client tự kiểm soát. Không nhét token, địa chỉ bí mật hoặc PII vào header chỉ để debug.

**Correlation không phải authorization:** recipient vẫn phải được kiểm tra theo chính sách ứng dụng.

## 18. Không dùng “last message” hay thứ tự captured array

Một cách sai:

~~~java
MimeMessage latest =
        mailbox.getAll().get(
                mailbox.getAll().size() - 1
        );
~~~

Giả định này thất bại khi:

- Test khác gửi email cùng lúc.
- Scheduler phát notification nền.
- Retry sinh thêm message.
- SMTP capture API không bảo đảm thứ tự.
- Worker xử lý các job đồng thời.

Nên dùng:

~~~java
List<CapturedMail> own =
        mailbox.findByCorrelationId(
                correlationId
        );

assertEquals(1, own.size());

CapturedMail actual = own.get(0);
~~~

Nếu use case thực sự gửi **hai email cho hai người nhận**, hãy assert một **tập message** đúng recipient và purpose, không assert phần tử đầu tiên nhất thiết là khách hàng và phần tử thứ hai nhất thiết là quản lý.

## 19. Database fixture cũng không được phụ thuộc thứ tự

Mail workflow thường đọc order/customer/tenant từ database. Nếu test A tạo record và test B dùng record đó, lỗi phụ thuộc thứ tự đã xuất hiện trước SMTP.

Ví dụ sai:

~~~java
static UUID orderId;

@Test
void createOrder() {
    orderId = orderRepository.save(...).getId();
}

@Test
void sendMail() {
    mailService.send(orderId);
}
~~~

Cách an toàn:

~~~java
@Test
void sendsMailForOwnOrder() {
    Order order = orderFixtures.createConfirmedOrder(
            "it-" + UUID.randomUUID()
    );

    mailService.send(order.getId());

    // Tìm đúng message cho order của test.
}
~~~

Với `@Sql` hoặc seed data, dùng khóa/namespace không va chạm; tránh ID cố định do nhiều test cùng cập nhật. Cleanup cần chỉ xóa những record test sở hữu.

### @Transactional trên test và thread worker

Một lỗi tinh vi: test method gắn `@Transactional`, tạo order chưa commit rồi gọi `@Async` worker trong thread khác. Worker có thể không đọc thấy order vì transaction trên thread test chưa commit.

Không giải quyết bằng sleep dài hơn. Có thể:

- Commit fixture trước khi kích hoạt worker.
- Dùng `TestTransaction` để điều khiển ranh giới khi phù hợp.
- Không bọc toàn bộ test trong transaction rollback nếu workflow cần worker nhìn thấy dữ liệu đã commit.
- Dùng database/schema riêng để cleanup sau test.
- Với outbox, xác nhận worker chỉ đọc những job đã commit.

Điều này thuộc transaction visibility, không phải lỗi mailbox.

## 20. Outbox test phải định danh đúng job

Nếu worker poll `mail_outbox`, không nên chọn record tùy tiện:

~~~java
MailOutbox job = repository.findFirstPending();
worker.process(job);

assertEquals(1, inbox.allMessages().size());
~~~

Khi có test khác tạo job, `findFirstPending` có thể trả về công việc không thuộc test.

Một test tốt có:

- `outboxJobId` duy nhất.
- `idempotencyKey` duy nhất cho ý định gửi mới.
- Recipient/correlation ID duy nhất.
- DB fixture được commit trước khi worker đọc.
- Trạng thái `SENT` hoặc `RETRY` được tìm theo job ID.
- SMTP message được lọc theo correlation ID.

Ví dụ khái niệm:

~~~java
UUID jobId = fixtures.insertPendingMail(
        "it-" + UUID.randomUUID(),
        recipient
);

worker.processJob(jobId);

await().atMost(Duration.ofSeconds(10))
    .untilAsserted(() -> {

        assertEquals(
                MailStatus.SENT,
                repository.getStatus(jobId)
        );

        assertEquals(
                1,
                inbox.findByJobId(jobId).size()
        );
    });
~~~

`processJob`, `getStatus` và `findByJobId` là helper/test seam minh họa. Nếu production worker không có API xử lý một job riêng, có thể dùng scheduler thật với DB độc lập, thay vì thay đổi production semantics chỉ để thuận tiện test.

## 21. Idempotency và retry không phải “luôn một SMTP message”

Một outbox record có unique key có thể được worker đọc lại sau crash. Tình huống:

~~~text
Worker A claim job
SMTP relay chấp nhận mail
Worker A crash trước UPDATE SENT
Worker B claim lại sau lease
SMTP có thể nhận thêm một message
~~~

Unique constraint chặn **tạo nhiều job logic**, nhưng không bảo đảm SMTP chỉ nhận đúng một message qua crash window. Test cần phản ánh hợp đồng thực tế.

Nếu kiểm tra duplicate enqueue:

~~~java
String key = "it-" + UUID.randomUUID();

service.requestMail(key);
service.requestMail(key);

assertEquals(
        1,
        outboxRepository.countByKey(key)
);
~~~

Đây là assertion đúng cho idempotent **enqueue**. Test “không gửi lại job đã `SENT`” là câu chuyện khác. Test crash sau SMTP acceptance phải nhận biết side effect có thể bị lặp, trừ khi provider thực sự có cơ chế dedupe được định nghĩa.

Không xóa duplicate message trước assertion để làm test pass.

## 22. Test phủ định: không gửi mail cũng cần ranh giới rõ

Ví dụ:

~~~java
service.rejectUnauthorizedRequest(...);

assertEquals(
        0,
        sharedInbox.getReceivedMessages().length
);
~~~

Assertion này có thể fail vì inbox chứa thư của test khác, hoặc pass vì một test khác vừa xóa inbox. Với async, chưa thấy email ngay lúc đó cũng không chứng minh sẽ không gửi về sau.

Lựa chọn tốt:

1. Test application policy với fake `MailGateway` riêng, assert không có `send` call.
2. Integration test dùng SMTP server riêng và đợi workflow tới trạng thái kết thúc.
3. Hoặc kiểm tra không có message mang correlation ID của request bị từ chối trong một cửa sổ quan sát có điều kiện, kết hợp trạng thái job/policy.

Một test negative không nên dựa vào “mailbox toàn suite hoàn toàn rỗng”.

## 23. Parallel tests và JUnit 5

Khi JUnit parallel execution được bật, mọi shared mutable state cần được xem xét:

- Static mutable collection.
- Shared SMTP server có reset inbox.
- Database row chung.
- Spring singleton có thể bị test mutate.
- Background scheduler cùng lấy job.
- Static fields dùng làm correlation hoặc order ID.
- Test server lifecycle/port chồng nhau.

### @Execution(SAME_THREAD)

Có thể tạm thời yêu cầu một class chạy các method tuần tự:

~~~java
@Execution(ExecutionMode.SAME_THREAD)
class SharedMailboxIT {
    // Tạm hạn chế tranh chấp trong phạm vi JUnit.
}
~~~

Điều này không ngăn class khác/JVM khác dùng mailbox cùng lúc. Nó là mitigation, không phải giải pháp isolation bền vững.

### @ResourceLock

Nếu nhiều test trong cùng JUnit engine bắt buộc dùng một tài nguyên đặt tên:

~~~java
@ResourceLock(
        value = "smtp-shared-mailbox",
        mode = ResourceAccessMode.READ_WRITE
)
class SharedMailboxIT {
    // Các test dùng cùng lock name được
    // điều phối bởi JUnit trong phạm vi phù hợp.
}
~~~

`@ResourceLock` **không phải distributed lock**. Nó không đồng bộ hai JVM fork, hai pipeline CI hoặc hai máy.

Khi có thể, thiết kế **per-test server hoặc namespace** vẫn tốt hơn khóa toàn suite.

## 24. TestInstance(PER_CLASS) và mutable state

Với:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class MailIT {

    private final List<String> subjects =
            new ArrayList<>();
}
~~~

các method cùng instance chia sẻ list `subjects`. Nếu không reset, test sau thấy dữ liệu test trước; nếu chạy parallel, còn có data race.

Đừng dùng `PER_CLASS` chỉ để chia sẻ biến kết quả email giữa test. Nếu muốn một server per class, có thể giữ reference server ở scope class nhưng mỗi test vẫn phải có fixture/correlation riêng.

Thread-safe collection cũng không tự giải quyết quyền sở hữu dữ liệu.

## 25. CI nhiều process và nhiều job

Một test suite có thể chạy an toàn trong một JVM nhưng xung đột trên CI:

~~~text
CI job A: runner 1 → qa-mailbox@example.test
CI job B: runner 2 → qa-mailbox@example.test
CI job C: runner 3 → qa-mailbox@example.test
~~~

Mọi JUnit lock chỉ hoạt động trong phạm vi engine/process được quản lý; mailbox bên ngoài vẫn dùng chung.

Các lựa chọn:

- Mailpit/GreenMail container riêng cho từng CI job.
- SMTP test account riêng theo pipeline.
- Namespace email theo build ID + test ID.
- Port mapping động để tránh tranh chấp.
- Schema/database riêng cho mỗi job.
- Cleanup scoped theo run ownership.
- Không dùng credential production.
- Không xóa toàn mailbox khi build khác đang chạy.

Nếu phải dùng external mailbox, cần tách vùng sở hữu hoặc có coordination thực sự giữa các process, không chỉ thêm `@Execution(SAME_THREAD)`.

## 26. Plus addressing không đồng nghĩa mailbox độc lập

Một provider có thể cho địa chỉ:

~~~text
qa+run-a@example.test
qa+run-b@example.test
~~~

Nhưng hai địa chỉ đó có thể cùng đổ vào **một mailbox vật lý**. Một số provider không hỗ trợ plus addressing hoặc xử lý local-part khác nhau.

Dùng alias giúp phân biệt recipient trên message, nhưng vẫn cần:

- Correlation ID.
- Truy vấn/filter chính xác.
- Cleanup chỉ message thuộc run.
- Hạn chế test khác gọi “delete all”.
- Quản lý provider quota.

Không giả định email alias tương đương tài khoản mailbox riêng có isolation tuyệt đối.

## 27. Đợi đúng message và tránh poll quá nhanh

Một adapter test có thể có API:

~~~java
public interface TestInbox {

    List<CapturedMail> findByCorrelationId(
            String correlationId);

    List<CapturedMail> findByRecipient(
            String recipient);
}
~~~

Test sử dụng:

~~~java
String id = UUID.randomUUID().toString();

service.sendWithCorrelationId(id);

await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {

        List<CapturedMail> captured =
                testInbox.findByCorrelationId(id);

        assertEquals(1, captured.size());
        assertEquals(
                "ORDER_CONFIRMED",
                captured.get(0).purpose()
        );
    });
~~~

Không poll DB/SMTP API mỗi 1 ms mà không có lý do; nó có thể tạo tải và ảnh hưởng timing. Chọn deadline và interval phù hợp CI, nhưng vẫn muốn lỗi vĩnh viễn được báo sớm bằng trạng thái cuối/reason code nếu có.

### Kiểm thử timeout/retry nên điều khiển thời gian

Nếu workflow dùng retry sau 5 phút, không nên cho test ngủ thật 5 phút. Có thể inject `Clock`, chạy một scheduler có seam hoặc set `nextAttemptAt` có chủ đích trong fixture. Điều khiển thời gian giúp test độc lập và deterministic.

## 28. Diagnostic khi test thất bại

Khi email không xuất hiện trước timeout, hãy báo thông tin **thuộc test hiện tại**:

~~~text
testCase: sendsInvoiceMail
correlationId: it-931a
expectedMatchingMessages: 1
actualMatchingMessages: 0
outboxStatus: RETRY
failureCategory: SMTP_TIMEOUT
~~~

Không dump toàn bộ inbox của suite hoặc mọi email token/password vì:

- Dữ liệu có thể thuộc test khác.
- Output quá lớn, khó tìm lỗi.
- Có thể làm lộ token bảo mật.
- Khi test cleanup, thông tin liên quan bị mất.

Một test server per method giúp diagnostic scoped đơn giản hơn. Có thể lưu thông tin tóm tắt trước `@AfterEach` dừng server.

## 29. MIME và Unicode: chỉ assert sau khi đã tìm đúng thư

Sau khi xác định email thuộc test bằng correlation ID:

~~~java
MimeMessage actual =
        inbox.findOneByCorrelationId(id);

assertEquals(
        "Hóa đơn tháng 11 – Đơn hàng ORD-2048",
        actual.getSubject()
);

InternetAddress recipient = (InternetAddress)
        actual.getRecipients(
                Message.RecipientType.TO
        )[0];

assertEquals(
        "buyer@example.test",
        recipient.getAddress()
);
~~~

Với MIME multipart có HTML/plain text và attachment, có thể có nhiều mức `multipart/alternative` / `multipart/mixed`. Không giả định phần tử đầu luôn plain text và phần tử thứ hai luôn HTML.

Nên tìm part theo MIME type và kiểm tra decoded content. Không assert raw MIME boundary, Message-ID ngẫu nhiên hoặc thứ tự captured messages nếu chúng không thuộc hợp đồng cần test.

## 30. Gửi nhiều email trong một use case

Một workflow có thể gửi email cho khách hàng và quản lý. Nên kiểm tra tập kết quả, không kiểm tra vị trí:

~~~java
List<CapturedMail> own =
        inbox.findByRequestId(requestId);

assertEquals(2, own.size());

assertTrue(
        own.stream().anyMatch(mail ->
                mail.recipient().equals(customerEmail)
                && mail.purpose() == MailPurpose.CUSTOMER
        )
);

assertTrue(
        own.stream().anyMatch(mail ->
                mail.recipient().equals(managerEmail)
                && mail.purpose() == MailPurpose.MANAGER
        )
);
~~~

Nếu thứ tự gửi không được thiết kế như một invariant nghiệp vụ, đừng assert mail của khách hàng bắt buộc xuất hiện trước mail quản lý. Hai task async có thể hoàn thành theo thứ tự khác nhau mà vẫn đúng.

## 31. Những lỗi phổ biến và hướng sửa

### 31.1. Test A gửi, test B kiểm tra

**Lỗi:** test B phụ thuộc test A.

**Sửa:** mỗi test tự tạo và kiểm tra message hoặc gom scenario vào một test.

### 31.2. @Order để sửa test flaky

**Lỗi:** thứ tự được áp nhưng trạng thái chung không có ownership.

**Sửa:** isolate server/fixture; không phụ thuộc thứ tự.

### 31.3. Đọc getReceivedMessages()[0]

**Lỗi:** có thể là email cũ hoặc từ test khác.

**Sửa:** lọc correlation/recipient trước khi assert.

### 31.4. Assert inbox toàn hệ thống có đúng một thư

**Lỗi:** test khác có thể gửi.

**Sửa:** đếm chỉ message thuộc test, hoặc sở hữu toàn server.

### 31.5. Xóa mọi email trong @BeforeEach

**Lỗi:** xóa thư của test chạy song song.

**Sửa:** reset chỉ server riêng hoặc cleanup scoped.

### 31.6. Dùng một static mutable list làm inbox

**Lỗi:** chia sẻ state và có data race.

**Sửa:** capturing store per test và ownership rõ.

### 31.7. Thread.sleep cố định với @Async

**Lỗi:** timing tùy môi trường.

**Sửa:** Awaitility/latch/future và điều kiện kết thúc đúng.

### 31.8. Spring context cache sender trỏ server đã dừng

**Lỗi:** context và SMTP lifecycle không khớp.

**Sửa:** dynamic property và server lifecycle phù hợp; `@DirtiesContext` khi thực sự cần.

### 31.9. Dùng port SMTP cố định

**Lỗi:** CI parallel port collision.

**Sửa:** ephemeral host port và truyền runtime config vào sender.

### 31.10. @Transactional test chưa commit nhưng worker đã đọc

**Lỗi:** thread khác không thấy dữ liệu.

**Sửa:** commit fixture đúng thời điểm và cleanup riêng.

### 31.11. Test phủ định chỉ kiểm tra inbox ngay tức thì

**Lỗi:** email có thể được gửi về sau.

**Sửa:** đợi trạng thái workflow cuối hoặc fake gateway để assert policy.

### 31.12. Dùng cùng idempotency key trong nhiều test

**Lỗi:** test sau bị dedupe bởi job cũ.

**Sửa:** sinh key riêng cho từng ý định gửi của test.

### 31.13. Retry test yêu cầu exactly-once SMTP qua crash

**Lỗi:** không phù hợp tính chất database/SMTP.

**Sửa:** kiểm tra hợp đồng thực tế về enqueue, claim và outcome không chắc chắn.

### 31.14. Cleanup theo khoảng thời gian

**Lỗi:** có thể xóa thư build khác.

**Sửa:** cleanup theo test run/correlation.

### 31.15. Dùng production SMTP credential

**Lỗi:** gửi nhầm mail thật và tiêu thụ quota.

**Sửa:** fake/GreenMail/Mailpit hoặc sandbox được cô lập.

### 31.16. @ResourceLock được coi là distributed lock

**Lỗi:** lock không bao phủ CI runner khác.

**Sửa:** cô lập account/server hoặc coordination bên ngoài.

## 32. Ma trận thiết kế test

| Câu hỏi kiểm thử | Cách tổ chức | Tránh |
| --- | --- | --- |
| Một email đồng bộ | Server riêng, correlation riêng | Đọc newest message |
| Email bất đồng bộ | Await theo ID và deadline | Sleep cố định |
| Nhiều email trong một request | Assert tập message theo request | Assert thứ tự array |
| Policy từ chối gửi | Fake gateway hoặc isolated server | Đếm toàn inbox |
| Outbox worker | Job ID và fixture riêng | Claim job PENDING bất kỳ |
| Retry | Stable job ID, attempt ID khi cần | Đếm mọi thư toàn cục |
| Parallel methods | Namespace/server per method | Delete-all mailbox |
| Parallel classes | Server per class và filter | Static mutable store |
| Nhiều CI runner | Container/account per run | JUnit-only lock |
| Dynamic SMTP port | @DynamicPropertySource, lifecycle hợp lý | Bean giữ port cũ |
| Unicode subject | Đọc đúng MIME rồi assert decoded text | So sánh raw MIME toàn file |
| Provider sandbox | Account/recipient test riêng | Production recipients |

## 33. Bài tập suy luận

**Câu 1.** Test A gửi thư, test B xác nhận subject. Khi chạy riêng B bị fail. Nguyên nhân?

Test B phụ thuộc trạng thái test A. Một test độc lập phải tự chuẩn bị và kiểm tra hành vi của nó.

**Câu 2.** Hai test cùng gửi tới một mailbox, đều đọc phần tử 0. Có rủi ro gì?

Có thể đọc email của nhau hoặc thư cũ. Dùng correlation ID và SMTP server/namespace riêng.

**Câu 3.** Có nên gọi `deleteAllMessages` trên server dùng chung ở `@BeforeEach`?

Không. Có thể xóa email mà test khác vừa gửi. Reset toàn server chỉ khi test sở hữu riêng nó.

**Câu 4.** `@TestMethodOrder` có bảo đảm test độc lập khi chạy CI nhiều fork?

Không. Nó không loại bỏ state phụ thuộc và không phối hợp nhiều runner.

**Câu 5.** `@ResourceLock("mailbox")` có bảo vệ hai máy CI khác nhau?

Không, đó không phải distributed lock.

**Câu 6.** Worker async mất 3 giây trên CI; test sleep 1 giây rồi fail. Nên sửa gì?

Đợi theo message/correlation và deadline thay vì sleep cố định.

**Câu 7.** Spring `JavaMailSender` trỏ port test server đã stop. Cần xem phần nào?

Spring context cache, dynamic properties và lifecycle server.

**Câu 8.** Một thư có trong inbox nhưng correlation ID không khớp. Có coi test pass?

Không. Thư có thể do test khác tạo.

**Câu 9.** Test tạo outbox trong `@Transactional` rồi async worker không thấy row. Nên tăng sleep?

Không. Giải quyết commit/transaction visibility.

**Câu 10.** Test “không gửi” thấy inbox rỗng tức thì. Đã chứng minh nhánh async không gửi?

Chưa. Cần quan sát trạng thái cuối hoặc kiểm tra gateway call có kiểm soát.

**Câu 11.** Hai email của cùng request đến SMTP theo thứ tự khác nhau. Có phải bug?

Không nếu thứ tự không phải hợp đồng nghiệp vụ. Assert tập message đúng.

**Câu 12.** Unique constraint trên outbox có bảo đảm chỉ một SMTP message khi crash sau khi relay chấp nhận?

Không. DB và SMTP không có atomic commit chung.

## 34. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["JUnit test"] --> B["Tạo fixture + correlation ID riêng"]
    B --> C["SMTP server/namespace thuộc test"]
    C --> D["Gọi application use case"]
    D --> E["SMTP capture / outbox worker"]
    E --> F["Poll theo correlation ID"]
    F --> G{"Thấy đúng kết quả?"}
    G -->|"Chưa, chưa timeout"| F
    G -->|"Đúng"| H["Assert recipient, subject, MIME"]
    G -->|"Timeout"| I["Fail + diagnostic scoped"]
    H --> J["Cleanup tài nguyên của test"]
    I --> J
~~~

Những nguyên tắc quan trọng:

1. **Mỗi integration test tự chuẩn bị và kiểm tra dữ liệu của mình**, không phụ thuộc test trước.
2. **Không dùng `@Order` làm giải pháp mặc định** cho trạng thái mail dùng chung.
3. **Ưu tiên SMTP test server riêng** per method, per class hoặc container khi phù hợp.
4. **Khi phải chia sẻ server, correlation ID/recipient namespace là bắt buộc**, và không xóa mail của test khác.
5. **Không assert tổng inbox hoặc phần tử mới nhất** khi nhiều test có thể gửi.
6. **Async test phải đợi theo điều kiện**, không ngủ theo thời gian cố định.
7. **Spring context và SMTP server phải có lifecycle khớp nhau**, đặc biệt với dynamic port.
8. **Database/outbox fixture cũng phải được cô lập**, và worker chỉ đọc dữ liệu đã commit.
9. **JUnit resource lock chỉ bảo vệ phạm vi được quản lý**, không phải nhiều CI process.
10. **Test phủ định cần trạng thái kết thúc đáng tin**, vì chưa thấy mail ngay không chứng minh sẽ không gửi.
11. **Test retry/idempotency theo đúng hợp đồng**, không đòi SMTP exactly-once khi không có cơ chế hỗ trợ.
12. **Dùng sandbox/fake server**, tránh gửi email thật tới khách hàng trong automated tests.
13. **Cleanup và diagnostic theo ownership/correlation**, không dump hoặc xóa toàn mailbox.

Trong Spring Framework Mail, `JavaMailSender` chỉ thực hiện việc gửi tới transport được cấu hình. **Integration test chịu trách nhiệm biết mình sở hữu mailbox nào, thông điệp nào thuộc về mình và khi nào có đủ bằng chứng để assert**. Khi cô lập tài nguyên và không dựa vào thứ tự test, cùng một bộ kiểm thử có thể chạy đơn lẻ, chạy cả suite hoặc chạy song song trên CI mà ít bị ảnh hưởng bởi email và trạng thái không liên quan.
