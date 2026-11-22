# Lỗi batch, số hàng bị tác động và khả năng đối soát

**Ghi hàng loạt (batch writing)** giúp giảm số lần trao đổi với cơ sở dữ liệu khi ứng dụng Java/Hibernate phải tạo, sửa hoặc xóa nhiều bản ghi. Nhưng khi một lệnh lỗi, driver báo số hàng tác động không xác định, hoặc kết nối mất đúng lúc commit, điều khó nhất không phải gọi lại phương thức ghi. Vấn đề là phải xác định **những thay đổi nào đã thực sự commit**, những item nào cần thử lại và làm sao tránh tạo bản ghi trùng.

Bài học thuộc chương **Ghi hàng loạt**, tập trung vào ba năng lực:

1. **Hiểu lỗi batch và JDBC update counts:** `BatchUpdateException`, `Statement.SUCCESS_NO_INFO`, `Statement.EXECUTE_FAILED`, optimistic locking và sự khác biệt giữa flush với commit.
2. **Thiết kế ranh giới transaction và retry:** chunking, rollback, error isolation, idempotency và xử lý trạng thái chưa rõ kết quả commit.
3. **Đối soát (reconciliation):** so input với target bằng business key, payload hash, ledger, aggregates và trạng thái outbox, thay vì chỉ đếm tổng số SQL statements.

Nguyên tắc xuyên suốt: **số hàng được driver báo tác động không đồng nghĩa với số business items đã được commit thành công.**

## 1. Ba cơ chế thường đều được gọi là batch

| Cơ chế | Ví dụ | Bản chất | Kết quả |
| --- | --- | --- | --- |
| Hibernate entity batching | Nhiều `persist()` rồi `flush()` | Hibernate gom các SQL actions tương thích thành JDBC batches | Không trả count riêng cho từng `persist()` |
| JDBC batching trực tiếp | `addBatch()` rồi `executeBatch()` | Driver thực thi các lần chạy cùng statement | `int[]` hoặc `long[]` update counts |
| Bulk HQL/JPQL | `update Entity ... where ...` và `executeUpdate()` | Một lệnh bulk có thể ảnh hưởng nhiều entities | Một số nguyên theo semantics bulk ORM |

Ví dụ Hibernate:

~~~java
for (ImportRecord item : items) {
    entityManager.persist(ImportedOrder.from(item));
}
entityManager.flush();
~~~

JDBC:

~~~java
for (ImportRecord item : items) {
    ps.setString(1, item.sourceKey());
    ps.setBigDecimal(2, item.amount());
    ps.addBatch();
}
int[] updateCounts = ps.executeBatch();
~~~

Bulk HQL:

~~~java
int affectedEntities = entityManager.createQuery("""
    update PurchaseOrder o
    set o.status = :completed
    where o.status = :paid
    """)
    .setParameter("completed", OrderStatus.COMPLETED)
    .setParameter("paid", OrderStatus.PAID)
    .executeUpdate();
~~~

**Không suy luận counts[i] của JDBC là trạng thái item[i] của Hibernate.** Hibernate có thể sắp xếp, nhóm hoặc tạo nhiều câu SQL cho một entity. Số do bulk HQL trả về cũng không nhất thiết là tổng số hàng vật lý ở mọi bảng.

### 1.1. Batch không phải transaction

Batch là cách gom việc gửi SQL; transaction quyết định atomicity và commit/rollback.

~~~text
Job 10.000 bản ghi
├── Chunk 1: Transaction T1
│   ├── JDBC batch A
│   └── JDBC batch B
├── Chunk 2: Transaction T2
│   ├── JDBC batch C
│   └── JDBC batch D
└── ...
~~~

Nếu T2 rollback, mọi SQL trong T2 có thể đã chạy nhưng không trở thành thay đổi bền vững. Nếu T1 đã commit thì những dữ liệu đó không tự rollback theo T2.

### 1.2. Batch thành công không có nghĩa toàn job thành công

Một job có thể đã commit 18 chunks, còn chunk 19 thất bại. Cần định nghĩa rõ hợp đồng:

- **All-or-nothing:** toàn bộ dữ liệu phải commit như một đơn vị nghiệp vụ.
- **Partial acceptance:** mỗi chunk/item được xác nhận độc lập; lỗi được báo rõ.
- **Eventual processing:** target đã ghi nhưng các tác vụ downstream vẫn đang chờ.

Không chọn partial acceptance chỉ vì muốn tăng throughput khi nghiệp vụ đòi atomicity.

## 2. Những thời điểm có thể xảy ra lỗi

~~~mermaid
flowchart TD
    A["Nhận và validate input"] --> B["Chuẩn hóa business key"]
    B --> C["Mở transaction"]
    C --> D["Persist hoặc update entities"]
    D --> E["Flush và JDBC executeBatch"]
    E --> F{"SQL thành công?"}
    F -->|"Không"| G["Rollback + phân loại lỗi"]
    F -->|"Có"| H["Commit"]
    H --> I{"Commit outcome rõ?"}
    I -->|"Có"| J["Xác nhận COMMITTED"]
    I -->|"Chưa rõ"| K["UNKNOWN + reconciliation"]
    G --> L["Retry mới hoặc permanent failure"]
    K --> L
    J --> M["Đối soát toàn job"]
~~~

Lỗi có thể xảy ra ở:

- Validation, trước khi gửi SQL.
- `flush()`: UNIQUE, FK, NOT NULL, CHECK constraint, optimistic locking.
- `executeBatch()`: driver ném `BatchUpdateException`.
- `commit()`: deferred constraint, serialization failure hoặc lỗi transaction khác.
- Đường truyền xác nhận commit: server đã commit nhưng client không nhận được response.
- Sau commit: process crash trước khi cập nhật ledger hoặc phát event.

Vì vậy **một exception không tự cho biết database hiện giữ những row nào**.

## 3. JDBC update counts: số thường và giá trị đặc biệt

JDBC `Statement.executeBatch()` trả `int[]`. `executeLargeBatch()` có thể trả `long[]` khi số đếm lớn.

Ví dụ:

~~~java
try (PreparedStatement ps = connection.prepareStatement("""
    update inventory
       set available = available - ?
     where sku = ?
       and available >= ?
    """)) {

    for (Reservation r : requests) {
        ps.setInt(1, r.quantity());
        ps.setString(2, r.sku());
        ps.setInt(3, r.quantity());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

Các giá trị trong mảng:

| Giá trị | Hằng JDBC | Ý nghĩa |
| --- | --- | --- |
| `0` | — | Driver báo statement không tác động hàng nào |
| Số dương | — | Driver biết số hàng bị tác động |
| `-2` | `Statement.SUCCESS_NO_INFO` | Statement thành công nhưng không biết số hàng chính xác |
| `-3` | `Statement.EXECUTE_FAILED` | Statement thất bại khi driver tiếp tục báo trạng thái từng lệnh |

Ví dụ:

~~~text
Lần addBatch:        A   B   C   D
getUpdateCounts():   1   1  -2   1
~~~

Không được cộng -2 như số hàng âm hoặc coi là lỗi. Nó có nghĩa **success, no exact count**.

Một mảng khác:

~~~text
Lần addBatch:        A   B   C   D
getUpdateCounts():   1   0  -3   1
~~~

`0` có thể là UPDATE hợp lệ nhưng WHERE không khớp row. `-3` báo statement lỗi theo driver. Tuy nhiên, các statement được báo thành công vẫn có thể rollback cùng transaction.

### 3.1. BatchUpdateException

Khi một batch bị lỗi, JDBC có thể ném:

~~~java
java.sql.BatchUpdateException
~~~

Ví dụ diagnostic:

~~~java
catch (BatchUpdateException ex) {
    int[] counts = ex.getUpdateCounts();
    String sqlState = ex.getSQLState();
    int vendorCode = ex.getErrorCode();
    SQLException chained = ex.getNextException();

    // Ghi nhận có kiểm soát; counts KHÔNG phải commit receipt.
}
~~~

Driver có thể:

- **Dừng ngay:** mảng counts chỉ chứa kết quả của các lệnh trước điểm lỗi.
- **Tiếp tục:** mảng có thể phản ánh nhiều hoặc tất cả vị trí, dùng `EXECUTE_FAILED` cho những statement lỗi.

Không giả định mọi driver đều trả mảng đủ chiều dài hoặc có cùng chính sách dừng/tiếp tục.

### 3.2. Counts không phải danh sách item đã commit

Ngay cả khi counts là `[1,1,1]`:

- Transaction sau đó có thể rollback.
- Database có thể phát hiện deferred constraint lúc commit.
- Connection có thể mất khi gửi COMMIT, khiến outcome chưa rõ.
- Một business item có thể chạm nhiều database rows.
- Một SQL statement có thể ảnh hưởng nhiều rows.

Vì vậy:

~~~text
JDBC statement success ≠ transaction committed
Physical rows affected  ≠ successful business items
~~~

## 4. Ví dụ plain JDBC với ranh giới commit rõ ràng

~~~java
import javax.sql.DataSource;
import java.sql.*;
import java.util.List;

public final class InventoryBatchWriter {

    private final DataSource dataSource;

    public InventoryBatchWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int[] apply(List<Reservation> requests)
            throws SQLException {

        try (Connection c = dataSource.getConnection()) {
            boolean previousAutoCommit = c.getAutoCommit();
            SQLException failure = null;

            try {
                c.setAutoCommit(false);
                int[] counts;

                try (PreparedStatement ps =
                        c.prepareStatement("""
                            update inventory
                               set available = available - ?
                             where sku = ?
                               and available >= ?
                            """)) {

                    for (Reservation r : requests) {
                        ps.setInt(1, r.quantity());
                        ps.setString(2, r.sku());
                        ps.setInt(3, r.quantity());
                        ps.addBatch();
                    }

                    counts = ps.executeBatch();
                }

                // Contract ví dụ: reservation phải update đúng một row.
                for (int count : counts) {
                    if (count == 0 ||
                        count == Statement.EXECUTE_FAILED) {
                        throw new SQLException(
                            "Reservation không thành công");
                    }
                }

                // SUCCESS_NO_INFO không chứng minh được count=1.
                // Nếu business contract đòi exact count,
                // cần thêm bước xác minh hoặc đổi strategy.

                c.commit();
                return counts;

            } catch (SQLException ex) {
                failure = ex;
                if (ex instanceof BatchUpdateException batchEx) {
                    int[] partial = batchEx.getUpdateCounts();
                    // Chỉ ghi diagnostic, không suy ra committed items.
                }
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;

            } finally {
                try {
                    c.setAutoCommit(previousAutoCommit);
                } catch (SQLException restorationFailure) {
                    if (failure != null) {
                        failure.addSuppressed(restorationFailure);
                    } else {
                        throw restorationFailure;
                    }
                }
            }
        }
    }
}
~~~

~~~java
public record Reservation(String sku, int quantity) {}
~~~

Đây là ví dụ cho **plain JDBC transaction**. Khi dùng Spring `@Transactional` hoặc JTA, transaction manager sở hữu connection và commit; không tự `setAutoCommit()` hoặc `commit()` trên connection do framework quản lý.

Điểm chính:

- `executeBatch()` không phải `commit()`.
- `count=0` được coi là business failure trong bài toán đặt trước tồn kho, nhưng ở use case khác có thể là no-op hợp lệ.
- `SUCCESS_NO_INFO` là thành công không biết exact count; ứng dụng không được giả định nó bằng 1.
- Rollback cần được thực hiện sau SQL failure.
- Một commit timeout vẫn có thể tạo outcome UNKNOWN, cần đối soát.

## 5. Hibernate batching và cấu hình

Ví dụ Spring Boot:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
~~~

`hibernate.jdbc.batch_size` quyết định mức gom các JDBC statements phù hợp. Nó **không phải** kích thước transaction/chunk.

`hibernate.order_inserts` và `hibernate.order_updates` có thể nhóm/sắp các actions theo statement shape, tăng cơ hội batching. Đổi lại, thứ tự SQL thực tế có thể khác thứ tự input, và tính toán ordering cũng có chi phí.

Ví dụ:

~~~java
for (ImportRecord item : records) {
    em.persist(ImportedOrder.from(item));
}
em.flush();
~~~

Hibernate có thể:

- Tạo nhiều SQL cho một entity có secondary tables/inheritance.
- Chạy INSERT vào join tables do associations.
- Gom các INSERT/UPDATE tương thích.
- Thực hiện flush sớm hơn mong đợi tùy flush mode/query.
- Hạn chế insert batching khi ID strategy là `IDENTITY` vì cần lấy generated key sớm trong nhiều mapping/version.

**Không dùng counts[i] để xác nhận record nguồn thứ i** nếu Hibernate đang tự grouping/reordering.

### 5.1. Flush khác commit

~~~java
em.flush();
~~~

có thể kích hoạt SQL và làm lỗi constraint lộ ra, nhưng các thay đổi vẫn có thể rollback.

~~~java
em.flush();
em.clear();
~~~

thường dùng để tránh persistence context giữ quá nhiều managed entities trong import, nhưng `clear()` detach **tất cả** managed entities. Nếu vẫn cùng transaction thì SQL đã flush vẫn chưa commit.

### 5.2. Chunk size khác JDBC batch size

~~~text
hibernate.jdbc.batch_size = 50
job chunk size           = 500
~~~

Một chunk 500 items có thể tạo nhiều JDBC batches. Nếu cả 500 nằm trong transaction T, một lỗi SQL ở phần cuối vẫn có thể khiến T rollback toàn bộ.

## 6. Nhóm lỗi và chính sách ban đầu

| Lỗi | Ví dụ | Xử lý thường phù hợp |
| --- | --- | --- |
| Input invalid | Giá trị thiếu, sai format | Validate và reject/quarantine |
| UNIQUE violation | Duplicate business key | Đối chiếu existing payload trước khi coi là idempotent |
| FOREIGN KEY violation | Parent không tồn tại | Giải quyết dependency trước |
| CHECK/NOT NULL violation | Dữ liệu trái schema | Thường permanent nếu input không đổi |
| Optimistic conflict | Entity version stale | Rollback, reload, giải quyết conflict |
| Deadlock | Transaction bị chọn làm victim | Retry transaction mới với backoff |
| Serialization failure | Không thể commit theo isolation | Retry nguyên transaction |
| Lock timeout | Không lấy được lock | Phân loại theo DB và tình trạng transaction |
| Network loss | Mất kết nối trong lúc chạy hoặc commit | Xác định chắc rollback hay UNKNOWN |
| Resource exhaustion | Pool/memory/DB overload | Giảm tải và điều tra |
| Deferred constraint | Commit lỗi dù flush thành công | Rollback và xử lý nguyên nhân |
| Process crash sau commit | Target có, ledger chưa ghi | Reconcile theo business key |

### 6.1. SQLState, vendor code và exception chain

~~~java
SQLException ex = ...;

String sqlState = ex.getSQLState();
int errorCode = ex.getErrorCode();
SQLException next = ex.getNextException();
Throwable cause = ex.getCause();
~~~

SQLState class `23` thường liên quan integrity constraint, `40` liên quan rollback/serialization, `08` liên quan connection exception. Nhưng driver/vendor có khác biệt. Retry classifier cần được kiểm thử theo DB/driver cụ thể.

Các wrapper Hibernate/Spring có thể gồm:

- `org.hibernate.exception.ConstraintViolationException`.
- `org.hibernate.StaleStateException`.
- `jakarta.persistence.OptimisticLockException`.
- Spring `DataIntegrityViolationException`.
- Spring `OptimisticLockingFailureException` hoặc subtype.
- `BatchUpdateException` / `SQLException` ở nested cause chain.

Phân biệt `jakarta.validation.ConstraintViolationException` (Bean Validation) với `org.hibernate.exception.ConstraintViolationException` (database constraint).

## 7. Lỗi có thể xuất hiện muộn hơn persist()

~~~java
@Transactional
public void writeChunk(List<ImportRecord> inputs) {
    for (ImportRecord input : inputs) {
        em.persist(ImportedOrder.from(input));
        // Chưa chắc SQL INSERT đã chạy.
    }

    em.flush();
    // Lỗi có thể xuất hiện tại đây.
}
~~~

Một số lỗi còn có thể xuất hiện khi transaction manager commit **sau khi method body kết thúc**. Vì vậy gọi `persist()` xong không đủ để báo item đã commit.

### 7.1. Sau SQL/flush failure, rollback

Không nên:

~~~java
try {
    em.flush();
} catch (PersistenceException ex) {
    // Không an toàn: sửa entity rồi flush lại
    // trên cùng Session/transaction đã lỗi.
}
~~~

Một SQL failure có thể khiến transaction bị đánh dấu rollback-only hoặc bị DB abort, đặc biệt trên PostgreSQL. Cách xử lý an toàn thông thường: **rollback và không tái sử dụng Session/EntityManager lỗi; retry trong transaction mới**.

### 7.2. Không nuốt lỗi trong @Transactional

~~~java
try {
    em.flush();
} catch (RuntimeException ex) {
    log.warn("Chunk failed", ex);
    throw ex;
}
~~~

Để transaction interceptor rollback. Việc đổi status retry/dead-letter nên được điều phối **ngoài transaction đã thất bại**.

## 8. Optimistic locking và row count mong đợi

Với entity:

~~~java
@Entity
@Table(name = "accounts")
public class Account {

    @Id
    private Long id;

    @Version
    private long version;

    private BigDecimal balance;

    protected Account() {}

    public void setBalance(BigDecimal value) {
        this.balance = value;
    }
}
~~~

Hibernate có thể sinh SQL tương đương:

~~~sql
UPDATE accounts
SET balance = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Khi version trong DB khác version của entity đã nạp, UPDATE có thể tác động **0 hàng**, Hibernate coi đó là stale/optimistic-lock conflict.

### 8.1. Count=0 không có cùng ý nghĩa ở mọi nơi

| Statement | Count=0 có thể nghĩa |
| --- | --- |
| Versioned entity UPDATE | Concurrency conflict hoặc entity bị xóa |
| Bulk UPDATE theo status | Không có row phù hợp, có thể hợp lệ |
| Inventory reservation | Không đủ hàng hoặc SKU không tồn tại |
| DELETE idempotent | Hàng đã không còn, có thể chấp nhận |

**Business contract** quyết định cách xử lý 0, không phải bản thân JDBC.

### 8.2. SUCCESS_NO_INFO và optimistic lock

Nếu driver trả `SUCCESS_NO_INFO` cho một batched UPDATE, provider không có exact affected row count để xác minh kỳ vọng một hàng theo cách thông thường. Hành vi phụ thuộc Hibernate version, driver và batching semantics. Với hệ thống cần optimistic locking chắc chắn, hãy test trên driver thật; không giả định counts luôn là 1.

## 9. Bulk HQL executeUpdate() không luôn đếm physical rows

~~~java
int affected = em.createQuery("""
    delete from BaseDocument d
    where d.archived = true
    """)
    .executeUpdate();
~~~

Trong Hibernate, con số bulk HQL thường mang nghĩa **số entities affected**. Nếu `BaseDocument` dùng JOINED inheritance hay multi-table mapping, để xóa một entity có thể phải tác động nhiều bảng vật lý. Vì vậy affected entity count không nhất thiết bằng tổng physical rows deleted.

Bulk HQL/JPQL cũng không giống vòng lặp sửa managed entities:

- Không thực hiện dirty checking từng instance.
- Không mặc định chạy entity callbacks/cascade tương tự entity operations.
- Có thể không tăng/kiểm tra `@Version` theo cách của entity UPDATE thông thường.
- Có thể làm managed instances trong persistence context stale.
- Vẫn thuộc transaction và có thể rollback sau khi `executeUpdate()` trả số dương.

Reconciliation phải kiểm tra **trạng thái dữ liệu mục tiêu**, không chỉ return value.

## 10. Transaction boundary: toàn job hay từng chunk?

### 10.1. Một transaction cho toàn job

~~~text
Job: 100.000 records
└─ Transaction T
   ├─ JDBC batches ...
   └─ COMMIT
~~~

Ưu điểm: all-or-nothing. Nhược điểm: transaction dài, giữ locks/undo/transaction log lâu, rollback đắt, một lỗi muộn có thể hủy toàn bộ.

### 10.2. Mỗi chunk một transaction

~~~text
Job: 100.000 records
├─ Chunk 1 / T1 → COMMITTED
├─ Chunk 2 / T2 → COMMITTED
├─ Chunk 3 / T3 → ROLLED_BACK
└─ Chunk 4      → chưa xử lý
~~~

Ưu điểm: giảm rollback cost, dễ checkpoint/retry. Nhược điểm: job có **partial committed state**, cần ledger và reconciliation để xác nhận/chốt.

Lựa chọn phụ thuộc hợp đồng nghiệp vụ; không tự chuyển all-or-nothing sang partial acceptance chỉ vì muốn hiệu năng.

## 11. Spring: writer riêng cho mỗi chunk

~~~java
@Service
public class ImportChunkWriter {

    @PersistenceContext
    private EntityManager em;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeChunk(List<ImportRecord> chunk) {
        for (ImportRecord record : chunk) {
            em.persist(ImportedOrder.from(record));
        }

        em.flush();
        em.clear();
    }
}
~~~

Coordinator:

~~~java
@Service
public class ImportCoordinator {

    private final ImportChunkWriter writer;

    public ImportCoordinator(ImportChunkWriter writer) {
        this.writer = writer;
    }

    public void run(List<ImportRecord> items) {
        int chunkSize = 500;

        for (int i = 0; i < items.size(); i += chunkSize) {
            List<ImportRecord> chunk = items.subList(
                i, Math.min(i + chunkSize, items.size()));

            try {
                writer.writeChunk(chunk);
                // Với local transaction qua Spring proxy,
                // commit đã được xử lý khi method return.
                markCommitObserved(i, chunk.size());
            } catch (RuntimeException ex) {
                handleChunkError(i, chunk, ex);
            }
        }
    }

    private void markCommitObserved(int start, int size) {
        // Ledger có transaction riêng hoặc cùng target.
    }

    private void handleChunkError(
            int start, List<ImportRecord> chunk,
            RuntimeException ex) {
        // Phân loại, retry và reconciliation.
    }
}
~~~

`ImportRecord`, `ImportedOrder` và các helper là model giả định. Cần thêm mapping và ledger implementation cho ứng dụng thật.

### 11.1. Self-invocation và @Transactional

Với Spring proxy-based transactions, `this.writeChunk()` gọi trong cùng bean có thể bypass proxy, khiến `REQUIRES_NEW` không được áp dụng. Tách writer thành bean riêng như ví dụ hoặc dùng `TransactionTemplate`.

### 11.2. REQUIRES_NEW có chi phí

Nếu caller giữ transaction ngoài, một transaction REQUIRES_NEW có thể cần connection khác. Tránh bao coordinator bằng một transaction dài và đo connection pool khi chạy nhiều workers.

### 11.3. Có khoảng hở giữa commit và ledger

Writer có thể commit thành công rồi process crash trước `markCommitObserved()`. Vì thế ledger báo chưa xong dù target đã có dữ liệu. Cần reconciliation hoặc ghi target + ledger trong cùng transaction nếu cùng DB và thiết kế cho phép.

## 12. Error isolation: chia nhỏ chunk lỗi

Một chunk 8 items có một item sai constraint:

~~~text
[A B C D E F G H] → FAIL
   /             \
[A B C D]     [E F G H]
 SUCCESS        FAIL
               /    \
             [E F] [G H]
             FAIL  SUCCESS
             /  \
           [E]  [F]
           FAIL SUCCESS
~~~

Quy trình:

1. Rollback transaction thất bại.
2. Phân loại lỗi.
3. Nếu là lỗi dữ liệu có thể cô lập và nghiệp vụ cho phép partial acceptance, chia chunk.
4. Thử mỗi nửa trong **transaction mới**.
5. Ghi item lỗi đơn lẻ vào quarantine/dead-letter.
6. Chỉ xác nhận item thành công sau commit.

Không dùng binary split cho mọi deadlock/serialization/network error. Lỗi transient thường retry transaction theo policy; commit unknown phải reconciliation trước.

### 12.1. Duplicate trong cùng input

Hai items có cùng business key có thể cạnh tranh nhau, khiến kết quả split phụ thuộc thứ tự. Nên deduplicate source trước hoặc định nghĩa first-wins/last-wins/reject/version-based policy.

### 12.2. Không tự đổi atomicity

Nếu job đòi all-or-nothing, không được âm thầm commit các nửa thành công. Đó là thay đổi contract nghiệp vụ.

## 13. Retry có giới hạn và transaction mới

Pseudocode:

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        writer.writeChunk(chunk); // transaction mới
        return;
    } catch (RuntimeException ex) {
        if (!classifier.isRetryable(ex)) {
            throw ex;
        }
        if (attempt == maxAttempts) {
            throw ex;
        }
        backoff.pause(attempt); // ngoài transaction
    }
}
~~~

`classifier` và `backoff` là abstraction ứng dụng. Cần max attempts, exponential backoff/jitter, monitoring và dead-letter khi cần.

Điều quan trọng hơn retry code là **tính idempotent**. Nếu transaction trước đã commit nhưng client timeout, retry INSERT không có unique business key sẽ nhân đôi dữ liệu.

## 14. Idempotency bằng business key

Một item nên có identity từ nguồn:

~~~text
tenantId        = 42
sourceSystem    = ERP
externalOrderId = P-2026-00991
sourceVersion   = 3
payloadHash     = ...
~~~

Schema:

~~~sql
CREATE TABLE imported_orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    source_system VARCHAR(80) NOT NULL,
    external_order_id VARCHAR(150) NOT NULL,
    source_version BIGINT NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    amount DECIMAL(19,2) NOT NULL,
    CONSTRAINT uk_business_order
      UNIQUE (tenant_id, source_system, external_order_id)
);
~~~

Khi retry:

1. Xác minh target theo business key.
2. Nếu row đã có cùng version/hash/business outcome → có thể `ALREADY_APPLIED`.
3. Nếu row khác payload/version → xử lý conflict/update policy.
4. Nếu chưa có → thử INSERT/UPSERT an toàn trong transaction mới.
5. Xác nhận commit hoặc reconciliation trước khi báo success.

### 14.1. Check-then-insert vẫn race

~~~text
Worker A: SELECT key → không có
Worker B: SELECT key → không có
Worker A: INSERT → COMMIT
Worker B: INSERT → unique violation
~~~

Chỉ SELECT trước không đủ. **Unique constraint tại DB** là hàng rào chống duplicate dưới concurrency. Sau conflict, rollback transaction lỗi và xác minh target trong transaction mới.

### 14.2. UPSERT không đồng nghĩa “new insert”

PostgreSQL `INSERT ... ON CONFLICT` và các DB khác có `MERGE` hoặc cú pháp khác. Một lệnh upsert có thể INSERT mới hoặc UPDATE cũ. Affected count khác nhau tùy DB/driver, nên nếu cần metric new/updated/skipped phải ghi nhận rõ semantics và test.

### 14.3. Unique conflict có thể là lỗi thật

Nếu cùng externalOrderId nhưng amount/sourceVersion khác, đừng mặc định duplicate là success. Có thể đó là hai command xung đột cần review hoặc quy tắc versioned update.

## 15. Ledger và staging hỗ trợ reconciliation

Một import pipeline đáng tin thường có:

1. **Staging**: input theo jobId, tenantId, sourceKey, payloadHash.
2. **Target**: dữ liệu nghiệp vụ cuối.
3. **Job ledger**: status hiện hành, attempts, error code, target ID.
4. **Outbox**: sự kiện cần phát sau commit.

Ví dụ ledger:

~~~sql
CREATE TABLE import_jobs (
    job_id VARCHAR(100) PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE import_items (
    job_id VARCHAR(100) NOT NULL,
    source_key VARCHAR(150) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    status VARCHAR(30) NOT NULL,
    target_id BIGINT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_code VARCHAR(80),
    PRIMARY KEY (job_id, source_key),
    FOREIGN KEY (job_id) REFERENCES import_jobs(job_id)
);
~~~

Các trạng thái:

| State | Ý nghĩa |
| --- | --- |
| `PENDING` | Đã nhận, chưa hoàn tất |
| `IN_PROGRESS` | Worker đang xử lý; chưa chứng minh commit |
| `COMMITTED` | Business outcome bền vững đã được xác nhận |
| `ALREADY_APPLIED` | Same operation đã được áp dụng từ trước |
| `RETRY_PENDING` | Thất bại tạm thời, chờ retry |
| `PERMANENT_FAILURE` | Item lỗi cần sửa/manual resolution |
| `UNKNOWN` | Không biết chắc transaction đã commit hay chưa |

**Không gộp UNKNOWN vào FAILED.** Một UNKNOWN có thể đã commit ở database.

### 15.1. Cùng DB thì ghi ledger và target trong cùng transaction

~~~text
BEGIN
  INSERT/UPDATE target
  UPDATE import_items SET status='COMMITTED', target_id=...
COMMIT
~~~

Khi rollback, cả hai thay đổi rollback. Nếu target và ledger nằm ở hai DB/queue/service khác nhau, không có atomicity mặc định; phải có reconciliation/outbox/saga hoặc distributed transaction được thiết kế rõ.

### 15.2. Crash ở khoảng hở vẫn xảy ra

Nếu target commit và coordinator ledger update là hai transactions, worker có thể crash giữa chúng. Reconciler cần query target theo business key/hash để cập nhật lại ledger, không INSERT thêm.

## 16. “Số item thành công” khác physical row count

Một source item có thể tạo:

- Một row bảng chính.
- Vài rows bảng child.
- Một audit record.
- Một outbox event.

Vì vậy các metric phải khác đơn vị:

| Metric | Đơn vị |
| --- | --- |
| `inputCount` | Source items |
| `attemptCount` | Item attempts |
| `knownJdbcAffectedRows` | Physical rows được driver báo count chính xác |
| `successNoInfoCount` | Statements thành công nhưng count không rõ |
| `committedItemCount` | Business items đã xác nhận |
| `alreadyAppliedCount` | Idempotent items đã có |
| `retryPendingCount` | Items chờ thử lại |
| `permanentFailureCount` | Items không thể tự xử lý |
| `unknownCount` | Items chưa biết outcome |
| `mismatchCount` | Items sai khi đối soát |

Một công thức ledger:

~~~text
accepted source items =
    COMMITTED + ALREADY_APPLIED + RETRY_PENDING
  + PERMANENT_FAILURE + UNKNOWN + PENDING + IN_PROGRESS
~~~

Điều này giả định mỗi accepted item có đúng **một trạng thái hiện hành**. Nếu ledger lưu nhiều attempts, không cộng tất cả attempts như các item độc lập.

## 17. SQL đối soát key và content

Staging:

~~~sql
CREATE TABLE import_staging (
    job_id VARCHAR(100) NOT NULL,
    tenant_id BIGINT NOT NULL,
    source_key VARCHAR(150) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    amount DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (job_id, source_key)
);
~~~

Target minh họa:

~~~sql
CREATE TABLE imported_orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    source_key VARCHAR(150) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    amount DECIMAL(19,2) NOT NULL,
    UNIQUE (tenant_id, source_key)
);
~~~

### 17.1. Tìm source keys chưa có target

~~~sql
SELECT s.job_id, s.tenant_id, s.source_key
FROM import_staging s
LEFT JOIN imported_orders t
  ON t.tenant_id = s.tenant_id
 AND t.source_key = s.source_key
WHERE s.job_id = :jobId
  AND t.id IS NULL;
~~~

Kết quả missing cần kết hợp ledger: có thể là pending, permanent failure hoặc cần retry, không tự coi tất cả là data loss.

### 17.2. Tìm mismatch theo hash

~~~sql
SELECT
    s.source_key,
    s.payload_hash AS expected_hash,
    t.payload_hash AS actual_hash
FROM import_staging s
JOIN imported_orders t
  ON t.tenant_id = s.tenant_id
 AND t.source_key = s.source_key
WHERE s.job_id = :jobId
  AND s.payload_hash <> t.payload_hash;
~~~

Ví dụ giả định hash NOT NULL. Khi có NULL, cần null-safe comparison phù hợp dialect.

### 17.3. So aggregate theo đúng keys của job

~~~sql
SELECT COUNT(*) AS source_count,
       SUM(amount) AS source_amount
FROM import_staging
WHERE job_id = :jobId;
~~~

Với target, phải join lại theo business key của source job:

~~~sql
SELECT COUNT(*) AS target_count,
       SUM(t.amount) AS target_amount
FROM import_staging s
JOIN imported_orders t
  ON t.tenant_id = s.tenant_id
 AND t.source_key = s.source_key
WHERE s.job_id = :jobId;
~~~

Đừng đếm toàn bộ orders cùng tenant rồi so với job; những orders của job khác sẽ làm sai số.

### 17.4. Count khớp vẫn có thể sai

Source 10.000 items, target 10.000 rows không chứng minh mọi key và amount đúng. Có thể thiếu 5 keys và tồn tại 5 duplicates/sai mappings. Cần **key reconciliation**, **hash/version reconciliation** và các business aggregates phù hợp.

## 18. Commit outcome UNKNOWN

Tình huống:

~~~text
Client gửi batch
DB thực thi statements
Client gửi COMMIT
Mất kết nối trước khi nhận kết quả COMMIT
~~~

Client không thể xác định chắc:

- DB đã commit nhưng response bị mất.
- DB rollback hoặc chưa commit.

`getUpdateCounts()` không giải quyết được vì counts thuộc giai đoạn execute, không phải xác nhận COMMIT.

Quy trình:

1. Đánh dấu UNKNOWN; không báo chắc chắn FAILED.
2. Mở transaction/connection mới.
3. Đọc target theo business keys ổn định.
4. So payload hash/version/outcome.
5. Target đúng → COMMITTED hoặc ALREADY_APPLIED.
6. Target không có → xác minh consistency của nguồn đọc rồi retry idempotent.
7. Target khác → CONFLICT/manual review.
8. Chưa thể xác minh → giữ UNKNOWN và alert.

**Read replica lag** có thể khiến một record vừa commit trên primary chưa được nhìn thấy. Với commit-unknown, nên dùng primary hoặc nguồn đọc có consistency bảo đảm phù hợp trước khi kết luận missing.

## 19. Outbox bảo vệ luồng event sau DB commit

Nếu ứng dụng INSERT order rồi gửi message:

~~~text
DB COMMIT thành công
     ↓ process crash
Message chưa được publish
~~~

Nếu gửi message trước commit:

~~~text
Message publish thành công
     ↓
DB transaction rollback
~~~

Consumer nhận event về order chưa tồn tại.

**Transactional outbox** ghi event cùng transaction với target:

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_key VARCHAR(150) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

~~~text
BEGIN
  INSERT/UPDATE imported_orders
  INSERT outbox_events
COMMIT
~~~

Publisher riêng gửi outbox events, sau đó ghi nhận published. Publisher có thể gửi rồi crash trước khi cập nhật, gây **gửi lại**. Consumer phải idempotent theo event ID.

Outbox giảm khoảng hở “DB commit vs event durable”, nhưng không tự tạo exactly-once end-to-end.

## 20. Logging, metrics và reconciliation backlog

Structured log:

~~~json
{
  "jobId": "import-2026-11-15-001",
  "chunkId": "00042",
  "attempt": 2,
  "inputCount": 500,
  "transactionOutcome": "ROLLED_BACK",
  "errorCategory": "UNIQUE_CONSTRAINT",
  "sqlStateClass": "23",
  "durationMs": 480,
  "retryable": false
}
~~~

Nên theo dõi:

- Confirmed committed items/second (thay vì chỉ attempted items).
- Failed chunks, retries, permanent failures.
- UNKNOWN quá hạn, key/hash mismatches.
- Transaction latency, rollback rate, deadlocks/lock waits.
- Connection pool pressure, memory, DB transaction log.
- Outbox lag và downstream duplicates.

Hibernate 6 có thể bật:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
hibernate.generate_statistics=true
~~~

Bind logs có thể chứa dữ liệu nhạy cảm; tránh TRACE tràn lan trên production.

`SessionFactory.getStatistics()` hữu ích để xem prepared statements và entity actions, nhưng thường có phạm vi toàn SessionFactory và **không phải** ledger các business items đã commit.

## 21. Chọn batch size và chunk size theo benchmark

Batch lớn giúp giảm round-trips nhưng có thể tăng memory, lock contention, transaction duration, rollback/retry cost và áp lực connection pool.

Một ma trận benchmark minh họa:

~~~text
JDBC batch size: 20, 50, 100
Chunk size:     200, 500, 1000
Worker count:   1, 2, 4
~~~

Đo:

- Confirmed committed items/second.
- P95/P99 chunk latency.
- Deadlocks/timeouts.
- Retry attempts/item.
- Memory và connection usage.
- Reconciliation backlog.
- Business mismatch rate.

Không kết luận batch size lớn hơn luôn nhanh hơn. Với contention trên unique index hoặc cùng rows, tăng worker count có thể làm throughput giảm.

## 22. Integration tests cần có

Nên kiểm thử trên DB/driver tương tự production, ví dụ Testcontainers cho stack phù hợp.

1. **Unique duplicate:** chunk rollback đúng, retry không tạo trùng, phân biệt same payload và conflict.
2. **FK/CHECK constraint:** lỗi xuất hiện ở flush hoặc commit; rollback và không reuse Session lỗi.
3. **Optimistic conflict:** hai transactions sửa cùng entity version, transaction sau nhận stale exception.
4. **Deadlock/serialization:** retry toàn transaction với backoff và max attempts.
5. **Deferred constraint:** flush thành công nhưng commit thất bại, ledger không báo COMMITTED.
6. **Crash sau commit trước ledger:** reconciler xác minh target và sửa ledger mà không INSERT lại.
7. **SUCCESS_NO_INFO:** code không cộng -2 và không dùng nó để khẳng định count=1.
8. **Partial BatchUpdateException:** code chịu được mảng ngắn/EXECUTE_FAILED và rollback.
9. **Tenant scope:** hai tenant cùng sourceKey không được đối soát nhầm.
10. **Replica lag:** không kết luận missing ngay từ replica chưa đồng bộ.
11. **Outbox retry:** event được gửi lại nhưng consumer vẫn idempotent.
12. **Load test:** benchmark chunk size, batching và worker concurrency trên dữ liệu đại diện.

## 23. Chốt trạng thái job như thế nào?

| Hợp đồng job | Khi nào được hoàn tất? |
| --- | --- |
| All-or-nothing | Toàn transaction đúng contract đã commit |
| Partial acceptance | Mỗi item có outcome xác định: committed/already-applied hoặc lỗi được chấp nhận |
| Eventual processing | Phân biệt DB import complete với downstream delivery complete |
| Batch job có checkpoint | Mọi batch được xử lý bền vững, checkpoint phù hợp, retry idempotent |

Không ghi `COMPLETED` tuyệt đối nếu còn UNKNOWN/retry pending mà contract yêu cầu xử lý hết.

Recovery runbook:

1. Cô lập job lỗi, tránh nhiều workers retry trùng.
2. Ghi nhận job/chunk/attempt/SQLState.
3. Xác định transaction boundaries và chunks đã commit.
4. Đưa UNKNOWN vào reconciliation.
5. Đọc target theo business keys trên nguồn nhất quán.
6. So payload hash/version, counts và aggregates.
7. Phân loại committed, already applied, retry, permanent, unknown.
8. Retry trong transaction mới, có idempotency và backoff.
9. Kiểm tra outbox/downstream state.
10. Xuất kết quả cuối cùng và audit mọi repair.

## 24. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| BatchUpdateException có đủ counts cho mọi lệnh | Driver có thể dừng sớm hoặc tiếp tục |
| `SUCCESS_NO_INFO` là lỗi | Thành công nhưng không biết exact row count |
| Count=1 nghĩa là committed | Statement execution khác transaction commit |
| Flush=commit | Flush có thể bị rollback sau đó |
| Count=0 luôn là lỗi | Tùy business contract |
| Một entity tương ứng đúng một SQL row | Mapping có thể chạm nhiều bảng |
| HQL executeUpdate đếm mọi physical row | Có semantics entity count |
| jdbc.batch_size bằng chunk size | Hai cấu hình khác tầng |
| Hibernate statement thứ k là input thứ k | Hibernate có thể reorder/group |
| Bắt SQL exception rồi tiếp tục Session | Sau flush error thường phải rollback, bỏ context |
| Retry duplicate là an toàn | Cần business key và kiểm tra payload/version |
| Timeout đồng nghĩa rollback | Commit outcome có thể UNKNOWN |
| Source count bằng target count là đủ | Cần key/hash/aggregate reconciliation |
| Unique constraint bảo đảm exactly-once end-to-end | External side effects còn cần idempotency/outbox |
| Outbox bảo đảm event gửi đúng một lần | Publisher có thể gửi lại; consumer phải dedupe |
| Ghi ledger sau commit không có khoảng hở | Process có thể crash giữa hai bước |
| Statistics chứng minh số items committed | Statistics không phải business ledger |

## 25. Bài tập thực hành

### Bài 1 — JDBC counts

Batch trả `[1, 1, -2, 0, 1]`. Giải thích -2, 0 và vì sao không cộng mảng trực tiếp để ra committed business records.

### Bài 2 — BatchUpdateException

Batch 10 statements, exception có 3 update counts. Có thể kết luận statement thứ tư lỗi trong mọi driver không? Phân biệt driver dừng và tiếp tục.

### Bài 3 — Flush và commit

Hibernate persist 100 entities, flush thành công nhưng commit thất bại do deferred constraint. Có thể ghi 100 COMMITTED không?

### Bài 4 — Optimistic locking

Versioned UPDATE trả 0 rows. Vì sao đây thường là concurrency conflict? Khi nào count 0 lại là kết quả hợp lệ?

### Bài 5 — IDENTITY

Vì sao IDENTITY có thể làm giảm khả năng batching Hibernate INSERT? Cần đánh giá gì trước khi đổi sang sequence?

### Bài 6 — Chunk transactions

Chúng ta có chunks 1–17 committed, chunk 18 rollback. Job nên resume thế nào để không ghi lại dữ liệu đã commit?

### Bài 7 — Error isolation

Một chunk 8 items có một unique violation. Mô tả binary split với transactions mới và các tình huống không được split tùy tiện.

### Bài 8 — Duplicate conflict

Hai records có cùng externalOrderId nhưng payload hash khác. Có thể coi ALREADY_APPLIED không?

### Bài 9 — Commit unknown

Client mất kết nối sau khi gửi COMMIT. Thiết kế reconciliation trước retry, bao gồm nguồn đọc DB đủ consistency.

### Bài 10 — Count reconciliation

Source 10.000 records, target cũng 10.000. Nêu ba cách kiểm tra ngoài tổng count.

### Bài 11 — SQL missing keys

Viết LEFT JOIN staging-target theo tenantId và sourceKey để tìm keys chưa có trong target.

### Bài 12 — Bulk HQL

Một DELETE HQL trên entity JOINED inheritance báo affected=10 nhưng SQL sửa hai bảng. Vì sao physical rows có thể khác?

### Bài 13 — Self-invocation

`this.writeChunk()` gọi method có `@Transactional(REQUIRES_NEW)`. Với Spring proxy, điều gì có thể sai? Cách sửa?

### Bài 14 — Outbox

Vì sao DB commit và gửi message có khoảng hở? Outbox giúp gì, và vì sao consumer vẫn cần idempotency?

### Bài 15 — Retry policy

Phân loại unique violation, deadlock, validation error, optimistic lock và connection loss lúc commit thành permanent/transient/unknown theo context.

### Bài 16 — Metrics

Đo attempted throughput hay confirmed committed items/second để đánh giá thành công job? Vì sao?

### Bài 17 — Read replica

Reconciler không thấy row trên replica ngay sau commit timeout. Có thể kết luận row missing không?

### Bài 18 — Chốt job

Ledger còn 4 UNKNOWN, 20 RETRY_PENDING và một PERMANENT_FAILURE. Có nên báo hoàn tất tuyệt đối không?

### Gợi ý đáp án

- **Bài 1:** -2 = SUCCESS_NO_INFO; 0 tùy câu SQL; không có bằng chứng commit.
- **Bài 2:** Driver có thể trả partial counts hoặc tiếp tục với EXECUTE_FAILED; không suy đoán chắc từ mảng.
- **Bài 3:** Không; flush có thể rollback.
- **Bài 4:** Entity version mismatch thường tạo stale conflict; bulk no-op có thể 0 hợp lệ.
- **Bài 5:** IDENTITY thường cần INSERT sớm để lấy key; phải đánh giá provider/driver/DB, semantics ID và benchmark.
- **Bài 6:** Giữ những chunks đã commit và chỉ retry chunk cần thiết theo idempotency.
- **Bài 7:** Mỗi split cần transaction mới; transient/unknown cần policy khác.
- **Bài 8:** Không; payload khác có thể là conflict.
- **Bài 9:** UNKNOWN, đọc target bằng business key/hash trên nguồn nhất quán rồi retry idempotent nếu cần.
- **Bài 10:** Key reconciliation, hash/version comparison, aggregates/outbox.
- **Bài 11:** LEFT JOIN theo tenant/sourceKey, lọc target.id IS NULL.
- **Bài 12:** Một entity có thể nằm trên nhiều bảng nên physical row count khác entity count.
- **Bài 13:** Self-invocation bypass proxy; dùng bean khác hoặc TransactionTemplate.
- **Bài 14:** Outbox ghi cùng transaction; publisher có thể phát lại, consumer phải dedupe.
- **Bài 15:** Deadlock thường transient; validation/unique conflict thường permanent; commit loss có thể UNKNOWN.
- **Bài 16:** Dùng confirmed committed business outcomes.
- **Bài 17:** Không; replica có thể lag, nên đọc primary/nguồn đủ consistency.
- **Bài 18:** Không; phải xử lý UNKNOWN/retry và định nghĩa policy permanent errors.

---

## Tổng kết

**Batching tăng throughput, không tự bảo đảm tính chính xác hoặc exactly-once.** Khi batch lỗi, cần tách:

1. **JDBC update counts** phản ánh số rows mà driver biết hoặc các sentinel `SUCCESS_NO_INFO` và `EXECUTE_FAILED`; chúng không chứng minh commit.
2. **Hibernate flushing** có thể group/reorder statements và phát hiện constraint/optimistic conflict muộn; không dùng mảng counts như business ledger.
3. **Bulk HQL** trả số affected entities theo semantics ORM, không nhất thiết là tổng physical rows ở nhiều bảng.
4. **Transaction boundaries** quyết định rollback/partial acceptance; sau SQL failure, rollback và retry trong transaction mới.
5. **Idempotency + reconciliation** dựa trên unique business keys, staging/ledger và đối chiếu key/hash/aggregates để phân biệt COMMITTED, FAILED và UNKNOWN.
6. **Outbox, giới hạn retry và observability** bảo vệ luồng xử lý dài hơn một DB transaction.

**Chỉ công bố thành công khi business outcome được xác nhận bền vững. Nếu chưa biết commit đã xảy ra chưa, giữ UNKNOWN và đối soát trước khi retry thay vì chạy lại mù quáng.**
