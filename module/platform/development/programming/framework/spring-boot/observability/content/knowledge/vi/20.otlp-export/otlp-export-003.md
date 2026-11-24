# OTLP metrics trong Spring Boot

Spring Boot có thể xuất metrics do Micrometer thu thập tới hệ thống observability hỗ trợ OpenTelemetry Protocol (OTLP). Cách tích hợp này gửi Counter, Timer, Gauge và các phép đo phân phối qua giao thức trung lập với nhà cung cấp, thường thông qua OpenTelemetry Collector rồi tới metrics backend.

Bài **“OTLP metrics”** thuộc chương **OTLP export** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

**Điểm cốt lõi:** trong tích hợp metrics tiêu chuẩn của Spring Boot, Micrometer quản lý metric instruments và OtlpMeterRegistry chuyển đổi/xuất chúng qua OTLP. Đây là pipeline metrics, tách biệt với việc xuất spans và logs bằng OpenTelemetry.

## 1. OTLP metrics là gì?

OTLP là giao thức truyền telemetry giữa ứng dụng, collector và backend. Với metrics, payload OTLP chứa resource, scope/instrumentation metadata và metric data points, thay vì chỉ là chuỗi văn bản như Prometheus exposition.

```mermaid
flowchart LR
    A["Spring Boot application"] --> B["Micrometer meters"]
    B --> C["OtlpMeterRegistry"]
    C --> D["OTLP/HTTP metrics"]
    D --> E["OpenTelemetry Collector"]
    E --> F["Metrics backend"]
    F --> G["Query, dashboard, alerts"]
```

| Thành phần | Vai trò |
| --- | --- |
| Micrometer MeterRegistry | Quản lý Counter, Timer, Gauge, tags và measurements |
| OtlpMeterRegistry | Chuyển đổi meter data thành OTLP metrics và publish định kỳ |
| OTLP receiver | Nhận payload metrics qua OTLP |
| OpenTelemetry Collector | Nhận, xử lý, batch, route và export telemetry |
| Metrics backend | Lưu trữ, truy vấn và cảnh báo |
| Dashboard | Hiển thị SLI, xu hướng và tình trạng vận hành |

**OTLP không phải metrics database.** Chỉ cấu hình endpoint gửi dữ liệu không tạo ra storage hay dashboard. Receiver và backend phía sau phải được triển khai, cấu hình riêng.

## 2. Spring Boot dùng Micrometer để xuất metrics qua OTLP

Spring Boot chọn Micrometer làm abstraction metrics. Khi dependency OTLP registry có trên runtime classpath, auto-configuration có thể tạo OtlpMeterRegistry và bind cấu hình từ namespace management.otlp.metrics.export.

Điều này có một hệ quả quan trọng: metrics do Spring Boot/Micrometer thu thập **không mặc định đi qua OpenTelemetry SdkMeterProvider**. Nếu dependency bên thứ ba tự tạo OpenTelemetry MeterProvider, metrics của dependency đó không tự động được xuất bằng Micrometer registry. Cần cấu hình provider và wiring riêng nếu muốn xuất chúng.

Với ứng dụng Spring Boot thông thường, hãy instrument metrics bằng Micrometer:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutMetrics {
    private final Counter accepted;

    public CheckoutMetrics(MeterRegistry registry) {
        this.accepted = Counter.builder("checkout.accepted")
                .description("Accepted checkout attempts")
                .tag("channel", "web")
                .register(registry);
    }

    public void recordAccepted() {
        accepted.increment();
    }
}
```

Khi registry thực tế là OtlpMeterRegistry, meter này được xuất qua OTLP theo lịch publish. Code nghiệp vụ không cần biết receiver hay backend cụ thể.

Tài liệu Spring Boot giải thích lựa chọn Micrometer và metrics với OTLP tại [Observability — Metrics](https://docs.spring.io/spring-boot/reference/actuator/observability.html).

## 3. Thêm dependency OTLP registry

Với Gradle Groovy và dependency management của Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
}
```

Một số dự án dùng starter observability tổng hợp có thể đã kéo registry OTLP vào runtime. Trước khi thêm dependency, kiểm tra cấu hình dependency management để tránh khai báo trùng hoặc tự override version không tương thích.

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-otlp</artifactId>
    <scope>runtime</scope>
</dependency>
```

Không tự chọn phiên bản micrometer-registry-otlp khác BOM của Spring Boot nếu chưa kiểm tra ma trận tương thích.

## 4. Cấu hình endpoint OTLP

Spring Boot hỗ trợ property sau:

```yaml
management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
```

Path /v1/metrics là endpoint OTLP/HTTP metrics phổ biến. Nếu Collector chạy trong container khác, thay localhost bằng hostname mà ứng dụng truy cập được, ví dụ otel-collector. Trong container, localhost thường trỏ về chính container ứng dụng.

Ví dụ cấu hình local:

```yaml
spring:
  application:
    name: checkout-service

management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
        step: 30s
        aggregation-temporality: cumulative
        compression-mode: gzip
```

Các property phải đúng dòng Spring Boot/Micrometer của dự án. Cấu hình hiện hành có các tùy chọn như url, step, aggregation-temporality, compression-mode, batch-size, headers, resource-attributes và timeout. Xem [Spring Boot Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) và [Micrometer OTLP registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html).

### URL và protocol

| Endpoint | Ý nghĩa |
| --- | --- |
| http://localhost:4318/v1/metrics | OTLP/HTTP metrics receiver cục bộ |
| https://otlp.example.com:4318/v1/metrics | OTLP/HTTP qua TLS |
| localhost:4317 | Thường là OTLP/gRPC receiver, không phải URL HTTP /v1/metrics |

Đừng đổi port hoặc path tùy ý. Receiver cần bật đúng protocol, và registry sender phải dùng protocol tương ứng. OtlpMeterRegistry chuẩn của Micrometer thường dùng HTTP sender; transport khác cần sender implementation phù hợp.

## 5. Chu kỳ publish, batch và timeout

step là chu kỳ registry publish metrics:

```yaml
management:
  otlp:
    metrics:
      export:
        step: 30s
        batch-size: 10000
        connect-timeout: 1s
        read-timeout: 10s
```

- **step:** khoảng thời gian publish/aggregation của registry. Chu kỳ ngắn làm dữ liệu mới hơn nhưng thường tăng số lần gửi.
- **batch-size:** số meter/measurements được gom vào payload theo cấu hình registry; khi vượt có thể tạo nhiều request.
- **connect-timeout:** giới hạn thời gian thiết lập kết nối.
- **read-timeout:** giới hạn thời gian chờ response từ receiver.

Đây là ví dụ khởi đầu, không phải sizing production. Đo số meter, kích thước payload, network latency và khả năng ingest. Không chọn step rất nhỏ chỉ để dashboard nhìn cập nhật tức thì.

### Export interval khác scrape interval

Với Prometheus pull, scraper quyết định lúc lấy mẫu endpoint. Với OTLP push, registry chủ động publish theo chu kỳ step. Dữ liệu còn cần thời gian instrumentation, aggregation, vận chuyển, ingestion và query; không nhất thiết xuất hiện ngay khi Counter tăng.

## 6. Aggregation temporality: cumulative và delta

OTLP hỗ trợ hai dạng temporality phổ biến:

- **Cumulative:** giá trị tích lũy kể từ điểm bắt đầu của aggregation stream.
- **Delta:** giá trị mới phát sinh trong một khoảng thời gian, độc lập với các khoảng trước.

Ví dụ Counter tăng 12 lần trong khoảng A và thêm 8 lần trong khoảng B:

| Khoảng | Cumulative | Delta |
| --- | ---: | ---: |
| A | 12 | 12 |
| B | 20 | 8 |

Backend cần hiểu temporality để tính rate, tổng hợp và xử lý reset đúng. Một backend chỉ hỗ trợ một loại temporality có thể từ chối hoặc xử lý sai loại còn lại.

Cấu hình cumulative:

```yaml
management:
  otlp:
    metrics:
      export:
        aggregation-temporality: cumulative
```

Micrometer OTLP registry hiện hành thường dùng cumulative làm mặc định, nhưng cần xác minh theo phiên bản. Cấu hình registry, biến môi trường và khả năng backend đều có thể ảnh hưởng. Không chuyển delta/cumulative trước khi kiểm tra hai phía.

### Reset và restart

Cumulative series cần xử lý reset khi process khởi động lại hoặc meter state reset. Delta streams biểu diễn increments theo khoảng, nhưng backend cần nhận biết start time và semantics tương ứng. Nếu backend nhận sai temporality, rate có thể nhảy, mất hoặc bị nhân đôi.

Khi thay đổi temporality trong production, coi đây là thay đổi hợp đồng dữ liệu: thử query, alert, dashboards và aggregation trước rollout.

## 7. Resource attributes và service identity

OTLP metrics gắn với **Resource** mô tả entity tạo dữ liệu, ví dụ service name, deployment environment và region.

Ví dụ:

```yaml
management:
  otlp:
    metrics:
      export:
        resource-attributes:
          service.name: checkout-service
          deployment.environment: production
          cloud.region: ap-southeast-1
```

Tên property và cách bind resource attributes tùy phiên bản registry/Spring Boot. Micrometer OTLP registry cũng hỗ trợ resource attributes từ các biến môi trường OpenTelemetry như OTEL_RESOURCE_ATTRIBUTES và OTEL_SERVICE_NAME theo cấu hình mặc định.

Resource attributes thường có các trường như telemetry.sdk.name, telemetry.sdk.language, telemetry.sdk.version và service.name. Nếu service.name không được cấu hình đúng, dữ liệu có thể xuất hiện dưới unknown_service. Xác minh resource attributes ở backend thay vì chỉ tin rằng YAML đã được load.

### Resource attributes khác meter tags

| Resource attribute | Meter tag |
| --- | --- |
| Mô tả nguồn/instance/service tạo telemetry | Phân loại một meter |
| Áp dụng cho nhóm metrics của resource | Có thể thay đổi theo meter |
| Ví dụ service.name | Ví dụ payment.method |
| Group theo service/environment | Dimension của từng series |

Không lặp metadata vào cả resource và mọi meter tag nếu backend không cần; việc này có thể làm query khó hơn hoặc tăng cardinality.

## 8. Headers và authentication

OTLP receiver có thể yêu cầu authorization header. Spring Boot cho phép cấu hình custom headers qua namespace management.otlp.metrics.export.headers.

Ví dụ cú pháp:

```yaml
management:
  otlp:
    metrics:
      export:
        url: https://otlp.example.com/v1/metrics
        headers:
          Authorization: Bearer token-managed-outside-source
```

Đây là giá trị minh họa; không commit token thật vào repository. Dùng secret manager, Kubernetes Secret hoặc cơ chế quản lý credential của nền tảng. Xác nhận tên header/định dạng auth theo receiver.

Bảo vệ đường truyền bằng TLS; cấp token chỉ có quyền ingest cần thiết; thiết lập rotation/expiry; không in headers nhạy cảm vào logs và dùng tenant/project scoping nếu backend hỗ trợ.

## 9. Compression và payload size

Payload OTLP có thể lớn khi có nhiều meters, tags hoặc histogram buckets. Gzip có thể giảm byte truyền nhưng làm tăng CPU và chi phí xử lý.

```yaml
management:
  otlp:
    metrics:
      export:
        compression-mode: gzip
        batch-size: 5000
```

Đo số meters active, số data points mỗi lần export, payload trước/sau nén, CPU, network throughput và tỷ lệ lỗi do payload vượt giới hạn receiver.

Batch nhỏ có thể giảm kích thước mỗi request nhưng tăng request count; batch lớn giảm overhead nhưng có thể tăng memory và rủi ro payload lớn. Chọn theo receiver và workload.

## 10. Micrometer meter types được ánh xạ sang OTLP

| Micrometer meter | OTLP data point thường gặp |
| --- | --- |
| Counter, FunctionCounter | Sum |
| Gauge, TimeGauge, MultiGauge | Gauge |
| Timer | Histogram hoặc Summary theo cấu hình |
| DistributionSummary | Histogram hoặc Summary |
| LongTaskTimer | Mapping phụ thuộc implementation |
| FunctionTimer | Sum/count theo hỗ trợ của registry |

OTLP có Sums, Gauges, Histograms, Exponential Histograms và Summaries. Chi tiết mapping thuộc phiên bản Micrometer registry. Không giả định mọi Meter type có mọi statistical fields; một số mapping chỉ xuất count/sum.

Xem [Micrometer OTLP](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html) để biết mapping và giới hạn của phiên bản.

## 11. Histogram, percentile và SLO

Muốn query latency percentile, xác nhận Timer được cấu hình histogram/distribution phù hợp và backend hỗ trợ data point đó.

Ví dụ một configuration class minh họa MeterFilter:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterFilter timerFilter() {
        return MeterFilter.maxExpected(
                "http.server.requests",
                java.time.Duration.ofSeconds(10));
    }
}
```

Filter trên giới hạn expected value; nó không tự bật histogram cho mọi phiên bản/registry. Cần cấu hình distribution/percentile phù hợp theo Micrometer/Spring Boot của dự án, rồi xác minh OTLP data point ở backend.

Histogram không miễn phí. Nhiều route, status, method và bucket có thể nhân tổng số data points. Chỉ dùng low-cardinality tags như route template (/orders/{id}), method, status group, application và environment. Không gắn traceId, user.id, order.id hoặc session ID làm metric tags.

## 12. Exemplars và liên kết với traces

Micrometer OTLP registry hỗ trợ OTLP exemplars. Trong Spring Boot, ExemplarContextProvider có thể cung cấp exemplar context; với Micrometer Tracing, provider có thể được auto-configure. Cấu hình hiện hành mặc định chỉ đưa sampled traces vào exemplars.

Exemplar mang tham chiếu trace trong một metric observation, giúp đi từ metric sang trace nếu backend và dashboard hỗ trợ. Cần kiểm tra:

1. Tracing context hiện hành ở lúc đo.
2. Registry/exemplar provider hỗ trợ.
3. OTLP exporter encode exemplar.
4. Collector giữ exemplar khi xử lý/forward.
5. Metrics backend lưu exemplar.
6. Dashboard có trace datasource và mapping.

Không giả định bật OTLP metrics là có correlation. Cần tracing pipeline riêng và sampled trace vẫn còn trong retention.

## 13. Collector nhận OTLP metrics

Một Collector pipeline có receiver, processor và exporter. Ví dụ receiver OTLP/HTTP dùng để kiểm thử local:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 1024

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

Exporter debug chỉ dùng để xác minh Collector nhận dữ liệu trong local/test. Production cần exporter tới metrics backend và cấu hình TLS/auth, retry/queue, resource limits.

Ứng dụng phải kết nối tới OTLP/HTTP endpoint mà Collector lắng nghe. Với receiver trên, path metrics thường là /v1/metrics. Nếu chỉ bật gRPC trên 4317 mà ứng dụng gửi HTTP, request sẽ thất bại.

Collector không tự tạo backend. Receiver hoạt động không có nghĩa backend lưu dữ liệu. Theo dõi Collector internal telemetry, accepted/refused points, send failures, queue saturation và retries.

## 14. Kiểm thử OTLP metrics end-to-end

Không dừng ở việc ứng dụng khởi động. Kiểm tra theo tầng:

1. **MeterRegistry:** tạo request nghiệp vụ hoặc Counter thử nghiệm; xác minh meter có trong registry/Actuator metrics nếu endpoint được expose.
2. **Registry OTLP:** xác nhận micrometer-registry-otlp có trong runtime, auto-configuration tạo registry và endpoint property được bind.
3. **Export request:** dùng Collector/receiver test; xác minh request tới đúng URL /v1/metrics, response hợp lệ và payload được chấp nhận.
4. **Resource/dimensions:** kiểm tra service.name, environment, meter name, unit, tags, temporality và histogram data points.
5. **Query:** tạo traffic có kiểm soát; so sánh counter/rate với thao tác đã thực hiện trong cùng cửa sổ. Với Timer, đối chiếu count và sum; muốn p95 thì xác nhận histogram thực sự tồn tại.
6. **Lỗi receiver:** thử endpoint sai, auth sai hoặc Collector dừng trong môi trường test. Quan sát export errors/timeouts và xác minh business request không hỏng.
7. **Recovery:** khôi phục Collector/backend và quan sát registry tiếp tục export ở chu kỳ sau.

Không giả định mọi data points bị mất trong thời gian offline đều được replay. Hành vi phụ thuộc registry, aggregation temporality, buffer và lifecycle process.

## 15. Vận hành khi export lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
| --- | --- | --- |
| Không thấy metrics ở Collector | Sai URL, protocol, DNS hoặc network | Endpoint, port, path /v1/metrics |
| HTTP 404 | Sai path hoặc receiver route | OTLP/HTTP receiver và metrics path |
| HTTP 401/403 | Token/header sai hoặc thiếu quyền | Secret, auth config, tenant scope |
| TLS handshake failed | CA/certificate/SNI không hợp lệ | Trust store, SSL bundle, hostname |
| Export timeout | Receiver/backend chậm hoặc network nghẽn | Connect/read timeout, latency, queue |
| Payload rejected | Schema, payload size hoặc point type | Receiver response và registry version |
| Một số meter thiếu | Filter, meter chưa register hoặc batch/export failure | MeterRegistry, filters, exporter logs |
| Không query được p95 | Histogram chưa bật hoặc backend không hỗ trợ | Data point type và histogram config |
| Service thành unknown_service | Resource identity chưa cấu hình | service.name và OTEL resource attributes |
| Values nhảy sau restart | Cumulative reset/temporality handling | Start timestamps và backend semantics |

### Bảo vệ ứng dụng

- Giới hạn connect/read timeout.
- Không để exporter retry vô hạn trên request thread.
- Theo dõi queue/buffer và memory khi có hỗ trợ.
- Theo dõi exporter errors và Collector queue.
- Không biến telemetry failure thành business failure ngoài yêu cầu nghiệp vụ rõ ràng.
- Không log secret hoặc payload nhạy cảm.

Không tuyên bố zero data loss nếu chưa thử nghiệm. Registry theo step có thể chỉ giữ state trong process; restart hoặc mất kết nối có thể làm mất measurements chưa publish.

## 16. Khi nào nên dùng OTLP metrics?

| Điều kiện | OTLP metrics phù hợp khi |
| --- | --- |
| Có Collector/backend hỗ trợ OTLP | Có receiver/endpoint được quản trị |
| Muốn vendor-neutral transport | Không gắn ứng dụng với API riêng |
| Cần route/transform ở Collector | Có policy tập trung |
| Nhiều tín hiệu telemetry | Muốn quy ước resource metadata nhất quán |
| Network chỉ cho outbound | Ứng dụng gửi OTLP outbound tới collector |
| Backend có query model riêng | Đã xác nhận hỗ trợ temporality/histogram cần dùng |

OTLP không tự động tốt hơn Prometheus scrape. Chọn theo topology, vận hành, query model, retention và SLO. Có thể dùng cả hai pipeline nếu cần, nhưng tránh duplicate ingestion và kiểm soát cardinality.

## 17. Bài thực hành: xuất Counter và Timer qua OTLP

Thực hiện trong local/test với một Collector OTLP/HTTP:

1. Thêm Actuator và micrometer-registry-otlp qua dependency management.
2. Cấu hình management.otlp.metrics.export.url trỏ tới Collector /v1/metrics.
3. Khai báo service.name và environment metadata.
4. Tạo Counter checkout.accepted và Timer checkout.processing.
5. Gửi request test có kết quả thành công và lỗi.
6. Quan sát Collector nhận metrics và backend hiển thị đúng resource/tags.
7. Thử histogram nếu cần p95/p99; xác minh data point thực tế.
8. Dừng Collector trong test, quan sát exporter behavior và recovery.
9. Kiểm tra metrics vẫn ghi đủ request theo instrumentation dù trace sampling ở tỷ lệ thấp hơn.

Kết quả cần ghi lại:

| Hạng mục | Bằng chứng |
| --- | --- |
| Dependency | Registry OTLP có trong runtime |
| Endpoint | URL/protocol/path kết nối được |
| Export | Collector accepted metrics |
| Resource | Service/environment đúng |
| Meter | Counter/Timer có name/unit đúng |
| Temporality | Backend đọc đúng cumulative hoặc delta |
| Distribution | Histogram có data points cần thiết |
| Resilience | Timeout/failure không làm business request lỗi |
| Data quality | Không có tag high-cardinality không cần thiết |

## 18. Câu hỏi tự kiểm tra

1. OTLP là giao thức hay metrics backend?
2. Trong Spring Boot, thành phần nào quản lý metrics khi xuất qua OTLP?
3. Vì sao không nhầm Micrometer OtlpMeterRegistry với OpenTelemetry SdkMeterProvider?
4. Dependency nào cung cấp OTLP registry cho Micrometer?
5. Endpoint OTLP/HTTP metrics thường dùng path nào?
6. step khác Prometheus scrape interval thế nào?
7. Cumulative và delta aggregation temporality khác nhau ra sao?
8. Vì sao backend phải biết temporality?
9. Resource attribute service.name khác meter tag application thế nào?
10. batch-size, connect timeout và read timeout ảnh hưởng gì?
11. Micrometer meter types nào được ánh xạ thành OTLP metrics?
12. Muốn p95 latency, cần xác minh histogram ở những tầng nào?
13. OTLP exemplar cần các thành phần nào để mở trace?
14. Vì sao receiver nhận payload không có nghĩa backend đã lưu metrics?
15. Khi Collector unavailable, vì sao không giả định mọi samples được replay?

## Tài liệu tham khảo

- [Spring Boot — Metrics and OTLP](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): dependency registry, URL, custom headers và OTLP metrics export.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): vai trò Micrometer và khác biệt với OpenTelemetry MeterProvider.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): các property management.otlp.metrics.export.
- [Micrometer — OTLP Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html): cấu hình, temporality, compression, resource attributes và meter mapping.
- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/): transport và protocol OTLP.
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/): receiver, processor, exporter và pipeline.

## Kết luận

**OTLP metrics trong Spring Boot là đường xuất metrics do Micrometer quản lý tới hệ thống hỗ trợ OTLP.** Thêm micrometer-registry-otlp, cấu hình management.otlp.metrics.export, xác định resource attributes và bảo đảm receiver/backend tương thích là những phần thiết yếu. step, batch, timeout, compression, temporality, histogram và headers quyết định chất lượng cũng như độ tin cậy của pipeline.

Khi vận hành, kiểm chứng từng tầng từ meter trong ứng dụng tới registry, Collector và backend; theo dõi exporter errors, queue, service identity và cardinality. Giữ rõ ranh giới giữa metrics, traces và logs: OTLP metrics không tự xuất spans/logs, nhưng khi các pipeline được cấu hình nhất quán, chúng cùng hỗ trợ điều tra lỗi và độ trễ.

