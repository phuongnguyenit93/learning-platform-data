# MockMvc với Spring Security filter chain thực tế

Khi kiểm thử một **Spring Security Servlet Resource Server**, ta thường cần xác nhận rằng request HTTP đi qua đúng chuỗi filter đang được ứng dụng sử dụng: bearer token được trích xuất, `AuthenticationManager` được chọn, JWT hoặc opaque token được xác minh, `SecurityContext` được thiết lập, rule authorization được áp dụng và kết quả HTTP được trả về đúng.

`MockMvc` cho phép gửi request qua Spring MVC mà không cần mở cổng HTTP thật. Khi được cấu hình đúng, nó vẫn chạy **Spring Security `FilterChainProxy` và `SecurityFilterChain` thật** của application context. Điều này làm cho MockMvc phù hợp để kiểm thử nhiều hành vi quan trọng:

- Endpoint private từ chối request không có token.
- Bearer token sai chữ ký, issuer, audience hoặc hết hạn bị từ chối.
- Token hợp lệ được ánh xạ thành principal và authorities đúng.
- Scope thiếu dẫn tới 403.
- `SecurityFilterChain` đúng được chọn theo `securityMatcher` và `@Order`.
- CSRF, CORS, exception handling và method security hoạt động theo cấu hình.
- JWT decoder hoặc opaque introspector được gọi đúng trong đường xác thực.

Điểm cần phân biệt là **MockMvc có thể chạy filter chain thật nhưng test vẫn có thể mock authentication**. Ví dụ `.with(jwt())`, `.with(opaqueToken())` và `@WithMockUser` thường đưa một `Authentication` có sẵn vào `SecurityContext`; chúng rất hữu ích để test authorization nhưng không chứng minh bearer filter, decoder, chữ ký JWT, JWKS hay introspection hoạt động.

> **Nguyên tắc:** chọn mức kiểm thử theo câu hỏi cần trả lời. Dùng mock authentication để kiểm tra rule quyền; gửi `Authorization: Bearer ...` qua filter chain để kiểm tra authentication pipeline; dùng test key/JWKS server hoặc introspection server giả lập để kiểm tra xác minh token; dùng test server/network thật khi cần xác nhận TLS, proxy và hạ tầng.

Bài này tập trung vào **Spring Security Servlet với Spring MVC Test/MockMvc**. Ví dụ dùng Java 17+, JUnit 5, Spring Boot và Spring Security hiện đại. WebFlux sử dụng `WebTestClient` và `SecurityMockServerConfigurers`, không dùng `MockMvc`.

## 1. MockMvc thực sự kiểm thử phần nào?

MockMvc mô phỏng Servlet API và Spring MVC dispatch trong bộ nhớ. Khi có cấu hình Spring Security phù hợp, request vẫn đi qua filter chain trước khi tới `DispatcherServlet` và controller.

~~~text
MockMvc.perform(request)
        |
        v
Servlet filters được đăng ký
        |
        v
FilterChainProxy
        |
        v
SecurityFilterChain phù hợp đầu tiên
        |
        +-- SecurityContextHolderFilter
        +-- CsrfFilter (nếu bật)
        +-- BearerTokenAuthenticationFilter
        +-- AnonymousAuthenticationFilter
        +-- ExceptionTranslationFilter
        +-- AuthorizationFilter
        |
        v
DispatcherServlet
        |
        v
Controller / service
        |
        v
MockMvc ResultActions
~~~

Thứ tự filter cụ thể tùy cấu hình và phiên bản; sơ đồ trên mô tả các thành phần thường gặp, không phải danh sách đầy đủ hoặc thứ tự tuyệt đối cho mọi ứng dụng.

### 1.1. `FilterChainProxy` là điểm vào của Spring Security

Trong ứng dụng Servlet, Spring Security thường đăng ký một filter bean có tên:

~~~text
springSecurityFilterChain
~~~

Bean này thường là `FilterChainProxy`. Nó chứa danh sách `SecurityFilterChain`, kiểm tra request matchers theo thứ tự và chọn chain phù hợp.

Một ứng dụng có thể có:

~~~text
@Order(1) /api/admin/**  -> admin SecurityFilterChain
@Order(2) /api/**        -> API Resource Server chain
@Order(3) /**            -> browser/fallback chain
~~~

MockMvc chỉ kiểm tra được việc chọn chain nếu `FilterChainProxy` thực sự được gắn vào MockMvc request pipeline.

### 1.2. Những gì MockMvc không tự kiểm tra

MockMvc không mở socket HTTP và không tự mô phỏng toàn bộ hạ tầng triển khai. Vì vậy, nó không thay thế kiểm thử:

- TLS handshake, server certificate và client certificate thực.
- Reverse proxy, load balancer, ingress và forwarded headers ngoài đời.
- DNS, firewall, egress policy và network timeout thực.
- HTTP connection pooling giữa các process.
- Browser CORS enforcement thực tế.
- Hành vi của container production như Tomcat/Jetty/Undertow trong mọi chi tiết.
- OAuth Authorization Server thực, trừ khi test chủ động gọi một AS test.
- Cookie behavior của browser thật và SameSite policy trên browser.

MockMvc phù hợp cho **Servlet filter chain và MVC integration**; kiểm thử hạ tầng cần thêm integration test qua server thật hoặc môi trường staging.

## 2. Dependencies cần cho MockMvc và Spring Security Test

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test, MockMvc, AssertJ và Mockito theo dependency management của Spring Boot. `spring-security-test` cung cấp các annotation và request post processors như:

- `@WithMockUser`
- `@WithUserDetails`
- `user()`
- `jwt()`
- `opaqueToken()`
- `authentication()`
- `csrf()`
- `httpBasic()`
- `formLogin()`

Không cần tự đặt version riêng cho Spring Security Test nếu Spring Boot BOM đã quản lý version tương ứng. Trộn `spring-security-test` khác minor version với Spring Security runtime có thể gây lỗi method/class hoặc behavior khó chẩn đoán.

## 3. Cách chuẩn để gắn filter chain thật vào MockMvc

### 3.1. Dùng `webAppContextSetup` và `springSecurity()`

Khi tự tạo MockMvc từ `WebApplicationContext`, cách chuẩn là:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = Application.class)
class ApiSecurityTests {

    @Autowired
    WebApplicationContext context;

    MockMvc mvc;

    @BeforeEach
    void setUp() {
        this.mvc = MockMvcBuilders
            .webAppContextSetup(this.context)
            .apply(springSecurity())
            .build();
    }
}
~~~

`springSecurity()` cấu hình MockMvc với Spring Security. Cụ thể, nó thêm bean `springSecurityFilterChain` làm filter và thiết lập hỗ trợ `TestSecurityContextHolder` cho các request post processors/annotations.

Đây là điểm quan trọng: **không chỉ import một `SecurityFilterChain` bean rồi cho rằng MockMvc đã chạy nó**. Cần đảm bảo `FilterChainProxy` được đăng ký trong request pipeline.

### 3.2. Dùng `@SpringBootTest` và `@AutoConfigureMockMvc`

Với ứng dụng Spring Boot, cách thường dùng hơn là để Boot tạo MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrdersApiSecurityIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void requestWithoutTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

`@SpringBootTest` tải application context và `@AutoConfigureMockMvc` cấu hình MockMvc. Mặc định, MockMvc auto-configuration đăng ký các servlet filters của ứng dụng; Spring Security filter chain được áp dụng nếu filter bean nằm trong context.

Mặc định nên giữ `addFilters=true`. Cấu hình:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

làm MockMvc không đăng ký các filters của application context. Đây là một nguyên nhân phổ biến khiến test security trả 200 dù production sẽ trả 401/403. Không dùng tùy chọn này cho test nhằm xác nhận Spring Security filter chain.

### 3.3. Dùng `@WebMvcTest` cho slice test

`@WebMvcTest` chỉ tải phần MVC cần thiết, không khởi động toàn bộ ứng dụng. Có thể import security config thực tế:

~~~java
@WebMvcTest(controllers = OrdersController.class)
@Import(ApiSecurityConfiguration.class)
class OrdersControllerSecurityTests {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    OrdersService ordersService;
}
~~~

`@MockitoBean` là annotation của Spring Framework hiện đại để thay bean trong test context; với Spring Boot/Spring Framework cũ hơn, dự án có thể đang dùng `@MockBean`. Hãy chọn annotation phù hợp version dependency của dự án.

Lưu ý:

- Import đúng `SecurityFilterChain` production cần kiểm thử.
- Mock service/repository phụ thuộc để test tập trung vào MVC/security.
- Không import một `TestSecurityConfiguration` nới lỏng quyền rồi coi kết quả là production security.
- Nếu `@WebMvcTest` tự cấu hình security mặc định vì không tìm thấy config ứng dụng, hãy xác nhận chain thực tế được import.
- Không dùng `addFilters=false` nếu mục tiêu là test security.

### 3.4. Dùng `standaloneSetup` khi nào?

~~~java
MockMvcBuilders
    .standaloneSetup(new OrdersController(service))
    .build();
~~~

`standaloneSetup` tạo MockMvc từ controller được cung cấp, không tải `WebApplicationContext` đầy đủ. Nó phù hợp cho controller test nhỏ, nhưng không tự gắn toàn bộ `FilterChainProxy` của application.

Có thể thêm filter tường minh:

~~~java
MockMvcBuilders
    .standaloneSetup(controller)
    .apply(springSecurity(filterChainProxy))
    .build();
~~~

Cách này chỉ phù hợp khi ta chủ động cung cấp filter chain thật và hiểu những bean MVC/configuration nào còn thiếu. Với kiểm thử security integration, `webAppContextSetup` hoặc `@SpringBootTest` thường phản ánh ứng dụng tốt hơn.

### 3.5. Tránh đăng ký FilterChainProxy hai lần

Nếu đã dùng:

~~~java
.apply(springSecurity())
~~~

thì không thêm cùng `FilterChainProxy` lần nữa qua `.addFilters(...)` hoặc một cơ chế khác. Đăng ký filter trùng có thể khiến một request đi qua security chain nhiều lần, gây hành vi khó hiểu như CSRF/token processing lặp hoặc context bị thay đổi.

## 4. Phân biệt test filter chain thật với mock authentication

Đây là khác biệt quan trọng nhất khi viết test.

| Cách viết | Có chạy `FilterChainProxy`? | Có chạy Bearer filter? | Có gọi JWT decoder/introspector? | Dùng tốt cho |
|---|---:|---:|---:|---|
| `@SpringBootTest` + MockMvc + bearer header | Có | Có | Có nếu cấu hình thật | Integration security pipeline |
| `webAppContextSetup` + `springSecurity()` + bearer header | Có | Có | Có nếu cấu hình thật | Integration security pipeline |
| `.with(jwt())` | Có, nếu MockMvc gắn filter chain | Không theo đường bearer parsing thông thường | Không | Authorization với mock JWT |
| `.with(opaqueToken())` | Có, nếu filter chain được gắn | Không theo đường introspection thông thường | Không | Authorization với mock opaque principal |
| `.with(user("..."))` | Có, nếu filter chain được gắn | Không | Không | Rule authorization với user mock |
| `@WithMockUser` | Có, nếu filter chain được gắn | Không | Không | Method/HTTP authorization |
| `.with(authentication(...))` | Có, nếu filter chain được gắn | Không | Không | Kiểm thử rule với Authentication tự dựng |
| Mock `JwtDecoder` + bearer header | Có | Có | Decoder mock được gọi, không verify chữ ký thật | Bearer filter/provider wiring |
| Real `JwtDecoder` + signed test JWT | Có | Có | Có, xác minh chữ ký thật | JWT authentication integration |

**MockMvc thật và authentication thật là hai khái niệm khác nhau.** `.with(jwt())` có thể đi qua filter chain thật nhưng nó cài một JWT authentication mock vào request/security context, nên không chạy toàn bộ quá trình bearer token.

### 4.1. `jwt()` tạo một Jwt giả lập

Ví dụ:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt()))
    .andExpect(status().isOk());
~~~

Spring Security Test tạo một `Jwt` mẫu và đưa authentication phù hợp vào request. JWT mẫu mặc định có thể dùng header `alg=none`; nó không phải token JWS đã ký và không cần `JwtDecoder` xác minh.

Có thể tùy chỉnh claims:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("user-42")
            .claim("iss", "https://idp.example.com")
            .claim("aud", List.of("orders-api"))
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isOk());
~~~

Hoặc chỉ định authorities rõ:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

Khi truyền `.authorities(...)`, test kiểm soát trực tiếp danh sách quyền. Cách này hữu ích để test `hasAuthority`, nhưng không chứng minh `JwtAuthenticationConverter` production đã ánh xạ claims đúng.

### 4.2. `opaqueToken()` cũng tạo principal giả lập

~~~java
mvc.perform(get("/api/orders")
        .with(opaqueToken()))
    .andExpect(status().isOk());
~~~

Request post processor tạo một `BearerTokenAuthentication` mẫu với principal/attributes/authorities. Nó không cần gọi Authorization Server và không chạy `OpaqueTokenIntrospector` thật.

Có thể tùy chỉnh attributes và authorities:

~~~java
mvc.perform(get("/api/orders")
        .with(opaqueToken()
            .attributes(attrs -> attrs.put("sub", "user-42"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
    .andExpect(status().isOk());
~~~

Đây là cách kiểm tra authorization của opaque principal. Muốn kiểm tra client authentication, introspection URL, `active`, timeout hoặc response parsing, phải gửi bearer token qua filter chain với introspector thật và endpoint test.

### 4.3. `@WithMockUser` cũng không xác minh bearer token

~~~java
@Test
@WithMockUser(username = "mai", authorities = "SCOPE_orders.read")
void userCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isOk());
}
~~~

Annotation này thiết lập `SecurityContext` cho test. Nó không mô phỏng JWT, issuer, audience, signature, JWKS hay introspection. Dùng nó khi câu hỏi của test là “authority này được phép gọi route này không?”.

### 4.4. Không dùng `jwt()` để test 401 của JWT invalid

Ví dụ sai mục tiêu:

~~~java
@Test
void invalidJwtIsRejected() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt()))
        .andExpect(status().isUnauthorized());
}
~~~

`.with(jwt())` đã cung cấp một authentication mock, nên test không đưa chuỗi bearer invalid qua decoder. Nó không kiểm tra trường hợp chữ ký sai. Để test JWT invalid, gửi:

~~~http
Authorization: Bearer <malformed-or-invalid-token>
~~~

qua request bình thường, không gắn `.with(jwt())`.

## 5. Kiểm thử HTTP authorization với `jwt()` trước

Trước khi viết integration test token thật, có thể dùng các test ngắn để xác nhận scope policy.

Giả sử:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
)
~~~

Test:

~~~java
@Test
void readScopeCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void readScopeCannotCreateOrders() throws Exception {
    mvc.perform(post("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden());
}

@Test
void missingScopeCannotReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities()))
        .andExpect(status().isForbidden());
}
~~~

Nếu CSRF bật, các POST requests cần token CSRF hợp lệ. Xem phần 10.

Những test này giúp kiểm tra:

- Request matcher đúng route/method.
- Authority prefix đúng.
- Quy tắc đọc/ghi không bị đảo.
- `denyAll()` được áp dụng cho route không khai báo.

Chúng không kiểm tra nguồn gốc của authority. Nếu converter production đang tạo sai scope, cần thêm test converter hoặc integration test với token thật.

## 6. Kiểm thử bearer authentication qua filter chain thật

Để xác nhận Bearer filter hoạt động, gửi token trong `Authorization` header:

~~~java
@Test
void requestWithoutTokenIsUnauthorized() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());
}

@Test
void malformedBearerTokenIsRejected() throws Exception {
    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer not-a-jwt"))
        .andExpect(status().isUnauthorized());
}
~~~

Test này đi qua đường request thực của Spring Security trong MockMvc. Với JWT Resource Server, `BearerTokenAuthenticationFilter` trích xuất token và gọi authentication manager/provider; provider gọi decoder.

Nếu API dùng opaque token, request bearer token cũng đi qua filter, nhưng provider gọi `OpaqueTokenIntrospector`.

### 6.1. Kiểm tra WWW-Authenticate

Bearer authentication entry point thường trả challenge:

~~~java
mvc.perform(get("/api/orders"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("Bearer")
    ));
~~~

Nội dung challenge/error cụ thể phụ thuộc entry point và phiên bản. Không nên khóa test vào toàn bộ chuỗi message nội bộ nếu ứng dụng không có contract response cố định.

### 6.2. Phân biệt 401 và 403

| Tình huống | Kết quả thường gặp | Lý do |
|---|---|---|
| Không có token trên route private | 401 | Chưa authenticated |
| Bearer token malformed | 401 | Authentication thất bại |
| JWT signature sai | 401 | Token không hợp lệ |
| Issuer/audience sai | 401 | Claims validation thất bại |
| Token hợp lệ nhưng thiếu scope | 403 | Authentication thành công, authorization thất bại |
| User mock có authority sai | 403 | Không đủ quyền |
| CSRF token thiếu ở POST khi CSRF bật | 403 | CSRF filter từ chối |
| Request không match chain hoặc chain khác được chọn | Phụ thuộc chain được chọn | Phải kiểm tra filter-chain routing |

Một test chỉ assert 403 mà không xác định nguyên nhân có thể che lỗi: đó có thể là CSRF, authority thiếu hoặc custom access-denied handler. Hãy thiết kế test để biết filter nào từ chối request.

## 7. `@SpringBootTest` với JWT decoder thực và test key

Một integration test tốt cho JWT có thể dùng RSA key riêng của test. Ta ký JWT bằng private key và xác minh bằng public key. Như vậy không cần Authorization Server production, nhưng vẫn kiểm tra chữ ký thật.

### 7.1. Tạo test key pair

~~~java
@TestConfiguration
static class JwtTestConfiguration {

    static final String ISSUER =
        "https://idp.test.example/realms/orders";

    static final String AUDIENCE = "orders-api";

    @Bean
    KeyPair testRsaKeyPair() throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");

        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @Bean
    JwtEncoder testJwtEncoder(KeyPair testRsaKeyPair) {
        RSAKey rsaJwk = new RSAKey.Builder(
                (RSAPublicKey) testRsaKeyPair.getPublic())
            .privateKey((RSAPrivateKey) testRsaKeyPair.getPrivate())
            .keyID("test-key")
            .build();

        JWKSource<SecurityContext> jwkSource =
            new ImmutableJWKSet<>(new JWKSet(rsaJwk));

        return new NimbusJwtEncoder(jwkSource);
    }

    @Bean
    @Primary
    JwtDecoder testJwtDecoder(KeyPair testRsaKeyPair) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) testRsaKeyPair.getPublic())
            .signatureAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token"));

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

Các imports chính:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
~~~

Dòng `com.nimbusds.jose.jose.JWSAlgorithm` trong danh sách trên **không cần thiết và không phải import sử dụng trong ví dụ**; bỏ dòng đó khi tạo file Java. Các class Nimbus được quản lý bởi dependency OAuth2 JOSE của Spring Security.

Đây là test configuration dùng `JwtEncoder` để ký và `NimbusJwtDecoder` để verify. `@Primary` khiến decoder test được ưu tiên khi context còn có decoder khác; trong dự án thực tế, nên import cấu hình test một cách rõ ràng và tránh để decoder production gọi nhầm endpoint.

### 7.2. Tạo access token test đã ký

~~~java
private String signedToken(
        JwtEncoder encoder,
        String subject,
        List<String> scopes,
        Instant now) {

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(JwtTestConfiguration.ISSUER)
        .subject(subject)
        .audience(List.of(JwtTestConfiguration.AUDIENCE))
        .issuedAt(now)
        .expiresAt(now.plusSeconds(300))
        .claim("scope", String.join(" ", scopes))
        .build();

    JwsHeader headers = JwsHeader.with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(headers, claims)
    ).getTokenValue();
}
~~~

Imports:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.security.oauth2.jose.jws.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
~~~

Token này có chữ ký RSA thật từ private test key. Decoder sử dụng public test key để verify. Nó vẫn là test fixture; không dùng private key này trong bất kỳ môi trường production nào.

### 7.3. Gửi bearer token qua MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Import(JwtTestConfiguration.class)
class JwtFilterChainIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    JwtEncoder jwtEncoder;

    @Test
    void signedTokenWithReadScopeCanAccessOrders() throws Exception {
        String token = signedToken(
            jwtEncoder,
            "user-42",
            List.of("orders.read"),
            Instant.now()
        );

        mvc.perform(get("/api/orders")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + token
                ))
            .andExpect(status().isOk());
    }
}
~~~

Test này không dùng `.with(jwt())`. Vì vậy bearer token đi qua filter chain, provider và decoder test thực, bao gồm xác minh chữ ký.

### 7.4. Test chữ ký sai

Tạo một token được ký bằng **key pair khác** nhưng cùng issuer/audience. Decoder của ứng dụng không có public key tương ứng, nên chữ ký phải thất bại.

~~~text
Key A: test decoder tin cậy
Key B: attacker/test key khác

Token ký bằng Key B
  -> request Bearer
  -> decoder verify bằng public key A
  -> signature invalid
  -> 401
~~~

Không sửa payload của token đã ký rồi chỉ giữ chữ ký cũ; điều đó cũng tạo invalid signature nhưng không kiểm tra trường hợp key khác. Cả hai case có thể hữu ích.

### 7.5. Test issuer, audience và thời hạn

Dùng helper tạo token với các giá trị có thể thay đổi:

| Token | Expected |
|---|---|
| `iss` đúng, `aud=orders-api`, chữ ký đúng, còn hạn | Authentication thành công |
| `iss` khác | 401 |
| `aud=billing-api` | 401 |
| `exp` ở quá khứ | 401 |
| `nbf` trong tương lai ngoài clock skew | 401 |
| Signature sai | 401 |
| `alg` không nằm trong allowlist | 401 |

Khi test timestamp, đặt `Instant` rõ ràng thay vì dựa vào thời gian cố định đã qua. Nếu decoder sử dụng custom `Clock`, cấu hình clock test để tránh flaky test.

## 8. Kiểm thử JWKS HTTP thật bằng mock server

Test public key trực tiếp là đủ để xác nhận JWS verification, nhưng nó không kiểm tra HTTP fetch tới JWKS endpoint. Khi cần xác nhận `NimbusJwtDecoder` lấy keys đúng cách, hãy chạy một HTTP stub.

### 8.1. Luồng test JWKS

~~~text
Mock HTTP server
   |
   +-- GET /jwks
   |      |
   |      +-- Trả JWK Set chỉ chứa public test key
   |
Spring Resource Server
   |
   +-- JwtDecoder.withJwkSetUri(testServerUrl)
   |
MockMvc request với JWT ký bằng private test key
   |
   +-- Decoder fetch JWKS
   +-- Verify signature
   +-- Validate issuer/audience
   +-- Controller
~~~

Có thể dùng WireMock, MockWebServer hoặc HTTP stub mà dự án đang sử dụng. Không bắt buộc thêm một thư viện khác nếu test framework hiện tại đã có server giả lập.

### 8.2. JWK Set response

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "test-key",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-public-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Response chỉ chứa public key. Private key dùng ký JWT phải ở test fixture.

### 8.3. Điều cần assert

- Request tới đúng path JWKS.
- Không gọi JWKS endpoint khi test không cần key mới và cache còn hiệu lực.
- Token với `kid` phù hợp được verify.
- Token ký bằng key khác bị từ chối.
- Khi JWKS được cập nhật thêm key mới, decoder có thể lấy key mới theo refresh behavior.
- Khi JWKS timeout hoặc JSON sai, authentication không thành công.
- Unknown `kid` không làm Resource Server fetch URL do JWT header tùy ý.

Không khẳng định mỗi request JWT sẽ tạo một HTTP request JWKS; decoder có cache và hành vi refresh riêng.

## 9. Kiểm thử opaque token và introspection

### 9.1. Mock opaque token chỉ kiểm tra authorization

~~~java
mvc.perform(get("/api/orders")
        .with(opaqueToken()
            .attributes(attrs -> {
                attrs.put("sub", "user-42");
                attrs.put("aud", List.of("orders-api"));
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
    .andExpect(status().isOk());
~~~

Đây là test của HTTP authorization với một principal opaque giả lập. Nó không gọi introspection endpoint.

### 9.2. Kiểm tra introspection thật qua stub

Cấu hình `OpaqueTokenIntrospector` trỏ tới endpoint mock:

~~~text
POST /introspect
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <test-resource-server-credentials>
token=opaque-test-token
~~~

Stub response active:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "test-client",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

Stub response inactive:

~~~json
{
  "active": false
}
~~~

Gửi request thật:

~~~java
mvc.perform(get("/api/orders")
        .header(
            HttpHeaders.AUTHORIZATION,
            "Bearer opaque-test-token"
        ))
    .andExpect(status().isOk());
~~~

Test `active=false` phải xác nhận không có controller business action nào được gọi. Nếu introspection endpoint trả HTTP 401/403 do credentials sai, đó là lỗi cấu hình/resource-server client; không được tự coi response là active.

### 9.3. Những assertions hữu ích

- HTTP method là POST.
- Token nằm trong form body theo contract.
- Introspection client authentication đúng.
- Endpoint URL đúng môi trường test.
- `active=false` bị từ chối.
- Audience sai không được vào API nếu contract yêu cầu audience.
- Scope được ánh xạ thành `SCOPE_*`.
- Timeout hoặc 5xx không tạo authenticated principal.
- Không log raw token hoặc client secret.
- Cache behavior phù hợp revocation policy nếu có cache.

## 10. CSRF trong MockMvc

CSRF filter có thể làm một POST request bị 403 trước khi request tới controller hoặc authorization logic.

### 10.1. Thêm CSRF token cho request unsafe

~~~java
mvc.perform(post("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write")
        ))
        .with(csrf()))
    .andExpect(status().isCreated());
~~~

`csrf()` request post processor thêm CSRF token hợp lệ theo cơ chế test. Có thể gửi token qua header:

~~~java
mvc.perform(post("/api/orders")
        .with(user("mai"))
        .with(csrf().asHeader()))
    .andExpect(status().isCreated());
~~~

### 10.2. Test CSRF bị thiếu

~~~java
mvc.perform(post("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write")
        )))
    .andExpect(status().isForbidden());
~~~

Nếu CSRF đang bật, request có authentication và authority đúng vẫn có thể bị từ chối do thiếu CSRF token.

### 10.3. Khi nào API bearer-only tắt CSRF?

Một API chỉ nhận credential qua `Authorization: Bearer` do client chủ động gắn thường có CSRF threat model khác cookie-based authentication. Có thể cấu hình:

~~~java
.csrf(AbstractHttpConfigurer::disable)
~~~

Nhưng không tắt CSRF chỉ vì API dùng JWT hoặc `SessionCreationPolicy.STATELESS`. Nếu access token được gửi tự động qua cookie hoặc ứng dụng có session cookie, CSRF vẫn cần được xem xét.

Test phải phản ánh chính sách thật của application, không thêm `.with(csrf())` một cách máy móc để mọi POST đều qua.

## 11. Kiểm thử nhiều SecurityFilterChain

Ứng dụng có thể có nhiều chain với matcher và thứ tự khác nhau:

~~~java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasAuthority("SCOPE_admin"))
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasAuthority("SCOPE_api"))
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(3)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
        .build();
}
~~~

Đây là sơ đồ cấu hình; trong ứng dụng thật cần chú ý các shared beans, decoder và các chain configurer.

### 11.1. Test route chọn đúng chain

~~~java
@Test
void adminRouteRequiresAdminScope() throws Exception {
    mvc.perform(get("/api/admin/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_api")
            )))
        .andExpect(status().isForbidden());
}

@Test
void regularApiRouteAcceptsApiScope() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_api")
            )))
        .andExpect(status().isOk());
}
~~~

Hai test này cho thấy policy khác nhau theo path. Tuy nhiên, vì dùng `.with(jwt())`, chúng test **authorization sau khi chain được chọn**, không xác minh decoder hay bearer filter.

### 11.2. Kiểm tra `@Order` và matcher overlap

Một số lỗi thường gặp:

- Chain `/api/**` đứng trước `/api/admin/**`, làm admin request chọn chain chung.
- Chain đầu tiên match mọi request, khiến các chain sau không bao giờ được dùng.
- Fallback chain thiếu, khiến một số request không đi qua chain nào.
- `securityMatcher` và controller path không đồng bộ.
- Context path hoặc servlet path làm matcher khác dự kiến.
- Test chỉ gọi một URL happy path nên không phát hiện chain bị che.

Nên có ít nhất một test cho mỗi chain và một test cho URL không match chain đặc hiệu.

### 11.3. Test resolver theo request

Nếu dùng `AuthenticationManagerResolver<HttpServletRequest>` cho JWT/opaque hoặc nhiều issuers, test cả:

- Request path/host được chọn đúng manager.
- Unknown route trả reject manager hoặc bị chain deny.
- JWT invalid không fallback sang manager khác ngoài policy.
- Resolver không fetch issuer/JWKS URL do request tùy ý cung cấp.
- Resolver không giữ request object trong singleton/shared state.
- Per-issuer decoder/introspector áp đúng validators.

## 12. Test Authentication và Authorization riêng biệt

Một filter chain thật có nhiều tầng. Nên phân loại test để lỗi chỉ rõ đang ở đâu.

| Tầng | Câu hỏi | Cách test |
|---|---|---|
| Bearer extraction | Header token được đọc đúng? | Gửi `Authorization: Bearer ...` |
| Authentication manager | Provider phù hợp được chọn? | Bearer integration test + verify interactions |
| JWT decoder | Signature/issuer/audience đúng? | Signed token test + real decoder |
| JWKS retrieval | Key source đúng? | Mock JWKS HTTP server |
| Opaque introspection | `active` và client auth đúng? | Introspection HTTP stub |
| SecurityContext | Principal/authorities được thiết lập? | Controller test đọc Authentication |
| HTTP authorization | Scope/role đúng? | `jwt()`/`opaqueToken()` |
| Method security | `@PreAuthorize` đúng? | MockMvc + method security enabled |
| Business authorization | Tenant/owner/ACL đúng? | Service integration test |
| Error translation | 401/403 response đúng? | MockMvc + assertions |

Không nên gộp tất cả vào một test khổng lồ. Một bộ test tốt có unit test converter/validator, authorization test nhanh và một số integration tests đi qua bearer filter thật.

## 13. Kiểm thử `@PreAuthorize` và method security

Nếu ứng dụng dùng:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto findOrder(String id) {
    ...
}
~~~

phải bật method security trong application/test context:

~~~java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfiguration {
}
~~~

Một MockMvc test với JWT mock:

~~~java
mvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

có thể đi qua HTTP filters và method security interceptor. Nếu HTTP layer đã permit route, method security vẫn có thể từ chối ở service method.

Cần test cả:

- Có authority đúng.
- Thiếu authority.
- Principal loại user gọi method dành cho service.
- Tenant/object ownership không đúng.
- Method invocation không xảy ra khi bị từ chối.

`@WithMockUser` hoặc `jwt()` có thể giúp kiểm tra policy method security; để kiểm tra authority mapping từ JWT claims, cần token thật qua decoder.

## 14. Kiểm thử custom JwtAuthenticationConverter

Nếu application ánh xạ:

~~~text
scope=orders.read
caller_kind=user
~~~

thành:

~~~text
SCOPE_orders.read
CALLER_USER
~~~

có hai cấp test.

### 14.1. Unit test converter

Tạo `Jwt` test object và gọi converter trực tiếp:

~~~java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "RS256")
    .issuer("https://idp.test.example")
    .subject("user-42")
    .claim("scope", "orders.read")
    .claim("caller_kind", "user")
    .build();

Collection<GrantedAuthority> authorities =
    converter.convert(jwt);
~~~

Assert rằng `SCOPE_orders.read` và `CALLER_USER` xuất hiện. Đây chỉ là unit test mapping; `Jwt` object được dựng trực tiếp không có chữ ký đã verify.

### 14.2. Integration test converter qua bearer flow

Tạo JWT ký thật với claims trên và gửi trong header Bearer. Sau khi decoder xác minh, `JwtAuthenticationConverter` production được gọi.

Test này xác nhận:

- Decoder chấp nhận token.
- Converter được gọi trong pipeline.
- Scope được map đúng.
- Custom caller marker được map đúng.
- Endpoint yêu cầu cả caller kind và scope hoạt động như contract.

Không thêm `.with(jwt())` vào request integration này vì nó sẽ bypass converter được gắn trong `JwtAuthenticationProvider` theo đường bearer thông thường.

## 15. Kiểm thử authentication entry point và access denied handler

Ứng dụng có thể chuẩn hóa JSON error response:

~~~java
.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(customAuthenticationEntryPoint)
    .accessDeniedHandler(customAccessDeniedHandler)
)
~~~

Test nên phân biệt:

**Unauthenticated:**

~~~java
mvc.perform(get("/api/orders"))
    .andExpect(status().isUnauthorized())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ));
~~~

**Authenticated but forbidden:**

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities()))
    .andExpect(status().isForbidden())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ));
~~~

Kiểm tra response body theo contract công khai của API, không gắn test với stack trace, class name hoặc thông điệp exception nội bộ.

Nếu bearer token invalid, authentication entry point xử lý lỗi xác thực. Nếu token hợp lệ nhưng thiếu quyền, access denied handler xử lý. Nếu service ném lỗi nghiệp vụ, `@ControllerAdvice`/exception handling MVC có thể xử lý theo contract khác.

## 16. Kiểm thử CORS và preflight

CORS preflight thường là request `OPTIONS` không có bearer token:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

MockMvc có thể kiểm tra response headers từ CORS configuration:

~~~java
mvc.perform(options("/api/orders")
        .header(HttpHeaders.ORIGIN, "https://app.example.com")
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
            "GET"
        )
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
            "authorization"
        ))
    .andExpect(status().isOk())
    .andExpect(header().string(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://app.example.com"
    ));
~~~

Status và header cụ thể phụ thuộc CORS config. Preflight thường được xử lý trước authentication; không yêu cầu token nếu policy cho phép.

MockMvc kiểm tra CORS filter/configuration ở server side, nhưng không mô phỏng browser enforcement. Một browser thật còn áp dụng CORS protocol và có thể chặn JavaScript đọc response dù server đã trả dữ liệu.

## 17. Kiểm thử Session và SecurityContext persistence

Resource Server bearer-only thường stateless:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

Test có thể xác nhận mỗi request phải mang bearer token và không tái sử dụng authentication từ session ngoài ý muốn.

Nếu ứng dụng vừa có browser session vừa có API bearer chain, hãy test hai chains riêng:

- UI route dùng session/cookie theo policy.
- API route yêu cầu bearer token.
- `JSESSIONID` không tự trở thành Bearer authentication nếu API contract không cho phép.
- Session không làm lộ principal từ request trước sang tenant/user khác.
- SecurityContext được clear/persist theo đúng repository và policy.

MockMvc có `MockHttpSession`; có thể gửi cùng session qua nhiều requests để kiểm tra session-based flow. Nhưng với API stateless, không nên dùng session trong test bearer để che việc request thiếu token.

## 18. Kiểm thử CSRF và security context với annotation

`@WithMockUser` thiết lập context trước test method. Spring Security Test tích hợp `TestSecurityContextHolderPostProcessor` khi MockMvc được cấu hình qua `springSecurity()`.

Ví dụ:

~~~java
@Test
@WithMockUser(username = "mai", authorities = "SCOPE_orders.read")
void readRouteWorksForMockUser() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isOk());
}
~~~

Annotation hữu ích cho tests cần một principal có sẵn. Tuy nhiên, nếu test method cần bearer filter, hãy bỏ annotation và gửi bearer header.

Không trộn `@WithMockUser` và một token Bearer khác trong cùng test trừ khi mục tiêu là kiểm tra precedence/interaction rất cụ thể. Nếu cả hai cùng cung cấp authentication, test có thể không kiểm tra principal mà bạn nghĩ nó đang kiểm tra.

## 19. Test thực tế cho `BearerTokenAuthenticationFilter`

Một cách xác nhận bearer filter được gọi là gửi token header và quan sát decoder/introspector test dependency.

Ví dụ dùng Mockito:

~~~java
verify(jwtDecoder).decode(anyString());
~~~

Nếu decoder là mock, test chứng minh filter/provider gọi decoder với token. Nó **không** chứng minh chữ ký được verify.

Đối với introspection:

~~~java
verify(opaqueTokenIntrospector).introspect("opaque-test-token");
~~~

Một introspector mock có thể trả principal active để test pipeline, nhưng không kiểm tra HTTP client, credentials hoặc response parsing.

Để kiểm tra provider thật và network client thật, thay mock bằng decoder/introspector trỏ tới test key hoặc HTTP stub.

## 20. Những anti-pattern phổ biến

### 20.1. Tắt tất cả filters rồi test security status

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

Khi filters bị tắt, request không chạy Spring Security filter chain. Test 200 không chứng minh API production permit request.

### 20.2. Dùng `jwt()` rồi tuyên bố chữ ký đã được kiểm tra

`jwt()` tạo mock authentication. Nó không gọi `JwtDecoder` để verify chữ ký.

### 20.3. Dùng `opaqueToken()` rồi tuyên bố introspection endpoint hoạt động

`opaqueToken()` tạo `BearerTokenAuthentication` giả lập. Nó không gửi request tới AS.

### 20.4. Dùng `@WithMockUser` để test JWT claims

`@WithMockUser` không tạo JWT. Nó không kiểm tra `iss`, `aud`, `exp`, `kid`, `scope` hoặc custom claim converter.

### 20.5. Mock toàn bộ `SecurityFilterChain`

Nếu thay `SecurityFilterChain` production bằng chain test permitAll, test không còn kiểm tra policy thật. Chỉ mock những dependency bên ngoài như service, repository hoặc decoder/introspector khi mục tiêu test cho phép.

### 20.6. Dùng standaloneSetup mà không gắn security filter

Controller test có thể qua mà không hề chạy security. Dùng `webAppContextSetup` hoặc cung cấp `FilterChainProxy` thật.

### 20.7. Assert status duy nhất cho mọi lỗi

Một 403 có thể đến từ CSRF, authority thiếu hoặc custom access denied. Một 401 có thể do token malformed, issuer sai hoặc decoder exception. Hãy thêm assertions/verification cần thiết để biết nguyên nhân.

### 20.8. Không kiểm tra chain fallback

Request ngoài matcher có thể không đi qua chain nào nếu thiếu fallback. Test các route lạ và route admin đặc biệt.

### 20.9. Dùng token production trong test

Không lấy bearer token thật từ log, browser hoặc môi trường production để làm fixture. Sinh test key/token hoặc dùng test Authorization Server.

### 20.10. Test phụ thuộc thời gian thực không ổn định

JWT `exp`/`nbf` có thể khiến test chạy hôm nay pass nhưng ngày mai fail. Tạo claims dựa trên `Instant.now()` hoặc clock test được kiểm soát.

### 20.11. Dùng `@SpringBootTest` cho mọi test

Full context chậm hơn slice test. Dùng `@WebMvcTest` cho MVC/security slice, unit tests cho converter/validator, và một số integration tests cho full bearer pipeline.

### 20.12. Không kiểm tra side effects khi bị từ chối

Ngoài assert 401/403, có thể verify service không được gọi:

~~~java
verifyNoInteractions(ordersService);
~~~

Điều này giúp phát hiện lỗi controller/service vẫn chạy dù security response cuối cùng bị từ chối ở một tầng khác.

## 21. Ma trận test nên có cho Resource Server

| Nhóm | Request | Kỳ vọng | Mức test |
|---|---|---|---|
| Public route | Không token | 200 | MockMvc + real chain |
| Private route | Không token | 401 | Real bearer filter chain |
| Malformed token | Bearer chuỗi sai | 401 | Real bearer filter chain |
| JWT signature invalid | Token ký bằng key khác | 401 | Real decoder |
| Wrong issuer | JWT có `iss` khác | 401 | Real decoder/validator |
| Wrong audience | `aud` khác API | 401 | Real decoder/validator |
| Expired JWT | `exp` quá khứ | 401 | Real decoder/validator |
| Valid JWT | Signed test token | 200 nếu đủ scope | Real decoder |
| Missing scope | JWT hợp lệ nhưng thiếu scope | 403 | Real decoder hoặc mock JWT cho authorization |
| Opaque active | Introspection active=true | 200 nếu đủ scope | Real introspector + stub |
| Opaque inactive | Introspection active=false | 401 | Real introspector + stub |
| Introspection timeout | AS test timeout | Không authenticated | Real introspector + stub |
| CSRF missing | POST khi CSRF bật | 403 | Real chain |
| CSRF valid | POST + csrf token | Đi tiếp nếu quyền đủ | Real chain |
| Admin chain | Scope API thường | 403 | Chain selection + authorization |
| Unknown route | Không match route | Deny | Fallback chain |
| Method security | Thiếu authority | Access denied | MVC + method security |
| Tenant mismatch | Token hợp lệ, tenant sai | 403/404 theo policy | Service integration |
| CORS preflight | OPTIONS đúng Origin | CORS response | MockMvc CORS |
| Converter mapping | Claims user/service | Authority đúng | Unit + signed JWT integration |

Không phải mọi case cần một full Spring context riêng. Có thể nhóm test theo fixture và dùng unit/slice/integration layers phù hợp.

## 22. Tổ chức test classes theo mục đích

Một cấu trúc dễ duy trì:

~~~text
src/test/java
  security/
    CallerAuthoritiesConverterTests.java
    AudienceValidatorTests.java
    ApiAuthorizationMockMvcTests.java
    JwtBearerFilterChainTests.java
    OpaqueIntrospectionFilterChainTests.java
    MultiSecurityFilterChainRoutingTests.java
    CsrfAndCorsMockMvcTests.java
    MethodSecurityTests.java
  support/
    TestJwtFactory.java
    TestJwksServer.java
    TestIntrospectionServer.java
    SecurityTestConfiguration.java
~~~

Gợi ý:

- `*Tests` unit: converter, validator, mapping.
- `*MockMvcTests` authorization: dùng `jwt()`, `opaqueToken()`, `user()`.
- `*FilterChainTests` integration: gửi header Bearer thật qua `MockMvc`.
- `*Server` fixtures: test JWKS/introspection endpoint.
- `TestJwtFactory`: ký token với test private key và claims có thể tùy chỉnh.
- `SecurityTestConfiguration`: chỉ chứa test keys/decoder/endpoint, không thay policy production.

Tên thư mục/class chỉ là ví dụ; điều quan trọng là phân biệt rõ mock-authentication test với bearer-pipeline test.

## 23. Debug khi MockMvc không chạy filter chain như mong đợi

Nếu endpoint trả 200 khi không token:

1. Kiểm tra `@AutoConfigureMockMvc(addFilters = false)` có đang được dùng không.
2. Nếu tự build MockMvc, có `.apply(springSecurity())` không?
3. `FilterChainProxy` bean `springSecurityFilterChain` có trong application context không?
4. Có `SecurityFilterChain` nào match request không?
5. Chain có `permitAll()` hoặc matcher quá rộng không?
6. Test có dùng `.with(jwt())`, `.with(user())`, `@WithMockUser` hoặc `.with(authentication())` không?
7. Có test config nào thay security config production không?
8. `@WebMvcTest` đã import đúng security configuration chưa?
9. Có filter custom nào tự bỏ qua route?
10. Request path có context path/servlet path làm matcher khác dự kiến không?

Nếu request trả 403 thay vì 401:

- Kiểm tra CSRF có chặn POST/PUT/PATCH/DELETE không.
- Kiểm tra principal đã authenticated nhưng thiếu authority không.
- Kiểm tra `AccessDeniedHandler`.
- Kiểm tra `@PreAuthorize`.
- Kiểm tra chain nào được chọn.

Nếu request Bearer token không gọi decoder:

- Xác nhận header đúng `Authorization: Bearer ...`.
- Bỏ `jwt()`/`authentication()` request post processor.
- Xác nhận `oauth2ResourceServer().jwt(...)` hoặc resolver đúng được cấu hình.
- Xác nhận request đi vào đúng `SecurityFilterChain`.
- Kiểm tra route có permitAll không; token invalid vẫn thường được xử lý nếu header bearer được gửi, nhưng behavior cụ thể tùy token resolver/filter config.

## 24. Những giới hạn cần test ngoài MockMvc

Một bộ test security tốt không dừng ở MockMvc.

| Vấn đề | MockMvc | Test server/staging |
|---|---|---|
| Request matcher và filter ordering | Có | Có |
| Bearer extraction/provider | Có | Có |
| JWT signature với test key | Có | Có |
| JWKS HTTP fetch qua mock server | Có | Có |
| Introspection HTTP call qua stub | Có | Có |
| CSRF/CORS server config | Có | Có |
| TLS handshake | Không mô phỏng đầy đủ | Có |
| mTLS client certificate | Không mô phỏng đầy đủ | Có |
| Reverse proxy forwarded headers | Chỉ mô phỏng request attributes | Có |
| DNS/firewall/egress | Không | Có |
| Browser CORS enforcement | Không | Browser E2E |
| Cookie SameSite behavior | Không mô phỏng browser | Browser E2E |
| Connection timeout/load balancer | Không mô phỏng hạ tầng thật | Có |
| Multiple replicas/shared cache | Không | Distributed integration test |

Nếu Resource Server dùng mTLS-bound access token, DPoP, proxy headers hoặc network trust, hãy bổ sung test chuyên biệt. MockMvc có thể test request-aware verifier bằng request attribute giả, nhưng điều đó không chứng minh TLS certificate thực được container xác minh.

## 25. Câu hỏi tự kiểm tra

**1.** Cần làm gì để MockMvc dùng Spring Security filter chain thật?

> Dùng `webAppContextSetup(context).apply(springSecurity()).build()` hoặc Spring Boot `@AutoConfigureMockMvc` với filters được bật.

**2.** `springSecurity()` thêm thành phần nào vào MockMvc?

> Nó đăng ký bean `springSecurityFilterChain` (thường là `FilterChainProxy`) làm filter và tích hợp TestSecurityContextHolder.

**3.** `@AutoConfigureMockMvc(addFilters=false)` có kiểm tra Spring Security không?

> Không. Nó tắt đăng ký servlet filters cho MockMvc.

**4.** `.with(jwt())` có xác minh chữ ký JWT không?

> Không. Nó tạo mock `Jwt`/authentication để test authorization.

**5.** `.with(opaqueToken())` có gọi introspection endpoint không?

> Không. Nó tạo `BearerTokenAuthentication` giả lập.

**6.** `@WithMockUser` có đi qua `BearerTokenAuthenticationFilter` không?

> Không. Nó thiết lập SecurityContext với user mock.

**7.** Muốn kiểm tra JWT signature thật phải làm gì?

> Tạo JWT ký bằng private test key, gửi qua `Authorization: Bearer`, dùng decoder verify bằng public key/JWKS test.

**8.** Muốn test introspection thật qua MockMvc cần gì?

> Introspector thật trỏ tới HTTP stub/test AS và request Bearer không dùng `opaqueToken()` mock post processor.

**9.** Vì sao cần `@Order` test khi có nhiều `SecurityFilterChain`?

> Vì `FilterChainProxy` chọn chain match đầu tiên; chain tổng quát có thể che chain đặc hiệu.

**10.** POST trả 403 có nhất thiết thiếu scope không?

> Không. Có thể thiếu CSRF token hoặc bị method security/access denied policy từ chối.

**11.** MockMvc có kiểm tra TLS/mTLS handshake không?

> Không đầy đủ. Cần test server/container và TLS client thật.

**12.** Vì sao `jwt()` hữu ích dù không verify signature?

> Nó cho phép test nhanh HTTP authorization rules với claims/authorities tùy chỉnh, không cần dựng token crypto trong mọi test.

**13.** Test signed JWT bằng public key trực tiếp có kiểm tra JWKS fetch không?

> Không. Nó kiểm tra chữ ký; muốn test HTTP JWKS retrieval cần mock JWKS server.

**14.** Có nên mock toàn bộ `SecurityFilterChain` trong integration test?

> Không nếu mục tiêu là xác nhận production filter chain; chỉ mock dependency ngoài security khi cần.

**15.** Vì sao cần verify service không được gọi khi token bị từ chối?

> Để chắc chắn không có business side effect trước khi security decision hoàn tất.

## 26. Tài liệu tham khảo

- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): `FilterChainProxy`, `springSecurity()` và TestSecurityContextHolder.
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, `opaqueToken()`, `authentication()` và giới hạn mock authentication.
- [Spring Security — MockMvc Request Post Processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html): `user`, `csrf`, `httpBasic`, form login và request processors.
- [Spring Security 6.5 — Setting Up MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): đối chiếu API và setup ở dòng 6.5.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): test `@PreAuthorize` và method security.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): Spring MVC Test, `webAppContextSetup` và `standaloneSetup`.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices và context.
- [Spring Boot — Auto-configured MockMvc](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@AutoConfigureMockMvc` và servlet filters.
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoder, validators, bearer authentication.
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và opaque authentication.
- [Spring Security — Authorization HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matcher, authority và deny rules.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF filter và token behavior.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS filter và preflight.

**Kết luận:** MockMvc có thể kiểm thử **Spring Security filter chain thực tế** khi request được đưa qua `FilterChainProxy` bằng `springSecurity()` hoặc Boot MockMvc auto-configuration với filters bật. Nhưng `.with(jwt())`, `.with(opaqueToken())` và `@WithMockUser` chỉ tạo authentication giả lập để kiểm tra authorization. Muốn xác nhận Resource Server xử lý bearer token đúng, hãy gửi `Authorization: Bearer ...` qua MockMvc; dùng JWT ký bằng test key và decoder thật, hoặc introspection server stub để kiểm tra từng provider. Kết hợp unit tests, authorization tests, bearer-pipeline integration tests và test hạ tầng khi cần TLS/proxy/network để có bằng chứng phù hợp cho từng lớp bảo mật.
