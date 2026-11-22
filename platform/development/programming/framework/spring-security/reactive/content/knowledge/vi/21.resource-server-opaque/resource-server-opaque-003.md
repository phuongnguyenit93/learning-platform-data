# Cấu hình introspection-uri, client-id và client-secret

> **Module:** Spring Security - reactive. **Mục:** Resource Server Opaque. Bài hướng dẫn cấu hình OAuth 2.0 Opaque Token Resource Server bằng **Spring WebFlux, Spring Security 6.5.x, Spring Boot 3.x, Java 17+**. Trọng tâm là chính xác ba thuộc tính `introspection-uri`, `client-id`, `client-secret`, cơ chế RFC 7662, xác thực Bearer, scope authorities, xử lý lỗi, bảo mật secret và kiểm thử. Domain `example.test` và mọi credential trong ví dụ chỉ là dữ liệu minh họa, không phải IdP hoạt động.

## 1. Kết quả học tập

Người học cần làm được:

1. Hiểu opaque access token khác JWT: không tự trích claims đáng tin nếu chưa xác minh.
2. Phân biệt Resource Server với Authorization Server và OAuth2 Client.
3. Khai báo đúng `spring.security.oauth2.resourceserver.opaquetoken.introspection-uri`, `client-id` và `client-secret` qua Spring Boot.
4. Giải thích luồng POST `application/x-www-form-urlencoded` đến Introspection Endpoint, dùng introspection client credentials để xác thực.
5. Giải thích `active:true`, `active:false` và ánh xạ scope `messages.read` thành authority `SCOPE_messages.read`.
6. Bảo vệ WebFlux API bằng `SecurityWebFilterChain`, `ServerHttpSecurity` và `oauth2ResourceServer(...opaqueToken...)`.
7. Phân biệt 401 do thiếu/không hợp lệ Bearer, 403 do thiếu authority và lỗi mạng/hạ tầng khi IdP không khả dụng.
8. Viết test WebFlux `WebTestClient` kiểm 200/401/403 với fake `ReactiveOpaqueTokenIntrospector`.
9. Viết test contract dùng `SpringReactiveOpaqueTokenIntrospector` thật và local HTTP endpoint để kiểm Basic header, form body và active flag.
10. Có checklist production: HTTPS, secret manager, token revocation, timeout, rate limiting, multi-tenant và error handling fail closed.

**Một câu ghi nhớ:** Resource Server nhận **access token của caller** trong header `Authorization: Bearer`, sau đó dùng **client ID/secret của chính Resource Server** để hỏi **Authorization Server** token còn active không. Hai loại credentials **không được nhầm lẫn**.

## 2. Phân biệt vai trò trong OAuth 2.0

| Vai trò | Công việc | Input/output |
| --- | --- | --- |
| Authorization Server / Identity Provider | Cấp token, hỗ trợ token introspection/revocation | Token, grants, token metadata |
| OAuth2 Client | Nhận access token theo flow được phép và gọi API | Outbound `Authorization: Bearer ...` |
| Resource Server | Xác minh Bearer token đến API, quyết định user có được gọi endpoint | Inbound Bearer token, introspection response |
| API user / browser / machine caller | Gửi yêu cầu truy cập dữ liệu | Bearer access token được cấp |

Một WebFlux app có thể cùng lúc làm OAuth2 Client khi gọi downstream service và Resource Server khi phục vụ inbound API. Tuy nhiên:

- `spring.security.oauth2.client.registration.*` là cấu hình **OAuth2 Client xin token**;
- `spring.security.oauth2.resourceserver.jwt.*` là cấu hình **JWT validation** của Resource Server;
- `spring.security.oauth2.resourceserver.opaquetoken.*` là cấu hình **opaque token introspection** của Resource Server.

Không lấy `client-secret` ở `resourceserver.opaquetoken` để đăng nhập người dùng, không gửi nó cho frontend, không coi nó là một access token.

### 2.1 Opaque access token là gì?

Opaque token là credential mà Resource Server không tự xác minh qua ký tự/claims có thể đọc cục bộ. Ví dụ:

```http
GET /api/messages HTTP/1.1
Host: api.example.test
Authorization: Bearer 6dab5a3b-demo-token
```

Chuỗi sau `Bearer` có thể là một tham chiếu ngẫu nhiên do IdP cấp. Resource Server không biết user, client, expiry, scopes chỉ từ token string. Thay vì parse và đoán quyền, nó truy vấn **OAuth2 Token Introspection Endpoint** theo RFC 7662.

Opaque **không bắt buộc** là một chuỗi ngắn: ngay cả JWT cũng có thể được xác minh qua introspection nếu kiến trúc cần quyết định online của IdP. Điều quan trọng là **phương pháp xác minh** đang dùng, không phải “chuỗi có dấu chấm hay không”.

### 2.2 So với JWT Resource Server

| Nội dung | JWT validation | Opaque introspection |
| --- | --- | --- |
| Cơ chế | Verify chữ ký, issuer/audience/expiry/claims | Gửi token tới IdP, chấp nhận active/metadata được trả về |
| Nhu cầu kết nối IdP mỗi request | Không nhất thiết sau khi có JWKS/key hợp lệ | Thường có request introspection nếu không cache |
| Thu hồi token nhanh | Phụ thuộc token lifetime/revoke policy riêng | IdP có thể trả `active:false` ngay khi bị thu hồi |
| Latency | Thường thấp cho local verification | Phụ thuộc network/IdP |
| Lỗi thường gặp | Signature, kid, jwks, iss, aud, exp | Endpoint, Basic secret, TLS, timeout, active flag |
| Config Spring Boot | `resourceserver.jwt.issuer-uri` | `resourceserver.opaquetoken.introspection-uri` + client credentials |

**Không có kết luận JWT luôn tốt hơn hoặc opaque luôn an toàn hơn.** Opaque introspection có lợi cho quyết định token active tại thời điểm kiểm tra, nhưng làm Resource Server phụ thuộc IdP trong authentication path.

## 3. Ba thuộc tính cấu hình chính xác

Đây là cấu hình **Spring Boot 3.x** theo Spring Security 6.5:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Các giá trị `${INTROSPECTION_CLIENT_ID}` và `${INTROSPECTION_CLIENT_SECRET}` là placeholders để runtime nhận từ environment/secrets manager. **Phải thay endpoint bằng URI do IdP thật công bố** trước khi chạy end-to-end. Không dùng domain `example.test` làm IdP production.

| Thuộc tính | Ý nghĩa | Lỗi điển hình |
| --- | --- | --- |
| `introspection-uri` | HTTPS URL đầy đủ của token introspection endpoint | Nhầm URL token endpoint, login endpoint, JWKS, issuer metadata |
| `client-id` | ID của confidential client được **cho phép introspect** tại IdP | Dùng nhầm SPA/client ID hoặc client không có quyền |
| `client-secret` | Bí mật chứng minh identity của introspection client | Secret chưa inject, expired/rotated, leak qua logs hoặc config |

### 3.1 introspection-uri là endpoint nào?

Một số đường dẫn chỉ để minh họa:

```text
https://idp.example.test/oauth2/introspect
https://idp.example.test/protocol/openid-connect/token/introspect
https://idp.example.test/oauth2/v1/introspect
```

Các IdP dùng endpoint khác nhau. **Không tự đoán URL theo issuer** và không nhầm `introspection-uri` với:

- `authorization-uri`: browser được chuyển đến để login/consent;
- `token-uri`: OAuth2 Client đổi code hoặc xin access token;
- `jwk-set-uri`: tập khóa công khai dùng để validate JWT;
- `issuer-uri`: metadata/issuer dùng trong validation tương ứng;
- `userinfo-uri`: OIDC UserInfo endpoint;
- `/api/messages`: đường dẫn của Resource Server do bạn bảo vệ.

URI introspection **phải được cấu hình từ nguồn tin cậy**, không lấy từ header/query/token chưa xác minh. Nếu URI do attacker kiểm soát, app có thể gửi cả bearer token lẫn introspection client credentials tới máy của attacker (**SSRF/credential leakage**).

### 3.2 client-id là danh tính nào?

Đây là ID của **resource-server introspection client**, không phải `client_id` ở token được cấp cho một mobile app, không phải `sub` của user. Một công ty có thể có:

```text
mobile-app-client             -> OAuth2 Client xin access token
backend-api-introspection     -> Confidential client có quyền introspect
alice                         -> Resource owner / subject
```

Ba danh tính đó khác nhau. IdP cần cho `backend-api-introspection` quyền tra cứu trạng thái token theo chính sách. Nếu dùng client ID của SPA không có quyền introspection, request tới IdP có thể thất bại dù access token bản thân còn active.

### 3.3 client-secret dùng ở đâu?

Secret được Resource Server sử dụng khi gửi **introspection request** tới Authorization Server. Với cấu hình Spring Security 6.5 mặc định, HTTP Basic client authentication là cách phổ biến. Nó không phải bearer token để đặt trên inbound API.

**Basic có Base64, không có nghĩa được mã hóa an toàn.** Dùng HTTPS/TLS đúng certificates, hostname và truststore. Trong môi trường thật lưu secret bằng secrets manager/Key Vault/Vault/Kubernetes Secret có kiểm soát, không commit vào Git hoặc in ra CI logs.

Một ví dụ **chỉ là cách inject environment vào process demo**:

```powershell
$env:INTROSPECTION_CLIENT_ID = "local-introspector"
$env:INTROSPECTION_CLIENT_SECRET = "<insert-from-secret-store>"
.\gradlew.bat bootRun
```

Phần `<insert-from-secret-store>` không phải password hoạt động. Trên production, tránh gõ secret thật trong terminal có command history và tránh mọi hình thức hardcode.

### 3.4 Client authentication methods khác Basic

RFC 7662 cho phép introspection endpoint yêu cầu client authentication. Nhiều IdP hỗ trợ Basic client secret, nhưng cũng có mTLS, private_key_jwt hoặc cơ chế IdP riêng. Ba Boot properties là cách cấu hình phổ thông; khi IdP yêu cầu phương thức khác, cần custom `ReactiveOpaqueTokenIntrospector`/HTTP client đúng contract của IdP và bảo mật TLS.

Đừng “chữa” lỗi Basic 401 bằng cách gửi client secret trong query string hoặc gửi secret lại cho browser. Client secret thuộc backend và cần được giới hạn quyền.

## 4. Luồng xác minh opaque Bearer token

```text
API caller
   |
   | GET /api/messages
   | Authorization: Bearer <opaque-token>
   v
Spring Security WebFlux
   |
   | 1. Bearer authentication filter trích token
   | 2. ReactiveOpaqueTokenIntrospector gọi IdP
   v
Authorization Server
   |
   | HTTPS POST introspection-uri
   | Basic <client-id:client-secret>
   | Content-Type: application/x-www-form-urlencoded
   | token=<opaque-token>
   |
   +-- {"active":true,...} -> verified principal/authorities
   +-- {"active":false}    -> invalid token, authentication fails
   +-- timeout/5xx         -> unable to validate, do not grant access
   v
Spring Security authorization
   |
   +-- scope đủ       -> gọi controller -> 200 tùy business
   +-- scope thiếu    -> 403
   +-- thiếu/sai token -> 401
```

### 4.1 Outbound POST introspection có dạng gì?

Một HTTP exchange khái niệm:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <REDACTED_CLIENT_AUTH>

token=<REDACTED_USER_ACCESS_TOKEN>
```

Đây không phải curl command hoàn chỉnh. Form field `token` được gửi tới IdP; header Basic dùng credential của **Resource Server**. Giá trị `token_type_hint=access_token` là tùy chọn có thể được IdP hỗ trợ, không phải thứ bạn cần tự thêm khi dùng mặc định của Spring.

Resource Server có thể gửi các giá trị nhạy cảm **trong cả header và body** của outbound POST; phải vô hiệu hóa logging chi tiết có nguy cơ lộ credentials.

### 4.2 active:true có ý nghĩa gì?

Ví dụ response IdP:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "messages.read profile.read",
  "client_id": "mobile-app",
  "token_type": "Bearer",
  "exp": 1893456000
}
```

Theo Spring Security Opaque Token support:

- `active:true` cho biết IdP xác nhận token active theo chính sách của nó.
- Spring tạo `OAuth2AuthenticatedPrincipal` từ attributes và `BearerTokenAuthentication` cho request.
- Những scope được map thành authorities có prefix `SCOPE_`:
  - `messages.read` → `SCOPE_messages.read`;
  - `profile.read` → `SCOPE_profile.read`.
- `Authentication#getName()` thường lấy từ `sub` khi IdP trả thuộc tính này.
- Sau authentication, **authorization còn phải kiểm tra** scope và domain policy.

Không tự tin vào `sub` hoặc `scope` lấy từ JSON payload do **caller** gửi. Chỉ dùng attributes đã được trusted introspection xác nhận.

### 4.3 active:false có ý nghĩa gì?

```json
{
  "active": false
}
```

Đây là đáp án thường gặp khi token không tồn tại, hết hạn, bị revoke hoặc không được introspection client phép hỏi. Resource Server **không cấp principal hợp lệ** và protected API thường trả 401 Bearer challenge.

IdP có thể cố tình không tiết lộ lý do cụ thể để giảm khả năng thăm dò trạng thái token. Đừng xuất token hoặc thông tin chi tiết nội bộ trong error body.

### 4.4 Active:true không có nghĩa truy cập mọi API

Một token `scope="profile.read"` vẫn không được phép truy cập endpoint cần `SCOPE_messages.read`. Một token có scope messages.read cũng không đương nhiên được xem thông điệp của tenant khác. Authorization gồm cả **HTTP rule** và **business/resource ownership rule**.

## 5. Các Spring Security types cần nắm

| Type | Tầng dùng | Trách nhiệm |
| --- | --- | --- |
| `ServerHttpSecurity` | Cấu hình WebFlux security | `authorizeExchange`, `oauth2ResourceServer` |
| `SecurityWebFilterChain` | WebFilter bảo mật | Xác thực/phân quyền request |
| `ReactiveOpaqueTokenIntrospector` | Authentication pipeline | `Mono<OAuth2AuthenticatedPrincipal> introspect(String token)` |
| `SpringReactiveOpaqueTokenIntrospector` | HTTP introspection | Gọi endpoint do cấu hình, kiểm active và ánh xạ |
| `OAuth2AuthenticatedPrincipal` | Sau introspection | Claims/attributes và authorities |
| `BearerTokenAuthentication` | Reactive SecurityContext | Authentication dành cho bearer caller |
| `ReactiveSecurityContextHolder` | Reactor | Truyền SecurityContext qua reactive chain |
| `ServerAuthenticationEntryPoint` | Lỗi authentication | Xử lý 401/challenge |
| `ServerAccessDeniedHandler` | Lỗi authorization | Xử lý 403 khi user thiếu quyền |

**Tránh trộn Servlet API**: `HttpSecurity`, `SecurityFilterChain` và `OpaqueTokenIntrospector` đồng bộ là các type phía Servlet. Trong WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveOpaqueTokenIntrospector`.

### 5.1 Boot auto-config hoạt động ra sao?

Khi project dùng OAuth2 Resource Server starter và khai ba properties:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

nếu **không có custom `ReactiveOpaqueTokenIntrospector` bean**, Spring Boot có thể tạo introspector tương ứng. Nếu **không có custom `SecurityWebFilterChain` bean**, Boot có thể thêm chain mặc định bảo vệ requests và bật opaque token.

Khi bạn định nghĩa `SecurityWebFilterChain` riêng, **đừng mặc định** chain đó tự bật opaque support nếu bạn không khai `oauth2ResourceServer(...opaqueToken...)`. Trong bài ta cấu hình tường minh để có scope-based authorization.

**Lưu ý về dependency:** `spring-boot-starter-oauth2-resource-server` cung cấp các dependency Resource Server phù hợp. `spring-boot-starter-oauth2-client` không thay nó; client starter phục vụ ứng dụng xin token outbound.

## 6. Project Java 17+ Spring Boot 3.x chạy theo cấu hình này

### 6.1 Dependencies

Tạo project Spring Initializr (Java 17+, Spring Boot 3.x, Gradle Groovy), chọn Spring Reactive Web, Spring Security, OAuth2 Resource Server. Trong `build.gradle` đã có Boot plugin/dependency management, thêm:

```groovy
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

Không thêm `spring-boot-starter-web` nếu muốn thực sự chạy **reactive WebFlux**; khi MVC và WebFlux cùng có mặt, Boot thường chọn MVC mặc định.

### 6.2 Cấu trúc file

```text
src/main/java/com/example/opaqueapi/
  OpaqueApiApplication.java
  OpaqueSecurityConfig.java
  MessageController.java
src/main/resources/
  application.yml
src/test/java/com/example/opaqueapi/
  OpaqueHttpTest.java
  IntrospectionContractTest.java
```

Mỗi class public nằm trong file Java cùng tên và cùng package `com.example.opaqueapi`; code cần Spring dependencies, không chạy trực tiếp bằng `javac` trần.

### 6.3 OpaqueApiApplication.java

`src/main/java/com/example/opaqueapi/OpaqueApiApplication.java`:

```java
package com.example.opaqueapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueApiApplication.class, args);
    }
}
```

### 6.4 application.yml

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Domain `idp.example.test` dùng để minh họa và **không tạo connection thật**. Muốn chạy staging, thay bằng endpoint IdP và inject client ID/secret. Unit tests ở phần sau tự cung cấp fake introspector nên không cần IdP.

### 6.5 OpaqueSecurityConfig.java

`src/main/java/com/example/opaqueapi/OpaqueSecurityConfig.java`:

```java
package com.example.opaqueapi;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class OpaqueSecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/messages")
                    .hasAuthority("SCOPE_messages.read")
                .pathMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
```

**Giải thích kỹ:**

- `@EnableWebFluxSecurity` kích hoạt security stack reactive.
- `/public/health` là health endpoint demo, public theo quyết định rõ.
- `/api/messages` yêu cầu `SCOPE_messages.read` **đúng authority** từ trusted introspection scopes; `messages.read` không phải `ROLE_messages.read`.
- `/api/profile` chỉ yêu cầu authenticated bearer token; nếu tenant policy cần scope riêng hãy siết rule.
- `anyExchange().denyAll()` là mặc định an toàn.
- `oauth2ResourceServer(...opaqueToken...)` bật authentication cho Bearer token, dùng introspector từ auto-config/bean.
- `Customizer.withDefaults()` không có nghĩa “cho qua mọi token”. Token vẫn được introspection và phải hợp lệ.

### 6.6 MessageController.java

`src/main/java/com/example/opaqueapi/MessageController.java`:

```java
package com.example.opaqueapi;

import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class MessageController {

    public record MessageView(String owner, String text) {}
    public record ProfileView(String subject) {}

    @GetMapping(
        value = "/public/health",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping(
        value = "/api/messages",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<MessageView> messages(BearerTokenAuthentication auth) {
        return Mono.just(new MessageView(
            auth.getName(), "protected-example"
        ));
    }

    @GetMapping(
        value = "/api/profile",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ProfileView> profile(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(new ProfileView(principal.getName()));
    }
}
```

Sau khi opaque token hợp lệ, `BearerTokenAuthentication`/`OAuth2AuthenticatedPrincipal` phản ánh danh tính tin cậy từ IdP. Controller không tự parse `Authorization` để lấy username hoặc scope và **không trả raw bearer token/client secret** cho API caller.

**Mẫu chỉ phục vụ học tập:** Text “protected-example” là dữ liệu giả; khi thay bằng tin nhắn thật cần thêm kiểm tra owner/tenant/resource access, không chỉ scope chung.

## 7. Test WebFlux authorization với fake introspector

Đây là test ứng dụng tách khỏi IdP. Nó tạo hai token giả định:

- `opaque-read`: user alice, `SCOPE_messages.read`.
- `opaque-profile`: user bob, `SCOPE_profile.read`.
- Mọi token khác đều bị reject bằng `BadOpaqueTokenException`.

Dùng `WebTestClient.bindToApplicationContext(...)` và `springSecurity()` để chạy WebFlux security filters. Đây **không phải test trực tiếp Basic auth / outbound POST introspection**; phần 8 kiểm tra riêng.

### 7.1 OpaqueHttpTest.java

`src/test/java/com/example/opaqueapi/OpaqueHttpTest.java`:

```java
package com.example.opaqueapi;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = {
        "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://unused.example.test/introspect",
        "spring.security.oauth2.resourceserver.opaquetoken.client-id=offline",
        "spring.security.oauth2.resourceserver.opaquetoken.client-secret=offline"
    }
)
@Import(OpaqueHttpTest.TestTokens.class)
class OpaqueHttpTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @TestConfiguration(proxyBeanMethods = false)
    static class TestTokens {
        @Bean
        @Primary
        ReactiveOpaqueTokenIntrospector testIntrospector() {
            return token -> {
                if ("opaque-read".equals(token)) {
                    return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                        "alice",
                        Map.of("sub", "alice", "scope", "messages.read"),
                        List.of(new SimpleGrantedAuthority(
                            "SCOPE_messages.read"))
                    ));
                }
                if ("opaque-profile".equals(token)) {
                    return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                        "bob",
                        Map.of("sub", "bob", "scope", "profile.read"),
                        List.of(new SimpleGrantedAuthority(
                            "SCOPE_profile.read"))
                    ));
                }
                return Mono.error(
                    new BadOpaqueTokenException("Inactive token"));
            };
        }
    }

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/public/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void missingBearerGets401() {
        client.get().uri("/api/messages")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void goodReadTokenGets200() {
        client.get().uri("/api/messages")
            .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-read")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice")
            .jsonPath("$.text").isEqualTo("protected-example");
    }

    @Test
    void activeTokenMissingScopeGets403() {
        client.get().uri("/api/messages")
            .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-profile")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void invalidBearerGets401() {
        client.get().uri("/api/messages")
            .header(HttpHeaders.AUTHORIZATION, "Bearer expired-token")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void profileAllowsAnyAuthenticatedToken() {
        client.get().uri("/api/profile")
            .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-profile")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("bob");
    }

    @Test
    void unmatchedRouteIsDenied() {
        client.get().uri("/api/admin")
            .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-read")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Chạy trong project:

```bash
./gradlew test --tests '*OpaqueHttpTest'
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*OpaqueHttpTest'
```

**Các kết quả ở đây là assertions dự kiến, chưa phải output của một build đã chạy.** Test không gọi HTTPS IdP thật. Nó kiểm integration **Bearer filter + fake introspector + authorization rules + controller**.

### 7.2 mockOpaqueToken() khác gì?

Spring Security Test hỗ trợ:

```java
client.mutateWith(
    mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_messages.read"))
).get()
 .uri("/api/messages")
 .exchange()
 .expectStatus().isOk();
```

Đây là snippet test, cần static import `mockOpaqueToken`, biến `client` và `SimpleGrantedAuthority`. Nó inject Authentication giả, **bỏ qua outbound introspection**, nên không thể chứng minh ba properties được cấu hình đúng.

Phân tầng hợp lý:

| Test | Chứng minh | Không chứng minh |
| --- | --- | --- |
| `mockOpaqueToken()` | Authorization rule nhận authorities/principal | Credential/POST đến IdP |
| Fake `ReactiveOpaqueTokenIntrospector` | Bearer header được đưa tới introspector và xử lý 200/401/403 | HTTP Basic/introspection URI thật |
| Real `SpringReactiveOpaqueTokenIntrospector` + local stub | HTTP POST, Basic credentials, form token, active flag | TLS trust/IdP policy thật |
| E2E với IdP sandbox | Introspection client registration/permissions, TLS, scopes, revocation | Tự chứng minh production scale/security |

## 8. Test HTTP introspection request thật tới server loopback

Không cần IdP ngoài mạng để kiểm cách gửi `client-id`/`client-secret`. Java 17 có `com.sun.net.httpserver.HttpServer` (module `jdk.httpserver`). Bài test mở ephemeral port trên `127.0.0.1`, ghi nhận:

- HTTP method: POST;
- Header `Authorization: Basic ...` có client ID và secret demo;
- Header `Content-Type: application/x-www-form-urlencoded`;
- Request body có `token=opaque-good`;
- Response `active:true` cho principal, `active:false` không cho.

**Chỉ dùng HTTP loopback trong test.** Production phải là HTTPS; không gửi Basic credentials hoặc access token qua HTTP giữa máy.

### 8.1 IntrospectionContractTest.java

`src/test/java/com/example/opaqueapi/IntrospectionContractTest.java`:

```java
package com.example.opaqueapi;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicReference;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import reactor.test.StepVerifier;

class IntrospectionContractTest {

    private HttpServer server;
    private SpringReactiveOpaqueTokenIntrospector introspector;

    private final AtomicReference<String> method = new AtomicReference<>();
    private final AtomicReference<String> authorization = new AtomicReference<>();
    private final AtomicReference<String> contentType = new AtomicReference<>();
    private final AtomicReference<String> formBody = new AtomicReference<>();

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0
        );
        server.createContext("/introspect", this::handle);
        server.start();

        String uri = "http://127.0.0.1:" +
            server.getAddress().getPort() + "/introspect";

        introspector = SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId("local-introspector")
            .clientSecret("local-demo-secret")
            .build();
    }

    private void handle(HttpExchange exchange) throws IOException {
        try {
            method.set(exchange.getRequestMethod());
            authorization.set(exchange.getRequestHeaders()
                .getFirst("Authorization"));
            contentType.set(exchange.getRequestHeaders()
                .getFirst("Content-Type"));

            String body = new String(
                exchange.getRequestBody().readAllBytes(),
                StandardCharsets.UTF_8
            );
            formBody.set(body);

            String json = body.contains("token=opaque-good")
                ? "{\"active\":true,\"sub\":\"alice\",\"scope\":\"messages.read\"}"
                : "{\"active\":false}";

            byte[] response = json.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                .set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
        }
        finally {
            exchange.close();
        }
    }

    @AfterEach
    void shutdown() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void postsTokenAndBasicClientCredentials() {
        StepVerifier.create(introspector.introspect("opaque-good"))
            .assertNext(principal ->
                assertThat((String) principal.getAttribute("sub"))
                    .isEqualTo("alice")
            )
            .verifyComplete();

        assertThat(method.get()).isEqualTo("POST");

        String basic = "Basic " + Base64.getEncoder()
            .encodeToString(
                "local-introspector:local-demo-secret"
                    .getBytes(StandardCharsets.UTF_8)
            );
        assertThat(authorization.get()).isEqualTo(basic);
        assertThat(contentType.get())
            .startsWith("application/x-www-form-urlencoded");
        assertThat(formBody.get()).contains("token=opaque-good");
    }

    @Test
    void inactiveResponseCannotAuthenticate() {
        StepVerifier.create(introspector.introspect("opaque-revoked"))
            .expectError()
            .verify();
    }
}
```

Chạy:

```bash
./gradlew test --tests '*IntrospectionContractTest'
```

**Kỳ vọng:** Test 1 kiểm Spring Security gửi POST/form/basic và nhận principal, test 2 kiểm `active:false` không thành công. Test này dùng builder `SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` của **Spring Security 6.5**, không cần IdP thật. Khi build kiểu module có cấu hình đặc biệt, bảo đảm JDK module `jdk.httpserver` hiện diện.

### 8.2 Phạm vi test

HTTP stub không kiểm client ID thật được IdP cho phép, không kiểm certificate trust vì loopback HTTP, không kiểm token revocation thực. Bắt buộc có thêm staging integration tests với IdP đúng môi trường khi production.

## 9. Tùy chọn cấu hình nâng cao

### 9.1 Java DSL thay application.yml

Spring Security 6.5 cho phép cấu hình URI và credentials trực tiếp trong `ServerHttpSecurity`:

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex ->
            ex.anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque
                .introspectionUri("https://idp.example.test/introspect")
                .introspectionClientCredentials(
                    clientId, clientSecret
                )
            )
        )
        .build();
}
```

Đây là **method snippet**, cần biến `clientId` và `clientSecret` từ secret/config (không phải literal secret), imports tương ứng. Cấu hình qua DSL có thể **ghi đè auto-config**; tránh để YAML trỏ IdP A trong khi DSL trỏ IdP B. Nếu chỉ cần ba properties, ưu tiên property-driven configuration để dễ quản lý environment và tránh duplicate logic.

### 9.2 Custom ReactiveOpaqueTokenIntrospector bean

Khi cần chọn network timeout, custom WebClient, mTLS hoặc mapping claims:

```java
@Bean
ReactiveOpaqueTokenIntrospector introspector(
    @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
    String uri,
    @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
    String id,
    @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
    String secret
) {
    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(uri)
        .clientId(id)
        .clientSecret(secret)
        .build();
}
```

Đây là **bean snippet**; cần imports của Spring `Value`, `Bean`, introspection classes. Dùng builder vì constructor ba String của `SpringReactiveOpaqueTokenIntrospector` đã **deprecated for removal trong 6.5**.

**Cẩn thận:** Khi tạo custom `ReactiveOpaqueTokenIntrospector` bean, Boot auto-config mặc định sẽ nhường chỗ (back off). Bạn chịu trách nhiệm kiểm active, expiry/metadata và mapping đúng. Một lambda `token -> Mono.just(new Principal(...))` trong production có thể biến **mọi bearer token** thành authenticated user — nghiêm trọng.

### 9.3 Custom authority mapping

Spring Security mặc định map scope trong response thành authorities `SCOPE_<scope>`. Nếu IdP trả roles trong một attribute riêng:

1. Dùng **trusted introspector** làm delegate để token được xác minh trước.
2. Chỉ đọc verified attributes từ delegate, không lấy role từ request header.
3. Map vào authorities có namespace rõ, tránh tùy ý cấp `ROLE_ADMIN`.
4. Áp issuer/audience/tenant boundary và kiểm thử negative cases.

Snippet cấu trúc:

```java
public final class DelegatingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public DelegatingIntrospector(
        ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .map(verified -> {
                // Mapping chỉ dùng verified.getAttributes()
                // và policy đã được cấu hình/tin cậy.
                return verified;
            });
    }
}
```

Đây là **class snippet** trong file riêng, cần imports `ReactiveOpaqueTokenIntrospector`, `OAuth2AuthenticatedPrincipal` và `Mono`. Phần `return verified` bảo toàn principal mà delegate đã xác minh; logic mapping tùy IdP không được đoán bừa.

### 9.4 Khi nào không nên override?

Nếu IdP hỗ trợ RFC 7662 thông thường với Basic credentials, ba Boot properties đủ cho nhiều ứng dụng. Tránh viết code custom chỉ để sao chép chức năng thư viện: tăng rủi ro nhầm token request, quên validation, rò rỉ secret hoặc xử lý lỗi sai.

## 10. Chẩn đoán 401/403/introspection failure

| Tình huống | Nguồn | Kết quả thường gặp |
| --- | --- | --- |
| Không có `Authorization: Bearer` | Inbound API caller thiếu credential | 401 |
| Bearer bị trống/sai định dạng | Inbound authentication parser | 401 |
| IdP trả `active:false` | Token invalid/expired/revoked | 401 |
| IdP trả `active:true`, đúng scope | Authenticated + authorized | 200, tùy endpoint |
| IdP trả `active:true`, thiếu scope | HTTP authorization | 403 |
| `client-id` hoặc `client-secret` sai | IdP reject outbound introspection call | Không tự đồng nghĩa inbound 401/403; xử lý lỗi auth service |
| `introspection-uri` sai path | HTTP 404 từ IdP | Lỗi tích hợp, cần sửa URI |
| TLS handshake/cert error | Outbound HTTPS tới IdP | Không xác minh được token, fail closed |
| IdP 5xx/timeout | Outbound dependency unavailable | Không cho dữ liệu; status tùy exception handling, có thể 5xx |
| Token active nhưng sai tenant | Business authorization | 403/404 theo privacy policy |
| API path chưa đăng ký | `anyExchange().denyAll()` | Thường 403 nếu token hợp lệ |
| Public health request | `permitAll()` | 200 nếu handler thành công |

**Phân biệt hai HTTP request:** Resource Server nhận một inbound GET với Bearer; đồng thời nó tạo một **outbound POST** đến IdP với Basic. Lỗi 401/403 từ IdP outbound **không đơn giản** được chuyển nguyên trạng thành 401/403 của API consumer. Đừng bắt mọi exception của introspector rồi trả 200 hoặc principal mặc định.

### 10.1 Khi nào fail closed?

Nếu IdP không trả kết quả hợp lệ, Resource Server không biết Bearer token có active và đủ scope. Không được tạo authenticated principal hoặc trả dữ liệu nhạy cảm. Có thể đưa response lỗi hạ tầng đã sanitize (ví dụ 503) theo architecture, nhưng **không mặc định cho phép**.

### 10.2 403 không phải token invalid

Một token active với scope `profile.read` vẫn có thể bị từ chối khi gọi `/api/messages`. Đó là **authorization denial**, không phải introspection failure. Không cứ 403 thì yêu cầu user đăng nhập lại; xem scope/domain policy trước.

### 10.3 Tại sao curl đọc API được mà browser bị CORS?

CORS do browser áp dụng, không phải phần `active:true`. Nếu SPA frontend cross-origin gọi API, phải cấu hình CORS preflight trước authentication đúng cách. CORS success **không bảo đảm token active**; Resource Server vẫn kiểm Bearer theo policy.

## 11. Bảo vệ introspection client secret và Bearer token

**Một outbound introspection request chứa hai nhóm secret:**
- Basic client secret của Resource Server;
- Bearer token do API caller đưa vào body.

Vì vậy:

- Dùng **HTTPS/TLS** với certificate/hostname validation từ Resource Server tới IdP.
- Không dùng insecure trust-all TLS trong production.
- Đặt IdP URI ở trusted configuration, không cho attacker chọn URL khi gửi token.
- Không ghi `Authorization: Basic`, `Bearer`, `token=...`, `client_secret` vào logs, traces, CI artifacts hoặc support tickets.
- Giới hạn IAM/ACL để chỉ workload Resource Server đọc introspection secret.
- Dùng secret manager và có rotation/rollback runbook.
- Xem xét outbound egress allowlist chống SSRF.
- Không đưa secret vào frontend localStorage, cookies/query strings hoặc response API.
- Áp quyền introspection client theo least privilege; nếu có multi-tenant, tách client credentials/trust boundary.
- Không tưởng rằng mã hóa Base64 của HTTP Basic giúp che secret khỏi người nghe lén.
- Đặt timeout, rate limiting và metrics để nhiều bearer tokens rác không làm IdP bị quá tải.

**Không bao giờ log raw token để debug:** log route, loại lỗi, latency, request ID và tên IdP được allowlist; nếu cần correlation token, đánh giá hash/HMAC có salt/rotation và giới hạn quyền truy cập để không tạo oracle/PII leak.

## 12. Cache, revocation và phụ thuộc IdP

### 12.1 Có nên cache kết quả introspection?

Cache giúp giảm thời gian mỗi API request và giảm tải IdP, nhưng đồng nghĩa một token đã bị revoke có thể **còn được chấp nhận tới lúc cache expire**. Cần xác định:

- TTL không vượt access token expiration và đủ ngắn so với revocation SLO;
- Cache key tách issuer/tenant/audience, bảo vệ token value;
- Cách invalidate khi IdP revokes token (nếu có event/hook);
- Không dùng stale active cache làm fallback tự động khi IdP outage;
- Negative caching/rate limiting phải tránh tạo oracle tiết lộ token có tồn tại;
- Monitoring token cache hit/miss, stale errors và revoked token acceptance.

Không mặc định Spring Security Opaque Token support tự cache các kết quả introspection của bạn. Nếu thêm cache custom phải kiểm security implications.

### 12.2 Timeout và retry

Vì introspection dùng HTTP outbound trên authentication critical path:

1. Giới hạn connect/read timeout và concurrent introspections.
2. Retry có backoff chỉ cho transient network failure, có giới hạn.
3. Không retry infinite `active:false` hoặc client credentials sai.
4. Dùng connection pooling đúng cấu hình Netty/WebClient.
5. Có circuit breaker/bulkhead phù hợp SLO nếu IdP liên tục chậm.
6. Alert theo latency, outage và spikes trong số lượng invalid tokens.

**Không gọi `block()` trong Netty event-loop.** `ReactiveOpaqueTokenIntrospector` trả `Mono`, tích hợp vào WebFlux reactive authentication.

### 12.3 Rate limiting trước introspection

Kẻ tấn công có thể gửi hàng nghìn Bearer chuỗi ngẫu nhiên để buộc app hỏi IdP cho từng token. Dù cuối cùng trả 401, cuộc gọi outbound đã tiêu tốn tài nguyên. Ingress/gateway và ứng dụng cần có request budget, rate limits, bot protection/quotas theo IP hoặc client identity, và tránh logging token values.

### 12.4 Revocation và độ trễ

Đầu mối tin cậy là Authorization Server. Nếu token bị thu hồi, IdP có thể trả `active:false` và Resource Server từ chối lần introspection tiếp theo. Nhưng nếu app tự cache positive result 5 phút, khả năng từ chối có thể chậm tới khoảng 5 phút. Đây là quyết định bảo mật cần phê duyệt dựa trên data sensitivity.

## 13. Multi-tenant và authority mapping

### 13.1 Active không phải policy hoàn chỉnh

Nếu API phục vụ nhiều tenants, `active:true` và scope `messages.read` không tự xác nhận user được đọc tài liệu tenant B. Phải có business rule dựa trên trusted tenant/owner claims và database access control.

### 13.2 Issuer/audience

Một số introspection endpoints trả `aud`, `iss`, `client_id`, `exp`; có nơi chỉ trả active/scope/sub. Những trường đó có thể optional hoặc thay đổi theo provider. Đừng giả định bất kỳ IdP nào cũng trả `aud` đúng định dạng. Nếu kiến trúc cần audience restriction, cấu hình IdP để giới hạn resource introspection hoặc viết policy xác minh attributes đáng tin.

### 13.3 Nhiều IdPs

Một `introspection-uri` duy nhất hợp lý khi dùng một IdP/trust boundary. Nếu hỗ trợ nhiều issuers/tenants, cần routing tin cậy và credentials riêng — không chọn IdP dựa trên một string chưa xác minh trong opaque token, không gửi token của issuer A sang IdP B và không nhận arbitrary URL từ request làm introspection URI.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nhầm `introspection-uri` với `token-uri` | 404/invalid request | Lấy đúng RFC 7662 endpoint từ IdP |
| Quên `client-id`/`client-secret` | Boot không tạo introspector đúng hoặc IdP từ chối | Inject đủ ba properties |
| Dùng client ID của SPA thay introspection client | IdP không cho introspect | Tạo confidential client có quyền phù hợp |
| Commit client secret vào Git | Credential compromise | Secret manager, rotation, redact |
| HTTP không có TLS tới IdP | Lộ Basic secret/token | Dùng HTTPS và certificate verification |
| Dùng `HttpSecurity` trong WebFlux | Sai stack | `ServerHttpSecurity` + `SecurityWebFilterChain` |
| Dùng Servlet `OpaqueTokenIntrospector` | Không đúng reactive interface | `ReactiveOpaqueTokenIntrospector` |
| Nghĩ `active:true` cho phép mọi method/path | Privilege escalation | Scope + resource authorization |
| Viết `hasAuthority("messages.read")` | Không match `SCOPE_messages.read` | Dùng đúng prefix `SCOPE_` |
| Tưởng 401 outbound IdP = 401 inbound client | Sai error classification | Phân biệt request/hops |
| Catch network error rồi return principal | Authentication bypass | Fail closed |
| Fake introspector được dùng ở production | Bypass token verification | Fake chỉ nằm trong test |
| Dùng `mockOpaqueToken()` để kiểm client secret | Không có introspection HTTP | Thêm contract test/staging integration |
| Cache positive không có TTL/revocation | Accept revoked token | TTL theo security SLO |
| Log full token và Basic header | Credential leakage | Redaction/safe metrics |
| IdP 5xx làm API chậm | Critical dependency thiếu budgets | Timeouts/concurrency/circuit breaker |
| Multi-tenant token dùng sai IdP | Cross-issuer trust confusion | Trusted routing và isolated credentials |
| Client thiếu scope bị 403, cố refresh | Không tự cấp thêm quyền | Kiểm scope, consent/domain policy |
| Dùng `X-User`/`X-Role` từ caller | Caller tự mạo danh | Chỉ dùng verified principal/attributes |
| CORS 401 và token 401 bị nhầm | Debug sai tầng | Kiểm preflight và auth riêng |
| Tăng log network chi tiết trong production | Leak body/header | Logging allowlist, scrub secret |

## 15. Câu hỏi tự kiểm tra

**1. `introspection-uri` trỏ tới đâu?** Tới **Token Introspection Endpoint của Authorization Server**, không phải URL API đang bảo vệ.

**2. `client-id`/`client-secret` là của user gọi API?** Không. Chúng là credentials của introspection client dùng bởi Resource Server.

**3. Bearer access token đi đâu?** Caller gửi đến Resource Server. Resource Server truyền token tới IdP trong introspection form; không gửi refresh token.

**4. `active:false` có được coi là authenticated không?** Không, token validation thất bại.

**5. `active:true` và scope `profile.read` gọi `/api/messages` cần `messages.read` sẽ có gì?** Thường 403 do thiếu `SCOPE_messages.read`.

**6. Tại sao introspection thường là HTTP POST?** RFC 7662 định nghĩa endpoint nhận request form chứa `token` và client authentication; Spring Security tuân theo giao thức.

**7. Đổi `oauth2Client()` thành `oauth2ResourceServer()` có thay thế được nhau không?** Không; một bên lấy outbound token, một bên validate inbound token.

**8. Basic client secret được bảo vệ bằng Base64 chưa?** Chưa; Base64 không phải encryption. Phải dùng HTTPS.

**9. Vì sao không dùng `issuer-uri` thay `introspection-uri`?** `issuer-uri` phổ biến với JWT validation/discovery; opaque introspection cần endpoint được cấu hình rõ.

**10. IdP timeout thì có cấp quyền để app không gián đoạn không?** Không. Phải fail closed và xử lý lỗi infrastructure.

**11. Khi nào dùng custom introspector bean?** Khi có nhu cầu đã xác định như mTLS, custom HTTP client/claim mapping; phải delegate tới trusted validation và kiểm thử.

**12. Vì sao `mockOpaqueToken()` không kiểm Basic credentials?** Nó tạo principal giả trong test, không gửi introspection request thật.

**13. Vì sao cache có rủi ro?** Token đã revoke có thể vẫn được chấp nhận trong thời gian TTL.

**14. Một token active đã được đọc dữ liệu mọi tenant chưa?** Chưa; còn scope, audience/tenant và object ownership checks.

**15. Test status HTTP nào có ý nghĩa?** Thiếu/bad bearer thường 401; active thiếu scope 403; đủ scope 200; network IdP fail không được biến thành 200.

## 16. Checklist production

- [ ] Đúng **opaque Resource Server**, không nhầm với JWT hoặc OAuth2 Client.
- [ ] Đúng `introspection-uri` từ trusted IdP, dùng HTTPS/TLS.
- [ ] `client-id` thuộc confidential introspection client có quyền cần thiết.
- [ ] `client-secret` nằm trong server secret manager, không trong Git/frontend/logs.
- [ ] Dùng `ReactiveOpaqueTokenIntrospector` và `ServerHttpSecurity` đúng WebFlux stack.
- [ ] Bật `oauth2ResourceServer(...opaqueToken...)` cho protected APIs.
- [ ] Không có fake introspector bean trong production.
- [ ] `active:false` bị từ chối; active true mới tạo principal.
- [ ] Scopes được map `SCOPE_...` và route rules kiểm đúng authorities.
- [ ] Có owner/tenant/domain checks nếu API trả dữ liệu riêng.
- [ ] Kiểm 401/403/200 với `WebTestClient` và negative cases.
- [ ] Kiểm Basic/form POST bằng real introspector contract test.
- [ ] Kiểm kết nối HTTPS, certificates, client secret permissions ở IdP sandbox.
- [ ] Có timeout, concurrency limit, rate limit, monitoring và outage runbook.
- [ ] Đánh giá positive cache TTL so với revocation SLO.
- [ ] Không log raw bearer token, Basic credentials hoặc token form body.
- [ ] Có egress allowlist, SSRF protection, phân tách issuer/tenant khi cần.
- [ ] Có phương án secret rotation và tránh downtime khi credential đổi.
- [ ] CORS, CSRF, gateway policy được thiết kế độc lập, không thay bearer validation.

## 17. Tổng kết

Ba thuộc tính thiết yếu cho Spring Boot **opaque token introspection** là:

```yaml
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri: https://idp.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id: ${INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Khi nhận `Authorization: Bearer <opaque-token>`, Spring Security WebFlux dùng `ReactiveOpaqueTokenIntrospector` để hỏi Authorization Server qua HTTPS, xác nhận `active:true` rồi map scope thành `SCOPE_...`. Token invalid thường bị từ chối **401**, token active nhưng không đủ quyền thường bị **403**. Không vì IdP unavailable mà bypass authentication.

**Quan trọng nhất:** `client-id`/`client-secret` ở đây là **credentials của Resource Server để introspect**, không phải Bearer token của API caller. Bảo vệ chúng bằng TLS/secrets management, kiểm chính xác endpoint, phân quyền theo scope/tenant và test đủ cả fake HTTP policy lẫn contract introspection thật.

### Tài liệu chính thức

- [Spring Security 6.5 — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/index.html)
- [Spring Security 6.5 — Reactive OAuth2 Tests, mockOpaqueToken](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [Spring Security 6.5 — SpringReactiveOpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security 6.5 — SpringReactiveOpaqueTokenIntrospector.Builder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.Builder.html)
- [Spring Security 6.5 — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Boot 3.5 — Security configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
