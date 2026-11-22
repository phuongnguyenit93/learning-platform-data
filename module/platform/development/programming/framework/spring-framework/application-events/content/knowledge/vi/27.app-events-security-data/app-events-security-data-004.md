# Xử lý dữ liệu cá nhân trong log khi dùng Spring Application Events

## 1. Vì sao logging event có thể trở thành sự cố bảo mật?

Spring Application Events giúp các phần của ứng dụng phản ứng với một sự thật nghiệp vụ như `CustomerProfileUpdated`, `PaymentCaptured` hoặc `AccountAccessDenied`. Listener thường ghi log để chẩn đoán: đã phát loại event nào, được xử lý ở đâu, mất bao lâu và tại sao thất bại.

Nhưng **event payload không đồng nghĩa dữ liệu được phép ghi log**. Payload có thể có tên, email, số điện thoại, địa chỉ, mã định danh, thông tin sức khỏe, nội dung thông báo, lịch sử thanh toán hoặc các trường gián tiếp giúp xác định một cá nhân. Một dòng log không an toàn có thể tạo bản sao dữ liệu mới ngoài phạm vi kiểm soát của cơ sở dữ liệu nghiệp vụ.

Ví dụ phản thiết kế:

```java
@EventListener
public void on(CustomerProfileUpdated event) {
    logger.info("Received event: {}", event);
}
```

Đây là **mã minh họa chưa đầy đủ**: class, logger và event do ứng dụng định nghĩa. Nếu `CustomerProfileUpdated` là Java record, Lombok `@Data` hay object có `toString()` liệt kê các field, cách viết trên có thể đẩy nguyên email, địa chỉ, số điện thoại hoặc ghi chú khách hàng vào log.

Ngay cả khi chỉ dành cho debug, log có thể được sao chép qua console, container runtime, log collector, monitoring SaaS, bản lưu trữ, backup và hệ thống tìm kiếm. Quyền truy cập log thường khác quyền truy cập database, nên rò rỉ xảy ra dù API chính đã kiểm soát truy cập đúng.

**Nguyên tắc xuyên suốt:** log **thông tin cần thiết để vận hành và điều tra**, không log nguyên domain event. Thu thập tối thiểu, dùng danh sách trường được phép (allowlist), xác định mục đích/retention, bảo vệ nơi lưu và kiểm thử chống rò dữ liệu.

## 2. Ba lớp thông tin cần phân biệt

| Lớp dữ liệu | Ví dụ | Có nên xuất log? |
| --- | --- | --- |
| **Domain payload** | Email cũ/mới, địa chỉ, số tiền, hồ sơ người dùng | Chỉ khi thực sự cần và được phép; mặc định không dump toàn bộ |
| **Event/operation metadata** | Event type, event ID ngẫu nhiên, outcome code, duration | Thường hữu ích; vẫn phải phân loại và giới hạn |
| **Execution/tracing context** | Trace ID, correlation ID, tenant, actor, MDC | Hữu ích có điều kiện; không tự coi là vô danh |
| **Secrets/credentials** | JWT, cookie phiên, API key, mật khẩu, khóa mã hóa | **Không ghi trực tiếp** |
| **Operational diagnostics** | Exception type, stable error code, consumer name | Thường phù hợp hơn raw exception message/HTTP body |
| **Audit evidence** | Actor, action, target, timestamp, result | Cần contract, quyền và retention riêng; không tự động bằng log debug |

Một **opaque customer ID** có thể vẫn được coi là dữ liệu cá nhân nếu có khả năng liên kết tới một người. Thay email bằng `customerId` giúp giảm lộ trực tiếp, nhưng **không biến log thành dữ liệu ẩn danh**. Tương tự, tenant ID và trace ID có thể dùng để liên kết hành vi qua nhiều dịch vụ; phải kiểm soát chúng theo chính sách nội bộ.

### Dữ liệu cá nhân trực tiếp và gián tiếp

Dữ liệu cá nhân trực tiếp có thể gồm email, số điện thoại, ảnh hoặc mã số giấy tờ. Dữ liệu gián tiếp có thể là IP, thiết bị, một định danh ổn định hoặc tổ hợp nhiều thuộc tính đủ để nhận diện. Tính chất nhạy cảm còn phụ thuộc luật áp dụng, ngữ cảnh và khả năng liên kết dữ liệu.

Không nên áp một danh sách cố định kiểu “chỉ email và điện thoại mới nhạy cảm”. Một mã khách hàng có vẻ vô nghĩa nhưng nếu người đọc log có quyền query CRM thì có thể nhận diện được người dùng ngay.

## 3. Ghi gì để chẩn đoán Application Events?

Một dòng log hữu ích khi listener xử lý thành công có thể là:

```text
event_type=CustomerProfileUpdated
event_id=6244b752-bd2b-4aa3-8120-a835ca600ce2
handler=profile-audit
outcome=SUCCESS
duration_ms=14
```

Ở đây event ID là UUID giả định, không phải customer ID. Dòng log **không** cần email cũ/mới, full name, address hoặc nội dung profile để trả lời câu hỏi “handler có xử lý event này không?”.

Nếu listener thất bại:

```text
event_type=CustomerProfileUpdated
event_id=6244b752-bd2b-4aa3-8120-a835ca600ce2
handler=profile-audit
outcome=FAILED
error_code=PROFILE_AUDIT_UNAVAILABLE
```

Không nhất thiết phải ghi raw payload hoặc `exception.getMessage()`. Với lỗi thực tế, stack trace đôi khi cần thiết để debug, nhưng exception message, causal chain và stack frame cũng có thể chứa query parameters, URL, file path, usernames hoặc dữ liệu do khách hàng cung cấp. Phải có chính sách xử lý exception an toàn.

### Một contract log khuyến nghị

| Trường | Ví dụ | Giới hạn |
| --- | --- | --- |
| `event_type` | `CustomerProfileUpdated` | Giá trị từ enum/constant đã định nghĩa |
| `event_id` | UUID v4/v7 hoặc ID opaque | Không nhúng email/định danh người dùng vào ID |
| `handler` | `profile-audit` | Low cardinality; không dùng tên khách hàng |
| `outcome` | `STARTED/SUCCESS/FAILED/SKIPPED` | Tập giá trị xác định |
| `error_code` | `DOWNSTREAM_TIMEOUT` | Mã lỗi ổn định thay vì raw response body |
| `duration_ms` | `14` | Đếm thời gian; không chứa payload |
| `correlation_id` | ID truy vết được cấp ở ingress | Không nhận chuỗi bất kỳ như đã xác thực |
| `tenant_ref` | Opaque tenant ID, nếu thật sự cần | Có thể là thông tin nhạy cảm theo hệ thống |
| `subject_ref` | Pseudonymous reference, nếu cần | Có thể tái định danh; hạn chế truy cập và retention |

Không bắt buộc tất cả field. Một log event xử lý thành công có thể chỉ cần `event_type`, `event_id`, `outcome` và duration. Thêm field phải có lý do vận hành cụ thể, không vì “biết càng nhiều càng tốt”.

## 4. Những dữ liệu không nên log trực tiếp

Theo thực hành từ OWASP Logging Cheat Sheet, nhiều loại dữ liệu nên loại bỏ hoặc bảo vệ trước khi lưu log:

- Password, OTP, mã khôi phục, câu trả lời bảo mật.
- Access/refresh token, JWT, bearer header, session ID và cookie.
- Khóa mã hóa, API secret, private key và connection string chứa credential.
- Số thẻ thanh toán, mã bảo mật, tài khoản ngân hàng hoặc payment payload nhạy cảm.
- Mã định danh chính phủ, dữ liệu sức khỏe và dữ liệu cá nhân cần bảo vệ cao.
- Full request/response body, file upload, payload webhook có thể chứa dữ liệu người dùng.
- Raw `Authentication`, `SecurityContext`, principal hoặc authorities nhạy cảm.
- Dữ liệu nội bộ vượt mức phân loại mà nền tảng logging được phép lưu.

Với tên, email, số điện thoại, địa chỉ hoặc IP, chính sách có thể phụ thuộc mục đích ghi và nghĩa vụ pháp lý. **Không mặc định “đã masking một phần” là có thể lưu vô thời hạn**. Ưu tiên không thu thập khi không cần thiết.

### Ví dụ nguy hiểm trong Spring

```java
logger.debug("event={}", event);
logger.error("request failed: {}", request.getParameterMap());
logger.info("headers={}", headers);
logger.warn("failed to authenticate {}", authentication);
logger.error("external call failed: {}", responseBody);
```

Đây là những snippet phản thiết kế; biến trong từng dòng chỉ mang tính minh họa. Chúng có thể đưa mọi field ở domain/request/transport vào log. Khi severity là `DEBUG`, dữ liệu vẫn nguy hiểm: một lần bật debug để điều tra sự cố có thể làm phát sinh rất nhiều bản sao khó thu hồi.

**Phương án thay thế:** log loại operation và outcome được định nghĩa sẵn, cộng một ID không chứa dữ liệu trực tiếp. Nếu cần mở bản ghi thật, truy cập dữ liệu nghiệp vụ qua công cụ đã có authorization/audit, không xây một bản sao dữ liệu trong log.

## 5. Phân biệt bảo vệ payload với bảo vệ log

Một domain event có thể cần mang dữ liệu mà listener khác phải sử dụng:

```java
public record CustomerEmailChanged(
        UUID eventId,
        String customerRef,
        String previousEmail,
        String newEmail,
        Instant occurredAt) {
}
```

Đây là record minh họa; cần import `UUID` và `Instant`. Email trong **event** có thể có mục đích nghiệp vụ xác định, chẳng hạn cập nhật contact index. Nhưng **listener log** không cần email để chứng minh xử lý đã hoàn thành.

```java
@EventListener
public void on(CustomerEmailChanged event) {
    updateIndex(event.customerRef(), event.newEmail());

    logger.info(
            "event_type=CustomerEmailChanged event_id={} outcome=SUCCESS",
            event.eventId());
}
```

Đoạn này là snippet, cần logger, `updateIndex(...)` và bean listener phù hợp. Nó không phải chương trình độc lập.

Nếu consumer chỉ cần biết “email đã đổi” và có thể truy vấn một nguồn đã phân quyền, event thậm chí có thể mang **customer ID + event ID** thay vì raw email. Đó là quyết định kiến trúc riêng: truy vấn lúc xử lý có thể đọc trạng thái *mới hơn* fact ban đầu, nên một số consumer thật sự cần snapshot. Dù chọn cách nào, logging không tự được phép dump toàn bộ.

**Data minimization ở hai tầng:** tối giản payload được publish theo nhu cầu consumer, và tối giản phần payload được phép xuất sang log/traces/metrics.

## 6. Phản thiết kế: toString(), record và Lombok

Java record tự sinh `toString()` để thể hiện components. Lombok `@Data` hoặc `@ToString` cũng có thể sinh biểu diễn chứa field nhạy cảm. Vì thế:

```java
record UserRegistered(String email, String phone) {}

logger.info("{}", new UserRegistered(
        "person@example.invalid", "+10000000000"));
```

Dòng log có thể chứa nguyên email và số điện thoại. Không nên chỉ sửa `toString()` để che dữ liệu rồi tiếp tục dump mọi object. Một class mới thêm field `accessToken` về sau có thể tạo rủi ro; nested objects cũng có thể in thông tin ngoài dự kiến.

Với Lombok, có thể dùng `@ToString.Exclude` cho field nhạy cảm trong những chỗ cần debug, nhưng đây chỉ là **lớp phòng vệ bổ sung**. Chiến lược chính vẫn là không đưa raw object vào logger.

### JSON serialization cũng có rủi ro tương tự

```java
logger.debug("event_json={}", objectMapper.writeValueAsString(event));
```

Đây là snippet minh họa với Jackson. Việc chuyển object thành JSON **không làm payload tự trở thành an toàn**. JSON có thể encode mọi field, bao gồm credentials hoặc nested PII. Tương tự, annotation dùng để kiểm soát API serialization không đương nhiên bảo vệ mọi đường logging khác.

Để structured logging an toàn, **xây một DTO log nhỏ theo allowlist**, khác với domain event, rồi để logging backend encode đúng định dạng.

## 7. Allowlist tốt hơn blacklist/redaction cuối đường ống

Hai chiến lược:

| Chiến lược | Cách hoạt động | Điểm yếu / điểm mạnh |
| --- | --- | --- |
| **Blacklist** | Log mọi field, rồi regex che email/token đã biết | Dễ bỏ sót format mới, nested fields, secret encode, unknown keys |
| **Allowlist** | Chỉ xây log từ những trường được phép | An toàn hơn theo mặc định; field mới không tự lộ |
| **Redaction ở collector** | Thu nhận raw log rồi che ở pipeline | Raw data có thể đã tồn tại tại container/stdout/agent trước khi bị che |
| **Mask ở logger/encoder** | Biến đổi field nhạy cảm trước khi xuất | Hữu ích lớp bổ sung; vẫn cần policy và test |
| **Không log dữ liệu** | Không tạo bản sao ngay từ nguồn | Giảm rủi ro nhất khi field không cần thiết |

Nếu chọn masking, phải đánh giá tính phù hợp theo threat model. Ví dụ che email thành `a***@example.invalid` vẫn có thể giúp đoán cá nhân khi kết hợp domain, tenant, timestamp và logs khác. Đây là **masking**, không phải ẩn danh tuyệt đối.

Không thể giả định một regex tìm `@` sẽ bắt được mọi thông tin cá nhân. Dữ liệu có thể ở free text, JSON nested, URL query, stack trace hoặc encoded payload.

### Khi bắt buộc cần theo dõi một subject xuyên log

Một reference ổn định nhưng không chứa email có thể dùng được, **nếu** nhu cầu vận hành thật sự đòi hỏi. Tuy nhiên:

- Raw `customerId` vẫn có khả năng là PII có thể liên kết.
- Hàm băm SHA-256 thông thường của email **không** đảm bảo ẩn danh: email có entropy thấp và có thể dò từ danh sách phổ biến.
- Pseudonymization dựa trên HMAC với khóa bí mật được quản lý tốt có thể giảm khả năng dò trực tiếp, nhưng output vẫn **có thể liên kết** và phải được bảo vệ.
- Stable pseudonym cho phép tracking dài hạn; cần chính sách scope/retention/rotation và đánh giá quyền riêng tư.
- Không đưa HMAC key, salt/pepper hoặc mapping table vào log.

Nếu không cần nối theo người, chỉ dùng event ID + outcome thường an toàn hơn.

## 8. Ví dụ Maven chạy được: @EventListener chỉ ghi metadata được phép

Ví dụ này dùng **Java 17+**, **Spring Framework 6.2.12** và **SLF4J 2.0.16 với SimpleLogger**. Nó cố ý cho domain event chứa email để cho thấy **payload được xử lý trong ứng dụng không đồng nghĩa được xuất log**.

Mục tiêu:

1. Publish một Java record `CustomerEmailChanged` bằng Spring context.
2. `@EventListener` nhận event và xây log summary **chỉ từ loại event, UUID và outcome cố định**.
3. Sử dụng SLF4J parameterized logging, không đưa raw event hoặc email vào logger.
4. Kiểm tra lại chính chuỗi summary nhằm ngăn email xuất hiện.
5. In kết quả kiểm tra ổn định không phụ thuộc timestamp của logging backend.

### 8.1. Cấu trúc project

```text
privacy-safe-event-log/
├── pom.xml
└── src/main/java/demo/PrivacySafeEventLogDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>privacy-safe-event-log</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.16</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.PrivacySafeEventLogDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/PrivacySafeEventLogDemo.java`:

```java
package demo;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class PrivacySafeEventLogDemo {

    public record CustomerEmailChanged(
            UUID eventId,
            String customerRef,
            String previousEmail,
            String newEmail,
            Instant occurredAt) {

        public CustomerEmailChanged {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(customerRef, "customerRef");
            Objects.requireNonNull(previousEmail, "previousEmail");
            Objects.requireNonNull(newEmail, "newEmail");
            Objects.requireNonNull(occurredAt, "occurredAt");
        }
    }

    public static final class SafeEventLogListener {
        private static final Logger log =
                LoggerFactory.getLogger(SafeEventLogListener.class);

        private volatile String lastSafeSummary;

        @EventListener
        public void on(CustomerEmailChanged event) {
            // Không gọi event.toString(), không log email/các field PII.
            String safeSummary =
                    "event_type=CustomerEmailChanged"
                    + " event_id=" + event.eventId()
                    + " outcome=OBSERVED";

            lastSafeSummary = safeSummary;
            log.info("{}", safeSummary);
        }

        public String lastSafeSummary() {
            return lastSafeSummary;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        SafeEventLogListener safeEventLogListener() {
            return new SafeEventLogListener();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            CustomerEmailChanged event = new CustomerEmailChanged(
                    UUID.fromString(
                            "6244b752-bd2b-4aa3-8120-a835ca600ce2"),
                    "customer-42",
                    "old@example.invalid",
                    "new@example.invalid",
                    Instant.parse("2026-01-01T10:00:00Z"));

            context.publishEvent(event);

            String summary = context
                    .getBean(SafeEventLogListener.class)
                    .lastSafeSummary();

            if (summary == null) {
                throw new IllegalStateException("Listener not invoked");
            }

            boolean leaked = summary.contains(event.previousEmail())
                    || summary.contains(event.newEmail());

            System.out.println("SAFE_SUMMARY=" + summary);
            System.out.println("EMAIL_LEAKED=" + leaked);
            System.out.println(
                    "HAS_LINE_BREAK=" + (summary.contains("\n")
                            || summary.contains("\r")));
        }
    }
}
```

Chạy:

```bash
mvn -q compile exec:java
```

Các dòng được tạo bởi **`System.out.println(...)`** (logging backend có thể tạo thêm một dòng `INFO` với cách trình bày riêng):

```text
SAFE_SUMMARY=event_type=CustomerEmailChanged event_id=6244b752-bd2b-4aa3-8120-a835ca600ce2 outcome=OBSERVED
EMAIL_LEAKED=false
HAS_LINE_BREAK=false
```

### 8.2. Vì sao ví dụ đúng chủ đề?

- `AnnotationConfigApplicationContext` tạo context và đăng ký phương thức `@EventListener` của bean.
- `context.publishEvent(event)` phát một Java record thông thường. Spring hỗ trợ payload không kế thừa `ApplicationEvent`.
- Multicaster mặc định xử lý listener **đồng bộ** trên cùng thread, nên sau publish có thể đọc `lastSafeSummary()` ngay trong `main`.
- Listener **có thể truy cập** `previousEmail` và `newEmail` qua event, nhưng không sử dụng chúng khi dựng summary để log.
- Event ID là UUID định dạng hợp lệ từ nguồn đáng tin trong demo. Không có dữ liệu email trong summary hay ký tự CR/LF.
- SLF4J chỉ nhận summary đã được dựng từ allowlist. Với production, cần dùng structured logging/encoder phù hợp thay vì tự lắp một chuỗi lớn từ nhiều field động.

**Giới hạn cần ghi rõ:** demo kiểm tra chuỗi summary được đưa tới logger, **không bắt toàn bộ log phát ra từ mọi thư viện, framework, exception handler hoặc logging pipeline**. Nó không chứng minh toàn hệ thống không rò PII. Dữ liệu giả có đuôi `.invalid`, không dùng thông tin người thật. Dự án không có HTTP, database hoặc transaction. Trong production nên bổ sung integration test bắt log output từ appender và scan toàn pipeline.

### 8.3. Vì sao không log customerRef dù nó “chỉ là ID”?

Đối với mục tiêu duy nhất “listener đã nhận event chưa”, event UUID đủ để truy sự cố. `customerRef` có thể được dùng để tra dữ liệu người thật trong CRM, do đó là pseudonymous reference cần bảo vệ. Việc không đưa field này vào log giảm khả năng truy vết hành vi cá nhân bằng những người có quyền đọc log nhưng không có quyền đọc CRM.

Nếu business thật cần audit theo subject, hãy thiết kế **audit trail riêng** với quyền truy cập và retention thích hợp, thay vì dựa vào debug logger có log level thay đổi theo sự cố.

## 9. Bảo vệ log khỏi CRLF/log injection

Ngoài rò dữ liệu, logging raw input có thể cho phép kẻ tấn công chèn một “dòng log giả”:

```text
displayName = "Alice\nERROR admin-login-success user=attacker"
```

Nếu code nối trực tiếp input vào log text, dòng giả có thể làm sai phân tích sự cố hoặc alert.

### 9.1. Parameterized logging không tự sanitize

```java
logger.warn("Profile update failed for name={}", displayName);
```

Cách này tốt hơn string concatenation về cấu trúc message template, nhưng **không mặc nhiên escape mọi ký tự CR/LF** ở mọi logging backend và định dạng. Nếu `displayName` chưa được validate hoặc encoder không escape, log injection vẫn là rủi ro.

### 9.2. Ưu tiên typed allowlist và structured encoding

Một hướng an toàn hơn:

```java
logger.warn(
        "event_type={} outcome={} error_code={}",
        "CustomerProfileUpdated",
        "FAILED",
        "INVALID_DISPLAY_NAME");
```

Giá trị là các literal hoặc enum có danh sách hữu hạn; không có untrusted display name. Nếu phải ghi một input, hãy validate kích thước/kiểu, encode theo output format, giới hạn độ dài và dùng structured JSON encoder có escape đúng. Không tự loại `\n` rồi nghĩ đã giải quyết mọi dạng log injection (Unicode controls, delimiter và log-viewer parsing còn có thể liên quan).

### 9.3. Structured JSON không tự giải quyết privacy

Một structured logger có thể serialize an toàn các dấu xuống dòng và dấu ngoặc, nhưng nếu field JSON chứa số thẻ, token hoặc email thì **vẫn rò dữ liệu**, chỉ khác cách biểu diễn. Cần cả hai: **allowlist dữ liệu** và **encoding đúng định dạng**.

## 10. Exceptions có thể làm lộ dữ liệu trong log

Một pattern thường gặp:

```java
try {
    remoteClient.updateCustomer(event);
} catch (Exception ex) {
    logger.error("Could not update customer {}", event, ex);
}
```

Đây là snippet phản thiết kế, không chạy độc lập. Nó có thể đưa toàn bộ event PII qua `toString()`, đồng thời exception/stack trace có thể chứa URL, response body hoặc thông tin từ SDK.

Một cách có kiểm soát:

```java
try {
    remoteClient.updateCustomer(event);
} catch (ExternalServiceException ex) {
    logger.error(
            "event_type={} event_id={} outcome={} error_code={}",
            "CustomerEmailChanged",
            event.eventId(),
            "FAILED",
            "CONTACT_INDEX_UNAVAILABLE");

    // Chính sách retry/escalation ở tầng xử lý lỗi riêng;
    // không mặc nhiên nuốt exception rồi báo nghiệp vụ thành công.
    throw ex;
}
```

Đây là snippet minh họa; `remoteClient` và `ExternalServiceException` do ứng dụng định nghĩa. Nếu cần stack trace để triage, có thể ghi ở kênh truy cập hạn chế sau khi kiểm tra exception source và message; **không** tự assume mọi `Throwable.toString()` đều vô hại.

### Lỗi validation và exception messages

Validation framework có thể đưa rejected value vào error description. Ví dụ khi email không hợp lệ, một message có thể mô tả đúng chuỗi email mà khách nhập. Nếu logger ghi `exception.getMessage()` hoặc `BindingResult.toString()`, input có thể rò.

Cách tốt hơn: log field name có trong allowlist + stable validation error code + event ID, thay vì raw invalid value. Khi điều tra lỗi nhập liệu, dùng các kênh truy vấn dữ liệu đã phân quyền nếu thật sự cần xem giá trị.

## 11. Spring Boot logging và log level không phải cơ chế phân quyền

Spring Boot thường cấu hình logging backend (Logback là lựa chọn thông dụng với starter mặc định) và cho phép kiểm soát log level qua cấu hình. Ví dụ:

```yaml
logging:
  level:
    root: INFO
    demo.customer: INFO
```

Đây là YAML minh họa cho một ứng dụng Spring Boot, **không thuộc project Maven thuần Spring ở phần 8**. Chỉnh `DEBUG`/`TRACE` có thể làm tăng log chi tiết từ thư viện hoặc custom listeners; một lần bật level bằng config động cũng có thể để lại dữ liệu trong log collector.

Không lấy log level làm rào cản duy nhất:

- PII ở `DEBUG` vẫn là PII.
- Người dùng có quyền bật debug có thể không có quyền đọc hồ sơ cá nhân.
- Thư viện hoặc SDK có thể log HTTP headers/body theo cấu hình riêng.
- Một error path có thể log dữ liệu ở `ERROR` dù business logger bình thường không log.
- Collector có thể giữ bản sao sau khi bạn tắt debug.

**Chiến lược mạnh:** không xuất dữ liệu nhạy cảm ở code paths mặc định; kiểm soát logging config, code review và security test khi bật debug/trace; hạn chế việc thay đổi level production theo quy trình được duyệt.

### Đặc biệt với SQL logging

Truy vấn SQL có parameterized placeholders không đồng nghĩa log của JDBC/ORM luôn an toàn. Khi bật trace logging cho SQL bind values hoặc JDBC proxy, giá trị email, số tài khoản hoặc trường PII có thể xuất hiện. Cần kiểm tra **cấu hình bind parameter logging** của Hibernate và thư viện database theo phiên bản thực tế.

Nếu thật sự cần đo SQL performance, ưu tiên query shape, duration, error class, query fingerprint không chứa literal nhạy cảm. Không đưa bind values vào nơi lưu log thông thường.

## 12. HTTP access logs, request body và headers

Một event listener thường được gọi từ request HTTP, nên đường rò PII không chỉ nằm trong `@EventListener`. Những nơi khác có thể log cùng dữ liệu:

- Servlet filter hoặc Spring MVC interceptor log raw request.
- Logback access log, web server access log chứa query string.
- HTTP client interceptor log URL/request/response.
- Retry interceptor hoặc circuit breaker log response message.
- Spring Boot error handler log exception description.
- Log collector gộp headers, cookies, trace baggage.

Ví dụ URL:

```text
GET /customers?email=person@example.invalid
```

Ngay cả khi event listener không log email, **access log ghi nguyên query string** vẫn rò. Vì vậy, không nên truyền secrets/PII trong query parameters nếu có lựa chọn giao thức tốt hơn, và cần áp dụng allowlist/redaction ở ingress/egress.

### Không log all headers

Header `Authorization`, `Cookie`, `Set-Cookie`, token trao đổi nội bộ và các header tùy biến có thể chứa secrets. Chỉ log những header thật sự cần theo policy, có allowlist và validation.

### ContentCachingRequestWrapper không là giải pháp privacy

Trong Spring MVC, `ContentCachingRequestWrapper` có thể giúp một filter đọc lại body đã được tiêu thụ, nhưng nếu dùng nó để in toàn bộ body vào log thì rủi ro vẫn như cũ. Thậm chí bộ nhớ chứa raw body ở filter có thể tạo thêm vấn đề. Không kích hoạt request/response payload logging diện rộng chỉ để debug event.

## 13. MDC và context propagation: nguy cơ rò giữa requests

Mapped Diagnostic Context (MDC) có thể giúp gắn `traceId` hoặc `correlationId` vào các dòng log. Nhưng nhiều logging implementations sử dụng ThreadLocal, nên cần quản lý vòng đời.

Ví dụ minh họa dùng SLF4J:

```java
try (MDC.MDCCloseable ignored =
        MDC.putCloseable("correlationId", correlationId)) {
    service.handle(command);
}
```

Đây là snippet có `MDC`, `service`, `command` và `correlationId` do ứng dụng cung cấp. Nó sử dụng try-with-resources để restore/remove field đã đặt, nhưng cần chú ý nếu giá trị trước đó tồn tại và phải khôi phục theo chính sách. Không đẩy email, token, số điện thoại hoặc raw request headers vào MDC.

### 13.1. Listener đồng bộ

Theo cơ chế mặc định, Spring Application Events xử lý listeners đồng bộ trên publisher thread. Nếu MDC đã có correlation ID trong scope này thì listener có thể nhìn thấy cùng MDC. Điều đó không có nghĩa MDC sạch hoặc an toàn: nếu publisher đặt một field PII không được phép, listener và logger phía sau cũng có thể phát tán nó.

### 13.2. Listener bất đồng bộ

Khi dùng `@Async`, task executor hoặc custom multicaster chạy listener ở thread khác, MDC và các ThreadLocal **không được bảo đảm tự truyền**. Spring Framework có `ContextPropagatingTaskDecorator`/Micrometer Context Propagation cho các context được cấu hình, nhưng không phải mọi key/security/tenant context đều được hỗ trợ tự động.

Nguy hiểm hơn, nếu task từng set `customerId` hoặc tenant rồi không clear, thread pool có thể tái sử dụng worker cho một user khác, gây **cross-request/cross-tenant leakage**.

Ví dụ vệ sinh MDC ở một task:

```java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("correlationId", safeCorrelationId);
    processEvent(event);
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

Đây là snippet, cần import `java.util.Map` và `org.slf4j.MDC`; `processEvent` và `safeCorrelationId` do ứng dụng định nghĩa. Nó phục hồi state trước đó, nhưng **không hợp pháp hóa PII** trong previous map. Chỉ truyền context có allowlist và thuộc đúng execution boundary.

## 14. Trace, metrics và log là ba nơi lưu dữ liệu khác nhau

Một hành động có thể đồng thời tạo:

```text
Domain event
  +--> Listener application log
  +--> Distributed tracing span attributes
  +--> Metrics tags/labels
  +--> Audit table
  +--> Message broker / event publication registry
```

Chặn PII ở logger **không tự chặn** nó ở span attributes, exception recording hoặc metrics. Ví dụ gắn `customerEmail` vào OpenTelemetry span có thể xuất dữ liệu tới tracing backend. Đưa raw user/tenant ID vào metric label còn làm tăng cardinality rất cao.

### Hướng xử lý

- **Metrics:** chỉ dùng low-cardinality tags như event type, outcome, listener name và class lỗi đã chuẩn hóa. Không dùng email, customerId, eventId hoặc token làm label.
- **Traces:** dùng traceId/spanId để tương quan; chỉ ghi event metadata thật sự cần. Hạn chế raw payload và exception body.
- **Logs:** allowlist fields, structured encoding, access control, retention.
- **Audit:** schema và quyền riêng, có nhu cầu pháp lý/nghiệp vụ rõ; không dùng debug log làm nguồn audit duy nhất.
- **Events/outbox:** chỉ lưu dữ liệu cần cho consumer và reliability; bảo vệ theo chính sách dữ liệu và phân quyền.

Một chuỗi event được observability instrument không làm cho tracing attributes tự nhiên phù hợp để lưu PII. Phải đánh giá từng nơi dữ liệu được xuất.

## 15. Audit log khác operational log

Trong hệ thống có yêu cầu truy cứu hành động, cần phân biệt:

| Đặc điểm | Operational log | Audit trail |
| --- | --- | --- |
| Mục tiêu | Debug, performance, triage lỗi | Ghi nhận ai làm gì, với đối tượng nào và kết quả |
| Độ ổn định schema | Có thể đổi theo release/log backend | Cần hợp đồng ổn định, có version |
| Quyền truy cập | Dev/operations theo role | Quyền hạn riêng, thường nhạy cảm hơn |
| Retention | Theo nhu cầu vận hành | Theo chính sách/luật/hợp đồng áp dụng |
| Bảo vệ toàn vẹn | Có nhưng mức độ phụ thuộc | Thường cần kiểm soát thay đổi/tampering mạnh |
| Trạng thái transaction | Không tự bảo đảm gắn commit | Cần xác định semantics của sự thật và commit |
| PII | Tối thiểu | Chỉ field cần cho nghĩa vụ audit, được bảo vệ |

Ví dụ “nhân viên hỗ trợ đã truy cập hồ sơ khách hàng” có thể cần audit record với actor ID và target ID, nhưng không vì thế mà cho phép application log dòng “fullCustomer={...}”.

Nếu tổ chức cần lưu hành động truy cập PII, có thể log **sự kiện truy cập** và kết quả, không log **nội dung PII đã truy cập**.

## 16. Multi-tenant logging: tenant ID có thể nhạy cảm

Trong hệ thống đa tenant:

- Tenant ID có thể chỉ tới một doanh nghiệp/nhóm người cụ thể.
- Một event có thể liên quan actor của tenant A nhưng dữ liệu thuộc tenant B nếu application bug.
- Logs tập trung có thể chứa thông tin nhiều tenant trong cùng index.

Do đó, log an toàn phải xử lý cả **quyền ghi** và **quyền đọc**:

1. Tenant được lấy từ nguồn đã xác thực và khớp resource owner; không tin header tùy ý.
2. Nếu log chứa tenant reference, có quy tắc phân vùng/truy cập phù hợp.
3. Người xem log của tenant A không được truy vấn log của tenant B.
4. Cần kiểm tra cả log console, exporter, dashboard, saved search và API token của log platform.
5. Không đặt tenant ID vào label metrics vô hạn nếu tenant count lớn.
6. Không cho untrusted event tự chọn index/bucket của logging backend chỉ bằng field `tenantId`.

Một application event mang `tenantId` **không phải bằng chứng** người tiêu thụ có quyền xử lý tenant đó. Đây là metadata, không phải token ủy quyền.

## 17. Lifecycle và transaction: có thể log fact trước commit

Một listener `@EventListener` đồng bộ có thể chạy khi publisher đang trong transaction. Nếu transaction rollback sau khi listener ghi:

```text
OrderUpdated event observed
```

thì dòng log không chứng minh business state đã commit bền vững.

Ví dụ:

```java
@Transactional
public void changeEmail(...) {
    repository.save(...);
    publisher.publishEvent(new CustomerEmailChanged(...));
}
```

Đây là pseudocode; các biến và types cần có trong ứng dụng. Nếu transaction rollback sau publish, log của listener có thể đã tồn tại dù dữ liệu DB không đổi.

Một listener `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` có thể phù hợp khi chỉ muốn log milestone sau commit. Nhưng callback after-commit không tự đảm bảo log được ghi, retry sau crash, hoặc delivery bền vững.

**Ngôn ngữ log cần trung thực:** `event_received`, `handler_completed`, `business_committed` là những trạng thái khác nhau. Không ghi `outcome=SUCCESS` chỉ khi task vừa được submit cho executor.

### Không log mật khẩu dưới danh nghĩa audit

Khi một thay đổi credential thành công, audit có thể ghi `CredentialChanged`, actor/subject ID và timestamp theo policy. **Không** ghi password cũ/mới, password hash, reset token hoặc recovery code, kể cả vào bảng audit.

## 18. Khi dùng ErrorHandler hoặc async executor

Một lỗi ở listener có thể xuất hiện ở:

- `SimpleApplicationEventMulticaster.setErrorHandler(...)`.
- `AsyncUncaughtExceptionHandler` của `@Async void`.
- `Future.get()/CompletionException`.
- Task decorator/worker log.
- Retry scheduler, message listener container, outbox publisher.

Những thành phần này có thể log `Throwable` hoặc toàn bộ payload **bất chấp listener chính đã viết log an toàn**.

Ví dụ cần tránh:

```java
multicaster.setErrorHandler(error -> {
    logger.error("Listener failed: {}", error.getMessage());
});
```

Nếu message chứa email hoặc response body, nó bị lộ. Ngoài ra cách log trên bỏ stack trace/causal chain, khó debug.

Hướng xử lý có kiểm soát:

```java
multicaster.setErrorHandler(error -> {
    String code = classifyToStableErrorCode(error);
    logger.error("application_event_listener_failed error_code={}", code);
    recordFailureMetric(code);
});
```

Đây là snippet minh họa; `classifyToStableErrorCode` và `recordFailureMetric` cần do ứng dụng định nghĩa. Handler ở đây return, nghĩa là **suppress lỗi** trong multicaster; phải quyết định retry/escalation theo nghiệp vụ. Không vì muốn tránh rò PII mà âm thầm bỏ qua tác vụ thất bại quan trọng.

### Exception class vs exception message

`error.getClass().getSimpleName()` thường ít nhạy cảm hơn `error.getMessage()`, nhưng vẫn nên quy về error code allowlist nếu muốn metric labels hoặc log contract ổn định. Class name có thể làm lộ chi tiết nội bộ; stack trace phải được giữ ở kênh thích hợp và tuân thủ redaction policy.

## 19. Quản trị log pipeline, retention và xóa dữ liệu

Bảo vệ ở code là tầng đầu. Sau đó phải kiểm soát đường đi của log:

```text
Spring listener
   |
   v
SLF4J / Logback / encoder
   |
   v
stdout / log file / sidecar
   |
   v
collector / agent / pipeline processor
   |
   v
index / object storage / SIEM / monitoring vendor
   |
   v
dashboards / exports / backups
```

Mỗi điểm có thể tạo bản sao với retention và access khác nhau. Những biện pháp cần thiết:

- **Data classification:** trường nào được ghi, trường nào không, lý do và owner.
- **Least privilege:** ai đọc được log nào, giới hạn bởi môi trường và tenant khi cần.
- **Encryption in transit/at rest:** đường chuyển và lưu trữ đáp ứng chính sách tổ chức.
- **Retention:** thời hạn lưu tối thiểu cần cho mục đích rõ ràng, phù hợp luật/hợp đồng; không giữ vô thời hạn vì tiện debug.
- **Deletion/rectification:** có quy trình xử lý yêu cầu hợp lệ về dữ liệu cá nhân, including archives/backups và legal holds nếu có.
- **Access audit:** ghi nhận ai đã xem/xuất log nhạy cảm khi cần.
- **Vendor review:** log aggregator là một hệ thống xử lý dữ liệu; đánh giá vai trò, vị trí lưu, quyền truy cập và hợp đồng liên quan.
- **Incident response:** xác định mức độ, khoanh vùng, thu hồi/quay vòng credentials nếu token lộ, xử lý các bản sao đã lưu.

**Không có một thời hạn retention duy nhất đúng cho mọi nơi.** Nghĩa vụ cụ thể phụ thuộc pháp luật áp dụng, phân loại dữ liệu, loại log và quy trình của tổ chức. Các quy tắc kỹ thuật ở đây không thay thế đánh giá pháp lý hoặc chính sách bảo vệ dữ liệu.

## 20. Kiểm thử chống rò PII trong log

Kiểm thử chỉ nhìn `System.out.println` của demo chưa đủ. Một hệ thống production nên kiểm thử **đầu ra của logging backend** và các pipeline tương ứng.

### 20.1. Canary data

Dùng dữ liệu giả rõ ràng, không dùng hồ sơ người thật:

```text
canary.email@example.invalid
+10000000000
CANARY-SECRET-DO-NOT-LOG
```

Chèn canary vào payload hoặc exception response trong một integration test. Sau khi chạy operation, quét **captured log output** và khẳng định không có giá trị này. Nếu canary có thể đi vào collector, kiểm tra cả điểm xuất thông tin dưới điều kiện test được cô lập.

Không log canary như cách “test” trực tiếp trên production khi có nguy cơ ảnh hưởng alert/retention; dùng môi trường kiểm thử và quyền phù hợp.

### 20.2. JUnit assertion ở tầng formatter

Có thể tách việc dựng log field thành một pure function:

```java
static String safeSummary(CustomerEmailChanged event) {
    return "event_type=CustomerEmailChanged"
            + " event_id=" + event.eventId()
            + " outcome=OBSERVED";
}
```

Đây là snippet; cần record tương ứng. Test:

```java
String text = safeSummary(event);

assertFalse(text.contains(event.previousEmail()));
assertFalse(text.contains(event.newEmail()));
assertFalse(text.contains("CANARY-SECRET-DO-NOT-LOG"));
assertFalse(text.contains("\n"));
assertFalse(text.contains("\r"));
```

Đây là JUnit snippet, không nằm trong demo Maven phần 8; cần dữ liệu test tương ứng và imports JUnit. Kiểm thử riêng formatter giúp phát hiện regression khi ai đó thêm field nhạy cảm vào log.

### 20.3. Integration test bắt log thật

Với Logback, có thể gắn một `ListAppender<ILoggingEvent>` vào logger được kiểm thử rồi đọc `getFormattedMessage()`. Đây là phương án **Logback-specific**: project cần `logback-classic` trên test classpath và phải detach/stop appender sau test để tránh nhiễm state giữa các phương thức.

Test cần phân biệt:

- Message template và formatted message.
- Exception stack trace được encoder ghi ra sau message.
- MDC/markers/key-value pairs được backend thêm ngoài text.
- Log do các thư viện khác phát, không chỉ logger của listener.
- Nested JSON cấu trúc và encoding/output thực tế.

Nếu muốn chứng minh toàn bộ log không rò PII, cần capture cả **appender output cuối cùng**, không chỉ một field của `ILoggingEvent`.

### 20.4. Các tình huống cần test

| Tình huống | Kỳ vọng |
| --- | --- |
| Event thành công với email trong payload | Log chỉ có allowlisted metadata |
| Listener ném exception chứa email trong message | Logger/error handler không xuất raw email |
| Input chứa `\r`, `\n` hoặc delimiter | Không tạo log entry giả / JSON được escape đúng |
| Bật DEBUG/TRACE ở service và HTTP client | Không ghi secrets hoặc full request body |
| Event chạy qua `@Async`/executor | MDC không rò từ request/tenant trước |
| Một user thuộc tenant A, sự kiện của tenant B | Phân quyền và log access không cross-tenant |
| JSON event thêm field `accessToken` | Allowlist log không tự đưa field mới vào |
| Webhook/HTTP response lỗi chứa token | Log không xuất raw response |
| Replayed event cũ | Dữ liệu nhạy cảm không bị dump trong retry/error path |
| Tracing enabled | Span attributes/baggage không chứa canary |
| Metric labels | Không dùng ID người dùng/email/UUID mỗi event |
| Đổi cấu hình log level | Không làm lộ dữ liệu bất ngờ |

## 21. Quy trình code review cho logging của event listener

**Bước 1 — Xác định mục đích.** Log để đo throughput, tìm event ID, điều tra lỗi hay làm audit? Mỗi mục đích cần data contract riêng.

**Bước 2 — Phân loại event payload.** Tìm field cá nhân, secrets, free text, nested objects và derived identifiers. Không chỉ kiểm tra kiểu String; `Map` và object wrappers cũng có thể chứa dữ liệu.

**Bước 3 — Thiết kế log schema tối thiểu.** Bắt đầu bằng event type, event ID, handler, outcome, duration và error code đã chuẩn hóa.

**Bước 4 — Cấm dump objects.** Dò `logger.*("...{}", event)`, `event.toString()`, JSON serializer, request/response body logging, full exception message.

**Bước 5 — Kiểm soát đường lỗi.** Xem ErrorHandler, async executor, retry, fallback, exception mapper, tracing và HTTP client logs.

**Bước 6 — Kiểm tra encoding.** Untrusted fields phải được validate/giới hạn kích thước và encoder cần escape đúng output format, tránh log injection.

**Bước 7 — Phân loại ID.** UUID event khác ID user/tenant; stable identifier có khả năng tái định danh vẫn phải bảo vệ.

**Bước 8 — Kiểm soát context.** MDC/baggage chỉ chứa allowlisted metadata, cleanup giữa requests và executor tasks.

**Bước 9 — Test canary ở mức appender/pipeline.** Chạy cả success, failure, async, DEBUG/TRACE và stack trace.

**Bước 10 — Kiểm soát lưu trữ.** Đặt owner, access control, retention, encryption, export và incident response cho mọi log sink.

## 22. Những lỗi thường gặp

1. **Log trực tiếp record event** vì Java tự có `toString()`.
2. **Log toàn bộ JSON** rồi tin JSON serialization tự mask PII.
3. **Chỉ che email bằng regex** mà bỏ sót số điện thoại, nested payload, free text, token, URL query.
4. **Tin raw SHA-256(email) là anonymization** trong khi có thể dò dictionary.
5. **Ghi stable customer ID rồi tuyên bố log không chứa dữ liệu cá nhân**.
6. **Bật SQL bind parameter logging** trong production làm lộ giá trị thực.
7. **Log Authorization/Cookie headers** qua filter hoặc HTTP client interceptor.
8. **Cho rằng DEBUG không nguy hiểm** vì production thường bật INFO.
9. **Log `exception.getMessage()`** khi message chứa input hoặc response body.
10. **Đặt email/tenant/customerId vào metric tags**, gây high cardinality và rò.
11. **Đặt PII vào tracing baggage hoặc span attributes**, dù business logger đã an toàn.
12. **Không dọn MDC khi dùng thread pool**, dẫn tới log gắn nhầm user/tenant.
13. **Cho rằng SLF4J placeholder tự chống mọi log injection**, dù raw CRLF vẫn có thể được in.
14. **Mask ở collector nhưng bỏ qua bản raw tại stdout/agent**, nơi dữ liệu đã tồn tại.
15. **Giữ log vô thời hạn** vì chưa có retention policy.
16. **Trao quyền đọc toàn bộ log cho người không có quyền truy cập dữ liệu gốc**.
17. **Dùng audit log như debug log hoặc ngược lại**, làm yếu tính toàn vẹn và bảo vệ dữ liệu.
18. **Chỉ test happy path**, để error/async/retry log làm rò dữ liệu.
19. **Đổi format log nhưng không test encoder/structured fields**, khiến redaction mất hiệu lực.
20. **Log success trước khi transaction commit**, làm audit suy sai trạng thái.
21. **Ghi raw HTTP request body từ ContentCachingRequestWrapper** để debug một event.
22. **Bỏ qua logging ở thư viện bên thứ ba**, nhất là request/response và retries.
23. **Tin rằng token đã hết hạn thì có thể ghi log**, trong khi token, secrets và identifiers vẫn có thể gây rủi ro.
24. **Xóa dòng log “nhạy cảm” mà không kiểm tra bản sao và backups**, khiến kết quả xử lý sự cố không đầy đủ.

## 23. Checklist trước khi triển khai

- [ ] Có danh sách field được phép log theo từng loại event và use case?
- [ ] Không đưa raw event, entity, request, principal hay exception response body vào logger?
- [ ] Email, số điện thoại, giấy tờ, địa chỉ, token, cookie và secrets bị loại khỏi log thông thường?
- [ ] Opaque IDs được đánh giá như dữ liệu có thể liên kết, không coi mặc định là anonymous?
- [ ] Khi cần correlation, event ID và trace ID được tạo đúng, không chứa PII?
- [ ] Error codes và outcome là giá trị cố định/allowlisted?
- [ ] Không dùng untrusted text làm log message template?
- [ ] Structured encoder escape CRLF và các control characters phù hợp?
- [ ] Đã kiểm tra MDC cleanup, async listener và executor context propagation?
- [ ] Đã rà SQL bind log, HTTP body/header log, exceptions và thư viện bên thứ ba?
- [ ] Traces và metrics không vô tình xuất PII trong attrs/tags?
- [ ] Audit trail có schema, authorization và retention riêng?
- [ ] Quyền truy cập log storage, dashboards và exports áp dụng least privilege?
- [ ] Có thời hạn retention và quy trình xử lý dữ liệu, backup, legal hold phù hợp?
- [ ] Canary test đã kiểm tra output appender/pipeline khi success và failure?
- [ ] Cấu hình DEBUG/TRACE, logging backend, dependencies được kiểm tra theo phiên bản triển khai?
- [ ] Người vận hành có quy trình xử lý sự cố nếu đã phát hiện token/PII trong log?

**Kết luận:** Với Spring Application Events, một listener có thể cần đọc dữ liệu cá nhân để hoàn thành nghiệp vụ, nhưng **đọc được không có nghĩa được phép ghi vào log**. Hãy xem event payload, log record, tracing attributes và audit là các hợp đồng dữ liệu khác nhau. Tạo log từ **allowlist metadata tối thiểu**, tránh `event.toString()` và raw exception/request dumps, ngăn log injection, hạn chế quyền truy cập và retention, đồng thời kiểm thử toàn bộ pipeline bằng dữ liệu canary. Khi muốn tìm một sự cố cụ thể, dùng event/correlation ID an toàn để tra cứu hệ thống dữ liệu đã phân quyền, thay vì biến log thành bản sao hồ sơ khách hàng.

## Tài liệu tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Developer Guide — Security Logging and Monitoring](https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [SLF4J Manual](https://www.slf4j.org/manual.html)
- [OpenTelemetry — Semantic Conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/)
