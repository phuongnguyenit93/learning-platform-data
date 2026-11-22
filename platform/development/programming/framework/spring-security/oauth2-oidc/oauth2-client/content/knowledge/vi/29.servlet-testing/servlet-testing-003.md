# 29.3. oidcLogin() để mô phỏng người dùng OIDC

## Mục tiêu bài học

Khi kiểm thử ứng dụng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** dùng Servlet/MVC, không phải mọi test đều cần mở trình duyệt, chuyển hướng sang OpenID Provider (OP), nhập mật khẩu rồi đổi authorization code lấy token.

Nếu mục tiêu là kiểm tra **controller hoặc authorization rule sau khi một người dùng đã đăng nhập OIDC**, Spring Security Test cung cấp request post-processor `oidcLogin()` dành cho `MockMvc`.

Ví dụ ngắn nhất:

~~~java
mvc.perform(get("/me").with(oidcLogin()))
        .andExpect(status().isOk());
~~~

`oidcLogin()` đặt một **Authentication giả lập với principal OidcUser** vào ngữ cảnh request. Nó giúp test nhanh nghiệp vụ phụ thuộc OIDC claims, roles và registration mà không cần OpenID Provider thật.

Ranh giới quan trọng: **`oidcLogin()` không thực hiện OIDC Authorization Code flow, không gọi token endpoint và không xác minh chữ ký ID token thật.** Nó kiểm tra hành vi khi OIDC principal đã được giả lập là authenticated.

Sau bài học, bạn có thể:

1. Giải thích mục đích, API và giới hạn của `SecurityMockMvcRequestPostProcessors.oidcLogin()`.
2. Cấu hình `spring-security-test` và `MockMvc` có Spring Security filter chain.
3. Dùng `oidcLogin()` với `@SpringBootTest`/`@AutoConfigureMockMvc` hoặc `@WebMvcTest`.
4. Giả lập subject, issuer, email và những claims trong ID token bằng `idToken(...)`.
5. Đặt UserInfo claims bằng `userInfoToken(...)`.
6. Tạo authorities/roles cụ thể bằng `authorities(...)`.
7. Đưa custom `OidcUser` vào request qua `oidcUser(...)`.
8. Chọn `ClientRegistration` cụ thể khi ứng dụng có nhiều OIDC providers.
9. Test `@AuthenticationPrincipal`, `OAuth2AuthenticationToken` và `SecurityContext`.
10. Test endpoint allowed/denied, method security và CSRF với MockMvc.
11. Phân biệt kiểm thử mapping từ claims sang authorities với kiểm thử endpoint đã nhận authorities.
12. Test tenant membership, ownership và identity theo issuer + subject.
13. Phân biệt `oidcLogin()` với `oauth2Login()`, `jwt()`, `opaqueToken()`, `user()` và `@WithMockUser`.
14. Xác định khi nào phải dùng integration test thật cho `state`, `nonce`, PKCE, callback, issuer/JWKS validation hoặc token refresh.
15. Tránh các test “xanh giả” vì đã tự cấp quyền cho user hoặc vô tình bỏ SecurityFilterChain.

---

## 1. Bài toán thực tế: controller cần OIDC principal

Giả sử Employee Portal có endpoint xem thông tin người dùng hiện tại:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    Profile me(@AuthenticationPrincipal OidcUser user) {
        return new Profile(
                user.getIdToken().getSubject(),
                user.getEmail());
    }

    record Profile(String subject, String email) {}
}
~~~

Trong production, `OidcUser` được tạo sau khi Spring Security hoàn thành các bước OIDC Login.

~~~text
Browser -> Portal -> OpenID Provider
  -> Authorization Request với state
  -> OP xác thực user
  -> Callback với code + state
  -> Portal đổi authorization code lấy token
  -> ID token được xác minh
  -> Tạo OAuth2AuthenticationToken với OidcUser
  -> Controller đọc Authentication
~~~

Nếu chỉ cần xác minh controller trả đúng `subject` và `email`, việc khởi động một OP thật làm test trở nên chậm và khó kiểm soát.

Dùng `oidcLogin()` để **bỏ qua phần giao thức đã được giả lập** và đưa một OIDC principal cụ thể vào request.

### 1.1. Mục tiêu test và công cụ phù hợp

| Câu hỏi | Cách kiểm thử |
|---|---|
| Controller đọc đúng subject/email từ OidcUser? | `oidcLogin()` |
| Endpoint chỉ cho user có ROLE_ADMIN? | `oidcLogin().authorities(...)` |
| Controller hiển thị registration ID đúng? | `oidcLogin().clientRegistration(...)` |
| User thiếu membership tenant bị chặn? | `oidcLogin()` + domain authorization |
| POST có CSRF protection? | `oidcLogin()` + `csrf()` |
| Browser có được chuyển tới đúng OP? | Test authorization endpoint/filter |
| Callback có `state` sai bị chặn? | Login flow integration test |
| ID token sai chữ ký/issuer bị từ chối? | OIDC validation integration test |
| Resource Server từ chối JWT audience sai? | Resource Server JWT tests |
| Refresh token rotation được lưu đúng? | Authorized-client manager/token endpoint integration test |

**Một test OIDC principal không phải một test toàn bộ OIDC Login.**

## 2. `oidcLogin()` nằm ở đâu?

API là static factory method của:

~~~java
org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors
~~~

Static import:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
~~~

Sử dụng trong MockMvc request:

~~~java
mvc.perform(get("/me").with(oidcLogin()));
~~~

Đây là `RequestPostProcessor` của Spring Security Test. Nó tham gia dựng request test để SecurityContext có OIDC authentication giả lập.

### 2.1. Những thành phần được mô phỏng

~~~text
MockMvc request
  -> .with(oidcLogin())
      -> OAuth2AuthenticationToken giả lập
      -> OidcUser giả lập
      -> ID token claims giả
      -> UserInfo claims giả nếu cấu hình
      -> GrantedAuthority giả
      -> ClientRegistration context giả
  -> Spring Security filter chain
  -> MVC Controller / Method Security
  -> HTTP response assertion
~~~

Ở một số helper/version, authorized client test context cũng được chuẩn bị cho request. Không vì thế coi token trong test là access token thật do AS cấp và được xác minh.

### 2.2. Những bước KHÔNG được chạy

`oidcLogin()` không tự:

- Gọi OP authorization endpoint.
- Hiển thị login form hoặc MFA.
- Thực hiện consent flow.
- Sinh và xác minh authorization response thực.
- Đổi code tại token endpoint.
- Tải metadata/JWKS và xác minh chữ ký ID token.
- Thử `nonce` hoặc PKCE verifier với OP.
- Gọi UserInfo endpoint.
- Thực hiện refresh token grant hoặc rotation.
- Thu hồi token tại Authorization Server.

Mọi claims do test thêm đều được **tin như dữ liệu mock** cho request.

### 2.3. Tại sao vẫn cần SecurityFilterChain?

Mục đích của MockMvc security test là để Authentication giả lập đi qua những authorization rules thực tế:

~~~text
authenticated()
hasRole(...)
hasAuthority(...)
@PreAuthorize(...)
CSRF protection
~~~

Nếu bạn tắt filters hoặc chỉ chạy controller trong một setup không có security, nhiều test vẫn nhận HTTP 200 nhưng không chứng minh security rules đang được thực thi.

## 3. Dependency cho kiểm thử Servlet

### 3.1. Maven

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-security-test` nên tương thích với phiên bản Spring Security dùng trong ứng dụng. Dự án dùng Spring Boot BOM thường không cần tự đặt version riêng.

### 3.3. Những class cần chú ý

| Class/API | Package/ý nghĩa |
|---|---|
| `MockMvc` | Spring Test Servlet MVC |
| `oidcLogin()` | Spring Security Test request post-processor |
| `OidcUser` | OIDC principal |
| `OidcIdToken` | ID token object |
| `OidcUserInfo` | UserInfo claims |
| `OAuth2AuthenticationToken` | Authentication sau OAuth2/OIDC Login |
| `ClientRegistration` | OAuth client configuration |
| `SimpleGrantedAuthority` | Authority test |
| `csrf()` | CSRF request post-processor |

## 4. MockMvc với Spring Boot

Hai lựa chọn thường dùng:

- `@SpringBootTest` + `@AutoConfigureMockMvc`: nạp application context rộng.
- `@WebMvcTest`: nạp MVC slice, phù hợp test controller.

### 4.1. Full context test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PortalSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loggedInOidcUserCanReadProfile() throws Exception {
        mvc.perform(get("/me").with(oidcLogin()))
                .andExpect(status().isOk());
    }
}
~~~

Ưu điểm là nạp nhiều thành phần production, bao gồm cấu hình SecurityFilterChain khi được component scan/import phù hợp.

Nhược điểm: context lớn; có thể bị ảnh hưởng bởi DB, messaging hoặc OIDC discovery nếu app khởi tạo tích hợp ngoài.

### 4.2. Controller slice test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsOidcAuthentication() throws Exception {
        mvc.perform(get("/me").with(oidcLogin()))
                .andExpect(status().isOk());
    }
}
~~~

Nếu controller cần service, phải cung cấp test dependency phù hợp version của Spring Boot (mock/test bean). Nếu muốn kiểm tra **production SecurityFilterChain**, có thể cần `@Import(...)` cấu hình security cụ thể.

### 4.3. Không mặc định test slice đã có mọi bean

`@WebMvcTest` có thể không nạp:

- Service implementation ngoài MVC.
- Custom `GrantedAuthoritiesMapper`.
- Một số bean OIDC Client/ClientRegistration tùy cấu hình.
- Method-security proxy ở service nếu service bị mock.
- Persistence/database.

Đây là lựa chọn có chủ đích. Dùng full context khi mục tiêu test cần nhiều lớp.

### 4.4. Tránh gọi OP production khi khởi tạo context

Cấu hình `issuer-uri` có thể dẫn tới metadata discovery khi tạo registration.

Để test độc lập, dùng test configuration với fake `ClientRegistration`, fake issuer endpoints hoặc mock discovery server. Không để unit test tự truy cập OP production.

## 5. Test controller với ID token claims tường minh

Controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    Profile me(@AuthenticationPrincipal OidcUser user) {
        return new Profile(
                user.getIdToken().getSubject(),
                user.getEmail());
    }

    record Profile(String subject, String email) {}
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsSubjectAndEmail() throws Exception {
        mvc.perform(get("/me")
                        .with(oidcLogin()
                                .idToken(token -> token
                                        .claim("sub", "alice-123")
                                        .claim("email",
                                                "alice@example.test"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject")
                        .value("alice-123"))
                .andExpect(jsonPath("$.email")
                        .value("alice@example.test"));
    }
}
~~~

### 5.1. Test xác minh điều gì?

- Controller nhận được OIDC principal.
- `sub` và email được đọc đúng từ dữ liệu test.
- Response JSON chứa giá trị mong muốn.
- Request đi qua security rules tương ứng test context.

### 5.2. Test không xác minh điều gì?

- Alice có thật ở OP.
- Email được xác minh bởi OP.
- ID token có chữ ký hợp lệ.
- Authorization Code callback thành công.
- Portal nhận access token đúng audience cho downstream API.

### 5.3. Không phụ thuộc giá trị mặc định của helper

`oidcLogin()` có test principal/claims mặc định. Đặt claims tường minh khi chúng ảnh hưởng nghiệp vụ, để test dễ hiểu và không phụ thuộc giá trị giả mặc định.

## 6. Tùy chỉnh `idToken(...)`

Tạo ID token claims giả:

~~~java
.with(oidcLogin()
        .idToken(token -> token
                .claim("sub", "alice-123")
                .claim("email", "alice@example.test")
                .claim("email_verified", true)))
~~~

### 6.1. Subject

Nếu code dùng:

~~~java
user.getIdToken().getSubject()
~~~

thì cần test `sub`.

### 6.2. Custom claims

Nếu application dùng:

~~~java
user.getIdToken().getClaimAsString("department")
~~~

test:

~~~java
.with(oidcLogin()
        .idToken(token -> token
                .claim("sub", "alice-123")
                .claim("department", "finance")))
~~~

### 6.3. Issuer và audience

Có thể mô phỏng:

~~~java
.with(oidcLogin()
        .idToken(token -> token
                .claim("iss", "https://login.test.example")
                .claim("sub", "alice-123")
                .claim("aud", java.util.List.of("portal-web"))))
~~~

**Giá trị `iss`/`aud` trong mock không được xác minh bởi JWT decoder thật.**

Nếu đặt `iss=https://untrusted.test`, request vẫn có thể được coi là authenticated vì `oidcLogin()` không tái diễn token validation. Dùng OIDC integration test để kiểm tra logic từ chối issuer sai.

### 6.4. Bảng claims

| Claim | Ý nghĩa | Cần lưu ý trong mock |
|---|---|---|
| `sub` | Subject trong namespace issuer | Không globally unique |
| `iss` | OP issuer | `oidcLogin()` không verify issuer |
| `aud` | RP audience | Không phải API access-token audience |
| `email` | Email | Có thể absent |
| `email_verified` | Email verified theo OP | Không tự suy từ email |
| `preferred_username` | Tên hiển thị | Không nhất thiết stable identity |
| `groups` | Custom group claim | Không tự chuyển thành Spring authorities |
| `auth_time` | Authentication time | Khi app kiểm tra freshness |
| `acr`/`amr` | Authentication context/method | Provider-specific semantics |

## 7. `userInfoToken(...)`: mô phỏng UserInfo

Đôi khi OP cung cấp email, name hoặc profile ở UserInfo thay vì ID token.

~~~java
mvc.perform(get("/me")
                .with(oidcLogin()
                        .idToken(token -> token
                                .claim("sub", "alice-123"))
                        .userInfoToken(info -> info
                                .claim("email", "alice@example.test")
                                .claim("name", "Alice Example"))))
        .andExpect(status().isOk());
~~~

### 7.1. Nó có gọi HTTP UserInfo endpoint không?

Không. `userInfoToken(...)` dựng `OidcUserInfo` giả để principal chứa UserInfo claims.

### 7.2. Khi code đọc `OidcUser.getEmail()`

`OidcUser` có thể cung cấp claims kết hợp từ ID token và UserInfo. Test nên đặt dữ liệu tại nguồn phù hợp production OP.

Nếu một claim có ở cả ID token và UserInfo, cần test semantics/precedence theo implementation thực tế nếu logic dựa vào nguồn nào thắng.

### 7.3. UserInfo khác OAuth access token

`OidcUserInfo` là dữ liệu claims. Nó không phải access token và không thể dùng làm Bearer header.

### 7.4. Test UserInfo HTTP flow ở nơi khác

Nếu muốn chắc chắn app xử lý 401/500 từ UserInfo endpoint, cần authentication integration test có mock OP/UserInfo HTTP endpoint.

## 8. `authorities(...)`: cho principal quyền cụ thể

Ví dụ SecurityFilterChain:

~~~java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
~~~

Trong test:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

mvc.perform(get("/admin/dashboard")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority("ROLE_ADMIN"))))
        .andExpect(status().isOk());
~~~

### 8.1. Negative test

~~~java
mvc.perform(get("/admin/dashboard")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority("ROLE_VIEWER"))))
        .andExpect(status().isForbidden());
~~~

### 8.2. `authorities(...)` không chạy custom mapper

Nếu production mapping là:

~~~text
OIDC groups=[finance-admins]
  -> GrantedAuthoritiesMapper
  -> ROLE_FINANCE_ADMIN
~~~

thì:

~~~java
.with(oidcLogin()
        .authorities(
                new SimpleGrantedAuthority("ROLE_FINANCE_ADMIN")))
~~~

chỉ nói rằng user **đã có** authority. Test không chứng minh mapper từ OP groups chạy đúng.

### 8.3. Phân biệt role và scope

~~~text
ROLE_ADMIN
ROLE_VIEWER
SCOPE_orders.read
SCOPE_orders.write
~~~

`hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN`; `hasAuthority("SCOPE_orders.read")` kiểm tra đúng authority string.

Một mock OIDC principal có `SCOPE_orders.read` không tự chứng minh Orders API chấp nhận một access token hợp lệ.

### 8.4. Test cả đủ quyền và thiếu quyền

Không tạo mọi fake user với ROLE_ADMIN mặc định. Nếu mọi test được cấp quyền rộng, các regression về authorization rất dễ bị bỏ sót.

## 9. Truyền custom `OidcUser` với `oidcUser(...)`

Khi cần token, UserInfo và authorities đồng bộ hoặc custom principal implementation, có thể tự dựng `OidcUser`.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

final class OidcTestUsers {

    private OidcTestUsers() {}

    static OidcUser alice() {
        Instant now =
                Instant.parse("2026-11-16T09:00:00Z");

        OidcIdToken idToken = new OidcIdToken(
                "fake-id-token",
                now,
                now.plusSeconds(3600),
                Map.of(
                        "iss", "https://login.test.example",
                        "sub", "alice-123",
                        "aud", List.of("portal-web")));

        OidcUserInfo userInfo = new OidcUserInfo(
                Map.of(
                        "sub", "alice-123",
                        "email", "alice@example.test"));

        return new DefaultOidcUser(
                List.of(new SimpleGrantedAuthority("ROLE_USER")),
                idToken,
                userInfo,
                "sub");
    }
}
~~~

Dùng trong MockMvc:

~~~java
mvc.perform(get("/me")
                .with(oidcLogin()
                        .oidcUser(OidcTestUsers.alice())))
        .andExpect(status().isOk());
~~~

### 9.1. Khi nào cách này phù hợp?

- Có custom OIDC user wrapper.
- Có UserInfo và ID token claims cần kết hợp.
- Test principal name attribute.
- Cần fixture phức tạp dùng lại nhiều nơi.
- Muốn kiểm tra controller xử lý authorities cụ thể.

### 9.2. Không dùng token thật

`fake-id-token` là giá trị giả. Không copy ID token/access token production vào source test.

### 9.3. Expiry trong fixture không chứng minh validation

`oidcLogin()` không kiểm tra token cryptographically, nên một ID token object có expiry đã qua có thể vẫn được đưa vào Authentication. Kiểm tra expiry thật tại OIDC authentication/JWT decoder boundary.

## 10. Kiểm thử nhiều ClientRegistration

Ứng dụng có thể hỗ trợ:

~~~text
corporate-login
partner-login
~~~

và controller đọc:

~~~java
authentication.getAuthorizedClientRegistrationId()
~~~

Khi muốn test rõ registration, dùng `clientRegistration(...)`.

### 10.1. Registration fixture

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;

final class OidcTestRegistrations {

    private OidcTestRegistrations() {}

    static ClientRegistration corporate() {
        return ClientRegistration
                .withRegistrationId("corporate-login")
                .clientId("portal-test-client")
                .clientSecret("test-only-secret")
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .authorizationUri(
                        "https://login.test.example/authorize")
                .tokenUri(
                        "https://login.test.example/token")
                .jwkSetUri(
                        "https://login.test.example/jwks")
                .issuerUri("https://login.test.example")
                .scope("openid", "profile")
                .clientName("Corporate Test")
                .build();
    }
}
~~~

Mọi URLs ở đây là fixtures và không được sử dụng để gọi OP production.

### 10.2. Gắn registration

~~~java
mvc.perform(get("/me/provider")
                .with(oidcLogin()
                        .clientRegistration(
                                OidcTestRegistrations.corporate())))
        .andExpect(status().isOk());
~~~

### 10.3. Không xem clientRegistration là verified identity

`clientRegistration(...)` cho test biết đang mô phỏng registration nào. Nó không làm Spring Security kiểm tra issuer của ID token giả với issuer của registration.

### 10.4. Hai registrations cùng issuer

Hai OAuth clients có thể dùng chung một issuer nhưng khác client ID/scopes. Test cần xác định registration ID chính xác khi logic phụ thuộc registration.

## 11. Đọc `OAuth2AuthenticationToken`

Controller:

~~~java
import org.springframework.security.oauth2.client.authentication
        .OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProviderController {

    @GetMapping("/me/provider")
    ProviderInfo provider(
            OAuth2AuthenticationToken authentication) {

        return new ProviderInfo(
                authentication.getAuthorizedClientRegistrationId(),
                authentication.getName());
    }

    record ProviderInfo(
            String registrationId,
            String principalName) {}
}
~~~

Test:

~~~java
mvc.perform(get("/me/provider")
                .with(oidcLogin()
                        .clientRegistration(
                                OidcTestRegistrations.corporate())
                        .idToken(token -> token
                                .claim("sub", "alice-123"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId")
                .value("corporate-login"));
~~~

### 11.1. Registration không phải role

`registrationId=corporate-login` không tự tạo `ROLE_ADMIN`. Authentication của user và authorization theo domain là hai tầng.

### 11.2. Subject không phải email

`authentication.getName()` có thể là subject hoặc principal name attribute được cấu hình. Không mặc định nó là email.

### 11.3. Không lấy registration từ query tùy ý

Production nên lấy registration từ `OAuth2AuthenticationToken` đã được tạo bởi Spring Security, không tin `?registrationId=...` như bằng chứng login thành công.

## 12. Kiểm thử endpoint allowed và denied

Giả sử:

~~~java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/me").authenticated()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll())
~~~

### 12.1. User authenticated vào `/me`

~~~java
mvc.perform(get("/me").with(oidcLogin()))
        .andExpect(status().isOk());
~~~

### 12.2. Admin được phép

~~~java
mvc.perform(get("/admin/dashboard")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority("ROLE_ADMIN"))))
        .andExpect(status().isOk());
~~~

### 12.3. Viewer bị từ chối

~~~java
mvc.perform(get("/admin/dashboard")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority("ROLE_VIEWER"))))
        .andExpect(status().isForbidden());
~~~

### 12.4. Anonymous request

~~~java
mvc.perform(get("/admin/dashboard"))
        .andExpect(result -> {
            int status = result.getResponse().getStatus();
            org.assertj.core.api.Assertions.assertThat(status)
                    .isIn(302, 401);
        });
~~~

Đoạn anonymous chỉ minh họa vì app browser thường redirect login còn API bearer-only thường trả 401. **Test thực nên assert chính xác status/Location theo SecurityFilterChain của dự án**, không giữ expectation lỏng như ví dụ.

### 12.5. Unknown endpoints

Nếu có `anyRequest().denyAll()`, cần test một route được map nhưng không allowlist. Không nhầm 404 do MVC không có handler với 403 do security authorization.

## 13. Method Security và `@PreAuthorize`

Ví dụ service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportsService {

    @PreAuthorize(
            "hasAuthority('ROLE_REPORT_READER')")
    public String report() {
        return "report-ok";
    }
}
~~~

Controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {

    private final ReportsService service;

    public ReportsController(ReportsService service) {
        this.service = service;
    }

    @GetMapping("/reports")
    String report() {
        return service.report();
    }
}
~~~

### 13.1. Cho phép

~~~java
mvc.perform(get("/reports")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "ROLE_REPORT_READER"))))
        .andExpect(status().isOk());
~~~

### 13.2. Từ chối

~~~java
mvc.perform(get("/reports")
                .with(oidcLogin()
                        .authorities(
                                new SimpleGrantedAuthority("ROLE_USER"))))
        .andExpect(status().isForbidden());
~~~

### 13.3. Cần bật Method Security

`@EnableMethodSecurity` phải hoạt động trong context test. Nếu dùng `@WebMvcTest` và mock `ReportsService`, method interceptor trên service thật có thể không chạy.

**Một request 200 khi gọi mock service không chứng minh @PreAuthorize của service đã được thực thi.**

### 13.4. Test đúng tầng

- Controller security rules: MockMvc với SecurityFilterChain.
- Method security trên service: context có proxied service thật.
- Business authorization: service/domain tests với identity/roles cụ thể.

## 14. Claims không tự chuyển thành authorities

Production có thể map:

~~~text
ID token/UserInfo:
  groups=["finance-admins"]

Custom GrantedAuthoritiesMapper:
  finance-admins -> ROLE_FINANCE_ADMIN
~~~

Nếu test:

~~~java
.with(oidcLogin()
        .idToken(token -> token
                .claim("groups",
                        java.util.List.of("finance-admins"))))
~~~

không nên kỳ vọng Spring Security Test tự chạy toàn bộ custom OIDC user loading/GrantedAuthoritiesMapper pipeline.

### 14.1. Test mapping riêng

Kiểm tra component mapping thật:

~~~text
Input: validated OIDC claims, issuer
Mapping: finance-admins -> ROLE_FINANCE_ADMIN
Output: granted ROLE_FINANCE_ADMIN
~~~

### 14.2. Test endpoint riêng

~~~java
.with(oidcLogin()
        .authorities(
                new SimpleGrantedAuthority("ROLE_FINANCE_ADMIN")))
~~~

Đây là test authorization endpoint **sau khi mapping**.

### 14.3. Cần integration test nếu muốn kiểm tra từ OP tới Role

Mock OP ID token/UserInfo theo issuer-specific policy, chạy OIDC authentication flow và xác nhận SecurityContext authorities thật sau login.

### 14.4. Nguy cơ test “xanh giả”

Nếu tự cấp ROLE_ADMIN ở mọi test, logic mapping role có thể sai nhưng endpoint test vẫn xanh. Phải phân biệt phạm vi test.

## 15. CSRF khi test POST/PUT/DELETE

Portal dùng browser cookie có CSRF threat model khác bearer-only API. OIDC authentication không tự vô hiệu CSRF protection.

### 15.1. POST authenticated nhưng không có CSRF token

~~~java
mvc.perform(post("/profile/update")
                .with(oidcLogin())
                .contentType("application/json")
                .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isForbidden());
~~~

Giả sử endpoint tồn tại và SecurityFilterChain bật CSRF.

### 15.2. POST với CSRF token hợp lệ

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;

mvc.perform(post("/profile/update")
                .with(oidcLogin())
                .with(csrf())
                .contentType("application/json")
                .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isOk());
~~~

Kết quả `200` giả định controller, validation và domain policy đều cho phép.

### 15.3. Đừng bỏ CSRF để test hết 403

Nếu POST fail:

1. Có OIDC Authentication chưa?
2. Authorities có đủ không?
3. Có CSRF token chưa?
4. Endpoint có validation/business denial không?
5. SecurityFilterChain đang dùng có đúng không?

### 15.4. OAuth `state` không thay CSRF token của app

`state` ràng buộc callback trong OAuth flow. Nó không thay CSRF protection cho mọi POST sử dụng session cookie.

## 16. Request-scoped authentication và session

`with(oidcLogin())` tạo Authentication cho **request MockMvc đó**.

~~~java
mvc.perform(get("/me").with(oidcLogin()));
mvc.perform(get("/me")); // Không mặc định còn đăng nhập
~~~

### 16.1. Test hai requests có session

Nếu cần mô phỏng trình duyệt giữ session qua nhiều requests, dùng `MockHttpSession` và cơ chế lưu/truy xuất SecurityContext phù hợp với app.

Không coi post-processor là giải pháp tự động kiểm thử toàn bộ session lifecycle.

### 16.2. Test logout/session fixation

Logout, session invalidation, session fixation protection và SSO cookie behavior cần test với flow/session setup đúng tầng.

### 16.3. Test unauthorized request

Gửi request không `oidcLogin()`, kiểm tra browser login redirect hoặc 401 theo contract.

### 16.4. Không gắn authenticated user cho toàn test suite

Nếu dùng default request customization luôn `oidcLogin()`, anonymous tests sẽ không còn ý nghĩa.

## 17. Helpers cho nhiều test users

Fixture:

~~~java
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;

final class OidcTestRequests {

    private OidcTestRequests() {}

    static RequestPostProcessor loginAs(String subject) {
        return oidcLogin()
                .idToken(token -> token.claim("sub", subject));
    }
}
~~~

Dùng:

~~~java
mvc.perform(get("/me")
                .with(OidcTestRequests.loginAs("alice-123")))
        .andExpect(status().isOk());

mvc.perform(get("/me")
                .with(OidcTestRequests.loginAs("bob-456")))
        .andExpect(status().isOk());
~~~

### 17.1. Mỗi user cần identity rõ

Không dùng một ID token giả mặc định rồi test ownership giữa Alice/Bob mà không đổi `sub`.

### 17.2. Nhiều issuer

Nếu OP khác nhau cùng phát `sub=user-123`, ứng dụng phải phân biệt identity bằng `iss` + `sub` hoặc internal user mapping.

~~~java
.with(oidcLogin()
        .idToken(token -> token
                .claim("iss", "https://partner.test.example")
                .claim("sub", "user-123")))
~~~

Đây vẫn chỉ là fake identity claims, không phải issuer validation.

### 17.3. Không dùng email làm identity duy nhất

Email có thể thay đổi hoặc chưa được xác minh. Test identity/ownership nên dựa vào stable identity key của hệ thống.

## 18. Tenant membership và object ownership

Một user có thể OIDC login hợp lệ nhưng không thuộc tenant được yêu cầu.

Ví dụ:

~~~text
OIDC principal:
  issuer = company-op
  sub = alice-123

Membership:
  alice-123 thuộc Acme
  alice-123 không thuộc Globex
~~~

### 18.1. Các test cần có

| Trường hợp | Kết quả |
|---|---|
| Alice thuộc Acme, truy cập Acme | Allow nếu đủ quyền |
| Alice thuộc Acme, truy cập Globex | Deny |
| Alice đã bị revoke membership | Deny |
| Alice gọi order của Bob | Deny |
| Hai issuers có cùng sub | Không tự merge |
| Token claims có `tid=globex` nhưng membership không cho phép | Deny |

### 18.2. Dùng domain service thật hoặc mock có ý nghĩa

Nếu controller gọi mocked service trả 200 cho mọi principal, test không chứng minh tenant/owner authorization.

Khi cần test owner policy, dùng service thực hoặc stub được cấu hình phản ánh các điều kiện ownership.

### 18.3. Không đồng nhất OIDC login với domain permission

`oidcLogin()` giúp làm cho request authenticated. Nó không tự biết Alice được xem order nào.

### 18.4. Chấp nhận 403 hoặc 404 theo contract

Một số API trả 404 thay vì 403 để tránh lộ tài nguyên tồn tại. Test phải phản ánh đúng policy và bảo đảm dữ liệu không bị trả trái quyền.

## 19. `@AuthenticationPrincipal` và Authentication

Trong controller, có thể đọc principal theo nhiều cách.

### 19.1. `@AuthenticationPrincipal OidcUser`

~~~java
@GetMapping("/me/subject")
String subject(@AuthenticationPrincipal OidcUser user) {
    return user.getIdToken().getSubject();
}
~~~

Dùng `oidcLogin().idToken(...)` để test.

### 19.2. `Authentication`

~~~java
@GetMapping("/me/name")
String name(Authentication authentication) {
    return authentication.getName();
}
~~~

`getName()` không mặc định là email. Nó phụ thuộc principal name attribute, thường là subject trong OIDC.

### 19.3. `OAuth2AuthenticationToken`

~~~java
@GetMapping("/me/registration")
String registration(OAuth2AuthenticationToken auth) {
    return auth.getAuthorizedClientRegistrationId();
}
~~~

Dùng `oidcLogin().clientRegistration(...)` để test.

### 19.4. `SecurityContextHolder`

Trong Servlet security filter chain, SecurityContext chứa Authentication trong request thread. `oidcLogin()` giúp test controller/service đọc ngữ cảnh này.

Không lưu Authentication vào biến static/singleton khiến user session A ảnh hưởng user B.

## 20. `oidcLogin()` và `OAuth2AuthorizedClient`

OIDC Login production có thể tạo:

~~~text
OAuth2AuthenticationToken:
  User đã xác thực tại Portal.

OAuth2AuthorizedClient:
  ClientRegistration + access token + refresh token (nếu có).
~~~

### 20.1. Controller chỉ cần OidcUser

Dùng `oidcLogin()` rất phù hợp.

### 20.2. Controller dùng `@RegisteredOAuth2AuthorizedClient`

Nếu endpoint cần access token để gọi downstream API, test còn phải kiểm tra:

- Authorized client test setup.
- Repository/service/manager configuration.
- Token value được gắn vào đúng outbound API request.
- Không dùng ID token hoặc refresh token làm Bearer access token.
- 401/403 và refresh handling.

Helper `oidcLogin()` không thay các test outbound OAuth2 Client này.

### 20.3. Test authorized client riêng

Dùng token fixtures và mock HTTP client/token endpoint khi cần. Một mock principal có claim `sub` đúng không bảo đảm access token được cấp đúng audience.

### 20.4. Không test refresh bằng `oidcLogin()`

Refresh token grant, rotation, saving new refresh token và concurrency cần component/integration tests với authorized-client manager và fake AS token endpoint.

## 21. So sánh các Spring Security Test helpers

| Helper | Authentication mô phỏng | Dùng cho |
|---|---|---|
| `oidcLogin()` | OIDC Login, `OidcUser` | Portal/RP sau OIDC Login |
| `oauth2Login()` | OAuth2 Login, `OAuth2User` | OAuth2-only provider hoặc non-OIDC principal |
| `jwt()` | Bearer JWT Authentication | Resource Server JWT API |
| `opaqueToken()` | Opaque Bearer Authentication | Resource Server opaque API |
| `user("alice")` | Username/password Authentication | Form-login style tests |
| `@WithMockUser` | Mock user SecurityContext | Role checks không cần OIDC claims |
| `authentication(...)` | Authentication tùy biến | Custom auth scenarios |

### 21.1. `oidcLogin()` vs `oauth2Login()`

Khi controller cần `OidcUser.getIdToken()`, dùng `oidcLogin()`.

Nếu ứng dụng OAuth2-only Login dựa trên UserInfo không có ID token, `oauth2Login()` mô phỏng `OAuth2User` thích hợp hơn.

### 21.2. `oidcLogin()` vs `jwt()`

`oidcLogin()` là **browser login principal ở OAuth2/OIDC Client**.

`jwt()` là **incoming Bearer Authentication ở Resource Server**.

Không dùng `oidcLogin()` để chứng minh API đã xác minh JWT access token.

### 21.3. `@WithMockUser`

Dùng `@WithMockUser` nhanh cho authorization rule đơn giản, nhưng nó không mặc định tạo OIDC ID token, UserInfo hoặc registration ID.

### 21.4. `jwt()` cũng không thực hiện signature validation thật

`jwt()` giúp test Resource Server authorization sau khi JWT đã được giả lập là authenticated. Muốn test chữ ký/issuer/audience cần decoder/integration tests thực.

## 22. Ví dụ Resource Server test dùng `jwt()`

Nếu Orders API bảo vệ bằng:

~~~java
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
~~~

test có thể dùng:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

mvc.perform(get("/api/orders")
                .with(jwt()
                        .jwt(token -> token
                                .claim("sub", "alice-123"))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_orders.read"))))
        .andExpect(status().isOk());
~~~

### 22.1. Hai SecurityContexts khác nhau

~~~text
Portal OIDC Client:
  OAuth2AuthenticationToken
  principal = OidcUser

Orders API Resource Server:
  JwtAuthenticationToken
  principal = Jwt
~~~

### 22.2. Access token audience

`jwt()` trong test không chứng minh production JwtDecoder từ chối token `aud=billing-api`. Test decoder/integration riêng để xác minh audience validation đúng.

### 22.3. Không gửi ID token sang API

ID token dành cho Relying Party, còn Resource Server cần OAuth access token hợp lệ theo audience/scope/API contract.

## 23. Những giới hạn của `oidcLogin()` cần ghi nhớ

| Điều muốn kiểm tra | `oidcLogin()` đủ không? | Gợi ý |
|---|---|---|
| Controller lấy OidcUser claims | Có | MockMvc |
| Endpoint check role/authority | Có, nếu filter/method security chạy | MockMvc + authorities |
| Membership/owner | Có thể, nếu domain logic chạy | Domain integration |
| Custom role mapping của OIDC service | Không tự chạy | Test mapper/authentication pipeline |
| Authorization Request redirect URI | Không | OAuth2 Login filter test |
| State correlation | Không | Callback integration |
| PKCE challenge/verifier | Không | Authorization Code integration |
| OIDC nonce | Không | OIDC authentication integration |
| ID token signature/JWKS | Không | Test OP/JWT validation |
| Issuer/audience validation thật | Không | OIDC/JWT decoder integration |
| HTTP UserInfo request | Không | Test user service + mock OP |
| Token refresh/save/rotation | Không | Authorized client manager tests |
| RP-Initiated Logout | Không | Logout protocol integration |
| Outbound API Authorization header | Không tự đủ | HTTP client/token store test |

## 24. Khi nào cần OIDC Login integration test?

Một application có thể có hàng chục controller tests bằng `oidcLogin()` và một số tests sâu hơn cho login flow.

### 24.1. Redirect

Kiểm tra `/oauth2/authorization/{registrationId}` trả redirect đến đúng OP với `client_id`, `scope`, `redirect_uri` và `state`.

### 24.2. Callback

Dùng Authorization Request repository và fake AS:

- State đúng cho request ban đầu → tiếp tục.
- State thiếu/sai/đã dùng → reject.
- Code sai/đã dùng → token endpoint error.
- Callback registration/issuer mismatch → reject theo validation.

### 24.3. ID token validation

Dùng test JWKS/OP:

- Signature sai.
- Issuer sai.
- Audience không chứa client ID phù hợp.
- Expired token.
- Nonce mismatch khi áp dụng.
- Claims không đáp ứng OIDC profile.

### 24.4. UserInfo

Test UserInfo endpoint trả 401/500, claims không đủ hoặc user-name attribute mapping sai.

### 24.5. Token lifecycle

Kiểm tra save/refresh/remove authorized client, invalid_grant, logout và rotation theo AS policy.

**Không gọi OP production để thực hiện các negative/security tests.** Dùng mock server/test OP và fake credentials.

## 25. Tự dựng MockMvc thủ công

Khi không dùng `@AutoConfigureMockMvc`, có thể sử dụng:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup
        .SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.setup
        .MockMvcBuilders.webAppContextSetup;

class ManualMockMvcTest {

    @Autowired
    WebApplicationContext context;

    MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = webAppContextSetup(context)
                .apply(springSecurity())
                .build();
    }
}
~~~

Test class còn cần Spring Test context setup phù hợp để inject `WebApplicationContext`.

### 25.1. Tại sao `springSecurity()` quan trọng?

Nó gắn `FilterChainProxy`/security context test integration với MockMvc. Nếu bỏ cấu hình này, request có thể không được filter chain xử lý như production.

### 25.2. `standaloneSetup(...)`

`MockMvcBuilders.standaloneSetup(controller)` không tự nạp SecurityFilterChain từ application context. Chỉ dùng nếu mục tiêu là test MVC thuần hoặc đã chủ động gắn security configuration thích hợp.

### 25.3. Không sửa lỗi bằng cách tắt filters

Nếu MockMvc test bị lỗi do thiếu security bean, hãy xác định bean cần cung cấp. Tắt filters để test qua sẽ làm security assertions vô giá trị.

## 26. Tổ chức fixtures tránh false positives

Một helper có thể tạo OIDC request theo principal:

~~~java
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;

final class OidcFixtures {

    private OidcFixtures() {}

    static RequestPostProcessor alice() {
        return oidcLogin()
                .idToken(token -> token
                        .claim("sub", "alice-123")
                        .claim("email", "alice@example.test"));
    }

    static RequestPostProcessor admin() {
        return oidcLogin()
                .idToken(token -> token
                        .claim("sub", "admin-123"))
                .authorities(
                        new SimpleGrantedAuthority("ROLE_ADMIN"));
    }
}
~~~

### 26.1. Tên fixture theo use case

Nên có `viewer()`, `admin()`, `tenantMember()`, `tenantNonMember()` để test rõ.

### 26.2. Không cấp ROLE_ADMIN mặc định

Nếu tất cả mock users đều là admin, test endpoint security thường chỉ chứng minh happy path.

### 26.3. Không dùng production tokens

ID token trong test nên là fake data. Không sao chép credential thật từ environment production.

### 26.4. Tách test role mapping và endpoint rules

Một fixture có ROLE_ADMIN chỉ kiểm tra endpoint sau mapping; role mapper từ ID token claims cần test riêng.

## 27. Ma trận kiểm thử Servlet

| Nhóm | Tình huống | Kỳ vọng |
|---|---|---|
| Principal | `oidcLogin()` subject Alice | Controller đọc Alice |
| Claims | ID token có email | JSON response đúng |
| UserInfo | Email từ UserInfo | Principal getter đúng |
| Registration | `corporate-login` | Registration ID đúng |
| Authorities | ROLE_ADMIN | Admin route allowed |
| Authorities | ROLE_VIEWER | Admin route denied |
| Anonymous | Không oidcLogin | 302/401 theo app |
| CSRF | POST OIDC user thiếu csrf | 403 |
| CSRF | POST + `csrf()` | Được xử lý nếu có quyền |
| Method security | Đủ authority | Proxy cho phép |
| Method security | Thiếu authority | Proxy từ chối |
| Tenant | Alice thuộc Acme | Allow đúng tài nguyên |
| Tenant | Alice không thuộc Globex | Deny |
| Owner | Bob gọi order của Alice | Deny |
| OIDC role mapping | Group → role | Test mapper thực |
| API JWT | `jwt()` và scope | API auth rules |
| Actual ID token | Issuer/signature sai | Integration reject |
| Authorization callback | State/nonce sai | Login integration reject |
| Outbound token | Access token giả | Header/host đúng |
| Session | Hai requests | Session state đúng thiết kế |

## 28. Troubleshooting

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Không tìm thấy `oidcLogin()` | Thiếu spring-security-test/import | Bổ sung dependency/static import |
| `OidcUser` null | MockMvc SecurityContext chưa tích hợp | Giữ Spring Security filters |
| GET 403 dù có oidcLogin | Thiếu authority hoặc method policy | Xem roles/rules |
| POST 403 | Thiếu CSRF hoặc authority | Thử `csrf()` và kiểm tra rules |
| Có groups claim nhưng không có ROLE_ADMIN | Claim không tự map authorities | Test mapper riêng |
| Test ROLE_ADMIN xanh nhưng production mapping sai | Test cấp authority trực tiếp | Test OIDC authentication pipeline |
| Registration ID không đúng | Default registration | Dùng `clientRegistration(...)` |
| Controller không nạp custom SecurityFilterChain | `@WebMvcTest` slice | Import security configuration phù hợp |
| Context gọi OP production | issuer discovery | Test ClientRegistration/mock metadata |
| `@PreAuthorize` không được áp | Method security chưa bật hoặc service mock | Test proxied service thật |
| State sai mà test vẫn 200 | `oidcLogin()` bypass flow | Test callback/filter integration |
| ID token issuer sai vẫn được chấp nhận | Mock principal không verify token | Test JWT/OIDC validation |
| API test dùng oidcLogin | Nhầm Client với Resource Server | Dùng `jwt()`/`opaqueToken()` |
| Hai requests không giữ auth | Post-processor theo request | Dùng MockHttpSession đúng |
| Email xuất hiện sai nguồn | ID token/UserInfo không như OP | Test source/claims |
| Browser redirect thay vì 401 | Login entry point | Kiểm tra SecurityFilterChain |
| Token bị log | HTTP debug/test fixture | Fake tokens và redaction |

## 29. Những hiểu nhầm phổ biến

**“`oidcLogin()` kiểm thử OIDC Login thật.”**

Không. Nó mô phỏng người dùng đã đăng nhập cho request.

**“`oidcLogin()` xác minh ID token chữ ký đúng.”**

Không. Claims do test dựng không qua decoder thật.

**“Thêm `groups=admins` là user có ROLE_ADMIN.”**

Không tự động. Cần custom role mapper khi production có logic này.

**“`oidcLogin()` làm state/PKCE/nonce test xanh.”**

Không. Các bước callback cần integration test riêng.

**“`@WithMockUser` giống `oidcLogin()`.”**

Không. MockUser mặc định không có OidcUser/ID token/registration.

**“`jwt()` và `oidcLogin()` dùng thay nhau được.”**

Không. Một helper cho Resource Server JWT, helper kia cho OIDC Client Login.

**“User đã login thì POST không cần CSRF.”**

Không. Browser cookie-backed session vẫn cần CSRF protection.

**“`@WebMvcTest` luôn chạy mọi @PreAuthorize ở service.”**

Không. Service có thể không được nạp hoặc bị mock.

**“Một test oidcLogin đã chứng minh access token refresh được.”**

Không. Refresh/token manager cần test riêng.

**“OIDC user có subject hợp lệ thì chắc được xem mọi order.”**

Không. Cần domain/tenant/owner authorization.

## 30. Tình huống thực hành

### A. Kiểm tra endpoint /me

Controller đọc subject/email.

**Cách làm:** `oidcLogin().idToken(...)` và JSON assertions.

### B. Kiểm tra role admin

Chỉ ROLE_ADMIN được truy cập /admin.

**Cách làm:** allowed test với ROLE_ADMIN và denied test với ROLE_VIEWER.

### C. Kiểm tra claim mapping

Production chuyển OIDC groups thành authorities.

**Cách làm:** test mapper thực, không chỉ inject ROLE_ADMIN.

### D. Kiểm tra callback state mismatch

Callback có state không tồn tại.

**Cách làm:** test OAuth2 Login filter với Authorization Request repository và fake OP; `oidcLogin()` không kiểm tra state.

### E. Kiểm tra signature/issuer ID token

OP trả ID token ký sai hoặc issuer khác.

**Cách làm:** OIDC authentication integration test với test JWKS/OP.

### F. Kiểm tra CSRF POST

Authenticated user gửi update thiếu CSRF token.

**Cách làm:** test 403 và case có `csrf()` theo session policy.

### G. Nhiều OIDC providers

Controller hiển thị provider hiện tại.

**Cách làm:** `oidcLogin().clientRegistration(...)` với ClientRegistration cụ thể.

### H. Tenant isolation

Alice chỉ thuộc Acme, gọi Globex.

**Cách làm:** mock Alice OIDC principal và kiểm thử membership/domain authorization thật.

### I. Outbound Bearer token

Portal gọi Orders API qua OAuth2AuthorizedClient.

**Cách làm:** fake authorized client, mock HTTP client, assert token/host/error handling. `oidcLogin()` một mình không đủ.

### J. Session nhiều requests

Request thứ hai cần cùng principal/session.

**Cách làm:** mô phỏng MockHttpSession/SecurityContext persistence có chủ đích.

## 31. Câu hỏi tự kiểm tra

**1. `oidcLogin()` thuộc dependency nào?**

`spring-security-test`.

**2. Static import là gì?**

`SecurityMockMvcRequestPostProcessors.oidcLogin`.

**3. Nó mô phỏng principal nào?**

`OidcUser` trong OAuth2 Login Authentication.

**4. Nó có gọi OpenID Provider thật không?**

Không.

**5. Nó có xác minh chữ ký ID token không?**

Không.

**6. Dùng API nào để sửa ID token claims?**

`idToken(token -> ...)`.

**7. Dùng API nào để sửa UserInfo?**

`userInfoToken(info -> ...)`.

**8. Dùng API nào để cấp authorities trực tiếp?**

`authorities(...)`.

**9. Có thể đưa custom OidcUser vào request không?**

Có, dùng `oidcUser(...)`.

**10. Test registration ID cụ thể thế nào?**

`clientRegistration(...)` với ClientRegistration fixture.

**11. groups claim có tự thành ROLE_ADMIN không?**

Không mặc định.

**12. Muốn test groups → role cần làm gì?**

Test GrantedAuthoritiesMapper/OIDC user loading logic thực.

**13. Test POST dựa trên session cookie cần gì?**

`csrf()` khi CSRF protection đang bật.

**14. Test anonymous thế nào?**

Gửi request không oidcLogin và assert entry point của app.

**15. oidcLogin có tự giữ Authentication cho tất cả requests sau không?**

Không mặc định; nó áp cho request cụ thể.

**16. Resource Server JWT API nên test bằng gì?**

`jwt()` và decoder/integration tests cho signature/issuer/audience thật.

**17. `@WebMvcTest` có thể không test được @PreAuthorize trên service vì sao?**

Service không được nạp hoặc được mock nên proxy method security có thể không chạy.

**18. Test PKCE/nonce/state bằng oidcLogin được không?**

Không; cần login integration tests.

**19. OIDC principal đã authenticated có cần tenant/owner check không?**

Có.

**20. Test outbound access token cần kiểm tra gì?**

Authorized client/token setup, Authorization Bearer header, target host và error handling.

## Ghi nhớ

- **`oidcLogin()` là request post-processor của Spring Security Test để mô phỏng user đã OIDC Login**, không chạy Authorization Code flow thật.
- **Dùng `spring-security-test`, MockMvc và Spring Security filter chain đúng context** để kiểm tra controller/security authorization.
- **`idToken(...)`, `userInfoToken(...)`, `authorities(...)`, `oidcUser(...)` và `clientRegistration(...)`** cho phép dựng OIDC principals rõ ràng và lặp lại.
- **OIDC claims và Spring GrantedAuthorities là hai tầng khác nhau**. Nếu production có custom groups-to-role mapper, phải test mapper riêng.
- **`oidcLogin()` khác `oauth2Login()`, `jwt()`, `opaqueToken()` và `@WithMockUser`**; chọn đúng helper theo security boundary.
- **Test allowed, denied, anonymous và CSRF**, không cấp admin cho mọi user hay tắt security filters để test chạy.
- **`oidcLogin()` không xác minh state, nonce, PKCE, callback, ID token signature/issuer hoặc refresh token thật**. Những phần này cần integration tests với mock/test OP.
- **Sau mock authentication, tenant membership và object ownership vẫn phải được kiểm tra**; OIDC Login không tự cấp quyền dữ liệu.
- **Kiểm thử outbound OAuth2AuthorizedClient và token relay riêng**, không lấy ID token làm API access token hoặc để lộ credentials trong test logs.
