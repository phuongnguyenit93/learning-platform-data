# Giới hạn của helper không chạy redirect, đổi code hoặc xác minh ID token thật

Trong kiểm thử Spring Security, gọi `oauth2Login()` hoặc `oidcLogin()` của `spring-security-test` có thể làm một request `MockMvc` được xử lý như người dùng **đã đăng nhập**. Đây là tính năng hữu ích: ta có thể kiểm tra controller, method security và quyền truy cập theo authorities/claims mà không cần dựng một nhà cung cấp danh tính (Identity Provider, IdP).

Nhưng một request trả `200 OK` khi dùng helper **không chứng minh** rằng ứng dụng đã:

- Chuyển hướng browser đến authorization endpoint của IdP.
- Tạo và lưu OAuth 2.0 authorization request, `state` hoặc `nonce`.
- Nhận callback chứa `code` rồi đổi authorization code lấy token tại token endpoint.
- Xác thực chữ ký, issuer, audience, thời hạn hoặc nonce của **ID token OIDC thật**.
- Gọi user-info endpoint, tạo session theo luồng callback hay sử dụng đúng client credentials.

Bài học thuộc chương **Đăng nhập OAuth2 và OIDC** của module `SPRING_SECURITY_TESTING`. Mục tiêu là hiểu rõ ranh giới của helper giả lập và chọn cách kiểm thử tương ứng trên ứng dụng Servlet bằng `MockMvc`; phần cuối đối chiếu với `WebTestClient` của Reactive.

Sau bài này, bạn sẽ viết được test phân quyền dùng `oauth2Login()/oidcLogin()` và giải thích được vì sao cần một loại integration test khác để chứng minh redirect, code exchange hay xác thực ID token thực sự xảy ra.

## 1. Phân biệt OAuth2 login, OIDC login và Resource Server

Ba cơ chế thường xuất hiện trong cùng hệ sinh thái nhưng có mục đích khác nhau.

| Cơ chế | Vai trò của ứng dụng | Thông tin thường nhận | Mục đích |
| --- | --- | --- | --- |
| `oauth2Login()` của ứng dụng | OAuth 2.0 Client, login qua browser | Authorization code, access token, thông tin người dùng từ user-info hoặc cơ chế tùy biến | Đăng nhập người dùng qua OAuth2 |
| `oidcLogin()` của ứng dụng | OpenID Connect Relying Party | Authorization code, access token, **ID token** và có thể user-info | Xác thực danh tính người dùng theo OIDC |
| `oauth2ResourceServer().jwt()` | Resource Server bảo vệ API | `Authorization: Bearer <JWT>` | Kiểm tra Bearer access token tới API |
| `oauth2ResourceServer().opaqueToken()` | Resource Server bảo vệ API | `Authorization: Bearer <opaque>` | Introspect opaque access token |

Ở đây, `SecurityMockMvcRequestPostProcessors.oauth2Login()` và `oidcLogin()` chỉ là **request post-processors cho test**, cùng tên gần với cấu hình ứng dụng `http.oauth2Login()` nhưng không có cùng tác dụng. Cấu hình production đăng ký các filter và cơ chế đăng nhập; helper test trực tiếp cung cấp authentication cho một request.

**ID token** dùng để truyền thông tin xác thực danh tính từ OpenID Provider đến Client/Relying Party. Nó khác **access token**, thường được dùng để gọi resource server. Trả về một `OidcUser` giả lập trong test không có nghĩa API hoặc ứng dụng đã giải mã access token hay kiểm tra ID token từ IdP.

### 1.1. Luồng browser login thật gồm những chặng nào?

Với Authorization Code Flow của OAuth2/OIDC, đường đi thường là:

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as Ứng dụng Spring Security
    participant I as Identity Provider
    B->>A: GET /oauth2/authorization/demo
    A->>A: Sinh authorization request, state (và nonce với OIDC)
    A-->>B: 302 Location: IdP /authorize?...
    B->>I: GET /authorize?...client_id,redirect_uri,state,...
    I-->>B: Đăng nhập/chấp thuận và redirect
    B->>A: GET /login/oauth2/code/demo?code=...&state=...
    A->>A: Tra authorization request đã lưu và so khớp state
    A->>I: POST /token với authorization code
    I-->>A: Access token, và ID token nếu OIDC
    opt OIDC
        A->>A: Kiểm tra ID token theo cấu hình
    end
    opt Có user-info
        A->>I: Gọi user-info endpoint
        I-->>A: Thuộc tính người dùng
    end
    A->>A: Tạo OAuth2AuthenticationToken và security context
    A-->>B: Redirect sau login; session được cập nhật
```

Các thành phần Spring Security quan trọng trong pipeline là:

- `OAuth2AuthorizationRequestRedirectFilter`: xử lý URL khởi động login và tạo authorization redirect.
- `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` (thường là repository dựa trên HTTP session): lưu request để kiểm tra callback/state.
- `OAuth2LoginAuthenticationFilter`: xử lý callback authorization code.
- `OAuth2AccessTokenResponseClient`: đổi code lấy token từ token endpoint qua đường thực thi đã cấu hình.
- `OAuth2UserService` hoặc `OidcUserService`: tải/chuẩn hóa thông tin principal tùy provider và cấu hình.
- Bộ phận giải mã và xác minh ID token OIDC, thường sử dụng `JwtDecoderFactory<ClientRegistration>` và các validators của OIDC.

Pipeline này còn phụ thuộc cấu hình `ClientRegistration`, HTTP session, `state`, `nonce`, PKCE (nếu áp dụng), token endpoint/JWK Set và các success/failure handler. Một test chỉ gắn mock principal **không thực thi** các chặng đó.

## 2. Helper oauth2Login() và oidcLogin() tạo gì?

`spring-security-test` có hai request post-processor dành riêng cho ứng dụng Servlet:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;

mockMvc.perform(get("/api/me").with(oauth2Login()));
mockMvc.perform(get("/api/me").with(oidcLogin()));
```

Ý tưởng của helper là chuẩn bị `OAuth2AuthenticationToken` với một principal tương ứng, authorities và thông tin client cần cho tình huống test. Với `oauth2Login()`, principal là `OAuth2User`; với `oidcLogin()`, principal là `OidcUser` chứa `OidcIdToken` giả lập. Thông tin này được chèn vào security context của request test, chứ không phải là kết quả ứng dụng vừa thực hiện một authorization code flow.

| Điều muốn kiểm tra | `oauth2Login()` | `oidcLogin()` |
| --- | --- | --- |
| Controller đọc `Authentication.getName()` | Có | Có |
| Rule `hasAuthority(...)` chấp nhận/từ chối | Có | Có |
| Đọc thuộc tính `OAuth2User` | Có | Có, qua `OidcUser` |
| Đọc claim của `OidcIdToken` giả lập | Không phải trọng tâm | Có |
| Tạo redirect tới IdP và kiểm tra tham số `state` | **Không** | **Không** |
| Gọi HTTP POST token endpoint để đổi code | **Không** | **Không** |
| Kiểm tra chữ ký ID token bằng JWK thật | Không áp dụng | **Không** |
| Xác minh `iss`, `aud`, `exp`, `nonce` như luồng login thật | Không | **Không** |
| Chứng minh IdP thật chấp nhận credentials | **Không** | **Không** |

Helper cũng không tự thao tác browser hoặc follow HTTP redirects. Ngay cả một test `MockMvc` sử dụng callback thật cũng không phải là trình duyệt thật: `MockMvc` mô phỏng HTTP request/response qua Servlet pipeline trong JVM. Phân biệt hai tầng này giúp chọn đúng công cụ.

## 3. Ứng dụng mẫu: xác thực OAuth2/OIDC để bảo vệ endpoint

Ví dụ dùng Spring Boot Servlet, JUnit Jupiter, MockMvc và Spring Security 6.x. Dependency điển hình:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Sử dụng phiên bản Spring Security do Spring Boot BOM quản lý. Code sau minh họa cấu hình cần có; trong dự án thật, có thể tách `ClientRegistrationRepository` sang cấu hình test.

### 3.1. SecurityFilterChain và ClientRegistration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BrowserLoginSecurityConfig {

    @Bean
    SecurityFilterChain browserSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Một `ClientRegistrationRepository` mẫu cho OIDC (đặt trong cấu hình riêng) có thể được tạo bằng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.IdTokenClaimNames;

@Bean
ClientRegistrationRepository clientRegistrationRepository() {
    ClientRegistration demoOidc = ClientRegistration
        .withRegistrationId("demo")
        .clientId("demo-client")
        .clientSecret("demo-secret-for-test-only")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid", "profile")
        .authorizationUri("https://idp.example.test/authorize")
        .tokenUri("https://idp.example.test/token")
        .jwkSetUri("https://idp.example.test/jwks")
        .issuerUri("https://idp.example.test")
        .userInfoUri("https://idp.example.test/userinfo")
        .userNameAttributeName(IdTokenClaimNames.SUB)
        .clientName("Demo OIDC")
        .build();

    return new InMemoryClientRegistrationRepository(demoOidc);
}
```

Đây là cấu hình **minh họa, không phải IdP đang hoạt động**. Các URL `example.test` sẽ không phục vụ code exchange. Muốn kiểm tra callback thật, cần thay các URL bằng mock HTTP server cục bộ hoặc môi trường IdP test đã sẵn sàng. Không đưa client secret production vào test.

Lưu ý: code `@Bean` trên phải nằm trong một class `@Configuration` phù hợp. Nếu ứng dụng đã có `ClientRegistrationRepository` từ `application.yml`, không tạo thêm một bean cùng mục đích một cách vô tình.

### 3.2. Controller quan sát principal và quyền

```java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class LoginDemoController {

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("name", authentication.getName());
    }

    @GetMapping("/api/oidc")
    Map<String, String> oidc(@AuthenticationPrincipal OidcUser user) {
        return Map.of("sub", user.getSubject());
    }

    @GetMapping("/api/reports")
    String reports() {
        return "reports-visible";
    }
}
```

Ở đây, `/api/me` chỉ cần đăng nhập; `/api/reports` đòi `SCOPE_reports.read`. Endpoint `/api/oidc` cho phép kiểm tra một `OidcUser` được truyền vào controller. Đây là tầng sử dụng authentication đã có, thích hợp cho helper.

## 4. Dùng oauth2Login() để kiểm tra behavior sau khi đăng nhập

Giả sử ứng dụng đã nhận được một `OAuth2User` tên Alice từ provider và muốn kiểm tra API trả đúng danh tính. Ta tạo principal giả lập, rồi đưa nó vào request:

```java
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OAuth2HelperTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void oauth2UserCanAccessProtectedEndpoint() throws Exception {
        OAuth2User alice = new DefaultOAuth2User(
            List.of(new SimpleGrantedAuthority("ROLE_USER")),
            Map.of("sub", "alice", "email", "alice@example.test"),
            "sub"
        );

        mockMvc.perform(get("/api/me")
                .with(oauth2Login().oauth2User(alice)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));
    }
}
```

**Bài test có giá trị:** controller xử lý được `OAuth2AuthenticationToken` chứa `OAuth2User`, danh tính có thể đến endpoint bảo vệ và được chuyển vào response đúng cách.

**Bài test chưa chứng minh:** `/oauth2/authorization/demo` đã trả redirect, `state` được lưu hay callback `/login/oauth2/code/demo` đã đổi code lấy token. Việc tạo `DefaultOAuth2User` trong test cũng không chứng minh provider đã thực sự trả những thuộc tính đó.

### 4.1. Kiểm tra phân quyền bằng authority giả lập

Ví dụ sau thuộc cùng class, cần thêm static import `content()` và `SecurityMockMvcRequestPostProcessors.oauth2Login` nếu tách riêng:

```java
@Test
void requestedScopeCanBeSimulated() throws Exception {
    mockMvc.perform(get("/api/reports")
            .with(oauth2Login().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")
            )))
        .andExpect(status().isOk());
}

@Test
void missingScopeIsForbiddenEvenWhenLoggedIn() throws Exception {
    mockMvc.perform(get("/api/reports")
            .with(oauth2Login().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            )))
        .andExpect(status().isForbidden());
}
```

Hai test chỉ kiểm tra điều kiện `hasAuthority("SCOPE_reports.read")`. Trong luồng đăng nhập OAuth2 thật, authorities có thể đến từ `OAuth2UserService`, `GrantedAuthoritiesMapper` hoặc ánh xạ tùy chỉnh. Helper cho phép **gán trực tiếp** các authority, vì vậy nó không kiểm tra việc chuyển scope/claim từ provider có chính xác hay không.

Đừng mặc định mọi OAuth2 Login đều sinh ra `SCOPE_...` giống resource server. Quy tắc authorities phụ thuộc kết quả login và cách mapping được cấu hình; test phải dựng đúng loại authority mà ứng dụng thực sự sử dụng.

## 5. Dùng oidcLogin(): claim giả lập không chứng minh ID token hợp lệ

OIDC bổ sung khái niệm **ID token** có các claim như `iss` (issuer), `sub` (subject), `aud` (audience), `exp` (expiration), `iat` (issued at), và đôi khi `nonce`. Với đăng nhập thật, ứng dụng phải xác minh ID token theo chính sách của OpenID Connect và cấu hình provider.

Helper `oidcLogin()` cho phép **tự tạo claim** của `OidcIdToken` ngay trong test:

```java
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
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OidcHelperTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void oidcHelperCreatesPrincipalWithChosenSubject()
            throws Exception {
        mockMvc.perform(get("/api/oidc")
                .with(oidcLogin()
                    .idToken(token -> token.claim("sub", "alice-oidc"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sub").value("alice-oidc"));
    }
}
```

`OidcIdToken` trong helper là **đối tượng Java chứa claims đã được chuẩn bị**. Nó không phải một compact ID token JWS vừa được tải từ token endpoint rồi kiểm tra chữ ký bằng public key của provider. Không có bước tra JWKS hay gọi `JwtDecoderFactory` trong request này.

### 5.1. Minh họa vì sao claim không được xác minh

Ngay cả khi helper được cấp claim `iss` hoặc `aud` không khớp ClientRegistration thật, test vẫn có thể đi vào controller bởi helper **không chạy bộ xác minh ID token OIDC**:

```java
@Test
void helperDoesNotVerifyIssuerOrAudience() throws Exception {
    mockMvc.perform(get("/api/oidc")
            .with(oidcLogin().idToken(token -> token
                .claim("sub", "alice-oidc")
                .claim("iss", "https://unrelated-provider.example.test")
                .claim("aud", List.of("other-client")))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.sub").value("alice-oidc"));
}
```

Với snippet tách riêng, import `java.util.List`. Ví dụ trên có ý nghĩa **minh họa ranh giới bảo mật của helper**, không phải gợi ý chấp nhận issuer/audience sai trong ứng dụng thật.

Sự khác biệt quan trọng:

- `oidcLogin().idToken(...)`: test tự cung cấp claims, Spring Security dùng principal đó để kiểm tra downstream behavior.
- Callback OIDC thật: ứng dụng nhận token response, giải mã/kiểm tra ID token từ provider, kiểm tra những ràng buộc OIDC cần thiết và chỉ sau đó tạo `OidcUser`.

Việc gọi `oidcLogin()` không chứng minh chữ ký RS256/ES256 hợp lệ, `exp` chưa hết hạn, `aud` có client ID hiện tại, `iss` đúng issuer hoặc `nonce` khớp với authorization request. Các thuộc tính đó phải được kiểm tra trong đường thực thi login thật, hoặc ở một bài test riêng trực tiếp cho bộ decoder/validator thật.

### 5.2. Khi nào nên dùng helper cho OIDC?

Đây là các trường hợp rất phù hợp:

| Câu hỏi của bài test | Dùng `oidcLogin()` được không? | Assertion gợi ý |
| --- | --- | --- |
| Controller đọc `sub`/email từ `OidcUser` đúng không? | Có | Giá trị JSON/trường trả về |
| Service có nhận đúng principal? | Có | Kết quả nghiệp vụ |
| Quyền truy cập theo authority được ánh xạ sẵn? | Có | 200/403 |
| Rule theo claim tùy biến hoạt động khi principal có claim? | Có | 200/403 hoặc logic nghiệp vụ |
| IdP đã phát hành ID token ký bằng khóa hợp lệ? | Không | Decoder thật chấp nhận/từ chối token |
| Callback kiểm tra issuer, audience, nonce, expiry? | Không | Login integration test với token response thật |
| Redirect chứa state và callback dùng đúng session? | Không | HTTP redirect/callback test |

Nếu mục tiêu là phân quyền hoặc logic của controller, helper giúp bài test dễ đọc và tập trung. Nếu mục tiêu là chứng minh **cơ chế đăng nhập bảo mật**, cần đi qua những bước mà helper bỏ qua.

## 6. Kiểm thử redirect thực của OAuth2AuthorizationRequestRedirectFilter

Một HTTP request tới URL khởi động login là bước đầu của integration test:

```http
GET /oauth2/authorization/demo HTTP/1.1
```

Với `ClientRegistration` có registrationId `demo`, `OAuth2AuthorizationRequestRedirectFilter` sẽ xây authorization request và trả redirect tới provider. Ta có thể kiểm tra **redirect** qua `MockMvc` mà chưa cần gọi provider thật.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OAuth2AuthorizationRedirectTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginStartRedirectsToConfiguredProvider() throws Exception {
        mockMvc.perform(get("/oauth2/authorization/demo"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                HttpHeaders.LOCATION,
                containsString(
                    "https://idp.example.test/authorize"
                )
            ))
            .andExpect(header().string(
                HttpHeaders.LOCATION,
                containsString("state=")
            ))
            .andExpect(header().string(
                HttpHeaders.LOCATION,
                containsString("client_id=demo-client")
            ));
    }
}
```

Đây là request qua **filter redirect thực** của ứng dụng. Nó chứng minh bước tạo authorization request và trả `302 Location` với provider/client được cấu hình, nhưng **chưa** chứng minh đổi code hoặc xác thực ID token. `MockMvc` không tự đi theo URL `Location` để mở trang IdP.

Cần kiểm tra thêm khi triển khai thật:

- `response_type=code` và `redirect_uri` tương ứng với client registration, chú ý URL encoding.
- `scope=openid` nếu bắt đầu OIDC login.
- `state` có mặt, ngẫu nhiên thích hợp và được lưu trong authorization request repository.
- `nonce` cho OIDC nếu library/flow tạo nonce; `code_challenge` khi PKCE được bật/cần dùng.
- Ứng dụng không rò rỉ client secret vào browser redirect.

Các tham số có thể được URL-encode và thứ tự khác nhau; thay vì so sánh một URL literal dài, nên parse query parameters rồi assert giá trị có ý nghĩa. Chỉ hardcode những giá trị thực sự là contract của cấu hình test.

### 6.1. Vì sao state và session quan trọng?

Khi browser bắt đầu login, Spring Security tạo authorization request, thường lưu trong HTTP session, rồi redirect đến IdP. Callback tới ứng dụng cần mang `state` khớp giá trị đã tạo.

Một test callback không có session hoặc có `state` sai **không tương đương** với một Authorization Code Flow thành công. Các cơ chế bảo vệ callback cần được kiểm thử riêng thay vì bỏ qua để lấy được HTTP 200.

Có thể lấy session từ request bắt đầu login:

```java
MvcResult start = mockMvc.perform(
        get("/oauth2/authorization/demo"))
    .andExpect(status().is3xxRedirection())
    .andReturn();

MockHttpSession session =
    (MockHttpSession) start.getRequest().getSession(false);

String location = start.getResponse().getRedirectedUrl();
// Trích tham số state từ location bằng một URI/query parser
// và dùng cùng session khi mô phỏng callback.
```

Đoạn này là phần chuẩn bị, không phải test callback hoàn chỉnh. Import `MvcResult` từ `org.springframework.test.web.servlet` và `MockHttpSession` từ `org.springframework.mock.web`. Nếu repository/session strategy được tùy biến, cách giữ authorization request phải theo cấu hình đó.

## 7. Kiểm thử authorization code exchange tại callback

Bước tiếp theo của flow thật là:

```http
GET /login/oauth2/code/demo?code=test-authorization-code&state=<state-dung> HTTP/1.1
Cookie: JSESSIONID=<session-cua-lan-bat-dau>
```

`OAuth2LoginAuthenticationFilter` kiểm tra callback và thông tin authorization request đã lưu, sau đó client trao đổi authorization code với token endpoint. Khi login OIDC, kết quả token endpoint có thể chứa `id_token` và ứng dụng phải xử lý/kiểm tra ID token.

**Muốn chứng minh code exchange thực sự xảy ra, chỉ dùng `oidcLogin()` hoặc `oauth2Login()` là không đủ.** Một integration test cần dựng đường callback thật cùng một HTTP stub cho token endpoint.

Một kịch bản kiểm thử điển hình:

1. Khởi động local HTTP stub server ở port động cho endpoint `/authorize`, `/token`, `/jwks` và `/userinfo` (nếu dùng).
2. Cấp `ClientRegistration` trỏ đến local stub; giữ `client-id`, `redirect-uri` và OIDC metadata nhất quán.
3. Gửi `GET /oauth2/authorization/demo` bằng `MockMvc`, ghi lại HTTP session và tham số `state` từ redirect.
4. Mô phỏng callback `GET /login/oauth2/code/demo?code=...&state=...` bằng **cùng session**.
5. Cho stub token endpoint trả OAuth2 token response; với OIDC, trả `id_token` đã ký bằng key test và expose public JWK qua `/jwks`.
6. Kiểm tra stub đã nhận HTTP POST trao đổi code: phương thức, đường dẫn, body có `grant_type=authorization_code`, `code`, `redirect_uri`, client authentication/PKCE tùy cấu hình.
7. Kiểm tra callback thành công hay thất bại, session authentication và endpoint bảo vệ ở request tiếp theo.

Khi test chạy với HTTP server cục bộ, bạn có thể assert:

| Bước | Bằng chứng cần thấy |
| --- | --- |
| Authorization request | Redirect thật chứa `state`, `client_id`, `redirect_uri` |
| State binding | Callback dùng đúng session và đúng `state` được chấp nhận; state sai bị từ chối |
| Token exchange | Local stub nhận POST `/token` và đúng authorization code |
| ID token OIDC | Token được decoder/validator thật chấp nhận hoặc từ chối |
| Session sau login | Request mới mang session thành công truy cập tài nguyên |
| Failure handling | Code sai, token endpoint lỗi hoặc ID token sai khiến login không được xác thực |

Nếu chỉ mock `OAuth2AccessTokenResponseClient` để trả sẵn token, test có thể chứng minh callback filter đi tới client abstraction, nhưng chưa chứng minh HTTP POST/credentials. Nếu dùng token endpoint stub thật và decoder thật, phạm vi kiểm tra mở rộng đến giao tiếp HTTP và xác minh chữ ký/claims như cấu hình.

### 7.1. Các tình huống thất bại cần có

**State không khớp:** Callback mang `state` khác giá trị trong authorization request. Luồng phải từ chối thay vì đổi code thành session đăng nhập. Assertion nên kiểm tra không có authentication hợp lệ và failure handler nhận lỗi tương ứng. Với cấu hình login mặc định, kết quả thường là redirect đến URL lỗi như `/login?error`; nếu handler tùy biến, trạng thái/URL cũng thay đổi.

**Authorization code sai hoặc đã dùng:** Token endpoint trả lỗi OAuth2 (thường `invalid_grant`). Ứng dụng không được tạo phiên đăng nhập thành công. Stub phải ghi nhận token request khi đã đi tới bước exchange.

**Client credentials/redirect URI sai:** Token endpoint có thể từ chối token request; test phải kiểm tra request chứa cấu hình client mong muốn, không chỉ kiểm tra UI redirect.

**Code hợp lệ nhưng ID token không hợp lệ:** Token endpoint trả token response với ID token có chữ ký sai, issuer/audience sai hoặc hết hạn. Khi dùng decoder thật/validator đã được cấu hình, OIDC login phải thất bại trước khi tạo principal hợp lệ.

**Nonce không khớp:** Nếu OIDC flow tạo và yêu cầu nonce, ID token phải mang nonce tương ứng với authorization request. Test callback thật cần dựng nonce đúng từ phiên mở đầu, rồi có thể tạo một negative case nonce sai. `oidcLogin()` không cung cấp bằng chứng của phép đối chiếu này.

Không nên “sửa” test bằng cách vô hiệu hóa `state`, `nonce`, ID token validation hoặc thay tất cả handler thành `permitAll`. Làm vậy sẽ thay đổi cơ chế cần kiểm chứng.

## 8. Kiểm thử xác minh ID token thật cần những thành phần nào?

OIDC ID token thường là JWT có cấu trúc ba phần (header, payload, signature), được ký bằng thuật toán mà client tin cậy. Để thử xác minh thật, cần:

- Một cặp khóa kiểm thử hoặc JWK phù hợp với thuật toán đã cấu hình; private key để ký ID token mẫu, public key được công bố tại local JWKS endpoint.
- ID token có chữ ký hợp lệ, `iss` của IdP test, `aud` chứa đúng `client_id`, `sub` và thời gian hợp lệ; `nonce` nếu flow yêu cầu.
- Decoder/validator **thật** được dùng trong callback OIDC, với cấu hình issuer, JWK Set URI và các quy tắc OIDC đúng.
- Callback thật sử dụng authorization request/state đã lưu và token endpoint trả `id_token` đó.

Sau đó kiểm tra những thay đổi độc lập:

| Biến thể ID token | Mục đích | Kỳ vọng |
| --- | --- | --- |
| Ký đúng bằng private key test, claims hợp lệ | Happy path | OIDC login thành công |
| Sửa payload nhưng giữ chữ ký cũ | Chứng minh kiểm tra chữ ký | Login bị từ chối |
| `iss` khác provider được tin cậy | Kiểm tra issuer | Login bị từ chối |
| `aud` không chứa client ID | Kiểm tra audience | Login bị từ chối |
| `exp` đã qua | Kiểm tra thời hạn | Login bị từ chối |
| `nonce` sai khi nonce được yêu cầu | Kiểm tra liên kết authorization request | Login bị từ chối |
| JWKS không có key phù hợp | Kiểm tra lỗi khóa | Login thất bại; phân biệt lỗi token với lỗi hạ tầng |

**Không sử dụng `oidcLogin().idToken(...)` để kết luận các biến thể này được decoder từ chối.** Helper xây một `OidcIdToken` Java object từ claims và gắn nó vào principal; không thực hiện bước kiểm tra compact JWS.

Một test đơn vị riêng cho decoder có thể kiểm tra chữ ký và claims mà không cần browser redirect. Nhưng test đó **không** chứng minh callback/filter đã gọi decoder. Integration test callback là nơi hai bằng chứng giao nhau.

### 8.1. Tránh nhầm mock decoder với decoder thật

Có ba mức mô phỏng khác nhau:

1. **Dùng `oidcLogin()`:** không gọi decoder, chỉ tạo user và claims phục vụ phân quyền.
2. **Dùng callback thật nhưng mock decoder/JWT decoder factory:** có thể kiểm tra callback đã yêu cầu decode/validate và xử lý exception; vẫn chưa kiểm tra chữ ký.
3. **Dùng callback thật với decoder và test JWK/token đã ký:** kiểm tra thực tế việc xác minh chữ ký và claims theo cấu hình hiện hành.

Nếu mock trả ID token đã chấp nhận, một ID token có chữ ký sai vẫn có thể “đăng nhập thành công” trong test tùy cách mock. Điều này là hệ quả bình thường của việc thay decoder; không được trình bày kết quả như bằng chứng xác thực token thật.

## 9. Session: helper có giống một lần login thành công thật không?

Trong browser login, Spring Security thường lưu authentication sau callback thành công, rồi browser giữ session cookie để gửi các request tiếp theo. Với helper `oauth2Login()/oidcLogin()`, authentication được thiết lập cho **request mà test tạo ra**. Nó không tự sinh chuỗi redirect, callback hay cuộc trao đổi token.

Ví dụ:

```java
mockMvc.perform(get("/api/me").with(oidcLogin()))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/me"))
    .andExpect(status().is3xxRedirection());
```

Khi test gọi `perform()` lần hai mà không gửi session/authentication, request đó không đương nhiên được xem là đã đăng nhập. Trong cấu hình login mặc định, truy cập tài nguyên bảo vệ khi chưa xác thực thường chuyển hướng tới trang login; tuy nhiên status cụ thể phụ thuộc entry point, content negotiation và các chain của ứng dụng.

Đối với test callback thật, thường cần giữ session đã dùng để lưu authorization request, sau đó lấy session/cookie của response thành công và dùng lại ở request kế tiếp. Test này chứng minh behavior session liên quan tới login, điều mà một assertion 200 với helper không tự chứng minh.

Khi làm bài thực hành, hãy phân biệt:
- **Request-local authentication:** `.with(oidcLogin())` cung cấp principal cho một request.
- **Session sau authorization code flow:** callback thành công tạo/cập nhật security context và session theo cấu hình của ứng dụng.
- **Browser end-to-end:** browser gửi cookie thật qua HTTP/TLS và đi theo redirect tới IdP.

## 10. Các dấu hiệu test “xanh” nhưng sai mục tiêu

### 10.1. Chỉ test trạng thái 200

```java
mockMvc.perform(get("/api/me").with(oidcLogin()))
    .andExpect(status().isOk());
```

Test này phù hợp khi mục tiêu là bảo vệ URL với user đã xác thực. Nhưng nó không chứng minh login thành công với authorization code hợp lệ. Để kiểm tra login flow, phải quan sát redirect/callback/token exchange và session.

### 10.2. Đưa một ID token “giả” vào helper rồi xem là đã xác thực chữ ký

```java
mockMvc.perform(get("/api/oidc")
        .with(oidcLogin().idToken(t -> t
            .claim("sub", "alice")
            .claim("iss", "https://untrusted.example.test"))))
    .andExpect(status().isOk());
```

Helper không cần JWT string có chữ ký. Nó không xác nhận issuer này có trong danh sách provider được tin cậy. Đoạn test chỉ chứng minh endpoint làm việc được với principal chứa claims mà test tự cấp.

### 10.3. Không chạy Spring Security filters

Với Boot thông thường, `@SpringBootTest` và `@AutoConfigureMockMvc` đăng ký filters phù hợp. Nếu tự dựng `MockMvc`, cần tích hợp Spring Security:

```java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;

MockMvc mvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
```

Dùng `MockMvcBuilders.standaloneSetup(controller)` đơn thuần hoặc `@AutoConfigureMockMvc(addFilters = false)` có thể bỏ qua redirect filter, login filter và authorization. Một test URL bắt đầu login không đi qua đúng filter chain không thể chứng minh redirect thực.

### 10.4. Mong MockMvc tự gọi IdP sau HTTP 302

`MockMvc` trả response của request đang thực thi; nó không tự mở trang IdP hay gọi URL `Location`. Nếu chỉ test bước đầu `GET /oauth2/authorization/demo` và nhận `302`, đó là **redirect test**, chưa phải code exchange test.

### 10.5. Gửi callback mà không giữ state và session

Callback `/login/oauth2/code/demo` không thể được coi là độc lập với bước bắt đầu login. `state` và authorization request đã lưu được dùng để liên kết hai bước. Nếu chỉ tự gắn `code=foo` và `state=foo` mà không có session phù hợp, lỗi hoặc redirect xảy ra không chứng minh token endpoint xử lý code thành công hay thất bại.

### 10.6. Mock toàn bộ IdP rồi tuyên bố đã kiểm tra thuật toán ký

Mock `OAuth2UserService`, `OAuth2AccessTokenResponseClient` hoặc decoder có thể giúp test nhanh một đoạn pipeline. Nhưng từng mock loại bỏ trách nhiệm của thành phần tương ứng. Muốn xác minh signature/issuer/audience thực, phải dùng decoder thật với token đã ký và trust material test phù hợp.

### 10.7. Nhầm OAuth2 Login với Bearer JWT authentication

`oidcLogin()` là helper cho **OIDC client login**; `jwt()` của spring-security-test là helper cho **Resource Server JWT**. Chúng tạo các authentication/principal khác nhau và không gọi cùng bộ filter. Hãy chọn helper theo vai trò của ứng dụng và đường request cần kiểm tra.

## 11. Đối chiếu nhanh với WebFlux và WebTestClient

Trong ứng dụng Reactive, Spring Security Test có các configurer tương ứng như `SecurityMockServerConfigurers.mockOAuth2Login()` và `mockOidcLogin()`. Chúng giúp `WebTestClient` tạo authentication giả lập cho request, tương tự `oauth2Login()/oidcLogin()` ở Servlet.

Ví dụ ý tưởng:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;

webTestClient.mutateWith(mockOidcLogin())
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
```

Đây vẫn là bài test downstream authorization. Configurer Reactive không đi tới authorization server, không đổi code và không kiểm tra chữ ký ID token thật chỉ vì request thành công. Khi cần kiểm tra browser login flow trên WebFlux, phải đi qua các reactive security web filters, lưu trạng thái/cookies cần thiết và stub HTTP provider tương ứng.

Không sao chép nguyên các API Servlet `MockMvc` sang WebTestClient: tên helper và cách thiết lập security context khác nhau. Điều giống nhau là **ranh giới** giữa mock authenticated user và thực thi giao thức OAuth2/OIDC.

## 12. Chọn tầng kiểm thử theo yêu cầu

Một bộ test cân bằng thường bao gồm:

| Mục tiêu | Công cụ phù hợp | Bằng chứng cần thu |
| --- | --- | --- |
| Controller nhận `OAuth2User` / `OidcUser` | `oauth2Login()` / `oidcLogin()` | Response, principal, claims |
| Quyền truy cập theo authorities | Helper + authorities giả lập | 200/403 |
| Bắt đầu login, đúng IdP | `MockMvc GET /oauth2/authorization/{registrationId}` | 302, `Location`, `state`, client/redirect |
| Callback kiểm tra state | Login filter thật + session trước đó | State sai bị từ chối, đúng được xử lý |
| Code exchange thực | Callback thật + token endpoint HTTP stub | POST `/token`, code/redirect/client authentication |
| User-info integration | HTTP stub + `OAuth2UserService`/`OidcUserService` thật | HTTP request và mapping attributes |
| ID token signature, issuer, audience, expiry | Decoder/validators thật với JWK/token đã ký | Token tốt chấp nhận, token xấu bị từ chối |
| OIDC nonce correlation | Bắt đầu login và callback đầy đủ | Nonce không khớp gây thất bại khi được yêu cầu |
| Session sau callback | MockMvc nhiều requests chia sẻ session | Sau login có quyền, logout/mất session hết quyền |
| Browser và IdP end-to-end | Browser automation + IdP test | Redirect/cookie/TLS/consent theo môi trường thật |

Không cần đưa tất cả tầng vào mọi test. Phần lớn biến thể quyền truy cập nên được kiểm tra nhanh bằng helper. Chỉ vài integration test chuyên biệt có thể cung cấp bằng chứng cho đường redirect, code exchange, xác thực ID token và session.

### Bài tập thực hành

Tạo ba nhóm test cho endpoint `/api/oidc`:

1. **Mock principal:** Gửi request với `oidcLogin().idToken(t -> t.claim("sub", "alice"))`, kiểm tra endpoint trả `alice`. Ghi rõ đây là kiểm tra xử lý principal đã được tạo.
2. **Authorization redirect:** Gửi `GET /oauth2/authorization/demo`, kiểm tra `302`, `Location` chứa provider đúng, `state` và `client_id`. Giải thích vì sao bước này chưa chứng minh token exchange.
3. **Callback + ID token:** Dùng session/state từ bước 2; local HTTP stub nhận POST `/token` và trả ID token ký bằng key test. Kiểm tra một ID token hợp lệ được chấp nhận, một ID token có issuer/audience/chữ ký sai bị từ chối bởi decoder thật. Ghi nhận session ở request sau login thành công.

Sau đó thêm một callback có `state` sai và xác nhận ứng dụng không tạo phiên đăng nhập hợp lệ. Thử thay decoder thật bằng mock, rồi chỉ ra bằng chứng nào về chữ ký/issuer/audience đã mất.

**Tiêu chí hoàn thành:** Người học phân biệt được ba mệnh đề độc lập: **(1)** helper tạo một người dùng đã xác thực phục vụ kiểm thử quyền, **(2)** redirect và callback thực đi qua Spring Security login filters, và **(3)** ID token thật được kiểm tra bởi decoder/validator với khóa và claims theo cấu hình. Kết quả `200` của `oidcLogin()` chỉ đủ chứng minh mệnh đề đầu tiên; muốn chứng minh hai mệnh đề còn lại phải có các test chuyên biệt cho giao thức và token.

