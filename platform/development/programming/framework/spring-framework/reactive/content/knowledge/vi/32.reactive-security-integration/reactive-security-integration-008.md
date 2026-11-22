# Phân biệt bảo mật WebFlux với thiết kế hệ thống OAuth2 chuyên sâu

## 1. Vấn đề cần phân biệt

Spring WebFlux là HTTP stack reactive. Spring Security cho WebFlux bảo vệ các HTTP request và Publisher đang chạy trong một ứng dụng. OAuth 2.0 là khung giao thức ủy quyền giữa nhiều hệ thống; OpenID Connect (OIDC) bổ sung tầng xác thực danh tính dựa trên OAuth 2.0.

Bốn phạm vi không đồng nhất:

- **WebFlux security:** request có được vào endpoint không, ai đã authenticated, quyền nào được yêu cầu, security context được truyền thế nào trong Mono/Flux?
- **OAuth2 Resource Server:** API tiếp nhận và kiểm tra bearer access token do nơi khác cấp, rồi áp dụng scope, role và business authorization.
- **OAuth2 Client/OIDC Login:** ứng dụng chuyển người dùng tới Identity Provider để đăng nhập, hoặc xin access token hợp lệ trước khi gọi API khác.
- **Thiết kế authorization platform:** vận hành authorization server, client registration, grant/PKCE, consent, token issuance, refresh, JWKS, revocation, introspection, tenant isolation, audit và high availability.

**Kết luận đầu tiên:** thêm Spring Security và một `SecurityWebFilterChain` giúp bảo vệ API WebFlux nhưng **không tự tạo một OAuth2 Authorization Server**. Ngược lại, xây authorization server tốt không thay thế kiểm tra quyền trên tài nguyên cụ thể của API.

## 2. Vai trò OAuth2 và ranh giới hệ thống

| Vai trò OAuth2 | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Resource Owner | Chủ thể sở hữu/kiểm soát quyền đối với tài nguyên | Người dùng sở hữu đơn hàng |
| Client | Ứng dụng xin quyền truy cập | SPA, BFF, backend service, mobile app |
| Authorization Server | Xác thực/ủy quyền và phát access token | Identity Provider của tổ chức |
| Resource Server | API chứa dữ liệu được bảo vệ và kiểm tra token | Orders API dùng Spring WebFlux |

Luồng tổng quát:

~~~text
  User / Browser
        |
        v
  Client (SPA/BFF)
        | \
        |  \--- Authorization Code + PKCE ---> Authorization Server
        |                                      - Login/MFA
        |                                      - Consent/client policy
        |                                      - Issue/refresh/revoke tokens
        |                                      - JWKS/introspection
        |<---------------- access token ---------|
        |
        | Authorization: Bearer <access-token>
        v
  Gateway (tùy chọn)
        |
        v
  Spring WebFlux Resource Server
    1. Authenticate bearer token
    2. Validate signature/issuer/audience/time
    3. Map scopes to authorities
    4. Authorize route + owner/tenant/resource
        |
        v
    Database / Downstream API
~~~

Một sản phẩm có thể có một authorization server và hàng chục WebFlux resource servers. Không cần mỗi microservice tự phát token. Một `WebClient` gửi HTTP request cũng không tự trở thành OAuth2 client có quyền: nó phải sử dụng một access token được cấp cho đúng resource/audience.

## 3. SecurityWebFilterChain là lớp bảo vệ request

Trong Spring Security reactive, những thành phần chính gồm:

- `@EnableWebFluxSecurity`: bật cấu hình reactive security khi cần.
- `SecurityWebFilterChain`: tổ hợp các WebFilters và quy tắc cho request.
- `ServerHttpSecurity`: DSL cấu hình authorization, resource server, login, CORS/CSRF và các cơ chế khác.
- `ReactiveAuthenticationManager`: xác thực reactive theo provider.
- `ReactiveAuthorizationManager`: quyết định cho phép/từ chối.
- `ReactiveSecurityContextHolder`: truy cập security context qua Reactor Context.
- `@EnableReactiveMethodSecurity` và `@PreAuthorize`: kiểm tra method-level authorization cho các reactive methods.

Ví dụ bảo vệ API theo scope:

~~~java
@Configuration
@EnableWebFluxSecurity
class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .csrf(csrf -> csrf.disable())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                        .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Đây là snippet dành cho **stateless bearer-only API**. Cần cấu hình JWT decoder bằng issuer/JWKS phù hợp. `csrf.disable()` chỉ hợp lý khi ứng dụng không dựa vào cookie/session do browser tự gửi để xác thực request thay đổi trạng thái. Với OIDC login dùng session cookie hoặc BFF, không sao chép cấu hình này một cách máy móc.

### 3.1. Authentication và Authorization khác nhau

- **Authentication:** xác nhận danh tính/credentials của caller. Ví dụ Bearer token hợp lệ xác định subject.
- **Authorization:** quyết định caller có được đọc/ghi tài nguyên hay không. Ví dụ user có scope `orders:read` nhưng không sở hữu order 42 vẫn phải bị từ chối.

Spring Security làm tốt cả hai ở request pipeline; nhưng hệ thống OAuth2 còn định nghĩa **ai cấp token và dựa trên điều kiện nào**.

### 3.2. Reactor Context, không dựa vào ThreadLocal

Một reactive chain có thể đổi thread. Security context được tích hợp qua Reactor Context:

~~~java
Mono<String> currentUser =
        ReactiveSecurityContextHolder.getContext()
                .map(context ->
                        context.getAuthentication().getName());
~~~

Đoạn trên cần được subscribe trong authenticated reactive context. Không giả định `SecurityContextHolder.getContext()` qua ThreadLocal sẽ luôn đúng bên trong `flatMap` hoặc `publishOn`.

### 3.3. Method security

~~~java
@Configuration
@EnableReactiveMethodSecurity
class MethodSecurityConfiguration {
}

@Service
class DocumentService {

    @PreAuthorize("hasAuthority('SCOPE_documents:read')")
    Mono<Document> read(String id) {
        return repository.findById(id);
    }
}
~~~

Đây là snippet minh họa, cần `Document` và `repository` do dự án định nghĩa. `@PreAuthorize` kiểm soát quyền coarse-grained nhưng service vẫn phải kiểm tra ownership/tenant/ACL của từng document.

## 4. OAuth2 không đồng nghĩa với đăng nhập OIDC

| Khái niệm | Trả lời câu hỏi | Đối tượng chủ yếu |
| --- | --- | --- |
| Authentication | Ai đang gọi? | User/service |
| Authorization | Có quyền với tài nguyên không? | Subject + resource |
| OAuth 2.0 | Client nhận ủy quyền truy cập resource thế nào? | Client, authorization/resource server |
| OIDC | Client xác nhận sự kiện đăng nhập/danh tính user ra sao? | OIDC client / Identity Provider |
| Spring Security WebFlux | Quy tắc security thực thi trong reactive request chain thế nào? | WebFlux app |

OAuth2 là delegation framework, không phải một giao thức đăng nhập danh tính đầy đủ. OIDC cung cấp ID token, UserInfo và các cơ chế xác minh danh tính tiêu chuẩn. OAuth2 Login với một số provider có thể tích hợp đăng nhập qua API riêng, nhưng không nên lẫn với OIDC chuẩn.

### 4.1. Access token, ID token, refresh token

| Token | Dùng cho | Không nên dùng để |
| --- | --- | --- |
| Access token | Resource server bảo vệ API | Làm ID token cho client |
| ID token | OIDC relying party/client kiểm tra thông tin login | Làm Bearer access token cho API |
| Refresh token | OAuth2 client xin access token mới | Gọi resource server |

**Không gửi ID token vào API để thay access token.** Audience của ID token là client đăng nhập, không nhất thiết là API. Không gửi refresh token đến resource server. Với public client, refresh token phải được bảo vệ theo policy nâng cao vì thiết bị/browser khó giữ bí mật lâu dài.

## 5. Ba vai trò mà WebFlux thường triển khai

### 5.1. Resource Server: bảo vệ API

Request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJ...
~~~

Resource server xác minh bearer token và áp dụng route/resource policy. Trong Spring WebFlux:

- JWT: `ReactiveJwtDecoder` xác minh chữ ký và claims.
- Opaque token: `ReactiveOpaqueTokenIntrospector` hỏi authorization server.
- `SecurityWebFilterChain` kiểm tra authority/route.
- Business service quyết định resource-level access.

Resource server không phải nơi cấp refresh token hoặc thực hiện OAuth consent.

### 5.2. OAuth2 Client: lấy token để gọi API khác

Spring Security reactive hỗ trợ `ReactiveOAuth2AuthorizedClientManager` và filter cho `WebClient`:

~~~java
@Bean
WebClient oauthWebClient(
        ReactiveOAuth2AuthorizedClientManager manager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                    manager);

    return WebClient.builder()
            .filter(oauth)
            .build();
}
~~~

Đây là snippet tích hợp, cần OAuth2 client registration, authorized-client selection và token provider configuration. Không có nghĩa mọi outbound request tự nhận token; phải bảo đảm token chỉ được gửi tới host/audience phù hợp.

### 5.3. OAuth2/OIDC Login: người dùng đăng nhập

~~~java
@Bean
SecurityWebFilterChain loginChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(e ->
                    e.anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
}
~~~

Snippet minh họa cho ứng dụng login client, không phải authorization server. Nó cần OAuth2 client registration, provider metadata, redirect URI, session handling và những controls liên quan tới browser login.

## 6. Authorization Server thuộc kiến trúc riêng

Authorization Server có thể phải thực hiện:

1. User authentication/federation, MFA và quản lý session.
2. Đăng ký public/confidential client và client authentication.
3. Xác thực redirect URI và grant policy.
4. Authorization Code, PKCE, client credentials, refresh và grant bổ sung.
5. Quản lý scope, consent và quyền ủy quyền.
6. Phát access token, và ID token nếu cung cấp OIDC.
7. Quản lý signing keys, JWKS và key rotation.
8. Cung cấp introspection, revocation, metadata/discovery.
9. Lưu authorization, consent, client data và secrets an toàn.
10. Audit, rate limiting, high availability, threat monitoring và incident recovery.

Trong Spring Security **7**, chức năng Spring Authorization Server đã được đưa vào hệ sinh thái Spring Security. Hướng dẫn authorization server chính thức hiện dùng **Servlet stack** với `HttpSecurity`, `SecurityFilterChain` và `OAuth2AuthorizationServerConfigurer`. Không coi `@EnableWebFluxSecurity` hoặc reactive `SecurityWebFilterChain` là cách tự động tạo authorization server.

| Mối quan tâm | WebFlux Resource Server | Authorization Server |
| --- | --- | --- |
| Nhận Bearer access token | Có | Không phải nhiệm vụ chính |
| Xác minh JWT ký bởi IdP | Có | Cung cấp keys/issuer |
| Introspect token | Là consumer | Cung cấp endpoint |
| Kiểm tra route/scope | Có | Định nghĩa scope policy |
| Kiểm tra owner/tenant trên tài nguyên | API business logic | Định nghĩa trust model |
| Phát access/refresh/ID token | Không | Có |
| Authorization Code + PKCE | Client có thể tham gia | Xác minh code/verifier và cấp token |
| Client registration và consent | Tiêu thụ policy | Quản lý |
| Signing key rotation | Consume JWKS | Quản lý private key và JWKS |
| Revocation endpoint | Có thể gọi | Cung cấp |
| High availability/token-store | API HA | OAuth2 platform HA |

Đơn vị phát hành token có thể là IdP được quản lý hoặc hệ thống tự xây. Đừng chọn viết authorization server chỉ vì API đang dùng WebFlux.

## 7. Authorization Code + PKCE cho người dùng

Luồng tổng quát:

~~~text
Client / Browser                Authorization Server           Resource Server
      |                                |                             |
      | Create verifier/challenge      |                             |
      |--- /authorize ---------------->|                             |
      |    client_id, redirect_uri     |                             |
      |    scope, state, challenge     |                             |
      |<-- Login / Consent ------------|                             |
      |--- Authenticate / Approve ---->|                             |
      |<-- Redirect ?code&state -------|                             |
      |--- /token -------------------->|                             |
      |    code, code_verifier         |                             |
      |<-- Access token ---------------|                             |
      |--- Bearer access token ------------------------------------->|
      |<-- API response ---------------------------------------------|
~~~

Các điều kiện quan trọng:

- `code_verifier` phải đủ ngẫu nhiên và chỉ gắn với một authorization request.
- `code_challenge` thường dùng S256; server kiểm tra verifier ở token endpoint.
- `state` giúp ràng buộc authorization response với request của client.
- `nonce` quan trọng khi OIDC client xác thực ID token theo flow tương ứng.
- `redirect_uri` phải được đăng ký/so khớp chặt, không mở redirect tùy tiện.
- Authorization code nên ngắn hạn, dùng một lần.
- Public client không thể bảo vệ client secret giống backend confidential client.
- Bảo vệ access token khỏi bị lộ qua browser storage, URL và logs.

Không chọn implicit flow hoặc Resource Owner Password Credentials grant làm nền mặc định cho ứng dụng mới. Tuân thủ các hướng dẫn OAuth2 Security BCP và policy nhà cung cấp.

## 8. Client Credentials cho machine-to-machine

~~~text
  Service A                     Authorization Server                   Service B
      |                                  |                                  |
      |-- Client authentication -------->|                                  |
      |   grant_type=client_credentials  |                                  |
      |<-- Access token -----------------|                                  |
      |-- Authorization: Bearer token ------------------------------------->|
      |<-- Response -------------------------------------------------------|
~~~

Client Credentials thường biểu diễn quyền của service/client chứ không phải một user cụ thể. Không tự đặt `sub=user123` để giả vờ có user delegation. Nếu downstream cần user context, thiết kế token relay hoặc token exchange với permission/audience riêng.

Server-to-server client có thể dùng client secret, private-key JWT hoặc mTLS theo mức độ bảo mật; credentials phải ở secret manager/keystore chứ không nằm trong source code và không được log.

## 9. JWT Resource Server: kiểm tra điều gì?

Một JWT gồm ba phần:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Payload ví dụ (không phải token có thể gọi API):

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1820000000,
  "nbf": 1819999000,
  "iat": 1819998900,
  "scope": "orders:read",
  "tenant_id": "tenant-a"
}
~~~

### 9.1. Các validation bắt buộc về mặt thiết kế

1. Chữ ký đúng với public key được tin cậy.
2. Thuật toán ký thuộc allowlist; không tin alg chỉ vì token tự khai.
3. `iss` khớp issuer được cấu hình.
4. `aud` chứa API/resource server này.
5. `exp` chưa hết hạn, `nbf` hợp lệ, clock skew có policy.
6. Token type/profile phù hợp nếu API yêu cầu access-token JWT profile.
7. Scope và authority đáp ứng endpoint.
8. User có quyền với resource và tenant thực tế.

Không chỉ Base64-decode payload rồi đọc claim mà bỏ verify. Token phát cho API A không tự có quyền ở API B dù cùng issuer.

### 9.2. Spring Boot JWT configuration

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          audiences:
            - orders-api
          jwk-set-uri: https://identity.example.test/oauth2/jwks
~~~

Địa chỉ trên là ví dụ. Trong production dùng issuer đáng tin và JWK Set thực. `issuer-uri` phải khớp `iss`; `audiences` kiểm tra `aud`; `jwk-set-uri` khai báo nguồn public keys.

Nếu chỉ khai báo issuer, framework có cơ chế discover metadata/JWKS. Nếu khai báo trực tiếp JWK URI cùng issuer, hệ thống có thể tránh phụ thuộc discovery tại startup nhưng vẫn cần validate issuer. Xác nhận behavior theo Spring Security version và network/HA model.

### 9.3. Scopes chuyển thành authorities

JWT:

~~~json
{
  "scope": "orders:read orders:write"
}
~~~

Spring Security thường ánh xạ thành:

~~~text
SCOPE_orders:read
SCOPE_orders:write
~~~

Do đó:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
.hasAuthority("SCOPE_orders:read")
~~~

Scope, role và ownership là ba lớp khác nhau. `ROLE_ADMIN`, `SCOPE_admin` và `permission:orders:read` không tự tương đương. Khi IdP dùng claim tùy chỉnh, cần converter được kiểm thử để tránh privilege escalation.

### 9.4. 401 và 403

| Status | Nghĩa thường gặp |
| --- | --- |
| 401 Unauthorized | Thiếu/sai/expired bearer token hoặc chưa authenticated |
| 403 Forbidden | Authenticated nhưng không đủ authority/business permission |

Không nên trả 403 cho mọi trường hợp token hỏng; cũng không dùng 200 với body lỗi thay cho HTTP semantics khi không có lý do.

## 10. Opaque token và introspection

Opaque token không yêu cầu API giải mã cấu trúc token. Resource server gọi introspection endpoint để hỏi authorization server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: "\${INTROSPECTION_CLIENT_SECRET}"
~~~

Spring WebFlux sử dụng `ReactiveOpaqueTokenIntrospector`. Server introspection có thể trả `active`, scope, sub, expiry và metadata. Nếu token không active, request bị từ chối.

### 10.1. JWT so với opaque token

| Tiêu chí | JWT verify offline | Opaque introspection |
| --- | --- | --- |
| Xác minh | Local signature + claims/JWKS | Remote introspection |
| Latency | Thường thấp nếu đã cache keys | Phụ thuộc network/IdP |
| Revocation | Có thể trễ đến exp nếu không có check bổ sung | Có thể phản ánh revocation theo policy |
| Payload visibility | JWT payload thường decode được, không mặc nhiên encrypted | Token thường opaque với API |
| Vận hành | Key cache, issuer/audience, rotation | Introspection timeout, cache, rate limits |
| Độ sẵn sàng | API có thể verify khi IdP tạm ngừng nếu keys đã cache | Network dependency rõ hơn |

JWT cũng có thể được introspect nếu IdP hỗ trợ. Phân biệt **format token** với **cách validate token**.

### 10.2. Thu hồi token

- Short-lived JWT giảm cửa sổ lộ token nhưng không tự tạo instant revocation.
- Refresh token rotation/reuse detection giúp giảm rủi ro credential replay.
- Opaque introspection có thể kiểm tra token active theo thời điểm gọi.
- Cache introspection tăng performance nhưng chậm phản ánh revocation.
- Nếu yêu cầu khóa user/token trong vài giây, phải có SLA và kiến trúc riêng, không chỉ một flag Spring.

## 11. WebFlux vừa là Resource Server vừa có thể là OAuth2 Client

Mẫu nhiều microservice:

~~~text
Browser --> API A [Resource Server]
                  |
                  +-- WebClient [OAuth2 Client] --> API B [Resource Server]
                  |
                  +-- Database
~~~

Cần trả lời:

1. API B cần service identity hay delegated user identity?
2. Access token của API A có đúng audience cho API B không?
3. Có được relay token gốc hay phải token exchange?
4. Scopes có nên được thu hẹp?
5. Ai cất refresh token, refresh vào thời điểm nào?
6. Có ngăn token gửi sang host ngoài allowlist khi redirect không?
7. Nếu user bị revoke, token ở downstream còn hiệu lực bao lâu?

**Không relay bearer token tùy tiện.** Một token được phát cho audience A không mặc định hợp lệ tại B. Tách scope và audience cho từng trust boundary; khi cần, dùng token exchange hoặc delegation được IdP hỗ trợ.

`ReactiveOAuth2AuthorizedClientManager` và WebClient filter giải quyết một phần kỹ thuật lấy/gắn token, không thay thế quyền quyết định token nào được gửi cho ai.

## 12. CORS, CSRF, cookie và WebSocket

### 12.1. CORS không phải authentication

CORS là browser policy quyết định JavaScript ở origin khác có thể đọc response hay không. Nó không ngăn curl hoặc backend service gọi API. Preflight OPTIONS có thể không mang cookie; CORS phải được xử lý trước security authentication đối với luồng preflight.

Nếu browser dùng `credentials: "include"`, actual response phải có allowed-origin cụ thể và allow-credentials true; wildcard origin không hợp lệ cho credentialed requests.

### 12.2. CSRF phụ thuộc authentication model

Browser có thể tự gắn session cookies cho request; đó là một yếu tố của CSRF. Stateless bearer-only API có request header Authorization được đặt tường minh có threat model khác.

Không tắt CSRF chỉ vì “dùng OAuth2”: OIDC login với session cookie, BFF hoặc browser forms vẫn có thể cần CSRF protection. CORS không thay thế CSRF.

### 12.3. SPA/BFF/native/machine clients

- **BFF:** backend giữ token, browser giữ session cookie `HttpOnly`/`Secure`/`SameSite`, CSRF defense và session lifecycle.
- **SPA:** public client, Authorization Code + PKCE, kiểm soát XSS và token storage.
- **Native:** system browser/user agent, redirect handling/PKCE, không nhúng confidential secret.
- **Machine:** client credentials và strong client authentication theo policy.

Client secret nằm trong JavaScript SPA hoặc mobile package có thể bị trích xuất. Không coi chúng là confidential clients.

### 12.4. WebSocket và SSE

WebSocket bắt đầu bằng HTTP handshake, nhưng sau upgrade các message không đi qua HTTP request security filter theo cách một request mới sẽ đi qua. Hãy xác thực handshake, kiểm tra Origin và bảo vệ mỗi command/message nhạy cảm khi cần. Không dựa vào CORS để bảo vệ WebSocket.

SSE là HTTP streaming; khi dùng native browser EventSource có hạn chế riêng về custom headers. Không sao chép nguyên bearer header strategy của fetch mà không kiểm tra client transport.

## 13. Non-blocking không làm security tự an toàn

WebFlux tránh blocking event-loop nhưng kiến trúc bảo mật vẫn cần:

- Non-blocking HTTP clients khi introspection/remote policy.
- Timeout, retry có giới hạn và fail-closed behavior.
- TLS trust/hostname validation, mTLS nếu yêu cầu.
- Reactor Context đúng cách, không lạm dụng ThreadLocal.
- Không gọi blocking JDBC/LDAP/SDK trên event-loop.
- Giới hạn rate tới authorization/introspection/JWKS.
- Redact token, cookie, PII khỏi logs.
- Validate authorization với resource/tenant trong service.

Bọc một blocking security SDK bằng Mono mà không dùng scheduler phù hợp vẫn gây blocking. Scheduler cũng không làm một token invalid trở thành hợp lệ.

## 14. Chương trình Java 17+ chạy được: WebFlux Resource Server

Ví dụ này tạo một API **xác minh JWT và áp dụng scope**, nhưng **không cấp token**. Tests dùng Spring Security `mockJwt()` để tập trung kiểm thử phân quyền offline, không cần IdP thật.

Yêu cầu:

- JDK 17+.
- Maven 3.6.3+.
- Spring Boot **4.1.2**.
- Maven Central để tải dependencies lần đầu.

### 14.1. Cấu trúc thư mục

~~~text
webflux-resource-server-demo/
  pom.xml
  src/main/java/example/security/SecurityBoundaryApplication.java
  src/main/java/example/security/ApiSecurityConfiguration.java
  src/main/java/example/security/OrdersController.java
  src/main/resources/application.yml
  src/test/java/example/security/OrdersSecurityTest.java
~~~

### 14.2. pom.xml

Spring Boot 4.1 có các starter rõ tên cho OAuth2 resource server và WebFlux test.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-resource-server-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tên cũ `spring-boot-starter-oauth2-resource-server` vẫn có thể thấy trong dự án cũ, nhưng Boot 4.1 đánh dấu deprecated và ưu tiên starter `spring-boot-starter-security-oauth2-resource-server`.

### 14.3. Application class

**src/main/java/example/security/SecurityBoundaryApplication.java**

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SecurityBoundaryApplication.class, args);
    }
}
~~~

### 14.4. Security configuration

**src/main/java/example/security/ApiSecurityConfiguration.java**

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .csrf(csrf -> csrf.disable())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                        .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:write")
                        .pathMatchers(HttpMethod.GET, "/api/me")
                        .authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Các quy tắc:

- GET /api/public cho anonymous.
- GET /api/orders/{id} cần `SCOPE_orders:read`.
- POST /api/orders/{id} cần `SCOPE_orders:write`.
- GET /api/me cần authenticated.
- Route còn lại deny.
- JWT được resource server kiểm tra.
- CSRF disabled chỉ phục vụ demo stateless bearer-only; không áp dụng nguyên xi nếu thêm cookie login.

### 14.5. Controller

**src/main/java/example/security/OrdersController.java**

~~~java
package example.security;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class OrdersController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/orders/{id}")
    public Mono<String> readOrder(@PathVariable String id) {
        return Mono.just("order:" + id);
    }

    @PostMapping("/orders/{id}")
    public Mono<String> updateOrder(@PathVariable String id) {
        return Mono.just("updated:" + id);
    }

    @GetMapping("/me")
    public Mono<String> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just("user:" + jwt.getSubject());
    }
}
~~~

Endpoint demo không truy cập dữ liệu thật. Ở ứng dụng production, phải kiểm tra user có quyền với ID order cụ thể trước khi trả dữ liệu, ngoài scope check.

### 14.6. Resource server settings

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
          audiences:
            - orders-api
~~~

Issuer này **chỉ là địa chỉ minh họa**, không phải một Identity Provider thật. Spring Security sử dụng nó để xác định nơi lấy keys/metadata khi cần verify JWT thực. Các test bên dưới dùng mockJwt nên không gọi IdP. Nếu muốn chạy end-to-end với token thật, thay issuer bằng IdP thực và bảo đảm `aud`, keys, algorithm, scope đúng.

### 14.7. Test authorization offline bằng WebTestClient

**src/test/java/example/security/OrdersSecurityTest.java**

~~~java
package example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OrdersSecurityTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicRouteWithoutToken() {
        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void protectedRouteRejectsMissingToken() {
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readScopeAllowsRead() {
        client.mutateWith(mockJwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("order:42");
    }

    @Test
    void readScopeCannotWrite() {
        client.mutateWith(mockJwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .post()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void writeScopeAllowsWrite() {
        client.mutateWith(mockJwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:write")))
                .post()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("updated:42");
    }

    @Test
    void principalSubjectVisible() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt.subject("alice")))
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user:alice");
    }
}
~~~

Test `mockJwt` gắn authentication test vào WebTestClient để tập trung vào authorization rules. Nó **không phát JWT được ký thật** và không kiểm chứng cryptographic validation.

### 14.8. Chạy demo

Trong thư mục chứa `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

**Kết quả kỳ vọng phần test summary:**

~~~text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
~~~

Maven console còn có thời gian, logs và các dòng khác nên không khẳng định toàn bộ stdout chỉ gồm dòng trên.

Sau khi app chạy cổng 8080 mặc định:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/orders/42
~~~

Lệnh đầu trả 200 và body `public`. Lệnh sau không có bearer token nên thường trả 401. Demo **không có endpoint /oauth2/token**; để thử JWT thật, cấu hình IdP thực và nhận access token đúng audience/scope.

## 15. mockJwt kiểm thử gì và chưa kiểm thử gì?

| Trường hợp | mockJwt kiểm tra được? | Cần test khác? |
| --- | --- | --- |
| Public route cho anonymous | Có | HTTP integration optional |
| Quy tắc scope read/write, 401/403 | Có | Full-stack integration optional |
| JWT principal/sub ở controller | Có | Claim mapping integration |
| JWT chữ ký RSA/ECDSA | Không | JWT ký thật + decoder |
| `iss` và `aud` validation | Không tự chứng minh | Negative token tests |
| `exp`/`nbf` và clock skew | Không tự chứng minh | Decoder tests |
| JWKS metadata/key rotation | Không | Mock IdP/JWKS server |
| Opaque introspection active/revoked | Không | Stub introspection |
| Authorization Code + PKCE | Không | Browser/IdP end-to-end |
| Cookie/session/CSRF | Không | Browser/security tests |
| Tenant ownership trên database | Không | Business policy tests |

Một hệ thống có thể vượt qua tất cả mockJwt tests nhưng vẫn chấp nhận sai audience do cấu hình decoder. Phải test **policy** và **token validation** tách biệt.

## 16. Token lifecycle và secrets

### 16.1. Access token

Access token là bearer credential. Chọn TTL theo rủi ro, trải nghiệm và khả năng refresh. Không đặt token trong URL, query string, browser logs, tracing span hoặc error response. Dùng HTTPS/TLS, redact header Authorization và kiểm tra destination trước khi chuyển token qua WebClient.

### 16.2. Refresh token

Refresh token thường có lifetime lớn hơn access token và yêu cầu:

- Chỉ cấp cho loại client được phép.
- Lưu trong storage phù hợp với threat model.
- Rotation hoặc sender-constraining khi cần.
- Reuse detection, revocation, logout/session policy.
- Audit theo client/user/device.
- Không tiết lộ qua logs và telemetry.

Resource Server bình thường không giữ refresh token của user. Đó là trách nhiệm token client/authorization server layer.

### 16.3. Signing keys và JWKS rotation

Authorization Server quản lý **private signing key**, resource server cần **public verification keys**:

1. Publish public key mới qua JWKS.
2. Bắt đầu ký token mới bằng key mới theo rotation plan.
3. Giữ key cũ trong khoảng mà token cũ còn hợp lệ.
4. Tôn trọng cache TTL và propagation delay.
5. Ngừng key cũ khi an toàn; có playbook nếu lộ private key.

Không copy private key từ IdP vào các API để “xác minh JWT”. Không để shared secret không cần thiết ở hàng chục services.

### 16.4. Token exchange

Khi API A gọi API B thay mặt user, cần thiết kế audience, scope narrowing, actor/user claims, TTL và audit. Token exchange phải được IdP/authorization server hỗ trợ theo policy. Không để API tự sửa claim JWT rồi ký lại mà không có trust delegation rõ ràng.

## 17. Multi-tenant và authorization trên tài nguyên

JWT có claim tenant hoặc scope đọc không tự chứng minh user được đọc mọi tài nguyên.

Hai lớp kiểm tra:

1. **Coarse-grained:** token hợp lệ, scope/authority đủ để gọi route.
2. **Fine-grained:** resource thuộc tenant và owner/ACL cho phép truy cập.

Ví dụ minh họa:

~~~java
Mono<Order> readOrder(String orderId, Jwt principal) {
    return orderRepository.findById(orderId)
            .filter(order -> order.tenantId()
                    .equals(principal.getClaimAsString("tenant_id")))
            .filter(order -> order.ownerId()
                    .equals(principal.getSubject()))
            .switchIfEmpty(Mono.error(
                    new AccessDeniedException("Not allowed")));
}
~~~

Đây là snippet cần repository/Order thật. Policy owner-only có thể quá chặt với người quản lý; hãy thiết kế delegated roles/tenant membership riêng. Tránh IDOR bằng cách xác minh resource-to-subject relationship trên server, không tin tenant header hoặc ID do client tự đưa.

## 18. Khi thiết kế OAuth2 platform chuyên sâu cần quyết định gì?

| Hạng mục | Quyết định bắt buộc |
| --- | --- |
| Identity | Local account, federation, SSO, MFA, account recovery |
| Clients | Public/confidential, registration, exact redirect URIs |
| Grants | Code+PKCE, client credentials, refresh, device và grant bổ sung |
| Token format | JWT/opaque, claims, scopes, audiences, TTL |
| Signing | Key algorithms, KMS/HSM, JWKS, rotation/recovery |
| Consent | Consent UX, retention, withdrawal, audit |
| Sessions | Logout, session binding, step-up, re-authentication |
| Revocation | Access/refresh revocation, latency SLA |
| Storage | Consents, authorizations, clients, secrets encryption |
| Tenancy | Issuer strategy, tenant routing, isolation |
| Risk | Anti-bot, brute force, phishing, token replay, rate limiting |
| Availability | HA, DB replication, cache, key service dependencies |
| Standards | Metadata, OIDC discovery, OAuth2 RFCs, conformance tests |
| Operations | Monitoring, incident response, access reviews, compliance |

Các tính năng nâng cao tùy threat model: PAR, JAR, mTLS/DPoP sender-constrained tokens, token exchange, FAPI profile, step-up authentication. Không tự bật các tính năng này chỉ vì ứng dụng sử dụng reactive.

## 19. Anti-pattern và cách khắc phục

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Tự ký JWT rồi gọi đó là OAuth2 platform | Thiếu grants, consent, client policies, revocation | Dùng IdP hoặc Authorization Server có chuẩn |
| Dùng ID token cho API | Sai purpose/audience | Dùng access token |
| Chỉ parse JWT payload | Chấp nhận claim giả | Verify chữ ký và claims |
| Kiểm tra chữ ký nhưng bỏ `iss`/`aud` | Token confusion | Validate issuer/audience |
| Có scope là cho đọc mọi record | IDOR, tenant leakage | Resource-level policy |
| Relay token A sang mọi service B | Rò token và sai audience | Token exchange/delegation |
| Lưu client secret trong SPA/mobile | Secret bị trích xuất | Public client + PKCE |
| Tắt CSRF khi còn cookie login | CSRF risk | Phân biệt session và bearer-only |
| CORS wildcard cùng credentials | Browser reject và trust quá rộng | Exact allowed origins |
| Cho phép mọi route mặc định | Endpoint mới có thể không được bảo vệ | Deny by default |
| Mỗi resource server tự làm IdP | Tăng complexity và trust surface | Tách role/ownership |
| Log bearer/refresh tokens | Token leakage | Redaction/secret management |
| Introspection không timeout | API bị treo khi IdP chậm | Resilience và fail-closed |
| JWKS cache không cập nhật | Lỗi khi IdP xoay keys | Rotation/cache policy |
| Chỉ kiểm thử mockJwt | Không phát hiện decoder sai | JWT/JWKS/IdP integration tests |
| Blocking security call trên event-loop | Sụt throughput | Non-blocking call/scheduler bounded |
| Lẫn 401 và 403 | Sai auth semantics | Phân loại authentication/authorization |

## 20. Observability theo từng tầng

**Tầng WebFlux API:**

- 401/403 theo route template và client category.
- JWT decode failures theo loại: signature, issuer, audience, expiry.
- Introspection latency/errors/timeouts.
- Security rule deny decisions theo mã nội bộ.
- JWKS refresh/cache failures.
- Downstream token acquisition failures.
- Event-loop saturation và security call latency.

**Tầng Authorization Server:**

- Login/MFA success/failure và suspicious login.
- Authorization code/token issuance volumes.
- Consent grant/deny.
- Refresh rotation/reuse.
- Revocation requests và thực tế latency.
- Signing key lifecycle.
- Per-client rate limiting và audit.

Không dùng raw token, client secret, PII hoặc URL chứa query nhạy cảm làm log/metric tags. Dùng correlation ID không có credential. Khi IdP lỗi, fail-open authentication thường không phải lựa chọn chấp nhận được.

## 21. Lộ trình triển khai theo độ phức tạp

### Mức 1. Bảo vệ một WebFlux API

- Xác định public/private routes và security chain.
- Chọn authentication mechanism.
- Áp dụng authority/scope, ownership, tenant.
- Viết tests 200/401/403.
- Không cần tự phát token nếu có IdP sẵn.

### Mức 2. Tích hợp OAuth2/OIDC với IdP

- Cấu hình issuer, audience, JWKS hoặc introspection.
- Xây OAuth2 client/login nếu cần.
- Định nghĩa scope/audience cho các downstream APIs.
- Test signature/expiry/issuer/audience và key rotation.
- Kiểm soát CORS/CSRF/cookies, logout và token handling.

### Mức 3. Vận hành authorization platform

- Thiết kế token issuance/grants/client registration.
- Xây consent, refresh/revocation, signing key lifecycle.
- Audit, tenant isolation, high availability, backup.
- Chạy conformance và penetration tests.
- Có runbook cho compromised clients/keys/tokens.

Không tiến tới mức 3 chỉ vì “dự án viết bằng WebFlux”. Chọn quy mô dựa trên vai trò cần sở hữu.

## 22. Checklist production

- [ ] Xác định ứng dụng là resource server, client/login hay authorization server.
- [ ] Dùng `SecurityWebFilterChain`/`ServerHttpSecurity` cho WebFlux, không nhầm servlet `SecurityFilterChain`.
- [ ] Mọi route chưa có rule cụ thể được deny theo mặc định.
- [ ] JWT được validate signature, issuer, audience, exp/nbf và allowed algorithms.
- [ ] Access token dùng cho API, không dùng ID token thay thế.
- [ ] Scopes được map thành authorities đúng hợp đồng IdP.
- [ ] Có ownership/ACL/tenant verification theo từng resource.
- [ ] JWKS/introspection có timeout, cache và rotation strategy.
- [ ] Private signing key thuộc authorization server.
- [ ] Browser public client dùng Authorization Code + PKCE khi phù hợp.
- [ ] Client secrets không nhúng vào SPA/native app.
- [ ] Refresh token có storage, rotation, reuse detection và revocation policy.
- [ ] CORS/CSRF/cookie defenses phù hợp authentication model.
- [ ] Không relay bearer token sang audience khác mà không có policy.
- [ ] Reactive security calls không block event-loop.
- [ ] Security context được truyền đúng qua Reactor Context.
- [ ] Tests mockJwt cho policy và signed-JWT/JWKS/IdP cho validation.
- [ ] Có negative tests: token expired, wrong issuer, wrong audience, missing scope.
- [ ] Có audit, redaction, incident response và rate limiting.
- [ ] Authorization platform có thiết kế riêng cho availability, client lifecycle và token issuance.

## 23. Tự kiểm tra

**Câu 1.** Spring Security WebFlux có tự thành OAuth2 Authorization Server không?

Không. Nó bảo vệ API và hỗ trợ OAuth2 resource server/client/login. Token issuance thuộc authorization server.

**Câu 2.** `SecurityWebFilterChain` khác `SecurityFilterChain` thế nào?

SecurityWebFilterChain thuộc reactive WebFlux; SecurityFilterChain thuộc Servlet security stack.

**Câu 3.** Access token và ID token khác nhau ở đâu?

Access token dành cho resource server; ID token dành cho OIDC client xác minh danh tính/login.

**Câu 4.** Có `SCOPE_orders:read` thì được đọc mọi order?

Không. Vẫn cần kiểm tra ownership/tenant/ACL trên order cụ thể.

**Câu 5.** JWT được kiểm tra bằng gì trong WebFlux?

`ReactiveJwtDecoder` với keys và validators phù hợp.

**Câu 6.** Opaque token được kiểm tra thế nào?

`ReactiveOpaqueTokenIntrospector` gọi authorization server introspection endpoint.

**Câu 7.** Vì sao kiểm tra audience quan trọng?

Để không dùng access token dành cho API khác vào resource server này.

**Câu 8.** 401 và 403 khác nhau thế nào?

401 thường là chưa authenticated hoặc token sai; 403 là authenticated nhưng thiếu quyền.

**Câu 9.** OAuth2 Client có phải nơi phát access token không?

Không. Client xin token từ authorization server để truy cập resource server.

**Câu 10.** PKCE bảo vệ điều gì?

Ràng buộc authorization code với client đã khởi tạo request, chống một số tấn công đánh cắp code.

**Câu 11.** Client Credentials có đại diện người dùng không?

Thường không; đó là grant cho danh tính/quyền của client service.

**Câu 12.** Vì sao chỉ test mockJwt là chưa đủ?

Nó bỏ qua xác minh chữ ký, issuer, audience và JWKS; phải test token/decoder thật.

**Câu 13.** CORS thay thế CSRF protection được không?

Không. CORS là origin policy của browser, còn CSRF liên quan credentials tự gửi như cookies.

**Câu 14.** JWT verify offline có tự thu hồi ngay khi user logout không?

Không. Phải có short TTL hoặc kiểm tra revocation/introspection bổ sung với SLA.

**Câu 15.** Vì sao private signing key không nên nằm ở resource server?

Resource server chỉ cần public verification key; phát hành token thuộc authorization server.

**Câu 16.** Khi nào cần OAuth2 platform chuyên sâu?

Khi sở hữu cả client/grant/PKCE/consent/JWKS/revocation/tenant/HA, thay vì chỉ cần xác minh token bảo vệ một API.

## 24. Tài liệu chính thức và tiêu chuẩn

- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/): Resource Server, Client và OAuth2 Login trên reactive stack.
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder, issuer, JWKS, scope và authorities.
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): introspection và ReactiveOpaqueTokenIntrospector.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/): authorized client manager và WebClient.
- [Spring Security — OAuth2 Login WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): authorization-code login.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): @PreAuthorize và Reactor Context.
- [Spring Security — Testing OAuth2](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): mockJwt, WebTestClient và policy tests.
- [Spring Security — Authorization Server Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/configuration-model.html): Servlet-oriented authorization server, token endpoints và OIDC.
- [Spring Boot — OAuth2 Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): issuer, JWK URI, audiences và client settings.
- [Spring Boot — Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html): Boot 4 resource-server starter và WebFlux test starter.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vai trò và grants.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token sử dụng với HTTP API.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636): Proof Key for Code Exchange.
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint.
- [RFC 7662 — Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active token introspection.
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token JWT profile.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): threat model và security recommendations.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, authentication và UserInfo.

**Ghi nhớ:** Bảo mật WebFlux là xác thực/phân quyền trong reactive request pipeline. WebFlux resource server **nhận và kiểm tra token**, OAuth2 client **xin và sử dụng token**, authorization server **phát hành và quản trị token**. Thiết kế hệ thống OAuth2 chuyên sâu là bài toán client/grant/PKCE/consent/keys/revocation/tenant/HA toàn hệ thống. Dù token hợp lệ, API vẫn phải kiểm tra quyền đối với từng tài nguyên cụ thể.