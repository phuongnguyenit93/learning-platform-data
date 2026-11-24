# Tích hợp Spring Security với SecurityWebFilterChain trong Spring Cloud Gateway

Một API Gateway thường là điểm vào chung của nhiều microservices. Nếu Gateway định tuyến đúng nhưng không xác thực người gọi hoặc không kiểm soát quyền truy cập, một URL public có thể trở thành đường đi đến dữ liệu nội bộ. Với **SPRING_CLOUD_GATEWAY** chạy trên **Spring WebFlux**, nền tảng quan trọng để bảo vệ HTTP request là **Spring Security reactive**, được cấu hình thông qua **`SecurityWebFilterChain`** và **`ServerHttpSecurity`**.

Bài học thuộc chương **Xác thực và phân quyền**, tập trung vào cách đưa Spring Security vào Gateway Server WebFlux: tổ chức chuỗi bảo mật trước route matching, xác thực JWT theo mô hình OAuth2 Resource Server, phân quyền theo public path và HTTP method, xử lý mã `401`/`403`, phối hợp CORS/CSRF và chuyển thông tin danh tính đến downstream an toàn. Các ví dụ kết nối với route predicate, filter chain, biến đổi đường dẫn/header, service discovery, rate limiting, circuit breaker, retry, TLS và quan sát request, nhưng **mỗi nhóm chức năng cần chính sách riêng**.

> **Phạm vi:** Ví dụ hướng đến **Spring Cloud Gateway Server WebFlux**, Spring Security reactive theo cách cấu hình phổ biến trong Spring Security 6.x / Spring Boot 3.x. Tên starter, namespace Gateway và DSL có thể khác ở các dòng phát hành khác. **Gateway Server MVC dùng Servlet security (`SecurityFilterChain` / `HttpSecurity`), không dùng trực tiếp mã `SecurityWebFilterChain` dưới đây.** Chọn đúng tài liệu theo release train trước khi áp dụng.

## 1. Ba câu hỏi khác nhau: định tuyến, xác thực và phân quyền

Ví dụ client gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Gateway cần giải quyết ba vấn đề riêng:

| Câu hỏi | Thành phần tiêu biểu | Ý nghĩa |
|---|---|---|
| Request nên đến dịch vụ nào? | `RoutePredicateHandlerMapping`, `Route`, `Path`/`Method` predicates | **Định tuyến**: chọn downstream và gateway filters |
| Ai đang gọi API? | Spring Security `AuthenticationWebFilter` / OAuth2 Resource Server | **Xác thực**: xác minh token/credentials và xây `Authentication` |
| Người này được làm gì? | `SecurityWebFilterChain`, `authorizeExchange` và policy của backend | **Phân quyền**: quyết định có cho phép thao tác hay không |

**Một route match không có nghĩa request được phép truy cập.** Ngược lại, một access token hợp lệ không bảo đảm request match route hoặc backend có thể phục vụ nó.

Ví dụ:
- JWT hợp lệ với quyền `orders.read` có thể đọc `GET /api/orders/42`.
- Cùng JWT không nhất thiết được phép `POST /api/orders`, vì đây là hành động ghi dữ liệu.
- JWT hợp lệ nhưng route `/api/unknown` không tồn tại vẫn không tạo ra route mới.
- Không có JWT có thể bị từ chối ở tầng security **trước khi Gateway tìm route**.

### Sơ đồ tổng thể

~~~mermaid
flowchart TD
    C["Client: HTTP request"] --> W["Spring WebFlux WebFilter chain"]
    W --> SEC{"Spring Security: xác thực và phân quyền"}
    SEC -->|Không có / token sai| U["401 Unauthorized"]
    SEC -->|Đủ xác thực nhưng thiếu quyền| F["403 Forbidden"]
    SEC -->|Được phép| HM["Gateway: RoutePredicateHandlerMapping"]
    HM -->|Không match route| N["Không có route / handler phù hợp"]
    HM -->|Match| GF["FilteringWebHandler: GlobalFilter + GatewayFilter"]
    GF --> RW["RewritePath / Headers / Rate limit / Circuit breaker"]
    RW --> LB["Routing: URI tĩnh hoặc lb://service-id"]
    LB --> DS["Downstream kiểm tra quyền nghiệp vụ"]
    DS --> R["Response về Gateway và client"]
~~~

Sơ đồ thể hiện kiến trúc khái niệm. `WebFilter` của Spring Security là một tầng HTTP của WebFlux, còn `GatewayFilter` chỉ tham gia khi route Gateway đã được chọn. Những cơ chế như CORS hoặc xử lý lỗi có thể can thiệp sớm ở những tầng liên quan.

## 2. Vì sao Gateway WebFlux cần SecurityWebFilterChain?

Trong Spring Security có hai hệ API dễ nhầm:

| Web stack | Cấu hình security | API chính |
|---|---|---|
| **Reactive WebFlux** | `SecurityWebFilterChain` | `ServerHttpSecurity`, `WebFilter`, Reactor `Mono`/`Flux` |
| **Servlet / Spring MVC** | `SecurityFilterChain` | `HttpSecurity`, Servlet `Filter` |

Spring Cloud Gateway **Server WebFlux** dùng kiến trúc bất đồng bộ, non-blocking. Do đó:

- Viết bean `SecurityWebFilterChain`, không chỉ bean `SecurityFilterChain` của Servlet.
- Sử dụng `ServerHttpSecurity` để định nghĩa matcher, authentication và authorization.
- Khi xử lý thông tin security bằng code tùy biến, sử dụng reactive API và Reactor Context; không mặc định principal nằm trong `ThreadLocal` của một servlet thread.
- Tránh gọi `block()` trong reactive security/filter chain; thao tác blocking có thể làm nghẽn event-loop hoặc tăng latency.

Một ứng dụng WebFlux thông thường có thể có nhiều `WebFilter`, trong đó Spring Security tổ chức các filter của mình trong `SecurityWebFilterChain`. Các filter này bảo vệ request **trước** khi đến handler/routing của Gateway theo thiết lập security tương ứng.

### SecurityWebFilterChain khác GatewayFilterChain

| Đặc tính | `SecurityWebFilterChain` | `GatewayFilterChain` |
|---|---|---|
| Thuộc thư viện | Spring Security reactive | Spring Cloud Gateway |
| Đầu vào cấu hình | `ServerHttpSecurity` và security matchers | `GlobalFilter` / `GatewayFilter` của route |
| Phạm vi | Request HTTP phù hợp với security chain, kể cả request không match Gateway route | Request đã chọn route Gateway |
| Vai trò | Xác thực, phân quyền, xử lý security | Biến đổi request/response, routing, resilience |
| Có sẵn khi chỉ khai báo route YAML? | Cần có Spring Security cấu hình/dependency thích hợp | Có trong Gateway Server WebFlux |

**Lỗi nguy hiểm:** chỉ thêm `GatewayFilter` kiểm tra một header `X-User-Role` do client gửi rồi nghĩ đã thực hiện phân quyền. Header đầu vào có thể bị giả mạo. Dùng security framework để xác thực danh tính và policy đáng tin cậy.

## 3. Phụ thuộc cần thiết

Giả sử một dự án Maven hoặc Gradle được quản lý bởi **Spring Boot BOM** và **Spring Cloud BOM** tương thích.

Các thành phần chức năng thường cần là:

- Starter **Spring Cloud Gateway Server WebFlux** của release train đang sử dụng.
- `spring-boot-starter-security` để có Spring Security.
- `spring-boot-starter-oauth2-resource-server` để xác minh Bearer JWT hoặc token theo cơ chế resource server.
- Nếu URI dùng `lb://`, bổ sung Spring Cloud LoadBalancer và DiscoveryClient phù hợp, **không phải dependency của SecurityWebFilterChain**.

Ví dụ phần phụ thuộc Gradle (chỉ minh họa tên artifact của dòng hỗ trợ):

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    // Chỉ cần khi route sử dụng lb:// và runtime chưa có load balancer:
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

**Không tự khóa version tùy ý cho từng dependency** khi dự án đã sử dụng BOM tương thích. Tên Gateway starter có thay đổi giữa các dòng (`spring-cloud-starter-gateway` cũng xuất hiện trong tài liệu nhiều bản cũ), nên kiểm tra artifact và release train đúng dự án. Không thêm `spring-boot-starter-web` (Servlet) chỉ để “kích hoạt Spring Security” cho ứng dụng Gateway WebFlux.

## 4. Cấu hình một SecurityWebFilterChain cho API dùng Bearer JWT

Giả định Gateway công khai ba nhóm endpoint:

- `GET /api/orders/**` yêu cầu authority `SCOPE_orders.read`.
- `POST /api/orders/**` yêu cầu authority `SCOPE_orders.write`.
- `/api/admin/**` yêu cầu authority `SCOPE_admin`.
- `/actuator/health` được đọc công khai theo chính sách ví dụ; các endpoint quản trị khác không mở mặc định.

Đây là **một policy minh họa**, không phải tập scope chuẩn có sẵn của Spring hay của hệ thống OAuth2.

~~~java
package example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain gatewaySecurityWebFilterChain(ServerHttpSecurity http) {
        return http
            // Chỉ phù hợp nếu API này là stateless Bearer-token
            // và không dựa vào cookie session để xác thực.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)

            .authorizeExchange(exchanges -> exchanges
                // Chỉ cho request OPTIONS đi qua bước phân quyền;
                // vẫn cần cấu hình CORS đúng ở tầng tương ứng.
                .pathMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()

                .pathMatchers("/actuator/health").permitAll()

                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .pathMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")

                // Fail closed: route mới không tự được cấp quyền.
                .anyExchange().denyAll()
            )

            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

### Cách đọc từng đoạn

1. `@EnableWebFluxSecurity` bật cấu hình Spring Security cho WebFlux trong cách tổ chức Java config này.
2. `@Bean SecurityWebFilterChain` cung cấp quy tắc cho reactive security pipeline.
3. `authorizeExchange` khai báo rule **theo request path và method mà Gateway nhận**, không phải path sau `StripPrefix`.
4. `hasAuthority("SCOPE_orders.read")` đòi authority được thiết lập từ xác thực. Với Bearer JWT resource server và cách map scope mặc định của Spring Security, scope `orders.read` thường được biểu diễn thành authority `SCOPE_orders.read`.
5. `anyExchange().denyAll()` là **mặc định từ chối** cho các path/method không khai báo. Nếu dự án muốn policy khác, phải quyết định rõ và kiểm thử.
6. `oauth2ResourceServer(...jwt(...))` kích hoạt việc xác thực Bearer JWT thông qua `ReactiveJwtDecoder` được auto-configure hoặc do ứng dụng định nghĩa.

**Lưu ý về `denyAll()`:** một request chưa được policy cho phép có thể nhận `401` hoặc `403` ở tầng security **trước khi Gateway kịp xác định có route hay không**. Nếu muốn các URL công khai nhận `404` theo đúng định tuyến, hãy thiết kế vùng public/security matcher rõ ràng. Không dùng `permitAll()` toàn cục chỉ để “đẹp mã 404”.

### CSRF là quyết định theo mô hình xác thực

Dòng `.csrf(ServerHttpSecurity.CsrfSpec::disable)` trong ví dụ **chỉ hợp lý khi Gateway thật sự vận hành API stateless dùng Bearer token trong header, không dựa vào credential được trình duyệt tự gắn như cookie session**. Nếu ứng dụng có `oauth2Login`, form login, session cookie hoặc chức năng cần chống CSRF, **không sao chép việc disable CSRF**; cấu hình bảo vệ phù hợp và kiểm thử từng luồng.

## 5. Cấu hình nơi xác minh JWT

Một OAuth2 Resource Server cần biết cách xác minh chữ ký và claims của token. Ví dụ Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

`issuer-uri` phải khớp **issuer thật** của Identity Provider, và nhà cung cấp cần có metadata/JWKs phù hợp để Spring Security có thể xác minh JWT. Domain ở đây chỉ để minh họa: cấu hình này **không thể chạy nếu không có Identity Provider thực**.

Khi dùng OAuth2 resource server với JWT, các bước phổ biến:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security ở Gateway
    participant IDP as Identity Provider / JWKS
    participant G as Gateway route filters
    participant B as Backend
    C->>S: Authorization: Bearer access-token
    S->>IDP: Lấy metadata/JWKs khi cần (có cache theo implementation)
    IDP-->>S: Public keys / metadata
    S->>S: Xác minh chữ ký, thời hạn, issuer và validators
    S->>S: Chuyển claims/scope thành Authentication và authorities
    alt Không xác thực được
        S-->>C: 401
    else Thiếu authority
        S-->>C: 403
    else Được phép
        S->>G: Chuyển đến Gateway handler/filters
        G->>B: Forward request theo policy
        B-->>C: Response qua Gateway
    end
~~~

Sơ đồ **không có nghĩa mọi request đều gọi Identity Provider**: việc lấy/cached public keys và metadata phụ thuộc decoder và cấu hình. JWT có thể được xác minh cục bộ bằng public key đã biết. Không thực hiện một HTTP request remote cho mọi JWT chỉ vì nhìn sơ đồ.

### Những claims nào được kiểm tra?

| Thông tin | Vai trò | Ghi chú |
|---|---|---|
| **Chữ ký** | Chống token bị chỉnh nội dung | Phải xác minh bằng thuật toán/key được tin cậy |
| `exp` | Thời điểm hết hạn | JWT hết hạn phải bị từ chối theo validator phù hợp |
| `nbf` | Chưa có hiệu lực trước thời điểm | Phụ thuộc validator/claim có mặt |
| `iss` | Issuer | Cần khớp issuer đã tin cậy |
| `aud` | Đối tượng token hướng tới | **Không mặc định giả định đã được kiểm tra cho API của bạn**; cần thêm audience validation khi yêu cầu |
| `scope` hoặc `scp` | Phạm vi quyền | Có thể ánh xạ sang authorities `SCOPE_...` theo converter mặc định |
| `sub` | Định danh principal | Không tự chứng minh có quyền đọc tất cả dữ liệu của user khác |

**Token được ký đúng không đồng nghĩa đủ quyền.** Một JWT có `iss` hợp lệ nhưng `aud` dành cho API khác vẫn có thể không phù hợp cho Gateway này. Nếu contract yêu cầu audience cụ thể, cấu hình `ReactiveJwtDecoder` với validators cho `aud` và kiểm thử token sai audience.

**Không hardcode khóa bí mật/JWT thật trong YAML hoặc log.** Với JWT bất đối xứng, backend/Gateway thường dùng public keys từ JWK Set được tin cậy; hệ thống cần chính sách key rotation, cache, thời gian và TLS đến Identity Provider.

### Ủy quyền theo scope/role khác nhau thế nào?

Mặc định JWT resource server có thể chuyển scope như `orders.read` thành `SCOPE_orders.read`. Tuy nhiên, nếu Identity Provider đặt role ở claim riêng như `realm_access.roles` hoặc `roles`, bạn thường cần **converter phù hợp** để map sang authorities dùng bởi `hasAuthority`. Không tự giả định Spring Security sẽ đọc mọi claim role.

So sánh:

~~~text
JWT scope: "orders.read orders.write"
 -> authorities (theo mapping scope mặc định):
    SCOPE_orders.read
    SCOPE_orders.write

JWT roles: ["ADMIN"]
 -> không nhất thiết tự sinh ROLE_ADMIN
    nếu chưa có converter tương ứng
~~~

Ngoài ra `hasRole("ADMIN")` thường làm việc với convention authority `ROLE_ADMIN`, còn `hasAuthority("SCOPE_admin")` kiểm tra **đúng** authority có tên `SCOPE_admin`. Hai cách dùng **không tương đương**.

## 6. Route predicates và security rules: thứ tự nào được kiểm tra?

Giả định route:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=GET
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Edge-Service,orders
~~~

Dưới policy phần 4, request `GET /api/orders/42` có trình tự logic:

1. Spring Security kiểm tra Bearer token và authority `SCOPE_orders.read` theo **public path `/api/orders/42`**.
2. Nếu không qua security, request bị từ chối; backend không được gọi.
3. Nếu qua security, Gateway mới chọn `orders-api` nhờ `Path` và `Method`.
4. Filter `StripPrefix=1` thay path `/api/orders/42` thành `/orders/42`.
5. Header `X-Edge-Service: orders` được đặt trên request forward.
6. Backend nhận request và vẫn cần kiểm tra quyền nghiệp vụ (ví dụ đơn hàng 42 có thuộc người dùng hay không).

**Đừng viết security rule theo `/orders/42` chỉ vì `StripPrefix` tạo ra URL ấy ở downstream.** Security matcher ở Gateway nhìn đường dẫn **trước** filter rewrite.

### Thứ tự các rule trong authorizeExchange

Quy tắc chi tiết nên đặt **trước** quy tắc bắt tất cả:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyExchange().denyAll()
)
~~~

Nếu đặt `anyExchange().permitAll()` hoặc matcher bao phủ toàn bộ trước rule bảo vệ cụ thể, rule cụ thể có thể không bao giờ được xét. Không xem một `Gateway RoutePredicate` cùng path là phương tiện thay thế việc định nghĩa security rule này.

## 7. HTTP 401, 403 và những response dễ bị chẩn đoán nhầm

**401 Unauthorized** thường xuất hiện khi request cần xác thực nhưng **không có credentials hợp lệ**: thiếu Bearer token, token hết hạn, chữ ký sai, issuer sai hoặc token không parse được.

**403 Forbidden** thường xuất hiện khi principal đã được xác thực nhưng **không đủ authority** để thực hiện thao tác, hoặc khi một chính sách từ chối rõ ràng.

| Request đến Gateway | Kết quả security dự kiến trong policy demo | Có gọi backend không? |
|---|---|---|
| GET `/api/orders/42` không có token | `401` | Không |
| GET `/api/orders/42` với JWT hỏng | `401` | Không |
| GET `/api/orders/42` JWT hợp lệ chỉ có `SCOPE_orders.write` | `403` | Không |
| GET `/api/orders/42` JWT có `SCOPE_orders.read` | Qua security; kết quả tiếp theo tùy route/backend | Có nếu route match và routing thành công |
| POST `/api/orders/42` JWT chỉ có `SCOPE_orders.read` | `403` | Không |
| POST `/api/orders/42` JWT có `SCOPE_orders.write` | Qua security; nhưng route demo chỉ cho `Method=GET` | Không theo route demo; có thể 404 |
| GET `/api/unknown` với JWT hợp lệ | `403` do `denyAll` của policy demo | Không |

**Bảng này mô tả chính sách cụ thể của ví dụ**, không phải quy luật mà mọi Gateway phải trả đúng mã đó trong mọi trường hợp. Đặc biệt, CSRF, CORS, custom exception handlers, route fallback và error handler có thể thay đổi tình huống thực tế.

Khi một token sai, Spring Security có thể thêm `WWW-Authenticate` theo Bearer token error handling. Không xóa header này một cách máy móc bằng `RemoveResponseHeader`, vì nó có thể giúp HTTP client hiểu yêu cầu xác thực.

### Vì sao không đổi mọi lỗi thành 200?

Một Gateway filter thay status thành `200` để tránh CORS/error handling thường khiến frontend tưởng thao tác thành công, làm hỏng tracing và che lỗi bảo mật. Giữ mã HTTP có ý nghĩa, có payload lỗi nhất quán và kiểm soát header CORS trên cả response lỗi.

## 8. CORS preflight trong Gateway có Spring Security

Browser từ `https://app.example.test` gửi POST với `Authorization` có thể bắt đầu bằng:

~~~http
OPTIONS /api/orders/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

**Preflight thường không mang Bearer token như request thật.** Nếu Spring Security yêu cầu token cho OPTIONS trước khi CORS processing giải quyết preflight, frontend có thể nhận `401/403` và báo lỗi CORS.

Trong ví dụ Java, rule:

~~~java
.pathMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()
~~~

giúp OPTIONS ở vùng API đi qua bước **authorization**, nhưng **không tự tạo `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` hoặc `Access-Control-Allow-Headers`**. Bạn vẫn phải cấu hình CORS ở WebFlux/Gateway và phối hợp cách Spring Security xử lý preflight.

Ví dụ global CORS của Gateway Server WebFlux (namespace tương ứng bản đang dùng):

~~~yaml
spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - https://app.example.test
            allowedMethods:
              - GET
              - POST
              - OPTIONS
            allowedHeaders:
              - Authorization
              - Content-Type
            exposedHeaders:
              - X-Request-Id
~~~

`add-to-simple-url-handler-mapping` có ích nếu preflight OPTIONS không match `Method=POST` của một route. Tuy nhiên, nếu Security `WebFilter` chặn request trước khi CORS handler giải quyết, bạn vẫn cần phối hợp Spring Security CORS integration đúng phiên bản (có thể bằng `CorsWebFilter`/reactive CORS configuration phù hợp). **Không tạo hai bộ CORS policy xung đột** rồi chỉ dựa vào một filter dedupe để che header lặp.

CORS chỉ là cơ chế bảo vệ tương tác giữa **browser origin** và response. Nó **không xác thực JWT** và không chống việc HTTP client ngoài trình duyệt gọi API. Với ứng dụng sử dụng cookie, phải giải quyết `allowCredentials`, `SameSite`, `Secure` và CSRF theo threat model.

## 9. Token propagation: kiểm tra JWT tại Gateway chưa kết thúc bài toán bảo mật

Có hai mô hình thường gặp khi Gateway chuyển request tới downstream.

### Mô hình A: Gateway xác thực, downstream vẫn tự xác minh

Gateway dùng Spring Security JWT Resource Server. Downstream cũng là resource server hoặc có cơ chế xác thực đáng tin cậy và kiểm tra token/claims theo chính sách của mình.

Ưu điểm:
- Downstream không phải tin mù quáng vào một header do client có thể giả mạo.
- Nếu request đi qua đường mạng khác Gateway, backend vẫn có lớp bảo vệ.
- Backend kiểm soát quyền nghiệp vụ như `order.ownerId == authenticatedUser`.

Lưu ý: phải hiểu **Authorization header có được chuyển tiếp hay bị filter/proxy loại bỏ**. Một số cấu hình Gateway có thể forward header còn lại, nhưng điều đó không thay thế thiết kế token propagation và security downstream.

### Mô hình B: Gateway xác thực, downstream nhận danh tính nội bộ

Trong một số kiến trúc, Gateway/edge chịu trách nhiệm xác thực và chuyển tiếp một đại diện danh tính đã được xác minh tới dịch vụ tin cậy. Khi đó phải có **ranh giới tin cậy mạnh**:

- Không cho client bên ngoài gọi trực tiếp backend.
- Loại bỏ các header định danh do client tự cung cấp, ví dụ `X-Authenticated-User` và `X-User-Role`, **trước khi** gắn thông tin từ security context đã xác thực.
- Bảo vệ chặng Gateway → backend bằng mạng riêng và TLS/mTLS hoặc cơ chế xác thực giữa services theo yêu cầu.
- Xác định chính xác downstream tin trường nào và quyền nào vẫn phải tự kiểm tra.

**Đừng làm thế này:**

~~~yaml
filters:
  - SetRequestHeader=X-Authenticated-User,admin
~~~

Header tĩnh `admin` không xuất phát từ kết quả xác thực; nó có thể khiến downstream hiểu nhầm mọi người gọi đều là quản trị viên.

### TokenRelay không đồng nghĩa JWT Resource Server

Trong Spring Cloud Gateway, **TokenRelay GatewayFilter Factory** liên quan đến việc chuyển tiếp access token trong những luồng OAuth2 client/authorized client phù hợp; nó đòi tích hợp và cấu hình tương ứng. Chỉ bật JWT resource server **không có nghĩa** TokenRelay tự được thêm vào mọi route, cũng không có nghĩa token từ incoming request luôn phải chuyển nguyên bản tới tất cả downstream.

Quyết định truyền token cần tính đến audience, scope tối thiểu, token exchange/on-behalf-of khi phù hợp, confidentiality, TTL và mục đích của backend. Không chuyển JWT của một API sang dịch vụ có audience khác mà chưa kiểm chứng hợp đồng xác thực.

## 10. Reactive Security Context và filter tùy biến

Khi viết code WebFlux, thông tin xác thực đi cùng **reactive subscriber context**, không nên phụ thuộc vào việc cùng một Java thread xử lý request từ đầu đến cuối.

Trong một filter/hàm xử lý phù hợp, có thể truy cập principal thông qua `ServerWebExchange`:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

Mono<String> authenticatedName(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .cast(Authentication.class)
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
}
~~~

**Đây là ví dụ đọc danh tính trong ứng dụng reactive**, không phải đoạn policy hoàn chỉnh. `Mono` có thể rỗng nếu request không có principal; `isAuthenticated` không tự biểu diễn mức quyền cần thiết cho API. Với custom filter thật, phải xử lý rõ các trường hợp thiếu principal, anonymous authentication, và principal có kiểu khác nếu môi trường dùng nhiều cơ chế đăng nhập.

Nếu cần thông tin JWT cụ thể, dùng kiểu Authentication phù hợp như `JwtAuthenticationToken` sau khi đã xác thực; không tự parse chuỗi `Authorization` bằng cách tách dấu chấm rồi tin các claims.

Tránh:
- Dùng `SecurityContextHolder.getContext()` ở một callback reactive rồi mặc định context luôn gắn với thread hiện tại.
- Gọi dịch vụ từ xa bằng API blocking trong Netty event loop.
- Gắn role/tenant do client truyền vào một header rồi bỏ qua xác minh.
- Log toàn bộ access token, refresh token, session cookie hoặc secret.

**Ưu tiên chính sách khai báo trong `authorizeExchange`** cho những rule rõ ràng. Chỉ dùng custom `ReactiveAuthorizationManager` khi cần kiểm tra phức tạp có nguồn dữ liệu đáng tin cậy, có timeout, cancellation/error handling phù hợp.

## 11. Nhiều SecurityWebFilterChain và thứ tự matcher

Một Gateway có thể cần chính sách khác nhau cho API public, management endpoints và OAuth2 login. Spring Security reactive hỗ trợ **nhiều `SecurityWebFilterChain`**, lựa chọn một chain dựa trên `securityMatcher` và thứ tự `@Order`.

Ví dụ **minh họa nguyên tắc**:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Bean
@Order(1)
SecurityWebFilterChain managementChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(new PathPatternParserServerWebExchangeMatcher("/actuator/**"))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/actuator/health").permitAll()
            .anyExchange().hasAuthority("SCOPE_ops")
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .csrf(ServerHttpSecurity.CsrfSpec::disable)
        .build();
}
~~~

Một chain khác ở `@Order(2)` có thể bao phủ `/api/**` với rule riêng. **Đừng đăng ký đồng thời ví dụ chain ở phần 4 và một chain bổ sung không được thiết kế đúng thứ tự**: phải xác định các `securityMatcher` có chồng lấn hay không, chain nào được chọn và các request còn lại đi đâu.

Lưu ý thực tế:

- `@Order` ở đây là thứ tự **chọn SecurityWebFilterChain**, không phải `Route.order` của Gateway.
- `securityMatcher` giới hạn phạm vi chain. `pathMatchers` trong `authorizeExchange` là **rule bên trong chain đã chọn**; chúng không thay thế phạm vi chain.
- Chain `@Order(1)` match trước có thể khiến chain `@Order(2)` không bao giờ nhận một số URL.
- Nếu management server chạy **cổng hoặc application context riêng**, bảo mật Actuator còn phải xét phạm vi port/context, không mặc định chain của Gateway bao phủ tất cả.

Trong nhiều dự án, **một chain với rule rõ ràng** dễ đọc hơn. Chỉ tách nhiều chain khi có khác biệt thật về cơ chế xác thực, chính sách session hoặc phạm vi quản trị.

## 12. Lỗi phổ biến khi kết hợp Spring Security với Gateway

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Mọi request đều nhận 401 | Thiếu/không hợp lệ JWT, sai issuer, chưa có decoder phù hợp | Kiểm tra `issuer-uri`, JWKS, clock, token signature/claims |
| Có token hợp lệ nhưng 403 | Thiếu authority hoặc mapping scope/roles sai | Kiểm tra `scope`/`scp`, converter và `hasAuthority` |
| GET hợp lệ nhưng POST 403 | Rule theo method tách quyền read/write | Cấp scope đúng; không dùng GET quyền thay POST |
| Token hợp lệ nhưng nhận 404 | Security qua, route không match hoặc backend 404 | Kiểm tra Route Predicate/StripPrefix và downstream |
| Route mới được tạo nhưng mọi request 403 | `anyExchange().denyAll()` fail closed | Cập nhật security policy được duyệt, không mở tất cả routes |
| Preflight OPTIONS bị 401/403 | Security chặn trước khi CORS được xử lý | Kiểm tra reactive CORS integration và rule OPTIONS |
| Browser báo lỗi CORS còn cURL thấy 401 | Error response thiếu CORS headers, không chỉ là vấn đề JWT | Kiểm tra browser Network và response 401 thực tế |
| Security class compile không được | Nhầm `HttpSecurity`/Servlet với `ServerHttpSecurity`/WebFlux | Chọn đúng dependency và API |
| Backend nhận path khác security matcher | Gateway filter đã rewrite public path | Viết security matcher theo request đến Gateway |
| Backend không nhận token | Header bị bỏ hoặc thiết kế token propagation chưa rõ | Kiểm tra Authorization/header filters, backend trust model |
| Backend tin sai role | Dùng header client/tĩnh thay kết quả xác thực | Gỡ header không đáng tin; bảo vệ danh tính ở security context |
| JWT ký đúng nhưng không dành cho API này | Audience không được kiểm tra theo yêu cầu | Thêm audience validation, kiểm thử token khác audience |
| Actuator bị mở ra Internet | Security rule hoặc ingress/proxy cho phép quá rộng | Giới hạn endpoint exposure và quản trị ở lớp mạng/security |
| Đăng nhập qua cookie thất bại hoặc có nguy cơ CSRF | Sao chép disable CSRF từ ví dụ stateless | Thiết kế riêng session, CSRF, SameSite và CORS |
| Một số Gateway nodes chấp nhận, node khác từ chối | Khác version, issuer config, keys/cache, clock hoặc policy | Kiểm tra rollout, clocks, cấu hình và logs từng node |

### 401/403 do Gateway hay downstream?

Phân biệt bằng dấu hiệu quan sát:

- Nếu Spring Security chặn sớm, thường **không có route ID/downstream call**.
- Nếu Gateway đã forward request và backend trả 401/403, đó có thể là **security policy của backend**.
- Nếu rate limiter trả 429 hoặc circuit breaker trả 503, không kết luận ngay là JWT sai.
- Nếu request không match route, error handler có thể tạo response khác security policy đã dự đoán, tùy rule `anyExchange`.

Dùng structured logs/metrics để liên kết route ID, status, event security, backend target và correlation ID. **Không log nguyên văn Bearer token**.

## 13. Bài thực hành end-to-end với JWT và route

### Điều kiện chuẩn bị

- Gateway Server WebFlux chạy tại `http://localhost:8080`.
- Có Identity Provider thật tại issuer đã cấu hình, cấp **JWT access token** có chữ ký được Gateway tin cậy.
- Có backend echo/order ở `http://localhost:9090` nhận `GET /orders/42`; endpoint chỉ là giả định phục vụ lab.
- Có class `GatewaySecurityConfiguration` của phần 4 và route của phần 6.
- Sử dụng một token có scope `orders.read` và một token đã xác thực nhưng không có scope đó; giá trị phải được lấy từ môi trường thử nghiệm có quyền cấp token, **không đưa token thật vào source code**.

### Bước 1 — Không có JWT

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

Kỳ vọng security yêu cầu xác thực và trả **401** theo policy demo, không forward tới backend. Nếu nhận 404, cần kiểm tra security chain có thực sự bảo vệ URL hay không và thứ tự handler.

### Bước 2 — JWT không hợp lệ

~~~bash
curl -i -H "Authorization: Bearer invalid-token" \
  http://localhost:8080/api/orders/42
~~~

Kỳ vọng **401** vì Bearer token không hợp lệ; kiểm tra status và `WWW-Authenticate` nếu được trả về. Không dùng token production vào lab.

### Bước 3 — JWT hợp lệ nhưng thiếu quyền

Sử dụng biến môi trường chứa token được cấp riêng cho thử nghiệm:

~~~bash
curl -i -H "Authorization: Bearer <VALID_JWT_WITHOUT_orders.read>" \
  http://localhost:8080/api/orders/42
~~~

Chuỗi trong dấu ngoặc nhọn chỉ là **placeholder minh họa**, cần thay bằng token test thật được cấp từ Identity Provider. Kỳ vọng **403** theo ví dụ khi token có thể xác thực nhưng thiếu authority `SCOPE_orders.read`.

### Bước 4 — JWT hợp lệ và đủ quyền

~~~bash
curl -i -H "Authorization: Bearer <VALID_JWT_WITH_orders.read>" \
  http://localhost:8080/api/orders/42
~~~

Security có thể cho qua; route `orders-api` match GET/path, filter bỏ `/api`, backend nhận `GET /orders/42`. Kết quả client có thể là 2xx hoặc status do backend quyết định. **Một response 5xx không tự chứng minh JWT thiếu quyền.**

### Bước 5 — Method khác

Dùng token chỉ có `orders.read` để gửi POST:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer <VALID_JWT_WITH_orders.read>" \
  http://localhost:8080/api/orders/42
~~~

Kỳ vọng **403** do thiếu `SCOPE_orders.write`, ngay cả trước bước Gateway route matching. Sau đó thử token có `orders.write`: nó qua security nhưng route demo chỉ có `Method=GET`, nên **không forward theo route đó**. Có thể thấy 404 nếu không có route/handler khác, minh họa phân biệt security và routing.

### Bước 6 — Preflight từ browser

~~~bash
curl -i -X OPTIONS \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" \
  http://localhost:8080/api/orders/42
~~~

Kiểm tra Gateway trả response preflight phù hợp khi cấu hình CORS chính xác, dù OPTIONS không có Bearer token. **CORS không được xác minh chỉ bằng `200`**: còn phải xem `Access-Control-Allow-Origin`, Allow-Methods và Allow-Headers.

### Ma trận kiểm thử tổng hợp

| Trường hợp | Kết quả security | Kết quả routing | Cần xác nhận |
|---|---|---|---|
| Thiếu JWT | 401 | Không routing | Backend không nhận request |
| JWT sai | 401 | Không routing | Token không được chấp nhận |
| JWT hợp lệ thiếu read | 403 | Không routing | Authority mapping đúng |
| JWT hợp lệ có read + GET | Cho phép | Match `orders-api` | Path backend sau StripPrefix |
| JWT hợp lệ có read + POST | 403 | Không routing | Rule theo HTTP method |
| JWT hợp lệ có write + POST | Cho phép | Route demo GET-only không match | Tách routing và security |
| OPTIONS preflight hợp lệ | Không đòi Bearer token ở nhánh phù hợp | Có thể không match route | CORS response đúng |
| Backend không khả dụng | Cho phép nếu JWT đúng | Routing lỗi | Không nhầm với lỗi xác thực |

### Kiểm thử tự động nên có

Trong dự án dùng Spring WebFlux, có thể viết integration tests với **`WebTestClient`** và các hỗ trợ **`spring-security-test`** phù hợp reactive. Khi test security riêng, mock JWT có authority mong muốn để xác nhận `401`/`403` và path/method authorization; khi test end-to-end, dùng Identity Provider test hoặc các JWT được phát hành bằng key test, xác minh decoder và đường forward thực tế.

Không chỉ unit test rule `hasAuthority` mà bỏ qua trường hợp route có `StripPrefix`, header auth bị xóa, CORS preflight hoặc backend từ chối truy cập object-level.

## 14. Vận hành Gateway bảo mật trong production

| Nhóm | Việc phải thiết kế ngoài SecurityWebFilterChain |
|---|---|
| **Xác thực** | Issuer/JWKS tin cậy, signature, `exp`/`nbf`/`iss`, audience validation khi cần, clock sync và key rotation |
| **Phân quyền** | Scope/roles đúng nguồn, least privilege, quyền đối tượng/tenant ở backend, policy khi route mới xuất hiện |
| **Rate limiting** | Key resolver không tin header do client tự đặt, hạn mức theo user/client/route, xử lý HTTP 429 rõ |
| **Circuit breaker và retry** | Không retry không kiểm soát, giới hạn số lần, timeout, idempotency cho thao tác ghi |
| **Service discovery** | Kiểm soát routes được sinh từ registry; không tự mở API nội bộ; URI `lb://` có instance hợp lệ |
| **TLS** | HTTPS client → Gateway, Gateway → backend theo threat model, certificate trust, mTLS nếu cần |
| **Request/response headers** | Không forward credentials không cần thiết; quản lý `Authorization`/`Forwarded`/`X-User-*` theo trust boundary |
| **CORS và CSRF** | Chính sách origin rõ ràng; preflight trước auth khi phù hợp; không disable CSRF cho cookie app tùy tiện |
| **Observability** | Metrics theo 401/403/429/5xx, trace và audit không lộ token/PII; phân biệt lỗi edge/backend |
| **Quản trị** | Actuator/gateway management endpoints được giới hạn mạng và authentication/authorization |
| **Nhiều Gateway instances** | Đồng nhất cấu hình, keys, clocks, security rules và cache; rollout/rollback có kiểm chứng |

**Defense in depth:** Gateway là chốt kiểm tra đầu tiên, nhưng không nên là nơi **duy nhất** quyết định quyền truy cập dữ liệu nhạy cảm. Backend phải kiểm tra quyền sở hữu resource, tenant isolation và các ràng buộc nghiệp vụ mà Gateway không đủ ngữ cảnh để biết.

## 15. Checklist hoàn thành

- [ ] Tôi đã chọn đúng Gateway **Server WebFlux** và dùng `SecurityWebFilterChain` với `ServerHttpSecurity`.
- [ ] Các dependencies Gateway/Spring Security/OAuth2 Resource Server cùng release train tương thích.
- [ ] Tôi phân biệt định tuyến (`RoutePredicate`) với xác thực (`Authentication`) và phân quyền (`Authorization`).
- [ ] Spring Security bảo vệ public URL **trước** các filter rewrite path/header của Gateway.
- [ ] Tôi dùng `authorizeExchange` theo path/method và quy tắc `anyExchange` có chủ đích.
- [ ] Tôi xác minh issuer/JWKS, thời hạn JWT và **audience nếu hợp đồng API cần**.
- [ ] Scope/role converter khớp với authority như `SCOPE_orders.read`; không nhầm `hasRole` và `hasAuthority`.
- [ ] Tôi kiểm thử thiếu token → 401, token hợp lệ thiếu quyền → 403, đủ quyền → tiếp tục routing.
- [ ] Tôi biết route không match và backend lỗi có thể cho status khác 401/403.
- [ ] Tôi đã tích hợp CORS/preflight với Spring Security mà không mở quyền API nghiệp vụ.
- [ ] Tôi chỉ disable CSRF với mô hình stateless thực sự phù hợp; cookie/session có chính sách riêng.
- [ ] Tôi phân biệt TokenRelay/OAuth2 client với Resource Server JWT validation.
- [ ] Tôi không tin header định danh do client tự khai, không hardcode user/role trong GatewayFilter.
- [ ] Backend vẫn xác minh quyền nghiệp vụ và không dễ bị truy cập bypass Gateway.
- [ ] Tôi kiểm soát TLS, rate limiting, retry/circuit breaker, discovery và Actuator như những cấu phần riêng.
- [ ] Tôi kiểm tra log/metrics/tracing mà không để lộ access token và dữ liệu người dùng.
- [ ] Tôi đã kiểm thử trên nhiều Gateway instances và cả các nhánh lỗi thật.

## Tài liệu tham khảo chính thức

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, `ServerHttpSecurity` và thiết lập security reactive.
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html) — xác minh Bearer JWT, issuer, JWKs và authority mapping.
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) — `authorizeExchange` và bảo vệ endpoint.
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — cách phối hợp CORS với Spring Security trên WebFlux.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — kiến trúc route predicate, GatewayFilter chain, TokenRelay và WebFlux/MVC theo phiên bản.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — WebFilter, ServerWebExchange và Reactive Streams.

**Ghi nhớ:** `SecurityWebFilterChain` là **lớp bảo vệ HTTP reactive** ở phía trước Gateway routing: JWT Resource Server xác thực người gọi, `authorizeExchange` kiểm tra quyền trên **public path/method**, rồi Gateway mới chọn route và thực thi filter chain. Hãy duy trì kiểm tra object-level ở downstream, cấu hình CORS/CSRF đúng mô hình và không dùng header tự khai hoặc route predicate thay cho phân quyền.
