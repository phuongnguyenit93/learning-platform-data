# Mock ReactiveJwtDecoder và ReactiveOpaqueTokenIntrospector

## 1. Vì sao mock hai component này trong kiểm thử WebFlux?

Spring Security WebFlux có thể xác thực access token theo hai cách phổ biến:

- **JWT:** Resource Server chuyển compact token cho `ReactiveJwtDecoder`. Decoder trả về `Mono<Jwt>` sau khi giải mã và xác minh token.
- **Opaque token:** Resource Server chuyển token cho `ReactiveOpaqueTokenIntrospector`. Introspector gọi Authorization Server hoặc một adapter tương ứng và trả về `Mono<OAuth2AuthenticatedPrincipal>` khi token active.

Khi kiểm thử một ứng dụng reactive, ta thường muốn xác minh toàn bộ security chain và HTTP behavior mà không cần gọi Identity Provider thật. Cách hữu ích là **mock đúng dependency ở ranh giới xác minh token**, còn giữ nguyên các thành phần Spring Security phía trên:

~~~text
WebTestClient
    |
    v
SecurityWebFilterChain
    |
    v
BearerTokenAuthenticationWebFilter
    |
    v
ReactiveAuthenticationManager
    |
    +---- JWT: ReactiveJwtDecoder (mock)
    |
    +---- Opaque: ReactiveOpaqueTokenIntrospector (mock)
    |
    v
Authentication + authorities
    |
    v
Authorization rules
    |
    v
Controller / service
~~~

Với cách này, test vẫn chạy qua việc đọc Authorization header, reactive authentication manager, chuyển Authentication, authorization rules và controller. Ta kiểm soát kết quả xác minh token bằng Mockito.

Cần phân biệt hai mục tiêu:

- Mock decoder/introspector để kiểm tra **security filter chain có gọi đúng component và xử lý kết quả reactive ra sao**.
- Mock Authentication trực tiếp bằng `mockJwt()` hoặc `mockOpaqueToken()` để kiểm tra controller/authorization mà không chạy decoder/introspector.

Hai kiểu test này bổ sung cho nhau. Chúng không chứng minh cùng một điều.

## 2. Hai reactive interfaces có hợp đồng khác nhau

### 2.1. ReactiveJwtDecoder

Interface `ReactiveJwtDecoder` nằm trong package:

~~~java
org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
~~~

Phương thức chính:

~~~java
Mono<Jwt> decode(String token);
~~~

Đầu vào là giá trị access token. Kết quả là một `Mono<Jwt>`:

- `Mono.just(jwt)`: decoder đã chấp nhận token và trả JWT.
- `Mono.error(...)`: token không được xác minh hoặc decoder gặp lỗi.
- `Mono.empty()`: không phải kết quả thành công thông thường của decoder; nên coi là contract bất thường và kiểm tra cách application xử lý.

Trong production, decoder thực hiện những công việc như parse compact JWT, kiểm tra chữ ký, key, issuer, timestamp và các validators đã cấu hình. Khi mock decoder, những kiểm tra này **được thay thế bằng kết quả stub**.

### 2.2. ReactiveOpaqueTokenIntrospector

Interface `ReactiveOpaqueTokenIntrospector` nằm trong package:

~~~java
org.springframework.security.oauth2.server.resource.introspection
~~~

Phương thức:

~~~java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
~~~

Đầu vào là opaque access token. Kết quả:

- `Mono.just(principal)`: introspection xác nhận token active và trả attributes/authorities.
- `Mono.error(new BadOpaqueTokenException(...))`: token không hợp lệ hoặc inactive.
- `Mono.error(...)` với lỗi khác: introspection dependency hoặc protocol gặp vấn đề.

Trong production, introspector thường gọi RFC 7662 endpoint bằng HTTP client đã cấu hình. Khi mock interface này, test không gửi HTTP đến Authorization Server; test chỉ kiểm tra phần Resource Server nhận và xử lý kết quả introspection.

### 2.3. So sánh

| Đặc điểm | ReactiveJwtDecoder | ReactiveOpaqueTokenIntrospector |
|---|---|---|
| Đầu vào | Compact JWT | Opaque token |
| Kiểu kết quả | `Mono<Jwt>` | `Mono<OAuth2AuthenticatedPrincipal>` |
| Thành phần được mock | JWT decoder | Token introspector |
| Dữ liệu xác thực | Claims và JWT headers | Introspection attributes |
| Thành phần bị bỏ qua khi mock | Signature/JWKS/validators trong decoder thật | HTTP introspection/client authentication/schema của AS |
| Dùng trong | JWT Resource Server | Opaque-token Resource Server |

Không truyền một `Jwt` vào `ReactiveOpaqueTokenIntrospector` hoặc một `OAuth2AuthenticatedPrincipal` vào decoder. Đây là hai contract khác nhau.

## 3. Cấu hình JWT Resource Server trong WebFlux

Một cấu hình Servlet dùng `HttpSecurity`/`SecurityFilterChain`. WebFlux dùng `ServerHttpSecurity`/`SecurityWebFilterChain`.

Ví dụ:

~~~java
@Configuration
@EnableWebFluxSecurity
public class JwtApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveJwtDecoder jwtDecoder) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtDecoder(jwtDecoder))
            )
            .build();
    }
}
~~~

Điểm quan trọng là chain nhận `ReactiveJwtDecoder` qua dependency injection. Trong test, thay bean decoder bằng Mockito mock thì filter chain vẫn là cấu hình thật và vẫn phải xử lý request.

Một decoder production có thể được tạo từ issuer location, JWK Set URI hoặc custom configuration. Khi test thay thế bean decoder, không cần gọi discovery/JWKS endpoint thật.

Nếu ứng dụng dùng auto-configuration, hãy xác nhận bean được mock chính là bean mà chain đang sử dụng. Nếu có nhiều decoder hoặc nhiều `SecurityWebFilterChain`, xác định rõ chain và decoder tương ứng với endpoint đang test.

## 4. Mock ReactiveJwtDecoder bằng Mockito

### 4.1. Dùng @MockitoBean trong Spring test context

Với Spring Framework 6.2 / Spring Boot 3.4 trở lên, có thể dùng `@MockitoBean` để thay bean trong ApplicationContext bằng Mockito mock:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
@AutoConfigureWebTestClient
class JwtResourceServerTests {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;
}
~~~

`@MockitoBean` nằm trong package:

~~~java
org.springframework.test.context.bean.override.mockito.MockitoBean
~~~

Với các phiên bản Spring Boot cũ hơn, dự án có thể dùng `@MockBean`:

~~~java
import org.springframework.boot.test.mock.mockito.MockBean;

@MockBean
ReactiveJwtDecoder jwtDecoder;
~~~

`@MockBean` đã được deprecated trong một số phiên bản Boot mới để chuyển sang bean override annotations. Hãy dùng annotation có trong dependency version của dự án; không khai báo cả hai cho cùng một bean.

### 4.2. Tạo Jwt giả lập

Một JWT object cho test có thể được dựng bằng builder:

~~~java
private Jwt jwtWithReadScope() {
    Instant now = Instant.now();

    return Jwt.withTokenValue("jwt-fixture-001")
        .header("alg", "RS256")
        .header("kid", "test-key-01")
        .issuer(URI.create("https://id.example.test/realms/shop"))
        .subject("user-123")
        .audience(List.of("orders-api"))
        .issuedAt(now)
        .expiresAt(now.plusSeconds(300))
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")
        .claim("client_id", "orders-web")
        .build();
}
~~~

Imports:

~~~java
import java.net.URI;
import java.time.Instant;
import java.util.List;

import org.springframework.security.oauth2.jwt.Jwt;
~~~

Header `alg` và `kid` ở đây chỉ là metadata của object JWT được dựng trong test. Vì decoder bị mock, object này không phải compact JWT đã được ký và xác minh. Không dùng test này để khẳng định chữ ký RS256 hoặc JWKS configuration hoạt động.

### 4.3. Stub decoder trả về Mono.just

~~~java
@Test
void acceptsJwtAndAllowsReadScope() {
    Jwt jwt = jwtWithReadScope();

    when(jwtDecoder.decode("jwt-fixture-001"))
        .thenReturn(Mono.just(jwt));

    webTestClient.get()
        .uri("/api/orders/42")
        .headers(headers ->
            headers.setBearerAuth("jwt-fixture-001")
        )
        .exchange()
        .expectStatus().isOk();

    verify(jwtDecoder).decode("jwt-fixture-001");
}
~~~

Imports Mockito/Reactor:

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import reactor.core.publisher.Mono;
~~~

WebTestClient gửi Bearer token bình thường. Security chain trích xuất token, gọi decoder mock và dùng JWT trả về để tạo authentication. Vì JWT có scope `orders.read`, converter mặc định có thể tạo authority `SCOPE_orders.read` và URL policy cho phép request.

Đây là kiểm thử tích hợp security chain ở mức Resource Server authentication. Nó chưa kiểm tra decoder thật.

### 4.4. Kiểm tra thiếu scope trả 403

~~~java
@Test
void authenticatedJwtWithoutRequiredScopeIsForbidden() {
    Instant now = Instant.now();

    Jwt jwt = Jwt.withTokenValue("jwt-profile-only")
        .header("alg", "RS256")
        .subject("user-123")
        .issuedAt(now)
        .expiresAt(now.plusSeconds(300))
        .claim("scope", "profile.read")
        .build();

    when(jwtDecoder.decode("jwt-profile-only"))
        .thenReturn(Mono.just(jwt));

    webTestClient.get()
        .uri("/api/orders/42")
        .headers(headers ->
            headers.setBearerAuth("jwt-profile-only")
        )
        .exchange()
        .expectStatus().isForbidden();

    verify(jwtDecoder).decode("jwt-profile-only");
}
~~~

Test này chứng minh token đã được chấp nhận thành JWT Authentication, nhưng authority không đáp ứng policy. Kết quả thường là 403.

### 4.5. Decoder trả lỗi xác thực

Khi decoder phát ra lỗi JWT, Resource Server phải xử lý nó như authentication failure:

~~~java
@Test
void decoderFailureProducesUnauthorizedResponse() {
    when(jwtDecoder.decode("bad-jwt"))
        .thenReturn(Mono.error(
            new JwtException("Invalid test token")
        ));

    webTestClient.get()
        .uri("/api/orders/42")
        .headers(headers -> headers.setBearerAuth("bad-jwt"))
        .exchange()
        .expectStatus().isUnauthorized();

    verify(jwtDecoder).decode("bad-jwt");
}
~~~

Imports:

~~~java
import org.springframework.security.oauth2.jwt.JwtException;
~~~

Trong test, message chỉ là nội dung lỗi nội bộ. Không nên phản chiếu chi tiết exception hoặc token raw về client trong response production.

### 4.6. Không có Bearer token thì decoder không được gọi

~~~java
@Test
void missingBearerTokenDoesNotInvokeDecoder() {
    webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isUnauthorized();

    verifyNoInteractions(jwtDecoder);
}
~~~

Test này kiểm tra protected endpoint từ chối anonymous request và decoder không bị gọi khi không có token.

Imports:

~~~java
import static org.mockito.Mockito.verifyNoInteractions;
~~~

## 5. Mock ReactiveOpaqueTokenIntrospector

### 5.1. Cấu hình opaque-token Resource Server

Một chain opaque-token có thể cấu hình như sau:

~~~java
@Configuration
@EnableWebFluxSecurity
public class OpaqueApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/partners/**")
                    .hasAuthority("SCOPE_partner.reports.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque ->
                    opaque.introspector(introspector)
                )
            )
            .build();
    }
}
~~~

Chain này dùng introspector được inject. Trong test, mock interface đó để điều khiển phản hồi active/inactive và attributes.

JWT và opaque-token DSL là hai lựa chọn cho Resource Server configuration. Nếu một ứng dụng hỗ trợ cả hai, hãy xác định rõ endpoint/chain nào sử dụng loại token nào, tránh cấu hình mơ hồ hoặc để cùng một endpoint nhận token ngoài contract.

### 5.2. Tạo OAuth2AuthenticatedPrincipal

Dùng `DefaultOAuth2AuthenticatedPrincipal` để tạo principal giả lập:

~~~java
private OAuth2AuthenticatedPrincipal activePartnerPrincipal() {
    Map<String, Object> attributes = new HashMap<>();
    attributes.put("sub", "partner-user-01");
    attributes.put("client_id", "partner-client");
    attributes.put("scope", "partner.reports.read");
    attributes.put("tenant_id", "partner-a");

    Collection<GrantedAuthority> authorities = List.of(
        new SimpleGrantedAuthority("SCOPE_partner.reports.read")
    );

    return new DefaultOAuth2AuthenticatedPrincipal(
        "partner-user-01",
        attributes,
        authorities
    );
}
~~~

Imports:

~~~java
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
~~~

Trong ví dụ, principal có cả attributes và authorities. Introspector implementation thường chịu trách nhiệm tạo principal cùng authorities từ response contract. Test cần dùng đúng principal shape mà application dự kiến nhận.

### 5.3. Stub introspector trả principal active

~~~java
@Test
void activeOpaqueTokenCanReadPartnerReport() {
    when(introspector.introspect("opaque-fixture-001"))
        .thenReturn(Mono.just(activePartnerPrincipal()));

    webTestClient.get()
        .uri("/api/partners/reports/2026")
        .headers(headers ->
            headers.setBearerAuth("opaque-fixture-001")
        )
        .exchange()
        .expectStatus().isOk();

    verify(introspector).introspect("opaque-fixture-001");
}
~~~

Request vẫn dùng Bearer scheme. Khác biệt nằm ở phía server: token được gửi tới `ReactiveOpaqueTokenIntrospector` thay vì JWT decoder.

### 5.4. Thiếu authority sau introspection trả 403

~~~java
@Test
void activeOpaqueTokenWithoutReportScopeIsForbidden() {
    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "partner-user-01",
            Map.of(
                "sub", "partner-user-01",
                "scope", "partner.profile.read"
            ),
            List.of(
                new SimpleGrantedAuthority(
                    "SCOPE_partner.profile.read"
                )
            )
        );

    when(introspector.introspect("opaque-profile-token"))
        .thenReturn(Mono.just(principal));

    webTestClient.get()
        .uri("/api/partners/reports/2026")
        .headers(headers ->
            headers.setBearerAuth("opaque-profile-token")
        )
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Đây là token đã được introspector xác nhận active nhưng principal không có authority endpoint yêu cầu. Nó khác với token inactive, vốn phải thất bại ở authentication.

### 5.5. Introspector từ chối token inactive

Một introspector tuân contract thường phát ra `BadOpaqueTokenException` khi token không active:

~~~java
@Test
void inactiveOpaqueTokenIsUnauthorized() {
    when(introspector.introspect("inactive-token"))
        .thenReturn(Mono.error(
            new BadOpaqueTokenException("Token is inactive")
        ));

    webTestClient.get()
        .uri("/api/partners/reports/2026")
        .headers(headers -> headers.setBearerAuth("inactive-token"))
        .exchange()
        .expectStatus().isUnauthorized();

    verify(introspector).introspect("inactive-token");
}
~~~

Import:

~~~java
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
~~~

Khi mock introspector, hãy mô phỏng đúng contract: inactive token được biểu diễn bằng authentication error. Không trả một principal có attribute `active=false` rồi mong Resource Server tự hiểu nó là token inactive; việc diễn giải response introspection thuộc introspector.

## 6. Dùng @MockitoBean và WebTestClient cho test filter chain

Một test class hoàn chỉnh có thể dùng:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class JwtResourceServerTests {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    @Test
    void authenticatedJwtCanReadOrders() {
        Jwt jwt = jwtWithReadScope();

        when(jwtDecoder.decode("jwt-fixture-001"))
            .thenReturn(Mono.just(jwt));

        webTestClient.get()
            .uri("/api/orders/42")
            .headers(h -> h.setBearerAuth("jwt-fixture-001"))
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Đây là ví dụ cho Spring Framework 6.2+; nếu dự án dùng Spring Boot cũ hơn, thay `@MockitoBean` bằng `@MockBean` theo version.

Với slice test `@WebFluxTest`, cần import security configuration và controller được kiểm tra. Slice test có thể không load toàn bộ application configuration, vì vậy đừng giả định bean mock tự động được nối vào chain. `@SpringBootTest` hữu ích khi muốn xác nhận wiring gần với ứng dụng thực tế.

## 7. Mock decoder/introspector khác mock Authentication

Spring Security Test cũng có các WebFlux request mutators như `mockJwt()` và `mockOpaqueToken()` (tên/package/availability phụ thuộc version). Chúng đặt Authentication giả lập trực tiếp vào request.

| Mục tiêu | Cách làm | Component được gọi? |
|---|---|---|
| Kiểm tra URL authorization với JWT principal giả lập | `mockJwt()` | Không gọi ReactiveJwtDecoder |
| Kiểm tra controller với opaque principal giả lập | `mockOpaqueToken()` | Không gọi ReactiveOpaqueTokenIntrospector |
| Kiểm tra Bearer extraction và JWT authentication manager | Mock ReactiveJwtDecoder, gửi Bearer header | Có |
| Kiểm tra Bearer extraction và opaque authentication manager | Mock ReactiveOpaqueTokenIntrospector, gửi Bearer header | Có |
| Kiểm tra chữ ký JWT thật | Decoder thật với test key/JWKS | Có |
| Kiểm tra HTTP introspection thật | Introspector thật với mock HTTP server/sandbox | Có |

Không dùng `mockJwt()` rồi `verify(jwtDecoder).decode(...)`: request post-processor đã bỏ qua decoder, nên mock không được gọi. Tương tự, `mockOpaqueToken()` không gọi introspector.

## 8. Kiểm thử reactive error và publisher behavior

Vì hai interface trả về Reactor `Mono`, stub cần trả một publisher. Không trả `Jwt` hoặc principal trực tiếp từ Mockito.

### 8.1. Thành công

~~~java
when(jwtDecoder.decode("good-token"))
    .thenReturn(Mono.just(jwt));
~~~

### 8.2. Lỗi xác thực

~~~java
when(jwtDecoder.decode("bad-token"))
    .thenReturn(Mono.error(new JwtException("Invalid JWT")));
~~~

### 8.3. Lỗi introspection

~~~java
when(introspector.introspect("inactive-token"))
    .thenReturn(Mono.error(
        new BadOpaqueTokenException("Inactive token")
    ));
~~~

### 8.4. Publisher rỗng

`Mono.empty()` khác `Mono.error(...)` và `Mono.just(...)`. Không dùng empty để mô tả token invalid nếu contract của component yêu cầu authentication exception. Một publisher rỗng có thể dẫn tới hành vi không mong đợi trong authentication pipeline; nếu application có wrapper/adapter riêng, hãy test rõ empty case và quy định cách chuyển thành lỗi.

### 8.5. Không block reactive pipeline

Trong WebFlux test, dùng `WebTestClient` và để framework subscribe publisher. Không gọi `block()` trong controller, filter hoặc reactive authentication code chỉ để test dễ hơn. Khi kiểm tra một service/adapter reactive riêng, có thể dùng `StepVerifier`:

~~~java
StepVerifier.create(tokenService.resolve("test-token"))
    .expectNextMatches(result ->
        result.getSubject().equals("user-123")
    )
    .verifyComplete();
~~~

`StepVerifier` phù hợp để kiểm tra publisher contract của code reactive do ứng dụng viết. Nó không thay thế HTTP integration test qua `SecurityWebFilterChain`.

## 9. Kiểm thử claims, authorities và principal shape

### 9.1. JWT claims

Với decoder mock trả `Jwt`, kiểm tra:

- Subject được controller đọc đúng.
- Issuer/audience claims được truyền đúng vào application layer.
- Tenant claim được đọc đúng.
- Custom claims có kiểu dữ liệu mà converter/service mong đợi.
- Authorities được tạo theo scope/role mapping.
- Claim thiếu hoặc sai kiểu không tạo quyền ngoài dự kiến.

Lưu ý: vì decoder mock đã trả `Jwt`, test này không chứng minh issuer/audience validators đã thực thi. Nếu muốn kiểm tra validators, cần test decoder thật.

### 9.2. Opaque principal attributes

Với introspector mock trả `OAuth2AuthenticatedPrincipal`, kiểm tra:

- Subject và client ID.
- Scope/authorities.
- Tenant hoặc partner identifier.
- Attributes optional/missing.
- Kiểu dữ liệu của claims.
- Quyền được phép/từ chối.

Không giả định opaque principal có `Jwt#getClaims()`. Dùng contract `OAuth2AuthenticatedPrincipal#getAttribute(...)` hoặc `getAttributes()`.

### 9.3. Không trộn role và scope

Ví dụ authority `SCOPE_orders.read` không giống `ROLE_ADMIN`. Khi stub JWT/opaque principal, tạo authority đúng với policy mà test đang kiểm tra. Nếu converter production tạo authorities, hãy có test riêng cho converter/wiring.

## 10. Kiểm tra đúng HTTP semantics

| Request/result | Ý nghĩa | Kết quả thường gặp |
|---|---|---|
| Không có Bearer token trên protected route | Chưa authenticated | 401 |
| JWT decoder trả `Mono.just(jwt)`, scope đúng | Authenticated và authorized | 2xx |
| JWT decoder trả JWT thiếu scope | Authenticated nhưng thiếu quyền | 403 |
| JWT decoder phát `JwtException` | Authentication failure | 401 |
| Introspector trả principal có scope | Active opaque token | 2xx |
| Introspector phát `BadOpaqueTokenException` | Token inactive/invalid | 401 |
| Principal active nhưng thiếu scope | Authorization denied | 403 |
| Introspection service unavailable | Dependency failure | Theo exception translation và availability policy của ứng dụng |

Không mặc định mọi lỗi từ introspector phải trở thành cùng một status. `BadOpaqueTokenException` mô tả token không hợp lệ; lỗi mạng, timeout hoặc credential của Resource Server với AS là các nhóm lỗi vận hành khác. Hãy kiểm tra exception mapping và authentication entry point của application, không gộp tất cả thành “invalid token”.

## 11. Xác nhận decoder mock được dùng bởi chain

Một lỗi thường gặp là mock đúng interface nhưng chain lại dùng decoder khác được tạo bên trong configuration.

Kiểm tra các điểm sau:

1. Security configuration nhận `ReactiveJwtDecoder` qua constructor/bean injection.
2. `@MockitoBean` thay đúng bean trong context.
3. Không có nhiều `ReactiveJwtDecoder` beans mà qualifier khác đang được dùng.
4. Request đang đi qua đúng `SecurityWebFilterChain`.
5. Test gửi `Authorization: Bearer ...`, không gắn Authentication trực tiếp bằng mock post-processor.
6. Sau khi WebTestClient exchange hoàn tất, `verify(jwtDecoder).decode(token)` xác nhận decoder đã được gọi.

Với opaque token, áp dụng các bước tương tự cho `ReactiveOpaqueTokenIntrospector`.

Nếu decoder/introspector không được gọi, hãy kiểm tra route matcher, security chain order, test context và cách test client được bind. Đừng đổi assertion để làm test pass khi component cần kiểm tra chưa được gọi.

## 12. Lỗi thường gặp khi mock reactive components

### Lỗi 1 — Trả object thay vì Mono

Sai:

~~~java
when(jwtDecoder.decode("token")).thenReturn(jwt);
~~~

Đúng:

~~~java
when(jwtDecoder.decode("token")).thenReturn(Mono.just(jwt));
~~~

Tương tự, introspector phải trả `Mono.just(principal)`.

### Lỗi 2 — Dùng Mono.just(null)

Reactor không cho phép `Mono.just(null)`. Dùng `Mono.empty()` nếu contract thật sự cho phép empty; với invalid token, thường dùng authentication exception qua `Mono.error(...)`.

### Lỗi 3 — Mock cả AuthenticationManager

Nếu mục tiêu là kiểm tra decoder/introspector integration, mock `ReactiveAuthenticationManager` sẽ bỏ qua component đang muốn kiểm tra. Mock đúng decoder hoặc introspector, giữ authentication manager/filter chain thật.

### Lỗi 4 — Dùng mockJwt() rồi verify decoder

`mockJwt()` đã tạo Authentication trực tiếp. Decoder không được gọi.

### Lỗi 5 — Dùng mockOpaqueToken() rồi verify introspector

`mockOpaqueToken()` cũng bypass introspector. Dùng Bearer header và mock dependency.

### Lỗi 6 — Nghĩ JWT object được dựng bằng builder đã có chữ ký

`Jwt.withTokenValue(...)` tạo object để test principal/claims. Nó không tạo compact JWT có chữ ký hợp lệ. Chữ ký chỉ được kiểm tra khi compact token đi qua decoder thật.

### Lỗi 7 — Kỳ vọng mock decoder tự validate issuer/audience

Mock decoder chỉ trả kết quả stub. Nếu stub trả `Mono.just(jwt)`, Resource Server sẽ nhận JWT đó; validators bên trong decoder thật đã bị thay thế. Dùng token sai và decoder thật nếu mục tiêu là kiểm tra validation.

### Lỗi 8 — Stub đúng token nhưng request gửi token khác

Mockito stub theo đối số. Nếu request dùng token string khác, stub có thể không match và trả `null`, dẫn tới lỗi khó hiểu. Dùng constant cho fixture token và kiểm tra invocation arguments.

### Lỗi 9 — Quên rằng reactive work chạy khi subscribe

Một số lời gọi xảy ra trong quá trình WebTestClient exchange subscribe publisher. Thực hiện `verify(...)` sau khi exchange hoàn tất. Không verify trước khi publisher được thực thi.

### Lỗi 10 — Dùng @MockBean/@MockitoBean không đúng version

Annotation và package phụ thuộc Spring Framework/Boot version. Kiểm tra dependency tree và test API của version dự án trước khi chọn bean override annotation.

## 13. Chiến lược test theo tầng

Một bộ WebFlux Resource Server tests có thể chia thành:

~~~mermaid
flowchart TD
    A["Unit test converter / adapter"] --> B["WebTestClient + mocked decoder/introspector"]
    B --> C["Signed JWT + real ReactiveJwtDecoder"]
    B --> D["HTTP stub + real ReactiveOpaqueTokenIntrospector"]
    C --> E["JWKS / issuer / audience / expiry"]
    D --> F["Introspection protocol / active / timeout"]
    E --> G["Authorization and API behavior"]
    F --> G
~~~

### Tầng 1 — Unit tests cho code reactive của ứng dụng

Kiểm tra custom claim converter, adapter, principal mapping và error mapping. Dùng Mockito và `StepVerifier` khi cần kiểm tra publisher behavior.

### Tầng 2 — WebTestClient với decoder/introspector mock

Giữ SecurityWebFilterChain thật, gửi Bearer header và mock đúng interface. Kiểm tra token được chuyển tới dependency, Authentication được tạo, authorities được áp dụng và HTTP status đúng.

### Tầng 3 — Decoder thật với test signing key

Dùng private key test để ký JWT, public key/JWKS test để xác minh. Kiểm tra signature, issuer, audience, timestamp, algorithm và key rotation. Không dùng production signing key.

### Tầng 4 — Introspector thật với HTTP stub hoặc sandbox

Dùng mock HTTP server để kiểm tra request introspection, client authentication, response `active`, schema, timeout và error mapping. Sandbox test xác nhận contract với provider thực khi cần.

Không cần gọi production Authorization Server trong mọi pull request. Unit và WebFlux integration tests nên deterministic, độc lập mạng.

## 14. Checklist khi mock ReactiveJwtDecoder hoặc ReactiveOpaqueTokenIntrospector

- [ ] Đã xác định endpoint đang dùng JWT hay opaque token.
- [ ] Mock đúng interface reactive tương ứng.
- [ ] Stub trả `Mono.just(...)` hoặc `Mono.error(...)`, không trả object trực tiếp.
- [ ] Giữ nguyên SecurityWebFilterChain và reactive authentication manager.
- [ ] Gửi Bearer token qua Authorization header.
- [ ] Xác nhận mock dependency thực sự được gọi.
- [ ] Test token được chấp nhận.
- [ ] Test token invalid/inactive.
- [ ] Test authenticated principal thiếu authority trả 403.
- [ ] Kiểm tra JWT claims hoặc opaque attributes theo principal contract.
- [ ] Không coi decoder mock là kiểm thử chữ ký/issuer/audience/JWKS.
- [ ] Không coi introspector mock là kiểm thử HTTP introspection/client authentication.
- [ ] Có test decoder thật với test key nếu ứng dụng phụ thuộc JWT validation.
- [ ] Có test introspector thật với HTTP stub nếu ứng dụng phụ thuộc opaque introspection.
- [ ] Không dùng `mockJwt()`/`mockOpaqueToken()` khi mục tiêu là verify decoder/introspector invocation.
- [ ] Kiểm tra version tương thích của `@MockitoBean` hoặc `@MockBean`.

## 15. Kết luận

`ReactiveJwtDecoder` và `ReactiveOpaqueTokenIntrospector` là hai ranh giới xác minh access token khác nhau trong Spring Security WebFlux. Mock chúng bằng Mockito cho phép kiểm tra security filter chain mà không cần gọi issuer thật:

- Với JWT, stub `decode(token)` trả `Mono<Jwt>` hoặc lỗi.
- Với opaque token, stub `introspect(token)` trả `Mono<OAuth2AuthenticatedPrincipal>` hoặc lỗi.
- Gửi Bearer token qua `WebTestClient` để request đi qua reactive authentication manager và SecurityWebFilterChain.
- Dùng `mockJwt()`/`mockOpaqueToken()` khi chỉ muốn kiểm tra authorization với Authentication giả lập.
- Dùng decoder/introspector thật cùng test key hoặc HTTP stub khi cần xác minh chữ ký JWT hay giao thức introspection.

Giữ rõ ranh giới giữa mock authentication, mock token-verification dependency và integration với provider thật sẽ giúp test nói chính xác điều nó đã chứng minh.

### Tài liệu tham khảo

- [Spring Security Reference — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Testing Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
- [Spring Security API — ReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html)
- [Spring Security API — DefaultOAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)

