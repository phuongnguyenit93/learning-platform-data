# Giới hạn của token giả lập và kiểm thử thật JWT decoder, chữ ký, issuer, audience trong Spring Security WebFlux

## 1. Mục tiêu và bối cảnh

Bài này dành cho **Spring Security - reactive (WebFlux)**, ở mức kiểm thử chuyên sâu. Mục tiêu là phân biệt rõ các phép thử dùng danh tính giả lập với phép thử thật đường đi `Authorization: Bearer <JWT>` → bộ lọc bảo mật → `ReactiveJwtDecoder` → xác minh chữ ký/claims → ánh xạ quyền → quyết định truy cập.

Một JWT thường có dạng `header.payload.signature` (mỗi phần được mã hóa Base64URL). Đọc được JSON trong payload **không chứng minh** token đáng tin: ứng dụng phải xác minh chữ ký bằng khóa đáng tin, kiểm tra các ràng buộc thời gian (`exp`, `nbf`), nguồn phát hành (`iss`), đối tượng nhận (`aud`) và sau đó mới áp dụng chính sách quyền. Header như `alg`/`kid` là đầu vào cần kiểm tra theo cấu hình tin cậy; không tự cho phép thuật toán hoặc URL khóa chỉ vì token đề xuất.

Trong WebFlux, thành phần giải mã và xác thực JWT là **`ReactiveJwtDecoder`**. `JwtDecoder` thường gặp trong ví dụ Servlet/MVC là kiểu khác; không dùng nhầm khi viết bài kiểm thử reactive. Nếu ứng dụng dùng opaque token thay vì JWT, luồng xác thực tương ứng là `ReactiveOpaqueTokenIntrospector`, với kỹ thuật test khác.

## 2. `mockJwt()` chứng minh điều gì, và bỏ qua điều gì?

`SecurityMockServerConfigurers.mockJwt()` của `spring-security-test` gắn một `JwtAuthenticationToken` giả lập vào request thử nghiệm qua `WebTestClient`. Nó rất phù hợp để kiểm tra **authorization** và dữ liệu principal sau khi coi danh tính là đã xác thực. Tùy claims/scopes đã thiết lập, `mockJwt()` giúp thử HTTP 200/403, quyền `SCOPE_*`, các đường dẫn được bảo vệ và logic dùng JWT claims.

Tuy nhiên, `mockJwt()` **không đi qua quy trình phân tích chuỗi Bearer token, giải mã JWS và gọi `ReactiveJwtDecoder` thật**. Token giả lập có thể mang `alg: none`, chữ ký không tồn tại, issuer sai, audience sai hoặc thời gian hết hạn mà bài test vẫn xanh nếu quyền được cấp. Vì vậy:

| Cách kiểm thử | Đi qua decoder thật? | Kiểm tra chữ ký, `iss`, `aud`, thời hạn? | Phù hợp nhất |
| --- | --- | --- | --- |
| `mockJwt()` / `mockAuthentication()` | Không | Không | Quy tắc quyền, scope, principal, handler |
| Mock bean `ReactiveJwtDecoder` trả về `Jwt` có sẵn | Có gọi API decoder nhưng dùng kết quả giả | Không kiểm chứng thuật toán xác minh thật | Kiểm tra wiring, nhánh thành công/thất bại |
| `NimbusReactiveJwtDecoder` + JWT **thật được ký** bởi khóa test | Có | Có, nếu thiết lập đầy đủ validators | Chữ ký, issuer, audience, exp/nbf và HTTP 401/403 |
| JWT thật + HTTP JWKS/metadata giả lập có kiểm soát | Có, gồm truy xuất khóa | Có; thêm `kid`, JWKS, cache/rotation, lỗi mạng | Kiểm thử tích hợp gần môi trường triển khai |

**Nguyên tắc:** một bài test `mockJwt()` trả 200 không được dùng làm bằng chứng rằng resource server từ chối token bị sửa payload hoặc ký bằng khóa lạ.

## 3. Dựng ứng dụng WebFlux tối thiểu để kiểm thử

Ví dụ bên dưới dùng Java 17, Spring Boot 3.5.0 (họ Spring Security 6.x), Maven và JUnit 5. Các URL `.example.test` chỉ là giá trị minh họa; bài test ký JWT bên dưới tự dựng khóa và decoder trong bộ nhớ nên không cần IdP thật. Đặt các file theo đúng tên/đường dẫn đã ghi để chạy `mvn test`.

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jwt-reactive-tests</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
```

`spring-boot-starter-oauth2-resource-server` mang các thành phần Resource Server/JWT cần thiết; `spring-security-test` cung cấp `mockJwt()` và `springSecurity()`. Không thêm `spring-boot-starter-web` vào ví dụ này để giữ ngữ cảnh WebFlux.

**`src/main/java/example/securityreactive/ResourceServerApp.java`**:

```java
package example.securityreactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceServerApp {
    public static void main(String[] args) {
        SpringApplication.run(ResourceServerApp.class, args);
    }
}
```

**`src/main/java/example/securityreactive/SecurityConfig.java`**:

```java
package example.securityreactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/reports").hasAuthority("SCOPE_reports.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

**`src/main/java/example/securityreactive/ReportsController.java`**:

```java
package example.securityreactive;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {
    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("report:visible-to-reader");
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }
}
```

**`src/main/resources/application.yml`**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/tenant
          jwk-set-uri: https://issuer.example.test/tenant/jwks
          audiences:
            - reports-api
```

Trong môi trường thật, thay URL bằng endpoint đáng tin của IdP. `issuer-uri` quy định `iss` mong đợi; `jwk-set-uri` quy định nơi lấy khóa công khai để xác minh chữ ký; `audiences` yêu cầu `aud` chứa `reports-api`. Boot 3.5 hỗ trợ thuộc tính audience này cho cả servlet và reactive. Nếu tự khai báo bean `ReactiveJwtDecoder` thì phải **tự bảo đảm** issuer/audience/time validators thích hợp; cấu hình property không tự động “ghép” validators vào một bean tùy biến.

## 4. Lớp test thứ nhất: quyền truy cập bằng `mockJwt()`

**`src/test/java/example/securityreactive/MockJwtAuthorizationTest.java`**:

```java
package example.securityreactive;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class MockJwtAuthorizationTest {
    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void noAuthenticationReturns401() {
        client.get().uri("/reports").exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedWithoutRequiredScopeReturns403() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("scope", "profile.read")))
            .get().uri("/reports").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void expectedScopeReturns200() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("scope", "reports.read")))
            .get().uri("/reports").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:visible-to-reader");
    }

    @Test
    void fakeExpiredWrongIssuerAndAudienceCanStillPass() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                .claim("scope", "reports.read")
                .claim("iss", "https://attacker.example.test")
                .claim("aud", List.of("someone-else"))
                .claim("exp", Instant.now().minusSeconds(3600))))
            .get().uri("/reports").exchange()
            .expectStatus().isOk();
    }
}
```

Test cuối **cố ý** gửi các claims không hợp lệ nhưng vẫn kỳ vọng 200 để chứng minh ranh giới của mock: đối tượng authentication đã được dựng sẵn, không thực hiện kiểm chứng chữ ký/issuer/audience/thời hạn. Không lấy kết quả này làm chính sách cho production.

`mockJwt().jwt(...)` có thể thay `sub`, `scope`, `scp`, `iss` và các claim khác; `mockJwt().authorities(...)` có thể cấp thẳng danh sách authorities khi bài test chỉ tập trung vào quyền. Nếu cần kiểm tra converter ánh xạ quyền **thật** (đặc biệt converter tự viết), hãy có bài test riêng cho converter hoặc luồng token thật; gán authorities trực tiếp sẽ bỏ qua logic chuyển đổi đó.

## 5. Lớp test thứ hai: ký RSA thật, xác minh bằng decoder thật và gửi Bearer qua HTTP

Ví dụ kế tiếp tạo hai cặp khóa RSA trong bài test: một cặp **đáng tin**, một cặp **giả mạo**. Resource Server chỉ biết **public key** của cặp đáng tin; test dùng private key để ký compact JWT RS256 thật qua Nimbus JOSE. `NimbusReactiveJwtDecoder` thực hiện xác minh chữ ký thật và `DelegatingOAuth2TokenValidator` kết hợp chuẩn thời gian/issuer với audience tùy chỉnh.

Cấu hình khóa trong bộ nhớ giúp phép thử độc lập với IdP/JWKS qua mạng nhưng vẫn đi qua chuỗi **HTTP Bearer → SecurityWebFilterChain → ReactiveJwtDecoder → xác thực/ủy quyền**, khác hẳn `mockJwt()`.

**`src/test/java/example/securityreactive/SignedJwtHttpTest.java`**:

```java
package example.securityreactive;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(SignedJwtHttpTest.TestDecoderConfig.class)
class SignedJwtHttpTest {
    private static final String ISSUER = "https://issuer.example.test/tenant";
    private static final String AUDIENCE = "reports-api";
    private static final KeyPair TRUSTED = generateKeyPair();

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestDecoderConfig {
        @Bean
        ReactiveJwtDecoder reactiveJwtDecoderForTest() {
            NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
                .withPublicKey((RSAPublicKey) TRUSTED.getPublic())
                .build();

            OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

            OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience() != null && jwt.getAudience().contains(AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(new OAuth2Error(
                        "invalid_token", "Unexpected audience", null));

            decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audience));
            return decoder;
        }
    }

    @Test
    void acceptsValidSignedJwt() throws JOSEException {
        String jwt = sign(TRUSTED, ISSUER, AUDIENCE, "reports.read",
            Instant.now().minusSeconds(10), Instant.now().plusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:visible-to-reader");
    }

    @Test
    void rejectsJwtSignedByUnknownPrivateKey() throws JOSEException {
        String jwt = sign(generateKeyPair(), ISSUER, AUDIENCE, "reports.read",
            Instant.now().minusSeconds(10), Instant.now().plusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void rejectsWrongIssuer() throws JOSEException {
        String jwt = sign(TRUSTED, "https://evil.example.test", AUDIENCE,
            "reports.read", Instant.now().minusSeconds(10),
            Instant.now().plusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void rejectsWrongAudience() throws JOSEException {
        String jwt = sign(TRUSTED, ISSUER, "unrelated-service",
            "reports.read", Instant.now().minusSeconds(10),
            Instant.now().plusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void rejectsExpiredToken() throws JOSEException {
        String jwt = sign(TRUSTED, ISSUER, AUDIENCE, "reports.read",
            Instant.now().minusSeconds(1200),
            Instant.now().minusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void rejectsTokenNotYetValid() throws JOSEException {
        String jwt = sign(TRUSTED, ISSUER, AUDIENCE, "reports.read",
            Instant.now().plusSeconds(600),
            Instant.now().plusSeconds(1800));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validJwtWithInsufficientScopeReturns403() throws JOSEException {
        String jwt = sign(TRUSTED, ISSUER, AUDIENCE, "profile.read",
            Instant.now().minusSeconds(10), Instant.now().plusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void malformedBearerTokenReturns401() {
        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth("not.a.valid.jwt"))
            .exchange().expectStatus().isUnauthorized();
    }

    private static String sign(KeyPair signingKey, String issuer,
                               String audience, String scope,
                               Instant notBefore, Instant expiresAt)
            throws JOSEException {
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .audience(audience)
            .subject("alice")
            .claim("scope", scope)
            .issueTime(Date.from(Instant.now()))
            .notBeforeTime(Date.from(notBefore))
            .expirationTime(Date.from(expiresAt))
            .build();

        SignedJWT jwt = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                .type(JOSEObjectType.JWT).build(),
            claims);
        jwt.sign(new RSASSASigner(
            (RSAPrivateKey) signingKey.getPrivate()));
        return jwt.serialize();
    }

    private static KeyPair generateKeyPair() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
```

**Chạy thử** tại thư mục chứa `pom.xml`:

```bash
mvn test
```

Ở đây không giả định bất kỳ stdout đặc biệt nào của Maven vì log phụ thuộc môi trường; điều cần xác nhận là toàn bộ test hoàn tất thành công. Kỳ vọng về hành vi HTTP: token ký đúng + issuer/audience/thời gian/scope đúng → **200**; chữ ký sai/issuer sai/audience sai/hết hạn/chưa hiệu lực/token hỏng → **401**; token hợp lệ nhưng thiếu scope cần thiết → **403**. Bộ kiểm tra thời gian thường có clock skew mặc định khoảng 60 giây, nên các giá trị âm/dương 600 giây trong test tránh trường hợp sát ranh giới.

Trong ví dụ này, `@Import(TestDecoderConfig.class)` tạo decoder thật từ public key test và thay thế decoder tự cấu hình của Boot theo điều kiện bean. Vì vậy bài test xác minh cơ chế RSA và các validators được cài trong `TestDecoderConfig`, nhưng **không** xác minh khả năng tải JWK từ URL sản xuất. Private key chỉ nằm trong bài test để tạo dữ liệu; resource server bình thường không cần private key của IdP.

## 6. Kiểm thử JWKS, `kid`, thuật toán và issuer discovery sát thực tế hơn

Khi hệ thống dựa vào `issuer-uri`/`jwk-set-uri`, hãy bổ sung nhóm kiểm thử tích hợp với HTTP server giả lập nội bộ (ví dụ WireMock hoặc MockWebServer) **trả về JWK Set thật**:

1. Tạo cặp RSA dùng riêng cho test, xuất **public JWK** (gồm `kty`, `n`, `e`, `kid`, `alg` nếu cần) vào endpoint `/jwks`. Giữ private key chỉ ở test để ký JWT có header `kid` tương ứng.
2. Khởi động JWKS stub trên một cổng ngẫu nhiên. Xây decoder bằng `NimbusReactiveJwtDecoder.withJwkSetUri(stubJwksUrl).build()` và gắn `JwtValidators.createDefaultWithIssuer(issuer)` cùng audience validator. Nếu cần test discovery, phục vụ cả endpoint metadata hợp lệ, khai báo `jwks_uri`, rồi tạo decoder qua đường `issuer-uri`/issuer discovery.
3. Gửi Bearer JWT thật qua `WebTestClient`; kiểm tra token hợp lệ thành công. Thử `kid` không có trong JWKS, token ký bằng khóa không tin cậy, thuật toán ngoài danh sách cho phép, JWKS không truy cập được, JSON/JWK hỏng và key rotation theo cơ chế cache thực tế.
4. Khi kiểm tra rotation/cache, dùng cơ chế làm mới được hỗ trợ hoặc điều khiển đồng hồ/cache để tránh test phụ thuộc timing ngẫu nhiên. Kiểm tra key cũ bị loại khi chính sách yêu cầu, key mới được chấp nhận sau khi tải lại. Không mặc định rằng mỗi request đều lấy lại JWKS.
5. Khóa tiêu chí tin cậy ở cấu hình ứng dụng. Không tải khóa tùy ý từ `jku` hoặc `x5u` trong JWT do client gửi; không mặc nhiên tin mọi giá trị `alg`. `alg: none` hay chuyển sang khóa đối xứng ngoài chính sách phải bị từ chối.

Test với `withPublicKey(...)` (mục 5) và test với `withJwkSetUri(...)` bổ trợ nhau: nhóm đầu ổn định, nhanh, tách mạng; nhóm sau kiểm chứng khả năng phân phối/chọn khóa, metadata và những hỏng hóc có thể xảy ra trên đường mạng.

## 7. Bảng ca kiểm thử tối thiểu

| Trường hợp | Kết quả khi request `/reports` | Điều được kiểm chứng |
| --- | --- | --- |
| Không có Bearer | 401 | Chưa xác thực |
| JWT hợp lệ + `scope=reports.read` | 200 | Xác thực và phân quyền thành công |
| JWT hợp lệ nhưng thiếu `reports.read` | 403 | Phân quyền sau xác thực |
| Sửa payload sau khi ký | 401 | Dấu ký không còn khớp nội dung |
| Ký bằng private key không tin cậy | 401 | Trust anchor/public key |
| `alg` không được tin cậy hoặc token không ký | 401 | Chính sách thuật toán/ký |
| `iss` khác chính xác giá trị đã cấu hình | 401 | Issuer validator |
| `aud` thiếu hoặc không chứa audience của API | 401 | Audience validator |
| `exp` đã qua (vượt clock skew) | 401 | Expiration validator |
| `nbf` ở tương lai (vượt clock skew) | 401 | Not-before validator |
| JWT sai cấu trúc/không parse được | 401 | Xử lý Bearer không hợp lệ |
| `kid` không khớp khóa trong JWKS | 401 | Chọn khóa từ JWKS |
| IdP/JWKS không phản hồi | Phải từ chối xác thực, kiểm tra status/error thực tế | Không fail-open khi xác minh không thể hoàn tất |

Các dòng về chữ ký/issuer/audience chỉ có ý nghĩa khi chạy bằng **decoder thật**. Nếu policy cần nhiều audience, trường `aud` có thể là danh sách: kiểm tra **chứa** audience mục tiêu, không đánh đồng `aud` với `scope`. `iss` phải đúng issuer mà ứng dụng tin cậy (kể cả đường dẫn tenant, theo cấu hình), không chỉ so sánh hostname. Với token chưa xác thực, thường là **401**; token xác thực hợp lệ nhưng không đủ quyền, thường là **403**.

## 8. Lỗi phổ biến và cách phòng tránh

- **Chỉ dùng `mockJwt()` để tuyên bố “JWT an toàn”.** Sửa bằng nhóm signed-token test, đặc biệt kiểm chữ ký sai, issuer sai, audience sai, exp/nbf.
- **Chỉ Base64-decode payload rồi kiểm tra claim.** Điều này không xác minh nguồn phát hành hay tính toàn vẹn. Luôn dùng decoder/JWS verifier đáng tin.
- **Kiểm `iss` nhưng quên `aud`.** Token từ cùng IdP nhưng phát cho dịch vụ khác có thể bị nhận nhầm. Cấu hình `spring.security.oauth2.resourceserver.jwt.audiences` nếu dùng Boot auto-config, hoặc thêm audience validator khi tự dựng bean.
- **Viết bean `ReactiveJwtDecoder` tùy biến và làm mất validators mặc định.** Gắn `JwtValidators.createDefaultWithIssuer(...)` và audience validator theo nhu cầu; kiểm lại các quy tắc timestamp/clock skew.
- **Dùng `JwtDecoder` kiểu Servlet trong WebFlux.** Với reactive resource server, injection và cấu hình nên dùng `ReactiveJwtDecoder` cùng `SecurityWebFilterChain`.
- **Gắn authorities trực tiếp trong mock rồi tưởng đã test converter.** Thử ánh xạ `scope`/`scp` qua token thật hoặc test converter độc lập; authorities giả lập không chứng minh mapping từ JWT.
- **Nhầm 401 với 403.** 401 thường nghĩa là không xác thực được; 403 có nghĩa là danh tính hợp lệ nhưng không có quyền yêu cầu.
- **Dùng các thời điểm sát hiện tại trong test exp/nbf.** Dễ bị clock skew hoặc tốc độ CI làm test chập chờn; dùng đồng hồ giả lập hoặc khoảng cách đủ lớn.
- **Phụ thuộc IdP bên ngoài khi chạy unit/integration test thường xuyên.** Dùng khóa và JWKS stub riêng cho test; dành E2E có IdP thật cho môi trường và lịch chạy được kiểm soát.
- **Cho JWT chỉ định trực tiếp trust source/alg.** Hãy giới hạn thuật toán và public keys theo cấu hình server, kiểm sự kiện rotation, không tin URL khóa của bên gửi.
- **Ghi log token thật, private key hoặc chi tiết nhạy cảm khi test fail.** Trong CI chỉ ghi nguyên nhân/nhóm lỗi đủ chẩn đoán; tránh rò rỉ credentials.
- **Chạy WebTestClient qua một server HTTP thật rồi nghĩ `mockJwt()` luôn can thiệp được vào server đó.** `mockJwt()` được thiết kế cho WebFlux mock-server test support; với HTTP server thật cần gửi header `Authorization: Bearer <token>` và cấu hình decoder tương ứng.

## 9. Quy trình chọn loại test khi phát triển

Bắt đầu từ quy tắc endpoint: dùng `mockJwt()` để mô tả rõ các nhóm người dùng/scope được hoặc bị từ chối. Tiếp theo, dùng JWT RS256 thật có issuer, audience, exp/nbf chủ động để đảm bảo chuỗi xác thực không thể bị lừa bằng token giả. Cuối cùng, nếu môi trường triển khai dùng JWKS/issuer discovery, bổ sung stub HTTP để xác minh lựa chọn `kid`, thuật toán, rotation và lỗi mạng. Mỗi lỗi phát hiện được ở lớp nào thì sửa nguyên nhân tại lớp đó; không thay `ReactiveJwtDecoder` thật bằng mock trong một bài test được đặt mục tiêu kiểm chứng chữ ký.

**Tài liệu tham khảo chính thức:**
- Spring Security — Testing OAuth 2.0 for WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security — Reactive OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Boot 3.5 — Resource Server properties and audience configuration: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
