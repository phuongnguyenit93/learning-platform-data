# Token giả lập khác với kiểm thử decoder, chữ ký hoặc introspection thực

## 1. Vấn đề cần phân biệt

Một bài kiểm thử Spring Security có thể trả HTTP `200 OK` khi dùng `jwt()` trong MockMvc hoặc `mockJwt()` trong WebTestClient, dù API thật vẫn **từ chối** JWT vì chữ ký sai, `aud` không đúng, `iss` giả, khóa đã được rotate, token hết hạn hoặc introspection trả `active=false`.

Nguyên nhân: các công cụ giả lập authentication trong `spring-security-test` nhằm thiết lập một `Authentication`/`SecurityContext` đã được coi là hợp lệ để kiểm thử **authorization và business logic**. Chúng **không mặc nhiên phát một Bearer credential thật đi qua decoder hoặc gọi authorization server**. Một test xanh của controller/role không chứng minh việc xác minh token ở ranh giới hệ thống đã an toàn.

Bài học thuộc nhóm **Kiểm thử đăng nhập** trong module Spring Security authentication, nhưng cần phân biệt ba lớp thường bị gọi chung là “login test”:

- **Đăng nhập người dùng** bằng form/session hoặc OIDC `oauth2Login()`: tạo session hoặc thực hiện Authorization Code Flow.
- **Xác thực Bearer access token ở Resource Server**: mỗi request có `Authorization: Bearer ...` được JWT decoder hoặc opaque-token introspector kiểm tra trước khi xây `Authentication`.
- **Ủy quyền truy cập**: sau khi Authentication hợp lệ, rule về scope/role/ACL mới quyết định 200, 403 hoặc 404.

Một JWT test giả có thể kiểm tra lớp cuối nhưng không kiểm tra **chữ ký/claims** ở lớp thứ hai. Tương tự `oidcLogin()` là principal giả để test controller, không chứng minh Spring client đã thực hiện thật OIDC discovery, nonce, state, token exchange hay ID token signature verification.

### Mục tiêu học tập

1. Biết chính xác `jwt()`, `opaqueToken()`, `mockJwt()`, `mockOpaqueToken()`, mock `JwtDecoder` và mock `OpaqueTokenIntrospector` kiểm tra/bỏ qua phần nào.
2. Viết unit/controller tests nhanh với token giả và tuyên bố **đúng phạm vi bằng chứng** của chúng.
3. Dùng `NimbusJwtDecoder` và token RSA/JWS **thật sự ký** để kiểm chứng chữ ký, khóa tin cậy, thuật toán và chính sách `iss/aud/exp/nbf`.
4. Kiểm tra `SpringOpaqueTokenIntrospector` gửi HTTP tới endpoint được kiểm soát, xử lý `active=true/false` và lỗi hạ tầng.
5. Chạy test qua **HTTP filter chain** với Bearer token dạng chuỗi, không dùng postprocessor tạo sẵn principal, để xác minh status/challenge chính xác.
6. Hiểu những gì cần test riêng với IdP/JWKS/introspection server staging: cache, rotation, auth của introspection client, timeout, TLS, revocation.
7. Tránh đưa token thật, private key hay credentials vào log hoặc test fixture công khai.

**Giả định phiên bản:** Java 17+, Spring Boot 3.x / Spring Security 6.5.x, Spring Framework 6.x, Spring Security Test, JUnit Jupiter. Một số class có package hoặc DSL khác ở Spring Security 7.x, nên đối chiếu BOM dự án. Không chạy đoạn mã minh họa production với secret hardcoded.

## 2. Cơ chế đúng: ai xác nhận credential hợp lệ?

### 2.1. JWT Resource Server

~~~text
Client: Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
             |
             v
BearerTokenAuthenticationFilter
             |
             v
JwtAuthenticationProvider
             |
             v
JwtDecoder.decode(rawJwt)
   |- parse compact JWS, kiểm tra cấu trúc/alg
   |- chọn public key tin cậy (cố định hoặc JWKS)
   |- verify signature/MAC
   |- validate exp, nbf, iss, aud, typ, custom policy
             |
        +----+-------+
        |            |
      valid        invalid
        |            |
        v            v
 JwtAuthentication  Authentication failure
        |            |
        v            v
 scope -> SCOPE_*  401, WWW-Authenticate
        |
        v
  AuthorizationManager (scope/ACL)
        |             |
      allow          deny
        |             |
      200/2xx      403/404 policy
~~~

Thứ tự chi tiết và validators phụ thuộc cấu hình, nhưng **điểm then chốt** là token thật phải đi vào `JwtDecoder.decode(String)`, không chỉ đưa `Jwt` object đã tạo sẵn vào `SecurityContext`. Chữ ký đúng **chưa đủ** để token được chấp nhận: issuer, audience, time window, token type và policy scope cũng phải hợp lệ.

### 2.2. Opaque Token Resource Server

~~~text
Client: Authorization: Bearer opaque-secret-value
             |
             v
BearerTokenAuthenticationFilter
             |
             v
OpaqueTokenAuthenticationProvider
             |
             v
OpaqueTokenIntrospector.introspect(rawToken)
             |
             +-- HTTPS POST tới authorization server
             |      (client authentication + token)
             |      <--- {"active":true,"sub":"alice","scope":"orders.read"}
             |
             +-- nếu active false / không xác thực được:
             |      Authentication failure
             |
             v
OAuth2AuthenticatedPrincipal + authorities
             |
             v
AuthorizationManager
~~~

Trong opaque-token mode, **authorization server là nơi xác nhận trạng thái**; application không thể suy ra `active` từ việc token có vài dấu chấm giống JWT. Spring Security cho phép introspect cả token mang dạng JWT nếu resource server được cấu hình theo hướng đó. Đây là thiết kế khác với tự verify chữ ký bằng `NimbusJwtDecoder` và có đặc tính revocation/availability khác.

### 2.3. Nhìn bằng bảng

| Cấp độ kiểm thử | Test làm gì | Chữ ký/JWT time/issuer/audience thật? | Gọi introspection HTTP? |
| --- | --- | --- | --- |
| `MockMvc .with(jwt())` | Đưa `JwtAuthenticationToken` giả vào request/security context | **Không** | Không |
| `MockMvc .with(opaqueToken())` | Đưa principal opaque giả, authorities theo setup | Không | **Không** |
| `WebTestClient .mutateWith(mockJwt())` | Đưa reactive security context có JWT Authentication | **Không** | Không |
| `WebTestClient .mutateWith(mockOpaqueToken())` | Đưa reactive opaque principal | Không | **Không** |
| Mock `JwtDecoder.decode(...)` trả `Jwt` | Kiểm thử filter/provider gọi decoder theo stub | **Không**, vì stub trả kết quả định sẵn | Không |
| Mock `OpaqueTokenIntrospector` trả principal | Kiểm thử provider/authorization mapping theo stub | Không | **Không**, vì stub không gọi HTTP |
| `NimbusJwtDecoder` + token ký thật + key thật | Kiểm chứng JWS, validators được cấu hình | **Có**, trong phạm vi key/validators test | Không |
| `SpringOpaqueTokenIntrospector` + `MockRestServiceServer` | Chạy HTTP client/introspector thật tới mock HTTP transport, kiểm tra active/error | Không | **Có đi qua HTTP client mock**, không phải IdP live |
| Resource Server filter chain + header Bearer ký thật | Kiểm tra kết nối filter → decoder → authorization → HTTP | **Có**, nếu dùng decoder thật | Tùy mode |
| Local test IdP/JWKS/introspection server hoặc staging | Kiểm tra protocol endpoint, discovery, TLS, cache/rotation, client auth | Có nếu cấu hình đúng | Có network thật tới server test |

**Không lấy một test 200 dùng mock principal làm bằng chứng rằng token có chữ ký hợp lệ.** Đặt tên test theo phạm vi thực: `canReadOrdersWithScope()` khác `rejectsWrongJwtSignature()`.

## 3. Dùng token giả đúng mục đích

### 3.1. MockMvc Servlet: `jwt()` và `opaqueToken()`

Giả sử `GET /api/orders` được bảo vệ bằng `hasAuthority("SCOPE_orders.read")` và có controller trả 200 cho user đủ quyền. Các đoạn dưới đây là **snippet đặt trong test class đã thiết lập MockMvc và Spring Security filter chain**, không chạy độc lập:

~~~java
import static org.springframework.security.test.web.servlet
    .request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet
    .request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

// JWT giả: kiểm tra chính sách authorization, không verify chữ ký.
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
   .andExpect(status().isOk());

// JWT giả thiếu scope: kiểm tra từ chối do authorization.
mvc.perform(get("/api/orders").with(jwt()))
   .andExpect(status().isForbidden());

// Opaque principal giả: introspection endpoint không hề được gọi.
mvc.perform(get("/api/orders")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
   .andExpect(status().isOk());
~~~

**Import trong snippet chỉ được trình bày rút dòng vì chiều dài văn bản; trong file Java, mỗi câu lệnh `import` phải nằm trên một dòng duy nhất.** Nên dùng IDE auto-import khi đặt vào project thật; method `jwt` nằm ở `SecurityMockMvcRequestPostProcessors`, không phải `org.springframework.security.oauth2.jwt.Jwt`. Có thể tùy biến claims bằng `jwt().jwt(builder -> builder.claim("scope", "orders.read"))` nhưng đó vẫn chỉ là claim **do test tạo**. Nó không chứng minh JWT được ký/được verify.

Giới hạn: route phải có thật, `MockMvc` phải có Spring Security integration và rule `hasAuthority(...)`; nếu project không đúng setup, status giả định 200/403 không tự bảo đảm. Với HTTP filter riêng chạy JWT decoder thật, **không sử dụng `.with(jwt())`** ở test đó.

### 3.2. Reactive WebTestClient

Với app WebFlux dùng `SecurityWebFilterChain`, `WebTestClient` đã áp dụng Spring Security test support:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Reactive JWT giả, dùng test mapping/authorization:
client.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders").exchange()
    .expectStatus().isOk();

// Reactive opaque token giả:
client.mutateWith(mockOpaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders").exchange()
    .expectStatus().isOk();
~~~

**Cũng là snippet với import rút dòng**, không phải file độc lập; khi paste, chỉnh import thành một dòng. Không kết luận `ReactiveJwtDecoder.decode(...)` hay `ReactiveOpaqueTokenIntrospector.introspect(...)` đã chạy. Nếu muốn kiểm tra reactive decoder/introspector thật, gửi header Bearer ở request thật qua `WebTestClient`, dùng server/test fixture được cấu hình đúng và kiểm tra `Mono`/HTTP status.

### 3.3. Mock decoder và fake principal khác nhau như thế nào?

Cần phân biệt:

- **Principal injection** (`jwt()`, `mockJwt()`): test tạo authentication object và đưa vào security context trước authorization. Phần đọc token từ header và verifier thường bị bypass.
- **Mock `JwtDecoder`**: filter/provider có thể vẫn đọc header Bearer và **gọi** `decode(String)`, nhưng thứ trả về do mock quyết định. Test có thể kiểm tra mapping errors, response 401 và việc decoder được gọi; **không chứng minh RSA signature verification**.
- **Decoder thật**: gửi JWT compact string ký thật, gọi `NimbusJwtDecoder.decode(token)` hoặc đi qua resource server filter. Chỉ kiểu này (với key đúng/khác và validators phù hợp) mới trực tiếp kiểm tra crypto/claims path.
- **Mock introspector**: tương tự mock decoder, nhưng không gửi HTTP đến introspection endpoint; test response handling chứ không kiểm tra request format, authentication header, `active` hoặc network failures thật.

Một anti-pattern:

~~~java
// Test này chỉ chứng minh rằng mock decoder trả Jwt theo setup.
when(jwtDecoder.decode("anything")).thenReturn(fakeJwt);
mvc.perform(get("/api/orders")
        .header("Authorization", "Bearer anything"))
   .andExpect(status().isOk());
~~~

Đây là snippet giả định đã có Mockito, `jwtDecoder`, `fakeJwt`, `mvc`, route hợp lệ. `anything` không cần là JWT compact được ký; vì `JwtDecoder` đã bị stub, test vẫn có thể xanh. Gọi đây là **filter wiring test**, không phải `verifiesJwtSignature` test.

## 4. Chuẩn bị dependency và phân lớp test

Với project Spring Boot 3.x có plugin/BOM quản lý versions, có thể khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-oauth2-resource-server` có các thành phần cần cho JWT decoder và opaque introspector. Spring Boot BOM quản lý versions để JUnit/Spring Security/Nimbus tương thích; không ghép bản Spring Security bất kỳ ngoài BOM mà không đánh giá. `spring-boot-starter-test` cấp JUnit 5, Mockito, Spring Test, MockRestServiceServer và công cụ test MVC.

Tổ chức test nên có:

- **Authorization test nhanh:** mockJwt/mockOpaqueToken, không khởi động IdP, xem route/role/claim mapping và business ACL.
- **Decoder unit test:** `NimbusJwtDecoder` thật, RSA key test được sinh tạm trong memory, JWT thật được ký; kiểm tra signature/issuer/audience/time/algorithm.
- **Introspection HTTP-client component test:** `SpringOpaqueTokenIntrospector` thật và `MockRestServiceServer` giả lập wire response, kiểm tra POST form/client auth và active.
- **Resource Server filter integration:** client gửi `Authorization: Bearer <token>` thật, kiểm tra filter, JWT decoder/introspector, success/401/403 và challenge.
- **Provider contract/e2e:** test server quản lý JWKS/introspection hoặc staging IdP với TLS/client credentials, cache/rotation/revocation/latency; đây là nơi phát hiện lỗi network mà mock transport không thể chứng minh.

Lựa chọn test theo **threat model**. Không cần mọi controller test gọi IdP thật, nhưng các ranh giới tin cậy cần một lớp test kiểm chứng thật.

## 5. JUnit 5: `NimbusJwtDecoder` thực sự kiểm tra chữ ký RSA và claims

Ví dụ này là **một class JUnit 5 đầy đủ** cho Spring Security 6.5.x, sử dụng thư viện Nimbus JOSE + JWT có sẵn qua dependency resource-server. Nó sinh RSA 2048 bit trong test, **ký JWT compact RS256** bằng private key A, kiểm tra bằng public key A, thử chữ ký của private key B và các claim không hợp lệ.

Mỗi test có cặp khóa mới trong memory; không có certificate production hay token thật. `withPublicKey` xác minh bằng khóa public cố định, **không kiểm tra HTTP JWKS/discovery**; loại test đó được tách ở mục 6.

Tạo `src/test/java/example/RealJwtDecoderTest.java`:

~~~java
package example;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RealJwtDecoderTest {

    private static final String ISSUER =
        "https://issuer.example.test/realms/demo";
    private static final String AUDIENCE = "orders-api";

    private KeyPair trusted;
    private NimbusJwtDecoder decoder;

    private static KeyPair newRsaKeyPair() throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @BeforeEach
    void setUp() throws Exception {
        trusted = newRsaKeyPair();

        decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) trusted.getPublic())
            .build();

        // Mặc định timestamp/issuer + validator audience của API.
        var audience = new JwtClaimValidator<List<String>>(
            "aud", value -> value != null && value.contains(AUDIENCE));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience));
    }

    private static String signedJwt(
            KeyPair signingKey,
            String issuer,
            String audience,
            Instant expiresAt) throws Exception {

        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audience)
            .issueTime(Date.from(now.minusSeconds(20)))
            .notBeforeTime(Date.from(now.minusSeconds(10)))
            .expirationTime(Date.from(expiresAt))
            .claim("scope", "orders.read")
            .build();

        SignedJWT signed = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                .type(JOSEObjectType.JWT)
                .keyID("test-key")
                .build(),
            claims);

        signed.sign(
            new RSASSASigner(
                (RSAPrivateKey) signingKey.getPrivate()));

        return signed.serialize();
    }

    @Test
    void acceptsSignedTokenWithTrustedKeyAndValidClaims()
            throws Exception {

        String token = signedJwt(
            trusted, ISSUER, AUDIENCE,
            Instant.now().plusSeconds(300));

        Jwt result = decoder.decode(token);

        assertEquals("alice", result.getSubject());
        assertEquals(ISSUER, result.getIssuer().toString());
        assertTrue(result.getAudience().contains(AUDIENCE));
    }

    @Test
    void rejectsValidRs256SignatureFromUntrustedPrivateKey()
            throws Exception {

        KeyPair attacker = newRsaKeyPair();
        String token = signedJwt(
            attacker, ISSUER, AUDIENCE,
            Instant.now().plusSeconds(300));

        assertThrows(JwtException.class,
            () -> decoder.decode(token));
    }

    @Test
    void rejectsWrongIssuerAlthoughSignatureIsValid()
            throws Exception {

        String token = signedJwt(
            trusted, "https://other-issuer.example.test",
            AUDIENCE, Instant.now().plusSeconds(300));

        assertThrows(JwtException.class,
            () -> decoder.decode(token));
    }

    @Test
    void rejectsWrongAudienceAlthoughSignatureIsValid()
            throws Exception {

        String token = signedJwt(
            trusted, ISSUER, "other-api",
            Instant.now().plusSeconds(300));

        assertThrows(JwtException.class,
            () -> decoder.decode(token));
    }

    @Test
    void rejectsExpiredToken() throws Exception {
        String token = signedJwt(
            trusted, ISSUER, AUDIENCE,
            Instant.now().minusSeconds(600));

        // Tránh nằm trong clock-skew mặc định (thường 60 s).
        assertThrows(JwtException.class,
            () -> decoder.decode(token));
    }

    @Test
    void rejectsMalformedNonJwtString() {
        assertThrows(JwtException.class,
            () -> decoder.decode("not-a-jwt"));
    }
}
~~~

Chạy khi dự án có Gradle wrapper và dependency đồng bộ:

~~~bash
./gradlew test --tests "example.RealJwtDecoderTest"
~~~

**Kết quả mong đợi:** sáu test pass; không có stdout cố định đáng tin vì Gradle/JUnit version và settings ảnh hưởng bản in. Không gắn dấu “đã chạy” nếu chỉ đọc code mẫu.

### Những điều test thực sự chứng minh

- `acceptsSignedToken...`: decoder xác minh JWS RS256 bằng **public key phù hợp**, sau đó xác thực `iss, aud, exp, nbf` theo validators đã cấu hình. Quyền `orders.read` chưa được thử ở controller.
- `rejectsValidRs256SignatureFromUntrustedPrivateKey`: token có định dạng chuẩn và được ký bởi key khác vẫn bị từ chối. Nó khác mock JWT vì có phép kiểm tra chữ ký thật.
- `rejectsWrongIssuer...` và `rejectsWrongAudience...`: **chữ ký hợp lệ không đủ**; token phát cho OP hoặc API khác phải bị từ chối.
- `rejectsExpiredToken`: token đã hết hạn nhiều phút không còn được tin; độ lệch đồng hồ (clock skew) cần policy rõ.
- `rejectsMalformedNonJwtString`: decoder phải từ chối input không phải compact JWT.
- Các test này **không chứng minh** cấu hình bean thật đang dùng đúng decoder; không kiểm tra JWKS HTTP, key rotation, proxy/TLS, header Bearer, conversion `scope→SCOPE_...` hoặc HTTP status. Cần lớp integration phù hợp.

### Các trường hợp cần bổ sung tùy threat model

| Input JWT | Kỳ vọng |
| --- | --- |
| `alg=none` không chữ ký | Rejected; không cho thuật toán vô danh |
| Thuật toán ngoài allowlist | Rejected |
| `kid` không có trong trusted JWKS | Rejected, theo policy cache/refresh |
| `nbf` ở tương lai xa | Rejected |
| `exp` thiếu hoặc sai kiểu | Rejected nếu profile yêu cầu; đừng giả định mọi profile mặc định buộc claim này |
| `aud` là mảng, không chứa API ID | Rejected |
| `iss` domain gần giống nhưng khác chính xác | Rejected |
| `typ=at+jwt` hoặc profile chuyên biệt | Validator type/claims tương ứng, không suy ra từ signature |
| Claims quá lớn, JWS quá dài | Bounded by gateway/server limits, fail safely |
| Token bị revoke khi vẫn còn `exp` | JWT local verification không tự biết revocation; cần denylist/short TTL/introspection/rotation strategy tùy kiến trúc |
| JWKS rotated/old key removed | Cache-refresh/rollover behavior được test với test JWKS server |
| Token ký đúng nhưng account bị disable | Ứng dụng phải áp account-state policy nếu cần, không phải chỉ decoder |

**Cảnh báo quan trọng:** Spring Security có defaults hữu ích nhưng **audience validator thường cần cấu hình rõ**. `NimbusJwtDecoder.withPublicKey(...).build()` không tự biết audience nào là API của bạn. Ví dụ đã đặt `JwtClaimValidator` để phân biệt phần cryptographic trust và phần audience authorization.

## 6. Test JWKS, issuer discovery, rotation khác kiểm thử public key cố định

Ví dụ trên tự cấp public key vào `withPublicKey(...)`. Trong hệ thống thật, application có thể dùng `spring.security.oauth2.resourceserver.jwt.issuer-uri` hoặc `jwk-set-uri`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
          # jwk-set-uri nếu muốn chỉ rõ endpoint JWKS;
          # vẫn cần issuer validator khi cấu hình thủ công.
~~~

Đây chỉ là URL mô phỏng. Với `issuer-uri` Spring Security/JWT decoder có thể dùng metadata discovery tìm `jwks_uri` rồi chọn key tin cậy. Khác với test public key cố định, integration test cần dựng **test OIDC issuer/JWKS server** (ví dụ WireMock hoặc mock HTTP server chạy trên loopback) rồi cấu hình service dùng issuer URL của server ấy.

Một test JWKS đạt yêu cầu cần kiểm tra:

1. Endpoint metadata công bố đúng `issuer` và `jwks_uri`; service không chấp nhận issuer không tin.
2. JWT A có `kid=old`, `alg=RS256` ký private key A; JWKS trả public JWK A; request thành công.
3. Rollover: JWKS chứa A+B, token `kid=new` được ký bởi B; decoder refresh/cache behavior theo cấu hình. **Không giả định** refresh luôn xảy ra ngay tại một thời điểm trong mọi version/cache.
4. JWKS rút A sau grace window; token A phải bị từ chối khi cache cũ được làm mới hoặc policy hết thời gian cho phép.
5. Key giả hoặc token đổi payload nhưng giữ signature cũ bị từ chối.
6. JWKS 500/timeout/TLS failure: fail closed, ghi lỗi vận hành, không tự bỏ qua chữ ký.
7. Header `kid` bất thường và `jku`/`x5u` từ token không được tự phép trỏ decoder tới host bất kỳ: bảo vệ SSRF/trust source.
8. Thiết kế algorithm allowlist để tránh thuật toán bị thay từ token header làm sai trust model.

**Không cấu hình test bằng cách thay decoder thật bằng `@MockBean JwtDecoder`**, rồi gọi đó là key-rotation test. Nếu mục tiêu là discovery/key cache, test phải đi qua decoder và HTTP JWKS client thật (dù remote server do test kiểm soát).

### Mô hình “real” có nhiều cấp

- **Real signature/local decoder**: có RSA verify thật nhưng không có network.
- **Real decoder + mock HTTP JWKS server**: có HTTP fetch/cache/discovery logic nhưng server chỉ là fixture.
- **Real integration staging IdP**: giao thức tới issuer thực ở môi trường kiểm thử; cần credential/secret an toàn và test không flaky.
- **Real production-like end-to-end**: service, gateway, TLS, claim policy, auth server, caching, retry và security controls phù hợp, chi phí cao hơn.

Không vì một tầng không bao phủ mọi thứ mà kết luận test vô ích. Vấn đề là **gắn đúng nhãn cho bằng chứng**.

## 7. JUnit 5: chạy SpringOpaqueTokenIntrospector với HTTP client được kiểm soát

Một token opaque thường không thể decode nội bộ; service cần gửi nó đến endpoint introspection của authorization server với credentials của resource server. Mock `OpaqueTokenIntrospector` chỉ trả sẵn principal nên không kiểm tra POST/form/`active`. Dưới đây là **component test có introspector thật** và `RestTemplate` thật nhưng HTTP response do `MockRestServiceServer` trả; **không gọi IdP ngoài mạng**. Nó kiểm tra tương tác ở boundary của HTTP client.

Tạo `src/test/java/example/OpaqueIntrospectionHttpTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.support.BasicAuthenticationInterceptor;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class OpaqueIntrospectionHttpTest {

    private static final String ENDPOINT =
        "https://idp.example.test/oauth2/introspect";

    private static RestTemplate testRestTemplate() {
        RestTemplate rest = new RestTemplate();

        // Secret giả chỉ dành cho test. Production dùng secret store.
        rest.getInterceptors().add(
            new BasicAuthenticationInterceptor(
                "test-client", "test-secret"));
        return rest;
    }

    @Test
    void activeTokenIsResolvedThroughIntrospectionHttpClient() {
        RestTemplate rest = testRestTemplate();
        MockRestServiceServer http =
            MockRestServiceServer.bindTo(rest).build();

        http.expect(requestTo(ENDPOINT))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess(
                "{\"active\":true,"
                + "\"sub\":\"alice\","
                + "\"scope\":\"orders.read\"}",
                MediaType.APPLICATION_JSON));

        var introspector =
            new SpringOpaqueTokenIntrospector(ENDPOINT, rest);

        var principal = introspector.introspect("opaque-valid");

        assertEquals("alice", principal.getName());
        assertTrue(principal.getAuthorities().stream().anyMatch(
            authority -> "SCOPE_orders.read".equals(
                authority.getAuthority())));
        http.verify();
    }

    @Test
    void inactiveTokenIsRejectedByRealIntrospectorLogic() {
        RestTemplate rest = testRestTemplate();
        MockRestServiceServer http =
            MockRestServiceServer.bindTo(rest).build();

        http.expect(requestTo(ENDPOINT))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess(
                "{\"active\":false}",
                MediaType.APPLICATION_JSON));

        var introspector =
            new SpringOpaqueTokenIntrospector(ENDPOINT, rest);

        assertThrows(BadOpaqueTokenException.class,
            () -> introspector.introspect("opaque-revoked"));
        http.verify();
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests "example.OpaqueIntrospectionHttpTest"
~~~

**Kết quả mong đợi:** cả hai test pass nếu dependency/API đúng. `MockRestServiceServer` chặn request của `RestTemplate` bằng client HTTP giả, nên nó kiểm tra method/url/response parsing/`active` nhưng **không chứng minh kết nối TLS với IdP thực, authorization của client, timeout hoặc revocation live**.

### Thêm assertion để không đánh rơi security contract

Trong test thực tế cần xác nhận HTTP request chính xác:

- `Content-Type: application/x-www-form-urlencoded` và tham số `token` với giá trị được encode đúng, không log token raw. Dùng `MockRestRequestMatchers.content()` để kiểm tra request body.
- `Authorization: Basic ...` hoặc phương thức client authentication mà IdP hỗ trợ, theo cấu hình/secret store. Ở ví dụ interceptor đã thêm Basic auth cho HTTP client nhưng **chưa assert header**; thêm khi test protocol-specific.
- `active=false` bị từ chối, không chỉ tạo principal với danh sách scope rỗng.
- Error từ IdP (4xx/5xx), response malformed, hết hạn, timeout phải **fail closed** và trả lỗi phù hợp, không giả làm token hợp lệ.
- Trạng thái `active=true` có `iss`, `aud`, `client_id`, `sub`, `scope` phải được đối chiếu với policy resource server nếu authorization server trả và ứng dụng yêu cầu. Introspection chỉ cho biết server tin token active; không tự kiểm tra mọi ràng buộc nghiệp vụ.
- Cần đánh giá cache introspection: cache response `active=true` quá lâu có thể làm revocation trễ. Test TTL/invalidation và outage behavior.

**Không khẳng định “introspection thật với IdP” khi chỉ dùng MockRestServiceServer.** Đây là test nội bộ của client/introspector với HTTP giả lập; test staging/môi trường thực cần credentials, endpoint và policy quản lý riêng.

## 8. HTTP integration: gửi Bearer thật qua filter chain

### 8.1. Tránh bỏ qua decoder bằng postprocessor

Để kiểm tra end-to-end trong **ứng dụng Spring Security Servlet** có `SecurityFilterChain`:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth -> oauth.jwt(
            org.springframework.security.config.Customizer.withDefaults()))
        .build();
}
~~~

Cấu hình trên chỉ là snippet; cần class `@Configuration`, bean `JwtDecoder` thật và controller thật. Với Spring Security 6.x, `oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))` bật JWT authentication. Các request thuộc `/api/orders/**` yêu cầu scope, dù JWT được ký đúng.

### 8.2. Test phải gửi chuỗi token, không inject Authentication

~~~java
// Trong class @SpringBootTest + @AutoConfigureMockMvc,
// đã cấu hình JwtDecoder thật và endpoint /api/orders/42.

mvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer " + signedJwt))
   .andExpect(status().isOk());

mvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer " + wrongKeySignedJwt))
   .andExpect(status().isUnauthorized())
   .andExpect(header().string(
       "WWW-Authenticate",
       org.hamcrest.Matchers.startsWith("Bearer")));
~~~

Snippet giả định `signedJwt`/`wrongKeySignedJwt` được tạo bằng helper giống mục 5 và endpoint có quyền đúng. Đừng gắn `.with(jwt())` vào những request này, vì điều đó đưa Authentication giả vào test và có thể khiến kết quả không còn chứng minh decoder path.

- Kiểm tra **401 + `WWW-Authenticate: Bearer`** khi không có Bearer hợp lệ (chi tiết challenge theo RFC 6750); Spring Security có thể dùng mã `invalid_token`.
- Kiểm tra **403** khi JWT signature/claims hợp lệ nhưng `SCOPE_orders.read` thiếu; 403 là **authorization**, không phải lỗi chữ ký.
- Kiểm tra 200 khi token hợp lệ và đủ scope.
- Kiểm tra endpoint không lộ exception, public error contract và cache headers khi cần.
- Kiểm tra profile thật có `JwtDecoder` bean được cấu hình đúng, không bị `@MockBean`, `@SpyBean` hoặc test-profile overriding vô tình thay thế.
- Nếu dùng servlet `oauth2Login()`/ID token, kiểm tra Authorization Code, state/nonce, redirect URI và ID token bằng test IdP riêng; **không** coi test Resource Server JWT access token đã bao phủ OIDC login.

**Ranh giới:** `MockMvc` thực thi servlet filter chain và controller trong mock servlet environment nếu cấu hình đúng, nhưng không phải test socket/TLS/network thực. Test môi trường có reverse proxy, forwarded headers, gateway và OAuth IdP vẫn cần kiểm thử khác.

### 8.3. Opaque token integration

Thay `.oauth2ResourceServer(oauth -> oauth.jwt(...))` bằng `opaqueToken(...)` trong chain theo phiên bản/DSL, cung cấp một `OpaqueTokenIntrospector` thật và HTTP test endpoint. Gửi `Authorization: Bearer opaque-valid` thật, test 200 với `active=true` và scope cần thiết; gửi token `active=false` test 401; `active=true` thiếu scope test 403. Không dùng `.with(opaqueToken())` trong test muốn chứng minh introspection path.

### 8.4. Reactive tương ứng

Với WebFlux, resource server dùng `ReactiveJwtDecoder` hoặc `ReactiveOpaqueTokenIntrospector`. Kiểm thử integration đưa Bearer header vào `WebTestClient` và dùng reactive decoder/introspector thật, không `mutateWith(mockJwt())`/`mockOpaqueToken()`. Spring Security Test hỗ trợ cả hai mock configurers nhưng chúng không thay việc kiểm tra crypto/protocol.

## 9. Java 17 thuần: thấy sự khác biệt giữa chữ ký và dữ liệu tự đặt

Ví dụ này không dùng JWT thư viện: nó dùng **JCA RSA/SHA-256** để minh họa rằng “có một object chứa claims” khác hoàn toàn với “dữ liệu đã được người sở hữu private key tin cậy ký”. Đây chỉ là phép ký thông điệp **độc lập**, không phải JWT/JWS, không có issuer/audience/expiry, không được dùng thay NimbusJwtDecoder trong production.

Tạo `SignatureTrustBoundaryDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public class SignatureTrustBoundaryDemo {

    private static byte[] sign(
            PrivateKey key, byte[] bytes)
            throws GeneralSecurityException {

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(bytes);
        return signer.sign();
    }

    private static boolean verify(
            PublicKey key, byte[] bytes, byte[] signature)
            throws GeneralSecurityException {

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(bytes);
        return verifier.verify(signature);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair trusted = generator.generateKeyPair();
        KeyPair untrusted = generator.generateKeyPair();

        byte[] original = "sub=alice;scope=orders.read"
            .getBytes(StandardCharsets.UTF_8);
        byte[] tampered = "sub=alice;scope=orders.admin"
            .getBytes(StandardCharsets.UTF_8);

        byte[] signature = sign(trusted.getPrivate(), original);

        System.out.println("valid="
            + verify(trusted.getPublic(), original, signature));
        System.out.println("tampered="
            + verify(trusted.getPublic(), tampered, signature));
        System.out.println("wrongKey="
            + verify(untrusted.getPublic(), original, signature));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac SignatureTrustBoundaryDemo.java
java SignatureTrustBoundaryDemo
~~~

Stdout xác định về mặt logic dù RSA key sinh ngẫu nhiên:

~~~text
valid=true
tampered=false
wrongKey=false
~~~

Bài học từ demo: phía server **cần public key tin cậy** và kiểm chứng chính xác chuỗi bytes đã ký. Nếu test chỉ tạo object `Authentication` với `ROLE_ADMIN`, không có bước ký/verify nên nó không thể phát hiện giả mạo hoặc dùng key ngoài trust set.

**Đừng nhầm ví dụ RSA với JWT**: JWT/JWS còn header `alg/kid`, canonical wire format, time-based claims, issuer/audience và policy validation. `NimbusJwtDecoder` là nơi dùng thư viện chuẩn để kiểm tra các yếu tố ấy.

## 10. Ma trận kiểm thử tối thiểu

| Điều cần chứng minh | Token/fixture | Cấp test | Expected |
| --- | --- | --- | --- |
| Controller đọc role `SCOPE_orders.read` | `jwt().authorities(...)` | MockMvc | 200, nếu endpoint đúng |
| Controller từ chối user thiếu scope | `jwt()` không có authority yêu cầu | MockMvc | 403 |
| WebFlux security context đã có JWT | `mockJwt()` | WebTestClient | Business rule/authorization đúng |
| Valid RS256 signature | Private key A ký, decoder public A | Decoder unit | `Jwt` hợp lệ |
| Chữ ký key B | Private key B, decoder public A | Decoder unit | `JwtException` |
| Sai `iss` | JWT ký bằng A, iss của issuer khác | Decoder unit | `JwtException` |
| Sai `aud` | JWT ký bằng A, aud API khác | Decoder unit | `JwtException` |
| Hết hạn | JWT ký đúng, exp cách hiện tại nhiều phút trước | Decoder unit | `JwtException` |
| JWKS rollover | issuer + JWKS mock server, key A/B | Decoder integration | Có/không chấp nhận đúng theo trust/cache policy |
| Opaque active | HTTP introspection active=true | Introspector component | Principal hợp lệ |
| Opaque inactive | HTTP introspection active=false | Introspector component | Bị từ chối |
| IdP 5xx/timeout | HTTP mock timeout/5xx | Introspector component | Fail closed + vận hành nhìn thấy lỗi |
| Bearer thiếu | Không có Authorization header | Security filter integration | 401 + challenge |
| JWT hợp lệ nhưng scope thiếu | Bearer JWT ký thật, policy không đủ | Security filter integration | 403 |
| JWT không hợp lệ | Bearer JWT wrong signature | Security filter integration | 401 |
| Opaque đúng format nhưng inactive | Bearer string qua filter, HTTP introspection false | Security filter integration | 401 |
| Local user bị disable | Token cryptographically valid, policy account check | Domain integration | Không cấp quyền theo chính sách |
| Revoked JWT còn `exp` | Local offline JWT decoder | Architecture test | **Có thể vẫn hợp lệ** nếu không có cơ chế revoke |
| OAuth login callback | Test OIDC OP cùng code/state/nonce/signature | OIDC login e2e | Chỉ chấp nhận flow đã xác thực |

### Lưu ý khi viết assertion

- Không chỉ assert “401” mà bỏ qua `WWW-Authenticate`; HTTP Bearer challenge có semantics riêng.
- Không assert substring exception chứa secret/issuer host rồi đưa ra response body; log vận hành phải redact.
- Không viết test JWT signature sai bằng `Jwt.withTokenValue("fake")...build()`: đó là Jwt object, không phải JWS bytes được ký.
- Không dùng real production refresh token hay client secret trong CI. Sinh key/tokens test trong memory, cô lập test IdP.
- Đừng cho test chỉ có negative: thiếu positive test thật sẽ không biết decoder bị cấu hình “deny all”.
- Đừng chỉ có positive: chữ ký đúng chưa kiểm chứng issuer/audience/time/revocation đúng policy.
- Với virtual time/clock skew, test thời gian phải có biên an toàn; với integration expiry gần sát có thể flaky.
- Cần assert decoder/introspector **đã được gọi thật** khi tuyên bố kiểm thử boundary; dùng spy/counters khi thích hợp, nhưng spy không thay kết quả cryptographic.
- Nếu cần so hiệu năng introspection, tách performance/load test khỏi unit test và kiểm tra timeout/backoff/rate limits.

## 11. Những hiểu nhầm phổ biến và cách sửa

1. **“`jwt()` đã test chữ ký”** → Sai. Nó đưa sẵn Jwt Authentication cho controller/filter authorization.
2. **“Test có `alg=RS256` trong claim thì key thật được check”** → Sai. Chỉ tạo header/claim object không làm cryptographic verification.
3. **“Mock `JwtDecoder.decode` return Jwt là real decoder test”** → Sai. Mockito làm thay kết quả; chỉ dùng để test wiring/error mapping.
4. **“`opaqueToken()` test request introspection HTTP”** → Sai. Nó tạo principal giả không gọi network.
5. **“Một token nhìn giống JWT thì phải verify offline”** → Sai. Authorization server có thể yêu cầu introspection ngay cả khi token có dạng JWT.
6. **“JWT chữ ký đúng thì mọi API phải chấp nhận”** → Sai. `aud`, `iss`, `exp`, `nbf`, type và policy phải được kiểm tra.
7. **“Access token có `scope=admin` do client tự gửi là đáng tin”** → Sai. Không dùng unverified claims trong controller.
8. **“Không cần test 401/403 vì StepVerifier/decoder pass”** → Sai. HTTP filters/challenges là tầng khác.
9. **“Introspection trả `active=false` nhưng vẫn có `sub` nên có thể cho qua”** → Sai. Inactive phải bị từ chối.
10. **“JWKS rotate chắc chắn decoder sẽ refresh ngay”** → Sai. Caching/refresh phụ thuộc implementation, config và timing; test theo policy.
11. **“JWT bị revoke ở IdP lập tức bị decoder offline chặn”** → Sai. Offline signature validation không tự gọi revocation service.
12. **“Bật skip TLS verification trong test staging tiện hơn”** → Không nên. Nó che lỗi trust thật và có thể bị copy sang production.
13. **“E2E nào cũng nên gọi IdP live production”** → Không. Dùng local mock server/test IdP và staging được kiểm soát; tránh quota, PII và tác động tài khoản thật.
14. **“Chỉ test correct signature là đủ”** → Sai. Cần invalid claims, khác audience/issuer, alg allowlist, key mismatch, expiry.
15. **“Có bearer token đã được verify đồng nghĩa user còn ACTIVE”** → Không hẳn. Kiểm tra account status/domain policy tại tầng phù hợp.

## 12. Checklist trước khi coi hệ thống có kiểm thử authentication hoàn chỉnh

- [ ] Đã tách test authorization (mock principal) khỏi test JWT decoder/introspection.
- [ ] Có positive/negative tests thật cho RSA signature, key mismatch, issuer, audience, exp/nbf và algorithm policy.
- [ ] Có test JWKS discovery/rotation/cache/timeout nếu môi trường dùng dynamic keys.
- [ ] Có test introspection client POST/form/auth/`active`/scope và fail-closed network errors.
- [ ] Có HTTP filter chain test đưa **raw Bearer credential** vào header, không inject `JwtAuthenticationToken`.
- [ ] 401/403 và `WWW-Authenticate` được assert theo semantics RFC 6750.
- [ ] Test OIDC `oauth2Login` riêng khi sản phẩm dùng login federation; token access không thay ID token.
- [ ] Không để test config thay `JwtDecoder`/`OpaqueTokenIntrospector` thật bằng mock trong lớp integration mà không chủ ý.
- [ ] Keys/tokens/credentials test là giả, không có production secret/logging bí mật.
- [ ] Test names phản ánh bằng chứng thực tế: authorization/mock, decoder/crypto, HTTP introspection, provider e2e.
- [ ] Lớp monitoring nhìn thấy lỗi invalid_token, issuer mismatch, JWKS timeout nhưng không trả exception detail ra public response.
- [ ] Test chạy ổn định trong CI và staging, tránh phụ thuộc IdP live không kiểm soát cho mọi commit.

**Tổng kết:** dùng `jwt()`, `mockJwt()`, `opaqueToken()` hoặc `mockOpaqueToken()` để test **authorization khi đã có principal** là rất hữu ích, nhưng chúng **không kiểm chứng raw credential**. Muốn biết JWT thật sự được bảo vệ cần gửi token compact ký thật qua `NimbusJwtDecoder`/filter chain với validators rõ; muốn biết opaque token được tin đúng cần chạy `SpringOpaqueTokenIntrospector` với HTTP response và `active` được xác minh. Kết hợp các tầng, thay vì gán quá nhiều ý nghĩa cho một test xanh.

## 13. Tài liệu tham khảo chính thức

- Spring Security 6.5 — Testing OAuth2 trong MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html
- Spring Security 6.5 — Testing OAuth2 trong WebTestClient: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security 6.5 — JWT Resource Server, signature, validators, JWK: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — Opaque Token Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 API — `NimbusJwtDecoder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html
- Spring Security 6.5 API — `SpringOpaqueTokenIntrospector`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html
- RFC 7515 — JSON Web Signature: https://www.rfc-editor.org/rfc/rfc7515.html
- RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662.html
- RFC 6750 — Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725.html
