# Database error metrics

Một API Spring Boot có thể trả 500 khi database connection bị từ chối, 503 khi connection pool cạn, hoặc 409 khi nghiệp vụ phát hiện dữ liệu xung đột. Nếu dashboard chỉ có một bộ đếm database.errors, đội vận hành khó biết lỗi đến từ kết nối, timeout truy vấn, transaction hay constraint nghiệp vụ. Database error metrics cần phân loại lỗi đủ để định hướng điều tra, nhưng phải giữ dimensions ổn định để metrics có thể tổng hợp và cảnh báo tin cậy.

Bài **Database error metrics** thuộc chương **Database observability** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc:** Metrics trả lời lỗi DB xảy ra thường xuyên đến đâu, ở operation nào và thuộc nhóm nào. Logs/traces cung cấp chi tiết của một lần thất bại. Không dùng exception message, SQL text, parameter, schema/table động, user ID hoặc connection string làm metric tags. Phân biệt lỗi DB thật với business rejection được ánh xạ thành HTTP 4xx; hai loại có thể cùng làm request thất bại nhưng không có cùng ý nghĩa vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích database error metrics và vai trò trong observability.
2. Phân biệt connectivity, pool exhaustion, query timeout, transaction, constraint và business errors.
3. Nhận diện exception từ JDBC, Spring Data/JPA và R2DBC.
4. Dùng SQLState class và vendor error code để phân loại lỗi.
5. Thiết kế Counter/Timer cho database operation và failure.
6. Chọn low-cardinality dimensions như db.system, operation, error.type và outcome.
7. Tránh SQL text, exception message, parameter và ID động trong metric tags.
8. Kết hợp metrics với Observation, traces và structured logs.
9. Thiết kế alert theo error rate, latency, pool saturation và dependency availability.
10. Kiểm thử việc ghi nhận lỗi mà không làm lộ dữ liệu nhạy cảm hoặc đếm trùng.

## 2. Database error metrics là gì?

Database error metrics là số liệu tổng hợp về lỗi phát sinh khi ứng dụng tương tác với database. Chúng có thể được tạo từ JDBC operations và Spring JDBC exception translation, JPA/Hibernate repository operations, R2DBC reactive database operations, connection pool, transaction manager và custom instrumentation.

Các câu hỏi vận hành:
- Tỷ lệ query lỗi trên tổng query là bao nhiêu?
- Lỗi tập trung ở database system hoặc operation nào?
- Connection timeout có tăng cùng pool pending không?
- Query timeout xuất hiện sau deployment nào?
- Lỗi constraint là dữ liệu không hợp lệ hay dấu hiệu regression?
- DB dependency làm latency và error rate của API tăng hay không?

Metric là tín hiệu tổng hợp. Nó không thay thế log/trace chứa SQL operation đã được làm sạch, exception class và context của request.

## 3. Phân loại database failures

| Nhóm | Ví dụ | Tác động vận hành |
|---|---|---|
| Connection acquisition | Pool exhausted, acquisition timeout | Không lấy được connection |
| Connection establishment | Connection refused, network unreachable | Không kết nối được database |
| Authentication/authorization | Invalid credentials, permission denied | Cấu hình hoặc quyền truy cập sai |
| Query timeout/cancel | Statement timeout, query canceled | Query vượt giới hạn hoặc bị hủy |
| Transaction | Deadlock, serialization failure, rollback | Transaction không hoàn tất |
| Constraint/data integrity | Unique violation, foreign key violation | Dữ liệu vi phạm ràng buộc |
| Resource exhaustion | Too many connections, disk full | Database/hạ tầng cạn tài nguyên |
| Protocol/driver | Connection reset, protocol error | Driver/network/server issue |
| Business rejection | Order exists, insufficient balance | Kết quả nghiệp vụ, không nhất thiết là DB failure |

Business rejection có thể được phát hiện trước khi gửi SQL. Unique constraint violation có thể biểu hiện business conflict, nhưng vẫn cần phân biệt nguồn gốc và chính sách API. Không đánh dấu mọi 409/400 là database failure.

### 3.1 Connectivity và pool errors

Pool acquisition timeout thường có nghĩa ứng dụng không lấy được connection trong thời gian cho phép. Nguyên nhân có thể là mọi connection đang được sử dụng, query/transaction giữ connection quá lâu, connection leak, pool size thấp so với concurrency hoặc database chậm.

Connection refused, DNS failure hoặc network timeout xảy ra ở giai đoạn kết nối; chúng khác pool acquisition timeout. Cần metric riêng nếu muốn xác định lớp hạ tầng đang gặp vấn đề.

### 3.2 Query và transaction errors

Query timeout có thể do execution plan, lock contention, database overload hoặc timeout cấu hình quá thấp. Deadlock/serialization failure thường cần xem transaction isolation, access order và retry policy. Constraint violations có thể là dữ liệu không hợp lệ hoặc race condition.

Không dùng exception message để suy ra taxonomy bằng regex tùy tiện. Ưu tiên exception type, SQLState và vendor code theo database/driver đã biết.

## 4. Exception translation và SQLState

Spring JDBC dịch SQLException sang DataAccessException hierarchy. Ví dụ DataIntegrityViolationException, DuplicateKeyException, QueryTimeoutException, TransientDataAccessResourceException và CannotGetJdbcConnectionException. JPA/Hibernate có thể wrap lỗi driver trong PersistenceException, HibernateException hoặc Spring DataAccessException. R2DBC dùng exception types riêng và mapping của driver. Vì vậy cần nhìn cause chain, không chỉ exception ngoài cùng.

### 4.1 SQLState class

SQLState là mã phân loại chuẩn của lỗi SQL. Một số class thường gặp:

| SQLState class | Ý nghĩa tổng quát | Nhóm metric gợi ý |
|---|---|---|
| 08 | Connection exception | connection |
| 22 | Data exception | data |
| 23 | Integrity constraint violation | constraint |
| 25 | Invalid transaction state | transaction |
| 40 | Transaction rollback, gồm serialization/deadlock theo mã con | transaction |
| 42 | Syntax/access rule violation | query_or_permission |
| 53 | Insufficient resources | resource |
| 57 | Operator intervention/system error | database_unavailable_or_cancelled |
| 28 | Invalid authorization specification | authentication |

Đây là phân loại tổng quát; ý nghĩa cụ thể của SQLState con và vendor code phụ thuộc database. Không gộp tất cả class 42 thành syntax bug nếu database dùng mã con cho quyền truy cập.

### 4.2 Vendor error code

Một số database có mã vendor giúp phân biệt deadlock, duplicate key hoặc connection failure. Mapping nên nằm trong adapter theo database/driver version, được test và version hóa. Không phát raw vendor message hoặc code tùy ý thành tag nếu tập giá trị không được kiểm soát.

Nếu không nhận diện được SQLState/vendor code, dùng nhóm bounded unknown thay vì tạo tag từ chuỗi tự do.

## 5. Thiết kế metric dimensions

Metric dimensions phải ổn định và cardinality thấp:

| Dimension | Giá trị phù hợp | Tránh |
|---|---|---|
| db.system | postgresql, mysql, oracle | JDBC URL đầy đủ |
| db.operation.name | SELECT, INSERT, UPDATE, DELETE | SQL nguyên văn |
| error.type | timeout, connection, constraint, transaction, unknown | Exception message |
| outcome | success, error | Nội dung response tự do |
| pool.name | primary, reporting | Tên pool chứa tenant/customer động |
| service.name | order-service | Instance/request ID |
| environment | production, staging | Giá trị từ request |

Không thêm SQL query text/bind parameters, database password/connection string, user ID/order ID/email/account number, raw exception message/stack trace, table name động hoặc trace ID/request ID làm metric labels.

Nếu cần điều tra query cụ thể, dùng trace span hoặc log record đã scrub và giới hạn quyền truy cập/retention.

## 6. Chọn metric: counter, timer và pool gauges

| Metric | Type | Ý nghĩa |
|---|---|---|
| db.client.operations | Counter | Số operation hoàn tất |
| db.client.errors | Counter | Số operation thất bại |
| db.client.operation.duration | Timer/Histogram | Latency operation |
| db.client.timeouts | Counter | Số timeout |
| db.pool.active | Gauge | Connection đang được dùng |
| db.pool.idle | Gauge | Connection rảnh |
| db.pool.pending | Gauge | Request đang chờ connection |
| db.pool.max | Gauge | Tổng giới hạn pool |
| db.pool.acquire.duration | Timer | Thời gian lấy connection nếu instrumentation cung cấp |

Tên metric chính xác phụ thuộc Micrometer binder, Spring Boot version, JDBC/R2DBC instrumentation và semantic convention. Không tạo custom meter trùng với meter tự động đã được registry cung cấp.

### 6.1 Error count và error rate

Counter chỉ tăng khi operation thất bại. Để tính error rate, cần denominator là tổng operations:

~~~text
error_rate = failed_operations / total_operations
~~~

Nếu chỉ nhìn error count, traffic tăng có thể làm số lỗi tăng dù tỷ lệ lỗi không đổi. Dashboard nên hiển thị cả rate và absolute count.

### 6.2 Timer và failure

Timer có thể ghi cả operation thành công và thất bại để latency distribution phản ánh toàn bộ attempts. Nếu chỉ ghi timer thành công, dashboard có thể trông tốt hơn trong lúc request chậm đang timeout và bị loại khỏi distribution.

Có thể phân loại timer bằng outcome nếu instrumentation hỗ trợ bounded tag. Đảm bảo không tạo timer mới cho mỗi exception message.

### 6.3 Pool gauges

Pool metrics giúp phân biệt database chậm với pool thiếu capacity:
- Active gần max và pending tăng: ứng dụng đang chờ connection.
- Active thấp nhưng connect errors tăng: có thể là network/auth/database unavailable.
- Active cao lâu và query duration tăng: query/transaction có thể giữ connection quá lâu.
- Idle bằng 0 trong peak: pool có thể bão hòa.

Không chỉ tăng pool size; database cũng có giới hạn connection và tăng concurrency có thể làm database quá tải nặng hơn.

## 7. Micrometer Observation cho database operations

Micrometer Observation cho phép đo operation bằng abstraction thống nhất. Khi có handler phù hợp, observation có thể tạo metrics và tracing spans. Instrumentation của Spring/JDBC/Hibernate/R2DBC có thể cung cấp observation tự động tùy stack và dependency.

Ví dụ custom repository operation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
class InventoryRepositoryMetrics {

    private final ObservationRegistry observationRegistry;

    InventoryRepositoryMetrics(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    Inventory load(String sku) {
        return Observation.createNotStarted(
                        "inventory.repository.load",
                        observationRegistry)
                .lowCardinalityKeyValue("db.operation.name", "SELECT")
                .observe(() -> performQuery(sku));
    }

    private Inventory performQuery(String sku) {
        // Gọi repository/JDBC thực tế.
        return null;
    }
}
~~~

Ví dụ minh họa custom operation; trong code thật, không bọc lại query đã được instrument tự động nếu điều đó tạo metrics/traces trùng. Nếu cần custom business observation, đặt tên khác và mô tả logical operation rõ ràng.

### 7.1 Ghi nhận lỗi trong Observation

Observation có thể ghi exception khi operation ném lỗi ra khỏi callback; error handler/tracing handler có thể chuyển thông tin đó thành span event/status hoặc metric tags tùy convention. Nếu exception được bắt và chuyển thành kết quả bình thường bên trong callback, handler có thể không tự biết operation thất bại.

~~~java
return Observation.createNotStarted("inventory.repository.load", observationRegistry)
        .lowCardinalityKeyValue("db.operation.name", "SELECT")
        .observe(() -> repository.findBySku(sku)
                .orElseThrow(() -> new InventoryNotFoundException(sku)));
~~~

Nếu not-found là business outcome bình thường, không nhất thiết tính là database error. Phân biệt query thành công nhưng không có row với database query thất bại.

## 8. Ví dụ custom error counter an toàn

Nếu ứng dụng cần metric nghiệp vụ riêng, phân loại exception thành tập error.type hữu hạn:

~~~java
enum DbErrorType {
    CONNECTION,
    TIMEOUT,
    CONSTRAINT,
    TRANSACTION,
    PERMISSION,
    UNKNOWN
}
~~~

Classifier nên đọc cause chain/SQLState bằng mapping đã kiểm thử:

~~~java
DbErrorType classify(DataAccessException ex) {
    if (hasSqlStateClass(ex, "08")) {
        return DbErrorType.CONNECTION;
    }
    if (hasSqlStateClass(ex, "23")) {
        return DbErrorType.CONSTRAINT;
    }
    if (hasSqlStateClass(ex, "40")) {
        return DbErrorType.TRANSACTION;
    }
    if (isQueryTimeout(ex)) {
        return DbErrorType.TIMEOUT;
    }
    if (isPermissionFailure(ex)) {
        return DbErrorType.PERMISSION;
    }
    return DbErrorType.UNKNOWN;
}
~~~

Các helper là pseudocode vì cách lấy SQLException, SQLState và vendor code phụ thuộc exception hierarchy/driver. Không copy như implementation hoàn chỉnh nếu chưa duyệt cause chain và exception wrap của ứng dụng.

Sau khi phân loại, tăng Counter:

~~~java
Counter.builder("app.database.errors")
        .tag("db.system", "postgresql")
        .tag("operation", "SELECT")
        .tag("error.type", errorType.name().toLowerCase(Locale.ROOT))
        .register(meterRegistry)
        .increment();
~~~

Không dùng tên database/table do request truyền vào. Dùng db.system và operation đã chuẩn hóa; nếu có nhiều logical database, đặt alias cố định như primary/reporting.

### 8.1 Đếm lỗi đúng một lần

Nếu driver instrumentation, Spring exception translation và custom catch block đều tăng error counter cho cùng failure, metric sẽ bị đếm trùng. Chọn một layer sở hữu error counting:
- Instrumentation chuẩn cho database client operations.
- Custom metric chỉ cho business-level failure chưa được đo.
- Không vừa tăng counter trong repository catch vừa tăng lại ở service/controller cho cùng operation.

## 9. JDBC, JPA và R2DBC

### 9.1 JDBC/Spring JDBC

Spring JDBC có exception translation giúp ứng dụng xử lý DataAccessException thay vì phụ thuộc trực tiếp driver exceptions. Giữ cause để logs/traces điều tra sâu hơn nhưng không ghi message nhạy cảm vào metric tags.

JDBC instrumentation có thể đo query execution, connection usage và error theo integration. Kiểm tra dependency/version và tránh thêm custom Timer trùng.

### 9.2 JPA/Hibernate

Repository call có thể chưa thực thi SQL ngay; Hibernate có thể trì hoãn flush đến cuối transaction. Constraint violation có thể xuất hiện ở flush/commit chứ không phải tại dòng save(). Khi đo, cần hiểu transaction boundary và thời điểm database thực sự nhận statement.

Một repository method trả về thành công trước commit không chứng minh transaction đã commit thành công. Nếu metric business operation cần biểu thị commit, instrument transaction completion hoặc boundary thích hợp.

### 9.3 R2DBC

R2DBC là reactive và lỗi có thể xuất hiện bất đồng bộ trong publisher subscription. Không đo bằng cách tạo Timer quanh việc khởi tạo Mono/Flux; cần instrument thời gian từ subscribe tới terminal signal (complete/error/cancel) hoặc dùng Observation integration có sẵn.

Reactive cancellation không nhất thiết là database error. Phân biệt cancellation do client disconnect/deadline với query error từ database.

## 10. Transaction, rollback và business errors

Một transaction có thể thất bại vì deadlock, serialization conflict, constraint violation hoặc lỗi kết nối. Metric cần phản ánh operation/transaction outcome, nhưng tránh đếm cùng lỗi ở cả statement, transaction manager và business service.

Phân biệt:
- Query thất bại và transaction rollback.
- Query thành công nhưng transaction commit thất bại.
- Transaction bị rollback chủ động theo business rule.
- Business validation thất bại trước khi có SQL.
- Optimistic locking conflict do dữ liệu đồng thời thay đổi.

Một rollback có thể là kết quả dự kiến. Có thể có metric transaction.outcome=rollback riêng và error.type phân biệt failure kỹ thuật với business cancellation.

## 11. Liên kết metrics với traces và logs

Metrics cho biết tỷ lệ lỗi/latency tăng. Trace cho biết DB operation nằm trong request nào và mất bao lâu. Log cho biết exception class, SQLState đã scrub và context cần thiết.

~~~mermaid
flowchart LR
    A["Database error metrics"] --> B["Phát hiện error rate tăng"]
    B --> C["Trace của request bị ảnh hưởng"]
    C --> D["DB client span"]
    D --> E["Structured log"]
    E --> F["Exception type / SQLState / safe context"]
    F --> G["Điều tra pool, query, lock hoặc database"]
~~~

Log có thể gồm service.name, environment, operation name/repository method, exception class, SQLState class đã chuẩn hóa, database alias, traceId/spanId và elapsed time.

Không ghi SQL bind values, credentials, raw customer data hoặc exception message chưa scrub.

## 12. Alerting theo error metrics

Một alert tốt kết hợp error rate, latency và saturation:

| Alert | Điều kiện gợi ý | Ý nghĩa |
|---|---|---|
| DB operation error rate | Error ratio vượt ngưỡng trong cửa sổ liên tiếp | Lỗi DB có ảnh hưởng thực |
| DB connection errors | Connection failures tăng nhanh | Network/auth/DB availability |
| Query timeout rate | Timeout counter/rate vượt baseline | Query hoặc DB latency |
| Pool saturation | Active gần max và pending tăng | Ứng dụng thiếu connection capacity |
| Transaction rollback | Rollback kỹ thuật tăng so baseline | Deadlock/serialization/commit failures |
| DB latency SLO | p95/p99 vượt budget | Query/dependency chậm |

Không cảnh báo theo error count tuyệt đối nếu traffic thay đổi mạnh. Dùng ratio, minimum request volume, duration window và route/business impact. Tách constraint/business conflicts khỏi availability alerts nếu chúng là kết quả thường gặp.

### 12.1 Ví dụ PromQL conceptual

~~~promql
sum(rate(app_database_errors_total[5m]))
/
clamp_min(sum(rate(app_database_operations_total[5m])), 1)
~~~

Query minh họa; tên metric thực tế có thể được Prometheus registry chuẩn hóa và cần labels phù hợp. Trong production, group theo db.system và error.type khi cardinality đã được kiểm soát.

## 13. Cardinality và dữ liệu nhạy cảm

Một metric với tags db.system, operation, error.type và outcome có thể có số series nhỏ. Nếu thêm SQL statement, exception message, tenant ID hoặc user ID, số series tăng không giới hạn thực tế.

~~~text
An toàn:
db.system=postgresql
operation=SELECT
error.type=timeout
outcome=error

Không an toàn:
sql="select * from orders where customer_id=..."
exception.message="password authentication failed for user ..."
customer.id=customer-83921
jdbc.url=jdbc:postgresql://db.internal/orders?password=...
~~~

Hash SQL hoặc user ID cũng không tự giải quyết cardinality và privacy. Hash query với literal values có thể vẫn tạo series theo từng request. Dùng query fingerprint chuẩn hóa nếu instrumentation/backend hỗ trợ và policy cho phép; không tự tạo hash động làm metric label.

## 14. Kiểm thử database error metrics

Dùng database test instance/container hoặc mock ở đúng boundary. Test cần xác nhận classifier, counter và Observation behavior.

Kịch bản:
1. Query thành công: operation counter tăng, error counter không tăng.
2. Query timeout: error.type=timeout.
3. Connection unavailable: error.type=connection.
4. Unique constraint violation: error.type=constraint.
5. Deadlock/serialization failure: error.type=transaction.
6. Business not-found không có SQL error: không tăng database error counter.
7. R2DBC cancellation: phân biệt cancellation với DB failure.
8. Exception chứa secret giả: metric labels không chứa message/SQL/credential.

Test classifier bằng SQLState fixtures đã biết của database/driver đang dùng; không giả định mọi database map vendor code giống nhau.

### 14.1 Ví dụ kiểm tra Counter

~~~java
@Test
void incrementsDatabaseErrorCounterForTimeout() {
    meterRegistry.clear();

    service.executeQueryThatTimesOut();

    Counter counter = meterRegistry.find("app.database.errors")
            .tag("db.system", "postgresql")
            .tag("operation", "SELECT")
            .tag("error.type", "timeout")
            .counter();

    assertThat(counter).isNotNull();
    assertThat(counter.count()).isEqualTo(1.0);
}
~~~

Đây là test minh họa; test thực tế cần fixture DB/driver hoặc mock classifier phù hợp. Đảm bảo test không vô tình tạo thêm meter cùng name với tag set khác.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| DB error counter tăng nhưng API 2xx | Background task/retry lỗi hoặc lỗi được fallback | Correlate theo service/operation/trace |
| API 4xx tăng nhưng DB errors không tăng | Business validation hoặc not-found | Không ép thành DB error |
| Pool timeout tăng, connection error thấp | Không lấy được connection từ pool | Kiểm tra active/idle/pending, leak và transaction duration |
| Connection errors tăng | DNS/network/auth/database availability | Kiểm tra SQLState class 08 và infra |
| Query timeout tăng | Slow query, lock, DB saturation hoặc timeout quá thấp | Xem DB spans, query plan và lock metrics |
| Constraint errors tăng sau deploy | Schema/data migration hoặc write behavior đổi | Kiểm tra unique/FK constraints và rollout |
| Error counter đếm gấp đôi | Nhiều layer cùng instrument một failure | Chọn một owner cho database error counting |
| JPA save thành công nhưng transaction rollback | SQL flush/commit diễn ra sau method return | Quan sát transaction completion |
| R2DBC không ghi duration | Timer dừng khi tạo publisher thay vì terminal signal | Instrument subscription/terminal signal |
| Metric cardinality tăng mạnh | SQL/message/ID động thành tags | Chuẩn hóa bounded dimensions |
| Không phân loại được exception | Driver wrap exception hoặc SQLState không được lấy từ cause | Duyệt cause chain và bổ sung mapping đã test |
| Error logs không có trace ID | Context propagation/log correlation chưa cấu hình | Kiểm tra tracing bridge và MDC integration |

## 16. Playbook: database error rate tăng sau deployment

**Tình huống:** Sau release Order Service, database error rate tăng từ mức nền thấp lên cao.

1. Lọc metrics theo service, db.system, operation và error.type.
2. Xác định nhóm lỗi tăng: connection, timeout, constraint hay transaction.
3. So sánh error rate với tổng operation rate để loại trừ traffic spike.
4. Kiểm tra pool active/idle/pending và connection acquisition timeout.
5. Mở traces của request bị ảnh hưởng, xem DB span duration và parent operation.
6. Đọc logs đã scrub để xem exception class, SQLState class và database alias.
7. So sánh version/deployment trước và sau release; kiểm tra schema migration, query hoặc transaction changes.
8. Nếu deadlock/serialization tăng, xem transaction access order/isolation và retry policy.
9. Nếu timeout tăng, kiểm tra query latency, lock wait, pool và DB resource saturation.
10. Xác nhận sau fix: error ratio, latency và pool pending trở về baseline; không còn duplicate counting.

Không chỉ tăng pool size hoặc timeout để che symptom. Xác định lỗi ở pool, network, query, transaction hay data integrity trước khi thay cấu hình.

## 17. Bài tập tự kiểm tra

**Bài 1 — Phân loại lỗi.** Một query gặp unique constraint violation. Nên phân loại vào error.type nào? Khi nào đây là business conflict thay vì database availability failure?

**Bài 2 — SQLState.** SQLState class 08 và 23 thường biểu thị nhóm lỗi nào? Vì sao cần đọc mã con/vendor code?

**Bài 3 — Metric dimensions.** Vì sao không dùng exception message hoặc SQL statement làm tag cho app.database.errors?

**Bài 4 — Error rate.** Vì sao error count tăng không nhất thiết có nghĩa reliability giảm? Cần denominator nào?

**Bài 5 — Pool saturation.** Active connections bằng max và pending tăng, nhưng connect timeout không tăng. Bạn nghi ngờ giai đoạn nào?

**Bài 6 — JPA commit.** Repository save trả về thành công nhưng transaction commit thất bại. Vì sao metric quanh riêng method save có thể bỏ lỡ lỗi?

**Bài 7 — R2DBC.** Vì sao không dừng Timer ngay sau khi tạo Mono? Terminal signals nào cần được xem xét?

**Bài 8 — Đếm trùng.** Driver instrumentation, repository catch và service catch đều tăng counter. Hãy đề xuất cách chọn instrumentation owner.

### Gợi ý trả lời

1. Constraint. Nếu client gửi dữ liệu xung đột và API contract coi đó là 409, đây là business conflict; nếu tăng bất thường, điều tra race/schema.
2. 08 là connection exception; 23 là integrity constraint violation. Mã con/vendor code cho biết tình huống cụ thể theo database.
3. Chúng có giá trị biến thiên rất cao và có thể chứa PII/secret; metric labels cần bounded.
4. Traffic có thể tăng; dùng tổng database operations làm denominator để tính ratio.
5. Pool acquisition/wait; kiểm tra pending, active, idle, leak và transaction duration.
6. JPA có thể flush/commit sau khi method trả về; đo transaction completion boundary.
7. Publisher chưa thực thi khi tạo Mono. Đo từ subscribe tới complete/error/cancel và phân loại cancellation riêng.
8. Để instrumentation chuẩn đo operation DB; custom counter chỉ cho business event chưa có metric tương đương, tránh tăng cùng lỗi ở nhiều layer.

## 18. Tài liệu tham khảo chính thức

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer metrics, data source/pool metrics và customization.
- [Spring Framework — Data Access](https://docs.spring.io/spring-framework/reference/data-access.html): exception translation và data access abstractions.
- [Spring JDBC — Data Access Exceptions](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JDBC support và exception translation.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle, handlers và conventions.
- [HikariCP — Metrics](https://github.com/brettwooldridge/HikariCP): pool metrics, active/idle/pending connections và configuration.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLState classes và error codes.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): database activity và monitoring views.
- [OpenTelemetry Semantic Conventions — Database](https://opentelemetry.io/docs/specs/semconv/db/): database operation attributes và telemetry conventions.
- [R2DBC SPI](https://r2dbc.io/spec/1.0.0.RELEASE/spec/html/): reactive database API và error signals.

**Ghi nhớ:** Database error metrics phải phân biệt connection/pool, query, transaction, constraint và business outcomes. Dùng SQLState/exception classification đã kiểm thử để tạo error.type hữu hạn; kết hợp error counter với tổng operations, latency và pool gauges. Observation giúp liên kết metrics với DB spans, logs và trace context. Đừng đưa SQL, exception message, bind values hoặc ID động vào metric tags. Khi lỗi tăng, xác định đúng giai đoạn và layer trước khi thay pool size, timeout hay retry policy.

