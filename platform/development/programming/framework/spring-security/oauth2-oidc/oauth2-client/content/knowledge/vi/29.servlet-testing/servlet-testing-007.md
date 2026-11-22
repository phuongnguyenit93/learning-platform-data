# 29.7. Kiểm thử @RegisteredOAuth2AuthorizedClient và lựa chọn registration

## 1. Bối cảnh: controller nhận đúng token nhưng lấy từ OAuth client nào?

Một ứng dụng **Employee Portal** dùng **Spring Security OAuth 2.0/OIDC Client** với hai client registrations:

~~~text
portal-web
  -> Access token có scope orders.read
  -> Gọi Orders API

portal-admin
  -> Access token có scope audit.read
  -> Gọi Audit API
~~~

Cả hai có thể dùng chung OpenID Provider nhưng **client ID, scopes, authorization và token phải được phân biệt**. Một REST controller nhận:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-web")
OAuth2AuthorizedClient authorizedClient
~~~

để lấy token được cấp cho registration `portal-web`.

Nếu test chỉ gọi:

~~~java
mvc.perform(get("/api/orders").with(oidcLogin()));
~~~

rồi kiểm tra HTTP 200, có thể bỏ sót câu hỏi quan trọng: **controller đã được inject authorized client của đúng registration và principal chưa?** Ngoài ra, test cũng có thể thất bại vì mock login chỉ có một registration mặc định, còn controller đòi `portal-web`.

Một bộ test có ý nghĩa cần kiểm tra cả:

- HTTP request được xác thực theo đúng ngữ cảnh.
- `OAuth2AuthorizedClient` được resolver lấy từ repository/manager phù hợp.
- `registrationId` đúng.
- Principal sở hữu authorized client đúng.
- Access token/scopes có giá trị test mong đợi.
- Không gửi token của registration A cho API của registration B.
- Khi thiếu authorization, lỗi xảy ra theo policy và **không fallback sang token khác**.

> Bài thực hành tập trung vào **Spring MVC/Servlet**, Spring Boot 3, Spring Security 6, JUnit 5 và MockMvc. Không cần gọi Authorization Server thật để test method argument resolution. Ví dụ cần chỉnh imports/package/security policy theo ứng dụng. Các token dùng trong test đều là giá trị giả.

## 2. Mục tiêu học tập

Sau bài, người học có thể:

1. Giải thích vai trò của `@RegisteredOAuth2AuthorizedClient` trong Spring MVC.
2. Phân biệt **OAuth2 Authentication**, **ClientRegistration** và **OAuth2AuthorizedClient**.
3. Chọn đúng công cụ test: `oauth2Login()`, `oidcLogin()` và `oauth2Client()`.
4. Tạo fixture chứa nhiều registrations với issuer, client ID và scopes khác nhau.
5. Dùng MockMvc kiểm tra một controller có annotation chọn registration tường minh.
6. Test trường hợp annotation không chỉ rõ registration và phụ thuộc current OAuth2 login context.
7. Test principalName, scopes, token expiry và authorized-client repository.
8. Không nhầm `@WithMockUser` với một authorized client đã lưu.
9. Test các tình huống thiếu/wrong registration, 401/403, CSRF, nhiều tenants và session.
10. Biết giới hạn của MockMvc và khi nào dùng HTTP fake server/browser E2E.

## 3. Bốn thành phần dễ nhầm

| Thành phần | Ví dụ | Trách nhiệm |
|---|---|---|
| `Authentication` | `OAuth2AuthenticationToken` | Xác định principal hiện tại đã authenticated |
| `ClientRegistration` | `portal-web` | Metadata của một OAuth client (client ID, secret, grant, scopes, endpoints) |
| `OAuth2AuthorizedClient` | `portal-web + alice + AT-W` | Authorization/token được cấp cho client và principal |
| `OAuth2AuthorizedClientManager` | Servlet manager | Tải, authorize, refresh và lưu authorized client theo provider chain |

Một user đã đăng nhập OIDC không đồng nghĩa mọi OAuth client của ứng dụng đã được user cấp quyền:

~~~text
Current browser Authentication:
  registrationId = portal-web
  principal = alice

Authorized Client store:
  (portal-web, alice)  -> AT-W
  (portal-admin, alice) -> AT-A [có hoặc không]
~~~

Nếu controller cần `portal-admin`, không được thay thế bằng `portal-web` chỉ vì principal cùng tên.

### 3.1. Phân biệt registrationId và provider key

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal-web:
            provider: company-oidc
          portal-admin:
            provider: company-oidc
        provider:
          company-oidc:
            issuer-uri: https://login.example.test
~~~

Ở đây:

~~~text
Registration IDs: portal-web, portal-admin
Provider alias:   company-oidc
~~~

Annotation dùng **registration ID**, không phải provider alias.

### 3.2. Authorized client không phải ID Token

`OAuth2AuthorizedClient.getAccessToken()` trả access token để gọi Resource Server. OIDC `OidcUser.getIdToken()` là ID Token cho xác thực client; test không được coi chúng là một.

## 4. Annotation hoạt động ở lớp nào?

Controller:

~~~java
@GetMapping("/api/orders")
public String orders(
    @RegisteredOAuth2AuthorizedClient("portal-web")
    OAuth2AuthorizedClient authorizedClient
) {
    return authorizedClient.getClientRegistration().getRegistrationId();
}
~~~

Spring Security cung cấp:

~~~java
org.springframework.security.oauth2.client.web.method.annotation
    .OAuth2AuthorizedClientArgumentResolver
~~~

Đây là `HandlerMethodArgumentResolver` cho tham số có annotation tương ứng. Resolver sử dụng `OAuth2AuthorizedClientManager` nên kế thừa khả năng của manager (load authorized client, refresh/authorize phù hợp provider chain).

~~~mermaid
sequenceDiagram
    actor Test as MockMvc Test
    participant MVC as Spring MVC
    participant Resolver as OAuth2AuthorizedClientArgumentResolver
    participant Manager as OAuth2AuthorizedClientManager
    participant Repo as AuthorizedClientRepository
    participant Controller as OrdersController

    Test->>MVC: GET /api/orders with test SecurityContext + authorized client
    MVC->>Resolver: Resolve annotation("portal-web")
    Resolver->>Manager: authorize with registrationId + principal
    Manager->>Repo: Load authorized client
    Repo-->>Manager: portal-web / alice / AT-W
    Manager-->>Resolver: Authorized client
    Resolver-->>Controller: OAuth2AuthorizedClient parameter
    Controller-->>Test: Safe response (not token value)
~~~

**MockMvc test phải cung cấp đúng cả SecurityContext và authorized-client state khi controller cần chúng.** Đặt một Authentication giả mà repository không biết token có thể chưa đủ.

## 5. Hai kiểu sử dụng annotation

### 5.1. Chỉ định registration rõ ràng

~~~java
@RegisteredOAuth2AuthorizedClient("portal-web")
OAuth2AuthorizedClient webClient
~~~

tương đương:

~~~java
@RegisteredOAuth2AuthorizedClient(registrationId = "portal-web")
OAuth2AuthorizedClient webClient
~~~

`value` và `registrationId` là aliases của annotation. Đây là cách nên ưu tiên nếu endpoint luôn gọi một API bằng một registration cố định.

### 5.2. Để trống registration

~~~java
@RegisteredOAuth2AuthorizedClient
OAuth2AuthorizedClient currentClient
~~~

Khi không chỉ rõ ID, resolver có thể dựa vào `OAuth2AuthenticationToken` hiện hành để xác định registration (tùy request/authentication context và cách cấu hình).

Điều này cần được **test như một hành vi riêng**, nhất là ứng dụng có nhiều registrations hoặc nhiều kiểu Authentication.

### 5.3. Không chọn registration từ tên phương thức

Tên controller:

~~~java
public String adminOrders(...)
~~~

không khiến Spring tự chọn `portal-admin`. Cần annotation hoặc cơ chế selection tường minh.

## 6. Dependencies cho dự án và tests

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Nếu có WebClient dùng để gọi downstream API:

~~~kotlin
implementation("org.springframework.boot:spring-boot-starter-webflux")
~~~

chỉ khi ứng dụng cần WebClient/WebFlux components. Spring MVC test `MockMvc` không tự đòi ứng dụng phải chuyển sang Reactive stack.

Các versions nên được quản lý bằng Spring Boot dependency management/BOM tương thích; đừng trộn spring-security-test của version không khớp core.

## 7. Hai ClientRegistration fixtures có metadata khác nhau

Ta tạo test registrations trực tiếp để **không gọi OIDC discovery ở production**:

~~~java
package com.example.portal.test;

import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

public final class TestRegistrations {

    private TestRegistrations() {}

    public static ClientRegistration web() {
        return ClientRegistration.withRegistrationId("portal-web")
            .clientId("portal-web-test-client")
            .clientSecret("web-test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "orders.read")
            .authorizationUri("https://idp.example.test/oauth2/authorize")
            .tokenUri("https://idp.example.test/oauth2/token")
            .jwkSetUri("https://idp.example.test/oauth2/jwks")
            .issuerUri("https://idp.example.test")
            .clientName("Portal Web")
            .build();
    }

    public static ClientRegistration admin() {
        return ClientRegistration.withRegistrationId("portal-admin")
            .clientId("portal-admin-test-client")
            .clientSecret("admin-test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "audit.read")
            .authorizationUri("https://idp.example.test/oauth2/authorize")
            .tokenUri("https://idp.example.test/oauth2/token")
            .jwkSetUri("https://idp.example.test/oauth2/jwks")
            .issuerUri("https://idp.example.test")
            .clientName("Portal Admin")
            .build();
    }
}
~~~

Hai registrations dùng **cùng issuer** nhưng khác:

~~~text
registration ID
client ID
client secret giả
scope
clientName
~~~

Đây là mô hình phù hợp để bắt lỗi lấy nhầm authorized client. Nếu cả hai fixtures đều sử dụng cùng token/scopes, test khó phát hiện selection bug.

### 7.1. Tại sao không dùng real client secret?

MockMvc không thực hiện token exchange thực với IdP trong những tests này. Dùng secrets test cố định giúp tránh lộ production credential và giữ tests deterministic.

### 7.2. Vì sao dùng issuer/JWK URI giả?

Đây chỉ là metadata dùng xây `ClientRegistration`; tests controller không thực sự tải JWKS hoặc xác minh ID Token bằng network. Integration test thực với IdP cần fake discovery/JWK/token endpoints riêng.

## 8. Tạo OAuth2AccessToken giả cho test

Không dùng access token thật từ production. Dùng:

~~~java
package com.example.portal.test;

import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

public final class TestAccessTokens {
    private TestAccessTokens() {}

    public static OAuth2AccessToken webToken() {
        Instant now = Instant.now();
        return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "fake-access-token-for-web",
            now.minusSeconds(10),
            now.plusSeconds(600),
            Set.of("orders.read")
        );
    }

    public static OAuth2AccessToken adminToken() {
        Instant now = Instant.now();
        return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "fake-access-token-for-admin",
            now.minusSeconds(10),
            now.plusSeconds(600),
            Set.of("audit.read")
        );
    }
}
~~~

**Access tokens cần còn hạn** trong những tests chỉ nhằm kiểm tra argument resolution. Nếu fixture hết hạn, manager có thể cố refresh/reauthorize và test vô tình phụ thuộc token endpoint/provider configuration.

### 8.1. Vì sao expiresAt là tương lai?

~~~text
now = 09:00
expiresAt = 09:10
~~~

thì manager có thể tái sử dụng authorized client đã lưu. Với token hết hạn/sắp hết hạn và clock skew, nó có thể chọn provider refresh behavior, nằm ngoài phạm vi happy-path unit test.

### 8.2. Khi cần test expired token

Tạo token riêng có expiresAt trong quá khứ và **mock token refresh provider/manager hoặc fake token endpoint**, đừng sử dụng expired token trong tất cả fixtures mặc định.

## 9. Tạo OAuth2AuthorizedClient với principal cụ thể

~~~java
package com.example.portal.test;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

public final class TestAuthorizedClients {
    private TestAuthorizedClients() {}

    public static OAuth2AuthorizedClient webFor(String principalName) {
        return new OAuth2AuthorizedClient(
            TestRegistrations.web(),
            principalName,
            TestAccessTokens.webToken()
        );
    }

    public static OAuth2AuthorizedClient adminFor(String principalName) {
        return new OAuth2AuthorizedClient(
            TestRegistrations.admin(),
            principalName,
            TestAccessTokens.adminToken()
        );
    }
}
~~~

Trong production, `OAuth2AuthorizedClient` có thể chứa refresh token; ở đây không cần vì chỉ test resolve client còn hạn.

### 9.1. Principal key là ranh giới bảo mật

~~~text
portal-web + alice -> AT-W-Alice
portal-web + bob   -> AT-W-Bob
portal-admin + alice -> AT-A-Alice
~~~

Không lấy authorized client của `bob` khi Authentication hiện tại là `alice`.

### 9.2. Token không nhất thiết là JWT

`OAuth2AccessToken` trong Spring Security có thể chứa opaque token hoặc JWT string. Trong test resolver, chúng ta chỉ cần một token giả và expiry/scopes phù hợp; không cần token có chữ ký.

## 10. Controller mẫu: trả metadata an toàn thay vì token

Controller dùng để quan sát registration được inject:

~~~java
package com.example.portal.web;

import java.util.Map;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation
    .RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/test/clients")
public class AuthorizedClientProbeController {

    @GetMapping("/web")
    public Map<String, String> web(
        @RegisteredOAuth2AuthorizedClient("portal-web")
        OAuth2AuthorizedClient client
    ) {
        return safeView(client);
    }

    @GetMapping("/admin")
    public Map<String, String> admin(
        @RegisteredOAuth2AuthorizedClient("portal-admin")
        OAuth2AuthorizedClient client
    ) {
        return safeView(client);
    }

    @GetMapping("/current")
    public Map<String, String> current(
        @RegisteredOAuth2AuthorizedClient
        OAuth2AuthorizedClient client
    ) {
        return safeView(client);
    }

    private Map<String, String> safeView(OAuth2AuthorizedClient client) {
        return Map.of(
            "registrationId",
            client.getClientRegistration().getRegistrationId(),
            "principalName",
            client.getPrincipalName(),
            "clientId",
            client.getClientRegistration().getClientId()
        );
    }
}
~~~

Đường dẫn `/test/clients/**` chỉ để minh họa/test. Trong production, **không công bố access token, refresh token hoặc client secret**, và chỉ lộ metadata cần thiết theo authorization policy.

### 10.1. Controller này kiểm tra được gì?

Khi `/test/clients/web` trả:

~~~json
{
  "registrationId": "portal-web",
  "principalName": "alice",
  "clientId": "portal-web-test-client"
}
~~~

ta biết tham số `OAuth2AuthorizedClient` mà controller nhận thuộc registration/owner nào. **Chưa chứng minh access token được Resource Server chấp nhận**, vì đây là mock.

### 10.2. Tại sao không trả tokenValue?

Token giả trong test không nhạy cảm, nhưng pattern controller trả token trực tiếp dễ bị copy vào production. Nên kiểm tra token trong **test fixtures/spies** hoặc fake downstream server, thay vì biến response thành API tiết lộ Bearer credential.

## 11. Setup Spring Security và HttpSessionAuthorizedClientRepository cho MockMvc

Một cấu hình test cho Servlet:

~~~java
package com.example.portal.test;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration
    .InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.web
    .HttpSessionOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web
    .OAuth2AuthorizedClientRepository;
import org.springframework.security.web.SecurityFilterChain;

@TestConfiguration
public class OAuth2MvcTestConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        return new InMemoryClientRegistrationRepository(
            TestRegistrations.web(),
            TestRegistrations.admin()
        );
    }

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository() {
        return new HttpSessionOAuth2AuthorizedClientRepository();
    }

    @Bean
    SecurityFilterChain testSecurityChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Điểm quan trọng:

- Registration repository có cả `portal-web` và `portal-admin`.
- Authorized-client repository dùng **HttpSessionOAuth2AuthorizedClientRepository** trong test.
- Spring Security filters hoạt động trong MockMvc.
- Controller có argument resolver được đăng ký qua Spring MVC/Security configuration.

**Không khởi động Authorization Server thật**; fake registrations chỉ mang metadata.

### 11.1. Tại sao repository bean quan trọng?

Test request postprocessors như `oauth2Client()`, `oauth2Login()` và `oidcLogin()` có thể đưa authorized client giả vào session thông qua **HttpSessionOAuth2AuthorizedClientRepository**. Nếu ứng dụng lại dùng repository custom hoặc service-based manager không đọc cùng nơi, argument resolver có thể không tìm thấy token.

Muốn test production repository/custom manager, phải set up **cùng implementation và storage contract** với resolver, không giả định postprocessor tự điền mọi backend.

### 11.2. Tại sao cần Spring Security filter chain?

`oauth2Login()` và `oidcLogin()` postprocessors thiết lập Authentication vào mock request context; Spring Security filters làm Authentication có hiệu lực trong `SecurityContextHolder` khi MVC/controller chạy.

Với `MockMvcBuilders.standaloneSetup(...)`, cần `.apply(springSecurity())` hoặc gắn Security filter chain đúng cách, đồng thời đăng ký argument resolver phù hợp.

## 12. @WebMvcTest: một test class tập trung vào controller

~~~java
package com.example.portal.web;

import com.example.portal.test.OAuth2MvcTestConfig;
import com.example.portal.test.TestRegistrations;
import com.example.portal.test.TestAccessTokens;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Client;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@WebMvcTest(controllers = AuthorizedClientProbeController.class)
@Import(OAuth2MvcTestConfig.class)
class AuthorizedClientProbeControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void webEndpointUsesWebRegistrationForAlice() throws Exception {
        mvc.perform(get("/test/clients/web")
                .with(user("alice"))
                .with(oauth2Client("portal-web")
                    .clientRegistration(TestRegistrations.web())
                    .principalName("alice")
                    .accessToken(TestAccessTokens.webToken())))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.registrationId")
                .value("portal-web"))
            .andExpect(jsonPath("$.principalName")
                .value("alice"))
            .andExpect(jsonPath("$.clientId")
                .value("portal-web-test-client"));
    }

    @Test
    void adminEndpointUsesAdminRegistrationForAlice() throws Exception {
        mvc.perform(get("/test/clients/admin")
                .with(user("alice"))
                .with(oauth2Client("portal-admin")
                    .clientRegistration(TestRegistrations.admin())
                    .principalName("alice")
                    .accessToken(TestAccessTokens.adminToken())))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.registrationId")
                .value("portal-admin"))
            .andExpect(jsonPath("$.principalName")
                .value("alice"))
            .andExpect(jsonPath("$.clientId")
                .value("portal-admin-test-client"));
    }
}
~~~

**Điểm then chốt:** MockMvc request vừa có `user("alice")` để qua authentication layer, vừa có `oauth2Client("portal-web")` hoặc `oauth2Client("portal-admin")` để repository có authorized-client entry đúng registration/principal.

### 12.1. Với SecurityMockMvc test, `@WithMockUser` có thay được `user("alice")`?

Có thể dùng:

~~~java
@WithMockUser(username = "alice")
@Test
void webEndpointUsesWebRegistration() throws Exception {
    mvc.perform(get("/test/clients/web")
            .with(oauth2Client("portal-web")
                .principalName("alice")
                .clientRegistration(TestRegistrations.web())
                .accessToken(TestAccessTokens.webToken())))
        .andExpect(status().isOk());
}
~~~

Nhưng `@WithMockUser` chỉ thiết lập một Authentication giả; nó **không tự tạo OAuth2AuthorizedClient**. Vì vậy `oauth2Client()` vẫn cần thiết trong kịch bản này.

### 12.2. Nếu `@WebMvcTest` dùng security configuration thật

Có thể cần `@Import` các filter-chain/manager/repository beans thuộc slice. Tránh vô tình có hai beans cùng kiểu hoặc auto-configuration đòi issuer discovery ra Internet.

Test nên có cấu hình rõ ràng, hoàn toàn local.

## 13. oauth2Client() — công cụ chính để test annotation

Spring Security Test cung cấp:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Client;
~~~

Sử dụng tối giản:

~~~java
mvc.perform(get("/test/clients/web")
        .with(user("user"))
        .with(oauth2Client("portal-web")))
    .andExpect(status().isOk());
~~~

Tuy nhiên, postprocessor mặc định sẽ tạo một authorized client **giả** với metadata, token và principal mặc định; nếu app cần `clientId/scopes` đúng fixtures, nên cấu hình:

~~~java
.with(oauth2Client("portal-web")
    .principalName("alice")
    .clientRegistration(TestRegistrations.web())
    .accessToken(TestAccessTokens.webToken()))
~~~

### 13.1. Các customizations đáng chú ý

| Method | Dùng để |
|---|---|
| `oauth2Client("portal-web")` | Chọn registration ID của fake authorized client |
| `.principalName("alice")` | Đặt owner của authorized client |
| `.clientRegistration(clientRegistration)` | Gắn metadata client đầy đủ |
| `.clientRegistration(builder -> ...)` | Sửa client registration builder trong test |
| `.accessToken(accessToken)` | Gắn access token/scopes/expiry giả |

### 13.2. `oauth2Client()` không tương đương `oauth2Login()`

`oauth2Client()` tập trung đặt **authorized-client state vào repository/session**. Nó không tự bảo đảm user có OAuth2AuthenticationToken/OidcUser; nếu endpoint yêu cầu authentication, thêm `user()`, `oauth2Login()` hoặc `oidcLogin()` tùy test.

### 13.3. Không phụ thuộc default token fixture cho security policy

Postprocessor mặc định có scopes đơn giản (ví dụ `read`). Nếu controller kiểm tra `orders.read`, hãy tạo access token có đúng scope.

## 14. oidcLogin() — mô phỏng OIDC Authentication và authorized client

Với ứng dụng OIDC:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
~~~

Test current registration:

~~~java
@Test
void currentRegistrationUsesOidcLoginRegistration() throws Exception {
    mvc.perform(get("/test/clients/current")
            .with(oidcLogin()
                .clientRegistration(TestRegistrations.web())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId")
            .value("portal-web"));
}
~~~

`oidcLogin()` tạo mock `OidcUser` và `OAuth2AuthenticationToken`, đồng thời liên kết authorized client giả vào session. Vì vậy phù hợp khi controller có:

~~~java
@AuthenticationPrincipal OidcUser user
~~~

hoặc dựa vào OIDC claims.

### 14.1. Tùy chỉnh ID Token claims

~~~java
mvc.perform(get("/api/profile")
    .with(oidcLogin()
        .clientRegistration(TestRegistrations.web())
        .idToken(token -> token.claim("tenant", "acme"))));
~~~

Claims được tạo **giả** cho test; không có chữ ký/issuer thật được xác minh qua mạng trong mock request.

### 14.2. Khi nào vẫn dùng oauth2Client() cùng oidcLogin()?

Ví dụ browser đăng nhập bằng `portal-web`, nhưng controller cần thêm token của `portal-admin`:

~~~java
mvc.perform(get("/test/clients/admin")
    .with(oidcLogin()
        .clientRegistration(TestRegistrations.web()))
    .with(oauth2Client("portal-admin")
        .principalName("user")
        .clientRegistration(TestRegistrations.admin())
        .accessToken(TestAccessTokens.adminToken())))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.registrationId")
        .value("portal-admin"));
~~~

Trong ví dụ, principal mặc định của `oidcLogin()` thường là `user`. Vì vậy fake ADMIN authorized client cũng cần `principalName("user")`. Nếu test dùng một `OidcUser` tùy biến, hãy đảm bảo `principalName` trùng `Authentication.getName()`.

**Lưu ý:** nếu application repository/manager custom không đọc authorized clients từ HttpSession, cần seed chính store đó; đừng giả định postprocessor tạo token ở mọi backend.

## 15. oauth2Login() — khi không cần OidcUser

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Login;
~~~

Ví dụ:

~~~java
@Test
void currentRegistrationWithOauth2Login() throws Exception {
    mvc.perform(get("/test/clients/current")
            .with(oauth2Login()
                .clientRegistration(TestRegistrations.admin())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId")
            .value("portal-admin"));
}
~~~

`oauth2Login()` tạo mock `OAuth2User`, còn `oidcLogin()` tạo mock `OidcUser`. Cả hai thiết lập `OAuth2AuthenticationToken` và có authorized-client state cho mock request.

### 15.1. Phân biệt từ góc nhìn controller

| Controller cần | Test postprocessor phù hợp |
|---|---|
| Username/authorities bình thường | `user()` hoặc `@WithMockUser` |
| `OAuth2User` / OAuth2 login | `oauth2Login()` |
| `OidcUser` / ID Token claims | `oidcLogin()` |
| Chỉ cần một authorized client cụ thể | `oauth2Client("id")` cộng Authentication phù hợp |
| Browser đăng nhập web nhưng dùng admin authorized client | `oidcLogin(web)` + `oauth2Client(admin)` |

### 15.2. Không dùng jwt() thay vì oauth2Client()

`jwt()` tạo JwtAuthenticationToken cho **Resource Server authentication tests**, không tự tạo authorized client ở **OAuth2 Client repository**.

Đây là hai chức năng khác nhau của Spring Security.

## 16. Test registration ID tường minh khác current login registration

Chạy hai requests:

~~~java
@Test
void explicitWebIgnoresCurrentAdminLoginRegistration()
        throws Exception {
    mvc.perform(get("/test/clients/web")
        .with(oidcLogin()
            .clientRegistration(TestRegistrations.admin()))
        .with(oauth2Client("portal-web")
            .principalName("user")
            .clientRegistration(TestRegistrations.web())
            .accessToken(TestAccessTokens.webToken())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId").value("portal-web"));
}
~~~

`current Authentication` thuộc ADMIN, nhưng annotation explicit yêu cầu WEB; nếu WEB authorized client đã có cho principal đó, resolver dùng WEB. Test như vậy giúp phát hiện code vô tình:

~~~java
((OAuth2AuthenticationToken) authentication)
    .getAuthorizedClientRegistrationId();
~~~

rồi mặc định dùng registration đang login cho tất cả downstream APIs.

### 16.1. Phải kiểm tra authorization ở business layer

Vì user có thể có cả WEB và ADMIN tokens trong store, việc method nhận đúng ADMIN authorized client **không đồng nghĩa user có ROLE_ADMIN ở domain app**.

MockMvc test cần riêng:

- User được phép/không được phép gọi endpoint.
- Registration được chọn nếu endpoint được gọi.
- Downstream Resource Server audience/scopes/permissions.

Không đánh đồng ba assertions.

## 17. Test annotation không chỉ định registration khi có nhiều clients

Controller:

~~~java
@GetMapping("/test/clients/current")
public Map<String, String> current(
    @RegisteredOAuth2AuthorizedClient OAuth2AuthorizedClient client
) {
    return safeView(client);
}
~~~

Test:

~~~java
@Test
void currentFollowsWebLogin() throws Exception {
    mvc.perform(get("/test/clients/current")
        .with(oidcLogin()
            .clientRegistration(TestRegistrations.web())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId").value("portal-web"));
}

@Test
void currentFollowsAdminLogin() throws Exception {
    mvc.perform(get("/test/clients/current")
        .with(oidcLogin()
            .clientRegistration(TestRegistrations.admin())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId").value("portal-admin"));
}
~~~

Khi không có OAuth2AuthenticationToken hoặc resolver không có đủ thông tin lựa chọn, hành vi cụ thể phụ thuộc manager/config. Test **đừng giả định** rằng Spring chọn registration đầu tiên trong YAML.

### 17.1. Cùng provider không giúp phân biệt registrations

~~~text
portal-web.provider=company-oidc
portal-admin.provider=company-oidc
~~~

Thực tế vẫn có hai ClientRegistration độc lập. Provider alias không thể thay câu trả lời cho câu hỏi “authorized client nào?”.

### 17.2. Ưu tiên explicit selection cho endpoint cố định

Nếu Orders endpoint luôn cần WEB token:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-web")
~~~

ít mơ hồ hơn annotation trống, đặc biệt sau khi user đăng nhập lại qua ADMIN registration.

## 18. Principal name: kiểm tra đúng owner của authorized client

Giả sử test:

~~~java
mvc.perform(get("/test/clients/web")
    .with(user("alice"))
    .with(oauth2Client("portal-web")
        .principalName("bob")
        .clientRegistration(TestRegistrations.web())));
~~~

Ứng dụng có Authentication là `alice`, nhưng authorized-client fixture gắn với `bob`. Không nên mong controller lấy token của Bob.

**Expected result phụ thuộc repository/manager:** có thể không tìm thấy authorized client và kích hoạt authorization flow hoặc lỗi. Điều cần test là:

~~~text
Mismatched owner must not silently return Bob's token to Alice.
~~~

### 18.1. Test đúng bằng principalName

~~~java
.with(user("alice"))
.with(oauth2Client("portal-web")
    .principalName("alice")
    .clientRegistration(TestRegistrations.web()))
~~~

Tùy cách custom principal của ứng dụng, `Authentication.getName()` có thể là `sub` hoặc một internal ID. Không mặc định email là stable principal key.

### 18.2. OIDC pairwise subject và account linking

Cùng user tại cùng OP vẫn có thể có pairwise `sub` khác nhau giữa registrations/sectors. Trong test, principal phải phản ánh identity mapping đã được xác minh; không tự gộp tokens vì email giống nhau.

## 19. Test token scopes — scope thuộc token chứ không thuộc annotation

Controller:

~~~java
@GetMapping("/test/clients/web/scopes")
public Set<String> scopes(
    @RegisteredOAuth2AuthorizedClient("portal-web")
    OAuth2AuthorizedClient authorizedClient
) {
    return authorizedClient.getAccessToken().getScopes();
}
~~~

Test:

~~~java
@Test
void webAccessTokenCarriesOrdersRead() throws Exception {
    mvc.perform(get("/test/clients/web/scopes")
        .with(user("alice"))
        .with(oauth2Client("portal-web")
            .principalName("alice")
            .clientRegistration(TestRegistrations.web())
            .accessToken(TestAccessTokens.webToken())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[0]").value("orders.read"));
}
~~~

Trong demo, `TestAccessTokens.webToken()` trả `Set.of("orders.read")` nên có một phần tử. Khi set có nhiều scopes, đừng dựa vào thứ tự vì `Set` không bảo đảm iteration order.

### 19.1. ClientRegistration scopes khác granted token scopes

~~~text
Configured scopes:
  openid profile orders.read

Granted access token scopes:
  orders.read
~~~

Hai tập giá trị không nhất thiết giống nhau vì Authorization Server có thể áp grant/consent/scope policy. Test controller nhìn `authorizedClient.getAccessToken().getScopes()` là test **granted token scopes**, không phải chỉ config scopes.

### 19.2. Token có scope không đủ kiểm chứng Resource Server

Một JWT payload có `scope=orders.read` trong mock không chứng minh Orders API sẽ cho phép. API còn issuer, signature, audience, tenant, ownership và policy. Cần integration test riêng cho Bearer request.

## 20. Test token expiry và refresh bằng cách tách lớp

Nếu cần test manager xử lý token hết hạn:

~~~java
Instant now = Instant.now();
OAuth2AccessToken expired = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "fake-expired-token",
    now.minusSeconds(3600),
    now.minusSeconds(60),
    Set.of("orders.read")
);
~~~

Đừng để test controller annotation vô tình gọi token endpoint thật. Có ba cách:

1. Unit test riêng provider/manager bằng fake token-response client.
2. Mock `OAuth2AuthorizedClientManager` mà argument resolver thực sự sử dụng.
3. Fake HTTP token endpoint trong integration test.

### 20.1. Không coi “resolver được inject” là “refresh thành công”

Resolver có thể trả một authorized client còn hạn mà không gọi AS. Test argument resolution cần chứng minh đúng registration/principal, trong khi refresh test cần chứng minh:

~~~text
Input:
  expired AT, valid RT, correct registration

Expected:
  refresh grant invoked with correct client credentials/RT
  new authorized client persisted
  original principal/registration preserved
~~~

Đây là **mục tiêu test khác**, không cần nhồi mọi thứ vào một MockMvc method.

### 20.2. Refresh token rotation và concurrent tests

Khi nhiều requests dùng cùng authorized client, một refresh token có thể bị rotate. Negative tests cần chứng minh failure cleanup không xóa token mới hơn hoặc token của registration khác.

## 21. Test repository/service với hai registrations

Trong Servlet:

~~~java
OAuth2AuthorizedClientRepository
OAuth2AuthorizedClientService
~~~

khác nhau về phạm vi persistence:

- **Repository**: thường phục vụ web requests, có thể session-based.
- **Service**: application-level authorized clients, ví dụ in-memory/JDBC.

### 21.1. Test load web/admin độc lập

~~~text
Given:
  (portal-web, alice) -> AT-W
  (portal-admin, alice) -> AT-A

When:
  load portal-web for alice
Then:
  return AT-W

When:
  load portal-admin for alice
Then:
  return AT-A
~~~

### 21.2. Test cleanup phạm vi hẹp

~~~text
Remove (portal-web, alice).

Expected:
  (portal-admin, alice) still exists.
  (portal-web, bob) still exists.
~~~

Không xóa tất cả tokens của một issuer chỉ vì WEB token invalid.

### 21.3. Test với Spring Session/JDBC custom storage

Nếu production dùng Redis/JDBC cho authorized clients, `oauth2Client()` cài token giả vào HttpSession **có thể không đúng store** của application. Khi muốn kiểm tra custom persistence, seed chính `OAuth2AuthorizedClientService` hoặc repository tương ứng, với principal và registration IDs chuẩn.

## 22. Test chọn registration theo business use case

Một ứng dụng có:

~~~text
OrdersController:
  always portal-web

AuditController:
  always portal-admin

ReportsJob:
  reports-service with client_credentials
~~~

Với controller annotation tường minh:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-web")
~~~

MockMvc có thể chứng minh controller nhận token WEB.

Nhưng nếu business logic chọn registration dựa trên tenant hoặc endpoint:

~~~java
String registrationId =
    trustedTenantRegistry.registrationFor(authorizedTenant);
~~~

thì selection nằm ở service/manager, **không còn là giá trị động của annotation**. Test bằng fake manager/registry và verify `OAuth2AuthorizeRequest` chứa registration được allowlist.

### 22.1. Không biến annotation value thành HTTP parameter

Không có nghĩa:

~~~text
/api/orders?registrationId=portal-admin
~~~

sẽ thay annotation cố định `@RegisteredOAuth2AuthorizedClient("portal-web")`. Nếu cần dynamic selection, phải viết logic riêng và kiểm tra authorization.

### 22.2. Không dùng client_credentials thay authorization người dùng

Nếu `portal-web` token thiếu quyền, không tự chọn `reports-service` có quyền cao để vượt policy. Unit tests cần từ chối sự thay đổi registration không được phép.

## 23. Test HTTP client thực sự đính đúng Bearer token

Controller được inject `OAuth2AuthorizedClient` có thể truyền nó cho WebClient/RestClient. Ta cần test **outgoing request**:

~~~text
GET /api/orders
Authorization: Bearer fake-access-token-for-web
~~~

và đảm bảo không dùng admin token.

### 23.1. WebClient Servlet integration

Spring Security có:

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction
~~~

cho Servlet + WebClient. Khi đã có `OAuth2AuthorizedClient`:

~~~java
import static org.springframework.security.oauth2.client.web
    .reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction
    .oauth2AuthorizedClient;

String response = webClient.get()
    .uri("https://orders.example.test/api/orders")
    .attributes(oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

Test với fake HTTP server hoặc `ExchangeFunction` có thể capture `Authorization` và assert Bearer token đúng.

### 23.2. Mẫu fake ExchangeFunction

~~~java
AtomicReference<String> authorization = new AtomicReference<>();

ExchangeFunction fakeExchange = request -> {
    authorization.set(
        request.headers().getFirst("Authorization"));
    return Mono.just(ClientResponse.create(HttpStatus.OK)
        .body("ok")
        .build());
};

WebClient webClient = WebClient.builder()
    .exchangeFunction(fakeExchange)
    .build();
~~~

Đây là **fragment test**; cần tích hợp OAuth filter được cấu hình và fake authorized client vào request, hoặc kiểm thử service tự set header nếu muốn isolate transport. Sau request:

~~~java
assertThat(authorization.get())
    .isEqualTo("Bearer fake-access-token-for-web");
~~~

Đừng gửi request tới Internet thật trong unit test, cũng đừng dùng token production.

### 23.3. RestClient (Spring Security 6.4+)

`OAuth2ClientHttpRequestInterceptor` dùng manager; test registration selection thường qua:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver
    .clientRegistrationId;

restClient.get()
    .uri("/api/orders")
    .attributes(clientRegistrationId("portal-web"))
    .retrieve()
    .body(String.class);
~~~

Đây là **một selection mechanism khác** với controller annotation; cần test cả hai khi ứng dụng dùng kết hợp. Có thể dùng `MockRestServiceServer` hoặc custom ClientHttpRequestFactory để assert Bearer request.

## 24. Khi nào dùng @SpringBootTest thay @WebMvcTest?

| Hình thức test | Đánh giá phù hợp |
|---|---|
 `@WebMvcTest` + fake registrations/repository | Test MVC annotation, security filters và response |
 `@SpringBootTest` + `@AutoConfigureMockMvc` | Test wiring của toàn bộ application beans/manager/repositories |
 Unit test service + mock manager | Test dynamic registration selection/permission checks |
 Fake IdP + fake downstream server | Test token exchange/refresh/end-to-end HTTP integration |
 Browser E2E | Test cookies, SameSite, redirects, session across real browser |

### 24.1. Full-context integration test

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OAuth2ClientWiringIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ClientRegistrationRepository registrations;
    @Autowired OAuth2AuthorizedClientRepository authorizedClients;
    // Test methods using test profile/fake IdP fixtures.
}
~~~

**Không dùng live OIDC issuer discovery của production** trong tests mặc định. Khi `issuer-uri` có trong config, framework có thể tải metadata khi tạo ClientRegistration; dùng fake issuer/discovery hoặc explicit endpoint fixtures trong test profile.

### 24.2. Test slice có thể thiếu bean

`@WebMvcTest` chỉ load một phần context; nếu thiếu `OAuth2AuthorizedClientArgumentResolver`, `ClientRegistrationRepository` hoặc manager thì test thất bại trước khi chạy business logic.

Đây là lỗi **test wiring**, không chứng minh production annotation sai.

## 25. MockMvc standaloneSetup: cần resolver và Spring Security

Nếu không dùng Boot web test slice:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new AuthorizedClientProbeController())
    .setCustomArgumentResolvers(
        new OAuth2AuthorizedClientArgumentResolver(manager))
    .apply(springSecurity(securityFilterChain))
    .build();
~~~

Đây là **mẫu ý tưởng**; `manager` và `securityFilterChain` phải được tạo đúng với Spring Security Test API/ứng dụng. Với standalone setup, filter chain/security context/authorized-client repository có thể phải cung cấp thủ công. Không mặc định một `MockMvcBuilders.standaloneSetup(controller)` trần hiểu annotation của Spring Security.

### 25.1. Vì sao full MVC config đơn giản hơn?

Với `@WebMvcTest` và `@Import(OAuth2MvcTestConfig.class)`, Spring MVC và security infrastructure có cơ hội được wire theo cùng cấu hình. Standalone hữu ích cho tests rất nhỏ nhưng dễ quên argument resolver hoặc filter chain.

### 25.2. @WithMockUser không tự đăng ký argument resolver

`@WithMockUser` chỉ chuẩn bị Authentication cho test; resolver vẫn phải được MVC configuration đăng ký. Nếu thấy `IllegalStateException`, `No suitable resolver` hoặc request parameter injection failure, kiểm tra wiring, không chỉ thay mock user.

## 26. Negative test: thiếu authorized client

Giả sử browser đã authenticated nhưng chưa authorize `portal-admin`.

~~~text
Authentication: alice
Repository:
  (portal-web, alice) -> AT-W
  (portal-admin, alice) -> [missing]
~~~

Khi gọi controller:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-admin")
OAuth2AuthorizedClient client
~~~

manager có thể:

- Khởi tạo authorization code flow và redirect nếu có web context/provider phù hợp.
- Trả null hoặc throw exception theo grant/config.
- Dùng một provider chain khác nếu registration là `client_credentials`.

**Không hard-code “thiếu client luôn trả 404/401”** cho mọi hệ thống. Viết test theo **policy mong đợi của ứng dụng**, ví dụ:

~~~text
No authorized client for portal-admin
  => Must not return portal-web's token
  => Must not call Admin API with WEB token
  => Can initiate authorization or return controlled error
~~~

### 26.1. Tránh false success

Nếu test chỉ assert controller trả một string khác null, có thể vô tình chấp nhận fallback token. Nên assert registration ID và downstream Bearer token cụ thể.

### 26.2. Invalid registration ID

Nếu annotation dùng:

~~~java
@RegisteredOAuth2AuthorizedClient("does-not-exist")
~~~

resolver/manager không thể tìm registration. Kết quả cụ thể phụ thuộc exception handling; test phải xác minh **không có authorization thành công và không gọi token endpoint của registration khác**.

## 27. Authentication chưa đăng nhập: 401 hay redirect?

Với SecurityFilterChain:

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated())
.oauth2Login(Customizer.withDefaults())
~~~

request chưa authenticated thường được đưa qua AuthenticationEntryPoint; với browser login flow có thể là redirect đến trang login. Với API JSON chain có thể là 401 theo policy.

~~~java
@Test
void anonymousRequestIsNotAllowed() throws Exception {
    mvc.perform(get("/test/clients/web"))
        .andExpect(status().is3xxRedirection());
}
~~~

Test này **chỉ phù hợp với chain mẫu ở trên**; nếu ứng dụng cấu hình API entry point trả 401, assertion phải là `isUnauthorized()`.

### 27.1. Authentication và authorized client là hai lớp

Nếu request anonymous và có `oauth2Client()` fake session token, security chain vẫn có thể chặn endpoint do thiếu authentication. Không coi authorized client presence là bằng chứng browser authenticated.

### 27.2. Nếu dùng @WithMockUser

`@WithMockUser` có thể vượt authentication gate nhưng không đảm bảo OIDC principal, ID Token claims hoặc authorized-client state. Cần chọn test fixture theo thứ controller thực sự sử dụng.

## 28. 403 và CSRF: tránh nhầm với lỗi registration

Ví dụ controller POST:

~~~java
@PostMapping("/api/orders")
public ResponseEntity<Void> submitOrder(
    @RegisteredOAuth2AuthorizedClient("portal-web")
    OAuth2AuthorizedClient client
) {
    // Business operation...
    return ResponseEntity.accepted().build();
}
~~~

Với Spring Security CSRF protection cho session browser:

~~~java
@Test
void postRequiresCsrf() throws Exception {
    mvc.perform(post("/api/orders")
        .with(oidcLogin()
            .clientRegistration(TestRegistrations.web())))
        .andExpect(status().isForbidden());
}
~~~

Đây có thể là **403 do CSRF**, không phải thiếu OAuth2 token.

Test happy path:

~~~java
mvc.perform(post("/api/orders")
    .with(csrf())
    .with(oidcLogin()
        .clientRegistration(TestRegistrations.web())))
    .andExpect(status().isAccepted());
~~~

### 28.1. Có nên csrf.disable() chỉ cho test dễ pass?

Không. Nếu production dùng session/cookie, CSRF là một cơ chế bảo vệ độc lập. Test cần phản ánh policy production. Không tắt CSRF toàn app để che thiếu CSRF request postprocessor.

### 28.2. Roles và scopes

Một 403 có thể do `@PreAuthorize` hoặc `hasAuthority(...)`, dù authorized client tồn tại. Test phải cung cấp authorities ở Authentication phù hợp và tách biệt với access token scopes khi cần.

## 29. Test registration selection với nhiều principal và tenant

Một hệ thống SaaS:

~~~text
tenant acme:
  registration = portal-acme
  principal = acme-alice

tenant globex:
  registration = portal-globex
  principal = globex-alice
~~~

Hai users có cùng email cũng không được dùng chéo authorized clients.

### 29.1. Test identity key

~~~text
Given:
  (portal-acme, acme-alice) -> AT-A
  (portal-globex, globex-alice) -> AT-G

When:
  ACME request needs portal-acme
Then:
  AT-A used

When:
  GLOBEX request needs portal-globex
Then:
  AT-G used
~~~

### 29.2. Không tin query registrationId

Nếu controller đọc `?registrationId=portal-globex` rồi chọn token của GLOBEX mà không kiểm tra tenant membership, nguy cơ cross-tenant credential use.

Dynamic selection phải dựa trên trusted tenant registry và authorization trước khi gọi manager. Unit test cần chứng minh ACME user không thể chọn GLOBEX registration chỉ bằng đổi URL parameter.

### 29.3. Cùng issuer không đồng nghĩa chung token

Hai registrations có thể cùng provider alias và issuer nhưng khác client IDs/scopes. Assert registration ID **và client ID**, không chỉ issuer URL.

## 30. Kiểm thử registration đang đăng nhập khác authorized client dùng để gọi API

Tình huống:

~~~text
Browser Authentication:
  OAuth2AuthenticationToken.registrationId = portal-web

AuthorizedClientRepository:
  (portal-web, alice) -> AT-W
  (portal-admin, alice) -> AT-A

Controller /api/audit:
  @RegisteredOAuth2AuthorizedClient("portal-admin")
~~~

Test nên xác nhận controller nhận ADMIN authorized client, nhưng authorization riêng phải đảm bảo Alice có quyền gọi audit.

### 30.1. Không dùng getAuthorizedClientRegistrationId() ở mọi nơi

`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` cho biết registration của **current login**, không bảo đảm là client chính xác của mọi downstream API.

Với nhiều registrations, có thể cần explicit selection:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-admin")
~~~

hoặc service manager chọn registration theo trusted business policy.

### 30.2. Test default selection và explicit selection phải độc lập

Không gộp chúng vào một assertion khó hiểu. Viết separate tests:

- Current registration follows OIDC login context.
- Explicit registration remains WEB/ADMIN theo annotation.
- Missing explicit registration không fallback sang current login token.

## 31. MockMvc không xác minh được gì?

MockMvc sử dụng mock HTTP Servlet environment; những thứ **không tự được kiểm chứng** bởi `oauth2Client()` hoặc `oidcLogin()`:

- OP thực sự nhận client ID/secret và redirect URI đúng.
- Authorization code thực sự được đổi lấy token.
- ID Token signature/issuer/audience/nonce được xác minh bằng JWKS thật.
- Browser thực hiện SameSite/Secure/HttpOnly cookie policy.
- Refresh token thực sự được rotate/revoke.
- Resource Server thực sự tin access token.
- Token scopes/audience được AS cấp theo production policy.

**Mock fixtures cho phép cô lập code cần test**, không chứng minh cả Authorization Code/OIDC protocol hoàn chỉnh.

### 31.1. Test layers được đề xuất

~~~text
Unit:
  Dynamic selection, tenant/RBAC, manager invocation.

MockMvc:
  MVC argument resolver, login/authenticated context, session repository.

HTTP integration:
  Fake AS token endpoint, fake Resource Server, Authorization header.

Browser E2E:
  Redirect/callback cookies/state/CSRF across actual origins.
~~~

## 32. Troubleshooting: controller nhận null hoặc không tìm được client

| Triệu chứng | Nguyên nhân phổ biến | Hướng điều tra |
|---|---|---|
| Resolver không nhận annotation | MVC/security argument resolver chưa được đăng ký | Kiểm tra OAuth2 Client MVC config |
| `No bean of type ClientRegistrationRepository` | Test slice thiếu OAuth2 client bean | Import fixture repository |
| Missing authorized client | `oauth2Login()` mock nhưng registration không trùng | Cấu hình `.clientRegistration(...)` |
| Missing authorized client dù oauth2Client được gọi | Test repo khác app repo | Dùng HttpSession repo bean hoặc seed đúng store |
| Client returned với principal=user thay vì alice | Mock principalName mặc định | Gọi `.principalName("alice")` |
| Manager gọi token endpoint trong test | Token expired hoặc chưa có authorized client | Dùng future expiresAt, mock provider/endpoint |
| Test pass nhưng production uses wrong token | Chưa assert client ID/Bearer header | Assert outbound request |
| 302 thay vì expected 200 | Login entry point hoặc authorization redirect | Phân biệt thiếu browser Authentication/client |
| 401 thay vì 302 | API AuthenticationEntryPoint | Assert đúng policy |
| 403 POST | Thiếu CSRF token hoặc role | `.with(csrf())` và authorities |
| 404 wrong path | Controller/filter matcher khác | Kiểm tra endpoints |
| `registrationId=company-oidc` không tồn tại | Dùng provider alias thay registration ID | Sửa thành portal-web |
| Test bị phụ thuộc Internet/IdP | `issuer-uri` discovery | Dùng fake metadata/ClientRegistration |
| Client tests chạy không ổn định | Shared mutable sessions/store giữa tests | Isolate data/clean state |
| Failed refresh làm xóa ADMIN token | Cleanup keyed chỉ theo issuer | Key theo registration+principal |
| Different principal under OIDC | Pairwise sub/custom name attribute | Align trusted principalName |

### 32.1. Cây quyết định debug

~~~text
@RegisteredOAuth2AuthorizedClient test failed
    |
    v
Endpoint đi qua đúng SecurityFilterChain?
    |-- Không -> kiểm tra matcher/MockMvc springSecurity().
    |
    v
Authentication có mặt?
    |-- Không -> user()/oauth2Login()/oidcLogin().
    |
    v
Registration ID được yêu cầu chính xác?
    |-- Không -> annotation hoặc trusted selector.
    |
    v
ClientRegistrationRepository có ID đó?
    |-- Không -> test fixture/profile.
    |
    v
Authorized-client repository/manager cùng store?
    |-- Không -> seed đúng HttpSession/service/custom store.
    |
    v
principalName của client khớp Authentication?
    |-- Không -> điều chỉnh fixture, không dùng user input.
    |
    v
Access token có còn hạn?
    |-- Không -> test refresh riêng.
    |
    v
Controller nhận đúng registration/token?
    |-- Không -> kiểm tra resolver/manager selection.
    |
    v
Downstream API authorization và Bearer header đúng?
~~~

## 33. Anti-pattern khi test annotation

**1. Chỉ dùng @WithMockUser rồi kỳ vọng OAuth2AuthorizedClient tồn tại.** Authentication giả không tự lưu token.

**2. Test bằng một registration duy nhất.** Không phát hiện lỗi chọn client khi ứng dụng có nhiều registrations.

**3. Hai fixture clients có cùng clientId/scopes/token.** Test không phân biệt được sai registration.

**4. Dùng provider alias trong annotation.** `company-oidc` không phải `portal-web`.

**5. Test tokenValue bằng HTTP response production-style.** Dễ tạo endpoint rò Bearer credential.

**6. Dùng token hết hạn cho mọi test resolver.** Manager có thể refresh ngoài mục đích test.

**7. MockMvc không gắn Spring Security filters.** Test không có Authentication context như production.

**8. Test repository khác production mà không biết.** Fake session repository có thể che bug Redis/JDBC.

**9. Chỉ assert HTTP 200.** Không chứng minh registration/client ID/principal đúng.

**10. Gộp current login registration và explicit API registration.** Dễ dùng token sai API.

**11. Bỏ CSRF/security filters để POST test pass.** Không phản ánh policy.

**12. Dùng jwt() thay OAuth2 Client fixture.** Resource Server authentication khác authorized client.

**13. Chấp nhận token của user/tenant khác trong fixture.** Gây false confidence về isolation.

**14. Test gọi production IdP hoặc dùng real client secret.** Không deterministic và có rủi ro bảo mật.

**15. Cho mock manager trả bất kỳ authorized client nào mà không assert request registrationId.** Có thể che lỗi dynamic selection.

## 34. Bài tập thực hành

### Bài 1 — Chọn đúng registration

Controller có:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-web")
OAuth2AuthorizedClient client
~~~

**Hỏi:** Nếu fake repository chỉ chứa `portal-admin`, controller có được dùng ADMIN token không?

**Hướng giải:** Không được fallback ngầm. Cần WEB authorization theo manager policy hoặc controlled error/redirect; test phải reject use of ADMIN token.

### Bài 2 — @WithMockUser có đủ?

~~~java
@WithMockUser(username = "alice")
@Test
void test() { ... }
~~~

**Hỏi:** Đã có OAuth2AuthorizedClient của `portal-web` chưa?

**Hướng giải:** Chưa chắc. `@WithMockUser` chỉ tạo Authentication; thêm `oauth2Client("portal-web")` hoặc seed repository đúng.

### Bài 3 — Dùng oidcLogin()

~~~java
.with(oidcLogin().clientRegistration(TestRegistrations.admin()))
~~~

**Hỏi:** Registration của current OAuth2AuthenticationToken là gì?

**Hướng giải:** `portal-admin`. Nếu annotation không chỉ ID và resolver dựa current login context, test mong current authorized client là ADMIN.

### Bài 4 — Explicit khác current

Browser login qua ADMIN nhưng controller annotation yêu cầu WEB.

**Hỏi:** Nên chọn token nào?

**Hướng giải:** WEB authorized client đã được cấp cho đúng principal theo annotation. Không lấy ADMIN token chỉ vì Authentication hiện hành thuộc ADMIN.

### Bài 5 — Principal mismatch

~~~text
Authentication.name = alice
AuthorizedClient.principalName = bob
~~~

**Hỏi:** Có được trả Bob token cho Alice?

**Hướng giải:** Không. Test expected fail-safe theo repository/manager policy; không cố đổi principal name từ query param.

### Bài 6 — Token scopes

WEB configured scopes có `openid profile orders.read`; access token giả chỉ `orders.read`.

**Hỏi:** Controller dùng `getAccessToken().getScopes()` trả gì?

**Hướng giải:** Granted access token scopes, không nhất thiết trùng configured scopes.

### Bài 7 — Missing HttpSession repo bean

MockMvc dùng `oauth2Client()`, còn MVC resolver dùng custom JDBC repository.

**Hỏi:** Vì sao không tìm được client?

**Hướng giải:** Postprocessor seed token vào session test repo; app resolver lại tìm JDBC. Cần seed correct production store hoặc dùng HttpSession repo bean tương ứng trong test.

### Bài 8 — CSRF và 403

POST endpoint trả 403 dù `oidcLogin()` và token đúng.

**Hỏi:** Kiểm tra gì đầu tiên?

**Hướng giải:** Security rules, CSRF token (`.with(csrf())`), role/authority. Không quy tất cả 403 thành thiếu OAuth token.

### Bài 9 — Multi-tenant

ACME và GLOBEX cùng issuer, khác registration ID, cùng username `alice`.

**Hỏi:** Test isolation tối thiểu?

**Hướng giải:** Fixture token/key khác nhau, membership authorization, đúng registration, không sử dụng chéo access token hoặc resource data.

### Bài 10 — MockMvc chứng minh gì?

Test `oidcLogin()` pass và controller nhận registration ID mong muốn.

**Hỏi:** Đã chứng minh production OP cấp token hợp lệ chưa?

**Hướng giải:** Chưa. MockMvc không trao đổi code, không xác minh chữ ký ID Token/AS hoặc browser cookie; cần fake AS integration hoặc staging E2E riêng.

## 35. Checklist trước khi hoàn tất bộ tests Servlet

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Đúng annotation/argument type? | `@RegisteredOAuth2AuthorizedClient OAuth2AuthorizedClient` |
| Annotation explicit hay implicit? | Test cả behavior tương ứng |
| Registration IDs có duy nhất? | WEB/ADMIN khác nhau |
| Provider alias có bị nhầm? | Không |
| Test ClientRegistration có client IDs riêng? | Có |
| Test fixture tokens khác và còn hạn? | Có ở happy path |
| Test principalName khớp Authentication? | Có |
| MockMvc có Spring Security filters? | Có |
| MVC argument resolver được đăng ký? | Có |
| Test authorized-client repo khớp manager? | Có |
| oauth2Client() dùng cho authorized client state? | Có |
| oauth2Login()/oidcLogin() dùng đúng Authentication? | Có |
| @WithMockUser không bị coi là authorized-client fixture? | Đúng |
| Test web endpoint chọn WEB? | Assert registration ID/client ID |
| Test admin endpoint chọn ADMIN? | Assert registration ID/client ID |
| Test current registration theo login? | Có |
| Test explicit selection khác current? | Có |
| Test missing client không fallback sai? | Có |
| Test user principal isolation? | Có |
| Test tenant registration isolation? | Có nếu multi-tenant |
| Test scopes được cấp? | Có |
| Test expired token/refresh riêng? | Có nếu app dùng refresh |
| Test outgoing Bearer header? | Có khi controller gọi API |
| Test 401/403/CSRF theo security chain? | Có |
| Test setup không gọi IdP production? | Có |
| Không dùng secrets/token thật trong CI? | Có |
| Test data/session được isolate? | Có |
| Browser cookie/E2E tests riêng? | Có nếu cần callback |

## 36. Tài liệu tham khảo

Các tài liệu Spring Security chính thức có ví dụ tương ứng:

- **Testing OAuth 2.0 (Servlet MockMvc)**: `https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html`
- **Authorized Client Features** và annotation resolver: `https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorized-clients.html`
- **Core OAuth2 Client classes**: `https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html`

Khi nâng phiên bản Spring Security, nên đối chiếu API `SecurityMockMvcRequestPostProcessors`, argument resolver và manager wiring trong version dự án đang dùng.

## 37. Tổng kết

`@RegisteredOAuth2AuthorizedClient` giúp Spring MVC inject một `OAuth2AuthorizedClient` theo **registration ID**. Resolver sử dụng `OAuth2AuthorizedClientManager`, nên việc test không chỉ là tạo Authentication mà còn phải đảm bảo **authorized-client repository, registration, principal và token context** đúng.

Trong MockMvc, `oauth2Client("portal-web")` là cách tập trung nhất để đưa fake authorized client vào session; `oauth2Login()` và `oidcLogin()` mô phỏng Authentication và có thể liên kết authorized client tương ứng. `@WithMockUser` chỉ mô phỏng Authentication thông thường, không tự tạo OAuth2 authorized client. Nếu manager dùng custom repository/JDBC, test phải seed **đúng store thực sự được resolver đọc**.

Với ứng dụng nhiều registrations, bài test có giá trị nhất phải chứng minh **WEB token không bị chọn thay ADMIN token, principal Alice không đọc token của Bob, và tenant A không dùng token tenant B**. Assert registration ID, client ID, principal, scopes và outgoing Bearer header khi phù hợp; tách test refresh/consent/IdP protocol khỏi test MVC argument resolution. Đó là cách kiểm thử lựa chọn registration vừa rõ ràng, vừa không làm mất các ranh giới OAuth2/OIDC và authorization.
