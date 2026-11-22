# Log ở repository trong Java — exception, transaction, SQL và trách nhiệm logging

## 1. Vai trò của repository và câu hỏi “có nên log tại đây?”

Trong ứng dụng Java phân tầng, **repository/DAO** cung cấp thao tác truy cập dữ liệu qua JDBC, JPA/Hibernate, Spring Data hoặc storage adapter. Repository thường nằm dưới application service và trên database:

```text
HTTP Controller / Message Consumer
             |
     Application Service
    (use case, transaction)
             |
       Repository / DAO
     (query, mapping, data)
             |
    JDBC / JPA / Driver / DB
```

Vì ở gần database, repository có thể biết loại operation, datasource, số hàng đọc/ghi, exception kỹ thuật và latency. Tuy nhiên, log quá nhiều ở đây làm tăng chi phí I/O/CPU, gây duplicate với service/controller, và thậm chí lộ SQL parameter, password hoặc dữ liệu cá nhân.

Trong nhóm **Logging và exception**, bài **Log ở repository** nhấn mạnh bốn mục tiêu: **log đúng thông tin kỹ thuật**, **giữ đúng semantics của exception và transaction**, **không ghi trùng lỗi**, **không phát tán dữ liệu nhạy cảm**. Không có quy tắc rằng mọi `repository.save(...)` đều phải ghi INFO.

Hình dung một request thành công:

```text
GET /api/orders/42
  → HTTP filter: request summary + status/duration
  → OrderService: quyết định đọc đơn hàng
  → OrderRepository: SELECT...
  → DB: một hàng
  → Service: trả OrderView
  → HTTP 200
```

Đã có HTTP summary thì thường **không cần** một dòng `"find order 42"` tại controller, service và repository. Repository chỉ cần diagnostic ở DEBUG hoặc metrics/tracing khi có câu hỏi kỹ thuật cần trả lời.

## 2. Phân chia ownership log giữa các tầng

| Event | Nơi sở hữu thường hợp lý | Level/tín hiệu |
| --- | --- | --- |
| Request bắt đầu/kết thúc, status, duration | HTTP filter/Observation | INFO, timer metrics |
| Thay đổi trạng thái nghiệp vụ | Service/domain event | INFO hoặc audit |
| Một SQL query được tạo | Hibernate/JDBC instrumentation | DEBUG theo nhu cầu |
| Query/connection acquisition chậm | Repository wrapper/metrics | WARN có ngưỡng, histogram |
| Cache miss, batch fetch | Repository/adapter | DEBUG hoặc metric |
| Không tìm thấy record | Service/controller quyết định ý nghĩa | INFO/DEBUG hoặc không log |
| Exception không được xử lý | Boundary (HTTP, consumer, scheduler) | ERROR một lần |
| Retry storage có chủ đích | Retry owner | WARN cho attempt, outcome cuối |
| Transaction commit bền vững | Post-commit/outbox/audit infrastructure | Business event có contract |

Quy tắc này là **guideline kiến trúc**, không phải API Java bắt buộc. Repository có thể là điểm quan sát cuối cùng trong một CLI job, library hoặc standalone connector; khi đó nó có thể sở hữu log WARN/ERROR. Dù ở đâu, **mỗi failure phải có chủ sở hữu log tổng kết**, tránh catch–log–rethrow nhiều tầng mà không thêm thông tin.

### 2.1. Lợi ích của log có cấu trúc

Một event có cấu trúc:

```text
WARN event=repository.slow_operation
     operation=find_order entity=Order datasource=primary
     duration_ms=1280.400 trace_id=<safe-trace-id>
```

Các trường `event`, `operation`, `entity`, `datasource`, `duration_ms` giúp tìm lỗi nhanh hơn câu “DB is slow”. Trong ứng dụng thật, `trace_id` phải được instrumentation cung cấp; không copy placeholder thành dữ liệu sản xuất. Không cần in nguyên query params hoặc object entity để chẩn đoán duration.

## 3. Phân biệt ba tình huống: FOUND, NOT_FOUND và ERROR

`repository.findById(42L)` có thể:
1. Trả entity: truy vấn thành công.
2. Trả `Optional.empty()`: không có record theo điều kiện, không tự là lỗi database.
3. Ném exception: **không biết kết quả do truy cập dữ liệu bị lỗi**.

Đừng đánh đồng “không tồn tại” với “không truy vấn được”.

| Tình huống | Kết quả tầng repository | Hành vi tầng service/boundary |
| --- | --- | --- |
| Row tồn tại | `Optional.of(entity)` | Chuyển DTO, trả thành công |
| Row không tồn tại | `Optional.empty()` | Có thể HTTP 404 hoặc một kết quả hợp lệ |
| Database unavailable | Exception | Báo lỗi hạ tầng, thường khác 404 |
| Conflict khi ghi | Exception được phân loại | Conflict/retry nếu nghiệp vụ cho phép |
| Query timeout | Exception | Đánh giá timeout budget và khả năng retry |

Ví dụ Spring Data JPA:

```java
Optional<OrderEntity> found = orderRepository.findById(orderId);
if (found.isEmpty()) {
    return Optional.empty();
}
return found;
```

Đây là **đoạn minh họa** trong method có `OrderEntity`, `orderRepository` và kiểu trả về phù hợp, không phải file Java độc lập. Không log ERROR chỉ vì `Optional.empty()`; service hiểu ngữ nghĩa use case tốt hơn repository.

## 4. Exception trong repository: propagate, translate hay recover?

Khi database call lỗi, repository có các lựa chọn:

- **Propagate:** để exception đi lên tầng có quyền quyết định outcome, thường là mặc định đúng.
- **Translate:** chuyển từ exception của driver/JPA thành abstraction phù hợp, giữ original cause nếu có thể.
- **Recover:** fallback/retry theo policy đã thiết kế và hiểu idempotency.
- **Log kỹ thuật:** nếu có dữ kiện chẩn đoán quan trọng chỉ tồn tại ở repository, không chứa secret.

Mẫu sai phổ biến:

```java
try {
    repository.save(order);
} catch (RuntimeException ex) {
    log.error("Saving order failed", ex);
    throw ex;
}
```

Nếu service và global exception handler cũng log-and-rethrow, một failure tạo **ba stack trace** gần giống nhau. Nó làm nhiễu log và có thể tăng chi phí ingest. Nếu không thể xử lý lỗi tại đây, thường chỉ cần:

```java
repository.save(order);
```

Tầng có khả năng quyết định HTTP response, retry, dead-letter hoặc fallback sẽ log **một event kết quả** có operation/error type/correlation ID. Nếu một lớp cần bổ sung context, có thể bọc exception và giữ `cause`, không bắt buộc in log ngay tại mỗi lớp.

### 4.1. Không nuốt exception

Ví dụ có rủi ro:

```java
try {
    repository.save(order);
} catch (DataAccessException ex) {
    log.warn("Database write failed");
}
return successResponse;
```

Method trả thành công giả dù write thất bại. Với Spring transaction, một lỗi có thể khiến transaction được đánh dấu rollback-only, dẫn tới `UnexpectedRollbackException` khi kết thúc. Chỉ catch rồi tiếp tục nếu đã có recovery/compensation hợp lệ và kết quả nghiệp vụ thực sự đúng.

## 5. Java 17+ runnable: log ở repository và ở request boundary

Ví dụ dùng **`java.util.logging` (JUL)**, không cần Spring hay database thật. Repository in-memory mô phỏng ba kết quả: found, not found và exception. Repository ghi diagnostic `FINE`; boundary ghi outcome một lần. Custom Handler trong bộ nhớ đảm bảo stdout xác định, không phụ thuộc timestamp hoặc cấu hình logger của máy.

Lưu thành `RepositoryLogDemo.java`:

```java
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class RepositoryLogDemo {
    private static final class Lines extends Handler {
        private final StringBuilder output = new StringBuilder();

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            output.append(record.getLevel().getName())
                  .append(" ")
                  .append(record.getMessage())
                  .append("\n");
        }

        @Override public void flush() { }
        @Override public void close() { }

        String text() { return output.toString(); }
    }

    private static final class StoreUnavailable extends RuntimeException {
        StoreUnavailable() { super("simulated storage failure"); }
    }

    private static final class InMemoryOrderRepository {
        private final Logger log;
        private final Map<Long, String> rows = Map.of(42L, "PAID");

        InMemoryOrderRepository(Logger log) {
            this.log = log;
        }

        String findStatus(long id) {
            log.fine("event=repository.lookup entity=Order id=" + id);
            if (id == 9L) {
                throw new StoreUnavailable();
            }
            return rows.get(id);
        }
    }

    private static void handleRequest(long id,
                                      InMemoryOrderRepository repo,
                                      Logger requestLog) {
        try {
            String status = repo.findStatus(id);
            if (status == null) {
                requestLog.info("event=order.lookup outcome=NOT_FOUND id=" + id);
            } else {
                requestLog.info("event=order.lookup outcome=FOUND id=" + id
                        + " status=" + status);
            }
        } catch (StoreUnavailable ex) {
            requestLog.warning("event=order.lookup outcome=ERROR "
                    + "error_type=STORE_UNAVAILABLE id=" + id);
        }
    }

    public static void main(String[] args) {
        Logger repoLog = Logger.getLogger("demo.repository");
        Logger requestLog = Logger.getLogger("demo.request");
        Lines handler = new Lines();
        handler.setLevel(Level.ALL);

        repoLog.setLevel(Level.FINE);
        requestLog.setLevel(Level.INFO);
        repoLog.setUseParentHandlers(false);
        requestLog.setUseParentHandlers(false);
        repoLog.addHandler(handler);
        requestLog.addHandler(handler);

        try {
            InMemoryOrderRepository repo = new InMemoryOrderRepository(repoLog);
            handleRequest(42L, repo, requestLog);
            handleRequest(77L, repo, requestLog);
            handleRequest(9L, repo, requestLog);
            System.out.print(handler.text());
        } finally {
            repoLog.removeHandler(handler);
            requestLog.removeHandler(handler);
            handler.close();
        }
    }
}
```

Chạy:

```bash
javac --release 17 RepositoryLogDemo.java
java RepositoryLogDemo
```

Stdout chính xác:

```text
FINE event=repository.lookup entity=Order id=42
INFO event=order.lookup outcome=FOUND id=42 status=PAID
FINE event=repository.lookup entity=Order id=77
INFO event=order.lookup outcome=NOT_FOUND id=77
FINE event=repository.lookup entity=Order id=9
WARNING event=order.lookup outcome=ERROR error_type=STORE_UNAVAILABLE id=9
```

Tại ID 9, repository **ném lỗi** mà không in stack trace; boundary nhận và ghi một WARNING duy nhất. Hai logger có tên khác nhau không nằm trong quan hệ cha-con trong ví dụ, mỗi logger có một handler và `setUseParentHandlers(false)`, nên không tạo duplicate do propagation.

Đây là **demo của logging architecture**, không phải cách triển khai JDBC in-memory production. Với request HTTP thật, boundary phải trả response status thích hợp hoặc thực hiện retry/dead-letter theo contract, thay vì chỉ catch rồi kết thúc như demo. `id` là giá trị tổng hợp; định danh người dùng/đơn hàng trong hệ thống thật cần xem chính sách privacy trước khi log.

### 5.1. Tại sao log ở FINE/DEBUG?

Log mức DEBUG (JUL tương ứng gần nhất là `FINE`) thường thích hợp để khảo sát operation nội bộ mà không bắt buộc xuất ra production ở INFO. Khi tắt mức thấp, ứng dụng tránh một phần chi phí sinh event; nhưng các chuỗi nối trước lời gọi JUL có thể vẫn được tạo, nên với log đắt đỏ có thể cân nhắc `logger.isLoggable(Level.FINE)` hoặc API deferred formatting phù hợp.

Không nên log toàn bộ entity, JDBC parameters hoặc kết quả truy vấn dù ở FINE/DEBUG: developer có thể bật debug tạm tại môi trường chứa dữ liệu thật.

## 6. Spring Data JPA: trách nhiệm của repository interface

Một repository Spring Data JPA:

```java
package com.example.orders;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderJpaRepository
        extends JpaRepository<OrderEntity, Long> {
}
```

`OrderEntity` là entity có trong dự án. Đoạn code này cần Spring Data JPA, Jakarta Persistence và datasource cấu hình; không biên dịch độc lập chỉ với JDK.

Service quyết định ý nghĩa nghiệp vụ:

```java
package com.example.orders;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderQueryService {
    private final OrderJpaRepository orders;

    public OrderQueryService(OrderJpaRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderView find(long id) {
        OrderEntity entity = orders.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
        return new OrderView(entity.getId(), entity.getStatus());
    }
}
```

`OrderView`, `OrderNotFoundException`, `OrderEntity` là kiểu riêng của dự án nên class này chỉ minh họa kiến trúc. Khi không tìm thấy, service chuyển sang domain exception; HTTP boundary có thể map thành 404. Không nhất thiết log một dòng ERROR ở repository.

### 6.1. Transaction configuration trong Spring Data JPA

Theo tài liệu Spring Data JPA, các CRUD methods **kế thừa** từ `CrudRepository` thường sử dụng transaction configuration của `SimpleJpaRepository`: read operations mặc định `readOnly=true`, write operations dùng `@Transactional` thông thường. **Các query methods tự khai báo không mặc nhiên có cùng transaction configuration** trong mọi trường hợp. Với use case gọi nhiều repository, transaction boundary thường nên ở service/facade.

Không tự kết luận một method `findBy...` luôn có read-only transaction, và không dựa riêng tên method để suy điều kiện commit hay flush.

## 7. `@Repository`, exception translation và DataAccessException

Spring hỗ trợ một hệ thống exception abstraction `org.springframework.dao.DataAccessException`. Khi có `PersistenceExceptionTranslationPostProcessor` và translator phù hợp, bean `@Repository` có thể được áp dụng exception translation từ persistence exceptions của JPA/Hibernate/ORM.

**Không đúng** khi nói annotation `@Repository` tự động dịch **mọi** checked `SQLException` từ raw JDBC. Với `JdbcTemplate`, Spring sử dụng `SQLExceptionTranslator` phù hợp trong pipeline JDBC; raw JDBC tự viết cần exception contract rõ.

Một số loại:

| Loại exception | Thường mang nghĩa | Hành động |
| --- | --- | --- |
| `DataAccessException` | Gốc của hierarchy Spring DAO | Không retry mọi subtype |
| `DataIntegrityViolationException` | Vi phạm một ràng buộc DB | Đọc constraint/driver cause an toàn |
| `DuplicateKeyException` | Unique/primary key conflict | Domain conflict khi đúng nghiệp vụ |
| `OptimisticLockingFailureException` | Cập nhật xung đột version | Retry có điều kiện hoặc báo 409 |
| `CannotGetJdbcConnectionException` | Không lấy được connection | Kiểm tra DB/pool/network |
| `QueryTimeoutException` | Query vượt timeout theo translator | Timeout budget và query plan |
| `EmptyResultDataAccessException` | API kỳ vọng hàng nhưng không có | Có thể là kết quả không tồn tại |

Exception mapping chịu ảnh hưởng của driver, dialect, công nghệ truy cập và thao tác; `DataIntegrityViolationException` có thể là unique, foreign key hoặc non-null constraint. Không map tất cả thành HTTP 409 chỉ vì trông như conflict.

## 8. Một lỗi, một log ở boundary

`Repository` thường không biết request sẽ được retry, có fallback hay được trả thành HTTP 503. Boundary mới có đầy đủ thông tin để quyết định log cuối:

```text
Driver/JPA -> CannotGetJdbcConnectionException
Repository -> propagate
Service -> propagate nếu không thể phục hồi
HTTP handler -> log ERROR một lần + trả HTTP 503
```

Ví dụ method trong class `@RestControllerAdvice` của Spring MVC:

```java
@ExceptionHandler(CannotGetJdbcConnectionException.class)
ResponseEntity<ProblemDetail> storageUnavailable(
        CannotGetJdbcConnectionException ex) {
    log.error("event=storage.unavailable "
            + "error_type={} operation={}",
            ex.getClass().getSimpleName(), "read_order");

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Storage temporarily unavailable");
    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(problem);
}
```

Đây là method minh họa với SLF4J logger và imports Spring Web; nó **không độc lập**. Status 503 chỉ phù hợp tình huống connection unavailable trong ví dụ, không áp cho mọi DataAccessException. Log không in `ex.getMessage()` vì nội dung đó có thể mang JDBC URL, SQL parameters hay credential.

Khi service cần đổi exception kỹ thuật sang domain exception:

```java
try {
    repository.reserve(orderId);
} catch (OptimisticLockingFailureException ex) {
    throw new OrderConcurrentUpdateException(orderId, ex);
}
```

`OrderConcurrentUpdateException` là kiểu tự định nghĩa có constructor lưu `cause` gốc. Không cần `log.error` trước khi ném nếu global handler đã nhận ownership ghi lỗi. Việc giữ cause cho phép chẩn đoán stack trace tại đúng nơi được phép ghi.

## 9. Transaction: `save`, flush và commit khác nhau

Anti-pattern:

```java
@Transactional
public void createOrder(Order order) {
    repository.save(order);
    log.info("Order committed id={}", order.getId());
}
```

Trong JPA, `save` có thể cập nhật persistence context; SQL có thể được thực thi khi flush/commit tùy provider/ID strategy. `saveAndFlush` đẩy SQL ra sớm nhưng **không có nghĩa transaction đã commit**. Sau khi method return, transaction interceptor vẫn có thể gặp exception tại commit. Vì vậy log `"committed"` in trước đó có thể sai.

Nếu chỉ log hành động trong transaction, dùng wording trung thực như `"save attempted"` hoặc `"entity staged"`; không tự tuyên bố commit success.

Nếu cần audit hoặc event phát ra **sau commit**, có các hướng:
- Spring `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chạy callback theo phase tương ứng, nhưng callback in-memory **không bảo đảm durable delivery sau crash**.
- Transactional outbox ghi event trong cùng transaction với thay đổi dữ liệu để worker khác publish sau đó.
- Audit trail có ID/sequence, retention và durability phù hợp yêu cầu nghiệp vụ.

Không dùng một dòng INFO của AsyncAppender làm chứng cứ chắc chắn về commit hoặc lưu bền vững.

### 9.1. Rollback và lỗi checked/unchecked

Trong Spring, mặc định transaction thường rollback với `RuntimeException` hoặc `Error`, còn checked exception có thể cần `rollbackFor`/cấu hình phù hợp. Nếu repository nuốt lỗi và chỉ ghi WARN, service có thể tưởng thao tác đã thành công hoặc gặp rollback-only ở commit.

Không nên tự retry bên trong transaction đã lỗi mà không biết nó còn usable hay đã rollback-only. Với retry transaction, cần policy tạo attempt/transaction hợp lệ mới ở tầng thích hợp.

### 9.2. Lỗi database đôi khi phát sinh sau method repository

Lazy-loading, `flush`, validation, transaction interceptor hoặc DB commit có thể ném exception sau khi một method repository đã return. Vì vậy bắt và log mọi lỗi tại từng method repository **không bao phủ tất cả lỗi**, đồng thời gây duplicate. Theo dõi cả transaction boundary và trace.

## 10. SQL logging: Hibernate 6 và nguy cơ bind parameters

Với Hibernate 6, các category dùng để chẩn đoán:

```properties
# Spring Boot application.properties - bật tạm khi cần
logging.level.org.hibernate.SQL=DEBUG

# Nguy hiểm khi có dữ liệu thật: ghi JDBC binding values.
# logging.level.org.hibernate.orm.jdbc.bind=TRACE

# Cũng có thể tiết lộ dữ liệu đọc từ ResultSet.
# logging.level.org.hibernate.orm.jdbc.extract=TRACE
```

- `org.hibernate.SQL` in generated SQL theo mức logging Hibernate.
- `org.hibernate.orm.jdbc.bind` ở TRACE có thể in **giá trị bind thực**: email, số tài khoản, token, password hash.
- `org.hibernate.orm.jdbc.extract` có thể in dữ liệu đọc.
- `hibernate.show_sql=true` đưa SQL ra console bằng cơ chế Hibernate, không hoàn toàn giống appender logger đã cấu hình; khó kiểm soát tập trung.

Các category của Hibernate 5 khác một phần so với Hibernate 6; luôn kiểm tra framework version. Không bật JDBC bind/extract TRACE trên production chứa dữ liệu nhạy cảm.

### 10.1. Placeholder SQL không tự bảo vệ khỏi leak log

Ví dụ:

```sql
SELECT id, status FROM orders WHERE customer_email = ?
```

`PreparedStatement` giúp parameterization, giảm SQL injection, nhưng TRACE của driver/Hibernate vẫn có thể log **email đã bind**. SQL text cũng có thể chứa literal nhạy cảm nếu app tự ghép query. Vì vậy nguyên tắc không in bí mật vẫn áp dụng ngay cả khi code dùng parameterized query.

Nên bật SQL DEBUG trong môi trường an toàn, dùng synthetic data, hạn chế người xem và tắt sau khi xử lý. Kiểm tra Collector, archive, dashboard và backup vì dòng log phát ra một lần có thể tồn tại lâu ở nhiều nơi.

## 11. JDBC: đo thời gian operation mà không in parameter

Đo duration bằng `System.nanoTime()`:

```java
public Optional<String> findStatus(long id) throws SQLException {
    long started = System.nanoTime();
    boolean completed = false;
    try (Connection c = dataSource.getConnection();
         PreparedStatement ps = c.prepareStatement(
                 "SELECT status FROM orders WHERE id = ?")) {

        ps.setLong(1, id);
        try (ResultSet rs = ps.executeQuery()) {
            Optional<String> result = rs.next()
                    ? Optional.ofNullable(rs.getString("status"))
                    : Optional.empty();
            completed = true;
            return result;
        }
    } finally {
        double millis = (System.nanoTime() - started) / 1_000_000.0;
        if (log.isDebugEnabled()) {
            log.debug("event=repository.operation "
                    + "operation=find_status entity=Order "
                    + "outcome={} duration_ms={}",
                    completed ? "OK" : "FAILED", millis);
        }
    }
}
```

Đây là snippet tích hợp, cần `javax.sql.DataSource`, `java.sql`, `Optional`, SLF4J logger và bảng DB. **Không chạy độc lập chỉ với JDK**. Nó đo cả lấy connection, prepare, execute và đọc một hàng, không chỉ thời gian CPU/database execute. Không in `id` hoặc bound value trong log để giảm nguy cơ dữ liệu nhạy cảm.

Đo elapsed bằng clock đơn điệu phù hợp hơn `System.currentTimeMillis()` vì wall-clock có thể được điều chỉnh. Nếu cần phân biệt pool wait và query execution, dùng timer/span riêng.

Snippet có `throws SQLException`: checked SQLException không tự được chuyển thành `DataAccessException` chỉ vì người viết thêm `@Repository`. Với Spring JDBC, `JdbcTemplate` thường là abstraction phù hợp để dùng exception translation và resource handling.

## 12. Log slow repository operations mà không spam

Ví dụ event:

```text
WARN event=repository.slow_operation
     operation=find_order entity=Order
     datasource=primary duration_ms=1280.4 trace_id=<safe-id>
```

Ngưỡng 1.000 ms chỉ là ví dụ. Một lookup nhỏ có thể cần ngưỡng thấp hơn; một report lớn có thể được thiết kế chạy lâu. Chọn dựa vào SLO, phân loại operation và bối cảnh.

Thiết kế nên:
- Đo metrics/histograms cho mọi operation quan trọng khi có thể.
- Log WARN cho slow requests đã vượt threshold, hoặc sample có kiểm soát.
- Gắn tên operation, datasource, duration, outcome và trace ID an toàn.
- Không gắn email, order ID, raw SQL hoặc request ID vào **metric tags** cardinality cao.
- Kiểm tra connection pool, lock, network, fetch, mapping trước khi kết luận DB execute chậm.
- Đo overhead formatting/appender; async queue đầy có thể block hoặc drop log.

Một request chậm có thể do pool wait 900 ms và query 10 ms; tổng repository time 910 ms không chứng minh SQL engine mất 910 ms.

## 13. Metrics, tracing, MDC và quyền riêng tư

| Tín hiệu | Dùng cho | Điều cần tránh |
| --- | --- | --- |
| Logs | Failure details/operation/error type | Dump entity/params, duplicate stack |
| Metrics | Query count, pool usage, p95/p99 | High-cardinality ID/raw SQL labels |
| Traces | HTTP → service → repository → DB | Sensitive query/credentials trong span |
| Audit | Business state change có retention | Dùng DEBUG repository thay audit store |

Các chỉ số hữu ích: pool active/idle/pending, connection acquisition time, query duration, timeout/deadlock rates, retries, SQL statements per HTTP request. Spring Boot với HikariCP/Micrometer có thể đã cung cấp một phần tín hiệu; kiểm tra trước khi tự xây logging cho mọi query.

MDC hoặc Log4j2 ThreadContext giúp gắn `trace_id`, `request_id` và operation vào logs. Ví dụ SLF4J:

```java
try (MDC.MDCCloseable ignored =
             MDC.putCloseable("operation", "find_order")) {
    return repository.findById(id);
}
```

Đây là snippet tích hợp cần `org.slf4j.MDC`. `try-with-resources` dọn context để tránh rò giữa request khi thread pool tái sử dụng. Với async tasks cần propagation phù hợp; MDC không tự chuyển giữa mọi thread.

Không đặt password, bearer token, cookie, JDBC URL có secret, user credential hay SQL parameters vào MDC, logging message, exception hoặc span attributes. Structured logging và placeholder `{}` **không tự mask dữ liệu**.

## 14. Retry và exception logging: phân biệt attempt với failure cuối

Một lỗi transient có thể retry khi có policy idempotency và timeout budget. Nhưng **không retry tất cả `DataAccessException`**: constraint violation hoặc thao tác write không idempotent có thể không hợp lệ khi retry.

Một ví dụ:

```text
WARN event=storage.retry operation=reserve_order
     attempt=2 max_attempts=3 reason=TRANSIENT
ERROR event=order.reserve_failed attempts=3
      error_type=STORAGE_UNAVAILABLE
```

Đây là **hai event có ý nghĩa khác nhau**: một retry đã xảy ra và một kết quả thất bại sau khi hết số lần thử. Chúng không phải duplicate nếu event/attempt metadata rõ. Không cần log stack trace ở từng retry khi đã có failure cuối, trừ khi nghiệp vụ chẩn đoán yêu cầu.

Nếu retry cần transaction mới, policy phải ở lớp bao ngoài transaction; retry trong transaction bị rollback-only có thể không phục hồi. Với optimistic locking, chỉ retry khi thao tác có thể chạy lại an toàn và được use case cho phép.

## 15. Batch và N+1: khi INFO mỗi query trở thành vấn đề

Một controller có thể gây N+1, ví dụ lấy 100 orders rồi lần lượt load một relation cho từng order. Nếu mỗi repository method log INFO, một request tạo hàng trăm dòng. Chính log có thể làm tăng latency/ingest cost trong khi vẫn không cho biết nguyên nhân query nhiều.

Công cụ phù hợp:
- SQL/query statistics, call count và connection-pool metrics.
- JDBC spans/traces, cẩn trọng attributes chứa dữ liệu cá nhân.
- Hibernate SQL DEBUG tạm thời trong môi trường an toàn.
- Query plans, fetch strategy, batch size và code review.
- Load test sau khi sửa query, không chỉ tắt logger để giảm volume.

Với batch jobs, log một summary: `batch_id` an toàn, tổng số items, duration, success/failure counts. Nếu audit từng row là yêu cầu nghiêm ngặt, dùng kênh audit có transaction/durability/retention được thiết kế, không phụ thuộc INFO của AsyncAppender.

## 16. Cấu hình level cho package trong Spring Boot

```properties
logging.level.root=INFO
logging.level.com.example.orders.repository=DEBUG

# Chỉ bật khi cần điều tra SQL của Hibernate 6:
logging.level.org.hibernate.SQL=DEBUG

# Không bật thường trực nếu dùng dữ liệu thật:
# logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

`com.example.orders.repository` chỉ ảnh hưởng logger thuộc namespace tương ứng. Hibernate SQL dùng category riêng; đặt DEBUG ở repository package không tự bật SQL.

Nếu gắn appender riêng cho repository, kiểm tra `additivity`. Cùng appender gắn tại logger con và root có thể ghi log hai lần; `additivity=false` nhưng thiếu appender ở con có thể làm mất log. Trong nhiều trường hợp chỉ cần logger level theo package, không cần file appender mới.

## 17. Checklist kiểm thử failure, privacy và logging

| Case | Kỳ vọng |
| --- | --- |
| Query trả entity | Không spam INFO, service nhận đúng kết quả |
| Query trả empty | Không bị coi là DB outage |
| DB connection thất bại | Exception propagate, log tổng kết một lần |
| Data integrity violation | Phân loại đúng, không retry mù |
| Duplicate key | Conflict khi đúng use case |
| Optimistic locking | Giữ cause, retry/409 theo contract |
| Query timeout | Có error type/operation/duration, không raw params |
| Service gọi save rồi commit fail | Không log “committed” sai |
| Repository catch DataAccessException | Không swallow để trả success giả |
| Exception đi qua 3 tầng | Không in ba stack trace trùng |
| Hibernate SQL DEBUG | Có SQL cần thiết, không kèm bind values |
| Hibernate bind TRACE | Không được bật với dữ liệu production nhạy cảm |
| Raw JDBC SQLException | Không giả định annotation tự translate |
| Retry | Attempts và final result có event names khác |
| MDC ở thread pool | Không rò context/request ID |
| N+1 / batch | Metrics/traces hữu ích, không spam |
| Root + child appender | Không duplicate do additivity |
| Async logging | Hiểu queue full, block/drop, shutdown |

Có thể gắn test appender/Handler để assert event count, level và error code. Dùng canary credential tổng hợp để kiểm tra mọi sink không in token, SQL parameters hoặc data nhạy cảm. Test tích hợp cần xác minh transaction rollback và HTTP response, không chỉ số log.

## 18. Các sai lầm thường gặp

**Log INFO mọi `findById/save`:** volume tăng mà trùng với summary cấp service/HTTP.

**Catch–log–rethrow mọi tầng:** một exception có nhiều stack trace vô ích.

**Log rồi nuốt lỗi:** transaction/response có thể không đúng.

**Coi `Optional.empty()` là ERROR:** nhầm không có dữ liệu với database failure.

**Ghi “committed” sau `save()`:** flush/commit có thể xảy ra sau đó.

**Bật JDBC bind TRACE:** có thể lộ PII, credential và dữ liệu trả về.

**In entity/toString:** chứa email, token, password hash, dữ liệu tài chính.

**Retry mọi DataAccessException:** có lỗi không retryable; nguy cơ duplicate side effects.

**Đo duration bằng currentTimeMillis:** clock có thể nhảy; dùng nanoTime cho elapsed.

**Dùng repository DEBUG làm audit:** không có bảo đảm durability và transaction phù hợp.

**Thêm metric labels theo raw SQL/ID:** cardinality tăng mạnh.

**Gắn appender trùng root/child:** duplicate do additivity.

## 19. Quy trình thiết kế thực tế

1. Xác định repository đang dùng JDBC, Spring Data JPA hay adapter khác.
2. Phân loại found/not found/expected conflict/transient/fatal error.
3. Định nghĩa **tầng sở hữu log ERROR** và trách nhiệm retry/fallback.
4. Chỉ ghi repository diagnostic thật sự cần: operation, entity, datasource, duration, outcome.
5. Không log raw SQL bind parameters, entity nhạy cảm, credential và exception message chưa kiểm tra.
6. Đặt transaction boundary ở service và không coi save/flush là commit.
7. Dùng metrics/tracing cho pool latency, query duration, N+1, throughput và error rate.
8. Bật SQL DEBUG/TRACE tạm theo policy, kiểm tra phiên bản Hibernate.
9. Kiểm tra log routing, additivity, async loss và quyền truy cập.
10. Test propagation, rollback, exception translation, privacy và không duplicate.

**Kết luận:** repository chủ yếu cung cấp **kết quả truy cập dữ liệu và đúng loại exception**. Log ở đây nên là thông tin kỹ thuật hữu ích, không thay thế nghiệp vụ, transaction hay audit và không lặp toàn bộ lỗi ở những tầng khác. Đặt ownership rõ ràng giúp hệ thống vừa dễ điều tra vừa có log đáng tin cậy.

## Tài liệu tham khảo

- [Spring Data JPA – Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html).
- [Spring Framework – PersistenceExceptionTranslationPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/annotation/PersistenceExceptionTranslationPostProcessor.html).
- [Spring Framework – DataAccessException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html).
- [Spring Framework – JdbcTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
- [Hibernate ORM – Logging categories](https://docs.jboss.org/hibernate/orm/6.4/logging/logging.html).
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html).
- [SLF4J – User Manual](https://www.slf4j.org/manual.html).
- [Oracle Java – System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).
- [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).