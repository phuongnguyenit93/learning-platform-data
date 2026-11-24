# Kiến trúc Servlet và WebMvc.fn của Gateway Server Web MVC

## 1. Gateway Server Web MVC là gì và vì sao cần hiểu kiến trúc?

**Spring Cloud Gateway** cung cấp cổng vào cho microservices: chọn tuyến theo điều kiện HTTP, biến đổi path/header, chuyển request tới backend, khám phá dịch vụ, áp dụng xác thực và chính sách bảo vệ như rate limiting, retry, circuit breaker hoặc TLS. Khi xây Gateway, bạn phải chọn một **mô hình ứng dụng web** phù hợp với nền tảng chạy của dự án.

Một trong những lựa chọn là **Spring Cloud Gateway Server Web MVC**: biến thể của Spring Cloud Gateway xây trên **Spring MVC, Servlet API và WebMvc.fn**. Nó dùng nền tảng Servlet của Spring Boot, cho phép khai báo tuyến proxy theo kiểu hàm `RouterFunction` và sử dụng các cơ chế Servlet/MVC quen thuộc để tiếp nhận, xử lý và trả HTTP response.

Điều này **khác với Spring Cloud Gateway Server WebFlux**, vốn xây trên Spring WebFlux và Reactor. Hai biến thể có cùng mục tiêu ở mức nghiệp vụ nhưng khác đáng kể về **HTTP runtime, lập trình filter, vòng đời request, API bảo mật và công cụ kiểm thử**. Không thể thay vài tên dependency rồi sao chép nguyên một `GlobalFilter` trả về `Mono<Void>` sang ứng dụng Server Web MVC.

Bài học thuộc chương **Server Web MVC** của module **SPRING_CLOUD_GATEWAY**, tập trung vào kiến trúc Servlet và WebMvc.fn; các ví dụ về route predicate, filter chain, rewrite, service discovery, authentication, retry, TLS và quan sát request được dùng để làm rõ cách các thành phần phối hợp.

Sau khi học, bạn có thể:

1. Mô tả đường đi **Servlet container → Servlet Filter chain → DispatcherServlet → WebMvc.fn → Gateway handler/filter → upstream**.
2. Phân biệt `HttpServletRequest`, `ServerRequest`, `HandlerFunction`, `RouterFunction` và `ServerResponse`.
3. Hiểu **RouterFunctionMapping** và **HandlerFunctionAdapter** trong cách Spring MVC chọn và chạy handler dạng hàm.
4. Phân biệt **Servlet Filter**, **Spring Security FilterChain**, **Gateway MVC before/after filter** và **HTTP client outbound**.
5. Khai báo một route Gateway Server Web MVC bằng **YAML** và một route bằng **Java RouterFunctions DSL**.
6. Nhận biết khác biệt giữa các **namespace/starter** của Gateway MVC qua các dòng phiên bản.
7. Giải thích tác động của **Servlet threads, blocking I/O, connection pools, timeout và backpressure** đến khả năng chịu tải.
8. Thiết kế kiểm thử, logging và vận hành một Gateway MVC mà không mở rộng quyền hoặc phát tán credentials.

> **Phạm vi:** Bài này nói về **Gateway Server Web MVC**, không phải Gateway Server WebFlux và không phải dự án Spring Cloud Gateway ProxyExchange cũ. Ví dụ dùng Spring Boot/Spring MVC hiện đại; các tên starter, property, filter factory và Java DSL có thể khác giữa các release. Chọn một Spring Boot + Spring Cloud BOM tương thích trước khi áp dụng, rồi kiểm tra API thực tế của dòng đó.

## 2. Nền tảng Servlet: ai thực sự nhận một HTTP request?

Khi ứng dụng Gateway Server Web MVC chạy, Spring Boot thường khởi động **Servlet web application** với một Servlet container nhúng, ví dụ Tomcat hoặc Jetty nếu phiên bản và dependency phù hợp. HTTP request đi vào một cổng server đã được cấu hình, được container xử lý qua Servlet API rồi chuyển tới Spring MVC.

~~~mermaid
flowchart TD
    C["HTTP client"] --> P["Ingress / reverse proxy, nếu có"]
    P --> T["Servlet container: Tomcat / Jetty"]
    T --> F["Servlet Filter chain"]
    F --> DS["Spring MVC DispatcherServlet"]
    DS --> HM["HandlerMapping"]
    HM --> RF["WebMvc.fn RouterFunction"]
    RF --> HF["Gateway HandlerFunction"]
    HF --> HC["Outbound HTTP client"]
    HC --> U["Catalog / Orders service"]
    U --> HC
    HC --> HF
    HF --> DS
    DS --> T
    T --> C
~~~

Trong luồng này, mỗi thành phần có trách nhiệm riêng:

| Thành phần | Vai trò | Không nên nhầm với |
| --- | --- | --- |
| **Servlet container** | Nhận socket/HTTP, quản lý request và response, kết nối, thread, Servlet lifecycle | Reactor Netty của Gateway WebFlux |
| `jakarta.servlet.Filter` | Bọc đường đi của request ở lớp Servlet | Gateway MVC before/after filter |
| **Spring Security Servlet filter chain** | Xác thực và phân quyền request trước khi vào MVC handler | Gateway route predicate |
| `DispatcherServlet` | Front controller của Spring MVC, phân phối đến handler phù hợp | Gateway HTTP client gọi backend |
| `RouterFunctionMapping` | Tìm một `HandlerFunction` theo WebMvc.fn routing | Reactive `RoutePredicateHandlerMapping` |
| `HandlerFunctionAdapter` | Điều phối thực thi `HandlerFunction` đã được chọn | `GatewayFilterChain` của WebFlux |
| Gateway **before/handler/after filters** | Chỉnh request, proxy hoặc chỉnh response theo DSL/route | Servlet Filter áp trên toàn ứng dụng |
| **Outbound HTTP client** | Tạo HTTP request mới tới backend, nhận response | Servlet container nhận inbound |

Mô hình trên là **luồng logic**; container có thể hỗ trợ async Servlet và một số triển khai có cơ chế tối ưu streaming, nhưng điều đó **không biến Server Web MVC thành Reactor-based WebFlux Gateway**.

### Request ở ranh giới Servlet

Lớp Servlet gốc dùng các kiểu dữ liệu như:

~~~java
jakarta.servlet.http.HttpServletRequest
jakarta.servlet.http.HttpServletResponse
jakarta.servlet.Filter
jakarta.servlet.FilterChain
~~~

Trong Spring MVC dạng hàm, bạn thường làm việc ở mức cao hơn:

~~~java
org.springframework.web.servlet.function.ServerRequest
org.springframework.web.servlet.function.ServerResponse
org.springframework.web.servlet.function.RouterFunction
org.springframework.web.servlet.function.HandlerFunction
~~~

Hai lớp API này liên hệ với nhau nhưng **không đồng nhất**. `ServerRequest` là abstraction hướng đến handler dạng hàm; nó **không phải** `org.springframework.web.reactive.function.server.ServerRequest` của WebFlux. Khi IDE auto-import nhầm package reactive, code sẽ khó biên dịch hoặc lẫn mô hình runtime.

### Servlet threading và I/O

Trong mô hình Servlet truyền thống, request thường sử dụng một request-handling thread khi thực hiện logic synchronous/blocking. Gateway còn dùng HTTP client outbound, pool kết nối và timeout riêng để gọi backend. Vì vậy một upstream chậm có thể làm **request threads hoặc tài nguyên I/O** bị giữ lâu, tùy cách client và Servlet async được triển khai.

Không tự kết luận rằng “Servlet luôn chỉ xử lý một request cho mỗi thread trong toàn bộ vòng đời”, vì Servlet async có thể giải phóng/điều phối thread ở một số giai đoạn. Nhưng cũng **không được giả định tất cả filter/HTTP client của Gateway MVC đều non-blocking**, chỉ vì ứng dụng có một vài callback hoặc streaming response. Hãy kiểm tra implementation và đo **thread occupancy, connection pool, queue depth và latency**.

## 3. WebMvc.fn là gì?

**WebMvc.fn** là mô hình lập trình HTTP dạng hàm của Spring MVC. Thay vì bắt buộc viết một controller bằng `@RestController` và `@GetMapping`, bạn có thể định nghĩa các tuyến bằng `RouterFunction<ServerResponse>` và xử lý chúng qua `HandlerFunction<ServerResponse>`.

Một tuyến functional về mặt khái niệm có dạng:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/hello", request ->
                        ServerResponse.ok().body("Hello from MVC"))
                .build();
~~~

Đây là ví dụ **Spring MVC WebMvc.fn thông thường**, chưa phải một Gateway proxy. Nó minh họa rằng:

1. `RouterFunction` giữ các quy tắc match request.
2. Một predicate như `GET("/hello", ...)` xác định method/path.
3. `HandlerFunction` nhận `ServerRequest` và trả `ServerResponse`.
4. `DispatcherServlet` thông qua hạ tầng MVC sẽ tìm và gọi handler tương ứng.

Nếu muốn proxy tới backend thay vì tự tạo chuỗi Hello, **Gateway Server Web MVC** cung cấp các handler và filters chuyên dụng để gửi request outbound.

### Annotation MVC và functional MVC có thể cùng tồn tại

Trong một Spring MVC application, các endpoint dạng `@RestController` và `RouterFunction` có thể cùng được đăng ký. Ví dụ:

- `@RestController` cho một endpoint kiểm tra nội bộ do ứng dụng tự viết.
- `RouterFunction` cho các tuyến Gateway proxy.
- Spring Boot Actuator cho health/metrics trên management HTTP surface.

Nhưng việc chúng cùng tồn tại **không có nghĩa cùng đi qua một Gateway route filter**. Phải biết `HandlerMapping` nào chọn request và security/Servlet filters nào áp lên đường đi. Một `Gateway MVC before filter` gắn vào route Catalog không tự động chạy cho `@GetMapping("/internal/info")` ở controller khác.

### Cấu trúc kiểu dữ liệu

~~~text
RouterFunction<ServerResponse>
    match(ServerRequest)
           |
           v
HandlerFunction<ServerResponse>
    handle(ServerRequest)
           |
           v
ServerResponse
    status + headers + body
~~~

Đây là mô hình **imperative/function-based** của WebMvc.fn. Khác với WebFlux Web.fn, một `HandlerFunction` MVC **không trả `Mono<ServerResponse>`**. Những route filters MVC cũng không sử dụng trực tiếp `Mono<Void>` và `GatewayFilterChain` như Gateway Server WebFlux.

## 4. Từ DispatcherServlet đến Gateway proxy handler

Sơ đồ cụ thể hơn khi một client gọi `GET /api/catalog/products/42`:

~~~mermaid
sequenceDiagram
    participant Client
    participant Container as Servlet container
    participant Security as Servlet Security chain
    participant MVC as DispatcherServlet
    participant Router as WebMvc.fn RouterFunctionMapping
    participant Gateway as Gateway handler + filters
    participant Backend as Catalog service
    Client->>Container: GET /api/catalog/products/42
    Container->>Security: Servlet FilterChain
    Security-->>Container: Authorized request continues
    Container->>MVC: Servlet request
    MVC->>Router: Find matching route
    Router-->>MVC: HandlerFunction
    MVC->>Gateway: Execute MVC handler
    Gateway->>Gateway: before filters: path/header changes
    Gateway->>Backend: HTTP request via outbound client
    Backend-->>Gateway: 200 + JSON
    Gateway->>Gateway: after filters: response adjustments
    Gateway-->>MVC: ServerResponse
    MVC-->>Container: HTTP response
    Container-->>Client: 200 + JSON
~~~

**Các bước quan trọng:**

1. **Container nhận request:** quản lý kết nối, giới hạn parser HTTP, request body, response stream.
2. **Servlet filters:** có thể thực hiện encoding, tracing, authentication và authorization; Spring Security thường nằm ở lớp này.
3. **DispatcherServlet:** tìm handler theo cơ chế `HandlerMapping` của Spring MVC.
4. **WebMvc.fn routing:** `RouterFunctionMapping` đánh giá route predicates; khi match, `HandlerFunctionAdapter` sẽ làm cầu nối gọi handler tương ứng.
5. **Gateway MVC filters:** các bước before/after có thể đổi URI, path, headers, request context và response theo khả năng của filter factory/version.
6. **Gateway HTTP handler:** tạo HTTP request outbound tới backend được chọn, dùng client/request factory và network stack phù hợp.
7. **Backend trả response:** Gateway xử lý status/headers/body, áp các bước after và trả `ServerResponse` cho MVC.
8. **Container gửi response:** response tới client, các Servlet filters bọc bên ngoài có thể còn xử lý tiếp phần hậu kỳ của chúng.

**Ranh giới quan trọng:** Đây là một luồng **hai HTTP kết nối** — client → Gateway và Gateway → backend. Gateway không “chuyển nguyên ServletRequest sang socket khác”; nó phải xây **một outbound request** với method, URI, headers và body phù hợp, rồi chuyển kết quả về inbound response.

### Nhầm lẫn phổ biến: route match không đồng nghĩa request proxy thành công

Một RouterFunction có thể match thành công nhưng outbound:

- Không phân giải được `lb://catalog-service` vì discovery không có instance.
- Gặp DNS, TCP connect hoặc TLS handshake error.
- Timeout vì backend quá chậm hoặc connection pool hết chỗ.
- Được CircuitBreaker short-circuit theo chính sách route.
- Bị trước đó chặn bởi Spring Security, nên Gateway handler không chạy.

Vì vậy cần phân biệt **route lookup**, **request filtering**, **outbound transport** và **response delivery**. HTTP 404 do route không match khác với HTTP 404 do backend Catalog trả, và HTTP 503 khi không có instance khác với 503 backend chủ động trả.

## 5. Predicate của WebMvc.fn và route predicate của Gateway MVC

Một `RouterFunction` được chọn khi request đáp ứng điều kiện: path, HTTP method, host hoặc headers tùy predicate/factory của phiên bản. Gateway Server Web MVC ánh xạ tư duy đó vào **route definitions** với ID, URI, predicates và filters.

Ví dụ các điều kiện thiết kế:

| Điều kiện | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Path | Nhận một nhóm đường dẫn | `/api/catalog/**` |
| Method | Giới hạn HTTP method | `GET`, `HEAD` |
| Header | Match một header theo pattern được hỗ trợ | `X-Api-Version` |
| Host | Route dựa trên host công khai đáng tin | `shop.example.test` |
| Query | Match tham số query theo semantics factory | `page` hoặc `category` |

**Predicate chọn route, không cấp quyền.** Một điều kiện `Host=admin.example.test` hoặc `Header=X-Role,admin` không chứng minh người dùng có quyền admin. Spring Security Servlet và backend authorization phải thực hiện xác thực/phân quyền theo trust boundary.

### Route không match

Khi không có RouterFunction nào phù hợp, Spring MVC có thể trả 404 theo handler mapping/error handling của ứng dụng. Tuy nhiên route catch-all, static resource handling, annotation controllers hoặc một handler khác có thể nhận request trước/sau tùy ordering. **Đừng suy ra mọi 404 là Gateway predicate sai**; hãy kiểm tra `HandlerMapping` và route definitions thực tế.

### Chồng lấn và ưu tiên route

Nếu vừa có `Path=/api/**` vừa có `Path=/api/admin/**`, cả hai có thể khớp một admin request. Phải biết quy tắc chọn route/ordering của phiên bản và đảm bảo **chính sách bảo mật tách biệt route order**. Một route rộng có thể đưa request tới backend khác nếu được chọn trước. Kiểm thử trường hợp exact path, trailing slash, encoded slash, method khác và các path rewrite ở ingress.

## 6. Before, handler và after: ba điểm mở rộng cần nhớ

Một Gateway MVC route được tổ chức logic như sau:

~~~mermaid
flowchart LR
    Req["ServerRequest"] --> Pred["Route predicate"]
    Pred --> Before["Before filters"]
    Before --> Handler["Gateway HTTP HandlerFunction"]
    Handler --> After["After filters"]
    After --> Resp["ServerResponse"]
~~~

**Before filter** thường chỉnh hoặc kiểm tra request **trước** khi gọi HTTP handler: đổi request path, URI đích, headers hoặc các thuộc tính request. **HandlerFunction** là nơi gọi upstream thực sự hoặc tạo response. **After filter** có thể chỉnh kết quả sau khi handler tạo response theo contract và implementation.

### So sánh với Server WebFlux

| Gateway Server Web MVC | Gateway Server WebFlux |
| --- | --- |
| WebMvc.fn `RouterFunction<ServerResponse>` | Spring WebFlux route predicates + reactive handler/filter chain |
| `HandlerFunction<ServerResponse>` | Reactive Gateway handler, `Mono<Void>` chain |
| Before/after/filter functions theo Gateway MVC API | `GatewayFilter`/`GlobalFilter` với `chain.filter(exchange)` |
| `ServerRequest` của `web.servlet.function` | `ServerWebExchange` và reactive request/response |
| Servlet `SecurityFilterChain` | Reactive `SecurityWebFilterChain` |
| Servlet container / HTTP client MVC | Reactor/WebFlux HTTP runtime |

**Đừng sao chép operator Reactor** như `doOnError`, `doFinally`, `Mono.defer` vào một WebMvc.fn filter chỉ vì bạn quen cách viết Gateway Server WebFlux. Trong MVC, xử lý lỗi có thể dựa trên exception, HTTP result, Servlet exception resolvers và các filter functions của route.

### After filter không phải thời điểm có thể sửa bất cứ thứ gì

Một after filter thao tác trên response ở mức được framework hỗ trợ. Nhưng **response status/headers/body có thể đã hoặc đang được ghi** theo implementation, streaming mode và filter order. Không giả định một custom after function có thể đảo lại response đã commit, đọc toàn bộ body vô hạn hoặc biến partial stream thành một JSON error khác. Dùng API filter được hỗ trợ và kiểm thử thực với backend streaming.

### Thứ tự thực thi khi nhiều filters được khai báo

Với nhiều before/after functions và filter wrappers, thứ tự áp dụng phụ thuộc cấu trúc route builder, composition và phiên bản. Hãy xét mỗi bước theo:

1. **Route predicate** chọn tuyến nào?
2. **Before filters** biến đổi những dữ liệu nào trước handler?
3. **Handler** thấy URI, path, headers và body cuối cùng ra sao?
4. **After filters** chỉnh response ở thời điểm nào?
5. **Servlet filters** ở lớp ngoài có đọc/ghi response hay chặn request không?

Không suy luận về “thứ tự cuối cùng” chỉ từ tên filter, nhất là khi Java DSL và cấu hình YAML cùng được sử dụng. Dùng test HTTP stub ghi nhận **request thực tới upstream** để xác minh.

## 7. Starter, phiên bản và cấu hình Spring Boot cho Server Web MVC

Spring Cloud Gateway có những biến thể khác nhau trong hệ sinh thái Spring Cloud, vì vậy **chọn đúng starter là quyết định kiến trúc**, không chỉ quyết định cú pháp.

Với dòng Spring Cloud Gateway Server Web MVC mới, dependency Maven thường có dạng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
~~~

Ở một số dòng cũ, tên starter có thể là `spring-cloud-starter-gateway-mvc`. Dùng **tên artifact và Spring Cloud BOM được hỗ trợ bởi Spring Boot version** của dự án. Đừng trộn một starter cũ vào BOM mới hoặc tự gán phiên bản tùy ý khi chưa xác minh compatibility matrix.

Ví dụ cấu trúc dependency:

~~~text
Spring Boot application
   |
   +-- Spring Cloud dependency BOM (phiên bản tương thích)
   |
   +-- Gateway Server Web MVC starter
   |      +-- Spring MVC / Servlet web runtime
   |      +-- Gateway WebMvc.fn routing / filter support
   |
   +-- Spring Cloud LoadBalancer (nếu dùng lb://)
   |
   +-- Spring Security Servlet (nếu bảo vệ gateway)
   |
   +-- Spring Boot Actuator / Micrometer (nếu quan sát)
~~~

Không nhất thiết phải khai báo từng dependency con nếu starter đã kéo theo chúng; quan trọng là **dependency graph thực tế**, bản compatible và **không vô tình đưa ứng dụng sang WebFlux Gateway**.

### 7.1. Lớp khởi động ứng dụng

Một ứng dụng Spring Boot Servlet thường có main class:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcGatewayApplication.class, args);
    }
}
~~~

Class này chưa khai báo route. Spring Boot sẽ lựa chọn web application type từ dependency và cấu hình; với MVC gateway, bạn cần **Servlet web application context** đúng, không ép chạy kiểu reactive. Nếu ứng dụng đồng thời chứa `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot có quy tắc suy luận web application type riêng; **đừng dùng cách thêm cả hai để “hỗ trợ cả MVC lẫn WebFlux” mà không kiểm tra runtime**.

### 7.2. Những phần không tương thích trực tiếp

| Thành phần quen thuộc của Gateway WebFlux | Không nên copy sang Web MVC vì |
| --- | --- |
| `spring-cloud-starter-gateway-server-webflux` | Đó là starter của biến thể reactive |
| `org.springframework.cloud.gateway.filter.GlobalFilter` | Dùng `Mono<Void>` và `ServerWebExchange` của WebFlux |
| `org.springframework.cloud.gateway.filter.GatewayFilter` | API reactive filter chain khác với MVC handler/filter functions |
| `ServerHttpSecurity` và `SecurityWebFilterChain` | Dành cho Spring Security reactive; MVC dùng `HttpSecurity` và `SecurityFilterChain` |
| `org.springframework.web.reactive.function.server.RouterFunction` | WebFlux.fn, không phải `org.springframework.web.servlet.function.RouterFunction` |
| Reactor Netty HTTP client properties | Không tự điều khiển Servlet container hoặc MVC outbound client |
| `Mono.defer`, `doFinally` trên Gateway filter | Không phải hợp đồng trả về của WebMvc.fn handler |

Bạn **vẫn có thể dùng Reactor trong một phần khác của ứng dụng** khi có nhu cầu, nhưng điều đó không thay đổi hợp đồng xử lý HTTP chính của Gateway Server Web MVC.

## 8. Ví dụ YAML: một route Servlet Gateway đơn giản

Giả sử:

- Gateway nghe trên `localhost:8080`.
- Catalog backend thử nghiệm nghe trên `localhost:9001`.
- Client gọi `GET /api/catalog/products/42`.
- Catalog backend có endpoint `GET /catalog/products/42`.

Một cấu hình ở dòng Gateway mới hỗ trợ namespace `server.webmvc`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-read
              uri: http://localhost:9001
              predicates:
                - Path=/api/catalog/**
                - Method=GET,HEAD
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway-Source,mvc-edge
~~~

**Giải thích từng phần:**

1. `server.port=8080` cấu hình cổng HTTP inbound của ứng dụng Boot.
2. `id=catalog-read` là định danh route phục vụ cấu hình, kiểm thử và quan sát.
3. `uri=http://localhost:9001` là upstream HTTP destination, **không phải cổng Gateway**.
4. `Path=/api/catalog/**` giới hạn URL client được nhận bởi route.
5. `Method=GET,HEAD` giới hạn phương thức, tránh một POST bất ngờ được proxy qua tuyến chỉ đọc.
6. `StripPrefix=1` xóa **một segment đầu** của path: `/api/catalog/products/42` → `/catalog/products/42`.
7. `AddRequestHeader` bổ sung header minh họa để backend có thể thấy request đi qua Gateway. **Không dùng header tự thêm như một bằng chứng authentication**.

Ví dụ trên **không tự bảo vệ bằng HTTPS, xác thực, rate limit hoặc mTLS**. Nó phù hợp với **lab cục bộ**, và mọi request thực tế đi tới backend cần được kiểm tra bằng HTTP stub. Với deploy Docker/Kubernetes, `localhost` của Gateway container **không tự trỏ tới một container backend khác**; hãy dùng tên DNS/service đúng mạng.

### 8.1. Namespace YAML phụ thuộc phiên bản

Trong những dòng Spring Cloud Gateway MVC trước, property route thường gặp là:

~~~yaml
spring:
  cloud:
    gateway:
      mvc:
        routes:
          - id: catalog-read
            uri: http://localhost:9001
            predicates:
              - Path=/api/catalog/**
~~~

Trong một số dòng mới hơn, namespace có thể là **`spring.cloud.gateway.server.webmvc.routes`**. Đừng khai báo đồng thời cả hai rồi đoán config nào được áp dụng. Kiểm tra Spring Cloud release notes, configuration metadata **của dependency thực đang dùng**, startup logs và test xem route thực sự match.

**Không nhầm với WebFlux:** `spring.cloud.gateway.server.webflux.routes` hoặc `spring.cloud.gateway.routes` trên một dự án WebFlux khác không bảo đảm Gateway Server MVC sẽ đọc cấu hình tương ứng.

### 8.2. Dòng chảy của request ví dụ

~~~text
Client:
    GET http://localhost:8080/api/catalog/products/42?lang=vi
                   |
                   v
Servlet Gateway MVC:
    Match Path=/api/catalog/**, Method=GET
    StripPrefix(1)
    AddRequestHeader(X-Gateway-Source: mvc-edge)
                   |
                   v
Catalog backend:
    GET http://localhost:9001/catalog/products/42?lang=vi
    X-Gateway-Source: mvc-edge
                   |
                   v
Gateway returns upstream response to client
~~~

Query string `lang=vi` trong ví dụ nên được giữ nguyên nếu không có filter nào cố ý sửa nó; tuy nhiên việc giữ hoặc mã hóa lại **ký tự đặc biệt, encoded slash, dấu `+` và ký tự phần trăm (%)** phải được kiểm thử ở đúng phiên bản/router. Không chỉ nhìn một request ASCII đơn giản rồi kết luận mọi URI encoding đều đúng.

## 9. Java DSL: khai báo Gateway proxy bằng RouterFunction

Gateway Server Web MVC có thể cho phép tạo route theo Java DSL chuyên biệt, dựa trên WebMvc.fn. Một mẫu thường gặp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;

@Configuration
public class CatalogGatewayRoutes {

    @Bean
    public RouterFunction<ServerResponse> catalogRoute() {
        return route("catalog-java")
                .GET("/api/catalog/**", http())
                .before(uri("http://localhost:9001"))
                .build();
    }
}
~~~

**Đây là mẫu Java DSL của Gateway Server MVC** dùng những thành phần `GatewayRouterFunctions`, `HandlerFunctions` và `BeforeFilterFunctions` thuộc dòng MVC. Các method overload và package có thể khác giữa các release; kiểm tra Java API tương ứng với BOM của bạn.

Trong ví dụ:

- `route("catalog-java")` tạo một route có ID rõ ràng.
- `.GET("/api/catalog/**", http())` đăng ký predicate GET và Gateway HTTP handler.
- `.before(uri("http://localhost:9001"))` chỉ định URI của upstream trước khi handler thực thi.
- `.build()` trả một Spring MVC `RouterFunction<ServerResponse>` có thể được Spring container đăng ký dưới dạng bean.

**Khác biệt so với YAML ở phần 8:** Java DSL mẫu này **chưa thêm StripPrefix**, vì vậy backend có thể nhận nguyên path `/api/catalog/products/42` nếu không có một before filter đổi path. Nếu backend chỉ hỗ trợ `/catalog/products/42`, bạn phải gắn before filter tương ứng trong phiên bản của mình.

### 9.1. Bổ sung filter chỉnh path khi API hỗ trợ

Ở các dòng MVC có `BeforeFilterFunctions.stripPrefix`, một route có thể được phát triển:

~~~java
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;

// Đoạn phương thức builder, đặt trong bean RouterFunction ở trên:
return route("catalog-java")
        .GET("/api/catalog/**", http())
        .before(uri("http://localhost:9001"))
        .before(stripPrefix(1))
        .build();
~~~

Đây là **đoạn thay thế phần return** của method ví dụ trước, không phải một file Java thứ hai độc lập. Kiểm tra filter API có trong phiên bản đang dùng; có thể cần đổi thứ tự nếu builder/filter đang xử lý URI và path theo semantics khác. Dùng backend stub để xác nhận URI cuối.

### 9.2. Không tự viết HTTP client trong từng HandlerFunction nếu không cần

WebMvc.fn cho phép bạn tự tạo một handler:

~~~java
// Mã ý tưởng WebMvc.fn thông thường, không phải Gateway proxy factory:
request -> ServerResponse.ok().body("Hello")
~~~

Nhưng với một Gateway proxy, **ưu tiên HandlerFunctions và filters chuyên dụng của Gateway MVC** để giữ đúng HTTP semantics, truyền headers, stream body, kết hợp discovery và xử lý lỗi. Tự dùng `RestClient` rồi copy mọi request/response headers bằng tay dễ làm lộ `Authorization`, sai `Content-Length`, chuyển hop-by-hop headers hoặc tiêu thụ body trước khi proxy.

### 9.3. Có được khai báo cùng route qua YAML và Java không?

Có thể dùng cả hai hình thức trong ứng dụng nếu framework/version hỗ trợ, nhưng **đừng cố tạo hai routes chồng lấn với cùng path/method mà không có ưu tiên rõ**. Ví dụ YAML `catalog-read` và Java `catalog-java` cùng match `GET /api/catalog/**` thì một route có thể được chọn thay vì route kia. Với bài lab, **chọn một trong hai cấu hình** để dễ xác minh, hoặc làm rõ order/conditions và test.

## 10. Before filters: thay đổi request trước khi proxy

Before filters thuộc route có thể xử lý path, headers, URI, query hoặc những chính sách request được hỗ trợ. Chúng có vai trò tương tự **pre-routing transformation**, nhưng không phải là Servlet filters.

| Loại thay đổi | Mục đích | Rủi ro nếu dùng sai |
| --- | --- | --- |
| StripPrefix | Bỏ segment tiền tố bên ngoài của API Gateway | Bỏ quá nhiều segment, backend 404 |
| RewritePath | Đổi cấu trúc URL theo quy tắc/regex | Mất dấu slash, query hoặc encoded characters |
| AddRequestHeader | Bổ sung header cho upstream | Header bị backend tin như identity dù client có thể giả |
| RemoveRequestHeader | Loại header không cần chuyển | Xóa Authorization của route cần token, hoặc quên xóa Cookie ở vendor route |
| SetRequestHeader | Ghi đè một header với giá trị do hệ thống kiểm soát | Vô tình chuyển user-controlled data thành trusted metadata |
| URI/upstream selection | Chọn backend service | Có thể dẫn đến SSRF nếu lấy URI từ header client |

### 10.1. Request phải được xem là dữ liệu không tin cậy

Một client có thể gửi:

~~~http
GET /api/catalog/products/42 HTTP/1.1
Host: shop.example.test
Authorization: Bearer <client-token>
X-User-Role: ADMIN
X-Forwarded-Host: attacker.example
~~~

Gateway **không được coi** `X-User-Role` do client tự gửi là authority. Nếu cần identity, hãy dựa vào **Spring Security Servlet SecurityContext** sau xác thực hoặc contract danh tính nội bộ có nguồn và chữ ký tin cậy. Những header `Forwarded`/`X-Forwarded-*` chỉ nên được tin khi đến từ proxy/ingress được quản lý.

Nếu route Catalog là public và **không cần access token của người dùng**, hãy cân nhắc xóa `Authorization` và `Cookie` khỏi outbound request theo filter có sẵn của Gateway MVC. Nếu Orders cần access token, chỉ forward khi Orders là **audience được phép**, qua TLS và backend tự validate token; không gửi refresh token hay ID token tới mọi service.

### 10.2. Header HTTP không phải dữ liệu bất biến khi qua Gateway

Gateway nhận request inbound nhưng tạo request outbound mới. Header như `Host`, `Connection`, `Transfer-Encoding`, `Content-Length` và forwarding headers có ngữ nghĩa theo từng hop. Không sao chép tất cả headers một cách mù quáng, và không tự set `Content-Length` theo số ký tự Java nếu body có UTF-8 hoặc nén.

Tùy filter/client/framework, một số hop-by-hop headers được xử lý tự động, nhưng **vẫn phải test** những tình huống có reverse proxy, HTTP/2 ↔ HTTP/1.1, streaming, gzip và WebSocket upgrade.

### 10.3. Query string, encoded slash và context path

Ví dụ client gửi:

~~~text
/api/catalog/items/%2F-special?tag=a%2Bb&sort=price%20desc
~~~

Một path rewrite không cẩn thận có thể:

- Decode `%2F` thành dấu slash và làm thay đổi phân cấp path.
- Chuyển `+` thành space trong query dù client gửi encoded plus.
- Làm mất query string khi tạo URL đích.
- Tạo double slash hoặc slash cuối ngoài dự kiến.
- Thay đổi ý nghĩa đường dẫn nếu ingress đã rewrite trước khi vào Gateway.

Không có một quy tắc normalization duy nhất bảo đảm tương đương ở mọi proxy/Servlet container. Hãy test các path đó **qua toàn bộ ingress → Gateway → backend** và áp allowlist/authorization trên cách biểu diễn đường dẫn mà các tầng thực sự nhìn thấy.

## 11. Service discovery và URI `lb://` trong MVC Gateway

Trong microservices, backend thường không có một host:port cố định. Một route có thể dùng service ID:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: orders-read
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
~~~

Điều kiện sử dụng:

1. Ứng dụng có **Spring Cloud LoadBalancer** và nguồn thông tin instance tương thích với dòng Gateway MVC đang dùng.
2. `orders-service` phải resolve được tới những ServiceInstance đã được phê duyệt.
3. Gateway xử lý scheme/host/port/TLS đúng với instance.
4. Backend bảo vệ quyền truy cập của mình; service discovery không phải authentication.

~~~mermaid
flowchart TD
    P["GET /api/orders/42"] --> G["Gateway MVC route: lb://orders-service"]
    G --> LB["Service instance selection"]
    LB --> A["orders-1.internal:8443"]
    LB --> B["orders-2.internal:8443"]
    A --> H["HTTPS outbound client"]
    B --> H
    H --> R["HTTP response"]
~~~

**Cảnh báo về kiến trúc:** Đừng mô tả bước này bằng đúng class `ReactiveLoadBalancerClientFilter` của **Gateway WebFlux**, vì Gateway Server Web MVC dùng integration và HTTP routing khác. Khái niệm tương tự — resolve service ID thành instance thật — nhưng **implementation không đồng nhất**.

### No-instance khác backend 503

Nếu service registry không trả instance nào, Gateway không thể chọn đích. Kết quả HTTP cuối (thường thuộc nhóm không sẵn sàng) phụ thuộc implementation/error handler và policy. Nếu có instance nhưng nó trả `HTTP/1.1 503`, đó lại là **response từ backend**. Phải quan sát route ID, service ID, trạng thái discovery, lỗi client HTTP và backend request count để phân biệt.

### Vấn đề niềm tin đối với registry

Một route `lb://orders-service` không tự chứng minh host cuối đáng tin. Nếu registry bị ghi bản ghi độc hại, token có thể được gửi sang host không được phê duyệt. Hãy bảo vệ quyền cập nhật registry, namespace, destination egress, TLS certificate/hostname và mTLS khi cần. **Không cho Internet client trực tiếp đặt service ID hoặc upstream URI tùy ý**.

## 12. Outbound HTTP client: kết nối thứ hai của Gateway MVC

Sau route predicate và before filters, Gateway phải phát một HTTP request outbound tới backend. Tùy dòng Gateway MVC và HTTP client implementation, hạ tầng có thể tích hợp các API **Spring MVC HTTP client/RestClient** cùng request factory tương ứng. Điều quan trọng không phải tên class HTTP client trong ví dụ, mà là **quản lý transport như một thành phần riêng**:

~~~text
Incoming:
    Client --TLS/HTTP--> Servlet container --MVC--> Gateway handler

Outgoing:
    Gateway handler --HTTP client connection pool--TLS/HTTP--> Backend
~~~

### Những tài nguyên cần quản lý

| Tài nguyên | Khi backend chậm hoặc lỗi | Cách bảo vệ |
| --- | --- | --- |
| Servlet request threads | Có thể bị giữ để chờ xử lý hoặc ghi response, tùy implementation | Đo active/busy threads, giới hạn admission/concurrency |
| Outbound connection pool | Thiếu connections, pending acquire tăng | Pool size và timeout theo năng lực backend |
| TCP connect | Chờ kết nối hoặc bị refused | Connect timeout và discovery health |
| TLS handshake | Cert/hostname không hợp lệ, handshake timeout | Truststore, hostname verification, mTLS |
| HTTP response | Backend chậm hoặc không trả đúng deadline | Response/read timeout có chủ đích |
| Request/response buffers | Body lớn hoặc stream bị giữ quá lâu | Stream phù hợp, giới hạn body, tránh cache không cần |
| Retry/circuit breaker | Nhiều attempts hoặc fail fast | Retry budget, idempotency, trạng thái breaker |

**Không mặc định cấu hình `spring.cloud.gateway.server.webflux.httpclient.*` điều khiển MVC outbound transport.** Phải tìm đúng property/API của phiên bản Gateway MVC/HTTP client đang sử dụng, kiểm tra chúng thực sự được bind và đo kết quả trong test.

### Timeout ở ba ranh giới

Một request có thể có:

- **Client deadline:** người dùng chỉ chờ tối đa một thời gian nhất định.
- **Gateway outbound timeout:** giới hạn TCP/TLS/HTTP call tới backend.
- **Backend timeout:** giới hạn DB, SDK hoặc service-to-service calls phía sau.

Nếu Gateway đặt HTTP client timeout rất dài, một backend treo có thể giữ tài nguyên ngay cả khi client đã bỏ. Nếu timeout quá ngắn, những lời gọi hợp lệ có thể bị cắt và retry làm tăng tải. Chọn thời gian dựa trên **SLO của API, loại workload và giới hạn của toàn chuỗi**; không sao chép giá trị WebFlux sang MVC mà không xác minh semantics.

### Streaming và blocking

Với large upload/download hoặc SSE/NDJSON, cần biết Gateway MVC có **hỗ trợ streaming/buffering** theo route/filter/HTTP client cụ thể thế nào. Không mặc định body luôn được chuyển tiếp “zero copy”, và không log toàn body hoặc đọc `InputStream` vào một byte array không giới hạn.

HTTP response có thể **đã commit** sau khi bắt đầu gửi status, headers hoặc một phần body. Nếu backend lỗi giữa stream, Gateway không thể quay lại gửi 503 JSON mới trên cùng response. Thiết kế reconnect/resume và partial-result handling theo giao thức, thay vì áp retry như GET JSON ngắn.

## 13. Bảo vệ Gateway MVC bằng Spring Security Servlet

Gateway Server Web MVC dùng stack Spring MVC/Servlet, nên cơ chế Spring Security phù hợp là **`SecurityFilterChain` và `HttpSecurity`**. Nó khác với `SecurityWebFilterChain`/`ServerHttpSecurity` của WebFlux.

~~~mermaid
flowchart TD
    C["Client + Authorization header"] --> SF["Servlet Security FilterChain"]
    SF --> AUTH{"JWT hợp lệ? Có quyền?"}
    AUTH -->|Không| DENY["401 / 403"]
    AUTH -->|Có| DS["DispatcherServlet"]
    DS --> ROUTE["Gateway MVC RouterFunction"]
    ROUTE --> BACK["Outbound HTTP client → backend"]
    BACK --> RES["Response tới client"]
~~~

### Ví dụ Spring Security cho API stateless Bearer JWT

Giả sử public Catalog, private Orders và admin API đều đi qua Gateway. Một cấu hình minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class MvcGatewaySecurity {

    @Bean
    SecurityFilterChain gatewaySecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**")
                                .hasAuthority("SCOPE_admin")
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().denyAll()
                )
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                // Chỉ minh họa cho Bearer-only API không dùng cookie auth.
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
~~~

Và nguồn xác thực JWT **minh họa** trong cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/store
~~~

**Lưu ý bảo mật:**

1. `issuer-uri` phải trỏ tới IdP tin cậy thật của môi trường và cần xác minh **audience** phù hợp với API/Gateway; đừng mặc định validation issuer đã kiểm tra audience theo chính sách nghiệp vụ.
2. `SCOPE_admin` chỉ có giá trị nếu authority converter đã ánh xạ scope/admin claim đáng tin thành authority đó. Không tin `X-Role: admin` do client tự gửi.
3. `requestMatchers("/api/admin/**")` cần được kiểm thử cả exact base path `/api/admin`, trailing slash và các biến thể path. Tránh rule quá rộng `/api/**.permitAll()` đứng trước rule admin.
4. `csrf(csrf -> csrf.disable())` chỉ phù hợp với mô hình **Bearer-only stateless API** đã đánh giá rủi ro; nếu browser gửi session cookie/refresh cookie tự động thì phải thiết kế CSRF protection.
5. Nếu endpoint management/Actuator tồn tại, `anyRequest().denyAll()` trong ví dụ sẽ chặn các URL chưa khai báo — đó là hành vi cố ý. Cần tách security chain hoặc matcher thích hợp cho health/operations, không mở toàn bộ Actuator chỉ để readiness xanh.
6. **Authentication ở Gateway không thay backend authorization.** Backend vẫn phải xét quyền sở hữu đơn hàng, tenant, audience và quyền thao tác cụ thể.

### Không dùng Gateway route filter để thay SecurityFilterChain

Một Gateway before filter có thể từ chối request trước khi gọi backend, nhưng nó chỉ chạy **sau khi route tương ứng được chọn**. Nếu một endpoint khác được MVC controller hoặc Actuator handler phục vụ, filter route Catalog không áp vào đó. Authentication/authorization bảo vệ ranh giới HTTP nên đặt ở **Servlet Security FilterChain** hoặc cơ chế có phạm vi tương ứng.

### Khi public route nhận token hỏng

Một route được Spring Security `permitAll()` vẫn có thể trả lỗi authentication nếu client **chủ động gửi Bearer token hỏng** và resource server xử lý credential ấy. Đừng nhầm lỗi đó với route MVC không match hoặc Gateway before filter làm sai. Test public endpoint với **không token**, token hợp lệ và token hỏng riêng biệt.

## 14. Servlet filters khác Gateway filters như thế nào?

Có ba lớp filter dễ bị gọi chung bằng từ “filter”:

| Loại | API | Thời điểm/phạm vi | Ví dụ |
| --- | --- | --- | --- |
| **Servlet Filter** | `jakarta.servlet.Filter` và `FilterChain` | Bọc HTTP request trước/sau Servlet, có thể áp lên nhiều handlers | Security, encoding, tracing |
| **WebMvc.fn HandlerFilterFunction** | `org.springframework.web.servlet.function.HandlerFilterFunction` | Bọc một functional handler/route function | Logging hẹp, kiểm tra policy dành cho nhóm routes |
| **Gateway MVC before/after filters** | Những factory/functions của Spring Cloud Gateway Server MVC | Biến đổi request/response tại những vị trí Gateway DSL hỗ trợ | StripPrefix, rewrite, request/response headers |

**Servlet Filter có thể chạy trước route selection**, trong khi Gateway before/after filter thường gắn với một route đã match. Nếu muốn log mọi HTTP request—including 404 không khớp route, Actuator, internal controller—thì instrumentation ở servlet/server layer phù hợp hơn, nhưng phải bảo vệ dữ liệu nhạy cảm.

### 14.1. Mẫu HandlerFilterFunction quan sát thời gian thực thi handler

Ví dụ **Spring MVC WebMvc.fn thuần**:

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.ServerResponse;

final class MvcRouteTelemetry {
    private static final Logger log =
            LoggerFactory.getLogger(MvcRouteTelemetry.class);

    private MvcRouteTelemetry() {}

    static HandlerFilterFunction<ServerResponse, ServerResponse> timing() {
        return (request, next) -> {
            long startNanos = System.nanoTime();
            try {
                ServerResponse response = next.handle(request);
                log.debug("mvcHandler outcome=returned status={} elapsedMs={}",
                        response.statusCode().value(),
                        TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startNanos));
                return response;
            } catch (RuntimeException error) {
                log.warn("mvcHandler outcome=exception type={}",
                        error.getClass().getSimpleName());
                throw error;
            }
        };
    }
}
~~~

Mục tiêu đoạn code là **quan sát thời điểm functional handler trả `ServerResponse`**, không phải đo chính xác thời điểm toàn bộ response bytes tới client. Với body streaming, `next.handle(request)` có thể trả trước khi dữ liệu được truyền hết. Không dùng hàm này thay HTTP server access metrics hoặc network latency instrumentation.

**Không ghi** `request.headers()`, raw URI query, `Authorization`, `Cookie` hay exception message tùy ý vào logs. Nếu cần log route ID, lấy từ metadata cấu hình đã được quản lý, không lấy một chuỗi do client tự quyết định.

### 14.2. Servlet Filter và asynchronous dispatch

Khi MVC/Servlet async được sử dụng, một request có thể đi qua nhiều dispatch phases tùy dispatcher types và cách đăng ký filter. Một filter tự viết có thể chạy nhiều lần hoặc bỏ qua async/error dispatch nếu configuration không đúng. Không suy đoán “mỗi filter invocation luôn tương ứng một user request”; khi cần phải kiểm tra Servlet dispatcher type và test cancellation/error.

### 14.3. Error response và filter hậu kỳ

Nếu handler ném exception, `HandlerExceptionResolver`, MVC error handling hoặc Servlet container có thể tạo error response. Một Gateway after filter chỉ nhận response thành công từ handler **không nhất thiết thấy một exception đã thoát**. Tương tự, Servlet Filter có thể thấy exception trước khi MVC/Servlet error dispatch xử lý. Điều này ảnh hưởng metrics; hãy tách **handler returned**, **HTTP final status** và **error dispatch**.

## 15. Timeout, retry, circuit breaker và fallback trong kiến trúc MVC

Cả Gateway Web MVC lẫn WebFlux đều có thể cần bảo vệ backend khỏi lỗi dây chuyền, nhưng **filter factories, API và implementation không hoàn toàn giống nhau**. Không copy route filter `CircuitBreaker` hoặc `Retry` từ WebFlux mà mặc định mọi option đều hoạt động trên Web MVC.

### 15.1. Timeout là giới hạn cho từng giai đoạn

Một request đi qua:

~~~text
Client deadline
     |
Servlet inbound read / servlet processing
     |
Outbound pool acquire
     |
TCP connect / TLS handshake
     |
Backend response read
     |
Servlet write response
~~~

Tùy HTTP client và phiên bản, cần cấu hình **connect timeout, response/read timeout, pool acquire timeout**. Một timeout HTTP client **không mặc định là tổng deadline** từ khi client bắt đầu gửi đến lúc response hoàn tất. Nếu backend chậm, các threads/connections đang chờ có thể tích tụ.

### 15.2. Retry là nguồn khuếch đại tải

Nếu client retry 2 lần sau lần đầu, Gateway retry 2 lần sau lần đầu và SDK backend cũng retry 2 lần, số attempts lý thuyết tới dependency cuối có thể là:

\[
3 \times 3 \times 3 = 27
\]

Vì vậy:

- Chọn **một tầng chịu trách nhiệm retry chính** cho mỗi operation/dependency khi có thể.
- Chỉ retry những phương thức/lỗi đã được xác nhận an toàn, ví dụ GET idempotent gặp lỗi kết nối tạm thời.
- Dùng **retry budget**, backoff và jitter; ngừng khi operation đã quá deadline.
- Không retry POST thanh toán/đặt hàng nếu backend không hỗ trợ **idempotency** thực sự và deduplication.
- Không phát lại request body có stream/upload lớn nếu chưa xác minh khả năng replay và giới hạn memory.

### 15.3. Circuit breaker làm gì ở Gateway MVC?

Một CircuitBreaker khi được phiên bản MVC hỗ trợ có thể theo dõi lỗi/slow calls và tạm **short-circuit** yêu cầu outbound tới dependency suy giảm. Nó bổ sung cho timeout, rate limiting, health filtering và bulkhead.

~~~mermaid
flowchart TD
    R["Gateway MVC route"] --> CB{"Circuit permits call?"}
    CB -->|CLOSED hoặc probe HALF_OPEN| U["Outbound HTTP call"]
    CB -->|OPEN| FB["Fail fast / configured fallback"]
    U --> D["Backend"]
    D --> RES["Client response"]
    FB --> RES
~~~

**Trạng thái breaker** và semantics fallback phụ thuộc Spring Cloud CircuitBreaker/Resilience4j hoặc implementation của phiên bản MVC đã cấu hình. Chế độ fallback có thể có giới hạn về URI và response body. Nếu không rõ implementation, hãy bắt đầu bằng **503 an toàn, không lộ data**, thay vì giả vờ thao tác nghiệp vụ thành công.

### 15.4. Fallback không được che lỗi bảo mật

Không đổi 401/403 thành 200. Một fallback trả kết quả cached Orders cũng phải bảo vệ **đúng người dùng/tenant**, cache age và quyền tài nguyên. Với thao tác thanh toán, không trả `201 Created` khi backend chưa xác nhận commit. Fallback là một phần của **API contract**, không phải chỉ là cách làm hết biểu đồ 5xx.

## 16. Bảo toàn HTTP semantics và an toàn route

Một reverse proxy đúng không chỉ trả được JSON; nó còn phải giữ các quy tắc HTTP:

| Thành phần | Điều phải xác định | Lỗi thường gặp |
| --- | --- | --- |
| Method | GET/HEAD/POST/PATCH/DELETE được phép trên route nào? | Chấp nhận POST trên route chỉ dành cho đọc |
| URI/path | Rewrite và percent-encoding được xử lý ra sao? | Mất query, đổi encoded slash |
| Request headers | Header nào được copy, bỏ hoặc do Gateway tạo? | Lộ Authorization, Cookie hoặc spoof forwarded header |
| Request body | Có stream, buffer, nén hoặc body quá lớn không? | Đọc hết memory, lỗi Content-Length |
| Response status | Upstream status và Gateway fallback khác nhau thế nào? | Trả 200 giả khi backend 503 |
| Response headers | Cache-Control, Set-Cookie, Location, CORS, Vary | Cookie sai domain, redirect sang host ngoài |
| Response body | Có bị sửa ở trạng thái đã commit không? | JSON lỗi ghi nối vào SSE |
| TLS | Hop inbound/outbound có xác minh chứng chỉ? | Bỏ hostname verification cho nhanh |

### 16.1. Forwarded headers và ranh giới proxy

Trong một topology với ingress:

~~~text
Browser --HTTPS--> Ingress --HTTP(S)--> Gateway MVC --HTTPS--> Orders
~~~

Gateway có thể cần hiểu public host/scheme thật để dựng redirect, response link hoặc audit. Nhưng các header `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host` phải đến từ **proxy tin cậy**, không lấy mù từ client. Nếu một custom before filter dùng một forwarded host do client tự đặt để chọn outbound URI, có thể mở lỗ hổng SSRF.

### 16.2. Hai phía TLS khác nhau

TLS client → Gateway và TLS Gateway → backend là **hai kết nối độc lập**. Public HTTPS không tự bảo đảm backend cũng dùng HTTPS. Hãy kiểm tra CA/truststore, hostname/SAN, service identity và mTLS nếu cần. Một backend đích **không đáng tin** vẫn có thể nhận token dù dùng TLS hợp lệ; do đó cần cả **destination allowlist và audience policy**.

### 16.3. Headers hop-by-hop và proxy authentication

Không chuyển bừa `Connection`, `Upgrade`, `Proxy-Authorization` hoặc thông tin transport chỉ có nghĩa cho một hop. Với `Authorization`, chỉ forward khi service nhận **được phép và cần** credential đó, và backend tự xác minh. Không đưa refresh token/ID token của đăng nhập OIDC xuống các resource server nghiệp vụ.

### 16.4. CORS không phải authorization

Nếu frontend ở origin khác Gateway API, browser có thể gửi OPTIONS preflight. Cấu hình CORS ở lớp phù hợp để preflight được xử lý **trước authentication chặn nhầm**, nhưng request chính vẫn phải được authorize. Một `permitAll` cho OPTIONS không tự tạo hoặc kiểm tra `Access-Control-Allow-Origin`. CORS chỉ áp cho hành vi browser; HTTP client khác vẫn phải qua security.

## 17. Observability và Actuator của một Gateway Servlet

Một Gateway MVC cần quan sát **hai phía HTTP** và tình trạng runtime Servlet:

~~~mermaid
flowchart TD
    I["Inbound HTTP metrics"] --> Obs["Monitoring / tracing"]
    S["Servlet threads, busy/idle, connections"] --> Obs
    R["Gateway route ID, selected handler"] --> Obs
    C["Outbound HTTP client: pool / latency / errors"] --> Obs
    L["LoadBalancer / discovery results"] --> Obs
    F["Circuit breaker / retries / fallbacks"] --> Obs
    B["Backend status and latency"] --> Obs
~~~

Những câu hỏi quan trọng:

1. Request đi vào **Servlet container** nhưng bị chặn ở Security FilterChain, hay đã đi tới Gateway route?
2. `RouterFunctionMapping` đã chọn route nào? Có route nào chồng lấn không?
3. HTTP client đã gọi backend chưa, hay request bị short-circuit bởi rate limiter/circuit breaker?
4. Nếu gọi outbound, nó mất bao lâu ở **pool acquire, connect, TLS, response**?
5. Kết quả cuối client thấy là backend status, fallback status hay Servlet error response?
6. Khi lỗi tăng, **active/busy Servlet threads** và outbound pool có bị giữ hết không?

### 17.1. Những metrics nên có

| Metric khái niệm | Mục tiêu |
| --- | --- |
| Inbound HTTP requests theo method/status/route | Đo traffic và kết quả từ phía client |
| Duration p50/p95/p99 | Xác định latency tăng trên route |
| Servlet active/busy threads | Tìm exhaustion do handler/outbound blocking |
| HTTP outbound connections/pending requests | Tìm giới hạn pool hoặc connect problems |
| Upstream calls by service ID | Đo số lần gọi thật, phân biệt inbound với retry |
| 401/403 theo security outcome | Phân biệt auth từ lỗi backend |
| 404: route miss vs backend 404 | Tránh sửa nhầm RouterFunction |
| Circuit OPEN / fallback count | Biết khi service suy giảm nhưng response vẫn có thể là 200 |
| Retry attempts và retry budget | Phát hiện khuếch đại tải |
| TLS/connect/read failures | Phân tích lỗi transport |
| JVM heap/GC/CPU | Theo dõi resource pressure |

Tên metrics **phụ thuộc Spring Boot, Servlet container, HTTP client, Micrometer và Gateway MVC phiên bản**. Một số meters có thể chưa được bật, yêu cầu instrumentation hoặc phụ thuộc vào client implementation. Đừng tự khẳng định Spring Cloud Gateway MVC tự tạo tất cả các metric trên bằng một cấu hình duy nhất.

### 17.2. Actuator và management plane

Spring Boot Actuator có thể expose `health`, `info`, `metrics` và các management endpoints theo dependency/config. **Gateway-specific actuator capabilities của Server Web MVC có thể khác Server WebFlux theo phiên bản**, vì vậy kiểm tra tài liệu và endpoint mapping thực thay vì chắc chắn `/actuator/gateway/routes` có đầy đủ chức năng ghi/xóa route ở mọi dòng.

**Không bật `management.endpoints.web.exposure.include: "*"` trên public Gateway** chỉ để debug. Expose tối thiểu, dùng management port riêng nếu cần, network policy, TLS và Spring Security Servlet với quyền vận hành riêng. Route listing có thể chứa URI, metadata/filter arguments và cấu trúc service nội bộ.

### 17.3. Log an toàn

Một log hợp lý:

~~~text
route=catalog-read method=GET status=200 elapsedMs=42
upstreamService=catalog-service attempts=1
~~~

Không log:

~~~text
Authorization: Bearer <access-token>
Cookie: SESSION=<session-id>
GET /api/orders?access_token=<token>
Set-Cookie: SESSION=<session-id>
~~~

Đặc biệt trong hệ thống Servlet, **ingress access log, Tomcat access log, Spring Security DEBUG, outbound HTTP wire logs và APM agent** có thể thu thập dữ liệu khác với custom Gateway filter. Cần kiểm tra toàn bộ sink, hạn chế query/header capture và tránh token làm correlation/metric label.

### 17.4. Tracing qua hai hop

Một trace có thể nối các span:

~~~text
Client request
    -> Gateway MVC inbound HTTP span
         -> Gateway MVC outbound HTTP span
             -> Catalog service span
~~~

Tracing cần propagation an toàn qua hạ tầng như Micrometer/OpenTelemetry theo phiên bản. Không tin mọi trace header từ Internet là dữ liệu có thể dùng trực tiếp làm identity hoặc audit, và không đặt JWT/session cookie vào trace baggage. Nếu một request Gateway retry 2 attempts, tracing có thể hiển thị nhiều outbound spans thuộc một inbound span; **phải hiểu đơn vị đo**, không xem đó là hai user operations.

## 18. Backend stub để chứng minh đường đi qua Gateway MVC

Một bài học kiến trúc sẽ chưa đủ nếu chỉ nhìn cấu hình. Cần chứng minh **backend thực sự nhận method/path/header nào**, và response đi từ backend qua Gateway tới client.

Giả sử chạy một ứng dụng **Catalog stub riêng** trên cổng 9001. Một Spring MVC controller có thể mô phỏng backend:

~~~java
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogStubController {

    @GetMapping("/catalog/products/{id}")
    ResponseEntity<Map<String, Object>> getProduct(
            @PathVariable String id,
            @RequestHeader(
                    name = "X-Gateway-Source",
                    defaultValue = "missing"
            ) String gatewaySource
    ) {
        return ResponseEntity.ok(Map.of(
                "productId", id,
                "gatewaySource", gatewaySource,
                "backend", "catalog-stub-1"));
    }
}
~~~

**Yêu cầu lab:** Stub chạy trên server HTTP có cổng 9001, riêng với Gateway port 8080. `server.port=9001` thuộc **ứng dụng stub**, không thuộc Gateway. Nếu đang chạy nhiều services trong cùng máy/container, xác nhận đúng network namespace và tránh xung đột port.

Với cấu hình YAML ở phần 8, request:

~~~bash
curl -i 'http://localhost:8080/api/catalog/products/42'
~~~

có thể tạo response **minh họa**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"productId":"42","gatewaySource":"mvc-edge","backend":"catalog-stub-1"}
~~~

Đây là **kết quả kỳ vọng**, không phải lệnh đã chạy. Khi Spring Security theo phần 13 được bật với `/api/public/**` là public, request ở `/api/catalog/**` thuộc nhóm **cần authentication** theo rule `/api/**`. Trong trường hợp đó, **curl anonymous phải nhận 401**; cần cấp token hợp lệ cho route hoặc dùng một cấu hình security lab cho phép đọc Catalog. Không đổi security thành `permitAll()` cho mọi API chỉ để ví dụ trả 200.

### 18.1. Thống nhất cấu hình và test

Có hai phương án:

- **Lab routing thuần:** Không bật bảo mật ứng dụng trên Gateway thử nghiệm cô lập. Dùng curl anonymous để quan sát path/header và xác nhận backend nhận đúng request.
- **Lab security tích hợp:** Bật SecurityFilterChain đã thiết kế; dùng token JWT test hợp lệ cho `/api/catalog/**`, hoặc tạo route public cụ thể `/api/public/catalog/**` kèm predicate/security nhất quán.

Đừng trộn hai phương án rồi kết luận “Gateway proxy lỗi” khi thực ra Servlet security đang trả 401 trước khi tới RouterFunction.

### 18.2. Ma trận method/path

| Client request | Kỳ vọng route Catalog | Backend nhận gì nếu security cho phép? |
| --- | --- | --- |
| `GET /api/catalog/products/42` | Match | `GET /catalog/products/42` |
| `HEAD /api/catalog/products/42` | Match theo Method predicate | `HEAD /catalog/products/42`; body không được gửi cho client |
| `POST /api/catalog/products/42` | Không match route GET/HEAD | Không có request tới Catalog qua route này |
| `GET /api/other/products/42` | Không match | Không có request tới Catalog qua route này |
| `GET /api/catalog/products/42?lang=vi` | Match | Path được strip, query cần được giữ đúng |
| `GET /api/catalog/products/%2F42` | Phụ thuộc container/path decoding | Kiểm thử encoded slash và normalization thực |

**Không đồng nhất “route không match” với status 404 chắc chắn** nếu ứng dụng còn có controller hoặc route catch-all. Quan sát backend request counter hoặc trace an toàn để xác định request có thật sự đến Catalog không.

## 19. Kiểm thử end-to-end bằng Java HTTP client

Với MVC Gateway, `MockMvc` hữu ích để kiểm tra mapping/security ở lớp Spring MVC, nhưng khi cần chứng minh **gateway HTTP client outbound, TCP, TLS và header rewriting**, nên chạy **full HTTP integration test** với backend stub thực.

Ví dụ dùng JDK `java.net.http.HttpClient` và Spring Boot integration test:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CatalogMvcGatewayIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void routesRequestToCatalogStub() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(
                        "http://localhost:" + port
                                + "/api/catalog/products/42"))
                .GET()
                .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("productId"));
        assertTrue(response.body().contains("42"));
        assertTrue(response.body().contains("mvc-edge"));
    }
}
~~~

**Điều kiện để ví dụ có ý nghĩa:**

1. Ví dụ dùng **JDK HttpClient** và cú pháp tương thích Java 17. Việc quản lý vòng đời/đóng client phụ thuộc API JDK cụ thể; với test thực tế nên tái sử dụng client phù hợp, không tạo một pool mới cho mỗi request.
2. Gateway đang chạy ở RANDOM_PORT và route URI đến **Catalog stub 9001** đang hoạt động.
3. Nếu Spring Security đang bật, test phải có token test hợp lệ hoặc endpoint được permit theo policy; ví dụ này giả định **lab routing thuần**.
4. Cần `spring-boot-starter-test` (hoặc dependencies test tương ứng) và backend stub riêng.
5. Assertions trên JSON string chỉ minh họa; test tốt hơn dùng JSON parser và kiểm tra backend call counter.

**Chưa chạy test ở đây**; đây là cách xây test trong dự án của người học. Với môi trường real CI, nên dùng backend stub có cổng động và inject URI/route configuration để tránh port 9001 bị chiếm.

### 19.1. Một bộ kiểm thử không nên thiếu

| Tình huống | Kỳ vọng |
| --- | --- |
| GET route match | Đúng upstream, method/path/query/header |
| POST vào route chỉ GET | Không proxy qua route đó |
| Backend trả 404 | Phân biệt với 404 do không match route |
| Backend trả 503 | Không tự retry hoặc fallback khi chưa cấu hình |
| Backend TCP refused | HTTP client báo lỗi thích hợp, không treo vô hạn |
| Backend delay quá timeout | Request kết thúc theo deadline/fallback đã thiết kế |
| Backend TLS cert không tin | Kết nối phải thất bại, không tắt verification |
| lb:// không có instance | Không gửi request tới host tùy ý |
| User token thiếu quyền | Servlet Security chặn trước backend |
| Admin token đúng scope | Qua security; backend vẫn kiểm tra quyền nghiệp vụ |
| Client gửi header spoof | Không tạo principal/authority từ header client |
| Backend gửi Set-Cookie/redirect | Header được xử lý đúng trust boundary |
| Request body lớn | Không cache vô hạn, không đổi Content-Length sai |
| SSE gửi một phần rồi lỗi | Không ghi JSON 503 nối vào stream đã commit |
| Retry/breaker được bật | Đếm upstream attempts, kiểm tra fallback/status |

### 19.2. Security test và proxy test là hai loại bằng chứng khác nhau

`MockMvc` có thể xác minh rằng một request anonymous nhận 401 hoặc một admin token thiếu scope nhận 403 theo Servlet security. Nhưng nó **không tự xác minh** kết nối HTTP thực tới backend. Ngược lại, một integration test proxy nhận 200 không chứng minh JWT validation/audience/ownership đúng. Cần cả hai nhóm test với conditions và data riêng.

## 20. Hiệu năng Servlet Gateway: thread, connection và tải thực tế

Một Gateway thường làm việc “mỏng” hơn business service: nhận request, kiểm tra chính sách và proxy. Tuy nhiên nó vẫn có thể trở thành **điểm nghẽn** nếu backend chậm hoặc filter tự viết chặn thread.

### 20.1. Mô hình tài nguyên

~~~mermaid
flowchart LR
    C["N clients"] --> S["Servlet request capacity"]
    S --> F["MVC route + before filters"]
    F --> P["Outbound connection pool"]
    P --> U["Upstream capacity"]
    U --> P
    P --> S
    S --> C
~~~

Với xử lý blocking truyền thống, khả năng phục vụ có thể bị giới hạn bởi số request threads, số outbound connections, queue và thời gian chờ upstream. Nếu một request giữ thread trung bình \(W\) giây và arrival rate là \(\lambda\) request/giây, số request **đang xử lý trung bình** xấp xỉ theo định luật Little:

\[
L = \lambda W
\]

Ví dụ mô hình đơn giản:

- Gateway nhận 500 request/giây.
- Mỗi request tồn tại trung bình 0,2 giây trong hệ thống.
- Số request đồng thời trung bình xấp xỉ \(500 \times 0{,}2 = 100\).

Nếu backend chậm khiến thời gian trung bình tăng lên **2 giây**, số request đồng thời xấp xỉ **1.000** ở cùng arrival rate. Tùy implementation blocking/async, các request này có thể giữ threads, connections hoặc bộ nhớ theo mức khác nhau. **Đừng coi công thức này là công thức để đặt chính xác `maxThreads`**, vì còn queueing, phân phối latency, keep-alive, retries, async Servlet và tài nguyên ở nhiều hop.

### 20.2. Virtual threads có giải quyết hết không?

Những dòng Spring Boot/JDK hỗ trợ có thể tận dụng **Java virtual threads** cho các tác vụ blocking. Chúng có thể giảm chi phí giữ platform thread khi I/O chờ, nhưng:

1. Không làm backend nhanh hơn hoặc tăng số connection DB/TCP vô hạn.
2. Không xóa giới hạn outbound pool, file descriptors, heap hoặc socket buffers.
3. Không đảm bảo mọi HTTP client/filter/library đều virtual-thread-friendly.
4. Có thể gặp trường hợp pinning hoặc resource bottleneck; cần quan sát thực.
5. Không biến `Server Web MVC` thành `Server WebFlux` và không thay đổi API filter.

Nếu cân nhắc `spring.threads.virtual.enabled` trong dòng Spring Boot hỗ trợ, hãy benchmark và kiểm tra toàn bộ stack thay vì bật chỉ vì thấy Servlet threads bận.

### 20.3. Backpressure ở đâu?

Reactor/WebFlux có khái niệm backpressure ở mức Reactive Streams. Gateway MVC hoạt động trên Servlet/imperative stack; cần kiểm soát tải bằng **bounded queues, connection limits, timeouts, admission control, rate limit, bulkhead và streaming/buffering đúng API**. TCP cũng có flow control của riêng nó, nhưng đó **không tương đương** việc toàn bộ ứng dụng MVC tự có reactive backpressure end-to-end.

Khi gateway gặp 1.000 uploads lớn, việc đọc toàn body vào `byte[]` có thể làm bộ nhớ phình mạnh. Hãy đặt request-size limits, stream theo khả năng hỗ trợ và không cache body chỉ để retry hay log.

### 20.4. Một quy trình load test có ích

| Giai đoạn | Điều kiện | Tín hiệu cần quan sát |
| --- | --- | --- |
| Baseline | Backend trả 200 nhanh, không retry | Throughput, p95/p99, busy threads |
| Slow upstream | Backend delay có kiểm soát | Active requests, connection pool pending |
| No instance | Discovery rỗng | Error status, không chờ HTTP connect vô ích |
| Backend 503 | Stub trả lỗi | Retry attempts, circuit state, final status |
| Burst traffic | Tải tăng ngắn hạn | Rate limiter, queue growth, CPU |
| Large response | Tải xuống nhiều dữ liệu | Memory, socket throughput, body buffering |
| Cancellation | Client ngắt giữa stream | Cleanup, stale connections, server errors |

Không chạy bài thử tải như một cuộc tấn công vào production. Chọn một môi trường cô lập, backend stub, rate limits an toàn và mục tiêu latency/QPS được phê duyệt. **Không tối ưu chỉ theo HTTP 200**: cần đo lượng requests thực tới backend và những response lỗi/degraded có được phản ánh trung thực không.

## 21. Chẩn đoán lỗi theo đúng lớp của kiến trúc

Khi request không được proxy như mong đợi, hãy xác định **nó dừng ở lớp nào** thay vì tăng timeout hoặc bật log chứa credentials.

| Hiện tượng | Lớp cần điều tra đầu tiên | Hướng kiểm tra |
| --- | --- | --- |
| Startup báo không tạo được Servlet web server | Dependencies/web application type | Kiểm tra Starter Server Web MVC, Boot/Cloud BOM, không lẫn WebFlux |
| Java `RouterFunction` không compile | Package/API WebMvc.fn | Dùng `web.servlet.function`, kiểm tra Gateway MVC DSL theo release |
| YAML route không được nạp | Configuration binding | `gateway.mvc.routes` hay `gateway.server.webmvc.routes` đúng phiên bản? |
| `GET /api/catalog/...` trả 401 | Spring Security Servlet | Token? Path rule? Issuer/audience? |
| User thường vào được admin API | Security matcher/order | Rule admin có đứng trước rule rộng? Backend kiểm tra quyền chưa? |
| HTTP 404 trước khi gọi backend | Servlet HandlerMapping/RouterFunction | Predicate, method, context path, route overlap |
| Backend nhận path sai | Gateway before/path filter | StripPrefix/RewritePath, slash/query/encoding |
| Không có `lb://` instance | Discovery/LoadBalancer | Registry, service ID, health, instance metadata |
| Gateway trả 502/503 khi backend chạy | Outbound transport | DNS/TCP/TLS/HTTP client timeout; mTLS |
| GET route thành công nhưng POST không tới backend | Method predicate | Route có `Method=GET,HEAD`? |
| Header mới không thấy ở backend | Filter order/HTTP client | Filter đã gắn route? Header bị overwrite? |
| Body upload hỏng hoặc Content-Length sai | Request/response streaming | Body consumption, encoding, buffer lifetime |
| Response header thêm nhưng client không thấy | After filter/response commit | Header đã commit? Proxy phía trước có loại bỏ? |
| 200 ở Gateway nhưng client bị cắt stream | Network/streaming | Partial write, connection close, client cancel |
| Retry làm backend tăng tải mạnh | Retry ở nhiều tầng | Client/ingress/Gateway/SDK attempts; budget |
| Server threads bận nhưng CPU thấp | Blocking I/O hoặc pool chờ | Thread dump, outbound pool, slow backend |
| Servlet Security config không chạy như mong đợi | Dùng nhầm stack reactive | Có lỡ dùng `SecurityWebFilterChain` thay `SecurityFilterChain`? |
| Actuator route listing không có endpoint mong đợi | Management capability/version | Endpoint có hỗ trợ MVC? Enabled/exposed/security/path? |
| Tracing thiếu backend span | HTTP client instrumentation | Kiểm tra propagation và client integration |

### 21.1. Quy trình 10 bước

1. **Cổng nào nhận request?** Xác minh ingress, host, TLS scheme và Servlet server listener.
2. **Servlet Security có cho qua không?** 401/403 có thể xảy ra trước Gateway route.
3. **DispatcherServlet chọn HandlerMapping nào?** Có WebMvc.fn route, annotation controller hay Actuator handler?
4. **Route nào match?** Kiểm tra path/method/host/header và order.
5. **Before filters thay gì?** So sánh path/query/header trước và sau, không dump token.
6. **URI đích là gì?** Static host hay `lb://`? Nếu lb, instance được chọn thế nào?
7. **Outbound HTTP client làm gì?** DNS, pool acquire, connect, TLS, request write, response read.
8. **Backend có nhận request không?** Dùng stub counter hoặc backend trace ID an toàn.
9. **Response do ai tạo?** Backend thật, Gateway fallback, Servlet error handler hay security layer?
10. **Resource pressure thế nào?** Busy threads, pool, queue, memory, retry attempts và circuit state.

**Đừng bật logging raw Authorization, Cookie hoặc request body** chỉ để phân biệt hai lớp. Có thể dùng route ID, method, final status, sanitized exception type, backend identifier và trace ID do hệ thống quản lý.

### 21.2. Khi nâng cấp Spring Cloud Gateway

Vì namespace và API giữa các dòng có thể thay đổi, mọi lần nâng cấp cần:

- Đối chiếu **Spring Boot + Spring Cloud BOM**, starter Server Web MVC và package imports.
- Kiểm tra tất cả route definitions đã được bind vào **đúng namespace**.
- Kiểm tra Java DSL và các before/after filters theo release.
- Chạy negative tests cho security và management port.
- Kiểm chứng URI/path/query rewriting, header forwarding và service discovery.
- Chạy HTTP integration tests với backend stub cho 2xx, 4xx, 5xx, timeout, streaming.
- So sánh busy threads, outbound pool, latency và retry attempts trước/sau.

Không dựa vào việc ứng dụng khởi động thành công để kết luận một route viết bằng property cũ vẫn tồn tại.

## 22. Bài thực hành tổng hợp: xây Gateway Server Web MVC cho Catalog và Orders

**Bối cảnh:** Một nhóm muốn chuyển một cổng vào đơn giản từ thiết kế demo sang Gateway Server Web MVC chạy Servlet. Client phải gọi một API duy nhất; Catalog public, Orders private, còn endpoint quản trị phải được cô lập. Phần thực hành không yêu cầu dự án WebFlux.

### Phần A — Xây hệ thống

1. Chọn **Spring Boot/Cloud BOM tương thích**, Gateway Server Web MVC starter đúng tên của release, thêm Spring Cloud LoadBalancer khi cần.
2. Tạo ứng dụng `MvcGatewayApplication`, nghe trên port 8080.
3. Dựng Catalog stub port 9001, Orders stub port 9002 trên lab; mỗi stub trả một trường `handledBy` và ghi request count trong bộ nhớ thử nghiệm.
4. Tạo route Catalog `GET /api/catalog/**` với `StripPrefix=1`; Orders `GET /api/orders/**` cũng strip đúng path.
5. Dùng **một** trong YAML hay Java DSL cho Catalog ở giai đoạn đầu; sau đó thử hình thức còn lại trong một profile/test khác để không có hai route chồng lấn.
6. Test bằng `curl`/JDK HttpClient rằng backend thật nhận đúng path/query/header.

### Phần B — Bảo mật

1. Dùng Servlet **`SecurityFilterChain`**, không dùng WebFlux `SecurityWebFilterChain`.
2. Cấu hình một route public `/api/public/catalog/**` hoặc dùng policy tương ứng với `/api/catalog/**`; đảm bảo path của security matcher và Gateway predicate thống nhất.
3. Với Orders, yêu cầu Bearer JWT đúng issuer, audience và scope. Backend Orders tiếp tục kiểm tra quyền sở hữu đơn hàng.
4. Ngăn cookie, token hoặc API key được gửi tới Catalog public khi không cần; không dùng client-supplied header làm quyền.
5. Nếu bật Actuator, chỉ expose health/metrics cần thiết trên management network có bảo vệ; không công khai route mutation.

### Phần C — Service discovery và độ tin cậy

1. Đổi URI Orders từ static HTTP sang `lb://orders-service` khi nguồn ServiceInstance test đã sẵn sàng.
2. Mô phỏng hai Orders instances; xác minh request được chuyển tới instance thật từ load balancing.
3. Gỡ một instance khỏi discovery/readiness và xem hệ thống xử lý; không giả định Gateway sẽ retry vô hạn.
4. Gây connect refusal, backend 503 và response delay bằng stub. Chọn timeout có giới hạn và xác nhận lỗi theo contract.
5. Nếu thêm retry/circuit breaker, chỉ dùng những factories được Gateway MVC version hỗ trợ, có **budget, idempotency và test counter**.
6. Thử HTTPS tới upstream test với chứng chỉ tin cậy; lỗi certificate phải bị từ chối, không tắt xác minh hostname.

### Phần D — Kiểm tra request/response biên

| Test | Điều cần chứng minh |
| --- | --- |
| GET Catalog thường | Đúng `/catalog/products/42` tại stub |
| GET kèm query | Không mất `?lang=vi` |
| POST vào route GET-only | Không gửi tới backend qua route đó |
| Client gửi `X-User-Role: ADMIN` | Không được cấp quyền admin |
| Anonymous gọi Orders | Bị chặn bởi Servlet Security trước backend |
| Token user hợp lệ gọi Orders | Đúng route; backend kiểm tra quyền tài nguyên |
| Backend 404 | Không nhầm với route miss |
| Không có instance trong discovery | Không tự proxy sang host tùy ý |
| Backend TLS handshake failure | Bị từ chối an toàn |
| Header Cookie/Authorization vào Catalog public | Không bị chuyển khi route contract không cần |
| SSE gửi dở rồi lỗi | Không cố thay response 200 đã commit thành 503 JSON |
| Response body lớn | Không buffer vô hạn hoặc hỏng Content-Length |
| Retry được bật trong lab | Số attempts không vượt giới hạn; không tạo side effect trùng |
| 2 Gateway replicas | Route/config và Security behavior nhất quán |

### Phần E — Đo hiệu năng

1. Test Catalog backend trả nhanh; lấy baseline QPS, p95/p99 và Servlet busy threads.
2. Thêm delay có kiểm soát ở backend; quan sát outbound pool và concurrent requests.
3. Bật rate limiting/bulkhead phù hợp nếu cần và so sánh.
4. Không bật retry ở cả client/Gateway/backend cùng lúc mà không có budget; đo attempts thực ở stub.
5. Thu thập health/metrics/tracing **không chứa token, Cookie hoặc raw URL query**.
6. Thử lớn dần trên lab có giới hạn; báo cáo tại sao bottleneck nằm ở thread, pool hay upstream.

### Phần F — Báo cáo cần nộp

Ghi rõ:

- Spring Boot/Gateway versions, tên starter và namespace YAML thật sự được dùng.
- Sơ đồ Servlet container → FilterChain → DispatcherServlet → RouterFunction → handler → HTTP client.
- Danh sách route ID, predicate, before/after filter và URI đích.
- Bằng chứng backend stub nhận đúng path, header, method và số request.
- Ma trận security (anonymous/user/admin), CORS và quyền management.
- Kết quả lỗi connect/TLS/503, timeout/retry/fallback khi có cấu hình.
- Metrics về busy threads, outbound connections và latency.
- Rủi ro còn lại, quyết định về streaming/body handling và phương án rollout/rollback.

**Tiêu chí đạt:** Người học mô tả đúng vai trò **Servlet/WebMvc.fn**, chạy Gateway MVC với ít nhất một route proxy thực, xác minh security và rewrite qua backend stub, phân biệt lỗi từng lớp, không dùng nhầm WebFlux API và không làm lộ credentials khi quan sát request.

## 23. Những hiểu lầm phổ biến

| Nhận định sai | Điều đúng |
| --- | --- |
| “Gateway nào cũng dựa trên WebFlux.” | Spring Cloud Gateway có **Server Web MVC** dựa trên Servlet/WebMvc.fn và biến thể Server WebFlux riêng. |
| “Thêm spring-boot-starter-web vào Gateway WebFlux là đã đổi sang MVC.” | Phải dùng **Gateway Server Web MVC starter** và API/config phù hợp. |
| “WebMvc.fn chỉ là WebFlux.fn đổi package.” | WebMvc.fn dùng `web.servlet.function` và handler trả `ServerResponse` trực tiếp. |
| “`RouterFunction` là Servlet Filter.” | RouterFunction match handler; Servlet Filter nằm ở lớp Servlet FilterChain. |
| “Gateway before filter luôn chạy cho mọi HTTP request.” | Nó thuộc route tương ứng; Actuator/controllers khác có thể không đi qua. |
| “Route match rồi nghĩa là upstream healthy.” | Route selection khác discovery, connection, TLS và backend response. |
| “`GlobalFilter`/Mono<Void> WebFlux có thể copy vào Gateway MVC.” | Hai filter/runtime models khác nhau. |
| “`SecurityWebFilterChain` bảo vệ MVC Gateway.” | Dùng Spring Security **Servlet SecurityFilterChain** cho MVC stack. |
| “Header `X-User-Role` chứng minh quyền admin.” | Header client không phải authority; dùng principal đã xác thực. |
| “Dùng `lb://` là có load balancing khỏe và bảo mật.” | Cần nguồn ServiceInstance tin cậy, health, TLS và backend authorization. |
| “HTTP client timeout bằng tổng deadline của client.” | Connect/read/pool/request timeout có semantics khác nhau. |
| “Dùng virtual threads là không cần giới hạn outbound pool.” | Virtual threads không làm dependency hoặc sockets vô hạn. |
| “After filter có thể đổi status khi response đã stream một phần.” | Status/headers đã commit không thể thay lại trên cùng response. |
| “Bật retry luôn cải thiện tỉ lệ thành công.” | Nhiều tầng retry có thể khuếch đại tải và lặp side effects. |
| “Có Actuator là mọi Gateway MVC route endpoint giống WebFlux.” | Capability và mappings phụ thuộc biến thể/phiên bản; kiểm tra implementation thật. |
| “HTTP 200 qua Gateway chứng minh auth, path và backend đều đúng.” | Phải kiểm tra source response, upstream counter, token/audience và quyền tài nguyên. |

## 24. Tổng kết

- **Gateway Server Web MVC** là biến thể Spring Cloud Gateway dựa trên **Servlet container + Spring MVC + WebMvc.fn**. Nó vẫn giải quyết routing, filters, service discovery và độ tin cậy của cổng vào microservices, nhưng **không dùng cùng runtime/filter contract** như Gateway Server WebFlux.
- Request thường đi qua **Servlet FilterChain**, **DispatcherServlet**, **RouterFunctionMapping**, **HandlerFunctionAdapter**, rồi **Gateway MVC before/handler/after** và HTTP client outbound tới backend.
- `RouterFunction<ServerResponse>`, `ServerRequest` và `HandlerFunction<ServerResponse>` thuộc **`org.springframework.web.servlet.function`**; không import nhầm từ `web.reactive.function.server`.
- Java DSL của Gateway MVC có thể dùng `GatewayRouterFunctions.route`, `HandlerFunctions.http` và các before filter functions; YAML route thường có `id`, `uri`, `predicates` và `filters`. **Starter và namespace thay đổi theo release**, vì vậy cần kiểm tra BOM thực tế.
- **Servlet Filter và SecurityFilterChain** bảo vệ inbound HTTP ở lớp khác với route-specific Gateway MVC filters. Authentication/authorization không được thay bằng `Path`, `Host` hoặc header do client tự đặt.
- `lb://` giải quyết lựa chọn instance nếu integration phù hợp, nhưng không thay thế kiểm tra service identity, readiness, TLS và backend authorization.
- HTTP client outbound, Servlet threads, timeout, pool, body streaming và memory là những giới hạn tài nguyên cần quan sát. **Virtual threads không thay đổi mô hình WebMvc.fn thành WebFlux**.
- Retry, circuit breaker, rate limiting, fallback và Actuator có thể hữu ích nhưng **capability/configuration phải khớp Gateway Server MVC version**; không copy mù cấu hình WebFlux.
- Chỉ coi kiến trúc hoạt động đúng khi đã **kiểm chứng method/path/query/header thật ở backend**, phân biệt lỗi security/route/transport/upstream và thử các tình huống timeout, encoded URL, TLS, streaming cùng load.

Nắm chắc **Servlet, DispatcherServlet và WebMvc.fn** giúp bạn biết chính xác **request đang ở tầng nào, ai chọn route, ai gọi backend và ai có quyền thay đổi response**, từ đó xây dựng Spring Cloud Gateway Server Web MVC an toàn, dễ kiểm thử và vận hành có kiểm soát.
