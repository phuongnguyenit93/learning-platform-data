# Theo dõi trạng thái xử lý event trong Spring Framework Application Events

Một lời gọi `ApplicationEventPublisher.publishEvent(event)` **không phải bằng chứng rằng mọi listener đã xử lý thành công event**. Listener có thể chỉ được lên lịch qua executor, chạy sau khi transaction commit, ném exception, bị process crash hoặc phải retry. Trong các luồng nghiệp vụ quan trọng, ta cần biết event đang ở bước nào, handler nào đã hoàn thành, handler nào thất bại, công việc có bị kẹt hay không và có thể xử lý lại an toàn hay không.

**Theo dõi trạng thái xử lý event** là thiết kế một lifecycle có định danh, bản ghi trạng thái, quy tắc chuyển trạng thái, lịch sử attempt và cơ chế khôi phục. Điều này khác với chỉ ghi log `"event received"` hoặc đếm số lần `publishEvent` được gọi. Đặc biệt, cùng một event có thể được gửi đến **nhiều listener**, nên trạng thái của event và trạng thái **từng đích xử lý** cần được phân biệt.

Bài học này tập trung vào độ tin cậy của Spring Application Events: mô hình `PENDING → PROCESSING → SUCCEEDED/FAILED → DEAD`, transaction boundary, atomic claim, retry, lease, idempotency, observability và Spring Modulith Event Publication Registry. Cuối bài có một integration test Java 17+ dùng Spring Framework, JDBC, H2 và JUnit 5 để minh họa luồng **đăng ký publication trong transaction nghiệp vụ → xử lý AFTER_COMMIT → cập nhật trạng thái bằng transaction riêng → retry**.

## 1. Đâu là trạng thái cần theo dõi?

Một event có thể mang ID `evt-103`, kiểu `order.paid`. Giả sử ba handler độc lập quan tâm đến event này:

~~~text
                       OrderPaid(evt-103)
                              |
               +--------------+---------------+
               |              |               |
           invoice         email           analytics
           SUCCEEDED       FAILED          PROCESSING
~~~

Nói `evt-103 = DONE` là mơ hồ. Invoice đã hoàn tất nhưng email chưa gửi; analytics còn chạy. Một thiết kế thực dụng là ghi trạng thái theo **(event_id, handler_id)** hoặc theo một `publication_id` duy nhất đại diện cho cặp đó.

| Đối tượng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Event** | Một sự kiện logic đã được tạo | `event_id=evt-103`, `event_type=order.paid` |
| **Publication / delivery target** | Việc giao event cho một handler cụ thể | `(evt-103, email)` |
| **Attempt** | Một lần thử chạy handler của publication | Attempt 1 lỗi, attempt 2 thành công |
| **Outcome** | Kết quả của một attempt hoặc trạng thái cuối | `FAILED`, `SUCCEEDED`, `DEAD` |
| **Checkpoint/lease** | Thông tin điều phối worker khi xử lý có thể dài | `claimed_by`, `lease_until`, `version` |

Định danh handler cần ổn định qua các lần deploy nếu muốn khôi phục các publication cũ. Không sử dụng tên bean tự sinh hoặc tên class có thể đổi tùy refactor mà không có kế hoạch migration. Khi một handler đã thành công, các lần phát lại cùng logical event **không nên tạo side effect lần nữa**.

### Published, dispatched, processed và committed không đồng nghĩa

- `PUBLISHED`: code yêu cầu phát hoặc publication đã được ghi lại, tùy định nghĩa của hệ thống.
- `DISPATCHED`: một tác vụ đã được giao cho executor/broker; chưa chắc handler bắt đầu.
- `PROCESSING`: handler/worker đã claim và bắt đầu một attempt.
- `SUCCEEDED`: công việc được handler xác nhận thành công theo contract của nó.
- `COMMITTED`: một transaction database cụ thể đã commit; không tự đồng nghĩa mọi handler hoàn tất.
- `ACKNOWLEDGED`: một đích cụ thể đã xác nhận theo API, không mặc nhiên là “người dùng cuối nhận được thông báo”.

Tên trạng thái không mang bảo đảm thần kỳ. **Mỗi transition phải được gắn với một sự kiện thực tế có thể xác minh**.

## 2. Mô hình lifecycle tối thiểu

Một state machine có thể bắt đầu như sau:

~~~text
CREATE event + publication
         |
         v
      PENDING ----------------------+
         |                         |
    claim/lease                     |
         v                         |
     PROCESSING                     |
      /      \                      |
  success    failure/crash           |
    |          |                    |
    v          v                    |
 SUCCEEDED    FAILED --retry------+
               |
        max attempts /
        non-retryable error
               |
               v
              DEAD

PROCESSING quá hạn lease -> đánh dấu stale và claim lại
(chỉ khi đã có cơ chế fencing/khôi phục an toàn)
~~~

Có thể dùng tên `COMPLETED` thay cho `SUCCEEDED`, `DEAD_LETTERED` thay cho `DEAD`; điều cốt lõi là **định nghĩa chuyển trạng thái và hợp đồng retry**.

| State | Ý nghĩa | Có nên chạy tiếp tự động? |
| --- | --- | --- |
| `PENDING` | Đã có publication hợp lệ, chờ handler claim | Có, khi đến hạn |
| `PROCESSING` | Một worker đã claim attempt | Không claim song song nếu lease còn hiệu lực |
| `SUCCEEDED` | Handler hoàn tất theo contract đã định | Không retry side effect |
| `FAILED` | Attempt lỗi; còn đủ điều kiện retry | Có, theo `next_attempt_at`, backoff |
| `DEAD` | Hết số lần thử hoặc lỗi vĩnh viễn | Không tự retry; cần operator/reconciliation |
| `CANCELLED` (tùy chọn) | Có lệnh nghiệp vụ hủy phần việc | Chỉ khi policy cho phép |

**Cần phân biệt lỗi tạm thời và lỗi vĩnh viễn.** Timeout gateway, HTTP 503 có thể retry; payload vi phạm schema hoặc đích đã bị xóa có thể cần trạng thái `DEAD` ngay. Không phải mọi exception đều xứng đáng lặp 100 lần.

## 3. Trường dữ liệu cần có

Một bảng theo dõi publication có thể gồm:

| Field | Vai trò |
| --- | --- |
| `publication_id` | ID duy nhất cho từng publication |
| `event_id` | ID ổn định của logical event qua retry |
| `event_type` | Kiểu event có version/schema rõ ràng |
| `handler_id` | Đích xử lý, ví dụ `send-receipt-email` |
| `status` | Trạng thái hiện tại |
| `attempts` | Số lần đã claim/bắt đầu attempt |
| `created_at` | Thời điểm đăng ký publication |
| `started_at` | Thời điểm attempt gần nhất bắt đầu |
| `completed_at` | Thời điểm xử lý thành công |
| `next_attempt_at` | Thời điểm có thể retry |
| `lease_until` | Hạn giữ claim để phát hiện worker bỏ dở |
| `claimed_by` | Định danh worker hiện giữ claim |
| `version` / `fencing_token` | Ngăn worker cũ ghi đè kết quả worker mới |
| `last_error_code` | Mã lỗi phân loại đã được lọc dữ liệu nhạy cảm |
| `correlation_id` | Nối log và trace liên quan |
| `payload_ref` hoặc payload nhỏ | Cách worker tái dựng công việc để retry |

Một unique constraint theo `(event_id, handler_id)` ngăn tạo nhiều publication cùng đích vì cùng logical event. Tuy nhiên, nếu hệ thống **cố ý xử lý nhiều lần** cùng event vì các bản cấu hình handler khác nhau, phải định nghĩa khóa uniqueness tương ứng; đừng tự tiện bỏ unique constraint.

### SQL schema tham khảo

Đây là **một bản schema gợi ý**, không phải schema tự động của Spring Modulith:

~~~sql
CREATE TABLE event_publication (
  publication_id VARCHAR(64) PRIMARY KEY,
  event_id VARCHAR(64) NOT NULL,
  handler_id VARCHAR(100) NOT NULL,
  event_type VARCHAR(120) NOT NULL,
  status VARCHAR(24) NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at TIMESTAMP NULL,
  completed_at TIMESTAMP NULL,
  next_attempt_at TIMESTAMP NULL,
  lease_until TIMESTAMP NULL,
  claimed_by VARCHAR(100) NULL,
  fencing_token BIGINT NOT NULL DEFAULT 0,
  last_error_code VARCHAR(100) NULL,
  correlation_id VARCHAR(100) NULL,
  UNIQUE (event_id, handler_id),
  CHECK (attempts >= 0)
);
~~~

Schema trên cần migration/index phù hợp với DB thật. Ví dụ, worker cần index theo `(status, next_attempt_at)` hoặc `(status, lease_until)` để lấy các publication chờ xử lý; không chỉ index mỗi `event_id` rồi quét bảng. Tên bảng, độ dài cột, cách dùng timestamp/time zone và lock strategy cần xác nhận theo database.

**Đừng đặt serialized credentials hoặc toàn bộ đối tượng JPA managed vào bảng publication.** Nếu retry cần dữ liệu tại thời điểm tạo event, dùng immutable snapshot nhỏ hoặc một reference bền vững có version/checksum/access control. Nếu worker chỉ reload theo aggregate ID, dữ liệu có thể đã đổi kể từ lần publish đầu.

## 4. Transaction boundary: đăng ký trước, xử lý sau commit

Vấn đề phổ biến nhất: service ghi đơn hàng rồi publish event trong transaction, sau đó listener chạy `@Async` hoặc `AFTER_COMMIT`. Nếu app chết **sau DB commit nhưng trước khi task async được schedule**, chỉ có log in-memory không đủ để biết việc còn thiếu.

~~~text
BEGIN transaction
  UPDATE orders
  INSERT event_publication(event_id, handler_id, PENDING)
COMMIT
  |
  +-- sau commit: thử dispatch handler
         |
         +-- nếu thành công: PROCESSING -> SUCCEEDED
         +-- nếu lỗi: PROCESSING -> FAILED
         +-- nếu crash trước dispatch: publication còn PENDING
~~~

Đó là lý do **transactional registration** quan trọng: hàng publication và thay đổi nghiệp vụ cùng được commit, hoặc cùng rollback. Worker/phần mềm khôi phục có thể quét publication tồn đọng để thực hiện sau. Ngược lại, gọi `publishEvent` **không tự tạo publication record bền vững** trong Spring Framework thuần.

`@TransactionalEventListener(phase = AFTER_COMMIT)` giúp listener bắt đầu theo phase transaction, nhưng **một mình nó không tạo durable queue hay tự retry sau crash**. Nếu callback ném exception, transaction nguồn đã commit không thể đảo ngược. Nếu xử lý tại after-commit cần **ghi một trạng thái DB mới**, hãy mở transaction mới phù hợp (ví dụ `REQUIRES_NEW` hoặc một `TransactionTemplate` tương đương). Resource của transaction cũ có thể vẫn được bind trong callback, nhưng không còn commit tiếp theo.

Trong ứng dụng không có transaction tại thời điểm publish, `@TransactionalEventListener` mặc định **không chạy** trừ khi cấu hình `fallbackExecution=true`. Vì vậy hãy kiểm thử cả event trong và ngoài transaction.

## 5. Chuyển trạng thái an toàn khi có nhiều worker

Một worker không nên đọc `status=PENDING`, rồi cập nhật `PROCESSING` bằng hai thao tác không được bảo vệ, vì hai workers có thể cùng đọc `PENDING` và cùng xử lý.

Mẫu **atomic claim** với điều kiện trạng thái:

~~~sql
UPDATE event_publication
   SET status = 'PROCESSING',
       attempts = attempts + 1,
       started_at = CURRENT_TIMESTAMP,
       claimed_by = :worker_id,
       lease_until = :lease_until,
       fencing_token = fencing_token + 1
 WHERE publication_id = :publication_id
   AND status IN ('PENDING', 'FAILED')
   AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP)
   AND attempts < :max_attempts;
~~~

Worker chỉ xử lý khi câu UPDATE ảnh hưởng **chính xác một hàng**. Một worker khác bị ảnh hưởng 0 hàng phải bỏ qua. Đây là mô hình SQL khái niệm dùng named parameters, không chạy trực tiếp được trên mọi JDBC client nếu chưa bind chúng. Với khối lượng cao, cơ chế claim có thể dùng `SELECT ... FOR UPDATE SKIP LOCKED`, optimistic locking hoặc DB-specific atomic update/returning; phải kiểm thử isolation của DB thật.

### Khi worker crash ở PROCESSING

Một trạng thái `PROCESSING` có thể tồn tại vô hạn nếu process chết mà không chạy `catch/finally`. Hệ thống cần **lease timeout** hoặc stale-publication monitor. Tuy vậy, chỉ chuyển `PROCESSING` quá hạn về `FAILED` chưa đủ: worker cũ có thể chạy chậm và bỗng tiếp tục gửi side effect sau khi worker mới đã claim.

Giải pháp theo độ nghiêm trọng:

1. `lease_until` xác định khi nào được phép xem claim đã quá hạn.
2. `fencing_token` tăng theo mỗi lần claim; mọi lệnh cập nhật kết quả phải kèm token đang giữ.
3. Worker cũ với token lỗi thời không được update trạng thái của owner mới.
4. Với side effect bên ngoài DB, fencing trong DB **không tự cấm** request đã gửi tới hệ thống ngoài; dùng idempotency key ở downstream khi có thể.
5. Nếu xử lý lâu, có heartbeat gia hạn lease; khi không gia hạn được phải ngừng hoặc kết thúc attempt theo policy.

Ví dụ update có điều kiện:

~~~sql
UPDATE event_publication
   SET status = 'SUCCEEDED', completed_at = CURRENT_TIMESTAMP
 WHERE publication_id = :publication_id
   AND status = 'PROCESSING'
   AND claimed_by = :worker_id
   AND fencing_token = :expected_token;
~~~

Nếu affected rows = 0, worker phải ghi nhận stale claim/concurrency conflict, không báo thành công giả. Không dùng `UPDATE ... WHERE event_id=?` mà bỏ handler và token trong hệ thống nhiều consumer.

## 6. Retry, idempotency và delivery semantics

**At-least-once** nghĩa là một handler có thể nhận logical event nhiều lần, đặc biệt khi nó hoàn thành side effect nhưng process chết **trước lúc ghi `SUCCEEDED`**. Do vậy, trạng thái publication không loại bỏ được nhu cầu **idempotency**.

~~~text
Worker claim event X (attempt 1)
  -> gửi email/payment request thành công
  -> process crash trước khi mark SUCCEEDED

Recovery thấy publication chưa hoàn tất
  -> retry event X (attempt 2)
  -> có nguy cơ gửi lặp
~~~

Các chiến lược:

- Cung cấp idempotency key ổn định theo `(event_id, handler_id)` cho gateway/broker hỗ trợ.
- Với side effect trong cùng database, dùng bảng `processed_event` có unique constraint, kiểm tra và cập nhật nghiệp vụ trong cùng transaction.
- Với side effect HTTP/email không hỗ trợ idempotency, phải chấp nhận/reconcile duplicate hoặc xây dựng cơ chế khóa/sổ cái và quy trình xử lý trùng.
- Retry dùng exponential backoff + jitter, `next_attempt_at`, giới hạn `max_attempts`; phân loại lỗi retryable/permanent.
- Sau `DEAD`, có dashboard, cảnh báo, lý do phân loại và quy trình xử lý thủ công/replay được kiểm soát.

Một khóa idempotency **không nên đổi theo attempts** nếu ý định là ngăn xử lý lặp của cùng event. Nhưng key cũng không nên tái sử dụng cho **hai hành động nghiệp vụ khác nhau**. Định nghĩa identity trước khi chọn chính sách.

### Tại sao không thể tuyên bố exactly-once end-to-end?

Transaction DB và một API ngoài process thường không cùng một atomic commit. Không thể chỉ nhờ application event + trạng thái `SUCCEEDED` mà bảo đảm email/charge/HTTP request chỉ xảy ra đúng một lần. Có thể đạt hiệu quả “exactly-once” **cho một loại side effect cụ thể** bằng protocol/idempotent sink phù hợp, nhưng cần xem từng boundary và failure window.

## 7. Integration test Java 17+: Spring event và trạng thái publication trong H2

Ví dụ này minh họa một **registry tự xây tối thiểu** để hiểu nguyên lý; nó **không thay thế Spring Modulith** và chưa có lease/scheduler để recovery tự động. Bảng trạng thái được ghi trong transaction nghiệp vụ, còn listener là `@TransactionalEventListener(AFTER_COMMIT)`. Cập nhật trạng thái của listener dùng `TransactionTemplate` với `PROPAGATION_REQUIRES_NEW` để dữ liệu vẫn commit sau transaction nguồn.

Bộ test kiểm chứng: commit thành công, rollback không tạo publication, failure và retry an toàn trên cùng event ID, và chuyển `DEAD` khi hết số lần thử. Gateway ở đây là fake có thể điều khiển; với gateway thật cần idempotency.

### 7.1. Cấu hình Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'event-state-tracking'
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

Nếu ứng dụng đang dùng Spring Boot, hãy để Boot quản lý các phiên bản tương thích. H2 `jdbc:h2:mem:...` chỉ được dùng cho test; production cần database bền vững, migration và chính sách retention.

### 7.2. File src/test/java/example/events/EventStatusTrackingTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
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

@SpringJUnitConfig(EventStatusTrackingTest.Config.class)
class EventStatusTrackingTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired PublisherService publisherService;
    @Autowired DeliveryHandler handler;
    @Autowired Registry registry;
    @Autowired FakeGateway gateway;

    @BeforeEach
    void reset() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS work_item (" +
            "id VARCHAR(64) PRIMARY KEY)"
        );
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS event_state (" +
            "event_id VARCHAR(64) NOT NULL," +
            "handler VARCHAR(40) NOT NULL," +
            "status VARCHAR(24) NOT NULL," +
            "attempts INT NOT NULL," +
            "last_error VARCHAR(120)," +
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP," +
            "PRIMARY KEY(event_id, handler))"
        );
        jdbc.update("DELETE FROM event_state");
        jdbc.update("DELETE FROM work_item");
        gateway.reset();
    }

    @Test
    void successfulCommitIsTracked() {
        publisherService.create("e-success", false);

        assertEquals("SUCCEEDED", registry.status("e-success"));
        assertEquals(1, registry.attempts("e-success"));
        assertEquals(1, registry.itemCount("e-success"));
        assertEquals(1, gateway.calls());
    }

    @Test
    void rollbackRemovesBusinessDataAndPendingPublication() {
        assertThrows(
            IllegalStateException.class,
            () -> publisherService.create("e-rollback", true)
        );

        assertEquals(0, registry.itemCount("e-rollback"));
        assertEquals(0, registry.publicationCount("e-rollback"));
        assertEquals(0, gateway.calls());
    }

    @Test
    void failedAttemptCanBeRetriedWithoutNewPublication() {
        gateway.failNext();
        publisherService.create("e-retry", false);

        assertEquals("FAILED", registry.status("e-retry"));
        assertEquals(1, registry.attempts("e-retry"));

        // Trong production, scheduler/recovery worker sẽ làm việc này.
        handler.retry("e-retry");

        assertEquals("SUCCEEDED", registry.status("e-retry"));
        assertEquals(2, registry.attempts("e-retry"));
        assertEquals(1, registry.publicationCount("e-retry"));
        assertEquals(2, gateway.calls());
    }

    @Test
    void repeatedFailureStopsAtMaxAttempts() {
        gateway.setAlwaysFail(true);
        publisherService.create("e-dead", false);
        handler.retry("e-dead");
        handler.retry("e-dead");
        handler.retry("e-dead");

        assertEquals("DEAD", registry.status("e-dead"));
        assertEquals(3, registry.attempts("e-dead"));
        assertEquals(3, gateway.calls());
    }

    record WorkAccepted(String eventId) { }

    static class FakeGateway {
        private final AtomicBoolean failNext = new AtomicBoolean();
        private final AtomicBoolean alwaysFail = new AtomicBoolean();
        private final AtomicInteger calls = new AtomicInteger();

        void failNext() {
            failNext.set(true);
        }

        void setAlwaysFail(boolean value) {
            alwaysFail.set(value);
        }

        void reset() {
            failNext.set(false);
            alwaysFail.set(false);
            calls.set(0);
        }

        int calls() {
            return calls.get();
        }

        void send(String eventId) {
            calls.incrementAndGet();
            if (alwaysFail.get() || failNext.getAndSet(false)) {
                throw new IllegalStateException("gateway-unavailable");
            }
        }
    }

    static class Registry {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate statusTx;

        Registry(JdbcTemplate jdbc, TransactionTemplate statusTx) {
            this.jdbc = jdbc;
            this.statusTx = statusTx;
        }

        int claim(String eventId) {
            return statusTx.execute(status -> jdbc.update(
                "UPDATE event_state SET status='PROCESSING'," +
                "attempts=attempts+1, updated_at=CURRENT_TIMESTAMP " +
                "WHERE event_id=? AND handler='email' " +
                "AND status IN ('PENDING','FAILED') AND attempts<3",
                eventId
            ));
        }

        void success(String eventId) {
            statusTx.executeWithoutResult(status -> jdbc.update(
                "UPDATE event_state SET status='SUCCEEDED'," +
                "last_error=NULL, updated_at=CURRENT_TIMESTAMP " +
                "WHERE event_id=? AND handler='email' " +
                "AND status='PROCESSING'",
                eventId
            ));
        }

        void failure(String eventId, String errorCode) {
            statusTx.executeWithoutResult(status -> jdbc.update(
                "UPDATE event_state SET status=" +
                "CASE WHEN attempts >= 3 THEN 'DEAD' " +
                "ELSE 'FAILED' END, last_error=?," +
                "updated_at=CURRENT_TIMESTAMP " +
                "WHERE event_id=? AND handler='email' " +
                "AND status='PROCESSING'",
                errorCode, eventId
            ));
        }

        String status(String eventId) {
            return jdbc.queryForObject(
                "SELECT status FROM event_state " +
                "WHERE event_id=? AND handler='email'",
                String.class, eventId
            );
        }

        int attempts(String eventId) {
            return jdbc.queryForObject(
                "SELECT attempts FROM event_state " +
                "WHERE event_id=? AND handler='email'",
                Integer.class, eventId
            );
        }

        int publicationCount(String eventId) {
            return jdbc.queryForObject(
                "SELECT COUNT(*) FROM event_state WHERE event_id=?",
                Integer.class, eventId
            );
        }

        int itemCount(String eventId) {
            return jdbc.queryForObject(
                "SELECT COUNT(*) FROM work_item WHERE id=?",
                Integer.class, eventId
            );
        }
    }

    static class PublisherService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        PublisherService(JdbcTemplate jdbc, TransactionTemplate tx,
                         ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.tx = tx;
            this.publisher = publisher;
        }

        void create(String eventId, boolean rollback) {
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO work_item(id) VALUES (?)", eventId
                );
                jdbc.update(
                    "INSERT INTO event_state(" +
                    "event_id,handler,status,attempts) " +
                    "VALUES (?,?,?,?)",
                    eventId, "email", "PENDING", 0
                );
                publisher.publishEvent(new WorkAccepted(eventId));
                if (rollback) {
                    throw new IllegalStateException("forced-rollback");
                }
            });
        }
    }

    static class DeliveryHandler {
        private final Registry registry;
        private final FakeGateway gateway;

        DeliveryHandler(Registry registry, FakeGateway gateway) {
            this.registry = registry;
            this.gateway = gateway;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onWork(WorkAccepted event) {
            handle(event.eventId());
        }

        // Recovery entry point: gọi cùng logic từ scheduler.
        void retry(String eventId) {
            handle(eventId);
        }

        private void handle(String eventId) {
            if (registry.claim(eventId) != 1) {
                return; // SUCCEEDED, DEAD hoặc đang PROCESSING
            }
            try {
                gateway.send(eventId);
                registry.success(eventId);
            } catch (RuntimeException ex) {
                // Mã lỗi đã phân loại, không persist raw payload/stack.
                registry.failure(eventId, "GATEWAY_ERROR");
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                "jdbc:h2:mem:event_state_demo;DB_CLOSE_DELAY=-1",
                "sa", ""
            );
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        DataSourceTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean("publicationTx")
        TransactionTemplate publicationTx(
                DataSourceTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean("statusTx")
        TransactionTemplate statusTx(
                DataSourceTransactionManager manager) {
            TransactionTemplate template =
                new TransactionTemplate(manager);
            template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW
            );
            return template;
        }

        @Bean
        Registry registry(JdbcTemplate jdbc,
                @Qualifier("statusTx") TransactionTemplate statusTx) {
            return new Registry(jdbc, statusTx);
        }

        @Bean
        FakeGateway fakeGateway() {
            return new FakeGateway();
        }

        @Bean
        DeliveryHandler handler(Registry registry, FakeGateway gateway) {
            return new DeliveryHandler(registry, gateway);
        }

        @Bean
        PublisherService publisherService(
                JdbcTemplate jdbc,
                @Qualifier("publicationTx") TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            return new PublisherService(jdbc, tx, publisher);
        }
    }
}
~~~

### 7.3. Chạy và hiểu kết quả

Nếu project đã có Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.EventStatusTrackingTest"
~~~

Trên Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.EventStatusTrackingTest"
~~~

Bốn test không in log trạng thái thành stdout; kết quả mong đợi được kiểm tra qua assertions:

| Test | Kết quả sau transaction/attempt |
| --- | --- |
| `successfulCommitIsTracked` | Publication `SUCCEEDED`, attempts=1, work_item tồn tại |
| `rollbackRemovesBusinessDataAndPendingPublication` | Không có work_item/publication, listener after-commit không gọi gateway |
| `failedAttemptCanBeRetriedWithoutNewPublication` | Lần đầu `FAILED`; retry cùng ID thành `SUCCEEDED`, attempts=2, vẫn một publication |
| `repeatedFailureStopsAtMaxAttempts` | Sau ba lần lỗi: `DEAD`, attempts=3; retry tiếp không gọi gateway |

**Giới hạn cố ý của ví dụ:** `Registry.claim` là atomic update có điều kiện và `attempts`, nhưng chưa có `lease_until`/fencing, `next_attempt_at`, scheduler, idempotency ở gateway thật, publish persistence của nhiều handler hay DB restart. Một task bị crash khi đang `PROCESSING` có thể kẹt; đây là điều phải bổ sung trong production. H2 trong bộ test dùng in-memory DB, không kiểm chứng durability qua restart.

Test cũng dùng **listener AFTER_COMMIT đồng bộ**, không bật `@Async`. Vì vậy các assertion đọc trạng thái ngay sau `publisherService.create(...)` là phù hợp trong ví dụ này, bởi callback after-commit và các transaction cập nhật đã hoàn thành trước khi lệnh trả về. Nếu đổi sang `@Async`, phải **đợi observable outcome có timeout** (Awaitility/`CompletableFuture`/latch), không assert lập tức.

## 8. Spring Modulith Event Publication Registry: dùng thành phần có sẵn

Nếu ứng dụng chia thành các module trong Spring Boot, **Spring Modulith** cung cấp Event Publication Registry để ghi nhận những publication gửi tới các transactional event listeners trong transaction nghiệp vụ. Khi listener xử lý thành công, registry đánh dấu publication hoàn tất; nếu lỗi hoặc process crash, các publication chưa hoàn tất có thể được kiểm tra và resubmit theo cơ chế phù hợp.

Một listener module thường được viết:

~~~java
@Component
class BillingListener {

    @ApplicationModuleListener
    void on(OrderPaid event) {
        // Thực hiện công việc thuộc billing module.
    }
}
~~~

Đây là **trích đoạn Spring Modulith**, cần dependency, imports và loại `OrderPaid` của ứng dụng; không phải một phần của project H2 ở trên. `@ApplicationModuleListener` kết hợp ý tưởng transactional event listener và module event handling; semantics chi tiết còn tùy phiên bản Modulith và cấu hình transaction.

### Lifecycle và API theo phiên bản

- Ở các dòng Spring Modulith trước 2.0, trọng tâm registry là **publication incomplete/completed** và resubmission; trạng thái failure có thể được suy ra từ record chưa completed, không nên mặc định tồn tại một enum nhiều trạng thái.
- **Spring Modulith 2.0+** giới thiệu lifecycle cụ thể như `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED`, `RESUBMITTED`, cùng completion attempts và thông tin về lần resubmit. Đây là **tên trạng thái của Modulith**, khác tên `PENDING/SUCCEEDED/DEAD` do ta tự đặt ở phần ví dụ.
- Spring Modulith có `IncompleteEventPublications` và, ở các bản hỗ trợ từ 2.0, `FailedEventPublications` để hỗ trợ tìm/đưa publication trở lại xử lý. Cần kiểm tra API theo version project; không sao chép code từ phiên bản khác.
- Có thể cấu hình resubmit outstanding publications khi restart bằng property phù hợp với version (ví dụ `spring.modulith.events.republish-outstanding-events-on-restart` theo tài liệu hiện hành).
- Registry không mặc nhiên chứng minh external side effect là exactly-once. Một listener có thể tạo side effect rồi crash trước khi completion được ghi; idempotency vẫn quan trọng.

Các lựa chọn persistence có starter tương ứng (JDBC, JPA và một số datastore khác). Completion mode cũng cần thiết kế retention: `UPDATE` giữ record completed để truy vấn, `DELETE` xóa sau khi xong, `ARCHIVE` chuyển sang storage lưu lịch sử, tùy version/khả năng backend. Không để completion records tăng vô hạn mà không có housekeeping.

**Nên chọn registry có sẵn khi** kiến trúc dùng Spring Modulith phù hợp, các listeners cần tracking transactional delivery và muốn tránh tự viết toàn bộ ledger/recovery logic. **Nên dùng outbox/broker/consumer tracker riêng khi** workflow vượt process/service, yêu cầu broker ack, partitioning, DLQ, lifecycle khác hoặc cần monitoring/retention phù hợp một hệ thống message bus bên ngoài.

## 9. Observability và vận hành: log, metrics, cảnh báo

Một state table chỉ hữu ích nếu người vận hành có thể phát hiện backlog và failures. Ví dụ một log record nên giữ field có ý nghĩa nhất quán:

~~~json
{
  "message": "event_handler_state_transition",
  "event_id": "evt-103",
  "handler_id": "send-receipt-email",
  "previous_state": "PROCESSING",
  "new_state": "FAILED",
  "attempt": 2,
  "error_code": "DOWNSTREAM_TIMEOUT",
  "correlation_id": "corr-77"
}
~~~

Không đưa password, access token, raw request payload hoặc stack trace chứa PII vào ledger/log một cách tùy tiện. `last_error_code` nên là giá trị được phân loại/sanitize, không phải `exception.toString()` của dữ liệu nhạy cảm.

Các metrics quan trọng:

| Metric | Dùng để làm gì? |
| --- | --- |
| `pending_publications` | Có bao nhiêu publication chờ xử lý |
| `oldest_pending_age_seconds` | Công việc lâu nhất bị tồn đọng |
| `processing_age_seconds` | Phát hiện worker chậm hoặc stuck |
| `failed_publications` | Quy mô công việc lỗi còn retry |
| `dead_publications` | Số publication cần can thiệp |
| `processing_duration_seconds` | P50/P95/P99 latency của handler |
| `attempts_per_publication` | Retry tăng bất thường |
| `resubmission_rate` | Tốc độ khôi phục, nguy cơ retry storm |
| `outbox_lag_seconds` | Độ trễ từ commit đến giao downstream |

Không dùng `event_id` hay `publication_id` làm metric label vì cardinality cao; dùng `event_type`, `handler_id`, `status` ở tập giá trị được kiểm soát. Dùng structured logs + trace ID/correlation ID để điều tra **một event cụ thể**.

### Cảnh báo nên dựa vào thời gian, không chỉ số lượng

Một backlog 200 publication trong lúc peak load có thể bình thường, nhưng một publication `PENDING` 12 giờ hoặc `PROCESSING` vượt lease là tín hiệu nghiêm trọng hơn. Alert nên kết hợp:

- độ tuổi publication cũ nhất;
- số `DEAD` mới xuất hiện;
- tỷ lệ `FAILED`/retry theo handler;
- throughput xử lý so với arrival;
- tần suất lease expiry;
- lỗi DB/broker/repository khiến **status write** không thành công.

**Lưu ý lỗi khi ghi trạng thái:** nếu side effect thành công nhưng `mark SUCCEEDED` thất bại, không được kết luận chắc chắn handler chưa thành công. Nó có thể rơi vào trạng thái **unknown outcome**, phải reconciliation/idempotency trước retry.

## 10. Các vấn đề transaction và concurrency thường bị bỏ sót

### 10.1. Trạng thái của nhiều handler khác nhau

Một event được xử lý bởi invoice, email và analytics không phải một unit thành công duy nhất. Mỗi handler có thể commit vào DB khác, gọi gateway riêng và có retry độc lập. Aggregate-level summary như `ALL_DONE` chỉ nên được suy ra từ trạng thái từng đích và rule rõ ràng.

### 10.2. Rollback của event producer

Khi source transaction rollback, publication được ghi trong cùng transaction cũng phải rollback. Nếu publication được ghi autocommit trước khi nghiệp vụ rollback, worker có thể xử lý một event mà trạng thái nghiệp vụ chưa từng được commit.

### 10.3. Hai worker cùng claim

Câu `UPDATE ... WHERE status='PENDING'` atomic hạn chế claim trùng trong database, nhưng không tự giải quyết crash/scheduling. Lease và fencing cần đi kèm khi retry sau timeout.

### 10.4. `PROCESSING` vô hạn

Nếu chỉ chuyển trạng thái trong `catch`, crash không chạy catch. Cần monitor stale/lease và recovery. Nhưng đừng resubmit mọi `PROCESSING` ngay khi nhìn thấy chúng: task có thể đang hoạt động bình thường.

### 10.5. Trạng thái thay đổi trước side effect

Đánh dấu `SUCCEEDED` **trước** khi gọi gateway là sai: gateway có thể fail, ledger nói thành công giả. Đánh dấu sau side effect vẫn có một failure window giữa hai thao tác; đó là lý do cần idempotency.

### 10.6. Xóa publication quá sớm

Nếu completed records bị xóa ngay, operator không còn toàn bộ lịch sử. Cần chọn retention theo audit/compliance. Nếu lưu mãi không purge, storage/index tăng vô hạn. Completion mode là trade-off, không có một giá trị đúng cho mọi hệ thống.

### 10.7. Duplicate publication khác duplicate attempt

Một unique constraint có thể chặn hai publication cho cùng event/handler, nhưng worker vẫn có thể có nhiều attempts của **một publication**. Đừng sửa `event_id` giữa các lần retry nếu vẫn là cùng sự kiện logic.

## 11. Thiết kế retry/recovery production

Một recovery loop cần các bước rõ ràng:

~~~text
periodic scheduler
  -> tìm PENDING đến hạn + FAILED retryable đến hạn
  -> claim nguyên tử với worker ID/lease/fencing token
  -> gọi handler với idempotency key ổn định
  -> nếu thành công: commit SUCCEEDED (đúng token)
  -> nếu lỗi: record error code, next_attempt_at, FAILED hoặc DEAD
  -> nếu crash: staleness monitor phát hiện lease quá hạn
  -> cảnh báo nếu DEAD/oldest pending vượt threshold
~~~

Backoff mẫu: `min(cap, base × 2^(attempt-1)) + jitter`. Không nên dùng cùng một deadline cố định khiến hàng nghìn publications retry đồng thời, tạo “thundering herd”.

Bảng policy cần được định nghĩa trước:

| Lỗi | Hành động gợi ý |
| --- | --- |
| Network timeout / HTTP 503 / DB lock transient | Retry có backoff và giới hạn |
| Validation lỗi schema/version | `DEAD` hoặc quarantine, cần sửa dữ liệu |
| Permission denied vĩnh viễn | Không retry mù; cần policy/cấu hình lại |
| Duplicate detected by idempotent sink | Xem contract rồi coi thành công đã có hoặc đối chiếu |
| Unknown result sau timeout khi gọi payment gateway | Query trạng thái bằng idempotency key trước khi retry |
| Crash trong `PROCESSING` | Lease expiry + fencing + downstream idempotency |
| Lỗi ghi trạng thái `SUCCEEDED` | Reconciliation; tránh giả định side effect chưa xảy ra |

Với payment/billing, **không tự retry charge bằng request mới không có idempotency key** chỉ vì publication còn `FAILED`. Độ tin cậy phải được thiết kế end-to-end qua cả hai phía.

## 12. Kiểm thử nào chứng minh trạng thái đáng tin cậy?

Bộ test H2 minh họa các transition cơ bản, nhưng production nên có thêm các bài test sau:

1. **Commit + listener thành công:** publication đến terminal state đúng.
2. **Producer rollback:** không còn publication độc lập trái với nghiệp vụ.
3. **Failure + retry:** cùng event ID, attempts tăng, một publication duy nhất.
4. **Max retries / permanent error:** chuyển `DEAD`, không lặp vô hạn.
5. **Hai workers đồng thời:** chỉ một claim thắng trong cùng thời điểm.
6. **Process chết giữa PROCESSING:** lease stale, recovery đúng và token cũ không thể mark succeeded.
7. **Side effect thành công nhưng mark status lỗi:** retry không lặp side effect nhờ idempotency.
8. **Nhiều handlers:** failure của email không làm mất completed của invoice.
9. **Async listener:** đợi observable outcome bằng Awaitility/latch có timeout, không dùng `Thread.sleep`.
10. **Transaction after-commit:** test thực sự commit; không gắn `@Transactional` trên test rồi để Spring TestContext rollback mặc định.
11. **Monitoring:** status counters, oldest age, dead alerts được ghi/đọc đúng.
12. **Schema migration và restart:** publication cũ vẫn được rehydrate bởi phiên bản mới.

Test cạnh tranh và crash nên dùng database/persistence phù hợp production (có thể bằng Testcontainers) vì H2 không mô phỏng toàn bộ isolation/locking của PostgreSQL/MySQL.

## 13. Checklist triển khai

- [ ] Mỗi logical event có `event_id` ổn định và event type/version rõ.
- [ ] Trạng thái lưu theo **event + handler**, không chỉ theo event tổng quát.
- [ ] Publication đăng ký transactionally với thay đổi nghiệp vụ khi cần durability.
- [ ] Có atomic claim, max attempts, backoff và policy phân loại lỗi.
- [ ] Có lease/staleness detection và fencing token nếu nhiều workers.
- [ ] Có idempotency cho side effect ở DB/broker/API ngoài.
- [ ] Phân biệt `published`, `processing`, `completed` với commit/ack semantics.
- [ ] `@TransactionalEventListener(AFTER_COMMIT)` không bị nhầm là durable queue.
- [ ] Có cơ chế replay/recovery publication tồn đọng sau restart.
- [ ] Có trạng thái `DEAD` hoặc quarantine cho lỗi không thể retry.
- [ ] Có metrics về backlog tuổi, failure ratio, processing time và retry storm.
- [ ] Không log hoặc lưu credentials/raw payload nhạy cảm vào ledger.
- [ ] Có retention/cleanup completion records phù hợp.
- [ ] Test thực tế commit, rollback, failure, retry, crash/concurrency.

## 14. Câu hỏi tự kiểm tra

**Câu 1:** `publishEvent()` trả về bình thường có nghĩa listener async đã hoàn tất không?

Không. Nó thường chỉ xác nhận đường dispatch/schedule theo cấu hình. Muốn biết xử lý xong cần quan sát outcome của từng handler.

**Câu 2:** Vì sao trạng thái cần theo `(event_id, handler_id)`?

Vì cùng một event có thể được invoice xử lý xong, email thất bại và analytics đang chạy. Một trạng thái `DONE` chung làm mất thông tin và khiến retry sai.

**Câu 3:** Ghi `PENDING` và dữ liệu nghiệp vụ trong cùng transaction mang lại gì?

Nếu transaction commit, cả dữ liệu và publication tồn tại; nếu rollback, cả hai biến mất. Điều đó hỗ trợ khôi phục sau crash ở bước dispatch.

**Câu 4:** Vì sao cần `PROCESSING` cùng lease/fencing?

Để phân biệt đã claim với chưa claim, phát hiện worker crash và ngăn worker cũ ghi đè trạng thái của worker mới. Lease một mình chưa loại được duplicate side effect.

**Câu 5:** Mark `SUCCEEDED` sau khi gọi gateway thành công đã đảm bảo exactly-once chưa?

Chưa. Có một khoảng giữa gateway thành công và status write; crash trong khoảng này có thể tạo retry. Cần idempotency/reconciliation ở downstream.

**Câu 6:** `@TransactionalEventListener(AFTER_COMMIT)` có tự lưu event bền vững không?

Không. Nó gắn callback với transaction phase; durability/recovery cần registry hoặc outbox/persistence phù hợp.

**Câu 7:** Spring Modulith Registry khác bảng tự xây trong ví dụ thế nào?

Modulith cung cấp hạ tầng ghi publication và completion/resubmission, có lifecycle mở rộng trong các phiên bản 2.x. Bảng tự xây trong ví dụ chỉ minh họa vài state transitions, chưa có crash recovery/lease/production durability.

**Ghi nhớ:** Theo dõi event đáng tin cậy phải trả lời **event nào, tới handler nào, đang ở attempt nào, đã commit kết quả chưa, có retry an toàn được không và khôi phục ra sao khi crash**. State machine + publication ledger transactionally persisted + idempotency + recovery/metrics mới tạo thành một giải pháp đầy đủ; gọi `publishEvent` hoặc log “done” đơn lẻ là không đủ.

## Tài liệu tham khảo

- [Spring Framework – Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – @TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Modulith – Working with Application Events / Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith – EventPublicationRegistry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html)
- [Spring Framework – TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
