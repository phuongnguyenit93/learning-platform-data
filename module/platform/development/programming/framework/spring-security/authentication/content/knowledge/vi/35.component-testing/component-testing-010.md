# Phân biệt principal giả lập với bằng chứng xác thực được kiểm tra thực

> **Module:** Spring Security – authentication. **Nhóm:** Kiểm thử thành phần. Áp dụng cho Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet stack), JUnit 5 và Spring Security Test. Trọng tâm là phân biệt **đặt sẵn một principal/Authentication trong test** với **thực sự xác minh mật khẩu, token, phiên hoặc bằng chứng từ Identity Provider**. Một bài test có trạng thái `authenticated()` không tự chứng minh cơ chế đăng nhập an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `Principal`, `Authentication`, `SecurityContext`, `AuthenticationManager`, `AuthenticationProvider` và cơ chế thực thi authentication ở Spring Security.
2. Biết `@WithMockUser`, `@WithUserDetails`, `user()`, `authentication()`, `jwt()`, `oauth2Login()` và `opaqueToken()` tạo **test fixture** với phạm vi khác nhau.
3. Xác định chính xác **điều được chứng minh** và **điều chưa được chứng minh** khi một test sử dụng principal giả lập.
4. Viết kiểm thử **authorization** với principal giả (nhanh, tập trung) và kiểm thử **authentication thực qua HTTP filter/provider** với `formLogin()` hoặc `httpBasic()`.
5. Giải thích vì sao `@WithUserDetails` có thể truy vấn user store nhưng **không thay cho việc kiểm tra password**, và `jwt()` **không kiểm tra chữ ký JWT**.
6. Biết phân lớp tests để xác minh password encoder, account flags, CSRF, authentication filters, session persistence, JWT signature/issuer/audience/time và phân quyền.
7. Phòng tránh false positive do `addFilters=false`, `standaloneSetup` thiếu security, mock `AuthenticationManager`, role được tự khai, principal giả không tồn tại, token giả với `alg=none`.
8. Viết bài test dạng “negative-first”: yêu cầu bảo vệ phải **từ chối** thiếu/sai bằng chứng trước khi chấp nhận bằng chứng hợp lệ.

## 2. Định nghĩa: principal không phải là bằng chứng xác thực

Trong Java, `java.security.Principal` là abstraction biểu diễn **một danh tính**. Trong Spring Security, `Authentication` vừa biểu diễn thông tin danh tính, authorities và trạng thái xác thực, vừa có thể đóng vai trò yêu cầu xác thực trước khi được provider xử lý.

- **Principal:** đối tượng hoặc định danh “ai”; có thể là username `lan`, `UserDetails`, `Jwt`, `OidcUser`, domain principal.
- **Credentials:** bằng chứng được trình để xác minh, như password, bearer access token, assertion có chữ ký; một số authentication results xóa credentials sau khi thành công.
- **Authorities:** quyền/scope mà nguồn tin cậy đã xác nhận tại thời điểm xác thực, ví dụ `ROLE_USER` hoặc `SCOPE_reports.read`.
- **Authentication.isAuthenticated():** trạng thái trên đối tượng Authentication, **không phải phép chứng minh độc lập rằng một mật khẩu/JWT đã từng được kiểm tra**.
- **SecurityContextHolder:** nơi truy cập context gắn với execution/thread trong Servlet (chi tiết quản lý tùy strategy). Việc test tự đặt context không có nghĩa có người đã login thật.

Một request production dùng form password thường trải qua:

```text
Browser POST /login (username + password)
        │
        ▼
UsernamePasswordAuthenticationFilter
        │ Authentication object chưa verified
        ▼
AuthenticationManager / ProviderManager
        │
        └── DaoAuthenticationProvider
              ├─ UserDetailsService.loadUserByUsername()
              ├─ PasswordEncoder.matches(raw, storedHash)
              ├─ account locked/disabled/expired checks
              └─ success → Authentication được xác minh
        │
        ▼
SecurityContext + session strategy/handlers
        │
        ▼
AuthorizationFilter / @PreAuthorize / business policy
        │
        ▼
Endpoint được phép hoặc bị từ chối
```

Trong khi đó `@WithMockUser` hoặc `user("lan")` có thể **đặt sẵn một `UsernamePasswordAuthenticationToken` đã authenticated** vào test request/context:

```text
JUnit test method
        │
        │ @WithMockUser(username="lan",roles="USER")
        ▼
Spring Security Test tạo Authentication giả lập
        │
        ▼
SecurityContext chứa principal + ROLE_USER
        │
        ▼
AuthorizationFilter / protected method
        │
        ▼
Kết quả có thể là 200 / 403
        │
        └─ KHÔNG có bước nhập password,
           KHÔNG có PasswordEncoder.matches(),
           KHÔNG chứng minh account tồn tại.
```

**Điểm then chốt:** hai luồng có thể dẫn đến **cùng tên principal và cùng authorities**, nhưng **đường đi bằng chứng** hoàn toàn khác. Test giả lập có thể rất đúng để kiểm thử **authorization cho một principal đã được giả định là xác thực**, nhưng **không thể kết luận password/JWT verifier hoạt động** từ kết quả đó.

## 3. Bảng phân biệt từng loại test fixture

| Cách thiết lập | Bằng chứng thực sự được kiểm tra trong test? | Điều test mạnh nhất | Điều không thể kết luận |
|---|---|---|---|
| `@WithMockUser(username="lan", roles="USER")` | Không; test tạo principal không cần user tồn tại | Method/request authorization với user/role cho trước | Password đúng, user có trong DB, MFA đã pass |
| `@WithAnonymousUser` | Không; mô phỏng anonymous | Endpoint phải từ chối/cho phép anonymous đúng policy | Có authentication flow thật đã chạy |
| `mvc.perform(get(...).with(user("lan")))` | Không; inject user trong request | Access rules/handlers khi đã có Authentication | Password được kiểm tra |
| `mvc.perform(...with(authentication(auth)))` | Không, nếu `auth` được dựng sẵn | Quy tắc dựa trên Authentication shape/authorities | Authentication object đến từ verifier thật |
| `@WithUserDetails("lan")` | **Có loadUserByUsername**, không kiểm tra password | Principal type, mapping UserDetails và method authorization | PasswordEncoder.matches và login filter thành công |
| `.with(jwt())` | **Không** kiểm chữ ký/issuer/audience/exp như request token thật | Resource authorization theo `JwtAuthenticationToken`/scope giả | JWT thực được issuer ký và decoder chấp nhận |
| `.with(oauth2Login())` / `.with(oidcLogin())` | Không chạy OAuth/OIDC redirects và token exchange thật | Authorization dựa vào principal/claims OIDC giả | Code/state/nonce/issuer/token signature thực đúng |
| `.with(opaqueToken())` | Không bắt buộc gọi introspection server | Quyền theo introspected-principal giả | Token opaque có thật và introspection policy đúng |
| `.with(httpBasic("lan","password"))` | **Có thể**, khi real SecurityFilterChain/manager/provider đang hoạt động | Password auth qua Basic filter, mapping flags, response | Đúng nếu provider/encoder đã bị mock hoặc filter bị tắt |
| `mvc.perform(formLogin().user(...).password(...))` | **Có thể**, khi real login filter/provider chạy | POST form login, CSRF, password provider, success/failure | Không chứng minh token/session/SAML/OIDC flows khác |
| Real signed JWT trong header `Authorization: Bearer ...` | Có khi Resource Server dùng real `JwtDecoder`/validators | Chữ ký, claim/time/issuer/audience theo cấu hình | Không chứng minh authorization nếu chỉ assert status thiếu scope |
| End-to-end browser + real IdP | Kiểm tra tích hợp gần thực nhất trong phạm vi môi trường | Redirect, login, cookies/session, external assertions | Không bảo đảm mọi trường hợp phishing/operations đều đã được kiểm tra |

**Chú thích quan trọng:** `@WithUserDetails` có truy xuất `UserDetailsService`; test đó **có thể chứng minh** rằng user đã được lookup và chuyển thành principal đúng kiểu, **không chứng minh** password user nhập đã được `matches`. Còn `formLogin()` và `httpBasic()` chỉ chứng minh đường xác thực thật nếu **không bị thay AuthenticationManager/provider, UserDetailsService hoặc password encoder bằng mock luôn thành công**.

## 4. Khi nào nên giả lập principal?

Giả lập là lựa chọn đúng nếu **mục tiêu trực tiếp của bài test không phải xác minh mật khẩu/token**. Ví dụ:

- Một `@PreAuthorize("hasRole('AUDITOR')")` có từ chối `ROLE_USER` không?
- Controller có lấy đúng `authentication.getName()` để tìm dữ liệu theo owner không?
- Dữ liệu tenant A có bị lộ cho người thuộc tenant B dù cùng `ROLE_USER` không?
- Method service có từ chối user không có permission khi được gọi ngoài HTTP không?
- DTO có loại bỏ fields riêng tư theo role/owner không?
- CORS/CSRF hoặc headers áp dụng cho request đã có một Authentication xác định?

Trong các test đó, inject principal giúp **cô lập authorization và business logic**, giảm I/O/crypto, test nhanh và dễ tái hiện. Tuy nhiên phải **đặt tên và phạm vi đúng**:

**Tên đúng:**

```text
shouldAllowAuditorToReadReportWhenAlreadyAuthenticated()
shouldRejectViewerFromTenantB()
shouldRejectAnonymousRequestToPrivateEndpoint()
```

**Tên gây hiểu lầm:**

```text
passwordLoginWorks()  // nhưng bên trong chỉ @WithMockUser
jwtSignatureVerified() // nhưng bên trong chỉ .with(jwt())
userWasAuthenticatedByIdp() // nhưng chỉ .with(oidcLogin())
```

Rule hữu ích: **Nếu bỏ toàn bộ mật khẩu/JWT/IdP khỏi test mà test vẫn pass, test đó có thể chỉ chứng minh authorization dựa trên một principal đã được cấp sẵn.**

### 4.1. @WithMockUser hoạt động ra sao?

`@WithMockUser` thuộc module `spring-security-test` và được `WithSecurityContextTestExecutionListener` dùng để thiết lập `SecurityContext` trước khi test chạy. Các default thông dụng:

- username: `user`;
- password trong fixture: `password`;
- role: `USER`, tạo authority `ROLE_USER`;
- principal: Spring Security `User`;
- Authentication: `UsernamePasswordAuthenticationToken` với trạng thái authenticated.

Không cần database có record `user`; password `password` trong annotation **không được đem đi so với password hash**. Các role strings trong `roles` được thêm prefix `ROLE_`; `authorities` giữ nguyên chuỗi. Không dùng `roles={"ROLE_ADMIN"}` rồi nhận prefix thành `ROLE_ROLE_ADMIN`. Dùng `roles={"ADMIN"}` hoặc `authorities={"ROLE_ADMIN"}` tương ứng.

Ví dụ:

```java
@Test
@WithMockUser(username = "lan", roles = "AUDITOR")
void auditorMayReadReport() {
    // Service phải là bean được Spring AOP/proxy bảo vệ.
    assertThat(reportService.readSummary()).isNotBlank();
}
```

Kết quả pass nói rằng **quy tắc cho `ROLE_AUDITOR` trong context giả lập** đã hoạt động (nếu method security được bật). Nó không chứng minh user `lan` có role đó ở database hay password login thành công. Phải kiểm thử **role issuance** riêng từ trusted user store/IdP.

### 4.2. @WithUserDetails có thực hơn @WithMockUser không?

`@WithUserDetails("lan")` gọi `UserDetailsService` của test context để lấy một `UserDetails` thật theo cấu hình test, rồi dùng nó làm principal cho Authentication giả lập. Vì thế:

- Có thể kiểm tra user tồn tại theo repository mà test đang kết nối.
- Có thể kiểm tra kiểu principal tùy biến (ví dụ `CustomUserDetails` giữ stable account ID).
- Có thể kiểm tra mapping `getAuthorities()` từ DB/app configuration.
- **Không** tự thực hiện `DaoAuthenticationProvider.authenticate(UsernamePasswordAuthenticationToken)`.
- **Không** gọi `PasswordEncoder.matches(raw, storedHash)` chỉ vì `@WithUserDetails`.
- Không có POST login, không có failure handler/session fixation/CSRF login flow.

Nếu `UserDetailsService` trong test là một mock trả về UserDetails cố định, ngay cả việc “user tồn tại trong DB” cũng **chưa** được chứng minh. Phải nói rõ bean/service thật hay mock.

Ví dụ:

```java
@Test
@WithUserDetails(value = "lan")
void principalTypeFromStoreIsUsed() {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    assertThat(auth.getPrincipal()).isInstanceOf(UserDetails.class);
    assertThat(auth.getName()).isEqualTo("lan");
}
```

Đây là **snippet** trong một Spring Test class có `UserDetailsService` bean và static AssertJ imports; không phải standalone. Chỉ test **lookup + context setup**.

### 4.3. @WithSecurityContext cho custom principal

`@WithSecurityContext` có thể tạo một fixture Authentication đặc thù: đa tenant, authorities, MFA claims, scopes hoặc custom principal. Cách này hữu ích khi app cần principal shape phức tạp nhưng vẫn là **giả lập**. Nếu factory tự set `authenticated=true`, đó là quyết định của **test**, không phải bằng chứng MFA/session thật.

Điều cần bảo vệ ở production: **không được cho client cung cấp `Authentication`/`roles`/`isAuthenticated` bằng JSON/header và được server tin ngay**, vì test fixture dễ tạo principal là đặc quyền của môi trường kiểm thử.

## 5. Thực sự kiểm tra credential khác giả principal ở bước nào?

Với username/password, đường production tối thiểu cần:

1. Request gửi username/password tới filter được cấu hình: `POST /login` hoặc HTTP Basic.
2. Filter tạo một `Authentication` **chưa authenticated** với credential raw cần kiểm tra.
3. `AuthenticationManager` gọi provider phù hợp, ví dụ `DaoAuthenticationProvider`.
4. Provider dùng `UserDetailsService` tải user, kiểm tra account status (enabled/locked/expired), so credential bằng `PasswordEncoder.matches`.
5. Nếu sai, trả failure/challenge mà không tạo session có quyền.
6. Nếu đúng, tạo kết quả Authentication đã xác thực và áp dụng session/context strategy.
7. Authorization kiểm tra authorities/role/ownership của principal đã xác minh.
8. Với MFA, password đúng **chưa đủ** nếu tài nguyên yêu cầu yếu tố bổ sung; test phải chạy flow thứ hai.

**Với JWT bearer:**

```text
HTTP Authorization: Bearer eyJ...
        ↓
BearerTokenAuthenticationFilter
        ↓
JwtAuthenticationProvider / JwtDecoder
        ├─ kiểm tra chữ ký và thuật toán được phép
        ├─ xác minh issuer, audience, exp, nbf theo policy
        ├─ xác minh key/kid, trust metadata
        └─ map claims/scopes thành authorities
        ↓
Authentication xác minh thành công
        ↓
Authorization tiếp tục
```

**Với `.with(jwt())`:** Spring Security Test **cài sẵn `JwtAuthenticationToken`**, thông thường không phát một HTTP bearer token để decoder kiểm tra chữ ký. Giá trị `alg=none` hay `sub=user` trong fixture không chứng minh ứng dụng chấp nhận `alg=none` trên đường production; ngược lại, nó **không chứng minh ứng dụng từ chối alg=none**. Cần test decoder/HTTP header thật cho các kết luận đó.

## 6. Thiết kế hệ thống test theo những câu hỏi khác nhau

| Tầng kiểm thử | Đầu vào | Đối tượng thật cần chạy | Câu hỏi test trả lời |
|---|---|---|---|
| Domain unit test | Identity/roles giả định + resource metadata | Domain policy, không cần Spring | “User này có quyền đọc tài liệu này không?” |
| Method security test | `@WithMockUser`/`@WithUserDetails` | `@PreAuthorize` proxy/interceptors | “Security rule trên method có chặn đúng quyền không?” |
| MVC authorization slice | MockMvc `user()`/`jwt()` | Controller + SecurityFilterChain + authorization | “Endpoint map authority sang response đúng không?” |
| Authentication component test | HTTP Basic/form login request | Real authentication filter + AuthenticationManager + PasswordEncoder/UserDetailsService theo cấu hình | “Password đúng/sai/disabled được xử lý thế nào?” |
| JWT decoder/security test | JWT ký thật (test key) trong Authorization header | Bearer filter + real JwtDecoder/validators | “JWT sai chữ ký, sai iss/aud/exp có bị từ chối không?” |
| OIDC/SSO integration | Authorization code/state/nonce, IdP test | OAuth2 login client, callback/token verification | “Callback thực và user linking có an toàn không?” |
| E2E browser | Real browser, cookies, CSRF, login and logout | App/proxy/IdP/db ở môi trường test | “Cả hành trình người dùng có vận hành an toàn không?” |

Các tầng **bổ sung** nhau, không có tầng nào tự thay mọi tầng khác. Dùng quá nhiều E2E để kiểm tra một điều kiện `hasRole` gây chậm và flaky; dùng toàn `@WithMockUser` mà không có một test password/JWT thật gây **ngộ nhận bảo mật**.

### 6.1. Hai chiều coverage nên đo riêng

**Coverage của authorization**: ai được phép làm gì, có chặn user khác/tenant khác, kiểm tra role/scope/ownership, method-level protection, object-level authorization.

**Coverage của authentication**: credential được cấp từ đâu, verifier thực sự kiểm tra hay bị mock, loại token đúng mục đích, password hash/status, JWT signature/audience/issuer/time, refresh/MFA/session, failure paths.

Một file test có 100 ca `@WithMockUser` có thể rất tốt cho authorization nhưng gần **0 coverage cho credential verifier**. Test report nên mô tả hai chiều để không gây hiểu nhầm.

## 7. Spring Boot 3 + Spring Security 6: một ứng dụng nhỏ để so sánh

Ví dụ này tạo ứng dụng **form login + HTTP Basic**, tài khoản nội bộ `lan` có role `READER`. Mục đích là chạy hai bộ test **trên cùng endpoint**: một bộ chèn principal giả, một bộ gửi credential đi qua filter/provider. Các class có thể biên dịch/chạy trong project Spring Boot 3.x có JDK 17+, Gradle/BOM đúng và dependencies bên dưới.

### 7.1. Gradle dependencies

`build.gradle` (phần `dependencies`; plugin Spring Boot và repositories được khai trong project):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không cần database cho ví dụ; `InMemoryUserDetailsManager` là user store **thật trong bộ test**, chứ không phải database production. Điều cần chứng minh là provider sử dụng hash và kiểm tra mật khẩu. Production nên có persistence và cơ chế quản lý account/sessions đúng policy.

### 7.2. Main Spring Boot app

File `src/main/java/example/learning/auth/SecurityTestApplication.java`:

```java
package example.learning.auth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTestApplication.class, args);
    }
}
```

### 7.3. SecurityConfig — giữ provider thật, hash thật

File `src/main/java/example/learning/auth/ExampleSecurityConfig.java`:

```java
package example.learning.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ExampleSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
            .password(encoder.encode("correct-password-123"))
            .roles("READER")
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(encoder.encode("disabled-password-123"))
            .roles("READER")
            .disabled(true)
            .build();

        return new InMemoryUserDetailsManager(lan, disabled);
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers("/reports/**").hasRole("READER")
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

**Lý do cấu hình này phù hợp bài học:**

- `PasswordEncoder` là một bean thật, không phải Mockito mock luôn trả `true`.
- `UserDetailsService` trả hai user thật từ in-memory store. Account `disabled` dùng đúng mật khẩu nhưng login vẫn phải bị từ chối.
- `DaoAuthenticationProvider` được tích hợp qua cấu hình có user store và encoder phù hợp; thông qua Basic/Form, password thực sự đi qua verifier.
- `/reports/**` đòi `ROLE_READER`; user không có role này bị 403 hoặc yêu cầu auth tùy trạng thái.
- Cả Basic và Form được bật để so hai kiểu request. Việc chọn entrypoint/status phụ thuộc Accept/content-negotiation; trong test Basic có thể gửi `Accept: application/json` để tránh UX HTML.
- Cấu hình này là **mẫu học tập**, không phải khuyến nghị mặc định bật Basic cho mọi frontend production. Không đưa password ví dụ vào source thật hoặc dùng InMemory store trong hệ thống nhiều người dùng.

### 7.4. Endpoint chỉ phản ánh danh tính được giao

File `src/main/java/example/learning/auth/ReportController.java`:

```java
package example.learning.auth;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    @GetMapping("/reports/me")
    public String whoAmI(Authentication authentication) {
        return authentication.getName();
    }
}
```

Endpoint này **không kiểm chứng password**. Nó chỉ đọc `Authentication` mà security filters/context đã cung cấp. Vì vậy, nếu test chèn Authentication giả, controller có thể trả `ghost` dù trong user store không có `ghost`. Đó là **tính năng của test fixture**, không chứng minh production login cho ghost.

### 7.5. Bộ MockMvc tests — đối chiếu mock và credential thực

File `src/test/java/example/learning/auth/AuthBoundaryTests.java`:

```java
package example.learning.auth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class AuthBoundaryTests {

    @Autowired MockMvc mvc;

    @Test
    void mockedPrincipalCanAccessWithoutAnAccountRecord()
            throws Exception {
        mvc.perform(get("/reports/me")
                .with(user("ghost").roles("READER")))
            .andExpect(status().isOk())
            .andExpect(content().string("ghost"));
    }

    @Test
    void actualHttpBasicRejectsUnknownAccount()
            throws Exception {
        mvc.perform(get("/reports/me")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("ghost", "whatever")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void actualHttpBasicRejectsWrongPassword()
            throws Exception {
        mvc.perform(get("/reports/me")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("lan", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void actualHttpBasicAcceptsCorrectPassword()
            throws Exception {
        mvc.perform(get("/reports/me")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("lan", "correct-password-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("lan"));
    }

    @Test
    void actualHttpBasicRejectsDisabledAccount()
            throws Exception {
        mvc.perform(get("/reports/me")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("disabled", "disabled-password-123")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void simulatedRoleWithoutPermissionGetsForbidden()
            throws Exception {
        mvc.perform(get("/reports/me")
                .with(user("ghost").roles("VIEWER")))
            .andExpect(status().isForbidden());
    }
}
```

**Sửa imports khi chép vào Java file:** Trong Markdown, hai `import static` đầu tiên ở trên bị xuống dòng giữa tên package và tên class cho dễ đọc. Java **cho phép whitespace sau dấu chấm**, nhưng để bảo đảm cú pháp rõ ràng trong IDE, dùng nguyên một dòng cho mỗi import:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

Bộ test có thể chạy bằng:

```bash
./gradlew test --tests example.learning.auth.AuthBoundaryTests
```

Trên Windows, có thể dùng `gradlew.bat test --tests example.learning.auth.AuthBoundaryTests`. Không chép số lượng tests/output CI cố định làm “stdout” nếu chưa thực sự chạy môi trường của bạn.

**Giải thích kết quả mong đợi:**

1. `ghost + user("ghost").roles("READER")` được cho vào **test SecurityContext**, nên `/reports/me` trả `ghost`: **authorization với principal giả đã pass**.
2. `ghost + httpBasic("ghost","whatever")` phải thất bại vì `UserDetailsService` không có `ghost`: **provider thật đã tham gia**.
3. `lan` gửi password sai phải 401: **PasswordEncoder.matches` không chấp nhận.
4. `lan` gửi đúng password có thể đọc `/reports/me` và nhận `lan`.
5. `disabled` có password đúng nhưng vẫn bị chặn do account flags.
6. `ghost` được gán giả `ROLE_VIEWER` không đủ `ROLE_READER` nên bị 403 (vẫn chỉ là authorization test).

Không rút kết luận sai rằng “test ghost qua được thì có lỗ hổng login”: `user()` chỉ có hiệu lực **bên trong MockMvc test**, không phải request HTTP gửi bởi attacker ở production. Ngược lại, nếu dùng fixture giả để kiểm thử login, bài test sẽ không phát hiện các lỗi password provider.

## 8. @WithMockUser và @WithUserDetails trong method security

Với method security, `@EnableMethodSecurity` phải được bật và method bảo vệ cần được gọi **qua Spring-managed proxy**. Nếu tự tạo service bằng `new` hoặc tự gọi annotated method trong cùng class (self-invocation), test có thể đi vòng method security.

Ví dụ service:

```java
package example.learning.auth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasRole('READER')")
    public String summary() {
        return "report-visible";
    }
}
```

Cần bật method security:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
```

Imports tương ứng: `org.springframework.context.annotation.Configuration` và `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`. Đây là snippet tích hợp vào app.

Tests:

```java
@Test
@WithMockUser(username = "ghost", roles = "READER")
void mockedReaderCanCallProtectedService() {
    assertThat(reportService.summary()).isEqualTo("report-visible");
}

@Test
@WithUserDetails("lan")
void realUserDetailsCanBeLoadedWithoutPasswordCheck() {
    assertThat(reportService.summary()).isEqualTo("report-visible");
}
```

Đây là snippets dùng cùng test context có `ReportService` bean, `UserDetailsService` và imports của Spring Security Test, JUnit5, AssertJ. `@WithMockUser` không yêu cầu `ghost` tồn tại. `@WithUserDetails` yêu cầu `lan` được `UserDetailsService` load; **chưa có bước nhập password**. Cả hai phù hợp để test method authorization. Muốn test password, chạy request qua `formLogin()`/`httpBasic()` hoặc trực tiếp `AuthenticationManager.authenticate(...)` với provider/encoder thật.

### 8.1. Nếu không bật method security?

Một test có `@WithMockUser(roles="USER")`, gọi `service.sensitiveOperation()` và thấy thành công có thể chỉ vì `@PreAuthorize` không được intercept. Test phải có cả **positive** và **negative**:

- Authorized role được phép.
- Missing role phải bị `AccessDeniedException`/`AuthorizationDeniedException` hoặc response 403 qua HTTP đúng.
- Không context phải bị từ chối.
- Ownership/tenant khác phải bị chặn dù role trùng nhau.

Positive-only dễ tạo false sense of security: một method không có security cũng “pass” khi user admin gọi vào.

## 9. RequestPostProcessor jwt(): nguy hiểm của diễn giải sai

Spring Security Test cung cấp `SecurityMockMvcRequestPostProcessors.jwt()` giúp tạo `JwtAuthenticationToken` mà không phải làm JWT thật. Ví dụ snippet trong MockMvc test có Resource Server route `GET /api/reports` đòi `SCOPE_reports.read`:

```java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

Nếu application endpoint/controller thực sự hiện diện và authorization đúng, test này chứng minh **giả định đã có JwtAuthenticationToken với SCOPE_reports.read thì rule cho phép**. Nhưng:

- Không chứng minh JWT có chữ ký hợp lệ hoặc không chấp nhận `alg=none`.
- Không chứng minh issuer/audience đã được cấu hình và validator hoạt động.
- Không chứng minh token chưa hết hạn hoặc chưa bị thu hồi.
- Không chứng minh scope claim thật được map đúng, nếu test gán authorities trực tiếp.
- Không chứng minh giao thức Authorization header hoặc Bearer failure handler được kiểm thử.
- Không chứng minh ID Token, access token, refresh token và reset token được phân biệt.

Một test có thể pass dù project **không hề khai cấu hình `issuer-uri`**, nếu đã mock sẵn JwtAuthenticationToken. Đây là **giới hạn phương pháp test**, không phải kết luận Resource Server mặc nhiên không an toàn.

### 9.1. jwt().jwt(...).claim(...) khác jwt().authorities(...)

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(builder -> builder
            .claim("sub", "lan")
            .claim("scope", "reports.read"))))
    .andExpect(status().isOk());
```

Đoạn này tạo mock `Jwt` với claims rồi đưa qua converter của test support nếu không tùy authorities; vẫn **không kiểm chữ ký**. Nếu app có custom `JwtAuthenticationConverter` / user mapping, cần test converter bằng một `Jwt` giả riêng và kiểm thử integration có signed token thật để bảo đảm claim-to-authority mapping đúng ở production.

### 9.2. Test JWT thật qua HTTP Authorization header

Một integration test thực sự kiểm tra JWT nên:

1. Khởi động Spring Boot Resource Server dùng **real `JwtDecoder`** và bộ validators production-equivalent.
2. Tạo một RSA/EC test key pair và JWKS/issuer fixture tin cậy chỉ phục vụ test, hoặc chạy test Authorization Server.
3. Tạo access token **ký thật** bằng test private key; cấu hình decoder tin public key đúng issuer.
4. Gửi raw string bằng `Authorization: Bearer <signed-token>`, **không dùng `.with(jwt())`**.
5. Assert token valid được nhận, wrong signature/algorithm/kid bị từ chối.
6. Assert issuer/audience/expiry/nbf sai bị từ chối; token thiếu scope bị 403 sau khi xác thực.
7. Kiểm tra `WWW-Authenticate` và HTTP status, không chỉ body của controller.
8. Nếu app cần revocation/introspection hoặc session version, test tương tác thật với verifier/shared store đó.

Ví dụ điểm gửi request trong test (snippet; `signedToken` do fixture cấp, không hardcode token thật):

```java
mvc.perform(get("/api/reports")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + signedToken))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + tamperedToken))
    .andExpect(status().isUnauthorized());
```

Đoạn cần static import `get`, `status` và `org.springframework.http.HttpHeaders` cùng các biến của test fixture. **Đừng giả định “đã pass với `JwtDecoder` mock” là chữ ký đã được xác minh.** Mockito mock decoder giúp tập trung vào token wiring/filter error handling, nhưng không test crypto.

### 9.3. Test JwtDecoder độc lập cũng hữu ích

Bạn có thể unit/integration-test `JwtDecoder.decode(String token)` thật với test keys. Khi decode invalid, phải có lỗi `JwtException`/`JwtValidationException` phù hợp và không tạo Authentication; khi decode valid, check claim values, mapping validator. Tuy nhiên chỉ kiểm decoder **chưa** chứng minh `BearerTokenAuthenticationFilter`, security chain matcher, request header extraction và authorization path được cấu hình đúng. Cần ít nhất một HTTP integration test đầy đủ.

## 10. Test đăng nhập thật bằng formLogin() và httpBasic()

### 10.1. Form login request post processor

`formLogin()` tạo một POST tới `/login` có username/password và CSRF hợp lệ theo Spring Security Test:

```java
mvc.perform(formLogin()
        .user("lan")
        .password("correct-password-123"))
    .andExpect(authenticated().withUsername("lan"));

mvc.perform(formLogin()
        .user("lan")
        .password("wrong"))
    .andExpect(unauthenticated());
```

Static imports cho assertions:

```java
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
```

Đây là các snippets trong MockMvc test đã có Spring Security filter chain và `UsernamePasswordAuthenticationFilter`/provider thật. Form login có thể redirect sau thành công hoặc thất bại; test có thể assert `redirectedUrl`/flash/session theo config của app. Nếu đổi URL/field names, `formLogin("/auth").user("u","lan").password("p","...")` phải khớp login processing configuration.

**Không quên CSRF:** Nếu tự viết `post("/login").param(...)` trong test, cần `.with(csrf())` cho app session-based có CSRF bật. Một test bỏ CSRF có thể nhận 403 trước khi password provider chạy; việc chỉ thấy “login failed” không chứng minh password sai bị từ chối.

### 10.2. HTTP Basic request post processor

`httpBasic("lan", "...")` tạo header Basic đúng dạng; nó **không** tự chèn một Authentication đã được xác thực:

```java
mvc.perform(get("/reports/me")
        .accept(MediaType.APPLICATION_JSON)
        .with(httpBasic("lan", "wrong")))
    .andExpect(status().isUnauthorized());

mvc.perform(get("/reports/me")
        .accept(MediaType.APPLICATION_JSON)
        .with(httpBasic("lan", "correct-password-123")))
    .andExpect(status().isOk());
```

Ở app mục 7, test Basic đi qua filter/manager/encoder thật. Nếu bạn đã mock `AuthenticationManager.authenticate(...)` để trả principal bất kể password, **đường HTTP được gửi là thật nhưng phần xác minh credential là giả**. Chất lượng test phụ thuộc toàn bộ dependency chain, không chỉ `httpBasic()`.

### 10.3. Test direct AuthenticationManager: hữu ích nhưng chưa đủ cho HTTP

Một component test có thể gọi trực tiếp `AuthenticationManager.authenticate(...)` với `UsernamePasswordAuthenticationToken.unauthenticated(username,password)` và assert success/`BadCredentialsException`. Điều đó kiểm tra provider và encoder, nhưng không kiểm filter URL, CSRF, session fixation, failure handler, redirect/cookie, hay security chain matcher. Vì vậy cần phối hợp với MockMvc HTTP test.

## 11. Bài học Java 17 độc lập: khác nhau giữa role giả và password thật

Chương trình này **biên dịch/chạy với JDK 17+** và không cần thư viện ngoài. Nó dùng PBKDF2 từ JDK làm **minh họa đơn giản về kiểm chứng secret**; không thay `PasswordEncoder` của Spring Security, không phải template production. Output đều là boolean nên tái lập chính xác dù salt được tạo ngẫu nhiên.

Lưu file `PrincipalEvidenceBoundaryDemo.java`:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Map;
import java.util.Set;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PrincipalEvidenceBoundaryDemo {

    record Account(
        String username, byte[] salt, byte[] passwordHash,
        Set<String> trustedRoles) {}

    record Principal(String username, Set<String> roles) {}

    // Chỉ minh họa verifier; production dùng PasswordEncoder
    // với thuật toán và cấu hình được tổ chức quản lý.
    static byte[] hash(char[] password, byte[] salt) {
        PBEKeySpec spec =
            new PBEKeySpec(password, salt, 120_000, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                .generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(ex);
        } finally {
            spec.clearPassword();
        }
    }

    static Principal authenticate(
            String username, char[] suppliedPassword,
            Map<String, Account> accounts) {

        Account account = accounts.get(username);
        if (account == null) {
            return null;
        }
        byte[] suppliedHash =
            hash(suppliedPassword, account.salt());

        if (!MessageDigest.isEqual(
                account.passwordHash(), suppliedHash)) {
            return null;
        }
        return new Principal(
            account.username(), account.trustedRoles());
    }

    static boolean mayRead(Principal principal) {
        return principal != null
            && principal.roles().contains("READER");
    }

    public static void main(String[] args) {
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);

        Account lan = new Account(
            "lan",
            salt,
            hash("correct-password".toCharArray(), salt),
            Set.of("READER")
        );
        Map<String, Account> accounts = Map.of("lan", lan);

        Principal injected =
            new Principal("ghost", Set.of("READER"));

        System.out.println("Mock ghost may read: " +
            mayRead(injected));
        System.out.println("Ghost real login: " +
            (authenticate("ghost",
                "anything".toCharArray(), accounts) != null));
        System.out.println("Wrong password: " +
            (authenticate("lan",
                "wrong".toCharArray(), accounts) != null));

        Principal verified = authenticate(
            "lan", "correct-password".toCharArray(), accounts);
        System.out.println("Verified login: " +
            (verified != null));
        System.out.println("Verified read: " +
            mayRead(verified));
        System.out.println("Injected login proof: " +
            (authenticate(injected.username(),
                "anything".toCharArray(), accounts) != null));
    }
}
```

Lệnh:

```bash
javac PrincipalEvidenceBoundaryDemo.java
java PrincipalEvidenceBoundaryDemo
```

Stdout chính xác:

```text
Mock ghost may read: true
Ghost real login: false
Wrong password: false
Verified login: true
Verified read: true
Injected login proof: false
```

**Phân tích:**

- `Mock ghost may read: true`: hàm authorization nhận một `Principal` được giả định có `READER`. Vì nó không biết lịch sử chứng minh danh tính, nó cho phép. Đó là mô hình của authorization test với principal đã được injected.
- `Ghost real login: false`: `authenticate` đòi có account trong store, không thể xác minh `ghost` dù principal giả dễ tạo.
- `Wrong password: false`: verifier thực sự tính PBKDF2 với salt account và so kết quả.
- `Verified login: true`: chỉ khi secret đúng mới tạo Principal từ **roles trusted ở account**.
- `Verified read: true`: sau khi xác minh credential, authorization cho phép.
- `Injected login proof: false`: principal giả không thể được nộp làm bằng chứng cho verifier.

**Bảo đảm và giới hạn:** demo không cung cấp login web/HTTP session/JWT/MFA/CSRF, account flags, brute-force protection hay password hash migration. Cost `120_000` chỉ để demo chạy được, **không phải khuyến nghị cấu hình PBKDF2 production**; dùng `PasswordEncoder`, algorithm/cost theo policy, salt ngẫu nhiên, kiểm soát giới hạn request. Trong test chạy JDK, việc test code tự tạo Principal không gây lỗ hổng production trừ khi app có endpoint **tin principal/roles từ client**.

## 12. Dấu hiệu test đang chứng minh nhầm thứ

### 12.1. Một test dùng @WithMockUser nhưng tên là passwordLoginWorks

```java
@Test
@WithMockUser(username="lan", roles="USER")
void passwordLoginWorks() {
    // Test trực tiếp service đã có principal.
}
```

**Vấn đề:** Không request POST login, không raw password, không `PasswordEncoder.matches`. Tên test không phản ánh phạm vi. Nên đổi thành `authenticatedUserCanAccessService` và viết test form login riêng.

### 12.2. .with(jwt()) rồi tuyên bố token alg=none bị chặn

```java
mvc.perform(get("/api/resource").with(jwt()))
    .andExpect(status().isOk());
```

**Vấn đề:** `jwt()` dựng token giả để test authorization. Test này không chạy decoder chữ ký JWT. Để kiểm `alg=none`, phải gửi JWT raw malformed/unsigned qua Authorization header và real `JwtDecoder`; kỳ vọng 401. Cần test issuer/audience/time nữa.

### 12.3. Disabled account được giả thành ACTIVE

```java
mvc.perform(get("/reports/me")
        .with(user("disabled").roles("READER")))
    .andExpect(status().isOk());
```

Bài test có thể pass dù user store đánh dấu account disabled. Vì `user()` bỏ qua provider account status, không dùng bài đó chứng minh “user bị khóa không login được”. Dùng `httpBasic()` hoặc `formLogin()` với provider thật để kiểm đúng chính sách disabled/locked.

### 12.4. MockMvc không chạy security filters

```java
@AutoConfigureMockMvc(addFilters = false)
```

Cấu hình trên cố ý **không thêm filters** vào MockMvc; nếu test trả 200 cho protected URL thì **không chứng minh Spring Security cho phép đúng**. Nó có thể hữu ích để unit-test controller nhưng phải đặt tên rõ và có các security integration tests riêng.

Tương tự, `MockMvcBuilders.standaloneSetup(controller)` mà không `.apply(springSecurity())`/FilterChainProxy thích hợp có thể bỏ qua security filters. `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity())` hoặc `@AutoConfigureMockMvc(addFilters=true)` phù hợp khi muốn thực thi request-level security. Không đánh đồng `@WebMvcTest` và full application: slice có thể mock nhiều beans, vì vậy cần nhìn thực tế filter/provider nào được dựng.

### 12.5. @MockBean AuthenticationManager trả success vô điều kiện

Nếu Mockito setup để `when(authenticationManager.authenticate(any())).thenReturn(verifiedAuthentication)`, HTTP POST có thể trả success mà không hề kiểm password. Đó là test filter wiring với **verifier bị thay**. Cần một test riêng không mock AuthenticationManager/provider/encoder cho giả thuyết “wrong password rejected”.

Đồng thời, `@MockitoBean`/`@MockBean` là công cụ test; nếu làm mock `JwtDecoder` trả Jwt cho mọi token, không thể từ đó kết luận ứng dụng xác minh signature thật.

### 12.6. Test chỉ happy path

```text
Admin role → HTTP 200
```

Chưa đủ. Một endpoint **bỏ hoàn toàn SecurityFilterChain** cũng có thể trả 200. Cần negative tests:

```text
anonymous → 401/302 (theo cơ chế)
wrong password → 401/redirect failure
disabled account → failed authentication
valid account but missing role → 403
cross-tenant same role → 403/404 theo policy
tampered JWT → 401
expired JWT → 401
wrong issuer/audience → 401
correct role + correct token → 2xx
```

## 13. SecurityContextHolder, threads và test isolation

Spring Security Test cung cấp `WithSecurityContextTestExecutionListener` để tạo/dọn SecurityContext theo vòng đời test. Khi tự thay context ở unit test, cần dọn bằng `SecurityContextHolder.clearContext()` trong `@AfterEach` hoặc `finally` để tránh test nhiễm trạng thái qua thread reuse.

**Nhưng cleanup test không thay cho session lifecycle thật.** Với web/session, Spring Security sử dụng `SecurityContextRepository` và các session strategies để lưu/đọc context. Một test trực tiếp set `SecurityContextHolder` rồi gọi service **không kiểm**:

- Cookie `JSESSIONID` có được cấp đúng và `Secure`/`HttpOnly`/`SameSite` phù hợp không.
- Session fixation protection có đổi session ID sau login không.
- Logout có invalidation thực không.
- Session revoked ở node khác có còn được chấp nhận không.
- Stateless JWT verifier có chạy trên request tiếp theo không.

Các câu hỏi này đòi HTTP integration test/session repository/proxy hoặc E2E. Một `Authentication` đã bị inject là trạng thái của **bài test**, không có nguồn bảo đảm tự thân.

## 14. Khác biệt còn lớn hơn khi có MFA và SSO

### 14.1. MFA

Test `@WithMockUser(roles="ADMIN")` có thể làm endpoint admin pass dù app sản phẩm yêu cầu MFA. Nếu MFA policy dựa trên factor authorities, assurance claims hoặc session state, test cần tạo đúng **verified factor representation** và có test thực cho luồng factor enrollment, OTP/WebAuthn verifier, replay, freshness, recovery bypass.

Không tự coi `authorities={"FACTOR_TOTP"}` đặt trong test là bằng chứng TOTP đã được xác minh ở production. Các authority names hoặc MFA flags đều có thể **giả lập** trong test; cần test đường phát hành và xác minh thật của chúng.

### 14.2. OIDC login

`.with(oidcLogin())` có thể đặt một `OidcUser` đã được xây cho test. Nó hữu ích để kiểm principal mapping và authorization sau SSO, nhưng không chứng minh:

- `state`/`nonce` được generate và validate đúng;
- authorization code chỉ dùng một lần;
- ID Token được verify chữ ký/issuer/audience/expiry;
- external identity `(iss, sub)` được link an toàn với local account;
- logout/revocation trong IdP hoạt động.

Cần test OAuth client/provider exchange và callback với test IdP hoặc mock web server hỗ trợ kiểm tra protocol thực, không dùng giả principal để “chứng minh” SSO.

### 14.3. Opaque token

Test `opaqueToken()` hỗ trợ authorization với principal/attributes giả; không chứng minh introspection endpoint được gọi, client authentication tới authorization server đúng hoặc response `active=false` bị từ chối. Cần integration test với trusted introspection simulator hoặc IdP test service, cùng token expiration/revocation.

### 14.4. API gateway preauthentication

Nếu kiến trúc tin `X-Authenticated-User` do gateway gắn, một test chủ động set header có thể mô phỏng trusted proxy path nhưng **không chứng minh** backend đã chặn spoofed header từ Internet. Test mạng/proxy phải xác minh gateway xóa/ghi đè header từ client, backend không public, account binding và permission source đáng tin.

## 15. Bộ ma trận QA gợi ý cho một module authentication

| Kiểm thử | Dùng mock principal? | Cần real verifier? | Giá trị |
|---|---|---|---|
| Method `@PreAuthorize` chỉ cho `ROLE_READER` | Có | Không, nếu test scope chỉ authorization | Kiểm chính sách role |
| Controller trả đúng identity từ Authentication | Có | Không | Kiểm mapping principal |
| User không có role bị 403 | Có | Không | Negative authz |
| Không có account ghost mà login thành công | **Không** | Có | Kiểm anti-account-confusion |
| Password sai nhưng app vẫn login | **Không** | Có | Kiểm password provider |
| Account locked/disabled không login | **Không** | Có | Kiểm account flags ở verifier |
| Password hash strategy hoạt động | Không | Có | Kiểm `PasswordEncoder` |
| JWT sai chữ ký nhưng được chấp nhận | **Không** | Có | Kiểm cryptographic JWT decoder |
| JWT sai audience/issuer/hết hạn | **Không** | Có | Kiểm token validators |
| JWT thật thiếu scope bị 403 | Có thể bổ sung authz mock, nhưng cần ít nhất một integration | Có cho end-to-end | Token mapping + permission |
| Form login thiếu CSRF | **Không** | Request filter đầy đủ | Kiểm browser CSRF path |
| Cookie/session fixation sau login | **Không** | Cần login filter + session | Kiểm lifecycle |
| MFA OTP replay | **Không** | Cần real MFA verifier/store | Kiểm single-use |
| Wrong tenant object despite role | Có | Không bắt buộc cho unit policy | Kiểm object ownership |
| OIDC ID Token sai nonce | **Không** | Cần real protocol/validator | Kiểm SSO security |
| Email/OTT/reset token đổi mục đích | **Không** | Cần purpose-specific verifier | Kiểm token confusion |

### 15.1. Bộ test đặt tên trung thực

**Authorization với giả principal:**

```text
givenAuthenticatedReader_whenReadOwnReport_thenAllowed()
givenAuthenticatedReader_whenReadOtherTenantReport_thenForbidden()
givenMockAdmin_whenInvokeProtectedMethod_thenAllowed()
givenAnonymous_whenOpenPrivateEndpoint_thenUnauthorized()
```

**Authentication với bằng chứng được kiểm tra:**

```text
givenWrongPassword_whenHttpBasic_then401()
givenDisabledAccount_whenFormLogin_thenAuthenticationFails()
givenValidPassword_whenFormLogin_thenSessionIsEstablished()
givenUnsignedJwt_whenBearerRequest_then401()
givenExpiredJwt_whenBearerRequest_then401()
givenWrongAudienceJwt_whenBearerRequest_then401()
givenValidSignedJwt_whenBearerRequest_thenPermissionsApplied()
givenInvalidOtp_whenStepUp_thenAccessDenied()
```

Cách đặt tên này giúp người đọc hiểu **bằng chứng nào đã thực sự được xử lý** mà không cần suy từ test fixtures.

## 16. Checklist trước khi kết luận authentication đã được kiểm thử

1. **Ghi mục tiêu từng test:** authentication, authorization, principal shape, HTTP filter, account status, session hay token validation.
2. **Kiểm phạm vi fixture:** `@WithMockUser`/`user()` không đăng nhập; `@WithUserDetails` lookup user nhưng không check password.
3. **Không đếm mock JWT là crypto coverage:** `jwt()`/`oidcLogin()`/`opaqueToken()` chỉ thiết lập security context phục vụ test.
4. **Chạy real filters:** `@AutoConfigureMockMvc(addFilters=true)` hoặc `springSecurity()`; không nhầm với `addFilters=false`.
5. **Chạy real verifier cho test đăng nhập:** không mock AuthenticationManager/DaoAuthenticationProvider/PasswordEncoder để luôn success.
6. **Kiểm password âm tính:** sai password, user không tồn tại, disabled/locked, credential expired, tránh enumeration.
7. **Kiểm JWT âm tính:** chữ ký sai, alg không cho phép, issuer/audience/time sai, scope không đủ, token loại khác.
8. **Kiểm trạng thái:** request thiếu auth → 401/302; token invalid → 401; có auth nhưng thiếu quyền → 403; đúng quyền → response ứng dụng.
9. **Giữ CSRF:** browser form login và các POST thay đổi trạng thái phải có CSRF policy được kiểm thử.
10. **Method security thật:** `@EnableMethodSecurity`, bean Spring proxy, negative tests phát hiện self-invocation/bypass.
11. **Session/cookie:** test success handler, session fixation, logout và revocation khi có session, không suy từ context test.
12. **SSO/MFA:** luôn test đường issuing, signing/verification, factor origin/binding và recovery, không suy từ authority giả.
13. **Threat model:** test principal cross-tenant, role escalation, stale authorities, BOLA/IDOR, không chỉ login happy path.
14. **Tách báo cáo:** phân định số test authorization mock, authentication integration, JWT crypto, E2E; không gộp thành “đã test security”.
15. **Kiểm thiết bị và hạ tầng:** nếu dùng preauth/gateway, xác minh headers không spoof; nếu dùng OIDC, test callback issuer/state/nonce; nếu dùng JWT, test JWKS rotation.
16. **Test data:** chỉ sử dụng tài khoản/keys/credentials thử nghiệm; không commit secrets production, không log raw token/password.

## 17. Câu hỏi tự đánh giá

**Câu 1.** `@WithMockUser(username="ghost",roles="ADMIN")` cho phép gọi một method admin. Có thể kết luận account `ghost` đăng nhập được bằng password không?  
**Trả lời:** Không. Annotation đã tạo context principal giả, có thể không tồn tại user thật. Test chỉ chứng minh authorization với role đã cấp trong fixture.

**Câu 2.** `@WithUserDetails("lan")` có bảo đảm đã chạy `PasswordEncoder.matches` không?  
**Trả lời:** Không. Nó load `UserDetails` từ service rồi dựng authenticated context; không gửi password qua provider. Nếu lookup dùng real DB, chỉ riêng thao tác lookup là có thật.

**Câu 3.** Vì sao `.with(jwt())` có thể pass khi JWT chưa hề được ký?  
**Trả lời:** Đây là request post-processor của Spring Security Test tạo `JwtAuthenticationToken` cho authorization; nó không cần có JWT chữ ký hợp lệ hoặc chạy real decoder.

**Câu 4.** Làm sao kiểm tra password sai bị từ chối thật?  
**Trả lời:** Gửi `httpBasic("lan","wrong")` hoặc `formLogin().user("lan").password("wrong")` qua real SecurityFilterChain/AuthenticationManager/DaoAuthenticationProvider và UserDetailsService+PasswordEncoder thực; assert không tạo Authentication.

**Câu 5.** Một test login có header Basic thật nhưng mock AuthenticationManager luôn success. Nó đã test password chưa?  
**Trả lời:** Chưa. HTTP filter có nhận credentials, nhưng verifier đã bị thay bằng mock trả authenticated object vô điều kiện.

**Câu 6.** Vì sao test role admin chỉ kiểm tra HTTP 200 là không đủ?  
**Trả lời:** Nếu security filters hoặc method security bị tắt, request vẫn có thể 200. Phải có negative tests anonymous/role khác/tenant khác bị chặn.

**Câu 7.** Spring Security Test `jwt()` đã xác minh audience/issuer chưa?  
**Trả lời:** Chưa. Cần real JwtDecoder validators và signed-token HTTP integration tests.

**Câu 8.** Test `@WebMvcTest` có luôn giống full authentication production không?  
**Trả lời:** Không. Nó là MVC slice; beans/providers có thể bị mock hoặc không được load. Kiểm tra actual chain và thêm `@SpringBootTest` integration test khi cần.

**Câu 9.** Dùng `SecurityContextHolder.setAuthentication` trong unit test có phát một session cookie thật không?  
**Trả lời:** Không. Chỉ đặt context trong execution; login filter, session repository và HTTP cookie lifecycle phải được test riêng.

**Câu 10.** Nếu trong hệ thống thật user đã login nhưng quyền admin vừa bị thu hồi, `@WithMockUser(roles="ADMIN")` có phát hiện stale session không?  
**Trả lời:** Không. Nó giả định authority ADMIN hiện có; cần integration tests revocation/role version/current permission checks.

## Tài liệu tham khảo

- [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser`, `@WithUserDetails`, `@WithAnonymousUser` và test listener.
- [Spring Security 6.5 — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `springSecurity()` và FilterChainProxy.
- [Spring Security 6.5 — Running Tests as a User](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html): `user()`, `authentication()`, `securityContext()`.
- [Spring Security — Testing Form-Based Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html): `formLogin()`, CSRF và form login.
- [Spring Security 6.5 — Testing HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html): `httpBasic()` tạo header Basic để filter xác minh.
- [Spring Security — Testing OAuth2/JWT](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, `opaqueToken()`, `oauth2Login()` và giả principal.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): UsernamePasswordAuthenticationFilter, AuthenticationManager, failure/success handlers.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): UserDetailsService, PasswordEncoder và account flags.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoder, issuer/audience/time and signature validation.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, proxy authorization.
