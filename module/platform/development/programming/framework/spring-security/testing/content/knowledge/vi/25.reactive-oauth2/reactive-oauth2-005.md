# ReactiveOpaqueTokenIntrospector với kết quả hoặc lỗi kiểm soát được

## 1. Bài toán: kiểm chứng opaque access token mà không phụ thuộc máy chủ cấp quyền

Trong một ứng dụng **Spring WebFlux OAuth2 Resource Server**, client gửi access token đến API:

```http
GET /api/reports/42 HTTP/1.1
Authorization: Bearer opa-2f5d...random...
```

Token **opaque** chỉ là một chuỗi đại diện cho quyền truy cập; bản thân API không thể giải mã payload như JWT để biết subject, scope hay thời hạn. Resource server thường phải gửi token đến **introspection endpoint** của Authorization Server (theo cơ chế như RFC 7662) và nhận thông tin token có đang hoạt động hay không, thuộc ai và có các quyền gì.

Một ca kiểm thử cần kiểm tra ít nhất ba hành vi:

1. Token hoạt động, có scope `reports:read` → API cho phép đọc báo cáo.
2. Token hoạt động nhưng chỉ có scope `profile` → người gọi đã xác thực, song không có quyền đọc báo cáo.
3. Token không hoạt động, không tồn tại hoặc bị từ chối khi introspect → không tạo authentication hợp lệ.

Còn một nhánh quan trọng: **dịch vụ introspection không phản hồi**. Đây là lỗi hạ tầng, khác về ý nghĩa với token được xác nhận không hợp lệ. Cả hai trường hợp đều không được cho phép truy cập; cách trả mã lỗi cho client phải được thiết kế và kiểm thử rõ ràng.

Bài thuộc chương **OAuth2 Reactive** của module **SPRING_SECURITY_TESTING**, nơi người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế qua `spring-security-test`. Trọng tâm là `ReactiveOpaqueTokenIntrospector`, `Mono`, `WebTestClient`, các trạng thái 401/403/200 và cách tạo kết quả hoặc lỗi **có thể kiểm soát** trong test, đồng thời đối chiếu với `MockMvc`, `@WithMockUser`, `SecurityContext` cùng các helper JWT/OAuth2/OIDC giả lập.

Sau bài học, bạn có thể:

- Giải thích đường đi của bearer opaque token trong Reactive Resource Server.
- Tạo `ReactiveOpaqueTokenIntrospector` giả cho từng token với `Mono.just(...)` và `Mono.error(...)` mà không gọi network.
- Phân biệt `OAuth2AuthenticatedPrincipal`, `GrantedAuthority`, scope và quyền truy cập.
- Chứng minh các nhánh **anonymous 401**, **inactive 401**, **active thiếu scope 403**, **active đủ scope 200** thông qua `WebTestClient`.
- Kiểm tra riêng lỗi introspection endpoint không sẵn sàng bằng `StepVerifier`, không gán nhầm lỗi hạ tầng thành thành công.
- Phân biệt thử nghiệm dùng `mockOpaqueToken()` với thử nghiệm thật sự đi qua `ReactiveOpaqueTokenIntrospector`.

## 2. ReactiveOpaqueTokenIntrospector nằm ở đâu trong chuỗi bảo mật?

Spring Security hỗ trợ `ReactiveOpaqueTokenIntrospector` ở OAuth2 Resource Server WebFlux. Hợp đồng cốt lõi có dạng:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

- **Đầu vào:** chuỗi access token được trích từ header `Authorization: Bearer ...`.
- **Kết quả thành công:** `Mono` phát một `OAuth2AuthenticatedPrincipal` có attributes (thông tin token) và authorities (quyền được cấp).
- **Kết quả lỗi:** `Mono.error(...)` báo không thể chấp nhận token hoặc introspection không thành công.
- **Không có authentication:** request không có bearer credential sẽ không cần gọi introspector; entry point xử lý yêu cầu chưa xác thực.

```mermaid
flowchart TD
    A["HTTP Authorization: Bearer opaque-token"] --> B{"Có bearer token?"}
    B -->|Không| U["401 qua authentication entry point"]
    B -->|Có| C["Reactive bearer authentication"]
    C --> D["ReactiveOpaqueTokenIntrospector.introspect(token)"]
    D -->|Token inactive / không hợp lệ| E["Mono.error: token không hợp lệ"]
    D -->|Dịch vụ introspection lỗi| F["Mono.error: lỗi hạ tầng"]
    D -->|Token active| G["Mono<OAuth2AuthenticatedPrincipal>"]
    E --> U
    F --> X["Authentication thất bại; HTTP mapping theo cấu hình"]
    G --> H["Tạo Authentication với authorities"]
    H --> I{"Có SCOPE_reports:read?"}
    I -->|Không| V["403 Forbidden"]
    I -->|Có| J["Controller: 200 nếu xử lý thành công"]
```

Introspector chỉ trả kết quả về tình trạng token. **Authorization** vẫn được quyết định bởi quy tắc Spring Security, ví dụ `hasAuthority("SCOPE_reports:read")`. Một token có introspection thành công không có nghĩa mọi endpoint đều cho phép truy cập.

### 2.1. Phân biệt các thuật ngữ

| Thuật ngữ | Vai trò |
|---|---|
| Opaque token | Chuỗi bearer không được resource server giải mã nội dung như JWT |
| Token introspection | Trao đổi với Authorization Server hoặc service có thẩm quyền để kiểm tra token |
| `ReactiveOpaqueTokenIntrospector` | Interface Reactive trả một `Mono` của principal hoặc lỗi |
| `OAuth2AuthenticatedPrincipal` | Principal chứa `name`, attributes và authorities của token đã chấp nhận |
| `GrantedAuthority` | Chuỗi quyền mà authorization rule dùng để ra quyết định |
| `BearerTokenAuthentication` | Kiểu authentication biểu diễn opaque bearer token được chấp nhận |
| `WebTestClient` | Công cụ kiểm thử trao đổi HTTP trên WebFlux |
| `mockOpaqueToken()` | Helper test dựng sẵn authentication, **bỏ qua việc gọi introspector** |

Opaque bearer token khác `OAuth2 Login` trong ứng dụng client. OAuth2 Login tạo phiên người dùng qua authorization-code flow; opaque Resource Server xác thực **mỗi request mang bearer token**. Một người dùng OIDC đăng nhập thành công không tự động chứng minh resource server chấp nhận opaque bearer token.

### 2.2. Servlet và Reactive khác nhau ở điểm nào?

| Phần việc | Servlet | Reactive |
|---|---|---|
| Bảo vệ HTTP | `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |
| Introspection | `OpaqueTokenIntrospector` đồng bộ | `ReactiveOpaqueTokenIntrospector` trả `Mono` |
| Test HTTP | `MockMvc` | `WebTestClient` |
| Authentication context | Servlet `SecurityContextHolder` theo filter/thread | Reactive SecurityContext gắn với Reactor context |
| Helper opaque token | `opaqueToken()` trong MockMvc tests | `mockOpaqueToken()` với WebTestClient mock-context |

Không sử dụng `OpaqueTokenIntrospector` đồng bộ trực tiếp trong test dành cho Reactive chỉ vì hai interface có tên gần giống. Nếu một thư viện introspection bắt buộc blocking, cần tích hợp đúng cách với reactive runtime; không gọi `block()` trong event-loop request handler.

## 3. Hai loại lỗi bắt buộc phân biệt

### 3.1. Token không hợp lệ hoặc không hoạt động

Theo introspection response chuẩn, Authorization Server có thể trả `active: false` cho token không tồn tại, hết hạn hoặc đã bị thu hồi. Introspector chuẩn phải biến kết quả không được chấp nhận thành một **authentication failure**, không trả principal đã xác thực.

Với stub, có thể thể hiện trực tiếp:

```java
return Mono.error(
    new BadOpaqueTokenException("inactive or unknown token")
);
```

`BadOpaqueTokenException` thuộc nhóm lỗi introspection của Spring Security. Trong cấu hình Resource Server bearer thông thường, token bị từ chối dẫn đến **401 Unauthorized**; không nên chuyển thành 403 vì người gọi chưa được xác thực.

### 3.2. Lỗi hạ tầng introspection

Khi introspection service bị timeout, lỗi mạng, trả response sai định dạng hoặc trả lỗi máy chủ, client chưa có bằng chứng token hợp lệ. Một stub có thể biểu diễn:

```java
return Mono.error(
    new OAuth2IntrospectionException(
        "Introspection service is unavailable")
);
```

Đây là một **lỗi kiểm soát được trong test**, không có nghĩa mọi ứng dụng mặc định trả 503. Phản hồi HTTP của lỗi hạ tầng còn phụ thuộc phiên bản Spring Security, exception translation và handler đã cấu hình. Một số cấu hình có thể biểu diễn lỗi này như lỗi bearer authentication; số khác có thể đưa vào nhánh server error. **Không cố định 503, 500 hay 401 nếu chưa định nghĩa và thực thi contract lỗi của ứng dụng.**

Điều chắc chắn cần kiểm chứng: **không được cấp quyền** chỉ vì dịch vụ kiểm tra token lỗi. Tuyệt đối tránh fallback kiểu “service introspection không gọi được nên coi token là hợp lệ”.

### 3.3. Một lỗi không phải “token inactive”: thiếu authority

Khi introspector trả về một principal hợp lệ nhưng không có `SCOPE_reports:read`, authentication có thể thành công. Chỉ sau đó authorization rule mới trả **403 Forbidden**. Nếu test active token thiếu scope lại nhận 401, hãy kiểm tra introspector có vô tình trả lỗi hoặc token không được map thành authentication hay không.

## 4. Dependency và cấu hình SecurityWebFilterChain

Ứng dụng mẫu dùng Java 17+, Spring Boot 3 và Spring Security 6. Với các phiên bản khác, chọn dependency và API cấu hình tương thích.

```kotlin
// build.gradle.kts
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}
```

Ví dụ security chain cho hai endpoint `GET /api/me` và `GET /api/reports/42`:

```java
@Configuration
@EnableWebFluxSecurity
class OpaqueSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports:read")
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque -> opaque
                    .introspector(introspector)))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }
}
```

Những loại quan trọng thuộc các package: `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, `org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector` và `org.springframework.http.HttpMethod`.

- `oauth2ResourceServer().opaqueToken(...)` kích hoạt xác thực bearer opaque token.
- `introspector(introspector)` đảm bảo filter chain sử dụng **bean đã chủ động truyền vào**, phù hợp khi test muốn thay dịch vụ thật bằng stub.
- `hasAuthority("SCOPE_reports:read")` kiểm tra authority đã được đưa vào authentication.
- Tắt form login và HTTP Basic trong ví dụ API giúp anonymous sử dụng bearer entry point.
- `csrf(...disable)` chỉ thích hợp trong ví dụ API stateless xác thực qua bearer header, không phải lời khuyên tắt CSRF trong mọi ứng dụng dùng cookie hoặc browser session.

Không cần nối mạng tới Authorization Server để kiểm tra phản hồi HTTP ở ví dụ này, vì bean introspector test sẽ quyết định kết quả ngay trong tiến trình.

## 5. Tạo introspector test với kết quả và lỗi có thể chọn chính xác

Giả sử bốn chuỗi token thử nghiệm có ý nghĩa:

| Token gửi qua HTTP | Ý nghĩa trong fixture | Kết quả test |
|---|---|---|
| `active-reader` | Token active của Alice, có scope đọc báo cáo | Introspector trả principal có `SCOPE_reports:read` |
| `active-profile` | Token active của Bob, chỉ có scope profile | Introspector trả principal có `SCOPE_profile` |
| `inactive` | Token không còn được chấp nhận | Introspector phát `BadOpaqueTokenException` |
| `service-down` | Introspection service giả lập không sẵn sàng | Introspector phát `OAuth2IntrospectionException` |

Đây là **giá trị thử nghiệm có thể dự đoán**; production token không nên chứa tên quyền công khai thay cho chuỗi opaque ngẫu nhiên.

### 5.1. Factory dựng principal với attributes và authorities

```java
static OAuth2AuthenticatedPrincipal principal(
        String subject, String scope) {

    Collection<GrantedAuthority> authorities = List.of(
        new SimpleGrantedAuthority("SCOPE_" + scope)
    );

    Map<String, Object> attributes = Map.of(
        "sub", subject,
        "active", true,
        "scope", scope,
        "client_id", "test-client"
    );

    return new DefaultOAuth2AuthenticatedPrincipal(
        subject,
        attributes,
        authorities
    );
}
```

Các import chính:

```java
import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
```

`DefaultOAuth2AuthenticatedPrincipal` cho phép chọn `name`, attributes và authorities minh bạch. Với `principal("alice", "reports:read")`, token được mô phỏng có attribute `scope=reports:read` và authority `SCOPE_reports:read`. Với `principal("bob", "profile")`, authentication chỉ có `SCOPE_profile`.

**Phân biệt claim và quyền:** riêng việc trả attribute `scope` chưa chứng minh converter của ứng dụng đã dựng đúng authorities. Trong fixture này chúng ta **tự dựng authorities** để tập trung kiểm tra authorization rule. Nếu muốn kiểm thử ánh xạ scope của introspector thật, cần test riêng converter hoặc đường đi introspection network theo cấu hình thực tế.

### 5.2. Bean introspector quyết định bằng chuỗi token

```java
@TestConfiguration
class ControlledIntrospectionConfig {

    @Bean
    @Primary
    ReactiveOpaqueTokenIntrospector introspector() {
        return token -> switch (token) {
            case "active-reader" ->
                Mono.just(principal("alice", "reports:read"));

            case "active-profile" ->
                Mono.just(principal("bob", "profile"));

            case "inactive" ->
                Mono.error(new BadOpaqueTokenException(
                    "Token is inactive"));

            case "service-down" ->
                Mono.error(new OAuth2IntrospectionException(
                    "Introspection service unavailable"));

            default ->
                Mono.error(new BadOpaqueTokenException(
                    "Unknown token"));
        };
    }

    // Đặt phương thức principal(...) của mục 5.1
    // trong class này hoặc một class fixture dùng chung.
}
```

Import liên quan:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
```

Đây là **test bean**, không được tự động đưa vào production profile. `@Primary` giúp lựa chọn bean ưu tiên khi có nhiều candidate, nhưng nếu filter chain thật đã cấu hình một introspector cụ thể bên trong builder, cần xác minh test đã sử dụng bean nào. Ở cấu hình mục 4, introspector được truyền trực tiếp vào `opaque.introspector(...)` nên đường đi rõ ràng.

Lưu ý API `Mono`: return `Mono.just(principal)` khi chấp nhận token; return `Mono.error(exception)` khi cần từ chối. **Không gọi `subscribe()` hoặc `block()` trong `introspect`** để lấy kết quả trước khi trả; như vậy có thể làm hỏng mô hình non-blocking và cơ chế truyền lỗi qua pipeline.

### 5.3. Những điều stub có chủ đích không kiểm tra

Fixture này không tạo request mạng. Nó không tự chứng minh:

- URL introspection endpoint, HTTP Basic client credentials hoặc client authentication thật đã cấu hình đúng.
- Introspection response `active` của nhà cung cấp được parse/chuyển đổi chính xác.
- Token bị thu hồi ở máy chủ thật, thời hạn `exp` hay cache introspection hoạt động đúng.
- Timeout, retry, circuit breaker và response mapping của HTTP client thật hoạt động đúng.
- Nhà cung cấp từ chối token không thuộc audience/resource được cấp phép.

Những phần đó cần một integration test có HTTP server giả lập hoặc một môi trường thử nghiệm riêng cho Authorization Server.

## 6. Test HTTP bằng WebTestClient: 401, 403 và 200

Khi `WebTestClient` được kết nối với ứng dụng WebFlux qua mock application context, request có header Bearer sẽ đi qua **bộ lọc xác thực opaque thực**, rồi gọi bean introspector test. Đây là điều quan trọng: **test không dùng `mutateWith(mockOpaqueToken())` ở những phép thử này**.

Một controller tối giản:

```java
@RestController
class DemoResourceController {

    @GetMapping("/api/me")
    Mono<String> me(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(principal.getName());
    }

    @GetMapping("/api/reports/42")
    Mono<String> report() {
        return Mono.just("report-42");
    }
}
```

Với security chain và `ControlledIntrospectionConfig` được nạp trong Spring test context, viết:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
@Import(ControlledIntrospectionConfig.class)
class OpaqueTokenHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void noBearerTokenIsUnauthorized() {
        client.get()
            .uri("/api/reports/42")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void inactiveTokenIsUnauthorized() {
        client.get()
            .uri("/api/reports/42")
            .headers(h -> h.setBearerAuth("inactive"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownTokenIsUnauthorized() {
        client.get()
            .uri("/api/reports/42")
            .headers(h -> h.setBearerAuth("not-in-fixture"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validTokenWithWrongScopeIsForbidden() {
        client.get()
            .uri("/api/reports/42")
            .headers(h -> h.setBearerAuth("active-profile"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validTokenWithRequiredScopeIsAllowed() {
        client.get()
            .uri("/api/reports/42")
            .headers(h -> h.setBearerAuth("active-reader"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("report-42");
    }

    @Test
    void introspectedPrincipalNameIsAvailable() {
        client.get()
            .uri("/api/me")
            .headers(h -> h.setBearerAuth("active-reader"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("alice");
    }
}
```

Các import đặc trưng: `@SpringBootTest`, `@AutoConfigureWebTestClient`, `@Import`, `@Autowired`, `@Test` và `WebTestClient`. Cần có ứng dụng WebFlux test thực sự nạp `OpaqueSecurityConfig` và `DemoResourceController`; có thể định nghĩa chúng trong test configuration hoặc import chính xác. Nếu project đồng thời có Spring MVC, xác nhận test context đang chạy ở **Reactive application type**.

### 6.1. Điều mà từng assertion thực sự chứng minh

| Kịch bản | Introspector có được gọi? | Authentication | Authorization | Kết quả |
|---|---|---|---|---|
| Không gửi Bearer token | Không | Không có | Không đánh giá như authenticated user | 401 |
| Token `inactive` | Có | Thất bại vì BadOpaqueTokenException | Chưa đủ điều kiện | 401 |
| Token `active-profile` | Có | Thành công với Bob | Thiếu `SCOPE_reports:read` | 403 |
| Token `active-reader` | Có | Thành công với Alice | Có authority bắt buộc | 200 |
| Token `active-reader` ở `/api/me` | Có | Thành công với Alice | Chỉ cần authenticated | 200, trả Alice |

Những kỳ vọng này áp dụng cho **cấu hình Resource Server Bearer mặc định không có handler tùy biến** và endpoint mẫu. Nếu có custom authentication entry point hoặc error handler, phải so sánh theo contract HTTP của ứng dụng.

Khi thiếu quyền nhưng introspection thành công, kỳ vọng **403**, không phải 401. Nếu test thiếu scope lại cho 200, kiểm tra rule đang dùng `authenticated()` thay vì `hasAuthority(...)` hoặc stub vô tình trả thừa quyền.

### 6.2. Kiểm tra WWW-Authenticate khi cần

Một Resource Server theo bearer protocol thường trả header `WWW-Authenticate` khi từ chối token. Ta có thể bổ sung:

```java
client.get()
    .uri("/api/reports/42")
    .headers(h -> h.setBearerAuth("inactive"))
    .exchange()
    .expectStatus().isUnauthorized()
    .expectHeader()
    .valueMatches("WWW-Authenticate", "Bearer.*");
```

Không nên assert nguyên văn `error_description` nếu ứng dụng chưa có contract rõ ràng: nội dung có thể thay đổi theo phiên bản Spring Security, và việc lộ chi tiết introspection qua response là không cần thiết. Với server đã tùy biến header, chọn assertion theo chính sách dự án.

## 7. Test lỗi hạ tầng bằng StepVerifier để xác định nguyên nhân chính xác

Lỗi token bị từ chối và lỗi server introspection không sẵn sàng là hai tình huống khác nhau trong fixture. Thay vì gán một status HTTP đoán trước cho `service-down`, ta test trực tiếp hợp đồng của `ReactiveOpaqueTokenIntrospector`:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@Import(ControlledIntrospectionConfig.class)
class IntrospectorSignalTest {

    @Autowired
    ReactiveOpaqueTokenIntrospector introspector;

    @Test
    void activeTokenEmitsPrincipalThenCompletes() {
        StepVerifier.create(introspector.introspect("active-reader"))
            .assertNext(principal -> {
                assertThat(principal.getName()).isEqualTo("alice");
                assertThat(principal.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .contains("SCOPE_reports:read");
            })
            .verifyComplete();
    }

    @Test
    void inactiveTokenEmitsInvalidTokenError() {
        StepVerifier.create(introspector.introspect("inactive"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void providerOutageEmitsInfrastructureError() {
        StepVerifier.create(introspector.introspect("service-down"))
            .expectError(OAuth2IntrospectionException.class)
            .verify();
    }
}
```

Import: `reactor.test.StepVerifier`, `org.assertj.core.api.Assertions.assertThat` và các kiểu `GrantedAuthority`/exception tương ứng. Trường hợp có nhiều `ApplicationContext`, phải đảm bảo test nạp đúng bean introspector.

**Giới hạn của phép thử trên:** nó kiểm tra signal `onNext/onComplete/onError` từ stub, chưa chứng minh cơ chế HTTP chuyển **lỗi hạ tầng** thành status cụ thể. Nếu sản phẩm yêu cầu “introspection service down → 503 Service Unavailable”, hãy thiết kế đường xử lý lỗi riêng có thể quan sát được (ví dụ authentication error mapping/handler có chủ đích), sau đó viết một phép thử WebTestClient xác nhận **503 và không được gọi controller**. Không khẳng định mặc định Spring Security sẽ tự trả 503 khi nhận mọi `OAuth2IntrospectionException`.

### 7.1. Vì sao không dùng onErrorResume để cho qua?

Một implementation nguy hiểm:

```java
// Không dùng: lỗi introspection lại cấp quyền cho request.
return remoteIntrospector.introspect(token)
    .onErrorResume(error ->
        Mono.just(principal("anonymous", "reports:read"))
    );
```

Đoạn code minh họa **anti-pattern fail-open**: mất khả năng xác minh token nhưng vẫn dựng principal có quyền. Hành vi an toàn là **fail closed**: nếu không xác minh được, không tạo authentication hợp lệ. Có thể áp dụng giới hạn thời gian, chính sách retry có kiểm soát, circuit breaker và observability; các biện pháp đó không được tự chuyển lỗi thành quyền truy cập.

### 7.2. Timeout và lỗi mạng phải được kiểm tra riêng

Khi dùng introspector HTTP thật, nên tách các trường hợp:

| Tình huống | Điều cần kiểm tra |
|---|---|
| Response 200, `active: true`, scope hợp lệ | Principal được tạo, mapping authority đúng |
| Response 200, `active: false` | Token bị từ chối; không có authentication |
| HTTP 401/403 từ introspection endpoint | Phân tích lỗi client credentials/cấu hình; không coi token đã được xác minh |
| HTTP 5xx hoặc mất kết nối | Không cho phép truy cập; retry/timeout đúng chính sách |
| Response thiếu field bắt buộc hoặc sai kiểu | Không cấp quyền từ dữ liệu không hợp lệ |
| Introspection endpoint rất chậm | Request bị giới hạn thời gian, không treo vô hạn |
| Token đúng nhưng không đủ scope | Authentication thành công; authorization từ chối |

Không quy kết mọi lỗi HTTP 401 từ introspection endpoint là “access token của người dùng sai”: bản thân client credential dùng để gọi introspection endpoint cũng có thể không hợp lệ. Test hạ tầng và log/metrics cần phân biệt nguyên nhân, trong khi kết quả truy cập tài nguyên phải vẫn an toàn.

## 8. Stub bằng Mockito: kiểm tra chính xác tham số và nhánh trả về

Một cách khác là mock interface bằng Mockito. Khi chỉ cần test class sử dụng introspector, có thể stub method mà không tạo bean cố định:

```java
@Test
void stubIntrospectionResultsAndErrors() {
    ReactiveOpaqueTokenIntrospector introspector =
        Mockito.mock(ReactiveOpaqueTokenIntrospector.class);

    OAuth2AuthenticatedPrincipal alice =
        principal("alice", "reports:read");

    Mockito.when(introspector.introspect("active-reader"))
        .thenReturn(Mono.just(alice));

    Mockito.when(introspector.introspect("inactive"))
        .thenReturn(Mono.error(
            new BadOpaqueTokenException("inactive")));

    Mockito.when(introspector.introspect("service-down"))
        .thenReturn(Mono.error(
            new OAuth2IntrospectionException("unavailable")));

    StepVerifier.create(introspector.introspect("active-reader"))
        .expectNext(alice)
        .verifyComplete();

    StepVerifier.create(introspector.introspect("inactive"))
        .expectError(BadOpaqueTokenException.class)
        .verify();

    StepVerifier.create(introspector.introspect("service-down"))
        .expectError(OAuth2IntrospectionException.class)
        .verify();

    Mockito.verify(introspector)
        .introspect("active-reader");
}
```

Đoạn này giả định phương thức `principal(...)` từ mục 5.1 được đặt trong test class hoặc fixture helper. `Mockito` thuộc `org.mockito.Mockito`, thường có sẵn trong `spring-boot-starter-test`.

Nếu test HTTP cần dùng Mockito, **mock phải là bean introspector mà `SecurityWebFilterChain` thật sự tham chiếu**. Có thể thay bean qua cơ chế bean override của phiên bản Spring Test/Spring Boot đang dùng (chẳng hạn `@MockitoBean` ở hệ thư viện mới) và stub trong `@BeforeEach`. Những API override bean thay đổi theo phiên bản; ở bài này `@TestConfiguration` với bean xác định trước giúp dễ đọc và ít lệ thuộc annotation version hơn.

**Không kết luận “đã test introspection qua HTTP” chỉ vì Mockito trả đúng Mono.** Test tương tác HTTP còn phải gửi header Bearer qua `WebTestClient` và quan sát filter chain.

## 9. mockOpaqueToken() có ích nhưng bỏ qua introspector

`spring-security-test` còn hỗ trợ `SecurityMockServerConfigurers.mockOpaqueToken()` khi test WebFlux gắn với mock application context. Helper này tạo authentication của opaque token ngay trong test exchange:

```java
client
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("scope", "reports:read");
        })
        .authorities(
            new SimpleGrantedAuthority("SCOPE_reports:read")))
    .get()
    .uri("/api/reports/42")
    .exchange()
    .expectStatus().isOk();
```

Đoạn trên phù hợp để test **authorization khi đã có principal**, nhanh và không cần cấu hình introspection network. Tuy nhiên, **`ReactiveOpaqueTokenIntrospector.introspect(...)` không phải là phần được kiểm thử ở đây**: test không đọc bearer token từ header để gửi cho introspector.

So sánh:

| Phương pháp | Có chạy bearer filter/introspector? | Dùng khi nào? |
|---|---|---|
| `mutateWith(mockOpaqueToken())` | Không kiểm tra introspector | Test controller/authorization với opaque authentication dựng sẵn |
| `headers.setBearerAuth("active-reader")` + stub bean | **Có**, gọi introspector stub | Test đường đi HTTP, lỗi/cho phép dựa trên kết quả introspector kiểm soát được |
| `headers.setBearerAuth(token)` + HTTP introspector thật | Có và có network introspection | Kiểm tra URL, credentials, response parser, timeout, cache, mapping thật |
| `mutateWith(mockJwt())` | Không kiểm tra opaque introspection | Test rule khi đã có JWT authentication |
| `mutateWith(mockUser())` / `@WithMockUser` | Không có opaque token | Test authorization theo role với user giả lập |
| `mutateWith(mockOAuth2Login()/mockOidcLogin())` | Không có opaque token | Test logic sau OAuth2/OIDC login |

Để biết test đã chạy introspector hay chưa, có thể thêm spy/counter ở bean test, hoặc kiểm tra một token đặc biệt `inactive` làm HTTP trả 401 như ví dụ. Điều quan trọng là assertion phải đi qua **header Bearer và security filter chain**, thay vì chỉ dựng authentication có sẵn.

## 10. Điều gì thay đổi khi chạy WebTestClient qua cổng HTTP thật?

Cần phân biệt hai kiểu client:

- **Mock WebFlux exchange:** `WebTestClient.bindToApplicationContext(context).apply(springSecurity()).build()` hoặc WebTestClient tương ứng trong Spring Boot test context. Helper `mockOpaqueToken()`/`mockJwt()` có thể đưa security context vào server exchange giả lập.
- **Live HTTP server:** `WebTestClient.bindToServer()` hoặc `@SpringBootTest(webEnvironment = RANDOM_PORT)`. Client gửi HTTP qua mạng đến server; mock authentication nằm trong JVM test **không tự đi theo request**.

Đối với live HTTP server, cách phù hợp để kiểm thử opaque token là gửi `Authorization: Bearer ...`. Khi introspector test bean được nạp trong server test context, server có thể dùng nó để trả kết quả xác thực kiểm soát được. Với live environment có introspection thật, cần cấu hình Authorization Server giả lập hoặc endpoint test có kiểm soát.

```java
// Hoạt động cho cả client mock-context và client live HTTP,
// miễn là server dùng introspector hỗ trợ token fixture.
client.get()
    .uri("/api/reports/42")
    .headers(headers -> headers.setBearerAuth("active-reader"))
    .exchange()
    .expectStatus().isOk();
```

Không dùng `mutateWith(mockOpaqueToken())` để tuyên bố đã kiểm thử đường truyền mạng ở `RANDOM_PORT`. Client mutation dạng mock không phải bearer credential được tự động truyền qua TCP.

## 11. Các lỗi hay gặp và hướng chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm chứng/sửa |
|---|---|---|
| Active token vẫn trả 401 | Stub không được dùng, token trích sai, principal creation lỗi | Kiểm tra bean được filter chain tham chiếu và header Bearer |
| Token có scope nhưng HTTP trả 403 | Principal thiếu `SCOPE_reports:read` trong authorities | Kiểm tra authority mapping, không chỉ attributes |
| Token inactive lại trả 200 | Test dùng `mockOpaqueToken()` hoặc stub vô tình trả principal | Gửi header Bearer; trả `BadOpaqueTokenException` cho inactive |
| Introspection service lỗi mà request vẫn 200 | Có fallback cấp quyền khi lỗi | Loại bỏ fail-open, giữ lỗi trong reactive chain |
| Anonymous trả 302 thay vì 401 | Form/OAuth2 login entry point đã được bật | Test theo chain thực hoặc dùng bearer-only chain cho API |
| HTTP 503 được kỳ vọng nhưng lại 401/500 | Chưa cấu hình chính sách map lỗi hạ tầng | Định nghĩa riêng error mapping/handler và kiểm tra lại |
| Request bị treo trong test | Introspector trả `Mono.never()` hoặc không có timeout | Giới hạn thời gian thực hiện và test timeout |
| Test dùng `@WithMockUser` PASS nhưng token thật fail | Mock bypass introspector | Bổ sung test bearer header và fixture introspector |
| Reactor context bị mất ở code tùy biến | Dùng blocking/thread-local hoặc thao tác async không đúng | Giữ reactive pipeline và Spring Security context |
| Nhiều test phụ thuộc thứ tự chạy | Stub Mockito chung chưa reset, bean test chứa trạng thái mutable | Tạo fixture stateless hoặc reset mock theo từng ca |
| 401 bị nhầm với 403 | Không phân biệt authentication và authorization | Kiểm tra signal introspection, authorities và rule |

Đặc biệt, không log giá trị opaque access token, `Authorization` header, client secret hoặc thông tin nhạy cảm của principal trong production. Nếu cần theo dõi, ghi mã lỗi chuẩn hóa, thời gian phản hồi và metadata an toàn; có thể dùng correlation ID không chứa bearer credential.

## 12. Ma trận thực hành: mô phỏng các kết quả introspection

Xây dựng API `GET /api/reports/42` yêu cầu `SCOPE_reports:read` và `GET /api/me` chỉ cần xác thực. Dùng bean `ReactiveOpaqueTokenIntrospector` của mục 5, sau đó hoàn thiện:

1. **Anonymous:** GET `/api/reports/42` không có bearer token → 401.
2. **Token inactive:** header Bearer `inactive` → `BadOpaqueTokenException` → 401.
3. **Token không được fixture biết:** header Bearer `random` → lỗi invalid token → 401.
4. **Đủ quyền:** header Bearer `active-reader` → 200, body `report-42`.
5. **Thiếu quyền:** header Bearer `active-profile` → 403.
6. **Principal đúng:** header Bearer `active-reader` tới `/api/me` → 200, body `alice`.
7. **Dịch vụ introspection lỗi:** gọi trực tiếp `introspect("service-down")` → `StepVerifier` nhận `OAuth2IntrospectionException`; không phát principal.
8. **Nhiều client/tokens:** test đồng thời các request có token khác nhau, fixture stateless để không lẫn identity.
9. **Đối chứng mock:** dùng `mockOpaqueToken()` với scope đọc → 200; giải thích vì sao phép thử này không kiểm tra introspector.
10. **HTTP introspection thật:** dựng fake Authorization Server trả `active=true/false`, lỗi HTTP và timeout; xác minh từng response được map đúng, đồng thời kiểm tra quyền được gán theo scope.

**Tiêu chí hoàn thành:** Bộ test phải kiểm tra được **Mono thành công có principal và authorities cụ thể**, **Mono lỗi token không hợp lệ**, **Mono lỗi hạ tầng**, và các phản hồi HTTP **401/403/200** của filter chain WebFlux dùng bearer header. Bạn cần chỉ ra rằng `ReactiveOpaqueTokenIntrospector` quyết định **authentication**, còn `SecurityWebFilterChain` quyết định **authorization**, và một `mockOpaqueToken()` chỉ phục vụ test logic sau khi đã có authentication. Việc introspection service không sẵn sàng phải luôn dẫn đến **không cấp quyền truy cập**, dù ứng dụng chọn chính sách HTTP error riêng.
