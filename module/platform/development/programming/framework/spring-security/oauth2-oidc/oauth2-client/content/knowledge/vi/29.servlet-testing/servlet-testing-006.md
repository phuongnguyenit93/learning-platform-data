# 29.6. Kiểm thử controller sử dụng @AuthenticationPrincipal

## 1. Vì sao kiểm thử `@AuthenticationPrincipal` dễ tạo kết quả sai?

Trong ứng dụng **Spring Security OAuth 2.0/OIDC Client (Servlet)**, controller thường cần biết người dùng hiện tại là ai. Một cách phổ biến là dùng annotation `@AuthenticationPrincipal`:

```java
@GetMapping("/api/me")
public UserProfile me(@AuthenticationPrincipal OidcUser user) {
    return new UserProfile(
        user.getSubject(),
        user.getClaimAsString("email")
    );
}
```

Nhìn qua, đây là một controller đơn giản. Nhưng một test sử dụng:

```java
@WithMockUser(username = "alice")
```

**không nhất thiết tạo ra `OidcUser`**. `@WithMockUser` chủ yếu thiết lập một `UsernamePasswordAuthenticationToken` với principal dạng Spring Security `UserDetails`. Trong khi đó, controller lại yêu cầu principal có kiểu `OidcUser`, chứa ID Token và OIDC claims.

Hệ quả thường gặp:

- Controller nhận `null` ở tham số `@AuthenticationPrincipal OidcUser`.
- Controller phát sinh `NullPointerException` khi gọi `user.getSubject()`.
- Test báo lỗi nhưng nguyên nhân là **fixture sai loại principal**, không phải code controller.
- Một test dùng `@WithMockUser` pass khi controller chỉ cần username nhưng không kiểm tra đúng **OIDC Login**.
- Test mock trực tiếp service/controller bỏ qua argument resolver, khiến lỗi wiring `@AuthenticationPrincipal` không bị phát hiện.

Vì vậy, cần phân biệt hai mục tiêu:

1. **Kiểm thử Spring MVC controller nhận đúng principal** từ `SecurityContext` qua `@AuthenticationPrincipal`.
2. **Kiểm thử OAuth2/OIDC protocol thật** như authorization redirect, token exchange, chữ ký, issuer, audience, state, nonce và PKCE.

Mục tiêu thứ nhất có thể kiểm thử nhanh bằng **`MockMvc` + `spring-security-test`**, đặc biệt các request postprocessors **`oidcLogin()`** và **`oauth2Login()`**. Mục tiêu thứ hai cần các integration tests ở phạm vi khác, không được tuyên bố đã kiểm thử đầy đủ chỉ bằng cách dựng mock principal.

> **Nguyên tắc:** Hãy dựng **đúng loại `Authentication`/principal mà production sử dụng**. Với OIDC Login, thông thường dùng `oidcLogin()` hoặc custom `OidcUser`; với OAuth2 Login không OIDC, dùng `oauth2Login()`. `@WithMockUser` phù hợp cho kiểm thử generic username/password authentication, nhưng không phải lựa chọn mặc định để kiểm thử controller phụ thuộc `OidcUser`.

### 1.1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích `@AuthenticationPrincipal` thực sự lấy dữ liệu từ đâu.
2. Phân biệt `Principal`, `Authentication`, `SecurityContext`, `UserDetails`, `OAuth2User`, `OidcUser` và `Jwt`.
3. Cấu hình `MockMvc` với Spring Security filters để annotation được resolve đúng.
4. Dùng `oidcLogin()` để kiểm thử controller cần OIDC subject/claims.
5. Dùng `oauth2Login()` để kiểm thử controller cần `OAuth2User`.
6. Biết khi nào `@WithMockUser` sẽ tạo sai kiểu principal.
7. Kiểm thử `@AuthenticationPrincipal(expression = "...")`, `errorOnInvalidType` và meta-annotation tùy chỉnh.
8. Kiểm thử endpoint public, request chưa đăng nhập và principal không đúng loại.
9. Kiểm thử role/authority/tenant isolation mà không tự tin vào raw request headers.
10. Dùng `@WebMvcTest`, `@SpringBootTest`/`@AutoConfigureMockMvc` và `@WithSecurityContext` đúng phạm vi.
11. Tránh trộn `@AuthenticationPrincipal` với `@RegisteredOAuth2AuthorizedClient`.
12. Phân biệt controller slice tests với OIDC Login/Resource Server integration tests.
13. Thiết kế test dữ liệu tổng hợp, bảo vệ claims và tránh logs chứa token/PII.

## 2. `@AuthenticationPrincipal` hoạt động như thế nào?

Spring Security Servlet cho phép lấy principal trong `SecurityContextHolder`. Annotation được xử lý bởi:

```java
org.springframework.security.web.method.annotation
    .AuthenticationPrincipalArgumentResolver
```

Về mặt khái niệm:

```text
HTTP request
    ↓
Spring Security Filter Chain
    ↓
SecurityContextHolder.getContext().getAuthentication()
    ↓
Authentication.getPrincipal()
    ↓
AuthenticationPrincipalArgumentResolver
    ↓
Controller parameter @AuthenticationPrincipal
```

### 2.1. Các loại dữ liệu cần phân biệt

| Kiểu | Mô tả | Cách sử dụng |
| --- | --- | --- |
| `SecurityContext` | Chứa `Authentication` của request/thread theo SecurityContext strategy | Spring Security filters/test helpers |
| `Authentication` | Toàn bộ thông tin principal, authorities và trạng thái authenticated | Injection trực tiếp hoặc `@CurrentSecurityContext` |
| `Authentication.getPrincipal()` | Đối tượng đại diện danh tính chính | `@AuthenticationPrincipal` |
| `UserDetails` | Principal thường gặp của username/password login | `@WithMockUser`, `user(...)` |
| `OAuth2User` | Principal sau OAuth2 Login | `oauth2Login()` |
| `OidcUser` | Principal sau OpenID Connect Login, có ID Token | `oidcLogin()` |
| `Jwt` | Principal phổ biến của `JwtAuthenticationToken` tại Resource Server | `jwt()` khi test bearer JWT |
| `OAuth2AuthorizedClient` | `ClientRegistration` kết hợp access/refresh tokens | `@RegisteredOAuth2AuthorizedClient` hoặc manager/service |

Controller:

```java
@GetMapping("/api/whoami")
String whoAmI(@AuthenticationPrincipal OidcUser user) {
    return user.getSubject();
}
```

Annotation sẽ lấy **principal**, không lấy nguyên `Authentication`, không đọc `Authorization: Bearer` trực tiếp và không tự truy vấn OIDC UserInfo Endpoint.

### 2.2. Đường truyền thực tế của OIDC Login

Ở một OIDC Login thường gặp:

```text
Authentication:
    OAuth2AuthenticationToken
        |
        +-- principal: DefaultOidcUser implements OidcUser
        |     |
        |     +-- OidcIdToken
        |     +-- OidcUserInfo (có thể có)
        |     +-- authorities
        |
        +-- authorities
        +-- authorizedClientRegistrationId = corporate
```

`OidcUser` chứa OIDC identity; `OAuth2AuthenticationToken` còn có **registration ID** dùng để phân biệt provider/tenant.

Vì vậy:

```java
@AuthenticationPrincipal OidcUser oidcUser
```

lấy principal chứ **không trực tiếp** lấy registration ID. Nếu controller cần cả registration ID hoặc authorities, có thể inject `Authentication`:

```java
@GetMapping("/api/context")
Map<String, String> context(
        Authentication authentication,
        @AuthenticationPrincipal OidcUser user) {

    if (!(authentication instanceof OAuth2AuthenticationToken token)) {
        throw new IllegalStateException(
            "Expected OAuth2AuthenticationToken");
    }

    return Map.of(
        "subject", user.getSubject(),
        "registrationId",
        token.getAuthorizedClientRegistrationId());
}
```

**Lưu ý:** `registrationId` xác định client registration đã dùng để đăng nhập, nhưng **không thay thế** kiểm tra user có quyền truy cập tenant hay không.

### 2.3. `getName()` và `sub` không hoàn toàn đồng nghĩa

Với `OidcUser`, thuộc tính cốt lõi của danh tính là OIDC `sub`, gắn với `iss` của OP. `DefaultOidcUser` thường dùng `sub` làm name attribute mặc định, nhưng ứng dụng có thể cấu hình principal name attribute khác.

Vì vậy:

```java
oidcUser.getSubject()
```

là cách diễn đạt rõ rằng ứng dụng cần **OIDC subject**.

Nếu dùng:

```java
oidcUser.getName()
```

phải hiểu `getName()` phụ thuộc cách xây `OidcUser` và name attribute. Nó không nhất thiết là email hoặc username.

Không dùng `email` làm khóa định danh người dùng một cách vô điều kiện; email có thể đổi hoặc thiếu, có thể chưa được xác minh tùy claims/provider. Trong multi-issuer model, identity thường cần **cặp `(issuer, subject)`**.

## 3. Chọn đúng loại test cho đúng câu hỏi

| Loại test | Có Spring MVC argument resolution? | Có Security filter chain? | Có OAuth2/OIDC network flow thật? |
| --- | --- | --- | --- |
| Gọi trực tiếp method controller | Không | Không | Không |
| `MockMvcBuilders.standaloneSetup(controller)` đơn giản | Có MVC resolver cơ bản, nhưng security integration cần cấu hình | Không tự động | Không |
| `@WebMvcTest` + MockMvc + Spring Security test | Có | Có nếu security filters được áp dụng | Không |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Có | Thường có, tùy test config | Không nếu chỉ dùng `oidcLogin()` |
| Integration test với fake/test OP | Có | Có | Có thể kiểm thử authorize/token/JWT validation |
| Browser E2E với OP sandbox | Có | Có | Có, gồm redirect/cookie/proxy theo phạm vi |

**Trọng tâm bài:** kiểm thử controller Servlet bằng Spring MVC Test và `spring-security-test`, không chạy Authorization Code flow thật cho mỗi test method.

### 3.1. Khi nào gọi trực tiếp controller là đủ?

Một unit test:

```java
OidcUser user = ...;
UserProfile result = controller.me(user);
```

có thể kiểm tra logic mapping từ `OidcUser` sang DTO.

Nhưng nó **không chứng minh**:

- `@AuthenticationPrincipal` được resolve đúng.
- `SecurityContext` thực sự có OIDC principal.
- Request chưa đăng nhập bị chặn.
- URL authorization rules/CSRF hoạt động.
- Exception handling và JSON serialization đúng.

Nếu đề bài là **kiểm thử controller sử dụng `@AuthenticationPrincipal`**, nên có ít nhất một test qua **MockMvc**.

## 4. Dependencies cho Servlet tests

Ví dụ Gradle của ứng dụng Spring Boot Servlet:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-security-test` cung cấp các công cụ như:

- `SecurityMockMvcRequestPostProcessors.oidcLogin()`.
- `SecurityMockMvcRequestPostProcessors.oauth2Login()`.
- `SecurityMockMvcRequestPostProcessors.user(...)`.
- `SecurityMockMvcRequestPostProcessors.authentication(...)`.
- `SecurityMockMvcRequestPostProcessors.securityContext(...)`.
- `SecurityMockMvcRequestPostProcessors.csrf()`.
- `@WithMockUser`.
- `@WithAnonymousUser`.
- `@WithSecurityContext`.

Phần lớn ví dụ dùng **JUnit Jupiter/JUnit 5**, Java 17+ và các API Spring Security hiện đại. Tên packages, các builder methods và annotation mocking có thể khác giữa Spring Boot/Spring Security versions. Khi áp dụng thật, dùng BOM/dependency management đồng bộ.

### 4.1. Static imports thường dùng

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;

import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
```

Những imports được xuống dòng để dễ đọc. Trong file Java thực, hãy viết mỗi `import` thành **một statement hợp lệ trên cùng dòng hoặc nhiều dòng Java cho phép**; ví dụ minh họa không nhằm trình bày toàn bộ source file.

## 5. Một controller mẫu sử dụng `@AuthenticationPrincipal OidcUser`

Giả sử API trả về danh tính tối thiểu của người dùng đã OIDC Login:

```java
package example.portal.web;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public ResponseEntity<MeResponse> me(
            @AuthenticationPrincipal OidcUser user) {

        if (user == null) {
            return ResponseEntity.status(401).build();
        }

        String subject = user.getSubject();

        String email = user.getClaimAsString("email");

        String issuer =
            user.getIdToken().getClaimAsString("iss");

        return ResponseEntity.ok(
            new MeResponse(subject, email, issuer));
    }

    public record MeResponse(
        String subject,
        String email,
        String issuer
    ) {}
}
```

**Vì sao có nhánh `user == null`?** Ví dụ muốn controller có hành vi dễ hiểu ngay cả khi endpoint được đặt `permitAll`, gọi trực tiếp trong unit test hoặc authentication principal không đúng loại. Trong API production được bảo vệ bằng `.authenticated()`, request chưa đăng nhập thường bị Spring Security chặn **trước khi controller chạy**.

**Lưu ý:** Nếu `@AuthenticationPrincipal` được cấu hình `errorOnInvalidType = true`, principal sai loại có thể gây exception trước khi method được gọi, thay vì trả `null`.

### 5.1. Không nên trả toàn bộ claims ra client

Controller ví dụ chỉ trả ba trường để minh họa test. Trong production:

- Không trả raw `id_token`, `access_token` hoặc `refresh_token`.
- Không mặc nhiên trả toàn bộ `OidcUser.getClaims()` vì có thể chứa PII.
- `sub` + `iss` nên được dùng làm định danh nội bộ tùy trust/tenant policy.
- Nếu không cần `email`, không đưa email vào response.
- Không dùng `email` như một permission/tenant membership proof.
- Cần kiểm soát `Cache-Control` nếu endpoint trả dữ liệu danh tính nhạy cảm.

## 6. `@WebMvcTest` kiểm thử controller bằng `oidcLogin()`

Để kiểm thử **MVC argument resolution** mà không khởi tạo toàn bộ application/database/IdP, có thể dùng `@WebMvcTest`.

### 6.1. Test security configuration

Với mục tiêu test injection, có thể cung cấp một security chain tối giản:

```java
@WebMvcTest(MeController.class)
@Import(MeControllerTest.TestSecurity.class)
class MeControllerTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class TestSecurity {

        @Bean
        SecurityFilterChain securityFilterChain(
                HttpSecurity http) throws Exception {

            return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/me").authenticated()
                    .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        }
    }

    // Test methods ở phần tiếp theo.
}
```

**Tại sao dùng `httpBasic` thay vì `oauth2Login` trong slice test này?**

Vì test **không kiểm tra quá trình login với OP**, chỉ muốn xác minh:

- Security filter chain nhận một `Authentication` mock từ test.
- `@AuthenticationPrincipal` resolve đúng `OidcUser`.
- `@GetMapping` trả JSON đúng.
- Request chưa xác thực bị chặn.

Dùng `httpBasic()` trong **test-only chain** cũng giúp trạng thái unauthenticated thường trả `401`, không bị redirect tới một login page. Nếu bạn muốn kiểm tra **production security config**, dùng một context/integration test khác, không thay chain bằng test config.

Đoạn code trên cần các imports JUnit 5, Spring Boot Test, Spring Test, Spring Security, Spring MVC Test. `@WebMvcTest` chỉ load MVC slice; các dependencies của controller (services, repositories) cần mock nếu có.

### 6.2. Test `oidcLogin()` với claims tùy chỉnh

```java
@Test
void meReturnsSubjectEmailAndIssuerFromOidcPrincipal()
        throws Exception {

    mvc.perform(get("/api/me")
            .with(oidcLogin()
                .idToken(idToken -> idToken
                    .claim("sub", "user-acme-42")
                    .claim("email", "alice@example.test")
                    .claim("iss",
                        "https://idp.example.test/realms/acme")
                    .claim("aud", List.of("portal-web")))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject")
            .value("user-acme-42"))
        .andExpect(jsonPath("$.email")
            .value("alice@example.test"))
        .andExpect(jsonPath("$.issuer")
            .value("https://idp.example.test/realms/acme"));
}
```

`oidcLogin()` tạo một authentication/principal phục vụ test và cấu hình `SecurityContext` request. Consumer truyền vào `.idToken(...)` giúp sửa claims của **ID Token giả** dùng để dựng `OidcUser`.

Điểm được kiểm tra:

1. MockMvc đi qua Spring MVC endpoint.
2. Spring Security test postprocessor đặt OIDC authentication trong request.
3. `@AuthenticationPrincipal` nhận được `OidcUser`.
4. Method đọc claims và tạo DTO đúng.
5. Jackson serialize response thành JSON.

**Điểm chưa được kiểm tra:** test không chứng minh OP thật đã ký ID Token hợp lệ, issuer/audience thực tế đúng, authorization code/state/nonce/PKCE được validate hoặc token exchange thành công.

### 6.3. Test thiếu claim tùy chọn

OIDC `email` không phải lúc nào cũng có, dù client xin scope `email`. Controller cần quyết định hợp đồng:

- Cho trả `null` nếu email không có.
- Trả một giá trị fallback **không gây nhầm identity**.
- Yêu cầu email theo business rules và trả lỗi nghiệp vụ có kiểm soát.
- Không suy ra email từ `sub`.

Một test:

```java
@Test
void meAllowsMissingOptionalEmailClaim()
        throws Exception {

    mvc.perform(get("/api/me")
            .with(oidcLogin()
                .idToken(idToken -> idToken
                    .claim("sub", "user-without-email")
                    .claim("iss", "https://idp.example.test")
                    .claims(claims -> claims.remove("email")))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject")
            .value("user-without-email"))
        .andExpect(jsonPath("$.email").doesNotExist());
}
```

**Lưu ý về JSON serialization:** Jackson thường serialize field `null` thành JSON `null` nếu không cấu hình exclude-null. Assertion `.doesNotExist()` có thể phù hợp cho missing hoặc null theo JsonPath matcher tùy cấu hình; nếu API contract phân biệt **field bị bỏ** với **field có giá trị null**, hãy dùng JSON assertion cụ thể cho serializer của dự án.

Nếu `claims(...)`/consumer API không có trong Spring Security version đang dùng, có thể tạo `OidcIdToken`/`OidcUser` fake rồi truyền qua `.oidcUser(...)`. Cần test theo phiên bản cụ thể.

## 7. `@WithMockUser` không thay thế `oidcLogin()`

Một test có vẻ hợp lý:

```java
@Test
@WithMockUser(username = "alice")
void meWithMockUser() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk());
}
```

Nhưng với controller:

```java
@GetMapping("/api/me")
MeResponse me(@AuthenticationPrincipal OidcUser user) {
    return new MeResponse(
        user.getSubject(), null, null);
}
```

`@WithMockUser` tạo principal là `UserDetails` thông thường. Nó **không phải** `OidcUser`.

### 7.1. Kết quả phụ thuộc vào parameter và resolver

Khi loại principal thực tế không gán được cho parameter:

```java
@AuthenticationPrincipal OidcUser user
```

resolver mặc định có thể trả `null` nếu `errorOnInvalidType` để mặc định `false`. Nếu controller dereference `user`, có thể gặp NPE.

Nếu cấu hình:

```java
@AuthenticationPrincipal(errorOnInvalidType = true)
OidcUser user
```

Spring Security resolver sẽ ném lỗi ép kiểu khi gặp principal không đúng loại.

Đừng mặc định sai loại principal sẽ trở thành `401`. **Request đã được xác thực** bằng `@WithMockUser`; HTTP filter `.authenticated()` có thể cho request đi vào controller. Lỗi khi resolve/bắt đầu xử lý principal là lỗi **kiểu dữ liệu/test fixture**, không phải unauthenticated request.

### 7.2. Khi nào `@WithMockUser` là đúng?

Nó phù hợp khi controller chỉ cần:

```java
@GetMapping("/api/name")
String name(Authentication authentication) {
    return authentication.getName();
}
```

hoặc:

```java
@GetMapping("/api/user")
String user(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
```

hoặc khi test URL/method authorization theo roles mà **không phụ thuộc** OIDC claims.

Một quy tắc thực hành:

| Controller parameter | Test helper nên cân nhắc |
| --- | --- |
| `@AuthenticationPrincipal UserDetails` | `@WithMockUser` hoặc `.with(user(...))` |
| `@AuthenticationPrincipal OAuth2User` | `.with(oauth2Login())` |
| `@AuthenticationPrincipal OidcUser` | `.with(oidcLogin())` |
| `@AuthenticationPrincipal Jwt` | `.with(jwt())` khi Resource Server dùng JWT |
| `Authentication` hoặc `Principal` generic | `@WithMockUser`, `authentication(...)`, OIDC helpers tùy mục tiêu |
| Principal domain tùy chỉnh | `@WithSecurityContext` hoặc `authentication(...)` với principal đúng loại |
| Authorized client token | Helper/fixture riêng cho `OAuth2AuthorizedClient` và manager/service |

**Nhớ:** `oauth2Login()` tạo OAuth2 login context; `oidcLogin()` tạo OIDC login context. Hai kiểu principal không được coi là tương đương chỉ vì cả hai có attributes.

## 8. Kiểm thử controller dùng `OAuth2User`

Một OAuth2 provider không hỗ trợ OIDC có thể trả về OAuth2 user attributes mà **không có ID Token**.

Controller:

```java
@RestController
class OAuth2ProfileController {

    @GetMapping("/api/oauth2-profile")
    Map<String, String> profile(
            @AuthenticationPrincipal OAuth2User user) {

        if (user == null) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        return Map.of(
            "name", user.getName(),
            "providerUserId",
                String.valueOf(user.getAttribute("id")));
    }
}
```

Test với `oauth2Login()`:

```java
@Test
void oauth2ProfileReadsUserAttributes() throws Exception {
    mvc.perform(get("/api/oauth2-profile")
            .with(oauth2Login()
                .attributes(attrs -> {
                    attrs.put("id", "provider-user-17");
                    attrs.put("name", "Alice");
                })))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("Alice"))
        .andExpect(jsonPath("$.providerUserId")
            .value("provider-user-17"));
}
```

**Điều cần kiểm tra:** `OAuth2User.getName()` phụ thuộc `nameAttributeKey` mà `DefaultOAuth2User` hoặc provider mapping chọn. Nếu provider dùng `"id"` thay `"name"` làm name attribute, cần dựng đúng fixture hoặc custom `OAuth2User`.

Không mặc định OAuth2 providers đều trả cùng claim names: GitHub có `id`/`login`, provider khác có `sub` hoặc trường riêng. Sự khác biệt nên được xử lý trong user service/attribute mapper chứ không nhồi các fallback thiếu kiểm soát vào mọi controller.

### 8.1. `oauth2Login()` có thay OIDC login test không?

Nếu controller nhận:

```java
@AuthenticationPrincipal OidcUser user
```

thì test `.with(oauth2Login())` thường **không tạo đúng OIDC principal**. Ngược lại, `OidcUser` là một subtype của `OAuth2User`, nhưng controller dựa vào ID Token/issuer/nonce vẫn cần OIDC-specific fixture.

Chọn helper theo **loại `Authentication` mà production sẽ tạo**, không theo việc cả hai đều có map attributes.

## 9. `@AuthenticationPrincipal(expression = "...")`: test giá trị được extract

Annotation hỗ trợ **Spring Expression Language (SpEL)** để lấy một phần của principal.

Ví dụ:

```java
@RestController
class SubjectController {

    @GetMapping("/api/subject")
    Map<String, String> subject(
        @AuthenticationPrincipal(
            expression = "attributes['sub']")
        String subject) {

        if (subject == null) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        return Map.of("subject", subject);
    }
}
```

Test:

```java
@Test
void subjectExpressionUsesOidcClaims() throws Exception {
    mvc.perform(get("/api/subject")
            .with(oidcLogin()
                .idToken(token -> token
                    .claim("sub", "subject-123"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject")
            .value("subject-123"));
}
```

Ở đây expression `attributes['sub']` truy cập attributes của OIDC principal, không đọc JSON từ request.

### 9.1. Khác giữa `attributes` và `idToken.claims`

Một `OidcUser` có thể chứa:

- `OidcIdToken` claims.
- `OidcUserInfo` claims.
- `getAttributes()` là view các attributes đã được OIDC user service kết hợp.

Nếu business logic cần **subject của ID Token** rõ ràng, có thể dùng:

```java
@AuthenticationPrincipal(
    expression = "idToken.claims['sub']")
String subject
```

Cần hiểu expression truy cập property JavaBean như `getIdToken()` và `getClaims()`. Nếu kiểu principal không phải `OidcUser`, expression có thể fail, không đơn giản luôn trả null.

Không viết SpEL dài làm authorization policy nhạy cảm nằm kín trong controller signature. Khi cần kiểm tra tenant membership, ownership hoặc entitlements, tốt hơn gọi domain authorization service có test riêng.

### 9.2. Test expression khi claim vắng mặt

Ví dụ:

```java
@GetMapping("/api/handle")
String handle(
    @AuthenticationPrincipal(
        expression = "attributes['preferred_username']")
    String preferredUsername) {

    return preferredUsername == null
        ? "anonymous-handle"
        : preferredUsername;
}
```

Kiểm thử:

```text
Claim preferred_username = "alice" -> "alice".
Claim preferred_username không tồn tại -> fallback phù hợp.
Principal không phải OAuth2User -> expression evaluation có thể lỗi.
```

Không coi `preferred_username` hoặc email là identity key duy nhất nếu provider có thể thay đổi trường đó.

### 9.3. `errorOnInvalidType`

```java
@GetMapping("/api/strict-me")
String strictMe(
        @AuthenticationPrincipal(errorOnInvalidType = true)
        OidcUser user) {

    return user.getSubject();
}
```

`errorOnInvalidType = true` giúp lỗi type mismatch xuất hiện rõ thay vì silently inject null.

Bộ tests nên có:

1. `oidcLogin()` → tham số đúng loại, endpoint thành công.
2. `@WithMockUser` → sai loại, request không được xử lý như một OIDC user.
3. Anonymous request → bị security layer chặn hoặc xử lý bằng hợp đồng rõ.

**Không phụ thuộc cứng vào một HTTP 500 cụ thể** cho type mismatch nếu exception handler/test environment không quy định status; hãy assert loại exception/contract mà ứng dụng thực sự cam kết.

## 10. Tạo meta-annotation tùy chỉnh cho OIDC principal

Khi nhiều controllers đều yêu cầu `OidcUser`, có thể tạo:

```java
@Target({
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@AuthenticationPrincipal
public @interface CurrentOidcUser {
}
```

Sau đó:

```java
@GetMapping("/api/me")
MeResponse me(@CurrentOidcUser OidcUser user) {
    return new MeResponse(
        user.getSubject(),
        user.getClaimAsString("email"),
        user.getIdToken().getClaimAsString("iss"));
}
```

Spring Security hỗ trợ meta-annotation dựa trên `@AuthenticationPrincipal` để giữ controller signature gọn hơn hoặc diễn đạt domain concept.

### 10.1. Meta-annotation với SpEL

Có thể định nghĩa annotation lấy ID của user từ custom principal:

```java
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@AuthenticationPrincipal(
    expression = "attributes['sub']")
public @interface CurrentSubject {
}
```

Dùng:

```java
@GetMapping("/api/subject")
String subject(@CurrentSubject String subject) {
    return subject;
}
```

Test bằng `oidcLogin()`:

```java
@Test
void currentSubjectAnnotationResolvesOidcSub()
        throws Exception {

    mvc.perform(get("/api/subject")
            .with(oidcLogin()
                .idToken(token -> token
                    .claim("sub", "s-007"))))
        .andExpect(status().isOk())
        .andExpect(content().string("s-007"));
}
```

**Lưu ý:** Tùy biến annotation phải được test qua Spring MVC argument resolver. Gọi trực tiếp controller method sẽ không kiểm tra annotation wiring.

## 11. Test một controller nhận cả principal và Authentication

Một endpoint đôi khi cần cả `OidcUser` và registration ID:

```java
@RestController
class IdentityContextController {

    @GetMapping("/api/identity-context")
    Map<String, String> current(
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {

        if (!(authentication instanceof OAuth2AuthenticationToken t)) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        if (user == null) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        return Map.of(
            "subject", user.getSubject(),
            "registrationId",
            t.getAuthorizedClientRegistrationId());
    }
}
```

Test:

```java
@Test
void returnsRegistrationIdFromOAuth2Authentication()
        throws Exception {

    mvc.perform(get("/api/identity-context")
            .with(oidcLogin()
                .clientRegistration(
                    ClientRegistration.withRegistrationId("corporate")
                        .clientId("portal-web")
                        .clientSecret("FAKE_TEST_SECRET")
                        .clientAuthenticationMethod(
                            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                        .authorizationGrantType(
                            AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri(
                            "{baseUrl}/login/oauth2/code/{registrationId}")
                        .authorizationUri("https://idp.example.test/auth")
                        .tokenUri("https://idp.example.test/token")
                        .jwkSetUri("https://idp.example.test/keys")
                        .scope("openid")
                        .build())
                .idToken(token -> token
                    .claim("sub", "user-88"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId")
            .value("corporate"))
        .andExpect(jsonPath("$.subject")
            .value("user-88"));
}
```

**Mục đích:** bảo đảm `Authentication` thuộc registration mong đợi, không chỉ principal có `sub` đúng. `ClientRegistration` ở đây là **test fixture**, các endpoints là URL giả và không thực hiện network requests.

Trong multi-tenant, một test có `registrationId = corporate` không chứng minh user có entitlement vào tenant corporate. **Tenant authorization** là bước riêng.

### 11.1. Dùng `@CurrentSecurityContext` nếu cần phần khác của context

Spring Security còn có:

```java
@CurrentSecurityContext
```

Dùng khi cần lấy `SecurityContext` hoặc một expression trên context:

```java
@GetMapping("/api/auth-name")
String authenticationName(
    @CurrentSecurityContext(
        expression = "authentication.name")
    String name) {

    return name;
}
```

Điều này khác `@AuthenticationPrincipal`, vốn lấy `authentication.principal` trước rồi mới thực hiện expression trên principal.

## 12. Test request chưa được xác thực

Một controller có `@AuthenticationPrincipal` thường nằm sau:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/me").authenticated());
```

Nếu request không có Authentication:

```java
@Test
void unauthenticatedRequestIsRejected()
        throws Exception {

    mvc.perform(get("/api/me"))
        .andExpect(status().isUnauthorized());
}
```

**Test này giả định** test security chain dùng HTTP Basic entry point như phần 6. Nếu production dùng `oauth2Login()`, unauthenticated browser request có thể được **redirect 302** đến login page hoặc Authorization Endpoint tùy cấu hình. Với REST API, có thể cấu hình entry point trả 401 theo đường dẫn API.

Vì vậy **không cố định**:

```text
Chưa đăng nhập -> luôn HTTP 401
```

mà hãy kiểm tra **hợp đồng đã cấu hình**:

| Security config | Kết quả request chưa đăng nhập thường gặp |
| --- | --- |
| `httpBasic()` cho API | HTTP 401 + `WWW-Authenticate` |
| `oauth2Login()` cho browser UI | HTTP 302 tới login page/authorization request |
| Custom `AuthenticationEntryPoint` JSON | HTTP 401 + JSON error |
| Endpoint `permitAll` | Controller có thể nhận `null` principal |
| `anonymous()` theo access policy | AnonymousAuthenticationToken có thể được phép |

### 12.1. Controller public có thể nhận null

Ví dụ:

```java
@GetMapping("/public/welcome")
String welcome(
        @AuthenticationPrincipal OidcUser user) {

    return user == null
        ? "Welcome, guest"
        : "Welcome, " + user.getSubject();
}
```

Tests:

```java
@Test
void publicWelcomeForAnonymous() throws Exception {
    mvc.perform(get("/public/welcome"))
        .andExpect(status().isOk())
        .andExpect(content().string("Welcome, guest"));
}

@Test
void publicWelcomeForOidcUser() throws Exception {
    mvc.perform(get("/public/welcome")
            .with(oidcLogin()
                .idToken(t -> t.claim("sub", "alice"))))
        .andExpect(status().isOk())
        .andExpect(content().string("Welcome, alice"));
}
```

**Chú ý:** Endpoint phải thật sự `permitAll` trong test security config. Nếu test config ở phần 6 chỉ cho `"/api/me"` authenticated và phần còn lại permitAll, hai tests này có thể hoạt động khi controller được nạp vào MVC context.

### 12.2. Không dùng `@WithAnonymousUser` rồi mong có OIDC claims

Anonymous principal thường là string/anonymous representation. Với parameter `OidcUser`, resolver mặc định sẽ không tạo ID Token mới, và trong nhiều trường hợp inject null.

Hành vi cần test là **public endpoint trả dữ liệu tối thiểu** hoặc **protected endpoint bị chặn**, không cố gắn một OIDC identity giả cho anonymous request.

## 13. Test quyền truy cập: principal hợp lệ chưa đủ

Một người dùng có `OidcUser` hợp lệ chưa chắc có quyền đọc mọi endpoint.

Ví dụ security config:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**")
        .hasAuthority("SCOPE_reports.admin")
    .anyRequest().authenticated());
```

`oidcLogin()` dựng principal, nhưng authorities mặc định của mock có thể **khác** authorities được app mapper cấp trong production.

Để test role/authority cụ thể:

```java
@Test
void readOnlyOidcUserCannotAccessAdmin()
        throws Exception {

    mvc.perform(get("/api/admin/reports")
            .with(oidcLogin()
                .authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_reports.read"))))
        .andExpect(status().isForbidden());
}
```

Và:

```java
@Test
void adminAuthorityAllowsAccess()
        throws Exception {

    mvc.perform(get("/api/admin/reports")
            .with(oidcLogin()
                .authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_reports.admin"))))
        .andExpect(status().isOk());
}
```

Các tests này giả định URL mapping/handler và security chain đã được nạp. Việc mock authorities đúng không tự chứng minh OP đã cấp scope/role thật hoặc application mapper từ JWT/UserInfo hoạt động; nên có integration tests riêng cho authorities mapper nếu đó là security-critical component.

### 13.1. Không tin authorities từ một header client tự cung cấp

Một anti-pattern:

```java
@GetMapping("/api/admin")
String admin(
        @RequestHeader("X-Role") String role,
        @AuthenticationPrincipal OidcUser user) {
    // tin X-Role từ browser
}
```

Một browser có thể gửi `X-Role: ADMIN` tùy ý. Test security nên cố tình gửi header này trong request chỉ có read-only authorities và xác minh access **vẫn bị từ chối**.

`@AuthenticationPrincipal` giúp lấy security identity đã được authentication layer cung cấp; authorization vẫn cần kiểm tra **server-side authorities/entitlements** đáng tin cậy.

## 14. Kiểm thử multi-tenant: không lấy tenant từ OIDC claim một cách mù quáng

Một hệ thống SaaS có thể dùng:

```text
registrationId = acme__oidc
issuer         = https://id.example.test/realms/acme
sub            = user-17
```

Một user đăng nhập qua Acme nhưng request:

```text
GET /api/tenants/beta/reports
```

Không được cho rằng user có quyền Beta chỉ vì `OidcUser` khác `null`.

### 14.1. Controller + authorization service

```java
@RestController
class TenantProfileController {

    private final TenantAuthorization tenantAuthorization;

    TenantProfileController(
            TenantAuthorization tenantAuthorization) {
        this.tenantAuthorization = tenantAuthorization;
    }

    @GetMapping("/api/tenants/{tenantId}/profile")
    Map<String, String> profile(
            @PathVariable String tenantId,
            @AuthenticationPrincipal OidcUser user) {

        if (user == null) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        String issuer =
            user.getIdToken().getClaimAsString("iss");

        tenantAuthorization.requireMembership(
            tenantId,
            issuer,
            user.getSubject());

        return Map.of(
            "tenantId", tenantId,
            "subject", user.getSubject());
    }
}
```

`TenantAuthorization` là **interface dịch vụ nội bộ do ứng dụng định nghĩa**, ví dụ:

```java
interface TenantAuthorization {
    void requireMembership(
        String tenantId,
        String issuer,
        String subject);
}
```

Service phải xác minh membership/entitlement từ nguồn đáng tin, không dùng duy nhất raw URL path hoặc email domain để cấp quyền.

### 14.2. Slice test với mocked service

Nếu dùng Spring Framework 6.2+/Spring Boot version tương ứng, có thể dùng `@MockitoBean`:

```java
@WebMvcTest(TenantProfileController.class)
@Import(TestSecurity.class)
class TenantProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    TenantAuthorization tenantAuthorization;

    @Test
    void sendsVerifiedIdentityToMembershipService()
            throws Exception {

        mvc.perform(get("/api/tenants/acme/profile")
                .with(oidcLogin()
                    .idToken(token -> token
                        .claim("sub", "subject-17")
                        .claim("iss",
                            "https://id.example.test/realms/acme"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("acme"));

        verify(tenantAuthorization).requireMembership(
            "acme",
            "https://id.example.test/realms/acme",
            "subject-17");
    }
}
```

`@MockitoBean` có package:

```java
org.springframework.test.context.bean.override.mockito.MockitoBean
```

Ở Spring Boot cũ, test có thể dùng `@MockBean` của Spring Boot Test. Không trộn hai annotations tùy tiện; chọn theo BOM/versions. `verify(...)` thuộc Mockito.

**Giới hạn quan trọng:** Mockito mock chỉ chứng minh controller **gọi đúng service với dữ liệu đúng**. Nó không chứng minh membership/authorization policy của service là an toàn. Cần test riêng cho service và integration test khi domain security đặc biệt quan trọng.

### 14.3. Test cross-tenant denial

Với Mockito, có thể cấu hình:

```java
doThrow(new AccessDeniedException(
    "Tenant membership required"))
    .when(tenantAuthorization)
    .requireMembership(
        eq("beta"),
        eq("https://id.example.test/realms/acme"),
        eq("subject-17"));
```

Sau đó request:

```text
GET /api/tenants/beta/profile
OIDC issuer = Acme
subject     = subject-17
```

Expected: **không trả profile của Beta**. HTTP status thường là `403` nếu Spring Security exception translation/controller error handling phù hợp; xác minh dựa trên security config thực tế.

Không sửa test bằng cách cho service “chấp nhận mọi tenant” để tạo response 200.

## 15. Tùy chỉnh toàn bộ OidcUser trong MockMvc

Đôi khi `.idToken(...)` chưa đủ. Ví dụ controller cần:

- `OidcUserInfo` từ UserInfo Endpoint.
- Customized `getName()` property.
- Authorities đã được mapper xử lý.
- Custom implementation của `OidcUser`.
- Name attribute key không phải mặc định.
- Nhiều claims có cấu trúc (groups, organization, locale).

Có thể dựng OIDC principal rõ ràng:

```java
Instant issuedAt = Instant.now().minusSeconds(10);
Instant expiresAt = Instant.now().plusSeconds(300);

OidcIdToken idToken = new OidcIdToken(
    "FAKE_ID_TOKEN",
    issuedAt,
    expiresAt,
    Map.of(
        "iss", "https://idp.example.test",
        "sub", "user-17",
        "aud", List.of("portal-web")));

OidcUserInfo userInfo = new OidcUserInfo(
    Map.of(
        "sub", "user-17",
        "email", "alice@example.test",
        "preferred_username", "alice"));

OidcUser principal = new DefaultOidcUser(
    List.of(new SimpleGrantedAuthority("ROLE_USER")),
    idToken,
    userInfo,
    "sub");
```

Sau đó:

```java
mvc.perform(get("/api/me")
        .with(oidcLogin().oidcUser(principal)))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.subject").value("user-17"));
```

Đây là fixture được dựng từ các API `OidcIdToken`, `OidcUserInfo` và `DefaultOidcUser` của Spring Security. Các chuỗi `"FAKE_ID_TOKEN"` không phải JWT đã được OP ký; MockMvc helper không tự liên lạc OP để xác minh.

### 15.1. Kiểm thử thiếu UserInfo

Một số providers không gọi UserInfo hoặc không cấp claim mong muốn. Test controller cần hoạt động khi principal chỉ có ID Token, không có UserInfo:

```java
OidcUser user = new DefaultOidcUser(
    List.of(new SimpleGrantedAuthority("ROLE_USER")),
    idToken);
```

Nếu business logic yêu cầu email, cần định nghĩa hành vi rõ khi email không có. Không mặc nhiên cho rằng mọi `OidcUser` đều có email/roles/groups.

### 15.2. Kiểm thử `getName()` tùy chỉnh

Với `DefaultOidcUser` nhận `nameAttributeKey = "preferred_username"` hoặc một thuộc tính phù hợp, `getName()` có thể không còn giống `sub`.

Test case nên phân biệt:

```text
subject = "user-17"
preferred_username = "alice"
getName() = "alice" theo nameAttributeKey đã cấu hình
```

Nếu dữ liệu dùng làm security principal key cần bất biến, nên dùng subject+issuer thay vì display username.

## 16. Tạo custom `@WithSecurityContext` cho nhiều test methods

Khi có hàng chục controller tests cần cùng OIDC identity, việc lặp `.with(oidcLogin().idToken(...))` ở mọi request có thể dài. Spring Security Test cho phép tạo annotation test tùy chỉnh dựa trên:

```java
@WithSecurityContext
```

### 16.1. Định nghĩa annotation

```java
@Target({
    ElementType.METHOD,
    ElementType.TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(
    factory = WithTestOidcUserFactory.class)
public @interface WithTestOidcUser {

    String sub() default "test-user";

    String issuer()
        default "https://idp.example.test/realms/acme";

    String registrationId() default "corporate";
}
```

Annotation này do dự án tự định nghĩa, **không có sẵn trong Spring Security**.

### 16.2. Factory dựng SecurityContext

```java
public final class WithTestOidcUserFactory
    implements WithSecurityContextFactory<WithTestOidcUser> {

    @Override
    public SecurityContext createSecurityContext(
            WithTestOidcUser annotation) {

        Instant now = Instant.now();

        OidcIdToken idToken = new OidcIdToken(
            "FAKE_TEST_ID_TOKEN",
            now.minusSeconds(5),
            now.plusSeconds(300),
            Map.of(
                "iss", annotation.issuer(),
                "sub", annotation.sub(),
                "aud", List.of("portal-web")));

        OidcUser oidcUser = new DefaultOidcUser(
            List.of(new SimpleGrantedAuthority("ROLE_USER")),
            idToken);

        Authentication authentication =
            new OAuth2AuthenticationToken(
                oidcUser,
                oidcUser.getAuthorities(),
                annotation.registrationId());

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();

        context.setAuthentication(authentication);
        return context;
    }
}
```

Mục đích là test **đúng principal type** và `OAuth2AuthenticationToken` theo contract sản phẩm, không chỉ set username string.

### 16.3. Sử dụng annotation

```java
@Test
@WithTestOidcUser(
    sub = "s-123",
    registrationId = "corporate")
void returnsSubjectWithoutPerRequestPostProcessor()
        throws Exception {

    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject")
            .value("s-123"));
}
```

Khi `MockMvc`/Spring Security TestContext setup đúng, annotation tạo SecurityContext phục vụ request test.

**Khi nào nên dùng cách nào?**

- Một vài test cases cần claims khác nhau theo request: dùng `.with(oidcLogin())`.
- Một test class lớn có identity fixture chuẩn: cân nhắc `@WithTestOidcUser`.
- Cần kiểm thử nhiều requests trong **cùng test** với các users khác nhau: request postprocessors thường rõ ràng hơn.
- Cần integration-test OIDC callback/token validation thật: **không** dùng synthetic `@WithSecurityContext` làm bằng chứng protocol.

### 16.4. Tránh rò SecurityContext giữa tests

Spring Security TestContext thường quản lý lifecycle, nhưng custom utilities hoặc `SecurityContextHolder.setContext(...)` viết tay có thể để lại context trong thread được tái sử dụng.

Nếu tự thiết lập context trong unit test ngoài framework hỗ trợ:

```java
try {
    SecurityContextHolder.setContext(context);
    // run assertions
} finally {
    SecurityContextHolder.clearContext();
}
```

Trong MockMvc tests, ưu tiên helpers chính thức hơn tự mutate static/thread-local state. Không sử dụng global static `Authentication` làm user của tất cả tests nếu có thể dẫn đến leakage.

## 17. `MockMvcBuilders.standaloneSetup(...)` và `springSecurity()`

Một source phổ biến của test “controller nhận null principal” là tạo `MockMvc` bằng:

```java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(controller)
    .build();
```

Cách này **không tự động cấu hình toàn bộ Spring Security filter chain**. Request postprocessors `oidcLogin()` được thiết kế để làm việc với Spring Security Test và một security filter/context setup phù hợp.

Khi tự xây MockMvc:

```java
MockMvc mvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
```

Đây là cách thường dùng khi context có `springSecurityFilterChain` phù hợp. Static import:

```java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;
```

### 17.1. Tại sao apply `springSecurity()` quan trọng?

Nó giúp MockMvc tích hợp security filters và các test helpers cần thiết để đưa Authentication vào SecurityContext đúng cách. Nếu chỉ tạo MockMvc standalone rồi `.with(oidcLogin())`, có thể nhận principal null hoặc khác mong đợi tùy setup.

### 17.2. Có thể dùng standalone setup không?

Có, nhưng phải **cấu hình Security filter chain và argument resolvers phù hợp** nếu muốn kiểm thử security context injection. Điều này dễ bỏ sót và khiến test khác production.

Với yêu cầu kiểm thử `@AuthenticationPrincipal`, **`@WebMvcTest` với auto-configured MockMvc** hoặc `webAppContextSetup(...).apply(springSecurity())` thường rõ ràng hơn. Standalone setup phù hợp cho unit tests controller logic khi bạn truyền principal trực tiếp như một parameter.

### 17.3. Tránh filter chain bị disable trong test

Những thao tác như bỏ Spring Security filters khỏi MockMvc hoặc `@AutoConfigureMockMvc(addFilters = false)` có thể khiến:

- Endpoint protected trả dữ liệu cho anonymous request trong test.
- Request postprocessors không còn hoạt động như production.
- `@AuthenticationPrincipal` không nhận context đúng.
- Tests cho `401`, `403`, CSRF thành vô nghĩa.

Chỉ disable filters nếu test **cố ý** giới hạn phạm vi, và không dùng kết quả đó để khẳng định security integration đã hoạt động.

## 18. `@SpringBootTest` và `@AutoConfigureMockMvc`

Khi cần chạy controller với cấu hình security gần production hơn:

```java
@SpringBootTest
@AutoConfigureMockMvc
class MeControllerIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void oidcPrincipalReachesController()
            throws Exception {

        mvc.perform(get("/api/me")
                .with(oidcLogin()
                    .idToken(t -> t.claim(
                        "sub", "integration-user"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject")
                .value("integration-user"));
    }
}
```

**Khác với `@WebMvcTest`:**

- Load nhiều beans/application configuration hơn.
- Có thể cần test datasource/profiles/config secrets.
- Dùng production-style `SecurityFilterChain` nếu test không override.
- Vẫn **không thực hiện OIDC Authorization Code flow thật** khi dùng `oidcLogin()`.

Để kiểm tra việc Spring Security parse ID Token từ Token Endpoint, validate issuer/audience/nonce và tạo `OidcUser`, cần thêm test với OP sandbox/fake token endpoint và signing keys thích hợp.

### 18.1. Khi full-context test không khởi động

Một ứng dụng cấu hình:

```java
.oauth2Login(...)
```

có thể cần `ClientRegistrationRepository` hợp lệ. Nếu test profile không có OIDC issuer metadata/registration, startup có thể lỗi do missing bean/config. Đây là **test context configuration issue**, không phải `@AuthenticationPrincipal` bug.

Có thể:

- Cung cấp test `ClientRegistrationRepository` với fake endpoints.
- Mock những collaborators không thuộc scope.
- Dùng `@WebMvcTest` và test SecurityFilterChain như phần 6.
- Tách protocol integration tests có test OP riêng.

Không dùng production client secrets hoặc account thật trong controller tests.

## 19. HTTP request postprocessor so với method-level annotation

Có hai cách đặt mock Authentication phổ biến:

### 19.1. Trên từng HTTP request

```java
mvc.perform(get("/api/me")
    .with(oidcLogin()));
```

Ưu điểm:

- Explicit ngay tại request.
- Dễ thử nhiều principals trong một test.
- Dễ thay attributes/authorities/registration ID.
- Dễ tạo matrix positive/negative cho cùng endpoint.

### 19.2. Trên test method/class

```java
@Test
@WithTestOidcUser(sub = "alice")
void testMe() throws Exception {
    mvc.perform(get("/api/me"))
       .andExpect(status().isOk());
}
```

Ưu điểm:

- Gọn với fixture lặp lại.
- Dễ đọc test class có một identity mặc định.

Nhược điểm:

- Khi request setup phức tạp, có thể không rõ test dùng Authentication nào.
- Nếu kết hợp `@WithMockUser` và `.with(oidcLogin())` trong cùng test, **Authentication được dùng cuối cùng phụ thuộc test setup/order**; nên tránh fixture chồng chéo không cần thiết.
- TestContext cần tích hợp Spring Security Test đúng.

**Khuyến nghị:** mỗi test nên có một **nguồn principal rõ ràng**, tránh dùng cả annotation + postprocessor với identity khác nhau trừ khi bạn đang cố tình kiểm tra precedence.

## 20. `@AuthenticationPrincipal` không lấy `OAuth2AuthorizedClient`

Controller OIDC Login có thể cần đồng thời:

```java
@AuthenticationPrincipal OidcUser user
```

và một authorized client:

```java
@RegisteredOAuth2AuthorizedClient("corporate")
OAuth2AuthorizedClient authorizedClient
```

Hai annotations nhận dữ liệu từ **hai nguồn khác nhau**.

| Annotation | Đối tượng | Nguồn |
| --- | --- | --- |
| `@AuthenticationPrincipal` | `OidcUser`, `OAuth2User`, `UserDetails`, `Jwt`... | `Authentication.getPrincipal()` |
| `@RegisteredOAuth2AuthorizedClient` | `OAuth2AuthorizedClient` | Authorized-client repository/service/manager và registration |
| `@CurrentSecurityContext` | SecurityContext hoặc expression | Current SecurityContext |

Nếu controller:

```java
@GetMapping("/api/downstream")
String downstream(
        @AuthenticationPrincipal OidcUser user,
        @RegisteredOAuth2AuthorizedClient("corporate")
        OAuth2AuthorizedClient client) {

    // user là identity.
    // client.getAccessToken() là OAuth2 token dùng cho API.
    return user.getSubject();
}
```

thì:

```java
.with(oidcLogin())
```

không nên bị coi là **bằng chứng đủ** authorized-client store có token sẵn cho mọi registration. Mặc dù test helper có thể thiết lập OAuth2 login context, lifecycle và persistence của authorized clients vẫn cần fixture/test riêng theo resolver/service mà controller dùng.

### 20.1. Nếu cần test bearer token

Giả sử service gọi downstream API. Nên mock service/client adapter hoặc fake API server và assert:

- Token được lấy từ đúng authorized client.
- Access token không phải ID Token.
- Registration ID/subject/tenant đúng.
- Token không gửi tới API host tùy ý.
- Lỗi downstream được xử lý an toàn.

Không đưa raw bearer tokens vào controller response chỉ để dễ assert.

## 21. Kiểm thử argument resolver khi principal sai loại

Một test suite hữu ích nên có các cases:

| Principal fixture | Controller đòi | Kỳ vọng cơ bản |
| --- | --- | --- |
| `oidcLogin()` | `OidcUser` | Injection đúng loại |
| `oidcLogin()` | `OAuth2User` | Có thể inject vì `OidcUser` là subtype của `OAuth2User` |
| `oauth2Login()` | `OAuth2User` | Injection đúng loại |
| `oauth2Login()` | `OidcUser` | Mismatch; `null` hoặc exception theo annotation |
| `@WithMockUser` | `OidcUser` | Mismatch |
| `.with(jwt())` | `Jwt` | Đúng khi API là JWT Resource Server |
| `.with(jwt())` | `OidcUser` | Mismatch |
| Anonymous request, endpoint protected | `OidcUser` | Security entry point chặn trước controller |
| Anonymous request, endpoint public | `OidcUser` | Có thể nhận null |
| Custom principal | Custom parameter type | Phải dựng đúng Authentication |

### 21.1. Khi `@AuthenticationPrincipal` trả null dù request “đã authenticated”

Điều tra theo thứ tự:

1. `Authentication` trong SecurityContext thuộc loại gì?
2. `authentication.getPrincipal().getClass()` là gì? Chỉ log class name, không log principal object đầy claims.
3. Controller parameter type là gì?
4. Có `errorOnInvalidType = true` không?
5. Có SpEL expression không?
6. Filter chain có thực sự chạy trong MockMvc không?
7. Có custom security context setup/helper ghi đè mock OIDC login không?
8. Có nhiều security filter chains match URL khác nhau không?
9. Test đang dùng `@WithMockUser`, `oauth2Login()` hay `oidcLogin()`?
10. Controller có `@AuthenticationPrincipal` meta-annotation đúng retention/target không?

**Không sửa bằng cách ép kiểu không kiểm tra**:

```java
OidcUser user =
    (OidcUser) SecurityContextHolder
        .getContext()
        .getAuthentication()
        .getPrincipal();
```

Nếu Authentication thực sự không phải OIDC login, phép cast này cũng sai và dễ che giấu lỗi cấu hình.

## 22. Kiểm thử response và exception contract

Ngoài việc inject đúng principal, một controller tốt nên có response contract rõ ràng.

### 22.1. Happy path

Given: OIDC principal có `sub`, issuer và email phù hợp.

When: `GET /api/me`.

Then:

- HTTP 200.
- JSON DTO chỉ chứa các trường đã được phép.
- Subject đúng.
- Không trả access/ID/refresh tokens.
- Không lộ toàn bộ claims chứa PII.

### 22.2. Missing required claim

Nếu ứng dụng yêu cầu `sub` nhưng mock principal bị thiếu, Spring Security `OidcIdToken` hoặc `DefaultOidcUser` có thể có các invariant/behavior riêng. Thay vì cố dựng một object bất hợp lệ rồi gán nhãn như production OIDC response, hãy:

- Test validation của mapper/DTO khi nhận đầu vào bất hợp lệ.
- Test OIDC token validation ở protocol integration level.
- Test controller trả lỗi hợp đồng nếu application mapper có thể nhận thiếu identity.
- Không mặc định một mock `OidcUser` được tạo không kiểm tra đầy đủ có nghĩa OP thật có thể phát ID Token như vậy.

### 22.3. Missing optional email

Email có thể thiếu. Test:

```text
email present  -> DTO có email.
email absent   -> DTO trả null/omit hoặc lỗi nghiệp vụ đã định.
```

Không dùng `sub` làm email giả hoặc trả `username@company` tự dựng nếu không có policy.

### 22.4. Authorization denial

Given: OIDC user xác thực hợp lệ nhưng không có membership tenant.

Then:

- HTTP 403 hoặc business authorization response theo policy.
- Không truy xuất/tiết lộ dữ liệu tenant.
- Không cache cross-tenant response.
- Không coi authentication success là authorization success.

### 22.5. Sanitized failure

Khi xảy ra exception, response/logs không nên chứa:

```text
id_token=<raw>
access_token=<raw>
refresh_token=<raw>
client_secret=<raw>
fullOidcClaims=<PII>
```

Nếu dùng `@ControllerAdvice`, viết test cho safe error mapping và HTTP status, không chỉ `assertThrows`.

## 23. Test CSRF trên controller có HTTP POST

`@AuthenticationPrincipal` vẫn hoạt động trên POST, nhưng với browser session application, POST có thể cần CSRF token:

```java
@PostMapping("/api/preferences")
ResponseEntity<Void> save(
        @AuthenticationPrincipal OidcUser user,
        @RequestBody Preferences preferences) {

    preferencesService.save(
        user.getSubject(), preferences);

    return ResponseEntity.noContent().build();
}
```

Test có CSRF token:

```java
mvc.perform(post("/api/preferences")
        .with(oidcLogin()
            .idToken(t -> t.claim("sub", "user-1")))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"theme":"dark"}
            """))
    .andExpect(status().isNoContent());
```

Test thiếu CSRF:

```java
mvc.perform(post("/api/preferences")
        .with(oidcLogin()))
    .andExpect(status().isForbidden());
```

Các tests này giả định **CSRF protection được bật** trong test security chain, method mapping và service dependencies được cung cấp đúng. Nếu app dùng stateless API với CSRF policy khác, expected status có thể khác.

**Không disable CSRF toàn bộ** để sửa một controller test. Với OAuth2 Login dùng browser cookies, CSRF vẫn là thành phần quan trọng.

## 24. Async controllers và propagation của SecurityContext

Một số Servlet controllers dùng asynchronous MVC:

```java
@GetMapping("/api/async-me")
Callable<String> asyncMe(
        @AuthenticationPrincipal OidcUser user) {

    return () -> "hello-" + user.getSubject();
}
```

Trong ví dụ này, principal được inject **trước** khi async work bắt đầu; lambda giữ reference đã resolve. Nếu service chạy trên thread khác và tự gọi `SecurityContextHolder`, cần hiểu SecurityContext propagation. Spring Security có cơ chế hỗ trợ Servlet async và `DelegatingSecurityContext*` wrappers cho các executor use cases, nhưng không tự đảm bảo mọi custom thread pool đều giữ context.

Test có thể dùng MockMvc async assertions:

```java
MvcResult result = mvc.perform(
        get("/api/async-me")
            .with(oidcLogin()
                .idToken(t -> t.claim("sub", "u-async"))))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andExpect(content().string("hello-u-async"));
```

Đây là **Servlet MockMvc** test; không nhầm với WebFlux `Mono`/`WebTestClient`.

### 24.1. Nếu service cần SecurityContext ở executor

Đừng chỉ test kết quả string. Có thể test rằng service nhận đúng principal hoặc explicit subject parameter. Tốt nhất với domain logic là truyền dữ liệu identity cần thiết theo parameter đã xác minh:

```java
reportService.loadReports(
    user.getIdToken().getClaimAsString("iss"),
    user.getSubject());
```

thay vì để deep business layer phải đọc `SecurityContextHolder` qua nhiều threads.

## 25. Method security và annotation-driven controller tests

Một controller/service có thể dùng:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
@GetMapping("/api/reports")
List<Report> reports(
        @AuthenticationPrincipal OidcUser user) {
    return reportService.forUser(user.getSubject());
}
```

Để annotation method security thực sự hoạt động trong tests, application/test context phải có **method security configuration** như `@EnableMethodSecurity` và các proxies phù hợp.

Nếu một `@WebMvcTest` chỉ load controller mà không bật method security, test có thể **pass một endpoint lẽ ra bị từ chối**.

Phân biệt:

- **Filter-chain URL rules:** `.authorizeHttpRequests(...)`.
- **Method security:** `@PreAuthorize`, `@PostAuthorize`, các interceptors/proxies.
- **Domain authorization:** membership/entitlements/ownership trong service.

Một test dùng mock OIDC principal không tự kích hoạt tất cả các layers nếu test context đã cắt bỏ chúng.

### 25.1. Test cả permitted và denied authorities

Một bộ test tối thiểu:

```text
Principal OidcUser + SCOPE_reports.read
    GET /api/reports -> allow

Principal OidcUser không có SCOPE_reports.read
    GET /api/reports -> deny

Anonymous
    GET /api/reports -> login entry point/401

Principal có scope nhưng không thuộc tenant
    GET /api/tenants/T2/reports -> domain deny
```

**Đừng chỉ assert controller service được gọi** mà bỏ quan sát HTTP status và authorization behavior nếu endpoint nhạy cảm.

## 26. `Jwt` principal: phân biệt OAuth2 Client với Resource Server

Một ứng dụng có thể đồng thời:

- Đăng nhập browser qua OIDC Login (principal `OidcUser`).
- Nhận bearer access token ở API (principal `Jwt` hoặc `BearerTokenAuthentication` tùy token type).

Hai request security flows này khác nhau.

Ví dụ Resource Server controller:

```java
@GetMapping("/api/service-subject")
String serviceSubject(
        @AuthenticationPrincipal Jwt jwt) {

    return jwt.getSubject();
}
```

MockMvc helper:

```java
mvc.perform(get("/api/service-subject")
        .with(jwt().jwt(token -> token
            .claim("sub", "service-user")
            .claim("aud", List.of("reports-api")))))
    .andExpect(status().isOk())
    .andExpect(content().string("service-user"));
```

Trong đó `jwt()` thuộc:

```java
SecurityMockMvcRequestPostProcessors.jwt()
```

**Không dùng `oidcLogin()` để kiểm thử controller kỳ vọng principal `Jwt` từ Resource Server**, và không dùng `jwt()` để giả OIDC Login `OidcUser`.

### 26.1. `jwt()` không kiểm thử JWT signature/audience validation thật

`jwt()` trực tiếp thiết lập JWT Authentication cho request test; không gọi remote JWKS hoặc verify chữ ký theo full token decoder. Nó phù hợp để test controller và authority mapping đã chọn, **không đủ** để chứng minh API reject JWT sai issuer/audience/expiry.

Muốn kiểm thử decoder:

- Dùng signed JWT fixtures với test JWKS/test issuer.
- Giữ `JwtDecoder` validators theo production policy.
- Test `401 invalid_token` cho sai issuer/audience/signature/expiry.
- Không tắt JWT validation production để test dễ pass.

## 27. Cách tách test fixtures và giữ dữ liệu độc lập

Khi nhiều tests cần OIDC principal, có thể dùng factory:

```java
final class TestOidcUsers {

    static OidcUser user(
            String issuer,
            String subject,
            String email) {

        Instant now = Instant.now();

        Map<String, Object> claims = new HashMap<>();
        claims.put("iss", issuer);
        claims.put("sub", subject);
        claims.put("aud", List.of("portal-web"));

        if (email != null) {
            claims.put("email", email);
        }

        OidcIdToken token = new OidcIdToken(
            "FAKE_ID_TOKEN",
            now.minusSeconds(10),
            now.plusSeconds(300),
            claims);

        return new DefaultOidcUser(
            List.of(
                new SimpleGrantedAuthority("ROLE_USER")),
            token);
    }
}
```

Test:

```java
mvc.perform(get("/api/me")
        .with(oidcLogin().oidcUser(
            TestOidcUsers.user(
                "https://idp.example.test/realms/acme",
                "acme-u17",
                null))))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.subject").value("acme-u17"));
```

Một factory giúp consistency nhưng **không nên che giấu security assumptions**. Cần test cases riêng cho:

- Issuer khác tenant.
- `sub` trùng giữa hai issuers.
- Email thiếu/đã thay đổi.
- Name attribute key tùy provider.
- Authorities thiếu.
- UserInfo không có.
- Principal sai kiểu.
- Public/anonymous request.

Không dùng một ID Token giả có email/roles đầy đủ cho mọi test, vì sẽ bỏ sót nullable claims và privilege boundaries.

## 28. Kiểm thử custom principal không phải `OidcUser`

Một ứng dụng có thể chuyển OIDC claims sang principal domain-specific sau authentication:

```java
public record PortalPrincipal(
    String issuer,
    String subject,
    String tenantId) {}
```

Controller:

```java
@GetMapping("/api/domain-me")
Map<String, String> me(
        @AuthenticationPrincipal PortalPrincipal user) {

    return Map.of(
        "tenantId", user.tenantId(),
        "subject", user.subject());
}
```

`oidcLogin()` mặc định **không tạo PortalPrincipal** vì nó tạo `OidcUser`. Để test controller này, cần dựng một Authentication chứa đúng custom principal:

```java
PortalPrincipal user = new PortalPrincipal(
    "https://idp.example.test",
    "u-42",
    "acme");

Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        user,
        "N/A",
        List.of(new SimpleGrantedAuthority("ROLE_USER")));

mvc.perform(get("/api/domain-me")
        .with(
            SecurityMockMvcRequestPostProcessors
                .authentication(authentication)))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.tenantId").value("acme"));
```

Đây là **test fixture**; kiểu `UsernamePasswordAuthenticationToken` trong mock không chứng minh production từng đăng nhập bằng username/password. Nếu production sử dụng custom `Authentication` class, nên dựng đúng kiểu đó cho những tests cần kiểm tra security context.

### 28.1. Khi nào nên dùng custom principal?

Có thể có lợi nếu ứng dụng:

- Không muốn controllers phụ thuộc trực tiếp vào Spring Security OAuth2 types.
- Cần một identity model `(issuer, subject, tenant)`.
- Có nhiều login mechanisms nhưng muốn một domain principal thống nhất.
- Có requirements về claim normalization và entitlement mapping.

Tuy nhiên chuyển đổi OIDC principal thành domain principal phải được thực hiện **sau khi OIDC token validation thật**, không dựa trên raw headers/query parameters. Unit tests của controller vẫn cần tách khỏi tests của converter/validator.

## 29. Các anti-pattern kiểm thử thường gặp

### 29.1. `@WithMockUser` cho mọi controller

Sai khi controller cần `OidcUser` hoặc `OAuth2User` cụ thể. Có thể nhận null/exception hoặc bỏ qua logic OIDC claims.

**Thay thế:** `oidcLogin()`, `oauth2Login()` hoặc custom security context factory đúng loại.

### 29.2. `@AuthenticationPrincipal` được kiểm thử bằng gọi method trực tiếp

Không kiểm tra MVC argument resolution, filter chain, HTTP status và exception mapping.

**Thay thế:** ít nhất một MockMvc test cho mỗi pattern principal injection quan trọng.

### 29.3. `standaloneSetup()` mà không tích hợp Spring Security

Có thể khiến mock Authentication không được đưa vào context hoặc security filters không chạy.

**Thay thế:** `@WebMvcTest`/`@AutoConfigureMockMvc` hoặc `webAppContextSetup(...).apply(springSecurity())`.

### 29.4. Principal sai loại nhưng controller dùng ép kiểu thủ công

Ép kiểu hoặc lấy claim từ `Object` mà không kiểm tra làm test khó chẩn đoán.

**Thay thế:** parameter typed và `errorOnInvalidType` khi muốn fail fast.

### 29.5. Assert username nhưng không assert subject/issuer

`getName()` có thể tùy config. Trong multi-issuer, `sub` không globally unique.

**Thay thế:** test rõ `(issuer, subject)` và tenant membership.

### 29.6. Chỉ kiểm tra 200 mà không kiểm tra dữ liệu

Endpoint có thể 200 nhưng trả identity sai hoặc dữ liệu của tenant khác.

**Thay thế:** assert JSON fields và service call arguments.

### 29.7. Mock all authorities thành ADMIN

Tạo happy path nhưng không kiểm tra least privilege.

**Thay thế:** test read-only, admin, missing authority, cross-tenant denial.

### 29.8. Mock OIDC User có đầy đủ mọi claim

Không phát hiện behavior khi email/preferred_username/locale thiếu.

**Thay thế:** test optional claims và provider-specific mappings.

### 29.9. `oidcLogin()` được coi là signature validation test

Helper không thực hiện Authorization Code/JWT cryptographic verification.

**Thay thế:** protocol integration tests với OP sandbox/test JWKS.

### 29.10. Dùng `jwt()` cho OIDC Login

`Jwt` trong Resource Server context không cùng kiểu với `OidcUser`.

**Thay thế:** chọn helper theo authentication mechanism.

### 29.11. Cho controller lấy Authorization header rồi parse token thủ công

Làm security logic rải rác và có nguy cơ bỏ validation framework.

**Thay thế:** dùng Spring Security authentication filters và typed principal.

### 29.12. Bỏ filters trong test để làm endpoint pass

Không kiểm tra request thực sự được authentication/authorization.

**Thay thế:** giữ security filters khi mục tiêu là request/security integration.

### 29.13. Dùng email domain để xác định tenant quyền hạn

Email có thể chưa xác minh/thay đổi và không chứng minh membership.

**Thay thế:** verified OIDC identity và domain authorization service.

### 29.14. Log toàn bộ OidcUser hoặc ID Token

Có thể lộ PII, session ID, token claims và credentials.

**Thay thế:** chỉ log non-sensitive issuer alias, principal type, outcome và correlation ID.

### 29.15. Test có nhiều nguồn Authentication

Dùng `@WithMockUser` và `.with(oidcLogin())` đồng thời không kiểm soát precedence làm test khó hiểu.

**Thay thế:** mỗi test một identity fixture rõ ràng.

## 30. Ma trận kiểm thử controller `@AuthenticationPrincipal`

| ID | Controller cần | Test context | Điều kỳ vọng |
| --- | --- | --- | --- |
| C01 | `OidcUser` | `.with(oidcLogin())` | Principal đúng loại, 2xx theo business logic |
| C02 | `OidcUser` | ID Token sub tùy chỉnh | DTO chứa đúng sub |
| C03 | `OidcUser` | ID Token issuer tùy chỉnh | DTO/mapper dùng đúng issuer |
| C04 | `OidcUser` | Email không có | Hành vi nullable/fallback đúng |
| C05 | `OidcUser` | `.with(oauth2Login())` | Type mismatch được xử lý đúng |
| C06 | `OidcUser` | `@WithMockUser` | Không giả mạo thành OIDC |
| C07 | `OidcUser` | Anonymous, protected endpoint | 401/302 theo entry point |
| C08 | `OidcUser` | Anonymous, public endpoint | Guest response/nullable principal |
| C09 | `OAuth2User` | `.with(oauth2Login())` | Provider attributes được đọc đúng |
| C10 | `Jwt` | `.with(jwt())` | Resource Server principal đúng |
| C11 | `OidcUser` | `.with(jwt())` | Type mismatch |
| C12 | `@CurrentSubject` | `oidcLogin()` | SpEL meta annotation extract sub |
| C13 | `errorOnInvalidType=true` | Wrong principal type | Fail fast, không silent null |
| C14 | `Authentication` + `OidcUser` | OIDC login registration=corporate | Đọc registrationId đúng |
| C15 | Domain principal | Custom Authentication | Injection đúng custom type |
| C16 | Tenant endpoint | OIDC Acme + tenant Acme membership | Allowed |
| C17 | Tenant endpoint | OIDC Acme + tenant Beta | Denied |
| C18 | URL role protection | OIDC user only read authority | Admin endpoint 403 |
| C19 | URL role protection | OIDC user admin authority | Admin endpoint 2xx |
| C20 | POST with CSRF | OIDC principal + CSRF | Business action có thể thực hiện |
| C21 | POST without CSRF | OIDC principal | 403 nếu CSRF enabled |
| C22 | Async controller | OIDC principal + asyncDispatch | Subject đúng qua async |
| C23 | Controller response | OIDC user có token | Không trả raw tokens/PII ngoài contract |
| C24 | MockMvc setup | Security filters disabled | Test không được dùng để kết luận authn hoạt động |
| C25 | Authenticated user, missing membership | Domain service deny | Không trả dữ liệu tenant |
| C26 | Same `sub`, different issuer | Hai OIDC principals | Không trộn identity keys |
| C27 | Custom OidcUser name attribute | Preferred username khác sub | Phân biệt `getName` và subject |
| C28 | `@RegisteredOAuth2AuthorizedClient` | Chỉ mock OIDC login | Không mặc nhiên khẳng định token storage |
| C29 | Spring Method Security | `@PreAuthorize` + config | Check method security thực sự được bật |
| C30 | Error response | Exception/invalid context | Không log/return ID/access/refresh tokens |

**Lưu ý:** HTTP status cụ thể phụ thuộc SecurityFilterChain, AuthenticationEntryPoint, controller advice và việc test đang dùng MVC slice hay full app context. Test suite phải xác nhận **hợp đồng của ứng dụng**, không giả định mặc định của mọi Spring Boot setup giống nhau.

## 31. Một bộ test mẫu có cấu trúc rõ ràng

Một project có thể chia:

```text
src/main/java/
  example/portal/web/
    MeController.java
    TenantProfileController.java
  example/portal/security/
    SecurityConfig.java
    TenantAuthorization.java

src/test/java/
  example/portal/web/
    MeControllerTest.java
    TenantProfileControllerTest.java
  example/portal/security/
    TestOidcUsers.java
    WithTestOidcUser.java
    WithTestOidcUserFactory.java
  example/portal/integration/
    OidcLoginFlowIntegrationTest.java
    ResourceServerJwtValidationTest.java
```

### 31.1. Vai trò của từng test

| File | Trọng tâm |
| --- | --- |
| `MeControllerTest` | `@AuthenticationPrincipal OidcUser`, JSON DTO, unauthenticated behavior |
| `TenantProfileControllerTest` | Controller truyền `(tenant, issuer, sub)` tới authorization service |
| `TestOidcUsers` | Dữ liệu `OidcIdToken`, `OidcUserInfo`, authorities tổng hợp |
| `WithTestOidcUser` | Chia sẻ fixture đúng OIDC principal type |
| `OidcLoginFlowIntegrationTest` | Authorization Request, callback, Token Endpoint, issuer/audience/nonce validation |
| `ResourceServerJwtValidationTest` | JWT decoder, `iss`, `aud`, signature, expiry, API authorization |

Không cần đưa mọi test vào cùng một `@SpringBootTest` nặng. Controller tests thường chạy nhanh với `@WebMvcTest`; security protocol tests có setup riêng theo threat model.

### 31.2. Một mẫu Given–When–Then

```text
Given
    Spring MVC controller /api/me
    SecurityFilterChain bảo vệ endpoint
    OidcUser với issuer, subject và email tổng hợp

When
    MockMvc GET /api/me + oidcLogin()

Then
    HTTP 200
    JSON subject đúng
    JSON issuer đúng
    Không có ID Token/access token trong response

And
    Không gọi Authorization Endpoint/Token Endpoint thật
```

Trường hợp từ chối:

```text
Given
    OidcUser có issuer Acme, sub A17
    TenantAuthorization không cho truy cập Beta

When
    GET /api/tenants/beta/profile

Then
    Không có dữ liệu Beta
    HTTP 403 hoặc lỗi hợp đồng tương ứng
    Không tự tin vào tenant path hoặc email
```

## 32. Troubleshooting khi test không như mong đợi

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `@AuthenticationPrincipal OidcUser` nhận null | Dùng `@WithMockUser`/`oauth2Login()` sai loại | Dùng `oidcLogin()` |
| Controller bị NPE trong test | Principal null, thiếu claim | Kiểm tra fixture và nullable contract |
| MockMvc request không có SecurityContext | Security filters/setup chưa tích hợp | Dùng auto-config MockMvc hoặc `.apply(springSecurity())` |
| Anonymous test trả 302 thay 401 | App dùng OAuth2 Login entry point | Test theo config hoặc đặt API entry point riêng |
| `@WithMockUser` cho 200 dù OIDC type mismatch | Security `.authenticated()` không kiểm tra principal Java type | Test đúng OIDC principal |
| `getName()` khác `sub` | Custom name attribute key | Test subject và display name riêng |
| Email luôn null | Claim không nằm trong ID Token/UserInfo fixture | Cấu hình mock OidcUser đúng |
| Test chỉ thấy `ROLE_USER`, không thấy scope | Authorities fixture chưa cấu hình | `.authorities(...)` theo expected mapping |
| `@PreAuthorize` dường như không hoạt động | Method security chưa được bật trong test context | Load security config/proxy hoặc test riêng |
| `@MockitoBean` không nhận diện | Spring Framework/Boot version cũ | Dùng `@MockBean` theo version hoặc nâng dependency phù hợp |
| Full context không startup | Thiếu ClientRegistrationRepository/issuer metadata/test secret | Dùng test profile hoặc MVC slice |
| OIDC test pass nhưng production ID Token bị từ chối | Helper không chạy JWT validation | Viết protocol integration test |
| User Info claim bất ngờ | Mock chỉ có ID Token, thiếu UserInfo | Dựng custom `DefaultOidcUser` |
| CSRF POST trả 403 | Thiếu `.with(csrf())` | Thêm CSRF token cho test request hợp lệ |
| Cross-tenant test không deny | Service bị mock “allow all” | Stub deny và test policy service |
| Async test chưa thấy response | Chưa `asyncDispatch` | Dùng MockMvc async test pattern |
| JWT API principal là `Jwt`, không phải `OidcUser` | Resource Server khác OIDC Login | Dùng `jwt()` helper |
| Response chứa claim/token không mong muốn | Controller serialize principal trực tiếp | Trả DTO tối thiểu |
| Dữ liệu user test leak giữa methods | Shared SecurityContext/global fixtures | Dùng helpers và clear context phù hợp |

### 32.1. Một trình tự điều tra 5 bước

1. **Xem parameter type:** `OidcUser`, `OAuth2User`, `UserDetails`, `Jwt` hay custom type?
2. **Xem Authentication fixture:** `oidcLogin`, `oauth2Login`, `@WithMockUser`, `jwt`, hay `authentication(...)`?
3. **Xem MockMvc security integration:** có filters/`springSecurity()` không?
4. **Xem access policy:** request được authenticated/authorized hay controller thực sự chạy?
5. **Xem claims/service dependencies:** `sub`, `iss`, `email`, authorities và tenant membership có đúng contract không?

Không bắt đầu bằng cách tắt security filters hoặc thay principal parameter thành `Object`.

## 33. Những điều `oidcLogin()` KHÔNG chứng minh

Đây là ranh giới quan trọng trong test quality:

```java
mvc.perform(get("/api/me").with(oidcLogin()))
```

**Có thể kiểm tra:**

- OIDC principal được inject vào MVC controller.
- Controller mapping/DTO serialization.
- Role/authority checks nếu fixture/security config phù hợp.
- `@AuthenticationPrincipal`/SpEL/meta-annotation behavior.
- Domain service được gọi với identity phù hợp.

**Không tự kiểm tra:**

- RP tạo authorization request đúng `redirect_uri`/`state`/PKCE.
- User thực sự được OP xác thực.
- Authorization code được đổi token với đúng Token Endpoint.
- ID Token signature/JWKS/`iss`/`aud`/nonce/expiry.
- UserInfo Endpoint được gọi an toàn.
- Client secret hoặc mTLS/private_key_jwt đúng.
- Refresh token rotation.
- Access token được API chấp nhận đúng audience.
- Browser cookies, proxy, SameSite hoặc SSO logout.
- User có membership/entitlements thật nếu service bị mock.

Với các yêu cầu bảo mật cao, hãy kết hợp:

1. **Controller slice tests** bằng `oidcLogin()`/`oauth2Login()`.
2. **Security config tests** với đúng filter chains/authorities.
3. **OIDC Login integration tests** bằng test OP/JWKS/token fixtures.
4. **Resource Server tests** bằng access token validation thật.
5. **Domain authorization tests** cho ownership, role, tenant policy.
6. **End-to-end tests** cho browser redirect/session khi cần.

Không tự chuyển các test này thành một test đơn khổng lồ chỉ vì muốn “full coverage”. Mỗi lớp kiểm tra một hợp đồng rõ ràng.

## 34. Câu hỏi ôn tập

**1. `@AuthenticationPrincipal` lấy principal từ đâu?**

Từ `Authentication.getPrincipal()` trong SecurityContext của request, qua Spring Security MVC argument resolver.

**2. `@WithMockUser` có tạo `OidcUser` không?**

Thông thường không. Nó tạo một generic UserDetails-based authentication, nên có thể sai kiểu với controller cần `OidcUser`.

**3. Khi nào dùng `oidcLogin()`?**

Khi test Servlet MockMvc controller hoặc authorization behavior cần principal giống OIDC Login.

**4. Khi nào dùng `oauth2Login()`?**

Khi ứng dụng dùng OAuth2 Login không có OIDC hoặc controller cần `OAuth2User`.

**5. `oidcLogin()` có thực hiện authorization code/token exchange không?**

Không. Nó dựng mock authentication cho request test.

**6. Vì sao gọi trực tiếp controller method chưa đủ?**

Không kiểm tra MVC argument resolver, SecurityContext và filter chain.

**7. `OidcUser.getSubject()` khác `getName()` thế nào?**

`getSubject()` diễn đạt rõ OIDC `sub`; `getName()` có thể phụ thuộc name attribute key của principal implementation.

**8. Email có thể dùng làm unique user key cho mọi OIDC providers không?**

Không nên mặc định. Email có thể thiếu/thay đổi; identity thường cần `(issuer, sub)`.

**9. `@AuthenticationPrincipal(expression = "attributes['sub']")` làm gì?**

Dùng SpEL lấy trường `sub` từ attributes của principal.

**10. Khi nào dùng `errorOnInvalidType=true`?**

Khi muốn principal sai Java type gây lỗi rõ ràng thay vì resolver silently inject null.

**11. Vì sao controller nhận `null` dù request được authenticated?**

Vì Authentication có thể chứa principal khác kiểu yêu cầu; `.authenticated()` không kiểm tra tham số Java type của controller.

**12. Test request anonymous luôn trả 401 không?**

Không. Với OAuth2 Login entry point có thể 302 redirect; behavior phụ thuộc security configuration.

**13. Một test chỉ dùng `oidcLogin()` có chứng minh ID Token được ký đúng không?**

Không. Cần integration test decoder/OP phù hợp.

**14. Làm sao custom OidcUser claims trong test?**

Dùng `oidcLogin().idToken(...)`, hoặc dựng `OidcIdToken`/`DefaultOidcUser` rồi `.oidcUser(...)`.

**15. UserInfo claims có luôn nằm trong ID Token không?**

Không. UserInfo có thể cung cấp thêm claims; test fixture cần phản ánh production contract.

**16. Muốn kiểm tra registration ID thì làm thế nào?**

Dùng `OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` hoặc một identity context abstraction phù hợp, không lấy từ `OidcUser.getSubject()`.

**17. Registration ID có chứng minh tenant membership không?**

Không. Cần domain authorization kiểm tra user được phép truy cập tenant.

**18. `@WithSecurityContext` dùng để làm gì?**

Định nghĩa annotation test tùy chỉnh để tạo SecurityContext/Authentication đúng loại.

**19. Meta-annotation `@CurrentOidcUser` có lợi ích gì?**

Giữ controller signature gọn và diễn đạt dependency vào OIDC principal; vẫn dựa trên `@AuthenticationPrincipal` resolver.

**20. `standaloneSetup()` có tự chạy Spring Security filter chain không?**

Không. Cần setup security phù hợp nếu test muốn kiểm tra integration.

**21. Vì sao cần `.apply(springSecurity())` với webAppContextSetup?**

Để tích hợp security filters/test helpers với MockMvc đúng cách.

**22. `@WebMvcTest` và `@SpringBootTest` khác nhau ở đâu?**

Một bên nạp MVC slice nhanh; bên kia nạp application context rộng hơn và các security dependencies gần production hơn.

**23. `@RegisteredOAuth2AuthorizedClient` có lấy principal không?**

Không. Nó resolve authorized client chứa access/refresh tokens, khác với `@AuthenticationPrincipal`.

**24. Một controller nhận `Jwt` principal có nên test bằng `oidcLogin()`?**

Không. Với JWT Resource Server, thường dùng `jwt()`.

**25. Tại sao test JWT postprocessor chưa đủ chứng minh Resource Server audience validation?**

Helper thiết lập authentication mock, không nhất thiết chạy JWT signature/issuer/audience validators thật.

**26. Test POST có cần CSRF token không?**

Khi CSRF được bật theo browser-session security policy, request hợp lệ thường cần `.with(csrf())`.

**27. Tại sao không nên trả nguyên `OidcUser` làm JSON?**

Có thể lộ toàn bộ claims, PII hoặc token-related data. Nên trả DTO tối thiểu.

**28. Nếu test tenant authorization bằng mock service, đã chứng minh policy thật chưa?**

Chưa. Nó chỉ chứng minh controller gọi service đúng; policy service cần test riêng.

**29. Làm sao kiểm tra async controller?**

Dùng MockMvc `asyncStarted()` và `asyncDispatch(result)`; với custom executor cần xem SecurityContext propagation.

**30. Điều gì nên có trong test matrix của `@AuthenticationPrincipal`?**

Đúng/sai kiểu principal, OIDC/OAuth2/JWT fixtures, authenticated/anonymous, missing claims, SpEL/meta annotation, roles/scopes, tenant policy, CSRF, async và response không lộ dữ liệu nhạy cảm.

## 35. Tài liệu tham khảo

- [Spring Security Reference — Testing, Servlet](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring Security Reference — MockMvc OAuth 2.0 Login Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security Reference — MockMvc OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security Reference — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security Reference — WithMockUser](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security Reference — MVC AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html)
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security Reference — OIDC Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security API — AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/annotation/AuthenticationPrincipal.html)
- [Spring Security API — AuthenticationPrincipalArgumentResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/method/annotation/AuthenticationPrincipalArgumentResolver.html)
- [Spring Security API — OidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html)
- [Spring Security API — DefaultOidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html)
- [Spring Security API — OAuth2AuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html)
- [Spring Security API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)

**Ghi nhớ:** `@AuthenticationPrincipal` trong Spring MVC lấy **`Authentication.getPrincipal()`**, nên MockMvc test phải dựng **đúng principal Java type**. Với controller OIDC, ưu tiên **`.with(oidcLogin())`** hoặc custom `OidcUser`; với OAuth2 user không OIDC dùng **`oauth2Login()`**; với JWT Resource Server dùng **`jwt()`**. `@WithMockUser` không tự tạo OIDC principal. Hãy giữ MockMvc tích hợp Spring Security filters, test cả anonymous/type mismatch/claims/authorities/tenant boundaries, và trả DTO tối thiểu. Những fixtures này kiểm thử **controller + argument resolution**, **không thay** integration tests về Authorization Code, ID Token signature/issuer/audience, access token validation hoặc domain authorization.
