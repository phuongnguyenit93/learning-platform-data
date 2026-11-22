# ReactorLoadBalancerExchangeFilterFunction trong chuỗi filter

Khi `WebClient` gửi request đến `http://inventory-service`, chuỗi `ExchangeFilterFunction` có thể can thiệp trước khi request đi qua HTTP connector. **`ReactorLoadBalancerExchangeFilterFunction`** là bộ lọc tích hợp Spring Cloud LoadBalancer với WebClient: nó nhận URI có hostname là **service ID**, lấy một `ServiceInstance` từ bộ chọn tương ứng, rồi chuyển request đến URI của instance đã chọn.

Điểm quan trọng của bài học là **vị trí bộ lọc trong chuỗi**, không chỉ là cách gắn một annotation. Các filter xác thực, truyền context và logging có thể chạy *trước hoặc sau* quá trình chuyển service ID thành địa chỉ thực. Điều này làm thay đổi URL mà filter nhìn thấy, phạm vi thời gian đo được, cách log request và ranh giới giữa một lần gọi logic với các lần thử lại.

Trong module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**, WebClient là một trong các lựa chọn liên lạc đồng bộ về mặt nghiệp vụ nhưng thực thi I/O theo mô hình reactive, bên cạnh RestClient và OpenFeign. Các nguyên tắc discovery, health check, định tuyến, retry và timeout vẫn cần được hiểu độc lập với việc dùng HTTP client nào.

## 1. WebClient dùng filter chain để làm gì?

`WebClient` là HTTP client có API reactive thuộc Spring WebFlux. `ExchangeFilterFunction` có chữ ký khái niệm:

~~~java
Mono<ClientResponse> filter(
        ClientRequest request,
        ExchangeFunction next
);
~~~

- `ClientRequest` biểu diễn method, URL, headers, cookies, attributes và request body.
- `ExchangeFunction next` đại diện cho phần còn lại của chuỗi filter hoặc tầng thực thi HTTP.
- `Mono<ClientResponse>` mô tả kết quả bất đồng bộ của lần trao đổi HTTP.
- Mỗi filter có thể tạo request mới bằng `ClientRequest.from(request)`, gọi `next.exchange(...)` và xử lý response, error hoặc cancellation trong chuỗi reactive.

Luồng ví dụ:

~~~mermaid
flowchart LR
    A["OrderService"] --> B["WebClient"]
    B --> C["Correlation filter"]
    C --> D["Authentication filter"]
    D --> E["ReactorLoadBalancerExchangeFilterFunction"]
    E --> F["HTTP logging filter"]
    F --> G["ExchangeFunction / connector"]
    G --> H["Inventory replica"]
~~~

Sơ đồ minh họa thứ tự khi các filter được đăng ký như vậy. **Không phải mọi WebClient đều có cùng các filter**, cũng không bảo đảm những filter tự động từ framework xuất hiện ở cùng vị trí trong mọi release train. Khi dùng `@LoadBalanced`, Spring Cloud tự thêm tích hợp vào builder; khi dùng `.filter(lbFunction)` thủ công, ứng dụng chịu trách nhiệm vị trí của nó.

### Vì sao WebClient khác RestTemplate ở đây?

| Khía cạnh | RestTemplate | WebClient |
|---|---|---|
| Điểm mở rộng HTTP client | `ClientHttpRequestInterceptor` | `ExchangeFilterFunction` |
| Giá trị trả về thông thường | Object hoặc `ResponseEntity` sau lời gọi blocking | `Mono<T>`, `Flux<T>` hoặc `Mono<ClientResponse>` |
| Cách tiếp tục chuỗi | `execution.execute(request, body)` | `next.exchange(request)` |
| Cơ chế truyền context phù hợp | ThreadLocal/MDC trong luồng blocking có kiểm soát | Reactor `Context` và instrumentation reactive |
| Tích hợp LoadBalancer | Interceptor/`@LoadBalanced RestTemplate` | `ReactorLoadBalancerExchangeFilterFunction` hoặc builder `@LoadBalanced` |

Dùng WebClient bên trong Spring MVC vẫn được; không bắt buộc chuyển toàn bộ controller thành WebFlux. Nhưng không nên gọi `block()` trên thread event loop vì có thể gây chặn luồng, tắc nghẽn hoặc lỗi runtime.

## 2. Từ service ID tới ServiceInstance: filter làm gì?

Giả sử discovery cung cấp:

| Service ID | Instance ID | Host | Port |
|---|---|---|---:|
| `inventory-service` | `inventory-a` | `127.0.0.1` | 8081 |
| `inventory-service` | `inventory-b` | `127.0.0.1` | 8082 |

Business code tạo URL logic:

~~~text
http://inventory-service/api/stock/SKU-100
~~~

Khi bộ lọc load balancing chạy, nó đọc hostname `inventory-service` từ URL, yêu cầu Spring Cloud LoadBalancer chọn một instance và dựng URL dựa trên instance đó:

~~~text
ClientRequest ban đầu:
    GET http://inventory-service/api/stock/SKU-100

ReactorLoadBalancerExchangeFilterFunction:
    service ID = inventory-service
    -> ServiceInstanceListSupplier
    -> LoadBalancer chọn inventory-b

ClientRequest chuyển cho HTTP connector:
    GET http://127.0.0.1:8082/api/stock/SKU-100
~~~

~~~mermaid
sequenceDiagram
    participant B as Business
    participant F as WebClient filter chain
    participant L as Reactor LoadBalancer
    participant S as Instance supplier
    participant I as Inventory instance B

    B->>F: GET http://inventory-service/api/stock
    F->>L: Chọn ServiceInstance cho inventory-service
    L->>S: Lấy các instance đủ điều kiện
    S-->>L: [inventory-a, inventory-b]
    L-->>F: inventory-b :8082
    F->>I: GET http://127.0.0.1:8082/api/stock
    I-->>F: 200 + JSON
    F-->>B: Mono<ClientResponse> / body
~~~

Thuật toán mặc định thường là Round Robin; có thể dùng Random hoặc chiến lược riêng qua `@LoadBalancerClient`. Bộ lọc WebClient **không tự quyết định** sức khỏe, zone hay trọng số: danh sách ứng viên và thuật toán đến từ context LoadBalancer của service ID.

Nếu chỉ có một instance, filter luôn chọn instance đó. Nếu không có ứng viên, cơ chế load balancing không thể chọn backend. Với tích hợp hiện hành, request có thể được biểu diễn bằng response `503 Service Unavailable`, nhưng cách lỗi được biểu diễn ở tầng caller còn phụ thuộc phiên bản và cách dùng `retrieve()` hoặc `exchangeToMono()`.

## 3. Điều kiện để ReactorLoadBalancerExchangeFilterFunction hoạt động

Caller cần các thành phần sau:

1. `spring-boot-starter-webflux` (hoặc Spring WebFlux tương ứng) để có WebClient và reactive HTTP stack.
2. `spring-cloud-starter-loadbalancer` để có Spring Cloud LoadBalancer cùng tích hợp với HTTP client.
3. Một danh sách `ServiceInstance` cho service ID, lấy từ discovery registry, `SimpleDiscoveryClient` hoặc supplier tùy chỉnh.
4. WebClient đã được cấu hình dùng LoadBalancer filter.
5. Backend thật đang lắng nghe tại các host/port được discovery cung cấp.

Ví dụ Maven dependencies trong một Spring Boot application dùng Spring Cloud BOM tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

Nếu ứng dụng đồng thời có `spring-boot-starter-web`, WebClient vẫn có thể được sử dụng ở service layer. Sự hiện diện của WebClient không mặc nhiên khiến ứng dụng chạy trên server reactive thay vì Spring MVC.

Cần quản lý phiên bản Spring Boot/Spring Cloud bằng tổ hợp tương thích. Không sao chép một phiên bản library tùy ý chỉ vì snippet biên dịch trong dự án khác.

## 4. Cách 1: dùng @LoadBalanced WebClient.Builder

Đây là cách thuận tiện và thường được dùng trong ứng dụng Spring Cloud:

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder loadBalancedBuilder) {

        return loadBalancedBuilder
                .clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

`@LoadBalanced` đánh dấu builder để Spring Cloud tích hợp LoadBalancer filter. `clone()` giúp giảm nguy cơ làm biến đổi cấu hình của builder đang được chia sẻ với WebClient khác. Không cần tự thêm `ReactorLoadBalancerExchangeFilterFunction` lần nữa vào builder này.

Caller:

~~~java
package com.example.order.inventory;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class InventoryClient {

    private final WebClient inventoryWebClient;

    public InventoryClient(WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<InventoryResponse> findStock(String sku) {
        return inventoryWebClient.get()
                .uri("/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }

    public record InventoryResponse(String sku, int available) {
    }
}
~~~

Method trả `Mono<InventoryResponse>` và chỉ thực hiện request khi có subscriber. Nếu gọi `findStock(sku)` mà không subscribe hoặc không có framework tiêu thụ Mono, request chưa chắc được gửi.

**Chú ý bean injection:** nếu hệ thống có nhiều WebClient beans, nên dùng `@Qualifier("inventoryWebClient")` trên constructor để chọn đúng client. Không dựa vào thứ tự bean ngẫu nhiên.

### Khi nào dùng cách này?

Khi chỉ cần dùng service ID như URL logic và không kiểm soát chi tiết vị trí LoadBalancer filter trong chuỗi, `@LoadBalanced WebClient.Builder` là giải pháp gọn. Các tính năng bổ sung như authentication, correlation và logging vẫn có thể dùng `.filter(...)`, nhưng thứ tự hoàn chỉnh cần được xác minh nếu điều đó ảnh hưởng đến yêu cầu của bạn.

## 5. Cách 2: gắn ReactorLoadBalancerExchangeFilterFunction thủ công

Nếu cần kiểm soát thứ tự filter, tiêm `ReactorLoadBalancerExchangeFilterFunction` do Spring Cloud tạo và gắn nó vào WebClient như một `ExchangeFilterFunction`.

**Đây là phương án thay thế cho cách 1, không dùng đồng thời trên cùng một builder.**

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.reactive.ReactorLoadBalancerExchangeFilterFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class ExplicitLoadBalancerConfiguration {

    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(
            WebClient.Builder ordinaryBuilder,
            ReactorLoadBalancerExchangeFilterFunction lbFunction) {

        return ordinaryBuilder
                .clone()
                .baseUrl("http://inventory-service")
                .filter(lbFunction)
                .build();
    }
}
~~~

Snippet trên cố ý nhận `WebClient.Builder ordinaryBuilder` thông thường do Spring Boot cung cấp, **không phải một builder đã đánh dấu `@LoadBalanced`**. Nếu một bean builder khác trong hệ thống đã mang annotation này, hãy dùng qualifier rõ ràng hoặc cấu hình một builder riêng để tránh gắn LoadBalancer filter hai lần.

Một biến thể có thêm filter:

~~~java
@Bean("inventoryWebClient")
WebClient inventoryWebClient(
        WebClient.Builder builder,
        ReactorLoadBalancerExchangeFilterFunction lbFunction,
        ExchangeFilterFunction correlationFilter,
        ExchangeFilterFunction logicalRequestLogFilter,
        ExchangeFilterFunction physicalRequestLogFilter) {

    return builder.clone()
            .baseUrl("http://inventory-service")
            .filter(correlationFilter)
            .filter(logicalRequestLogFilter)
            .filter(lbFunction)
            .filter(physicalRequestLogFilter)
            .build();
}
~~~

Giả định đây là các bean `ExchangeFilterFunction` riêng đã được định nghĩa ở ứng dụng. Ý đồ thiết kế:

- `correlationFilter` thêm header nhận diện request từ Reactor Context.
- `logicalRequestLogFilter` nhìn URL chứa service ID trước LoadBalancer.
- `lbFunction` chọn instance và thay URL đến địa chỉ đích.
- `physicalRequestLogFilter` có thể nhìn URL vật lý của instance đã chọn.

Nếu application cần bảo vệ địa chỉ nội bộ khỏi log, không đưa host vật lý hoặc dữ liệu nhạy cảm vào logs sản xuất. Tốt hơn là dùng tracing/lifecycle metrics và policy redact phù hợp.

## 6. Thứ tự filter thay đổi những gì?

`WebClient.Builder.filter(...)` đăng ký filter vào chuỗi; thông thường filter ngoài được gọi trước, filter nằm sau được gọi khi `next.exchange(...)` được thực thi.

Ví dụ cấu hình:

~~~text
F1 = correlation
F2 = logical request logging
F3 = ReactorLoadBalancerExchangeFilterFunction
F4 = physical request logging
F5 = HTTP connector
~~~

Trình tự trước khi nhận response:

~~~text
Business code
  -> F1: thêm X-Correlation-Id
    -> F2: nhìn URL http://inventory-service/...
      -> F3: chọn ServiceInstance
        -> F4: nhìn URL http://127.0.0.1:8082/...
          -> F5: thực hiện network I/O
~~~

Response, error và cancellation đi ngược về phía filter ngoài tùy toán tử Reactor mà filter đã gắn. Điều này ảnh hưởng đến:

| Vị trí | URL nhìn thấy | Ý nghĩa đo lường |
|---|---|---|
| Trước LoadBalancer | URL logic chứa service ID | Có thể quan sát lựa chọn LoadBalancer và network I/O sau đó |
| Sau LoadBalancer | URL đã được resolve sang host/port | Có thể đo transport của một attempt, tùy vị trí retry |
| Bao bên ngoài auth filter | Request đã được gắn token ở bước downstream | Có thể bao gồm thời gian lấy token nếu auth filter gọi network |
| Bên trong auth filter | Request thường đã có thông tin xác thực | Không nhất thiết tính thời gian xin token |

Trình tự thực tế còn có thể bao gồm filter do Spring Boot, observability hoặc framework khác đăng ký. Không nên giả định thứ tự tối ưu chỉ từ thứ tự trong đoạn code; hãy xác minh bằng test integration hoặc logging được kiểm soát.

## 7. Viết filter truyền Correlation ID đúng với Reactor Context

Đối với WebClient, không nên mặc định lấy `MDC.get("correlationId")` để truyền request context. MDC thường gắn với ThreadLocal trong khi các signal của Reactor có thể chạy trên nhiều thread khác nhau. Reactor `Context` được truyền theo subscriber và là lựa chọn phù hợp cho context bất đồng bộ.

Ví dụ filter:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import reactor.core.publisher.Mono;

@Bean
ExchangeFilterFunction correlationIdFilter() {
    return (request, next) -> Mono.deferContextual(context -> {
        String correlationId =
                context.getOrDefault("correlationId", "");

        ClientRequest updated = ClientRequest.from(request)
                .headers(headers -> {
                    if (!correlationId.isBlank()) {
                        headers.set(
                                "X-Correlation-Id",
                                correlationId
                        );
                    }
                })
                .build();

        return next.exchange(updated);
    });
}
~~~

Cách gọi:

~~~java
public Mono<InventoryResponse> getInventory(
        String sku,
        String correlationId) {

    return inventoryWebClient.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResponse.class)
            .contextWrite(context ->
                    context.put("correlationId", correlationId)
            );
}
~~~

Trong ví dụ này, filter được thực thi trong subscription có `Context` chứa key `correlationId`. `Mono.deferContextual(...)` giúp đọc giá trị **tại thời điểm subscribe**, tránh chụp context quá sớm ở thời điểm assemble.

Các nguyên tắc cần giữ:

1. Chỉ truyền correlation ID đã được kiểm tra/chuẩn hóa ở boundary đáng tin cậy.
2. Không tự tạo ID mới ở mỗi lần retry nếu mục tiêu là nối các attempt về cùng một logical request.
3. Không xem `X-Correlation-Id` là bằng chứng xác thực hoặc quyền truy cập.
4. Không sao chép tất cả inbound headers sang outbound.
5. Nếu đã bật Micrometer Tracing/OpenTelemetry, để instrumentation phụ trách `traceparent` và các trace headers chuẩn.

Nếu filter không nhìn thấy key, hãy kiểm tra thứ tự `contextWrite`, các publisher trung gian và vị trí subscriber. `Context` truyền theo subscription chứ không phải một biến global dùng chung cho mọi request.

## 8. Filter xác thực bất đồng bộ, không block event loop

Nếu `inventory-service` cần Bearer token, filter có thể gọi một token provider trả về `Mono<String>`. Hãy sử dụng OAuth2 client hoặc cơ chế workload identity phù hợp với kiến trúc của hệ thống, không nhúng token vào source code.

Ví dụ interface dùng cho lab:

~~~java
public interface InventoryTokenProvider {
    Mono<String> accessToken();
}
~~~

Filter:

~~~java
@Bean
ExchangeFilterFunction inventoryAuthenticationFilter(
        InventoryTokenProvider tokenProvider) {

    return (request, next) ->
            tokenProvider.accessToken()
                    .flatMap(token -> {
                        ClientRequest authorized =
                                ClientRequest.from(request)
                                        .headers(headers ->
                                                headers.setBearerAuth(token)
                                        )
                                        .build();

                        return next.exchange(authorized);
                    });
}
~~~

Đây là mô hình **reactive token provider**: implementation phải tự quản lý cấp token, cache, thời hạn và lỗi của authorization server. Trong hệ thống thực, có thể dùng `ReactiveOAuth2AuthorizedClientManager` cùng cấu hình `client_credentials` thích hợp; đừng giả định một manager blocking sẽ an toàn khi gọi trực tiếp trên event loop.

Nếu cần gọi HTTP xin token, nên thực hiện một cách bất đồng bộ qua client **không mang filter inventory load balancing** trừ khi token endpoint cũng là dịch vụ được thiết kế để discovery. Tránh tạo dependency vòng khiến inventory WebClient cần token từ một WebClient lại cần chính token đó.

### Không để Bearer token rò rỉ sang dịch vụ khác

Gắn filter xác thực vào WebClient chỉ dành cho `inventory-service` hoặc dùng policy chọn credential theo đích đã được xác thực. Nếu một WebClient có base URL động, token filter không phân biệt đích có thể gửi token inventory sang một hostname không được phép nhận.

Một thiết kế dễ kiểm soát là:

~~~text
inventoryWebClient:
    correlationFilter -> inventoryAuthFilter -> lbFilter

paymentWebClient:
    correlationFilter -> paymentAuthFilter -> lbFilter

publicExternalWebClient:
    correlationFilter -> (không gắn internal service token)
~~~

Không dùng `ClientRequest.url()` thiếu kiểm tra để tin một hostname do người dùng nhập. Với URL động, cần có allowlist, chặn SSRF và quyết định token ở ranh giới application, không chỉ ở filter.

## 9. Logging filter: phân biệt response HTTP và tín hiệu lỗi

Một filter ghi nhận thời gian có thể dùng `Mono.defer` để bắt đầu đo tại subscription:

~~~java
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import reactor.core.publisher.Mono;

private static final Logger LOG =
        LoggerFactory.getLogger("outbound.inventory");

@Bean
ExchangeFilterFunction safeOutboundLoggingFilter() {

    return (request, next) -> Mono.defer(() -> {
        long started = System.nanoTime();
        String method = request.method().name();
        String host = request.url().getHost();

        return next.exchange(request)
                .doOnNext(response -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started
                    );

                    LOG.info(
                            "outbound_http method={} targetHost={} status={} elapsedMs={}",
                            method,
                            host,
                            response.statusCode().value(),
                            elapsedMs
                    );
                })
                .doOnError(error -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started
                    );

                    LOG.warn(
                            "outbound_http_failed method={} targetHost={} errorType={} elapsedMs={}",
                            method,
                            host,
                            error.getClass().getSimpleName(),
                            elapsedMs
                    );
                });
    });
}
~~~

Đây là một `@Bean` factory method minh họa trong `@Configuration` class; `LOG` phải là static field của class chứa bean.

Cần hiểu:

- Một response HTTP 500 hoặc 503 thường vẫn là **ClientResponse** bình thường ở tầng `ExchangeFilterFunction`; nó không nhất thiết kích hoạt `doOnError` ngay tại đây.
- `retrieve()` về sau mới chuyển status 4xx/5xx thành `WebClientResponseException` theo mặc định nếu caller muốn giải mã body.
- Lỗi kết nối, DNS, timeout hoặc exception trong filter có thể đi vào `doOnError`.
- Cancellation có thể không tạo `doOnNext` hoặc `doOnError`; nếu cần đo mọi kết thúc, dùng `doFinally` và phân biệt `SignalType`.
- Không đọc response body trong logging filter trừ khi hiểu rõ cơ chế tiêu thụ `DataBuffer`, replay, backpressure và chi phí bộ nhớ.

Không log toàn bộ URL query, request body, `Authorization`, cookies hoặc token. Đặt tên metric/label theo route template nếu có thể để tránh cardinality quá lớn.

## 10. LoadBalancer filter, health check và policy chọn instance

`ReactorLoadBalancerExchangeFilterFunction` không chứa toàn bộ logic discovery/health check bên trong. Nó ủy quyền chọn instance cho Spring Cloud LoadBalancer. Chuỗi xử lý có thể là:

~~~mermaid
flowchart LR
    A["ServiceInstance supplier từ Discovery"] --> B["Cache (nếu bật)"]
    B --> C["Health / zone / hint filtering"]
    C --> D["Candidate ServiceInstances"]
    D --> E["Round Robin / Random / custom ReactorLoadBalancer"]
    E --> F["ReactorLoadBalancerExchangeFilterFunction"]
    F --> G["HTTP connector"]
~~~

Nếu `ServiceInstanceListSupplier` chỉ trả về một instance, WebClient sẽ luôn dùng instance đó bất kể thuật toán Round Robin hay Random. Nếu tất cả instance bị bộ lọc loại bỏ, cách phản hồi sẽ phụ thuộc vào cơ chế fallback của supplier và filter.

Đừng nhầm ba loại filter:

| Thành phần | Input | Nhiệm vụ |
|---|---|---|
| `ExchangeFilterFunction` | `ClientRequest`/`ClientResponse` | Can thiệp HTTP request/response của WebClient |
| `ServiceInstanceListSupplier` | Service ID và yêu cầu LoadBalancer | Cung cấp/lọc danh sách instance ứng viên |
| `ReactorLoadBalancer<ServiceInstance>` | Danh sách instance và request selection | Chọn một instance từ tập ứng viên |

Ví dụ `HealthCheckServiceInstanceListSupplier` là **supplier**, không phải một WebClient `ExchangeFilterFunction` do bạn gắn trực tiếp vào `WebClient.Builder`.

Zone, hint, weighted selection và retry-aware supplier cũng thuộc cơ chế lựa chọn của Spring Cloud, không phải các HTTP filter có thể đổi chỗ tùy ý trong WebClient.

## 11. Retry: một lần gọi logic có thể chọn instance nhiều lần

WebClient trả publisher. Với request thông thường, mỗi lần subscribe hoặc re-subscribe có thể bắt đầu một lần trao đổi HTTP mới, bao gồm cả việc chọn instance. Ví dụ:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.util.retry.Retry;

public Mono<InventoryResponse> findStockWithBoundedRetry(String sku) {
    return inventoryWebClient.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResponse.class)
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(150))
                            .filter(error ->
                                    error instanceof WebClientRequestException
                            )
            );
}
~~~

Hai lần retry nghĩa là tối đa ba attempts (lần đầu và hai lần thử lại) nếu các lỗi liên tiếp thuộc loại được filter chấp nhận. Ví dụ này chỉ retry `WebClientRequestException`; nó **không tự retry response 503** được `retrieve()` chuyển thành `WebClientResponseException`.

Lưu ý:

- Lần retry có thể chọn lại **cùng instance vừa lỗi** nếu không có cơ chế retry-aware/avoid-previous-instance phù hợp.
- Nếu Spring Cloud LoadBalancer cũng bật retry nội bộ, thêm `retryWhen` ở WebClient có thể dẫn đến retry nhiều tầng, số request tăng hơn dự kiến.
- Retry POST/PUT nghiệp vụ có side effects cần chính sách idempotency và deadline; không tùy tiện áp dụng ví dụ GET cho thanh toán.
- Token acquisition filter có thể chạy lại khi publisher được subscribe lại. Token provider cần cache và hạn chế request xin token trùng lặp.
- Việc resubscribe request body dạng streaming chưa chắc an toàn; phải bảo đảm payload replayable trước khi retry.

Ví dụ chỉ minh họa phạm vi retry. Trong production, nên có error classification, tổng deadline, backoff/jitter và metrics phân biệt logical request với HTTP attempts.

## 12. Timeout ở đâu khi request đi qua nhiều filter?

Trong WebClient dùng Reactor Netty, có thể thiết lập connect timeout và response timeout trên HTTP transport:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
        .responseTimeout(Duration.ofSeconds(2));

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .filter(lbFunction)
        .baseUrl("http://inventory-service")
        .build();
~~~

Ở đây `lbFunction` là bean `ReactorLoadBalancerExchangeFilterFunction` do Spring Cloud cung cấp. Đây là snippet độc lập, không dùng `@LoadBalanced` cùng lúc. Trong ứng dụng Spring Boot có sẵn `WebClient.Builder`, nên tích hợp connector qua builder/customizer của Boot khi muốn giữ observation/tracing customization.

Cần phân biệt:

- **Connect timeout**: chờ thiết lập kết nối TCP.
- **Response timeout**: chờ response theo semantics của Reactor Netty.
- **Reactive `Mono.timeout(...)`**: thời hạn tối đa cho publisher tại vị trí đặt toán tử; có thể bao gồm filter, chọn instance, token và các lần retry nếu đặt đúng chỗ.
- **Discovery timeout**: giới hạn khi truy xuất danh sách instance nếu cơ chế discovery hỗ trợ.

Ví dụ muốn giới hạn toàn bộ publisher ở 3 giây:

~~~java
return inventoryWebClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResponse.class)
        .timeout(Duration.ofSeconds(3));
~~~

Nếu có `retryWhen`, thứ tự đặt `timeout` so với `retryWhen` làm thay đổi việc giới hạn mỗi attempt hay tổng các attempt. Muốn tổng deadline, đặt toán tử thời hạn bao trọn toàn bộ chuỗi retry và kiểm thử theo timing thực tế.

## 13. Thực hành: hai replica inventory và WebClient dùng LoadBalancer

Để quan sát filter chain thực tế, xây dựng lab đơn giản:

~~~text
order-service :8080
  |
  | WebClient "http://inventory-service/whoami"
  v
Spring Cloud LoadBalancer
  |
  +--- inventory instance 1 :8081
  |
  +--- inventory instance 2 :8082
~~~

Ở caller, dùng `SimpleDiscoveryClient`:

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

Ở inventory-service, thêm endpoint trả về cổng hiện tại:

~~~java
import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InstanceController {

    private final Environment environment;

    public InstanceController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/whoami")
    public Map<String, String> whoAmI() {
        return Map.of(
                "instance", "inventory:" +
                        environment.getProperty("server.port", "unknown")
        );
    }
}
~~~

Chạy hai tiến trình inventory cùng mã nguồn trên cổng 8081 và 8082 bằng `--server.port=8081` và `--server.port=8082`. Gọi trực tiếp `http://localhost:8081/whoami` và `http://localhost:8082/whoami` trước để chắc hai backend hoạt động.

Ở caller, định nghĩa WebClient một trong hai cách ở trên. Controller reactive minh họa:

~~~java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
public class InventoryProxyController {

    private final WebClient inventoryWebClient;

    public InventoryProxyController(WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    @GetMapping("/proxy/whoami")
    public Mono<Map> proxyWhoAmI() {
        return inventoryWebClient.get()
                .uri("/whoami")
                .retrieve()
                .bodyToMono(Map.class);
    }
}
~~~

Controller ở trên chỉ phù hợp làm lab; trong code production, dùng DTO có kiểu rõ ràng thay vì `Map` raw.

PowerShell gửi 20 lần:

~~~powershell
1..20 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/proxy/whoami"
}
~~~

Nếu instance list ổn định và dùng Round Robin, sẽ thường thấy cổng 8081 và 8082 luân phiên theo số lượt chọn; thứ tự/độ đều thực tế có thể bị ảnh hưởng bởi concurrency, retry hoặc caching. Nếu cấu hình Random, có thể thấy cùng một cổng lặp lại liên tiếp.

### Quan sát logical URL và physical URL

Khi dùng cách gắn filter thủ công, thêm hai filter log ở hai phía `lbFunction`:

~~~java
@Bean
ExchangeFilterFunction logicalUrlLog() {
    return (request, next) -> {
        // Chỉ dùng để chẩn đoán, không log query chứa dữ liệu nhạy cảm.
        System.out.println("logical host = " + request.url().getHost());
        return next.exchange(request);
    };
}

@Bean
ExchangeFilterFunction physicalUrlLog() {
    return (request, next) -> {
        System.out.println("physical host = " + request.url().getHost()
                + ":" + request.url().getPort());
        return next.exchange(request);
    };
}
~~~

Gắn theo thứ tự:

~~~java
builder
    .filter(logicalUrlLog)
    .filter(lbFunction)
    .filter(physicalUrlLog);
~~~

Kỳ vọng logical filter nhìn thấy `inventory-service`; filter sau LoadBalancer có thể nhìn thấy `localhost:8081` hoặc `localhost:8082`. **Đây là cách chẩn đoán dành cho lab**, không phải bằng chứng duy nhất của thuật toán: nên đối chiếu backend access log và Spring Cloud lifecycle metrics nếu cần theo dõi production.

## 14. Kiểm thử filter chain không phụ thuộc may rủi phân phối

Một test dễ sai là mong mọi cặp request luôn đi đúng hai replica khác nhau. Với Random, điều đó không được bảo đảm; với Round Robin, concurrency và retry có thể làm thứ tự không giống test mong đợi.

Nên có hai tầng kiểm thử:

**Unit test filter thuần túy:** truyền một `ExchangeFunction` giả cho correlation/auth/logging filter. Xác nhận filter thêm đúng headers, không sửa URL sai, không để lộ token, trả `ClientResponse` đúng và propagate lỗi/cancellation. Không cần khởi động registry.

**Integration test LoadBalancer:** chạy hai backend thử nghiệm và Spring context có `SimpleDiscoveryClient`, bảo đảm một request gọi bằng service ID được giải quyết thành host/port vật lý và nhận response từ backend. Dùng `StepVerifier` hoặc `WebTestClient` để subscribe publisher. Có thể đo nhiều request để kiểm tra phân phối mà không bắt buộc thứ tự cố định.

Một cách kiểm thử lỗi no-instance:

1. Cấu hình service ID `missing-service` không có instance.
2. Dùng WebClient đã load-balanced gọi `http://missing-service/whoami`.
3. Kiểm tra kết quả không phải 200 thành công; thông thường là lỗi tương ứng `503` sau `retrieve()`.
4. Xác nhận log không chứa token và error handler trả message nghiệp vụ phù hợp.

Nếu response body là stream, hãy kiểm tra việc release `DataBuffer` trong filter custom; đọc body để log hoặc bỏ qua `ClientResponse` mà không giải phóng tài nguyên có thể làm rò rỉ bộ nhớ/connection pool.

## 15. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `UnknownHostException: inventory-service` | Dùng WebClient thường, chưa gắn LoadBalancer filter | Kiểm tra bean builder được inject, `@LoadBalanced` hoặc `.filter(lbFunction)` |
| HTTP 503 từ service ID | Không có instance đủ điều kiện hoặc backend lỗi | Kiểm tra discovery, health supplier và status thực tế |
| Một request được log hai lần | Đăng ký nhiều logging filter hoặc retry ở nhiều tầng | Kiểm tra thứ tự filter và số attempts |
| LoadBalancer bị gọi trùng | Đã gắn thủ công lbFunction vào builder có `@LoadBalanced` | Chọn một trong hai cách tích hợp |
| Log chỉ nhìn service ID, không thấy replica | Logging filter đứng trước LoadBalancer | Đặt filter chẩn đoán sau lbFunction hoặc dùng backend log/lifecycle |
| Filter lấy correlation ID rỗng | Dùng MDC ThreadLocal hoặc thiếu Reactor Context | Kiểm tra `contextWrite` và `deferContextual` |
| Token bị gửi sai service | Dùng token filter trên WebClient gọi nhiều hostname | Dùng client theo downstream và allowlist đích |
| 500 không vào `doOnError` của logging filter | 500 là `ClientResponse` tại tầng filter | Kiểm tra `response.statusCode()` ở `doOnNext` |
| `block()` gây tắc nghẽn | Gọi blocking trong event loop | Giữ filter và token provider reactive |
| `retryWhen` không chuyển instance | Không có retry-aware routing hoặc vẫn chọn ngẫu nhiên cùng backend | Kiểm tra cơ chế retry/avoid-previous và supplier |
| Một logical request có nhiều HTTP attempts | Retry nội bộ và retryWhen chồng nhau | Đặt budget chung và phân biệt metrics |
| Đổi timeout nhưng request vẫn chờ dài | Timeout đặt ở transport khác với toàn pipeline | Đặt deadline tổng phù hợp, kiểm tra thứ tự retry/timeout |
| Không có trace dù WebClient hoạt động | Builder tự tạo bỏ qua instrumentation | Dùng Boot-managed builder/observation customization |

## 16. Checklist đưa vào môi trường thực

- [ ] Xác định WebClient đang dùng **service ID** hay hostname DNS/VIP thông thường.
- [ ] Nếu cần client-side load balancing, có `spring-cloud-starter-loadbalancer` và nguồn `ServiceInstance`.
- [ ] Dùng `@LoadBalanced WebClient.Builder` **hoặc** gắn `ReactorLoadBalancerExchangeFilterFunction` thủ công; tránh gắn cả hai.
- [ ] Chỉ dùng custom filter cho HTTP request/response; cấu hình supplier/strategy ở tầng Spring Cloud LoadBalancer.
- [ ] Đăng ký filter theo thứ tự có chủ đích và kiểm chứng logical URL/physical URL nếu cần.
- [ ] Dùng Reactor Context hoặc tracing instrumentation thay vì chỉ dựa vào ThreadLocal MDC.
- [ ] Token filter bất đồng bộ, không `block()` trên event loop; giới hạn token đúng đích.
- [ ] Không log bearer token, raw body, cookies, toàn bộ URI/query hoặc dữ liệu nhạy cảm.
- [ ] Phân biệt HTTP 4xx/5xx với reactive onError ở tầng filter.
- [ ] Giới hạn tổng retry và timeout; cân nhắc idempotency cho thao tác ghi.
- [ ] Đối chiếu health check/discovery khi xuất hiện 503 hoặc phân phối lệch.
- [ ] Dùng Boot-managed builder khi cần Micrometer Observation/tracing.
- [ ] Unit test filter độc lập và integration test qua ít nhất hai replica.
- [ ] Kiểm tra cancellation, response body resources và connection pool khi triển khai filter custom.

## Tài liệu tham khảo

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): tích hợp `@LoadBalanced WebClient.Builder`, reactive filter, supplier, selection và retry.
- [Spring Framework — WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): `ExchangeFilterFunction`, `ClientRequest`, `ClientResponse` và trách nhiệm xử lý body.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): HTTP client reactive, status, request body và codecs.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): instrumentation/tracing từ Spring-managed WebClient builders.

**Kết luận:** `ReactorLoadBalancerExchangeFilterFunction` là cầu nối giữa **WebClient filter chain** và **Spring Cloud LoadBalancer**. Nó lấy service ID từ URI logic, nhờ LoadBalancer chọn một `ServiceInstance`, rồi đưa request đã resolve đến HTTP connector. Đặt filter đúng thứ tự giúp xác thực, truyền context và ghi nhận hoạt động nhất quán; đồng thời tách bạch rõ việc chọn instance với retry, timeout, health check và observability trong luồng reactive.
