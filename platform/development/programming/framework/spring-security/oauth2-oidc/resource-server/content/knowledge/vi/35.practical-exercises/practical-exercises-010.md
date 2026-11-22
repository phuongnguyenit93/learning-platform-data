# Viết kiểm thử mock danh tính và kiểm thử chữ ký, introspection thực tế

Một bộ kiểm thử Spring Security OAuth 2.0 Resource Server cần trả lời hai câu hỏi khác nhau:

1. Khi ứng dụng đã có một Authentication, controller, service và authorization rules có xử lý đúng principal, scope, role, tenant và quyền truy cập không?
2. Khi client gửi một Bearer token thật, Resource Server có trích xuất token, xác minh chữ ký JWT hoặc gọi introspection endpoint, kiểm tra kết quả và tạo Authentication đúng không?

Câu hỏi thứ nhất phù hợp với **mock identity tests**. Câu hỏi thứ hai cần **authentication integration tests** đi qua SecurityFilterChain và dùng decoder/introspector thật hoặc test server có HTTP contract tương ứng.

Spring Security cung cấp các helper như **jwt()**, **opaqueToken()**, **mockJwt()** và **mockOpaqueToken()** để tạo danh tính test nhanh. Những helper này không ký JWT, không kiểm tra chữ ký và không gọi Authorization Server. Nếu chỉ dùng chúng, test có thể chứng minh authorization policy hoạt động với một Authentication đã được dựng sẵn, nhưng không chứng minh access token ngoài đời được xác minh đúng.

Bài học xây dựng một test strategy hoàn chỉnh cho cả Servlet và WebFlux: mock danh tính cho policy, ký JWT bằng khóa test để kiểm chữ ký, gửi token qua HTTP introspection endpoint test để kiểm opaque-token flow, và kiểm tra các trường hợp token sai, inactive, thiếu scope hoặc gặp lỗi kết nối.

## 1. Ba lớp cần kiểm thử riêng

Resource Server xử lý request theo một chuỗi:

~~~mermaid
flowchart TD
    R[HTTP request + Authorization Bearer] --> E[Bearer token extraction]
    E --> V{JWT hay opaque?}
    V -->|JWT| D[JwtDecoder / ReactiveJwtDecoder]
    V -->|Opaque| I[OpaqueTokenIntrospector / ReactiveOpaqueTokenIntrospector]
    D -->|Chữ ký và claims hợp lệ| A[Authentication]
    I -->|active=true và attributes hợp lệ| A
    D -->|Invalid| U[Authentication failure]
    I -->|Inactive / lỗi xác minh| U
    A --> Z[Authorization: scope, role, tenant]
    Z -->|Đủ quyền| C[Controller / service]
    Z -->|Thiếu quyền| F[403 Forbidden]
~~~

Có thể chia test suite thành ba lớp:

| Lớp | Mục tiêu | Công cụ |
|---|---|---|
| Mock identity | Kiểm tra controller, service, scope, role, tenant, ownership | MockMvc + jwt()/opaqueToken(); WebTestClient + mockJwt()/mockOpaqueToken() |
| JWT signature | Kiểm tra Bearer extraction, chữ ký, issuer, audience, thời gian, thuật toán | JwtEncoder ký test token + JwtDecoder thật + SecurityFilterChain |
| Opaque introspection | Kiểm tra Bearer extraction, HTTP request, client authentication, active, scopes và attributes | Introspection HTTP test server + OpaqueTokenIntrospector thật |

Một test có thể đi qua nhiều lớp, nhưng cần biết nó đang chứng minh điều gì. Ví dụ mockMvc với jwt() vẫn chạy authorization filter chain nếu Spring Security filters được gắn, nhưng helper đưa JwtAuthenticationToken vào test context thay cho việc giải mã Bearer token.

## 2. Chọn helper theo loại danh tính

Không phải mọi Authentication đều giống nhau. Hãy chọn test helper dựa trên kiểu principal mà controller hoặc service thực sự nhận.

| Helper | Authentication / principal | Dùng khi |
|---|---|---|
| @WithMockUser hoặc user() | UsernamePasswordAuthenticationToken / UserDetails | Kiểm tra role hoặc method security tổng quát |
| jwt() | JwtAuthenticationToken / Jwt | Servlet Resource Server JWT authorization |
| opaqueToken() | BearerTokenAuthentication / OAuth2AuthenticatedPrincipal | Servlet Resource Server opaque-token authorization |
| mockJwt() | JwtAuthenticationToken / Jwt | WebFlux Resource Server JWT authorization |
| mockOpaqueToken() | BearerTokenAuthentication / OAuth2AuthenticatedPrincipal | WebFlux Resource Server opaque-token authorization |
| oidcLogin() / mockOidcLogin() | OAuth2AuthenticationToken / OidcUser | OAuth2/OIDC Login flow |

**OIDC Login và Resource Server Bearer authentication là hai flow khác nhau.** Nếu API nhận access token trong Authorization header, không dùng oidcLogin() chỉ vì hệ thống có OpenID Connect.

### 2.1. Dependency kiểm thử

Với Spring Boot dependency management, thêm test module tương thích với Spring Security runtime:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Khi kiểm tra JWT ký thật, ứng dụng còn cần module JOSE phù hợp. Khi dùng NimbusJwtEncoder/NimbusJwtDecoder, dependency quản lý phiên bản Spring Security/Nimbus theo BOM của dự án.

Để dựng một HTTP introspection endpoint cục bộ trong test, có thể dùng MockWebServer:

~~~groovy
dependencies {
    testImplementation("com.squareup.okhttp3:mockwebserver")
}
~~~

Hãy dùng phiên bản MockWebServer tương thích với OkHttp mà dự án quản lý. Các test examples bên dưới dùng token và credentials giả, không dùng secret production.

## 3. Mock identity trong Servlet với MockMvc

Spring Security Test cung cấp RequestPostProcessor cho MockMvc. Các helper đưa Authentication vào request test để authorization rules và controller có thể sử dụng.

### 3.1. JWT với jwt()

Ví dụ controller:

~~~java
@RestController
class OrderController {

    @GetMapping("/api/orders")
    List<String> orders(@AuthenticationPrincipal Jwt jwt) {
        return List.of(
            jwt.getSubject(),
            jwt.getClaimAsString("tenant_id")
        );
    }
}
~~~

Test:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void authenticatedUserCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-a")
                .claim("scope", "orders.read")
            )))
        .andExpect(status().isOk());
}
~~~

JWT mặc định do helper tạo có header alg=none và claims sub=user, scope=read. Có thể tùy chỉnh header, claims và authorities theo scenario.

**jwt() không xác minh chữ ký.** Nó tạo JwtAuthenticationToken cho test. Dùng helper này khi mục tiêu là kiểm tra authorization hoặc cách controller đọc claims.

### 3.2. Cấp authority trực tiếp

Nếu chỉ muốn kiểm tra một rule cụ thể:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

Cách này bỏ qua bước chuyển scope claim thành authority. Nếu muốn kiểm tra custom JwtAuthenticationConverter, hãy cung cấp claims và để converter production chạy trong filter chain hoặc kiểm tra converter độc lập.

### 3.3. Kiểm tra scope bị thiếu

~~~java
@Test
void writeOnlyTokenCannotReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            )))
        .andExpect(status().isForbidden());
}
~~~

Test này chứng minh rule đọc yêu cầu SCOPE_orders.read. Nó không chứng minh token được ký hoặc decoder từ chối token sai chữ ký.

### 3.4. Opaque principal với opaqueToken()

Với controller nhận BearerTokenAuthentication:

~~~java
@GetMapping("/api/profile")
String profile(BearerTokenAuthentication authentication) {
    return (String) authentication.getTokenAttributes().get("sub");
}
~~~

Test:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void opaquePrincipalProvidesSubject() throws Exception {
    mvc.perform(get("/api/profile")
            .with(opaqueToken()
                .attributes(attributes -> {
                    attributes.put("sub", "alice");
                    attributes.put("tenant_id", "tenant-a");
                })
            ))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
}
~~~

Mặc định opaqueToken() tạo BearerTokenAuthentication với principal có sub=user và authority SCOPE_read. Có thể thay attributes, authorities hoặc cung cấp principal hoàn chỉnh.

### 3.5. Role test với @WithMockUser

~~~java
@Test
@WithMockUser(username = "admin", roles = "ADMIN")
void adminCanDeleteOrder() throws Exception {
    mvc.perform(delete("/api/orders/42"))
        .andExpect(status().isNoContent());
}
~~~

roles="ADMIN" tạo authority ROLE_ADMIN. Test này phù hợp với role-based policy tổng quát. Nếu endpoint cần BearerTokenAuthentication hoặc Jwt claims, dùng helper OAuth2 phù hợp.

## 4. Mock identity trong WebFlux với WebTestClient

Với WebFlux, Spring Security Test cung cấp WebTestClientConfigurer để đưa Authentication vào ServerWebExchange.

### 4.1. JWT với mockJwt()

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

@Test
void jwtPrincipalCanReadOrders() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
            .claim("sub", "alice")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read")
        ))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

mockJwt() tạo JwtAuthenticationToken test và đưa nó vào security context. Nó không gửi JWT compact qua Bearer filter và không gọi ReactiveJwtDecoder.

### 4.2. Opaque principal với mockOpaqueToken()

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

@Test
void opaquePrincipalCanReadOrders() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
                attributes.put("scope", "orders.read");
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        )
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

mockOpaqueToken() tạo BearerTokenAuthentication với OAuth2AuthenticatedPrincipal. Helper mặc định dùng sub=user, scope=read và SCOPE_read.

### 4.3. Gắn Spring Security vào WebTestClient

Khi bind client vào application context, bảo đảm Spring Security filter chain được áp dụng:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Với Spring Boot WebFlux integration test, có thể dùng WebTestClient được auto-configure. Với WebFlux slice test, cần import SecurityWebFilterChain và các bean phụ thuộc phù hợp.

### 4.4. Kiểm tra reactive method security

Nếu service dùng @PreAuthorize, bật @EnableReactiveMethodSecurity và gọi service bean được Spring quản lý. Mock identity có thể kiểm authority/tenant policy ở service boundary, nhưng không thay test introspection hoặc JWT signature.

## 5. Mock authentication không tương đương mock decoder

Có ba cách test thường bị nhầm:

| Cách | Bearer token extraction | Decoder/introspector thật | Authorization |
|---|---:|---:|---:|
| jwt()/mockJwt() | Không | Không | Có |
| opaqueToken()/mockOpaqueToken() | Không | Không | Có |
| Mock JwtDecoder / Mock Introspector trong filter chain | Có | Không, dùng test double | Có |
| Signed JWT + decoder thật | Có | JWT decoder thật | Có |
| Bearer token + HTTP introspection test server | Có | Introspector thật gọi HTTP | Có |

Mock decoder có thể hữu ích để kiểm tra BearerTokenAuthenticationFilter, xử lý exception và ánh xạ Authentication. Nhưng nó không kiểm tra chữ ký.

Tương tự, mock introspector có thể kiểm tra integration giữa provider và một principal test. Nó không chứng minh HTTP request tới Authorization Server được tạo đúng.

## 6. Ký JWT bằng khóa RSA test

Để kiểm tra chữ ký thực, test cần:

1. Tạo RSA key pair chỉ dùng trong test.
2. Dùng private key ký JWT.
3. Cấu hình Resource Server decoder với public key tương ứng.
4. Gửi compact JWT qua Authorization: Bearer.
5. Để SecurityFilterChain gọi decoder và xác minh chữ ký.
6. Kiểm cả token hợp lệ và token sai.

Private key chỉ dùng để ký test token. Resource Server chỉ được cung cấp public key để xác minh.

### 6.1. Tạo test key và encoder

Ví dụ Spring Security với Nimbus:

~~~java
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.TestConfiguration;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;

@TestConfiguration
class JwtTestConfiguration {

    @Bean
    RSAKey testRsaKey() throws JOSEException {
        return new RSAKeyGenerator(2048)
            .keyID("test-key")
            .generate();
    }

    @Bean
    JwtEncoder testJwtEncoder(RSAKey testRsaKey) {
        JWKSource<SecurityContext> source =
            new ImmutableJWKSet<>(new JWKSet(testRsaKey));

        return new NimbusJwtEncoder(source);
    }
}
~~~

RSA key được tạo khi test context khởi tạo. Không commit private key hoặc tái sử dụng test key này trong môi trường thật.

### 6.2. Cấu hình decoder bằng public key

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@TestConfiguration
class JwtDecoderTestConfiguration {

    static final String ISSUER = "https://issuer.test";
    static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder testJwtDecoder(RSAKey testRsaKey) throws JOSEException {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withPublicKey(testRsaKey.toRSAPublicKey())
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Required audience is missing",
                    null
                )
            );
        };

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

Decoder sử dụng public key để verify RS256 signature. Default validators kiểm issuer và thời gian; audience validator kiểm Resource Server nhận token đúng audience.

Nếu cấu hình thực tế còn có tenant, token profile hoặc claim bắt buộc, thêm validator tương ứng vào chain. Không thay toàn bộ default validators bằng một validator chỉ kiểm audience.

### 6.3. Tạo JWT đã ký cho từng test

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;

String signedToken(
        JwtEncoder encoder,
        String issuer,
        String audience,
        Instant issuedAt,
        Instant expiresAt) {

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(issuer)
        .subject("alice")
        .audience(List.of(audience))
        .issuedAt(issuedAt)
        .expiresAt(expiresAt)
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")
        .build();

    JwsHeader headers = JwsHeader
        .with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(headers, claims)
    ).getTokenValue();
}
~~~

Token được ký bằng private key trong JWK source. Sau đó Resource Server nhận compact token và tự xác minh bằng public key đã cấu hình.

### 6.4. Gửi token đã ký qua MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Import({JwtTestConfiguration.class, JwtDecoderTestConfiguration.class})
class SignedJwtResourceServerTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    JwtEncoder jwtEncoder;

    @Test
    void validSignedJwtPassesAuthenticationAndAuthorization() throws Exception {
        Instant now = Instant.now();

        String token = signedToken(
            jwtEncoder,
            JwtDecoderTestConfiguration.ISSUER,
            JwtDecoderTestConfiguration.AUDIENCE,
            now.minusSeconds(10),
            now.plusSeconds(300)
        );

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk());
    }
}
~~~

Đây là integration test đi qua Bearer token extraction và decoder. Không gọi jwt() hoặc authentication() trong request.

Test phải dùng SecurityFilterChain thực tế hoặc một chain test có cùng cấu hình Resource Server, authorization và validators cần kiểm.

## 7. Test JWT sai chữ ký, issuer, audience và thời hạn

Một bộ test chỉ có token hợp lệ chưa đủ. Cần chứng minh decoder từ chối những token gần giống nhưng vi phạm từng điều kiện.

### 7.1. Token ký bằng key không được tin cậy

Tạo một RSA key pair thứ hai và encoder riêng:

~~~java
RSAKey otherKey = new RSAKeyGenerator(2048)
    .keyID("other-key")
    .generate();

JwtEncoder attackerEncoder = new NimbusJwtEncoder(
    new ImmutableJWKSet<>(
        new JWKSet(otherKey)
    )
);
~~~

Dùng encoder đó tạo JWT có issuer/audience hợp lệ nhưng chữ ký bằng private key khác. Gửi token qua Authorization header và kỳ vọng authentication thất bại.

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + tokenSignedByOtherKey))
    .andExpect(status().isUnauthorized());
~~~

Đây là kiểm tra chữ ký thực: decoder không có public key tương ứng nên không xác minh được JWS.

### 7.2. Token sai issuer

Ký token bằng đúng test private key nhưng claim iss không đúng issuer được cấu hình. Chữ ký hợp lệ vẫn phải bị từ chối do issuer validator.

### 7.3. Token sai audience

Ký token với audience billing-api thay vì orders-api. Decoder xác minh được chữ ký nhưng audience validator phải từ chối.

### 7.4. Token hết hạn hoặc chưa có hiệu lực

Dùng expiresAt ở quá khứ hoặc notBefore ở tương lai. Kiểm tra clock skew theo cấu hình của ứng dụng.

### 7.5. Phân biệt nguyên nhân 401

| Scenario | Kết quả dự kiến |
|---|---|
| Không có Bearer token trên protected endpoint | 401 |
| Token malformed | 401 |
| Chữ ký sai | 401 |
| Issuer sai | 401 |
| Audience sai | 401 |
| Token hết hạn | 401 |
| Token hợp lệ nhưng thiếu scope | 403 |
| Token hợp lệ, đủ scope và đúng tenant | Qua authorization |

401 thường cho biết authentication thất bại; 403 thường cho biết đã authenticated nhưng không đủ quyền. Hãy kiểm tra response và log test để biết layer nào từ chối.

## 8. Kiểm tra JWKS endpoint thật qua HTTP test server

Decoder dùng public key trực tiếp kiểm chữ ký nhưng không kiểm quá trình lấy key từ JWKS endpoint.

Nếu ứng dụng cấu hình jwk-set-uri, nên có thêm test cho:

- HTTP GET tới JWKS URI.
- JSON JWK Set được parse.
- kid trong JWT chọn đúng key.
- Cache key set được tái sử dụng.
- Key rotation và unknown kid.
- JWKS timeout hoặc HTTP 5xx.
- Key của issuer khác không được dùng nhầm.

Có thể dùng MockWebServer trả JWK Set public key:

~~~java
String jwksJson = new JWKSet(testRsaKey.toPublicJWK()).toString();

server.enqueue(
    new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody(jwksJson)
);
~~~

Cấu hình decoder dùng server.url("/jwks") làm JWK Set URI, sau đó gửi JWT được ký bằng private key tương ứng qua SecurityFilterChain.

Sau request, kiểm tra server nhận GET /jwks. Test này kiểm tra cả signature verification và JWKS HTTP retrieval. Đây vẫn là test server cục bộ, không phải Authorization Server production.

## 9. Introspection thực tế: gửi Bearer token qua HTTP endpoint

Với opaque token, Resource Server gọi Authorization Server introspection endpoint. Spring Security Servlet sử dụng OpaqueTokenAuthenticationProvider cùng OpaqueTokenIntrospector; WebFlux dùng reactive tương ứng.

Luồng Servlet:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Introspection test server

    C->>F: Authorization: Bearer opaque-token
    F->>P: BearerTokenAuthenticationToken
    P->>I: introspect(opaque-token)
    I->>AS: POST /introspect + client authentication
    AS-->>I: active=true, sub, scope
    I-->>P: OAuth2AuthenticatedPrincipal
    P-->>F: BearerTokenAuthentication
    F-->>C: Continue to authorization/controller
~~~

Khác với opaqueToken(), request này thực sự gọi introspection HTTP client. Test server có thể xác nhận request body, client authentication và response parsing.

### 9.1. Dựng introspection endpoint bằng MockWebServer

Khởi động server trước test:

~~~java
static MockWebServer introspectionServer;

@BeforeAll
static void startServer() throws IOException {
    introspectionServer = new MockWebServer();
    introspectionServer.start();
}

@AfterAll
static void stopServer() throws IOException {
    introspectionServer.shutdown();
}
~~~

Cấu hình introspector dùng URL local:

~~~java
@Bean
OpaqueTokenIntrospector testIntrospector() {
    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(
            introspectionServer.url("/introspect").toString()
        )
        .clientId("resource-server")
        .clientSecret("test-secret")
        .build();
}
~~~

Trong test application, gắn introspector vào SecurityFilterChain:

~~~java
@Bean
SecurityFilterChain testSecurity(
        HttpSecurity http,
        OpaqueTokenIntrospector testIntrospector) throws Exception {

    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque
                .introspector(testIntrospector)
            )
        )
        .build();
}
~~~

Nếu ứng dụng đã có SecurityFilterChain production, test nên thay endpoint/credentials hoặc introspector bằng test configuration nhưng giữ nguyên các authorization rules đang cần kiểm.

### 9.2. Test token active

Trước khi gọi endpoint, enqueue response:

~~~java
introspectionServer.enqueue(
    new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("""
            {
              "active": true,
              "sub": "alice",
              "scope": "orders.read",
              "tenant_id": "tenant-a",
              "aud": ["orders-api"]
            }
            """)
);
~~~

Gửi Bearer token bình thường:

~~~java
mvc.perform(get("/api/orders")
        .header(
            HttpHeaders.AUTHORIZATION,
            "Bearer opaque-test-token"
        ))
    .andExpect(status().isOk());
~~~

Sau request, kiểm tra introspection server:

~~~java
RecordedRequest request =
    introspectionServer.takeRequest(1, TimeUnit.SECONDS);

assertThat(request).isNotNull();
assertThat(request.getMethod()).isEqualTo("POST");
assertThat(request.getPath()).isEqualTo("/introspect");
assertThat(request.getHeader("Authorization"))
    .startsWith("Basic ");
assertThat(request.getBody().readUtf8())
    .contains("token=opaque-test-token");
~~~

Điều này chứng minh Resource Server đã gửi token tới endpoint, dùng client authentication và nhận response để tạo principal. Token test là chuỗi opaque giả, không phải access token production.

### 9.3. Kiểm tra client authentication

Nếu dùng HTTP Basic, có thể xác minh header được tạo từ test client ID/secret:

~~~java
String credentials = "resource-server:test-secret";
String encoded = Base64.getEncoder().encodeToString(
    credentials.getBytes(StandardCharsets.UTF_8)
);

assertThat(request.getHeader("Authorization"))
    .isEqualTo("Basic " + encoded);
~~~

Không ghi client secret thật vào test output. Nếu test credentials có ký tự đặc biệt, kiểm tra đúng encoding contract của Spring Security builder để phát hiện double-encoding.

### 9.4. Token inactive

Enqueue:

~~~java
introspectionServer.enqueue(
    new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("""
            {
              "active": false
            }
            """)
);
~~~

Gửi Bearer token và kỳ vọng authentication thất bại, thường là 401. Controller không được thực thi.

### 9.5. Token active nhưng thiếu scope

Enqueue:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.write"
}
~~~

Request GET /api/orders phải bị từ chối bởi authorization, thường là 403. Đây là khác biệt quan trọng:

- active=false: token không được xác thực.
- active=true nhưng thiếu orders.read: token được xác thực nhưng không đủ quyền.

## 10. Introspection với WebFlux

Reactive Resource Server sử dụng ReactiveOpaqueTokenIntrospector. Trong test có thể tạo introspector trỏ tới MockWebServer:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector testReactiveIntrospector() {
    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(
            introspectionServer.url("/introspect").toString()
        )
        .clientId("resource-server")
        .clientSecret("test-secret")
        .build();
}
~~~

Gắn vào SecurityWebFilterChain:

~~~java
@Bean
SecurityWebFilterChain testReactiveSecurity(
        ServerHttpSecurity http,
        ReactiveOpaqueTokenIntrospector testReactiveIntrospector) {

    return http
        .authorizeExchange(authorize -> authorize
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque
                .introspector(testReactiveIntrospector)
            )
        )
        .build();
}
~~~

Gửi Bearer token qua WebTestClient:

~~~java
webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers -> headers.setBearerAuth("opaque-test-token"))
    .exchange()
    .expectStatus().isOk();
~~~

Sau đó lấy RecordedRequest từ MockWebServer để kiểm tra POST path, Basic authentication và form body.

Đây là test qua reactive filter chain và reactive HTTP client. Không dùng mockOpaqueToken() trong scenario này vì helper sẽ đưa BearerTokenAuthentication vào test exchange mà không gọi introspector.

## 11. Test lỗi introspection và behavior fail-closed

Không chỉ test response active=true. Các tình huống sau cần được bao phủ:

| Introspection response | Kết quả cần xác nhận |
|---|---|
| active=true, scope đúng | Authentication thành công, authorization có thể cho phép |
| active=true, scope thiếu | Authentication thành công, authorization từ chối |
| active=false | Authentication thất bại |
| HTTP 401/403 từ AS | Client authentication/configuration failure |
| HTTP 5xx | Không tạo Authentication thành công |
| Timeout | Không fail-open |
| JSON malformed | Không tạo principal giả |
| Thiếu claim bắt buộc | Policy/mapping xử lý rõ |
| Sai kiểu dữ liệu | Không phát sinh quyền ngoài ý muốn |

Không khẳng định mọi lỗi AS phải trả cùng một HTTP status. Entry point và exception translation có thể khác theo lỗi. Điều quan trọng là request không được coi là authenticated khi không có kết quả introspection hợp lệ.

### 11.1. Không mock response khi mục tiêu là HTTP integration

Nếu dùng:

~~~java
when(introspector.introspect("opaque-token"))
    .thenReturn(principal);
~~~

test chỉ chứng minh provider gọi mock introspector. Nó không kiểm tra HTTP method, URL, body, client credentials, JSON parser, timeout hoặc response active.

Dùng HTTP test server khi cần kiểm những phần đó.

### 11.2. Test với Authorization Server thật

MockWebServer kiểm tra HTTP contract của client bằng response do test kiểm soát. Nó không chứng minh Authorization Server thực tế có policy đúng.

Với release quan trọng, có thể bổ sung một bộ contract/integration test với Authorization Server sandbox hoặc Testcontainers:

- Tạo client riêng cho test.
- Xin access token theo grant phù hợp.
- Gửi JWT/opaque token tới Resource Server.
- Thu hồi token opaque nếu AS hỗ trợ.
- Xác nhận introspection trả active=false sau revoke theo SLA.
- Xác nhận audience/scope và issuer policy.
- Dọn client, user và token test sau khi chạy.

Không dùng môi trường production hoặc credentials production cho test suite.

## 12. JWT có thể được xác minh bằng introspection

JWT thường được xác minh cục bộ bằng chữ ký và claims. Tuy nhiên, một hệ thống có thể chọn gọi introspection cho JWT nếu cần kiểm tra trạng thái thu hồi tại Authorization Server trên mỗi request.

Trong trường hợp này, Resource Server dùng Opaque Token support để gửi token tới introspection endpoint. Authentication được tạo theo opaque-token flow và principal attributes đến từ introspection response.

Đừng nhầm hai chế độ:

| Chế độ | Cách xác minh | Kiểm tra trong test |
|---|---|---|
| JWT decoder | Signature, issuer, audience, timestamps, type | Ký JWT và gửi qua JwtDecoder thật |
| Introspection, kể cả token có định dạng JWT | AS trả active và attributes | Gửi Bearer token qua introspection endpoint |
| Mock JWT | Authentication test được inject | Authorization/controller |
| Mock opaque | BearerTokenAuthentication test được inject | Authorization/controller |

Nếu dùng introspection cho JWT, test cần xác nhận introspection endpoint thực sự được gọi. Không dùng test chữ ký để kết luận revocation được kiểm tra.

## 13. Mock decoder/introspector trong test filter chain

Có một mức trung gian hữu ích: gửi Authorization Bearer qua filter chain nhưng thay decoder hoặc introspector bằng test double.

### 13.1. Mock JwtDecoder

Khi decoder được mock:

- BearerTokenAuthenticationFilter vẫn trích xuất token.
- Authentication provider vẫn gọi decoder.
- Test có thể xác nhận token string được truyền đúng.
- Test có thể kiểm exception mapping và authorization.
- Không kiểm chữ ký hoặc validators thật.

Ví dụ:

~~~java
when(jwtDecoder.decode("test-token"))
    .thenReturn(testJwt);
~~~

Gửi request:

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-token"))
    .andExpect(status().isOk());
~~~

### 13.2. Mock OpaqueTokenIntrospector

Tương tự, mock introspector có thể xác nhận token được truyền tới introspector và principal được đưa vào Authentication.

Nhưng HTTP client và introspection response parsing vẫn chưa được kiểm.

### 13.3. Dùng test double đúng mục đích

| Test double | Kiểm được | Không kiểm được |
|---|---|---|
| Mock Authentication helper | Authorization và principal binding | Bearer extraction, decoder, introspection |
| Mock JwtDecoder | Bearer extraction, provider/filter integration | Cryptographic signature, claims validators |
| Mock OpaqueTokenIntrospector | Bearer extraction, provider integration | HTTP request/response, client auth |
| Local introspection HTTP server | HTTP client, body, credentials, response parsing | Authorization Server production policy |
| Real Authorization Server sandbox | Contract giữa AS và Resource Server | Không thay thế test đơn vị nhanh |

## 14. Kiểm tra SecurityFilterChain có thật sự chạy

Một test có thể trả 200 dù security filters không được gắn. Khi mục tiêu là kiểm Resource Server, phải xác nhận test harness sử dụng filter chain.

### 14.1. MockMvc

Với Spring Boot:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerTests {

    @Autowired
    MockMvc mvc;
}
~~~

Không dùng **addFilters = false** trong test muốn xác minh Bearer token. Với MockMvc tự tạo qua WebApplicationContext, áp dụng springSecurity().

### 14.2. WebTestClient

Với application context:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Nếu test bind trực tiếp vào controller bằng bindToController(), test có thể bỏ qua phần lớn security configuration. Dùng application context hoặc chạy server integration khi cần xác nhận filter chain.

### 14.3. CSRF và HTTP methods

Nếu CSRF đang bật, POST/PUT/PATCH/DELETE có thể bị từ chối trước khi scope authorization chạy. Với MockMvc, thêm csrf() cho test muốn tập trung vào scope/role, hoặc viết test CSRF riêng.

Không disable CSRF chỉ để làm test qua. Với API Bearer-only stateless, quyết định CSRF phải dựa trên cách credential được gửi và threat model.

## 15. Test tenant, subject và resource ownership

Authentication hợp lệ không có nghĩa principal được đọc mọi tài nguyên.

Giả sử endpoint yêu cầu:

- SCOPE_orders.read.
- tenant_id phải là tenant-a.
- subject phải là owner của order.
- Order phải tồn tại.

Test matrix:

| Principal | Scope | Tenant | Owner | Kết quả |
|---|---|---|---|---|
| Alice | orders.read | tenant-a | Alice | Cho phép |
| Alice | orders.write | tenant-a | Alice | Từ chối đọc |
| Bob | orders.read | tenant-a | Alice | Từ chối |
| Alice | orders.read | tenant-b | Alice | Từ chối |
| Alice | orders.read | tenant-a | Không tồn tại | 404 theo API contract |

Mock identity tests thích hợp để kiểm tra ma trận này nhanh. Sau đó, một số integration tests với signed JWT hoặc introspection principal xác nhận claims thực tế được đưa vào đúng field.

Đặc biệt, không lấy tenant hoặc subject từ query parameter để thay cho claim đã xác minh. Repository query nên giới hạn tenant/owner ngay từ database.

## 16. Kiểm thử custom authority mapping

Một token có thể chứa scope hoặc role claims theo contract riêng. Cần tách hai câu hỏi:

1. Decoder/introspector có xác minh token và trả claims đúng không?
2. Converter có ánh xạ claims thành GrantedAuthority đúng không?

Ví dụ JWT claim:

~~~json
{
  "sub": "alice",
  "scope": "orders.read",
  "roles": ["ORDER_MANAGER"]
}
~~~

Nếu custom JwtAuthenticationConverter map role thành ROLE_ORDER_MANAGER, có thể:

- Unit test converter với Jwt test object để kiểm mapping.
- Integration test signed JWT để kiểm decoder và converter cùng hoạt động.
- Negative test không có roles để bảo đảm không tự cấp quyền.

Opaque token tương tự: dùng introspection HTTP response có scope/roles và xác nhận authority sau authentication. Không suy ra ROLE_ADMIN chỉ vì response có attribute tên roles nếu application chưa cấu hình mapper.

## 17. Bảng tổng hợp test suite

Một bộ test thực hành có thể được tổ chức như sau:

| Nhóm | Test case | Công cụ | Điều chứng minh |
|---|---|---|---|
| Mock JWT | Đủ scope | jwt()/mockJwt() | Authorization |
| Mock JWT | Thiếu scope | jwt()/mockJwt() | 403 policy |
| Mock opaque | Attributes và principal name | opaqueToken()/mockOpaqueToken() | Controller binding |
| Role | Admin/user | @WithMockUser | Role policy |
| JWT thật | RSA signature hợp lệ | JwtEncoder + JwtDecoder | Cryptographic verification |
| JWT thật | Signature sai | Key khác | Decoder từ chối |
| JWT thật | Issuer/audience sai | Signed token claims khác | Claim validation |
| JWT thật | Expired | Signed token quá hạn | Timestamp validation |
| JWKS | Fetch key và key rotation | Local JWKS HTTP server | JWK retrieval/cache |
| Opaque thật | active=true | MockWebServer + real introspector | HTTP introspection |
| Opaque thật | active=false | MockWebServer + real introspector | Authentication rejection |
| Opaque thật | Thiếu scope | Introspection response | 403 authorization |
| Opaque lỗi | Timeout/5xx | HTTP test server | Fail-closed |
| Multi-tenant | Tenant mismatch | Signed token/introspection | Tenant isolation |
| Integration | AS sandbox | Testcontainers/sandbox | AS contract |

## 18. Các anti-pattern thường gặp

**Dùng jwt() rồi tuyên bố chữ ký JWT đã được kiểm tra.** Helper inject JwtAuthenticationToken, không gọi decoder.

**Dùng opaqueToken() rồi tuyên bố introspection đã chạy.** Helper inject BearerTokenAuthentication, không gọi endpoint.

**Mock JwtDecoder trong test được gọi là signature integration test.** Mock decoder không xác minh JWS.

**Mock introspector rồi kết luận HTTP Basic và body đúng.** Mock không gửi HTTP request.

**Chỉ test token hợp lệ.** Cần wrong key, issuer, audience, expiration, inactive token và thiếu scope.

**Tắt Security filters để test dễ xanh.** Kết quả không chứng minh Resource Server hoạt động.

**Nhầm OIDC Login với Resource Server.** oidcLogin() không thay thế Bearer access-token flow.

**Dùng test key production.** Private key test phải được tạo riêng và không tái sử dụng.

**Đưa secret thật vào MockWebServer fixture.** Chỉ dùng credentials giả.

**Không kiểm introspection request.** Test status 200 đơn lẻ chưa chứng minh token đã được gửi tới endpoint mong đợi.

**Không phân biệt 401 và 403.** Token inactive và token thiếu scope là hai kết quả khác nhau.

**Chỉ kiểm direct JwtDecoder.decode().** Có thể bỏ sót Bearer extraction, SecurityFilterChain và exception translation; cần thêm HTTP request integration test.

**Không test JWKS nếu ứng dụng dùng remote JWK Set.** Public-key unit test không kiểm HTTP fetch, cache hoặc key rotation.

**Retry hoặc fail-open khi introspection endpoint lỗi.** Không có kết quả xác minh tin cậy thì không tạo Authentication thành công.

## 19. Quy trình triển khai test strategy

**Bước 1 — Liệt kê Authentication types.** Xác định API dùng JWT, opaque token, OIDC Login hay session.

**Bước 2 — Viết mock identity tests.** Dùng jwt()/opaqueToken() cho Servlet và mockJwt()/mockOpaqueToken() cho WebFlux để kiểm controller, scope, role, tenant và ownership.

**Bước 3 — Test authority converters.** Kiểm scope, roles, custom claims và principal mapping riêng.

**Bước 4 — Tạo test signing keys.** Dùng RSA/EC key pair ephemeral; private key chỉ ký token test.

**Bước 5 — Gắn decoder thật.** Dùng public key hoặc JWKS test endpoint cùng issuer/audience/time validators.

**Bước 6 — Gửi Bearer token thật.** Không dùng authentication helper trong các test cần xác minh chữ ký.

**Bước 7 — Test token sai.** Signature, issuer, audience, typ, exp, nbf và algorithm không được tin cậy.

**Bước 8 — Dựng introspection HTTP test server.** Trả active=true/false, scope và attributes theo scenario.

**Bước 9 — Gửi Bearer token qua filter chain.** Kiểm POST, endpoint path, client authentication, token body và principal result.

**Bước 10 — Test lỗi AS.** 401/403, 5xx, timeout, JSON lỗi và response thiếu claim.

**Bước 11 — Test tenant và ownership.** Đúng scope nhưng sai tenant/owner vẫn phải bị từ chối.

**Bước 12 — Chạy AS contract tests khi cần.** Dùng sandbox hoặc Testcontainers để xác nhận hành vi thật của Authorization Server.

**Bước 13 — Giữ test harness đúng.** MockMvc/WebTestClient phải gắn Spring Security filters; không vô tình bỏ qua filter chain.

## 20. Câu hỏi tự kiểm tra

**1. jwt() và mockJwt() kiểm tra điều gì?**

Chúng tạo JwtAuthenticationToken test để kiểm tra authorization và cách ứng dụng sử dụng JWT claims.

**2. Hai helper đó có verify chữ ký không?**

Không. Chúng không gọi JwtDecoder.

**3. opaqueToken() và mockOpaqueToken() có gọi introspection endpoint không?**

Không. Chúng tạo BearerTokenAuthentication test với OAuth2AuthenticatedPrincipal.

**4. Muốn kiểm chữ ký JWT thật cần gì?**

JWT được ký bằng private key test, decoder thật dùng public key tương ứng, và request Bearer đi qua SecurityFilterChain.

**5. Vì sao cần test sai chữ ký?**

Để chứng minh decoder từ chối token không được ký bởi key tin cậy.

**6. Muốn kiểm JWKS retrieval cần test gì?**

Dựng JWKS HTTP endpoint test, gửi signed JWT qua decoder dùng JWK Set URI và kiểm request/key selection/cache.

**7. Muốn kiểm introspection HTTP cần gì?**

Bearer token thật qua filter chain, introspector thật trỏ tới HTTP test server và assertions về request/response.

**8. active=false khác thiếu scope thế nào?**

active=false làm authentication thất bại, thường 401. active=true nhưng thiếu scope dẫn tới authorization denial, thường 403.

**9. Mock decoder có chứng minh signature không?**

Không. Nó chỉ thay decoder trong test.

**10. MockWebServer có phải Authorization Server thật không?**

Không. Nó là HTTP test server giúp kiểm request/response contract của introspection client. AS sandbox cần thiết nếu muốn kiểm behavior phía Authorization Server.

**11. Khi nào dùng @WithMockUser?**

Khi test chỉ cần một principal/role tổng quát và không phụ thuộc Jwt hoặc BearerTokenAuthentication.

**12. Vì sao cần test qua SecurityFilterChain?**

Để xác nhận Bearer extraction, authentication provider, decoder/introspector, exception translation và authorization cùng hoạt động như request thực.

## Kết luận

Một test suite Resource Server tốt không chọn giữa mock và integration test; nó dùng mỗi loại cho đúng mục tiêu.

**Mock identity tests** chạy nhanh và tập trung vào controller, method security, scope, role, tenant và ownership. **JWT signature tests** phải ký token bằng private key test rồi gửi Bearer token qua decoder thật để xác minh bằng public key. **Opaque introspection tests** phải gửi Bearer token qua filter chain tới HTTP introspection endpoint và kiểm request, client authentication, active status, attributes và authorities.

Giữ các lớp test tách biệt giúp biết chính xác điều gì đã được chứng minh. jwt()/mockJwt() không kiểm chữ ký; opaqueToken()/mockOpaqueToken() không gọi introspection; mock decoder/introspector không kiểm cryptography hoặc HTTP. Khi cần kiểm toàn bộ đường đi, hãy dùng SecurityFilterChain thật, test keys, JWKS/introspection test server và cả positive lẫn negative cases.

**Kết quả cần đạt là token hợp lệ được xác minh và chỉ nhận đúng quyền; token sai chữ ký, sai issuer/audience, inactive, hết hạn hoặc thiếu quyền phải bị từ chối ở đúng tầng.**

### Tài liệu tham khảo

- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Testing OAuth 2.0 with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security API — NimbusJwtEncoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security API — SpringOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html)
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [OkHttp — MockWebServer](https://github.com/square/okhttp/tree/master/mockwebserver)
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
