# Ranh giới với cấu hình Authorization Server và bảo vệ API bằng access token

## 1. Mục tiêu và tình huống thực tế

Một ứng dụng Java/Spring Boot đã triển khai **SAML 2.0 federation** hoặc **OpenID Connect (OIDC) login** có thể xác thực người dùng thành công bằng IdP bên ngoài. Khi cùng hệ thống có thêm REST API, một câu hỏi mới xuất hiện: **API có nên tin phiên đăng nhập SSO của ứng dụng web, hay phải xác minh OAuth 2.0 access token?** Và nếu cần access token, **bên nào phát hành token**?

Phải phân biệt bốn vai trò:

- **SAML SP / OIDC Relying Party (RP)**: ứng dụng web xác thực người dùng bằng SAMLResponse hoặc OIDC ID Token/authorization code, thường thiết lập `SecurityContext` và HTTP session riêng.
- **OAuth 2.0 Client**: thành phần yêu cầu authorization grant và nhận access token từ một Authorization Server, có thể gọi API thay mặt người dùng hoặc bằng client credentials.
- **Authorization Server (AS)**: thành phần quản lý registered clients, grants, consent, token endpoints, signing keys, phát hành access token/refresh token và, nếu bật OIDC, ID Token.
- **Resource Server (RS)**: API nhận Bearer access token, kiểm tra token và quyền trước khi cho phép đọc/ghi tài nguyên.

**Bật `oauth2Login` hoặc `saml2Login` không tự làm ứng dụng thành Authorization Server. Bật `oauth2ResourceServer` không khiến ứng dụng tự ký hoặc phát hành access token.** Những tính năng này xử lý các phía khác nhau của trust boundary.

Bài học thuộc nhóm **OIDC và môi giới**: giải thích ranh giới khi một broker xác minh danh tính upstream rồi cấp hoặc chuyển tiếp quyền cho downstream APIs. Ví dụ sử dụng **Spring Boot 3.x/Spring Security 6.x/Java 17+**; API của Spring Security 7.x và Spring Authorization Server 1.x có khác biệt cần ghim phiên bản. Các hostname `example.test` là dữ liệu minh họa.

Mục tiêu sau bài: phân biệt ID Token/access token/session, nhận diện đúng cấu hình client/AS/RS, cấu hình JWT Resource Server với `iss`/`aud`/signature/time/scope, hiểu opaque token introspection, thiết kế API multi-issuer có allowlist, tách session web và Bearer stateless, kiểm thử token substitution/mismatch và tránh cấp quyền tenant từ token chưa xác minh.

## 2. Mô hình tổng thể: upstream federation, downstream OAuth 2.0

```mermaid
flowchart LR
    B["Browser"] -->|"SSO login"| W["Web App: SAML SP / OIDC Client"]
    W <-->|"SAMLRequest / SAMLResponse hoặc OIDC Authorization Code"| U["Upstream IdP / OP"]
    W -->|"Phiên ứng dụng + cookie"| B
    AS["Downstream Authorization Server"] -->|"Phát access token"| C["OAuth2 Client / BFF"]
    C -->|"Authorization: Bearer access token"| API["Orders API: Resource Server"]
    API -.->|"JWKS hoặc introspection đã cấu hình"| AS
    W -.->|"Có thể chính là client/BFF"| C
```

Sơ đồ biểu thị **vai trò**, không bắt buộc chúng là các máy chủ vật lý độc lập. Hai biến thể hay gặp:

1. **OP là AS**: ứng dụng web đăng nhập OIDC với một OP, nhận access token do chính OP/AS phát hành, rồi gọi API nếu **token được cấp cho đúng audience của API**.
2. **Identity broker**: broker là SAML SP/OIDC RP ở phía upstream; nếu triển khai thêm downstream Authorization Server, broker **phát token mới** bằng issuer/key của mình sau khi xác minh và liên kết identity upstream. API tin broker AS, không nhất thiết tin SAML IdP trực tiếp.

**Không có bước mặc định “SAMLResponse → JWT access token” trong `saml2Login`.** Muốn có downstream token cần một Authorization Server, một grant/token exchange profile đã phê duyệt và chính sách cấp quyền cụ thể.

## 3. Ranh giới trách nhiệm trong Spring Security

| Vai trò | Spring Security/Boot thường dùng | Kết quả | Không làm |
| --- | --- | --- | --- |
| OIDC web client | `spring-boot-starter-oauth2-client`, `oauth2Login`, `ClientRegistrationRepository` | OIDC authentication, browser session, authorized client khi thích hợp | Không tự phát token cho API |
| SAML SP | `spring-security-saml2-service-provider`, `saml2Login`, `RelyingPartyRegistrationRepository` | Xác thực SAML Assertion, browser principal/session | Không làm OAuth2 AS |
| OAuth2 client gọi API | `OAuth2AuthorizedClientManager` / authorized-client repository | Lấy/quản lý access token được AS cấp | Không thay việc API verify token |
| Authorization Server | `spring-boot-starter-oauth2-authorization-server` trong Boot 3.x, Spring Authorization Server 1.x | Authorization code/token/introspection/JWKS, keys, registered clients | Không tự bảo vệ business API ở services khác |
| JWT Resource Server | `spring-boot-starter-oauth2-resource-server`, `oauth2ResourceServer().jwt()`, `JwtDecoder` | Verify JWT access token, tạo `JwtAuthenticationToken` | Không phát JWT |
| Opaque Resource Server | `oauth2ResourceServer().opaqueToken()`, `OpaqueTokenIntrospector` | Introspect token và map scopes | Không phát refresh token |
| Broker | Upstream client + downstream AS **nếu đã triển khai hai phía** | Môi giới danh tính, phát token mới theo policy downstream | Không chỉ đổi tên upstream token |

Spring Boot cấu hình client, resource server và authorization server ở **các namespace khác nhau**. Sao chép property `oauth2.resourceserver.jwt.issuer-uri` sang một ứng dụng login **không tạo endpoint `/oauth2/token`**.

## 4. Phân biệt SAMLResponse, ID Token, access token và cookie

| Đối tượng | Nguồn phát | Bên nhận hợp lệ | Mục đích |
| --- | --- | --- | --- |
| SAML Response/Assertion | SAML IdP | SP ACS | Xác thực danh tính theo SAML federation |
| OIDC ID Token | OIDC Provider | **OIDC client/RP** | Khẳng định sự kiện xác thực, `iss`, `sub`, `aud` của client |
| OAuth access token | OAuth Authorization Server | **Resource Server được chỉ định** | Cho phép một client truy cập API trong phạm vi được cấp |
| Refresh token | AS | OAuth2 Client được cho phép | Xin access token mới, không gửi đến Orders API |
| Authorization code | AS | OAuth2 Client qua redirect | Đổi thành token tại token endpoint, theo PKCE/client auth |
| `JSESSIONID` / `SESSION` | SP/web app hoặc Spring Session | Browser → đúng web app | Duy trì phiên ứng dụng, không phải access token API |
| Opaque token | AS | Client sử dụng, RS introspect | Access token dạng tham chiếu, không tự chứa claims để API decode |

**ID Token không phải access token.** OIDC Core quy định `aud` của ID Token bao gồm **client ID của RP**. JWT access token dành cho Orders API phải có audience phù hợp **Orders API**. Một RS không được chấp nhận mọi JWT do cùng OP ký rồi coi chúng đều là API access token.

**Một user đã đăng nhập web không đồng nghĩa browser tự sở hữu quyền Bearer với backend.** Web có thể dùng server-side `OAuth2AuthorizedClientManager` để lấy access token và gọi API qua BFF; browser chỉ giữ cookie của BFF. Hoặc một public client/mobile app nhận token bằng Authorization Code + PKCE theo cấu hình riêng. Các mô hình này khác nhau về nơi lưu token và rủi ro XSS/CSRF.

## 5. Ví dụ JWT minh họa: audience của client và của API

OIDC ID Token dành cho client `portal-client`:

```json
{
  "iss": "https://auth.example.test",
  "sub": "user-1001",
  "aud": "portal-client",
  "iat": 1799999000,
  "exp": 1800000000,
  "nonce": "nonce-from-authorization-request"
}
```

JWT access token dành cho Orders API:

```json
{
  "iss": "https://auth.example.test",
  "sub": "user-1001",
  "aud": ["orders-api"],
  "client_id": "portal-client",
  "scope": "orders.read orders.write",
  "iat": 1799999000,
  "exp": 1800000000,
  "jti": "example-access-token-id"
}
```

Hai JSON trên **chỉ mô tả claims**, không phải JWT hoàn chỉnh, không có chữ ký, không được dùng để login hoặc gọi API. Các timestamp chỉ là dữ liệu ví dụ, không cam kết còn hạn tại thời điểm đọc.

Nếu hệ thống dùng **RFC 9068 JWT access token profile**, header còn có `typ=at+jwt` hoặc `application/at+jwt`, cùng JWS algorithm/signature hợp lệ. Các AS không theo RFC 9068 có thể dùng profile riêng; API phải kiểm tra đúng profile/token type mà AS đã cam kết, không chỉ kiểm tra ba phần Base64URL của JWT.

**Đừng coi `sub` luôn là user ID nội bộ**: subject có phạm vi issuer, và token từ `client_credentials` có thể đại diện cho ứng dụng, không phải con người.

## 6. Authorization Server cấu hình ở đâu?

Nếu tổ chức cần **phát hành OAuth tokens của chính mình**, tạo một ứng dụng Authorization Server riêng hoặc một role AS được cấu hình rõ. Trong Spring Boot 3.x/Spring Authorization Server 1.x, dependency gốc:

```groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-oauth2-authorization-server"
}
```

Đây là **mảnh Gradle**, giả định project đã có plugins Java/Spring Boot, BOM, repositories và Java 17+. AS còn phải có các thành phần:

- `RegisteredClientRepository`: client IDs, client authentication methods, redirect URIs, grant types, scopes, consent, PKCE policies.
- `OAuth2AuthorizationService`: lưu authorizations/refresh tokens và trạng thái tương ứng.
- `AuthorizationServerSettings`: issuer và các protocol endpoint paths.
- `OAuth2TokenGenerator` / `OAuth2TokenCustomizer`: phát hành token, token claims/format.
- `JWKSource`, key management và rotation cho signed JWTs.
- Cơ chế xác thực người dùng khi grant cần resource owner; OIDC support nếu AS đóng vai OP.
- CSRF/consent/session/rate limiting/audit phù hợp protocol endpoints và hạ tầng.

Spring Security 7.x hiện có bộ tài liệu Authorization Server trong chính Spring Security. **API lớp/package giữa các nhánh phải được chọn theo release**, không copy lẫn code Spring Authorization Server 1.x và Spring Security 7.x.

### Các endpoint AS điển hình

| Endpoint | Tác dụng |
| --- | --- |
| `/oauth2/authorize` | Authorization endpoint |
| `/oauth2/token` | Token endpoint |
| `/oauth2/jwks` | Public JWK Set phục vụ verify |
| `/oauth2/introspect` | Token introspection |
| `/oauth2/revoke` | Token revocation |
| `/.well-known/oauth-authorization-server` | AS metadata |
| `/.well-known/openid-configuration` | OIDC OP discovery khi bật |
| `/userinfo` | OIDC UserInfo nếu hỗ trợ |

Đây là những **endpoint của AS**, không phải các controller ở Orders API. Đừng tự thêm một `@PostMapping("/oauth2/token")` trong API rồi coi đã có AS an toàn.

## 7. AS settings và trách nhiệm phát đúng audience

Trong ứng dụng **Authorization Server**, issuer là danh tính phát hành token. Mảnh Java Spring Authorization Server 1.x:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.test")
            .build();
}
```

Đây **không phải class độc lập**: cần khai báo trong AS `@Configuration` và import lớp thư viện phù hợp. Issuer của token phải khớp issuer này, còn API sẽ cấu hình **giá trị đã phê duyệt** làm expected issuer.

AS cũng phải phát **access token dành cho đúng API**, không mặc định mọi token do nó phát đều có quyền đối với mọi resource. Với Spring Authorization Server, một `OAuth2TokenCustomizer<JwtEncodingContext>` có thể thêm `aud` cho **access token** theo policy client/scope/resource:

```java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> ordersAudience() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && context.getAuthorizedScopes().contains("orders.read")) {
            context.getClaims().audience(java.util.List.of("orders-api"));
        }
    };
}
```

Đây là **mảnh code minh họa ở AS**, không thuộc Resource Server. Trong production, việc xác định `aud` phải dựa trên **registered client, resource indicator (RFC 8707 khi hỗ trợ), scopes được cấp và chính sách AS**, không chỉ dựa vào một scope dùng chung. Đừng sửa ID Token `aud` thành audience API.

Không phát `orders.write` chỉ vì client yêu cầu scope này; AS phải kiểm tra quyền client, resource owner và consent/policy. API còn phải kiểm tra quyền object cụ thể dù token có scope đã được cấp.

## 8. Spring Boot property: client, AS và Resource Server hoàn toàn khác nhau

| Prefix | Đặt ở đâu? |
| --- | --- |
| `spring.security.oauth2.client.registration.*` | OIDC/OAuth2 Client (client ID/secret, scopes, redirect) |
| `spring.security.oauth2.client.provider.*` | Client: issuer, authorization/token/JWKS endpoints do OP/AS cung cấp |
| `spring.security.saml2.relyingparty.registration.*` | SAML SP: metadata IdP, SP Entity ID, ACS, keys |
| `spring.security.oauth2.authorizationserver.*` | Authorization Server: registered clients/AS settings |
| `spring.security.oauth2.resourceserver.jwt.*` | Resource Server: issuer/JWKS/audience/algorithms để **verify** JWT |
| `spring.security.oauth2.resourceserver.opaquetoken.*` | Resource Server: introspection endpoint và credentials |
| `server.servlet.session.cookie.*` | Web app session cookie, không phải OAuth token verifier |

Cấu hình issuer bên client và bên Resource Server có thể **bằng nhau** nếu cùng AS/OP, nhưng mục đích khác: client dùng issuer để xác thực **OIDC login/authorized client**, còn RS dùng issuer để xác minh **Bearer access token**.

### Một lỗi thực tế

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://auth.example.test"
```

Đoạn này **không tạo Authorization Server** và không tự cấp access token. Nó giúp API biết issuer cần tin khi verify JWT.

## 9. Bảo vệ API bằng JWT: chữ ký, issuer, audience và thời hạn

Một request OAuth Bearer:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_REDACTED
```

API phải:

1. Đọc token từ `Authorization` header theo Bearer policy, không từ cookie SSO hay query param.
2. Xác minh JWS signature với **trusted JWKS/public key** thuộc AS đã provision; `kid` chỉ hỗ trợ chọn trong bộ khóa tin cậy.
3. Kiểm tra `iss` khớp AS issuer expected.
4. Kiểm tra `exp`/`nbf`; clock skew giới hạn.
5. Kiểm tra `aud` chứa resource identifier **của Orders API**.
6. Kiểm tra token type/profile: không nhận ID Token thay access token.
7. Chuyển `scope`/`scp` thành authorities theo mapper đã được phê duyệt.
8. Kiểm tra HTTP method, scope, tenant, owner/ACL, trạng thái bản ghi.
9. Fail-closed nếu bất kỳ bước nào không đáp ứng.

**Verify chữ ký đúng chưa có nghĩa được sử dụng ở API này.** Token có `aud=billing-api` có thể ký bởi **cùng AS** nhưng phải bị Orders API từ chối. Token có scope `orders.read` cũng không tự cho phép xem mọi đơn hàng của mọi tenant.

## 10. JWT Resource Server Spring Boot 3.5+/Security 6.5

Trong **API project** có thể dùng các dependencies:

```groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.boot:spring-boot-starter-oauth2-resource-server"
}
```

Đây là mảnh build file trong dự án đã có Java 17+/Spring Boot plugins/BOM.

Ví dụ `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://auth.example.test"
          jwk-set-uri: "https://auth.example.test/oauth2/jwks"
          audiences: "orders-api"
```

Ý nghĩa:

- `issuer-uri` là **issuer được API chấp thuận**, dùng verify `iss`.
- `jwk-set-uri` trỏ trusted JWKS endpoint đã được cấu hình. Khi có cả issuer và JWKS, RS không nhất thiết phải gọi discovery ngay lúc startup, nhưng vẫn verify issuer.
- `audiences` trong Boot 3.5+ đặt audience kỳ vọng, hỗ trợ kiểm tra `aud`.
- Đây là **cấu hình xác minh**, không phải endpoint phát token.

Với Boot/Security version khác, kiểm tra property support của chính release; nếu `audiences` chưa có thì thêm `OAuth2TokenValidator<Jwt>` theo API version thay vì mặc định bỏ audience check.

Nếu AS chỉ là SAML IdP không có OAuth token endpoint/JWKS, **không được dùng SAML metadata URL làm `jwk-set-uri`**. SAML XML signing certificate và OAuth JWT verification key có thể khác hệ thống và khác trust contract.

## 11. Cấu hình ứng dụng có web login và Bearer API riêng biệt

Có thể triển khai **hai ứng dụng** (dễ cô lập security boundaries hơn). Nếu web và API ở chung một Spring Boot application, tạo **hai SecurityFilterChain**:

- API `/api/**` dùng stateless Bearer, không dựa vào session cookie.
- Web `/web/**` dùng OIDC/SAML browser login và HTTP session với CSRF mặc định.

Ví dụ tổng hợp dưới đây cho phép học cả hai, nhưng **không có Authorization Server trong app**.

### 11.1. Dependencies

Trong `build.gradle` của dự án Spring Boot đã có plugins và dependency management:

```groovy
repositories {
    mavenCentral()
    // Khi bộ OpenSAML của Spring Security yêu cầu thêm repository:
    maven { url "https://build.shibboleth.net/maven/releases/" }
}

dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.boot:spring-boot-starter-oauth2-client"
    implementation "org.springframework.boot:spring-boot-starter-oauth2-resource-server"
    implementation "org.springframework.security:spring-security-saml2-service-provider"
}
```

### 11.2. application.yml

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
        provider:
          corp:
            issuer-uri: "https://auth.example.test"
      resourceserver:
        jwt:
          issuer-uri: "https://auth.example.test"
          jwk-set-uri: "https://auth.example.test/oauth2/jwks"
          audiences: "orders-api"
    saml2:
      relyingparty:
        registration:
          partner:
            assertingparty:
              metadata-uri: "${SAML_IDP_METADATA_URI}"
```

OIDC client, SAML SP và RS dùng **ba cấu hình trách nhiệm khác nhau**. Những giá trị trong `${...}` là biến môi trường/secret manager sau khi đổi thành cú pháp Spring `${...}` thực tế qua ví dụ, **không** điền credentials thật vào tài liệu hoặc source control. Public hostname `example.test` là placeholder.

### 11.3. Class Java đầy đủ

Lưu `src/main/java/demo/boundary/TokenBoundaryApplication.java`:

```java
package demo.boundary;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class TokenBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(TokenBoundaryApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .saml2Login(Customizer.withDefaults())
                .build();
    }

    @GetMapping("/")
    public String home() {
        return "Use /web/me or /api/orders/42 with an access token";
    }

    @GetMapping("/web/me")
    public String me() {
        return "Authenticated browser session";
    }

    @GetMapping("/api/orders/{id}")
    public Map<String, Object> read(@PathVariable long id) {
        // Demo không lấy dữ liệu thật. Production còn kiểm tra
        // owner, tenant, role và ACL của chính đơn hàng.
        return Map.of("orderId", id, "status", "visible");
    }

    @PostMapping("/api/orders/{id}")
    public Map<String, Object> update(@PathVariable long id) {
        // Chỉ mô phỏng; production cần transaction và domain policy.
        return Map.of("orderId", id, "status", "updated-demo");
    }
}
```

**Giải thích các ranh giới trong code:**

1. `@Order(1)` với `securityMatcher("/api/**")` ưu tiên Bearer resource server cho API.
2. `oauth2ResourceServer().jwt()` lấy `JwtDecoder` từ Boot auto configuration với issuer/JWKS/audience ở YAML. Không có code tự ký JWT.
3. `SessionCreationPolicy.STATELESS` không tạo authenticated browser session chỉ từ API Bearer request.
4. `csrf.disable()` chỉ áp dụng **API chain**. Điều này chỉ đúng nếu API thực sự sử dụng Bearer trong Authorization header và không tự nhận ambient browser session cookies. Với cookie-authenticated API, phải giữ CSRF policy phù hợp.
5. `GET /api/orders/**` đòi `SCOPE_orders.read`; `POST` đòi `SCOPE_orders.write`; các method còn lại bị deny theo fallback.
6. `@Order(2)` web chain vẫn giữ browser login, HTTP session và CSRF protection.
7. `/login/oauth2/code/corp` và `/login/saml2/sso/partner` thuộc web authentication protocol, **không** thuộc `/api/**`.
8. Không có bean `AuthorizationServerSettings`/`RegisteredClientRepository`/`JWKSource` vì project **không phát token**.

Scope ở ví dụ chỉ bảo vệ route; đừng dùng code này như triển khai đơn hàng thật khi chưa có owner/tenant/object authorization.

### Chạy và kết quả

Dự án cần OIDC provider và SAML IdP thật cùng một AS JWT issuing endpoint/JWKS đã được cấu hình. Khi thay placeholder bằng môi trường sandbox hợp lệ, chạy:

```bash
OIDC_CLIENT_ID=portal-client \
OIDC_CLIENT_SECRET=from-secret-store \
SAML_IDP_METADATA_URI=https://saml.example.test/metadata \
./gradlew bootRun
```

Không có stdout login/token cố định; output phụ thuộc AS/IdP và credentials. Khi gọi API với **access token đúng issuer, audience và scope** thì GET `/api/orders/42` trả JSON:

```json
{"orderId":42,"status":"visible"}
```

Khi token sai chữ ký/hết hạn/sai `aud`, RS từ chối authentication. Nếu token hợp lệ nhưng thiếu scope phù hợp, HTTP authorization từ chối. Đó là hành vi đúng, không phải bug do session SSO.

## 12. Gọi API với token và phân biệt response 401/403

Client gọi:

```bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.test/api/orders/42
```

`ACCESS_TOKEN` phải được nhận qua một **OAuth grant hợp lệ** và dành cho Orders API. Không thay bằng OIDC ID Token, refresh token, SAMLResponse hoặc session cookie. Ví dụ `api.example.test` là host tượng trưng; nếu chạy local phải dùng URL/port ứng dụng thực.

| Trường hợp | Kết quả thông thường |
| --- | --- |
| API thiếu Authorization Bearer | **401 Unauthorized** |
| Bearer sai chữ ký, issuer, audience hoặc hết hạn | **401 Unauthorized** |
| ID Token bị từ chối do audience/token type | **401 Unauthorized** |
| Token hợp lệ nhưng thiếu `orders.read` cho GET | **403 Forbidden** |
| Token có `orders.read` nhưng user không được đọc order 42 | **403**, hoặc response che tồn tại tài nguyên theo policy |
| Web `/web/me` chưa có session | Thường **302 redirect** đến login/IdP |
| Đã đăng nhập web nhưng gọi API không có Bearer | **401** ở API chain stateless |

Bearer handling có thể thêm `WWW-Authenticate` theo RFC 6750. Một HTTP 401 của API **không chứng minh** IdP SSO của web app thất bại; có thể chỉ do token thiếu/sai audience.

## 13. JWT authentication và quyền scope

Sau khi Spring Security Resource Server xác minh JWT, `Authentication` thường là `JwtAuthenticationToken`, principal là `Jwt`. Spring Security mặc định dùng `JwtGrantedAuthoritiesConverter` để map claim `scope` hoặc `scp` thành authorities có tiền tố **`SCOPE_`**.

Ví dụ `scope="orders.read orders.write"` được map thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Với `authorizeHttpRequests` hoặc `@PreAuthorize`:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.write')")
public void updateOrder(long id) {
    // Chưa đủ nếu không có owner/tenant/domain policy.
}
```

Đây là **mảnh Java minh họa**, cần `@EnableMethodSecurity` và service Spring-managed; không phải class chạy độc lập. `hasAuthority("SCOPE_orders.write")` kiểm tra đúng authority đã map, **khác** `hasRole("ADMIN")` (mặc định sẽ tìm `ROLE_ADMIN`).

Nếu AS dùng custom claims, cấu hình `JwtAuthenticationConverter` theo hợp đồng issuer. Không tự chuyển mọi `groups=["admins"]` thành `ROLE_ADMIN` vì một AS hoặc tenant ít tin cậy có thể có nhóm tên giống nhau. Authorization domain cần local permissions và resource ACL.

## 14. Audience validation và JwtDecoder tùy biến

Spring Boot 3.5+ hỗ trợ `spring.security.oauth2.resourceserver.jwt.audiences`. Nếu dự án có yêu cầu validator riêng, đừng thay default issuer/time validation bằng lambda chỉ kiểm tra audience.

Ví dụ **mảnh Bean** cho API, dùng trong một `@Configuration` có `app.jwt.issuer` và `app.jwt.jwks-uri`:

```java
@Bean
JwtDecoder jwtDecoder(
        @Value("${app.jwt.issuer}") String issuer,
        @Value("${app.jwt.jwks-uri}") String jwksUri) {

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

    OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience() != null
                    && jwt.getAudience().contains("orders-api")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Audience orders-api required",
                                    null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(defaults, audience));
    return decoder;
}
```

Các import thuộc `org.springframework.security.oauth2.jwt.*`, `org.springframework.security.oauth2.core.*`, `org.springframework.security.oauth2.core.validator.*`, `org.springframework.beans.factory.annotation.Value`, `org.springframework.context.annotation.Bean`. Đây **không phải class Java độc lập**; dùng nó làm **phương án thay thế** auto-config decoder nếu thật sự cần.

**Cảnh báo:** khi tự khai báo `JwtDecoder @Bean`, bạn có thể thay Boot decoder mặc định. Phải giữ đầy đủ các validators cần thiết: issuer, timestamps, audience, token type/profile và đúng algorithms. Không kỳ vọng property `audiences` tự áp dụng thêm lên bean do bạn tự dựng.

Với RFC 9068, cần type-aware validator phù hợp bản Spring Security, chẳng hạn `JwtValidators.createAtJwtValidator()` và cấu hình decoder không chặn/diễn giải sai `typ=at+jwt`. Kiểm tra Javadoc đúng phiên bản; `createDefaultWithIssuer` **không tự khẳng định** API tuân mọi yêu cầu RFC 9068.

## 15. JWT access token profile khác với bất kỳ JWT hợp lệ nào

RFC 9068 cung cấp profile cho **OAuth2 JWT access tokens**. Những yêu cầu quan trọng bao gồm:

- Access token phải được ký, không chấp nhận `alg=none`.
- Header `typ` cho biết `at+jwt` (hoặc dạng đầy đủ `application/at+jwt`).
- `iss`, `exp` và `aud` có ngữ nghĩa rõ; `aud` chỉ resource server thích hợp.
- RS xác minh chữ ký bằng key đã tin, issuer, thời hạn và token type.
- Claims ủy quyền được xét cùng chính sách đối tượng/tài nguyên.

Nếu API tuyên bố chỉ nhận token theo profile đó, **ID Token** có `typ=JWT` hoặc `aud=portal-client` phải bị từ chối, dù cả hai dùng cùng OP signing key. Nếu AS dùng profile JWT access token khác, vẫn phải có cách phân biệt ID Token và access token theo thỏa thuận issuer, audience, token type và policy — không dựa duy nhất vào việc chuỗi “trông giống JWT”.

Không lấy `kid`/`jku`/`x5u` từ JWT header để tải khóa bất kỳ trên Internet. `kid` chỉ là key identifier giúp chọn giữa **những keys đã được tin cậy**. Dynamic key fetching từ unverified input có thể dẫn đến SSRF và self-established trust.

## 16. Opaque token introspection thay JWT local validation

AS có thể phát **reference/opaque access token** thay vì JWT. API không thể xác minh bằng cách parse claims. Thay vào đó, Resource Server gọi **OAuth2 Token Introspection Endpoint** (RFC 7662).

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant API as Orders Resource Server
    participant AS as Authorization Server
    Client->>API: Authorization: Bearer opaque-token
    API->>AS: Introspection request + RS client credentials
    AS-->>API: active, scope, exp, sub, aud ... theo policy
    API->>API: Kiểm tra active, resource audience, scope, local ACL
    API-->>Client: 200 hoặc 401/403
```

**API project** khi dùng opaque token có thể cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: "https://auth.example.test/oauth2/introspect"
          client-id: "${INTROSPECTION_CLIENT_ID}"
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

Và thay DSL JWT bằng:

```java
.oauth2ResourceServer(oauth -> oauth
        .opaqueToken(Customizer.withDefaults()))
```

Hai đoạn là **phương án thay thế**, không phải lúc nào cũng bật song song JWT và opaque. Token được introspection trả `active=true` **không tự đủ quyền**: RS vẫn cần audience/resource, scope, tenant/ACL và các điều kiện policy thích hợp.

### Trade-off

| Tiêu chí | JWT tự verify bằng JWKS | Opaque introspection |
| --- | --- | --- |
| Mạng đến AS mỗi request | Thường không nếu key đã cache | Thường có, trừ caching |
| Thu hồi tức thời | Khó nếu JWT còn hiệu lực mà không có denylist | Có thể phản ánh revocation nhanh hơn tùy cache |
| Latency | Thường thấp hơn | Có độ trễ network |
| Khả năng chạy khi AS tạm outage | Có thể tiếp tục với trusted cached keys | Thường không verify được, cần fail-closed |
| Metadata trong token | JWT payload thường đọc được (không tự encrypted) | Opaque không tự tiết lộ claims |
| Phân quyền object | Vẫn phải thực hiện | Vẫn phải thực hiện |

Nếu cache introspection, phải chấp nhận **cửa sổ revocation delay** và bảo vệ cached token state. Secrets để gọi introspection thuộc **Resource Server**, không đưa vào browser/JavaScript.

## 17. Scope khác với quyền trên từng bản ghi

Scope `orders.read` nói rằng token được phép yêu cầu chức năng đọc đơn hàng **theo chính sách AS/RS**. Nó **không** chứng minh user/client được đọc đơn hàng `orderId=42`. Một token đúng scope có thể vẫn bị từ chối vì:

- Đơn hàng thuộc tenant khác.
- Local user chưa được liên kết hoặc đã bị disable.
- Người dùng không thuộc danh sách owners/readers.
- Order đã chuyển trạng thái, không cho sửa.
- Token thuộc machine client nhưng API cần user delegation.
- Giao dịch cần MFA/freshness bổ sung ngoài scope.

Mô hình quyết định:

```text
allow = tokenVerified
    AND expectedIssuer
    AND expectedAudience
    AND tokenWithinValidityWindow
    AND requiredScope
    AND localIdentityOrClientAllowed
    AND tenantMatchesResource
    AND resourcePolicyAllowsAction
    AND optionalAssuranceFreshnessSatisfied
```

Đây là pseudocode, không phải SpEL chạy trực tiếp. Cần **authorization ở service/domain/repository** bên cạnh `authorizeHttpRequests` để chống IDOR/BOLA; đồng thời tránh TOCTOU bằng transaction/atomic update cho nghiệp vụ có side effects.

Với `client_credentials`, token có thể không đại diện con người; API nên phân biệt **service identity** với **end-user identity**. Không dùng `sub` như user ID nội bộ nếu profile AS quy định subject là client.

## 18. Identity broker: upstream login và downstream issuance

Một broker có thể là **OIDC Client/SAML SP** của một IdP ngoài, và đồng thời là **Authorization Server** cho ứng dụng/API nội bộ. Đây là hai trust domains:

1. Broker nhận upstream SAMLResponse/ID Token, xác minh issuer/signature/audience/time/correlation.
2. Broker liên kết external subject với **local user** theo chính sách, không auto-link bằng email trùng.
3. Broker đánh giá liệu client downstream được phép nhận token, scope, resource/audience và độ mới của authentication hay không.
4. Nếu broker thực sự có AS module, broker phát **access token mới** với issuer và signing keys của broker, audience của API và scopes đã được cấp.
5. API xác minh downstream token bằng **trusted broker issuer/JWKS**, không lấy upstream SAML assertion làm bearer.

**Không có một conversion ngầm “SAMLResponse → JWT” khi bật `saml2Login`.** Nếu broker chỉ làm login proxy, nó không nhất thiết có `/oauth2/token` và không tự phát Bearer. Muốn thực hiện token issuance phải triển khai AS và protocol flows thực sự.

Khi truyền danh tính service A → B, cân nhắc OAuth2 Token Exchange (RFC 8693) nếu AS hỗ trợ, hoặc grant/service-to-service/BFF được thỏa thuận. Không chuyển nguyên access token có `aud=api-a` đến `api-b` và bỏ audience validation chỉ để “đỡ cấp token mới”.

## 19. Multi-issuer Resource Server: unverified iss chỉ được chọn verifier

Nếu Orders API tin nhiều AS (ví dụ North và South), Spring Security hỗ trợ:

```java
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://north-auth.example.test",
                "https://south-auth.example.test");

http.oauth2ResourceServer(oauth -> oauth
        .authenticationManagerResolver(resolver));
```

Đây là **mảnh SecurityFilterChain**, không phải Java SE độc lập. Nó minh họa cách chọn verifier từ **trusted issuers** đã có. Claim `iss` chưa được verify có thể giúp chọn một verifier, nhưng verifier sau đó mới kiểm tra signature/issuer.

Không làm:

```text
issuer = unverifiedJwt.getClaim("iss")
decoder = JwtDecoders.fromIssuerLocation(issuer)
acceptJwtIfDecoderSucceeds()
```

Đó là **dynamic trust**. Attacker có thể tự dựng issuer/JWKS rồi ký token. Nguồn issuer phải là allowlist được quản trị hoặc repository thêm/thu hồi qua quy trình được phê duyệt. Mỗi issuer còn cần audience/type/scopes và tenant authorization riêng; một JWT hợp lệ từ South không tự cấp quyền North.

## 20. Session cookie, CSRF và Bearer API là hai bối cảnh khác nhau

Web federation dùng cookie session `JSESSIONID` hoặc `SESSION`. Browser thường tự gắn cookie phù hợp; vì thế web app cần CSRF protection cho form/method có side effects, kể cả khi đăng nhập qua SAML/OIDC.

Một API chỉ nhận token trong `Authorization` header thường **không dựa vào ambient cookie**. Nếu nó thực sự Bearer-only, stateless và không có cookie authentication, có thể đặt `csrf.disable()` **chỉ trong API SecurityFilterChain**. Không tắt CSRF cho web login/action chain để “làm SAML callback chạy được”.

Các nguyên tắc:

- SAML ACS `/login/saml2/sso/...` nhận form POST theo protocol, phải được Spring Security SAML filter xử lý với signature/issuer/audience/recipient/correlation checks.
- OIDC callback `/login/oauth2/code/...` thuộc OAuth2 login flow và phải kiểm tra `state`/nonce/issuer theo protocol.
- API `/api/**` nhận Bearer, thiếu token thường 401 thay vì redirect IdP.
- CORS điều khiển trình duyệt ở cross-origin JS requests, **không cấp quyền API** và không thay issuer/audience validation.
- Nếu API dùng cookie/session song song, **đừng copy chế độ tắt CSRF của Bearer-only API**.
- BFF có thể giữ access token ở server-side và browser giữ session cookie của BFF; khi đó BFF vẫn cần CSRF/XSS/session protections.

## 21. Bearer token và bảo vệ bí mật

Access token và refresh token là **credentials nhạy cảm**. Thực hành:

- Dùng HTTPS toàn bộ; không chuyển token trên URL query `?access_token=...`.
- Gửi access token qua `Authorization: Bearer` header, không tự đặt vào SAML `RelayState`.
- Không log raw token, `Authorization` headers, ID Token, SAMLResponse, cookies hoặc client secrets.
- Refresh token nằm ở OAuth2 Client được cấp phép, **không gửi tới API nghiệp vụ**.
- Giới hạn TTL access token; cân nhắc refresh-token rotation, revocation/introspection theo AS policy.
- Quản lý JWKS rotation và public key cache có giới hạn; không tự thêm key từ `jku`/`x5u`.
- Public clients (SPA/mobile) không thể giữ client secret an toàn như confidential server client; dùng Authorization Code + PKCE theo policy.
- Với BFF, token nên được lưu server-side và không exposed không cần thiết tới browser JS.
- Nếu phải revoke quyền ngay, đánh giá trade-off JWT self-contained so với introspection/denylist.

**HTTPS/TLS không thay JWT signature verification**; chúng bảo vệ những ranh giới khác nhau. Và signature verification không thay audience/scope/ACL.

## 22. Java 17 độc lập: mô phỏng policy sau khi access token đã được xác minh

Chương trình dưới đây **không decode/verify JWT**. Nó mô phỏng quyết định authorization **sau khi** thư viện Resource Server đã xác minh token. Cờ `verified` trong ví dụ chỉ là input test, **không được lấy từ HTTP header hoặc token do người dùng tự khai**.

Lưu file `VerifiedApiPolicyDemo.java`:

```java
import java.util.Set;

public final class VerifiedApiPolicyDemo {

    record VerifiedToken(
            boolean verified,
            String issuer,
            Set<String> audiences,
            Set<String> scopes,
            String tenant) {
    }

    static boolean canRead(VerifiedToken token, String resourceTenant) {
        return token != null
                && token.verified()
                && "https://auth.example.test".equals(token.issuer())
                && token.audiences().contains("orders-api")
                && token.scopes().contains("orders.read")
                && token.tenant().equals(resourceTenant);
    }

    public static void main(String[] args) {
        VerifiedToken valid = new VerifiedToken(
                true, "https://auth.example.test",
                Set.of("orders-api"),
                Set.of("orders.read"), "north");

        VerifiedToken otherApi = new VerifiedToken(
                true, "https://auth.example.test",
                Set.of("billing-api"),
                Set.of("orders.read"), "north");

        VerifiedToken noScope = new VerifiedToken(
                true, "https://auth.example.test",
                Set.of("orders-api"),
                Set.of("profile"), "north");

        VerifiedToken unverified = new VerifiedToken(
                false, "https://auth.example.test",
                Set.of("orders-api"),
                Set.of("orders.read"), "north");

        System.out.println("allowed=" + canRead(valid, "north"));
        System.out.println("wrongAudience=" + canRead(otherApi, "north"));
        System.out.println("missingScope=" + canRead(noScope, "north"));
        System.out.println("wrongTenant=" + canRead(valid, "south"));
        System.out.println("unverified=" + canRead(unverified, "north"));
    }
}
```

Chạy bằng Java 17+:

```bash
javac VerifiedApiPolicyDemo.java
java VerifiedApiPolicyDemo
```

Stdout chính xác:

```text
allowed=true
wrongAudience=false
missingScope=false
wrongTenant=false
unverified=false
```

Nếu trong production, `tenant` từ JWT do một AS không được ủy quyền phát tenant claims thì không được tin để ra quyết định. Hãy map authenticated issuer/subject vào local user và tenant membership theo chính sách ứng dụng. Demo chỉ cho thấy **một lỗi ở bất kỳ điều kiện nào phải dẫn đến deny**.

## 23. Ma trận kiểm thử tối thiểu

| Test | Token/login | Kết quả |
| --- | --- | --- |
| A. OIDC browser login đúng | ID Token verified, web session | `/web/me` hoạt động |
| B. SAML login đúng | Signed SAMLResponse và ACS hợp lệ | Web session được tạo |
| C. Web session cookie gửi tới API Bearer-only | Không có access token | API 401 |
| D. API không có Bearer | Missing Authorization header | 401 |
| E. JWT sai chữ ký | Key không thuộc trusted JWKS | 401 |
| F. JWT issuer không approved | `iss` lạ | 401 |
| G. JWT hết hạn | `exp` trong quá khứ | 401 |
| H. JWT chưa hiệu lực | `nbf` tương lai | 401 |
| I. JWT sai audience | `aud=billing-api` | 401 |
| J. ID Token dùng như Bearer | `aud=portal-client`/wrong type | 401 |
| K. Access token GET đủ scope | `orders.read` + audience đúng | 200 nếu ACL cho phép |
| L. Access token POST thiếu write scope | Chỉ `orders.read` | 403 |
| M. Đủ scope nhưng order tenant khác | Cross-tenant | Deny theo resource ACL |
| N. Opaque `active=false` | Introspection không active | 401 |
| O. Introspection endpoint outage | Không xác minh được token | Fail-closed |
| P. Multi-issuer unknown `iss` | Issuer lạ | Không dynamic trust |
| Q. JWT header có `jku` attacker | Key URL chưa trusted | Không fetch tùy ý |
| R. AS signing key rotate hợp lệ | JWKS updated, issuer đúng | Token mới có thể verify |
| S. Machine token `client_credentials` | Không có human principal | Chỉ service permissions |
| T. Scope mapping admin không được ủy quyền | `groups=admin` claim lạ | Không cấp role nội bộ |
| U. Same-site browser POST với CSRF thiếu | Session/cookie authentication | Web CSRF filter deny |
| V. Token còn hạn nhưng local user disabled | Trạng thái business revocation | Domain policy deny |

Dùng Spring Security Test `jwt()` để test HTTP authorization/mapping **không chứng minh** validation chữ ký thật. Cần integration test qua `JwtDecoder` có keys sandbox, issuer/audience mismatches và test với AS hợp lệ để kiểm tra toàn bộ pipeline.

Đừng dùng production tokens/refresh tokens/raw SAMLResponse trong test fixtures public hoặc ticket; nếu cần trace, redact secrets.

## 24. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| 401 ở API nhưng SSO web vẫn hoạt động | Web cookie ≠ Bearer access token | Client lấy token đúng grant/resource |
| 401 invalid issuer | AS issuer khác expected `issuer-uri` | Kiểm tra issuer được phê duyệt, không bỏ issuer validator |
| 401 invalid audience | Token dành cho API khác hoặc AS chưa set `aud` | Cập nhật AS token policy và RS expected audience |
| 401 invalid signature | JWKS/cert mismatch, rotation | Kiểm tra key từ AS tin cậy, không lấy key từ token header |
| 401 ID Token từ OP | Sai token type/audience | Dùng access token của AS |
| 403 thiếu `SCOPE_orders.write` | Token không được cấp write scope | Kiểm tra client registration/consent/scopes, không cấp mù |
| 403 dù scope hợp lệ | Tenant/ACL/domain policy | Kiểm tra ownership và quyền bản ghi |
| Resource Server startup fail | Không truy cập được issuer discovery/JWKS | Dùng trusted `jwk-set-uri` khi phù hợp và kiểm tra TLS |
| Introspection timeout | AS không sẵn sàng/network/credential | Timeout/fail-closed; giám sát endpoint |
| JWT dùng được mãi dù user logout | JWT self-contained còn `exp` | TTL ngắn/denylist hoặc introspection theo policy |
| OAuth2 client callback lỗi | Client ID/secret, redirectUri, state/nonce | Sửa client registration, không đụng API JwtDecoder |
| SAML ACS lỗi | Metadata/Issuer/Signature/Recipient/session | Debug SAML SP riêng, không coi là JWT API error |
| JWT bị chấp nhận cross-tenant | Chỉ kiểm tra signature, thiếu audience/tenant | Add audience và local tenant policy |
| API bắt đầu redirect tới IdP | Web chain bắt API do matcher order sai | Dùng `@Order`, `securityMatcher`, test từng path |

**Không sửa bằng cách tắt signature validation, bỏ audience, chấp nhận issuer tùy ý hoặc `permitAll("/api/**")`.** Những cách đó làm mất ranh giới bảo mật chính của Resource Server.

## 25. Checklist trước production

- [ ] Mỗi service đã có vai trò rõ: Client/SP, Authorization Server, Resource Server hay broker.
- [ ] AS có registered clients, consent/PKCE/grants, key custody/rotation, issuer, token TTL và audit.
- [ ] ID Token, SAML Assertion, access token và refresh token không bị dùng lẫn.
- [ ] API Bearer-only được bảo vệ bằng `oauth2ResourceServer` chứ không bằng cookie SSO của web app khác.
- [ ] JWT được kiểm tra signature, expected issuer, audience, exp/nbf, profile/token type và algorithms.
- [ ] `jwk-set-uri` chỉ từ trusted AS, không dynamic theo JWT header hay unverified `iss`.
- [ ] JWT scopes được map thành `SCOPE_*` nhất quán, kết hợp owner/tenant/ACL.
- [ ] Multi-issuer API dùng allowlist; unknown issuer fail-closed.
- [ ] Token từ client_credentials không bị nhầm là human user.
- [ ] Nếu dùng opaque token, introspection credentials/timeout/cache/revocation được quản lý.
- [ ] Nếu triển khai broker, upstream auth được verify trước khi downstream AS cấp token có issuer/aud/scope mới.
- [ ] Không forward token dành cho API A sang API B nếu aud không đúng.
- [ ] API chain stateless tách web chain session; CSRF không bị tắt cho web.
- [ ] Browser/BFF bảo vệ session cookie, access/refresh tokens và không lưu secrets không cần thiết.
- [ ] Test 401/403, issuer/aud/signature/time, ID Token confusion, tenant ACL, introspection outage và key rotation.
- [ ] Không log raw token, SAMLResponse, JSESSIONID, private keys hoặc client secrets.
- [ ] Đã ghim phiên bản Spring Boot/Security/Authorization Server và kiểm thử sau nâng cấp.

## 26. Câu hỏi tự đánh giá

**1. `oauth2Login` có phát hành access token không?**  
Không. Client thực hiện login/authorization code flow; AS phát token theo grant và chính sách.

**2. `oauth2ResourceServer().jwt()` làm API trở thành Authorization Server chứ?**  
Không. Nó khiến API xác minh JWT Bearer access tokens.

**3. Một ID Token hợp lệ có nên gọi Orders API không?**  
Không. ID Token dành cho OIDC RP; API cần access token đúng audience/token type/scope.

**4. Vì sao một token có chữ ký đúng vẫn bị 401 ở API?**  
Có thể sai issuer, audience, quá hạn, chưa hiệu lực hoặc sai token profile.

**5. `SCOPE_orders.read` có tự cho phép đọc order bất kỳ không?**  
Không. Vẫn cần tenant/owner/object-level authorization.

**6. Vì sao không lấy `iss` từ unverified JWT rồi tự gọi discovery để tin issuer đó?**  
Vì có thể thành dynamic self-established trust/SSRF; phải dùng trusted issuer allowlist.

**7. Đăng nhập SAML thành công có tự tạo JWT access token downstream không?**  
Không. Cần downstream AS/approved token issuance flow.

**8. Khi nào nên dùng opaque introspection?**  
Khi AS phát opaque/reference token hoặc cần kiểm tra token active qua AS, với trade-off availability/latency/cache.

**9. API chỉ nhận Bearer có thể tắt CSRF không?**  
Có thể trong API chain thực sự stateless, không dùng cookie-authentication. Web chain dùng session vẫn phải bảo vệ CSRF.

**10. 401 và 403 khác nhau thế nào?**  
401 thường do chưa xác thực hoặc token không hợp lệ; 403 thường do đã xác thực nhưng không đủ scope/quyền.

## 27. Tài liệu tham khảo

- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `oauth2Login`, OIDC client registration.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/): `OAuth2AuthorizedClientManager` và token lifecycle.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer, JWKS, audiences, JWT validation và scope mapping.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, active status và cấu hình.
- [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers`.
- [Spring Authorization Server 1.x — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): starter, registered clients, keys, AS setup.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `OAuth2AuthorizationServerConfigurer`, protocol endpoints và issuer.
- [Spring Security — Authorization Server Core Components](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/core-model-components.html): token generator/customizer, JWT/opaque formats.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token validation/audience, issuer và subject.
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): `typ=at+jwt`, aud, iss, token verification.
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): active status và introspection API.
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer Authorization header và error responses.
- [RFC 8707 — OAuth2 Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707.html): chỉ định resource/audience trong access-token request.
- [RFC 8693 — OAuth2 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): delegated token exchange khi AS hỗ trợ.
- [RFC 9700 — OAuth2 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html): chống AS mix-up và OAuth2 client protection.
- [OWASP API Security 2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): owner/tenant/object authorization.
