# Kiểm thử token không hợp lệ mà vẫn đi qua decoder phản ứng thực tế

Trong **Spring Security OAuth 2.0/OIDC Resource Server** sử dụng **WebFlux**, một HTTP request mang Bearer JWT thường được xác thực qua `ReactiveJwtDecoder` trước khi Spring Security tạo `Authentication` và áp các quy tắc phân quyền. Khi viết test, chúng ta thường muốn chứng minh các token **sai chữ ký, sai issuer, sai audience, hết hạn, chưa có hiệu lực hoặc dùng thuật toán không được phép** thật sự bị từ chối.

Một cái bẫy phổ biến là viết test bằng `mockJwt()`, `@WithMockUser` hoặc tự mock `ReactiveJwtDecoder`, rồi kết luận rằng “ứng dụng đã kiểm tra JWT không hợp lệ”. Những công cụ đó hữu ích cho **kiểm thử authorization**, nhưng thông thường chúng **bỏ qua quá trình decode và xác minh JWT thật**. Test vẫn có thể chạy xanh ngay cả khi decoder thực tế cấu hình nhầm issuer, không kiểm tra audience, tin sai khóa hoặc không được nối vào security chain.

Bài học này tập trung vào yêu cầu **kiểm thử token không hợp lệ mà vẫn đi qua decoder phản ứng thực tế** trong chương **JWT trong WebFlux** của module **Spring Security OAuth 2.0 OIDC Resource Server**. Ta sẽ xây một môi trường kiểm thử tự chứa: tạo cặp khóa RSA thử nghiệm, ký JWT thật bằng private key của test, dùng một `NimbusReactiveJwtDecoder` thật với public key tương ứng, gửi token qua HTTP bằng `WebTestClient`, và đối chiếu kết quả với `StepVerifier` khi kiểm thử decoder trực tiếp.

> Tất cả issuer URL, audience, keys và token trong ví dụ là **dữ liệu thử nghiệm**, không được dùng để gọi API sản xuất. Những đoạn code dùng API theo phong cách Spring Boot 3.x / Spring Security 6.x phổ biến; khi chạy với phiên bản cụ thể, cần dùng dependency và các overload được phiên bản đó hỗ trợ.

## 1. Kết quả kiểm thử cần chứng minh là gì?

Giả sử Orders API chỉ chấp nhận JWT access token có:

~~~text
iss = https://issuer.example.test/realms/shop
aud chứa orders-api
JWS alg = RS256 (được allowlist)
chữ ký đúng bằng RSA public key tin cậy của test
exp chưa hết hạn
nbf không nằm trong tương lai ngoài clock skew cho phép
scope chứa orders.read khi gọi GET /api/orders
~~~

Một test thật phải chứng minh ít nhất ba tầng riêng biệt:

| Tầng | Kiểm tra gì? | Ví dụ kết quả |
|---|---|---|
| **JWS/decoder** | Cú pháp JWT, chữ ký, khóa, thuật toán, các claims theo validators | JWT sai chữ ký → xác thực thất bại |
| **Reactive security filter chain** | Bearer token được lấy từ HTTP request và chuyển tới `ReactiveJwtDecoder` đang dùng | HTTP request có JWT invalid → thường 401 |
| **Authorization** | Principal đã xác thực có quyền gọi endpoint không | JWT hợp lệ nhưng thiếu `SCOPE_orders.read` → thường 403 |

Kiểm thử đúng không được đánh đồng:

~~~text
401 vì JWT sai chữ ký     → authentication / decoder
401 vì issuer/audience sai → authentication / JWT validators
403 vì thiếu scope        → authorization
404 vì không có handler   → routing/controller, không chứng minh decoder
503 khi không lấy được JWKS → có thể là lỗi hạ tầng, không chứng minh token invalid
~~~

### 1.1. Luồng thực thi cần được giữ trong bài test

~~~mermaid
sequenceDiagram
    participant T as Test (WebTestClient)
    participant W as WebFlux Server
    participant F as Spring Security WebFilter
    participant D as ReactiveJwtDecoder thật
    participant K as Khóa/validator tin cậy
    T->>W: GET /api/orders + Authorization: Bearer <JWT>
    W->>F: HTTP exchange
    F->>D: decode(token)
    D->>K: JWS verification + iss/aud/exp/nbf
    alt Token sai
        K-->>D: JWT validation error
        D-->>F: Mono.error(...)
        F-->>T: 401 / Bearer challenge
    else Token hợp lệ
        K-->>D: Verified Jwt
        D-->>F: Mono<Jwt>
        F->>F: JwtAuthenticationToken + authorities
        F->>W: HTTP authorization
        W-->>T: 200 nếu đủ scope, hoặc 403 nếu thiếu quyền
    end
~~~

Ở đây “thật” không có nghĩa phải gọi Authorization Server sản xuất hoặc dùng token của người thật. **Decoder thật** là một implementation cryptographic/claims validation thực sự như `NimbusReactiveJwtDecoder`, cấu hình bằng **khóa thử nghiệm** và validators thực; test có thể chạy hoàn toàn trong máy/CI.

## 2. Ba loại test: tránh nhầm mục đích

### 2.1. Test authorization bằng `mockJwt()`

Trong WebFlux, Spring Security Test cung cấp `SecurityMockServerConfigurers.mockJwt()`:

~~~java
webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Test này **mô phỏng** một principal đã được xác thực và gán authorities theo ý muốn. Nó rất hữu ích để kiểm tra `hasAuthority(...)`, quy tắc route hoặc controller, nhưng **không chứng minh** chữ ký JWT được verify, issuer đúng hay `exp` đã được xét. Nếu gán claims sai bằng `mockJwt()`, chúng vẫn có thể được coi là một `Jwt` đã xác thực trong ngữ cảnh test.

### 2.2. Test trực tiếp `ReactiveJwtDecoder` bằng `StepVerifier`

~~~java
StepVerifier.create(realDecoder.decode(token))
    .expectError(JwtException.class)
    .verify();
~~~

Test này thật sự gọi `decode(token)` và kiểm tra error signal trong `Mono`. Nó **không chứng minh** WebFlux security chain đã chọn đúng decoder hoặc Authorization header được xử lý đúng. Đây là tầng kiểm thử decoder/validator.

### 2.3. Test HTTP tích hợp bằng `WebTestClient` và Bearer thật

~~~java
webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers -> headers.setBearerAuth(invalidSignedToken))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Nếu ứng dụng test dùng `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` và bean `ReactiveJwtDecoder` **không bị mock**, HTTP request này đi qua chính pipeline xác thực. **Đây là hướng trọng tâm của bài**.

| Công cụ / phương pháp | Có xác minh chữ ký và JWT claims thật? | Có đi qua HTTP security filter? | Mục tiêu |
|---|---|---|---|
| `mockJwt()` | **Không** | Có phần authorization/security test thích hợp, nhưng authentication được mô phỏng | Test quyền |
| `@WithMockUser` | **Không** | Authentication mô phỏng | Test quyền/controller |
| Mock `ReactiveJwtDecoder` trả `Mono.error(...)` | **Không** | Có thể có | Test cách ứng dụng xử lý lỗi từ decoder |
| Gọi `NimbusReactiveJwtDecoder.decode(token)` với `StepVerifier` | **Có** | Không | Test cryptography + validators |
| `WebTestClient` gửi Bearer JWT ký thật, dùng decoder thật | **Có** | **Có** | Test luồng xác thực end-to-end trong ứng dụng |
| `WebTestClient` gửi token tới test JWKS HTTP server | **Có**, kể cả tải key qua HTTP | **Có** | Test toàn bộ decoder/JWKS/key-selection |

## 3. Thiết kế bộ dữ liệu JWT âm tính

Một bài test có ý nghĩa cần có **positive control**: một JWT hợp lệ được chấp nhận trong cùng cấu hình. Nếu tất cả token đều bị 401 vì sai URL, thiếu decoder hoặc ứng dụng không khởi động đúng, các “negative tests” rất dễ tạo cảm giác an toàn giả.

### 3.1. Các biến thể nên thử

| Token thử nghiệm | Điều cần thay đổi | Tầng phải từ chối |
|---|---|---|
| Hợp lệ | RS256, đúng key/iss/aud/time/scope | Cho qua; 200 nếu endpoint hoạt động |
| Sai chữ ký | Ký bằng **private key khác** | JWS verification → 401 |
| Payload bị sửa sau ký | Thay phần payload mà giữ nguyên signature | JWS verification → 401 |
| Sai issuer | Ký đúng key nhưng `iss` khác issuer tin cậy | Issuer validator → 401 |
| Sai audience | Ký đúng key nhưng `aud` không chứa `orders-api` | Audience validator → 401 |
| Đã hết hạn | `exp` trong quá khứ đủ xa để vượt clock skew | Timestamp validator → 401 |
| Chưa có hiệu lực | `nbf` ở tương lai đủ xa | Timestamp validator → 401 |
| Thuật toán không được phép | `alg=none` hoặc HS256 khi chỉ cho RS256 | JOSE/algorithm policy → 401 |
| Token hỏng cấu trúc | Không parse được JWT | Decoder parsing → 401 |
| Token hợp lệ nhưng thiếu scope | JWT ký đúng, claim `scope` không có `orders.read` | Authorization → 403 |
| Không có Bearer token | Không gửi `Authorization` | Authentication entry point → 401 |

**Không nên nhét tất cả lỗi vào một token duy nhất.** Nếu một JWT đồng thời sai chữ ký, sai issuer và hết hạn, decoder có thể dừng ngay ở bước chữ ký; test 401 không chứng minh validator issuer/expiry đã chạy. Mỗi trường hợp nên **chỉ thay đổi một điều kiện quan trọng**, trong khi các điều kiện khác vẫn hợp lệ.

### 3.2. Không cần private key sản xuất

Trong test, tạo cặp RSA 2048-bit hoặc mạnh hơn theo chính sách:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(2048);
KeyPair testKeys = generator.generateKeyPair();
~~~

- **Private key**: chỉ dùng để ký JWT thử nghiệm, ở test runtime.
- **Public key**: đưa cho `NimbusReactiveJwtDecoder` làm khóa tin cậy.
- **Wrong key**: dùng một cặp RSA khác để tạo JWT sai chữ ký đối với decoder.
- **Không** copy private key Authorization Server thật vào test hay repository.

### 3.3. Thời gian và clock skew

Thư viện JWT thường cho phép một khoảng lệch đồng hồ nhất định; vì vậy:

~~~text
exp = now - 1 giây
~~~

chưa chắc là negative test ổn định. Với test mặc định, nên dùng `exp` ở quá khứ xa hơn clock skew (ví dụ vài phút hoặc một giờ), và `nbf` ở tương lai đủ xa. Nếu test chính xác ranh giới skew, phải kiểm soát `Clock`/validator theo API của phiên bản đang dùng.

Tránh ghi một timestamp cố định như năm 2026 rồi mong test “token còn hạn” vẫn chạy đúng nhiều năm sau. Với positive control, tạo `iat`, `nbf`, `exp` dựa vào thời điểm thực thi test hoặc một `Clock` được inject vào toàn bộ policy.

## 4. Cấu hình ứng dụng thử nghiệm: WebFlux + Resource Server thật

Trong một dự án Spring Boot WebFlux, những dependency cơ bản:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Ví dụ Gradle này dành cho một ứng dụng **WebFlux**, không trộn `spring-boot-starter-web` Servlet để làm thay đổi web application type ngoài dự kiến. Khi quản lý dependencies không thông qua Boot starter, cần đảm bảo có module JWT/JOSE của Spring Security và Nimbus JOSE JWT theo phiên bản tương thích.

### 4.1. Security chain chỉ chấp nhận đúng scope

Một cấu hình WebFlux:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Đây là cấu hình minh họa cơ sở. Khi có nhiều `SecurityWebFilterChain`, phải bảo đảm request thực sự chọn chain có `oauth2ResourceServer(...jwt(...))`; một chain rộng đứng trước có thể che mất chain API. Phần test tích hợp sau sẽ dùng một test application tối giản để kiểm soát chuyện này.

### 4.2. Cấu hình decoder thật dùng public key test

~~~java
NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
    .withPublicKey((RSAPublicKey) testKeyPair.getPublic())
    .signatureAlgorithm(SignatureAlgorithm.RS256)
    .build();
~~~

Implementation này thực sự xác minh **RSA JWS signature**, không chỉ parse claims. Để kiểm thử issuer/audience/time, cần thêm validators:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token", "Audience is not accepted", null));

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(
            "https://issuer.example.test/realms/shop"),
        audienceValidator
    )
);
~~~

Điểm quan trọng: `setJwtValidator(...)` **thay thế** validator được cấu hình trên decoder. Ghép `JwtValidators.createDefaultWithIssuer(issuer)` giúp giữ bộ validator mặc định gồm các ràng buộc issuer/thời gian phù hợp phiên bản, rồi mới thêm audience. Nếu hợp đồng yêu cầu `exp` phải tồn tại, `typ=at+jwt` hoặc claim riêng, cần thêm validator tương ứng; không giả định mọi điều kiện profile đều có sẵn.

### 4.3. Vì sao dùng public key thay vì JWKS ngay trong test đầu tiên?

`NimbusReactiveJwtDecoder.withPublicKey(...)` vẫn là **decoder thật**. Nó kiểm tra chữ ký bằng public key nhưng không cần HTTP JWKS server, nên test được cô lập khỏi mạng và có thể kiểm soát dễ:

~~~text
Private test RSA key → ký token thật
Public test RSA key  → NimbusReactiveJwtDecoder verify thật
WebTestClient        → request HTTP đi qua security filters
~~~

Đây là cấp kiểm thử phù hợp để chứng minh **token invalid bị từ chối bởi decoder**. Tuy nhiên, nó **không kiểm tra** tải JWKS, chọn `kid`, làm mới cache hoặc key rotation. Những yêu cầu đó cần một lớp integration test với test JWKS endpoint, trình bày ở phần sau.

## 5. Ví dụ đầy đủ: `WebTestClient` gửi JWT ký RSA thật

Dưới đây là một file test Java **độc lập về cấu hình**. Nó khai báo:

- Một Spring Boot WebFlux application nhỏ chỉ dùng trong test.
- `SecurityWebFilterChain` thật với `oauth2ResourceServer().jwt()`.
- `NimbusReactiveJwtDecoder` thật, tin một RSA public key được tạo trong test.
- JWT được ký bằng Nimbus JOSE/JWT, với **private key tương ứng**.
- Controller GET `/api/orders` trả `ok` để làm positive control.
- Những test HTTP dùng Bearer header thật, **không gọi `mockJwt()`**.

### 5.1. File `ReactiveJwtHttpIntegrationTest.java`

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.List;
import java.nio.charset.StandardCharsets;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.PlainJWT;
import com.nimbusds.jwt.SignedJWT;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootTest(
    classes = ReactiveJwtHttpIntegrationTest.TestApp.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ReactiveJwtHttpIntegrationTest {

    static final String ISSUER =
        "https://issuer.example.test/realms/shop";
    static final String AUDIENCE = "orders-api";

    @Autowired
    WebTestClient client;

    @Autowired
    KeyPair signingKey;

    // App riêng cho test: không dùng Authorization Server production.
    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({TestSecurity.class, OrdersEndpoint.class})
    static class TestApp {}

    @Configuration(proxyBeanMethods = false)
    static class TestSecurity {

        @Bean
        KeyPair signingKey() throws GeneralSecurityException {
            KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        }

        @Bean
        ReactiveJwtDecoder reactiveJwtDecoder(KeyPair signingKey) {
            NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                    .withPublicKey((RSAPublicKey) signingKey.getPublic())
                    .signatureAlgorithm(SignatureAlgorithm.RS256)
                    .build();

            OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Audience is not accepted",
                            null
                        )
                    );

            decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(ISSUER),
                    audience
                )
            );

            return decoder;
        }

        @Bean
        SecurityWebFilterChain securityWebFilterChain(
                ServerHttpSecurity http) {
            return http
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers(HttpMethod.GET, "/api/orders")
                        .hasAuthority("SCOPE_orders.read")
                    .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(withDefaults()))
                .build();
        }
    }

    @RestController
    static class OrdersEndpoint {
        @GetMapping("/api/orders")
        Mono<String> orders() {
            return Mono.just("ok");
        }
    }

    // Mỗi test có claims mới dựa trên thời gian lúc chạy.
    private JWTClaimsSet.Builder validClaims() {
        Instant now = Instant.now();
        return new JWTClaimsSet.Builder()
            .issuer(ISSUER)
            .subject("test-user")
            .audience(List.of(AUDIENCE))
            .issueTime(Date.from(now.minusSeconds(30)))
            .notBeforeTime(Date.from(now.minusSeconds(30)))
            .expirationTime(Date.from(now.plusSeconds(300)))
            .claim("scope", "orders.read");
    }

    // JWS thật: dùng private key thử nghiệm để tạo chữ ký RS256.
    private String sign(
            JWTClaimsSet claims,
            RSAPrivateKey privateKey) throws JOSEException {

        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
            .type(JOSEObjectType.JWT)
            .keyID("test-rsa-key")
            .build();

        SignedJWT signed = new SignedJWT(header, claims);
        signed.sign(new RSASSASigner(privateKey));
        return signed.serialize();
    }

    private String validToken() throws JOSEException {
        return sign(
            validClaims().build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );
    }

    private void expectUnauthorized(String bearerToken) {
        client.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(bearerToken))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validSignedJwtWithReadScopeIsAccepted() throws Exception {
        client.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(validToken()))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void jwtSignedByDifferentKeyIsRejected() throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair untrusted = generator.generateKeyPair();

        String token = sign(
            validClaims().build(),
            (RSAPrivateKey) untrusted.getPrivate()
        );

        expectUnauthorized(token);
    }

    @Test
    void tamperingPayloadAfterSigningIsRejected() throws Exception {
        String original = validToken();
        String[] parts = original.split("\\.", -1);

        // Đổi payload nhưng KHÔNG ký lại: signature cũ không hợp lệ.
        String changedPayload = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(
                "{\"sub\":\"changed-after-signing\"}"
                    .getBytes(StandardCharsets.UTF_8)
            );

        String tampered =
            parts[0] + "." + changedPayload + "." + parts[2];
        expectUnauthorized(tampered);
    }

    @Test
    void wrongIssuerIsRejectedEvenWithValidSignature()
            throws Exception {
        String token = sign(
            validClaims()
                .issuer("https://other-issuer.example.test")
                .build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );

        expectUnauthorized(token);
    }

    @Test
    void wrongAudienceIsRejectedEvenWithValidSignature()
            throws Exception {
        String token = sign(
            validClaims()
                .audience(List.of("billing-api"))
                .build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );

        expectUnauthorized(token);
    }

    @Test
    void expiredJwtIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(
            validClaims()
                .issueTime(Date.from(now.minusSeconds(7200)))
                .notBeforeTime(Date.from(now.minusSeconds(7200)))
                .expirationTime(Date.from(now.minusSeconds(3600)))
                .build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );

        expectUnauthorized(token);
    }

    @Test
    void notYetValidJwtIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(
            validClaims()
                .notBeforeTime(Date.from(now.plusSeconds(3600)))
                .build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );

        expectUnauthorized(token);
    }

    @Test
    void unsignedPlainJwtIsRejected() {
        String token = new PlainJWT(validClaims().build())
            .serialize();
        expectUnauthorized(token);
    }

    @Test
    void malformedJwtIsRejected() {
        expectUnauthorized("this-is-not-a-jwt");
    }

    @Test
    void validJwtWithWrongScopeIsForbidden() throws Exception {
        String token = sign(
            validClaims()
                .claim("scope", "orders.create")
                .build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );

        client.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void missingBearerTokenIsUnauthorized() {
        client.get()
            .uri("/api/orders")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

### 5.2. Vì sao đây là một integration test của decoder phản ứng thật?

Trong code trên, request `WebTestClient` chạy qua cổng HTTP test server và WebFlux security filter chain. Bean `ReactiveJwtDecoder` được tạo bằng `NimbusReactiveJwtDecoder.withPublicKey(...)` **không phải Mockito mock**, và được `oauth2ResourceServer().jwt()` sử dụng.

Các JWT được ký bằng `RSASSASigner` trên private key thử nghiệm. Decoder dùng public key cùng cặp, tự kiểm tra signature và validators. Nhờ đó:

- Token hợp lệ cho kết quả 200: **positive control** xác nhận cấu hình hoạt động.
- Chữ ký từ khóa khác cho 401: chứng minh Resource Server **không chấp nhận mọi JWT có cấu trúc hợp lệ**.
- Token cùng khóa nhưng sai issuer/audience/time cho 401: kiểm tra **claims validators**.
- Token hợp lệ nhưng scope sai cho 403: phân biệt **authentication** và **authorization**.
- Token không có Bearer header cho 401: kiểm tra authentication entry point.

`RANDOM_PORT` khiến bài test chạy với HTTP server thật trên cổng ngẫu nhiên; nó giúp đi qua các WebFlux filters như request của client, thay vì chỉ gọi một method Java. Trường hợp cần test nhanh hơn có thể dùng `WebTestClient.bindToApplicationContext(...)` với Spring Security mock server configurers thích hợp, nhưng vẫn phải gửi **Bearer token qua header** và đảm bảo decoder thật được wiring. Đừng vô tình gọi `mutateWith(mockJwt())` trong test dành cho decoder.

### 5.3. Sự khác biệt với hệ thống production

Bài test cố tình không gọi tới issuer thật, discovery metadata hay JWKS HTTP endpoint. Nó chỉ thay **nguồn khóa** thành RSA public key thử nghiệm; logic cryptography và claim validation vẫn là thật.

Nếu production dùng `issuer-uri` + JWKS, cần **bổ sung** test riêng cho:

- Lấy JWK Set từ URL đúng và từ nguồn tin cậy.
- Chọn public key theo `kid` và thuật toán được allowlist.
- Public key rotation và JWKS cache refresh.
- JWKS endpoint lỗi/timeout hoặc không có key phù hợp.
- Các điều kiện issuer/audience/token profile thật của ứng dụng.

Không nên đánh đồng “đã chạy `NimbusReactiveJwtDecoder` với public key” với “đã kiểm tra toàn bộ discovery và vòng đời JWKS”. Hai loại test bổ sung cho nhau.

## 6. Kiểm thử `ReactiveJwtDecoder.decode(...)` trực tiếp bằng `StepVerifier`

Khi HTTP test báo 401, lỗi có thể phát sinh tại Bearer token resolver, decoder, authentication entry point hoặc custom WebFilter. Để cô lập việc kiểm tra **claims và chữ ký**, có thể gọi decoder thật đang được ứng dụng sử dụng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

// Các thành viên bổ sung vào class test ở phần 5.
@Autowired
ReactiveJwtDecoder actualDecoder;

@Test
void decoderAcceptsValidJwt() throws Exception {
    String token = validToken();

    StepVerifier.create(actualDecoder.decode(token))
        .assertNext(jwt -> {
            assertThat(jwt.getSubject()).isEqualTo("test-user");
            assertThat(jwt.getIssuer().toString()).isEqualTo(ISSUER);
            assertThat(jwt.getAudience()).contains(AUDIENCE);
        })
        .verifyComplete();
}

@Test
void decoderRejectsSignedJwtWithWrongAudience() throws Exception {
    String token = sign(
        validClaims().audience(List.of("billing-api")).build(),
        (RSAPrivateKey) signingKey.getPrivate()
    );

    StepVerifier.create(actualDecoder.decode(token))
        .expectError(JwtException.class)
        .verify();
}
~~~

Các method trên sử dụng `validToken()`, `validClaims()`, `sign(...)` và `signingKey` từ class test phần 5. Đặt fields và methods vào đúng phạm vi class; đây không phải một class độc lập để copy nguyên vào file mới.

### 6.1. Vì sao `StepVerifier` phù hợp?

`ReactiveJwtDecoder.decode(String)` trả `Mono<Jwt>`. JWT hợp lệ phát `onNext(Jwt)` rồi `onComplete`, còn JWT không hợp lệ phát `onError(...)`. Kiểm thử reactive phải thực sự subscribe:

~~~text
Valid:
  Mono<Jwt> → onNext(verified JWT) → onComplete

Invalid:
  Mono<Jwt> → onError(JwtException subtype)
~~~

Một phản ví dụ:

~~~java
// PHẢN VÍ DỤ: Mono không null KHÔNG chứng minh token hợp lệ.
assertNotNull(decoder.decode(invalidToken));
~~~

Đối tượng `Mono` có thể khác null dù khi subscribe nó phát error. Vì vậy test phải kiểm tra **reactive signal** bằng `StepVerifier` hoặc một subscriber tương đương.

### 6.2. Tránh phụ thuộc message nội bộ

JWT sai chữ ký có thể được Spring Security/Nimbus gói thành exception subtype và message khác nhau theo version. Khi kiểm tra policy, thường đủ để assert `JwtException` hoặc loại exception ổn định do ứng dụng chủ động chuẩn hóa. Không in raw token vào failure message/log của CI.

### 6.3. Decoder test và HTTP integration test bổ sung nhau

Nếu `StepVerifier` từ chối audience sai nhưng HTTP request vẫn trả 200, có thể ứng dụng **không dùng decoder đó** trong chain hoặc có security test override. Nếu HTTP trả 401 nhưng `StepVerifier` chấp nhận token, lỗi có thể xuất phát tại Bearer resolver, filter chain hoặc một cấu hình authorization khác. Vì vậy cần cả **decoder test trực tiếp** và **HTTP test đi qua security filters**.

## 7. Xác nhận HTTP request thật sự gọi decoder

Nếu cần chứng minh decoder được invoke, có thể bọc decoder thực bằng một decorator chỉ tăng bộ đếm khi subscription, rồi **chuyển nguyên token tới decoder thật**.

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.core.publisher.Mono;

final class CountingReactiveJwtDecoder implements ReactiveJwtDecoder {
    private final ReactiveJwtDecoder delegate;
    private final AtomicInteger subscriptions = new AtomicInteger();

    CountingReactiveJwtDecoder(ReactiveJwtDecoder delegate) {
        this.delegate = Objects.requireNonNull(delegate);
    }

    @Override
    public Mono<Jwt> decode(String token) {
        return Mono.defer(() -> {
            subscriptions.incrementAndGet();
            return delegate.decode(token);
        });
    }

    int calls() {
        return subscriptions.get();
    }
}
~~~

Trong test configuration, **thay** bean decoder hiện tại bằng phương án decorator (không tạo hai bean cạnh tranh):

~~~java
@Bean
CountingReactiveJwtDecoder reactiveJwtDecoder(KeyPair signingKey) {
    NimbusReactiveJwtDecoder real = NimbusReactiveJwtDecoder
        .withPublicKey((RSAPublicKey) signingKey.getPublic())
        .signatureAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains(AUDIENCE)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    real.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audienceValidator
        )
    );

    return new CountingReactiveJwtDecoder(real);
}
~~~

Ví dụ một HTTP test có thể đọc `calls()` trước/sau request và xác nhận tăng thêm một lần. Cần đảm bảo test **không chạy song song** nếu dùng counter chung; tránh assert số đếm chính xác khi nhiều request khác có thể diễn ra đồng thời. Với chính sách redirect/filter phức tạp, cần biết số lần decoder được kỳ vọng gọi.

Điểm cốt lõi: đây là **delegating wrapper**, không phải mock tạo `Mono.just(fakeJwt)` hay `Mono.error(...)` theo ý test. Chữ ký và validators vẫn được kiểm tra bởi `NimbusReactiveJwtDecoder` thật.

Không nhất thiết gắn counter vào mọi test: positive control 200, negative signature 401 và các negative claims 401 đã là bằng chứng mạnh. Decorator hữu ích khi điều tra lỗi wiring, nhiều chain/bean decoder hoặc nguy cơ test vô tình dùng mock.

## 8. Kiểm tra thuật toán ký không được phép

Một JWT có JOSE header tự khai báo `alg=HS256`, `alg=RS256`, `alg=none` hoặc thuật toán khác. Resource Server **không được tin một thuật toán tùy ý chỉ vì header yêu cầu nó**.

Decoder trong ví dụ phần 5 allowlist:

~~~java
.signatureAlgorithm(SignatureAlgorithm.RS256)
~~~

Như vậy, token không ký hoặc ký bằng HS256 phải bị từ chối ngay cả khi issuer, audience, scope và thời gian trông đúng.

### 8.1. Token unsigned / `alg=none`

~~~java
String unsigned = new PlainJWT(validClaims().build()).serialize();
expectUnauthorized(unsigned);
~~~

`PlainJWT` không mang chữ ký JWS được yêu cầu. Đây là negative test kiểm tra application không chấp nhận một token chỉ có payload.

### 8.2. Token HS256 thử nghiệm

Một method bổ sung vào class integration test ở phần 5:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.MACSigner;
import com.nimbusds.jwt.SignedJWT;

@Test
void hs256TokenIsRejectedByRs256OnlyDecoder() throws Exception {
    byte[] testOnlyHmacKey =
        "01234567890123456789012345678901"
            .getBytes(StandardCharsets.UTF_8);

    SignedJWT jwt = new SignedJWT(
        new JWSHeader(JWSAlgorithm.HS256),
        validClaims().build()
    );
    jwt.sign(new MACSigner(testOnlyHmacKey));

    expectUnauthorized(jwt.serialize());
}
~~~

Khóa HMAC chỉ là chuỗi giả trong test, **không phải secret để dùng ở production**. JWT HS256 không được phép trong cấu hình chỉ tin RS256. Nếu Authorization Server thực sự sử dụng thêm algorithm, phải có hợp đồng key/algorithm trust riêng và test đầy đủ chứ không bật mọi thuật toán theo nội dung header.

### 8.3. Không “đoán” thuật toán theo token chưa tin cậy

Một cấu hình chống algorithm confusion cần đạt:

~~~text
Expected: RS256 + trusted RSA public key

Incoming RS256, đúng signer → accept nếu claims đúng
Incoming RS256, sai signer  → reject
Incoming HS256              → reject
Incoming alg=none           → reject
Incoming unsupported alg    → reject
~~~

Không sửa test bằng cách bỏ signature verification hoặc cho decoder tự động chấp nhận mọi `alg`. Đây là kiểm tra **trust policy**, không phải chỉ kiểm tra một parser có đọc được header không.

## 9. Sai issuer, sai audience và token profile

### 9.1. Sai issuer dù chữ ký đúng

Test `wrongIssuerIsRejectedEvenWithValidSignature()` dùng private key **được tin cậy** để ký một JWT có `iss` khác:

~~~text
signature = valid
iss       = https://other-issuer.example.test
aud       = orders-api
time      = valid
scope     = orders.read
~~~

Nếu token này được chấp nhận, issuer validator có thể chưa được gắn hoặc HTTP request đang dùng decoder khác. Một token vừa sai signature vừa sai issuer **không chứng minh** issuer validation đã chạy vì decoder có thể loại chữ ký trước.

### 9.2. Sai audience dù chữ ký và issuer đúng

~~~text
signature = valid
iss       = trusted issuer
aud       = billing-api
time      = valid
scope     = orders.read
~~~

Orders API phải từ chối JWT dành cho Billing API. **Audience** xác định resource nào được phép nhận token; **scope** xác định quyền thao tác. Chuỗi `orders.read` không bù cho audience sai.

| Giá trị `aud` | Với Orders API | Quyết định audience |
|---|---|---|
| `["orders-api"]` | Chứa resource ID đúng | Hợp lệ về audience |
| `["billing-api"]` | Không có resource ID đúng | Từ chối |
| `["billing-api","orders-api"]` | Nếu issuer/profile cho phép token đa audience | Có thể hợp lệ về audience |
| Không có `aud` | Profile yêu cầu audience | Từ chối |
| `["orders-api-v2"]` | Chỉ hợp lệ khi allowlist có giá trị này | Không tự coi là `orders-api` |

Validator `jwt.getAudience().contains(AUDIENCE)` là một **chính sách chứa ít nhất một audience**. Nếu token profile yêu cầu **chính xác một audience** hoặc cấm multi-audience, cần viết validator chặt hơn và bổ sung negative tests tương ứng.

### 9.3. Không dùng OIDC ID token thay access token

Một OIDC ID token có thể là JWT ký hợp lệ bởi cùng issuer nhưng được cấp cho **OIDC client**, không phải cho Resource Server API. Nếu `aud` của ID token trùng client ID thay vì resource ID, Orders API phải từ chối. Trong các hệ thống áp JWT access token profile như RFC 9068, có thể cần kiểm tra `typ=at+jwt` và những claims profile khác.

Chỉ có `JwtDecoder` kiểm tra chữ ký + issuer chưa đảm bảo mọi token JWT cùng issuer đều có mục đích đúng. Khi thêm token type/profile validation, cần có test ký đúng nhưng **sai loại token**.

### 9.4. Thiếu `exp` không nhất thiết tự bị từ chối trong mọi profile

Một số timestamp validators kiểm tra giá trị `exp`/`nbf` **khi claim có mặt**, trong khi hợp đồng có thể còn yêu cầu `exp` bắt buộc. Nếu Orders API phải từ chối token thiếu `exp`, hãy thêm validator:

~~~java
OAuth2TokenValidator<Jwt> expRequired = jwt ->
    jwt.getExpiresAt() != null
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Required exp claim is missing",
                null
            )
        );

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator,
        expRequired
    )
);
~~~

Đây là **cấu hình mở rộng** của decoder, với `audienceValidator` đã có; không khai báo hai lần `setJwtValidator` mà quên rằng lần sau thay thế lần trước. Khi đã có rule này, test token ký đúng nhưng thiếu `exp` mới có cơ sở mong đợi 401. Nếu không có rule, không mặc định tuyên bố mọi Spring Security version đều buộc `exp` phải tồn tại.

### 9.5. Claim `iat` nằm trong tương lai

`iat` cho biết thời điểm phát hành, nhưng việc nó nằm trong tương lai có bị từ chối ngay không phụ thuộc bộ validator và token profile. Nếu API yêu cầu giới hạn tuổi đời, phải thiết kế validator cụ thể cho `iat` cùng clock skew, rồi test một JWT **được ký hợp lệ** nhưng có `iat` sai chính sách.

Không suy từ kết quả test `nbf` rằng ứng dụng chắc chắn có cùng rule cho `iat`: đây là hai claims có ý nghĩa khác nhau.

## 10. Kiểm thử JWKS qua HTTP: một tầng khác với public key cố định

Ở production, Resource Server thường dùng `issuer-uri` và `jwk-set-uri`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/shop
          jwk-set-uri: https://issuer.example.test/realms/shop/jwks
~~~

Khi đó decoder có thể **tải, cache, chọn JWK theo `kid`/`alg`** và xử lý key rotation. Một test `withPublicKey(...)` không kiểm tra mạng/JWKS này. Để kiểm tra mà không phụ thuộc IdP production, ta có thể tạo một **HTTP test server trên loopback**, trả JWKS chỉ chứa public key của test.

### 10.1. Tạo JWK từ RSA public key

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import java.security.KeyPair;
import java.security.interfaces.RSAPublicKey;

RSAKey publicJwk = new RSAKey.Builder(
        (RSAPublicKey) testKeyPair.getPublic())
    .keyID("test-rsa-key")
    .algorithm(JWSAlgorithm.RS256)
    .build();

String jwksJson = new JWKSet(publicJwk).toString();
~~~

Nếu xây `RSAKey` từ public key như trên, JWKS không cần chứa private signing key. Khi ký JWT, JOSE header chọn `keyID("test-rsa-key")` tương ứng với JWK đã công bố. **Không bao giờ xuất private key vào JWKS, test logs hoặc artifact chia sẻ**.

### 10.2. Helper test server bằng JDK `HttpServer`

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.interfaces.RSAPublicKey;
import java.util.concurrent.atomic.AtomicReference;

final class LocalJwksServer implements AutoCloseable {
    private final HttpServer server;
    private final AtomicReference<String> jwksBody;

    LocalJwksServer(KeyPair trustedKeys) throws IOException {
        RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) trustedKeys.getPublic())
            .keyID("test-rsa-key")
            .algorithm(JWSAlgorithm.RS256)
            .build();

        jwksBody = new AtomicReference<>(new JWKSet(jwk).toString());

        server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/jwks", exchange -> {
            byte[] bytes = jwksBody.get()
                .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                .set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
    }

    String jwksUri() {
        return "http://127.0.0.1:"
            + server.getAddress().getPort() + "/jwks";
    }

    void publishJwks(String json) {
        jwksBody.set(json);
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
~~~

Đây là **test-only server**, dùng `http://127.0.0.1` để chạy local mà không cần cấp chứng chỉ. Production JWKS phải dùng URL được tin cậy và TLS thích hợp. Nếu dự án dùng Java modules (`module-info.java`), việc sử dụng `com.sun.net.httpserver` cần cấu hình module `jdk.httpserver` phù hợp.

### 10.3. Decoder thật trỏ vào test JWKS endpoint

~~~java
try (LocalJwksServer jwks = new LocalJwksServer(testKeyPair)) {
    NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
        .withJwkSetUri(jwks.jwksUri())
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audienceValidator
        )
    );

    StepVerifier.create(decoder.decode(validSignedToken))
        .expectNextCount(1)
        .verifyComplete();
}
~~~

Đoạn này là **mẫu ghép bên trong test method**: `testKeyPair`, `validSignedToken`, `audienceValidator` và `ISSUER` phải được tạo như ở các phần trước. Nó kiểm tra decoder/JWKS thật qua HTTP test server. Muốn kiểm tra **HTTP SecurityWebFilterChain**, phải cung cấp decoder dùng JWKS này làm bean mà test application thực sự sử dụng, rồi gửi token bằng `WebTestClient`.

### 10.4. Các trường hợp JWKS nên bao phủ

| JWKS test server | JWT | Kỳ vọng |
|---|---|---|
| Có đúng public key và `kid` | JWT ký bằng private key tương ứng | Chấp nhận khi claims hợp lệ |
| Không có key tương ứng | JWT ký bằng private key khác | Không xác thực |
| Cùng `kid` nhưng public key sai | JWT có chữ ký không khớp | Không xác thực |
| Chỉ công bố key không hỗ trợ algorithm | JWT dùng algorithm khác allowlist | Không xác thực |
| Trả JSON không phải JWKS hợp lệ | JWT cần key | Decoder không thể xác minh |
| Trả 503 hoặc timeout | JWT cần lấy key chưa cache | Không tạo principal |
| Cùng lúc công bố khóa cũ và mới | JWT được ký bằng từng khóa | Kiểm tra rollover window |
| Gỡ khóa cũ trước khi token cũ hết hạn | JWT cũ | Có thể bị từ chối, tùy cache; phát hiện rủi ro vận hành |

JWKS caching và thời điểm làm mới `kid` phụ thuộc decoder, cache configuration và phiên bản Nimbus/Spring Security. Đừng giả định thay response JWKS là mọi decoder đã refresh ngay. Với test muốn kiểm chứng cache rỗng, hãy dùng **decoder instance mới** hoặc reset cache bằng API chính thức, không dựa vào thứ tự các test khác.

### 10.5. `kid` không phải bằng chứng trust

`kid` chỉ là key identifier có thể do người gửi token đặt vào header. Decoder phải chọn khóa từ **JWK Set URL đã được cấu hình tin cậy**, không lấy URL từ `jku` hoặc `x5u` do token chưa xác minh tự chỉ định. Kiểm thử `withPublicKey(...)` không chứng minh lựa chọn `kid` đúng; khi cần kiểm tra key selection, dùng JWKS-aware decoder như trong phần này.

## 11. Lỗi tải JWKS khác với token sai chữ ký

JWT sai chữ ký là trường hợp **có đủ key để kiểm tra và xác định chữ ký không hợp lệ**. JWKS trả 503 hoặc không truy cập được có thể là trường hợp **chưa có key đủ tin cậy để kết luận**.

~~~text
Case A: Invalid JWS signature
    → Decoder kiểm tra bằng trusted public key
    → Không tạo Authentication
    → Thường HTTP 401

Case B: JWKS endpoint unavailable, không có cached key
    → Decoder không đủ key tin cậy
    → Không tạo Authentication
    → HTTP status tùy exception mapping (có thể 401/5xx)
~~~

| Trường hợp | Ý nghĩa | Điều cần điều tra |
|---|---|---|
| Bad signature | Token không đạt xác minh mật mã | Key ký sai, token bị sửa, token giả |
| Unknown `kid` | Không tìm được key phù hợp | Rotation, cache refresh, token profile |
| Wrong `iss` | Issuer validator từ chối | Trust configuration, token sai issuer |
| Wrong `aud` | Audience validator từ chối | Client lấy token sai resource |
| Expired JWT | Timestamp validator từ chối | TTL, client refresh |
| JWKS 503/timeout | Nguồn key tạm không khả dụng | Availability, network, timeout/cache |

Điểm bất biến: **không tự chấp nhận token chưa được verify chỉ vì key service gặp lỗi**.

~~~java
// PHẢN VÍ DỤ: không cho qua JWT khi decoder lỗi.
return realDecoder.decode(token)
    .onErrorResume(error ->
        Mono.just(trustClaimsWithoutVerification(token)));
~~~

Nếu hệ thống cần xác minh JWT khi JWKS endpoint tạm lỗi, nó phải có **trusted key cache còn hợp lệ theo chính sách** hoặc cơ chế xác minh dự phòng được thiết kế trước. Không lấy claims từ token chưa xác minh làm principal.

### 11.1. JWKS cache và vòng đời khóa

~~~text
T0: JWKS = [oldKey]
T1: JWKS = [oldKey, newKey]
T2: issuer bắt đầu ký token bằng newKey
T3: token cũ cuối cùng hết hạn (+ skew)
T4: issuer gỡ oldKey khỏi JWKS
~~~

Nếu gỡ oldKey quá sớm, những JWT cũ vẫn chưa hết hạn có thể bị từ chối. JWKS cache khiến việc nhìn thấy key cũ/mới phụ thuộc TTL và refresh policy. Test key rollover cần xét **khoảng chồng lấn**, không chỉ thay JSON rồi mong mọi decoder đồng loạt đổi key.

### 11.2. Tách từng loại test để chẩn đoán tốt

1. **Public-key decoder test**: cryptographic signature + claims validators.
2. **JWKS decoder test**: HTTP key retrieval, `kid` và cache.
3. **Issuer discovery test**: metadata issuer và JWK Set URI tin cậy.
4. **WebFlux HTTP security test**: chọn chain, xử lý Bearer, tạo Authentication và scope.

Khi một nhóm lỗi, dễ xác định mắt xích liên quan thay vì chỉ thấy một HTTP 401 khó hiểu.

## 12. Chọn đúng kiểu Spring Security Test

### 12.1. `@SpringBootTest(webEnvironment = RANDOM_PORT)`

Ví dụ phần 5 khởi động WebFlux application với web server thật trên random port, dùng `WebTestClient` để gọi HTTP qua filters. Cách này gần với runtime hơn nhưng có thêm chi phí startup/auto-configuration.

### 12.2. `@WebFluxTest`

`@WebFluxTest` thường chỉ nạp web layer theo test slice. Nó hữu ích cho controller/serialization, nhưng **không nên giả định decoder và security chain production luôn được nạp**. Muốn test JWT validation cần import security config và cung cấp **real ReactiveJwtDecoder + key/validators**.

### 12.3. `WebTestClient.bindToController(...)`

~~~java
WebTestClient.bindToController(new OrdersController()).build();
~~~

Kiểu test này có thể chỉ gọi controller mà **không có Spring Security WebFilter chain**. Thấy 200 không chứng minh JWT đã được xác minh. Có thể bind tới application context và áp security test configurers thích hợp, hoặc dùng `@SpringBootTest` như ở phần 5.

### 12.4. Vì sao `mutateWith(mockJwt())` không phải test decoder?

~~~java
// PHẢN VÍ DỤ nếu mục tiêu là test issuer verification.
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("iss", "https://wrong-issuer.example.test")))
    .get()
    .uri("/api/orders")
    .exchange();
~~~

`mockJwt()` tạo authentication mô phỏng, không tự gọi JWS verification hoặc issuer validator. Một claim `iss` sai trong test này **không bắt buộc bị 401**. Để kiểm tra issuer, hãy **ký một JWT thật bằng test private key** với issuer sai và gửi nó qua `Authorization`.

### 12.5. Mock decoder chỉ hữu ích cho test xử lý lỗi

~~~java
when(reactiveJwtDecoder.decode(anyString()))
    .thenReturn(Mono.error(new BadJwtException("synthetic")));
~~~

Mock này có thể kiểm tra response khi decoder báo lỗi, nhưng **không kiểm tra decoder có tự phát hiện chữ ký/claims sai hay không**. Các cơ chế như `@MockBean` hoặc `@MockitoBean` (tùy phiên bản) thay decoder thật bằng mock cũng không đạt mục tiêu bài học. Nên giữ riêng **test error handling bằng mock** và **test xác thực mật mã bằng real decoder**.

## 13. HTTP status 401, 403 và việc chọn đúng security chain

Một JWT hợp lệ với `scope="orders.create"` có thể đã qua decoder thành công, nhưng GET `/api/orders` yêu cầu `SCOPE_orders.read`. Kết quả ở HTTP authorization thông thường là:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Một JWT sai chữ ký, issuer, audience hoặc thời gian thường bị từ chối ở authentication:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Không có Bearer credential trên endpoint bảo vệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Các response trên là ví dụ theo RFC 6750; nội dung header và body cụ thể còn phụ thuộc phiên bản Spring Security, entry point, access-denied handler và cấu hình chain. Trong test chính của bài, `expectStatus().isUnauthorized()` và `isForbidden()` kiểm tra **ranh giới authentication/authorization**; không nên phụ thuộc nguyên văn `error_description` do thư viện nội bộ tạo.

### 13.1. Chỉ assert 401 chưa chứng minh decoder đã chạy

Nếu test gọi URL không nằm trong chain JWT hoặc một route không có controller:

~~~java
client.get()
    .uri("/unknown-path")
    .headers(h -> h.setBearerAuth(invalidToken))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

401 có thể do filter authentication hoặc một chain khác, không chắc là decoder đã được nối đúng cho `/api/orders`. Để có bằng chứng, dùng **cùng URL protected** cho positive/negative controls và quan sát decoder trực tiếp hoặc bằng delegating counter khi cần.

### 13.2. `permitAll` không bảo đảm bỏ qua token sai

Một endpoint công khai:

~~~text
GET /public/catalog, no Bearer token:
    → có thể được cho phép

GET /public/catalog, Authorization: Bearer invalid:
    → có thể 401 bởi authentication filter
~~~

`permitAll()` áp ở authorization, nhưng Bearer authentication filter trong cùng chain vẫn có thể xử lý credential và từ chối nó trước khi authorization rule chạy. Nếu muốn khu vực public thực sự tách khỏi Bearer authentication, thiết kế chain riêng là một lựa chọn; đừng dùng `permitAll` trên API protected để làm token invalid “đi qua”.

### 13.3. Nhiều `SecurityWebFilterChain`

Giả sử:

~~~text
@Order(1) public chain: securityMatcher("/public/**")
@Order(2) API chain: securityMatcher("/api/**"), oauth2ResourceServer(jwt)
@Order(3) fallback chain: denyAll
~~~

Test JWT invalid phải gọi URL thuộc **API chain**, không phải public chain hoặc một URL không chain nào xử lý. Thứ tự chọn security chain và thứ tự matcher của `authorizeExchange(...)` đều là first-match-wins theo cấu hình. Một matcher rộng đặt sai vị trí có thể làm bộ test “không hề tới decoder” mà vẫn trả status lỗi.

### 13.4. CORS, OPTIONS và HTTP method

Browser gửi CORS preflight thường dùng `OPTIONS` và không mang Bearer token. Cấu hình CORS đúng giúp preflight đi qua theo policy, nhưng HTTP request thật vẫn phải xác thực. Đừng dùng một test OPTIONS không yêu cầu Bearer để kết luận decoder bảo vệ GET/POST API. Chọn đúng route + HTTP method trong từng test.

### 13.5. Đảm bảo 401 không trả raw token

Khi decoder báo lỗi, Spring Security có thể đưa thông tin mã lỗi Bearer trong `WWW-Authenticate`. HTTP response **không được echo nguyên JWT**, Authorization header, private key, claims nhạy cảm hoặc stack trace từ Nimbus.

Test có thể bổ sung:

~~~java
String fakeToken = "invalid-token-for-test-only";

client.get()
    .uri("/api/orders")
    .headers(h -> h.setBearerAuth(fakeToken))
    .exchange()
    .expectStatus().isUnauthorized()
    .expectBody(String.class)
    .value(body -> assertThat(body).doesNotContain(fakeToken));
~~~

Đây là test bảo vệ **response body**; nếu body rỗng hoặc representation khác, hãy chọn assertion phù hợp response format. Nó không tự kiểm tra access logs, APM/tracing hoặc gateway, nên cần privacy tests tại những tầng đó nếu tổ chức có thu HTTP headers/bodies.

## 14. Những sai lầm làm test âm tính “xanh giả”

### 14.1. Chỉ tạo token string bất kỳ rồi thấy 401

~~~java
expectUnauthorized("abc");
~~~

Test này chỉ chứng minh request mang chuỗi không parse được bị từ chối. Nó **không chứng minh chữ ký RSA, issuer, audience hay timestamp validators**. Cần từng JWT ký thật và chỉ sai một điều kiện.

### 14.2. Chỉ mock một `Jwt` object

~~~java
// PHẢN VÍ DỤ cho kiểm tra cryptographic validation:
Jwt jwt = Jwt.withTokenValue("fake")
    .header("alg", "RS256")
    .claim("iss", "https://issuer.example.test/realms/shop")
    .build();
~~~

Tạo `Jwt` object không có nghĩa nó đã được ký hoặc xác minh. Đây có thể là fixture để test claim mapping, không phải đối tượng chứng minh JWS.

### 14.3. Assert lỗi của mock decoder

~~~java
when(decoder.decode(anyString()))
    .thenReturn(Mono.error(new JwtException("bad")));
~~~

Kết quả 401 chỉ chứng minh filter xử lý `Mono.error`, không chứng minh decoder thật sẽ tự sinh lỗi với JWT sai chữ ký.

### 14.4. Dùng cùng một JWT sai nhiều điều kiện

JWT vừa ký bằng wrong key vừa có `iss` sai sẽ bị từ chối ở bước nào thì phụ thuộc decoder; không thể kết luận issuer validator hoạt động. Mỗi test case nên giữ những điều kiện còn lại đúng.

### 14.5. Cho JWT hợp lệ nhưng thiếu scope và mong 401

Scope thường được kiểm tra ở authorization sau khi decoder tạo principal. Nếu JWT hợp lệ nhưng không có `SCOPE_orders.read`, response mong đợi thường là **403**, trừ khi một validator token profile có rule đặc thù khác. Cần phân biệt hai tầng.

### 14.6. JWT hết hạn vài giây

Clock skew có thể khiến test không ổn định. Dùng `exp` đủ xa trong quá khứ; nếu kiểm thử skew boundary, kiểm soát clock/validator và không dựa vào scheduler ảo đơn thuần.

### 14.7. Test chỉ kiểm tra endpoint không tồn tại

Một URL không có handler thường có thể dẫn tới 404 khi authentication thành công, khiến positive control không đạt. Trong ví dụ chính có `OrdersEndpoint` thực sự trả `ok`; điều đó loại bỏ nhầm lẫn giữa lỗi routing và lỗi decode.

### 14.8. Dùng test decoder khác với decoder của HTTP chain

Một `StepVerifier` gọi bean decoder A không chứng minh chain dùng decoder A nếu security config đang có decoder B hoặc nhiều chain. Hãy kiểm soát context hoặc dùng decorator để xác nhận.

### 14.9. Tự nhận thuật toán từ token để tạo decoder

Không tạo decoder với thuật toán/URL lấy từ header chưa tin cậy rồi tự kết luận JWT hợp lệ. Khi test algorithm confusion, chính sách allowlist phải nằm ở cấu hình server, không để token quyết định.

### 14.10. Tạm bỏ claim validators để test chữ ký

Nếu cần test signature độc lập, có thể viết decoder test cấp thấp có policy rõ. Nhưng **integration test** phải dùng tập validator phù hợp production contract; không bỏ issuer/audience để negative test “chạy được” rồi vô tình bỏ sót bảo vệ.

### 14.11. Cấu hình secret/key test bị lẫn vào production

Không tái sử dụng private key thử nghiệm hoặc config public key test ở runtime production. Với `@SpringBootTest`, cô lập test configuration trong source set `src/test/java` hoặc class test-only, không đóng gói vào ứng dụng phát hành.

### 14.12. Dùng `StepVerifier.withVirtualTime` để giả thay hệ thống clock

Virtual time của Reactor điều khiển **scheduler được hỗ trợ**, nhưng không tự thay `Clock.systemUTC()` hoặc `Instant.now()` bên trong JWT validators. Nếu cần test chính xác deadline/clock skew, phải inject clock mà validator thực sự dùng hoặc tạo thời gian claims đủ xa ranh giới như ví dụ.

### 14.13. Bật logging toàn bộ JWT để debug

Không log raw Bearer token, private key, `Authorization` header hoặc claims PII trong CI. Nếu cần quan sát lỗi, dùng loại lỗi, request ID và instrumentation hạn chế. Token test là dữ liệu giả, nhưng thói quen log credential có thể bị copy sang production.

## 15. Chống flaky tests và rò rỉ trạng thái giữa các ca

### 15.1. Sinh test key theo vòng đời test context

Cặp khóa RSA nên được tạo cho **test context** hoặc test suite, để token được ký bằng đúng private key mà bean decoder sử dụng public key tương ứng. Nếu mỗi test tạo một key mới nhưng decoder vẫn giữ public key cũ, toàn bộ test hợp lệ sẽ bị 401, làm positive control thất bại.

### 15.2. Tạo JWT claims mới cho mỗi test

Một JWT hard-code `exp` trong tương lai gần có thể hết hạn khi CI chạy chậm hoặc khi tài liệu được dùng lại nhiều năm sau. `validClaims()` tạo timestamp tương đối theo `Instant.now()` như phần 5 giúp test không phụ thuộc ngày hiện tại.

### 15.3. Không để thứ tự test ảnh hưởng cache

JWKS decoder có thể cache keys. Test A tải JWKS rồi test B thay public key trên server nhưng dùng decoder cũ sẽ có kết quả phụ thuộc cache. Với case cần cache sạch, dùng **decoder mới**/context mới hoặc cơ chế reset cache công khai và chính thức. Nếu chủ đích test cache, phải kiểm soát thời gian và trạng thái cache minh bạch.

### 15.4. Không dùng shared mutable counter khi test chạy song song

`CountingReactiveJwtDecoder` đếm số lần subscribe. Nếu các test song song dùng chung bean, assert `before+1` có thể sai vì request khác chạy đồng thời. Chạy nhóm instrumentation tuần tự, tách context hoặc gắn observation theo request ID được quản lý phù hợp.

### 15.5. Dọn test HTTP server và tài nguyên

Với `LocalJwksServer`, dùng `try-with-resources` hoặc lifecycle hooks của test để `stop()` server, tránh rò cổng/socket. Không để server JWKS giả sống lâu sau bài test hoặc bind ra network interface công khai.

### 15.6. Đừng dùng live Authorization Server sản xuất

Test phải kiểm soát signing keys, tokens, issuer policy, clock và JWKS response. Gọi IdP production làm test chậm, khó lặp, có thể ghi audit hoặc sử dụng credential thật. Nếu cần acceptance test với IdP staging, dùng environment và tokens được cấp **riêng cho test**, bảo vệ secrets và không log raw token.

## 16. Ma trận hồi quy JWT thực trong WebFlux

Một bộ test tốt phải có cả **positive control**, các token sai đúng một điều kiện, và trường hợp authentication thành công nhưng authorization từ chối.

| Case | Token / điều kiện | Tầng phải kiểm tra | Kết quả thông dụng |
|---|---|---|---|
| R01 | RS256, key/iss/aud/exp/nbf/scope đúng | Decoder + authorization | HTTP 200 |
| R02 | Ký bằng private key không được tin | JWS signature | HTTP 401 |
| R03 | Sửa payload sau khi ký | JWS signature | HTTP 401 |
| R04 | `alg=none` | JOSE algorithm policy | HTTP 401 |
| R05 | HS256 khi chỉ allowlist RS256 | JOSE algorithm policy | HTTP 401 |
| R06 | JWT malformed | Decoder parsing | HTTP 401 |
| R07 | `iss` sai, chữ ký đúng | Issuer validator | HTTP 401 |
| R08 | `aud` sai, chữ ký đúng | Audience validator | HTTP 401 |
| R09 | `exp` đủ xa trong quá khứ | Timestamp validator | HTTP 401 |
| R10 | `nbf` đủ xa trong tương lai | Timestamp validator | HTTP 401 |
| R11 | Thiếu `exp` khi có custom rule bắt buộc | Claim/profile validator | HTTP 401 |
| R12 | `typ` sai theo access-token profile yêu cầu | Token type validator nếu đã cấu hình | HTTP 401 |
| R13 | JWT đúng nhưng chỉ có `orders.create` | HTTP `hasAuthority("SCOPE_orders.read")` | HTTP 403 |
| R14 | Không mang Bearer token | Authentication entry point | HTTP 401 |
| R15 | JWT đúng nhưng signer key không có trong JWKS | JWKS/key-selection | Không xác thực |
| R16 | JWKS server timeout, chưa có trusted cached key | JWKS transport/trust | Không xác thực; HTTP code tùy error policy |

Với R11 và R12, Spring Security không tự suy ra mọi hợp đồng riêng của issuer. Chỉ assert từ chối khi ứng dụng **đã cấu hình validator tương ứng**. Với R15/R16, có thể phát lỗi hạ tầng khác với `invalid_token`; điều bất biến là **không cấp principal khi thiếu bằng chứng xác minh**.

### 16.1. Ma trận test wiring và cấu hình

| Thay đổi cấu hình | Nguy cơ cần phát hiện |
|---|---|
| Bean decoder thật bị mock vô tình | Test chỉ kiểm tra `Mono` do mock phát |
| Audience validator bị bỏ khỏi `setJwtValidator` | Token cấp cho API khác được nhận |
| Timestamp validator bị thay bằng audience-only validator | Token hết hạn có thể được nhận |
| Security chain không bật `oauth2ResourceServer().jwt()` | Bearer token không đi qua decoder |
| Public chain đặt matcher quá rộng | Request đi nhầm chain |
| JWT converter đổi prefix authority | Token đúng bị 403 hoặc sai phân quyền |
| JWKS caching không được kiểm soát | Key rotation test phụ thuộc thứ tự |
| JWT `typ` profile bị đổi | ID token/access token confusion |
| Custom error handler trả stack trace/raw token | Rò rỉ credential |

Không cần chạy mọi ca bằng `@SpringBootTest`. Có thể chia decoder-focused `StepVerifier` tests, HTTP integration `WebTestClient` tests, JWKS integration tests và authorization tests để cân đối tốc độ với độ bao phủ.

## 17. Chẩn đoán một negative test thất bại

### 17.1. Sai audience vẫn được 200

Kiểm tra test có dùng `mockJwt()` hoặc mock decoder không; audience validator có được gắn vào bean thật không; `setJwtValidator(...)` có bị gọi lần hai thay mất rule không; request có chọn đúng security chain không; có custom `onErrorResume` nào tạo principal từ token chưa xác minh không.

### 17.2. Sai chữ ký vẫn được 200

Đây là tình huống cần điều tra trực tiếp:

~~~text
HTTP Authorization: Bearer ...
    ↓
AuthenticationWebFilter của Resource Server
    ↓
ReactiveJwtDecoder thật?
    ↓
JWS signature verification bằng trusted key?
    ↓
Authentication chỉ khi JWT hợp lệ
~~~

Nguyên nhân thường gặp là test đã mô phỏng authentication, binding `WebTestClient` không đi qua security filters, hoặc custom decoder chỉ parse payload mà không xác minh chữ ký. JWT thử nghiệm nên được ký bằng **wrong RSA private key** trong khi mọi claims khác vẫn đúng.

### 17.3. Token hợp lệ lại trả 401

Kiểm tra private/public key có cùng cặp không, `kid` có khớp JWKS không, `alg` có thuộc allowlist không, `iss`/`aud` có đúng hợp đồng không, token có còn hạn theo clock test không và HTTP request có chọn đúng decoder/chain không. Nếu positive control 200 thất bại, **không kết luận từ các negative tests 401 rằng decoder hoạt động đúng**.

### 17.4. Token hợp lệ trả 403

Decoder có thể đã hoàn tất đúng và lỗi nằm ở authority mapping. Ví dụ:

~~~text
JWT claim: scope="orders.read"
Expected GrantedAuthority: SCOPE_orders.read
HTTP rule: hasAuthority("SCOPE_orders.read")
~~~

Nếu custom converter đổi claim name/prefix hoặc tạo authorities khác, JWT vẫn được xác thực nhưng thiếu quyền. Không bỏ HTTP authorization rule chỉ để test trả 200; cần xác định mapping và hợp đồng.

### 17.5. JWKS server đã tắt nhưng JWT vẫn được xác thực

Có thể decoder đã giữ **public key cached và còn tin cậy**. Đây không nhất thiết là fail-open. Khi test lỗi tải khóa, sử dụng decoder có cache rỗng hoặc kiểm soát chính xác trạng thái key; phân biệt “không cần gọi JWKS vì có cache” với “bỏ xác minh”.

### 17.6. Test độc lập xanh nhưng cả suite đỏ

Tìm shared mutable state: cặp RSA keys bị thay giữa test, JWKS cache từ test trước, local HTTP server đã đóng, parallel calls làm sai counter, timestamps quá sát skew boundary hoặc profile config thay đổi. Cần test isolation và input deterministic, không phụ thuộc thứ tự.

### 17.7. Lỗi `StepVerifier` không chỉ ra HTTP wiring

`StepVerifier` gọi decoder trực tiếp, nên không kiểm tra Bearer resolver/HTTP security chain. Ngược lại, HTTP 401 có thể xuất hiện trước decoder. Đó là lý do vừa cần **direct decoder tests**, vừa cần **HTTP Bearer integration tests**.

## 18. Bài tập thực hành

### Bài tập 1. Phân biệt chữ ký sai và issuer sai

Tạo hai JWT:

- JWT A: đúng `iss`/`aud`/time/scope nhưng ký bằng RSA private key không được tin.
- JWT B: đúng signature/public key, audience/time/scope, nhưng `iss` là issuer khác.

Gửi lần lượt qua `WebTestClient` tới `GET /api/orders`, xác nhận cả hai 401 và `validToken()` vẫn được 200. Sau đó dùng `StepVerifier` để chứng minh decoder thật phát error cho từng JWT. Không dùng mock decoder để “giả” kết quả.

### Bài tập 2. Kiểm tra audience khác resource

Ký JWT hợp lệ với `aud=["billing-api"]` và `scope="orders.read"`. Kỳ vọng Orders API từ chối ở **authentication** vì audience sai, không được dựa vào scope để cho qua.

### Bài tập 3. Kiểm tra scope sai nhưng token hợp lệ

Ký JWT đúng issuer/audience/key/time với `scope="orders.create"`. Gửi GET `/api/orders` và kỳ vọng **403** thay vì 401. Đây là một test chứng minh sự tách biệt giữa validation và authorization.

### Bài tập 4. Kiểm tra JWT hết hạn sát thời điểm hiện tại

Tạo `exp=now-1s` rồi quan sát test có thể phụ thuộc clock skew. Thay bằng `exp=now-1h` để test hết hạn chắc chắn, hoặc cấu hình clock/skew rõ ràng nếu đang kiểm tra ranh giới thời gian. Không dùng `StepVerifier.withVirtualTime` rồi giả định nó tự thay `Clock.systemUTC()`.

### Bài tập 5. Kiểm tra JWKS

Chạy `LocalJwksServer` công bố public JWK, giải mã token ký với matching `kid`. Sau đó tạo một decoder mới trỏ đến JWKS không chứa signer key và xác nhận JWT không được chấp nhận. Đừng dùng decoder có cache cũ khi mục tiêu là kiểm tra missing key.

### Bài tập 6. Chứng minh đi qua decoder

Đổi bean test sang `CountingReactiveJwtDecoder` bọc `NimbusReactiveJwtDecoder`. Gửi Bearer JWT sai chữ ký, xem số subscription tăng trong một test chạy tuần tự; đồng thời xác nhận JWT hợp lệ vẫn được 200. **Không thay delegate bằng mock**.

## 19. Checklist khi hoàn tất bài kiểm thử

- [ ] Test có **JWT ký thật bằng private key thử nghiệm**, không chỉ mock principal.
- [ ] Security chain có `oauth2ResourceServer(...jwt(...))` và dùng `ReactiveJwtDecoder` thật.
- [ ] Decoder trust public key/JWKS và algorithm đã allowlist.
- [ ] Có positive control: JWT hợp lệ nhận 200 trên endpoint có controller.
- [ ] Các case sai signature, issuer, audience, expiry, not-before được tách riêng.
- [ ] Có negative case unsigned/unsupported algorithm.
- [ ] Có case JWT hợp lệ thiếu scope trả 403 ở authorization.
- [ ] Test gọi đúng URL/method trong đúng `SecurityWebFilterChain`.
- [ ] `StepVerifier` kiểm tra error signal thay vì chỉ object `Mono` không null.
- [ ] Không dùng `mockJwt()` để chứng minh cryptographic verification.
- [ ] Claim validators sau `setJwtValidator` vẫn giữ default issuer/time rules.
- [ ] Nếu có token type, `exp` presence hoặc tenant rule bắt buộc thì có validator và test tương ứng.
- [ ] Với JWKS: có test key retrieval, `kid`, missing/wrong key và cache/rotation tùy nhu cầu.
- [ ] Không phụ thuộc clock sát expiry, thứ tự test hoặc cache không kiểm soát.
- [ ] Không dùng production private key/token; không log raw Bearer credential.
- [ ] Khi JWKS lỗi, hệ thống **không chấp nhận token chưa xác minh**.

## 20. Kết luận

Để kiểm thử JWT không hợp lệ trong Spring Security WebFlux, cần phân biệt rõ **mô phỏng một principal đã được xác thực** với **chạy xác minh JWT thật**:

~~~text
Không đủ cho JWT validation:
    mockJwt()
    @WithMockUser
    mocked ReactiveJwtDecoder
    Jwt.withTokenValue(...) tạo object
    kiểm tra Mono != null

Đúng mục tiêu:
    Test RSA private key → ký JWT
    WebTestClient → Authorization: Bearer <signed JWT>
    Spring Security WebFlux filter chain
    NimbusReactiveJwtDecoder thật
    Verify JWS + issuer + audience + timestamp
    401 nếu token invalid
    403 nếu token valid nhưng thiếu authority
    200 nếu valid và đủ quyền
~~~

**`StepVerifier` kiểm tra decoder trực tiếp; `WebTestClient` kiểm tra decoder trong luồng HTTP thật.** Hai cách kết hợp với positive control và các negative cases tách biệt sẽ chứng minh API không chỉ trả lỗi cho một chuỗi token bất kỳ, mà thật sự **từ chối token không hợp lệ qua decoder phản ứng được cấu hình đáng tin**.

Khi production còn phụ thuộc JWKS/discovery, bổ sung integration test với **JWK Set server thử nghiệm** để kiểm tra lấy khóa, `kid` và key rotation. Dù ở public-key test hay JWKS test, nguyên tắc bảo mật cuối cùng không đổi: **không có xác minh đáng tin thì không tạo Authentication thành công, và JWT đã xác thực vẫn phải qua authorization cho endpoint và dữ liệu nghiệp vụ**.

## Tài liệu tham khảo

- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html)
- [Spring Security — NimbusReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [Spring Security — ReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [Spring Security — JwtValidators Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Reactor — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
