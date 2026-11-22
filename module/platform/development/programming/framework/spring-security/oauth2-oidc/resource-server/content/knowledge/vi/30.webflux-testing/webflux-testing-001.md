# WebTestClient với SecurityWebFilterChain

Trong ứng dụng Spring WebFlux, **WebTestClient** giúp kiểm thử HTTP endpoints theo cách reactive, còn **SecurityWebFilterChain** là nơi Spring Security áp dụng authentication, authorization, CSRF và các WebFilter bảo mật cho request. Khi kiểm thử Resource Server, cần bảo đảm request đi qua đúng security chain và quan sát được kết quả ở HTTP boundary.

Một test WebFlux có thể kiểm tra nhiều lớp:

- Không có credential: endpoint được bảo vệ trả `401 Unauthorized`.
- Đã xác thực nhưng thiếu authority/scope: trả `403 Forbidden`.
- JWT có scope phù hợp: request được phép qua security chain.
- Route public: được phép truy cập theo policy.
- POST/PUT/DELETE: tuân theo CSRF policy của ứng dụng.
- JWT sai chữ ký, issuer, audience hoặc hết hạn: decoder thực từ chối token.
- Custom converter, method security và nhiều security chains: hoạt động đúng với request thực tế.

Điểm cần phân biệt: **test helper như `mockJwt()` tạo một authentication giả lập để kiểm tra authorization; nó không chứng minh `ReactiveJwtDecoder` đã xác minh chữ ký JWT**. Khi cần kiểm tra token validation, phải gửi Bearer token có chữ ký thật qua filter chain và để decoder thật xử lý.

Bài học thuộc chương **Kiểm thử WebFlux** trong module **Spring Security OAuth 2.0 OIDC Resource Server**. Các ví dụ sử dụng Spring Security reactive stack và JUnit 5. Tên API/annotation cụ thể có thể khác giữa các phiên bản Spring Boot/Spring Security; cần dùng dependency version của dự án.

## 1. Vai trò của WebTestClient và SecurityWebFilterChain

WebFlux dùng reactive pipeline dựa trên `Publisher`/`Mono`/`Flux`. Security được áp dụng bằng `WebFilter` và `SecurityWebFilterChain`, không phải Servlet `FilterChainProxy`/`SecurityFilterChain` của Spring MVC.

~~~text
WebTestClient
     |
     v
HTTP request / exchange
     |
     v
WebFlux WebHandler
     |
     v
WebFilter chain
     |
     +--> SecurityWebFilterChain
     |       |
     |       +--> SecurityContext
     |       +--> Authentication
     |       +--> Authorization
     |       +--> CSRF / exception handling
     |
     v
RouterFunction / Controller
     |
     v
HTTP response
~~~

`WebTestClient` có thể bind trực tiếp với controller, application context hoặc một server đang chạy. Cách bind quyết định mức độ tích hợp được kiểm thử:

| Cách bind | Phạm vi | Khi phù hợp |
|---|---|---|
| `bindToController(...)` | Controller/WebFlux handler được chọn | Test HTTP mapping/handler đơn giản; phải tự cấu hình những filter cần thiết |
| `bindToRouterFunction(...)` | RouterFunction và handler tương ứng | Test functional endpoints |
| `bindToApplicationContext(...)` | WebFlux application context và filter beans | Test security chain cùng application wiring trong môi trường mock server |
| `bindToServer()` | HTTP server đang chạy | Test end-to-end qua network boundary |
| Spring Boot `@SpringBootTest` + `@AutoConfigureWebTestClient` | Ứng dụng được khởi chạy theo test context | Integration test gần production hơn |

Nếu mục tiêu là kiểm thử `SecurityWebFilterChain`, một controller-only client không tự bảo đảm đã cài security filters. Dùng application context binding với `springSecurity()` hoặc để Spring Boot cấu hình test client qua ứng dụng thật.

## 2. Dependencies cho WebFlux security tests

Với Spring Boot, dependency chính:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và các test utilities thường dùng. `spring-security-test` cung cấp reactive test support như `mockUser()`, `mockJwt()`, `mockAuthentication()` và `csrf()`.

Không cần thêm Spring MVC starter cho một ứng dụng WebFlux thuần chỉ để dùng `WebTestClient`. Trộn `spring-boot-starter-web` và `spring-boot-starter-webflux` có thể khiến Boot chọn application type Servlet tùy classpath/configuration; hãy xác định rõ ứng dụng đang chạy reactive hay Servlet.

## 3. Cấu hình SecurityWebFilterChain được kiểm thử

Ví dụ Resource Server bảo vệ Orders API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableReactiveMethodSecurity
class OrdersSecurityConfiguration {

    @Bean
    SecurityWebFilterChain ordersSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Trong cấu hình này:

- `permitAll()` cho route public.
- GET Orders yêu cầu authority `SCOPE_orders.read`.
- POST Orders yêu cầu `SCOPE_orders.write`.
- Những request còn lại phải được xác thực.
- `oauth2ResourceServer().jwt()` cấu hình Bearer JWT authentication qua reactive decoder.
- `@EnableReactiveMethodSecurity` bật method-level authorization cho reactive stack nếu ứng dụng dùng `@PreAuthorize`/các annotation method security.

### 3.1. CSRF policy cần được quyết định rõ

WebFlux security bật CSRF protection theo mặc định. Với API chỉ nhận access token qua Authorization header và không dùng cookie/session tự động gửi kèm, ứng dụng có thể chủ động disable CSRF:

~~~java
return http
    .csrf(ServerHttpSecurity.CsrfSpec::disable)
    .authorizeExchange(...)
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
    .build();
~~~

Chỉ disable khi mô hình authentication thực sự là stateless bearer-token và không dựa vào browser cookies để tự động xác thực. Nếu ứng dụng dùng session cookie/OAuth2 Login hoặc cookie-based authentication, CSRF protection có thể vẫn cần thiết. Trong trường hợp đó, POST test phải gửi CSRF token hợp lệ.

### 3.2. Controller reactive để test

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
class OrdersController {

    @GetMapping("/{id}")
    Mono<OrderResponse> findById(@PathVariable String id) {
        if ("missing".equals(id)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found"));
        }
        return Mono.just(new OrderResponse(id, "CREATED"));
    }

    @PostMapping
    Mono<OrderResponse> create(@RequestBody CreateOrderRequest request) {
        return Mono.just(new OrderResponse("order-100", "CREATED"));
    }
}

record OrderResponse(String id, String status) {}
record CreateOrderRequest(String sku, int quantity) {}
~~~

Controller chỉ là ví dụ tối giản để thể hiện security boundary. Trong ứng dụng thực, handler có thể gọi service reactive và trả `Mono`/`Flux`; `WebTestClient` sẽ subscribe và kiểm tra response mà không cần gọi `.block()` trong code production.

## 4. Hai cách khởi tạo WebTestClient có Security

### 4.1. Spring Boot integration test với server ngẫu nhiên

Khi cần kiểm tra application thật qua HTTP server:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OrdersHttpIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publicEndpointIsAccessible() {
        webTestClient.get()
            .uri("/public/health")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

`RANDOM_PORT` khởi chạy server thật trên một cổng ngẫu nhiên. `WebTestClient` gửi request qua network stack; test bao phủ server startup, routing, WebFilters, security chain và response handling. Cách này chậm hơn mock application context nhưng có giá trị khi cần kiểm tra cấu hình tích hợp thực tế.

Nếu ứng dụng yêu cầu issuer/JWKS endpoint trong lúc startup, test cần cấu hình test issuer/decoder phù hợp để không phụ thuộc mạng bên ngoài. Phần kiểm thử token thật sẽ trình bày ở dưới.

### 4.2. Bind vào application context và cài Spring Security

Nếu không cần mở server TCP:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OrdersApplicationContextTest {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient webTestClient;

    @BeforeEach
    void setUp() {
        webTestClient = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicEndpointIsAccessible() {
        webTestClient.get()
            .uri("/public/health")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

`springSecurity()` thêm integration cần thiết để security filters trong application context được áp dụng khi WebTestClient xử lý request. Nếu bỏ bước này, test có thể chạy handler mà không đi qua đúng security chain, dẫn tới kết quả bảo mật sai lệch.

### 4.3. Không dùng bindToController rồi kết luận đã test security chain

Ví dụ:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new OrdersController())
    .build();
~~~

Client này hữu ích cho controller-only test. Nhưng nếu không cài `SecurityWebFilterChain`/security filters, nó không chứng minh endpoint được bảo vệ bởi cấu hình ứng dụng. Khi test `SecurityWebFilterChain`, hãy dùng application context hoặc Boot integration test.

## 5. Dùng mockJwt() để kiểm tra authorization

Với Resource Server JWT, `mockJwt()` là test helper tiện lợi để tạo một `JwtAuthenticationToken` giả lập cho request. Nó cho phép kiểm tra path rules và scope authorities mà không cần gọi Authorization Server hoặc xác minh chữ ký.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest
class OrdersAuthorizationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void ordersReadScopeCanReadOrder() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("scope", "orders.read")))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("42")
            .jsonPath("$.status").isEqualTo("CREATED");
    }

    @Test
    void ordersWriteScopeCannotReadOrder() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("scope", "orders.write")))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Spring Security's default JWT authority converter maps a space-delimited `scope` claim to authorities prefixed with `SCOPE_`. Vì vậy `scope=orders.read` tạo authority `SCOPE_orders.read` theo cấu hình mặc định. Nếu ứng dụng dùng custom `JwtAuthenticationConverter`, test phải phản ánh mapping thực tế.

### 5.1. Tạo nhiều scopes trong mock JWT

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("scope", "orders.read orders.write")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Giá trị `scope` trong OAuth access token thường là chuỗi các scope phân tách bằng dấu cách. Test helper dùng claims giả lập; không cần một JWT compact có chữ ký cho mục tiêu authorization-only này.

### 5.2. Cấu hình authorities trực tiếp

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Cách này cho test kiểm soát chính xác authorities được gắn vào authentication. Nó **không kiểm tra** `scope`/`scp` claim được converter chuyển thành authority ra sao. Hãy chọn claim-based hoặc authority-based tùy lớp cần kiểm thử.

### 5.3. Mock JWT có thể gắn subject và issuer

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .subject("alice")
        .issuer("https://login.example.test")
        .claim("aud", "orders-api")
        .claim("scope", "orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Những claims này hữu ích cho controller/method-security tests. Tuy nhiên `mockJwt()` không xác minh rằng issuer, audience hoặc chữ ký thực sự được decoder chấp nhận. Không dùng test này làm bằng chứng JWT validation đang hoạt động.

## 6. Kiểm tra 401, 403 và endpoint public

Một bộ test security cơ bản nên phân biệt ba trường hợp:

| Request | Authentication | Authority | Kết quả thường mong đợi |
|---|---|---|---|
| GET `/public/health` | Không cần | Không cần | 200 |
| GET `/api/orders/42` không có token | Chưa xác thực | Không có | 401 |
| GET `/api/orders/42` có token hợp lệ nhưng thiếu `orders.read` | Đã xác thực | Thiếu scope | 403 |
| GET `/api/orders/42` có token và `orders.read` | Đã xác thực | Đủ scope | 200 |

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest
class OrdersSecurityStatusTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publicEndpointDoesNotRequireAuthentication() {
        webTestClient.get()
            .uri("/public/health")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void protectedEndpointRequiresAuthentication() {
        webTestClient.get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedPrincipalWithoutRequiredScopeIsForbidden() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("scope", "profile.read")))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void authenticatedPrincipalWithRequiredScopeIsAllowed() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("scope", "orders.read")))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Không có token trên protected endpoint thường dẫn đến 401 vì Resource Server yêu cầu authentication. Token hợp lệ nhưng thiếu authority thường dẫn đến 403. Exception handling tùy cấu hình có thể thay đổi response body, nhưng không nên biến thiếu quyền thành một request thành công.

### 6.1. Dùng mockUser() cho ứng dụng có UserDetails authentication

`mockUser()` tạo một user authentication giả lập. Nó phù hợp khi test authorization rules chung hoặc ứng dụng có form login/basic/session authentication:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

webTestClient
    .mutateWith(mockUser().roles("ADMIN"))
    .get()
    .uri("/admin/report")
    .exchange()
    .expectStatus().isOk();
~~~

`mockUser()` không tạo `JwtAuthenticationToken` và không kiểm tra Resource Server JWT flow. Nếu endpoint yêu cầu `SCOPE_orders.read`, dùng `mockJwt()` hoặc một authentication fixture có đúng authority.

### 6.2. Dùng mockAuthentication() khi cần principal tùy chỉnh

`mockAuthentication()` cho phép cài một `Authentication` giả lập vào request. Ví dụ này hữu ích khi kiểm thử principal tùy biến hoặc một loại authentication không phải JWT:

~~~java
import org.springframework.security.authentication.TestingAuthenticationToken;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockAuthentication;

var authentication = new TestingAuthenticationToken(
    "alice", "not-a-real-credential", "SCOPE_orders.read");
authentication.setAuthenticated(true);

webTestClient
    .mutateWith(mockAuthentication(authentication))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Đây là test principal đã được xác thực giả lập. Không dùng `TestingAuthenticationToken` như cơ chế authentication trong production và không xem test này là bằng chứng chữ ký JWT được xác minh.

## 7. Kiểm thử CSRF với WebTestClient

Nếu `SecurityWebFilterChain` giữ CSRF protection, một POST không có CSRF token có thể bị từ chối ngay cả khi request đã có authentication. Điều này đặc biệt quan trọng với cookie/session-based browser applications.

### 7.1. POST không có CSRF token

~~~java
@Test
void postWithoutCsrfTokenIsRejectedWhenCsrfIsEnabled() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt ->
            jwt.claim("scope", "orders.write")))
        .post()
        .uri("/api/orders")
        .bodyValue(new CreateOrderRequest("sku-123", 2))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Test này giả định CSRF đang bật và không có custom CSRF repository/exception handler làm thay đổi chi tiết response.

### 7.2. POST với CSRF token

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@Test
void postWithCsrfTokenAndWriteScopeIsAllowed() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt ->
            jwt.claim("scope", "orders.write")))
        .mutateWith(csrf())
        .post()
        .uri("/api/orders")
        .bodyValue(new CreateOrderRequest("sku-123", 2))
        .exchange()
        .expectStatus().isOk();
}
~~~

Nếu ứng dụng API stateless đã chủ động disable CSRF vì chỉ dùng Bearer header và không dùng cookie tự động gửi, test không cần `csrf()`. Test phải phản ánh **CSRF policy thật của chain**, không thêm helper chỉ để làm cho test pass.

### 7.3. CSRF và authentication là hai điều kiện riêng

Request POST có thể bị chặn bởi CSRF trước khi đến authorization rule hoặc controller. Vì vậy khi debug 403, kiểm tra:

- CSRF token có được gửi khi policy yêu cầu không?
- Authentication có được thiết lập không?
- Principal có authority cần thiết không?
- Có method security hoặc custom authorization manager từ chối không?

Không kết luận mọi 403 đều là thiếu scope.

## 8. Kiểm thử JWT thật qua ReactiveJwtDecoder

Mock JWT helpers bỏ qua token decoder. Để kiểm tra chữ ký, issuer, audience và thời gian, hãy gửi compact JWT có chữ ký thật qua Authorization Bearer header và cấu hình ReactiveJwtDecoder xác minh nó.

### 8.1. Vì sao cần một test signing key riêng?

Trong integration test, có thể sinh một RSA key pair dùng riêng cho test:

~~~text
Test private key:
    ký JWT fixture
    chỉ dùng trong test runtime

Test public key:
    cấu hình ReactiveJwtDecoder
    dùng để verify chữ ký

Production:
    dùng issuer/JWKS thật
    không trust test key
~~~

Không dùng private signing key của production issuer trong test. Không gọi mạng ngoài để lấy token trong mỗi test; fixture cục bộ giúp test lặp lại ổn định.

### 8.2. Test decoder với issuer và audience validators

Ví dụ cấu hình test:

~~~java
import java.security.interfaces.RSAPublicKey;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;

@TestConfiguration
class TestJwtDecoderConfiguration {

    static final String ISSUER = "https://issuer.test";
    static final String AUDIENCE = "https://api.test/orders";

    @Bean
    TestRsaKeys testRsaKeys() {
        return new TestRsaKeys();
    }

    @Bean
    @Primary
    ReactiveJwtDecoder testReactiveJwtDecoder(TestRsaKeys keys) {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withPublicKey(
                (RSAPublicKey) keys.keyPair().getPublic())
                .signatureAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Token audience is not accepted", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator
            )
        );
        return decoder;
    }
}
~~~

JwtValidators.createDefaultWithIssuer giữ các kiểm tra mặc định theo issuer và thời gian; audience validator được ghép bằng DelegatingOAuth2TokenValidator. Nếu chỉ gọi setJwtValidator(audienceValidator), ứng dụng có thể vô tình thay thế các validator mặc định.

TestRsaKeys là fixture test do ứng dụng tạo để giữ key pair ổn định giữa encoder và decoder. Đặt bean test trong test source set và bảo đảm đây là decoder mà SecurityWebFilterChain thực sự sử dụng. Nếu production configuration đã khai báo decoder riêng, dùng test profile/context riêng hoặc thay thế bean theo cơ chế test phù hợp thay vì tạo hai decoder cạnh tranh.

### 8.3. Tạo JWT có chữ ký bằng NimbusJwtEncoder

Spring Security OAuth2 JOSE cung cấp NimbusJwtEncoder. Có thể dựng JWK source từ key pair test:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.context.annotation.Bean;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

@TestConfiguration
class TestJwtEncoderConfiguration {

    @Bean
    JwtEncoder testJwtEncoder(TestRsaKeys keys) {
        RSAKey rsaJwk = new RSAKey.Builder(
                (RSAPublicKey) keys.keyPair().getPublic())
            .privateKey((RSAPrivateKey) keys.keyPair().getPrivate())
            .keyID("test-key")
            .build();

        JWKSource<SecurityContext> jwkSource =
            new ImmutableJWKSet<>(new JWKSet(rsaJwk));
        return new NimbusJwtEncoder(jwkSource);
    }
}
~~~

TestRsaKeys có thể tạo key pair một lần:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;

final class TestRsaKeys {

    private final KeyPair keyPair;

    TestRsaKeys() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            this.keyPair = generator.generateKeyPair();
        } catch (Exception ex) {
            throw new IllegalStateException("Cannot create test RSA keys", ex);
        }
    }

    KeyPair keyPair() {
        return keyPair;
    }
}
~~~

Để hai bean encoder/decoder dùng cùng key pair, đăng ký TestRsaKeys thành một singleton bean trong test configuration. Không tạo một cặp key mới riêng trong từng bean.

### 8.4. Tạo token fixture với claims phù hợp

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.security.oauth2.jose.jws.JwsHeader;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;

String signedToken(
        JwtEncoder encoder,
        String audience,
        String scope,
        Instant expiresAt) {

    Instant now = Instant.now();
    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(TestJwtDecoderConfiguration.ISSUER)
        .subject("alice")
        .audience(List.of(audience))
        .issuedAt(now.minusSeconds(5))
        .expiresAt(expiresAt)
        .claim("scope", scope)
        .build();

    JwsHeader headers = JwsHeader.with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(headers, claims)
    ).getTokenValue();
}
~~~

Các tham số audience, scope, expiresAt cho phép tạo positive và negative tokens nhưng tất cả đều được ký bằng cùng test key. Nhờ vậy, test sai audience có thể chứng minh audience validator hoạt động thay vì bị từ chối do chữ ký.

### 8.5. Gửi token thật qua WebTestClient

~~~java
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@Import({TestJwtDecoderConfiguration.class, TestJwtEncoderConfiguration.class})
class OrdersRealJwtIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Autowired
    JwtEncoder testJwtEncoder;

    @Test
    void acceptsSignedTokenWithCorrectIssuerAudienceAndScope() {
        String token = signedToken(
            testJwtEncoder,
            TestJwtDecoderConfiguration.AUDIENCE,
            "orders.read",
            Instant.now().plusSeconds(300)
        );

        webTestClient.get()
            .uri("/api/orders/42")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void rejectsSignedTokenForAnotherAudience() {
        String token = signedToken(
            testJwtEncoder,
            "https://api.test/payments",
            "orders.read",
            Instant.now().plusSeconds(300)
        );

        webTestClient.get()
            .uri("/api/orders/42")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Đây là integration test theo mô hình test decoder/encoder đã cấu hình. Token sai audience vẫn có chữ ký hợp lệ và issuer đúng, nên 401 kiểm tra đúng ranh giới audience. Token thiếu scope nhưng đúng issuer/audience có thể được xác thực rồi nhận 403 ở authorization.

### 8.6. Test expired token và thiếu scope

Tạo token hết hạn nhưng có chữ ký hợp lệ:

~~~java
String expiredToken = signedToken(
    testJwtEncoder,
    TestJwtDecoderConfiguration.AUDIENCE,
    "orders.read",
    Instant.now().minusSeconds(120)
);
~~~

Gửi token này tới endpoint protected và mong đợi 401. Thời điểm hết hạn nên nằm đủ xa trong quá khứ để không bị chấp nhận bởi clock skew.

Token đúng issuer, audience, expiry nhưng thiếu scope:

~~~java
String insufficientScopeToken = signedToken(
    testJwtEncoder,
    TestJwtDecoderConfiguration.AUDIENCE,
    "orders.write",
    Instant.now().plusSeconds(300)
);
~~~

Gửi token này tới GET Orders. Decoder có thể xác thực token, sau đó authorization rule từ chối vì thiếu SCOPE_orders.read; kết quả thường là 403. Đây là cách tách bạch token validation và endpoint authorization.

## 9. Kiểm thử slice bằng @WebFluxTest

`@WebFluxTest` tải một phần WebFlux application context, thường tập trung vào controller/handler và các WebFlux components liên quan. Nó khởi tạo nhanh hơn một full `@SpringBootTest` nhưng không tự mang toàn bộ cấu hình application.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@WebFluxTest(controllers = OrdersController.class)
@Import(OrdersSecurityConfiguration.class)
class OrdersControllerSliceTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void requestWithoutJwtIsUnauthorized() {
        webTestClient.get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void requestWithReadScopeIsAllowed() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("scope", "orders.read")))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Nếu controller phụ thuộc service/repository, slice test cần mock các dependency bị loại khỏi slice. Tùy Spring Boot version, dùng annotation bean override phù hợp như `@MockitoBean` hoặc `@MockBean`. Không import cả application config không cần thiết chỉ để làm test context khởi động.

### 9.1. Slice test kiểm tra gì?

`@WebFluxTest` phù hợp để kiểm tra:

- Mapping path/method và binding request body.
- Response status/body/headers.
- Security chain được import và áp dụng trong slice.
- Authorities cần cho endpoint.
- Error mapping ở controller/WebFlux layer.

Nó không tự chứng minh:

- Production issuer/JWKS discovery hoạt động.
- Production decoder có key/algorithm đúng.
- OAuth client hoặc external database được cấu hình đầy đủ.
- Gateway/proxy ngoài ứng dụng forward headers đúng.

### 9.2. Đừng nhầm test slice với full integration

Nếu test chỉ import `OrdersSecurityConfiguration` nhưng production còn có một chain khác, custom filter, security context repository hoặc gateway integration, slice có thể không bao phủ các thành phần đó. Dùng slice cho feedback nhanh; dùng full context/server integration cho các ranh giới wiring quan trọng.

## 10. Kiểm thử method security trong WebFlux

Path authorization và method authorization là hai lớp riêng. Một endpoint có thể được cho phép ở HTTP path nhưng service method vẫn cần scope cụ thể.

Ví dụ service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class SecureOrdersService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    Mono<OrderResponse> read(String id) {
        return Mono.just(new OrderResponse(id, "CREATED"));
    }
}
~~~

Với reactive method security, method trả reactive type như Mono/Flux để Spring Security có thể áp dụng authorization trong reactive execution. Cấu hình phải bật `@EnableReactiveMethodSecurity`.

### 10.1. Test method security qua HTTP

Một test HTTP dùng mock JWT có scope phù hợp:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("scope", "orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Với token thiếu scope:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("scope", "orders.write")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isForbidden();
~~~

Để test method security độc lập với HTTP mapping, có thể gọi service bean qua test context và subscribe kết quả. Tuy nhiên cần xác nhận lời gọi đi qua Spring proxy; gọi trực tiếp method nội bộ trong cùng class (self-invocation) có thể bypass proxy-based method security.

### 10.2. Test method security không chỉ dựa vào controller status

Nếu endpoint có path rule `hasAuthority("SCOPE_orders.read")` và method cũng yêu cầu cùng authority, test thiếu scope có thể bị chặn ở path trước khi chạy service method. Để chứng minh method annotation riêng, có thể dùng endpoint test cho phép authenticated user ở path level nhưng service method yêu cầu scope, hoặc test service proxy trực tiếp.

## 11. Kiểm thử nhiều SecurityWebFilterChain

Một ứng dụng WebFlux có thể khai báo nhiều `SecurityWebFilterChain`, ví dụ:

- API chain cho `/api/**`.
- Actuator chain cho `/actuator/**`.
- Browser/login chain cho route UI còn lại.

Spring Security chọn chain đầu tiên có matcher phù hợp theo thứ tự `@Order`. Test phải chứng minh **request vào đúng chain dự kiến**, không chỉ chứng minh một chain nào đó đã hoạt động.

### 11.1. Lập bảng route trước khi viết test

| Request path | Chain dự kiến | Authentication | Quyền |
|---|---|---|---|
| `/api/orders/42` | API Resource Server | Bearer JWT | `SCOPE_orders.read` |
| `/actuator/health` | Actuator policy | Theo exposure policy | Có thể public |
| `/ui/profile` | Browser/session chain | OAuth2 Login/session | User authenticated |

### 11.2. Test từng vùng route

~~~java
@Test
void apiRouteRequiresBearerAuthentication() {
    webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void healthEndpointUsesItsConfiguredPolicy() {
    webTestClient.get()
        .uri("/actuator/health")
        .exchange()
        .expectStatus().isOk();
}
~~~

Ví dụ health route chỉ public nếu chain/actuator exposure policy thực sự cho phép. Không sao chép kết quả 200 vào mọi ứng dụng.

### 11.3. Sai thứ tự chain có thể làm test sai

Nếu chain rộng hơn như `anyExchange()` đứng trước chain `/api/**`, request API có thể bị xử lý bởi chain rộng và không chạy JWT Resource Server config. Kiểm thử route đại diện cho từng chain giúp phát hiện matcher/order sai.

Khi có nhiều chain, nên dùng test token thật cho ít nhất một request API quan trọng để xác nhận đúng chain có decoder/validators thực được chọn.

## 12. Kiểm thử custom JWT authority converter

Mặc định Spring Security chuyển các scope trong claim `scope` hoặc `scp` thành authority có prefix `SCOPE_`. Một số issuer lại dùng claim riêng như `roles`, `permissions` hoặc cấu trúc nested. Khi ứng dụng có custom converter, cần kiểm thử mapping đó.

### 12.1. Ví dụ policy dùng roles claim

Giả sử ứng dụng muốn map:

~~~json
{
  "sub": "alice",
  "roles": ["ORDER_READER", "ORDER_APPROVER"]
}
~~~

thành authorities:

~~~text
ROLE_ORDER_READER
ROLE_ORDER_APPROVER
~~~

Không giả định Spring Security tự map mọi claim roles theo đúng quy ước ứng dụng. Converter phải được cấu hình rõ ràng.

### 12.2. Kiểm thử converter ở tầng authorization

Nếu converter được thiết kế như một bean riêng, có thể test trực tiếp việc chuyển claims sang authorities bằng JWT object dựng trong test. Sau đó cần một integration test xác nhận bean converter đó thật sự được gắn vào Resource Server:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("roles", List.of("ORDER_READER"))))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Ví dụ này chỉ thành công nếu mockJwt configurer hoặc test authentication setup dùng cùng authority mapping mong đợi. Nếu mockJwt mặc định vẫn chỉ đọc scope, hãy đặt authorities trực tiếp cho test authorization và viết test riêng cho converter thật. Để xác nhận converter được nối vào decoder, dùng JWT ký thật qua request như phần trước.

### 12.3. Test sai claim mapping

Một token có roles bằng ORDER_APPROVER không nên vô tình nhận quyền đọc đơn hàng nếu policy chỉ cấp quyền đó cho ORDER_READER. Tạo negative case cho role/permission gần giống để phát hiện prefix hoặc mapping quá rộng.

## 13. Kiểm tra method, headers và response body

WebTestClient có thể kiểm tra toàn bộ HTTP contract của endpoint sau khi request vượt security chain.

### 13.1. Kiểm tra status và JSON

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("scope", "orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo("42")
    .jsonPath("$.status").isEqualTo("CREATED");
~~~

Security test không chỉ nên assert status khi endpoint có response contract quan trọng. Có thể xác nhận body, content type, cache headers và các response headers do application policy yêu cầu.

### 13.2. Kiểm tra HTTP method riêng

GET và POST có thể yêu cầu scope khác nhau. Test cả hai:

~~~java
@Test
void readScopeCannotCreateOrder() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt ->
            jwt.claim("scope", "orders.read")))
        .post()
        .uri("/api/orders")
        .bodyValue(new CreateOrderRequest("sku-123", 2))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Nếu CSRF vẫn bật, POST test cần thêm CSRF token; nếu API đã disable CSRF theo policy stateless bearer, test chỉ cần scope authorization.

### 13.3. Kiểm tra lỗi nghiệp vụ sau security

Một principal có scope hợp lệ vẫn có thể nhận 404 khi order không tồn tại:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("scope", "orders.read")))
    .get()
    .uri("/api/orders/missing")
    .exchange()
    .expectStatus().isNotFound();
~~~

Điều này chứng minh request đã qua authentication/authorization rồi mới chạm business handler. Không nên dùng status 404 cho mọi lỗi security để che giấu cấu hình chain; giữ response semantics nhất quán với API policy.

## 14. Reactive execution và context propagation trong tests

WebFlux security lưu SecurityContext trong reactive context. Vì vậy cách viết test hoặc service code có thể ảnh hưởng đến việc Authentication được nhìn thấy trong reactive pipeline.

### 14.1. Không block reactive pipeline để đọc SecurityContext

Trong production WebFlux, tránh:

~~~java
// Không nên trong reactive request pipeline
Authentication authentication =
    ReactiveSecurityContextHolder.getContext().block()
        .getAuthentication();
~~~

Thay vào đó, compose reactive chain:

~~~java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(authentication -> service.loadFor(authentication));
~~~

WebTestClient subscribe request pipeline và đợi response theo test exchange. Không cần gọi block trong test để lấy Authentication; hãy assert response hoặc dùng reactive test utilities ở lớp service.

### 14.2. Kiểm thử principal được truyền vào handler

Controller có thể nhận principal:

~~~java
@GetMapping("/me")
Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(Map.of("subject", jwt.getSubject()));
}
~~~

Test với mock JWT:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt.subject("alice")))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.subject").isEqualTo("alice");
~~~

Với controller nhận @AuthenticationPrincipal, principal type phụ thuộc Authentication được tạo. Nếu dùng custom authentication converter, principal có thể không còn là Jwt; test cần xác nhận đúng principal type.

### 14.3. Async work không tự kế thừa request context

Không mặc định SecurityContext tự được mang sang mọi executor, scheduler hoặc background task. Nếu handler dispatch work sang thread pool riêng, cần thiết kế context propagation có kiểm soát. Test cần xác nhận user context được truyền đúng nơi cần và không rò sang request khác.

Không lưu SecurityContext vào static mutable field để làm test pass; cách đó có thể gây cross-request data leakage.

## 15. Kiểm thử CSRF, CORS và security response headers

CSRF và CORS là hai cơ chế khác nhau:

- CSRF kiểm soát request thay mặt browser session/cookie.
- CORS quyết định browser origin nào được phép đọc response và gửi các request có header/method cần preflight.

### 15.1. Test CORS preflight

Nếu browser client gửi Authorization header hoặc custom headers, test OPTIONS preflight:

~~~java
webTestClient.options()
    .uri("/api/orders")
    .header(HttpHeaders.ORIGIN, "https://shop.example.test")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://shop.example.test");
~~~

Response cụ thể phụ thuộc CORS configuration và version. Cần kiểm tra origin allowlist, methods, headers, credentials và exposed response headers theo contract của frontend. Không cho phép mọi origin cùng credentials chỉ để test đơn giản.

### 15.2. CORS preflight không phải bằng chứng authentication

Preflight OPTIONS thường được xử lý trước khi browser gửi request thật có Authorization. Một OPTIONS 200 không chứng minh GET/POST được xác thực hoặc được cấp quyền. Test request thật riêng.

### 15.3. Security headers

Nếu API hoặc browser app có policy về HSTS, cache control, content type options hoặc CSP, kiểm tra response headers ở HTTP boundary:

~~~java
webTestClient.get()
    .uri("/public/health")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().exists("X-Content-Type-Options");
~~~

Không assert một header nếu ứng dụng không cấu hình hoặc không có requirement tương ứng. API và browser UI có thể cần security header policy khác nhau.

## 16. Troubleshooting WebTestClient và SecurityWebFilterChain

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Endpoint protected trả 200 khi không có token | Security chain không được cài vào test client hoặc matcher không khớp | Bind application context, apply springSecurity, kiểm tra chain order/matcher |
| Mọi request trả 401 kể cả mockJwt | Test client chưa áp dụng security test configurer hoặc route dùng chain khác | Kiểm tra WebTestClient builder, filter chain được chọn và dependency spring-security-test |
| mockJwt có scope đúng nhưng trả 403 | Authority prefix/custom converter khác với mong đợi | Xem Authentication authorities và converter thật |
| Token ký thật trả 401 | Signature, issuer, audience, exp/nbf hoặc decoder wiring sai | Xác minh từng validator; kiểm tra public key tương ứng |
| Token sai audience vẫn trả 200 | Audience validator không được gắn vào decoder thực hoặc test dùng mockJwt | Gửi signed JWT qua Bearer header và kiểm tra decoder bean |
| POST trả 403 dù scope đúng | CSRF đang bật và request thiếu token | Dùng csrf() khi policy yêu cầu hoặc xem lại stateless API CSRF policy |
| Test @WebFluxTest không có SecurityWebFilterChain | Slice không import security configuration | Import chain/config cần thiết vào slice |
| Test context gọi issuer/JWKS thật | Auto-configuration discovery đang phụ thuộc network | Dùng test decoder/JWK fixture hoặc mock issuer cục bộ |
| Method security không chặn | Chưa bật reactive method security, method không qua proxy hoặc return type không phù hợp | Kiểm tra annotation/configuration/proxy và reactive return |
| Request qua nhiều chain cho kết quả lạ | Sai @Order hoặc securityMatcher quá rộng | Test từng path và chain matcher |
| SecurityContext mất trong async flow | Reactive context không được propagate vào execution path | Kiểm tra Reactor context và custom scheduler/executor |
| CORS OPTIONS thành công nhưng GET thất bại | Preflight chỉ kiểm tra CORS, không xác minh Bearer token | Test request thật riêng |

### 16.1. Bật log security có kiểm soát

Trong môi trường test có thể tăng log level cho Spring Security để hiểu chain/provider được gọi:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Không bật verbose HTTP logging với raw Authorization header trong production. Nếu log có token hoặc claims nhạy cảm, cần redaction và giới hạn quyền truy cập.

### 16.2. Xác định test đang dùng mock hay decoder thật

Hỏi ba câu:

1. Request có dùng mutateWith(mockJwt()) không? Nếu có, Authentication được mock và decoder thường bị bypass.
2. Request có Authorization: Bearer với signed JWT không? Nếu có, filter Resource Server có thể gọi decoder thật.
3. Test context có ReactiveJwtDecoder bean nào được chain sử dụng? Kiểm tra test config/auto-configuration và bean selection.

Nếu mục tiêu là audience/signature validation, phải có test ở câu 2 và 3.

## 17. Checklist thiết kế bộ WebTestClient security tests

### 17.1. Test setup

- [ ] Đã xác định ứng dụng là WebFlux reactive hay Servlet MVC.
- [ ] Có spring-boot-starter-webflux và spring-security-test phù hợp.
- [ ] WebTestClient được bind vào application context hoặc server theo phạm vi cần test.
- [ ] Nếu bind application context, đã apply springSecurity().
- [ ] SecurityWebFilterChain thực tế được import/khởi tạo trong test context.
- [ ] Nếu dùng @WebFluxTest, đã import security configuration cần thiết.
- [ ] Không phụ thuộc Authorization Server/JWKS bên ngoài trong test unit/slice.

### 17.2. Authentication và authorization

- [ ] Protected route không có token bị từ chối (thường 401).
- [ ] Public route được truy cập theo policy.
- [ ] mockJwt có authority đủ được phép.
- [ ] mockJwt thiếu scope bị từ chối (thường 403).
- [ ] Đã phân biệt mockUser/mockAuthentication với JWT Resource Server authentication.
- [ ] Custom authority converter có test riêng.
- [ ] Method security và path authorization được kiểm tra ở đúng lớp.
- [ ] Nhiều SecurityWebFilterChain được kiểm tra theo matcher/order.

### 17.3. Token validation

- [ ] Có test JWT ký thật qua Bearer header và ReactiveJwtDecoder thực.
- [ ] Token đúng issuer/audience/time/signature được chấp nhận.
- [ ] Token sai chữ ký bị từ chối.
- [ ] Token sai issuer bị từ chối.
- [ ] Token sai audience bị từ chối.
- [ ] Token hết hạn/not-before invalid bị từ chối.
- [ ] Token đúng nhưng thiếu scope được phân biệt với token invalid.
- [ ] Test decoder dùng key test riêng, không dùng production private key.

### 17.4. HTTP và vận hành

- [ ] CSRF test phản ánh policy thật của ứng dụng.
- [ ] CORS preflight và actual request được test riêng.
- [ ] Response status/body/headers được assert khi có contract.
- [ ] Reactive SecurityContext không bị block hoặc lưu static.
- [ ] Async context propagation có test nếu ứng dụng dùng scheduler/executor riêng.
- [ ] Không log access token hoặc raw Authorization header.
- [ ] Test slice và full integration có phạm vi rõ ràng.

## 18. Kết luận

WebTestClient là công cụ kiểm thử HTTP tự nhiên cho WebFlux. Khi mục tiêu là kiểm tra SecurityWebFilterChain, hãy đưa security filters thực vào test client bằng application context binding cùng springSecurity(), hoặc dùng Spring Boot integration test với WebTestClient được auto-configure.

Để kiểm tra authorization nhanh, mockJwt() tạo Authentication giả lập có claims/authorities phù hợp. Nó hữu ích cho 401/403, scope rules, controller và method security. Nhưng nó không chạy JWT signature validation. Với issuer, audience, expiry và chữ ký, hãy tạo JWT có chữ ký test thật, gửi qua Authorization Bearer header và để ReactiveJwtDecoder xác minh.

Một bộ test vững chắc cần phân biệt:

~~~text
Authentication:
    no token / invalid token → reject
    valid JWT → authenticated

Authorization:
    valid principal + required scope → allow
    valid principal + missing scope → deny

HTTP/application:
    CSRF, CORS, route matcher, method security,
    response body and business errors
~~~

WebFlux security dựa trên reactive context và WebFilter chain, vì vậy không dùng Servlet test setup như thể đó là cùng một runtime. Kiểm tra đúng chain, đúng decoder, đúng context và đúng policy của ứng dụng là điều làm cho kết quả WebTestClient có ý nghĩa.

## Tài liệu tham khảo

- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — CSRF Protection for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot — @WebFluxTest](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html)
- [Spring Security — SecurityMockServerConfigurers Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [Spring Security — ReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [Spring Security — NimbusReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
