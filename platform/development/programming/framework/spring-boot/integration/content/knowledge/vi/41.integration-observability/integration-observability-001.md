# Micrometer Observation và các tích hợp do Spring Boot hỗ trợ

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, một luồng xử lý có thể đi qua HTTP controller, WebClient, database, cache, broker thông điệp và các endpoint của Spring Integration. Khi đơn hàng xử lý chậm hoặc một sự kiện bị gửi lại nhiều lần, câu hỏi vận hành không chỉ là “có lỗi hay không”, mà còn là **độ trễ phát sinh ở bước nào, luồng đã tới đâu và lỗi có ảnh hưởng đến kết quả nghiệp vụ không**.

Bài học thuộc chương **Quan sát tích hợp**, tập trung vào **Micrometer Observation** và cách Spring Boot kết nối các thành phần quan sát. Spring Boot giúp cấu hình metrics, tracing và các điểm tích hợp được hỗ trợ; ứng dụng vẫn phải định nghĩa tên phép đo, ranh giới nghiệp vụ, nhãn, thời điểm hoàn thành, xử lý lỗi và bảo mật dữ liệu.

Sau bài học, bạn có thể:

- Phân biệt **logs, metrics, traces** và vai trò của `Observation`.
- Giải thích các thành phần `ObservationRegistry`, `ObservationHandler`, `ObservationConvention`, low/high-cardinality key values.
- Dùng cấu hình Spring Boot để thu metrics/traces và tạo observation riêng cho nghiệp vụ tích hợp.
- Biết những tích hợp HTTP, messaging, database, cache và Spring Integration cần điều kiện bổ sung nào để có quan sát thực tế.
- Truyền ngữ cảnh giữa thread, reactive pipeline và các hệ thống khác mà không nhầm `traceId` với idempotency key.
- Kiểm thử, giám sát và chẩn đoán luồng tích hợp bằng tín hiệu có ý nghĩa.

> **Giới hạn quan trọng:** “Có Observation” không có nghĩa là đã có đủ cả ba tín hiệu ở hệ thống giám sát. Metrics cần registry/exporter, tracing cần tracer/exporter và propagation, còn logs cần ứng dụng và pipeline thu thập log tương ứng.

## 1. Vì sao một integration flow cần quan sát?

Xét luồng nhận sự kiện đặt hàng:

1. HTTP API nhận `OrderSubmitted`.
2. Service kiểm tra bản ghi đã xử lý trước đó để tránh trùng `eventId`.
3. Gọi Catalog API bằng `WebClient` để kiểm tra thông tin sản phẩm.
4. Ghi trạng thái vào database và outbox trong một transaction cục bộ.
5. Publisher gửi outbox sang message broker.
6. Consumer nhận sự kiện, cập nhật cache và gọi hệ thống giao hàng.

Ở luồng này, một HTTP request có thể kết thúc **trước** khi consumer xử lý xong sự kiện. Một transaction database có thể commit thành công nhưng publisher chưa gửi broker. Một timeout ở bước gọi giao hàng chưa chứng minh phía đối tác chưa thực hiện thao tác.

~~~mermaid
flowchart LR
    A["HTTP / Gateway"] --> B["Idempotency check"]
    B --> C["Catalog WebClient"]
    C --> D["DB + outbox"]
    D --> E["Broker publisher"]
    E --> F["Broker / consumer"]
    F --> G["Cache + delivery API"]
    A -. "request span" .-> H["Tracing"]
    B -.-> H
    C -.-> H
    D -.-> H
    E -.-> H
    F -.-> H
    G -.-> H
    A -. "rates & latency" .-> I["Metrics"]
    C -.-> I
    D -.-> I
    E -.-> I
    F -.-> I
    G -.-> I
    G -. "structured events" .-> J["Logs"]
~~~

Sơ đồ mô tả mục tiêu observability, **không cam kết** rằng tất cả các span được tạo sẵn hoặc trace context tự động đi qua mọi adapter. Cần kiểm tra điều kiện auto-configuration và instrumentation của mỗi thư viện.

Ba tín hiệu trả lời những câu hỏi khác nhau:

| Tín hiệu | Trả lời chủ yếu | Ví dụ |
| --- | --- | --- |
| **Metrics** | Có xu hướng lỗi, độ trễ hoặc tải bất thường hay không? | Tỷ lệ timeout, p95, số message tồn đọng |
| **Traces** | Một tác vụ cụ thể đi qua các thành phần nào và mất thời gian ở đâu? | HTTP inbound → WebClient → DB → broker |
| **Logs** | Sự kiện gì đã xảy ra ở một thời điểm, có ngữ cảnh gì? | Sự kiện bị từ chối do schema version không hỗ trợ |

Không nên biến metric thành nhật ký từng sự kiện: tag `orderId` hoặc `eventId` trên mỗi lần xử lý làm số chuỗi thời gian tăng rất lớn. Ngược lại, chỉ có logs mà không có metric sẽ khó đánh giá tốc độ lỗi, backlog hoặc p99 ở quy mô hệ thống.

## 2. Micrometer Observation là gì?

`Micrometer Observation` là abstraction cho **một hoạt động có điểm bắt đầu và kết thúc**, có thể kèm tên, thuộc tính, sự kiện và lỗi. Nó cho phép cùng một điểm instrument gửi dữ liệu tới những handler khác nhau, thay vì nghiệp vụ tự gọi API metrics và tracing ở khắp nơi.

Các thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `Observation` | Đại diện một hoạt động đang được đo; gọi `start`, mở scope, ghi lỗi/event và `stop` |
| `ObservationRegistry` | Trung tâm cấu hình và đăng ký observation/handler; Spring Boot có thể cung cấp bean đã tích hợp |
| `Observation.Context` | Giữ thông tin của một observation, phục vụ handler và convention |
| `ObservationHandler` | Phản ứng với lifecycle; có thể tạo timer, span hoặc xử lý tùy biến |
| `ObservationConvention` | Chuẩn hóa tên observation, contextual name và bộ key/value |
| `ObservationPredicate` | Quyết định observation nào bị bỏ qua |
| `ObservationFilter` | Điều chỉnh context/tags theo chính sách dùng chung |

~~~mermaid
flowchart TB
    A["Business adapter / HTTP instrumentation"] --> B["Observation"]
    B --> C["ObservationRegistry"]
    C --> D["Convention / Predicate / Filter"]
    C --> E["Meter ObservationHandler"]
    C --> F["Tracing ObservationHandler"]
    E --> G["MeterRegistry"]
    F --> H["Micrometer Tracing"]
    G --> I["Prometheus / OTLP / monitoring"]
    H --> J["OTLP collector / trace backend"]
~~~

Một observation có thể sinh timer đo khoảng `start → stop` khi được nối với meter handler, và có thể tạo span khi được nối với tracing handler. Nếu không có handler tương ứng hoặc exporter, kết quả có thể không xuất hiện trong hệ thống giám sát.

### 2.1. Vòng đời một Observation

Vòng đời thông thường:

1. Tạo observation qua `ObservationRegistry`.
2. Gắn tên/thuộc tính có ý nghĩa trước khi bắt đầu.
3. `start()`.
4. `openScope()` khi cần đưa observation vào ngữ cảnh thread hiện tại.
5. Chạy logic.
6. Ghi `observation.error(exception)` nếu có lỗi.
7. Đóng scope và `stop()` trong mọi trường hợp.

API `observe(...)` cung cấp dạng rút gọn cho công việc **đồng bộ**, tự xử lý start/scope/error/stop:

~~~java
import io.micrometer.observation.Observation;

Observation.createNotStarted("integration.order.validate", registry)
        .lowCardinalityKeyValue("source", "http")
        .observe(() -> {
            validateOrder(order);
        });
~~~

Ở ví dụ này, `registry` và `order` là các biến đã có trong component; `validateOrder` là nghiệp vụ minh họa. Tên `integration.order.validate` mô tả loại hoạt động, không chứa ID của từng đơn hàng.

### 2.2. Low cardinality và high cardinality

**Cardinality** là số giá trị khác nhau mà một key có thể nhận.

| Dữ liệu | Phạm vi nên dùng | Vì sao |
| --- | --- | --- |
| `flow=order-ingestion` | Low cardinality | Tập flow hữu hạn, phù hợp metric và trace |
| `operation=validate/apply/publish` | Low cardinality | Số giá trị nhỏ, so sánh được giữa các lần chạy |
| `outcome=success/rejected/error` | Low cardinality | Phù hợp dashboard và tỷ lệ lỗi |
| `partner=catalog/delivery` | Low cardinality nếu tập đối tác được kiểm soát | Hữu ích cho cảnh báo từng downstream |
| `eventId=evt-...` | Không đưa vào metric tag | Gần như duy nhất cho từng sự kiện |
| `orderId`, `userId`, `tenantId` | Tránh metric tag; cân nhắc bảo mật cả trong trace/log | Dễ tạo cardinality cao hoặc lộ dữ liệu |
| URL đầy đủ có query parameter | Tránh metric tag | Path tùy biến và token có thể bị lộ |
| Route template `/orders/{id}` | Low cardinality | Hữu hạn, dễ đo theo endpoint |

`lowCardinalityKeyValue(...)` thường đi vào **metrics và traces**. `highCardinalityKeyValue(...)` chỉ nên đưa vào **traces**, với chính sách bảo mật và lưu giữ phù hợp. High cardinality không đồng nghĩa “an toàn để ghi mọi ID”; tracing backend vẫn chịu chi phí và yêu cầu bảo vệ dữ liệu.

**Nguyên tắc:** định nghĩa tập nhãn từ thiết kế nghiệp vụ trước khi instrument, không lấy nguyên giá trị đầu vào từ người dùng làm metric tag.

## 3. Khởi tạo hạ tầng với Spring Boot Actuator

Với một ứng dụng Spring Boot có Spring Integration, thêm dependency cho hạ tầng và export metrics:

~~~groovy
// build.gradle - Gradle Groovy DSL
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Nếu muốn xuất metrics theo định dạng Prometheus:
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Các starter này cho phép Boot tự cấu hình nhiều thành phần Micrometer khi dependency và điều kiện phù hợp. Một số starter/nhóm package được tổ chức lại giữa Spring Boot 3.x và 4.x, vì vậy để Boot quản lý version dependency và đối chiếu bản reference tương ứng.

Cấu hình cơ bản cho môi trường thử nghiệm:

~~~yaml
spring:
  application:
    name: order-integration

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-integration
  tracing:
    sampling:
      probability: 0.1
~~~

Ý nghĩa:

- `/actuator/health`: kiểm tra trạng thái theo các health indicator đã được cấu hình.
- `/actuator/metrics` và `/actuator/metrics/{name}`: kiểm tra tên metric và những tag/measurement được xuất.
- `/actuator/prometheus`: phục vụ scrape khi có Prometheus registry và endpoint khả dụng.
- `management.metrics.tags.application`: thêm nhãn application ổn định vào metrics.
- `management.tracing.sampling.probability`: tỷ lệ lấy mẫu traces; **không** phải tỷ lệ bỏ metrics.

Ví dụ trên không cấu hình endpoint OTLP để xuất tracing. Để xuất traces cần thêm tracing implementation/exporter ở phần tiếp theo.

> **Bảo mật:** `management.endpoints.web.exposure.include` cho phép endpoint hiện diện trên HTTP management interface; hãy dùng network policy, authentication/authorization, gateway hoặc management port phù hợp. Không public toàn bộ Actuator endpoints, và không gửi secret ra metric label.

### 3.1. Bật tracing với OpenTelemetry: khác nhau theo Boot version

Spring Boot hỗ trợ Micrometer Tracing và backend như OTLP/Zipkin khi có dependency và cấu hình tương ứng.

Với **Spring Boot 4.x**, tài liệu chính thức giới thiệu starter thuận tiện cho OpenTelemetry + OTLP:

~~~groovy
// Spring Boot 4.x
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Sau đó cấu hình exporter bằng các khóa `management.opentelemetry.tracing.export.otlp.*` phù hợp với giao thức/collector. Đặt endpoint và thông tin xác thực từ cấu hình môi trường, không hard-code access token.

Với **Spring Boot 3.x**, cấu hình phổ biến dùng các dependency riêng:

~~~groovy
// Spring Boot 3.x: minh họa lựa chọn OpenTelemetry + OTLP
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Các property OTLP tracing 3.x thường thuộc nhóm `management.otlp.tracing.*`; **không áp dụng nguyên xi cấu hình 4.x cho 3.x**. Kiểm tra reference của phiên bản Boot đang sử dụng và chọn exporter được môi trường giám sát hỗ trợ.

Phân biệt:

- **Micrometer Observation**: API đánh dấu công việc được đo.
- **Micrometer Tracing**: API/bridge hỗ trợ span và propagation.
- **OpenTelemetry/Brave**: tracer implementation và định dạng propagation/export phù hợp.
- **Collector/backend**: dịch vụ nhận, lưu trữ và cho phép truy vấn traces.
- **Prometheus/OTLP MeterRegistry**: tuyến xuất metrics; không có nghĩa cùng tracer backend tự nhận metrics.

Có thể chỉ bật metrics mà không cần tracing ở giai đoạn đầu, nhưng cần đặt tên/tags nhất quán để sau này mở rộng.

## 4. Tạo Observation riêng cho nghiệp vụ tích hợp

Một HTTP request được đo tự động thường chỉ cho biết tổng độ trễ xử lý request. Nghiệp vụ còn cần biết bao nhiêu thời gian dùng để **áp dụng sự kiện vào database**, **đợi một downstream** hoặc **đẩy một message**.

Ví dụ có DTO và cổng lưu dữ liệu:

~~~java
// OrderEvent.java
public record OrderEvent(
        String eventId,
        String orderId,
        String source) {
}
~~~

~~~java
// OrderPersistencePort.java
public interface OrderPersistencePort {
    void apply(OrderEvent event);
}
~~~

Service instrument một **hoạt động đồng bộ có ranh giới rõ**:

~~~java
// OrderProcessingService.java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderProcessingService {

    private final OrderPersistencePort persistencePort;
    private final ObservationRegistry observationRegistry;

    public OrderProcessingService(
            OrderPersistencePort persistencePort,
            ObservationRegistry observationRegistry) {
        this.persistencePort = persistencePort;
        this.observationRegistry = observationRegistry;
    }

    public void process(OrderEvent event) {
        Observation.createNotStarted(
                        "integration.order.apply",
                        observationRegistry)
                .lowCardinalityKeyValue("flow", "order-ingestion")
                .lowCardinalityKeyValue("operation", "apply")
                .observe(() -> persistencePort.apply(event));
    }
}
~~~

Khi `persistencePort.apply(event)` ném exception ra ngoài lambda, `observe(...)` tự ghi error và kết thúc observation trước khi exception tiếp tục tới caller. Cách đo này bao phủ **thời gian thực thi thực của lời gọi đồng bộ**; nó không thay thế đo transaction commit nếu commit xảy ra tại một tầng khác sau khi phương thức kết thúc.

Khi cần phân biệt **lỗi bị xử lý và nuốt** với thành công thực sự, dùng vòng đời tường minh:

~~~java
Observation observation = Observation.createNotStarted(
                "integration.partner.lookup",
                observationRegistry)
        .lowCardinalityKeyValue("partner", "catalog")
        .start();

try (Observation.Scope scope = observation.openScope()) {
    invokePartner(); // Hàm minh họa; có thể ném RuntimeException
} catch (RuntimeException exception) {
    observation.error(exception);
    // Tại đây áp dụng hợp đồng fallback/throw của adapter.
    throw exception;
} finally {
    observation.stop();
}
~~~

Đảm bảo `stop()` nằm ở `finally` để tránh observation bị bỏ dở khi có lỗi. Nếu fallback xử lý thành công một lỗi nội bộ, phải định nghĩa rõ “thành công” ở cấp activity nào; có thể thêm outcome tag với tập giá trị hữu hạn hoặc tạo observation riêng cho lần fallback.

### 4.1. Gắn Observation vào một Spring Integration flow

Với Java DSL và bean service bên trên:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class OrderFlowConfiguration {

    @Bean
    IntegrationFlow orderFlow(OrderProcessingService service) {
        return IntegrationFlow.from("orders.input")
                .handle(service, "process")
                .get();
    }
}
~~~

Flow này nối channel `orders.input` với service activator. Nếu gửi qua `DirectChannel` và handler thực thi trong cùng thread, observation ở `OrderProcessingService` nằm trong đường xử lý đồng bộ. Nếu chuyển sang `ExecutorChannel`, poller hoặc broker, phạm vi transaction/trace context có thể thay đổi.

**Không bắt buộc phải đặt Observation bằng tay tại mọi endpoint.** Spring Integration có cơ chế instrumentation riêng; cần dùng quan sát tùy biến cho các khoảng công việc mang ý nghĩa nghiệp vụ cụ thể và tránh đo chồng lặp cùng một thao tác với tên khác.

### 4.2. Cách dùng @Observed

Micrometer cung cấp annotation `@Observed` để đo phương thức. Hỗ trợ quét annotation của Spring Boot cần được bật tường minh và phải có khả năng AOP phù hợp.

~~~yaml
management:
  observations:
    annotations:
      enabled: true
~~~

Trong Spring Boot 4.x, tài liệu hướng dẫn thêm dependency `org.springframework.boot:spring-boot-starter-aspectj` nếu chưa có hỗ trợ weaving/AOP. Với Spring Boot 3.x, kiểm tra yêu cầu `org.aspectj:aspectjweaver` và cấu hình trên phiên bản đang chạy.

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class PricingService {

    @Observed(
            name = "integration.price.calculate",
            lowCardinalityKeyValues = {
                    "component", "pricing-service"
            })
    public int calculate(int quantity, int unitPrice) {
        return quantity * unitPrice;
    }
}
~~~

`@Observed` tiện cho phương thức đồng bộ, nhưng nên nhớ:

- Nếu lời gọi tự gọi từ phương thức khác trong **cùng object** theo đường self-invocation, advice dựa trên proxy có thể không chạy.
- Những thành phần đã được instrument tự động như HTTP controller có thể tạo **observation trùng lặp** nếu gắn thêm annotation bừa bãi.
- Dùng một cách đo có ranh giới rõ: annotation, API thủ công hoặc instrumentation sẵn có theo nhu cầu.

## 5. Những tích hợp do Spring Boot hỗ trợ

Mức độ tự động khác nhau theo thư viện, phiên bản và cấu hình.

| Khu vực | Có thể quan sát được | Điều kiện/ranh giới thực tế |
| --- | --- | --- |
| **HTTP inbound (Spring MVC/WebFlux)** | Request count, latency, status, HTTP server spans | Cần web stack và cấu hình observation/metrics/tracing phù hợp |
| **WebClient** | HTTP client metrics/traces; propagation trace headers | Dùng `WebClient.Builder` do Boot auto-configure; không tự dựng client mất cấu hình Boot |
| **RestClient/RestTemplate** | HTTP client observations và trace propagation | Dùng builder/template do Boot quản lý hoặc customizer phù hợp |
| **JDBC/DataSource** | Pool metrics; có thể có SQL observations qua instrumentation bổ sung | Pool metrics **khác** query tracing; JDBC query spans cần thành phần như Datasource Micrometer |
| **R2DBC** | Connection pool/driver metrics hoặc observations | Observability R2DBC của Boot cần dependency/cấu hình hỗ trợ, ví dụ `r2dbc-proxy` |
| **Cache** | Các chỉ số provider như hits/misses/eviction khi được instrument | Phụ thuộc Caffeine/Redis/provider; không mặc nhiên có span cho mọi `@Cacheable` |
| **Kafka/Rabbit/JMS** | Send/receive, listener/container hoặc client metrics/spans | Phụ thuộc adapter, listener/template observation flags, transport và exporter |
| **Spring Integration** | Gateway, producer/channel, handler và endpoint metrics/traces | Cần hạ tầng Observation + cấu hình quản lý Integration phù hợp |
| **Thread pools/schedulers** | Active threads, queue, task metrics tùy bean/provider | Không bảo đảm trace context tự đi qua mọi executor |
| **Application logic** | Domain operation latency, outcome, error | Tạo `Observation`/`@Observed` có chủ đích |

Ở database, phân biệt **“pool còn bao nhiêu connection”** với **“query nào chậm”**. Chỉ có Hikari metrics không chứng minh việc truy vết từng truy vấn SQL đã bật. Tương tự, một broker client có metric network tốt nhưng nếu listener không propagate trace context, sẽ khó nhìn thấy một trace xuyên producer và consumer.

### 5.1. Giữ builder HTTP do Boot quản lý

Ví dụ sử dụng `WebClient.Builder` được tiêm:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class CatalogHttpConfiguration {

    @Bean
    WebClient catalogWebClient(WebClient.Builder bootBuilder) {
        return bootBuilder
                .baseUrl("https://catalog.example.org")
                .build();
    }
}
~~~

URL ở trên chỉ minh họa; hệ thống thực lấy URL từ `@ConfigurationProperties`. Builder do Boot cung cấp là điểm nối quan trọng để nhận các cấu hình connector, observation registry và tracing propagation tương ứng. Tạo bằng `WebClient.create(...)` hoặc `WebClient.builder()` trực tiếp **không mặc nhiên** kế thừa toàn bộ cấu hình instrument của Boot.

Khi app gọi outbound HTTP, hoạt động HTTP client có thể xuất hiện như span con của request inbound **nếu có active observation context và tracer phù hợp**. Nếu lời gọi chạy ở thread khác, cần thêm context propagation (phần 7).

### 5.2. Broker, database và cache: không suy rộng từ HTTP

Đối với broker, `publish()` thành công không đồng nghĩa consumer đã commit nghiệp vụ; quan sát tối thiểu cần phân biệt **send, acknowledgment, receive, process, retry và dead-letter**. Với Kafka/AMQP, bật observation ở listener/template/adapter theo đúng version thư viện; không giả định mọi broker adapter tự tạo span từ việc chỉ thêm Actuator.

Với cache, các chỉ số như hit ratio hoặc eviction chỉ có nếu provider có instrumentation tương ứng. Cache miss có thể làm request tổng chậm, nhưng muốn biết chậm do cache lookup hay downstream, cần tách observation rõ ràng và tránh ghi key dữ liệu nhạy cảm vào tag.

## 6. Quan sát các endpoint Spring Integration

Spring Integration hiện đại có `IntegrationManagement` và hỗ trợ Micrometer metrics/Observation. Một điểm dễ bỏ sót: **có `ObservationRegistry` bean chưa chắc toàn bộ Integration endpoint được instrument**.

Theo tài liệu Spring Integration, `@EnableIntegrationManagement` cho phép cấu hình tập component cần theo dõi thông qua `observationPatterns`. Mặc định, không tự bật Observation cho tất cả các component `IntegrationManagement`.

Ví dụ bật rộng để tìm hiểu trong môi trường thử nghiệm:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegrationManagement;

@Configuration(proxyBeanMethods = false)
@EnableIntegrationManagement(observationPatterns = "*")
public class IntegrationObservabilityConfiguration {
}
~~~

- `observationPatterns = "*"` yêu cầu instrument các component được hỗ trợ có tên khớp.
- Khi production có nhiều flow/endpoint, chỉ chọn nhóm cần quan sát theo quy ước đặt tên để giảm chi phí và cardinality.
- Cần `ObservationRegistry` và handler được cấu hình phù hợp. Không nhầm `observationPatterns` với chính sách chọn trace sampling.
- Tên metric và quy ước có thể thay đổi theo version; kiểm tra các endpoint thực tế trong `/actuator/metrics`.

Các tên observation/metric được Spring Integration tài liệu hóa gồm:

| Observation/metric | Ý nghĩa | Ví dụ tag giới hạn tập giá trị |
| --- | --- | --- |
| `spring.integration.gateway` | Thời gian xử lý gateway request-reply | Component name, type, outcome |
| `spring.integration.handler` | Thời gian ở message handler | Component name, type |
| `spring.integration.producer` | Hoạt động tạo/gửi message từ component được instrument | Component name, type |
| `spring.integration.*.active` | Long-task timer cho hoạt động đang chạy, khi được hỗ trợ | Tag đã có từ thời điểm start |

Tên cấu phần phải ổn định giữa các lần deploy. Không đặt tên channel/endpoint bằng `orderId`, tenant hoặc thông tin người dùng, vì component name có thể trở thành nhãn metric.

### Quan sát flow khác đo nghiệp vụ

Trong flow `orders.input → filter → transformer → handler`:

- Observation của **gateway** cho biết thao tác tiếp nhận/tương tác.
- Observation của **handler** cho biết thời gian một endpoint xử lý.
- Observation tùy biến `integration.order.apply` diễn giải một bước mang ý nghĩa nghiệp vụ.
- Observation của **HTTP client** thể hiện lời gọi dịch vụ ngoài.
- Observation của **DB** thể hiện mức instrument của pool/query.

Các đoạn thời gian này có thể **lồng nhau**. Cộng tổng thời gian của tất cả observation sẽ đếm chồng thời gian và không bằng latency đầu-cuối. Dùng distributed tracing để xem quan hệ parent/child và phân tích critical path.

## 7. Trace context xuyên thread, reactive pipeline và broker

Một trace thường có `traceId` để liên kết nhiều span; một span có `spanId` riêng. Khi dòng công việc đi sang thread, process hoặc broker khác, phải truyền **trace context** sao cho consumer có thể tiếp tục mối liên hệ.

~~~mermaid
sequenceDiagram
    participant API as HTTP API
    participant S as Order Service
    participant C as WebClient/Catalog
    participant B as Broker
    participant W as Worker Consumer
    API->>S: request + trace context
    S->>C: outbound HTTP + trace headers
    C-->>S: response
    S->>B: event + propagated context
    B-->>W: redelivery/delivery
    W->>W: consumer span + business processing
~~~

Sơ đồ có giả định **instrumentation của producer/consumer thực sự gửi và trích xuất các header propagation**; broker không tự làm việc này chỉ vì payload có `correlationId`.

### 7.1. Reactive context và thread-local

Trong code đồng bộ, active observation thường nằm trong thread-local scope. Reactor có thể chuyển execution sang thread khác, nên giá trị thread-local không mặc nhiên sẵn có tại mọi operator.

Spring Boot có thuộc tính:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Khi sử dụng `auto`, Boot có thể bật context propagation tự động của Reactor theo khả năng của phiên bản và thư viện hiện có. Điều này tạo chi phí vận hành nhất định, nên hãy kiểm thử span thực tế trên những luồng sử dụng `publishOn`, `subscribeOn`, `flatMap` hoặc async client.

**Bẫy đo sai trong reactive code:**

~~~java
// Sai nếu mục tiêu là đo toàn bộ network I/O:
return Observation.createNotStarted("catalog.fetch", registry)
        .observe(() -> webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class));
~~~

`bodyToMono(...)` trả về một publisher chưa được subscribe. Lambda `observe(...)` ở đây kết thúc sau khi **tạo publisher**, trước khi network I/O thực sự hoàn tất. Nếu cần đo latency reactive, dùng instrumentation có lifecycle gắn với `subscription → terminal signal` và context propagation phù hợp; không đo thời gian tạo `Mono` như thể đó là thời gian HTTP.

Với WebClient, ưu tiên instrumentation có sẵn từ builder do Boot cung cấp. Với pipeline Reactor tùy biến, dùng giải pháp observation/tracing của Reactor phiên bản đang dùng hoặc khai báo thời điểm start/stop theo tín hiệu terminal và cancellation.

### 7.2. Executor, @Async và poller

Khi xử lý qua `ExecutorChannel`, `@Async` hoặc poller của Spring Integration, caller và consumer thường nằm ở thread khác. Cần chú ý:

- Gửi công việc sang executor không đảm bảo mang toàn bộ observation scope sang thread mới.
- Nếu dùng `AsyncTaskExecutor` được Boot auto-configure, một số phiên bản Boot hỗ trợ `spring.task.execution.propagate-context`; kiểm tra property theo version trước khi dùng.
- Nếu tự khai báo executor, có thể cần `ContextPropagatingTaskDecorator` hoặc cơ chế propagation tương đương.
- Truyền trace context không đồng nghĩa truyền transaction context; một transaction JDBC của thread gửi không tự chạy xuyên `ExecutorChannel`.

### 7.3. Propagation và idempotency là hai hợp đồng khác nhau

| Giá trị | Mục đích | Có nên dùng để loại trùng? |
| --- | --- | --- |
| `traceId` | Kết nối dấu vết request/process giữa các span | **Không**; một nghiệp vụ có thể có nhiều lần thử/trace |
| `spanId` | Định danh một đơn vị đo trong trace | **Không** |
| `correlationId` | Liên kết các message thuộc cùng quy trình nghiệp vụ | Chỉ khi hợp đồng quy định rõ ý nghĩa |
| `eventId`, `idempotencyKey` | Định danh sự kiện/tác động nghiệp vụ để kiểm soát gửi trùng | **Có**, với store/unique constraint và quy tắc atomic |
| `outboxId` | Theo dõi bản ghi chờ publish | Hữu ích cho quy trình publish/retry, nhưng chưa đủ cho consumer idempotency |

Đừng copy toàn bộ baggage hoặc header của request nguồn vào broker message. Chỉ forward trace context được chuẩn hóa và metadata nghiệp vụ đã qua kiểm tra.

## 8. Quan sát lỗi, retry, transaction và xử lý trùng lặp

Observability phải phản ánh **kết quả thực tế** của luồng, không chỉ đếm exception.

Ví dụ consumer gặp timeout khi gọi delivery service:

1. Broker đã giao `OrderReady` cho consumer.
2. Consumer gửi HTTP POST đến delivery service.
3. HTTP request timeout; không chắc đối tác đã nhận hay chưa.
4. Consumer retry với cùng `idempotencyKey`.
5. Nếu đối tác hỗ trợ idempotency, có thể trả kết quả của lần đầu.
6. Chỉ ack broker khi hợp đồng consumer/broker cho phép xác nhận hoàn thành.

Các điểm quan sát nên tách biệt:

| Sự kiện | Đo gì? | Lưu ý |
| --- | --- | --- |
| Message received | Số lần được giao tới consumer | Bao gồm redelivery, không phải số nghiệp vụ duy nhất |
| Duplicate discarded | Số event bị loại do idempotency | Đếm theo event type ổn định |
| Business apply | Latency + outcome của nghiệp vụ | Chỉ “success” khi hiệu ứng đã được commit đúng ranh giới |
| HTTP outbound attempt | Latency/status/exception của **mỗi lần thử** | Retry nhiều lần tạo nhiều HTTP attempt |
| Final delivery result | Outcome cuối của thao tác theo chính sách retry | Khác tỷ lệ lỗi của attempt |
| Outbox publish | Backlog, tuổi bản ghi, send attempt, acknowledged | Send success không đồng nghĩa consumer done |
| DLQ/recovery | Số message hết retry và tuổi tồn đọng | Cần quy trình replay/đối soát |

Nếu exception được catch và trả fallback, span HTTP outbound có thể ghi error trong khi observation nghiệp vụ trả thành công theo hợp đồng. Không nên “sửa” metric HTTP thành success để làm đẹp số liệu. Thay vào đó, định nghĩa outcome của mỗi lớp theo đúng trách nhiệm.

### Observation và transaction

Khi cần đo độ trễ **đến lúc DB commit**, vị trí tạo/stop observation phải bao trùm đúng điểm commit (chẳng hạn đo ở wrapper ngoài lời gọi được áp dụng `@Transactional`), thay vì chỉ đo bên trong một method đang ở transaction chưa hoàn tất.

Với một flow chạy qua `DirectChannel` trong cùng thread, một transaction local có thể bao phủ các bước DB tương thích nếu được cấu hình. Sang `ExecutorChannel`/broker thì không có transaction ACID chung mặc định. Trace liên kết các bước để nhìn thấy diễn biến, nhưng **không cung cấp tính nguyên tử hoặc bảo đảm delivery**.

### Retry và sampling

Nếu sampling rate thấp, có thể thiếu trace cụ thể của một lỗi hiếm. Metrics về tổng số lỗi và độ trễ vẫn có thể đo được nếu instrument đầy đủ, trong khi trace backend chỉ lưu mẫu. Với lỗi quan trọng cần điều tra, kết hợp:

- Metric counter/timer theo **outcome** có cardinality thấp.
- Structured logs chứa traceId/spanId khi tracing context hiện diện.
- Lựa chọn sampling theo SLO/chi phí, và khả năng tail-based sampling tại collector nếu kiến trúc hỗ trợ.
- Business event ID ở audit/inbox/outbox store (có truy cập kiểm soát), không phải metric label.

## 9. Sơ đồ đo đạc đề xuất cho một hệ thống tích hợp

Từ cùng luồng order ingestion, chọn vài chỉ số trả lời được hành động vận hành cụ thể:

| Nhóm | Metric/quan sát gợi ý | Tác dụng |
| --- | --- | --- |
| HTTP ingress | Request rate, 4xx/5xx, p95/p99 | Phát hiện lỗi tại API |
| HTTP downstream | Duration và timeout theo `partner` | Nhận biết Catalog/Delivery suy giảm |
| Business operation | `integration.order.apply` theo `outcome` | Đo xử lý nghiệp vụ thành công/lỗi |
| Idempotency | Duplicate events / total events | Phát hiện redelivery hoặc upstream gửi trùng |
| DB | Pool active/idle/pending; query latency nếu đã instrument | Phân biệt cạn pool và truy vấn chậm |
| Cache | Hit ratio, miss, eviction, backend error | Kiểm tra cache giúp hay hại |
| Broker | Consumer lag, queue depth, redelivery, DLQ | Phát hiện tồn đọng |
| Outbox | Rows pending, oldest age, publish attempts | Phát hiện kẹt đồng bộ DB → broker |
| Spring Integration | Gateway/handler/producer duration | Xác định endpoint xử lý chậm |

Ví dụ một dashboard thực dụng nên đặt cạnh nhau **request rate, error rate, latency p95/p99 và saturation/backlog** để người vận hành thấy xu hướng. Với luồng bất đồng bộ, thêm **độ trễ từ khi event được nhận đến khi hiệu ứng nghiệp vụ hoàn thành** dựa trên timestamp được chuẩn hóa và có kiểm soát clock skew.

Một SLO có ý nghĩa có thể là: “99% sự kiện hợp lệ được áp dụng trong 30 giây kể từ khi broker nhận”, nhưng chỉ đặt mục tiêu đó nếu có timestamp/ack và dữ liệu đo để kiểm chứng. Đừng mặc định latency HTTP inbound là latency toàn bộ quy trình nếu consumer chạy sau.

## 10. Kiểm thử Observation và cấu hình auto-configuration

Kiểm thử nên chứng minh **một hành vi quan sát thật** đã xảy ra, thay vì chỉ xác minh `ObservationRegistry` bean tồn tại.

### 10.1. Unit test vòng đời và tên metric

Có thể kiểm tra một observation đồng bộ với Micrometer Registry đơn giản, không cần backend bên ngoài:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderObservationTest {

    @Test
    void recordsOneCompletedOperation() {
        var meterRegistry = new SimpleMeterRegistry();
        var observationRegistry = ObservationRegistry.create();

        observationRegistry.observationConfig()
                .observationHandler(
                        new DefaultMeterObservationHandler(meterRegistry));

        Observation.createNotStarted(
                        "integration.order.apply",
                        observationRegistry)
                .lowCardinalityKeyValue("flow", "order-ingestion")
                .observe(() -> {
                    // Thao tác đồng bộ minh họa.
                });

        assertEquals(
                1L,
                meterRegistry.get("integration.order.apply")
                        .tag("flow", "order-ingestion")
                        .timer()
                        .count());
    }
}
~~~

Các class test sử dụng Micrometer và JUnit. `SimpleMeterRegistry` ở đây xác nhận observation **đã được handler chuyển thành timer**, nhưng không chứng minh có trace export, HTTP propagation hoặc integration auto-configuration.

### 10.2. Spring Boot integration test

Trong một test dùng `@SpringBootTest`, kiểm tra:

1. `ObservationRegistry` được Boot inject và có handler/registry theo dependency.
2. Flow hoặc HTTP adapter nhận client/builder do Boot auto-configure.
3. Gọi endpoint mô phỏng bằng HTTP stub hoặc broker test fixture; metric/span xuất hiện khi component được instrument.
4. Lỗi timeout/HTTP 5xx/duplicate tạo kết quả quan sát theo hợp đồng.
5. Flow có `@EnableIntegrationManagement` và `observationPatterns` sinh instrumentation cho đúng nhóm endpoint.
6. Nếu có tracing, xác minh context propagation giữa request và outbound, hoặc producer và consumer.

**Lưu ý:** Spring Boot có thể không bật **trace reporting/export** trong một số cấu hình `@SpringBootTest`, để tránh test gửi span ra ngoài. Muốn assert spans, sử dụng registry/tracer test phù hợp hoặc cấu hình exporter in-memory cho fixture; không suy ra tracing hỏng vì backend production không nhận span trong bài test.

### 10.3. Kiểm thử mất ngữ cảnh và dữ liệu nhạy cảm

Các bài test có giá trị cao:

- Thay `DirectChannel` bằng `ExecutorChannel` hoặc một `publishOn` trong Reactor; kiểm tra parent-child trace.
- Gửi sự kiện qua broker stub và xác minh trace headers được inject/extract.
- Đọc metric names/tags và khẳng định không có `userId`, `eventId`, access token hoặc URL query nguyên vẹn.
- Tạo 100 eventId khác nhau; số series metric không tăng theo từng event.
- Inject lỗi trong handler, xác minh observation đã kết thúc và có error/outcome phù hợp.
- Lặp lại sự kiện đã commit để xác minh metric duplicate tăng, còn business apply không tăng.

## 11. Các lỗi thường gặp khi triển khai

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Có Actuator nhưng không thấy traces | Thiếu tracing implementation/exporter, sampling hoặc collector | Kiểm tra dependency, exporter endpoint, tỷ lệ sampling, collector |
| Có `ObservationRegistry` nhưng không thấy metric nghiệp vụ | Không có meter handler, observation không được stop, không có registry/exporter | Kiểm tra lifecycle, handler và `/actuator/metrics` |
| WebClient không có trace headers | Client được tự tạo ngoài builder của Boot hoặc không có trace context đang active | Tiêm `WebClient.Builder` do Boot quản lý và kiểm tra propagation |
| Flow Spring Integration không có observation | Chưa cấu hình `@EnableIntegrationManagement(observationPatterns=...)` hoặc thiếu registry | Kiểm tra component names/patterns và điều kiện phiên bản |
| Span bị đứt khi chuyển thread | Thread-local context không được propagate | Kiểm tra executor, Reactor context propagation, adapter transport |
| Timer chỉ vài microseconds dù HTTP rất chậm | Đo lúc **tạo `Mono`** chứ không đo subscription | Dùng HTTP client instrumentation hoặc operator theo lifecycle reactive |
| p95 xấu nhưng trace không tìm thấy request | Sampling chỉ giữ một phần traces | Xem metrics/logs; điều chỉnh sampling có kiểm soát |
| Metric store tốn bộ nhớ quá mức | Tên/tag chứa ID khác nhau cho mỗi request | Giới hạn cardinality, chuẩn hóa route/endpoint |
| Có database pool metrics nhưng không có SQL spans | Chưa instrument query layer | Thêm instrumentation JDBC/R2DBC được hỗ trợ |
| Đã thêm `@Observed` nhưng metric lặp | Tự instrument chồng lên auto instrumentation | Gỡ một lớp đo hoặc phân định ranh giới khác nhau |
| Retry tăng số request nhưng “order failed” thấp | Metric attempt và metric outcome cuối khác nhau | Tạo dashboard riêng cho attempt, final outcome |
| Traces nhìn thấy nhưng không có audit/idempotency | Observation không bảo đảm tác động nghiệp vụ chỉ một lần | Dùng eventId, unique constraint, inbox/outbox và transactional design |

## 12. Checklist trước khi triển khai

- [ ] Có kiến trúc ba tín hiệu: logs, metrics, traces, mỗi tín hiệu có backend và chính sách lưu giữ phù hợp.
- [ ] Dùng `ObservationRegistry` do Boot cấu hình khi instrument phần nghiệp vụ.
- [ ] Đã đặt observation name và tập low-cardinality tags ổn định; không đặt ID hoặc secret vào metric.
- [ ] HTTP outbound dùng builder do Boot quản lý để giữ instrumentation và propagation.
- [ ] Với Spring Integration, đã kiểm tra `@EnableIntegrationManagement` và phạm vi `observationPatterns`.
- [ ] Đã kiểm thử propagation qua thread, Reactor pipeline và broker theo luồng thực tế.
- [ ] Metrics phân biệt các attempt retry với kết quả cuối và trạng thái commit nghiệp vụ.
- [ ] Đã có alert cho error rate, latency, queue lag, outbox age và DLQ theo nhu cầu.
- [ ] Test chứng minh observation được stop, lỗi được ghi nhận và không sinh high-cardinality metric labels.
- [ ] Actuator/collector/exporter được bảo vệ; không gửi payload bí mật hoặc PII qua logs, spans và tags.

**Ghi nhớ:** Spring Boot và Micrometer cung cấp một nền tảng Observation thống nhất, giúp nhiều thư viện ghi metrics và traces theo chuẩn chung. Một luồng tích hợp chỉ thực sự quan sát được khi **đo đúng ranh giới nghiệp vụ, đặt tên/tags đúng, truyền ngữ cảnh qua các transport và hiểu thời điểm một tác động được commit**. Observation giúp thấy vấn đề để xử lý, nhưng không thay thế hợp đồng dữ liệu, transaction, retry và idempotency.

## Tài liệu tham khảo

- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): `ObservationRegistry`, handler, context propagation, annotation và tích hợp JDBC/R2DBC.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registries, metric instrumentation và xuất metrics.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, tracer implementation, OTLP, sampling và HTTP propagation.
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): đối chiếu dependencies và properties với nhánh 3.x.
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): mô hình observation và cách ghi sự kiện.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): registry, context, handlers, conventions, cardinality và metric conversion.
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): `@EnableIntegrationManagement`, `observationPatterns` và các observation conventions.
