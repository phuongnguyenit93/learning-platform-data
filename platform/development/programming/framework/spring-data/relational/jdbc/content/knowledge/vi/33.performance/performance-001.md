# Đo số câu SQL, số lượt kết nối, thời gian và dung lượng kết quả

Tối ưu hiệu năng Spring Data JDBC cần số liệu ở nhiều lớp. Một repository call có thể phát sinh nhiều câu SQL; một transaction có thể mượn một connection từ pool rồi dùng connection đó cho nhiều statement; một câu SELECT có thể nhanh ở database nhưng trả về quá nhiều hàng khiến ứng dụng tốn thời gian và bộ nhớ.

Vì vậy, khi đo một use case, cần theo dõi ít nhất bốn nhóm thông tin:

1. **Số câu SQL:** bao nhiêu statement được thực thi, thuộc loại SELECT/INSERT/UPDATE/DELETE nào và có tăng theo số aggregate hay không.
2. **Số lượt sử dụng connection:** ứng dụng mượn/trả connection từ pool bao nhiêu lần, pool đang có bao nhiêu connection active/idle và có phải chờ connection hay không.
3. **Thời gian:** thời gian tổng của use case, thời gian từng statement, thời gian chờ connection và thời gian database thực thi.
4. **Dung lượng kết quả:** số hàng trả về, kích thước dữ liệu được materialize và kích thước payload ứng dụng thực sự gửi ra ngoài.

Bốn nhóm số liệu bổ sung cho nhau. Chỉ đo thời gian tổng không chỉ ra bottleneck nằm ở SQL, pool, mapping hay serialization. Chỉ đếm SQL cũng không cho biết một query trả về mười hàng hay một triệu hàng.

## 1. Xác định ranh giới cần đo

Trước khi thêm instrumentation, hãy chọn một use case cụ thể, ví dụ tải trang chi tiết đơn hàng hoặc tìm danh sách khách hàng.

Một luồng điển hình:

```text
HTTP request
    |
    v
Application service
    |
    +--> Spring Data JDBC repository
    |       |
    |       +--> DataSource / connection pool
    |                 |
    |                 +--> JDBC statements
    |                           |
    |                           v
    |                        Database
    |
    +--> Mapping aggregate / DTO
    |
    +--> Serialize response
    |
    v
HTTP response
```

Mỗi lớp có một loại thời gian khác nhau:

| Ranh giới | Số liệu cần đo |
| --- | --- |
| HTTP/service | Tổng thời gian use case, success/error, số lần gọi. |
| Repository | Số lần gọi repository và thời gian mỗi operation. |
| DataSource | Số lần mượn/trả connection, thời gian chờ pool. |
| JDBC statement | Số statement, loại SQL, thời gian thực thi, batch size. |
| ResultSet/materialization | Số hàng đọc, thời gian mapping và dữ liệu giữ trong bộ nhớ. |
| Response | Số item và số byte payload sau serialization. |

Không nên gộp tất cả thành một metric tên "database time". Thời gian một repository call có thể bao gồm chờ connection, bind parameter, gửi SQL, chờ database, đọc ResultSet và chuyển đổi dữ liệu thành object.

## 2. Số câu SQL không bằng số lần gọi repository

Một lời gọi repository không nhất thiết tương ứng với một statement.

Ví dụ:

```java
PurchaseOrder order = orders.findById(orderId).orElseThrow();
```

Tùy mapping aggregate và cách load các thành phần được sở hữu, Spring Data JDBC có thể cần nhiều statement để đọc root và các collection/child rows. Tương tự, lưu một aggregate có nhiều thành phần có thể phát sinh nhiều INSERT/UPDATE/DELETE.

Các yếu tố làm thay đổi số statement:

- Aggregate có bao nhiêu collection được ánh xạ.
- Truy vấn cần tải bao nhiêu aggregate.
- Một query được thực thi một lần hay lặp trong vòng lặp.
- Repository method có thực hiện count query hoặc query bổ sung hay không.
- Có dùng custom query, auditing, callback hoặc thao tác phụ khác không.
- Driver/database thực thi batch như thế nào.

Do đó, muốn biết số SQL thực tế, hãy đo ở ranh giới JDBC/DataSource thay vì suy ra từ số dòng code hoặc số repository method.

### 2.1. Phát hiện N+1 query

N+1 thường xuất hiện khi ứng dụng tải một danh sách N aggregate rồi chạy thêm một query cho từng aggregate.

Ví dụ:

```java
List<Customer> customers = customerRepository.findAll();

for (Customer customer : customers) {
    List<PurchaseOrder> orders =
        orderRepository.findByCustomerId(customer.id());
    // Tạo nội dung hiển thị.
}
```

Nếu danh sách có 50 khách hàng, luồng này có thể tạo một query tải khách hàng và thêm 50 query tải đơn hàng. Tổng số query tăng theo N.

Một cách đo hữu ích là chạy cùng use case với dataset có 1, 10 và 50 bản ghi rồi so sánh số statement. Nếu số SQL tăng gần tuyến tính theo số aggregate, hãy xem xét N+1 hoặc một truy vấn lặp trong application code.

Không phải mọi số query tăng theo N đều là lỗi. Có trường hợp nghiệp vụ thực sự cần thao tác riêng cho từng aggregate. Tuy nhiên, đo được xu hướng giúp xác định phần nào cần tối ưu.

## 3. Đo SQL bằng DataSource instrumentation

Muốn đếm statement độc lập với repository, có thể instrument DataSource. Một proxy ở lớp JDBC quan sát các thao tác tạo PreparedStatement, execute, batch và thời gian thực thi.

Các lựa chọn phổ biến:

| Công cụ | Mục đích |
| --- | --- |
| datasource-proxy | Bọc DataSource, lắng nghe query execution, đếm và đo thời gian statement. |
| P6Spy | Ghi log SQL và thời gian để chẩn đoán câu lệnh thực tế. |
| Micrometer | Ghi metrics/timer và xuất dữ liệu tới hệ thống quan sát. |
| JDBC/database telemetry | Bổ sung số liệu từ driver, pool và database engine. |

Dùng proxy để đo và dùng SQL logging để debug là hai mục đích khác nhau. Log đầy đủ từng statement rất hữu ích khi điều tra cục bộ, nhưng có thể tạo lượng log lớn và lộ dữ liệu nhạy cảm nếu bật trên production.

### 3.1. Minh họa datasource-proxy

Thư viện datasource-proxy cung cấp `QueryExecutionListener` để nhận thông tin trước và sau khi statement chạy.

```java
public class SqlMetricsListener implements QueryExecutionListener {

    private final MeterRegistry registry;

    public SqlMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeQuery(
            ExecutionInfo executionInfo,
            List<QueryInfo> queryInfoList) {
        // Có thể ghi nhận thời điểm bắt đầu nếu cần.
    }

    @Override
    public void afterQuery(
            ExecutionInfo executionInfo,
            List<QueryInfo> queryInfoList) {

        Timer.builder("app.jdbc.query")
            .tag("success",
                Boolean.toString(executionInfo.isSuccess()))
            .register(registry)
            .record(
                executionInfo.getElapsedTime(),
                TimeUnit.MILLISECONDS
            );

        for (QueryInfo queryInfo : queryInfoList) {
            // Phân loại statement và tăng counter tương ứng.
            // Không đưa raw parameter hoặc SQL đầy đủ vào metric tag.
        }
    }
}
```

Đây là phần listener minh họa cách ghi Timer; cần thêm dependency datasource-proxy và Micrometer phù hợp với ứng dụng. Khi tạo proxy, bọc DataSource thực tế và bảo đảm Spring Data JDBC cùng các JDBC client sử dụng wrapper đó.

Ví dụ khởi tạo wrapper:

```java
DataSource instrumentedDataSource =
    ProxyDataSourceBuilder
        .create(actualDataSource)
        .name("application")
        .listener(sqlMetricsListener)
        .build();
```

Trong Spring Boot, hãy cấu hình wrapper như DataSource mà repository sử dụng, giữ pool thật ở bên trong. Không tạo một Hikari pool thứ hai chỉ để đo SQL. Nếu ứng dụng đã có cấu hình DataSource tùy chỉnh, hãy tích hợp proxy vào cấu hình đó và kiểm tra Actuator/metrics vẫn quan sát đúng pool bên dưới.

### 3.2. Đếm theo loại statement

Nên có counter riêng cho các nhóm:

- SELECT.
- INSERT.
- UPDATE.
- DELETE.
- Batch execution.
- Statement lỗi.

Phân loại SQL bằng parser hoặc metadata của instrumentation nếu có. Regex đơn giản trên chuỗi SQL có thể phân loại sai khi câu lệnh bắt đầu bằng comment, CTE hoặc database-specific syntax.

Một metric có thể biểu diễn:

```text
app.jdbc.statements{operation="SELECT"}  = 120
app.jdbc.statements{operation="INSERT"}  = 8
app.jdbc.statements{operation="UPDATE"}  = 14
app.jdbc.statements{operation="DELETE"}  = 2
app.jdbc.statement.errors                = 1
```

Các con số trên chỉ là ví dụ. Hãy đo trong một khoảng thời gian hoặc một request scope cụ thể nếu muốn biết chi phí của từng use case.

### 3.3. Batch và số câu SQL

Một batch JDBC có thể chứa nhiều parameter set cho cùng statement. Vì vậy cần phân biệt:

- Số lần execute statement/batch.
- Số parameter set trong batch.
- Số hàng database thực sự tác động.

Ví dụ một batch INSERT gồm 100 parameter sets có thể là một lần gọi batch execution nhưng tạo 100 row. Không nên dùng một counter duy nhất rồi gọi chung là “số câu SQL” mà không định nghĩa cách đếm.

## 4. Đo thời gian: query, connection và use case

Có ít nhất ba loại thời gian cần phân biệt:

1. **Use case duration:** từ lúc service bắt đầu tới khi hoàn tất.
2. **Connection acquisition time:** thời gian chờ pool cấp connection.
3. **Statement execution time:** thời gian từ lúc JDBC execute tới khi driver trả quyền điều khiển.

Ngoài ra, việc đọc hết ResultSet và materialize aggregate có thể tiếp tục sau thời điểm execute trả về, tùy driver và cách framework tiêu thụ dữ liệu. Vì vậy statement elapsed time không nhất thiết bằng toàn bộ thời gian repository call.

### 4.1. Đo thời gian use case bằng Micrometer

Ví dụ dùng Timer:

```java
@Service
public class CustomerQueryService {

    private final CustomerRepository customers;
    private final Timer searchTimer;

    public CustomerQueryService(
            CustomerRepository customers,
            MeterRegistry registry) {
        this.customers = customers;
        this.searchTimer = registry.timer(
            "app.customer.search.duration"
        );
    }

    public List<Customer> findActiveCustomers() {
        return searchTimer.record(
            () -> customers.findByActiveTrue()
        );
    }
}
```

Timer có thể cung cấp count, total time và thống kê phân phối tùy cấu hình registry. Trong ứng dụng thực tế, nên instrument ở service/use case boundary để bao gồm toàn bộ thao tác persistence và mapping thuộc use case.

Nếu dùng annotation như `@Timed`, cần cấu hình Micrometer/AOP tương ứng. Đừng giả định chỉ thêm annotation là mọi method đều tự động được đo trong mọi phiên bản Spring Boot.

### 4.2. Đo thời gian statement

Proxy DataSource có thể ghi elapsed time của mỗi query. Khi xem số liệu, hãy phân biệt:

- Thời gian một statement.
- Tổng thời gian cộng dồn của tất cả statement trong request.
- Wall-clock time của request.

Nếu một request thực hiện 20 query song song, tổng elapsed time của query có thể lớn hơn wall-clock time. Trong Spring Data JDBC imperative thông thường, nhiều thao tác thường chạy tuần tự trong cùng thread, nhưng không nên giả định phép cộng thời gian query luôn bằng thời gian service.

### 4.3. Percentile quan trọng hơn chỉ nhìn average

Average có thể che giấu một nhóm request rất chậm. Theo dõi p50, p95 và p99 giúp hiểu trải nghiệm tail latency:

| Chỉ số | Cách diễn giải |
| --- | --- |
| p50 | Một request điển hình ở giữa phân phối. |
| p95 | 95% request hoàn tất trong hoặc dưới mức này. |
| p99 | Nhóm request chậm nhất, hữu ích để phát hiện tail latency. |
| max | Giá trị lớn nhất quan sát được; nhạy với outlier. |

Hãy kết hợp percentile với throughput và error rate. p99 tăng khi tải cao có thể liên quan tới connection pool, lock contention, query plan hoặc database saturation.
## 5. Đo lượt mượn connection và connection vật lý

Từ “số connection” có thể chỉ những sự kiện khác nhau. Cần định nghĩa rõ trước khi tạo metric.

| Số liệu | Ý nghĩa |
| --- | --- |
| Connection acquisition | Số lần ứng dụng gọi lấy connection từ DataSource/pool. |
| Connection release | Số lần ứng dụng trả connection về pool hoặc đóng logical handle. |
| Physical connection creation | Số lần pool mở kết nối vật lý mới tới database. |
| Active connections | Số connection hiện đang được ứng dụng mượn khỏi pool. |
| Idle connections | Số connection đang rảnh trong pool. |
| Pending borrowers | Số luồng đang chờ pool cấp connection. |
| Acquisition duration | Thời gian từ lúc yêu cầu connection tới lúc nhận được connection. |

Một transaction có thể mượn một connection và dùng nó cho nhiều statement. Do đó 30 câu SQL trong một transaction không có nghĩa ứng dụng đã mở 30 connection.

Ngược lại, nếu không có transaction bao quanh nhiều thao tác, connection có thể được mượn/trả theo từng operation tùy cách repository và transaction infrastructure thực thi.

### 5.1. Connection pool HikariCP

Spring Boot thường dùng HikariCP làm connection pool khi có dependency phù hợp. Pool quản lý số connection vật lý, tái sử dụng chúng giữa các request và cung cấp metrics.

Các số liệu Hikari thường gặp:

- `hikaricp.connections.active`: connection đang được mượn.
- `hikaricp.connections.idle`: connection đang rảnh trong pool.
- `hikaricp.connections.pending`: luồng đang chờ connection.
- `hikaricp.connections.max`: giới hạn connection.
- `hikaricp.connections.min`: mức tối thiểu cấu hình.
- `hikaricp.connections.acquire`: thời gian lấy connection.
- `hikaricp.connections.usage`: thời gian connection được sử dụng.
- `hikaricp.connections.creation`: thời gian tạo connection vật lý.

Tên metric cụ thể có thể phụ thuộc phiên bản HikariCP, Micrometer và cấu hình registry. Dùng Spring Boot Actuator/Micrometer để xuất pool metrics nếu ứng dụng đã bật instrumentation phù hợp.

Một cấu hình pool minh họa:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
```

Các giá trị trên chỉ minh họa cú pháp, không phải kích thước pool khuyến nghị cho mọi hệ thống. Chọn pool size dựa trên khả năng chịu tải của database, số instance ứng dụng, concurrency và thời gian giữ connection.

### 5.2. Diễn giải pool metrics

Một số tình huống thường gặp:

| Quan sát | Khả năng cần điều tra |
| --- | --- |
| Active luôn gần max, pending tăng | Pool có thể thiếu capacity hoặc transaction giữ connection quá lâu. |
| Active thấp, query chậm | Bottleneck có thể nằm ở database, lock, query plan hoặc result processing. |
| Acquire duration tăng | Request phải chờ pool cấp connection. |
| Usage duration tăng | Connection bị giữ lâu trong transaction hoặc operation. |
| Physical creation tăng liên tục | Connection bị đóng/mất thường xuyên, pool churn hoặc database/network không ổn định. |
| Idle luôn cao, active thấp | Pool có thể lớn hơn nhu cầu, nhưng cần xem giờ cao điểm trước khi giảm. |

Không tăng `maximum-pool-size` chỉ vì thấy pending. Nhiều connection hơn có thể làm database chịu concurrency cao hơn, tăng lock contention và làm query chậm thêm. Trước tiên xác định connection đang bị giữ ở đâu và database còn capacity hay không.

### 5.3. Đếm acquisition không đồng nghĩa đếm kết nối mới

Nếu cần đếm số lượt mượn connection, instrument `DataSource.getConnection()` và logical close/return. Nếu cần đếm số kết nối TCP/JDBC vật lý mới, xem metrics của pool như creation/total hoặc telemetry của database.

Hai chỉ số này có ý nghĩa khác nhau:

```text
Một pool có 10 physical connections
        |
        +-- Request A mượn connection #3
        |       +-- SELECT
        |       +-- UPDATE
        |       +-- INSERT
        |       +-- trả connection #3
        |
        +-- Request B sau đó mượn lại connection #3
                +-- SELECT
                +-- trả connection #3

Physical connection tạo: có thể chỉ 1
Connection acquisition: 2
SQL statement: 4
```

Đây là lý do không thể dùng số lần mở connection để suy ra số statement hoặc số request.

## 6. Đo số hàng và dung lượng kết quả

Một SELECT có thể chỉ mất vài millisecond ở database nhưng trả về lượng dữ liệu rất lớn. Khi đó ứng dụng tốn thời gian đọc dữ liệu, materialize object, giữ heap và serialize response.

Cần phân biệt ba đại lượng:

1. **Rows returned:** số hàng ResultSet hoặc số phần tử repository trả về.
2. **Materialized object size:** bộ nhớ heap mà entity/DTO và collection chiếm trong JVM.
3. **Payload size:** số byte response thực tế sau serialization/compression.

Chúng không bằng nhau. Một row có nhiều cột VARCHAR lớn có thể nặng hơn nhiều row chỉ chứa ID và status.

### 6.1. Đếm số phần tử ở application boundary

Với repository trả về List, có thể ghi nhận size sau khi tải:

```java
List<Customer> result = customers.findByActiveTrue();

registry.counter(
    "app.customer.search.rows",
    "result",
    result.isEmpty() ? "empty" : "non_empty"
).increment(result.size());
```

Metric trên đếm số object trả về ở application layer. Nó không đo chính xác số byte mà JDBC driver nhận qua network hoặc dung lượng heap thực tế.

Với Page/Slice, có thể ghi nhận `getNumberOfElements()`. Nếu cần tổng số row matching, `Page.getTotalElements()` là một đại lượng khác và có thể khiến framework chạy thêm count query.

### 6.2. Đếm row trong ResultSet

Muốn đếm số row JDBC đọc, có thể dùng proxy/listener hoặc wrapper quanh ResultSet để tăng counter mỗi lần `next()` trả true. Cần chú ý:

- Một ResultSet có thể được đọc từng phần.
- Một số API dùng streaming/cursor và không materialize toàn bộ cùng lúc.
- ResultSet có thể được tiêu thụ bởi framework trước khi repository trả kết quả.
- Đếm row không cho biết chính xác bytes truyền trên network.

Nếu instrumentation chỉ quan sát thời gian execute statement mà không bọc ResultSet, đừng gắn nhãn số đó là “rows read” nếu công cụ không thực sự cung cấp row count.

### 6.3. Ước lượng dung lượng dữ liệu

Có thể ước lượng ở tầng ứng dụng bằng kích thước trường hoặc số byte serialized:

```java
byte[] payload = objectMapper.writeValueAsBytes(response);

int payloadBytes = payload.length;
```

Đây là kích thước JSON payload trước khi server gửi đi hoặc nén, tùy vị trí đo. Nó hữu ích cho API response size nhưng không đại diện chính xác kích thước ResultSet trên wire.

Nếu cần đo bytes database truyền về, dùng telemetry/monitoring của database, driver hoặc network layer phù hợp. Nếu cần ước lượng heap, dùng profiler/JFR hoặc công cụ phân tích allocation; không lấy độ dài JSON làm đại diện cho object graph trong JVM.

### 6.4. Projection giảm dữ liệu đọc

Nếu màn hình chỉ cần ID, tên và trạng thái, không nên tải toàn bộ aggregate cùng các collection lớn chỉ để bỏ đi phần lớn dữ liệu sau đó.

Có thể dùng projection/DTO query phù hợp:

```java
public record CustomerListItem(
    Long id,
    String name,
    boolean active
) {}
```

Với query đọc phức tạp, custom query hoặc MyBatis có thể trả đúng các cột cần thiết. Với aggregate cần thay đổi domain state, tiếp tục tải aggregate root theo repository. Chọn projection theo mục tiêu đọc, không biến DTO thành đường ghi aggregate.

### 6.5. Pagination và giới hạn kết quả

Tránh trả toàn bộ bảng khi giao diện chỉ cần một trang:

```java
Page<Customer> findByActiveTrue(Pageable pageable);
```

Ví dụ:

```java
Pageable pageRequest = PageRequest.of(
    0,
    50,
    Sort.by("id").ascending()
);

Page<Customer> page =
    customerRepository.findByActiveTrue(pageRequest);
```

Kích thước trang cần cân nhắc cả số row và độ rộng dữ liệu. Trang 50 row có thể vẫn lớn nếu mỗi row chứa cột text/JSON dài.

Pagination cũng có chi phí: Page thường cần tổng số row, có thể phát sinh count query. Nếu UI chỉ cần biết còn trang tiếp theo, `Slice` có thể phù hợp hơn khi repository method hỗ trợ.

## 7. Kết hợp bốn nhóm số liệu để tìm bottleneck

Không nên đọc từng metric riêng lẻ. Hãy kết hợp chúng trong cùng một khoảng thời gian hoặc cùng một request trace.

| SQL count | Connection wait | Query time | Result size | Hướng điều tra |
| --- | --- | --- | --- | --- |
| Cao | Thấp | Mỗi query nhanh | Nhỏ | Có thể N+1 hoặc nhiều round-trip. |
| Thấp | Thấp | Cao | Nhỏ | Query plan, lock, index hoặc database load. |
| Thấp | Cao | Bình thường | Nhỏ | Pool saturation hoặc connection bị giữ lâu ở request khác. |
| Thấp | Thấp | Trung bình | Rất lớn | Result transfer, mapping, heap và serialization. |
| Cao | Cao | Cao | Lớn | Nhiều vấn đề cùng lúc; giảm query/result và xem lại transaction/pool. |
| Thấp | Thấp | Thấp | Nhỏ | Có thể chưa có bottleneck ở đường database này. |

Ví dụ:

- Service chạy 80 ms.
- Có 42 SELECT.
- Tổng thời gian statement cộng dồn 25 ms.
- Connection acquisition p95 là 2 ms.
- Tổng kết quả 400 row.

Khả năng cần xem xét là số round-trip/query lặp, vì thời gian từng query và chờ pool không quá cao nhưng statement count lớn. Hãy tìm vòng lặp repository call hoặc N+1.

Một ví dụ khác:

- Service chạy 900 ms.
- Có 2 SELECT.
- Tổng thời gian statement 120 ms.
- ResultSet có 100.000 row.
- Serialization mất 500 ms.

Trong trường hợp này, giảm số SQL không phải ưu tiên đầu tiên. Cần giới hạn kết quả, dùng projection, pagination hoặc xử lý theo batch/streaming phù hợp.

## 8. Dùng Micrometer và Actuator

Micrometer cung cấp Counter, Timer, Gauge và DistributionSummary để ghi nhận số liệu có thể xuất sang Prometheus, OTLP hoặc registry khác.

Một bộ metric ở mức ứng dụng có thể gồm:

| Metric | Loại | Ý nghĩa |
| --- | --- | --- |
| `app.jdbc.statements` | Counter | Số statement theo operation. |
| `app.jdbc.statement.duration` | Timer | Thời gian thực thi statement. |
| `app.jdbc.connection.acquire` | Timer | Thời gian lấy connection. |
| `app.repository.calls` | Counter | Số lần gọi repository theo use case. |
| `app.repository.duration` | Timer | Thời gian repository operation. |
| `app.repository.result.rows` | DistributionSummary/Counter | Phân phối số row trả về. |
| `app.response.bytes` | DistributionSummary | Kích thước payload response. |

Hãy bật Spring Boot Actuator và registry cần dùng. Ví dụ dependency thường gặp là Actuator và Micrometer Prometheus registry; cách cấu hình endpoint và export phụ thuộc phiên bản Spring Boot.

Metric tag nên có cardinality thấp:

- operation: SELECT/INSERT/UPDATE/DELETE.
- repository: tên nhóm repository hoặc use case ổn định.
- outcome: success/error.
- database: tên datasource cố định.

Không dùng các giá trị sau làm tag:

- SQL đầy đủ có literal hoặc parameter.
- ID khách hàng/đơn hàng.
- Email, username hoặc dữ liệu cá nhân.
- Request URL có query string tùy ý.
- Giá trị search keyword.

Các tag có cardinality cao làm tăng bộ nhớ và chi phí của metrics backend. Raw SQL và parameter nhạy cảm nên được xử lý trong log/tracing có kiểm soát, không đưa vào label metric.

## 9. Logging SQL để điều tra

SQL logging hữu ích khi cần xem câu lệnh thực tế, parameter binding hoặc thứ tự query. Có thể dùng datasource-proxy, P6Spy hoặc logging category phù hợp với JDBC layer.

Khi bật log:

- Chỉ bật mức chi tiết trong thời gian cần điều tra.
- Tránh ghi mật khẩu, token, email, địa chỉ hoặc dữ liệu nhạy cảm.
- Không bật log toàn bộ parameter production nếu chưa có policy bảo vệ.
- Dùng correlation/trace ID để nối log với request.
- Tắt hoặc giảm log sau khi điều tra xong.

Log không thay thế metrics. Metrics cho biết xu hướng theo thời gian; log giúp điều tra một statement cụ thể.

## 10. Kiểm thử số SQL và connection trong integration test

Unit test service thường mock repository nên không đo được số statement thực tế. Muốn kiểm tra query count, cần chạy qua Spring Data JDBC và DataSource được instrument.

### 10.1. Test số statement có giới hạn

Một test có thể reset counter trước operation rồi xác nhận số SELECT không vượt quá ngưỡng:

```java
@Test
void loadsCustomerListWithoutUnboundedQueries() {
    sqlMetrics.reset();

    customerService.loadCustomerSummaries();

    assertThat(sqlMetrics.selectCount())
        .isLessThanOrEqualTo(3);
}
```

`sqlMetrics` đại diện cho collector được tích hợp với datasource proxy trong test. Ngưỡng 3 chỉ là ví dụ; xác định từ hành vi mong đợi và schema thực tế của dự án.

Không nên assert số query chính xác nếu số đó phụ thuộc implementation detail có thể thay đổi giữa phiên bản Spring Data. Một upper bound hoặc kiểm tra tăng trưởng theo dataset thường bền hơn.

### 10.2. Test xu hướng theo kích thước dataset

Một cách hữu ích để phát hiện N+1:

1. Seed 1 customer có đơn hàng.
2. Đo statement count khi tải danh sách.
3. Seed 10 customer.
4. Đo lại cùng use case.
5. Seed 50 customer.
6. So sánh số statement.

Nếu query count tăng từ 2 lên 11 rồi 51, nhiều khả năng có một query bổ sung cho từng customer. Nếu số query gần như cố định nhưng số row tăng, ứng dụng có thể đang dùng query tập hợp hiệu quả hơn.

Test cần reset metrics giữa các lần chạy và loại trừ SQL seed/cleanup khỏi vùng đo.

### 10.3. Test connection acquisition

Để kiểm tra connection pool, có thể quan sát pool metrics trước và sau operation hoặc instrument DataSource để đếm checkout/return.

Đừng assert physical connection creation bằng 1 trong test thông thường vì pool có thể khởi tạo trước, tái sử dụng hoặc tạo connection bất đồng bộ. Thay vào đó, kiểm tra:

- Không có connection acquisition timeout.
- Active connection trở về mức nền sau operation.
- Pending không tăng kéo dài.
- Acquisition time nằm trong ngưỡng của môi trường test.
- Connection được trả về ngay cả khi transaction rollback hoặc exception.

### 10.4. Test kết quả lớn

Seed dữ liệu có kích thước khác nhau và kiểm tra:

- Số item trả về.
- Có giới hạn trang hay không.
- Response payload bytes.
- Thời gian materialization/serialization.
- Bộ nhớ allocation nếu đây là đường dữ liệu lớn.

Với query có pagination, xác nhận page size được áp dụng ở database. Không chỉ gọi `subList` trên một List đã tải toàn bộ dữ liệu.

## 11. Dùng EXPLAIN và database metrics đúng chỗ

Application metrics cho biết ứng dụng phát bao nhiêu SQL, mất bao lâu và nhận bao nhiêu kết quả. Nó không giải thích đầy đủ database thực thi query bằng plan nào.

Khi statement chậm, dùng công cụ database:

- PostgreSQL: `EXPLAIN` và `EXPLAIN (ANALYZE, BUFFERS)`.
- MySQL: `EXPLAIN` hoặc `EXPLAIN ANALYZE` theo phiên bản.
- SQL Server: actual execution plan và Query Store.
- Oracle: execution plan và SQL monitoring phù hợp.

Kiểm tra:

- Có dùng index dự kiến không.
- Có full table scan trên bảng lớn không.
- Cardinality estimate có sai lệch không.
- Join order và join method có hợp lý không.
- Có sort/hash spill ra disk không.
- Query có đọc quá nhiều row rồi mới lọc không.
- Lock wait hoặc I/O có chi phối thời gian không.

Chỉ chạy dạng ANALYZE có thực thi query khi hiểu tác động của nó; một số câu lệnh có side effect hoặc tải lớn. Dùng môi trường/staging và quyền truy cập phù hợp.

## 12. Quy trình đo một use case Spring Data JDBC

Có thể dùng quy trình sau khi điều tra một endpoint hoặc service chậm:

1. Chọn use case và tạo dataset đại diện.
2. Ghi nhận tổng thời gian service, số lần gọi repository và outcome.
3. Instrument DataSource để đếm statement theo loại và đo elapsed time.
4. Ghi nhận connection acquisition/return và pool metrics.
5. Đếm số row ở application boundary; đo payload bytes nếu API trả dữ liệu.
6. Chạy cùng use case với nhiều kích thước dataset để tìm query count tăng theo N.
7. Dùng trace/log để xác định câu SQL gây tốn thời gian hoặc lặp lại.
8. Dùng EXPLAIN/database telemetry để hiểu query plan.
9. Thay đổi query, projection, pagination, index hoặc transaction scope theo nguyên nhân đo được.
10. Chạy lại cùng workload và so sánh trước/sau trên cùng database, cấu hình và dữ liệu.
11. Theo dõi p95/p99, error rate và pool saturation sau khi triển khai.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Đếm repository call rồi kết luận số SQL | Một repository operation có thể phát nhiều statement. | Đo ở DataSource/JDBC boundary. |
| Đếm số statement batch thành số row | Một batch execution có nhiều parameter sets. | Theo dõi execution, batch size và affected rows riêng. |
| Gọi connection acquisition là connection mới | Pool tái sử dụng physical connection. | Tách checkout/return với physical creation. |
| Query time bằng service time theo giả định | Mapping, transaction, connection wait và serialization cũng tốn thời gian. | Đo từng boundary. |
| Average thấp nhưng user vẫn gặp request chậm | Tail latency bị average che khuất. | Theo dõi p95/p99 và error rate. |
| Một SELECT nhanh nhưng endpoint chậm | ResultSet lớn, mapping hoặc serialization nặng. | Đo rows, payload và allocation. |
| Pool pending cao nên tăng max pool ngay | Database có thể đã quá tải hoặc connection bị giữ lâu. | Tìm nguyên nhân giữ connection và database capacity trước. |
| SQL log production làm lộ dữ liệu | Parameter/literal chứa thông tin nhạy cảm. | Redact, giới hạn thời gian và quyền truy cập log. |
| Metrics tăng cardinality nhanh | Tag bằng SQL, ID hoặc request parameter. | Dùng tag ổn định, ít giá trị. |
| Test query count quá cứng | Implementation/framework thay đổi số statement phụ trợ. | Assert upper bound hoặc xu hướng scaling. |
| H2 không phản ánh production | Khác dialect, plan, driver và kiểu dữ liệu. | Đo integration trên database tương ứng production. |

## 14. Checklist số liệu cần có

Với một use case quan trọng, dashboard hoặc test nên cho biết:

| Nhóm | Số liệu tối thiểu |
| --- | --- |
| SQL | Tổng statement, SELECT/INSERT/UPDATE/DELETE, batch count, error count. |
| Query timing | p50/p95/p99, tổng elapsed time, query chậm nhất qua trace/log. |
| Connection | Active, idle, pending, max, acquire time, usage time, timeout count. |
| Result | Rows returned, page size, payload bytes, allocation nếu cần. |
| Use case | Request count, total duration, success/error, trace ID trong log. |

Không phải mọi metric đều cần xuất công khai. Chọn mức quan sát theo chi phí và nhu cầu vận hành; metrics có cardinality thấp nên luôn sẵn, còn SQL detail/parameter tracing chỉ bật khi điều tra có kiểm soát.

> **Đo hiệu năng persistence cần tách số statement, lượt mượn connection, thời gian từng lớp và kích thước kết quả.** Một transaction có thể dùng một connection cho nhiều SQL; một SELECT ít câu lệnh vẫn có thể trả quá nhiều dữ liệu. Đo ở DataSource, connection pool và application boundary, sau đó kết hợp số liệu với execution plan để xác định bottleneck thực sự.

### Tài liệu tham khảo

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): tích hợp Micrometer và các metric do Spring Boot cung cấp.
- [Spring Boot — DataSource Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.supported.jdbc): metric liên quan datasource và connection pool.
- [HikariCP — Metrics](https://github.com/brettwooldridge/HikariCP): pool metrics, connection acquisition và usage.
- [datasource-proxy](https://github.com/jdbc-observations/datasource-proxy): proxy DataSource, query execution listener và query counting.
- [P6Spy](https://p6spy.readthedocs.io/): quan sát và logging hoạt động JDBC.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo thời gian và phân phối latency.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): đọc execution plan và phân tích chi phí query.
- [Spring Data JDBC — Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repository, aggregate mapping và hành vi persistence của Spring Data JDBC.
