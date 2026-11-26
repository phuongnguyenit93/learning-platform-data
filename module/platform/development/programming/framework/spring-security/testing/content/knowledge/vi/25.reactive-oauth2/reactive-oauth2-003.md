# ReactiveJwtDecoder giả lập so với decoder thật

Khi kiểm thử Spring WebFlux OAuth2 Resource Server, ta có thể làm cho một request mang danh tính JWT theo ít nhất ba cách: gắn `Authentication` giả lập bằng `mockJwt()`; gửi bearer token và thay `ReactiveJwtDecoder` bằng mock; hoặc gửi **JWT được ký thật** để `NimbusReactiveJwtDecoder` tải khóa từ JWKS và xác minh token. Cả ba đều có ích, nhưng **mỗi cách chứng minh một phạm vi khác nhau**.

Bài thuộc chương **OAuth2 Reactive** của module `SPRING_SECURITY_TESTING`, nơi người học kiểm chứng xác thực, phân quyền và HTTP security bằng `spring-security-test` trên cả Servlet và Reactive. Trọng tâm ở đây là WebFlux với `WebTestClient`, `ReactiveJwtDecoder`, Reactor `SecurityContext` và các trường hợp truy cập được phép/bị từ chối. Ta sẽ xây dựng cùng một API rồi so sánh test giả lập với test dùng decoder thật, nêu rõ chỗ nào có thể phát sinh kết quả xanh giả.

> **Nguyên tắc:** Đừng viết `.mutateWith(mockJwt())` rồi kết luận đã thử được kiểm tra chữ ký JWT, issuer, audience, thời hạn token hoặc kết nối JWKS. Đừng mock `ReactiveJwtDecoder` rồi kết luận decoder production đã hoạt động đúng.

## 1. Vai trò của ReactiveJwtDecoder trong luồng Resource Server

Một HTTP request gửi tới ứng dụng:

```http
GET /api/reports/q4 HTTP/1.1
Host: localhost:8080
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0...
```

Nếu ứng dụng có `oauth2ResourceServer().jwt()`, Spring Security WebFlux tìm bearer token, gọi `ReactiveJwtDecoder.decode(String)` để giải mã và xác minh JWT, rồi dùng converter tạo `Authentication` và đưa vào Reactor security context. Quy tắc HTTP/method security kiểm tra authorities trên `Authentication` đó.

```mermaid
flowchart TD
    A["WebTestClient: GET /api/reports/q4"] --> B{Cách setup test}
    B -- "mutateWith(mockJwt())" --> C["Authentication/Jwt được test configurer tạo sẵn"]
    B -- "Authorization: Bearer ..." --> D["ServerAuthenticationConverter lấy bearer"]
    D --> E["ReactiveJwtAuthenticationManager"]
    E --> F["ReactiveJwtDecoder.decode(token)"]
    F --> G["ReactiveJwtAuthenticationConverter"]
    C --> H["AuthorizationWebFilter: hasAuthority"]
    G --> H
    H --> I{Có SCOPE_reports.read?}
    I -- Có --> J[Controller gọi nghiệp vụ]
    I -- Không --> K[403 nếu đã xác thực nhưng thiếu quyền]
    F -. "mock decoder" .-> L["Trả Jwt/Mono.error theo stub, bỏ qua kiểm tra chữ ký thật"]
    F -. "decoder thật" .-> M["Kiểm tra signature, time, issuer, audience và có thể tải JWKS"]
```

Nhánh `mockJwt()` **không** đi qua `ReactiveJwtDecoder`. Hai nhánh bearer đều có thể đi qua lớp quản lý xác thực; khác biệt nằm ở việc `decode(...)` trả dữ liệu do Mockito dàn dựng hay do decoder thật kiểm tra.

`ReactiveJwtDecoder` có phương thức trung tâm:

```java
public interface ReactiveJwtDecoder {
    reactor.core.publisher.Mono<org.springframework.security.oauth2.jwt.Jwt>
            decode(String token) throws org.springframework.security.oauth2.jwt.JwtException;
}
```

Trong thực tế, `decode` trả `Mono<Jwt>` thành công hoặc lỗi. Một đối tượng `Jwt` được tạo thủ công **chỉ là dữ liệu**, chưa tự chứng minh chữ ký của chuỗi bearer đã hợp lệ; chính decoder chịu trách nhiệm xác minh theo cấu hình.

### Không nhầm Resource Server với OAuth2/OIDC Login

`ReactiveJwtDecoder` trong bài phục vụ **API nhận bearer JWT**. Nó không phải toàn bộ luồng **đăng nhập trình duyệt OAuth2/OIDC Authorization Code**. `mockOAuth2Login()`/`mockOidcLogin()` giả lập người dùng đã đăng nhập, còn `mockJwt()` giả lập JWT authentication của Resource Server. ID Token của OIDC login có audience và ý nghĩa khác access token của Resource Server.

## 2. So sánh ba chiến lược test

| Chiến lược | Request gửi gì? | Có gọi decoder của ứng dụng? | Có kiểm tra chữ ký/claims thật? | Mục tiêu phù hợp |
|---|---|---|---|---|
| **A.** `mockJwt()` | Test configurer gắn JWT authentication trực tiếp | **Không** | **Không** | HTTP/method authorization và controller khi đã có danh tính JWT. |
| **B.** Bearer header + `@MockitoBean ReactiveJwtDecoder` | Chuỗi bearer giả, decoder trả `Mono<Jwt>` được stub | **Có gọi interface mock** | **Không** | Wiring từ bearer token qua authentication manager, converter quyền và HTTP authorization. |
| **C.** Bearer header + decoder thật + JWKS test server | JWT RSA ký thật | **Có, decoder thật** | **Có**, theo validators đang cấu hình | Signature, `kid`, JWKS, issuer/audience/time và toàn bộ HTTP authorization. |

Không có chiến lược nào thay thế hoàn toàn chiến lược khác. A nhanh để viết nhiều ca quyền; B kiểm soát phản hồi decoder và đường chuyển thành authorities; C giúp bắt lỗi cấu hình decoder, khóa ký và xác thực token mà A/B không thể thấy.

## 3. Ứng dụng Reactive mẫu để dùng chung các test

Ví dụ dùng Java 17+, Spring Boot WebFlux và các dependency `spring-boot-starter-webflux`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-resource-server`, `spring-boot-starter-test`, `spring-security-test`. Với Maven/Gradle thật, đảm bảo ứng dụng dùng **WebFlux**, không để Servlet MVC vô tình chiếm web application type.

### SecurityWebFilterChain

Ứng dụng chỉ cho phép người dùng mang authority `SCOPE_reports.read` đọc báo cáo.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ResourceServerSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers(HttpMethod.GET, "/api/reports/**")
                        .hasAuthority("SCOPE_reports.read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Theo converter JWT mặc định, claim `scope` hoặc `scp` thường tạo authority có tiền tố `SCOPE_`. Nếu dự án dùng converter riêng (chẳng hạn đọc `permissions`, thêm `PERM_`), hãy sửa đồng thời **biểu thức phân quyền** và **dữ liệu test**; không được lấy kết quả trên chain mặc định để kết luận converter tùy chỉnh đã được kiểm tra.

### Controller và service

```java
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

interface ReportService {
    Mono<String> read(String reportId);
}

@Service
class DefaultReportService implements ReportService {
    @Override
    public Mono<String> read(String reportId) {
        return Mono.just("report-" + reportId);
    }
}

@RestController
@RequestMapping("/api/reports")
class ReportController {
    private final ReportService service;

    ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Mono<String> read(@PathVariable String id) {
        return service.read(id);
    }
}
```

Để quan sát nghiệp vụ, các test có thể mock `ReportService`. Cách đó hợp lệ ở ví dụ này vì **authorization nằm tại HTTP SecurityWebFilterChain**. Nếu cần kiểm thử `@PreAuthorize` trên chính service, phải giữ service là Spring bean thật và mock dependency phía sau để không bỏ qua proxy/interceptor.

### Decoder production có validator

Ví dụ cung cấp decoder thật qua JWKS URI đã cấu hình. `jwk-set-uri` dùng để tải khóa công khai; `issuer` là giá trị phải có trong claim `iss`. API cũng phải kiểm tra `aud` tương ứng với chính Resource Server.

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
class ReportJwtDecoderConfig {
    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${training.jwt.jwks-uri}") String jwksUri,
            @Value("${training.jwt.issuer}") String issuer
    ) {
        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
                .withJwkSetUri(jwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> defaultAndIssuer =
                JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains("reports-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required audience is missing",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaultAndIssuer, audience));
        return decoder;
    }
}
```

Hai property `training.jwt.jwks-uri` và `training.jwt.issuer` phải được cấu hình ngoài production; trong test sẽ trỏ đến JWKS HTTP server **cục bộ**. Đừng đặt URI sản xuất vào bài test; mạng và lịch xoay khóa của IdP sẽ làm test không lặp lại được. Nếu dùng issuer discovery tự động thay vì JWKS URI tường minh, cần kiểm tra thêm quy trình discovery/metadata.

## 4. Khởi tạo WebTestClient đúng cho WebFlux security

Với test chạy trong `ApplicationContext` của WebFlux, áp dụng `SecurityMockServerConfigurers.springSecurity()`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@Autowired
ApplicationContext context;

WebTestClient webTestClient;

@BeforeEach
void setUpClient() {
    webTestClient = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
}
```

Đây là đoạn thành viên **bên trong Spring test class**. `WebTestClient` bind-to-context có thể mô phỏng authentication bằng `mutateWith(...)`. Nếu dùng `WebTestClient.bindToServer()` gọi một **server HTTP riêng**, bạn không thể dùng `mockJwt()` để tự cài Reactor security context phía server; muốn test tích hợp từ ngoài tiến trình thì hãy gửi bearer token thực.

## 5. Chiến lược A: mockJwt() — không đi qua ReactiveJwtDecoder

`mockJwt()` là `WebTestClientConfigurer` từ package `org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers`. Nó gắn một JWT Authentication giả lập cho request, **không gửi chuỗi JWT được ký và không chạy bộ giải mã**.

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

webTestClient
        .mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority(
                        "SCOPE_reports.read")))
        .get()
        .uri("/api/reports/q4")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("report-q4");
```

Đây là test tốt để trả lời: **nếu Authentication đã có authority `SCOPE_reports.read`, endpoint có cho phép và trả nội dung đúng không?**

Test bị từ chối cũng dễ dựng:

```java
webTestClient
        .mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority(
                        "SCOPE_reports.write")))
        .get()
        .uri("/api/reports/q4")
        .exchange()
        .expectStatus().isForbidden();
```

**Điểm không được suy diễn:** Nếu thiết lập sai `jwk-set-uri`, public key hết hạn, issuer khác hoặc signature không hợp lệ, hai test `mockJwt()` vẫn có thể xanh. Chúng không sử dụng `ReportJwtDecoderConfig` để giải mã token. Ngay cả khi gọi `mockJwt().jwt(jwt -> jwt.claim("scope", "reports.read"))`, hãy nhớ rằng post-processor không tự động dùng custom converter hay validator của application.

## 6. Chiến lược B: mock ReactiveJwtDecoder, giữ đường bearer/filter thật

Khi muốn kiểm tra bộ lọc bearer và việc chuyển `Jwt` thành `Authentication` nhưng không muốn phụ thuộc RSA/JWKS, có thể thay bean `ReactiveJwtDecoder` bằng Mockito. `WebTestClient` **gửi header Authorization thật**, còn `decode(...)` được stub trả `Mono<Jwt>`.

Ví dụ dưới dùng `@MockitoBean` của Spring Framework 6.2+/Spring Boot 3.4+. Với stack cũ hơn, dùng cơ chế mock bean phù hợp.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import java.time.Instant;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = {
                "training.jwt.jwks-uri=http://127.0.0.1:9/unused",
                "training.jwt.issuer=https://issuer.training.test"
        })
class MockReactiveJwtDecoderTest {
    @Autowired
    ApplicationContext context;

    @MockitoBean
    ReactiveJwtDecoder decoder;

    @MockitoBean
    ReportService reports;

    WebTestClient webTestClient;

    @BeforeEach
    void setUp() {
        webTestClient = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    private static Jwt jwt(String token, String scope) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(token)
                .header("alg", "RS256")
                .subject("lan")
                .issuer("https://issuer.training.test")
                .audience(java.util.List.of("reports-api"))
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300))
                .claim("scope", scope)
                .build();
    }

    @Test
    void bearerTokenDecodedToReadScope_isAllowed() {
        when(decoder.decode("good-token"))
                .thenReturn(Mono.just(
                        jwt("good-token", "reports.read")));
        when(reports.read("q4")).thenReturn(Mono.just("report-q4"));

        webTestClient.get()
                .uri("/api/reports/q4")
                .header(HttpHeaders.AUTHORIZATION, "Bearer good-token")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report-q4");

        verify(decoder).decode("good-token");
        verify(reports).read("q4");
    }

    @Test
    void bearerTokenWithoutReadScope_isForbidden() {
        when(decoder.decode("write-only"))
                .thenReturn(Mono.just(
                        jwt("write-only", "reports.write")));

        webTestClient.get()
                .uri("/api/reports/q4")
                .header(HttpHeaders.AUTHORIZATION, "Bearer write-only")
                .exchange()
                .expectStatus().isForbidden();

        verify(decoder).decode("write-only");
        verifyNoInteractions(reports);
    }

    @Test
    void decoderRejectsToken_returnsUnauthorized() {
        when(decoder.decode("bad-token"))
                .thenReturn(Mono.error(
                        new BadJwtException("Token not trusted")));

        webTestClient.get()
                .uri("/api/reports/q4")
                .header(HttpHeaders.AUTHORIZATION, "Bearer bad-token")
                .exchange()
                .expectStatus().isUnauthorized();

        verify(decoder).decode("bad-token");
        verifyNoInteractions(reports);
    }
}
```

Ba ca này kiểm tra:

1. `Bearer good-token` đi qua reactive authentication manager; `decode` được gọi, claim `scope` được converter mặc định chuyển thành `SCOPE_reports.read`, HTTP authorization cho phép (200).
2. `Bearer write-only` được decoder giả lập công nhận nhưng không đủ quyền: HTTP authorization từ chối (403) trước khi gọi service.
3. Decoder phát `BadJwtException`: authentication thất bại (thông thường 401 với Bearer entry point), không chạy nghiệp vụ.

URL `http://127.0.0.1:9/unused` là giá trị **dummy chỉ cho test**; decoder đã được Mockito thay thế, vì vậy test không được gọi mạng tới URI này. Không dùng cấu hình dummy như vậy trong production.

### Điều B không chứng minh

Một `Jwt` được Mockito trả về có thể có `iss` sai, `exp` hết hạn, `aud` thiếu hoặc header `alg` giả. Nếu mock vẫn trả `Mono.just(jwt)`, Spring Security thường xem đây là **kết quả decode thành công** và tiếp tục authorization. Các validator của `NimbusReactiveJwtDecoder` **không chạy**. Do đó test B không chứng minh signature/issuer/audience/expiration đang được kiểm tra đúng.

Ngược lại, B có thể kiểm tra việc **converter production được nối vào authentication manager** tốt hơn A: A cấp sẵn Authentication, còn B gửi bearer header để hệ thống chuyển `Jwt` từ decoder thành Authentication. Nếu ứng dụng có converter tùy chỉnh, hãy dùng claim đặc thù trong `Jwt` và bảo đảm test không cấp sẵn authority đầu ra.

## 7. Chiến lược C: decoder thật, JWT RSA ký thật, JWKS test server

Muốn kiểm tra xác thực thực tế, **không mock `ReactiveJwtDecoder`** và không dùng `mockJwt()`. Thay vào đó, tạo cặp khóa RSA cho test, ký JWT, công bố public key trong JWKS qua HTTP loopback rồi gửi token qua `Authorization: Bearer ...`. Khi đó `NimbusReactiveJwtDecoder` phải tải khóa, xác minh chữ ký và chạy validators.

### 7.1. Fixture RSA + JWT bằng Nimbus JOSE + JWT

```java
import java.time.Instant;
import java.util.Date;
import java.util.List;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

final class ReactiveJwtFixture {
    static final String ISSUER = "https://issuer.training.test";
    static final String AUDIENCE = "reports-api";

    static RSAKey key(String kid) throws JOSEException {
        return new RSAKeyGenerator(2048)
                .keyID(kid)
                .keyUse(KeyUse.SIGNATURE)
                .algorithm(JWSAlgorithm.RS256)
                .generate();
    }

    static String publicJwks(RSAKey key) {
        return new JWKSet(key.toPublicJWK()).toString();
    }

    static String signedToken(RSAKey signingKey)
            throws JOSEException {
        Instant now = Instant.now();
        var claims = new JWTClaimsSet.Builder()
                .issuer(ISSUER)
                .subject("lan")
                .audience(AUDIENCE)
                .issueTime(Date.from(now))
                .expirationTime(Date.from(now.plusSeconds(300)))
                .claim("scope", "reports.read")
                .build();

        var jwt = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .type(JOSEObjectType.JWT)
                        .keyID(signingKey.getKeyID())
                        .build(),
                claims);

        jwt.sign(new RSASSASigner(
                signingKey.toRSAPrivateKey()));
        return jwt.serialize();
    }
}
```

Chỉ xuất `key.toPublicJWK()` trong JWKS. **Private key không được trả qua HTTP**; nó chỉ ở fixture để ký token. Test phải tạo cặp khóa riêng, không tải private key thật của IdP. Trong dự án cần nhiều ca, bổ sung helper cho claim `iss`/`aud`/`exp` biến đổi để kiểm tra các nhánh không hợp lệ.

### 7.2. JWKS server cục bộ

Đoạn sau dùng `HttpServer` của JDK để trả public JWKS qua HTTP tại `127.0.0.1`. Có thể thay bằng WireMock hoặc MockWebServer.

```java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import com.sun.net.httpserver.HttpServer;

final class LocalJwksServer implements AutoCloseable {
    private final HttpServer server;
    private final AtomicReference<String> body =
            new AtomicReference<>("{\"keys\":[]}");
    private final AtomicInteger fetches = new AtomicInteger();

    LocalJwksServer() throws IOException {
        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/jwks", exchange -> {
            fetches.incrementAndGet();
            byte[] json = body.get().getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, json.length);
            try (var out = exchange.getResponseBody()) {
                out.write(json);
            }
        });
        server.start();
    }

    void publish(String jwksJson) {
        body.set(jwksJson);
    }

    String url() {
        return "http://127.0.0.1:"
                + server.getAddress().getPort() + "/jwks";
    }

    int fetches() {
        return fetches.get();
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
```

Server loopback chỉ dùng cho test. Trong production, JWKS URI phải được cấu hình là nguồn tin cậy, dùng kết nối bảo mật phù hợp. Khi kiểm tra cache/JWKS rotation, có thể thay `body` trong lúc giữ cùng URI và đo `fetches()`, nhưng **không mặc định một con số TTL hay số request mạng**: cơ chế cache/refresh phụ thuộc phiên bản Nimbus và cấu hình.

### 7.3. Context test dùng decoder thật và Bearer header

Ví dụ lớp test `@SpringBootTest` có cùng `ResourceServerSecurityConfig`/`ReportJwtDecoderConfig`. Nó đăng ký URI JWKS động trước khi Spring tạo decoder:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class RealReactiveJwtDecoderTest {
    static final LocalJwksServer JWKS = startServer();

    static LocalJwksServer startServer() {
        try {
            return new LocalJwksServer();
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    @DynamicPropertySource
    static void decoderProperties(DynamicPropertyRegistry registry) {
        registry.add("training.jwt.jwks-uri", JWKS::url);
        registry.add("training.jwt.issuer",
                () -> ReactiveJwtFixture.ISSUER);
    }

    @Autowired
    ApplicationContext context;

    WebTestClient webTestClient;

    @BeforeEach
    void setUp() {
        webTestClient = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void realSignatureIsAccepted_butForgeryIsRejected()
            throws Exception {
        var trustedKey = ReactiveJwtFixture.key("k1");
        var otherPrivateKey = ReactiveJwtFixture.key("k1");
        JWKS.publish(ReactiveJwtFixture.publicJwks(trustedKey));

        String valid = ReactiveJwtFixture.signedToken(trustedKey);
        String forged = ReactiveJwtFixture.signedToken(otherPrivateKey);

        webTestClient.get()
                .uri("/api/reports/q4")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + valid)
                .exchange()
                .expectStatus().isOk();

        webTestClient.get()
                .uri("/api/reports/q4")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + forged)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @AfterAll
    static void stopServer() {
        JWKS.close();
    }
}
```

Hai keypair ở trên cố tình có **cùng `kid=k1` nhưng private key khác nhau**: token giả mạo có header chỉ tới `kid` tồn tại trong JWKS song chữ ký không khớp public key đáng tin. Vì vậy ca thứ hai phải bị từ chối; tìm được `kid` không có nghĩa signature hợp lệ.

Test này sử dụng `DefaultReportService` thật để request hợp lệ có thể trả 200. Nếu muốn kiểm tra tác dụng phụ khi từ chối, mock **dependency nghiệp vụ**, nhưng không mock decoder. Để đo `iss`, `aud` và `exp`, tạo thêm token ký bằng **trustedKey** song có claims không hợp lệ rồi kỳ vọng xác thực thất bại. Không ghi nguyên raw token vào log kết quả.

> Nếu JWKS server HTTP thật trả 503/timeout hoặc cache chưa có khóa, lỗi có thể được ánh xạ tùy cấu hình exception handling. Không chỉ assert một status ngẫu nhiên: cần bảo đảm request không vào nghiệp vụ và kiểm tra loại lỗi/telemetry phù hợp. Test signature sai và issuer/audience sai thường kỳ vọng 401 dưới Bearer entry point mặc định.

## 8. Các test quan trọng theo từng tầng

| Trường hợp | A: mockJwt() | B: mock decoder | C: decoder thật |
|---|---|---|---|
| Có authority phù hợp → 200 | **Có** | Có | Có |
| Đã xác thực, thiếu authority → 403 | **Có** | **Có** | Có |
| Không gửi bearer token → 401 | Có, bằng request không mutate | Có | **Có** |
| Stub decoder trả `BadJwtException` → 401 | Không | **Có** | Không dùng stub |
| JWT chữ ký RSA sai → từ chối | Không | Không | **Có** |
| JWT hết hạn/sai issuer/sai audience → từ chối | Không | Không | **Có** |
| Cấu hình JWKS URI/`kid` sai hoặc mất mạng | Không | Không | **Có** |
| Converter từ claims → authorities được nối đúng | Không nếu cấp sẵn authorities | **Có, nếu test dùng claims và converter thật** | **Có** |
| Tốc độ chạy thấp, cô lập tốt | Rất tốt | Tốt | Cần fixture khóa/server và cache state được kiểm soát |

Thiết kế bộ kiểm thử tốt thường gồm nhiều test A để bao phủ rules, một số test B để bao phủ đường bearer và converter, cùng các ca C có mục tiêu bảo mật rõ ràng cho chữ ký/claims/JWKS. Không nên dùng một test C nặng cho mọi tổ hợp quyền đơn giản, nhưng cũng không dùng hàng trăm test A thay cho một ca xác thực chữ ký thật.

## 9. Các bẫy gây kết quả xanh giả

1. **`mockJwt().authorities(...)` cấp sẵn quyền**, nên không chứng minh claim JWT đã được converter của ứng dụng ánh xạ đúng.
2. **`@MockitoBean ReactiveJwtDecoder` bỏ qua signature và validators**; `Mono.just(jwt)` có thể đưa cả một JWT có `iss`/`aud`/`exp` sai vào luồng phân quyền.
3. **Dùng `@WithMockUser` trong bài test JWT** có thể kiểm tra luật authority đơn giản nhưng không đại diện cho `JwtAuthenticationToken`, bearer filter hay principal JWT.
4. **Dùng `SecurityMockMvcRequestPostProcessors.jwt()` với WebFlux** là trộn Servlet và Reactive. Chọn `SecurityMockServerConfigurers.mockJwt()` cho `WebTestClient` in-process.
5. **Chỉ kiểm tra 403**: một cấu hình từ chối mọi request vẫn có thể làm test “thiếu quyền” xanh. Luôn có ca quyền hợp lệ dẫn tới nghiệp vụ thành công.
6. **Quên kiểm soát cache giữa các test C**: decoder/context có thể giữ public JWKS từ ca trước; dùng test class/context riêng hoặc cơ chế invalidation nếu cần kịch bản cold cache.
7. **Tắt SecurityWebFilterChain trong WebFlux slice test**: test controller trả 200 không chứng minh security chạy. Bind đúng context và `apply(springSecurity())`.
8. **Mock service có `@PreAuthorize`** nếu mục tiêu test method security. Giữ bean bảo vệ thật và chỉ mock dependency phía sau.
9. **Trộn JWT Resource Server với OIDC Login**: ID Token của login không tương đương bearer Access Token của API.
10. **Mock publisher sai**: `ReactiveJwtDecoder.decode()` phải trả `Mono<Jwt>`; `null` từ Mockito mock không phải lỗi “JWT bị từ chối” mà là lỗi lập trình trong test.

## 10. Reactive context và cách xác minh request bị chặn

Spring Security WebFlux dùng Reactor context để mang `SecurityContext` xuyên qua pipeline. Gọi `SecurityContextHolder.getContext().setAuthentication(...)` trong thread của test (mô hình Servlet) **không phải cách tin cậy** để xác thực một HTTP request WebFlux. Các test configurer `mockJwt()` tạo context tương thích Reactive cho request in-process; khi gửi bearer token, authentication manager và decoder của server phải tạo context này.

Khi một request bị từ chối, assertion nên đi xa hơn HTTP status:

- Với `GET` chỉ đọc: xác minh service `read(...)` không được gọi, hoặc response không lộ dữ liệu.
- Với `POST` có tác dụng phụ: bảo đảm publisher nghiệp vụ không được subscribe/chạy; kiểm soát CSRF riêng nếu security chain có bật CSRF.
- Với method security: đừng để URL rule đã chặn sẵn nếu muốn đo đúng `@PreAuthorize`. Để request đi tới Spring-managed service rồi kiểm tra lỗi do interceptor.
- Với decoder thật: ghi nhận số lần tải JWKS, sự kiện lỗi xác thực và chính sách timeout; không ghi token/private key ra log.

## 11. Checklist trước khi kết luận “JWT Reactive đã được kiểm thử”

- [ ] Đã xác định mục tiêu là quyền sau authentication, converter/wiring, hay chữ ký và claims JWT thực sự.
- [ ] Với `mockJwt()`, nêu rõ không gọi `ReactiveJwtDecoder`; kiểm tra cả nhánh được phép và bị từ chối.
- [ ] Với mock decoder, gửi `Authorization: Bearer ...` và stub `Mono<Jwt>`/`Mono.error(...)`; kiểm tra converter và nghiệp vụ được gọi đúng.
- [ ] Với decoder thật, dùng JWT ký bằng RSA fixture, JWKS chỉ chứa khóa công khai và URI từ HTTP test server đáng tin.
- [ ] Có test chữ ký giả mạo, token hết hạn, sai issuer/audience và kết quả bị từ chối.
- [ ] Không kết luận từ `mockJwt().authorities(...)` rằng converter production đã chạy.
- [ ] `WebTestClient` bind-to-context đã `apply(springSecurity())` với `SecurityWebFilterChain` thật; nếu bind-to-server thì gửi credentials/token qua HTTP.
- [ ] Test không phụ thuộc IdP production, không chia sẻ JWKS cache ngoài kiểm soát, không ghi raw token hay khóa riêng.
- [ ] Các lỗi 401/403 và các tương tác nghiệp vụ được phân biệt; CSRF và method security không che khuất nguyên nhân thất bại.

**Kết luận:** `mockJwt()` giúp kiểm tra nhanh **hành vi sau khi đã có JWT authentication**; mock `ReactiveJwtDecoder` giúp kiểm tra **đường bearer → decoder output → converter → phân quyền**; decoder thật cùng JWT ký và JWKS cục bộ mới kiểm tra được **chữ ký, issuer, audience, thời gian và phụ thuộc mạng**. Dùng đúng tầng test sẽ giảm false positive và giữ bộ kiểm thử Reactive vừa nhanh vừa đáng tin cậy.
