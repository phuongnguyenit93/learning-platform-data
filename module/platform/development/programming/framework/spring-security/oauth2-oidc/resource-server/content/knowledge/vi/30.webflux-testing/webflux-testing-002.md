# mockJwt() và tùy chỉnh claims, authorities

Khi kiểm thử một ứng dụng **Spring Security WebFlux Resource Server dùng JWT access token**, ta thường cần xác minh các route có yêu cầu đúng scope hay không, controller đọc được principal/claims nào, và method security có chặn đúng người dùng hay không. Những test này không nhất thiết phải tạo JWT đã ký hoặc gọi Authorization Server. Spring Security Test cung cấp **§mockJwt()§** để dựng một JWT authentication giả lập trong request của **WebTestClient**.

§mockJwt()§ đặc biệt hữu ích khi muốn tập trung vào phần xử lý sau authentication:

- Tùy chỉnh claims như §sub§, §iss§, §aud§, §tenant_id§ hoặc §client_id§.
- Gán authorities như §SCOPE_orders.read§ và §ROLE_ADMIN§.
- Kiểm tra §JwtAuthenticationToken§, §@AuthenticationPrincipal Jwt§ và reactive controller.
- Kiểm tra HTTP authorization, §@PreAuthorize§ và trường hợp 401/403.

Tuy nhiên, §mockJwt()§ **đặt sẵn một Authentication đã được xác thực cho test**. Nó không chạy §ReactiveJwtDecoder§, không xác minh chữ ký JWT, không tải JWKS, không kiểm issuer/audience/expiry bằng validator production và không gọi Authorization Server. Muốn kiểm tra các bước đó, cần gửi một Bearer JWT qua filter chain với decoder test hoặc test issuer/JWKS.

> **Cách nhớ:** §mockJwt()§ kiểm tra ứng dụng xử lý một JWT principal như thế nào sau authentication; Bearer-header integration test kiểm tra ứng dụng xác thực JWT ra sao.

Bài học thuộc chương **Kiểm thử WebFlux** trong module Spring Security OAuth 2.0 OIDC Resource Server. Nội dung trình bày API test, cách tùy chỉnh claims và authorities, controller binding, HTTP/method authorization, cấu hình WebFlux test context và cách phân biệt mock authentication với JWT decoder integration.

## 1. JWT Resource Server trong WebFlux

Khi client gửi JWT access token tới một API WebFlux, Spring Security thường thực hiện:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant API as WebFlux Resource Server
    participant AS as Authorization Server / JWKS
    C->>API: Authorization: Bearer JWT
    API->>API: AuthenticationWebFilter
    API->>API: BearerTokenAuthenticationConverter
    API->>API: ReactiveAuthenticationManager
    API->>AS: Fetch/refresh JWKS when needed
    API->>API: ReactiveJwtDecoder verifies token
    API->>API: Build JwtAuthenticationToken
    API->>API: Authorization + controller
    API-->>C: Response
~~~

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| §AuthenticationWebFilter§ | Reactive security filter xử lý authentication |
| §ServerBearerTokenAuthenticationConverter§ | Đọc Bearer token từ request |
| §ReactiveAuthenticationManager§ | Điều phối xác thực bất đồng bộ |
| §JwtReactiveAuthenticationManager§ | Dùng decoder để xác minh JWT và tạo authentication |
| §ReactiveJwtDecoder§ | Decode/verify JWT, kiểm chữ ký và các validators đã cấu hình |
| §JwtAuthenticationToken§ | Authentication chứa JWT principal và authorities |
| §ReactiveAuthorizationManager§ | Quyết định quyền truy cập cho exchange/method |
| §ReactiveSecurityContextHolder§ | Truy cập SecurityContext trong reactive execution context |

Một request test dùng §mockJwt()§ bỏ qua bước parse Bearer token, decoder và JWKS. Helper đặt §JwtAuthenticationToken§ vào security context để phần authorization/controller có thể được kiểm thử.

## 2. §mockJwt()§ là gì và import ở đâu?

§mockJwt()§ là một **WebTestClient configurer** trong §spring-security-test§. API nằm trong §SecurityMockServerConfigurers§ của reactive test support.

Static import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
~~~

Dependency Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án dùng Spring Boot BOM, hãy để dependency management chọn version tương ứng với Spring Security runtime. Không ghim riêng một phiên bản test module khác dòng runtime.

### 2.1. Cách dùng cơ bản

Với một §WebTestClient§ được Spring Boot cấu hình:

~~~java
@Test
void requestWithMockJwtIsAuthenticated() {
    webTestClient
        .mutateWith(mockJwt())
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

§mutateWith(mockJwt())§ áp dụng mock JWT authentication cho request được gửi bởi client đã mutate. Đây là cách dùng phổ biến trong reactive integration tests.

### 2.2. Test helper không cần compact JWT

Test không cần tự tạo chuỗi JWT dạng ba phần:

~~~text
base64url(header).base64url(payload).signature
~~~

§mockJwt()§ dựng một đối tượng §Jwt§ cùng §JwtAuthenticationToken§ trong test context. Giá trị token/header/claims mặc định là fixture do helper cung cấp; nó không đại diện cho token được ký bởi issuer thật.

### 2.3. Đừng nhầm với Servlet MockMvc

WebFlux dùng:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
~~~

Servlet MVC dùng một request post-processor khác trong §SecurityMockMvcRequestPostProcessors§. Không import nhầm helper MockMvc khi test §WebTestClient§. Hai stack có cách cấu hình request test khác nhau dù cùng tên §mockJwt()§.

## 3. Tùy chỉnh JWT claims

§mockJwt()§ cho phép tùy chỉnh §Jwt.Builder§ qua hàm nhận builder. Có thể đặt claims phản ánh principal và metadata mà API sử dụng.

### 3.1. Đặt subject và custom claims

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("sub", "alice")
        .claim("tenant_id", "tenant-a")
        .claim("client_id", "orders-web")
        .claim("email", "alice@example.test")))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

Các claim trên là dữ liệu giả lập cho test. Ví dụ:

| Claim | Ý nghĩa thường gặp |
|---|---|
| §sub§ | Subject định danh người dùng/service trong phạm vi issuer |
| §tenant_id§ | Tenant theo contract của Authorization Server |
| §client_id§ | OAuth client liên quan tới access token |
| §email§ | Claim hồ sơ nếu issuer phát hành và API có lý do sử dụng |

Không coi việc test tự thêm §tenant_id§ hoặc §email§ là bằng chứng issuer thật phát hành claim đó. Test fixture phải phản ánh schema đã được thống nhất với nhà phát hành.

### 3.2. Đặt issuer và audience trong fixture

Nếu controller hoặc service đọc issuer/audience:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("iss", "https://identity.example.test")
        .claim("sub", "alice")
        .claim("aud", List.of("orders-api"))
        .claim("tenant_id", "tenant-a")))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

Việc đặt §iss§ và §aud§ giúp kiểm tra code sử dụng claims đó. Nó **không chạy issuer validator hoặc audience validator**. Một test có §aud=orders-api§ vẫn có thể pass dù production decoder đang cấu hình sai audience, bởi §mockJwt()§ đã bỏ qua decoder. Hãy viết test decoder riêng cho validation.

### 3.3. Thời gian và token ID

Nếu code nghiệp vụ đọc các claim thời gian hoặc token ID, có thể đưa chúng vào fixture:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("sub", "alice")
        .claim("jti", "test-token-001")
        .claim("iat", Instant.parse("2026-01-01T10:00:00Z"))
        .claim("exp", Instant.parse("2026-01-01T10:10:00Z"))))
    .get()
    .uri("/api/token-info")
    .exchange()
    .expectStatus().isOk();
~~~

Tùy phiên bản Spring Security, builder có thể cung cấp các method tiện ích cho thời gian/subject; dùng API builder đúng version của dự án. Với claims tùy chỉnh, đảm bảo kiểu dữ liệu tương thích NumericDate và mapper của ứng dụng.

Đừng dùng fixture trên để chứng minh expiry validator chạy. Test đó cần Bearer token đi qua §ReactiveJwtDecoder§ hoặc kiểm validator trực tiếp.

### 3.4. Claims mặc định

§mockJwt()§ cung cấp một JWT fixture mặc định để test có thể chạy mà không cần khai báo mọi trường. Default claims/authorities là chi tiết của Spring Security Test và có thể thay đổi giữa các phiên bản. Test nghiệp vụ nên đặt rõ §sub§, §aud§, tenant và các authorities mà nó cần thay vì phụ thuộc ngầm vào defaults.

## 4. Tùy chỉnh authorities

Claims mô tả dữ liệu token; **authorities** là quyền mà Spring Security authorization engine kiểm tra. Hai phần có liên quan nhưng không nên coi là một.

### 4.1. Đặt scope authority trực tiếp

Nếu endpoint yêu cầu §SCOPE_orders.read§:

~~~java
webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Import:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
~~~

Khi gọi §authorities(...)§, test chủ động xác định các quyền của mock authentication. Đây là cách rõ ràng để kiểm tra một nhánh authorization mà không phụ thuộc vào claim converter.

### 4.2. Gán nhiều authorities

~~~java
webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read"),
        new SimpleGrantedAuthority("SCOPE_orders.write"),
        new SimpleGrantedAuthority("ROLE_SUPPORT")))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Ví dụ có hai scope và một role. Chỉ gán quyền cần thiết cho test; không cấp §ROLE_ADMIN§ mặc định cho mọi mock principal vì như vậy các test có thể bỏ sót lỗi least privilege.

### 4.3. Scope claim và scope authority

JWT access token có thể mang:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Spring Security thường dùng §JwtGrantedAuthoritiesConverter§ để ánh xạ scope thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Một số issuer dùng claim §scp§ hoặc định dạng mảng; khi đó ứng dụng có thể cấu hình converter riêng. Trong test:

- Nếu muốn kiểm tra controller/authorization với một tập quyền đã xác định, đặt §.authorities(...)§.
- Nếu muốn kiểm tra converter production đọc claim §scope§/§scp§ ra sao, test converter riêng hoặc gửi Bearer JWT qua authentication pipeline với decoder test.

Đừng cho rằng việc thêm §scope§ vào claims bằng §.jwt(...)§ luôn kiểm tra được custom converter của ứng dụng. §mockJwt()§ đã dựng authentication và có thể dùng converter mặc định của test helper; custom production converter không nhất thiết được gọi.

### 4.4. Quyền và claims là hai input riêng

Ví dụ:

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .claim("sub", "alice")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read"))
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Test này dựng cả metadata và authority. Nếu production converter bị lỗi và không ánh xạ scope, test vẫn có thể pass vì authority đã được gán trực tiếp. Vì vậy, đây là **authorization test**, không phải converter test.

## 5. Controller nhận JWT principal trong WebFlux

Sau khi JWT authentication thành công, controller có thể nhận principal dưới dạng §Jwt§ hoặc §JwtAuthenticationToken§.

### 5.1. Dùng §@AuthenticationPrincipal Jwt§

~~~java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class CurrentUserController {

    @GetMapping("/api/me")
    Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "tenant", jwt.getClaimAsString("tenant_id")
        ));
    }
}
~~~

Test:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("sub", "alice")
        .claim("tenant_id", "tenant-a")))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.subject").isEqualTo("alice")
    .jsonPath("$.tenant").isEqualTo("tenant-a");
~~~

§@AuthenticationPrincipal§ lấy principal từ SecurityContext hiện tại. Với JWT Resource Server, principal là đối tượng §Jwt§; không phải §OAuth2AuthenticatedPrincipal§ tổng quát như opaque-token authentication.

### 5.2. Dùng §JwtAuthenticationToken§

Nếu cần cả authorities và JWT:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class TokenDetailsController {

    @GetMapping("/api/token-details")
    Mono<Map<String, Object>> details(
            @AuthenticationPrincipal JwtAuthenticationToken authentication) {
        return Mono.just(Map.of(
            "subject", authentication.getName(),
            "authorities", authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList(),
            "claims", authentication.getToken().getClaims()
        ));
    }
}
~~~

Trong nhiều trường hợp, inject §Jwt§ là đủ. Nếu controller cần authentication metadata, có thể dùng §Authentication§ hoặc §JwtAuthenticationToken§ qua method argument được resolver hỗ trợ. Tránh trả toàn bộ claims cho client trong production vì chúng có thể chứa thông tin nội bộ hoặc PII; ví dụ chỉ nhằm minh họa cách truy cập.

### 5.3. Dùng §ReactiveSecurityContextHolder§ trong service

Trong reactive service không nhận trực tiếp principal qua method argument, có thể đọc SecurityContext từ Reactor context:

~~~java
Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .cast(JwtAuthenticationToken.class)
        .map(JwtAuthenticationToken::getToken)
        .map(Jwt::getSubject);
}
~~~

Import:

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
~~~

Test với §mockJwt()§ có thể xác minh service đọc được subject qua reactive context. Tránh gọi §subscribe()§ bên trong service; trả §Mono§ để Spring WebFlux duy trì context qua pipeline.

## 6. Cấu hình WebFlux Security để kiểm thử

Một API JWT Resource Server có thể cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Trong production, §ReactiveJwtDecoder§ phải được cung cấp qua issuer/JWK configuration hoặc bean tường minh. Ví dụ này chỉ minh họa security chain. Nếu test context cần decoder bean để khởi tạo filter chain, cung cấp test bean dù các test §mockJwt()§ không gọi nó.

### 6.1. Không tắt CSRF một cách máy móc

API chỉ nhận Bearer token qua Authorization header thường không dùng cookie tự động gửi từ browser. Nhưng ứng dụng có thể có session/cookie endpoints trong cùng context. Chỉ tắt CSRF khi mô hình credential và chain matcher cho phép; không sao chép một cấu hình stateless vào toàn bộ ứng dụng chỉ để test POST dễ hơn.

### 6.2. Phân tách chain nếu ứng dụng vừa là client vừa là API

Một ứng dụng WebFlux có thể vừa dùng OAuth2 Login vừa làm Resource Server. Cần tách rule cho browser session và Bearer API, tránh việc test §mockJwt()§ vô tình kiểm một chain khác với chain bảo vệ endpoint. Với nhiều chain, xác nhận matcher/ordering và endpoint đang được test.

## 7. Test đầy đủ với §@WebFluxTest§

§@WebFluxTest§ phù hợp để test controller và WebFlux slice. §WebTestClient§ được inject để gửi request qua test server.

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(CurrentUserController.class)
@Import(ApiSecurityConfiguration.class)
class CurrentUserControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void returnsSubjectAndTenantFromJwt() {
        webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-a")))
            .get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice")
            .jsonPath("$.tenant").isEqualTo("tenant-a");
    }
}
~~~

Tùy phiên bản Spring Boot và cách cấu hình Resource Server, context có thể cần một §ReactiveJwtDecoder§ bean dù mock post-processor bỏ qua decoder ở runtime. Khi đó cung cấp test bean hoặc import test configuration. Không cấu hình test để vô tình discovery issuer thật khi test chỉ cần mock authentication.

### 7.1. Test configuration cung cấp decoder không dùng tới

Một decoder test có thể fail nếu có request vô tình đi vào đường Bearer authentication:

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.core.publisher.Mono;

@TestConfiguration
class MockJwtTestConfiguration {

    @Bean
    @Primary
    ReactiveJwtDecoder testReactiveJwtDecoder() {
        return token -> Mono.error(
            new BadJwtException("Unexpected decoder invocation in mockJwt test"));
    }
}
~~~

Import cấu hình này vào test slice khi cần:

~~~java
@Import({ApiSecurityConfiguration.class, MockJwtTestConfiguration.class})
~~~

Bean trên không xác minh token; nó làm rõ rằng test đang mong đợi §mockJwt()§ tạo authentication sẵn. Nếu test cần kiểm decoder, dùng một decoder test riêng có behavior tương ứng thay vì bean fail-fast này.

### 7.2. Nếu dùng §bindToApplicationContext§

Khi tự dựng §WebTestClient§ thay vì dùng Boot test auto-configuration, cần gắn Spring Security WebFlux filter chain:

~~~java
webTestClient = WebTestClient
    .bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Static import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
~~~

Nếu không tích hợp filter chain, test có thể chỉ gọi controller và không kiểm tra authorization thực. Hãy bảo đảm §mockJwt()§ và security filters cùng tham gia vào request pipeline.

## 8. Kiểm thử 401, 403 và 2xx

Giả sử endpoint GET yêu cầu §SCOPE_orders.read§ và mọi endpoint còn lại yêu cầu authentication.

### 8.1. Không có authentication: 401

~~~java
@Test
void requestWithoutJwtIsUnauthorized() {
    webTestClient
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

Request không dùng §mockJwt()§ vì mục tiêu là kiểm tra trường hợp không có Authentication. Nếu endpoint được §permitAll()§ hoặc matcher khác bảo vệ, status kỳ vọng sẽ khác.

### 8.2. Có JWT nhưng thiếu scope: 403

~~~java
@Test
void jwtWithoutReadScopeIsForbidden() {
    webTestClient
        .mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Mock JWT đã authenticated, nhưng authority không thỏa policy. Đây là test phù hợp để chứng minh endpoint không cho phép bất kỳ principal nào chỉ vì đã đăng nhập.

### 8.3. Có scope đúng: 200

~~~java
@Test
void jwtWithReadScopeCanReadOrders() {
    webTestClient
        .mutateWith(mockJwt()
            .jwt(jwt -> jwt.claim("sub", "alice"))
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

Test này xác minh authorization rule sau authentication. Nó không chứng minh một JWT có chữ ký thật sẽ được decoder chấp nhận.

### 8.4. POST yêu cầu scope write

~~~java
@Test
void readOnlyJwtCannotCreateOrder() {
    webTestClient
        .mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
        .post()
        .uri("/api/orders")
        .bodyValue(Map.of("sku", "SKU-100"))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Nếu endpoint POST dùng CSRF hoặc có custom filter, status có thể phản ánh lớp bảo vệ đó trước authorization. Trong API Bearer thuần, cấu hình CSRF phải phù hợp với threat model. Test cần biết nó đang kiểm CSRF hay scope.

## 9. Method security trong WebFlux

HTTP matcher không phải lớp authorization duy nhất. Một reactive service có thể dùng §@PreAuthorize§ để kiểm scope:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    Mono<String> listOrders() {
        return Mono.just("orders");
    }
}
~~~

Bật reactive method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

### 9.1. Test method security với mockJwt

Gọi endpoint đi qua controller/service proxy:

~~~java
@Test
void methodSecurityAllowsReadScope() {
    webTestClient
        .mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

Và trường hợp thiếu quyền:

~~~java
@Test
void methodSecurityRejectsMissingReadScope() {
    webTestClient
        .mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Test method security phải nạp cấu hình §@EnableReactiveMethodSecurity§ và gọi method qua Spring bean proxy. Nếu test gọi trực tiếp một object được tạo bằng §new§, annotation có thể không được áp dụng.

### 9.2. Reactive return type

Reactive method security hỗ trợ method trả về publisher theo cấu hình phù hợp. Đừng chuyển method sang blocking chỉ để test dễ hơn. Hãy kiểm tra subscription/error signal và HTTP mapping trong WebFlux pipeline.

## 10. Kiểm thử custom claims và domain authorization

Một access token có thể chứa §tenant_id§, §organization_id§ hoặc claim nghiệp vụ riêng. Controller/service phải dùng các claims này như dữ liệu từ principal đã xác thực.

### 10.1. Test tenant được phép

~~~java
@Test
void userCanReadOwnTenantOrders() {
    webTestClient
        .mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-a"))
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
        .get()
        .uri("/api/tenants/tenant-a/orders")
        .exchange()
        .expectStatus().isOk();
}
~~~

### 10.2. Test tenant khác

~~~java
@Test
void userCannotReadAnotherTenantOrders() {
    webTestClient
        .mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-a"))
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
        .get()
        .uri("/api/tenants/tenant-b/orders")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Kết quả 403 giả định ứng dụng thực sự so tenant trong principal với tenant được yêu cầu. §mockJwt()§ chỉ cung cấp claim fixture; nó không tự tạo tenant authorization. Nếu controller/service không có rule tenant, cả hai test có thể cùng trả 200.

### 10.3. Subject và issuer

Subject thường chỉ duy nhất trong phạm vi issuer. Nếu hệ thống multi-issuer, identity key cần kết hợp issuer đã xác minh và subject:

~~~text
principal identity = (verified iss, sub)
~~~

Có thể test trường hợp hai issuer cùng §sub§ nhưng là hai principal khác nhau. Lưu ý §mockJwt()§ đặt claims để test logic identity; test này không kiểm tra issuer validation của decoder.

## 11. So sánh §mockJwt()§ với §mockOpaqueToken()§

Spring Security Test có helper khác nhau cho JWT và opaque token:

| Khía cạnh | §mockJwt()§ | §mockOpaqueToken()§ |
|---|---|---|
| Dạng authentication | JWT Resource Server | Opaque bearer Resource Server |
| Principal | §Jwt§ | §OAuth2AuthenticatedPrincipal§ |
| Authentication | §JwtAuthenticationToken§ | §BearerTokenAuthentication§ |
| Claims/attributes | JWT claims | Opaque principal attributes |
| Authorities | Có thể tùy chỉnh | Có thể tùy chỉnh |
| Decoder/introspector thật | Không gọi decoder | Không gọi introspector |
| Dùng phổ biến | WebFlux JWT tests | WebFlux opaque-token tests |

Không dùng §mockJwt()§ để kiểm tra controller được thiết kế nhận opaque principal, hoặc §mockOpaqueToken()§ để chứng minh JWT signature validator hoạt động. Chọn helper phù hợp với loại Resource Server production.

## 12. Giới hạn của §mockJwt()§ và các test cần viết riêng

§mockJwt()§ không kiểm tra:

- Compact JWT parser có chấp nhận đúng token hay không.
- JWS signature có hợp lệ không.
- Key ID/JWKS rotation và algorithm allowlist.
- Issuer validator có từ chối issuer lạ không.
- Audience validator có yêu cầu đúng resource không.
- §exp§/§nbf§/§iat§ validators có chạy không.
- JWT access-token profile/§typ§ có đúng không.
- Custom §ReactiveJwtDecoder§ hoặc authentication manager được gọi không.
- DPoP proof, §cnf§ key binding hoặc token replay store.

Các nội dung này cần test decoder/validator, Bearer-header integration hoặc test DPoP riêng.

### 12.1. Test decoder validator trực tiếp

Nếu có custom §OAuth2TokenValidator<Jwt>§, có thể tạo §Jwt§ fixture và gọi validator trực tiếp để kiểm claims. Test này chứng minh policy logic, nhưng không chứng minh filter chain gọi validator. Cần thêm integration test qua decoder nếu muốn kiểm wiring.

### 12.2. Test Bearer header qua reactive filter chain

Gửi token trong header thay vì dùng mock post-processor:

~~~java
webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers -> headers.setBearerAuth("test-compact-jwt"))
    .exchange()
    .expectStatus().isOk();
~~~

Test context cần cung cấp §ReactiveJwtDecoder§ test có behavior xác định. Có thể dùng decoder stub:

~~~java
@Bean
ReactiveJwtDecoder testDecoder() {
    return token -> {
        if (!"test-compact-jwt".equals(token)) {
            return Mono.error(new BadJwtException("Unknown token"));
        }
        Jwt jwt = Jwt.withTokenValue(token)
            .header("alg", "test")
            .claim("iss", "https://issuer.test")
            .claim("sub", "alice")
            .claim("aud", List.of("orders-api"))
            .claim("scope", "orders.read")
            .issuedAt(Instant.now().minusSeconds(30))
            .expiresAt(Instant.now().plusSeconds(300))
            .build();
        return Mono.just(jwt);
    };
}
~~~

Đây là **stub decoder**, không kiểm chữ ký compact JWT. Nó kiểm tra Bearer filter → manager → decoder wiring và phần sau decoder. Để kiểm JWS signature, JWKS, key rotation và algorithm policy, dùng decoder/JWK test thật hoặc issuer test có private key/public JWKS.

### 12.3. Test inactive/error không thuộc mockJwt

JWT Resource Server không gọi introspection endpoint cho JWT thông thường. Các trường hợp invalid signature, issuer sai hoặc token hết hạn cần test decoder. Nếu muốn test opaque token §active=false§, dùng opaque introspector test; đừng áp semantics opaque vào §mockJwt()§.

## 13. §@WebFluxTest§, §@SpringBootTest§ và WebTestClient setup

### 13.1. §@WebFluxTest§

Dùng khi chỉ cần controller slice:

~~~java
@WebFluxTest(controllers = OrdersController.class)
@Import({ApiSecurityConfiguration.class,
         ReactiveMethodSecurityConfiguration.class})
class OrdersControllerTest {
    @Autowired
    WebTestClient webTestClient;
}
~~~

Import security configuration nếu slice không tự nạp cấu hình đó. Các service/repository phụ thuộc controller có thể cần mock bean theo cơ chế test của version Spring Boot.

### 13.2. §@SpringBootTest§

Dùng khi muốn kiểm tra application context, filter chains, service proxy và method security gần production:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class OrdersSecurityIntegrationTest {
    @Autowired
    WebTestClient webTestClient;
}
~~~

Test này khởi tạo nhiều thành phần hơn. Cấu hình test phải cô lập database, message broker và external identity provider; không để CI phụ thuộc issuer production.

### 13.3. §bindToApplicationContext§

Nếu tự tạo client:

~~~java
WebTestClient webTestClient = WebTestClient
    .bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Static import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
~~~

Đảm bảo Spring Security WebFlux filter chain được gắn vào client. Nếu dùng bind trực tiếp vào controller mà không có security filters, kết quả không đại diện cho HTTP authorization của ứng dụng.

## 14. Kiểm thử converter claims thành authorities

Production có thể cấu hình §JwtGrantedAuthoritiesConverter§ hoặc custom converter. Ví dụ issuer gửi scope dưới dạng mảng §permissions§:

~~~json
{
  "sub": "alice",
  "permissions": ["orders.read", "orders.write"]
}
~~~

Một converter có thể map thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Khi test bằng:

~~~java
.mutateWith(mockJwt().authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")))
~~~

ta đã bỏ qua converter. Để test converter:

1. Tạo §Jwt§ fixture có claim §permissions§.
2. Gọi converter production trực tiếp.
3. Assert authorities tạo ra.
4. Thêm integration test Bearer header qua authentication manager/decoder được cấu hình với converter đó.

Không tự gán authority rồi kết luận converter hoạt động.

### 14.1. Test converter trực tiếp

~~~java
@Test
void permissionsClaimMapsToAuthorities() {
    Jwt jwt = Jwt.withTokenValue("test")
        .header("alg", "none")
        .claim("sub", "alice")
        .claim("permissions", List.of("orders.read", "orders.write"))
        .build();

    Collection<GrantedAuthority> authorities =
        permissionsAuthoritiesConverter.convert(jwt);

    assertThat(authorities)
        .extracting(GrantedAuthority::getAuthority)
        .containsExactlyInAnyOrder(
            "SCOPE_orders.read",
            "SCOPE_orders.write");
}
~~~

Đoạn test giả định converter §permissionsAuthoritiesConverter§ là bean production được inject và dùng AssertJ. JWT fixture này chỉ dành cho converter test; header §alg=none§ không được dùng để xác minh token production.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
§mockJwt()§ test trả 403 | Không có authority endpoint yêu cầu | Đặt §.authorities(...)§ đúng scope |
Controller nhận principal null | Security filters không chạy hoặc test không dùng helper | Kiểm tra WebTestClient và Spring Security setup |
Controller nhận sai kiểu principal | Endpoint dùng opaque principal nhưng test JWT | Dùng helper đúng token type |
Test pass dù JWT chữ ký sai | §mockJwt()§ bỏ qua decoder | Gửi Bearer JWT qua decoder integration test |
Test pass dù audience sai | Claims fixture không chạy audience validator | Test validator/decoder thật |
Custom scope converter lỗi nhưng test vẫn pass | Authority đã được gán trực tiếp | Test converter riêng và Bearer pipeline |
§@WithMockUser§ pass nhưng controller lỗi | Principal type khác §Jwt§ | Dùng §mockJwt()§ |
§@AuthenticationPrincipal Jwt§ không bind | SecurityContext không chứa JwtAuthenticationToken | Kiểm tra authentication fixture và filter chain |
Reactive method security không chạy | Thiếu §@EnableReactiveMethodSecurity§ hoặc gọi method ngoài proxy | Import config và gọi qua Spring bean |
Test WebFlux vô tình gọi issuer thật | Test context dùng discovery/JWKS production | Inject decoder test và cô lập properties |
POST bị từ chối trước scope check | CSRF hoặc custom filter | Xác định lớp từ chối; cấu hình test theo đúng policy |
Hai test dùng default claims cho kết quả khác nhau sau upgrade | Dựa vào defaults của helper | Đặt claims/authorities tường minh |
Test controller trực tiếp trả 200 | Không đi qua security filter chain | Dùng WebFluxTest/SpringBootTest hoặc apply springSecurity |
Test tenant khác vẫn 200 | Chưa có domain authorization hoặc chỉ kiểm scope | Kiểm tenant/owner trong service |

## 16. Ma trận chọn test

| Câu hỏi | Công cụ |
|---|---|
Controller đọc §sub§, §tenant_id§ đúng không? | §mockJwt().jwt(...)§ |
GET cần §SCOPE_orders.read§ không? | §mockJwt().authorities(...)§ |
Thiếu scope có bị 403 không? | §mockJwt()§ với authority sai |
Không có JWT có bị 401 không? | WebTestClient không dùng mock authentication |
Method security có chặn đúng không? | §mockJwt()§ + reactive method security config |
Custom claim converter hoạt động không? | Unit test converter và Bearer integration |
Bearer header có được đọc không? | WebTestClient + Authorization header |
Decoder có kiểm signature/JWKS không? | Test decoder/JWKS thật |
Issuer/audience/expiry validators có chạy không? | Validator/decoder integration test |
JWT key rotation có hoạt động không? | JWKS test server và signed tokens |
Opaque introspection có active=false không? | Opaque introspector test, không dùng mockJwt |
DPoP proof/replay có hợp lệ không? | DPoP verifier/replay integration test |

## 17. Quy trình viết test WebFlux với mockJwt()

Một trình tự thực tế:

1. **Chọn đúng token type:** API dùng JWT hay opaque token; với JWT, dùng §mockJwt()§.
2. **Nạp filter chain:** xác nhận WebTestClient chạy đúng Spring Security WebFlux filters.
3. **Dựng claims:** đặt §sub§, tenant, issuer/audience hoặc metadata mà controller cần.
4. **Dựng authorities:** gán scope/role chính xác cho nhánh authorization.
5. **Kiểm controller:** xác minh §@AuthenticationPrincipal Jwt§ hoặc reactive SecurityContext.
6. **Kiểm quyền:** test thiếu token, thiếu scope, đủ scope và sai tenant.
7. **Kiểm method security:** bật reactive method security và gọi service qua Spring proxy.
8. **Kiểm converter riêng:** không gán sẵn authority nếu mục tiêu là test mapping từ claim.
9. **Kiểm decoder riêng:** gửi Bearer JWT qua filter chain với decoder test/JWKS.
10. **Giữ test độc lập:** không để test mock authentication vô tình gọi Authorization Server thật.

## 18. Kết luận

~~~text
mockJwt()
  = WebTestClient mock authentication for JWT Resource Server
  = customize Jwt claims
  = customize GrantedAuthority values
  = test controller / method / HTTP authorization

mockJwt()
  != parse a compact Bearer JWT
  != verify JWS signature or JWKS
  != run ReactiveJwtDecoder validators
  != prove issuer / audience / expiry validation

BEARER INTEGRATION TEST
  Authorization: Bearer <test JWT>
       |
       v
  AuthenticationWebFilter
       |
       v
  ReactiveAuthenticationManager
       |
       v
  ReactiveJwtDecoder
       |
       v
  JwtAuthenticationToken
       |
       v
  Authorization + Controller
~~~

§mockJwt()§ là công cụ phù hợp để kiểm thử **phần ứng dụng xử lý JWT principal sau authentication** trong WebFlux. Dùng §.jwt(...)§ để tùy chỉnh claims và §.authorities(...)§ để đặt quyền tường minh; từ đó kiểm tra controller arguments, scope rules, method security và tenant policy.

Khi cần chứng minh token thật được xác minh, hãy gửi Bearer JWT qua WebTestClient và cấu hình §ReactiveJwtDecoder§/test JWKS phù hợp. Việc tách test mock principal khỏi test decoder giúp kết quả rõ ràng: một nhóm chứng minh authorization/controller hoạt động với principal đã xác thực, nhóm còn lại chứng minh Resource Server chỉ tạo principal khi JWT đáp ứng trust contract.

## Tài liệu tham khảo

- [Spring Security Reference — Testing Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/test/index.html): test support cho WebFlux và WebTestClient.
- [Spring Security Reference — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): reactive OAuth2 test support và §mockJwt()§.
- [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html): WebTestClient configurers như §mockJwt()§ và §springSecurity()§.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder, authentication manager và JWT validation.
- [Spring Security API — JwtAuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationToken.html): JWT authentication và authorities.
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html): JWT claims và builder.
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): reactive method authorization.
- [Spring Security Reference — Reactive Test Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): tích hợp Spring Security với WebTestClient.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT claims such as §iss§, §sub§, §aud§, §iat§, §exp§ and §jti§.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile and validation requirements.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token request semantics.
