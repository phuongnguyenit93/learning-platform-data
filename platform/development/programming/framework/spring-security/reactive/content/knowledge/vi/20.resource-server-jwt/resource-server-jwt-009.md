# Đọc Jwt, claim và principal trong Controller hoặc dịch vụ — Spring Security WebFlux Resource Server

## Mục tiêu học tập

Bài thuộc nhóm **Resource Server JWT** trong module **Spring Security - reactive**. Sau khi client gửi `Authorization: Bearer <access-token>`, Spring Security WebFlux cần **xác minh JWT trước** rồi mới chuyển thông tin xác thực vào luồng xử lý HTTP. Ở controller hoặc service, ta thường cần subject (`sub`), tenant, scope/authority, một số claims nghiệp vụ và danh tính của principal để kiểm quyền truy cập dữ liệu.

Có hai cách phù hợp với hai tầng khác nhau:

- **Controller WebFlux:** tiêm `@AuthenticationPrincipal Jwt jwt` khi endpoint dành cho JWT-authenticated user và chỉ cần đọc một số thông tin.
- **Service reactive:** dùng `ReactiveSecurityContextHolder.getContext()` trong publisher `Mono`/`Flux`, kiểm `Authentication` thuộc loại phù hợp rồi lấy `JwtAuthenticationToken.getToken()`, hoặc truyền một object danh tính đã được kiểm tra từ controller xuống service một cách tường minh.

**Không** dùng `SecurityContextHolder.getContext()` kiểu `ThreadLocal` của Servlet để đoán principal trong WebFlux. **Không** đọc raw JWT bằng Base64 rồi tự tin claims. **Không** trả toàn bộ JWT/claims/token value về client.

Sau bài học bạn có thể:

1. Mô tả luồng từ Bearer header qua `AuthenticationWebFilter`, `ReactiveJwtDecoder`, `JwtAuthenticationToken`, Reactor Context rồi tới controller/service.
2. Phân biệt `Jwt` (token đã decode/validate), `JwtAuthenticationToken` (Authentication), `Authentication.getPrincipal()` và `Authentication.getName()`.
3. Đọc `sub`, `iss`, `aud`, `exp`, `iat`, `nbf`, `scope`/`scp` và claim custom `tenant_id` bằng API có kiểu dữ liệu phù hợp.
4. Biết `getClaimAsString`, `getClaimAsStringList`, `getClaimAsMap`, `getClaimAsInstant`, `getAudience`, `getSubject` hoạt động thế nào khi claim vắng hoặc sai kiểu.
5. Dùng `@AuthenticationPrincipal Jwt` trong annotated controller, và `ReactiveSecurityContextHolder`/`JwtAuthenticationToken` trong service với publisher lazy.
6. Phân biệt **claim thô** với **GrantedAuthority**; mặc định scope trở thành `SCOPE_<scope>`, còn roles/tenant chỉ có khi converter/policy định nghĩa.
7. Thực hành app **Java 17+, Spring Boot 3.3.13, WebFlux + Spring Security Resource Server** với endpoint thông tin user và kiểm quyền sở hữu đơn hàng.
8. Dùng `WebTestClient` và `mockJwt()` kiểm controller, service, scope, tenant; dùng `StepVerifier` chứng minh Reactor Context, và hiểu mock **không** xác minh JWT signature.
9. Nhận biết thiếu/expired/invalid JWT → 401, đủ danh tính nhưng thiếu scope/tenant → 403, tài nguyên không thuộc chủ sở hữu → 404 theo policy demo.
10. Kiểm issuer, audience, timestamp, key rotation, mapping claims, machine-token vs user-token, token forwarding và multi-tenant isolation trước production.

## 1. Tổng quan: đọc Jwt **sau** khi xác thực

Một request API thường đến dạng:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Đoạn token trong ví dụ chỉ là prefix mô phỏng, không phải token hợp lệ. Resource Server thực hiện:

```text
Browser / Service client
         |
         | Authorization: Bearer <JWT access token>
         v
WebFlux WebFilter chain
         |
         v
Spring Security WebFilterChainProxy
         |
         v
AuthenticationWebFilter / Bearer-token resolver
         |
         v
ReactiveAuthenticationManager
         |
         +-> ReactiveJwtDecoder
         |     - parse JOSE/JWT
         |     - xác minh chữ ký bằng JWK / trusted public key
         |     - kiểm exp, nbf, iss theo cấu hình
         |     - kiểm aud khi app cấu hình validator tương ứng
         |
         v
Jwt -> JwtAuthenticationToken (principal = Jwt)
         |
         v
SecurityContext trong Reactor Context
         |
         v
AuthorizationWebFilter (scope/authority)
         |
         v
DispatcherHandler -> @RestController
         |
         +-> @AuthenticationPrincipal Jwt jwt
         |
         +-> Service -> ReactiveSecurityContextHolder.getContext()
                          -> Authentication
                          -> JwtAuthenticationToken.getToken()
```

**Bất biến bảo mật:** Nếu chưa có một `ReactiveJwtDecoder` hợp lệ xác minh chữ ký/issuer/time/audience theo chính sách, việc “đọc `sub`/`tenant_id`” không tạo ra danh tính đáng tin. Một JWT là dữ liệu **do ai đó đã ký**, không tự động là token dành cho API của bạn.

### 1.1. Đúng lớp, đúng vai trò

| Thành phần | Kiểu Java | Điều nó biểu diễn |
| --- | --- | --- |
| Bearer header | `String` | Credential do client gửi; **chưa tin cậy** |
| `Jwt` | `org.springframework.security.oauth2.jwt.Jwt` | Claims/JOSE headers của JWT đã qua decoder ở flow resource server |
| `JwtAuthenticationToken` | `org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken` | Authentication chứa Jwt và authorities |
| `Authentication.getPrincipal()` | `Object` | Mặc định là `Jwt` khi xác thực bearer JWT thành công; có thể đổi bằng custom converter |
| `Authentication.getName()` | `String` | Mặc định thường lấy `sub`, nhưng có thể được cấu hình lại |
| `GrantedAuthority` | `String getAuthority()` | Quyền do converter/security tạo, ví dụ `SCOPE_orders:read` |
| `SecurityContext` | Spring Security context | Chứa Authentication của subscriber hiện tại |
| `ReactiveSecurityContextHolder` | Reactive API | Cách đọc SecurityContext theo **Reactor Context**, không ThreadLocal |
| `@AuthenticationPrincipal` | Annotation | Lấy principal trực tiếp cho controller method trong scope phù hợp |

**Tránh nhầm:** `Principal` trong Java có thể chỉ hỗ trợ `getName()`; nó không tương đương toàn bộ `Jwt`. `JwtAuthenticationToken` là Authentication, có phương thức `getToken()` và `getTokenAttributes()`. Nếu bạn chỉ cần sub, dùng tên/principal nhất quán; nếu cần JWT claims đã xác minh, lấy token qua API phù hợp.

### 1.2. Resource Server không phải OAuth2 Client

- **Resource Server:** nhận Bearer token, xác minh rồi bảo vệ endpoint.
- **OAuth2 Client / OAuth2 Login:** khởi tạo login, trao code/refresh token với Authorization Server, có thể lưu OAuth2AuthorizedClient.
- **Authorization Server:** phát và ký token.

Thêm `spring-boot-starter-oauth2-resource-server` **không** tự thêm trang đăng nhập OAuth2 hay Token Endpoint. Ngược lại, `@AuthenticationPrincipal OidcUser` dùng cho session-based OIDC Login, **không** phải mặc định cho API Resource Server JWT.

## 2. Jwt gồm những phần nào?

JWT (JSON Web Token) thường là chuỗi gồm ba phần Base64URL:

```text
BASE64URL(JOSE header).BASE64URL(claims payload).BASE64URL(signature)
```

JOSE header ví dụ:

```json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "JWT"
}
```

Claims payload minh họa:

```json
{
  "iss": "https://login.example.test/realms/learning",
  "sub": "subject-7",
  "aud": ["orders-api"],
  "exp": 1794086400,
  "iat": 1794082800,
  "nbf": 1794082800,
  "scope": "orders:read profile",
  "tenant_id": "tenant-a",
  "preferred_username": "alice"
}
```

Các thời gian ở đây là con số minh họa, không phải token hợp lệ. **JWT payload dễ được giải mã** và không được mã hóa bí mật trong JWS thông thường. Không nhét password/secret hoặc dữ liệu nhạy cảm quá mức vào claims.

### 2.1. Các claim chuẩn

| Claim | Ý nghĩa | API đọc |
| --- | --- | --- |
| `iss` | Issuer đã phát token | `jwt.getIssuer()` hoặc `jwt.getClaimAsString("iss")` |
| `sub` | Subject trong phạm vi issuer | `jwt.getSubject()` |
| `aud` | Audience mà token hướng đến | `jwt.getAudience()` |
| `exp` | Expiration timestamp | `jwt.getExpiresAt()` |
| `iat` | Issued-at | `jwt.getIssuedAt()` |
| `nbf` | Not-before | `jwt.getNotBefore()` |
| `jti` | JWT ID, khi provider cung cấp | `jwt.getId()` |
| `scope` | Scope, thường string cách nhau bằng space | `jwt.getClaimAsString("scope")`; converter tạo authorities |
| `scp` | Scope có thể là danh sách | `jwt.getClaimAsStringList("scp")` nếu schema là list |
| `tenant_id` | Claim nghiệp vụ, **không chuẩn OAuth2** | `jwt.getClaimAsString("tenant_id")` nếu provider đã thỏa thuận schema |
| `preferred_username` | Username hiển thị, có thể thay đổi | `jwt.getClaimAsString("preferred_username")` |

**Đừng làm:** `jwt.getClaimAsString("aud").split(",")` để suy audience. `aud` có thể là list, dùng `getAudience()`. Với `scope` dạng string tách bằng dấu cách, dùng converter hoặc tách đúng theo contract, không đoán tự động mọi provider gửi giống nhau.

### 2.2. Thiếu claim và sai kiểu

Các hàm đọc claim có thể trả `null` nếu không tồn tại, và một số phép chuyển đổi có thể ném exception khi dữ liệu không chuyển được. Vì vậy:

```java
String tenant = jwt.getClaimAsString("tenant_id");
if (tenant == null || tenant.isBlank()) {
    // fail-closed nếu đây là dữ liệu bắt buộc cho authorization
}
```

**Không** gọi `Map.of("tenant", jwt.getClaimAsString("tenant_id"))` khi claim có thể null: `Map.of` không cho giá trị null và sẽ ném `NullPointerException`. Trong lớp DTO, có thể để field optional/null khi chỉ hiển thị thông tin; với kiểm quyền, thiếu claim nên bị từ chối.

### 2.3. Không dùng claim tên đẹp làm khóa danh tính

`preferred_username`/`email` có thể đổi hoặc không unique trên nhiều issuer/tenant. `sub` thường là khóa chủ thể ổn định trong phạm vi **issuer**. Với nhiều IdP, dùng cặp `(iss, sub)` hoặc ánh xạ sang internal user ID; không chỉ lấy `sub` trên toàn hệ thống nếu token đến từ nhiều issuers.

Đối với machine-to-machine `client_credentials`, `sub` có thể là **service account** chứ không phải con người. Endpoint `/me` hiển thị principal vẫn có thể hoạt động, nhưng business logic “đơn hàng của tôi” không được mặc nhiên dùng máy như user. Cần phân biệt token user và service token theo issuance policy, audience, scopes và nguồn tin cậy.

## 3. @AuthenticationPrincipal Jwt trong Controller

Cách ngắn gọn nhất cho annotated controller:

```java
@RestController
class MeController {

    @GetMapping("/api/me")
    public MeResponse me(@AuthenticationPrincipal Jwt jwt) {
        return new MeResponse(
                jwt.getSubject(),
                jwt.getClaimAsString("preferred_username"));
    }

    record MeResponse(String subject, String displayName) {}
}
```

Đây là **mảnh minh họa**, không phải full class runnable (cần imports). Spring Security WebFlux resolve `@AuthenticationPrincipal` bằng principal đã có trong Authentication của request. Nếu JWT resource server đang được dùng với converter mặc định, principal là `Jwt`.

**Những giới hạn cần nhớ:**

- Route **phải được bảo vệ** bằng authentication phù hợp; nếu permitAll và request anonymous, tham số có thể null.
- Nếu áp dụng custom principal converter trả object khác Jwt, `@AuthenticationPrincipal Jwt` có thể không nhận đúng kiểu. Test actual security configuration.
- Controller dùng JWT **đã được decoder kiểm**, không tự parse Bearer header bằng Base64.
- `@AuthenticationPrincipal` chỉ giúp lấy principal, không thực hiện authorization ownership. User authenticated vẫn có thể bị cấm tài nguyên khác.
- Với method chỉ làm thao tác CPU nhỏ để chuyển DTO, trả POJO bình thường là được; khi có I/O reactive nên trả `Mono`/`Flux` và không `block()`.
- Không trả `jwt.getTokenValue()` hoặc `jwt.getClaims()` nguyên vẹn cho client.

### 3.1. Chỉ lấy claim cần thiết

Ví dụ:

```java
@GetMapping("/api/profile")
public Mono<ProfileDto> profile(@AuthenticationPrincipal Jwt jwt) {
    String subject = jwt.getSubject();
    String username = jwt.getClaimAsString("preferred_username");

    return Mono.just(new ProfileDto(
            subject,
            username == null ? "" : username));
}
```

Đây là mảnh code, cần định nghĩa `ProfileDto`. Nếu username không tồn tại, trả chuỗi rỗng là lựa chọn **hiển thị** của API, không phải cho phép missing user ID. Với authorization, subject phải được kiểm tra không blank.

### 3.2. Lấy Authentication hoặc JwtAuthenticationToken

Nếu cần authorities cùng lúc với token, một lựa chọn là service-level `ReactiveSecurityContextHolder`. Với controller, WebFlux có các cơ chế inject principal/authentication; tuy nhiên đừng trộn `Principal`, `Authentication`, `Jwt` và `JwtAuthenticationToken` mà không kiểm kiểu runtime.

Nhắc lại:
- `JwtAuthenticationToken.getToken()` trả Jwt.
- `JwtAuthenticationToken.getName()` mặc định phản ánh subject hoặc một claim khác nếu converter đã đổi.
- `JwtAuthenticationToken.getAuthorities()` là quyền đã được mapper đưa vào Authentication.
- `Jwt.getClaims()` là claims thô, không phải security roles đã duyệt.

## 4. ReactiveSecurityContextHolder trong Service

Trong WebFlux, Reactor publisher có thể chạy qua nhiều thread/scheduler. SecurityContext được giữ trong **Reactor Context** đi cùng subscription, không phải một biến `ThreadLocal` toàn cục.

Cách đọc:

```java
public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
```

Đoạn này minh họa lấy name, nhưng **chưa đủ** nếu service bắt buộc chỉ nhận JWT access token có claim tenant: authentication có thể là Basic/form hoặc anonymous ở luồng khác. Trong service quan trọng, nên kiểm loại Authentication, `isAuthenticated()` và claims bắt buộc trước khi dùng.

### 4.1. Một mẫu fail-closed đúng

```java
public Mono<Identity> requireJwtIdentity() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                    new AccessDeniedException("Missing authentication")))
            .flatMap(authentication -> {
                if (!(authentication instanceof JwtAuthenticationToken token)
                        || !authentication.isAuthenticated()) {
                    return Mono.error(new AccessDeniedException(
                            "JWT authentication required"));
                }

                Jwt jwt = token.getToken();
                String subject = jwt.getSubject();
                String tenant = jwt.getClaimAsString("tenant_id");

                if (subject == null || subject.isBlank()
                        || tenant == null || tenant.isBlank()) {
                    return Mono.error(new AccessDeniedException(
                            "Required identity claims missing"));
                }

                return Mono.just(new Identity(subject, tenant));
            });
}
```

Mảnh này cần các imports, record `Identity` và nằm trong class service. Nó minh họa:

- Không dùng `block()`.
- Không tự gọi `subscribe()`.
- Nếu SecurityContext thiếu, tạo `Mono.error` chứ không bỏ qua.
- Nếu Authentication không phải JWT, từ chối thay vì cast bừa.
- Lấy `sub` và `tenant_id` chỉ sau khi token được xác minh trong HTTP resource-server flow.
- Missing subject/tenant gây lỗi authorization, không truy vấn mọi tenant như fallback.
- Chỉ khi đủ thông tin mới trả domain identity đã tối giản.

### 4.2. Vì sao không dùng SecurityContextHolder ThreadLocal?

Ví dụ sai trong WebFlux:

```java
// SAI hoặc không ổn định trong reactive flow.
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

Spring Security Servlet truyền context bằng ThreadLocal cho request xử lý theo thread model riêng. WebFlux/Reactor có thể đổi thread, sử dụng event loop và scheduler. `SecurityContextHolder` có thể trả null, stale context hoặc không phản ánh subscriber hiện tại.

Đúng hơn:

```java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

Trong reactive chain, context thường được Spring Security thiết lập bởi `ReactorContextWebFilter`/security integration, và được truyền qua operator Reactor khi không tách subscription sai cách.

### 4.3. Context mất khi làm việc ngoài subscriber

Cẩn trọng với:

- Gọi `subscribe()` thủ công ở service rồi trả `Mono.empty()`; sub-flow có lifecycle/context riêng.
- Tạo một `Mono` rồi cache/chia sẻ global cho nhiều user; có thể trộn dữ liệu nếu cached value gắn principal.
- Đẩy xử lý sang `CompletableFuture`/callback API không preserve context, rồi cố đọc ThreadLocal.
- Viết một static field giữ Authentication “của request hiện tại”.
- Sử dụng `Context.of(...)` thay thế toàn bộ Reactor Context khi cần merge.
- Gọi `block()` trên event loop và làm treo WebFlux request.

Với Reactor operators chuẩn như `flatMap`, `concatMap`, `publishOn`, context được mang theo subscription theo quy tắc Reactor. Nếu chuyển qua external async library, cần cơ chế context propagation explicit hoặc truyền `Identity` kiểu dữ liệu thường như một đối số.

### 4.4. Truyền Identity tường minh cũng là phương án tốt

Một service thuần nghiệp vụ có thể dùng:

```java
Mono<Order> readOrder(String id, Identity caller);
```

Controller hoặc tầng application boundary xây `Identity` từ JWT đã validated rồi gọi service. Điều này giúp unit test dễ, không khiến mọi service phụ thuộc Spring Security. Nhưng phải đảm bảo `Identity` **chỉ được tạo từ nguồn đã tin** và không đến trực tiếp từ request body/header do client tự sửa.

## 5. Claims khác GrantedAuthority

JWT có thể chứa:

```json
{
  "scope": "orders:read orders:write",
  "tenant_id": "tenant-a",
  "roles": ["viewer"]
}
```

Trong cấu hình Spring Security JWT resource server mặc định, scope hoặc scp thường được chuyển thành các authorities:

```text
SCOPE_orders:read
SCOPE_orders:write
```

Nhưng `roles: ["viewer"]` **không mặc nhiên** trở thành `ROLE_viewer` nếu chưa có mapper phù hợp. Tương tự, `tenant_id` không tự giới hạn SQL query theo tenant.

| Dữ liệu | Nơi xuất hiện | Có đủ để authorize không? |
| --- | --- | --- |
| `jwt.getClaimAsString("scope")` | Claim string thô | Không thay kết quả converter/security |
| `authentication.getAuthorities()` | Danh sách `GrantedAuthority` | Có thể dùng cho scope/role đã mapping |
| `jwt.getClaimAsString("tenant_id")` | Claim nghiệp vụ | Cần kiểm issuer/audience, kiểu dữ liệu và record ownership |
| `jwt.getSubject()` | User/service subject | Xác định ai, không tự cấp quyền đọc record |
| `authentication.getName()` | Principal name đã cấu hình | Không chắc trùng sub/email trong custom converter |
| `jwt.getTokenValue()` | Raw bearer credential | Tuyệt đối không dùng làm mã user, không log/trả response |

### 5.1. Đường kiểm quyền nhiều tầng

```text
GET /api/orders/A-100
  |
  v
Spring Security:
  Bearer token valid?
  -> scope/authorities chứa SCOPE_orders:read?
  |
  v
OrderService:
  subject, tenant_id hợp lệ?
  -> query chỉ record thuộc đúng tenant và owner?
  |
  v
200 (đúng chủ sở hữu)
404 hoặc 403 (không thuộc quyền, theo response policy)
```

**Chỉ có `SCOPE_orders:read` không đủ** để đọc đơn hàng của mọi user. Scope cho phép **loại thao tác**; ownership + tenant bảo vệ **đối tượng dữ liệu cụ thể**. Một token chứa `tenant_id=tenant-a` vẫn phải bị từ chối nếu yêu cầu record thuộc tenant-b.

### 5.2. Cảnh báo về custom roles

Nếu provider dùng `realm_access.roles` hay `resource_access.{client}.roles` (đặc trưng một số IdP), đừng cast raw `Map<String,Object>` thiếu kiểm kiểu rồi coi là ROLE_*. Phải có converter đã được test, issuer/audience validation và policy role mapping. Claim roles từ **access token** khác ID token và có thể không tồn tại tùy provider/client scope.

Trong WebFlux, DSL hỗ trợ:

```java
.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt
                .jwtAuthenticationConverter(
                        reactiveConverter)))
```

Trong đó `reactiveConverter` phải là `Converter<Jwt, Mono<AbstractAuthenticationToken>>` phù hợp. Với một `JwtAuthenticationConverter` đồng bộ có mapper authorities, có thể bọc bằng `ReactiveJwtAuthenticationConverterAdapter`. **Đây là mảnh code minh họa**, không phải biến có sẵn trong project runnable phía dưới.

## 6. Dự án chạy được: Java 17+, Spring Boot 3.3.13, WebFlux JWT

Mục tiêu là có một ứng dụng Resource Server **thực** với `issuer-uri` cấu hình và những endpoint:

| Endpoint | Quy tắc | Nội dung |
| --- | --- | --- |
| `GET /public/ping` | permitAll | Kiểm API sống, không cần JWT |
| `GET /api/me` | authenticated JWT | Đọc Jwt tại controller bằng `@AuthenticationPrincipal` và chỉ trả ba field |
| `GET /api/context` | authenticated JWT | Đọc SecurityContext trong service, yêu cầu `sub` + `tenant_id` |
| `GET /api/orders/{id}` | `SCOPE_orders:read` | Đọc subject/tenant trong service, chỉ trả order của chủ sở hữu |
| Các URL/method khác | denyAll | Không mặc định mở API |

**Cấu trúc:**

```text
webflux-jwt-principal/
  settings.gradle
  build.gradle
  src/
    main/
      resources/application.yml
      java/example/
        JwtPrincipalApplication.java
        SecurityConfig.java
        IdentityController.java
        CurrentJwtService.java
        OrderService.java
        OrdersController.java
    test/
      java/example/
        JwtPrincipalApplicationTests.java
        CurrentJwtServiceTests.java
```

Ví dụ dùng Map in-memory chỉ để minh họa ownership, không phải repository production. Khi dùng R2DBC/DB, hãy **đưa tenant + owner vào WHERE của query** thay vì load record của tenant khác rồi mới lọc sau, đồng thời kiểm policy đối với mọi thao tác cập nhật.

### 6.1. settings.gradle

```groovy
rootProject.name = 'webflux-jwt-principal'
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Chú ý:** Boot starter OAuth2 Resource Server cung cấp các phần phụ thuộc cần thiết, bao gồm cơ chế JWT/JOSE. Không trộn `spring-boot-starter-web` (Servlet MVC) nếu mục tiêu là Netty/WebFlux. Spring Boot BOM quản lý các phiên bản Spring Security, Reactor và Nimbus tương thích.

### 6.3. application.yml

Tạo `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: http://localhost:9090/realms/learning
```

Đây là **issuer demo HTTP localhost**, không phải production. Khi deploy, dùng issuer HTTPS từ IdP thực:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/learning
```

Nếu Keycloak local chưa chạy, các test `mockJwt()` không cần JWT thật nhưng vẫn phải khởi tạo Spring test context. Với cấu hình Boot/Spring Security phổ biến, discovery cho resource server có thể được trì hoãn cho tới JWT request đầu tiên; tuy nhiên khi tùy biến bean decoder eager hoặc nâng version, khởi tạo context có thể cần IdP. Đừng xem test mock là bằng chứng IdP đang sẵn sàng.

### 6.4. JwtPrincipalApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtPrincipalApplication {

    public static void main(String[] args) {
        SpringApplication.run(JwtPrincipalApplication.class, args);
    }
}
```

### 6.5. SecurityConfig.java

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/public/ping")
                        .permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/me", "/api/context")
                        .authenticated()
                        .pathMatchers(
                                HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(withDefaults()))
                .build();
    }
}
```

**Giải thích:**

- `@EnableWebFluxSecurity` kích hoạt WebFlux Security (không phải `@EnableWebSecurity` của Servlet).
- `oauth2ResourceServer(o -> o.jwt(...))` yêu cầu Bearer JWT cho các protected routes.
- `GET /public/ping` permitAll.
- `GET /api/me`, `GET /api/context` yêu cầu Authentication; service còn kiểm loại JWT và claims.
- `GET /api/orders/**` yêu cầu authority `SCOPE_orders:read`.
- `anyExchange().denyAll()` ngăn các route/method ngoài dự định.
- 401/403 được Spring Security xử lý đúng HTTP security flow; không viết `@ExceptionHandler(Exception.class)` đổi mọi lỗi thành 200.
- HTTP Basic và form login **không** được bật; mặc định authentication ở đây là Bearer resource-server.
- Ví dụ không có POST/PUT/DELETE; khi xây API state-changing phải đánh giá CSRF theo kiểu credentials (Bearer trong header, cookie/session…) thay vì tắt vô điều kiện.
- Route pattern cần kiểm thử nếu có reverse proxy/prefix/multiple `SecurityWebFilterChain`.

### 6.6. IdentityController.java: đọc Jwt tại controller

```java
package example;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final CurrentJwtService currentJwtService;

    public IdentityController(CurrentJwtService currentJwtService) {
        this.currentJwtService = currentJwtService;
    }

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "PONG");
    }

    @GetMapping("/api/me")
    public JwtView me(@AuthenticationPrincipal Jwt jwt) {
        // jwt được Spring Security cung cấp SAU khi decoder validate.
        String username = jwt.getClaimAsString("preferred_username");
        String tenant = jwt.getClaimAsString("tenant_id");

        return new JwtView(
                jwt.getSubject(),
                username == null ? "" : username,
                tenant == null ? "" : tenant);
    }

    @GetMapping("/api/context")
    public reactor.core.publisher.Mono<CurrentJwtService.Identity> context() {
        // Không truyền raw token, service đọc Reactor Context.
        return currentJwtService.requireIdentity();
    }

    public record JwtView(
            String subject,
            String preferredUsername,
            String tenantId) {
    }
}
```

**Điểm cốt lõi:**

1. `@AuthenticationPrincipal Jwt jwt` lấy principal từ SecurityContext của request JWT đã validated.
2. `getSubject()` lấy `sub`. `preferred_username` chỉ để hiển thị; không nên làm khóa người dùng bất biến.
3. `tenant_id` thiếu được biểu thị bằng chuỗi rỗng ở **endpoint hiển thị** `/api/me`, nhưng `/api/context` sẽ từ chối nếu claim này bắt buộc.
4. Body **không** chứa `jwt.getTokenValue()`, JOSE signature, raw claims, email/phone hoặc credentials.
5. `/api/context` trả `Mono` và đọc authentication ở service; không lấy thread-local.
6. Không bọc `currentJwtService.requireIdentity().block()` trong controller.
7. DTO record của Java 17 là lựa chọn gọn để định nghĩa API response ổn định.
8. Nếu app tùy biến principal thành một object khác `Jwt`, annotation trên phải được điều chỉnh theo converter; đừng cast bừa.
9. Trong các endpoint permitAll, tham số annotated principal có thể null nếu request không có JWT; endpoint bảo vệ ở ví dụ tránh trường hợp này.

### 6.7. CurrentJwtService.java: lấy JWT trong reactive service

```java
package example;

import java.util.List;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class CurrentJwtService {

    public Mono<Identity> requireIdentity() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .switchIfEmpty(Mono.error(new AccessDeniedException(
                        "Missing authentication context")))
                .flatMap(authentication -> {
                    if (!(authentication instanceof JwtAuthenticationToken token)
                            || !authentication.isAuthenticated()) {
                        return Mono.error(new AccessDeniedException(
                                "JWT authentication required"));
                    }

                    Jwt jwt = token.getToken();

                    String subject = jwt.getSubject();
                    String tenant = jwt.getClaimAsString("tenant_id");

                    if (subject == null || subject.isBlank()
                            || tenant == null || tenant.isBlank()) {
                        return Mono.error(new AccessDeniedException(
                                "Missing subject or tenant claim"));
                    }

                    List<String> authorities = authentication
                            .getAuthorities().stream()
                            .map(GrantedAuthority::getAuthority)
                            .sorted()
                            .toList();

                    return Mono.just(new Identity(
                            subject, tenant, authorities));
                });
    }

    public record Identity(
            String subject,
            String tenantId,
            List<String> authorities) {
    }
}
```

**Giải thích từng bước:**

- `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>`, không đọc từ một static/global variable.
- `map(SecurityContext::getAuthentication)` lấy Authentication của **subscription hiện tại**.
- `switchIfEmpty(Mono.error(...))` fail-closed nếu không có context.
- `instanceof JwtAuthenticationToken token` là pattern matching Java 17, tránh `ClassCastException` do cast sang JWT khi caller có loại authentication khác.
- `token.getToken()` trả `Jwt` mà decoder đã kiểm qua HTTP resource server.
- `sub`/`tenant_id` là claims bắt buộc cho hành vi nghiệp vụ của ví dụ; thiếu thì 403 khi caller đã authenticated và AccessDeniedException được security xử lý.
- Authorities từ `authentication.getAuthorities()` đã qua converter, không phải raw `scope` được split tùy tiện.
- `Identity` được rút gọn: không chứa raw access token, toàn bộ claims hoặc email.
- Không `block()`, không `subscribe()`, không biến `Mono.empty()` thành “permission granted”.
- Nếu cần service thuần nghiệp vụ không phụ thuộc Security API, truyền `Identity` như parameter từ application boundary đã xác minh.

**Vì sao service vẫn kiểm JWT dù URL đã authenticated?** Vì một ngày nào đó có thêm Basic/form/opaque token chain, hoặc service được gọi từ background job/test. Lỗi sẽ fail-closed thay vì âm thầm dùng principal khác.

### 6.8. OrderService.java: bảo vệ tenant + owner

```java
package example;

import java.util.Map;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private final CurrentJwtService currentJwtService;

    private final Map<String, StoredOrder> data = Map.of(
            "A-100", new StoredOrder(
                    "A-100", "tenant-a", "subject-7", "READY"),
            "A-101", new StoredOrder(
                    "A-101", "tenant-a", "subject-8", "PAID"),
            "B-200", new StoredOrder(
                    "B-200", "tenant-b", "subject-7", "PENDING")
    );

    public OrderService(CurrentJwtService currentJwtService) {
        this.currentJwtService = currentJwtService;
    }

    public Mono<OrderView> readOwned(String orderId) {
        return currentJwtService.requireIdentity()
                .flatMap(identity ->
                        Mono.justOrEmpty(data.get(orderId))
                                .filter(order ->
                                        order.tenantId()
                                                .equals(identity.tenantId())
                                        && order.ownerSubject()
                                                .equals(identity.subject()))
                                .map(order -> new OrderView(
                                        order.id(), order.status())));
    }

    private record StoredOrder(
            String id,
            String tenantId,
            String ownerSubject,
            String status) {
    }

    public record OrderView(String id, String status) {
    }
}
```

Đây là **in-memory demo**, không kết nối database, được giữ ngắn để người học tập trung vào JWT/claim/principal. Trong production cần:

```sql
SELECT id, status
FROM orders
WHERE id = :orderId
  AND tenant_id = :verifiedTenantId
  AND owner_subject = :verifiedSubject;
```

Các placeholder SQL ở đây là **bind parameters**, không nối string từ request/JWT để tạo SQL. Với R2DBC, thực thi query reactive và đảm bảo tenant/owner thuộc điều kiện WHERE; không load record của tenant khác rồi mới lọc để tránh lộ dữ liệu hoặc tạo TOCTOU.

Trong demo, token của `subject-7` thuộc `tenant-a` có thể đọc `A-100`; không đọc `A-101` vì owner khác, không đọc `B-200` vì tenant khác. Cùng subject string xuất hiện ở tenant-b nhưng không được coi là cùng quyền. Endpoint trả 404 cho record không có hoặc không thuộc quyền nhằm giảm khả năng dò tồn tại.

### 6.9. OrdersController.java

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    private final OrderService orders;

    public OrdersController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/orders/{id}")
    public Mono<OrderService.OrderView> get(@PathVariable String id) {
        return orders.readOwned(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Order not found")));
    }
}
```

**Phân biệt 401/403/404:**

- JWT thiếu/hỏng/hết hạn → Spring Security 401, **không vào controller**.
- JWT hợp lệ nhưng không có `SCOPE_orders:read` → 403, **không vào OrdersController**.
- JWT hợp lệ và có scope nhưng thiếu `sub`/`tenant_id` bắt buộc → 403 từ service.
- Scope và claims hợp lệ nhưng record không thuộc owner/tenant → 404 theo policy của ví dụ.
- Scope, owner, tenant đều hợp lệ → 200 DTO chỉ có id/status.

**Không viết logic “nếu khác tenant thì bỏ filter, trả toàn bộ data”**. `Mono.empty()` ở repository đọc record có thể là “không tìm thấy”, nhưng không nên dùng `Mono.empty()` thay cho authentication/claim validation failure nếu đó là policy bắt buộc.

## 7. Chạy và quan sát HTTP

### 7.1. Khởi động

Cài JDK 17+, Gradle phù hợp Boot 3.3.13. Từ thư mục dự án:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows sử dụng `gradlew.bat bootRun`. Ứng dụng lắng nghe tại `http://localhost:8080`.

**Lưu ý:** Với `issuer-uri` và decoder auto-configuration, key discovery có thể thực hiện khi token đầu tiên được decode (tùy cách tạo decoder/version). Để thử Bearer token thật, phải có IdP/issuer tương ứng. Các test `mockJwt()` dưới đây không cần tạo access token có chữ ký để kiểm business logic.

### 7.2. Thử route public

```bash
curl -i http://localhost:8080/public/ping
```

Dự kiến status 200 và:

```json
{"message":"PONG"}
```

### 7.3. Thử route bảo vệ không token

```bash
curl -i http://localhost:8080/api/me
curl -i http://localhost:8080/api/context
curl -i http://localhost:8080/api/orders/A-100
```

Với cấu hình Bearer Resource Server, request thiếu credentials thường nhận **401** cùng header challenge `WWW-Authenticate: Bearer`. Nếu gửi một token giả, decoder sẽ từ chối, không tạo principal đáng tin.

### 7.4. Thử với IdP thật (tuỳ chọn)

Có thể chạy Keycloak local để phát access token thật:

```bash
docker run --rm --name keycloak-jwt-lab \
  -p 127.0.0.1:9090:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.8.2 \
  start-dev --hostname=http://localhost:9090
```

Đây là Keycloak **dev mode**, HTTP và admin demo; chỉ dùng localhost. Trong admin console `http://localhost:9090/admin/`:

1. Tạo realm `learning`.
2. Tạo confidential OIDC client có **Client ID** `jwt-demo-machine`, bật client authentication và **Service Accounts Roles / client_credentials**.
3. Sao chép client secret vào môi trường test, không đưa vào Git hoặc frontend.
4. Có thể tạo client scope/mapper để access token chứa `tenant_id=tenant-a` và scope `orders:read` khi muốn thử `/api/context` và `/api/orders/...`. **Keycloak mặc định không tự thêm claims nghiệp vụ tùy ý**; cần cấu hình mapper thực.
5. Nếu token dành cho Resource Server có yêu cầu audience `orders-api`, cần cấu hình audience mapper tại IdP và validator `aud` tại API (xem mục 10).
6. Đảm bảo discovery issuer là `http://localhost:9090/realms/learning`.

Token endpoint:

```text
http://localhost:9090/realms/learning/protocol/openid-connect/token
```

Bản demo machine-token sẽ có `sub` của **service account** do Keycloak cấp, không mặc định là `subject-7` trong fixtures. Vì thế `/api/me` có thể trả danh tính service account; `/api/orders/A-100` **không được kỳ vọng 200** trừ khi policy/fixture thật sự khớp owner và tenant. Đây là hành vi bảo mật đúng, không phải lỗi @AuthenticationPrincipal.

Ở môi trường lab, sau khi cấp token bằng một client HTTP phù hợp, gọi API:

```bash
curl -i -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/me

curl -i -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/context
```

`TOKEN` là biến môi trường chứa access token đã lấy qua giao thức OAuth2, **không phải** string bạn tự tạo hay ID token. Cách truyền token trên dòng lệnh có thể xuất hiện trong process list/history/trace; chỉ phù hợp môi trường test bảo vệ, và không copy token ra log/chat. Production dùng secret/token management an toàn và HTTPS.

Nếu access token không có `tenant_id`, `/api/me` hiển thị tenant rỗng, còn `/api/context` sẽ trả 403 theo policy ví dụ. Nếu app không có audience validation, cần bổ sung trước production; chỉ có issuer validation chưa bảo đảm token được phát **cho API này**.

## 8. Kiểm thử tự động bằng WebTestClient và mockJwt

Để test việc controller/service lấy principal, **không cần phải tạo JWT có chữ ký** cho mọi test. Spring Security Test cung cấp `SecurityMockServerConfigurers.mockJwt()` để đặt một JWT Authentication giả vào WebTestClient.

Điều quan trọng nhất: **`mockJwt()` không chạy ReactiveJwtDecoder, không kiểm signature, issuer, aud, exp hoặc fetch JWKs.** Nó chỉ giúp test authorization logic, controller, SecurityContext/role/claims. Tách nhóm test này khỏi integration tests xác minh token thật.

### 8.1. JwtPrincipalApplicationTests.java

Tạo `src/test/java/example/JwtPrincipalApplicationTests.java`:

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class JwtPrincipalApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicPingIsVisibleWithoutJwt() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("PONG");
    }

    @Test
    void anonymousMeMustAuthenticate() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void meReadsJwtClaimsInController() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a")
                                .claim("preferred_username", "alice")))
                .get().uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("subject-7")
                .jsonPath("$.preferredUsername").isEqualTo("alice")
                .jsonPath("$.tenantId").isEqualTo("tenant-a");
    }

    @Test
    void meDisplaysMissingOptionalClaimWithoutCrash() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claims(claims ->
                                        claims.remove("tenant_id"))))
                .get().uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenantId").isEqualTo("");
    }

    @Test
    void serviceReadsReactorContext() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get().uri("/api/context")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("subject-7")
                .jsonPath("$.tenantId").isEqualTo("tenant-a")
                .jsonPath("$.authorities[0]")
                .isEqualTo("SCOPE_orders:read");
    }

    @Test
    void serviceDeniesMissingRequiredTenant() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claims(claims ->
                                        claims.remove("tenant_id"))))
                .get().uri("/api/context")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void ownerCanReadOwnOrder() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a")
                                .claim("scope", "orders:read"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get().uri("/api/orders/A-100")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("A-100")
                .jsonPath("$.status").isEqualTo("READY");
    }

    @Test
    void sameTenantDifferentOwnerIsNotVisible() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get().uri("/api/orders/A-101")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void sameSubjectDifferentTenantIsNotVisible() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get().uri("/api/orders/B-200")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void missingScopeIsForbiddenBeforeController() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_profile")))
                .get().uri("/api/orders/A-100")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void rawScopeStringIsNotSameAsGrantedAuthority() {
        // Mock deliberately overrides authorities. Demonstrates that
        // authorization checks Authentication authorities, not a raw
        // string returned by getClaimAsString("scope").
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a")
                                .claim("scope", "orders:read"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_other")))
                .get().uri("/api/orders/A-100")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Lệnh:

```bash
gradle test
```

**Lưu ý:** Trong code test trên, import `java.util.List` không được sử dụng; Java không lỗi compile với unused import, nhưng có thể xóa khi áp dụng linter nghiêm ngặt. Đây là test cho **controller, Spring Security HTTP rules, service claims và Reactor Context**, không kiểm độ tin cậy chữ ký của token giả.

### 8.2. Test cho service thuần reactive với StepVerifier

Tạo `src/test/java/example/CurrentJwtServiceTests.java`:

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;

import reactor.test.StepVerifier;

class CurrentJwtServiceTests {

    private final CurrentJwtService service = new CurrentJwtService();

    @Test
    void extractsJwtFromSubscriberContext() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only-token")
                .header("alg", "none")
                .claim("sub", "subject-7")
                .claim("tenant_id", "tenant-a")
                .build();

        Authentication authentication = new JwtAuthenticationToken(
                jwt,
                List.of(new SimpleGrantedAuthority(
                        "SCOPE_orders:read")));

        StepVerifier.create(
                service.requireIdentity()
                        .contextWrite(
                                ReactiveSecurityContextHolder
                                        .withAuthentication(authentication)))
                .assertNext(identity -> {
                    org.junit.jupiter.api.Assertions.assertEquals(
                            "subject-7", identity.subject());
                    org.junit.jupiter.api.Assertions.assertEquals(
                            "tenant-a", identity.tenantId());
                    org.junit.jupiter.api.Assertions.assertTrue(
                            identity.authorities().contains(
                                    "SCOPE_orders:read"));
                })
                .verifyComplete();
    }

    @Test
    void missingContextFailsClosed() {
        StepVerifier.create(service.requireIdentity())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void missingTenantFailsClosed() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only-token")
                .header("alg", "none")
                .claim("sub", "subject-7")
                .build();

        Authentication authentication =
                new JwtAuthenticationToken(jwt);

        StepVerifier.create(service.requireIdentity()
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(authentication)))
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
```

**Tại sao test dùng header `alg=none` mà production không dùng?** Đây là `Jwt` được khởi tạo trực tiếp trong unit test, **không đi qua `ReactiveJwtDecoder`**. Nó chỉ minh họa truyền Authentication qua Reactor Context. Trong production tuyệt đối không cấu hình decoder chấp nhận unsigned JWT hoặc `alg=none`. Test chữ ký/issuer/exp thuộc nhóm integration test riêng.

### 8.3. Test matrix

| Request / scenario | Kỳ vọng | Nơi xử lý |
| --- | --- | --- |
| GET `/public/ping` không token | 200 | Controller |
| GET `/api/me` không token | 401 | Resource Server entry point |
| JWT mock có sub/username/tenant | 200 + DTO | `@AuthenticationPrincipal Jwt` |
| JWT mock thiếu tenant ở `/api/me` | 200 + tenant rỗng | Controller hiển thị, không authorize tenant |
| JWT mock có tenant ở `/api/context` | 200 + Identity | `ReactiveSecurityContextHolder` |
| JWT mock thiếu tenant ở `/api/context` | 403 | Service fail-closed |
| JWT mock đủ scope + owner + tenant cho A-100 | 200 | Security + OrderService |
| JWT mock cùng tenant, khác owner A-101 | 404 | OrderService |
| JWT mock cùng subject, khác tenant B-200 | 404 | OrderService |
| JWT mock thiếu `SCOPE_orders:read` | 403 | AuthorizationWebFilter |
| JWT mock có claim raw scope nhưng authorities bị override khác | 403 | AuthorizationWebFilter |
| Token ký sai, issuer/audience sai, hết hạn | Phải 401 trong E2E | `ReactiveJwtDecoder` + validations; **không** do mockJwt test |

**Lưu ý:** Một số error responses mặc định của Spring Boot/Spring Security phụ thuộc version và `Accept`. Test ở trên chỉ so status, không giả định mọi lỗi 401/403 có body JSON cố định. Nếu API cần ProblemDetail thống nhất, hãy thiết kế `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler` riêng, không phá bearer `WWW-Authenticate`.

## 9. Sự khác biệt giữa Jwt, principal và name

### 9.1. Vì sao `Authentication.getPrincipal()` là Jwt?

Trong Spring Security JWT Resource Server mặc định, sau khi xác minh token, authentication thường là `JwtAuthenticationToken`; principal của nó là `Jwt` và `getName()` thường dựa trên claim `sub`.

```java
JwtAuthenticationToken token = ...;
Jwt jwt = token.getToken();

String subject = jwt.getSubject();
String principalName = token.getName();
```

Đây là **mảnh minh họa**, không phải một block runnable độc lập. Mặc định hai giá trị thường cùng biểu thị `sub`. Nhưng nếu config `JwtAuthenticationConverter.setPrincipalClaimName("preferred_username")`, `token.getName()` sẽ có thể đổi trong khi `jwt.getSubject()` vẫn là subject thật.

**Khuyến nghị:** Lấy **identity key** từ claim ổn định/được issuer xác minh và theo contract của hệ thống; không dựa vào username hiển thị hay tên principal tùy biến khi xác định owner của dữ liệu.

### 9.2. Tùy biến principal name trong WebFlux

Khi thật sự có yêu cầu, có thể khai báo converter cho DSL reactive:

```java
JwtAuthenticationConverter sync = new JwtAuthenticationConverter();
sync.setPrincipalClaimName("preferred_username");

var adapter = new ReactiveJwtAuthenticationConverterAdapter(sync);

// Trong ServerHttpSecurity.oauth2ResourceServer(...):
.jwt(jwt -> jwt.jwtAuthenticationConverter(adapter))
```

Mảnh code trên yêu cầu imports `JwtAuthenticationConverter`, `ReactiveJwtAuthenticationConverterAdapter` và wiring vào security chain. Nó **không** thay validator issuer/audience hoặc tạo tenant permissions; chỉ làm Authentication name lấy từ claim khác. Với tenant isolation, vẫn đọc `sub`/`tenant_id` đáng tin và kiểm access.

### 9.3. Đọc claim nested

Một số IdP phát claims như:

```json
{
  "realm_access": {
    "roles": ["employee", "manager"]
  }
}
```

Có thể dùng:

```java
Map<String, Object> realm =
        jwt.getClaimAsMap("realm_access");

if (realm != null) {
    Object rawRoles = realm.get("roles");
    if (rawRoles instanceof List<?> roles) {
        // Validate type từng phần tử, allowlist role names,
        // rồi map theo policy server.
    }
}
```

Không dùng cast `(List<String>) realm.get("roles")` khi chưa kiểm kiểu dữ liệu; dễ gặp `ClassCastException` hoặc dữ liệu bất thường. Không tự biến mọi role string không giới hạn thành `ROLE_ADMIN` chỉ vì IdP đưa trong payload; cần issuer, audience, client scope và role mapper có kiểm soát.

### 9.4. Lấy Jwt tại phương thức Service có @PreAuthorize

Nếu bật `@EnableReactiveMethodSecurity`, có thể bảo vệ service:

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public Mono<OrderView> findOwned(String id) {
    return currentJwtService.requireIdentity()
            .flatMap(identity -> repository.findOwned(
                    id, identity.tenantId(), identity.subject()));
}
```

Đây là **mảnh minh họa**, giả định có `repository` và `OrderView`. Với reactive method security, phương thức trả `Mono`/`Flux` cần được gọi qua Spring proxy, không tự gọi self-invocation để bypass interceptor. Method security kiểm scope; service vẫn giới hạn tenant/owner. Không dùng `block()` trong SpEL hoặc business pipeline.

## 10. Mô hình trust: signature, issuer, audience, exp và tenant

### 10.1. Đã decode được không có nghĩa được tin

Kẻ tấn công có thể tự tạo JSON:

```json
{
  "sub": "admin",
  "tenant_id": "tenant-a",
  "scope": "orders:read orders:write"
}
```

Sau đó Base64URL encode thành một chuỗi trông giống JWT. Nếu ứng dụng chỉ tách payload rồi tin claims, attacker tự cấp quyền. **Phải dùng `ReactiveJwtDecoder` có verification** trước khi gọi service. Không giải quyết bằng cách “kiểm JWT có đủ ba phần” hoặc chỉ nhìn `alg`.

### 10.2. Spring Resource Server mặc định kiểm gì?

Với `issuer-uri` và trusted JWK, Spring Security resource server thường:

- Xác minh chữ ký JWS/JWK theo thuật toán được phép;
- Kiểm thời gian `exp`/`nbf` (với clock skew mặc định theo phiên bản);
- Kiểm issuer `iss` khớp cấu hình;
- Chuyển scope/scp thành `SCOPE_*` authorities;
- Tạo Authentication dựa trên validated Jwt.

**Điểm quan trọng:** Không mặc định kết luận **audience (`aud`) đã được API kiểm đúng** nếu bạn chỉ cấu hình issuer-uri. Với nhiều Authorization Servers, audience là yêu cầu bắt buộc để ngăn token được cấp cho ứng dụng A bị mang đến API B. Cần validator `aud` hoặc policy provider tương đương được kiểm chứng.

### 10.3. Thêm audience validator theo hợp đồng API

Có thể thay Boot decoder bean bằng cấu hình sau (mảnh class cấu hình đầy đủ):

```java
package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class AudienceDecoderConfig {

    @Bean
    ReactiveJwtDecoder audienceAwareDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withIssuerLocation(issuer)
                        .build();

        OAuth2TokenValidator<Jwt> base =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains("orders-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required API audience missing",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        base, audience));

        return decoder;
    }
}
```

**Đây là cấu hình TÙY CHỌN để thêm khi triển khai API thật**, không bắt buộc cho mockJwt tests với issuer local. Khi tạo bean `ReactiveJwtDecoder` riêng, bạn **thay/ghi đè Boot auto-config**, vì vậy phải giữ validator chuẩn `JwtValidators.createDefaultWithIssuer(issuer)` để không vô tình bỏ exp/nbf/iss. `withIssuerLocation(...)` có thể cần OIDC metadata/discovery từ IdP khi dựng bean, vì vậy test/startup cần IdP hoặc một setup stub phù hợp.

Nếu IdP chưa cấp `aud=orders-api`, các token thật sẽ bị 401 — đó là điều **đúng** cho resource server yêu cầu audience. Cần cấu hình Authorization Server phát đúng audience; **không** xóa validator chỉ để token của dịch vụ khác dùng được.

### 10.4. Issuer + subject khi có nhiều IdP

Nếu app tin nhiều issuers, đừng chỉ xây user key `sub`; dùng `(issuer, subject)`, validate issuer routing và audience riêng cho mỗi source. Multi-tenant authentication có thể cần `JwtIssuerReactiveAuthenticationManagerResolver` hoặc cấu hình nhiều `SecurityWebFilterChain`/manager theo pattern phù hợp. Issuer URI từ token/host/request là **untrusted input cho tới khi policy match**, tránh SSRF khi tùy ý fetch JWK URL do token chỉ định.

### 10.5. Claims không thay dữ liệu hiện tại

Token được ký tại thời điểm phát hành, nhưng quyền có thể thay đổi sau đó:

- User bị xóa/khóa hoặc rời tenant;
- Order được chuyển owner;
- Role admin bị thu hồi;
- Subscription hết hạn;
- Access token còn hợp lệ đến `exp` nhưng policy đã đổi.

Nếu hệ thống cần revocation gần thời gian thực, cân nhắc token TTL ngắn, revocation/introspection, policy check vào DB/cache, token version hoặc event-based invalidation. Không suy rằng JWT tự động phản ánh mọi thay đổi DB ngay sau khi phát token.

## 11. Các lỗi thường gặp và cách sửa

### 11.1. `@AuthenticationPrincipal Jwt` trả null

Nguyên nhân:
- Route permitAll/anonymous nhưng code giả định JWT luôn có;
- Authentication principal đã được custom converter thành kiểu khác;
- Request đang qua Basic/form/opaque token chain;
- Security WebFilterChain không match path;
- Không gửi Bearer token;
- Controller được gọi trực tiếp ngoài security request context trong unit test.

Cách sửa: bảo vệ route, kiểm chain và loại Authentication, dùng mockJwt đúng cách trong WebTestClient. Nếu hỗ trợ nhiều auth types, thiết kế endpoint phân nhánh theo contract thay vì cast bừa.

### 11.2. `jwt.getClaimAsString("tenant_id")` null

Provider có thể chưa phát claim, đặt tên khác, claim nested hoặc token thiếu client scope mapper. Kiểm **access token thật**, không nhầm ID Token. Với query cần tenant, **fail-closed**; đừng đặt tenant mặc định lấy từ request header `X-Tenant` chưa được kiểm.

### 11.3. Đọc `getClaimAsStringList("scope")` bị lỗi

`scope` thường là **một string** với các scope phân tách dấu cách. Với `scp` một số providers gửi list. Dùng đúng API theo schema; authorization nên đọc `GrantedAuthority` đã map bởi Spring, không tự split nhiều kiểu trong mỗi service.

### 11.4. 401 dù JWT có claims “đúng”

JWT có thể expired, `nbf` chưa đến, sai issuer/audience, JWK key chưa được tin cậy, signature không đúng, `alg` không cho phép, token bị truncate hoặc Authorization header không chuẩn. Đọc error category/`WWW-Authenticate`; **không** tự decode JWT và bỏ verification để chạy.

### 11.5. 403 dù JWT xác minh chữ ký thành công

Chữ ký đúng chỉ xác minh nguồn phát. Token có thể thiếu `SCOPE_orders:read`, tenant claim bắt buộc, role mapping hoặc quyền nghiệp vụ. Phân biệt 403 của Security authorization với 403 của service claim validation.

### 11.6. 404 nhưng trong DB có order

Có thể order thuộc user/tenant khác — chính xác chính sách ẩn tài nguyên. Không thay query bằng tìm theo `id` đơn thuần để debug production mà bỏ tenant/owner. Dùng audit log đã redact với request ID và policy result.

### 11.7. `SecurityContextHolder.getContext()` trống trong WebFlux

Đang dùng Servlet ThreadLocal API. Sửa bằng `ReactiveSecurityContextHolder.getContext()` trong publisher hoặc truyền identity tường minh. Không block, không tự subscribe, không cache global Authentication.

### 11.8. Principal name khác subject

Có thể `JwtAuthenticationConverter.setPrincipalClaimName(...)` đã đổi; `getName()` không mặc định luôn là sub trong mọi ứng dụng. Nếu lưu owner ID, quyết định contract dựa trên issuer+subject/internal user ID, không lấy username/email có thể đổi.

### 11.9. Chỉ @PreAuthorize theo scope nhưng vẫn IDOR

Scope cho phép loại hành động, không chứng minh user sở hữu record. Thêm giới hạn tenant/owner trong database query và kiểm resource-specific policy. Tránh chỉ trả entity theo ID từ client.

### 11.10. Test `mockJwt` PASS nhưng Bearer token thật FAIL

`mockJwt` bypass decoder. Cần E2E với IdP/JWK/signature/iss/aud/exp và real HTTP request. Đây không phải lỗi của test; hai nhóm test đo những lớp khác nhau.

### 11.11. Lộ toàn bộ claims trong response

`return jwt.getClaims()` có thể lộ email, phone, internal roles, tenant mapping, session-related claims hoặc thông tin không cần thiết. Trả DTO allowlist field cần cho UI; log/trace cũng redact. Không bao giờ trả `jwt.getTokenValue()`.

### 11.12. Resource Server nhầm ID Token với Access Token

OIDC ID Token dùng để Client xác minh login, không mặc định được gửi như Bearer tới Resource Server. API nên chấp nhận **access token** có audience/scope phù hợp. Nếu decoder chỉ kiểm issuer mà không kiểm audience, một ID Token có thể bị chấp nhận sai theo cấu hình yếu. Bổ sung audience/token purpose validation.

### 11.13. Nhiều service đọc request header Authorization để chuyển tiếp

Không tự truyền raw Bearer JWT của user sang mọi downstream API. Mỗi Resource Server cần audience/scope hợp lệ; token relay phải có trust boundary rõ và có thể cần OAuth2 Token Exchange hoặc một access token khác. Log HTTP client không được in Authorization header.

### 11.14. JSON claim sai kiểu làm lỗi 500

Nếu `tenant_id` ở một issuer là string nhưng issuer khác trả object/list, `getClaimAsString` có thể lỗi/chuyển đổi không như mong đợi. Schema claim phải được thỏa thuận và kiểm khi decode/validation hoặc tại service boundary; trả lỗi có kiểm soát, không lộ stack trace.

### 11.15. `@EnableReactiveMethodSecurity` không có tác dụng

Kiểm bean method được gọi qua Spring proxy, annotation nằm đúng method public, return type reactive, không self-invocation, không cấu hình method security Servlet. Thêm integration tests với security context thực/`mockJwt`.

### 11.16. Token scope có dấu hai chấm hoặc dấu gạch

`SCOPE_orders:read` là tên authority bình thường. Trong SpEL string, nhớ quote literal đúng:

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
```

Dấu `:` không tạo role đặc biệt. `hasRole("ADMIN")` thường tìm `ROLE_ADMIN` và **không tương đương** `SCOPE_orders:read`.

## 12. Kiểm thử JWT thật và phân biệt mức độ tin cậy

### 12.1. Test mockJwt: kiểm business, không kiểm crypto

Các unit/integration tests ở mục 8 mô phỏng Authentication đã thành công. Chúng phù hợp cho:
- URL rules và 403 khi thiếu authority;
- Controller `@AuthenticationPrincipal`;
- Service Reactor Context;
- tenant/owner enforcement;
- contract DTO.

Nhưng chúng **không chạy**:
- Signature verification;
- JWK retrieval/rotation;
- Issuer/audience validation;
- Timestamp/clock skew;
- Token type confusion;
- Certificate/HTTPS verification;
- Token replay/revocation.

### 12.2. Test chữ ký và token endpoint thật

Dùng một IdP test realm hoặc signer test với public JWK phù hợp. Các ca cần có:

| Token | Kỳ vọng |
| --- | --- |
| Signature hợp lệ, issuer đúng, audience đúng, chưa hết hạn | 200 ở endpoint đủ scope và record |
| Signature bị sửa | 401 |
| `exp` trong quá khứ | 401 |
| `nbf` trong tương lai vượt clock skew | 401 |
| Issuer không tin cậy | 401 |
| Audience không chứa API khi validator aud bật | 401 |
| Scope thiếu | 403 ở `/api/orders/**` |
| Tenant thiếu | 403 ở service yêu cầu tenant |
| Owner khác/tenant khác | 404 theo policy |
| JWT dạng unsigned/`alg=none` ngoài test | 401 |
| OIDC ID token không đúng audience/type cho API | 401 khi validator phù hợp |

Không tạo token “giả nhưng có đủ claims” rồi dùng kết quả HTTP 200 làm bằng chứng production an toàn. Hãy xác nhận API sử dụng đúng `ReactiveJwtDecoder`, JWK trust và validators.

### 12.3. Testing reactive context với StepVerifier

Nếu service cần identity của user, test trực tiếp publisher với:

```java
.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authentication))
```

Đây là API Reactor hiện đại; không dùng `subscriberContext` từ ví dụ Reactor rất cũ. Nhớ test thêm **missing context** và **missing tenant** để bảo đảm fail-closed.

### 12.4. Không bao giờ log raw token trong tests

Synthetic token ở `mockJwt()` là dữ liệu giả nên có thể dùng trong bộ nhớ test, nhưng không ghi raw production JWT vào fixtures/CI artifacts. Nếu cần test với token thật, dùng CI secret store và token ngắn hạn, ghi chỉ status/code đã redact.

## 13. Advanced: nhiều identity types và mapping nguyên tắc

### 13.1. Opaque token khác JWT

Với OAuth2 opaque token introspection, Authentication thường là `BearerTokenAuthentication` với `OAuth2AuthenticatedPrincipal` và attributes, **không phải `JwtAuthenticationToken`**. Nếu API hỗ trợ cả hai, nên xây một `CurrentCaller` abstraction được tạo từ từng cơ chế xác thực đã được kiểm chứng, không cast tất cả principal thành Jwt.

Cách tiếp cận an toàn:

```text
JWT access token -> ReactiveJwtDecoder -> JwtAuthenticationToken -> CurrentCaller
Opaque token -> ReactiveOpaqueTokenIntrospector -> BearerTokenAuthentication
             -> CurrentCaller
OIDC Login session -> OidcUser/Auth -> CurrentCaller (policy riêng)
```

Mỗi nhánh có validation và trust semantics riêng. Một service thuần có thể nhận CurrentCaller(subject, tenant, permissions) đã được tạo sau authentication thay vì đọc framework types.

### 13.2. Tách JWT claims, authorities, permissions

Nên chia ba khái niệm:

1. **Claims đã ký**: issuer/sub/audience/tenant/scope.
2. **Authorities của Authentication**: mapper đưa các claims thích hợp thành `SCOPE_*`/`ROLE_*`.
3. **Permissions hiện hành**: chính sách của resource + dữ liệu DB + trạng thái user/tenant tại thời điểm request.

Không lấy raw claim role hay scope từ query parameter. Không để service tùy ý tin `preferred_username` là tenant ID. Với hệ thống multi-tenant, tenant chọn từ URL/header có thể là **requested tenant**, cần đối chiếu với tenant/affiliation được cấp quyền thực tế; không tự tin header `X-Tenant`.

### 13.3. @AuthenticationPrincipal(expression = ...)

Spring Security annotation có thể hỗ trợ SpEL expression trên principal, ví dụ lấy một nested field. Tuy nhiên khi học JWT Resource Server, dùng `@AuthenticationPrincipal Jwt` rồi gọi `jwt.getClaimAsString(...)` rõ ràng hơn, tránh khóa controller vào cấu trúc Map nested và dễ test missing claims. Nếu dùng meta-annotation cho identity đã chuẩn hóa, phải có resolver/converter phù hợp và test với WebFlux chứ không copy Servlet code.

### 13.4. Tránh đóng gói token trong cache global

Không lưu Jwt/Authentication raw vào static field, singleton state hoặc Reactor `cache()` trên publisher dùng chung cho nhiều request. `Jwt` chứa dữ liệu user; cache sai scope có thể làm user B nhìn thấy identity của user A. Khi cần cache authorization decision, key phải gồm issuer+subject+tenant+resource+policy version và TTL phù hợp.

### 13.5. Khi service gọi WebClient downstream

`ReactiveSecurityContextHolder` giúp biết caller nhưng **không tự gửi bearer token** qua WebClient outbound. Chuyển token user sang Resource Server khác đòi hỏi security design:
- API downstream tin issuer/audience của token đó?
- Có cần token exchange/on-behalf-of không?
- Scope có đủ cho downstream?
- Có nguy cơ token bị ghi vào proxy/log?
- Có cần service-to-service client credentials riêng không?

Không tự thêm `Authorization: Bearer jwt.getTokenValue()` cho mọi URL do client kiểm soát; rủi ro SSRF/token leakage. Khi đúng use case token relay, dùng security integration có kiểm soát endpoint/destination.

## 14. Checklist production

1. JWT được giải mã và **verify signature** bằng `ReactiveJwtDecoder` phù hợp; không tự parse Base64 làm auth.
2. Chỉ tin issuer/algorithms/JWK từ nguồn được cấu hình; không fetch arbitrary JKU/JWKS URL do token tự chỉ.
3. Bật issuer validation, exp/nbf; quản lý clock skew và key rotation.
4. **Audience validation** đúng API; không nhận nhầm ID Token hoặc token cho service khác.
5. Thống nhất claim schema: `sub`, `tenant_id`, `scope`/`scp` và kiểu dữ liệu.
6. Đọc `@AuthenticationPrincipal Jwt` khi controller có đúng JWT Authentication; kiểm null/kiểu ở route đa cơ chế.
7. Trong service dùng `ReactiveSecurityContextHolder` hoặc truyền Identity đã chuẩn hóa, không dùng Servlet `SecurityContextHolder`.
8. Không `block()`/`subscribe()` thủ công trong request reactive.
9. Dùng `GrantedAuthority` để kiểm scope/role đã được mapper xử lý, không tin raw string từ client.
10. Kiểm resource ownership/tenant ở service/DB query, không chỉ ở HTTP route.
11. Thiếu claim bắt buộc phải fail-closed; không tự fallback tenant.
12. Không đưa `Jwt.getTokenValue()`, toàn bộ claims, email hoặc token headers vào JSON/log/metrics.
13. Phân biệt subject người dùng và service account, và user token vs client credentials token.
14. Khi role/user state thay đổi cần hiểu JWT có độ trễ đến khi hết hạn hoặc có revocation strategy.
15. Bảo vệ 401/403 đúng semantics Bearer; không catch-all trả 200/500 và bỏ `WWW-Authenticate`.
16. Có test negative tenant khác, owner khác, scope thiếu, token sai issuer/audience/exp/signature.
17. `mockJwt()` test authorization logic nhưng luôn có **E2E decoder tests** với token ký thật.
18. Nếu nhiều issuers, key user theo issuer+sub và isolate trust policies.
19. Nếu dùng proxy/gateway, không tin authentication headers/claims do bên ngoài tự gắn nếu chưa qua trusted auth boundary.
20. Nếu triển khai Kafka/background job, Reactor Context từ HTTP không tự lan sang mọi task; truyền immutable verified identity hoặc dùng service principal riêng.
21. Khi nâng version Spring Boot/Spring Security, kiểm lại converters, claims coercion, WebFlux argument resolver và security chain selection.
22. Chạy load/regression tests tránh token/identity leak do reactive caching/context propagation.

## 15. Câu hỏi tự kiểm tra

**1. `Jwt` và `JwtAuthenticationToken` khác nhau thế nào?**  
Jwt chứa token/claims/headers đã qua decoder. JwtAuthenticationToken là Authentication gồm Jwt, authorities và name.

**2. Controller dùng annotation nào để lấy Jwt mặc định?**  
`@AuthenticationPrincipal Jwt jwt` trên method parameter của controller WebFlux.

**3. Trong service reactive phải dùng API nào để đọc SecurityContext?**  
`ReactiveSecurityContextHolder.getContext()` trong một publisher `Mono`/`Flux`, không dùng Servlet ThreadLocal `SecurityContextHolder`.

**4. JWT payload Base64URL đọc được có đáng tin chưa?**  
Chưa. Phải verify signature/issuer/time/audience và policy token qua decoder trước.

**5. Claim `tenant_id` thiếu thì nên làm gì ở service cần tenant?**  
Fail-closed; ví dụ phát `AccessDeniedException`, không coi là toàn bộ tenant.

**6. `getSubject()` tương ứng claim nào?**  
`sub`.

**7. `Authentication.getName()` có luôn bằng email/username không?**  
Không. Mặc định JWT thường là `sub`, nhưng principal claim converter có thể đổi; email/username không chắc ổn định.

**8. Claim `scope` có tự trở thành `ROLE_*` không?**  
Không. Mặc định scope thường thành `SCOPE_*`, còn roles phải qua mapper riêng.

**9. Vì sao có `SCOPE_orders:read` vẫn không được đọc order A-101?**  
Vì scope chỉ cho loại thao tác, order A-101 thuộc owner khác; service phải kiểm chủ sở hữu.

**10. Subject giống nhau nhưng tenant khác có phải cùng quyền không?**  
Không. Identity/permission phải xét tenant và issuer, resource ownership.

**11. Token chưa được xác thực hoặc không có Bearer thường trả gì?**  
401 từ resource server entry point khi endpoint protected.

**12. JWT hợp lệ nhưng thiếu `SCOPE_orders:read` ở `/api/orders/A-100`?**  
403.

**13. JWT hợp lệ, scope đủ, nhưng record thuộc user/tenant khác?**  
Demo trả 404 để không tiết lộ sự tồn tại của record ngoài quyền.

**14. Vì sao `mockJwt()` không chứng minh certificate/JWK/signature đúng?**  
Vì nó tạo Authentication giả trong test, bỏ qua `ReactiveJwtDecoder`.

**15. `Jwt.getTokenValue()` có nên trả vào response `/api/me` không?**  
Không. Nó là bearer credential có thể được dùng gọi API.

**16. Khi IdP gửi `scp` là list, có nên gọi `getClaimAsString("scope")` rồi split không?**  
Không. Cần đọc đúng claim name/type và/hoặc dùng Spring authority mapping.

**17. Vai trò của audience validation là gì?**  
Đảm bảo access token được phát **cho API này**, không chỉ do cùng issuer ký.

**18. JWT có `preferred_username=admin` có chứng minh user là admin không?**  
Không. Đây là claim hiển thị, không tự tạo ROLE_ADMIN hoặc quyền nghiệp vụ.

**19. Có nên lưu Authentication trong static field để service khác đọc nhanh không?**  
Không. Gây trộn context/identity và rò rỉ quyền giữa requests.

**20. Khi WebClient outbound gọi API khác, Reactor Context có tự đính bearer token vào request không?**  
Không. Token relay/client credentials phải cấu hình có chủ đích và đúng audience/scope.

**21. Vì sao Identity trong service không chứa raw Jwt?**  
Để giảm quyền truy cập và dữ liệu nhạy cảm, làm domain logic/test rõ ràng hơn.

**22. Nếu app có nhiều issuers, chỉ dùng `sub` làm khóa global có an toàn không?**  
Không đảm bảo. Dùng issuer+subject hoặc internal mapping, isolate validators.

**23. Cách xử lý sai khi `getClaimAsStringList` nhận kiểu dữ liệu khác?**  
Không cast mù quáng hoặc nuốt exception thành quyền; kiểm schema/mapper và fail-closed.

**24. JWT access token có phải ID Token của OIDC Login không?**  
Không. ID Token nhằm xác minh user tại client, Resource Server cần access token đúng audience/scope.

**25. Vì sao cần test trên token thật dù controller tests đã pass?**  
Để xác minh cryptographic signature, issuer, audience, expiry/JWK và integration hành vi real HTTP Bearer.

**Ghi nhớ:** Trong **Spring Security WebFlux Resource Server JWT**, Controller có thể đọc principal qua `@AuthenticationPrincipal Jwt`, còn service reactive đọc `Authentication` bằng `ReactiveSecurityContextHolder`. Phải đọc **Jwt đã validated**, giữ ranh giới giữa raw claims và authorities, kiểm **sub + tenant + resource ownership**, fail-closed khi thiếu claim bắt buộc, không block event loop và **không lộ raw bearer token**. Kết hợp `mockJwt`/`StepVerifier` với test decoder/JWK thật để vừa kiểm nghiệp vụ vừa kiểm bảo mật.

## Tài liệu tham khảo

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): cấu hình issuer, Jwt authentication, scope authorities, audience validation, claim conversion.
- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/): resource server, OAuth2 client và JWT support.
- [Spring Security — Reactive JWT testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, authorities, `JwtAuthenticationToken` và giới hạn test.
- [Spring Security — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context, `@PreAuthorize` và reactive method security.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain` và `ServerHttpSecurity`.
- [Spring Security 6.3 — Jwt API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/jwt/Jwt.html): token value, subject, claim methods, JOSE headers.
- [Spring Security 6.3 — ClaimAccessor API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/core/ClaimAccessor.html): typed claim extraction và missing claims.
- [Spring Security 6.3 — NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): decoder, validator, JWK.
- [Spring Framework — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): subscription context và propagation.
- [OAuth 2.0 Bearer Token Usage — RFC 6750](https://www.rfc-editor.org/rfc/rfc6750): Authorization Bearer, `WWW-Authenticate` và lỗi 401/403.
- [JSON Web Token — RFC 7519](https://www.rfc-editor.org/rfc/rfc7519): registered claims, sub/iss/aud/exp/iat/nbf.
- [JWT Best Current Practices — RFC 8725](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, audience/issuer, trust boundaries.
- [Keycloak — Getting Started on Docker](https://www.keycloak.org/getting-started/getting-started-docker): demo IdP local/realm/client configuration.
