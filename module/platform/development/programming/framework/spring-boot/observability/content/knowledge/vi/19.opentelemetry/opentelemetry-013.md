# Không nhầm OTel metrics với Micrometer metrics

Một ứng dụng Spring Boot có thể dùng Micrometer để đo số request, thời gian xử lý và connection pool, trong khi một thư viện bên thứ ba lại tự tạo metric bằng OpenTelemetry API. Cả hai đều được gọi là metrics và có thể gửi tới cùng một hệ thống quan sát, nhưng chúng không tự động dùng chung registry hoặc cùng một đường export. Vì vậy dashboard có thể thấy metrics do Spring Boot tạo ra nhưng bỏ sót metrics do thư viện OpenTelemetry tạo ra.

Bài **Không nhầm OTel metrics với Micrometer metrics** thuộc chương **OpenTelemetry** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc:** Trong hệ sinh thái Spring Boot, **Micrometer là lựa chọn metrics chính**. Micrometer cung cấp API đo lường và MeterRegistry cho ứng dụng; registry cụ thể xuất dữ liệu tới Prometheus, OTLP hoặc backend khác. OpenTelemetry Metrics có API/SDK riêng (Meter, MeterProvider, SdkMeterProvider). Việc dùng OTLP **không đồng nghĩa** ứng dụng đang dùng OpenTelemetry Metrics SDK: OtlpMeterRegistry vẫn là registry của Micrometer, chỉ xuất dữ liệu theo OTLP.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Micrometer metrics API, MeterRegistry và OpenTelemetry Metrics API/SDK.
2. Giải thích vì sao Spring Boot mặc định dùng Micrometer cho metrics.
3. Hiểu OtlpMeterRegistry là Micrometer registry xuất theo OTLP, không phải OpenTelemetry SdkMeterProvider.
4. Nhận ra vì sao metrics do thư viện dùng OTel MeterProvider tạo có thể không xuất cùng pipeline Micrometer.
5. Phân biệt OTel tracing support với OTel metrics support trong Spring Boot.
6. Hiểu vai trò của Micrometer Observation và các handler khi tạo metrics/traces.
7. Cấu hình một pipeline Micrometer OTLP, Prometheus hoặc backend phù hợp.
8. Biết khi nào cần cấu hình riêng OpenTelemetry MeterProvider cho dependency.
9. Tránh đo trùng một operation bằng Micrometer và OTel instrumentation.
10. Kiểm tra tên metric, unit, temporality, histogram và resource labels qua pipeline.

## 2. Hai hệ metrics, hai API và hai pipeline

**Micrometer** là facade metrics trong hệ sinh thái Java/Spring. Code tạo Counter, Timer, Gauge, DistributionSummary qua API Micrometer, sau đó meter được đăng ký vào một hoặc nhiều MeterRegistry.

**OpenTelemetry Metrics** định nghĩa API và SDK riêng. Code lấy meter từ OpenTelemetry/MeterProvider, tạo instruments như Counter, Histogram, ObservableGauge; SDK quản lý aggregation, temporality, readers và exporter.

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["Micrometer API"]
    A --> C["OpenTelemetry Metrics API<br/>(nếu dependency dùng trực tiếp)"]
    B --> D["MeterRegistry"]
    D --> E["Prometheus / OTLP / SaaS Registry"]
    E --> F["Metrics backend"]
    C --> G["OpenTelemetry MeterProvider"]
    G --> H["MetricReader / Exporter"]
    H --> I["OTLP Collector / backend"]
    I --> F
~~~

Hai pipeline có thể cùng gửi tới một backend, nhưng **không tự đồng bộ dữ liệu**. Cần xác định API nào tạo metric, registry/provider nào nhận instrument, reader/exporter nào xuất dữ liệu và Resource/attributes nào đi cùng.

| Câu hỏi | Micrometer | OpenTelemetry Metrics |
|---|---|---|
| API chính | MeterRegistry, Counter, Timer, Gauge | MeterProvider, Meter, LongCounter, Histogram, ObservableGauge |
| Đăng ký instrument | MeterRegistry | Meter từ MeterProvider |
| Quản lý/export | Registry implementation | SDK MetricReader, exporter, aggregation pipeline |
| Spring Boot mặc định | Có auto-configuration qua Actuator | Không tự động tạo toàn bộ OTel Metrics SDK pipeline |
| Export OTLP | OtlpMeterRegistry | OTel OTLP metric exporter/reader |
| Endpoint chẩn đoán | /actuator/metrics, có thể /actuator/prometheus | Tùy SDK/exporter; không tự có Actuator Micrometer endpoint |
| Mục tiêu chính | Metrics Spring ecosystem, nhiều monitoring backends | Metrics theo OpenTelemetry API/data model và OTLP pipeline |

## 3. Micrometer metrics trong Spring Boot

Spring Boot Actuator auto-configure Micrometer và tạo composite MeterRegistry. Registry cụ thể được thêm vào composite tùy implementation có trên classpath. Ví dụ có thể dùng Prometheus, OTLP, Datadog, StatsD hoặc Simple in-memory registry.

Một service tạo metric thường chỉ phụ thuộc API Micrometer:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutMetrics {

    private final Counter approved;

    public CheckoutMetrics(MeterRegistry registry) {
        this.approved = Counter.builder("checkout.authorization.result")
                .description("Number of approved authorizations")
                .tag("outcome", "approved")
                .register(registry);
    }

    public void authorizationApproved() {
        approved.increment();
    }
}
~~~

Code không cần biết backend là Prometheus hay OTLP. Registry được Spring Boot cấu hình sẽ nhận measurement và xuất theo implementation tương ứng.

### 3.1 MeterRegistry là abstraction; backend registry mới thực hiện export

- SimpleMeterRegistry: giữ measurements trong memory để test/chẩn đoán.
- PrometheusMeterRegistry: cung cấp dữ liệu theo format Prometheus scrape.
- OtlpMeterRegistry: xuất metrics từ Micrometer theo OTLP.
- Registry vendor-specific: xuất theo giao thức của backend tương ứng.

Chỉ inject MeterRegistry không đủ chứng minh dữ liệu đã rời khỏi JVM. Cần có registry có exporter hoạt động và backend/Collector tiếp nhận.

### 3.2 Observation cũng thường tạo Micrometer metrics

Spring Boot dùng Micrometer Observation cho metrics và tracing. Ví dụ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class InventoryObservation {

    private final ObservationRegistry observations;

    public InventoryObservation(ObservationRegistry observations) {
        this.observations = observations;
    }

    public void reserve() {
        Observation.createNotStarted("inventory.reserve", observations)
                .lowCardinalityKeyValue("result", "success")
                .observe(this::reserveInventory);
    }

    private void reserveInventory() {
        // Thực hiện nghiệp vụ.
    }
}
~~~

Khi Spring Boot auto-configure DefaultMeterObservationHandler, observation hoàn tất có thể tạo timer/metrics qua Micrometer. Nếu tracing handler cũng được cài đặt, observation có thể tạo span. Điều này không có nghĩa Micrometer metrics đã được chuyển thành OTel SDK metrics.

## 4. OpenTelemetry Metrics API và SDK

OpenTelemetry cung cấp một mô hình riêng:

- **MeterProvider:** điểm truy cập tạo Meter.
- **Meter:** nhóm instrument theo instrumentation scope.
- **Instruments:** Counter, UpDownCounter, Histogram, ObservableGauge và các loại tương ứng.
- **MetricReader:** thu thập/đọc các metric streams từ SDK.
- **Exporter:** serialize và chuyển dữ liệu tới nơi nhận, ví dụ OTLP.
- **Resource:** nhận diện service/process phát telemetry.
- **Attributes:** các chiều phân nhóm data points.

Ví dụ dùng OpenTelemetry API trực tiếp:

~~~java
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.OpenTelemetry;

public class OTelCheckoutMetrics {

    private final LongCounter approved;

    public OTelCheckoutMetrics(OpenTelemetry openTelemetry) {
        Meter meter = openTelemetry.getMeter("com.example.checkout");
        this.approved = meter.counterBuilder("checkout.authorization.approved")
                .setDescription("Approved checkout authorizations")
                .setUnit("{authorization}")
                .build();
    }

    public void recordApproved() {
        approved.add(1);
    }
}
~~~

Ví dụ này tạo instrument qua OpenTelemetry API. Nó **không đăng ký Counter vào Micrometer MeterRegistry**. Việc nó có được export hay không phụ thuộc OpenTelemetry object đang kết nối tới MeterProvider nào và provider đó có reader/exporter phù hợp hay không.

### 4.1 API có thể tồn tại mà SDK pipeline không tồn tại

Một dependency có thể phụ thuộc opentelemetry-api và gọi GlobalOpenTelemetry.getMeter(...). Nếu runtime không cung cấp một SDK MeterProvider có cấu hình, API có thể hoạt động với noop/default behavior hoặc provider không có export reader. Khi đó metric không xuất hiện trong Micrometer registry và cũng không tự đi vào OTLP.

Một OpenTelemetry bean hoặc tracing provider cũng không tự chứng minh đã có Metrics SDK provider/exporter hoàn chỉnh. Kiểm tra đúng MeterProvider và pipeline metrics.

## 5. Điều Spring Boot hiện hành làm và không làm

Trong Spring Boot hiện hành, metrics trong hệ sinh thái Spring được thu thập qua **Micrometer**. Tài liệu Spring Boot nêu rõ metrics không được thu thập/export thông qua OpenTelemetry SdkMeterProvider mặc định; Spring Boot không cung cấp SdkMeterProvider bean mặc định. Thay vào đó, Micrometer metrics có thể được export qua OTLP bằng OtlpMeterRegistry.

Một dependency dùng OpenTelemetry MeterProvider trực tiếp cũng không có nghĩa metrics của nó được Spring Boot export tự động. Nếu dependency đó cần OTel Metrics SDK, ứng dụng phải cung cấp/cấu hình MeterProvider phù hợp và wiring nó vào dependency. Hãy kiểm tra đúng phiên bản Spring Boot vì auto-configuration và starter có thể thay đổi theo major release.

| Khả năng | Spring Boot Micrometer path | OpenTelemetry Metrics SDK path |
|---|---|---|
| Metrics mặc định của Spring Boot | Có | Không mặc định |
| Bean MeterRegistry | Có, qua Actuator | Không thay thế bởi SdkMeterProvider |
| Bean SdkMeterProvider mặc định | Không | Cần cấu hình khi sử dụng OTel Metrics SDK |
| HTTP server/JVM metrics của Boot | Micrometer meters/observations | Không tự xuất qua OTel SDK |
| Micrometer metrics gửi OTLP | Có thể qua OtlpMeterRegistry | Không cần OTel SDK MeterProvider |
| Instrument OTel API của dependency | Không tự vào Micrometer registry | Cần MeterProvider/reader/exporter và wiring |
| Actuator /actuator/metrics | Đọc Micrometer registry | Không tự đọc OTel SDK instruments |

### 5.1 OTel tracing có thể hoạt động trong khi OTel metrics không có

Spring Boot có thể tích hợp OpenTelemetry cho traces qua Micrometer Tracing và OTLP exporter. Điều đó **không đồng nghĩa** metrics cũng được gửi qua SdkMeterProvider. Tracing provider và metrics provider là các thành phần riêng trong OpenTelemetry SDK; chúng có exporter/readers và lifecycle riêng.

Một ứng dụng có thể đồng thời:
- Tạo observations bằng ObservationRegistry.
- Ghi metrics qua Micrometer MeterRegistry.
- Gửi traces qua Micrometer Tracing/OpenTelemetry.
- Xuất Micrometer metrics qua OtlpMeterRegistry.
- Không sử dụng OpenTelemetry Metrics SDK trực tiếp.

Đây là cấu hình hợp lệ và phù hợp với khuyến nghị Spring Boot dùng Micrometer cho metrics.

## 6. Xuất Micrometer metrics qua OTLP

Nếu mục tiêu là gửi metrics do Spring Boot/Micrometer tạo tới OpenTelemetry Collector hoặc backend nhận OTLP, cách trực tiếp là cấu hình **Micrometer OTLP registry**.

### 6.1 Dependency

Với Gradle và BOM/dependency management Micrometer/Spring Boot tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
}
~~~

Không khai báo version tùy tiện nếu Spring Boot BOM đã quản lý phiên bản Micrometer. Kiểm tra compatibility khi override Micrometer version độc lập.

### 6.2 Cấu hình endpoint OTLP

Ví dụ Spring Boot properties:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: "http://otel-collector:4318/v1/metrics"
        step: 30s
        aggregation-temporality: cumulative
        compression: gzip
        resource-attributes:
          service.namespace: commerce
          deployment.environment.name: staging
~~~

Property binding chính xác phụ thuộc Spring Boot/Micrometer version. Micrometer OTLP hiện hỗ trợ cấu hình URL, batch size, temporality, compression, headers, publish interval (step) và resource attributes. Mặc định HTTP OTLP endpoint thường là localhost:4318/v1/metrics và publish interval mặc định một phút nếu không ghi đè.

Trong môi trường thật:
- Đặt endpoint Collector có thể truy cập từ application network.
- Dùng TLS và authentication theo policy hạ tầng.
- Đặt headers/secret qua secret management, không commit token vào YAML.
- Cấu hình timeout/retry/queue theo năng lực backend.
- Xác minh Collector nhận đúng signal metrics, không chỉ traces.

### 6.3 Pipeline

~~~mermaid
flowchart LR
    A["Spring Boot business code"] --> B["Micrometer MeterRegistry"]
    B --> C["OtlpMeterRegistry"]
    C --> D["OTLP HTTP /v1/metrics"]
    D --> E["OpenTelemetry Collector"]
    E --> F["Metrics backend"]
~~~

Dù protocol xuất là OTLP, instruments vẫn được tạo bằng Micrometer và được quản lý bởi Micrometer registry. Collector/backend nhận OTLP metric data points; điều đó không biến MeterRegistry thành SdkMeterProvider.

### 6.4 Resource attributes trong Micrometer OTLP registry

OtlpMeterRegistry có cấu hình Resource attributes riêng. Micrometer documentation mô tả các mặc định như telemetry.sdk.name=io.micrometer, telemetry.sdk.language=java, version của Micrometer và service.name=unknown_service. Có thể cấu hình attributes qua management.otlp.metrics.export.resource-attributes; OTEL_RESOURCE_ATTRIBUTES và OTEL_SERVICE_NAME cũng được hỗ trợ theo hành vi registry hiện hành.

Không mặc định OtlpMeterRegistry dùng chính bean Resource của OpenTelemetry SDK do Spring Boot tạo. Xác nhận resource labels thực tế ở payload/backend và cấu hình nguồn service identity rõ ràng.

## 7. Xuất Micrometer metrics qua Prometheus

Một lựa chọn khác là Prometheus registry. Đây vẫn là Micrometer metrics:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Cấu hình endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
~~~

Sau khi ứng dụng chạy và phát sinh traffic:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/prometheus
~~~

/actuator/metrics dùng meter name gốc của Micrometer; /actuator/prometheus trả exposition format cho Prometheus scrape khi registry và endpoint đã được cấu hình/expose.

Prometheus có thể scrape ứng dụng trực tiếp. OTLP Collector cũng có thể nhận metrics từ các nguồn OTLP khác. Hai backend pathways có thể cùng tồn tại nhưng cần chủ động tránh scrape/export trùng một tập metrics.

## 8. OTel Metrics SDK khi dependency yêu cầu trực tiếp

Có trường hợp một dependency chỉ cung cấp instrumentation qua OpenTelemetry Metrics API. Nếu muốn nhận metrics ấy, cần cung cấp một OTel SDK pipeline thực sự.

Về kiến trúc, cần:

1. Một OpenTelemetry SDK/MeterProvider có cấu hình Resource.
2. Một metric reader (ví dụ periodic exporting reader).
3. Một exporter tương ứng, chẳng hạn OTLP exporter.
4. Một bean/provider được dependency instrumentation sử dụng.
5. Lifecycle đóng/shutdown đúng khi ứng dụng dừng.
6. Một pipeline nhận OTLP riêng hoặc dùng chung Collector với các signal khác.

~~~mermaid
flowchart TD
    A["Dependency instrumentation"] --> B["OpenTelemetry Metrics API"]
    B --> C["SdkMeterProvider"]
    C --> D["Periodic MetricReader"]
    D --> E["OTLP Metric Exporter"]
    E --> F["Collector"]
    F --> G["Metrics backend"]
~~~

Spring Boot Actuator có thể cung cấp OpenTelemetry API bean và đăng ký một số OTel SDK provider beans nếu ứng dụng tự cung cấp chúng, tùy phiên bản. Nhưng không nên giả định nó tự tạo SdkMeterProvider và OTLP metrics exporter. Nếu khai báo bean, wiring dependency vào đúng instance/provider; không để dependency gọi global singleton khác với bean được cấu hình.

### 8.1 Ví dụ kiến trúc SDK riêng

Pseudo-code minh họa các thành phần (không phải cấu hình copy/paste cho mọi Boot version):

~~~java
// Pseudocode: builders/dependencies tùy OpenTelemetry SDK version.
Resource resource = Resource.getDefault()
        .merge(Resource.create(Attributes.of(
                AttributeKey.stringKey("service.name"),
                "order-service")));

SdkMeterProvider meterProvider = SdkMeterProvider.builder()
        .setResource(resource)
        .registerMetricReader(periodicReader)
        .build();

OpenTelemetry openTelemetry = OpenTelemetrySdk.builder()
        .setMeterProvider(meterProvider)
        .build();
~~~

Đoạn này chỉ minh họa kiến trúc; periodicReader phải được tạo từ exporter phù hợp và OpenTelemetry instance phải được đưa tới dependency dùng OTel Metrics API. Tự khai báo provider cần quan tâm shutdown/lifecycle và tránh tạo nhiều provider cùng instrument.

### 8.2 Không tự tạo OTel SDK chỉ để “metrics có chữ OpenTelemetry”

Nếu code ứng dụng đã dùng Micrometer và mục tiêu chỉ là export tới backend nhận OTLP, thêm một SdkMeterProvider riêng thường không cần thiết. Dùng OtlpMeterRegistry đơn giản hơn, phù hợp với Spring Boot metrics auto-configuration và giữ application instrumentation nhất quán.

Chỉ thêm OTel Metrics SDK khi dependency/framework thực sự cần OTel API hoặc có yêu cầu kiến trúc cụ thể để dùng native OTel metrics.

## 9. Semantic conventions: tên metric không tự động giống nhau

Micrometer và OpenTelemetry có conventions về naming, unit, attributes, aggregation. Dùng cùng OTLP protocol không bảo đảm tên metric và dimensions của hai API trùng nhau.

Spring Boot mặc định dùng Micrometer/Spring conventions cho observations. Có thể yêu cầu dùng OpenTelemetry stable semantic conventions cho các conventions mà Spring Boot hỗ trợ:

~~~yaml
management:
  observations:
    conventions: open-telemetry
~~~

Điều này thay đổi convention được dùng cho observations tương ứng; **không chuyển engine metrics từ Micrometer sang OpenTelemetry SdkMeterProvider**. Một số custom property đổi tên meter có thể không còn tác dụng khi chọn OTel conventions. Không phải mọi custom metric name đều tự được chuyển đổi.

### 9.1 Ví dụ khác biệt trong HTTP metrics

Ứng dụng có thể phát metric tên http.server.requests theo convention Micrometer/Spring; khi chọn OTel conventions, tên/attribute mapping cho observations có thể theo OpenTelemetry conventions ổn định mà Spring Boot hỗ trợ. Query/dashboard cũ có thể cần cập nhật khi đổi convention.

Đừng suy luận rằng chỉ đổi convention property sẽ:
- Tạo thêm OTel MeterProvider.
- Bật OTLP export.
- Thêm Collector pipeline.
- Làm metric do dependency dùng OTel API tự xuất.

Convention trả lời “đặt tên và mô tả metric thế nào”; registry/provider trả lời “ai sở hữu instrument và dữ liệu đi qua đâu”.

## 10. Mapping instrument và data point khi Micrometer export OTLP

OtlpMeterRegistry chuyển các Micrometer meters thành các loại OTLP metric data points phù hợp. Một số mapping thường gặp theo tài liệu Micrometer:

| Micrometer meter | OTLP data point thường dùng |
|---|---|
| Counter, FunctionCounter | Sum |
| Gauge, TimeGauge, MultiGauge | Gauge |
| Timer, DistributionSummary | Histogram hoặc Exponential Histogram tùy cấu hình |
| LongTaskTimer, FunctionTimer | Histogram/Summary mapping theo hỗ trợ; FunctionTimer có giới hạn sum/count |
| Client-side percentiles | Summary data point khi chỉ publish percentiles |

Với Timer và DistributionSummary, cấu hình histogram/SLO ảnh hưởng loại data point. Micrometer OTLP hiện ưu tiên histogram cho timer/summary khi không yêu cầu chỉ client-side percentiles; Summary data point trong OTLP được xem là legacy cho percentile đã tính sẵn và không khuyến nghị cho ứng dụng mới.

### 10.1 Histogram và percentile không giống nhau

- **Histogram:** dữ liệu bucket/count/sum có thể được tổng hợp giữa instances để ước lượng percentile.
- **Client-side percentile:** ứng dụng tính percentile trước khi export; kết quả thường không thể gộp chính xác giữa các instances như histogram.
- **SLO buckets:** bucket được chọn theo ranh giới mục tiêu dịch vụ, hữu ích cho alert/query tương ứng.
- **Temporality:** cumulative hoặc delta ảnh hưởng cách additive measurements được biểu diễn qua thời gian.

Ví dụ cấu hình SLO cho timer:

~~~yaml
management:
  metrics:
    distribution:
      slo:
        checkout.payment.duration: 0.1s,0.3s,0.5s,1s
~~~

Cấu hình minh họa cách chọn bucket boundaries cho meter name; key binding thực tế cần đúng format property của Spring Boot version. Xác minh exporter/backend nhận histogram data point và query dùng đúng temporality.

## 11. Cardinality và tags/attributes

Micrometer tags và OTel attributes đều tạo dimensions cho metric data. Khi giá trị có quá nhiều khả năng, số time series có thể tăng nhanh.

Không dùng các giá trị gần như duy nhất cho mỗi request:

~~~java
// Tránh tạo một metric series cho mỗi request.
Counter.builder("checkout.requests")
        .tag("orderId", orderId)
        .register(registry)
        .increment();
~~~

Nên dùng dimensions ổn định, hữu hạn:

~~~java
Counter.builder("checkout.requests")
        .tag("outcome", "approved")
        .tag("channel", "mobile")
        .register(registry)
        .increment();
~~~

Quy tắc áp dụng cho cả hai metric API:

- Không đưa traceId/spanId/orderId/userId/email vào metric attributes.
- Chuẩn hóa route thành template, không dùng raw URL chứa ID.
- Giới hạn giá trị exception, status, region, channel thành tập có kiểm soát.
- Dùng logs/traces để điều tra request cụ thể.
- Dùng metrics cho xu hướng và thống kê trên nhiều request.

Nếu cùng một operation được instrument qua hai API, cardinality có thể tăng gấp đôi hoặc query bị phân mảnh do tên/tag mapping khác nhau. Chọn một instrumentation owner.

## 12. Tránh đo trùng giữa Micrometer và OpenTelemetry

Một lỗi tích hợp hay gặp là:
- Spring MVC auto-instrumentation tạo observation/Timer.
- Một OTel Java agent hoặc thư viện instrumentation khác cũng tạo metric cho cùng HTTP server request.
- Custom code bổ sung thêm Counter/Timer cho cùng operation.
- Cả hai pipelines xuất metrics đến backend và dashboard cộng hoặc hiển thị hai series.

Kết quả có thể là request count gấp đôi, latency bị so sánh sai, chi phí tăng và người vận hành không biết meter nào là canonical.

### 12.1 Chọn instrumentation owner theo boundary

| Boundary | Một lựa chọn rõ ràng |
|---|---|
| Spring MVC/WebFlux server requests | Spring Boot/Micrometer auto-observation hoặc OTel agent instrumentation sau khi quyết định convention |
| JDBC client/database | Một instrumentation implementation được chọn, không bật song song không kiểm soát |
| Business operation | Micrometer Observation hoặc OTel API theo kiến trúc |
| JVM/process metrics | Spring Boot/Micrometer binders hoặc OTel runtime instrumentation; tránh publish trùng |
| Dependency chỉ expose OTel Metrics API | Cung cấp OTel MeterProvider pipeline nếu cần metrics của dependency |

Không phải mọi OTel auto-instrumentation đều tạo metrics trùng với Spring Boot; phạm vi và signal hỗ trợ phụ thuộc agent/library version. Kiểm tra tên instrument và instrumentation scope thực tế thay vì giả định.

### 12.2 Tránh chỉ lọc tên trùng sau khi export

Nếu hai pipelines phát cùng ý nghĩa với tên khác nhau, chỉ xóa một tên khỏi dashboard có thể che lấp duplicate instrumentation chứ không xử lý nguyên nhân. Trước tiên kiểm tra nguồn tạo metric, registry/provider, scope, labels và nơi export. Sau đó disable instrumentation dư hoặc đặt convention/ownership rõ ràng.

## 13. Quy trình quyết định nên dùng metrics API nào

### Trường hợp A — Ứng dụng Spring Boot thông thường

Dùng Micrometer API và MeterRegistry; tạo custom counters/timers và Observation; chọn Prometheus, OTLP hoặc registry backend qua dependency/config. Đây là con đường mặc định trong hệ sinh thái Spring.

### Trường hợp B — Chỉ cần gửi Micrometer metrics tới OpenTelemetry Collector

Dùng micrometer-registry-otlp và cấu hình management.otlp.metrics.export. Bạn vẫn dùng Micrometer instruments và registry, còn Collector nhận OTLP metrics.

### Trường hợp C — Một dependency chỉ phát metrics bằng OTel API

Kiểm tra dependency gọi provider nào. Nếu cần metrics ấy, cung cấp/wire SdkMeterProvider, reader và exporter cho dependency; xác minh metrics không còn bị noop. Không giả định Micrometer registry sẽ tự nhận instruments của OTel.

### Trường hợp D — Ứng dụng chủ động chọn native OpenTelemetry Metrics SDK

Xây pipeline SDK/provider/exporter có chủ đích và quyết định metrics nào do Micrometer quản lý, metrics nào do OTel SDK quản lý. Cần quy ước naming, Resource, unit, cardinality, shutdown và tránh đo trùng. Với ứng dụng Spring Boot, đánh giá kỹ nhu cầu trước khi thay thế pipeline Micrometer mặc định.

## 14. Debug khi metrics bị thiếu

| Triệu chứng | Nguyên nhân có thể | Việc kiểm tra |
|---|---|---|
| /actuator/metrics có metric nhưng Collector không thấy | Micrometer registry chưa export hoặc endpoint sai | Kiểm tra registry implementation, export URL/step và exporter logs |
| OTLP traces có nhưng OTLP metrics không có | Tracing exporter đã cấu hình, Micrometer OTLP registry chưa được thêm | Kiểm tra micrometer-registry-otlp và management.otlp.metrics.export |
| OTel API dependency tạo metric nhưng backend không thấy | Không có SdkMeterProvider/reader/exporter hoặc dependency chưa được wire đúng provider | Kiểm tra provider instance, reader và SDK pipeline |
| Prometheus thấy metric nhưng OTel dashboard không thấy | Chưa có OTLP export hoặc backend không ingest Prometheus | Kiểm tra pipeline riêng |
| Metrics count tăng gấp đôi | Instrumentation trùng giữa Spring/Micrometer và OTel agent/library | Kiểm tra instrumentation scope, meter names và labels |
| Metric name khác dashboard cũ | Convention/mapping thay đổi | Kiểm tra management.observations.conventions, naming conventions và exporter |
| Resource/service name khác nhau | Micrometer OTLP resource config và OTel SDK Resource khác nhau | Kiểm tra service.name, resource attributes và Collector transform |
| Histogram không có bucket mong đợi | Chưa cấu hình histogram/SLO hoặc exporter mapping | Kiểm tra distribution properties, data point type và temporality |
| Counter rate bất thường sau restart | Counter semantics/reset và temporality/query không khớp | Xem cumulative/delta và backend query |
| Actuator metrics không thấy custom metric | Meter chưa register vào Spring MeterRegistry hoặc tag query sai | Inject registry đúng, kiểm tra meter ID/tag filters |
| Metrics không export trong thời gian ngắn | Registry publish theo step/flush interval | Chờ chu kỳ export phù hợp và kiểm tra shutdown/flush |
| Một số OTel metrics có nhưng Spring metrics thiếu | Hai provider pipelines có cấu hình khác nhau | Kiểm tra riêng từng pipeline |

## 15. Playbook: OTLP backend có traces nhưng thiếu metrics

**Tình huống:** Spring Boot đã gửi traces tới Collector. Dashboard tracing hoạt động, nhưng metrics từ Actuator không xuất hiện.

1. **Xác định nguồn metric:** meter được tạo qua MeterRegistry hay OTel MeterProvider?
2. **Kiểm tra dependency:** có micrometer-registry-otlp không nếu muốn gửi Micrometer metrics theo OTLP?
3. **Kiểm tra cấu hình Micrometer:** management.otlp.metrics.export.url, headers, step, resource attributes và enabled flags.
4. **Kiểm tra endpoint/transport:** Collector nhận đúng OTLP HTTP path /v1/metrics hoặc endpoint/transport tương ứng.
5. **Kiểm tra Collector pipeline:** receiver OTLP phải nối tới metrics pipeline và exporter backend.
6. **Kiểm tra metric resource/name:** xác minh service name, attributes và data point type.
7. **Nếu metric xuất phát từ OTel API:** kiểm tra có SdkMeterProvider, reader và exporter; Spring Boot không mặc định biến OTel API instruments thành Micrometer meters.
8. **Kiểm tra instrumentation trùng:** so sánh metric count/name/scope nếu đã bật agent và Spring instrumentation cùng lúc.

Không thêm OTel SDK MeterProvider chỉ vì traces đang chạy; trước hết xác định metrics bị thiếu thuộc API nào.

## 16. Bài tập tự kiểm tra

**Bài 1 — Phân biệt API.** Một service inject MeterRegistry và tạo Timer. Nó có đang dùng OpenTelemetry Metrics SDK không? Giải thích.

**Bài 2 — OTLP registry.** Dự án thêm micrometer-registry-otlp. Vì sao metrics gửi tới Collector theo OTLP vẫn là Micrometer metrics?

**Bài 3 — Dependency dùng OTel API.** Một thư viện gọi openTelemetry.getMeter(...).counterBuilder(...), nhưng metric không thấy ở backend. Nêu các thành phần pipeline cần kiểm tra.

**Bài 4 — Traces có, metrics không.** Spring Boot đã cấu hình Micrometer Tracing và OTLP trace exporter. Vì sao điều này không bảo đảm metrics được gửi theo OTLP?

**Bài 5 — Convention property.** Đặt management.observations.conventions=open-telemetry có chuyển MeterRegistry sang OTel SdkMeterProvider không? Property này thay đổi điều gì?

**Bài 6 — Duplicate instrumentation.** Spring MVC auto-observation và OTel agent cùng đo HTTP server request. Hãy nêu triệu chứng có thể xuất hiện và cách xác định nguồn duplicate.

**Bài 7 — Cardinality.** Một Counter có tag traceId. Vì sao không phù hợp dù backend hỗ trợ OTLP?

**Bài 8 — Chọn pipeline.** Ứng dụng chỉ muốn export Micrometer metrics tới OpenTelemetry Collector. Cần dependency và cấu hình gì? Khi nào mới cần native OTel Metrics SDK?

### Gợi ý trả lời

1. Không. Đó là Micrometer API; MeterRegistry sở hữu meter.
2. OTLP là protocol/export format; OtlpMeterRegistry vẫn là implementation của Micrometer MeterRegistry.
3. Kiểm tra MeterProvider, SdkMeterProvider, MetricReader, exporter, Resource và dependency wiring.
4. Tracing và metrics là các provider/export pipelines riêng. Spring Boot không tự export OTel SDK metrics; Micrometer metrics cần registry tương ứng.
5. Không. Nó chọn OpenTelemetry stable semantic conventions cho observations được hỗ trợ; không thay registry/SDK engine.
6. Count trùng, series gần giống nhau, instrumentation scope khác; kiểm tra agent/library và Spring observations, rồi chọn một owner cho boundary.
7. Trace ID gần như duy nhất mỗi request tạo series cardinality rất cao; dùng logs/traces để tìm request cụ thể.
8. Thêm micrometer-registry-otlp, cấu hình management.otlp.metrics.export; native OTel SDK chỉ cần khi dependency/app thực sự dùng OTel Metrics API hoặc có yêu cầu riêng.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Spring Boot dùng Micrometer cho metrics, OTel support, conventions và giới hạn auto-configuration.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registries, Actuator endpoints và custom metrics.
- [Micrometer — OTLP Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html): OtlpMeterRegistry, configuration, resource attributes và mapping data points.
- [Micrometer — Registry Concepts](https://docs.micrometer.io/micrometer/reference/concepts/registry.html): MeterRegistry, composite và registry implementations.
- [OpenTelemetry — Metrics API](https://opentelemetry.io/docs/specs/otel/metrics/api/): MeterProvider, Meter và instruments.
- [OpenTelemetry — Metrics SDK](https://opentelemetry.io/docs/specs/otel/metrics/sdk/): MetricReader, aggregation, collection và export SDK.
- [OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): data points, temporality và aggregation.
- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/): transport và export telemetry data.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle và handlers cho metrics/tracing.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure và bảo vệ metrics endpoints.

**Ghi nhớ:** Micrometer và OpenTelemetry Metrics là hai API/SDK metrics riêng. Spring Boot dùng Micrometer làm con đường metrics mặc định; OtlpMeterRegistry gửi Micrometer meters bằng OTLP nhưng không phải SdkMeterProvider. Metrics do dependency tạo qua OTel API cần OTel Metrics SDK pipeline được cấu hình và wiring riêng nếu muốn export. Phân loại nguồn instrument trước khi debug, chọn một instrumentation owner cho mỗi boundary, kiểm tra registry/provider và Collector pipeline, rồi đối chiếu naming, Resource, temporality và cardinality để tránh mất hoặc đếm trùng metrics.

