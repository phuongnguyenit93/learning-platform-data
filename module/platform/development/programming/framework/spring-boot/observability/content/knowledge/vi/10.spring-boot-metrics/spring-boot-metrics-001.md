# Auto-configured MeterRegistry

Trong chương **Spring Boot metrics** của mô-đun **SPRING_BOOT_OBSERVABILITY**, `MeterRegistry` là thành phần trung tâm để ứng dụng ghi **metrics**: số request, thời lượng xử lý, lỗi, mức sử dụng JVM, độ bão hòa tài nguyên và các chỉ số nghiệp vụ. Với cơ chế auto-configuration, Spring Boot có thể tạo và cấu hình registry phù hợp với dependency có trên classpath. Bạn chỉ cần inject `MeterRegistry` vào service khi cần đo những hoạt động riêng của ứng dụng.

Mục tiêu của mô-đun là xây dựng observability trong Spring Boot bằng **Micrometer Observation, metrics, logs và distributed tracing**; bao gồm propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra hành vi thực tế. `MeterRegistry` thuộc nhánh metrics. Tracing và logs có đường xử lý riêng; hiểu đúng trách nhiệm của từng thành phần giúp tránh kỳ vọng rằng thêm Prometheus registry sẽ tự động tạo distributed traces.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Giải thích khi nào Spring Boot tự cung cấp bean `MeterRegistry`, và vai trò của registry implementation trên classpath.
2. Phân biệt **SimpleMeterRegistry**, **CompositeMeterRegistry** và registry dành cho Prometheus hoặc một backend khác.
3. Cấu hình Actuator và Prometheus; xác minh dữ liệu ở `/actuator/metrics` và `/actuator/prometheus`.
4. Inject `MeterRegistry` để ghi `Counter`, `Timer` và một vài metrics nghiệp vụ.
5. Áp dụng common tags và cấu hình phân bố độ trễ mà không tạo cardinality quá cao.
6. Phân biệt dữ liệu do meter ghi trực tiếp với metrics được tạo từ Micrometer Observation.
7. Chẩn đoán lỗi thiếu metric, tên metric khác mong đợi, scrape lỗi và mối liên hệ với tracing/logs.

## 2. `MeterRegistry` quản lý những gì?

Micrometer Metrics cung cấp các loại meter để mô tả dữ liệu số. `MeterRegistry` đăng ký, tìm và cung cấp các meter theo **tên cộng với tập tags**. Khi code lấy lại meter có cùng định danh trong cùng registry, nó thường nhận lại meter đã đăng ký.

| Loại meter | Thông tin đo được | Ví dụ thực tế |
| --- | --- | --- |
| `Counter` | Số sự kiện tăng dần. | Số lần thanh toán thành công hay bị từ chối. |
| `Timer` | Số lần gọi và tổng thời lượng, có thể có phân bố. | Thời gian tính giá, thời gian xử lý HTTP. |
| `Gauge` | Giá trị hiện tại ở thời điểm quan sát. | Số phần tử trong hàng đợi. |
| `DistributionSummary` | Phân bố các số đo không phải thời gian. | Kích thước thông điệp tính bằng byte. |
| `LongTaskTimer` | Số công việc dài đang chạy và thời gian của chúng. | Batch job lâu hoặc quy trình cần theo dõi trong khi chạy. |

Ví dụ, một `Timer` thường có count và tổng thời lượng. Với Prometheus registry, dữ liệu timer có thể được xuất thành các chuỗi dạng `_seconds_count` và `_seconds_sum`; histogram buckets cần cấu hình thích hợp.

**MeterRegistry không phải kho dữ liệu giám sát.** Nó là lớp ghi nhận và xuất số đo. Một Prometheus registry thường cho server Prometheus **scrape** dữ liệu; một số registry khác có thể push dữ liệu tới dịch vụ bên ngoài.

~~~mermaid
flowchart LR
    A["Spring Boot request / business code"] --> B["Meter hoặc Micrometer Observation"]
    B --> C["MeterRegistry được auto-configure"]
    C --> D["Simple/Composite/Prometheus registry"]
    D --> E["Actuator hoặc exporter"]
    E --> F["Metrics backend và dashboard"]
    B --> G["Tracing handler nếu được cấu hình"]
    G --> H["Trace exporter và backend"]
    A --> I["Logs / MDC nếu ứng dụng cấu hình"]
~~~

Sơ đồ chỉ mô tả luồng khái niệm. Một observation cần **metrics observation handler** để tạo số đo trong MeterRegistry; nó cũng cần **tracing handler** và exporter riêng nếu muốn có span. Logs thường được tạo bởi logging framework, có thể liên kết với trace thông qua MDC khi tích hợp tracing phù hợp.

## 3. Spring Boot auto-configure registry theo classpath

Cơ chế tự cấu hình dựa vào bean, thư viện và property hiện diện tại thời điểm khởi động:

1. Thêm `spring-boot-starter-actuator` đưa hạ tầng Actuator và Micrometer vào một ứng dụng Spring Boot thông dụng.
2. Spring Boot phát hiện registry implementation được hỗ trợ trên classpath và cấu hình bean registry tương ứng nếu các điều kiện auto-configuration được đáp ứng.
3. Spring Boot thường cấu hình một **composite meter registry** để số đo có thể được chuyển tới các registry bên dưới.
4. Nếu chưa có backend registry cụ thể, **SimpleMeterRegistry** trong bộ nhớ có thể là fallback khi cấu hình cho phép.
5. Spring Boot có thể đăng ký các meter binders/instrumentation được hỗ trợ cho JVM, process, HTTP, connection pool hoặc tích hợp khác.
6. Bạn inject bean `MeterRegistry` để ghi metrics; exporter và hệ thống thu thập bên ngoài chịu trách nhiệm đưa dữ liệu vào dashboard.

Không cần tự tạo bean `SimpleMeterRegistry` hoặc `PrometheusMeterRegistry` trong mỗi service nếu ứng dụng đã sử dụng auto-configuration thích hợp.

### Ba kiểu registry dễ gặp

| Kiểu | Công dụng | Hạn chế |
| --- | --- | --- |
| **Simple** | Lưu số đo trong bộ nhớ, phù hợp quan sát cục bộ hoặc thử nghiệm. | Không tự gửi số đo tới một backend tập trung. |
| **Composite** | Kết hợp nhiều registry, giúp mã ứng dụng ghi thông qua một điểm chung. | Mỗi registry con có thể có cách đặt tên/biểu diễn riêng. |
| **Prometheus** | Cung cấp định dạng dữ liệu để Prometheus thu thập. | Cần endpoint có thể scrape và Prometheus server/config tương ứng. |

Auto-configured **không có nghĩa** là Spring Boot tự cài đặt Prometheus server, trace collector hoặc log backend. Một ứng dụng có thể ghi metrics chính xác nhưng chưa có nơi bên ngoài lưu chúng.

Khi ứng dụng đã có custom `MeterRegistry` bean hoặc có nhiều registry implementations, kết quả có thể khác mẫu đơn giản trên; kiểm tra bean definitions và endpoint thực tế trước khi đưa ra kết luận.

## 4. Bật Actuator và Prometheus registry

Ví dụ Gradle cho ứng dụng **Spring Boot 3.x** dùng Spring MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Spring Boot thường quản lý phiên bản Micrometer tương thích qua dependency management/BOM. Không nên gắn ngẫu nhiên một phiên bản Micrometer khác với bộ dependency mà Spring Boot đang quản lý.

Ví dụ `application.yml` cho môi trường thử nghiệm:

~~~yaml
spring:
  application:
    name: order-api

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-api
      environment: local
~~~

Các điểm cần hiểu:

- Actuator cung cấp endpoint xem metrics và hạ tầng instrumentation.
- `micrometer-registry-prometheus` cho phép Spring Boot auto-configure Prometheus registry khi điều kiện phù hợp.
- `management.endpoints.web.exposure.include` chỉ định endpoint nào được expose qua web.
- `management.metrics.tags` thêm common tags có giá trị ổn định vào các meter.

**Bảo mật:** không expose các endpoint quản trị/metrics rộng rãi ra Internet. Sử dụng cổng quản trị, network policy và security rules tương ứng. Chỉ mở những endpoint thực sự cần thiết.

### Kiểm tra trực tiếp

Khởi động ứng dụng, gọi thử vài request đến controller, rồi kiểm tra:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/http.server.requests
curl -s http://localhost:8080/actuator/prometheus
~~~

Kết quả kỳ vọng:

- `/actuator/metrics` liệt kê các **meter names** đã có dữ liệu.
- `/actuator/metrics/http.server.requests` trả dữ liệu HTTP server nếu instrumentation tương ứng đã ghi nhận request.
- `/actuator/prometheus` cung cấp dữ liệu theo định dạng của Prometheus registry.
- Tên meter trong Actuator như `http.server.requests` có thể được chuyển thành các tên Prometheus như `http_server_requests_seconds_count`.

Nếu chưa có traffic hoặc chưa chạy nhánh code ghi metric, một meter cụ thể có thể chưa xuất hiện. Endpoint metrics có dữ liệu cũng chưa chứng minh server Prometheus đang scrape thành công.

## 5. Inject `MeterRegistry` thay vì tự khởi tạo registry

Spring service có thể nhận registry do Spring Boot cung cấp qua constructor:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutMetrics {
    private final MeterRegistry registry;

    public CheckoutMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void success() {
        registry.counter("checkout.completed", "outcome", "success")
                .increment();
    }

    public void failure() {
        registry.counter("checkout.completed", "outcome", "error")
                .increment();
    }
}
~~~

Trong ví dụ, các giá trị `success` và `error` có số lượng hữu hạn nên phù hợp làm **low-cardinality tags**. `MeterRegistry` tái sử dụng counter theo tên và tags; mỗi lời gọi `increment()` tăng số sự kiện trong meter đó.

Vì `CheckoutMetrics` là bean Spring thông thường, **không có số liệu mới chỉ vì bean tồn tại**. Controller/service phải gọi `success()` hoặc `failure()` trong luồng nghiệp vụ. Nếu cả controller lẫn service cùng tăng counter cho một sự kiện, metrics sẽ bị đếm hai lần.

Kiểm tra sau khi chạy nghiệp vụ:

~~~bash
curl -s http://localhost:8080/actuator/metrics/checkout.completed
~~~

Nên có một nơi chịu trách nhiệm phát mỗi metric nghiệp vụ, cùng định nghĩa rõ ràng của “success”, “failure”, “retry” và “business rejection”.

## 6. Đo độ trễ bằng `Timer`

Giả sử `PricingService` tính giá của đơn hàng, cần ghi lại duration của mỗi lần tính:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class PricingService {
    private final MeterRegistry registry;
    private final PricingEngine engine;

    public PricingService(MeterRegistry registry, PricingEngine engine) {
        this.registry = registry;
        this.engine = engine;
    }

    public Price calculate(PriceRequest request) {
        Timer timer = Timer.builder("pricing.calculate")
                .description("Time spent calculating prices")
                .tag("operation", "calculate")
                .register(registry);

        return timer.record(() -> engine.calculate(request));
    }

    public interface PricingEngine {
        Price calculate(PriceRequest request);
    }

    public record PriceRequest(String currency, int itemCount) {}
    public record Price(long minorUnits, String currency) {}
}
~~~

`Timer.record(...)` đo khoảng thời gian lambda thực thi. Nếu có exception, timer vẫn ghi duration nhưng **không tự tạo riêng nhãn kết quả “error”**. Khi cần phân biệt outcome, hãy thiết kế thêm trạng thái lỗi theo ngữ nghĩa nghiệp vụ hoặc dùng `Timer.Sample`.

### Outcome chỉ biết sau khi xử lý

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    return engine.calculate(request);
} catch (RuntimeException exception) {
    outcome = "error";
    throw exception;
} finally {
    Timer timer = Timer.builder("pricing.calculate")
            .tag("outcome", outcome)
            .register(registry);
    sample.stop(timer);
}
~~~

Đoạn trên minh họa logic của phương thức có kiểu trả về phù hợp. `Timer.Sample` bắt đầu đo, sau đó chọn timer theo outcome để dừng. Nếu “không đủ tiền” là kết quả nghiệp vụ hợp lệ, không nhất thiết ghi cùng `error` với một lỗi hệ thống.

Một lưu ý: timer được tạo và đăng ký theo **tên cùng tags**. Không dùng order ID, request ID, email hay URL thô làm tag vì mỗi request có thể tạo một định danh meter mới.

## 7. Các metrics tự động thường thấy

Tùy dependency, bean, binder và loại ứng dụng, Spring Boot có thể tự ghi những nhóm metrics sau:

| Nhóm | Ví dụ | Câu hỏi điều tra |
| --- | --- | --- |
| **JVM** | Heap, GC pause, số thread. | Độ trễ có trùng với GC hoặc thiếu bộ nhớ? |
| **Process/system** | CPU, uptime, file descriptor tùy nền tảng. | Dịch vụ có bão hòa tài nguyên không? |
| **HTTP server** | Count, duration, status, method và route mẫu. | Route nào có tỉ lệ lỗi hoặc P95 tăng? |
| **HTTP client** | Duration của lời gọi tới dịch vụ khác khi client được instrument. | Dependency nào đang chậm? |
| **Connection pool** | Kết nối active, idle, waiting theo thư viện hỗ trợ. | Có phải request chờ lấy connection? |
| **Cache/message/database** | Metrics theo tích hợp tương ứng. | Có nút thắt ở cache, queue hoặc data source? |
| **Nghiệp vụ** | `checkout.completed`, `pricing.calculate`. | Tỉ lệ thành công và thời gian xử lý nghiệp vụ ra sao? |

Danh sách này là **khả năng theo điều kiện**, không phải cam kết mọi ứng dụng đều có sẵn từng meter. Ví dụ, HTTP client được tạo thủ công ngoài builder/instrumentation mà Spring Boot cung cấp có thể không xuất các metrics mong đợi.

Luôn xem danh sách meter và những labels thực tế ở endpoint hoặc backend thay vì suy đoán từ tên thư viện.

## 8. Mối liên hệ với Micrometer Observation

Trong Spring Boot, nhiều hoạt động được instrument qua **Micrometer Observation**. Phân biệt hai registry:

| Thành phần | Trách nhiệm |
| --- | --- |
| `ObservationRegistry` | Quản lý observation, handlers, conventions, filters, scope. |
| `Observation` | Mô tả hoạt động có vòng đời bắt đầu–kết thúc, key-values và lỗi. |
| Metrics observation handler | Ghi số đo từ observation tới `MeterRegistry`. |
| `MeterRegistry` | Quản lý counters/timers/gauges và các registry xuất metrics. |
| Tracing observation handler | Chuyển observation thành span khi bridge tracing được cấu hình. |

Ví dụ custom observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final ObservationRegistry observationRegistry;
    private final InventoryGateway gateway;

    public InventoryService(ObservationRegistry observationRegistry,
                            InventoryGateway gateway) {
        this.observationRegistry = observationRegistry;
        this.gateway = gateway;
    }

    public Stock reserve(String sku, int quantity) {
        return Observation.createNotStarted("inventory.reserve", observationRegistry)
                .lowCardinalityKeyValue("operation", "reserve")
                .lowCardinalityKeyValue("dependency", "inventory")
                .observe(() -> gateway.reserve(sku, quantity));
    }

    public interface InventoryGateway {
        Stock reserve(String sku, int quantity);
    }

    public record Stock(int quantity) {}
}
~~~

Mẫu `observe(...)` quản lý vòng đời khi lambda chạy đồng bộ. Khi metrics handler đã được cấu hình, có thể tạo meter thời gian cho `inventory.reserve`; nếu thêm tracing bridge/exporter phù hợp, có thể tạo tracing span. **Một MeterRegistry hoạt động không tự bảo đảm có span hoặc trace.**

Không nên dùng thêm `Timer` thủ công bao cùng đoạn xử lý chỉ để “chắc chắn có metrics” nếu observation đã ghi cùng một loại phép đo với cùng ý nghĩa. Việc instrument trùng sẽ gây khó hiểu hoặc đếm trùng khi đọc dashboard.

## 9. Common tags và cardinality

Trong nhiều metrics backend, mỗi tổ hợp **tên metric + toàn bộ tập tags** tạo một time series riêng. Một tag biến đổi theo request có thể tạo lượng series tăng theo số request.

Ví dụ cần tránh:

~~~java
// Mỗi request ID gần như duy nhất: cardinality không kiểm soát.
registry.counter("checkout.attempts",
        "requestId", requestId).increment();
~~~

Cách phù hợp hơn:

~~~java
registry.counter("checkout.attempts",
        "operation", "checkout",
        "outcome", "success").increment();
~~~

Những tag như `operation`, `method`, `status`, `uri` dạng route template và `outcome` thường hữu ích nếu tập giá trị nhỏ, có kiểm soát. `userId`, `orderId`, UUID, email và URL raw chứa ID thường không phù hợp cho low-cardinality metrics.

### Đặt common tags bằng properties

~~~yaml
management:
  metrics:
    tags:
      application: order-api
      environment: prod
      region: ap-southeast-1
~~~

Common tags hữu ích để lọc các service hoặc môi trường trong dashboard. Tuy nhiên, thêm nhiều chiều làm số tổ hợp series nhân lên. Không đặt request ID hoặc thời điểm hiện tại làm common tag.

### Tùy chỉnh bằng `MeterRegistryCustomizer`

Khi cần xử lý theo Java thay vì YAML, Spring Boot hỗ trợ customizer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTagsCustomizer() {
        return registry -> registry.config()
                .commonTags("team", "checkout");
    }
}
~~~

Customizer điều chỉnh registry trong giai đoạn cấu hình của Spring Boot. Tránh khai báo trùng tags ở nhiều nguồn mà không kiểm tra dữ liệu xuất.

## 10. Histogram và P95/P99

`Timer` ghi các số đo duration; việc tính phân vị tổng hợp qua nhiều instance đòi hỏi cách đo thích hợp. Với Prometheus registry, histogram buckets cho phép tính gần đúng P95/P99 từ dữ liệu tập hợp.

Ví dụ bật histogram cho HTTP server timer trong Spring Boot 3.x:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

Không nên bật histogram cho mọi timer một cách tùy tiện: mỗi bộ bucket và tập nhãn có thể tạo thêm nhiều time series, tăng chi phí thu thập và lưu trữ.

Ví dụ PromQL dưới đây giả định registry xuất tên metric và labels tương ứng; cần xác minh ở `/actuator/prometheus` của ứng dụng thực tế.

**Lưu lượng request/giây theo route:**

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/orders/{id}",method="GET"
}[5m]))
~~~

**Tỉ lệ lỗi HTTP 5xx:**

~~~promql
100 *
sum(rate(http_server_requests_seconds_count{
  uri="/orders/{id}",method="GET",status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  uri="/orders/{id}",method="GET"
}[5m]))
~~~

**P95 latency từ histogram buckets:**

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/orders/{id}",method="GET"
    }[5m])
  )
)
~~~

Lưu ý:

- Các timer metrics xuất sang Prometheus trong ví dụ dùng đơn vị **giây**: `0.25` tương ứng 250 ms.
- Chỉ có P95 histogram khi bucket series tồn tại và bộ lọc query đúng.
- Khi nhiều service/environment cùng ghi vào Prometheus, hãy thêm nhãn lọc service/namespace/job phù hợp.
- **Không lấy trung bình cộng P95 từng instance** để được P95 toàn dịch vụ. Gộp các buckets có ranh giới tương thích rồi dùng `histogram_quantile`.
- Ở tải rất thấp, tỉ lệ lỗi hoặc P95 dễ biến động; chọn thời gian cửa sổ và ngưỡng traffic phù hợp.
- Trường hợp mẫu số bằng không, tỉ lệ lỗi có thể không xác định; dashboard và alert cần xử lý tình huống đó.

## 11. `MeterFilter` và quy tắc kiểm soát

`MeterFilter` hoạt động ở tầng metrics registry, cho phép chặn một loại meter hoặc điều chỉnh metadata của meter. Ví dụ chặn một nhóm metric debug không cần thiết:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricsPolicyConfiguration {

    @Bean
    MeterFilter denyDebugMeters() {
        return MeterFilter.deny(id ->
                id.getName().startsWith("internal.debug."));
    }
}
~~~

Đây là ví dụ về cách áp dụng quy tắc có phạm vi rõ. Tránh chặn nhầm những metrics liên quan đến lỗi, độ trễ hoặc SLO. Nếu cardinality cao do cách đặt tag sai, cách sửa bền vững là **thiết kế lại tags**, thay vì từ chối toàn bộ metric nghiệp vụ.

`MeterFilter` không thay thế `ObservationPredicate` hay tracing sampling:

- `MeterFilter` can thiệp vào **đăng ký meter** ở metrics registry.
- `ObservationPredicate` có thể loại observation ở tầng Micrometer Observation.
- Tracing sampling quyết định phần nào của **distributed traces** được ghi/giữ lại theo stack và pipeline.

Việc loại meter không tự ngăn logger phát dòng log hoặc không tự tắt tracing span của observation liên quan.

## 12. MeterRegistry, logs và distributed tracing

Metrics là tín hiệu **tổng hợp**: “bao nhiêu request lỗi?”, “P95 tăng lúc nào?”, “route nào bị ảnh hưởng?”. Nó không trực tiếp giải thích toàn bộ đường đi của từng request.

Khi ứng dụng có Micrometer Tracing phù hợp:

- Tracing có thể dùng W3C `traceparent` để truyền trace context qua HTTP hoặc các carrier khác.
- Logs có thể chứa `traceId` và `spanId` trong MDC, giúp tìm sự kiện cụ thể.
- Một trace được giữ có thể cho thấy parent/child spans, retries, network và dependency latency.
- Exporter, collector, backend và **sampling** quyết định traces nào được lưu và tra cứu được.

Ví dụ: HTTP server metrics đếm 10.000 request, trong đó 200 request lỗi. Trace backend có thể chỉ lưu một phần request do sampling. Điều này **không có nghĩa metrics bị mất 90% dữ liệu**; metrics và traces có pipeline riêng.

Ngược lại, có tracing exporter không tự động bật Prometheus metrics; hai exporter không thay thế nhau. Nếu trace bị tách tại một service, cần kiểm tra context propagation, client instrumentation và ranh giới async, không thể sửa bằng cách gắn thêm metric tags.

## 13. Runbook: metrics giúp khoanh vùng sự cố như thế nào?

Giả sử sau một deploy, P95 của `POST /checkout` tăng từ 200 ms lên 1,4 giây, còn request/giây gần như không đổi.

1. **Xác nhận thông số đầu vào:** service, environment, mốc triển khai, time window và tags thực tế từ registry.
2. **Kiểm tra HTTP metrics:** traffic, error rate và P95 của `POST /checkout` so với route khác.
3. **Kiểm tra JVM và saturation:** CPU, heap/GC, thread pool, connection pool; tránh kết luận “CPU ổn nên database chậm” khi chưa có bằng chứng.
4. **So sánh custom metrics:** `pricing.calculate` có tăng không? Số checkout thành công/thất bại thay đổi thế nào?
5. **Mở logs trong cùng khoảng thời gian:** timeout, retry, exception, correlation IDs và tên dependency.
6. **Mở một số traces phù hợp:** xem critical path và span nào tiêu tốn nhiều thời gian, đối chiếu client/server latency.
7. **Xác nhận bằng dữ liệu dependency:** slow query, queue, pool wait, lock, network hoặc dữ liệu từ service downstream.
8. **Khắc phục và đo lại:** theo dõi P95, error rate và traffic đủ lâu; trace nhanh đơn lẻ không đủ chứng minh vấn đề đã hết.

Nếu metrics bị thiếu tại bước 2–4, ưu tiên kiểm tra **đường dữ liệu** (registry, binder, exporter, scrape target) trước khi suy diễn từ dashboard trống.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không inject được `MeterRegistry` | Thiếu dependency hoặc auto-configuration chưa tạo bean. | Xem Actuator/Micrometer trên classpath và bean configuration. |
| `/actuator/metrics` trả 404 | Endpoint chưa expose, bị disable hoặc đổi management port/base path. | Kiểm tra properties và security. |
| Có `/actuator/metrics` nhưng thiếu `/actuator/prometheus` | Thiếu Prometheus registry hoặc endpoint chưa bật/expose. | Kiểm tra dependency và exposure. |
| App có metric nhưng Prometheus không thu được | Scrape target hoặc network/auth/port sai. | Kiểm tra target status và raw scrape response. |
| Không thấy custom metric | Chưa gọi code ghi metric; tên/tags hoặc registry không như mong đợi. | Gọi thử nhánh nghiệp vụ và đọc danh sách meter. |
| P95 query trả trống | Thiếu histogram buckets hoặc PromQL lọc nhãn sai. | Kiểm tra `_bucket` và `le` trên Prometheus. |
| Latency trông lớn/nhỏ bất thường | Nhầm giây với millisecond. | Xác minh base unit và phép chuyển đổi. |
| Nhiều series tăng theo số request | Tag chứa request ID, user ID hoặc URL raw. | Loại high-cardinality tags khỏi metrics. |
| Counter nghiệp vụ tăng gấp đôi | Hai tầng cùng ghi hoặc instrumentation trùng. | Xác định một nguồn đo chính thức. |
| Có metrics nhưng không có traces | Tracing bridge, sampling hoặc exporter/collector chưa đúng. | Kiểm tra pipeline tracing riêng. |
| Tracing có span nhưng logs thiếu trace ID | Logging correlation/context không active hoặc async mất context. | Kiểm tra MDC pattern, tracing và propagation. |

## 15. Bài tập thực hành

### Bài tập 1: Registry và exporter

Ứng dụng có `/actuator/metrics/http.server.requests` trả dữ liệu nhưng `/actuator/prometheus` trả 404. Điều này chứng minh HTTP metrics không tồn tại không?

**Đáp án:** Không. Endpoint Actuator metrics có dữ liệu nhưng Prometheus registry/endpoint có thể chưa được cấu hình hoặc expose. Kiểm tra dependency `micrometer-registry-prometheus`, endpoint exposure, management port/base path và security.

### Bài tập 2: Tag nào nguy hiểm?

Với `checkout.completed`, lựa chọn nào là tag phù hợp?

- A. `outcome=success/error`.
- B. `requestId=uuid-mới-mỗi-request`.
- C. `paymentProvider=bank-a/bank-b`.
- D. `customerEmail=user@example.com`.

**Đáp án:** A và C phù hợp nếu tập giá trị hữu hạn, được quản trị. B và D có cardinality cao; D còn có nguy cơ lộ dữ liệu cá nhân. Dùng logs/traces có phân quyền thích hợp để điều tra một request riêng lẻ.

### Bài tập 3: Composite registry

Nếu ứng dụng cấu hình hai registry backend, service nên tăng cùng một counter hai lần để “gửi đủ cho hai nơi” không?

**Đáp án:** Không. Code ghi một lần qua bean `MeterRegistry` được auto-configure; composite/registries lo việc chuyển dữ liệu theo cấu hình. Ghi hai lần sẽ làm sai số.

### Bài tập 4: Vì sao không trung bình các P95?

Ba instance có lưu lượng và phân bố latency khác nhau. Dashboard tính trung bình cộng P95 từng instance. Đây có phải P95 của toàn dịch vụ không?

**Đáp án:** Không. Phân vị không cộng gộp theo cách đó. Dùng histogram buckets cùng ranh giới, gộp `rate(..._bucket[5m])` theo `le` và các chiều cần giữ trước khi gọi `histogram_quantile`.

### Bài tập 5: Metrics có, trace không có

Metrics đếm 1.000 request, trace backend chỉ lưu khoảng 100 trace. Có cần sửa `MeterRegistry` không?

**Đáp án:** Chưa có bằng chứng. Tracing có thể đang sampling 10%, hoặc exporter/collector gặp vấn đề. Kiểm tra tracing pipeline trước; metrics và traces có chính sách thu thập khác nhau.

## 16. Checklist trước khi triển khai

- [ ] `spring-boot-starter-actuator` và registry implementation phù hợp đã có trên classpath.
- [ ] Ứng dụng dùng `MeterRegistry` được Spring Boot cung cấp, tránh tạo registry riêng không chủ đích.
- [ ] Biết registry đang là Simple, Composite hay có exporter backend; xác định ai scrape/push dữ liệu.
- [ ] `/actuator/metrics` và `/actuator/prometheus` chỉ được expose khi cần và có bảo vệ phù hợp.
- [ ] Metrics HTTP, JVM và nghiệp vụ thực sự xuất hiện sau khi phát traffic thử nghiệm.
- [ ] Tên meter ổn định, tags hữu hạn, không chứa request ID hoặc dữ liệu nhạy cảm.
- [ ] Common tags xác định đúng service, environment hoặc khu vực.
- [ ] Histogram được bật có chọn lọc, dashboard kiểm tra đúng đơn vị và route.
- [ ] Không instrument trùng lặp gây đếm hai lần hoặc làm rối nguồn dữ liệu.
- [ ] Có quy trình kiểm tra scrape target, export và registry khi metric thiếu.
- [ ] Metrics được liên kết với logs/traces khi điều tra; sampling và propagation được hiểu rõ.

**Ghi nhớ:** Spring Boot có thể **auto-configure MeterRegistry** dựa trên dependency và môi trường, giúp ứng dụng đo metrics mà không cần tự khởi tạo registry ở mỗi service. Để dữ liệu thực sự hữu ích, hãy chọn registry/exporter phù hợp, giữ tags có cardinality thấp, kiểm tra histogram và pipeline, rồi kết hợp metrics với logs và distributed tracing để biến tín hiệu bất thường thành giả thuyết và bằng chứng xử lý sự cố.
