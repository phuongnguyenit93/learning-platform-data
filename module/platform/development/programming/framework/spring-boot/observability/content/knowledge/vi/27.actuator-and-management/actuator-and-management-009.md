# Metrics endpoint

Khi dashboard báo latency tăng, đội vận hành cần xác minh meter nào đang được ghi nhận trên một instance Spring Boot, các tag nào tồn tại và giá trị đo hiện tại ra sao. Actuator Metrics endpoint cung cấp giao diện HTTP để liệt kê meter names, đọc một meter cụ thể và lọc theo tag. Đây là công cụ chẩn đoán hữu ích trong quá trình phát triển và vận hành.

Bài **Metrics endpoint** thuộc chương **Actuator và management** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Điểm cốt lõi:** GET /actuator/metrics liệt kê meter names; GET /actuator/metrics/{requiredMetricName} đọc meter cụ thể và các tag values; query parameter tag=KEY:VALUE lọc theo tag. Endpoint đọc MeterRegistry của application process hiện tại, trả JSON chẩn đoán và không phải Prometheus exposition endpoint hay kho lịch sử time series.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích vai trò của Actuator Metrics endpoint.
2. Bật Actuator và cấu hình base path, port, endpoint exposure.
3. Liệt kê meter names và truy vấn một meter.
4. Lọc meter bằng tag key/value.
5. Đọc measurements của Counter, Gauge, Timer và DistributionSummary.
6. Hiểu vì sao histogram/percentile fields có thể không xuất hiện.
7. Phân biệt Metrics endpoint với Prometheus scrape endpoint.
8. Bảo vệ endpoint bằng authentication, network policy và exposure tối thiểu.
9. Điều tra meter thiếu, tag không khớp và cardinality tăng.
10. Biết khi nào cần dashboard, exporter hoặc tracing backend.

## 2. Actuator Metrics endpoint là gì?

Spring Boot Actuator cung cấp endpoint metrics để đọc các meters đã đăng ký trong Micrometer MeterRegistry. Mỗi meter có name, type, measurements và có thể có tags.

| HTTP request | Mục đích |
|---|---|
| GET /actuator/metrics | Liệt kê meter names |
| GET /actuator/metrics/{requiredMetricName} | Đọc meter theo tên |
| GET /actuator/metrics/{requiredMetricName}?tag=key:value | Lọc meter theo tag |
| GET /actuator | Discovery document nếu links được bật và exposed |

Endpoint chỉ đọc dữ liệu của application process/registry hiện tại. Nó không query trực tiếp database, Prometheus, OTLP Collector hay metrics của các service khác.

Ví dụ meter http.server.requests có thể đến từ HTTP server instrumentation; jvm.memory.used từ JVM binder; app.orders.created do ứng dụng tự đăng ký.

## 3. Thêm Spring Boot Actuator

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Với Maven, thêm spring-boot-starter-actuator và dùng Spring Boot dependency management để chọn version tương thích.

Actuator cung cấp endpoint infrastructure và integrations. Meter nào xuất hiện còn phụ thuộc auto-configuration, binders, MeterRegistry, instrumentation của MVC/HTTP client/database/messaging/JVM và custom meters. Chỉ thêm Actuator không làm mọi method tự động có metric; cần instrumentation hoặc binder tạo meter.

## 4. Cấu hình exposure của endpoint

Actuator endpoints có thể expose qua HTTP hoặc JMX. Cấu hình HTTP exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Nếu dùng Prometheus registry và cần endpoint scrape, expose prometheus riêng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Chỉ expose endpoint cần thiết. Tránh wildcard * trong production nếu chưa đánh giá toàn bộ endpoint và security policy.

Base path mặc định thường là /actuator; có thể đổi:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

Khi đổi base path, Metrics endpoint trở thành /manage/metrics. Nếu management server chạy trên port riêng, URL phải dùng port đó. Kiểm tra cấu hình thực tế thay vì giả định luôn dùng application port.

## 5. Liệt kê meter names

Gửi request:

~~~http
GET /actuator/metrics
Accept: application/vnd.spring-boot.actuator.v3+json
~~~

Response minh họa:

~~~json
{
  "names": [
    "application.ready.time",
    "http.server.requests",
    "jvm.memory.used",
    "process.cpu.usage",
    "system.cpu.usage"
  ]
}
~~~

Danh sách thực tế phụ thuộc runtime, dependencies và instrumentation. Không phải ứng dụng nào cũng có đúng các meter trong ví dụ.

Danh sách names giúp khám phá tên meter; nó không trả toàn bộ time series hoặc lịch sử. Một meter có thể chưa xuất hiện nếu code path tạo meter chưa chạy hoặc binder chưa được bật.

### 5.1 Một số nhóm meter thường gặp

| Nhóm | Ví dụ meter | Ý nghĩa |
|---|---|---|
| HTTP server | http.server.requests | Số lượng và thời gian xử lý HTTP requests |
| HTTP client | http.client.requests | Outbound HTTP exchanges |
| JVM memory | jvm.memory.used | Memory đang sử dụng theo area/tag |
| JVM threads | jvm.threads.live | Số thread đang sống |
| CPU | process.cpu.usage, system.cpu.usage | CPU process hoặc host |
| Data source | jdbc.connections.active | Connections đang active nếu binder hỗ trợ |
| Executor | executor.active | Tasks đang hoạt động nếu executor được instrument |
| Application | app.orders.created | Custom business meter |

Tên và tags phụ thuộc version, registry và integration. Dùng endpoint để xác nhận meter có thật trước khi viết query.

## 6. Đọc một meter cụ thể

Ví dụ:

~~~http
GET /actuator/metrics/http.server.requests
~~~

Response rút gọn minh họa:

~~~json
{
  "name": "http.server.requests",
  "description": "Duration of HTTP server request handling",
  "baseUnit": "seconds",
  "measurements": [
    {"statistic": "COUNT", "value": 1250.0},
    {"statistic": "TOTAL_TIME", "value": 42.7},
    {"statistic": "MAX", "value": 1.82}
  ],
  "availableTags": [
    {"tag": "method", "values": ["GET", "POST"]},
    {"tag": "status", "values": ["200", "404", "500"]},
    {"tag": "outcome", "values": ["SUCCESS", "CLIENT_ERROR", "SERVER_ERROR"]}
  ]
}
~~~

Các số liệu chỉ là dữ liệu minh họa. Timer thường cung cấp COUNT, TOTAL_TIME và MAX; distribution statistics có thể có thêm fields tùy cấu hình và registry. Không mặc định mọi meter đều có cùng measurements.

### 6.1 Ý nghĩa measurements

- COUNT: số lần ghi nhận.
- TOTAL_TIME: tổng thời gian đã ghi nhận, theo base unit.
- MAX: giá trị lớn nhất trong cửa sổ/đoạn dữ liệu mà meter implementation giữ.
- VALUE: giá trị hiện tại của Gauge hoặc FunctionCounter tùy meter type.
- Các thống kê phân phối khác: tùy loại meter và cấu hình.

Với Timer, baseUnit thường là seconds khi trả qua Actuator, nhưng luôn đọc baseUnit và statistic thay vì tự giả định.

### 6.2 Available tags

availableTags liệt kê tag keys và values đã được ghi nhận cho meter. Nó giúp khám phá dimension hiện có để viết query. Nó không phải danh sách tag values của mọi service hoặc mọi thời điểm trong hệ thống; nó phản ánh registry mà endpoint đang đọc.

## 7. Lọc meter bằng tag

Dùng query parameter tag:

~~~http
GET /actuator/metrics/http.server.requests?tag=method:GET
~~~

Nhiều điều kiện có thể truyền bằng cách lặp query parameter:

~~~http
GET /actuator/metrics/http.server.requests?tag=method:GET&tag=status:200
~~~

Ví dụ điều tra POST trả 500:

~~~http
GET /actuator/metrics/http.server.requests?tag=method:POST&tag=status:500
~~~

Mỗi tag filter giới hạn kết quả theo key/value tương ứng. Nếu tag key/value không tồn tại hoặc không có meter phù hợp, endpoint có thể trả lỗi không tìm thấy meter matching. Trước hết kiểm tra availableTags để biết tag names và values chính xác.

### 7.1 Encode query parameters

Một số tag values có ký tự đặc biệt, dấu cách hoặc ký tự cần URL encoding. HTTP client/browser phải encode query parameter đúng cách. Không nối trực tiếp user input vào URL management endpoint mà không encode và validate.

### 7.2 Tag filtering không phải PromQL

Actuator tag filter chỉ chọn meter theo tag values. Nó không hỗ trợ aggregation, rate, histogram quantile hay phép toán giữa series như PromQL. Dùng Prometheus hoặc metrics backend cho query time series và phép tính phức tạp.

## 8. Counter, Gauge, Timer và DistributionSummary

| Meter type | Dữ liệu quan sát | Cách diễn giải |
|---|---|---|
| Counter | COUNT | Tổng số lần event tăng counter |
| Gauge | VALUE | Giá trị tại thời điểm đọc |
| Timer | COUNT, TOTAL_TIME, MAX và thống kê phân phối nếu có | Số lần và thời gian operation |
| DistributionSummary | COUNT, TOTAL và MAX/percentiles nếu cấu hình | Phân phối kích thước/giá trị |
| FunctionCounter | COUNT | Giá trị tích lũy đọc từ function |
| LongTaskTimer | ACTIVE_TASKS, DURATION | Task đang chạy và thời gian active theo implementation |

Counter không thể giảm; Gauge có thể tăng/giảm. Timer ghi duration của events; DistributionSummary ghi các giá trị không nhất thiết là thời gian.

Ví dụ đọc gauge:

~~~http
GET /actuator/metrics/jvm.memory.used?tag=area:heap
~~~

Ví dụ đọc custom counter:

~~~http
GET /actuator/metrics/app.orders.created
~~~

Nếu meter không có tag area hoặc app.orders.created chưa được đăng ký, request sẽ không trả kết quả như mong muốn. Kiểm tra names và availableTags trước.

## 9. Percentiles và histogram

Không phải mọi Timer đều tự động có percentile hoặc histogram buckets. Cần cấu hình distribution statistics ở meter hoặc registry phù hợp.

Ví dụ bật percentile histogram cho một meter qua MeterFilter:

~~~java
@Bean
MeterFilter httpServerHistogram() {
    return new MeterFilter() {
        @Override
        public DistributionStatisticConfig configure(
                Meter.Id id,
                DistributionStatisticConfig config) {
            if (id.getName().equals("http.server.requests")) {
                return DistributionStatisticConfig.builder()
                        .percentilesHistogram(true)
                        .build()
                        .merge(config);
            }
            return config;
        }
    };
}
~~~

Ví dụ minh họa cấu hình registry; kiểm tra binder, registry và naming convention của ứng dụng. Có thể dùng properties như management.metrics.distribution.percentiles-histogram theo meter name trong các phiên bản hỗ trợ.

Khi distribution statistics được bật, endpoint có thể hiển thị thêm measurements như percentiles hoặc histogram-related data tùy meter/registry. Không giả định chỉ cần gọi endpoint là p95/p99 sẽ có sẵn.

### 9.1 Percentiles và histogram khác nhau

- Client-side percentile được tính trong từng meter instance; khó tổng hợp chính xác giữa nhiều instances.
- Histogram buckets có thể được backend tổng hợp để tính quantile và SLO.
- Histogram tăng số series/time series; chỉ bật cho meters cần thiết.
- Bucket boundaries nên khớp latency objectives và workload.

Metrics endpoint phù hợp kiểm tra cấu hình và giá trị cục bộ; backend chuyên dụng phù hợp phân tích percentile trên fleet.

## 10. Custom metrics xuất hiện trong endpoint

Khi ứng dụng đăng ký meter qua Micrometer, endpoint có thể đọc meter đó từ MeterRegistry.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
class OrderMetrics {

    private final Counter created;

    OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("app.orders.created")
                .description("Number of created orders")
                .tag("channel", "web")
                .register(registry);
    }

    void recordCreated() {
        created.increment();
    }
}
~~~

Ví dụ cố định channel=web để minh họa bounded tag. Trong ứng dụng thực tế, nếu channel là biến đầu vào, chỉ cho phép tập giá trị hữu hạn và chuẩn hóa trước khi tạo meter. Không tạo meter mới theo order ID/customer ID.

Sau khi method recordCreated chạy, gọi:

~~~http
GET /actuator/metrics/app.orders.created
~~~

Có thể lọc tag nếu meter có nhiều channel values đã đăng ký.

### 10.1 Common tags

Common tags có thể cấu hình qua MeterRegistryCustomizer hoặc properties để gắn metadata như service/environment vào meters. Chọn giá trị ổn định; không gắn instance-specific ID hoặc request data nếu làm cardinality tăng không cần thiết.

## 11. Metrics endpoint và Prometheus endpoint khác nhau

| Endpoint | Mục đích | Response |
|---|---|---|
| /actuator/metrics | Chẩn đoán một meter trong ứng dụng | JSON Actuator |
| /actuator/prometheus | Prometheus scrape | Prometheus exposition text |
| OTLP metrics exporter | Push metrics tới Collector/backend | OTLP protocol |
| Metrics backend query API | Query dữ liệu lưu trữ qua thời gian | Query result theo backend |

Để Prometheus scrape, thêm registry dependency phù hợp và expose endpoint:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Prometheus scrape /actuator/prometheus, không scrape /actuator/metrics như thể đó là exposition endpoint. Metrics endpoint không cung cấp lịch sử theo thời gian; nó đọc trạng thái meter hiện tại trong process.

## 12. Bảo mật Metrics endpoint

Metrics có thể tiết lộ tên service, dependency và topology nội bộ; route names, HTTP status và traffic patterns; JVM/process utilization; database pool state và business volumes.

Không expose endpoint công khai mà không có authentication/network controls. Nguyên tắc:
1. Chỉ expose endpoint cần thiết.
2. Đặt management port/network interface trong management network nếu phù hợp.
3. Bảo vệ bằng Spring Security hoặc reverse proxy authentication.
4. Dùng TLS trên network không tin cậy.
5. Hạn chế quyền truy cập theo role/service account.
6. Không trả credentials, request payload hoặc PII trong custom tags.
7. Ghi audit/access logs phù hợp và kiểm soát retention.
8. Kiểm tra endpoint exposure sau mỗi thay đổi cấu hình.

Exposure quyết định endpoint có route hay không; authentication/authorization là lớp kiểm soát riêng. Chỉ expose health và metrics không đồng nghĩa endpoint đã được xác thực.

## 13. Management port và base path

Có thể tách management server khỏi application port:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,metrics
~~~

Trong ví dụ, application HTTP server nghe 8080 và management server nghe 8081. Đường dẫn metrics là /actuator/metrics trên management port. Có thể cấu hình address/interface riêng theo deployment; bảo đảm load balancer, firewall và service network chỉ cho phép monitoring clients truy cập.

Nếu dùng management port riêng, một số health/readiness/liveness checks có thể có behavior khác khi management server không sẵn sàng. Thiết kế probe và availability policy theo hướng dẫn Actuator của version đang dùng.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| /actuator/metrics trả 404 | Actuator thiếu, endpoint không expose hoặc base path khác | Kiểm tra dependency, exposure và URL |
| Endpoint trả 401/403 | Security yêu cầu authentication/role | Dùng credentials/service account phù hợp |
| Names không có meter mong đợi | Instrumentation chưa tạo meter hoặc binder thiếu | Kiểm tra dependency, registry và code path |
| Meter tồn tại nhưng count bằng 0 | Chưa có event sau khi meter đăng ký | Gọi operation và đọc lại |
| Query tag không match | Key/value sai hoặc tag chưa xuất hiện | Xem availableTags |
| Timer không có p95/p99 | Distribution statistics chưa bật hoặc registry khác | Cấu hình histogram/percentiles |
| Metrics endpoint có dữ liệu nhưng Prometheus không scrape | Chưa thêm registry hoặc chưa expose prometheus | Thêm Prometheus registry và cấu hình scrape endpoint |
| Gauge thay đổi giữa các lần gọi | Gauge phản ánh trạng thái hiện tại | Diễn giải như snapshot, không phải counter |
| Metric cardinality tăng | Tag values động tạo meter IDs mới | Chuẩn hóa/allowlist dimensions |
| Meter name khác dự kiến | Convention/naming normalization hoặc integration version | Kiểm tra registry và meter names |
| Management port không truy cập được | Bind address/firewall/service network | Kiểm tra network path và management server |
| Endpoint lộ dữ liệu nội bộ | Exposure quá rộng hoặc thiếu auth | Thu hẹp exposure, network policy và security |

## 15. Playbook: điều tra HTTP latency tăng bằng Metrics endpoint

**Tình huống:** Dashboard cảnh báo HTTP latency tăng, cần xác nhận meter và tags tại một instance.

1. Truy cập management address qua network được cấp quyền.
2. Gọi /actuator/metrics để xác nhận meter http.server.requests tồn tại.
3. Gọi /actuator/metrics/http.server.requests để xem measurements và availableTags.
4. Lọc theo method, uri và status để xem nhóm request cần điều tra.
5. So sánh COUNT, TOTAL_TIME và MAX; endpoint là snapshot của registry, không phải lịch sử.
6. Mở trace backend để tìm request cụ thể và xem downstream spans.
7. So sánh với Prometheus/backend query để xem p95/p99, rate và xu hướng qua nhiều instances.
8. Nếu tag value không có, xác minh instrumentation/convention và route mapping.
9. Nếu endpoint không có meter, kiểm tra auto-configuration, binder và code path.
10. Sau điều tra, giữ management endpoint trong phạm vi truy cập cần thiết.

Không dùng một lần đọc MAX hoặc COUNT để kết luận toàn bộ fleet đang khỏe hay lỗi; endpoint chỉ phản ánh registry cục bộ.

## 16. Bài tập tự kiểm tra

**Bài 1 — Liệt kê meter.** Endpoint nào liệt kê meter names? Nó có trả lịch sử metrics không?

**Bài 2 — Đọc Timer.** Timer có COUNT=100, TOTAL_TIME=20 và baseUnit=seconds. Trung bình mỗi event là bao nhiêu giây? Vì sao không thể suy ra p95 từ hai số này?

**Bài 3 — Tag filtering.** Hãy viết URL để đọc HTTP server requests cho POST có status 500. Có thể truyền nhiều tag filters thế nào?

**Bài 4 — Available tags.** availableTags dùng để làm gì? Vì sao nó không phải danh sách tag values của toàn bộ hệ thống phân tán?

**Bài 5 — Prometheus.** Vì sao Prometheus scrape /actuator/prometheus thay vì /actuator/metrics?

**Bài 6 — Percentiles.** Vì sao Metrics endpoint không mặc định có p95/p99 cho mọi Timer? Histogram có chi phí gì?

**Bài 7 — Security.** Metrics endpoint tiết lộ những loại thông tin nào? Nêu hai lớp bảo vệ cần cấu hình.

**Bài 8 — Meter missing.** Meter app.orders.created không xuất hiện trong names. Hãy nêu các điểm kiểm tra theo thứ tự.

### Gợi ý trả lời

1. GET /actuator/metrics; endpoint liệt kê meter names và không lưu lịch sử time series.
2. Trung bình 0,2 giây. COUNT/TOTAL_TIME không cho biết phân phối nên không suy ra p95.
3. /actuator/metrics/http.server.requests?tag=method:POST&tag=status:500; lặp query parameter tag cho từng điều kiện.
4. Khám phá tag keys/values của meter tại registry hiện tại; không phải toàn bộ instances hoặc backend history.
5. Prometheus endpoint trả exposition format dành cho scraper; Metrics endpoint trả JSON chẩn đoán của Actuator.
6. Distribution statistics cần cấu hình và có chi phí memory/series/ingest; chỉ bật cho meter cần thiết.
7. Lộ topology, route, traffic và resource utilization. Thu hẹp network exposure và yêu cầu authentication/authorization.
8. Kiểm tra code đăng ký meter, code path increment, MeterRegistry, filters/predicates, endpoint exposure và tên meter thực tế.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure, access, base path và security considerations.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer integration, meter names, tags và distribution statistics.
- [Spring Boot — Prometheus](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus): Prometheus registry và scrape endpoint.
- [Micrometer — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html): meter types, Counter, Gauge, Timer và DistributionSummary.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer measurements, histogram và percentiles.
- [Spring Boot — Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html): bảo vệ management endpoints bằng Spring Security.
- [Prometheus — Exposition Formats](https://prometheus.io/docs/instrumenting/exposition_formats/): định dạng metrics mà Prometheus scrape.
- [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/): metric instruments và aggregation concepts.

**Ghi nhớ:** Metrics endpoint giúp khám phá và đọc meters trong registry của một Spring Boot instance. Dùng endpoint gốc để liệt kê names, endpoint theo meter name để xem measurements/availableTags, và query parameter tag để lọc. Nó trả JSON chẩn đoán, không phải lịch sử hay Prometheus exposition format. Muốn query rate, p95/p99 và xu hướng fleet-wide, dùng Prometheus/metrics backend; giữ endpoint management trong network được bảo vệ và chỉ expose những gì vận hành cần.

