# So sánh Server WebFlux với Server Web MVC trong Spring Cloud Gateway

Spring Cloud Gateway là cổng vào cho hệ thống microservices: nhận request từ client, chọn đích đến bằng **route predicate**, biến đổi request/response qua **filter**, rồi chuyển tiếp tới dịch vụ phía sau. Khi xây dựng gateway, bạn có hai lựa chọn triển khai dạng **Server**: **Spring Cloud Gateway Server WebFlux** và **Spring Cloud Gateway Server Web MVC**. Chúng cùng giải quyết bài toán định tuyến, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request, nhưng khác nhau về nền tảng HTTP, cách viết mã mở rộng và cách vận hành.

> **Phạm vi phiên bản:** Các tên starter và tiền tố cấu hình trong ví dụ dưới đây theo dòng Spring Cloud Gateway **5.0.x** (Spring Cloud 2025.1, Spring Boot 4). Từ Spring Cloud 2025.0 / Gateway 4.3, dự án đã chuyển dần sang tên module và tiền tố `server.webflux` / `server.webmvc`. Với hệ thống 4.2 trở về trước, cần đối chiếu tài liệu đúng phiên bản trước khi sao chép cấu hình.

## 1. Hiểu đúng hai biến thể Server

- **Server WebFlux** được xây trên Spring WebFlux, Project Reactor và runtime **Reactor Netty**. Luồng xử lý hướng bất đồng bộ, không chặn (non-blocking), phù hợp khi gateway chủ yếu chờ I/O mạng và cần duy trì nhiều kết nối đồng thời.
- **Server Web MVC** được xây trên Spring MVC theo API hàm **WebMvc.fn** và chạy trong môi trường **Servlet** như Tomcat hoặc Jetty. Lập trình viên có thể tiếp tục sử dụng hệ sinh thái và mô hình lập trình Servlet quen thuộc.
- Cả hai đều là **gateway server** độc lập hoặc nhúng trong ứng dụng Spring Boot. Đừng nhầm chúng với biến thể **Proxy Exchange**: Proxy Exchange được sử dụng trong handler/controller có annotation, không phải đối tượng so sánh của bài này.

**Lựa chọn WebFlux hay Web MVC cho gateway không phụ thuộc vào công nghệ của microservice phía sau.** Gateway WebFlux hoàn toàn có thể gọi backend Spring MVC, Node.js hoặc Go; gateway Web MVC cũng có thể gọi backend WebFlux. Quyết định nằm ở cách chính gateway nhận, xử lý và chuyển tiếp lưu lượng.

## 2. Bảng so sánh nền tảng

| Tiêu chí | Server WebFlux | Server Web MVC |
|---|---|---|
| Nền tảng | Spring WebFlux + Reactor | Spring MVC + WebMvc.fn |
| Runtime HTTP phía server | Reactor Netty; không chạy như ứng dụng Servlet/WAR truyền thống | Servlet container, thường là Tomcat hoặc Jetty |
| Mô hình thực thi | Event loop và I/O non-blocking; tránh gọi blocking trên event loop | Request được xử lý theo mô hình Servlet; tác vụ đồng bộ thuận tiện hơn |
| Kiểu mở rộng route | `RouteLocator`, `RouteLocatorBuilder`, `RoutePredicateFactory`, `GatewayFilter`, `GlobalFilter` | `RouterFunction<ServerResponse>`, `RequestPredicate`, `HandlerFunction` và `HandlerFilterFunction`; các hàm `before`/`after` |
| Đối tượng request chủ đạo | `ServerWebExchange`, `Mono`, `Flux` | `ServerRequest`, `ServerResponse`, Servlet request |
| Filter pipeline | `FilteringWebHandler` phối hợp `GlobalFilter` với `GatewayFilter` theo route | WebMvc.fn router và các hàm xử lý trước/sau, filter trên `RouterFunction` |
| Giao tiếp downstream | Thông thường dùng HTTP client Reactor Netty | HTTP forwarding được thực hiện qua cơ chế handler của Server MVC |
| Thư viện đồng bộ cũ | Cần xem xét khả năng chặn I/O và thread scheduling | Tích hợp tự nhiên với nhiều thư viện Servlet/đồng bộ |
| Rate limiting tiêu biểu | `RequestRateLimiter` với Redis hoặc Bucket4j; key resolver kiểu reactive | `RateLimiter` dựa trên Bucket4j; key resolver nhận `ServerRequest`, cấu hình qua Java DSL |
| Bảo mật Spring Security | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Áp lực kết nối kéo dài | Có lợi thế mô hình non-blocking nếu toàn bộ đường đi xử lý đúng | Hỗ trợ các tình huống này nhưng cần tính đến tài nguyên Servlet, buffering và cấu hình thread |
| Vấn đề cần chú ý | Một thao tác blocking trong event loop có thể làm tăng độ trễ cho nhiều request | Khi nhiều request chờ I/O, tài nguyên thread và bộ nhớ cần được đo đạc, điều chỉnh |

Không có quy tắc “WebFlux luôn nhanh hơn Web MVC”. Throughput và độ trễ thực tế còn phụ thuộc tốc độ backend, chi phí TLS, số filter, kiểu payload, connection pool, thread, lượng kết nối đang mở và cấu hình triển khai.

## 3. Một request đi qua gateway như thế nào?

### 3.1. Pipeline Server WebFlux

~~~mermaid
flowchart LR
    A["Client"] --> B["RoutePredicate / HandlerMapping"]
    B --> C["FilteringWebHandler"]
    C --> D["GlobalFilter + GatewayFilter<br/>pre-processing"]
    D --> E["Reactor Netty HttpClient"]
    E --> F["Microservice"]
    F --> G["Filter post-processing"]
    G --> H["Response về client"]
~~~

1. `HandlerMapping` tìm route có predicate khớp với request (chẳng hạn `Path=/api/orders/**`).
2. `FilteringWebHandler` tạo chuỗi filter theo route và thứ tự ưu tiên.
3. Filter có thể kiểm tra header, thêm thông tin, thay đường dẫn, áp dụng rate limit hoặc circuit breaker trước khi gửi yêu cầu.
4. HTTP client chuyển request sang upstream. Khi có phản hồi, phần xử lý sau (post) của filter tiếp tục chạy rồi trả response.

Trong WebFlux, lập trình viên thường thao tác với `ServerWebExchange` và các kiểu phản ứng `Mono`/`Flux`. Ví dụ, gọi JDBC đồng bộ, `Thread.sleep` hoặc HTTP client blocking ngay trong event loop có thể làm nghẽn khả năng phục vụ request khác. Nếu không tránh được thao tác blocking, phải thiết kế việc tách nó sang executor/scheduler phù hợp và đo tải; tách thread không tự động giải quyết giới hạn tài nguyên.

### 3.2. Pipeline Server Web MVC

~~~mermaid
flowchart LR
    A["Client"] --> B["Servlet container"]
    B --> C["WebMvc.fn RouterFunction / RequestPredicate"]
    C --> D["before / HandlerFilterFunction"]
    D --> E["HandlerFunctions.http()"]
    E --> F["Microservice"]
    F --> G["after / response filters"]
    G --> H["Response về client"]
~~~

Server Web MVC biểu diễn route bằng `RouterFunction`; handler chuyển tiếp HTTP thường là `HandlerFunctions.http()`. Thay vì đem nguyên interface `GlobalFilter` của WebFlux sang dùng, ta mở rộng bằng các predicate, `before` filter, `HandlerFilterFunction` và `after` filter của WebMvc.fn/gateway MVC.

Ví dụ, một filter cần bổ sung header trước khi proxy có thể viết theo dạng `.before(addRequestHeader(...))`; filter cần bao quanh xử lý có thể viết theo dạng `.filter(...)`. Thứ tự đặt filter có ý nghĩa, đặc biệt khi vừa sửa URL vừa load balance hoặc retry.

## 4. Cài đặt hai biến thể

### 4.1. Dependency

Sử dụng **một** starter Server phù hợp trong ứng dụng gateway. Spring Cloud BOM phải tương thích với phiên bản Spring Boot của dự án.

**WebFlux (Maven):**

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
</dependency>
~~~

**Web MVC (Maven):**

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
~~~

WebFlux yêu cầu Reactor Netty; thêm `spring-boot-starter-web` để kéo Spring MVC/Servlet vào cùng ứng dụng có thể làm cơ chế chọn web stack của Spring Boot khác kỳ vọng. Khi chọn Server Web MVC, sử dụng runtime Servlet và dependency phục vụ Web MVC. Không chỉ đổi dependency rồi giữ nguyên mọi custom filter.

### 4.2. Cùng một route ở hai cấu hình YAML

Giả sử order service chạy tại `http://localhost:9001` và công khai API `GET /orders/42`. Gateway cần tiếp nhận `GET /api/orders/42`, bỏ segment `api` rồi thêm header `X-Gateway`.

**Server WebFlux — `application.yml`:**

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-route
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway, webflux
~~~

**Server Web MVC — `application.yml`:**

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: orders-route
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway, webmvc
~~~

Kiểm tra hành vi:

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

Nếu order service hoạt động, request được gửi tới `http://localhost:9001/orders/42` kèm header `X-Gateway: webflux` hoặc `X-Gateway: webmvc` tương ứng. `StripPrefix=1` bỏ **một segment đầu tiên**, không phải một ký tự hay một tiền tố chuỗi tùy ý. Giá trị response HTTP do backend quyết định.

**Điểm mấu chốt:** Trong nhánh Gateway 5.0, tiền tố route là `spring.cloud.gateway.server.webflux.routes` hoặc `spring.cloud.gateway.server.webmvc.routes`. Hai mẫu YAML trên giống nhau ở cú pháp predicate/filter thông dụng, nhưng không có nghĩa mọi filter hay tham số của hai stack tương đương từng cái một.

### 4.3. Tạo route bằng Java DSL

**WebFlux** sử dụng `RouteLocatorBuilder`:

~~~java
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WebFluxRoutes {
    @Bean
    RouteLocator ordersRoute(RouteLocatorBuilder builder) {
        return builder.routes()
            .route("orders-route", r -> r
                .path("/api/orders/**")
                .filters(f -> f.stripPrefix(1)
                    .addRequestHeader("X-Gateway", "webflux"))
                .uri("http://localhost:9001"))
            .build();
    }
}
~~~

**Web MVC** sử dụng `GatewayRouterFunctions` và `HandlerFunctions`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.addRequestHeader;

@Configuration
class WebMvcRoutes {
    @Bean
    RouterFunction<ServerResponse> ordersRoute() {
        return route("orders-route")
            .GET("/api/orders/**", http())
            .before(uri("http://localhost:9001"))
            .before(stripPrefix(1))
            .before(addRequestHeader("X-Gateway", "webmvc"))
            .build();
    }
}
~~~

Hai class trên là **hai phương án thay thế**, không đặt cùng lúc trong một ứng dụng. Chúng minh họa khác biệt lớn nhất khi mở rộng gateway: WebFlux xây route qua DSL phản ứng, còn Web MVC xây `RouterFunction` qua API WebMvc.fn. Nếu hệ thống chỉ cần cấu hình route đơn giản, YAML thường dễ kiểm tra và thay đổi hơn Java DSL; Java DSL hữu ích khi cần filter hoặc predicate tùy biến.

## 5. So sánh các khả năng quan trọng khi xây API Gateway

### 5.1. Predicate, đường dẫn và header

Cả hai hỗ trợ các loại predicate phổ biến như `Path`, `Host`, `Method`, `Header`, `Query` và filter như `StripPrefix`, `RewritePath`, `SetPath`, `AddRequestHeader`, `AddResponseHeader`, `RemoveRequestHeader`. Tuy nhiên, **tên có vẻ giống nhau không đảm bảo cùng interface, thứ tự chạy hoặc mức hỗ trợ ở mọi release**.

Ví dụ, route `Path=/api/orders/**` khớp cả `/api/orders/42`; khi kết hợp `StripPrefix=1`, upstream nhận `/orders/42`. Nếu muốn đổi `/v1/orders/42` thành `/orders/42` theo quy tắc phức tạp, cân nhắc `RewritePath` hoặc `SetPath` và kiểm thử đường dẫn có ký tự mã hóa, query string, dấu `/` cuối đường dẫn.

Một số lưu ý thực hành:

1. Đường dẫn đặt bên trong `uri` của route không phải cơ chế viết lại path đáng tin cậy; dùng filter chuyên trách.
2. Thứ tự filter quan trọng: với Server Web MVC, khi dùng `lb()` bằng Java DSL, đặt sau những filter đổi path như `stripPrefix()`; cấu hình `lb://` có cơ chế thứ tự riêng.
3. Chỉ bổ sung header cần thiết; không vô tình chuyển tiếp header nhạy cảm hoặc tin tưởng `X-Forwarded-*` do client tự gửi.

### 5.2. Khám phá dịch vụ và cân bằng tải

Ở cả hai biến thể, URI `lb://order-service` có thể dùng Spring Cloud LoadBalancer để chuyển tên dịch vụ thành instance cụ thể, khi hệ thống đã cung cấp cơ chế khám phá dịch vụ phù hợp và dependency cần thiết, ví dụ `spring-cloud-starter-loadbalancer`.

~~~yaml
# Thay cho http://localhost:9001 trong route của từng stack:
uri: lb://order-service
~~~

`lb://` **không tự tạo registry**, không tự khám phá instance chỉ vì bạn viết tên dịch vụ. Cần thiết lập DiscoveryClient (Eureka, Consul, Kubernetes discovery hoặc cơ chế tương ứng), kiểm thử khi danh sách instance rỗng và xác định chính sách timeout/retry. Cả hai gateway có thể đứng trước cùng một tập backend.

### 5.3. Xác thực và phân quyền

Với WebFlux, Spring Security dùng `SecurityWebFilterChain` và các API reactive; với Web MVC, Spring Security dùng `SecurityFilterChain` cùng cơ chế Servlet. Cả hai có thể xác thực JWT theo OAuth2 Resource Server, tích hợp OAuth2 client và relay token khi cấu hình đúng.

Một thiết kế thường gặp:

~~~text
Client -- Authorization: Bearer <token> --> Gateway
    1. Xác thực chữ ký, issuer, audience, thời hạn token
    2. Kiểm tra quyền truy cập route
    3. Chuyển tiếp danh tính/claim theo hợp đồng với backend
    4. Backend vẫn kiểm tra quyền với tài nguyên riêng
~~~

Không xem `AddRequestHeader=Authorization,...` hoặc `TokenRelay` như một sự thay thế cho xác thực. Token relay phụ thuộc bối cảnh đăng nhập/OAuth2 và cấu hình client; gateway cần tránh lộ token qua log hoặc thông báo lỗi. Khi cho phép health endpoint truy cập công khai, thiết lập security matcher rõ ràng trên đúng web stack.

### 5.4. Rate limiting: khác biệt đáng chú ý

**WebFlux:** `RequestRateLimiter` thường dùng `RedisRateLimiter` với token bucket, hoặc triển khai Bucket4j tùy dependency. `KeyResolver` nhận `ServerWebExchange` và trả về `Mono<String>`. Ví dụ định nghĩa route:

~~~yaml
# Đoạn filters trong route Server WebFlux;
# cần reactive Redis và KeyResolver phù hợp môi trường.
filters:
  - name: RequestRateLimiter
    args:
      redis-rate-limiter.replenishRate: 10
      redis-rate-limiter.burstCapacity: 20
      redis-rate-limiter.requestedTokens: 1
~~~

Khi hết token, gateway thường trả **HTTP 429**. `replenishRate=10` là tốc độ cấp lại 10 token/giây, `burstCapacity=20` là sức chứa tối đa, `requestedTokens=1` là số token mỗi request. Chọn khóa theo người dùng/tenant/client đáng tin cậy, không lấy bừa query param do client tự sửa. Redis phù hợp khi cần giới hạn phân tán giữa nhiều replica gateway.

**Web MVC:** filter `RateLimiter` sử dụng **Bucket4j** và `KeyResolver` dạng `Function<ServerRequest, String>`. Tài liệu Gateway MVC 5.0 lưu ý key resolver hiện phải cấu hình bằng **Java DSL**, không phải chỉ sao chép YAML `RequestRateLimiter` của WebFlux. Khi dùng kho lưu trữ bucket cục bộ, giới hạn chỉ áp dụng trên từng instance; muốn quota thống nhất cần cơ chế lưu trữ/distribution thích hợp.

Vì vậy, khi chuyển giữa hai stack, phải kiểm tra lại **dependency, tên filter, cách tạo khóa và nơi lưu trạng thái quota**, kể cả khi yêu cầu nghiệp vụ “100 request mỗi phút mỗi user” không đổi.

### 5.5. Circuit breaker, retry và fallback

Cả hai hỗ trợ pattern resilience, nhưng các API/filter triển khai và dependency cần được cấu hình theo stack cụ thể:

- **Circuit breaker** giám sát lỗi hoặc trạng thái phản hồi theo cấu hình, mở mạch khi upstream có vấn đề và có thể chuyển tới fallback. Nếu dùng `fallbackUri`, cần đảm bảo endpoint fallback tương thích với biến thể và release đang chạy.
- **Retry** lặp lại yêu cầu khi gặp lỗi thỏa điều kiện; nên bắt đầu với những thao tác idempotent như `GET`, kiểm soát số lần retry, backoff và timeout tổng thể.
- **Timeout** xác định giới hạn chờ kết nối/response. Tăng retry mà không quản lý timeout có thể khiến một request chiếm tài nguyên lâu hơn và làm sự cố backend lan rộng.

Ví dụ: order service trả 503 trong 20 giây. Gateway có thể retry có giới hạn cho `GET /orders/42`, sau đó trả lỗi hoặc fallback. Nhưng với `POST /payments`, retry có thể tạo giao dịch trùng nếu backend không hỗ trợ idempotency key. Đừng bật retry mặc định cho mọi method.

Khi retry request có body, một số cách triển khai cần **cache body**, tăng tiêu thụ bộ nhớ. Kiểm thử payload lớn và request đang stream trước khi bật.

### 5.6. TLS, WebSocket và quan sát request

**TLS:** Cả hai đều có thể phục vụ HTTPS phía client qua cấu hình SSL của Spring Boot (chẳng hạn `server.ssl.*`) và chuyển tiếp tới upstream `https://`. TLS vào gateway và TLS từ gateway sang backend là **hai kết nối khác nhau**; certificate/trust configuration của HTTP client phía outbound phụ thuộc vào web stack. Ở môi trường production, kiểm tra xác thực chứng chỉ upstream thay vì tắt kiểm tra TLS.

**WebSocket:** WebFlux có cơ chế proxy WebSocket theo mô hình non-blocking; Server Web MVC ở các bản hỗ trợ mới cũng có proxy WebSocket khi bổ sung dependency WebSocket phù hợp. Với MVC, Servlet WebSocket không cung cấp backpressure tương tự luồng Reactor; cần cân nhắc giới hạn buffer, số kết nối giữ lâu và khả năng quan sát khi chọn kiến trúc.

**Observability:** Cả hai có thể tích hợp Spring Boot Actuator, Micrometer, tracing và log có correlation ID. Nên quan sát ít nhất: số request theo route, tỷ lệ 4xx/5xx, độ trễ p95/p99, lỗi upstream, số lần retry, trạng thái circuit breaker, yêu cầu bị rate limit, số kết nối và tài nguyên runtime. Tên metric/tag và endpoint có thể khác theo phiên bản; xác minh bằng Actuator của chính bản triển khai.

## 6. Chọn biến thể nào cho từng bài toán?

| Bối cảnh | Hướng lựa chọn | Lý do / điều kiện |
|---|---|---|
| Gateway chủ yếu proxy lượng lớn request I/O-bound, nhiều kết nối đồng thời, streaming | Cân nhắc **Server WebFlux** | Event loop và I/O non-blocking có lợi khi filter/HTTP client không chặn |
| Đội ngũ đã có Spring MVC, thư viện Servlet và logic filter đồng bộ | Cân nhắc **Server Web MVC** | Dễ tận dụng kiến thức, thư viện và cách debug Servlet |
| Yêu cầu custom filter dùng Reactor `Mono`/`Flux` | **Server WebFlux** | API native tương thích |
| Cần tích hợp `HttpServletRequest`, `SecurityFilterChain` hoặc filter Servlet có sẵn | **Server Web MVC** | Tránh viết lại toàn bộ logic sang reactive |
| Cần rate limit phân tán Redis với `RequestRateLimiter` đang dùng | **WebFlux** có đường triển khai trực tiếp | Không giả định bộ cấu hình `RequestRateLimiter` hoạt động y hệt trên MVC |
| Cần WebSocket rất nhiều kết nối duy trì lâu | **Đánh giá WebFlux trước**, benchmark cả hai nếu cần | Kiểm tra mô hình backpressure, buffer và tài nguyên mỗi kết nối |
| Backend phía sau viết bằng Spring MVC | **Cả hai** | Backend không quyết định web stack của gateway |
| Chỉ có lưu lượng vừa phải và route/filter cơ bản | **Cả hai** | Chọn theo năng lực bảo trì, deployment và nhu cầu tương lai |

**Cách đưa ra quyết định có số liệu:** Dựng hai bản gateway với cùng route, security policy, upstream và giới hạn tài nguyên. Dùng bộ tải phản ánh lưu lượng thực (có cả kết nối chậm, lỗi 5xx, payload lớn, keep-alive), so sánh RPS, p95/p99, CPU, heap, GC, thread và số kết nối. Kiểm thử cả tình huống backend chậm 500 ms, vì vấn đề của gateway thường xuất hiện khi phải **chờ** upstream chứ không chỉ khi backend trả lời nhanh.

## 7. Tình huống thực tế: gateway trước ba microservice

Giả sử hệ thống thương mại có `identity-service`, `catalog-service` và `order-service`. Gateway cung cấp một domain `api.example.com`:

~~~mermaid
flowchart TB
    C["Web / Mobile / Partner"] --> G["API Gateway"]
    G --> A["/api/auth/** → identity-service"]
    G --> B["/api/products/** → catalog-service"]
    G --> D["/api/orders/** → order-service"]
    G -.-> O["Metrics / tracing / logging"]
~~~

Thiết kế route và policy:

| Route | Predicate | Biến đổi | Chính sách |
|---|---|---|---|
| `auth` | `Path=/api/auth/**` | `StripPrefix=1` | Giới hạn login theo key đáng tin cậy, không lộ token |
| `catalog` | `Path=/api/products/**` | `StripPrefix=1` | Timeout rõ ràng, cân nhắc cache và retry `GET` |
| `orders` | `Path=/api/orders/**` | `StripPrefix=1` | Xác thực JWT, kiểm tra quyền, circuit breaker phù hợp |

Khi gateway chỉ thực hiện routing, JWT validation và proxy non-blocking tới các service thường chậm, WebFlux là ứng viên phù hợp. Nếu công ty đang vận hành nhiều filter Servlet và cần tái sử dụng các thành phần đồng bộ, Web MVC giúp rút ngắn chi phí chuyển đổi. Trong cả hai trường hợp, backend vẫn phải xác nhận quyền sở hữu đơn hàng, tránh giả định “đã đi qua gateway thì mọi request đều được tin cậy”.

## 8. Lỗi thường gặp khi chuyển đổi giữa WebFlux và Web MVC

1. **Chỉ đổi starter mà giữ nguyên Java custom filter.** `GlobalFilter` nhận `ServerWebExchange` không thể chuyển nguyên xi thành `HandlerFilterFunction` nhận `ServerRequest`. Phải đổi API và kiểm tra thứ tự thực thi.
2. **Sao chép sai prefix từ bài viết cũ.** Ví dụ cũ dùng `spring.cloud.gateway.routes` cho WebFlux hoặc `spring.cloud.gateway.mvc.routes` cho MVC. Tài liệu mới dùng `spring.cloud.gateway.server.webflux.routes` và `spring.cloud.gateway.server.webmvc.routes`; kiểm tra release đang chạy.
3. **Kéo lẫn runtime Servlet vào WebFlux.** Kết hợp dependency thiếu chủ đích có thể khiến Spring Boot chọn web application type khác và gateway WebFlux không khởi động như mong muốn.
4. **Cho rằng mọi filter có cùng tên/cấu hình.** Rate limiting là ví dụ rõ nhất: WebFlux `RequestRateLimiter` và MVC `RateLimiter` sử dụng API khác nhau.
5. **Chặn event loop hoặc bỏ qua giới hạn thread.** WebFlux cần tránh blocking; MVC cần theo dõi thread pool, timeout và số kết nối chờ. Virtual thread nếu được bật phù hợp có thể giúp một số tải blocking, nhưng không biến Servlet thành pipeline reactive.
6. **Tin tưởng forwarded headers hoặc log thông tin nhạy cảm.** Chỉ chấp nhận `Forwarded`/`X-Forwarded-*` từ proxy tin cậy theo cấu hình release; loại bỏ token, cookie và dữ liệu nhạy cảm khỏi log/tracing.
7. **Đoán rằng retry vô hại.** Retry sai với POST không idempotent có thể nhân đôi tác động; đồng thời retry lớn khi backend đang quá tải dễ gây thêm áp lực.
8. **Đọc sai kết quả benchmark.** Benchmark chỉ gọi upstream trả `200` ngay không đo được rủi ro khi kết nối giữ lâu hoặc upstream chậm. Cần workload đại diện cho production.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Gateway Server WebFlux chạy cùng một backend Spring MVC có hợp lệ không?  
**Đáp án:** Có. Web stack của gateway không buộc backend dùng cùng web stack.

**Câu 2.** Tại sao không nên viết `Thread.sleep(200)` trong `GlobalFilter` của WebFlux?  
**Đáp án:** Thao tác blocking có thể chiếm event-loop thread, làm tăng độ trễ cho nhiều request dùng chung thread đó.

**Câu 3.** Với `Path=/api/orders/**` và `StripPrefix=1`, request `/api/orders/42` chuyển thành path nào?  
**Đáp án:** `/orders/42`.

**Câu 4.** Có thể sao chép cấu hình `RequestRateLimiter` Redis của WebFlux sang MVC và mặc định hoạt động không?  
**Đáp án:** Không. MVC dùng filter/API Bucket4j riêng và có các yêu cầu cấu hình Java DSL, nhất là key resolver.

**Câu 5.** Phải chọn WebFlux vì backend dùng Reactor?  
**Đáp án:** Không. Chọn web stack theo yêu cầu của gateway, tải thực tế, khả năng tích hợp, vận hành và benchmark.

## 10. Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring Cloud Gateway 5.0 — Tổng quan các biến thể](https://docs.spring.io/spring-cloud-gateway/reference/5.0/index.html).
- [Server WebFlux — Starter và yêu cầu Reactor Netty](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/starter.html).
- [Server Web MVC — Starter và Servlet runtime](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/starter.html).
- [Server WebFlux — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/how-it-works.html) và [Server Web MVC — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/how-it-works.html).
- [Server Web MVC — Java Routes API](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/java-routes-api.html).
- [Server WebFlux — RequestRateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html) và [Server Web MVC — RateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/filters/ratelimiter.html).
- [Spring Cloud 2025.0 — Ghi chú đổi tên starter và property prefix](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes).

Khi nâng cấp Spring Cloud Gateway, luôn tra đúng **release train và phiên bản** của ứng dụng vì khả năng filter, tên dependency, property và các lựa chọn bảo mật có thể thay đổi giữa các nhánh.
