# Tránh tự viết bộ lọc giải mã JWT và tránh coi dữ liệu chưa xác minh là danh tính

*Chuyên đề: Spring Security Reactive — Resource Server JWT. Java 17+, Spring WebFlux, Spring Security 6.x.*

## 1. Vấn đề bảo mật cốt lõi

Một API WebFlux nhận Authorization: Bearer JWT. Người phát triển có thể chia JWT thành ba đoạn, giải mã payload bằng Base64URL, tìm sub=admin và gán một Authentication có quyền ADMIN vào Reactor SecurityContext. Đây là **lỗ hổng xác thực nghiêm trọng**: Base64URL chỉ biến chuỗi thành dữ liệu có thể đọc, không xác minh bất kỳ chữ ký hay nguồn gốc nào. Attacker hoàn toàn có thể tạo payload với sub, roles, tenant hoặc expiresAt bất kỳ.

Không nên tự xây authentication WebFilter chỉ để đọc JWT. Spring Security Reactive đã có OAuth2 Resource Server, JwtReactiveAuthenticationManager, ReactiveJwtDecoder và NimbusReactiveJwtDecoder để xác minh token trước khi tạo Authentication. Các rule authorizeExchange hay method security chỉ đáng tin khi Authentication được tạo từ token thực sự qua chuỗi xác minh.

Kết thúc bài học, bạn cần:

1. Phân biệt decode dữ liệu, verify JWS signature, validate claims, tạo Authentication và authorize một request.
2. Biết vì sao JWT header/payload, X-User, X-Role, cookie username, Origin hay URL query **chưa được xác minh** không thể được dùng làm danh tính.
3. Cấu hình Resource Server JWT chuẩn bằng ServerHttpSecurity, một trusted JWKS, RS256 và validators iss, exp, nbf, aud.
4. Nhận biết lỗi alg=none, algorithm confusion, untrusted jku/x5u, key confusion, ID-token confusion, wrong-audience và JWT tampering.
5. Phân biệt status 401 do token không hợp lệ với 403 do principal hợp lệ nhưng thiếu scope.
6. Dùng JwtAuthenticationToken/@AuthenticationPrincipal Jwt và authority SCOPE_orders.read đúng cách.
7. Viết ứng dụng Gradle Java 17+ Spring Boot 3.5.16 với ba endpoint public, authenticated và scope-protected.
8. Viết kiểm thử WebTestClient sử dụng **RSA signature thật** và MockWebServer JWKS nội bộ, không chỉ mock principal để giả vờ đã xác thực.
9. Xác định giới hạn JWT offline: revocation, JWKS rotation, trust boundaries, audience, token type và quyền theo resource/tenant.

**Nguyên tắc:** mọi claim đều là dữ liệu không đáng tin cho đến khi JWT được xác minh chữ ký và kiểm tra ngữ cảnh. Sau xác thực, JWT hợp lệ vẫn không tự tạo quyền trên mọi dữ liệu.

## 2. JWT là dữ liệu có thể đọc, không phải dữ liệu đã được tin cậy

Một JWT dạng JWS compact thường gồm:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Header minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "key-2026"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "alice",
  "aud": ["api://training"],
  "iat": 1780000000,
  "nbf": 1780000000,
  "exp": 1780001800,
  "scope": "orders.read"
}
~~~

**Không có encryption trong JWS ví dụ.** Người giữ JWT có thể đọc header và payload. Do đó không đưa password, refresh token, PII nhạy cảm hay secret vào JWT. Chữ ký xác nhận authenticity/integrity khi verifier dùng key đáng tin, thuật toán đúng và kiểm tra chữ ký thật; nó không tự che giấu claims.

| Bước | Làm gì | Ý nghĩa bảo mật |
| --- | --- | --- |
| Base64URL decode | Đọc JSON header và payload | Chưa hề xác minh nguồn gốc |
| Parse JSON | Lấy các claim sub, iss, aud, scope | Vẫn là input do client cung cấp |
| JWS verification | Dùng trusted public key + approved algorithm kiểm tra signature | Phát hiện payload/header bị sửa |
| Claim validation | Kiểm tra issuer, aud, exp, nbf, token type | Token phải dành cho API và còn hợp lệ |
| Authentication conversion | Chuyển verified Jwt thành Authentication/authorities | Principal đã có ranh giới tin cậy |
| Authorization | Kiểm tra scope/role/tenant/ownership | Caller có quyền đối với request/resource cụ thể |

Ví dụ **sai**, không được triển khai làm authentication:

~~~java
String[] parts = bearerToken.split("\\.");
String decodedPayload = new String(
        java.util.Base64.getUrlDecoder().decode(parts[1]),
        java.nio.charset.StandardCharsets.UTF_8);
// Nếu parse decodedPayload rồi tin "sub":"admin" hoặc "role":"ADMIN"
// để tạo Authentication: attacker có thể tự dựng token giả.
// Kiểm tra ba đoạn và giải mã JSON KHÔNG hề kiểm tra chữ ký.
~~~

Một người có thể tạo JWT giả header alg=none, payload sub=admin, scope=orders.read, expiry năm sau. Nếu app tin payload trước khi verify, attacker đã vượt authentication. Dù kiểm tra cấu trúc ba đoạn, chữ ký vẫn có thể sai hoặc thiếu.

### 2.1. Header cũng không phải trust anchor

Các tham số kid, alg, jku, jwk, x5u trong JOSE header do phía đưa token lựa chọn. Policy phải tới từ Resource Server:

- Algorithm được phép: ví dụ RS256, không do token tự quyết định.
- Issuer và JWKS URL từ cấu hình triển khai đáng tin, không phải URL trong header token.
- kid chỉ gợi ý chọn key **trong trusted JWKS**; không là đường dẫn máy chủ hay URL để fetch.
- Không chấp nhận alg=none cho signed access token.
- Không nhầm public RSA key thành HMAC secret khi thư viện cho phép nhiều thuật toán. Đây là algorithm/key confusion.
- Không chấp nhận một public key JWK do attacker nhúng vào JWT làm key xác minh nguồn đáng tin.

Cho phép token đưa jku tới một hostname ngoài dự kiến có thể gây **SSRF** và attacker-key substitution. Không tự viết logic dynamic fetch JWKS dựa trên header token.

### 2.2. Claims còn cần ngữ cảnh

**iss** là bên phát hành token. **sub** thường là subject trong phạm vi issuer; trong hệ đa issuer nên cân nhắc cặp (iss, sub), không chỉ sub. **aud** xác định tài nguyên nhận token. Token của API khác dù đúng chữ ký phải bị từ chối. **exp** và **nbf** xác định cửa sổ thời gian; dùng clock skew có kiểm soát. **scope/scp** chỉ được chuyển thành authorities sau validation.

JWT hợp lệ có scope orders.read vẫn không cho Alice đọc đơn của Bob nếu API cần ownership/tenant check. Authorization là bước độc lập với việc xác minh token.

## 3. Không nhầm ID token với OAuth2 access token

OIDC ID token thường cũng được ký bởi Authorization Server, nhưng nó dành cho OAuth2/OIDC Client để xác nhận lần login, không tự là Bearer access token cho Resource Server. Một token reset password cũng có thể là JWT ký bằng cùng key của issuer. Không nhận tất cả làm access token chỉ vì signature hợp lệ.

Cần áp dụng những quy tắc của profile token thực tế: audience của API, issuer, token type/typ (ví dụ at+jwt theo RFC 9068 nếu nhà cung cấp dùng profile đó), use, client_id và các claims bắt buộc khác theo hợp đồng. Không tùy tiện tắt type validation để cho mọi loại JWT vào API.

Một số API dùng opaque access token thay JWT; khi đó dùng cơ chế OAuth2 Resource Server opaque-token introspection phù hợp, **không tự giả định token nào cũng có ba phần**.

### 3.1. Một JWT hợp lệ không đồng nghĩa có quyền admin

Valid signature chỉ nói rằng token được ký bởi key chấp nhận. Nếu issuer cấp access token cho Bob, Resource Server phải lấy subject Bob chứ không tin request tự thêm X-User: admin. Nếu Bob không có scope orders.read, GET /api/orders phải 403. Nếu Bob có scope nhưng cố đọc order thuộc Alice, nghiệp vụ phải kiểm tra owner/tenant.

## 4. Spring Security Reactive xác minh JWT như thế nào?

~~~text
HTTP GET + Authorization: Bearer <token>
                  |
                  v
         SecurityWebFilterChain
                  |
                  v
      Bearer authentication converter
                  |
                  v
       JwtReactiveAuthenticationManager
                  |
                  v
         ReactiveJwtDecoder
       (NimbusReactiveJwtDecoder)
           |       |       |
           |       |       +-- check issuer, audience, exp, nbf
           |       +---------- approved JWS algorithm
           +------------------ verify JWS with trusted JWKS
                  |
          +-------+-------+
          |               |
        hợp lệ          không hợp lệ
          |               |
          v               v
  JwtAuthentication     401 + WWW-Authenticate: Bearer
          |
          v
  Reactor SecurityContext
          |
          v
 authorizeExchange / method security / owner checks
          |
       +--+--+
       |     |
   đủ quyền thiếu quyền
       |     |
       v     v
      200   403
~~~

Đây là sơ đồ trách nhiệm, không mô tả thứ tự từng class nội bộ bất biến qua mọi phiên bản. Điểm cốt lõi: **decoder và validators chạy trước khi claims trở thành Authentication**.

### 4.1. Cấu hình ngắn gọn thường dùng

Nếu nhà cung cấp hỗ trợ issuer metadata hợp lệ và Boot có thể kết nối, các dòng sau là một khởi điểm tiêu chuẩn:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test
~~~

Cùng với cấu hình SecurityWebFilterChain:

~~~java
http
    .authorizeExchange(ex -> ex.anyExchange().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
            org.springframework.security.config.Customizer.withDefaults()));
~~~

Đoạn trên chỉ là phần method minh họa. Spring Boot và Spring Security cung cấp decoder, signature verification và kiểm tra issuer/timestamp theo defaults. **Audience của Resource Server cần được xác nhận rõ** bằng cấu hình Boot phù hợp phiên bản hoặc custom OAuth2TokenValidator; không coi defaults tự kiểm tra audience của mọi API.

Bài demo dùng bean NimbusReactiveJwtDecoder có JWKS URI từ cấu hình và validator audience để dễ nhận diện từng kiểm tra. Không tự tạo JWT parsing WebFilter.

### 4.2. Principal đã được verify

Spring Resource Server JWT thường tạo JwtAuthenticationToken và dùng Jwt làm principal. Một controller có thể nhận Jwt bằng @AuthenticationPrincipal:

~~~java
@GetMapping("/api/me")
public Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(Map.of("subject", jwt.getSubject()));
}
~~~

Đoạn trên là phương thức trong controller, không phải file Java độc lập. Ở đây Jwt đến từ Spring SecurityContext sau khi authentication thành công. Nếu đọc ReactiveSecurityContextHolder trong service, cũng chỉ sử dụng Authentication do security pipeline tạo, không tự gán một object fake từ raw request header.

## 5. Những validators quan trọng

| Kiểm tra | Mục đích | Kết quả khi sai |
| --- | --- | --- |
| Chữ ký JWS | Phát hiện sửa header/payload và người ký không đúng | 401 |
| Trusted alg | Ngăn alg=none/alg confusion | 401 |
| JWKS trust | Không lấy key từ URL do attacker chọn | 401/fail closed |
| issuer iss | Token đến từ Authorization Server được phê duyệt | 401 |
| audience aud | Token phải dành cho API cụ thể | 401 |
| expiration exp | Token không hết hạn (có skew giới hạn) | 401 |
| not-before nbf | Token chưa có hiệu lực phải bị từ chối | 401 |
| type/use | Không nhận ID/password-reset token thành access token | 401 |
| scope/authority | Quyền gọi endpoint | 403 nếu JWT hợp lệ nhưng không đủ |
| owner/tenant | Quyền truy cập resource cụ thể | 403 hoặc 404 theo chính sách không lộ tồn tại |
| revocation | Tùy mô hình JWT offline/introspection | Có thể cần state hoặc token TTL ngắn |

**Sai claims không được dùng làm principal rồi mới “sửa sau”.** Từ chối chúng ở decoder/validator hoặc auth manager, trước authorization.

### 5.1. Clock skew không có nghĩa bỏ kiểm tra expiry

Resource Server dùng JwtTimestampValidator và có khoảng dung sai lệch đồng hồ (thường 60 giây theo Spring Security 6.x). Đặt skew vừa đủ theo NTP/network latency, không gỡ exp/nbf validation để chữa đồng hồ máy lỗi. Kiểm tra expired token trong test với quá hạn nhiều phút tránh flaky behavior tại đúng biên.

### 5.2. Key rotation

Authorization Server có thể phát JWT mới với kid mới. JWKS tin cậy có thể chứa nhiều public keys trong giai đoạn chuyển đổi. Dùng NimbusReactiveJwtDecoder/JWKS caching theo thư viện; kiểm tra key rotation khi triển khai, không hard-code public key vĩnh viễn nếu issuer thường xuyên rotate.

Nếu JWKS endpoint tạm lỗi, **không fallback accept-all** hoặc bỏ signature validation. Cần xử lý availability, timeout, cache và observability trong trust boundary đúng.

## 6. Dự án thực hành Java 17+: Spring Boot WebFlux Resource Server

Đây là ví dụ **Spring Boot 3.5.16** với Gradle 8.x tương thích và Java 17+. Các địa chỉ issuer.example.test là ví dụ, không có IdP Internet thật. Ứng dụng có thể khởi động và phục vụ GET /public/ping, nhưng để nhận một Bearer thật từ production phải cấu hình issuer/JWKS/audience thật. Bộ integration test ở mục 7 sẽ cấp JWKS từ MockWebServer loopback và ký JWT bằng private key test để chứng minh decoder hoạt động mà không cần IdP bên ngoài.

Mục tiêu endpoint:

| Method/path | Chính sách |
| --- | --- |
| GET /public/ping | Public |
| GET /api/me | JWT hợp lệ |
| GET /api/orders | JWT hợp lệ và SCOPE_orders.read |
| Các URL khác | denyAll |

### 6.1. Cấu trúc thư mục

~~~text
verified-jwt-api/
├── settings.gradle
├── build.gradle
├── src/main/resources/application.yml
├── src/main/java/example/resource/ResourceApplication.java
├── src/main/java/example/resource/SecurityConfig.java
├── src/main/java/example/resource/ApiController.java
└── src/test/java/example/resource/JwtSecurityIntegrationTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'verified-jwt-api'
~~~

### 6.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Project chỉ dùng WebFlux và Resource Server. Không sử dụng spring-boot-starter-web MVC hay tự chèn Bearer parsing WebFilter. MockWebServer là test-only dependency.

### 6.4. application.yml

~~~yaml
app:
  security:
    issuer: https://issuer.example.test
    jwk-set-uri: https://issuer.example.test/oauth2/jwks
    audience: api://training
~~~

Cả ba giá trị đều phải đến từ deployment trusted configuration. Trong production, JWKS URI cần HTTPS và domain IdP được phê duyệt; không lấy issuer hoặc jwkSetUri từ JWT untrusted hay query của request. JWK URI mock trong test là HTTP loopback **chỉ dành cho test**, không cấu hình production.

### 6.5. ResourceApplication.java

~~~java
package example.resource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceApplication.class, args);
    }
}
~~~

### 6.6. SecurityConfig.java

~~~java
package example.resource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(Environment env) {
        String jwksUri = required(env, "app.security.jwk-set-uri");
        String issuer = required(env, "app.security.issuer");
        String audience = required(env, "app.security.audience");

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withJwkSetUri(jwksUri)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required audience is missing",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard, audienceValidator));
        return decoder;
    }

    private static String required(Environment env, String key) {
        String value = env.getProperty(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing trusted JWT setting: " + key);
        }
        return value;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/public/ping").permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/orders")
                                .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.GET,
                                "/api/me").authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .build();
    }
}
~~~

**Các quyết định bảo mật trong SecurityConfig:**

1. JWKS URI, issuer, audience đọc từ trusted Environment, không từ request hoặc token.
2. NimbusReactiveJwtDecoder xác minh **JWS RS256** dựa trên JWKS đã cấu hình.
3. JwtValidators.createDefaultWithIssuer kiểm tra issuer và các timestamps mặc định. Không tự làm Base64URL decode.
4. Audience validator kiểm tra API hiện tại có nằm trong claim aud hay không; không dùng contains substring trong raw payload.
5. DelegatingOAuth2TokenValidator giữ cả standard checks lẫn audience check.
6. oauth2ResourceServer().jwt() kích hoạt authentication framework, Spring tạo JwtAuthenticationToken/authorities sau verify.
7. /api/orders yêu cầu **SCOPE_orders.read** đã được chuyển từ scope của JWT hợp lệ, không từ X-Role.
8. Rule denyAll ngăn request tới URL không được công bố.
9. Không có OAuth2 Client flow trong Resource Server demo; API chỉ nhận Bearer và kiểm tra.
10. Để yêu cầu RFC 9068 access token typ=at+jwt, cần cấu hình token type validation theo contract của issuer; ví dụ chưa tự định nghĩa profile này.

### 6.7. ApiController.java

~~~java
package example.resource;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }

    @GetMapping("/api/orders")
    public Mono<Map<String, String>> orders(
            @AuthenticationPrincipal Jwt jwt) {
        // Trong nghiệp vụ thật còn kiểm tra owner/tenant.
        return Mono.just(Map.of(
                "subject", jwt.getSubject(),
                "resource", "orders"));
    }
}
~~~

Controller không đọc header Authorization hay parse raw token. Jwt chỉ được Spring cung cấp cho request đã authentication thành công. Không expose raw JWT hoặc toàn bộ claims qua API nếu không có nhu cầu.

## 7. Integration test dùng chữ ký RSA thật và trusted JWKS local

Một test dùng mockJwt() có giá trị khi kiểm thử **authorization rules**, nhưng nó cố ý không kiểm chứng signature. Bài này cần negative tests thực sự đi qua ReactiveJwtDecoder. Vì vậy test tạo RSA keypair ở runtime, dùng NimbusJwtEncoder **private key** ký token, MockWebServer chỉ xuất **public key** qua JWKS, rồi gọi server Spring WebFlux bằng WebTestClient.

**Không cần IdP thật, không cần internet.** Hệ thống test tạo issuer và audience giả nhưng nhất quán. Mọi JWT sai vẫn phải bị NimbusReactiveJwtDecoder từ chối.

### 7.1. JwtSecurityIntegrationTest.java

~~~java
package example.resource;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Base64;
import java.util.List;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class JwtSecurityIntegrationTest {

    private static final String ISSUER =
            "https://issuer.example.test";
    private static final String AUDIENCE =
            "api://training";
    private static final String KID = "rsa-test-key-1";

    private static final KeyPair KEYS = newKeyPair();
    private static final RSAKey JWK =
            new RSAKey.Builder((RSAPublicKey) KEYS.getPublic())
                    .privateKey((RSAPrivateKey) KEYS.getPrivate())
                    .keyID(KID)
                    .algorithm(JWSAlgorithm.RS256)
                    .build();

    private static final JwtEncoder ENCODER =
            new NimbusJwtEncoder(
                    new ImmutableJWKSet<>(new JWKSet(JWK)));

    private static final MockWebServer JWKS_SERVER =
            startJwksServer();

    @Autowired
    WebTestClient client;

    private static KeyPair newKeyPair() {
        try {
            KeyPairGenerator generator =
                    KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static MockWebServer startJwksServer() {
        MockWebServer server = new MockWebServer();
        String publicJwks = new JWKSet(
                JWK.toPublicJWK()).toString();

        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                if ("/jwks".equals(request.getPath())) {
                    return new MockResponse()
                            .setResponseCode(200)
                            .addHeader("Content-Type",
                                    "application/json")
                            .setBody(publicJwks);
                }
                return new MockResponse().setResponseCode(404);
            }
        });

        try {
            server.start();
            return server;
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    @DynamicPropertySource
    static void jwtProperties(DynamicPropertyRegistry registry) {
        registry.add("app.security.issuer", () -> ISSUER);
        registry.add("app.security.audience", () -> AUDIENCE);
        registry.add("app.security.jwk-set-uri",
                () -> JWKS_SERVER.url("/jwks").toString());
    }

    @AfterAll
    static void shutdown() throws IOException {
        JWKS_SERVER.shutdown();
    }

    private static String sign(
            String subject, String issuer,
            String audience, String scope, Instant expiry) {
        Instant issued = Instant.now().minusSeconds(7200);

        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(issuer)
                .subject(subject)
                .audience(List.of(audience))
                .issuedAt(issued)
                .notBefore(issued)
                .expiresAt(expiry)
                .claim("scope", scope)
                .build();

        JwsHeader header = JwsHeader
                .with(SignatureAlgorithm.RS256)
                .keyId(KID)
                .build();

        return ENCODER.encode(
                JwtEncoderParameters.from(header, claims))
                .getTokenValue();
    }

    private static String valid(String subject, String scope) {
        return sign(subject, ISSUER, AUDIENCE, scope,
                Instant.now().plusSeconds(900));
    }

    @Test
    void publicPingIsAccessible() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void protectedApiNeedsBearerToken() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists("WWW-Authenticate");
    }

    @Test
    void signedJwtBecomesTrustedPrincipal() {
        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(
                        valid("alice", "orders.read")))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("alice");
    }

    @Test
    void verifiedScopeAllowsOrders() {
        client.get().uri("/api/orders")
                .headers(h -> h.setBearerAuth(
                        valid("alice", "orders.read")))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.resource").isEqualTo("orders");
    }

    @Test
    void validJwtWithoutScopeIsForbidden() {
        client.get().uri("/api/orders")
                .headers(h -> h.setBearerAuth(
                        valid("alice", "profile")))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void fakeUserAndRoleHeadersDoNotReplaceJwtIdentity() {
        client.get().uri("/api/me")
                .header("X-User", "admin")
                .header("X-Role", "ADMIN")
                .headers(h -> h.setBearerAuth(
                        valid("alice", "profile")))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("alice");
    }

    @Test
    void fakeUserHeaderWithoutBearerCannotAuthenticate() {
        client.get().uri("/api/me")
                .header("X-User", "admin")
                .header("X-Role", "ADMIN")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void modifiedSignatureIsRejected() {
        String[] parts = valid(
                "alice", "orders.read").split("\\.");
        String sig = parts[2];
        parts[2] = (sig.charAt(0) == 'A' ? "B" : "A")
                + sig.substring(1);

        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(
                        String.join(".", parts)))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctSignatureButWrongIssuerIsRejected() {
        String jwt = sign(
                "admin", "https://other-issuer.example.test",
                AUDIENCE, "orders.read",
                Instant.now().plusSeconds(900));

        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctSignatureButWrongAudienceIsRejected() {
        String jwt = sign(
                "admin", ISSUER, "api://other",
                "orders.read", Instant.now().plusSeconds(900));

        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void expiredSignedJwtIsRejected() {
        String jwt = sign(
                "admin", ISSUER, AUDIENCE,
                "orders.read", Instant.now().minusSeconds(600));

        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void algNoneUnsignedJwtCannotImpersonateAdmin() {
        String header = b64(
                "{\"alg\":\"none\",\"typ\":\"JWT\"}");
        String payload = b64(
                "{\"sub\":\"admin\",\"scope\":\"orders.read\","
                + "\"iss\":\"https://issuer.example.test\","
                + "\"aud\":[\"api://training\"]}");
        String forged = header + "." + payload + ".";

        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(forged))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    private static String b64(String text) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(
                        text.getBytes(StandardCharsets.UTF_8));
    }
}
~~~

### 7.2. Chạy và giải thích kết quả

~~~bash
gradle test
~~~

**Dự kiến:** 12 JUnit tests pass khi JDK, Gradle và dependencies phù hợp. Đây là kỳ vọng từ thiết kế, **không phải tuyên bố build thực tế đã được chạy**. MockWebServer mở một cổng loopback chỉ để trả public JWKS; test encoder ký JWT bằng private key RSA tạo ngẫu nhiên trong bộ nhớ.

Những tình huống đã test:

| Trường hợp | HTTP status mong đợi | Kiểm chứng |
| --- | --- | --- |
| GET /public/ping không token | 200 | Public endpoint |
| GET /api/me không token | 401 | Thiếu Authentication |
| JWT RS256 đúng, iss/aud/exp hợp lệ | 200 | Signature và claims hợp lệ |
| JWT scope orders.read | 200 trên /api/orders | Mapping SCOPE_orders.read |
| JWT đúng nhưng scope chỉ profile | 403 | Authorization độc lập |
| JWT Alice, X-User admin | 200 trả Alice | Header giả không thay principal |
| X-User admin, không Bearer | 401 | Không tin header tự khai |
| Chữ ký bị thay byte | 401 | Signature verification thật |
| Chữ ký đúng nhưng issuer khác | 401 | iss validation |
| Chữ ký đúng nhưng audience khác | 401 | aud validation |
| JWT hết hạn nhiều phút | 401 | exp validation |
| alg=none và payload admin | 401 | Không chấp nhận token unsigned |

**Vì sao phải ký RSA thật?** Nếu chỉ dùng mockJwt() hoặc @MockBean decoder, bạn có thể kiểm tra controller và authorization nhưng **không chứng minh cryptographic signature verification**. Bài này để NimbusReactiveJwtDecoder thật lấy public JWK và xác minh các JWT thật do encoder test ký, nhờ đó các negative tests có ý nghĩa.

**Ranh giới test:** JWK server HTTP localhost là môi trường test, khác production. Test này không xác minh JWKS endpoint thật của doanh nghiệp, issuer discovery, cert TLS, key rotation, multi-issuer policy hoặc revocation. Phải test bổ sung trong staging.

### 7.3. Chữ ký hợp lệ nhưng authority khác

Spring Security JWT converter mặc định thường lấy scope/scp thành GrantedAuthority có prefix SCOPE_. Vì vậy .hasAuthority("SCOPE_orders.read") chỉ cho JWT có scope orders.read đã verified. Nếu issuer có custom roles claim, cần cấu hình JwtAuthenticationConverter/ReactiveJwtAuthenticationConverterAdapter phù hợp **sau decoder**, không tự đọc raw roles trước xác thực.

Ví dụ API dùng user-subject làm khóa chủ thể nhưng không suy từ X-User. Nếu dữ liệu thật thuộc nhiều người/tenant, service cần kiểm tra owner/tenant trong DB; không thể dừng ở scope.

## 8. Kiểm tra với curl, log và DevTools

Khởi động demo:

~~~bash
gradle bootRun
~~~

Vì YAML chứa issuer.example.test (tên miền tài liệu), application có thể khởi động và public ping hoạt động, nhưng **token được phát từ IdP thật chỉ verify được sau khi deployment cấu hình JWKS/issuer/audience thật**.

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
~~~

Expected: ping 200 với JSON status=ok, /api/me không Bearer 401 và challenge Bearer.

Khi đã cấu hình IdP staging thực, gọi HTTPS API bằng **access token đã được cấp cho audience của API**:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.staging.example.org/api/me
~~~

Kết quả: token hợp lệ 200 subject tương ứng; sai chữ ký/issuer/audience/expired 401; JWT hợp lệ thiếu scope trên /api/orders 403. Không dán token thật trong bài báo cáo, shell history, logs hoặc screenshot. Không dùng curl -k để bỏ certificate verification trong production.

**Tránh endpoint /decode** trả raw claims trước xác minh. JWT payload ai có token cũng đọc được; một endpoint riêng không tạo thêm bảo mật mà có thể khiến đội vận hành nhầm dữ liệu chưa xác minh thành danh tính.

## 9. Các rủi ro production cần đánh giá thêm

### 9.1. Revocation

JWT hợp lệ chữ ký và exp vẫn có thể đã bị revoke bởi Authorization Server. Với xác minh JWT offline, Resource Server không tự biết thu hồi tức thời. Theo threat model, dùng TTL ngắn, token introspection/opaque token, revocation list hay stateful authorization checks. Chữ ký không tạo quyền vĩnh viễn.

### 9.2. HTTPS và Bearer token

Bearer token là credential: ai có thể dùng trong phạm vi được cấp. HTTPS/TLS có certificate verification là cần thiết; JWS signature không che payload hoặc ngăn kẻ nghe lén dùng token. Không gửi token qua URL query, logs, error pages, metrics hoặc tài nguyên công khai.

### 9.3. JWKS key rotation

Authorization Server có thể rotate signing keys với kid mới. Giữ endpoint JWKS ổn định, quản lý caching/refresh và theo dõi unknown kid. Không bỏ signature verification khi JWKS server lỗi. Với hệ nhiều issuers/tenants, phải kiểm soát issuer-to-keyset mapping riêng; không nạp key arbitrary từ token.

### 9.4. Type confusion và ID token

ID token của OIDC Client không tự là access token. Ngoài aud/iss/exp/nbf, dự án thật có thể cần typ=at+jwt, client_id/token_use hoặc validators theo RFC 9068 và hợp đồng issuer. Không tự tắt typ validation nếu không có phương án thay thế đúng. Nếu có nhiều token profiles cùng issuer, hãy xác định chính xác token nào được phép ở Resource Server.

### 9.5. Proxy và trusted headers

Một API gateway có thể đã verify token và chuyển X-User/X-Tenant xuống backend. Chỉ tin những headers này khi có **mTLS/network isolation/strip incoming headers và một trust contract rõ**; client Internet không được gửi headers cùng tên qua proxy mà thay được identity. Trong demo, backend tự verify JWT và bỏ qua X-User, tránh lớp trust phức tạp.

### 9.6. Không dùng JWE như JWS

JWS ký payload để bảo vệ integrity/authenticity nhưng không encrypt. JWE encrypt nhưng không tự chứng minh nguồn gốc issuer trong mọi cấu trúc; nếu phải có cả confidentiality và authenticity, dùng token profile nested signing/encryption theo tiêu chuẩn, không tự giải mã payload và nhận làm identity.

## 10. Lỗi thường gặp

| Sai lầm | Rủi ro | Sửa |
| --- | --- | --- |
| Decode JWT rồi đọc sub | Impersonation | ReactiveJwtDecoder + validators |
| Đọc X-User/X-Role để tạo Authentication | Client tự cấp quyền | Chỉ tin SecurityContext đã verify |
| Chỉ kiểm tra exp | Attacker tự đặt exp dài | Verify signature, issuer, audience |
| Chỉ kiểm tra signature | Token đúng key nhưng sai API | Validate aud/iss/type |
| Cho header jku quyết định JWKS URL | SSRF/key substitution | JWKS URI trusted config |
| Tin kid như URL | Attacker-key injection | kid chỉ chọn key trong trusted JWKS |
| Cho phép alg=none | Unsigned token accepted | Pin trusted JWS algorithms |
| Trộn HS256/RS256 không kiểm tra key type | Key confusion | Nimbus decoder, alg policy |
| Nhận ID token làm access token | Token type confusion | Audience/type validator |
| Lấy role từ raw payload | Privilege escalation | Authority conversion sau verify |
| JWT scope orders.read cho đọc mọi order | IDOR/cross tenant | Owner/tenant checks |
| Trả 200 với expired token | Replay | exp/nbf validators |
| Dùng fake Jwt principal rồi nói đã test signature | Ảo tưởng về test | RSA/JWKS test như trên |
| Bỏ qua key rotation | Outage hoặc trust policy lỗi | Trusted JWKS cache/rotation |
| Không dùng HTTPS | Lộ Bearer token | TLS, certificate verification |
| Log raw Authorization | Secret leak | Redaction |
| Tự block() trong WebFilter | Tắc Reactor event loop | Spring Security built-in |
| Fallback accept-all khi JWKS lỗi | Authentication bypass | Fail closed |
| Coi 401 bằng 403 | Client lỗi UX/authorization | Test status phân biệt |

## 11. Checklist code review

1. Resource Server dùng spring-boot-starter-oauth2-resource-server và oauth2ResourceServer.jwt, không có custom Base64URL-authentication filter.
2. Decoder xác minh RS256 với trusted JWKS/public keys; chỉ chấp nhận allowed algorithms.
3. Issuer được kiểm tra chính xác, audience của API bắt buộc, expiry/not-before đúng.
4. Required token profile/type đã được thiết kế, không chấp nhận ID/password-reset token.
5. Headers jku, x5u, kid không trở thành untrusted key source.
6. Không gán Authentication từ raw header, claim tự khai hoặc query parameters.
7. Scope/roles chuyển sang authorities sau xác minh; test 403 khi thiếu quyền.
8. Tenant/owner checks ở service/DB, không chỉ kiểm tra có sub.
9. Test 401 thiếu/sai signature/issuer/audience/expiry/alg none.
10. Test principal Alice không bị X-User admin thay thế.
11. Test JWKS rotation/unknown kid và timeout ở staging.
12. Không gửi Bearer qua HTTP công khai, URL query hay logs.
13. Đánh giá revocation và short token lifetime theo rủi ro.
14. Không đưa secrets/PII không cần thiết vào JWT payload.
15. Tách trust boundary giữa Authorization Server, Resource Server và OAuth2 Client.
16. Có metrics auth failure theo error category nhưng không leak token.
17. Quan sát proxy/WAF có strip/overwrite Authorization headers không.
18. Nếu có multiple SecurityWebFilterChain, kiểm tra matcher/order không tạo API bypass.

## 12. Câu hỏi tự kiểm tra và đáp án

1. Decode Base64URL có chứng minh JWT do issuer ký không? **Không.**
2. JWT có sub=admin và exp năm sau nhưng signature rỗng có phải user admin không? **Không, 401.**
3. JWT đúng chữ ký nhưng aud dành cho API khác thì sao? **401.**
4. JWT hợp lệ nhưng thiếu orders.read trên /api/orders thì sao? **403.**
5. JWT của Alice có thể bị X-User: admin thay đổi principal không? **Không.**
6. Vì sao không tin jku trong header? **Attacker có thể chỉ định JWKS độc hại hoặc SSRF.**
7. kid dùng để làm gì? **Chọn key trong trusted JWKS, không tự chọn issuer hoặc key source.**
8. Vì sao cần pin alg RS256? **Tránh alg none và algorithm confusion.**
9. ID token có thể dùng thay access token cho API không? **Không nếu không thỏa profile/audience và contract Resource Server.**
10. Có chữ ký đúng và scope đúng thì được đọc order của mọi user không? **Không, còn owner/tenant check.**
11. Vì sao dùng RSA ký thật trong test? **Để kiểm tra xác minh cryptographic, không chỉ authorization mock.**
12. Khi JWKS endpoint lỗi, có nên bỏ verify để API chạy không? **Không, fail closed.**
13. Expiry và revocation khác nhau thế nào? **Token chưa hết hạn vẫn có thể bị thu hồi; offline JWT không tự biết.**
14. JWT payload có được coi là bí mật vì encoded không? **Không, Base64URL không mã hóa.**
15. Principal nên lấy từ đâu? **Spring SecurityContext / @AuthenticationPrincipal sau verify.**
16. Một 403 khác 401 thế nào? **403 là quyền thiếu khi đã xác thực; 401 là thiếu/sai authentication.**

## 13. Tài liệu tra cứu

- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security Javadoc — NimbusReactiveJwtDecoder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- Spring Security Javadoc — JwtValidators: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html
- Spring Security — Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- OWASP JWT Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_Cheat_Sheet.html
- RFC 7515 (JWS): https://www.rfc-editor.org/rfc/rfc7515.html
- RFC 7519 (JWT): https://www.rfc-editor.org/rfc/rfc7519.html
- RFC 8725 (JWT Best Current Practices): https://www.rfc-editor.org/rfc/rfc8725.html
- RFC 9068 (JWT access token profile): https://www.rfc-editor.org/rfc/rfc9068.html
- RFC 6750 (OAuth Bearer): https://www.rfc-editor.org/rfc/rfc6750.html

**Kết luận:** Đọc được sub/roles trong payload **không đồng nghĩa đã xác thực**. Chỉ để Spring Security Resource Server đưa Jwt vào Reactor SecurityContext sau khi NimbusReactiveJwtDecoder xác minh chữ ký từ JWKS tin cậy, thuật toán, issuer, audience và thời hạn. Sau đó mới áp dụng scope, quyền nghiệp vụ và owner/tenant checks. Bộ WebTestClient ký RSA thật, kiểm tra các token giả mạo và phân biệt 401/403 là tiêu chí QA thiết thực khi ngăn các lỗi JWT authentication tự viết.