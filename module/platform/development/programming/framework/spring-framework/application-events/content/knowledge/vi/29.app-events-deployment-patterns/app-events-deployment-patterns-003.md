# Ghi audit sau thao tác nghiệp vụ trong Spring Application Events

Audit trail là bằng chứng về **ai thực hiện hành động gì, lên đối tượng nào, khi nào, với kết quả nào**. Trong ứng dụng Spring, một thao tác nghiệp vụ thường nằm trong transaction; service có thể phát event để audit listener ghi nhận hành động. Nhưng thời điểm phát event **không đồng nghĩa với thời điểm transaction commit**. Nếu ghi audit quá sớm, có thể lưu bản ghi cho thao tác cuối cùng rollback; nếu chỉ ghi sau commit bằng callback trong bộ nhớ, lại có thể mất audit khi process crash trước khi callback kịp chạy.

Bài này trình bày hai chiến lược khác nhau: **audit bắt buộc phải được ghi cùng transaction nghiệp vụ** và **audit ghi sau commit** bằng `@TransactionalEventListener(phase = AFTER_COMMIT)`. Với phương án sau, cần hiểu khi nào phải mở transaction mới, cách kiểm thử commit/rollback/lỗi ghi audit và lúc nào phải dùng transactional outbox hoặc Spring Modulith Event Publication Registry để có khả năng retry/khôi phục.

## 1. Định nghĩa yêu cầu trước khi chọn listener

Có ít nhất ba mức độ audit:

| Loại | Ví dụ | Mức bảo đảm |
| --- | --- | --- |
| **Audit bắt buộc/tuân thủ** | Ai phê duyệt giao dịch, ai thay đổi vai trò truy cập | Không được commit nghiệp vụ nếu audit tương ứng không được commit |
| **Audit sau commit** | Lịch sử phụ trợ cho một thay đổi đã hoàn tất | Chỉ ghi nếu nghiệp vụ commit; nếu callback lỗi phải biết rõ khả năng mất dữ liệu |
| **Audit gửi ra hệ thống khác** | Chuyển lịch sử thay đổi vào kho compliance hoặc analytics | Cần lưu ý định gửi bền vững, retry và idempotency |
| **Log vận hành** | `INFO event received` hoặc stack trace | Không phải bằng chứng audit bền vững |

Câu hỏi thiết kế then chốt: **Nếu audit sink đang lỗi, nghiệp vụ chính có được phép hoàn thành không?**

Nếu câu trả lời là **không**, nên ghi audit và thay đổi nghiệp vụ vào **cùng một transaction** trên cùng transactional resource, hoặc ít nhất ghi *ý định audit* bền vững cùng nghiệp vụ rồi giao tiếp an toàn với sink sau đó. Nếu câu trả lời là **có**, `AFTER_COMMIT` có thể phù hợp với tác vụ phụ, nhưng phải chấp nhận hoặc xử lý riêng cửa sổ mất event.

Ngoài ra cần định nghĩa `outcome`: ghi “user yêu cầu phê duyệt” khác “đơn hàng đã được commit ở trạng thái APPROVED”. Audit dựa trên after-commit thường thể hiện **thao tác đã commit**, không dùng làm nhật ký tổng hợp cho mọi lần thử hoặc thao tác bị từ chối.

## 2. Vì sao @EventListener thường chưa đủ để ghi audit sau commit?

Một event đơn giản:

~~~java
public record OrderApproved(
    String eventId,
    String orderId,
    String actorId,
    java.time.Instant occurredAt
) { }
~~~

Trong service đang có transaction:

~~~java
@Transactional
public void approve(String orderId) {
    orderRepository.setApproved(orderId);
    publisher.publishEvent(new OrderApproved(
        newEventId(), orderId, verifiedActorId(), Instant.now()
    ));
}
~~~

Hai đoạn trên là **trích đoạn**: cần các repository/helper, `@Transactional` và `ApplicationEventPublisher` thích hợp.

Theo mặc định, `ApplicationEventPublisher` dùng cơ chế dispatch đồng bộ qua `SimpleApplicationEventMulticaster`. Nếu listener gắn `@EventListener` thông thường ghi audit vào hệ thống bên ngoài ngay lúc nhận event, nó có thể được gọi **trước khi transaction nghiệp vụ commit**:

~~~text
BEGIN business TX
  UPDATE order -> APPROVED
  publishEvent(OrderApproved)
        |
        +-- @EventListener gửi audit ra service ngoài
        |      -> "order approved" đã lưu bên ngoài
  một bước nghiệp vụ tiếp theo ném exception
ROLLBACK business TX

Kết quả: audit bên ngoài nói thành công,
nhưng trạng thái order lại không được commit.
~~~

Nếu listener đồng bộ ghi audit **trong cùng database transaction** (không tách transaction), hai thay đổi có thể rollback cùng nhau. Đó là một thiết kế hợp lệ cho audit bắt buộc; rủi ro ở ví dụ trên là side effect độc lập hoặc ghi vào tài nguyên **ngoài** transaction nguồn.

Không đặt niềm tin vào `@Order` để giải quyết việc này. Annotation đó chỉ ảnh hưởng thứ tự gọi listeners, **không đổi transaction boundary**.

## 3. AFTER_COMMIT: chỉ phản ứng với business transaction thành công

Dùng `@TransactionalEventListener` với pha rõ ràng:

~~~java
@Component
class AuditEventListener {

    private final AuditWriter auditWriter;

    AuditEventListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderApproved(OrderApproved event) {
        auditWriter.record(event);
    }
}
~~~

Đây là **trích đoạn** trong ứng dụng Spring. Annotation cần import `org.springframework.transaction.event.TransactionalEventListener` và `TransactionPhase`; `AuditWriter` và `OrderApproved` do ứng dụng định nghĩa.

Luồng thời gian:

~~~text
Service thread
    |
    +-- BEGIN TX
    |     UPDATE orders
    |     publish OrderApproved
    |         +-- listener đăng ký callback AFTER_COMMIT
    |
    +-- COMMIT thành công
    |      |
    |      +-- gọi callback audit
    |             +-- INSERT audit trong transaction RIÊNG
    |
    +-- service kết thúc

Nếu ROLLBACK: callback AFTER_COMMIT không xử lý event.
~~~

`TransactionPhase` có `BEFORE_COMMIT`, `AFTER_COMMIT` (mặc định), `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Chọn rõ `AFTER_COMMIT` sẽ làm mục đích code dễ đọc hơn.

**Không có active transaction:** `@TransactionalEventListener` mặc định **không chạy** vì không thể xác định phase commit. Nếu cấu hình `fallbackExecution=true`, nó có thể chạy khi không có transaction, nhưng đó là một thay đổi semantic cần được thiết kế và kiểm thử; không bật chỉ để làm test pass.

**Không được đảo ngược commit:** lỗi xảy ra trong callback sau commit **không thể rollback lại** business transaction đã commit. Đường lan truyền exception tới caller tùy vị trí callback và cơ chế dispatch; không dùng exception propagation thay thế cơ chế retry/recovery.

**Không có durable delivery mặc định:** callback được đăng ký qua transaction synchronization trong process. Nếu ứng dụng chết ngay sau commit trước khi callback hoàn tất, Spring Framework thuần **không tự lưu một publication queue** để gửi lại.

## 4. Ghi audit DB sau commit phải dùng transaction mới

Một chi tiết quan trọng trong tài liệu Spring: sau khi transaction đã commit, những transactional resources cũ có thể vẫn đang bound tới thread trong thời gian callback. Một câu lệnh DB của listener có thể tiếp tục nhìn thấy resource cũ nhưng **không còn commit tiếp theo** cho phần thay đổi mới.

Vì vậy, khi audit callback cần ghi DB, sử dụng `PROPAGATION_REQUIRES_NEW`:

~~~java
@Configuration
class AuditTransactionConfig {

    @Bean("auditTx")
    TransactionTemplate auditTx(
            DataSourceTransactionManager manager) {
        TransactionTemplate template =
            new TransactionTemplate(manager);
        template.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
        return template;
    }
}
~~~

Đây là **trích đoạn**, cần imports cho Spring configuration, `TransactionTemplate`, `TransactionDefinition` và transaction manager. `REQUIRES_NEW` khởi tạo transaction vật lý mới phù hợp cho audit write, với lifecycle commit riêng.

Tương đương, đặt method ghi audit trên một bean được gọi **qua Spring transactional proxy**:

~~~java
@Service
class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(OrderApproved event) {
        // auditRepository.insert(...);
    }
}
~~~

Hai đoạn là **các phương án thay thế**. Với `@Transactional`, nếu cùng bean tự gọi `this.record(...)` trong proxy mode thông thường, transactional advice có thể bị bỏ qua. `TransactionTemplate` thường giúp ví dụ/test rõ transaction boundary hơn.

Phân biệt:
- `@TransactionalEventListener` quyết định **khi nào listener được gọi**.
- `@Transactional`/`TransactionTemplate` quyết định **transaction nào bao quanh việc ghi audit**.
- `@Async` chỉ quyết định **executor/thread chạy công việc**; không tự tạo transaction, durability hoặc context propagation.

## 5. Audit event nên mang trường nào?

Một hợp đồng tối thiểu:

~~~java
public record AuditFact(
    String eventId,
    String aggregateType,
    String aggregateId,
    String actionCode,
    String actorId,
    String correlationId,
    java.time.Instant occurredAt
) { }
~~~

Đây là record minh họa. Khi hệ thống có nhiều loại action, nên phân biệt event nghiệp vụ `OrderApproved` với một `AuditFact` có schema chung. Không nên phát một event `AuditFact` chung quá sớm nếu làm mất ngữ nghĩa domain.

| Trường | Mục đích | Lưu ý |
| --- | --- | --- |
| `eventId` | Định danh **một logical event** | Giữ ổn định qua retry/delivery lại |
| `aggregateId` và `aggregateType` | Đối tượng tác động | Có thể nhạy cảm, áp dụng hashing/retention |
| `actionCode` | Mã hành động ổn định | Ví dụ `order.approved`, không phải message text tự do |
| `actorId` | Tài khoản/identity thực hiện | Phải lấy từ nguồn đã xác thực/authorize |
| `correlationId` | Liên kết request/workflow | Không thay thế eventId |
| `occurredAt` | Thời điểm sự kiện nghiệp vụ | Khác thời điểm audit row được ghi |
| `outcome` | `COMMITTED`, `REJECTED`, ... | Không tự kết luận external delivery đã thành công |
| `schemaVersion` | Phiên bản schema event | Dùng khi payload thay đổi lâu dài |

Tránh truyền nguyên `Authentication`, access token, `HttpServletRequest`, managed JPA entity hay list chứa dữ liệu cá nhân vào event. Listener async/after-commit có thể chạy ngoài phạm vi request/session ban đầu; DTO chỉ mang dữ liệu đã chọn sẽ an toàn và dễ kiểm thử hơn.

### actorId đáng tin được lấy tại business boundary

~~~java
Authentication auth = SecurityContextHolder.getContext()
    .getAuthentication();
if (auth == null || !auth.isAuthenticated()) {
    throw new AccessDeniedException("Authentication required");
}
String actorId = auth.getName();
~~~

Đây là trích đoạn, cần policy xử lý anonymous authentication: `AnonymousAuthenticationToken` cũng có thể được đánh dấu authenticated. Ứng dụng phải authorize action bằng policy của mình trước khi gán actor vào event. Không dùng `actorId` do client gửi như bằng chứng đã xác thực.

## 6. Ví dụ tích hợp hoàn chỉnh Java 17+: AFTER_COMMIT audit + H2

Ví dụ sau là integration test Java 17+ dùng Spring Framework 6.2, Spring JDBC, H2 và JUnit 5, **không cần Spring Boot**. Service ghi một `order_record` trong transaction; sau commit, listener ghi `audit_entry` qua một `TransactionTemplate(REQUIRES_NEW)`. Test minh họa cả happy path và failure window.

### 6.1. Cấu hình Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-audit-event-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
}
repositories {
    mavenCentral()
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-jdbc'
    testImplementation 'org.springframework:spring-tx'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
    testRuntimeOnly 'com.h2database:h2:2.3.232'
}
tasks.named('test') {
    useJUnitPlatform()
}
~~~

Với Spring Boot, ưu tiên dependency versions đồng bộ do Boot quản lý. H2 là in-memory database để kiểm thử: không dùng kết quả test này làm bằng chứng về durability qua JVM crash.

### 6.2. src/test/java/example/audit/AfterCommitAuditTest.java

~~~java
package example.audit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@SpringJUnitConfig(AfterCommitAuditTest.Config.class)
class AfterCommitAuditTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired ApprovalService service;
    @Autowired ApplicationEventPublisher publisher;
    @Autowired AuditListener listener;

    @BeforeEach
    void reset() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS order_record (" +
            "id VARCHAR(50) PRIMARY KEY, state VARCHAR(20) NOT NULL)"
        );
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS audit_entry (" +
            "event_id VARCHAR(50) PRIMARY KEY, " +
            "order_id VARCHAR(50) NOT NULL, " +
            "actor_id VARCHAR(50) NOT NULL, " +
            "action_code VARCHAR(50) NOT NULL, " +
            "occurred_at TIMESTAMP NOT NULL)"
        );
        jdbc.update("DELETE FROM audit_entry");
        jdbc.update("DELETE FROM order_record");
        listener.reset();
    }

    @Test
    void committedOrderGetsAuditRow() {
        service.approve("ORD-1", "evt-1", "alice", false);
        assertEquals(1, orders("ORD-1"));
        assertEquals(1, audits("evt-1"));
        assertEquals("alice", jdbc.queryForObject(
            "SELECT actor_id FROM audit_entry WHERE event_id=?",
            String.class, "evt-1"
        ));
        assertEquals("order.approved", jdbc.queryForObject(
            "SELECT action_code FROM audit_entry WHERE event_id=?",
            String.class, "evt-1"
        ));
    }

    @Test
    void sourceRollbackSkipsAfterCommitAudit() {
        assertThrows(IllegalStateException.class, () ->
            service.approve("ORD-2", "evt-2", "bob", true));
        assertEquals(0, orders("ORD-2"));
        assertEquals(0, audits("evt-2"));
    }

    @Test
    void publicationWithoutTransactionDoesNotInvokeListener() {
        publisher.publishEvent(new OrderApproved(
            "evt-3", "ORD-3", "carol", Instant.now()
        ));
        assertEquals(0, audits("evt-3"));
    }

    @Test
    void auditFailureCannotUndoCommittedOrder() {
        listener.failNextWrite();
        service.approve("ORD-4", "evt-4", "dave", false);
        assertEquals(1, orders("ORD-4"));
        assertEquals(0, audits("evt-4"));
        assertEquals(List.of("evt-4"), listener.failedIds());
    }

    private int orders(String orderId) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM order_record WHERE id=?",
            Integer.class, orderId);
    }

    private int audits(String eventId) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_entry WHERE event_id=?",
            Integer.class, eventId);
    }

    record OrderApproved(
        String eventId, String orderId,
        String actorId, Instant occurredAt) { }

    static class ApprovalService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate businessTx;
        private final ApplicationEventPublisher publisher;

        ApprovalService(JdbcTemplate jdbc,
                TransactionTemplate businessTx,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.businessTx = businessTx;
            this.publisher = publisher;
        }

        void approve(String orderId, String eventId,
                String actorId, boolean forceRollback) {
            businessTx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO order_record(id,state) VALUES (?,?)",
                    orderId, "APPROVED");
                publisher.publishEvent(new OrderApproved(
                    eventId, orderId, actorId, Instant.now()));
                if (forceRollback) {
                    throw new IllegalStateException("forced rollback");
                }
            });
        }
    }

    static class AuditListener {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate auditTx;
        private final AtomicBoolean failNext = new AtomicBoolean();
        private final ConcurrentLinkedQueue<String> failed =
            new ConcurrentLinkedQueue<>();

        AuditListener(JdbcTemplate jdbc, TransactionTemplate auditTx) {
            this.jdbc = jdbc;
            this.auditTx = auditTx;
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
        public void onApproved(OrderApproved event) {
            try {
                auditTx.executeWithoutResult(status -> {
                    if (failNext.getAndSet(false)) {
                        throw new IllegalStateException(
                            "audit store unavailable");
                    }
                    jdbc.update(
                        "INSERT INTO audit_entry(" +
                        "event_id,order_id,actor_id," +
                        "action_code,occurred_at) " +
                        "VALUES (?,?,?,?,?)",
                        event.eventId(), event.orderId(),
                        event.actorId(), "order.approved",
                        Timestamp.from(event.occurredAt())
                    );
                });
            } catch (RuntimeException ex) {
                // Test probe minh họa failure: KHÔNG bền vững!
                failed.add(event.eventId());
            }
        }

        void failNextWrite() {
            failNext.set(true);
        }

        List<String> failedIds() {
            return List.copyOf(failed);
        }

        void reset() {
            failNext.set(false);
            failed.clear();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                "jdbc:h2:mem:audit_demo;DB_CLOSE_DELAY=-1",
                "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        DataSourceTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean("businessTx")
        TransactionTemplate businessTx(
                DataSourceTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean("auditTx")
        TransactionTemplate auditTx(
                DataSourceTransactionManager manager) {
            TransactionTemplate template =
                new TransactionTemplate(manager);
            template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            return template;
        }

        @Bean
        ApprovalService service(
                JdbcTemplate jdbc,
                @Qualifier("businessTx") TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            return new ApprovalService(jdbc, tx, publisher);
        }

        @Bean
        AuditListener listener(
                JdbcTemplate jdbc,
                @Qualifier("auditTx") TransactionTemplate tx) {
            return new AuditListener(jdbc, tx);
        }
    }
}
~~~

### 6.3. Chạy và đọc kết quả

Trong project có Gradle wrapper:

~~~bash
./gradlew test --tests "example.audit.AfterCommitAuditTest"
~~~

Trên Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.audit.AfterCommitAuditTest"
~~~

Không có stdout nghiệp vụ cố định: test sử dụng JUnit assertions trực tiếp trên database. Kết quả mong đợi:

| Test | Đơn hàng | Audit | Kết luận |
| --- | --- | --- | --- |
| `committedOrderGetsAuditRow` | ORD-1 có | evt-1 có | Audit ghi sau commit bằng transaction mới |
| `sourceRollbackSkipsAfterCommitAudit` | ORD-2 không có | evt-2 không có | Rollback không kích hoạt callback AFTER_COMMIT |
| `publicationWithoutTransactionDoesNotInvokeListener` | Không đổi | evt-3 không có | Không active transaction, mặc định không chạy |
| `auditFailureCannotUndoCommittedOrder` | ORD-4 có | evt-4 không có | Audit lỗi sau commit không rollback nghiệp vụ |

Đây là **ví dụ listener đồng bộ trong callback after-commit**, không bật `@Async`. Callback và audit transaction mới hoàn tất khi `businessTx.executeWithoutResult` trả về, nên assertions có thể chạy ngay. Nếu bật `@Async` hoặc đưa audit vào broker, cần chờ kết quả quan sát được với timeout (`Awaitility`, `CountDownLatch` hay future do ứng dụng cung cấp), không dùng `Thread.sleep`.

Test cuối **cố tình minh họa audit thất bại có thể bị mất**: `ConcurrentLinkedQueue` của listener chỉ là probe trong bộ nhớ, không phải durable failure journal. **Không sao chép phần catch-nuốt-lỗi này vào production** khi audit có ý nghĩa bắt buộc.

## 7. Vì sao AFTER_COMMIT không bảo đảm audit không mất?

Xét ba cửa sổ lỗi:

~~~text
(A) Business transaction đang mở
    -> lỗi -> rollback
    -> AFTER_COMMIT không chạy
    -> không nên có audit "approved committed"

(B) DB đã commit, JVM chết trước callback
    -> business record tồn tại
    -> không có audit
    -> Spring ApplicationEventPublisher không có durable backlog

(C) Callback đã gửi audit ra hệ thống ngoài
    -> process chết trước lúc ghi nhận đã hoàn tất
    -> retry có thể gửi audit lặp
~~~

`@TransactionalEventListener` xử lý đúng việc chỉ chạy sau commit, nhưng không tự lưu event/attempts để recovery. Tương tự, `@Async` chỉ chuyển thread/executor; nó **không** tự động lưu task bền vững, không tự có retry và có thể gặp executor rejection.

### Mẫu transactional outbox

Một mô hình mạnh hơn:

~~~text
BEGIN business transaction
  UPDATE order
  INSERT audit_outbox(
      event_id, action_code, aggregate_id,
      actor_id, payload_ref, status=PENDING)
COMMIT

Background worker:
  claim PENDING bằng cập nhật nguyên tử/lease
  -> gửi hoặc ghi audit với idempotency key
  -> mark SENT nếu sink xác nhận
  -> lỗi: FAILED, retry với backoff
  -> quá số lần: DEAD, alert/reconciliation
~~~

**Điểm quyết định:** thay đổi nghiệp vụ và outbox row được ghi **trong cùng transaction**. Nếu rollback cả hai biến mất; nếu commit thì ý định audit còn trong DB, worker có thể khôi phục sau process crash. Callback `AFTER_COMMIT` có thể được dùng làm “nudge” đánh thức worker để giảm latency, nhưng worker **vẫn phải tự quét outbox** vì nudge có thể bị mất.

Trích đoạn cho `@Transactional` service:

~~~java
@Transactional
public void approve(String orderId) {
    String actor = currentVerifiedActorId();
    orderRepository.approve(orderId);
    auditOutboxRepository.insert(
        nextEventId(), "order.approved", orderId, actor);
}
~~~

Đây là trích đoạn, không phải class độc lập; repository và helpers do ứng dụng định nghĩa. Để có atomic commit, hai repository phải tham gia **cùng transaction manager/resource**, không gửi HTTP hoặc ghi một DB không tham gia transaction rồi giả định atomic.

### Idempotency của audit sink

Outbox thường cho **at-least-once delivery**. Có thể xảy ra: sink nhận audit thành công, process chết trước khi mark `SENT`; worker retry. Dùng `event_id` ổn định và unique key theo logical audit action (hoặc `(event_id, handler_id)` trong nhiều sinks). Một `SELECT EXISTS` rồi `INSERT` riêng lẻ chưa đủ tránh race giữa hai workers; dùng unique constraint/atomic upsert thích hợp và phân loại lỗi duplicate chính xác.

**Không thể tuyên bố exactly-once end-to-end** chỉ vì Spring callback chạy một lần. External APIs, transaction DB và broker acknowledgements có các failure windows khác nhau; cần hợp đồng idempotency và reconciliation ở đích.

## 8. Spring Modulith Event Publication Registry

Nếu ứng dụng dùng Spring Modulith, **Event Publication Registry** có thể lưu những publication dành cho transactional listeners trong transaction nghiệp vụ, theo dõi completion và cung cấp cơ chế resubmission khi publication chưa hoàn tất. Tài liệu chính thức: <https://docs.spring.io/spring-modulith/reference/events.html>.

Trích đoạn module listener:

~~~java
@Component
class AuditModuleListener {

    @ApplicationModuleListener
    void on(OrderApproved event) {
        auditRepository.insertIfAbsent(event);
    }
}
~~~

Đoạn này chỉ minh họa ý tưởng Spring Modulith, cần đúng imports, dependency starter và bean `auditRepository`; nó **không thuộc project H2 test phía trên**. `@ApplicationModuleListener` có ngữ nghĩa transactional/async phù hợp module-event handling theo phiên bản. Dù registry lưu publication, ứng dụng vẫn cần audit schema, chính sách bảo mật, idempotent sink, retention và monitoring.

Với Spring Modulith 2.x, publication lifecycle có các trạng thái như `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED`, `RESUBMITTED`; API và properties cần đối chiếu **đúng version** của project. Đừng mặc định lấy ví dụ 2.x áp vào ứng dụng Modulith 1.x, và đừng coi registry record là bản thân **audit trail** đầy đủ.

Nếu không dùng Modulith, có thể triển khai outbox hoặc message broker với consumer tracking riêng. Với audit xuyên nhiều services, cần xem xét retention của audit sink, schema evolution, consumer idempotency, replay quyền hạn và chiến lược bảo vệ dữ liệu.

## 9. Ghi đúng loại audit cho hành động bị từ chối

Một `AFTER_COMMIT` listener có chủ đích **không chạy khi transaction rollback**. Vậy audit “login failed”, “access denied” hoặc “approve attempted but rejected” phải được ghi ở nơi khác.

Có thể chia rõ:

- **Audit hành động đã commit:** `OrderApproved` phát trong transaction, listener `AFTER_COMMIT` hoặc outbox.
- **Audit lần thử bị từ chối:** event/log ghi lại kết quả `REJECTED` từ policy/validation path, với transaction và reliability riêng.
- **Audit sự kiện hệ thống:** background task không có người dùng trực tiếp, ghi `actorType=SYSTEM`, `serviceId` và `correlationId` có ý nghĩa.

Không dùng `fallbackExecution=true` chỉ để “bắt tất cả trường hợp”: nó thay đổi contract giao dịch, không tự giải quyết failed attempts hoặc durable delivery.

Cần tách thời điểm `occurredAt` trong event (khi hành động xảy ra) với `recordedAt` trong audit table (khi lưu audit). Hai timestamps có thể lệch do queue delay/retry, nên không lấy chênh lệch đó làm bằng chứng gian lận khi chưa kiểm tra nguồn clock và latency.

## 10. Bảo mật, privacy và tính toàn vẹn của audit

Audit dễ chứa dữ liệu nhạy cảm. Một event có `actorId`, `aggregateId` hay old/new values vẫn có thể là PII trong một số bối cảnh.

Nguyên tắc áp dụng:

1. **Allowlist fields** thay vì serialize nguyên entity/HTTP payload.
2. **Không lưu credentials:** password, access/refresh token, API key, session cookie hoặc authorization header.
3. **Danh tính đã kiểm chứng:** lấy actor từ authentication/authorization context ở business boundary; async listener không tự có SecurityContext của caller.
4. **Đồng bộ timezone:** lưu `Instant`/UTC hoặc timestamp có timezone policy rõ; phân biệt event time và recorded time.
5. **Phân quyền đọc/ghi:** audit ledger có quyền truy cập riêng, giới hạn chỉnh sửa/xóa, encryption và retention phù hợp.
6. **Tamper evidence nếu bắt buộc:** append-only controls, hashing/signature/immutable storage và kiểm tra integrity; một bảng SQL bình thường không tự chống sửa tuyệt đối.
7. **Dữ liệu trước/sau:** chỉ ghi field cần thiết, đánh giá retention và quyền được quên/xóa theo quy định hiện hành.

Khi actor có thể là anonymous/system, schema audit nên chứa loại actor hoặc ID hệ thống, thay vì giả tạo “user” mặc định. Không log toàn bộ `Authentication` object, vì có thể chứa thông tin nhạy cảm.

## 11. Monitoring và reconciliation

Không chỉ kiểm tra listener log `"audit requested"`. Cần quan sát audit **đã lưu thành công** và các công việc tồn đọng:

| Chỉ số | Công dụng |
| --- | --- |
| Audit write failures theo action/handler | Biết sink/DB có lỗi |
| Oldest PENDING age / outbox lag | Phát hiện event chưa được giao |
| Retry attempts và dead-letter backlog | Phát hiện tiến trình kẹt hoặc lỗi kéo dài |
| Audit persisted latency | Thời gian từ commit đến audit row/sink ack |
| Missing audit reconciliation count | Phát hiện thay đổi nghiệp vụ không có audit tương ứng |
| Duplicate audit events deduped | Theo dõi idempotency và retry |
| Audit storage growth và retention | Tránh đầy disk/index và vi phạm policy |

Một structured log hữu ích có `event_id`, `action_code`, `actor_id` ở mức được phép, `aggregate_id`, `correlation_id`, `handler`, `processing_phase`, `attempt`, `error_code` đã sanitize. Không đưa `eventId` làm label metric vì cardinality quá cao.

Nếu audit là compliance-critical, reconciliation nên đối chiếu nguồn dữ liệu nghiệp vụ và audit ledger. Ví dụ mọi `order_record.state=APPROVED` trong phạm vi phiên bản/audit policy đều có audit event tương ứng, ngoại trừ các trạng thái được giải thích bằng nghiệp vụ; không chỉ kiểm tra số lượng tổng.

## 12. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `@EventListener` sync ghi HTTP audit trước commit | Audit “thành công” cho transaction đã rollback | Dùng AFTER_COMMIT hoặc ghi cùng TX theo policy |
| AFTER_COMMIT ghi DB mà không có transaction mới | Thay đổi có thể tham gia resource transaction cũ nhưng không commit | Dùng `REQUIRES_NEW` |
| Cho rằng AFTER_COMMIT = durable queue | Crash giữa commit và callback mất audit | Ghi outbox/registry transactionally |
| Gắn `@Async` để “bền vững hơn” | Task chỉ nằm trong in-memory executor | Dùng durable work + retry |
| Catch lỗi audit rồi chỉ log | Không có audit row và không có đường phục hồi | Durable failure tracking, retry/alert |
| Dùng actorId từ request body không xác minh | Audit ghi danh tính giả | Capture trusted actor tại service |
| Event chứa JPA entity/HTTP request | Lazy-loading, mutable state, leaked context | Event DTO nhỏ, immutable fields |
| Không có eventId/unique key | Retry gây duplicate audit | Idempotency theo logical event |
| Test `@Transactional` mặc định rollback nhưng mong AFTER_COMMIT | Listener không chạy trong test | Test commit chủ động bằng TransactionTemplate/TestTransaction |
| Coi audit log chung với debug logs | Sampling/retention sai hoặc thiếu quyền truy cập | Audit ledger riêng theo yêu cầu |
| Ghi `SUCCESS` trước commit | Outcome sai khi transaction rollback | Chỉ ghi committed outcome sau commit/atomic TX |
| Dùng `@Order` để bảo đảm atomic | Chỉ thay đổi invocation ordering | Transaction boundary và persistence đúng |

## 13. Checklist triển khai

- [ ] Đã định nghĩa audit bắt buộc hay best-effort, mức downtime/loss được phép.
- [ ] Nếu audit atomic bắt buộc, cùng transaction giữa business row và audit row/outbox.
- [ ] Event chứa ID ổn định, action, aggregate, actor đã xác thực, occurredAt/correlationId.
- [ ] Dùng `@TransactionalEventListener(AFTER_COMMIT)` chỉ khi cần gắn với commit.
- [ ] Listener ghi DB sau commit có transaction mới (hoặc worker transaction riêng).
- [ ] Đã xét `fallbackExecution=false` khi không có transaction.
- [ ] Có test commit, rollback, outside-transaction, audit failure.
- [ ] Với async: test chờ outcome bằng timeout, không assert ngay sau publish.
- [ ] Khi audit không được mất: outbox/registry, retry/backoff, idempotency, reconciliation.
- [ ] Có xử lý riêng cho failed/denied attempts, không chỉ audit committed success.
- [ ] Không lưu secrets/PII thừa; có retention, access control và integrity requirements.
- [ ] Có monitoring pending age, failure ratio, audit lag và dead-letter.
- [ ] Không cho rằng publishEvent return = commit, delivery hoặc audit success.

## 14. Câu hỏi tự kiểm tra

**Câu 1:** Tại sao `@EventListener` thông thường có thể ghi audit sai?

Vì listener thường chạy ngay khi publish, có thể **trước khi transaction commit**. Nếu nó ghi sang một storage độc lập rồi business transaction rollback, audit có thể phản ánh một thay đổi chưa từng được commit.

**Câu 2:** Tại sao `@TransactionalEventListener(AFTER_COMMIT)` không ghi audit khi source rollback?

Vì callback chỉ đăng ký và thực thi theo pha commit thành công; rollback không kích hoạt `AFTER_COMMIT`.

**Câu 3:** Vì sao nên dùng `REQUIRES_NEW` để ghi audit DB trong callback after-commit?

Transaction đã hoàn tất nhưng resource cũ có thể vẫn bound; không có commit tiếp theo. Transaction mới cho audit một đơn vị ghi/commit độc lập.

**Câu 4:** Lỗi audit sau commit có thể rollback business transaction vừa commit không?

Không. Audit là một công việc tiếp theo và có thể thất bại; muốn không mất phải dùng transactionally recorded intent/outbox hoặc phương án ghi audit cùng transaction nguồn.

**Câu 5:** Outbox có bảo đảm audit sink xử lý exactly once không?

Không tự động. Worker có thể gửi xong nhưng crash trước mark `SENT`. Cần idempotency key ở sink hoặc reconciliation và hợp đồng retry rõ.

**Câu 6:** Spring Modulith Registry có tự là audit ledger nghiệp vụ không?

Không. Nó theo dõi publication/completion để hỗ trợ delivery/recovery; ứng dụng vẫn quyết định audit schema, nội dung, quyền và retention.

**Câu 7:** Muốn ghi audit lần truy cập bị từ chối thì `AFTER_COMMIT` là đủ chưa?

Chưa. Lần từ chối có thể không có transaction hoặc rollback; cần một đường ghi nhận failed attempts riêng, phù hợp với security policy và durability requirements.

**Ghi nhớ:** `AFTER_COMMIT` giúp audit **chỉ phản ứng khi business transaction đã commit**; `REQUIRES_NEW` giúp audit database write được commit riêng. Hai thứ này **không tự tạo durable recovery**. Audit bắt buộc phải được ghi atomic với nghiệp vụ hoặc có durable intent (outbox/registry), idempotency, retry và đối soát.

## Tài liệu tham khảo

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — TransactionSynchronization.afterCompletion](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — TransactionTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Modulith — Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
