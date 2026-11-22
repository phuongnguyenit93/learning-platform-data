# Dọn message và tài nguyên giữa các test

Trong **kiểm thử tích hợp Spring Framework Mail**, ứng dụng thường gửi email qua một SMTP server thử nghiệm như GreenMail, Mailpit hoặc MailHog. Khác với unit test chỉ dùng Mockito, integration test có thể mở socket, gửi lệnh SMTP thật, ghi email vào mailbox của server giả lập, tạo file đính kèm, ghi job vào database và chạy worker bất đồng bộ.

Những tài nguyên này có **vòng đời vượt ra ngoài một assertion đơn lẻ**. Nếu test thứ nhất để lại email hoặc job, test thứ hai có thể đọc nhầm kết quả cũ. Nếu SMTP server hoặc kết nối mạng không được đóng, bộ test tiếp theo có thể không bind được port. Nếu file tạm hoặc executor chưa dừng, CI có thể rò rỉ tài nguyên, chạy chậm hoặc thất bại ngẫu nhiên.

Vì vậy, ngoài việc kiểm tra email gửi đúng, mỗi integration test cần có **chiến lược cô lập và dọn dẹp trạng thái**: message đã nhận, mailbox, database/outbox, hàng đợi, task bất đồng bộ, socket/transport, file/stream và những thành phần đã khởi động cho test.

Ví dụ vấn đề:

~~~text
Test A: send order confirmation
  -> SMTP inbox có 1 mail
  -> Test A kết thúc nhưng inbox chưa được xóa

Test B: send password reset
  -> SMTP inbox có 2 mail
  -> assertEquals(1, receivedMessages.length) thất bại

Test B không sai ở logic gửi, nhưng sai vì state từ Test A.
~~~

Mục tiêu bài học là làm cho test **độc lập, có thể chạy lại, dọn được dù assertion thất bại**, và không vô tình xóa tài nguyên đang được test khác sử dụng.

## 1. Những loại trạng thái cần dọn

Một email integration test có thể chạm nhiều lớp:

| Lớp | Ví dụ trạng thái còn lại | Hậu quả nếu không dọn |
| --- | --- | --- |
| SMTP test server | Email trong mailbox nhận | Test sau đếm nhầm message |
| SMTP protocol/session | Connection hoặc server chưa dừng | Port bị chiếm, socket/resource leak |
| Application mail job | Outbox row `PENDING`, `RETRY_WAIT` | Worker gửi lại ở test sau |
| Database nghiệp vụ | Order/customer/notification state | Test phụ thuộc thứ tự |
| Queue/broker | Message chưa được consume, retry/delayed message | Event cũ kích hoạt mail mới |
| Scheduler/async executor | Task gửi chưa hoàn tất | Mail tới sau khi đã clear inbox |
| Filesystem | PDF, ảnh inline, thư mục upload, file tạm | Rò rỉ disk, nhầm attachment |
| Stream | `InputStream`, `OutputStream` | File lock và descriptor leak |
| Spring context | Bean singleton, cache, scheduler, connection pool | State chia sẻ ngoài dự kiến |
| Test doubles | Mock invocation/state, stub HTTP server requests | Assertion bị ảnh hưởng bởi lượt trước |
| Provider sandbox | Mailbox/event/API request còn tồn tại | Kết quả lẫn giữa nhiều job |

Không phải bài test nào cũng có tất cả những thành phần trên. Hãy xác định **tài nguyên thực sự được tạo** và người sở hữu vòng đời của nó.

### 1.1. Dọn đúng thứ, đúng phạm vi

Một quy tắc hữu ích:

> Component nào tạo hoặc sở hữu tài nguyên, component đó cần có cơ chế đóng/dọn tương ứng; test phải chỉ rõ phần tài nguyên nào thuộc phạm vi của mình.

Ví dụ:

- Test tự khởi động GreenMail → test có trách nhiệm dừng GreenMail.
- Test dùng GreenMail chung toàn class → từng method dọn mailbox, class dừng server.
- Test tạo outbox row bằng `testRunId` → xóa/khôi phục những row của chính test, không `TRUNCATE` database đang được dùng chung.
- Test dùng Testcontainers container do JUnit extension quản lý → không tự stop giữa các method nếu container thuộc phạm vi class/suite.
- Test tạo file bằng `@TempDir` → để JUnit dọn sau khi đã kết thúc mọi thao tác đọc file.

**Không chạy lệnh xóa hàng loạt trên SMTP server/DB dùng chung với môi trường thật.** Các thao tác purge/delete trong bài chỉ dành cho hạ tầng kiểm thử được xác nhận là cô lập.

## 2. Test isolation: mới mỗi test hay dùng chung rồi dọn?

Có ba cách phổ biến:

| Chiến lược | SMTP server | Mailbox giữa test | Ưu điểm | Nhược điểm |
| --- | --- | --- | --- | --- |
| **Per-test instance** | Khởi động/stop cho mỗi method | Mới hoàn toàn | Cô lập cao, ít phụ thuộc thứ tự | Tốn thời gian startup |
| **Per-class instance** | Một server cho cả test class | Purge giữa methods | Cân bằng tốc độ và cô lập | Cần xử lý song song/async |
| **Shared suite/container** | Một server cho nhiều classes | Định danh/namespace riêng hoặc purge có khóa | Nhanh cho bộ test lớn | Dễ race nếu purge toàn cục |

Lựa chọn nên dựa trên thời gian khởi động và yêu cầu chạy song song:

- Với vài test SMTP nhỏ, **per-test** thường đơn giản và dễ tin cậy nhất.
- Với nhiều method dùng cùng một server trong một class, **per-class + purge** có thể tiết kiệm thời gian.
- Với một Mailpit/Testcontainers chung cho nhiều class, **test-specific correlation ID và filter** thường an toàn hơn việc xóa toàn bộ message giữa các test chạy đồng thời.

### 2.1. “Dọn sau test” khác “dọn trước test”

- **Before-test cleanup** giúp test bắt đầu từ trạng thái đã biết, kể cả khi lần chạy trước bị hủy bất thường.
- **After-test cleanup** giải phóng tài nguyên ngay sau test, kể cả khi assertion ném exception, và hạn chế ảnh hưởng đến test sau.

Khi dùng shared fixture tuần tự, có thể dùng cả hai:

~~~text
@BeforeEach -> đảm bảo mailbox sạch
run test   -> gửi và assert
@AfterEach  -> xóa message test tạo
~~~

Tuy nhiên, nếu **nhiều test chạy song song trên cùng server**, purge toàn bộ trong `@BeforeEach` hoặc `@AfterEach` của test A có thể xóa message của test B. Dọn dẹp phải phù hợp với **scope và concurrency**.

## 3. Vòng đời tài nguyên với JUnit 5

JUnit Jupiter có các callback thường dùng:

| Hook | Thời điểm | Thường dùng cho |
| --- | --- | --- |
| `@BeforeEach` | Trước từng test method | Tạo mailbox/session, reset state |
| `@AfterEach` | Sau từng test method | Dọn message, file, reset fake state |
| `@BeforeAll` | Trước các method trong class | Start SMTP server dùng chung |
| `@AfterAll` | Sau các method trong class | Stop SMTP server, giải phóng pool |
| `@TempDir` | JUnit cấp thư mục tạm | Chứa attachment/files do test sở hữu |
| `@TestInstance(PER_CLASS)` | Cho phép lifecycle instance theo class | Instance `@BeforeAll` và `@AfterAll` |
| `@ResourceLock` | Đồng bộ test chia sẻ resource theo tên | Tránh purge/gửi song song vào server chung |

Một sơ đồ:

~~~mermaid
sequenceDiagram
    participant J as JUnit
    participant T as Test
    participant S as SMTP Test Server
    J->>T: BeforeEach
    T->>S: Start/prepare isolated mailbox
    J->>T: Execute test
    T->>S: Send + inspect messages
    J->>T: AfterEach
    T->>S: Purge/stop/close
    Note over J,S: Cleanup cũng cần chạy khi assertion thất bại
~~~

Các hook teardown giúp tránh trường hợp assertion thất bại làm code sau assertion không được thực hiện. Tuy nhiên, khi JVM bị kill hoặc runner bị kết thúc cưỡng bức, không thể đảm bảo callback sẽ chạy; đó là lý do cần cô lập môi trường, thời hạn sống của container và cơ chế cleanup dự phòng.

## 4. Ví dụ đầy đủ: mỗi test có GreenMail riêng

Một mẫu dễ hiểu là dùng GreenMail làm SMTP server thử nghiệm trong bộ nhớ. Trong ví dụ sau:

- JUnit khởi động GreenMail trước mỗi test;
- server bind vào `127.0.0.1` và cổng động, tránh va chạm cổng cố định;
- `JavaMailSenderImpl` gửi SMTP thật đến GreenMail;
- test kiểm tra `getReceivedMessages()`;
- `@AfterEach` dừng server, kể cả khi test thất bại.

### 4.1. Dependency minh họa

Với Spring Boot 3 / Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // Chọn bản GreenMail tương thích Jakarta Mail/JDK dự án.
    testImplementation 'com.icegreen:greenmail:<compatible-version>'
}
~~~

`<compatible-version>` là placeholder cần thay bằng phiên bản thực sự được quản lý trong build. Không trộn GreenMail phiên bản dùng `javax.mail` với code chạy `jakarta.mail` nếu chúng không tương thích.

### 4.2. Test class

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.*;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class SimpleMailIntegrationTest {
    private GreenMail greenMail;
    private JavaMailSenderImpl sender;

    @BeforeEach
    void setUp() {
        ServerSetup setup = new ServerSetup(
                0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP);

        greenMail = new GreenMail(setup);
        greenMail.start();

        sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(greenMail.getSmtp().getPort());
        sender.setProtocol("smtp");
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "false");
        props.put("mail.smtp.connectiontimeout", "3000");
        props.put("mail.smtp.timeout", "3000");
        props.put("mail.smtp.writetimeout", "3000");
    }

    @AfterEach
    void tearDown() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }

    @Test
    void sendsOneMessageToIsolatedMailbox() throws Exception {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("notifications@example.test");
        mail.setTo("alice@example.test");
        mail.setSubject("Order A123");
        mail.setText("Order A123 confirmed");

        sender.send(mail);

        assertTrue(
                greenMail.waitForIncomingEmail(5_000L, 1),
                "Expected one SMTP message in test server");

        MimeMessage[] messages = greenMail.getReceivedMessages();
        assertEquals(1, messages.length);
        assertEquals("Order A123", messages[0].getSubject());
    }
}
~~~

**Điểm quan trọng của ví dụ:** `JavaMailSenderImpl` là implementation thật, không phải Mockito mock. SMTP server là tiến trình/test component cục bộ, không phải email provider production. `greenMail.stop()` giải phóng listener/socket và mailbox gắn với instance đó sau test.

Port `0` yêu cầu hệ điều hành cấp cổng trống. Cách đọc port thực tế bằng `getSmtp().getPort()` phù hợp với API của GreenMail được ví dụ sử dụng; với phiên bản cụ thể, hãy dùng accessor được thư viện hỗ trợ.

### 4.3. Vì sao per-test instance ít bị ô nhiễm trạng thái?

~~~text
test A:
  GreenMail A -> 1 message -> stop A

test B:
  GreenMail B -> 0 message lúc bắt đầu -> stop B
~~~

Test B không cần gọi purge mailbox của A; nó có một server mới. Nếu JUnit chạy hai method song song, mỗi method vẫn dùng **instance và port riêng**. Nhưng những dữ liệu khác như database singleton hoặc queue chung vẫn cần được cô lập độc lập.

### 4.4. Teardown phải xử lý mọi tài nguyên đã tạo

Nếu một test còn tạo attachment file hoặc executor riêng, `greenMail.stop()` chưa đủ. Nên đóng/stop toàn bộ theo thứ tự thích hợp:

~~~text
Stop producing new mail
  -> wait/cancel background tasks
  -> release message/stream references
  -> stop SMTP server
  -> delete test files
~~~

Thứ tự có thể khác nếu tài nguyên có dependency khác nhau; nguyên tắc là không xóa file hoặc server **trong khi một tác vụ vẫn đang sử dụng chúng**.

## 5. Dùng một GreenMail cho toàn test class

Nếu startup SMTP server tốn thời gian, có thể dùng server một lần cho tất cả methods, sau đó **purge mailbox giữa các test**.

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.SAME_THREAD)
class SharedGreenMailIntegrationTest {
    private GreenMail greenMail;

    @BeforeAll
    void startServer() {
        greenMail = new GreenMail(new ServerSetup(
                0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP));
        greenMail.start();
    }

    @BeforeEach
    void clearBefore() {
        greenMail.purgeEmailFromAllMailboxes();
    }

    @AfterEach
    void clearAfter() {
        greenMail.purgeEmailFromAllMailboxes();
    }

    @AfterAll
    void stopServer() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }
}
~~~

Đây là **mẫu lifecycle**; test methods và `JavaMailSender` cấu hình tới port server được bổ sung theo ứng dụng. API `purgeEmailFromAllMailboxes()` xóa các message trong mailbox do GreenMail instance quản lý, không cần dừng/start lại SMTP server.

### 5.1. Lưu ý khi purge all

Chỉ gọi purge toàn bộ nếu:

1. SMTP server thuộc riêng class/suite được kiểm soát.
2. Không có test khác đang chạy trên cùng mailbox/server.
3. Không còn worker bất đồng bộ gửi mail từ test trước.
4. Không có job/queue cũ có thể đẩy mail vào inbox sau khi purge.

Nếu điều kiện 2 hoặc 3 không đúng, inbox có thể sạch lúc `@BeforeEach` nhưng lại nhận mail cũ vài mili giây sau đó.

### 5.2. Không dừng server chung sau từng method

Sai với instance dùng chung:

~~~java
@AfterEach
void tearDown() {
    greenMail.stop();
}
~~~

nếu `@BeforeAll` chỉ start một lần. Method sau sẽ kết nối tới server đã dừng. Phải phân biệt **xóa message** với **stop server**:

~~~text
per-class server:
  BeforeAll -> start
  BeforeEach/AfterEach -> purge state
  AfterAll -> stop
~~~

### 5.3. Purge chỉ xóa mailbox, không xóa toàn hệ thống

`purgeEmailFromAllMailboxes()` không tự:

- xóa outbox job trong database;
- dừng scheduler;
- xóa message trong RabbitMQ/Kafka;
- đóng file/stream;
- xóa Mailpit container khác;
- dọn Spring bean singleton cache;
- hủy retry đã lên lịch.

Do đó phải có kế hoạch cleanup đồng bộ cho các thành phần sản sinh email.

## 6. Khi dùng Spring Boot context và SMTP test server

Một integration test `@SpringBootTest` thường lấy `JavaMailSender` từ application context. Khi đó cấu hình host/port phải trỏ đến **server test đã được khởi động trước khi context tạo sender**.

Một cách là kết hợp `@DynamicPropertySource` với server có vòng đời class:

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class SpringBootMailIntegrationTest {
    private static final GreenMail SMTP = new GreenMail(
            new ServerSetup(
                    0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP));

    static {
        SMTP.start(); // Trước khi Spring cần dynamic properties.
    }

    @DynamicPropertySource
    static void mailProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.mail.host", () -> "127.0.0.1");
        registry.add("spring.mail.port",
                () -> SMTP.getSmtp().getPort());
        registry.add("spring.mail.properties[mail.smtp.auth]",
                () -> "false");
        registry.add(
                "spring.mail.properties[mail.smtp.starttls.enable]",
                () -> "false");
    }

    @Autowired
    InvoiceNotificationService invoiceNotifications;

    @BeforeEach
    void emptyMailboxes() {
        SMTP.purgeEmailFromAllMailboxes();
    }

    @Test
    void sendsInvoiceNotification() throws Exception {
        invoiceNotifications.sendTestInvoice(
                "alice@example.test", "INV-123");

        assertTrue(SMTP.waitForIncomingEmail(5_000L, 1));
        assertEquals(1, SMTP.getReceivedMessages().length);
    }

    @AfterAll
    static void stopSmtp() {
        SMTP.stop();
    }
}
~~~

`InvoiceNotificationService` và `sendTestInvoice(...)` là code ứng dụng minh họa, không phải API có sẵn của Spring. Với dự án có nhiều sender bean hoặc configuration profile riêng, cần map những property tương ứng vào cấu hình thật.

### 6.1. Tại sao khởi động server trong static initializer?

`@DynamicPropertySource` cần truy cập port thật khi Spring tạo context. Nếu đợi đến `@BeforeEach` mới start server, context có thể đã được tạo và sender đã lấy port khác/chưa tồn tại.

Một số phiên bản/library có lifecycle khác nhau; phần quan trọng là **SMTP test server phải sẵn sàng trước khi property được resolve và bean SMTP được sử dụng**.

### 6.2. Tại sao có @DirtiesContext?

Spring Test cache application context để tăng tốc. Nếu context của class A trỏ tới port của GreenMail A, nhưng A stop server sau `@AfterAll`, một test class B tái sử dụng context ấy có thể vẫn trỏ tới port đã đóng.

`@DirtiesContext(classMode = AFTER_CLASS)` báo rằng context class này không nên tiếp tục được tái sử dụng sau khi test kết thúc. Đây là một lựa chọn để tránh context cache giữ cấu hình động đã hết hiệu lực.

Tuy nhiên, `@DirtiesContext` có chi phí khởi tạo Spring context mới; không nên thêm nó vào mọi test nếu không có lý do. Thiết kế lifecycle Testcontainers/Spring context có thể cho phép một server giữ sống cùng vòng đời context mà không cần làm bẩn context sau mỗi method.

### 6.3. Không tắt TLS ở production

Trong ví dụ, `mail.smtp.starttls.enable=false` chỉ đúng khi local test server chạy SMTP plaintext trên loopback theo thiết kế test. Production cần TLS/STARTTLS, xác thực và hostname verification phù hợp provider.

Đừng copy cấu hình test này vào `application-prod.yml` chỉ để test pass.

## 7. Mailpit/MailHog và Testcontainers

Một số nhóm thay GreenMail bằng Mailpit hoặc MailHog để có web UI và API quản trị mailbox. Khi chạy bằng Testcontainers, các lớp trạng thái gồm:

1. **Container/process** Mailpit/MailHog.
2. **Message store** trong container.
3. **Host port mappings** từ Docker.
4. **Spring application context** đang trỏ tới SMTP host/port.
5. **Test messages** của từng scenario.

Ví dụ kiến trúc:

~~~text
JUnit / Spring Test
      |
      +--> Testcontainers Mailpit
      |       SMTP listener (container port)
      |       HTTP API/UI (container port)
      |
      +--> Spring JavaMailSender
              -> mapped SMTP host/port

AfterEach:
  API delete messages owned by this test,
  or purge mailbox only if server is not shared concurrently

AfterAll / container lifecycle:
  Testcontainers stops container and releases ports
~~~

### 7.1. Mẫu Testcontainers

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@Testcontainers
class MailpitContainerIntegrationTest {

    // Thay <approved-version> bằng image tag đã được dự án duyệt.
    @Container
    static final GenericContainer<?> MAILPIT =
            new GenericContainer<>(
                    DockerImageName.parse(
                            "axllent/mailpit:<approved-version>"))
                    .withExposedPorts(1025, 8025);

    @DynamicPropertySource
    static void smtpProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.mail.host", MAILPIT::getHost);
        registry.add(
                "spring.mail.port", () -> MAILPIT.getMappedPort(1025));
    }

    @Test
    void testSendingToMailpit() {
        // Gọi service, tra cứu message bằng Mailpit test client/API.
    }
}
~~~

Ví dụ này minh họa vòng đời container và cổng ánh xạ; chưa chứa phần query/purge HTTP API vì endpoint và cách xác thực cần theo phiên bản Mailpit được dùng. Nếu dùng `@SpringBootTest`, cần cấu hình class đó và các property authentication/TLS cho test server tương ứng.

`<approved-version>` là placeholder, không phải image tag chạy được. Với CI, nên **pin** một phiên bản đã được kiểm thử thay vì dùng `latest` để tránh thay đổi đột ngột.

### 7.2. Dọn message qua API

Một test helper có thể cung cấp interface:

~~~java
public interface TestMailboxClient {
    void deleteMessagesOwnedBy(String testRunId);
    List<TestMailSummary> findMessagesByCorrelationId(
            String correlationId);
}
~~~

Implementation dùng API của Mailpit/MailHog/provider sandbox tương ứng, xác thực theo môi trường test. **Không tự đoán URL xóa toàn bộ** của mọi công cụ: endpoint, quyền, cú pháp filter và hỗ trợ batch có thể khác theo version.

Nếu tool chỉ hỗ trợ purge all mà container được chia sẻ giữa các test, có thể chọn một trong các hướng:

- chạy các test liên quan tuần tự bằng resource lock;
- cấp container riêng cho từng test class;
- tách mailbox namespace theo test;
- lưu test ID và chỉ xóa những message của test nếu API có hỗ trợ.

### 7.3. Teardown container không thay thế cleanup DB

Testcontainers có thể tự stop container theo lifecycle, nhưng database/outbox của ứng dụng có thể còn chạy ở một container/service khác. Nếu worker vẫn giữ job PENDING, lần chạy test khác hoặc sau khi restart có thể gửi mail vào container mới.

Phải dọn **nguồn sinh message**, không chỉ dọn inbox nhận message.

## 8. Dùng correlation ID để cô lập message

Purge toàn bộ mailbox không phải lúc nào cũng an toàn. Khi dùng một SMTP test server chung, nên gắn **ID riêng của từng test** vào message hoặc metadata.

Ví dụ:

~~~text
X-Test-Run-Id: it-20261112-7c3b
X-Correlation-Id: order-A123-test-7c3b
~~~

Trong một test integration:

1. Tạo `testRunId` mới.
2. Gọi use case có thể liên kết message với ID đó.
3. Chờ message thuộc đúng `testRunId`.
4. Assert chỉ những message matching ID.
5. Xóa những message thuộc test, nếu API và quyền cho phép.

Điều này giúp tránh assertion phụ thuộc tổng số email của mọi test:

~~~java
assertEquals(
        1,
        mailbox.findMessagesByCorrelationId(testRunId).size()
);
~~~

Thay vì:

~~~java
assertEquals(
        1,
        mailbox.getAllMessages().size()
);
~~~

### 8.1. Có nên đặt header test-only trong production message?

Một custom header test có thể hữu ích, nhưng không nên khiến code production tự gửi thông tin test ID hoặc dữ liệu bí mật trong header. Các phương án:

- inject correlation ID là tính năng tracing đã được sản phẩm cho phép;
- dùng một recipient mailbox riêng, tạo theo test hoặc tenant test;
- dùng message/job ID trong kho nội bộ rồi tra từ provider test API;
- cấu hình một decorator sender **chỉ hoạt động dưới test profile** để gắn marker.

Không để header như `X-Test-Run-Id` mang dữ liệu cá nhân, secret hoặc token. Nếu test ID có thể xuất hiện trong log/SMTP message, chỉ dùng giá trị opaque ngắn hạn.

### 8.2. Filter theo recipient chưa chắc đủ

Chỉ dùng `test@example.test` cho mọi test khiến thư vẫn lẫn nhau. Nếu muốn filter theo recipient, mỗi test hoặc nhóm test nên có address/alias riêng theo chính sách server test hỗ trợ, ví dụ:

~~~text
order-7c3b@example.test
reset-9a4d@example.test
~~~

Không giả định mọi mailbox server xử lý plus-addressing hoặc wildcard mailbox giống nhau. Hãy kiểm tra API và cấu hình của test tool.

## 9. Bẫy bất đồng bộ: mail tới sau khi cleanup

Ví dụ hệ thống có `@Async` hoặc background mail worker:

~~~text
T1 Test publish OrderConfirmedEvent
T2 Test đọc inbox: hiện 0 mail
T3 Test @AfterEach purge mailbox
T4 Worker mới chạy và gửi mail
T5 Test kế tiếp bắt đầu, inbox đã có mail cũ
~~~

Đây là nguyên nhân flaky test rất phổ biến. **Clear mailbox không đồng nghĩa đã hết nguồn gửi mail.**

### 9.1. Đợi đúng sự kiện/điều kiện thay vì sleep cố định

Không nên:

~~~java
Thread.sleep(2000);
assertEquals(1, greenMail.getReceivedMessages().length);
~~~

Hai giây có thể quá dài trên máy nhanh hoặc quá ngắn trên CI chậm. Nên dùng điều kiện với timeout hữu hạn.

Với GreenMail:

~~~java
assertTrue(greenMail.waitForIncomingEmail(5_000L, 1));
assertEquals(1, greenMail.getReceivedMessages().length);
~~~

Với một kho async/outbox và thư viện chờ điều kiện như Awaitility:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() -> {
        assertEquals(
                1,
                mailbox.findMessagesByCorrelationId(testRunId).size()
        );
    });
~~~

`await()` là API của Awaitility nếu dự án dùng dependency đó. Cần import `org.awaitility.Awaitility.await` và `java.time.Duration`. Đây là minh họa cách chờ theo **condition**, không phải bắt buộc thêm Awaitility cho mọi test.

### 9.2. Chờ cả nguồn phát sinh đã yên

Chỉ chờ “nhận 1 email” chưa đủ nếu một worker vẫn đang chạy và có thể gửi email thứ hai.

Với workflow quan trọng, điều kiện kết thúc test có thể gồm:

~~~text
Job thuộc testRunId:
  status terminal (SUBMITTED hoặc FAILED_FINAL)

Worker:
  không còn attempt active cho testRunId

Mailbox:
  nhận đủ message thuộc testRunId
~~~

Sau đó mới purge và teardown server. Nếu application dùng retry queue, kiểm tra những delayed retries còn chờ và chủ động hủy/dọn theo testRunId.

### 9.3. Cẩn trọng với @Async và Spring context

Nếu `@Async` chạy trên một executor thuộc Spring context, việc stop SMTP server trước khi executor kết thúc có thể tạo connection refused hoặc lỗi trong log sau test.

Test có thể:

- cấu hình executor riêng cho test để theo dõi task;
- dùng latch hoặc test hook ở mức application để biết job đã terminal;
- tắt scheduler không liên quan bằng test profile;
- chờ completion có timeout, rồi mới cleanup;
- tránh dùng executor global/static không quản lý lifecycle.

Không nên “giải quyết” bằng `Thread.sleep(...)` hoặc bỏ qua lỗi teardown.

## 10. Dọn outbox và database giữa các test

Trong ứng dụng Spring Mail có transactional outbox:

~~~text
Database transaction
  -> INSERT order
  -> INSERT mail_outbox
  -> COMMIT

MailWorker
  -> scan/claim outbox
  -> SMTP send
  -> update status
~~~

Nếu test dọn inbox nhưng không dọn `mail_outbox`, job cũ có thể tiếp tục được worker xử lý. Nếu chỉ xóa outbox nhưng worker đã claim message, worker có thể vẫn đang giữ payload và gửi sau đó.

### 10.1. Transaction rollback trong test không thu hồi email

Spring test có thể đánh dấu method `@Transactional` và tự rollback dữ liệu khi test kết thúc. Nhưng SMTP submission là tác động bên ngoài database:

~~~text
BEGIN test transaction
UPDATE order
SMTP send (server đã nhận mail)
ROLLBACK database

Database: không còn order
Mailbox: email vẫn tồn tại
~~~

Vì vậy, **@Transactional test rollback không thay thế SMTP mailbox cleanup**.

### 10.2. AFTER_COMMIT không chạy nếu test rollback

Nếu ứng dụng gửi email qua `@TransactionalEventListener(phase = AFTER_COMMIT)`, một test được Spring Test rollback mặc định có thể không kích hoạt listener.

Để test hành vi commit:

- dùng `TransactionTemplate` và để transaction thực commit;
- hoặc cấu hình `@Commit` cho scenario phù hợp;
- hoặc thực thi use case ngoài một test-level transaction đang rollback.

Sau đó phải dọn dữ liệu đã **commit**, không kỳ vọng Spring tự rollback chúng.

### 10.3. Chọn cơ chế cleanup database

Các cách thường gặp:

| Cách | Phù hợp | Cần chú ý |
| --- | --- | --- |
| Test transaction rollback | Dữ liệu thay đổi trong test transaction | Không rollback SMTP/broker side effects |
| `@Sql` cleanup | Dữ liệu đã commit và có schema ổn định | Thứ tự foreign key, transaction mode |
| Repository delete by testRunId | Shared DB có namespace theo test | Không xóa bản ghi người khác |
| Testcontainers DB riêng | Cô lập DB cấp class/suite | Startup time, context lifecycle |
| DB/schema per test | Cô lập mạnh nhất | Cần migrations và cấu hình dynamic datasource |
| Database cleaner có kiểm soát | Test DB độc lập | Không dùng trên database shared/prod |

Ví dụ minh họa `@Sql` cho **database test đã cô lập**:

~~~java
@Sql(
    statements = {
        "DELETE FROM mail_attempt WHERE test_run_id = 'test-344'",
        "DELETE FROM mail_outbox WHERE test_run_id = 'test-344'",
        "DELETE FROM orders WHERE test_run_id = 'test-344'"
    },
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
~~~

Trong thực tế, test ID thường sinh động; `@Sql` static như trên chỉ phù hợp nếu fixture có ID cố định hoặc dùng schema riêng. Nếu `testRunId` sinh mỗi test, hãy dùng repository/JdbcTemplate với prepared parameters để xóa chính xác các row tương ứng. Cần hiểu phase, transaction và foreign-key constraints của ứng dụng.

### 10.4. Thứ tự cleanup khi có worker

Một trình tự an toàn thường là:

1. Dừng hoặc ngăn job mới thuộc test.
2. Chờ các attempts đang chạy hoàn tất hoặc bị hủy có kiểm soát.
3. Xóa retry/delayed tasks của test.
4. Xóa các outbox/event/attempt rows thuộc test theo đúng FK order.
5. Xóa email test trong SMTP mailbox.
6. Giải phóng resource/connection/file.

Không xóa outbox row đang được một worker giữ reference mà không có cơ chế coordination. Nếu worker vẫn gửi sau khi cleanup, test tiếp theo lại bị ô nhiễm trạng thái.

## 11. Dọn queue và broker giữa các test

RabbitMQ, Kafka, Redis Streams hoặc queue nội bộ có thể giữ:

- event chưa consume;
- job retry đã schedule;
- message unacked/in-flight;
- dead-letter entry;
- consumer group offset/ack state;
- duplicate delivery.

Chỉ xóa mailbox không xử lý các trạng thái này.

### 11.1. Dùng queue riêng hoặc namespace theo test

Khi test song song, chiến lược tốt thường là:

~~~text
test A -> queue mail-test-A -> SMTP mailbox/tag A
test B -> queue mail-test-B -> SMTP mailbox/tag B
~~~

Nếu không thể có queue per test, dùng `testRunId` trong payload và cơ chế tìm/xóa job có scope. Nhưng Kafka hay một số broker không hỗ trợ “xóa tùy ý một event giữa stream” như database; có thể cần topic riêng, consumer group riêng hoặc container riêng.

### 11.2. Không purge queue dùng chung khi test chạy song song

~~~text
Test A creates job A
Test B purges shared queue
Test A waits -> timeout
~~~

Purge all là một thao tác **toàn cục**. Chỉ dùng khi queue được test đó sở hữu độc quyền hoặc toàn suite bảo đảm không có activity đồng thời.

### 11.3. Retry và dead-letter

Một job lỗi có thể được schedule lại sau vài giây/phút. Teardown phải:

- biết retry scheduler đang ở đâu;
- hủy/đánh dấu terminal job thuộc test;
- dọn delayed queue nếu broker hỗ trợ và ownership rõ;
- không để retry xuất hiện sau khi server test đã stop.

Với CI, các retry dài nên được điều chỉnh bằng **test profile** hoặc test clock/controllable scheduler để không cần đợi hàng phút thật. Nhưng test cần giữ đúng semantics, không vô tình bỏ mất hành vi retry đang kiểm thử.

## 12. Dọn file đính kèm và tài nguyên I/O

Email có attachment thường đọc từ file tạm, `InputStream` hoặc resource do ứng dụng tạo.

Ví dụ:

~~~java
helper.addAttachment(
        "invoice-A123.pdf",
        new FileSystemResource(file)
);
~~~

Trong nhiều implementation, attachment bytes có thể chỉ được đọc khi message được serialize/gửi. Nếu xóa file **ngay sau khi gọi `addAttachment(...)`** nhưng trước `sender.send(...)`, gửi mail có thể thất bại vì file không còn.

### 12.1. Dùng @TempDir

JUnit 5 có `@TempDir`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class AttachmentMailIntegrationTest {
    @TempDir
    Path tempDir;

    @Test
    void sendsPdfAttachment() throws Exception {
        Path pdf = tempDir.resolve("invoice-A123.pdf");
        Files.write(pdf, fakePdfBytes());

        // Service dùng file này để tạo MIME attachment và gửi SMTP.
        invoiceMailer.sendInvoice(
                "alice@example.test", pdf);

        // Chờ sender/worker hoàn tất trước khi test kết thúc.
        // JUnit dọn tempDir sau test theo lifecycle của @TempDir.
    }
}
~~~

`fakePdfBytes()` và `invoiceMailer` là fixture/service minh họa. Thư mục test phải nằm trên filesystem test, không dùng đường dẫn attachment production.

**Nếu mail gửi bất đồng bộ**, test phải chờ job đã đọc xong attachment trước khi kết thúc. Nếu không, JUnit có thể dọn `tempDir` trong khi worker vẫn đang đọc file.

### 12.2. ByteArrayResource có lợi khi attachment nhỏ

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] bytes = fakePdfBytes();
helper.addAttachment(
        "invoice-A123.pdf",
        new ByteArrayResource(bytes),
        "application/pdf"
);
~~~

`ByteArrayResource` giữ dữ liệu trong bộ nhớ và cho phép mở lại stream, thuận tiện với nhiều test MIME nhỏ. Cần hạn chế dùng cách này với file rất lớn vì tiêu tốn heap.

### 12.3. InputStreamResource và stream một lần

Một số resource bọc `InputStream` chỉ dùng được một lần. MIME/JavaMail có thể cần đọc stream ở thời điểm gửi hoặc serialization; nếu code đã đóng stream hoặc đọc hết, email có thể thiếu attachment.

Khi test:

- dùng `ByteArrayResource` cho dữ liệu nhỏ;
- hoặc dùng `FileSystemResource` và giữ file tồn tại tới khi send hoàn tất;
- nếu dùng custom `InputStreamSource`, phải tuân thủ contract có thể mở stream mới theo yêu cầu;
- đóng stream do test trực tiếp mở bằng `try-with-resources`;
- không giả định tạo `MimeMessage` đã đọc xong toàn bộ attachment.

### 12.4. Đóng stream đúng cách

~~~java
try (InputStream input =
        Files.newInputStream(tempFile)) {
    byte[] bytes = input.readAllBytes();
    // Dùng bytes để tạo fixture hoặc checksum kiểm tra.
}
~~~

Đối với luồng trả về từ `Part.getInputStream()`, cũng nên đóng bằng `try-with-resources` sau khi đọc.

### 12.5. Không xóa file đang thuộc worker khác

Một lỗi nghiêm trọng:

~~~java
@AfterEach
void cleanup() {
    deleteRecursively(sharedUploadDirectory);
}
~~~

nếu thư mục đó chứa attachment của nhiều test hoặc service khác. Chỉ xóa **thư mục con riêng theo testRunId** hoặc dùng `@TempDir` được JUnit cấp riêng.

## 13. Resource leak do transport và connection pool

Khi gửi bằng `JavaMailSenderImpl`, thư viện có thể mở SMTP transport, stream và socket. Nếu test trực tiếp dùng Jakarta Mail `Transport`, cần quản lý vòng đời của object.

Ví dụ:

~~~java
Transport transport = session.getTransport("smtp");
try {
    transport.connect(host, port, user, password);
    transport.sendMessage(
            mimeMessage,
            mimeMessage.getAllRecipients()
    );
} finally {
    if (transport.isConnected()) {
        transport.close();
    }
}
~~~

Đoạn này minh họa phần **low-level Jakarta Mail transport**; ứng dụng dùng `JavaMailSender.send(...)` thường không cần tự lấy/close `Transport` theo kiểu đó.

### 13.1. Những thứ không nên đóng quá sớm

- Không stop SMTP test server trước khi sender/worker hoàn tất.
- Không close DataSource được Spring context dùng chung sau mỗi test method.
- Không stop Testcontainers container do class/suite khác đang sử dụng.
- Không gọi `ExecutorService.shutdownNow()` lên một executor dùng chung không thuộc test sở hữu.
- Không xóa attachment file trước khi MimeMessage serialize/send xong.

Nguyên tắc là **đóng theo owner**, không đóng mọi object nhìn thấy được.

### 13.2. Server bị chiếm port

Triệu chứng:

~~~text
java.net.BindException: Address already in use
~~~

Thường liên quan:

- test trước không stop SMTP server;
- nhiều test cùng dùng port cố định;
- một process ngoài test đang chiếm port;
- class dùng shared server nhưng lifecycle start/stop không thống nhất.

Cách giảm:

- chọn cổng động nếu thư viện hỗ trợ;
- dùng container mapped port;
- bảo đảm `@AfterEach`/`@AfterAll` cleanup;
- tránh tạo nhiều server bằng một singleton static không được quản lý.

Không nên tự chọn một cổng ngẫu nhiên bằng code riêng rồi bind sau một khoảng thời gian dài: giữa bước kiểm tra và bind có thể phát sinh race. Cơ chế bind port `0` và đọc lại port đã cấp là lựa chọn tốt khi được hỗ trợ.

## 14. Test chạy song song và nguy cơ race

JUnit 5 có thể được cấu hình chạy tests song song. Một shared mailbox là **mutable global state**:

~~~text
Test A: send mail A
Test B: @BeforeEach purge inbox
Test A: assert mail A exists -> fail
~~~

Nếu muốn chạy song song, các lựa chọn ưu tiên:

1. Mỗi test có SMTP server/port riêng.
2. Mỗi class có container/mailbox riêng.
3. Cùng server nhưng mỗi test dùng recipient/correlation ID riêng và **không purge all**.
4. Với shared server không thể cô lập, chạy tuần tự bằng lock và lifecycle nhất quán.

### 14.1. ResourceLock

Ví dụ:

~~~java
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock(
        value = "shared-smtp-mailbox",
        mode = ResourceAccessMode.READ_WRITE)
class SharedMailboxIntegrationTest {
    // Các test class khác dùng cùng mailbox cũng phải
    // khai báo ResourceLock với cùng tên để phối hợp.
}
~~~

`@ResourceLock` chỉ có tác dụng với các test dùng cùng cơ chế khóa của JUnit. Nó không khóa các process CI độc lập hay những chương trình ngoài JUnit. Nếu chạy nhiều JVM/test runners dùng chung SMTP sandbox, cần cách cô lập ở cấp hạ tầng, không chỉ annotation.

### 14.2. Chạy tuần tự không giải quyết late async mail

Ngay cả khi mỗi method chạy lần lượt:

~~~text
Test A kết thúc khi async job chưa hoàn tất
Test B bắt đầu
Job A gửi email trong thời gian Test B chạy
~~~

Do đó vẫn cần chờ trạng thái job terminal hoặc ngăn task cũ, không chỉ đặt `@Execution(SAME_THREAD)`.

## 15. Kiểm tra không có email ngoài ý muốn

Một test có thể yêu cầu **không gửi mail** khi rollback hoặc validation thất bại:

~~~text
Given invalid recipient
When application rejects request
Then no mail is sent
~~~

Trong test đồng bộ, có thể kiểm tra inbox rỗng ngay sau khi lời gọi kết thúc. Nhưng với async workflow, `inbox.isEmpty()` tại một thời điểm chưa chứng minh task không gửi email muộn.

### 15.1. Negative assertions phải xác định cửa sổ quan sát

Một test tốt có thể:

1. Gọi use case.
2. Đợi application process/transaction đi tới trạng thái terminal.
3. Xác minh không có job gửi được tạo hoặc job bị đánh dấu canceled.
4. Xác minh không có message thuộc `testRunId` trong mailbox.

Nếu không có tín hiệu completion của hệ thống, phải ghi rõ giới hạn của negative assertion và dùng một cửa sổ chờ có timeout phù hợp; không biến “không thấy ngay” thành “sẽ không bao giờ gửi”.

### 15.2. Khi kiểm tra gửi đúng một lần

Nếu test cần assert chỉ có một message:

~~~java
assertEquals(
        1,
        mailbox.findMessagesByCorrelationId(testRunId).size()
);
~~~

hãy chắc rằng:

- event/worker đã xử lý xong;
- retry và delayed queue thuộc job đã terminal;
- correlation ID chỉ đại diện một logical request;
- test không đếm message của test khác.

Chỉ gọi `getReceivedMessages().length == 1` khi mailbox thật sự đã được cô lập hoặc dọn sạch phù hợp.

## 16. Kiểm soát thời gian bằng Clock và scheduler thử nghiệm

Một số mail được gửi sau delay:

~~~text
Order placed
  -> 15 phút sau gửi reminder
~~~

Nếu integration test cần kiểm tra cleanup, không hợp lý khi `Thread.sleep(15 minutes)`.

Có thể thiết kế:

- inject `Clock` để test xác định thời điểm;
- dùng scheduler có thể điều khiển trong test;
- giảm delay bằng test configuration nếu vẫn kiểm tra đúng behavior;
- lưu job với `nextAttemptAt` rồi kích hoạt worker có kiểm soát;
- đợi terminal state với timeout hữu hạn.

Quan trọng là cleanup phải tính đến **các tác vụ đã schedule nhưng chưa chạy**. Nếu test dọn database trước khi scheduler kích hoạt, worker có thể ném lỗi hoặc gửi message không còn phù hợp.

### 16.1. Hủy job retry theo testRunId

Một adapter có thể cung cấp:

~~~java
public interface TestMailJobs {
    void cancelPendingJobsFor(String testRunId);
    void awaitNoActiveAttemptsFor(
            String testRunId, Duration timeout);
    void deleteTerminalJobsFor(String testRunId);
}
~~~

Đây là **test support interface** do dự án định nghĩa, không phải API mặc định của Spring Mail. Nó tạo ra điểm đồng bộ rõ ràng giữa ứng dụng và cleanup, thay vì thao tác ngầm trên queue.

## 17. Teardown phải an toàn khi setup thất bại một phần

Giả sử `@BeforeEach`:

1. Start SMTP server thành công.
2. Start queue consumer thất bại.
3. Chưa tạo mail sender.

Nếu `@AfterEach` giả định mọi tài nguyên đều đã được tạo, cleanup có thể ném `NullPointerException` và che mất lỗi gốc.

Ví dụ:

~~~java
private GreenMail smtp;
private ExecutorService executor;

@AfterEach
void tearDown() {
    if (executor != null) {
        executor.shutdownNow(); // Chỉ executor thuộc test.
    }

    if (smtp != null) {
        smtp.stop();
    }
}
~~~

Trong thực tế, nên dừng executor theo chính sách có thời hạn: ngừng nhận task mới, chờ task đang làm, rồi force stop khi cần. `shutdownNow()` không bảo đảm dừng ngay mọi task và có thể bỏ dở thao tác mạng; ví dụ trên chỉ minh họa **null-safe teardown**.

### 17.1. Dùng try/finally cho tài nguyên cục bộ

Khi tài nguyên chỉ cần trong một method:

~~~java
GreenMail smtp = createAndStartTestSmtp();
try {
    // Arrange, act, assert.
} finally {
    smtp.stop();
}
~~~

`try/finally` là lựa chọn rõ ràng nếu không cần reuse fixture. Với nhiều resource, ưu tiên `AutoCloseable` hoặc JUnit extension khi thích hợp.

### 17.2. Tránh xóa dữ liệu trước khi thu thập chẩn đoán

Khi test fail, ta thường muốn biết:

- có bao nhiêu message được nhận;
- subject/recipient của message;
- worker/job state;
- SMTP response hoặc error code;
- correlation ID liên quan.

Nếu `@AfterEach` purge ngay, debugging có thể khó hơn. Có thể:

1. Dùng `TestWatcher` hoặc callback ở test extension để chụp **metadata an toàn** khi thất bại.
2. Sau đó purge/stop server.
3. Không lưu full raw message chứa PII/OTP/secret trong CI artifacts.

Đừng giữ tài nguyên sống vô hạn chỉ vì test thất bại; cần cleanup cả khi fail.

## 18. Một tiện ích test để quản lý lifecycle

Với nhiều test class, có thể gói logic start/cleanup/stop trong một fixture.

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class TestSmtpFixture implements AutoCloseable {
    private final GreenMail greenMail;
    private final JavaMailSenderImpl sender;

    public TestSmtpFixture() {
        greenMail = new GreenMail(new ServerSetup(
                0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP));
        greenMail.start();

        sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(greenMail.getSmtp().getPort());
        sender.setProtocol("smtp");
        sender.getJavaMailProperties()
                .put("mail.smtp.auth", "false");
    }

    public JavaMailSenderImpl sender() {
        return sender;
    }

    public GreenMail server() {
        return greenMail;
    }

    @Override
    public void close() {
        greenMail.stop();
    }
}
~~~

Sử dụng:

~~~java
@Test
void sendsOneMessage() throws Exception {
    try (TestSmtpFixture smtp = new TestSmtpFixture()) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("sender@example.test");
        mail.setTo("alice@example.test");
        mail.setSubject("Hello");
        mail.setText("Integration test");

        smtp.sender().send(mail);

        assertTrue(
                smtp.server().waitForIncomingEmail(5_000L, 1));
        assertEquals(
                1,
                smtp.server().getReceivedMessages().length);
    }
}
~~~

Fixture tập trung quyền sở hữu server và sender. Khi block kết thúc, `close()` được gọi ngay cả khi assertion thất bại. Nếu test tạo thêm DB/broker/file resources, có thể đưa chúng vào fixture hoặc một extension khác nhưng phải xác định rõ thứ tự teardown.

### 18.1. Một fixture không nên giữ state static không có scope

Không nên lưu một `static GreenMail` rồi cho tất cả tests gọi `purgeEmailFromAllMailboxes()` nếu suite chạy song song hoặc nhiều JVM.

Nếu cần chia sẻ để tăng tốc, thiết kế fixture ở scope class/suite, khóa truy cập hoặc partition trạng thái. **Một singleton không tự đồng nghĩa với một fixture an toàn.**

## 19. Các tình huống integration test cần cleanup khác nhau

| Tình huống | State quan trọng | Cleanup chủ yếu |
| --- | --- | --- |
| Gửi plain text một lần | SMTP mailbox | Stop server riêng hoặc purge |
| Gửi HTML có inline image | MIME + resource/stream | Chờ send; đóng I/O; dọn file |
| Gửi PDF từ `@TempDir` | File tạm + mailbox | Chờ hoàn tất rồi để JUnit dọn |
| Gửi qua `@TransactionalEventListener` | Transaction + event + mailbox | Commit test chủ đích; dọn DB/mailbox |
| Gửi bằng `@Async` | Executor + mailbox | Chờ task terminal, rồi purge |
| Gửi bằng transactional outbox | Outbox + worker + mailbox | Cancel/drain job; dọn DB; purge |
| Retry sau SMTP 4xx | Retry queue/delayed job | Hủy retries còn chờ theo test ID |
| Test SMTP auth failure | SMTP connection và logs | Stop server; không lưu credential |
| Test bounce webhook | Provider event + DB status | Dọn webhook fixture/DB, không chỉ inbox |
| Nhiều test song song | Shared mailbox/queue | Namespace, server riêng hoặc lock |
| Testcontainers SMTP | Container + HTTP inbox | Cleanup scoped messages, stop theo lifecycle |
| Test fail giữa chừng | Mọi resource đã tạo một phần | Teardown null-safe, diagnostics tối thiểu |

## 20. Lỗi thường gặp và nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Giải pháp |
| --- | --- | --- |
| Test thứ hai thấy 2 email thay vì 1 | Mailbox còn email từ test trước | Per-test server hoặc purge đúng scope |
| Có lúc test pass, có lúc fail | Worker async gửi muộn sau cleanup | Chờ terminal state, cô lập job |
| `Address already in use` | Server không stop hoặc cổng cố định | Teardown + dynamic port |
| Test pass cục bộ nhưng fail CI | Timing chậm, race, port clash | Bounded wait, test isolation |
| Test A mất message khi chạy song song | Test B purge shared mailbox | Server/recipient namespace hoặc resource lock |
| SMTP kết nối sai cổng | Context cache giữ dynamic port cũ | Quản lý context/server lifecycle |
| File attachment không tìm thấy | File bị xóa trước khi gửi | Chờ send hoàn tất, dùng `@TempDir` |
| Windows không xóa được file tạm | Stream/file handle chưa đóng | `try-with-resources` |
| Test rollback DB nhưng inbox vẫn có mail | SMTP không thuộc DB transaction | Cleanup mailbox riêng |
| AFTER_COMMIT không gửi trong test | Test transaction rollback mặc định | Commit trong scenario cần kiểm thử |
| Mail cũ xuất hiện sau khi purge | Retry/outbox job chưa dọn | Ngăn nguồn gửi, cancel/drain retries |
| `@AfterEach` ném NPE | Setup không hoàn tất mọi bước | Null-safe cleanup |
| Stop container khiến test khác fail | Container dùng chung | Chỉ owner stop, scope đúng |
| Email từ test khác bị xóa | Purge all trên server shared | Delete by ID hoặc cô lập inbox |
| Negative assertion fail ngẫu nhiên | Không có tín hiệu async completion | Chờ workflow terminal |
| Raw email/OTP xuất hiện trong CI logs | Dump MimeMessage để debug | Log metadata, fixture giả |

## 21. Tình huống tổng hợp: test xác nhận đơn hàng qua outbox

Giả sử ứng dụng chạy:

~~~text
POST /orders/A123/confirm
   |
   v
Database transaction
   -> update order
   -> insert mail_outbox(key=order-confirmed:A123:evt-1)
   -> COMMIT
   |
   v
MailWorker
   -> create MimeMessage
   -> SMTP to GreenMail/Mailpit
   -> update job SUBMITTED
~~~

Test có thể sử dụng một `testRunId` riêng:

~~~text
testRunId = it-344-7c3b
orderId   = order-it-344-7c3b
mailKey   = order-confirmed:it-344-7c3b
recipient = order-it-344-7c3b@example.test
~~~

### 21.1. Arrange

1. Start SMTP server cô lập (hoặc chọn namespace mailbox riêng).
2. Trỏ Spring Mail sender vào SMTP server test.
3. Tạo database fixture với `testRunId`.
4. Đảm bảo scheduler/worker có thể xử lý job của test.
5. Xác nhận không có job/message cũ thuộc `testRunId`.

### 21.2. Act

Gọi use case xác nhận đơn hàng, để database transaction **commit** thật nếu cần test luồng outbox/AFTER_COMMIT.

### 21.3. Assert

Đợi:

~~~text
outbox job:
  status = SUBMITTED

SMTP mailbox:
  1 message thuộc testRunId

MimeMessage:
  To, From, Subject và body đúng
~~~

Không đếm tất cả mail trong mailbox chia sẻ nếu có nhiều test. Dùng correlation ID, recipient riêng hoặc fixture đã purge độc quyền.

### 21.4. Cleanup

1. Ngăn hoặc chờ worker đang xử lý `testRunId`.
2. Hủy retry/delayed job của test nếu còn.
3. Dọn attempt/outbox/order rows thuộc test.
4. Xóa SMTP message của test hoặc stop SMTP instance riêng.
5. Đóng I/O, dọn `@TempDir` sau khi gửi hoàn tất.
6. Dừng container/server theo vòng đời owner.

### 21.5. Vì sao thứ tự quan trọng?

Sai:

~~~text
purge mailbox
delete order
worker vẫn đang chạy
worker submit email
test B đọc thấy message của test A
~~~

Đúng hơn:

~~~text
chờ/hủy worker A
đảm bảo không còn retry A
cleanup DB A
purge mailbox A
stop server nếu A sở hữu server
~~~

Trình tự cụ thể có thể khác theo kiến trúc nhưng phải bảo đảm **không còn producer cũ** khi tuyên bố inbox đã sạch.

## 22. Checklist dọn message và tài nguyên

### Isolation

- [ ] SMTP server/mailbox có phạm vi sở hữu rõ ràng (per test/class/suite).
- [ ] Không dùng chung mailbox với production hoặc môi trường khác.
- [ ] Cổng SMTP test là cổng động hoặc được quản lý độc quyền.
- [ ] Nếu chạy song song, có namespace hoặc lock phù hợp.

### Message

- [ ] Before-test state được xác định: mailbox trống hoặc filter đúng `testRunId`.
- [ ] Assertions không tính nhầm email của test khác.
- [ ] After-test purge chỉ trong phạm vi được phép.
- [ ] Không xóa message trước khi hoàn tất thu thập kết quả cần kiểm tra.

### Async và dữ liệu

- [ ] Chờ job/attempt terminal trước cleanup.
- [ ] Hủy delayed retries và dọn outbox rows của test.
- [ ] Test DB rollback không bị nhầm là SMTP rollback.
- [ ] Với AFTER_COMMIT, scenario có commit thật khi cần.
- [ ] Không purge queue/broker dùng chung của test khác.

### Tài nguyên

- [ ] SMTP listener/container được stop bởi đúng owner.
- [ ] Stream/file handles được đóng.
- [ ] File attachment còn tồn tại cho đến khi MIME đã được gửi/serialize.
- [ ] Dùng `@TempDir` hoặc thư mục riêng theo test.
- [ ] Executor/scheduler do test tạo được shutdown theo lifecycle.

### Độ ổn định và an toàn

- [ ] Chờ bằng điều kiện với timeout, không `Thread.sleep` tùy tiện.
- [ ] Teardown chạy được cả khi test fail hoặc setup không hoàn chỉnh.
- [ ] Không log password, token, OTP hoặc PII không cần thiết.
- [ ] Dynamic port và Spring context cache có vòng đời nhất quán.
- [ ] Không suy ra delivery thật từ kết quả SMTP test server.

## 23. Những điều cần nhớ

- **SMTP mailbox là trạng thái có thể lưu lại giữa test**, cần được cô lập hoặc purge đúng cách.
- **Per-test server** đơn giản và dễ tránh ô nhiễm nhất; **per-class server** có thể nhanh hơn nhưng cần cleanup và kiểm soát concurrency.
- Dùng `@AfterEach`/`@AfterAll` hoặc `try/finally`/`AutoCloseable` để giải phóng tài nguyên dù assertion thất bại.
- `@Transactional` rollback chỉ áp dụng cho DB transaction, không xóa email đã gửi.
- Worker async, scheduler và retry queue có thể gửi mail **sau khi inbox đã được dọn**.
- Dọn nguồn sinh email (outbox/queue/task) trước khi tuyên bố mailbox sạch.
- `@TempDir` giúp quản lý attachment file, nhưng chỉ dọn sau khi worker không còn đọc file.
- Test chạy song song cần server/recipient namespace riêng hoặc resource lock; purge all trên server chia sẻ có thể phá test khác.
- `@DynamicPropertySource` và Spring context cache phải đồng bộ với vòng đời SMTP test server/container.
- Test integration với GreenMail/Mailpit kiểm tra **submission và nội dung đã nhận tại test server**, không chứng minh thư đã vào Inbox của người dùng thật.

Dọn message và tài nguyên giữa các test không chỉ là gọi một hàm `clearInbox()`. Một bộ kiểm thử tích hợp Spring Framework Mail đáng tin cậy phải xác định **ai sở hữu trạng thái, khi nào producer đã ngừng hoạt động và phạm vi nào được phép xóa**. Khi thiết kế đúng lifecycle SMTP server, mailbox, outbox, queue, worker và file đính kèm, các test trở nên độc lập, dễ chạy trên CI và ít gặp lỗi phụ thuộc thứ tự hay timing.

### Tài liệu tham khảo

- **Spring Framework Reference — Testing:** quản lý test context, transaction, SQL scripts và lifecycle.
- **Spring Boot Reference — Testing và Sending Email:** cấu hình mail sender trong integration tests.
- **Spring Framework API — JavaMailSender / JavaMailSenderImpl:** SMTP submission và các phương thức gửi.
- **JUnit 5 User Guide:** `@BeforeEach`, `@AfterEach`, `@BeforeAll`, `@AfterAll`, `@TempDir`, parallel execution và `@ResourceLock`.
- **GreenMail documentation:** embedded SMTP server, `getReceivedMessages`, `purgeEmailFromAllMailboxes` và server lifecycle.
- **Mailpit/MailHog documentation:** SMTP test inbox, API tìm/xóa message và container configuration.
- **Testcontainers for Java documentation:** container lifecycle, mapped ports, JUnit Jupiter integration.
- **Spring Test — DynamicPropertySource và DirtiesContext:** cấu hình port động và ứng dụng context cache.
- **Jakarta Mail API — MimeMessage, Multipart, Transport:** MIME message và quản lý tài nguyên mail.
- **Awaitility documentation:** bounded waiting khi kiểm thử workflow bất đồng bộ.
