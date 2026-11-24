# Tách tuyến công khai, tuyến cần đăng nhập và tuyến quản trị

## 1. Vấn đề cần giải quyết ở API Gateway

Trong một hệ thống microservices, **Spring Cloud Gateway** thường là điểm vào cho nhiều nhóm API: xem danh mục sản phẩm không cần đăng nhập, xem tài khoản/đơn hàng của chính mình sau khi xác thực, và quản lý tài nguyên dành riêng cho nhân viên quản trị. Gateway còn thực hiện route predicate, filter chain, sửa path/header, service discovery, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request. **Không phải mọi route đều nên có cùng quyền truy cập.**

Giả sử hệ thống bán hàng có ba nhóm endpoint:

| Nhóm | URL công khai mẫu | Ai được phép? | Ví dụ nghiệp vụ |
| --- | --- | --- | --- |
| **Public** | `GET /api/public/products/42` | Người dùng chưa đăng nhập cũng có thể đọc | Xem danh mục, thông tin sản phẩm công khai |
| **Authenticated** | `GET /api/account/profile` | Người dùng có phiên/token hợp lệ | Xem hồ sơ của chính mình |
| **Admin** | `DELETE /api/admin/products/42` | Danh tính đã xác thực **và** có quyền quản trị phù hợp | Xóa sản phẩm hoặc thay đổi cấu hình |

Nếu chỉ khai báo các route rồi nghĩ rằng path `/api/admin/**` “khó đoán” hoặc có header `X-Role: admin` là đủ an toàn, hệ thống có thể cho phép truy cập trái phép. **Route chỉ xác định đích chuyển tiếp; authorization mới quyết định ai được thực hiện hành động.**

Trong chương **Xác thực và phân quyền** của **Spring Cloud Gateway**, bài này tập trung vào thiết kế ranh giới giữa các route và thực thi bằng **Spring Security WebFlux**. Sau khi học, bạn có thể:

1. Phân loại endpoint public, cần đăng nhập và chỉ dành cho admin theo hợp đồng API.
2. Viết route Gateway và chính sách `SecurityWebFilterChain` tương ứng, tránh chồng lấn hoặc để hở endpoint.
3. Hiểu thứ tự xử lý giữa **WebFilter bảo mật**, **route predicates** và **GatewayFilter/GlobalFilter**.
4. Xác thực JWT theo issuer, chữ ký và thời hạn; liên kết quyền admin với **authority/claim đáng tin cậy**.
5. Phân biệt lỗi **401 Unauthorized** với **403 Forbidden**, và kiểm soát response không rò rỉ dữ liệu.
6. Xây ma trận kiểm thử anonymous/user/admin; xử lý preflight CORS, CSRF, token relay và các tuyến quản trị đặc biệt.
7. Bảo vệ cả upstream service, không coi Gateway là ranh giới tin cậy duy nhất.

> **Phạm vi:** Các ví dụ dùng **Spring Cloud Gateway Server WebFlux** và Spring Security reactive. Spring Cloud Gateway Server Web MVC có mô hình filter/config khác. Namespace route và starter phụ thuộc phiên bản Spring Boot/Spring Cloud; hãy chọn đúng phiên bản trong dự án.

## 2. Phân biệt định tuyến, xác thực và phân quyền

Ba quyết định thường cùng xuất hiện ở Gateway nhưng có mục tiêu khác nhau:

| Quyết định | Câu hỏi | Cơ chế thường dùng |
| --- | --- | --- |
| **Routing** | Request này thuộc API/service nào? | `Path`, `Method`, `Host`, `Header` predicates và route URI |
| **Authentication** | Caller là ai? Bằng chứng danh tính có hợp lệ không? | Spring Security, JWT/OAuth2 Resource Server, session, mTLS tùy thiết kế |
| **Authorization** | Caller đã xác thực có quyền làm việc này không? | `authenticated()`, `hasAuthority(...)`, policy theo scope/role và kiểm tra nghiệp vụ |

Ví dụ, một route có predicate:

~~~yaml
predicates:
  - Path=/api/admin/**
  - Header=X-Role, ^admin$
~~~

**Không phải một cơ chế phân quyền.** Bất kỳ client nào cũng có thể tự gửi `X-Role: admin` nếu biên mạng không kiểm soát header. Kết quả chỉ cho biết request **đủ điều kiện match route**, không chứng minh caller là quản trị viên.

Đối với tài nguyên nhạy cảm như đơn hàng, **phân quyền còn phụ thuộc tài nguyên cụ thể**: ngay cả user đã đăng nhập cũng không được xem đơn hàng của user khác. Gateway có thể yêu cầu token hợp lệ, nhưng service Orders phải kiểm tra người dùng có quyền với `orderId` đang truy cập.

### “Public” không có nghĩa “không cần bảo vệ”

Endpoint public vẫn cần TLS, input validation, bảo vệ khỏi scraping/abuse, rate limit, giới hạn body, CORS thích hợp và logging không lộ dữ liệu. `permitAll()` chỉ nói rằng **không yêu cầu authentication để đi tiếp**, không loại bỏ các biện pháp vận hành và an toàn khác.

### “Admin” không chỉ là “đã đăng nhập”

`authenticated()` cho phép mọi caller có authentication hợp lệ, kể cả tài khoản người dùng bình thường. Tuyến admin cần quy tắc **hạn chế hơn**, ví dụ `hasAuthority("SCOPE_admin")` khi OAuth2 access token thực sự được cấp scope `admin`, hoặc quy tắc role đã được mapping từ một nguồn danh tính đáng tin.

## 3. Thiết kế ma trận truy cập trước khi viết code

Hãy viết chính sách truy cập thành bảng trước khi cấu hình route. Một chính sách mẫu:

| API | Anonymous | User hợp lệ | Admin hợp lệ | Điều kiện bổ sung |
| --- | --- | --- | --- | --- |
| `GET /api/public/products/**` | Cho phép | Cho phép | Cho phép | Dữ liệu phải thực sự công khai |
| `POST /auth/login` | Cho phép | Cho phép theo contract | Cho phép theo contract | Chống brute force; không lộ lý do sai mật khẩu |
| `GET /api/account/profile` | Từ chối | Cho phép | Cho phép nếu contract cho phép | Service kiểm tra identity/ownership |
| `PATCH /api/account/profile` | Từ chối | Cho phép | Cho phép nếu contract cho phép | Kiểm tra field và quyền sửa |
| `GET /api/admin/reports` | Từ chối | Từ chối | Cho phép | Cần authority admin hợp lệ |
| `DELETE /api/admin/products/{id}` | Từ chối | Từ chối | Cho phép | Audit, xác nhận nghiệp vụ, least privilege |
| `GET /actuator/health` | Có thể cho phép | Có thể cho phép | Có thể cho phép | Chỉ lộ thông tin health tối thiểu |
| `/actuator/env`, `/actuator/beans` | Từ chối | Từ chối | Không tự cho phép | Management plane tách biệt và hạn chế truy cập |

**Một nguyên tắc thiết kế tốt là deny-by-default:** endpoint không khớp nhóm được cho phép phải bị từ chối, thay vì tự động coi là public.

### Phân tách bằng path, host hay service?

Có nhiều cách tổ chức:

- **Path-based:** `/api/public/**`, `/api/account/**`, `/api/admin/**`. Dễ trình bày và kiểm thử; ví dụ chính của bài.
- **Host-based:** `api.example.test` cho API công khai, `admin.example.test` cho admin. Có thể giúp phân vùng quản trị, nhưng **DNS/Host predicate không thay thế authorization**.
- **Service-based:** Catalog service cho public, Account service cho authenticated, Admin service cho admin. Địa chỉ backend riêng giúp cô lập mạng nhưng vẫn phải kiểm tra quyền.
- **Theo phương thức:** cùng một path có `GET` public nhưng `POST` yêu cầu admin. Khi dùng kiểu này, chính sách Spring Security phải phản ánh **cả method và path**, không chỉ path.

Trong ví dụ bên dưới, các nhóm path khác nhau giúp giảm rủi ro quy tắc chồng lấn. Với hệ thống thực, một service có thể chứa nhiều cấp quyền; **không suy ra tất cả endpoint của service đều thuộc cùng một cấp bảo vệ**.

## 4. Khai báo route: public, login, authenticated, admin

Một cấu hình ví dụ với **Spring Cloud Gateway Server WebFlux**:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-public
              uri: lb://catalog-service
              predicates:
                - Path=/api/public/products/**
                - Method=GET

            - id: identity-login
              uri: lb://identity-service
              predicates:
                - Path=/auth/login
                - Method=POST

            - id: account-private
              uri: lb://account-service
              predicates:
                - Path=/api/account/**

            - id: administration
              uri: lb://admin-service
              predicates:
                - Path=/api/admin/**
~~~

Giải thích:

1. Route **catalog-public** chỉ nhận GET theo path sản phẩm public.
2. Route **identity-login** chỉ nhận POST đến endpoint cấp token/đăng nhập của ứng dụng.
3. Route **account-private** chuyển các request dành cho tài khoản đến Account service.
4. Route **administration** chuyển request quản trị đến Admin service.

Các URI `lb://` yêu cầu **Spring Cloud LoadBalancer** và nguồn `ServiceInstance` (service discovery hoặc danh sách instance được cấu hình). Nếu đang học với backend local, có thể dùng `http://localhost:9001` và các cổng backend tương ứng.

**Điểm rất quan trọng:** YAML trên **chưa bảo vệ** account hay admin. Nó chỉ mô tả điều kiện chọn route và nơi chuyển request. Ta phải cấu hình **Spring Security** để quyết định ai được phép đi tới chúng.

Các backend trong ví dụ cần hiểu chính xác public path nhận được, như `/api/public/products/42`. Nếu backend mong đợi `/products/42`, hãy bổ sung `StripPrefix` hoặc `RewritePath` có chủ đích, rồi kiểm thử path thực nhận; đừng nhầm biến đổi path với bảo mật.

**Tương thích phiên bản:** Ở các Spring Cloud Gateway WebFlux đời trước, prefix thường là `spring.cloud.gateway.routes` thay vì `spring.cloud.gateway.server.webflux.routes`. Không dùng đồng thời hai kiểu chỉ để “phòng hờ”; kiểm tra tài liệu và dependency thực tế.

## 5. Bảo vệ các nhóm tuyến bằng Spring Security WebFlux

Trong ứng dụng Gateway Server WebFlux, **Spring Security** vận hành thông qua các **WebFilter** của WebFlux, với cấu hình tiêu biểu bằng `SecurityWebFilterChain`. Các quy tắc được áp dụng lên request **trước khi route Gateway thực hiện forwarding thông thường**.

Đối với một API **stateless dùng Bearer JWT** (không xác thực bằng browser session/cookie), có thể cấu hình:

~~~java
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
                // Chỉ phù hợp ở đây vì API minh họa dùng Bearer JWT
                // và không sử dụng cookie/session để xác thực.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchange -> exchange
                        .pathMatchers(HttpMethod.GET, "/actuator/health")
                            .permitAll()
                        .pathMatchers(HttpMethod.POST, "/auth/login")
                            .permitAll()
                        .pathMatchers("/api/admin", "/api/admin/**")
                            .hasAuthority("SCOPE_admin")
                        .pathMatchers("/api/account", "/api/account/**")
                            .authenticated()
                        .pathMatchers("/api/public", "/api/public/**")
                            .permitAll()
                        .anyExchange()
                            .denyAll()
                )
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Những điểm cần giải thích rõ:**

- `permitAll()` cho phép đi tiếp không cần xác thực; nó **không** cấp token, không định tuyến và không bỏ qua các biện pháp như rate limit.
- `authenticated()` yêu cầu authentication hợp lệ, nhưng **không tự giới hạn role, scope hay quyền sở hữu tài nguyên**.
- `hasAuthority("SCOPE_admin")` yêu cầu quyền **SCOPE_admin** xuất hiện trong `Authentication` sau khi token được xác minh và ánh xạ. Với cấu hình JWT mặc định thông thường, scope `admin` trong claim `scope`/`scp` có thể tạo authority `SCOPE_admin`. Token chỉ có claim `role: "admin"` **không tự bảo đảm** có authority này.
- `anyExchange().denyAll()` đảm bảo những request không khớp quy tắc explicit **không được tự động coi là public**. Đường dẫn chưa khai báo route cũng không trở thành public vì lý do đó.
- `oauth2ResourceServer(...jwt(...))` chỉ **xác thực Bearer JWT**. Nó không tạo hoặc phát token cho `POST /auth/login`; việc đó thuộc Identity service/Authorization Server.
- `csrf(...disable)` **chỉ có lý do hợp lệ khi xác thực dựa trên Bearer token không tự động được browser gửi như cookie**. Nếu dùng cookie/session, cần đánh giá và giữ cơ chế bảo vệ CSRF phù hợp; không sao chép dòng này một cách máy móc.

**Yêu cầu dependency:** ứng dụng cần các starter bảo mật WebFlux phù hợp, thường gồm `spring-boot-starter-security` và `spring-boot-starter-oauth2-resource-server`; trường hợp JWT phải có thư viện giải mã/kiểm tra token tương thích. Đừng trộn `SecurityFilterChain` của Servlet MVC với `SecurityWebFilterChain` reactive trong cùng ví dụ.

### Quy tắc được xét theo thứ tự

Trong `authorizeExchange`, các matcher được xét theo thứ tự cấu hình. **Quy tắc cụ thể phải xuất hiện trước quy tắc tổng quát**. Ví dụ nguy hiểm:

~~~java
// SAI về chính sách admin: rule rộng được xét trước!
.authorizeExchange(exchange -> exchange
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
        .anyExchange().denyAll())
~~~

Request `/api/admin/users` có thể bị rule `/api/**` bao phủ trước và chỉ yêu cầu đăng nhập, làm mất yêu cầu admin. Cấu hình an toàn hơn là đặt matcher admin trước matcher rộng; tốt nhất là chia tên namespace rõ ràng và không tạo rule rộng không cần thiết.

### Chính sách bao phủ endpoint gốc

Nếu dùng `/api/admin/**`, đừng quên endpoint chính xác `/api/admin` (không có slash cuối). Mẫu ở trên khai báo cả hai để tránh phụ thuộc không cần thiết vào cách match trailing slash của từng version. Tương tự với `/api/account` và `/api/public`.

## 6. JWT: xác thực danh tính rồi mới xét authority

Spring Security OAuth2 Resource Server có thể xác minh JWT Bearer do một Identity Provider được tin cậy phát hành. Ví dụ cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/store
~~~

Đây là URI minh họa, phải thay bằng **issuer thật đã được cấu hình và tin cậy** trong hệ thống. Provider cần công bố metadata/JWKS hoặc có cơ chế decoder tương thích. Khi deployment, cần đảm bảo Gateway truy cập được nguồn khóa cần thiết theo thiết kế và có cách xử lý sự cố/luân chuyển khóa hợp lệ.

Một access token JWT thường có claims mang ý nghĩa tương tự:

~~~json
{
  "iss": "https://identity.example.test/realms/store",
  "sub": "user-742",
  "aud": ["shop-api"],
  "scope": "catalog.read account.read",
  "exp": 1999999999
}
~~~

Token trên **chỉ là JSON mô tả payload**, không phải token thật có chữ ký; không sử dụng nó để xác thực. Một request thực gửi token:

~~~http
GET /api/account/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...<opaque-redacted>...
~~~

Gateway phải kiểm tra ít nhất các yếu tố phù hợp với mô hình tin cậy:

| Kiểm tra | Ý nghĩa |
| --- | --- |
| **Signature và thuật toán được phép** | Token thực sự được issuer tin cậy ký; tránh chấp nhận thuật toán hoặc khóa do client tự quyết định |
| **Issuer (`iss`)** | Token đến từ đúng nhà phát hành được tin cậy |
| **Expiration (`exp`)** | Token còn thời hạn |
| **Not before (`nbf`)** | Token không được dùng trước thời điểm có hiệu lực |
| **Audience (`aud`)** | Token được phát hành cho API/hệ thống cần bảo vệ |
| **Scope/authority** | Caller được phép thực hiện loại thao tác nào |
| **Subject/tenant** | Danh tính và ranh giới dữ liệu cho kiểm tra nghiệp vụ |

**Lưu ý:** Cấu hình `issuer-uri` trong Spring Security thường giúp xác minh issuer, chữ ký và một số timestamp qua decoder mặc định, nhưng **không nên mặc định audience sẽ luôn được kiểm tra đúng theo API của bạn**. Hãy cấu hình validator audience hoặc chính sách tương ứng theo phiên bản Security/Boot đang dùng. Đây là một yêu cầu bảo mật thiết kế, không phải phần tùy chọn cho những API có nhiều audience.

JWT hợp lệ **không đồng nghĩa** quyền admin hợp lệ. Một JWT cho phép người dùng xem sản phẩm không được tự động cấp quyền quản trị chỉ vì caller biết URL `/api/admin/**`.

### JWT scope khác role trong Identity Provider

Ví dụ policy dùng:

~~~java
.pathMatchers("/api/admin/**")
    .hasAuthority("SCOPE_admin")
~~~

Khi IdP cấp access token có `scope: "admin"` và converter của Spring Security ánh xạ nó thành `SCOPE_admin`, rule có thể cho qua. Nhưng nếu IdP chỉ dùng claim `roles: ["ADMIN"]` hoặc `realm_access.roles` theo định dạng riêng, **phải viết/cấu hình authority converter phù hợp**. Không giả định `hasRole("ADMIN")` luôn nhận được claim role tùy ý trong token.

**Nguyên tắc least privilege:** Một token hoặc role quá rộng (ví dụ `admin` cho mọi thao tác) làm tăng tác động khi lộ token. Với hệ thống lớn, có thể chia scope cụ thể như `catalog.write`, `reports.read` hoặc `users.manage`, rồi dùng method/path policy và kiểm tra nghiệp vụ tương ứng.

## 7. SecurityWebFilterChain chạy ở đâu so với route và GatewayFilter?

Đây là điểm thường gây nhầm lẫn khi thiết kế bảo mật cho Gateway:

~~~mermaid
flowchart TD
    C[HTTP request] --> W[WebFlux WebFilter chain]
    W --> S[Spring Security: authentication / authorization]
    S --> Q{Request được phép?}
    Q -->|Không| D[401 hoặc 403, không proxy]
    Q -->|Có| M[RoutePredicateHandlerMapping]
    M --> P{Route predicate khớp?}
    P -->|Không| NF[Không có route Gateway phù hợp]
    P -->|Có| F[FilteringWebHandler]
    F --> GF[Gateway GlobalFilter + route GatewayFilter]
    GF --> U[Upstream service hoặc local forward]
    U --> R[HTTP response về client]
~~~

Sơ đồ trên trình bày **một cách nhìn logic** trong WebFlux: **Spring Security WebFilter** hoạt động ở lớp WebFlux, còn `GlobalFilter` và `GatewayFilter` được thực hiện trong pipeline của Gateway **sau khi route được chọn**. Một GlobalFilter **không tự bảo vệ mọi controller hoặc request không có route**, trong khi SecurityWebFilterChain có thể bao phủ các request thuộc ứng dụng theo matcher của nó.

### Vì sao không chỉ dùng GatewayFilter để kiểm tra admin?

Giả sử bạn viết GatewayFilter cho route `administration` để kiểm tra JWT. Các điểm yếu có thể xuất hiện:

1. Một route khác hoặc route động vô tình đưa request đến cùng backend admin nhưng **không gắn filter đó**.
2. Một endpoint WebFlux cục bộ hoặc actuator không qua route admin, nên **GatewayFilter không chạy**.
3. Một `Path` predicate có điều kiện khác, còn một route fallback chồng lấn lại cho request đi theo đường ít bảo vệ.
4. Logic tùy chỉnh tự xác thực header nhưng thiếu kiểm tra chữ ký, issuer, audience hoặc expiry.

Do đó, **Spring Security WebFlux** thích hợp để đặt chính sách authentication/authorization nền tảng. GatewayFilter vẫn hữu ích cho rate limiting, header transformation, tracing hoặc bước bảo vệ bổ sung trong phạm vi rõ ràng; không nên để nó là lớp quyền duy nhất cho toàn ứng dụng.

### Route predicate và security matcher không nhất thiết có cùng ngữ nghĩa

`Path=/api/admin/**` thuộc **Gateway route predicate**; `pathMatchers("/api/admin/**")` thuộc **Spring Security WebFlux**. Hai công cụ đều nhìn đường dẫn request nhưng có thể có khác biệt về parser, trailing slash, cách xử lý path parameter hoặc percent-encoding tùy version. Vì vậy hãy kiểm thử các đường dẫn biên, đặc biệt khi có:

- `/api/admin` và `/api/admin/`.
- `/api/admin/users` và `/api/adminusers`.
- Slash trùng như `/api/admin//users`.
- Encoded slash `%2F`, dot segment `..`, double encoding `%252F`.
- Path đã bị ingress rewrite trước khi request đến Gateway.

**Không dùng một cách normalize path cho security và một cách khác cho routing** mà không kiểm chứng. Một tầng thấy path là public nhưng tầng kia giải mã thành đường dẫn admin có thể tạo lỗ hổng vượt qua quyền.

### RewritePath chạy sau quyết định bảo mật theo path đầu vào

Ví dụ route `Path=/api/admin/**` có filter `StripPrefix=2`, làm backend nhận `/users/42`. Spring Security ở Gateway đánh giá đường dẫn **công khai khi request vào Gateway**, không nên chờ path đã được StripPrefix. Service backend phải áp chính sách của chính service lên đường dẫn `/users/42` và danh tính được truyền theo cơ chế tin cậy.

## 8. Mã 401, 403 và 404: đừng nhầm nguyên nhân

HTTP status của lỗi bảo mật phải phù hợp với từng quyết định.

| Tình huống | Kết quả bảo mật thường gặp | Ý nghĩa |
| --- | --- | --- |
| Anonymous vào `/api/account/profile` | **401 Unauthorized** | Chưa có bằng chứng xác thực hợp lệ |
| Bearer token sai chữ ký/hết hạn | **401 Unauthorized** | Token không hợp lệ để xác thực |
| User có token hợp lệ nhưng không có `SCOPE_admin` vào admin API | **403 Forbidden** | Đã xác thực nhưng không đủ quyền |
| Admin có authority hợp lệ vào API admin | Được **đi tiếp** | Chưa bảo đảm service trả 200; nghiệp vụ có thể từ chối |
| Không có route nào khớp nhưng security cho phép | Có thể **404** hoặc kết quả khác theo handler | Lỗi định tuyến/tài nguyên, không phải lỗi authentication |
| `anyExchange().denyAll()` chặn URL lạ | Bị từ chối ở lớp security | Mã cuối có thể phụ thuộc authentication/entry point |

Một lỗi thường thấy là trả **403** cho mọi trường hợp chưa có token, hoặc trả **401** dù người dùng đã xác thực nhưng thiếu role. Sự nhầm lẫn này khiến client không biết nên đăng nhập lại hay hiển thị “không có quyền”.

### Ví dụ 401 với Bearer challenge

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Cache-Control: no-store
~~~

Khi dùng OAuth2 Resource Server, **WWW-Authenticate** là một phần quan trọng của challenge. Có thể có thêm thông tin lỗi theo giao thức; không ghi token thật, stack trace hoặc dữ liệu nội bộ vào response. Đối với 403, payload JSON có thể chỉ nói “không đủ quyền”; không cần công khai danh sách quyền nội bộ chi tiết.

**Đừng tự đổi status bằng `SetStatus` để “biến” 403 thành 200.** Client có thể nhận HTTP 200 cùng body lỗi và hiểu sai nghiệp vụ. Việc quyết định authentication failure và access denied nên do Spring Security hoặc error handler được thiết kế đồng bộ status, headers và body đảm nhiệm.

### Khi public route nhận Bearer token sai thì sao?

`permitAll()` không có nghĩa các authentication filter phải bỏ qua mọi credential đã được trình bày. Tùy cấu hình, nếu client gửi một **Bearer token không hợp lệ** đến endpoint public, resource-server authentication filter có thể trả 401 trước khi tới rule `permitAll()`. Hãy kiểm thử cả request **không có Authorization** và request **có Authorization nhưng hỏng**; đừng ngầm cam kết hai trường hợp luôn giống nhau.

## 9. Public login, token issuance và chống lạm dụng

Ở ví dụ route `POST /auth/login`, Gateway để anonymous gọi **Identity service**. Điều này **không đồng nghĩa** Gateway tự kiểm tra mật khẩu hoặc cấp JWT.

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway as Spring Cloud Gateway
    participant IdP as Identity/Authorization Service
    participant API as Account service
    Client->>Gateway: POST /auth/login (credentials)
    Gateway->>Gateway: Public auth endpoint + rate limit
    Gateway->>IdP: Forward request
    IdP-->>Gateway: Access token (if valid)
    Gateway-->>Client: Token response over HTTPS
    Client->>Gateway: GET /api/account/profile + Bearer token
    Gateway->>Gateway: Validate token + authenticated
    Gateway->>API: Forward allowed request
    API-->>Client: Profile via Gateway
~~~

**Ví dụ minh họa** này sử dụng một login API riêng cho dễ học. Một hệ thống production có thể dùng chuẩn **OAuth2 Authorization Code + PKCE**, OpenID Connect và một Authorization Server chuyên trách, thay vì tự thiết kế endpoint xử lý username/password. Chọn flow phụ thuộc loại client, nhu cầu SSO và chính sách tổ chức.

Endpoint public xử lý đăng nhập cần bảo vệ:

- **TLS bắt buộc** để tránh gửi mật khẩu hoặc token dưới dạng rõ.
- **Rate limiting theo nguồn hợp lý** và chống brute force/credential stuffing; không chỉ dựa vào IP nếu có reverse proxy hoặc nhiều user dùng chung IP.
- **Phản hồi lỗi không tiết lộ** tài khoản tồn tại hay không, trạng thái mật khẩu và dữ liệu bí mật.
- **Giới hạn kích thước request/body**, chống lạm dụng, nhật ký an toàn và giám sát bất thường.
- **Không cache token response** tùy tiện; áp cache policy đúng contract.
- **Không log Authorization, password, refresh token**, cookie hoặc phần body chứa credentials.
- **Không tự công bố** các endpoint quản trị của Identity service chỉ vì một route dùng `Path=/auth/**` quá rộng. Chỉ expose những endpoint public đã được thiết kế.

Nếu hỗ trợ tự đăng ký `POST /auth/register`, phải bổ sung **cả route lẫn rule permitAll riêng**, kèm xác minh chống abuse. Tránh đặt `/auth/**` thành public rồi vô tình để lộ endpoint cấp/quản lý token hoặc chức năng nội bộ.

## 10. Tuyến cần đăng nhập: authentication không bằng quyền tài nguyên

Lấy ví dụ:

~~~http
GET /api/account/orders/O-42 HTTP/1.1
Authorization: Bearer eyJ...<redacted>...
~~~

Gateway có thể xác minh JWT và chấp nhận vì `authenticated()`. Tuy nhiên, câu hỏi quan trọng ở Orders/Account service là: **`O-42` có thuộc người dùng đang đăng nhập không?**

Một user bình thường có token hợp lệ **không được xem tài nguyên của user khác**. Gateway chỉ có thể thực hiện một phần kiểm tra dựa vào URI, token hoặc metadata có sẵn; thông thường nó không biết toàn bộ quan hệ quyền sở hữu dữ liệu và thay đổi nghiệp vụ của service.

### Các lớp cần phối hợp

1. **Gateway:** kiểm tra access token phù hợp, chặn anonymous trên các route private, áp rate limiting và lọc input cơ bản.
2. **Backend:** xác minh caller/identity từ nguồn đáng tin, kiểm tra quyền tài nguyên cụ thể, tenant boundary và chính sách nghiệp vụ.
3. **Dữ liệu:** truy vấn phải giới hạn theo subject/tenant hoặc ràng buộc sở hữu; không chỉ đọc record theo ID rồi trả về.
4. **Audit:** ghi subject, loại hành động và kết quả ở mức an toàn mà không làm lộ token hoặc dữ liệu cá nhân nhạy cảm.

Ví dụ policy `authenticated()` là mức tối thiểu của nhóm này. Khi API có nhiều loại thao tác, nên áp thêm authority/permission cụ thể: `account.read`, `orders.write`, quyền với từng đối tượng hoặc scope có nghĩa tương đương trong hệ thống.

### Tránh tin X-User-Id tự khai

Không sử dụng một header do client gửi như `X-User-Id: user-742` làm bằng chứng người gọi đã xác thực. Nếu kiến trúc yêu cầu truyền identity xuống backend, phải lấy từ **authentication đã được xác minh** và bảo vệ hop backend, loại bỏ header cùng tên do client có thể giả mạo. Tốt hơn, backend có thể tự xác minh token hoặc token nội bộ giới hạn audience/scope.

## 11. Tuyến quản trị: bảo vệ sâu hơn một rule hasAuthority

Một API admin có thể cho phép thay đổi giá sản phẩm, cấp quyền nhân viên, đọc báo cáo hoặc vận hành hệ thống. Vì tác động lớn, cần đặt tiêu chuẩn bảo vệ cao hơn tuyến chỉ yêu cầu đăng nhập.

**Các lớp phòng vệ phù hợp:**

| Lớp | Ví dụ |
| --- | --- |
| Authentication mạnh | Token từ IdP đáng tin, MFA/step-up khi cần |
| Authorization | Scope/authority riêng cho admin và quyền cụ thể theo hành động |
| Mạng | Admin hostname/VPN/Zero Trust gateway hoặc allowlist nếu phù hợp, không thay thế token |
| Backend | Kiểm tra lại quyền thực hiện nghiệp vụ và quyền đối với tài nguyên |
| Audit | Ghi nhận ai làm gì, khi nào, kết quả; bảo vệ tính toàn vẹn của log |
| Chống lạm dụng | Rate limiting, kiểm soát tự động hóa và cảnh báo bất thường |
| Session/token | Thời hạn, thu hồi, audience, rotation và chính sách thiết bị phù hợp |
| Thay đổi nguy hiểm | Phân quyền tách nhiệm vụ, xác nhận hoặc phê duyệt nếu quy trình yêu cầu |

Nếu hệ thống dùng role `ROLE_ADMIN` thay cho scope, rule có thể dùng `hasRole("ADMIN")` **chỉ khi** authentication thực sự chứa authority `ROLE_ADMIN` (theo mặc định prefix `ROLE_`). Cách mapping giữa IdP roles và Spring Security authorities phải được định nghĩa và kiểm thử. Đừng nhận role trực tiếp từ JSON body hoặc request header.

### Admin hostname không thay thế kiểm tra quyền

Ví dụ một route có predicate `Host=admin.example.test`. Header Host có thể được client kiểm soát trong nhiều bối cảnh; DNS hay việc tách host không chứng minh caller là admin. Nếu sử dụng admin host, vẫn phải yêu cầu token/authority, bảo vệ TLS và kiểm soát ingress/virtual host. Đồng thời phải đảm bảo không có route khác expose cùng backend admin từ public host.

### Đừng xem quyền admin là quyền với management plane

Quản trị nghiệp vụ như `/api/admin/products` khác với **Spring Boot Actuator**, cấu hình hạ tầng, refresh route, metrics, environment hay heap dump. Ngay cả một user có `SCOPE_admin` cho nghiệp vụ cũng không mặc nhiên được xem secrets hoặc sửa runtime của Gateway. Management plane cần bảo vệ riêng, thường tách port/mạng/quyền và hạn chế endpoint được expose.

## 12. Token được chuyển xuống backend như thế nào?

Xác thực ở Gateway rồi proxy request không tự giải quyết câu hỏi **upstream tin danh tính bằng cách nào**.

### Mô hình A — Chuyển tiếp Bearer token và backend tự xác minh

Client gửi:

~~~http
Authorization: Bearer <access-token>
~~~

Gateway xác thực token; nếu request được phép, route có thể chuyển header Authorization tới backend theo chính sách proxy/filter của hệ thống. Backend cũng là resource server và **xác minh lại** token, audience, issuer và quyền tài nguyên. Đây là mô hình rõ ràng về ranh giới tin cậy, nhưng phải bảo đảm token có audience/scope phù hợp cho service nhận. Không nên dùng một token có quyền rộng ở mọi service chỉ vì dễ chuyển tiếp.

### Mô hình B — Gateway trao đổi token hoặc phát tín hiệu identity nội bộ

Trong một số kiến trúc, Gateway có thể thực hiện **token exchange/on-behalf-of** hoặc cung cấp một token nội bộ có audience và scope hạn chế. Backend xác minh token nội bộ từ một issuer đáng tin. Mô hình này đòi hỏi bảo vệ khóa ký, giới hạn TTL, cơ chế ủy quyền và định danh giữa các service.

Nếu dùng header chứa identity nội bộ thay token, phải ngăn spoofing bằng cách xóa header từ phía client, chỉ nhận traffic qua proxy tin cậy, bảo vệ kênh (ví dụ mTLS) và có cơ chế xác thực tính toàn vẹn của thông tin nếu thiết kế cần. Header thêm vào đơn thuần không có chữ ký hoặc ranh giới mạng phù hợp **không tạo ra danh tính đáng tin**.

### TokenRelay không phải công tắc “bật bảo mật”

Spring Cloud Gateway có **TokenRelay GatewayFilter Factory** trong một số cấu hình OAuth2 Client để chuyển access token của authorized client xuống upstream. Nó khác với việc **Gateway Resource Server xác minh một Bearer JWT có sẵn**. Không mặc định cứ thêm `TokenRelay` vào route là có authentication/authorization đúng hoặc backend được bảo vệ. Cần dependency OAuth2 Client, authorized-client context và chính sách truyền token phù hợp; đồng thời phải kiểm tra audience và giới hạn scope.

### Ranh giới TLS và discovery

Gateway → backend là một kết nối riêng với client → Gateway. Dù public endpoint dùng HTTPS, Gateway có thể dùng HTTP tới ServiceInstance nếu cấu hình như vậy; phải cân nhắc TLS/mTLS, truststore, network policy và tính bảo mật của token trên hop nội bộ. **Discovery metadata hoặc `ServiceInstance.isSecure()` không thay thế xác minh chứng chỉ**, và không cho phép client chọn tùy ý service ID nội bộ.

## 13. CORS và CSRF: hai vấn đề khác với quyền route

Đối với ứng dụng web chạy ở `https://shop.example.test` gọi API ở `https://api.example.test`, browser áp dụng **CORS**. Khi frontend gửi Authorization header hoặc JSON request, browser có thể gửi một **preflight OPTIONS** trước request chính.

Ví dụ:

~~~http
OPTIONS /api/account/profile HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight là một câu hỏi kiểm tra chính sách cross-origin, **không phải request GET lấy hồ sơ**. Nó thường không mang Bearer token. Nếu Spring Security cố yêu cầu authentication của route private **trước khi CORS được xử lý**, browser có thể nhận 401/403 cho OPTIONS và chặn luôn request chính.

**Cách xử lý:** cấu hình CORS ở lớp phù hợp để preflight hợp lệ được xử lý trước bước auth/authorization cần thiết, đồng thời đảm bảo request GET/POST thực tế vẫn phải qua security. Không đơn giản dùng `.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` rồi cho rằng CORS đã đúng; permitAll không tự tạo `Access-Control-Allow-Origin` hoặc kiểm tra danh sách origin.

### Ví dụ một CorsConfigurationSource cho WebFlux

Trong cùng ứng dụng Security WebFlux, có thể xây nguồn cấu hình CORS:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://shop.example.test"));
    cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    cors.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", cors);
    return source;
}
~~~

Đây là **phương thức bean minh họa**, cần đặt trong class `@Configuration` và liên kết đúng vào cấu hình `ServerHttpSecurity.cors(...)` hoặc cơ chế CORS reactive tương ứng với bản Spring Security. Chẳng hạn trong `SecurityWebFilterChain`, có thể sử dụng `.cors(cors -> cors.configurationSource(corsConfigurationSource()))` khi API phiên bản hỗ trợ. Không copy toàn bộ vào một class không có import/cấu hình phù hợp rồi cho rằng CORS tự được bật.

**Lưu ý:**

- `allowCredentials(false)` là lựa chọn minh họa cho API Bearer token không phụ thuộc cookie. Nếu thực sự dùng browser cookie/session, chính sách credentials, SameSite, CSRF và origin phải được thiết kế lại.
- Không dùng `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true`.
- Không để Gateway và upstream đồng thời trả header CORS trùng/xung đột. Chọn một nguồn sở hữu chính sách hoặc dùng khả năng dedupe có kiểm soát.
- Với CORS theo Origin, cần để ý `Vary: Origin` và hành vi cache phù hợp.
- Một preflight hợp lệ được cho qua **không cấp quyền** cho GET/POST chính; request chính vẫn phải có token và scope phù hợp.
- Một số cấu hình Gateway sử dụng global CORS handler khi OPTIONS không khớp route có `Method=GET`; hãy kiểm tra cả trường hợp route predicate không match OPTIONS.

### CSRF không phải CORS

**CORS** là cơ chế browser quyết định một trang khác origin có được đọc response và gửi một số request cross-origin theo chính sách server hay không. **CSRF** liên quan request có thể mang credential tự động (thường cookie/session) khiến browser thực hiện hành động không được người dùng dự định.

Vì vậy:

- API stateless dùng **Bearer token được client gắn chủ động trong Authorization header** có mô hình CSRF khác ứng dụng login qua cookie; ví dụ ở phần 5 tắt CSRF **chỉ trong bối cảnh này**.
- Nếu client dùng session cookie, refresh-token cookie hoặc cơ chế browser tự đính kèm credential, cần phân tích CSRF và bảo vệ tương ứng; không tắt CSRF chỉ vì “đã có JWT ở đâu đó”.
- CORS không thể thay thế authentication/authorization. Client ngoài browser (curl, mobile app, service-to-service) không bị hạn chế như browser CORS nhưng vẫn phải bị Spring Security kiểm tra.

## 14. Thứ tự nhiều SecurityWebFilterChain và route chồng lấn

Đối với một ứng dụng Gateway nhỏ, một `SecurityWebFilterChain` với `anyExchange().denyAll()` ở cuối thường dễ kiểm soát. Ứng dụng lớn có thể chia thành nhiều security chain theo `securityMatcher` và `@Order`, ví dụ một chain cho admin, một chain cho API công khai.

**Nguyên tắc quan trọng:** Trong Spring Security, **chain đầu tiên có matcher phù hợp** được chọn cho request; không mặc định có nhiều chain cộng dồn chính sách theo kiểu “chain public rồi chain admin”. Nếu thứ tự chain hoặc matcher sai, một request có thể rơi vào chain ít hạn chế hơn hoặc không có chain nào bảo vệ.

Ví dụ về tư duy thứ tự:

~~~text
Ưu tiên 1: các đường dẫn admin    -> authenticate + admin authority
Ưu tiên 2: các đường dẫn account  -> authenticate
Ưu tiên 3: các đường dẫn public   -> permitAll
Mặc định: từ chối
~~~

Không nên tách thành nhiều chain nếu chưa có nhu cầu rõ ràng; một chain duy nhất như phần 5 giúp người mới thấy chính sách tổng thể và tránh bỏ quên matcher.

### Route order khác security rule order

Spring Cloud Gateway có `order` để chọn route khi nhiều route predicates cùng khớp. Spring Security có thứ tự matcher và thứ tự chọn `SecurityWebFilterChain`. **Đó là các lớp ưu tiên khác nhau.**

| Ưu tiên | Kiểm soát điều gì? |
| --- | --- |
| `SecurityWebFilterChain` và security matcher | Request có được phép đi vào ứng dụng không? |
| `authorizeExchange` matcher | Quy tắc authorization nào được áp dụng? |
| Gateway route `order` | Route nào được chọn khi nhiều predicate cùng khớp? |
| Gateway filter order | Filter nào chạy trước/sau trong route được chọn? |

Một route catch-all như `Path=/**` có thể khiến request vào một backend không mong đợi. Nếu chính sách security tương ứng chỉ dùng matcher `/api/account/**` và để các URL còn lại public, endpoint mới có thể vô tình bị lộ. **Deny-by-default** ở WebFlux, cùng việc giới hạn danh sách route và kiểm tra route order, giúp hạn chế nguy cơ này.

### DiscoveryClient Route Definition Locator và auto-exposure

Nếu bật tính năng **tự sinh route từ service discovery**, Gateway có thể có thêm route ngoài những route YAML bạn trực tiếp đọc. Điều này **không tự cấp quyền truy cập**, nhưng có thể tạo những đường dẫn không được xét tới trong ma trận bảo mật. Với Gateway công khai, nên hạn chế service được expose và áp policy mặc định từ chối những URL không được phê duyệt.

### Endpoint nội bộ và fallback

Một route có CircuitBreaker fallback sử dụng `fallbackUri: forward:/internal/fallback` có thể gọi một handler nội bộ trong cùng ứng dụng. **Không mặc định rằng WebFilter security sẽ được chạy lại trên mỗi forward nội bộ theo cùng cách một HTTP request mới đi vào Gateway**. Hãy bảo vệ đường vào gốc, không expose bừa bãi handler fallback, và tránh để handler phản hồi dữ liệu nhạy cảm chỉ vì nhận một request nội bộ.

## 15. Ma trận kiểm thử anonymous, user và admin

Tạo ba nhóm credential trong **môi trường kiểm thử**:

- **Anonymous:** không gửi header Authorization.
- **User:** access token hợp lệ, đúng issuer/audience nhưng **không có** authority `SCOPE_admin`.
- **Admin:** access token hợp lệ, đúng issuer/audience và có authority `SCOPE_admin`.

Thêm các trường hợp **token hết hạn**, **token sai chữ ký**, **token sai audience** và **token có role claim nhưng chưa được map thành authority**.

Giả sử backend, discovery, issuer JWT và cấu hình security đã chạy đúng, kỳ vọng ở **lớp bảo mật Gateway**:

| Request | Anonymous | User hợp lệ | Admin hợp lệ |
| --- | --- | --- | --- |
| `GET /api/public/products/42` | Được đi tiếp | Được đi tiếp | Được đi tiếp |
| `POST /auth/login` | Được đi tiếp | Được đi tiếp nếu không có policy khác | Được đi tiếp nếu không có policy khác |
| `GET /api/account/profile` | **401** | Được đi tiếp | Được đi tiếp theo rule `authenticated` |
| `PATCH /api/account/profile` | **401** | Được đi tiếp | Được đi tiếp theo rule `authenticated` |
| `GET /api/admin/reports` | **401** | **403** | Được đi tiếp |
| `DELETE /api/admin/products/42` | **401** | **403** | Được đi tiếp |
| `GET /api/unknown` | Bị từ chối | Bị từ chối | Bị từ chối |

“**Được đi tiếp**” chỉ có nghĩa security không chặn; backend vẫn có thể trả 400, 404, 403, 429, 500 hoặc status khác theo contract. Ví dụ một admin có token hợp lệ chưa chắc có quyền xóa mọi sản phẩm nếu service áp quyền theo tổ chức/tenant.

### Dùng curl để thử đường đi

~~~bash
# Public endpoint, không cần token:
curl -i 'http://localhost:8080/api/public/products/42'

# Private endpoint, không có token: kỳ vọng 401:
curl -i 'http://localhost:8080/api/account/profile'

# User token hợp lệ trên private endpoint:
curl -i -H "Authorization: Bearer ${USER_TOKEN}" \
  'http://localhost:8080/api/account/profile'

# User không có authority admin: kỳ vọng 403:
curl -i -H "Authorization: Bearer ${USER_TOKEN}" \
  'http://localhost:8080/api/admin/reports'

# Admin token hợp lệ: đi tới admin service:
curl -i -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  'http://localhost:8080/api/admin/reports'
~~~

`USER_TOKEN` và `ADMIN_TOKEN` là **biến môi trường do người kiểm thử thiết lập**, không phải token được cung cấp bởi bài. Không đưa token thật vào file cấu hình, shell history chia sẻ, ảnh chụp màn hình hoặc log công khai. Với hệ thống có TLS, thay URL `http://localhost` bằng endpoint **HTTPS** thực và không gửi token qua mạng không được bảo vệ.

### Những test biên nên có

1. Anonymous gửi GET đến admin path không có slash cuối `/api/admin`.
2. User gửi `X-Role: admin` nhưng không có scope admin; vẫn phải bị từ chối.
3. User gửi JWT có `roles: ["ADMIN"]` nhưng authority converter chưa map thành `SCOPE_admin`; kiểm tra không bị cấp quyền ngoài ý muốn.
4. JWT sai issuer, sai audience hoặc đã hết hạn; phải bị chặn trước backend.
5. URL có double slash, encoded slash, trailing slash hoặc path do ingress rewrite.
6. OPTIONS preflight trước request cần authentication; kiểm tra CORS và sau đó kiểm tra request chính.
7. Backend admin được gọi **trực tiếp qua mạng** thay vì qua Gateway; phải có bảo vệ mạng/authorization phù hợp.
8. Kiểm tra route mới thêm không tự trở thành public.

**Không chỉ xem HTTP 200:** test cần chứng minh backend nào nhận request, liệu request bị chặn có thật sự **không tới upstream**, và phản hồi bảo mật có status/header/body nhất quán.

## 16. Kiểm thử bằng WebTestClient và backend stub

Trong ứng dụng WebFlux, có thể dùng `WebTestClient` để gọi Gateway thực hoặc môi trường test được bind phù hợp. Ví dụ một test tích hợp minh họa kiểm tra anonymous:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

class GatewaySecurityHttpTest {

    private final WebTestClient client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:8080")
            .build();

    @Test
    void anonymousCannotReadPrivateProfile() {
        client.get()
                .uri("/api/account/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void anonymousCannotCallAdminApi() {
        client.delete()
                .uri("/api/admin/products/42")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

Đây là đoạn **test minh họa**, không phải test có thể chạy độc lập ngay: phải có Spring test/JUnit dependency, một Gateway đang nghe tại 8080, security config, và cấu hình test đúng. Đối với test end-to-end, dùng **backend stub/spy** để ghi nhận request nào tới Catalog/Account/Admin. Test nên khẳng định các request bị chặn **không tới** backend, đồng thời token hợp lệ với scope đúng thực sự qua được lớp Gateway.

### Mock JWT trong integration test

Khi test Spring Security WebFlux ở mức ứng dụng, thư viện `spring-security-test` cung cấp công cụ như `mockJwt()` (nếu dùng cấu hình mock phù hợp) để tạo authentication/authorities cho test. Điều đó giúp kiểm tra **authorization rules** mà không cần IdP thật.

Tuy nhiên, **mockJwt không chứng minh quá trình xác thực chữ ký, issuer, audience hoặc luân chuyển JWKS thực**. Cần một nhóm integration test khác với JWT được ký bởi key thử nghiệm hợp lệ và decoder thực, hoặc môi trường IdP kiểm thử, để xác minh đường đi của token xấu/hết hạn và cấu hình trust.

### Kiểm thử quyền sở hữu tài nguyên

Một test chỉ gửi admin scope chưa đủ cho backend. Hãy chuẩn bị hai user A và B, một đơn hàng thuộc A; xác minh:

- A xem được đơn hàng của A khi đủ quyền.
- B bị từ chối với đơn hàng của A dù token B hợp lệ.
- Admin có thể/không thể xem đơn hàng đó **theo đúng policy cụ thể**, không mặc định admin có toàn quyền.
- Không endpoint nào lấy subject từ header do client tự đặt thay vì authentication được xác minh.

## 17. Chẩn đoán các lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Anonymous gọi admin được 200 | Rule `permitAll` hoặc `authenticated` quá rộng, chain order sai, route bypass | Rà `SecurityWebFilterChain`, matcher và backend/network |
| User bình thường vào admin thành công | `/api/**` match trước admin hoặc authority mapping quá rộng | Đặt admin rule trước; kiểm tra `Authentication.getAuthorities()` trong test an toàn |
| Admin token hợp lệ bị 403 | JWT có role claim nhưng không được map sang `SCOPE_admin` | Đồng bộ IdP claims, converter và policy |
| Token hợp lệ bị 401 | Sai issuer, audience, chữ ký, hết hạn, clock skew hoặc JWKS không phù hợp | Kiểm tra JWT validator, trust và lỗi auth an toàn |
| Public endpoint bị 401 khi gửi token hỏng | Bearer authentication filter xử lý credential không hợp lệ | Test riêng trường hợp có/không có Authorization |
| Browser báo lỗi CORS nhưng curl được | Preflight không được xử lý, Origin/header không được cho phép hoặc CORS trùng | Kiểm tra OPTIONS, header CORS và trách nhiệm Gateway/upstream |
| Login POST bị 403 | CSRF/session policy sai hoặc route/security matcher không khớp | Xác định dùng cookie hay Bearer, kiểm tra CSRF và method |
| API trả 404 dù security cho phép | Route không khớp hoặc backend trả 404 | Xem route ID và response backend |
| Client thêm `X-Role: admin` vào được tuyến | Dùng request header tự khai làm bằng chứng quyền | Dùng token đã xác minh và authority đáng tin |
| Path `/api/admin` khác `/api/admin/` | Base path chưa được bao phủ hoặc parser khác nhau | Match exact path và descendants, kiểm thử |
| Route fallback làm lộ dữ liệu nội bộ | Handler `forward:` không được bảo vệ đúng điểm vào | Bảo vệ route gốc và handler nội bộ, không rely vào forward tự chạy lại security |
| Access token bị chuyển sai service | TokenRelay/Authorization forwarding không phù hợp audience | Áp policy token, token exchange hoặc backend validation |
| Admin API bị gọi trực tiếp qua IP nội bộ | Backend thiếu mạng bảo vệ/authorization | Phân vùng mạng, TLS/mTLS và phân quyền tại service |
| Endpoint mới vô tình public | Rule broad permit hoặc route auto-discovery không kiểm soát | `anyExchange().denyAll()` và review route |
| Response 403 bị đổi thành 200 | Dùng SetStatus hoặc fallback sai | Bảo toàn ngữ nghĩa status, body và bảo mật |

### Quy trình điều tra đúng thứ tự

1. **Request vào đâu?** Xem scheme, Host, path, method và ingress có sửa URI không.
2. **Chain nào được chọn?** Xác minh `SecurityWebFilterChain` và security matcher.
3. **Auth có thành công?** JWT decoder chấp nhận chữ ký/issuer/audience/expiration chưa?
4. **Authorities là gì?** Token đã map thành `SCOPE_admin` hoặc authority mong đợi chưa?
5. **Authorize rule nào thắng?** Có một matcher rộng đứng trước matcher admin không?
6. **Route Gateway nào được chọn?** Path/Method/Host predicates có khớp như dự kiến không?
7. **Backend nhận gì?** Token/claims/path/header đã truyền qua ranh giới tin cậy thế nào?
8. **Nghiệp vụ có từ chối?** Kiểm tra quyền sở hữu tài nguyên và policy tại service.
9. **Bảo vệ phụ trợ?** CORS, CSRF, rate limiter, circuit breaker, retry hoặc forward handler có ảnh hưởng không?

Không cần bật log chi tiết Authorization header hay JWT payload của mọi request để điều tra. Có thể log **route ID, loại lỗi, status, tên authority đã được chuẩn hóa và trace ID an toàn** ở mức truy cập phù hợp; không ghi access token, cookie hoặc credentials.

## 18. Bài thực hành tổng hợp: thiết kế gateway cho ba mức truy cập

**Bối cảnh:** Một nền tảng quản lý cửa hàng có Catalog, Account và Admin service. Gateway chịu trách nhiệm route predicate, kết nối tới service discovery, quản lý filter chain và kiểm soát truy cập ở lớp biên. Backend vẫn kiểm tra quyền nghiệp vụ.

### Phần A — Thiết kế hợp đồng

1. Liệt kê ít nhất hai public endpoint, hai authenticated endpoint và hai admin endpoint.
2. Với từng endpoint, ghi rõ method, path, người được phép, loại dữ liệu, service đích và yêu cầu về cache/audit.
3. Tách `POST /auth/login` thành route công khai **chỉ cho đúng method/path**; không cho phép toàn bộ `/auth/**` không có lý do.
4. Chọn authority admin phù hợp với issuer thực tế. Nếu dùng scope `admin`, xác minh nó xuất hiện trong `Authentication` dưới dạng `SCOPE_admin`.

### Phần B — Triển khai

1. Khai báo bốn route tương đương phần 4 bằng `lb://` hoặc URI backend cục bộ.
2. Thêm `SecurityWebFilterChain` tương tự phần 5; đặt quy tắc admin trước private/public và cuối cùng là `anyExchange().denyAll()`.
3. Cấu hình OAuth2 Resource Server với issuer tin cậy và audience validator phù hợp.
4. Cấu hình CORS cho frontend có Origin được cho phép; test preflight trước request có Authorization.
5. Thêm rate limiter bảo vệ login/public endpoint, log/audit hành động admin ở mức an toàn.
6. Đảm bảo backend không được gọi trực tiếp từ vùng mạng không có bảo vệ.

### Phần C — Kiểm thử bắt buộc

| Bài kiểm thử | Kết quả mong đợi |
| --- | --- |
| Anonymous GET public | Được chuyển đến Catalog nếu route/backend hợp lệ |
| Anonymous GET account | 401 ở lớp security |
| Anonymous DELETE admin | 401 ở lớp security |
| User GET account | Qua gateway; backend tiếp tục kiểm tra quyền tài nguyên |
| User DELETE admin | 403 và **không tới Admin service** |
| Admin DELETE admin | Qua security; backend xét chính sách nghiệp vụ |
| Token sai chữ ký/issuer/audience | Không được cho phép truy cập tài nguyên private/admin |
| Header `X-Role: admin` từ user | Không thay đổi quyền thực tế |
| OPTIONS preflight của browser | Được xử lý theo CORS policy; GET/POST chính vẫn cần token phù hợp |
| URL chứa encoded slash/trailing slash | Không có cách biểu diễn đường dẫn nào bypass authorization |
| Route mới không có rule | Bị từ chối theo default policy |
| Truy cập backend trực tiếp | Bị bảo vệ bởi network/backend authorization |

### Phần D — Xem xét sự cố

1. **Lỗi có chủ đích:** Đưa `.pathMatchers("/api/**").permitAll()` lên đầu. Trong môi trường test, quan sát tác động rồi sửa ngay. Không deploy cấu hình cố ý tạo lỗ hổng này.
2. **Sai authority mapping:** Cấp token có claim role nhưng không có authority admin tương ứng, xác minh không tự được vào admin.
3. **Sai route order:** Thêm một route `Path=/**` trong môi trường test để thấy tại sao routing không được thay thế authorization.
4. **TokenRelay và audience:** Thử một backend chỉ chấp nhận token cho đúng audience; xác minh không chuyển bừa token có audience khác.
5. **CORS/session:** Nếu dùng cookie, xác định lại CSRF, SameSite và CORS credentials trước khi cho phép login/đổi dữ liệu.

**Tiêu chí đạt:** Có ma trận quyền được thực thi; anonymous không vào private/admin; user không có admin authority bị 403; admin có quyền hợp lệ đi đúng route nhưng backend vẫn kiểm tra tài nguyên; default deny, preflight CORS và các biến thể path đều được kiểm thử; không log token và không công bố management plane.

## 19. Kiểm soát vận hành và thay đổi về sau

Chính sách security có thể đúng hôm nay nhưng bị phá khi nhóm khác thêm route hoặc đổi API:

- **Review route và policy trong cùng thay đổi:** nếu thêm `/api/admin/reports/export`, phải có chủ sở hữu, auth method, authority và test tương ứng.
- **Quy hoạch URL nhất quán:** tránh tên public/private chồng lấn hoặc những rewrite tạo đường vòng đi tới cùng backend nhạy cảm.
- **Bảo vệ secrets/JWKS/issuer:** kiểm soát key rotation, truststore, token validity, thu hồi/rotation theo quy trình IdP.
- **Giám sát lỗi:** theo dõi 401/403 bất thường, lỗi giải mã token, no-instance, rate-limit response, latency và lỗi upstream **tách biệt**.
- **Audit admin:** ghi nhận principal, thao tác, tài nguyên và kết quả ở nơi bảo vệ truy cập; không ghi token, mật khẩu hoặc dữ liệu cá nhân dư thừa.
- **Defense in depth:** nếu Gateway bị cấu hình sai hoặc một tuyến khác cho tới service nội bộ, backend vẫn kiểm tra quyền và mạng vẫn giới hạn kết nối.
- **Kiểm tra định kỳ CORS, CSRF và đường dẫn:** thay đổi browser client, ingress, redirect hoặc path normalization đều có thể tác động bảo mật.
- **Không đánh đổi bảo mật để sửa lỗi vận hành:** không tắt JWT validation, TLS hostname verification hay mở `permitAll` rộng chỉ vì gặp 401/403.

## 20. Tổng kết

- **Route predicate là để chọn đích; Spring Security là để xác thực và phân quyền.** Không dùng `Header=X-Role, admin` hoặc `Host=admin...` làm bằng chứng quyền.
- Thiết kế rõ ba lớp: **public** dùng `permitAll()` có kiểm soát; **private** yêu cầu `authenticated()`; **admin** đòi thêm authority đáng tin như `SCOPE_admin` khi đã mapping đúng.
- Dùng `SecurityWebFilterChain` cho Gateway Server WebFlux và đặt **quy tắc cụ thể trước quy tắc rộng**; kết thúc bằng `anyExchange().denyAll()` để tránh endpoint mới mặc định public.
- **JWT phải được xác minh đầy đủ**: chữ ký, issuer, thời hạn, audience và quyền phù hợp. Access token hợp lệ không đồng nghĩa caller được làm mọi việc; backend vẫn phải kiểm tra tài nguyên/tenant.
- **401** thường nghĩa là cần authentication hợp lệ; **403** nghĩa là đã xác thực nhưng thiếu quyền. Không đảo lộn status bằng response filter hoặc fallback không phù hợp.
- **CORS preflight, CSRF, token relay, URL rewriting, forwarded headers và route order** tác động đến ranh giới truy cập nhưng không thay thế chính sách security.
- API admin cần **bảo vệ nhiều lớp**: token/role hoặc scope đúng, MFA khi cần, network/TLS/mTLS, backend authorization, rate limit, audit và management plane riêng.
- Chỉ coi thiết kế thành công khi đã kiểm thử **anonymous, user, admin, token xấu, preflight, path biến thể và backend trực tiếp**, đồng thời quan sát request theo route mà không làm lộ credentials.
