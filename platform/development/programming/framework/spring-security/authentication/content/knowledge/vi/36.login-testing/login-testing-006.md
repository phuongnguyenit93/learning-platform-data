# Yêu cầu sau đăng nhập để xác nhận danh tính được lưu đúng

## 1. Vì sao một lần đăng nhập thành công chưa đủ để kết luận?

Khi kiểm thử một ứng dụng Spring Security có đăng nhập bằng form/session, chúng ta thường gọi `POST /login`, nhìn thấy redirect hoặc HTTP 200 rồi kết luận “đăng nhập hoạt động”. Đây mới là **bước đầu**. Một hệ thống có thể kiểm đúng mật khẩu ở request hiện tại nhưng **không lưu SecurityContext vào session**, gắn sai user vào phiên, không phục hồi authority ở request tiếp theo hoặc vô tình dùng danh tính từ một request khác.

Phép thử có ý nghĩa hơn là thực hiện **hai HTTP request độc lập**:

1. **Request đăng nhập:** gửi credential qua cơ chế login thật; kiểm authentication thành công và thu lấy phiên được server trả về.
2. **Request sau đăng nhập:** không gửi lại username/password; chỉ mang đúng phiên đó đến endpoint được bảo vệ. Endpoint phải thấy **đúng principal và authorities** của user vừa đăng nhập.
3. **Kiểm thử âm tính:** request mới **không có phiên** hoặc phiên của người dùng khác không được mang theo cùng danh tính; login thất bại không lưu user; user đúng nhưng thiếu role vẫn phải bị chặn.
4. **Kiểm tra lifecycle:** logout/invalidate/expired session làm danh tính không còn được sử dụng; nếu ứng dụng dựa trên Bearer JWT thay session, phải kiểm token ở request kế tiếp thay vì giả định state được lưu trên server.

Đây là bài thuộc nhóm **Kiểm thử đăng nhập** trong module **Spring Security - authentication**. Trọng tâm là xác nhận **persistence và restoration của Authentication giữa các request** chứ không chỉ xác minh password ở một request đơn lẻ.

**Kết luận cốt lõi:** `authenticated()` trên phản hồi `POST /login` là cần thiết nhưng **chưa đủ**; hãy thử `GET /me` với cùng `HttpSession` và xác minh identity + authorities tại endpoint thật.

## 2. Mô hình hai request độc lập

Ví dụ một website server-side sử dụng Spring Security form login:

```text
Browser / MockMvc Client                 Spring Security + Server
           |                                        |
           | POST /login                           |
           | username=alice, password=...          |
           | CSRF token hợp lệ                     |
           |--------------------------------------->|
           |                             UsernamePasswordAuthenticationFilter
           |                             AuthenticationManager / DaoAuthenticationProvider
           |                             PasswordEncoder kiểm password
           |                             UsernamePasswordAuthenticationToken
           |                             SecurityContextRepository.saveContext(...)
           |<---------------------------------------|
           | 302 Location: /                       |
           | Set-Cookie: JSESSIONID=...             |
           |                                        |
           | GET /me                               |
           | Cookie: JSESSIONID=...                 |
           |--------------------------------------->|
           |                             SecurityContextHolderFilter
           |                             load từ SecurityContextRepository
           |                             authorization: authenticated
           |                             controller đọc Authentication.getName()
           |<---------------------------------------|
           | 200 JSON { username: "alice", ... }    |
```

Trong MockMvc, chúng ta thường chuyển cùng một `MockHttpSession` từ lần `perform(post("/login"))` sang lần `perform(get("/me").session(session))`. Điều đó **mô phỏng việc browser gửi session cookie trong request thứ hai**.

Không cần (và không nên) gửi lại password ở `GET /me`. Nếu test phải gắn username/password hoặc inject một mock principal vào request sau, test không còn chứng minh identity đã được **lưu rồi khôi phục** từ đăng nhập ban đầu.

### 2.1. Phân biệt các loại state

| Thành phần | Tồn tại ở đâu? | Trách nhiệm |
| --- | --- | --- |
| `SecurityContextHolder` | Thường thread-local trong lúc xử lý request | Cho code đang chạy biết Authentication của request |
| `SecurityContext` | Object chứa `Authentication` | Danh tính và trạng thái xác thực của request |
| `SecurityContextRepository` | Tầng load/save context | Liên kết Authentication với các request tiếp theo |
| `HttpSessionSecurityContextRepository` | HTTP session | Lưu SecurityContext qua request trong web session |
| `RequestAttributeSecurityContextRepository` | Request attributes | Giữ context trong một request qua các dispatch, **không** phải storage phiên nhiều request |
| `DelegatingSecurityContextRepository` | Ủy nhiệm đến nhiều repositories | Mặc định phổ biến của Spring Security 6 là request attribute + HttpSession |
| `JSESSIONID` | Cookie chứa session ID | Chỉ định phiên cho server, **không tự chứa user/password** |
| `Authentication` | Object do cơ chế xác thực tạo | Principal, authorities, trạng thái authenticated, details và credential |

`SecurityContextHolder` không phải kho đăng nhập vĩnh viễn. Sau khi servlet filter chain kết thúc, context của request được dọn khỏi thread; lần sau Spring Security phải **đọc lại** qua repository hoặc xác thực lại credential theo mô hình stateless.

## 3. Chính xác cần kiểm gì ở request tiếp theo?

Một test post-login tốt có nhiều mức chứng minh:

| Cần kiểm | Vì sao? | Cách chứng minh |
| --- | --- | --- |
| HTTP status hợp lệ | Endpoint được cho phép xử lý | `status().isOk()` |
| Principal đúng | Không lấy nhầm anonymous, user khác hoặc identity cũ | `authenticated().withUsername("alice")`; `Authentication.getName()` |
| Authority phù hợp | Login không tự làm mất vai trò, không cấp thừa quyền | `ROLE_READER`, `SCOPE_x` theo chính sách |
| Authenticated thực sự | Không chỉ trả body giả hoặc session ID tồn tại | Kiểm Authentication trong request |
| Không gửi lại credential | Đã khôi phục identity từ state hợp lệ | Request thứ hai chỉ dùng session |
| Không có session → không được phép | Không có sự cố state leak giữa clients | Anonymous request bị chuyển login/401 |
| Login sai → không có identity được lưu | Failure không tạo authenticated session | Request thứ hai với phiên failure vẫn bị chặn |
| Session của user B khác user A | Không có session confusion/cross-user leak | Hai login độc lập, hai GET cho đúng tên |
| Thiếu quyền vẫn 403 | Authentication khác authorization | Authenticated user `ROLE_READER` vào `/admin` bị từ chối |
| Logout/expired session không còn hiệu lực | Không để session sống quá lifecycle | Sau logout dùng cookie cũ không còn auth |
| Bảo vệ CSRF/session fixation | Phiên không thể bị thiết lập ngoài ý muốn | POST thiếu CSRF không login; session policy đúng |

**Lưu ý:** chỉ gọi `status().isOk()` chưa đủ. Controller có thể là public, hoặc test vô tình mock Authentication ngay trên request thứ hai. Hãy buộc endpoint yêu cầu `authenticated()` và kiểm đúng principal thực sự trong `SecurityContext`.

## 4. Luồng lưu và khôi phục trong Spring Security 6.x

Trong Spring Security 6, `SecurityContextHolderFilter` tải context từ `SecurityContextRepository`, nhưng **không tự động lưu lại mọi thay đổi** của `SecurityContextHolder` khi request kết thúc. Với các cơ chế authentication chuẩn như form login, filter liên quan thực hiện việc lưu context cho bạn khi đăng nhập thành công. Nếu bạn tự viết custom login filter/controller, bạn cần xử lý **explicit save**.

Chuỗi điển hình:

```text
Request 1: POST /login
  UsernamePasswordAuthenticationFilter
    └─ AuthenticationManager.authenticate(...)
         └─ UserDetailsService + PasswordEncoder
    └─ SessionAuthenticationStrategy (session fixation policy)
    └─ Tạo SecurityContext mới, gắn Authentication đã xác thực
    └─ SecurityContextRepository.saveContext(...)
    └─ SuccessHandler: redirect

Request 2: GET /me + session ID
  SecurityContextHolderFilter
    └─ SecurityContextRepository.loadDeferredContext(request)
    └─ Set vào SecurityContextHolder khi cần
  AuthorizationFilter
    └─ authenticated()
  Controller
    └─ Authentication.getName() → "alice"
```

### 4.1. Vì sao cần request thứ hai?

Nếu một custom handler chạy:

```java
// PHẢN VÍ DỤ: chỉ set ThreadLocal, KHÔNG lưu qua repository
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
```

Endpoint trong **request hiện tại** có thể thấy user, nhưng request sau lại anonymous. Với Spring Security 6 khi yêu cầu explicit save, đoạn trên **không đủ** để persist Authentication. Cần gọi `SecurityContextRepository.saveContext(context, request, response)` theo cấu hình của chain, và phải làm **trước khi response bị committed**.

### 4.2. Mặc định repository gồm những gì?

Ở Servlet stack Spring Security 6.x, cấu hình thông dụng mặc định dùng `DelegatingSecurityContextRepository` với `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository`. Nhánh request attribute có thể phục vụ error/forward dispatch **trong cùng HTTP request**; nhánh HttpSession giữ identity cho **request khác** có cùng session.

Khi test mục tiêu “đăng nhập một lần, request khác vẫn là Alice”, điều bạn thật sự kiểm là phiên/context được persist + restored, không chỉ tồn tại attribute tạm ở request đầu.

Thay bằng `NullSecurityContextRepository` hoặc cấu hình `SessionCreationPolicy.STATELESS` trong chain web có thể làm thất bại kỳ vọng giữ session. Nhưng trong Resource Server stateless, điều đó có thể là **thiết kế đúng**: mỗi request phải cung cấp token của mình.

## 5. Lựa chọn lớp kiểm thử

Không phải mọi phương pháp đều chứng minh điều giống nhau:

| Kiểu kiểm thử | Kiểm được gì? | Giới hạn |
| --- | --- | --- |
| Unit test `AuthenticationProvider` | Đúng/sai credential, authorities khi authenticate | Không chứng minh HTTP session/repository |
| `@WithMockUser` | Authorization/controller với user giả lập | Không thực hiện login thật, không kiểm persistence |
| `user("alice")` request post-processor | User giả lập ở request đang kiểm | Không chứng minh session từ login trước |
| `jwt()` post-processor | Test phân quyền JWT giả lập | Không kiểm chữ ký/issuer/audience và không chứng minh session |
| MockMvc `POST /login` rồi `GET /me` cùng session | Form filter, authentication manager, repository và authorization theo request | Giả lập Servlet, chưa chứng minh cookie/TLS/proxy thực tế |
| HTTP integration test với server chạy + cookie jar | Set-Cookie, session ID, cookie flags, HTTP thật và routing | Chậm hơn; cần môi trường quản lý được |
| Browser E2E (Playwright/Selenium) | UX login, redirect, browser cookie, CSRF, logout | Khó cô lập root cause; không thay integration test |

**Khuyến nghị cho đề bài này:** chọn MockMvc hai-request làm test chính, sau đó có một HTTP/browser test thực cho session cookie, proxy và các vấn đề vòng đời. Không chỉ dùng `@WithMockUser`.

## 6. Project Spring Boot 3.x và Java 17: cấu hình chuẩn

Ví dụ được thiết kế cho **Spring Boot 3.x + Spring Security 6.x + Java 17+**, sử dụng Spring MVC/Servlet và một form login mặc định. Chưa tích hợp Redis session, OIDC hay database thật để trọng tâm không bị lệch.

### 6.1. Dependencies Gradle

Trong project đã có plugin Spring Boot, dependency management, Java toolchain phù hợp, thêm khối `dependencies`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-security-test` cung cấp các matchers/processors như `authenticated()`, `unauthenticated()`, `csrf()`, `formLogin()` và `user()`. `@SpringBootTest` + `@AutoConfigureMockMvc` làm cho các filter do Spring Boot tự cấu hình được áp vào MockMvc.

**Không cần tự gọi `MockMvcBuilders.standaloneSetup(...)` cho ví dụ này.** Nếu tự build MockMvc thay vì dùng Boot auto-configuration, phải gắn Spring Security bằng `.apply(springSecurity())` (và framework/context phù hợp); nếu không test có thể bỏ qua filters và cho kết quả sai.

### 6.2. Main class

Đặt các tệp Java ở `src/main/java/com/example/loginproof/`, package `com.example.loginproof`.

**`LoginProofApplication.java`**

```java
package com.example.loginproof;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginProofApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoginProofApplication.class, args);
    }
}
```

### 6.3. SecurityConfig.java

**`SecurityConfig.java`**

```java
package com.example.loginproof;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/error").permitAll()
                        .requestMatchers("/me").authenticated()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-secret"))
                        .roles("READER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-demo-secret"))
                        .roles("VIEWER")
                        .build());
    }
}
```

**Điểm đáng chú ý:**

- `formLogin(Customizer.withDefaults())` sử dụng Spring Security login page mặc định và xử lý `POST /login` bằng `UsernamePasswordAuthenticationFilter`.
- `/me` yêu cầu authenticated user; `/admin` còn yêu cầu `ROLE_ADMIN`. Alice và Bob **không** có role ADMIN trong demo, nên cùng đăng nhập được nhưng bị 403 khi vào `/admin`.
- `PasswordEncoder` là BCrypt, không so plaintext trực tiếp. Hai mật khẩu chỉ dành cho **lab/test**, không phải secrets hợp lệ để đưa vào production.
- `anyRequest().denyAll()` chặn URL chưa định nghĩa; các trang login/error được permit để không gây redirect loop.
- Không disable CSRF. Khi POST form login, test cần tạo CSRF token đúng; bỏ qua CSRF để sửa test 403 là hành động sai với web session.
- Không dùng `SessionCreationPolicy.STATELESS` vì đây là website cần lưu Authentication trong HttpSession.
- Trong project thật, UserDetailsService và password encoder có thể dùng database/LDAP, session store phân tán, MFA và account state; ý nghĩa test hai-request vẫn giữ nguyên.

### 6.4. Endpoint quan sát identity mà không lộ secrets

**`IdentityController.java`**

```java
package com.example.loginproof;

import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/")
    public String home() {
        return "Home: public";
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();

        return Map.of(
                "username", authentication.getName(),
                "authenticated", authentication.isAuthenticated(),
                "authorities", authorities);
    }

    @GetMapping("/admin")
    public String admin() {
        return "Admin: permitted";
    }
}
```

Khi session của Alice được restore đúng, `GET /me` sẽ trả JSON tương tự:

```json
{
  "username": "alice",
  "authenticated": true,
  "authorities": ["ROLE_READER"]
}
```

Đây là ví dụ response **kỳ vọng theo demo**, không phải kết quả đã đo trên một server thật. Không trả credential, password hash, OAuth2 access/refresh token, session ID hoặc toàn bộ `Authentication.toString()`. Với production, endpoint `/me` chỉ trả thông tin người dùng thực sự cần hiển thị; các quyền chi tiết có thể là thông tin nội bộ nên phải cân nhắc contract.

## 7. MockMvc test chính: login thật rồi gửi request tiếp theo

Đây là phần quan trọng nhất của bài. File test nằm ở `src/test/java/com/example/loginproof/LoginPersistenceTest.java`.

**`LoginPersistenceTest.java`**

```java
package com.example.loginproof;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.hasItem;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginPersistenceTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login(String username, String password)
            throws Exception {

        MvcResult loginResult = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", username)
                        .param("password", password))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername(username))
                .andReturn();

        HttpSession session = loginResult.getRequest().getSession(false);
        assertNotNull(session, "Login must establish a session");
        return (MockHttpSession) session;
    }

    @Test
    void nextRequestMustRestoreAliceFromSameSession() throws Exception {
        MockHttpSession session = login("alice", "alice-demo-secret");

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(authenticated().withUsername("alice"))
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authenticated").value(true))
                .andExpect(jsonPath("$.authorities", hasItem("ROLE_READER")));
    }

    @Test
    void freshRequestWithoutSessionMustNotBorrowAlice() throws Exception {
        login("alice", "alice-demo-secret");

        // Không truyền .session(...) trong request thứ hai.
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void differentSessionsMustKeepTheirOwnIdentities() throws Exception {
        MockHttpSession alice = login("alice", "alice-demo-secret");
        MockHttpSession bob = login("bob", "bob-demo-secret");

        mvc.perform(get("/me").session(alice))
                .andExpect(status().isOk())
                .andExpect(authenticated().withUsername("alice"))
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authorities", hasItem("ROLE_READER")));

        mvc.perform(get("/me").session(bob))
                .andExpect(status().isOk())
                .andExpect(authenticated().withUsername("bob"))
                .andExpect(jsonPath("$.username").value("bob"))
                .andExpect(jsonPath("$.authorities", hasItem("ROLE_VIEWER")));
    }

    @Test
    void readerIsAuthenticatedButNotAuthorizedAsAdmin() throws Exception {
        MockHttpSession session = login("alice", "alice-demo-secret");

        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden())
                .andExpect(authenticated().withUsername("alice"));
    }
}
```

### 7.1. Đọc từng bước của test thành công

1. `mvc.perform(post("/login").with(csrf())...)` gửi HTTP request login qua **filter chain thật** trong Spring test context; không inject sẵn Authentication giả.
2. `andExpect(authenticated().withUsername("alice"))` xác nhận authentication trên **kết quả login** đúng Alice.
3. `getRequest().getSession(false)` lấy phiên phía server **sau khi login**, không tạo session mới chỉ để cho test qua. Phép cast tới `MockHttpSession` phù hợp môi trường MockMvc.
4. `mvc.perform(get("/me").session(session))` là **request mới**. Không có `.with(user("alice"))`, không có password và không set `SecurityContextHolder` thủ công.
5. `authenticated().withUsername("alice")` trên **request thứ hai** kiểm được Authentication đã được khôi phục, thay vì chỉ dựa vào HTTP 200.
6. `jsonPath("$.username")` và `jsonPath("$.authorities")` chứng minh controller nhìn thấy đúng danh tính và role trong context đã phục hồi.
7. Test user Bob dùng một session khác để xác minh **cách ly hai người dùng**; việc request Alice rồi Bob rồi Alice vẫn đúng giúp phát hiện rò rỉ state giữa các request hoặc thread.

**Ý nghĩa:** test có thể thất bại nếu một custom authentication handler chỉ set ThreadLocal mà không save SecurityContext. Login request có thể vẫn được xem là authenticated, nhưng GET /me ở request kế tiếp lại chuyển hướng đăng nhập.

### 7.2. Không coi redirect login là chứng cứ persistence

Form login thường trả 302 sau khi login thành công. Redirect chỉ cho biết success handler được gọi; nếu repository lưu sai hoặc một request dùng session khác, request mới vẫn có thể không có user. Hãy kiểm `GET /me`. Tương tự, một response có HTTP 200 không chứng minh Authentication nếu endpoint không protected.

### 7.3. Chạy test

Trong project có Gradle wrapper:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Kết quả kỳ vọng** là bốn test ở file trên pass khi cấu hình đúng. Bài này cung cấp mã và cách kiểm thử, **không tuyên bố đã chạy lệnh trong repository hoặc CI**. Với dự án thật có security filters/CSRF/session config khác, điều chỉnh test theo contract của dự án nhưng vẫn giữ yêu cầu **hai request và kiểm cùng identity**.

## 8. Trường hợp login thất bại: không được lưu authenticated principal

Login sai thường được `AuthenticationFailureHandler` xử lý; context xác thực cần bị xóa hoặc không được tạo. Dùng cùng một session trước/ sau lần login sai để chắc chắn thất bại không cấp quyền.

Đoạn test **thêm vào class `LoginPersistenceTest`** (cần imports được ghi ở dưới):

```java
@Test
void failedLoginMustNotAuthenticateExistingAnonymousSession()
        throws Exception {

    MockHttpSession session = new MockHttpSession();

    mvc.perform(post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "wrong-secret"))
            .andExpect(status().is3xxRedirection())
            .andExpect(unauthenticated());

    mvc.perform(get("/me").session(session))
            .andExpect(status().is3xxRedirection())
            .andExpect(unauthenticated());
}
```

Thêm import:

```java
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
```

**Không** chỉ assert “login sai → chuyển `/login?error`” rồi dừng: nếu custom filter vô tình lưu authentication trước khi xác minh xong, một request tiếp theo vẫn có thể được cho qua.

Cần phân biệt **login thất bại của một session anonymous** với **user đang đăng nhập rồi nhập sai credential ở một form khác**. Trong tình huống thứ hai, policy có thể là giữ session hiện tại, yêu cầu reauthentication, xóa session hoặc báo lỗi; phải định nghĩa rõ contract. Không lấy một failed login attempt làm bằng chứng chắc chắn tất cả phiên khác của user đã bị xóa.

## 9. Kiểm tra CSRF và xác thực đúng endpoint

Với browser form login, Spring Security mặc định bật CSRF. Test gửi `POST /login` không có token có thể bị chặn 403 **trước** khi password được kiểm. Nếu chỉ assert 403 rồi kết luận “sai mật khẩu bị chặn”, test sai mục tiêu.

Đoạn test có thể thêm vào class:

```java
@Test
void postLoginWithoutCsrfMustBeRejected() throws Exception {
    mvc.perform(post("/login")
                    .param("username", "alice")
                    .param("password", "alice-demo-secret"))
            .andExpect(status().isForbidden());
}
```

Khi muốn test login thật, dùng `.with(csrf())` hoặc Spring Security Test `formLogin()` tạo CSRF đúng. Không tắt CSRF toàn web chain để làm test “dễ pass”.

**Test âm tính quan trọng:** sau POST thiếu CSRF, request vào `/me` không được có authenticated Alice. Có thể bổ sung một session mới rõ ràng vào cả hai request để xác minh điều đó, tương tự mục 8. Các state-mutating endpoints dùng cookie session cũng phải được bảo vệ CSRF; GET /me chỉ đọc nên không cần token.

## 10. Alternative: sử dụng formLogin() RequestBuilder của Spring Security Test

Spring Security Test có `SecurityMockMvcRequestBuilders.formLogin()`. Đây là helper tạo POST form login với username/password và CSRF hợp lệ, không phải cách inject user giả.

Ví dụ **đoạn đặt trong test class**, sử dụng helper:

```java
MvcResult loginResult = mvc.perform(formLogin()
                .user("alice")
                .password("alice-demo-secret"))
        .andExpect(authenticated().withUsername("alice"))
        .andReturn();

MockHttpSession session =
        (MockHttpSession) loginResult.getRequest().getSession(false);
assertNotNull(session);

mvc.perform(get("/me").session(session))
        .andExpect(authenticated().withUsername("alice"))
        .andExpect(jsonPath("$.username").value("alice"));
```

Import cần dùng:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
```

Với custom `loginProcessingUrl("/auth/login")` và custom parameter names, helper hỗ trợ điều chỉnh URL và tên field theo API của phiên bản Spring Security Test. Trong ví dụ hiện tại, dùng default `POST /login`, `username` và `password`.

**Tại sao `formLogin()` khác `with(user(...))`?** `formLogin()` thực sự gửi POST qua authentication filters; `with(user("alice"))` đặt một SecurityContext giả lập trên request đang test. Chỉ kiểu đầu, khi gắn session rồi GET tiếp theo, mới chứng minh đường đăng nhập đã chạy.

## 11. Kiểm thử trực tiếp SecurityContext trong HttpSession: khi nào cần?

Có thể đọc thuộc tính session mà `HttpSessionSecurityContextRepository` thường dùng:

```java
Object stored = session.getAttribute(
        HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);

assertNotNull(stored);

SecurityContext context = (SecurityContext) stored;
assertEquals("alice", context.getAuthentication().getName());
```

Đây là **snippet Java bổ sung cho test**; cần imports:

```java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import static org.junit.jupiter.api.Assertions.assertEquals;
```

Với Spring Security 6 mặc định dùng session repository, kiểm tra này giúp chẩn đoán state storage. Tuy nhiên:

- Nó phụ thuộc **cơ chế lưu cụ thể**. Nếu dự án dùng custom `SecurityContextRepository`, Redis/session adapter khác hoặc stateless API, key/loại dữ liệu có thể khác.
- Có object trong session **chưa đủ**: authorization có thể vẫn dùng một filter chain khác và không load được object đó.
- Điều quan trọng nhất vẫn là **request thứ hai không inject mock principal** và endpoint protected đọc đúng Authentication.
- Không đọc session ID hoặc serialized SecurityContext vào log/CI artifacts.

**Ưu tiên test hành vi.** Khi debug session persistence, mới dùng kiểm tra repository/session attribute để thu hẹp nguyên nhân.

## 12. Custom authentication: explicit save bắt buộc khi muốn duy trì phiên

Nếu ứng dụng tự viết controller login hoặc filter tạo Authentication, cách sau là **minh họa logic đặt trong component có request/response/AuthenticationManager và repository được cấu hình**:

```java
Authentication requested =
        UsernamePasswordAuthenticationToken.unauthenticated(
                submittedUsername, submittedPassword);

Authentication verified = authenticationManager.authenticate(requested);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// Spring Security 6: phải lưu nếu muốn request tiếp theo load context.
securityContextRepository.saveContext(context, request, response);
```

Các kiểu cần import:

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;
```

**Không copy snippet này nguyên vào main project rồi coi như một login controller độc lập.** Cần implement AuthenticationManager, error handling, session authentication strategy, CSRF policy, success/failure handler, account controls và đúng `SecurityContextRepository` của chain. Một custom flow bỏ qua session fixation strategy có thể tạo lỗ hổng ngay cả khi context đã được lưu.

### 12.1. Hai lỗi thường gặp ở Spring Security 6

**Lỗi A: chỉ set context, không gọi save.** Trong request hiện tại user được xác thực nhưng request sau anonymous. Mẫu hai-request test bắt được.

**Lỗi B: dùng repository không khớp chain.** Custom controller lưu vào một `HttpSessionSecurityContextRepository` tùy tạo, trong khi filter chain đọc từ `NullSecurityContextRepository` hoặc repository custom khác. Có state nhưng không được phục hồi. Phải cấu hình và sử dụng nhất quán trên đường login và những request protected.

### 12.2. Save trước khi redirect hoặc commit response

Khi dùng `sendRedirect`, response có thể bị committed. Nên lưu SecurityContext trước khi gửi redirect/trả response. Nếu tạo session sau khi response đã committed, cookie session có thể không đến client như mong muốn. Một test chỉ nhìn username ở login request có thể không phát hiện, còn test sau login sẽ phát hiện.

### 12.3. SecurityContextHolderFilter và sự khác biệt với Spring Security 5

Trong Spring Security 5, `SecurityContextPersistenceFilter` từng hỗ trợ save context khi kết thúc request theo cấu hình mặc định. Spring Security 6 ưu tiên `SecurityContextHolderFilter`, yêu cầu explicit save khi custom code thay Authentication. Không cố bật cả hai filters để “chữa” persistence; xem tài liệu phiên bản đang dùng và thiết kế repository đúng.

## 13. Session fixation và vì sao nên lấy session sau login

Một rủi ro của login qua HTTP session là **session fixation**: attacker cố khiến nạn nhân đăng nhập vào một session ID đã biết. Spring Security thường dùng session authentication strategy để thay đổi session ID hoặc session theo cấu hình/container.

Vì thế trong test:

1. Đăng nhập qua filter chuẩn, không tự set Authentication để bỏ qua session strategy.
2. Lấy session **từ kết quả sau login** bằng `loginResult.getRequest().getSession(false)`.
3. Dùng session đó cho GET /me. Không hardcode session ID hay giả định ID trước và sau login luôn giống nhau.
4. Nếu test session fixation cụ thể, tạo session trước login và kiểm `SessionAuthenticationStrategy` theo environment; không dùng một assertion phù hợp container này rồi coi là bảo đảm trên mọi container.

Session ID là credential của browser session. Không trả nó trong JSON /me, không log full cookie, dùng HTTPS, cookie `Secure`, `HttpOnly` và `SameSite` theo chính sách. Cookie ID **không mang username**; server dùng ID để tra context.

Với nhiều instance/pod, cần session affinity hoặc distributed session store phù hợp. Một integration test dùng load balancer gửi login tới node A và request sau tới node B sẽ phát hiện lỗi session state không được chia sẻ.

## 14. Hai người dùng, hai phiên: chống rò rỉ identity

Test Alice và Bob ở mục 7 kiểm hai session tách biệt. Có thể mở rộng bằng cách gửi luân phiên:

```text
Login Alice → session A
Login Bob   → session B

GET /me + session A  → username = alice, ROLE_READER
GET /me + session B  → username = bob,   ROLE_VIEWER
GET /me + session A  → username = alice, ROLE_READER
GET /me không session → anonymous/redirect login
```

Mục tiêu: bắt lỗi **cross-user contamination**, ví dụ một controller lưu current user trong field singleton hoặc custom filter không dọn `SecurityContextHolder` của thread trước khi tái sử dụng.

**Sai lầm nguy hiểm:**

```java
// PHẢN VÍ DỤ: singleton controller giữ identity trong field chia sẻ
@RestController
class UnsafeController {
    private String lastUser;

    @GetMapping("/whoami")
    String who(Authentication auth) {
        lastUser = auth.getName();
        return lastUser;
    }
}
```

Code trên không phải một giải pháp test identity: field mutable trong bean singleton có race giữa requests; nếu sử dụng `lastUser` ở nơi khác, user A có thể nhìn thấy thông tin user B. Trong controller/service, lấy identity từ Authentication của **request hiện tại**, không giữ principal trong field dùng chung.

MDC/tracing cần được clear đúng ở cuối request; không coi `ThreadLocal` do tự tạo là session store. `SecurityContextHolderFilter` quản lifecycle context của framework, nhưng custom ThreadLocal của ứng dụng vẫn cần dọn riêng.

## 15. Đăng xuất, hết hạn phiên và xác thực lại

Sau đăng nhập, test không chỉ hỏi “có lưu user không?” mà còn hỏi “khi nào không còn được dùng?”. Cần kiểm:

- `POST /logout` với CSRF hợp lệ làm clear Authentication và invalidate session theo cấu hình.
- Request dùng session/cookie **cũ** sau logout không được truy cập /me như authenticated user.
- Session hết hạn theo server policy khiến request protected cần login lại.
- Role/permission bị thu hồi trong khi session đang tồn tại phải được phản ánh theo chính sách refresh hoặc invalidation.
- Password reset, user disabled, account locked hoặc MFA step-up có thể yêu cầu hủy/đổi session theo threat model.
- Concurrent sessions: nếu có cấu hình `maximumSessions`, kiểm session A/B theo hành vi mong muốn, không giả định mặc định framework tự giới hạn.
- Remember-me, persistent login và OAuth2 authorized client state cần test riêng, vì chúng có thể **tái xác thực** user ngay cả khi session gốc đã hết.

Với MockMvc, sau khi logout một `MockHttpSession` có thể bị **invalidated**, nên cố dùng lại object đó có thể ném exception thay vì tạo request như browser thật. Để xác minh cookie cũ trên HTTP thực, dùng test server với cookie jar/client có thể gửi cookie cũ mà không dùng object đã invalidate; kết quả mong đợi là không còn authenticated.

**Đừng coi redirect tới `/login` sau logout là đủ** nếu một endpoint JSON/API vẫn chấp nhận session cũ hoặc còn một remember-me token có hiệu lực.

## 16. OAuth2/OIDC login: danh tính nào được lưu?

Nếu website sử dụng `oauth2Login()` thay vì form login, pattern kiểm thử **vẫn là hai request** nhưng loại Authentication/principal khác:

1. Browser thực hiện Authorization Code/OIDC login qua IdP.
2. Spring Security xác minh response/token từ IdP, xây `OAuth2AuthenticationToken` với principal `OAuth2User` hoặc `OidcUser`.
3. Theo cấu hình web session, SecurityContext được persist; request sau với cùng session phải thấy principal của **đúng provider và đúng người dùng**.
4. Endpoint kiểm `authentication.getName()`, provider registration và claims đã được xác minh theo contract; không coi email chưa verified là định danh chính khi liên kết local account.
5. Logout OIDC, token expiration và local session expiration là **các vòng đời khác nhau**, phải test riêng.

Với OIDC, danh tính ổn định nên dựa vào cặp `(iss, sub)` theo issuer đã tin cậy. Không dựa vào display name/email có thể đổi hoặc trùng để liên kết tài khoản. Khi so sánh identity trong post-login request, cần xác minh chính xác **issuer, subject, tenant và local account mapping** nếu ứng dụng liên kết provider bên ngoài.

### 16.1. Unit/mock OIDC khác test callback thật

Spring Security Test có post-processors như `oidcLogin()` để tạo authenticated principal cho một request kiểm authorization/controller. Nó không tự mô phỏng quá trình redirect/callback, `state`, nonce, signature/issuer validation và session save của OIDC login thật.

Do đó:

- `oidcLogin()` phù hợp để kiểm controller và policy cho một `OidcUser` giả lập.
- Để chứng minh **OIDC login được persist qua request**, cần integration test cho login flow/callback trong môi trường IdP test hoặc một web E2E flow, rồi gọi request thứ hai bằng session cookie.
- Không lấy `oidcLogin()` request processor trên GET /me rồi tuyên bố OIDC login persistence thành công.

## 17. Resource Server Bearer/JWT: request thứ hai có ý nghĩa khác

Đối với API stateless dùng `oauth2ResourceServer().jwt()`, không có mục tiêu “JWT được lưu trong HttpSession” trừ khi ứng dụng **cố ý** thiết kế điều đó. Thông thường mỗi HTTP request tự cung cấp:

```http
GET /api/me HTTP/1.1
Authorization: Bearer <access_token>
```

Resource Server xác minh chữ ký/issuer/audience/expiry của **access token** rồi tạo `JwtAuthenticationToken` cho **request đó**. Sau request, không có yêu cầu giữ JWT trong session.

Test API stateless nên kiểm:

| Yêu cầu | Kết quả kỳ vọng |
| --- | --- |
| GET /api/me có JWT hợp lệ đúng scope | 200, principal/claims đã verify |
| GET /api/me kế tiếp với cùng token hợp lệ | Vẫn có identity đúng |
| GET /api/me kế tiếp **không** có token | 401, không được “mượn” Authentication từ request trước |
| Token chữ ký sai, sai issuer/audience, hết hạn | 401 |
| Token hợp lệ nhưng thiếu scope/role | Thường 403 |
| Cookie từ web form không phải Bearer token | Không tự cho phép truy cập API nếu API chain stateless |

**Rất quan trọng:** test dùng `jwt()` của Spring Security Test chỉ mô phỏng Authentication, **không đi qua JwtDecoder kiểm chữ ký**. Cần integration test với token ký bằng test key và JWKS/AS thử nghiệm khi muốn kiểm xác thực token thực.

Vì vậy **cùng khái niệm “request tiếp theo” nhưng khác tiêu chí**: web session cần khôi phục state từ session; stateless API cần xác thực mới từ credential hợp lệ trong từng request.

## 18. HTTP end-to-end với cookie jar

MockMvc là môi trường giả lập. Để xác nhận browser cookie trong HTTP thực, chạy ứng dụng trên port thử nghiệm và dùng cookie jar.

Với web form có CSRF, flow thực thường là:

```text
GET /login
  → nhận session cookie (nếu server tạo)
  → lấy CSRF token trong HTML form hoặc từ cơ chế token endpoint được bảo vệ

POST /login + username/password + CSRF token + session cookie
  → authentication thành công
  → nhận cookie/ID session sau login (có thể thay đổi vì session fixation)

GET /me + cookie phiên mới
  → 200 và đúng identity
```

Không gửi POST không có CSRF rồi tự động tắt CSRF khi thấy 403. Không copy cứng CSRF token từ session khác: token cần khớp chính sách repository/session của request. Với server-rendered form, template engine thường đưa hidden CSRF input đúng vào form. Với SPA, cần contract CSRF phù hợp.

Có thể dùng `curl -c cookies.txt -b cookies.txt` để lưu và gửi cookie, nhưng để login qua CSRF cần trích token đúng từ GET /login; cách triển khai tự động tùy template/HTML. Khi kiểm 302 gốc, đừng dùng `curl -L` trước khi xem header vì redirect có thể che response login.

### 18.1. Vì sao HTTP E2E vẫn cần?

MockMvc không thể kiểm đầy đủ:

- Header `Set-Cookie`/domain/path/secure/samesite qua reverse proxy.
- Session cookie bị browser từ chối do `SameSite`/HTTPS hoặc cross-site origin.
- Session affinity/Redis session giữa hai node.
- HttpSession lifecycle/container behavior trên server thật.
- OIDC login redirect và callback giữa browser/IdP.
- XSS/CSRF, cookie replay/invalid session trong môi trường thực.

Đoạn MockMvc kiểm **logic Spring web security** rất tốt, nhưng E2E mới xác minh toàn đường từ client tới backend.

## 19. Các lỗi thường gặp và cách sửa

| Sai lầm | Vì sao test đánh lừa | Cách sửa |
| --- | --- | --- |
| Chỉ `POST /login` rồi assert 302 | Không chứng minh session/context được lưu | GET /me với session từ login |
| Dùng `with(user("alice"))` ở GET sau login | Tự gắn principal mới, che lỗi persistence | Chỉ dùng `.session(session)` |
| Dùng `@WithMockUser` cho toàn test login | Bypass filter/password validation | Dùng POST login thật trong test context |
| Sau login, GET /me không truyền session | Request mới anonymous đúng thiết kế, test giả lỗi | Truyền `MockHttpSession` hậu login |
| Đọc `SecurityContextHolder` sau `mvc.perform` | ThreadLocal đã được cleanup, dễ kết luận sai | Assert trong request bằng endpoint/ResultMatcher |
| Tạo session mới bằng `getSession()` khi debug | Có session nhưng không chứng minh login đã tạo | Dùng `getSession(false)` và assertNotNull |
| GET /me public, chỉ assert 200 | Anonymous cũng 200 | Bảo vệ `authenticated()` và assert principal |
| Custom login chỉ set context | Không persist trong Security 6 | Gọi `SecurityContextRepository.saveContext` |
| Lưu vào repository khác với chain | GET không load được context | Dùng một repository được cấu hình nhất quán |
| Custom login bỏ session strategy | Có thể tạo session fixation vulnerability | Gọi strategy/flow chuẩn trước save |
| POST form không có CSRF token | 403 từ CsrfFilter, chưa kiểm password | `.with(csrf())` hoặc `formLogin()` helper |
| Kiểm user đúng nhưng bỏ authorities | Role có thể bị mất hoặc cấp sai | Assert role/scope ở request thứ hai |
| Hai users dùng một session trong test | Dữ liệu có thể bị ghi đè, không test isolation | Tạo hai session độc lập và xen kẽ |
| Assert chính xác Location trên mọi setup | SavedRequest/success handler thay đổi redirect | Assert 3xx + đúng target theo contract |
| Test `jwt()` cho persistence | JWT postprocessor chỉ cho request hiện tại | Session test cho web, decoder test cho JWT |
| Nghĩ ID token/OIDC email là session ID | Nhầm danh tính/protocol | Kiểm `(iss, sub)` và web session riêng |
| Test logout bằng MockHttpSession đã invalidate | Có thể gây exception của object mock | Dùng E2E cookie replay hoặc session được mô phỏng hợp lệ |
| Không test no-session/wrong-session | Dễ bỏ sót identity leak giữa users | Negative tests và cross-session |
| Chỉ nhìn response body, không nhìn Authentication | Controller có thể trả dữ liệu hardcode | Assert cả security context và output |
| Không bảo vệ cookie/session | Session hijacking có thể vượt qua login | TLS, Secure/HttpOnly/SameSite, rotation, expiration |
| Giả định session có sẵn trên mọi backend pod | Stateful load balancing có thể làm mất context | Spring Session/affinity phù hợp và E2E |

## 20. Checklist kiểm thử trước khi hoàn tất tính năng login

Một pull request sửa login chỉ nên coi là đã được kiểm tra đầy đủ khi có bằng chứng:

- [ ] POST /login với credential đúng qua **authentication filter thật**, không inject mock user.
- [ ] Phản hồi login thành công đúng HTTP contract (redirect hoặc JSON) và không lộ secret.
- [ ] Test lấy **session sau login**, không giả định session ID ban đầu còn nguyên.
- [ ] GET protected resource ở request thứ hai **không gửi lại password**, chỉ dùng session đã lấy.
- [ ] Kết quả thứ hai có Authentication authenticated, username đúng và quyền đúng.
- [ ] Không có session (hoặc session sai) không nhận danh tính của user trước.
- [ ] Failed login không ghi authenticated principal vào một session anonymous.
- [ ] Two-user test có session Alice/Bob riêng, không rò state khi gửi xen kẽ.
- [ ] Có rule cho role/authorization ở endpoint, user thiếu role bị 403.
- [ ] POST login thiếu CSRF không bị diễn giải nhầm là lỗi password.
- [ ] Logout, session expiry, session fixation và remember-me flow có test riêng.
- [ ] Custom login nếu có lưu SecurityContext đúng repository trước response commit.
- [ ] OIDC/SAML/social login nếu có, kiểm mapping identity và callback persistence thay vì chỉ mock principal.
- [ ] API bearer stateless nếu có, request sau **phải có token hợp lệ riêng**, không dùng session web.
- [ ] Integration test có cookie jar, proxy HTTPS và session store để kiểm browser behavior khi cần.
- [ ] Test không in password/token/cookie/session ID, principal đầy đủ hoặc credential vào CI logs.

## 21. Bài tập thực hành

1. Chạy `LoginPersistenceTest` trong project Boot 3.x. Bỏ lần `.session(session)` khỏi GET /me; giải thích vì sao anonymous redirect lại là hành vi **đúng** cho request không có phiên.
2. Tự viết custom login handler chỉ gán `SecurityContextHolder.setContext(...)` nhưng quên save. Thử login result matcher và GET thứ hai; sau đó sửa bằng `SecurityContextRepository.saveContext(...)`.
3. Thay `.requestMatchers("/me").authenticated()` bằng `permitAll()`. Vì sao chỉ kiểm status 200 sẽ tạo false positive? Thêm assertion Authentication/JSON.
4. Tạo ba user với roles khác nhau. Đăng nhập từng người, dùng session riêng và kiểm `authorities` ở request tiếp theo. Sau đó gửi request Alice→Bob→Alice.
5. Cài test login sai với session tồn tại từ trước, kiểm request thứ hai không trở thành authenticated.
6. Thử POST /login thiếu CSRF và kiểm 403. Tại sao đây không chứng minh password sai? Làm sao dùng `formLogin()` helper để sinh CSRF hợp lệ?
7. Tạo một endpoint chỉ dành cho ADMIN. Kiểm rằng user READER đã xác thực và được lưu đúng session vẫn nhận 403 ở endpoint này.
8. Viết integration test dùng cookie jar qua proxy HTTPS và hai backend pods. Nếu không có distributed session, chuyện gì xảy ra khi request thứ hai vào pod khác?
9. Nếu ứng dụng dùng OIDC, thiết kế test callback thật và GET /me để kiểm `(iss, sub)`/account mapping, không dùng `oidcLogin()` để thay thế kiểm flow.
10. Thiết kế test Resource Server stateless: hai request có JWT hợp lệ đều thành công; request thứ ba không token phải 401, chứng minh không rò identity từ hai request trước.

## 22. Tổng kết và tài liệu tham khảo

- **Một lần login thành công không đủ** để chứng minh danh tính được duy trì. Cần **request thứ hai độc lập** tới tài nguyên protected bằng session/cookie đã nhận.
- Trong Spring Security Servlet, `SecurityContextHolder` biểu diễn context của request; `SecurityContextRepository` giữ và phục hồi Authentication giữa request.
- Với Spring Security 6, custom login phải **save context rõ ràng** khi muốn persist; form login chuẩn thực hiện việc đó theo cơ chế framework.
- Một test mạnh kiểm cả **Authentication/username/authorities** tại GET sau login; không chỉ status 200 hoặc một biến session tồn tại.
- Mock `@WithMockUser`, `with(user(...))` hoặc `jwt()` phù hợp test policy ở một request, **không chứng minh login flow thật đã lưu session**.
- Negative tests thiếu session, login thất bại, session user khác, thiếu role, CSRF và logout cần có để chống false positives.
- Với OAuth2/OIDC web login, tiêu chí vẫn là đúng user/issuer/subject trong request tiếp theo; với API JWT stateless, tiêu chí là **mỗi request** tự xác minh token thay vì lưu web session.

**Tài liệu chính thức để kiểm chứng:**

- [Spring Security 6.5 — Testing Form-Based Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — Testing MockMvc Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SecurityContextRepository and Explicit Saving](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Spring Security Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)