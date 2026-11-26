# `oauth2Login` trong MockMvc và principal `OAuth2User`

## 1. Mục tiêu của bài học

Ứng dụng Spring Security có thể đăng nhập người dùng thông qua một nhà cung cấp OAuth2 bên ngoài. Sau khi đăng nhập thành công, Spring Security tạo một authentication đại diện cho người dùng OAuth2 và đặt principal để controller, service hoặc chính sách phân quyền sử dụng. Trong ứng dụng Servlet, principal phổ biến của luồng OAuth2 Login là **`OAuth2User`**.

Khi kiểm thử controller cần principal này, `@WithMockUser` không phù hợp: annotation đó tạo principal kiểu `User` của Spring Security, không tạo `OAuth2User`. Spring Security Test cung cấp request post-processor **`oauth2Login()`** để dựng một OAuth2 login authentication giả lập cho từng request `MockMvc`.

Bài học thuộc chương **Đăng nhập OAuth2 và OIDC** của module **SPRING_SECURITY_TESTING**. Module tập trung kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive; người học sử dụng `MockMvc`, `WebTestClient`, `SecurityContext`, `@WithMockUser` và các công cụ giả lập JWT/OAuth2/OIDC để kiểm tra các ca được phép hoặc bị từ chối.

Sau bài này, bạn có thể:

- Giải thích `oauth2Login()` tạo `OAuth2AuthenticationToken` với principal `OAuth2User`.
- Dùng `MockMvc` để gắn attributes và authorities vào danh tính OAuth2 giả lập.
- Đọc principal bằng `@AuthenticationPrincipal OAuth2User`.
- Hiểu vai trò của `nameAttributeKey` và `OAuth2User.getName()`.
- Kiểm thử endpoint yêu cầu đăng nhập và endpoint yêu cầu authority cụ thể.
- Phân biệt kiểm thử controller với OAuth2 principal với kiểm thử authorization code flow và giao tiếp Identity Provider thật.
- Nhận biết sự khác nhau giữa OAuth2 Login và OIDC Login.

## 2. OAuth2 Login tạo ra những đối tượng nào?

Sau khi OAuth2 Login thành công, Spring Security biểu diễn danh tính người dùng bằng một `OAuth2AuthenticationToken`. Token này giữ principal triển khai `OAuth2User`, authorities và registration ID của client đã dùng.

```text
OAuth2 Login thành công
        |
        v
OAuth2AuthenticationToken
   |          |                 |
   |          |                 +-- authorizedClientRegistrationId
   |          |
   |          +-- authorities: GrantedAuthority
   |
   +-- principal: OAuth2User
             |
             +-- getName()
             +-- getAttributes()
             +-- getAuthorities()
```

Các thành phần chính:

| Thành phần | Ý nghĩa |
| --- | --- |
| `OAuth2AuthenticationToken` | Authentication đại diện cho người dùng đã đăng nhập bằng OAuth2 Login |
| `OAuth2User` | Principal chứa tên và attributes do OAuth2 User Service cung cấp |
| `OAuth2User.getName()` | Trả về giá trị của thuộc tính được cấu hình làm tên người dùng |
| `OAuth2User.getAttributes()` | Map các thuộc tính nhận được từ UserInfo endpoint hoặc nguồn principal tương ứng |
| `OAuth2User.getAuthorities()` | Các quyền được gắn vào principal |
| `getAuthorizedClientRegistrationId()` | ID của cấu hình OAuth2 client đã dùng cho đăng nhập |

Với OAuth2 Login, các attributes phụ thuộc nhà cung cấp. Không nên mặc định mọi provider đều trả về `sub`, `email` hoặc `name`; ứng dụng phải biết thuộc tính nào có trong hợp đồng của provider.

### OAuth2User và OidcUser

`OidcUser` là một kiểu principal chuyên biệt cho OpenID Connect và cũng kế thừa `OAuth2User`. OAuth2 Login thuần túy thường cung cấp `OAuth2User`; khi đăng nhập OIDC, principal có thêm thông tin ID Token và các khái niệm OIDC như `OidcIdToken`.

| Luồng | Principal thường dùng | Công cụ test |
| --- | --- | --- |
| OAuth2 Login | `OAuth2User` | `oauth2Login()` |
| OpenID Connect Login | `OidcUser` | `oidcLogin()` |

Nếu controller chỉ yêu cầu `OAuth2User`, một `OidcUser` cũng thỏa mãn kiểu này vì quan hệ kế thừa. Nhưng nếu controller cần đọc ID Token hoặc claim OIDC đặc thù, hãy test bằng `oidcLogin()` và principal `OidcUser`.

## 3. oauth2Login() trong Spring Security Test

Với MockMvc, request post-processor được cung cấp qua static import:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oauth2Login;
```

Dùng trực tiếp:

```java
mockMvc.perform(get("/profile")
        .with(oauth2Login()))
    .andExpect(status().isOk());
```

`oauth2Login()` dựng một OAuth2 login authentication giả lập và gắn nó vào request test. Theo đó, request đi vào security filter chain với danh tính OAuth2 đã được thiết lập. Đây là cách kiểm thử controller và authorization sau khi người dùng đã đăng nhập.

Request post-processor cho phép tùy chỉnh những thành phần thường cần trong test:

```java
mockMvc.perform(get("/profile")
        .with(oauth2Login()
                .attributes(attributes -> {
                    attributes.put("sub", "user-123");
                    attributes.put("name", "Mai Nguyen");
                    attributes.put("email", "mai@example.test");
                })
                .authorities(
                    new SimpleGrantedAuthority("report:read")
                )))
    .andExpect(status().isOk());
```

Trong ví dụ:

- `attributes(...)` cung cấp dữ liệu principal `OAuth2User`.
- `authorities(...)` cung cấp các `GrantedAuthority` dùng trong chính sách phân quyền.
- `oauth2Login()` tạo authentication OAuth2 giả lập cho request.

Các thuộc tính và authorities này do test cung cấp. Chúng không được lấy từ một UserInfo endpoint thật trong lúc request chạy.

## 4. nameAttributeKey và OAuth2User.getName()

Một `OAuth2User` cần biết thuộc tính nào là tên định danh. Cấu hình OAuth2 client xác định khóa này bằng `userNameAttributeName` trong phần UserInfo endpoint của `ClientRegistration`.

Ví dụ một provider trả về:

```json
{
  "sub": "user-123",
  "name": "Mai Nguyen",
  "email": "mai@example.test"
}
```

Nếu cấu hình `userNameAttributeName("sub")`, thì:

```java
oauth2User.getName();                 // "user-123"
oauth2User.getAttribute("name");      // "Mai Nguyen"
oauth2User.getAttribute("email");     // "mai@example.test"
```

`getName()` không nhất thiết trả về trường `name` hiển thị. Nó trả về giá trị của thuộc tính định danh đã cấu hình. Điều này quan trọng khi controller dùng `principal.getName()` làm khóa người dùng hoặc khi ứng dụng ánh xạ tài khoản nội bộ.

Trong test, attributes phải có khóa định danh tương ứng. Nếu provider dùng `id` thay vì `sub`, cấu hình client và dữ liệu test cũng phải thống nhất:

```java
// ClientRegistration dùng userNameAttributeName("id")
attributes.put("id", "partner-456");
attributes.put("display_name", "Partner Mai");
```

Đừng viết test với `sub` rồi mong `getName()` tự suy ra từ `email` hoặc `name` nếu `ClientRegistration` đang cấu hình một khóa khác.

## 5. Cấu hình OAuth2 Client cho test context

Khi security chain bật `oauth2Login()`, ứng dụng cần một `ClientRegistrationRepository` để quản lý cấu hình OAuth2 client. Trong test, có thể đăng ký một client giả với endpoint dành riêng cho ví dụ. Các URL dưới đây chỉ là placeholder; request post-processor `oauth2Login()` không gọi chúng để thực hiện đăng nhập.

```java
@TestConfiguration
class OAuth2ClientTestConfiguration {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration testRegistration =
                ClientRegistration.withRegistrationId("test")
                        .clientId("test-client")
                        .clientSecret("test-secret")
                        .clientAuthenticationMethod(
                                ClientAuthenticationMethod.CLIENT_SECRET_BASIC
                        )
                        .authorizationGrantType(
                                AuthorizationGrantType.AUTHORIZATION_CODE
                        )
                        .redirectUri(
                                "{baseUrl}/login/oauth2/code/{registrationId}"
                        )
                        .scope("profile", "email")
                        .authorizationUri(
                                "https://idp.example.test/oauth2/authorize"
                        )
                        .tokenUri(
                                "https://idp.example.test/oauth2/token"
                        )
                        .userInfoUri(
                                "https://idp.example.test/userinfo"
                        )
                        .userNameAttributeName("sub")
                        .clientName("Test Identity Provider")
                        .build();

        return new InMemoryClientRegistrationRepository(testRegistration);
    }
}
```

Các import chính:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
```

Client registration giả cung cấp cấu hình mà `oauth2Login()` filter chain cần. Không cần client ID, secret hoặc endpoint thật của nhà cung cấp trong test authorization dùng request post-processor.

## 6. SecurityFilterChain và controller mẫu

Ta xây dựng hai endpoint:

- `GET /profile`: yêu cầu người dùng đã đăng nhập OAuth2.
- `GET /reports`: yêu cầu authority `report:read`.

### 6.1. Security configuration

```java
@Configuration
class OAuth2LoginSecurityConfig {

    @Bean
    SecurityFilterChain oauth2LoginFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/profile").authenticated()
                .requestMatchers("/reports")
                    .hasAuthority("report:read")
                .anyRequest().denyAll()
        );

        http.oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

Các import:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Ở đây `authenticated()` yêu cầu một danh tính đã xác thực; `hasAuthority("report:read")` kiểm tra chuỗi authority chính xác. OAuth2 Login được bật bằng `oauth2Login`.

### 6.2. Controller nhận OAuth2User

```java
record OAuth2ProfileResponse(
        String subject,
        String displayName,
        String email,
        String registrationId
) {}

@RestController
class OAuth2ProfileController {

    @GetMapping("/profile")
    OAuth2ProfileResponse profile(
            @AuthenticationPrincipal OAuth2User principal,
            Authentication authentication) {

        OAuth2AuthenticationToken oauth2Authentication =
                (OAuth2AuthenticationToken) authentication;

        return new OAuth2ProfileResponse(
                principal.getName(),
                principal.getAttribute("name"),
                principal.getAttribute("email"),
                oauth2Authentication.getAuthorizedClientRegistrationId()
        );
    }

    @GetMapping("/reports")
    String reports() {
        return "reports";
    }
}
```

Các import:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
```

Controller dùng `@AuthenticationPrincipal` để lấy principal `OAuth2User`. Tham số `Authentication` cho phép truy cập token hiện tại và registration ID. Trong ứng dụng thật, nên xử lý trường hợp provider không trả một attribute tùy chọn như `email`; ví dụ trên giả định test cung cấp đầy đủ các trường cần trả về.

## 7. Kiểm thử principal OAuth2User bằng MockMvc

### 7.1. Cấu hình test slice

```java
@WebMvcTest(OAuth2ProfileController.class)
@Import({
    OAuth2LoginSecurityConfig.class,
    OAuth2ClientTestConfiguration.class
})
class OAuth2LoginMockMvcTest {

    @Autowired
    MockMvc mockMvc;
}
```

Import:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
```

`@WebMvcTest` tạo MVC slice; do đó cần nạp security configuration và client registration repository dùng cho OAuth2 Login. Nếu test context đã cung cấp các bean này từ một cấu hình khác, không cần khai báo trùng.

### 7.2. Cung cấp attributes và kiểm tra response

```java
@Test
void oauth2UserAttributesReachController() throws Exception {
    mockMvc.perform(get("/profile")
            .with(oauth2Login()
                    .attributes(attributes -> {
                        attributes.put("sub", "user-123");
                        attributes.put("name", "Mai Nguyen");
                        attributes.put("email", "mai@example.test");
                    })))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("user-123"))
            .andExpect(jsonPath("$.displayName").value("Mai Nguyen"))
            .andExpect(jsonPath("$.email").value("mai@example.test"))
            .andExpect(jsonPath("$.registrationId").value("test"));
}
```

Request post-processor tạo principal OAuth2 có attributes được cung cấp. Controller nhận principal qua `@AuthenticationPrincipal OAuth2User` và trả dữ liệu tương ứng. Đây là kiểm tra tích hợp giữa request, Spring Security filter chain, argument resolver và controller.

### 7.3. Kiểm tra authentication

Có thể dùng result matcher để xác nhận request đã được xác thực:

```java
mockMvc.perform(get("/profile")
        .with(oauth2Login()
                .attributes(attributes ->
                        attributes.put("sub", "user-123"))))
    .andExpect(status().isOk())
    .andExpect(authenticated());
```

Static import:

```java
import static org.springframework.security.test.web.servlet.result
        .SecurityMockMvcResultMatchers.authenticated;
```

Matcher này xác nhận request được xử lý với authentication đã xác thực. Nếu cần kiểm tra chính xác principal và registration ID, hãy kiểm tra các giá trị mà controller sử dụng hoặc viết matcher phù hợp với `OAuth2AuthenticationToken`.

## 8. Kiểm thử authorities của OAuth2 login

`OAuth2User` có danh sách `GrantedAuthority`. Với request post-processor, test có thể chỉ định authority để kiểm tra chính sách:

```java
@Test
void oauth2UserWithReportReadCanAccessReports() throws Exception {
    mockMvc.perform(get("/reports")
            .with(oauth2Login()
                    .attributes(attributes ->
                            attributes.put("sub", "user-123"))
                    .authorities(
                            new SimpleGrantedAuthority("report:read")
                    )))
            .andExpect(status().isOk())
            .andExpect(content().string("reports"));
}
```

Và ca thiếu quyền:

```java
@Test
void oauth2UserWithoutReportReadIsForbidden() throws Exception {
    mockMvc.perform(get("/reports")
            .with(oauth2Login()
                    .attributes(attributes ->
                            attributes.put("sub", "user-123"))))
            .andExpect(status().isForbidden());
}
```

Import:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Trong ví dụ, test đầu cấp rõ `report:read`; test thứ hai dùng authorities mặc định của OAuth2 login test helper và không có authority nghiệp vụ đó. Vì chính sách yêu cầu chính xác `report:read`, request thứ hai bị từ chối.

**Không suy luận role hoặc scope từ tên claim một cách tự động.** Nếu ứng dụng muốn claim `roles: ["REPORT_READER"]` trở thành `ROLE_REPORT_READER`, hoặc scope `reports.read` trở thành authority riêng, ứng dụng cần cấu hình mapping phù hợp. `oauth2Login().authorities(...)` cung cấp authority trực tiếp cho test và có thể bỏ qua logic mapping production; do đó hãy test riêng mapper hoặc `OAuth2UserService` khi muốn xác minh việc chuyển claim thành quyền.

## 9. Phân biệt OAuth2User attributes với access token scopes

OAuth2 Login thường lấy thông tin người dùng từ UserInfo endpoint hoặc nguồn principal tương ứng. Attributes mô tả người dùng, ví dụ:

```json
{
  "sub": "user-123",
  "name": "Mai Nguyen",
  "email": "mai@example.test"
}
```

Scopes được cấp cho access token mô tả phạm vi client được phép truy cập. Chúng không tự động đồng nghĩa với role của người dùng. Việc chuyển scope hoặc claim thành `GrantedAuthority` phụ thuộc cấu hình và chính sách của ứng dụng.

| Dữ liệu | Ví dụ | Vai trò |
| --- | --- | --- |
| OAuth2User attribute | `email = mai@example.test` | Thông tin profile |
| OAuth2User name attribute | `sub = user-123` | Định danh principal theo cấu hình |
| GrantedAuthority | `ROLE_REPORT_READER` | Quyền được dùng trong authorization |
| OAuth2 access token scope | `reports.read` | Phạm vi được cấp cho access token |

Đừng viết test chỉ đặt attribute `role = "ADMIN"` rồi kỳ vọng `hasRole("ADMIN")` tự động cho phép. Nếu ứng dụng có mapper, test mapper và test authorization riêng. Trong test authorization thuần túy, chỉ định authority chính xác bằng `.authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))`.

## 10. Tùy chỉnh name attribute theo ClientRegistration

Mỗi OAuth2 provider có thể dùng khóa định danh khác nhau. Ví dụ:

```java
ClientRegistration partnerRegistration =
        ClientRegistration.withRegistrationId("partner")
                .clientId("partner-client")
                .clientSecret("test-secret")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC
                )
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE
                )
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}"
                )
                .scope("profile")
                .authorizationUri(
                        "https://partner.example.test/oauth2/authorize"
                )
                .tokenUri("https://partner.example.test/oauth2/token")
                .userInfoUri("https://partner.example.test/userinfo")
                .userNameAttributeName("id")
                .clientName("Partner")
                .build();
```

Với registration này, principal lấy `id` làm tên:

```java
attributes.put("id", "partner-456");
attributes.put("display_name", "Partner Mai");
```

Khi kiểm thử nhiều provider, truyền registration tương ứng cho request post-processor:

```java
mockMvc.perform(get("/profile")
        .with(oauth2Login()
                .clientRegistration(partnerRegistration)
                .attributes(attributes -> {
                    attributes.put("id", "partner-456");
                    attributes.put("display_name", "Partner Mai");
                })))
    .andExpect(status().isOk());
```

Khi đó principal được dựng theo `ClientRegistration` có `userNameAttributeName("id")). Hãy bảo đảm attributes có chứa name attribute đã cấu hình. Nếu không, việc tạo `DefaultOAuth2User` có thể thất bại hoặc `getName()` không phản ánh định danh mà ứng dụng mong đợi.

## 11. @WithMockUser không thay thế oauth2Login()

Hai cách tạo authentication có mục tiêu khác nhau:

| Cách | Principal | Authentication |
| --- | --- | --- |
| `@WithMockUser(username = "mai")` | `User` của Spring Security | `UsernamePasswordAuthenticationToken` |
| `.with(oauth2Login())` | `OAuth2User` | `OAuth2AuthenticationToken` |

Nếu controller có:

```java
@GetMapping("/profile")
String profile(@AuthenticationPrincipal OAuth2User principal) {
    return principal.getName();
}
```

thì test với `@WithMockUser` không tạo principal đúng kiểu. Tùy cấu hình resolver và tham số, controller có thể nhận `null` hoặc lỗi khi sử dụng principal. Hãy dùng `oauth2Login()` cho endpoint yêu cầu OAuth2 principal.

Ngược lại, nếu endpoint chỉ kiểm tra `hasRole("ADMIN")` và không phụ thuộc loại principal, `@WithMockUser(roles = "ADMIN")` có thể đủ cho test authorization. Không cần dùng OAuth2 helper cho mọi endpoint chỉ vì ứng dụng có bật OAuth2 Login.

## 12. oauth2Login() kiểm tra được gì và không kiểm tra được gì?

`oauth2Login()` thiết lập authentication giả lập. Nó giúp kiểm tra:

- Controller nhận đúng kiểu `OAuth2User`.
- `getName()` và `getAttribute(...)` được sử dụng đúng.
- Authorization theo authorities của OAuth2 authentication.
- Ứng dụng xử lý registration ID và principal theo cấu hình test.
- Các phản hồi HTTP khi người dùng OAuth2 có hoặc thiếu quyền.

Nó không thực hiện authorization code flow với Identity Provider. Cụ thể, helper không chứng minh:

- Trình duyệt được redirect đến authorization endpoint đúng.
- `state` được tạo và xác minh chống CSRF trong callback.
- Authorization code được trao đổi tại token endpoint.
- Client authentication bằng client secret hoặc private key hoạt động.
- Access token được lấy và lưu đúng.
- UserInfo endpoint được gọi và dữ liệu được parse đúng.
- `OAuth2UserService` production hoặc `GrantedAuthoritiesMapper` hoạt động đúng.

| Mục tiêu | Cách test phù hợp |
| --- | --- |
| Controller dùng `OAuth2User` | `oauth2Login()` + MockMvc |
| Authorization theo authority | `oauth2Login().authorities(...)` |
| Ánh xạ UserInfo attributes thành principal | Test `OAuth2UserService` hoặc luồng OAuth2 Login với UserInfo endpoint giả lập |
| Mapping role/claim thành authority | Test `GrantedAuthoritiesMapper` và cấu hình login |
| Redirect, state và callback | Integration test với mock Identity Provider |
| Code exchange và token response | Mock token endpoint hoặc test IdP |
| Client secret, token và UserInfo thực | Test tích hợp với provider sandbox hoặc máy chủ giả lập |

Để kiểm tra flow đầy đủ, có thể dùng một Identity Provider giả lập hoặc sandbox trong môi trường test. Khi đó test gửi request khởi tạo login, theo redirect/callback, kiểm tra state và quan sát token exchange. Không sử dụng credential production hoặc gọi provider thật trong test đơn vị.

## 13. OAuth2 Login và OIDC Login không phải cùng một principal

OpenID Connect mở rộng OAuth2 bằng lớp nhận dạng người dùng và ID Token. Khi provider hỗ trợ OIDC và client yêu cầu scope `openid`, Spring Security dùng OIDC-specific authentication/principal.

| Đặc điểm | OAuth2 Login | OIDC Login |
| --- | --- | --- |
| Principal | `OAuth2User` | `OidcUser` (kế thừa `OAuth2User`) |
| Thông tin profile | OAuth2 UserInfo attributes | OIDC claims từ ID Token/UserInfo |
| ID Token | Không phải thành phần bắt buộc của OAuth2 Login thuần | Có |
| Test helper | `oauth2Login()` | `oidcLogin()` |

Nếu controller nhận `OAuth2User`, cả hai loại principal có thể tương thích. Nếu controller nhận `OidcUser` hoặc truy cập `getIdToken()`, dùng `oidcLogin()` để test đúng hợp đồng.

Ví dụ test OIDC riêng:

```java
mockMvc.perform(get("/oidc-profile")
        .with(oidcLogin()
                .idToken(token -> token
                        .subject("user-123")
                        .claim("email", "mai@example.test")
                )))
    .andExpect(status().isOk());
```

Không dùng kết quả test `oauth2Login()` để kết luận ID Token hoặc nonce OIDC đã được xác minh.

## 14. Kiểm thử anonymous và entry point OAuth2 Login

Với endpoint yêu cầu authentication, request không có danh tính có thể được chuyển hướng tới trang đăng nhập OAuth2. Nếu chỉ có một client registration, trang đăng nhập mặc định có thể dẫn người dùng đến endpoint khởi tạo authorization request tương ứng.

Hành vi chính xác phụ thuộc cấu hình:

- OAuth2 Login có thể chuyển hướng khách tới `/oauth2/authorization/{registrationId}`.
- Ứng dụng API có thể cấu hình entry point trả `401`.
- Ứng dụng có thể dùng login page tùy chỉnh.

Vì vậy, khi test request không có authentication, hãy xác định entry point đang được cấu hình và kiểm tra status/Location tương ứng. `@WithAnonymousUser` tạo anonymous token để kiểm tra context; request không gắn `oauth2Login()` mới giúp kiểm tra hành vi entry point khi thiếu authentication trong MockMvc.

## 15. WebFlux và WebTestClient

`oauth2Login()` được trình bày trong bài này là request post-processor của **MockMvc**, dành cho Servlet. WebFlux dùng `WebTestClient` và các configurer của Spring Security Reactive Test; không truyền request post-processor MockMvc sang client Reactive.

Nếu ứng dụng có cả Servlet và Reactive:

- Dùng `oauth2Login()` trong test MockMvc để dựng OAuth2 principal cho MVC controller.
- Dùng configurer OAuth2 login tương ứng của `SecurityMockServerConfigurers` trong `WebTestClient` khi phiên bản Spring Security hỗ trợ và mục tiêu là Reactive OAuth2 authorization.
- Kiểm tra `OAuth2User` hoặc `OidcUser` qua endpoint Reactive trong Reactor Context.
- Dùng integration test riêng nếu cần xác minh redirect, callback, token endpoint và UserInfo endpoint trong luồng thật.

Không dùng `SecurityContextHolder` theo giả định context Reactive luôn nằm trên thread hiện tại. Kiểm tra kết quả qua `WebTestClient` và cấu hình security filter chain Reactive.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Controller nhận `OAuth2User` nhưng test dùng `@WithMockUser` | Principal thực tế là Spring `User`, không phải OAuth2User | Dùng `oauth2Login()` |
| `OAuth2User.getName()` không đúng | Name attribute key không khớp cấu hình registration | Kiểm tra `userNameAttributeName` và attributes test |
| Không tìm thấy `ClientRegistrationRepository` | Test context chưa nạp OAuth2 client config | Import hoặc cấu hình repository trong test |
| Endpoint trả `403` dù principal OAuth2 đã có | Authentication tồn tại nhưng thiếu authority yêu cầu | Cấp authority đúng hoặc kiểm tra mapper |
| Attribute `role = ADMIN` không qua `hasRole("ADMIN")` | Claim không tự trở thành `ROLE_ADMIN` | Cấu hình và test authority mapper |
| Test helper thành công nhưng callback production lỗi | Helper bỏ qua authorization code flow | Viết integration test với mock/test IdP |
| Không thấy access token trong principal | OAuth2User không phải nơi chứa access token | Dùng cơ chế authorized client phù hợp |
| Dùng `oauth2Login()` cho controller cần `OidcUser` | Test tạo OAuth2User thay vì OIDC principal | Dùng `oidcLogin()` |
| WebFlux test không nhận context | Dùng nhầm helper MockMvc hoặc thiếu Reactive integration | Dùng WebTestClient và Reactive security configurer |
| Anonymous request nhận redirect thay vì 401 | Entry point OAuth2 Login chuyển hướng tới IdP | Kiểm tra status và Location theo cấu hình |

Khi debug, kiểm tra lần lượt: **kiểu Authentication → kiểu principal → name attribute → authorities → security matcher → entry point**. Điều này giúp phân biệt lỗi principal, lỗi ánh xạ quyền và lỗi cấu hình OAuth2 Login.

## 17. Bài tập thực hành

Một ứng dụng dùng OAuth2 Login với provider có UserInfo:

```json
{
  "sub": "staff-100",
  "name": "Mai Nguyen",
  "email": "mai@example.test"
}
```

Các endpoint:

- `GET /profile`: yêu cầu authentication và trả subject, tên, email.
- `GET /reports`: yêu cầu authority `report:read`.
- `POST /reports/approve`: yêu cầu `report:approve` và CSRF hợp lệ.

Hãy thực hiện:

1. Tạo `ClientRegistrationRepository` cho test với `userNameAttributeName("sub")).
2. Cấu hình `SecurityFilterChain` bật `oauth2Login()`.
3. Viết controller nhận `@AuthenticationPrincipal OAuth2User` và trả attributes.
4. Dùng `oauth2Login().attributes(...)` để kiểm tra response profile.
5. Dùng `oauth2Login().authorities(new SimpleGrantedAuthority("report:read"))` để kiểm tra GET báo cáo được phép.
6. Bỏ authority `report:read` và xác nhận request bị từ chối.
7. Cấp `report:approve` và CSRF hợp lệ để kiểm tra POST phê duyệt.
8. Thay name attribute key thành `id`, cập nhật registration và dữ liệu test, rồi xác nhận `OAuth2User.getName()`.
9. So sánh `oauth2Login()` với `oidcLogin()`; xác định khi nào controller cần `OidcUser`.
10. Viết một integration test với mock Identity Provider để kiểm tra redirect, state, callback và token exchange; giải thích vì sao các bước này không được kiểm tra bởi request post-processor.

**Câu hỏi tự kiểm tra:** Nếu test `oauth2Login()` trả `200` cho `GET /profile`, có thể kết luận ứng dụng đã trao đổi authorization code và gọi UserInfo endpoint thành công không? **Không.** Test helper tạo authentication và principal giả lập trực tiếp. Muốn kiểm tra các bước giao tiếp với Identity Provider, cần integration test cho OAuth2 authorization code flow.

## 18. Ghi nhớ

`oauth2Login()` của Spring Security Test tạo một `OAuth2AuthenticationToken` với principal `OAuth2User` cho request MockMvc. Dùng `attributes(...)` để cung cấp dữ liệu người dùng và `authorities(...)` để kiểm tra chính sách phân quyền; `OAuth2User.getName()` phụ thuộc name attribute key trong `ClientRegistration`. `@WithMockUser` tạo principal khác kiểu nên không thay thế được OAuth2 login helper khi controller yêu cầu `OAuth2User`.

Request post-processor kiểm tra controller và authorization sau khi danh tính đã được thiết lập. Nó không thực hiện redirect, state validation, authorization code exchange, token validation hoặc gọi UserInfo endpoint thật. Khi cần kiểm tra các bước đó, hãy dùng integration test với Identity Provider giả lập hoặc sandbox; với OIDC principal và ID Token, dùng `oidcLogin()` cho test principal tương ứng.
