# Lỗi tài nguyên, khóa, truy cập đồng thời và khả năng thử lại trong Spring Data Access

Khi truy cập cơ sở dữ liệu qua `JdbcTemplate` hoặc các tầng truy cập dữ liệu của Spring, một thao tác thất bại có thể do **kết nối/tài nguyên**, **tranh chấp khóa**, **xung đột khi cập nhật đồng thời**, hoặc **lỗi dữ liệu/SQL không thể giải quyết bằng thử lại**. Các lỗi này có cách xử lý khác nhau. Đặc biệt, **không phải cứ bắt `DataAccessException` rồi chạy lại câu SQL là an toàn**.

Ví dụ: hai transaction cùng cập nhật một hàng có thể gây lock timeout hoặc deadlock; hai người sửa cùng bản ghi có thể tạo optimistic conflict; database mất kết nối sau một lệnh chuyển tiền có thể khiến ứng dụng **không biết lệnh đã commit hay chưa**. Trong mỗi trường hợp, cần phân loại chính xác, hiểu ranh giới transaction, chọn hành động an toàn và chỉ retry khi có lý do.

Bài học tập trung vào hệ ngoại lệ `org.springframework.dao` của Spring Framework, cách nhận biết lỗi resource/lock/concurrency, quyết định khả năng thử lại (retry), cách giữ dữ liệu nhất quán, và các ví dụ Java 17+ dùng Spring JDBC.

## 1. Spring làm gì khi JDBC phát sinh lỗi?

Với JDBC thuần, bạn thường gặp `SQLException`, `SQLTransientException`, `SQLIntegrityConstraintViolationException`, `SQLTransactionRollbackException`... và các mã `SQLState` hoặc mã lỗi riêng của database. Nếu chỉ bắt chung `SQLException` trong mọi lớp nghiệp vụ, mã ứng dụng phải phụ thuộc trực tiếp vào driver và vendor.

`JdbcTemplate` thường **dịch các `SQLException`** sang hệ ngoại lệ runtime chung của Spring:

```text
Driver / database
  -> SQLException (+ SQLState, vendor error code, subtype)
  -> SQLExceptionTranslator của Spring JDBC
  -> DataAccessException phù hợp
  -> tầng service quyết định rollback, báo lỗi hoặc retry
```

`DataAccessException` là ngoại lệ **unchecked** (kế thừa `RuntimeException`). Spring sử dụng lớp `SQLExceptionTranslator` để ánh xạ lỗi JDBC. Trên Spring Framework 6.x, translator mặc định là `SQLExceptionSubclassTranslator` với fallback qua `SQLStateSQLExceptionTranslator`; `SQLErrorCodeSQLExceptionTranslator` có thể dùng mã lỗi vendor khi được cấu hình phù hợp.

**Không có bảo đảm** một SQLState luôn tạo chính xác một lớp ngoại lệ Spring ở mọi phiên bản driver/vendor. Khi phân tích sự cố thật, quan sát đồng thời lớp ngoại lệ Spring, `getMostSpecificCause()` hoặc `getRootCause()`, SQLState, vendor code và trạng thái transaction.

## 2. Các nhánh ngoại lệ quan trọng

Sơ đồ rút gọn:

```text
DataAccessException (RuntimeException)
├── TransientDataAccessException
│   ├── ConcurrencyFailureException
│   │   ├── PessimisticLockingFailureException
│   │   │   └── CannotAcquireLockException
│   │   └── OptimisticLockingFailureException
│   ├── TransientDataAccessResourceException
│   └── QueryTimeoutException
├── NonTransientDataAccessException
│   ├── NonTransientDataAccessResourceException
│   │   └── DataAccessResourceFailureException
│   │       └── CannotGetJdbcConnectionException
│   ├── DataIntegrityViolationException
│   │   └── DuplicateKeyException
│   └── InvalidDataAccessResourceUsageException
├── RecoverableDataAccessException
└── UncategorizedDataAccessException
```

Đây là **cây minh họa các nhánh liên quan**, không liệt kê mọi superclass/lớp con của Spring. `BadSqlGrammarException` thuộc họ lỗi dùng SQL/tài nguyên sai (`InvalidDataAccessResourceUsageException`). Hai lớp lịch sử `DeadlockLoserDataAccessException` và `CannotSerializeTransactionException` cũng nằm dưới `PessimisticLockingFailureException`, nhưng đã **deprecated từ Spring 6.0.3**; với mã mới nên xử lý qua `PessimisticLockingFailureException` hoặc nhánh cụ thể phù hợp.

Sự phân loại `transient` nói rằng lỗi **có thể** biến mất khi thử lại; nó **không chứng minh retry luôn an toàn về mặt nghiệp vụ**, không quyết định chắc chắn câu lệnh trước đó chưa commit và không thay thế chính sách giới hạn retry.

| Ngoại lệ / nhóm | Ý nghĩa thường gặp | Hành động ban đầu |
| --- | --- | --- |
| `CannotGetJdbcConnectionException` / `DataAccessResourceFailureException` | Không lấy được connection, DB unavailable, pool/driver/configuration gặp vấn đề; thuộc nhánh **non-transient** của Spring | Kiểm tra hạ tầng, cấu hình, pool, cause; cân nhắc phục hồi theo chính sách riêng |
| `TransientDataAccessResourceException` | Tài nguyên thất bại tạm thời | Xác định trạng thái lệnh/transaction, rồi cân nhắc retry có giới hạn |
| `RecoverableDataAccessException` | Cần thao tác phục hồi (ví dụ kết nối mới) trước khi thử lại | Phục hồi tài nguyên và **thử lại toàn transaction** nếu nghiệp vụ an toàn |
| `PessimisticLockingFailureException` / `CannotAcquireLockException` | Không lấy được lock, deadlock hoặc lỗi liên quan tranh chấp khóa (tùy translator) | Rollback transaction bị lỗi, thử lại từ transaction mới khi thích hợp |
| `OptimisticLockingFailureException` | Dữ liệu đã thay đổi kể từ lúc đọc (version/stale state) | Đọc lại trạng thái và **tính lại** thao tác, hoặc trả conflict cho người dùng |
| `QueryTimeoutException` | Query vượt timeout / bị dừng theo driver | Kiểm tra query, lock, hạ tầng; không retry mù thao tác ghi |
| `DataIntegrityViolationException` / `DuplicateKeyException` | Trùng khóa, sai FK, NOT NULL, CHECK... | Sửa dữ liệu hoặc xử lý tình huống nghiệp vụ; retry nguyên xi thường không ích |
| `BadSqlGrammarException` | Cú pháp SQL, bảng/cột sai, SQL không tương thích | Sửa SQL/schema; không retry |
| `PermissionDeniedDataAccessException` | Thiếu quyền truy cập tài nguyên DB | Sửa quyền/chính sách; không retry mù |
| `UncategorizedDataAccessException` | Translator không phân loại được | Xem cause/SQLState/vendor code và trạng thái transaction trước khi quyết định |

**Bẫy thường gặp:** `CannotGetJdbcConnectionException` **không** kế thừa `TransientDataAccessException`. Đây là subclass của `DataAccessResourceFailureException` dưới nhánh non-transient. Kết nối có thể trở lại sau 5 giây, nhưng code `catch (TransientDataAccessException e)` không mặc nhiên bắt lỗi này. Ngược lại, `TransientDataAccessException` cũng không có nghĩa mọi lệnh `INSERT` có thể chạy lại an toàn.

## 3. Lỗi tài nguyên: phân biệt thiếu kết nối, mất kết nối, quá tải và lỗi cấu hình

"Tài nguyên" có thể là connection, connection pool, phiên làm việc, database endpoint hoặc tài nguyên xử lý query. Các tình huống cần phân biệt:

1. **Không mở được connection trước khi bắt đầu transaction**: DB down, host không tới được, credentials sai, TLS sai, pool hết connection... Có thể thấy `CannotGetJdbcConnectionException` hoặc lỗi liên quan. Nếu do sai mật khẩu/URL, thử thêm 100 lần không giúp gì; nếu do sự cố mạng ngắn hạn, cần cơ chế chờ/health check và giới hạn tải hợp lý.
2. **Connection mất giữa transaction**: driver có thể trả một loại `SQLException` khác; transaction có thể đã bị hủy, nhưng với thao tác ghi quanh thời điểm mất kết nối, ứng dụng phải cẩn thận về kết quả commit chưa xác định. Chỉ dựa vào class lỗi thường không đủ.
3. **Connection pool bị cạn**: nhiều yêu cầu giữ connection quá lâu, leak, query chậm, lock wait, pool max-size quá nhỏ hoặc database không đủ capacity. Nếu mọi request lập tức retry, tải có thể tăng và sự cố nặng hơn.
4. **Hệ thống DB có sự cố phục hồi tạm thời**: có thể cân nhắc retry bằng connection mới, nhưng nên bổ sung timeout, backoff, jitter, circuit breaker/giới hạn song song phù hợp.

Hướng chẩn đoán:

- Kiểm tra logs của datasource/pool/driver và thời điểm xảy ra lỗi; xác nhận thời gian chờ lấy connection, số connection active/idle, pool pending và DB max connections.
- Xác nhận có thay đổi secrets, DNS, firewall, TLS, database failover hoặc network policy không.
- Với lỗi trong giao dịch ghi, phân biệt **lệnh chưa gửi**, **lệnh đã gửi nhưng chưa nhận kết quả**, và **không xác định được trạng thái commit**.
- Ghi nhận class Spring, SQLState/vendor code và request/operation ID; hạn chế log trực tiếp tham số nhạy cảm.
- Chọn timeout và concurrency limit ở phía ứng dụng phù hợp; retry không thay thế việc sửa leak connection hoặc cấu hình sai.

Nếu kết quả ghi **không chắc chắn**, retry phải gắn với cơ chế idempotency, deduplication hoặc đối chiếu trạng thái bằng khóa nghiệp vụ. Xem mục 8.

## 4. Khóa và truy cập đồng thời: ba nhóm cơ chế khác nhau

### 4.1. Pessimistic locking: thực sự giữ lock trong database

Ví dụ hai transaction cùng muốn sửa hàng có khóa `account_id = 10`:

```sql
-- Trong một transaction của DB có hỗ trợ cú pháp tương ứng:
SELECT balance FROM accounts WHERE account_id = 10 FOR UPDATE;
-- Sau đó UPDATE accounts ... và COMMIT.
```

Một transaction có thể phải chờ transaction kia thả lock. Nếu chờ quá lâu, không lấy được lock hoặc tạo deadlock, database có thể từ chối một transaction. Spring có thể dịch lỗi đó thành `PessimisticLockingFailureException` hoặc `CannotAcquireLockException`, tùy driver và translator.

`SELECT ... FOR UPDATE` không mang tính portable tuyệt đối giữa mọi database. Cú pháp, thời hạn lock, chế độ `NOWAIT`/`SKIP LOCKED`, mức isolation và thời điểm giải phóng lock phụ thuộc hệ DB.

**Deadlock khác lock wait thông thường:**

```text
Transaction A: đã khóa bản ghi X -> chờ Y
Transaction B: đã khóa bản ghi Y -> chờ X
                                      ^
                                      |
                           Vòng chờ không giải được
```

Database thường phát hiện deadlock và chọn một transaction làm "victim" để rollback/abort. Trong môi trường Spring/JDBC, không nên chỉ kiểm tra tên `DeadlockLoserDataAccessException` vì lớp này đã deprecated và kết quả mapping khác nhau theo vendor. Xử lý nhóm `PessimisticLockingFailureException` khi thực sự có chính sách retry lock failure.

Giảm tranh chấp trước khi nghĩ đến retry: giữ transaction ngắn, lấy lock theo thứ tự nhất quán, tạo index cho điều kiện cập nhật, tránh I/O mạng hoặc công việc CPU dài trong transaction, và chỉ khóa những hàng thật cần thiết.

### 4.2. Optimistic locking: kiểm tra phiên bản khi ghi

Optimistic locking thường dùng cột `version` hoặc `row_version`. Hai người cùng đọc phiên bản 7:

```text
T0: A đọc version=7, B đọc version=7
T1: A UPDATE ... WHERE version=7 -> 1 hàng, version thành 8
T2: B UPDATE ... WHERE version=7 -> 0 hàng (xung đột)
T3: B đọc lại version=8 và quyết định thử tính lại hay báo người dùng
```

Một mẫu SQL:

```sql
UPDATE inventory
SET quantity = ?, row_version = row_version + 1
WHERE sku = ? AND row_version = ?;
```

Nếu update count trả **0**, có thể hàng đã bị thay đổi hoặc xóa; ứng dụng cần kiểm tra ngữ cảnh trước khi xử lý. **`JdbcTemplate.update(...)` chỉ trả số hàng bị ảnh hưởng; nó không tự động ném `OptimisticLockingFailureException` khi kết quả bằng 0.** Bạn có thể chủ động phát hiện và ném ngoại lệ tại tầng DAO. ORM như JPA/Hibernate hoặc một framework quản lý version có thể tự phát hiện conflict.

Retry optimistic conflict **khác** retry lock timeout: không được chạy lại cùng `UPDATE ... WHERE version=7` mãi mãi. Phải đọc trạng thái mới và tính lại thay đổi theo quy tắc nghiệp vụ; có khi người dùng cần quyết định khi hai bản sửa cùng một trường.

### 4.3. Isolation / serialization conflict: transaction không thể cùng hợp lệ

Ở mức isolation mạnh như `SERIALIZABLE`, database có thể từ chối một transaction khi lịch thực thi đồng thời không thể được chấp nhận theo bảo đảm isolation. Với PostgreSQL, SQLState `40001` thường biểu thị `serialization_failure`, nhưng lớp ngoại lệ Spring cụ thể phụ thuộc phiên bản/translator; cần bắt nhóm thích hợp và kiểm tra cause khi cần.

Việc thử lại trong tình huống này thường phải thực hiện **toàn bộ transaction**, bao gồm đọc lại các hàng và ra quyết định từ dữ liệu mới; chỉ chạy lại lệnh `UPDATE` cuối cùng với dữ liệu cũ có thể vẫn sai.

Isolation, lock và optimistic version là những cơ chế liên quan nhưng **không tương đương**. Khóa DB có thể chặn người khác, optimistic version phát hiện xung đột bằng điều kiện, còn isolation bảo đảm những tính chất quan sát dữ liệu trong transaction.

## 5. Quy tắc quyết định retry

Trước khi retry, cần trả lời lần lượt:

1. **Có phải lỗi có khả năng qua đi?** Lock contention/deadlock là ứng viên hợp lý; lỗi SQL sai, schema thiếu hoặc dữ liệu vi phạm ràng buộc thường cần sửa nguyên nhân.
2. **Trạng thái transaction cũ đã kết thúc/rollback chưa?** Không chạy lại câu SQL trong một transaction đã bị đánh dấu rollback-only hoặc transaction đang ở trạng thái lỗi. Với PostgreSQL, lỗi SQL có thể làm transaction hiện tại không thể tiếp tục cho đến rollback.
3. **Thao tác có an toàn để thực hiện lại không?** Một lời gọi chuyển tiền, phát sự kiện, gửi email hoặc trừ tồn kho có thể gây tác dụng phụ nếu đã commit một phần. Cần idempotency key, unique constraint, outbox hoặc cơ chế dedup khi cần.
4. **Retry có đọc và tính lại trạng thái mới không?** Với optimistic conflict và serialization failure, dữ liệu ban đầu có thể lỗi thời.
5. **Có giới hạn chặt chẽ không?** Chọn tối đa số attempt, timeout chung, backoff có jitter, giới hạn đồng thời và cách trả lỗi cuối cùng.
6. **Người dùng/hệ thống có cần biết conflict không?** Không nên tự động ghi đè quyết định người dùng chỉ để ép một yêu cầu thành công.

Ma trận quyết định:

| Trường hợp | Retry? | Điều kiện |
| --- | --- | --- |
| Deadlock/không lấy được lock | **Có thể** | Sau rollback, tạo transaction mới, bounded retry, giữ thao tác an toàn |
| Serialization failure | **Có thể** | Retry **toàn transaction** với dữ liệu đọc lại |
| Optimistic version conflict | **Có điều kiện** | Có thể hợp nhất thay đổi; đọc lại và tính lại, nếu không trả conflict |
| Transient resource failure | **Có điều kiện** | Tình trạng DB đã ổn; trạng thái commit được xác định hoặc có idempotency |
| Recoverable resource exception | **Sau phục hồi** | Tạo connection mới/khôi phục tài nguyên theo hướng dẫn rồi retry toàn transaction |
| Query timeout khi ghi | **Thận trọng** | Không biết chắc tác động/commit; cần xác minh hoặc idempotency trước khi thử |
| Không thể kết nối vì sai credentials/URL | **Không** | Sửa cấu hình/quyền |
| Trùng unique key | **Không retry nguyên xi** | Có thể là conflict nghiệp vụ hoặc kết quả thành công của lần gọi trước; kiểm tra theo idempotency key |
| Sai SQL/kiểu cột/sai quyền | **Không** | Sửa chương trình hoặc quyền |
| Database outage diện rộng | **Hạn chế tối đa** | Backoff/circuit breaker, ngừng gây thêm tải, quan sát hệ thống hồi phục |

"Retry 3 lần" phải được hiểu rõ: **3 attempts tổng cộng**, gồm lần đầu và tối đa 2 lần thử lại. Đừng để một lớp HTTP client retry 3 lần, tầng service retry 3 lần và driver tự retry 3 lần mà không kiểm soát, vì tổng số thao tác có thể tăng rất nhiều.

## 6. Retry đúng ranh giới transaction

### 6.1. Trình tự an toàn

```text
Attempt 1:
  BEGIN -> đọc dữ liệu -> kiểm tra -> ghi -> thất bại lock -> ROLLBACK
      |
      v
  Đánh giá exception -> backoff / jitter (không giữ transaction)
      |
      v
Attempt 2:
  BEGIN mới -> đọc lại dữ liệu -> tính lại -> ghi -> COMMIT
      |
      v
  Chỉ sau commit thành công mới công bố kết quả.
```

**Không bắt lỗi trong transaction rồi cố chạy lại trên cùng connection/transaction** khi database đã hủy hoặc đánh dấu transaction bị lỗi. Nếu code bắt và nuốt ngoại lệ, `@Transactional` có thể tưởng rằng phương thức đã thành công; đôi khi transaction vẫn rollback-only và gây `UnexpectedRollbackException` lúc commit.

Dùng `@Transactional` qua Spring proxy để đặt transaction ở service là cách thông dụng. Nếu kết hợp annotation retry (`@Retryable`) và `@Transactional`, cần bảo đảm cơ chế retry **bao ngoài** ranh giới transaction; thứ tự advice/proxy ảnh hưởng đến điều này. Đừng dựa vào lời gọi nội bộ cùng bean (`this.method()`) để kích hoạt annotation proxy. Với tình huống cần kiểm soát rõ, `TransactionTemplate` có thể đặt mỗi attempt vào một transaction tường minh.

### 6.2. Mẫu code retry lock failure bằng `TransactionTemplate`

Mảnh code Java 17 sau minh họa wrapper **có giới hạn ba attempts**, chỉ bắt `PessimisticLockingFailureException`. Hàm này được gọi khi **không có transaction đang mở ở caller**; `TransactionTemplate` với propagation mặc định `REQUIRED` khi đó tạo transaction mới ở mỗi lần gọi.

```java
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.transaction.support.TransactionTemplate;

static <T> T runWithLockRetry(
        TransactionTemplate tx,
        Supplier<T> databaseWork) {

    final int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            // Toàn bộ đọc/tính/ghi trong attempt này thuộc một transaction.
            return tx.execute(status -> databaseWork.get());
        } catch (PessimisticLockingFailureException lockFailure) {
            // Spring đã kết thúc/rollback transaction bị lỗi trước khi
            // tx.execute(...) ném ngoại lệ ra ngoài.
            if (attempt == maxAttempts) {
                throw lockFailure;
            }

            // 40ms, 80ms + jitter 0..19ms.
            long delayMs = 40L * (1L << (attempt - 1))
                + ThreadLocalRandom.current().nextLong(20L);
            try {
                Thread.sleep(delayMs);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Retry interrupted", interrupted
                );
            }
        }
    }
    throw new IllegalStateException("Unreachable retry state");
}
```

Đây là **mảnh mã để tích hợp vào lớp Java đã có `TransactionTemplate` và nghiệp vụ**, không phải chương trình độc lập. Nó không retry `OptimisticLockingFailureException`, `QueryTimeoutException`, resource failure, `DuplicateKeyException` hay tất cả `DataAccessException`.

Ví dụ gọi ở tầng service:

```java
// Giả định tx, jdbc và orderId đã được cấu hình.
// Hàm cần được gọi ở ngoài transaction đang hoạt động.
runWithLockRetry(tx, () -> {
    int quantity = jdbc.queryForObject(
        "SELECT quantity FROM inventory WHERE id = ?",
        Integer.class, orderId
    );
    // Kiểm tra điều kiện nghiệp vụ bằng dữ liệu vừa đọc,
    // rồi thực hiện các câu SQL cần thiết trong cùng transaction.
    return quantity;
});
```

Lời gọi minh họa trên chỉ đọc dữ liệu để cho thấy phạm vi callback; trong thực tế đặt **toàn bộ** các bước đọc, xác thực và ghi liên quan vào `databaseWork`. Không gửi email/call API không hỗ trợ rollback ngay trong callback: nếu retry thì tác dụng phụ bên ngoài DB có thể xảy ra nhiều lần.

Một giới hạn nữa: `Thread.sleep` chặn thread hiện tại. Đoạn code phù hợp để giải thích thao tác đồng bộ và delay rất ngắn, không phải cấu hình bắt buộc cho hệ thống throughput cao hoặc reactive. Có thể dùng thư viện retry như Spring Retry với chính sách ngoại lệ, attempt, backoff/jitter và transaction advice rõ ràng; mục tiêu quan trọng là **đúng ranh giới** chứ không phải tự viết vòng lặp ở mọi service.

## 7. Ví dụ Java 17+ chạy được: optimistic conflict và đọc lại trước khi thử

Ví dụ dưới đây không tạo hai luồng chạy thật; nó **cố ý cho hai "writer" đọc cùng snapshot** để tái hiện xung đột một cách xác định, giúp quan sát chính xác update count của `JdbcTemplate`. Một hàng tồn kho bắt đầu với `quantity = 10` và `row_version = 0`. Writer A cộng 3, writer B dự định cộng 4 nhưng đã đọc phiên bản cũ.

Cấu trúc:

```text
concurrency-demo/
├── build.gradle
└── src/main/java/OptimisticRetryDemo.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'OptimisticRetryDemo'
}
```

Nội dung `src/main/java/OptimisticRetryDemo.java`:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class OptimisticRetryDemo {

    record StockSnapshot(int quantity, long version) {}

    static StockSnapshot load(JdbcTemplate jdbc) {
        return jdbc.queryForObject("""
            SELECT quantity, row_version FROM stock WHERE sku = ?
            """, (rs, rowNum) -> new StockSnapshot(
                rs.getInt("quantity"),
                rs.getLong("row_version")
            ), "BOOK");
    }

    static void addStock(JdbcTemplate jdbc,
                         StockSnapshot snapshot,
                         int amount) {
        int updated = jdbc.update("""
            UPDATE stock
            SET quantity = ?, row_version = row_version + 1
            WHERE sku = ? AND row_version = ?
            """,
            snapshot.quantity() + amount,
            "BOOK",
            snapshot.version()
        );

        if (updated != 1) {
            // JdbcTemplate.update trả số hàng, KHÔNG tự ném
            // OptimisticLockingFailureException khi updated == 0.
            throw new OptimisticLockingFailureException(
                "The stock row changed since it was read"
            );
        }
    }

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:concurrency_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.execute("""
            CREATE TABLE stock (
                sku VARCHAR(20) PRIMARY KEY,
                quantity INT NOT NULL,
                row_version BIGINT NOT NULL
            )
            """);
        jdbc.update(
            "INSERT INTO stock (sku, quantity, row_version) VALUES (?, ?, ?)",
            "BOOK", 10, 0L
        );

        // Hai writer cùng quan sát version=0.
        StockSnapshot writerA = load(jdbc);
        StockSnapshot writerB = load(jdbc);
        System.out.println(
            "Both read version: " + writerA.version()
        );

        addStock(jdbc, writerA, 3);
        System.out.println("Writer A: +3 applied");

        try {
            addStock(jdbc, writerB, 4);
        } catch (OptimisticLockingFailureException conflict) {
            System.out.println("Writer B attempt 1: conflict");
        }

        // Chỉ thử lại sau khi đọc lại phiên bản và số lượng mới.
        StockSnapshot fresh = load(jdbc);
        addStock(jdbc, fresh, 4);
        System.out.println("Writer B attempt 2: +4 applied");

        StockSnapshot result = load(jdbc);
        System.out.println(
            "Final: quantity=" + result.quantity()
            + ", version=" + result.version()
        );
    }
}
```

Chạy từ thư mục `concurrency-demo` bằng Gradle đã cài:

```bash
gradle --quiet run
```

Nếu dự án có Gradle Wrapper riêng thì dùng `./gradlew --quiet run` (Windows: `.\gradlew.bat --quiet run`). Với dữ liệu cố định và H2 in-memory, stdout của chương trình:

```text
Both read version: 0
Writer A: +3 applied
Writer B attempt 1: conflict
Writer B attempt 2: +4 applied
Final: quantity=17, version=2
```

**Vì sao kết quả là 17?** Writer A đọc 10/version 0, cập nhật thành 13/version 1. Writer B dùng snapshot cũ 10/version 0; `WHERE row_version = 0` không còn khớp nên `updated = 0`, **không có lần cộng 4 sai vào cơ sở dữ liệu**. B đọc lại 13/version 1, tính 13+4 rồi cập nhật thành 17/version 2.

Ba điều cần nhớ từ ví dụ:

- Lớp exception của Spring chỉ xuất hiện vì **DAO chủ động ném** nó sau khi thấy `updated != 1`; `JdbcTemplate` không có khả năng biết nghiệp vụ kỳ vọng `row_version`.
- Tranh chấp trong ví dụ được mô phỏng bằng **snapshot cũ**, không phải lock timeout hoặc deadlock thật. Đừng dùng kết quả này để kết luận về mức khóa/timing của một database khác.
- Với bài toán cộng số lượng, phép cộng có thể áp dụng lại sau khi đọc mới. Nếu hai người cùng sửa "địa chỉ giao hàng", việc tự chọn giá trị mới để ghi đè thường không đúng; nên trả conflict để người dùng quyết định.

Trong ứng dụng production, nhiều bước như đọc, kiểm tra tồn kho, cập nhật và ghi audit cần transaction phù hợp. Ví dụ console tập trung minh họa **phép so khớp version và xử lý stale read**; mỗi `UPDATE` riêng lẻ là một thao tác SQL nguyên tử của H2 trong chế độ autocommit.

## 8. Retry và idempotency khi kết quả ghi chưa rõ

Một tình huống nguy hiểm:

```text
Client gửi lệnh tạo đơn hàng tới DB
  -> DB tạo đơn, có thể đã commit
  -> mất mạng trước khi client nhận câu trả lời
  -> client tưởng thất bại, gửi lại
  -> có thể tạo đơn thứ hai
```

Trong trường hợp này, chỉ phân loại exception là transient **không đủ**. Chúng ta phải làm cho yêu cầu lặp lại có thể xác định được kết quả.

Một thiết kế thường dùng:

```sql
CREATE TABLE payment_request (
    request_key VARCHAR(100) PRIMARY KEY,
    account_id BIGINT NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

`request_key` do ứng dụng xác định cho **một thao tác logic duy nhất** và được tái sử dụng trong các lần retry. Unique/primary-key constraint giúp DB không có hai hàng cùng khóa. Tuy nhiên **trùng khóa không có nghĩa luôn thành công**: ứng dụng phải kiểm tra bản ghi có cùng payload/đích đến và trạng thái hợp lệ trước khi trả lại kết quả cũ. Nếu cùng khóa nhưng payload khác, cần từ chối.

Khi nghiệp vụ chuyển tiền:

- Chọn khóa yêu cầu ổn định, unique constraint, thao tác DB có transaction và kiểm tra trạng thái.
- Nếu không nhận được kết quả ghi, **truy vấn theo khóa yêu cầu** để xác định đã xử lý hay chưa; nếu chưa thể truy vấn, tiếp tục theo cơ chế phục hồi có kiểm soát.
- Nếu có gửi sự kiện tới message broker/email sau ghi DB, cân nhắc transactional outbox hoặc một cơ chế dedup ở bên nhận. Không lặp phát sự kiện trực tiếp trong callback có retry mà không bảo đảm chống trùng.
- Trả trạng thái rõ ràng khi kết quả vẫn chưa xác định; không giả vờ toàn bộ transaction chắc chắn đã rollback chỉ vì client gặp timeout.

Idempotency không phải chỉ là "đặt unique index": nó gồm **khóa thao tác, kiểm tra tham số, lưu trạng thái và cách trả kết quả** của một yêu cầu được gửi nhiều lần.

## 9. Thực hành kiểm thử lỗi khóa và retry

Kiểm thử tích hợp nên dùng driver và database cùng loại với môi trường sản xuất khi cần đo hành vi lock thực tế. H2 phù hợp cho ví dụ version ở mục 7, nhưng không bảo đảm giống PostgreSQL, MySQL hoặc SQL Server về deadlock, timeout, SQLState hay translation.

| Tình huống thử | Cách tạo điều kiện | Điều cần xác minh |
| --- | --- | --- |
| Optimistic conflict | Đọc cùng `row_version` ở hai luồng/đối tượng, cập nhật theo thứ tự | Writer sau cập nhật 0 hàng, code nhận biết conflict, không lost update |
| Lock timeout | Connection/transaction A giữ lock, B cố lấy lock với timeout hữu hạn | Loại lỗi thực tế, rollback B, không giữ transaction lỗi |
| Deadlock | Hai transaction lấy lock hai hàng theo thứ tự ngược nhau | Database hủy một transaction; retry được nếu tạo transaction mới |
| Serialization failure | Transaction ở mức isolation thích hợp, truy cập các hàng dẫn tới xung đột | Retry đọc/tính/ghi toàn transaction, không lặp chỉ câu cuối |
| Mất connection trước query | Dừng DB/đứt mạng hoặc dùng test harness phù hợp | Không retry vô hạn, thông báo đúng, có backoff |
| Mất connection quanh commit | Tạo lỗi mạng ở bước cuối giao dịch | Không nhân đôi dữ liệu sau retry; idempotency key xử lý trạng thái chưa rõ |
| Dữ liệu sai (unique/FK/NOT NULL) | Ghi bản ghi vi phạm constraint | Không retry lỗi cố định; trả lỗi nghiệp vụ hoặc sửa input |
| Hết số attempt | Giả lập lỗi lock trên mọi lần | Đúng số attempts, exception cuối được truyền, không nuốt lỗi |
| Interrupt khi backoff | Interrupt thread đang chờ | Khôi phục interrupt flag, dừng retry |
| Hiệu ứng ngoài DB | Callback có gửi message / gọi API | Không phát lặp; dùng outbox hoặc cơ chế tương đương |

Đừng xây test chỉ dựa vào `Thread.sleep(100)` để "hy vọng" hai transaction tranh chấp. Nên dùng đồng bộ hóa xác định (ví dụ `CountDownLatch`), hai connection thực sự độc lập, giới hạn thời gian và assertion trạng thái DB cuối cùng. Với deadlock, lock ordering, isolation và chiến lược timeout phải dựa vào database đích.

## 10. Quan sát và vận hành khi lỗi tái diễn

Ngoài xử lý exception, ứng dụng production cần số liệu để biết retry đang cứu hệ thống hay làm sự cố nặng hơn:

- **Attempts per operation**, retry count, tổng thời gian và kết quả cuối cùng; phân biệt "lần gọi ban đầu" với "số lần retry".
- **Nguyên nhân** theo class Spring, SQLState/vendor code, thao tác logic và nhóm database; tránh lộ mật khẩu, token, thông tin cá nhân hoặc toàn bộ dữ liệu nhạy cảm.
- **Pool metrics**: connection active/idle/pending, acquisition timeout, leak detection, DB max connections.
- **Lock metrics**: transaction duration, lock wait, deadlock count, statement timeout và số transaction bị rollback.
- **Giới hạn**: max attempts, overall deadline, jitter, bounded concurrency/circuit breaker đối với resource outage.

Báo lỗi cuối cùng có ngữ cảnh nghiệp vụ và `cause`, không trả trực tiếp stack trace hoặc SQL nhạy cảm cho client. Conflict do người khác cập nhật có thể được biểu diễn thành HTTP `409 Conflict` khi API có hợp đồng như vậy; lỗi DB unavailable thường là lỗi hạ tầng tạm thời, cần phản hồi phù hợp và tránh khẳng định lệnh đã được hủy nếu commit không rõ.

## 11. Các sai lầm điển hình

**Sai lầm 1: retry mọi `DataAccessException`.** SQL sai, unique key bị trùng, thiếu quyền và schema lỗi không tự biến mất. Retry mù gây thêm tải, che giấu lỗi thực và có thể nhân đôi tác dụng phụ.

**Sai lầm 2: chỉ catch `TransientDataAccessException` và cho rằng đã xử lý mọi lỗi mất DB.** `CannotGetJdbcConnectionException` thuộc nhánh **non-transient**. Khả năng phục hồi thực tế cần đánh giá độc lập với class hierarchy.

**Sai lầm 3: retry trong cùng transaction đã lỗi.** Transaction có thể bị rollback-only hoặc DB từ chối tiếp tục. Hãy để transaction cũ kết thúc rồi bắt đầu transaction mới cho lần thử tiếp theo.

**Sai lầm 4: retry optimistic conflict mà không đọc lại.** Phiên bản cũ sẽ tiếp tục không khớp. Với nghiệp vụ cần hòa giải thay đổi, phải đọc mới, tính lại hoặc trả conflict.

**Sai lầm 5: dùng lock nhưng giữ transaction quá lâu.** Gọi API ngoài, chạy job nặng hoặc chờ backoff khi đang giữ lock khiến tranh chấp tăng; giảm thời gian giữ lock và đưa delay ra **ngoài transaction**.

**Sai lầm 6: dùng `@Transactional` hoặc `@Retryable` trên lời gọi nội bộ cùng bean rồi tưởng proxy chạy.** Trong cấu hình proxy thông dụng, self-invocation không đi qua proxy; xác minh cách AOP advice được áp dụng, hoặc dùng `TransactionTemplate` khi cần minh bạch.

**Sai lầm 7: giả định timeout là rollback chắc chắn.** Client có thể mất kết nối sau khi DB commit. Đối với yêu cầu không idempotent, trước khi retry phải xác minh trạng thái hoặc có khóa chống trùng.

**Sai lầm 8: coi "deadlock" là lỗi code không thể retry.** Deadlock có thể là trạng thái tranh chấp tạm thời và database chọn một nạn nhân. Có thể retry transaction mới có giới hạn, đồng thời sửa thứ tự lấy lock để giảm tần suất.

**Sai lầm 9: không chặn retry storm.** Khi DB outage, hàng nghìn request cùng retry tức thì làm cạn pool và kéo dài thời gian phục hồi. Cần backoff có jitter, giới hạn attempt và theo dõi sức khỏe hệ thống.

**Sai lầm 10: nghĩ tất cả database ánh xạ lock error giống hệt nhau.** SQLState, vendor error code, class driver và translator Spring khác nhau. Viết test tích hợp với vendor production và ghi nhận ngoại lệ thực nhận thay vì hard-code suy đoán.

## 12. Câu hỏi tự đánh giá

**Câu 1.** `JdbcTemplate.update(...)` trả 0 khi cập nhật `WHERE id=? AND row_version=?`. Có tự ném `OptimisticLockingFailureException` không?

**Đáp án:** Không. JDBC trả update count; tầng DAO/ORM phải hiểu kỳ vọng và phát hiện conflict. Với JDBC thủ công có thể kiểm tra `updated == 0` rồi ném `OptimisticLockingFailureException` hoặc trả kết quả conflict phù hợp.

**Câu 2.** `CannotGetJdbcConnectionException` thuộc `TransientDataAccessException`?

**Đáp án:** Không. Nó thuộc `DataAccessResourceFailureException` dưới nhánh non-transient. Điều đó không khẳng định sự cố ngoài đời sẽ tồn tại mãi; phải phân tích nguyên nhân và chiến lược phục hồi riêng.

**Câu 3.** Transaction bị deadlock khi vừa đọc số dư, tính phí và cập nhật. Nên chạy lại mỗi `UPDATE` cuối cùng hay toàn bộ transaction?

**Đáp án:** Retry **toàn transaction** từ bước đọc trạng thái mới, sau khi transaction cũ rollback, với giới hạn attempts/backoff. Những bước tính toán phụ thuộc dữ liệu cũ cũng phải chạy lại.

**Câu 4.** Yêu cầu "tạo thanh toán" mất kết nối sau lúc gửi SQL. Có thể gọi lại ngay và tin rằng lần đầu thất bại?

**Đáp án:** Không. Có thể trạng thái commit chưa xác định. Cần idempotency key, xác minh trạng thái hoặc cơ chế phục hồi/dedup phù hợp.

**Câu 5.** Hai người sửa cùng địa chỉ giao hàng. Một người cập nhật trước khiến phiên bản của người còn lại bị stale. Có nên tự reload rồi ghi đè địa chỉ thứ hai?

**Đáp án:** Thường không nên. Trả conflict hoặc hiển thị khác biệt để người dùng quyết định; retry tự động chỉ phù hợp khi phép biến đổi và quy tắc hợp nhất dữ liệu thực sự an toàn.

**Câu 6.** Vì sao backoff phải đặt bên ngoài transaction?

**Đáp án:** Vì chờ trong transaction có thể tiếp tục giữ connection/lock và kéo dài tranh chấp. Nên rollback/đóng transaction cũ, sau đó chờ rồi mở transaction mới.

## 13. Ghi nhớ

- `DataAccessException` là lớp gốc của hệ ngoại lệ truy cập dữ liệu Spring; `JdbcTemplate` dịch `SQLException` nhưng mapping cụ thể phụ thuộc driver/translator.
- **Lỗi tài nguyên**, **pessimistic lock**, **optimistic conflict** và **lỗi dữ liệu cố định** có nguyên nhân và chính sách xử lý khác nhau.
- `PessimisticLockingFailureException` là nhánh phù hợp để nhận diện nhiều lỗi locking; hai lớp deadlock/serialization tên cũ đã deprecated trong Spring 6.0.3.
- `CannotGetJdbcConnectionException` thuộc nhánh **non-transient**. Một lỗi hạ tầng có thể phục hồi, nhưng không được đồng nhất khả năng phục hồi với khả năng retry an toàn.
- Với lỗi lock/serialization đủ điều kiện, retry **transaction mới**, từ bước đọc và tính toán, có backoff/jitter và max attempts.
- Với optimistic locking, phải nhận biết update count 0 hoặc ngoại lệ từ ORM, **đọc lại và hòa giải dữ liệu**; không tự động ghi đè quyết định người dùng.
- Mọi retry thao tác ghi cần xét **rollback/commit chưa rõ, idempotency và hiệu ứng ngoài DB**. Cơ chế retry phải có giới hạn và có thể quan sát.

### Tài liệu tham khảo

- Spring Framework — [JDBC Core và `SQLExceptionTranslator`](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html).
- Spring Framework 6.2 — [`DataAccessException` và các lớp con](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/DataAccessException.html).
- Spring Framework 6.2 — [`TransientDataAccessException`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/TransientDataAccessException.html).
- Spring Framework 6.2 — [`DataAccessResourceFailureException`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/DataAccessResourceFailureException.html).
- Spring Framework 6.2 — [`PessimisticLockingFailureException`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/PessimisticLockingFailureException.html).
- Spring Framework 6.2 — [`OptimisticLockingFailureException`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/OptimisticLockingFailureException.html).
- Spring Framework — [`@Transactional` và rollback mặc định](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- Spring Retry — [Reference Documentation](https://docs.spring.io/spring-retry/reference/).
