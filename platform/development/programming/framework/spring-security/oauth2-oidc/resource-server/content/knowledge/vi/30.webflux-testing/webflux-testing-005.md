# StepVerifier cho validator, converter và introspector phản ứng

## 1. Vì sao kiểm thử reactive cần cách tiếp cận khác?

Trong Spring Security WebFlux, quá trình xác thực OAuth 2.0 Resource Server thường trả về một Publisher thay vì kết quả có sẵn ngay khi gọi method. JWT decoder trả về **Mono<Jwt>**, JWT authentication converter trả về **Mono<AbstractAuthenticationToken>**, còn opaque-token introspector trả về **Mono<OAuth2AuthenticatedPrincipal>**.

Điều này có nghĩa lời gọi method chưa chắc đã thực hiện công việc. Với Reactor, Publisher thường là lazy: công việc bắt đầu khi có subscription. Nếu test chỉ gọi method rồi kiểm tra object trả về, test có thể chưa thực sự chạy phần xác thực.

**StepVerifier** của Reactor Test cho phép mô tả chuỗi tín hiệu mong đợi: phần tử được phát ra, lỗi, hoàn tất, backpressure và cancellation. Test sẽ subscribe Publisher và kiểm tra những tín hiệu thực tế theo thứ tự.

Trong bài này, ta dùng StepVerifier để kiểm tra các ranh giới reactive của Spring Security Resource Server:

- JWT decoder và kết quả validation.
- Converter ánh xạ JWT thành Authentication.
- Opaque token introspector gọi Authorization Server hoặc nguồn trạng thái token.
- Các bước kiểm tra bất đồng bộ bổ sung như tenant membership hoặc entitlement.
- Lỗi timeout, upstream failure, empty publisher và cancellation.
- Tích hợp toàn bộ security chain bằng WebTestClient.

Có một khác biệt cần giữ rõ: **OAuth2TokenValidator<Jwt> của Spring Security là API đồng bộ**. Method **validate(Jwt)** trả về **OAuth2TokenValidatorResult**, không trả về Mono. Trong reactive Resource Server, validator được ReactiveJwtDecoder gọi trong quá trình tạo **Mono<Jwt>**. Vì vậy, ta test validator trực tiếp cho logic đồng bộ và dùng StepVerifier để test decoder/pipeline phản ứng chứa validator đó. Nếu cần gọi dịch vụ bất đồng bộ để kiểm tra tenant hoặc entitlement, hãy đặt bước đó trong reactive authentication/authorization pipeline, không nhét blocking call vào validator đồng bộ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu StepVerifier subscribe và kiểm tra tín hiệu Mono/Flux như thế nào.
2. Phân biệt validator đồng bộ với ReactiveJwtDecoder.
3. Kiểm tra JWT hợp lệ, sai audience, issuer, timestamp và chữ ký.
4. Kiểm tra converter đồng bộ được bọc bằng ReactiveJwtAuthenticationConverterAdapter.
5. Kiểm tra converter thật sự bất đồng bộ khi cần tra cứu authority.
6. Kiểm tra ReactiveOpaqueTokenIntrospector với success, inactive token và lỗi upstream.
7. Dùng virtual time để test timeout, delay và TTL mà không chờ thật.
8. Kiểm tra context, cancellation và subscription.
9. Kết hợp StepVerifier với WebTestClient để test security chain WebFlux.
10. Tránh các lỗi phổ biến như gọi block(), mock quá sâu hoặc test chỉ kiểm tra object chưa được subscribe.

## 2. Chuẩn bị dependency và test fixture

### 2.1. Dependency

Ứng dụng cần Spring Security Resource Server, Spring WebFlux và Reactor Test. Với Gradle, dùng dependency management/BOM của Spring Boot để các phiên bản Spring Security và Reactor tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Nếu dự án đã có starter test, vẫn khai báo reactor-test rõ ràng khi test dùng StepVerifier, TestPublisher hoặc PublisherProbe. Không tự đặt một phiên bản Reactor Test khác với Reactor Core đang được BOM quản lý.

### 2.2. Những import thường dùng

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
~~~

Các test Spring Security thường dùng thêm:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;

import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
~~~

Tên package và một số extension point có thể khác giữa các dòng Spring Security. Hãy dùng Javadoc của đúng version đã resolve trong build.

### 2.3. Tạo JWT object cho unit test

Khi chỉ test predicate của validator hoặc converter, không cần ký token thật. Có thể tạo một đối tượng Jwt trực tiếp:

~~~java
static final String ISSUER = "https://id.example.test";
static final String AUDIENCE = "orders-api";

static Jwt validJwt() {
    Instant now = Instant.now();

    return Jwt.withTokenValue("test-access-token")
        .header("alg", "RS256")
        .issuer(ISSUER)
        .subject("user-417")
        .audience(List.of(AUDIENCE))
        .issuedAt(now.minusSeconds(10))
        .expiresAt(now.plusSeconds(300))
        .claim("scope", "orders.read")
        .build();
}
~~~

Đây là fixture cho unit test claim mapping và converter. Nó không chứng minh chữ ký JWT được xác minh. Khi test chữ ký hoặc decoder thật, hãy tạo compact JWT bằng private key test và cấu hình decoder với public key tương ứng.

---

## 3. StepVerifier kiểm tra tín hiệu như thế nào?

### 3.1. Một Mono thành công

Ví dụ đơn giản:

~~~java
@Test
void emitsOneValueAndCompletes() {
    Mono<String> result = Mono.just("orders-api");

    StepVerifier.create(result)
        .expectNext("orders-api")
        .verifyComplete();
}
~~~

**verifyComplete()** vừa khai báo tín hiệu kết thúc mong đợi, vừa subscribe và chạy test. Nếu Publisher phát lỗi, phát sai giá trị hoặc không kết thúc, test thất bại.

### 3.2. Kiểm tra giá trị bằng predicate

Khi không muốn so sánh toàn bộ object:

~~~java
StepVerifier.create(Mono.just(validJwt()))
    .assertNext(jwt -> {
        assertEquals("user-417", jwt.getSubject());
        assertTrue(jwt.getAudience().contains("orders-api"));
    })
    .verifyComplete();
~~~

**assertNext** phù hợp khi cần nhiều assertion. **expectNextMatches** phù hợp với predicate ngắn:

~~~java
StepVerifier.create(Mono.just("orders.read"))
    .expectNextMatches(scope -> scope.startsWith("orders."))
    .verifyComplete();
~~~

### 3.3. Kiểm tra lỗi

Publisher có thể kết thúc bằng error:

~~~java
StepVerifier.create(Mono.error(
        new IllegalStateException("introspection unavailable")))
    .expectError(IllegalStateException.class)
    .verify();
~~~

Khi cần kiểm tra nội dung lỗi:

~~~java
StepVerifier.create(Mono.error(
        new IllegalArgumentException("invalid audience")))
    .expectErrorSatisfies(error -> {
        assertInstanceOf(IllegalArgumentException.class, error);
        assertEquals("invalid audience", error.getMessage());
    })
    .verify();
~~~

Không chỉ kiểm tra rằng “có lỗi”. Hãy xác nhận loại lỗi phù hợp với hợp đồng của lớp đang test. Ví dụ, token sai claim là lỗi token validation; timeout Authorization Server là lỗi hạ tầng; thiếu scope sau khi xác thực là lỗi authorization.

### 3.4. Mono.empty không giống Mono.error

Ba trạng thái khác nhau:

| Publisher | Ý nghĩa | Test |
|---|---|---|
| **Mono.just(value)** | Có một kết quả | expectNext(value).verifyComplete() |
| **Mono.empty()** | Hoàn tất mà không phát kết quả | verifyComplete() và xác nhận không có phần tử |
| **Mono.error(error)** | Kết thúc bằng lỗi | expectError(...) |

Với một authentication converter hoặc introspector, phát **Mono.empty()** thường không phải cách biểu diễn “token không hợp lệ”. Hãy phát lỗi phù hợp theo contract để framework không nhầm lẫn giữa “không có kết quả” và “xác thực thất bại”.

### 3.5. Giới hạn thời gian kiểm thử

Một Publisher không kết thúc có thể làm test treo. Có thể đặt timeout cho bước verify:

~~~java
StepVerifier.create(Mono.never())
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

Trong test thực tế, chọn timeout đủ rộng cho CI nhưng đủ ngắn để phát hiện deadlock hoặc upstream không phản hồi.

### 3.6. StepVerifier kích hoạt subscription

Đoạn này chưa chạy tác vụ reactive:

~~~java
Mono<Jwt> decoded = decoder.decode(compactJwt);
~~~

Publisher chỉ mô tả công việc. Khi test dùng:

~~~java
StepVerifier.create(decoded)
    .expectNextMatches(jwt -> jwt.getSubject().equals("user-417"))
    .verifyComplete();
~~~

StepVerifier mới subscribe và quan sát kết quả. Không gọi **block()** chỉ để ép Publisher chạy trong test.

---

## 4. Kiểm thử OAuth2TokenValidator và ReactiveJwtDecoder

### 4.1. Validator của JWT là đồng bộ

Spring Security định nghĩa:

~~~java
OAuth2TokenValidatorResult validate(Jwt token);
~~~

Validator kiểm tra thuộc tính của token và trả về success hoặc failure ngay trong lời gọi. Đây không phải reactive contract. Ví dụ validator audience:

~~~java
static OAuth2TokenValidator<Jwt> audienceValidator(
        String requiredAudience) {

    return jwt -> {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        );

        return OAuth2TokenValidatorResult.failure(error);
    };
}
~~~

Có thể kết hợp validator mặc định và validator riêng:

~~~java
OAuth2TokenValidator<Jwt> validator =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator(AUDIENCE)
    );
~~~

Validator mặc định kiểm tra issuer và timestamp theo cấu hình. Validator audience bổ sung điều kiện API cần.

### 4.2. Unit test validator trực tiếp

~~~java
@Test
void acceptsJwtForExpectedAudience() {
    OAuth2TokenValidator<Jwt> validator =
        audienceValidator("orders-api");

    OAuth2TokenValidatorResult result =
        validator.validate(validJwt());

    assertTrue(result.getErrors().isEmpty());
}

@Test
void rejectsJwtForDifferentAudience() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .issuer(ISSUER)
        .subject("user-417")
        .audience(List.of("billing-api"))
        .issuedAt(Instant.now().minusSeconds(5))
        .expiresAt(Instant.now().plusSeconds(120))
        .build();

    OAuth2TokenValidatorResult result =
        audienceValidator("orders-api").validate(jwt);

    assertFalse(result.getErrors().isEmpty());
    assertEquals(
        "invalid_token",
        result.getErrors().iterator().next().getErrorCode()
    );
}
~~~

Test này kiểm tra logic validator. Không cần StepVerifier vì không có Publisher ở đây.

### 4.3. ReactiveJwtDecoder tạo Mono<Jwt>

Reactive decoder có contract:

~~~java
Mono<Jwt> decode(String token);
~~~

Với Spring Security, **NimbusReactiveJwtDecoder** có thể xác minh chữ ký, giải mã claim và gọi validator đã cấu hình. Đây là ranh giới phù hợp để dùng StepVerifier.

Ví dụ cấu hình decoder:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(
            "https://id.example.com/.well-known/jwks.json"
        ).build();

    OAuth2TokenValidator<Jwt> withIssuer =
        JwtValidators.createDefaultWithIssuer(ISSUER);

    OAuth2TokenValidator<Jwt> withAudience =
        new DelegatingOAuth2TokenValidator<>(
            withIssuer,
            audienceValidator(AUDIENCE)
        );

    decoder.setJwtValidator(withAudience);
    return decoder;
}
~~~

### 4.4. Test decoder với JWT được ký thật

Một integration-style unit test nên dùng:

- Private key test để ký JWT.
- Public key tương ứng để cấu hình decoder.
- Issuer, audience và timestamp rõ ràng.
- Compact JWT được tạo trước khi gọi decode.
- StepVerifier để kiểm tra Mono<Jwt>.

Ví dụ phần assertion:

~~~java
@Test
void decodesAndValidatesSignedJwt() {
    String compactJwt = signedJwtFixture();

    StepVerifier.create(decoder.decode(compactJwt))
        .assertNext(jwt -> {
            assertEquals(ISSUER, jwt.getIssuer().toString());
            assertEquals("user-417", jwt.getSubject());
            assertTrue(jwt.getAudience().contains(AUDIENCE));
        })
        .verifyComplete();
}
~~~

**signedJwtFixture()** là helper của test tạo token bằng private key test. Không dùng một JWT giả với header **alg=none** để chứng minh chữ ký hợp lệ.

### 4.5. Test token sai audience qua decoder

Khi decoder có audience validator:

~~~java
@Test
void decoderRejectsWrongAudience() {
    String compactJwt = signedJwtFixtureWithAudience("billing-api");

    StepVerifier.create(decoder.decode(compactJwt))
        .expectError(JwtException.class)
        .verify();
}
~~~

Tùy decoder/version, lỗi cụ thể có thể là JwtValidationException hoặc một JwtException khác. Nếu test contract chỉ yêu cầu decoder từ chối token, kiểm tra kiểu cha JwtException sẽ bền hơn so với phụ thuộc message nội bộ.

### 4.6. Phân biệt validator failure và decoder failure

| Tình huống | Lớp phát hiện | Kết quả thường thấy |
|---|---|---|
| Audience không đúng | OAuth2TokenValidator | Decode thất bại |
| Issuer không đúng | JwtIssuerValidator/default validator | Decode thất bại |
| Token hết hạn | JwtTimestampValidator | Decode thất bại |
| Compact JWT sai định dạng | Decoder/parser | Decode thất bại |
| Chữ ký không hợp lệ | Decoder/signature verifier | Decode thất bại |
| JWKS endpoint lỗi | Key retrieval/upstream | Decode thất bại do hạ tầng |

Khi test lỗi, không gộp tất cả thành một trường hợp “invalid token”. Chia test theo lớp để biết lỗi phát sinh từ policy, dữ liệu token hay dependency.

### 4.7. Kiểm tra custom asynchronous policy ở đúng tầng

Nếu policy cần gọi một dịch vụ bất đồng bộ, ví dụ kiểm tra user còn thuộc tenant hay không, không gọi HTTP/Redis blocking bên trong OAuth2TokenValidator. Validator đồng bộ sẽ chặn thread gọi nó và không thể trả Mono.

Có thể thực hiện bước kiểm tra ở reactive authorization layer:

~~~java
public interface TenantMembership {
    Mono<Boolean> isMember(String subject, String tenantId);
}
~~~

Ví dụ một ReactiveAuthorizationManager có thể trả AuthorizationDecision sau khi truy vấn membership:

~~~java
public final class TenantAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final TenantMembership membership;

    public TenantAuthorizationManager(TenantMembership membership) {
        this.membership = membership;
    }

    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        String tenantId = context.getExchange()
            .getRequest()
            .getHeaders()
            .getFirst("X-Tenant-Id");

        return authentication
            .filter(JwtAuthenticationToken.class::isInstance)
            .cast(JwtAuthenticationToken.class)
            .flatMap(auth -> membership.isMember(
                    auth.getToken().getSubject(), tenantId)
                .map(AuthorizationDecision::new))
            .defaultIfEmpty(new AuthorizationDecision(false));
    }
}
~~~

Trong ứng dụng thật, tenant ID phải được xác minh theo tenant registry/route policy. Không tin một header do Client gửi như bằng chứng duy nhất về tenant. Đoạn code chỉ minh họa vị trí đặt async check.

Test bằng StepVerifier:

~~~java
@Test
void grantsAccessWhenMembershipExists() {
    when(membership.isMember("user-417", "alpha"))
        .thenReturn(Mono.just(true));

    Mono<AuthorizationDecision> decision =
        authorizationManager.check(
            Mono.just(jwtAuthentication(validJwt())),
            authorizationContext("alpha")
        );

    StepVerifier.create(decision)
        .expectNextMatches(AuthorizationDecision::isGranted)
        .verifyComplete();
}

@Test
void deniesAccessWhenMembershipDoesNotExist() {
    when(membership.isMember("user-417", "alpha"))
        .thenReturn(Mono.just(false));

    StepVerifier.create(checkTenantAccess("alpha"))
        .expectNextMatches(result -> !result.isGranted())
        .verifyComplete();
}
~~~

Các helper **jwtAuthentication** và **authorizationContext** tạo Authentication/AuthorizationContext fixture. Test manager riêng giúp xác nhận quyết định reactive; test security chain ở mục 10 xác nhận nó được nối vào route thực tế.

---

## 5. Kiểm thử JWT authentication converter

### 5.1. Converter có thể đồng bộ hoặc reactive

Trong WebFlux, DSL JWT cần converter có kiểu:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>>
~~~

Một converter hiện hữu của Servlet/imperative stack thường có kiểu:

~~~java
Converter<Jwt, AbstractAuthenticationToken>
~~~

Spring Security cung cấp **ReactiveJwtAuthenticationConverterAdapter** để bọc converter đồng bộ thành reactive converter.

### 5.2. Dùng ReactiveJwtAuthenticationConverterAdapter

Ví dụ cấu hình authority mapping từ claim scope:

~~~java
@Bean
Converter<Jwt, Mono<AbstractAuthenticationToken>>
jwtAuthenticationConverter() {

    JwtGrantedAuthoritiesConverter authoritiesConverter =
        new JwtGrantedAuthoritiesConverter();

    authoritiesConverter.setAuthoritiesClaimName("scope");
    authoritiesConverter.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter delegate =
        new JwtAuthenticationConverter();

    delegate.setJwtGrantedAuthoritiesConverter(authoritiesConverter);

    return new ReactiveJwtAuthenticationConverterAdapter(delegate);
}
~~~

Gắn vào WebFlux Resource Server:

~~~java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        Converter<Jwt, Mono<AbstractAuthenticationToken>> converter) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.jwtAuthenticationConverter(converter))
        )
        .build();
}
~~~

Adapter chỉ bọc kết quả của converter đồng bộ trong Mono. Nó không làm cho việc tra cứu database/HTTP bên trong delegate trở thành non-blocking. Nếu cần tra cứu bất đồng bộ, viết converter trả Mono trực tiếp và dùng reactive client.

### 5.3. Test converter đồng bộ được adapter bọc

~~~java
@Test
void convertsJwtToAuthentication() {
    JwtAuthenticationConverter delegate =
        new JwtAuthenticationConverter();

    Converter<Jwt, Mono<AbstractAuthenticationToken>> converter =
        new ReactiveJwtAuthenticationConverterAdapter(delegate);

    StepVerifier.create(converter.convert(validJwt()))
        .assertNext(authentication -> {
            assertInstanceOf(JwtAuthenticationToken.class, authentication);
            assertEquals("user-417", authentication.getName());
            assertTrue(authentication.getAuthorities().stream()
                .anyMatch(authority ->
                    authority.getAuthority().equals("SCOPE_orders.read")));
        })
        .verifyComplete();
}
~~~

Test này xác nhận adapter phát Authentication và authority mapping đúng. Nó không chứng minh delegate thực hiện I/O bất đồng bộ.

### 5.4. Converter bất đồng bộ để tải authority

Khi roles/permissions nằm trong một service reactive, converter có thể gọi service và trả Mono:

~~~java
public interface RoleDirectory {
    Mono<Collection<GrantedAuthority>> findAuthorities(String subject);
}
~~~

~~~java
public final class DirectoryJwtAuthenticationConverter
        implements Converter<Jwt, Mono<AbstractAuthenticationToken>> {

    private final RoleDirectory directory;

    public DirectoryJwtAuthenticationConverter(RoleDirectory directory) {
        this.directory = directory;
    }

    @Override
    public Mono<AbstractAuthenticationToken> convert(Jwt jwt) {
        return directory.findAuthorities(jwt.getSubject())
            .map(authorities ->
                new JwtAuthenticationToken(jwt, authorities));
    }
}
~~~

Converter này không gọi block() và không tạo list authority giả khi directory lỗi. Nếu directory trả empty, contract của directory cần được định nghĩa rõ; thường nên trả collection rỗng thay vì Mono.empty để converter luôn phát Authentication với tập quyền rỗng.

### 5.5. Test converter thành công

~~~java
@Test
void loadsAuthoritiesAsynchronously() {
    GrantedAuthority read =
        new SimpleGrantedAuthority("SCOPE_orders.read");

    when(roleDirectory.findAuthorities("user-417"))
        .thenReturn(Mono.just(List.of(read)));

    Converter<Jwt, Mono<AbstractAuthenticationToken>> converter =
        new DirectoryJwtAuthenticationConverter(roleDirectory);

    StepVerifier.create(converter.convert(validJwt()))
        .assertNext(authentication -> {
            assertEquals("user-417", authentication.getName());
            assertTrue(authentication.getAuthorities().contains(read));
        })
        .verifyComplete();

    verify(roleDirectory).findAuthorities("user-417");
}
~~~

Vì StepVerifier subscribe, lời gọi đến role directory được kích hoạt. Mockito verify sau khi verifyComplete() hoàn tất giúp xác nhận dependency thực sự được gọi.

### 5.6. Test converter khi dependency lỗi

~~~java
@Test
void propagatesRoleDirectoryFailure() {
    when(roleDirectory.findAuthorities("user-417"))
        .thenReturn(Mono.error(
            new IllegalStateException("role directory unavailable")));

    Converter<Jwt, Mono<AbstractAuthenticationToken>> converter =
        new DirectoryJwtAuthenticationConverter(roleDirectory);

    StepVerifier.create(converter.convert(validJwt()))
        .expectErrorMatches(error ->
            error instanceof IllegalStateException
                && error.getMessage().contains("unavailable"))
        .verify();
}
~~~

Không dùng onErrorResume(error -> Mono.just(authentication)) để cho phép token đi qua khi authority service lỗi. Việc đó có thể biến lỗi dependency thành cấp quyền ngoài ý muốn.

### 5.7. Test converter không được gọi I/O trước subscription

Vì Publisher lazy, test có thể xác nhận dependency chưa được gọi trước khi subscribe:

~~~java
@Test
void roleLookupStartsOnSubscription() {
    when(roleDirectory.findAuthorities("user-417"))
        .thenReturn(Mono.just(List.of()));

    Mono<AbstractAuthenticationToken> result =
        converter.convert(validJwt());

    verifyNoInteractions(roleDirectory);

    StepVerifier.create(result)
        .expectNextCount(1)
        .verifyComplete();

    verify(roleDirectory).findAuthorities("user-417");
}
~~~

Nếu converter gọi service ngay khi method được gọi thay vì trong pipeline, test này sẽ phát hiện eager side effect.

---

## 6. Kiểm thử ReactiveOpaqueTokenIntrospector

### 6.1. Contract của introspector

Với opaque access token, Resource Server không decode JWT cục bộ. Nó gọi introspection endpoint hoặc một token-state store để xác minh token. WebFlux dùng:

~~~java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
~~~

Spring Security cung cấp **SpringReactiveOpaqueTokenIntrospector**. Có thể thay bằng custom implementation hoặc bọc implementation mặc định để map authority, thêm policy hoặc metrics.

Một introspector hợp lệ phát principal khi token được xác nhận. Nếu token inactive hoặc không thể introspect, nó phải phát lỗi phù hợp. Không phát một principal rỗng để biểu diễn token invalid.

### 6.2. Custom introspector bọc delegate

Ví dụ thêm authority mapping từ introspection attributes:

~~~java
public final class CustomOpaqueTokenIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public CustomOpaqueTokenIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .map(principal -> {
                Collection<GrantedAuthority> authorities =
                    extractAuthorities(principal);

                return new DefaultOAuth2AuthenticatedPrincipal(
                    principal.getName(),
                    principal.getAttributes(),
                    authorities
                );
            });
    }

    private Collection<GrantedAuthority> extractAuthorities(
            OAuth2AuthenticatedPrincipal principal) {

        Object scopeValue = principal.getAttribute("scope");

        if (!(scopeValue instanceof String scopes)) {
            return List.of();
        }

        return Arrays.stream(scopes.split(" "))
            .filter(scope -> !scope.isBlank())
            .map(scope -> new SimpleGrantedAuthority("SCOPE_" + scope))
            .toList();
    }
}
~~~

Đoạn code minh họa khi AS trả scope dưới dạng chuỗi phân tách bằng dấu cách. Nếu AS trả list hoặc một claim custom, map theo contract thật. Không tự nâng scope thành role quản trị.

### 6.3. Test introspector trả principal

~~~java
@Test
void introspectsActiveToken() {
    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-417",
            Map.of(
                "active", true,
                "scope", "orders.read"
            ),
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
        );

    when(delegate.introspect("opaque-token"))
        .thenReturn(Mono.just(principal));

    StepVerifier.create(introspector.introspect("opaque-token"))
        .assertNext(result -> {
            assertEquals("user-417", result.getName());
            assertEquals(
                "orders.read",
                result.getAttribute("scope")
            );
            assertTrue(result.getAuthorities().stream()
                .anyMatch(authority ->
                    authority.getAuthority().equals("SCOPE_orders.read")));
        })
        .verifyComplete();

    verify(delegate).introspect("opaque-token");
}
~~~

Test này kiểm tra cả việc gọi delegate và việc giữ lại attributes/authorities.

### 6.4. Test token inactive

Introspection response có **active=false** không phải principal thành công. **SpringReactiveOpaqueTokenIntrospector** sẽ báo lỗi nếu token không active. Với custom introspector, giữ nguyên error từ delegate:

~~~java
@Test
void propagatesInactiveTokenFailure() {
    when(delegate.introspect("revoked-token"))
        .thenReturn(Mono.error(
            new IllegalStateException("token is inactive")));

    StepVerifier.create(introspector.introspect("revoked-token"))
        .expectErrorMatches(error ->
            error.getMessage().contains("inactive"))
        .verify();
}
~~~

Trong test thực tế, dùng exception mà introspector đang triển khai phát ra, chẳng hạn OAuth2IntrospectionException hoặc OAuth2AuthenticationException tùy lớp. Điều quan trọng là không chuyển inactive token thành principal có quyền.

### 6.5. Test introspection timeout

Có thể đặt timeout ở lớp gọi introspector hoặc ở HTTP client theo policy ứng dụng:

~~~java
@Test
void failsWhenIntrospectionDoesNotRespond() {
    Mono<OAuth2AuthenticatedPrincipal> result =
        Mono.<OAuth2AuthenticatedPrincipal>never()
            .timeout(Duration.ofMillis(100));

    StepVerifier.create(result)
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));
}
~~~

Test này kiểm tra semantics timeout của pipeline. Với HTTP introspection thật, nên cấu hình connect/read/response timeout tại WebClient và test bằng mock web server hoặc stub endpoint để xác nhận timeout ở tầng mạng.

### 6.6. Không cache lỗi như token inactive

Có hai loại kết quả cần phân biệt:

- AS trả token inactive: token không được xác thực.
- AS timeout hoặc trả lỗi 5xx: không xác định được trạng thái token vì dependency không sẵn sàng.

Không cache upstream timeout thành active=false lâu dài nếu điều đó che giấu sự cố. Cũng không biến timeout thành active=true. Resource Server cần áp dụng fail-closed cho việc cấp Authentication và trả lỗi theo error handling đã thiết kế.

---

## 7. Kiểm thử lỗi, retry và timeout trong reactive pipeline

### 7.1. Phân loại lỗi

| Lỗi | Lớp thường phát hiện | Hành vi test |
|---|---|---|
| JWT sai chữ ký | ReactiveJwtDecoder | Mono error |
| JWT sai audience | JWT validator trong decoder | Mono error |
| Opaque token inactive | ReactiveOpaqueTokenIntrospector | Mono error |
| Introspection endpoint timeout | WebClient/dependency | Timeout/error |
| Role directory lỗi | Custom converter | Mono error |
| User không thuộc tenant | ReactiveAuthorizationManager | AuthorizationDecision false |
| Thiếu scope | Authorization rule | 403 |
| Request không có token | Security entry point | 401 |

Test nên xác nhận lỗi tại đúng ranh giới. Ví dụ user không thuộc tenant không có nghĩa JWT signature invalid; đó là quyết định authorization.

### 7.2. Kiểm tra retry có chủ đích

Nếu một dependency cho phép retry lỗi transient, test cả số lần gọi và kết quả cuối:

~~~java
@Test
void retriesTransientIntrospectionFailure() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> result = Mono.defer(() -> {
        if (attempts.incrementAndGet() < 3) {
            return Mono.error(new IOException("temporary failure"));
        }
        return Mono.just("active");
    }).retry(2);

    StepVerifier.create(result)
        .expectNext("active")
        .verifyComplete();

    assertEquals(3, attempts.get());
}
~~~

Không retry mọi lỗi. Token invalid, audience mismatch hoặc inactive token là lỗi xác thực; retry không thể sửa được. Retry HTTP introspection cần giới hạn số lần, backoff, timeout và bulkhead để không tạo retry storm.

### 7.3. Virtual time cho delay và timeout

Khi test publisher có delay, không cần dùng Thread.sleep:

~~~java
@Test
void verifiesDelayedResultWithoutWaiting() {
    StepVerifier.withVirtualTime(
            () -> Mono.delay(Duration.ofMinutes(5)))
        .thenAwait(Duration.ofMinutes(5))
        .expectNext(0L)
        .verifyComplete();
}
~~~

Publisher phải được tạo bên trong Supplier truyền cho withVirtualTime, để StepVerifier cài virtual scheduler trước khi pipeline được assemble.

Virtual time chỉ có tác dụng với scheduler hỗ trợ virtual scheduling. Một HTTP request thật hoặc một thư viện dùng scheduler riêng không tự động được tua nhanh.

### 7.4. Test timeout bằng virtual time

~~~java
@Test
void verifiesReactiveTimeout() {
    StepVerifier.withVirtualTime(
            () -> Mono.<String>never()
                .timeout(Duration.ofSeconds(30)))
        .thenAwait(Duration.ofSeconds(30))
        .expectError(TimeoutException.class)
        .verify();
}
~~~

Đây là test timeout operator, không phải test cấu hình timeout của Netty/WebClient. Để test HTTP client, dùng mock server và thời gian thực có giới hạn hợp lý.

### 7.5. Kiểm tra cancellation

Khi Client hủy request hoặc timeout, pipeline nên truyền cancellation về upstream để giải phóng tài nguyên:

~~~java
@Test
void cancelsUpstreamWhenSubscriberCancels() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Mono<String> source = Mono.<String>never()
        .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source)
        .expectSubscription()
        .thenCancel()
        .verify();

    assertTrue(cancelled.get());
}
~~~

Đối với introspection hoặc directory lookup, cancellation có thể giúp dừng công việc không còn cần thiết. Tuy nhiên, cancellation không phải lúc nào cũng hủy được request đã gửi tới hệ thống ngoài; hãy kiểm tra khả năng cancellation của HTTP client và downstream service.

---

## 8. Backpressure, Context và subscription count

### 8.1. Kiểm tra backpressure

Mono chỉ phát tối đa một phần tử, nhưng Flux hoặc publisher nội bộ có thể cần test demand:

~~~java
@Test
void emitsOnlyAfterDemand() {
    StepVerifier.create(Flux.just("one", "two"), 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext("one")
        .thenRequest(1)
        .expectNext("two")
        .verifyComplete();
}
~~~

Với Resource Server, phần lớn decoder/introspector là Mono. Tuy nhiên, converter có thể kết hợp nhiều nguồn reactive; test demand nếu pipeline của bạn xử lý Flux hoặc stream authority.

### 8.2. Kiểm tra Reactor Context

Nếu custom pipeline lấy correlation ID hoặc tenant context từ Reactor Context, có thể khởi tạo context cho StepVerifier:

~~~java
StepVerifier.create(
        service.loadAuthorities("user-417"),
        StepVerifierOptions.create()
            .withInitialContext(Context.of("correlationId", "test-123"))
    )
    .expectAccessibleContext()
    .contains("correlationId", "test-123")
    .then()
    .expectNextCount(1)
    .verifyComplete();
~~~

Không nhầm Reactor Context với Servlet ThreadLocal. Trong reactive flow, không dựa vào việc callback chạy trên cùng một thread. Spring Security lưu SecurityContext trong reactive context; code tùy chỉnh phải giữ nguyên pipeline và không chuyển sang blocking executor tùy tiện.

### 8.3. Kiểm tra số lần introspection

Nếu pipeline có retry, cache hoặc nhiều subscriber, xác nhận số lần gọi dependency:

~~~java
@Test
void introspectsOnceForOneSubscription() {
    AtomicInteger calls = new AtomicInteger();

    ReactiveOpaqueTokenIntrospector introspector =
        token -> Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.just(activePrincipal());
        });

    StepVerifier.create(introspector.introspect("opaque-token"))
        .expectNextCount(1)
        .verifyComplete();

    assertEquals(1, calls.get());
}
~~~

Nếu cùng một Mono được subscribe hai lần, công việc có thể chạy hai lần. Đừng dùng cache() hoặc share() chỉ để làm test pass; hãy quyết định rõ liệu introspection result có được cache hay không và cache có phù hợp với revocation freshness hay không.

### 8.4. Dùng PublisherProbe hoặc TestPublisher khi cần kiểm soát luồng

**PublisherProbe** giúp xác nhận nhánh Publisher có được subscribe hay không. **TestPublisher** cho phép test điều khiển thời điểm phát value/error.

Chúng hữu ích khi custom converter/introspector có nhánh:

- Token đã cache: không gọi AS.
- Token cache miss: gọi introspection.
- User không có tenant membership: không gọi repository dữ liệu.
- Upstream bị hủy: không tiếp tục gọi các dependency sau đó.

Dùng chúng để kiểm tra orchestration. Với chữ ký JWT, claim validation và HTTP behavior, vẫn cần test fixture hoặc integration test thật.

---

## 9. Test WebFlux security chain bằng WebTestClient

### 9.1. Unit test không thay integration test

StepVerifier kiểm tra Publisher độc lập. Nó không chứng minh SecurityWebFilterChain đang nối đúng decoder, converter, introspector và authorization rule.

WebTestClient kiểm tra HTTP request/response qua WebFlux application context. Có thể kết hợp với Spring Security test support để gửi token hoặc mock authentication.

### 9.2. Cấu hình chain JWT

Ví dụ chain:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveJwtDecoder decoder,
        Converter<Jwt, Mono<AbstractAuthenticationToken>> converter) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .decoder(decoder)
                .jwtAuthenticationConverter(converter)
            )
        )
        .build();
}
~~~

### 9.3. Kiểm tra endpoint với mock JWT

Spring Security test có thể cung cấp mock JWT để kiểm tra authorization mapping:

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .subject("user-417")
            .claim("scope", "orders.read")
        )
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Đây là test authorization/route rule. Mock JWT không chạy chữ ký verification, ReactiveJwtDecoder hoặc custom OAuth2TokenValidator. Không dùng test này làm bằng chứng rằng decoder từ chối JWT sai chữ ký.

### 9.4. Kiểm tra decoder thật qua HTTP

Để test end-to-end:

1. Khởi động WebFlux application context.
2. Cấu hình decoder với public key test hoặc JWKS test endpoint.
3. Tạo compact JWT có chữ ký bằng private key test.
4. Gửi token bằng Authorization header.
5. Kiểm tra HTTP status và response body.
6. Gửi token sai audience hoặc chữ ký để xác nhận 401.
7. Gửi token hợp lệ nhưng thiếu scope để xác nhận 403.

Khi test introspection, dùng stub HTTP endpoint trả response active/inactive và kiểm tra Resource Server phản hồi tương ứng. Không cần gọi Authorization Server production trong test.

### 9.5. Kiểm tra converter được gọi trong request flow

Có thể dùng spy/mock dependency mà converter gọi, gửi một request có JWT đã được decoder xác thực và xác nhận dependency được gọi đúng một lần. Điều này chứng minh converter nằm trong pipeline thực tế.

### 9.6. Kiểm tra HTTP status đúng lớp

| Trường hợp | Kết quả HTTP thường mong đợi |
|---|---|
| Không có token trên endpoint cần xác thực | 401 |
| JWT sai chữ ký/issuer/audience/expiry | 401 |
| Opaque token inactive | 401 |
| Introspection dependency lỗi | Theo error mapping; không cấp Authentication |
| JWT hợp lệ nhưng thiếu scope | 403 |
| JWT hợp lệ nhưng tenant policy từ chối | 403 hoặc 404 theo policy |
| JWT hợp lệ và đủ quyền | 2xx |

Nếu introspection timeout, hệ thống có thể phản hồi 503 theo error handling đã thiết kế. Đừng chuyển timeout thành 2xx hoặc một principal mặc định.

---

## 10. Một ví dụ test suite tổng hợp

Bộ test có thể chia theo ranh giới:

~~~text
security/
  AudienceValidatorTests
  ReactiveJwtDecoderTests
  JwtAuthenticationConverterTests
  ReactiveOpaqueTokenIntrospectorTests
  TenantAuthorizationManagerTests
  ResourceServerWebFluxIntegrationTests
~~~

### 10.1. AudienceValidatorTests

- Đúng audience trả success.
- Sai audience trả validation error.
- Thiếu audience trả validation error.
- Token có nhiều audience nhưng không có API cần thiết bị từ chối.

### 10.2. ReactiveJwtDecoderTests

- JWT được ký bằng key tin cậy phát ra Jwt.
- Chữ ký sai phát error.
- Issuer sai phát error.
- Audience sai phát error.
- Token hết hạn phát error.
- JWKS/upstream failure không được biến thành Jwt hợp lệ.

### 10.3. JwtAuthenticationConverterTests

- Subject được map thành Authentication name.
- Scope được map thành authority có prefix phù hợp.
- Claim custom được map đúng.
- Role directory được gọi khi subscribe.
- Role directory lỗi được truyền đi.
- Không có quyền trả Authentication với authority rỗng hoặc bị từ chối theo contract, không tự thêm quyền mặc định.

### 10.4. ReactiveOpaqueTokenIntrospectorTests

- Token active trả principal.
- Attributes được giữ nguyên.
- Scope được map đúng.
- Token inactive phát lỗi.
- HTTP timeout phát lỗi.
- HTTP 5xx không tạo principal.
- Delegate được gọi đúng số lần.
- Không log token hoặc client secret.

### 10.5. TenantAuthorizationManagerTests

- Membership true cho phép.
- Membership false từ chối.
- Membership service timeout không cấp quyền.
- Thiếu Authentication bị từ chối.
- Tenant ID không hợp lệ bị từ chối.
- Context/correlation data được giữ trong reactive chain.

### 10.6. ResourceServerWebFluxIntegrationTests

- Endpoint public truy cập được.
- Endpoint protected không token trả 401.
- JWT hợp lệ đủ scope trả 2xx.
- JWT hợp lệ thiếu scope trả 403.
- JWT sai signature trả 401.
- Opaque token active được chấp nhận.
- Opaque token inactive bị từ chối.
- Dependency outage không làm request được xác thực ngoài ý muốn.

---

## 11. Các lỗi thường gặp khi dùng StepVerifier

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi method rồi không subscribe | Test không chạy pipeline | Dùng StepVerifier hoặc WebTestClient |
| Gọi block() trong test reactive | Che giấu subscription/lỗi execution model | Kiểm tra bằng StepVerifier |
| Dùng StepVerifier trực tiếp với OAuth2TokenValidator | Validator không trả Publisher | Test validate() trực tiếp |
| Cho rằng ReactiveJwtDecoder làm validator thành async | Hiểu sai ranh giới reactive | Validator vẫn sync; decoder phát Mono |
| Mock decoder cho mọi test | Không test chữ ký/claim validation thật | Có decoder integration test bằng key test |
| Dùng mockJwt để test signature | Bỏ qua decoder | Gửi compact JWT ký thật |
| Converter gọi blocking database | Chặn event loop | Dùng reactive repository/client |
| Adapter được coi là tự biến I/O thành non-blocking | Blocking delegate vẫn blocking | Chỉ dùng adapter cho converter sync thuần CPU |
| Introspector trả Mono.empty khi token inactive | Không thể hiện đúng lỗi xác thực | Phát lỗi theo contract introspector |
| Timeout bị đổi thành principal mặc định | Fail-open | Không cấp Authentication khi không xác minh được |
| Retry cả lỗi token invalid | Tốn tải, không sửa token | Chỉ retry lỗi transient đã phân loại |
| Test dùng Thread.sleep | Chậm và flaky | Dùng virtual time khi scheduler hỗ trợ |
| Không đặt verify timeout | Test có thể treo | Dùng verify(Duration) |
| Không test cancellation | Tài nguyên upstream có thể tiếp tục chạy | Dùng thenCancel và kiểm tra doOnCancel |
| Test chỉ một node cho cache phân tán | Bỏ sót race/replay giữa node | Integration test với store chung |
| Mock toàn bộ security chain | Không xác nhận wiring | Bổ sung WebTestClient integration test |

---

## 12. Quy trình viết một StepVerifier test dễ đọc

Khi viết test cho một reactive security component, đi theo các bước:

1. Xác định contract: Mono phát principal, authentication hay lỗi?
2. Tạo fixture nhỏ nhất: Jwt, principal, key pair hoặc stub response.
3. Chuẩn bị dependency mock/fake trước khi tạo Publisher.
4. Tạo Publisher nhưng không subscribe thủ công.
5. Dùng StepVerifier để mô tả value/error/completion/cancellation.
6. Sau verify, kiểm tra interaction count và side effect.
7. Đặt timeout để tránh test treo.
8. Thêm integration test nếu logic phụ thuộc wiring hoặc HTTP boundary.

Một test tốt thường cho thấy cả kết quả và tín hiệu kết thúc:

~~~java
StepVerifier.create(introspector.introspect("opaque-token"))
    .assertNext(principal -> {
        assertEquals("user-417", principal.getName());
        assertTrue(principal.getAuthorities().stream()
            .anyMatch(authority ->
                authority.getAuthority().equals("SCOPE_orders.read")));
    })
    .verifyComplete();
~~~

Đừng dùng expectNextCount(1) nếu nội dung principal là điều quan trọng đối với bảo mật. Kiểm tra claim, subject, scope và authority thực sự được trả về.

---

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao gọi decoder rồi kiểm tra biến Publisher chưa đủ?

**Trả lời:** Reactive Publisher thường lazy. Công việc chỉ bắt đầu khi có subscription; StepVerifier subscribe và quan sát các tín hiệu thực tế.

**Câu 2.** OAuth2TokenValidator có phải reactive API không?

**Trả lời:** Không. validate(Jwt) trả OAuth2TokenValidatorResult đồng bộ. ReactiveJwtDecoder gọi validator trong quá trình tạo Mono<Jwt>.

**Câu 3.** Nên dùng StepVerifier ở đâu khi test JWT validation?

**Trả lời:** Test predicate của validator trực tiếp bằng JUnit; dùng StepVerifier cho ReactiveJwtDecoder.decode() để xác nhận decoder phát Jwt hoặc error.

**Câu 4.** ReactiveJwtAuthenticationConverterAdapter làm gì?

**Trả lời:** Nó bọc Converter<Jwt, AbstractAuthenticationToken> đồng bộ thành Converter<Jwt, Mono<AbstractAuthenticationToken>>. Nó không biến blocking I/O bên trong delegate thành non-blocking.

**Câu 5.** Khi nào nên viết converter trả Mono trực tiếp?

**Trả lời:** Khi mapping Authentication cần gọi reactive service để tải authority, entitlement hoặc thông tin khác.

**Câu 6.** ReactiveOpaqueTokenIntrospector trả gì khi token active?

**Trả lời:** Mono phát OAuth2AuthenticatedPrincipal với attributes và authorities phù hợp.

**Câu 7.** Token inactive nên trả Mono.empty hay Mono.error?

**Trả lời:** Phát lỗi theo contract introspector. Mono.empty không phải cách biểu diễn chuẩn cho token inactive.

**Câu 8.** Làm sao test upstream timeout mà không chờ lâu?

**Trả lời:** Dùng virtual time với publisher/scheduler hỗ trợ virtual scheduling, hoặc test timeout operator trực tiếp. HTTP client thật cần test riêng với mock server.

**Câu 9.** Vì sao không dùng mockJwt để test chữ ký?

**Trả lời:** mockJwt tạo Authentication fixture và bỏ qua quá trình decode/verify chữ ký. Cần compact JWT được ký thật bằng key test.

**Câu 10.** Nếu role directory lỗi, converter có nên trả Authentication mặc định không?

**Trả lời:** Không. Lỗi dependency phải được truyền theo failure policy; không tự cấp quyền khi chưa tải được authority.

**Câu 11.** StepVerifier kiểm tra cancellation bằng cách nào?

**Trả lời:** Dùng expectSubscription(), thenCancel(), verify() và kiểm tra doOnCancel hoặc cleanup của upstream.

**Câu 12.** Vì sao không retry audience mismatch?

**Trả lời:** Đây là lỗi dữ liệu/token policy, không phải lỗi transient của dependency. Retry không thể làm token sai audience trở nên hợp lệ.

**Câu 13.** Test converter đơn lẻ có đủ chứng minh SecurityWebFilterChain dùng converter không?

**Trả lời:** Không. Cần WebTestClient integration test để xác nhận wiring của decoder, converter, filter chain và authorization rule.

**Câu 14.** Có thể đặt blocking Redis call trong OAuth2TokenValidator khi dùng WebFlux không?

**Trả lời:** Không nên. Validator là đồng bộ và có thể chặn thread xử lý. Dùng reactive authorization/authentication pipeline và reactive client.

**Câu 15.** Khi introspection timeout, Resource Server có được chấp nhận token không?

**Trả lời:** Không. Không thể xác minh trạng thái token thì không được cấp Authentication theo kiểu fail-open.

---

## 14. Tài liệu tham khảo chính thức

- [Spring Security — OAuth 2.0 Resource Server JWT for WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder, validation và JWT authentication converter.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token for WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): ReactiveOpaqueTokenIntrospector, SpringReactiveOpaqueTokenIntrospector và custom introspector.
- [Spring Security API — OAuth2TokenValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2TokenValidator.html): contract validate() đồng bộ.
- [Spring Security API — ReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html): decode() trả Mono<Jwt>.
- [Spring Security API — ReactiveJwtAuthenticationConverterAdapter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverterAdapter.html): adapter cho converter đồng bộ.
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html): contract introspection trả Mono principal.
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): expectNext, expectError, thenCancel, verify và virtual time.
- [Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, TestPublisher và PublisherProbe.

API có thể thay đổi giữa các phiên bản. Hãy kiểm tra tài liệu đúng phiên bản Spring Security/Reactor mà build của dự án đang resolve.

## 15. Ghi nhớ

StepVerifier là công cụ kiểm tra hành vi Publisher: subscribe, giá trị phát ra, lỗi, hoàn tất, backpressure và cancellation. Dùng nó ở ranh giới reactive mà ứng dụng thực sự sử dụng.

- **JWT validator:** validate() của OAuth2TokenValidator là đồng bộ; test logic trực tiếp.
- **JWT decoder:** ReactiveJwtDecoder.decode() trả Mono<Jwt>; dùng StepVerifier để kiểm tra decode và lỗi validation.
- **Authentication converter:** dùng ReactiveJwtAuthenticationConverterAdapter cho converter đồng bộ; viết Converter trả Mono khi cần tra cứu reactive thật sự.
- **Opaque introspector:** ReactiveOpaqueTokenIntrospector.introspect() trả Mono principal; test active, inactive, timeout và lỗi upstream.
- **Async policy:** đặt tenant/entitlement lookup trong reactive authorization/authentication pipeline, không block trong validator.
- **Integration:** WebTestClient kiểm tra SecurityWebFilterChain; mockJwt chỉ phù hợp test authorization, không xác minh chữ ký JWT.

Một bài test reactive tốt chứng minh cả kết quả lẫn cách pipeline kết thúc. Không để lỗi upstream biến thành Authentication mặc định, không để converter blocking chạy trên event loop và không dùng mock thay cho kiểm thử chữ ký hoặc wiring cần được xác minh.
