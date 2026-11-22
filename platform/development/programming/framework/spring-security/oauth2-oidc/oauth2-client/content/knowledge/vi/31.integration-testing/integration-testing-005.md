# 31.5. Kiểm thử ID Token hết hạn, sai issuer, sai audience và sai chữ ký

## 1. Bối cảnh: token endpoint trả 200 không có nghĩa ID Token đáng tin

Một ứng dụng **Employee Portal** sử dụng **Spring Security OAuth 2.0/OIDC Client** để người dùng đăng nhập qua OpenID Provider (OP):

~~~text
Browser
  -> Employee Portal (Relying Party / OAuth2 Client)
      -> Authorization endpoint
      -> Token endpoint
      -> JWK Set endpoint của OpenID Provider
~~~

Trong Authorization Code Flow, OP trả về:

~~~json
{
  "access_token": "<redacted-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "<compact-signed-jwt>"
}
~~~

**ID Token** là bằng chứng xác thực người dùng do OP phát cho **OAuth2/OIDC Client**, khác với **access token** được dùng để gọi Resource Server. Kể cả khi HTTP status là 200 và token chứa tên user hợp lệ, Spring Security vẫn phải từ chối ID Token nếu:

1. **Hết hạn**: claim `exp` không còn hợp lệ.
2. **Sai issuer**: claim `iss` không khớp issuer đã tin cậy.
3. **Sai audience**: claim `aud` không chứa `client_id` của registration hiện tại.
4. **Sai chữ ký**: JWS signature không được xác minh bởi trusted signing key.

Nếu chỉ test:

~~~java
mockMvc.perform(get("/api/me").with(oidcLogin()))
    .andExpect(status().isOk());
~~~

thì chưa chứng minh bốn điều kiện đó. `oidcLogin()` là **Spring Security Test postprocessor** đưa Authentication giả vào request, bỏ qua token endpoint và quá trình giải mã/xác minh JWT thật.

**Mục tiêu bài học:** dùng **fake OP** phát ID Tokens ký thật bằng RSA, cho **Spring Security OIDC Client** tự xử lý authorization-code callback, lấy JWKS và xác minh token. Test đầu tiên phải thành công với token đúng; bốn test tiếp theo phải thất bại khi chỉ thay đổi một yếu tố.

> Ngữ cảnh: Java 17+, Spring Boot 3, Spring Security 6, Servlet/Spring MVC, MockMvc và Nimbus JOSE + JWT. Có phần định hướng tương ứng cho WebFlux. Tất cả hosts, secrets và keys dùng trong bài là fixtures, tuyệt đối không lấy ID Token/client secret từ production.

## 2. Mục tiêu cụ thể của bộ kiểm thử

Sau bài này, cần chứng minh bằng tests:

- **Valid control**: token đúng issuer, audience, thời hạn, nonce và signature được chấp nhận.
- **Expired**: token có `exp` trong quá khứ đủ xa để vượt clock skew phải bị từ chối.
- **Wrong issuer**: token ký bởi trusted key, nhưng `iss` sai, phải bị từ chối.
- **Wrong audience**: token ký đúng, issuer đúng nhưng `aud` không chứa client ID, phải bị từ chối.
- **Bad signature**: claims đúng, JOSE header `kid` trỏ trusted key nhưng signer là key khác, phải bị từ chối.
- **Fail closed**: negative callback không tạo authenticated session hoặc cho phép truy cập endpoint bảo vệ.
- **Kỹ thuật test đúng**: lỗi phải xảy ra ở ID Token validation, không bị che bởi lỗi state/cookie/token endpoint/JWKS.
- **Bảo mật vận hành**: test và logs không tiết lộ signing private key, real credentials, code, refresh token hay raw ID Token.

## 3. Những claim bắt buộc hiểu đúng

Một ID Token JWT payload minh họa:

~~~json
{
  "iss": "https://login.company.example",
  "sub": "employee-0042",
  "aud": "employee-portal-web",
  "exp": 1893456600,
  "iat": 1893456300,
  "nonce": "nonce-tied-to-authorization-request"
}
~~~

Timestamp trên chỉ minh họa. Trong tests hãy tính thời gian tương đối với `Instant.now()`, thay vì hard-code một năm dễ hết hạn.

| Claim | Ý nghĩa | Điều kiểm tra |
|---|---|---|
| `iss` | ID của OpenID Provider phát hành | Khớp trusted issuer chính xác |
| `sub` | Subject theo issuer | Có giá trị hợp lệ và được ánh xạ đúng |
| `aud` | Audience của ID Token | Chứa đúng OAuth client ID |
| `exp` | Thời điểm hết hạn | Chưa hết hạn theo policy clock skew |
| `iat` | Thời điểm phát hành | Phù hợp validation contract |
| `nonce` | Ràng buộc với authentication request | Khớp original authorization request |
| `azp` | Authorized party trong một số trường hợp | Hợp lệ với client/audience rules |
| `auth_time` | Thời điểm user xác thực nếu yêu cầu | Đáp ứng chính sách max_age |

**Không nhầm ba giá trị:**

~~~text
iss = ai phát ID Token?
aud = ID Token dành cho OAuth client nào?
sub = người dùng nào được xác thực bởi issuer đó?
~~~

### 3.1. ID Token audience khác access-token audience

~~~text
ID Token:
  aud = employee-portal-web

Access Token:
  aud = orders-api (khi contract của Resource Server yêu cầu)
~~~

Đừng sửa ID Token audience validator để nhận `orders-api` chỉ vì Portal cần gọi Orders API.

### 3.2. Issuer phải khớp chính xác

~~~text
https://login.example.com/realms/staff
https://login.example.com/realms/partners
~~~

Hai giá trị có thể là hai issuers khác nhau dù dùng chung hostname/JWK infrastructure. Không tự xóa path hoặc ép issuer trùng chỉ vì cùng vendor.

## 4. Spring Security xác minh ID Token ở đâu?

Ở Servlet stack, luồng điển hình:

~~~text
OAuth2AuthorizationRequestRedirectFilter
  -> tạo authorization request, state, nonce
  -> redirect browser tới Authorization Server

OAuth2LoginAuthenticationFilter
  -> xử lý callback authorization code
  -> dùng OAuth2/OIDC authentication provider
  -> đổi code lấy token response
  -> decode/verify ID Token theo ClientRegistration
  -> tạo Authentication khi tất cả checks thành công
~~~

Những thành phần đáng biết:

~~~java
org.springframework.security.oauth2.client.oidc.authentication
    .OidcAuthorizationCodeAuthenticationProvider

org.springframework.security.oauth2.client.oidc.authentication
    .OidcIdTokenDecoderFactory
~~~

`OidcIdTokenDecoderFactory` cung cấp decoder theo `ClientRegistration`, sử dụng issuer/client ID/JWK Set và algorithm policy phù hợp. Trong toàn bộ OIDC login flow còn có các kiểm tra gắn ID Token với authorization request như nonce.

### 4.1. Hai JWT validation paths không giống nhau

Một backend có thể đồng thời:

~~~text
OAuth2 Client:
  Validate OIDC ID Token cho browser login.

OAuth2 Resource Server:
  Validate JWT access token nhận từ caller.
~~~

`JwtDecoder` của Resource Server không tự thay thế factory decoder cho OIDC Client. Mock sai decoder có thể khiến test hoàn toàn không chạm vào mechanism cần xác minh.

### 4.2. Những kết quả cần phân biệt

~~~mermaid
flowchart TD
    A["OIDC callback with code/state"] --> B["Token endpoint returns id_token"]
    B --> C{"JWT parse + trusted JWK/signature"}
    C -->|Invalid| R["Reject login"]
    C -->|Valid| D{"iss, aud, exp and time claims"}
    D -->|Invalid| R
    D -->|Valid| E{"nonce / OIDC flow binding"}
    E -->|Invalid| R
    E -->|Valid| F["Authenticated OAuth2AuthenticationToken"]
~~~

Một callback fail **không tự chứng minh** đã chạy `exp` hoặc signature validator. Nó có thể fail từ state mismatch trước khi token endpoint được gọi.

## 5. Ma trận test: chỉ thay một yếu tố mỗi lần

| Scenario | Issuer | Audience | Expiration | Signing key | Expect |
|---|---|---|---|---|---|
| VALID | Expected | Client ID | Tương lai | Trusted | Thành công |
| EXPIRED | Expected | Client ID | **Quá khứ** | Trusted | Từ chối |
| WRONG_ISSUER | **Unexpected** | Client ID | Tương lai | Trusted | Từ chối |
| WRONG_AUDIENCE | Expected | **Khác client ID** | Tương lai | Trusted | Từ chối |
| BAD_SIGNATURE | Expected | Client ID | Tương lai | **Attacker** | Từ chối |

Trong cả năm scenarios: `nonce`, `state`, token endpoint status và JWK Set response vẫn phải đúng.

**Không** tạo wrong issuer token bằng cách đổi payload sau khi đã ký: signature sẽ sai, che mất nguyên nhân issuer.

## 6. Vì sao cần một fake OpenID Provider?

Một **fake OP** cung cấp:

~~~text
POST /token
  -> HTTP 200 + access_token/id_token

GET /jwks
  -> HTTP 200 + trusted public RSA JWK
~~~

Test khởi tạo OAuth2 authorization request trực tiếp qua Spring Security:

~~~text
GET /oauth2/authorization/oidc-test
  -> 302 Location: <fake-op>/authorize?...state=...&nonce=...
~~~

Sau đó test đóng vai browser gửi callback:

~~~text
GET /login/oauth2/code/oidc-test?code=fake-code&state=<original-state>
~~~

**Điểm thiết yếu:** dùng cùng `MockHttpSession` giữa start và callback để Spring Security tìm được original authorization request. Fake OP chỉ cần phục vụ token/JWKS endpoints, vì test không thực sự mở trang authorization trong browser.

### 6.1. Sơ đồ test

~~~mermaid
sequenceDiagram
    participant Test as JUnit / MockMvc
    participant Portal as Spring Security OAuth2 Client
    participant Fake as Fake OP

    Test->>Portal: GET /oauth2/authorization/oidc-test
    Portal-->>Test: Redirect with state and nonce
    Test->>Test: Save session, parse state/nonce
    Test->>Fake: Set next scenario
    Test->>Portal: Callback with original state, fake code, same session
    Portal->>Fake: POST /token
    Fake-->>Portal: Signed id_token scenario
    Portal->>Fake: GET /jwks (may be cached)
    Fake-->>Portal: Trusted public JWK
    Portal->>Portal: Verify JWS + claims + nonce
    Portal-->>Test: Success or authentication failure
~~~

### 6.2. Không gọi IdP thật trong CI

Fake OP nên bind `127.0.0.1` với random port. Một integration test có kết quả ổn định hơn khi không phụ thuộc credentials production, external network, consent prompts hoặc rate limits của nhà cung cấp.

## 7. Dependencies và công cụ

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("com.nimbusds:nimbus-jose-jwt")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Spring Boot BOM giúp quản lý các dependency versions tương thích. Để giảm thư viện ngoài, ví dụ fake server sử dụng Java JDK `com.sun.net.httpserver.HttpServer`. Khi project dùng Java module system, có thể cần khai báo module `jdk.httpserver` cho tests.

### 7.1. Không dùng jwt() của Resource Server Test cho mục tiêu này

~~~java
.with(jwt())
~~~

chỉ tạo mock JWT Authentication để test Spring Resource Server hoặc controller. Nó không khiến Spring Security OAuth2/OIDC Client đổi code, lấy ID Token và kiểm tra chữ ký.

## 8. RSA keys dùng để tạo valid và invalid signature

Nimbus JOSE:

~~~java
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;

RSAKey trusted = new RSAKeyGenerator(2048)
    .keyID("trusted-kid")
    .generate();
RSAKey attacker = new RSAKeyGenerator(2048)
    .keyID("attacker-kid")
    .generate();

String publicJwks = new JWKSet(
    trusted.toPublicJWK()
).toString();
~~~

Chỉ đưa `trusted.toPublicJWK()` vào fake `/jwks`. Private RSA keys chỉ có trong test process, không gửi qua HTTP.

### 8.1. Cách tạo bad signature thật sự

Giữ:

~~~text
JWT header:
  alg=RS256
  kid=trusted-kid

JWKS:
  kid=trusted-kid -> trusted public key
~~~

nhưng ký bằng **attacker private key**. Khi decoder chọn đúng trusted public key, phép kiểm tra RSA signature phải thất bại. Nếu chỉ đổi header `kid` thành unknown, test có thể fail ở **key lookup**, chưa chắc chứng minh chữ ký sai.

### 8.2. Không thay compact JWT thủ công

Nếu sửa base64url payload của một signed JWT, signature đã mất hiệu lực. Với negative tests `EXPIRED`, `WRONG_ISSUER`, `WRONG_AUDIENCE`, hãy sửa claims trước rồi **ký bằng trusted key** để test chính xác một validator.

## 9. Helper tạo JWT ID Token đã ký

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.time.Instant;
import java.util.Date;

static String signedIdToken(
    RSAKey privateSigningKey,
    String advertisedKid,
    String issuer,
    String audience,
    String nonce,
    Instant issuedAt,
    Instant expiresAt
) throws Exception {
    JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .issuer(issuer)
        .subject("employee-0042")
        .audience(audience)
        .issueTime(Date.from(issuedAt))
        .expirationTime(Date.from(expiresAt))
        .claim("nonce", nonce)
        .build();

    SignedJWT jwt = new SignedJWT(
        new JWSHeader.Builder(JWSAlgorithm.RS256)
            .keyID(advertisedKid)
            .build(),
        claims
    );
    jwt.sign(new RSASSASigner(privateSigningKey));
    return jwt.serialize();
}
~~~

Một valid token có:

~~~text
iss = testIssuer
sub = employee-0042
aud = employee-portal-test
iat = now - 10 seconds
exp = now + 10 minutes
nonce = nonce from /authorize redirect
signature = trusted RSA key
~~~

### 9.1. Vì sao exp case phải điều chỉnh cả iat?

Nếu đặt `exp=now-15 phút` nhưng `iat=now`, `iat > exp` cũng có thể là dữ liệu thời gian bất thường. Để cô lập expiry, dùng:

~~~java
Instant issuedAt = now.minusSeconds(1800);
Instant expiresAt = now.minusSeconds(900);
~~~

Tức là ID Token được phát 30 phút trước và hết hạn 15 phút trước.

## 10. Test ClientRegistration trỏ thẳng đến fake OP

Thay vì dùng issuer discovery thật:

~~~yaml
provider:
  company:
    issuer-uri: https://production-idp.example
~~~

test có thể tạo ClientRegistration trực tiếp:

~~~java
ClientRegistration registration =
    ClientRegistration.withRegistrationId("oidc-test")
        .clientId("employee-portal-test")
        .clientSecret("only-a-test-secret")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
            AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri(
            "{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid")
        .authorizationUri(fakeIssuer + "/authorize")
        .tokenUri(fakeIssuer + "/token")
        .jwkSetUri(fakeIssuer + "/jwks")
        .issuerUri(fakeIssuer)
        .clientName("Test OpenID Client")
        .build();
~~~

Điều này giữ:

- Client ID để validate audience.
- Trusted issuer để validate `iss`.
- JWKS URI để validate signature.
- Token endpoint để Spring Security đổi fake code lấy ID Token.
- Redirect URI/callback theo registration.

`scope("openid")` kích hoạt OIDC login semantics. Không cần UserInfo trong ví dụ vì mục tiêu kiểm tra ID Token; nếu thêm UserInfo endpoint, phải stub và tách lỗi UserInfo khỏi lỗi ID Token.

## 11. MockMvc phải chạy filter chain thật

Một test security chain có thể:

~~~java
@Bean
SecurityFilterChain testSecurityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/me").authenticated()
            .anyRequest().permitAll())
        .oauth2Login(oauth -> oauth
            .successHandler((request, response, auth) ->
                response.setStatus(204))
            .failureHandler((request, response, ex) ->
                response.sendError(401)))
        .exceptionHandling(errors -> errors
            .authenticationEntryPoint(
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
        .build();
}
~~~

Trong code mẫu này:

- Callback **thành công** trả 204 thay vì redirect.
- Callback **thất bại** trả 401 thay vì redirect `/login?error`.
- Request anonymous tới `/api/me` trả 401.

Đây là **test-only policy** giúp assertions rõ ràng. Production có thể giữ default OAuth2 Login redirects; khi đó assertions phải phản ánh redirect thực tế.

### 11.1. Không test bằng cách disable signature validator

Không đặt custom decoder luôn trả token “valid” trong bài này; mục tiêu là để Spring Security thực sự xác minh JWT được fake OP ký.

### 11.2. Tránh lỗi 401 không liên quan token

Nếu valid token cũng bị từ chối vì SecurityFilterChain, thiếu registration bean hoặc failure handler không đúng, negative test không có ý nghĩa. Luôn làm valid baseline thành công trước.

## 12. Fake OP server bằng JDK HttpServer

Server có hai routes:

~~~java
HttpServer server = HttpServer.create(
    new InetSocketAddress("127.0.0.1", 0), 0);
~~~

`0` là ephemeral port do OS cấp. Sau `server.start()`, dùng:

~~~java
String issuer = "http://127.0.0.1:"
    + server.getAddress().getPort();
~~~

Chỉ dùng HTTP localhost cho **test**. Production OIDC issuer/token/JWKS endpoints phải sử dụng HTTPS/TLS và trusted metadata.

### 12.1. JWKS handler

~~~java
server.createContext("/jwks", exchange -> {
    byte[] data = new JWKSet(
        trusted.toPublicJWK()
    ).toString().getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders().set(
        "Content-Type", "application/json");
    exchange.sendResponseHeaders(200, data.length);
    try (OutputStream out = exchange.getResponseBody()) {
        out.write(data);
    }
});
~~~

### 12.2. Token endpoint handler

~~~java
server.createContext("/token", exchange -> {
    try {
        exchange.getRequestBody().readAllBytes();
        String jwt = makeTokenForCurrentScenario();
        String body =
            "{\"access_token\":\"fake-access-token\","
            + "\"token_type\":\"Bearer\","
            + "\"expires_in\":300,"
            + "\"id_token\":\"" + jwt + "\"}";
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "application/json");
        exchange.sendResponseHeaders(200, data.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(data);
        }
    } catch (Exception ex) {
        exchange.sendResponseHeaders(500, -1);
        exchange.close();
    }
});
~~~

Đây là **fixture code fragment**: `makeTokenForCurrentScenario()` được định nghĩa trong helper dưới đây. Fake token handler không xác thực real client secret/authorization code; nó cho phép test tập trung vào OIDC Client validation. Nếu muốn test grant/code/client authentication, phải viết integration test khác cho fake AS behavior.

## 13. Kết hợp các đoạn vào một test fixture

Ta dùng một fixture **FakeOidcServer** quản lý:

~~~java
enum Scenario {
    VALID,
    EXPIRED,
    WRONG_ISSUER,
    WRONG_AUDIENCE,
    BAD_SIGNATURE
}
~~~

State:

~~~java
final AtomicReference<Scenario> scenario =
    new AtomicReference<>(Scenario.VALID);
final AtomicReference<String> nonce =
    new AtomicReference<>();
final RSAKey trusted;
final RSAKey attacker;
final HttpServer server;
final String issuer;
~~~

Sau mỗi test:

~~~java
@BeforeEach
void reset() {
    fakeOp.scenario.set(Scenario.VALID);
    fakeOp.nonce.set(null);
}
~~~

Khi chạy tests song song, một global mutable scenario có thể bị test khác ghi đè. Vì vậy fixture mẫu giả định tests chạy **tuần tự**, hoặc cần tách server theo từng test / dùng correlation ID để route response đúng.

### 13.1. Tạo token theo scenario

~~~java
String makeTokenForCurrentScenario() throws Exception {
    Instant now = Instant.now();
    Scenario current = scenario.get();

    String actualIssuer =
        current == Scenario.WRONG_ISSUER
            ? "https://wrong-issuer.example.invalid"
            : issuer;

    String actualAudience =
        current == Scenario.WRONG_AUDIENCE
            ? "unrelated-client"
            : "employee-portal-test";

    Instant issuedAt =
        current == Scenario.EXPIRED
            ? now.minusSeconds(1800)
            : now.minusSeconds(10);

    Instant expiresAt =
        current == Scenario.EXPIRED
            ? now.minusSeconds(900)
            : now.plusSeconds(600);

    RSAKey signingKey =
        current == Scenario.BAD_SIGNATURE
            ? attacker
            : trusted;

    return signedIdToken(
        signingKey,
        trusted.getKeyID(), // giữ trusted kid cả khi sai chữ ký
        actualIssuer,
        actualAudience,
        nonce.get(),
        issuedAt,
        expiresAt
    );
}
~~~

`signedIdToken()` là helper Nimbus đã định nghĩa ở mục 9.

### 13.2. Không hard-code real nonce

Nonce phải được lấy từ authorization request do Spring Security tạo. Một nonce hard-code dùng chung mọi tests có thể khiến valid case fail ở OIDC flow binding trước khi kiểm tra các claim mục tiêu.

## 14. Đầu tiên: tạo authorization request và giữ MockHttpSession

Test helper:

~~~java
private MockHttpSession beginLoginAndCaptureContext() throws Exception {
    MvcResult started = mockMvc
        .perform(get("/oauth2/authorization/oidc-test"))
        .andExpect(status().is3xxRedirection())
        .andReturn();

    MockHttpSession session = (MockHttpSession)
        started.getRequest().getSession(false);
    assertNotNull(session);

    String location = started.getResponse().getRedirectedUrl();
    assertNotNull(location);

    var query = UriComponentsBuilder.fromUriString(location)
        .build()
        .getQueryParams();
    String state = query.getFirst("state");
    String nonce = query.getFirst("nonce");

    assertNotNull(state);
    assertNotNull(nonce);

    fakeOp.nonce.set(nonce);
    savedState = state; // test field, chỉ giữ cục bộ trong fixture
    return session;
}
~~~

Ở đây `fakeOp` là fixture server, `savedState` là test field. Nếu tests chạy song song, thay các fields này bằng per-test immutable context record.

### 14.1. Tại sao cần state?

`state` gắn callback với original authorization request và chống login CSRF. Nếu gửi callback với state sai, Spring Security có thể từ chối trước token exchange. Đó là **một bài test state riêng**, không chứng minh exp/issuer/aud/signature validation.

### 14.2. Tại sao cần nonce?

Nonce gắn ID Token với original OIDC authentication request. Spring Security có thể lưu raw nonce và gửi hashed nonce; khi fake OP phát ID Token, nó cần trả **giá trị nonce nhận được trong authorization request**. Test không tự đoán nonce.

### 14.3. Cùng session là điều bắt buộc trong flow mẫu

Không khởi tạo authorization request với session A rồi gửi callback với session B. Khi đó authorization request repository không tìm thấy context gốc, dẫn tới false positive negative tests.

## 15. Callback helper chạy cho từng scenario

~~~java
private MockHttpSession performLogin(
    Scenario scenario,
    int expectedCallbackStatus
) throws Exception {
    MockHttpSession session = beginLoginAndCaptureContext();

    fakeOp.scenario.set(scenario);

    mockMvc.perform(
        get("/login/oauth2/code/oidc-test")
            .session(session)
            .param("code", "fake-authorization-code")
            .param("state", savedState)
    ).andExpect(status().is(expectedCallbackStatus));

    return session;
}
~~~

Mục tiêu không phải chứng minh fake authorization code được OP chấp nhận về security semantics; fake token endpoint luôn trả fixture token. **Mục tiêu là đưa JWT có điều kiện đúng/sai tới decoder của OIDC Client trong một callback hợp lệ về state/session.**

## 16. Test valid baseline: ID Token đúng được nhận

~~~java
@Test
void validIdTokenIsAccepted() throws Exception {
    MockHttpSession session =
        performLogin(Scenario.VALID, 204);

    mockMvc.perform(get("/api/me").session(session))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject")
            .value("employee-0042"))
        .andExpect(jsonPath("$.registration")
            .value("oidc-test"));
}
~~~

Một controller probe:

~~~java
@RestController
class CurrentUserController {

    @GetMapping("/api/me")
    Map<String, String> me(
        OAuth2AuthenticationToken authentication
    ) {
        return Map.of(
            "subject", authentication.getName(),
            "registration",
            authentication.getAuthorizedClientRegistrationId()
        );
    }
}
~~~

Khi valid test thành công:

~~~text
Original request state was valid.
Fake token endpoint responded.
JWT parse/signature/claims/nonce validations succeeded.
Authenticated principal persisted in session.
Protected endpoint is accessible.
~~~

### 16.1. Nếu valid baseline fail, dừng kết luận từ negative tests

Nếu tất cả tokens đều fail vì JWKS endpoint 404, negative tests sẽ cho kết quả “bị từ chối” nhưng **không chứng minh** validation của bốn claim. Trước hết phải làm valid flow thành công.

## 17. Test expired: exp quá khứ nhưng signature đúng

~~~java
@Test
void expiredIdTokenIsRejected() throws Exception {
    MockHttpSession session =
        performLogin(Scenario.EXPIRED, 401);

    mockMvc.perform(get("/api/me").session(session))
        .andExpect(status().isUnauthorized());
}
~~~

Fixture:

~~~text
iss: expected
aud: employee-portal-test
nonce: expected
signature: trusted
iat: now - 1800 seconds
exp: now - 900 seconds
~~~

Token hết hạn 15 phút trước nhằm tránh clock-skew tolerance biến test thành flaky.

### 17.1. Không chỉ sửa payload sau khi ký

Nếu sửa `exp` bằng base64url decoder rồi giữ signature cũ, test có thể fail vì signature sai. Luôn ký **sau** khi đặt expiry quá khứ.

### 17.2. Clock skew và custom validator

Thời gian sát `now` thường không phù hợp test integration ổn định. Nếu phải kiểm tra chính xác biên skew, viết **unit test time validator** với Clock/tolerance được cấu hình rõ, không đoán default tolerance.

## 18. Test wrong issuer: iss khác nhưng public key đúng

~~~java
@Test
void wrongIssuerIsRejected() throws Exception {
    MockHttpSession session =
        performLogin(Scenario.WRONG_ISSUER, 401);

    mockMvc.perform(get("/api/me").session(session))
        .andExpect(status().isUnauthorized());
}
~~~

Fixture:

~~~text
expectedIssuer: http://127.0.0.1:<fake-port>
actualIssuer: https://wrong-issuer.example.invalid
aud: expected
exp: future
nonce: expected
signature: trusted
~~~

**Quan trọng:** signature phải đúng, không dùng attacker key ở scenario này. Nếu không, test không chứng minh issuer validation đã chạy.

### 18.1. Issuer có path

`https://id.example/realms/a` và `https://id.example/realms/b` không được tự coi là một issuer. Không sửa validator để chỉ so hostname.

### 18.2. Một public key có thể được tái sử dụng

Ngay cả khi token của một issuer khác được ký bởi key mà client đang tin, issuer check vẫn phải ngăn accepting token từ sai trust boundary.

## 19. Test wrong audience: aud không chứa client ID

~~~java
@Test
void wrongAudienceIsRejected() throws Exception {
    MockHttpSession session =
        performLogin(Scenario.WRONG_AUDIENCE, 401);

    mockMvc.perform(get("/api/me").session(session))
        .andExpect(status().isUnauthorized());
}
~~~

Fixture:

~~~text
clientId in ClientRegistration: employee-portal-test
aud in ID Token: unrelated-client
iss: expected
exp: future
signature: trusted
nonce: expected
~~~

Expected: OIDC Client từ chối vì token không dành cho Relying Party hiện tại.

### 19.1. aud là string hoặc array

~~~json
{"aud": "employee-portal-test"}
~~~

hoặc:

~~~json
{"aud": ["employee-portal-test", "other-client"]}
~~~

Với multiple audiences, cần xét thêm `azp` theo OIDC rules và client policy. Đừng chỉ kiểm tra một string literal rồi bỏ qua các trường hợp array.

### 19.2. Không chấp nhận aud của API

ID Token aud phải dành cho **client ID**, không phải `orders-api` hoặc hostname của downstream API, trừ khi nó cũng thực sự là client ID theo contract (trường hợp này không được suy đoán).

## 20. Test bad signature: dùng signer khác nhưng giữ trusted kid

~~~java
@Test
void badSignatureIsRejected() throws Exception {
    MockHttpSession session =
        performLogin(Scenario.BAD_SIGNATURE, 401);

    mockMvc.perform(get("/api/me").session(session))
        .andExpect(status().isUnauthorized());
}
~~~

Token:

~~~text
iss: expected
aud: expected
exp: future
nonce: expected
JOSE header kid: trusted-kid
JWKS public key: trusted
actual signing private key: attacker
~~~

Nếu Spring Security xác minh chữ ký bằng trusted public key, token phải bị từ chối.

### 20.1. Khác với unknown kid

~~~text
kid=unknown
JWKS does not contain unknown
~~~

có thể fail vì không tìm được key, chưa chắc do cryptographic signature verification. Cả hai nên được test nhưng là **hai cases khác nhau**.

### 20.2. Không nhầm malformed JWT với wrong signature

JWT compact sai base64 hoặc thiếu segment thường fail ở parser. Để test chữ ký, tạo một JWS có định dạng đúng bằng Nimbus và ký bằng key khác.

## 21. Cấu hình @SpringBootTest + @AutoConfigureMockMvc

Một minimal test application có thể dùng:

~~~java
@SpringBootTest(
    classes = IdTokenValidationIT.TestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class IdTokenValidationIT {

    @Autowired MockMvc mockMvc;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({
        TestSecurityConfiguration.class,
        CurrentUserController.class
    })
    static class TestApplication {}
}
~~~

Trong `TestSecurityConfiguration`, khai báo:

~~~java
@Configuration
class TestSecurityConfiguration {

    @Bean
    ClientRegistrationRepository clientRegistrations() {
        return new InMemoryClientRegistrationRepository(
            testClientRegistration());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/me").authenticated()
                .anyRequest().permitAll())
            .oauth2Login(oauth -> oauth
                .successHandler((req, res, a) ->
                    res.setStatus(204))
                .failureHandler((req, res, ex) ->
                    res.sendError(401)))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .build();
    }
}
~~~

`testClientRegistration()` trả fixture ở mục 10 và cần được tạo sau khi fake OP đang nghe trên port. Khi ghép code thật, nên khởi chạy fake server trong static fixture/extension có lifecycle chắc chắn **trước khi Spring context tạo ClientRegistrationRepository**, và stop server trong `@AfterAll` / JUnit extension.

### 21.1. Vì sao một test app mini có ích?

Ứng dụng lớn có thể chứa nhiều SecurityFilterChains, JWT Resource Server, custom login handlers và production issuer-uri. Một minimal context giúp cô lập ID Token validation mà không bị tests khác/auto-discovery chen vào.

### 21.2. Thay handlers production hay test-only?

Test-only success 204/failure 401 dễ assert. Nếu muốn kiểm thử exact production handler behavior, giữ handler production và assert 302 redirect hoặc error page đúng. **Không dùng status 401 của handler như bằng chứng duy nhất**, hãy kiểm tra valid baseline và session sau failure.

## 22. Đảm bảo negative login không tạo Authentication

Đối với mỗi negative case:

~~~java
MockHttpSession session =
    performLogin(Scenario.WRONG_AUDIENCE, 401);

mockMvc.perform(get("/api/me").session(session))
    .andExpect(status().isUnauthorized());
~~~

Tức là:

~~~text
callback rejected
  -> no authenticated OAuth2AuthenticationToken persisted
  -> subsequent protected request is denied
~~~

**Không chỉ nhìn exception message**: một exception có thể bị custom error handler nuốt nhưng SecurityContext đã sai. Test session behavior cho bằng chứng cấp ứng dụng.

### 22.1. Khi session đã login trước đó

Nếu user đã authenticated trước khi thử login lại, failure policy có thể giữ hoặc hủy old Authentication tùy thiết kế. Các negative tests của bài nên bắt đầu với **session mới**, không reuse authenticated session từ valid scenario, để kết quả rõ ràng.

## 23. Tách test decoder trực tiếp và callback integration

Nếu chỉ muốn kiểm tra decoder:

~~~java
import org.springframework.security.oauth2.client.oidc.authentication
    .OidcIdTokenDecoderFactory;
import org.springframework.security.oauth2.jwt.JwtDecoder;

OidcIdTokenDecoderFactory factory =
    new OidcIdTokenDecoderFactory();

JwtDecoder decoder = factory.createDecoder(testRegistration);

assertThrows(RuntimeException.class,
    () -> decoder.decode(expiredSignedJwt));
~~~

`expiredSignedJwt` cần là JWT đã ký thật; fake JWKS endpoint phải chạy để decoder lấy trusted key.

### 23.1. Ưu điểm unit decoder test

- Tập trung vào `exp`, `iss`, `aud` và signature.
- Setup nhanh, ít phụ thuộc session/callback.
- Dễ dùng fixed Clock và trực tiếp kiểm tra validation exception.

### 23.2. Giới hạn

`factory.createDecoder().decode()` không tự chứng minh:

- Original authorization request/state.
- Authorization Code Flow/token endpoint exchange.
- Nonce binding tại OIDC authentication provider.
- Cookie/session persistence.
- Custom success/failure handlers.

Vì vậy nên có cả **decoder tests** và một số **fake OP callback integration tests**.

## 24. Clock skew: tránh flaky expired tests

Một số JWT validators cho phép clock tolerance:

~~~text
server now = 10:00:00
token exp  = 09:59:59
allowed skew = 60 seconds
~~~

Token có thể vẫn được chấp nhận theo policy. Điều đó không nhất thiết là bug.

### 24.1. Expired test nên vượt skew rõ ràng

~~~java
Instant now = Instant.now();
Instant expired = now.minusSeconds(900);
~~~

Giá trị cách 15 phút đủ lớn đối với nhiều default tolerances. Nếu application cấu hình skew dài hơn, test phải điều chỉnh theo policy.

### 24.2. Unit test boundary bằng fixed Clock

Khi cần chính xác biên:

~~~text
exp just inside tolerance -> result according to policy
exp just outside tolerance -> reject
~~~

Nên kiểm tra validator với controlled Clock/clock skew thay vì `Thread.sleep()` và trông đợi thời gian thực làm test ổn định.

### 24.3. Iat và nbf

`iat` tương lai bất thường và `nbf` tương lai có thể cần test riêng theo validator/policy. Không cố tạo cả ba lỗi thời gian cùng lúc nếu mục tiêu chỉ là `exp`.

## 25. OIDC nonce: test bổ sung nên có

Nonce gắn ID Token với authorization request:

~~~text
Original authorization request nonce = N1
ID Token nonce = N2
N1 != N2
=> OIDC login must fail
~~~

Để test, giữ token issuer/audience/expiration/signature hợp lệ nhưng đổi `nonce` trước khi ký.

### 25.1. State khác nonce

`state` gắn authorization callback với request và chống login CSRF. `nonce` gắn ID Token với authentication request. Không thay thế cái này bằng cái kia.

### 25.2. Nonce mismatch không phải wrong issuer

Nếu một wrong issuer test tình cờ dùng wrong nonce, failure có thể đến từ nonce. Bốn scenarios chính phải giữ nonce đúng để không che lỗi.

### 25.3. Không dùng một nonce global trong production

Nonce cần được tạo per-authorization request và đủ entropy. Test nên lấy nonce từ redirect của Spring Security, không ép application dùng nonce cố định.

## 26. Multiple audiences và azp

OIDC cho phép audience nhiều phần tử:

~~~json
{
  "aud": ["employee-portal-web", "another-client"],
  "azp": "employee-portal-web"
}
~~~

Client ID được mong đợi cần nằm trong audience, đồng thời xét OIDC `azp` rules khi cần. Spring Security/validator extensions có thể thay đổi mức kiểm tra bổ sung theo phiên bản, nên test theo security contract đã chọn.

Các cases nên bổ sung:

~~~text
aud includes expected, azp expected -> evaluate other claims, accept if valid
aud includes expected, azp unexpected -> reject under relevant OIDC policy
aud excludes expected                 -> reject
~~~

### 26.1. Cùng issuer không tự cho phép audience khác

Hai registrations:

~~~text
employee-client: clientId=employee-portal
admin-client: clientId=admin-portal
issuer: same company OP
~~~

ID Token `aud=employee-portal` không hợp lệ cho `admin-client` chỉ vì OP/JWKS giống nhau.

## 27. Signature, alg và kid: các trường hợp gần nhau

| Scenario | Cơ chế bị kiểm tra |
|---|---|
| BAD_SIGNATURE, same trusted kid | Cryptographic signature verification |
| Unknown `kid` | Trusted JWK lookup/refresh |
| JWK key sai | Signature verification hoặc key selection |
| Unsupported `alg` | Algorithm allowlist |
| `alg=none` | Unsigned token rejection |
| New key after rotation | JWKS cache/refresh |

### 27.1. Đừng tin JOSE header do token tự khai

Trước khi verification, `alg`, `kid` và optional key URLs là dữ liệu không đáng tin. Client phải ràng buộc thuật toán/key source với trusted ClientRegistration/OP metadata, không lấy key từ arbitrary token-provided URL.

### 27.2. JWKS phải chỉ chứa public material

Fake JWKS response không được vô tình expose RSA private components. Dùng `trusted.toPublicJWK()`.

### 27.3. JWKS caching không nhất thiết GET mỗi lần

Decoder có thể cache JWK Set và refresh khi cần. Test signature validity nên assert outcome, không bắt mọi callback đều thực hiện một network GET `/jwks`.

## 28. Rotation của signing key và cache

Thử:

~~~text
Phase 1:
  JWKS -> key-old
  ID Token signed key-old
  Expected accepted

Phase 2:
  JWKS -> key-old, key-new
  ID Token signed key-new
  Expected accepted after supported JWKS refresh

Phase 3:
  JWKS -> only key-new
  New tokens signed key-new
  Old key trust/revocation follows policy
~~~

Mục tiêu là bảo đảm key rotation không tạo login outage hoặc nới lỏng validation. **Không tự chấp nhận key ngoài trusted JWKS** chỉ vì login cần phục hồi.

### 28.1. Clock và cache tạo bài toán bất đồng bộ

Thời điểm cache hết hạn/JWK refresh có thể phụ thuộc implementation. Dùng fake OP theo test lifecycle, controlled cache configuration và test timeouts thay vì polling mù.

## 29. Multi-tenant và provider mix-up

SaaS có:

~~~text
tenant ACME:
  issuer = https://id.acme.example/oidc
  client_id = portal-acme

tenant GLOBEX:
  issuer = https://id.globex.example/oidc
  client_id = portal-globex
~~~

Negative tests cần bao phủ:

- ACME callback nhận ID Token của GLOBEX issuer.
- ACME callback nhận ID Token aud của GLOBEX client.
- ACME ID Token ký bởi key không thuộc trusted ACME JWKS.
- User đổi tenant trong query nhưng original state/registration vẫn thuộc ACME.

**Không lấy `iss` chưa xác minh từ JWT payload để tự tạo ClientRegistration** rồi coi nó là trusted provider. Expected issuer phải đến từ original authorization request và tenant/client catalog đã được quản trị.

### 29.1. Subject không thay tenant authorization

Ngay cả khi ID Token hợp lệ, user vẫn phải có active membership và resource permissions cho tenant. OIDC authentication thành công không tự mở mọi dữ liệu SaaS.

## 30. Đừng nhầm OIDC ID Token và Resource Server JWT test

| Câu hỏi | Test phù hợp |
|---|---|
 OIDC Client có chấp nhận ID Token hết hạn? | Fake OP + callback/ID Token decoder |
 OIDC Client có chấp nhận sai `iss`? | Fake OP signed ID Token wrong issuer |
 OIDC Client có chấp nhận sai `aud`? | Fake OP signed ID Token wrong client |
 OIDC Client có xác minh chữ ký thật? | Trusted JWKS + bad RSA signature |
 API Resource Server có từ chối access token sai audience? | JwtDecoder/Resource Server integration |
 Controller hiển thị đúng user sau login? | `oidcLogin()` MockMvc |
 Cookie SameSite callback hoạt động trên browser? | Browser E2E / proxy integration |

Một app có thể vừa đóng vai OAuth2 Client, vừa đóng vai Resource Server; hai validators phải được test đúng luồng.

## 31. WebFlux: áp dụng cùng chiến lược với WebTestClient

Với Spring WebFlux, cấu hình:

~~~text
ReactiveClientRegistrationRepository
SecurityWebFilterChain
WebTestClient
WebSession
~~~

Flow vẫn tương tự:

~~~text
GET /oauth2/authorization/oidc-test
  -> redirect with state/nonce
GET /login/oauth2/code/oidc-test?code=...&state=...
  -> fetch fake token
  -> validate ID Token
  -> establish reactive authentication/session
~~~

### 31.1. mockOidcLogin() không kiểm tra chữ ký

~~~java
webTestClient.mutateWith(mockOidcLogin())
~~~

chỉ tạo mock OidcUser/Authentication trên in-process exchange. Không dùng nó để tuyên bố ID Token JWT được xác minh.

### 31.2. Giữ WebSession giữa hai requests

WebFlux callback integration cần cookie/WebSession continuity. Đừng bắt đầu authorization request với một client không lưu cookie rồi callback với session khác, vì sẽ fail ở state correlation.

### 31.3. Reactive decoder không được fail open

Nếu JWKS endpoint đang 503 hoặc không verify được signature, không chấp nhận ID Token chưa xác minh. Test có thể chứng minh login fail closed thay vì tạo một mock principal để bypass.

## 32. Quan sát lỗi mà không lộ thông tin nhạy cảm

Một event có thể được chuẩn hóa:

~~~json
{
  "event": "oidc_login_failure",
  "registrationId": "oidc-test",
  "reasonCategory": "WRONG_AUDIENCE",
  "correlationId": "req-42"
}
~~~

Đây là **application-defined category**, không phải hứa Spring Security luôn tạo đúng chuỗi này. Exception type/message có thể khác theo version và JOSE library.

Không log:

~~~text
id_token=<compact-JWT>
access_token=<Bearer>
refresh_token=<secret>
client_secret=<secret>
authorization_code=<one-time-code>
Authorization: Basic <credential>
Cookie: JSESSIONID=<session-id>
RSA private key
~~~

### 32.1. Không hiển thị raw exception cho browser

Thông báo phù hợp:

~~~text
Không thể xác minh thông tin đăng nhập từ nhà cung cấp.
Vui lòng thử lại hoặc liên hệ hỗ trợ.
~~~

Không đưa stacktrace, JWK keys, raw OAuth error_description hay jwt claims nhạy cảm vào UI.

## 33. Những nguyên nhân làm negative test false positive

| Triệu chứng | Vì sao không chứng minh đúng validator? | Cách giải quyết |
|---|---|---|
| Valid token cũng 401 | Test setup hỏng | Làm valid baseline success |
| Token endpoint 404/500 | Chưa có ID Token để validate | Sửa fake OP |
| JWKS endpoint 404 | Signature validator thiếu key | Trả trusted public key |
| State mismatch | Callback fail trước token exchange | Giữ original state |
| Session mất | Authorization request không tìm thấy | Dùng cùng session |
| Nonce mismatch | Failure ở nonce check | Copy nonce từ auth request |
| Wrong issuer ký bằng attacker | Failure ở signature | Dùng trusted signing key |
| Wrong audience exp đã hết | Failure ở expiration | Đặt exp tương lai |
| Bad signature với unknown kid | Failure ở key lookup | Giữ header kid trusted |
| Sửa payload JWT sau khi ký | Signature invalid | Ký lại sau khi sửa claim |
| Clock skew chấp nhận exp vừa quá hạn | Test ở ranh giới | Exp xa trong quá khứ |
| Dùng oidcLogin() | Decoder không chạy | Fake OP callback |
| Mock JwtDecoder luôn valid | Bypass cơ chế cần test | Dùng real ID Token decoder |
| Test chạy parallel với scenario chung | Token scenario bị đổi | Isolate fixtures |
| Fake OP chưa khởi động khi context tạo bean | Registration URI sai port | Controlled lifecycle |

## 34. Kiểm tra nguyên nhân fail theo thứ tự

~~~text
Unexpected test outcome
    |
    v
Does VALID scenario succeed end-to-end?
    |-- No -> fix session/state/callback/OP/JWKS setup.
    |
    v
Is token endpoint called with response 200?
    |-- No -> callback or fake AS problem.
    |
    v
Does ID Token contain expected nonce?
    |-- No -> authorization request binding problem.
    |
    v
Does JWT signature verify against trusted JWKS?
    |-- No -> signature/key test, not issuer/audience test.
    |
    v
Does iss match ClientRegistration?
    |-- No -> issuer validation should reject.
    |
    v
Does aud contain OAuth client ID?
    |-- No -> audience validation should reject.
    |
    v
Is exp within accepted validity/skew window?
    |-- No -> expiry validation should reject.
    |
    v
Did negative callback leave session unauthenticated?
    |-- No -> inspect failure handler/security persistence.
~~~

## 35. Anti-pattern cần tránh

**1. Dùng `oidcLogin()` để chứng minh signature validation.** Mock Authentication bypass protocol.

**2. Dùng token của production trong CI.** Rủi ro lộ credential và flaky external dependency.

**3. Sửa JWT payload sau khi ký để test wrong issuer/audience/exp.** Lỗi chữ ký che mục tiêu.

**4. Cùng một token có sai chữ ký, exp và issuer.** Không cô lập validator.

**5. Chỉ assert callback != 200.** Có thể fail do session/state/JWKS.

**6. Bỏ qua valid baseline.** Không biết integration có hoạt động hay không.

**7. Dùng fake public JWK nhưng signer là một key khác trong VALID case.** Baseline fail.

**8. Chấp nhận unsigned JWT `alg=none` do claims trông đúng.** Phá trust boundary.

**9. Tắt issuer/audience check vì IdP khác client.** Cần sửa cấu hình/trust contract.

**10. Dùng Resource Server JwtDecoder để suy OIDC ID Token validation.** Hai paths khác nhau.

**11. Cho query param quyết định issuer/JWK URL.** Có nguy cơ SSRF/issuer mix-up.

**12. Dùng session đã authenticated trong negative case mới.** Có thể che failure persistence.

**13. Log ID Token hoặc private RSA key để debug.** Có thể lộ identity/credential.

**14. Chạy parallel tests với shared mutable fake OP scenario.** Kết quả không ổn định.

**15. Bỏ nonce/state validation để callback test dễ chạy.** Khiến integration kém an toàn.

## 36. Bài tập thực hành

### Bài 1 — exp quá khứ sau khi ký

Bạn ký một JWT hợp lệ rồi đổi `exp` trong payload base64url mà giữ nguyên signature.

**Hỏi:** Callback fail có chứng minh expiration validator?

**Giải:** Không. Chữ ký đã sai. Phải đặt `exp` trước, rồi ký bằng trusted key.

### Bài 2 — wrong issuer nhưng cũng bad signature

Token có issuer sai và dùng private key attacker.

**Hỏi:** Test chứng minh issuer validation chưa?

**Giải:** Chưa. Có thể fail ở signature. Giữ trusted signature, chỉ đổi `iss`.

### Bài 3 — wrong audience là Orders API

~~~text
ID Token aud=orders-api
OAuth Client clientId=employee-portal-web
~~~

**Hỏi:** Có hợp lệ?

**Giải:** Không. ID Token audience phải chứa client ID của Relying Party, không phải mặc định tên downstream Resource Server.

### Bài 4 — signer B, header kid A

JWKS chứa RSA public key A, header `kid=A`, JWT ký bằng RSA private key B.

**Hỏi:** Expect?

**Giải:** Signature verification phải fail, dù claims đúng.

### Bài 5 — clock skew

`exp=now-1s` nhưng test vẫn login thành công.

**Hỏi:** Vì sao?

**Giải:** Validator có thể cho phép clock tolerance. Dùng exp quá khứ rõ ràng hoặc unit test Clock cố định.

### Bài 6 — callback state sai

Callback với `state=wrong` và ID Token issuer sai.

**Hỏi:** Có chứng minh issuer validator?

**Giải:** Không. Có thể fail ở state trước khi gọi token endpoint.

### Bài 7 — mockOidcLogin sai issuer

`oidcLogin().idToken(token -> token.claim("iss","wrong"))` rồi GET controller 200.

**Hỏi:** Spring Security có bỏ qua issuer ở production?

**Giải:** Không thể kết luận. Test postprocessor đã tạo Authentication giả; cần fake OP + real decoder test.

### Bài 8 — nhiều registrations chung issuer

Client A có ID `employee-portal`, client B có ID `admin-portal`. ID Token `aud=employee-portal`.

**Hỏi:** Có dùng cho client B không?

**Giải:** Không. Audience phải khớp client ID của registration hiện tại.

### Bài 9 — JWKS timeout

Fake OP trả 503 cho JWKS, login thất bại.

**Hỏi:** Có nên tạm tắt signature verification?

**Giải:** Không. Fail closed và xử lý availability/caching đúng policy.

### Bài 10 — valid baseline cũng fail

Cả năm test đều trả 401.

**Hỏi:** Có thể kết luận bốn negative cases đúng?

**Giải:** Không. Sửa valid token/session/token endpoint/JWKS/nonce cho baseline 204 và authenticated session trước.

## 37. Checklist triển khai

| Câu hỏi | Cần xác nhận |
|---|---|
| Có fake OP/token endpoint local? | Có |
| Có fake public JWKS đúng? | Có |
| Test ClientRegistration dùng issuer/client ID riêng? | Có |
| Không gọi IdP production? | Có |
| Fake token response trả JSON có id_token? | Có |
| JWT compact được ký bằng Nimbus? | Có |
| Trusted public key không chứa private params? | Có |
| Original state được parse và dùng lại? | Có |
| Original nonce được đưa vào ID Token? | Có |
| Dùng cùng MockHttpSession khi callback? | Có |
| Valid baseline callback thành công? | Có |
| Valid session truy cập endpoint protected được? | Có |
| Expired token đủ xa past clock skew? | Có |
| Wrong issuer còn valid signature? | Có |
| Wrong audience còn valid signature? | Có |
| Bad signature dùng attacker signer, trusted kid? | Có |
| Mọi negative login đều bị từ chối? | Có |
| Negative session không authenticated? | Có |
| Không dùng oidcLogin() thay real validation? | Đúng |
| Không mock always-valid decoder? | Đúng |
| Không bỏ qua nonce/state? | Đúng |
| Test JWKS caching/rotation nếu cần? | Có |
| Test multi-registration/tenant nếu cần? | Có |
| Fake OP fixture isolated khi parallel? | Có |
| Logs không chứa raw tokens/keys? | Có |
| Có browser/cookie E2E tests riêng khi cần? | Có |

## 38. Tổng kết

**ID Token chỉ đáng tin sau khi Spring Security xác minh chữ ký, thời hạn, issuer, audience và các ràng buộc OIDC.** Một token có `sub` hay email trông hợp lệ vẫn phải bị từ chối nếu chữ ký sai, exp đã hết, issuer không trusted hoặc audience không chứa ClientRegistration client ID.

Để kiểm thử bốn trường hợp này, cần **RSA-signed JWT fixture và fake OP token/JWKS endpoints**, sau đó cho **OAuth2/OIDC Client callback** chạy qua Spring Security thật. Luôn có valid baseline; bốn negative tests thay **đúng một yếu tố** mỗi lần, giữ state/session/nonce và những claims còn lại hợp lệ. Sau callback lỗi, xác nhận không có authenticated session truy cập endpoint bảo vệ.

`oidcLogin()` hữu ích để test controller/RBAC nhưng không xác minh signature/claims; test decoder trực tiếp giúp cô lập JWT validation, còn fake OP callback integration test chứng minh những kiểm tra đó được tích hợp vào OIDC Login. Với WebFlux, dùng fake OP tương tự qua WebTestClient và WebSession.

**Kết luận:** chất lượng của bộ test không nằm ở việc “token sai đều bị từ chối”, mà ở khả năng chứng minh **token đúng được chấp nhận**, **mỗi lỗi riêng được phát hiện đúng tầng** và **không có đường fallback nào bỏ qua security validation chỉ để đăng nhập thành công**.
