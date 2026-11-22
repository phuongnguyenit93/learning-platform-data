# Giám sát pool, thời gian giao dịch và truy vấn chậm trong JPA

Ứng dụng sử dụng **JPA/Hibernate** để truy cập cơ sở dữ liệu quan hệ thường bắt đầu gặp vấn đề hiệu năng khi lưu lượng tăng, dữ liệu lớn dần hoặc triển khai một đợt di trú. Một API chậm có thể do thiếu kết nối trong pool, do giao dịch giữ kết nối quá lâu, do câu SQL chạy chậm, hoặc do phải chờ khóa từ giao dịch khác. Các nguyên nhân này dễ tạo ra triệu chứng giống nhau nhưng cần cách xử lý khác nhau.

Ví dụ, nếu một request mất 3 giây để hoàn thành, việc tăng kích thước pool chưa chắc giúp ích: request có thể chỉ mất 10 ms để lấy connection nhưng tốn 2,8 giây chờ một câu SQL. Ngược lại, câu SQL chạy nhanh cũng chưa chắc bảo đảm API nhanh nếu thread phải chờ connection 2 giây trước khi thực thi.

Mục tiêu vận hành là đo được toàn bộ chuỗi **request → đợi connection → transaction → JDBC/SQL → database**, liên kết các phép đo bằng trace, nhận diện đúng nút thắt và kiểm chứng tác động của từng thay đổi, kể cả khi ứng dụng đang nâng phiên bản schema.

## 1. Phân biệt các loại thời gian

Một request có thể trải qua các giai đoạn sau:

```text
HTTP request
    |
    +-- Authentication / validation
    |
    +-- Bắt đầu logic nghiệp vụ
          |
          +-- Bắt đầu transaction (có thể chưa checkout connection)
          |     |
          |     +-- Đợi pool cấp connection
          |     |
          |     +-- Gửi SQL qua JDBC
          |     |     |
          |     |     +-- Network
          |     |     +-- DB parse/plan/execute
          |     |     +-- Chờ lock / I/O (nếu có)
          |     |
          |     +-- Xử lý kết quả / các SQL tiếp theo
          |     |
          |     +-- Flush, commit hoặc rollback
          |
          +-- Mapping response
    |
HTTP response
```

Các đại lượng nên đo riêng:

| Chỉ số | Bắt đầu → kết thúc | Có thể cao vì |
|---|---|---|
| **API latency** | Nhận request → hoàn tất response | Bất kỳ bước nào, kể cả ngoài database |
| **Connection acquisition time** | Yêu cầu kết nối → pool cấp connection | Pool cạn, nhiều request đồng thời, kết nối tạo mới chậm |
| **Connection usage/hold time** | Checkout → trả connection về pool | Transaction dài, nhiều SQL, xử lý ứng dụng khi đang giữ connection |
| **Transaction duration** | Bắt đầu → commit/rollback kết thúc | SQL, flush, lock, xử lý nghiệp vụ, lệnh gọi bên ngoài |
| **SQL elapsed time phía ứng dụng** | JDBC execute → nhận kết quả cần thiết | Network, database, lock, truyền kết quả |
| **SQL execution time phía database** | DB bắt đầu xử lý câu lệnh → hoàn tất | Plan kém, scan nhiều dữ liệu, I/O, CPU, lock |
| **Lock wait** | Yêu cầu lock → có lock hoặc hết timeout | Giao dịch khác đang giữ khóa |

Các khoảng thời gian **có thể chồng lấp**, không nên cộng tất cả như các số độc lập. Ví dụ SQL chạy trong khoảng giữ connection; transaction có thể bắt đầu trước khi connection thực sự được lấy, tùy cơ chế quản lý kết nối. Một trace theo mốc thời gian là cách đáng tin cậy để hiểu trình tự.

Nguyên tắc quan trọng: **độ trễ lấy connection, thời gian giữ connection và độ trễ truy vấn là ba phép đo khác nhau**.

## 2. Kiến trúc quan sát phù hợp

Trong ứng dụng Spring Boot + Spring Data JPA, có thể phối hợp bốn lớp:

1. **HikariCP** đo số connection đang dùng/rảnh/chờ và thời gian lấy/giữ connection.
2. **Micrometer + Spring Boot Actuator** công bố metric ứng dụng, transaction và request để hệ thống giám sát thu thập.
3. **Distributed tracing** (ví dụ OpenTelemetry qua Micrometer Tracing) nối một HTTP request với các span JDBC và những dịch vụ liên quan.
4. **Công cụ ở database** đo SQL nặng, lock, session đang mở, CPU/I/O và tác động của migration.

Không công cụ đơn lẻ nào nhìn được đầy đủ mọi phía. Metric cho biết xu hướng và bất thường; trace cho biết request cụ thể đi qua những bước nào; log có cấu trúc hỗ trợ đối chiếu; công cụ database chỉ ra hoạt động thực tế của SQL và transaction.

### 2.1. Các metric nên có trên dashboard

| Nhóm | Metric cần theo dõi | Cách đọc |
|---|---|---|
| Pool | Active, idle, pending, max | Active sát max và pending tăng kéo dài cho thấy tranh chấp connection |
| Pool | Connection acquire p50/p95/p99 | Thời gian lấy connection có tăng trước khi API chậm không? |
| Pool | Connection usage p95/p99 | Một request giữ connection lâu hơn bình thường? |
| Pool | Timeout khi chờ connection | Người gọi đã chờ quá giới hạn `connectionTimeout` |
| Transaction | Số lần/giây, duration p95/p99, tỷ lệ rollback | Giao dịch có kéo dài hoặc thất bại khi tải tăng? |
| SQL | Số lần thực thi, duration, rows returned/affected | Chậm do từng SQL nặng hay do quá nhiều SQL nhỏ? |
| DB | Active sessions, lock waits, deadlocks, CPU, I/O | Nút thắt có nằm ở tài nguyên database? |
| API | Throughput, error rate, latency p95/p99 | Hệ quả thực sự mà người dùng nhận thấy |

Theo dõi **p95/p99**, không chỉ trung bình: một phần nhỏ giao dịch rất chậm vẫn có thể giữ pool đủ lâu để làm nhiều request khác bị xếp hàng.

Không gắn `userId`, `orderId`, câu SQL nguyên văn có giá trị bind hay ID request vào **metric labels**. Những thuộc tính thay đổi liên tục sẽ tạo cardinality rất lớn. Đưa thông tin chi tiết vào trace/log có kiểm soát; metric nên dùng tag ít biến động như `operation=order.checkout`, `pool=primary` hoặc `db.system=postgresql`.

## 3. Theo dõi HikariCP connection pool

HikariCP là connection pool thường được Spring Boot sử dụng cho JDBC/JPA. Pool tái sử dụng kết nối vật lý nhằm tránh chi phí mở connection trên từng request, đồng thời giới hạn số phiên làm việc đồng thời với database.

### 3.1. Cấu hình minh họa

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/app
    username: app_user
    # Lấy mật khẩu từ secret manager/biến môi trường.
    hikari:
      pool-name: primary
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1740000
      leak-detection-threshold: 60000

  jpa:
    open-in-view: false

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Các giá trị trên chỉ là **ví dụ khởi đầu**, cần được đo và điều chỉnh theo tải, timeout của database và hạ tầng mạng:

- `maximum-pool-size`: số connection tối đa của **một instance ứng dụng**, không phải toàn cluster.
- `minimum-idle`: số connection rảnh mà pool cố duy trì; cấu hình thấp hơn max cho phép pool co giãn, nhưng phải xét độ trễ khi tạo connection mới.
- `connection-timeout`: thời gian tối đa caller chờ lấy connection từ pool, tính bằng **mili giây**; không giới hạn thời gian SQL hay toàn bộ transaction.
- `validation-timeout`: thời gian chờ kiểm tra connection còn sử dụng được.
- `idle-timeout`: thời gian nghỉ trước khi connection dư có thể được thu hồi; chịu tác động của `minimum-idle`.
- `max-lifetime`: tuổi thọ tối đa của một connection trong pool. Khi hạ tầng đóng connection theo tuổi/idle, cấu hình vòng đời pool nên phù hợp và thường kết thúc sớm hơn giới hạn cứng liên quan.
- `leak-detection-threshold`: log cảnh báo khi một connection bị giữ quá thời gian này. **Đây không phải bằng chứng chắc chắn connection leak**: một transaction chạy lâu hợp lệ cũng có thể kích hoạt cảnh báo.
- `open-in-view: false`: tránh cho JPA persistence context sống xuyên suốt giai đoạn tạo HTTP response; buộc tầng nghiệp vụ xác định rõ điểm tải quan hệ thay vì phát sinh lazy query muộn ngoài transaction.

Để bật `/actuator/prometheus` cần dependency Actuator và Prometheus registry tương thích. Các endpoint metric phải được bảo vệ ở mạng quản trị/collector, không phơi bày tự do ra Internet.

### 3.2. Đọc metric thay vì suy đoán

Khi được instrument, HikariCP thường cung cấp các meter Micrometer có tên:

```text
hikaricp.connections.active
hikaricp.connections.idle
hikaricp.connections.pending
hikaricp.connections.max
hikaricp.connections.acquire
hikaricp.connections.usage
hikaricp.connections.timeout
```

Tên và định dạng tại Prometheus có thể được chuyển đổi theo registry/version; có thể xem danh sách meter thực tế qua Actuator:

```bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.pending
curl http://localhost:8080/actuator/metrics/hikaricp.connections.acquire
```

Khi bảo mật Actuator, lệnh trên cần chạy từ mạng tin cậy với thông tin xác thực hợp lệ. Nếu có nhiều data source, hãy phân tách theo tên pool; nếu nhiều pod, giữ nhãn instance khi cần phân tích riêng trước khi tổng hợp.

Diễn giải một số tổ hợp triệu chứng:

| Active | Pending | Acquire latency | Khả năng xảy ra |
|---|---|---|---|
| Thấp so với max | Gần 0 | Thấp | Pool chưa bị bão hòa; hãy xem SQL, ứng dụng hoặc dịch vụ khác |
| Sát max | Tăng liên tục | Tăng | Có hàng đợi connection; xem usage time và throughput |
| Sát max | Tăng | Tăng, timeout xuất hiện | Pool bão hòa; tìm transaction lâu, leak hoặc DB chậm |
| Thấp | Có đỉnh ngắn | Tăng ngắn hạn | Có thể do burst và tạo connection mới; so với lưu lượng |
| Cao nhưng ổn định | Gần 0 | Thấp | Không nhất thiết là lỗi; có thể là mức sử dụng bình thường |

Không dùng một ngưỡng kiểu “active 80% = tăng pool ngay” cho mọi hệ thống. Hãy đánh giá **tỷ lệ sử dụng + pending + acquire p95 + usage duration + DB load** trong cùng khoảng thời gian.

### 3.3. Tính dung lượng toàn cluster

Giới hạn connection của database được chia sẻ bởi tất cả ứng dụng, worker, tác vụ di trú, công cụ quản trị và phiên dự phòng:

```text
Tổng connection dự kiến
  = (số instance ứng dụng × maximumPoolSize mỗi instance)
    + connection của background workers
    + connection của migration/admin
    + connection của dịch vụ khác

Tổng dự kiến <= giới hạn connection hữu dụng của database
```

Ví dụ bốn instance, mỗi instance tối đa 12 connection, cộng 5 connection cho worker và 10 connection cho các thành phần khác thì tổng dự kiến là `4 × 12 + 5 + 10 = 63`. Nếu database có giới hạn danh nghĩa 100 connection, vẫn cần trừ phần dành riêng cho quản trị/replication và kiểm tra tải thật trước khi tăng pool.

Một gợi ý để ước lượng mức đồng thời trung bình theo định luật Little:

```text
Số connection đang được giữ trung bình
  ≈ tốc độ các thao tác cần DB (thao tác/giây)
    × thời gian giữ connection trung bình (giây)
```

Ví dụ 40 thao tác/giây, giữ connection 0,2 giây mỗi thao tác thì cần xấp xỉ 8 connection hoạt động **trung bình**. Kích thước pool thực tế còn phụ thuộc burst, phân phối p95/p99, số thao tác DB mỗi request, ngưỡng DB chịu được và lượng headroom. Không lấy công thức trung bình làm cấu hình cứng.

**Pool lớn hơn không đồng nghĩa throughput cao hơn.** Khi database đã bão hòa CPU, I/O hoặc lock, thêm connection thường chỉ tăng tranh chấp và làm đuôi latency xấu đi.

## 4. Đo thời gian transaction đúng ranh giới

Một transaction JPA có thể bao gồm đọc entity, kiểm tra nghiệp vụ, thay đổi entity, gọi `flush()` và commit. Transaction chậm giữ khóa lâu hơn, có thể giữ connection lâu, làm tăng hàng đợi ở pool và khiến phiên bản dữ liệu trở nên cũ nhanh hơn.

### 4.1. Các nguyên nhân transaction quá dài

- Đặt một vòng lặp xử lý hàng nghìn bản ghi trong một transaction duy nhất.
- Gọi HTTP API, gửi email, upload file hoặc sleep khi transaction còn mở.
- Dùng fetch/lazy loading không kiểm soát khiến nhiều câu SQL phát sinh trong cùng transaction.
- Chờ lock của transaction khác trước khi update.
- Ghi một lượng lớn dữ liệu khiến flush và commit tốn thời gian.
- Tạo transaction lồng theo `Propagation.REQUIRES_NEW` trong khi transaction ngoài vẫn đang giữ connection; mỗi luồng có thể cần thêm connection.
- Để transaction ở trạng thái `idle in transaction`, đặc biệt khi luồng ứng dụng đợi thao tác khác.

Với Spring, `@Transactional` thường nằm ở **Service layer**, vì đây là nơi xác định một đơn vị nghiệp vụ cần tính nguyên tử:

```java
@Service
public class InvoiceService {
    private final InvoiceRepository invoices;

    public InvoiceService(InvoiceRepository invoices) {
        this.invoices = invoices;
    }

    @Transactional
    public void markPaid(Long id) {
        Invoice invoice = invoices.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Invoice not found"));

        invoice.markPaid();
        // Dirty checking sẽ cập nhật entity ở flush/commit.
    }
}
```

Ví dụ này biểu diễn ranh giới transaction, không quy định cách ánh xạ lỗi HTTP hay thanh toán thực tế. Việc gọi một phương thức `@Transactional` từ phương thức khác trên **cùng object** có thể bỏ qua proxy Spring, dẫn tới transaction không được mở như tưởng tượng. Cần kiểm tra đường gọi thực tế khi đo.

### 4.2. Gắn Timer cho transaction nghiệp vụ

Không phải mọi Spring Boot deployment đều có sẵn metric duration cho **từng phương thức transaction nghiệp vụ**. Một cách đo chủ động là dùng `TransactionTemplate` để bao trùm toàn bộ thực thi và commit:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ShipmentCommandService {
    private final ShipmentRepository shipments;
    private final TransactionTemplate transactionTemplate;
    private final MeterRegistry registry;

    public ShipmentCommandService(
            ShipmentRepository shipments,
            TransactionTemplate transactionTemplate,
            MeterRegistry registry) {
        this.shipments = shipments;
        this.transactionTemplate = transactionTemplate;
        this.registry = registry;
    }

    public void markShipped(Long id) {
        Timer.Sample sample = Timer.start(registry);
        String result = "success";

        try {
            transactionTemplate.executeWithoutResult(status -> {
                Shipment shipment = shipments.findById(id)
                    .orElseThrow(() -> new NoSuchElementException("Shipment not found"));

                shipment.markShipped();
                // executeWithoutResult hoàn tất khi transaction đã xử lý commit/rollback.
            });
        } catch (RuntimeException exception) {
            result = "failure";
            throw exception;
        } finally {
            sample.stop(Timer.builder("app.persistence.transaction.duration")
                .description("End-to-end duration of one business transaction")
                .tag("operation", "shipment.markShipped")
                .tag("result", result)
                .publishPercentileHistogram()
                .register(registry));
        }
    }
}
```

Đoạn code giả định `ShipmentRepository` và entity `Shipment` đã được định nghĩa trong ứng dụng. Với `TransactionTemplate` quản lý transaction ở phương thức này, phép đo bao gồm cả thời gian commit/rollback của transaction do template tạo. Nếu nó chỉ **tham gia transaction bên ngoài**, phép đo không bao gồm commit cuối cùng của transaction ngoài; cần đặt điểm đo tại ranh giới transaction thực sự. Không đồng thời bọc thêm một transaction bên ngoài mà không hiểu propagation.

Timer sử dụng tên operation cố định để tránh tag nổ cardinality. Khi cần chi tiết theo request, dùng trace ID trong log và span. Histogram phục vụ tính phân vị phía hệ thống quan sát, nhưng cần cân nhắc chi phí lưu trữ.

### 4.3. Transaction timeout và SQL timeout khác nhau

```java
@Transactional(timeout = 10)
public void recomputeAggregate() {
    // Khối nghiệp vụ cần thời gian giới hạn.
}
```

`timeout = 10` có đơn vị **giây**. Spring truyền cấu hình timeout qua transaction manager và các cơ chế mà JDBC/JPA hỗ trợ. Đây **không phải bộ đếm cưỡng chế dừng mọi dòng Java đúng sau 10 giây**; một lệnh I/O không hỗ trợ timeout hoặc một transaction tham gia transaction khác có thể có hành vi khác.

Trong PostgreSQL, database cũng có thể giới hạn thời gian xử lý một câu lệnh, chẳng hạn:

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';
-- Truy vấn hoặc cập nhật cần được giới hạn thời gian ở DB
COMMIT;
```

`SET LOCAL` áp dụng cho transaction hiện tại. Ngoài `statement_timeout` còn có các cơ chế riêng cho `lock_timeout` và xử lý session `idle in transaction`. Cấu hình cần được phối hợp với timeout HTTP, transaction, JDBC, pool và retry để tránh lệnh đã bị ngắt ở một tầng nhưng ứng dụng vẫn chờ ở tầng khác.

## 5. Phát hiện truy vấn chậm ở phía ứng dụng

Trong ứng dụng JPA, một thao tác nghiệp vụ có thể làm phát sinh nhiều SQL: entity load, lazy load, flush, insert/update/delete và truy vấn phân trang. Không phải lúc nào một method Repository cũng tương ứng với đúng một SQL.

### 5.1. Mục tiêu quan sát SQL

Cần biết tối thiểu:

- Câu lệnh hoặc nhóm câu lệnh nào tốn nhiều **tổng thời gian** nhất.
- Câu lệnh nào có **p95/p99** cao dù số lần gọi ít.
- Một request nghiệp vụ thực hiện **bao nhiêu câu SQL**.
- Thời gian cao đến từ **database execution, lock wait hay mạng/serialization**.
- Vấn đề xuất hiện sau thay đổi code, dữ liệu, index hay migration nào.

Ở môi trường phát triển, có thể bật log SQL Hibernate để hiểu câu lệnh được sinh:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
```

Đối với Hibernate 6, log binding parameter thường nằm dưới logger `org.hibernate.orm.jdbc.bind`. Không bật TRACE parameter hoặc in đầy đủ SQL có dữ liệu nhạy cảm trên production mà chưa thiết kế chính sách bảo vệ và giới hạn log. SQL logging liên tục cũng làm tăng I/O và ảnh hưởng hiệu năng.

Để đo request thực tế, ưu tiên instrumentation JDBC/span do Micrometer/OpenTelemetry hoặc công cụ đo truy vấn có khả năng tổng hợp. Hibernate statistics có thể hữu ích khi chẩn đoán cục bộ nhưng việc bật thống kê chi tiết diện rộng cần kiểm soát overhead.

### 5.2. Chậm vì N+1 hay chậm vì một truy vấn?

Ví dụ Repository trả về 100 `PurchaseOrder`. Nếu API map từng order sang DTO rồi gọi `order.getItems()` trên một quan hệ lazy, ORM có thể sinh:

```text
1 SQL: SELECT danh sách 100 orders
100 SQL: SELECT items WHERE order_id = ?
=> Có thể thành 101 round trip đến database
```

Mỗi SQL chỉ mất 5–10 ms nhưng tổng thời gian nhiều round trip và connection usage vẫn tăng cao. Khi đó thêm index cho một SQL riêng lẻ có thể cải thiện rất ít so với giảm số SQL.

Một phương án là lấy dữ liệu theo nhu cầu đọc bằng **DTO projection**, `JOIN FETCH` hoặc `@EntityGraph`. Tuy nhiên, fetch một collection bằng JOIN đồng thời phân trang có thể gây nhân bản hàng hoặc hành vi phân trang không mong muốn; phải chọn cách tải phù hợp, chẳng hạn hai truy vấn: lấy trang ID rồi batch tải chi tiết. Đừng mặc định “EAGER mọi quan hệ” để xóa N+1.

### 5.3. Chậm vì truy vấn thực sự

Những biểu hiện thường gặp:

- Lọc bằng cột chưa có index phù hợp với mẫu truy vấn.
- Truy vấn đi qua quá nhiều hàng, `SELECT *` hoặc join tạo lượng kết quả quá lớn.
- Sort/group trên nhiều dữ liệu, cần hash/sort lớn và tràn ra đĩa.
- Điều kiện biến đổi cột như `LOWER(column)` khi chưa có index/expression index thích hợp.
- Phân trang offset rất sâu khiến database phải quét hoặc bỏ qua nhiều hàng.
- Plan dùng thống kê cardinality cũ, dữ liệu phân bố lệch hoặc plan không phù hợp tham số.
- Lệnh nhìn như chậm nhưng phần lớn thời gian đang **chờ lock**.

Tối ưu hiệu quả cần dựa trên execution plan và số liệu truy vấn, không chỉ dựa vào việc “thấy có index”.

## 6. Chẩn đoán trực tiếp ở PostgreSQL

Phần này dùng PostgreSQL để minh họa. Với MySQL, Oracle hay SQL Server, nguyên tắc đo tương tự nhưng hệ thống view, log và cơ chế lock khác nhau.

### 6.1. Thống kê câu lệnh từ `pg_stat_statements`

Khi DBA đã cấu hình `shared_preload_libraries` và extension `pg_stat_statements`, có thể xem các truy vấn được chuẩn hóa và tổng hợp:

```sql
SELECT
    calls,
    ROUND(total_exec_time::numeric, 1) AS total_ms,
    ROUND(mean_exec_time::numeric, 2) AS mean_ms,
    rows,
    LEFT(query, 180) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Thứ tự theo `total_exec_time` giúp nhận diện SQL tiêu tốn **nhiều thời gian database nhất** trong khoảng thống kê. Thứ tự theo `mean_exec_time` giúp tìm câu lệnh nặng trung bình, nhưng phải kết hợp số lần gọi và mức độ ảnh hưởng. Một truy vấn chạy 10.000 lần × 20 ms có thể tiêu tốn tổng tài nguyên lớn hơn một truy vấn đơn lẻ 2 giây.

Lưu ý `pg_stat_statements` tổng hợp theo dạng câu lệnh; các số `mean_exec_time`/`total_exec_time` **không phải** p95/p99 theo request. Cần kết hợp trace/histogram nếu muốn phân phối độ trễ đầu cuối. Quyền xem nội dung truy vấn phụ thuộc chính sách database.

### 6.2. Kiểm tra transaction và wait event

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start  AS transaction_age,
    now() - query_start AS query_age,
    LEFT(query, 180) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

Kết quả giúp nhận diện:

- Session `active` đang thực thi SQL.
- Session `idle in transaction` có transaction còn mở nhưng đang không chạy SQL, có thể giữ khóa và cản trở việc dọn phiên bản row theo MVCC.
- `wait_event_type = 'Lock'` thể hiện session đang đợi lock.
- Transaction có `transaction_age` lớn bất thường cần được đối chiếu với request/worker tương ứng.

Thông tin `query_sample` có thể chứa dữ liệu nhạy cảm, nên chỉ truy cập trong môi trường có phân quyền. Trên bản PostgreSQL có đủ quyền, có thể kết hợp thêm `pg_locks` và `pg_blocking_pids(pid)` để xác định session đang chặn session nào.

### 6.3. Xem execution plan

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.customer_id, o.created_at
FROM purchase_orders o
WHERE o.customer_id = 1234
ORDER BY o.created_at DESC
LIMIT 20;
```

Các mục quan trọng khi đọc plan:

- **Actual rows** so với rows ước lượng: sai lệch lớn có thể chỉ ra statistics không còn phản ánh dữ liệu.
- **Sequential Scan / Index Scan / Bitmap Heap Scan**: xác định hướng truy xuất hàng, nhưng không coi Seq Scan mặc định là lỗi.
- **Buffers hit/read**: cho biết phần lớn thao tác có dùng cache hay đọc thêm block từ storage.
- **Sort/Hash và temp I/O**: xác định khâu tiêu hao bộ nhớ hoặc đĩa.
- **Execution Time**: thời gian xử lý ở database, chưa bao gồm đầy đủ thời gian chờ pool và xây response ở ứng dụng.

`EXPLAIN ANALYZE` **thực sự thực thi câu lệnh**. Chỉ chạy có kiểm soát, đặc biệt với SQL ghi dữ liệu hoặc truy vấn rất nặng. Dùng môi trường staging hoặc phiên đọc phù hợp và đánh giá tác động trước khi chạy trên production.

### 6.4. Slow query log và lock log

PostgreSQL có tham số `log_min_duration_statement` để log câu lệnh hoàn thành chậm hơn một ngưỡng thời gian (mili giây). `log_lock_waits` và `deadlock_timeout` có thể cung cấp bằng chứng về thời gian chờ khóa. Những cài đặt này phải được điều chỉnh theo SLO, khối lượng log, chính sách bảo mật và quyền quản trị; không bật log cực chi tiết vô thời hạn trên hệ thống tải cao.

## 7. Phân biệt các nguyên nhân khi chỉ số xấu đi

| Hiện tượng quan sát | Nguyên nhân nên điều tra | Hướng xử lý ban đầu |
|---|---|---|
| Pool pending tăng; active sát max; usage p99 tăng | Transaction dài hoặc DB chậm | Xem transaction spans, SQL, lock, external calls bên trong transaction |
| Acquire p99 tăng nhưng SQL p95 bình thường | Pool quá nhỏ so với concurrency, hoặc connection bị giữ lâu ngoài SQL | Soát checkout/return, concurrency, transaction scope; đối chiếu DB capacity |
| SQL latency p99 tăng, pending chưa cao | Plan xấu, I/O, lock, network | `EXPLAIN`, DB wait events, pg_stat_statements, histogram |
| Nhiều SQL nhỏ trong mỗi request | N+1, lazy loading, lặp query, thiếu batch | Đo query count theo operation, sửa fetch/projection/batching |
| `idle in transaction` tồn tại lâu | Transaction mở khi ứng dụng đang chờ/xử lý bên ngoài | Rút ngắn transaction, không gọi I/O ngoại vi khi giữ transaction |
| DB CPU/IO cao, thêm pool thì chậm hơn | Database đã bão hòa | Giảm concurrency có kiểm soát, tối ưu SQL, index, caching/batching |
| Timeout pool chỉ trong giờ migration | Backfill/DDL làm tăng khóa hoặc tranh connection | Throttle migration, tách workload, theo dõi lock và ảnh hưởng tới API |
| Lỗi `Connection is not available` tăng | Caller đợi quá `connectionTimeout` | Điều tra pending, active, usage và DB; không tự động chỉ tăng timeout |
| Latency API tăng nhưng các số DB bình thường | CPU/GC ứng dụng, serialization, service ngoài | Theo dõi JVM, thread, external spans và request trace |

Phải nhìn chỉ số trong cùng cửa sổ thời gian và trên cùng pool/instance. Một biểu đồ tổng hợp toàn cluster có thể che mất việc chỉ một pod đang bị rò connection hoặc một pool read replica đang bão hòa.

### Ví dụ suy luận theo dữ liệu

Một đợt tăng tải cho thấy:

```text
API p95                   : 2.7 s
Connection acquire p95    : 1.8 s
Connection usage p95      : 2.1 s
DB statement mean latency : 35 ms
Hikari active/max         : 12/12
Hikari pending            : > 0 liên tục
```

Những số này **không chứng minh** SQL đang nhanh trong mọi request; số trung bình DB có thể che đuôi chậm. Tuy nhiên chúng đủ để ưu tiên điều tra việc giữ connection lâu: có nhiều SQL trong transaction, gọi dịch vụ ngoài khi transaction còn mở, hoặc một số câu lệnh bị lock. Tăng `maximumPoolSize` khi chưa xem DB capacity có thể chuyển hàng đợi từ pool xuống database.

## 8. Giám sát trong vận hành và di trú schema

Trong một đợt deploy có **Flyway/Liquibase migration**, database có thể chịu thêm DDL, tạo index, backfill và kiểm tra constraint. Những thao tác này có thể kéo dài transaction hoặc giữ lock, khiến API đang chạy bình thường bất ngờ tăng latency.

### 8.1. Đo baseline trước migration

Trước khi thay đổi schema, lưu số liệu theo một cửa sổ tải đại diện:

- Traffic, error rate, API latency p50/p95/p99 cho các endpoint quan trọng.
- Hikari active/idle/pending, acquire p95, usage p95 và timeout.
- Transaction duration/rollback theo nhóm operation.
- Top SQL theo tổng thời gian, lock wait, CPU/I/O và số connection của DB.
- Số instance ứng dụng, cấu hình pool và bản ứng dụng/schema hiện tại.

Khi deploy, ghi timestamp của mỗi giai đoạn (**DDL**, **backfill**, **create index**, **switch application version**) để đối chiếu các biểu đồ với thay đổi thực tế. Nếu có thể, phát hành metric sự kiện triển khai hoặc annotation trên dashboard.

### 8.2. Những rủi ro thường gặp

**Backfill khối lượng lớn:** cập nhật hàng triệu hàng trong một transaction có thể làm tăng WAL/undo, giữ lock dài, tạo bloat và ảnh hưởng đọc/ghi. Cân nhắc chạy theo batch nhỏ, commit từng batch, giới hạn concurrency, checkpoint tiến độ và cho phép tiếp tục sau gián đoạn.

**DDL chặn giao dịch khác:** một số lệnh thay đổi bảng cần lock không tương thích với truy vấn hiện tại. Với PostgreSQL, `CREATE INDEX CONCURRENTLY` giúp giảm chặn các thao tác ghi trong nhiều trường hợp nhưng có yêu cầu riêng và **không được chạy bên trong transaction block**. Cần phối hợp với công cụ migration để xử lý script này đúng cách.

**Ứng dụng scale-out:** mỗi pod mới có pool riêng. Nếu tăng từ 4 lên 8 pod mà giữ `maximumPoolSize=12`, ứng dụng có thể yêu cầu tối đa 96 connection, chưa kể worker và migration.

**Schema và code không tương thích:** một đợt deploy rolling có thể có phiên bản ứng dụng cũ và mới truy cập đồng thời. Thực hành *expand → migrate → contract* (thêm cấu trúc tương thích, di chuyển dữ liệu, rồi mới bỏ cấu trúc cũ) giúp giảm áp lực phải thực hiện một migration khóa bảng lớn trong giờ cao điểm.

**Thay đổi index hoặc statistics:** sau migration, kế hoạch thực thi có thể thay đổi. Cần xem lại SQL top và `EXPLAIN` nếu p95/p99 tăng, kể cả khi không có lỗi ứng dụng.

### 8.3. Đối chiếu sau migration

Sau khi schema và ứng dụng ổn định, so sánh cùng traffic band giữa trước và sau:

| Hạng mục | Câu hỏi đánh giá |
|---|---|
| Pool | Pending/timeout có biến mất hay kéo dài hơn trước? |
| Transaction | p95/p99 có tăng tại thao tác write/read nào? |
| SQL | Query count và tổng DB execution time có đổi? |
| Lock | Xuất hiện lock wait hoặc deadlock mới không? |
| Sức chứa | Số session từ tất cả pod và job có còn trong giới hạn? |
| Tính đúng | Có lỗi timeout/rollback hoặc retry tạo tác động lặp? |

Nếu rollback một migration hoặc ứng dụng, cũng cần giám sát sau rollback: việc quay lại phiên bản cũ không bảo đảm một plan, statistics hay lượng lock sẽ lập tức giống trạng thái ban đầu.

## 9. Cảnh báo và runbook xử lý sự cố

Mục tiêu của cảnh báo là chỉ ra **hậu quả người dùng đang chịu** và **tín hiệu kỹ thuật có khả năng giải thích nguyên nhân**. Ví dụ:

- Cảnh báo ưu tiên cao khi API latency hoặc error rate vượt SLO, đồng thời xem pool timeout.
- Cảnh báo pool khi `pending > 0` duy trì qua nhiều lần đo, acquire p95 tăng và active liên tục sát max.
- Cảnh báo transaction khi duration p99 tăng mạnh so với baseline; nếu có, đặt thêm ngưỡng với các thao tác write nhạy cảm.
- Cảnh báo database khi lock wait/deadlock, quá nhiều session `idle in transaction` hoặc CPU/I/O liên tục bão hòa.

Mọi ngưỡng cụ thể cần dựa trên baseline và SLO thật của hệ thống, không sao chép một con số chung.

Khi nhận cảnh báo, có thể xử lý theo thứ tự:

1. **Xác định ảnh hưởng:** dịch vụ, API, khoảng thời gian, số người bị ảnh hưởng, error rate và tốc độ request.
2. **Phân tách độ trễ:** so p95 API với acquire, usage, transaction và SQL; kiểm tra trace chậm cùng thời gian.
3. **Kiểm tra DB:** session, lock, query top, CPU/I/O, connection limit; đối chiếu lúc deploy/migration/batch chạy.
4. **Khoanh vùng thay đổi:** release mới, thêm pod, query/index mới, backfill hoặc thay đổi timeout.
5. **Giảm ảnh hưởng có kiểm soát:** dừng/throttle batch, hạ concurrency, thu hẹp transaction, rollback thay đổi phù hợp hoặc tối ưu truy vấn.
6. **Xác minh sau can thiệp:** pending/acquire/usage giảm, SQL/lock cải thiện và API p95/error rate trở lại baseline; giữ lại dấu mốc sự cố và dữ liệu so sánh.

Không xóa connection hoặc kill session tùy tiện: có thể rollback giao dịch đang xử lý dữ liệu quan trọng. Nếu buộc phải can thiệp vào session/blocker, cần xác định transaction, chủ sở hữu và hậu quả nghiệp vụ.

## 10. Những giới hạn thường bị hiểu sai

### “Tăng pool là sửa được API chậm”

Chỉ đúng trong một số trường hợp pool giới hạn concurrency còn DB có đủ headroom. Nếu DB đã bão hòa hoặc transaction giữ connection do chờ lock, tăng pool có thể làm thời gian chờ SQL tệ hơn.

### “`@Transactional(readOnly = true)` đồng nghĩa không giữ connection”

Không đúng. Read-only chủ yếu là thông tin/hint về tính chất transaction và có thể ảnh hưởng flush/optimization tùy provider; truy vấn vẫn cần connection, transaction vẫn có thời lượng và vẫn có thể ảnh hưởng tới tài nguyên database.

### “Log SQL là đủ để biết bottleneck”

Log SQL cho biết câu lệnh được phát ra; nếu thiếu duration, số lần gọi, thời gian chờ lock và request context thì không đủ để kết luận nguyên nhân. Trên production phải tránh log dữ liệu bí mật và lượng log quá lớn.

### “Leak detection log nghĩa là code quên close connection”

Log này nghĩa là một lần checkout vượt ngưỡng. Điều tra stack trace, transaction duration và đường gọi; transaction hợp lệ quá dài cũng có thể tạo cảnh báo.

### “Spring transaction timeout sẽ dừng mọi truy vấn đúng hạn”

Timeout phụ thuộc transaction manager, JDBC driver và DB, và có thể có giới hạn trong việc ngắt code Java đang thực thi. Cần phối hợp cơ chế timeout theo từng lớp và kiểm chứng hành vi thực tế.

### “Một statement nhanh thì transaction cũng nhanh”

Không đúng nếu một transaction chạy 200 statement nhỏ, flush một lượng lớn entity hoặc bị chờ ở dịch vụ ngoài. Phải quan sát số statement trên mỗi transaction và thời gian connection bị giữ.

## 11. Chiến lược áp dụng thực tế

Với hệ thống JPA vận hành lâu dài, điểm khởi đầu hữu ích là **dashboard cho pool và API**, sau đó bổ sung **transaction timer có operation label cố định**, **tracing JDBC** và **thống kê SQL/lock ở database**. Các phép đo phải cùng đồng hồ thời gian, có tên data source/pool và có dấu mốc deploy để so sánh.

Khi có truy vấn chậm, hãy xác định nó làm chậm vì chính SQL, vì quá nhiều round trip, hay vì chờ transaction khác. Khi pool cạn, hãy xem connection usage, transaction duration và sức chứa database trước khi thay đổi kích thước. Khi di trú schema, hãy đo baseline, theo dõi DDL/backfill/lock trong suốt quá trình và xác minh sau rollout.

Thiết kế giám sát như vậy biến một biểu hiện chung “JPA chậm” thành những câu hỏi có dữ liệu kiểm chứng: **đợi connection bao lâu, giữ connection làm gì, SQL nào tốn tài nguyên, transaction nào chặn giao dịch khác, và thay đổi nào khiến các đại lượng ấy xấu đi**.
