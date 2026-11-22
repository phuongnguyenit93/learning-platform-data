# Observation và số liệu phía máy chủ, phía WebClient

Trong Spring WebFlux, **Observation** là lớp ghi nhận một hoạt động trong ứng dụng theo một vòng đời thống nhất. Từ một Observation, Micrometer có thể tạo metric, trace hoặc dữ liệu quan sát khác tùy các handler được đăng ký. Spring Boot Actuator tích hợp cơ chế này để tự động đo request HTTP ở phía server và các request đi ra qua WebClient.

Hai metric quan trọng nhất:

- `http.server.requests`: thời gian và kết quả xử lý HTTP request tại ứng dụng WebFlux.
- `http.client.requests`: thời gian và kết quả trao đổi HTTP của WebClient với dịch vụ đích.

Trong Spring Boot, Actuator tự cấu hình Observation cho WebFlux controller và functional endpoint. Với WebClient, cần sử dụng `WebClient.Builder` do Spring Boot cung cấp để registry quan sát được gắn tự động. Nếu tự tạo client bằng `WebClient.create()` hoặc builder độc lập, cần cấu hình `ObservationRegistry` rõ ràng.

Bài này đi từ ObservationRegistry, MeterRegistry, convention và cardinality đến metric server/client, cấu hình Prometheus, custom tag an toàn và một ví dụ Java 17 có integration test kiểm tra cả hai metric.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Observation, Metric, Trace và Log.
2. Giải thích vai trò của `ObservationRegistry`, `ObservationContext` và `ObservationHandler`.
3. Hiểu `ObservationConvention`, `ObservationFilter` và `ObservationPredicate`.
4. Phân biệt low-cardinality và high-cardinality key values.
5. Biết Spring Boot Actuator tạo `http.server.requests` cho Spring WebFlux.
6. Biết `http.client.requests` được tạo cho WebClient như thế nào.
7. Dùng WebClient builder do Boot auto-configure để giữ instrumentation.
8. Cấu hình thủ công ObservationRegistry cho WebClient tự tạo.
9. Thêm tag server bằng `DefaultServerRequestObservationConvention`.
10. Đọc metric qua Actuator metrics endpoint và Prometheus.
11. Cấu hình histogram, SLO buckets và percentile đúng mục đích.
12. Hiểu khi nào exception được ghi nhận là lỗi của observation.
13. Tránh metric cardinality explosion và rò dữ liệu cá nhân.
14. Viết ứng dụng Java 17 và kiểm thử metric server/client bằng WebClient.

## 2. Observability: Observation, Metric, Trace và Log

Các khái niệm này liên quan nhưng không giống nhau.

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Log | Điều gì đã xảy ra, với ngữ cảnh nào? | Request bị từ chối vì thiếu quyền |
| Metric | Xu hướng và số lượng thay đổi thế nào? | p95 latency, request rate, error rate |
| Trace | Một request đi qua những service nào? | API → WebClient → inventory service |
| Observation | Một hoạt động được ghi nhận theo lifecycle nào? | HTTP server request, HTTP client exchange |

**Observation là điểm tích hợp**, không phải một backend lưu trữ. Một Observation được tạo, bắt đầu, có thể nhận event/error, rồi dừng. Các ObservationHandler tiêu thụ lifecycle đó để tạo metric, trace hoặc output khác.

Ví dụ một HTTP request:

~~~text
HTTP request arrives
       |
       v
Observation starts
       |
       +--> collect method, route, status context
       |
       +--> controller and downstream WebClient calls
       |
       v
Observation stops
       |
       +--> Meter handler records timer/counter
       |
       +--> Tracing handler finishes span (if configured)
~~~

Nếu chỉ có Micrometer metrics registry, Observation có thể tạo metric mà không tạo distributed trace. Muốn trace phân tán, cần thêm Micrometer Tracing bridge và exporter phù hợp.

## 3. Các thành phần Micrometer Observation

### 3.1. ObservationRegistry

`ObservationRegistry` là điểm đăng ký và điều phối các Observation. Các instrumented component như Spring WebFlux và WebClient nhận registry để gửi sự kiện vòng đời.

Trong Spring Boot có Actuator, registry được auto-configure và tích hợp với các handler. Nếu component không được gắn registry phù hợp, observation có thể trở thành no-op và không ghi số liệu.

### 3.2. ObservationContext

`ObservationContext` giữ dữ liệu liên quan đến một operation: request, response, exception, key values và các thuộc tính mà instrumentation cần. HTTP server có context riêng chứa thông tin request/response; WebClient có context cho client exchange.

Context cho phép convention và handler cùng đọc thông tin mà không phải truyền từng trường qua nhiều lớp code.

### 3.3. ObservationConvention

`ObservationConvention` quyết định tên observation và các key values cần thu thập. Ví dụ HTTP server convention có thể thêm method, URI template, status và outcome.

Spring cung cấp convention mặc định. Ứng dụng có thể mở rộng default convention để bổ sung tag ổn định, hoặc triển khai convention riêng nếu cần thay đổi toàn bộ hợp đồng.

### 3.4. ObservationHandler

`ObservationHandler` nhận callback theo lifecycle như start, error, event và stop. Một handler có thể chuyển dữ liệu sang MeterRegistry, tracing system hoặc hệ thống riêng.

Spring Boot tự đăng ký meter observation handler khi Actuator và registry phù hợp có mặt. Vì vậy ứng dụng thông thường không cần tự viết handler chỉ để có HTTP metrics.

### 3.5. ObservationFilter và ObservationPredicate

- `ObservationFilter` chỉnh sửa context sau khi convention đóng góp key values, trước khi handler xử lý kết quả.
- `ObservationPredicate` quyết định có tạo observation hay không; nếu không, operation có thể trở thành no-op.

Hai extension point này hữu ích cho policy toàn ứng dụng, nhưng không nên dùng để xóa tùy tiện các trường cần cho debugging hoặc SLO.

### 3.6. ObservationRegistry khác MeterRegistry

| API | Vai trò |
| --- | --- |
| `ObservationRegistry` | Quản lý vòng đời Observation và các handler |
| `MeterRegistry` | Lưu/đăng ký Counter, Timer, Gauge, DistributionSummary |
| `ObservationConvention` | Đặt tên và cung cấp key values |
| `ObservationHandler` | Nhận lifecycle và tạo output |
| `MeterFilter` | Lọc/điều chỉnh meter khi đăng ký |

Không truyền nhầm MeterRegistry vào API cần ObservationRegistry. Spring Boot kết nối hai registry thông qua các handler đã cấu hình.

## 4. Low cardinality và high cardinality

Cardinality là số lượng giá trị khác nhau mà một tag/key có thể nhận.

**Low-cardinality** có số giá trị hữu hạn, được giới hạn tương đối nhỏ. Ví dụ:

- HTTP method: GET, POST, PUT, DELETE.
- Outcome: SUCCESS, CLIENT_ERROR, SERVER_ERROR.
- Status: 200, 400, 404, 500.
- URI template: `/api/items/{id}`.

**High-cardinality** có thể sinh ra rất nhiều giá trị khác nhau. Ví dụ:

- URL thực tế `/api/items/8f3a...`.
- User ID, order ID, email, session ID.
- Trace ID hoặc request ID.
- Giá trị query string chứa dữ liệu người dùng.

Micrometer sử dụng low-cardinality values cho metric tags; high-cardinality values có thể được giữ trong trace context nhưng không nên đưa vào meter tags vì gây nổ số lượng time series.

Ví dụ tốt:

~~~text
http.server.requests{
  method="GET",
  uri="/api/items/{id}",
  status="200",
  outcome="SUCCESS"
}
~~~

Ví dụ xấu:

~~~text
http.server.requests{
  uri="/api/items/8f3a4e2b-...",
  userId="user-928374",
  traceId="7b1d..."
}
~~~

Nếu mỗi user hoặc mỗi request tạo một time series, Prometheus và backend metrics có thể tiêu thụ lượng memory/index rất lớn.

**Nguyên tắc:** metric tags mô tả nhóm có giới hạn; trace attributes phù hợp hơn với định danh riêng của một request khi chính sách dữ liệu cho phép.

## 5. Observation và metric phía WebFlux server

Khi dùng Spring Boot Actuator, auto-configuration bật instrumentation cho request được xử lý bởi Spring WebFlux controller và functional endpoint. Metric mặc định:

~~~text
http.server.requests
~~~

Metric này đo thời gian xử lý HTTP exchange và gắn các tag mô tả kết quả.

### 5.1. Tag mặc định

Các low-cardinality tag thường gặp:

| Tag | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `method` | HTTP method | GET |
| `uri` | URI template của handler | /api/items/{id} |
| `status` | HTTP status | 200 |
| `outcome` | Nhóm kết quả | SUCCESS |
| `exception`/`error` | Loại lỗi nếu được ghi nhận | none hoặc tên exception |

Tên tag lỗi cụ thể có thể khác theo phiên bản Spring/Micrometer convention. Hãy kiểm tra meter thực tế trong ứng dụng thay vì hard-code giả định giữa các major version.

High-cardinality metadata có thể gồm HTTP URL đầy đủ; không đưa giá trị đó thành tag metric không giới hạn.

### 5.2. URI template quan trọng thế nào?

Với mapping:

~~~java
@GetMapping("/api/items/{id}")
Mono<ItemView> get(@PathVariable String id) {
    return service.find(id);
}
~~~

Tag `uri` nên là:

~~~text
/api/items/{id}
~~~

không phải:

~~~text
/api/items/10001
/api/items/10002
/api/items/10003
~~~

Spring dùng URI template của handler nếu có thể xác định. Đây là lý do nên khai báo mapping bằng template rõ ràng thay vì tự tạo hàng nghìn route động.

### 5.3. Observation cho controller và functional endpoint

WebFlux instrumentation bao gồm cả annotated controller và functional handler. Vì vậy một request xử lý bằng `@GetMapping` hoặc `RouterFunction` vẫn có thể được ghi nhận nếu server ObservationRegistry được cấu hình.

Nếu dùng Spring Framework thuần không có Boot, cần gắn ObservationRegistry vào `WebHttpHandlerBuilder` khi xây dựng HttpHandler. Spring Boot Actuator thường thực hiện phần cấu hình này tự động.

### 5.4. Exception được xử lý bên trong controller

Observation server thường ghi nhận exception khi lỗi đi ra khỏi quá trình xử lý tới instrumentation. Nếu controller hoặc `@ExceptionHandler` bắt lỗi và chuyển thành response bình thường, exception đó có thể không tự động xuất hiện trong tag lỗi của request metric.

Nếu muốn một lỗi đã xử lý vẫn được ghi nhận, ứng dụng cần chủ động đặt error vào observation context/request attribute theo API và phiên bản đang dùng. Không giả định mọi response 4xx/5xx đều có tag exception giống nhau.

## 6. Observation và metric phía WebClient

Spring Boot Actuator quản lý instrumentation cho WebClient. Metric mặc định:

~~~text
http.client.requests
~~~

Observation đo toàn bộ HTTP client exchange, từ lúc thiết lập kết nối đến khi response body được deserialize theo contract của client.

### 6.1. Tag mặc định

| Tag | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `method` | HTTP method | GET |
| `uri` | URI template được dùng khi gọi client | /inventory/{id} |
| `client.name` | Host đích | inventory.internal |
| `status` | HTTP response status hoặc trạng thái lỗi | 200 |
| `outcome` | Nhóm kết quả | SUCCESS |
| `error` | Loại lỗi nếu exchange thất bại | none hoặc exception type |

High-cardinality HTTP URL có thể được lưu trong trace context, nhưng không nên đưa vào metric tags.

### 6.2. Dùng WebClient.Builder do Spring Boot cung cấp

Cách khuyến nghị:

~~~java
@Service
class InventoryClient {

    private final WebClient webClient;

    InventoryClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://inventory.internal")
            .build();
    }

    Mono<ItemView> find(String id) {
        return webClient.get()
            .uri("/inventory/{id}", id)
            .retrieve()
            .bodyToMono(ItemView.class);
    }
}
~~~

Builder do Boot auto-configure được áp dụng ObservationRegistry và customizer liên quan. Request tạo qua client này có thể sinh `http.client.requests`.

### 6.3. Tự tạo WebClient có thể mất instrumentation

Cách dễ bỏ sót registry:

~~~java
WebClient client = WebClient.create("https://inventory.internal");
~~~

WebClient độc lập không tự động thừa hưởng mọi customizer của Boot. Nếu tự tạo builder, gắn registry:

~~~java
WebClient client = WebClient.builder()
    .observationRegistry(observationRegistry)
    .baseUrl("https://inventory.internal")
    .build();
~~~

Có thể gắn thêm convention riêng qua API builder nếu cần. Điều quan trọng là client thực sự được cấu hình với ObservationRegistry đang dùng trong ứng dụng.

### 6.4. Không đo nhầm thời điểm hoàn tất

Observation client bao trùm exchange; với reactive body, thời điểm kết thúc gắn với quá trình nhận/đọc body theo semantics của client. Không chỉ đo thời gian tạo WebClient request builder rồi kết luận đó là HTTP latency.

Nếu code bỏ qua hoặc không consume response body theo cách đúng, lifecycle và connection reuse có thể bị ảnh hưởng. Dùng `retrieve().bodyToMono` hoặc exchange API với cleanup rõ ràng.

## 7. Cấu hình Spring Boot Actuator và Prometheus

Thêm các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Actuator cung cấp Observation/Micrometer integration và các endpoint chẩn đoán. Prometheus registry cung cấp định dạng scrape tại endpoint Prometheus.

### 7.1. application.properties

~~~properties
spring.application.name=webflux-observation-demo

management.endpoints.web.exposure.include=health,info,metrics,prometheus

management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.percentiles-histogram.http.client.requests=true

management.metrics.distribution.slo.http.server.requests=100ms,250ms,500ms,1s
management.metrics.distribution.slo.http.client.requests=100ms,250ms,500ms,1s
~~~

Ý nghĩa:

- Expose health/info/metrics/prometheus cho môi trường demo.
- Bật histogram phù hợp để backend tính percentile có thể tổng hợp.
- Định nghĩa bucket SLO cho hai loại HTTP request.

Trong production, chỉ expose endpoint cần thiết và bảo vệ Actuator bằng network policy hoặc authentication. Không public metrics/Prometheus endpoint cho Internet nếu không có kiểm soát.

### 7.2. Metrics endpoint để chẩn đoán

Liệt kê metric:

~~~http
GET /actuator/metrics
~~~

Xem metric server:

~~~http
GET /actuator/metrics/http.server.requests
~~~

Xem metric client:

~~~http
GET /actuator/metrics/http.client.requests
~~~

Lọc theo tag, ví dụ:

~~~http
GET /actuator/metrics/http.server.requests?tag=method:GET
~~~

Metrics endpoint phù hợp để chẩn đoán một ứng dụng đang chạy và xem meter/tag hiện có. Không nên dùng nó làm backend scrape chính trong production.

### 7.3. Prometheus scrape endpoint

Prometheus đọc:

~~~http
GET /actuator/prometheus
~~~

Ví dụ scrape configuration:

~~~yaml
scrape_configs:
  - job_name: "webflux-app"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["localhost:8080"]
~~~

Prometheus scrape định kỳ, lưu time series và cho phép query/rule/alert. Nếu dùng Kubernetes/service discovery, thay static target bằng discovery phù hợp.

### 7.4. Histogram, SLO và percentile

Histogram cung cấp bucket counts có thể tổng hợp giữa nhiều instance. SLO buckets giúp theo dõi tỷ lệ request nằm trong ngưỡng thời gian đã định.

Percentile tính tại từng process không nhất thiết có thể cộng/tổng hợp chính xác qua nhiều instance. Nếu cần p95/p99 trên toàn cụm, thường dùng histogram buckets và query backend có khả năng tổng hợp.

Không bật histogram cho mọi metric một cách vô điều kiện. Histogram làm tăng số time series; chỉ bật cho những metric có nhu cầu latency/SLO rõ.

## 8. Tùy biến tag server bằng ObservationConvention

Spring Boot cho phép cung cấp bean kế thừa `DefaultServerRequestObservationConvention` để bổ sung low-cardinality tags.

Ví dụ thêm tag cố định `service.area=catalog`:

~~~java
package demo;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.reactive.observation.DefaultServerRequestObservationConvention;
import org.springframework.http.server.reactive.observation.ServerRequestObservationContext;
import org.springframework.http.server.reactive.observation.ServerRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
class ObservationConfiguration {

    @Bean
    ServerRequestObservationConvention serverRequestConvention() {
        return new DefaultServerRequestObservationConvention() {
            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ServerRequestObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("service.area", "catalog"));
            }
        };
    }
}
~~~

Convention giữ nguyên tag mặc định và bổ sung một tag có số giá trị nhỏ. Spring Boot dùng convention bean này cho WebFlux server observations.

### 8.1. Khi nào implement convention riêng?

- **Mở rộng default:** khi chỉ cần thêm vài tag ổn định.
- **Implement toàn bộ interface:** khi cần thay đổi tên observation hoặc toàn bộ key values.
- **ObservationFilter:** khi cần chỉnh sửa context sau khi convention đã tạo tags.
- **ObservationPredicate:** khi cần bỏ qua một số observation có chủ đích.

Mở rộng default thường dễ bảo trì hơn vì giữ được các tag mặc định của framework.

### 8.2. Tránh custom tag có cardinality cao

Không thêm các giá trị như user ID, order ID, email hoặc trace ID vào low-cardinality metric tags. Những giá trị này có thể khác nhau ở mọi request, tạo hàng triệu time series. Nếu thực sự cần, cân nhắc trace attribute có kiểm soát và chính sách bảo vệ dữ liệu.

### 8.3. Tùy biến WebClient observation

WebClient dùng `ClientRequestObservationConvention` thuộc package:

~~~text
org.springframework.web.reactive.function.client
~~~

Có thể cung cấp convention bean để thay đổi các tag client. Giữ lại method, URI template, host, status và outcome cần thiết; không đưa full URL hoặc ID động vào low-cardinality tags.

Nếu chỉ cần registry, không cần custom convention. Boot-managed `WebClient.Builder` đã có instrumentation mặc định.

## 9. Ghi Observation cho nghiệp vụ riêng

Không chỉ HTTP exchange mới có thể được quan sát. Một thao tác nghiệp vụ như lookup cache hoặc xử lý đơn hàng cũng có thể tạo Observation riêng.

Ví dụ với một thao tác đồng bộ:

~~~java
ItemView loadFromLegacyCache(
        String id,
        ObservationRegistry observationRegistry) {

    return Observation.createNotStarted(
            "catalog.cache.lookup",
            observationRegistry
        )
        .lowCardinalityKeyValue("cache", "product")
        .observe(() -> legacyCache.get(id));
}
~~~

Ví dụ giả định `legacyCache.get(id)` là API đồng bộ và trả ItemView. Observation đo đúng thời gian thực thi lời gọi đồng bộ đó.

**Không áp dụng nguyên xi `observe()` để bao quanh việc tạo một Mono.** Với publisher, supplier thường chỉ trả về object Mono rất nhanh; Observation có thể dừng trước khi pipeline thực thi. Muốn instrument reactive publisher, dùng integration Micrometer/Reactor phù hợp với phiên bản, hoặc quản lý lifecycle theo subscribe/terminate/cancel để observation bao trùm quá trình thực thi.

### 9.1. Tên và tag nghiệp vụ

Tên nên ổn định:

~~~text
catalog.cache.lookup
orders.payment.authorize
inventory.reserve
~~~

Tag nên có tập giá trị giới hạn:

~~~text
cache=product
operation=lookup
result=hit|miss
~~~

Không dùng tên observation riêng cho từng order/user. Hãy giữ tên operation ổn định và dùng tag có cardinality thấp.

## 10. Tracing và context propagation

Observation có thể được xử lý bởi tracing handler nếu ứng dụng cài Micrometer Tracing bridge và exporter tương ứng. Khi đó một HTTP server request có thể tạo server span, WebClient exchange tạo client span và trace context được truyền giữa các service.

Một số nguyên tắc:

- Dùng builder WebClient được Boot cấu hình để giữ observation/tracing customizer.
- Không tự xóa trace headers khi không có lý do.
- Không tự tạo trace ID bằng UUID rồi ghi nó thành metric tag.
- Kiểm tra Reactor context propagation khi chuyển qua scheduler.
- Giữ baggage nhỏ và không chứa secret.
- Sampling quyết định trace nào được giữ; metrics thường vẫn ghi nhận toàn bộ request theo cấu hình.

Metrics trả lời xu hướng tổng thể; trace giúp điều tra một request cụ thể. Không dùng trace như thay thế cho metrics hoặc ngược lại.

## 11. Ví dụ Java 17 hoàn chỉnh: đo cả server và WebClient

Ví dụ dùng **Spring Boot 3.5.16**, Java 17, WebFlux và Actuator. Test tạo một HTTP request bằng WebClient tới chính server đang chạy trên port ngẫu nhiên. Nhờ đó một lần gọi tạo cả:

- `http.client.requests` ở phía WebClient.
- `http.server.requests` ở phía WebFlux server.

Test còn xác minh tag custom `service.area=catalog`.

### 11.1. Cấu trúc dự án

~~~text
webflux-observation-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/ObservabilityApplication.java
    │   ├── java/demo/ItemView.java
    │   ├── java/demo/ItemController.java
    │   ├── java/demo/ObservationConfiguration.java
    │   └── resources/application.properties
    └── test/java/demo/ObservabilityIntegrationTest.java
~~~

### 11.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 11.3. application.properties

~~~properties
spring.application.name=webflux-observation-demo

management.endpoints.web.exposure.include=health,info,metrics,prometheus

management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.percentiles-histogram.http.client.requests=true

management.metrics.distribution.slo.http.server.requests=100ms,250ms,500ms,1s
management.metrics.distribution.slo.http.client.requests=100ms,250ms,500ms,1s
~~~

### 11.4. ObservabilityApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ObservabilityApplication.class, args);
    }
}
~~~

### 11.5. ItemView.java

~~~java
package demo;

public record ItemView(
    String id,
    String status
) {}
~~~

### 11.6. ItemController.java

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class ItemController {

    @GetMapping("/api/items/{id}")
    Mono<ItemView> getItem(@PathVariable String id) {
        return Mono.just(
            new ItemView(id, "available")
        );
    }
}
~~~

### 11.7. ObservationConfiguration.java

~~~java
package demo;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.reactive.observation.DefaultServerRequestObservationConvention;
import org.springframework.http.server.reactive.observation.ServerRequestObservationContext;
import org.springframework.http.server.reactive.observation.ServerRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
class ObservationConfiguration {

    @Bean
    ServerRequestObservationConvention serverRequestConvention() {
        return new DefaultServerRequestObservationConvention() {
            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ServerRequestObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("service.area", "catalog"));
            }
        };
    }
}
~~~

### 11.8. ObservabilityIntegrationTest.java

~~~java
package demo;

import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.function.client.WebClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ObservabilityIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    WebClient.Builder webClientBuilder;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void webClientCallRecordsClientAndServerMetrics() {
        WebClient client = webClientBuilder.clone()
            .baseUrl("http://localhost:" + port)
            .build();

        ItemView item = client.get()
            .uri("/api/items/{id}", "42")
            .retrieve()
            .bodyToMono(ItemView.class)
            .block(Duration.ofSeconds(5));

        assertNotNull(item);
        assertEquals("42", item.id());
        assertEquals("available", item.status());

        Timer clientTimer = meterRegistry
            .find("http.client.requests")
            .timer();

        Timer serverTimer = meterRegistry
            .find("http.server.requests")
            .tag("service.area", "catalog")
            .timer();

        assertNotNull(clientTimer);
        assertNotNull(serverTimer);
        assertTrue(clientTimer.count() >= 1);
        assertTrue(serverTimer.count() >= 1);
    }
}
~~~

**Vì sao test này chứng minh được instrumentation?**

1. Test inject Boot-managed `WebClient.Builder`.
2. Builder tạo client có ObservationRegistry được cấu hình.
3. Client gửi GET tới WebFlux server port ngẫu nhiên.
4. WebClient tạo `http.client.requests`.
5. WebFlux server tạo `http.server.requests`.
6. Custom server convention thêm tag `service.area=catalog`.
7. Test đọc hai Timer từ MeterRegistry và kiểm tra count lớn hơn hoặc bằng 1.

`block(Duration)` chỉ nằm trong JUnit test thread để chờ HTTP result. Không copy cách chờ đồng bộ này vào WebFlux controller/event loop.

### 11.9. Chạy test

Với Gradle wrapper:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Nếu chưa có wrapper nhưng đã cài Gradle tương thích:

~~~bash
gradle test
~~~

Test dùng server port ngẫu nhiên và không cần gọi dịch vụ bên ngoài.

### 11.10. Kiểm tra khi ứng dụng đang chạy

Khởi động:

~~~bash
./gradlew bootRun
~~~

Gọi API:

~~~bash
curl http://localhost:8080/api/items/42
~~~

Response JSON dự kiến:

~~~json
{"id":"42","status":"available"}
~~~

Xem metric server:

~~~bash
curl http://localhost:8080/actuator/metrics/http.server.requests
~~~

Xem metric client sau khi có một WebClient call:

~~~bash
curl http://localhost:8080/actuator/metrics/http.client.requests
~~~

Xem Prometheus exposition:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

Gọi trực tiếp endpoint bằng curl chỉ tạo server metric; nó không tự tạo `http.client.requests` trong cùng ứng dụng vì curl không phải WebClient chạy bên trong process. Muốn có client metric, phải phát sinh request qua một WebClient đã instrument.

## 12. Đọc và diễn giải số liệu

### 12.1. Request rate

Đếm số request trong một khoảng thời gian bằng metric count/rate ở backend. Cần phân biệt request tổng thể và request theo method/status/route.

### 12.2. Latency

Timer ghi count, total time và max; histogram/SLO buckets hỗ trợ phân tích phân phối. Dùng p50/p95/p99 để nhìn tail latency, không chỉ trung bình.

### 12.3. Error rate

Lọc theo status/outcome/error. Phân biệt:

- Server trả 4xx do input/client.
- Server trả 5xx do lỗi ứng dụng.
- Client không nhận response do DNS/connect/TLS/timeout.
- Downstream trả 4xx/5xx.
- Request bị cancel trước khi hoàn tất.

### 12.4. Server và client metric có thể lệch nhau

Một request vào server có thể gọi nhiều WebClient downstream. Vì thế số lượng `http.client.requests` có thể lớn hơn số lượng `http.server.requests`.

Ngược lại, một số request server không gọi downstream. Không nên kỳ vọng hai metric có count bằng nhau.

### 12.5. Thời gian client dài hơn server

Client timer có thể bao gồm DNS/connection setup, network, remote processing và body decoding. Server timer chỉ đo phần xử lý phía server theo instrumentation. Chênh lệch có thể phản ánh network, queue, connection pool, downstream hoặc body transfer.

## 13. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ Observation chính là metric | Không hiểu handler nào tạo output | Observation là lifecycle; handler tạo metric/trace |
| Không thêm Actuator | Không có auto-config metrics như mong đợi | Thêm spring-boot-starter-actuator |
| Dùng WebClient.create() và chờ metric | Client observation có thể no-op | Inject Boot-managed WebClient.Builder |
| Tự tạo WebClient.Builder không gắn registry | Không có http.client.requests | Gọi observationRegistry(registry) |
| Nhầm ObservationRegistry với MeterRegistry | Gắn sai API và thiếu handler | Dùng đúng registry theo trách nhiệm |
| Thêm userId/orderId làm metric tag | Cardinality tăng không kiểm soát | Dùng low-cardinality tag; định danh chi tiết chỉ ở trace khi phù hợp |
| Tag URI bằng giá trị path thực | Mỗi ID tạo time series mới | Dùng URI template |
| Chỉ kiểm tra server metric | Không biết downstream call có được đo không | Kiểm tra cả http.server.requests và http.client.requests |
| Gọi curl rồi tìm client metric | curl không chạy trong process ứng dụng | Dùng WebClient được instrument |
| Không expose Actuator endpoint | Không truy cập được metrics/prometheus | Cấu hình exposure và security phù hợp |
| Public Actuator không bảo vệ | Lộ topology và dữ liệu vận hành | Giới hạn network/authentication |
| Bật histogram mọi metric | Tăng số series và storage | Chỉ bật theo SLO/use case |
| Chỉ nhìn average latency | Bỏ sót tail latency | Xem histogram và p95/p99 |
| Tưởng exception đã handled luôn thành error tag | Error metric thiếu | Xem exception handling và set observation error nếu cần |
| Dùng observe() quanh việc tạo Mono | Observation dừng trước khi publisher chạy | Dùng reactive instrumentation/lifecycle phù hợp |
| Tạo convention thay default toàn bộ không chủ ý | Mất tag mặc định | Extend DefaultServerRequestObservationConvention |
| Ghi full URL/token vào tags | Rò dữ liệu và tăng cardinality | Mask dữ liệu; không tag secret |
| Dùng metrics endpoint làm Prometheus scraper | Backend polling endpoint chẩn đoán không tối ưu | Dùng /actuator/prometheus |

## 14. Checklist triển khai

1. **Dependency:** có spring-boot-starter-actuator?
2. **Server:** WebFlux controllers và functional endpoints tạo http.server.requests?
3. **Client:** WebClient dùng builder auto-configured hoặc registry được gắn thủ công?
4. **ObservationRegistry:** các component dùng đúng registry?
5. **MeterRegistry:** có exporter/backend cần thiết?
6. **Convention:** tag mặc định được giữ lại khi tùy biến?
7. **Cardinality:** tag metric có tập giá trị nhỏ và bounded?
8. **URI:** metric dùng route template, không dùng ID thực?
9. **Errors:** exception handling có làm mất error context cần thiết?
10. **Histogram:** có SLO/percentile cần theo dõi rõ?
11. **Tracing:** có tracing bridge/exporter nếu cần distributed trace?
12. **Context:** Reactor/WebClient context propagation hoạt động khi đổi scheduler?
13. **Endpoints:** metrics/prometheus chỉ expose cho đối tượng được phép?
14. **Tests:** integration test xác minh cả client và server timer?
15. **Operations:** dashboard phân biệt server latency, client latency, status và outcome?

**Ghi nhớ:** Spring Boot Actuator tự instrument WebFlux server thành `http.server.requests` và WebClient thành `http.client.requests` khi client dùng `WebClient.Builder` do Boot cấu hình. ObservationRegistry điều phối lifecycle; MeterRegistry lưu metric; convention cung cấp tags. Dùng URI template và low-cardinality tags để kiểm soát số time series. Thêm histogram/SLO khi cần phân tích latency, expose Prometheus có bảo vệ và kiểm thử end-to-end cả server lẫn client thay vì chỉ nhìn một phía.

## Tài liệu tham khảo

- Spring Boot 3.5 — Actuator Metrics, WebFlux and WebClient instrumentation: https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- Spring Boot — Actuator endpoints and Prometheus exposure: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Framework — Observability Support, ObservationRegistry and conventions: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Spring Framework 6.2 — DefaultServerRequestObservationConvention API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/http/server/reactive/observation/DefaultServerRequestObservationConvention.html
- Spring Framework — WebClient configuration and observation: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Micrometer — Observation components and lifecycle: https://docs.micrometer.io/micrometer/reference/observation/components.html
- Micrometer — Observation concepts and cardinality: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
