# mockOAuth2Login và OAuth2User

Trong ứng dụng Spring WebFlux sử dụng OAuth 2.0 Login, controller có thể cần biết **người dùng vừa đăng nhập là ai**, provider trả về những thuộc tính nào và principal có đủ quyền để gọi API hay không. Nếu mỗi ca kiểm thử đều phải chuyển hướng đến authorization server, nhập tài khoản rồi trao đổi authorization code để lấy token, bài kiểm thử controller sẽ chậm, dễ phụ thuộc mạng và khó chủ động tạo các tình huống thiếu quyền.

`spring-security-test` cung cấp **`mockOAuth2Login()`** dành cho `WebTestClient`: ta đưa một `OAuth2AuthenticationToken` mô phỏng cùng `OAuth2User` vào ngữ cảnh security của request Reactive. Nhờ đó, có thể kiểm tra `@AuthenticationPrincipal OAuth2User`, attributes, authorities và kết quả HTTP **200/401/403** mà không cần provider thật.

Bài học thuộc chương **OAuth2 Reactive** trong module **SPRING_SECURITY_TESTING**. Module tập trung kiểm chứng xác thực, phân quyền và bảo vệ HTTP trên Servlet/Reactive bằng MockMvc, WebTestClient, `@WithMockUser`, SecurityContext, JWT/OAuth2/OIDC giả lập và các ca được phép hoặc bị từ chối. Ở đây ta đi sâu vào **Reactive OAuth2 Login**, không nhầm `mockOAuth2Login()` với `oauth2Login()` của MockMvc hay với `mockJwt()` của OAuth2 Resource Server.

## 1. Nhìn đúng ba đối tượng: Authentication, OAuth2User và ClientRegistration

Đăng nhập OAuth2 của Spring Security tạo một `OAuth2AuthenticationToken`. Đối tượng này chứa principal kiểu `OAuth2User`, tập `GrantedAuthority` và định danh client registration liên quan đến lần đăng nhập.

| Thành phần | Vai trò trong bài kiểm thử | Ví dụ cần xác minh |
| --- | --- | --- |
| `OAuth2AuthenticationToken` | Đại diện cho người dùng đã được xác thực bằng OAuth2 Login | Đúng kiểu authentication, đúng `authorizedClientRegistrationId` |
| `OAuth2User` | Cung cấp tên người dùng, attributes và authorities | `getName()`, `getAttribute("id")`, `getAuthorities()` |
| `DefaultOAuth2User` | Implementation có thể tạo trực tiếp cho test | Cấu hình `nameAttributeKey`, ví dụ `id` |
| `ClientRegistration` | Metadata của OAuth2 Client ứng với provider | Registration ID `corporate`, `clientId`, authorization/token endpoint |
| `OAuth2AuthorizedClient` | Biểu diễn grant và access/refresh token đã cấp | Không đồng nhất với `OAuth2User`; cần test kho lưu/token riêng |
| `SecurityWebFilterChain` | Kiểm tra request có được phép truy cập endpoint | `authenticated()`, `hasAuthority(...)` |

Ví dụ nhà cung cấp danh tính trả các thuộc tính sau:

```json
{
  "id": "account-42",
  "name": "Lan Nguyen",
  "email": "lan@example.test",
  "department": "sales"
}
```

Ta muốn `OAuth2User.getName()` trả `account-42`, còn `getAttribute("name")` trả `Lan Nguyen`. Hai giá trị **không nhất thiết giống nhau**: trường dùng định danh thường do `nameAttributeKey` hoặc cấu hình provider quyết định, không phải mọi ứng dụng đều dùng email làm tên chính.

Trong Reactive, ngữ cảnh security được truyền theo **Reactor Context** (`ReactiveSecurityContextHolder`), không nên suy đoán rằng `SecurityContextHolder` dựa trên `ThreadLocal` luôn có cùng nội dung tại mọi bước bất đồng bộ.

```mermaid
flowchart TD
    A[WebTestClient tạo request] --> B[mutateWith mockOAuth2Login]
    B --> C[OAuth2AuthenticationToken mô phỏng]
    C --> D[Principal OAuth2User]
    A --> E[SecurityWebFilterChain]
    C --> E
    E --> F{Authenticated và đủ authority?}
    F -->|Không| G[401 hoặc 403 theo nguyên nhân]
    F -->|Có| H[WebFlux Controller]
    D --> I[@AuthenticationPrincipal OAuth2User]
    I --> H
    H --> J[HTTP response]
```

**Phạm vi bảo đảm:** sơ đồ mô tả cách test đưa authentication mô phỏng vào WebFlux để kiểm tra logic bên trong ứng dụng. Nó **không** mô tả luồng Authorization Code thực: chuyển hướng browser, xác nhận `state`, trao đổi code, tải UserInfo hoặc xác minh token do provider ký.

## 2. Dependency và môi trường đúng cho WebTestClient

Để làm theo các ví dụ, cần Java 17+, Spring Boot 3.x, Spring WebFlux, Spring Security, JUnit 5 và module `spring-security-test`. Cấu hình Gradle minh họa:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Các ví dụ chỉ tập trung vào Mock WebFlux, không liên hệ với identity provider thật; đăng nhập OAuth2 production vẫn cần `ClientRegistrationRepository` / `ReactiveClientRegistrationRepository` và cấu hình provider phù hợp. Không sử dụng client secret, access token hoặc tài khoản thật trong fixture.

Lưu ý lựa chọn test runner:

- `@WebFluxTest` tạo một **slice** cho controller và các thành phần WebFlux, phù hợp với kiểm tra binding/HTTP policy; cần import `SecurityWebFilterChain` muốn kiểm tra.
- `@SpringBootTest` với Reactive application context có phạm vi rộng hơn; phù hợp khi cần service, filter và security configuration gần production.
- `WebTestClient.bindToApplicationContext(context)` + `springSecurity()` kiểm tra các web filter trong context mà không cần chạy một HTTP server ngoài.
- `WebTestClient.bindToServer()` gửi HTTP qua mạng; mock configurer **không thể chèn security context vào server từ xa**. Khi test server thật, phải gửi credential/token hoặc cookie hợp lệ.

## 3. Controller Reactive đọc `@AuthenticationPrincipal OAuth2User`

Tạo API mẫu với bốn endpoint: public, profile, một endpoint đọc báo cáo đòi `SCOPE_reports.read` và endpoint chẩn đoán kiểu principal. Endpoint đăng ký client cho phép kiểm chứng `registrationId` trên `OAuth2AuthenticationToken`.

```java
import java.security.Principal;
import java.util.Map;
import java.util.Objects;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
class ReactiveProfileController {

    @GetMapping("/public")
    Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/profile")
    Mono<Map<String, String>> profile(
            @AuthenticationPrincipal OAuth2User user) {
        return Mono.just(Map.of(
            "principalName", user.getName(),
            "id", Objects.toString(user.getAttribute("id"), "(missing)"),
            "displayName",
                Objects.toString(user.getAttribute("name"), "(missing)")
        ));
    }

    @GetMapping("/reports")
    Mono<String> reports(@AuthenticationPrincipal OAuth2User user) {
        return Mono.just("reports-for:" + user.getName());
    }

    @GetMapping("/principal-kind")
    Mono<String> principalKind(
            @AuthenticationPrincipal OAuth2User user) {
        return Mono.just(user == null ? "not-oauth2-user" : "oauth2-user");
    }

    @GetMapping("/registration")
    Mono<String> registration(Principal principal) {
        if (principal instanceof OAuth2AuthenticationToken oauth2) {
            return Mono.just(oauth2.getAuthorizedClientRegistrationId());
        }
        return Mono.just("not-oauth2-login");
    }
}
```

Các endpoint `/profile` và `/reports` **chủ ý** gọi phương thức của `OAuth2User`, nhờ đó ca thành công phải có principal đúng kiểu. Riêng `/principal-kind` được thiết kế không dereference `null` để cho thấy `@WithMockUser` hoặc `mockUser()` khác `mockOAuth2Login()` như thế nào.

Trong ứng dụng thật, cần kiểm tra dữ liệu attributes trước khi sử dụng trong quyết định nghiệp vụ. Không coi `email` có mặt trong attributes là bằng chứng email đã được xác minh.

## 4. SecurityWebFilterChain mẫu cho kịch bản 200, 401 và 403

Để minh họa authorization mà không yêu cầu provider OAuth2 thực, ta dùng một chain test cho API. Chain bảo vệ mọi endpoint trừ `/api/public`, yêu cầu riêng `SCOPE_reports.read` đối với `/api/reports`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveProfileTestSecurity {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(
                    "/api/profile",
                    "/api/principal-kind",
                    "/api/registration"
                ).authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }
}
```

Ở đây `httpBasic()` cung cấp challenge cho request chưa xác thực, nên `GET /api/profile` không có credential thường trả **401 Unauthorized**. Một request có `OAuth2User` hợp lệ nhưng thiếu `SCOPE_reports.read` sẽ bị từ chối **403 Forbidden** tại `/api/reports`. Việc phân biệt status phụ thuộc entry point/handler mà ứng dụng cấu hình; nếu bật `oauth2Login()` trong production, request browser chưa xác thực có thể nhận **302 redirect** thay vì 401.

**Tại sao chain không gọi `oauth2Login()`?** Vì đây là chain **test riêng** để xác minh một authentication đã được giả lập bằng `mockOAuth2Login()`. Nó không cấu hình thật các OAuth2 authorization endpoint, client registration hoặc login callback. Với bài kiểm thử cả OAuth2 login flow, cần thêm `oauth2Login(Customizer.withDefaults())` trong **cấu hình production thích hợp**, registry client và provider thử nghiệm. Không nhầm hai phạm vi này.

## 5. Tạo WebTestClient nền rồi tùy biến cho từng test

Sử dụng `WebTestClient` bind vào reactive application context và áp dụng hỗ trợ test của Spring Security:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(controllers = ReactiveProfileController.class)
@Import(ReactiveProfileTestSecurity.class)
class ReactiveOAuth2LoginTest {

    @Autowired
    ApplicationContext context;

    WebTestClient baseClient;

    @BeforeEach
    void setUp() {
        baseClient = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    // Các @Test ở các mục tiếp theo nằm trong lớp này.
}
```

`apply(springSecurity())` là bước cần thiết khi tự cấu hình client dạng bind-to-application-context để hỗ trợ `mockOAuth2Login()` và các security test configurer khác. Nên giữ `baseClient` **không có danh tính đăng nhập mặc định**, sau đó tạo client riêng theo từng tình huống:

```java
WebTestClient aliceClient =
    baseClient.mutateWith(mockOAuth2Login());
```

`mutateWith(...)` trả về một instance `WebTestClient` đã áp dụng configurer, không cần `build()` lần nữa. Tuy nhiên, không được chỉ gọi `baseClient.mutateWith(...)` rồi bỏ qua giá trị trả về; request gửi bằng `baseClient` vẫn là request của client nền.

## 6. Chủ động tạo OAuth2User thay vì phụ thuộc fixture mặc định

Nếu một controller dùng claim `id`, `name` hay `department`, nên tạo principal có **đúng bộ attributes** và chỉ định `nameAttributeKey`. `DefaultOAuth2User` phù hợp vì không cần liên hệ provider.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;

final class ReactiveOAuth2Fixtures {
    private ReactiveOAuth2Fixtures() {}

    static OAuth2User user(String id, String displayName,
                           boolean canReadReports) {
        List<GrantedAuthority> authorities = new ArrayList<>();
        authorities.add(new SimpleGrantedAuthority("ROLE_USER"));
        if (canReadReports) {
            authorities.add(
                new SimpleGrantedAuthority("SCOPE_reports.read"));
        }

        return new DefaultOAuth2User(
            authorities,
            Map.of(
                "id", id,
                "name", displayName,
                "email", id + "@example.test"
            ),
            "id" // OAuth2User.getName() đọc giá trị của attribute này.
        );
    }
}
```

Giả sử Alice có `id = "alice-42"` và tên hiển thị `"Alice"`:

- `getName()` trả `alice-42`, vì `nameAttributeKey` là `id`.
- `getAttribute("name")` trả `Alice`.
- `getAuthorities()` luôn có `ROLE_USER`, và chỉ có `SCOPE_reports.read` khi `canReadReports = true`.

Tách rõ hai tập dữ liệu:

1. **Attributes** mô tả người dùng: `id`, `name`, `email`. Chúng không tự tạo quyền `SCOPE_reports.read`.
2. **Authorities** dùng cho các rule `hasRole`/`hasAuthority`. Nếu muốn ánh xạ một attribute thành quyền, cần có chính sách converter thích hợp trong ứng dụng, và bài test riêng để kiểm chứng converter đó.

Việc truyền `OAuth2User` tự tạo vào `mockOAuth2Login()` sẽ làm các test rõ ràng hơn và không phụ thuộc những giá trị mặc định của thư viện có thể thay đổi theo phiên bản.

## 7. Kiểm tra @AuthenticationPrincipal thật sự nhận đúng OAuth2User

Thêm vào lớp `ReactiveOAuth2LoginTest` các import và phương thức test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.user.OAuth2User;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;

@Test
void oauth2PrincipalHasExpectedNameAndAttributes() {
    OAuth2User alice =
        ReactiveOAuth2Fixtures.user("alice-42", "Alice", false);

    WebTestClient aliceClient =
        baseClient.mutateWith(mockOAuth2Login().oauth2User(alice));

    aliceClient.get().uri("/api/profile")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.principalName").isEqualTo("alice-42")
        .jsonPath("$.id").isEqualTo("alice-42")
        .jsonPath("$.displayName").isEqualTo("Alice");
}
```

Trong request này, `mockOAuth2Login()` tạo `OAuth2AuthenticationToken` mô phỏng, còn `.oauth2User(alice)` chỉ định principal thực sự mà `@AuthenticationPrincipal OAuth2User` phải nhận. Assertions không chỉ kiểm tra **200** mà còn đối chiếu các giá trị **đọc từ principal trong controller**.

Tránh kiểu test sau:

```java
baseClient.mutateWith(mockOAuth2Login()); // Bỏ qua client trả về.

baseClient.get().uri("/api/profile")
    .exchange()
    .expectStatus().isUnauthorized();
```

Đoạn này vẫn dùng client nền, vì vậy không minh họa quá trình login. Cần thực hiện request bằng **instance trả về** từ `mutateWith`.

## 8. Hai người dùng khác nhau và request ẩn danh không bị lẫn nhau

Đăng nhập của Alice và Bob cần tách biệt trong cùng một lớp test. Tạo mỗi client từ **cùng `baseClient`** thay vì lấy Bob bằng cách mutate client Alice:

```java
@Test
void aliceBobAndAnonymousRequestsStayIndependent() {
    WebTestClient aliceClient = baseClient.mutateWith(
        mockOAuth2Login().oauth2User(
            ReactiveOAuth2Fixtures.user("alice-42", "Alice", false)));

    WebTestClient bobClient = baseClient.mutateWith(
        mockOAuth2Login().oauth2User(
            ReactiveOAuth2Fixtures.user("bob-17", "Bob", false)));

    aliceClient.get().uri("/api/profile")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.principalName").isEqualTo("alice-42");

    bobClient.get().uri("/api/profile")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.principalName").isEqualTo("bob-17");

    // Gọi lại Alice sau Bob để phát hiện rò rỉ danh tính.
    aliceClient.get().uri("/api/profile")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.principalName").isEqualTo("alice-42");

    baseClient.get().uri("/api/profile")
        .exchange()
        .expectStatus().isUnauthorized();

    baseClient.get().uri("/api/public")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("public");
}
```

Kết quả kỳ vọng: Alice luôn là Alice, Bob luôn là Bob, còn client nền không có `Authentication` đã đăng nhập. Cách kiểm tra này phát hiện lỗi **gán nhầm client dùng chung** hoặc vô tình tái sử dụng cùng dữ liệu principal giữa các test.

Kiểm thử trên không tự chứng minh session OAuth2 thật đã được cô lập: `mockOAuth2Login()` cung cấp authentication mô phỏng cho HTTP test. Với yêu cầu bảo mật giữa browser session, cần thêm test riêng cho `WebSession`, cookies và kho `ServerOAuth2AuthorizedClientRepository`.

## 9. Phân quyền: OAuth2User đã xác thực nhưng chưa chắc có quyền

`mockOAuth2Login()` xác lập trạng thái đã đăng nhập cho request. Nó **không có nghĩa** người dùng tự động được truy cập mọi endpoint. Với `GET /api/reports` yêu cầu `SCOPE_reports.read`, hãy viết cả trường hợp được phép lẫn bị từ chối:

```java
@Test
void oauth2UserWithoutReportsAuthorityGets403() {
    WebTestClient viewer = baseClient.mutateWith(
        mockOAuth2Login().oauth2User(
            ReactiveOAuth2Fixtures.user("viewer-1", "Viewer", false)));

    viewer.get().uri("/api/reports")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void oauth2UserWithReportsAuthorityGets200() {
    WebTestClient reporter = baseClient.mutateWith(
        mockOAuth2Login().oauth2User(
            ReactiveOAuth2Fixtures.user("reporter-1", "Reporter", true)));

    reporter.get().uri("/api/reports")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("reports-for:reporter-1");
}

@Test
void anonymousRequestToReportsGets401() {
    baseClient.get().uri("/api/reports")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

Ma trận kết quả:

| Request | Authentication | `SCOPE_reports.read` | Kỳ vọng |
| --- | --- | --- | --- |
| Anonymous | Không có | Không | `401` trong cấu hình HTTP Basic mẫu |
| OAuth2User `viewer-1` | Có | Không | `403` |
| OAuth2User `reporter-1` | Có | Có | `200`, đúng nội dung |

Hai nhánh từ chối kiểm tra hai điều khác nhau: **401** do chưa xác thực; **403** do đã xác thực nhưng không đủ authority. Nếu API dùng OAuth2 Login trong production, anonymous request có thể được redirect đến trang đăng nhập; hãy thay assertion đúng với entry point được cấu hình, tránh rập khuôn status.

### Có thể dùng `.authorities(...)` thay vì tạo principal mới?

Tùy phiên bản `spring-security-test`, mutator `mockOAuth2Login()` hỗ trợ cung cấp authorities trực tiếp, chẳng hạn:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

WebTestClient reporter = baseClient.mutateWith(
    mockOAuth2Login()
        .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")));
```

Đây là cách ngắn gọn để kiểm tra **policy**. Nhưng khi muốn chứng minh mapping attributes hoặc `nameAttributeKey` của provider, nên tạo `DefaultOAuth2User` minh bạch rồi truyền vào `.oauth2User(...)`. Không tự suy diễn từ thuộc tính `department: "sales"` rằng framework đã cấp authority tương ứng.

## 10. Đăng ký client tùy chỉnh và OAuth2AuthenticationToken

Một ứng dụng có thể đăng nhập qua nhiều OAuth2 provider. `ClientRegistration` chứa metadata của provider, trong khi `OAuth2User` chứa danh tính. `mockOAuth2Login()` có thể nhận một registration tùy chỉnh để kiểm tra endpoint có thực sự phân biệt registration hay không.

Factory fixture (chỉ dùng URL và secret minh họa):

```java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;

static ClientRegistration corporateRegistration() {
    return ClientRegistration.withRegistrationId("corporate")
        .clientId("test-corporate-client")
        .clientSecret("test-only-secret")
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .authorizationUri("https://idp.example.test/oauth2/authorize")
        .tokenUri("https://idp.example.test/oauth2/token")
        .userInfoUri("https://idp.example.test/userinfo")
        .userNameAttributeName("id")
        .scope("profile")
        .clientName("Test Corporate IDP")
        .build();
}
```

Ví dụ kiểm thử:

```java
@Test
void oauth2AuthenticationContainsExpectedRegistrationId() {
    WebTestClient corporateClient = baseClient.mutateWith(
        mockOAuth2Login()
            .clientRegistration(corporateRegistration())
            .oauth2User(
                ReactiveOAuth2Fixtures.user("employee-8", "Minh", false)));

    corporateClient.get().uri("/api/registration")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("corporate");
}
```

Ca này xác nhận controller nhận `OAuth2AuthenticationToken` với **registrationId `corporate`** thay vì một principal OAuth2 không có thông tin provider. Tuy vậy, nó không chứng minh callback `/login/oauth2/code/corporate` đã được gọi, provider hợp lệ, access token được cấp hay UserInfo endpoint đã trả dữ liệu.

Với đăng nhập thực từ nhiều issuer/provider, cần xác định rõ khóa định danh người dùng (chẳng hạn kết hợp registration/issuer với subject) và xây kiểm thử ngăn tài khoản khác provider bị gộp nhầm vì trùng email hoặc tên hiển thị.

## 11. `@AuthenticationPrincipal` với `OAuth2User`, `mockUser` và `mockOidcLogin`

Ba loại principal thường bị nhầm trong bài test:

| Công cụ | Kiểu authentication/principal thường được tạo | Mục tiêu chính |
| --- | --- | --- |
| `mockUser("alice")` | `UsernamePasswordAuthenticationToken` / principal kiểu `UserDetails` | Kiểm tra đăng nhập giả lập thông thường, roles |
| `mockOAuth2Login()` | `OAuth2AuthenticationToken` / `OAuth2User` | Kiểm tra OAuth2 Login, attributes, controller binding |
| `mockOidcLogin()` | `OAuth2AuthenticationToken` / `OidcUser` | Kiểm tra OIDC Login, ID Token và OIDC claims |
| `mockJwt()` | JWT authentication của Resource Server / `Jwt` | Kiểm tra bearer JWT của API, scope/roles |

`OidcUser` mở rộng `OAuth2User`, nên endpoint yêu cầu `@AuthenticationPrincipal OAuth2User` có thể nhận một `OidcUser`. Chiều ngược lại không đúng: `DefaultOAuth2User` thuần túy không có `OidcIdToken`.

Kiểm tra sự khác nhau mà **không để controller gây NullPointerException**:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

@Test
void mockUserDoesNotCreateOAuth2User() {
    WebTestClient ordinaryLogin = baseClient.mutateWith(
        mockUser("alice").roles("USER"));

    ordinaryLogin.get().uri("/api/principal-kind")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("not-oauth2-user");
}

@Test
void mockOAuth2LoginProvidesOAuth2User() {
    WebTestClient oauth2Login = baseClient.mutateWith(
        mockOAuth2Login().oauth2User(
            ReactiveOAuth2Fixtures.user("alice-42", "Alice", false)));

    oauth2Login.get().uri("/api/principal-kind")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("oauth2-user");
}
```

Với `@AuthenticationPrincipal`, khi kiểu principal không thể gán cho kiểu tham số, hành vi mặc định là trả `null`. Annotation có `errorOnInvalidType = true` để yêu cầu phát hiện sai kiểu bằng `ClassCastException`. Trong controller thật, không dùng một `NullPointerException` ngẫu nhiên làm cơ chế trả `401`/ `403`; đặt chính sách truy cập ở `SecurityWebFilterChain` hoặc method security, và xử lý kiểu principal một cách có chủ đích.

### Thử thuộc tính qua `.attributes(...)`

Khi không cần tạo `DefaultOAuth2User` riêng, có thể sửa bộ thuộc tính test:

```java
WebTestClient oauth2Client = baseClient.mutateWith(
    mockOAuth2Login().attributes(attributes -> {
        attributes.put("sub", "provider-user-7");
        attributes.put("name", "Huy");
    }));
```

Đây là cách nhanh để kiểm tra nhánh đọc attributes. Nếu controller mong `getName()` từ khóa `id` hoặc một provider dùng `preferred_username`, hãy cung cấp `DefaultOAuth2User` với `nameAttributeKey` đúng thay vì dựa vào fixture mặc định của thư viện.

## 12. Xem OAuth2User trong luồng Reactor mà không dùng ThreadLocal

Với WebFlux, một service cần biết người dùng hiện tại trong chuỗi Reactor có thể lấy context bằng `ReactiveSecurityContextHolder`:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.core.user.OAuth2User;
import reactor.core.publisher.Mono;

Mono<String> currentOauth2UserName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getPrincipal)
        .ofType(OAuth2User.class)
        .map(OAuth2User::getName);
}
```

Ví dụ sẽ phát ra tên nếu principal là `OAuth2User`; với anonymous hoặc principal sai loại, chuỗi có thể hoàn thành mà không phát giá trị. Trong controller, `@AuthenticationPrincipal` thường đơn giản hơn. Khi xử lý ở service Reactive, tránh gọi `SecurityContextHolder.getContext()` như một nguồn tin cậy toàn cục vì subscription có thể chuyển thread và security context nằm trong Reactor Context.

Nếu một nghiệp vụ cần xác thực bổ sung về quyền, hãy kiểm tra authority trong `Authentication` hoặc dùng method security Reactive phù hợp. Việc principal có attribute `department` hay `email` không tự động trở thành quyền trong `GrantedAuthority`.

## 13. Những trường hợp `mockOAuth2Login()` không đủ

Đây là nhóm công cụ **mô phỏng trạng thái sau đăng nhập**, không phải trình giả lập đầy đủ OAuth2 provider:

| Muốn kiểm tra | `mockOAuth2Login()` có đủ không? | Cách bổ sung |
| --- | --- | --- |
| Controller nhận `OAuth2User` đúng kiểu và attribute | **Có** | Custom `DefaultOAuth2User`, assert body |
| `hasAuthority` cho phép hoặc từ chối HTTP | **Có** nếu filter chain đúng | Ca 200/403 với authorities cụ thể |
| Request anonymous bị chặn | **Có** | Dùng client nền không đăng nhập; assert entry point |
| Dữ liệu Alice không lẫn sang Bob trong test | **Có** cho mock principal của từng request | Hai client local, gọi xen kẽ, assert principal |
| OAuth2 Authorization Code, PKCE, `state` | **Không** | Integration test với authorization server thử nghiệm |
| Access token thực, refresh token và lưu authorized client | **Không đủ** | Test `ReactiveOAuth2AuthorizedClientService`/`ServerOAuth2AuthorizedClientRepository` |
| OIDC ID Token, `nonce`, `iss`, `aud` | **Không** | `mockOidcLogin()` cho controller; provider/decoder thật cho xác minh token |
| JWT Resource Server kiểm tra chữ ký và hạn dùng | **Không** | Bearer token ký test và `ReactiveJwtDecoder` thật |
| Session OAuth2 và logout giữa nhiều browser | **Không đủ** | Kiểm thử cookie, `WebSession`, OAuth2 authorized client và logout |

Một test xanh với `mockOAuth2Login()` có thể phát hiện controller truy cập sai attribute hoặc SecurityWebFilterChain phân quyền nhầm. Nhưng nó **không** xác nhận rằng client registration production đã cấu hình đúng redirect URI, provider đã trả về thông tin hợp lệ, hay token thật đã được lưu/refresh.

Trong bài kiểm thử tích hợp luồng login, những điểm khác biệt thường cần mock authorization server thay vì chỉ mock SecurityContext. Đối với API bearer, dùng `mockJwt()`/JWT thật theo mục tiêu; đừng thay bằng `mockOAuth2Login()` vì hai loại `Authentication` có ý nghĩa khác nhau.

## 14. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| `mockOAuth2Login()` không có tác dụng | Gọi `mutateWith` rồi bỏ qua client trả về | Gán `WebTestClient loginClient = baseClient.mutateWith(...)` và dùng instance mới |
| Request vẫn bị `401` | Test không áp dụng security configurer hoặc gửi bằng client nền | Dùng `bindToApplicationContext(...).apply(springSecurity())`, kiểm tra client đang gửi |
| Request nhận `403` thay vì `200` | `OAuth2User` thiếu authority policy yêu cầu | Đối chiếu `hasAuthority("SCOPE_reports.read")` và `getAuthorities()` |
| Controller bị `NullPointerException` | `@AuthenticationPrincipal OAuth2User` nhận principal loại khác | Dùng `mockOAuth2Login()`, hoặc xử lý sai kiểu có chủ đích |
| `getName()` không giống email hoặc display name | `nameAttributeKey` khác tên attribute đang mong đợi | Tạo `DefaultOAuth2User` với đúng khóa tên; assert riêng từng giá trị |
| `registrationId` không đúng | Test dùng registration mặc định | `.clientRegistration(...) ` và assert `OAuth2AuthenticationToken` |
| Test riêng lẻ qua nhưng chạy suite thất bại | Dùng chung client có danh tính, mock state/cookie bị rò rỉ | Lấy client nền sạch trong `@BeforeEach`, tạo client cục bộ theo kịch bản |
| `@WithMockUser` có quyền nhưng không đọc được attributes OAuth2 | `@WithMockUser` không tạo `OAuth2User` | Dùng `mockOAuth2Login()` với principal đúng |
| Test giả lập “xác minh token OAuth2” nhưng không qua provider | Mock configurer đã chèn Authentication | Tách test controller khỏi test Authorization Code/token verification |

### Phân biệt mock client và HTTP client thật

`WebTestClient.bindToServer()` giao tiếp qua HTTP/TCP với server đang chạy. Nó không thể truyền một object `OAuth2User` Java trực tiếp vào `ReactiveSecurityContextHolder` của server từ xa. Với test này, `.mutateWith(mockOAuth2Login())` thích hợp khi client đã bind vào mock WebFlux context; nếu server chạy thật, cần kiểm tra theo giao thức: cookie đăng nhập, HTTP redirect hoặc bearer credential.

## 15. Bài thực hành có ca được phép và bị từ chối

Hãy thêm `GET /api/team` trả về `team` lấy từ OAuth2User attributes và yêu cầu authority `SCOPE_team.read`. Hoàn thành các bước:

1. Tạo `DefaultOAuth2User` của Alice với `id=alice-42`, `name=Alice`, `team=backend`, `ROLE_USER` và `SCOPE_team.read`. Dùng `mockOAuth2Login().oauth2User(alice)` để assert `200` và response `backend`.
2. Tạo Bob với `team=frontend`, chỉ có `ROLE_USER`; assert `403` khi gọi `GET /api/team`.
3. Dùng client nền không đăng nhập; assert request vào `/api/team` bị từ chối (ví dụ `401` với HTTP Basic entry point).
4. Gọi xen kẽ client Alice → Bob → Alice và kiểm tra giá trị đội/response không bị ghi đè hoặc lẫn nhau.
5. Dùng `mockUser("alice")` gọi `/api/principal-kind`, xác nhận không nhận được `OAuth2User`; giải thích khác biệt với `mockOAuth2Login()`.
6. Cấu hình `ClientRegistration` có `registrationId=corporate` rồi assert endpoint `/api/registration` trả `corporate`.
7. Tự xây một test bổ sung chỉ dùng `.with(mockOAuth2Login())` **không phù hợp trong Reactive**: hãy sửa thành `WebTestClient.mutateWith(mockOAuth2Login())`; phân biệt API Servlet MockMvc và WebFlux.

**Tiêu chí hoàn thành:** sử dụng đúng `SecurityMockServerConfigurers.mockOAuth2Login()` trên `WebTestClient`; tạo `OAuth2User` có attributes và authorities rõ ràng; xác minh `@AuthenticationPrincipal`, `OAuth2AuthenticationToken`, 200/401/403; không làm bẩn client nền; và biết được giới hạn giữa **kiểm thử principal sau đăng nhập** với **kiểm thử luồng OAuth2/OIDC thật**.

### Tài liệu tham khảo

- [Spring Security — Reactive OAuth2 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOAuth2Login()`, `mockOidcLogin()`, `mockJwt()` cùng các cách tùy chỉnh user.
- [Spring Security — Reactive WebTestClient Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html): tích hợp `springSecurity()`, `mutateWith(...)` và các security test configurer.
- [Spring Security — OAuth 2.0 Login for Reactive](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): mô hình OAuth2 Login và cấu hình đăng nhập thực.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): các cách bind client vào context hay server và xác minh HTTP response.
