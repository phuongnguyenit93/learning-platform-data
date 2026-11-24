# Datasource Micrometer trong Spring Boot

Trong chương **Database observability** của module **SPRING_BOOT_OBSERVABILITY**, Datasource Micrometer là cách quan sát tình trạng và hành vi của connection pool thông qua metrics. Với Spring Boot sử dụng JDBC và HikariCP, Micrometer có thể thu thập số connection đang active, idle, tối đa, số thread đang chờ connection và thời gian lấy/giữ connection. Những metrics này giúp phát hiện pool saturation, thiếu capacity hoặc connection bị giữ quá lâu trước khi lỗi lan thành timeout ở API.

Datasource metrics không thay thế database monitoring. Micrometer quan sát pool ở phía ứng dụng: ứng dụng đang có bao nhiêu connection, bao nhiêu request chờ pool và thời gian mượn connection ra sao. Database server monitoring quan sát phía máy chủ: query execution, locks, buffer/cache, replication và tài nguyên database. Kết hợp hai phía giúp phân biệt pool cạn connection do ứng dụng giữ connection lâu với database chậm khiến connection không được trả về.

Trong module **SPRING_BOOT_OBSERVABILITY**, datasource metrics là một tín hiệu trong bộ observability gồm Micrometer Observation, metrics, logs và distributed tracing. Bài này giải thích cách Spring Boot/Micrometer instrument DataSource, ý nghĩa từng metric, cấu hình Actuator/Prometheus, đọc dấu hiệu pool saturation, kiểm soát tags/cardinality và liên kết với query traces/logs.

## 1. Datasource Micrometer nằm ở đâu?

Với JDBC datasource được Spring Boot quản lý và pool có integration phù hợp, Actuator/Micrometer có thể bind metrics từ pool vào MeterRegistry:

```text
Incoming HTTP request
        |
        v
   Service method
        |
        v
     JDBC call
        |
        v
   HikariCP DataSource
      |       |       |
      v       v       v
   active    idle   pending
      \       |       /
       \      |      /
        Micrometer binder
               |
               v
          MeterRegistry
               |
       +-------+--------+
       |                |
       v                v
 /actuator/metrics   Prometheus scrape
       |                |
       +-------+--------+
               v
        Metrics backend
```

| Thành phần | Vai trò |
| --- | --- |
| JDBC DataSource | API cung cấp connection cho ứng dụng |
| HikariCP | Quản lý connection pool nếu được chọn làm pool implementation |
| Micrometer binder | Đọc pool state/statistics và ghi vào MeterRegistry |
| MeterRegistry | Lưu measurements trong ứng dụng và chuyển tới registry/exporter |
| Actuator metrics endpoint | Cho phép kiểm tra metric trong registry |
| Prometheus registry/endpoint | Expose metrics theo format scrape khi được cấu hình |
| Metrics backend | Lưu lịch sử, query, dashboard và alert |

Spring Boot thường tự cấu hình HikariCP khi dependency phù hợp có mặt và datasource được tạo theo auto-configuration. Cách bind metrics phụ thuộc Spring Boot, Micrometer và pool implementation/version. Không giả định mọi DataSource tùy chỉnh hoặc datasource tạo ngoài container đều tự động được instrument.

## 2. Những metric datasource thường gặp

Tên metric phổ biến với HikariCP/Micrometer có thể có prefix hikaricp hoặc tên được chuẩn hóa theo registry. Các metric thường thấy:

| Metric concept | Ý nghĩa | Dùng để trả lời |
| --- | --- | --- |
| Active connections | Connection đang được ứng dụng mượn | Bao nhiêu connection đang bận? |
| Idle connections | Connection sẵn sàng được mượn | Pool còn bao nhiêu capacity rảnh? |
| Maximum connections | Giới hạn connection tối đa của pool | Trần capacity hiện tại là bao nhiêu? |
| Minimum idle | Mức idle tối thiểu được cấu hình/duy trì | Pool cố duy trì bao nhiêu connection rảnh? |
| Pending threads | Thread đang chờ lấy connection | Request có đang xếp hàng ở pool không? |
| Connection acquire time | Thời gian chờ để lấy connection | Pool có khó cấp connection không? |
| Connection usage time | Thời gian connection được giữ/mượn | Connection có bị giữ lâu không? |
| Connection creation time | Thời gian tạo connection mới | Mở connection tới DB có chậm không? |

Tên chính xác và availability tùy binder/pool/version. Ví dụ một registry có thể expose:

```text
hikaricp.connections.active
hikaricp.connections.idle
hikaricp.connections.max
hikaricp.connections.min
hikaricp.connections.pending
hikaricp.connections.acquire
hikaricp.connections.usage
hikaricp.connections.creation
```

Một số registry chuyển dấu chấm thành underscore hoặc đổi tên khi scrape. Hãy xác minh metric names thực tế tại Actuator/Prometheus endpoint.

## 3. Active, idle, max và pending nói lên điều gì?

Các gauge về pool state cần được đọc cùng nhau:

- **Active:** số connection đang được mượn bởi code ứng dụng.
- **Idle:** số connection đang rảnh trong pool.
- **Max:** giới hạn connection tối đa.
- **Pending:** số thread đang chờ connection được trả về hoặc được tạo.

Một pool có active gần max chưa chắc là sự cố nếu thời gian giữ connection ngắn và không có pending. Ngược lại, active thấp nhưng pending cao có thể báo hiệu pool đang bị giới hạn, metrics bị lấy từ datasource khác hoặc connection acquisition có vấn đề cần điều tra.

Ví dụ một snapshot:

| Metric | Giá trị minh họa |
| --- | ---: |
| Active | 20 |
| Idle | 0 |
| Max | 20 |
| Pending | 14 |

Snapshot này cho thấy pool đã chạm max và 14 thread đang chờ. Nếu trạng thái kéo dài, latency request có thể tăng do phải chờ connection. Tuy nhiên, một snapshot đơn lẻ không đủ kết luận; hãy xem thời gian duy trì, acquire latency, DB health và traffic.

### Connection utilization

\[
\text{Pool utilization} =
\frac{\text{Active connections}}{\text{Maximum connections}}
\times 100\%
\]

Với active = 18 và max = 20, utilization là 90%. Đây là tín hiệu cần theo dõi khi kéo dài, nhưng không phải ngưỡng lỗi chung cho mọi workload. Một pool có utilization cao nhưng không có pending và acquire time thấp có thể đang hoạt động tốt.

## 4. Acquire time, usage time và creation time

Ba timer/histogram concept trả lời ba vấn đề khác nhau:

**Acquire time** đo thời gian ứng dụng chờ pool cấp connection. Nếu acquire p95 tăng, pool có thể thiếu connection rảnh, pending queue tăng hoặc connection creation chậm.

**Usage time** đo thời gian connection được giữ trong lúc ứng dụng sử dụng. Nếu usage p95 cao, transaction dài, query chậm, code giữ connection trong khi gọi HTTP bên ngoài hoặc connection không được đóng đúng cách có thể là nguyên nhân.

**Creation time** đo thời gian tạo connection mới. Nếu tăng, cần kiểm tra DNS/network tới database, TLS, authentication, database connection limit và tốc độ handshake.

Không suy ra query duration trực tiếp từ usage time. Usage time có thể gồm nhiều thao tác trong transaction, thời gian xử lý giữa các câu query và thời gian ứng dụng giữ connection. Muốn biết câu SQL nào chậm, cần database query metrics/tracing hoặc slow query logs.

## 5. Spring Boot tự cấu hình DataSource và HikariCP

Với ứng dụng Spring Boot JDBC phổ biến, dependency starter và cấu hình datasource có thể tạo HikariCP pool tự động:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
```

Ví dụ cấu hình:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: `{ORDERS_DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1800000

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Đây là ví dụ cấu hình; username, URL, pool size và timeout phải dựa trên môi trường thật. Không commit mật khẩu vào source. Expose Actuator endpoints theo network/security policy, đặc biệt không để metrics hoặc environment details công khai không cần thiết.

pool-name giúp phân biệt datasource trong metric tags khi ứng dụng có nhiều pool. Dùng tên ổn định theo chức năng như orders-pool hoặc reporting-pool, không dùng request ID hoặc tên tenant tùy ý.

## 6. Micrometer binder và datasource tự tạo

Spring Boot có thể bind metrics tự động cho datasource được auto-configure. Nếu datasource được tạo thủ công, nhiều datasource hoặc pool wrapper được dùng, cần xác minh mỗi pool có binder phù hợp.

Với HikariCP, Micrometer binder có thể đọc Hikari metrics thông qua DataSource/pool integration. Trong một số setup, có thể đăng ký binder thủ công:

```java
import com.zaxxer.hikari.HikariDataSource;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.db.HikariCPMetrics;

void bindPoolMetrics(
        HikariDataSource dataSource,
        MeterRegistry registry) {
    new HikariCPMetrics(dataSource, java.util.Collections.emptyList())
            .bindTo(registry);
}
```

Đoạn code minh họa binder API; package, constructor và cách auto-binding có thể thay đổi theo Micrometer version. Trước khi bind thủ công, kiểm tra Actuator đã đăng ký metrics cho pool chưa. Bind cùng datasource hai lần có thể gây meter registration conflict hoặc dữ liệu trùng.

Với nhiều datasource, xác định rõ mỗi pool được đặt tên/tag thế nào và dashboard có phân biệt được chúng không. Không dùng một tag chung cho tất cả pool nếu cần chẩn đoán pool riêng.

## 7. Kiểm tra datasource metrics qua Actuator

Nếu Actuator metrics endpoint được expose, có thể kiểm tra metric names:

```http
GET /actuator/metrics
```

Sau đó truy vấn một metric cụ thể theo tên registry thực tế, ví dụ:

```http
GET /actuator/metrics/hikaricp.connections.active
GET /actuator/metrics/hikaricp.connections.pending
GET /actuator/metrics/hikaricp.connections.acquire
```

Tên trên chỉ là ví dụ thường gặp; endpoint metrics trả về danh sách measurements và available tags của registry. Nếu không thấy metric:

1. Xác nhận Actuator và metrics registry có trong dependency.
2. Kiểm tra DataSource thực tế có phải HikariDataSource không.
3. Xác định pool được Spring Boot auto-configure hay tạo thủ công.
4. Kiểm tra binder có được đăng ký và datasource có đang hoạt động không.
5. Kiểm tra metric name theo output thật, không phỏng đoán prefix.

Actuator metrics endpoint phục vụ chẩn đoán từng metric trong registry; nó không thay thế Prometheus scrape endpoint hoặc backend lịch sử.

## 8. Prometheus và dashboard datasource

Nếu dùng Prometheus registry/exporter, endpoint exposition có thể cung cấp các series datasource cho scraper:

```text
GET /actuator/prometheus
```

Một dashboard cơ bản nên có:

| Panel | Metric concept | Cách đọc |
| --- | --- | --- |
| Active vs max | Active connections và max | Mức sử dụng pool |
| Idle | Idle connections | Số connection rảnh |
| Pending | Pending threads | Áp lực chờ pool |
| Acquire p95/p99 | Acquire duration histogram | Độ trễ lấy connection |
| Usage p95/p99 | Connection usage duration | Thời gian giữ connection |
| Creation duration | Connection creation time | Độ trễ mở connection |
| Connection timeout count | Pool timeout/error metric nếu có | Request thất bại do không lấy được connection |

Không phải mọi binder/exporter đều cung cấp cùng loại histogram hoặc timeout counter. Xem series thực tế và cấu hình distribution phù hợp. Đừng tạo query dựa trên tên metric hoặc unit đoán trước.

## 9. Nhận diện pool saturation

Pool saturation thường thể hiện qua nhiều tín hiệu đồng thời:

1. Active connections tiến sát maximum.
2. Idle connections về 0 trong thời gian kéo dài.
3. Pending threads tăng.
4. Acquire time p95/p99 tăng.
5. HTTP server latency hoặc transaction latency tăng.
6. Có connection acquisition timeout.

```text
Normal:
active thấp/vừa | idle còn | pending = 0 | acquire thấp
                         |
                         v
High load:
active tăng | idle giảm | pending bắt đầu tăng
                         |
                         v
Pool saturation:
active = max | idle = 0 | pending cao | acquire tăng
                         |
                         v
API latency tăng / timeout / request failure
```

Khi thấy dấu hiệu saturation, không vội tăng maximum-pool-size. Database có giới hạn connection và có thể bị quá tải nếu mọi instance cùng tăng pool. Cần xác định bottleneck trước:

- Query chậm hoặc lock contention?
- Transaction giữ connection quá lâu?
- Code gọi remote HTTP trong transaction?
- Connection leak hoặc không đóng resource?
- Traffic tăng đột biến hoặc pool sizing không phù hợp?
- Database max connections hoặc network capacity đã chạm giới hạn?

Tăng pool chỉ hữu ích khi database còn capacity và workload thực sự cần concurrency cao hơn. Nếu database đã nghẽn, tăng connection có thể làm tình hình tệ hơn.

## 10. Nhiều datasource và pool naming

Một ứng dụng có thể có datasource cho OLTP, reporting, batch hoặc read replica. Mỗi pool cần identity rõ ràng:

| Pool | Mục đích | Pool name minh họa |
| --- | --- | --- |
| Primary | Transaction nghiệp vụ | orders-primary |
| Read replica | Truy vấn đọc | orders-read |
| Reporting | Báo cáo | orders-reporting |
| Batch | Tác vụ nền | orders-batch |

Metric tags nên dùng tên pool ổn định. Không tạo pool name theo tenant/request vì mỗi tên có thể tạo một nhóm series riêng. Nếu hệ thống multi-tenant dùng chung pool, tenant ID không nên là datasource metric tag mặc định.

Nếu có nhiều datasource nhưng dashboard chỉ thấy một pool, kiểm tra:

- Bean nào được primary và auto-configure?
- Các datasource còn lại có được bind?
- Pool wrapper có expose Hikari metrics?
- Binder có đăng ký đúng registry?
- Tag pool name có phân biệt?

## 11. Cardinality và tags của datasource metrics

Datasource metrics thường có ít dimensions như pool name, service instance hoặc datasource role. Giữ chúng ổn định:

| Tag | Nên dùng? | Lý do |
| --- | --- | --- |
| Pool name cố định | Có | Phân biệt pool trong ứng dụng |
| Service name | Có, thường là resource | Nhận diện service |
| Instance ID | Tùy backend/resource model | Phân biệt replica nếu cần |
| Database host đã chuẩn hóa | Có thể | Chẩn đoán endpoint DB có giới hạn |
| Tenant ID tùy request | Không | Cardinality tăng theo tenant |
| SQL statement nguyên văn | Không | Nội dung lớn, động và có thể nhạy cảm |
| Query parameter values | Không | Tạo series không giới hạn |
| Connection ID | Không | Gần như duy nhất cho từng connection |

Không gắn raw SQL hoặc query hash vào datasource pool gauge/timer nếu mục tiêu là pool health. SQL-level metrics/tracing cần pipeline khác với giới hạn cardinality, normalization và redaction riêng.

## 12. Liên kết datasource metrics với query, logs và traces

Datasource metrics cho biết pool đang chịu tải ra sao; database query tracing/logs giúp tìm câu lệnh hoặc transaction gây ra tải:

```text
HTTP request latency p95 tăng
          |
          v
JDBC connection acquire p95 tăng?
          |
     +----+----+
     |         |
    Yes        No
     |         |
     v         v
Pool / DB   Điều tra app hoặc
contention  dependency khác
     |
     v
Trace spans / SQL observation / DB slow query logs
     |
     v
Xác định query chậm, lock hoặc connection giữ lâu
```

Khi tracing JDBC được cấu hình, trace có thể hiển thị span cho thao tác database; khả năng và mức chi tiết tùy instrumentation/driver. Không mặc định mọi JDBC call tự tạo span chỉ vì Hikari metrics đã có.

Log có thể ghi correlation ID/trace ID cùng operation, datasource role và exception type. Không ghi password, connection URL có credential, raw parameter nhạy cảm hoặc SQL chứa dữ liệu người dùng. Dùng query fingerprint/normalized statement nếu hệ thống có cơ chế an toàn.

Metrics không cần Trace ID làm tag. Nếu backend hỗ trợ exemplars, có thể liên kết một sample metric với trace representative mà không làm tăng cardinality toàn bộ series.

## 13. Connection leak, transaction dài và pool timeout

| Hiện tượng | Metric/dấu hiệu | Nguyên nhân cần điều tra |
| --- | --- | --- |
| Pool thiếu capacity | Active sát max, pending tăng | Sizing hoặc concurrency cao |
| Query chậm | Usage time tăng, DB query duration tăng | Execution plan, index, locks |
| Acquire chậm | Acquire time tăng, idle thấp | Pool saturation hoặc creation chậm |
| Connection creation chậm | Creation time tăng | DNS/network/TLS/auth/database load |
| Connection leak | Active tăng và không giảm sau workload | Resource không đóng hoặc transaction bị treo |
| Long transaction | Usage time dài, lock waits | Transaction scope quá rộng |
| Pool timeout | Acquire vượt connectionTimeout | Pool không cấp connection trong deadline |

HikariCP có thể hỗ trợ leak detection threshold để cảnh báo connection bị giữ lâu hơn ngưỡng. Chỉ bật với threshold phù hợp vì log leak detection có thể tạo noise khi query hợp lệ lâu. Leak detection là công cụ chẩn đoán, không thay thế việc quản lý connection/transaction đúng.

Ví dụ:

```yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 30000
```

Giá trị 30 giây chỉ là ví dụ; đặt theo transaction duration bình thường và mục tiêu vận hành. Nếu threshold thấp hơn workload hợp lệ, log cảnh báo có thể gây hiểu nhầm.

## 14. Kiểm thử datasource metrics

Một integration test nên kiểm tra cả metric xuất hiện và thay đổi khi có hoạt động JDBC:

1. Khởi động application context với datasource test.
2. Xác nhận MeterRegistry chứa datasource/pool metrics dự kiến.
3. Thực hiện một query đơn giản qua repository/JdbcTemplate.
4. Kiểm tra acquire/usage hoặc query-related metrics tăng theo semantics của binder.
5. Tạo concurrency có kiểm soát để quan sát active/pending nếu test pool nhỏ và có thể tái lập.
6. Xác nhận pool name tag đúng và không có request/tenant/SQL raw tags.
7. Kiểm tra Actuator endpoint và Prometheus exposition nếu được cấu hình.

Không viết test phụ thuộc chính xác thời gian acquire vài millisecond trên CI vì timing dao động theo máy. Ưu tiên kiểm tra meter registration, tag set, counter/count monotonic hoặc trạng thái pool dưới điều kiện test được kiểm soát.

### Kịch bản điều tra

Một service có:

| Chỉ số | Giá trị quan sát |
| --- | --- |
| Active | 30 |
| Max | 30 |
| Idle | 0 |
| Pending | 45 |
| Acquire p95 | 1,8 giây |
| JDBC usage p95 | 2,4 giây |
| HTTP server p95 | 2,7 giây |

Các số liệu gợi ý pool đang chịu áp lực. Bước tiếp theo:

- Kiểm tra database query latency và lock waits.
- Mở trace của request đại diện để xem thao tác JDBC nào giữ connection lâu.
- Kiểm tra transaction có bao quanh remote HTTP call hoặc xử lý ngoài database không.
- So sánh pool size tổng của tất cả app instances với giới hạn DB.
- Xem connection timeout/leak warnings và workload concurrency.

Không kết luận chỉ cần tăng max lên 60. Nếu DB đang xử lý query chậm, gấp đôi pool có thể tăng contention.

## 15. Bài tập tình huống

Một ứng dụng Spring Boot có 4 replica, mỗi replica dùng HikariCP với maximum pool size 25. Dashboard cho thấy active thường xuyên chạm 25, pending tăng trong giờ cao điểm và acquire p99 tăng lên 2 giây. Database có giới hạn 120 connections cho ứng dụng này.

**Câu hỏi:**

1. Tổng số connection tối đa theo cấu hình hiện tại là bao nhiêu?
2. Vì sao tăng pool size mỗi replica lên 40 có thể nguy hiểm?
3. Những metrics nào cần kiểm tra để phân biệt query chậm với pool thiếu capacity?
4. Usage time cao gợi ý điều gì?
5. Có thể liên kết pool metrics với tracing/logs như thế nào?

**Gợi ý phân tích:**

- Tổng pool max hiện tại là 4 × 25 = 100 connections, chưa tính các process/job khác có thể kết nối DB.
- Nếu tăng lên 40, tổng max thành 160, vượt giới hạn 120 trước khi tính overhead và workload khác.
- Xem active/idle/max/pending, acquire duration, usage duration, creation duration, connection timeout, DB query latency và lock waits.
- Usage cao có thể do query chậm, transaction dài hoặc code giữ connection trong khi thực hiện công việc không liên quan DB.
- Dùng datasource pool name và low-cardinality dimensions trong metrics; mở trace có JDBC spans và tìm logs theo correlation/trace ID. Không đưa SQL raw hay connection ID vào metric tags.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| Datasource binder | Biết cách Micrometer thu thập pool metrics |
| Active/idle/max/pending | Đọc tình trạng pool |
| Acquire/usage/creation | Phân biệt các loại latency |
| Spring Boot/HikariCP | Cấu hình pool và quan sát datasource |
| Actuator/Prometheus | Xác minh metric names và tags thực tế |
| Pool saturation | Nhận diện active=max, idle=0, pending tăng |
| Multi-datasource | Đặt pool name ổn định và phân biệt từng pool |
| Cardinality | Không gắn tenant, connection ID hoặc SQL raw vào tags |
| Database tracing | Liên kết metrics với query spans và logs |
| Capacity planning | Tính tổng pool size trên mọi replica |
| Connection leak | Dùng usage/leak detection đúng cách |
| Testing | Xác minh binder, tags và metric behavior |

**Ghi nhớ:** Datasource Micrometer cho biết ứng dụng đang sử dụng connection pool như thế nào. Active, idle, max và pending mô tả trạng thái; acquire, usage và creation duration giúp tìm điểm nghẽn. Trong Spring Boot, hãy xác minh binder và metric names thực tế, đặt pool name ổn định, expose Actuator/Prometheus an toàn và theo dõi nhiều tín hiệu cùng lúc. Khi pool saturation xuất hiện, kiểm tra query latency, lock, transaction scope, connection leak và tổng pool capacity trên tất cả replicas trước khi tăng maximum size. Kết hợp pool metrics với JDBC traces và structured logs để xác định nguyên nhân ở đúng lớp.
