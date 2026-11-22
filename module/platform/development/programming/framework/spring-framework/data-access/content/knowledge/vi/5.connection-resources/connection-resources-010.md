# Đọc lỗi và số liệu để phát hiện rò rỉ kết nối

Khi ứng dụng Java/Spring dùng JDBC, Hibernate/JPA hoặc Spring JDBC, nhiều thao tác truy cập dữ liệu cần mượn một `Connection` từ `DataSource`. Với connection pool, tài nguyên này phải được **trả lại pool** sau khi sử dụng. Nếu connection bị giữ quá lâu hoặc không được trả, ứng dụng có thể xuất hiện lỗi timeout dù database vẫn hoạt động.

Để phát hiện sự cố, không chỉ nhìn vào một dòng log hoặc một chỉ số `active`. Cần đọc **thông báo lỗi, stack trace, số liệu pool theo thời gian, thời lượng giữ connection, tải ứng dụng và trạng thái database** rồi đặt chúng trong cùng dòng thời gian. Bài này lấy Spring JDBC và HikariCP làm ví dụ, nhưng tư duy chẩn đoán có thể dùng với các pool khác nếu đối chiếu đúng tên metric và cơ chế của chúng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **connection leak**, giữ connection lâu, pool cạn vì tải cao, truy vấn/transaction chậm và database từ chối kết nối.
- Đọc đúng ý nghĩa `active`, `idle`, `total`, `max`, `pending`, counter timeout và timer acquire/usage.
- Hiểu HikariCP `leakDetectionThreshold` cảnh báo điều gì, stack trace chỉ tới đâu, và khi nào có thông báo connection đã được trả lại.
- Sử dụng log, Spring Boot Actuator/Micrometer hoặc Hikari JMX để đặt giả thuyết rồi kiểm chứng trên chuỗi số liệu.
- Chuyển stack trace/call site nghi vấn thành kiểm tra mã Java/Spring, sửa vòng đời JDBC bằng `try-with-resources`, `JdbcTemplate` và transaction boundary phù hợp.
- Đánh giá bản sửa qua một bài thử có tải, so sánh trước/sau và tránh cách “khắc phục” chỉ che triệu chứng.

## 2. Từ mượn connection đến trả connection

Với một pool JDBC điển hình:

~~~text
Request / scheduled job
        |
        v
Service / Repository
        |
        v
DataSource.getConnection()
        |
        +--> Pool có connection idle? ---- Có --> borrow
        |                                   |
        +--> Có thể tạo thêm connection? - Có --> create + borrow
        |
        +--> Hết slot và không có idle --> chờ (pending)
                                            |
                      connection được trả --+
                          |                 |
                          v                 +--> quá connectionTimeout
                  sử dụng SQL                    --> exception
                          |
                      close() / release
                          |
                          v
                   trả về pool (idle)
~~~

Một `Connection` **đang active trong pool** thường là connection đã được mượn và chưa trả, **không đồng nghĩa** database đang thực thi SQL. Nó có thể đang đọc `ResultSet`, chờ I/O, giữ transaction, xử lý Java hoặc đơn giản bị bỏ quên. Khi dùng pool, `Connection.close()` trên handle do pool cấp thường trả tài nguyên logic về pool; pool quyết định lúc nào đóng connection vật lý.

**Connection leak** trong phạm vi bài này là trường hợp mã đã mượn connection nhưng không hoàn trả đúng vòng đời do quên close/release, đường xử lý ngoại lệ bỏ qua cleanup hoặc tài nguyên bị giữ lại vô thời hạn. Một connection được trả sau 40 giây trong transaction hợp lệ không nhất thiết bị leak, dù có thể làm pool cạn. Ngược lại, leak chưa chắc tạo ngay lỗi; pool còn idle sẽ che dấu sự cố cho tới lúc tích lũy đủ lâu.

Phân biệt ba lớp thời gian:

1. **Acquire/wait time:** thời gian gọi `getConnection()` phải chờ một connection có thể sử dụng.
2. **Usage/borrow time:** từ khi mượn connection thành công đến khi trả về pool; thời gian này có thể dài hơn thời gian SQL chạy.
3. **SQL execution / transaction duration:** thời gian database thực thi câu lệnh hoặc transaction hoạt động. Các khoảng thời gian này có thể chồng lấn nhưng **không bằng nhau**.

Ví dụ: request dùng 100 ms để chạy SQL, sau đó gọi API ngoài mất 15 giây trong cùng transaction và chỉ hoàn thành mới release connection. Metric usage có thể gần 15 giây dù database chỉ bận 100 ms. Đó là giữ connection lâu do ranh giới transaction, khác về nguyên nhân so với quên close hoàn toàn.

## 3. Nhận diện bốn nhóm hiện tượng

| Hiện tượng | Điều thấy ở pool | Câu hỏi phải kiểm tra |
| --- | --- | --- |
| **Leak thật:** connection không trả | Active tích lũy, không về mức bình thường sau khi tải giảm; idle giảm, có thể tới pending/timeout | Có đoạn mã thiếu cleanup? Thread hoặc bean nào giữ handle? |
| **Giữ connection quá lâu:** transaction dài, đọc stream chậm, chờ service khác | Active cao theo thời lượng request/transaction; có thể được trả sau thời gian dài | SQL thực sự chậm hay code giữ transaction qua I/O? |
| **Nhu cầu hợp lệ vượt công suất pool** | Active gần max khi QPS/đồng thời tăng; pending tăng; hồi phục khi tải giảm | Pool/DB phù hợp capacity và độ dài truy vấn hiện tại chưa? |
| **DB/driver/network không tạo được connection** | Total có thể thấp hơn max, pending/timeout tăng, thường có root cause kết nối | DB có sẵn không, giới hạn session/TLS/credentials/driver ra sao? |

Đây là các **mẫu hình**, không phải luật quyết định tự động. Một hệ thống có thể vừa có leak vừa gặp truy vấn chậm; một pool bão hòa chưa nói rõ nguyên nhân.

### Hai câu hỏi nền tảng

- **Bao lâu connection được mượn?** Nếu trả sau khi transaction kết thúc thì cần xem transaction duration và dòng xử lý. Nếu không bao giờ trả thì xem nơi mượn và nhánh cleanup.
- **Tải đã giảm mà active có giảm theo không?** Xem nhiều lần lấy mẫu sau khi request/job hoàn tất. Một snapshot duy nhất không đủ kết luận.

## 4. Đọc log lỗi theo tầng, tránh đoán từ tên exception

### 4.1. HikariCP báo không lấy được connection

Log minh họa (số liệu do bài tự đặt, không phải log thu thập từ hệ thống):

~~~text
java.sql.SQLTransientConnectionException:
  LearningPool - Connection is not available, request timed out after 5002ms
  (total=8, active=8, idle=0, waiting=6)
~~~

Diễn giải:

- `Connection is not available`: caller không được cấp connection trước khi hết thời gian chờ mượn.
- `request timed out after 5002ms`: thời gian chờ mượn xấp xỉ `connectionTimeout`, **không phải SQL query timeout**.
- `total=8`: pool hiện có tám connection; `active=8`: cả tám đang được mượn; `idle=0`: không có connection sẵn; `waiting=6`: thời điểm ghi log có sáu thread đang đợi.
- Log chứng minh **pool exhaustion tại thời điểm đó**; nó chưa chứng minh ai làm rò rỉ connection.

Nếu `total < maximumPoolSize` mà vẫn timeout, cần kiểm tra pool có đang cố tạo connection, database có từ chối, driver có lỗi xác thực/TLS hoặc thời gian thiết lập connection kéo dài không. Hikari có thể bọc nguyên nhân gốc trong chuỗi exception; đọc đầy đủ `Caused by`, `SQLException.getNextException()` và log của driver/database.

### 4.2. HikariCP phát hiện khả năng leak theo thời gian giữ

Khi bật `leakDetectionThreshold`, Hikari lên lịch cảnh báo nếu một connection được mượn quá ngưỡng. Log minh họa đã lược bớt stack:

~~~text
WARN  com.zaxxer.hikari.pool.ProxyLeakTask -
  Connection leak detection triggered for ... on thread http-nio-8080-exec-4,
  stack trace follows
java.lang.Exception: Apparent connection leak detected
    at com.zaxxer.hikari.HikariDataSource.getConnection(...)
    at com.example.data.ReportRepository.loadReport(ReportRepository.java:42)
    at com.example.service.ReportService.generate(ReportService.java:28)
~~~

Cần đọc **đúng ý nghĩa stack trace**:

- Stack thường ghi lại **đường gọi khi connection được mượn** (checkout/acquisition site), không nhất thiết là vị trí nó bị giữ tại thời điểm cảnh báo.
- `ReportRepository.java:42` là đầu mối để tìm đường cấp connection. Tiếp tục xem mọi nhánh `return`, `throw`, `catch` và `finally` đi qua sau dòng này.
- Log cảnh báo *apparent leak* là **nghi vấn do giữ quá ngưỡng**, không khẳng định leak thật. Một báo cáo xử lý 30 giây vẫn có thể release đúng cách sau khi hoàn thành.

Nếu connection được trả sau khi Hikari đã phát cảnh báo, có thể thấy một log INFO dạng:

~~~text
Previously reported leaked connection ... was returned to the pool (unleaked)
~~~

Thông báo này là bằng chứng connection **đã được trả** và cảnh báo trước đó có thể là giữ lâu, không còn là handle thất lạc vào thời điểm trả. Nó không bảo đảm hành vi giữ lâu là chấp nhận được. Ngược lại, không thấy log “unleaked” **không tự động** khẳng định leak: log có thể bị lọc, ứng dụng dừng trước khi trả, hoặc connection còn được giữ khi kết thúc quan sát.

### 4.3. Các lỗi dễ nhầm với leak

| Dòng lỗi/triệu chứng | Điều nó trực tiếp cho biết | Phải kiểm tra thêm |
| --- | --- | --- |
| `SQLTransientConnectionException` lúc getConnection | Không cấp connection kịp | Active/pending/total, tải, lỗi tạo connection |
| `SQLTimeoutException` từ driver/câu SQL | Tác vụ JDBC có giới hạn thời gian bị vượt, tùy driver | SQL, lock, network, query timeout; không tự kết luận pool leak |
| `Connection reset`, `Broken pipe`, SQLState class `08` | Kết nối gặp lỗi truyền thông/driver | DB/network, server đóng connection, pool validation |
| Database `too many connections` | Giới hạn kết nối database bị chạm | Tổng connection của **mọi** instance/pool và tiến trình khác |
| DB lock/deadlock/lock timeout | Tranh chấp transaction/lock | Transaction đang mở, query và lịch sử lock |
| Spring `CannotGetJdbcConnectionException` | Spring không lấy được JDBC connection | Root cause của pool/driver; Spring có thể wrap exception bên dưới |

Cần phân biệt **lỗi xảy ra ở bước lấy connection**, **lỗi trong lúc SQL chạy** và **lỗi trả/đóng connection**. Stack trên cùng của Spring có thể là wrapper; nguyên nhân gốc nằm sâu hơn.

## 5. Những chỉ số pool phải đọc cùng nhau

Trong Spring Boot có Actuator và Micrometer, các DataSource được hỗ trợ thường có meter với prefix `jdbc.connections.*`; HikariCP có thêm `hikaricp.connections.*`. Với ứng dụng Spring Framework không dùng Boot, cần tự cấu hình monitoring tương ứng. Tên/sự hiện diện của meter phụ thuộc phiên bản, registry, pool implementation và việc DataSource có được instrument hay không.

| Tên meter điển hình (Actuator) | Kiểu | Ý nghĩa | Gợi ý khi diễn giải |
| --- | --- | --- | --- |
| `jdbc.connections.active` / `hikaricp.connections.active` | Gauge | Connection đang được mượn | Có giảm sau khi nhu cầu kết thúc không? |
| `jdbc.connections.idle` / `hikaricp.connections.idle` | Gauge | Connection pool đang rảnh | Idle bằng 0 khi tải cao chưa nói lên leak |
| `hikaricp.connections` | Gauge | Tổng số connection hiện tại trong Hikari pool | Không phải số tích lũy đã tạo từ trước |
| `jdbc.connections.max` / `hikaricp.connections.max` | Gauge | Giới hạn connection được pool phép giữ | Là giới hạn pool, không đồng nghĩa giới hạn của database |
| `jdbc.connections.min` / `hikaricp.connections.min` | Gauge | Mức duy trì tối thiểu theo pool | Hữu ích khi hiểu idle baseline |
| `hikaricp.connections.pending` | Gauge | Thread đang chờ mượn connection | Pending tăng liên tục là dấu hiệu áp lực |
| `hikaricp.connections.timeout` | Counter | Số lần mượn connection bị timeout tích lũy | Quan sát tốc độ tăng; counter tăng không giảm |
| `hikaricp.connections.acquire` | Timer | Thời gian cấp connection cho caller | Tăng khi contention hoặc tạo connection chậm |
| `hikaricp.connections.usage` | Timer | Thời gian giữ connection trước lúc trả | Giúp tìm giao dịch/request giữ tài nguyên lâu |
| `hikaricp.connections.creation` | Timer | Thời gian tạo connection mới | Tăng khi kết nối DB/driver/network chậm |

**Gauge** là ảnh chụp trạng thái tại thời điểm lấy mẫu; **counter** là số tích lũy tăng khi có sự kiện, có thể reset khi process khởi động lại; **timer** tổng hợp thời lượng và số lần đo. Đừng đọc số `timeout=50` như “50 thread đang chờ”: đó là counter các lần timeout đã xảy ra, không phải trạng thái hiện tại.

### Quan hệ giữa active, idle, total, max

Thông thường trong một snapshot ổn định, `active + idle ≈ total` và `total ≤ max`. Dấu `≈` có chủ đích: metric thường được lấy ở những thời điểm rất gần nhau, không có snapshot nguyên tử chung, còn pool liên tục borrow/return/create/retire connection. Giá trị cộng có thể lệch trong lúc thay đổi nhanh.

**Active không phải QPS:** QPS/requests-per-second cao nhưng mỗi truy vấn chỉ vài mili giây có thể giữ mức active thấp. Ngược lại chỉ vài transaction kéo dài có thể chiếm hết pool. Active là số connection đang được mượn, kể cả không có query nào đang chạy.

**Pending không phải tất cả request:** pending chỉ đếm những caller đang chờ connection ở pool này. Request nằm chờ tại thread pool, queue, HTTP server hoặc upstream chưa gọi `getConnection()` không nằm trong con số đó.

**Usage timer có độ trễ chứng cứ:** thời lượng được ghi khi connection được trả về. Một connection đang bị giữ vô thời hạn có thể chưa đóng góp một quan sát usage hoàn chỉnh. Do đó usage timer thấp **không loại trừ leak đang diễn ra**. Nên xem cùng active, pending và leak-detection logs.

### Nhãn (tags) và nhiều pool

Ứng dụng có thể có nhiều `DataSource`: primary, reporting, read-only, batch, tenant-specific. Metric tổng cộng tất cả pool có thể che một pool bị cạn. Trong Spring Boot, `jdbc.connections.*` thường có tag theo tên bean DataSource; Hikari-specific metrics có tag pool name. Khi tra cứu phải lọc đúng **service, instance, pool, environment**. Nếu các pod/instance dùng tên pool giống nhau, bổ sung nhãn instance tại hệ thống monitoring.

## 6. Xem số liệu bằng Spring Boot Actuator

Ví dụ cấu hình **dành cho môi trường chẩn đoán có kiểm soát** trong Spring Boot dùng HikariCP:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: LearningPool
      maximum-pool-size: 8
      connection-timeout: 5000
      leak-detection-threshold: 20000

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
~~~

- `maximum-pool-size: 8` đặt giới hạn connection của pool; đây **chỉ là số mẫu**, không phải recommendation cho production.
- `connection-timeout: 5000` (mili giây) là giới hạn chờ một connection từ pool.
- `leak-detection-threshold: 20000` (mili giây) khiến Hikari log cảnh báo connection bị mượn hơn khoảng 20 giây.
- `management.endpoints.web.exposure.include` cho phép xem endpoint metrics qua HTTP; endpoint này cần hạn chế truy cập bằng bảo mật và cấu hình mạng theo ứng dụng thật.

Theo HikariCP, ngưỡng leak-detection bằng `0` nghĩa là tắt (mặc định); mức nhỏ nhất được chấp nhận để bật là `2000` ms. Ngưỡng **không đóng connection**, chỉ cảnh báo. Chọn threshold dựa trên thời gian giữ connection hợp lệ ở hệ thống (chẳng hạn cao hơn thời gian transaction bình thường nhưng đủ thấp để bắt sự cố), chứ không chọn 2000 ms cho mọi ứng dụng. Bật cảnh báo ở ngưỡng quá thấp có thể làm log nhiễu vì transaction dài hợp lệ.

Nếu ứng dụng có `spring-boot-starter-actuator` và metric binder phù hợp, thử trong mạng quản trị:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.pending
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.timeout
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.usage
curl -s http://localhost:8080/actuator/metrics/jdbc.connections.active
~~~

Các URL này là **ví dụ truy vấn**, không phải khẳng định mọi ứng dụng đều có đủ meter. Hãy xem danh sách tên thực tế trong `/actuator/metrics` trước; một số chỉ số không xuất hiện khi pool/provider hoặc cấu hình instrumentation khác. Endpoint metrics dùng tên meter của Micrometer; khi đưa sang Prometheus, tên có thể được chuẩn hóa (ví dụ dấu chấm thành gạch dưới và counter thêm suffix), nên không dùng máy móc tên HTTP endpoint làm tên PromQL.

Nếu endpoint cho nhiều pool, lọc tag sau khi kiểm tra `availableTags` trong response. Ví dụ một cách gửi tag:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/hikaricp.connections.active?tag=pool:LearningPool"
~~~

Tên tag `pool` là cách Hikari/Micrometer thường sử dụng; hãy xác minh nhãn thực tế ở môi trường đang dùng thay vì đoán.

### Ví dụ đọc một response metrics

Một output **minh họa cấu trúc**, các giá trị không phải số liệu hệ thống:

~~~json
{
  "name": "hikaricp.connections.active",
  "measurements": [
    {"statistic": "VALUE", "value": 8.0}
  ],
  "availableTags": [
    {"tag": "pool", "values": ["LearningPool"]}
  ]
}
~~~

Điều chắc chắn rút ra: tại thời điểm đo, pool phù hợp tag đang có khoảng tám connection active. Để biết có leak hay không vẫn phải đối chiếu `max`, `pending`, tải và các snapshot trước/sau. Nếu một meter gộp nhiều pool/instance, lọc tag trước khi so với `maximumPoolSize` của một pool duy nhất.

### Cần lấy số liệu theo thời gian

Actuator `/metrics` trả trạng thái tại một thời điểm. Muốn phát hiện leak tích lũy, nên thu thập chuỗi thời gian bằng registry/monitoring như Prometheus, Grafana, Datadog hoặc hệ thống tương đương; theo dõi ít nhất:

- `active` và `idle` theo thời gian, cùng đường `max` của **đúng pool**.
- `pending` và tốc độ tăng counter `timeout`.
- Thời lượng acquire/usage phân vị (p95/p99 nếu được cấu hình distribution phù hợp) và tổng số lượt dùng.
- QPS, số request đang xử lý, thời gian HTTP, độ dài transaction, số job chạy song song.
- CPU, thread pool, DB lock/wait/query duration, số session database, network/connection creation errors.

Không có ngưỡng cảnh báo “active ≥ 80% = leak” dùng chung cho mọi hệ thống. Quan sát **độ kéo dài**, **mức nền khi ít tải**, và **đồng biến/nghịch biến** với request. Một pool được cố ý thiết kế sát ngưỡng sử dụng có thể có active cao mà vẫn khỏe nếu pending và timeout không tăng.

## 7. Phân tích diễn biến: cùng một ảnh chụp, nhiều kết luận khác nhau

Giả định mỗi tình huống đều là một pool có `max=8`. Số liệu dưới đây **là tình huống học tập**, không phải log/metric thực tế.

### Tình huống A: tải tăng rồi hồi phục

| Thời điểm | In-flight requests | Active | Idle | Pending | Timeout counter | Diễn giải |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 09:00 | 1 | 1 | 7 | 0 | 0 | Mức nền |
| 09:05 | 15 | 8 | 0 | 5 | 0 | Tải cao, pool đạt max |
| 09:10 | 4 | 4 | 4 | 0 | 2 | Đã có timeout khi bão hòa |
| 09:15 | 0 | 0 | 8 | 0 | 2 | Active trở về 0 |

Kết luận hợp lý: có **pool saturation trong giai đoạn cao điểm**, nhưng chưa có tín hiệu mạnh về connection bị giữ sau khi công việc kết thúc. Counter timeout vẫn là 2 vì đó là số tích lũy. Tiếp tục xem khả năng chịu tải, thời gian SQL/transaction và kích thước pool.

### Tình huống B: tải giảm nhưng active giữ nguyên

| Thời điểm | In-flight requests | Active | Idle | Pending | Timeout counter | Diễn giải |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 10:00 | 1 | 1 | 7 | 0 | 0 | Mức nền |
| 10:05 | 12 | 8 | 0 | 4 | 0 | Pool đạt max |
| 10:10 | 0 | 8 | 0 | 0 | 2 | Tải quan sát đã dừng, active chưa giảm |
| 10:15 | 0 | 8 | 0 | 0 | 2 | Active tiếp tục bị giữ |

Đây là **tín hiệu đáng điều tra**: vì sao tám connection còn active khi số request quan sát là 0? Kiểm tra scheduled jobs, async workers, in-flight event consumers, transaction dài và borrower stack. Không được kết luận leak chỉ từ HTTP request: một tác vụ nền không được tính vào in-flight requests vẫn có thể dùng connection hợp lệ.

Khi đã kiểm soát mọi nguồn tải và đợi đủ lâu hơn thời gian transaction bình thường, active vẫn không trở về mức nền, giả thuyết leak tăng sức nặng. Nếu có log checkout chỉ về cùng một call site và không có bằng chứng return, khả năng tìm được nguyên nhân càng cao.

### Tình huống C: total nhỏ hơn max nhưng vẫn timeout

Ví dụ `max=16, total=3, active=3, idle=0, pending=12`. Đây **không giống** việc tám connection bị giữ trong một pool tối đa tám. Pool đang không có đủ connection, nhưng có thể do **không tạo thêm được** (database giới hạn, mạng, TLS, authentication, driver) hoặc quá trình mở connection quá chậm. Cần đọc log tạo connection, root cause của `SQLException` và trạng thái database trước khi sửa code cleanup.

## 8. Ví dụ Java 17+ chạy độc lập: đọc timeline metric

Ví dụ sau **không kết nối database**; nó mô phỏng bốn snapshot để luyện cách phát hiện *tín hiệu nghi vấn*. Lưu thành `PoolSignalDemo.java`:

~~~java
import java.util.List;

public class PoolSignalDemo {
    record Snapshot(
            String time,
            int inFlight,
            int active,
            int idle,
            int max,
            int pending,
            long timeouts
    ) {}

    public static void main(String[] args) {
        List<Snapshot> samples = List.of(
                new Snapshot("10:00", 1, 1, 7, 8, 0, 0),
                new Snapshot("10:05", 12, 8, 0, 8, 4, 0),
                new Snapshot("10:10", 0, 8, 0, 8, 0, 2),
                new Snapshot("10:15", 0, 8, 0, 8, 0, 2)
        );

        for (Snapshot s : samples) {
            System.out.printf(
                    "%s inFlight=%d active=%d/%d idle=%d pending=%d timeouts=%d%n",
                    s.time(), s.inFlight(), s.active(), s.max(),
                    s.idle(), s.pending(), s.timeouts()
            );
        }

        Snapshot a = samples.get(2);
        Snapshot b = samples.get(3);
        boolean suspicious =
                a.inFlight() == 0 && b.inFlight() == 0
                && a.active() == a.max()
                && b.active() == b.max();

        System.out.println(suspicious
                ? "SUSPECT: inspect borrowers and long transactions"
                : "INCONCLUSIVE: continue observing");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 PoolSignalDemo.java
java PoolSignalDemo
~~~

Stdout chính xác:

~~~text
10:00 inFlight=1 active=1/8 idle=7 pending=0 timeouts=0
10:05 inFlight=12 active=8/8 idle=0 pending=4 timeouts=0
10:10 inFlight=0 active=8/8 idle=0 pending=0 timeouts=2
10:15 inFlight=0 active=8/8 idle=0 pending=0 timeouts=2
SUSPECT: inspect borrowers and long transactions
~~~

Đây chỉ là **heuristic học tập**. Chương trình không có thông tin request theo background job, thread owner hay transaction duration, nên chỉ in `SUSPECT` để kích hoạt điều tra. Một công cụ production cần dùng dữ liệu theo thời gian thực và thêm tín hiệu; không nên tự động restart server/close connection từ biểu thức đơn giản này.

## 9. Dùng leak detection đúng cách với HikariCP

`leakDetectionThreshold` phát sinh cảnh báo sau khi connection bị checkout quá một khoảng thời gian. Ví dụ trong Spring Boot:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: LearningPool
      leak-detection-threshold: 20000
~~~

Ở môi trường không dùng Spring Boot, một `HikariConfig` có thể được cấu hình trực tiếp:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:h2:mem:training");
config.setUsername("sa");
config.setPassword("");
config.setPoolName("LearningPool");
config.setLeakDetectionThreshold(20_000L);
HikariDataSource dataSource = new HikariDataSource(config);
~~~

Đoạn này là **minh họa tích hợp**, yêu cầu dependency HikariCP và JDBC driver H2; cần đóng `HikariDataSource` khi ứng dụng sở hữu vòng đời pool. Nó không phải Java file độc lập. Nếu môi trường đã cung cấp pooled `DataSource` (ví dụ JNDI), không tạo pool Hikari thứ hai chỉ để bật leak detection; hãy sử dụng khả năng chẩn đoán của pool do container quản lý.

**Ngưỡng 20 giây** chỉ là ví dụ. Chọn theo phân phối thời gian borrow/transaction hợp lệ:

1. Quan sát usage bình thường dưới tải thực tế, tìm p95/p99 hoặc phần đuôi phù hợp.
2. Lựa chọn ngưỡng lớn hơn các ca hợp lệ phổ biến nhưng đủ nhỏ để bắt giữ lâu gây rủi ro.
3. Bật trong khoảng chẩn đoán, giám sát tần suất cảnh báo và tác động log.
4. Phân loại từng stack, đối chiếu log `unleaked` và metric; chỉ sửa code sau khi xác định đường giữ connection.
5. Điều chỉnh/giữ cấu hình theo chính sách vận hành khi hoàn tất; tránh threshold quá thấp gây cảnh báo giả hàng loạt.

**Cần phân biệt:** `connectionTimeout` giới hạn thời gian *chờ mượn* connection; `leakDetectionThreshold` kiểm tra thời gian *đã mượn nhưng chưa trả*. `maxLifetime`/`idleTimeout` kiểm soát vòng đời connection của pool theo điều kiện, **không phải cơ chế thu hồi ngay một connection đang bị application giữ**. Tăng `maxLifetime` hoặc giảm `idleTimeout` thường không xử lý nguyên nhân mã quên close.

### Đọc stack checkout có trách nhiệm

Một stack có thể trỏ vào `JdbcTemplate` hoặc framework wrapper trước khi trỏ tới class ứng dụng. Hãy tìm frame **đầu tiên thuộc package nghiệp vụ** và lần theo callback, stream, transaction và nhánh exception. Nếu một cùng call site có nhiều warning, đó là điểm ưu tiên kiểm tra, nhưng chưa bảo đảm tất cả warning cùng một nguyên nhân. Correlate với trace/span/request ID và timestamp, tránh log secret hoặc toàn bộ thông tin truy vấn nhạy cảm.

## 10. Xác minh qua JMX khi không dùng Actuator

HikariCP có thể expose MBean khi cấu hình `registerMbeans=true`. Các thuộc tính pool MXBean thường gồm:

- `ActiveConnections`: connection được mượn.
- `IdleConnections`: connection đang rảnh.
- `TotalConnections`: tổng connection pool hiện giữ.
- `ThreadsAwaitingConnection`: thread đang chờ borrow.

Ví dụ cấu hình ứng dụng sở hữu Hikari pool:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: LearningPool
      register-mbeans: true
~~~

Trong công cụ JMX như JConsole/JMC, tìm MBean theo tên pool. Giá trị được lấy ở các thời điểm khác nhau nên có thể không cộng chính xác trong lúc pool thay đổi nhanh. JMX cũng có quyền thao tác quản trị pool; giới hạn truy cập và không chạy thao tác can thiệp connection trong khi đang điều tra trừ khi có kế hoạch vận hành cụ thể.

Nếu cần đọc qua Java (đoạn minh họa trong ứng dụng đã có bean `HikariDataSource`):

~~~java
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;

HikariPoolMXBean pool = hikariDataSource.getHikariPoolMXBean();
if (pool != null) {
    System.out.println("active=" + pool.getActiveConnections());
    System.out.println("idle=" + pool.getIdleConnections());
    System.out.println("waiting=" + pool.getThreadsAwaitingConnection());
}
~~~

Đây là code phụ thuộc HikariCP và một biến `hikariDataSource` đã được inject; không phải chương trình Java độc lập. Lấy mẫu định kỳ và đối chiếu với request/transaction mới có ý nghĩa chẩn đoán. MBean giúp **quan sát** chứ không cho biết object Java nào đang giữ từng connection.

## 11. Truy từ dấu hiệu về mã nguồn

Khi log chỉ vào một vị trí mượn connection, xem đủ các nhánh điều khiển, đặc biệt:

- Trong `try` có `return` sớm hay ném exception trước khi `close()`?
- `ResultSet`, `PreparedStatement`, `CallableStatement` hoặc `Connection` có được mở ngoài vòng đời mong đợi không?
- Một object/iterator/stream giữ `ResultSet` sống sau khi method trả về?
- Có callback async, scheduled job, event listener hoặc thread local giữ connection/transaction không?
- Có lời gọi HTTP, file I/O, sleep, xử lý CPU lâu trong transaction sau lúc lấy connection không?
- Logic đọc/ghi dùng Spring transaction-aware access hay tự lấy connection bằng đường khác?

### 11.1. Mẫu sai: JDBC mở connection rồi quên close

Đây là **đoạn mã chống ví dụ**, không nên sử dụng:

~~~java
// Chống ví dụ: nếu query hoặc mapping lỗi, connection có thể bị giữ.
Connection connection = dataSource.getConnection();
PreparedStatement statement =
        connection.prepareStatement("SELECT name FROM customer WHERE id = ?");
statement.setLong(1, customerId);
ResultSet rs = statement.executeQuery();
if (!rs.next()) {
    return null; // Return sớm: không đóng result set, statement, connection.
}
return rs.getString("name"); // Cũng không đóng resource.
~~~

Mỗi request chạy đoạn này có thể để lại một borrowed connection. Khi số request tích lũy tới `maximumPoolSize`, request mới phải chờ và có thể nhận timeout. Code ném `SQLException` trước khi cleanup càng làm lỗi khó tái hiện nếu chỉ thử đường thành công.

### 11.2. Mẫu đúng: try-with-resources cho cả ba tài nguyên

Đây là đoạn method có thể đặt trong class Java đã có field `DataSource dataSource`; đoạn này cần JDBC driver/database tương ứng để chạy:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class CustomerReader {
    private final DataSource dataSource;

    public CustomerReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findName(long customerId) throws SQLException {
        String sql = "SELECT name FROM customer WHERE id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, customerId);
            try (ResultSet rs = statement.executeQuery()) {
                return rs.next() ? rs.getString("name") : null;
            }
        }
    }
}
~~~

`try-with-resources` đóng theo thứ tự ngược lúc tạo: `ResultSet` → `PreparedStatement` → `Connection`; cả khi có `return` hoặc exception, các `close()` vẫn được gọi. Với pooled DataSource, `close()` trên handle đúng là thao tác **trả về pool**. Đây là quy tắc tránh leak cho JDBC trực tiếp. Nếu connection tham gia Spring-managed transaction, cần sử dụng đường lấy/release phù hợp (xem bên dưới), không tự đóng một resource do transaction manager sở hữu một cách tùy tiện.

**Không dùng `finally { connection.close(); }` mà bỏ qua các lỗi thứ cấp khi `connection` có thể chưa được gán; try-with-resources biểu đạt ownership rõ ràng hơn.** Java giữ exception chính và thêm lỗi khi close thành *suppressed exception*, hữu ích cho điều tra.

### 11.3. Với Spring JDBC, để JdbcTemplate quản lý resource

Mẫu repository trong một Spring application context đã có bean `JdbcTemplate`:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerCountRepository {
    private final JdbcTemplate jdbc;

    public CustomerCountRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int countCustomers() {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer", Integer.class
        );
        return count == null ? 0 : count;
    }
}
~~~

`JdbcTemplate` quản lý việc lấy và trả JDBC resources qua hạ tầng Spring. Trong transaction đang hoạt động, nó dùng cơ chế `DataSourceUtils` để dùng connection đang gắn với transaction rồi để transaction manager quyết định thời điểm trả cuối cùng. Vì vậy, **không phải mỗi lệnh JdbcTemplate kết thúc là active lập tức giảm** khi service vẫn còn một transaction mở.

Nếu dùng JDBC thuần trong Spring-managed transaction, cân nhắc `DataSourceUtils.getConnection(dataSource)` và `DataSourceUtils.releaseConnection(connection, dataSource)`, hoặc `TransactionAwareDataSourceProxy` khi tích hợp legacy code; không trộn trực tiếp `dataSource.getConnection()` với transaction-bound connection rồi giả định mọi lời gọi cùng một transaction. Ưu tiên các abstraction Spring khi có thể.

### 11.4. Stream kết quả cần được đóng

`JdbcTemplate.queryForStream(...)` trả về một `Stream<T>` dựa trên tài nguyên JDBC. Việc đọc hết dữ liệu **không thay thế** việc đóng stream. Ví dụ trong class có `JdbcTemplate jdbc`:

~~~java
import java.util.stream.Stream;

public long countPositiveIds() {
    try (Stream<Long> ids = jdbc.queryForStream(
            "SELECT id FROM customer",
            (rs, rowNum) -> rs.getLong("id"))) {
        return ids.filter(id -> id > 0).count();
    }
}
~~~

Dù consumer `count()` hoàn tất, `try-with-resources` vẫn cần thiết để gọi `Stream.close()` và giải phóng JDBC resources mà stream sở hữu. Không trả một live stream ra controller rồi quên đóng sau khi serialize. Các API stream của JPA/Hibernate cũng có yêu cầu vòng đời; xem tài liệu provider và transaction context thực tế.

### 11.5. Giữ transaction quá rộng

Ví dụ service định làm:

~~~text
@Transactional
  query database (50 ms)
  gọi external HTTP API (15 s)
  ghi database (50 ms)
  commit / release
~~~

Ở nhiều cấu hình, connection đã được mượn tại thao tác đầu và bị giữ cho tới khi transaction kết thúc. Leak detection có thể báo warning sau 10 giây dù code cuối cùng trả connection. Để giảm thời gian chiếm pool, xem có thể **tách phần I/O mạng khỏi transaction** một cách an toàn về nghiệp vụ và nhất quán dữ liệu hay không. Không tự ý chuyển transaction boundaries nếu quy tắc nguyên tử của nghiệp vụ yêu cầu các thao tác ghi cùng transaction.

Với Spring AOP, `@Transactional` còn phụ thuộc cơ chế proxy, lời gọi nội bộ cùng bean, transaction manager, propagation và đường chạy async; kiểm tra transaction thực sự active thay vì suy luận chỉ từ annotation.

## 12. Dùng thêm dữ liệu từ database để loại trừ nguyên nhân

Pool metrics nói về connection phía **application**; phía database có thể cho thấy session, transaction và câu SQL đang thực thi. Chúng bổ sung cho nhau chứ không có ánh xạ một-một hoàn hảo: một driver/pool có thể mở connection vật lý theo lịch riêng, còn database cũng nhận connection từ ứng dụng khác.

Với PostgreSQL, có thể quan sát session theo quyền được cấp:

~~~sql
SELECT pid, usename, application_name, state,
       now() - xact_start AS transaction_age,
       now() - query_start AS query_age,
       wait_event_type, wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Khi đọc:

- `state='active'` ở `pg_stat_activity` có nghĩa PostgreSQL đang xử lý truy vấn cho backend đó. Nó **không đồng nghĩa** Hikari `active` (đang được mượn ở application).
- `idle in transaction` ở PostgreSQL có thể cho thấy transaction vẫn mở mà không chạy SQL, cần tìm người giữ transaction; có thể gây lock/bloat và chiếm tài nguyên.
- `transaction_age` là tuổi transaction khi `xact_start` không NULL; `query_age` là tuổi mốc query được ghi nhận, không thể mặc nhiên xem đó là thời gian query đang chạy với mọi trạng thái.
- `wait_event_type` và `wait_event` giúp phân biệt chờ lock/I/O, nếu phiên bản PostgreSQL cung cấp và user có quyền xem.

Giới hạn quyền database có thể che thông tin session/query của user khác. Không chạy các lệnh terminate session hàng loạt chỉ vì thấy nhiều session; cần xác định owner và tác động transaction. Với MySQL, SQL Server, Oracle hoặc database khác, dùng view/monitoring tương đương theo tài liệu của hệ quản trị đó.

Cũng kiểm tra **tổng số pool của các instance**: 10 pod, mỗi pod `max=20`, có thể tạo tới khoảng 200 connection về mặt cấu hình, chưa kể worker/service khác. Lỗi database đạt giới hạn connection không có nghĩa từng pool đang leak.

## 13. Quy trình điều tra một incident từ đầu đến cuối

### Bước 1 — Khoanh vùng và lưu bằng chứng

Ghi khoảng thời gian, môi trường, service/instance/pool, bản deploy, request/job liên quan, số liệu trước và sau khi bắt đầu lỗi. Thu thập các exception đầy đủ và log pool, root cause, trace IDs nếu có. Nếu có nhiều datasource, phải biết **pool nào** hết connection.

### Bước 2 — Xác định lỗi ở pha nào

Nếu lỗi nằm tại `getConnection()`, xem active/idle/total/pending và nguyên nhân mở connection. Nếu đã có connection nhưng query timeout, ưu tiên SQL execution, lock và transaction. Nếu không thấy lỗi nhưng active không trở về baseline, bắt đầu điều tra giữ connection lâu/leak.

### Bước 3 — So sánh baseline, peak và recovery

Trên **cùng instance/pool**, vẽ active, pending, counter timeout cùng request rate/in-flight và thời gian xử lý. Quan sát ít nhất đủ lâu để các transaction hợp lệ có thể kết thúc; tránh đưa một thời lượng cố định chung cho mọi hệ thống.

Nếu active tăng theo tải rồi giảm: nghiêng về capacity hoặc latency. Nếu active tích lũy qua nhiều lần tăng/giảm tải và không về baseline: nghiêng về leak hoặc tác vụ nền/transaction không kết thúc.

### Bước 4 — Ghép leak log với borrower stack

Nếu bật leak detection, lấy stack tại thời điểm checkout, lọc theo class ứng dụng và khoảng thời gian. Tìm nơi mở connection, nơi lẽ ra đóng, nhánh return/exception, callback/stream. Quan sát có log “unleaked” hay không. Nếu nhiều warning thuộc cùng code path, làm rõ nó là một request cực dài hay nhiều connection thực sự không trả.

### Bước 5 — Kiểm chứng DB và thread

Xem session, transaction age, lock wait và query chậm ở database; đối chiếu request/trace, JVM thread dump khi phù hợp. Thread dump cho biết vị trí thread đang đứng ở thời điểm chụp; không phải lúc nào cũng xác định chủ sở hữu connection. Dùng thêm span/time logging ở transaction/service và connection checkout logs nếu cần.

### Bước 6 — Sửa nguyên nhân nhỏ nhất

Ví dụ:

- Bọc JDBC Connection/Statement/ResultSet trong `try-with-resources`.
- Dùng `JdbcTemplate` để giảm code quản lý tài nguyên thủ công.
- Bảo đảm các stream/cursor/iterator dựa trên JDBC được đóng sau khi đọc.
- Thu hẹp transaction không cần giữ qua network call; giới hạn thời gian truy vấn/transaction và kiểm tra đường xử lý cancellation.
- Khắc phục query chậm, lock contention hoặc giới hạn DB nếu nguyên nhân không phải leak.
- Nếu có nhiều `DataSource`, xác định đúng transaction manager và pool được sử dụng.

### Bước 7 — Kiểm thử sau sửa

Chạy lại tải tái hiện với cùng điều kiện đầu vào, concurrency, pool size và quan sát đủ thời gian. So sánh:

1. Active trở về mức nền sau khi tất cả tác vụ kết thúc?
2. Pending có giải tỏa, timeout counter có ngừng tăng ngoài thời điểm quá tải?
3. Thời gian borrow/usage có về phạm vi dự kiến?
4. Leak warnings ở call site cũ còn xuất hiện không; log “unleaked” có giúp giải thích cảnh báo do giữ lâu?
5. Trên DB còn transaction/session tồn đọng bất thường không?
6. Không phát sinh lỗi nghiệp vụ hoặc thay đổi transaction semantics sau khi sửa?

Không dùng kết quả “không còn exception trong 30 giây” làm QA duy nhất nếu leak tích lũy cần hàng trăm request mới xuất hiện.

## 14. Kiểm thử có kiểm soát để nhìn thấy sự khác biệt

Một bài tập hữu ích khi có môi trường test riêng: cấu hình một Hikari pool nhỏ (ví dụ 2 connection), tạo thao tác JDBC có và không có `try-with-resources`, gọi tuần tự rồi quan sát active/idle/pending. **Chỉ chạy tình huống cố ý quên đóng trong môi trường test cô lập**, vì nó làm cạn pool và gây lỗi cho tác vụ khác.

Thực hiện hai lượt tách biệt, tạo pool mới cho mỗi lượt để không giữ lại trạng thái của ví dụ lỗi:

- **Lượt A (cố ý lỗi):** Mượn connection nhưng không trả. Sau hai lần thành công, lần mượn kế tiếp có thể chờ rồi timeout, tùy cách pool và test chạy. Active không về baseline.
- **Lượt B (đúng):** Mỗi lần mượn đều nằm trong `try-with-resources`; sau khi method kết thúc, active trở lại mức phù hợp khi không có transaction khác.
- Đọc counter timeout và event log; số liệu có thể thay đổi theo thời điểm lấy mẫu. Nếu dùng H2 in-memory, pool vẫn phải có JDBC driver và schema test phù hợp.

Không dùng `System.gc()` hoặc hy vọng `finalize()` để sửa leak; vòng đời tài nguyên cần được quản lý tường minh. Connection pool có thể reclaim một số tài nguyên khi lỗi, nhưng điều đó không bảo đảm mọi connection bị mã giữ sẽ tự quay về đúng hạn.

## 15. Cách đặt cảnh báo và dashboard thực tế

Một dashboard điều tra nên đặt các đồ thị trên cùng timeline:

| Nhóm | Đồ thị nên có | Lý do |
| --- | --- | --- |
| Pool availability | active, idle, total, max | Thấy pool bão hòa và phục hồi |
| Contention | pending, acquire latency | Thấy thread phải chờ borrow |
| Failure | tốc độ tăng timeout counter, số lỗi `getConnection()` | Thấy tác động đến request |
| Duration | usage time, transaction time, query time | Phân biệt giữ connection và SQL chậm |
| Traffic | request rate, concurrency, batch throughput | Đối chiếu nhu cầu thực |
| DB | session, connection errors, lock wait, slow queries | Xác định nút thắt phía DB |

Một số **tín hiệu cảnh báo đáng cấu hình theo baseline/SLO**:

- Pending liên tục lớn hơn 0 trong nhiều kỳ lấy mẫu kèm acquire latency tăng.
- Tốc độ tăng counter timeout lớn hơn 0 và request bắt đầu thất bại.
- Active duy trì gần max lâu **sau khi mọi nguồn workload liên quan đã kết thúc**.
- Usage duration phần đuôi tăng rõ rệt sau một bản deploy, đặc biệt tại một endpoint/job.
- Nhiều leak-detection warnings từ cùng một code path, có hoặc không có sự kiện trả connection.

Đừng báo động chỉ từ “idle=0” trong 1 giây hoặc “active=8” khi `max=8`: chúng có thể phản ánh một peak bình thường. Dùng cửa sổ thời gian, điều kiện kết hợp, phân biệt môi trường và tránh alert storm.

Nếu dùng Prometheus, gauge nên được xử lý như giá trị trạng thái, còn counter timeout nên dùng tốc độ tăng/rate hoặc increase sau khi biết tên metric được export thực tế (thường khác tên Actuator). Không lấy phép trừ counter qua một lần restart mà quên counter reset.

## 16. Những nhầm lẫn cần tránh khi kết luận

1. **“Active cao = leak.”** Không đủ: có thể là workload, transaction dài hoặc query chậm. Cần so với workload và recovery.
2. **“Timeout xuất hiện = mã quên close.”** Timeout cho biết không borrow kịp; DB không tạo được connection cũng gây hiện tượng này.
3. **“Leak warning chắc chắn là leak.”** Ngưỡng cảnh báo là thời gian giữ; có thể có log trả lại pool sau đó.
4. **“Tăng maximumPoolSize giải quyết tận gốc.”** Nếu connection không trả, pool lớn hơn chỉ hoãn cạn; còn có thể làm DB quá giới hạn.
5. **“connectionTimeout là timeout của câu SELECT.”** Không: nó là thời gian chờ mượn pool; query/statement timeout được cấu hình ở tầng khác.
6. **“Connection.close() đóng socket mỗi lần.”** Với pool, nó thường trả handle để tái sử dụng; gọi close vẫn bắt buộc.
7. **“Usage timer thấp thì không có leak.”** Một connection chưa trả có thể chưa có sample usage hoàn thành.
8. **“Có @Transactional thì không thể giữ connection lâu.”** Transaction kéo dài thường chính là lý do borrow lâu; kiểm tra scope, query và I/O.
9. **“Cứ gọi dataSource.getConnection() trong code raw JDBC là tham gia đúng Spring transaction.”** Spring JDBC khuyến nghị `DataSourceUtils`/`JdbcTemplate` khi cần connection bound với transaction.
10. **“Pool số liệu khớp DB session 1:1.”** Hệ thống có nhiều pool/instance/connection khác; còn có idle, reconnect và instrumentation khác nhau.
11. **“Đã đóng ResultSet nghĩa là Connection chắc chắn được trả.”** Đóng từng resource theo ownership; ResultSet không thay việc đóng Connection.
12. **“Không thấy warning thì không có leak.”** Leak detection có thể tắt, threshold quá cao, log level lọc, hoặc sự cố khác mô hình.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Pool `max=10, active=10, idle=0, pending=3`. Có đủ bằng chứng kết luận leak chưa?  
**Đáp án:** Chưa. Chỉ chắc pool đang bão hòa tại thời điểm đo. Cần so sánh theo thời gian, tải, transaction/SQL, log checkout và khả năng tạo connection.

**Câu 2.** Timeout counter tăng từ 4 lên 9 trong cùng process. Có bao nhiêu lần timeout mới trong khoảng đó?  
**Đáp án:** 5 lần, nếu counter không reset và không có thay đổi cách thu thập.

**Câu 3.** Leak warning xuất hiện ở giây thứ 20, và giây 27 có “returned to the pool (unleaked)”. Điều gì được chứng minh?  
**Đáp án:** Connection đã được trả sau khi giữ vượt ngưỡng. Không thể nói đây là leak vĩnh viễn; cần xem lý do giữ 27 giây và tác động tới pool.

**Câu 4.** `active` vẫn bằng `max` sau khi HTTP request giảm còn 0. Vì sao chưa được tuyên bố chắc chắn leak?  
**Đáp án:** Có thể còn scheduled jobs, async consumers, transaction chờ I/O, background requests hoặc thông tin tải chưa bao phủ mọi borrower.

**Câu 5.** Tăng `maximumPoolSize` từ 10 lên 50 có sửa đoạn code quên `close()` không?  
**Đáp án:** Không. Nó làm chậm thời điểm pool cạn, có thể tăng áp lực database. Cần sửa đường resource release.

**Câu 6.** Với `JdbcTemplate.queryForStream(...)`, vì sao cần `try-with-resources` quanh Stream?  
**Đáp án:** Stream dựa trên ResultSet/Statement/Connection và cần gọi close để giải phóng JDBC resources, kể cả sau khi tiêu thụ xong.

**Câu 7.** Database log “too many connections” trong khi mỗi Hikari pool có `active=5` và `max=10`. Nên kiểm tra gì?  
**Đáp án:** Số pod/instance/pool, tổng connection của mọi ứng dụng khác, session DB, connection creation failure. Không suy luận chỉ từ một pool.

**Câu 8.** Hikari `hikaricp.connections.usage` tăng còn SQL p95 gần như không đổi. Giả thuyết nào hợp lý?  
**Đáp án:** Connection bị giữ ngoài thời gian SQL như transaction chứa HTTP call, xử lý dữ liệu hoặc chờ logic ứng dụng; cần đối chiếu transaction span và log borrower.

## 18. Tổng kết

**Rò rỉ kết nối là vấn đề vòng đời của tài nguyên đã được mượn.** Log timeout chỉ cho biết thời điểm pool không phục vụ được nhu cầu; leak-detection warning cung cấp vị trí mượn và thời gian giữ quá ngưỡng; metric active/idle/pending/usage/timeout mô tả sức khỏe pool theo thời gian. Kết luận đáng tin cần phối hợp cả ba với request, transaction và database state, sau đó xác nhận bằng kiểm thử trước/sau bản sửa.

Giữ connection ngắn nhất phù hợp nghiệp vụ, trả đúng ownership bằng `try-with-resources` hoặc cơ chế Spring, đóng các stream/cursor đúng cách và quan sát metric trên từng pool sẽ giúp phân biệt leak thật với nút thắt hiệu năng.

### Tài liệu tham khảo

- [HikariCP README — configuration (connectionTimeout, maximumPoolSize, leakDetectionThreshold)](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): ý nghĩa timeout borrow, giới hạn pool và ngưỡng cảnh báo leak.
- [HikariCP — ProxyLeakTask](https://github.com/brettwooldridge/HikariCP/blob/dev/src/main/java/com/zaxxer/hikari/pool/ProxyLeakTask.java): cơ chế log stack của borrower và log trả kết nối “unleaked”.
- [HikariCP — JMX Monitoring and Management](https://github.com/brettwooldridge/HikariCP/wiki/MBean-%28JMX%29-Monitoring-and-Management): số liệu active/idle/total/waiting và lưu ý snapshot.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): meter `jdbc.connections.*`, metric Hikari, Actuator query.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceUtils`, `JdbcTemplate`, transaction-aware connection.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): tài nguyên JDBC và `JdbcTemplate`.
- [Spring Framework — JdbcTemplate.queryForStream JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): stream cần đóng sau khi sử dụng.