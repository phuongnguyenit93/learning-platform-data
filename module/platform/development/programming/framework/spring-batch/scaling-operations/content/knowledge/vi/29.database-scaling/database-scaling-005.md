# Lock contention khi ghi trong Spring Batch

## 1. Khi 32 worker tranh cùng một hàng dữ liệu

Một hệ thống tài chính xử lý hàng chục triệu giao dịch bằng Spring Batch. Job được chia thành 32 partition theo khoảng thời gian; các worker đọc dữ liệu độc lập và cập nhật bảng tổng hợp số dư. Sau khi tăng từ 4 lên 32 worker, hệ thống gặp hiện tượng:

- CPU worker thấp dù số thread lớn, còn thời gian job tăng.
- PostgreSQL có nhiều session `active` nhưng phần lớn đợi `Lock` hoặc `transactionid`.
- Các transaction cùng `UPDATE account_balances SET balance_cents = ... WHERE account_id = 42` bị xếp hàng.
- Một số chunk nhận lỗi deadlock hoặc `lock_timeout`; retry làm tải tăng thêm.
- JDBC pool sớm hết connection vì thread mượn connection rồi **giữ trong lúc chờ khóa**.

Dữ liệu đầu vào đã được chia đúng thành các partition không giao nhau, nhưng mọi partition vẫn có thể ghi vào **cùng một tài khoản tổng hợp**. **Partition đầu vào không đồng nghĩa partition khóa ghi.**

Đây là bài **“Lock contention khi ghi”** thuộc chương **Database scaling** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module tập trung mở rộng Spring Batch cho dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán, đồng thời đo nút thắt, đảm bảo thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế.

Sau bài này, bạn có thể:

1. Phân biệt **lock wait**, **deadlock**, **lost update**, **optimistic conflict** và **pool starvation**.
2. Giải thích vì sao MVCC không loại bỏ nhu cầu khóa khi nhiều writer sửa cùng dữ liệu.
3. Tìm hot rows, lock blockers và transaction kéo dài bằng số liệu PostgreSQL.
4. Thiết kế partition theo **khóa ghi** thay vì chỉ chia theo thời gian đọc.
5. Áp dụng thứ tự khóa xác định, transaction ngắn, immutable ledger và idempotency.
6. Biết khi nào `SKIP LOCKED` phù hợp và khi nào tuyệt đối không dùng để lặng lẽ bỏ qua record.
7. Chọn mức concurrency, chunk size, retry/backoff và kiểm thử restart dựa trên bằng chứng.

Ví dụ tập trung vào **Java 17+, Spring Batch 5.2.x, Spring Boot 3.x và PostgreSQL**. Nguyên tắc contention cũng áp dụng cho RDBMS khác, nhưng **loại khóa, mức isolation, cú pháp SQL và cơ chế chẩn đoán khác nhau**; không coi lệnh PostgreSQL là SQL portable.

## 2. Hiểu đúng lock contention trong cơ sở dữ liệu

**Lock contention** xuất hiện khi một transaction đang giữ hoặc yêu cầu một tài nguyên khóa mà transaction khác cần theo chế độ không tương thích. Transaction đến sau phải chờ, thất bại vì timeout hoặc bị chọn làm nạn nhân deadlock.

PostgreSQL sử dụng **MVCC** để nhiều thao tác đọc thông thường không phải chờ các transaction đang ghi theo cách một số mô hình khóa truyền thống yêu cầu. Nhưng MVCC **không** cho phép hai transaction cập nhật cùng một row mà không phối hợp:

- `UPDATE`/`DELETE` và `SELECT ... FOR UPDATE` có thể tạo tranh chấp row-level lock.
- `INSERT` với `UNIQUE`/`PRIMARY KEY` hoặc `ON CONFLICT` có thể chờ transaction tạo cùng giá trị khóa.
- Foreign key validation, DDL, bảng/hàng khóa theo mode khác nhau cũng có thể tạo wait.
- Một số bottleneck hiển thị dưới dạng `LWLock`, I/O, buffer contention hoặc CPU, **không phải** tất cả đều là row locks.

### Các khái niệm dễ nhầm

| Hiện tượng | Điều xảy ra | Phản ứng phù hợp |
|---|---|---|
| **Lock wait** | Transaction B đợi A nhả khóa | Đo blocker, giảm thời gian giữ khóa và tần suất chạm hot key |
| **Deadlock** | A đợi B và B cũng đợi A, tạo chu trình | DB hủy một transaction; sửa thứ tự khóa và retry **toàn transaction** có giới hạn |
| **Lost update** | App đọc một giá trị cũ rồi ghi đè giá trị đã được transaction khác cập nhật | Dùng SQL update nguyên tử, điều kiện version/optimistic lock, hoặc row lock phù hợp |
| **Serialization failure** | DB yêu cầu retry vì lịch thực thi không thỏa isolation semantics | Retry đơn vị transaction đã rollback theo chính sách |
| **Pool starvation** | Nhiều thread chờ mượn JDBC connection | Đo active/pending và transaction hold time; có thể là **hậu quả** của lock contention |
| **Hot row/key** | Nhiều worker liên tục cập nhật cùng một business key | Đổi ownership/aggregation design, tránh fan-in vào một row |
| **Index/unique contention** | Nhiều write chạm unique key hoặc vùng index nóng | Đo conflict pattern, thiết kế key/index/batch hợp lý |

**Không kết luận `active connections` cao là đủ chứng minh lock contention.** Cần đối chiếu PostgreSQL wait events, blocking sessions, SQL/transaction duration và số worker đang chạm cùng khóa.

## 3. Dòng thời gian: transaction chờ một hot row

Giả sử có bảng:

~~~sql
CREATE TABLE account_balances (
    account_id    BIGINT PRIMARY KEY,
    balance_cents BIGINT NOT NULL DEFAULT 0
);

INSERT INTO account_balances(account_id, balance_cents)
VALUES (42, 100000);
~~~

Hai transaction muốn cộng tiền vào `account_id=42`:

~~~mermaid
sequenceDiagram
    participant A as Worker A / Tx A
    participant D as PostgreSQL row account_id=42
    participant B as Worker B / Tx B
    A->>D: BEGIN; UPDATE balance += 500
    Note over A,D: Tx A giữ row lock tới commit/rollback
    B->>D: BEGIN; UPDATE balance += 200
    Note over B,D: Tx B chờ khóa không tương thích
    A->>D: COMMIT
    D-->>B: Có thể tiếp tục UPDATE
    B->>D: COMMIT
~~~

Với một transaction ghi từ 4 worker và một transaction khác từ 32 worker, **một hot row vẫn phải được cập nhật tuần tự ở điểm tranh chấp**. Tăng worker còn có thể làm hàng đợi lock và connection usage dài hơn.

### Minh họa thủ công trên hai session, chỉ dùng staging

**Session A:**

~~~sql
BEGIN;
UPDATE account_balances
SET balance_cents = balance_cents + 500
WHERE account_id = 42;
-- Giữ transaction chưa COMMIT để quan sát.
~~~

**Session B, đồng thời:**

~~~sql
BEGIN;
UPDATE account_balances
SET balance_cents = balance_cents + 200
WHERE account_id = 42;
-- Có thể chờ đến khi A COMMIT/ROLLBACK.
COMMIT;
~~~

Quay lại **session A**, thực hiện `COMMIT`. Khi đó session B có thể tiếp tục và commit. Không giữ session A mở lâu trong production chỉ để tạo thử nghiệm vì nó có thể chặn job và các ứng dụng khác.

### Atomic increment khác với stale read–modify–write

~~~sql
-- Nên dùng cho phép cộng số dư đơn giản:
UPDATE account_balances
SET balance_cents = balance_cents + :deltaCents
WHERE account_id = :accountId;
~~~

Phép cập nhật biểu thức trên được database áp dụng với điều phối transaction/khóa, khác với cách ứng dụng đọc số dư, tính toán ngoài database rồi ghi đè một hằng số:

~~~text
Thread A đọc balance=100
Thread B đọc balance=100
A ghi balance=110
B ghi balance=120
=> Sai nếu nghiệp vụ mong 100+10+20=130.
~~~

Một transaction bao quanh Java code **chưa chắc** loại bỏ lost update nếu ứng dụng thực hiện read–modify–write bằng giá trị cũ mà không dùng isolation/locking/version control phù hợp. Dùng atomic SQL, optimistic versioning hoặc pessimistic locking theo yêu cầu nghiệp vụ.

## 4. Vì sao một batch partition plan vẫn đụng khóa nhau?

~~~mermaid
flowchart TB
    M[Partition manager] --> PA["Window A: 00–06h"]
    M --> PB["Window B: 06–12h"]
    M --> PC["Window C: 12–18h"]
    PA --> WA[Worker A]
    PB --> WB[Worker B]
    PC --> WC[Worker C]
    WA --> RA["UPDATE account 42"]
    WB --> RB["UPDATE account 42"]
    WC --> RC["UPDATE account 42"]
    RA --> H[(Hot row: account_id 42)]
    RB --> H
    RC --> H
~~~

Ba worker **đọc các event khác nhau** và vẫn đồng thời tranh hàng số dư của cùng tài khoản.

| Kiểu partition đầu vào | Có ngăn write contention không? | Vì sao |
|---|---|---|
| Theo thời gian | **Không mặc định** | Tài khoản/khách hàng xuất hiện ở nhiều khoảng thời gian |
| Theo ID sự kiện | **Không mặc định** | Các event ID khác nhau vẫn có thể cập nhật một aggregate key |
| Theo file | **Không mặc định** | Hai file có thể chứa cùng business key |
| Theo tenant | **Có thể**, nếu khóa ghi cũng tách theo tenant | Bảng/dòng shared global vẫn có thể bị tranh |
| Theo `account_id` hoặc hash của khóa ghi | **Thường tốt hơn** | Mỗi account có thể thuộc một worker/partition trong job |
| Theo time + account bucket | **Có điều kiện** | Cần bảo đảm một account không bị nhiều window viết cùng lúc hoặc thay cách ghi |

**Không đồng nhất tách reader state với tách write set.** `@StepScope` giúp một reader có state/cursor riêng cho mỗi `StepExecution`, nhưng writer singleton hay nhiều writer khác nhau vẫn có thể cập nhật **cùng một row trong database**.

### Một write-conflict graph hữu ích

Xem mỗi partition là một node; nối hai partition nếu chúng có thể ghi cùng key:

~~~text
Partition 0: account {1, 2, 42}
Partition 1: account {3, 42, 77}
Partition 2: account {42, 88}

Conflict edges:
0 -- 1 (account 42)
0 -- 2 (account 42)
1 -- 2 (account 42)
~~~

Nếu cùng một key xuất hiện ở hàng chục partition, tăng worker chỉ làm nhiều transaction đồng thời xếp hàng. Giải pháp tốt hơn là **điều chỉnh write ownership hoặc data flow**, không chỉ thay pool size.

## 5. Transaction càng dài, khóa càng bị giữ lâu

Với transaction thông thường, các row lock do `UPDATE` giữ sẽ tồn tại đến **COMMIT hoặc ROLLBACK**. Một chunk transaction lâu không chỉ làm lock wait tăng mà còn giữ JDBC connection, có thể tạo pool starvation dây chuyền.

~~~text
BEGIN TRANSACTION
  UPDATE hot account row
  xử lý thêm 1.000 item
  gọi HTTP API mất 12 giây
  ghi thêm business rows
COMMIT
~~~

Nếu connection đã mượn và row lock đã được lấy trước lời gọi HTTP, các worker khác có thể phải đợi toàn bộ 12 giây. Khi tăng concurrency, hàng đợi lock tăng và nhiều thread giữ connection mà không làm việc hữu ích.

### Liên hệ với chunk size

Spring Batch chunk-oriented step xử lý một nhóm item rồi commit. `chunk(1000)` **không** có nghĩa có 1.000 connections, nhưng có thể kéo dài transaction hơn `chunk(100)` nếu cùng logic xử lý và lượng ghi.

| Thiết kế | Lợi ích có thể có | Rủi ro |
|---|---|---|
| Chunk nhỏ | Transaction ngắn, số item phải retry ít | Nhiều commit, metadata updates và roundtrip |
| Chunk lớn | Tận dụng JDBC batch/giảm commit overhead | Lock được giữ lâu, rollback/retry tốn thời gian |
| Network call trong transaction | Code nhìn đơn giản | Chờ mạng trong lúc giữ connection/khóa |
| Writer upsert cùng aggregate row | Dễ cập nhật báo cáo tức thì | Hot row và contention tăng theo worker |
| Tách append-only rồi aggregate riêng | Tránh nhiều worker chạm cùng mutable row | Thêm bước tổng hợp và quản lý tính nhất quán |

### Tránh HTTP/API chậm trong transaction

~~~java
// Anti-pattern minh họa, không phải class Java độc lập:
@Transactional
public void applyAndNotify(LedgerEvent event) {
    jdbcTemplate.update(
            "UPDATE account_balances "
          + "SET balance_cents = balance_cents + ? "
          + "WHERE account_id = ?",
            event.deltaCents(), event.accountId());

    remoteBillingApi.send(event); // Có thể giữ row lock trong lúc chờ mạng.
}
~~~

Một phương án là dùng **transactional outbox**: transaction ghi business data và một outbox event vào cùng database, commit, rồi worker khác gửi message/API với idempotency key. Điều này giúp **rút ngắn thời gian giữ khóa** và tránh buộc broker/API bên ngoài nằm trong transaction DB.

**Không chuyển một side effect ra async rồi mặc định đạt exactly-once.** Cần schema outbox, event ID, consumer dedupe và cơ chế retry bền vững.

## 6. Nhiều worker có thể lock khác thứ tự và gây deadlock

Hai transaction đều cần cập nhật tài khoản A và B:

~~~text
Tx 1: lock account 10
Tx 2: lock account 20
Tx 1: request lock account 20 -> chờ Tx 2
Tx 2: request lock account 10 -> chờ Tx 1
=> chu trình deadlock; PostgreSQL hủy một transaction
~~~

~~~mermaid
flowchart LR
    T1["Tx 1 giữ row 10"] -->|Đợi row 20| T2["Tx 2 giữ row 20"]
    T2 -->|Đợi row 10| T1
~~~

Trong PostgreSQL, deadlock thường được báo bằng SQLSTATE **`40P01`**. Database phát hiện chu trình và hủy một transaction để phần còn lại tiếp tục. Đây không giống tình huống một transaction chỉ **chờ một chiều** để transaction khác commit.

### Quy tắc quan trọng: luôn lấy khóa theo một thứ tự xác định

Nếu mọi transaction phải khóa nhiều account, hãy chuẩn hóa thứ tự theo `account_id` tăng dần, **bất kể chiều chuyển tiền**:

~~~text
Transfer 10 -> 20: lock 10, lock 20
Transfer 20 -> 10: lock 10, lock 20
~~~

Thứ tự nhất quán làm giảm chu trình deadlock do ứng dụng tự tạo, nhưng **không bảo đảm triệt tiêu mọi deadlock** vì có thể còn index/FK, trigger, logic SQL khác hoặc code path không áp cùng quy ước.

### Ví dụ Java dùng Spring transaction và thứ tự khóa

~~~java
import java.util.List;
import java.util.stream.Stream;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountTransferService {
    private final JdbcTemplate jdbcTemplate;

    public AccountTransferService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void transfer(long sourceId, long targetId, long cents) {
        if (sourceId == targetId || cents <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        List<Long> ids = Stream.of(sourceId, targetId)
                .sorted()
                .toList();

        // Mọi transaction lock các row theo thứ tự account_id tăng dần.
        for (long accountId : ids) {
            Long existing = jdbcTemplate.queryForObject(
                    "SELECT account_id FROM account_balances "
                  + "WHERE account_id = ? FOR UPDATE",
                    Long.class, accountId);
            if (existing == null) {
                throw new IllegalStateException("Missing account");
            }
        }

        int debited = jdbcTemplate.update("""
                UPDATE account_balances
                SET balance_cents = balance_cents - ?
                WHERE account_id = ? AND balance_cents >= ?
                """, cents, sourceId, cents);
        if (debited != 1) {
            throw new IllegalStateException("Insufficient balance");
        }

        int credited = jdbcTemplate.update("""
                UPDATE account_balances
                SET balance_cents = balance_cents + ?
                WHERE account_id = ?
                """, cents, targetId);
        if (credited != 1) {
            throw new IllegalStateException("Missing target");
        }
    }
}
~~~

Đây là **ví dụ kỹ thuật về thứ tự khóa**, chưa phải hệ thống chuyển tiền production: nó thiếu **transfer ID/idempotency key**, journal/audit trail, giới hạn số tiền, authorization, overflow checks và kiểm soát chính sách nghiệp vụ. Không dùng nó làm writer batch có thể replay khi restart nếu chưa bổ sung các ràng buộc đó.

`@Transactional` chỉ phát huy đúng nếu method được gọi qua Spring-managed proxy và `JdbcTemplate` sử dụng DataSource/transaction manager tương ứng. Trong môi trường nhiều DataSource, phải chỉ rõ transaction manager phù hợp. Không gọi `this.transfer(...)` từ method cùng class rồi giả định proxy sẽ can thiệp.

## 7. Thiết kế event idempotent nhưng vẫn có hot row

Giả sử mỗi event có `event_id` duy nhất. Một transaction cần:

1. Chỉ chấp nhận `event_id` một lần.
2. Nếu event mới, cộng `delta_cents` vào số dư tài khoản.
3. Nếu event bị replay, không cộng lần hai.

Tiếp tục dùng bảng `account_balances` đã tạo ở phần 3 (không chạy lại lệnh `CREATE TABLE` cho bảng ấy). Bổ sung bảng ghi nhận event đã xử lý:

~~~sql
CREATE TABLE processed_ledger_events (
    event_id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL
        REFERENCES account_balances(account_id),
    delta_cents BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_ledger_events_account_time
    ON processed_ledger_events (account_id, occurred_at, event_id);
~~~

Một SQL statement có thể thực hiện guard idempotency và cập nhật số dư **cùng một statement/transaction**:

~~~sql
WITH accepted AS (
    INSERT INTO processed_ledger_events
        (event_id, account_id, delta_cents, occurred_at)
    VALUES
        (:eventId, :accountId, :deltaCents, :occurredAt)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING account_id, delta_cents
)
UPDATE account_balances AS b
SET balance_cents = b.balance_cents + a.delta_cents
FROM accepted AS a
WHERE b.account_id = a.account_id;
~~~

**Tại sao câu lệnh này hữu ích?** Nếu `event_id` đã được ghi bởi một transaction đã commit, CTE `accepted` không có row, nên `UPDATE` không cộng thêm lần nữa. Nếu event mới, cả việc insert marker và cộng số dư thuộc cùng transaction. Nếu transaction rollback, cả hai thao tác rollback.

**Giới hạn:**

- Nếu hai event mới cùng `account_id=42`, cả hai vẫn phải tranh khóa row `account_balances(42)`.
- `ON CONFLICT DO NOTHING` không có nghĩa **không đợi khóa**: unique conflict với transaction chưa commit có thể phải đợi.
- Duplicate `event_id` nhưng payload khác không nên được im lặng bỏ qua trong nghiệp vụ nghiêm ngặt; cần validate checksum/business invariants, phát hiện data corruption.
- Không dùng schema này cho các business invariants phức tạp hoặc sửa event đã phát hành mà chưa có versioning/bù trừ.
- Nếu cùng transaction còn publish event qua API ngoài DB, câu lệnh này không làm side effect ngoài DB idempotent.

### Spring Batch JDBC writer minh họa

~~~java
import java.time.OffsetDateTime;
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

record LedgerEvent(
        long eventId,
        long accountId,
        long deltaCents,
        OffsetDateTime occurredAt) {}

@Configuration
public class LedgerWriterConfiguration {
    @Bean
    public JdbcBatchItemWriter<LedgerEvent> ledgerWriter(
            DataSource businessDataSource) {

        return new JdbcBatchItemWriterBuilder<LedgerEvent>()
                .dataSource(businessDataSource)
                .sql("""
                    WITH accepted AS (
                        INSERT INTO processed_ledger_events
                            (event_id, account_id, delta_cents, occurred_at)
                        VALUES
                            (:eventId, :accountId, :deltaCents, :occurredAt)
                        ON CONFLICT (event_id) DO NOTHING
                        RETURNING account_id, delta_cents
                    )
                    UPDATE account_balances AS b
                    SET balance_cents = b.balance_cents + a.delta_cents
                    FROM accepted AS a
                    WHERE b.account_id = a.account_id
                    """)
                .itemSqlParameterSourceProvider(e ->
                        new MapSqlParameterSource()
                                .addValue("eventId", e.eventId())
                                .addValue("accountId", e.accountId())
                                .addValue("deltaCents", e.deltaCents())
                                .addValue("occurredAt", e.occurredAt()))
                .assertUpdates(false)
                .build();
    }
}
~~~

`assertUpdates(false)` cần có trong ví dụ vì một event trùng sẽ cho **0 row updated**, và điều đó là outcome mong đợi của idempotency guard. `JdbcBatchItemWriter`/driver vẫn cần integration test với PostgreSQL thực để xác minh update counts, transaction boundaries và checkpoint.

**Đây không phải cách loại bỏ contention** mà là cách xử lý **duplicate/restart an toàn hơn**. Với tài khoản rất nóng, cả nghìn worker thực hiện CTE này vẫn xếp hàng trên cùng row số dư.

## 8. Đổi kiến trúc ghi: immutable events trước, aggregate sau

Một hướng giảm hot row là **không cập nhật aggregate row trong mọi worker ingest**:

~~~mermaid
flowchart LR
    A[Worker partition 0] --> E[(Append-only ledger)]
    B[Worker partition 1] --> E
    C[Worker partition 2] --> E
    E --> G[Aggregate theo account_id hoặc bucket]
    G --> S[(account_balances / projections)]
~~~

Ở bước ingest, worker ghi **event immutable có khóa riêng**, hạn chế đụng nhau tại aggregate row. Bước tiếp theo gom event và cập nhật số dư **theo account**, có thể dùng một owner/worker cho mỗi account hoặc một batch update có logic kiểm tra version.

### So sánh phương án

| Phương án | Lợi ích | Đánh đổi |
|---|---|---|
| Mỗi event cập nhật `account_balances` ngay | Số dư mới gần real-time | Hot rows, lock wait theo số worker |
| Ghi immutable event rồi aggregate sau | Writer ingest ít tranh aggregate row hơn, audit tốt | Eventual consistency, thêm bước xử lý và watermark |
| Partition theo `account_id` | Một account vào một worker trong job | Account lớn tạo partition skew; các job khác vẫn có thể đụng |
| Aggregate từng nhóm account | Giảm số lần sửa cùng row | Cần đảm bảo một batch update không làm bỏ sót event |
| Sharded counters / per-bucket totals | Giảm fan-in vào một row | Đọc/tổng hợp phức tạp hơn, semantics nhất quán cần rõ |

**Immutable ledger không miễn nhiễm mọi contention**: primary-key/unique index, foreign key, index page hotspot và storage throughput vẫn có thể là bottleneck. Nó chỉ chuyển điểm nóng từ một mutable aggregate row sang workload insert phân tán hơn; phải đo thực tế.

### Chia theo khóa ghi thay vì thời gian

Nếu bước aggregate dùng một partition cho mỗi bucket:

~~~sql
-- Khi account_id là số nguyên không âm và bucketCount được cố định:
WHERE MOD(account_id, :bucketCount) = :bucketId
~~~

Các bucket phải **không giao nhau, phủ đủ tập account và giữ cố định qua restart**. Nếu account ID có thể âm, cần chuẩn hóa modulo. Điều kiện `MOD` trên cột có thể làm index btree thông thường khó dùng; cân nhắc lưu `bucket_id` materialized/index hoặc dùng manifest phân vùng nếu query plan đòi hỏi.

Với một account chứa 40% tổng event, hash partitioning cũng không tự cân tải: một owner vẫn phải xử lý account đó. Có thể tổng hợp partial per-account segments trước, rồi merge kết quả cuối theo một transaction/owner duy nhất, miễn phép tổng hợp kết hợp được và idempotency được thiết kế rõ.

## 9. Chẩn đoán blocker và transaction đang chờ bằng PostgreSQL

Muốn xử lý contention, bước đầu tiên là **tìm đúng transaction đang chặn**, không phải tăng `connectionTimeout`. Với PostgreSQL, `pg_stat_activity` và `pg_blocking_pids(pid)` giúp xác định session bị block và session đang block. Quyền quan sát phải được DBA cấp phù hợp, ví dụ role có quyền đọc thống kê cần thiết.

### 9.1. Liệt kê session đang bị chặn

~~~sql
SELECT
    a.pid AS waiting_pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    now() - a.xact_start AS transaction_age
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY transaction_age DESC NULLS LAST;
~~~

`pg_blocking_pids` trả về các PID được hệ thống xem là blocker đối với backend được hỏi; mảng có thể chứa nhiều PID. `transaction_age` tính từ thời điểm bắt đầu transaction hiện hành, **không phải thời gian chờ lock chính xác**. Một transaction vừa bắt đầu chờ cũng có thể đã chạy lâu từ trước.

Nếu có rất nhiều dòng cùng chờ một PID, đó là dấu hiệu một session/transaction đang tạo **fan-in bottleneck**. Không tự `pg_terminate_backend` trong production khi chưa xác định nó đang giữ transaction nghiệp vụ gì và hậu quả rollback/side effect.

### 9.2. Đọc cả phía đang chặn

~~~sql
SELECT
    blocked.pid AS waiting_pid,
    blocked.application_name AS waiting_app,
    blocked.wait_event_type,
    blocked.wait_event,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    now() - blocker.xact_start AS blocker_transaction_age
FROM pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid))
    AS blocked_by(blocker_pid) ON TRUE
JOIN pg_stat_activity AS blocker
    ON blocker.pid = blocked_by.blocker_pid
WHERE blocked.datname = current_database()
ORDER BY blocker_transaction_age DESC NULLS LAST;
~~~

Hai tình huống thường gặp:

- **Blocker đang `idle in transaction`:** ứng dụng đã mở transaction, thực hiện SQL rồi chờ mạng/CPU/user input nhưng chưa commit. Cần sửa transaction lifetime.
- **Blocker đang `active`:** SQL có thể đang xử lý một write batch dài, chờ tài nguyên khác hoặc chạy trigger. Cần xem query plan, locks và workload thực.

### 9.3. Tổng hợp kiểu khóa (đọc để điều tra)

~~~sql
SELECT
    locktype,
    mode,
    granted,
    count(*) AS lock_count
FROM pg_locks
GROUP BY locktype, mode, granted
ORDER BY lock_count DESC;
~~~

`pg_locks` phản ánh nhiều loại khóa; **không phải tất cả row-level locks đều hiện dưới dạng mỗi row là một dòng dễ đọc**. Một worker chờ row đang bị transaction khác cập nhật có thể hiển thị wait trên `transactionid`. Hãy dùng `pg_blocking_pids`, SQL/transaction trace và thông tin khóa để xác định nguyên nhân, không chỉ đếm row locks trong view.

### 9.4. Metric và log ở PostgreSQL

- `wait_event_type` và `wait_event`: phân biệt chờ `Lock`, `IO`, `LWLock` hay loại khác.
- `pg_stat_statements` (nếu extension được cài đặt): tìm SQL có tổng thời gian/mean execution cao; **không tự cung cấp toàn bộ thời gian chờ lock theo business key**.
- `log_lock_waits` và `deadlock_timeout`: có thể ghi lại lock wait vượt ngưỡng để phục vụ điều tra. Việc bật/thay giá trị cần đánh giá chi phí log và quyền DBA.
- PostgreSQL log có thể ghi lỗi `deadlock detected` cùng chi tiết SQL/transaction; phải bảo vệ thông tin nhạy cảm trong log.
- `application_name` trên JDBC connection giúp phân biệt manager, worker pod và workload nhưng không nên chứa ID cá nhân/secret.

**Đừng bật `log_statement='all'` lâu dài chỉ để tìm lock:** log khổng lồ, overhead và nguy cơ lộ dữ liệu. Ưu tiên instrumentation có mục tiêu, trace/query fingerprints và một cửa sổ thu thập an toàn.

## 10. Index, unique constraint và foreign key cũng ảnh hưởng contention

Không phải cứ hai worker cập nhật **hai row khác nhau** là mọi wait biến mất.

### Unique key conflict

~~~sql
INSERT INTO processed_ledger_events
    (event_id, account_id, delta_cents, occurred_at)
VALUES (:eventId, :accountId, :deltaCents, :occurredAt)
ON CONFLICT (event_id) DO NOTHING;
~~~

Nếu hai worker cùng nhận một `event_id` do broker redelivery hoặc lỗi partition plan, unique index cần điều phối conflict. `DO NOTHING` làm insert lặp **không tạo thêm row**, nhưng transaction vẫn có thể **đợi** giao dịch khác quyết định commit/rollback trước khi biết xung đột có thật hay không. Đừng coi unique constraint là công cụ phân phối tải thay cho partition plan.

### Foreign key

Worker insert hàng con tham chiếu hàng cha. Nếu transaction khác đang xóa/sửa khóa hàng cha, việc kiểm tra FK có thể tạo lock wait. Quan sát loại khóa và SQL thực tế trước khi “tối ưu” bằng cách bỏ foreign key; bỏ ràng buộc có thể dẫn tới dữ liệu không nhất quán.

### Index và update pattern

- Mỗi `INSERT`/`UPDATE` có thể phải cập nhật nhiều index. **Index thừa** làm tăng chi phí write và bộ nhớ/buffer I/O.
- Một index duy nhất/hot key hoặc nhiều insert vào vùng khóa gần nhau có thể gây cạnh tranh ở tầng index/buffer, không nhất thiết hiển thị như row-lock wait.
- Bỏ mọi index để tăng write throughput thường không hợp lý: query, constraint và restart scan có thể chậm nghiêm trọng.
- Giảm số index bằng **dữ liệu đo được** và kiểm tra query read path, constraint, retention và migration.
- Với PostgreSQL physical table partitioning, partition pruning và index theo partition có thể giảm một số phạm vi I/O, nhưng **không tự giải quyết** nhiều worker ghi vào cùng một logical account row.

Nếu `pg_stat_activity` không cho thấy `Lock` wait mà throughput vẫn không tăng, cần xem CPU, I/O, `LWLock`, WAL flush, checkpoint pressure, vacuum và connection pool. Không quy mọi chậm trễ ghi về row-lock contention.

## 11. Khi nào SELECT FOR UPDATE hoặc optimistic locking phù hợp?

### Pessimistic locking

`SELECT ... FOR UPDATE` giúp transaction **giữ quyền cập nhật row** từ lúc kiểm tra điều kiện đến khi ghi kết quả:

~~~sql
BEGIN;
SELECT balance_cents
FROM account_balances
WHERE account_id = :accountId
FOR UPDATE;

-- Kiểm tra nghiệp vụ rồi ghi trong cùng transaction.
UPDATE account_balances
SET balance_cents = :newBalance
WHERE account_id = :accountId;
COMMIT;
~~~

Phù hợp khi việc kiểm tra và ghi phải được bảo vệ bằng lock trong một transaction. Nhưng nó **chủ động tăng thời gian giữ row lock** và có thể làm contention nặng hơn nếu dùng quá rộng. Nếu chỉ muốn cộng một số nguyên, câu SQL `SET balance_cents = balance_cents + :delta` thường đơn giản hơn.

### Optimistic locking

Một bảng có thể có `version`:

~~~sql
ALTER TABLE account_balances
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;

-- Ghi dựa trên version vừa đọc:
UPDATE account_balances
SET balance_cents = :newBalance,
    version = version + 1
WHERE account_id = :accountId
  AND version = :expectedVersion;
~~~

Nếu update count bằng 0, có thể đã có transaction khác cập nhật row; code cần **đọc lại state và quyết định retry/merge**. Đây là optimistic conflict detection, không phải cách loại bỏ mọi row lock. Với một hot row bị 100 worker sửa liên tục, optimistic retries có thể tiêu tốn nhiều công sức mà không tăng throughput.

**Lưu ý:** `ALTER TABLE` chỉ là minh họa schema, không chạy bừa trên một bảng đang có constraint/ORM mapping khác. Spring Data/JPA `@Version` có semantics riêng; với Spring Batch JDBC writer, phải tự xử lý update count/version conflict.

### Isolation level

- PostgreSQL `READ COMMITTED` thường là mức mặc định và có hành vi chờ row update tương ứng.
- `REPEATABLE READ` và `SERIALIZABLE` có thể báo **serialization failure** thay vì âm thầm cho phép lịch ghi không nhất quán; ứng dụng phải retry transaction theo policy.
- Tăng isolation lên `SERIALIZABLE` **không phải** giải pháp chung cho mọi contention; số rollback/retry và chi phí có thể tăng.
- Không hạ isolation chỉ để “hết lock” nếu có thể phá business invariants như số dư không âm hay tính duy nhất.

Chọn locking/isolation dựa trên **invariant nghiệp vụ** và test cạnh tranh thực tế.

## 12. SKIP LOCKED: rất hữu ích cho queue, nguy hiểm cho batch đối soát

PostgreSQL hỗ trợ `FOR UPDATE SKIP LOCKED` để những worker khác **bỏ qua các hàng đang bị khóa** thay vì chờ. Nó thích hợp cho **work queue** có khái niệm claim/retry, nhưng không phù hợp để âm thầm bỏ record trong một job cần đối soát đủ 100% tập dữ liệu.

### Claim các tác vụ chưa được worker khác giữ

Ví dụ queue table:

~~~sql
CREATE TABLE batch_work_queue (
    id BIGINT PRIMARY KEY,
    state TEXT NOT NULL,
    owner_id TEXT,
    lease_until TIMESTAMPTZ
);
~~~

Một transaction chọn và claim hàng chưa xử lý:

~~~sql
WITH picked AS (
    SELECT id
    FROM batch_work_queue
    WHERE state = 'READY'
    ORDER BY id
    LIMIT :claimLimit
    FOR UPDATE SKIP LOCKED
)
UPDATE batch_work_queue AS q
SET state = 'CLAIMED',
    owner_id = :workerId,
    lease_until = now() + INTERVAL '10 minutes'
FROM picked AS p
WHERE q.id = p.id
RETURNING q.id;
~~~

Ở đây `SKIP LOCKED` là **một chiến lược xếp việc**: worker khác có thể lấy task khác. Nhưng còn cần thiết kế:

1. Claim/lease được commit; trạng thái `CLAIMED` tồn tại qua worker crash.
2. Có logic xử lý lease hết hạn và reclaim các task chưa hoàn tất.
3. Worker cũ có thể vẫn sống khi lease hết hạn, vì vậy cần **fencing/claim token** hoặc idempotency khi ghi output.
4. Có giới hạn retry và poison message/task; không biến job thành vòng lặp không bao giờ kết thúc.
5. Monitoring phải bảo đảm không có task `READY/CLAIMED` bị bỏ quên mãi.

**Không thay một truy vấn đối soát “đọc đủ mọi row của ngày” bằng `SKIP LOCKED` rồi tuyên bố job `COMPLETED`:** một row bị khóa tại thời điểm query sẽ bị bỏ qua, có thể không được quay lại, dẫn tới dữ liệu thiếu.

### NOWAIT và lock timeout

`FOR UPDATE NOWAIT` báo lỗi ngay khi không lấy được khóa; `lock_timeout` giới hạn thời gian chờ khóa, còn `statement_timeout` giới hạn thời gian thực thi statement. Đây là **cơ chế kiểm soát lỗi/latency**, không phải cách tăng khả năng cập nhật một hot row.

Ví dụ chỉ chạy trong **transaction có chủ đích**:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';
-- Thực thi câu SQL cần bảo vệ thời gian chờ trong transaction này.
COMMIT;
~~~

`SET LOCAL` áp dụng trong phạm vi transaction hiện tại; không thay cấu hình timeout global của DB mà không có review DBA. Khi bị timeout, cần xử lý transaction failure/rollback và đối soát side effects trước khi retry.

## 13. Spring Batch chunk retry: khôi phục đúng ranh giới transaction

Nếu worker gặp deadlock, PostgreSQL có thể rollback transaction và trả SQLSTATE **`40P01`**. Với `SERIALIZABLE`/`REPEATABLE READ`, xung đột có thể trả **`40001`**. Retry có thể hợp lý, nhưng chỉ khi **toàn đơn vị transaction** được chạy lại an toàn.

| SQLSTATE (PostgreSQL) | Ví dụ ý nghĩa | Có nên retry? |
|---|---|---|
| `40P01` | Deadlock detected | Thường retry toàn transaction có giới hạn, có backoff/jitter |
| `40001` | Serialization failure | Thường retry toàn transaction theo policy |
| `55P03` | Lock not available, NOWAIT/lock timeout | Tùy SLA và loại lock; không retry vô hạn |
| `57014` | Query canceled, có thể do `statement_timeout` | Cần phân biệt timeout/huỷ chủ động, xem side effect |
| `23505` | Unique constraint violation | Thường là lỗi dữ liệu/logic trừ khi duplicate thuộc idempotency contract |
| `08xxx` | Connection exception | Có thể không biết commit trước đó đã xảy ra chưa; cần reconciliation/idempotency |

Trong Spring Batch 5.2.x, một chunk-oriented step có thể dùng fault-tolerant builder:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.transaction.PlatformTransactionManager;

// Trong một class @Configuration; LedgerEvent là record ở phần trước.
@Bean
public Step ledgerWorkerStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<LedgerEvent> reader,
        JdbcBatchItemWriter<LedgerEvent> ledgerWriter) {

    return new StepBuilder("ledgerWorkerStep", repository)
            .<LedgerEvent, LedgerEvent>chunk(200, transactionManager)
            .reader(reader)
            .writer(ledgerWriter)
            .faultTolerant()
            .retry(PessimisticLockingFailureException.class)
            .retryLimit(3)
            .build();
}
~~~

Đây là **cấu hình minh họa**: các exception do JDBC/transaction manager dịch từ SQLSTATE có thể khác theo driver và Spring version, và `PessimisticLockingFailureException` không bao phủ mọi `40001` hoặc timeout. Phải kiểm tra exception translation thực tế rồi chọn **retryable classification** phù hợp. Với SQL deadlock, có thể cần cấu hình bounded backoff/jitter theo stack đang dùng để tránh nhiều worker retry đồng loạt.

Không đặt vòng `while(retry)` ngay trong JDBC writer **sau khi PostgreSQL đã đánh dấu transaction là aborted**: transaction lỗi phải rollback trước khi thực thi lại. Retry nên ở boundary framework/transaction thích hợp, có giới hạn, và tránh gọi side effect ngoài transaction trong vòng thử lại.

### Retry không thay thế idempotency

Một chunk có thể đã:

~~~text
1. Commit kết quả nghiệp vụ vào database
2. Mất kết nối trước khi manager nhìn thấy metadata hoàn tất
3. Broker redeliver request / job được restart
4. Các item được xử lý lại
~~~

Nếu writer chỉ làm `balance = balance + delta` mà không có event ID guard, số dư có thể bị cộng hai lần. `JobRepository` giúp checkpoint nhưng không đảm bảo exactly-once qua **business DB + metadata DB + broker** trong mọi cấu hình. Dùng unique business key, ledger/outbox và kiểm tra exact execution status trước khi phát lại.

## 14. Connection pool và lock contention tạo vòng khuếch đại

~~~mermaid
flowchart TB
    A[Thêm worker/partition] --> B[Nhiều transaction chạm hot key]
    B --> C[Lock wait lâu]
    C --> D[Connection bị giữ lâu]
    D --> E[Hikari pool pending / timeout]
    E --> F[Chunk rollback, retry hoặc restart]
    F --> B
~~~

Khi một worker đợi lock, nó vẫn có thể giữ JDBC connection. Nếu hàng chục worker cùng đợi, Hikari pool cạn và **những transaction không hề chạm hot key** cũng có thể bị timeout vì không mượn được connection.

### Sizing cần đo theo thực tế

Nếu có `N` worker pods, mỗi pod tối đa `C` execution hoạt động và business pool max `P`:

\[
T_{\mathrm{active}}\le N\times C
\]

\[
\mathrm{ConnectionCapacity}_{\mathrm{workers}}\le N\times P
\]

Hai đại lượng trên **khác nhau**. Một execution có thể dùng nhiều hoặc không dùng connection trong một số pha; Hikari `maximumPoolSize` là trần của một pool, không phải số connection active.

Với 8 worker pod và mỗi pod 4 execution, có thể có tối đa 32 execution hoạt động. Nhưng nếu 90% transaction đều muốn cập nhật cùng một row, **tài nguyên giới hạn là hàng khóa**, không phải số CPU cores hoặc connection pool.

### Ước lượng giới hạn của một hot key

Nếu mỗi transaction giữ lock trên cùng row trong trung bình `t_{\mathrm{hold}}` giây, giới hạn lý tưởng do việc truy cập tuần tự vào row đó xấp xỉ:

\[
\mathrm{HotKeyThroughput}\lesssim \frac{1}{t_{\mathrm{hold}}}
\]

Đây là **ước lượng định tính trong một kịch bản đơn giản**, không phải dự báo SLA: thời gian khóa thực phân phối không đều, có overhead lập lịch, WAL, commit, network, retry và các khóa khác. Tuy nhiên nó chỉ ra lý do tăng từ 4 lên 64 worker **không làm một row được cập nhật đồng thời 64 lần**.

### Hãy đo pool và lock trên cùng khoảng thời gian

| Metric | Khi contention tăng thường thấy |
|---|---|
| PostgreSQL `wait_event_type='Lock'` | Nhiều session chờ khóa |
| Blocking PID fan-in | Một/few transactions chặn nhiều worker |
| Transaction p95/p99 duration | Tăng do chờ lock hoặc giữ lock quá lâu |
| Hikari `active` | Có thể tăng sát max |
| Hikari `pending`/acquire p95 | Tăng khi nhiều connection bị giữ |
| Worker CPU utilization | Có thể thấp, vì thread chờ |
| Rollback/timeout/retry | Tăng nếu áp retry thiếu kiểm soát |
| Business throughput | Đứng yên hoặc giảm dù worker count tăng |

Nếu `wait_event_type` chủ yếu là `IO`/`LWLock`, CPU hoặc network, không nên khẳng định **row-lock contention** là nguyên nhân. Điều chỉnh phải dựa vào blocker evidence.

## 15. Benchmark: so sánh concurrency với cùng snapshot

Giữ nguyên **input snapshot, dữ liệu account, transaction isolation, chunk size, SQL/index và DB capacity** khi thay đổi số worker. Chạy các mức 1, 2, 4, 8, 16; sau đó thay từng yếu tố nếu cần.

| Lần thử | Worker đồng thời | Phép đo trọng tâm | Câu hỏi |
|---|---:|---|---|
| A | 1 | Throughput và transaction duration gốc | Có khóa nào nóng ngay ở mức thấp? |
| B | 2 | Lock wait, speedup | Worker mới có giúp hay chỉ thêm queue lock? |
| C | 4 | Hikari active/pending, DB CPU/IO | Bottleneck chuyển từ CPU sang DB chưa? |
| D | 8 | p95/p99 lock wait, deadlocks, retry | Có bắt đầu giảm throughput không? |
| E | 16 | Total time, failed chunks, output set | Tăng concurrency có còn hợp lý? |

**Không điền các số liệu giả thành benchmark thực.** Trong báo cáo phải ghi rõ database engine/version, query plan, workload skew, pool max, giới hạn CPU/IO và số transaction đang chạy.

### Hai workload để so sánh

1. **Uniform keys:** 1 triệu event phân bố gần đều trên rất nhiều account. Các worker chạm nhiều row khác nhau.
2. **Skewed/hot keys:** 90% event liên quan đến một nhóm account nhỏ; các worker tranh cùng row.

Nếu throughput gần tuyến tính trong workload uniform nhưng nhanh chóng bão hòa ở workload skewed, đây là bằng chứng mạnh rằng **write-key distribution** là yếu tố chính; cần đổi partition/write architecture, không chỉ scale database connection.

### Các bất biến về tính đúng

- Mỗi `event_id` có tối đa một hiệu ứng nghiệp vụ đã commit.
- Tổng số dư thay đổi tương ứng với tổng delta của các event hợp lệ **đã chấp nhận**.
- Không có record bị bỏ quên sau `SKIP LOCKED` hoặc lease expiry.
- Không có hai worker cùng commit cùng một partition logic ngoài chính sách idempotency.
- Sau crash/restart, **tập event IDs và checksum** đúng, không chỉ `writeCount`.

Một job báo `COMPLETED` và đếm đúng số event vẫn có thể sai nếu một event được cộng hai lần và event khác bị bỏ sót.

## 16. Runbook khi production bắt đầu chờ khóa

### Bước 1 — Khoanh vùng thời điểm và thay đổi gần nhất

Ghi job name, `jobExecutionId`, `stepExecutionId`, số worker pods, concurrency, pool max, chunk size, SQL và schema deploy version. Xác định sự cố có bắt đầu ngay sau khi tăng replica, đổi index, chuyển từ insert sang upsert hoặc tăng chunk hay không.

### Bước 2 — Phân biệt lock wait với pool timeout

Đo Hikari active/idle/pending/acquire time cùng PostgreSQL `pg_stat_activity` và `pg_blocking_pids`. Nếu pool pending cao nhưng DB không có blocker đáng kể, kiểm tra connection leak, long transaction, network wait và cursor hold.

### Bước 3 — Tìm hot keys và blocking transaction

Từ blocking PID, truy application name, transaction age, SQL fingerprint, log `stepExecutionId` và business key đã được băm/ẩn dữ liệu nhạy cảm. Phân biệt một blocker `idle in transaction` với một query update đang chạy hợp lệ.

### Bước 4 — Xem lock ordering và schema constraints

Nếu deadlock xảy ra giữa hai hoặc nhiều row, xem các path có khóa trái thứ tự không. Nếu conflict tại unique key, kiểm tra duplicate dispatch/business ID. Nếu FK wait, xem transaction thao tác row cha. Không xóa constraint để chữa triệu chứng mà chưa xét tính đúng.

### Bước 5 — Giảm tải có kiểm soát

Giảm consumer concurrency/partition active hoặc tạm dừng producer để ngắt retry storm. Đừng kill bừa blocking backend; rollback có thể ảnh hưởng business data và làm lại quá nhiều chunk.

### Bước 6 — Chọn giải pháp dài hạn theo nguyên nhân

- Một account row rất nóng → ownership theo account, append-only event rồi aggregate, hoặc thiết kế partial aggregation.
- Transaction giữ row lock qua HTTP → rút ngắn transaction, outbox.
- Deadlock hai account → lock theo thứ tự xác định và retry transaction có giới hạn.
- Duplicate event/unique conflict → sửa partition/delivery contract và áp idempotency.
- Pool pending do lock → giải quyết blocker/hold time trước khi tăng `maximumPoolSize`.
- DB IO/index hot → xem execution plan, index write cost và schema design.

### Bước 7 — Restart và đối soát

Xác định worker cũ còn sống hay không, dùng `JobRepository` để kiểm tra checkpoint và trạng thái partition. Restart với cùng identifying `JobParameters` và input/partition plan ổn định, writer idempotent. So sánh tập khóa business, aggregate checksum và trạng thái downstream; không sửa bảng metadata trực tiếp bằng SQL để “ép” job hoàn tất.

### Bước 8 — Ghi nhận kết quả và bảo vệ deploy sau

Lưu biểu đồ lock wait, blocker fan-in, Hikari pending, commit duration và throughput trước/sau thay đổi. Đặt ngưỡng cảnh báo theo baseline, update runbook và quy tắc scale để tránh một autoscaler vô tình nhân contention lên nhiều lần.

## 17. Ma trận kiểm thử concurrency và failure

| Kịch bản | Cách tạo | Tiêu chí đạt |
|---|---|---|
| Hai worker cùng cập nhật một row | Giữ transaction A mở; cho B update cùng account | B chờ theo hợp đồng, không lost update |
| Lost update | Hai thread đọc giá trị cũ rồi ghi đè | Test phát hiện sai; sửa bằng atomic update/version |
| Deadlock đảo thứ tự | A lock row 10→20; B lock row 20→10 | DB phát hiện deadlock; có rollback/retry giới hạn |
| Thứ tự khóa xác định | Hai transfer ngược chiều đều lock tăng dần | Không còn chu trình do lock inversion của hai path đó |
| Unique conflict | Gửi hai event có cùng `event_id` | Không cộng delta hai lần |
| Duplicate ID khác payload | Cùng ID, delta khác | Báo vi phạm contract/checksum, không âm thầm bỏ |
| Hot row | Phần lớn event ghi một account | Đo throughput bão hòa, lock wait tăng khi thêm worker |
| Uniform rows | Event rải trên nhiều account | So sánh speedup với hot-key workload |
| `SKIP LOCKED` queue | Nhiều consumer claim cùng queue | Không claim trùng; task hết lease có recovery |
| `SKIP LOCKED` trong reconciliation | Một row bị khóa | Test bắt được nguy cơ bỏ sót, không dùng skip để đánh dấu COMPLETED |
| Pool starvation | Nhiều worker đợi hot row | Phân biệt lock wait với Hikari acquisition timeout |
| Worker crash sau commit | Kill worker trước ACK/metadata thấy xong | Restart không cộng trùng event |
| Metadata/business DB outage | Ngắt một tài nguyên giữa chunk | Side effects được đối soát, không giả định distributed atomicity |
| Serializable conflict | Chạy transaction cạnh tranh ở isolation cao | Nhận biết `40001` và retry đúng boundary |
| Benchmark 1/2/4/8/16 | Cùng immutable snapshot | Báo throughput, waits và kiểm chứng dữ liệu đúng |

**Lưu ý thử nghiệm:** chủ động tạo deadlock hoặc giữ row lock trên môi trường staging có dữ liệu giả. Không thực hiện fault injection và `pg_terminate_backend` trên production nếu chưa có change approval và kế hoạch rollback thích hợp.

## 18. Checklist trước production

- [ ] Đã phân biệt **partition input** và **write set/key ownership**.
- [ ] Có số liệu hot keys, lock wait, blocker PID, transaction duration và throughput.
- [ ] Không dùng nhiều worker cùng ghi hot aggregate row mà không đo contention.
- [ ] Các SQL cập nhật counter dùng atomic update hoặc version/lock phù hợp.
- [ ] Khi cập nhật nhiều row, thứ tự lock thống nhất giữa các code path.
- [ ] Transaction ngắn; không giữ khóa trong lúc chờ HTTP/API hoặc tài nguyên ngoài DB.
- [ ] Chunk size/concurrency được benchmark; không đồng nhất `gridSize` với số worker active.
- [ ] Không mở rộng pool chỉ vì lock wait khiến active cao.
- [ ] Writer dùng business key/idempotency; `ON CONFLICT DO NOTHING` không che lỗi payload sai.
- [ ] Có chính sách rollback/retry có giới hạn cho `40P01` và `40001` theo exception thực.
- [ ] `SKIP LOCKED` chỉ dùng cho bài toán queue/claim có recovery, không dùng bỏ qua dữ liệu bắt buộc.
- [ ] Index/FK/unique constraint được rà soát theo cả read lẫn write workload.
- [ ] Có instrumentation `pg_stat_activity`, `pg_blocking_pids`, Hikari và `StepExecution`.
- [ ] Job restart dùng cùng identifying parameters, partition plan và immutable snapshot.
- [ ] Remote worker redelivery và các side effects ngoài transaction được xử lý idempotent.
- [ ] Kiểm thử fail giữa chunk và đối soát **tập ID nghiệp vụ**, không chỉ tổng số item.

## 19. Bài tập thực hành

### Bài tập 1 — Tạo contention có kiểm soát

Trên PostgreSQL staging, tạo bảng `account_balances` với account 42. Mở hai session như phần 3: A cập nhật mà chưa commit, B cập nhật cùng row. Dùng `pg_blocking_pids` để xác định blocker, sau đó commit A và xác minh số dư cuối đúng. Đo transaction duration trước và sau khi thay thời gian giữ khóa.

### Bài tập 2 — Phân biệt lock wait và deadlock

Với hai account 10 và 20, tạo hai transaction khóa theo thứ tự ngược nhau rồi quan sát SQLSTATE `40P01` trong staging. Sửa chương trình để cả hai khóa tăng dần `account_id`. Giải thích vì sao quy ước này giảm deadlock nhưng không loại bỏ mọi lock wait.

### Bài tập 3 — Thiết kế partition theo khóa ghi

Một job chia event theo 24 cửa sổ giờ nhưng 70% event thuộc 5 account. Thiết kế lại plan thành hash bucket theo `account_id`, nêu cách giữ bucket count ổn định qua restart và cách xử lý account quá lớn gây partition skew. So sánh với phương án immutable ledger rồi aggregate.

### Bài tập 4 — Chứng minh idempotency

Chạy writer CTE `INSERT ... ON CONFLICT DO NOTHING ... UPDATE` với cùng `event_id` hai lần; kiểm tra `processed_ledger_events` và `balance_cents`. Sau đó cho cùng event ID nhưng `delta_cents` khác, thiết kế cơ chế phát hiện dữ liệu sai thay vì coi là duplicate hợp lệ.

### Bài tập 5 — SKIP LOCKED đúng mục đích

Xây work queue dùng `FOR UPDATE SKIP LOCKED` và hai worker. Cho một worker claim rồi bị kill. Thiết kế lease, expiry reclaim và fencing/idempotency để worker cũ không thể ghi kết quả sau khi claim thuộc worker mới. Giải thích vì sao query này không dùng cho full reconciliation.

### Bài tập 6 — Tối ưu transaction/chunk

Chạy một job với `chunk(50)`, `chunk(200)` và `chunk(1000)` trên cùng snapshot. Thu lock wait p95, transaction duration, DB pool pending, rollback/retry, throughput và output checksum. Đánh giá mức chunk nào tối ưu **với dữ liệu và mức concurrency đó**, không suy rộng thành số mặc định toàn hệ thống.

### Bài tập 7 — Runbook sự cố thực tế

Sau khi tăng worker từ 4 lên 16, DB ghi nhận nhiều `wait_event_type='Lock'` và Hikari acquisition timeout. Viết runbook gồm thứ tự kiểm tra blocker, hot keys, transaction hold time, connection pool, giảm concurrency, sửa partitioning/write design, restart an toàn và đối soát khóa nghiệp vụ.

**Câu hỏi tự kiểm tra:** Vì sao MVCC không loại bỏ row locks khi UPDATE? Vì sao partition theo thời gian không ngăn hai worker ghi cùng aggregate row? Deadlock khác lock wait một chiều thế nào? Tại sao `ON CONFLICT DO NOTHING` vẫn có thể chờ? Khi nào `SELECT FOR UPDATE` hợp lý và khi nào chỉ làm tệ thêm contention? Vì sao `SKIP LOCKED` phù hợp cho work queue nhưng không an toàn cho full reconciliation? Vì sao retry phải quay lại boundary transaction và cần idempotency? Tại sao tăng `maximumPoolSize` có thể làm lock contention nặng hơn?

## 20. Tổng kết

**Lock contention khi ghi** là một trong những giới hạn chính của Spring Batch khi tăng thread, partition và worker pod. Dữ liệu đầu vào có thể được chia hoàn hảo, nhưng nếu nhiều execution cùng sửa một business key, database vẫn phải phối hợp khóa, làm tăng transaction duration, giữ JDBC connection lâu và có thể gây deadlock/retry storm.

Để scale bền vững, cần **đo blocker và hot keys, giảm thời gian giữ transaction, khóa theo thứ tự xác định, ưu tiên atomic SQL/idempotent writer, cân nhắc write ownership theo business key hoặc immutable events + aggregation, và dùng `SKIP LOCKED` đúng phạm vi queue**. Benchmark phải kiểm tra đồng thời throughput, lock wait, pool pressure và **tính đúng trên từng business key sau retry/restart**. Mục tiêu không phải là có nhiều worker nhất, mà là đạt thông lượng ổn định với dữ liệu chính xác và khả năng khôi phục có thể kiểm chứng.
