# Tạo resource server kiểm tra issuer và audience

## 1. Mục tiêu dự án

Trong dự án này, bạn xây dựng một REST API dùng Spring Security Resource Server để nhận JWT access token và chỉ chấp nhận token được phát hành bởi issuer tin cậy, còn hiệu lực và có audience dành cho API. Sau khi xác thực token, API tiếp tục kiểm tra scope trước khi cho phép thao tác.

Đây là bài thực hành trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là mô hình tin cậy giữa Authorization Server và Resource Server: resource server tin chữ ký từ khóa công khai được công bố bởi issuer đã cấu hình, xác minh claim issuer/audience/time, rồi mới dùng scope để phân quyền. Việc giải mã payload JWT bằng mắt hoặc chỉ kiểm tra một claim không đủ để xác thực token.

Sau dự án, bạn sẽ có một API với các hành vi:

- JWT có chữ ký hợp lệ, issuer đúng, audience đúng và còn hiệu lực: qua bước xác thực.
- JWT sai chữ ký, issuer sai, audience sai, hết hạn hoặc chưa đến thời điểm hiệu lực: bị từ chối với lỗi xác thực.
- JWT hợp lệ nhưng thiếu scope: bị từ chối ở bước phân quyền.
- JWT hợp lệ và đủ scope: được phép gọi endpoint tương ứng.

## 2. Kiến trúc và luồng tin cậy

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant A as Authorization Server
    participant R as Orders Resource Server
    participant J as JWKS Endpoint
    C->>A: OAuth authorization flow
    A-->>C: JWT access token
    C->>R: Request + Bearer token
    R->>J: Lấy public key theo kid (cache miss/refresh)
    J-->>R: JWKS public keys
    R->>R: Verify signature, issuer, exp, nbf, audience
    R->>R: Check scope / endpoint policy
    alt Token hợp lệ và đủ quyền
        R-->>C: 200 OK
    else Token không hợp lệ
        R-->>C: 401 Unauthorized
    else Token hợp lệ nhưng thiếu quyền
        R-->>C: 403 Forbidden
    end
~~~

| Thành phần | Trách nhiệm |
| --- | --- |
| Authorization Server (AS) | Xác thực client/user, áp dụng authorization policy và phát hành access token |
| JWT access token | Mang claims đã được issuer ký, gồm issuer, subject, audience, thời hạn và scope |
| JWKS endpoint | Công bố public keys để resource server xác minh chữ ký |
| Resource Server (RS) | Xác minh chữ ký/claims và quyết định quyền truy cập API |
| API client | Lấy token theo OAuth flow được cấp phép và gửi Bearer token tới đúng resource |

**Issuer** xác định bên phát hành token. Giá trị claim **iss** phải khớp chính xác issuer mà resource server tin cậy. **Audience** xác định resource server hoặc nhóm tài nguyên được phép nhận token. Một token có issuer đúng nhưng audience sai vẫn phải bị từ chối. Scope trả lời câu hỏi token được phép thực hiện hành động nào trong resource đã xác định.

## 3. Chuẩn bị môi trường

Yêu cầu:

- Java 17 trở lên.
- Maven hoặc Gradle.
- Spring Boot 3.x và Spring Security Resource Server tương thích.
- Một Authorization Server thử nghiệm có thể phát JWT access token và công bố metadata/JWKS, ví dụ Keycloak hoặc một OAuth/OIDC provider trong môi trường development.
- Giá trị issuer URI chính xác và audience mà API dự án sẽ chấp nhận.

Giá trị mẫu:

| Cấu hình | Giá trị |
| --- | --- |
| Issuer URI | **https://idp.example.test/realms/token-lab** |
| Audience | **orders-api** |
| Scope đọc | **orders.read** |
| Scope quản trị | **orders.admin** |
| API | **GET /api/orders**, **GET /api/admin** |

Hostname và giá trị trên chỉ là placeholder. Hãy thay bằng giá trị của Authorization Server thử nghiệm. Issuer URI phải giống claim **iss** trong access token, bao gồm scheme, hostname, path và dấu gạch chéo cuối nếu issuer công bố như vậy.

### 3.1 Tạo project Spring Boot

Tạo project có các dependency:

~~~text
Spring Web
Spring Security
OAuth2 Resource Server
Spring Boot Starter Test
Spring Security Test
~~~

Nếu dùng Maven, phần dependency chính có dạng:

~~~xml
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
~~~

Để Spring Boot BOM quản lý phiên bản tương thích; không trộn tùy ý các phiên bản Spring Security khác nhau.

Cấu trúc thư mục đề xuất:

~~~text
token-resource-server/
  src/
    main/
      java/com/example/tokenapi/
        TokenApiApplication.java
        config/SecurityConfig.java
        security/AudienceValidator.java
        web/ApiController.java
      resources/application.yml
    test/
      java/com/example/tokenapi/
        security/AudienceValidatorTest.java
        security/JwtDecoderIntegrationTest.java
        web/ApiAuthorizationTest.java
~~~

## 4. Cấu hình issuer và audience

Tạo file **application.yml**:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/token-lab

security:
  jwt:
    audience: orders-api
~~~

Spring Security dùng issuer URI để khám phá metadata và JWKS endpoint của Authorization Server. Resource server lấy public key phù hợp với **kid** trong JWT, xác minh chữ ký và áp dụng các validator mặc định. Ta sẽ bổ sung audience validator vì không được mặc định giả định rằng mọi cấu hình JWT decoder đều đã kiểm tra audience theo nhu cầu của API.

Giá trị **issuer-uri** là cấu hình tin cậy. Không lấy issuer từ header/body do API client gửi. Nếu issuer thay đổi, đó là thay đổi trust configuration cần được review và triển khai có kiểm soát.

## 5. Viết AudienceValidator

Tạo lớp **AudienceValidator.java**:

~~~java
package com.example.tokenapi.security;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class AudienceValidator implements OAuth2TokenValidator<Jwt> {
    private final String requiredAudience;

    public AudienceValidator(String requiredAudience) {
        if (requiredAudience == null || requiredAudience.isBlank()) {
            throw new IllegalArgumentException("Required audience must not be blank");
        }
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience() != null
                && jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "The required audience is missing",
                null);
        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

Validator này yêu cầu audience của JWT chứa chính xác giá trị **orders-api**. JWT có nhiều audience vẫn có thể hợp lệ nếu policy của API cho phép và danh sách có chứa audience cần thiết. Nếu hệ thống yêu cầu chỉ có một audience duy nhất, hãy bổ sung quy tắc đó một cách rõ ràng.

Không dùng so khớp substring trên chuỗi ghép, vì có thể nhận nhầm audience khác. **Jwt.getAudience()** trả danh sách audience đã được decoder parse theo cấu trúc JWT.

## 6. Cấu hình JwtDecoder kiểm tra issuer, thời hạn và audience

Tạo **SecurityConfig.java**:

~~~java
package com.example.tokenapi.config;

import com.example.tokenapi.security.AudienceValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    JwtDecoder jwtDecoder(Environment environment) {
        String issuerUri = environment.getRequiredProperty(
                "spring.security.oauth2.resourceserver.jwt.issuer-uri");
        String audience = environment.getRequiredProperty(
                "security.jwt.audience");

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuerUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTimeValidator =
                JwtValidators.createDefaultWithIssuer(issuerUri);
        OAuth2TokenValidator<Jwt> audienceValidator =
                new AudienceValidator(audience);

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                issuerAndTimeValidator,
                audienceValidator));

        return decoder;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_orders.admin")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**JwtValidators.createDefaultWithIssuer(issuerUri)** áp dụng các kiểm tra mặc định gồm issuer và thời gian hiệu lực như **exp/nbf**. **AudienceValidator** bổ sung điều kiện audience. **NimbusJwtDecoder** xác minh chữ ký bằng public key lấy từ issuer metadata/JWKS.

Trong ví dụ, CSRF được tắt vì API chỉ xác thực bằng Bearer token trong Authorization header và không dùng cookie/session authentication. Nếu ứng dụng đồng thời nhận credential tự động gửi bằng cookie, không áp dụng cấu hình này một cách máy móc; cần giữ CSRF defense phù hợp.

Mặc định Spring Security ánh xạ scope trong claim **scope** hoặc **scp** thành authority có tiền tố **SCOPE_**. Ví dụ **orders.read** thành **SCOPE_orders.read**. Nếu issuer có schema khác, phải cấu hình converter riêng và kiểm thử mapping.

## 7. Tạo endpoint được bảo vệ

Tạo **ApiController.java**:

~~~java
package com.example.tokenapi.web;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/orders")
    public Map<String, String> readOrders() {
        return Map.of(
                "resource", "orders-api",
                "result", "orders-read-allowed");
    }

    @GetMapping("/api/admin")
    public Map<String, String> readAdminData() {
        return Map.of(
                "resource", "orders-api",
                "result", "orders-admin-allowed");
    }
}
~~~

Endpoint **/api/orders** yêu cầu scope **orders.read**. Endpoint **/api/admin** yêu cầu scope **orders.admin**. Cả hai đều chịu sự kiểm tra issuer, thời hạn và audience trước khi đến bước scope authorization.

## 8. Cấu hình Authorization Server thử nghiệm

Trên Authorization Server, tạo client/resource phù hợp và cấu hình phát hành JWT access token. Cần bảo đảm:

- Issuer của token đúng với issuer URI trong resource server.
- JWT được ký bằng key mà public key tương ứng được công bố trong JWKS.
- Token có audience chứa **orders-api**.
- Token có scope **orders.read** hoặc **orders.admin** theo quyền được cấp.
- Token có **exp** và các thời điểm cần thiết.

Payload minh họa sau khi decode để quan sát:

~~~json
{
  "iss": "https://idp.example.test/realms/token-lab",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1795431000,
  "exp": 1795431300,
  "scope": "orders.read"
}
~~~

Payload này chỉ là ví dụ cấu trúc, không phải token có thể sử dụng. Decode JWT chỉ giúp quan sát claims; nó **không xác minh chữ ký**. Resource server phải xác minh chữ ký bằng public key tin cậy trước khi sử dụng claims.

Nếu Authorization Server không tự thêm audience tùy chỉnh, hãy cấu hình audience mapper/resource indicator theo khả năng của nhà cung cấp. Không sửa payload JWT sau khi phát hành; mọi thay đổi làm chữ ký không còn hợp lệ.

## 9. Chạy và gọi API

Khởi động resource server:

~~~bash
mvn spring-boot:run
~~~

Lấy access token từ Authorization Server thử nghiệm theo grant phù hợp với client. Không đặt client secret trong source code hoặc command history; dùng secret manager hoặc biến môi trường được bảo vệ. Sau đó gọi:

~~~bash
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER"
~~~

Kết quả mong đợi khi token hợp lệ, audience đúng và có scope đọc là **200 OK**.

Gọi endpoint admin bằng token chỉ có scope đọc:

~~~bash
curl -i http://localhost:8080/api/admin \
  -H "Authorization: Bearer ACCESS_TOKEN_WITH_ORDERS_READ"
~~~

Kết quả mong đợi là **403 Forbidden**. Token đã xác thực nhưng thiếu authority **SCOPE_orders.admin**.

Gọi API bằng token có issuer sai hoặc audience không chứa **orders-api** sẽ bị từ chối xác thực, thường là **401 Unauthorized**. Không dùng token thật trong ảnh chụp, log, ticket hoặc bài nộp.

## 10. Kiểm thử AudienceValidator

Tạo **AudienceValidatorTest.java** để kiểm tra logic audience độc lập:

~~~java
package com.example.tokenapi.security;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

class AudienceValidatorTest {
    private static final String AUDIENCE = "orders-api";
    private final AudienceValidator validator =
            new AudienceValidator(AUDIENCE);

    private Jwt jwtWithAudience(List<String> audiences) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("test-token")
                .header("alg", "RS256")
                .issuer("https://idp.example.test/realms/token-lab")
                .subject("user-123")
                .audience(audiences)
                .issuedAt(now.minusSeconds(1))
                .expiresAt(now.plusSeconds(300))
                .build();
    }

    @Test
    void acceptsTokenWithRequiredAudience() {
        assertFalse(validator.validate(
                jwtWithAudience(List.of("orders-api"))).hasErrors());
    }

    @Test
    void acceptsRequiredAudienceInAllowedAudienceList() {
        assertFalse(validator.validate(
                jwtWithAudience(List.of("inventory-api", "orders-api")))
                .hasErrors());
    }

    @Test
    void rejectsTokenWithDifferentAudience() {
        assertTrue(validator.validate(
                jwtWithAudience(List.of("billing-api"))).hasErrors());
    }
}
~~~

Các test này chỉ kiểm tra audience validator trên một đối tượng Jwt đã được tạo sẵn. Chúng **không kiểm tra chữ ký, issuer hoặc expiry**. Những kiểm tra đó thuộc trách nhiệm của decoder và cần được xác minh bằng test tích hợp ở bước tiếp theo.

## 11. Kiểm thử JwtDecoder bằng JWT ký thật trong test

Để chứng minh decoder thực sự xác minh chữ ký, issuer, audience và thời hạn, tạo một RSA key pair riêng trong test. Private key chỉ tồn tại trong test process; public key được dùng để cấu hình decoder. Không dùng signing key production.

Ví dụ **JwtDecoderIntegrationTest.java**:

~~~java
package com.example.tokenapi.security;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

class JwtDecoderIntegrationTest {
    private static final String ISSUER =
            "https://idp.example.test/realms/token-lab";
    private static final String AUDIENCE = "orders-api";

    private JwtEncoder encoder;
    private JwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair keyPair = generator.generateKeyPair();

        RSAKey signingJwk = new RSAKey.Builder(
                (RSAPublicKey) keyPair.getPublic())
            .privateKey((RSAPrivateKey) keyPair.getPrivate())
            .keyID("test-key")
            .build();

        var jwkSource = new ImmutableJWKSet<SecurityContext>(
                new JWKSet(signingJwk));
        encoder = new NimbusJwtEncoder(jwkSource);

        NimbusJwtDecoder nimbusDecoder = NimbusJwtDecoder
                .withPublicKey((RSAPublicKey) keyPair.getPublic())
                .signatureAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);
        OAuth2TokenValidator<Jwt> audience =
                new AudienceValidator(AUDIENCE);
        nimbusDecoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        decoder = nimbusDecoder;
    }

    private String issueToken(
            String issuer,
            List<String> audiences,
            Instant expiresAt) {
        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(issuer)
                .subject("user-123")
                .audience(audiences)
                .issuedAt(now.minusSeconds(1))
                .expiresAt(expiresAt)
                .claim("scope", "orders.read")
                .build();

        JwsHeader headers = JwsHeader
                .with(SignatureAlgorithm.RS256)
                .keyId("test-key")
                .build();
        return encoder.encode(
                JwtEncoderParameters.from(headers, claims))
                .getTokenValue();
    }

    @Test
    void acceptsSignedTokenWithExpectedIssuerAudienceAndExpiry() {
        String token = issueToken(
                ISSUER,
                List.of(AUDIENCE),
                Instant.now().plusSeconds(300));

        assertDoesNotThrow(() -> decoder.decode(token));
    }

    @Test
    void rejectsTokenWithModifiedSignature() {
        String token = issueToken(
                ISSUER,
                List.of(AUDIENCE),
                Instant.now().plusSeconds(300));
        int signatureStart = token.lastIndexOf('.') + 1;
        char replacement = token.charAt(signatureStart) == 'A' ? 'B' : 'A';
        String tamperedToken = token.substring(0, signatureStart)
                + replacement
                + token.substring(signatureStart + 1);

        assertThrows(JwtException.class, () -> decoder.decode(tamperedToken));
    }

    @Test
    void rejectsWrongIssuer() {
        String token = issueToken(
                "https://untrusted.example.test/issuer",
                List.of(AUDIENCE),
                Instant.now().plusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsWrongAudience() {
        String token = issueToken(
                ISSUER,
                List.of("billing-api"),
                Instant.now().plusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsExpiredToken() {
        String token = issueToken(
                ISSUER,
                List.of(AUDIENCE),
                Instant.now().minusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }
}
~~~

Test này dùng decoder với public key được biết trước để kiểm tra xác minh chữ ký và validator. Trong production, decoder dùng issuer discovery/JWKS như cấu hình ở phần 6; không hardcode public key của test vào ứng dụng. Bổ sung test chữ ký sai bằng cách ký token với một key pair khác và xác nhận decoder từ chối.

## 12. Kiểm thử scope ở HTTP layer

Spring Security Test cung cấp request post-processor **jwt()** để tạo Authentication giả lập. Nó hữu ích để kiểm tra endpoint authorization mà không cần gọi Authorization Server:

~~~java
@Test
void rejectsAdminEndpointWhenTokenOnlyHasReadScope() throws Exception {
    mockMvc.perform(get("/api/admin")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isForbidden());
}

@Test
void allowsOrdersEndpointWhenTokenHasReadScope() throws Exception {
    mockMvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());
}
~~~

**Lưu ý quan trọng:** **jwt()** tạo principal đã xác thực cho test và bỏ qua bước decode/verify JWT thực tế. Vì vậy, các test trên chỉ chứng minh quy tắc scope của endpoint. Chúng không chứng minh issuer, audience, signature hoặc expiry được kiểm tra. Dùng **JwtDecoderIntegrationTest** hoặc test HTTP với token ký thật để xác minh decoder; dùng **jwt()** cho authorization layer.

## 13. Kiểm thử end-to-end với Authorization Server

Sau khi unit và integration test cục bộ đạt, kết nối với Authorization Server thử nghiệm:

1. Đăng ký client phù hợp và cấp scope **orders.read**.
2. Cấu hình audience mapper để access token có **orders-api**.
3. Lấy token qua OAuth flow được phép.
4. Gọi **GET /api/orders**; kỳ vọng 200.
5. Lấy token có issuer đúng nhưng audience khác; gọi API và kỳ vọng 401.
6. Lấy token có audience đúng nhưng issuer khác; gọi API và kỳ vọng 401.
7. Lấy token hợp lệ nhưng chỉ có scope không liên quan; gọi API và kỳ vọng 403.
8. Chờ token hết hạn hoặc dùng fixture token expired; xác nhận API trả 401.
9. Xác minh resource server tải được JWKS và xử lý key rotation theo cache policy.

Khi tạo token âm, dùng client/realm thử nghiệm riêng. Không sửa token đã ký để thay issuer/audience vì chữ ký sẽ sai; nếu muốn cô lập riêng validator issuer/audience, dùng test ký thật như phần 11.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Mọi request đều 401 | Issuer URI sai, discovery/JWKS không truy cập được, signature/key không khớp | So sánh iss chính xác, kiểm tra TLS/network và JWKS kid |
| Token đúng issuer vẫn 401 | Audience thiếu hoặc sai | Xem aud của token test và cấu hình audience |
| Token đúng issuer/audience vẫn 401 | exp đã qua, nbf ở tương lai, clock skew hoặc chữ ký sai | Kiểm tra thời gian UTC, NTP và decoder error |
| Token hợp lệ nhưng 403 | Scope thiếu hoặc claim mapping sai | Kiểm tra granted scope và authority mapping |
| JWKS key mới không được nhận | Cache chưa refresh hoặc kid không tồn tại | Kiểm tra JWKS cache, key rotation và overlap |
| Test MockMvc pass nhưng production 401 | jwt() test đã bỏ qua decoder thật | Bổ sung decoder/integration test với JWT ký thật |
| Token ID token bị gửi đến API | Client nhầm ID token với access token | Chỉ dùng access token có audience của resource API |

Không ghi Authorization header hoặc raw JWT vào log để chẩn đoán. Có thể log correlation ID, issuer alias, audience alias, kid, reason code và status theo allowlist. Claim subject có thể là dữ liệu cá nhân; chỉ ghi khi thật sự cần và theo chính sách dữ liệu.

## 15. Tiêu chí hoàn thành dự án

- [ ] Project khởi động được với Spring Boot và Resource Server dependency.
- [ ] Resource server dùng issuer URI cấu hình cố định, tin cậy.
- [ ] JWT signature được xác minh bằng public key từ issuer/JWKS.
- [ ] Claim issuer được so khớp chính xác.
- [ ] Claim exp/nbf được kiểm tra.
- [ ] Audience phải chứa **orders-api**.
- [ ] Endpoint orders yêu cầu **SCOPE_orders.read**.
- [ ] Endpoint admin yêu cầu **SCOPE_orders.admin**.
- [ ] Token sai issuer, audience, chữ ký hoặc thời hạn bị từ chối.
- [ ] Token hợp lệ nhưng thiếu scope bị từ chối với 403 theo hợp đồng.
- [ ] Có unit test cho AudienceValidator.
- [ ] Có decoder integration test dùng JWT ký thật và RSA test key.
- [ ] Hiểu rõ jwt() MockMvc không kiểm tra decoder thật.
- [ ] Không ghi token/secret vào source control, log hoặc test report.

## Tài liệu tham khảo

- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** profile claim và cách sử dụng JWT access token.
- **RFC 7519 — JSON Web Token (JWT):** cấu trúc JWT và registered claims như iss, sub, aud, exp, nbf.
- **RFC 8725 — JSON Web Token Best Current Practices:** xác minh thuật toán, issuer, audience và các lưu ý bảo mật JWT.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** metadata discovery của Authorization Server.
- **RFC 8693 — OAuth 2.0 Token Exchange:** audience/resource và scope khi phát hành token cho service khác.
- **Spring Security Reference — OAuth 2.0 Resource Server JWT:** cấu hình issuer, JWKS, JwtDecoder và token validators.
- **Spring Security Reference — Testing OAuth 2.0:** kiểm thử authorization với MockMvc request post-processors.

Resource server chỉ nên chấp nhận JWT khi chữ ký được xác minh bằng key thuộc issuer tin cậy, issuer và audience đúng, thời hạn hợp lệ và scope đáp ứng endpoint policy. Dự án hoàn tất khi cả decoder test lẫn authorization test đều chứng minh được các ranh giới đó; một test principal giả lập không thay thế kiểm thử xác minh token thật.
