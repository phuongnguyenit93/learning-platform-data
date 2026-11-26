# Đối tượng `OAuth2AuthenticationToken` và tên registration

## 1. Vì sao cần hiểu `OAuth2AuthenticationToken`?

Khi ứng dụng Spring Security cho phép người dùng đăng nhập qua GitHub, Google hoặc nhà cung cấp OpenID Connect (OIDC) của doanh nghiệp, thông tin xác thực được lưu trong `SecurityContext` sau đăng nhập thành công thường là một đối tượng **`OAuth2AuthenticationToken`**. Đối tượng này chứa danh tính đã xác thực, quyền của người dùng và **tên client registration** đã được sử dụng.

Trong kiểm thử của module `SPRING_SECURITY_TESTING`, người học sử dụng `spring-security-test`, `MockMvc`, `WebTestClient` và các authentication giả lập để xác nhận ứng dụng phân biệt đúng người dùng, nhà cung cấp đăng nhập và quyền HTTP. Với luồng **Servlet OAuth2/OIDC Login**, có hai câu hỏi đặc biệt quan trọng:

1. `OAuth2AuthenticationToken` đại diện cho thông tin gì, và khác gì với access token hoặc ID token?
2. `getAuthorizedClientRegistrationId()` trả về giá trị nào, và phải kiểm tra giá trị đó như thế nào khi dùng `oauth2Login()` hoặc `oidcLogin()` trong MockMvc?

Ví dụ xuyên suốt sử dụng hai registration: `github` dành cho OAuth2 login và `corp-oidc` dành cho OIDC login. Một endpoint `GET /api/session` sẽ trả lại tên registration và tên principal để test xác nhận.

## 2. Bản chất của `OAuth2AuthenticationToken`

`OAuth2AuthenticationToken` là một implementation của `Authentication`, kế thừa `AbstractAuthenticationToken`, thường được tạo khi **đăng nhập OAuth2/OIDC** qua Spring Security. Những thành phần chính:

| Thành phần/API | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `getPrincipal()` | Đối tượng người dùng OAuth2 đã được tạo sau login; kiểu `OAuth2User` hoặc `OidcUser` | `DefaultOAuth2User`, `DefaultOidcUser` |
| `getName()` | Tên định danh của principal theo chiến lược `OAuth2User.getName()` | `"u-42"`, `"employee-9"` |
| `getAuthorities()` | Danh sách authorities có trong authentication | `OAUTH2_USER`, `OIDC_USER` hoặc quyền được ánh xạ |
| `isAuthenticated()` | Cờ cho biết authentication đã được đánh dấu xác thực | `true` sau login thành công |
| **`getAuthorizedClientRegistrationId()`** | **Khóa registration của client đã dùng cho login** | `"github"`, `"corp-oidc"` |

Chữ **`Authentication`** trong tên class phản ánh thông tin xác thực của người dùng hiện tại. Nó **không phải** đối tượng giữ chuỗi access token thô và **không phải** `JwtAuthenticationToken` thường được tạo bởi một **OAuth2 Resource Server** khi nhận Bearer JWT.

~~~mermaid
flowchart TD
    A["Đăng nhập qua OAuth2 / OIDC"] --> B["OAuth2AuthenticationToken"]
    B --> C["principal: OAuth2User hoặc OidcUser"]
    B --> D["authorities: Collection<GrantedAuthority>"]
    B --> E["registrationId: github / corp-oidc"]
    B --> F["name: OAuth2User.getName()"]
    G["OAuth2AuthorizedClient"] --> H["clientRegistration"]
    G --> I["accessToken và có thể refreshToken"]
    E -. "Khóa liên hệ khi tra authorized client" .-> G
~~~

### 2.1. Phân biệt ba đối tượng dễ nhầm

**`OAuth2AuthenticationToken`** biểu diễn danh tính đã đăng nhập của người dùng. Nó có `principal`, `authorities` và `authorizedClientRegistrationId`. Một HTTP request sau login có thể truy cập đối tượng này qua `Authentication` hoặc `SecurityContextHolder`.

**`ClientRegistration`** là cấu hình cho **ứng dụng khách OAuth2**: `registrationId`, `clientId`, `clientSecret`, `authorizationGrantType`, provider endpoints, scopes, redirect URI... Một ứng dụng có thể có nhiều `ClientRegistration` dù chúng cùng trỏ tới một nhà cung cấp.

**`OAuth2AuthorizedClient`** chứa thông tin về một client đã được ủy quyền thay mặt một principal, bao gồm `ClientRegistration`, tên principal, `OAuth2AccessToken` và có thể `OAuth2RefreshToken`. Nó thường được quản lý bởi `OAuth2AuthorizedClientRepository` hoặc `OAuth2AuthorizedClientService`. Việc có `OAuth2AuthenticationToken` không tự đảm bảo test đã trao đổi authorization code lấy access token thật.

| Câu hỏi | Đọc từ đâu? |
| --- | --- |
| Ai đang đăng nhập? | `OAuth2AuthenticationToken.getPrincipal()` và `getName()` |
| Dùng registration nào? | `getAuthorizedClientRegistrationId()` |
| Client ID cấu hình với provider là gì? | `ClientRegistration.getClientId()` |
| Access token để gọi API downstream là gì? | `OAuth2AuthorizedClient.getAccessToken()` |
| Người dùng OIDC có claim `sub` và `iss` nào? | `OidcUser.getIdToken()` cùng các claim liên quan |

## 3. `registrationId` là gì?

`registrationId` là **tên khóa do ứng dụng cấu hình cho một OAuth2/OIDC client**, không phải tên người dùng, không phải `client_id` do Identity Provider cấp, cũng không phải giá trị claim `iss` hay `sub`.

Ví dụ cấu hình minh họa của Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: example-github-client
            client-secret: example-github-secret
            scope: read:user
          corp-oidc:
            provider: corp-provider
            client-id: example-corp-client
            client-secret: example-corp-secret
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          corp-provider:
            issuer-uri: https://identity.example.test
~~~

Đây là cấu hình để giải thích tên registration; domain và secrets chỉ là giá trị mẫu, không dùng để kết nối thật. Hai khóa bên dưới `registration` là **`github`** và **`corp-oidc`**; khóa `corp-provider` bên dưới `provider` chỉ là tên cấu hình provider được registration tham chiếu.

Thông thường Spring Security sử dụng các đường dẫn mặc định:

- `GET /oauth2/authorization/github` để khởi động login bằng registration `github`.
- `GET /oauth2/authorization/corp-oidc` để khởi động login bằng registration `corp-oidc`.
- `/login/oauth2/code/{registrationId}` là mẫu redirect URI để xử lý callback authorization code khi cấu hình mặc định được sử dụng.

`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` sẽ cho biết registration đã được hệ thống gắn với kết quả login, ví dụ `github`. Giá trị này vẫn là `github` dù thông tin người dùng đến từ thuộc tính `id`, `login`, `name` hay `email`.

### 3.1. Tên registration không đồng nhất với provider

Một ứng dụng có thể tạo hai registrations `github-personal` và `github-work`, cùng dùng một provider GitHub nhưng có client ID, scopes hoặc chính sách khác nhau. Sau login, `getAuthorizedClientRegistrationId()` trả về chính xác `github-personal` hoặc `github-work` tương ứng, **không tự chuẩn hóa thành `github`**.

Ngược lại, tên `corp-oidc` có thể dùng provider được cấu hình dưới khóa `corp-provider`; `getAuthorizedClientRegistrationId()` vẫn trả về `corp-oidc`, không trả về `corp-provider`.

## 4. Principal OAuth2 và principal OIDC

Hai loại login thường sử dụng cùng class `OAuth2AuthenticationToken` nhưng **kiểu principal khác nhau**.

### 4.1. OAuth2 Login

Một login OAuth2 thông thường tạo principal kiểu `OAuth2User` (chẳng hạn `DefaultOAuth2User`). Principal có thuộc tính từ user-info endpoint và một khóa được cấu hình làm tên người dùng.

~~~java
OAuth2AuthenticationToken auth = /* lấy từ SecurityContext */;
OAuth2User oauth2User = auth.getPrincipal();

String registrationId = auth.getAuthorizedClientRegistrationId();
String principalName = auth.getName();
Map<String, Object> attributes = oauth2User.getAttributes();
~~~

Trong GitHub, một số cấu hình dùng thuộc tính `id` làm tên principal; ví dụ `principalName = "u-42"`. Trong test giả lập, tên này do `OAuth2User` được dựng cho test quyết định.

### 4.2. OIDC Login

OIDC bổ sung một lớp xác thực danh tính trên OAuth2. Principal thường là `OidcUser`, mở rộng `OAuth2User` và cho phép truy cập `OidcIdToken` cùng user info (nếu có).

~~~java
OAuth2AuthenticationToken auth = /* lấy từ SecurityContext */;

if (auth.getPrincipal() instanceof OidcUser oidcUser) {
    String subject = oidcUser.getSubject();       // claim "sub"
    String issuer = oidcUser.getIdToken()
                            .getIssuer().toString();
    String registrationId = auth.getAuthorizedClientRegistrationId();
}
~~~

Với OIDC, định danh người dùng nên được hiểu trong ngữ cảnh issuer; cặp `iss` và `sub` mới cung cấp ngữ cảnh danh tính rõ hơn. `registrationId` là tên cấu hình client của **ứng dụng**, không phải một claim có chữ ký trong ID token.

| Khía cạnh | OAuth2 Login | OIDC Login |
| --- | --- | --- |
| Đối tượng authentication sau login Servlet | `OAuth2AuthenticationToken` | `OAuth2AuthenticationToken` |
| Kiểu principal | `OAuth2User` | `OidcUser` |
| Nguồn thuộc tính | User info do provider trả về | ID token và có thể UserInfo |
| Tên principal | Phụ thuộc `userNameAttributeName` hoặc principal custom | Thường là `sub`, có thể tùy chỉnh |
| Tên registration | `getAuthorizedClientRegistrationId()` | Cũng `getAuthorizedClientRegistrationId()` |
| Kiểm thử MockMvc phù hợp | `oauth2Login()` | `oidcLogin()` |

**Đừng suy ra OIDC chỉ từ tên registration.** Một registration có chữ `oidc` trong tên chưa tự chứng minh rằng request đã đi qua việc xác minh ID token. Khi dùng mock test, đặc biệt phải phân biệt dữ liệu giả và giao thức xác thực thực.

## 5. Tự tạo `OAuth2AuthenticationToken` để hiểu từng trường

Đoạn code nhỏ sau là ví dụ minh họa lớp Java, không thực hiện login HTTP:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;

OAuth2User principal = new DefaultOAuth2User(
        List.of(new SimpleGrantedAuthority("OAUTH2_USER")),
        Map.of("id", "u-42", "login", "learner"),
        "id");

OAuth2AuthenticationToken authentication = new OAuth2AuthenticationToken(
        principal,
        principal.getAuthorities(),
        "github");

assert authentication.getAuthorizedClientRegistrationId().equals("github");
assert authentication.getName().equals("u-42");
assert authentication.getPrincipal() == principal;
assert authentication.isAuthenticated();
~~~

Hai chuỗi `"github"` và `"u-42"` đến từ **hai nguồn khác nhau**. `"github"` là registration ID được truyền vào constructor; `"u-42"` là giá trị thuộc tính `id` theo quy ước tên của `DefaultOAuth2User`. Đổi tên người dùng không làm registration ID tự đổi; đổi registration ID cũng không tự đổi principal.

Trong ứng dụng thật, authentication phải được tạo bởi luồng OAuth2/OIDC Login đã xác thực thành công. Đừng đưa constructor trên vào controller để tự công nhận một người dùng đến từ tham số HTTP.

## 6. Ví dụ endpoint đọc `OAuth2AuthenticationToken`

Giả sử ứng dụng có API Servlet nội bộ trả về ngữ cảnh login đã xác thực:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class SessionController {

    @GetMapping("/api/session")
    Map<String, Object> session(Authentication authentication) {
        if (!(authentication instanceof OAuth2AuthenticationToken oauth2)) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "OAuth2 login required");
        }

        return Map.of(
                "registrationId", oauth2.getAuthorizedClientRegistrationId(),
                "principalName", oauth2.getName(),
                "principalKind",
                    oauth2.getPrincipal() instanceof OidcUser ? "OIDC" : "OAuth2",
                "authenticated", oauth2.isAuthenticated());
    }
}
~~~

Một cấu hình security chain tối giản:

~~~java
@Configuration
@EnableWebSecurity
class LoginSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/session").authenticated()
                .anyRequest().permitAll())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Các import cấu hình gồm `@Configuration`, `@Bean`, `@EnableWebSecurity`, `HttpSecurity`, `SecurityFilterChain` và `Customizer`. Với demo production, cần cung cấp `ClientRegistrationRepository` và các registrations hợp lệ. **Security chain có `oauth2Login()` cần repository được đăng ký khi khởi tạo application context**; chỉ tạo một `ClientRegistration` trong phương thức test chưa đủ để thay thế bean này. Phần 7 sẽ dựng cả registration mẫu và một repository thử nghiệm cho `@SpringBootTest`.

Đầu ra tham khảo khi người dùng mock đăng nhập qua GitHub:

~~~json
{
  "registrationId": "github",
  "principalName": "u-42",
  "principalKind": "OAuth2",
  "authenticated": true
}
~~~

Endpoint ví dụ không trả access token, ID token hoặc dữ liệu bí mật ra HTTP. Trong ứng dụng thật, chỉ công khai những trường phù hợp với hợp đồng API; không mặc định mọi thông tin trong principal đều được phép trả về.

## 7. Kiểm thử `registrationId` bằng `MockMvc.oauth2Login()`

### 7.1. Chuẩn bị dependency và client registration mẫu

Ví dụ Spring Boot Servlet cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Trong lớp test tích hợp, tạo một `ClientRegistration` đủ trường cho test. Tên registration là tham số truyền vào factory:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

static ClientRegistration registration(String registrationId, boolean oidc) {
    return ClientRegistration.withRegistrationId(registrationId)
            .clientId("example-client-id")
            .clientSecret("example-client-secret")
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope(oidc
                    ? new String[] { "openid", "profile" }
                    : new String[] { "read:user" })
            .authorizationUri("https://identity.example.test/authorize")
            .tokenUri("https://identity.example.test/token")
            .userInfoUri("https://identity.example.test/userinfo")
            .userNameAttributeName(oidc ? "sub" : "id")
            .jwkSetUri("https://identity.example.test/jwks")
            .build();
}
~~~

Các URL ở đây là giá trị mô phỏng. Test dùng `oauth2Login()` / `oidcLogin()`, vì vậy **không trao đổi authorization code hay gọi trực tiếp những URL trên**. Đừng dùng factory này làm cấu hình production.

### 7.2. Test tên registration của OAuth2 Login

Tạo principal giả có tên `u-42` và gắn với registration `github`:

~~~java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Import(OAuth2RegistrationTests.TestClientRegistrations.class)
class OAuth2RegistrationTests {

    @TestConfiguration(proxyBeanMethods = false)
    static class TestClientRegistrations {
        @Bean
        ClientRegistrationRepository clientRegistrationRepository() {
            return new InMemoryClientRegistrationRepository(
                    registration("github", false),
                    registration("corp-oidc", true));
        }
    }

    @Autowired
    MockMvc mockMvc;

    // Đặt hàm registration(...) từ mục 7.1 trong lớp test này.

    @Test
    void oauth2LoginCarriesRegistrationId() throws Exception {
        ClientRegistration github = registration("github", false);

        OAuth2User learner = new DefaultOAuth2User(
                List.of(new SimpleGrantedAuthority("OAUTH2_USER")),
                Map.of("id", "u-42", "login", "learner"),
                "id");

        mockMvc.perform(get("/api/session")
                    .with(oauth2Login()
                            .clientRegistration(github)
                            .oauth2User(learner)))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.authenticated").value(true))
               .andExpect(jsonPath("$.registrationId").value("github"))
               .andExpect(jsonPath("$.principalName").value("u-42"))
               .andExpect(jsonPath("$.principalKind").value("OAuth2"));
    }
}
~~~

Trong lớp test này cần thêm import `org.springframework.boot.test.context.TestConfiguration`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Import`, `org.springframework.security.oauth2.client.registration.ClientRegistrationRepository` và `org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository`. `TestClientRegistrations` cung cấp bean repository cho security chain khi ứng dụng chưa có bean này; **nếu test context đã cấu hình repository thật, hãy dùng repository đó hoặc thay thế có chủ đích để tránh hai bean cạnh tranh**. Đoạn ví dụ giả định test context cũng nạp `LoginSecurityConfiguration` và `SessionController` của mục 6.

**Giải thích:** `oauth2Login()` đặt authentication đã được giả lập cho yêu cầu MockMvc. `clientRegistration(github)` cho matcher/controller biết tên registration là `github`. `oauth2User(learner)` đặt danh tính người dùng giả `u-42`. Vì vậy hai assertion:

- `$.registrationId == "github"`
- `$.principalName == "u-42"`

kiểm tra **hai giá trị riêng biệt**. Không nên kiểm tra `authentication.getName()` rồi kết luận ứng dụng đã xác định chính xác registration.

### 7.3. Kiểm thử hai registration cùng provider

Thêm vào lớp test ở mục 7.2:

~~~java
@Test
void registrationIdComesFromSelectedClientRegistration() throws Exception {
    OAuth2User learner = new DefaultOAuth2User(
            List.of(new SimpleGrantedAuthority("OAUTH2_USER")),
            Map.of("id", "u-42"),
            "id");

    mockMvc.perform(get("/api/session")
                .with(oauth2Login()
                        .clientRegistration(registration("github-work", false))
                        .oauth2User(learner)))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.registrationId").value("github-work"))
           .andExpect(jsonPath("$.principalName").value("u-42"));

    mockMvc.perform(get("/api/session")
                .with(oauth2Login()
                        .clientRegistration(
                            registration("github-personal", false))
                        .oauth2User(learner)))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.registrationId").value("github-personal"))
           .andExpect(jsonPath("$.principalName").value("u-42"));
}
~~~

Hai request có **cùng principal name** nhưng **khác registration ID**. Đó là ví dụ cho thấy registration ID được gắn với client configuration chứ không suy ra từ tên người dùng. Factory minh họa dùng cùng endpoint provider để mô phỏng hai registrations; trong sản phẩm thật, client ID và phạm vi cấp quyền có thể khác nhau.

## 8. Kiểm thử OIDC với `oidcLogin()`

Trong OIDC, `oidcLogin()` tạo một `OidcUser` giả và gắn vào `OAuth2AuthenticationToken`. Nó phù hợp khi controller cần các thuộc tính OIDC như `sub` hoặc `idToken`. Dùng cùng endpoint `GET /api/session`:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;

@Test
void oidcLoginCarriesRegistrationAndOidcPrincipal() throws Exception {
    ClientRegistration corporate = registration("corp-oidc", true);

    mockMvc.perform(get("/api/session")
                .with(oidcLogin()
                        .clientRegistration(corporate)
                        .idToken(token -> token
                            .claim("sub", "employee-9")
                            .claim("email", "employee@example.test"))))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.registrationId").value("corp-oidc"))
           .andExpect(jsonPath("$.principalName").value("employee-9"))
           .andExpect(jsonPath("$.principalKind").value("OIDC"))
           .andExpect(jsonPath("$.authenticated").value(true));
}
~~~

**Kỳ vọng:** authentication sau post-processor vẫn có thể được đọc qua `OAuth2AuthenticationToken`. Sự khác biệt là `getPrincipal()` cung cấp `OidcUser` có ID token giả. `getAuthorizedClientRegistrationId()` cho biết `corp-oidc`; tên principal đến từ `sub` của ID token giả.

Các phép khẳng định trên **không chứng minh** ID token đã được ký hợp lệ, issuer đã được xác minh, nonce đã khớp hay toàn bộ OAuth2 authorization-code flow đã chạy. `oidcLogin()` cố ý tạo trạng thái đã đăng nhập để kiểm thử logic ở phía ứng dụng.

### 8.1. Không nhầm `OAuth2AuthenticationToken` với `JwtAuthenticationToken`

Một yêu cầu được xác thực bởi OAuth2 Resource Server thông qua JWT Bearer thường có `JwtAuthenticationToken`, ví dụ khi gọi:

~~~http
GET /api/reports HTTP/1.1
Authorization: Bearer <signed-access-token>
~~~

Trong trường hợp đó, `JwtAuthenticationToken` biểu diễn token của resource server và không có API `getAuthorizedClientRegistrationId()` như `OAuth2AuthenticationToken`. Nếu một endpoint chấp nhận cả session OAuth2/OIDC Login lẫn bearer JWT, code cần phân nhánh an toàn theo kiểu `Authentication`; đừng ép cast vô điều kiện.

Tương tự, `@WithMockUser` tạo một principal được xác thực để kiểm thử quyền thông thường; nó không tạo client registration và không thay thế `oauth2Login()` khi cần kiểm tra `getAuthorizedClientRegistrationId()`.

## 9. Khi nào nên xác nhận trực tiếp authentication bằng result matcher?

Nếu không muốn tạo endpoint chỉ để hiển thị thông tin bảo mật, Spring Security Test có thể kiểm tra trạng thái authenticated. Khi cần xem sâu bên trong authentication, dùng matcher tương ứng:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;

@Test
void canInspectRegistrationDirectly() throws Exception {
    mockMvc.perform(get("/api/session")
                .with(oauth2Login()
                        .clientRegistration(registration("github", false))))
           .andExpect(authenticated().withAuthentication(authentication -> {
               assertInstanceOf(
                       OAuth2AuthenticationToken.class, authentication);
               OAuth2AuthenticationToken oauth2 =
                       (OAuth2AuthenticationToken) authentication;
               assertEquals("github",
                       oauth2.getAuthorizedClientRegistrationId());
           }));
}
~~~

Kiểu matcher này dùng cho kết quả một request MockMvc cụ thể. Không nên lấy `SecurityContextHolder.getContext().getAuthentication()` **sau khi** `mockMvc.perform(...)` kết thúc rồi suy luận rằng đó vẫn là authentication của request trước: Spring Security thường dọn context ở cuối vòng đời request để tránh rò rỉ giữa các test.

Khi muốn kiểm tra session thật sau redirect login, phải chạy một **flow đăng nhập thực** hoặc tích hợp phù hợp và giữ session/cookie từ request trước; `oauth2Login()` vẫn là helper gắn authentication giả vào request mà nó xử lý.

## 10. Giá trị của `registrationId` trong ứng dụng thực tế

Tên registration giúp chọn đúng cấu hình khi:

- Ứng dụng có nhiều phương thức đăng nhập OAuth2/OIDC và cần hiển thị nguồn đăng nhập.
- Chọn chiến lược ánh xạ tài khoản nội bộ dựa trên registration đã được hệ thống tin cậy xác lập.
- Tra `OAuth2AuthorizedClient` phù hợp bằng registration ID và principal khi gọi API downstream.
- Phân tách các client registrations có scopes, client ID hoặc chính sách riêng.
- Ghi log kiểm thử và chuẩn đoán luồng login, với điều kiện không ghi access token hay dữ liệu bí mật.

### 10.1. Không dùng registration ID thay thế bằng chứng danh tính

`getAuthorizedClientRegistrationId() == "corp-oidc"` không đủ để tự kết luận:

- User thực sự thuộc một tenant được cấp phép.
- ID token có issuer `iss` và audience `aud` hợp lệ.
- Email đã được xác minh.
- Người dùng có role hoặc permission nội bộ.
- Access token đã được cấp đúng scopes hoặc vẫn còn hạn.

Đối với OIDC, danh tính dựa trên claim đã được validator chấp nhận, thường gồm cặp `iss` + `sub`, và các kiểm tra nghiệp vụ khác. Chỉ kiểm tra tên registration rồi cấp quyền quản trị là nguy hiểm, nhất là khi có nhiều cấu hình provider, account linking hoặc tenant.

**Trong MockMvc với `oidcLogin()`, tên registration và claims là dữ liệu test tự đặt.** Vì vậy test chỉ chứng minh phần code phía sau authentication xử lý các giá trị đó đúng; nó không xác minh độ tin cậy của chúng.

### 10.2. Đổi tên registration có thể làm thay đổi hành vi

Nếu đổi cấu hình từ `corp-oidc` sang `corporate`, các nơi dùng `getAuthorizedClientRegistrationId()`, link `/oauth2/authorization/...`, key lưu authorized client và test mong đợi tên cũ có thể cần cập nhật tương ứng. Nên dùng tên ổn định và được kiểm soát; test một cách rõ ràng để nhận ra thay đổi ngoài ý muốn.

## 11. Phân biệt test giả lập và kiểm thử OAuth2/OIDC đầy đủ

Một test sử dụng `oauth2Login()` hay `oidcLogin()` **không tự thực hiện** các bước:

1. Redirect trình duyệt đến authorization endpoint của provider.
2. Tạo và lưu authorization request, kiểm tra tham số `state`.
3. Nhận authorization code tại callback và đổi code lấy token.
4. Xác minh chữ ký ID token, thời gian hiệu lực, issuer, audience và nonce theo yêu cầu OIDC.
5. Lấy UserInfo và liên kết tài khoản theo cấu hình ứng dụng.
6. Lưu authorized client/session thật và kiểm thử logout hoặc token refresh.

Test MockMvc giả lập nên dùng để kiểm tra **mapping và phân quyền sau khi đã có authentication**, chẳng hạn:

| Mục tiêu | Công cụ hợp lý | Điều có thể kết luận |
| --- | --- | --- |
| Controller đọc tên registration chính xác | `oauth2Login().clientRegistration(...)` | Mapping `OAuth2AuthenticationToken` đúng |
| Controller xử lý `OidcUser` và `sub` | `oidcLogin().idToken(...)` | Logic sử dụng principal OIDC đúng |
| Quyền truy cập phụ thuộc authorities | `oauth2Login().authorities(...)` hoặc principal tùy chỉnh | Quy tắc phân quyền với danh tính giả đúng |
| OAuth2 callback xử lý `state` và authorization code | Integration test với IdP/authorization server thử nghiệm | Flow code thực hoạt động theo cấu hình |
| ID token OIDC sai chữ ký, sai `iss`, sai `nonce` bị từ chối | Integration test với validator/IdP phù hợp | Các ràng buộc ID token đã chạy |
| Access token bị thu hồi sau logout | Integration test với cơ chế revocation tương ứng | Token cũ không còn sử dụng theo hợp đồng |

Đối với hệ thống có yêu cầu mạnh về bảo mật, nên kết hợp kiểm thử controller bằng principal giả với kiểm thử luồng OAuth2/OIDC có nhà cung cấp danh tính thử nghiệm (hoặc môi trường tích hợp được kiểm soát).

## 12. Một số lỗi thường gặp và cách xử lý

| Lỗi | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| So `getName()` với `"github"` để nhận biết provider | `getName()` là tên principal, không phải registration | Dùng `getAuthorizedClientRegistrationId()` |
| So `getAuthorizedClientRegistrationId()` với `clientId` | Registration ID là tên local; client ID do provider cấp | Đọc hai trường từ đúng đối tượng |
| Cho rằng `providerId` bằng `registrationId` | Hai khóa có thể khác nhau theo cấu hình | Kiểm tra `ClientRegistration` tương ứng |
| Test OIDC bằng `oauth2Login()` rồi cast principal sang `OidcUser` | `oauth2Login()` thông thường tạo `OAuth2User` | Dùng `oidcLogin()` cho OIDC |
| Dùng `@WithMockUser` rồi gọi `getAuthorizedClientRegistrationId()` | Principal mock thường không phải `OAuth2AuthenticationToken` | Dùng OAuth2/OIDC login test post-processor |
| Dùng `oauth2Login()` rồi nói đã kiểm tra OAuth callback | Helper bỏ qua luồng chuyển hướng và trao đổi code | Viết integration test riêng cho callback |
| Dùng `oidcLogin()` rồi nói ID token có chữ ký đúng | ID token và principal được tạo giả | Dùng validator/IdP test thật |
| Dùng registration ID để cấp đặc quyền quản trị | Nó không tự xác minh tenant, role hoặc danh tính | Kết hợp danh tính, issuer và luật phân quyền đã kiểm chứng |
| Truy xuất access token từ `OAuth2AuthenticationToken` | Object này không sở hữu API trả access token | Dùng `OAuth2AuthorizedClient` qua repository/service |
| Không bật security filter chain khi kiểm tra endpoint | Test có thể chạy ngoài cơ chế bảo vệ HTTP | Dùng `@AutoConfigureMockMvc` hoặc `apply(springSecurity())` phù hợp |

## 13. Bài tập thực hành

### Bài 1: Đọc đúng registration

Thêm một registration `github-work` vào test, tạo principal có `id = "u-42"`, kiểm tra JSON trả về `registrationId = "github-work"` và `principalName = "u-42"`. Sau đó đổi registration thành `github-personal` nhưng giữ principal không đổi. Giải thích vì sao tên principal không thay đổi.

### Bài 2: Phân biệt OAuth2 và OIDC

Viết một test `oauth2Login()` và một test `oidcLogin()` đi qua cùng `/api/session`. Khẳng định `principalKind` tương ứng là `OAuth2` và `OIDC`. Trong OIDC test, đặt claim `sub = "employee-9"`; giải thích vì sao `registrationId` vẫn là `corp-oidc`.

### Bài 3: Nhận diện giới hạn của test

Giả sử test sau thành công:

~~~java
mockMvc.perform(get("/api/session")
            .with(oidcLogin()
                    .clientRegistration(registration("corp-oidc", true))))
       .andExpect(status().isOk())
       .andExpect(jsonPath("$.registrationId").value("corp-oidc"));
~~~

Hãy xác định điều gì **đã được kiểm tra** (application xử lý authentication giả có registration này) và điều gì **chưa được kiểm tra** (OIDC code flow, chữ ký ID token, issuer, audience, nonce, token exchange). Sau đó đề xuất một ca integration test thật cho một trong các ràng buộc chưa được kiểm tra.

### Bài 4: Thiết kế quyền an toàn

Một controller chỉ cho phép truy cập khi `registrationId.equals("corp-oidc")`. Đề xuất bổ sung kiểm tra nào để tránh dùng registration ID làm bằng chứng duy nhất cho người dùng thuộc doanh nghiệp? Gợi ý: issuer + subject đã xác minh, ánh xạ user nội bộ và quyền nghiệp vụ.

## 14. Kết luận học tập

Một phiên đăng nhập OAuth2/OIDC Servlet được biểu diễn bằng `OAuth2AuthenticationToken`, trong đó **`getAuthorizedClientRegistrationId()` trả về tên cấu hình đăng nhập** còn **`getName()` trả về tên của principal**. Với OIDC, principal thường là `OidcUser` và có thêm ID token; với OAuth2 login thông thường, principal là `OAuth2User`. Các thông tin này liên quan nhưng không được đánh đồng.

`oauth2Login()` và `oidcLogin()` của Spring Security Test giúp xác nhận application đọc đúng registration và danh tính giả trong MockMvc. Muốn xác minh **quá trình đăng nhập và token thật**, cần bổ sung kiểm thử tích hợp cho authorization code, callback, state, token validation và các chính sách bảo mật thực tế.

## 15. Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): các thành phần và luồng đăng nhập OAuth2.
- [Spring Security — Testing OAuth2 Login với MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oauth2Login()` và `oidcLogin()`.
- [Spring Security — OAuth2AuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html): `getAuthorizedClientRegistrationId()`, principal và authorities.
- [Spring Security — Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication` và `SecurityContextHolder`.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `ClientRegistration` và `OAuth2AuthorizedClient`.
