# Bật Gateway Actuator với quyền truy cập phù hợp phiên bản

## 1. Gateway Actuator giải quyết vấn đề gì?

Trong một hệ thống microservices, **Spring Cloud Gateway** xử lý lưu lượng ở điểm vào: chọn route bằng `Path`, `Method` và những predicate khác; chạy filter chain; biến đổi đường dẫn/header; phân giải `lb://service-id` qua service discovery; xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và ghi nhận request. Khi hệ thống đang chạy, đội vận hành cần trả lời những câu hỏi như:

- Gateway hiện có **những route nào**, cùng điều kiện predicate và URI đích?
- Route vừa được thêm hoặc cập nhật có thực sự **được nạp** vào Gateway chưa?
- Route đang có **GlobalFilter** và **GatewayFilter** nào?
- Tại sao `GET /api/orders/42` không đi tới Orders service như mong đợi?
- Sau thay đổi cấu hình hoặc service discovery, Gateway đã **refresh định nghĩa route** hay chưa?

**Gateway Actuator endpoint** là tập endpoint quản trị do Spring Cloud Gateway tích hợp với **Spring Boot Actuator** nhằm quan sát và, khi được cho phép, thao tác với các route của Gateway. Nó khác với API nghiệp vụ mà client thường gọi. Thông tin route có thể giúp xử lý sự cố nhanh, nhưng cũng tiết lộ cấu trúc hệ thống, địa chỉ service nội bộ và cách filter bảo vệ request. Một số phiên bản/chế độ còn cung cấp thao tác **thêm, xóa hoặc refresh route** — đây là quyền thay đổi luồng lưu lượng thật.

Bài **“Bật Gateway Actuator với quyền truy cập phù hợp phiên bản”**, thuộc chương **Quản trị Actuator** của module **SPRING_CLOUD_GATEWAY**, tập trung vào cách mở Gateway Actuator **đủ để giám sát nhưng không vô tình tạo cửa hậu quản trị**.

Sau bài học, bạn có thể:

1. Phân biệt **Spring Boot Actuator** với **Gateway-specific actuator endpoint**.
2. Phân biệt ba việc độc lập: **cấp quyền truy cập cho endpoint**, **expose endpoint** và **xác thực/phân quyền HTTP**.
3. Chọn cấu hình `management.endpoint.gateway.access: read-only` trong những phiên bản hỗ trợ, hoặc cấu hình `enabled` theo cách tương thích với dòng cũ.
4. Bảo vệ `/actuator/gateway/**` bằng Spring Security WebFlux, mạng nội bộ và TLS/mTLS khi phù hợp.
5. Biết các thao tác đọc route/filter và vì sao thao tác refresh/thêm/xóa route thuộc **management plane** có rủi ro cao hơn.
6. Chẩn đoán chính xác 401, 403, 404/405 khi endpoint không truy cập được.
7. Kiểm tra bằng curl, WebTestClient và ma trận quyền để chứng minh người dùng Internet không thể đọc hoặc sửa route.
8. Vận hành Gateway nhiều replica mà không nhầm kết quả trên **một instance** với trạng thái đã đồng bộ toàn cụm.

> **Phạm vi:** Ví dụ chính dùng **Spring Cloud Gateway Server WebFlux** và Spring Boot Actuator/Spring Security reactive. Spring Cloud Gateway Server Web MVC, Spring Boot 3.3, 3.4+, 4.x và các release tương ứng có thể khác về starter, cấu hình endpoint và endpoint operations. **Không chọn property bằng cách chỉ nhìn tên phiên bản Gateway**: phải đối chiếu cả **Spring Boot**, **Spring Cloud BOM** và API Actuator đang có.

## 2. Hai loại API trên cùng một ứng dụng nhưng khác ranh giới tin cậy

Gateway nhận lưu lượng từ client, nhưng Actuator là **kênh quản trị**.

~~~mermaid
flowchart TD
    Public["Client / Internet"] --> API["Public API ingress"]
    API --> G["Spring Cloud Gateway"]
    G --> O["Orders service"]
    G --> C["Catalog service"]
    Ops["SRE / trusted operator"] --> M["Private management access"]
    M --> A["Spring Boot Actuator"]
    A --> GA["Gateway endpoint: inspect routes / filters"]
    GA --> G
    A --> H["Health / readiness"]
    A --> MT["Metrics"]
~~~

**Data plane** là nơi request nghiệp vụ được định tuyến. Ví dụ `GET /api/orders/42` qua route `lb://orders-service`. **Management plane** là nơi quan sát/điều khiển runtime của Gateway. Ví dụ `GET /actuator/gateway/routes` liệt kê route definitions ở mức mà endpoint hỗ trợ.

Một người dùng được phép gọi `/api/orders/42` **không tự được phép** truy cập `/actuator/gateway/routes`. Một tài khoản admin **nghiệp vụ** quản lý sản phẩm cũng không mặc nhiên được quyền thay đổi route Gateway. Đây phải là các quyền tách biệt.

### Spring Boot Actuator và Gateway Actuator khác nhau thế nào?

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Spring Boot Actuator** | Cơ chế quản trị, health, metrics và nhiều endpoint của ứng dụng | `/actuator/health`, `/actuator/info`, `/actuator/metrics` |
| **Gateway Actuator** | Endpoint chuyên cho định nghĩa route, filter, refresh và thao tác quản trị route khi được phép | `/actuator/gateway`, `/actuator/gateway/routes` |
| **Spring Security WebFlux** | Quyết định ai được gọi những URL quản trị khi chúng được đưa ra qua HTTP | `SecurityWebFilterChain`, authority/role/scope |
| **Network/TLS boundary** | Chỉ cho nguồn truy cập tin cậy kết nối tới management port | Private interface, firewall, mTLS/VPN |

Actuator không tự là một dashboard có giao diện đồ họa. Nó thường cung cấp các **HTTP management operations**; client như curl, hệ thống vận hành hoặc công cụ quan sát có thể gọi chúng theo chính sách.

### Không phải mọi Actuator endpoint đều nên public

Một số endpoint như `health` có thể cung cấp trạng thái tối thiểu cho probe nếu được thiết kế phù hợp. Các endpoint như `env`, `configprops`, `beans`, `heapdump`, `threaddump`, `loggers` và **gateway route-management** có độ nhạy cảm khác hẳn. Không dùng `management.endpoints.web.exposure.include: "*"` để “cho tiện debug” trên một Gateway truy cập từ Internet.

## 3. Ba cửa phải đi qua trước khi gọi được Gateway Actuator

Một HTTP request đến `/actuator/gateway/routes` cần phân biệt **ba lớp quyết định**.

~~~mermaid
flowchart TD
    R["GET /actuator/gateway/routes"] --> E{"Endpoint có khả dụng / được cấp access?"}
    E -->|Không| N["Operation không được đăng ký"]
    E -->|Có| X{"Gateway Actuator được expose qua HTTP?"}
    X -->|Không| H["Không có HTTP mapping công khai cho endpoint"]
    X -->|Có| S{"Network + HTTP security cho phép?"}
    S -->|Không| D["Blocked / 401 / 403"]
    S -->|Có| OK["Đọc thông tin route trong mức quyền endpoint"]
~~~

**Cửa 1 — Endpoint availability và access.** Một endpoint có thể bị tắt hoàn toàn; ở các dòng Spring Boot mới, property `management.endpoint.gateway.access` cho phép chọn `none`, `read-only` hoặc `unrestricted` khi Gateway Actuator hỗ trợ chính sách này. `read-only` có mục đích loại bỏ các thao tác ghi do Actuator định nghĩa.

**Cửa 2 — Exposure qua transport.** `management.endpoints.web.exposure.include` quyết định endpoint nào được expose qua HTTP. Một endpoint có thể khả dụng trong ứng dụng nhưng **không có mapping HTTP** vì không được include. Exposure **không phải** authentication; nó chỉ quyết định surface có thể gọi.

**Cửa 3 — HTTP security và mạng.** Endpoint được expose vẫn phải được bảo vệ bằng **Spring Security**, network policy, TLS và/hoặc mTLS theo kiến trúc. `read-only` **không ngăn người không có quyền đọc cấu hình nội bộ** nếu bạn expose endpoint công khai. Ngược lại, một SecurityWebFilterChain chỉ chặn HTTP requests **không thay đổi việc một Actuator write operation có được định nghĩa hay không**; nên giảm quyền ở cả cấp endpoint lẫn HTTP.

### Không được nhầm “read-only” với quyền role

| Thuộc tính | Nó kiểm soát | Nó **không** kiểm soát |
| --- | --- | --- |
| `management.endpoint.gateway.access=read-only` | Loại thao tác của Actuator Gateway được cho phép theo mô hình access | Ai có quyền gọi GET endpoint đó |
| `management.endpoints.web.exposure.include=gateway` | Đưa endpoint lên HTTP management surface | Người nào được phép truy cập |
| `.hasAuthority("SCOPE_ops.gateway.read")` | Authorization của request trong Spring Security | Actuator write operation có tồn tại hay không |
| Private management port/firewall | Ai có thể kết nối qua mạng | Quyền theo danh tính của từng operator |

**Defense in depth:** Với nhu cầu **chỉ xem route/filter**, cấu hình endpoint ở **read-only**, expose chọn lọc, bảo vệ HTTP bằng quyền riêng và không đưa management port lên Internet. Nếu endpoint không hỗ trợ read-only ở phiên bản đang chạy, ưu tiên bảo vệ chặt bằng security/network và cân nhắc nâng cấp theo kế hoạch.

## 4. Chọn property theo phiên bản: access hay enabled?

Spring Boot Actuator đã phát triển cơ chế **endpoint access** theo thời gian. Vì Gateway Actuator tích hợp vào Actuator, cú pháp bật và giới hạn thao tác cần khớp với **phiên bản Spring Boot và Spring Cloud Gateway** thực tế.

| Nhóm phiên bản/khả năng | Cấu hình nên kiểm tra | Ý nghĩa |
| --- | --- | --- |
| **Spring Boot hiện đại có hỗ trợ endpoint access**, thường từ dòng Boot 3.4 trở đi với Gateway tương thích | `management.endpoint.gateway.access=read-only` | Cho phép các Gateway Actuator read operations trong phạm vi được hỗ trợ |
| Cùng nhóm trên, **có yêu cầu thay đổi route** và đã kiểm soát management plane | `management.endpoint.gateway.access=unrestricted` | Cho phép cả write operations nếu endpoint cung cấp, **rủi ro cao** |
| Cùng nhóm trên, **muốn tắt Gateway endpoint** | `management.endpoint.gateway.access=none` | Không cấp quyền truy cập Gateway endpoint ở cấp Actuator |
| **Spring Boot/Gateway đời trước** hoặc dòng còn dùng cờ enable/disable | `management.endpoint.gateway.enabled=true` | Bật endpoint theo cơ chế cũ; không cung cấp read-only protection kiểu access mới |
| **Mọi nhóm có Actuator web exposure** | `management.endpoints.web.exposure.include=gateway` | Chỉ expose gateway nếu endpoint khả dụng; vẫn cần security |

**Đây là ma trận chọn hướng, không phải bảng hỗ trợ chính xác cho mọi patch release.** Một số phiên bản có thể đọc thuộc tính `enabled` để tương thích; một số hỗ trợ property `access` nhưng còn chịu giới hạn tổng thể của Actuator. Kiểm tra tài liệu **đúng phiên bản đang chạy**, metadata/config binding và HTTP operations thực tế, thay vì chép cả `enabled` và `access` với ý định “phòng hờ”.

### Tại sao không suy ra tính năng từ namespace của Gateway routes?

Ở một số dòng Spring Cloud Gateway, route definitions dùng:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog
          uri: lb://catalog-service
          predicates:
            - Path=/api/catalog/**
~~~

Ở các dòng mới của **Gateway Server WebFlux**, chúng có thể nằm dưới `spring.cloud.gateway.server.webflux.routes`. **Đó là namespace route**, không phải property điều khiển Gateway Actuator. Config bật Actuator nằm dưới **`management.*`**. Không tự kết luận phải viết `spring.cloud.gateway.server.webflux.actuator...` chỉ vì các route đã chuyển namespace.

### Cách xác định môi trường của bạn

1. Xác định **Spring Boot version** và **Spring Cloud release train/BOM** từ cấu hình dependency dự án mà nhóm phụ trách đã phê duyệt.
2. Xác định ứng dụng chạy **Gateway Server WebFlux** hay **Gateway Server Web MVC**; không trộn starter servlet/reactive khi viết security config.
3. Xác minh **Actuator starter** đã có, endpoint Gateway được cung cấp bởi dependency Gateway đang dùng.
4. Chọn một phương thức cấu hình `access` hoặc `enabled` thực sự được phiên bản hỗ trợ.
5. Bật `web.exposure` có chọn lọc và cấu hình Spring Security.
6. Dùng test HTTP để xác nhận GET route được phép, write request bị chặn hoặc không tồn tại đúng như chính sách.

Không dựa vào việc IDE nhận ra một property để khẳng định endpoint đã chạy. Một property không được bind có thể bị bỏ qua hoặc cảnh báo tùy cấu hình; **HTTP behavior và tests** mới là bằng chứng.

## 5. Cấu hình khuyến nghị: Gateway Actuator chỉ đọc

Trong một ứng dụng **Spring Boot hỗ trợ `management.endpoint.gateway.access`** và Gateway tương thích, thiết lập tối thiểu có chủ đích:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

**Giải thích:**

- `gateway.access: read-only` cho phép các thao tác đọc route/filter theo implementation hỗ trợ; không cấp quyền sửa route.
- `web.exposure.include` đưa **đúng ba endpoint ID** `health`, `info`, `gateway` ra HTTP, thay vì dùng wildcard.
- `health.show-details: never` giữ response health tối giản trong ví dụ. Nếu operator cần details, hãy thiết kế nhóm health và quyền riêng.
- YAML này **chưa định nghĩa authentication/authorization hoặc network isolation**. Nếu deployment expose cổng management ra Internet thì vẫn **chưa an toàn**, ngay cả khi read-only.

Một ví dụ minh họa (đã bảo vệ port và access đúng) là:

~~~bash
curl -i 'http://127.0.0.1:9091/actuator/gateway/routes'
~~~

Nếu cấu hình có management port riêng ở 9091 và operator đang chạy đúng **trên host được phép**, GET có thể trả JSON danh sách route. Nếu chưa có route nào, danh sách có thể rỗng. **Không xem HTTP 200 từ localhost là bằng chứng Internet không thể truy cập endpoint**; cần kiểm thử từ bên ngoài network boundary.

### Có thể áp giới hạn access cho tất cả Actuator endpoints không?

Các dòng Spring Boot hỗ trợ mô hình endpoint access còn có thể cung cấp **giới hạn truy cập chung** như `management.endpoints.access.max-permitted`. Nếu hệ thống chỉ cần đọc management data, một giới hạn chung **read-only** có thể bổ sung defense in depth. Tuy nhiên property đó cũng có thể ảnh hưởng các endpoint quản trị khác; kiểm tra compatibility và không dùng để thay thế HTTP security. Khi chưa chắc về binding/version, ưu tiên cấu hình per-endpoint và kiểm thử chính xác các write operations.

## 6. Cấu hình tương thích cho dòng cũ dùng enabled

Với một dòng Spring Boot/Gateway mà tài liệu của phiên bản đó dùng **`management.endpoint.gateway.enabled`** thay cho access mode:

~~~yaml
management:
  endpoint:
    gateway:
      enabled: true
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

**Cảnh báo an toàn quan trọng:** `enabled: true` không nói rằng chỉ các thao tác GET có thể thực hiện được. Tùy implementation và phiên bản, Gateway Actuator có thể cung cấp **POST refresh**, **POST tạo route** hoặc **DELETE route** nếu chúng được expose. Với cơ chế này:

1. Không expose Gateway endpoint tới Internet hay client nghiệp vụ.
2. Dùng **Spring Security WebFlux** để hạn chế chỉ những method/path được phép và kiểm soát danh tính operator.
3. Cân nhắc management port private, TLS/mTLS, firewall hoặc VPN/zero-trust access.
4. Test cả `POST` và `DELETE`, không chỉ GET.
5. Nếu không thể bảo đảm ranh giới này, **không bật Gateway Actuator** trên production chỉ vì muốn có route listing.

### Nếu cần ghi thao tác quản trị route

Chế độ `access: unrestricted` (ở phiên bản hỗ trợ) chỉ nên dùng khi đội vận hành có **yêu cầu nghiệp vụ cụ thể** để thay đổi route ở runtime, cùng một kênh quản trị độc lập với user-facing API:

~~~yaml
# Chỉ minh họa; KHÔNG khuyến nghị trên cổng public.
management:
  endpoint:
    gateway:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: gateway
~~~

Không copy cấu hình trên vào môi trường công khai. Cần quyền ghi riêng, change approval/audit, kiểm soát route destination, rollback, tránh SSRF/token egress và đồng bộ qua nhiều Gateway instances. Phần sau phân tích thao tác ghi và rủi ro của chúng.

## 7. Bảo vệ Gateway Actuator bằng Spring Security WebFlux

Ở **Spring Cloud Gateway Server WebFlux**, chính sách bảo mật HTTP nên được xây bằng **`SecurityWebFilterChain`** của Spring Security reactive, không phải `SecurityFilterChain` Servlet. Ví dụ dưới đây giả định:

- Actuator và API đang dùng **cùng WebFlux application port** và base path mặc định `/actuator`.
- Endpoint Gateway đã cấu hình **read-only** ở cấp Actuator, theo khả năng của phiên bản.
- Người vận hành có JWT hợp lệ với authority **`SCOPE_gateway.read`**.
- API nghiệp vụ có một security chain riêng, với chính sách mặc định từ chối.
- Ứng dụng dùng **stateless Bearer token**, không dựa vào cookie/session cho thao tác thay đổi trạng thái.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class GatewayHttpSecurityConfig {

    @Bean
    @Order(0)
    SecurityWebFilterChain managementChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers("/actuator/**"))
                .authorizeExchange(auth -> auth
                        .pathMatchers(HttpMethod.GET, "/actuator/health")
                            .permitAll()
                        .pathMatchers(
                                HttpMethod.GET,
                                "/actuator/gateway",
                                "/actuator/gateway/**")
                            .hasAuthority("SCOPE_gateway.read")
                        .anyExchange()
                            .denyAll()
                )
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                // Chỉ cho API thuần Bearer JWT, không dùng cookie auth.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain applicationChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers(HttpMethod.GET, "/api/public/**")
                            .permitAll()
                        .pathMatchers("/api/**")
                            .authenticated()
                        .anyExchange()
                            .denyAll()
                )
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

**Cách hiểu:**

1. `@Order(0)` và `securityMatcher("/actuator/**")` chọn security chain chuyên cho quản trị **trước** chain ứng dụng.
2. Health GET được permit trong ví dụ cho probe; **không đồng nghĩa mọi health details hoặc mọi actuator endpoint đều public**.
3. Gateway GET operations yêu cầu một **authority chuyên cho việc xem quản trị**. Không dùng `authenticated()` cho toàn bộ `/actuator/**`, vì như vậy tài khoản người dùng thông thường có thể được xem thông tin quản trị.
4. `anyExchange().denyAll()` trong management chain chặn các endpoint/method khác, gồm route write operations. Đừng đặt `/actuator/**.permitAll()` lên trước rule quản trị.
5. Chain ứng dụng bảo vệ riêng `/api/**`; không dựa vào Gateway route filters để thay Spring Security ở lớp WebFlux.
6. `oauth2ResourceServer(...jwt(...))` **xác thực JWT được trình bày**; nó không cấp token. Cần issuer/trust và audience validation đúng contract.
7. `csrf(...disable)` là lựa chọn minh họa **chỉ khi xác thực bằng Bearer JWT và không dùng cookie/session**. Với cookie-based admin UI hoặc form login, phải thiết kế CSRF protection thay vì sao chép dòng này.

Trong ví dụ này, `info` nằm trong danh sách HTTP exposure nhưng **không được phép truy cập** bởi management security chain, vì `anyExchange().denyAll()` chặn những path chưa khai báo. Nếu có nhu cầu xem `/actuator/info`, thêm quy tắc GET với quyền phù hợp; nếu không cần, bỏ `info` khỏi danh sách exposure để giảm surface.

### Cấu hình issuer cho ví dụ Bearer JWT

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/operations
~~~

Đây là **địa chỉ giả định cho lab**, không phải Identity Provider thật. Spring Security cần được cấu hình để xác minh chữ ký, issuer, thời hạn và **audience đúng với management API**. Đừng giả định `issuer-uri` tự kiểm tra audience nghiệp vụ của bạn theo đúng cách mong muốn; hãy thêm validator audience tương ứng với phiên bản và IdP.

Authority `SCOPE_gateway.read` trong code chỉ xuất hiện nếu JWT access token được ánh xạ từ scope `gateway.read` (hoặc một converter đáng tin gán authority tương đương). Nếu IdP chỉ cấp claim `roles: ["OPS"]`, cần **mapping role → authority** rõ ràng; không đọc một header `X-Role: ops` do client tự gửi.

### Nhiều SecurityWebFilterChain: chọn chain không phải cộng dồn chain

Spring Security chọn security chain đầu tiên khớp matcher theo order; nó không tự cộng tất cả quy tắc ở mọi chain. Nếu chain dành cho `/**` đứng trước chain `/actuator/**`, rule quản trị có thể không được áp dụng. Vì vậy:

- Đặt chain quản trị có matcher cụ thể và order ưu tiên.
- Dùng default deny cho những path/method chưa được cho phép.
- Kiểm thử chain được chọn với anonymous, user thường, operator và operator không đủ scope.
- Nếu đổi `management.endpoints.web.base-path`, sửa matcher tương ứng.

**Lưu ý management port riêng:** Khi `management.server.port` khác server port, Spring Boot có thể tạo management context/HTTP server riêng. Cách security chain được áp dụng ở management context phụ thuộc cấu hình ứng dụng/phiên bản. **Đừng suy ra** chỉ cần nhìn `GatewayHttpSecurityConfig` ở application port là management port đã được bảo vệ. Phải kiểm thử **đúng port, đúng base path và đúng nguồn truy cập**; bổ sung security configuration dành cho management context nếu kiến trúc yêu cầu.

## 8. Phân tách cổng quản trị với cổng public

Trong production, một cách giảm attack surface là cho API và management interface nghe trên **hai cổng khác nhau**, sau đó dùng network policy chỉ cho nguồn vận hành truy cập cổng quản trị.

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoint:
    gateway:
      access: read-only
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

Ví dụ này chỉ hợp lệ với **phiên bản hỗ trợ `gateway.access`**. Management server nghe loopback `127.0.0.1`, giúp giảm khả năng kết nối từ bên ngoài **trên cùng host/network namespace**. Nó không tự giải quyết TLS, quyền operator hoặc mọi mô hình triển khai.

### Trong container và Kubernetes phải hiểu network namespace

Khi ứng dụng chạy trong container:

- `127.0.0.1` thường là loopback **của container hoặc Pod/network namespace**, không phải loopback của máy vận hành.
- Nếu Prometheus/sidecar chạy ở vị trí khác, việc chỉ nghe loopback có thể làm scrape hoặc health probe thất bại.
- Để có management access từ một monitoring network, có thể cần bind private interface phù hợp và dùng **Kubernetes Service/NetworkPolicy, firewall hoặc service mesh** để hạn chế nguồn truy cập.
- Không cấu hình `0.0.0.0:9091` rồi mở port qua LoadBalancer public mà không có lớp auth và network restriction.
- Nếu ingress đang tự động forward mọi path đến ứng dụng 8080, tách port 9091 có thể giúp ngăn vô tình expose; nhưng vẫn phải kiểm tra mapping và các cổng được publish.

**Phân tách port là lớp bảo vệ**, không thay thế Spring Security. Một kẻ có khả năng kết nối management network không mặc nhiên được quyền đọc route definitions. Dùng TLS/mTLS hoặc cơ chế danh tính phù hợp trong nội bộ.

### Management base path và liveness/readiness probes

Mặc định HTTP path thường là `/actuator`, nhưng có thể thay đổi bằng `management.endpoints.web.base-path` hoặc path mapping:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

Khi đó endpoint có thể xuất hiện dưới `/manage/gateway/routes` thay vì `/actuator/gateway/routes` (trong môi trường HTTP mapping tương ứng). **Security matcher, ingress rules, firewall và monitoring checks phải đổi đồng bộ**. Không coi việc đổi path thành bí mật hoặc cơ chế bảo mật.

Health probes thường cần access khác Gateway route inspection. Hãy thiết kế **`/actuator/health/liveness`**, **`/actuator/health/readiness`** hoặc đường dẫn health riêng theo khả năng Spring Boot đang dùng, không cho mọi endpoint quản trị cùng mức truy cập chỉ vì liveness cần được gọi không xác thực.

## 9. Các Gateway Actuator read operations thường gặp

Khi endpoint được bật, expose và có quyền đọc, các thao tác sau thường hữu ích cho chẩn đoán **Gateway Server WebFlux**. **Danh sách và payload có thể khác phiên bản**:

| HTTP operation | Mục đích | Lưu ý |
| --- | --- | --- |
| `GET /actuator/gateway` | Thông tin/index về các operation Gateway nếu bản đang dùng cung cấp | Không bảo đảm mọi release có output giống nhau |
| `GET /actuator/gateway/routes` | Liệt kê các route đang khả dụng với thông tin predicate/filter/URI | Có thể lộ service IDs, hostnames và cấu hình nội bộ |
| `GET /actuator/gateway/routes/{id}` | Xem chi tiết một route | Route ID và output theo implementation |
| `GET /actuator/gateway/globalfilters` | Danh sách GlobalFilters và order/metadata mà endpoint có thể báo | Không phải bằng chứng mọi request đều đi qua filter |
| `GET /actuator/gateway/routefilters` | Xem các GatewayFilter factories được nhận diện | Không đồng nghĩa filter đã gắn vào mọi route |
| `GET /actuator/gateway/routes/{id}/combinedfilters` | Xem filter chain tổng hợp cho route nếu operation được hỗ trợ | Giúp kiểm tra thứ tự, không thay thế request trace |
| `GET /actuator/gateway/routepredicates` | Xem các route predicate factories nếu release cung cấp | Hữu ích khi xác định factory được đăng ký |

**Không ghi cứng rằng mọi operation trên đều có trên mọi release.** Một số bản chỉ trả tập operation khác, hoặc có thay đổi JSON output/verbose format. Cách tin cậy là đọc tài liệu version đã khóa và thực hiện test với HTTP client trong môi trường được phép.

### Route listing cho bạn biết gì?

Một route có thể được khai báo kiểu:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-read
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway-Source,orders-edge
~~~

Khi route được nạp, read endpoint có thể giúp xác nhận `orders-read` tồn tại, URI là `lb://orders-service` và các predicate/filter dự kiến đã được khai báo. Tuy nhiên, đây là thông tin **định nghĩa route**, không bảo đảm:

- Service discovery đang có instance khỏe.
- JWT của client được chấp nhận hoặc authorization đúng.
- `StripPrefix` tạo đúng path backend trong mọi trường hợp biên.
- TCP connect/TLS handshake tới backend thành công.
- Circuit breaker đang CLOSED hay một request vừa bị retry.
- Mọi Gateway replica đang chạy cùng một route definition.

Để trả lời các câu hỏi đó, phải kết hợp **request trace, Spring Security logs an toàn, Netty/LoadBalancer metrics, backend stub và HTTP test**.

### Vì sao kết quả GET route vẫn nhạy cảm?

Output của Gateway Actuator có thể chứa URI nội bộ, filter arguments, header constants, host matching, route metadata hoặc thông tin vận hành khác. Trong một số ứng dụng, nhà phát triển sai lầm đặt bí mật trực tiếp trong route URI hoặc filter args — ví dụ nhúng API key vào `SetRequestHeader`. Khi ấy, route listing trở thành đường rò rỉ bí mật.

**Không đặt secret trong định nghĩa route được xem như dữ liệu công khai**, và không dựa vào hành vi Actuator che từng giá trị để bảo vệ secrets. Đưa credential vào hệ thống quản lý secrets và thiết kế filter không ghi/hiển thị bí mật không cần thiết; vẫn kiểm tra output Actuator trong môi trường thử nghiệm.

## 10. Read-only là quyền xem, không phải báo cáo sức khỏe toàn diện

Một GET tới `/actuator/gateway/routes` có thể trả HTTP 200 khi Gateway đang chạy và route definitions có thể đọc được. Nhưng backend Orders có thể đang down, registry rỗng hoặc circuit breaker OPEN. Nên tách các tín hiệu:

| Quan sát | Câu hỏi |
| --- | --- |
| Actuator gateway routes | Route đã được nạp vào instance này chưa? |
| Spring Boot health | Ứng dụng/health groups báo trạng thái gì? |
| Readiness | Instance Gateway có nên nhận traffic mới không? |
| Route metrics | Route nào đang nhận request, status, latency ra sao? |
| Reactor Netty metrics | Pool connection/timeout có đang bão hòa không? |
| LoadBalancer/discovery | Có ServiceInstance phù hợp không? |
| Resilience4j/circuit metrics | Breaker có OPEN và chặn calls không? |
| Tracing và backend logs | Một request cụ thể đi qua route/filter nào? |

**Route tồn tại không đồng nghĩa backend sẵn sàng**. Ngược lại, endpoint management bị chặn bởi security không có nghĩa API routing bị lỗi. Việc cô lập management plane chính là để quản trị mà không trộn quyền quan sát với luồng nghiệp vụ.

## 11. Các write operations phải được coi là đặc quyền cao

Ở những phiên bản/chế độ hỗ trợ mutation, Gateway Actuator có thể cung cấp những thao tác như:

| HTTP operation minh họa | Ý nghĩa | Rủi ro |
| --- | --- | --- |
| `POST /actuator/gateway/refresh` | Yêu cầu Gateway làm mới/cập nhật thông tin route theo implementation | Một thay đổi bất ngờ có thể làm request đi route khác hoặc mất route tạm thời |
| `POST /actuator/gateway/routes/{id}` | Tạo/ghi định nghĩa route khi operation và repository hỗ trợ | Có thể thêm route vào internal service hoặc upstream không tin |
| `DELETE /actuator/gateway/routes/{id}` | Xóa route khi operation và repository hỗ trợ | Gián đoạn traffic, làm API quan trọng biến mất |

**Không phải cứ có read endpoint là write operations tồn tại hay khả dụng.** Chế độ `read-only` ở phiên bản hỗ trợ cần ngăn các operation ghi ở cấp Actuator; ở chế độ unrestricted và dòng cũ, phải xác minh bằng test. Nguồn lưu `RouteDefinitionRepository` cũng ảnh hưởng khả năng tạo/xóa và tính bền vững của route.

### Vì sao quyền ghi route đặc biệt nguy hiểm?

Một người có quyền tạo route có thể làm nhiều việc hơn “sửa menu đường dẫn”:

1. Dùng route URI trỏ tới endpoint mạng nội bộ vốn không dành cho client.
2. Đổi đích `lb://orders-service` sang service khác không được phép nhận JWT.
3. Gắn `StripPrefix` hoặc `RewritePath` để đưa request tới path quản trị backend.
4. Xóa/bỏ các filters kiểm tra header hoặc rate limiting trong một route.
5. Tạo route catch-all `Path=/**` làm chồng lấn với route đang hoạt động.
6. Khi kết hợp với config filter không an toàn, chuyển token/API key sang upstream không đáng tin.

Đây là bề mặt **SSRF, credential exfiltration và routing bypass** nếu bị lạm dụng. Vì vậy quyền ghi phải cần **nguồn truy cập riêng**, xác thực mạnh, least privilege, change approval, audit và kiểm tra destination allowlist. Không coi `hasRole("ADMIN")` của quản trị nghiệp vụ là đủ quyền thay đổi hạ tầng.

### Sửa route ở runtime không giống sửa file cấu hình

Một số cách tạo route động chỉ tác động tới **repository/cache ở runtime** của một instance. Không được mặc định rằng:

- Route mới được ghi bền qua restart.
- Mọi Gateway replica khác tự nhận cùng thay đổi.
- Một refresh luôn cập nhật từ cùng nguồn cấu hình mong muốn.
- Thay đổi qua Actuator được version control, có review và rollback.

Quy trình tốt hơn thường là **GitOps/config repository/service registry có quản lý**, deployment đã review và các bước kiểm tra trước/sau thay đổi. Nếu tổ chức buộc phải quản lý route động, cần nêu rõ source of truth, consistency model, propagation và rollback.

## 12. Kiểm thử an toàn bằng HTTP client

Chỉ dùng HTTP requests dưới đây trên môi trường **lab hoặc management network đã được phép**. Địa chỉ `127.0.0.1:9091` là giả định tương ứng với ví dụ management port ở phần 8; thay bằng endpoint được tổ chức phê duyệt khi chạy thật.

### Kiểm tra health tối thiểu

~~~bash
curl -i 'http://127.0.0.1:9091/actuator/health'
~~~

Nếu health được expose và policy cho phép, một response ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

**Đây là response minh họa, không phải kết quả chạy thật.** Nếu ứng dụng không healthy, security khác hoặc Actuator format thay đổi, status/content-type có thể khác. Không ép health trả 200 chỉ để probe xanh.

### Kiểm tra Gateway route listing

~~~bash
# Không có credential: kỳ vọng security từ chối (thường 401).
curl -i 'http://127.0.0.1:9091/actuator/gateway/routes'

# Với credential vận hành được cấp hợp lệ:
curl -i \
  -H "Authorization: Bearer ${OPS_READ_TOKEN}" \
  'http://127.0.0.1:9091/actuator/gateway/routes'
~~~

Trong ví dụ trên, `OPS_READ_TOKEN` chỉ là biến test chứa token cấp cho **operator**, không dùng token user. **Không đưa token production trực tiếp vào command line, screenshots hoặc log chia sẻ**. Thậm chí biến môi trường trong shell có thể bị lộ qua tracing/process inspection theo hệ điều hành; sử dụng cơ chế client/secret injection phù hợp khi vận hành thật.

### Đọc chi tiết một route

~~~bash
curl -i \
  -H "Authorization: Bearer ${OPS_READ_TOKEN}" \
  'http://127.0.0.1:9091/actuator/gateway/routes/orders-read'
~~~

Nếu đã bật `read-only`, các GET phía trên có thể thành công **khi** có quyền, endpoint thực sự được nạp và route tồn tại. Nếu request trả 404, hãy phân biệt **route ID không tồn tại** với **Gateway Actuator chưa được expose/đang disabled**. Phần chẩn đoán phía sau sẽ hệ thống hóa.

### Không dùng thao tác ghi để “thử có quyền không” trên production

**Không chạy `POST /actuator/gateway/refresh` hay `DELETE /actuator/gateway/routes/{id}` trên production chỉ để xem nó bị từ chối hay không.** Một cấu hình security sai có thể làm request được thực hiện và gây outage. Kiểm thử write protection bằng **WebTestClient/môi trường cô lập**, gửi request tới route ID giả và xác nhận không có thay đổi trong repository/backend counter.

## 13. Spring Security mặc định không phải một cam kết bảo mật vĩnh viễn

Spring Boot có cơ chế auto-configuration bảo mật Actuator khi Spring Security hiện diện, nhưng việc tạo một hoặc nhiều **`SecurityWebFilterChain` riêng** có thể làm thay đổi hoặc thay thế cách Boot tự bảo vệ các endpoints. **Không giả định rằng chỉ cần thêm `spring-boot-starter-security` thì mọi Actuator endpoint luôn được khóa đúng theo chính sách tổ chức.**

### Kiểm tra đủ cả ba nguồn bảo vệ

| Nguồn bảo vệ | Mục tiêu | Câu hỏi cần đặt |
| --- | --- | --- |
| Actuator endpoint access | Không đăng ký thao tác không được phép | `read-only` có thực sự ẩn write operations ở bản đang dùng? |
| Spring Security WebFlux | Xác thực/phân quyền theo request | Anonymous, user, ops-read, ops-write nhận status nào? |
| Network/TLS/mTLS | Hạn chế ai có thể kết nối management HTTP server | Có đường từ Internet/tenant khác vào management port không? |

Ví dụ một nhóm đã có Spring Security cho `/api/**` và thêm Actuator:

~~~java
// CHỐNG MẪU: matcher chỉ bảo vệ /api/**.
// Đừng coi đây là security policy đầy đủ cho management endpoint.
.authorizeExchange(auth -> auth
        .pathMatchers("/api/**").authenticated()
        .anyExchange().permitAll())
~~~

Với rule cuối `anyExchange().permitAll()`, nếu chain đó bao phủ `/actuator/gateway/routes`, endpoint có thể được gọi bởi anonymous khi đã expose. Đổi thành một management-specific chain hoặc deny-by-default với matcher rõ ràng, không để cấu hình API mặc định mở Actuator.

### Phân tách quyền read và write

Một mô hình authority tham khảo:

| Vai trò | Quyền phù hợp | Không được |
| --- | --- | --- |
| Public user | Không có quyền Gateway Actuator | Đọc route/filter hoặc sửa route |
| Application user | Gọi API nghiệp vụ theo JWT | Đọc Gateway Actuator chỉ vì có login |
| Operations viewer | `SCOPE_gateway.read` | Mutation/refresh nếu không được phân quyền |
| Operations change manager | Quyền riêng cho thay đổi hạ tầng, qua workflow được phê duyệt | Tự bỏ qua audit, allowlist đích hoặc review |
| Break-glass operator | Quyền tạm thời được cấp theo quy trình khẩn cấp | Duy trì quyền không giới hạn lâu dài |

Nếu phiên bản hỗ trợ `access: read-only`, **ngay cả một user có scope ghi** cũng không thể dùng Actuator write operations mà endpoint không đăng ký. Khi cần tạm mở unrestricted, nên thực hiện thay đổi có phê duyệt và có thời hạn, tách **management change workflow** khỏi data plane và khôi phục read-only sau thao tác.

### CSRF và phương thức ghi

Ở ví dụ Security WebFlux dùng **Bearer JWT không tự động được browser gửi như cookie**, CSRF bị tắt có điều kiện. Nếu management API dùng browser session/cookie hoặc SSO dựa trên cookie, **CSRF protection cần được thiết kế đúng** cho POST/DELETE. Không “fix” lỗi 403 bằng cách vô hiệu hóa CSRF vô điều kiện, hoặc bằng cách mở `permitAll` cho management endpoints.

### Đừng để GatewayFilter tự bảo vệ Actuator

Một `GlobalFilter` hoặc `GatewayFilter` chỉ hoạt động khi request được xử lý qua **Gateway FilteringWebHandler** tương ứng. `/actuator/gateway/**` là endpoint WebFlux/Actuator, không nhất thiết đi qua route Gateway. Vì vậy:

- Không dùng một GlobalFilter kiểm tra `X-Admin: true` rồi kết luận Actuator được bảo vệ.
- Không kỳ vọng `RequestRateLimiter` của route `Path=/**` tự đếm traffic Actuator.
- Không kỳ vọng `StripPrefix` hoặc `RewritePath` của Gateway route áp lên Actuator.
- Bảo vệ tại **Spring Security WebFilter** và **management HTTP/network boundary** thực sự.

Nếu đặt một catch-all Gateway route `Path=/**`, cần test nó không can thiệp hoặc che lấp management mappings theo thứ tự HandlerMapping của ứng dụng. Dù request tới handler nào, security policy không được trở nên lỏng hơn.

## 14. Diễn giải 401, 403, 404 và 405 khi gọi Actuator

Khi một GET vào Gateway Actuator không hoạt động, phải xác định **request bị chặn ở đâu** trước khi đổi cấu hình.

| Quan sát | Một số nguyên nhân hợp lý | Bước kiểm tra |
| --- | --- | --- |
| **Connection refused / timeout** | Sai port, chỉ bind loopback, network policy, server chưa mở | Kiểm tra listener, ingress/Service, đúng IP:port |
| **TLS handshake failure** | Sai scheme, CA, hostname hoặc mTLS identity | Kiểm tra chứng chỉ/trust; không tắt verification |
| **401 Unauthorized** | Không có token hợp lệ hoặc Resource Server từ chối token | Kiểm tra issuer, audience, thời hạn, credentials operator |
| **403 Forbidden** | Token hợp lệ nhưng thiếu authority hoặc security rule deny | Kiểm tra chain order, `SCOPE_gateway.read`, CSRF nếu dùng cookie |
| **404 Not Found** | Endpoint không enabled/access=none, không expose, base path sai, route ID không tồn tại hoặc mapping khác | Kiểm tra Boot/Gateway version và Actuator mapping |
| **405 Method Not Allowed** | Operation tồn tại nhưng method không được hỗ trợ/được cấp access | Kiểm tra read-only vs write operation ở phiên bản thật |
| **200 với JSON rỗng** | Endpoint đọc được nhưng chưa có route, route repository trống, hoặc response không có thông tin mong đợi | Xác minh route definition source và instance |
| **500 hoặc 503** | Lỗi nội bộ khi dựng route definitions, actuator, security hoặc dependency | Xem log an toàn, stack/metadata theo quyền |

**Status không luôn chỉ ra duy nhất một nguyên nhân.** Ví dụ một path không được expose có thể trả 404 ở lớp mapping, nhưng security chain có matcher rộng có thể trả 401/403 **trước khi biết** có handler tương ứng hay không. Với write endpoint read-only, phản hồi có thể là 403, 404 hoặc 405 tùy security/mapping/version. Kiểm chứng bằng chính sách và endpoint behavior, không lấy một status làm bằng chứng cuối cùng.

### Quy trình chẩn đoán không cần mở rộng quyền

1. **Xác minh đúng HTTP port**, scheme, base path và reverse proxy path rewrite.
2. **Kiểm tra Actuator starter** và version Spring Boot + Spring Cloud Gateway trong dependency được duyệt.
3. **Kiểm tra endpoint access/enable**, tránh trộn property của hai đời.
4. **Kiểm tra exposure include**, không đổi tạm thành `"*"` trên production.
5. **Kiểm tra security matcher/chain order**, issuer/audience/authority của operator.
6. **Gọi health endpoint đã phê duyệt** để xác nhận management server đang sống, nhưng không suy ra gateway endpoint đã bật từ health 200.
7. **Gọi read endpoint bằng token ops hợp lệ** trong management network.
8. **Kiểm tra route ID và repository** nếu endpoint trả JSON nhưng không thấy route mong đợi.
9. **Chạy negative tests cho write access trong lab**, không gửi POST/DELETE thử trực tiếp lên production.

### Tình huống cụ thể: health UP, gateway trả 404

Đây không nhất thiết là lỗi proxy. Có thể Boot Actuator đang expose `health`, nhưng `gateway` chưa được phép bởi `management.endpoint.gateway.access` hoặc chưa nằm trong `web.exposure.include`. Giải pháp là chọn đúng property **theo phiên bản**, không sửa route predicates hoặc bật `permitAll`.

### Tình huống cụ thể: route listing có 200 nhưng client API nhận 503

GET route listing chỉ xác nhận **route đã nạp vào instance**. HTTP 503 của client có thể do thiếu ServiceInstance, TLS/connect timeout, backend quá tải, circuit breaker OPEN, Gateway rate limiting/fallback hoặc upstream trả 503. Phải xem **load balancer, HTTP client, breaker state và telemetry**; mở thêm Actuator write access không giúp sửa đúng nguyên nhân.

## 15. Một phiên bản không được nhận cả hai cấu hình một cách mù quáng

Khi chuyển từ cơ chế `enabled` sang `access`, một số tình huống gây nhầm:

~~~yaml
# KHÔNG NÊN copy chung kiểu này mà không biết precedence/version.
management:
  endpoint:
    gateway:
      enabled: true
      access: read-only
~~~

Ở một phiên bản, `enabled` có thể vẫn được đọc để tương thích; ở phiên bản khác, `access` mới là cấu hình chính; ở một bản không hỗ trợ một property, nó có thể không có tác dụng. Nếu một config layer khác (environment, config server, deployment manifest) override, kết quả còn khác giá trị trong application YAML.

### Nguyên tắc viết cấu hình dễ kiểm toán

- **Khóa BOM**, không trộn một starter Gateway quá mới vào Boot cũ chỉ để có endpoint access.
- Chọn **một nguồn cấu hình quản trị được phê duyệt**, tránh giá trị trùng nhau rải trong nhiều profiles.
- Ghi rõ trong tài liệu triển khai: “Boot/Gateway version, property bật endpoint, mode access, exposure, port, allowed principals, write policy”.
- Với phiên bản hỗ trợ `access`, đặt `read-only` một cách **tường minh**, không dựa vào default thay đổi qua upgrade.
- Kiểm tra config binding warnings sau khi nâng cấp, nhưng không coi “ứng dụng khởi động được” là đã an toàn.
- Có test “GET được đọc, POST/DELETE không thực hiện được” trước khi đưa bản release mới lên production.

### Cấu hình theo môi trường

Một chính sách hợp lý có thể là:

| Môi trường | Gateway Actuator | Ai được xem? | Có cho thay đổi route runtime? |
| --- | --- | --- | --- |
| Local development | Có thể bật read-only cho học/diagnostics | Developer trên máy local | Chỉ trong lab có kiểm soát |
| CI/integration test | Bật theo bài test, kể cả unrestricted nếu phải test write | Test harness cô lập | Cho phép trong test sandbox |
| Staging | Read-only, network private, auth | SRE/ops đã cấp quyền | Theo change workflow nếu có nhu cầu |
| Production | Read-only hoặc tắt khi không cần | Rất ít operator/automation được phê duyệt | Mặc định **không**; chỉ khi quy trình riêng yêu cầu |

**Không coi staging là môi trường an toàn để dùng token production.** Dữ liệu và credentials thử nghiệm phải được tách riêng. Ở production, nếu chỉ dùng health/metrics để vận hành và không cần route listing, **tắt Gateway endpoint hoàn toàn** là lựa chọn giảm attack surface tốt.

## 16. Route information cũng là dữ liệu nhạy cảm

Rủi ro lớn của read-only endpoint là **lộ thông tin**, dù không có mutation:

~~~text
GET /actuator/gateway/routes
    -> route ids
    -> predicates / host & path patterns
    -> gateway filter names / arguments
    -> lb:// service IDs or HTTP backend URIs
    -> route metadata / ordering
~~~

Những thông tin này có thể giúp kẻ tấn công xác định:

- API admin hoặc endpoint nội bộ không được công bố rộng rãi.
- Cách path/header được rewrite để tiếp cận backend.
- Service ID và địa chỉ mạng nội bộ, kể cả những service dùng TLS/mTLS.
- Các tầng rate limiting, authentication filter hoặc fallback được cấu hình.
- Route ID để nhắm tới lỗi cấu hình hoặc thông tin trong logs.

### Ba quy tắc về bí mật trong route configuration

1. **Không nhúng credentials** trong `uri`, route metadata, request header filter args hoặc raw URL query. Quản lý secrets bằng cơ chế chuyên biệt, dùng service identity/TLS và token exchange theo nhu cầu.
2. **Không ghi nguyên Actuator response vào log/ticket công khai**. Khi gửi output cho support, lọc URI, host, filter args và thông tin nhạy cảm.
3. **Giới hạn người được xem** qua policy read-only + role/scope ops + private network. Người có quyền GET vẫn có thể sao chép response, nên cần audit, retention và quyền truy cập phù hợp.

### Dữ liệu nào nên xuất sang hệ thống metrics?

Nếu cần đo số route hoặc xác định routing failures, ưu tiên metadata chuẩn có cardinality hữu hạn như **route ID**, HTTP status, latency và loại lỗi đã chuẩn hóa. Không dùng:

- Raw JWT, API key, Cookie hoặc secret filter arguments.
- Raw request URI có `?access_token=...`.
- User ID/tenant ID hoặc host do client tự chỉ định làm metric label không kiểm soát.
- Toàn bộ Actuator JSON làm một span attribute.

Tách **logs, metrics, traces** với Actuator route listing: mỗi kênh có quyền truy cập và mức nhạy cảm khác nhau. Bật Gateway Actuator không tự làm Reactor Netty wiretap hoặc HTTP body logging an toàn; mỗi cơ chế cần chính sách riêng.

## 17. Spring Cloud Gateway nhiều replica: route listing có nhất quán không?

Trong Kubernetes hoặc deployment nhiều instances, một công cụ operator có thể truy cập management port của **một Gateway pod**:

~~~mermaid
flowchart TD
    Ops["Ops read request"] --> Mgmt["Private management service"]
    Mgmt --> G1["Gateway G1: route set v2"]
    Mgmt --> G2["Gateway G2: route set v1"]
    Mgmt --> G3["Gateway G3: route set v2"]
    Pub["Public ingress"] --> G1
    Pub --> G2
    Pub --> G3
~~~

Nếu route definitions được nạp từ config files, service discovery hoặc repository động, có thể có **độ trễ áp dụng cấu hình**, version mismatch hoặc các instances chưa restart/refresh đồng thời. Do đó:

- GET `/actuator/gateway/routes` của G1 **không chứng minh** G2 và G3 có cùng danh sách.
- Một POST refresh trỏ qua load balancer tới một Pod **không tự đảm bảo** mọi Pod đã refresh.
- Một route tạo động trên G1 **không mặc nhiên** tồn tại trên G2 nếu nguồn lưu không chia sẻ.
- Routing bugs có thể xuất hiện không ổn định vì client bị đưa tới các instances khác nhau.

### Kiểm tra nhất quán khi rollout

1. Xác định **source of truth** cho route definitions: config repository, static YAML, discovery, database hay custom RouteDefinitionRepository.
2. Gắn **deployment revision/config version** bằng metadata vận hành không nhạy cảm.
3. Kiểm tra route count/IDs trên từng instance hoặc một quy trình truy vấn có kiểm soát từng Pod.
4. Thử request qua từng instance hoặc điều phối test để phát hiện mismatch.
5. Kiểm tra readiness trước khi ingress đưa Pod mới vào phục vụ.
6. Nếu có refresh runtime, mô tả **sự kiện nào refresh**, propagation delay, rollback và hậu quả khi một Pod bỏ lỡ.

Không cần mở `access: unrestricted` để giải quyết mọi inconsistency. Đôi khi lỗi nằm ở config sync, deployment hoặc cache; cách xử lý là sửa **nguồn định nghĩa và rollout process**, không thêm thao tác ghi tùy ý trên từng instance.

## 18. Bảo vệ đường quản trị khi có gateway trên gateway

Nhiều tổ chức đặt một reverse proxy, ingress hoặc một Gateway khác phía trước management endpoint. Khi ấy phải phân biệt **hostname, path, authentication và upstream**:

~~~mermaid
flowchart LR
    O["Trusted operator"] --> Z["VPN / zero-trust access"]
    Z --> I["Private ingress / mTLS"]
    I --> S["Spring Security WebFlux"]
    S --> A["/actuator/gateway/routes"]
    X["Internet client"] -. "Denied by network" .-> I
~~~

Các điểm cần kiểm tra:

1. **Không tạo public route** `Path=/actuator/**` trỏ thẳng vào management port chỉ để dễ gọi.
2. Nếu ingress rewrite `/manage` thành `/actuator`, security chain phải kiểm tra **đúng path mà ứng dụng nhận**, và ingress phải không lộ các đường vòng.
3. Không coi một header như `X-Operator: true` hoặc `X-Forwarded-Host` do client tự khai là bằng chứng danh tính.
4. Nếu proxy có authentication, vẫn cần xác định **mối tin cậy giữa proxy và Gateway**, và cách Gateway nhận/xác minh principal; TLS/mTLS hoặc token audience giới hạn thường hữu ích.
5. Xác định giới hạn request/response size, timeout, rate limiting và audit cho management plane; không để một endpoint route listing quá lớn tạo chi phí không giới hạn.
6. Kiểm tra HTTPS/mTLS tới management server khi đi qua mạng; tránh truyền token ops dưới dạng plain HTTP ngoài loopback được tin cậy.

**Đổi URL thành tên khó đoán không phải bảo mật.** Cần nhận diện operator, quyền tối thiểu, network isolation và evidence từ negative tests.

## 19. Kiểm thử phân quyền Gateway Actuator với WebTestClient

Một cấu hình bảo mật chỉ được coi là đạt khi có **negative tests**: request không có quyền không đọc được route, request có token user thông thường không được đọc, và request dùng operator token với quyền chỉ đọc **không thể thay đổi route**.

### Ma trận quyền cần có

Giả sử môi trường lab dùng `read-only`, exposure chọn lọc và Security WebFlux như phần 7:

| Request | Anonymous | User token hợp lệ nhưng không có quyền ops | Operator có `SCOPE_gateway.read` |
| --- | --- | --- | --- |
| `GET /actuator/health` | Được phép nếu health được expose | Được phép | Được phép |
| `GET /actuator/gateway/routes` | **401** thường gặp | **403** thường gặp | Được đọc route listing |
| `GET /actuator/gateway/globalfilters` | Bị từ chối | Bị từ chối | Được đọc nếu operation khả dụng |
| `GET /actuator/gateway/routes/orders-read` | Bị từ chối | Bị từ chối | Được đọc khi route ID tồn tại |
| `POST /actuator/gateway/refresh` | Bị từ chối hoặc operation không được đăng ký | Bị từ chối hoặc operation không được đăng ký | **Không được refresh** |
| `POST /actuator/gateway/routes/new-route` | Bị từ chối hoặc operation không được đăng ký | Bị từ chối hoặc operation không được đăng ký | **Không được tạo route** |
| `DELETE /actuator/gateway/routes/orders-read` | Bị từ chối hoặc operation không được đăng ký | Bị từ chối hoặc operation không được đăng ký | **Không được xóa route** |
| `GET /actuator/env` | Bị từ chối | Bị từ chối | **Bị từ chối** theo policy ví dụ |

**Mã lỗi chính xác** có thể là 401, 403, 404 hoặc 405 theo thứ tự security/mapping/phiên bản. Điều phải bảo đảm ở các thao tác ghi là **không có mutation**. Đừng chấp nhận HTTP 2xx chỉ vì một response có chữ “error” trong body.

### Test tích hợp: anonymous và operator đọc

Trong môi trường kiểm thử cô lập, có thể dùng `WebTestClient` gọi **management port thật**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayActuatorAccessIT {

    private final WebTestClient client = WebTestClient.bindToServer()
            .baseUrl("http://127.0.0.1:9091")
            .build();

    @Test
    void anonymousCannotReadRoutes() {
        client.get()
                .uri("/actuator/gateway/routes")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void operatorCanReadRoutes() {
        // Token do IdP test cấp với issuer/audience/scope đúng.
        String token = System.getenv("OPS_READ_TEST_TOKEN");
        assertThat(token).isNotBlank();

        client.get()
                .uri("/actuator/gateway/routes")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void operatorCannotUseRefreshWriteOperation() {
        // Chỉ chạy trên sandbox; nếu cấu hình sai, POST có thể thay đổi state.
        String token = System.getenv("OPS_READ_TEST_TOKEN");
        assertThat(token).isNotBlank();

        client.post()
                .uri("/actuator/gateway/refresh")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .exchange()
                .expectStatus().is4xxClientError();
    }
}
~~~

**Điều kiện chạy:** Gateway phải được khởi động trong lab tại port 9091, Actuator và Spring Security được cấu hình phù hợp, có JUnit/Spring Test/AssertJ và token chỉ dành cho test. Đoạn code minh họa **không phải kết quả đã chạy**. Ở một topology khác, thay port/base path theo deployment.

Test POST ở trên **chỉ an toàn trong sandbox** vì nếu security sai thì refresh có thể thực sự xảy ra. Trong test thực tế, ngoài status hãy kiểm tra **không có side effect** bằng event/counter hoặc snapshot route definitions. Đối với DELETE, chỉ dùng route ID giả và repository cô lập; không gửi DELETE tới route quan trọng trên production.

### Test quyền app user và token sai

Bổ sung test dùng token test hợp lệ **không có** `SCOPE_gateway.read` và yêu cầu GET route listing bị từ chối. Sau đó thử:

1. JWT sai chữ ký.
2. JWT hết hạn.
3. JWT sai issuer hoặc audience.
4. JWT có claim `roles: ["OPS"]` nhưng authority converter chưa map thành `SCOPE_gateway.read`.
5. Token ops đã thu hồi/hết hạn theo chính sách IdP.

**Test `mockJwt()` chỉ chứng minh matcher/authority logic**, không xác nhận chữ ký, issuer, audience và cấu hình JWKS thực. Dùng signed test tokens/IdP test và decoder thật để kiểm thử authentication end-to-end.

### Test trên đúng context/port

Nếu `management.server.port` là 9091, kiểm thử trực tiếp 9091 **và** thử truy cập `/actuator/gateway/routes` qua public API port 8080. Kỳ vọng public path không lộ endpoint management khi kiến trúc chỉ expose ở cổng riêng. Nếu proxy rewrite path hoặc có management path mapping đặc biệt, test cả ingress, không chỉ WebTestClient bind trực tiếp ở process.

## 20. Bảng lỗi cấu hình thường gặp và cách sửa

| Phản mẫu hoặc sự cố | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Thêm `spring-boot-starter-actuator` rồi nghĩ Gateway endpoint đã bật và được bảo vệ | Endpoint không hiện, hoặc hiện với quyền không dự kiến | Chọn enable/access, exposure và security theo version |
| Dùng `enabled: true` trên phiên bản nên dùng `access` mà không kiểm thử | Không có bảo đảm read-only | Dùng property theo phiên bản, test write-denied |
| Chỉ đặt `web.exposure.include=gateway` | Endpoint có thể chưa khả dụng hoặc security chưa đúng | Kiểm tra cả ba cửa access/expose/security |
| Coi `read-only` là thay cho auth | Người ngoài có thể đọc route/filter nếu port public | Bảo vệ Spring Security + network |
| Dùng `management.endpoints.web.exposure.include: "*"` | Mở rộng nhiều management surfaces nhạy cảm | Include có chọn lọc |
| Có `anyExchange().permitAll()` trong custom security chain | Actuator có thể bị lộ khi Boot auto-security back off | Management chain riêng, deny by default |
| Chỉ gắn GatewayFilter bảo mật cho `Path=/actuator/**` | Không nhất thiết chạy với Actuator handler | Dùng WebFlux SecurityWebFilterChain |
| Dùng `hasRole("ADMIN")` của admin nghiệp vụ | Trộn quyền ứng dụng với quyền hạ tầng | Tách ops read/write authorities |
| Đặt management port khác nhưng không test security context | Cổng riêng có thể không nhận đúng chain | Integration test trực tiếp management port |
| Dùng loopback trong container rồi Prometheus không scrape được | Mất monitoring/readiness | Chọn network boundary phù hợp + policy |
| Expose 9091 qua public LoadBalancer | Management API bị truy cập từ Internet | Private Service, firewall/NetworkPolicy, TLS |
| Đổi `base-path: /manage` nhưng quên security matcher | Rule cũ không còn khớp | Cập nhật route/path matcher và test |
| Route listing trả 404 nhưng sửa Path predicate | Chẩn đoán sai lớp | Kiểm tra Actuator access/exposure/path |
| GET routes trả 200 nên coi Orders backend healthy | Bỏ qua no-instance, TLS, timeout | Dùng health/metrics/traces của dependency |
| POST refresh sau rollout mà chỉ tác động một Pod | Các Gateway replicas không đồng bộ | Thiết kế config propagation/source of truth |
| Cho phép dynamic routes có URI tùy ý | SSRF, route bypass, token exfiltration | Approve change, destination allowlist, network egress policy |
| Đưa API key vào `SetRequestHeader` rồi expose route listing | Rò secret qua output/diagnostics | Secret management riêng, giới hạn endpoint output |
| Dùng token user để gọi management | Phân quyền quá rộng | Token ops riêng, audience/scope rõ |
| Kiểm tra write bằng DELETE route thật trên production | Có thể gây outage nếu config sai | Negative test trong sandbox |
| Log toàn JSON routes ra ticket công khai | Lộ cấu trúc nội bộ | Redaction và quyền chia sẻ |

### Khi 404 không hết dù đã thêm exposure

Đừng tiếp tục chỉnh firewall hoặc nới `permitAll` nếu response 404. Trước hết xác nhận:

- Đúng application **Gateway Server WebFlux** và có **Actuator starter**.
- Endpoint Gateway đã khả dụng theo `access` hoặc `enabled` đúng phiên bản.
- HTTP exposure include có `gateway`, không chỉ `health`.
- Base path/port đúng, không có ingress rewrite.
- Security chain không chủ động trả 404 theo custom handler.
- Route path `/actuator/gateway/routes` đúng với endpoint mappings mà bản triển khai cung cấp.

Không có bằng chứng nào buộc phải mở Actuator bằng wildcard; wildcard chỉ làm tăng bề mặt tấn công.

## 21. Quy trình triển khai và rollback cho Gateway Actuator

Thay đổi management plane phải được review như một thay đổi bảo mật, kể cả khi chỉ thêm GET read-only.

### Trước triển khai

1. **Chốt phiên bản:** ghi rõ Spring Boot/Gateway version và dependency BOM.
2. **Chốt mục tiêu:** cần đọc routes, filters hay cần write operations? Nếu không cần, không bật endpoint.
3. **Chọn mode:** `read-only` nếu được hỗ trợ; với dòng cũ, bật `enabled` kèm security/network nghiêm ngặt.
4. **Chốt network:** management port, private address, ingress, mTLS/TLS và ai được phép kết nối.
5. **Chốt authorization:** scope/role ops, issuer/audience, lưu/token rotation, break-glass policy.
6. **Chốt exposure:** chỉ include những endpoint ID cần dùng; giữ health details tối giản.
7. **Chuẩn bị tests:** đọc được route với ops token, chặn anonymous/user token và mọi writes ngoài quy trình.

### Trong triển khai

1. Áp cấu hình vào một môi trường staging/lab cùng phiên bản.
2. Kiểm thử từ management network và một **nguồn không được phép**, để xác minh firewall/security thực.
3. Kiểm tra endpoint trả output không làm lộ credentials và không vô tình show internal secrets.
4. Thực hiện rollout có kiểm soát, kiểm tra các replica và config revision.
5. Theo dõi rate/latency/error của API Gateway để phát hiện bất thường khi management server được bật.
6. Xác nhận probes, Prometheus scraping và automation không bị ảnh hưởng bởi việc đổi port/path.

### Nếu phát hiện exposure sai

1. **Ngăn truy cập ngay ở network boundary** để giảm rủi ro trong lúc sửa cấu hình.
2. Thu hẹp HTTP exposure, chuyển endpoint về read-only hoặc disable theo phiên bản; thay đổi config/deployment có kiểm soát.
3. Kiểm tra logs/audit để xem có GET route information hoặc POST/DELETE được thực hiện bởi nguồn không mong đợi.
4. Nếu route bị sửa trái phép, khôi phục từ **source of truth**, xác minh từng instance và kiểm tra đích/token egress.
5. Nếu có secret lộ qua route listing, thực hiện quy trình rotation/revocation thích hợp; không chỉ xóa dòng log.
6. Bổ sung negative tests và kiểm soát thay đổi để ngăn tái diễn.

**Không “sửa nhanh” bằng cách đổi base path thành một chuỗi khó đoán**. Đó là obscurity, không giải quyết quyền truy cập thực tế.

## 22. Bài thực hành: bật Gateway Actuator chỉ đọc trong một Gateway có nhiều route

**Bối cảnh:** Một hệ thống học tập gồm Catalog, Orders và Identity service. Spring Cloud Gateway tiếp nhận request qua port `8080` và có route predicates/filters cho ba service. Người học muốn kiểm tra route nào đã nạp, nhưng **không muốn người dùng Internet hoặc user đăng nhập thông thường nhìn thấy hoặc sửa route**.

### Phần A — Xác nhận môi trường và chọn mode

1. Xác định Gateway đang dùng **Server WebFlux**, Spring Boot/Gateway versions và Actuator starter.
2. Dựng một backend stub cho Catalog và một service ID/URI minh họa Orders; xác minh API public/private route hoạt động theo contract.
3. Nếu phiên bản hỗ trợ `management.endpoint.gateway.access`, chọn **`read-only`** và include HTTP exposure đúng endpoint ID.
4. Nếu dòng cũ chỉ hỗ trợ `enabled`, bật endpoint bằng cấu hình được version hỗ trợ, nhưng **không coi read-only đã được bảo đảm**; chuẩn bị explicit HTTP read-only method policy và network isolation.
5. Chọn management port private, ví dụ 9091; với container, quyết định cách bind/listener phù hợp với monitoring network.
6. Không bật `unrestricted` ngoài sandbox nếu không có mục đích và quy trình thay đổi rõ.

### Phần B — Cấu hình các đường truy cập

Một cấu hình lab ở **dòng Spring Boot hỗ trợ read-only endpoint access**:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoint:
    gateway:
      access: read-only
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info,gateway

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
            - id: orders-read
              uri: http://127.0.0.1:9002
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
~~~

Trong ví dụ này, backend test cần nghe `9001`/`9002` trên đúng namespace mà Gateway có thể kết nối; nếu chạy trong Docker, `127.0.0.1` của Gateway container **không phải** địa chỉ của container backend. Khi đổi sang service discovery, dùng `lb://catalog-service` và dependency Spring Cloud LoadBalancer phù hợp. Hai route là dữ liệu test; người học không cần giả định Identity service thực sự có mặt để kiểm thử Actuator route listing.

**Phải bổ sung Spring Security** theo phần 7 hoặc một policy management-port tương đương đã được kiểm chứng. YAML trên chỉ minh họa port/exposure/access và route definitions; tự thân nó chưa hoàn thiện bảo mật.

### Phần C — Kiểm tra đọc route

Trong lab với management server đã bảo vệ:

~~~bash
# Probe health tối thiểu:
curl -i 'http://127.0.0.1:9091/actuator/health'

# Không có token ops: kỳ vọng bị chặn:
curl -i 'http://127.0.0.1:9091/actuator/gateway/routes'

# Với token ops READ của môi trường TEST:
curl -i \
  -H "Authorization: Bearer ${OPS_READ_TEST_TOKEN}" \
  'http://127.0.0.1:9091/actuator/gateway/routes'

# Xem route cụ thể:
curl -i \
  -H "Authorization: Bearer ${OPS_READ_TEST_TOKEN}" \
  'http://127.0.0.1:9091/actuator/gateway/routes/catalog-read'
~~~

Kiểm tra route IDs `catalog-read` và `orders-read`, URI đích, predicates và filters. Nếu JSON format khác ví dụ tài liệu, không ép nó thành một schema tự đoán: dùng endpoint output thực của phiên bản đang chạy và chỉ assert các thuộc tính liên quan.

**Không dùng token thật trong output bài thực hành**. Sử dụng signed JWT chỉ dùng cho môi trường test, có TTL ngắn và audience/scope phù hợp. Sau khi hoàn tất, thu hồi hoặc để hết hạn token test theo quy trình.

### Phần D — Negative tests cho read/write

| Case | Hành động trong lab | Kỳ vọng |
| --- | --- | --- |
| A | Anonymous GET `/actuator/gateway/routes` | Bị security chặn |
| B | User JWT không có quyền ops GET route listing | Bị từ chối quyền |
| C | JWT `SCOPE_gateway.read` GET route listing | Thành công nếu endpoint nạp đúng |
| D | JWT ops-read POST refresh | **Không refresh được** |
| E | JWT ops-read POST route mới | **Không tạo route được** |
| F | JWT ops-read DELETE route test | **Không xóa được** |
| G | JWT sai issuer/audience/expired GET routes | Không được đọc route |
| H | Từ mạng/ingress không được phép GET routes | Không thể truy cập management endpoint theo policy |
| I | Từ public API port `8080` gọi `/actuator/gateway/routes` | Không expose endpoint management qua port public |
| J | Đổi base path management trong lab | Chỉ mapping/matcher mới đúng; đường cũ không mở ngoài dự kiến |
| K | Hạ quyền `access: none` trong lab | Endpoint Gateway không còn khả dụng |
| L | Bản cũ với `enabled: true` | GET hoạt động theo policy, writes vẫn bị security/network chặn |

Các case D/E/F **chỉ chạy trong sandbox với repository/route IDs thử nghiệm**, không gọi route quan trọng trên production. Sau mỗi test, xác nhận **không có thay đổi route definitions**. Với read-only mode, operation có thể không được đăng ký; status 403/404/405 phụ thuộc phiên bản và security order, nhưng **không có HTTP write nào được thực hiện** mới là tiêu chí.

### Phần E — Mô phỏng vận hành nhiều replica

1. Chạy hai Gateway instances G1 và G2 với cùng route definitions từ source of truth test.
2. Gọi read endpoint của **từng instance**, không chỉ qua một load balancer ngẫu nhiên.
3. So sánh route IDs, predicates, URI và config/deployment revision.
4. Thay cấu hình route của G1 **trong sandbox** để thấy mismatch được phát hiện.
5. Khôi phục bằng config/deployment workflow đã kiểm soát; không cố tạo động một route ghi đè mọi thứ.
6. Kiểm tra public API vẫn định tuyến đúng, management security không cho user thường truy cập.

### Phần F — Chẩn đoán và hoàn thành báo cáo

Ghi lại các thông tin:

- Spring Boot và Spring Cloud Gateway versions, starter và namespace route.
- Property **`access` hoặc `enabled`** đã dùng và lý do.
- `management.endpoints.web.exposure.include` cùng management port/base path.
- Quy tắc Spring Security, JWT issuer/audience/authority của ops.
- Kết quả GET route listing với token ops và negative tests anonymous/user.
- Bằng chứng write operations không được phép; không có route bị tạo/xóa/refresh trái ý.
- Kết quả truy cập từ management network và mạng ngoài policy.
- Sự nhất quán route giữa các replicas, nếu có.

**Tiêu chí đạt:** Gateway Actuator hoạt động ở đúng version/configuration, người vận hành đọc được route/filter để chẩn đoán, user thường và Internet không truy cập được, write operations không xảy ra ngoài chính sách, không lộ secrets, và không nhầm việc đọc route với kiểm tra sức khỏe backend.

## 23. Tổng kết

- **Gateway Actuator là management plane**, khác với các API do Spring Cloud Gateway proxy cho client. Nó giúp kiểm tra route/filter và trong một số chế độ/phiên bản còn cho thay đổi route.
- Muốn bật an toàn phải xét **ba cửa**: endpoint access/enable, HTTP exposure và authentication/authorization + network isolation.
- Với Spring Boot/Gateway hỗ trợ access mode, **`management.endpoint.gateway.access: read-only`** là lựa chọn phù hợp khi chỉ cần quan sát. Trong dòng cũ, **`management.endpoint.gateway.enabled: true`** không tương đương một cam kết read-only.
- **`management.endpoints.web.exposure.include=gateway` chỉ mở HTTP surface**, không cấp quyền hoặc tự bảo vệ người đọc. Không dùng wildcard exposure trên Gateway công khai.
- Dùng **Spring Security WebFlux** với authority ops chuyên biệt và deny-by-default; không dùng GatewayFilter hoặc role admin nghiệp vụ thay cho bảo mật Actuator.
- **Management port private, TLS/mTLS, network policies và kiểm tra từ mạng không được phép** là lớp phòng vệ quan trọng. Với port riêng hoặc container, phải kiểm chứng context, bind address và path thực.
- Read operations như `GET /actuator/gateway/routes` có thể tiết lộ service IDs, backend URIs, predicates và filter args. Đừng ghi secrets vào route definitions hoặc chia sẻ Actuator output công khai.
- Write operations như refresh, create route hoặc delete route có nguy cơ gây outage, SSRF và credential exfiltration; **chỉ bật unrestricted khi có quy trình vận hành riêng**.
- Ở triển khai nhiều replicas, **route listing của một instance không chứng minh cả cụm đã đồng bộ**. Dựa vào source of truth, rollout checks, health, metrics và request traces để chẩn đoán.
- Test phải xác minh **GET được phép cho ops, anonymous/user bị chặn, POST/DELETE không gây mutation**, đồng thời phân biệt 401/403/404/405 theo cấu hình và phiên bản.

Mục tiêu không phải “mở càng nhiều Actuator endpoint càng tiện vận hành”, mà là **cung cấp đủ khả năng quan sát cần thiết trên một kênh quản trị được bảo vệ, với quyền thấp nhất và hành vi tương thích chính xác với phiên bản đang chạy**.
