# Token đúng, sai chữ ký, sai issuer, sai audience và sai loại

Khi xây dựng **Spring Security OAuth 2.0/OIDC Resource Server**, một integration test có giá trị phải chứng minh API chỉ chấp nhận access token đáp ứng đúng trust contract. Một JWT có cấu trúc hợp lệ và có chữ ký không đồng nghĩa nó được phát hành bởi issuer mà API tin cậy, dành cho API đó hoặc thuộc đúng loại token.

Một bộ kiểm thử cần phân biệt ít nhất năm trường hợp:

1. **Token đúng:** chữ ký hợp lệ, issuer tin cậy, audience chứa Resource Server, thời gian hợp lệ và token đúng profile access token.
2. **Sai chữ ký:** token được ký bằng private key khác với key mà Resource Server tin cậy, hoặc chữ ký bị sửa.
3. **Sai issuer:** chữ ký hợp lệ nhưng claim `iss` không đúng Authorization Server được cấu hình.
4. **Sai audience:** token do issuer tin cậy ký nhưng được cấp cho client/API khác.
5. **Sai loại:** token có thể được ký bởi cùng issuer, nhưng là ID token, JWT assertion hoặc một loại JWT khác chứ không phải access token dành cho API.

Các trường hợp âm phải đi qua **đúng authentication filter và decoder/introspector của ứng dụng**. Với JWT, hãy tạo token test được ký bằng keypair riêng, cấu hình decoder chỉ tin public key tương ứng, rồi gửi token qua HTTP `Authorization: Bearer`. Dùng `mockJwt()` hoặc dựng `JwtAuthenticationToken` trực tiếp sẽ bỏ qua phần xác minh chữ ký và claims mà integration test cần chứng minh.

> **Một token chỉ được chấp nhận khi tất cả lớp kiểm tra đều đạt:** chữ ký/nguồn tin cậy, issuer, audience, thời gian, token profile/type và quyền cần thiết. Chữ ký đúng chỉ là một phần của điều kiện.

## 1. Trust contract của một JWT access token

Một JWT thường có ba phần:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Header mô tả thuật toán và metadata JOSE; payload chứa claims; signature bảo vệ tính toàn vẹn của header và payload theo thuật toán đã chọn. Resource Server phải kiểm tra token theo profile mà hệ thống đã thống nhất với issuer.

Ví dụ access token theo JWT Profile for OAuth 2.0 Access Tokens:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "client_id": "orders-web",
  "iat": 1893459000,
  "exp": 1893459600,
  "jti": "at-3d91c8",
  "scope": "orders.read orders.write"
}
~~~

Header có thể có:

~~~json
{
  "alg": "RS256",
  "kid": "test-key-1",
  "typ": "at+jwt"
}
~~~

Các thành phần quan trọng:

| Thành phần | Câu hỏi mà Resource Server cần trả lời |
|---|---|
| Signature | Token có được ký bởi private key tương ứng với một public key tin cậy và không bị sửa không? |
| `iss` | Ai đã phát hành token? Có đúng issuer được cấu hình không? |
| `aud` | Token được cấp cho resource/API nào? Có chứa identifier của API hiện tại không? |
| `exp`, `nbf`, `iat` | Token có nằm trong cửa sổ thời gian được phép không? |
| `typ` / token profile | JWT này có đúng là access token theo profile mà API chấp nhận không? |
| `scope` / authorities | Token đã được xác thực có quyền thực hiện thao tác này không? |

Không được dùng một claim do token tự khai báo để quyết định trust trước khi xác minh chữ ký. Ví dụ, không lấy `iss` chưa xác minh rồi tải JWKS từ URL bất kỳ trong claim đó. Issuer và key source phải đến từ cấu hình/discovery trust đã thiết lập.

## 2. Phân biệt authentication failure và authorization failure

Các test dưới đây cần phân biệt:

- **401 Unauthorized:** không thể xác thực credential: chữ ký sai, issuer sai, audience sai, token hết hạn, token sai profile/type hoặc không có token khi endpoint yêu cầu authentication.
- **403 Forbidden:** token đã xác thực thành công nhưng không có authority cần thiết hoặc bị domain policy từ chối.
- **2xx:** authentication và authorization đều đạt, đồng thời business operation thành công.

Ví dụ:

| Token/request | Kết quả thường mong đợi |
|---|---:|
Không gửi Bearer token tới endpoint được bảo vệ | 401 |
JWT ký bằng key không tin cậy | 401 |
JWT sai issuer | 401 |
JWT sai audience | 401 |
ID token được gửi làm access token | 401 |
JWT access token đúng nhưng thiếu `orders.write` | 403 |
JWT access token đúng, đủ scope và domain permission | 2xx |

Không trả 403 cho token có chữ ký sai hoặc issuer sai. Những trường hợp đó chưa tạo được principal authenticated. Ngược lại, đừng dùng 401 để che mọi lỗi authorization sau khi token đã được xác thực.

## 3. Cấu hình Resource Server kiểm tra issuer, audience và token type

Spring Security JWT Resource Server dùng `JwtDecoder` để xác minh JWT và `OAuth2TokenValidator<Jwt>` để áp dụng các điều kiện bổ sung.

### 3.1. Cấu hình issuer và audience

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
          audiences:
            - orders-api
~~~

`issuer-uri` giúp Spring Security cấu hình decoder theo metadata/JWKS của issuer. Audience validation cần được hỗ trợ bởi phiên bản/cấu hình đang dùng; nếu không, thêm validator rõ ràng. Không giả định chỉ cấu hình `issuer-uri` là mọi token sai audience sẽ tự bị từ chối.

Với decoder tự cấu hình:

~~~java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withJwkSetUri(trustedJwkSetUri).build();

OAuth2TokenValidator<Jwt> issuerAndTime =
    JwtValidators.createDefaultWithIssuer(expectedIssuer);

OAuth2TokenValidator<Jwt> audience = jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Required audience is missing",
                null));

OAuth2TokenValidator<Jwt> tokenType = jwt -> {
    Object typ = jwt.getHeaders().get("typ");
    boolean isAccessToken =
        "at+jwt".equals(typ) || "application/at+jwt".equals(typ);

    return isAccessToken
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "JWT is not an access token",
                null));
};

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        issuerAndTime,
        audience,
        tokenType));
~~~

Đây là mẫu cho hệ thống dùng RFC 9068 và thống nhất header `typ` theo profile đó. Nếu issuer có profile khác, hãy kiểm tra loại token theo contract cụ thể; không tùy tiện chấp nhận mọi `typ`. Với RFC 9068, `at+jwt` là dấu hiệu quan trọng để phân biệt JWT access token với các loại JWT khác. Một số profile/implementation có thể dùng media type `application/at+jwt`; chỉ cho phép dạng đó nếu contract triển khai yêu cầu.

`JwtValidators.createDefaultWithIssuer(...)` cung cấp các kiểm tra chuẩn theo Spring Security, bao gồm issuer và timestamp validators mặc định. Audience và loại access token được ghép thêm thành policy rõ ràng.

### 3.2. Cấu hình thuật toán tin cậy

Resource Server không nên để token tự chọn thuật toán tùy ý. Với RSA test key, decoder có thể được cấu hình trực tiếp:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withPublicKey(trustedRsaPublicKey)
    .signatureAlgorithm(SignatureAlgorithm.RS256)
    .build();
~~~

Khi dùng JWKS, cấu hình key source/issuer phải tin cậy và decoder chỉ chấp nhận thuật toán được policy cho phép. Không chấp nhận `alg=none`, không tự chuyển sang HMAC chỉ vì header token yêu cầu và không lấy thuật toán từ dữ liệu chưa xác minh để thay đổi trust policy.

### 3.3. `typ` không giống `token_type`

Hai giá trị thường bị nhầm:

| Giá trị | Nằm ở đâu | Ý nghĩa |
|---|---|---|
| JOSE header `typ: at+jwt` | JWT header | Loại JWT theo access-token profile |
| OAuth token response `token_type: Bearer` | JSON response từ token endpoint | Cách client trình access token trong HTTP request |

`token_type=Bearer` không chứng minh JWT là access token theo RFC 9068. Nó cũng không thay thế kiểm tra `typ` hoặc issuer/audience.

### 3.4. ID token không phải access token

OIDC ID token mô tả kết quả authentication cho một OIDC client. Nó thường có audience là client ID, có thể có `nonce`, `auth_time` và các claims authentication. Access token được cấp để gọi Resource Server và phải có audience/resource phù hợp.

Ngay cả khi ID token được ký bởi cùng OP và chữ ký hợp lệ, API không được chấp nhận nó như access token. Dùng token profile/type validation và audience validation để ngăn token substitution/cross-JWT confusion.

## 4. Thiết lập integration test bằng keypair riêng

Một test đáng tin cần tự kiểm soát private key dùng để ký token và public key mà decoder tin cậy:

~~~text
Test token issuer
  private key A
      |
      +-- sign valid token
      +-- sign wrong-issuer token
      +-- sign wrong-audience token
      +-- sign wrong-type token

Resource Server under test
  trusts public key A
      |
      +-- accepts only token satisfying validators

Rogue test issuer
  private key B
      |
      +-- sign wrong-signature token
           (decoder does not trust public key B)
~~~

Không dùng private key production trong test. Test keypair có thể được tạo khi test suite khởi chạy hoặc dùng test fixture cố định trong source control. Nếu dùng fixture cố định, private key chỉ dành cho test và không được dùng ở môi trường thật.

### 4.1. Tạo RSA keypair

~~~java
static KeyPair generateRsaKeyPair() throws GeneralSecurityException {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    return generator.generateKeyPair();
}
~~~

Test tạo hai keypair:

- `trustedKeyPair`: token hợp lệ được ký bằng private key này; decoder tin public key tương ứng.
- `untrustedKeyPair`: token sai chữ ký được ký bằng private key này; decoder không tin public key tương ứng.

### 4.2. Tạo JWT test đã ký thật

Ví dụ helper dùng `NimbusJwtEncoder`:

~~~java
import java.security.KeyPair;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.JwsHeader;

final class TestAccessTokens {

    static String issue(
            KeyPair signingKey,
            String issuer,
            List<String> audience,
            String jwtType,
            String scope) {

        RSAKey rsaJwk = new RSAKey.Builder(
                (RSAPublicKey) signingKey.getPublic())
            .privateKey((RSAPrivateKey) signingKey.getPrivate())
            .keyID("test-key")
            .build();

        JWKSource<SecurityContext> jwkSource =
            new ImmutableJWKSet<>(new JWKSet(rsaJwk));
        JwtEncoder encoder = new NimbusJwtEncoder(jwkSource);

        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audience)
            .issuedAt(now.minusSeconds(30))
            .expiresAt(now.plusSeconds(300))
            .id(UUID.randomUUID().toString())
            .claim("client_id", "orders-web")
            .claim("scope", scope)
            .build();

        JwsHeader headers = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .type(jwtType)
            .keyId("test-key")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(headers, claims)
        ).getTokenValue();
    }
}
~~~

Helper tạo compact JWT có chữ ký RSA thật. Các biến `issuer`, `audience`, `jwtType` và `scope` cho phép tạo token âm nhưng vẫn ký bằng key được tin cậy. Đây là điểm quan trọng để test issuer, audience và type riêng biệt với lỗi signature.

Nếu dự án dùng một phiên bản Spring Security/Nimbus có API builder khác, điều chỉnh imports/API theo BOM của dự án; nguyên tắc test vẫn giữ nguyên: ký token bằng private key test, xác minh bằng public key test đã cấu hình.

### 4.3. Cấu hình decoder dùng public key tin cậy

~~~java
static JwtDecoder testDecoder(
        RSAPublicKey trustedPublicKey,
        String expectedIssuer) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withPublicKey(trustedPublicKey)
        .signatureAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(expectedIssuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    OAuth2TokenValidator<Jwt> type = jwt ->
        "at+jwt".equals(jwt.getHeaders().get("typ"))
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong token type", null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTime, audience, type));
    return decoder;
}
~~~

Mẫu trên chấp nhận đúng `typ=at+jwt`. Nếu profile đã chọn cho phép cả `application/at+jwt`, cập nhật validator theo contract. Đừng nới validator chỉ để một token sai loại trong test có thể đi qua.

### 4.4. Tích hợp decoder vào Servlet Resource Server

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtDecoder jwtDecoder) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.decoder(jwtDecoder)))
        .build();
}
~~~

Đây là Servlet `SecurityFilterChain`. Nếu ứng dụng là WebFlux, dùng `SecurityWebFilterChain` và `ReactiveJwtDecoder`; không dùng lẫn cấu hình Servlet và reactive.

## 5. Ma trận token cần tạo

Dùng một issuer mong đợi và audience của API:

~~~text
EXPECTED_ISSUER = https://identity.example.test
EXPECTED_AUDIENCE = orders-api
EXPECTED_TYPE = at+jwt
EXPECTED_ALGORITHM = RS256
~~~

Tạo các token sau:

| Case | Key ký | `iss` | `aud` | `typ` | Kết quả |
|---|---|---|---|---|---|
| Token đúng | Trusted private key A | Đúng | `orders-api` | `at+jwt` | Chấp nhận |
| Sai chữ ký | Untrusted private key B | Đúng | `orders-api` | `at+jwt` | Từ chối |
| Sai issuer | Trusted private key A | Issuer khác | `orders-api` | `at+jwt` | Từ chối |
| Sai audience | Trusted private key A | Đúng | `billing-api` | `at+jwt` | Từ chối |
| Sai type | Trusted private key A | Đúng | `orders-api` | `JWT` hoặc type không được policy chấp nhận | Từ chối |
| Hết hạn | Trusted private key A | Đúng | `orders-api` | `at+jwt` | Từ chối |
| Chưa có hiệu lực | Trusted private key A | Đúng | `orders-api` | `at+jwt` | Từ chối |
| Đúng token, thiếu scope | Trusted private key A | Đúng | `orders-api` | `at+jwt` | Authentication thành công, authorization từ chối |

Với các test sai issuer/audience/type, token vẫn được ký bằng **trusted private key A**. Nhờ vậy, test chứng minh đúng validator tương ứng đang từ chối token, không bị fail sớm vì signature.

Với sai chữ ký, giữ issuer, audience, type và thời gian đúng; chỉ thay key ký thành private key B. Khi decoder tin public key A, signature verification phải thất bại.

## 6. Kiểm thử tích hợp bằng MockMvc

### 6.1. Test đúng token

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AccessTokenIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    TestTokenFactory tokens;

    @Test
    void acceptsCorrectAccessToken() throws Exception {
        String token = tokens.validAccessToken();

        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk());
    }
}
~~~

Token đi qua Bearer authentication filter, `JwtAuthenticationProvider`, decoder và validators đã cấu hình. Test này chứng minh request được xác thực và được cấp quyền theo fixture.

### 6.2. Test sai chữ ký

~~~java
@Test
void rejectsTokenSignedByUntrustedKey() throws Exception {
    String token = tokens.accessTokenSignedByUntrustedKey();

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

Token vẫn có claims đúng. Chỉ private key ký khác với public key mà decoder tin. Kỳ vọng là 401 do authentication failure.

### 6.3. Test sai issuer

~~~java
@Test
void rejectsTokenFromUnexpectedIssuer() throws Exception {
    String token = tokens.accessToken(
        "https://attacker.example.test",
        List.of("orders-api"),
        "at+jwt",
        "orders.read",
        tokens.trustedSigningKey());

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

Token được ký bằng key tin cậy nhưng claim `iss` khác issuer đã cấu hình. Test này chứng minh issuer validator, không chứng minh signature.

### 6.4. Test sai audience

~~~java
@Test
void rejectsTokenIssuedForAnotherApi() throws Exception {
    String token = tokens.accessToken(
        "https://identity.example.test",
        List.of("billing-api"),
        "at+jwt",
        "orders.read",
        tokens.trustedSigningKey());

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

Token có chữ ký và issuer hợp lệ, nhưng chỉ dành cho `billing-api`. `orders-api` phải từ chối, kể cả khi token có scope tên `orders.read`. Scope không thay thế audience.

### 6.5. Test sai loại token

~~~java
@Test
void rejectsJwtWithWrongTypeHeader() throws Exception {
    String token = tokens.accessToken(
        "https://identity.example.test",
        List.of("orders-api"),
        "JWT",
        "orders.read",
        tokens.trustedSigningKey());

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

Token có chữ ký, issuer và audience đúng; chỉ JOSE `typ` không phải access-token type mà Resource Server chấp nhận. Đây là test độc lập cho token-type validator.

### 6.6. Test đúng token nhưng thiếu quyền

~~~java
@Test
void rejectsValidTokenWithoutRequiredScope() throws Exception {
    String token = tokens.accessToken(
        "https://identity.example.test",
        List.of("orders-api"),
        "at+jwt",
        "profile.read",
        tokens.trustedSigningKey());

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isForbidden());
}
~~~

Trường hợp này khác các test trước: token đã được xác thực thành công, nhưng thiếu `SCOPE_orders.read`, vì vậy kết quả là 403.

### 6.7. Ví dụ TestTokenFactory

Một factory có thể bọc helper ở phần trên:

~~~java
final class TestTokenFactory {

    private final KeyPair trusted;
    private final KeyPair untrusted;

    TestTokenFactory(KeyPair trusted, KeyPair untrusted) {
        this.trusted = trusted;
        this.untrusted = untrusted;
    }

    String validAccessToken() {
        return issue(trusted, EXPECTED_ISSUER,
            List.of("orders-api"), "at+jwt", "orders.read");
    }

    String accessTokenSignedByUntrustedKey() {
        return issue(untrusted, EXPECTED_ISSUER,
            List.of("orders-api"), "at+jwt", "orders.read");
    }

    String accessToken(
            String issuer,
            List<String> audience,
            String type,
            String scope,
            KeyPair signingKey) {
        return issue(signingKey, issuer, audience, type, scope);
    }
}
~~~

`issue(...)` gọi helper `TestAccessTokens.issue(...)` đã trình bày trước. Có thể đặt `KeyPair` và factory trong test configuration hoặc JUnit extension để tái sử dụng. Chỉ test code được truy cập private key.

## 7. Kiểm thử WebFlux bằng WebTestClient

Nếu Resource Server dùng WebFlux, cùng ma trận token vẫn áp dụng; thay MockMvc bằng WebTestClient và dùng reactive decoder.

### 7.1. Cấu hình reactive decoder

~~~java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder(RSAPublicKey trustedPublicKey) {
    NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
        .withPublicKey(trustedPublicKey)
        .signatureAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(EXPECTED_ISSUER);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    OAuth2TokenValidator<Jwt> type = jwt ->
        "at+jwt".equals(jwt.getHeaders().get("typ"))
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong token type", null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(defaults, audience, type));
    return decoder;
}
~~~

API builder/setter cụ thể có thể khác theo Spring Security version; giữ nguyên policy: decoder tin public key A, kiểm issuer/time, audience và access-token type.

### 7.2. Reactive SecurityWebFilterChain

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveJwtDecoder reactiveJwtDecoder) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.jwtDecoder(reactiveJwtDecoder)))
        .build();
}
~~~

### 7.3. Bearer-header test

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveAccessTokenIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Autowired
    TestTokenFactory tokens;

    @Test
    void acceptsCorrectSignedAccessToken() {
        webTestClient
            .get()
            .uri("/api/orders")
            .headers(headers ->
                headers.setBearerAuth(tokens.validAccessToken()))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void rejectsWrongAudience() {
        String token = tokens.wrongAudienceToken();

        webTestClient
            .get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Các case sai chữ ký, issuer và type có cùng cấu trúc: tạo token bằng factory tương ứng, gửi qua `setBearerAuth(...)` và assert 401. Không dùng `mutateWith(mockJwt())` trong các test này vì helper đó tạo authentication đã xác thực, bỏ qua `ReactiveJwtDecoder`.

## 8. Kiểm thử sai loại token: ID token, access token và JWT assertion

“Sai loại” là lỗi dễ bị bỏ sót vì nhiều token đều là JWT và có thể được ký bởi cùng OP.

### 8.1. ID token

OIDC ID token thường có:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice",
  "aud": ["orders-web"],
  "iat": 1893459000,
  "exp": 1893459600,
  "nonce": "oidc-login-transaction"
}
~~~

Token này được tạo cho OIDC client `orders-web`, không phải Resource Server `orders-api`. Nếu API kiểm audience đúng, nó sẽ bị từ chối vì `aud` không chứa `orders-api`. Nếu access-token profile còn yêu cầu `typ=at+jwt`, ID token với type `JWT` cũng bị từ chối.

### 8.2. Test ID token bị từ chối

Tạo một JWT có chữ ký bởi trusted key nhưng:

- `aud` là client ID (`orders-web`).
- `typ` không phải access-token type.
- Có thể có `nonce` theo OIDC fixture.

Gửi token đó trong `Authorization: Bearer`. API phải trả 401. Test này chứng minh ID token không thể thay access token.

Để cô lập type validation, cần thêm một test synthetic khác: giữ `iss`, `aud=orders-api`, `exp`, `nbf` (nếu có), signature đều hợp lệ nhưng đặt `typ=JWT`. Khi đó audience validator không từ chối trước, và type validator phải từ chối.

### 8.3. `token_type=Bearer` không cứu token sai profile

Token endpoint có thể trả:

~~~json
{
  "access_token": "<jwt>",
  "token_type": "Bearer",
  "expires_in": 300
}
~~~

`Bearer` chỉ nói client gửi access token bằng Authorization scheme Bearer. Nó không có nghĩa mọi JWT từ cùng OP (kể cả ID token) đều được phép gửi tới API. Resource Server vẫn phải kiểm chữ ký, issuer, audience, thời gian và token profile.

### 8.4. JWT client assertion

Client assertion có thể được ký bởi cùng client hoặc key được AS tin cậy, nhưng `aud` thường là token endpoint và `sub`/`iss` theo client-authentication profile. Nó không phải access token cho Orders API. Nếu bị gửi tới API, audience và token-type/profile validation phải từ chối.

## 9. Kiểm tra audience đúng cách

### 9.1. Audience là resource identifier

Audience phải xác định Resource Server/resource API theo contract. Ví dụ:

~~~text
orders-api
billing-api
https://api.example.com/orders
~~~

Chọn một dạng canonical và dùng nhất quán giữa AS, client và RS. Không dùng client ID thay audience resource nếu protocol/provider của bạn định nghĩa audience là resource identifier.

### 9.2. Một token có nhiều audience

JWT có thể chứa nhiều audience:

~~~json
{
  "aud": ["orders-api", "reporting-api"]
}
~~~

Nếu policy chấp nhận nhiều resource, validator phải kiểm tra membership theo contract. Nếu policy yêu cầu chỉ một audience duy nhất, cần kiểm tra chính xác số lượng và giá trị. Không tự yêu cầu `aud.size()==1` nếu hệ thống hợp lệ cho phép nhiều audience; cũng không chấp nhận bất kỳ audience nào chỉ vì có một giá trị quen thuộc.

### 9.3. `azp` không thay `aud`

OIDC có thể dùng `azp` (authorized party) để xác định client được phép sử dụng ID token trong các trường hợp liên quan. `azp` không thay thế audience validation của access token tại Resource Server. Đừng dùng `client_id` hoặc `azp` thay cho `aud` chỉ vì chúng đều nhắc đến client.

### 9.4. Sai audience phải fail authentication

Nếu `aud` không chứa identifier của API, không tạo principal authenticated. Đừng chỉ kiểm audience trong controller sau khi đã chấp nhận JWT vào SecurityContext; việc này làm nhiều endpoint/service khác có thể vô tình sử dụng token sai resource.

## 10. Kiểm tra issuer và nguồn public key

### 10.1. Issuer là exact trust boundary

`iss` phải khớp issuer được cấu hình theo contract, bao gồm scheme/host/path và các quy tắc so sánh của profile. Không tự lower-case, bỏ path hoặc chuẩn hóa URL theo ý mình. Hai issuer khác nhau có thể cùng subject hoặc cùng `kid`.

### 10.2. Không tin JWKS URI từ token

Một JWT có thể khai `iss` hoặc `jku`/`x5u` trong header. Resource Server không được dùng dữ liệu do token chưa xác minh cung cấp để tự động tải public key tùy ý. Key source phải gắn với issuer đã cấu hình/discovery metadata được tin cậy.

### 10.3. `kid` không phải bằng chứng chữ ký hợp lệ

`kid` chỉ giúp chọn key trong JWK Set. Kẻ tấn công có thể tự đặt `kid` bằng một giá trị hợp lệ. Decoder vẫn phải xác minh chữ ký bằng public key được chọn. Test wrong signature nên giữ cùng `kid` nếu có thể, nhưng ký bằng keypair khác để chứng minh chỉ `kid` đúng là chưa đủ.

### 10.4. JWKS rotation

Trong môi trường dùng JWKS:

- Token mới có thể mang `kid` mới khi issuer rotate signing key.
- Decoder phải lấy key từ JWKS endpoint tin cậy và refresh theo behavior của implementation.
- Key cũ có thể cần giữ trong thời gian token cũ còn hiệu lực.
- Unknown `kid`, JWKS timeout và key rotation cần test riêng.

Test với `NimbusJwtDecoder.withPublicKey(...)` kiểm chữ ký bằng một public key cố định; nó không kiểm JWKS HTTP fetch/rotation. Muốn kiểm JWKS integration, dùng một test HTTP server phục vụ JWK Set và cấu hình decoder với URI server đó.

## 11. Các trường hợp thời gian và cấu trúc khác

Ngoài năm case chính, nên có một số test boundary:

| Trường hợp | Điều kiện | Kết quả |
|---|---|---|
Expired | `exp` ở quá khứ ngoài clock skew | 401 |
Not yet valid | `nbf` ở tương lai ngoài clock skew | 401 |
Missing `exp` | Profile yêu cầu expiry | 401 |
Future `iat` | `iat` xa trong tương lai | 401 theo validator |
Malformed JWT | Sai compact serialization/base64/JSON | 401 |
Unsupported algorithm | `alg` ngoài allowlist | 401 |
Unknown key ID | Không tìm được key tin cậy | 401 |
Valid JWT, no scope | Signature/claims/type đúng, authority thiếu | 403 |
Valid JWT, enough scope | Tất cả validation và authorization đạt | 2xx |

Không dùng test clock thực tế phụ thuộc thời điểm chạy nếu có thể tiêm `Clock` và dùng fixed time cho custom validator. Với decoder mặc định, tạo token với khoảng thời gian đủ xa để tránh flaky do vài giây clock skew.

## 12. Cách xác minh test thực sự chạy qua decoder

Một integration test có thể vô tình bỏ qua decoder nếu dùng helper mock authentication hoặc tự gắn SecurityContext.

### 12.1. Đường test cần dùng

~~~text
WebTestClient / MockMvc
  Authorization: Bearer <signed test JWT>
          |
          v
Bearer token filter
          |
          v
AuthenticationManager
          |
          v
JwtDecoder / ReactiveJwtDecoder
          |
          +-- signature
          +-- issuer
          +-- audience
          +-- time
          +-- token type
          |
          v
JwtAuthenticationToken
          |
          v
HTTP authorization / controller
~~~

### 12.2. Những cách làm không chứng minh decoder

Các cách sau phù hợp cho test controller/authorization nhưng không chứng minh chữ ký/issuer/audience/type validation:

- `mockJwt()` trong WebTestClient.
- `jwt()`/`mockJwt()` trong MockMvc.
- `@WithMockUser`.
- Tự đặt `SecurityContext` với `JwtAuthenticationToken`.
- Gọi controller method trực tiếp.

Không phải các helper này sai; chúng chỉ trả lời câu hỏi khác. Hãy dùng chúng cho test authorization nhanh, và dùng Bearer-header test cho trust validation.

### 12.3. Kiểm tra fail đúng lớp

Để biết test không bị từ chối vì nguyên nhân khác:

- Sai signature: claims đúng, key ký sai.
- Sai issuer: signature đúng, audience/type/time đúng, issuer sai.
- Sai audience: signature và issuer đúng, type/time đúng, audience sai.
- Sai type: signature, issuer, audience và time đúng, chỉ type sai.

Đây là nguyên tắc **mỗi test thay đổi một điều kiện**. Nếu một token vừa sai issuer vừa sai audience, response 401 không chứng minh validator nào đã chạy.

## 13. Ma trận integration test đề xuất

| Test name | Token construction | Kết quả mong đợi | Điều được chứng minh |
|---|---|---:|---|
`acceptsCorrectAccessToken` | Trusted key + expected iss/aud/typ/time | 200 | Happy path end-to-end |
`rejectsUntrustedSignature` | Untrusted key, mọi claims khác đúng | 401 | Signature verification |
`rejectsUnexpectedIssuer` | Trusted key, issuer sai | 401 | Issuer validator |
`rejectsWrongAudience` | Trusted key, audience API khác | 401 | Audience validator |
`rejectsWrongJwtType` | Trusted key, expected iss/aud, typ sai | 401 | Token-type validator |
`rejectsIdTokenAsAccessToken` | Trusted key, ID-token audience/type | 401 | Token separation |
`rejectsExpiredToken` | Trusted key, exp quá khứ | 401 | Expiry validator |
`rejectsNotYetValidToken` | Trusted key, nbf tương lai | 401 | Not-before validator |
`forbidsMissingScope` | Valid token, scope không đủ | 403 | Authorization |
`allowsRequiredScope` | Valid token, đúng scope | 200 | Authentication + authorization |

Test nên có tên rõ và token factory có tham số cụ thể để reviewer nhìn thấy điều kiện nào thay đổi.

## 14. Ví dụ kiểm thử audience/type validator riêng

Nếu muốn unit-test validator trước integration test:

~~~java
@Test
void rejectsJwtWithoutOrdersAudience() {
    Jwt jwt = Jwt.withTokenValue("test")
        .header("alg", "RS256")
        .header("typ", "at+jwt")
        .claim("iss", EXPECTED_ISSUER)
        .claim("aud", List.of("billing-api"))
        .build();

    OAuth2TokenValidatorResult result = audienceValidator.validate(jwt);

    assertThat(result.hasErrors()).isTrue();
}
~~~

Và token type:

~~~java
@Test
void rejectsJwtThatIsNotAnAccessTokenType() {
    Jwt jwt = Jwt.withTokenValue("test")
        .header("alg", "RS256")
        .header("typ", "JWT")
        .claim("iss", EXPECTED_ISSUER)
        .claim("aud", List.of("orders-api"))
        .build();

    OAuth2TokenValidatorResult result = accessTokenTypeValidator.validate(jwt);

    assertThat(result.hasErrors()).isTrue();
}
~~~

Đây là unit test validator, không có chữ ký và không đi qua filter chain. Nó giúp test policy logic nhanh; integration test với token ký thật vẫn cần thiết để kiểm decoder/validator wiring.

## 15. Những lỗi thường gặp

| Anti-pattern | Hậu quả | Cách đúng |
|---|---|---|
Chỉ kiểm chữ ký | Token hợp lệ về crypto nhưng dành cho API/client khác có thể được nhận | Kiểm `iss`, `aud`, time và type |
Chỉ kiểm issuer | Token của issuer đúng nhưng audience sai vẫn có thể vào API | Audience validator |
Chỉ kiểm audience | Một issuer khác có thể phát token cùng audience | Issuer validator và trusted key source |
Dùng `kid` để quyết định token đáng tin | `kid` là selector, không xác minh signature | Verify signature bằng public key tin cậy |
Tin `jku` từ token | Có thể cho attacker chỉ định key endpoint | Dùng JWKS URI cấu hình/discovery đáng tin |
Chấp nhận ID token như access token | Token substitution/cross-JWT confusion | Audience + token-type/profile validation |
Nhầm `token_type=Bearer` với JOSE `typ` | Không kiểm được JWT purpose | Kiểm `typ`/profile theo contract |
Chỉ kiểm `scope` trong controller | Token sai issuer/audience đã qua authentication | Validate trước khi tạo Authentication |
Sai chữ ký và sai issuer cùng lúc trong một test | Không biết check nào từ chối | Mỗi negative test thay một điều kiện |
Dùng `mockJwt()` để test signature | Decoder bị bỏ qua | Gửi signed JWT qua Bearer filter |
Gán authority trực tiếp để test converter | Converter production không chạy | Test converter riêng và integration pipeline |
Chỉ kiểm response 401 | Có thể endpoint bị từ chối do CSRF/matcher khác | Xác nhận đúng chain và từng điều kiện test |
Chấp nhận `alg=none` | JWT không có chữ ký được tin | Allowlist thuật toán và cấu hình decoder |
Tin `aud` là một string duy nhất | Có thể xử lý sai JWT có nhiều audience hợp lệ | Áp policy audience rõ ràng |
Cho phép mọi `typ` để tương thích | Token loại khác có thể bị nhầm là access token | Chọn profile và allowlist type |

## 16. Checklist triển khai

### Token đúng

- [ ] JWT được ký bằng key thuộc issuer tin cậy.
- [ ] Thuật toán ký nằm trong allowlist.
- [ ] `iss` khớp issuer cấu hình.
- [ ] `aud` chứa đúng Resource Server identifier.
- [ ] `exp`/`nbf`/`iat` hợp lệ theo clock-skew policy.
- [ ] `typ`/token profile đúng với access token mà API chấp nhận.
- [ ] Scope/authority đủ cho endpoint.

### Negative integration tests

- [ ] Token ký bằng key khác bị 401.
- [ ] Token có chữ ký đúng nhưng issuer sai bị 401.
- [ ] Token có chữ ký/issuer đúng nhưng audience sai bị 401.
- [ ] Token có chữ ký/issuer/audience đúng nhưng type sai bị 401.
- [ ] ID token bị từ chối khi dùng làm Bearer access token.
- [ ] Token hết hạn/not-yet-valid bị từ chối.
- [ ] Token hợp lệ nhưng thiếu scope bị 403.
- [ ] Test gửi Bearer header qua filter chain và decoder thật/test decoder có chữ ký.
- [ ] Mỗi negative test chỉ thay đổi một điều kiện chính.

### Trust và key operations

- [ ] Không lấy key URL từ token chưa xác minh.
- [ ] JWKS URI/discovery metadata đến từ cấu hình tin cậy.
- [ ] `kid` chỉ dùng chọn key; signature luôn được xác minh.
- [ ] Test unknown `kid`, key rotation và JWKS outage nếu dùng JWKS.
- [ ] Test keypair không dùng private key production.
- [ ] Log không chứa raw access token.

## 17. Kết luận

~~~text
VALID ACCESS TOKEN
  signature verified with trusted key
  + expected issuer
  + audience contains this API
  + valid time window
  + correct access-token profile/type
  + required authority
        |
        v
      ACCEPT

BAD SIGNATURE / ISS / AUD / TYPE / TIME
        |
        v
       401

VALID TOKEN, INSUFFICIENT SCOPE
        |
        v
       403
~~~

Một integration test tốt không chỉ chứng minh token đúng được chấp nhận. Nó phải chứng minh Resource Server từ chối token được ký bằng key không tin cậy, token từ issuer khác, token dành cho audience khác và JWT sai loại. Để các kết quả có ý nghĩa, hãy ký token test bằng private key riêng, cấu hình decoder tin public key dự kiến và gửi Bearer token qua đúng filter chain.

Với sai issuer, audience hoặc type, giữ signature hợp lệ để kiểm tra từng validator độc lập. Với sai chữ ký, giữ claims đúng và chỉ thay signing key. Phân biệt 401 authentication failure với 403 insufficient authority. Đặc biệt, không dùng ID token thay access token: cùng issuer và cùng khả năng xác minh chữ ký không làm hai token có cùng mục đích.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT, JOSE header và claims `iss`, `aud`, `exp`, `nbf`, `iat`.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token profile, required claims và `typ`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, issuer/audience validation và cross-JWT confusion.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth security practices và token confusion/replay mitigations.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token semantics và validation.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): Authorization Server metadata discovery.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và key identifiers.
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, issuer validation, audience và JWT authentication.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder và WebFlux Resource Server.
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): Nimbus JWT decoder builders và validators.
- [Spring Security API — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): reactive Nimbus decoder.
- [Spring Security API — NimbusJwtEncoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html): tạo JWT ký trong test.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token Authorization header và error responses.
