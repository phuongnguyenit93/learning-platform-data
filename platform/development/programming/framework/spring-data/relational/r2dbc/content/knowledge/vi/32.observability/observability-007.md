# Phân biệt health check, readiness và khả năng phục vụ tải thật

Trong ứng dụng Spring Data Relational R2DBC, một endpoint health trả về `UP` không có nghĩa hệ thống chắc chắn phục vụ được mọi request hoặc chịu được tải production. Health check thường xác nhận một số thành phần cơ bản còn hoạt động tại thời điểm kiểm tra. Readiness trả lời câu hỏi instance có nên nhận traffic ngay lúc này hay không. Khả năng phục vụ tải thật lại cần được đánh giá bằng latency, throughput, error rate, mức sử dụng connection pool, tài nguyên database và thử nghiệm dưới tải đại diện.

Ba khái niệm này liên quan nhưng có mục đích khác nhau. Nếu dùng một truy vấn database nặng làm liveness probe, Kubernetes có thể restart toàn bộ pod khi database chậm, dù process vẫn sống và restart không sửa được nguyên nhân. Nếu readiness chỉ kiểm tra process đã khởi động, pod có thể nhận traffic trước khi R2DBC pool hoặc schema sẵn sàng. Nếu chỉ nhìn health endpoint để kết luận capacity, hệ thống có thể báo `UP` trong khi pool đã gần cạn và request thực tế timeout.

Spring Boot Actuator cung cấp health contributors và các probe group như liveness/readiness. Trong ứng dụng reactive, health indicator có thể trả `Mono<Health>`. R2DBC còn cần quan sát connection acquisition, query latency, pool saturation, timeout, cancellation và lỗi driver. Health endpoint nên ngắn, rẻ và có timeout; khả năng chịu tải cần được đánh giá bằng metrics, tracing, load test và SLO.

## 1. Ba câu hỏi khác nhau

| Khái niệm | Câu hỏi cần trả lời | Người tiêu thụ kết quả | Ví dụ |
| --- | --- | --- | --- |
| Health check | Một thành phần hoặc ứng dụng có đang ở trạng thái hoạt động cơ bản không? | Monitoring, operator, dashboard | Actuator `/actuator/health` |
| Readiness | Instance này có nên nhận request mới vào lúc này không? | Load balancer, Kubernetes Service/Ingress, orchestrator | `/actuator/health/readiness` |
| Khả năng phục vụ tải thật | Hệ thống có đáp ứng workload thực tế trong giới hạn latency/error/capacity không? | SRE, vận hành, capacity planning, release gate | Load test, metrics, traces, SLO |

Một process có thể sống nhưng chưa sẵn sàng: ứng dụng đang chạy migration, khởi tạo cache bắt buộc hoặc chưa thiết lập được kết nối cần thiết. Một process cũng có thể sẵn sàng nhận traffic nhưng chưa đủ capacity cho một đợt tải đột biến. Ngược lại, một probe có thể thất bại do dependency đang gián đoạn trong khi restart process không mang lại lợi ích.

Health check là tín hiệu trạng thái. Readiness là quyết định định tuyến traffic. Capacity là thuộc tính của toàn bộ hệ thống dưới một workload và thời gian quan sát xác định. Không nên dùng một endpoint duy nhất để thay thế cả ba.

## 2. Health check là gì?

Health check là phép kiểm tra có phạm vi rõ ràng nhằm xác định ứng dụng hoặc một dependency có thể thực hiện một thao tác cơ bản hay không. Trong Spring Boot, Actuator tổng hợp trạng thái từ các `HealthIndicator` hoặc `ReactiveHealthIndicator`.

Một health check có thể kiểm tra:

- Application context đã khởi tạo.
- Một dependency bắt buộc có thể kết nối.
- Database chấp nhận một truy vấn kiểm tra nhẹ.
- Một hệ thống message hoặc cache thiết yếu có thể truy cập.
- Một trạng thái nội bộ do ứng dụng công bố.

Health check thường là một phép kiểm tra tức thời, không phải một bài kiểm thử chức năng toàn diện. Ví dụ, một truy vấn `SELECT 1` thành công chứng minh connection có thể thực thi một câu SQL đơn giản tại thời điểm đó. Nó không chứng minh mọi query nghiệp vụ, mọi bảng, mọi quyền truy cập, mọi transaction hay mọi request đồng thời đều thành công.

### Health status trong Spring Boot

Actuator thường sử dụng các trạng thái:

| Status | Ý nghĩa khái quát |
| --- | --- |
| `UP` | Thành phần được kiểm tra đang hoạt động theo tiêu chí của indicator |
| `DOWN` | Thành phần không hoạt động hoặc phép kiểm tra thất bại |
| `OUT_OF_SERVICE` | Thành phần được chủ động đánh dấu không phục vụ |
| `UNKNOWN` | Không đủ thông tin để kết luận trạng thái |

Trạng thái tổng hợp của endpoint phụ thuộc status aggregator và cấu hình mapping. Với cấu hình HTTP mặc định phổ biến, `DOWN` và `OUT_OF_SERVICE` được ánh xạ thành HTTP 503; `UP` trả HTTP 200. Hãy kiểm tra `management.endpoint.health.status.http-mapping` nếu ứng dụng tùy chỉnh mapping.

### Health endpoint không phải endpoint nghiệp vụ

Không nên biến health endpoint thành một API thực hiện toàn bộ nghiệp vụ, ví dụ tạo rồi xóa một order, gửi message thật hoặc gọi hàng loạt dịch vụ ngoài. Những thao tác đó có side effect, tốn tài nguyên và có thể làm hệ thống xấu đi khi đang gặp sự cố.

Một health check tốt có các đặc điểm:

- Nhanh và có timeout hữu hạn.
- Ít hoặc không có side effect.
- Không đọc lượng dữ liệu lớn.
- Có tiêu chí UP/DOWN rõ ràng.
- Không trả secret, connection string hoặc dữ liệu nhạy cảm.
- Không tạo tải đáng kể khi được gọi lặp lại bởi nhiều probe.

## 3. Liveness: process còn sống và có thể tiếp tục chạy không?

Liveness trả lời câu hỏi: process có còn hoạt động theo cách mà restart có thể giúp phục hồi hay không? Với Spring Boot, availability state có thể biểu diễn trạng thái liveness qua `LivenessState`.

Liveness thường nên phản ánh tình trạng bên trong process:

- Application chưa bị đánh dấu `BROKEN`.
- Runtime vẫn có thể xử lý các tác vụ cơ bản.
- Không có trạng thái nội bộ không thể phục hồi mà restart là hành động phù hợp.

Liveness không nên phụ thuộc trực tiếp vào database, Redis, message broker hoặc API bên ngoài. Nếu database tạm thời mất kết nối, restart tất cả pod thường không làm database khỏe hơn. Nếu tất cả pod đồng loạt restart, chúng có thể tạo thêm connection storm đúng lúc database đang phục hồi.

### Vì sao không đưa database vào liveness?

Giả sử database bảo trì trong 30 giây. Nếu liveness gọi `SELECT 1` và trả DOWN, Kubernetes có thể restart các pod. Sau khi database phục hồi, nhiều pod cùng khởi động, tạo pool mới và đồng loạt mở connection. Điều này có thể làm database quá tải thêm.

Liveness nên dùng để phát hiện process bị kẹt hoặc trạng thái nội bộ cần restart. Dependency bên ngoài nên được quan sát qua readiness/metrics/alerts theo chính sách phù hợp.

## 4. Readiness: instance có nên nhận traffic không?

Readiness trả lời câu hỏi: nếu load balancer gửi một request mới tới instance này ngay bây giờ, instance có thể xử lý loại request mà nó được giao không?

Một instance chưa ready có thể đang:

- Khởi tạo các thành phần bắt buộc.
- Chạy bước warm-up cần thiết.
- Chưa có credential/configuration bắt buộc.
- Mất kết nối tới database bắt buộc cho phần lớn request.
- Đang drain để chuẩn bị shutdown.
- Được chủ động đánh dấu `REFUSING_TRAFFIC`.

Khi readiness thất bại, orchestrator hoặc load balancer ngừng gửi traffic mới tới instance đó theo cơ chế health check. Process vẫn có thể sống và tiếp tục xử lý công việc nền hoặc hoàn tất request đang chạy.

### Readiness phụ thuộc vào vai trò của instance

Không phải mọi dependency đều cần có mặt trong readiness. Nếu service chỉ có một số endpoint cần Redis nhưng vẫn phục vụ phần lớn request khi Redis không khả dụng, đưa Redis vào readiness có thể loại bỏ một instance vẫn còn hữu ích. Nếu database là dependency bắt buộc cho mọi request quan trọng, readiness có thể cần phản ánh trạng thái database.

Hãy xác định:

1. Request nào instance được kỳ vọng phục vụ?
2. Dependency nào là bắt buộc cho các request đó?
3. Nếu dependency lỗi, ứng dụng có fallback hoặc chế độ degraded hợp lệ không?
4. Nếu tất cả instance cùng mất dependency, việc đánh dấu tất cả unready có giúp ích không?
5. Probe có timeout và tần suất phù hợp không?

Readiness nên phản ánh khả năng tiếp nhận traffic theo hợp đồng của service, không phải trạng thái của mọi hệ thống mà ứng dụng biết tới.

## 5. Startup probe và thời gian khởi động

Startup probe giải quyết trường hợp ứng dụng mất nhiều thời gian để khởi động. Khi Kubernetes dùng startup probe, liveness và readiness probe chưa được đánh giá theo cách thông thường cho tới khi startup probe thành công.

Startup probe hữu ích khi ứng dụng:

- Khởi tạo Spring context lớn.
- Chạy initialization bắt buộc.
- Nạp metadata hoặc cấu hình từ nguồn bên ngoài.
- Warm-up thành phần cần thiết trước khi phục vụ.
- Có thời gian khởi động biến động giữa các môi trường.

Không nên tăng liveness `failureThreshold` quá lớn chỉ để che startup lâu nếu startup probe là cơ chế phù hợp hơn. Startup và liveness có mục đích khác nhau: startup cho thời gian khởi động; liveness phát hiện process cần restart sau khi đã khởi động.

Spring Boot có availability state và Actuator probe groups cho liveness/readiness. Startup probe của Kubernetes có thể sử dụng endpoint liveness hoặc endpoint health được thiết kế riêng cho giai đoạn khởi động, tùy cấu hình deployment.

## 6. Spring Boot Actuator và probe groups

Thêm Actuator vào ứng dụng Spring Boot để expose health endpoint:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
```

Hoặc Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Trong môi trường cần Kubernetes probes, có thể bật probe support và khai báo group rõ ràng:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
```

Các endpoint thường dùng:

| Endpoint | Mục đích |
| --- | --- |
| `/actuator/health` | Health tổng hợp |
| `/actuator/health/liveness` | Probe liveness |
| `/actuator/health/readiness` | Probe readiness |

Trong Kubernetes, Spring Boot có thể tự bật probe support khi nhận diện môi trường Kubernetes ở các phiên bản hỗ trợ. Khai báo tường minh giúp cấu hình deployment dễ đọc và có thể kiểm tra hơn. Tên property và hành vi chi tiết cần khớp Spring Boot version của dự án.

### Thêm đường dẫn probe trên cổng ứng dụng

Nếu management endpoint chạy trên một cổng riêng, Kubernetes có thể kiểm tra cổng management thành công trong khi server chính không còn nhận request đúng cách. Có thể bật additional probe paths trên main server port:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Spring Boot cung cấp các đường dẫn `/livez` và `/readyz` trên cổng ứng dụng khi tính năng này được hỗ trợ. Kiểm tra endpoint thực tế của phiên bản đang dùng và cấu hình probe cùng port mà traffic ứng dụng sử dụng.

Không expose mọi Actuator endpoint công khai chỉ để Kubernetes đọc health. Chỉ expose endpoint cần thiết, giới hạn network access và bảo vệ các endpoint chứa thông tin vận hành.

## 7. Cấu hình readiness có bao gồm database R2DBC không?

Spring Boot có thể tự cấu hình health contributor cho database khi nhận diện `ConnectionFactory`/R2DBC driver phù hợp. Trong nhiều cấu hình, component database có ID `db`; cần kiểm tra `/actuator/health` và component names của phiên bản ứng dụng thực tế.

Nếu database là dependency bắt buộc để phục vụ request, có thể đưa component database vào readiness group:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

Trong cấu hình này:

- Liveness phản ánh availability state của process.
- Readiness phản ánh availability state và trạng thái database contributor.
- Database contributor DOWN có thể làm readiness group DOWN và trả mã HTTP không thành công theo status mapping.

Chỉ đưa `db` vào readiness nếu database thực sự bắt buộc cho việc phục vụ traffic. Nếu service có chế độ degraded hoặc chỉ một số endpoint cần database, cần cân nhắc indicator/readiness policy chính xác hơn.

### Health contributor `db` kiểm tra điều gì?

Database health indicator thường thực hiện một phép kiểm tra kết nối/validation nhẹ theo implementation của Spring Boot và driver. Nó không chạy toàn bộ query nghiệp vụ, không đo throughput và không kiểm tra khả năng chịu tải. Cách lấy connection, câu lệnh validation và timeout có thể khác theo version.

Nếu cần một phép kiểm tra riêng, hãy tạo custom `ReactiveHealthIndicator` cho dependency cụ thể. Tránh tạo thêm một query check nếu built-in contributor đã đáp ứng đúng mục đích.

## 8. Custom reactive health indicator cho R2DBC

Trong trường hợp cần kiểm tra một điều kiện cụ thể hơn built-in contributor, có thể triển khai `ReactiveHealthIndicator`. Ví dụ sau chạy một truy vấn nhẹ và có timeout:

```java
import java.time.Duration;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("r2dbcReadiness")
public class R2dbcReadinessHealthIndicator
        implements ReactiveHealthIndicator {

    private final DatabaseClient databaseClient;

    public R2dbcReadinessHealthIndicator(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Mono<Health> health() {
        return databaseClient.sql("SELECT 1")
                .fetch()
                .first()
                .map(row -> Health.up().build())
                .switchIfEmpty(Mono.just(
                        Health.down()
                                .withDetail("reason", "No result returned")
                                .build()
                ))
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(error -> Mono.just(
                        Health.down()
                                .withDetail("cause", error.getClass().getSimpleName())
                                .build()
                ));
    }
}
```

Đây là ví dụ minh họa cho Spring Boot Actuator và Spring Data R2DBC; imports/API cần khớp version. `DatabaseClient.fetch().first()` trả publisher chứa hàng đầu tiên; `SELECT 1` thông thường phải trả một hàng. Nếu source empty hoặc query lỗi/timeout, indicator trả DOWN.

Thêm custom indicator vào readiness group:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,r2dbcReadiness
```

Nếu đã có built-in `db` contributor và nó đủ đáp ứng yêu cầu, không cần thêm custom indicator thứ hai. Hai phép kiểm tra đồng thời có thể tạo thêm connection và query không cần thiết.

### Giữ health check nhẹ

Không dùng truy vấn như:

```sql
SELECT COUNT(*) FROM orders;
```

hoặc scan bảng lớn để kiểm tra database còn sống. Truy vấn đó đo/tiêu thụ nhiều tài nguyên hơn mức cần thiết và có thể làm sự cố trầm trọng hơn. Health query nên xác nhận khả năng kết nối/thực thi cơ bản, không phải chạy báo cáo.

### Không trả thông tin nhạy cảm

Ví dụ trên chỉ đưa loại exception vào detail. Tránh trả message đầy đủ nếu message có thể chứa hostname, schema, SQL, tên user, đường dẫn hoặc thông tin nhạy cảm. Cấu hình hiển thị detail nên giới hạn người được phép xem.

## 9. R2DBC health check không chứng minh connection pool còn capacity

Một query `SELECT 1` thành công chỉ chứng minh một connection có thể được lấy và query hoàn thành trong điều kiện hiện tại. Nó không chứng minh pool còn đủ connection cho toàn bộ workload.

Ví dụ pool có `maxSize = 30`. Health check lấy được một connection và chạy xong. Trong cùng thời điểm, 30 request nghiệp vụ khác có thể đang giữ toàn bộ connection còn lại; các request tiếp theo phải chờ hoặc timeout. Health vẫn có thể trả UP nếu probe lấy được connection hoặc được chạy vào thời điểm pool còn chỗ.

Ngược lại, khi pool tạm thời đầy, health check có thể chờ acquire và timeout dù process vẫn sống. Đây là dấu hiệu có thể hữu ích cho readiness nếu service thực sự không thể nhận thêm traffic, nhưng cần tránh probe quá nhạy khiến instance liên tục chuyển ready/unready theo dao động ngắn hạn.

Hãy theo dõi riêng:

- Connection allocated và giới hạn tối đa.
- Connection acquired/in-use.
- Connection idle.
- Số request đang chờ acquire (pending).
- Thời gian chờ acquire và tỷ lệ acquire timeout.
- Thời gian giữ connection.
- Query latency và số query đồng thời.

Metric name cụ thể phụ thuộc R2DBC Pool, Micrometer và phiên bản Spring Boot. Kiểm tra metric registry của ứng dụng thay vì giả định mọi phiên bản xuất cùng tên.

## 10. Readiness không phải capacity test

Một probe thường chạy một request đơn lẻ, theo chu kỳ và với payload nhỏ. Nó không tạo workload đại diện cho ứng dụng. Vì vậy, readiness UP không chứng minh:

- 100, 1.000 hoặc 10.000 request đồng thời đều xử lý được.
- P95/P99 latency nằm trong SLO.
- Database có đủ CPU/I/O cho giờ cao điểm.
- Connection pool còn đủ headroom dưới tải đỉnh.
- Không có lock contention hoặc slow query.
- Consumer/background job có thể bắt kịp tốc độ dữ liệu đến.
- Hệ thống vẫn hoạt động ổn định sau nhiều giờ hoặc nhiều ngày.

Khả năng phục vụ tải thật cần được đánh giá bằng workload gần với production và metrics trong thời gian đủ dài. Probe chỉ là tín hiệu trạng thái cho orchestrator.

### Capacity có nhiều tầng

Với R2DBC, capacity không chỉ là số connection tối đa:

1. **HTTP server:** số request đồng thời, event loop, queue và timeout.
2. **Reactor pipeline:** concurrency, prefetch, scheduler usage và cancellation.
3. **R2DBC pool:** connection acquire, idle, pending và max size.
4. **Database:** CPU, IOPS, lock, transaction, buffer/cache và query plan.
5. **Dependency khác:** HTTP services, cache, broker và storage.
6. **Application runtime:** heap, direct memory, GC, CPU và thread/scheduler saturation.

Một tầng có thể là bottleneck dù mọi health check cơ bản đều UP.

## 11. Metrics quan trọng cho Spring Data R2DBC

Để biết ứng dụng có phục vụ được tải thật, cần quan sát cả request và database.

### HTTP/application metrics

- Request rate theo endpoint và method.
- Error rate theo status và exception category.
- P50/P95/P99 latency.
- Request đang chạy và queue length nếu có.
- Timeout, cancellation và client disconnect.
- Throughput thành công, không chỉ số request nhận vào.

### R2DBC pool metrics

- Số connection tối đa và đã cấp phát.
- Số connection đang được sử dụng.
- Số connection idle.
- Pending acquire count.
- Acquire latency và acquire timeout.
- Connection usage duration.

Nếu `r2dbc-pool` được dùng, kiểm tra cấu hình metrics và registry tương ứng. Không nên suy ra pool đang khỏe chỉ từ việc database health indicator UP.

### Database metrics

- Query latency theo loại query hoặc operation.
- Slow query count.
- Transaction duration và rollback rate.
- Lock wait/deadlock.
- CPU, memory, disk I/O và storage pressure.
- Active connections và giới hạn connection server.
- Replication lag nếu hệ thống dùng replica.
- Query plan regression và index usage.

### Reactor/runtime metrics

- Scheduler queue/worker saturation nếu được instrument.
- Reactor operator metrics phù hợp.
- Heap/direct memory và GC pause.
- CPU throttling trong container.
- Event loop blocked hoặc tác vụ blocking ngoài ý muốn.
- Số publisher đang hoạt động và thời gian hoàn tất.

Không expose mọi metric ra endpoint công khai. Dùng Micrometer registry và hệ thống monitoring phù hợp; giới hạn cardinality của label, tránh gắn customer ID, request ID hoặc giá trị tự do làm label.

## 12. Dùng Spring Boot Actuator để quan sát

Actuator cung cấp health và metrics endpoint. Ví dụ expose trong môi trường quản trị:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
      show-components: when_authorized
```

`prometheus` cần registry tương ứng được thêm vào dependencies. Cấu hình exposure phải phù hợp phiên bản Spring Boot và chính sách bảo mật. Chỉ expose endpoint cần thiết; metrics có thể tiết lộ topology, tên operation và đặc điểm tải.

Các endpoint tiêu biểu:

- `/actuator/health`: trạng thái tổng hợp.
- `/actuator/health/liveness`: trạng thái liveness.
- `/actuator/health/readiness`: trạng thái readiness.
- `/actuator/metrics`: tra cứu metric được Micrometer đăng ký.
- `/actuator/prometheus`: scrape format nếu có Prometheus registry.

Health details nên chỉ hiển thị khi người gọi được authorize. Không trả password, URL có credential, SQL bind values hoặc exception message nhạy cảm.

## 13. Readiness group nên bao gồm những gì?

Một readiness group tốt chỉ chứa các điều kiện thực sự cần để instance nhận traffic.

Ví dụ service R2DBC cần database cho phần lớn request:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

Ví dụ service có thể phục vụ read-only request khi một dependency tùy chọn mất kết nối:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
```

Ở trường hợp thứ hai, nếu database vẫn bắt buộc cho hầu hết request thì vẫn hợp lý đưa nó vào readiness. Nếu chỉ một endpoint phụ thuộc database còn các chức năng khác vẫn có thể phục vụ, hãy cân nhắc readiness theo khả năng tổng thể hoặc tách service/traffic class thay vì loại toàn bộ instance.

### Không đưa mọi dependency vào readiness một cách máy móc

Giả sử service dùng:

- R2DBC database bắt buộc.
- Redis chỉ dùng làm cache, có thể fallback database.
- Analytics API chỉ dùng gửi event không đồng bộ.
- Email provider không tham gia request path.

Readiness có thể chỉ cần kiểm tra database bắt buộc. Nếu Redis mất, service có thể chậm hơn nhưng vẫn phục vụ; analytics/email mất không nhất thiết khiến service ngừng nhận traffic. Thay vào đó, cảnh báo và retry/outbox xử lý các dependency tùy chọn.

### Shared dependency outage

Nếu database dùng chung đang DOWN, tất cả instance có thể đồng loạt readiness DOWN. Điều đó có thể phản ánh đúng việc chúng không thể phục vụ request cần DB, nhưng cũng có thể khiến load balancer không còn backend và người dùng nhận lỗi ở tầng gateway. Hãy phối hợp readiness với alerting, fallback, maintenance policy và cách hệ thống xử lý degraded mode.

Không nên loại bỏ database khỏi readiness chỉ để probe luôn xanh. Hãy quyết định theo khả năng thực sự của service và hậu quả định tuyến khi dependency hỏng.

## 14. Readiness state và vòng đời ứng dụng

Spring Boot có availability state để biểu diễn ứng dụng đã sẵn sàng nhận traffic hay chưa. Các trạng thái thường gặp gồm:

- `ACCEPTING_TRAFFIC`: ứng dụng có thể nhận traffic.
- `REFUSING_TRAFFIC`: ứng dụng không nên nhận request mới.

Ứng dụng có thể công bố readiness state qua availability event khi cần chủ động chuyển trạng thái, ví dụ bắt đầu drain trước shutdown:

```java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC
);
```

Khi trạng thái phù hợp để nhận traffic trở lại:

```java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.ACCEPTING_TRAFFIC
);
```

Các import và cách inject `ApplicationContext` cần theo cấu trúc ứng dụng. Spring Boot tự cập nhật availability state trong lifecycle chuẩn; chỉ phát event thủ công khi có một điều kiện nghiệp vụ/vận hành cụ thể cần điều khiển readiness.

### Graceful shutdown

Khi ứng dụng nhận tín hiệu shutdown:

1. Đánh dấu readiness `REFUSING_TRAFFIC` để ngừng nhận request mới.
2. Load balancer/orchestrator có thời gian cập nhật endpoint routing.
3. Hoàn tất request đang chạy trong khoảng graceful shutdown được cấu hình.
4. Đóng các publisher/consumer và connection pool theo lifecycle.
5. Kết thúc process.

Nếu đóng `ConnectionFactory` quá sớm, request đang chạy có thể lỗi. Nếu tiếp tục nhận request trong lúc đang đóng pool, request mới có thể timeout. Readiness và graceful shutdown cần được thiết kế cùng nhau.

## 15. Kubernetes liveness/readiness/startup probes

Ví dụ cấu hình Kubernetes dùng các endpoint Actuator:

```yaml
containers:
  - name: app
    image: example/r2dbc-service:1.0
    ports:
      - name: http
        containerPort: 8080
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 10
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
```

Đây là ví dụ cấu hình container trong Pod spec; các giá trị cần điều chỉnh theo thời gian khởi động, latency bình thường và mục tiêu phục hồi của service. Nếu đã bật additional paths trên main port, có thể dùng `/livez` và `/readyz` thay cho management path.

### Ý nghĩa các tham số

| Tham số | Ý nghĩa |
| --- | --- |
| `periodSeconds` | Khoảng thời gian giữa các lần probe |
| `timeoutSeconds` | Thời gian tối đa chờ một lần probe |
| `failureThreshold` | Số lần thất bại liên tiếp trước khi hành động tương ứng |
| `successThreshold` | Số lần thành công liên tiếp cần thiết để chuyển sang success trong trường hợp áp dụng |
| `initialDelaySeconds` | Thời gian chờ trước lần probe đầu tiên nếu dùng |

Startup probe cho phép quá trình khởi động lâu hơn mà không bị liveness restart quá sớm. Readiness có thể kiểm tra thường xuyên hơn liveness vì mục tiêu là điều chỉnh traffic. Đặt timeout đủ lớn cho điều kiện bình thường nhưng không lớn đến mức giữ pod trong trạng thái không xác định quá lâu.

## 16. Management port và main application port

Một cấu hình thường gặp là Actuator chạy trên cổng riêng, ví dụ `management.server.port: 8081`, còn ứng dụng nhận traffic trên 8080. Nếu Kubernetes chỉ probe cổng 8081, management server có thể vẫn trả health trong khi cổng ứng dụng bị lỗi hoặc không bind đúng.

Khi có thể, dùng additional health paths trên main port hoặc kiểm tra riêng main server bằng một probe phù hợp. Mục tiêu là readiness/liveness phản ánh đúng instance mà load balancer sẽ gửi traffic.

Ví dụ:

```yaml
server:
  port: 8080
management:
  server:
    port: 8081
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Kiểm tra chính xác path/port được expose ở phiên bản Spring Boot đang dùng. Đảm bảo firewall/network policy cho phép kubelet truy cập probe path nhưng không mở rộng Actuator ra internet.

## 17. Timeout và tần suất health check

Một health check không có timeout có thể treo lâu khi pool hoặc database gặp sự cố. Probe timeout cần được giới hạn ở cả tầng HTTP/Kubernetes và tầng reactive operation.

Với custom R2DBC indicator:

```java
return databaseClient.sql("SELECT 1")
        .fetch()
        .first()
        .map(row -> Health.up().build())
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(error -> Mono.just(
                Health.down()
                        .withDetail("cause", error.getClass().getSimpleName())
                        .build()
        ));
```

Timeout trong publisher giới hạn thời gian chờ query/connection theo pipeline. `timeoutSeconds` của Kubernetes giới hạn thời gian probe HTTP. Hai timeout nên phối hợp: timeout nội bộ cần đủ ngắn để indicator trả kết quả trước khi kubelet bỏ request.

### Tránh probe storm

Nếu có 100 pod, mỗi pod kiểm tra DB nhiều lần mỗi giây, health check có thể tạo thêm tải không cần thiết. Hãy chọn `periodSeconds` hợp lý, truy vấn cực nhẹ và cân nhắc cache TTL của health endpoint nếu phù hợp phiên bản/cấu hình. Không tạo query aggregate nặng hoặc gọi nhiều dependency ngoài trên mỗi probe.

Health check phải là một phần tải rất nhỏ so với workload thật. Trong outage, nó không được làm database tệ hơn.

## 18. Health check và circuit breaker

Health check, readiness và circuit breaker có quan hệ nhưng không thay thế nhau.

- Health check cung cấp tín hiệu trạng thái cho monitoring/orchestrator.
- Readiness quyết định instance có nhận traffic mới hay không.
- Circuit breaker điều khiển lời gọi tới một dependency khi tỷ lệ lỗi/latency vượt ngưỡng; nó có thể mở, half-open và đóng lại.
- Retry thử lại một thao tác theo chính sách số lần/backoff.
- Bulkhead giới hạn concurrency hoặc tài nguyên dành cho một dependency.

Ví dụ database chậm, circuit breaker ở tầng service có thể ngăn request tiếp tục tạo nhiều query đang chờ. Readiness có thể chuyển DOWN nếu ứng dụng thực sự không còn khả năng phục vụ. Nhưng không nên dùng health endpoint để thay thế circuit breaker trong từng request path.

## 19. Phân biệt probe với synthetic monitoring

Synthetic monitoring thực hiện các hành trình hoặc request đại diện từ bên ngoài hệ thống để kiểm tra trải nghiệm người dùng. Ví dụ:

- Gửi request đăng nhập bằng tài khoản test.
- Đọc một bản ghi fixture qua API.
- Thực hiện một giao dịch thử nghiệm có thể rollback hoặc dùng dữ liệu test.
- Kiểm tra API qua DNS, TLS, gateway và authentication thực tế.

Synthetic check có thể phát hiện lỗi routing, auth, serialization hoặc query nghiệp vụ mà `SELECT 1` không thấy. Tuy nhiên, nó cũng cần giới hạn tần suất, dữ liệu test và side effect. Không nên đặt synthetic journey phức tạp làm liveness probe chạy liên tục.

Health check thường chạy từ trong cluster và kiểm tra trạng thái instance; synthetic monitoring thường kiểm tra đường đi từ góc nhìn client. Cả hai bổ sung cho nhau.

## 20. Đánh giá khả năng phục vụ tải thật

Muốn biết service R2DBC có chịu được tải production không, cần chạy workload đại diện và đo kết quả. Các loại thử nghiệm thường dùng:

| Kiểu test tải | Mục đích |
| --- | --- |
| Load test | Kiểm tra mức tải dự kiến trong điều kiện bình thường |
| Stress test | Tăng tải vượt mức dự kiến để tìm giới hạn và cách hệ thống suy giảm |
| Spike test | Tạo đợt tăng tải đột ngột để xem hệ thống phản ứng thế nào |
| Soak test | Giữ tải ổn định trong thời gian dài để tìm memory leak, pool leak hoặc suy giảm dần |
| Capacity test | Tìm throughput tối đa trong khi vẫn đáp ứng latency/error mục tiêu |

Một test chỉ gửi nhiều request mà không đo latency, error và tài nguyên chưa đủ để kết luận capacity.

### Workload cần đại diện

Tạo kịch bản gần với production:

- Tỷ lệ đọc/ghi tương tự.
- Kích thước payload và số hàng trả về tương tự.
- Phân bố tenant/customer và độ chọn lọc query tương tự.
- Tỷ lệ cache hit/miss tương tự.
- Transaction duration và mức độ tranh chấp dữ liệu tương tự.
- Số request đồng thời và tốc độ đến thực tế.
- Các dependency ngoài có latency/error được mô phỏng phù hợp.
- Số application replica và pool size gần cấu hình triển khai.

Nếu chỉ benchmark một `SELECT 1`, kết quả không đại diện cho API đọc join nhiều bảng hoặc transaction ghi nhiều entity.

## 21. SLO, latency và error rate

Khả năng phục vụ tải thật nên được đánh giá bằng mục tiêu dịch vụ rõ ràng, ví dụ:

- Tỷ lệ request thành công trong một cửa sổ thời gian.
- P95/P99 latency theo endpoint quan trọng.
- Tỷ lệ timeout và lỗi database.
- Throughput thành công dưới tải dự kiến.
- Thời gian phục hồi sau khi dependency lỗi.
- Mức sử dụng connection pool và headroom.

Ví dụ, một service có thể có health UP nhưng P99 latency tăng từ 200 ms lên 8 giây. Về trạng thái process, nó vẫn sống; về trải nghiệm người dùng, nó đang không đáp ứng SLO. Health và SLO trả lời hai câu hỏi khác nhau.

Đặt alert dựa trên SLO/error budget và saturation metrics thay vì chỉ alert khi `/actuator/health` trả DOWN. Một hệ thống có thể bắt đầu suy giảm nghiêm trọng trước khi health indicator thất bại.

## 22. R2DBC pool saturation là tín hiệu quan trọng

R2DBC pool có giới hạn số connection. Khi tất cả connection đã được acquire, request mới phải chờ một connection được trả về. Nếu thời gian chờ vượt `maxAcquireTime` hoặc request deadline, operation có thể timeout.

Các dấu hiệu pool saturation:

- `acquired` gần bằng `maxSize` trong thời gian dài.
- `pending` tăng.
- Acquire latency tăng.
- Nhiều lỗi acquire timeout.
- Query latency bình thường ở database nhưng request latency tăng do chờ pool.
- Connection usage duration tăng vì transaction/stream giữ connection lâu.

Phân biệt hai trường hợp:

1. **Database chậm:** query thực sự mất nhiều thời gian, connection bị giữ lâu.
2. **Pool quá nhỏ hoặc concurrency quá cao:** request chờ connection dù query trên database không quá chậm.

Tăng pool size có thể giúp nếu database còn capacity và pool đang là bottleneck. Nhưng nếu database đã bão hòa, tăng pool có thể làm query đồng thời nhiều hơn và khiến latency xấu hơn. Hãy đo cả phía pool lẫn database trước khi điều chỉnh.

## 23. R2DBC query latency và transaction duration

Một health check nhẹ có thể thành công trong khi query nghiệp vụ bị chậm do:

- Index thiếu hoặc query plan thay đổi.
- Table scan trên bảng lớn.
- Lock wait hoặc deadlock.
- Nhiều transaction giữ connection quá lâu.
- Payload lớn và mapping tốn CPU.
- N+1 query hoặc nhiều round-trip.
- Network latency giữa app và database.
- Database đang chạy backup, vacuum/maintenance hoặc workload khác.

Theo dõi query latency theo operation name hoặc repository method đã chuẩn hóa. Không dùng SQL đầy đủ hoặc parameter value làm metric label vì cardinality và dữ liệu nhạy cảm. Distributed tracing có thể giúp nối request span với database span nếu driver/instrumentation hỗ trợ.

Transaction dài cũng ảnh hưởng pool và database. Tránh gọi HTTP, gửi email hoặc chờ người dùng trong lúc giữ transaction R2DBC nếu không có yêu cầu nhất quán bắt buộc.

## 24. Readiness khi database mất kết nối

Hãy xác định hành vi mong muốn thay vì tự động đánh dấu unready trong mọi trường hợp.

### Database bắt buộc cho mọi request

Nếu hầu hết endpoint cần truy vấn/ghi database và không có fallback hợp lệ, readiness có thể bao gồm database contributor. Khi database DOWN, instance ngừng nhận traffic mới; alert riêng báo dependency outage.

### Database chỉ phục vụ một phần chức năng

Nếu service vẫn có thể phục vụ health/info, cache-backed read hoặc endpoint độc lập, có thể không muốn loại toàn bộ instance khỏi load balancing. Một giải pháp khác là tách chức năng thành service riêng, hoặc dùng degraded mode rõ ràng cho endpoint phụ thuộc DB.

### Database lỗi ngắn hạn nhưng pool còn phục hồi

Probe quá nhạy có thể khiến readiness dao động. Chọn timeout/failure threshold phù hợp, dùng circuit breaker hoặc backpressure cho request path, và alert theo tỷ lệ lỗi. Không dùng một lần query chậm để lập tức restart process.

### Database dùng chung bị outage

Nếu tất cả replica cùng unready, load balancer có thể trả lỗi không có backend. Điều đó không làm database phục hồi. Cần có observability và runbook ở cấp dependency, không chỉ dựa vào việc restart pod.

## 25. Readiness khi deploy và rolling update

Trong rolling deployment, instance mới không nên nhận traffic trước khi:

- Application context hoàn tất.
- Các bean bắt buộc sẵn sàng.
- Kết nối database và schema tương thích.
- Initialization/warm-up thiết yếu hoàn tất.
- Readiness state chuyển sang `ACCEPTING_TRAFFIC`.

Instance cũ cần chuyển sang `REFUSING_TRAFFIC` trước khi dừng để load balancer ngừng gửi request mới. Request đang chạy cần được drain trong khoảng thời gian cho phép.

### Schema migration tương thích

Nếu deployment chạy nhiều phiên bản ứng dụng đồng thời, schema migration nên theo hướng expand-and-contract:

1. Thêm cột/index mới theo cách tương thích với version cũ.
2. Deploy ứng dụng có thể đọc/ghi schema mới mà vẫn tương thích version cũ.
3. Backfill dữ liệu nếu cần.
4. Chuyển traffic và xác nhận phiên bản mới ổn định.
5. Loại bỏ cột/cấu trúc cũ ở release sau.

Readiness chỉ nên thành công khi instance thực sự có thể phục vụ với schema hiện tại. Đừng dùng health check để chạy migration lớn mỗi vài giây; migration thuộc lifecycle deployment hoặc một job được kiểm soát.

## 26. Bảo mật health endpoint

Health endpoint có thể tiết lộ:

- Database hoặc broker nào đang được dùng.
- Tên component và dependency.
- Exception type, host hoặc chi tiết kết nối.
- Trạng thái pool và topology nội bộ.
- Phiên bản hoặc thông tin triển khai.

Các nguyên tắc:

- Chỉ expose endpoint cần thiết.
- Giới hạn truy cập bằng network policy, firewall hoặc Spring Security.
- Dùng `show-details: when_authorized` nếu cần chi tiết.
- Không đưa credential, token, SQL parameter hoặc dữ liệu người dùng vào health details.
- Không cho phép health endpoint kích hoạt thao tác ghi hoặc side effect tùy ý.
- Dùng endpoint đơn giản cho kubelet và endpoint chi tiết hơn cho monitoring có quyền.

Kubernetes cần đọc probe endpoint từ node/agent tương ứng, nhưng điều đó không đồng nghĩa endpoint cần công khai trên Internet.

## 27. Ví dụ cấu hình tổng hợp cho service R2DBC

Ví dụ dưới đây bật probe, giữ liveness độc lập với database và đưa database vào readiness vì service giả định cần DB cho request chính:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db:5432/app
    username: app_user
    password: ${DB_PASSWORD}

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: when_authorized
      show-components: when_authorized
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

Ví dụ dùng PostgreSQL URL chỉ để minh họa một ứng dụng R2DBC; đổi URL/driver cho database thực tế. `prometheus` cần registry dependency tương ứng. Component `db` cần tồn tại trong health contributors của application context. Nếu không có, kiểm tra driver/auto-configuration hoặc dùng custom indicator có tên rõ ràng.

Không sao chép cấu hình readiness có `db` cho mọi service. Nếu database không bắt buộc cho traffic hoặc có degraded mode, điều chỉnh group theo hợp đồng phục vụ thực tế.

## 28. Các lỗi thiết kế thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Pod liên tục restart khi DB outage | Liveness phụ thuộc database | Giữ liveness cho trạng thái nội bộ process; đưa dependency vào readiness/alerting |
| Pod nhận traffic trước khi app sẵn sàng | Readiness chỉ kiểm tra process hoặc cấu hình probe chưa đúng | Kiểm tra readiness state và dependency bắt buộc |
| `/actuator/health` UP nhưng API timeout | Health check quá nông, pool hoặc query đã bão hòa | Theo dõi pool, latency, error rate và load test |
| Readiness liên tục nhấp nháy | Probe timeout quá thấp hoặc phụ thuộc chập chờn | Chọn timeout/threshold phù hợp, giảm probe load, xử lý dependency |
| Tất cả replica bị loại khi cache lỗi | Đưa dependency tùy chọn vào readiness | Chỉ include dependency cần cho traffic cốt lõi |
| Management port UP nhưng app port lỗi | Probe chỉ kiểm tra management server riêng | Dùng additional paths trên main port hoặc kiểm tra đúng cổng phục vụ |
| Health check làm DB quá tải | Query nặng hoặc tần suất quá cao | Dùng query nhẹ, timeout và chu kỳ hợp lý |
| Readiness UP dù pool gần cạn | Một probe đơn lẻ vẫn lấy được connection | Theo dõi acquired/pending/acquire latency và capacity riêng |
| Probe timeout giữ request lâu | Indicator không có timeout nội bộ | Đặt timeout reactive và HTTP probe phù hợp |
| Health details lộ thông tin | `show-details` công khai hoặc exception message nhạy cảm | Giới hạn authorization và sanitize detail |
| Restart không phục hồi lỗi dependency | Dùng liveness cho lỗi database/broker bên ngoài | Alert và xử lý dependency; tránh restart storm |
| Load test pass nhưng production vẫn nghẽn | Workload test không đại diện hoặc thiếu soak/spike | Dùng traffic mix, concurrency, data volume và duration gần thực tế |

## 29. Quy trình thiết kế observability và probe

1. Xác định health check cần trả lời câu hỏi nào và ai tiêu thụ kết quả.
2. Thiết kế liveness độc lập với dependency bên ngoài; chỉ báo trạng thái process cần restart khi thất bại.
3. Thiết kế startup probe cho thời gian khởi động dài nếu cần.
4. Xác định dependency bắt buộc để nhận traffic và đưa chúng vào readiness với tiêu chí rõ ràng.
5. Với R2DBC, kiểm tra built-in `db` contributor hoặc tạo custom reactive indicator nhẹ, có timeout.
6. Bảo đảm probe chạy trên cổng/path đại diện cho server nhận traffic.
7. Cấu hình timeout, period và failure threshold để tránh probe storm/dao động quá nhạy.
8. Theo dõi HTTP latency/error, R2DBC pool, query latency, database saturation và runtime metrics.
9. Xây dựng load/stress/spike/soak test với workload và dữ liệu gần production.
10. Đánh giá P95/P99, error rate, throughput, pool headroom và database capacity theo SLO.
11. Kết hợp readiness với graceful shutdown, rolling deployment và schema migration tương thích.
12. Bảo vệ health/metrics endpoint và chỉ hiển thị chi tiết cho người được phép.

## 30. Ghi nhớ

- Health check xác nhận một điều kiện cơ bản tại thời điểm kiểm tra; nó không chứng minh toàn bộ nghiệp vụ hoặc capacity.
- Liveness trả lời process có cần restart để phục hồi không; không nên phụ thuộc database hoặc dịch vụ ngoài.
- Readiness trả lời instance có nên nhận traffic mới không; chỉ include dependency bắt buộc cho traffic cốt lõi.
- Startup probe dành thời gian cho ứng dụng khởi động trước khi liveness/readiness được áp dụng đầy đủ.
- Spring Boot Actuator cung cấp health contributors và probe groups; cấu hình `livenessState` và `readinessState` rõ ràng.
- R2DBC database contributor có thể kiểm tra kết nối/validation cơ bản; `SELECT 1` thành công không chứng minh query nghiệp vụ hoặc pool capacity.
- Custom `ReactiveHealthIndicator` nên trả publisher có timeout, query nhẹ và health details đã sanitize.
- Readiness UP không có nghĩa service chịu được tải thật; cần theo dõi latency, error rate, throughput, pool saturation và database metrics.
- Reactive Streams backpressure, R2DBC pool và database capacity là các tầng riêng cần quan sát.
- Load test, stress test, spike test và soak test dùng workload đại diện để đánh giá capacity và độ bền.
- Readiness, graceful shutdown và rolling deployment phải phối hợp để tránh nhận traffic khi đang drain.
- Health endpoint cần được bảo vệ; không expose credential, SQL parameter hoặc exception message nhạy cảm.

Một service R2DBC vận hành tốt cần ba loại bằng chứng riêng: process còn sống, instance sẵn sàng nhận traffic và hệ thống đáp ứng workload trong giới hạn SLO. Hãy dùng liveness để quyết định restart, readiness để điều khiển routing, còn metrics/tracing/load test để đánh giá khả năng phục vụ tải thật. Giữ probe nhẹ và có timeout; quan sát riêng connection pool, query và database để phát hiện suy giảm trước khi health endpoint chuyển DOWN.
