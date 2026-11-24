# Phân biệt query time và pool wait time trong Spring Boot

> **Chương:** Database observability  
> **Bài:** Phân biệt query time và pool wait time  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao phải tách query time và pool wait time?

Khi một repository call mất 800 ms, nguyên nhân không nhất thiết là câu SQL chạy chậm. Ứng dụng có thể mất 700 ms chỉ để chờ lấy connection từ pool, sau đó query thực thi trong 100 ms. Nếu chỉ nhìn một timer tổng, nhóm phát triển có thể tối ưu SQL trong khi nguyên nhân thật là pool saturation.

**Pool wait time** là thời gian request chờ được cấp một database connection từ connection pool. **Query time** là thời gian thực hiện thao tác database theo ranh giới đo cụ thể, thường bắt đầu khi statement được thực thi và kết thúc khi driver nhận kết quả tương ứng. Cần làm rõ query time có bao gồm đọc hết result set hay không.

Hai chỉ số trả lời hai câu hỏi khác nhau:

- Pool wait time: ứng dụng có đủ connection rảnh để phục vụ concurrency hiện tại không?
- Query time: sau khi có connection, database operation mất bao lâu?
- Repository duration: toàn bộ lời gọi repository mất bao lâu, gồm cả các phần phụ trợ trong method.
- Transaction duration: transaction giữ tài nguyên trong bao lâu, kể cả thời gian giữa các statements.

~~~mermaid
flowchart LR
  A["Repository call begins"] --> B["Acquire connection"]
  B --> C["Connection granted"]
  C --> D["Prepare / execute query"]
  D --> E["Read result"]
  E --> F["Release connection"]
  A -. "Pool wait time" .-> C
  C -. "Query / DB operation time" .-> E
  A -. "Repository duration" .-> F
~~~

Đo và dashboard riêng từng giai đoạn giúp xác định đúng bottleneck thay vì kết luận chung chung rằng database chậm.

## 2. Connection pool hoạt động như thế nào?

Mở một TCP connection mới tới database cho mỗi query thường tốn chi phí và có thể làm database quá tải. Connection pool duy trì một tập connections đã được tạo sẵn để nhiều request mượn và trả lại.

Với HikariCP, Spring Boot thường tự cấu hình pool khi có JDBC datasource phù hợp. Một connection được mượn bằng getConnection(), sử dụng trong transaction/statement, rồi trả về pool khi hoàn tất.

~~~mermaid
flowchart TD
  A["Concurrent application requests"] --> B["HikariCP connection pool"]
  B --> C{"Có idle connection?"}
  C -->|"Có"| D["Borrow connection"]
  C -->|"Không, còn capacity"| E["Create connection"]
  C -->|"Pool đạt maximum"| F["Wait in acquisition queue"]
  D --> G["Execute SQL"]
  E --> G
  G --> H["Return connection"]
  H --> B
  F -->|"Timeout"| I["Connection acquisition failure"]
  F -->|"Connection released"| D
~~~

Pool giới hạn số connections đồng thời từ một instance ứng dụng tới database. Khi tất cả connections đã được mượn, request mới phải chờ hoặc thất bại khi acquisition timeout hết hạn.

Pool wait tăng có thể do:
- Traffic/concurrency vượt capacity hiện tại.
- Query hoặc transaction giữ connection quá lâu.
- Connection leak hoặc code không đóng resource.
- Database chậm khiến connections không được trả về nhanh.
- Pool size quá nhỏ so với workload.
- Nhiều replicas cùng chia sẻ giới hạn connection của database.

Không mặc định pool càng lớn càng tốt. Tăng pool size làm tăng số sessions đồng thời mà database phải phục vụ, có thể khiến DB CPU, lock contention và memory pressure tăng.

## 3. Định nghĩa chính xác các khoảng thời gian

Một lần repository call có thể chứa nhiều giai đoạn. Để tránh cộng hoặc so sánh sai, hãy thống nhất các mốc:

| Khoảng thời gian | Bắt đầu | Kết thúc | Bao gồm |
| --- | --- | --- | --- |
| Pool acquisition | Gọi lấy connection | Connection được cấp hoặc timeout | Chờ pool, có thể gồm tạo connection tùy metric |
| Connection creation | Bắt đầu mở physical connection | Connection sẵn sàng | DNS/TCP/TLS/authentication tùy driver |
| Statement execution | Gửi/execute statement | Driver báo execution/result sẵn sàng theo API | Network và DB processing theo driver semantics |
| Result consumption | Bắt đầu đọc rows | Rows được consume xong | Transfer dữ liệu, decoding/mapping tùy đo |
| Repository duration | Vào method | Method return/error | Các query và application code bên trong |
| Transaction duration | Begin | Commit/rollback | Nhiều statements và thời gian giữa chúng |

Các driver có semantics khác nhau. JDBC executeQuery() có thể trả ResultSet trước khi toàn bộ rows được đọc; với streaming hoặc fetch size, thời gian tiêu thụ result có thể kéo dài sau execute call. R2DBC publishers có thể chỉ thực thi khi subscription và completion diễn ra.

**Query time không phải một khái niệm duy nhất nếu chưa định nghĩa ranh giới.** Đặt tên metric/span mô tả đúng thứ đang đo.

## 4. Ví dụ số: repository chậm nhưng query nhanh

Giả sử một request có số đo:

~~~text
Repository duration       = 820 ms
Pool acquisition wait     = 690 ms
Query execution           = 95 ms
Result mapping            = 25 ms
Other application work   = 10 ms
~~~

Tổng các phần minh họa bằng 820 ms. Pool wait chiếm phần lớn thời gian; tối ưu index có thể chỉ giảm 95 ms query execution và không giải quyết nguyên nhân chính.

Một request khác:

~~~text
Repository duration       = 850 ms
Pool acquisition wait     = 5 ms
Query execution           = 810 ms
Result mapping            = 35 ms
~~~

Trường hợp này pool không phải bottleneck. Cần kiểm tra query plan, lock wait, DB load, network và số rows.

Không phải instrumentation nào cũng cung cấp các phần thời gian cộng lại chính xác thành repository duration. Ví dụ trên là mô hình phân tích; hãy xác minh timer thực tế có overlap hoặc bỏ sót giai đoạn nào.

## 5. HikariCP metrics trong Spring Boot

Khi Actuator và Micrometer được cấu hình phù hợp, HikariCP có thể cung cấp pool metrics. Các meter phổ biến thường mô tả:

| Nhóm metric | Ý nghĩa |
| --- | --- |
| Active connections | Connections đang được mượn |
| Idle connections | Connections đang rảnh |
| Maximum connections | Giới hạn pool |
| Minimum connections | Mức idle tối thiểu được cấu hình |
| Pending threads | Số threads đang chờ connection |
| Connection acquisition | Thời gian chờ lấy connection, tùy binder/version |
| Connection usage | Thời gian connection được sử dụng, tùy binder/version |

Tên meter/tag cụ thể phụ thuộc phiên bản Spring Boot, Micrometer và pool implementation. Hãy xem endpoint Actuator metrics hoặc registry thay vì đoán tên.

Ví dụ cấu hình Actuator exposure trong môi trường dev:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Chỉ expose endpoint cần thiết và bảo vệ bằng security/network policy. Không mở metrics endpoint công khai chỉ để debug pool.

## 6. Đọc pool saturation từ các metrics

Một pool có dấu hiệu bão hòa khi active connections liên tục gần maximum và pending threads tăng. Nhưng một snapshot đơn lẻ chưa đủ; cần xem theo thời gian và đối chiếu workload.

Các chỉ số:

- Active gần maximum trong thời gian dài.
- Idle bằng 0 hoặc gần 0.
- Pending threads tăng.
- Acquisition latency p95/p99 tăng.
- Connection timeout count tăng.
- Usage duration tăng bất thường.

Ví dụ:

~~~text
maximum = 20
active  = 20
idle    = 0
pending = 35
~~~

Đây là dấu hiệu có nhiều request đang tranh connection. Nguyên nhân sâu hơn có thể là query chậm, transaction dài, lock wait hoặc pool quá nhỏ; pending không tự chứng minh cần tăng maximum.

### 6.1. Phân biệt saturation với connection leak

Saturation có thể là tải cao hợp lệ, trong khi leak là connection không được trả về đúng cách. Cả hai có thể làm active luôn cao và pending tăng.

Dấu hiệu nghi leak:
- Active connections tăng dần và không giảm sau khi traffic hạ.
- Một số connection bị giữ lâu bất thường.
- Hikari leak detection cảnh báo connection đã được mượn quá ngưỡng.
- Thread dump cho thấy code path không đóng resource hoặc transaction treo.

Leak detection threshold là công cụ chẩn đoán, không phải cơ chế tự sửa leak. Threshold quá thấp có thể tạo cảnh báo giả cho transaction hợp lệ nhưng dài.

## 7. Query time được đo ở đâu?

Query time có thể được quan sát ở nhiều tầng:

1. Database-native statement statistics/slow query logs.
2. JDBC driver hoặc datasource instrumentation.
3. OpenTelemetry JDBC instrumentation/Java agent.
4. Micrometer Observation/Tracing integration.
5. Custom timer quanh repository/service method.

Mỗi tầng có ranh giới và overhead khác nhau. Ví dụ custom Timer quanh repository method thường bao gồm pool wait và mapping, trong khi một driver span có thể tập trung vào statement execution.

~~~java
@Repository
public class OrderRepository {
    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Order findById(long id) {
        return jdbcTemplate.queryForObject(
                "select id, status from orders where id = ?",
                (rs, rowNum) -> new Order(
                        rs.getLong("id"),
                        rs.getString("status")),
                id);
    }
}
~~~

Để đo query time đúng nghĩa, ưu tiên instrumentation tại JDBC/driver/datasource có semantics được tài liệu hóa. Không gọi timer quanh repository rồi đặt tên là database execution time nếu timer bao gồm acquisition và application processing.

## 8. JDBC và R2DBC: khác biệt về pool wait và query timing

### 8.1. JDBC

JDBC thường dùng blocking calls. Việc lấy connection thường xảy ra khi gọi DataSource.getConnection(). Statement execution và ResultSet consumption có các mốc API tương đối rõ nhưng vẫn phụ thuộc driver/fetch behavior.

Một call repository đồng bộ có thể giữ connection trong suốt transaction hoặc method. Nếu thread chờ connection, nó cũng bị chiếm trong lúc pool wait.

### 8.2. R2DBC

R2DBC dùng reactive publishers. Connection acquisition và query thường diễn ra trong subscription. Đo thời gian tạo publisher không đo thời gian chờ pool hay thực thi database.

~~~java
Mono<Order> order = connectionFactory.create()
        .flatMap(connection ->
                executeQuery(connection, orderId)
                    .doFinally(signal -> connection.close()));
~~~

Ví dụ khái niệm cần được triển khai theo API/driver cụ thể; connection close trong R2DBC thường là publisher operation và cần được compose đúng cách. Dùng Spring DatabaseClient hoặc transaction manager phù hợp thay vì tự quản lý connection thiếu lifecycle.

Trong cả JDBC và R2DBC, cần đo riêng acquisition và database operation nếu muốn phân biệt bottleneck.

## 9. Transaction giữ connection lâu hơn query

Một transaction có thể thực hiện query nhanh nhưng giữ connection trong lúc application code làm thêm việc.

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    inventoryRepository.reserve(command.items());
    validateBusinessRules(command);
    pricingService.calculate(command);
    orderRepository.save(command);
}
~~~

Nếu validateBusinessRules hoặc pricingService làm công việc chậm trong transaction, connection có thể vẫn được giữ. Khi concurrency cao, pool wait tăng dù từng SQL statement không chậm.

Nguyên tắc:
- Giữ transaction càng ngắn càng tốt nhưng vẫn bảo đảm atomicity.
- Tránh gọi HTTP dependency bên trong transaction DB nếu không cần.
- Không thực hiện sleep hoặc xử lý file lớn khi đang giữ connection.
- Kiểm tra transaction propagation và nested calls.
- Đo transaction duration riêng với statement duration.

Không chuyển logic ra ngoài transaction nếu điều đó phá vỡ consistency. Cần xác định boundary nghiệp vụ và cơ chế outbox/saga nếu transaction liên quan nhiều hệ thống.

## 10. Lock wait làm query time tăng và pool bị chiếm

Một query chờ lock vẫn giữ connection trong nhiều trường hợp. Vì vậy database lock contention có thể gây ra cả query latency cao lẫn pool saturation.

~~~mermaid
flowchart TD
  A["Transaction A holds row lock"] --> B["Transaction B executes UPDATE"]
  B --> C["B waits for lock"]
  C --> D["Connection B remains occupied"]
  D --> E["Pool has fewer free connections"]
  E --> F["Other requests wait for pool"]
  C --> G["Query / transaction latency rises"]
  F --> H["Pool acquisition latency rises"]
~~~

Khi thấy cả query time và pool wait time tăng, đừng vội kết luận pool size là gốc rễ. Database có thể đang giữ connections do lock wait hoặc slow queries. Xem database wait events, blocking sessions, transaction age và query plan.

## 11. Pool size và connection budget toàn hệ thống

Pool size phải được tính trên toàn bộ số replicas, không chỉ một process.

Ví dụ:
- 6 replicas của order-service, mỗi replica pool max 20: tối đa 120 connections.
- 4 replicas của inventory-service, mỗi replica pool max 15: tối đa 60 connections.
- Các service khác cũng tiêu thụ connection budget.

~~~text
Potential application connections
  = sum(replicas(service) * pool_max(service))
~~~

Tổng này cần nằm trong connection budget của database, chừa chỗ cho migrations, monitoring, admin sessions, replicas tăng đột biến và các ứng dụng khác.

Không tăng pool size chỉ để pending về 0. Database có thể đạt saturation ở số connections thấp hơn max pool tổng. Cần benchmark concurrency và theo dõi DB CPU, I/O, lock waits, throughput cùng latency.

## 12. Query time, pool wait và trace waterfall

Một trace tốt có thể cho thấy khoảng thời gian database operation trong request. Nhưng pool acquisition chỉ hiện riêng nếu instrumentation hỗ trợ đo nó. Nếu không, DB span có thể bao gồm cả pool wait hoặc chỉ phần execute tùy integration.

~~~text
orders.create [INTERNAL]                    900 ms
  acquire connection                        650 ms  (nếu được instrument riêng)
  SELECT order_items [CLIENT / DB]            80 ms
  INSERT orders [CLIENT / DB]                 40 ms
  result mapping / application work          130 ms
~~~

Khi xem trace:
- Kiểm tra span start/end semantics.
- Xem có span riêng cho pool acquisition không.
- So sánh DB spans với Hikari metrics.
- Không cộng span durations lồng nhau một cách máy móc.
- Xem transaction/repository spans nếu có.

Nếu DB span chỉ mất 80 ms nhưng repository mất 800 ms, thời gian chênh lệch có thể là pool wait, mapping hoặc application work. Metrics pool giúp phân biệt.

## 13. Metrics và percentile cho pool wait/query time

Dùng histogram/timer để quan sát phân phối, không chỉ average. Ví dụ tên custom metrics minh họa:

~~~text
app.db.pool.acquire
app.db.statement.duration
app.db.repository.duration
app.db.transaction.duration
~~~

Các metric này cần được tạo ở đúng instrumentation boundary và không trùng với meter tự động đã có. Có thể dùng percentile/histogram cho p50/p95/p99 và count cho throughput.

Không dùng labels có cardinality cao như SQL text, bind values, connection ID, thread name hoặc request ID. Các dimension hữu ích thường là datasource name, db.system, operation group và outcome.

Ví dụ bảng dashboard:

| Panel | Metric | Câu hỏi |
| --- | --- | --- |
| Pool acquisition p95 | Pool wait timer | Request chờ connection bao lâu? |
| Statement p95 | DB statement timer | Query execution chậm không? |
| Active/idle/pending | Pool gauges | Pool có bão hòa không? |
| Connection usage p95 | Usage timer | Connection bị giữ lâu không? |
| Transaction duration | Transaction timer | Transaction có quá dài không? |
| DB lock waits | Database-native telemetry | Query chờ tài nguyên gì? |

## 14. Timeout và failure ở pool acquisition

Nếu không lấy được connection trong acquisition timeout, repository có thể thất bại trước khi SQL được gửi. Đây không phải query timeout dù exception xuất hiện trong code repository.

HikariCP có thể phát lỗi acquisition timeout sau khi chờ quá connectionTimeout. Tên exception/message và wrapping phụ thuộc phiên bản. Cần phân biệt:
- Pool acquisition timeout: không lấy được connection.
- Driver connect timeout: tạo physical connection mới bị timeout.
- Statement/query timeout: query đã bắt đầu nhưng vượt thời gian.
- Transaction timeout: transaction vượt deadline.
- Application request timeout: caller hết budget tổng.

Đặt timeout theo thứ tự hợp lý để lỗi tầng trong được phát hiện trước deadline ngoài, nhưng không áp dụng một bộ số cố định cho mọi workload.

## 15. Kiểm tra trong Spring Boot Actuator

Actuator metrics endpoint có thể cho phép inspect meter và tag values trong môi trường được bảo vệ.

Ví dụ truy vấn endpoint:

~~~http
GET /actuator/metrics
GET /actuator/metrics/hikaricp.connections.active
GET /actuator/metrics/hikaricp.connections.pending
~~~

Tên meter trên là ví dụ phổ biến với HikariCP binder; xác minh endpoint thực tế bằng danh sách meters của ứng dụng và version. Một số metric pool có thể không xuất hiện nếu datasource/pool binder không được đăng ký.

Cần kiểm tra:
- active, idle, max, min.
- pending/waiting.
- acquisition/usage metrics nếu có.
- query timer hoặc DB spans.
- tags theo datasource/pool name.

Không expose metrics endpoint ra Internet. Dùng authentication, network restriction hoặc management port riêng.

## 16. Troubleshooting theo mẫu kết hợp

| Pool wait | Query time | Khả năng | Hướng điều tra |
| --- | --- | --- | --- |
| Cao | Thấp | Pool saturation, transaction giữ connection, leak | Pending/active, usage duration, transaction age |
| Thấp | Cao | Query plan, lock, DB load, network | Slow query, EXPLAIN, wait events |
| Cao | Cao | DB overload, lock contention, pool không đủ capacity hoặc nhiều yếu tố | DB health, pool, concurrency, transaction |
| Thấp | Thấp nhưng repository cao | Mapping/application logic hoặc nhiều query | CPU profile, query count, trace |
| Cao đột ngột sau deploy | Pool config hoặc transaction regression | So sánh version/config/traffic |
| Acquisition timeout, không có DB span | Chưa lấy được connection nên statement chưa chạy | Pool metrics và connection budget |

### Quy trình điều tra

1. Chọn service, datasource và khoảng thời gian.
2. Đối chiếu pool active/idle/pending/max.
3. Xem acquisition latency p95/p99.
4. So sánh query/statement latency và repository duration.
5. Kiểm tra transaction duration, lock waits và connection usage.
6. Xác định request concurrency và replicas tổng.
7. Kiểm tra connection leak và resource cleanup.
8. Thay đổi một yếu tố, chạy load test cùng điều kiện và so sánh.

## 17. Tình huống thực tế: pool wait tăng sau khi traffic tăng

**Bối cảnh:** order-service chạy 5 replicas. Sau khi traffic tăng gấp đôi, p95 repository duration tăng từ 90 ms lên 720 ms. DB statement p95 vẫn khoảng 35 ms. Hikari active gần maximum và pending tăng.

### Bước 1 — tách thời gian

Trace/repository timer cho thấy khoảng chờ trước statement lớn. Pool metrics xác nhận acquisition wait tăng. Query execution chưa có regression rõ.

### Bước 2 — kiểm tra connection usage

Connection usage duration tăng từ 50 ms lên 600 ms. Một transaction gọi pricing service qua HTTP trong khi đang giữ transaction DB. Connection bị giữ trong lúc chờ network.

### Bước 3 — kiểm tra tổng connection budget

Pool max 20 trên 5 replicas tạo potential 100 connections. DB có connection budget giới hạn và còn nhiều service khác. Không tăng pool ngay khi chưa đánh giá database capacity.

### Bước 4 — rút ngắn transaction

Tách remote HTTP call ra khỏi transaction nếu business consistency cho phép, giữ transaction chỉ quanh các DB operations cần atomic. Nếu quy trình cần phối hợp nhiều hệ thống, đánh giá outbox/saga hoặc cơ chế consistency phù hợp.

### Bước 5 — xác minh

Chạy lại load test với cùng concurrency. So sánh acquisition p95, usage duration, pending, query p95, transaction duration, DB CPU và request latency.

**Kết quả mong muốn:** pool wait giảm nhờ connection được trả về sớm hơn; query time vẫn ổn định; không tăng pool vượt connection budget.

## 18. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — phân biệt hai timer

Tạo repository call với pool wait giả lập và query chậm. Thu thập acquisition time, statement duration và repository duration. Giải thích phần nào được tính ở từng metric.

### Bài tập B — tạo pool saturation

Cấu hình pool nhỏ trong môi trường test, chạy nhiều request đồng thời và giữ connection trong một khoảng thời gian. Quan sát active, idle, pending, acquisition latency và timeout. Không dùng test này trên database production.

### Bài tập C — mô phỏng query chậm

Tạo query test có plan kém hoặc lock wait có kiểm soát. Quan sát query timer và pool wait. Xác nhận query chậm có thể kéo pool wait tăng cho các request khác.

### Bài tập D — transaction giữ connection

Đặt một remote call giả lập bên trong transaction. Đo connection usage và transaction duration. Sau đó tách remote call ra khi semantics cho phép và so sánh.

### Bài tập E — connection budget

Tính tổng pool maximum theo số replicas của mọi service. So sánh với database max connections, admin reserve và migration/monitoring needs. Đề xuất giới hạn an toàn.

### Bài tập F — trace và metrics

Bật JDBC instrumentation và Hikari metrics. Tạo request có query nhanh nhưng pool wait dài. Xác định trace span có đo acquisition riêng hay không; đối chiếu với pool metrics.

### Câu hỏi tự kiểm tra

1. Pool wait time đo giai đoạn nào?
2. Query execution time khác result consumption thế nào?
3. Vì sao repository duration không đồng nghĩa statement duration?
4. Active=max và pending tăng gợi ý điều gì?
5. Connection leak khác saturation do traffic như thế nào?
6. Vì sao tăng pool size có thể làm database quá tải hơn?
7. JDBC và R2DBC khác nhau thế nào về acquisition/execution lifecycle?
8. Transaction dài có thể làm pool wait tăng dù query nhanh ra sao?
9. Lock contention có thể ảnh hưởng cả query time và pool wait thế nào?
10. Khi pool acquisition timeout, SQL statement có nhất thiết đã chạy không?
11. Làm sao phân biệt pool timeout với statement timeout?
12. Vì sao cần connection budget trên toàn bộ replicas?
13. Trace DB span có luôn tách riêng pool acquisition không?
14. Những metrics nào cần xem cùng acquisition latency?
15. Làm sao xác minh một thay đổi pool/transaction thực sự cải thiện hệ thống?

**Tiêu chí hoàn thành:** định nghĩa đúng pool wait/query/repository/transaction durations; đọc Hikari metrics; phân biệt saturation, leak, lock và query regression; hiểu JDBC/R2DBC lifecycle; tính connection budget; đối chiếu trace và metrics; kiểm thử bằng load có kiểm soát.

## 19. Ghi nhớ

- Pool wait time là thời gian chờ connection; query time là thời gian database operation theo ranh giới instrumentation.
- Repository duration có thể bao gồm pool wait, nhiều queries, mapping và application code.
- Hikari active gần maximum, idle thấp, pending tăng và acquisition p95 cao là dấu hiệu pool pressure, không tự chứng minh pool cần tăng.
- Query/transaction chậm có thể giữ connection lâu và gián tiếp làm pool wait tăng.
- Tách acquisition, statement execution, result consumption, repository và transaction durations.
- JDBC blocking và R2DBC reactive có lifecycle khác nhau; đo ở đúng subscription/execution boundary.
- Tính connection budget bằng tổng replicas nhân pool maximum trên toàn hệ thống; chừa capacity cho DB và vận hành.
- Không tăng pool mù quáng; kiểm tra DB capacity, lock waits, connection usage và concurrency.
- Dùng Actuator/Hikari metrics cùng DB spans, slow query logs và database-native wait telemetry.
- Load test có kiểm soát và so sánh cùng workload trước/sau thay đổi.

## Tài liệu tham khảo

- [Spring Boot Reference — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [Micrometer — JVM and Datasource Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry Semantic Conventions — Database](https://opentelemetry.io/docs/specs/semconv/database/)
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Spring Framework — R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)

