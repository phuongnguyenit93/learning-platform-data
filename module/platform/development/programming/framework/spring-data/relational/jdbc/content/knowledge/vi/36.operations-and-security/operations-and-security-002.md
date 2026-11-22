# Quan sát connection pool, truy vấn chậm và lỗi cơ sở dữ liệu

Trong production, một ứng dụng Spring Data JDBC có thể gặp nhiều vấn đề khác nhau: connection pool cạn, query chậm, database quá tải, lock kéo dài hoặc lỗi constraint tăng đột biến. Nếu chỉ nhìn log ứng dụng hoặc chỉ kiểm tra database có đang chạy hay không, đội vận hành khó xác định nguyên nhân và mức ảnh hưởng.

Quan sát tốt cần kết hợp ba nguồn dữ liệu:

- **Metrics:** xu hướng định lượng như connection active/pending, thời gian lấy connection, query latency và tỷ lệ lỗi.
- **Logs:** chi tiết sự kiện cụ thể, exception, SQL fingerprint và thông tin ngữ cảnh.
- **Traces:** đường đi của một request qua service, repository, JDBC và các thành phần phụ thuộc.

Với Spring Data JDBC, cần quan sát cả connection pool, thao tác JDBC và database engine. Bài học này trình bày cách thiết lập dashboard, phát hiện truy vấn chậm, phân loại lỗi database, đặt cảnh báo và xây dựng quy trình chẩn đoán an toàn.

## 1. Ba lớp cần quan sát

Một request có thể đi qua nhiều lớp trước khi trả kết quả:

```text
Client request
    |
    v
Application service
    |
    v
Spring Data JDBC repository
    |
    v
DataSource / HikariCP
    |
    v
JDBC driver
    |
    v
Database engine
```

Mỗi lớp trả lời một nhóm câu hỏi:

| Lớp | Câu hỏi vận hành |
| --- | --- |
| Application | Request nào chậm? Tỷ lệ lỗi bao nhiêu? |
| Repository/JDBC | Operation nào phát nhiều SQL? Statement nào chậm? |
| Connection pool | Có connection rảnh không? Request có phải chờ pool? |
| Database | Query plan, lock, I/O, CPU và connection utilization ra sao? |

Không nên kết luận database chậm chỉ vì endpoint chậm. Endpoint có thể tốn thời gian mapping dữ liệu lớn, chờ pool, gọi dịch vụ ngoài hoặc serialize response.

Tương tự, database health báo UP không có nghĩa query đang chạy nhanh hoặc pool còn capacity.

## 2. Quan sát connection pool HikariCP

Spring Boot thường dùng HikariCP làm connection pool cho DataSource JDBC. Pool giữ một tập connection vật lý và cấp lại cho các thao tác database, giúp tránh tạo connection mới cho mỗi statement.

Các metric thường được cung cấp khi HikariCP được tích hợp với Micrometer:

| Metric | Ý nghĩa |
| --- | --- |
| `hikaricp.connections.active` | Số connection đang được ứng dụng mượn. |
| `hikaricp.connections.idle` | Số connection đang rảnh trong pool. |
| `hikaricp.connections.pending` | Số thread đang chờ connection. |
| `hikaricp.connections.max` | Giới hạn connection tối đa. |
| `hikaricp.connections.min` | Mức idle tối thiểu được cấu hình. |
| `hikaricp.connections.acquire` | Thời gian chờ lấy connection. |
| `hikaricp.connections.usage` | Thời gian connection được giữ trước khi trả pool. |
| `hikaricp.connections.creation` | Thời gian tạo physical connection. |
| `hikaricp.connections.timeout` | Số lần acquisition timeout. |

Tên metric và tag có thể thay đổi theo phiên bản HikariCP/Micrometer và cấu hình registry. Kiểm tra danh sách metric thực tế từ Actuator hoặc registry đang sử dụng.

### 2.1. Hiểu active, idle và pending

Ba metric quan trọng nhất khi điều tra pool:

- **Active cao:** nhiều request đang giữ connection.
- **Idle thấp:** pool còn ít connection sẵn sàng.
- **Pending lớn hơn 0:** có thread phải chờ connection được trả về.

Một ảnh chụp tức thời chưa đủ để kết luận pool bị cạn. Hãy quan sát xu hướng trong một khoảng thời gian, đối chiếu throughput và latency của request.

Ví dụ:

```text
maximum connections = 20
active connections  = 20
idle connections    = 0
pending borrowers   = 12
acquire p95         = 850 ms
```

Nếu trạng thái này kéo dài cùng lúc request latency tăng, pool có thể đang là bottleneck. Tiếp theo cần tìm lý do connection bị giữ lâu: transaction dài, query chậm, lock wait hoặc code không trả connection.

### 2.2. Cấu hình pool và timeout

Ví dụ cấu hình:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      validation-timeout: 5000
```

Đây là giá trị minh họa, không phải cấu hình dùng chung cho mọi hệ thống. Cần chọn dựa trên database capacity, số instance ứng dụng, số luồng đồng thời và thời gian giữ connection.

`connection-timeout` giới hạn thời gian chờ pool cấp connection. Khi hết thời gian, Hikari ném lỗi acquisition timeout. Tăng timeout có thể làm request chờ lâu hơn mà không giải quyết tình trạng thiếu connection.

### 2.3. Tổng pool size trên nhiều instance

Nếu một service chạy nhiều replica, tổng số connection tối đa có thể tính gần đúng:

```text
total possible connections
    = maximumPoolSize per instance
      × number of application instances
```

Ví dụ 6 instance, mỗi instance có maximum pool size 20, có thể tạo tối đa 120 connection tới database. Cần cộng thêm connection từ job, migration, admin tool và các service khác.

Đừng chỉ xem pool size của một instance. Hãy so sánh tổng nhu cầu với giới hạn database và giữ lại capacity cho hoạt động quản trị/replication.

### 2.4. Leak detection và connection usage

HikariCP có `leakDetectionThreshold` để log khi connection được mượn lâu hơn ngưỡng đã đặt. Ví dụ:

```yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 60000
```

Ngưỡng 60 giây chỉ là ví dụ. Nếu đặt quá thấp, transaction hoặc query hợp lệ nhưng dài có thể tạo cảnh báo giả. Leak detection giúp tìm nơi giữ connection lâu, không tự chứng minh connection đã bị rò rỉ vĩnh viễn.

Khi thấy cảnh báo, kiểm tra stack trace nơi connection được mượn, thời gian transaction, query latency và việc resource có được đóng/trả trong mọi nhánh exception hay không.

## 3. Expose metrics bằng Spring Boot Actuator

Spring Boot Actuator cung cấp endpoint health và metrics. Với Micrometer registry phù hợp, ứng dụng có thể xuất metrics sang Prometheus hoặc hệ thống giám sát khác.

Ví dụ cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
```

Chỉ expose những endpoint thực sự cần. Endpoint quản trị có thể tiết lộ thông tin về môi trường, bean, cấu hình hoặc trạng thái nội bộ. Hãy giới hạn bằng authentication, authorization và network policy.

### 3.1. Kiểm tra health

Endpoint `/actuator/health` cung cấp trạng thái tổng quát. Khi database health indicator được bật, health response có thể cho biết datasource có kết nối được hay không.

Health check hữu ích cho readiness/availability, nhưng không thay thế dashboard performance. Một database có thể trả lời health check nhanh trong khi một query nghiệp vụ cụ thể rất chậm.

Trong hệ thống có liveness/readiness probe, hãy phân biệt:

- **Liveness:** process có còn sống và có thể tiếp tục chạy không.
- **Readiness:** instance có sẵn sàng nhận traffic không.
- **Dependency health:** database hoặc dịch vụ phụ thuộc có đang khả dụng không.

Không nên làm liveness thất bại chỉ vì database tạm thời mất kết nối nếu việc restart liên tục không giúp phục hồi và có thể tạo restart storm. Policy readiness cần phù hợp kiến trúc và cách hệ thống xử lý dependency outage.

### 3.2. Xem metrics cụ thể

Khi Actuator được cấu hình và endpoint được expose, có thể truy vấn metric theo tên, ví dụ:

```text
/actuator/metrics/hikaricp.connections.active
/actuator/metrics/hikaricp.connections.pending
/actuator/metrics/jdbc.connections.active
```

Tên metric khả dụng tùy DataSource pool và registry. Endpoint metrics phù hợp để kiểm tra trong môi trường quản trị; dashboard production thường lấy dữ liệu từ Prometheus/OTLP hoặc backend tương đương thay vì poll thủ công từng metric.

### 3.3. Metric cho application service

Bổ sung Timer/Counter ở ranh giới use case để biết operation nào tạo tải database:

```java
@Service
public class OrderQueryService {

    private final OrderRepository orders;
    private final Timer timer;

    public OrderQueryService(
            OrderRepository orders,
            MeterRegistry registry) {
        this.orders = orders;
        this.timer = registry.timer("app.orders.search");
    }

    public List<Order> findPending() {
        return timer.record(
            () -> orders.findByStatus(OrderStatus.PENDING)
        );
    }
}
```

Có thể thêm counter cho lỗi theo loại exception đã phân loại, nhưng tag phải có cardinality thấp. Không đưa ID đơn hàng, email, SQL đầy đủ hoặc exception message vào metric label.

## 4. Quan sát truy vấn chậm

Query chậm có thể đến từ nhiều nguyên nhân:

- Thiếu index hoặc index không được optimizer chọn.
- Query đọc quá nhiều row.
- Join, sort hoặc aggregate tốn kém.
- Lock wait hoặc transaction khác giữ lock.
- Database thiếu CPU, memory hoặc I/O capacity.
- Parameter distribution làm query plan không phù hợp.
- Kết quả lớn khiến driver và ứng dụng mất thời gian đọc/materialize.

Cần kết hợp statement timing ở application với database query statistics để tìm đúng nguyên nhân.

### 4.1. Đo query duration ở JDBC boundary

Có thể dùng datasource-proxy hoặc P6Spy để quan sát thời gian statement:

```java
public class QueryTimingListener implements QueryExecutionListener {

    private final MeterRegistry registry;

    public QueryTimingListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeQuery(
            ExecutionInfo executionInfo,
            List<QueryInfo> queryInfoList) {
    }

    @Override
    public void afterQuery(
            ExecutionInfo executionInfo,
            List<QueryInfo> queryInfoList) {

        Timer.builder("app.jdbc.statement")
            .tag("outcome",
                executionInfo.isSuccess() ? "success" : "error")
            .register(registry)
            .record(
                executionInfo.getElapsedTime(),
                TimeUnit.MILLISECONDS
            );
    }
}
```

Đây là ví dụ listener rút gọn; cần dependency datasource-proxy và cấu hình wrapper DataSource để repository sử dụng đúng wrapper. Hãy bổ sung cách phân loại operation/query fingerprint trong collector riêng nếu cần thống kê theo nhóm SQL.

Thời gian proxy đo ở JDBC boundary có thể bao gồm một phần chi phí driver/network. Nó không thay thế thời gian thực thi nội bộ của database. Muốn biết database dành thời gian ở scan, join, sort hay lock, cần xem telemetry/plan từ database.

### 4.2. Dùng query fingerprint thay vì raw SQL làm metric tag

Các câu query có thể khác nhau chỉ vì parameter:

```sql
SELECT * FROM purchase_orders WHERE id = 101;
SELECT * FROM purchase_orders WHERE id = 102;
SELECT * FROM purchase_orders WHERE id = 103;
```

Nếu đưa toàn bộ SQL vào metric tag, mỗi giá trị parameter có thể tạo một time series riêng. Thay vào đó, dùng query fingerprint/normalized SQL hoặc nhóm operation ổn định.

Không đưa parameter nhạy cảm vào fingerprint, log hoặc trace. Khi cần debug một query cụ thể, sử dụng log/tracing được bảo vệ với retention và quyền truy cập phù hợp.
## 5. Dùng database telemetry để tìm query tốn tài nguyên

JDBC timing cho biết ứng dụng chờ bao lâu ở statement. Database telemetry cho biết query đã sử dụng tài nguyên gì và vì sao nó chậm.

Các công cụ theo database:

| Database | Công cụ quan sát |
| --- | --- |
| PostgreSQL | `pg_stat_statements`, slow query log, `EXPLAIN (ANALYZE, BUFFERS)`. |
| MySQL | Performance Schema, statement digest summary, slow query log, EXPLAIN. |
| SQL Server | Query Store, actual execution plan, wait statistics. |
| Oracle | AWR/ASH và SQL monitoring theo cấu hình/giấy phép. |

Ví dụ với PostgreSQL, `pg_stat_statements` tổng hợp query theo dạng chuẩn hóa và cung cấp số lần gọi, thời gian thực thi, số row và các thống kê I/O. Nó giúp tìm query có tổng thời gian lớn hoặc mean latency cao.

Không nên chỉ xếp hạng theo query chậm nhất một lần. Một query mất 200 ms nhưng chạy một lần có thể ít ảnh hưởng hơn query mất 20 ms nhưng chạy hàng chục nghìn lần.

### 5.1. Phân biệt mean latency và total time

Theo dõi cả:

- Calls: số lần query được gọi.
- Mean execution time: thời gian trung bình mỗi lần.
- Total execution time: tổng thời gian cộng dồn.
- Rows: số hàng trả về hoặc tác động.
- Shared block reads/hits hoặc I/O tương đương.
- Lock/wait time nếu database cung cấp.

Một query có mean latency thấp nhưng calls rất cao thường gợi ý N+1 hoặc round-trip lặp. Một query có calls thấp nhưng total time cao có thể là báo cáo nặng hoặc query plan kém.

### 5.2. Dùng EXPLAIN để xem query plan

Khi tìm được query chậm, lấy query đại diện và phân tích execution plan. Với PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, total_amount
FROM purchase_orders
WHERE customer_id = 42
  AND status = 'PENDING'
ORDER BY created_at DESC
LIMIT 50;
```

Xem các điểm:

- Scan type: sequential scan hay index scan.
- Số row ước lượng so với số row thực tế.
- Join strategy và thứ tự join.
- Sort/hash có spill ra disk không.
- Buffer hit/read và I/O.
- Predicate nào lọc được ít row hơn dự kiến.

`EXPLAIN ANALYZE` thực thi query để đo thời gian thực tế. Chỉ dùng trên query an toàn và môi trường phù hợp; với câu lệnh ghi hoặc query rất nặng, cần đánh giá side effect và tải trước khi chạy.

## 6. Quan sát lỗi database

Không phải mọi exception đều là lỗi hạ tầng. Hãy phân loại theo nhóm Spring Data exception để biết cần hành động gì.

| Nhóm | Ví dụ | Ý nghĩa vận hành |
| --- | --- | --- |
| Integrity violation | `DuplicateKeyException`, `DataIntegrityViolationException` | Dữ liệu hoặc constraint không phù hợp; có thể là lỗi nghiệp vụ hoặc bug. |
| SQL/schema | `BadSqlGrammarException` | Query hoặc schema không tương thích; cần sửa code/migration. |
| Concurrency | `OptimisticLockingFailureException`, lock exception | Có cạnh tranh cập nhật hoặc lock contention. |
| Timeout | `QueryTimeoutException` | Query hoặc lock wait vượt ngưỡng. |
| Resource failure | `DataAccessResourceFailureException` | Database/connection/resource không khả dụng. |
| Unknown JDBC | `UncategorizedSQLException` | Translator chưa phân loại; cần xem cause, SQLState và vendor code. |

Nên có counter theo exception class hoặc nhóm lỗi ổn định:

```text
app.database.errors{category="integrity"}
app.database.errors{category="timeout"}
app.database.errors{category="resource"}
app.database.errors{category="concurrency"}
app.database.errors{category="sql"}
```

Không dùng exception message làm tag vì message có thể chứa SQL, parameter hoặc dữ liệu thay đổi liên tục. Nếu cần phân tích vendor code, ghi log/trace đã redact thay vì tạo hàng nghìn metric label.

### 6.1. Theo dõi tỷ lệ lỗi, không chỉ số lượng

100 lỗi trong một phút có thể nghiêm trọng với service chỉ nhận 200 request/phút, nhưng ít đáng lo hơn với hệ thống nhận hàng triệu request/phút.

Theo dõi error rate theo tỷ lệ:

```text
database error rate
    = failed database operations
      / total database operations
```

Kết hợp tỷ lệ lỗi với request throughput, latency và trạng thái pool. Ví dụ resource failure tăng cùng acquisition timeout có thể chỉ ra database outage hoặc pool không thể tạo connection.

### 6.2. Giữ cause chain và SQLState trong log

Khi log exception, giữ stack trace và cause. Nếu cause là SQLException, có thể ghi SQLState/vendor code theo policy:

```java
Throwable cause = ex;

while (cause != null && !(cause instanceof SQLException)) {
    cause = cause.getCause();
}

if (cause instanceof SQLException sqlException) {
    log.warn(
        "Database operation failed: sqlState={}, vendorCode={}",
        sqlException.getSQLState(),
        sqlException.getErrorCode(),
        ex
    );
}
```

Đoạn code minh họa cách tìm SQLException trong cause chain; trong thực tế, SQLException có thể còn nối thêm exception qua `getNextException()`. Không log raw parameter hoặc message chứa thông tin cá nhân nếu chưa được lọc.

## 7. Thiết kế dashboard và cảnh báo

Một dashboard vận hành nên kết hợp metrics ứng dụng, pool và database.

### 7.1. Dashboard connection pool

Hiển thị:

- Active/idle/max connections.
- Pending borrowers.
- Connection acquisition p50/p95/p99.
- Connection usage duration.
- Acquisition timeout count.
- Physical connection creation rate.

### 7.2. Dashboard SQL

Hiển thị:

- Statement count theo SELECT/INSERT/UPDATE/DELETE.
- Query latency p50/p95/p99.
- Top query fingerprints theo total execution time.
- Top query theo calls.
- Slow query count.
- Rows returned/affected nếu instrumentation hỗ trợ.

### 7.3. Dashboard lỗi

Hiển thị:

- Database error rate.
- Exception count theo nhóm.
- Deadlock/lock timeout count nếu database cung cấp.
- Optimistic locking conflict rate.
- Connection acquisition failures.
- Database health và connection utilization.

### 7.4. Nguyên tắc đặt alert

Không có một ngưỡng chung đúng cho mọi hệ thống. Alert nên dựa trên SLO và baseline của service.

Ví dụ điều kiện cần xem xét:

| Tín hiệu | Khi nào nên cảnh báo |
| --- | --- |
| Pending connections | Tăng liên tục trong nhiều cửa sổ đo, đồng thời acquisition latency tăng. |
| Active/max ratio | Gần 100% kéo dài và request latency xấu đi. |
| Acquisition timeout | Có timeout mới hoặc tỷ lệ vượt ngưỡng vận hành. |
| Query p95/p99 | Vượt SLO hoặc tăng bất thường so với baseline. |
| Slow query volume | Số query vượt slow threshold tăng đột biến. |
| Database error rate | Tỷ lệ lỗi vượt ngưỡng và ảnh hưởng request. |
| Database availability | Health check thất bại kéo dài hoặc nhiều instance cùng mất kết nối. |

Dùng alert có thời gian duy trì (for duration) để tránh cảnh báo vì một spike ngắn. Với lỗi nghiêm trọng như database unavailable, có thể cần cảnh báo nhanh hơn so với cảnh báo pool utilization.

## 8. Chẩn đoán pool exhaustion theo trình tự

Khi thấy pending connections và acquisition time tăng:

1. Xác nhận vấn đề ảnh hưởng một instance hay tất cả instance.
2. Xem active, idle, pending và acquisition timeout.
3. Kiểm tra connection usage duration và transaction duration.
4. Tìm query chậm hoặc lock wait đang giữ connection.
5. Kiểm tra code có gọi HTTP, publish message hoặc làm xử lý CPU nặng bên trong transaction không.
6. Đối chiếu database connection limit và số connection từ tất cả service.
7. Kiểm tra connection leak warning và stack trace.
8. Chỉ thay đổi pool size sau khi biết database còn capacity và nguyên nhân không phải transaction/query bị giữ lâu.

Ví dụ:

- Active luôn bằng max.
- Pending tăng.
- Query latency cũng tăng.
- Database CPU/lock wait cao.

Tăng pool size trong trường hợp này có thể làm database nhận thêm concurrent work và càng quá tải. Cần điều tra query plan, lock và transaction duration trước.

Một trường hợp khác:

- Active bằng max.
- Query latency thấp.
- Usage duration rất cao.
- Log cho thấy service gọi API bên ngoài trong transaction.

Lúc này connection bị giữ trong khi chờ network. Có thể rút ngắn transaction và chuyển side effect ra sau commit.

## 9. Chẩn đoán truy vấn chậm theo trình tự

Khi query p95/p99 tăng:

1. Xác định query fingerprint/use case có latency tăng.
2. So sánh calls, total time, rows và error rate.
3. Kiểm tra acquisition time để biết có phải chờ pool.
4. Lấy SQL/parameter đại diện qua trace hoặc log đã bảo vệ.
5. Kiểm tra query statistics và execution plan ở database.
6. Xem index, row estimate, join, sort, lock và I/O.
7. Kiểm tra kích thước result set và thời gian mapping/serialization.
8. Thay đổi query/index/projection/pagination dựa trên bằng chứng.
9. Chạy lại cùng workload và so sánh percentile, throughput, pool và database resource.

Không tối ưu chỉ vì một câu query nhìn có vẻ dài. Một câu SQL phức tạp có thể có plan tốt; một query đơn giản có thể quét hàng triệu row nếu thiếu index.

## 10. Tích hợp tracing và log

Distributed tracing giúp nối một request với các operation JDBC bên trong. Khi có instrumentation phù hợp, trace có thể thể hiện:

```text
HTTP POST /orders                 420 ms
  service.placeOrder              395 ms
    repository.save               120 ms
      JDBC INSERT purchase_orders  35 ms
      JDBC INSERT order_lines      48 ms
      JDBC UPDATE inventory        22 ms
    outbox.insert                  18 ms
```

Ví dụ trên chỉ minh họa cấu trúc span. Tên span và mức chi tiết phụ thuộc tracing instrumentation đang dùng.

Một số nguyên tắc:

- Dùng trace ID/span ID trong log để nối các sự kiện.
- Giữ metric tag cardinality thấp; trace mới là nơi phù hợp hơn cho chi tiết từng request.
- Không ghi SQL parameter nhạy cảm vào span attribute.
- Sampling phải cân bằng chi phí với khả năng điều tra lỗi hiếm.
- Giữ trace của request lỗi hoặc chậm theo policy phù hợp nếu hệ thống hỗ trợ tail sampling.

Metrics cho xu hướng, logs cho chi tiết sự kiện, traces cho quan hệ thời gian giữa các bước. Ba nguồn này nên bổ sung cho nhau.

## 11. Bảo vệ thông tin vận hành

Database telemetry có thể chứa thông tin nhạy cảm. Cần kiểm soát:

- Actuator endpoints chỉ truy cập được từ mạng/quyền quản trị phù hợp.
- Chỉ expose health/metrics/prometheus nếu thực sự cần.
- Không public endpoint chứa environment/configuration hoặc bean details.
- Redact SQL parameter, token, email và dữ liệu cá nhân.
- Giới hạn quyền đọc slow query log và database performance schema.
- Thiết lập retention và quyền truy cập cho logs/traces.
- Không đưa raw SQL, user ID hoặc query parameter vào metric label.

Health details có thể tiết lộ host, database name hoặc trạng thái dependency. Chỉ hiển thị cho caller được authorize.

## 12. Kiểm thử instrumentation và cảnh báo

Để chắc chắn quan sát hoạt động:

- Integration test xác nhận Hikari/DataSource metrics xuất hiện trong registry.
- Test query proxy đếm được SELECT/INSERT và ghi nhận elapsed time.
- Test error path xác nhận DataAccessException được đếm đúng nhóm.
- Test dashboard query dùng tag ổn định và không tạo label theo ID/SQL.
- Kiểm tra alert rule bằng dữ liệu mô phỏng hoặc staging.
- Kiểm tra health endpoint không lộ chi tiết cho caller chưa được authorize.

Không nên dùng unit test để khẳng định database thật đang khỏe. Health và pool behavior cần integration/operational verification trên môi trường có datasource thực.

## 13. Những lỗi vận hành thường gặp

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Pending connection tăng | Pool bận hoặc connection bị giữ lâu. | Xem usage time, query latency và transaction duration. |
| Active luôn bằng max | Quá nhiều concurrent work hoặc transaction dài. | Điều tra workload và database capacity trước khi tăng pool. |
| Acquisition timeout | Pool không cấp connection trong timeout. | Kiểm tra pending, database availability và connection leak. |
| Query p99 tăng nhưng pool bình thường | Database query plan, lock hoặc result size. | Xem query statistics và EXPLAIN. |
| Health UP nhưng endpoint chậm | Health check chỉ xác nhận khả năng kết nối cơ bản. | Xem latency, query stats và pool metrics. |
| Slow query log tăng mạnh | Query plan thay đổi, thiếu index hoặc tải tăng. | Nhóm theo fingerprint và xem calls/total time. |
| Database error rate tăng | Constraint, timeout, outage hoặc deploy schema mismatch. | Phân loại DataAccessException và đối chiếu migration/deploy. |
| Leak detection warning | Connection bị giữ lâu hoặc không được trả đúng cách. | Kiểm tra stack trace và transaction scope. |
| Metrics backend quá tải | Tag cardinality cao hoặc xuất quá nhiều chi tiết SQL. | Chuẩn hóa tag và chuyển chi tiết sang log/trace có kiểm soát. |
| Alert chập chờn | Ngưỡng quá nhạy hoặc không có thời gian duy trì. | Dùng baseline, SLO và alert duration phù hợp. |

## 14. Quy trình vận hành thường xuyên

Một quy trình thực tế có thể gồm:

1. Theo dõi dashboard pool, query latency, database error rate và request SLO.
2. Định kỳ xem top query theo total time và call count.
3. Đặt cảnh báo cho pending/acquisition timeout, slow query và database availability.
4. Khi alert xảy ra, dùng trace ID để tìm request bị ảnh hưởng.
5. Đối chiếu JDBC statement timing với database execution statistics.
6. Kiểm tra connection usage, transaction duration và lock wait.
7. Ghi lại nguyên nhân, phạm vi ảnh hưởng và thay đổi đã thực hiện.
8. Chạy lại workload sau khi tối ưu để xác nhận cải thiện.
9. Rà soát quyền truy cập, retention và redaction của telemetry định kỳ.

> **Quan sát production cần kết hợp pool metrics, query statistics, exception rate, logs và traces.** Pending/active cho biết áp lực connection; JDBC timing cho biết statement nào chậm; database telemetry giải thích query plan, lock và I/O; DataAccessException cho biết loại lỗi. Health check chỉ phản ánh khả năng hoạt động cơ bản, còn alert phải dựa trên baseline và SLO của service.

### Tài liệu tham khảo

- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics, Micrometer và datasource instrumentation.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure và bảo vệ endpoint quản trị.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP): connection pool settings, timeout và leak detection.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): latency timer và percentile/histogram.
- [OpenTelemetry — Java Instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/): tracing và JDBC instrumentation.
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): thống kê query theo fingerprint.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): phân tích execution plan.
- [MySQL — Performance Schema](https://dev.mysql.com/doc/refman/8.4/en/performance-schema.html): quan sát hoạt động SQL và tài nguyên database.
- [Spring Data JDBC — Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repository và persistence behavior.
