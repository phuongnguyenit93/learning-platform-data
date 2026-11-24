# Query latency trong database observability

> **Chương:** Database observability  
> **Bài:** Query latency  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao cần đo query latency?

Một HTTP request có thể mất 1,8 giây nhưng controller chỉ thực hiện vài dòng code. Phần lớn thời gian có thể nằm ở một truy vấn database, chờ connection pool, chờ lock hoặc đọc nhiều dữ liệu hơn dự kiến. Nếu chỉ đo tổng HTTP latency, nhóm vận hành biết request chậm nhưng chưa biết phần nào gây ra độ trễ.

**Query latency** là thời gian một thao tác truy vấn database tiêu tốn theo một ranh giới đo đã xác định. Ranh giới đó có thể là thời gian thực thi JDBC statement, thời gian một database client operation, thời gian lấy connection, hoặc toàn bộ vòng đời repository call. Các con số này không thể thay thế cho nhau.

Database observability kết hợp:
- Metrics để theo dõi số lượng truy vấn, latency distribution, error rate và connection pool.
- Traces để thấy database operation nằm ở đâu trong request và chiếm bao nhiêu thời gian.
- Logs/slow query logs để cung cấp chi tiết SQL, plan hoặc lỗi theo chính sách bảo mật.
- Database-native telemetry để phân tích lock, wait events, execution plan và resource pressure.

~~~mermaid
flowchart TD
  A["HTTP request"] --> B["Controller / service"]
  B --> C["Repository operation"]
  C --> D["Connection pool acquire"]
  D --> E["Database execute / wait"]
  E --> F["Read rows / map result"]
  F --> G["Return to service"]
  B --> H["HTTP response"]
  C --> I["DB metrics + trace span"]
  E --> J["DB slow query / wait telemetry"]
~~~

Mục tiêu không chỉ là tìm câu SQL chậm nhất. Cần xác định độ trễ nằm ở pool, network, database execution, lock contention hay xử lý kết quả trong ứng dụng.

## 2. Query latency có nhiều ranh giới đo

Trước khi so sánh latency, cần biết timer bắt đầu và kết thúc ở đâu.

| Ranh giới | Bao gồm | Không nhất thiết bao gồm |
| --- | --- | --- |
| Pool acquire time | Chờ lấy connection | SQL execution |
| Driver execute time | Gửi statement và chờ kết quả theo driver API | Mapping toàn bộ dữ liệu ở application |
| Result consumption | Đọc rows và chuyển dữ liệu | Các bước nghiệp vụ sau repository |
| Repository call duration | Toàn bộ repository method | Các công việc sau method |
| Transaction duration | Nhiều statements và thời gian giữa chúng | Chỉ riêng một query |
| End-to-end request duration | Tất cả hoạt động request | Không thể quy toàn bộ cho database |

Một repository method có thể chạy ba câu SQL, nên repository latency không phải query latency của một statement. Một transaction có thể giữ connection trong lúc thực hiện business logic; transaction duration dài không có nghĩa mọi SQL statement đều chậm.

Khi đặt dashboard hoặc SLO, đặt tên metric và span theo ranh giới thật. Tránh so sánh query duration đo từ driver với repository timer đo cả mapping và application code.

## 3. Phân biệt latency của database với pool, network và application

Một lần gọi database thường có nhiều giai đoạn:

1. Lấy connection từ pool.
2. Driver chuẩn bị statement và gửi qua network.
3. Database parse/plan hoặc dùng cached plan.
4. Database chờ lock, I/O hoặc CPU.
5. Database trả rows.
6. Driver đọc dữ liệu và application map kết quả.
7. Application đóng statement/connection hoặc trả connection về pool.

Bảng chẩn đoán:

| Dấu hiệu | Vùng nghi vấn | Bằng chứng cần xem |
| --- | --- | --- |
| Pool acquire tăng, SQL execute ổn định | Pool saturation/leak | Active/idle/pending connections |
| DB execution time tăng | Query plan, index, lock, DB load | Slow query, EXPLAIN, wait events |
| DB time thấp nhưng repository chậm | Mapping, serialization, application processing | CPU profile, row count, code path |
| Latency tăng cùng network RTT | Network/proxy/database endpoint | Network telemetry, driver timing |
| Chỉ một tenant/parameter chậm | Data skew hoặc plan sensitivity | Parameter distribution, plan |
| Nhiều query nhỏ trên một request | N+1 hoặc chatty access | Trace waterfall, query count |

Không kết luận “database chậm” chỉ từ một HTTP span dài. Hãy so sánh thời gian từng DB operation với pool metrics, downstream spans và database-native telemetry.

## 4. JDBC query instrumentation trong Spring Boot

Spring Boot Actuator và Micrometer cung cấp các integration quan sát cho một số database/client operations. Với JDBC, datasource instrumentation có thể tạo observations/spans và metrics tùy dependency, configuration và phiên bản.

Một số lựa chọn thường gặp:
- Micrometer Observation/Tracing tích hợp với Spring Boot.
- Datasource instrumentation hoặc JDBC instrumentation phù hợp.
- OpenTelemetry Java Agent auto-instrumentation cho JDBC driver được hỗ trợ.
- Database-specific metrics/slow query logs từ chính database.

Không giả định chỉ thêm Actuator là mọi SQL statement tự động xuất thành một span chi tiết. Kiểm tra instrumentation thực tế, dependency và backend.

~~~java
@Repository
public class ProductRepository {
    private final JdbcTemplate jdbcTemplate;

    public ProductRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Product findById(long id) {
        return jdbcTemplate.queryForObject(
                "select id, name from products where id = ?",
                (rs, rowNum) -> new Product(
                        rs.getLong("id"),
                        rs.getString("name")),
                id);
    }
}
~~~

Khi JDBC instrumentation hoạt động, truy vấn có thể xuất hiện trong trace dưới dạng client/database span hoặc một operation tương ứng. Các attribute cụ thể phụ thuộc instrumentation và semantic convention version.

## 5. R2DBC và reactive database operations

R2DBC cung cấp API reactive cho relational databases. Không nên áp dụng giả định về lifecycle của JDBC blocking calls cho R2DBC publishers.

~~~java
public Mono<Product> findById(Long id) {
    return databaseClient.sql(
            "select id, name from products where id = :id")
        .bind("id", id)
        .map((row, metadata) -> new Product(
                row.get("id", Long.class),
                row.get("name", String.class)))
        .one();
}
~~~

Trong reactive stack, query thực thi khi publisher được subscribe. Đo thời gian tạo Mono không tương đương thời gian query. Instrumentation phải bao phủ subscription và completion/error signal.

Các điểm cần kiểm tra:
- Context propagation qua Reactor operators.
- Connection pool acquire và release.
- Cancellation khi subscriber hủy.
- Thời điểm consume result.
- Query errors và decode/mapping errors.
- Driver instrumentation hỗ trợ version đang dùng.

Không gọi block() chỉ để đo latency; việc đó thay đổi execution model và có thể gây thread starvation.

## 6. Database spans trong distributed trace

Khi database instrumentation hoạt động, DB operation có thể được biểu diễn thành span con của server/business span.

~~~text
order-service: POST /orders                 [SERVER]
  order-service: orders.create               [INTERNAL]
    order-service: SELECT products           [CLIENT / DATABASE]
    order-service: INSERT orders             [CLIENT / DATABASE]
    order-service: UPDATE inventory          [CLIENT / DATABASE]
~~~

Trace giúp trả lời:
- Query nào chiếm phần lớn thời gian request?
- Một request có phát sinh quá nhiều database calls không?
- Query chậm xuất hiện trong service nào?
- DB span có lỗi hay chỉ đơn thuần chậm?
- Nhiều service cùng chờ một database dependency hay không?

Trace không thay thế execution plan. Một span 800 ms chỉ nói operation mất 800 ms theo ranh giới instrumentation; nó không cho biết database dùng sequential scan, chờ lock hay chờ storage. Cần kết hợp DB-native telemetry.

Không ghi raw SQL có literal hoặc parameter nhạy cảm vào span attributes. Ưu tiên operation name/statement summary đã chuẩn hóa và các metadata được allowlist.

## 7. Metrics cho query latency

Một Timer/Histogram phù hợp có thể theo dõi thời lượng database operation. Tùy instrumentation, metric names có thể khác nhau; đừng giả định một meter name giống nhau cho JDBC, R2DBC và mọi exporter.

Một metric custom minh họa:

~~~java
Timer queryTimer = Timer.builder("app.database.query")
        .tag("db.system", "postgresql")
        .tag("operation", "select")
        .tag("repository", "product")
        .register(meterRegistry);

queryTimer.record(() -> productRepository.findById(id));
~~~

Đây là ví dụ minh họa ranh giới repository call. Nó không nhất thiết đo riêng thời gian execute statement. Nếu JDBC instrumentation đã đo statement, tránh tạo thêm Timer có cùng tên/semantics rồi cộng hai số như một.

Các chiều metrics nên hữu hạn:
- db.system: postgresql, mysql, oracle.
- operation: select, insert, update, delete.
- repository/query group: product.find-by-id, order.create.
- outcome: success, error, timeout.
- datasource/pool name đã chuẩn hóa.

Không dùng SQL text, parameter value, customer ID, order ID hoặc raw table name động làm metric tag.

## 8. Percentiles, histogram và tail latency

Average latency có thể che giấu một nhóm request rất chậm. Giả sử 990 truy vấn mất 10 ms và 10 truy vấn mất 2 giây. Average có thể vẫn có vẻ thấp nhưng người dùng bị ảnh hưởng rõ rệt.

Các chỉ số thường dùng:
- p50: median, một nửa quan sát nhanh hơn hoặc bằng giá trị này.
- p90/p95: tail latency của phần lớn request.
- p99: nhóm rất chậm, hữu ích khi traffic đủ lớn.
- max: quan sát cực đại, nhạy với outlier.
- count/rate: số operation trong cửa sổ.

Histogram buckets giúp backend tính quantile và phân tích phân phối. Client-side percentile có thể không tổng hợp chính xác giữa nhiều instances; chọn histogram/aggregation phù hợp backend.

Ví dụ PromQL khái niệm nếu histogram được export:

~~~text
histogram_quantile(
  0.95,
  sum by (le, operation) (
    rate(app_database_query_seconds_bucket[5m])
  )
)
~~~

Metric name và bucket configuration cần khớp dữ liệu thực tế. p99 từ một cửa sổ có ít samples không ổn định; luôn xem sample count và traffic.

## 9. Slow query logs và query fingerprint

Slow query log ở database có thể ghi những statement vượt ngưỡng thời gian. Đây là nguồn hữu ích để tìm query chậm ngay cả khi application trace bị sampling bỏ.

Một query fingerprint chuẩn hóa cấu trúc statement, bỏ hoặc che literal values để gom các lần chạy tương tự.

Ví dụ:

~~~sql
select id, total
from orders
where customer_id = ?
  and status = ?
~~~

Fingerprint cho phép nhóm query shape thay vì tạo một nhóm riêng cho mỗi parameter. Cần xem database có cung cấp normalized query digest hoặc query ID không; cách hoạt động phụ thuộc engine.

Không bật log toàn bộ SQL với bind parameters trên production mà chưa đánh giá dữ liệu nhạy cảm, dung lượng và quyền truy cập. Query có thể chứa email, token, địa chỉ hoặc thông tin giao dịch.

## 10. N+1 queries và query count

Một endpoint có thể chậm vì chạy quá nhiều query nhỏ thay vì một query lớn. Đây là tình huống N+1 phổ biến với ORM/lazy loading.

Ví dụ: lấy danh sách 100 orders, sau đó mỗi order lazy-load customer:

~~~text
1 query: select orders ...
100 queries: select customer where id = ?
Total: 101 database calls
~~~

Mỗi query có thể chỉ mất 4 ms, nhưng tổng round trips, pool contention và scheduling tạo độ trễ đáng kể.

Dấu hiệu:
- Trace có nhiều DB spans cùng tên lặp lại.
- Query count tăng theo số rows trả về.
- Latency tăng khi page size tăng.
- DB CPU không quá cao nhưng network/round-trip overhead lớn.

Cách xử lý:
- Fetch join/entity graph phù hợp.
- Batch fetching.
- Projection chỉ lấy field cần thiết.
- Bulk query hoặc IN clause có giới hạn.
- Kiểm tra pagination và query plan.

Không thay N+1 bằng một query khổng lồ không có index hoặc trả quá nhiều dữ liệu. Đo query count, rows, latency và memory sau thay đổi.

## 11. Connection pool acquire latency

Connection pool là một phần quan trọng của database latency. Khi tất cả connections đang được sử dụng, request mới phải chờ connection rảnh hoặc timeout.

Một số chỉ số cần theo dõi nếu pool hỗ trợ:
- active connections.
- idle connections.
- maximum pool size.
- pending/waiting threads.
- acquisition time.
- usage/lease duration.
- timeout count.

Nếu pool acquire chiếm 700 ms nhưng DB execution chỉ 20 ms, tối ưu SQL có thể không giải quyết gốc rễ. Kiểm tra connection leak, transaction giữ connection quá lâu, pool size và concurrency.

Không tăng pool size một cách mù quáng. Database có giới hạn connections và tăng pool có thể làm DB quá tải hơn. Cần cân bằng số replicas, pool size mỗi replica và connection budget toàn hệ thống.

## 12. Lock contention và transaction duration

Một query có thể chậm vì chờ lock dù execution plan tốt. Các giao dịch dài hoặc transaction isolation có thể làm tăng thời gian chờ.

Dấu hiệu:
- Latency tăng đột ngột theo thời điểm.
- Nhiều query cùng chờ một bảng/row.
- Database wait events cho thấy lock wait.
- Query duration cao nhưng CPU query thấp.
- Transaction mở lâu hoặc connection bị giữ lâu.

Cần kết hợp:
- Database lock/wait telemetry.
- Transaction duration metrics.
- Trace spans theo repository/transaction.
- Database activity/session views.
- Query plan và index.

Không ghi dữ liệu nhạy cảm vào span chỉ để nhận diện row bị lock. Dùng query fingerprint, operation group và database diagnostics có kiểm soát.

## 13. Query latency và cardinality

Metric tags phải mô tả nhóm query ổn định. Ví dụ:

~~~text
db.system = postgresql
db.operation.name = SELECT
repository = product
outcome = success
~~~

Tránh các tag:
- sql = toàn bộ SQL text.
- parameter = giá trị bind.
- customer.id.
- order.id.
- raw table hoặc schema do input điều khiển.
- exception.message.

Nếu mỗi query parameter tạo một time series, cardinality sẽ tăng theo traffic. Chi tiết parameter nên được điều tra trong môi trường có kiểm soát qua DB query digest hoặc trace/log đã redaction, không biến thành metric dimension.

Tên attribute database trong OpenTelemetry semantic conventions đã thay đổi qua các phiên bản. Kiểm tra convention version của instrumentation và backend trước khi viết query dashboard dựa vào key cũ.

## 14. Logging và trace correlation cho query chậm

Khi phát hiện query chậm, log có thể ghi operation group, duration, datasource và trace context. Tránh log raw parameter values.

~~~java
long started = System.nanoTime();
try {
    return repository.loadSummary(accountRef);
} finally {
    long elapsedMs =
            TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);

    if (elapsedMs > 500) {
        log.warn(
                "Slow repository operation repository={} durationMs={}",
                "account-summary",
                elapsedMs);
    }
}
~~~

Đây là ví dụ đo repository method bằng tay. Trong production, ưu tiên instrumentation chuẩn nếu đã có; nếu custom timing, đảm bảo không đo trùng và có metric/threshold hợp lý. Code trên minh họa log threshold, không tự gắn trace ID; dùng logging correlation integration để lấy traceId/spanId từ current context.

Một log hữu ích có thể chứa:
- service.name/version.
- repository/query group.
- duration.
- outcome/error category.
- traceId/spanId nếu có.
- instance/datasource metadata đã chuẩn hóa.

Không log password, token, raw SQL parameters, PII hoặc toàn bộ entity.

## 15. Kiểm tra query latency trong Spring Boot

Một quy trình thực tế:

### Bước 1 — xác nhận instrumentation

Kiểm tra Actuator, Micrometer registry, tracing bridge hoặc OTel agent/SDK. Xác định database technology JDBC hay R2DBC và instrumentation tương ứng.

### Bước 2 — kiểm tra metrics

Xem request/DB operation count, latency distribution, pool active/idle/pending và error rate. Đối chiếu metric names/tags thực tế thay vì đoán.

### Bước 3 — mở trace mẫu

Tìm request chậm đã được sample. Xác định DB span nào chiếm nhiều thời gian, số query và parent operation.

### Bước 4 — xem database-native diagnostics

Dùng slow query log, query digest, EXPLAIN/EXPLAIN ANALYZE trong môi trường phù hợp, lock/wait events và DB load. EXPLAIN ANALYZE có thể thực thi query; thận trọng với statement thay đổi dữ liệu hoặc query nặng.

### Bước 5 — phân tách pool và execution

So sánh connection acquire time, statement execution, result consumption và repository duration. Xác định instrumentation hiện có đo ranh giới nào.

### Bước 6 — kiểm tra sau thay đổi

Sau khi thêm index, sửa N+1, thay pool config hoặc query shape, so sánh p50/p95/p99, count, error rate, DB CPU, lock waits và pool pending. Dùng cùng traffic pattern và cửa sổ đo.

## 16. Troubleshooting các mẫu query latency

| Triệu chứng | Nguyên nhân có thể | Bằng chứng / hành động |
| --- | --- | --- |
| p95 DB span tăng nhưng pool acquire ổn định | Query plan, DB load hoặc lock | Slow query digest, EXPLAIN, wait events |
| Repository chậm nhưng DB spans ngắn | Mapping, business logic, result processing | CPU profile, row count, code path |
| Pool pending tăng | Pool saturation hoặc connection leak | Active/idle/pending, transaction duration |
| Query count tăng theo page size | N+1/lazy loading | Trace waterfall, query count |
| Chỉ một parameter chậm | Data skew hoặc plan sensitivity | Query digest, parameter distribution |
| p99 cao nhưng p50 ổn định | Tail outliers, lock, cold cache | Phân tích outlier traces và DB waits |
| Latency tăng sau deploy | Query shape/index/config regression | So sánh version và plan |
| Nhiều DB spans trùng nhau | Duplicate instrumentation | Kiểm tra agent, datasource proxy và custom timer |
| Không có DB span | Thiếu instrumentation hoặc sampling | Kiểm tra agent/bridge/SDK và trace sampler |
| Metrics thiếu query dimensions | Convention hoặc custom tags chưa cấu hình | Inspect meter tags thực tế |
| Slow query logs nhiều nhưng app timer thấp | Khác ranh giới đo hoặc async/background query | So sánh clock, operation và database digest |
| Error rate tăng nhưng latency không tăng | Constraint, permission, connection failure | Exception type, SQLState, pool metrics |

### Quy trình điều tra nhanh

1. Chọn service, datasource và time window.
2. So sánh query count, p95/p99 và pool acquire.
3. Mở trace để xác định query group chiếm thời gian.
4. Lấy fingerprint/query ID từ database telemetry.
5. Kiểm tra plan, indexes, lock waits và row counts.
6. Xác định latency ở pool, network, execution hay result mapping.
7. Thay đổi một yếu tố và benchmark lại.
8. Theo dõi cả DB health và application latency sau deploy.

## 17. Tình huống thực tế: endpoint order-service tăng p95

**Bối cảnh:** POST /orders tăng p95 từ 120 ms lên 900 ms. HTTP server metrics cho thấy request chậm, nhưng không có nhiều 5xx.

### Bước 1 — trace chỉ ra database operation

Trace cho thấy orders.create có ba DB spans. Một SELECT trên order_items chiếm 720 ms; các spans khác dưới 20 ms.

### Bước 2 — kiểm tra pool

Pool acquire time thấp và pending connections gần 0. Điều này giảm khả năng pool saturation là nguyên nhân chính.

### Bước 3 — kiểm tra query digest và plan

Database slow query telemetry cho thấy query scan nhiều rows. EXPLAIN cho thấy filter/join không dùng index phù hợp. Nhóm xác minh bằng dữ liệu đại diện và workload test.

### Bước 4 — tối ưu query

Thêm index phù hợp hoặc thay đổi query shape sau khi kiểm tra write overhead và plan. Nếu trace có nhiều SELECT lặp theo từng item, đánh giá thêm N+1 và batch loading.

### Bước 5 — xác minh

Sau deploy, so sánh:
- p50/p95/p99 của DB operation.
- HTTP server latency.
- Query count mỗi order.
- DB CPU/IO và lock waits.
- Pool acquire và pending.
- Error rate và result correctness.

**Kết quả mong muốn:** xác định được phần latency thực sự nằm ở database execution, thay đổi query/index có bằng chứng và kiểm chứng tác động trên toàn request.

## 18. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — phân biệt các ranh giới latency

Tạo một repository call và đo riêng pool acquire, statement execute nếu driver cho phép, result consumption và repository duration. Giải thích vì sao các số khác nhau.

### Bài tập B — trace database calls

Bật JDBC hoặc R2DBC instrumentation phù hợp. Tạo một HTTP request có hai truy vấn. Xác minh DB spans là con của request trace và đo được thời gian từng operation.

### Bài tập C — mô phỏng N+1

Tạo endpoint tải 50 records có quan hệ lazy. Quan sát query count và trace waterfall. Chuyển sang fetch/batch/projection phù hợp, rồi so sánh query count, latency và memory.

### Bài tập D — pool saturation

Giới hạn connection pool nhỏ và tạo concurrency test. Quan sát active, idle, pending, acquire latency và timeout. Thay pool size có kiểm soát, không vượt connection budget của database.

### Bài tập E — slow query và plan

Tạo query có filter thiếu index trên dataset test. Thu thập query digest/slow log và EXPLAIN. Thêm index hoặc đổi query, đo lại p95/p99 và write overhead.

### Bài tập F — cardinality review

Rà soát metrics tags/tracing attributes. Loại SQL literal, parameter values, customer/order IDs khỏi metric labels. Dùng query group/fingerprint ổn định và kiểm tra số time series.

### Câu hỏi tự kiểm tra

1. Query latency khác repository duration và transaction duration thế nào?
2. Pool acquire time tăng nói lên điều gì?
3. Vì sao HTTP request chậm không đủ để kết luận database chậm?
4. JDBC và R2DBC khác nhau thế nào về execution lifecycle?
5. Database span cho biết điều gì và không cho biết điều gì?
6. p95/p99 hữu ích hơn average trong trường hợp nào?
7. N+1 queries làm tăng latency dù từng query nhanh ra sao?
8. Làm thế nào phân biệt lock wait với query plan chậm?
9. Vì sao không đưa SQL text/parameter vào metric tags?
10. Slow query log và trace sampling bổ sung cho nhau thế nào?
11. Connection pool size lớn hơn có luôn cải thiện latency không?
12. Làm sao xác định metric timer đo statement hay repository call?
13. EXPLAIN ANALYZE có rủi ro gì với query ghi dữ liệu?
14. Làm sao liên kết slow query log với trace mà không lộ PII?
15. Sau tối ưu cần theo dõi những chỉ số nào để tránh regression?

**Tiêu chí hoàn thành:** giải thích các ranh giới query latency; phân biệt pool/network/database/application time; instrument JDBC/R2DBC; đọc DB spans và histogram; nhận diện N+1, lock và pool saturation; dùng slow query/plan; kiểm soát cardinality và bảo mật; xác minh cải thiện bằng metrics/traces.

## 19. Ghi nhớ

- Query latency phải gắn với một ranh giới đo rõ ràng: pool acquire, statement execution, result consumption, repository hoặc transaction.
- HTTP request latency không đồng nghĩa database execution time.
- JDBC và R2DBC có lifecycle khác nhau; reactive query thực thi khi subscription diễn ra.
- DB spans giúp đặt query trong request trace nhưng không thay thế execution plan, lock/wait telemetry hay slow query digest.
- Theo dõi p50/p95/p99 cùng count; percentile cần đủ samples và histogram phù hợp.
- N+1, pool saturation, lock contention, data skew và result mapping đều có thể làm database path chậm.
- Tách pool acquire khỏi execute time để tránh tối ưu nhầm SQL khi gốc rễ là connection pool.
- Dùng query fingerprint/operation group thay raw SQL và parameters trong metrics.
- Kết hợp metrics, traces, logs và database-native diagnostics để tìm nguyên nhân.
- Sau tối ưu, xác minh latency, query count, pool, DB load, lock waits và correctness dưới workload đại diện.

## Tài liệu tham khảo

- [Spring Boot Reference — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry Semantic Conventions — Database](https://opentelemetry.io/docs/specs/semconv/database/)
- [OpenTelemetry Java Instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/)
- [Spring Framework — R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [PostgreSQL Documentation — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)

