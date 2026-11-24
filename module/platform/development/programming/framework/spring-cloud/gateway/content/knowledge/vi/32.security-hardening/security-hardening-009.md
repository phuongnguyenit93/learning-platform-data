# Bảo vệ token, cookie, API key và thông tin xác thực phía sau

**Chương:** Gia cố bảo mật  
**Module:** `SPRING_CLOUD_GATEWAY` — Xây dựng API Gateway bằng Spring Cloud Gateway với route predicates, filter chain, biến đổi path/header, service discovery; xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request.

Spring Cloud Gateway nằm giữa **client không tin cậy** và **các dịch vụ phía sau**. Một sai sót trong cách truyền `Authorization`, `Cookie`, `X-API-Key`, `Set-Cookie` hoặc token OAuth2 có thể biến API Gateway từ lớp kiểm soát truy cập thành đường rò rỉ thông tin xác thực. Ví dụ: một request được người dùng gửi đến `/api/catalog/**` lại mang access token có quyền thanh toán; nếu route chỉ đổi `StripPrefix` rồi chuyển mọi headers nguyên trạng đến service catalog, catalog sẽ nhận một bí mật mà nó không cần và không nên có.

Bảo vệ credentials tại Gateway không phải chỉ **xóa mọi header nhạy cảm**. Một Resource Server phía sau có thể **cần** access token gốc để tự phân quyền; một dịch vụ nội bộ khác cần **service credential riêng**, còn một ứng dụng Backend-for-Frontend (BFF) dùng session cookie tại Gateway nhưng **không** gửi cookie đó cho các backend. Chính sách đúng phụ thuộc **identity, audience, trust boundary, route và mục đích sử dụng**.

Bài này tập trung vào bảo vệ bốn nhóm thông tin: **Bearer token/JWT/OAuth2 token**, **session cookie và Set-Cookie**, **client API key**, và **downstream/service credentials**. Ta sẽ thiết kế ma trận chuyển tiếp, triển khai một Gateway Server WebFlux, áp dụng Spring Security, `RemoveRequestHeader`/`RemoveResponseHeader` và một filter backend-key có kiểm soát; phân tích Cookie/CSRF/CORS, TokenRelay, mTLS, secrets rotation, caches/retries, logs và kiểm thử negative cases. Những khác biệt của Gateway Server Web MVC cũng sẽ được ghi rõ.

> **Phạm vi phiên bản:** Ví dụ YAML chính dùng **Gateway Server WebFlux** với `spring-cloud-starter-gateway-server-webflux` và `spring.cloud.gateway.server.webflux.routes` trong dòng 5.x. Với Gateway 4.x, một số starter/property prefix khác (chẳng hạn `spring.cloud.gateway.routes`). **Gateway Server Web MVC** dùng Servlet/WebMvc.fn, `SecurityFilterChain` và `spring.cloud.gateway.server.webmvc.routes` ở dòng phù hợp; không dán nguyên `GlobalFilter`/`SecurityWebFilterChain` WebFlux sang MVC. Các security defaults, cookies và filter API phải được xác minh theo exact Spring Boot, Spring Cloud và Spring Security BOM.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

1. Phân loại access token, refresh token, ID token, session ID, API key, backend shared secret và mTLS client certificate theo **chủ sở hữu, audience và nơi lưu**.
2. Mô tả **trust boundary** Client → Gateway → downstream và giải thích vì sao xác thực tại Gateway không tự thay phân quyền tại backend.
3. Viết chính sách **per-route/per-service**: credential nào được nhận, kiểm tra, đổi, xóa, hoặc chuyển tiếp.
4. Sử dụng `RemoveRequestHeader`, `SetRequestHeader`, `RemoveResponseHeader`, `SecureHeaders` và `TokenRelay` theo mục đích, không trông chờ default proxy tự cô lập secrets.
5. Cấu hình Spring Security WebFlux Resource Server kiểm tra JWT issuer, expiry, scopes và audience theo nhu cầu.
6. Phân biệt `TokenRelay` (OAuth2 authorized-client flow) với **forward raw Authorization** và **OAuth2 token exchange**.
7. Thiết kế cookie `Secure`/`HttpOnly`/`SameSite`/`Path`/`Domain`, session rotation, CSRF protection và chính sách CORS đúng.
8. Tạo backend API key bằng **provider kiểm soát vòng đời**, không lấy key từ header client và không hardcode vào Java/YAML công khai.
9. Bảo vệ outbound TLS/mTLS, trusted proxies, cache, Retry, CircuitBreaker/fallback, WebSocket handshake và dynamic route management.
10. Kiểm thử **credentials không được chuyển đến backend sai**, không xuất hiện trong logs/traces, không lộ qua cache/redirect/error, với số lần downstream calls được đo rõ.

## 2. Mô hình đe dọa và ranh giới tin cậy

```mermaid
flowchart LR
    U["Browser / mobile / external client"] -->|"HTTPS<br/>cookie / Bearer / API key"| EDGE["Ingress / WAF / TLS termination"]
    EDGE -->|"Trusted network + forwarded headers policy"| GW["Spring Cloud Gateway<br/>Authn/Authz / routing / filters"]
    GW -->|"Audience-specific token<br/>or backend credential / mTLS"| CAT["Catalog service"]
    GW -->|"Different token audience<br/>or service identity"| PAY["Payment service"]
    GW -->|"No browser session cookie"| PUB["Public content backend"]
    GW <-->|"OAuth2/OIDC auth code<br/>token / JWKS"| IDP["Identity provider"]
    GW <-->|"Short-lived service secret"| VAULT["Vault / Secret Manager"]
```

**Có ít nhất ba ranh giới độc lập:**

1. **Client → Gateway:** thông tin do client gửi là **untrusted input**, kể cả `X-User-Id`, `X-Tenant`, `Forwarded`, `Host`, `X-API-Key` và `Cookie`. Gateway chỉ được xem client là authenticated sau khi kiểm tra token/session/key theo policy.
2. **Gateway → backend:** mỗi backend có trust level, audience/scopes và loại credential riêng. HTTPS/TLS bảo vệ chặng truyền, nhưng không quyết định liệu backend **được phép nhận credential đó**.
3. **Gateway → hệ quản lý danh tính và secrets:** OAuth2 client tokens, refresh tokens, API keys, certificates và signing materials cần storage/rotation/audit riêng. Không để route YAML vô tình lộ chúng.

### 2.1. Tài sản cần bảo vệ

| Tài sản | Ví dụ | Rủi ro nếu lộ |
|---|---|---|
| User access token | `Authorization: Bearer eyJ...` | Replay vào Resource Server nhận cùng audience; truy cập dữ liệu |
| Refresh token | OAuth2 offline/refresh credential | Lấy access token mới trong suốt vòng đời cho phép |
| ID token | OIDC token định danh cho client | Lộ claims/user info, sai mục đích nếu dùng làm API bearer |
| Session cookie | `__Host-GWSESSION=...` | Session hijacking/fixation |
| CSRF token | Form/header token gắn session | Bypass CSRF nếu lộ cùng context |
| Client API key | `X-API-Key: ...` | Dùng quota, giả lập một consumer/integration |
| Backend API key | `X-Backend-Api-Key: ...` | Truy cập backend với quyền máy-to-máy |
| OAuth2 client secret | Client credentials với IdP | Xin access token với identity của Gateway |
| mTLS private key | Service client certificate key | Giả Gateway khi kết nối dịch vụ |
| Credentials trong URI | `?token=...`, `user:pass@host` | Lộ qua logs, history, proxies và redirects |

### 2.2. Mười tình huống cần chặn

1. Client gửi header `X-Internal-Admin: true` và backend coi nó là quyền đã xác minh.
2. Gateway chuyển token dành cho **payment-api** tới catalog service chỉ vì request dùng cùng `Authorization`.
3. Gateway chuyển **session cookie** của chính nó tới mọi backend qua proxy header forwarding.
4. Backend trả `Set-Cookie` có `Domain` quá rộng khiến cookie nhạy cảm xuất hiện ở nhiều subdomains.
5. API key của đối tác bị ghi trong access log, route config, metric label hoặc tracing baggage.
6. Một `Location` redirect chứa token/credential đưa browser sang origin không được phép.
7. Gateway nhận một header `X-Forwarded-Proto: https` từ Internet rồi quyết định request là an toàn/được nội bộ tin cậy.
8. Local response cache/shared CDN trả dữ liệu một user cho user khác do thiếu phân vùng credential/session.
9. CircuitBreaker fallback hoặc error handler trả lại raw upstream exception/request headers chứa secrets.
10. Một dynamic route có `uri` trỏ tới máy không thuộc allowlist và dùng cùng service credential với routes khác — **SSRF và credential exfiltration**.

**Mục tiêu thiết kế:** credential chỉ tồn tại ở những chặng thật sự cần; nếu hệ thống/credential provider lỗi, **fail closed** thay vì cho phép route chạy thiếu kiểm tra, gửi token sai hoặc dùng credential mặc định.

## 3. Phân biệt các loại token và credential

### 3.1. Access token, ID token và refresh token

| Loại | Mục đích | Gateway nên làm | Không nên làm |
|---|---|---|---|
| **Access token** | Gọi một Resource Server theo `aud`/`scope`/`exp` | Xác minh và route theo policy; relay/exchange có chủ đích | Gửi tới mọi backend không quan tâm audience |
| **ID token** | OIDC identity assertion cho client | Dùng trong flow OIDC đúng vai trò | Thay access token để gọi API |
| **Refresh token** | Xin access token mới khi được cấp phép | Lưu ở backend/authorized-client store có bảo vệ, rotation | Gửi refresh token trong request downstream thông thường |
| **Opaque token** | Token cần introspection hoặc verification server-side | Resource Server introspection/authorization policy | Coi opaque string là JWT hoặc tin chỉ vì nó có vẻ dài |
| **Client API key** | Nhận diện consumer, quota/plan | Verify/hash lookup, bind policy, rotate | Coi key một mình là user identity có quyền cao |
| **Service credential** | Gateway chứng thực với backend/IdP | Server-side only, giới hạn audience/privilege | Chuyển lại cho browser hoặc đọc từ client header |

**JWT được mã hóa Base64URL chứ không được mặc định mã hóa bí mật.** Phần payload của JWT dạng JWS thường đọc được bởi người có token. Không đặt password, private key, thông tin ngân hàng hoặc PII không cần thiết vào claims. Đừng dùng ID token làm access token hay log toàn bộ JWT để “debug scopes”.

### 3.2. `iss`, `aud`, `exp`, `scope` và `sub` không hoán đổi nhau

- `iss`: ai phát hành token. Phải khớp IdP được trust.
- `aud`: token được cấp cho Resource Server nào; **mỗi backend phải kiểm tra audience của chính nó**.
- `exp`, `nbf`: thời hạn có hiệu lực; cần đồng hồ đồng bộ và clock skew giới hạn.
- `scope`/`scp`, roles: quyền được cấp; mapping sang `SCOPE_catalog:read` tùy issuer và converter.
- `sub`: đối tượng/subject; **không** tự đồng nhất với tenant, tổ chức hoặc tài khoản đã được phép truy cập một tài nguyên.
- `azp`/`client_id`: thông tin client được ủy quyền, không thay thế kiểm tra audience/scope.

Gateway kiểm tra chữ ký, issuer, lifetime và ít nhất scopes/audience theo hợp đồng. **Backend vẫn cần authorization tại cấp tài nguyên**: user A có scope `orders:read` không được đọc đơn hàng của user B chỉ vì Gateway đã chấp nhận token.

### 3.3. Token “được cấp cho Gateway” không tự hợp lệ với mọi backend

Ví dụ:

```json
{
  "iss": "https://idp.example.test/realms/demo",
  "sub": "user-123",
  "aud": ["gateway-api"],
  "scope": "catalog:read",
  "exp": 1893456000
}
```

Đây là **claims minh họa**, chưa phải token có chữ ký. Nó có audience `gateway-api`, **không có `payment-api`**. Không đưa nguyên token ấy đến payment chỉ vì Gateway đã giải mã và thấy user authenticated. Nếu backend cần xác thực end-user, thiết kế một trong các lựa chọn:

1. Access token ban đầu **được cấp trực tiếp** cho audience của backend và được kiểm tra ở cả hai tầng theo policy.
2. Gateway dùng **OAuth2 Token Exchange**/on-behalf-of flow được IdP hỗ trợ, tạo token có audience/scopes giảm thiểu cho backend.
3. BFF giữ user session tại Gateway; backend dùng **service credential** và nhận user context qua một kênh tin cậy có xác thực và kiểm soát, không dùng unsigned spoofable headers.

**Không tự coi việc thêm header `X-User-Id: user-123` là token exchange.** Nếu backend nhận identity header, bắt buộc có ranh giới mạng/mTLS/signature/HMAC, chặn direct callers và kiểm tra authorization tiếp.

## 4. Ma trận chuyển tiếp credential theo từng route

Trước khi viết filters, lập **một bảng quyết định**:

| Route | Ai gọi? | Xác thực tại Gateway | Credential gửi backend | Phải loại bỏ |
|---|---|---|---|---|
| `/api/public/**` | Anonymous | Không bắt buộc user login, giới hạn abuse | Không credential | `Authorization`, `Cookie`, `X-API-Key`, internal identity headers |
| `/api/catalog/**` | User/app với JWT | JWT issuer/audience/scope | Token đúng audience catalog **nếu backend yêu cầu**; hoặc service token riêng | Gateway session cookie, client API key, `X-Internal-*` |
| `/api/payments/**` | User được phép | JWT + fine-grained rules | Payment-scoped token hoặc mTLS service identity | Catalog token, refresh token, generic cookie |
| `/api/bff/orders/**` | Browser session | Session cookie + CSRF theo flow | Scoped backend token/service identity | Browser `Cookie`, BFF session ID, CSRF secret |
| `/api/partners/**` | Partner integration | API key verified + quota | Credential riêng cho partner-backend nếu cần | **Raw partner key**, user cookies, untrusted identity header |
| `/internal/**` | Chỉ internal caller | mTLS/RBAC/network policy | Least-privilege identity phù hợp | Internet-controlled headers, secrets của routes khác |

Một route `http://backend`/`lb://service-id` không tự chứa quyền truy cập. **Routing và authorization là hai chính sách khác nhau**. Cần kiểm tra thứ tự thực tế của Spring Security WebFilters, Gateway route predicates, `GlobalFilter`/`GatewayFilter` và HTTP client filters.

### 4.1. Đặt tên rõ ràng

```text
clientAuthorization  = token do browser/mobile gửi
gatewaySessionCookie = cookie cho phiên login tại Gateway
partnerApiKey        = key nhận diện consumer bên ngoài
backendServiceKey    = key của Gateway để gọi backend
backendAccessToken   = token có audience đúng backend
```

Không dùng chung một biến `secret` cho tất cả các loại trên, vì làm tăng nguy cơ forward nhầm. Nếu quản lý credentials bằng Vault, đặt key paths/roles riêng cho từng backend và môi trường, với policy tối thiểu.

### 4.2. Chọn cách xử lý

| Kết luận kiểm tra | Hành động |
|---|---|
| Client không được phép | Trả 401/403, **không gọi downstream** |
| Credential không thuộc audience route | Không relay; yêu cầu token phù hợp hoặc exchange đúng flow |
| Backend không cần user token/cookie | **Remove** trước outbound HTTP routing |
| Backend cần user token | Relay token được xác minh và đúng audience; backend cũng xác minh |
| Backend cần máy-to-máy | Inject credential từ server-side provider, không dùng giá trị client gửi |
| Token/key provider đang lỗi | Fail closed 503/controlled error; không bypass auth |
| Response có credential từ backend không được browser biết | Remove/redact response header/body theo contract |
| Cần log/trace | Chỉ ghi presence, outcome, route ID, credential reference không nhạy cảm |

## 5. Spring Cloud Gateway route/filter chain và HTTP header forwarding

Spring Cloud Gateway có các GatewayFilter factories như `RemoveRequestHeader`, `SetRequestHeader`, `RemoveResponseHeader`, `AddRequestHeader`, `TokenRelay` và `SecureHeaders`. Chúng xử lý những nhiệm vụ **khác nhau**.

| Thành phần | Hướng | Công dụng | Cảnh báo |
|---|---|---|---|
| `RemoveRequestHeader` | Client → backend | Bỏ credential/header đã cấm | Không tự thay authentication/authorization |
| `SetRequestHeader` | Client → backend | Thay **một giá trị** header do Gateway kiểm soát | Không dùng để đặt secret công khai vào YAML |
| `AddRequestHeader` | Client → backend | Thêm giá trị header | Có thể tạo nhiều giá trị; không thích hợp để “ghi đè chắc chắn” identity header |
| `RemoveResponseHeader` | Backend → client | Bỏ header có secret hay thông tin nội bộ | Đừng xóa `Set-Cookie` nếu route thực sự dùng cookie backend |
| `TokenRelay` | Gateway → backend | Lấy access token OAuth2 authorized-client, forward bearer | Cần OAuth2 Client/registration và token audience policy |
| `SecureHeaders` | Gateway → client | Thiết lập security response headers | Không redacts request tokens hay thay mTLS |
| `GlobalFilter` tùy biến | Tùy implementation | Cross-cutting routing/filter rule | Thứ tự/Security context/body handling phải đúng |

**Bẫy quan trọng:** Một HTTP proxy có thể chuyển tiếp `Authorization` theo cách xử lý headers mặc định ngay cả khi **không** cấu hình `TokenRelay`. `TokenRelay` là cơ chế OAuth2 lấy/đặt access token; nó **không phải công tắc duy nhất** quyết định Authorization có đến backend hay không. Nếu route không cần token, hãy **chủ động xóa** nó và viết integration test ở downstream.

### 5.1. Route public: bỏ credential khỏi outbound request

YAML WebFlux 5.x tối giản:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: public-catalog
              uri: http://localhost:8081
              predicates:
                - Path=/api/public/**
                - Method=GET
              filters:
                - StripPrefix=2
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie
                - RemoveRequestHeader=X-API-Key
                - RemoveRequestHeader=X-Authenticated-User
                - RemoveRequestHeader=X-Internal-Role
                - RemoveResponseHeader=Set-Cookie
```

Request `GET /api/public/items/42` đến backend thành `GET /items/42` **không chứa** các credential headers liệt kê. `RemoveResponseHeader=Set-Cookie` phù hợp **nếu route public này không cho phép backend đặt cookie**; không copy rule ấy sang một ứng dụng cần session cookie. Không tự xóa các headers bảo mật như `Cache-Control`, `Vary` hoặc HSTS chỉ để làm response “đẹp”.

**Các điều kiện bảo mật kèm theo:** route `Method=GET` chỉ giới hạn HTTP method, **không** tự xác thực; backend ở `localhost:8081` là lab. Gateway vẫn cần rate limiting, TLS/egress policy và kiểm soát route selection để chống abuse. Nếu có route catch-all khác, test để nó không nhận request với thông tin nhạy cảm ngoài ý định.

### 5.2. Route nội bộ: không dùng `AddRequestHeader` làm identity proof

Ví dụ sai khi dùng upstream header như một thông tin xác thực:

```yaml
filters:
  - AddRequestHeader=X-Authenticated-User, admin
```

Điều này ghi **cùng một identity** cho mọi request route, không kiểm tra JWT/session hay phân quyền. Và nếu client đã gửi `X-Authenticated-User`, `AddRequestHeader` còn có thể tạo **hai giá trị** khiến các service parse khác nhau; đây là một dạng **header confusion**.

Nếu bạn cần inject một header do Gateway tạo, hãy **loại header client giả mạo** trước, sau đó dùng `SetRequestHeader` hoặc custom filter đặt **giá trị đã xác thực** từ principal, với allowlist backend và transport tin cậy. Đối với quyền mạnh/PII, **prefer token được ký, mTLS hoặc một identity propagation mechanism được thiết kế** thay vì trông chờ một chuỗi header không có xác minh.

### 5.3. `default-filters` không tự thay security chain

Các filter có thể được áp vào mọi route bằng `default-filters` trong namespace Gateway tương ứng, nhưng:

- Một policy “xóa Authorization trên mọi route” có thể làm hỏng Resource Server phía sau vốn cần bearer token.
- Một policy “thêm backend API key trên mọi route” là **nguy hiểm**, vì credential có thể gửi tới backend mới hoặc route bị chiếm.
- Filter ordering với `TokenRelay`, `RemoveRequestHeader` và custom filters có thể làm token **bị xóa sau khi relay** hoặc **bị relay lại sau khi xóa**.
- Các hoạt động ở `GatewayFilter` xảy ra **sau** những Spring Security WebFilters ở luồng WebFlux điển hình; nếu credentials bị xác thực tại Gateway thì test phải xác minh no-auth requests bị chặn trước outbound routing.

**Thiết kế tốt:** chuẩn hóa các header rủi ro cao **theo trust zone**, dùng filter mặc định chỉ cho những headers thật sự cần quy tắc chung, và route-specific auth/credential policy cho service nhạy cảm.

## 6. Xác thực JWT tại Gateway bằng Spring Security WebFlux

Gateway có thể là **OAuth2 Resource Server**: nhận Bearer token, kiểm tra chữ ký, issuer, thời hạn và quyền, rồi mới cho phép request đến route. Backend vẫn phải kiểm tra quyền theo resource và audience của chính nó nếu nhận bearer token.

### 6.1. Dependencies và source cấu hình

Maven fragment cho **Gateway Server WebFlux** với Spring Cloud BOM tương thích:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Các artifacts/starter names phải được đối chiếu với Spring Boot/Gateway release train. **Không thêm OAuth2 Client starter chỉ để xác minh JWT**; OAuth2 Client phục vụ các flow như login/authorized-client/TokenRelay được thảo luận ở mục 7.

`application.yml` (đổi issuer và audience thành tên thật của **môi trường**):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
          audiences: gateway-api
```

`issuer-uri` cấu hình issuer đáng tin; Spring Security có thể lấy JWK Set URI qua metadata endpoint của IdP để xác minh JWT. `audiences` là cấu hình Boot dành cho việc kiểm tra claim `aud` trên những release hỗ trợ; nếu target version không cung cấp property này hoặc cần nhiều quy tắc, đăng ký validator `OAuth2TokenValidator<Jwt>` đúng API. **Không coi chỉ cấu hình issuer là đã kiểm tra đủ audience**. Không dùng JWT giả/unsigned chỉ vì test OAuth2 phức tạp.

### 6.2. Java WebFlux security chain

```java
package com.example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain gatewaySecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/catalog/**")
                    .hasAuthority("SCOPE_catalog:read")
                .pathMatchers(HttpMethod.POST, "/api/payments/**")
                    .hasAuthority("SCOPE_payments:write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

**Đây là mô hình phân quyền minh họa**:

- `/api/public/**` chỉ cho **GET** anonymous theo route/security policy.
- `GET /api/catalog/**` yêu cầu scope `catalog:read`.
- `POST /api/payments/**` yêu cầu `payments:write`, nhưng **chưa đủ** để thực thi thanh toán an toàn: backend phải xác minh user/tenant, idempotency và các giới hạn giao dịch.
- `anyExchange().denyAll()` từ chối mọi path/method chưa được cho phép, gồm cả /actuator/gateway/** nếu chưa cấu hình quản trị riêng.
- Chưa thêm OAuth2 login hay cookie session vào ví dụ này; với bearer-only APIs, cần thiết kế CSRF policy theo client type. Không tắt CSRF toàn bộ rồi sao chép đoạn đó sang ứng dụng BFF có browser cookies.

**Nếu bạn muốn GET public vẫn có Bearer token đi qua nhưng không buộc xác thực:** `permitAll()` không bảo đảm mọi Authorization header hợp lệ sẽ được bỏ qua khi Resource Server filter xử lý. Với public route, chính sách chấp nhận/loại bỏ bearer invalid/valid cần được test. Quan trọng nhất, `RemoveRequestHeader=Authorization` loại token **trước khi forward**, không thay Spring Security WebFilter ở đầu vào.

### 6.3. Xác minh đủ JWT claims

Trước khi quyết định `authenticated()` hoặc `hasAuthority(...)`:

1. Xác minh thuật toán chữ ký được hỗ trợ/allowlisted; không chấp nhận `alg=none`.
2. Lấy public signing keys từ IdP/JWKS **được tin**, không tự tin một `jku`/`x5u` URL do attacker đặt trong JWT header.
3. Kiểm tra `iss`, `aud`, `exp`, `nbf`; xử lý clock skew nhỏ, có giới hạn.
4. Kiểm tra `scope`/`roles` và mapping theo chính sách issuer, không tin một claim `isAdmin` tùy tiện.
5. Đối chiếu `tenant`/`resource ownership` tại backend; một JWT hợp lệ chưa chắc cho phép đọc tài nguyên cụ thể.
6. Có quy trình key rotation và xử lý token đã revoke/compromised, đặc biệt khi dùng JWT ngắn hạn và không introspect mỗi request.
7. Không dùng refresh token hoặc ID token như bearer API authorization.

### 6.4. `401` và `403` có ý nghĩa khác nhau

| Request | Kết quả mong đợi | Có đến backend không? |
|---|---|---|
| Không token vào route bảo vệ | `401 Unauthorized` | Không |
| Token hết hạn, chữ ký sai, issuer sai | `401 Unauthorized` | Không |
| Token hợp lệ nhưng thiếu scope | `403 Forbidden` | Không |
| Token hợp lệ, đúng scope, route đúng | Kết quả nghiệp vụ | Có |
| Token có audience khác gateway | `401` theo validator | Không |
| Token đúng scope nhưng sai tenant/owner | Thường `403`/`404` theo backend policy | Có thể đã đến backend, phải từ chối |

Đừng ghi nguyên giá trị Bearer token vào `WWW-Authenticate`, error response hoặc logs. `WWW-Authenticate` có thể chỉ cho client biết **loại auth cần dùng, realm hoặc error code được chuẩn hóa**, không phải nội dung private signing key.

## 7. `TokenRelay`: khi nào được phép chuyển access token?

Spring Cloud Gateway Server WebFlux có **`TokenRelay` GatewayFilter Factory** tích hợp Spring Security OAuth2 Client. Nó lấy access token liên kết với một **OAuth2 authorized client/client registration** (hoặc token người dùng đăng nhập qua OAuth2 login) rồi đặt token vào request đến backend. Điều này **khác** việc một proxy HTTP thông thường giữ nguyên `Authorization` header do client gửi.

### 7.1. Điều kiện cấu hình

Theo tài liệu Gateway WebFlux, cần thêm OAuth2 Client dependency (tên Spring Boot starter tùy release train):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

Và có `spring.security.oauth2.client.*` properties để Spring tạo `ReactiveClientRegistrationRepository`/authorized-client services. Nếu chỉ khai `TokenRelay` nhưng **không có OAuth2 Client setup**, filter bean có thể không được tạo; route hoặc app sẽ fail startup. Một bearer-only Resource Server **không tự đồng nghĩa** đã có một OAuth2 authorized-client token cho `TokenRelay`.

### 7.2. TokenRelay có tên client registration

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: partner-api
              uri: lb://partner-api
              predicates:
                - Path=/api/partners/**
              filters:
                - StripPrefix=2
                - TokenRelay=partner-backend
```

`partner-backend` trong `TokenRelay=...` là **OAuth2 client registration ID**, không phải `Route ID`, `ServiceInstance ID` hoặc tự động là tên backend. Phải tồn tại một client registration/cơ chế authorized-client tương ứng. Token được forward phải có **audience và scopes phù hợp**; việc filter hoạt động về mặt kỹ thuật không tự bảo đảm token hợp lệ cho partner API.

Với Java DSL WebFlux:

```java
@Bean
RouteLocator partnerRoutes(RouteLocatorBuilder builder) {
    return builder.routes()
        .route("partner-api", r -> r
            .path("/api/partners/**")
            .filters(f -> f
                .stripPrefix(2)
                .tokenRelay("partner-backend"))
            .uri("lb://partner-api"))
        .build();
}
```

Đây là bean thay thế cho YAML route ở trên, **không đăng ký cả hai** vào cùng project với route ID giống nhau. Cần Spring Cloud LoadBalancer và DiscoveryClient cho `lb://partner-api`; cần OAuth2 Client config cho `partner-backend`.

### 7.3. `TokenRelay` không có `clientRegistrationId`

```yaml
filters:
  - TokenRelay=
```

Trong một ứng dụng đã dùng `oauth2Login()`, Gateway có thể lấy access token của **OAuth2 authorized client hiện tại** và gửi xuống resource service. Nhưng:

- **Không có tham số** không có nghĩa “đổi token sang bất kỳ audience nào”.
- Nếu người dùng chỉ có session được tạo thủ công, không có OAuth2 authorized client, không mặc định có token để relay.
- Nếu route tới nhiều backends với audiences khác nhau, relay cùng token cho tất cả có thể là rò rỉ không cần thiết.
- Cần bảo vệ AuthorizedClientService/token store và refresh-token lifetimes/rotation khi dùng lâu dài.

Tài liệu WebFlux nêu implementation `ReactiveOAuth2AuthorizedClientService` mặc định có thể dùng **in-memory store**; trong hệ thống nhiều Gateway replicas cần thiết kế lưu authorized clients/session phù hợp (ví dụ lưu phía server an toàn) để không tạo lỗi login/TokenRelay chỉ vì request chuyển replica.

### 7.4. TokenRelay, raw forwarding và Token Exchange khác nhau

| Cơ chế | Nguồn token | Có đổi audience/scopes? | Khi phù hợp |
|---|---|---|---|
| HTTP raw `Authorization` forward | Header client mang tới | **Không** | Backend được phép nhận chính token đã xác minh |
| `TokenRelay` | OAuth2 authorized client từ Spring Security | Không tự bảo đảm exchange/đổi audience | Flow OAuth2 Client/login đã cấp token dùng được ở backend |
| OAuth2 Token Exchange/OBO | IdP phát token mới từ subject token và policy | **Có thể** request audience/scopes mới khi IdP hỗ trợ | Gateway cần token riêng cho từng backend |
| Service-to-service client credentials | Gateway dùng client identity của nó | Token mang service identity | Backend chỉ cần quyền của Gateway, không cần end-user delegation |
| mTLS service identity | Client certificate được cấp cho Gateway | Không phải access token | Backend xác thực workload/service qua TLS |

**Nguyên tắc least privilege:** mỗi backend chỉ nhận loại credential nó cần. Khi cùng một user đi qua catalog, payments và profile, cân nhắc **scoped tokens theo resource**; không dùng một token có đầy đủ mọi scope rồi relay vô điều kiện.

### 7.5. Chiến lược “đổi token” không được triển khai bằng giả mạo header

Đừng làm:

```yaml
filters:
  - SetRequestHeader=Authorization, Bearer fake-payment-token
```

Một chuỗi “fake token” không có IdP signature, revocation, issuer, audience hoặc least privilege. Khi cần token exchange:

1. Gateway xác minh token đầu vào.
2. Gọi IdP/token endpoint trên **TLS tin cậy**, dùng client authentication.
3. Xin token mới cho `aud=payment-api`, scopes tối thiểu và bounded lifetime.
4. Không cache token đa user sai khóa; không lưu raw token trong metrics.
5. Backend kiểm tra access token mới, kể cả delegation/sub/actor claims theo quy định IdP.
6. Xử lý lỗi IdP bằng fail closed, không chuyển token gốc làm fallback khi audience sai.

Mỗi Authorization Server có các loại grant hỗ trợ khác nhau. Không khẳng định Spring Cloud Gateway `TokenRelay` tự thực thi RFC 8693 Token Exchange; đây là workflow riêng cần OAuth2 Client/IdP integration được triển khai và test.

## 8. Cookie phiên Gateway và cookie của backend không phải một

Browser thường tự gửi `Cookie` đến origin/path phù hợp. Nếu Gateway dùng session login (BFF hoặc OAuth2 login), browser mang **cookie phiên Gateway**; proxy routing không nên chuyển nó tới mọi microservice.

### 8.1. Cookie attributes bắt buộc hiểu

| Attribute | Vai trò | Điều không được suy diễn |
|---|---|---|
| `Secure` | Browser chỉ gửi cookie qua HTTPS (ngoại lệ platform/browser cần xem chính xác) | Không mã hóa nội dung cookie |
| `HttpOnly` | JavaScript phía browser không đọc trực tiếp cookie | Không chặn mọi XSS hoặc CSRF; browser vẫn tự gửi cookie |
| `SameSite=Strict` | Giảm cross-site sending đáng kể | Có thể ảnh hưởng OIDC redirect/cross-site flows |
| `SameSite=Lax` | Cân bằng an toàn và một số điều hướng top-level | Không thay CSRF token khi session-based actions nhạy cảm |
| `SameSite=None` | Cho phép cross-site context được hỗ trợ | **Phải đi với Secure**, tăng rủi ro CSRF nếu không có bảo vệ |
| `Domain` | Giới hạn domain/subdomain nào được nhận cookie | Domain rộng tạo rủi ro subdomain sharing |
| `Path` | Giới hạn URL paths mà browser gửi cookie | Không phải security isolation tuyệt đối giữa apps cùng host |
| `Max-Age/Expires` | Thời gian browser lưu cookie | Không thay server-side session expiration/revocation |
| `__Host-` prefix | Browser yêu cầu `Secure`, `Path=/` và **không có Domain** | Không thay việc server xác minh session |

Cookie mẫu cho Gateway BFF:

```http
Set-Cookie: __Host-GWSESSION=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

`<opaque-random-id>` chỉ là ký hiệu, không chứa giá trị thực. Cookie nên là **session identifier ngẫu nhiên đủ entropy**, không lưu token/PII ở dạng plaintext trong cookie. Server-side session store có expiry, rotation và invalidation khi logout; nếu cookie bị đánh cắp, `HttpOnly`/`Secure` không thể tự thu hồi.

### 8.2. Spring WebFlux `CookieWebSessionIdResolver`

Với Gateway Server WebFlux có **WebSession** dùng cookie, cấu hình ví dụ:

```java
package com.example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration(proxyBeanMethods = false)
class WebSessionCookieConfiguration {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();

        resolver.setCookieName("__Host-GWSESSION");
        resolver.addCookieInitializer(builder -> builder
            .path("/")
            .secure(true)
            .httpOnly(true)
            .sameSite("Lax"));
        return resolver;
    }
}
```

Ví dụ này chỉ điều chỉnh **WebFlux WebSession cookie**, không tự tạo OAuth2 login flow, không tự chia sẻ WebSession giữa replicas, không tự cài Spring Session Redis và không thay `HttpSession` ở Gateway Server Web MVC. Nếu app không dùng WebSession/cookie auth, đừng tạo session chỉ để “an toàn hơn”.

**Với Gateway sau TLS-terminating ingress**, cần bảo đảm `Secure` được gán đúng và forwarded-proxy trust được cấu hình. Không tin `X-Forwarded-Proto` client tự đặt. `__Host-` yêu cầu không có Domain và `Path=/`, nên không dùng nó nếu chủ ý cần cross-subdomain cookie sharing (việc đó cũng cần threat modeling riêng).

### 8.3. Session rotation, logout và storage

Một thiết kế session an toàn cần:

1. Tạo session ID ngẫu nhiên qua CSPRNG; không dùng email, timestamp hay database ID dễ đoán.
2. Rotate session ID sau login/privilege elevation để chống session fixation.
3. Có idle timeout và absolute timeout phía server; kiểm soát concurrent sessions theo rủi ro.
4. Invalidate server-side session và authorized client tokens theo policy khi logout.
5. Với nhiều Gateway replicas, dùng server-side session/authorized-client store **được bảo vệ** hoặc sticky session có phân tích failover; sticky session không phải security solution.
6. Bảo vệ Redis/session store bằng ACL, TLS, network isolation, expiry và backup/retention policy.
7. Không in session ID vào request logs, Sentry tags, query string hoặc telemetry baggage.

Spring Session cung cấp các integration cho lưu sessions (ví dụ Redis) tùy Servlet/WebFlux stack; chọn starter/repository đúng Boot release. **Đừng coi một hướng dẫn Servlet là chứng minh WebFlux reactive session được cấu hình y hệt**: đọc đúng Spring Session reactive documentation.

### 8.4. Gateway không nên gửi chính cookie phiên của nó tới backend

Với route BFF mà backend dùng **server-to-server authentication**:

```yaml
filters:
  - RemoveRequestHeader=Cookie
  - RemoveRequestHeader=Authorization
  - RemoveRequestHeader=X-API-Key
  # Sau đó credential server-side được gắn bởi filter chuyên dụng.
```

Khi Gateway nhận browser session cookie và Spring Security WebFilters đã xác thực user, route filters có thể loại browser credentials **trước khi HTTP routing**, còn backend nhận một credential đã kiểm soát. **Không** diễn giải `RemoveRequestHeader=Cookie` như xóa phiên tại Gateway; Spring Security có thể đã xử lý cookie/session ở inbound phase. Nhưng **không hardcode giả định về filter order**: phải chạy integration test để chứng minh authenticate trước và strip trước outbound.

Nếu backend yêu cầu một cookie nghiệp vụ riêng, thiết kế allowlist cookie names, rewrite domain/path và backend auth thay vì remove toàn bộ. Tránh để các cookies của nhiều ứng dụng có **cùng tên** trên một origin Gateway; browser có thể gửi nhiều giá trị `Cookie` và backend có thể parse theo thứ tự khác nhau.

## 9. Cookie authentication cần CSRF; CORS không phải authentication

**CSRF** là nguy cơ browser tự gửi cookie phiên khi một trang khác kích hoạt request thay đổi trạng thái. **CORS** là cơ chế để browser quyết định JavaScript ở origin khác có được đọc response/call API với headers hay không. Hai cơ chế khác mục đích.

### 9.1. Khi nào cần CSRF?

| Kiến trúc client | Credential browser tự gửi? | CSRF |
|---|---|---|
| BFF dùng HttpOnly session cookie | **Có** | Bật CSRF protection cho state-changing requests |
| OAuth2 login lưu session ở Gateway | **Có** | Phải xử lý CSRF phù hợp login/session flow |
| API chỉ nhận `Authorization: Bearer ...` do non-browser client gửi | Không tự gửi qua browser cookie | Có thể không cần CSRF theo threat model, nhưng vẫn cần XSS/token security |
| Browser lưu Bearer token trong JS-readable storage | Header tự gửi bằng code | Rủi ro XSS/token theft lớn; nên cân nhắc BFF/cookie HttpOnly |
| mTLS client cert trong browser | Tùy browser/client certificate behavior | Đánh giá CSRF và origin policy theo luồng thực tế |

**Không tắt CSRF toàn cục** với lý do “Gateway là REST API” nếu có cookie-based login. `HttpOnly` không bảo vệ khỏi request giả mạo vì browser vẫn tự động gắn cookie; `SameSite=Lax/Strict` chỉ là phòng thủ bổ sung, không thay một CSRF token được xác minh hoặc chiến lược same-origin được thiết kế.

Với Spring Security WebFlux, CSRF protection có thể dùng `ServerCsrfTokenRepository` và cấu hình `ServerHttpSecurity.csrf(...)` theo phiên bản. Nếu frontend JavaScript cần đọc CSRF token, nên expose **CSRF token riêng** theo cách an toàn và nhận lại qua một custom header; không đưa token phiên hoặc refresh token vào JS-readable cookie để “dễ lập trình”.

### 9.2. Flow BFF an toàn minh họa

```mermaid
sequenceDiagram
    participant B as Browser
    participant G as Gateway/BFF
    participant S as Session + OAuth2 authorized-client store
    participant O as Orders backend
    B->>G: POST /api/bff/orders + secure session cookie + CSRF header
    G->>S: Validate session and CSRF binding
    S-->>G: Authenticated user context
    G->>G: Authorize scope / tenant / action
    G->>G: Remove Cookie, Authorization, X-API-Key from outbound
    G->>O: Scoped service credential / exchanged token + request
    O->>O: Resource ownership authorization
    O-->>G: Response without backend credential
    G-->>B: Status + safe body, Cache-Control: no-store
```

Nếu backend dùng một cookie riêng, bước remove Cookie có thể phải thay bằng cookie allowlist/re-issuance theo domain policy. Luồng trên **không yêu cầu** backend tin một `X-User` header không có chữ ký, và không để browser lấy access/refresh tokens từ session store.

### 9.3. CORS allowlist và credentials

Các response headers quan trọng:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN
```

Đây là ví dụ cho **một origin đã phê duyệt**, không phải cấu hình CORS của Gateway đã hoạt động. Nếu có credentials, không dùng `Access-Control-Allow-Origin: *` trái mô hình credentials trong browser. Không trả về origin bất kỳ từ `Origin` header chỉ bằng cách echo; cần allowlist và URL parsing/normalization chính xác.

**Preflight OPTIONS**:

- Browser gửi `Origin` + `Access-Control-Request-Method`/`-Headers`;
- Gateway phải xử lý OPTIONS đúng CORS policy, không bắt bearer/session auth làm preflight thất bại ngoài dự kiến;
- Một request actual POST vẫn phải được xác thực, có CSRF token đúng nếu dùng cookie session;
- Backend không nhất thiết phải nhận OPTIONS nếu Gateway giải quyết CORS ở edge;
- CORS không ngăn các non-browser clients gửi request trực tiếp và không thay authorization.

### 9.4. Cookie `SameSite=None` cho OIDC có nên dùng không?

Không nên chọn `SameSite=None` mặc định chỉ vì đang dùng OAuth2 login. Trên nhiều flows top-level navigation GET, `Lax` có thể đủ, nhưng OIDC có thể dùng POST response mode/cross-site embedding hoặc ứng dụng cần third-party contexts. Hãy test **đúng callback flow/browser** rồi chọn `SameSite` và `Secure` thích hợp; nếu phải dùng cross-site cookies, CSRF/origin/anti-replay controls càng quan trọng.

### 9.5. Phân biệt lỗi browser

| Triệu chứng | Nguyên nhân khả dĩ |
|---|---|
| Browser nói “CORS error” nhưng cURL 200 | Preflight/ACAO/credentials/Vary config, không phải backend auth |
| Browser không giữ cookie sau login | `Secure`, Domain/Path/SameSite, HTTPS or redirect scheme |
| GET hoạt động, POST trả 403 | CSRF token thiếu hoặc authorization thiếu; kiểm tra response/logs |
| Logout rồi cookie mất nhưng session vẫn valid | Chưa invalidate server-side session/authorized client |
| Cookie gửi tới backend không liên quan | Proxy forward `Cookie`, thiếu strip/allowlist |
| Browser đọc được session cookie qua JS | Thiếu `HttpOnly` hoặc cookie khác đang chứa credential |

## 10. Client API key và backend API key: hai danh tính khác nhau

**API key không phải JWT, không phải session cookie, và thường không có chuẩn audience/claims như OAuth2 access token.** API key có thể dùng để nhận diện partner, quota plan, application usage; không nên là cơ chế duy nhất bảo vệ giao dịch tài chính hoặc dữ liệu cá nhân có giá trị cao.

### 10.1. Bốn bước xử lý key đến từ client

1. Nhận key ở header có tên **được quy định rõ** (ví dụ `X-API-Key`); chỉ cho phép qua HTTPS.
2. Kiểm tra format/length và lookup một **verifier** phía server theo key ID hoặc keyed hash, không ghi raw value.
3. Kiểm tra key active, expiry/revocation, partner permissions, route allowlist, quota và IP/network restrictions phụ trợ.
4. Sau khi xác thực và gán consumer identity, **loại raw key khỏi outbound request** trừ khi backend cụ thể có contract để nhận nó và được phép.

Không để API key trong query string:

```http
GET /api/partners/orders?api_key=secret-value HTTP/1.1
```

Query string dễ xuất hiện trong proxy logs, browser history, analytics, Referer và caching. Với đối tác, header `X-API-Key` hoặc `Authorization: ApiKey ...` vẫn phải được bảo vệ TLS/redaction; **header không tự an toàn nếu logging/wiretap in nguyên dữ liệu**.

### 10.2. Lưu key an toàn

API key nên có entropy cao, phát sinh bằng CSPRNG và chỉ hiển thị **một lần** khi phát hành. Với random key đủ entropy:

- Có thể lưu public prefix/key ID để lookup và hash/HMAC verifier của phần secret.
- Dùng constant-time comparison khi kiểm tra secret verifier nếu cần tránh timing leaks.
- Encrypt backups/secret store, tách audit và quyền quản lý khóa.
- Có expiry/revocation/rotation; tồn tại hai key trong khoảng chuyển đổi giới hạn nếu cần zero-downtime.
- Không dùng email, customer ID, tên partner hay một chuỗi có thể đoán như một API key.
- Nếu key không đủ entropy, không giả SHA-256 thuần đã bảo vệ khỏi brute-force; nên sinh lại khóa random đủ mạnh.

**Không dùng raw API key làm metric label hoặc Redis rate-limiter key ở dạng hiển thị**. Có thể dùng một **internal consumer ID đã được xác thực** hoặc HMAC/pseudonym được quản lý, tránh tạo high-cardinality labels và rò bí mật qua Redis key listings.

### 10.3. Ranh giới trước/sau

```text
External request:
  X-API-Key: <partner-key>
  X-Internal-Partner: admin       (untrusted)

Gateway:
  validate partner-key -> partner-id and scopes
  authorize /api/partners/** + quota
  remove X-API-Key and X-Internal-Partner
  obtain scoped backend credential

Outbound request:
  X-Backend-Api-Key: <service-secret>   (chỉ cho partner backend)
  X-Correlation-ID: <trusted/validated-id>
  [no original partner key, no browser session cookie]
```

Các dấu `<...>` trên chỉ là placeholder, không phải secrets thật. Backend cần kiểm tra service credential hoặc mTLS và tiếp tục kiểm tra quyền partner theo một **identity context đáng tin**, không tin user-provided ID.

### 10.4. API key bị lộ, xoay khóa như thế nào?

| Sự kiện | Hành động |
|---|---|
| Partner key bị lộ trong CI log | Revoke/rotate key, scrub logs theo retention policy, review nơi sao chép |
| Backend shared key bị lộ | Rotate service key riêng backend, kiểm tra audit, chặn key cũ |
| Key vẫn hợp lệ nhưng quota bị abuse | Rate limit/quota theo consumer, monitor anomalies; không coi key là identity người dùng |
| Một backend bị chiếm | Revoke backend credentials, chặn egress/lateral movement, rotate những key chỉ backend đó biết |
| Nhiều Gateway replicas dùng key cũ mới lẫn lộn | Dual-key overlap ngắn hạn + metrics per key version không lộ key + rollout/revoke có kiểm soát |

Thay vì một shared key toàn bộ microservices, dùng **credential theo từng backend/service/environment**, có scope tối thiểu và khả năng revoke độc lập. Khi hệ thống hỗ trợ, **mTLS hoặc short-lived workload tokens** thường giảm một số rủi ro của API key lâu hạn.

## 11. Cấp backend credential từ server-side provider, không lấy từ client

Một Gateway đôi khi phải xác thực với legacy backend bằng `X-Backend-Api-Key`. Mục tiêu:

1. Backend key **không có trong request client**.
2. Key chỉ được gắn ở **route dành riêng cho backend đó**.
3. Raw partner key, browser cookie và Bearer token không có audience bị loại trước outbound routing.
4. Key được nạp từ **Secret Manager/Vault/Kubernetes Secret** hoặc provider quản lý vòng đời, có rotation/revocation, không hardcode Java/YAML.
5. Nếu provider không có credential hợp lệ, trả **503** hoặc policy error có kiểm soát, không forward request thiếu auth hay fallback sang key khác.
6. Không log key ở GlobalFilter, Netty wiretap, metrics hoặc exception.

### 11.1. Vì sao không dùng `AddRequestHeader` chứa secret?

Ví dụ cần **tránh trong production**:

```yaml
filters:
  - AddRequestHeader=X-Backend-Api-Key, super-secret-value
```

Raw value có thể lọt vào Git, management endpoints hiển thị route definitions, debug logs, change review, backups hay config server. Với `AddRequestHeader`, nếu client đã có `X-Backend-Api-Key`, backend có thể nhìn thấy **nhiều giá trị**. Đổi thành `SetRequestHeader` từ một variable cũng chưa giải quyết việc secret xuất hiện trong cấu hình/route metadata hoặc rotation. Thích hợp hơn là một component server-side chuyên dụng có policy và secret retrieval riêng.

### 11.2. Thiết kế `BackendCredentialProvider`

Một interface cung cấp **giá trị key hiện hành** cho một backend đã biết:

```java
package com.example.gateway.security;

public interface BackendCredentialProvider {
    /**
     * Trả credential hiện hành đã được nạp trong memory và
     * kiểm tra expiry/rotation theo policy. Không gọi blocking I/O
     * trực tiếp từ Spring WebFlux event loop.
     */
    String currentKey(String backend);
}
```

Implementation production nên được kết nối với Vault/Secret Manager và **cache được quản lý**, có refresh bất đồng bộ theo lịch/quy trình do hệ thống hỗ trợ. Không tự gọi API Vault đồng bộ ở mỗi request trên Reactor Netty event loop. Khi không có secret hợp lệ, trả null hoặc result báo lỗi để filter fail closed; tránh long-lived stale key. Nếu cần provider reactive trực tiếp, thay API bằng `Mono<Credential>` và xử lý timeout/cancellation/backpressure đúng, không gọi `.block()` trong `GatewayFilter`.

### 11.3. Custom WebFlux `GatewayFilterFactory` minh họa

```java
package com.example.gateway.security;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;

import java.util.Set;

@Component
public final class BackendApiKeyGatewayFilterFactory
        extends AbstractGatewayFilterFactory<
            BackendApiKeyGatewayFilterFactory.Config> {

    private static final Set<String> ALLOWED_BACKENDS =
        Set.of("orders", "partner");

    private final BackendCredentialProvider credentials;

    public BackendApiKeyGatewayFilterFactory(
            BackendCredentialProvider credentials) {
        super(Config.class);
        this.credentials = credentials;
    }

    @Override
    public GatewayFilter apply(Config config) {
        return (exchange, chain) -> {
            String backend = config.getBackend();
            if (backend == null ||
                !ALLOWED_BACKENDS.contains(backend)) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }

            String secret = credentials.currentKey(backend);
            if (secret == null || secret.isBlank()) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
                return exchange.getResponse().setComplete();
            }

            ServerHttpRequest outgoing =
                exchange.getRequest().mutate().headers(headers -> {
                    // Never let client override internal credentials.
                    headers.remove("X-Backend-Api-Key");
                    headers.remove("X-API-Key");
                    headers.remove(HttpHeaders.AUTHORIZATION);
                    headers.remove(HttpHeaders.COOKIE);
                    headers.remove("X-Internal-Role");

                    // Set one server-controlled value.
                    headers.set("X-Backend-Api-Key", secret);
                }).build();

            return chain.filter(
                exchange.mutate().request(outgoing).build());
        };
    }

    public static final class Config {
        private String backend;

        public String getBackend() {
            return backend;
        }

        public void setBackend(String backend) {
            this.backend = backend;
        }
    }
}
```

**Đây là mã mẫu cho một filter được kiểm soát trong Gateway Server WebFlux**. Để chạy cần một bean `BackendCredentialProvider` thực, cấu hình Spring Security/route đúng, và **không dùng provider test fake trong production**. Nếu thiếu provider, startup fail là kết quả an toàn hơn việc silently bỏ credential. Các luồng nhập/chỉnh sửa `Config.backend` phải được kiểm soát bằng policy; allowlist chỉ hai tên là minh họa, không phải danh sách sản phẩm.

### 11.4. Route áp dụng filter theo tên backend cụ thể

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-bff
              uri: lb://orders-service
              predicates:
                - Path=/api/bff/orders/**
              filters:
                - StripPrefix=2
                - name: BackendApiKey
                  args:
                    backend: orders
```

Backend route **phải được allowlist URI/service ID và sở hữu bởi control plane tin cậy**. Nếu một admin có thể đổi `uri: lb://orders-service` thành một attacker-controlled host, filter vẫn inject key vào request đó; **filter allowlist `backend=orders` không tự xác minh đích network**. Bắt buộc có thêm route definition authorization, egress policy, DNS/SSRF protections và integration tests.

**Lưu ý flow auth:** route BFF phải được Spring Security WebFlux chặn/authorize **trước khi filter này chạy**; filter này **không tự xác thực người dùng**. Nếu backend cần end-user identity, đừng suy ra user chỉ từ sự hiện diện của service API key; backend authorization phải dựa một token/exchanged context được xác minh hoặc cơ chế delegation riêng.

### 11.5. Thiếu một bean/provider nên xử lý ra sao?

| Trường hợp | Hành vi |
|---|---|
| Provider bean không được đăng ký | Startup fail, sửa configuration/dependency |
| Provider trả null/empty key | Gateway trả 503 trước outbound call |
| Secret hết hạn/đã revoke | Fail closed, refresh/rotate theo policy |
| Client gửi `X-Backend-Api-Key` giả | Bị xóa trước khi gắn server key |
| Route sang backend không có trong allowlist | 403/route load-time rejection |
| Backend trả 401 vì key cũ | Alert rotation drift; không log key; không retry vô hạn |
| User chưa được phép vào `/api/bff/orders/**` | Spring Security trả 401/403 trước khi filter được gọi |

**Đừng dùng `String` làm nơi chứa secret lâu dài hơn cần thiết**, dù HTTP headers cuối cùng yêu cầu chuỗi; tránh giữ secret trong static global cache không có expiry, tránh dump heap/logging khi điều tra sự cố. Với OAuth2 client credentials hay mTLS khả dụng, ưu tiên short-lived, audience-bound credentials.

## 12. TLS/mTLS và danh tính Gateway khi gọi downstream

Một Gateway triển khai ở edge thường có **hai kết nối khác nhau**:

```text
Client --TLS--> Ingress/Gateway --TLS/mTLS--> Orders service
              ^ public HTTPS     ^ internal service identity
```

HTTPS từ browser đến ingress **không bảo đảm** chặng Gateway → backend đã được mã hóa. Đừng coi network “private” là lý do gửi bearer token, cookie hoặc backend API key qua HTTP plaintext mà không có threat model.

### 12.1. TLS bảo vệ gì?

| Cơ chế | Bảo vệ được | Không thay thế |
|---|---|---|
| TLS client → Gateway | Confidentiality/integrity trên chặng public | Authorization, anti-CSRF, backend TLS |
| TLS Gateway → backend | Credential và payload khi truyền nội bộ, hostname validation | Backend audience/scope/resource authorization |
| mTLS Gateway → backend | Backend xác thực certificate của Gateway, Gateway xác thực backend | User identity, business authorization, token expiry |
| Service mesh mTLS | Workload-to-workload identity/transport | Route policy, app-layer identity, quota |
| HSTS | Browser dùng HTTPS ở các request sau theo policy | API key rotation, TLS giữa microservices |

**mTLS là service/workload authentication**, không tự xác minh user đang truy cập đơn hàng của ai. Nếu backend cần end-user delegation, dùng access token thích hợp hoặc signed user context đã được phê duyệt cùng mTLS.

### 12.2. Outbound TLS trong WebFlux

Gateway Server WebFlux thường dùng Reactor Netty HTTP client. Cấu hình truststore/SSL/handshake timeouts thuộc các nhóm `spring.cloud.gateway.server.webflux.httpclient.*` và TLS properties của release train; không chuyển máy móc sang Servlet/Web MVC `RestClient`. Với Spring Cloud Gateway Server Web MVC, các bản hiện hành mô tả cấu hình **Spring Boot SSL bundles/`spring.http.client.ssl.bundle`** cho outbound client.

**Không dùng các thiết lập tắt xác minh chứng chỉ** như:

```yaml
# KHÔNG đưa vào production:
# spring.cloud.gateway.server.webflux.httpclient.ssl.use-insecure-trust-manager: true
```

Để kiểm thử, tạo CA test, certificate SAN khớp hostname backend, cấu hình trust hợp lệ và test cả negative cases:

1. Certificate của backend được ký bởi CA tin cậy → thành công.
2. Certificate hostname/SNI không khớp → kết nối thất bại.
3. CA không được trust → handshake thất bại.
4. Backend yêu cầu mTLS mà Gateway thiếu client cert → thất bại.
5. Cert hết hạn hoặc đã rotate nhưng Gateway chưa nạp mới → fail closed và cảnh báo.

**Không “sửa” lỗi TLS bằng cách relay token khác, thêm `X-Forwarded-Proto` hoặc bật trust-all.** TLS failures, OAuth2 failures và Gateway route failures thuộc những tầng khác nhau.

### 12.3. Chọn identity nội bộ

Nếu backend hỗ trợ cả mTLS và OAuth2:

- Dùng mTLS để kiểm tra **Gateway workload** và hạn chế lateral movement.
- Dùng scoped access token để kiểm tra **ngữ cảnh user/client** hoặc quyền machine-to-machine.
- Dùng service DNS/`lb://service-id` allowlist cho đích đã phê duyệt.
- Ghi audit `service principal`, `route ID`, `decision`, `tenant ID` ở dạng không nhạy cảm.
- Không ghi raw access token hoặc private key vào trace.

Nếu backend chỉ nhận API key legacy, có thể tạm dùng service credential từ mục 11, nhưng cần giới hạn scope/rotation và network policy; **API key đơn lẻ không tương đương với mTLS**.

### 12.4. Trusted proxy headers

`Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` ảnh hưởng địa chỉ client, redirect và xác định HTTPS scheme. Theo Gateway WebFlux docs 5.x, việc tạo/áp dụng Forwarded/X-Forwarded headers có thể được kiểm soát bằng:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: "10\\.0\\.0\\.\\d+"
```

Biểu thức trên chỉ là **minh họa** một mạng nhỏ; **không** là allowlist CIDR chính xác cho mọi proxy. Cần match đúng IP format/IPv6, load balancer/ingress source addresses và release-specific semantics. Với thực tế có IPv6, NAT và nhiều hops, ưu tiên xây policy rõ và verify bằng request integration test. Đừng cấu hình `trusted-proxies: ".*"` để tin toàn bộ Internet. Ingress phải **xóa/ghi đè client-supplied forwarded headers trước khi thêm headers của nó**.

**Nếu header giả khiến Gateway nghĩ request HTTP là HTTPS**, ứng dụng có thể đặt redirect/cookie/HSTS sai hoặc log sai client IP; không dùng một IP tự khai để bỏ qua authentication/rate limiting.

## 13. Không để response trở thành kênh rò token/cookie

Credential có thể rò theo **chiều ngược lại** qua `Set-Cookie`, `Location`, response body, `WWW-Authenticate`, `X-Debug-*` hoặc exception message. Route filters không nên chỉ chăm chăm vào request.

### 13.1. `RemoveResponseHeader` theo contract

Giả sử backend catalog công khai vô tình phát:

```http
HTTP/1.1 200 OK
Set-Cookie: BACKENDSESSION=internal; Path=/; HttpOnly
X-Backend-Debug-Token: abc123
X-Internal-Host: catalog-pod-10-0-2-4
Content-Type: application/json
```

Với một **route không cần backend cookie**, filter:

```yaml
filters:
  - RemoveResponseHeader=Set-Cookie
  - RemoveResponseHeader=X-Backend-Debug-Token
  - RemoveResponseHeader=X-Internal-Host
```

Các headers nhạy cảm biến mất khỏi client response theo route policy. Nhưng nếu backend là ứng dụng cần đặt session cookie thực, **xóa `Set-Cookie` sẽ làm hỏng login**; thay vì blanket removal, hãy thiết kế cookie allowlist và kiểm tra `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path`.

### 13.2. Không được leak credentials qua `Location`

Ví dụ backend trả:

```http
HTTP/1.1 302 Found
Location: https://external.example.test/callback?access_token=<secret>
```

Trình duyệt có thể lưu URL trong history, gửi tới origin khác hoặc làm lộ query qua logs. Gateway cần policy redirect destinations, không cho backend tự sinh URLs chứa bearer tokens. **Không coi `RewriteLocationResponseHeader` là một giải pháp tự động xóa secrets trong mọi URL**; filter này chủ yếu biến đổi host/path/Location theo các rule, không thay validation mọi loại credential. Cần sửa upstream application và kiểm thử redirects.

### 13.3. `SecureHeaders` thuộc response hardening, không phải credential sanitizer

WebFlux `SecureHeaders` có thể bổ sung headers như:

- `Strict-Transport-Security` — ép HTTPS trong browser theo policy.
- `X-Content-Type-Options: nosniff` — hạn chế MIME sniffing.
- `X-Frame-Options: DENY` hoặc CSP `frame-ancestors` — hạn chế clickjacking.
- `Referrer-Policy: no-referrer` — giảm lộ URL qua referrers.
- `Content-Security-Policy` và `Permissions-Policy` — chính sách browser capabilities.

Nhưng **nó không xóa Authorization, Cookie hay API keys**, không thay TLS outbound và không cấp quyền cho route. Với HSTS, chỉ bật khi toàn bộ domain/subdomains đã hỗ trợ HTTPS và hiểu `includeSubDomains`/`preload` nếu dùng; không áp blindly lên môi trường staging có HTTP.

### 13.4. `Cache-Control` và shared caches

Với response chứa dữ liệu cá nhân/session/token:

```http
Cache-Control: private, no-store
Pragma: no-cache
```

`no-store` là chỉ dẫn hữu ích để tránh các HTTP caches tiêu chuẩn lưu nội dung nhạy cảm; `Pragma` chỉ phục vụ client legacy, không thay `Cache-Control`. Trong production, phải kiểm tra **CDN, browser cache, Gateway `LocalResponseCache` và backend caching** cùng lúc.

Không dựa vào `Vary: Authorization` như “đã bảo đảm tuyệt đối private cache” trong mọi cấu hình. Một shared cache có thể misconfigured hoặc key không phân tách tenant; lựa chọn an toàn hơn là **không cache** responses có session/user-specific data. Nếu phải cache, cần review cache key gồm user/tenant/authorization context, expiry/revocation, encryption và cache poisoning.

### 13.5. Error handlers và fallback

Một handler có thể vô tình trả:

```json
{
  "error": "backend timeout",
  "Authorization": "Bearer ...",
  "backendApiKey": "secret",
  "debugUri": "https://user:password@backend.internal"
}
```

Không trả raw exception/toString của request hay configuration. Gateway error response nên có **stable error code**, sanitized message và request/correlation ID không nhạy cảm; logs phía server có stack trace đã lọc. CircuitBreaker fallback chỉ trả dữ liệu đã được phép; không đem full `ServerWebExchange` attributes, token hoặc request headers vào response JSON.

## 14. Log, tracing, metrics và audit: tránh credential exfiltration thụ động

Rất nhiều lần lộ token xảy ra ở **hệ thống quan sát**: access logs, debug traces, APM tags, distributed tracing baggage, HAR files và exception dumps. Khi bật monitoring cho Gateway, tuân thủ **data minimization**.

### 14.1. Những gì có thể ghi và không nên ghi

| Nên ghi | Không nên ghi |
|---|---|
| Route ID, service ID, HTTP method, status class | `Authorization` và giá trị Bearer token |
| Authenticated principal ID nội bộ đã pseudonymize | Session ID, `Cookie`, `Set-Cookie` |
| Authn/authz outcome, reason code chuẩn | API key, client secret, refresh token |
| Backend response time, LB no-instance/retry count | Full URL nếu query chứa secrets hoặc PII |
| Correlation ID được kiểm soát | Raw login form, password, payment payload |
| Key version/reference như `orders-key-v3` (không raw key) | HMAC signing key/private certificate key |
| Trace ID/span ID | JWT payload đầy đủ, user PII, toàn bộ HTTP headers |

**Không dùng token làm correlation ID**: token có thể lặp lại trên hàng nghìn requests và là quyền truy cập. Tạo random/trace ID riêng, validate length/characters của client-supplied `X-Request-ID` và thay bằng giá trị tin cậy nếu cần.

### 14.2. Bảo vệ Reactor Netty wiretap và actuator

Gateway Server WebFlux có Reactor Netty HTTP client/server logging/wiretap features. Khi bật DEBUG/wiretap ở cấp headers/body, credentials và cookies có thể xuất hiện trong logs hoặc memory dumps. Trong production:

- Giữ wiretap/debug logging tắt trừ khi có incident procedure giới hạn thời gian/thu thập.
- Nếu cần chẩn đoán, ưu tiên log status/route ID/trace ID và header **names/presence**, không raw values.
- Redact ở **điểm tạo log**, không kỳ vọng downstream log collector xóa hết mọi bản sao.
- Bảo vệ `/actuator/gateway/routes`, `/actuator/env`, `/actuator/configprops`, `/actuator/heapdump` (nếu có) và mọi endpoint hiển thị route config/properties.
- Không gửi raw headers hoặc request bodies vào Sentry/OTel attributes/baggage.
- Dùng RBAC, retention/PII classification và audit khi truy xuất traces.

### 14.3. Log một quyết định thay vì secret

```json
{
  "routeId": "orders-bff",
  "requestId": "req-0f8a...",
  "subjectRef": "usr-42",
  "credentialSource": "backend-provider",
  "credentialVersion": "orders-v3",
  "authDecision": "ALLOW",
  "backendStatus": 200,
  "durationMs": 38
}
```

Đây là **ví dụ record không chứa secret**. `subjectRef` cũng có thể là thông tin cá nhân tùy hệ thống; dùng pseudonym và retention hợp lệ. Không log `credentialVersion` nếu phiên bản/key names tự tiết lộ topology nhạy cảm trong môi trường multi-tenant/public.

### 14.4. Đo kiểm trước khi release

Sau khi gọi route có JWT/cookie/API key **giả** trong môi trường test, rà soát:

1. Gateway stdout/stderr.
2. Ingress access log.
3. Downstream service log.
4. Trace spans + attributes + baggage.
5. Prometheus metrics label values.
6. CircuitBreaker/retry error details.
7. Test artifacts, screenshots, HAR files và CI upload logs.

**Kết quả PASS không phải chỉ là client nhận 200**: các giá trị credential giả đã dùng trong test **không được xuất hiện nguyên dạng** trong bất kỳ output log/trace/metrics không được phép nào.

## 15. Retry, CircuitBreaker, RateLimiter và cache có thể nhân rủi ro credentials

Một request thông thường chứa token/cookie/headers nhạy cảm sẽ đi qua filter chain. Khi bật `Retry`, `CircuitBreaker`, `RequestRateLimiter` hoặc `LocalResponseCache`, **số downstream calls, thời gian lưu dữ liệu, nơi credentials xuất hiện và thứ tự xử lý** thay đổi.

### 15.1. Retry có thể chuyển credentials nhiều lần

Giả sử POST thanh toán:

```text
POST /api/payments/charge
Authorization: Bearer <payment-scoped-token>
Idempotency-Key: <random-key>
```

Nếu Gateway retry sau timeout, backend có thể đã **commit giao dịch** ở lần đầu. Retry lặp request với cùng credentials mà không có idempotency contract có thể gây double charge. Cần:

- Chỉ retry **phương thức/loại lỗi được phê duyệt**, tránh vô điều kiện retry POST có side effects.
- Dùng idempotency key được backend xác minh và lưu kết quả theo key/tenant; key không tự là auth token.
- Đặt max retries/backoff/jitter và retry budget, chống retry storm.
- Xác định thời hạn access token còn đủ cho retry; nếu refresh giữa retries, phải đảm bảo token audience/subject không đổi ngoài policy.
- Nếu có `CacheRequestBody`/`ModifyRequestBody`, kiểm soát memory và không log body/credential.
- Test **số lần backend nhận request** và header visibility cho từng attempt.

Không để `Retry` hoặc HTTP client retry tự động gửi credential sang một **host khác** nếu route/redirect/discovery bị điều khiển trái policy. Với URI/host đích thay đổi, backend allowlist và TLS hostname validation phải còn hiệu lực ở mỗi attempt.

### 15.2. CircuitBreaker fallback cũng là một backend/destination

Ví dụ một route có fallback:

```yaml
filters:
  - name: CircuitBreaker
    args:
      name: ordersBreaker
      fallbackUri: forward:/fallback/orders
      statusCodes:
        - 500
        - 503
```

Fallback thường chạy bên trong Gateway khi dùng `forward:/fallback/orders`. Handler này có thể truy cập request/exchange chứa `Authorization`/`Cookie`. Không:

- Phản hồi lại raw request headers/exceptions;
- Gửi credentials tới fallback service khác audience;
- Trả fake 200 với private order data không được authorize;
- Coi fallback chính là phương thức xác thực;
- Mở `/fallback/orders` như public API phục vụ dữ liệu không có kiểm tra.

Với backend outage, **fail closed**: nếu authentication hoặc secret provider cũng không có, không dùng stale token của user khác hay bypass authorization để giữ “availability”. Fallback nên trả status/error code suy giảm đã được contract chấp thuận.

### 15.3. Rate limiting cần key đã được xác thực

Một cấu hình `RequestRateLimiter` hoặc Redis token bucket dùng một `KeyResolver`. Tránh:

```java
// Không tin header này nếu client tự khai và chưa xác thực.
String key = request.getHeaders().getFirst("X-User-Id");
```

Đúng hướng hơn là lấy:

- Authenticated consumer ID từ API key verifier;
- Principal/tenant ID đã được xác thực;
- Client certificate identity được TLS layer xác minh;
- Fallback rate limit key cho anonymous theo chính sách riêng.

Không dùng raw Bearer token/API key làm Redis key/metric label nếu có thể dùng internal opaque consumer ID hoặc keyed hash. Đặt quotas **trước khi downstream API key injection** để không gửi internal secret cho request đã bị Gateway từ chối. Nhưng thứ tự Gateway filter chain/security/route phải được test thực tế; không mặc định mọi limiter luôn chạy trước tất cả filters.

### 15.4. Response cache đặc biệt nguy hiểm với session/user data

`GET /api/orders/me` có thể trả cùng HTTP status cho hai users nhưng body khác. Nếu LocalResponseCache/CDN dùng một cache key chỉ theo `path`, user A có thể nhận response của user B. Vì vậy:

1. Với route chứa dữ liệu nhạy cảm: **disable shared caching**, dùng `Cache-Control: private, no-store` phù hợp.
2. Nếu cache thật sự cần: phân vùng theo authenticated principal/tenant/authorization scope và invalidation logic có review.
3. Không cache `Set-Cookie`/OAuth2 callback/refresh token response trong shared cache.
4. Test với **hai users** và **hai tenants** rồi kiểm tra body không giao thoa.
5. Backend vẫn kiểm tra ownership; cache hit có thể bỏ qua backend authorization, nên cache policy là một lớp security riêng.

Không cho rằng `LocalResponseCache` mặc định sẽ cache một response `no-store`; hãy kiểm tra eligibility theo version và test rằng các sensitive responses thực sự **không được lưu**.

### 15.5. Nguồn lỗi khi kết hợp filters

| Triệu chứng | Nguồn lỗi có thể |
|---|---|
| Backend nhận Authorization của user trên public route | Thiếu `RemoveRequestHeader` hoặc TokenRelay được bật quá rộng |
| Backend nhận hai `X-Backend-Api-Key` | Dùng `AddRequestHeader` khi client cũng gửi header |
| Retry call 2 không có credential | Custom filter cache body/headers sai hoặc filter order khác |
| Retry call 2 mang token user khác | Token cache shared giữa users/tenants |
| Fallback trả key vào JSON | Exception/error serializer quá nhiều metadata |
| RateLimiter bucket dùng raw key | `KeyResolver` lấy `X-API-Key` chưa hash/validated |
| User B nhận response của user A | Cache key/privacy policy sai |
| Downstream 401 sau rotation | Gateway replicas dùng phiên bản secret không đồng nhất |

## 16. WebSocket, SSE và credentials trên kết nối dài hạn

### 16.1. WebSocket handshake là HTTP request chứa credentials

Browser có thể gửi cookies và `Origin` trong WebSocket handshake. Một số clients phi browser hỗ trợ `Authorization` headers, nhưng **WebSocket browser API không cho JavaScript tùy ý đặt mọi HTTP header**, vì vậy có ứng dụng dùng session cookie/OIDC BFF để authenticate handshake. Dù cách nào:

- Authenticate/authorize **trước khi chấp nhận 101 Switching Protocols**.
- Validate `Origin` theo allowlist; WebSocket **không dùng CORS preflight như fetch**.
- Không nhận identity từ `Sec-WebSocket-Protocol` hoặc URL query token tùy tiện mà không xác minh và đánh giá rủi ro leak.
- Nếu bắt buộc có credential trong query/subprotocol, dùng token ngắn hạn single-use và scrub toàn bộ logs, nhưng ưu tiên flow an toàn khác.
- Gắn mỗi session vào principal/tenant đã xác thực; backend cần session authorization khi nhận messages.
- Đóng/revoke session theo policy khi credential hết hạn hoặc user logout; một kết nối đã nhận 101 không tự tái xác thực mọi message.

`TokenRelay` hoặc `RemoveRequestHeader` trên route WebSocket có thể tác động **handshake**, nhưng không dùng chúng như công cụ lọc mỗi WebSocket frame sau khi connection đã upgrade. Một HTTP `Retry` không tự reconnect/resume WebSocket messages an toàn.

### 16.2. Cookie và Origin trên WebSocket

Cookie `SameSite`/Domain/Path có thể khiến browser gửi hoặc không gửi session cookie trong handshake theo origin/site relationship. Nếu cookie gửi cross-site vì cấu hình rộng, không tự kết luận request hợp lệ chỉ vì có cookie; phải kiểm tra Origin, CSRF-like cross-site WebSocket hijacking và auth context. Trong Gateway Server Web MVC, tài liệu WebSocket có property `spring.cloud.gateway.server.webmvc.websocket.allowed-origins` theo version; Server WebFlux có handshake/filter route API riêng.

### 16.3. SSE và HTTP streaming

SSE dùng một HTTP response mở lâu. Token/cookie thường được kiểm tra **lúc thiết lập request**, nhưng token hết hạn trong khi stream đang mở cần policy riêng (close/re-auth/reconnect). Không để stream chứa raw secrets trong events, logs hoặc errors. `Retry` không thể mặc định replay một stream đã gửi event đầu tiên mà không gây trùng dữ liệu; sử dụng event IDs/`Last-Event-ID` và resume semantics được backend hỗ trợ.

### 16.4. Giới hạn payload và backpressure

Access token/cookie có thể rất dài; Gateway cần **header-size limits** hợp lý, nhưng không đặt thấp tới mức phá JWKS/JWT/cookies hợp lệ của ứng dụng. Với request body size, streaming/multipart và response buffering, tránh log hoặc giữ credentials lâu hơn cần thiết. Một client gửi cookie khổng lồ có thể gây header parsing/413/431 errors trước route; test error body không phản chiếu nguyên headers.

## 17. Vòng đời credentials: cấp phát, lưu trữ, xoay khóa và thu hồi

### 17.1. Quy trình chuẩn

```mermaid
flowchart LR
    ISSUE["Issue: minimum scope & TTL"] --> STORE["Store in protected system"]
    STORE --> USE["Use only on allowlisted route"]
    USE --> OBS["Observe metadata, never secret value"]
    OBS --> ROT["Rotate with bounded overlap"]
    ROT --> REVOKE["Revoke old credential"]
    REVOKE --> AUDIT["Audit + verify no stale replicas"]
```

| Giai đoạn | Điều cần kiểm tra |
|---|---|
| Cấp phát | Entropy, least privilege, audience và owner |
| Lưu trữ | Vault/KMS/Secret Manager/Redis/authorized-client store ACL/TLS |
| Truy xuất | Không gọi blocking secret fetch trên Reactor event loop; có cache/timeout |
| Sử dụng | Chỉ inject vào đích đã phê duyệt, không ghi log |
| Rotation | Các replicas có nhận key mới? Có overlap ngắn hạn? |
| Thu hồi | Backend/IdP thật sự chặn key/token cũ |
| Sự cố | Audit, incident isolation, remediation, retention policies |

### 17.2. Hạn dùng và cách rotation

**Access token** nên ngắn hạn, có issuer/audience/scopes; refresh token phải được bảo vệ tốt hơn vì cấp được access tokens mới. **API key** cần expiry/revocation/overlap khi rotate. **Client certificates** cần renew trước expiry và backend trust update. Với nhiều Gateway replicas:

1. Phát credential v2.
2. Backend tạm chấp nhận v1/v2 theo window được giới hạn.
3. Gateway provider/secret volume cập nhật sang v2.
4. Kiểm tra mọi replicas chỉ còn dùng v2 qua **key version/ref, không raw key**.
5. Revoke v1 và kiểm tra v1 không còn dùng được.
6. Thu hồi logs/artifacts đã chứa key cũ theo incident response.

Nếu secret bị lộ thực sự, không trì hoãn revoke chỉ để có zero-downtime migration; kế hoạch response theo mức độ nghiêm trọng và khả năng lạm dụng.

### 17.3. Kubernetes Secrets và Vault không tự che mọi vết rò

Kubernetes Secret là API object được mã hóa Base64 trong YAML/manifest, **không phải giá trị đã mã hóa bí mật chỉ vì Base64**. Cần encryption at rest, RBAC, pod security, audit, CSI/external secrets integration, giới hạn truy xuất và rotation. Secrets đưa vào environment variables có thể hiện trong process environment/dumps ở một số hệ thống; mounted files có quyền đúng vẫn cần tránh log và đảm bảo reload. Không gửi API key bằng annotation hoặc ConfigMap không bảo mật.

### 17.4. Mã hóa at rest và trust boundaries

Với OAuth2 authorized client store hoặc session store:

- Encryption at rest giảm một số rủi ro khi storage/backup bị đọc.
- TLS client → Redis/DB/Vault bảo vệ chặng mạng.
- Access control tách read/write token store khỏi route management.
- Retention/expiry và revocation không chỉ dựa vào TTL Redis.
- Không để một Gateway instance trên tenant A truy xuất refresh token tenant B nếu không được phép.
- Thử backup restore/DR để bảo đảm token revoke state không “sống lại” ngoài ý định.

### 17.5. Khi secret provider outage

Một lớp cache memory có thể giữ credential đã nạp hợp lệ tới expiration. Khi không còn credential hợp lệ:

- Trả 503/controlled failure cho route cần backend credential.
- Có metrics cho provider unavailable/credential expiry, **không** chứa raw secret.
- Không tự dùng hardcoded emergency key hoặc chuyển request thiếu authentication.
- Không chuyển request sang một backend khác có policy yếu hơn.
- Có alert và runbook rotation/restore, không tạo retry storm đến Vault/IdP.

## 18. Bài lab bảo mật: Gateway thật → mock backend

Để kiểm tra policy không chỉ nằm trên giấy, dùng **một backend HTTP giả** (WireMock/MockWebServer) và Gateway chạy trên **HTTP port thật trong test**. Không sử dụng backend production. Test tập trung vào:

1. Gateway nhận request có credentials giả từ client.
2. Spring Security quyết định allow/deny theo route.
3. Gateway route/filter thực thi.
4. Mock backend ghi **HTTP request đã nhận**, method, path, headers và số lần gọi.
5. Client nhận response không lộ header/credential backend.

### 18.1. Test project và dependencies

Maven fragments theo Boot/Cloud BOM tương thích:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.wiremock</groupId>
    <artifactId>wiremock</artifactId>
    <version>3.13.2</version>
    <scope>test</scope>
  </dependency>
</dependencies>
```

`3.13.2` là phiên bản **minh họa WireMock 3**, phải xem patch/compatibility của dự án. Không thêm dependency WireMock test scope vào production image. Spring Boot tests trong Boot 4 có artifact changes; dùng Spring Initializr/BOM phù hợp. Spring Security Resource Server/OAuth2 tests phải bổ sung dependencies khi thử 401/403.

### 18.2. Route test không phụ thuộc Internet

`src/test/resources/application-credentialtest.yml`:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: public-test-route
              uri: ${test.backend.base-url}
              predicates:
                - Path=/api/public/**
                - Method=GET
              filters:
                - StripPrefix=2
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie
                - RemoveRequestHeader=X-API-Key
                - RemoveRequestHeader=X-Authenticated-User
                - RemoveResponseHeader=Set-Cookie
                - RemoveResponseHeader=X-Backend-Debug-Token
```

Đây là **profile test riêng**; `${test.backend.base-url}` do JUnit cung cấp từ mock random port. Nếu app có route production mặc định, phải tách config/profile để route list không bị merge ngoài ý định. Không đưa mock URI vào production `application.yml`.

### 18.3. JUnit + WireMock test outbound header stripping

```java
package com.example.gateway;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration
    .wireMockConfig;
import static org.springframework.boot.test.context.SpringBootTest
    .WebEnvironment.RANDOM_PORT;

@SpringBootTest(classes = GatewayApplication.class,
                webEnvironment = RANDOM_PORT)
@ActiveProfiles("credentialtest")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CredentialBoundaryIntegrationTest {

    private static final WireMockServer BACKEND =
        new WireMockServer(wireMockConfig()
            .dynamicPort().bindAddress("127.0.0.1"));

    static {
        BACKEND.start();
    }

    @DynamicPropertySource
    static void backendUri(DynamicPropertyRegistry properties) {
        properties.add("test.backend.base-url", BACKEND::baseUrl);
    }

    @LocalServerPort
    int gatewayPort;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
            .baseUrl("http://127.0.0.1:" + gatewayPort)
            .build();
    }

    @BeforeEach
    void reset() {
        BACKEND.resetAll();
    }

    @AfterAll
    static void stop() {
        BACKEND.stop();
    }

    @Test
    void publicRouteDoesNotForwardClientSecrets() {
        BACKEND.stubFor(get(urlEqualTo("/items/42"))
            .willReturn(okJson("{\"sku\":\"42\"}")
                .withHeader("Set-Cookie", "backend=test")
                .withHeader("X-Backend-Debug-Token",
                            "synthetic-backend-secret")));

        client().get()
            .uri("/api/public/items/42")
            .header("Authorization", "Bearer synthetic-client-token")
            .header("Cookie", "__Host-GWSESSION=fake-session")
            .header("X-API-Key", "fake-partner-key")
            .header("X-Authenticated-User", "admin")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist("Set-Cookie")
            .expectHeader().doesNotExist("X-Backend-Debug-Token")
            .expectBody().jsonPath("$.sku").isEqualTo("42");

        BACKEND.verify(1, getRequestedFor(urlEqualTo("/items/42"))
            .withHeader("Authorization", absent())
            .withHeader("Cookie", absent())
            .withHeader("X-API-Key", absent())
            .withHeader("X-Authenticated-User", absent()));
    }
}
```

**Điều kiện chạy ví dụ:** class `GatewayApplication` và test profile phải có trong project Gateway; để tập trung vào strip filters, fixture này **không** gắn Resource Server authentication vào `/api/public/**`. Nếu application thực đã có `SecurityWebFilterChain` OAuth2 Resource Server đang xác thực mọi Bearer header kể cả `permitAll`, token giả `synthetic-client-token` có thể bị từ chối **trước khi Gateway route chạy**, và test sẽ trả 401. Khi đó cần dùng **test-only security configuration cô lập** hoặc một token test hợp lệ và test mục tiêu riêng; **không tắt authentication trong production chỉ để fixture pass**.

Đây là ví dụ kiểm thử **outbound header hygiene**, **không phải** test authn/authz. Các test xác minh token ở mục 18.4 phải chạy với Spring Security chain đúng và không chấp nhận fake unsigned token. `@DirtiesContext` giúp tránh Spring TestContext reuse URI của mock đã stop; không chạy song song tests cùng mock `resetAll()`.

### 18.4. Test authentication negative cases ở Gateway

Thiết lập một profile test riêng có:

- `SecurityWebFilterChain` với JWT Resource Server thật;
- JWKS/issuer **test-only** hoặc token được ký bằng khóa lab;
- Route `/api/private/**` yêu cầu `SCOPE_orders:read`;
- WireMock backend không chứa dữ liệu production.

Với mỗi request, xác minh:

| Request | Client expected | Mock backend |
|---|---|---|
| Không Bearer token | 401 | **0 calls** |
| Token signature sai | 401 | **0 calls** |
| Token expired/`nbf` future | 401 | **0 calls** |
| Token issuer khác | 401 | **0 calls** |
| Token `aud` khác gateway | 401 theo validator | **0 calls** |
| Token hợp lệ, thiếu scope | 403 | **0 calls** |
| Token hợp lệ, có scope | Theo backend contract | Đúng số calls được cho phép |
| Header `X-Internal-Role: admin` nhưng no token | 401 | **0 calls** |

Để assert no backend calls với WireMock:

```java
BACKEND.verify(0, anyRequestedFor(anyUrl()));
```

Đây là mảnh test method sau khi reset request journal. **Không dùng Mockito `@WithMockUser` hoặc `mockJwt()` rồi mặc định principal được chuyển qua live TCP `WebTestClient.bindToServer()`**. Các helpers Spring Security Test đặc biệt tiện khi bind mock application context, không tự tạo JWT trên HTTP wire. Với integration test live-port, hãy phát token thật được ký bởi **test signing key** hoặc dùng một test auth server/JWKS fixture.

### 18.5. Test backend key injection và rotation

Với filter `BackendApiKey` và provider test trả `key-v1-test-only`:

1. Client gửi `X-Backend-Api-Key: attacker-value` và `X-API-Key: partner-fake-key`.
2. Gateway xác thực/authorize client theo policy trước khi route.
3. WireMock ở **orders backend** nhận **một** `X-Backend-Api-Key: key-v1-test-only` và **không** nhận `attacker-value`/raw partner key/cookie.
4. Client response không chứa `X-Backend-Api-Key`/`Set-Cookie` từ backend nếu route contract cấm.
5. Provider đổi sang `key-v2-test-only`; request mới nhận v2, v1 bị revoke theo mô hình test.
6. Provider trả null/hết hạn → 503, backend **0 calls**, không fallback qua key cũ.
7. Thay route URI sang một mock backend **không được allowlist** trong một test cấu hình route control-plane riêng; phải bị chặn ở policy layer trước khi key được gửi.

**Không sử dụng raw production key/token trong test fixture.** Khi test rotation, key-v1/v2 chỉ là chuỗi giả, và cần assert logs/metrics không chứa chúng.

### 18.6. Test lỗi response và cache isolation

Stub WireMock trả:

```http
HTTP/1.1 302 Found
Location: /orders
Set-Cookie: BACKENDSESSION=synthetic
X-Backend-Debug-Token: synthetic-secret
Cache-Control: no-store
```

Test route có policy response:

- `Set-Cookie`/`X-Backend-Debug-Token` **không** tới browser nếu không được phép.
- `Location` không chứa token hoặc chuyển sang origin ngoài allowlist.
- `Cache-Control: no-store` vẫn được giữ.
- Với hai users synthetic A/B, response private không được cache/chia sẻ sai.
- Với backend HTTP 500, fallback không phản chiếu raw headers/keys trong JSON.

### 18.7. Quan sát cả hai hướng và mọi attempt

Trong tests bật Retry:

```text
Client request 1:
  Authorization: Bearer fake-user-token
  X-API-Key: fake-partner-key

Gateway outbound attempt 1:
  [neither raw client credential]
  X-Backend-Api-Key: fake-backend-key

Gateway outbound attempt 2 (nếu policy cho phép):
  [same credential policy, no cross-user mix]

Response:
  [no backend credential/cookie]
```

Nếu backend test record cho thấy **lần retry thứ hai thiếu token** hoặc **gửi token người dùng khác**, phải sửa filter ordering/body caching/authorized-client state trước khi release. Không chỉ assert status 200; cần **số downstream calls và header safety ở mỗi call**.

## 19. Gateway Server Web MVC: cùng nguyên tắc, khác API và security chain

Spring Cloud Gateway Server Web MVC chạy trên **Servlet/WebMvc.fn** chứ không phải Reactor/WebFlux. Nó có các filter tương ứng như `RemoveRequestHeader`, `RemoveResponseHeader` và `TokenRelay` theo tài liệu flavor, nhưng Java DSL không dùng `GatewayFilterFactory`/`GlobalFilter`.

### 19.1. Bảng so sánh triển khai

| Nhóm | Server WebFlux | Server Web MVC |
|---|---|---|
| Starter | `spring-cloud-starter-gateway-server-webflux` | `spring-cloud-starter-gateway-server-webmvc` |
| Routing 5.x | `server.webflux.routes` | `server.webmvc.routes` |
| Security chain | `SecurityWebFilterChain` + `ServerHttpSecurity` | `SecurityFilterChain` + `HttpSecurity` |
| Request context | `ServerWebExchange`/reactive `Mono` | `ServerRequest`/Servlet request |
| Custom filters | `GatewayFilter`/`GlobalFilter` | WebMvc.fn `Before/AfterFilterFunctions`/`HandlerFilterFunction` |
| TokenRelay | WebFlux `TokenRelayGatewayFilterFactory` | MVC `TokenRelay` filter/`tokenRelay(...)` |
| Cookie session | WebFlux `WebSession` + `CookieWebSessionIdResolver` | Servlet `HttpSession` + container/Spring Session |
| OAuth2 Client | Reactive authorized-client APIs | Servlet authorized-client APIs |
| TLS outbound | Reactor Netty HTTP client | Spring Boot `RestClient`/SSL bundles theo release |
| Rate limiting | Reactive `RequestRateLimiter`/RedisRateLimiter | MVC `RateLimiter`/Bucket4j ở docs 5.x |

### 19.2. Route MVC xóa credential tương đương

```yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: mvc-public
              uri: http://localhost:8081
              predicates:
                - Path=/api/public/**
              filters:
                - StripPrefix=2
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie
                - RemoveRequestHeader=X-API-Key
                - RemoveResponseHeader=Set-Cookie
```

Với Java DSL WebMvc.fn có thể dùng `BeforeFilterFunctions.removeRequestHeader` và `AfterFilterFunctions.removeResponseHeader` theo docs phiên bản. **Không copy** bean `BackendApiKeyGatewayFilterFactory` WebFlux ở mục 11 vào MVC và gọi nó sẽ hoạt động. Phải viết một MVC filter tương đương, nhận credential từ provider, kiểm soát routing/headers và lifecycle Servlet/RestClient riêng.

### 19.3. Security MVC là Servlet

```java
@Bean
SecurityFilterChain mvcSecurity(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/actuator/health").permitAll()
            .requestMatchers("/api/private/**").authenticated()
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));
    return http.build();
}
```

Đây là **mảnh method** chỉ minh họa Servlet security API, cần imports, Maven dependencies và JWT issuer/audience decoder đúng version. Không dùng `SecurityWebFilterChain` hoặc Reactor `WebSession` trong MVC. Với browser cookies, CSRF/session config phải được xét theo Spring Security Servlet, không tắt toàn cục để làm POST thử nghiệm chạy được.

### 19.4. `TokenRelay` MVC không có nghĩa mọi JWT được auto-forward hợp lệ

Docs Gateway Server MVC có `TokenRelay` filter và tham số optional `clientRegistrationId`. Nhưng authorization client store, security filter chain và token acquisition là **Servlet OAuth2 Client integration**, không phải ReactiveOAuth2AuthorizedClientService của WebFlux. Test:

- Registration ID có đúng và authorized client có token không?
- Token có audience/scopes tương ứng backend?
- Có duplicate Authorization header hay token tự khai bị override ngoài ý định không?
- User logout/token refresh trên nhiều replicas xử lý như thế nào?
- Backend có chỉ nhận token ở các routes được phê duyệt?

### 19.5. Test parity không được dựa vào tên filter

Hai Gateway cùng có `RemoveRequestHeader=Authorization` nhưng **thứ tự filter, exception mapping, security chain, connection pool và cookie handling** khác nhau. Hãy test với **cùng HTTP mock downstream**:

1. Anonymous/invalid/valid token tới mỗi Gateway.
2. Public route không forward token/cookie.
3. Protected route chỉ forward credential đúng audience.
4. Retry và fallback không rò key.
5. TLS/mTLS không fail-open.
6. Cache/response headers không lộ session.

**Không suy Gateway MVC “thiếu bảo mật” chỉ vì không dùng Reactor**, và cũng không suy một YAML WebFlux có thể copy 1:1 qua MVC.

## 20. Chẩn đoán sự cố credential leakage hoặc auth mismatch

| Triệu chứng | Nguyên nhân ưu tiên | Kiểm tra và sửa |
|---|---|---|
| Public route gửi Bearer token tới backend | Thiếu `RemoveRequestHeader`/filter order | WireMock verify header absent |
| Backend nhận hai `X-Backend-Api-Key` | `AddRequestHeader` với client header có sẵn | Remove spoofed input + `SetRequestHeader` từ provider |
| Gateway 200 nhưng backend có raw cookie | Cookie forwarding mặc định chưa bị lọc | Route-specific cookie allowlist/strip |
| OAuth2 `TokenRelay` bean không xuất hiện | Thiếu OAuth2 Client/registration | Đọc Gateway flavor docs, authorized-client config |
| TokenRelay hoạt động nhưng backend 401 | Sai `aud`/`scope`/token type | IdP token claims và backend validator |
| 401 trước khi `RemoveRequestHeader` chạy | Spring Security đã reject inbound bearer | Tách security test và header strip test |
| TokenRelay lấy nhầm user token | Auth context/authorized-client cache scope | Per-user/per-tenant store, test concurrency |
| Backend 403 dù Gateway đã cho phép | Backend resource authorization khác | Kiểm tra ownership/tenant, không bypass backend |
| Browser không lưu session cookie | Secure/SameSite/Domain/Path/HTTPS | Inspect Set-Cookie và reverse proxy TLS scheme |
| Browser gửi cookie nhưng POST 403 | CSRF token thiếu hoặc role/scope sai | Test CSRF separately from authorization |
| Logout không vô hiệu phiên | Chỉ xóa cookie, server session còn sống | Invalidate store, authorized-client lifecycle |
| Cookie gửi mọi subdomain | Domain quá rộng | Host-only cookie/`__Host-` prefix |
| Response public phát `Set-Cookie` nội bộ | Backend leak cookie, thiếu response filter | RemoveResponseHeader per route |
| Redirect chứa `?access_token=` | Upstream tạo URL chứa secret | Sửa upstream flow, validate Location |
| Key có trong Gateway route Actuator | Secret hardcoded vào route filter args | Chuyển sang provider và hạn chế Actuator |
| Trace có JWT/headers | Wiretap/APM baggage capture | Redaction at source, retention/audit |
| `429` không phân biệt tenants | KeyResolver dùng anonymous/raw spoofable header | Authenticated consumer ID/tenant key |
| Retry POST gây side effect trùng | Thiếu idempotency và retry policy | Per-method policy + backend dedupe |
| Cache trả dữ liệu sai user | Shared cache không partitioned | `no-store` hoặc safe cache key/invalidation |
| Filter internal key trả 503 | Secret provider unavailable/expired | Fail closed, alert/rotation |
| mTLS backend handshake fail | Missing CA/client cert/SNI | Kiểm tra outbound TLS, không trust-all |
| Một số replicas dùng key cũ | Rotation propagation drift | Audit credential version per replica |
| Header spoof vượt auth | Backend tin `X-User` do client đặt | Strip + signed identity or mTLS trust |
| Ingress tự tin client IP sai | `trusted-proxies` quá rộng | Allowlist trusted hops + sanitize Forwarded |
| Route admin tạo đích tùy ý | Dynamic routing thiếu RBAC/URI allowlist | Route policy, egress restrictions, audit |
| 404/403 khác nhau giữa Gateway WebFlux/MVC | Property namespace/filter/security stack khác | Version/flavor-specific config + integration tests |

### 20.1. Quy trình điều tra từng tầng

1. **Client:** status, route/path, loại credentials đã gửi (chỉ ghi loại, không raw value).
2. **Ingress:** TLS termination, forwarded headers, client IP trust.
3. **Spring Security:** authentication success/failure, scope/audience, session/CSRF.
4. **Gateway Route:** predicates, route ID, matched URI, default vs route-specific filters.
5. **Outbound HTTP:** backend thực nhận path/method/headers/body nào? Có raw client credential không?
6. **Backend auth:** backend validate issuer/audience/ownership/service credential hay chỉ tin internal header?
7. **Response:** Set-Cookie/Location/Cache-Control/WWW-Authenticate/error body có secret không?
8. **Operations:** logs, traces, retries, cache, multi-replica secret versions và Actuator exposure.

Nếu credentials đã lộ, **đừng chỉ xóa log rồi coi như an toàn**: revoke/rotate, điều tra mức truy cập, xác định bản sao trong backups/telemetry và xử lý sự cố theo chính sách tổ chức. Phân biệt **false positive** (test token giả trong fixture) với production secret thực, nhưng không chủ quan khi logs được gửi ra hệ thống bên thứ ba.

### 20.2. Những cách “sửa nhanh” cần tránh

- Bỏ JWT signature/audience validation để chấm dứt 401.
- Tắt CSRF toàn bộ vì browser POST trả 403, trong khi ứng dụng dùng cookie session.
- Bật `Access-Control-Allow-Origin: *` cùng credentials hoặc reflect Origin bất kỳ.
- Bật trust-all TLS để che lỗi certificate.
- Tạo key dự phòng hardcoded trong JAR.
- Bỏ `RemoveRequestHeader=Authorization` trên public route chỉ vì một backend khác cần token.
- Bật global `TokenRelay` cho mọi route mà không đánh giá audiences.
- Ghi toàn bộ headers/JWT vào log để debug.
- Mở Actuator route write trên Internet để cập nhật cấu hình nhanh.
- Trả 200 fallback với dữ liệu user không được phân quyền.

## 21. Vận hành, review và phản ứng khi nghi ngờ rò credential

### 21.1. Trước khi release

Một thay đổi route/filter/secret policy phải được review bởi **owner của route, owner của backend và bảo mật/identity** nếu đổi trust boundary:

| Thay đổi | Ai cần phê duyệt | Test bắt buộc |
|---|---|---|
| Thêm `TokenRelay` vào route | OAuth2/IdP + backend owner | Audience/scope, token store, negative tests |
| Thêm backend API key | Secret owner + backend owner | No client spoof, no cross-route leak, rotation |
| Thay cookie `Domain/SameSite` | BFF/frontend/security owner | Browser flows, CSRF, logout |
| Bật response cache | Privacy/security + API owner | Cross-user/tenant isolation |
| Mở route mới tới `lb://service` | Gateway platform + backend owner | URI allowlist, mTLS, authz |
| Thay `trusted-proxies` | Ingress/network security | Spoofed headers, redirects, client IP |
| Thay retry/fallback | Backend/domain owner | Call counts, idempotency, no credential leak |

Không coi “unit tests xanh” là đủ cho một thay đổi routing/credential; cần integration test qua HTTP và inspect downstream request.

### 21.2. Canary và rollback

Một rollout an toàn có thể:

1. Deploy Gateway candidate với filter/security policy mới sang canary replicas.
2. Gửi synthetic requests chứa tokens/keys giả; verify outbound headers và logs.
3. Test client A/B ở hai tenants, nhận 401/403/no-leak theo contract.
4. Cho một tỉ lệ traffic thấp theo route ít rủi ro.
5. So 401/403/429/5xx, p95/p99, backend auth failures, KeyProvider status, mTLS errors và token renewal rates.
6. **Rollback ngay** nếu có unauthorized forwarding, cross-tenant cache leak, wrong-audience TokenRelay hoặc secrets trong logs.
7. Sau rollback, đánh giá liệu credentials đã lộ có cần revoke/rotate; rollback binary **không tự thu hồi token** đã gửi sai.

Khi có WebSocket sessions đang mở, rollback router không tự chuyển TCP connections đã established; có thể cần client reconnect và revoke session ở backend nếu có dấu hiệu lộ.

### 21.3. Incident response khi key/token bị lộ

Quy trình đề xuất:

```mermaid
flowchart TD
    DET["Detect leak: logs / backend / monitoring"] --> CON["Contain: stop route or egress"]
    CON --> REV["Revoke affected keys/tokens / sessions"]
    REV --> ROT["Issue rotated credentials"]
    ROT --> AUD["Audit use, routes, logs, copies"]
    AUD --> FIX["Fix filters / cache / trust boundary"]
    FIX --> TEST["Run positive + negative integration tests"]
    TEST --> ROLL["Canary + monitor + close incident"]
```

**Không xóa bằng chứng cần thiết cho điều tra** ngoài retention/privacy policy; xử lý log artifacts có credential theo quy trình bảo mật và quyền truy cập giới hạn. Nếu lộ signing private key hoặc mTLS private key, phạm vi rotate/revoke lớn hơn một API key; xem xét certificate chains, clients và downstream systems bị ảnh hưởng.

## 22. Bài tập thực hành có tiêu chí đạt

Toàn bộ bài tập dành cho **project Gateway lab và credentials giả**; không gọi endpoints production hoặc cố truy cập tài khoản, tenant, secret store ngoài quyền. Một bài được coi đạt chỉ khi **client assertions và backend request verification** cùng đúng.

### Bài 1 — Phân loại credentials

Cho các giá trị:

```text
Authorization: Bearer <user-access-token>
Cookie: __Host-GWSESSION=<random-id>
X-API-Key: <partner-key>
X-Backend-Api-Key: <orders-service-key>
X-Internal-Role: admin
```

Phân loại: do ai phát hành, ai được sử dụng, nơi lưu, thời hạn, cơ chế xác minh và route nào được phép chuyển tiếp. **Đạt** khi giải thích rõ raw client API key và backend service key không đồng nhất, `X-Internal-Role` là dữ liệu không tin cậy nếu client gửi.

### Bài 2 — Route public không forward credential

Dựng WireMock backend và Gateway route `/api/public/**` với `StripPrefix=2`, `RemoveRequestHeader=Authorization`/`Cookie`/`X-API-Key`. Gửi request có các headers giả. **Đạt** khi client 200 theo stub, backend nhận đúng `/items/42` và không còn bất cứ header credential nào trong denylist.

### Bài 3 — Header spoofing

Client gửi `X-Authenticated-User: admin` và `X-Backend-Api-Key: attacker-value`. Thêm custom filter lấy key backend từ provider. **Đạt** khi backend không nhận những giá trị client giả, chỉ nhận **một** header key server-controlled. Trình bày tại sao dùng `AddRequestHeader` dễ gây header confusion.

### Bài 4 — JWT issuer/audience

Tạo JWT test đã ký cho các trường hợp: đúng `iss/aud/exp`, sai issuer, sai audience, expired, `nbf` trong tương lai. Dùng Spring Security Resource Server thật trong môi trường test. **Đạt** khi invalid cases trả 401 và mock backend có **zero calls**; valid token được xử lý tiếp theo scope/route.

### Bài 5 — Scope và ownership

User A/B đều có `SCOPE_orders:read`, nhưng request `/orders/{id}` thuộc user khác. Gateway có thể cho qua do scope hợp lệ; backend phải kiểm tra ownership. **Đạt** khi user A không đọc dữ liệu user B, và test chứng minh authorization vẫn được thực hiện tại backend.

### Bài 6 — TokenRelay với authorized client

Dựng OAuth2 Client registration test có token scoped cho catalog API và một route `TokenRelay=...`. Kiểm tra token đúng backend, không xuất hiện ở route public hay payment. **Đạt** khi audience/scope phù hợp và browser/caller không nhận lại access token trong response. Nêu khác biệt giữa TokenRelay và token exchange.

### Bài 7 — BFF session cookie

Dùng `CookieWebSessionIdResolver` với cookie `__Host-GWSESSION`, `Secure`, `HttpOnly`, `SameSite=Lax` và `Path=/`. Kiểm thử:

1. Browser nhận Set-Cookie đúng attributes trên HTTPS lab.
2. Cookie không chứa raw access/refresh token.
3. Backend không nhận cookie phiên Gateway qua BFF route.
4. Logout/timeout làm session invalid phía server.

**Đạt** khi cookie không thể đọc bằng JS giả lập và mọi state-changing request có CSRF/session policy phù hợp.

### Bài 8 — CSRF và CORS độc lập

Giả lập POST từ origin hợp lệ nhưng không có CSRF token trong ứng dụng dùng session cookie: kết quả phải bị từ chối theo security contract. Gửi preflight OPTIONS được phép và Origin không nằm allowlist. **Đạt** khi CORS không được hiểu là login/authorization và CSRF không bị tắt toàn cục để sửa POST 403.

### Bài 9 — Partner API key verification

Thiết kế verifier dùng key ID + secret hash/HMAC, active state, scopes và quota theo consumer ID. Tạo API key test dài đủ entropy. **Đạt** khi revoked/expired key bị chặn, key không xuất hiện trong query/logs/metrics và backend chỉ nhận credential của Gateway.

### Bài 10 — Backend key rotation

Provider test trả `orders-key-v1`, rồi `orders-key-v2`. Backend mock chấp nhận overlap ngắn hạn, sau đó từ chối v1. **Đạt** khi mọi replicas dùng v2 đúng hạn, provider lỗi trả 503 trước downstream call và không có hardcoded fallback key.

### Bài 11 — Response leakage

WireMock trả `Set-Cookie: BACKENDSESSION=...` và `X-Backend-Debug-Token: ...`. Route public xóa hai headers, nhưng route login hợp lệ được giữ Set-Cookie với attributes đúng. **Đạt** khi không dùng blanket removal làm hỏng login và không leak nội bộ trên public responses.

### Bài 12 — Redirect và query secret

Mock backend trả `302 Location` có query chứa token giả. Kiểm tra Gateway/client policy, sửa upstream để dùng flow không truyền token qua URL. **Đạt** khi không có token trong URL/history/logs và redirect external hosts được allowlist.

### Bài 13 — Cache isolation hai users

Tạo hai principal/tenants A/B, response `GET /api/orders/me` trả nội dung khác. Bật cache policy test có kiểm soát. **Đạt** khi A không bao giờ nhận body của B, kể cả request được phục vụ từ cache; với dữ liệu riêng nên kiểm tra `Cache-Control: no-store` và cache bypass.

### Bài 14 — Retry và credentials ở từng attempt

WireMock trả 503 lần đầu, 200 lần hai; chỉ bật Retry cho GET idempotent. Ghi từng request. **Đạt** khi cả hai attempts có đúng backend credential, không raw client key/cookie, và không tạo attempts ngoài policy.

### Bài 15 — CircuitBreaker fallback không lộ request

Cho backend trả 503 để kích hoạt fallback. **Đạt** khi fallback không phản chiếu Authorization, Cookie, API key, exception message hay nội bộ upstream host; không biến auth failure thành 200 chứa dữ liệu nhạy cảm.

### Bài 16 — Outbound TLS/mTLS

Dựng HTTPS backend test với CA/private key lab, route Gateway tới `https://`. Thử trust đúng, hostname mismatch, thiếu CA, thiếu client cert. **Đạt** khi Gateway không fail-open và không bật insecure trust manager.

### Bài 17 — Trusted proxy header spoofing

Client thử tự đặt `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-For` trong lab, còn ingress test hop đáng tin đặt headers chuẩn. **Đạt** khi Gateway dùng đúng proxy allowlist, không tin client IP giả để bypass rate limit/auth.

### Bài 18 — WebSocket handshake

Dùng WebSocket test server đúng protocol. Authenticate handshake bằng session/token được phép, thử Origin hợp lệ/không hợp lệ, unauthorized session và logout. **Đạt** khi unauthorized clients không mở được session, Origin policy đúng, và không đưa tokens trong query strings.

### Bài 19 — Log/trace redaction

Gửi credentials giả có markers dễ tìm `fake-user-token`/`fake-partner-key`/`fake-backend-key` qua lab. Quét sanitized outputs của Gateway, backend, ingress test và trace exporter. **Đạt** khi không có raw values ngoài mock request journal được bảo vệ, chỉ có route IDs/status/decision codes.

### Bài 20 — Test SSRF qua dynamic route

Thiết kế một control plane test có allowlist URI hosts và service IDs. Thử đề xuất route tới destination không nằm allowlist **mà không gửi request thật tới nội bộ ngoài quyền**. **Đạt** khi route creation bị từ chối trước khi traffic/secret injection, kèm audit identity của người đề xuất.

### Bài 21 — So Server WebFlux và Server Web MVC

Cùng mock downstream, lập hai Gateway apps riêng: `SecurityWebFilterChain`/WebFlux `RemoveRequestHeader` và `SecurityFilterChain`/MVC `BeforeFilterFunctions` tương ứng. **Đạt** khi hợp đồng credential isolation như nhau dù Java API/route config khác nhau; có testcase 401/403/response header ở cả hai.

### Bài 22 — Diễn tập key compromise

Giả lập một backend API key test bị lộ trong log fixture. Viết runbook containment → revoke/rotate → audit → fix → integration test → canary. **Đạt** khi có kế hoạch loại key khỏi bản sao logs/backup theo policy, đánh giá requests đã sử dụng key và kiểm tra từng replica nhận key mới.

### Bảng tự đánh giá

| Năng lực | Điều kiện đạt |
|---|---|
| Trust boundaries | Biết credentials của client/Gateway/backend khác nhau |
| JWT | Kiểm tra iss/aud/exp/nbf/scopes và backend resource ownership |
| TokenRelay | Không nhầm raw forward với OAuth2 authorized-client/token exchange |
| Cookie | Secure/HttpOnly/SameSite/Domain/Path + session lifecycle |
| CSRF/CORS | Không coi CORS là auth, không tắt CSRF với cookie session |
| API key | Verify, quota, rotate, không dùng raw key làm log/rate key |
| Backend credential | Server-side provider, route allowlist, fail-closed |
| TLS | HTTPS/mTLS và proxy trust đúng |
| Filters | Remove/SetRequestHeader và response sanitization có test |
| Resilience/cache | Retry/fallback/cache không rò credential hoặc cross-user data |
| Observability | Log/trace/metrics không có raw token/key/cookie |
| CI | Test client response và backend header/call count |
| Incident response | Có revoke/rotate/audit/rollback và trách nhiệm rõ |

## 23. Câu hỏi ôn tập và đáp án định hướng

**1. Vì sao không nên forward toàn bộ request headers từ client tới mọi backend?**  
Vì headers có thể chứa token, session cookie, API key hoặc identity do client giả mạo. Mỗi backend chỉ nên nhận credentials đúng audience và policy.

**2. Vì sao `RemoveRequestHeader=Authorization` không tự xác thực client?**  
Nó chỉ xóa header trên outbound request; Spring Security phải xác thực/authorize ở inbound phase trước khi route.

**3. `TokenRelay` có phải là raw `Authorization` forwarding?**  
Không. `TokenRelay` tích hợp OAuth2 Client/authorized-client token acquisition, còn proxy thông thường có thể giữ raw Authorization nếu không bị filter. Cả hai đều cần audience policy.

**4. Không có OAuth2 Client registration nhưng chỉ thêm `TokenRelay` vào YAML thì sao?**  
Filter bean có thể không được tạo hoặc route không khởi động đúng vì thiếu client setup; Resource Server JWT validation không tự tạo authorized client token.

**5. `TokenRelay=partner-backend` dùng tên gì?**  
Tên OAuth2 **client registration ID**, không tự là Route ID/ServiceInstance ID.

**6. TokenRelay có tự đổi access token của Gateway thành token `aud=payment-api` không?**  
Không được suy như vậy. Muốn đổi audience cần Token Exchange/OBO hoặc flow IdP phù hợp và backend validation.

**7. ID token có nên dùng để gọi Resource Server không?**  
Không. ID token là assertion nhận dạng cho OAuth2/OIDC client; API nên dùng access token được cấp đúng audience/scope.

**8. JWT payload có được mã hóa bí mật không?**  
Không mặc định. JWS JWT payload thường được Base64URL encoding và đọc được; không chứa secrets hoặc PII không cần thiết.

**9. Vì sao xác minh `iss` chưa đủ?**  
Token có thể do issuer đúng phát hành nhưng cấp cho audience khác hoặc thiếu scope. Cần kiểm tra `aud`, expiry, signature, scope và resource ownership.

**10. Gateway đã kiểm tra scope, backend còn phải phân quyền không?**  
Có. Backend biết resource ownership/tenant và phải tự enforce policy của mình, đặc biệt với dữ liệu nhạy cảm.

**11. 401 khác 403 thế nào?**  
401 thường cho thiếu/không hợp lệ authentication; 403 cho principal đã xác thực nhưng không được phép. Contract cụ thể phải được test.

**12. Vì sao API key không nên là giải pháp duy nhất cho tài nguyên có giá trị cao?**  
Key thường xác định app/consumer, dễ bị lộ/replay nếu thất thoát và thiếu user/transaction context. Kết hợp authorization, quota, mTLS/OAuth2 thích hợp.

**13. Vì sao không dùng API key trong query string?**  
URL dễ lộ qua access logs, history, Referer, analytics và caching. Dùng header qua TLS với log redaction.

**14. Có thể lưu một API key random bằng hash không?**  
Có thể lưu secret verifier/hash/HMAC nếu key có entropy đủ mạnh và lookup/rotation an toàn. Hash không cứu một key ngắn, có thể đoán.

**15. Raw partner API key có nên chuyển đến Orders backend không?**  
Không theo mặc định. Gateway xác minh key, quyết định quota/identity; backend nhận service credential hoặc token phù hợp nếu cần.

**16. Vì sao `AddRequestHeader=X-Backend-Api-Key` có thể nguy hiểm?**  
Client đã đặt header có thể khiến backend nhận nhiều giá trị; nếu value nằm trong YAML còn có nguy cơ lộ qua config/Actuator.

**17. Mục đích của `BackendCredentialProvider` là gì?**  
Lấy key được server quản lý, có rotation/expiry, không lấy từ client. Khi thiếu key phải fail closed trước downstream routing.

**18. Có thể đặt secret trong route YAML với `${SECRET}` để coi là an toàn tuyệt đối không?**  
Không. Property resolution tránh hardcode literal nhưng route metadata/config dumps, access control, rotation và exposure vẫn phải được đánh giá. Server-side provider thường phù hợp với secret lâu dài/nghiệp vụ nhạy cảm hơn.

**19. `HttpOnly` có chặn CSRF không?**  
Không. Browser vẫn gửi session cookie khi request được thực hiện. HttpOnly chủ yếu giảm JS access vào cookie.

**20. `Secure` cookie có mã hóa giá trị cookie không?**  
Không. Nó hướng browser chỉ gửi cookie qua secure transport; vẫn phải dùng HTTPS, session IDs an toàn và backend validation.

**21. `SameSite=Lax/Strict` có thay CSRF token không?**  
Không mặc định. Nó là defense in depth và có trade-off với OAuth2 login/cross-site flows.

**22. `__Host-` cookie yêu cầu gì?**  
`Secure`, `Path=/` và không có `Domain`; giúp hạn chế subdomain cookie forgery, không thay session authorization.

**23. Vì sao không forward BFF session cookie xuống tất cả microservices?**  
Cookie thuộc Gateway session trust boundary; backend không cần nó có thể làm lộ session ID nếu logs/compromise. Dùng service identity hoặc scoped backend token.

**24. Nếu Gateway có nhiều replicas, in-memory authorized-client/session store gặp vấn đề gì?**  
Đổi replica có thể làm mất session/token state hoặc tạo logout/login không ổn định. Cần server-side distributed store/consistent policy/rotation nếu sản phẩm yêu cầu.

**25. CORS có xác thực user không?**  
Không. CORS là browser cross-origin policy; non-browser clients có thể gửi requests trực tiếp và có thể giả Origin.

**26. Khi nào preflight OPTIONS cần được Gateway xử lý?**  
Khi browser gửi cross-origin request có method/headers cần preflight. Gateway phải trả CORS headers đúng allowlist mà không mở quyền cho actual request.

**27. mTLS Gateway → backend có thay JWT user authorization không?**  
Không. mTLS xác thực workload/service; user-level permissions vẫn cần token/context đáng tin và backend policy.

**28. Vì sao không dùng `use-insecure-trust-manager` để xử lý TLS failure?**  
Nó tắt certificate validation, mở đường MITM/credential theft. Phải cấu hình CA/hostname/SNI/client cert đúng.

**29. Nếu client tự khai `X-Forwarded-For`, Gateway có thể coi là client IP tin cậy không?**  
Không ngoài chuỗi proxy được kiểm soát. Ingress phải sanitize headers và Gateway dùng trusted-proxy allowlist.

**30. `SecureHeaders` filter có tự xóa access token không?**  
Không. Nó thêm browser security response headers, không phải request credential sanitizer.

**31. Có nên xóa `Set-Cookie` trên mọi response không?**  
Không. Phù hợp route không cần backend cookie, nhưng sẽ phá login/session của route hợp lệ. Cần response policy theo route.

**32. Tại sao `Location: https://...?...token=...` nguy hiểm?**  
Token có thể xuất hiện trong browser history, logs, Referer và website đích. Không truyền credentials qua URLs/redirects.

**33. Tại sao `Cache-Control: no-store` nên có trên private data?**  
Nó yêu cầu HTTP caches không lưu response nhạy cảm; cần xác minh Gateway/CDN không override và không cache sai user/tenant.

**34. `Vary: Authorization` có bảo đảm cache an toàn tuyệt đối không?**  
Không. Cache misconfiguration, key design và storage behavior vẫn có thể làm lộ dữ liệu. Với dữ liệu private, ưu tiên disable shared cache.

**35. Retry có thể làm lộ credential thêm lần nào?**  
Mỗi attempt có thể gửi lại headers/body; cần kiểm soát đích, số tries, expiry, same user/tenant và idempotency.

**36. CircuitBreaker fallback có thể là một kênh lộ secret như thế nào?**  
Nếu fallback phản hồi raw exception, request headers, exchange attributes hoặc gọi một backend không cùng audience.

**37. Vì sao không dùng raw API key làm rate-limit key?**  
Key có thể xuất hiện trong Redis/metrics/logs và client có thể giả key chưa xác thực. Dùng internal consumer ID hoặc keyed hash đáng tin.

**38. WebSocket handshake khác CORS preflight thế nào?**  
WebSocket handshake có Origin nhưng không dùng cùng CORS preflight như fetch; cần authenticate/authorize handshake và origin allowlist.

**39. Khi Bearer token hết hạn giữa SSE/WebSocket session, điều gì xảy ra?**  
Không tự có auth check mỗi frame/event. Ứng dụng phải có policy đóng/kích hoạt re-auth/reconnect và resume được kiểm soát.

**40. Có thể dùng `SecurityWebFilterChain` của WebFlux trong Gateway Server Web MVC không?**  
Không. MVC dùng Servlet `SecurityFilterChain`/`HttpSecurity`; route filter APIs cũng khác.

**41. Vì sao kiểm thử credential leak cần WireMock/MockWebServer?**  
Chúng ghi request thực **sau khi Gateway route/filters chạy**, giúp xác minh header thực tới backend và số downstream calls, không chỉ status phía client.

**42. Tại sao một public route với Bearer giả đôi khi trả 401 trước `RemoveRequestHeader`?**  
Spring Security Resource Server có thể xử lý và reject bearer ở inbound phase dù route `permitAll`; cần tách header hygiene test khỏi authentication test.

**43. Khi secret provider outage, Gateway nên làm gì?**  
Fail closed 503/controlled error đối với route cần key, báo metrics/alert; không gửi thiếu credential hoặc dùng hardcoded fallback.

**44. Khi key bị lộ, rollback Gateway image đã đủ chưa?**  
Chưa. Key/token có thể đã được sao chép hoặc dùng. Cần revoke/rotate, audit, kiểm tra logs/backups/other replicas và incident remediation.

**45. Bảo mật route động cần gì ngoài known service ID?**  
RBAC route management, URI/host allowlist, egress policy, mTLS, filter validation và audit; một tên service hợp lệ không tự bảo đảm người dùng được phép tạo route.

## 24. Checklist bảo vệ credential trên Gateway

### 24.1. Kiến trúc và trust boundaries

- [ ] Mỗi route có owner, backend service ID/URI, security policy và loại client được phép.
- [ ] Có ma trận **client credential → Gateway validation → downstream credential** rõ ràng cho mỗi route.
- [ ] Không mặc định forward mọi `Authorization`/`Cookie`/`X-API-Key` do client gửi.
- [ ] Có allowlist backend destinations, TLS requirements, URI schemes và dynamic route management permissions.
- [ ] Không dùng request headers do client tự khai (`X-User`, `X-Tenant`, `X-Internal-Role`) như identity đã xác thực.
- [ ] Trusted-proxy policy chỉ tin ingress/mesh hops đã xác minh; ingress sanitize forwarded headers.
- [ ] Backend vẫn thực hiện authorization theo resource/tenant, không phụ thuộc duy nhất Gateway.
- [ ] Không để public route/catch-all route shadow route protected do predicate/order sai.

### 24.2. OAuth2/JWT/TokenRelay

- [ ] Spring Security JWT/opaque introspection được cấu hình đúng flavor và Boot release.
- [ ] Validator kiểm tra signature algorithm, issuer, audience, expiration, not-before.
- [ ] Mỗi route enforce scopes/roles/permissions theo HTTP method và dữ liệu nghiệp vụ.
- [ ] Không dùng ID token/refresh token làm bearer API access token.
- [ ] TokenRelay chỉ áp vào routes và OAuth2 client registrations được phê duyệt.
- [ ] Access token được relay đúng audience/scope; nếu cần token exchange, dùng IdP flow được hỗ trợ.
- [ ] OAuth2 authorized-client/session store có ACL, encryption/TTL, rotation và multi-replica strategy.
- [ ] 401/403 failures không tới backend nếu policy Gateway phải chặn.
- [ ] Không đưa token vào query string, `Location` redirects hoặc URL userinfo.

### 24.3. Cookie/session/CSRF/CORS

- [ ] Session cookie có `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain` theo threat model.
- [ ] `__Host-` cookie không có Domain, dùng `Path=/` và `Secure`.
- [ ] Session ID ngẫu nhiên, có idle/absolute expiry, rotation và server-side invalidation.
- [ ] Backend không nhận Gateway session cookie nếu không có contract cho nó.
- [ ] Cookie-based POST/PUT/PATCH/DELETE có CSRF protection thích hợp.
- [ ] CORS chỉ cho phép origins/methods/headers được duyệt; không dùng wildcard trái credential policy.
- [ ] OPTIONS preflight được xử lý theo browser policy nhưng actual request vẫn cần authz/CSRF.
- [ ] Logout thu hồi server session/authorized client, không chỉ xóa browser cookie.
- [ ] Hai ứng dụng có cookie name/Domain/Path overlapping đã được đánh giá rủi ro.

### 24.4. API keys và service credentials

- [ ] API key client có entropy mạnh, expiry/revocation và quota theo consumer được xác thực.
- [ ] Không chấp nhận key trong URL query hoặc logs; raw key không làm Redis/metric labels.
- [ ] Mỗi backend có service credential/permission scope riêng khi cần.
- [ ] Backend credential lấy từ Vault/Secret Manager/provider, không hardcode route YAML/Java.
- [ ] Inbound client `X-Backend-Api-Key` bị xóa; outbound key chỉ có **một giá trị** server-controlled.
- [ ] Không inject service credential trên routes không thuộc backend allowlist.
- [ ] Provider unavailable/expired secret phải **fail closed** và có alert.
- [ ] Secret rotation được kiểm tra trên mọi replicas; old key được revoke đúng hạn.
- [ ] Không gọi blocking remote secrets API trên WebFlux event loop.

### 24.5. TLS, headers, response và observability

- [ ] Client → Gateway và Gateway → backend được bảo vệ bằng TLS theo policy.
- [ ] Certificate hostname, trust CA, mTLS identity, certificate expiry/rotation được test.
- [ ] Không dùng insecure trust manager, không tin arbitrary `Forwarded` headers.
- [ ] Header sanitization diễn ra trước outbound HTTP routing ở mọi route liên quan.
- [ ] `RemoveResponseHeader` chỉ xóa những headers bị cấm, không phá login/cookie flow.
- [ ] `Location` không chứa token/key/secret hoặc dẫn tới host ngoài allowlist.
- [ ] Sensitive responses có `Cache-Control: no-store` và không được shared cache sai user/tenant.
- [ ] `SecureHeaders`/HSTS/CSP/Referrer-Policy được cấu hình theo browser/domain policy.
- [ ] Logs, traces, APM, Netty wiretap, Actuator và metrics không để lộ tokens/cookies/keys.
- [ ] Không dùng raw Authorization/API key/session ID làm correlation ID hoặc metric label.
- [ ] WebSocket/SSE handshake, Origin, token expiration, reconnect được test.

### 24.6. Resilience, testing và vận hành

- [ ] Retry chỉ dành cho methods/failures được phê duyệt, có idempotency policy khi cần.
- [ ] Retry attempts không thay credential audience/user/tenant hoặc gửi tới host lạ.
- [ ] CircuitBreaker fallback/error handler không phản chiếu secrets/exceptions.
- [ ] RateLimiter dùng authenticated principal/consumer ID thay vì spoofable headers.
- [ ] Cache/Retry/TokenRelay/filter ordering đã qua integration tests riêng theo Gateway flavor.
- [ ] Mock downstream kiểm tra **headers và call count**, không chỉ client status.
- [ ] Test có negative cases: missing/invalid token, wrong scope/audience, client header spoof, CSRF/CORS deny.
- [ ] Test có response leakage, redirect, Set-Cookie, key provider outage/rotation.
- [ ] TLS negative cases và forwarded-header spoofing đã được kiểm tra.
- [ ] Kịch bản hai users/hai tenants không lộ response/cached data cho nhau.
- [ ] Route admin/Actuator nhạy cảm có authentication, authorization, network isolation và audit.
- [ ] CI dùng credentials giả, không lưu raw values vào logs/artifacts.
- [ ] Có canary/rollback, revoke/rotate và incident response plan nếu credential bị lộ.

## 25. Tổng kết

Bảo vệ token, cookie, API key và thông tin xác thực phía sau Spring Cloud Gateway trước hết là **thiết kế ranh giới tin cậy theo từng route và backend**. Gateway không nên là “ống dẫn trong suốt” chuyển mọi thứ client gửi vào nội bộ. Nó phải **xác minh inbound identity**, quyết định quyền, **loại credential không cần thiết**, chỉ gắn **credential phù hợp audience/service** và lọc response để không trả ngược secrets cho browser.

Những nguyên tắc cần ghi nhớ:

1. **Token đúng mục đích:** access token khác ID token/refresh token; JWT phải được kiểm tra signature, issuer, audience, expiry và scopes. Backend vẫn enforce resource ownership.
2. **`TokenRelay` không phải phép biến mọi token thành hợp lệ cho mọi backend.** Nếu cần đổi audience, thiết kế OAuth2 Token Exchange/client credentials theo IdP, không giả mạo `Authorization` bằng route header.
3. **Cookie của Gateway là credential của Gateway.** Cookie `Secure`/`HttpOnly`/`SameSite`, session lifecycle và CSRF/CORS cần được thiết kế cho browser; không forward cookie phiên tới mọi backend.
4. **Client API key và backend API key khác nhau.** Xác minh key client trước, strip raw key, lấy service key từ provider có rotation, gắn một giá trị duy nhất trên route đáng tin và fail closed khi mất key.
5. **TLS/mTLS và egress allowlist bảo vệ chặng nội bộ**, còn `RemoveRequestHeader`/`RemoveResponseHeader`, SecureHeaders và security filters bảo vệ các phần khác nhau của HTTP flow. Không một filter đơn lẻ thay toàn bộ security architecture.
6. **Retry, CircuitBreaker, RateLimiter, cache và WebSocket/SSE** thay đổi cách credentials tồn tại và đi qua các requests/connections; không chỉ test “HTTP 200”.
7. **Đo cả hai phía.** Client nhận gì và downstream **thực sự nhận header gì, bao nhiêu lần**; đồng thời chứng minh không có raw token/cookie/key trong logs, traces hoặc response.

Một Gateway an toàn không chỉ **từ chối request sai**, mà còn **không gửi credentials tới nơi không cần chúng**, **không cache/ghi log sai**, và có thể **thu hồi/rotate/audit** khi ranh giới tin cậy bị vi phạm. STEP 4 hoàn thành việc viết kiến thức này; Content QA/refactor chuyên môn, integration tests và security review thực tế là những bước riêng.

## Tài liệu tham khảo chính thức

1. [Spring Cloud Gateway Server WebFlux — TokenRelay GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html) — OAuth2 Client integration, `clientRegistrationId` và authorized-client store.
2. [Spring Cloud Gateway Server Web MVC — TokenRelay Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/tokenrelay.html) — token relay theo Servlet/WebMvc.fn.
3. [Spring Cloud Gateway Server WebFlux — SecureHeaders](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/secureheaders-factory.html) — response browser security headers.
4. [Spring Cloud Gateway Server WebFlux — RemoveRequestHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removerequestheader-factory.html) — loại headers trước proxy routing.
5. [Spring Cloud Gateway Server WebFlux — RemoveResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removeresponseheader-factory.html) — loại response headers.
6. [Spring Cloud Gateway Server WebFlux — HTTP Headers Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html) — Forwarded/X-Forwarded, trusted proxies, hop-by-hop headers.
7. [Spring Cloud Gateway Server WebFlux — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/cors-configuration.html) — Global/route CORS và preflight.
8. [Spring Cloud Gateway — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html) — route/filter namespaces theo Gateway flavor/version.
9. [Spring Cloud Gateway Server Web MVC — Spring Security Integration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/spring-security.html) — Servlet SecurityFilterChain/Resource Server/OAuth2 Client.
10. [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html) — JWT issuer, audience, validators, scopes.
11. [Spring Security — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — Resource Server configuration ở Servlet stack.
12. [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — CSRF protection và reactive setup.
13. [Spring Framework — CookieWebSessionIdResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html) — WebFlux session cookie options.
14. [Spring Session — Reference](https://docs.spring.io/spring-session/reference/) — session lifecycle, Redis and WebFlux/Servlet integrations.
15. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — cookie Secure/HttpOnly/SameSite, session rotation, storage.
16. [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html) — token validation, API keys, HTTP methods, CORS và URL leakage.
17. [OWASP — JSON Web Token Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html) — JWT risks, token claims/storage.
18. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — sensitive data trong logs và audit.
19. [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — rotation, vault, least privilege.
20. [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — URI/host allowlist và network controls.
21. [OAuth 2.0 Token Exchange — RFC 8693](https://www.rfc-editor.org/rfc/rfc8693) — standards-based delegation/token exchange.
22. [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700) — OAuth2 token/redirect/client security.
23. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie) — cookie attributes và prefix `__Host-`.
24. [OWASP — Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/) — baseline xác thực, session, secrets và API security.

> **Ghi chú version và kiểm thử:** Những ví dụ Java/YAML trong bài cần Spring Boot/Gateway/Security BOM tương thích, được chạy trong project lab với backend test và credentials giả trước khi ứng dụng thật sử dụng. `TokenRelay`/`SecureHeaders`/`RemoveRequestHeader`, các namespace config, cookie/session APIs và Web MVC equivalents có thể thay đổi giữa release trains; phải xem tài liệu bản đang dùng. Nội dung này **không thay** vòng QA học thuật STEP 6, kiểm thử tích hợp trên hệ thống thật hay security penetration test đã được ủy quyền.
