# Authentication được mock không chứng minh chữ ký hoặc toàn bộ luồng xác thực

## 1. Vấn đề cốt lõi: test HTTP 200 chưa chắc đã kiểm được authentication

Trong Spring Boot, một test bảo mật có thể rất dễ “xanh”:

~~~java
mockMvc.perform(get("/api/orders/me")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
~~~

Hoặc:

~~~java
@Test
@WithMockUser(username = "alice",
              authorities = "SCOPE_orders:read")
void userCanAccessOrders() throws Exception {
    mockMvc.perform(get("/api/orders/me"))
            .andExpect(status().isOk());
}
~~~

Cả hai đều có ích khi kiểm **ủy quyền (authorization)**, nhưng chúng **không chứng minh**:

- Người dùng `alice` có thật trong database/identity provider.
- Password, MFA, session, redirect, OAuth2 Authorization Code hoặc PKCE được thực thi.
- Client đã gửi `Authorization: Bearer ...` hợp lệ qua network.
- JWT có chữ ký đúng thuật toán và được ký bằng private key thuộc issuer đáng tin.
- JWT được `JwtDecoder` thật xác thực theo public key/JWKS.
- `iss`, `aud`, `exp`, `nbf`, token type và những claims bắt buộc được kiểm đúng.
- Token giả mạo, hết hạn, sai audience hoặc bị thay payload sẽ bị từ chối.
- Key rotation và JWKS discovery hoạt động với authorization server thật.

Đây không phải lỗi của `@WithMockUser` hoặc `jwt()`. Các helper này **cố tình** đưa một `Authentication` dựng sẵn vào Spring Security test context để giúp bạn kiểm policy mà không cần login/token signing. Lỗi xảy ra khi diễn giải kết quả test vượt ra ngoài phạm vi nó đã thực thi.

Bài này hướng dẫn phân tầng kiểm thử Spring Security theo mục tiêu, dùng ví dụ **Java 17, Spring Boot 3.5.16, Spring Security 6.5, JUnit Jupiter, MockMvc** và một bài lab tạo RSA key pair ngay trong test rồi ký JWT thật bằng `NimbusJwtEncoder`. Đường HTTP Bearer đi qua filter và `NimbusJwtDecoder` thật; các trường hợp giả chữ ký, sai issuer/audience, expired, future nbf và thiếu scope được kiểm riêng.

### Mục tiêu học tập

1. Phân biệt **authentication** (xác định ai), **authorization** (được làm gì) và **token validation** (chứng thực bằng chứng).
2. Hiểu chính xác phạm vi của `@WithMockUser`, `user()`, `jwt()`, `oauth2Login()`, `oidcLogin()` và mock `JwtDecoder`.
3. Không coi sự tồn tại của một `SecurityContext` được dựng sẵn là bằng chứng đã trải qua login.
4. Hiểu JWT ba phần header.payload.signature, chữ ký JWS và tính chất *decoded payload chưa được tin cậy*.
5. Kiểm Bearer token thật qua `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider` và `JwtDecoder`.
6. Phân biệt HTTP `401 Unauthorized` với `403 Forbidden`.
7. Kiểm RSA signature, issuer, audience, expiration, not-before, scope/authority và forbidden algorithm.
8. Hiểu vì sao signed-token resource-server test chưa thay thế kiểm toàn bộ OAuth2/OIDC Authorization Code + PKCE, token endpoint, MFA, cookies và session.
9. Dùng test-only key pair không cần private key thật, không chạm issuer production.
10. Chọn unit, MVC slice, security filter-chain integration và identity-provider end-to-end test theo rủi ro.

## 2. Ba khái niệm thường bị trộn lẫn

### 2.1. Authentication: xác định danh tính

Authentication là quá trình xác minh credentials/evidence của caller:
- Username + password.
- Session cookie có server-side session hoặc token.
- Bearer access token JWT đã được verify.
- Opaque access token đã được introspect.
- mTLS client certificate, passkey/WebAuthn, SAML assertions hoặc cơ chế khác.

Nếu đã có một `Authentication` object trong `SecurityContextHolder`, các phần downstream có thể xem caller là authenticated. Nhưng **việc object được đặt bằng test helper** không có nghĩa credential đã đi qua authentication provider thực.

### 2.2. Authorization: quyết định quyền truy cập

Authorization dùng authorities, scopes, roles, ownership, tenant context và business policy. Ví dụ endpoint:

~~~java
.requestMatchers("/api/orders/me")
.hasAuthority("SCOPE_orders:read")
~~~

Điều này trả lời “caller có authority cần thiết không?”, **không** tự trả lời “authority đó có xuất phát từ một JWT được ký hợp lệ không?”. Nếu test dựng sẵn authority, policy vẫn có thể được kiểm, nhưng nguồn của authority là fixture.

### 2.3. Token validation: chứng thực bằng chứng

Với OAuth2 Resource Server nhận JWT Bearer, một đường thực thường bao gồm:

~~~text
HTTP request
  |
  | Authorization: Bearer eyJ...
  v
BearerTokenAuthenticationFilter
  |
  v
AuthenticationManager / JwtAuthenticationProvider
  |
  v
JwtDecoder
  |-- parse compact JWS
  |-- kiểm thuật toán được tin cậy
  |-- chọn public key phù hợp (local/JWKS)
  |-- verify chữ ký
  |-- validate exp / nbf / iss / aud / token type ...
  v
JwtAuthenticationConverter
  |-- convert scope / scp -> SCOPE_...
  v
JwtAuthenticationToken / SecurityContext
  |
  v
AuthorizationFilter / method security
  |
  v
Controller và business logic
~~~

`MockMvc jwt()` và `@WithMockUser` bắt đầu gần cuối luồng: chúng cung cấp hoặc mô phỏng `Authentication` mà không tạo một Bearer token được ký và verify. Muốn chứng minh chữ ký, phải test đường token evidence thật.

## 3. Phạm vi của các test helpers

### 3.1. @WithMockUser

`@WithMockUser` tạo một user giả trong test context. User không cần tồn tại trong `UserDetailsService`/database. Theo tài liệu Spring Security, `Authentication` được đặt vào context có loại `UsernamePasswordAuthenticationToken`, principal là Spring Security `User`.

~~~java
@WithMockUser(username = "alice",
              roles = "ADMIN")
@Test
void adminPolicy() {
    // Các @PreAuthorize/authorization rules có thể dùng ROLE_ADMIN.
}
~~~

Đây là snippet, không phải test runnable độc lập. Nó có giá trị khi kiểm policy `hasRole("ADMIN")`. Nhưng test **không gọi** password encoder, credential checker, login form, OAuth2 authorization server, Bearer JWT decoder hay MFA.

**Lưu ý roles vs authorities:**
- `roles = "ADMIN"` tạo authority `ROLE_ADMIN`.
- `authorities = "SCOPE_orders:read"` tạo chính xác authority được đặt.
- Spring OAuth2 JWT resource server thường convert scope `orders:read` thành `SCOPE_orders:read`.
- Tên roles/scopes phải khớp chính xác policy; không suy ngược từ một role mock sang JWT scope thực.

### 3.2. MockMvc .with(user(...))

~~~java
mvc.perform(get("/api/orders/me")
        .with(user("alice").authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
~~~

Snippet này sử dụng `SecurityMockMvcRequestPostProcessors.user(...)` và Spring Security MockMvc integration. Nó cũng cung cấp user giả; không gửi một username/password thực để xác minh. Dùng cho request-scoped authorization scenarios.

### 3.3. MockMvc .with(jwt())

~~~java
mvc.perform(get("/api/orders/me")
        .with(jwt().jwt(builder ->
                builder.claim("sub", "alice"))
                .authorities(
                        new SimpleGrantedAuthority(
                                "SCOPE_orders:read"))))
        .andExpect(status().isOk());
~~~

`SecurityMockMvcRequestPostProcessors.jwt()` tạo một `JwtAuthenticationToken` và đưa vào request/SecurityContext. API docs nhấn mạnh các chi tiết được khai báo trực tiếp và **không yêu cầu JWT phải hợp lệ**.

Nó kiểm tốt:
- Quy tắc URL/method policy cho một principal JWT giả lập.
- Mapping authorities được **gán trực tiếp** trong test.
- Controller/service xử lý chính xác principal ID/claims khi SecurityContext đã có.
- Negative case khi caller thiếu authority mà test đặt.

Nó **không** kiểm:
- Chữ ký RSA/ECDSA/HMAC hay `alg`.
- JWKS discovery/refresh, `kid` hoặc key rotation.
- JWT compact serialization từ HTTP header.
- Token `iss`, `aud`, `exp`, `nbf` có bị decoder reject không.
- Authentication filter có thực sự gọi `JwtDecoder` hay không.

Nếu dùng `jwt().authorities(...)`, test thậm chí có thể gán scope đúng **dù JWT mock không chứa scope claim tương ứng**. Đó là điều tốt cho policy isolation, nhưng sai nếu ghi nhãn “đã test scope claim converter end-to-end”.

### 3.4. Mock JwtDecoder

Với `@MockitoBean JwtDecoder decoder` và stub:

~~~java
when(decoder.decode("sample-token"))
        .thenReturn(fakeJwt);
~~~

Có thể test việc Bearer header đi đến filter, decoder được gọi và một `Jwt` object được convert/authorized. Nhưng đây vẫn **không phải chữ ký thật**: decoder mock trả về object theo test, ngay cả khi token string không có chữ ký. Muốn verify chữ ký phải dùng decoder thật với key thật **dành riêng test**.

Trong Spring Boot 3.5/Spring Framework 6.2, `@MockitoBean` thay thế bean trong Spring context theo cơ chế bean overriding test. Nó khác `@Mock` của Mockito (không tự thay bean), và khác `@MockBean` đời cũ đã bị deprecate.

### 3.5. oauth2Login()/oidcLogin()

Spring Security test cũng có `oauth2Login()` và `oidcLogin()` MockMvc postprocessors. Chúng giúp dựng `OAuth2AuthenticationToken`/OIDC principal và authority để kiểm **đường downstream** khi đã login. Chúng không tự mở browser tới Identity Provider, redirect sang authorize endpoint, đổi authorization code tại token endpoint, kiểm PKCE, nhận JWKS hoặc xử lý MFA.

### 3.6. Opaque token postprocessor

`opaqueToken()` có ý nghĩa tương tự đối với resource server dùng token introspection: mô phỏng authenticated principal/claims, **không thực hiện** HTTP introspection thật với authorization server. Nếu muốn kiểm opaque token validity, cần `OpaqueTokenIntrospector` thật hoặc test IdP/introspection stub trong môi trường integration.

## 4. Vì sao JWT payload nhìn hợp lệ vẫn có thể giả mạo?

### 4.1. JWT compact có ba phần

JWT ký kiểu JWS thường có dạng:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Ví dụ header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "test-key"
}
~~~

Ví dụ claims:

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "iat": 1760000000,
  "nbf": 1760000000,
  "exp": 1760000300
}
~~~

Các số thời gian ở đây **chỉ để minh họa cấu trúc**, không phải claims có thể sử dụng ở ngày hiện tại. Một JWT được decode bằng Base64URL **không phải** đã được verify. Bất kỳ ai cũng có thể dựng một payload với `sub=admin` hoặc `scope=orders:read`; chỉ chữ ký hợp lệ dưới trust policy mới chứng minh nội dung không bị sửa kể từ khi signer đáng tin ký nó.

### 4.2. RS256 là gì?

`RS256` sử dụng RSA signature với SHA-256:
- Authorization server/issuer giữ **private key** để ký.
- Resource server dùng **public key** tương ứng để verify.
- Nếu attacker thay payload hoặc dùng private key khác, signature verification fail.
- `kid` giúp chọn public key trong JWKS; `kid` tự nó **không chứng minh trust**.

Các thuật toán khác như ES256 hoặc HS256 có mô hình key khác. Resource Server phải có allowlist thuật toán chấp nhận và đúng key types; không chọn trust policy chỉ theo header `alg` do attacker cung cấp.

### 4.3. alg=none và algorithm confusion

Một token có `{"alg":"none"}` không phải một JWT được ký theo chính sách RS256. Decoder configured chỉ cho phép RS256 phải reject. Tương tự, không nên vô ý cho phép HS256 trên một endpoint vốn kỳ vọng RSA public key hay dùng public key bytes như HMAC secret. Bảo đảm algorithm policy được cấu hình trên verifier, không dựa vào claims do token cung cấp.

Các bài test defensive có thể tạo token unsigned/wrong-alg/tampered và assert 401. Không cần triển khai một cơ chế ký yếu để chứng minh app an toàn; chỉ kiểm decoder **không chấp nhận**.

### 4.4. iss, aud và scope khác nhau

- `iss`: ai phát hành token. Resource Server phải tin issuer đó.
- `aud`: token dành cho resource nào. Đúng issuer nhưng audience thuộc API khác có thể không được dùng ở đây.
- `sub`: danh tính chủ thể; không tự cho biết authority.
- `scope`/`scp`: delegated permissions, thường được chuyển thành `SCOPE_...`.
- `exp`: thời điểm hết hạn; có thể áp clock skew.
- `nbf`: chưa hợp lệ trước thời điểm này; có thể áp clock skew.
- `iat`: thời điểm phát hành, hữu ích cho age/diagnostics nhưng không tự thay thế mọi validator.
- `jti`: token ID, hữu ích cho replay/revocation nếu có store/policy phù hợp.
- `typ`: phân biệt token type nếu API yêu cầu; không xem bất kỳ JWT signed nào cũng là access token.

**Chữ ký đúng chưa đồng nghĩa token được phép sử dụng**. Một signed ID token hoặc access token của audience khác có thể không hợp lệ cho API này.

## 5. Resource Server authentication với Spring Security

### 5.1. Dependency thực sự cần

Với JWT OAuth2 Resource Server cần:
- `spring-security-oauth2-resource-server` cho Bearer token/filter/provider.
- `spring-security-oauth2-jose` cho JWT parsing/signature/JWS/JWK.
- `spring-security-test` trong tests để có `@WithMockUser`, `jwt()` và security test support.

Spring Boot starter `spring-boot-starter-oauth2-resource-server` gom các phần runtime cần thiết. `spring-boot-starter-test` có JUnit/AssertJ/Mockito nhưng không thay `spring-security-test`.

### 5.2. Cấu hình production thường dùng

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/real-issuer
          audiences: https://orders-api.example.org
~~~

Đây là **mẫu production configuration**, không copy vào demo lab. Trong các phiên bản Spring Security/Boot được hỗ trợ, `issuer-uri` cho phép Resource Server khám phá metadata/JWKS và validate issuer. `audiences` yêu cầu kiểm `aud`. Không tự giả định audience được kiểm nếu app **chưa cấu hình validator/audiences**.

Một cách khác khi biết JWKS URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/real-issuer
          jwk-set-uri: https://idp.example.org/real-issuer/keys
          audiences: https://orders-api.example.org
~~~

Đặt `jwk-set-uri` tường minh có thể tránh coupling discovery tại startup/first request tùy configuration, nhưng vẫn cần issuer validation. Trong thực tế, JWKS endpoint phải là **trusted location qua HTTPS**, không lấy `jku`/`x5u` từ JWT không đáng tin để tự động fetch arbitrary URLs.

### 5.3. Spring Security mặc định kiểm gì?

Theo tài liệu Spring Security 6.5, JWT Resource Server điển hình:
- Verify chữ ký bằng key từ JWKS hoặc decoder bean.
- Validate `exp`, `nbf` và `iss` khi issuer được cấu hình.
- Convert scope thành authorities prefix `SCOPE_`.
- Có thể cấu hình `aud` bằng Boot property hoặc custom `OAuth2TokenValidator`.

Cần kiểm **mã cấu hình thật của ứng dụng**; nếu bạn thay `JwtDecoder` bean hoặc dùng custom authentication converter, defaults có thể không giống ví dụ. Test nên bảo vệ cả validator configuration.

### 5.4. 401 và 403

| Tình huống | Expected thông thường | Lý do |
| --- | --- | --- |
| Không có Bearer credential ở endpoint protected | 401 | Chưa authenticated |
| Bearer string hỏng format | 401 | Không decode được |
| Chữ ký sai | 401 | Evidence không đáng tin |
| JWT hết hạn / chưa có hiệu lực | 401 | Token invalid |
| Issuer/audience sai | 401 | Token không được chấp nhận |
| JWT hợp lệ, thiếu `orders:read` | 403 | Đã authenticated nhưng thiếu authority |
| JWT hợp lệ, đúng scope | 200 | Authentication + authorization thành công |
| Mock user tự gán đúng authority | Có thể 200 | **Không chứng minh token đã được verify** |

HTTP status có thể khác nếu application tùy biến entry point/error handling. Với default Bearer resource server, 401 vs 403 là phân biệt cơ bản cần assert. Có thể kiểm header `WWW-Authenticate: Bearer ...` khi contract cần, tránh hard-code thông điệp chi tiết chứa thông tin nhạy cảm.

## 6. Chiến lược kiểm thử nhiều tầng

### 6.1. Tầng 1: pure unit policy tests

Dùng Java/JUnit/Mockito để kiểm business permissions như “owner thấy đơn của mình, admin thấy mọi đơn”, không cần web hoặc JWT. Fixtures cho principal/roles/ownerId phải rõ. Tầng này rẻ, nhanh, bao phủ nhiều nhánh domain.

### 6.2. Tầng 2: @WebMvcTest + mocked Authentication

Giữ controller và Spring Security filter/config authorization, nhưng dùng `@WithMockUser` hoặc `jwt()` để dựng identity/authorities. Tốt để kiểm:
- URL matcher / hasAuthority / method-security nếu beans cần thiết được import.
- HTTP 200/403 cho principal đã chuẩn bị.
- Principal mapping trong controller.

**Không** đánh dấu tầng này là `JWT signature test`, `login flow test` hoặc `IdP integration test`.

### 6.3. Tầng 3: resource-server authentication integration

Dùng `@SpringBootTest + @AutoConfigureMockMvc` với filter chain thật, `JwtDecoder` thật, JWT ký bằng **test private key**. Gửi HTTP Authorization header thực:

~~~text
Authorization: Bearer <compact-signed-JWS>
~~~

Test này kiểm:
- Header extraction và Bearer authentication filter.
- JWS signature verification.
- `exp`/`nbf`, issuer, audience validators nếu cấu hình.
- Authority conversion từ `scope` và access policy.
- Status 401/403/200.

Nhưng vì JWT được tạo bởi **test encoder** và keypair in-memory, nó chưa chứng minh authorization server production đã cấp token đúng, JWKS network discovery/caching/rotation, OAuth2 redirect/code exchange hoặc MFA.

### 6.4. Tầng 4: JWKS/issuer integration

Dùng local test HTTP server phục vụ issuer metadata và JWKS:
- Cấu hình Resource Server dùng `issuer-uri`/`jwk-set-uri` test URL.
- Phát JWT ký bằng private key tương ứng.
- Kiểm call metadata/JWKS, algorithm allowlist và `kid` selection.
- Rotate key A → B, kiểm cache/refresh semantics và chính sách chấp nhận key cũ.
- Thử JWKS unavailable, HTTPS/certificate/timeouts theo yêu cầu.
- Kiểm đúng issuer/audience dù signature valid.

Không cần gọi IdP thật trong CI nhanh; server stub có response hợp đồng ổn định. Tuy nhiên stub chỉ chứng minh ứng dụng tương tác với **hợp đồng mô phỏng**.

### 6.5. Tầng 5: full OAuth2/OIDC flow

Nếu hệ thống sử dụng Authorization Code + PKCE, cookie/session và OIDC, cần test ở mức browser/real authorization server test tenant:
1. Client tạo `state`/`nonce` và PKCE code verifier/challenge.
2. Browser redirect tới authorization endpoint.
3. User thực hiện login, MFA nếu có.
4. Authorization server cấp authorization code và redirect back.
5. Client gửi code + code_verifier tới token endpoint.
6. Token endpoint kiểm client/redirect_uri/code/PKCE.
7. Client nhận token, kiểm ID token/nonce khi OIDC, thiết lập session theo thiết kế.
8. Resource server nhận access token, verify và authorize.
9. Kiểm logout, revoked session/token, expired token, CSRF/cookie và negative flows.

`@WithMockUser`/`jwt()` **không thực hiện các bước này**. Ngay cả full resource-server signed JWT test ở tầng 3 cũng chỉ kiểm **phần API nhận token**, không kiểm cách token được cấp.

### 6.6. Ma trận lựa chọn

| Công cụ | Có Spring Security policy? | Có Bearer header thật? | Có verify chữ ký? | Có full login/IdP flow? |
| --- | --- | --- | --- | --- |
| Pure unit + mocked principal | Tùy cách gọi | Không | Không | Không |
| `@WithMockUser` | Có, với context/filter được bật | Không | Không | Không |
| MockMvc `user()` | Có | Không | Không | Không |
| MockMvc `jwt()` | Có | Không | Không | Không |
| `@MockitoBean JwtDecoder` | Có + Bearer filter nếu gọi header | Có thể có | **Không** | Không |
| Real `NimbusJwtDecoder` + signed JWT | Có | Có | **Có** | Không |
| Real decoder + test JWKS server | Có | Có | Có, cả key discovery | Không |
| Browser + test IdP + API | Có | Có | Có | Phần flow được thực thi thực tế |

## 7. Bài lab Java 17 / Spring Boot 3.5.16: mock vs RSA JWT thật

### 7.1. Mục tiêu của lab

Xây một API `GET /api/orders/me` chỉ chấp nhận authority `SCOPE_orders:read`, trả JSON chứa tên principal và loại `Authentication` trong context. Hai nhóm test:

1. **MockAuthenticationMvcTest**: dùng `@WithMockUser` hoặc `jwt()` để chứng minh authorization policy có thể PASS dù không có Bearer JWT signature.
2. **SignedJwtResourceServerTest**: dùng RSA keypair test, ký JWS bằng `NimbusJwtEncoder`, gọi endpoint qua `Authorization: Bearer ...`. Decoder thật `NimbusJwtDecoder` verify signature, issuer, audience, time window; test kiểm token sai bị từ chối.

Thiết kế keypair:
- RSA 2048 sinh một lần trong Spring TestContext.
- Private key **chỉ có trong src/test/java**, không đóng gói production.
- Test `JwtEncoder` dùng private key để ký.
- Test `JwtDecoder` dùng public key để verify.
- `JwtValidators.createDefaultWithIssuer` kiểm issuer và timestamp.
- Custom audience validator yêu cầu `aud` chứa `orders-api`.
- Scope conversion của Spring Security mặc định tạo `SCOPE_orders:read`.
- RSA key khác, dù cùng `kid` và claims, không được chấp nhận.

**Phạm vi:** JUnit/MockMvc dùng mock servlet request chứ không mở TCP server; điều này **không** làm mất giá trị kiểm JWT signature/filter chain vì HTTP Authorization header vẫn đi qua filter và decoder thật. Nó không kiểm TLS/network proxy, browser login hoặc external IdP.

### 7.2. Cấu trúc thư mục

~~~text
auth-mock-vs-real-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/authlab/
│   │   ├── AuthLabApplication.java
│   │   ├── ApiSecurityConfig.java
│   │   └── OrdersController.java
│   └── resources/application.properties
└── src/test/java/com/example/authlab/
    ├── TestJwtSupportConfig.java
    ├── MockAuthenticationMvcTest.java
    └── SignedJwtResourceServerTest.java
~~~

Đặt đúng package/file name. Mỗi Java class có imports đầy đủ để compile. Mã ở phần 7.3–7.9 là **project runnable dự kiến**, khác các đoạn ý tưởng ngắn trong các phần khác.

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>auth-mock-vs-real-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
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

Maven BOM của Spring Boot 3.5 quản lý Spring Security, Spring Test, Nimbus JOSE, Mockito và JUnit tương thích. Không thêm riêng dependency Nimbus version không theo BOM nếu chưa cần.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=auth-mock-vs-real-lab
server.port=8080
~~~

**Chủ ý:** Lab không có `issuer-uri` production trong cấu hình chính. Khi chạy JUnit, decoder bean test-only được `@Import` từ `TestJwtSupportConfig`. Nếu chạy riêng `mvn spring-boot:run`, bạn cần cung cấp issuer/JWKS production-like config hoặc một `JwtDecoder` runtime bean phù hợp; không dùng private key test dưới `src/main` chỉ để app startup.

### 7.5. AuthLabApplication.java

~~~java
package com.example.authlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthLabApplication.class, args);
    }
}
~~~

### 7.6. ApiSecurityConfig.java

~~~java
package com.example.authlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/orders/me")
                        .hasAuthority("SCOPE_orders:read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Giải thích:
- URL matcher yêu cầu đúng authority `SCOPE_orders:read`.
- Resource Server JWT authentication được bật qua `oauth2ResourceServer(...jwt...)`.
- Chưa disable CSRF: demo chỉ có GET nên không phụ thuộc CSRF. Với REST API stateless dùng POST/PUT, quyết định CSRF phải xét cookie/session/credential threat model; không tắt bảo vệ chỉ để test dễ PASS.
- Không cấu hình `JwtDecoder` trong main: integration test cung cấp decoder thật có test public key. Production dùng issuer/JWKS config đã được phê duyệt.
- Không thêm `@EnableMethodSecurity` vì ví dụ chỉ kiểm URL policy; nếu có `@PreAuthorize` trong business service, cần bật method security và viết test ở boundary đó.

### 7.7. OrdersController.java

~~~java
package com.example.authlab;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    @GetMapping("/me")
    public Map<String, String> currentUser() {
        Authentication authentication =
                SecurityContextHolder.getContext()
                        .getAuthentication();

        return Map.of(
                "principal", authentication.getName(),
                "authenticationType",
                authentication.getClass().getSimpleName());
    }
}
~~~

Controller này chỉ expose test-readable principal/type; không phải API order production. Trong application production nên tránh đưa authentication implementation class name ra public API, và dùng method arguments/principal abstraction hoặc security services phù hợp.

Endpoint:
- MockUser → `UsernamePasswordAuthenticationToken`.
- Mock `jwt()` và real verified Bearer JWT → `JwtAuthenticationToken`.
- Cả hai loại vẫn có thể vượt `hasAuthority` nếu authority được cung cấp. Đây chính là điểm bài học muốn chứng minh.

### 7.8. TestJwtSupportConfig.java — keypair và validators chỉ dành cho test

`src/test/java/com/example/authlab/TestJwtSupportConfig.java`:

~~~java
package com.example.authlab;

import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

@TestConfiguration(proxyBeanMethods = false)
public class TestJwtSupportConfig {

    public static final String ISSUER =
            "https://issuer.example.test";
    public static final String AUDIENCE = "orders-api";
    public static final String KEY_ID = "test-key";

    @Bean
    KeyPair testSigningKey() throws GeneralSecurityException {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @Bean
    JwtEncoder testJwtEncoder(KeyPair testSigningKey) {
        RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) testSigningKey.getPublic())
                .privateKey(
                        (RSAPrivateKey) testSigningKey.getPrivate())
                .keyID(KEY_ID)
                .build();

        return new NimbusJwtEncoder(
                new ImmutableJWKSet<>(
                        new JWKSet(jwk)));
    }

    @Bean
    JwtDecoder testJwtDecoder(KeyPair testSigningKey) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey(
                        (RSAPublicKey) testSigningKey.getPublic())
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator =
                jwt -> jwt.getAudience() != null
                        && jwt.getAudience().contains(AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Token audience is not orders-api",
                                    null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(
                                ISSUER),
                        audienceValidator));

        return decoder;
    }
}
~~~

**Tính an toàn và ý nghĩa kiểm thử:**
- Public/private key sinh runtime cho mỗi Spring test context; không lưu private key trong repo.
- `NimbusJwtEncoder` ký bằng **private key test**.
- `NimbusJwtDecoder.withPublicKey(...)` verify signature bằng **public key test** và mặc định tin RS256 trong setup này.
- Validator kết hợp issuer, timestamp mặc định và audience yêu cầu. Test sai `iss`, `aud`, `exp`, `nbf` phải thất bại.
- Đây là **decoder thật**, không phải Mockito stub, nhưng **không test JWKS qua HTTP** vì key được tiêm trực tiếp. Đường JWKS discovery/key rotation cần suite riêng.
- `@TestConfiguration` ở `src/test/java` không nên được đưa vào production artifact; class chỉ được dùng khi test chủ động `@Import`.
- Với multi-key rotation test, cần làm việc với `NimbusJwtDecoder.withJwkSetUri(...)` và một JWKS server stub; không suy keypair đơn đã kiểm rotation.

### 7.9. MockAuthenticationMvcTest.java — authorization bằng danh tính giả

`src/test/java/com/example/authlab/MockAuthenticationMvcTest.java`:

~~~java
package com.example.authlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrdersController.class)
@Import(ApiSecurityConfig.class)
class MockAuthenticationMvcTest {

    @Autowired
    MockMvc mvc;

    // Cần bean để cấu hình Resource Server filter chain
    // trong MVC slice; test này KHÔNG kiểm chữ ký.
    @MockitoBean
    JwtDecoder decoder;

    @Test
    @WithMockUser(
            username = "alice",
            authorities = "SCOPE_orders:read")
    void mockUserPassesAuthorizationWithoutAnyJwt()
            throws Exception {

        mvc.perform(get("/api/orders/me"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.principal")
                        .value("alice"))
                .andExpect(jsonPath("$.authenticationType")
                        .value(
                                "UsernamePasswordAuthenticationToken"));
    }

    @Test
    void jwtPostProcessorPassesWithoutSignedBearerToken()
            throws Exception {

        mvc.perform(get("/api/orders/me")
                .with(jwt()
                        .jwt(jwt -> jwt
                                .claim("sub", "alice")
                                .claim("iss",
                                        "https://untrusted.example.test"))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_orders:read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.principal")
                        .value("alice"))
                .andExpect(jsonPath("$.authenticationType")
                        .value("JwtAuthenticationToken"));
    }

    @Test
    void mockJwtMissingRequiredAuthorityGetsForbidden()
            throws Exception {

        mvc.perform(get("/api/orders/me")
                .with(jwt()
                        .jwt(jwt -> jwt.claim("sub", "alice"))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_orders:write"))))
                .andExpect(status().isForbidden());
    }
}
~~~

**Đọc đúng kết quả:**
- Test 1 dùng `@WithMockUser`, không có Bearer token nhưng policy vẫn cho phép.
- Test 2 dùng `jwt()` gán `iss` **không đáng tin** và authority read do chính test set. Nó vẫn có thể PASS vì helper tạo `JwtAuthenticationToken` mà không gọi decoder thật. Đây là bằng chứng rõ ràng về **giới hạn** của test helper, không phải lỗ hổng production khi HTTP Bearer filter hoạt động bình thường.
- Test 3 kiểm negative authorization: principal đã authenticated mock nhưng thiếu scope → 403.
- `@MockitoBean JwtDecoder` chỉ là collaborator cho việc dựng filter chain trong MVC slice. Những request dùng `jwt()`/`@WithMockUser` không chứng minh phương thức `decoder.decode(...)` verify signature.
- Nếu thay `@WebMvcTest` thành `MockMvcBuilders.standaloneSetup(...)` mà không apply Spring Security, có thể bypass cả filter/policy; đừng coi đó là security integration test.

### 7.10. SignedJwtResourceServerTest.java — JWT ký RSA đi qua decoder thật

`src/test/java/com/example/authlab/SignedJwtResourceServerTest.java`:

~~~java
package com.example.authlab;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestJwtSupportConfig.class)
class SignedJwtResourceServerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    JwtEncoder encoder;

    @Autowired
    JwtDecoder decoder;

    @Test
    void authenticSignedTokenCanReadOrders()
            throws Exception {
        String bearer = sign(claims(
                TestJwtSupportConfig.ISSUER,
                TestJwtSupportConfig.AUDIENCE,
                "orders:read",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(300)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + bearer))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.principal")
                        .value("alice"))
                .andExpect(jsonPath("$.authenticationType")
                        .value("JwtAuthenticationToken"));
    }

    @Test
    void missingBearerCredentialIsUnauthorized()
            throws Exception {
        mvc.perform(get("/api/orders/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void malformedBearerTokenIsUnauthorized()
            throws Exception {
        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer not-a-jwt"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void sameClaimsSignedByWrongPrivateKeyAreRejected()
            throws Exception {

        JwtClaimsSet identicalClaims = claims(
                TestJwtSupportConfig.ISSUER,
                TestJwtSupportConfig.AUDIENCE,
                "orders:read",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(300));

        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair attackerKey = generator.generateKeyPair();

        RSAKey attackerJwk = new RSAKey.Builder(
                (RSAPublicKey) attackerKey.getPublic())
                .privateKey(
                        (RSAPrivateKey) attackerKey.getPrivate())
                // Cố tình cùng key ID: kid không làm key đáng tin.
                .keyID(TestJwtSupportConfig.KEY_ID)
                .build();

        JwtEncoder attackerEncoder = new NimbusJwtEncoder(
                new ImmutableJWKSet<>(
                        new JWKSet(attackerJwk)));

        String forged = encode(
                attackerEncoder, identicalClaims);

        // Đường decoder thật kiểm chữ ký, không chỉ claims.
        assertThatThrownBy(() -> decoder.decode(forged))
                .isInstanceOf(JwtException.class);

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + forged))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongIssuerIsUnauthorizedEvenWhenSignatureIsValid()
            throws Exception {
        String token = sign(claims(
                "https://other-issuer.example.test",
                TestJwtSupportConfig.AUDIENCE,
                "orders:read",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(300)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongAudienceIsUnauthorized()
            throws Exception {
        String token = sign(claims(
                TestJwtSupportConfig.ISSUER,
                "different-resource-api",
                "orders:read",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(300)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredSignedJwtIsUnauthorized()
            throws Exception {
        String token = sign(claims(
                TestJwtSupportConfig.ISSUER,
                TestJwtSupportConfig.AUDIENCE,
                "orders:read",
                Instant.now().minusSeconds(600),
                Instant.now().minusSeconds(180)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void jwtNotYetValidIsUnauthorized()
            throws Exception {
        String token = sign(claims(
                TestJwtSupportConfig.ISSUER,
                TestJwtSupportConfig.AUDIENCE,
                "orders:read",
                Instant.now().plusSeconds(300),
                Instant.now().plusSeconds(900)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validJwtWithInsufficientScopeIsForbidden()
            throws Exception {
        String token = sign(claims(
                TestJwtSupportConfig.ISSUER,
                TestJwtSupportConfig.AUDIENCE,
                "orders:write",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(300)));

        mvc.perform(get("/api/orders/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token))
                .andExpect(status().isForbidden());
    }

    private String sign(JwtClaimsSet claims) {
        return encode(encoder, claims);
    }

    private static String encode(
            JwtEncoder signer, JwtClaimsSet claims) {
        JwsHeader header = JwsHeader
                .with(SignatureAlgorithm.RS256)
                .keyId(TestJwtSupportConfig.KEY_ID)
                .build();

        return signer.encode(
                JwtEncoderParameters.from(header, claims))
                .getTokenValue();
    }

    private static JwtClaimsSet claims(
            String issuer,
            String audience,
            String scope,
            Instant notBefore,
            Instant expiresAt) {

        return JwtClaimsSet.builder()
                .issuer(issuer)
                .subject("alice")
                .audience(List.of(audience))
                .issuedAt(Instant.now().minusSeconds(900))
                .notBefore(notBefore)
                .expiresAt(expiresAt)
                .id(UUID.randomUUID().toString())
                .claim("scope", scope)
                .build();
    }
}
~~~

### 7.11. Phân tích từng test

**Test valid token:** `JwtEncoder` tạo compact JWS ký RSA, test đưa vào header thật. `BearerTokenAuthenticationFilter` trích token; `JwtDecoder` verify chữ ký và issuer/audience/timestamps; `JwtAuthenticationConverter` sinh `SCOPE_orders:read`; policy cho 200. Đây mới thực sự là JWT authentication verification trong app, dù không có network tới IdP.

**Test no token:** Không có `Authorization`, endpoint protected → 401; khác MockUser vì test không tự đặt authenticated principal.

**Test malformed token:** Header chứa Bearer value nhưng không phải compact JWT → decoder reject, 401.

**Test wrong private key:** Token có claims y hệt valid token, alg RS256 và **cùng kid**, nhưng private key ký không khớp public key server trust. Decoder thực ném `JwtException`; HTTP trả 401. Đây là negative signature test quan trọng nhất.

**Test wrong issuer:** Signature hợp lệ, nhưng `iss` khác expected → 401. Nó chứng minh chữ ký đúng chưa đủ khi issuer trust không đúng.

**Test wrong audience:** Signature và issuer đúng, nhưng `aud` không chứa `orders-api` → custom audience validator reject → 401. Nếu bỏ validator/Boot audience property, test này có thể lộ bug cấu hình.

**Test expired:** `exp` cách thời điểm test 180 giây trong quá khứ, vượt qua clock skew tolerance thông thường, tránh flaky boundary ± vài giây.

**Test not yet valid:** `nbf` cách thời điểm test 300 giây trong tương lai, vượt clock skew. Token ký đúng vẫn chưa được chấp nhận.

**Test insufficient scope:** Signature/iss/aud/time hợp lệ, nhưng only `orders:write` scope → authenticated mà thiếu `SCOPE_orders:read` → 403 (khác 401).

### 7.12. Vì sao không kiểm expiry bằng token expire 1 giây trước?

`JwtTimestampValidator` có clock skew allowance nhằm chống chênh đồng hồ giữa systems. Một token hết hạn 1 giây có thể vẫn hợp lệ theo policy và khiến test fail ngẫu nhiên. Trong lab, negative samples cách xa hiện tại vài phút. Với hệ thống cần kiểm chính xác boundary, phải cấu hình `Clock`/`JwtTimestampValidator` và skew cụ thể, không dựa vào wall-clock race.

### 7.13. Chạy Maven

Từ thư mục `auth-mock-vs-real-lab`, có JDK 17+ và Maven:

~~~bash
mvn -q clean test

mvn -q -Dtest=MockAuthenticationMvcTest test
mvn -q -Dtest=SignedJwtResourceServerTest test
~~~

Kết quả thiết kế mong đợi:
- Mock suite: 3 tests PASS, trong đó một mock issuer không đáng tin vẫn được phép do **authority được dựng sẵn**.
- Real signed-token suite: 9 tests PASS, bao gồm request 200 hợp lệ; no/invalid/wrong-signature/wrong-issuer/wrong-audience/expired/future-nbf → 401; insufficient scope → 403.
- Tổng 12 test methods.
- Maven exit code `0` khi thành công; báo cáo có trong `target/surefire-reports`.

**QA thực tế:** Các file Java và Maven declarations trong bài được rà soát cấu trúc/API, nhưng **không tuyên bố đã chạy Maven/JUnit** trong quá trình biên soạn. Kết quả trên là expected behavior, phải xác nhận trong dự án/CI.

### 7.14. Không chạy bare application với test key

`TestJwtSupportConfig` nằm trong `src/test/java`, chỉ được import trong tests. Đây là ranh giới an toàn. Không copy RSA test private key vào `application.properties`, `src/main/resources` hay source production.

Để chạy app độc lập cần cấu hình resource server kết nối issuer production/test-authority được kiểm duyệt, ví dụ `issuer-uri` và `audiences` như mục 5.2; không hard-code private key trong main chỉ để tránh lỗi context startup.

## 8. Kiểm “mock không chứng minh signature” bằng một lập luận trực tiếp

Hai requests khác nhau:

### 8.1. Request A: dựng Authentication

~~~java
mvc.perform(get("/api/orders/me")
        .with(jwt()
                .jwt(jwt -> jwt
                        .claim("sub", "alice")
                        .claim("iss",
                                "https://attacker.example.test"))
                .authorities(
                        new SimpleGrantedAuthority(
                                "SCOPE_orders:read"))))
        .andExpect(status().isOk());
~~~

Trong một security MockMvc test với filter chain, request này đưa một JwtAuthenticationToken vào context. Không có signed compact JWS, không có Bearer header. Fake issuer không làm test fail vì decoder validator **không chạy**.

### 8.2. Request B: đưa Bearer token thật

~~~java
mvc.perform(get("/api/orders/me")
        .header(HttpHeaders.AUTHORIZATION,
                "Bearer " + signedJwt))
        .andExpect(status().isOk());
~~~

Với `JwtDecoder` thật, request B đi qua filter/provider/verification. Nếu signedJwt có chữ ký sai, issuer khác, audience sai, expired hoặc nbf future, response 401 thay vì 200.

**Không viết test A rồi đặt tên `validatesJwtSignature()`.** Tên đúng có thể là `allowsScopeReadForMockJwtPrincipal()`. Test B tên `rejectsTokenSignedByUntrustedKey()` là chính xác với công việc đã thực thi.

## 9. 401 vs 403 và lập luận về lỗi

### 9.1. Token invalid không nên trở thành authenticated principal

Khi signature/issuer/audience/expiry không hợp lệ, resource server phải **không dựng thành công JwtAuthenticationToken đáng tin** cho request. Trả 401 là contract thông thường.

Nếu code tự decode Base64URL payload rồi set `Authentication` mà không kiểm signature, nguy cơ là caller tự chọn scope/role. Đừng parse JWT bằng cách `split("\\.")` + Base64 decode rồi tin claim `sub` hoặc `role`. Chỉ làm Base64 decode để inspect untrusted token trong diagnostic không sensitive; không dùng làm authentication.

### 9.2. Valid token nhưng thiếu quyền

Một Bearer token hợp lệ có thể chỉ chứa `scope=orders:write`. Việc decode signature thành công là **authentication**, nhưng policy `hasAuthority("SCOPE_orders:read")` vẫn từ chối → 403.

Nếu tất cả negative tests chỉ assert “không trả 200”, bạn có thể bỏ lỡ bug giữa invalid credential vs insufficient authorization. Kiểm chính xác status 401/403 và error contract phù hợp.

### 9.3. WWW-Authenticate

OAuth2 Bearer Resource Server thường trả `WWW-Authenticate` header khi 401, có thể có error code như `invalid_token`. Header detail có thể thay theo Spring Security version và policy; test nên assert những thành phần được yêu cầu bởi API contract, không hard-code nội dung chứa implementation detail trừ khi điều đó là requirement.

### 9.4. Method security và URL security

`@PreAuthorize("hasAuthority('SCOPE_orders:read')")` là method-level rule; cần `@EnableMethodSecurity` và call đi qua Spring-managed proxy. `@WithMockUser` rất hữu ích để test các policy này nhưng vẫn không verify JWT signature. Muốn kiểm đồng thời token validity và method-level rule, dùng signed Bearer token integration test cho service được gọi qua Spring proxy.

## 10. Đối chiếu chữ ký, issuer, audience, expiry, nbf

### 10.1. Signature

Test “cùng claims, private key khác” cô lập lỗi signature tốt hơn test một chuỗi JWT ngẫu nhiên hỏng vì chuỗi hỏng có thể fail từ bước parse, không đến cryptographic verification.

Trong lab, private key giả cũng dùng `kid=test-key`. Nếu signature được chấp nhận chỉ dựa vào `kid`, test sẽ phát hiện. `kid` là selector, không phải proof of trust.

### 10.2. Issuer

Khi issuer configuration cố định, token signed nhưng `iss` khác phải reject. Điều này bảo vệ trường hợp nhiều authorization servers có thể dùng keys/algorithms khác nhau. Một resource server thường phải dùng trust configuration cụ thể theo tenant/issuer; không tin bất kỳ issuer chỉ vì JWKS endpoint do token nêu.

### 10.3. Audience

Access token cho API A không nên dùng được ở API B chỉ vì cùng issuer và signature hợp lệ. Kiểm `aud` trong danh sách resource server của mình. Nếu app không cấu hình audience validation, đây là lỗ hổng policy đáng kiểm. Sample validator dùng `OAuth2TokenValidatorResult` kết hợp với issuer/timestamp validators.

### 10.4. exp và nbf

Timestamp validation phải xác định:
- Token quá hạn → invalid.
- Token chưa tới thời điểm `nbf` → invalid.
- Sai/thiếu claims bắt buộc → theo resource policy.
- Clock skew tolerance → explicit policy và test tương ứng.

Đừng nhầm JWT `exp` và server-side session expiry. Token JWT self-contained có thể còn valid về mặt chữ ký dù user đã logout, trừ khi có revocation/session binding strategy.

### 10.5. Scope và authorities

Spring Security mặc định map `scope`/`scp` thành `SCOPE_...`. Nhưng project thực có thể dùng `JwtGrantedAuthoritiesConverter` custom mapping `roles` hoặc `permissions`. Test phải kiểm:
- Claim dùng làm authority đến từ **validated JWT**.
- Scopes đúng semantics (least privilege).
- Không để user-controlled header/query parameter ghi đè authorities.
- Không coi `roles=["ADMIN"]` trong một untrusted payload là admin đã được ủy quyền.

## 11. JWKS, key rotation và algorithm trust

### 11.1. JWKS là gì?

JWKS (JSON Web Key Set) là tập public keys issuer công bố để resource server verify signatures. JWT header có thể có `kid` giúp chọn key phù hợp. Khi issuer đổi key, JWKS thay đổi; decoder/cache cần refresh theo chính sách.

Sample lab inject một public key trực tiếp, **không gọi JWKS HTTP endpoint**. Nó kiểm crypto verification với key đó, không kiểm cache/rotation/network.

### 11.2. Bài test JWKS integration nên bao phủ

1. Test issuer metadata endpoint trả `jwks_uri` chính xác.
2. JWKS gồm key A có `kid=k1`.
3. Token ký bằng private A hợp lệ.
4. Token ký bằng private B khi JWKS chỉ có A → reject.
5. JWKS cập nhật có public B, decoder làm mới cache theo cơ chế cho phép → token B hợp lệ.
6. Token A sau khi issuer thu hồi key A → reject khi cache đã cập nhật và policy yêu cầu.
7. JWKS server timeout/500 → kiểm error behavior, không silently trust token.
8. JWKS `alg`/key type không khớp → reject.
9. Issuer/audience vẫn phải được validate sau khi signature hợp lệ.
10. Logs không chứa Bearer token hoặc private key.

Bài test này cần local HTTP stub (WireMock/MockWebServer) hoặc test IdP. Không gọi endpoint production trong unit suite.

### 11.3. Thuật toán phải được tin cậy qua cấu hình

Resource Server không được tự chuyển sang một algorithm khác chỉ vì attacker đặt `alg` trong JWT header. Với `NimbusJwtDecoder.withPublicKey`, lab sử dụng RSA public key và RS256; production có thể allowlist RS256/RS512/ES256... theo issuer contract.

Đừng thay đổi algorithm allowlist khi test fail mà không review key types/trust. Một invalid-token test làm lộ mismatch là tín hiệu cần sửa configuration đúng, không phải để tắt verification.

### 11.4. Không lấy JWKS URL từ token chưa verify

Header values như `jku` hoặc `x5u` có thể chứa URL do caller kiểm soát. Nếu ứng dụng tự fetch URL từ untrusted token, có thể dẫn tới SSRF hoặc trust confusion. JWKS URI phải được bind với issuer/trust configuration đã phê duyệt, dùng HTTPS và network controls phù hợp. Không để JWT header tự quyết định trusted signer.

### 11.5. “Đổi key” và “thu hồi token” là hai việc khác

Key rotation không nhất thiết thu hồi mọi JWT cũ ngay; issuer có thể giữ keys cũ cho tới khi tokens hết hạn. Token revocation (logout, account disabled, incident) cần một chiến lược riêng: short TTL, revocation store/introspection, session version hoặc event-driven policy. Test mock JWT không chứng minh bất kỳ revocation mechanism nào.

## 12. Full OAuth2/OIDC flow khác JWT Resource Server

### 12.1. Authorization Code + PKCE

Một Browser/OAuth2 Login test cần kiểm:
- Client tạo random `state`; response callback khớp state, tránh login CSRF.
- PKCE code verifier được giữ an toàn; code challenge gửi trước.
- Authorization code chỉ dùng một lần, gắn đúng client/redirect_uri/verifier.
- Browser redirect/cookie/session security được kiểm.
- Token endpoint cấp token theo đúng authorized account/client.
- Resource Server dùng access token đúng audience/scope.
- User không bypass login/MFA flow bằng cách truy cập callback giả.

Chỉ gắn `@WithMockUser` vào method không kiểm được những bước này.

### 12.2. OIDC ID token không đồng nghĩa access token

OIDC ID token dùng để chứng minh identity cho **client** và có các checks như issuer, audience client ID, nonce theo flow. Access token dùng để authorize resource server. Một ID token signed hợp lệ **không tự được phép gọi mọi API**; resource server cần kiểm intended token type/audience và policy của mình.

### 12.3. Opaque token

Opaque token không chứa payload JWT mà resource server tự verify signature. Nó thường cần introspection endpoint hoặc token store/trust mechanism. Với Spring Security, `opaqueToken()` test postprocessor mô phỏng principal, không gọi introspection. Integration test dùng real `OpaqueTokenIntrospector` hoặc test identity server stub, kiểm active/inactive/expired/insufficient scope.

### 12.4. Username/password với AuthenticationManager

Nếu ứng dụng dùng form login:
- Test `@WithMockUser` bypass `UsernamePasswordAuthenticationFilter`, `AuthenticationManager`, `DaoAuthenticationProvider` và `PasswordEncoder`.
- Unit test `PasswordEncoder.matches` chỉ kiểm một thành phần.
- Integration test POST `/login` với credentials thật trong test DB cần kiểm handler, failure response, session/cookie/CSRF, session fixation protection và lockout/rate limits khi thuộc contract.
- Full E2E còn cần browser flow, redirects, MFA, external IdP khi có.

Không biến một test URL policy thành “authentication tested” chỉ vì nó có annotation mock user.

### 12.5. MFA và step-up authentication

Ngay cả token thật cũng có thể không chứng minh MFA đã diễn ra. Nếu business policy đòi MFA/step-up, kiểm `amr`/`acr` claims theo issuer trust, freshness (`auth_time`) và policy; đồng thời cần test IdP có thực thi MFA. Không cho rằng một claim tự gán trong `jwt()` là bằng chứng người dùng thực hiện MFA.

## 13. Lưu ý test configuration và Spring filter chain

### 13.1. Đừng tắt filters rồi gọi là security test

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

Cấu hình này bỏ filter chain khỏi MockMvc, có thể khiến request vào controller mà không qua Spring Security. Nó hữu ích cho test business controller thuần, **không** phù hợp để chứng minh JWT verification, CSRF, security headers hoặc authorization filters.

Trong lab signed-token, `@AutoConfigureMockMvc` sử dụng filters mặc định; request Bearer sẽ đi qua authentication pipeline.

### 13.2. Đừng mock chính component muốn kiểm

Nếu mục tiêu là verify signature, không `@MockitoBean JwtDecoder`. Nếu mục tiêu là authorization policy, mock decoder hoặc `jwt()` có thể hợp lý. Test design phải nói rõ *which boundary is real*.

### 13.3. @WebMvcTest không tự nạp mọi business @Service

`@WebMvcTest` là MVC slice; nó có thể không nạp custom service/decoder/config ngoài scope. Dùng `@Import(ApiSecurityConfig.class)` và `@MockitoBean JwtDecoder` khi test policy slice. Nếu controller phụ thuộc business service khác, mock collaborator đó. Nếu muốn verify JWT signature với beans thật, dùng full context hoặc import đủ test configuration và real decoder.

### 13.4. @SpringBootTest không tự đảm bảo authentication thật

`@SpringBootTest` nạp context; nhưng nếu test vẫn gọi `with(jwt())` hoặc `@WithMockUser`, nó **vẫn không verify chữ ký**. Annotation full-context không thay cách request được dựng. Kết luận dựa vào đường gọi thực sự, không dựa vào tên annotation.

### 13.5. @SecurityContext trong unit tests

Pure unit tests có thể tự set `SecurityContextHolder.getContext().setAuthentication(...)` rồi clear trong `finally`/`@AfterEach` để tránh ThreadLocal leakage. Đó là fixture, không phải end-to-end authentication. Spring Security Test helpers thường an toàn hơn cho Spring TestContext.

### 13.6. Test method-security proxy

Nếu `@PreAuthorize` nằm trên service:
- Spring bean phải được quản lý bởi AOP proxy phù hợp.
- Self-invocation có thể bypass method interceptor.
- `@EnableMethodSecurity` cần được bật.
- `@WithMockUser` có thể kiểm policy tại proxy.
- Signed JWT integration test có thể kiểm token authorities → method policy nếu thực sự gọi qua proxy.

## 14. Những lỗi bảo mật có thể bị mock tests bỏ sót

### 14.1. JWT signature verification bị vô hiệu hóa

App có thể tự parse Base64 payload rồi tin `scope=admin`. `jwt().authorities("admin")` test vẫn PASS vì policy kiểm đúng authority được gán. Chỉ test signed real Bearer token với forged/tampered token mới kiểm verifier.

### 14.2. Thiếu audience validation

JWT signed và issuer đúng nhưng dành cho resource khác có thể bị chấp nhận nếu app quên `aud` validator. `@WithMockUser` hoặc `jwt()` không phát hiện vì chúng không đi qua decoder. Test negative audience với real signed token rất quan trọng.

### 14.3. Sai issuer

Một token từ authorization server khác có thể có tương đồng claims. Resource Server phải trust **expected issuer**, không chấp nhận chỉ vì có trường `sub` và `scope`.

### 14.4. Chấp nhận token hết hạn hoặc chưa hợp lệ

Nếu decoder validator bị override sai, `exp`/`nbf` có thể không được enforce. MockPrincipal không phát hiện. Test khoảng cách thời gian vượt skew và kiểm 401.

### 14.5. Scope converter mapping sai

Issuer có thể phát `scope=orders:read` nhưng custom converter lại map nhầm `ROLE_ADMIN` hoặc bỏ prefix `SCOPE_`. Một `jwt().authorities(...)` hard-code bypass converter, nên test signed token với **scope claim thật** giúp bắt lỗi mapping.

### 14.6. Thiếu security filter cho endpoint

Nếu một endpoint matcher sai hoặc filter chain không apply, fake security context test có thể xanh hoặc test không đụng đường đó. Test no-auth request phải trả 401. Với nhiều `SecurityFilterChain`/`securityMatcher`, test từng nhóm URL, HTTP method và dispatcher type.

### 14.7. ID token được dùng thay access token

Không kiểm `aud`/token type khiến một ID token signed có thể được xử lý như access token. Test negative với audience/client ID không phải API và claims/token type khi contract quy định.

### 14.8. JWKS cache/key rotation lỗi

JWT signed với one local test key PASS, nhưng production decoder không reload public key sau rotation. Cần integration test với JWKS server/rotating keys, không dựa test signing fixture đơn.

### 14.9. Authentication success nhưng tenant/ownership sai

Token hợp lệ chỉ cung cấp identity; nó không tự cho phép đọc mọi order. Cần business authorization per-resource: `ownerId==principalId`, tenant binding, data scope, object-level checks. Một test signed JWT 200 cho một endpoint đơn giản chưa chứng minh chống IDOR/BOLA.

### 14.10. Password/MFA/session không được kiểm

Nếu system login bằng browser/IdP, fake authenticated user bypass credentials, MFA và redirects. Cần login E2E trong sandbox/tenant riêng. Đừng gửi test credentials thật của nhân viên vào CI logs.

## 15. Test JWT tampering và signature: đề xuất chi tiết

### 15.1. Thiết kế negative sample không mơ hồ

Có ít nhất ba nhóm:
1. **Malformed**: không parse được JWT, ví dụ `not-a-jwt`.
2. **Well-formed but untrusted signature**: claims hợp lệ và cùng `kid`, nhưng ký bằng key khác.
3. **Signature valid, business validation failed**: issuer, audience, time hoặc scope sai.

Nếu chỉ thử malformed string rồi gọi “signature test”, parser có thể reject **trước** khi verify RSA. Lab đã thêm group 2 để chứng minh signature verification thật.

### 15.2. Không đánh đồng signature và authorization

Token ký bằng đúng private key vẫn có thể thiếu scope. Response khi đó nên 403, không phải 401. Điều này cho thấy authentication thành công nhưng authorization fail. Tên test phải phản ánh phân biệt này.

### 15.3. Header algorithm âm bản

Nếu app kỳ vọng RS256, test nên reject `alg=none` hoặc algorithm ngoài allowlist. Có thể tạo unsigned token **chỉ để test** rồi assert decoder rejects; không copy token đó làm sample credential dùng trong production. Việc tạo token không an toàn trong test không phải lý do hạ security production.

### 15.4. Tampered payload

Nếu lấy JWT signed đúng, đổi `sub`/`scope` trong phần payload nhưng giữ signature, chữ ký không còn hợp lệ. Test có thể assert 401. Tuy nhiên phải đảm bảo payload còn là JSON/base64url well-formed để test thật sự tới signature verification; group test key-forgery ở lab là cách kiểm dễ lý giải hơn.

### 15.5. RSA/ECDSA/HMAC trade-offs

Bài lab dùng RSA 2048 cho tính tương thích, không đề xuất tự viết crypto. Trong hệ thống thật, dùng thư viện đã được audit, key management/KMS/issuer đáng tin, thuật toán/key length theo security policy. Không dựng JWT bằng nối strings và tự viết RSA signing trừ khi đang test một thư viện crypto chuyên dụng.

## 16. Thiết kế test production-like nhưng không phụ thuộc IdP production

### 16.1. Test-only issuer

Có thể dùng test realm/tenant riêng của một identity provider hoặc fake JWKS server. Không dùng production users, tokens, OAuth client secrets hoặc refresh tokens trong source code/test report. Thông tin test identity phải synthetic.

### 16.2. Deterministic time

Nếu test cần expires đúng mili giây, dùng injectable `Clock` và validator clock skew cố định. Sample chọn lệch vài phút để giảm flake trong môi trường có wall clock thực. Nên kiểm sync NTP giữa services trong CI security integration.

### 16.3. Isolated keypair per test context

Sinh keypair tại test context startup giúp không lưu private key vào repo. Nếu test chạy song song và chia sẻ context, signer/verifier dùng cùng keypair bean. Nếu mỗi class tự sinh keys và context caching sai, có thể gặp valid token bị reject do verifier dùng key khác; giữ cấu hình rõ và test isolation.

### 16.4. Verify actual HTTP token path

Phải có request với:
- Header `Authorization: Bearer <token>` do test signer tạo.
- Spring Security filters enabled.
- Real decoder bean.
- Negative cases signature/claims.
- Assertions status và business authority.

Nếu thay header bằng `with(jwt())`, đường verify đã bị bỏ qua dù test vẫn chạy MockMvc.

### 16.5. JWKS stub và network test

Để kiểm key discovery:
- Khởi động WireMock/MockWebServer trên port test.
- Expose metadata `/.well-known/openid-configuration` hoặc configured JWK Set URI.
- Return JWKS public keys.
- Configure Resource Server issuer URI và JWKS URI trỏ local server.
- Send signed token to resource server.
- Verify requests tới JWKS, behavior khi 404/503/timeout/rotation.
- Đảm bảo local stub và decoder cache lifecycle phù hợp.
- Không fake decoder nếu mục tiêu là JWKS client.

Tầng này bổ sung cho project runnable, không phải một phần đã triển khai trong lab `TestJwtSupportConfig`.

## 17. Chi tiết bảo mật ngoài JWT mà test có thể bỏ sót

### 17.1. CSRF

Nếu ứng dụng sử dụng session cookie, CSRF protection cho các method thay đổi trạng thái quan trọng. `@WithMockUser` không tự chứng minh CSRF token được issue/validate đúng. Với MockMvc, dùng `csrf()` postprocessor để kiểm behavior policy, và browser/session integration cho flow thực. Bearer-only stateless APIs thường có threat model khác; không tắt CSRF theo công thức cứng.

### 17.2. CORS

CORS là browser enforcement liên quan Origins/preflight, không quyết định chữ ký JWT. Test principal mock có thể bypass browser Origin handling. Cần test `OPTIONS` preflight, allowed origins, credentials/cookie rules, và reverse proxy headers theo contract.

### 17.3. Session fixation và cookie flags

Nếu form/OIDC login tạo session, test cookie `Secure`, `HttpOnly`, `SameSite`, rotation of session ID, logout invalidation và redirects. Resource-server unit tests với `jwt()` không chạm các thành phần này.

### 17.4. Redirect and open-redirect validation

OAuth2 authorization flow có `redirect_uri`/state, cần chống callback injection/open redirect. Mocked Authentication bypass hoàn toàn. Dùng browser/test IdP integration hoặc protocol-level tests với negative inputs.

### 17.5. MFA step-up và token freshness

Nếu API sensitive yêu cầu MFA, không chỉ kiểm `SCOPE_...`. Dùng validated `amr`/`acr`/`auth_time` claims và policy, nhưng cũng cần verify issuer đã thực hiện MFA đúng flow. Một claim `amr=["mfa"]` tự đặt bằng `jwt()` chỉ là giả định test.

### 17.6. Revocation và logout

JWT có thể cryptographically valid cho đến `exp` dù user logout. Nếu business cần revocation tức thì, phải có mechanism riêng và test actual revocation events/denylist/session token introspection. Đừng coi 401 cho expired token là chứng minh logout.

### 17.7. Rate limiting và brute-force mitigation

Mock login tránh actual credential check nên không thể chứng minh lockout/rate limit. Dùng test identity provider hoặc authentication endpoint integration có synthetic users và isolation, không tạo traffic tới IdP production.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Test `jwt()` PASS nhưng Bearer thật 401 | Decoder/issuer/audience/signature/time config sai | Gửi signed token và inspect validator errors |
| @WithMockUser PASS dù user không tồn tại | Mock user là fixture, không gọi repository | Thêm authentication integration test |
| `@WebMvcTest` không start | Thiếu `JwtDecoder` hoặc collaborator | `@MockitoBean`/`@Import` đúng slice |
| Bearer hợp lệ nhưng 403 | Scope mapping thiếu `SCOPE_` hoặc sai policy | Kiểm actual granted authorities |
| JWT signed bằng key đúng nhưng 401 | Issuer/audience/time mismatch | Kiểm validator và expected claims |
| JWT với same kid mà attacker key vẫn PASS | Signature verification bị bypass/sai trust | Kiểm real decoder, algorithm/key selection |
| HTTP no-token trả 200 | Endpoint matcher/filter chain thiếu | Bảo đảm filters bật, test no-auth 401 |
| `@AutoConfigureMockMvc(addFilters=false)` PASS | Security filters bị loại | Dùng filters thực trong security tests |
| jwt() claims issuer sai vẫn 200 | Mock postprocessor bypass validation | Đây là expected for policy mock, thêm signed test |
| Wrong audience vẫn 200 | Audience validator chưa cấu hình | Boot `audiences` hoặc custom validator |
| Test expired 1 giây trước nhưng vẫn 200 | Clock skew tolerance | Đặt test xa boundary hoặc cấu hình clock/skew |
| JWT scope claim có nhưng authority rỗng | Converter claim name/schema khác | Kiểm `JwtGrantedAuthoritiesConverter` |
| `@PreAuthorize` không chạy | Chưa bật method security hoặc self-invocation | `@EnableMethodSecurity`, Spring proxy |
| Token issuer metadata/JWKS không truy cập | Network/HTTPS/metadata URL sai | Local JWKS stub/logs/timeout/truststore |
| Key rotation token mới 401 | Cache/JWKS chưa refresh/key missing | Test key rotation integration |
| ID token gọi API vẫn 200 | Thiếu audience/type policy | Validate token intended use |
| Logout rồi JWT còn usable | Stateless token chưa revoked | Thiết kế revocation/short TTL |
| Mock principal type không như expected | @WithMockUser vs jwt() authentication classes khác | Assert loại Authentication và boundary |
| Tests pass nhưng production login fail | Chỉ kiểm downstream policy | Thêm IdP/browser full-flow tests |
| Leak Bearer token trong logs | Debug headers không được scrub | Redact Authorization/cookies/secrets |

Debug theo thứ tự: **test đang dựng Authentication hay gửi Bearer thật?** Filters có bật? Decoder là mock hay real? Trust keys/allowed alg/issuer/audience validators nào được cấu hình? Request 401 hay 403? Đã đến business method chưa? Chỉ sau khi xác nhận đúng boundary mới sửa expected.

## 19. Bài tập

1. Chạy test `@WithMockUser` với user không tồn tại và giải thích vì sao 200 vẫn hợp lệ trong phạm vi test.
2. Thêm `jwt().authorities("SCOPE_orders:read")` với `iss` sai, quan sát test policy PASS nhưng không chứng minh issuer.
3. Thêm một Bearer token ký đúng RSA, kiểm 200 và principal `alice`.
4. Ký cùng claims bằng một private key RSA khác, giữ nguyên `kid`, kiểm decoder ném `JwtException` và HTTP 401.
5. Ký token đúng nhưng `iss` sai, kiểm 401.
6. Ký token đúng nhưng `aud` không chứa `orders-api`, kiểm 401.
7. Bỏ audience validator trong một nhánh test kiểm soát, quan sát wrong audience có thể lọt qua; phục hồi validator.
8. Tạo token `exp` đã qua 3 phút, kiểm expired 401; giải thích clock skew.
9. Tạo `nbf` ở tương lai 5 phút, kiểm 401.
10. Tạo token hợp lệ với scope `orders:write`, kiểm 403 chứ không 401.
11. Thay `JwtGrantedAuthoritiesConverter` đọc claim `permissions`, tạo test real signed token tương ứng.
12. Thử `@AutoConfigureMockMvc(addFilters=false)` trên một test no-token, giải thích vì sao security assertions bị vô hiệu.
13. Viết `@WebMvcTest` chỉ test controller routing, sau đó lập test signed-token full context riêng.
14. Cấu hình một JWKS stub local có hai keys A/B; test key rotation và cache semantics.
15. Cấu hình production-like `issuer-uri` và `audiences` trong profile integration, test metadata/JWKS discovery.
16. Tạo một ID token signed đúng nhưng audience client ID khác API, kiểm Resource Server từ chối.
17. Thêm `@PreAuthorize` trên business service và kiểm method-level policy bằng mock user.
18. Thêm test real JWT từ user khác truy cập order không thuộc sở hữu của họ; kiểm object-level authorization.
19. Thiết kế browser OAuth2 Authorization Code + PKCE flow test với `state`/`nonce`/`redirect_uri` negatives.
20. Lập test MFA/step-up dùng test IdP, phân biệt mock `amr` claim và thực thi MFA.
21. Thiết kế logout/revocation test cho JWT còn hạn, phân biệt token validity và session state.
22. Bổ sung security logging kiểm Authorization header/secret không bị ghi vào test report.
23. Giả lập JWKS endpoint unavailable và đánh giá fail-closed/error policy.
24. Kiểm 401 vs 403 với error response contract và `WWW-Authenticate` phù hợp.
25. Tạo bảng map “test nào chứng minh điều gì”, dùng làm QA checklist cho module authentication.

## 20. Checklist review test authentication

- [ ] Mục tiêu là authentication, token validation hay authorization?
- [ ] Test name phản ánh boundary thực sự được kiểm?
- [ ] `@WithMockUser` chỉ được diễn giải là mocked principal?
- [ ] `jwt()` chỉ được diễn giải là mock JwtAuthenticationToken?
- [ ] Không coi `@MockitoBean JwtDecoder` là cryptographic verification?
- [ ] Có test HTTP Authorization Bearer token thật?
- [ ] Spring Security filter chain có được bật trong test?
- [ ] Không dùng `addFilters=false` cho test JWT/security?
- [ ] Decoder là real implementation khi test signature?
- [ ] Test RSA signature hợp lệ và private key không đáng tin?
- [ ] Sai issuer bị reject?
- [ ] Sai audience bị reject?
- [ ] Expired và future-nbf bị reject với clock skew tính toán?
- [ ] Thiếu scope trả 403 khi credential hợp lệ?
- [ ] Không token/malformed/signature invalid trả 401?
- [ ] Authority converter được kiểm từ claim token đã validate?
- [ ] Algorithm allowlist không tin header tùy ý?
- [ ] Không fetch JWKS URL không đáng tin từ token?
- [ ] Test keys nằm trong `src/test`, không dùng production secrets?
- [ ] JWKS discovery/key rotation có test riêng khi hệ thống phụ thuộc?
- [ ] Full OAuth2/OIDC login/PKCE có test riêng nếu business yêu cầu?
- [ ] OIDC ID token và API access token không bị trộn mục đích?
- [ ] MFA, session, logout, revocation, CSRF, CORS được kiểm đúng boundary?
- [ ] Có kiểm object/tenant-level authorization ngoài scope token?
- [ ] Không log Bearer tokens, private keys, cookies hoặc PII?
- [ ] Test time/clock skew và key cache không làm suite flaky?
- [ ] Maven/JUnit và CI reports xác nhận tests thực sự executed?

**Kết luận:** Một `Authentication` được mock giúp kiểm quyền, nhưng không cho biết caller đã vượt qua bước đăng nhập hay JWT đã được kiểm chữ ký. `@WithMockUser` và `MockMvc jwt()` cố tình bypass credential verification để test policy nhanh. Khi yêu cầu chứng minh Resource Server chấp nhận đúng JWT và từ chối token giả, hãy gửi **Bearer JWS thực sự được ký bằng test key**, giữ filter chain/decoder thật và kiểm signature, issuer, audience, time và scope. Còn khi yêu cầu chứng minh **toàn bộ luồng xác thực** — PKCE, redirect, IdP credentials, MFA, session — cần integration/E2E tests ở authentication server/browser boundary tương ứng. Không nâng phạm vi kết luận vượt qua những bước mà bài test đã chạy.

## 21. Tài liệu chính thức

- Spring Security 6.5 — Testing OAuth 2.0 (MockMvc jwt()/oauth2Login()/oidcLogin()): https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html
- Spring Security 6.5 — @WithMockUser and Method Security Testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html
- Spring Security 6.5 — SecurityMockMvcRequestPostProcessors.jwt() Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html
- Spring Security 6.5 — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — OAuth2 Resource Server Bearer Token: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html
- Spring Security 6.5 — OAuth2 Login: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/index.html
- Spring Security 6.5 — Authorization and Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — NimbusJwtDecoder Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html
- Spring Security 6.5 — NimbusJwtEncoder Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html
- Spring Boot 3.5 — OAuth2 Resource Server auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — MockitoBean test overriding: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- RFC 7515 — JSON Web Signature (JWS): https://www.rfc-editor.org/rfc/rfc7515
- RFC 7517 — JSON Web Key (JWK): https://www.rfc-editor.org/rfc/rfc7517
- RFC 8725 — JSON Web Token Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 7636 — PKCE: https://www.rfc-editor.org/rfc/rfc7636
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
