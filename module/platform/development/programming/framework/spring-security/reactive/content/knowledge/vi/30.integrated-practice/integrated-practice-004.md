# Xây dựng Resource Server JWT với kiểm tra issuer, audience và scope — Spring Security Reactive

## Mục tiêu và phạm vi

Bài thực hành xây dựng một **OAuth 2.0 Resource Server** trên Spring WebFlux với Java 17+, Spring Boot 3.x và Spring Security 6.x. API chỉ chấp nhận **JWT access token** khi đáp ứng đồng thời bốn điều kiện:

1. **Chữ ký và thời gian hợp lệ:** JWT được ký bằng khóa đáng tin cậy, thuật toán được cho phép, chưa hết hạn và đã đến thời điểm có hiệu lực.
2. **Issuer (claim `iss`) đúng:** token do đúng Authorization Server/Identity Provider đã được cấu hình phát hành.
3. **Audience (claim `aud`) phù hợp:** token được phát hành cho API này, ví dụ `api://orders`.
4. **Scope (claim `scope` hoặc `scp`) đủ:** token có đúng quyền `orders.read` cho GET và `orders.write` cho POST.

Bạn sẽ tạo hai endpoint, thiết lập xác thực và phân quyền, hiểu luồng Bearer token, chạy bộ kiểm thử JWT ký bằng RSA **thật trong bộ nhớ**, phân biệt lỗi 401/403, và nhận diện giới hạn của `mockJwt()`. Phần thực hành được thiết kế để học và chạy offline phần test, không cần đưa private key production vào ứng dụng.

## 1. Tư duy Resource Server: xác thực trước, phân quyền sau

~~~text
HTTP Authorization: Bearer <access token>
              |
              v
WebFlux SecurityWebFilterChain
              |
              v
ReactiveJwtDecoder
   +-- Phân tích JWT/JWS và alg/kid
   +-- Lấy public key đáng tin cậy từ JWK Set
   +-- Xác minh chữ ký
   +-- Xác thực exp, nbf, iss, aud
   |
   +-- Không hợp lệ --> 401 Unauthorized
              |
              v
JwtAuthenticationToken
   +-- Principal = Jwt, tên mặc định từ sub
   +-- scope/scp => GrantedAuthority "SCOPE_*"
              |
              v
authorizeExchange: hasAuthority(...)
   +-- Thiếu scope --> 403 Forbidden
              |
              v
Controller / service --> 200 OK hoặc 202 Accepted
~~~

`iss` trả lời **ai phát hành token**, `aud` trả lời **token được phát hành cho hệ thống nào**, `scope` trả lời **hệ thống nhận token cho phép hành động nào**. Hai token cùng issuer và chữ ký đều hợp lệ vẫn có thể phục vụ hai API khác nhau. Nếu bỏ kiểm tra audience, Resource Server có nguy cơ nhận nhầm token dành cho API khác; nếu bỏ kiểm tra scope, một token chỉ có quyền đọc có thể bị dùng để ghi.

Một JWT payload minh họa:

~~~json
{
  "iss": "https://idp.example.net/realms/training",
  "sub": "alice",
  "aud": ["api://orders"],
  "scope": "orders.read orders.write",
  "iat": 1760000000,
  "nbf": 1760000000,
  "exp": 1760003600
}
~~~

Các con số thời gian chỉ minh họa định dạng NumericDate, không phải token dùng được ở thời điểm hiện tại. Payload được mã hóa Base64URL **không đồng nghĩa được bảo vệ**; phải xác minh chữ ký của JWS bằng khóa tin cậy trước khi tin claims.

| Claim / trường | Kiểm tra và ý nghĩa |
| --- | --- |
| Header `alg` | Thuật toán JWS phải nằm trong allowlist, ví dụ RS256; tuyệt đối không tin `alg=none` |
| Header `kid` | Hỗ trợ tìm public key trong JWK Set, bản thân `kid` không tạo độ tin cậy |
| `iss` | So khớp issuer tin cậy, kể cả đường dẫn và dấu `/` cuối |
| `aud` | Danh sách đối tượng nhận token, phải chứa `api://orders` |
| `exp`, `nbf` | Hết hạn hoặc chưa có hiệu lực sẽ bị từ chối |
| `sub` | Định danh principal được controller truy cập qua `Jwt.getSubject()` |
| `scope` / `scp` | Chuyển thành authorities với tiền tố `SCOPE_` |
| `client_id` / `azp` | Không tự thay thế audience hoặc scope |

**Access Token và ID Token khác nhau.** ID Token OIDC xác thực sự kiện đăng nhập đối với OAuth client, thường có `aud` là client ID. Resource Server cần **access token dành cho API** của nó; đừng dùng ID Token chỉ vì ID Token cũng có định dạng JWT. Nếu provider yêu cầu JWT access token tuân RFC 9068, cần kiểm tra thêm token type/profile tương ứng.

## 2. Tạo dự án Java 17+ / Spring WebFlux

Trong dự án Spring Boot 3.x đã được thiết lập plugins Gradle và dependency management, khai báo ở `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot starter Resource Server cung cấp các thư viện OAuth2/JWT cần thiết. Khi quản lý dependencies thủ công, cần cả `spring-security-oauth2-resource-server` lẫn `spring-security-oauth2-jose` để decode và xác minh JWT.

Dùng **reactive API**: `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtDecoder` và `WebTestClient`. Các lớp `HttpSecurity`, `SecurityFilterChain`, `NimbusJwtDecoder` và `MockMvc` thuộc Servlet stack, không phải giải pháp tương ứng trong WebFlux.

## 3. Cấu hình issuer, audience và JWK Set

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp.example.net/realms/training"
          jwk-set-uri: "https://idp.example.net/realms/training/protocol/openid-connect/certs"
          audiences:
            - "api://orders"
~~~

**Các URL là ví dụ để thay bằng IdP thực tế.** Trước khi chạy ứng dụng với Bearer token do IdP phát hành, thay issuer và JWK Set URI theo tài liệu provider, cấp token đúng audience, bảo đảm API truy cập JWK Set qua HTTPS. Để chạy kiểm thử ở mục 8, không cần IdP thật vì test có decoder dùng key RSA trong bộ nhớ.

- `issuer-uri` xác định nguồn phát hành được tin cậy và giá trị `iss` hợp lệ. So khớp đầy đủ đường dẫn; issuer có hoặc không có dấu gạch chéo cuối có thể là hai giá trị khác nhau.
- `jwk-set-uri` xác định vị trí public keys để xác minh chữ ký. Khi khai báo cả `issuer-uri` và `jwk-set-uri`, Resource Server có thể tránh discovery metadata để tìm JWK URI khi khởi tạo mà **vẫn kiểm tra issuer**. Nếu chỉ có `issuer-uri`, framework có thể khám phá endpoint thông qua metadata phù hợp.
- `audiences` là thuộc tính có sẵn từ Spring Boot 3.3 cho cả Servlet lẫn reactive Resource Server. `aud` của token phải chứa `api://orders`. Token thiếu `aud` hoặc chỉ có `api://reports` không được xác thực.
- Kiểm tra mặc định dạng **contains** có nghĩa `aud=["api://orders","api://reports"]` vẫn được chấp nhận khi yêu cầu `api://orders`. Chính sách “chỉ một audience duy nhất” cần validator riêng, không suy diễn từ `contains`.

Các bước xác minh chữ ký phụ thuộc khóa công khai từ một nguồn đã tin cậy. Không đọc JWK Set URI tuỳ ý do token hoặc request cung cấp, không cho phép header JWT tự chọn nhà phát hành.

### Khi nào khai báo ReactiveJwtDecoder bean?

Chỉ cấu hình YAML trên đủ cho yêu cầu issuer + audience thông thường. Nếu cần custom claim policy, nhiều tenant có allowlist hoặc quy tắc audience đặc biệt, có thể thay auto-config bằng một `ReactiveJwtDecoder` bean tự xây:

~~~java
// Fragment tích hợp vào @Configuration với hai giá trị cấu hình:
// String issuer; String jwkSetUri;
@Bean
ReactiveJwtDecoder jwtDecoder() {
    NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri).build();

    OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains("api://orders")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error("invalid_token",
                                    "Wrong audience for orders API", null));

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            defaults, audienceValidator));
    return decoder;
}
~~~

Đây là **đoạn code minh họa để thay thế**, chưa phải một file Java chạy riêng: cần imports Spring Security, `issuer`/`jwkSetUri` được inject và `@Configuration`. Khi dùng `setJwtValidator` phải **ghép** kiểm tra mặc định (`JwtValidators.createDefaultWithIssuer` gồm thời gian và issuer) với kiểm tra audience. Nếu thay toàn bộ bằng audience validator, bạn có thể vô tình bỏ qua kiểm tra thời gian/issuer. Việc tự khai báo bean cũng thay thế cơ chế Boot tự tạo decoder, nên kiểm tra lại configuration khi deploy.

## 4. Cấu hình WebFlux Security để phân quyền theo scope

File `src/main/java/com/example/orders/OrdersApplication.java`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/orders/SecurityConfig.java`:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                // Chỉ áp dụng cho API stateless dùng Bearer header:
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders")
                            .hasAuthority("SCOPE_orders.write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Phân tích:

- `oauth2ResourceServer(...jwt(...))` bật xác thực Bearer JWT. Spring Security tạo Authentication từ JWT đã được decoder xác thực.
- `hasAuthority("SCOPE_orders.read")` yêu cầu đúng authority của scope đọc; POST yêu cầu `SCOPE_orders.write`.
- Mặc định `JwtGrantedAuthoritiesConverter` chuyển `scope="orders.read orders.write"` thành `SCOPE_orders.read` và `SCOPE_orders.write`; cũng hỗ trợ claim `scp` theo quy tắc mặc định.
- `hasRole("ADMIN")` dùng logic tiền tố `ROLE_`, **khác** scope. Không dùng role API để so khớp `SCOPE_orders.read`.
- `NoOpServerSecurityContextRepository` phù hợp với Bearer-only stateless API: mỗi request tự cung cấp Bearer token, không dùng WebSession để “nhớ” người dùng.
- CSRF chỉ tắt **vì đây là demo stateless không dựa cookie**. Nếu hệ thống phục vụ browser session/cookie bên cạnh Bearer, phải thiết kế CSRF riêng, không tắt đại trà.
- `anyExchange().denyAll()` giảm nguy cơ endpoint mới bị truy cập công khai ngoài dự kiến. Hãy mở đúng đường dẫn health/public nếu ứng dụng có yêu cầu vận hành.

File `src/main/java/com/example/orders/OrdersController.java`:

~~~java
package com.example.orders;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrdersController {
    public record OrderList(String owner, List<String> orderIds) {}

    @GetMapping("/api/orders")
    public Mono<OrderList> list(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(new OrderList(
                jwt.getSubject(), List.of("order-1001", "order-1002")));
    }

    @PostMapping("/api/orders")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Mono<Map<String, String>> create(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
                "status", "accepted", "owner", jwt.getSubject()));
    }
}
~~~

Controller nhận `Jwt` được Spring Security xác thực; `jwt.getSubject()` trả subject. Nội dung đơn hàng cố định chỉ để minh họa security, không phải code quản lý đơn hàng thực tế. Ở ứng dụng production cần kiểm tra cả tenant/ownership của từng đơn hàng, không suy ra “được đọc mọi đơn” chỉ vì có scope đọc. Với nhiều issuer, định danh người dùng thường cần cả issuer và subject.

## 5. Diễn giải 401, 403, 200 và 202

| Token và request | Decoder/authentication | Scope/authorization | Kết quả |
| --- | --- | --- | --- |
| Không có Bearer token | Không có principal | Chưa xét | **401 Unauthorized** |
| Chữ ký sai hoặc thuật toán không được phép | Không hợp lệ | Chưa xét | **401** |
| `exp` đã qua hoặc `nbf` chưa đến | Không hợp lệ | Chưa xét | **401** |
| Issuer khác `issuer-uri` | Không hợp lệ | Chưa xét | **401** |
| `aud` thiếu `api://orders` | Không hợp lệ | Chưa xét | **401** |
| JWT hợp lệ, có `orders.write` nhưng GET | Hợp lệ | Thiếu `orders.read` | **403 Forbidden** |
| JWT hợp lệ, có `orders.read` nhưng POST | Hợp lệ | Thiếu `orders.write` | **403** |
| JWT hợp lệ, có `orders.read` và GET | Hợp lệ | Đúng scope | **200 OK** |
| JWT hợp lệ, có `orders.write` và POST | Hợp lệ | Đúng scope | **202 Accepted** |

HTTP status trong bảng là kỳ vọng của security chain/controller ví dụ. Bên cạnh status, Bearer response có thể kèm `WWW-Authenticate` và thông tin `invalid_token` / `insufficient_scope` tùy handler. Không tự đổi mọi lỗi thành 403, cũng không trả HTTP 200 với payload báo thất bại nếu thực tế authentication không thành công.

## 6. Vì sao mockJwt() không đủ cho kiểm thử issuer và audience?

Spring Security test hỗ trợ `SecurityMockServerConfigurers.mockJwt()`:

~~~java
// Fragment đặt trong JUnit test đã cấu hình WebTestClient:
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.claim("sub", "alice")
                .claim("scope", "orders.read")))
      .get().uri("/api/orders")
      .exchange().expectStatus().isOk();
~~~

`mockJwt()` tạo Authentication giả, đặt vào SecurityContext của request. Nó **không** gọi `ReactiveJwtDecoder`, **không** tải JWK Set, **không** xác minh chữ ký, issuer, audience hoặc thời hạn. Đây là cách tốt để test mapping authority/controller, nhưng không chứng minh được tính hợp lệ của token thật. Mặc định, mock JWT có `sub=user` và `scope=read`; có thể sửa claims hoặc cấp authorities để test từng case.

Một bộ kiểm thử tốt cần cả:

- **Authorization tests:** sử dụng `mockJwt()` để kiểm tra GET/POST có scope đúng và thiếu scope.
- **Decoder/integration tests:** gửi Bearer token RS256 **được ký thật**, thử các giá trị `iss`, `aud`, `exp`, chữ ký khác nhau và quan sát Spring Security trả 401/403/2xx.

Bộ test sau thực hiện loại thứ hai; một test cuối chủ động chứng minh sự khác biệt với `mockJwt()`.

## 7. Kiểm thử end-to-end offline bằng JWT ký RSA thật

Không cần chạy IdP. Test tạo RSA KeyPair mới trong bộ nhớ, ký token bằng private key và tạo `NimbusReactiveJwtDecoder` dùng public key. Nó thay thế decoder auto-config của Boot **chỉ trong context test**, ghép kiểm tra mặc định cho issuer/timestamp và audience validator. Mỗi request Bearer phải đi qua actual WebFlux security filter/decoder.

File `src/test/java/com/example/orders/OrdersResourceServerTest.java`:

~~~java
package com.example.orders;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;

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
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@Import(OrdersResourceServerTest.LocalJwtTestConfig.class)
class OrdersResourceServerTest {
    private static final String ISSUER =
            "https://idp.example.net/realms/training";
    private static final String AUDIENCE = "api://orders";

    @Autowired
    ApplicationContext context;

    @Autowired
    KeyPair testKeys;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void absentBearerReturns401() {
        client.get().uri("/api/orders")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validSignatureIssuerAudienceAndReadScopeReturns200()
            throws Exception {
        String jwt = sign(testKeys.getPrivate(), ISSUER, AUDIENCE,
                "orders.read", Instant.now().plusSeconds(300));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("alice")
                .jsonPath("$.orderIds[0]").isEqualTo("order-1001");
    }

    @Test
    void differentIssuerReturns401() throws Exception {
        String jwt = sign(testKeys.getPrivate(),
                "https://other-issuer.example.net", AUDIENCE,
                "orders.read", Instant.now().plusSeconds(300));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void differentAudienceReturns401() throws Exception {
        String jwt = sign(testKeys.getPrivate(), ISSUER,
                "api://reports", "orders.read",
                Instant.now().plusSeconds(300));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void expiredTokenReturns401() throws Exception {
        // Quá hạn hơn 60 giây clock skew mặc định.
        String jwt = sign(testKeys.getPrivate(), ISSUER, AUDIENCE,
                "orders.read", Instant.now().minusSeconds(180));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void forgedSignatureReturns401() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair untrusted = generator.generateKeyPair();

        String jwt = sign(untrusted.getPrivate(), ISSUER, AUDIENCE,
                "orders.read", Instant.now().plusSeconds(300));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validTokenButWrongReadScopeReturns403() throws Exception {
        String jwt = sign(testKeys.getPrivate(), ISSUER, AUDIENCE,
                "orders.write", Instant.now().plusSeconds(300));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void validWriteScopeCanPost() throws Exception {
        String jwt = sign(testKeys.getPrivate(), ISSUER, AUDIENCE,
                "orders.write", Instant.now().plusSeconds(300));

        client.post().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isAccepted()
                .expectBody()
                .jsonPath("$.status").isEqualTo("accepted")
                .jsonPath("$.owner").isEqualTo("alice");
    }

    @Test
    void readScopeCannotPost() throws Exception {
        String jwt = sign(testKeys.getPrivate(), ISSUER, AUDIENCE,
                "orders.read", Instant.now().plusSeconds(300));

        client.post().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void mockJwtChecksScopeButDoesNotCheckIssuerOrAudience() {
        // iss và aud cố tình sai: vẫn 200 vì mockJwt bypass decoder.
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("iss", "https://other-issuer.example.net")
                    .claim("aud", List.of("api://reports"))
                    .claim("scope", "orders.read")))
                .get().uri("/api/orders")
                .exchange().expectStatus().isOk();
    }

    private String sign(
            PrivateKey privateKey, String issuer, String audience,
            String scope, Instant expiration) throws JOSEException {
        Instant now = Instant.now();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject("alice")
                .audience(List.of(audience))
                .issueTime(Date.from(now.minusSeconds(20)))
                .notBeforeTime(Date.from(now.minusSeconds(10)))
                .expirationTime(Date.from(expiration))
                .claim("scope", scope)
                .build();

        SignedJWT signed = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .type(JOSEObjectType.JWT).build(), claims);
        signed.sign(new RSASSASigner((RSAPrivateKey) privateKey));
        return signed.serialize();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class LocalJwtTestConfig {
        @Bean
        KeyPair testKeys() throws Exception {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        }

        @Bean
        @Primary
        ReactiveJwtDecoder testDecoder(KeyPair testKeys) {
            NimbusReactiveJwtDecoder decoder =
                    NimbusReactiveJwtDecoder.withPublicKey(
                            (RSAPublicKey) testKeys.getPublic()).build();

            OAuth2TokenValidator<Jwt> defaults =
                    JwtValidators.createDefaultWithIssuer(ISSUER);

            OAuth2TokenValidator<Jwt> audience = jwt ->
                    jwt.getAudience().contains(AUDIENCE)
                            ? OAuth2TokenValidatorResult.success()
                            : OAuth2TokenValidatorResult.failure(
                                    new OAuth2Error("invalid_token",
                                            "Wrong audience for orders API",
                                            null));

            decoder.setJwtValidator(
                    new DelegatingOAuth2TokenValidator<>(
                            defaults, audience));
            return decoder;
        }
    }
}
~~~

### Điều gì được kiểm chứng?

- `testKeys()` sinh khóa RSA ngay trong context kiểm thử, không lấy private key từ production.
- `sign(...)` sinh JWT JWS RS256 với `iss`, `aud`, `scope`, `exp`, `nbf` và chữ ký thật.
- `testDecoder(...)` chỉ dùng public key tương ứng; chữ ký từ khóa khác bị từ chối.
- `JwtValidators.createDefaultWithIssuer(ISSUER)` thực thi các kiểm tra JWT chuẩn cùng issuer; audience validator bổ sung bắt buộc `api://orders`.
- `@Import` đưa decoder test vào context, Boot sẽ không tạo decoder mặc định khi đã có bean; do vậy các test không truy cập JWK Set URI minh họa trong YAML.
- Các test dùng Bearer header đi qua filter, decoder rồi authorization. Test cuối dùng `mockJwt()` để **cho thấy riêng mock thì không chạy validation issuer/audience**.

File test này kiểm tra cả authentication và authorization của pipeline, thay vì gọi validator trực tiếp và giả định filter chain hoạt động đúng. Các khóa là dữ liệu thử nghiệm; **Resource Server production không được nhận private key của IdP**.

Chạy từ root dự án Gradle:

~~~bash
./gradlew test --tests 'com.example.orders.OrdersResourceServerTest'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.orders.OrdersResourceServerTest
~~~

Kỳ vọng khi đặt đúng file và dependencies: **10 tests PASS**. Đây là kết quả logic mong đợi của mẫu, cần thực sự chạy Gradle tại dự án để xác nhận triển khai. Chạy local tests không cần IdP; chạy ứng dụng với access token thật vẫn đòi issuer/JWK URI có thể truy cập được.

## 8. Thử HTTP với token của IdP thật

Để chạy `bootRun` thực tế, thay ba giá trị issuer/JWK Set/audience mẫu ở YAML bằng cấu hình đã được IdP cấp:

~~~bash
./gradlew bootRun
~~~

Lấy **access token** hợp lệ từ luồng OAuth2 phù hợp (ví dụ Authorization Code cho người dùng hoặc Client Credentials cho machine-to-machine, tùy nghiệp vụ). Token phải chứa issuer đúng, audience của API, scope phù hợp, chưa hết hạn và được ký bởi IdP mà Resource Server tin cậy.

Đặt access token vào biến môi trường `ACCESS_TOKEN` bằng cách an toàn của môi trường, không lưu vào source control. Dùng:

~~~bash
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
    http://localhost:8080/api/orders
~~~

Windows PowerShell:

~~~powershell
curl.exe -i -H "Authorization: Bearer $env:ACCESS_TOKEN" http://localhost:8080/api/orders
~~~

Để tạo đơn hàng thử, thay GET bằng POST và xin token có `orders.write`. Các URL `idp.example.net` không phải IdP hoạt động thật; khi chưa có provider, chạy bộ test RSA ở phần 7.

**Không dùng ID Token thay access token**, không copy JWT còn hạn vào log công khai. Một công cụ decode Base64 chỉ có thể đọc payload: nó không chứng minh chữ ký, issuer hay audience đã được kiểm tra.

## 9. Scope, scp và authorities

Spring Security mặc định ánh xạ scopes thành authorities theo tiền tố `SCOPE_`.

| Claim trong JWT | Kết quả cơ bản |
| --- | --- |
| `"scope": "orders.read"` | `SCOPE_orders.read` |
| `"scope": "orders.read orders.write"` | `SCOPE_orders.read` và `SCOPE_orders.write` |
| `"scp": ["orders.read","orders.write"]` | Hai authorities tương ứng |
| Thiếu cả `scope` và `scp` | Không có scope authorities tương ứng |
| `"roles": ["ADMIN"]` | Không tự sinh `ROLE_ADMIN` theo mặc định |

Nếu IdP dùng custom claim `permissions` hoặc scope có định dạng khác, cần cấu hình converter. Ví dụ **fragment** thay cách ánh xạ authorities (chỉ dùng nếu provider thực sự có claim `permissions`):

~~~java
JwtGrantedAuthoritiesConverter grants = new JwtGrantedAuthoritiesConverter();
grants.setAuthoritiesClaimName("permissions");
grants.setAuthorityPrefix("SCOPE_");

ReactiveJwtAuthenticationConverter converter =
        new ReactiveJwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(
        new ReactiveJwtGrantedAuthoritiesConverterAdapter(grants));

http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)));
~~~

Fragment này thuộc class cấu hình, cần imports của Spring Security và không phải file độc lập. **Authority converter không thay thế audience/issuer validator**. Nếu dùng custom converter, phải thêm test từ token thật và xác nhận scope thiếu vẫn bị 403.

## 10. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| 401 mặc dù token có chữ ký hợp lệ | Sai `iss`, sai `aud`, hết hạn hoặc chưa hiệu lực | So claim thực với cấu hình, kiểm tra timestamp |
| 401 sau đợt key rotation | JWK Set chưa có public key theo `kid` hoặc không truy cập được | Kiểm tra TLS, JWK endpoint, cache refresh |
| JWT dành cho API khác trả 200 | Chưa bật/đã vô hiệu audience validation | Cấu hình `audiences`; thêm test wrong audience |
| 403 khi Bearer token hợp lệ | Thiếu `SCOPE_orders.read`/`SCOPE_orders.write` | Kiểm tra `scope`/`scp`, mapping và policy |
| Tests `mockJwt()` đều pass nhưng token thật luôn 401 | Mock bypass signature/issuer/audience | Chạy kiểm thử RSA signed token và decoder thật |
| 403 cho POST | Thiếu write scope hoặc CSRF vẫn bật trong một ứng dụng dùng cookie | Kiểm tra authority/CSRF theo loại authentication |
| Chỉ đọc được ID Token từ IdP | Đang dùng nhầm loại token | Xin access token dành cho API resource |
| Decoder mới mất kiểm tra thời gian | `setJwtValidator` đã thay validators mặc định | Ghép `JwtValidators.createDefaultWithIssuer` với validator custom |
| API chấp nhận mọi đường dẫn | Rule `permitAll` quá rộng hoặc order matcher sai | Ghi rõ method + path; default deny |
| Log chứa đầy đủ access token | Log Authorization header hoặc claims nhạy cảm | Loại token khỏi log; dùng trace ID và error category |

Đừng “sửa” 401 bằng `permitAll()`, bỏ signature validation, bỏ audience, hoặc cho qua `alg=none`. Nếu token không đủ scope, không sửa bằng cách cho thêm mọi authority mà cần điều chỉnh cấp quyền ở IdP và quy tắc API có kiểm soát.

## 11. Những yêu cầu bổ sung khi triển khai thật

**Giới hạn thuật toán và trust.** Chỉ chấp nhận public keys đúng nhà phát hành, phù hợp RS256 hoặc tập thuật toán đã thống nhất. Không lấy JWK Set URL động từ JWT header (ví dụ dữ liệu không đáng tin cậy) và không cho token tự chọn issuer tùy ý. Với multi-tenant, dùng danh sách issuer hợp lệ và cơ chế chọn decoder an toàn.

**Thời hạn và đồng hồ.** Spring Security kiểm tra `exp` và `nbf`; cấu hình clock skew nhỏ nếu có lệch đồng hồ được dự báo. Không nới thời gian vô hạn hoặc bỏ validation chỉ để test tiện. Phần test đặt token hết hạn 180 giây trong quá khứ để vượt tolerance thông thường.

**Phân quyền nghiệp vụ.** `orders.read` cho phép vào endpoint, nhưng không tự xác nhận người gọi có quyền truy cập một đơn hàng cụ thể. Bổ sung ownership/tenant checks trong service. Với client credentials, `sub` có thể đại diện cho service/client thay vì người dùng cá nhân.

**Khả dụng IdP/JWK.** Việc refresh keys có thể cần gọi HTTP ngoài. Áp dụng timeout và cache policy phù hợp, quan sát lỗi JWK fetching, nhưng không được fail-open khi không thể xác minh chữ ký. Chuẩn bị cho key rotation và quy trình thu hồi token.

**Observability.** Phân biệt 401 (invalid token), 403 (insufficient authority) và lỗi upstream. Theo dõi tỷ lệ lỗi và latency có nhãn hữu hạn; không đưa raw tokens, email, user ID hoặc claim nhạy cảm thành metric labels.

**Test strategy.** Kiểm thử nhanh authorization bằng `mockJwt()`, integration bằng JWT ký thật và decoder, rồi kiểm thử staging với IdP thật để xác minh metadata/JWK/TLS/clock và cấu hình issuer/audience chính xác. Không coi bài test mock là bằng chứng crypto hoạt động.

## 12. Checklist hoàn thiện bài thực hành

- [ ] Dùng Spring WebFlux security chain, không pha Servlet API.
- [ ] Có `issuer-uri` đúng issuer của Authorization Server.
- [ ] Có JWK URI/trust key đúng và thuật toán được phép.
- [ ] Có `audiences` đúng tài nguyên `api://orders`.
- [ ] GET yêu cầu `SCOPE_orders.read`; POST yêu cầu `SCOPE_orders.write`.
- [ ] Không có token, sai chữ ký, sai issuer, sai audience, hết hạn -> 401.
- [ ] JWT hợp lệ nhưng thiếu scope -> 403.
- [ ] JWT hợp lệ với scope tương ứng -> 200 cho GET, 202 cho POST.
- [ ] Có test **JWT ký thật** chứ không chỉ `mockJwt()`.
- [ ] Có phân biệt ID Token và Access Token, không dùng token của API khác.
- [ ] Không để private key, access token hoặc claims nhạy cảm trong source/log.
- [ ] Có kế hoạch key rotation, timeout và kiểm tra ownership/tenant.

## Nguồn tham khảo chính thức

- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): cấu hình decoder, issuer, JWK Set, authorities, audience validator.
- [Spring Boot 3.3 — Security Resource Server](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): các thuộc tính `issuer-uri`, `jwk-set-uri`, `audiences` trong cả reactive và Servlet.
- [Spring Security — Testing OAuth 2.0 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()` và giới hạn của fixture.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf` và `sub`.
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): yêu cầu với JWT access tokens chuyên biệt.

Nguyên tắc cần ghi nhớ: **JWT hợp lệ về chữ ký chưa chắc được dùng cho API này**, và **JWT hợp lệ về issuer/audience chưa chắc được phép gọi mọi endpoint**. Xác thực, lựa chọn audience và phân quyền scope là ba cổng phải được thiết lập và kiểm chứng độc lập.