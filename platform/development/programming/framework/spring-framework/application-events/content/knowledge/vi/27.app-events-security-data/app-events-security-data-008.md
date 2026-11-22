# Audit event và retention trong Spring Framework Application Events

Trong hệ thống nghiệp vụ, **audit event** (sự kiện phục vụ kiểm toán/truy vết) ghi lại *ai hoặc hệ thống nào đã thực hiện hành động gì, trên đối tượng nào, tại thời điểm nào và kết quả ra sao*. **Retention** là chính sách xác định audit record cần được giữ bao lâu, vì mục đích gì, ai có quyền truy cập và phải xóa, ẩn danh, lưu trữ lạnh hay tạm giữ theo căn cứ nào khi hết thời hạn.

Ví dụ: người quản trị thay đổi quyền của một tài khoản, nhân viên phê duyệt đơn hàng, một tác vụ tự động xuất dữ liệu hoặc người dùng đăng nhập thất bại. Những hành động này có thể cần một audit trail đáng tin cậy để điều tra, đối soát và xác định trách nhiệm.

Đối với **Spring Framework Application Events**, một điểm quan trọng là:

> `ApplicationEventPublisher.publishEvent(...)` chỉ phát một event trong tiến trình. Nó **không tự lưu audit record, không bảo đảm commit, không cung cấp immutable audit store và không triển khai retention**.

Người thiết kế phải quyết định **event nào cần audit**, **audit record được lưu ở đâu**, **ràng buộc với transaction nào**, và **retention job thực hiện ra sao**. Một hệ thống ghi audit rất đầy đủ nhưng không giới hạn thời gian lưu, hoặc tự ý ghi toàn bộ dữ liệu nhạy cảm, vẫn có thể tạo ra rủi ro bảo mật và vi phạm chính sách quản trị dữ liệu.

Mục tiêu của bài:

- Phân biệt **domain event**, **audit event**, **application log** và **Spring Data auditing metadata**.
- Thiết kế **audit envelope** đủ để đối soát nhưng tối thiểu hóa dữ liệu nhạy cảm.
- Hiểu hành vi của `@EventListener`, `@TransactionalEventListener`, rollback và khả năng mất event.
- Chọn cách ghi audit cùng transaction hoặc qua **Transactional Outbox** khi yêu cầu bền vững.
- Thiết kế **retention schedule** có mục đích, thời hạn, legal hold, deletion/anonymization, backup và khả năng kiểm chứng.
- Áp dụng bằng một chương trình Java 17+ với Spring Framework 6.2, Spring JDBC và H2; quan sát kết quả commit/rollback và cleanup.

## 1. Audit event khác gì một domain event hoặc dòng log?

Một domain event như `OrderApproved` mô tả **một sự thật nghiệp vụ đã xảy ra**. Nó có thể được dùng để kích hoạt đọc mô hình, gửi thông báo hoặc phối hợp các bounded contexts.

Một audit record lại được tối ưu để trả lời **câu hỏi điều tra**. Ví dụ:

```text
actor=staff-17
action=ORDER_APPROVE
resourceType=ORDER
resourceId=order-42
decision=ALLOWED
outcome=SUCCESS
occurredAt=2026-01-10T00:00:00Z
correlationId=req-12
```

Các giá trị là **dữ liệu giả định**. Một event nghiệp vụ `OrderApproved(orderId)` chưa chắc chứa actor hoặc quyết định ủy quyền; audit record có thể bổ sung những thông tin đó từ **ngữ cảnh đã được xác thực ở ranh giới ứng dụng**.

| Loại dữ liệu | Dùng để | Giới hạn |
| --- | --- | --- |
| **Domain event** | Mô tả sự kiện nghiệp vụ, kích hoạt logic khác | Không mặc nhiên có đủ dữ liệu kiểm toán hoặc retention |
| **Audit event/record** | Truy vết ai, làm gì, khi nào, trên đối tượng nào, kết quả | Phải được bảo vệ, kiểm soát truy cập và vòng đời lưu trữ |
| **Application log** | Chẩn đoán lỗi và hoạt động runtime | Có thể bị xoay vòng, sampling, mất dòng; không tự là bằng chứng bền vững |
| **Spring Data auditing** | Lưu `createdBy/createdDate/lastModifiedBy/lastModifiedDate` cho entity | Thường mô tả **trạng thái metadata hiện tại**, không phải toàn bộ lịch sử thay đổi |
| **Outbox event** | Lưu ý định giao message cùng transaction dữ liệu | Có lifecycle gửi/retry khác với retention của audit trail |

**Spring Data JPA** hỗ trợ `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate` và `AuditorAware`. Nó hữu ích để biết ai tạo/sửa entity gần nhất nhưng **không tự thay thế một bảng audit history nhiều phiên bản**. Một record có thể đã bị thay đổi mười lần trong khi `lastModifiedBy` chỉ lưu người sửa cuối.

Không nên “audit” bằng cách chỉ viết `log.info("User changed role")`, vì log thường không có ràng buộc giao dịch, chính sách integrity, access control hoặc retention phù hợp với yêu cầu audit.

## 2. Phân loại audit events theo mục đích

Trước khi tạo schema, xác định **những hành động cần lưu** và yêu cầu bảo vệ:

| Nhóm | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Security audit** | Đăng nhập thất bại, thay đổi quyền, khóa tài khoản | Ai cố truy cập, kết quả và điểm kiểm soát nào quyết định? |
| **Business audit** | Phê duyệt đơn, hoàn tiền, chuyển trạng thái hợp đồng | Quyết định nghiệp vụ nào đã hoàn thành? |
| **Administrative audit** | Thay đổi cấu hình, tạo API key, xuất dữ liệu | Ai tác động vào hệ thống và tài nguyên nào? |
| **Data access audit** | Truy cập/đọc/xuất dữ liệu nhạy cảm | Ai đã truy cập dữ liệu nào, với mục đích hoặc quyền gì? |
| **Operational audit** | Job hệ thống thay đổi một tập bản ghi | Tác vụ tự động nào làm thay đổi dữ liệu? |

Không phải mọi event trong Spring context đều nên được persist. Spring còn có các **framework/lifecycle events** như `ContextRefreshedEvent`; nếu ghi tất cả chúng vào bảng audit, bạn có thể tạo nhiễu, tăng dung lượng và lưu dữ liệu không có giá trị kiểm toán.

Tạo **allowlist event types** được phép audit, quy định rõ hành động và outcome. Một listener tổng quát nhận `Object` rồi serialize toàn bộ payload là thiết kế có rủi ro cao.

### Sự kiện thành công và sự kiện thất bại có semantics khác nhau

Ví dụ “ORDER_APPROVED” chỉ nên được lưu như **thành công** khi thay đổi đã được commit theo hợp đồng nghiệp vụ. Trong khi đó, một lần **đăng nhập bị từ chối** cũng là một sự kiện bảo mật quan trọng, dù không có transaction nghiệp vụ nào commit.

Vì thế đừng mặc định áp dụng duy nhất một cơ chế “audit trong transaction của đơn hàng” cho cả audit thành công và audit thất bại. Với hành động bị từ chối hoặc transaction rollback, có thể cần **audit storage/transaction độc lập** nhưng vẫn phải tránh tạo nhật ký sai rằng một thay đổi nghiệp vụ đã thành công.

## 3. Thiết kế cấu trúc Audit Event Envelope

Một audit envelope thực tế nên ổn định và có semantic rõ:

```json
{
  "auditId": "aud-4d7e",
  "eventType": "ORDER_APPROVAL",
  "schemaVersion": 1,
  "eventId": "evt-65b2",
  "aggregateType": "ORDER",
  "aggregateId": "order-42",
  "actorRef": "staff-17",
  "action": "APPROVE",
  "decision": "ALLOWED",
  "outcome": "SUCCESS",
  "occurredAt": "2026-01-10T00:00:00Z",
  "recordedAt": "2026-01-10T00:00:01Z",
  "correlationId": "req-12",
  "retentionClass": "BUSINESS_AUDIT_V1"
}
```

Đây là **JSON minh họa**, không phải một chuẩn bắt buộc do Spring Framework sinh sẵn. Trường nào cần thiết phụ thuộc mục đích audit và chính sách của tổ chức.

**Vai trò các trường:**

- `auditId`: khóa duy nhất của **bản ghi audit**, hỗ trợ truy vấn/đối soát.
- `eventId`: ID của **logical source event** để correlation/dedup khi cần; không đồng nhất bắt buộc với `auditId`.
- `eventType` và `schemaVersion`: định danh hợp đồng để consumer tương lai có thể đọc dữ liệu lịch sử.
- `aggregateType`/`aggregateId`: loại và khóa đối tượng tác động; tránh nhét cả graph JPA vào record.
- `actorRef`: định danh actor đã được xác thực hoặc định danh một service/batch job; không tự tin vào chuỗi actor gửi từ client.
- `action`: động từ nghiệp vụ có tập giá trị chuẩn hóa, ví dụ `APPROVE`, `REVOKE`.
- `decision`: kết quả kiểm tra quyền/luật, ví dụ `ALLOWED`/`DENIED` khi phù hợp.
- `outcome`: `SUCCESS`/`FAILURE`/`REJECTED`; phải định nghĩa rõ thời điểm có thể xác nhận outcome.
- `occurredAt`: thời gian sự kiện được quan sát tại nguồn; không phải lúc lưu vào audit store.
- `recordedAt`: thời điểm audit store chấp nhận bản ghi, giúp đo ingestion delay.
- `correlationId`: nối với request/trace hoặc workflow mà không làm phát sinh số lượng metric labels không kiểm soát.
- `retentionClass`: tham chiếu tới **policy được version hóa**, không phải lý do để mọi record có cùng thời hạn.

### Event time và record time cần được tách

Khi dùng outbox hoặc message broker, một audit record có thể được xử lý **vài phút sau khi sự kiện xảy ra**. Không nên ghi mọi timestamp bằng `Instant.now()` ở listener rồi giả định đó là thời gian hành vi nghiệp vụ.

Ví dụ:

```text
occurredAt = 10:00:00Z  (hành động được tạo)
committedAt = 10:00:01Z (transaction commit, nếu có thể xác định)
recordedAt = 10:03:30Z (audit sink ghi sau retry)
```

Không phải hệ thống nào cũng có `committedAt` chính xác; nếu không có cơ chế lấy được thời điểm commit đáng tin cậy, **đừng tự bịa field đó**. Sử dụng các timestamp có nguồn rõ ràng, chuẩn hóa UTC/`Instant` cho lưu trữ, hiển thị timezone tại UI.

### Versioning của audit payload

Audit record thường được giữ lâu và đọc lại sau khi deploy nhiều phiên bản phần mềm. Vì vậy:

1. Không đổi ý nghĩa của trường cũ chỉ bằng cách giữ tên (ví dụ tiền từ đồng sang xu).
2. Thêm trường optional với default có **ý nghĩa nghiệp vụ rõ**.
3. Nếu breaking change, dùng `schemaVersion`, adapter/upcaster hoặc loại event mới.
4. Lưu thông tin tối thiểu để diễn giải lịch sử mà không phụ thuộc tên class Java/package.
5. Test replay fixtures cho các phiên bản đã từng được ghi.

**Một JSON parse thành công không chứng minh diễn giải kiểm toán đúng.** Audit cần semantics có thể bảo vệ trước việc đổi code.

## 4. Data minimization: không lưu toàn bộ event vào audit

Audit trail có giá trị vì **đúng mục đích**, không phải vì chứa càng nhiều dữ liệu càng tốt. Một ví dụ tệ:

```java
log.info("audit {}", objectMapper.writeValueAsString(request));
```

Nếu `request` chứa password, access token, số thẻ, địa chỉ, thông tin sức khỏe hoặc payload tự do, cách này có thể ghi bí mật vào logs và các hệ thống lưu trữ thứ cấp. Việc thêm `@EventListener` không làm dữ liệu được sanitize.

**Nên:**

- Dùng **allowlist fields** theo loại audit: ID đối tượng, hành động, outcome, actorRef được tin cậy, mốc thời gian, correlation ID.
- Không chứa raw password, session cookie, access token, API key, JWT, connection secret, payment-card sensitive data hoặc toàn bộ HTTP headers/body nếu không có mục đích/kiểm soát đặc biệt.
- Pseudonymize actor/subject khi không cần danh tính rõ, nhưng **không mặc định pseudonymized data là anonymous**. Một ID ổn định có thể liên kết về cá nhân.
- Sanitize dữ liệu có nguồn không tin cậy để chống **log injection** qua CR/LF hoặc ký tự điều khiển; với SQL dùng parameterized statements.
- Không serialize trực tiếp JPA entity đang managed, có lazy association hoặc các quan hệ chứa PII.
- Giới hạn độ dài và miền giá trị của `eventType`, `action`, `outcome` và các string do caller cung cấp.
- Với actor, lấy danh tính từ Spring Security context/server-side principal hoặc một nguồn xác thực tại boundary; không chấp nhận `actorId` tùy ý từ request làm “bằng chứng” cho audit.

**Ví dụ phân loại:**

| Dữ liệu | Mặc định |
| --- | --- |
| Event type, action enum, policy version | Thường có thể lưu |
| Mã đơn hàng/tài nguyên, actorRef | Lưu nếu cần, kiểm soát truy cập; có thể là dữ liệu cá nhân gián tiếp |
| Trace ID, request ID | Có thể lưu cho correlation, xét thời hạn/khả năng định danh |
| Email/số điện thoại/địa chỉ | Hạn chế hoặc tránh lưu nếu ID tham chiếu đủ dùng |
| Password, token, session secret, key | Không lưu nguyên giá trị |
| Full request/response body | Tránh mặc định; thường chứa dữ liệu ngoài nhu cầu audit |
| Lý do lỗi | Dùng mã lỗi hoặc message đã lọc secrets, không lưu toàn stack trace bất kỳ |

OWASP Logging Cheat Sheet khuyến nghị giới hạn dữ liệu nhạy cảm, bảo vệ quyền truy cập, phát hiện sửa đổi và quy trình hủy log khi hết thời hạn. Điều đó áp dụng cho audit trail chứ không chỉ file log truyền thống.

## 5. Transaction: audit phải phản ánh đúng kết quả

Đây là phần quyết định tính tin cậy của audit.

### 5.1. @EventListener đồng bộ: có thể cùng transaction nguồn

Trong cấu hình mặc định, `SimpleApplicationEventMulticaster` gọi `@EventListener` đồng bộ trên **thread của publisher**. Nếu service publish event **bên trong transaction** và listener dùng cùng Spring transaction manager/DataSource, thao tác SQL trong listener có thể tham gia **chính transaction đó**:

```text
BEGIN T1
  INSERT orders(id, status)
  publishEvent(OrderApproved)
      -> @EventListener
           INSERT audit_events(...)
COMMIT T1
```

**Lợi ích:** nếu cả hai insert thành công rồi transaction commit, có một record audit đi cùng thay đổi nghiệp vụ. Nếu transaction rollback, cả order và audit record cùng rollback. Điều này phù hợp cho **audit một sự thay đổi đã thực sự commit**, nhưng **không lưu vết riêng của nỗ lực bị từ chối** nếu bạn muốn lưu cả thất bại đó.

Lưu ý:

- `publishEvent(...)` chạy xong **chưa chứng minh transaction đã commit**.
- Listener đồng bộ có thể ném unchecked exception làm service thất bại và transaction rollback theo policy.
- Nếu listener catch lỗi audit rồi nuốt trong khi audit là bắt buộc, transaction có thể commit **không có audit**, trái hợp đồng.
- Nếu audit lưu qua một resource khác nhưng không tham gia cùng transaction, không được giả định có atomicity xuyên hai database.
- Không làm I/O ra mạng chậm trong cùng transaction chỉ để audit; có thể kéo dài lock/connection và làm tăng p95/p99 request latency.

### 5.2. @TransactionalEventListener(AFTER_COMMIT): đúng phase, nhưng không atomic audit

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderApproved(OrderApproved event) {
    auditWriter.write(event);
}
```

Đây là **đoạn tích hợp minh họa**, cần các kiểu `OrderApproved`, `auditWriter`, transaction phù hợp và các imports.

Callback chỉ chạy khi transaction nguồn **commit thành công**, mặc định `fallbackExecution = false` nên publish ngoài transaction phù hợp có thể bị bỏ qua.

Tuy nhiên:

1. Dữ liệu đơn hàng **đã commit** trước khi listener xử lý.
2. Nếu ghi audit thất bại, **không thể rollback transaction nguồn** đã commit.
3. Nếu process chết ở khoảng giữa commit và callback, audit event trong JVM có thể **bị mất**.
4. Nếu listener sau commit cần **ghi database mới**, thường phải mở **transaction mới rõ ràng**, ví dụ service `@Transactional(propagation = Propagation.REQUIRES_NEW)` được gọi qua Spring proxy. Với transaction imperative, tài nguyên giao dịch có thể vẫn còn gắn vào thread trong callback nhưng không có commit mới cho thao tác bạn vừa ghi nếu chỉ dựa vào transaction cũ.
5. Callback `AFTER_COMMIT` **không mặc định async**; I/O chậm trong callback có thể vẫn kéo dài request.

Vì thế, `@TransactionalEventListener(AFTER_COMMIT)` không phải cơ chế bảo đảm “mọi record audit đều tồn tại đúng một lần”. Nó giải quyết **thời điểm phản ứng**, không tự giải quyết lưu bền vững, retry hay deduplication.

### 5.3. Audit thất bại/denied phải được tách đúng ranh giới

Một nỗ lực đăng nhập bị từ chối vẫn có thể cần audit dù transaction nghiệp vụ không tồn tại hoặc rollback. Không thể dựa vào một `INSERT audit` trong **cùng transaction sẽ rollback** mà kỳ vọng bản ghi đó sống sót.

Hướng xử lý cần lựa chọn rõ:

- **Security logging pipeline độc lập** với transaction nghiệp vụ, được quản trị retention và integrity.
- **Transaction audit riêng** theo thiết kế, ví dụ `REQUIRES_NEW` qua Spring proxy cho imperative flow, nếu việc ghi vào cùng database và semantics cho phép.
- **Durable event ingestion** với xác nhận ghi/queue, có dead-letter và chính sách overload, nếu audit không được mất khi process lỗi.

Phải định nghĩa **fail-open hay fail-closed** cho từng loại audit. Một việc ghi metric best-effort không nên chặn nghiệp vụ quan trọng, nhưng một thao tác có yêu cầu audit bắt buộc có thể cần từ chối nếu audit store không sẵn sàng. Quyết định này thuộc hợp đồng/risk policy, không phải lựa chọn mặc định do Spring cung cấp.

## 6. Ví dụ hoàn chỉnh Java 17+: audit record cùng transaction và retention cleanup

Ví dụ dùng Spring Framework **6.2.9**, Spring JDBC và H2. Không cần Spring Boot hay web server.

Ta tạo:

- Bảng `purchase_orders` lưu đơn hàng.
- Bảng `audit_events` lưu event audit tối thiểu.
- `AuditRequested` là event immutable; `AuditListener` nhận bằng `@EventListener` đồng bộ và ghi `audit_events` qua `JdbcTemplate`.
- `TransactionTemplate` bao trùm `INSERT purchase_orders` và `publishEvent(...)`, để cả đơn và audit ở **cùng transaction**.
- Một lần xử lý thứ hai cố tình rollback. Sau rollback, cả đơn và audit mới đều không có trong DB.
- Cleanup dùng `expires_epoch_ms` được tính từ thời điểm event + 30 ngày **chỉ để minh họa**; nó xóa audit đến hạn nhưng **không xóa đơn hàng nghiệp vụ**.

Đây là một bài thực hành **về mechanics**, không phải hệ thống audit production. Không dùng thời hạn 30 ngày này làm chính sách pháp lý thật; chưa có legal hold, auth, partitioning, archive, backup purge hay integrity signature trong demo.

### 6.1. Cấu trúc

```text
audit-event-retention-demo/
├── pom.xml
└── src/main/java/example/AuditEventRetentionDemo.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>audit-event-retention-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                    <mainClass>example.AuditEventRetentionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. src/main/java/example/AuditEventRetentionDemo.java

```java
package example;

import java.time.Duration;
import java.time.Instant;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class AuditEventRetentionDemo {

    // Payload chỉ chứa những trường cần cho ví dụ.
    public record AuditRequested(
            String eventId,
            String orderId,
            String actorRef,
            String action,
            Instant occurredAt) {
    }

    public static class AuditListener {
        private final JdbcTemplate jdbc;
        private static final Duration DEMO_RETENTION =
                Duration.ofDays(30);

        public AuditListener(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @EventListener
        public void onAuditRequested(AuditRequested event) {
            long occurred = event.occurredAt().toEpochMilli();
            long expires = event.occurredAt()
                    .plus(DEMO_RETENTION).toEpochMilli();

            jdbc.update(
                "INSERT INTO audit_events " +
                "(event_id, order_id, actor_ref, action, " +
                "occurred_epoch_ms, expires_epoch_ms) " +
                "VALUES (?, ?, ?, ?, ?, ?)",
                event.eventId(),
                event.orderId(),
                event.actorRef(),
                event.action(),
                occurred,
                expires
            );

            // "Staged" chưa có nghĩa transaction đã commit.
            System.out.println("audit: staged " + event.eventId());
        }
    }

    private static long countOrders(JdbcTemplate jdbc) {
        Long value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders", Long.class);
        return value == null ? 0 : value;
    }

    private static long countAudit(JdbcTemplate jdbc) {
        Long value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events", Long.class);
        return value == null ? 0 : value;
    }

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL(
                "jdbc:h2:mem:audit_retention_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute(
                "CREATE TABLE purchase_orders (" +
                "id VARCHAR(40) PRIMARY KEY, status VARCHAR(30) NOT NULL)");
        jdbc.execute(
                "CREATE TABLE audit_events (" +
                "event_id VARCHAR(80) PRIMARY KEY, " +
                "order_id VARCHAR(40) NOT NULL, " +
                "actor_ref VARCHAR(80) NOT NULL, " +
                "action VARCHAR(80) NOT NULL, " +
                "occurred_epoch_ms BIGINT NOT NULL, " +
                "expires_epoch_ms BIGINT NOT NULL)");

        TransactionTemplate tx = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));

        Instant referenceTime =
                Instant.parse("2026-01-10T00:00:00Z");

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(
                    AuditListener.class, () -> new AuditListener(jdbc));
            context.refresh();

            // Kịch bản 1: nghiệp vụ + audit đều commit.
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO purchase_orders (id, status) " +
                    "VALUES (?, ?)", "order-1", "APPROVED");
                context.publishEvent(
                        new AuditRequested(
                                "evt-ok", "order-1",
                                "staff-ref-7", "ORDER_APPROVE",
                                referenceTime));
            });
            System.out.println("business: committed order-1");

            // Kịch bản 2: toàn bộ transaction rollback.
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.update(
                        "INSERT INTO purchase_orders (id, status) " +
                        "VALUES (?, ?)", "order-2", "APPROVED");
                    context.publishEvent(
                            new AuditRequested(
                                    "evt-reverted", "order-2",
                                    "staff-ref-7", "ORDER_APPROVE",
                                    referenceTime));
                    throw new IllegalStateException("rollback demo");
                });
            } catch (IllegalStateException expected) {
                System.out.println("business: rolled back");
            }

            System.out.println(
                "before cleanup: orders=" + countOrders(jdbc) +
                " audits=" + countAudit(jdbc));

            // Mô phỏng worker retention chạy sau 31 ngày.
            Instant cleanupAt = referenceTime.plus(
                    Duration.ofDays(31));
            int removed = jdbc.update(
                "DELETE FROM audit_events " +
                "WHERE expires_epoch_ms <= ?",
                cleanupAt.toEpochMilli());

            System.out.println("retention: removed=" + removed);
            System.out.println(
                "after cleanup: orders=" + countOrders(jdbc) +
                " audits=" + countAudit(jdbc));
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`, cần **JDK 17+**, Maven và quyền tải dependencies lần đầu:

```bash
mvn -q compile exec:java
```

Các dòng do **chính chương trình** in ra theo thứ tự (không tính log của Maven và Spring):

```text
audit: staged evt-ok
business: committed order-1
audit: staged evt-reverted
business: rolled back
before cleanup: orders=1 audits=1
retention: removed=1
after cleanup: orders=1 audits=0
```

### 6.4. Vì sao kết quả như vậy?

1. `AnnotationConfigApplicationContext` được refresh sau khi đăng ký `AuditListener` là Spring bean. Spring phát hiện phương thức `@EventListener`.
2. Event `AuditRequested` là Java record; Spring xử lý plain-object payload qua cơ chế `PayloadApplicationEvent` khi cần, listener vẫn nhận được kiểu record.
3. `JdbcTemplate` và `DataSourceTransactionManager` sử dụng **cùng `DataSource`**, nên hai lần `INSERT` trong cùng callback `TransactionTemplate` tham gia một database transaction. Listener chạy đồng bộ theo multicaster mặc định.
4. Event `evt-ok` được publish, listener in `audit: staged evt-ok`. Sau đó transaction thực sự commit và chương trình in `business: committed order-1`.
5. Event `evt-reverted` cũng được publish và listener in `staged`; tuy nhiên sau đó code ném `IllegalStateException` nên transaction rollback. Cả `order-2` và bản ghi `evt-reverted` đều **không còn** trong database. Một dòng log từ listener trước rollback không phải bằng chứng audit đã được lưu bền vững.
6. Trước cleanup chỉ có **một đơn hàng** và **một audit record** đã commit.
7. Demo đặt expiration là `referenceTime + 30 ngày`. Cleanup sau `31 ngày` xóa đúng record đã đến hạn, nhưng không động tới bảng đơn hàng. `removed=1` và `audits=0` thể hiện retention cleanup đã có hiệu lực.

**Giới hạn:** Demo dùng transaction một database trong H2 và không có security principal thật. Trong production phải tạo actorRef server-side, validate action, phân loại retention policy, áp dụng legal hold, hạn chế quyền ghi/xóa và quản lý backup/archive. Thời gian 30 ngày ở đây là một con số **giả lập cho học tập**, không phải thời hạn pháp luật mặc định.

## 7. Transactional Outbox: audit sau commit nhưng vẫn có đường phục hồi

Nếu mục tiêu là gửi audit sang một **dịch vụ audit riêng** hoặc kho lưu trữ bảo mật mà không chặn request bằng network call, có thể dùng **Transactional Outbox**:

```text
Transaction T1:
    UPDATE order status = APPROVED
    INSERT outbox_events(
        event_id, type, payload_minimized,
        status = PENDING, created_at, ...)
    COMMIT T1
          |
          v
Background dispatcher
    claim PENDING message
    -> send to audit sink
    -> ACK / retry with backoff
    -> mark SENT
          |
          v
Audit sink
    deduplicate by event_id / audit_id
    append audit record under retention policy
```

Thiết kế này cho phép recover khi process chết **sau commit nhưng trước khi giao**. Tuy vậy:

- Outbox và thay đổi nghiệp vụ phải được ghi **atomic** trong cùng transaction. Chỉ gọi `publishEvent` rồi ghi outbox sau commit không có cùng bảo đảm.
- Worker có thể gửi thành công rồi crash trước khi đánh dấu `SENT`, dẫn tới **delivery trùng**. Audit sink cần idempotency/unique key.
- **Outbox retention** (bao lâu giữ message đã gửi) **khác** với **audit retention** (bao lâu giữ bằng chứng kiểm toán). Không xóa audit cùng lúc cleanup outbox.
- **Retry có giới hạn** cần exception taxonomy, backoff, jitter và dead-letter/failure state. Không nuốt lỗi và coi là success.
- Audit sink có thể xử lý event bất đồng bộ; outcome và thời điểm ghi của nó khác thời điểm transaction nguồn commit.
- Nếu yêu cầu zero-gap giữa commit nghiệp vụ và audit, audit cùng transaction hoặc một hạ tầng giao dịch/bằng chứng được thiết kế nghiêm ngặt hơn có thể cần thiết. Outbox cung cấp khả năng phục hồi, không tự biến hai dịch vụ thành một transaction ACID xuyên mạng.

Đối với **event bị từ chối** (ví dụ quyền không đủ), phải có đường ghi audit riêng vì sẽ không có transaction nghiệp vụ thành công để ghi outbox theo cùng cách. Thiết kế riêng pipeline audit bảo mật và error path.

## 8. Retention policy: đừng chọn thời hạn bằng cảm tính

**Retention** phải dựa vào **mục đích, phân loại dữ liệu, rủi ro và nghĩa vụ pháp lý/hợp đồng áp dụng**. Không có một con số mặc định chung cho tất cả ứng dụng Spring.

Một policy record nên có:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `retentionClass` | Nhóm audit, ví dụ SECURITY_AUDIT / BUSINESS_AUDIT |
| `purpose` | Tại sao cần lưu: điều tra, đối soát, tuân thủ nghĩa vụ |
| `legalBasisOrPolicyRef` | Tham chiếu căn cứ/phê duyệt hợp lệ, không chỉ một chuỗi tùy tiện |
| `startsAt` / retention trigger | Tính thời hạn từ event time, commit time, tài khoản đóng hay mốc khác |
| `durationOrEndRule` | Số ngày/tháng/năm hoặc quy tắc phụ thuộc mốc nghiệp vụ |
| `actionAtExpiry` | Xóa, ẩn danh, archive, đưa vào quy trình kiểm duyệt trước xóa |
| `legalHoldPolicy` | Khi nào giữ lại có phê duyệt và ai có quyền giải phóng hold |
| `accessPolicy` | Role nào xem, tìm kiếm, xuất, xóa hoặc thay đổi policy |
| `policyVersion` | Hợp đồng retention có thể thay đổi theo thời gian |
| `backupHandling` | Cách hết hạn trên backup, replica, cold archive và search index |
| `verification` | Cách chứng minh job đã chạy và không xóa dữ liệu không đủ điều kiện |

**Ví dụ phân loại mang tính minh họa, không có giá trị pháp lý:**

```text
SECURITY_AUDIT_V1:
  purpose: investigate access and privilege changes
  duration: determined by approved security/legal schedule
  at_expiry: delete or anonymize unless valid hold

BUSINESS_APPROVAL_V1:
  purpose: reconstruct approval decisions
  duration: determined by applicable recordkeeping obligations
  at_expiry: archive or dispose according to approved policy

DEBUG_TELEMETRY_V1:
  purpose: short-term troubleshooting
  duration: shorter operational window
  at_expiry: rotate/delete with backup propagation
```

Không gán số năm cụ thể trong ví dụ này, vì **thời hạn bắt buộc phụ thuộc ngành, nơi xử lý dữ liệu và loại hồ sơ**. Một tổ chức chịu GDPR có nguyên tắc **storage limitation** và phải lưu dữ liệu cá nhân **không lâu hơn mức cần thiết cho mục đích** hoặc các nghĩa vụ lưu giữ hợp pháp. Những quy định áp dụng tại Việt Nam hoặc quốc gia khác cần được bộ phận pháp chế/bảo vệ dữ liệu đánh giá riêng; không suy ra từ bài học kỹ thuật.

### Retention bắt đầu tính từ đâu?

- Nếu policy nói “xóa sau 90 ngày kể từ khi sự kiện được tạo”, trigger có thể là `occurredAt`.
- Nếu policy nói “giữ tới N năm sau khi hợp đồng kết thúc”, expiration **không thể tính một lần từ `occurredAt`** khi hợp đồng vẫn mở.
- Nếu record được tạo muộn do retry, dùng `recordedAt` để tính expiration có thể giữ lâu hơn policy nếu trigger thật là `occurredAt`.
- Nếu policy thay đổi, có thể cần đánh giá lại các record đã tồn tại; không tự sửa ngầm expiration thiếu approval.

Trong SQL schema production nên tách **policy version**, **retention trigger** và `expires_at` để có thể giải thích sau này. Với thời hạn theo tháng/năm theo múi giờ, dùng lịch thích hợp (`ZonedDateTime`/`LocalDate` + zone/rules) thay vì giả định “một tháng = 30 ngày”. Demo Java dùng `Duration.ofDays(30)` chỉ vì quy tắc minh họa cố định 30×24 giờ.

## 9. Retention lifecycle: lưu, khóa quyền, hết hạn và xử lý hủy

Một vòng đời có kiểm soát:

```text
AUDIT CAPTURED
       |
       +-- validated + classified
       |
       v
ACTIVE (searchable by authorized roles)
       |
       +-- retention clock / policy version
       |
       +-- legal hold? ---- YES ---> HELD (restricted, reviewable)
       |                          |
       |                          +-- hold released --> evaluate expiry
       |
       +-- NO and expired
       |
       v
DISPOSITION QUEUE
       |
       +-- delete / anonymize / policy-approved archive
       |
       v
VERIFIED DISPOSITION
       |
       +-- record minimal non-sensitive proof:
           batch id, count, timestamp, policy version, outcome
```

**Append-only trong thời gian lưu** không đồng nghĩa “không bao giờ xóa”. Audit records có thể cần chống sửa đổi lén lút khi còn hiệu lực, nhưng retention scheduler vẫn phải có quyền **disposition** được kiểm soát, có phê duyệt, xác thực và khả năng kiểm chứng.

### Bước 1 — Đánh dấu đối tượng cần xử lý

Worker đọc record **đã đến hạn**, lọc theo policy đang hiệu lực và legal hold. Không nên xóa trực tiếp mọi record có timestamp cũ mà chưa xác nhận trigger/hold.

Ví dụ SQL **minh họa schema production**, không phải câu lệnh chạy nguyên trong demo mục 6:

```sql
SELECT audit_id
FROM audit_events
WHERE expires_at <= :cutoff
  AND legal_hold = FALSE
ORDER BY expires_at
FETCH FIRST 1000 ROWS ONLY;
```

Dấu `:cutoff` là **named parameter của tầng application**; cách phân trang/lock phụ thuộc database. Query production cần thêm phân vùng theo tenant/policy và cơ chế claim để tránh hai workers xóa trùng ngoài ý muốn.

### Bước 2 — Xóa theo batch nhỏ, tránh giữ lock dài

Không chạy `DELETE` hàng triệu rows trong một transaction lớn nếu có thể dùng batch có chỉ số và partition/pruning:

- Tạo index thích hợp cho `expires_at`, `retentionClass` và tình trạng hold theo workload.
- Xử lý batch giới hạn, commit giữa các batch.
- Khi có partition theo ngày/tháng và toàn bộ partition đủ điều kiện, cân nhắc drop/rotate partition **chỉ sau khi xác nhận tất cả records đều đủ điều kiện và không có legal hold**.
- Ghi progress checkpoint để job restart an toàn; idempotent cleanup.
- Giới hạn throughput để không ảnh hưởng SLA truy vấn audit hoặc transaction nghiệp vụ.
- Xử lý retry cho DB errors có giới hạn, báo dead-letter/alerts khi không thể hoàn tất.

### Bước 3 — Kiểm tra các bản sao

Một record có thể tồn tại tại:

```text
primary audit DB
    +-- read replicas
    +-- full-text search index
    +-- monitoring / logs
    +-- cached exports
    +-- object storage
    +-- cold archive
    +-- backup snapshots
```

Chỉ xóa trên primary table **không đồng nghĩa** đã xóa mọi bản sao. Chính sách retention nên nêu rõ sự khác biệt giữa data **đang hoạt động** và backup snapshot chỉ có thể expire theo vòng quay backup đã thiết kế. Cần quy trình xử lý khi restore backup để record đã hết hạn không vô tình tái xuất hiện, và quyền truy cập backup không kém bảo mật hơn hệ thống chính.

Nếu cần thực thi yêu cầu xóa dữ liệu cá nhân, cần đánh giá phạm vi tất cả bản sao/công cụ tìm kiếm/export và các ngoại lệ hợp pháp. Một ID được băm không mặc nhiên có nghĩa đã ẩn danh nếu còn khả năng liên kết lại với cá nhân.

### Bước 4 — Ghi bằng chứng về hành động retention

Một job retention cũng là thao tác đặc quyền, nên có thể cần ghi **bằng chứng tối thiểu**:

```json
{
  "jobId": "retention-job-88",
  "policyVersion": "SECURITY_AUDIT_V1",
  "startedAt": "2026-02-10T00:00:00Z",
  "completedAt": "2026-02-10T00:01:00Z",
  "selected": 300,
  "deleted": 300,
  "failed": 0,
  "operator": "system-retention-worker"
}
```

Đây là **metadata minh họa**, không cần giữ danh sách đầy đủ các audit records vừa xóa. Nếu “bằng chứng đã xóa” lại sao chép toàn bộ nội dung bị xóa, mục tiêu retention có thể bị vô hiệu hóa.

Một số nơi cần **tombstone** để đồng bộ yêu cầu xóa sang downstream. Tombstone cũng phải tuân theo policy riêng và chỉ chứa thông tin tối thiểu cần thiết.

## 10. Legal hold và yêu cầu xóa dữ liệu cá nhân

Có hai nguyên tắc dễ bị hiểu thành mâu thuẫn:

- **Integrity:** record không nên bị người dùng hoặc quản trị viên tùy tiện sửa/xóa để che dấu hành vi khi nó còn phải được giữ.
- **Storage limitation/erasure:** dữ liệu không được giữ vô thời hạn nếu không còn mục đích/căn cứ hợp lệ; trong một số điều kiện, cá nhân có quyền yêu cầu xóa hoặc hạn chế xử lý.

Vì vậy một audit store đáng tin cậy thường có **append-only cho hoạt động bình thường**, nhưng có một **disposition path được kiểm soát** để hết hạn/xóa/ẩn danh hoặc giữ lại theo legal hold đã được phê duyệt.

**Legal hold** không phải một cờ do người vận hành bất kỳ tự bật để giữ dữ liệu mãi mãi. Nó cần:

1. Lý do/căn cứ và phạm vi records hợp lệ.
2. Người có quyền phê duyệt, thời điểm bắt đầu và điều kiện kết thúc/review.
3. Quyền truy cập hạn chế trong thời gian hold.
4. Log sự kiện bật/tắt hold được bảo vệ.
5. Cơ chế tự quay lại đánh giá retention khi hold được giải phóng.

Không thể đưa ra một thời hạn giữ tối thiểu hoặc ngoại lệ xóa phổ quát cho mọi ngành/lãnh thổ. Hãy tham chiếu lịch lưu trữ hồ sơ của tổ chức, nghĩa vụ pháp lý có liên quan và tư vấn bộ phận pháp chế/bảo vệ dữ liệu khi thiết kế thực tế.

## 11. Bảo vệ integrity: chống sửa đổi lén lút và truy cập trái phép

Audit data có thể là mục tiêu của người muốn **xóa dấu vết**. Do đó, một table bình thường với quyền `UPDATE`/`DELETE` rộng rãi chưa đủ cho yêu cầu nhạy cảm.

### 11.1. Quyền tối thiểu và phân tách trách nhiệm

- Account ghi audit của ứng dụng chỉ nên có **INSERT và những quyền tối thiểu cần thiết**, không có quyền xóa/sửa mọi record.
- Retention worker dùng một role riêng, chỉ được xóa/ẩn danh record đủ điều kiện và có logging/phê duyệt theo chính sách.
- Vai trò đọc audit được tách khỏi vai trò viết/xóa; dùng RBAC/ABAC theo tenant và mục đích.
- Mọi truy vấn, export, điều chỉnh policy và bật legal hold nhạy cảm nên được quản trị và ghi nhận phù hợp.
- Mã hóa at rest và in transit; kiểm soát key rotation/backup/access to encryption keys.
- Giới hạn tốc độ tra cứu/export và tránh truy vấn theo key không có quyền, vì audit store có thể chứa những sự kiện rất nhạy cảm.

### 11.2. Tamper-evident khác tamper-proof

Có thể thêm một chuỗi hash/HMAC hoặc chữ ký cho các bản ghi/batch:

```text
digest_n = HMAC(key, canonical(record_n) || digest_(n-1))
```

Đây là **công thức khái niệm**, không phải một giao thức chuẩn đầy đủ. Nếu có HMAC hoặc chữ ký và key được giữ ngoài tầm ảnh hưởng của kẻ sửa database, thay đổi quá khứ sẽ khó thực hiện mà không bị phát hiện.

Cần thiết kế thêm:

- Canonical serialization ổn định, versioned schema.
- Bảo vệ key trong KMS/HSM hoặc boundary độc lập.
- Thứ tự record và concurrency (partition/hash chain theo stream hoặc batch).
- Anchor digest tới kho độc lập/WORM khi cần.
- Cách **chứng minh retention deletion hợp lệ** khi một mắt xích đã bị xóa: ví dụ ký các batch/chứng thư và giữ metadata tối thiểu, hoặc dùng cấu trúc integrity phù hợp với xóa có quản trị.

**Không gọi một hash thông thường là “bảo mật tuyệt đối”**. Nếu attacker có quyền ghi database và cũng sửa được toàn bộ chain/checkpoint, một hash chain không có anchor/key bảo vệ độc lập có thể bị tính lại.

### 11.3. Chống log injection và dữ liệu đầu vào giả mạo

Một chuỗi do người dùng gửi như `"OK\nadmin=trusted"` có thể làm log text trở nên sai lệch nếu không được encode/sanitize. Dùng structured logging và kiểm soát CR/LF, delimiter. Khi ghi SQL, dùng prepared statements/`JdbcTemplate` có parameters thay vì nối chuỗi do user điều khiển.

Actor và outcome phải được xác định từ logic xác thực/ủy quyền của **server**, không từ event payload do client tự khai. Khi cần kiểm toán một request bị từ chối, record đúng loại “DENIED” ngay tại security boundary.

## 12. Hiệu năng, dung lượng và chi phí giữ audit

Audit có thể trở thành nguồn dữ liệu có tốc độ tăng rất lớn:

```text
events_per_day × average_record_size × retention_days
```

Ví dụ **giả định**: 100.000 audit events/ngày, mỗi record trung bình 800 bytes và retention 90 ngày:

```text
100,000 × 800 × 90 = 7,200,000,000 bytes
≈ 7.2 GB payload thô (hệ thập phân)
```

Con số chưa gồm index, metadata, replication, backup, encryption overhead, log shipping và các bản sao search. Không dùng nó làm sizing production nếu chưa đo payload, index và truy vấn thật.

Những nguyên tắc:

- Ưu tiên **event có giá trị audit** thay vì ghi mọi Spring event theo kiểu broadcast.
- Dùng bản ghi nhỏ, có schema và tập field tối thiểu; không đưa full JPA entity/HTTP body vào.
- Partition theo thời gian/tenant nếu workload và database hỗ trợ; retention cleanup theo partition khi an toàn.
- Chọn index theo truy vấn thực tế (actor, aggregate, time, type) và kiểm soát chi phí ghi.
- Tách hot storage để truy vấn gần đây và cold storage nếu policy cho phép, nhưng phải quản lý tổng thời hạn ở cả hai.
- Giám sát tốc độ ingest, backlog, lỗi lưu, p95 query latency, disk/IO/backup growth và số records đến hạn chưa disposition.
- Với audit **bắt buộc**, xác định hành vi khi audit storage full/down. Không âm thầm bỏ event để giảm latency.

**Một số nhóm security events có thể cần phản hồi fail-closed**, nhóm telemetry/debug có thể best-effort. Không áp dụng một chính sách lỗi cho mọi loại vì sự khác nhau về risk và nghĩa vụ.

## 13. Các anti-patterns nguy hiểm

**1. Ghi mọi Spring event bằng `@EventListener(Object)` vào JSON.**  
Có thể vô tình lưu bean lifecycle events, token, dữ liệu nội bộ hoặc một object graph lớn. Chỉ audit event types được cho phép.

**2. Dùng `@TransactionalEventListener(AFTER_COMMIT)` rồi coi đó là audit bảo đảm cùng transaction.**  
Callback nằm sau commit; nếu lỗi ghi hoặc process chết, nghiệp vụ đã commit nhưng audit có thể thiếu.

**3. Ghi audit trong transaction sẽ rollback nhưng cần lưu bằng chứng nỗ lực thất bại.**  
Record cũng rollback. Cần pipeline hoặc transaction riêng theo chính sách cho các security failures/denied actions.

**4. Lấy actorId từ trường user gửi rồi coi là danh tính đã xác minh.**  
Có thể bị giả mạo. Lấy từ principal/server context được xác thực; phải quản lý cả service accounts.

**5. Chỉ giữ `@LastModifiedBy` rồi tuyên bố có lịch sử audit bất biến.**  
Metadata cho lần sửa cuối không phải lịch sử mọi lần thay đổi; audit trail là một mô hình bổ sung.

**6. Ghi cả request body/response body hoặc stack trace với token và PII.**  
Có thể làm rò bí mật qua SIEM/backups. Dùng allowlist, sanitize và kiểm soát cấp độ dữ liệu.

**7. Đặt “retention = forever” để tránh rủi ro xóa thiếu.**  
Có thể vi phạm data minimization/storage limitation; tăng rủi ro lộ dữ liệu và chi phí. Cần policy được phê duyệt, có hold hợp lệ nếu phải giữ lâu hơn.

**8. Chạy `DELETE` theo tuổi record mà không kiểm tra legal hold.**  
Có thể phá nghĩa vụ lưu giữ. Retention cần trạng thái hold và xác minh điều kiện disposition.

**9. Xóa DB xong tuyên bố toàn bộ dữ liệu đã biến mất.**  
Search index, export, backup, replica và cold archives có thể còn bản sao. Cần vòng đời xóa cho từng sink.

**10. Không lưu schemaVersion/eventType ổn định.**  
Sau nhiều năm, dữ liệu cũ có thể không đọc được vì đổi tên class hoặc format. Cần versioned audit schema/upcaster.

**11. Dựa vào log “audit staged” để kết luận transaction thành công.**  
Listener đồng bộ có thể đã chạy trước khi transaction rollback. Phải kiểm chứng dữ liệu đã commit.

**12. Cho rằng digest có thể ngăn mọi sửa đổi.**  
Hash chain thiếu key/anchor độc lập có thể bị thay toàn bộ; retention deletions cũng cần cơ chế chứng minh hợp lệ.

**13. Cho rằng outbox tự bảo đảm exactly-once.**  
Dispatcher có thể gửi trùng khi crash; audit consumer phải deduplicate bằng ID ổn định.

**14. Retention job không có monitoring hoặc audit của chính nó.**  
Job có thể ngừng chạy hoặc xóa sai mà không ai phát hiện. Cần metrics, alerts, kiểm tra mẫu và bằng chứng disposition không nhạy cảm.

## 14. Kế hoạch kiểm thử audit và retention

Nên có **test nghiệp vụ, test transaction, test quyền và test lifecycle**.

### 14.1. Integration test transaction

| Kịch bản | Kỳ vọng |
| --- | --- |
| Business change commit | Order và audit row cùng tồn tại |
| Listener ghi audit thất bại, audit bắt buộc | Transaction nguồn không được commit thành công nếu thiết kế đồng bộ atomic |
| Business transaction rollback sau publish | Audit trong cùng transaction cũng rollback |
| Security action bị deny | Có bản ghi denied theo đường audit độc lập đã thiết kế |
| `@TransactionalEventListener(AFTER_COMMIT)` ghi audit | Không chạy khi rollback; kiểm tra durability riêng khi crash |
| Outbox dispatcher gửi trùng | Audit sink không tạo hai logical records |

Không nên chỉ dùng `@RecordApplicationEvents` để kết luận audit đã persist. Recorder của `spring-test` xác nhận **event đã publish**, không xác nhận commit, không chứng minh retention hoặc audit sink đã lưu dữ liệu.

### 14.2. Test retention với Clock cố định

Đừng làm test ngủ 30 ngày hoặc phụ thuộc vào giờ máy:

1. Inject `Clock` hoặc cung cấp mốc tham chiếu vào retention service.
2. Tạo records trước, đúng và sau expiration threshold.
3. Đặt legal hold cho một subset và xác nhận chúng **không bị disposition**.
4. Xác nhận records đủ điều kiện được xóa/ẩn danh, còn order/business data không bị ảnh hưởng.
5. Chạy cleanup lần thứ hai và xác nhận idempotency (không xóa thêm ngoài mong đợi).
6. Mô phỏng DB failure giữa các batches; job restart tiếp tục từ checkpoint/claim state.
7. Kiểm tra backup/index/archive propagation theo chính sách, không chỉ row count ở primary.

Demo mục 6 dùng `Instant` cố định và một thời hạn minh họa để kiểm chứng cùng nguyên tắc mà không cần ngủ hoặc sửa đồng hồ hệ thống.

### 14.3. Security/privacy tests

- User không có role đọc audit không thể query/export audit records.
- Một tenant không thể xem hoặc xóa records của tenant khác.
- App writer không thể cập nhật/xóa lịch sử audit ngoài phạm vi cần thiết.
- Retention worker không được xóa record đang legal hold.
- Payload có token/password/PII giả lập không lọt vào audit serialization/log.
- CR/LF/delimiter từ input không tạo log injection.
- ID không được lấy từ client không xác thực để gán actor có quyền.
- Truy cập audit store, export và thay đổi policy đều được theo dõi theo chính sách.
- Khôi phục backup không phục hồi trái phép record đã hết hạn mà không có quy trình xử lý.

### 14.4. Reliability và vận hành

- Downstream audit tạm ngưng: outbox giữ event, retry có giới hạn, backlog được cảnh báo.
- Process chết sau commit nhưng trước send: worker có thể phục hồi.
- Send thành công rồi crash trước ACK: consumer dedup xử lý an toàn.
- Schema thay đổi: dữ liệu lịch sử vẫn đọc được theo version.
- Disk/storage gần đầy: cảnh báo trước khi mất audit bắt buộc, xác định fail-open/fail-closed.
- Retention worker bị dừng: oldest-expired-record age và backlog tăng, có alert.

## 15. Checklist triển khai production

Trước khi chấp nhận một audit workflow dựa trên Spring events, cần trả lời:

1. **Audit scope:** loại action/event nào cần audit, mục đích và căn cứ ghi là gì?
2. **Trust boundary:** actor/decision/outcome được tạo tại server, có thể bị giả mạo bởi client không?
3. **Schema:** event ID, type, version, aggregate ID, timestamp và correlation có ổn định không?
4. **Sensitive data:** có allowlist, masking/redaction và phân loại dữ liệu nhạy cảm không?
5. **Atomicity:** audit phải cùng commit với nghiệp vụ hay có thể eventual consistency?
6. **Rollback/denied events:** có đường ghi riêng khi transaction thất bại không?
7. **Durability:** mất process sau commit có mất audit không; có outbox/retry/dedup nếu cần?
8. **Access:** reader/writer/retention operator/hold approver có phân quyền tách biệt?
9. **Integrity:** có chống sửa đổi và kiểm chứng dấu vết độc lập theo risk policy không?
10. **Retention:** ai phê duyệt thời hạn, policy version, trigger và disposition?
11. **Hold/erasure:** có cơ chế legal hold và xử lý yêu cầu xóa/ẩn danh hợp lệ không?
12. **Copies:** replica, search, cache, export, backup và archive có lịch xóa tương ứng không?
13. **Operations:** có batch job, checkpoint, monitoring, alerts và runbook khôi phục không?
14. **Tests:** đã test commit/rollback, duplicated event, data leak, hold, expiration, restore chưa?

Mô hình tốt nhất thường không phải “một listener làm mọi thứ”, mà là **một hợp đồng audit rõ ràng** có pipeline ghi, bảo vệ, truy vấn và retention với trách nhiệm của từng lớp được kiểm chứng.

## 16. Câu hỏi tự đánh giá

**1. Một `@EventListener` đã in “audit recorded”, có chắc audit đã tồn tại bền vững không?**  
Không. Nếu listener tham gia transaction chưa commit và transaction rollback, audit row có thể biến mất. Phải kiểm tra commit/database.

**2. `@TransactionalEventListener(AFTER_COMMIT)` có bảo đảm audit cùng transaction nghiệp vụ không?**  
Không. Callback chạy sau commit; lỗi hoặc process crash có thể làm audit thiếu. Cân nhắc ghi cùng transaction hoặc outbox tùy yêu cầu.

**3. Tại sao không lưu toàn bộ Java event payload vào audit?**  
Vì có thể chứa PII/secrets, object graph lớn và schema không ổn định. Nên dùng envelope với allowlist các trường có mục đích kiểm toán.

**4. `@CreatedBy` và `@LastModifiedDate` có thay thế audit history không?**  
Không. Chúng cung cấp metadata tạo/sửa entity, không tự lưu toàn bộ chuỗi hành động đã diễn ra.

**5. Vì sao không thể xóa hết audit records cùng một thời hạn 30 ngày?**  
Các loại audit có mục đích, căn cứ và nghĩa vụ khác nhau. 30 ngày trong demo chỉ là số giả lập.

**6. Khi transaction rollback, làm sao vẫn lưu được nỗ lực truy cập bị từ chối?**  
Dùng cơ chế audit độc lập với transaction nghiệp vụ, được phê duyệt và có chính sách lỗi/retention tương ứng.

**7. Append-only có mâu thuẫn với retention deletion không?**  
Không. Append-only bảo vệ records khỏi sửa/xóa tùy tiện trong thời gian phải lưu; disposition hợp lệ cần đường xóa/ẩn danh có kiểm soát và bằng chứng tối thiểu.

**8. Ghi hash của các audit rows đã đủ chống xóa/sửa mọi record chưa?**  
Chưa. Cần bảo vệ key/anchor và xử lý chuỗi/batch, concurrency, retention có căn cứ; hash có thể bị tính lại nếu attacker kiểm soát mọi dữ liệu.

**9. Nếu outbox gửi cùng event hai lần do retry thì audit sink nên làm gì?**  
Dùng stable event ID và unique key/idempotency để tránh tạo hai logical audit records.

**10. Khi retention job đã xóa primary DB, điều gì vẫn phải kiểm tra?**  
Backup, replica, archive, search index, cached exports và yêu cầu xử lý dữ liệu cá nhân theo policy.

## 17. Tài liệu chính thức và tài liệu bảo mật

- [Spring Framework 6.2 — Application Events và annotation-based listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2.9 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/data-commons/auditing.html)
- [OWASP Cheat Sheet — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [European Commission — Principles of the GDPR, Data minimisation & storage limitation](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en)
- [European Commission — Dealing with requests from individuals](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/dealing-requests-individuals_en)
- [Java SE 17 — java.time.Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)

