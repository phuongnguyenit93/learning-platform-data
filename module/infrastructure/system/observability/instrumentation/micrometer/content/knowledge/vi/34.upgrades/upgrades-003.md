# Chuyển thế hệ Prometheus Java Client và các ràng buộc đăng ký

Prometheus Java Client có hai thế hệ API thường gặp trong các ứng dụng Java. Thế hệ cũ, thường được gọi là **simpleclient 0.x**, dùng package `io.prometheus.client` và `CollectorRegistry`. Thế hệ mới, **Prometheus Java Client 1.x**, được chia thành các module nhỏ hơn, dùng package `io.prometheus.metrics.*` và `PrometheusRegistry`.

Khi nâng cấp Micrometer, cần xác định ứng dụng đang sử dụng client trực tiếp hay chỉ dùng Micrometer làm facade. Nếu ứng dụng chỉ gọi `MeterRegistry`, phần lớn code instrumentation có thể giữ nguyên và thay đổi tập trung ở dependency/exporter. Nếu code gọi trực tiếp Prometheus Java Client, phải chuyển các lớp metric, registry, exporter và quy tắc đăng ký sang API mới.

Điểm quan trọng là không trộn lẫn các thế hệ trong cùng một đường export mà không có kế hoạch. Hai client có thể cùng tồn tại trong classpath do package khác nhau, nhưng chúng có registry, vòng đời, API và endpoint riêng. Một metric được đăng ký ở registry này không tự xuất hiện ở registry kia; nếu expose cả hai mà Prometheus scrape cùng dữ liệu, dashboard có thể đếm hai lần.

## 1. Xác định lớp API đang được ứng dụng sử dụng

Một ứng dụng Micrometer có thể dùng ba lớp:

| Lớp | Vai trò | API thường gặp |
|---|---|---|
| Instrumentation của ứng dụng | Mô tả Counter, Timer, Gauge, Observation | `MeterRegistry`, `Counter`, `Timer`, `ObservationRegistry` |
| Prometheus registry/client | Lưu và chuyển meter sang định dạng Prometheus | Micrometer Prometheus registry hoặc Prometheus Java Client trực tiếp |
| Exposition và scrape | Công bố endpoint để Prometheus đọc | Spring Boot Actuator, servlet exporter hoặc HTTP server exporter |

Nếu code nghiệp vụ chỉ inject `io.micrometer.core.instrument.MeterRegistry`, đó là dấu hiệu ứng dụng đang dùng abstraction Micrometer. Code không cần biết registry bên dưới là Prometheus, OTLP hay một backend khác.

Nếu code import `io.prometheus.client.Counter`, `CollectorRegistry` hoặc `io.prometheus.client.exporter.*`, ứng dụng đang dùng API simpleclient trực tiếp. Khi đó, việc nâng cấp client có ảnh hưởng trực tiếp đến source code.

Tìm các import và dependency trong module ứng dụng trước khi chọn lộ trình. Không chỉ nhìn thấy dependency Prometheus trong classpath rồi kết luận toàn bộ instrumentation đang dùng direct client.

## 2. Hai thế hệ Prometheus Java Client

| Nội dung | simpleclient 0.x | Prometheus Java Client 1.x |
|---|---|---|
| Package chính | `io.prometheus.client.*` | `io.prometheus.metrics.*` |
| Registry | `CollectorRegistry` | `PrometheusRegistry` |
| Metric API | Builder kiểu `Counter.build()` | Builder kiểu `Counter.builder()` |
| Label values | `labels(...)` | `labelValues(...)` |
| Phân phối thư viện | Các artifact simpleclient và module tích hợp | Các module metrics core/model/exporter/instrumentation |
| Exporter | Các module exporter của simpleclient | Các module exporter của client mới |
| Tích hợp Micrometer | Registry simpleclient tương ứng | Registry Micrometer cho Prometheus client mới |

Các package khác nhau giúp hai thế hệ có thể xuất hiện đồng thời trong classpath, nhưng không làm API tương thích nhị phân. Một object `CollectorRegistry` cũ không thể truyền trực tiếp cho API nhận `PrometheusRegistry` mới.

## 3. Chọn registry Micrometer phù hợp

Với ứng dụng Spring Boot dùng Actuator và Micrometer, cần chọn đúng registry artifact theo thế hệ Prometheus Java Client mong muốn.

Ví dụ dependency Maven cho registry dựa trên Prometheus Java Client mới:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Nếu cần duy trì registry dựa trên simpleclient cũ trong một ứng dụng Micrometer, có artifact tương ứng:

```xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus-simpleclient</artifactId>
    <scope>runtime</scope>
</dependency>
```

Hai artifact là lựa chọn theo thế hệ client, không nên thêm cả hai chỉ để “phòng khi cần”. Nếu cùng được cấu hình và expose, ứng dụng có thể tạo hai registry độc lập, hai endpoint hoặc hai luồng metrics. Hãy chọn một registry chính cho mỗi scrape target, trừ khi có kế hoạch migration có chủ đích.

Dùng Spring Boot dependency management/BOM để chọn phiên bản tương thích. Không tự nâng riêng Micrometer core, registry và Spring Boot starter lên các phiên bản không được quản lý cùng nhau.

## 4. Kiểm tra dependency tree trước khi nâng cấp

Một dependency bắc cầu có thể kéo simpleclient cũ vào classpath dù ứng dụng đã thêm registry mới. Trước khi sửa, xem dependency tree để biết:

- Có `micrometer-registry-prometheus` hay `micrometer-registry-prometheus-simpleclient`.
- Có `simpleclient`, `simpleclient_common` hoặc module exporter cũ không.
- Có `prometheus-metrics-core`, `prometheus-metrics-model` hoặc exporter module mới không.
- Có thư viện khác đang import `io.prometheus.client.*` không.
- Có version override làm lệch các module Prometheus client không.

Ví dụ lệnh Maven:

```bash
mvn dependency:tree -Dincludes=io.micrometer,io.prometheus
```

Ví dụ Gradle:

```bash
./gradlew dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
./gradlew dependencyInsight --dependency simpleclient --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Kết quả cần được đọc theo dependency path. Đừng loại bỏ một artifact chỉ vì tên có chữ `simpleclient` nếu một thư viện vẫn cần nó; trước tiên xác định thành phần nào sử dụng API cũ và có thể nâng cấp hay chưa.

## 5. API simpleclient 0.x: đăng ký Collector vào CollectorRegistry

Ví dụ direct client cũ:

```java
import io.prometheus.client.CollectorRegistry;
import io.prometheus.client.Counter;

public class LegacyRequestMetrics {

    private final Counter requests;

    public LegacyRequestMetrics(CollectorRegistry registry) {
        this.requests = Counter.build()
            .name("application_requests")
            .help("Number of application requests")
            .labelNames("method")
            .register(registry);
    }

    public void record(String method) {
        requests.labels(method).inc();
    }
}
```

Các đặc điểm đáng chú ý:

- Metric được tạo bằng builder static `build()`.
- `register(registry)` đăng ký collector vào registry.
- Label values được chọn bằng `labels(...)`.
- `inc()` cập nhật counter.
- Registry thường là `CollectorRegistry`, có thể là instance riêng hoặc default registry toàn cục.

Một lỗi phổ biến là tạo và đăng ký Counter mỗi lần xử lý request. Đăng ký meter nên diễn ra lúc khởi tạo component; request chỉ cập nhật child series tương ứng.

## 6. API Prometheus Java Client 1.x: metric và PrometheusRegistry

Ví dụ tương đương theo API client mới:

```java
import io.prometheus.metrics.core.metrics.Counter;
import io.prometheus.metrics.model.registry.PrometheusRegistry;

public class CurrentRequestMetrics {

    private final Counter requests;

    public CurrentRequestMetrics(PrometheusRegistry registry) {
        this.requests = Counter.builder()
            .name("application_requests")
            .help("Number of application requests")
            .labelNames("method")
            .register(registry);
    }

    public void record(String method) {
        requests.labelValues(method).inc();
    }
}
```

Các thay đổi thể hiện rõ:

- Package chuyển từ `io.prometheus.client` sang `io.prometheus.metrics.core.metrics`.
- Registry chuyển từ `CollectorRegistry` sang `PrometheusRegistry`.
- Builder chuyển sang `Counter.builder()`.
- Chọn label child bằng `labelValues(...)`.
- Metric được đăng ký vào registry mới.

Đây là ví dụ chuyển đổi direct API cho Counter. Khi chuyển Gauge, Histogram, Summary hoặc exporter, cần đọc API của module tương ứng; không giả định mọi method cũ có tên mới tương tự một-một.

## 7. Artifact modular của client mới

Client mới tách các trách nhiệm thành các module. Tên module thường gặp gồm:

| Module | Trách nhiệm |
|---|---|
| `prometheus-metrics-core` | Các loại metric và builder |
| `prometheus-metrics-model` | Registry, metric family và model dữ liệu |
| `prometheus-metrics-exposition-formats` | Định dạng text/OpenMetrics và writer |
| `prometheus-metrics-exporter-httpserver` | Exposition qua HTTP server tích hợp |
| `prometheus-metrics-exporter-servlet` | Tích hợp servlet |
| `prometheus-metrics-instrumentation-jvm` | Instrumentation JVM tương ứng |

Không phải ứng dụng nào cũng cần khai báo tất cả module trực tiếp. Nếu dùng Micrometer registry, dependency registry thường quản lý phần tích hợp cần thiết. Nếu dùng direct client, chỉ thêm module cho loại metric và exporter thực sự được dùng.

Tránh copy một danh sách dependency từ ứng dụng khác mà không xem kiến trúc server, servlet container và phiên bản client.

## 8. Micrometer facade giúp giảm phạm vi thay đổi

Nếu ứng dụng dùng Micrometer, code nghiệp vụ nên tiếp tục làm việc với API Micrometer:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public class OrderMetrics {

    private final Counter paidOrders;

    public OrderMetrics(MeterRegistry registry) {
        this.paidOrders = Counter.builder("business.orders.paid")
            .description("Orders that reached the paid state")
            .tag("domain", "order")
            .register(registry);
    }

    public void orderPaid() {
        paidOrders.increment();
    }
}
```

Khi chuyển registry từ simpleclient sang client mới, component này không cần import `PrometheusRegistry` hoặc Prometheus Counter. Micrometer registry chịu trách nhiệm chuyển meter sang backend.

Điều này tạo ranh giới tốt: domain/application code phụ thuộc Micrometer, còn adapter/exporter phụ thuộc Prometheus. Tránh để một phần code dùng Micrometer Counter và phần khác dùng direct Prometheus Counter cho cùng một business event.

## 9. Đăng ký metric một lần và tái sử dụng

Đăng ký metric là thao tác cấu hình, không phải thao tác nghiệp vụ. Hãy tạo meter trong constructor hoặc bean initialization, sau đó chỉ record/increment khi có sự kiện.

Không làm như sau:

```java
void requestHandled() {
    Counter.builder("application.requests")
        .help("Request count")
        .register(registry)
        .inc();
}
```

Đoạn code này lặp lại quá trình đăng ký và dễ gây lỗi collision hoặc chi phí không cần thiết. Hãy giữ tham chiếu metric:

```java
final class RequestMetrics {

    private final Counter requests;

    RequestMetrics(PrometheusRegistry registry) {
        this.requests = Counter.builder()
            .name("application_requests")
            .help("Request count")
            .register(registry);
    }

    void requestHandled() {
        requests.inc();
    }
}
```

Với Micrometer, cùng nguyên tắc áp dụng cho `MeterRegistry`: đăng ký meter một lần, giữ reference nếu phù hợp và không tạo tag value động trong hot path.

## 10. Registry là phạm vi đăng ký và nơi kiểm tra collision

Registry quản lý tập metric được đăng ký. Một metric family có tên đã được dùng không thể được đăng ký tùy tiện lần nữa với loại metric hoặc cấu trúc metadata không tương thích.

Các tình huống cần tránh:

- Hai component đăng ký cùng metric name nhưng khác loại metric.
- Cùng metric name nhưng khai báo label names khác nhau.
- Hai component cùng đăng ký một metric family mà không chia sẻ cùng meter.
- Tạo registry mới trong mỗi request rồi bỏ quên vòng đời.
- Dùng default registry toàn cục ở một phần code và registry Spring-managed ở phần khác.

Khi có collision, hành vi cụ thể và exception phụ thuộc thế hệ client và cách đăng ký. Không dựa vào việc “lần đăng ký thứ hai chắc chắn được gộp”. Hãy coi tên metric và cấu trúc label là hợp đồng phải được quản lý tập trung.

## 11. Label names phải ổn định cho một metric family

Với direct Prometheus client, label names được khai báo khi tạo metric. Các lần gọi `labels(...)` hoặc `labelValues(...)` phải truyền số lượng giá trị tương ứng với danh sách label names đã đăng ký.

Ví dụ:

```java
Counter requests = Counter.builder()
    .name("http_requests")
    .help("HTTP requests")
    .labelNames("method", "status")
    .register(registry);

requests.labelValues("GET", "200").inc();
requests.labelValues("POST", "500").inc();
```

Không thể lúc thì đăng ký label `method`, lúc khác thêm `tenant` vào cùng metric family mà không thay đổi định nghĩa. Nếu cần dimension mới, hãy thay đổi schema có chủ đích và kiểm tra dashboard/alert phụ thuộc vào metric đó.

Label values phải có cardinality giới hạn. Không dùng request ID, order ID, email, URL đầy đủ hoặc exception message làm label.

## 12. Tên metric và semantics có thể thay đổi khi export

Tên được khai báo ở API không phải lúc nào cũng xuất hiện nguyên văn trên endpoint. Naming convention, quy tắc suffix của Counter/Timer và registry mapping có thể ảnh hưởng tên cuối cùng.

Ví dụ, Micrometer dùng tên metric theo quy ước của nó rồi Prometheus naming convention chuyển sang dạng phù hợp. Timer có thể được export thành các series count, sum và histogram bucket. Direct Prometheus client có quy tắc đặt tên và exposition riêng.

Khi nâng cấp, so sánh output thực tế của endpoint trước và sau:

- Metric family name.
- Suffix như `_total`, `_count`, `_sum`.
- Label names và label values.
- Unit và help text.
- Histogram buckets và quantile.
- Exemplars hoặc các metadata được export.

Không sửa dashboard theo tên dự đoán. Lưu mẫu exposition trước nâng cấp, rồi so sánh với endpoint mới bằng một bộ request và dữ liệu giống nhau.

## 13. Histogram và Summary cần kiểm tra kỹ

Histogram và Summary không phải lúc nào cũng có semantics tương đương giữa hai thế hệ client và giữa direct client với Micrometer.

Histogram thường export bucket counts, sum và count; backend có thể tổng hợp bucket giữa nhiều instance để tính quantile. Summary có thể export quantile được tính tại process và thường không thể cộng gộp các quantile cục bộ thành quantile toàn service.

Khi chuyển client hoặc registry, xác minh:

- Bucket boundaries có giữ nguyên không.
- Bucket `+Inf` có xuất hiện đúng không.
- SLO buckets có được giữ không.
- Count và sum có đúng unit không.
- Percentiles phía client có còn được cấu hình như trước không.
- Dashboard dùng `histogram_quantile()` có còn đúng metric name/label không.

Không so sánh p95 của Summary với p95 từ histogram như thể chúng luôn tương đương. Chúng có thể dùng thuật toán, cửa sổ và cách tổng hợp khác nhau.

## 14. Không đăng ký cùng metric vào hai registry rồi expose chung

Trong giai đoạn chuyển đổi, có thể cần chạy song song hai client để so sánh output. Nhưng mỗi registry cần có ranh giới rõ.

Một mô hình tạm thời có thể là:

```text
Application instrumentation
    |                         |
Legacy registry          New registry
    |                         |
/metrics-legacy          /metrics-v2
    |                         |
Prometheus job legacy    Prometheus job candidate
```

Hai endpoint cần label/job khác nhau và không được cộng chung trong dashboard tổng. Nếu cả hai cùng export một metric name và label set vào cùng backend, query có thể cộng hai bản sao.

Không gắn cùng một meter handler hoặc custom instrumentation vào hai registry nếu thao tác record sẽ bị nhân đôi ngoài ý muốn. Nếu cần dual-write để kiểm chứng, hãy ghi rõ đây là shadow path, theo dõi riêng và có ngày kết thúc.

## 15. Tránh default registry toàn cục trong ứng dụng Spring

Các client cũ thường có ví dụ dùng default registry static. Điều đó tiện cho chương trình nhỏ nhưng có thể gây khó kiểm soát trong ứng dụng Spring Boot, nơi registry nên được quản lý theo dependency injection.

Một số rủi ro của global registry:

- Test dùng chung trạng thái giữa các test.
- Component đăng ký metric ở registry khác với registry đang được Actuator expose.
- Static initializer chạy trước khi cấu hình hoàn tất.
- Nhiều application context trong cùng JVM chia sẻ trạng thái ngoài dự kiến.
- Registry không được đóng hoặc dọn theo vòng đời ứng dụng.

Với Spring Boot, inject `MeterRegistry` hoặc bean registry phù hợp. Nếu dùng direct Prometheus client, tạo một `PrometheusRegistry` được quản lý như bean và inject vào component; tránh dùng default registry toàn cục trừ khi có lý do rõ ràng.

## 16. Spring Boot Actuator endpoint và registry được chọn

Khi dùng Micrometer Prometheus registry, Spring Boot Actuator thường cung cấp endpoint `/actuator/prometheus`. Endpoint này xuất dữ liệu từ registry Micrometer được cấu hình.

Ví dụ exposure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Đổi registry dependency có thể giữ nguyên endpoint path, nhưng không đảm bảo output hoàn toàn giống trước. Cần xác minh:

- Endpoint có được tạo và expose không.
- Security policy vẫn bảo vệ endpoint.
- Prometheus scrape target vẫn dùng đúng port/path.
- Metric families và label schema không bị thay đổi ngoài dự kiến.
- Không có endpoint cũ vẫn được scrape song song.

Nếu direct client tạo HTTP exporter riêng, endpoint của exporter đó không tự hợp nhất với Actuator endpoint. Muốn một endpoint chung cần một integration layer rõ ràng; không mở hai server trên cùng port hoặc kỳ vọng registry Micrometer tự nhìn thấy collectors của direct client.

## 17. Collision khi trộn Micrometer và direct Prometheus client

Một ứng dụng có thể vô tình định nghĩa cùng metric ở hai API:

```java
// Micrometer
meterRegistry.counter("application.requests").increment();

// Direct Prometheus client
prometheusCounter.labelValues("GET").inc();
```

Hai phép ghi thuộc hai registry khác nhau. Nếu hai registry export cùng metric family name và label schema đến hai endpoint, backend có thể lưu hai nguồn. Nếu scrape cả hai rồi aggregate, kết quả bị nhân đôi.

Nếu buộc phải giữ direct client trong khi chuyển sang Micrometer:

1. Đặt metric name riêng trong giai đoạn chuyển tiếp hoặc giữ một nguồn scrape.
2. Tách endpoint/job và label nguồn.
3. Không cộng series của hai nguồn trong dashboard.
4. Xác định component nào sở hữu metric sau migration.
5. Xóa direct client instrumentation cũ khi đã xác nhận parity.
6. Kiểm tra dependency tree để loại module không còn dùng.

Mục tiêu cuối cùng là một nguồn có thẩm quyền cho mỗi metric semantics, không phải chỉ một thư viện trong classpath.

## 18. Kiểm thử registry trước và sau nâng cấp

Một bộ test nên kiểm tra cả API-level lẫn exposition-level.

**API-level test:**

- Metric được đăng ký đúng một lần.
- Counter tăng đúng số lần gọi.
- Label names/values đúng.
- Timer count, total time và histogram sample đúng.
- Registry mới được tạo riêng cho mỗi test.

Ví dụ với Micrometer:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderMetricsTest {

    @Test
    void incrementsPaidOrderCounter() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        OrderMetrics metrics = new OrderMetrics(registry);

        metrics.orderPaid();

        assertThat(
            registry.get("business.orders.paid").counter().count()
        ).isEqualTo(1.0);

        registry.close();
    }
}
```

Test trên xác nhận semantics Micrometer, nhưng chưa xác minh Prometheus exporter. Cần thêm integration test dùng Prometheus registry thực tế.

**Exposition-level test:**

- Gọi endpoint scrape.
- Kiểm tra metric family name và type.
- Kiểm tra label names và values.
- Kiểm tra histogram buckets, count và sum.
- Xác nhận metric cũ không xuất hiện từ endpoint mới nếu đã loại bỏ.
- Xác nhận một thao tác không tạo hai sample trong cùng metric identity.

Lưu một snapshot exposition đã chuẩn hóa trước nâng cấp để so sánh. Không so sánh timestamp hoặc giá trị counter tuyệt đối nếu hai lần chạy không dùng cùng workload; so sánh schema và kết quả trong test fixture có thể tái lập.

## 19. Kiểm tra tương thích và rollout

Một lộ trình nâng cấp có thể chia thành các bước:

1. **Inventory:** tìm direct imports, registry artifact, exporter, endpoint và dashboard.
2. **Version alignment:** chọn Spring Boot/Micrometer BOM tương thích và xác định client generation.
3. **Dependency change:** thay registry artifact hoặc module direct client.
4. **Source migration:** chỉ sửa source code nơi đang dùng API cũ trực tiếp.
5. **Registration review:** kiểm tra metric names, labels, registry lifecycle và collisions.
6. **Test:** chạy unit, integration và exposition tests.
7. **Shadow comparison:** nếu cần, expose output mới qua endpoint/job riêng.
8. **Dashboard validation:** xác nhận rate, count, histogram và label schema.
9. **Cutover:** chuyển Prometheus scrape sang endpoint mới.
10. **Cleanup:** loại dependency, exporter và endpoint cũ sau khi xác nhận không còn consumer.

Không xóa endpoint cũ trước khi kiểm tra Prometheus scrape config, recording rules, alert rules và dashboard. Ngược lại, không để cả endpoint cũ và mới cùng được aggregate vô thời hạn.

## 20. Những lỗi thường gặp khi chuyển thế hệ

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không biên dịch sau nâng cấp | Import `io.prometheus.client.*` còn sót | Chuyển sang API mới hoặc giữ simpleclient registry có chủ đích |
| Không tìm thấy registry class | Dùng `CollectorRegistry` với client mới | Dùng `PrometheusRegistry` ở direct API mới |
| Duplicate registration | Hai component đăng ký cùng metric family | Chọn một owner và chia sẻ meter |
| Metric biến mất khỏi Actuator | Direct client registry không thuộc Micrometer registry | Chọn một integration path hoặc endpoint riêng |
| Counter tăng gấp đôi | Hai instrumentation paths cùng được scrape/aggregate | Kiểm tra registry, endpoint, job và query |
| Dashboard không còn dữ liệu | Metric name, suffix hoặc labels đổi | So sánh exposition trước/sau và cập nhật query |
| Histogram p95 thay đổi | Bucket hoặc semantics phân phối đổi | So sánh boundaries, count, sum và query |
| Test bị ảnh hưởng lẫn nhau | Dùng global/default registry | Tạo registry riêng cho mỗi test |
| Classpath có cả hai client | Dependency bắc cầu hoặc migration song song | Dùng dependencyInsight và xác định owner |
| Exporter không mở endpoint | Chưa thêm module/server integration tương ứng | Kiểm tra exporter dependency và lifecycle |

## 21. Checklist trước khi hoàn tất migration

- [ ] Đã xác định code dùng Micrometer facade hay direct Prometheus Java Client.
- [ ] Đã phân biệt simpleclient 0.x và Prometheus Java Client 1.x.
- [ ] Registry artifact khớp với thế hệ client đã chọn.
- [ ] Các module Micrometer/Prometheus được quản lý phiên bản đồng bộ.
- [ ] Đã kiểm tra dependency tree và thư viện còn dùng package cũ.
- [ ] Đã chuyển import, registry và builder API ở direct client code.
- [ ] Metric name, type, help, unit và label schema được rà soát.
- [ ] Mỗi metric family có một owner đăng ký.
- [ ] Không đăng ký metric trong request hot path.
- [ ] Không trộn default/global registry với registry Spring-managed ngoài ý muốn.
- [ ] Histogram, Summary, buckets và percentile được so sánh.
- [ ] Actuator endpoint hoặc direct exporter được xác minh.
- [ ] Không scrape cùng dữ liệu từ hai endpoint rồi cộng chung.
- [ ] Test API-level và exposition-level đều đạt.
- [ ] Dashboard, alert và recording rules đã được kiểm tra.
- [ ] Dependency và endpoint cũ được dọn sau cutover.

Nâng cấp Prometheus Java Client không chỉ là đổi package. Cần xác định ứng dụng đang dùng Micrometer hay direct client, chọn registry đúng thế hệ, chuyển cách đăng ký và bảo toàn hợp đồng metric với Prometheus. Giữ một nơi sở hữu mỗi metric family, đăng ký một lần trong lifecycle ứng dụng, kiểm tra label/bucket và so sánh exposition trước khi chuyển scrape target. Khi migration hoàn tất, code nghiệp vụ nên tiếp tục phụ thuộc Micrometer nếu không có lý do đặc biệt để gắn chặt với Prometheus API.

## Tài liệu tham khảo

- [Prometheus Java Client](https://prometheus.github.io/client_java/) — tài liệu client mới, registry, metric types và exporter.
- [Prometheus Java Client migration guide](https://prometheus.github.io/client_java/migration/) — khác biệt giữa simpleclient và client thế hệ mới.
- [Micrometer Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html) — cấu hình Prometheus registry trong Micrometer.
- [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — tích hợp Micrometer và endpoint metrics.
- [Prometheus Data Model](https://prometheus.io/docs/concepts/data_model/) — metric names, labels và time series.

