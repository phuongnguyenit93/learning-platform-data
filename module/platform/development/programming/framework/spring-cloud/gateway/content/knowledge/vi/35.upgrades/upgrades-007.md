# Chuyển giữa Server WebFlux và Server Web MVC theo ma trận tính năng

Spring Cloud Gateway cung cấp hai cách triển khai Gateway Server: **WebFlux** và **Web MVC**. Cả hai đều có thể làm cổng vào cho microservices, khớp route theo request, biến đổi path/header, chuyển tiếp HTTP và tích hợp các cơ chế như load balancing, security, circuit breaker và retry. Tuy nhiên, hai lựa chọn dựa trên mô hình web khác nhau, có API mở rộng, client proxy và một số tính năng chuyên biệt khác nhau.

Với module **SPRING_CLOUD_GATEWAY**, việc chuyển stack cần bắt đầu từ yêu cầu vận hành thực tế: ứng dụng cần reactive end-to-end, route tự sinh từ service registry, loại rate limiter nào, filter tùy chỉnh đang dùng API nào, hay cần tương thích với Servlet container và thư viện MVC hiện hữu. Chỉ đổi starter và prefix YAML không đủ để bảo đảm hành vi tương đương.

## Xác định đúng loại Gateway Server

Bài này nói về **Gateway Server**, tức thành phần nhận request từ client, chọn route và proxy request đến upstream. Spring Cloud Gateway còn có biến thể ProxyExchange để một controller gọi proxy qua đối tượng `ProxyExchange`; đây là cách tích hợp khác và không phải đối tượng so sánh trong bài.

### Server WebFlux

Gateway Server WebFlux được xây dựng trên Spring WebFlux, Project Reactor và runtime Netty. Request được biểu diễn bằng `ServerWebExchange`; filter theo route dùng `GatewayFilter`, còn filter áp dụng có điều kiện trên nhiều route có thể dùng `GlobalFilter`. Chuỗi xử lý có thể bất đồng bộ và non-blocking khi toàn bộ thành phần tham gia đều dùng API non-blocking.

Lựa chọn này phù hợp khi Gateway cần xử lý nhiều kết nối đồng thời, dùng reactive client/data access, hoặc dựa vào các extension reactive của Spring Cloud Gateway. Gateway Server WebFlux yêu cầu runtime Netty của Spring Boot và không chạy trong Servlet container truyền thống hoặc đóng gói WAR. Gọi API blocking từ event-loop có thể làm nghẽn xử lý; nếu phải tích hợp thư viện blocking, cần cô lập và đánh giá tác động bằng tải thực tế.

### Server Web MVC

Gateway Server Web MVC dựa trên Spring MVC và API `WebMvc.fn`. Route được biểu diễn bằng `RouterFunction`, handler proxy dùng `HandlerFunction`, predicate dùng `RequestPredicate`, còn filter dùng `HandlerFilterFunction`. Các filter có thể được tổ chức thành bước `before`, `after` hoặc nhóm nâng cao cần xử lý cả request và response.

Lựa chọn này phù hợp với ứng dụng Servlet, Spring MVC, Servlet Filter và các thư viện đồng bộ hiện hữu. Gateway Server Web MVC chạy trên các Servlet runtime như Tomcat và Jetty. Phần proxy backend sử dụng hạ tầng `RestClient` của Spring Boot, do đó cấu hình timeout, TLS và quan sát HTTP client theo mô hình của Spring Boot.

## Ma trận tính năng và khác biệt cần đánh giá

Bảng dưới đây mô tả các khả năng ở mức Gateway Server trong các tài liệu Spring Cloud Gateway hiện hành. “Có” nghĩa là có cơ chế được tài liệu hóa; không có nghĩa API, property hoặc hành vi runtime giống nhau. Luôn kiểm tra đúng phiên bản Spring Boot và Spring Cloud Release Train của dự án trước khi chốt thiết kế.

| Tiêu chí | Server WebFlux | Server Web MVC | Tác động khi chuyển |
|---|---|---|---|
| Runtime | Spring WebFlux, Reactor, Netty | Spring MVC, Servlet API; Tomcat/Jetty | Phải đổi web stack và đánh giá cách xử lý I/O, thread, timeout |
| Route model | `Route`, `RouteLocator`, `ServerWebExchange` | `RouterFunction`, `HandlerFunction`, `ServerRequest`/`ServerResponse` | Java route và custom predicate/filter không dùng chung trực tiếp |
| Predicate phổ biến | Path, Method, Host, Header, Cookie, Query, thời gian, weight và các predicate Gateway khác | Tái sử dụng predicate của WebMvc.fn và các `GatewayRequestPredicates`; có Path, Method, Host, Header, Cookie, Query, thời gian, weight cùng các khả năng theo phiên bản | Kiểm tra predicate cụ thể, quy tắc path và kiểu dữ liệu; không chỉ so tên YAML |
| Filter mở rộng | `GatewayFilter`, `GlobalFilter`, reactive `Mono` và `GatewayFilterChain` | `HandlerFilterFunction`, `BeforeFilterFunctions`, `AfterFilterFunctions`, các nhóm filter nâng cao | Viết lại custom filter, xử lý thứ tự trước/sau và cách truy cập request/response |
| Route từ service registry | Có `DiscoveryClient RouteDefinitionLocator` để tự tạo route từ dịch vụ đăng ký | Có `lb://serviceId`/LoadBalancer cho route khai báo; tài liệu Server Web MVC không mô tả locator tự sinh route tương đương WebFlux | Nếu đang phụ thuộc route tự sinh, cần thiết kế nguồn route riêng trước khi chuyển MVC |
| Load balancing | `lb://serviceId` qua reactive load balancer | `lb://serviceId` hoặc `lb()` trong Java DSL qua Spring Cloud LoadBalancer | Cả hai cần dependency LoadBalancer; kiểm tra thứ tự filter nếu tự cấu hình Java DSL |
| Rate limiting | `RequestRateLimiter`; Redis RateLimiter dùng token bucket và Redis reactive starter | `RateLimiter` dựa trên Bucket4j; `keyResolver` được cấu hình qua Java DSL | Phải chuyển thuật toán, key, backend lưu trạng thái và cách cấu hình; không sao chép nguyên YAML |
| Circuit breaker / retry | Gateway filter trên chuỗi reactive | `CircuitBreakerFilterFunctions` và `RetryFilterFunctions` trong WebMvc.fn | Kiểm tra fallback, exception, thứ tự filter và tính idempotent của request |
| WebSocket | Có WebSocket routing trên WebFlux/Netty | Có proxy WebSocket; cần `spring-boot-starter-websocket` | MVC không relay ping frame như ứng dụng nhận được; retry, circuit breaker và filter xử lý body không áp dụng sau khi kết nối đã thiết lập |
| Security | Spring Security reactive, `SecurityWebFilterChain` và tích hợp token relay phù hợp | Spring Security Servlet, `SecurityFilterChain`, OAuth2 client/resource server | Viết lại cấu hình security theo đúng stack; kiểm tra JWT, session, CORS và token relay |
| TLS tới upstream | Cấu hình HTTP client Reactor Netty dưới `spring.cloud.gateway.server.webflux.httpclient.ssl.*` | Dùng Spring Boot `RestClient`, `spring.http.client` và `spring.ssl.bundle` | Chuyển trust store, SSL bundle, timeout và kiểm thử chứng thư theo client mới |
| Observability | Có Gateway metrics filter với metric route như `spring.cloud.gateway.requests` và tag routeId/routeUri | Dùng quan sát HTTP server của Spring MVC và HTTP client `RestClient`; không giả định metric/tag Gateway giống WebFlux | Cập nhật dashboard, alert và tracing; bổ sung route tag nếu nghiệp vụ yêu cầu |
| Servlet Filter | Không dùng Servlet Filter làm extension point của Gateway reactive | Có thể tích hợp Servlet Filter; phải chú ý thứ tự với `FormFilter` | Rà soát filter đọc body/parameter, đặc biệt request `application/x-www-form-urlencoded` |

## Chọn stack theo yêu cầu vận hành

Ưu tiên **WebFlux** nếu một hoặc nhiều yêu cầu sau là bắt buộc:

- Ứng dụng cần reactive end-to-end và các lời gọi upstream dùng non-blocking I/O.
- Cần `GlobalFilter`/`GatewayFilter` hiện có hoặc các extension phụ thuộc `ServerWebExchange` và Reactor.
- Cần `DiscoveryClient RouteDefinitionLocator` để tự tạo route từ Eureka, Consul, Zookeeper hoặc registry tương thích.
- Cần `RequestRateLimiter` với Redis RateLimiter và cách quản lý quota hiện tại.
- Hệ thống có WebSocket routing và cần các khả năng của WebFlux/Netty như proxy ping frame.

Ưu tiên **Web MVC** nếu:

- Gateway là một phần của ứng dụng Spring MVC/Servlet và cần dùng chung Servlet Filter, Spring Security Servlet hoặc thư viện đồng bộ.
- Hạ tầng triển khai tiêu chuẩn hóa trên Tomcat/Jetty hoặc có yêu cầu tương thích Servlet.
- Đội phát triển muốn mở rộng route qua `RouterFunction`, `RequestPredicate` và `HandlerFilterFunction`.
- Nhu cầu rate limit phù hợp với Bucket4j và nhóm vận hành chấp nhận cấu hình key resolver trong Java DSL.
- Các route có thể khai báo rõ ràng hoặc dự án sẵn sàng tự quản lý bước tạo route từ service registry.

Không chọn WebFlux chỉ vì kỳ vọng hiệu năng cao hơn, cũng không chọn Web MVC chỉ vì ứng dụng hiện có một dependency MVC. Hãy đo tải với số kết nối đồng thời, thời gian upstream, kích thước request body, mức độ blocking và giới hạn thread của môi trường triển khai. Kết quả phụ thuộc vào toàn bộ chuỗi xử lý, không chỉ framework nhận request.

## Những khác biệt có thể làm thay đổi hành vi

### Route discovery và load balancing

WebFlux có thể bật route locator dựa trên `DiscoveryClient`. Mặc định, Gateway tạo route có path dạng `/{serviceId}/**`, dùng URI `lb://serviceId` và rewrite path để bỏ service ID trước khi gửi tới upstream. Khi tự thay danh sách filter của discovery locator, phải khai báo lại `RewritePath` mặc định nếu vẫn muốn bỏ service ID khỏi path.

Web MVC hỗ trợ load balancing cho route đã khai báo bằng URI `lb://serviceId` hoặc filter `lb()` trong Java DSL. Điều này giải quyết việc chọn instance của một route; không đồng nghĩa với cơ chế tự phát hiện và sinh route từ mọi service trong registry. Nếu hệ thống hiện đang phụ thuộc route tự sinh, cần tạo route từ nguồn quản lý riêng hoặc giữ WebFlux cho yêu cầu đó.

Ví dụ route tĩnh dùng được theo cấu trúc tương ứng của cả hai stack:

```yaml
# WebFlux: spring.cloud.gateway.server.webflux.routes
# Web MVC: spring.cloud.gateway.server.webmvc.routes
spring:
  cloud:
    gateway:
      server:
        webflux: # đổi thành webmvc khi dùng Server Web MVC
          routes:
            - id: orders-api
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
```

Ví dụ này chỉ minh họa route tĩnh và load balancing. Đối với Web MVC, route được phân giải bằng LoadBalancer filter; nếu viết Java DSL và tự gọi `lb()`, đặt nó sau filter thay đổi path như `setPath()` hoặc `stripPrefix()` để URI được phân giải đúng. Khi dùng cấu hình `lb://`, Gateway tự sắp xếp filter scheme tương ứng.

### Rate limiting

Hai stack có cơ chế rate limiting khác nhau. WebFlux dùng `RequestRateLimiter`; Redis RateLimiter dùng thuật toán token bucket với `replenishRate`, `burstCapacity` và `requestedTokens`, cần `spring-boot-starter-data-redis-reactive`. Ví dụ:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: public-api
              uri: lb://public-api
              predicates:
                - Path=/api/public/**
              filters:
                - name: RequestRateLimiter
                  args:
                    redis-rate-limiter.replenishRate: 10
                    redis-rate-limiter.burstCapacity: 20
                    redis-rate-limiter.requestedTokens: 1
```

Web MVC có `RateLimiter` dựa trên Bucket4j. Key resolver là một `Function<ServerRequest, String>` và tài liệu hiện hành yêu cầu cấu hình key resolver qua Java DSL. Ví dụ:

```java
@Bean
RouterFunction<ServerResponse> limitedRoute() {
    return route("limited-api")
        .GET("/api/public/**", http())
        .before(uri("https://public-api.internal"))
        .filter(rateLimit(config -> config
            .setCapacity(100)
            .setPeriod(Duration.ofMinutes(1))
            .setKeyResolver(request -> {
                var principal = request.servletRequest().getUserPrincipal();
                return principal == null ? "anonymous" : principal.getName();
            })))
        .build();
}
```

Ví dụ minh họa cấu hình key theo principal; chính sách cho request chưa xác thực cần được thiết kế rõ ràng. Trong production, chọn backend phân tán phù hợp để các instance Gateway dùng chung bucket; cache cục bộ chỉ phù hợp cho kiểm thử hoặc giới hạn theo từng instance. Khi chuyển stack, kiểm tra lại quota, burst, thời gian refill, mã 429/403 khi thiếu key và tính nhất quán giữa nhiều pod.

### Filter tùy chỉnh và thứ tự thực thi

Trong WebFlux, custom filter nhận `ServerWebExchange` và `GatewayFilterChain`; logic bất đồng bộ thường trả về `Mono<Void>`. `GlobalFilter` được kết hợp với filter theo route và sắp xếp theo `Ordered`, ảnh hưởng cả pha trước và sau khi proxy.

Trong Web MVC, custom filter dựa trên `HandlerFilterFunction<ServerResponse, ServerResponse>`. Các thao tác chỉ sửa request có thể dùng `BeforeFilterFunctions`; thao tác chỉ sửa response có thể dùng `AfterFilterFunctions`; filter nâng cao xử lý cả hai pha được đặt trong nhóm riêng như circuit breaker, load balancer, retry và token relay. Route MVC cũng nằm trong `RouterFunction`, nên có thể kết hợp với các API WebMvc.fn.

Không chuyển một `GlobalFilter` sang Servlet Filter một cách máy móc. Servlet Filter chạy ở ranh giới Servlet chain, còn `HandlerFilterFunction` chạy trong chuỗi handler của route. Chọn đúng điểm mở rộng theo phạm vi cần áp dụng, sau đó kiểm thử thứ tự xác thực, ghi log, biến đổi header, rewrite path và xử lý response.

Nếu có Servlet Filter tự đọc request parameter, kiểm tra thứ tự so với `FormFilter` của Gateway MVC. Với `application/x-www-form-urlencoded`, Servlet container kết hợp form body với query parameters; `FormFilter` khôi phục form body cho upstream. Filter đọc parameter trước `FormFilter` cần được đặt đúng thứ tự theo tài liệu.

### WebSocket

Cả hai stack có thể proxy WebSocket. Với Web MVC, thêm `spring-boot-starter-websocket` và cấu hình route `ws://`/`wss://`, hoặc dùng URI HTTP/HTTPS/LB với request có header `Upgrade: websocket`. Sau handshake, MVC relay text, binary và pong; ping do Servlet WebSocket API xử lý tại container nên không được chuyển tiếp nguyên trạng. Filter tác động response body, retry và circuit breaker không áp dụng cho luồng message sau khi kết nối đã thiết lập. Nếu ứng dụng dựa vào heartbeat để giám sát backend, dùng heartbeat ở tầng ứng dụng.

Khi chuyển WebSocket, kiểm tra handshake, subprotocol, `Origin`, thời gian kết nối, idle timeout, reconnect và cách đóng kết nối. Kiểm thử riêng đường đi qua load balancer và ingress, không suy luận từ việc route HTTP thông thường hoạt động.

### TLS, security và quan sát

TLS inbound vẫn được cấu hình ở server của ứng dụng qua `server.ssl`. TLS outbound khác nhau: WebFlux dùng cấu hình HTTP client Reactor Netty; Web MVC dùng `RestClient` và Spring Boot SSL bundle, ví dụ `spring.http.client.ssl.bundle` kết hợp `spring.ssl.bundle`. Không mang nguyên các key `httpclient.ssl.*` của WebFlux sang MVC. Không dùng trust manager chấp nhận mọi chứng thư trong production.

Security cũng phải theo web stack. WebFlux dùng reactive security chain; Web MVC dùng Servlet `SecurityFilterChain`. Sau khi chuyển, xác nhận lại resource server JWT/opaque token, OAuth2 login, token relay, session, CSRF, CORS và các endpoint quản trị. Với MVC, Spring Security có `StrictHttpFirewall`; chỉ nới quy tắc URL khi downstream thực sự cần và đã đánh giá rủi ro.

WebFlux cung cấp Gateway metrics filter với thông tin như `routeId`, `routeUri`, status và HTTP method. Web MVC dựa trên quan sát HTTP server của Spring MVC và HTTP client `RestClient`. Nếu dashboard hiện tại lọc theo route ID hoặc dùng metric `spring.cloud.gateway.requests`, hãy lập danh sách metric/tag cần giữ, bổ sung instrumentation ở MVC nếu cần và cập nhật alert trước khi chuyển traffic.

## Đổi dependency và namespace cấu hình

Từ Spring Cloud 2025.0, tên starter thể hiện rõ web stack. Dùng Spring Cloud BOM tương thích với phiên bản Spring Boot của ứng dụng và chọn đúng một starter Gateway Server:

```xml
<!-- Gateway Server WebFlux -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
</dependency>

<!-- Hoặc Gateway Server Web MVC -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
```

Không thêm cả hai starter như một cách chuyển đổi tại runtime. Tạo cấu hình/build profile riêng nếu cần thử nghiệm hai biến thể, và xác nhận dependency tree không kéo nhầm web stack hoặc phiên bản Spring Cloud khác release train.

Trong Spring Cloud 2025.0 trở lên, prefix cấu hình tương ứng là:

| Stack | Prefix cấu hình |
|---|---|
| Server WebFlux | `spring.cloud.gateway.server.webflux.*` |
| Server Web MVC | `spring.cloud.gateway.server.webmvc.*` |

Ở các release train cũ hơn, prefix có thể là `spring.cloud.gateway.*` cho WebFlux và `spring.cloud.gateway.mvc.*` cho Web MVC. Đừng áp dụng prefix mới vào một phiên bản chưa hỗ trợ. `spring-boot-properties-migrator` có thể giúp phát hiện một số property cũ trong giai đoạn chuyển tiếp, nhưng vẫn phải cập nhật nguồn cấu hình và gỡ migrator sau khi hoàn tất.

## Lộ trình chuyển đổi an toàn

1. **Lập baseline**: ghi lại Spring Boot/Spring Cloud version, starter, runtime, route ID, predicate, filter, URI, discovery locator, LoadBalancer, rate limiter, security, TLS, WebSocket, metrics và trace.
2. **Đối chiếu ma trận tính năng**: đánh dấu tính năng bắt buộc, tính năng có thể thay thế và tính năng cần tự triển khai. Đặc biệt xác định route tự sinh từ DiscoveryClient, Redis rate limiter, GlobalFilter và custom filter.
3. **Tạo nhánh thử nghiệm**: cập nhật BOM và starter theo stack đích; chuyển prefix; loại dependency xung đột; giữ lại cấu hình baseline để so sánh.
4. **Chuyển route và filter**: giữ nguyên route ID, predicate, upstream và mục đích biến đổi. Viết lại custom filter/Java DSL theo API mới; thay đổi implementation rate limiter, discovery hoặc TLS khi cần.
5. **Kiểm thử chức năng**: kiểm tra route match, thứ tự route, path/header rewrite, query/body, status code, load balancing, discovery, fallback, retry, rate limit, security, TLS và WebSocket.
6. **Kiểm thử tải và lỗi**: tạo upstream chậm, lỗi kết nối, timeout và mất instance; đo throughput, p95/p99 latency, CPU, heap, thread, connection pool và tỷ lệ lỗi. Kiểm tra request body lớn khi retry/cache body.
7. **Triển khai canary**: gửi một phần traffic qua stack mới, so sánh status code, route được chọn, upstream, latency, metric và trace. Chỉ tăng traffic khi tiêu chí chấp nhận đạt.
8. **Chuẩn bị rollback**: giữ artifact, cấu hình và dashboard của stack cũ; ghi rõ cách chuyển traffic lại và cách đồng bộ route/config giữa các instance.

## Bộ kiểm thử tối thiểu sau khi chuyển

| Kịch bản | Điều cần xác nhận |
|---|---|
| Path, Host, Method, Header, Cookie và Query | Route đúng được chọn; route chồng lấn giữ đúng thứ tự |
| `StripPrefix`, `RewritePath`, `SetPath`, header filter | Upstream nhận path/header chính xác; response không lộ header nội bộ |
| `lb://orders-service` | Chọn được instance, xử lý đúng khi không còn instance và không gửi nhầm scheme |
| Discovery locator (nếu dùng) | Service mới được phát hiện, route sinh đúng và path service ID được rewrite |
| Rate limit | Quota theo user/API key, burst, reset, trạng thái phân tán và phản hồi khi vượt ngưỡng |
| Circuit breaker và retry | Fallback đúng; không retry thao tác không idempotent nếu không có bảo vệ; không tạo request lặp ngoài ý muốn |
| OAuth2/JWT và token relay | Xác thực, phân quyền, audience/scope và header token downstream đúng |
| HTTPS tới Gateway và upstream | Chứng thư, hostname verification, trust store, timeout và mTLS (nếu có) hoạt động |
| WebSocket | Handshake, Origin, subprotocol, heartbeat, reconnect và đóng kết nối |
| Metrics và tracing | Dashboard/alert có đủ route, status, latency và correlation ID sau khi đổi stack |

## Dấu hiệu chuyển đổi chưa hoàn tất

- Ứng dụng MVC khởi động được nhưng các route từng tự sinh từ DiscoveryClient biến mất.
- Rate limit vẫn trả 429 nhưng bucket không còn dùng chung giữa các instance.
- Filter ghi log hoặc xác thực chạy sai thứ tự sau khi chuyển từ `GlobalFilter` sang Servlet/handler filter.
- TLS tới upstream lỗi do cấu hình trust store cũ không còn được `RestClient` sử dụng.
- WebSocket handshake thành công nhưng heartbeat hoặc xử lý lỗi backend thay đổi.
- Dashboard không còn metric route ID, khiến cảnh báo theo upstream hoặc route không phát hiện được lỗi.

Khi gặp các dấu hiệu này, quay lại ma trận tính năng để xác định khác biệt nằm ở runtime, extension point, dependency hay cấu hình. Không đánh giá hoàn tất chỉ dựa trên việc ứng dụng build và health check trả về UP.

## Tài liệu tham khảo

- [Spring Cloud Gateway — tổng quan hai biến thể Server và Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/index.html)
- [How to Include Spring Cloud Gateway Server WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/starter.html)
- [How to Include Spring Cloud Gateway Server Web MVC](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/starter.html)
- [Server Web MVC — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/how-it-works.html)
- [Server Web MVC — Gateway Request Predicates](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/gateway-request-predicates.html)
- [Server Web MVC — Gateway Handler Filter Functions](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/gateway-handler-filter-functions.html)
- [Server Web MVC — RateLimiter Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/ratelimiter.html)
- [Server Web MVC — LoadBalancer Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/loadbalancer.html)
- [Server Web MVC — TLS and SSL](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/tls-and-ssl.html)
- [Server Web MVC — WebSockets](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/websockets.html)
- [Server WebFlux — DiscoveryClient Route Definition Locator](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/the-discoveryclient-route-definition-locator.html)
- [Spring Cloud 2025.0 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes)

Chuyển giữa WebFlux và Web MVC là thay đổi về runtime và mô hình mở rộng của Gateway. Hãy dùng ma trận để chốt các tính năng không thể mất, sau đó chuyển dependency, namespace, filter, discovery, rate limit, TLS và quan sát request theo từng bước. Một lần chuyển đổi chỉ hoàn tất khi request thực tế và hành vi khi lỗi tương đương yêu cầu vận hành của hệ thống.
