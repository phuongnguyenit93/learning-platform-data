# Dữ liệu nhạy cảm trong event: thiết kế payload an toàn với Spring Framework

## 1. Vì sao event payload là một bề mặt rò rỉ dữ liệu?

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(event)` chuyển một đối tượng sự kiện tới cơ chế phân phối listener (`ApplicationEventMulticaster`). Một event có thể được nhiều `@EventListener` hoặc `ApplicationListener` tiếp nhận; các listener có thể ghi log, gửi metric, tạo tác vụ nền, lưu vào outbox hoặc chuyển tiếp sang message broker.

Vì vậy **payload của event phải được thiết kế như dữ liệu được chia sẻ cho những thành phần nhận nó**, không chỉ như tham số nội bộ của hàm đang gọi. Đưa mật khẩu, token, email, số giấy tờ hoặc thông tin tài chính vào event sẽ tạo thêm bản sao và đường truy cập không cần thiết.

Ví dụ **không nên làm**:

```java
// Trích đoạn minh họa một thiết kế không an toàn.
record CustomerUpdated(
        String customerId,
        String email,
        String password,
        String accessToken,
        String fullAddress) {}
```

Một listener chỉ cần biết "thông tin liên hệ đã thay đổi" nhưng lại nhận cả mật khẩu và access token. Nếu ai đó vô tình dùng `log.info("event={}", event)`, bản `toString()` mặc định của Java record còn có thể đưa toàn bộ nội dung vào log. Khi event được serialize thành JSON, dữ liệu nhạy cảm tiếp tục lan sang broker, dead-letter queue, công cụ APM và hệ thống lưu trữ bản sao.

**Nguyên tắc trọng tâm:** event chỉ nên mang **thông tin tối thiểu mà các consumer thực sự cần**, đúng mục đích và quyền truy cập của từng consumer. Nếu không có nhu cầu cụ thể, không đưa dữ liệu nhạy cảm vào event.

## 2. Phân loại dữ liệu trước khi xây dựng event

Không phải mọi dữ liệu đều nhạy cảm ở cùng một mức. Phân loại theo **khả năng gây hại nếu lộ**, mục đích sử dụng, khả năng liên kết để nhận diện một người, và chính sách bảo vệ của hệ thống.

| Nhóm | Ví dụ | Hướng xử lý mặc định khi thiết kế event |
| --- | --- | --- |
| Bí mật xác thực | Mật khẩu, mã OTP, refresh/access token, API key, khóa riêng | **Không đưa vào payload**; không ghi log; không phát lại qua event |
| Thông tin định danh cá nhân | Email, số điện thoại, địa chỉ, số giấy tờ, ngày sinh | Tránh đính kèm; dùng tham chiếu tối thiểu nếu consumer có quyền tra cứu |
| Dữ liệu tài chính/sức khỏe | Số tài khoản, thông tin thẻ, kết quả xét nghiệm, thông tin điều trị | Chỉ dùng khi có căn cứ nghiệp vụ và kiểm soát nghiêm ngặt; mặc định không phát rộng |
| Dữ liệu do người dùng nhập | Nội dung tin nhắn, ghi chú, tên tệp, văn bản tự do | Xem như dữ liệu không tin cậy; có thể chứa PII, bí mật hoặc payload gây log injection |
| Định danh có thể liên kết | Customer ID, order ID, tenant ID, IP, device ID | Không mặc nhiên "vô hại"; giới hạn scope, quyền tra cứu, retention |
| Metadata nghiệp vụ | Loại thay đổi, trạng thái, phiên bản aggregate, event ID | Chọn tối thiểu; ngay cả tên sự kiện đôi khi tiết lộ thông tin nhạy cảm |

Ví dụ tên `SensitiveDiagnosisConfirmed` đã có thể làm lộ thông tin sức khỏe chỉ từ **event type**, dù payload chỉ mang một ID. Khi miền nghiệp vụ nhạy cảm, cần xem xét cả tên event, routing key, topic name, metric tag và log message.

Một UUID ngẫu nhiên thay cho email giúp giảm lộ thông tin trực tiếp, nhưng **pseudonymization không đồng nghĩa anonymization**. Nếu người có quyền truy cập có thể dùng ID để tra cứu danh tính, ID vẫn có thể là dữ liệu cá nhân cần được bảo vệ.

## 3. Thiết kế theo consumer: ai thật sự cần trường nào?

Trước khi khai báo record event, đặt từng trường vào bảng nhu cầu:

| Trường ứng viên | Consumer nào cần? | Có thay thế được không? | Quyết định |
| --- | --- | --- | --- |
| `eventId` | Audit, retry, deduplication | Thường không | Có thể giữ, không chứa thông tin nhạy cảm trực tiếp |
| `customerRef` | Handler được ủy quyền cần tra cứu khách hàng | Opaque ID | Chỉ giữ nếu consumer thật sự cần; kiểm soát truy cập |
| `changedFields` | Audit hoặc đồng bộ hóa state | Enum thay vì dữ liệu cũ/mới | Có thể giữ ở mức chi tiết phù hợp |
| `newEmail` | Chỉ một dịch vụ gửi xác nhận có thể cần | Tra cứu có kiểm soát theo ID / luồng chuyên biệt | Mặc định loại khỏi event phát rộng |
| `oldEmail` | Hiếm khi cần ở các listener thường | Không truyền, hoặc luồng audit chuyên biệt | Loại khỏi event chung |
| `password` / `accessToken` | Không nên là dữ liệu của event phân phối rộng | Cơ chế xác thực/secret riêng | Loại bỏ hoàn toàn |
| `occurredAt` | Timeline nghiệp vụ, audit | Timestamp | Có thể giữ, cân nhắc khả năng liên kết |
| `schemaVersion` | Consumer ngoài tiến trình | Số phiên bản | Có thể giữ |

Kết quả ví dụ là một event tối giản:

```java
record ProfileChanged(
        String eventId,
        String customerRef,
        Set<ChangedField> changedFields) {}
```

Trong đó `ChangedField.EMAIL` có nghĩa **email đã thay đổi**, không mang giá trị email trước hoặc sau. Nếu một consumer cụ thể có quyền dùng giá trị mới, nó phải tra cứu qua một service được kiểm soát quyền hoặc một kênh chuyên biệt đã được đánh giá rủi ro.

Hãy cân nhắc **độ phân tán**: một event dùng cho 20 listener không nên chứa thêm thông tin chỉ vì một listener cần nó. Có thể tách event chuyên biệt có phạm vi truy cập hẹp, hoặc phát event tham chiếu chung và cung cấp thao tác tra cứu phù hợp cho consumer có quyền.

## 4. Ranh giới tin cậy trong luồng phân phối sự kiện

```text
Domain / Application service
    |
    | Thay đổi dữ liệu gốc trong kho được bảo vệ
    v
Tạo event tối thiểu
    |  eventId, customerRef, changedFields
    |  KHÔNG có email/mật khẩu/token
    v
ApplicationEventPublisher
    |
    +-- Audit listener: chỉ ghi event type + field names an toàn
    |
    +-- Cache listener: chỉ xử lý định danh trong phạm vi được phép
    |
    +-- Worker async: có thể chạy thread khác; không có mặc định
    |                 quyền truy cập hoặc context giống publisher
    |
    +-- Nếu có bridge/outbox/broker:
           serialize -> topic/queue -> DLQ -> replay -> backups
           mọi bản sao đều có thể lưu payload lâu hơn dự kiến
```

Trong cùng Spring application context, `@EventListener` không tự có cơ chế "field-level authorization" cho mọi payload. Một listener phù hợp về **kiểu event** có thể nhận toàn bộ object. Đừng coi việc các module "cùng ứng dụng" là lý do để đưa bí mật vào đối tượng event.

Đặc biệt, `ApplicationEventPublisher.publishEvent(Object)` có thể bao bọc POJO/record trong `PayloadApplicationEvent` khi phân phối. Mặc định, sự kiện thông thường được gọi đồng bộ; nhưng `publishEvent` về bản chất là **handoff** cho multicaster, không bảo đảm tất cả listener hoàn tất, và có thể có execution bất đồng bộ tùy cấu hình.

Sự thay đổi thread còn ảnh hưởng `SecurityContextHolder`, MDC, transaction và các giá trị `ThreadLocal`. Không dựa vào "publisher đang có quyền" để suy ra worker hoặc listener khác cũng có quyền đó.

## 5. Ví dụ Java 17 + Spring Framework 6.2 chạy độc lập

Mục tiêu: minh họa service có thể lưu email mới nhưng phát một event **không chứa email**, trong khi listener chỉ thấy loại thay đổi. Ví dụ không có database thật hay phân quyền thật; nó chứng minh cấu trúc payload và việc xử lý trong tiến trình, không phải một hệ thống bảo mật hoàn chỉnh.

### Cấu trúc

```text
safe-domain-events/
├── pom.xml
└── src/main/java/demo/SensitiveEventDemo.java
```

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>safe-domain-events</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SensitiveEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/SensitiveEventDemo.java`:

```java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SensitiveEventDemo {

    public enum ChangedField {
        EMAIL
    }

    // Event CHỈ chứa các field tối thiểu; không có email hay secret.
    public record ProfileChanged(
            String eventId,
            String customerRef,
            Set<ChangedField> changedFields) {

        public ProfileChanged {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(customerRef);
            changedFields = Set.copyOf(
                    Objects.requireNonNull(changedFields));
        }

        // Phòng ngừa khi ai đó vô tình log nguyên đối tượng.
        // Đây KHÔNG phải cơ chế bảo vệ JSON serialization.
        @Override
        public String toString() {
            return "ProfileChanged{changedFields=" + changedFields + "}";
        }
    }

    // Dữ liệu nhạy cảm thuộc kho dữ liệu gốc, không nằm trong event.
    public record Customer(String reference, String email) {
        @Override
        public String toString() {
            return "Customer{REDACTED}";
        }
    }

    public static class CustomerRepository {
        private final Map<String, Customer> rows = new HashMap<>();

        public CustomerRepository() {
            rows.put("customer-42",
                    new Customer("customer-42", "before@example.invalid"));
        }

        public Customer get(String reference) {
            Customer customer = rows.get(reference);
            if (customer == null) {
                throw new IllegalArgumentException("Unknown customer");
            }
            return customer;
        }

        public void save(Customer customer) {
            rows.put(customer.reference(), customer);
            System.out.println("repository: saved customer");
        }
    }

    public static class CustomerService {
        private final CustomerRepository repository;
        private final ApplicationEventPublisher publisher;

        public CustomerService(CustomerRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public void changeEmail(String customerRef, String newEmail) {
            Objects.requireNonNull(newEmail);
            // Đây chỉ là kiểm tra đầu vào tối thiểu để demo,
            // không phải email validator dùng trong production.
            if (!newEmail.contains("@")) {
                throw new IllegalArgumentException("Invalid email");
            }

            Customer old = repository.get(customerRef);
            repository.save(new Customer(old.reference(), newEmail));

            ProfileChanged event = new ProfileChanged(
                    UUID.randomUUID().toString(),
                    old.reference(),
                    Set.of(ChangedField.EMAIL));

            publisher.publishEvent(event);
            System.out.println("publisher: handoff complete");
        }
    }

    public static class AuditListener {
        @EventListener
        public void onProfileChanged(ProfileChanged event) {
            // Không log Customer/email, ID liên kết hay event object.
            System.out.println("listener: PROFILE_CHANGED fields="
                    + event.changedFields());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        CustomerRepository customerRepository() {
            return new CustomerRepository();
        }

        @Bean
        AuditListener auditListener() {
            return new AuditListener();
        }

        @Bean
        CustomerService customerService(
                CustomerRepository repository,
                ApplicationEventPublisher publisher) {
            return new CustomerService(repository, publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            CustomerService service =
                    context.getBean(CustomerService.class);
            CustomerRepository repository =
                    context.getBean(CustomerRepository.class);

            System.out.println("before: email stored in repository");
            service.changeEmail(
                    "customer-42", "replacement@example.invalid");
            System.out.println("after: email updated="
                    + "replacement@example.invalid".equals(
                            repository.get("customer-42").email()));
        }
    }
}
```

Chạy tại thư mục `safe-domain-events`, yêu cầu JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

Đầu ra do chương trình tự in (không tính thông tin phụ của Maven):

```text
before: email stored in repository
repository: saved customer
listener: PROFILE_CHANGED fields=[EMAIL]
publisher: handoff complete
after: email updated=true
```

### Giải thích và giới hạn của ví dụ

1. `CustomerRepository` giữ email trong cấu trúc dữ liệu riêng (ở đây là `Map` giả lập). Nó không in email vào stdout.
2. `CustomerService` cập nhật email trước, rồi tạo `ProfileChanged` với `eventId` ngẫu nhiên, `customerRef` và tập enum `EMAIL`. **Không có trường oldEmail/newEmail/token/password**.
3. Spring 6.2 phân phối record thông qua `publishEvent(Object)` đến phương thức `@EventListener` phù hợp. Với multicaster mặc định đồng bộ, dòng `listener` xuất hiện trước dòng `publisher: handoff complete`.
4. Bản `toString()` được viết để tránh lộ thông tin nếu ai đó in record. Tuy nhiên không nên log nguyên event và cũng không dựa vào `toString()` để bảo vệ serialization: một serializer JSON có thể truy cập trực tiếp `eventId` hoặc `customerRef`.
5. `Set.copyOf(...)` tạo tập immutable để consumer không sửa payload qua tham chiếu mutable sau khi event được tạo.
6. Chuỗi `replacement@example.invalid` là dữ liệu thử nghiệm thuộc miền `.invalid`, không phải thông tin liên hệ thật. Khi chạy thật phải thay bằng dữ liệu được xử lý theo quy định bảo vệ dữ liệu của ứng dụng.
7. Repository trong ví dụ **không có transaction, encryption hay authorization**. Đây là demo thiết kế event payload, không phải bằng chứng bảo vệ đầy đủ dữ liệu email khi lưu trữ.

**Quan trọng:** `customerRef` vẫn có thể là dữ liệu cá nhân dạng gián tiếp nếu được liên kết với hồ sơ khách hàng. Một listener muốn tra cứu hồ sơ phải được kiểm tra quyền theo user/service, tenant và mục đích sử dụng; việc có ID trong event không tự trao quyền truy cập.

## 6. Vì sao không nên dùng toàn bộ entity làm payload?

Một anti-pattern phổ biến:

```java
// Trích đoạn KHÔNG nên sử dụng cho event phát rộng.
publisher.publishEvent(customerEntity);
```

`customerEntity` có thể chứa email, địa chỉ, mối quan hệ JPA, thông tin thanh toán, lazy-loaded associations hoặc trường nội bộ chưa được phân loại. Khi gửi nguyên object:

- Listener nhận quá nhiều dữ liệu và có thể vô tình dùng thông tin ngoài phạm vi công việc.
- `toString()` tự sinh (record, Lombok `@Data`, hoặc code thủ công) có thể in cả dữ liệu nhạy cảm.
- Các công cụ mapping/serialization có thể duyệt getter và bất ngờ mở rộng đồ thị đối tượng.
- Entity mutable có thể đổi state sau khi event được phát, khiến listener async thấy kết quả không nhất quán.
- Lazy-loading và persistence context có thể gây lỗi ngoài transaction; việc sửa lỗi bằng cách eager-load mọi quan hệ lại làm phình payload.
- Nếu entity bị đưa vào broker/DLQ, thông tin nhạy cảm có thể được giữ lâu hơn database gốc.

**Thay thế:** xây một event record chuyên biệt, bất biến, chỉ mang snapshot của phần nghiệp vụ cần thiết. Nếu nhận event là đủ để tra cứu dữ liệu, chỉ mang một reference có kiểm soát; không phát tán toàn bộ entity.

Với một event cần snapshot (ví dụ số tiền thanh toán để tính đối soát), phải quyết định rõ trường đó có thật sự cần thiết, consumer nào được xem và dữ liệu ở event sẽ tồn tại bao lâu. Không áp dụng nguyên tắc "chỉ dùng ID" máy móc nếu consumer cần **giá trị tại thời điểm lịch sử** mà kho hiện tại có thể đã thay đổi.

## 7. ID tham chiếu có an toàn tuyệt đối không?

Không. Tham chiếu chỉ làm giảm việc sao chép các thuộc tính trực tiếp, không xóa trách nhiệm bảo vệ dữ liệu.

Đường xử lý phù hợp:

```text
ProfileChanged(eventId, customerRef, changedFields)
     |
     v
Consumer có nhu cầu sử dụng dữ liệu
     |
     +-- xác thực service / actor
     +-- xác định tenant và mục đích hợp lệ
     +-- kiểm tra quyền trên customerRef
     |
     v
RestrictedCustomerService.load(customerRef)
     |
     +-- chỉ trả trường cần thiết theo policy
     +-- ghi audit truy cập bằng metadata an toàn
     v
Xử lý và xóa dữ liệu tạm đúng chính sách
```

Rủi ro cần cân nhắc:

- **IDOR/BOLA**: consumer hoặc API dùng `customerRef` mà không kiểm tra quyền theo tenant/chủ thể có thể đọc nhầm dữ liệu người khác.
- **Linkability**: ID ổn định xuất hiện trong nhiều topic/log cho phép liên kết hoạt động của cùng một chủ thể.
- **Replay**: event cũ có thể bị replay sau khi quyền của consumer đã bị thu hồi; tra cứu lại phải đánh giá quyền *ở thời điểm xử lý*.
- **Snapshot vs current state**: nếu consumer tra cứu sau vài phút, email có thể đã đổi lần nữa; kết quả tra cứu không chắc phản ánh trạng thái tại thời điểm event.
- **Enumeration**: ID tuần tự có thể làm việc đoán đối tượng dễ hơn; opaque ID chỉ là một lớp giảm rủi ro, không thay thế access control.

Khi có yêu cầu snapshot lịch sử và nhạy cảm, có thể cần một kênh sự kiện riêng đã phân quyền chặt, payload mã hóa, hoặc lưu snapshot trong kho dữ liệu bảo vệ và phát reference truy cập giới hạn. Thiết kế tùy theo mục đích và retention; đừng để event chung mang quá nhiều thông tin chỉ nhằm tránh một lần tra cứu.

## 8. Logging, tracing và observability dễ làm lộ payload

Nguồn rò rỉ không chỉ ở listener nghiệp vụ. Payload có thể đi vào:

- Log `INFO`/`DEBUG` khi in event, parameters hoặc exception message.
- Structured logging khi logger tự lấy fields từ record/POJO.
- MDC, trace baggage, span attributes, metric labels và hệ thống APM.
- Dead-letter queue, retry topic, failure reports, error dashboards.
- HTTP access logs, webhook payload dumps, message serializer debug logs.
- Test snapshot, bản ghi lỗi CI, dump của JVM, bản sao dữ liệu phục vụ hỗ trợ.

Ví dụ không nên làm:

```java
// Nếu payload chứa PII, dòng này tạo rủi ro rò rỉ.
log.info("Received event {}", event);

// Có thể còn nguy hiểm hơn: biến email thành metric label,
// vừa lộ thông tin vừa tăng cardinality.
counter.tag("email", customer.getEmail());
```

Thiết kế tốt hơn là log một **allowlist** trường đã kiểm tra:

```java
// Trích đoạn minh họa, cần logger thật trong ứng dụng.
log.info("eventType=PROFILE_CHANGED changedFields={}",
        event.changedFields());
```

Lưu ý trường `changedFields` cũng có thể tiết lộ thông tin trong miền nhạy cảm. Với event về y tế hoặc tài chính, có thể chỉ log một code trung tính đã được phân loại.

### Masking, redaction và toString()

- **Không thu thập** dữ liệu vào event tốt hơn việc thu thập rồi masking.
- Nếu buộc phải lưu một phần, dùng **allowlist** thay vì serialize nguyên object rồi cố thay chuỗi bằng regex.
- `toString()` tùy chỉnh giúp giảm rủi ro log cơ bản, nhưng **không ngăn JSON/XML/protobuf serializer** đọc thuộc tính.
- Masking một phần (ví dụ email chỉ hiện 2 ký tự) vẫn có thể cho phép nhận diện. Đánh giá việc log các phần còn lại có thật sự cần không.
- Escape/control CR, LF và delimiters từ nội dung không tin cậy trước khi đưa vào log để giảm nguy cơ log injection.
- Đừng vô tình log request body hoặc exception chứa secret trong một listener chỉ vì đang debug lỗi.

OWASP Logging Cheat Sheet khuyến nghị loại bỏ, masking, sanitization, hashing hoặc encryption đối với loại dữ liệu nhạy cảm tùy hoàn cảnh, đồng thời hạn chế truy cập và vòng đời lưu trữ log. Tài liệu tham khảo ở cuối bài.

## 9. Hash, HMAC, tokenization và encryption có vai trò khác nhau

**Hash thường không đủ để "ẩn danh" một email hoặc số điện thoại.** Những trường có không gian giá trị dễ đoán có thể bị tấn công từ điển khi dùng `SHA-256(email)` thông thường. Không nên phát email hash ra mọi topic rồi coi đó là dữ liệu công khai.

Phân biệt:

| Kỹ thuật | Tác dụng | Giới hạn |
| --- | --- | --- |
| Loại bỏ field | Không tạo bản sao dữ liệu trong event | Consumer có thể cần luồng tra cứu khác |
| Tokenization/opaque reference | Thay giá trị bằng token hoặc ID, tra cứu qua vault/service | Vẫn cần bảo vệ token, map, authorization và retention |
| HMAC với khóa bí mật được quản lý | Tạo mã tham chiếu có kiểm soát từ dữ liệu đầu vào | Khóa phải được bảo vệ/luân chuyển; output vẫn có thể linkable |
| Encryption in transit (TLS) | Bảo vệ dữ liệu trên đường truyền | Consumer có quyền vẫn thấy plaintext; không bảo vệ log sau giải mã |
| Encryption at rest | Giảm rủi ro đọc dữ liệu từ storage/bản sao | Không thay thế phân quyền và quản lý khóa |
| Field-level encryption | Mã hóa một số trường nhạy cảm trong payload | Cần quản lý keys và consumer có quyền giải mã; không giải quyết việc phát quá rộng |

Nếu event phải chứa dữ liệu nhạy cảm trong một luồng chuyên biệt, hãy định nghĩa cụ thể bên nào mã hóa, ai giải mã, giới hạn quyền, thời hạn retention, rotation và cơ chế xóa/thu hồi. Không tự thiết kế thuật toán mật mã riêng. Mã hóa không làm một payload sai mục đích trở thành hợp lệ.

## 10. Event trong tiến trình khác với message broker/outbox

### In-process ApplicationEvent

Spring `@EventListener` có thể chạy trong cùng JVM, nhưng số listener có thể tăng dần theo module. Chỉ cần thêm một listener cho đúng type là số nơi có thể quan sát payload tăng lên. Không có field-level ACL mặc định ở multicaster.

### Khi event được đưa qua broker

Nếu bridge gửi event sang Kafka/RabbitMQ hoặc hệ thống khác, dữ liệu có thể tồn tại trong:

- Topic/queue và các replica.
- Consumer group đang trễ, retry và dead-letter topic.
- Backup, hệ thống phân tích, tracing và các bản dump vận hành.
- Schema registry hoặc sample payload do nhóm phát triển đưa vào tài liệu.
- Event archive lâu dài hoặc pipeline data lake.

Đặc biệt, giữ secret trong event không biến mất khi source database xóa secret đó. Phải xác định **retention của tất cả bản sao**, phân quyền theo topic/consumer, encryption, schema policy, môi trường staging và quy trình xóa theo yêu cầu áp dụng.

### Transactional outbox

Nếu cần phát event bền vững cùng transaction cập nhật aggregate, có thể ghi outbox row rồi relay:

```text
BEGIN DB TRANSACTION
    update customer_profile ...
    insert into outbox(event_id, type, customer_ref, changed_fields)
COMMIT

relay (sau commit)
    -> đọc outbox
    -> publish message
    -> retry/mark delivered
```

Outbox giải quyết **bảo toàn sự kiện qua crash** tốt hơn in-memory publish, nhưng nó còn tạo một **bản lưu lâu hơn**. Vì vậy thiết kế schema outbox cũng phải áp dụng data minimization, field encryption nếu cần, retention, quyền truy cập và chính sách xóa dữ liệu. Relay có thể phát trùng nếu đã gửi nhưng chưa cập nhật trạng thái; consumer nên idempotent dựa trên event ID.

### @TransactionalEventListener không phải công cụ lọc dữ liệu

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` giúp chỉ xử lý khi transaction đã commit, nhưng **không tự redaction payload**, không trao quyền, không bảo đảm consumer không log secret. Cũng không phải cơ chế lưu sự kiện bền vững sau crash. Phân biệt rõ *when to process* với *what data may be shared*.

## 11. Payload tối thiểu nhưng vẫn đủ cho nghiệp vụ

Không phải mọi event đều chỉ có ID. Một consumer có thể cần một snapshot lịch sử để đối soát, và tra cứu state hiện tại có thể trả thông tin khác.

Xem xét ba trường hợp:

**A. Đồng bộ lại cache thông tin hồ sơ.** Consumer chỉ cần `customerRef` và `changedFields`, sau đó tra cứu dữ liệu mới bằng API có authorization. Payload chung không cần chứa email.

**B. Thông báo "email đã đổi".** Một listener có thể cần gửi xác nhận tới địa chỉ mới. Thay vì đưa `newEmail` vào event chung, có thể dùng công việc gửi thông báo qua service chuyên biệt có quyền truy cập tối thiểu, hoặc kênh riêng được phân quyền và mã hóa phù hợp.

**C. Đối soát một khoản thanh toán.** Một snapshot như amount, currency hoặc payment reference có thể cần cho tính bất biến lịch sử. Dù vậy phải tránh số thẻ, CVV, token và các định danh thừa; chỉ consumer được ủy quyền mới nhận các dữ liệu có độ nhạy phù hợp.

Một schema event có thể kèm `eventId`, `occurredAt`, `aggregateVersion` và `schemaVersion` để hỗ trợ replay/idempotency. Chỉ thêm khi có nhu cầu; timestamp, ID và enum cũng có thể là thông tin liên kết khi kết hợp với dữ liệu khác.

**Quy tắc:** Nếu không giải thích được "consumer nào cần trường này và vì sao không thể thay bằng dữ liệu ít nhạy cảm hơn", đừng thêm nó vào payload chung.

## 12. Những tình huống phát sinh lỗi bảo mật

### 12.1. Gửi nguyên request DTO trong event

Request DTO thường chứa thông tin xác thực hoặc dữ liệu do client nhập. Đưa nguyên DTO vào event sẽ nhân rộng cả những field không dành cho listener. Xây event từ một schema allowlist rõ ràng sau khi kiểm tra nghiệp vụ.

### 12.2. Dùng @Data / record và log nguyên object

Lombok-generated `toString()`, Java record default `toString()` và structured logger có thể in toàn bộ field. Thiết kế phương thức redaction là lớp bảo vệ phụ, nhưng cách bền vững hơn là không có field nhạy cảm ngay trong event; kiểm tra log policy và unit tests.

### 12.3. Dùng email hoặc số giấy tờ làm event ID

Các identifier có thể bị lộ qua routing key, metrics, topic partitions, trace tags hoặc exception. Dùng một ID ngẫu nhiên/opaque phù hợp và giới hạn mapping ở service có quyền; không coi opaque ID là phương pháp thay cho authorization.

### 12.4. Consumer đọc dữ liệu người khác qua customerRef

Phát ID không cấp quyền. Cần kiểm tra tenant, mục đích sử dụng và quyền ở mỗi lần tra cứu. Đặc biệt không được dựa vào việc listener được gọi trong cùng process như một bằng chứng đã qua kiểm tra truy cập.

### 12.5. Truyền context nhạy cảm vào worker thread

Cơ chế `@Async` hoặc async multicaster thay đổi thread. Không copy toàn bộ `ThreadLocal`, HTTP headers hoặc security context sang worker chỉ để "giữ tiện ích"; chỉ truyền context cần thiết, được phép, theo cơ chế propagation an toàn. Khi xử lý event sau nhiều phút, xác thực và quyền hiện tại có thể đã thay đổi.

### 12.6. Replay event cũ mà bỏ qua chính sách dữ liệu mới

Một consumer replay event tồn tại lâu có thể phục hồi dữ liệu đã hết hạn hoặc đã bị yêu cầu xóa theo chính sách. Kiểm soát retention và quyền ở **cả broker, DLQ, outbox, backup và consumer storage**; lập kế hoạch migration, deletion hoặc tombstone theo công nghệ và nghĩa vụ pháp lý thực tế.

### 12.7. Đặt PII làm tag metrics

Các tag như `email`, `phone`, `customerId` thường làm tăng cardinality, tốn tài nguyên và có thể tiết lộ dữ liệu cho người xem dashboard. Dùng nhãn thấp cardinality như event type trung tính, kết quả xử lý, tên module hoặc code lỗi đã được chuẩn hóa.

### 12.8. Tin rằng encryption giải quyết mọi rủi ro

Nếu mọi consumer đều có key giải mã, event vẫn bị phát tán quá rộng. Nếu payload bị log trước khi mã hóa hoặc sau khi giải mã, TLS và encryption at rest không cứu được. Quyền truy cập, minimization, monitoring và quy trình xử lý sự cố vẫn bắt buộc.

## 13. Kiểm thử payload an toàn

Ngoài kiểm thử event được gửi đúng, hãy kiểm tra **những dữ liệu không được có**:

1. **Schema allowlist:** event `ProfileChanged` không có accessor `email()`, `password()` hoặc `accessToken()`; consumer nhận chỉ các trường cho phép.
2. **Kết quả nghiệp vụ:** cập nhật email vào repository thành công, nhưng listener chỉ nhận metadata tối thiểu.
3. **Không lộ qua log:** kiểm tra captured logs của publisher/listener, lỗi và serializer không chứa địa chỉ email thử nghiệm hoặc token giả.
4. **JSON thực tế:** nếu dùng Jackson/Avro/Protobuf cho broker, serialize event trong test và kiểm tra danh sách keys. `toString()` không chứng minh JSON an toàn.
5. **Trường gián tiếp:** thử dùng customer ID của tenant khác; listener/service tra cứu phải từ chối khi thiếu quyền.
6. **Async/replay:** người nhận không được dựa vào `SecurityContextHolder` của publisher; khi replay phải kiểm tra quyền và retention ở thời điểm xử lý.
7. **DLQ và outbox:** lỗi publish/consume không đẩy secret vào error message, raw headers hoặc dead-letter body.
8. **Idempotency:** event ID không chứa PII và consumer không áp dụng side effect trùng khi nhận lại cùng event.
9. **Snapshot:** với nghiệp vụ cần giá trị lịch sử, xác nhận schema lưu vừa đủ và được bảo vệ đúng phân loại.
10. **Review thay đổi schema:** thêm field mới bắt buộc trải qua đánh giá consumer, log, retention, access control và backward compatibility.

Một cách kiểm tra nhanh trong code review là lập danh sách các trường của event rồi trả lời bốn câu hỏi cho từng trường: **Ai cần? Để làm gì? Ở đâu sẽ lưu? Bao lâu?** Nếu không trả lời được, trường đó có thể đang làm tăng rủi ro không cần thiết.

### Trích đoạn test cần tránh lỗi phổ biến

```java
// Đây là ý tưởng kiểm thử, không phải một lớp JUnit độc lập.
// Không kiểm tra an toàn chỉ bằng profileChanged.toString().
String json = objectMapper.writeValueAsString(profileChanged);
assertFalse(json.contains("replacement@example.invalid"));
assertFalse(json.contains("accessToken"));
```

Tuy nhiên, một test dùng `contains(...)` là **hàng rào bổ sung**, không thay thế việc kiểm tra cấu trúc schema, privacy classification và kiểm thử quyền truy cập. Phải cấu hình serializer thật đang dùng và tránh ghi lại chính JSON nhạy cảm khi test thất bại.

## 14. Checklist triển khai

- [ ] Xác định consumer và mục đích trước khi chốt event type/schema.
- [ ] Áp dụng allowlist field; loại credentials, tokens, passwords và dữ liệu không cần thiết.
- [ ] Dùng event bất biến; tránh entity/DTO mutable và deep object graph.
- [ ] Xem opaque ID là dữ liệu có thể liên kết; kiểm tra tenant và authorization lúc tra cứu.
- [ ] Bảo đảm logger, tracer, metrics, exception và DLQ không lưu các trường bị cấm.
- [ ] Tách lựa chọn thời điểm publish/commit khỏi lựa chọn dữ liệu được chia sẻ.
- [ ] Nếu có broker/outbox, xác định retention, encryption, consumer ACL, deletion và replay.
- [ ] Xem xét idempotency, dữ liệu lịch sử, schema version và sự thay đổi quyền của consumer.
- [ ] Có tests về dữ liệu bị loại trừ, kết quả serialize, log và cross-tenant access.
- [ ] Đánh giá tác động privacy/security mỗi khi thêm một trường mới hoặc mở rộng tập consumer.

**Kết luận:** Một event tốt không phải event chứa "đủ mọi thứ để ai cũng tiện dùng", mà là event có **ngữ nghĩa rõ, dữ liệu tối thiểu, quyền nhận và vòng đời sử dụng kiểm soát được**. Trong Spring Framework, multicaster và annotation giúp phân phối event; phần bảo vệ dữ liệu nhạy cảm vẫn là trách nhiệm của thiết kế domain, application layer và hạ tầng vận hành.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Application Events và @EventListener](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — API Security Top 10: Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
