# Tích hợp Spring Cloud Circuit Breaker ở ranh giới HTTP client

Trong kiến trúc microservices, `order-service` thường gọi `inventory-service` qua RestClient, WebClient hoặc OpenFeign bằng service ID `inventory-service`. Spring Cloud LoadBalancer sẽ chọn một `ServiceInstance` dựa vào discovery, health check và thuật toán định tuyến. Tuy vậy, nếu cả inventory chậm, lỗi 5xx liên tục hoặc phụ thuộc database của nó bị quá tải, **tiếp tục gửi mọi request** tới inventory có thể khiến caller cạn thread, connection pool, timeout budget và kéo theo lỗi dây chuyền.

**Spring Cloud Circuit Breaker** cung cấp một API trừu tượng để cô lập lỗi ở **ranh giới gọi phụ thuộc**. Nó quan sát kết quả nhiều lời gọi tới một nhóm operation; khi tỷ lệ lỗi hoặc slow calls đủ cao, breaker có thể tạm ngừng cho phép gọi, fail fast hoặc chuyển sang fallback có kiểm soát. Sau khoảng chờ, một số request thử được phép đi qua để đánh giá khả năng phục hồi.

Bài học thuộc chương **Cô lập và khôi phục** này trình bày cơ chế và cách gắn Circuit Breaker ngay quanh HTTP client; ví dụ RestClient, WebClient, OpenFeign; cấu hình Resilience4j, fallback bảo toàn ý nghĩa dữ liệu, retry/timeout, quan sát và kiểm thử.

## 1. Vì sao đã có LoadBalancer vẫn cần Circuit Breaker?

~~~mermaid
flowchart LR
    U["Người dùng"] --> O["order-service"]
    O --> CB["Circuit Breaker: inventoryRead"]
    CB --> LB["Spring Cloud LoadBalancer"]
    LB --> A["inventory replica A"]
    LB --> B["inventory replica B"]
    LB --> C["inventory replica C"]
~~~

Giả sử `inventory-service` có ba instance A/B/C, nhưng tất cả cùng chậm vì chung một database. Dù LoadBalancer chọn instance khác, kết quả vẫn có thể là timeout. Nếu caller tăng số lần retry, số request đến database còn nhiều hơn. Circuit breaker có thể nhận diện nhiều lời gọi lỗi/chậm và tạm **chặn các lời gọi mới** để giảm áp lực lan truyền.

Cần tách ranh giới trách nhiệm:

| Thành phần | Vai trò | Điều nó không tự bảo đảm |
|---|---|---|
| Discovery | Cung cấp danh sách instance đang được biết | API nghiệp vụ của mọi instance đều khỏe |
| `HealthCheckServiceInstanceListSupplier` | Thăm dò/lọc instance theo endpoint sức khỏe | Endpoint `/stock` phản hồi nhanh và đúng |
| Spring Cloud LoadBalancer | Chọn một `ServiceInstance` cho một lời gọi | Quyết định ngừng gọi cả phụ thuộc đang lỗi |
| Spring Cloud Circuit Breaker | Cho phép/từ chối các lời gọi theo thống kê kết quả | Chọn replica mới hoặc rollback transaction |
| Retry | Thử lại một lỗi tạm thời theo policy | Giới hạn tải nếu lặp quá nhiều |
| HTTP timeout/TimeLimiter | Giới hạn thời gian đợi | Tự nhận diện tần suất lỗi để OPEN |
| Bulkhead | Hạn chế số lời gọi đồng thời | Chọn instance hoặc định tuyến |

Ví dụ có một replica chết, health check hoặc discovery có thể loại nó khỏi danh sách, còn các replica khác tiếp tục phục vụ. **Không nên dùng một breaker chung cho cả service để thay cho lọc đúng replica bị chết**, vì breaker chung có thể tạm chặn cả những replica còn khỏe.

## 2. Ba trạng thái: CLOSED, OPEN, HALF_OPEN

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure rate / slow-call rate vượt ngưỡng
    OPEN --> HALF_OPEN: Qua thời gian chờ và có call thử
    HALF_OPEN --> CLOSED: Các call thử đủ tốt
    HALF_OPEN --> OPEN: Các call thử vẫn lỗi hoặc quá chậm
~~~

- **CLOSED**: request được phép đi tới HTTP client, breaker ghi nhận kết quả theo sliding window.
- **OPEN**: request mới bị từ chối nhanh, thường có `CallNotPermittedException` (Resilience4j); không có attempt HTTP tới backend cho request bị chặn.
- **HALF_OPEN**: breaker cho phép một số lượng giới hạn request thử để quyết định trở lại CLOSED hay OPEN.

Circuit Breaker không nhất thiết mở sau lỗi đầu tiên. Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Nếu có ít hơn năm lần gọi được ghi nhận, chưa đủ `minimumNumberOfCalls` để áp dụng ngưỡng tỷ lệ lỗi. Khi đã đủ mẫu, ba lỗi trong năm lần gọi tương ứng tỷ lệ 60% và có thể khiến breaker OPEN nếu không có rule ngoại lệ:

\[
\mathrm{failureRate}=\frac{\mathrm{failedCalls}}{\mathrm{recordedCalls}}\times100\%.
\]

Lưu ý số call mà breaker nhìn thấy **không luôn bằng số HTTP attempt**, vì còn phụ thuộc vị trí retry so với breaker.

## 3. Chọn ranh giới bảo vệ: service hay operation?

Nên đặt breaker tại adapter/gateway chịu trách nhiệm gọi một dependency, thay vì nhúng logic breaker trong controller hoặc mỗi DTO mapper:

~~~text
OrderController
  -> OrderService (business workflow)
      -> InventoryGateway (ranh giới phụ thuộc)
          -> CircuitBreaker(inventoryRead)
              -> LoadBalanced HTTP client
                  -> ServiceInstance được chọn
~~~

Breaker ID phải ổn định và có ý nghĩa. Một số phương án:

| Phạm vi | Ví dụ ID | Khi nào hợp lý? | Rủi ro |
|---|---|---|---|
| Một service ID | `inventory-service` | Nhiều operations cùng đặc tính lỗi | Một API lỗi chặn mọi API cùng service |
| Một operation | `inventoryRead`, `inventoryReserve` | Read/write có SLO và fallback khác nhau | Tăng số breaker cần quan sát |
| Một instance | Theo replica | Chỉ khi thật sự có cơ chế outlier isolation | Cardinality lớn, lifecycle khó quản lý |
| Một request | ID ngẫu nhiên mỗi lần | **Không phù hợp** | Mất dữ liệu thống kê, breaker vô hiệu về mặt thực tế |

Khuyến nghị thông thường là bắt đầu theo **operation hoặc nhóm operation có cùng cách xử lý lỗi**. Ví dụ `inventoryRead` và `inventoryReserve` có thể cần chính sách khác nhau: tính tồn kho để hiển thị có thể dùng cache, còn thao tác giữ hàng phải fail-safe và không đoán kết quả.

Đặt một breaker bao cả luồng checkout gồm inventory, pricing và payment sẽ khiến một lỗi pricing có thể chặn cả các bước inventory đang khỏe. Mục tiêu là phân lập **phụ thuộc**, không làm mất tính độc lập của các bước.

## 4. Dependency và abstraction của Spring Cloud

Spring Cloud Circuit Breaker cung cấp API `CircuitBreakerFactory` cho code blocking và `ReactiveCircuitBreakerFactory` cho Reactor. Resilience4j là implementation phổ biến; khi thêm starter tương ứng, Spring sẽ tạo bean factory theo cấu hình.

**Dành cho RestClient/OpenFeign hoặc các lời gọi blocking:**

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

**Dành cho WebClient/reactive:**

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

Để chọn instance bằng service ID, cần `spring-cloud-starter-loadbalancer` (hoặc dependency transitively phù hợp). Các lựa chọn HTTP client:

- `spring-boot-starter-web` cho ứng dụng Spring MVC với RestClient;
- `spring-boot-starter-webflux` cho WebClient;
- `spring-cloud-starter-openfeign` cho Feign declarative client.

Đây là **các biến thể theo stack**, không cần mọi dự án cùng lúc dùng cả hai circuit-breaker starter. Dùng Spring Boot BOM và Spring Cloud BOM tương thích, đối chiếu tài liệu của release train đang chạy.

## 5. RestClient được load balance và bao bằng CircuitBreaker

Ví dụ `order-service` gọi inventory qua REST URL logic.

**Đăng ký RestClient:**

~~~java
package com.example.order.http;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean("inventoryRestClient")
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {

        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

`@LoadBalanced` gắn Spring Cloud LoadBalancer vào builder để caller có thể dùng service ID thay vì IP/port cố định. Circuit Breaker chưa xuất hiện trong builder này; chúng ta sẽ **bao lời gọi ở adapter** để có ID breaker riêng và fallback theo nghiệp vụ.

**Gateway bảo vệ một operation đọc tồn kho:**

~~~java
package com.example.order.inventory;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import java.util.concurrent.TimeoutException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

@Service
public class InventoryGateway {

    private final RestClient restClient;
    private final CircuitBreaker breaker;

    public InventoryGateway(
            @Qualifier("inventoryRestClient") RestClient restClient,
            CircuitBreakerFactory<?, ?> factory) {

        this.restClient = restClient;
        this.breaker = factory.create("inventoryRead");
    }

    public StockView getStock(String sku) {
        return breaker.run(
                () -> {
                    InventoryQuantity stock = restClient.get()
                            .uri("/stock/{sku}", sku)
                            .retrieve()
                            .body(InventoryQuantity.class);

                    if (stock == null) {
                        throw new IllegalStateException(
                                "Missing inventory response body"
                        );
                    }

                    return new StockView(
                            stock.sku(), stock.available(), false
                    );
                },
                cause -> fallback(sku, cause)
        );
    }

    private StockView fallback(String sku, Throwable cause) {
        if (cause instanceof HttpClientErrorException e) {
            // Không biến 400/401/403/404 thành stock UNKNOWN.
            throw e;
        }

        if (cause instanceof CallNotPermittedException
                || cause instanceof ResourceAccessException
                || cause instanceof HttpServerErrorException
                || cause instanceof TimeoutException) {
            return new StockView(sku, null, true);
        }

        if (cause instanceof RuntimeException e) {
            throw e;
        }

        throw new IllegalStateException(
                "Unexpected inventory failure", cause
        );
    }

    public record InventoryQuantity(String sku, int available) {}
    public record StockView(
            String sku,
            Integer available,
            boolean degraded
    ) {}
}
~~~

**Ý nghĩa:**

- `CircuitBreakerFactory<?, ?>` là abstraction, giúp adapter không lệ thuộc toàn bộ vào Resilience4j API.
- `factory.create("inventoryRead")` lấy breaker có cùng ID và cấu hình; không tạo ID ngẫu nhiên mỗi request.
- `breaker.run(supplier, fallback)` cho phép thực hiện HTTP call khi breaker ở trạng thái phù hợp; khi bị từ chối hoặc gặp lỗi, fallback được gọi với nguyên nhân.
- RestClient vẫn nhờ LoadBalancer chọn replica trong các call **được phép**.
- `available = null, degraded = true` nghĩa là **không biết số tồn kho**. Không bao giờ coi UNKNOWN là “còn hàng” để tạo đơn.
- HTTP 4xx được rethrow khỏi fallback ở ví dụ, **nhưng rethrow không làm thay đổi kết quả breaker đã ghi**. Cần cấu hình `ignoreExceptions`/`recordException` để 4xx nghiệp vụ không làm breaker mở.
- Không nên che những lỗi lập trình hoặc sai JSON contract thành kết quả giả hợp lệ.

Một fallback đọc-only có thể trả dữ liệu cache kèm `staleAt`/`source` nếu business chấp nhận. Ngược lại, API reserve stock hoặc payment không nên tự chế kết quả thành công khi backend lỗi.

## 6. Phân loại lỗi kỹ thuật và nghiệp vụ

| Kết quả từ inventory | Thường tính vào failure của breaker? | Ứng xử phù hợp |
|---|---|---|
| Connect timeout, connection refused | Có | Fallback giới hạn hoặc fail fast |
| HTTP 500/502/503/504 | Có | Đánh giá outage, không tăng retry vô hạn |
| HTTP 404 SKU không tồn tại | Thường không | Trả not found thật |
| HTTP 400 input sai | Thường không | Sửa/validate request |
| HTTP 401/403 | Thường không coi là outage | Xử lý security, không che bằng fallback |
| HTTP 429 | Tùy chính sách quá tải/rate limit | Tôn trọng Retry-After, tránh retry bão |
| JSON sai contract | Tùy cách phân loại | Báo lỗi contract thay vì dữ liệu giả |
| `CallNotPermittedException` khi OPEN | Không gửi HTTP attempt mới | Fallback hoặc lỗi nhanh |

Với Resilience4j, theo mặc định nhiều exception không bị ignore có thể được ghi nhận là failure. Nếu API thường trả 404 cho một tình huống hợp lệ, hãy điều chỉnh exception classification tương ứng. Ngược lại, nếu backend luôn trả HTTP 200 nhưng body chứa `success: false`, breaker **không tự hiểu** đó là failure; adapter phải xác định khi nào nên ném một exception mang ý nghĩa kỹ thuật hoặc áp dụng policy riêng.

## 7. Cấu hình Resilience4j theo breaker ID

`application.yml` minh họa:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 600ms
        slowCallRateThreshold: 80
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        registerHealthIndicator: true

  timelimiter:
    instances:
      inventoryRead:
        timeoutDuration: 900ms
        cancelRunningFuture: true
~~~

Tên `inventoryRead` phải khớp với `factory.create("inventoryRead")`. Các con số này là ví dụ để thử nghiệm, không phải cấu hình chuẩn cho mọi production workload.

| Thuộc tính | Ý nghĩa |
|---|---|
| `slidingWindowType` | Cửa sổ theo số call (`COUNT_BASED`) hoặc thời gian (`TIME_BASED`) |
| `slidingWindowSize` | Kích thước cửa sổ thống kê |
| `minimumNumberOfCalls` | Số call tối thiểu trước khi áp dụng ngưỡng OPEN |
| `failureRateThreshold` | Ngưỡng phần trăm failed calls |
| `slowCallDurationThreshold` | Mốc phân loại một call là slow |
| `slowCallRateThreshold` | Ngưỡng phần trăm slow calls |
| `waitDurationInOpenState` | Khoảng chờ trước khi có thể thử phục hồi |
| `permittedNumberOfCallsInHalfOpenState` | Giới hạn số phép thử khi HALF_OPEN |
| `registerHealthIndicator` | Tích hợp health indicator nếu có Actuator và cấu hình liên quan |
| `timelimiter.instances.<id>` | Thời hạn do Resilience4j TimeLimiter quản lý, không phải read timeout transport |

Spring Cloud CircuitBreaker Resilience4j cho phép cấu hình global default, group và theo ID; tài liệu chính thức ghi rõ **properties có mức ưu tiên cao hơn Java `Customizer`**, và các thiết lập riêng theo ID có ưu tiên hơn group/default đối với phần tương ứng.

### Không tính 404 hợp lệ thành outage

Nếu một GET SKU không tồn tại được chuyển thành HTTP 404 exception, Resilience4j có thể tính nó là lỗi theo mặc định. Nếu đây là kết quả nghiệp vụ bình thường, hãy cấu hình `ignoreExceptions` hoặc `recordException` đúng class exception thực tế.

Ví dụ với Spring RestClient và HTTP 404:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        ignoreExceptions:
          - org.springframework.web.client.HttpClientErrorException$NotFound
~~~

Hãy kiểm tra log/metrics để xác nhận class exception thực tế: RestClient có thể ném `HttpClientErrorException`, WebClient ném `WebClientResponseException`, còn Feign ném `FeignException`. Không đặt danh sách ignore quá rộng làm che lỗi thật.

### TimeLimiter khác timeout HTTP transport

Tài liệu Spring Cloud CircuitBreaker Resilience4j mô tả TimeLimiter được bật theo mặc định nếu không tắt qua policy. Có thể tắt theo một breaker ID khi muốn giới hạn bằng transport timeout và deadline khác:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        disable-time-limiter-map:
          inventoryRead: true
~~~

Tắt TimeLimiter **không** tắt connect/read timeout của HTTP client. Ngược lại, `timeoutDuration: 900ms` cũng không bảo đảm một lời gọi blocking đang thực thi hoặc backend transaction đã dừng sau 900ms. `cancelRunningFuture` chỉ thể hiện nỗ lực hủy; cần xem khả năng interruption/cancellation của HTTP transport, thread pool và context propagation trong cấu hình cụ thể.

## 8. Phạm vi breaker thường là operation, không phải replica

Giả sử service ID inventory có ba instance A/B/C:

~~~text
A khỏe -> request thành công
B lỗi  -> timeout
C khỏe -> request thành công
A khỏe -> request thành công
B lỗi  -> timeout
...
~~~

Nếu `inventoryRead` dùng chung cho cả service ID, lỗi B vẫn làm tăng failure rate của breaker. Khi ngưỡng bị vượt, breaker có thể OPEN và chặn cả các lời gọi có thể đã chọn A/C khỏe.

Do đó:

- Dùng discovery/health check/outlier policy để loại instance cụ thể bị hỏng.
- Dùng circuit breaker theo operation để hạn chế lỗi lan rộng từ **phụ thuộc** hoặc một loại API.
- Không giả định breaker chung theo service ID tự tạo một trạng thái OPEN/CLOSED riêng cho từng ServiceInstance.
- Sau khi inventory hồi phục, breaker cần cơ chế HALF_OPEN và các phép thử thành công; thay đổi danh sách instance không nhất thiết lập tức đóng breaker.

## 9. WebClient: ReactiveCircuitBreakerFactory bọc Mono

Với WebClient và Reactor, không gọi `Mono.block()` trên event loop chỉ để dùng breaker blocking. Dùng `ReactiveCircuitBreakerFactory` với starter reactive:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

Builder được load balance:

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class InventoryWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder builder) {

        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Dùng breaker reactive ở HTTP adapter:

~~~java
package com.example.order.inventory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

@Service
public class ReactiveInventoryGateway {

    private final WebClient client;
    private final ReactiveCircuitBreaker breaker;

    public ReactiveInventoryGateway(
            @Qualifier("inventoryWebClient") WebClient client,
            ReactiveCircuitBreakerFactory<?, ?> factory) {

        this.client = client;
        this.breaker = factory.create("inventoryReadReactive");
    }

    public Mono<StockView> getStock(String sku) {
        Mono<StockView> remote = client.get()
                .uri("/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryQuantity.class)
                .map(response -> new StockView(
                        response.sku(),
                        response.available(),
                        false
                ));

        return breaker.run(remote, cause -> {
            if (cause instanceof WebClientResponseException e
                    && e.getStatusCode().is4xxClientError()) {
                return Mono.error(cause);
            }

            return Mono.just(new StockView(sku, null, true));
        });
    }

    public record InventoryQuantity(String sku, int available) {}
    public record StockView(
            String sku,
            Integer available,
            boolean degraded
    ) {}
}
~~~

`ReactiveCircuitBreakerFactory.create` dùng ID theo operation; `run` bảo vệ `Mono` và nhận fallback reactive. Trong các call được phép, WebClient tiếp tục nhờ Spring Cloud LoadBalancer chọn instance.

Lưu ý:

- Fallback trả UNKNOWN bằng `available = null`, không giả dữ liệu.
- `Mono.error(cause)` với 4xx **không** thay thế cấu hình exception classification của breaker.
- `retrieve()` theo mặc định chuyển response 4xx/5xx thành exception ở bước xử lý response; `exchangeToMono()` có semantics khác.
- Fallback không nên blocking event loop hoặc gọi lại chính inventory đang lỗi.
- Dùng Reactor Context/observability thay vì dựa hoàn toàn vào MDC ThreadLocal.
- Có thể giới hạn tổng pipeline bằng deadline/timeouts riêng; timeout/cancel publisher không đảm bảo backend đã rollback.

## 10. OpenFeign: tích hợp có sẵn với Spring Cloud CircuitBreaker

OpenFeign có hỗ trợ bao các method Feign bằng Spring Cloud CircuitBreaker. Khi có circuit-breaker starter phù hợp trên classpath, bật:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Theo tài liệu Spring Cloud OpenFeign, `spring.cloud.openfeign.circuitbreaker.enabled` mặc định là `false`. Bật cấu hình này có thể áp dụng circuit breaker cho **các method Feign clients** trong ứng dụng, không chỉ một method cụ thể. Đây không phải một `RequestInterceptor` và không tự bật bằng cách chỉ thêm Spring Cloud LoadBalancer.

Feign interface:

~~~java
package com.example.order.inventory;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(
        name = "inventory-service",
        fallbackFactory = InventoryFeignFallbackFactory.class
)
public interface InventoryFeignClient {

    @GetMapping("/stock/{sku}")
    StockView getStock(@PathVariable("sku") String sku);
}
~~~

DTO trả cho caller:

~~~java
package com.example.order.inventory;

public record StockView(
        String sku,
        Integer available,
        boolean degraded
) {
}
~~~

Fallback factory theo nguyên nhân:

~~~java
package com.example.order.inventory;

import feign.FeignException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.cloud.openfeign.FallbackFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryFeignFallbackFactory
        implements FallbackFactory<InventoryFeignClient> {

    @Override
    public InventoryFeignClient create(Throwable cause) {
        return sku -> {
            if (cause instanceof CallNotPermittedException) {
                return new StockView(sku, null, true);
            }

            if (cause instanceof FeignException error) {
                if (error.status() < 0 || error.status() >= 500) {
                    return new StockView(sku, null, true);
                }

                // Không che các lỗi client như 400/401/403/404.
                throw error;
            }

            if (cause instanceof RuntimeException runtime) {
                throw runtime;
            }

            throw new IllegalStateException(
                    "Unexpected inventory failure", cause
            );
        };
    }
}
~~~

`InventoryFeignFallbackFactory` cần là Spring bean. Trong lab có thể bổ sung `@EnableFeignClients` ở caller và bảo đảm các package được quét. Chỉ truyền `fallbackFactory` vào interface không đủ nếu dependency/feature/bean không được cấu hình đúng.

Dùng `FallbackFactory` khi cần biết nguyên nhân; `fallback` chỉ định một implementation thay thế cố định phù hợp trong những trường hợp đơn giản.

**Phạm vi:** nếu nhiều Feign clients có requirements khác nhau, cân nhắc việc bật circuit breaker cho mọi method và tùy chỉnh opt-out. Tài liệu OpenFeign hướng dẫn dùng `Feign.Builder` prototype để loại một client khỏi breaker chung khi cần; không tự tạo hàng loạt circuit breakers có ID ngẫu nhiên.

## 11. ID của OpenFeign breaker không đơn giản là service ID

Theo tài liệu Spring Cloud OpenFeign, breaker name thường theo kiểu:

~~~text
<FeignClientInterface>#<method>(<parameterTypes>)
~~~

Ví dụ một method của `InventoryFeignClient` có thể có dạng `InventoryFeignClient#getStock(String)`. Trong các phiên bản hiện hành, `spring.cloud.openfeign.circuitbreaker.alphanumeric-ids.enabled` mặc định bật để ID phù hợp khi dùng trong configuration properties.

Có thể dùng `CircuitBreakerNameResolver` để kiểm soát tên:

~~~java
import org.springframework.cloud.openfeign.CircuitBreakerNameResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeignCircuitBreakerNaming {

    @Bean
    CircuitBreakerNameResolver circuitBreakerNameResolver() {
        return (feignClientName, target, method) ->
                target.type().getSimpleName()
                        + method.getName();
    }
}
~~~

Với ví dụ này, ID tương ứng là `InventoryFeignClientgetStock` và có thể cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      InventoryFeignClientgetStock:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
~~~

**Hãy xác minh tên thật trong registry/metrics/logs của phiên bản chạy**, thay vì sao chép bừa ví dụ khi dùng default naming. Cấu hình group breaker và các tên đã được normalize cũng cần kiểm tra khi nâng cấp release train.

## 12. Fallback phải giữ ý nghĩa nghiệp vụ

| Operation | Fallback có thể phù hợp | Fallback nguy hiểm |
|---|---|---|
| Gợi ý sản phẩm không bắt buộc | Danh sách rỗng với cờ degraded | Giả rằng dịch vụ đề xuất vẫn khỏe |
| Giá hiển thị tham khảo | Cache kèm timestamp, đánh dấu stale | Dùng giá cũ để thanh toán mà không kiểm tra |
| Tra cứu tồn kho | UNKNOWN để UI thông báo thử lại | `available = 0` hay `999` như số thật |
| Reserve stock | Fail fast, lưu idempotency key | Trả “đã giữ hàng” khi chưa có xác nhận |
| Tạo thanh toán | Fail-safe, tra cứu trạng thái về sau | Trả “đã thanh toán” khi không biết kết quả |
| Audit bắt buộc | Không âm thầm bỏ event | Fallback vô điều kiện không ghi lại |

Fallback lý tưởng nên **nhanh, không gây side effect mới và không gọi lại ngay dependency đang lỗi**. Nếu cần fallback sang Redis hoặc dịch vụ thứ hai, fallback cũng cần timeout/concurrency budget và được theo dõi độc lập.

Một HTTP 200 chứa `degraded: true` có thể là cách biểu diễn hợp lý cho chức năng hiển thị, nhưng không nên làm monitoring tin rằng business request đã hoàn tất đầy đủ. Với thao tác quan trọng, trả lỗi có kiểm soát phù hợp hơn.

## 13. Thứ tự Circuit Breaker, Retry và Timeout

Một cách đặt các chính sách:

~~~mermaid
flowchart LR
    A["Business request"] --> D["End-to-end deadline"]
    D --> CB["CircuitBreaker"]
    CB --> R["Retry có giới hạn"]
    R --> LB["Spring Cloud LoadBalancer"]
    LB --> T["HTTP transport timeout"]
    T --> B["Inventory replica"]
~~~

Đây là **một lựa chọn kiến trúc**, không phải thứ tự tự động duy nhất của Spring Cloud. Nếu breaker **bao ngoài retry**, một logical call gồm nhiều attempts có thể chỉ tạo một kết quả breaker. Nếu retry **bao ngoài breaker**, mỗi attempt có thể được ghi nhận riêng và làm breaker OPEN nhanh hơn.

Hãy quyết định rõ:

- Tầng nào sở hữu retry: Feign, LoadBalancer, resilience layer hay gateway?
- Breaker đo logical call hay từng HTTP attempt?
- Những exception nào được retry, bỏ qua hoặc ghi nhận failure?
- Timeout transport giới hạn một attempt hay toàn bộ chuỗi?
- Fallback có được nằm trong cùng end-to-end deadline không?
- **Không retry `CallNotPermittedException`**, vì breaker đang chủ động từ chối.
- Retry thao tác ghi chỉ khi bảo đảm idempotency; timeout có thể xảy ra sau khi backend đã commit.

Circuit breaker **không tự giới hạn concurrency trong CLOSED**. Bulkhead, connection pool limit, timeout và load shedding có vai trò riêng trong việc tránh cascading failure.

## 14. TimeLimiter, thread pool và ngữ cảnh người gọi

TimeLimiter đôi khi thực thi công việc blocking qua executor. Nếu caller dùng `MDC`, `SecurityContextHolder` hoặc một holder dựa trên `ThreadLocal` để gắn correlation ID và bearer token, việc chuyển luồng thực thi có thể khiến **ngữ cảnh biến mất**.

Ví dụ:

~~~text
HTTP thread:
    correlationId = C-123
    SecurityContext = authenticated user
        |
        v
CircuitBreaker / TimeLimiter
        |
        v
Executor thread:
    MDC / SecurityContext có thể trống nếu không propagate
        |
        v
OpenFeign RequestInterceptor hoặc RestClient interceptor
~~~

Biện pháp:

- Không lưu correlation ID hoặc thông tin người dùng vào field mutable của singleton HTTP client/breaker.
- Với ứng dụng blocking dùng executor, thiết lập context propagation theo hỗ trợ của Spring Security/Micrometer hoặc custom executor có quy tắc copy/restore rõ ràng.
- Nếu dùng `DelegatingSecurityContextExecutorService` hay giải pháp tương tự, kiểm thử cả việc xóa ngữ cảnh khi tác vụ kết thúc để tránh rò dữ liệu.
- Với Reactor/WebClient, ưu tiên Reactor `Context` và tracing instrumentation thay vì giả định ThreadLocal đi qua mọi operator.
- Token dành cho service-to-service có thể được cấp bằng client credentials riêng; không mặc định relay JWT của user qua mọi downstream.
- Không đặt time limit ở mức 200 ms rồi để fallback gọi network thêm 5 giây: fallback cũng cần nằm trong deadline tổng.

Tài liệu Spring Cloud CircuitBreaker có điểm mở rộng để cấu hình executor/context-aware executor cho implementation Resilience4j. Hãy chọn executor và chiến lược propagation phù hợp với release train được sử dụng.

## 15. Quan sát trạng thái circuit breaker bằng Actuator và Micrometer

Các trạng thái chuyển từ CLOSED sang OPEN rồi HALF_OPEN cần được **quan sát và cảnh báo**, không chỉ nhìn thấy “API vẫn trả HTTP 200 sau fallback”.

Khi Spring Boot Actuator, Resilience4j Micrometer integration và registry phù hợp được bật, có thể sử dụng các metric/counter của circuit breaker (tên cụ thể phụ thuộc phiên bản/exporter), ví dụ:

| Nhóm metric | Ý nghĩa |
|---|---|
| Circuit breaker state | CLOSED/OPEN/HALF_OPEN theo breaker name |
| Calls theo kết quả | Successful, failed, slow hoặc not permitted |
| Failure/slow-call rate | Tỷ lệ tính từ sliding window |
| Not-permitted calls | Lời gọi bị breaker chặn mà không gửi HTTP |
| Retry attempts | Số attempt thực gửi do retry |
| HTTP client latency | Độ trễ của transport/operation |
| LoadBalancer chọn instance | Service ID/instance và kết quả khi có instrumentation |
| Fallback count | Số lần degradation, cache fallback hoặc fast-fail |

Ví dụ cấu hình liên quan (cần starter Actuator và metrics registry thích hợp):

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics

resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        registerHealthIndicator: true
~~~

`registerHealthIndicator: true` có thể làm health endpoint phản ánh trạng thái breaker khi integration hỗ trợ. **Không tự động coi breaker OPEN là lý do toàn bộ order-service phải bị orchestration restart**. Một downstream có thể hỏng trong khi order-service vẫn xử lý các API khác bình thường. Quyết định readiness/liveness cần dựa trên criticality của dependency và policy vận hành.

Một cảnh báo hữu ích có thể là: breaker `inventoryRead` OPEN kéo dài, tỷ lệ not-permitted calls tăng, hoặc fallback UNKNOWN vượt tỷ lệ đã định. Không đưa SKU/user ID/tenant động vào metric labels làm cardinality tăng không kiểm soát.

### Logging cần phân biệt lỗi từ chối và lỗi backend

Hai tình huống có triệu chứng phía user tương tự nhưng khác nguyên nhân:

~~~text
Trường hợp A: HTTP attempt thất bại
  inventoryRead CLOSED
  -> LoadBalancer chọn inventory B
  -> Request gửi đi
  -> Connect timeout / HTTP 503
  -> Breaker ghi failure

Trường hợp B: breaker đang OPEN
  inventoryRead OPEN
  -> CallNotPermittedException
  -> Không có HTTP attempt mới
  -> Fallback UNKNOWN / error
~~~

Nếu mọi failure đều được log là “inventory timeout”, đội vận hành có thể vô tình chẩn đoán sai. Dùng exception class, breaker state và trace context để phân biệt; không log access token hoặc payload nhạy cảm.

## 16. Phục hồi: HALF_OPEN không phải bỏ qua mọi giới hạn

Khi thời gian OPEN hết, Resilience4j có thể chuyển trạng thái để thử các lời gọi mới. Số phép thử được phép phụ thuộc `permittedNumberOfCallsInHalfOpenState`; khi đã sử dụng hết số slot cho phép, các call khác có thể tiếp tục bị từ chối cho đến khi trạng thái được quyết định.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant B as CircuitBreaker
    participant L as LoadBalancer
    participant I as inventory-service

    C->>B: GET /stock (breaker OPEN)
    B-->>C: CallNotPermitted / fallback
    Note over B: Qua waitDurationInOpenState
    C->>B: GET /stock (thử phục hồi)
    B->>L: Cho phép một HALF_OPEN probe
    L->>I: HTTP GET /stock
    I-->>L: 200 OK
    L-->>B: Kết quả thành công
    Note over B: Đủ kết quả tốt -> CLOSED
    B-->>C: StockView thực tế
~~~

Sơ đồ minh họa cơ chế chuyển trạng thái; việc chuyển từ HALF_OPEN sang CLOSED phụ thuộc **cả tập phép thử** và cấu hình tỷ lệ lỗi/slow calls, không nhất thiết chỉ một response 200.

Các điểm vận hành:

1. Đừng set `waitDurationInOpenState` quá ngắn khi hệ thống đích cần thời gian phục hồi: breaker sẽ thử liên tục và có thể tạo thêm tải.
2. Đừng set quá dài nếu nghiệp vụ cần khôi phục nhanh sau sự cố ngắn.
3. Mỗi instance của **caller** thường có breaker state riêng trong tiến trình của nó. Nhiều caller replicas có thể chuyển HALF_OPEN gần nhau và tạo lượng probe đáng kể; cân nhắc concurrency limits và khả năng chịu tải lúc hồi phục.
4. Metrics và tracing cần xác định thời điểm chuyển state, số half-open probes và lượng fallback.
5. Một call thành công ở inventory không chứng minh toàn bộ backend ổn định; cần đủ mẫu theo chính sách.
6. Nếu service đã phục hồi nhưng vẫn trả chậm hơn `slowCallDurationThreshold`, breaker có thể tiếp tục OPEN vì **slow-call rate**, dù status đều là 200.

Không nên dựa vào thao tác restart caller để “reset breaker” như cách phục hồi chính: điều này xóa history, nhưng không giải quyết nguyên nhân lỗi downstream.

## 17. Bài thực hành với hai replica inventory

Mục tiêu: chứng minh một sự cố của `inventory-service` khiến breaker chuyển CLOSED → OPEN, không gửi thêm request trong OPEN, và sau khi inventory hồi phục, breaker dùng HALF_OPEN để thử lại.

### 17.1. Cấu hình discovery ở caller

Sử dụng `SimpleDiscoveryClient` để có hai replica:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Bổ sung cấu hình breaker riêng cho lab:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 5
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 8s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      inventoryRead:
        timeoutDuration: 2s
~~~

Những con số này chỉ dành cho thử nghiệm **ít request**, không phải ngưỡng production. Nếu request có retry, breaker có thể nhìn thấy số calls khác với số HTTP attempts; nên **tắt retry hoặc kiểm soát chặt số lần thử** trong bài lab để dễ quan sát.

### 17.2. Tạo endpoint mô phỏng inventory hỏng

Trong mỗi tiến trình inventory chạy mã nguồn tương tự:

~~~java
package com.example.inventory;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoInventoryController {

    private final AtomicBoolean failing = new AtomicBoolean(false);

    @GetMapping("/stock/{sku}")
    public ResponseEntity<InventoryQuantity> stock(
            @PathVariable String sku) {

        if (failing.get()) {
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .build();
        }

        return ResponseEntity.ok(
                new InventoryQuantity(sku, 12)
        );
    }

    // Chỉ cho môi trường local lab, KHÔNG triển khai công khai.
    @PostMapping("/demo/fail")
    public void fail() {
        failing.set(true);
    }

    @PostMapping("/demo/recover")
    public void recover() {
        failing.set(false);
    }

    public record InventoryQuantity(String sku, int available) {}
}
~~~

Chạy inventory ở cổng 8081 và 8082. Lưu ý mỗi tiến trình có `AtomicBoolean` riêng, nên thay đổi ở 8081 **không** ảnh hưởng 8082.

Caller dùng RestClient + `InventoryGateway` ở phần trước và tạo một controller `GET /orders/stock/{sku}` chuyển tiếp `gateway.getStock(sku)`. Endpoint này phải được triển khai trong lab; không phải API có sẵn từ Spring Cloud.

### 17.3. Kịch bản A: tất cả instance khỏe

~~~powershell
1..6 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/orders/stock/SKU-001"
}
~~~

Kỳ vọng ban đầu là `degraded: false`, `available: 12` và breaker ở CLOSED. Đối chiếu access log của inventory, vì response của `StockView` không ghi instance ID.

### 17.4. Kịch bản B: cả hai replica trả 503

~~~powershell
Invoke-RestMethod -Method Post http://localhost:8081/demo/fail
Invoke-RestMethod -Method Post http://localhost:8082/demo/fail

1..8 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/orders/stock/SKU-001"
}
~~~

Sau khi số call đủ và failure rate vượt ngưỡng, breaker có thể chuyển OPEN. Caller nhận `degraded: true`, `available: null` nếu fallback cho phép. Các call tiếp theo trong OPEN có thể được trả ngay mà **không** xuất hiện thêm inbound request ở log inventory.

Có thể kiểm tra circuit breaker state/counter qua Actuator metrics khi integration có sẵn. Không khẳng định chính xác “lần thứ N luôn OPEN” nếu test còn retry, custom exception classifier, metrics recording khác hoặc call concurrent.

### 17.5. Kịch bản C: backend hồi phục

~~~powershell
Invoke-RestMethod -Method Post http://localhost:8081/demo/recover
Invoke-RestMethod -Method Post http://localhost:8082/demo/recover
~~~

Sau khoảng `waitDurationInOpenState`, gửi một số request mới để kích hoạt HALF_OPEN probes. Nếu kết quả tốt theo tiêu chí, breaker trở về CLOSED và trả StockView thực tế. Nếu inventory tiếp tục trả 503, có thể trở lại OPEN.

**Không cần restart caller**; breaker được kỳ vọng phục hồi theo state machine và probes. Nếu traffic rất ít, có thể không có phép thử mới ngay sau thời gian chờ. Trong những hệ thống nhiều replica caller, mỗi tiến trình có thể quan sát state khác nhau.

## 18. Chiến lược kiểm thử có ý nghĩa

Không nên chỉ kiểm tra “fallback luôn trả 200 khi lỗi”. Một bộ test phù hợp nên bao gồm:

1. **Normal path:** backend 200, breaker CLOSED, dữ liệu thật và `degraded = false`.
2. **Error classification:** 404/400 nghiệp vụ không bị đổi thành 200 UNKNOWN; breaker metrics không coi nó là outage khi policy đã cấu hình ignore.
3. **OPEN path:** sau đủ failure, lời gọi mới không đến backend, trả fallback hoặc lỗi fail fast đúng contract.
4. **HALF_OPEN:** sau thời gian chờ, chỉ số lượng probes được phép được gửi; kết quả tốt đưa breaker về CLOSED.
5. **Failed recovery:** probes trả lỗi khiến breaker quay lại OPEN.
6. **Timeout:** transport timeout và TimeLimiter/deadline tổng không bị đánh đồng; xác nhận không còn giữ quá nhiều tasks sau cancellation.
7. **Retry:** kiểm tra số logical calls và số attempts, loại trừ retry khi breaker OPEN.
8. **Fallback safety:** giá trị `available = null` không bị tầng order hiểu nhầm là `available > 0`.
9. **Multi-replica caller:** breaker state theo tiến trình; đánh giá độ đồng bộ của metrics/alerts.
10. **No-instance:** khi discovery không trả instance, xử lý lỗi LoadBalancer và breaker rõ ràng, không che bằng thông báo sai.

Có thể sử dụng WireMock hoặc MockWebServer kết hợp Spring Boot test để mô phỏng HTTP 200, 404, 503, connect failure và delay; dùng cách kiểm soát thời gian chờ hoặc test scheduler phù hợp để tránh flaky tests. Với unit test chỉ kiểm tra `CircuitBreakerFactory` wrapper/fallback, nên thay HTTP adapter bằng stub để không phụ thuộc kết nối mạng.

Không chạy assertions dựa trên chuỗi replica Round Robin khi test có concurrency/retry, cũng không kỳ vọng một lời gọi lỗi đầu tiên luôn mở breaker.

## 19. Những lỗi thường gặp khi tích hợp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Có starter nhưng breaker không bảo vệ RestClient | Chưa dùng `factory.create(...).run(...)` | Kiểm tra HTTP gateway method và bean factory |
| WebClient vẫn gửi HTTP trong khi tưởng OPEN | Đang dùng client không được bao reactive breaker | Kiểm tra publisher được `breaker.run(...)` bao |
| Feign fallback không chạy | Chưa bật `spring.cloud.openfeign.circuitbreaker.enabled` hoặc fallback không phải bean | Kiểm tra starter, property và component scan |
| Resilience4j properties không tác dụng cho Feign | Dùng sai ID breaker method | Kiểm tra naming resolver, alphanumeric IDs và metrics |
| 404 làm breaker OPEN | Exception classifier coi 404 là lỗi | Dùng ignore/record policy cho lỗi nghiệp vụ |
| Mọi request OPEN dù chỉ một replica hỏng | Breaker chung theo service ID/operation | Sửa health/discovery filtering hoặc isolation strategy |
| OPEN nhưng inventory access logs còn traffic | Còn caller instance khác, method khác hoặc retry/probe khác | Gắn instance/operation ID để phân biệt |
| Breaker không bao giờ OPEN | `minimumNumberOfCalls` cao, lỗi không được ghi nhận hoặc fallback nằm bên trong | Kiểm tra counters và thứ tự policies |
| Breaker không trở về CLOSED | Không có probes hoặc probes vẫn lỗi/chậm | Kiểm tra HALF_OPEN events và thresholds |
| Timeout không hủy HTTP request thật | TimeLimiter chỉ báo timeout/cancel best effort | Kiểm tra transport, task lifecycle và backend work |
| Correlation ID mất khi bọc blocking call | Thay đổi executor/thread không propagate context | Dùng context-aware executor/propagation |
| Dashboard hiện toàn HTTP 200 dù inventory hỏng | Fallback che lỗi kỹ thuật | Thêm degraded metric, đừng đánh đồng 200 với thành công đầy đủ |
| Retry khi breaker OPEN | Policy retry mọi exception | Bỏ `CallNotPermittedException` khỏi retry conditions |
| Circuit breaker làm ứng dụng bị đánh unhealthy | Health indicator ảnh hưởng readiness/liveness không phù hợp | Thiết kế lại health groups theo criticality |

## 20. Checklist trước khi triển khai production

- [ ] Xác định operation HTTP cần bảo vệ và tên breaker ổn định.
- [ ] Phân biệt lỗi instance đơn lẻ (health/discovery) với outage của dependency/operation (breaker).
- [ ] Dùng `CircuitBreakerFactory` cho RestClient blocking và `ReactiveCircuitBreakerFactory` cho WebClient.
- [ ] Với OpenFeign, kiểm tra starter, `spring.cloud.openfeign.circuitbreaker.enabled` và `fallbackFactory`.
- [ ] Biết rõ tên breaker thực tế của từng Feign method khi cấu hình Resilience4j.
- [ ] Chọn `minimumNumberOfCalls`, window, failure/slow rates và wait duration từ dữ liệu SLO.
- [ ] Loại 4xx nghiệp vụ khỏi failure classification khi phù hợp; không che lỗi security/validation.
- [ ] Fallback trả dữ liệu có ngữ nghĩa rõ, không giả thành công cho reserve/payment.
- [ ] Có timeout transport, deadline tổng và retry budget độc lập; không retry call bị breaker từ chối.
- [ ] Kiểm tra tác động của TimeLimiter lên executor, MDC/SecurityContext, cancellation.
- [ ] Nếu nhiều request đồng thời, có bulkhead/pool limits để phòng cạn tài nguyên trong CLOSED.
- [ ] Đo state transition, not-permitted calls, fallback/degraded rate, lỗi backend và latency.
- [ ] Cân nhắc nhiều replicas caller cùng HALF_OPEN và khả năng tạo probe surge.
- [ ] Không để health indicator breaker OPEN vô tình kích hoạt restart toàn ứng dụng.
- [ ] Test các trạng thái CLOSED/OPEN/HALF_OPEN, exception classes, retry, timeout và recovery.
- [ ] Tránh trộn nhiều lớp circuit breaker cho cùng operation mà không có mục đích đo đạc rõ.

## Tài liệu tham khảo

- [Spring Cloud Commons — Spring Cloud Circuit Breaker](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): `CircuitBreakerFactory`, `ReactiveCircuitBreakerFactory` và điểm mở rộng cho HTTP clients.
- [Spring Cloud CircuitBreaker — Resilience4j Properties](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/circuit-breaker-properties-configuration.html): cấu hình default/group/instance, TimeLimiter và độ ưu tiên properties.
- [Spring Cloud CircuitBreaker — Default Configuration](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/default-configuration.html): `Customizer` cho blocking/reactive factories.
- [Spring Cloud OpenFeign — Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): Feign CircuitBreaker support, fallbackFactory, breaker IDs và cách bật integration.
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): service ID, `ServiceInstance`, health checks, retry và selection.
- [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): sliding window, failure/slow-call thresholds và state transitions.

**Kết luận:** Spring Cloud Circuit Breaker phù hợp nhất khi được đặt ngay tại **ranh giới phụ thuộc HTTP**, bao một operation cụ thể của RestClient, WebClient hoặc OpenFeign. Nó bảo vệ caller khỏi việc liên tục chờ một dependency lỗi/chậm, nhưng không thay thế LoadBalancer, health check, timeout, idempotency hay bulkhead. Thành công của thiết kế nằm ở breaker ID ổn định, phân loại lỗi chính xác, fallback trung thực, quan sát được trạng thái OPEN/HALF_OPEN và quy trình phục hồi đã kiểm thử.


