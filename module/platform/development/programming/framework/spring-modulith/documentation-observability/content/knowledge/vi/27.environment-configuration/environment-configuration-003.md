# Profile staging để kiểm thử backend thật

## 1. Vai trò của profile staging

Trong một ứng dụng Spring Boot được tổ chức thành **application module** bằng Spring Modulith, kiểm thử trên máy cá nhân mới chứng minh được một phần hành vi. Ứng dụng có thể khởi động và các unit test đều xanh, nhưng khi chạy với PostgreSQL, dịch vụ HTTP, OpenTelemetry Collector và trace backend thật, lỗi cấu hình, transaction hoặc context propagation mới xuất hiện.

Bài này thuộc module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY** và chương **Cấu hình môi trường**. Mục tiêu là dùng **Spring profile `staging`** để kiểm thử ứng dụng trên hạ tầng dành riêng cho staging, đồng thời đối chiếu **module graph, Spring Boot Actuator, event metrics, tracing và context propagation** với hoạt động thực tế của các module.

Cụm từ **backend thật** gồm hai nhóm tài nguyên:

- **Backend nghiệp vụ:** cơ sở dữ liệu, API, message broker hoặc dịch vụ tích hợp được triển khai thật trong môi trường staging. Chúng thực thi giao thức và lưu trạng thái, khác với mock/stub chỉ trả dữ liệu cố định.
- **Backend quan sát:** bộ thu thập OTLP, hệ thống lưu trace (như Jaeger hoặc Tempo), Prometheus và nơi tập trung log; phải thực sự nhận dữ liệu để chứng minh pipeline telemetry hoạt động.

Các backend này chỉ sử dụng dữ liệu thử nghiệm và thông tin xác thực staging, độc lập với production.

Sau bài này, người học sẽ biết cách:

1. Phân chia cấu hình chung và cấu hình theo profile staging.
2. Inject URL, credential, sampling và cấu hình Actuator mà không đưa secret vào source.
3. Deploy cùng một artifact với backend staging thật và kiểm tra giá trị cấu hình có hiệu lực.
4. Xác minh luồng request → event publication → listener bất đồng bộ → side effect.
5. Theo dõi request, event và module interaction bằng trace, log, metrics và registry.
6. Thiết lập smoke test, kiểm thử failure/retry và điều kiện chấp nhận trước phát hành.

> Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Modulith với BOM tương thích và Micrometer Tracing. Tên dependency, property và span tự động có thể khác giữa các phiên bản; cần xác nhận trên bản đang sử dụng. Mọi hostname trong bài là ví dụ minh họa.

## 2. Staging phải giống production ở những điểm nào?

Spring profile chọn cấu hình và bean phù hợp; **profile không tự tạo hạ tầng**. Một bài staging thực chất phải có database, network, secret, migration, executor và telemetry pipeline thật.

| Khía cạnh | Local / development | Staging | Production |
| --- | --- | --- | --- |
| Mục tiêu | Phát triển nhanh | Xác nhận tích hợp và vận hành | Phục vụ người dùng |
| Database | Có thể dùng Testcontainers | PostgreSQL staging + migration thật | Database production |
| External API | Có thể mock | API staging qua network/TLS | API production |
| Event publication | Có thể thử in-memory | Registry lưu bền khi yêu cầu | Registry lưu bền, monitoring |
| Trace | Có thể dùng collector local | Collector và backend trace staging | Pipeline trace production |
| Metrics | Kiểm tra local | Actuator + Prometheus/Grafana staging | Giám sát theo SLO |
| Dữ liệu | Fixture cục bộ | Dữ liệu tổng hợp, có cleanup | Dữ liệu thực |
| Sampling | Có thể cao | Cao cho lab, điều chỉnh theo tải | Chính sách tiết kiệm tài nguyên |

Một staging hữu ích tương đồng ở những tính chất quyết định: loại datastore, ranh giới transaction, cấu hình bảo mật, cơ chế chạy async, giao thức downstream và exporter. Quy mô máy không nhất thiết giống production nếu mục tiêu chưa phải load test.

**Ba tình huống staging cần phát hiện:** request trả 200 nhưng listener chưa xong; event được phát nhưng transaction nguồn rollback; trace exporter có cấu hình nhưng collector/backend không nhận span.

## 3. Mô hình ứng dụng Spring Modulith trên staging

Giả sử ứng dụng đặt hàng có hai module trong cùng một JVM:

- **orders:** tạo đơn và phát `OrderPlaced`.
- **fulfillment:** nhận sự kiện rồi ghi yêu cầu hoàn tất đơn và có thể gọi một external API của staging.

~~~mermaid
flowchart LR
    T[Client / CI smoke test] --> A[Spring Boot staging]
    subgraph M[Spring Modulith trong cùng JVM]
        O[orders] -->|OrderPlaced| F[fulfillment]
    end
    A --> M
    M --> P[(PostgreSQL staging)]
    M --> X[External HTTP API staging]
    M -->|OTLP spans| C[OTel Collector staging]
    C --> J[Jaeger / Tempo staging]
    M -->|Actuator metrics| E[Metrics endpoint]
    R[Prometheus staging] -->|Scrape| E
    M --> L[Structured logs staging]
~~~

Hình trên có bốn ranh giới cần hiểu:

1. **Module boundary:** orders và fulfillment là các application module độc lập về thiết kế, nhưng vẫn chạy cùng JVM. Spring application event không tự biến thành message qua network.
2. **Transaction boundary:** ghi orders, commit và listener xử lý sau commit có các mốc thời gian khác nhau.
3. **Thread boundary:** listener bất đồng bộ chạy trên executor; tracing context không nhất thiết được truyền tự động.
4. **Infrastructure boundary:** PostgreSQL, external HTTP service và Collector nằm ngoài tiến trình; phải xác minh network, credentials và dữ liệu thực sự tới đích.

Khi kiểm thử, cần chứng minh từng ranh giới thay vì chỉ gọi một API và nhìn HTTP 200.

## 4. Cấu trúc các tệp cấu hình

Tổ chức tài nguyên cấu hình theo quy ước Spring Boot:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-staging.yml
  application-prod.yml
~~~

`application.yml` chứa mặc định chung, còn `application-staging.yml` ghi đè các giá trị dành cho staging. Phương pháp này thuận tiện hơn nhân bản các class cấu hình theo môi trường nếu logic vẫn giống nhau.

### 4.1. application.yml — cấu hình chung

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true

logging:
  level:
    root: INFO
~~~

Cấu hình chung mặc định chỉ công khai lượng thông tin Actuator tối thiểu. Staging có thể bổ sung metric endpoints nhưng cần bảo vệ truy cập.

### 4.2. application-staging.yml — backend thật

~~~yaml
spring:
  datasource:
    url: ${STAGING_JDBC_URL}
    username: ${STAGING_DB_USER}
    password: ${STAGING_DB_PASSWORD}
    hikari:
      maximum-pool-size: 8

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
      environment: staging
  tracing:
    sampling:
      probability: ${STAGING_TRACING_SAMPLE_PROBABILITY:1.0}
  otlp:
    tracing:
      endpoint: ${STAGING_OTLP_TRACES_ENDPOINT}

integration:
  fulfillment:
    base-url: ${STAGING_FULFILLMENT_BASE_URL}

logging:
  pattern:
    level: "%5p [${spring.application.name:},traceId=%X{traceId:-},spanId=%X{spanId:-}]"
~~~

**Giải thích chính xác từng nhóm:**

- **spring.datasource:** kết nối database staging bằng credential được inject lúc chạy.
- **management.tracing.sampling.probability:** tỷ lệ chọn mẫu trace; giá trị 1.0 có ích trong lab nhỏ, nhưng gây tăng chi phí ở tải lớn.
- **management.otlp.tracing.endpoint:** endpoint **OTLP HTTP** nhận traces, ví dụ đường `/v1/traces`; collector vẫn cần được cấu hình để gửi tiếp đến backend.
- **management.endpoints.web.exposure:** cho phép truy cập thêm metrics/Prometheus; còn cần đúng registry và access policy.
- **management.metrics.tags.environment:** tag hữu hạn để phân biệt số liệu staging.
- **integration.fulfillment.base-url:** thuộc tính **tự định nghĩa**; phải có configuration properties hoặc client adapter đọc nó. Spring Boot không tự gọi external API nhờ có key này.
- **logging.pattern.level:** chèn `traceId` và `spanId` từ MDC khi tracing bridge/context logging đang hoạt động; trường có thể rỗng khi không có active trace.

Một bộ biến môi trường mẫu:

~~~text
SPRING_PROFILES_ACTIVE=staging
STAGING_JDBC_URL=jdbc:postgresql://postgres.staging.internal:5432/shop_staging
STAGING_DB_USER=shop_staging_app
STAGING_DB_PASSWORD=<injected-by-secret-manager>
STAGING_OTLP_TRACES_ENDPOINT=http://otel-collector.staging.internal:4318/v1/traces
STAGING_FULFILLMENT_BASE_URL=https://fulfillment.staging.example.test
STAGING_TRACING_SAMPLE_PROBABILITY=1.0
~~~

Danh sách trên là minh họa, không phải tệp chứa secret dùng chung. Hệ thống triển khai nên dùng Kubernetes Secret, secret manager hoặc chức năng tương đương; không commit mật khẩu, token và private key.

### 4.3. Quy tắc kích hoạt profile

Có thể kích hoạt bằng command line:

~~~bash
java -jar shop-modulith.jar --spring.profiles.active=staging
~~~

Hoặc inject biến môi trường `SPRING_PROFILES_ACTIVE=staging` khi chạy container.

Các điểm cần nhớ:

- **Không đặt `spring.profiles.active` trong `application-staging.yml`** để tự kích hoạt chính profile đó; dùng giá trị ngoài tài liệu cấu hình theo profile.
- `spring.config.activate.on-profile` dùng cho một tài liệu YAML có điều kiện khi thực sự cần nhiều tài liệu trong cùng một file.
- Environment variable/command line có thể ghi đè giá trị trong YAML theo thứ tự ưu tiên của Spring Boot.
- Tránh trộn profile `staging` và `prod` trong cùng một deploy, vì ghi đè sai có thể đưa tài nguyên production vào staging.
- Sử dụng **cùng artifact/image digest** trên staging và production; chỉ cấu hình và secret được thay đổi khi deploy.

## 5. Dependency của observability và event registry

Ví dụ Gradle khi các BOM Spring Boot/Spring Modulith đã quản lý version tương thích:

~~~groovy
dependencies {
    implementation("org.springframework.modulith:spring-modulith-starter-core")
    implementation("org.springframework.modulith:spring-modulith-starter-observability")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("org.postgresql:postgresql")

    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")

    // Cần nếu muốn dùng /actuator/prometheus:
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    // Chọn khi dùng registry publication lưu bền bằng JDBC:
    implementation("org.springframework.modulith:spring-modulith-starter-jdbc")
}
~~~

Dự án thực tế có thể cần thêm Spring Web, Spring Data, Flyway/Liquibase, HTTP client và security. Tùy phiên bản, tên artifact hay cơ chế tự cấu hình có thể thay đổi; cần đồng bộ BOM trước khi chốt thiết kế.

**Không giả định thêm JDBC starter đã tự tạo đủ bảng.** Persistent event publication registry cần schema/database tương thích với implementation đang dùng và migration hoặc initializer theo tài liệu của chính phiên bản đó. Migration nên chạy trong pipeline trước smoke test.

Nếu dự án đã cài một implementation event registry khác, hãy tránh đăng ký nhiều implementation cùng lúc.

## 6. Client tích hợp thật phải nhận cấu hình staging

Một service có thể khởi động đúng profile nhưng vẫn gọi mock server qua URL hardcoded trong Java. Cần có một adapter duy nhất đọc endpoint từ cấu hình:

~~~java
import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integration.fulfillment")
public record FulfillmentClientProperties(URI baseUrl) {
}
~~~

Đăng ký record bằng `@ConfigurationPropertiesScan` trên Spring Boot application hoặc `@EnableConfigurationProperties(FulfillmentClientProperties.class)` trong cấu hình. Client inject `FulfillmentClientProperties` và sử dụng `baseUrl()` để khởi tạo HTTP client thật.

Lưu ý phân biệt:

- **fulfillment module** là thành phần trong cùng JVM, tuân theo module graph.
- **fulfillment API** là backend ngoài tiến trình mà module có thể gọi qua HTTP.

Đối với outbound HTTP, cấu hình thêm connect/read timeout, auth, TLS trust, retry có giới hạn và propagation tracing headers. Không tắt TLS verification chỉ để smoke test vượt qua lỗi chứng chỉ.

## 7. Quan sát event publication và async listener trên staging

Luồng ví dụ:

~~~mermaid
sequenceDiagram
    autonumber
    participant H as HTTP request
    participant O as orders
    participant DB as PostgreSQL staging
    participant R as Publication registry
    participant F as fulfillment listener
    participant B as External API staging
    H->>O: POST /orders
    O->>DB: Lưu Order
    O->>R: Ghi nhận publication theo transaction
    O->>O: publishEvent(OrderPlaced)
    O->>DB: Commit transaction
    O-->>H: HTTP response
    O-->>F: Dispatch sau commit, async
    F->>B: Gọi API thật
    B-->>F: Phản hồi
    F->>DB: Commit side effect
    F->>R: Completion khi listener thành công
~~~

Đây là sơ đồ **khái niệm** cho trường hợp dùng transactional application module listener và persistent publication registry. Thứ tự thao tác nội bộ giữa event infrastructure/registry còn phụ thuộc implementation và transaction phase; không nên dùng hình làm cam kết tuyệt đối về SQL hay lịch thread.

### Mẫu sự kiện và listener

~~~java
// Public API trong module orders
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID eventId, UUID orderId) {
}
~~~

~~~java
// Module fulfillment
package com.example.shop.fulfillment;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;

@Component
public class OrderPlacedListener {

    private final FulfillmentService service;

    public OrderPlacedListener(FulfillmentService service) {
        this.service = service;
    }

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        service.handle(event.orderId(), event.eventId());
    }
}
~~~

`FulfillmentService` là service nghiệp vụ của ứng dụng cần được triển khai. Với các phiên bản Spring Modulith phù hợp, `@ApplicationModuleListener` mang semantics xử lý bất đồng bộ, sau commit và transaction riêng. Vì vậy request HTTP có thể trả về trước khi listener hoàn tất.

Để trace được một event qua các lần retry, event cần có **eventId** ổn định; khi phát lại cùng publication, giữ ID gốc. `eventId` có thể đưa vào structured log hoặc span attribute được kiểm soát, nhưng **không đưa vào metric tags** vì cardinality quá lớn.

### Event publication registry chứng minh điều gì?

Khi dùng persistent registry, hệ thống có thể ghi nhận publication hướng đến listener và đánh dấu hoàn tất theo kết quả xử lý. Các bản ghi chưa hoàn tất phục vụ chẩn đoán và quy trình khôi phục phù hợp với phiên bản/cấu hình.

| Bằng chứng | Kết luận có thể rút ra | Chưa đủ để kết luận |
| --- | --- | --- |
| HTTP 200/201 | Controller đã phản hồi thành công | Listener đã hoàn thành |
| Log `published` | Đã gọi publishEvent | Transaction đã commit |
| Record order tồn tại | Trạng thái order đã được lưu bền | Tác dụng phụ ở fulfillment thành công |
| Log listener-start | Listener bắt đầu lần thử xử lý | Transaction fulfillment đã commit |
| Span consume kết thúc | Đoạn mã được instrument đã hoàn tất | Publication registry đã ghi completed |
| Publication completed | Registry xác nhận theo semantics của nó | Không từng có duplicate side effect |
| Fulfillment record duy nhất | Side effect đạt hậu điều kiện | Mọi trace/log đều được xuất đầy đủ |

Nếu tiến trình chết sau khi side effect đã commit nhưng trước khi registry ghi completion, retry có thể xử lý lại cùng event. Cần **idempotency** theo eventId/orderId và unique constraint, không mặc định có exactly-once.

## 8. Tracing thật: từ ứng dụng tới Jaeger hoặc Tempo

Cấu hình exporter chỉ là bước đầu. Một trace phải đi qua:

1. Spring Boot hoặc custom Observation tạo span.
2. Micrometer Tracing bridge chuyển dữ liệu sang OpenTelemetry.
3. OTLP exporter gửi tới Collector staging.
4. Collector chuyển tiếp theo pipeline đã cấu hình.
5. Backend trace thực sự nhận và truy vấn được span.

Nếu chỉ có log “application started” hoặc endpoint `/actuator/health` báo UP, **chưa chứng minh** bước 3–5 thành công.

### Bổ sung Observation có chủ đích

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class EventObservationSupport {
    private final ObservationRegistry registry;

    public EventObservationSupport(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void observePublish(Runnable callback) {
        Observation.createNotStarted("business.event.publish", registry)
            .lowCardinalityKeyValue("module", "orders")
            .lowCardinalityKeyValue("event.type", "OrderPlaced")
            .observe(callback);
    }

    public void observeConsume(Runnable callback) {
        Observation.createNotStarted("business.event.consume", registry)
            .lowCardinalityKeyValue("module", "fulfillment")
            .lowCardinalityKeyValue("event.type", "OrderPlaced")
            .observe(callback);
    }
}
~~~

Gọi `observePublish(() -> publisher.publishEvent(event))` trong orders và `observeConsume(() -> service.handle(...))` trong listener theo luồng thực tế. Observation publication đo thời gian của lời gọi publish, **không đo toàn bộ thời gian tới khi listener xong**. Tên custom span có thể trùng phạm vi instrumentation tự động; kiểm tra trace để tránh tạo span dư thừa.

### Context propagation qua executor

Async listener chạy trên thread khác, nên trace parent và MDC có thể không còn trong thread worker. Với Spring Framework hỗ trợ `ContextPropagatingTaskDecorator` (dòng 6.1 trở lên), có thể cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncEventConfiguration {

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Nếu ứng dụng có nhiều executor, cần xác minh `@ApplicationModuleListener` thật sự chạy trên executor đã gắn decorator. Decorator **chỉ chụp active context khi task được submit**; nếu publication span đã kết thúc và không có parent context phù hợp sau commit, listener vẫn có thể bắt đầu trace mới. Liên kết eventId xuyên trace vẫn cần thiết.

Không lan truyền transaction thread-local hoặc quyền bảo mật từ request thread sang listener một cách tùy tiện. Listener có transaction riêng và phải xác thực/ủy quyền theo yêu cầu nghiệp vụ.

## 9. Metrics và Actuator trên staging

Bật Actuator không có nghĩa tất cả metric cần thiết tự xuất hiện. Cần xác nhận meter được đăng ký, có traffic và registry exporter thực sự nhận dữ liệu.

| Loại metric | Giá trị sử dụng |
| --- | --- |
| HTTP request count/duration | Đánh giá API latency và lỗi |
| Event publish attempts | Tần suất ứng dụng gọi publish |
| Listener attempts, success/failure | Đo tỷ lệ thất bại và số lần retry |
| Listener duration | Tìm xử lý chậm trong module |
| Outstanding event publications | Phát hiện backlog registry |
| Executor active threads, queue depth | Chẩn đoán listener trễ |
| Hikari connection pool | Phát hiện thiếu connection |
| Outbound HTTP latency/error | Chẩn đoán backend staging chậm |

Nếu chưa có metric tự động cho listener, có thể thêm counter/timer qua Micrometer. Dùng các tag số lượng hữu hạn như `module`, `event.type`, `outcome`; không dùng `eventId`, `orderId`, `traceId` làm label.

Lệnh kiểm tra mẫu (thay URL thật của hệ thống):

~~~bash
curl -i "https://shop.staging.example.test/actuator/health"
curl -i "https://shop.staging.example.test/actuator/health/readiness"
curl -i "https://shop.staging.example.test/actuator/metrics"
curl -i "https://shop.staging.example.test/actuator/prometheus"
~~~

Các endpoint chỉ trả dữ liệu nếu được expose, có dependency tương ứng và client có quyền truy cập. Endpoint readiness chỉ có nếu probe/health group được bật. `/actuator/prometheus` cần Prometheus registry; metric mới có thể chỉ được tạo sau request đầu tiên.

Health `UP` không tự khẳng định collector và external API hoạt động nếu chưa có indicator riêng. Đừng phụ thuộc readiness vào mọi dịch vụ không thiết yếu một cách máy móc; theo policy của hệ thống.

## 10. Module graph và trace runtime kiểm tra hai thứ khác nhau

Sinh module graph và kiểm tra các phụ thuộc giữa application module trong CI:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModulithArchitectureTests {

    @Test
    void verifyModules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }

    @Test
    void generateDocs() {
        var modules = ApplicationModules.of(ShopApplication.class);
        new Documenter(modules).writeDocumentation();
    }
}
~~~

`ShopApplication` là entrypoint giả định; cần đổi theo dự án và khai báo dependency docs/test phù hợp. Chạy những kiểm thử này trên **cùng source commit** với artifact deploy staging.

- **Module graph** mô tả quan hệ và các interface được công bố ở mức cấu trúc.
- **Trace** phản ánh một execution path thật, có timestamp và thời lượng.
- **Log/eventId** liên kết nhiều lần xử lý và nhiều trace.
- **Registry/database** cho biết hậu điều kiện đã được lưu và publication nào chưa hoàn tất.
- **Metrics** mô tả xu hướng của cả môi trường.

Không dùng trace thay kiểm thử kiến trúc vì không có request nào bao phủ toàn bộ dependency. Không dùng graph để khẳng định listener vừa chạy thành công vì graph không có trạng thái runtime.

## 11. Smoke test end-to-end với backend staging

Một smoke test staging phải gọi **bản deploy thật** qua mạng và xem bằng chứng bên ngoài tiến trình. Các API bên dưới là minh họa; cần thay bằng route và request schema của ứng dụng.

### 11.1. Kiểm tra trước khi ghi dữ liệu

1. Xác nhận URL API trỏ staging, không có hostname production.
2. Kiểm tra active profile/biến môi trường không chứa secret (log hoặc cơ chế deployment được kiểm soát).
3. Xác nhận migration và schema database đã sẵn sàng.
4. Xác nhận quyền kết nối backend staging, OTLP Collector và nơi nhận metric.
5. Chạy health/readiness và kiểm tra không có lỗi khởi động đáng chú ý.

### 11.2. Gửi một request tạo dữ liệu thử nghiệm

~~~bash
curl -i -X POST "https://shop.staging.example.test/api/orders" \
  -H "Content-Type: application/json" \
  -H "X-Test-Run: stg-smoke-001" \
  --data '{"clientReference":"STG-SMOKE-001","items":[{"sku":"TEST-1","quantity":1}]}'
~~~

Sau request, kiểm tra theo thứ tự:

1. Response đúng hợp đồng và có mã order/correlation.
2. Database staging có đơn được commit.
3. Log/module orders có `OrderPlaced`, cùng orderId/eventId.
4. Listener fulfillment thực sự chạy và tạo một side effect đã commit.
5. Publication được đánh dấu completed nếu đang dùng registry.
6. Backend tracing thấy request/span orders và có thể tìm span listener bằng cùng traceId hoặc eventId.
7. Dashboard Prometheus/Actuator phản ánh request và event attempts.

**Không chỉ xét HTTP 200:** listener sau commit chạy độc lập; test phải poll hậu điều kiện với timeout hữu hạn và báo lỗi nếu quá hạn.

### 11.3. Ca thất bại có kiểm soát

Dùng test fixture kích hoạt lỗi ở backend fulfillment **staging** (ví dụ một SKU được dành riêng cho việc giả lập downstream failure):

1. Gửi request hợp lệ để orders commit và phát event.
2. Xác nhận listener bắt đầu và báo lỗi đúng phạm vi.
3. Kiểm tra log/trace/metric failure và publication outstanding.
4. Sửa điều kiện lỗi, thực hiện retry/resubmit theo đúng cơ chế đã cấu hình.
5. Kiểm tra side effect cuối cùng chỉ có một bản ghi hợp lệ nhờ idempotency.
6. Xác nhận registry đánh dấu completed theo implementation đang dùng.

Không kích hoạt failure injection vào production. Khi chưa có cơ chế idempotency, không retry nhiều lần vì có thể nhân đôi tác dụng phụ.

### 11.4. Ma trận test tối thiểu

| Test | Cách xác minh | Kỳ vọng |
| --- | --- | --- |
| Active profile | Kiểm tra deployment và log khởi động | Đúng `staging` |
| Database | Tạo/đọc order thử nghiệm | PostgreSQL staging thực sự ghi dữ liệu |
| External API | Theo dõi request tại backend đích | Gọi đúng dịch vụ staging |
| OTLP traces | Tìm trace ở Jaeger/Tempo staging | Span có service và timestamp đúng |
| Metrics | Tạo traffic rồi query meter | Có giá trị/series hợp lệ |
| Async listener | Chờ hậu điều kiện đã commit | Side effect thành công |
| Failure | Cho listener ném lỗi | Có dấu vết thất bại, không báo completed giả |
| Recovery | Retry có kiểm soát | Không tạo duplicate |
| Module boundary | Chạy `ApplicationModules.verify()` | Không có phụ thuộc vi phạm |
| Access control | Gọi Actuator từ nơi không được phép | Bị từ chối theo policy |

## 12. Gợi ý pipeline CI/CD

~~~mermaid
flowchart TD
    A[Commit] --> B[Build + unit tests]
    B --> C[ApplicationModules.verify + docs]
    C --> D[Integration tests/Testcontainers]
    D --> E[Đóng gói image với digest]
    E --> F[Deploy lên staging]
    F --> G[Inject profile + secrets]
    G --> H[Readiness + migration]
    H --> I[Smoke test API/events]
    I --> J[Đối chiếu traces/metrics/registry]
    J --> K{Đạt tiêu chí?}
    K -- Có --> L[Cho phép bước phát hành tiếp]
    K -- Không --> M[Chặn phát hành và điều tra]
~~~

Không dùng staging profile cho toàn bộ unit test: nếu unit test vô tình kết nối database dùng chung hoặc external HTTP service, nó sẽ trở nên chậm, không tái lập và có thể tạo dữ liệu rác. Unit/integration tests sử dụng mock có chọn lọc hoặc Testcontainers; **smoke test sau deploy** dùng backend staging thật.

Lưu bằng chứng cho mỗi lần kiểm thử: commit/image digest, thời điểm, phiên bản database schema, test run ID, eventId, traceId (nếu có), hậu điều kiện và trạng thái publication. Các thông tin này giúp đối chiếu khi cùng artifact được chuyển sang môi trường khác.

## 13. Chẩn đoán các lỗi staging thường gặp

| Triệu chứng | Khả năng xảy ra | Bước điều tra |
| --- | --- | --- |
| Startup thành công nhưng gọi mock | Sai profile/URL hoặc mock bean còn hoạt động | Xem active profiles, cấu hình hiệu lực và log outbound |
| Health UP nhưng không có traces | Thiếu bridge/exporter, sampling, endpoint sai, collector pipeline lỗi | Xem exporter log, collector receive/export và backend |
| Có trace publisher, không có listener | Listener chưa chạy, mất context, không có instrumentation hoặc sampling | Tìm eventId trong log/registry trước |
| Listener có log xong nhưng DB chưa cập nhật | Transaction rollback hoặc ghi DB khác | Kiểm tra datasource và commit |
| Publication còn outstanding | Lỗi listener, restart giữa chừng, migration/serialization lỗi | Registry, exception và quy trình resubmit |
| Listener chạy lặp | Retry hoặc resubmission | Idempotency/unique constraint và số attempts |
| /actuator/prometheus trả 404 | Thiếu Prometheus registry hoặc chưa expose | Dependency, endpoint discovery và security |
| Collector có span nhưng Jaeger không thấy | Pipeline/exporter backend, quyền truy cập hoặc filter/sampling | Collector logs và query theo thời gian/service |
| Metrics quá nhiều series | Tag orderId/eventId/traceId | Thiết kế lại tag cardinality thấp |
| Staging đụng tài nguyên prod | Secret/hostname/namespace lẫn môi trường | Network isolation, service account và secret mapping |

### Quy trình điều tra một đơn hàng chưa được fulfillment

Đầu tiên lấy `orderId` và `eventId` từ log orders. Xác nhận transaction tạo order đã commit, kiểm tra publication ở registry, tìm mọi lượt listener theo eventId, mở trace tương ứng, rồi xác minh database fulfillment và request tại external API staging. Nếu trace bị tách giữa hai thread, tiếp tục nối bằng eventId; khác traceId không tự chứng minh event thất lạc. Chỉ resubmit sau khi đã xác định side effect có thể đang tồn tại.

## 14. Vận hành và bảo mật staging

- **Tách biệt tài nguyên:** staging dùng database, credential, network policy, OTLP tenant và log retention riêng. Không dùng dữ liệu khách hàng thật trừ khi đã có quy trình ẩn danh và cho phép cụ thể.
- **Không đưa secrets vào source:** password, API key và certificate private key lấy từ secret manager; tránh log cấu hình nhạy cảm khi debug.
- **Bảo vệ Actuator:** health có thể được mở theo policy; metrics/Prometheus/module endpoint cần private network hoặc auth phù hợp.
- **Kiểm soát trace costs:** 100% sampling thích hợp cho bài lab nhỏ; production và staging tải lớn cần sampling/retention hợp lý.
- **Đặt timeout và backpressure:** giới hạn executor queue, connection pool, retry và HTTP timeouts; kiểm tra dấu hiệu nghẽn khi listener tăng.
- **Chấp nhận at-least-once:** persistent publication và retry không thay thế idempotency; theo dõi outstanding backlog theo thời gian.
- **Đối soát cấu hình:** cùng artifact nhưng môi trường khác giá trị; liệt kê các khác biệt có chủ đích, không để URL production lọt vào staging.
- **Dọn dữ liệu test:** mỗi lần chạy tạo test ID riêng; chỉ dọn sau khi listener và các bên tích hợp đã xử lý xong.

## 15. Bài tập và tiêu chí hoàn thành

**Bài tập A — kết nối backend thật.** Cấu hình application-staging.yml với PostgreSQL, OTLP Collector và external API staging. Deploy artifact đã build và dùng một smoke test đọc phản hồi lẫn kết quả database. Tắt một thành phần có kiểm soát để xem health, log và error phản ánh ra sao.

**Bài tập B — trace module interaction.** Dùng Spring Modulith tạo hai module orders/fulfillment và event OrderPlaced. Lấy eventId từ log, tìm trace của request và listener; xác minh trạng thái registry và hậu điều kiện. Thử thay đổi cấu hình executor để hiểu context propagation.

**Bài tập C — failure và retry.** Gây lỗi listener một lần, quan sát outstanding publication và điều tra bằng trace/metric. Sau đó cho xử lý lại rồi xác minh unique constraint/idempotency ngăn side effect trùng.

**Bài tập D — tài liệu kiến trúc.** Chạy ApplicationModules.verify() và sinh module graph từ đúng source commit đang deploy; so sánh graph với các span tương tác module thực tế. Giải thích vì sao cả hai nguồn chứng cứ đều cần thiết.

### Checklist nghiệm thu

- [ ] Staging chạy đúng profile, không có URL hoặc secret production.
- [ ] Database, external API và telemetry backend thuộc staging và được xác minh qua thao tác thật.
- [ ] Có trace, metric và log của một request thử nghiệm; hiểu giới hạn của async context propagation.
- [ ] Event có ID đối chiếu; phân biệt mốc publish, commit, listener start và completion.
- [ ] Side effect sau listener được xác minh đã commit; registry phản ánh completion/outstanding phù hợp.
- [ ] Failure/retry không làm nhân đôi tác dụng phụ nghiệp vụ.
- [ ] Module graph/verification khớp commit của artifact deployed.
- [ ] Actuator và telemetry được bảo vệ; dữ liệu thử có thể cleanup và báo cáo có traceId/eventId để điều tra.

**Kết quả mong đợi:** profile staging trở thành một phép thử tích hợp và quan sát đáng tin cậy của Spring Modulith trên backend thật, giúp phát hiện sai lệch cấu hình, mất dấu sự kiện, lỗi dữ liệu và vi phạm ranh giới module trước khi phát hành production.
