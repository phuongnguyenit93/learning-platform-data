# Data source metrics trong Spring Boot: quan sát connection pool và truy vấn cơ sở dữ liệu

Trong chương **Spring Boot metrics** của module **SPRING_BOOT_OBSERVABILITY**, *data source metrics* là những số đo mô tả tình trạng sử dụng nguồn kết nối cơ sở dữ liệu mà ứng dụng đang quản lý. Với Spring Boot dùng JDBC và connection pool như HikariCP, metrics giúp trả lời: pool có bao nhiêu kết nối bận/rảnh, còn khả năng cấp kết nối không, có thread đang chờ không và số lần timeout khi lấy connection có tăng không.

Đây là mảnh ghép trong observability với **Micrometer Observation, metrics, logs và distributed tracing** để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực. Tuy nhiên, **pool metrics không tự cho biết câu SQL nào chậm**. Muốn kết luận nguyên nhân, cần đối chiếu chúng với thời gian của thao tác nghiệp vụ, truy vấn và transaction, logs, distributed traces và số liệu trên database server.

## 1. DataSource và connection pool đang đo điều gì?

Trong JDBC, `javax.sql.DataSource` là giao diện cung cấp connection tới database. Nhiều ứng dụng Spring Boot sử dụng một implementation có **connection pool** (thường là HikariCP) để tái sử dụng kết nối, tránh phải tạo connection vật lý mới cho mỗi request.

```text
HTTP request -> Service -> Repository / JdbcTemplate / JPA
                              |
                              v
                          DataSource
                              |
                              v
                     HikariCP connection pool
                       |            |
                  kết nối rảnh   kết nối bận
                       \            /
                            Database

Pool metrics: active, idle, max, min, pending, acquire, timeout...
Tín hiệu tầng khác: HTTP latency, business observation, SQL duration,
                    transaction duration, DB locks/CPU/I/O...
```

Một request có thể mất 2 giây dù SQL chỉ chạy 20 ms nếu nó phải chờ 1,8 giây để lấy connection. Ngược lại, pool vẫn còn nhiều connection rảnh nhưng một câu SQL bị chậm do thiếu index hoặc đợi lock. Hai tình huống cần cách xử lý khác nhau.

| Lớp quan sát | Câu hỏi trả lời được | Không thể kết luận chỉ từ lớp đó |
| --- | --- | --- |
| Data source/pool metrics | Bao nhiêu connection bận/rảnh/chờ, pool có cạn không | SQL nào chậm và vì sao chậm |
| HTTP server metrics | Endpoint nào chậm/lỗi, tải tăng khi nào | Độ trễ đến từ việc mượn connection hay chạy SQL |
| Database client spans/metrics (nếu instrument) | Lời gọi DB diễn ra ở bước nào trong trace, mất bao lâu | Tất cả nguyên nhân CPU, I/O, lock phía database |
| Database server metrics | Sessions, locks, CPU, I/O, slow queries | Request nghiệp vụ cụ thể nếu thiếu correlation |
| Logs và exceptions | Timeout, connection leak warning, lỗi mạng/xác thực | Phân phối độ trễ và tỷ lệ lỗi trên toàn bộ request |

Lưu ý: ứng dụng dùng **R2DBC** không nhất thiết có metrics của JDBC `DataSource`. Reactive connection pool có instrumentation và tên metric riêng theo driver/thư viện; không áp dụng nguyên các ví dụ JDBC/HikariCP cho mọi công nghệ database.

## 2. Spring Boot thu thập data source metrics như thế nào?

Spring Boot Actuator có auto-configuration cho các `DataSource` do Spring quản lý. Khi có implementation và metadata provider được hỗ trợ, dữ liệu connection pool được đưa vào Micrometer `MeterRegistry`. HikariCP thường là pool mặc định khi dự án dùng JDBC starter phù hợp và không cấu hình pool khác.

```text
Spring Boot DataSource bean
      |
      +--> DataSource pool metadata
      |          |
      |          +--> jdbc.connections.* --> MeterRegistry
      |                                      |
      |                                      +--> /actuator/metrics
      |                                      +--> Prometheus / OTLP exporter
      |
      +--> HikariCP instrumentation (nếu có)
                 |
                 +--> hikaricp.* --> MeterRegistry
                                        |
                                        +--> Backend / dashboard / alert
```

Hai nhóm tên thường gặp:

- **`jdbc.connections.*`:** số đo chung của pool như `active`, `idle`, `max`, `min` nếu Boot lấy được metadata.
- **`hikaricp.*`:** số đo chi tiết của HikariCP như số thread chờ, thời gian acquire/usage, số timeout hoặc creation time khi Hikari metrics được cấu hình.

Không phải mọi Spring Boot version, `DataSource` tùy biến hoặc cách tạo pool đều tự sinh đủ hai nhóm metrics. Một `DataSource` bị bọc bằng proxy, pool không được hỗ trợ, registry được thay thế hoặc thiếu dependency có thể khiến meter vắng mặt. **Kiểm tra metrics thực tế của phiên bản đang chạy** trước khi thiết kế cảnh báo.

Tên trong `/actuator/metrics` là tên **logic của Micrometer**. Với Prometheus, dấu chấm thường chuyển thành gạch dưới; counter, timer và histogram có thể tạo các series có hậu tố như `_total`, `_seconds_count`, `_seconds_sum`, `_bucket`. Không coi tên Actuator và tên PromQL là luôn giống nhau.

## 3. Thiết lập ví dụ với Spring Boot, Actuator và HikariCP

Một dự án Spring Boot dùng JDBC/PostgreSQL có thể khai báo các dependency Maven sau. Ví dụ giả định đã sử dụng Spring Boot parent/BOM để quản lý phiên bản:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Nếu dự án đã dùng JPA starter, không nhất thiết thêm JDBC starter chỉ để có metrics. Cấu hình `application.yml` minh họa:

```yaml
spring:
  application:
    name: orders-service
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 16
      minimum-idle: 4
      connection-timeout: 30000 # milliseconds

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
```

Giải thích:

1. Các biến môi trường cấp username/password; không nhúng credentials vào file thực tế hoặc log. URL `localhost` chỉ dành cho chạy thử.
2. `pool-name` giúp xác định pool trong các nhãn Hikari; nhãn cụ thể có thể là `pool` hoặc `name` tùy meter/implementation. Xác minh trong endpoint.
3. `maximum-pool-size: 16` và `minimum-idle: 4` là **con số ví dụ**, không phải giá trị tối ưu chung. Phải tính theo số replica, giới hạn connection của DB, tải và thời gian giữ connection.
4. `connection-timeout: 30000` là thời gian tối đa chờ lấy connection trong cấu hình Hikari tương ứng (30 giây), **không phải SQL query timeout**.
5. Endpoint metrics/Prometheus chỉ nên mở với phạm vi mạng quản trị hoặc bảo vệ truy cập thích hợp. Không công bố toàn bộ Actuator endpoints ra Internet.

Trong cấu hình trên, `${DB_USER}` và `${DB_PASSWORD}` là các placeholder được Spring resolve từ môi trường; `${spring.application.name}` tham chiếu cấu hình tên ứng dụng. Không ghi thông tin xác thực thật vào tài liệu hoặc telemetry.

## 4. Các chỉ số quan trọng và cách diễn giải

### 4.1. Nhóm JDBC pool metadata

Các tên logic Micrometer phổ biến nếu Spring Boot đọc được metadata:

| Meter | Loại thông thường | Ý nghĩa |
| --- | --- | --- |
| `jdbc.connections.active` | Gauge | Số connection đã được mượn/đang dùng trong pool |
| `jdbc.connections.idle` | Gauge | Số connection rảnh có thể cấp |
| `jdbc.connections.max` | Gauge | Cận trên số connection theo cấu hình/báo cáo của pool |
| `jdbc.connections.min` | Gauge | Cận dưới số connection theo cấu hình/báo cáo của pool |

Một số metadata provider không cung cấp được tất cả giá trị, hoặc dùng giá trị đặc biệt khi giới hạn không biết. Không tính tỷ lệ sử dụng khi `max` không hợp lệ.

**Active cao tự nó chưa có nghĩa pool đang nghẽn.** Pool có thể sử dụng 12/16 connections nhưng vẫn cấp kết nối ngay. Dấu hiệu đáng điều tra hơn là `active` sát `max`, `idle` thấp, `pending` kéo dài và số timeout hoặc thời gian acquire tăng.

### 4.2. Nhóm HikariCP

Khi Hikari metrics hoạt động, những meter thường gặp với tiền tố `hikaricp.connections` gồm:

| Meter thường gặp | Hình thức | Ý nghĩa vận hành |
| --- | --- | --- |
| `hikaricp.connections.active` | Gauge | Connection đang được mượn |
| `hikaricp.connections.idle` | Gauge | Connection nhàn rỗi |
| `hikaricp.connections.pending` | Gauge | Số thread đang chờ pool cấp connection |
| `hikaricp.connections.max` / `min` | Gauge | Giới hạn cấu hình của pool |
| `hikaricp.connections.acquire` | Timer | Thời gian **chờ đến khi lấy được connection** |
| `hikaricp.connections.usage` | Timer | Thời gian ứng dụng **giữ một connection** |
| `hikaricp.connections.creation` | Timer | Thời gian tạo connection vật lý mới |
| `hikaricp.connections.timeout` | Counter | Số lần không lấy được connection trước hạn chờ |

Tên/đơn vị/type và labels thực sự xuất ở backend phụ thuộc version Hikari, Micrometer registry và exporter; bảng trên là bản đồ khái niệm, cần đối chiếu dữ liệu chạy thật.

**Acquire không đồng nghĩa query latency.** Chờ connection lâu có thể do pool cạn hoặc tạo kết nối mới chậm. **Usage cũng không đồng nghĩa SQL duration:** connection có thể bị giữ trong transaction, chờ ứng dụng, gọi mạng hay xử lý khác giữa các truy vấn.

Một chuỗi nghẽn giả định: transaction mở quá lâu → `usage` tăng → `active` chạm `max` → `pending` tăng → `acquire` tăng → `timeout` tăng. Đây là giả thuyết cần kiểm tra qua traces, DB sessions/locks và logs, không phải kết luận chắc chắn chỉ từ metrics.

## 5. Xem metrics qua Actuator và exporter

Sau khi ứng dụng khởi động, thử các endpoint đã được cho phép:

```bash
# Liệt kê tên metrics mà Actuator biết:
curl -s http://localhost:8080/actuator/metrics

# Xem một metric logic, nếu đã tồn tại:
curl -s http://localhost:8080/actuator/metrics/jdbc.connections.active

# Xem Hikari pending, nếu instrumentation có sẵn:
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.pending

# Kiểm tra tên xuất sau conversion cho Prometheus:
curl -s http://localhost:8080/actuator/prometheus
```

Endpoint `/actuator/metrics/<meter-name>` thường trả JSON gồm `measurements` và `availableTags`. Đáp ứng **minh họa về cấu trúc**, số liệu và tag có thể khác:

```json
{
  "name": "jdbc.connections.active",
  "description": "Active connections",
  "measurements": [
    { "statistic": "VALUE", "value": 11.0 }
  ],
  "availableTags": [
    { "tag": "name", "values": ["orders"] }
  ]
}
```

Một số series Prometheus có thể trông giống:

```text
jdbc_connections_active{application="orders-service",name="orders"} 11.0
jdbc_connections_max{application="orders-service",name="orders"} 16.0
```

Tag `name="orders"` chỉ là ví dụ. Hikari có thể sử dụng tag `pool` trong metrics riêng. **Luôn đọc bộ labels thực tế** để tránh dashboard sai khi nhiều pool hoặc replica.

Nếu endpoint không truy cập được, kiểm tra dependency, cấu hình exposure, port và bảo mật. Nếu endpoint hoạt động nhưng không có meter, kiểm tra `DataSource` bean, loại pool, khả năng đọc metadata, registry và `MeterFilter` trước khi tự thêm metric thủ công.

## 6. Dashboard và truy vấn PromQL

Sau khi xác nhận Prometheus xuất đúng tên và nhãn, có thể xây các biểu đồ sau.

### Tỷ lệ sử dụng connection pool

```promql
jdbc_connections_active / clamp_min(jdbc_connections_max, 1)
```

Biểu thức cho tỷ lệ của **các series khớp cùng labels**; nhân 100 để ra phần trăm. Nếu active/max có labels khác nhau, cần sửa vector matching. Pool không có giá trị `max` đáng tin cậy phải được loại khỏi cảnh báo tỷ lệ này. Đừng lấy trung bình phần trăm của hai pool kích thước khác nhau rồi coi là mức sử dụng toàn hệ thống.

### Số thread chờ connection lớn nhất trong 5 phút

```promql
max_over_time(hikaricp_connections_pending[5m])
```

Pending thoáng qua khi tải tăng khác pending kéo dài nhiều phút. Ngưỡng alert cần dựa vào load, scrape interval và tác động thật lên HTTP latency/error.

### Tốc độ timeout khi mượn connection

```promql
rate(hikaricp_connections_timeout_total[5m])
```

Đây là ví dụ khi exporter chuyển counter `hikaricp.connections.timeout` thành series có hậu tố `_total`. Tên xuất khác nhau ở một số stack; xác minh bằng `/actuator/prometheus` trước khi áp dụng.

### Acquire p95 nếu có histogram buckets

```promql
histogram_quantile(
  0.95,
  sum by (le, pool) (
    rate(hikaricp_connections_acquire_seconds_bucket[5m])
  )
)
```

Truy vấn này **chỉ là minh họa**: phải tồn tại histogram bucket thực sự, label `pool` và tên `..._seconds_bucket` như giả định. Không thể tính p95 tổng hợp chính xác chỉ từ `count` và `sum` khi histogram không được cấu hình. Việc bật histogram còn ảnh hưởng số time series và chi phí.

Dashboard tối thiểu nên đặt cùng nhau HTTP RPS/p95/error rate; pool active/idle/max/pending; timeout rate; acquire/usage latency khi có; CPU/threads/heap của JVM và tình trạng database server.

## 7. Phân tích các mẫu sự cố

| Dấu hiệu | Giả thuyết | Kiểm chứng thêm |
| --- | --- | --- |
| `active ≈ max`, pending cao, timeout tăng | Pool cạn hoặc connection giữ quá lâu | HTTP latency, acquire/usage, DB sessions, transactions, thread dump |
| Acquire tăng nhưng usage không tăng | Chờ cấp connection hoặc tạo connection mới chậm | Creation time, idle, pending, network/database connectivity |
| Usage tăng mạnh, active cao | Transaction lâu, query chậm hoặc lock wait | Slow query logs, DB locks, JDBC spans, transaction boundaries |
| Idle nhiều, HTTP latency tăng | Nút thắt có thể ngoài pool | CPU/GC, business code, remote API, distributed traces |
| Timeout đi kèm lỗi “connection is not available” | Hết hạn chờ mượn connection | Connection timeout config, queue, DB tình trạng |
| Connection creation tăng, pool giảm đột ngột | DB failover, connection bị đóng/tạo lại | Network, DB restart, validation, idle timeout |
| Không thấy jdbc.connections mặc dù vẫn truy vấn DB | Meter chưa bind hoặc bị filter/exporter bỏ | Pool metadata, proxy DataSource, Actuator dependencies |

`active + idle` thường xấp xỉ tổng connection hiện có, nhưng có thể biến đổi khi pool tạo/đóng connections; không biến quan hệ này thành invariant tuyệt đối cho mọi implementation.

### Tình huống: pool nhỏ so với tải

Khi lưu lượng tăng, active chạm max, pending tăng, acquire p95 tăng; database vẫn còn tài nguyên. Tăng pool **có thể** giúp nếu database đủ khả năng và các connections không bị giữ bất thường. Nhưng phải tính thêm số replica và ngân sách connections chung.

### Tình huống: transaction rộng

Một phương thức `@Transactional` thực hiện gọi API bên ngoài trong khi transaction còn mở có thể giữ connection lâu, tùy cách JDBC/JPA lấy và giải phóng connection. Chỉ tăng `maximum-pool-size` có thể dời nút thắt và làm DB chịu tải nặng hơn. Cần xem transaction boundary, lock, slow query và tách công việc không cần transaction.

### Tình huống: nghi ngờ connection leak

Khi code JDBC mượn connection nhưng quên giải phóng, active có thể duy trì cao dù traffic giảm. HikariCP có khả năng phát log cảnh báo nghi ngờ leak khi connection bị giữ quá lâu, nhưng cảnh báo đó **không chứng minh đã có leak**; transaction hợp lệ nhưng chậm cũng có thể bị báo. Phải kiểm tra code, resource lifecycle, thread dump và database.

## 8. Liên kết data source metrics với tracing và logs

Pool metrics biểu diễn tình trạng của **một pool/instance theo thời gian**. Distributed tracing cho biết **đường đi một request được lấy mẫu**.

```text
HTTP: POST /checkout
  ├─ business: inventory.reserve
  │    └─ JDBC/database client span (nếu có instrumentation)
  └─ business: payment.authorize
       └─ HTTP client payment provider

Đồng thời: pool active=16, idle=0, pending=8, timeout tăng
```

Để điều tra một request chậm:

1. Xác định khoảng thời gian HTTP p95 hoặc lỗi tăng.
2. Đối chiếu pool active/idle/pending, acquire/usage và timeout của **đúng instance/pool**.
3. Mở trace ở cùng khoảng thời gian; kiểm tra span nghiệp vụ và DB client span nếu tracing integration được bật.
4. Dùng `traceId`/`spanId` trong logs nếu log correlation và MDC đã được cấu hình. Không tự lấy request ID làm metric label.
5. Đối chiếu DB sessions, lock waits, slow queries và CPU/I/O của database.

Với việc xử lý qua executor/queue/service khác, cần **context propagation** phù hợp. Mở một observation scope trên HTTP thread không tự động chuyển trace sang mọi worker. Sampling có thể khiến một số trace không xuất hiện trong khi pool metrics vẫn được ghi.

### Ví dụ: custom Observation cho thao tác sử dụng JdbcTemplate

Khi muốn đo riêng thời gian của một **bước nghiệp vụ**, có thể thêm observation mang ngữ nghĩa khác với pool metrics:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {
    private final JdbcTemplate jdbcTemplate;
    private final ObservationRegistry observationRegistry;

    public OrderLookupService(
            JdbcTemplate jdbcTemplate,
            ObservationRegistry observationRegistry) {
        this.jdbcTemplate = jdbcTemplate;
        this.observationRegistry = observationRegistry;
    }

    public long countPendingOrders() {
        Long count = Observation
                .createNotStarted("orders.pending_count.lookup",
                        observationRegistry)
                .lowCardinalityKeyValue("operation", "count_pending")
                .observe(() -> jdbcTemplate.queryForObject(
                        "SELECT COUNT(*) FROM orders WHERE status = ?",
                        Long.class,
                        "PENDING"));

        return count == null ? 0L : count;
    }
}
```

Ví dụ này dùng tên observation ổn định và query có bind parameter. Nếu metric handler được bật, observation có thể đo số lần và **thời lượng thao tác**; giá trị `count` trả về từ SQL **không tự biến thành gauge số đơn đang chờ**. Không đưa order ID, email, SQL text có parameters hoặc DB password vào low-cardinality tags.

Nếu đã có database client tracing, custom observation chỉ hữu ích khi nó biểu diễn **ranh giới nghiệp vụ**; tránh tạo hai timer cùng phạm vi và cùng ý nghĩa. Khi cần số đơn đang chờ như một gauge, chọn nguồn dữ liệu nhẹ thích hợp, tránh chạy `COUNT(*)` nặng vào **mỗi lần scrape** khiến chính observability làm database quá tải.

## 9. Nhiều DataSource, tags và cardinality

Một service có thể có pool đọc và pool ghi, hoặc nhiều DataSource đến những database khác nhau. Mỗi pool nên có một tag nhận diện **ổn định, giá trị hữu hạn**, chẳng hạn `pool=orders-read` và `pool=orders-write`. Với `jdbc.connections.*`, nhãn nhận diện có thể theo bean `DataSource`; với Hikari-specific metrics có thể theo pool name. Luôn kiểm tra output.

| Thiết kế | Đánh giá | Lý do |
| --- | --- | --- |
| Một pool đọc và một pool ghi được đặt tên cố định | Phù hợp khi kiến trúc yêu cầu | Phân tích capacity, latency và timeout theo từng pool |
| Mỗi request tạo pool có tên chứa request ID | Tránh | Tốn connection và gây nổ cardinality |
| Tag pool chứa tenant ID không có giới hạn | Tránh trên metric labels | Nhiều series theo tenant, chi phí lớn |
| Tags `application`, `environment`, `pool` có tập giá trị quản lý | Phù hợp | Có thể lọc dashboard và phân trách nhiệm |
| Raw JDBC URL, username/password làm tag | Tránh | Rò rỉ thông tin, độ dài và cardinality không ổn định |

Khi pool bị bọc qua proxy, metadata provider có thể không nhận diện pool gốc. Không vội tự tạo `Gauge` trùng tên với metric auto-configuration: có thể gây meter collision hoặc hai phép đo trùng nghĩa.

Hợp đồng về tên và tags là một phần của **telemetry schema**. Nếu đổi từ `name=orders` sang `pool=orders-pool`, dashboard/alert/PromQL dùng tag cũ có thể ngừng hoạt động. Cần quản lý thay đổi như với một API.

## 10. Cấu hình connection pool dựa trên số liệu

`maximum-pool-size`, `minimum-idle` và `connection-timeout` không có giá trị tối ưu cho mọi hệ thống. Hãy xem:

- **Số replica:** 10 replica × 20 connections tối đa có thể lên đến 200 DB connections, chưa tính service khác và kết nối quản trị.
- **Khả năng database:** số sessions cho phép, CPU, I/O, memory, lock contention và giới hạn của proxy.
- **Thời gian giữ connection:** transaction càng dài thì cùng throughput cần nhiều connections hoạt động đồng thời hơn.
- **Burst và concurrency:** tải đến theo cụm có thể sinh pending tạm thời; phân biệt burst với nghẽn kéo dài.
- **Retry policy:** nhiều retry đồng thời sau timeout có thể làm hàng chờ trầm trọng thêm.

Một ước lượng theo Little's Law: **số kết nối bận trung bình ≈ số lượt mượn connection mỗi giây × thời gian giữ connection trung bình (giây)**, giả sử hệ thống tương đối ổn định và đo đúng phạm vi.

Ví dụ, 100 lần mượn connection/giây với usage trung bình 0,08 giây tương ứng khoảng **8 connections bận trung bình**. Điều đó **không có nghĩa** pool size 8 luôn đủ: p95/p99 usage, burst, số instance, DB capacity và mức dự phòng đều quan trọng. Pool quá lớn có thể làm database chậm thêm thay vì giải quyết vấn đề.

Khi chỉnh kích thước pool, so sánh trước/sau HTTP RPS/p95/error, pool active/idle/pending, acquire/usage/timeout và số liệu DB. Đừng dựa vào một gauge đơn lẻ.

## 11. Những lỗi diễn giải thường gặp

**Nhầm active với SQL concurrency.** Connection được mượn có thể đang chờ hoặc nằm trong transaction mà không chạy SQL. `active` không phải số query đang thực thi trên server.

**Nhầm acquire với query latency.** Acquire đo chờ cấp connection, không đo trực tiếp thực thi SQL.

**Kết luận leak chỉ vì active cao.** Transaction dài, spike traffic và slow query có biểu hiện tương tự; cần thêm logs, thread dump và DB sessions.

**Coi gauge là counter.** `jdbc.connections.active` là giá trị tức thời khi được đọc/scrape, không phải tổng số connections được mượn từ khi khởi động.

**Gộp nhiều pool thiếu nhãn.** Tỷ lệ active/max phải so cùng pool và instance; gộp pool kích thước khác nhau có thể che khuất một pool đang cạn.

**Gắn high-cardinality tags.** Không dùng order ID, user ID, raw URL/query string, exception message hoặc trace ID làm metric labels. Dùng logs/traces có kiểm soát để điều tra một giao dịch.

**Đăng ký metrics chồng chéo.** Actuator, Hikari instrumentation và custom code có thể cùng đo một đại lượng. Kiểm kê meter names/types/tags trước khi thêm meter mới.

**Không phân biệt thiếu meter với thiếu dữ liệu xuất.** Meter tồn tại trong JVM không đồng nghĩa exporter đã gửi, scraper đã thu hoặc backend đã lưu. Kiểm tra từng bước.

## 12. Quy trình kiểm chứng

Trước khi tin dashboard hoặc tuning, hãy xác minh lần lượt:

1. **Instrumentation:** `DataSource` có là Spring bean không, pool thuộc loại nào, Actuator và registry có dependency phù hợp không?
2. **Tên metric:** `/actuator/metrics` có `jdbc.connections.*` và `hikaricp.*` nào? Tags nhận diện pool tên gì?
3. **Hành vi nền:** khi tải thấp, active/idle/pending phản ánh hợp lý trạng thái pool thực tế không?
4. **Hành vi dưới tải có kiểm soát:** khi concurrent requests tăng, active/pending/acquire có thay đổi phù hợp không?
5. **Đường lỗi:** khi hết hạn cấp connection, timeout metric, exception và logs có tương quan không?
6. **Exporter:** tên sau conversion, bộ labels và scrape/publish interval có đúng không?
7. **Correlations:** trace và log có liên hệ với HTTP request chậm không, context propagation có hoạt động qua async/service?
8. **Alerts:** ngưỡng/cửa sổ phản ánh tác động người dùng, có tách từng pool/instance và tránh false-positive vì burst không?

| Kịch bản | Dấu hiệu pool mong đợi | Kiểm chứng ngoài pool |
| --- | --- | --- |
| Ít request | Active thấp, idle tùy minimum idle | DB reachable, ứng dụng sẵn sàng |
| Burst truy vấn ngắn | Active tăng rồi giảm | HTTP latency bình thường |
| Pool cạn | Active gần max, pending tăng nếu có meter | Acquire và HTTP latency tăng |
| Connection timeout | Timeout counter tăng nếu có | Exception/log tương ứng |
| SQL đợi lock | Usage/active có thể tăng | DB lock waits, query tracing |
| Trace sampled out | Pool metric vẫn có thể ghi | Không nhầm sampling với thiếu meter |
| Sau nâng cấp Hikari/Micrometer | Tên/labels có thể đổi | Xác minh lại exporter và dashboard |
| Thêm DataSource | Có thêm các series theo pool nếu được hỗ trợ | Cardinality và tên không va chạm |

Không nên tạo tải lớn trên production chỉ để quan sát; dùng môi trường thử nghiệm phù hợp với tải và quyền kiểm soát.

## 13. Bài thực hành: checkout chậm do đâu?

Giả sử một dịch vụ Spring Boot có HikariCP tối đa **16 connections**. Khi tải tăng, dashboard cho thấy:

```text
HTTP checkout p95:              2.4 s  (trước đó: 0.3 s)
jdbc.connections.active:        16
jdbc.connections.idle:           0
jdbc.connections.max:           16
hikaricp.connections.pending:    9
Connection acquire p95:         1.7 s
Connection usage p95:           0.45 s
Connection timeout:             đang tăng
```

*Các số liệu trên là giả định để luyện phân tích; tên, đơn vị và labels phải xác minh theo registry thực tế.*

**Câu hỏi:** Có đủ bằng chứng để khẳng định “SQL chậm, phải tăng `maximum-pool-size` lên 64” không?

**Phân tích:** Chưa đủ. Có bằng chứng pool đang chịu sức ép cấp connection: active bằng max, idle bằng 0, pending cao và acquire p95 tăng. Nhưng nguyên nhân có thể là transaction rộng, SQL/lock lâu, connection không được giải phóng, database quá tải hoặc pool thực sự nhỏ so với concurrency.

**Đề xuất điều tra:**

1. So trace nghiệp vụ checkout với thời gian query/transaction và logs timeout.
2. Kiểm tra DB sessions, slow queries, locks và transaction boundaries.
3. So tổng connections của mọi replica với ngân sách database.
4. Nếu DB còn năng lực và pool đúng là giới hạn, thử tăng có kiểm soát rồi quan sát các chỉ số trước/sau.
5. Nếu DB đang quá tải, ưu tiên tối ưu SQL, index, phạm vi transaction hoặc giới hạn concurrency; tăng pool có thể làm sự cố nghiêm trọng hơn.

**Điểm cần nhớ:** Data source metrics cho biết khả năng **cấp phát và sử dụng connections**; business observations, SQL diagnostics, logs và distributed traces giúp xác định **công việc nào đang giữ connections và vì sao request chậm**. Dùng cả những tín hiệu này, bảo đảm context propagation và kiểm soát tags/cardinality/exporter, để đưa ra quyết định vận hành có căn cứ.
