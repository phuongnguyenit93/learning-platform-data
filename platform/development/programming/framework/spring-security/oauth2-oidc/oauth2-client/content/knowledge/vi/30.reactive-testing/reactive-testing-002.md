# 30.2. mockOAuth2Login() cho endpoint yêu cầu người dùng OAuth 2.0

## 1. Bối cảnh: kiểm thử endpoint WebFlux mà không cần đăng nhập IdP thật

Giả sử **Employee Portal** được viết bằng **Spring Boot 3, Spring WebFlux và Spring Security OAuth 2.0 Client**. Người dùng đăng nhập tại Authorization Server (AS), sau đó truy cập:

~~~http
GET /api/me HTTP/1.1
Host: portal.example.test
~~~

Controller cần lấy thông tin người dùng OAuth 2.0 hiện tại:

~~~java
@GetMapping("/api/me")
public Mono<UserView> me(@AuthenticationPrincipal OAuth2User user) {
    return Mono.just(new UserView(
        user.getName(),
        user.getAttribute("name")));
}
~~~

Ở production, ứng dụng có thể trải qua:

~~~text
Browser
  -> GET /oauth2/authorization/employee
  -> Authorization Server login/consent
  -> GET /login/oauth2/code/employee?code=...&state=...
  -> Spring Security đổi code lấy token
  -> tạo Authentication trong SecurityContext
  -> GET /api/me
~~~

Nhưng để kiểm tra logic WebFlux controller, ta **không cần** mỗi test phải:

- Mở browser tới IdP.
- Nhập mật khẩu.
- Thực hiện Authorization Code Flow.
- Gọi token/UserInfo/JWK endpoints thật.
- Lưu cookie/token từ một login production.

Spring Security Test cung cấp **`mockOAuth2Login()`**, một `WebTestClientConfigurer` chuyên dụng để đặt **OAuth2 Authentication giả** vào exchange đang được kiểm thử.

~~~java
webTestClient
    .mutateWith(mockOAuth2Login())
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

Điểm quan trọng: **test trên cho endpoint một authenticated OAuth2 principal giả**, chứ **không chứng minh** IdP, callback, token endpoint hoặc signature validation thật đã hoạt động.

> Phạm vi bài: Spring Security 6, Spring WebFlux, JUnit 5, WebTestClient và `SecurityMockServerConfigurers.mockOAuth2Login()`. Không dùng `SecurityMockMvcRequestPostProcessors.oauth2Login()` của Servlet: hai test stacks có API riêng. Tất cả identities/tokens/hosts bên dưới đều là dữ liệu giả.

## 2. Mục tiêu sau bài

Sau khi thực hành, người học cần:

1. Hiểu `mockOAuth2Login()` mô phỏng điều gì và không mô phỏng điều gì.
2. Nhận biết các kiểu `OAuth2User`, `OAuth2AuthenticationToken`, `ReactiveSecurityContextHolder`.
3. Cấu hình `WebTestClient` với Spring Security cho WebFlux.
4. Test endpoint yêu cầu đăng nhập và so sánh khi không có Authentication.
5. Tạo principal có `sub`, `name`, `email` hoặc claims tùy chỉnh.
6. Kiểm tra role/authority riêng với OAuth user attributes.
7. Kiểm tra registration ID của OAuth2 login.
8. Phân biệt `mockOAuth2Login()` với `mockOidcLogin()`, `mockJwt()` và `mockUser()`.
9. Test reactive method security và CSRF của session-based API.
10. Tách test login principal khỏi test `OAuth2AuthorizedClient`, WebClient token forwarding và real OAuth2 protocol.
11. Viết negative tests về principal, registration, tenant và quyền truy cập.
12. Chẩn đoán lỗi 302/401/403, thiếu `SecurityWebFilterChain` hoặc sai WebTestClient setup.

## 3. Kiến trúc và vị trí của mockOAuth2Login()

~~~mermaid
flowchart TD
    T["JUnit 5 test"] --> W["WebTestClient"]
    M["mockOAuth2Login()"] --> W
    W --> S["Spring Security WebFilterChain"]
    S --> C["WebFlux Controller"]
    C --> P["OAuth2User / OAuth2AuthenticationToken"]
    C --> B["Reactive Business Service"]
    AS["Authorization Server / IdP thật"] -. "Không được gọi trong mock-login test" .-> M
~~~

Không có bước token exchange thật trong test dạng này. Thay vì đưa credentials vào một trình duyệt, test gắn `SecurityContext` hợp lệ về mặt test vào exchange của WebFlux.

### 3.1. Những điều được mock

`mockOAuth2Login()` có thể tạo:

- Một `OAuth2AuthenticationToken`.
- Một `OAuth2User` làm principal.
- OAuth2 user attributes/authorities để controller và authorization layer đọc.
- Registration context cho Authentication.

### 3.2. Những điều không tự được xác minh

Không tự kiểm chứng:

- User thật đã nhập đúng mật khẩu tại IdP.
- Authorization Server đã ký ID Token hoặc cấp access token hợp lệ.
- `state`, `nonce` và PKCE đã được validate qua callback.
- OIDC discovery/JWKS response thực sự hợp lệ.
- Browser cookie có đúng `SameSite`, `Secure` hay không.
- Downstream Resource Server đã chấp nhận một Bearer token.
- Refresh token rotation hoạt động.

**Mocked Authentication là input được test chủ động tin tưởng**, dùng để cô lập và kiểm tra code đang ở sau authentication.

## 4. Từ OAuth2 login đến SecurityContext trong WebFlux

Một `OAuth2AuthenticationToken` chứa:

~~~text
principal: OAuth2User
authorities: Collection<GrantedAuthority>
authorizedClientRegistrationId: String
authenticated: true
~~~

Controller có thể nhận:

~~~java
@AuthenticationPrincipal OAuth2User user
~~~

hoặc:

~~~java
Authentication authentication
~~~

hoặc trong Reactive style:

~~~java
Mono<Principal> principal
~~~

Tùy method argument resolver của WebFlux, `Authentication` thường là một kiểu `Principal`. Trong Reactor pipeline, Spring Security còn cung cấp:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

để lấy SecurityContext từ Reactor context.

### 4.1. OAuth2User không phải OAuth2AuthorizedClient

Phân biệt:

| Kiểu | Chức năng |
|---|---|
| `OAuth2User` | Attributes, name, authorities của user đã đăng nhập |
| `OAuth2AuthenticationToken` | Authentication và registration ID hiện tại |
| `ClientRegistration` | Cấu hình một OAuth client |
| `OAuth2AuthorizedClient` | Access/refresh token được cấp cho registration/principal |
| `ReactiveOAuth2AuthorizedClientService` | Lưu authorized clients ở Reactive stack |

**Có OAuth2User không đồng nghĩa đã có access token usable cho mọi API**. Đây là một giới hạn rất quan trọng khi viết tests.

## 5. Dependencies mẫu cho Spring Boot WebFlux

Với Gradle Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.x.x"
    id("io.spring.dependency-management") version "1.x.x"
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

`3.x.x` và `1.x.x` là placeholders: trong project thật phải dùng versions tương thích, không copy nguyên placeholders để chạy Gradle. Spring Boot BOM thường quản lý versions của Spring Security, Reactor và Spring Framework.

### 5.1. Không nhầm với Servlet starter

Nếu ứng dụng chỉ cần WebFlux Reactive stack, không chủ động thêm `spring-boot-starter-web` (Spring MVC) vào test classpath mà không có lý do. Nếu cả MVC và WebFlux nằm trên classpath, Spring Boot có thể chọn Servlet web application type theo auto-configuration.

### 5.2. Import đúng mockOAuth2Login()

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;
~~~

**Không dùng import Servlet:**

~~~java
// Không dùng trong WebTestClient:
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Login;
~~~

Đây là lỗi thường gặp khi copy code từ chương kiểm thử Servlet sang Reactive.

## 6. Controller mẫu yêu cầu OAuth2User

Tạo một controller chỉ trả những dữ liệu an toàn:

~~~java
package com.example.portal.web;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ProfileController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
        @AuthenticationPrincipal OAuth2User user
    ) {
        String displayName = user.getAttribute("name");

        return Mono.just(Map.of(
            "subject", user.getName(),
            "displayName",
            displayName != null ? displayName : user.getName()
        ));
    }
}
~~~

Khi Browser đã login OAuth2 hợp lệ, Spring WebFlux inject user từ Authentication hiện tại. Test sẽ cung cấp `OAuth2User` giả.

### 6.1. Vì sao không trả toàn bộ attributes?

`OAuth2User.getAttributes()` có thể chứa email, avatar URL hoặc thông tin cá nhân khác. Trong API production, không trả toàn bộ attributes theo mặc định; chọn từng field được phép.

### 6.2. Vì sao controller trả Mono?

WebFlux ưu tiên kiểu Reactive khi cần pipeline bất đồng bộ. Trong trường hợp ánh xạ một principal có sẵn, `Mono.just(...)` chỉ là ví dụ đơn giản, không thực hiện HTTP network hay blocking I/O.

## 7. SecurityWebFilterChain cho các endpoint mẫu

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication
    .HttpStatusServerEntryPoint;

@Configuration
@EnableWebFluxSecurity
public class PortalSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
        ServerHttpSecurity http
    ) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasAuthority("ROLE_ADMIN")
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll()
            )
            .oauth2Login(Customizer.withDefaults())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED))
            )
            .build();
    }
}
~~~

Cấu hình này có những đặc điểm:

- `/api/public`: public.
- `/api/admin/report`: yêu cầu `ROLE_ADMIN`.
- Các `/api/**` còn lại: yêu cầu authenticated.
- Với unauthenticated API, trả **401** thay vì tự redirect sang login page.
- `oauth2Login()` khai báo hỗ trợ OAuth2 login trong Reactive filter chain.

**Entry point 401 là lựa chọn của API minh họa**, không phải default của mọi ứng dụng. Nếu ứng dụng dùng browser page, bạn có thể muốn redirect login; tests phải assert đúng contract.

### 7.1. Test vẫn cần chain thật nếu muốn kiểm chứng 401/403

Nếu chỉ gọi controller trực tiếp:

~~~java
controller.me(fakeUser)
~~~

bạn chỉ kiểm tra method logic, không kiểm chứng SecurityWebFilterChain. `WebTestClient` gắn Security filter chain phù hợp để test authenticated/denied paths.

### 7.2. oauth2Login() có thể cần ClientRegistrationRepository

Trong test context bật OAuth2 login, Spring Security có thể cần một `ReactiveClientRegistrationRepository` để xây các filters. Dùng fake registration ở test profile; tránh issuer discovery gọi IdP production chỉ để dựng test application context.

## 8. Controller cho cả registration và Authentication

Để kiểm tra mock tạo registration context nào, thêm endpoint:

~~~java
package com.example.portal.web;

import java.security.Principal;
import java.util.Map;
import org.springframework.security.oauth2.client.authentication
    .OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class LoginContextController {

    @GetMapping("/api/login-context")
    public Mono<Map<String, String>> context(
        Mono<Principal> principal
    ) {
        return principal
            .cast(OAuth2AuthenticationToken.class)
            .map(auth -> Map.of(
                "registrationId",
                auth.getAuthorizedClientRegistrationId(),
                "principalName",
                auth.getName()
            ));
    }
}
~~~

Đường dẫn `/api/login-context` là probe cho bài học. Trong app thật, chỉ expose dữ liệu cần thiết; không trả client secret, refresh token hay raw access token.

### 8.1. current login registration khác token dùng cho API

`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` cho biết registration của **Authentication hiện tại**. Nó không chứng minh ứng dụng đã có authorized client của một registration khác để gọi Resource Server.

## 9. ClientRegistration giả để test không cần IdP

Tạo một fixture:

~~~java
package com.example.portal.test;

import org.springframework.security.oauth2.client.registration
    .ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

public final class TestClientRegistrations {
    private TestClientRegistrations() {}

    public static ClientRegistration employee() {
        return ClientRegistration
            .withRegistrationId("employee")
            .clientId("employee-test-client")
            .clientSecret("test-secret-not-production")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("profile", "orders.read")
            .authorizationUri(
                "https://idp.example.test/oauth2/authorize")
            .tokenUri(
                "https://idp.example.test/oauth2/token")
            .userInfoUri(
                "https://idp.example.test/userinfo")
            .userNameAttributeName("sub")
            .clientName("Employee OAuth2 Test Client")
            .build();
    }

    public static ClientRegistration admin() {
        return ClientRegistration
            .withRegistrationId("admin")
            .clientId("admin-test-client")
            .clientSecret("admin-test-only-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("profile", "audit.read")
            .authorizationUri(
                "https://idp.example.test/oauth2/authorize")
            .tokenUri(
                "https://idp.example.test/oauth2/token")
            .userInfoUri(
                "https://idp.example.test/userinfo")
            .userNameAttributeName("sub")
            .clientName("Admin OAuth2 Test Client")
            .build();
    }
}
~~~

Hai registrations có cùng Authorization Server URI nhưng khác:

- Registration ID.
- Client ID.
- Test secret.
- Requested scopes.

Không cần dùng client credentials thật hoặc gọi token endpoint trong mock-login test.

### 9.1. Tại sao ở đây không dùng OIDC openid scope?

Ví dụ này đang test **OAuth2User** với `mockOAuth2Login()`. Với OIDC, ứng dụng thường nhận `OidcUser` và ID Token; khi muốn kiểm tra những cấu trúc đó, dùng `mockOidcLogin()` ở phần đối chiếu.

### 9.2. Registration fixture không phải authorized client/token fixture

`ClientRegistration` chỉ mô tả một OAuth client. Không vì tạo fixture này mà tự có real access token; method `mockOAuth2Login()` được dùng để tạo authentication state của test.

## 10. Fake OAuth2User có identity và authorities rõ ràng

Đừng để test phụ thuộc name/attributes mặc định của mock nếu assertions cần cụ thể. Tạo user:

~~~java
package com.example.portal.test;

import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;

public final class TestOAuth2Users {
    private TestOAuth2Users() {}

    public static OAuth2User aliceEmployee() {
        return new DefaultOAuth2User(
            List.of(new SimpleGrantedAuthority("ROLE_EMPLOYEE")),
            Map.of(
                "sub", "employee-001",
                "name", "Alice Nguyen",
                "email", "alice@example.test",
                "department", "orders"
            ),
            "sub"
        );
    }

    public static OAuth2User aliceAdmin() {
        return new DefaultOAuth2User(
            List.of(
                new SimpleGrantedAuthority("ROLE_EMPLOYEE"),
                new SimpleGrantedAuthority("ROLE_ADMIN")
            ),
            Map.of(
                "sub", "employee-001",
                "name", "Alice Nguyen",
                "email", "alice@example.test"
            ),
            "sub"
        );
    }
}
~~~

`DefaultOAuth2User(..., "sub")` chọn `sub` làm name attribute, nên:

~~~java
user.getName(); // "employee-001"
~~~

Authorities được đưa vào Authentication, dùng cho `hasAuthority()` hoặc `hasRole()`.

### 10.1. Email không phải name attribute bắt buộc

Một provider có thể dùng `id`, `sub` hoặc một attribute được cấu hình làm principal name. Test phải khớp contract thực tế; không suy từ email là định danh bất biến.

### 10.2. Authorities không tự lấy từ bất kỳ attribute nào

Một fake user có:

~~~json
{"roles": ["ADMIN"]}
~~~

không có nghĩa Spring Security sẽ tự sinh `ROLE_ADMIN`. Cần một authority mapping ở application hoặc cấu hình test `GrantedAuthority` phù hợp.

## 11. Cách viết test đầu tiên bằng WebTestClient

Import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;
~~~

Một test có thể viết:

~~~java
@Test
void meRequiresAnOauth2User() {
    webTestClient
        .mutateWith(
            mockOAuth2Login()
                .oauth2User(TestOAuth2Users.aliceEmployee())
        )
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.subject").isEqualTo("employee-001")
        .jsonPath("$.displayName").isEqualTo("Alice Nguyen");
}
~~~

Đây là dạng test quan trọng nhất của bài:

1. `mockOAuth2Login()` xây OAuth2 Authentication cho exchange.
2. `.oauth2User(...)` đưa principal có attributes/authorities rõ ràng.
3. `mutateWith(...)` áp cấu hình cho test client/exchange.
4. WebFilterChain đánh giá authentication.
5. MVC-style method argument? **Không**: đây là WebFlux controller, được reactive argument resolver inject `OAuth2User`.
6. Assertions kiểm tra response được tạo từ principal.

### 11.1. Viết test fail khi không đăng nhập

~~~java
@Test
void meWithoutAuthenticationReturns401() {
    webTestClient
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

Assertion `401` đúng với **SecurityWebFilterChain mẫu đã cấu hình entry point 401**. Nếu ứng dụng mặc định redirect browser tới `/login`, thay assertion tương ứng; không hard-code 401 cho mọi OAuth2 login app.

### 11.2. Dùng fixture riêng tránh user mặc định

Test chỉ:

~~~java
mockOAuth2Login()
~~~

có thể đủ để qua `.authenticated()`, nhưng khi cần phân biệt principal/role/tenant, hãy cung cấp fake user cụ thể.

## 12. Cách setup @WebFluxTest với WebTestClient

Đối với controller slice:

~~~java
package com.example.portal.web;

import com.example.portal.test.TestOAuth2Users;
import com.example.portal.test.TestClientRegistrations;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;

@WebFluxTest(
    controllers = {ProfileController.class, LoginContextController.class}
)
@Import(ReactiveOAuth2TestConfig.class)
class ProfileControllerWebFluxTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void authenticatedEmployeeCanReadOwnProfile() {
        webTestClient
            .mutateWith(mockOAuth2Login()
                .oauth2User(TestOAuth2Users.aliceEmployee())
                .clientRegistration(TestClientRegistrations.employee()))
            .get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("employee-001");
    }
}
~~~

`ReactiveOAuth2TestConfig` là test configuration ở mục tiếp theo; import thêm service mocks nếu controllers có dependencies.

### 12.1. Fake ReactiveClientRegistrationRepository trong test

~~~java
package com.example.portal.web;

import com.example.portal.test.TestClientRegistrations;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration
    .InMemoryReactiveClientRegistrationRepository;

@TestConfiguration
public class ReactiveOAuth2TestConfig {

    @Bean
    ReactiveClientRegistrationRepository testRegistrations() {
        return new InMemoryReactiveClientRegistrationRepository(
            TestClientRegistrations.employee(),
            TestClientRegistrations.admin()
        );
    }
}
~~~

Với cấu hình này, WebFlux/Spring Security có registrations cho `employee` và `admin` mà không cần discovery thật.

### 12.2. Security chain có được load vào @WebFluxTest không?

Slice test chỉ nạp một phần application context. Nếu `PortalSecurityConfig` không nằm trong context của `@WebFluxTest`, cần import nó:

~~~java
@Import({
    ReactiveOAuth2TestConfig.class,
    PortalSecurityConfig.class
})
~~~

Trong project thật, tránh tạo **hai** SecurityWebFilterChain không chủ ý; nếu Boot auto config cung cấp default chain, test cần biết chain nào thực sự được dùng.

### 12.3. Chọn slice hay full context?

`@WebFluxTest` phù hợp để kiểm tra WebFlux controller và security integration giới hạn. Nếu muốn xác minh wiring của toàn bộ reactive OAuth2 Client, database/token store, custom success handler hoặc WebClient manager, cân nhắc `@SpringBootTest` và fake dependencies.

## 13. @SpringBootTest + @AutoConfigureWebTestClient

Khi cần boot context đầy đủ:

~~~java
package com.example.portal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class OAuth2LoginReactiveIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void meIsVisibleForMockOauth2Principal() {
        webTestClient
            .mutateWith(mockOAuth2Login())
            .get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

**Lưu ý:** `mockOAuth2Login()` tích hợp mạnh nhất khi WebTestClient được bind **in-process** với Spring WebFlux application context hoặc WebHandler thông qua Spring Security test hooks.

Nếu dùng `RANDOM_PORT` / `bindToServer()` để gửi HTTP qua TCP tới app process khác, một mock test configurer trong JVM test **không phải** browser authentication credential truyền qua mạng. Không nên giả định `mutateWith(mockOAuth2Login())` làm server ở đầu kia tự authenticated. Với network E2E test, dùng fake IdP, session/login flow hoặc test-only server mechanism được kiểm soát.

### 13.1. Vì sao phải chú ý WebApplicationType?

Nếu application khởi chạy dưới Spring MVC Servlet thay vì Reactive, `@AutoConfigureWebTestClient` có thể không áp dụng như mong đợi. Đảm bảo classpath và Boot web application type đúng WebFlux; không dùng WebTestClient mutator để thay cho MockMvc trong Servlet tests.

## 14. Bind WebTestClient thủ công với Spring Security

Không dùng Boot auto-config cũng có thể setup client:

~~~java
@Autowired
ApplicationContext applicationContext;

WebTestClient client;

@BeforeEach
void setUp() {
    client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .configureClient()
        .build();
}
~~~

Static import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
~~~

Sau đó:

~~~java
client
    .mutateWith(mockOAuth2Login())
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

### 14.1. .apply(springSecurity()) và .mutateWith(mockOAuth2Login()) khác nhau

`springSecurity()` tích hợp Security WebFilterChain/filters vào WebTestClient đã bind với application.

`mockOAuth2Login()` chuẩn bị principal Authentication cho request test.

**Chỉ mutate login nhưng không có security filters trong custom WebTestClient setup** có thể khiến request không đi qua authorization logic như production.

### 14.2. Không cần tự tạo SecurityContextHolder ThreadLocal

Reactive SecurityContext nằm trong Reactor context gắn với publisher/exchange. Không dùng:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

rồi mặc định nó sẽ propagate đúng trong mọi reactive chain. Hãy dùng `mockOAuth2Login()` hoặc reactive test mechanisms của Spring Security.

## 15. Tùy biến OAuth2 user attributes nhanh

Ngoài việc đưa toàn bộ `OAuth2User`:

~~~java
.oauth2User(TestOAuth2Users.aliceEmployee())
~~~

bạn có thể tùy biến attributes trên mock:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .attributes(attributes -> {
            attributes.put("sub", "employee-002");
            attributes.put("name", "Bob Tran");
            attributes.put("department", "finance");
        }))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.subject").isEqualTo("employee-002")
    .jsonPath("$.displayName").isEqualTo("Bob Tran");
~~~

Đây là đường tắt hữu ích khi controller chỉ cần một vài attributes.

### 15.1. Cần phân biệt attribute name và principal name

Không phải mọi thuộc tính đều được dùng làm `OAuth2User.getName()`. User name được xác định qua `userNameAttributeName` của `DefaultOAuth2User`/provider configuration hoặc fake mutator.

Nếu test cần principalName chính xác, dùng `.oauth2User(new DefaultOAuth2User(...))` với name attribute rõ ràng.

### 15.2. Missing attribute là case quan trọng

Nếu provider không trả `name`, controller cần fallback hoặc xử lý có chủ đích:

~~~java
String name = user.getAttribute("name");
String display = name != null ? name : user.getName();
~~~

Viết test fake user không có `name` và expect `displayName = subject`, tránh `NullPointerException` hoặc rò internal errors.

### 15.3. Input không đáng tin khi render output

Một provider có thể trả `name` có ký tự HTML/Unicode đặc biệt. JSON serialization thường encode theo JSON contract, nhưng frontend cần escape output đúng ngữ cảnh. Mock user có thể chứa tên chứa ký tự đặc biệt để test UI/frontend separately.

## 16. Tùy chỉnh authorities của OAuth2 user

Một endpoint:

~~~java
@GetMapping("/api/admin/report")
public Mono<Map<String, String>> adminReport() {
    return Mono.just(Map.of("result", "report-ready"));
}
~~~

được bảo vệ bởi:

~~~java
.pathMatchers(HttpMethod.GET, "/api/admin/report")
    .hasAuthority("ROLE_ADMIN")
~~~

Test user thiếu quyền:

~~~java
@Test
void employeeCannotReadAdminReport() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/admin/report")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Test user đủ quyền:

~~~java
@Test
void adminCanReadAdminReport() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceAdmin()))
        .get()
        .uri("/api/admin/report")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.result").isEqualTo("report-ready");
}
~~~

### 16.1. Tùy chỉnh trực tiếp qua authorities()

Spring Security Test còn có cách thiết lập authorities cho mock:

~~~java
.mutateWith(mockOAuth2Login()
    .authorities(
        new SimpleGrantedAuthority("ROLE_ADMIN")
    ))
~~~

Trong tests phức tạp, tạo một `DefaultOAuth2User` với danh sách authorities đã định nghĩa là cách dễ giữ identity và permission fixtures nhất quán.

### 16.2. hasRole vs hasAuthority

~~~java
.hasRole("ADMIN")
~~~

thường mong authority `ROLE_ADMIN`, còn:

~~~java
.hasAuthority("ADMIN")
~~~

mong literal `ADMIN`.

Nếu test 403 dù mock có `ADMIN`, kiểm tra prefix/authority mapping thay vì tăng scope tùy tiện.

### 16.3. GrantedAuthority không phải OAuth scopes được AS cấp

Mock authorities giúp test application authorization logic. Nhưng nó không chứng minh Authorization Server thật đã cấp `admin.read` hoặc Resource Server chấp nhận token đó. Cần test bearer access token/claims riêng khi nghiệp vụ gọi API.

## 17. Kiểm tra registrationId của mock login

Giả sử endpoint `/api/login-context` trả current registration ID.

~~~java
@Test
void loginContextUsesEmployeeRegistration() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .clientRegistration(TestClientRegistrations.employee())
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/login-context")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("employee")
        .jsonPath("$.principalName").isEqualTo("employee-001");
}
~~~

Nếu test dùng ADMIN registration:

~~~java
@Test
void loginContextUsesAdminRegistration() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .clientRegistration(TestClientRegistrations.admin())
            .oauth2User(TestOAuth2Users.aliceAdmin()))
        .get()
        .uri("/api/login-context")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("admin");
}
~~~

### 17.1. Registration ID là login context, không phải role

Một người login bằng registration tên `admin` **không tự có `ROLE_ADMIN`**. Business policy phải xét authorities, membership, scopes và resource ownership riêng.

### 17.2. Cùng OP không đồng nghĩa cùng registration

~~~text
employee -> https://idp.example.test
admin    -> https://idp.example.test
~~~

Hai registrations có thể cùng issuer/token endpoint nhưng vẫn dùng client IDs và scopes khác nhau. Test nên xác minh registration được chọn, không chỉ issuer giống.

### 17.3. Không hard-code registration default

Nếu không gọi `.clientRegistration(...)`, test mutator có thể dùng test registration mặc định. Đừng viết assertion rằng default luôn bằng production registration name. Khi cần xác minh ID, đặt fixture explicit.

## 18. Test khi OAuth2User không có attribute bắt buộc

Một endpoint có thể đòi `department` để xử lý logic:

~~~java
@GetMapping("/api/department")
public Mono<Map<String, String>> department(
    @AuthenticationPrincipal OAuth2User user
) {
    String value = user.getAttribute("department");
    if (value == null || value.isBlank()) {
        return Mono.just(Map.of("status", "missing-department"));
    }
    return Mono.just(Map.of("department", value));
}
~~~

Test:

~~~java
@Test
void missingDepartmentGetsControlledResponse() {
    OAuth2User withoutDepartment = new DefaultOAuth2User(
        List.of(new SimpleGrantedAuthority("ROLE_EMPLOYEE")),
        Map.of("sub", "employee-001"),
        "sub"
    );

    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(withoutDepartment))
        .get()
        .uri("/api/department")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.status").isEqualTo("missing-department");
}
~~~

Đây là ví dụ kiểm tra **application logic với attributes có thể thiếu**, không phải validate OIDC protocol.

### 18.1. Không giả định mọi provider có email

OAuth2 UserInfo attributes có thể rất khác giữa providers. Email có thể không được cấp hoặc chưa verified; đừng dùng email để định danh user khi cần khóa ổn định.

### 18.2. Khi app yêu cầu profile completeness

Nếu thiếu attribute bắt buộc và app policy cần từ chối, test HTTP 422/403 theo contract chứ không cố ép mọi mock user phải có đầy đủ fields. Mục tiêu là bao phủ những nhánh nghiệp vụ thật.

## 19. Kiểm thử @AuthenticationPrincipal và SecurityContext Reactor

Một endpoint có thể trực tiếp lấy Authentication từ Reactive context:

~~~java
package com.example.portal.web;

import java.util.Map;
import org.springframework.security.core.context
    .ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveContextController {

    @GetMapping("/api/reactive-auth")
    public Mono<Map<String, String>> authContext() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication())
            .map(auth -> Map.of(
                "principal", auth.getName(),
                "authenticated",
                Boolean.toString(auth.isAuthenticated())
            ));
    }
}
~~~

Test:

~~~java
@Test
void reactiveContextCarriesOauth2Login() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/reactive-auth")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.principal").isEqualTo("employee-001")
        .jsonPath("$.authenticated").isEqualTo("true");
}
~~~

### 19.1. Vì sao không dùng SecurityContextHolder trong Reactive pipeline?

`SecurityContextHolder` gắn với thread-based context trong Servlet. Reactor có thể chuyển scheduler/thread. Nếu code Reactive tự đọc ThreadLocal như nguồn duy nhất, có thể không tìm thấy Authentication.

**ReactiveSecurityContextHolder hoặc method argument injection** là cách phù hợp hơn trong WebFlux.

### 19.2. Test Reactor Context propagation

Nếu business service có `publishOn`/`subscribeOn`, test nên đảm bảo security context được truyền qua framework-supported Reactor context. Không xây test bằng việc sửa global static authentication giữa tests.

## 20. Test reactive method security với mockOAuth2Login()

Nếu ứng dụng dùng:

~~~java
@EnableReactiveMethodSecurity
~~~

thì method:

~~~java
@PreAuthorize("hasAuthority('ROLE_ADMIN')")
public Mono<String> generateReport() {
    return Mono.just("report-ready");
}
~~~

được kiểm tra khi publisher method được gọi theo Reactive method security configuration.

### 20.1. Test qua WebTestClient

Nếu controller gọi service:

~~~java
@GetMapping("/api/admin/report-from-service")
public Mono<String> report() {
    return reportService.generateReport();
}
~~~

Test không đủ quyền:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .oauth2User(TestOAuth2Users.aliceEmployee()))
    .get()
    .uri("/api/admin/report-from-service")
    .exchange()
    .expectStatus().isForbidden();
~~~

Test có quyền:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .oauth2User(TestOAuth2Users.aliceAdmin()))
    .get()
    .uri("/api/admin/report-from-service")
    .exchange()
    .expectStatus().isOk();
~~~

Điều kiện: test context phải bật `@EnableReactiveMethodSecurity`, bean service phải được Spring proxied và method được gọi qua proxy. Nếu mock service hoàn toàn, annotation ở service thật không được thực thi.

### 20.2. Chú ý Publisher return type

Reactive method security thường áp dụng cho `Mono`/`Flux` và các supported reactive signatures. Không giả định `@PreAuthorize` trên một method blocking chạy ngoài Reactor context luôn có tương đương semantics.

### 20.3. Roles test không chứng minh user thật có role đó

`mockOAuth2Login()` cung cấp authorities do test định nghĩa. Test authorization logic, không chứng minh mapping từ IdP claims sang ROLE_ADMIN production đúng. Cần test mapping riêng.

## 21. CSRF với POST endpoint dùng browser session

Với WebFlux OAuth2 Login, browser thường dùng session cookie. Các state-changing requests cần CSRF protection theo policy.

Ví dụ:

~~~java
@PostMapping("/api/settings")
public Mono<Map<String, String>> save(
    @AuthenticationPrincipal OAuth2User user
) {
    return Mono.just(Map.of("savedFor", user.getName()));
}
~~~

Nếu Spring Security CSRF được bật, một POST dù đã mock login vẫn có thể trả 403:

~~~java
@Test
void postWithoutCsrfFails() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .post()
        .uri("/api/settings")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Để test happy path, dùng Reactive CSRF test mutator:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
~~~

~~~java
@Test
void postWithCsrfAndOauthLoginSucceeds() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .mutateWith(csrf())
        .post()
        .uri("/api/settings")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.savedFor").isEqualTo("employee-001");
}
~~~

### 21.1. 403 không mặc nhiên là OAuth2 authorization thiếu

WebFilterChain có thể trả 403 do:

- Thiếu CSRF token.
- User đã authenticated nhưng thiếu role/authority.
- Tenant/resource policy từ chối.
- Custom authorization manager từ chối.

Cần xem request method, CSRF setup và authorization checks trước khi kết luận fake OAuth2User sai.

### 21.2. Không tắt CSRF chỉ để test pass

`csrf.disable()` có thể hợp lý trong một số stateless bearer-token APIs có threat model riêng, nhưng không nên tắt bừa vì browser session/CSRF tests khó viết.

## 22. Thử anonymous request và mock OAuth2Login theo cùng endpoint

Một cặp test:

~~~java
@Test
void anonymousCannotReadProfile() {
    webTestClient
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void oauth2PrincipalCanReadProfile() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isOk();
}
~~~

Điều này kiểm tra logic của `.authenticated()` tại WebFilterChain với entry point API 401 mẫu.

### 22.1. Có thể thấy 302 thay vì 401

Nếu SecurityWebFilterChain định tuyến unauthenticated browser tới OAuth login entry point, test anonymous có thể nhận 302 tới `/login` hoặc URL đăng nhập. Assertion không phải “luôn 401”, mà là **theo contract SecurityWebFilterChain thực tế**.

### 22.2. Không bỏ security chain trong test

Nếu anonymous cũng nhận 200, kiểm tra:

~~~text
WebTestClient có .apply(springSecurity())?
SecurityWebFilterChain có được load?
Endpoint có nằm ngoài securityMatcher/path matcher?
Controller test có bị bind trực tiếp mà không có filter?
~~~

Test qua controller mà không có filter không chứng minh endpoint được bảo vệ.

## 23. So sánh mockOAuth2Login() và mockOidcLogin()

Đây là khác biệt trung tâm:

| Đặc điểm | `mockOAuth2Login()` | `mockOidcLogin()` |
|---|---|---|
| Test stack | WebFlux WebTestClient | WebFlux WebTestClient |
| Principal | `OAuth2User` | `OidcUser` |
| Authentication | `OAuth2AuthenticationToken` | `OAuth2AuthenticationToken` |
| ID Token object | Không tạo OIDC ID Token theo mục tiêu mock | Có thể tùy biến `OidcIdToken` |
| UserInfo claims | OAuth2User attributes | OIDC claims/UserInfo |
| Dùng cho | Generic OAuth2 Login | OpenID Connect login |
| Thực sự gọi AS | Không | Không |
| Đúng khi controller yêu cầu OidcUser | Không nên | Có |

### 23.1. Không dùng mockOAuth2Login() khi controller yêu cầu OidcUser

Controller:

~~~java
@GetMapping("/api/oidc-sub")
public Mono<String> subject(
    @AuthenticationPrincipal OidcUser user
) {
    return Mono.just(user.getSubject());
}
~~~

Test nên dùng:

~~~java
.mutateWith(mockOidcLogin()
    .idToken(token -> token.claim("sub", "oidc-user-001")))
~~~

với import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
~~~

### 23.2. Cả hai mock đều không xác minh chữ ký

`mockOidcLogin()` tạo test OidcUser/claims mà không trao đổi code hoặc validate ID Token signature trên mạng. Muốn test thật OIDC validation, dùng fake OIDC Provider/JWKS/token endpoint integration.

### 23.3. OAuth2User và OidcUser không đồng nghĩa AccessToken

OIDC ID Token là token dành cho client Authentication, còn access token dùng để gọi Resource Server. Đừng gửi raw ID Token như Bearer token cho API chỉ vì mock OIDC login thành công.

## 24. So sánh với mockJwt() và mockOpaqueToken()

Một ứng dụng có thể vừa là:

~~~text
OAuth2 Login Client:
  Browser -> WebFlux app -> IdP

Resource Server:
  API consumer -> WebFlux app with Bearer token
~~~

Hai request models khác nhau:

| Test mutator | Authentication chủ đạo | Phù hợp |
|---|---|---|
| `mockOAuth2Login()` | OAuth2AuthenticationToken | Browser đăng nhập OAuth2 |
| `mockOidcLogin()` | OAuth2AuthenticationToken + OidcUser | Browser đăng nhập OIDC |
| `mockJwt()` | JwtAuthenticationToken | Resource Server nhận JWT Bearer |
| `mockOpaqueToken()` | BearerTokenAuthentication | Resource Server nhận opaque token |
| `mockUser()` | UsernamePasswordAuthenticationToken | User/password style authentication |

### 24.1. Dùng mockJwt cho endpoint chỉ yêu cầu OAuth2User có được không?

`JwtAuthenticationToken.getPrincipal()` thường không phải `OAuth2User`, nên `@AuthenticationPrincipal OAuth2User` có thể nhận null/sai type. Vì vậy dùng mutator phù hợp **Authentication type** mà endpoint cần.

### 24.2. Hai security chains khác nhau

Một WebFlux app có thể:

- Dùng session + OAuth2 Login cho `/ui/**`.
- Dùng stateless JWT bearer auth cho `/api/external/**`.

Tests phải dùng đúng mutator và đúng matcher/entry point của chain. Không dùng `mockOAuth2Login()` để thay cho một Resource Server JWT validation test.

## 25. @WithMockUser khác mockOAuth2Login() như thế nào?

`@WithMockUser` hoặc reactive equivalent test setup cấp Authentication với một username và authorities, nhưng **không tạo OAuth2User attributes**.

Nếu controller:

~~~java
@AuthenticationPrincipal OAuth2User user
~~~

thì `mockOAuth2Login()` phù hợp hơn.

Nếu controller chỉ yêu cầu:

~~~java
Principal principal
~~~

hoặc rule `.authenticated()`, nhiều loại Authentication có thể đủ; nhưng test nên phản ánh thực tế OAuth2 login.

### 25.1. Test trông đúng nhưng principal khác production

Một endpoint dùng:

~~~java
OAuth2AuthenticationToken token =
    (OAuth2AuthenticationToken) authentication;
~~~

sẽ không hoạt động nếu test chỉ dựng UsernamePasswordAuthenticationToken. Điều này giúp phát hiện tests “quá giả” và thiếu điều kiện OAuth2-specific.

## 26. mockOAuth2Login() không thay mockOAuth2Client()

Trong Reactive OAuth2 Client, ứng dụng còn có:

~~~java
ReactiveOAuth2AuthorizedClientService
ServerOAuth2AuthorizedClientRepository
ReactiveOAuth2AuthorizedClientManager
OAuth2AuthorizedClient
~~~

Nhiều tests cần **access token dành cho downstream API**, không chỉ principal đăng nhập.

### 26.1. Hai mục đích test khác nhau

**Test A — endpoint yêu cầu OAuth2 user:**

~~~text
Input: OAuth2User / OAuth2AuthenticationToken
Target: @AuthenticationPrincipal, RBAC, reactive SecurityContext
Tool: mockOAuth2Login()
~~~

**Test B — endpoint dùng authorized client để gọi API:**

~~~text
Input: registrationId + authorized client + access token
Target: reactive authorized-client repository/manager, WebClient Bearer
Tool: mockOAuth2Client() nếu phiên bản hỗ trợ,
      hoặc seed/mock đúng repository/service/manager
~~~

Các hooks/tests Reactive OAuth2 Client phụ thuộc phiên bản Spring Security và authorized-client integration. Dù dùng mutator hay fake manager, test phải xác minh đúng registration, principal và token.

### 26.2. Mock login không phải bằng chứng OAuth2AuthorizedClient tồn tại

`mockOAuth2Login()` chủ yếu đặt Authentication vào reactive exchange; không được suy rằng mọi production `ServerOAuth2AuthorizedClientRepository` hoặc JDBC/Redis authorized-client store đều đã chứa một real token chỉ vì test qua `mockOAuth2Login()`.

### 26.3. Khi test @RegisteredOAuth2AuthorizedClient trong WebFlux

Reactive WebFlux có integration cho authorized-client resolution, khác Servlet MVC. Khi method cần authorized client:

~~~text
Controller authorized-client argument
  -> resolver / manager / repository
  -> registration/principal matching
  -> token
~~~

test cần setup chính authorized-client store/manager mà resolver dùng; không chỉ fake OAuth2User.

## 27. Kiểm thử WebClient outbound token riêng với mock login

Giả sử một controller gọi Orders API bằng token từ authorized-client manager:

~~~text
Browser authenticated via employee registration
  -> WebFlux controller
  -> ReactiveOAuth2AuthorizedClientManager
  -> WebClient Bearer access token
  -> Orders API
~~~

`mockOAuth2Login()` chỉ giải quyết phần **Browser authenticated**. Để test Authorization header:

1. Dùng fake `ReactiveOAuth2AuthorizedClientManager` hoặc seed repository/service.
2. Tạo access token giả riêng cho `employee`.
3. Dùng fake downstream HTTP server hoặc `ExchangeFunction`.
4. Assert đúng `Authorization: Bearer <test-token>`.
5. Assert không có token của ADMIN/tenant khác.

### 27.1. Ví dụ fake token

~~~java
Instant now = Instant.now();
OAuth2AccessToken token = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "fake-employee-access-token",
    now.minusSeconds(5),
    now.plusSeconds(600),
    Set.of("orders.read")
);
~~~

Đây là token giả, không cần chữ ký JWT vì test đang xem outbound HTTP behavior.

### 27.2. Fake manager với Mockito

~~~java
ReactiveOAuth2AuthorizedClientManager manager =
    mock(ReactiveOAuth2AuthorizedClientManager.class);

OAuth2AuthorizedClient client = new OAuth2AuthorizedClient(
    TestClientRegistrations.employee(),
    "employee-001",
    token
);

when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
    .thenReturn(Mono.just(client));
~~~

**Chỉ mock return value là chưa đủ** nếu mục tiêu test là selection. Test phải capture `OAuth2AuthorizeRequest` để assert requested registration ID và principal đúng. Ngoài ra `ReactiveOAuth2AuthorizedClientManager.authorize(...)` nhận `OAuth2AuthorizeRequest` và trả `Mono<OAuth2AuthorizedClient>`; không dùng Servlet manager đồng bộ.

### 27.3. Không lấy token của current login thay registration của API

Một user có thể login bằng `employee` nhưng cần một authorized client khác cho Admin API. Business code phải chọn registration theo policy; không suy từ current Authentication rằng token của mọi API giống nhau.

## 28. Nhiều registrations: test employee và admin riêng

Controller `/api/login-context` trả login registration.

Test:

~~~java
@Test
void employeeLoginHasEmployeeRegistration() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .clientRegistration(TestClientRegistrations.employee())
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/login-context")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("employee");
}

@Test
void adminLoginHasAdminRegistration() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .clientRegistration(TestClientRegistrations.admin())
            .oauth2User(TestOAuth2Users.aliceAdmin()))
        .get()
        .uri("/api/login-context")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("admin");
}
~~~

### 28.1. Không cho rằng registration admin là role ADMIN

Một negative test rất hữu ích:

~~~java
@Test
void adminRegistrationWithoutAdminAuthorityStillGets403() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .clientRegistration(TestClientRegistrations.admin())
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/admin/report")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Chọn registration tên `admin` không chứng minh user có quyền admin. Authorization dựa trên verified roles/permissions.

### 28.2. Cùng issuer không cho phép gộp identities

Nếu hai registrations cùng OpenID Provider, các OAuth2User attributes có thể khác do scopes/userInfo permissions. Test không nên giả định mọi attributes hoặc roles giống nhau.

### 28.3. Pairwise subject trong OIDC

Khi chuyển sang OIDC, `sub` có thể là pairwise theo sector/client. Không auto-link tài khoản chỉ bằng email. Mock OAuth2 principal không kiểm chứng các đặc tính này; identity mapping tests cần fixture đúng contract của IdP.

## 29. Test multi-tenant với mock login

Một SaaS:

~~~text
tenant acme:
  registrationId = portal-acme
  user sub = acme-user-42

tenant globex:
  registrationId = portal-globex
  user sub = globex-user-42
~~~

Test có thể tạo hai OAuth2User và ClientRegistration fixtures. Tuy nhiên, **tenant được truyền từ browser** vẫn phải được xác minh server-side.

### 29.1. Không tin claim tenant chưa được mapping

Nếu test fake user có:

~~~json
{"tenant": "globex"}
~~~

nó chỉ là test input. Business authorization cần map identity đến active membership. Test case:

~~~text
Authenticated ACME user
Request candidate tenant = globex
Expect denied unless active GLOBEX membership and proper login grant
~~~

### 29.2. Test isolation theo principal

Hai users có cùng display name hoặc email:

~~~text
ACME Alice: sub=A-42
GLOBEX Alice: sub=G-42
~~~

không được tự dùng chung session/authorized client. Test should assert denied cross-tenant access, không chỉ response 200 của hai tenants riêng lẻ.

### 29.3. Registration không phải tenant policy

Một registration ID có thể map tới tenant nhưng application còn cần membership/resource authorization. Không dùng `getAuthorizedClientRegistrationId()` làm bằng chứng duy nhất user được phép đọc mọi bản ghi tenant.

## 30. Test sau khi đổi scheduler: Reactive context không mất

Giả sử business service:

~~~java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .publishOn(Schedulers.boundedElastic());
}
~~~

Test `WebTestClient + mockOAuth2Login` vẫn nên thấy user chính xác nếu context được truyền bằng Reactor:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .oauth2User(TestOAuth2Users.aliceEmployee()))
    .get()
    .uri("/api/reactive-auth")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.principal").isEqualTo("employee-001");
~~~

### 30.1. Không truy cập ThreadLocal sau subscribeOn()

Bad pattern:

~~~java
String username =
    SecurityContextHolder.getContext()
        .getAuthentication()
        .getName();
~~~

trong Reactive pipeline có thể không có Authentication hoặc có context của thread khác. Nên dùng ReactiveSecurityContextHolder hoặc method arguments.

### 30.2. Không dùng block() trong event loop

Test code có thể dùng `StepVerifier` hoặc WebTestClient assertions để drive reactive publisher. Trong WebFlux runtime, `block()` trên event loop là anti-pattern. Mock login không làm code blocking trở nên non-blocking.

## 31. StepVerifier test service riêng với reactive SecurityContext

Khi không cần HTTP/WebFilterChain, bạn có thể unit test service đọc context:

~~~java
Authentication authentication = new OAuth2AuthenticationToken(
    TestOAuth2Users.aliceEmployee(),
    TestOAuth2Users.aliceEmployee().getAuthorities(),
    "employee"
);

Mono<String> result = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );

StepVerifier.create(result)
    .expectNext("employee-001")
    .verifyComplete();
~~~

`StepVerifier` đến từ Reactor Test, thường có trong Spring Boot starter test dependency set. Khi cần test HTTP endpoints, vẫn dùng `WebTestClient.mutateWith(mockOAuth2Login())` cho wiring đầy đủ.

### 31.1. Vì sao không dùng mockOAuth2Login() trong StepVerifier thuần?

`mockOAuth2Login()` là configurer của **WebTestClient**, không phải một Reactor `Context` trực tiếp cho mọi publisher. Unit test service có thể tự đặt SecurityContext bằng `ReactiveSecurityContextHolder.withAuthentication()`.

### 31.2. Hai levels kiểm thử bổ sung cho nhau

~~~text
StepVerifier:
  Unit test reactive service + explicit Authentication Context.

WebTestClient:
  HTTP routing + SecurityWebFilterChain + controller argument resolution.
~~~

Không thay thế hoàn toàn cái này bằng cái kia.

## 32. Xử lý trường hợp Authentication type không đúng

Controller:

~~~java
@GetMapping("/api/oauth2-only")
public Mono<String> oauth2Only(Mono<Principal> principal) {
    return principal
        .cast(OAuth2AuthenticationToken.class)
        .map(OAuth2AuthenticationToken::getAuthorizedClientRegistrationId);
}
~~~

Với `mockOAuth2Login()`, cast thành công.

Với `mockJwt()`, cast có thể fail vì principal Authentication là `JwtAuthenticationToken`, không phải `OAuth2AuthenticationToken`.

### 32.1. Có nên cast mù trong production?

Nếu endpoint thực sự chỉ cho OAuth2 login flow, có thể bảo vệ chain để chỉ những kiểu Authentication phù hợp vào. Nếu route được dùng bởi cả OAuth2 login và Bearer clients, dùng:

~~~java
if (authentication instanceof OAuth2AuthenticationToken oauth) {
    // OAuth2 login case.
} else {
    // Explicit fallback/error for different auth type.
}
~~~

để tránh `ClassCastException` bất ngờ.

### 32.2. Negative test auth type

Kiểm tra endpoint trả controlled 4xx/5xx theo API contract thay vì stack trace. Đừng lẫn lỗi programming type-cast với chuyện token invalid.

## 33. Mock login không chứng minh SecurityContext sống qua hai HTTP requests

Mỗi lần:

~~~java
webTestClient.mutateWith(mockOAuth2Login())
~~~

cho test exchange một Authentication giả.

Điều này **không tự chứng minh** session cookie được tạo, persist và quay lại trong request tiếp theo giống browser production.

### 33.1. Test session persistence riêng

Nếu ứng dụng dùng `WebSessionServerSecurityContextRepository` hoặc Spring Session, cần integration test bao gồm:

- Login callback/session creation (fake AS nếu cần).
- Session ID cookie.
- Second request gửi cookie.
- Session expiry/invalidation.
- Multi-node/shared session store behavior.

Mock mutator bypass các network/protocol steps đó.

### 33.2. SameSite/Secure/HttpOnly phải test tại browser/cookie layer

WebTestClient có thể inspect `Set-Cookie` headers nhưng không mô phỏng đầy đủ cross-site browser cookie enforcement. OIDC callback SameSite testing nên có browser E2E với origins/proxy tương ứng.

### 33.3. Không lưu mock credentials vào production storage

Test mocks và authorized-client fixtures dùng token giả; không đặt client secret thật hoặc reuse production session cookie vào CI logs.

## 34. Mock login và OAuth2 callback: ranh giới kiểm thử

Một login E2E thực có thể đi qua:

~~~mermaid
sequenceDiagram
    actor Browser as Browser
    participant App as Reactive Spring Security Client
    participant OP as OpenID Provider

    Browser->>App: GET /oauth2/authorization/employee
    App-->>Browser: 302 to OP, state/nonce/PKCE request
    Browser->>OP: Authenticate and authorize
    OP-->>Browser: Redirect code + state
    Browser->>App: GET /login/oauth2/code/employee?code=...&state=...
    App->>OP: POST /token with code
    OP-->>App: Access token/ID token or OAuth error
    App-->>Browser: Create session and redirect
    Browser->>App: GET /api/me with session cookie
~~~

Test `mockOAuth2Login()` bắt đầu ngay ở bước cuối:

~~~text
Assume OAuth2AuthenticationToken exists.
Test GET /api/me authorization and controller behavior.
~~~

### 34.1. Muốn test callback nên làm gì?

Sử dụng fake Authorization Server/OP để kiểm thử:

- Authorization request URI/client ID/scopes.
- `state` correlation.
- PKCE, nonce và redirect URI.
- Token response parsing và ID Token validation.
- Session/cookie persistence.
- Provider error callbacks.

Không coi mockOAuth2Login success là bằng chứng callback handling production đúng.

### 34.2. Test JWKS/issuer vẫn cần integration layer

`mockOAuth2Login()` không xác minh JWT signature. Với OIDC, validate JWK Set/issuer/audience/nonce ở integration test có fake OP/JWKS, không disable validation để test dễ pass.

## 35. Kiểm thử logic từ OAuth2User.getAttributes()

Một nghiệp vụ:

~~~java
public Mono<Boolean> isOrdersDepartment(OAuth2User user) {
    String department = user.getAttribute("department");
    return Mono.just("orders".equals(department));
}
~~~

Test có thể tạo:

~~~text
user A: department = orders -> true
user B: department = finance -> false
user C: missing department -> false
~~~

### 35.1. Không dùng user attribute làm role không xác minh

Nếu business layer coi `department` là authorization evidence, cần xác định attribute đó đến từ trusted provider/mapping và policy có cho phép không. Mock user có thể tự chứa gì cũng được; test input không tự chứng minh data production trusted.

### 35.2. Phân biệt identity data với permission

`preferred_username`, `name` hay `email` là identity/profile data, không nhất thiết là quyền truy cập. Authority/role do mapping/authorization policy tạo và có thể phụ thuộc tenant.

## 36. Kiểm thử error handling và 401/403

Các trạng thái nên phân biệt:

| Tình huống | Loại | Expected behavior theo chain mẫu |
|---|---|---|
| Anonymous GET /api/me | Không authenticated | 401 |
| Mock OAuth2User GET /api/me | Authenticated | 200 |
| Employee GET /api/admin/report | Thiếu ROLE_ADMIN | 403 |
| Admin GET /api/admin/report | Đủ ROLE_ADMIN | 200 |
| Employee POST /api/settings thiếu CSRF | CSRF denied | 403 |
| Employee POST /api/settings có CSRF | Authenticated + valid CSRF | 200 |
| Mock JWT tới endpoint cast OAuth2AuthenticationToken | Authentication type mismatch | Controlled error theo API policy |
| Mock OAuth2User thiếu attribute cần cho nghiệp vụ | Business validation | Controlled response/error |

### 36.1. Đừng quy mọi 403 thành “scope thiếu”

403 có thể do CSRF, role/authority, tenant authorization hoặc resource ownership. Trong test, quan sát security config và method authorization thay vì tự thay token scope bừa.

### 36.2. Không login redirect loop vì 401

Nếu WebFlux app dùng browser page, AuthenticationEntryPoint có thể là redirect; JSON API có thể chọn 401. Test nên phản ánh route-specific policy để frontend không liên tục theo redirect login ngoài mong muốn.

## 37. Kiểm thử lỗi sai provider/mismatched registration

Với hai ClientRegistrations:

~~~text
employee: client ID employee-test-client
admin:    client ID admin-test-client
~~~

Một test xác minh login context:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .clientRegistration(TestClientRegistrations.employee())
        .oauth2User(TestOAuth2Users.aliceEmployee()))
    .get()
    .uri("/api/login-context")
    .exchange()
    .expectBody()
    .jsonPath("$.registrationId").isEqualTo("employee");
~~~

Nhưng test đó **không bảo đảm** downstream OAuth2AuthorizedClientManager sẽ chọn registration employee khi gọi Orders API.

### 37.1. Chọn authorized client riêng

Nếu ứng dụng dùng Reactive WebClient OAuth2 filter, test business service selection bằng fake manager/repository và assert `OAuth2AuthorizeRequest.clientRegistrationId`, thay vì chỉ nhìn `OAuth2AuthenticationToken.registrationId`.

### 37.2. Nhiều providers khác nhau

Nếu employee và admin dùng hai issuers, mockOAuth2Login vẫn có thể tạo cả hai Authentication vì không thực hiện issuer verification. Test issuer trust boundary cần integration tests của callback/ID Token, không chỉ mock registration.

## 38. Best practices tránh flaky tests

1. Tạo **immutable fake users** hoặc object fixtures độc lập, không sửa map shared giữa tests.
2. Dùng registration IDs **cụ thể**, không phụ thuộc default mock value.
3. Tạo test ClientRegistration trực tiếp để không gọi Internet.
4. Với controller cần OAuth2User, dùng `mockOAuth2Login()`, không dùng `mockJwt()` theo thói quen.
5. Với controller cần OidcUser/ID Token claims, dùng `mockOidcLogin()`.
6. Với CSRF-protected POST, dùng `csrf()` thay vì disable CSRF.
7. Với role tests, authority fixture phải rõ `ROLE_*`.
8. Assert cả **anonymous denied** và **authenticated success**.
9. Tránh gọi real IdP/token endpoint trong unit/slice tests.
10. Test storage/manager riêng nếu endpoint dùng downstream authorized clients.
11. Không lưu mock Authentication vào static ThreadLocal chung tests.
12. Không dùng raw access token/secret production trong fixtures.
13. Nếu nhiều test classes share application context, không thay state global bừa bãi.
14. Khi test 401/403, phải biết SecurityWebFilterChain nào đang match.
15. Tách unit business assertions khỏi Spring Security wiring assertions khi cần chẩn đoán nhanh.

## 39. Troubleshooting khi mockOAuth2Login không hoạt động

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| Không tìm thấy method `mockOAuth2Login` | Thiếu `spring-security-test` hoặc sai import | Dùng `SecurityMockServerConfigurers` |
| Compile lỗi vì dùng `.with(...)` | Copy từ MockMvc Servlet | WebTestClient dùng `.mutateWith(...)` |
| Mock login vẫn nhận 401 | Security configurer/filter chain chưa tích hợp | Kiểm tra `springSecurity()` và reactive chain |
| Anonymous vẫn nhận 200 | Không có hoặc matcher sai security chain | Kiểm tra WebFilterChain/path match |
| Không inject OAuth2User | Authentication type sai | Dùng `mockOAuth2Login()`, đúng controller signature |
| `OidcUser` null | Dùng mockOAuth2Login thay OIDC mock | Dùng `mockOidcLogin()` |
| Principal name khác mong đợi | Tên mặc định/name attribute | Dùng `DefaultOAuth2User(...,"sub")` |
| 403 dù login thành công | Thiếu authority hoặc CSRF | Kiểm tra `ROLE_*` và `csrf()` |
| Test yêu cầu admin nhưng fake user là employee | Authority mapping không phù hợp | Set authorities theo policy |
| Registration ID khác | Chưa gọi `.clientRegistration(...)` | Dùng explicit fixture |
| OIDC issuer metadata load lỗi | `issuer-uri` kéo discovery | Fake ClientRegistration/IdP |
| Test pass nhưng JWT Resource Server fail | Mock login không test bearer validation | Dùng mockJwt/fake JWT validation integration |
| Authorized client không tồn tại | mock login chỉ giải quyết Authentication | Seed đúng Reactive authorized-client repository/service |
| WebClient gửi Bearer token sai | Registration selection/manager sai | Capture outgoing request và manager input |
| Test mất SecurityContext qua scheduler | Dùng ThreadLocal sai | Dùng ReactiveSecurityContextHolder/context propagation |
| Port-based HTTP test không nhận mock login | Mock mutator không truyền auth qua TCP | Bind in-process hoặc chạy fake real login flow |
| Test post không đi qua CSRF policy | Security chain chưa áp dụng hoặc bị disable | Kiểm tra filter chain & CSRF config |
| Test hiện HTML login thay JSON 401 | Browser login AuthenticationEntryPoint | Cấu hình API entry point, assert đúng behavior |

### 39.1. Cây quyết định debug

~~~text
WebFlux test with mockOAuth2Login failed
    |
    v
WebTestClient is bound in-process with springSecurity()?
    |-- No -> fix client binding.
    |
    v
SecurityWebFilterChain active and matching endpoint?
    |-- No -> import/configure reactive security.
    |
    v
mockOAuth2Login() mutator applied?
    |-- No -> use mutateWith().
    |
    v
Endpoint expects OAuth2User or OidcUser?
    |-- OidcUser -> mockOidcLogin().
    |
    v
OAuth2User name/attributes correct?
    |-- No -> use explicit DefaultOAuth2User.
    |
    v
Authorities satisfy rules?
    |-- No -> configure ROLE_* authority.
    |
    v
POST/PUT/DELETE requires CSRF?
    |-- Yes -> mutateWith(csrf()).
    |
    v
Registration context correct?
    |-- No -> clientRegistration(fixture).
    |
    v
Does endpoint also need OAuth2AuthorizedClient/token?
    |-- Yes -> seed/mock reactive manager/repository separately.
    |
    v
Review controller assertion and relevant HTTP security policy.
~~~

## 40. Các anti-pattern cần tránh

**1. Dùng OAuth2 Login mock thay cho việc xác minh callback.** Mock không gửi code/token request thật.

**2. Import `SecurityMockMvcRequestPostProcessors.oauth2Login()` vào WebFlux.** Sai test stack.

**3. Cho rằng `mockOAuth2Login()` tự tạo OIDC ID Token.** Dùng `mockOidcLogin()` cho OIDC user/ID Token claims.

**4. Cho rằng đã có authorized client access token cho mọi API.** Authentication và authorized-client state khác nhau.

**5. Test chỉ assert 200.** Nên assert principal name, safe attributes và registration/role khi liên quan.

**6. Dùng default authorities/name mà không biết giá trị.** Tạo explicit fixtures.

**7. Dùng mockJwt() để kiểm tra @AuthenticationPrincipal OAuth2User.** Resource Server authentication khác OAuth2 Login.

**8. Tắt CSRF để POST test pass.** Che mất một lớp bảo vệ browser session.

**9. Dùng global ThreadLocal cho Authentication trong Reactor.** Có thể mất context hoặc nhiễm sang test khác.

**10. Dùng live IdP/client secret trong unit test.** Không deterministic và có nguy cơ lộ secrets.

**11. Tin rằng mutator WebTestClient được gửi qua TCP tới một server khác.** Mock chỉ tác động test-bound exchange.

**12. Gộp registration ID với role.** Login qua registration admin không tự cấp quyền admin.

**13. Gộp name/email với stable user identity.** Có thể thay đổi hoặc trùng.

**14. Cho rằng mock successful là signature/JWKS validation đã pass.** Cần protocol integration tests.

**15. Không test anonymous/denied cases.** Happy path không chứng minh security policy.

## 41. Bài tập thực hành

### Bài 1 — Test user authenticated

Controller yêu cầu `@AuthenticationPrincipal OAuth2User`.

**Hỏi:** Dùng mutator nào trong WebTestClient?

**Gợi ý đáp án:** `mockOAuth2Login()` từ `SecurityMockServerConfigurers`. Dùng `.mutateWith(mockOAuth2Login())` trước request.

### Bài 2 — Test unauthenticated request

Endpoint `/api/me` được bảo vệ bằng `.authenticated()` và entry point HTTP 401.

**Hỏi:** Test request không mock login ra gì?

**Đáp án:** 401 Unauthorized theo chain đã chọn. Với browser login redirect chain khác, có thể là 302; không áp một status cho mọi cấu hình.

### Bài 3 — Đổi principal name

Muốn test `user.getName() == "employee-42"`.

**Đáp án:** Cung cấp `DefaultOAuth2User` có attributes `sub=employee-42` và `userNameAttributeName="sub"`, rồi `.oauth2User(user)`.

### Bài 4 — Test 403

User có `ROLE_EMPLOYEE`, endpoint cần `ROLE_ADMIN`.

**Hỏi:** Có cần đổi token scopes để test?

**Đáp án:** Không. Security rule theo GrantedAuthority trong ví dụ; fake OAuth2User có authority role tương ứng. Kiểm tra 403 với employee và 200 với admin.

### Bài 5 — Chọn registration

Ứng dụng có registrations `employee` và `admin`.

**Hỏi:** Kiểm tra current login registration bằng cách nào?

**Đáp án:** `mockOAuth2Login().clientRegistration(TestClientRegistrations.employee())`, gọi endpoint đọc `OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` và assert `employee`.

### Bài 6 — API cần OidcUser

Controller nhận `@AuthenticationPrincipal OidcUser` và gọi `getIdToken()`.

**Hỏi:** Có dùng mockOAuth2Login() không?

**Đáp án:** Dùng `mockOidcLogin()`, không phải generic OAuth2User mock.

### Bài 7 — CSRF

POST `/api/settings` với mock login trả 403.

**Hỏi:** Việc đầu tiên nên kiểm tra?

**Đáp án:** CSRF protection và authorization rules. Với browser session CSRF bật, dùng `.mutateWith(csrf())` cho happy-path test.

### Bài 8 — Resource Server JWT endpoint

Endpoint yêu cầu bearer JWT qua `oauth2ResourceServer().jwt()`.

**Hỏi:** mockOAuth2Login() có test đúng không?

**Đáp án:** Không phản ánh JwtAuthenticationToken/Resource Server behavior. Dùng `mockJwt()` hoặc fake JWT decoder validation integration.

### Bài 9 — WebClient gọi Orders API

Mock login đã pass nhưng WebClient không có access token.

**Hỏi:** Vì sao?

**Đáp án:** Authentication mock và OAuth2AuthorizedClient token storage là hai lớp. Cần mock/seed đúng ReactiveOAuth2AuthorizedClientManager hoặc repository/service rồi assert outgoing Authorization header.

### Bài 10 — Browser E2E

Mock test đã pass `/api/me` nhưng production OAuth callback lỗi `invalid_state`.

**Hỏi:** Mock test có bắt được không?

**Đáp án:** Không. `mockOAuth2Login()` bypass authorization request/callback/state. Cần fake IdP protocol integration/browser E2E để kiểm tra.

### Bài 11 — Multi-tenant

ACME và GLOBEX cùng issuer, khác registration IDs và membership.

**Hỏi:** Mock user claim `tenant=globex` có tự cấp quyền GLOBEX không?

**Đáp án:** Không. Application phải xác minh active membership và registration/token context theo tenant; test cross-tenant denial riêng.

### Bài 12 — WebTestClient kết nối server thật

Test dùng `bindToServer()` tới một app process remote.

**Hỏi:** `mutateWith(mockOAuth2Login())` có khiến remote server authenticated không?

**Đáp án:** Không thể mặc định. Mutator là test hook in-process, không phải OAuth credential qua TCP; cần login/fake OP hoặc test server mechanism phù hợp.

## 42. Checklist trước khi hoàn tất Reactive mock-login tests

| Câu hỏi | Điều cần đảm bảo |
|---|---|
| Đúng stack WebFlux? | Có |
| Import đúng mockOAuth2Login? | `SecurityMockServerConfigurers` |
| spring-security-test được khai báo? | Có |
| WebTestClient gắn Spring Security? | Có |
| SecurityWebFilterChain đang active? | Có |
| Test ClientRegistration không cần live IdP? | Có |
| OAuth2User có name attribute đúng? | Có |
| Attributes cần cho controller được cung cấp? | Có |
| Authorities rõ ràng theo RBAC? | Có |
| Test anonymous bị từ chối? | Có |
| Test authenticated được phép? | Có |
| Test employee thiếu admin role bị 403? | Có |
| Test admin đủ role được phép? | Có |
| Test registration ID explicit? | Có khi nhiều clients |
| Có phân biệt OAuth2User và OidcUser? | Có |
| Test ID Token claims dùng mockOidcLogin? | Có nếu liên quan OIDC |
| Test JWT Resource Server dùng mockJwt? | Có nếu liên quan Bearer JWT |
| POST được kiểm tra CSRF? | Có |
| ReactiveSecurityContextHolder được dùng đúng? | Có nếu service cần context |
| Không dùng ThreadLocal global trong Reactor? | Đúng |
| Không gọi production AS ở test? | Đúng |
| Mock login không bị coi là token exchange? | Đúng |
| Authorized-client manager/store được test riêng? | Có khi gọi API |
| Outgoing Bearer token được xác minh? | Có nếu application gửi token |
| Có negative tests principal/registration/tenant? | Có khi cần |
| Có tests cho callback/real cookies riêng? | Có nếu production yêu cầu |
| Test không lộ tokens/secrets? | Đúng |

## 43. Tổng kết

`mockOAuth2Login()` là công cụ cốt lõi của **Spring Security Test cho Reactive WebFlux** để kiểm thử endpoint yêu cầu **người dùng đã đăng nhập bằng OAuth 2.0**. Khi kết hợp:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .oauth2User(fakeOAuth2User)
        .clientRegistration(testRegistration))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

ta có thể kiểm tra WebFilterChain, `@AuthenticationPrincipal OAuth2User`, `OAuth2AuthenticationToken`, registration ID, reactive security context, role/authority và response behavior **mà không cần IdP thật**.

Để test đáng tin cậy, nên có **fixtures riêng** cho principal, attributes, authorities và ClientRegistration; dùng `@WebFluxTest` hoặc in-process WebTestClient gắn `springSecurity()`; test cả 401 anonymous, 403 thiếu quyền, CSRF cho POST và các cases sai registration/tenant.

Điều quan trọng nhất là giữ đúng phạm vi: **mockOAuth2Login kiểm tra Authentication sau login, không xác minh authorization-code callback, ID Token signature, token endpoint hay refresh-token behavior**. Khi endpoint thực sự dùng access token để gọi API, cần test `ReactiveOAuth2AuthorizedClientManager`/repository và outbound Bearer token riêng; khi endpoint đòi `OidcUser` thì dùng `mockOidcLogin()`; khi endpoint đóng vai trò Resource Server nhận JWT thì dùng `mockJwt()`.

Nhờ tách đúng các tầng test, ứng dụng vừa có test WebFlux nhanh, deterministic, vừa không nhầm lẫn giữa **đăng nhập OAuth2, phân quyền người dùng, lựa chọn authorized client và xác minh token thực tế**.
