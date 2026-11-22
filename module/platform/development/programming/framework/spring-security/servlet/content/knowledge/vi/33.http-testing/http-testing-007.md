# oauth2Login, oidcLogin, jwt và opaqueToken: phạm vi giả lập khi kiểm thử HTTP

**Ngữ cảnh:** Spring Security **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit 5 và MockMvc. Bốn hàm `oauth2Login()`, `oidcLogin()`, `jwt()`, `opaqueToken()` trong **`spring-security-test`** là các *request post-processor* giúp dựng **Authentication giả lập** cho một HTTP request kiểm thử. Hiểu đúng phạm vi của chúng là điều kiện quan trọng để không viết một bộ test “xanh” nhưng lại bỏ qua lỗi thực tế trong OAuth2/OIDC login, JWT validation hoặc opaque-token introspection.

## 1. Mục tiêu học tập và bức tranh lớn

Sau bài này, bạn có thể:

1. Phân biệt **OAuth2 Login / OIDC login** (đăng nhập người dùng vào web app) với **OAuth2 Resource Server** (xác minh bearer access token cho API).
2. Chọn đúng `oauth2Login()`, `oidcLogin()`, `jwt()` hoặc `opaqueToken()` theo **kiểu principal/Authentication** mà endpoint thực sự cần.
3. Dùng MockMvc kiểm tra **controller, method security, authorities, route authorization**, cả trường hợp được phép và bị từ chối.
4. Nhận ra những thứ **không** được bốn post-processor kiểm tra: redirect, state, nonce, chữ ký JWT, issuer/audience/time, token introspection, provider availability và token revocation.
5. Thiết kế thêm integration tests thực sự đi qua Spring Security authentication filters/decoders hoặc một IdP giả lập đáng tin cậy khi cần kiểm chứng boundary đó.

### 1.1 Bốn cách giả lập — bốn ý nghĩa khác nhau

| Post-processor trong MockMvc | Authentication/principal được giả lập | Thích hợp khi test | Không tự kiểm tra |
| --- | --- | --- | --- |
| `oauth2Login()` | `OAuth2AuthenticationToken` với `OAuth2User` | MVC web app đã đăng nhập qua một OAuth2 provider; controller đọc user attributes/authorities. | Authorization redirect, consent, code exchange, user-info HTTP call. |
| `oidcLogin()` | OAuth2 login authentication với `OidcUser` và ID token/user-info giả lập | MVC app dùng OIDC, controller cần `@AuthenticationPrincipal OidcUser` hoặc OIDC claims. | Chữ ký/issuer/audience/nonce/expiry của **ID token thật**, OIDC discovery, JWKS, token endpoint. |
| `jwt()` | `JwtAuthenticationToken` chứa một `Jwt` giả lập | API dựa trên JWT principal và authorities. | `BearerTokenAuthenticationFilter` xử lý token thật, `JwtDecoder`, chữ ký, issuer/audience, token expiry, chuyển đổi claims thực tế nếu authorities được set trực tiếp. |
| `opaqueToken()` | `BearerTokenAuthentication` với `OAuth2AuthenticatedPrincipal` giả lập | API dùng opaque bearer access token, cần principal attributes/scopes. | Gọi `OpaqueTokenIntrospector` đến authorization server, active/revoked/expired, sự cố mạng, HTTP auth introspection. |

Cả bốn tạo một trạng thái “**giả sử request đã xác thực thành công**”. Chúng rất hữu ích cho **kiểm thử authorization và behavior sau authentication**, nhưng **không phải** công cụ chứng minh security filter đã đọc và xác minh credential ngoài đời thực.

### 1.2 Đừng nhầm OAuth2 Client, OAuth2 Login, OIDC và Resource Server

- **OAuth2 Client:** ứng dụng quản lý quyền truy cập và access token để gọi một resource server bên ngoài. Nó có thể chạy cùng người dùng hoặc bằng grant `client_credentials`.
- **OAuth2 Login:** ứng dụng Spring MVC cho user đăng nhập qua một provider bên ngoài, sau đó có `Authentication` trong `SecurityContext` và thường duy trì phiên bằng cookie.
- **OpenID Connect (OIDC):** lớp xác thực danh tính trên OAuth 2.0, sử dụng ID token theo các ràng buộc chuẩn như `iss`, `sub`, `aud`, `exp`, `nonce` (nếu có).
- **OAuth2 Resource Server:** API bảo vệ endpoint bằng bearer **access token**, tự xác minh JWT hoặc introspect opaque token và kiểm tra quyền.

Một người dùng login thành công bằng OIDC không có nghĩa API tự chấp nhận mọi bearer token. Một `JwtAuthenticationToken` trong test cũng không chứng minh web app có OIDC login. **Đọc Authentication mà endpoint mong đợi trước khi chọn post-processor.**

## 2. Request post-processor hoạt động ở lớp nào?

Với MockMvc, ta có thể thực hiện:

```java
mvc.perform(get("/api/report").with(jwt()));
```

`with(...)` sửa **MockHttpServletRequest** phục vụ kiểm thử. Các security post-processors có thể tạo và gắn `SecurityContext`/`Authentication` vào request để Spring Security filters và controller sử dụng khi MockMvc xử lý request. Điều này **khác** gửi raw HTTP `Authorization: Bearer ...` rồi để resource server tự decode token.

Trong bài, “giả lập” nghĩa là **thay đầu vào tại biên authentication bằng một principal đã được dựng sẵn**, chứ không phải giả lập mọi giao thức liên quan.

```text
A. Test dùng post-processor (identity đã được thiết lập)
JUnit + MockMvc
  └─ get("/api/report").with(jwt())
       └─ request có mock SecurityContext/JwtAuthenticationToken
            └─ SecurityFilterChain / AuthorizationFilter
                 └─ Controller + service / method security
                    [Không cần JWT chữ ký thật hoặc JwtDecoder mạng]

B. Test đi qua bearer token filter thực sự
JUnit + MockMvc
  └─ get("/api/report")
       .header("Authorization", "Bearer eyJ...")
       └─ BearerTokenAuthenticationFilter
            └─ JwtDecoder hoặc OpaqueTokenIntrospector
                 └─ Authentication nếu token hợp lệ
                      └─ AuthorizationFilter
                           └─ Controller
```

Tương tự, `oauth2Login()` **không** khiến MockMvc trình duyệt redirect sang IdP, login, nhận authorization code hay kiểm tra state; nó tạo kết quả authentication thích hợp để test **phần phía sau login**.

**Điều kiện quan trọng:** các ví dụ sử dụng MockMvc **có tích hợp Spring Security filter chain**. Với Spring Boot, `@SpringBootTest` + `@AutoConfigureMockMvc` là một cách thuận tiện. Nếu tự dựng `MockMvcBuilders.standaloneSetup(...)` mà không tích hợp Spring Security qua `springSecurity()`, post-processor có thể không hoạt động theo cách mong muốn. Không kết luận “test đã kiểm tra security” khi filters bị vô tình loại khỏi request.

## 3. Lựa chọn post-processor từ endpoint

Giả sử dự án có:

- `GET /web/identity`: trả kiểu danh tính sau login (OAuth2 user hoặc OIDC user).
- `GET /web/subject`: yêu cầu `OidcUser`, trả `sub`.
- `GET /api/report`: chỉ cho caller có `SCOPE_reports.read`.
- `GET /api/admin`: chỉ cho caller có `SCOPE_admin`.
- `POST /web/update`: cập nhật thông tin trong phiên web, vẫn cần CSRF token.

Tại tầng **controller/authorization**, bốn request post-processor giúp tái hiện những trường hợp sau:

| Cần kiểm tra | Chọn | Vì sao |
| --- | --- | --- |
| Controller sử dụng `OAuth2User` sau OAuth2 Login | `oauth2Login()` | Mock principal kiểu OAuth2 user. |
| Controller đọc `OidcUser.getIdToken()` hoặc `getSubject()` | `oidcLogin()` | Có mock OIDC ID token/principal. |
| API authorize bằng `SCOPE_reports.read` với JWT-backed principal | `jwt().authorities(...)` | Chỉ định authorities chính xác cho testcase. |
| API authorize bằng scope từ opaque token | `opaqueToken().authorities(...)` | Dựng bearer principal và authorities. |
| Trả 403 khi thiếu authority | Cùng processor nhưng authorities thiếu | Test chính sách `hasAuthority`. |
| Test chỉ “có user” mà không cần OAuth2 type | `user(...)` hoặc `@WithMockUser` có thể đủ | Không cần giả làm OAuth/OIDC để kiểm tra mọi route. |
| Kiểm tra chữ ký JWT, `aud`, `iss`, `exp` | **Không dùng `jwt()` làm bằng chứng duy nhất** | Gửi bearer header qua resource server + decoder thực, hoặc test decoder phù hợp. |
| Kiểm tra opaque token active/revoked/introspection | **Không chỉ dùng `opaqueToken()`** | Cần introspector/stub server hoặc IdP test. |
| Kiểm tra authorization code, `state`, redirect URI | **Không chỉ dùng `oauth2Login()/oidcLogin()`** | Cần test flow với OAuth2/OIDC client filter và provider giả lập/kiểm soát. |

Nhiều bài test có thể dùng **cùng endpoint** với hai processor khác nhau. Điều này tốt để kiểm chứng authorization hoạt động cho nhiều principal types, **nhưng không biến hai cơ chế authentication production thành tương đương**.

## 4. Ví dụ chạy được: cấu hình Spring Boot, Controller và MockMvc

Ví dụ tối thiểu sau cố ý **không cấu hình OAuth2 Login hoặc Resource Server authentication flows thật**. Ta chỉ cấu hình **authorization** và HTTP Basic entry point để tập trung vào phạm vi của request post-processors. Đó chính là chủ đích giáo dục: test có thể PASS nhờ mock principal ngay cả khi app **chưa có** một IdP, JWT decoder hay opaque-token introspection thật.

Tạo dự án Gradle từ Spring Initializr với **Java 17+, Spring Boot 3.x, Spring Web, Spring Security, Spring Boot Starter Test** và thêm `spring-security-test`. Các file Java cùng package `com.example.authmock`.

### 4.1 Dependencies

Đoạn `build.gradle` minh họa các dependencies cần có, giữ nguyên plugins và repositories chuẩn của dự án Spring Boot do Initializr tạo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không cần chạy IdP thật hay introspection server để thực hiện **bộ MockMvc test giả lập** này. Khi chuyển sang integration test của OAuth2/OIDC/resource-server thật, phải thêm module và configuration tương ứng.

### 4.2 SecurityConfig.java

**`src/main/java/com/example/authmock/SecurityConfig.java`**

```java
package com.example.authmock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/web/identity",
                    "/web/subject"
                ).authenticated()
                .requestMatchers(
                    HttpMethod.POST, "/web/update"
                ).authenticated()
                .requestMatchers(
                    HttpMethod.GET, "/api/report"
                ).hasAuthority("SCOPE_reports.read")
                .requestMatchers(
                    HttpMethod.GET, "/api/admin"
                ).hasAuthority("SCOPE_admin")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Không bật oauth2Login hay oauth2ResourceServer ở demo này.
        // CSRF protection mặc định vẫn áp dụng với POST.
        return http.build();
    }
}
```

**Các điểm cần chú ý:**

1. `/web/identity` chỉ yêu cầu một Authentication hợp lệ.
2. `/api/report` và `/api/admin` yêu cầu **authority chính xác**. Trong Spring, `hasAuthority("SCOPE_reports.read")` không tự chuyển thành `ROLE_reports.read`; scope và role là hai quy ước khác nhau.
3. `httpBasic(...)` chỉ tạo một authentication entry point dễ kiểm thử cho request chưa đăng nhập; **không** biến ứng dụng thành OAuth2 Resource Server.
4. POST `/web/update` vẫn phải vượt qua CSRF protection nếu sử dụng chính sách mặc định của Spring Security.
5. Việc MockMvc dùng `jwt()`/`opaqueToken()` để truy cập `/api/report` **không chứng minh** endpoint production đã biết parse bearer token. Đây là test authorizations trong điều kiện đã có mock Authentication.

### 4.3 AuthController.java

**`src/main/java/com/example/authmock/AuthController.java`**

```java
package com.example.authmock;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.stream.Collectors;

@RestController
public class AuthController {

    @GetMapping("/web/identity")
    public String webIdentity(Authentication auth) {
        Object principal = auth.getPrincipal();

        if (principal instanceof OidcUser) {
            return "oidc";
        }
        if (principal instanceof OAuth2User) {
            return "oauth2";
        }
        return "other";
    }

    @GetMapping("/web/subject")
    public String oidcSubject(@AuthenticationPrincipal OidcUser user) {
        return user.getSubject();
    }

    @GetMapping("/api/report")
    public String report(Authentication auth) {
        return auth.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }

    @PostMapping("/web/update")
    public String update() {
        return "updated";
    }
}
```

Controller đọc principal theo **kiểu thực tế** mà post-processor cung cấp: `OidcUser` là một OAuth2 user với thông tin ID token và các claim OIDC, vì thế phải kiểm tra `instanceof OidcUser` **trước** `instanceof OAuth2User` nếu muốn phân biệt. `/api/report` trả authorities để testcase dễ đối chiếu; production có thể trả nội dung nghiệp vụ thay vì công bố toàn bộ danh sách quyền.

### 4.4 Application.java

**`src/main/java/com/example/authmock/Application.java`**

```java
package com.example.authmock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Đây là Spring Boot project, không biên dịch độc lập bằng `javac` nếu thiếu Spring classpath. Dùng Gradle wrapper:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Kết quả đúng là các **JUnit tests PASS** nếu project/dependencies đúng; không đoán một transcript `BUILD SUCCESSFUL` hay số lượng test từ một môi trường chưa chạy.

## 5. MockMvc tests dùng đủ bốn post-processor

**`src/test/java/com/example/authmock/AuthRequestPostProcessorTest.java`**

```java
package com.example.authmock;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthRequestPostProcessorTest {

    @Autowired
    MockMvc mvc;

    @Test
    void oauth2LoginGivesOAuth2Principal() throws Exception {
        mvc.perform(get("/web/identity").with(oauth2Login()))
            .andExpect(status().isOk())
            .andExpect(content().string("oauth2"));
    }

    @Test
    void oidcLoginGivesOidcUserAndMockIdTokenClaims()
            throws Exception {

        mvc.perform(
            get("/web/identity").with(oidcLogin())
        )
            .andExpect(status().isOk())
            .andExpect(content().string("oidc"));

        mvc.perform(
            get("/web/subject").with(
                oidcLogin().idToken(
                    token -> token.claim("sub", "oidc-account-17")
                )
            )
        )
            .andExpect(status().isOk())
            .andExpect(content().string("oidc-account-17"));
    }

    @Test
    void jwtAllowsRequiredAuthority() throws Exception {
        mvc.perform(
            get("/api/report").with(
                jwt()
                    .jwt(token -> token.claim("sub", "jwt-account"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_reports.read")
                    )
            )
        )
            .andExpect(status().isOk())
            .andExpect(content().string("SCOPE_reports.read"));
    }

    @Test
    void opaqueTokenAllowsRequiredAuthority() throws Exception {
        mvc.perform(
            get("/api/report").with(
                opaqueToken()
                    .attributes(
                        attrs -> attrs.put("sub", "opaque-account")
                    )
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_reports.read")
                    )
            )
        )
            .andExpect(status().isOk())
            .andExpect(content().string("SCOPE_reports.read"));
    }

    @Test
    void jwtWithWrongAuthorityIsForbidden() throws Exception {
        mvc.perform(
            get("/api/report").with(
                jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_other")
                )
            )
        )
            .andExpect(status().isForbidden());
    }

    @Test
    void opaqueTokenCannotAccessAdminWithoutAdminScope()
            throws Exception {

        mvc.perform(
            get("/api/admin").with(
                opaqueToken().authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                )
            )
        )
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedRequestIsRejected() throws Exception {
        mvc.perform(get("/api/report"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void fakeLoginDoesNotAutomaticallySupplyCsrfToken()
            throws Exception {

        mvc.perform(
            post("/web/update").with(oauth2Login())
        )
            .andExpect(status().isForbidden());

        mvc.perform(
            post("/web/update")
                .with(oauth2Login())
                .with(csrf())
        )
            .andExpect(status().isOk())
            .andExpect(content().string("updated"));
    }
}
```

**Giải thích:**

- `oauth2Login()` tạo principal OAuth2, nên endpoint phân loại là `oauth2`.
- `oidcLogin()` tạo principal kiểu `OidcUser`, và `idToken(token -> ...)` cho phép tùy biến một claim trong **ID token giả lập**. Endpoint đọc `sub` từ mock user; không có OIDC signature verification.
- `jwt()` và `opaqueToken()` cho phép gắn authorities rõ ràng, sau đó kiểm tra `hasAuthority(...)`. Hai test dương tính chứng minh policy chấp nhận authority được dựng sẵn; hai test âm tính chứng minh thiếu quyền bị từ chối.
- Request không có authentication bị trả 401 do cấu hình HTTP Basic entry point trong demo.
- `oauth2Login()` **không bypass CSRF** cho POST. `csrf()` là một test request post-processor riêng, mô phỏng token hợp lệ cho bài kiểm thử; nó không chứng minh trình duyệt production đã bootstrap CSRF token đúng cách.
- Không có bất kỳ test nào ở trên chứng minh endpoint xử lý bearer token thực sự: trong SecurityConfig ta **cố ý không bật `oauth2ResourceServer()`**. Điều này minh họa rõ ràng phạm vi mà test mock chấp nhận.

**Về imports:** các `static import` được tách dòng theo cú pháp Java hợp lệ (không đặt dấu chấm ở cuối dòng; tiếp tục trên dòng sau), nhưng nếu IDE dùng formatter khác, có thể viết trên một dòng như `import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;`. Nên giữ import đầy đủ theo công cụ build thực tế.

### 5.1 Test phân quyền có thể “xanh giả”

Một đoạn test chỉ dùng:

```java
mvc.perform(get("/api/report").with(jwt()
    .authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))))
   .andExpect(status().isOk());
```

chứng minh **controller/authorization xử lý một `JwtAuthenticationToken` giả lập** có authority ấy. Nó **không** chứng minh bearer token chứa scope `reports.read` sẽ được decode đúng, chuyển claim thành `SCOPE_reports.read` đúng hay bị từ chối nếu chữ ký sai.

Tương tự, một test `oidcLogin().idToken(...).andExpect(status().isOk())` không chứng minh provider phát ID token có issuer/audience/nonce hợp lệ, vì test đã cung cấp một `OidcUser` dựng sẵn.

## 6. Tùy biến principal, claims và authorities cho test đúng trọng tâm

### 6.1 oauth2Login(): test attributes và authorities của OAuth2 user

Có thể cấu hình mock attributes và authorities:

```java
mvc.perform(
    get("/web/identity").with(
        oauth2Login()
            .attributes(attrs -> attrs.put("department", "engineering"))
            .authorities(
                new SimpleGrantedAuthority("ROLE_EDITOR")
            )
    )
);
```

Đoạn trên là **request fragment** trong test có `mvc` và imports phù hợp, chưa phải class độc lập. Nó cho phép test controller hoặc method security xử lý OAuth2 user với thuộc tính/authority giả định.

**Không coi attribute do test đặt là claim đã được xác minh từ provider.** Trong ứng dụng thật, cần mapping profile/claims đáng tin cậy, kiểm tra account/tenant và chính sách gán quyền. `ROLE_EDITOR` do test gán là điều kiện đầu vào, không chứng minh ứng dụng có thể tự lấy role đó từ external provider.

### 6.2 oidcLogin(): test ID token/UserInfo, không kiểm tra chữ ký

Có thể dựng các OIDC claims cần cho controller:

```java
mvc.perform(
    get("/web/subject").with(
        oidcLogin()
            .idToken(token -> token
                .claim("sub", "employee-42")
                .claim("email", "employee@example.test")
            )
    )
);
```

Trong test, `OidcUser.getSubject()`, `getIdToken()` và claims tương ứng có thể được đọc. Tuy nhiên, **không chạy ID token decoder, issuer validation, audience validation, JWKS fetch hay nonce correlation** chỉ nhờ `oidcLogin()`. Việc thêm `email` cũng không bảo đảm provider production sẽ có `email_verified=true` hoặc cung cấp email theo đúng policy.

Khi cần test hành vi của controller dựa trên OIDC claims, dùng post-processor. Khi cần test **OIDC login security protocol**, phải dùng integration test cho OAuth2 Login/OIDC filters và provider phù hợp.

### 6.3 jwt(): tách JWT claims khỏi authorities

Ví dụ:

```java
mvc.perform(
    get("/api/report").with(
        jwt()
            .jwt(token -> token
                .claim("sub", "user-7")
                .claim("scope", "reports.read")
            )
            .authorities(
                new SimpleGrantedAuthority("SCOPE_other")
            )
    )
).andExpect(status().isForbidden());
```

**Dù mock JWT có claim `scope=reports.read`, test vẫn phải bị 403** vì ở đây authorities được **ghi đè cố ý** thành `SCOPE_other`. Đây là một cách chứng minh authorization dựa trên **`Authentication.getAuthorities()` sau khi xác thực**, không tự suy ra quyền từ một claim JSON trong controller.

Trong production, `JwtAuthenticationConverter` hoặc converter tùy chỉnh mới chịu trách nhiệm biến JWT claims thành authorities. `jwt().authorities(...)` **bỏ qua kiểm thử converter đó**. Nếu muốn kiểm thử converter, gọi converter trực tiếp trong unit test hoặc gửi bearer token qua configured resource server path để converter thực sự chạy.

Có thể truyền một `Converter<Jwt, Collection<GrantedAuthority>>` cho test post-processor nếu API phiên bản Spring Security hỗ trợ; nhưng đó vẫn là **unit-level converter behavior trên mock JWT**, không phải kiểm tra chữ ký/token decoder.

### 6.4 opaqueToken(): attributes và authorities từ introspection được dựng sẵn

`opaqueToken()` cho phép xác định attributes và authorities trên một principal giả:

```java
mvc.perform(
    get("/api/report").with(
        opaqueToken()
            .attributes(attrs -> {
                attrs.put("sub", "service-account-17");
                attrs.put("client_id", "reporting-app");
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")
            )
    )
).andExpect(status().isOk());
```

Nó hữu ích khi resource controller đọc `OAuth2AuthenticatedPrincipal`, `sub`, `client_id` hoặc authorities. Nhưng nó **không gọi `OpaqueTokenIntrospector.introspect(token)`**, nên không phát hiện trường hợp IdP trả `active:false`, introspection trả 401/500, thiếu scope hoặc token bị revoke.

Đối với resource server opaque token thật, auth server trả attributes và scopes qua introspection; Spring Security cần mapping chúng thành principal/authorities. Test post-processor đã cấp sẵn kết quả nên không có giao tiếp mạng.

### 6.5 Phân biệt role và scope trong test

- `hasRole("ADMIN")` thường yêu cầu authority `ROLE_ADMIN`.
- `hasAuthority("SCOPE_reports.read")` yêu cầu authority **chính xác** `SCOPE_reports.read`.
- `jwt().authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))` không tự suy ra `SCOPE_reports.read`.
- `jwt().jwt(token -> token.claim("scope", "reports.read"))` không thay thế test converter thật khi converter bị customize.
- Principal có `isAuthenticated()==true` không tự được phép mọi route; phải kiểm tra authorities, permission theo object và tenant ở backend.

Luôn ghi rõ **authority mong đợi** trong test, tránh test pass do mặc định không phù hợp nghiệp vụ.

## 7. Bốn post-processor KHÔNG bao phủ đường xác thực thật

### 7.1 OAuth2 Login và OIDC

Luồng login thật trong ứng dụng Servlet thường gồm:

```text
Browser
   └── GET /oauth2/authorization/{registrationId}
           └── OAuth2AuthorizationRequestRedirectFilter
                   └── redirect đến authorization endpoint
                           └── user login / consent
                                   └── callback /login/oauth2/code/{registrationId}
                                           └── kiểm tra state/authorization response
                                           └── exchange code tại token endpoint
                                           └── OIDC ID token validation nếu có
                                           └── OAuth2AuthenticationToken/SecurityContext
                                                   └── session browser
```

`oauth2Login()` và `oidcLogin()` **đi thẳng tới trạng thái cuối**. Chúng không kiểm tra:

- `ClientRegistration`, registration ID, callback URI có đúng provider allowlist không.
- `state` khớp authorization request hay bị replay/missing session.
- PKCE `code_challenge` / `code_verifier` theo chính sách client và provider.
- Authorization code có được đổi tại token endpoint với client authentication phù hợp không.
- UserInfo endpoint có lỗi hoặc trả attributes sai không.
- ID token có signature hợp lệ, issuer đúng, audience phù hợp, `exp` chưa hết, `nonce` khớp (theo luồng) không.
- Session cookie/SameSite/redirect/proxy có giữ login giữa nhiều HTTP requests thật không.

**Khi cần test những thứ này:** dùng test environment có OAuth2/OIDC provider phù hợp (ví dụ authorization server cho integration tests hoặc HTTP stub đúng giao thức), tích hợp `spring-boot-starter-oauth2-client`, kiểm tra redirect/callback và stubs token/JWKS/UserInfo như hệ thống production. MockMvc có thể bắt đầu bằng assert 302 và `Location`; để đi hết luồng có code exchange/JWKS cần provider giả lập hoặc test integration nhiều bước.

Đừng kết luận OAuth2 Login đã “an toàn trước login CSRF” chỉ vì `oauth2Login()` tạo được principal. State/nonce/PKCE và callback thực tế phải được kiểm tra đúng biên.

### 7.2 JWT Resource Server

Luồng bearer JWT thật:

```text
HTTP Authorization: Bearer <token>
      └── BearerTokenAuthenticationFilter
             └── JwtAuthenticationProvider
                    └── JwtDecoder
                          └── xác minh chữ ký/khóa
                          └── issuer, exp/nbf, audience theo policy
                    └── JwtAuthenticationConverter
                          └── authorities
             └── AuthorizationFilter
                    └── endpoint
```

`jwt()` **không gọi `JwtDecoder.decode(token)`**, vì vậy nó không thể chứng minh:

- JWT có chữ ký hợp lệ, algorithm và `kid` đúng chính sách.
- JWT chưa hết hạn (`exp`), chưa dùng trước `nbf`, issuer (`iss`) đúng.
- Audience (`aud`) dành cho chính API; audience validation có thể cần cấu hình thêm, không mặc định giả định đầy đủ.
- JWK rotation và lỗi JWKS endpoint được xử lý.
- Token thiếu/bị sửa bị từ chối như kỳ vọng.
- Mapping `scope`/`scp`/role claim thành authorities đúng với converter production.

**Bước tiếp theo:** viết test riêng cho `JwtDecoder`/`JwtAuthenticationConverter` và integration test gửi **bearer header thật** khi resource-server filter chain được bật. Unit test decoder có thể dùng signed JWT fixture với key test; integration test có thể dùng mock `JwtDecoder` để xác minh filter orchestration, nhưng **mock decoder không chứng minh chữ ký thật**.

### 7.3 Opaque Token Resource Server

Luồng opaque bearer token thật:

```text
HTTP Authorization: Bearer <opaque-token>
      └── BearerTokenAuthenticationFilter
             └── OpaqueTokenAuthenticationProvider
                    └── OpaqueTokenIntrospector
                         └── authorization server introspection endpoint
                              └── active, scope, sub, client_id, exp...
                    └── principal/authorities
             └── AuthorizationFilter
                    └── endpoint
```

`opaqueToken()` **không gọi introspection**. Một mock principal có authorities `SCOPE_admin` dù thật ra token đã bị revoke vẫn khiến test authorization “xanh” nếu test cấp đúng authority. Muốn biết revoked token bị từ chối, phải test `OpaqueTokenIntrospector` hoặc resource-server path thật với stub introspection endpoint.

**Chú ý:** JWT cũng có thể bị thu hồi theo chính sách hệ thống, nhưng JWT Resource Server mặc định xác minh token cục bộ theo trust/JWKS và không đồng nghĩa với per-request introspection. Không áp dụng giả định opaque-token revocation cho mọi JWT decoder.

## 8. Ví dụ thêm một test đi qua JwtDecoder thật trong filter chain

Phần này là một **cấu hình test riêng**, không chèn trực tiếp vào SecurityConfig tối giản ở mục 4 rồi giả định tất cả hoạt động cùng lúc. Trong một project Resource Server cần dependency `spring-boot-starter-oauth2-resource-server`, bật:

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/report")
            .hasAuthority("SCOPE_reports.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
```

Đây là **snippet DSL** bên trong `SecurityFilterChain`. Phải có `JwtDecoder` bean; production decoder thường lấy JWKs từ issuer/JWK Set URI theo cấu hình. Ví dụ integration test có thể **mock JwtDecoder** để kiểm tra filter gọi decoder và xử lý lỗi, dù test này vẫn **không xác thực chữ ký thật**.

Snippet của một test class Spring Boot 3.x có `@SpringBootTest`, `@AutoConfigureMockMvc` và resource-server config như trên:

```java
@Autowired
MockMvc mvc;

@MockBean
JwtDecoder jwtDecoder;

@Test
void badBearerTokenIsRejectedByResourceServerFilter() throws Exception {
    Mockito.when(jwtDecoder.decode("bad-token"))
        .thenThrow(new BadJwtException("invalid signature"));

    mvc.perform(
        get("/api/report")
            .header("Authorization", "Bearer bad-token")
    ).andExpect(status().isUnauthorized());

    Mockito.verify(jwtDecoder).decode("bad-token");
}
```

Đây là **test snippet không độc lập**: cần imports như `JwtDecoder`, `BadJwtException`, `Mockito`, `MockBean`, `MockMvc`, `@Test`, và cấu hình Resource Server + controller thực tế. `@MockBean` là API quen thuộc của Spring Boot 3.x (bị deprecate ở một số phiên bản mới hơn; có thể thay bằng `@MockitoBean` khi project hỗ trợ). Chọn đúng annotation mock bean của môi trường, không trộn cả hai.

Test có ích vì request chứa **header `Authorization: Bearer bad-token` thực** và filter/decoder interaction được quan sát. Tuy vậy `Mockito.when(...)` đã mô phỏng kết quả decode thất bại; test chỉ chứng minh error path/401 và filter wiring, **không chứng minh chữ ký RSA/ECDSA/JWK thực**. Để kiểm chứng crypto, cần thêm test decoder với token được ký bởi test key và các fixtures invalid signature, expired, wrong issuer/audience.

Một test happy path có thể stub decoder trả:

```java
Jwt jwt = Jwt.withTokenValue("good-token")
    .header("alg", "RS256")
    .claim("sub", "user-17")
    .claim("scope", "reports.read")
    .build();

Mockito.when(jwtDecoder.decode("good-token")).thenReturn(jwt);
```

Khi gửi header `Bearer good-token` qua resource server thật, converter mặc định có thể map `scope` thành `SCOPE_reports.read`, cho phép kiểm tra đường filter + converter. Nhưng **chữ ký vẫn là mock** vì decoder đã bị stub. Tách mức đảm bảo này rõ trong tên testcase và tài liệu.

## 9. Ví dụ test đường opaque-token introspection

Trong **cấu hình resource server opaque token riêng**, bật:

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/report")
            .hasAuthority("SCOPE_reports.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .opaqueToken(Customizer.withDefaults())
    );
```

Cấu hình cần `OpaqueTokenIntrospector` bean hoặc `spring.security.oauth2.resourceserver.opaquetoken` properties thích hợp. Để kiểm tra error path khi token inactive, một test riêng có thể mock introspector:

```java
@MockBean
OpaqueTokenIntrospector introspector;

@Test
void inactiveOpaqueBearerTokenIsRejected() throws Exception {
    Mockito.when(introspector.introspect("revoked-token"))
        .thenThrow(new OAuth2IntrospectionException("inactive"));

    mvc.perform(
        get("/api/report")
            .header("Authorization", "Bearer revoked-token")
    ).andExpect(status().isUnauthorized());

    Mockito.verify(introspector).introspect("revoked-token");
}
```

Đây cũng là **test snippet không độc lập**, dùng resource-server filter path và cần imports/fixture như mục trước; **không cùng cấu hình JWT-only trong một filter chain mặc định**, trừ khi kiến trúc application thực sự thiết kế lựa chọn. Mock introspector cho phép test cách ứng dụng xử lý kết quả giả lập `inactive` nhưng **không tạo HTTP request thật** đến authorization server.

Khi muốn kiểm tra introspection integration thực tế, dùng một **HTTP stub server** có kiểm soát trả các trường hợp: `active=true` với scopes, `active=false`, 401 do client credentials sai, 500/service unavailable, timeout và dữ liệu thiếu/malformed. Đồng thời kiểm tra secrets của introspection client không bị ghi log.

### 9.1 Phân tầng mức bảo đảm

| Test | Điều kiểm tra chắc hơn | Điều vẫn chưa được chứng minh |
| --- | --- | --- |
| `opaqueToken()` | Controller/authorization với mock Bearer principal. | Introspection được gọi hay không. |
| Bearer header + **mock** `OpaqueTokenIntrospector` | Filter wiring, 401/403, mapping theo stub. | HTTP request/credentials/introspection response thật. |
| Bearer header + introspector gọi **stub HTTP server** | HTTP request, parse response, network/error behavior. | Authorization server production thực sự chính xác/không bị compromise. |
| Staging/contract test với IdP được kiểm soát | Tương thích giao thức/scope/metadata thực tế hơn. | Không thay thế mọi production threat/operational monitoring. |

## 10. Kiểm thử authority và claim không bị nhầm lẫn

Một lỗi phổ biến là viết:

```java
mvc.perform(
    get("/api/admin").with(jwt())
).andExpect(status().isOk());
```

rồi kết luận “JWT token của admin sẽ vào được endpoint”. Thực tế `jwt()` dựng một principal mặc định **không phải admin token**; nếu endpoint được cấu hình cho phép mọi authenticated user thì test có thể pass do policy quá rộng, không chứng minh mapping quyền.

Nên viết **case đối nghịch** với authorities cụ thể:

```java
mvc.perform(
    get("/api/admin").with(jwt()
        .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
).andExpect(status().isForbidden());

mvc.perform(
    get("/api/admin").with(jwt()
        .authorities(new SimpleGrantedAuthority("SCOPE_admin")))
).andExpect(status().isOk());
```

Test trên bảo đảm request chính sách phân quyền theo authority mong muốn. Nếu service còn kiểm soát tài nguyên theo owner/tenant, cần test identity/tenant-specific authorization ở service hoặc integration: `ROLE_ADMIN` không tự chứng minh quyền xem mọi đối tượng.

**Tránh bẫy claim ≠ authority:** JWT claim `scope`/`scp` và OAuth2 attributes có thể trải qua converter/mapping riêng. Nếu dùng `.authorities(...)` trong post-processor, bạn đang **chỉ định kết quả cuối**, chưa kiểm tra converter. Để bảo vệ converter, thêm test trực tiếp:

```java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

// Unit test converter với một Jwt fixture phù hợp,
// rồi assert authorities, principal name và policy của project.
```

Đây là đoạn minh họa, không phải testcase đầy đủ; nếu project tùy biến converter (chẳng hạn roles trong `realm_access.roles`), phải test **đúng converter đang dùng** thay vì mặc định.

## 11. CSRF, session, headers và @WithMockUser: các biên khác nhau

### 11.1 OAuth2 login giả không vượt CSRF

Trong Spring Security Servlet, request thay đổi trạng thái theo session cookie thường cần CSRF token. `oauth2Login()` và `oidcLogin()` dựng identity **nhưng không tự làm một POST hợp lệ về CSRF**. Trong test:

```java
mvc.perform(
    post("/web/update").with(oidcLogin())
).andExpect(status().isForbidden());

mvc.perform(
    post("/web/update").with(oidcLogin()).with(csrf())
).andExpect(status().isOk());
```

Lệnh `with(csrf())` cũng là mock token hợp lệ theo Spring Security Test. Nó hữu ích để tập trung vào business behavior của POST, **không chứng minh** browser production đã lấy/lưu/gửi token đúng (CookieCsrfTokenRepository, deferred token, BREACH masking, header, SPA bootstrapping).

### 11.2 Session của MockMvc không chứng minh OIDC cookie lifecycle

`oidcLogin()` không thử đăng nhập nhiều request qua redirect/session fixation protection thật. Một test một-request với post-processor sẽ cung cấp mock identity mỗi lần gọi `perform`. Nó không bảo đảm session cookie của browser có `Secure`/`HttpOnly`/`SameSite` phù hợp hay login persistence sau callback; cần thêm end-to-end/integration test tương ứng.

### 11.3 @WithMockUser không tương đương OAuth2/OIDC

`@WithMockUser(username="alice", roles="USER")` tạo một mock security context với principal kiểu Spring Security user, hữu ích cho rule `hasRole("USER")` và controller chỉ cần `Authentication.getName()`. Nhưng controller cần `OidcUser.getSubject()` hoặc `Jwt.getClaim(...)` có thể không chạy đúng vì **kiểu principal khác**.

Chọn helper sát nghiệp vụ:

- `@WithMockUser` cho phương thức/controller không phụ thuộc OAuth2 principal type.
- `oauth2Login()` khi controller nhận `OAuth2User`.
- `oidcLogin()` khi controller nhận `OidcUser`.
- `jwt()` khi API/controller dùng `Jwt`/`JwtAuthenticationToken`.
- `opaqueToken()` khi API dùng `OAuth2AuthenticatedPrincipal` từ opaque-token auth.

Đừng sử dụng helper phức tạp hơn nếu chỉ cần quyền ROLE_USER; nhưng cũng đừng dùng `@WithMockUser` để vô tình che lỗi ép kiểu trong OIDC controller.

## 12. Test slice so với integration test

### 12.1 @WebMvcTest

`@WebMvcTest(MyController.class)` load **một lát cắt Spring MVC**: controller, MVC infrastructure và một phần filter/test support. Nó nhanh, nhưng nhiều service/security bean bị thiếu hoặc được mock. Khi dùng spring-security-test, cần bảo đảm `MockMvc` đã tích hợp Spring Security; có thể `@Import` security config phù hợp và `@MockBean` các dependency của controller.

Nên dùng để kiểm tra: serialization, route mapping, controller đọc principal, response status, `hasAuthority` trên filter chain slice đã cấu hình. Không dùng để kết luận IdP/JwtDecoder/introspection production hoạt động.

### 12.2 @SpringBootTest + @AutoConfigureMockMvc

Load application context rộng hơn, có filter chains thật, nhưng **request post-processor vẫn đang giả lập Authentication**. Vì vậy “integration test” không đồng nghĩa “cryptographic authentication integration test”.

Ví dụ:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationTest {
    @Autowired MockMvc mvc;

    @Test
    void allowsMockJwtWithReportScope() throws Exception {
        mvc.perform(get("/api/report")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
            .andExpect(status().isOk());
    }
}
```

Dù `@SpringBootTest` có thể load một `JwtDecoder` bean và resource server config thật, request trên **không cần gọi decoder**. Muốn test decoder/filter, gửi header bearer vào MockMvc và kiểm tra những tương tác/validation phù hợp.

### 12.3 Khi cần HTTP test ở container thật

MockMvc không tạo một trình duyệt hoặc HTTPS/TLS socket thực. Nếu bảo mật phụ thuộc reverse proxy, cookie SameSite/Secure, TLS client certificate, browser redirect/SSO hoặc CORS/CSRF ở web frontend, bổ sung integration/E2E test trên test server và browser phù hợp. Giữ phân tách rõ giữa **unit MockMvc** và **giao thức HTTP/browser/TLS**.

## 13. Ma trận kiểm thử nên có cho dự án thực tế

| Ranh giới | Positive test | Negative test | Công cụ/thành phần |
| --- | --- | --- | --- |
| OAuth2 controller | `oauth2Login()` thấy user attrs đúng | Thiếu authority → 403 | MockMvc post-processor. |
| OIDC controller | `oidcLogin()` có `OidcUser` và subject | Thiếu role/account mapping → 403 | MockMvc post-processor. |
| OAuth2 redirect/callback | Valid state/code exchange thành công | Wrong state/redirect/session/code → thất bại | OIDC provider fixture/stub + login filters. |
| ID token validation | Signed token đúng issuer/aud/expiry | Bad signature, expired, wrong issuer/aud/nonce | OIDC decoder/verification flow integration. |
| JWT authorization | `jwt().authorities(SCOPE_x)` → 200 | Wrong authority → 403 | MockMvc post-processor. |
| JWT decoder/filter | Bearer token hợp lệ được decode | Bad signature/exp/iss/aud/token missing → 401 | JWT Resource Server + decoder/test keys. |
| JWT converter | Claims tạo đúng authorities | Claim role/scope không được công nhận → deny | Converter unit/integration test. |
| Opaque authorization | `opaqueToken().authorities(SCOPE_x)` → 200 | Missing scope → 403 | MockMvc post-processor. |
| Opaque introspection | `active=true` → principal/scopes | `active=false`/revoked/timeout/401/500 | Introspector + stub HTTP IdP. |
| CSRF cho POST cookie session | Identity + đúng CSRF → được xử lý | Identity nhưng thiếu CSRF → 403 | MockMvc `csrf()` + browser contract test. |
| Authorization ở service | User có quyền đọc resource của mình | User A đọc resource của B → 403 | Service security/integration test. |
| Session/OIDC persistence | Login xong request tiếp có session | Logout/session expired → không còn quyền | Real multi-request/session/browser test. |

**Hai status khác ý nghĩa:**

- **401 Unauthorized:** thường do chưa xác thực hoặc credential không hợp lệ. Trên API bearer JWT/opaque token, 401 có thể xuất hiện khi signature/introspection thất bại. Với web login, unauthenticated request có thể được **302 redirect** sang login page thay vì 401.
- **403 Forbidden:** request đã được xác thực nhưng thiếu quyền, **hoặc** một filter như CSRF chặn request. Vì vậy một 403 không tự chứng minh thiếu scope; kiểm tra filter log, response và flow cụ thể.

## 14. Những lỗi thường gặp khi viết test

| Biểu hiện | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Test `jwt()` xanh nhưng API thật trả 401 | JWT mock không chạy decoder; token thật sai issuer/signature/audience hoặc filter không được bật. | Viết bearer-header integration test cho JWT Resource Server. |
| Test `opaqueToken()` xanh dù token đã revoke | Mock không gọi introspection, vẫn cấp authorities. | Test introspector active=false/revoke và lỗi mạng. |
| Test `oidcLogin()` xanh dù callback lỗi state | Mock bypass toàn bộ redirect/callback. | Test OAuth2 Login filter/provider flow; kiểm tra state/nonce. |
| `@WithMockUser` khiến `@AuthenticationPrincipal OidcUser` null | Principal kiểu User, không phải OidcUser. | Dùng `oidcLogin()`. |
| Test có `jwt().authorities(...)` nhưng converter production sai | Test đã override authorities cuối. | Unit/integration test converter và claims thực. |
| Test status 200 khi không cấu hình Resource Server | Mock đã tạo Authentication, authorization vẫn cho phép. | Bật Resource Server thật và test bearer header riêng. |
| MockMvc trả 403 thay vì 401 | Không có HTTP Basic/Bearer entry point hoặc bị CSRF chặn. | Hiểu SecurityFilterChain, entry point, request method và CSRF policy. |
| Test chạy không qua SecurityFilterChain | `standaloneSetup` không tích hợp springSecurity hoặc tắt filters. | Dùng `@AutoConfigureMockMvc`/`springSecurity()` và xác minh filters. |
| Test giả role admin nhưng thật không có quyền | Gán `ROLE_ADMIN` trực tiếp trong test, thiếu mapping từ IdP. | Test authority mapper từ provider claims/group. |
| Login mock pass cho một request, request sau anonymous | Post-processor chỉ đặt identity cho request test cụ thể. | Test HTTP session/login persistence thực tế. |
| Test POST oauth2Login bị 403 | Thiếu CSRF token hoặc rule khác chặn. | Thêm `with(csrf())` nếu testcase không nhằm kiểm tra CSRF; test thiếu CSRF riêng. |
| Mock JWT có claim nhưng authorities không như mong đợi | Claims và authorities đi qua converter; mock có thể override. | Assert authorities cuối và test converter tách biệt. |

## 15. Checklist khi chọn phạm vi giả lập

1. Đọc **SecurityFilterChain** production: ứng dụng web login hay API bearer? Token kiểu JWT hay opaque? Có nhiều filter chains theo route không?
2. Chọn post-processor theo principal thực tế controller cần, không chọn theo tên nhà cung cấp đăng nhập.
3. Kiểm tra **positive và negative authority cases**; không chỉ test request có Authentication trả 200.
4. Ghi rõ trong tên test “mock principal authorization” hay “real bearer decoder/introspector”; tránh các tên gây hiểu nhầm như `validJwtSignatureIsAccepted` khi chỉ dùng `jwt()`.
5. Không coi `oidcLogin().idToken(...)` là test chữ ký/nonce, không coi `opaqueToken().attributes(...)` là test revoked token.
6. Khi muốn test converter, **không ghi đè authorities** rồi kết luận converter hoạt động.
7. Khi muốn test HTTP authentication thật, gửi bearer header qua filter chain có Resource Server, hoặc thực hiện redirect/callback qua OIDC provider fixture.
8. Đảm bảo MockMvc tích hợp Spring Security, các filter không bị tắt và test dùng đúng SecurityFilterChain.
9. Tách **401 do authentication**, **403 do authorization** và **403 do CSRF**; test cả các nhánh xấu.
10. Thêm kiểm thử session persistence, CSRF, claim mapping, tenant/resource ownership và lỗi mạng theo kiến trúc.

**Ghi nhớ:** `oauth2Login()`, `oidcLogin()`, `jwt()` và `opaqueToken()` là công cụ **dựng danh tính đã xác thực** để kiểm thử **HTTP request behavior và phân quyền** trong Spring Security Servlet. Chúng không tự chạy giao thức OAuth2/OIDC, không kiểm tra chữ ký JWT, và không gọi opaque-token introspection. Một bộ test bảo mật đáng tin cần **tầng mock cho business authorization** kết hợp **tầng integration cho authentication boundary** mà ứng dụng thật phụ thuộc.
