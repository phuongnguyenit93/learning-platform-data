# Không đưa bí mật vào event payload

## 1. Vì sao một event có thể làm lộ bí mật?

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(...)` công bố một object để các listener quan tâm có thể phản ứng. Một `CredentialRotated` có thể được quan sát bởi audit, metrics, notification, outbox bridge hoặc các listener được thêm sau này:

~~~text
CredentialService
      |
      +-- publishEvent(CredentialRotated)
                  |
                  +-- AuditListener
                  +-- MetricsListener
                  +-- NotificationListener
                  +-- @Async SecurityListener
                  +-- Outbox/Broker Bridge (nếu có)
~~~

Nếu payload có password, token hoặc API key, bí mật có thể đi vào **mọi listener nhận event**, rồi tới log, tracing, queue, database outbox, backup, dead-letter queue (DLQ) và các dịch vụ tích hợp. Một lệnh `log.info("event={}", event)` có thể vô tình ghi cả credential, đặc biệt khi payload là Java record với `toString()` được sinh tự động.

**Nguyên tắc:** event là hợp đồng **chia sẻ thông tin sự việc**, không phải container chứa dữ liệu xác thực. Giữ secret trong boundary chuyên trách; event chỉ cần dữ liệu tối thiểu để consumer biết **điều gì đã xảy ra** và thực hiện công việc được phép.

Bài này hướng dẫn nhận diện secret; thiết kế payload theo allowlist; kiểm tra các đường rò rỉ qua log, object graph, serialization, outbox và async; đồng thời xây ví dụ Java 17+ Spring Framework có test ngăn thêm trường bí mật vào event.

## 2. Phân loại dữ liệu trước khi phát event

| Nhóm | Ví dụ | Quy tắc |
| --- | --- | --- |
| **Credential gốc** | mật khẩu, API key, client secret, database password, private key, SSH key, webhook signing secret | **Không đưa vào domain event thông thường** |
| **Token cấp quyền** | access token, refresh token, session cookie, password-reset token, magic-link token, JWT bearer token, OTP, recovery code | Không đưa vào event fan-out |
| **Dữ liệu xác thực phát sinh** | password hash, token verifier, pepper, key material | Không phát tán cho audit/metrics/notification; vẫn cần bảo vệ |
| **Dữ liệu thanh toán nhạy cảm** | CVV/CVC, PIN, số thẻ đầy đủ | Không phát tán; tuân thủ tiêu chuẩn chuyên ngành |
| **PII** | email, số điện thoại, địa chỉ, số định danh, dữ liệu sức khỏe | Cân nhắc mục đích, quyền xử lý và retention; ưu tiên giảm thiểu |
| **Business ID** | `accountId`, `orderId`, `paymentId` | Có thể dùng nếu có mục đích, kiểm soát tenancy/privacy |
| **Event metadata** | `eventId`, `occurredAt`, loại event, version | Thường phù hợp; không nhúng secret/PII vào ID |
| **Opaque reference** | `credentialRef`, `vaultVersion` | Chỉ khi reference **không tự cấp quyền truy xuất** |

Không đánh đồng PII với credential, nhưng cũng không coi PII là dữ liệu công khai. Một mã `sessionId` tuy được gọi là ID nhưng có thể là **bearer secret** nếu người có mã đó được phép sử dụng session. Ngược lại, `accountId` có thể không phải credential nhưng vẫn là dữ liệu riêng tư trong một hệ thống nhiều tenant.

**Không chuyển password thành hash rồi phát tán.** Password hash vẫn là dữ liệu nhạy cảm có thể bị dùng để tấn công offline. **Base64 không phải mã hóa.** Mã hóa đúng cách bảo vệ một số lớp vận chuyển/lưu trữ, nhưng không thay thế việc hỏi xem consumer có thật sự cần biết dữ liệu đó không.

## 3. Những anti-pattern cần loại bỏ

### 3.1 Nhét command/request vào record event

~~~java
// ANTI-PATTERN: minh họa, không phải chương trình độc lập.
public record UserRegistered(
    long userId,
    String email,
    String rawPassword,
    String sessionToken
) {}
~~~

Java record sinh `toString()` và accessor. Người khác có thể vô tình log cả `rawPassword` và `sessionToken`. Lombok `@Data` / `@ToString`, Kotlin data class hoặc serializer tự động cũng cần kiểm tra tương tự.

Một phiên bản tối thiểu hơn:

~~~java
public record UserRegistered(
    java.util.UUID eventId,
    long userId,
    java.time.Instant occurredAt
) {}
~~~

Nếu listener gửi email, nó có thể truy xuất địa chỉ liên hệ ở nơi được phép khi có mục đích nghiệp vụ rõ ràng. Không nhất thiết mọi subscriber phải nhận email/phone/raw profile.

### 3.2 Phát cả JPA entity hoặc HttpServletRequest

~~~java
// ANTI-PATTERN: giả định các kiểu đã tồn tại.
publisher.publishEvent(new AccountUpdated(accountEntity));
publisher.publishEvent(new RequestCaptured(httpServletRequest));
~~~

Entity có thể chứa password hash, lazy-loaded collection hoặc thông tin khách hàng. `HttpServletRequest` có thể chứa Authorization header và cookie. Khi `@Async` dùng executor, request có thể đã kết thúc; `RequestContextHolder` cũng không tự truyền sang thread khác. Đừng giữ raw request/credential trong background event.

### 3.3 Dựa hoàn toàn vào redaction

`@JsonIgnore` có thể ẩn một field khi dùng một cấu hình Jackson nhất định. Nhưng `toString()`, reflection, debug logger, AOP interceptor hoặc serializer khác vẫn có thể thấy trường đó. **Bảo vệ mạnh nhất là không tạo field secret trên event.** Logging/redaction chỉ là lớp phòng thủ bổ sung.

## 4. Thiết kế đúng: đưa metadata cần thiết, không đưa secret

Giả sử một tài khoản xoay vòng API credential:

~~~text
RotateCredential command
  accountId=101
  newSecret=[SENSITIVE]
         |
         v
CredentialService (trusted boundary)
  validate/store via secret manager
         |
         v
CredentialRotated
  eventId=<UUID>
  accountId=101
  credentialVersion=3
  occurredAt=<Instant>
         |
         +--> audit: ghi thay đổi version
         +--> metrics: đếm credential rotation
         +--> cache invalidation: bỏ cache version cũ
~~~

Payload có thể định nghĩa:

~~~java
public record CredentialRotated(
    java.util.UUID eventId,
    long accountId,
    int credentialVersion,
    java.time.Instant occurredAt
) {}
~~~

Trong event **không có** `newSecret`, `oldSecret`, `passwordHash`, `accessToken` hoặc `HttpServletRequest`. Service xử lý dữ liệu bí mật tại một vị trí có quyền; listener chỉ biết một fact và metadata.

Không phải mọi event đều bắt buộc có cả bốn trường. Ví dụ listener metrics có thể chỉ cần `event_type` và `outcome`, không cần `accountId` trong log. Hãy thiết kế theo người nhận và trust boundary cụ thể.

### Checklist kiểm tra mỗi trường

1. Listener nào cần field này và để làm gì?
2. Nếu lộ giá trị, người không có quyền có thể đăng nhập, reset mật khẩu hay lấy secret không?
3. Field có chứa email, tenant ID, dữ liệu cá nhân hoặc thông tin định danh không?
4. Có thể thay bằng version, ID hoặc trạng thái để giảm quyền đọc không?
5. Nếu event được in bởi `toString()`, serialized vào outbox, replay hay DLQ, có vi phạm không?
6. Có một cơ chế access control riêng khi cần giải tham chiếu dữ liệu nhạy cảm không?

**Không dùng “thêm tạm password cho dễ debug”.** Một lần publish có thể sinh nhiều bản sao khó thu hồi hơn source object.

## 5. Secret reference không phải phép màu

Khi worker thật sự cần quyền truy cập một secret, có thể gửi một **opaque reference**, rồi worker truy xuất qua secret manager:

~~~text
Event: CredentialSyncRequested
  credentialRef=cred/version-7
  eventId=...
        |
        v
Authorized worker
  - authenticate workload identity
  - authorize tenant/purpose/credential
  - fetch secret qua kênh được bảo vệ
  - chỉ dùng trong thời gian cần thiết
  - audit access, không log raw material
~~~

Các điều kiện quan trọng:

- Chỉ biết `credentialRef` **không được** tự động đủ quyền đọc secret. Nếu reference hoạt động như signed URL, reset link hoặc bearer token thì **chính nó là secret**, không nên broadcast.
- IAM/vault kiểm tra quyền tại lúc dereference. Không cấp mặc định “read all secrets” cho mọi listener.
- Hạn chế TTL, cache, quyền export, access log và số bản sao; có rotation/revocation.
- Reference cũng có thể tiết lộ tenant hoặc tên nội bộ; ưu tiên opaque ID không mang dữ liệu riêng tư.
- Một event được replay nhiều tháng sau có thể trỏ đến secret đã hết hạn/được rotate; consumer phải xử lý rõ trường hợp ấy.

Nếu một nghiệp vụ cần gửi token đến đúng người nhận, hãy tách **domain event chung** khỏi **secure delivery channel chuyên trách**, có authentication, authorization, encryption và retention phù hợp.

## 6. Ví dụ hoàn chỉnh Java 17+ Spring Framework 6.2

Ví dụ dùng **Spring Framework 6.2.19**, **JUnit 5.12.2**, Gradle và Java 17+. Không cần Spring Boot hoặc database. Nó minh họa cách **secret chỉ đi qua thành phần xử lý**, còn event chứa metadata đã được duyệt.

**Cảnh báo:** `DemoVault` trong ví dụ là kho **in-memory không được mã hóa**, chỉ để demo luồng dữ liệu; không phải secret store an toàn cho production. Hệ thống thật phải dùng secret manager/credential storage được phê duyệt, quản lý quyền và rotation đúng cách.

### Cấu trúc

~~~text
safe-event-payload/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/SafeEventPayloadDemo.java
    └── test/java/demo/SafeEventPayloadDemoTest.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'safe-event-payload'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.SafeEventPayloadDemo'
}

test {
    useJUnitPlatform()
}
~~~

### src/main/java/demo/SafeEventPayloadDemo.java

~~~java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

@Configuration
public class SafeEventPayloadDemo {

    // Không chứa password, token, key material hoặc raw request.
    public record CredentialRotated(
        UUID eventId,
        long accountId,
        int credentialVersion,
        Instant occurredAt
    ) {}

    @Bean
    Clock clock() {
        return Clock.fixed(
            Instant.parse("2026-01-02T03:04:05Z"),
            ZoneOffset.UTC
        );
    }

    @Bean
    DemoVault demoVault() {
        return new DemoVault();
    }

    @Bean
    RotationService rotationService(
            DemoVault vault,
            ApplicationEventPublisher publisher,
            Clock clock) {
        return new RotationService(vault, publisher, clock);
    }

    @Bean
    AuditSink auditSink() {
        return new AuditSink();
    }

    @Bean
    AuditListener auditListener(AuditSink sink) {
        return new AuditListener(sink);
    }

    // CHỈ DÀNH CHO DEMO: không dùng in-memory vault ở production.
    public static final class DemoVault implements AutoCloseable {
        private final Map<Long, char[]> values = new HashMap<>();
        private final Map<Long, Integer> versions = new HashMap<>();

        public synchronized int rotate(long accountId, char[] secret) {
            Objects.requireNonNull(secret, "secret");

            if (accountId <= 0 || secret.length < 12) {
                throw new IllegalArgumentException(
                    "Invalid rotation request"
                );
            }

            char[] copy = Arrays.copyOf(secret, secret.length);
            char[] old = values.put(accountId, copy);

            if (old != null) {
                Arrays.fill(old, '\0');
            }

            int version = versions.getOrDefault(accountId, 0) + 1;
            versions.put(accountId, version);
            return version;
        }

        @Override
        public synchronized void close() {
            for (char[] item : values.values()) {
                Arrays.fill(item, '\0');
            }
            values.clear();
            versions.clear();
        }
    }

    public static final class RotationService {
        private final DemoVault vault;
        private final ApplicationEventPublisher publisher;
        private final Clock clock;

        RotationService(
                DemoVault vault,
                ApplicationEventPublisher publisher,
                Clock clock) {
            this.vault = vault;
            this.publisher = publisher;
            this.clock = clock;
        }

        public CredentialRotated rotate(
                long accountId, char[] newSecret) {

            int version = vault.rotate(accountId, newSecret);
            CredentialRotated event = new CredentialRotated(
                UUID.randomUUID(),
                accountId,
                version,
                Instant.now(clock)
            );

            // Chỉ publish metadata đã được allowlist.
            publisher.publishEvent(event);
            return event;
        }
    }

    public static final class AuditSink {
        private final List<String> entries = new ArrayList<>();

        public synchronized void add(CredentialRotated event) {
            entries.add(
                "account=" + event.accountId()
                + " version=" + event.credentialVersion()
            );
        }

        public synchronized List<String> entries() {
            return List.copyOf(entries);
        }
    }

    public static final class AuditListener {
        private final AuditSink sink;

        AuditListener(AuditSink sink) {
            this.sink = sink;
        }

        @EventListener
        public void onCredentialRotated(CredentialRotated event) {
            sink.add(event);
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                SafeEventPayloadDemo.class)) {

            var service = ctx.getBean(RotationService.class);

            // Chỉ là giá trị giả phục vụ demo.
            char[] input =
                "FAKE_DEMO_CREDENTIAL_NOT_REAL".toCharArray();

            CredentialRotated event;
            try {
                event = service.rotate(101L, input);
            } finally {
                Arrays.fill(input, '\0');
            }

            boolean cleared = true;
            for (char value : input) {
                if (value != '\0') {
                    cleared = false;
                }
            }

            int audits = ctx.getBean(AuditSink.class)
                .entries().size();
            boolean leaked = event.toString().contains(
                "FAKE_DEMO_CREDENTIAL_NOT_REAL");

            System.out.println("audit entries=" + audits);
            System.out.println(
                "credential version=" + event.credentialVersion());
            System.out.println("event exposes secret=" + leaked);
            System.out.println("command buffer wiped=" + cleared);
            System.out.println("event time=" + event.occurredAt());
        }
    }
}
~~~

### Lệnh chạy và kết quả

~~~bash
gradle run --quiet
# Linux/macOS nếu có wrapper: ./gradlew run --quiet
# Windows nếu có wrapper: gradlew.bat run --quiet
~~~

Các dòng do chương trình in (không tính log môi trường):

~~~text
audit entries=1
credential version=1
event exposes secret=false
command buffer wiped=true
event time=2026-01-02T03:04:05Z
~~~

**Lý do:** chỉ có một event thành công; listener audit ghi đúng một dòng metadata; event record không có secret; caller đã zero buffer mà nó sở hữu; `Clock.fixed` khiến timestamp dự đoán được. `UUID.randomUUID()` tạo một event ID mới nhưng ID không được in.

`Arrays.fill(...)` chỉ xóa được **array cụ thể**. Nó không xóa bản sao đã từng được tạo, String literal, heap dump hay log. Chính vì vậy không nên để raw secret đi vòng qua event. Test `toString().contains(fake)` chỉ minh họa rủi ro, **không có nghĩa production nên log event.toString()**.

Demo không có transaction, database hoặc secure vault; nếu hệ thống thật lưu credential và publish event trong hai hệ khác nhau, phải thiết kế consistency và xử lý crash window riêng.

## 7. JUnit: khóa schema, kiểm tra payload và nhánh lỗi

Một test chỉ xem stdout không đủ. Nếu developer thêm field `refreshToken` vào event sau này, ta muốn test schema **thất bại ngay**.

Tệp `src/test/java/demo/SafeEventPayloadDemoTest.java`:

~~~java
package demo;

import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SafeEventPayloadDemoTest {

    @Test
    void eventSchemaIsAllowlisted() {
        Set<String> names = Arrays.stream(
            SafeEventPayloadDemo.CredentialRotated.class
                .getRecordComponents()
        ).map(RecordComponent::getName)
         .collect(Collectors.toSet());

        assertEquals(
            Set.of("eventId", "accountId",
                   "credentialVersion", "occurredAt"),
            names
        );
    }

    @Test
    void publishedEventDoesNotExposeSecret() {
        try (var ctx = new AnnotationConfigApplicationContext(
                SafeEventPayloadDemo.class)) {

            var service = ctx.getBean(
                SafeEventPayloadDemo.RotationService.class);
            var audit = ctx.getBean(
                SafeEventPayloadDemo.AuditSink.class);

            char[] input =
                "FAKE_DEMO_CREDENTIAL_NOT_REAL".toCharArray();
            SafeEventPayloadDemo.CredentialRotated event;
            try {
                event = service.rotate(101L, input);
            } finally {
                Arrays.fill(input, '\0');
            }

            assertFalse(event.toString().contains(
                "FAKE_DEMO_CREDENTIAL_NOT_REAL"));
            assertEquals(
                List.of("account=101 version=1"),
                audit.entries()
            );
            for (char c : input) {
                assertTrue(c == '\0');
            }
        }
    }

    @Test
    void invalidRotationDoesNotPublishSuccessFact() {
        try (var ctx = new AnnotationConfigApplicationContext(
                SafeEventPayloadDemo.class)) {

            var service = ctx.getBean(
                SafeEventPayloadDemo.RotationService.class);
            var audit = ctx.getBean(
                SafeEventPayloadDemo.AuditSink.class);

            char[] invalid = "short".toCharArray();
            try {
                assertThrows(
                    IllegalArgumentException.class,
                    () -> service.rotate(101L, invalid)
                );
            } finally {
                Arrays.fill(invalid, '\0');
            }

            assertEquals(0, audit.entries().size());
        }
    }
}
~~~

Chạy:

~~~bash
gradle test
# Linux/macOS: ./gradlew test
# Windows: gradlew.bat test
~~~

Kỳ vọng **ba JUnit tests pass** trong môi trường có dependency/Gradle phù hợp:

- schema record chỉ có bốn trường được cho phép;
- event phát thành công không chứa credential giả và audit chỉ có dữ liệu metadata;
- thao tác validation thất bại không phát event thông báo thành công.

**Giới hạn:** ba test này không kiểm tra security manager thật, quyền truy xuất vault, log AOP, JSON serialization, DLQ hoặc heap dump. Khi tích hợp production, phải bổ sung test đối với serializer/broker/outbox và cả đường logging/tracing thật.

## 8. Khi một consumer cần thông tin bí mật

Các trường hợp như password reset, OTP hoặc cấp API key ban đầu đôi khi cần **gửi secret cho người nhận xác định**. Đó là nghiệp vụ của một kênh giao hàng có kiểm soát, không phải một domain event công bố cho mọi listener.

~~~text
PasswordResetRequested
    accountId
    requestId
    occurredAt
         |
         +--> audit/metrics (không thấy token)
         |
         +--> trusted reset service
                - sinh token bằng CSPRNG phù hợp
                - lưu verifier, TTL, one-time-use
                - gửi qua kênh bảo vệ
                - không log token / reset URL
~~~

Không đưa token vào `PasswordResetRequested`. Nếu có message chuyên trách chứa bí mật được mã hóa cho một recipient, phải thiết kế key management, recipient authentication, ACL, expiry, retry, DLQ/redaction riêng. **Không coi việc message được mã hóa là lý do broadcast rộng**.

Một token phải có độ ngẫu nhiên phù hợp, thời hạn, mục đích cụ thể và cơ chế revoke/expire. Không tự tạo thuật toán mật mã; dùng thư viện và giải pháp chuyên trách đã được đánh giá.

## 9. Transaction, @Async và outbox có liên quan thế nào?

`@Async @EventListener` thay đổi thread xử lý, **không** thay đổi độ nhạy của dữ liệu trong event. Task có thể chạy sau khi HTTP request kết thúc, nên càng không nên đưa raw request hay mutable credential-bearing object vào payload.

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` liên kết handler với thời điểm transaction commit thành công. Nhưng:

- Listener AFTER_COMMIT vẫn có thể log/serialize payload; phase không tự động redact.
- Lỗi/side effect sau commit không thể làm dữ liệu T1 quay lại trạng thái chưa commit.
- Callback sau commit có crash window, không phải durable delivery.
- Khi dùng transactional outbox, **chỉ lưu sanitized event ngay từ lúc ghi outbox**. Không lưu raw secret rồi hy vọng sau đó xóa.
- Với reactive transaction, context ở Reactor Context; nguyên tắc loại secret khỏi payload không thay đổi.

Nếu workflow cần độ tin cậy, áp dụng outbox/queue bền vững và idempotency phù hợp, đồng thời vẫn tuân thủ data minimization và quyền truy cập. Một broker có TLS và encryption-at-rest **không thay thế** việc giới hạn fields và consumer ACL.

## 10. Kiểm soát observability và các bản sao

Các đường dữ liệu thường dễ bị bỏ qua:

- `log.info("event={}", event)` có thể kích hoạt record `toString()`.
- AOP interceptor có thể ghi toàn bộ method args, cả raw command.
- Exception reporter có thể dump event/request khi listener ném lỗi.
- Tracing baggage/span attributes có thể vô tình nhận Authorization header.
- Metric tags mang `accountId`, `email`, token hoặc `correlationId` tùy ý sẽ tăng cardinality và có nguy cơ lộ dữ liệu.
- Outbox, broker, DLQ, replay store, analytics và backup có thể giữ bản sao event lâu hơn dự kiến.
- Debug dumps/snapshots/test fixtures có thể chứa credential thật nếu dùng sample dữ liệu production.

**Dùng allowlist cho logs và traces**, chẳng hạn `eventType`, mã lỗi hữu hạn, thời điểm và ID được phép. Không ghi toàn object mặc định. Kiểm tra schema serialization thực tế trước khi forward ra ngoài.

### Khi phát hiện secret đã bị ghi vào event

1. Xác định loại secret, time window, event type, consumers, logs, outbox, broker, DLQ, retry store và backup có thể chứa bản sao.
2. Giảm phát tán và hạn chế quyền đọc theo quy trình ứng phó sự cố; không sao chép raw value sang công cụ hỗ trợ.
3. Rotate/revoke credential có nguy cơ lộ và kiểm tra hành vi sử dụng bất thường.
4. Xử lý retention/xóa bản sao theo chính sách và nghĩa vụ liên quan; xóa source event không bảo đảm các bản sao khác biến mất.
5. Sửa schema theo allowlist, thêm serialization/log capture tests và security review.
6. Phối hợp nhóm security/privacy nếu có dữ liệu cá nhân hoặc credential ảnh hưởng lớn.

Không tuyên bố “đã hết rò rỉ” chỉ vì đã đổi source code; cần xét cả vòng đời bản sao và rotation/revocation.

## 11. Những lỗi hiểu sai thường gặp

1. **“Event chỉ nội bộ JVM nên an toàn.”** Một listener/log bridge mới có thể mở rộng phạm vi nhận dữ liệu.
2. **“Gắn @JsonIgnore là xong.”** Nó chỉ ảnh hưởng một đường serialization; `toString()`/reflection có thể khác.
3. **“char[] không bao giờ lộ.”** Array có thể copy, giữ lâu hoặc dump; chỉ xóa được buffer cụ thể.
4. **“Password hash có thể đưa vào event.”** Verifier vẫn nhạy cảm và cần bảo vệ.
5. **“Base64 là encryption.”** Không phải; nó chỉ là encoding.
6. **“AFTER_COMMIT + @Async giải quyết confidentiality.”** Chúng chỉ thay đổi thời điểm/thread, không lọc payload.
7. **“Secret reference luôn vô hại.”** Reference có quyền bearer vẫn là secret.
8. **“DEBUG không được bật ở production.”** Nó có thể bật và gửi tới log collector.
9. **“Không thấy token trong stdout là đủ test.”** Cần kiểm tra schema, serializer, AOP, tracing, outbox, DLQ.
10. **“Một accountId không nhạy cảm.”** ID vẫn có thể là PII hoặc tiết lộ tenant; cân nhắc quyền và retention.

## 12. Checklist trước khi phát event

- [ ] Event chứa một fact đúng nghiệp vụ, không chứa raw command hay request.
- [ ] Payload là immutable value DTO với các trường allowlist được review.
- [ ] Không có password, access token, refresh token, API key, session token, OTP, private key, password hash hoặc key material.
- [ ] Không phát nguyên JPA entity, HTTP request, header hoặc nested object có thể chứa credential.
- [ ] Mỗi trường có mục đích xử lý/consumer được phép và giới hạn retention.
- [ ] Reference không tự cấp quyền; giải tham chiếu qua IAM/vault có kiểm tra authorization.
- [ ] Không log whole event, whole command hay method args chứa secret.
- [ ] Metrics/tracing/error handler dùng attribute/tag được duyệt.
- [ ] Serialized outbox/broker/DLQ payload không có secret.
- [ ] Có JUnit/schema test và integration test serialization/logging thực tế.
- [ ] Dùng test values giả, không dùng production credentials.
- [ ] Có chính sách revoke/rotate, incident response, backup/retention và access audit.
- [ ] Phân biệt bảo mật dữ liệu với commit, async execution và durable delivery.

### Ghi nhớ

~~~text
Credential-handling command
            |
            v
Trusted boundary
   |                 |
   v                 v
Secret manager    Domain event
ACL/rotation       chỉ metadata cần thiết
   |                 |
   |                 +--> audit / metrics / listeners
   |
   +--> không đưa raw secret ra event

Đừng đưa bí mật vào event payload.
Đừng log object nguyên vẹn.
Đừng coi encryption, @Async hay AFTER_COMMIT
là lý do bỏ qua data minimization.
~~~

**Kết luận:** Tách rõ **secret-handling boundary** khỏi **event contract**. Chỉ sự thật và metadata tối thiểu được phân phối cho các listener; dữ liệu cấp quyền chỉ tồn tại trong hệ thống được phép xử lý, có ACL, TTL, rotation và audit.

## Tài liệu tham khảo

- [Spring — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
