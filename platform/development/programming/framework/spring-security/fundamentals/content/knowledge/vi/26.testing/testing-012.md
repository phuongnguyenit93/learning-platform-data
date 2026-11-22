# Phân biệt kiểm thử đơn vị, tích hợp và hành vi thực tế trên trình duyệt

## 1. Ba loại kiểm thử — ba loại bằng chứng khác nhau

Trong Spring Security, **một unit test xanh chưa chứng minh login hoạt động**, một `MockMvc` integration test xanh chưa chứng minh trình duyệt xử lý cookie hoặc form đúng, và một browser test xanh cũng chưa chứng minh mọi nhánh của chính sách phân quyền ở service đều được kiểm.

Bài này thuộc nhóm **Kiểm thử**, tập trung vào việc chọn cấp độ test phù hợp cho từng yêu cầu bảo mật:

- **Unit test:** kiểm một hàm/class nhỏ, như role mapper, validator, `AuthorizationManager` hoặc logic kiểm sở hữu đối tượng. Không cần HTTP socket hay browser, có thể chạy thuần Java/JUnit. Chứng minh **quy tắc đang test** đúng với fixture đã cho.
- **Integration test:** kiểm nhiều thành phần chạy cùng nhau, chẳng hạn `SecurityFilterChain`, `UserDetailsService`, password encoder, controller, CSRF và endpoint. `MockMvc` dùng Servlet request/response giả nhưng có thể chạy security filters thật; `@SpringBootTest(RANDOM_PORT)` mở server và HTTP socket thực. Chứng minh **wiring/pipeline của test context**.
- **Browser E2E / UI test:** mở Chromium, Firefox hoặc WebKit bằng Playwright/Selenium, tương tác DOM, nhập form, follow redirects, lưu/gửi session cookie, thực thi JavaScript và browser policies. Chứng minh **user journey trên trình duyệt và môi trường đã chọn**.

Ba lớp có giá trị bổ sung, không phải cấp cao hơn thay toàn bộ cấp dưới. Browser test tốn thời gian và dễ phụ thuộc môi trường, còn unit test rẻ, nhanh và dễ debug nhưng không phát hiện được HTML form thiếu CSRF token hoặc cookie `SameSite` sai.

### Ranh giới bằng chứng

| Câu hỏi | Unit | Spring integration | Browser |
| --- | --- | --- | --- |
| Quy tắc “Alice không đọc dữ liệu Bob” đúng không? | Có, tại hàm policy | Có, nếu endpoint gọi policy | Có thể kiểm một journey |
| User/password thực sự được provider xác minh? | Chỉ nếu test provider | Có khi chạy authentication filters và provider thật | Có nếu server không mock authentication |
| Anonymous được redirect tới login? | Không | Có thể assert HTTP 302/Location | Có thể thấy browser thực chuyển trang |
| HTML login có render đúng? | Không | Có thể inspect response HTML | Có thể thấy/interact DOM |
| Form gửi CSRF token hợp lệ từ HTML thật? | Không | `with(csrf())` chỉ cấp token giả hợp lệ | Có nếu test submit form từ DOM |
| Cookie được browser lưu qua reload? | Không | Chỉ kiểm các header/session ở HTTP layer | Có |
| JavaScript/CORS/SameSite behavior? | Không | Có thể kiểm server headers/policy | Có với browser/origin thật |
| TLS/proxy/IdP production chắc chắn đúng? | Không | Không nếu không kết nối chúng | Không nếu browser chỉ chạy localhost/stub |

**Đặc biệt:** `@WithMockUser` và `with(user("ghost"))` cung cấp một principal đã xác thực cho test, ngay cả khi tài khoản `ghost` không tồn tại. Đây là cách kiểm **authorization**, không phải cách kiểm password, JWT signature hoặc OAuth2 login flow.

## 2. Mô hình các cấp kiểm thử theo luồng request

```text
UNIT (không cần Spring)
  OwnerPolicy.canRead("alice","bob") -> false

MOCKMVC INTEGRATION (mock Servlet, filters thật trong test context)
  MockMvc request
    -> FilterChainProxy / SecurityFilterChain
    -> UsernamePasswordAuthenticationFilter / CsrfFilter
    -> AuthenticationManager -> UserDetailsService + PasswordEncoder
    -> AuthorizationFilter -> Controller -> OwnerPolicy
    -> MockHttpServletResponse

HTTP INTEGRATION (server thực, client HTTP)
  TestRestTemplate / RestClient
    -> localhost:RANDOM_PORT -> embedded server -> security chain

BROWSER E2E (browser engine thực)
  Chromium -> GET /dashboard
           -> redirect /login
           -> HTML login form + CSRF
           -> submit username/password
           -> session cookie, redirect
           -> render dashboard
           -> submit form POST + CSRF, reload, logout
```

Trong cả ba tầng, chỉ được tuyên bố hành vi mà test **thực sự chạy**. Ví dụ nếu bạn dùng `@MockitoBean JwtDecoder` và lập trình nó luôn trả JWT hợp lệ, request Bearer integration test không xác minh được chữ ký token, dù nó vẫn đi qua một phần security chain.

## 3. Tình huống xuyên suốt và ma trận test

Giả sử ứng dụng có yêu cầu:

- `GET /` mở cho anonymous.
- `GET /dashboard` chỉ cho người đã đăng nhập.
- `POST /preferences` cho người đăng nhập đổi nickname, yêu cầu CSRF token.
- `GET /documents/{owner}` chỉ cho principal khớp owner.
- Tài khoản demo `alice` có password `correct-password`, còn `ghost` không tồn tại.

| Yêu cầu cần kiểm | Lớp ưu tiên | Case âm cần có |
| --- | --- | --- |
| Quy tắc owner | Unit | Alice truy cập document Bob, thiếu principal |
| Endpoint bảo vệ dashboard | MockMvc | Anonymous bị redirect login |
| Authentication form | MockMvc qua provider thật | Password sai, username không tồn tại |
| CSRF filter | MockMvc | POST thiếu token bị 403 |
| Controller gọi owner policy | MockMvc | User đã login vẫn bị 403 với owner khác |
| Form login hiển thị và submit đúng | Browser | Sai password không vào dashboard |
| Session cookie có tác dụng | Browser | Browser context mới vẫn anonymous |
| CSRF field từ template thật | Browser | Form không token không thể hoàn thành update |
| Production HTTPS/cookies/cross-origin | Staging browser + config tests | Cookie `Secure`/`SameSite` sai, CORS preflight fail |

Một browser test đơn lẻ không nên ôm hết thuật toán phân quyền của toàn hệ thống; những nhánh phức tạp ở service nên được unit/integration test chi tiết hơn.

## 4. Dự án ví dụ Java 17+ với cả ba nhóm test

Mã sau dùng **Spring Boot 3.5.7, Spring Security 6.x, Spring MVC, Thymeleaf, JUnit 5 và Playwright Java 1.64.0**. Tài khoản và trạng thái nickname nằm in-memory để ví dụ lặp lại dễ dàng; không thay cho database, secrets và session cluster production.

Cấu trúc:

```text
security-test-levels/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/SecurityTestLevelsApplication.java
    │   ├── java/demo/OwnerPolicy.java
    │   └── resources/templates/dashboard.html
    └── test/java/demo/
        ├── OwnerPolicyTest.java
        ├── SecurityIntegrationTest.java
        └── BrowserFlowTest.java
```

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-test-levels</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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
        <dependency>
            <groupId>com.microsoft.playwright</groupId>
            <artifactId>playwright</artifactId>
            <version>1.64.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven `<plugins>` đã chứa **hai phần tử `<plugin>` đóng/mở đầy đủ**. Plugin exec phục vụ cài browser binaries; dependency Playwright ở `test` scope nên lệnh CLI dùng `exec.classpathScope=test`.

### 4.2. Unit được kiểm: `src/main/java/demo/OwnerPolicy.java`

```java
package demo;

public final class OwnerPolicy {
    private OwnerPolicy() {}

    public static boolean canRead(String principal, String owner) {
        return principal != null && principal.equals(owner);
    }
}
```

Policy này cố tình đơn giản để minh họa sự khác nhau giữa **đúng logic** và **đúng wiring**. Ở hệ thống thật, hãy so stable user ID, tenant và quyền trên đối tượng từ DB, không tin `owner` do client tự khai báo.

### 4.3. Spring application: `src/main/java/demo/SecurityTestLevelsApplication.java`

```java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class SecurityTestLevelsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityTestLevelsApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUser(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("correct-password"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/").permitAll()
                        .requestMatchers(
                                "/dashboard",
                                "/preferences",
                                "/documents/**").authenticated()
                        .anyRequest().denyAll())
                .formLogin(form -> form.permitAll())
                .logout(logout -> logout.permitAll())
                .build();
    }

    @Controller
    static class Pages {
        private final Map<String, String> nicknames =
                new ConcurrentHashMap<>();

        @GetMapping("/")
        @ResponseBody
        String publicPage() {
            return "Public home";
        }

        @GetMapping("/dashboard")
        String dashboard(Authentication auth, Model model) {
            String username = auth.getName();
            model.addAttribute("username", username);
            model.addAttribute(
                    "nickname",
                    nicknames.getOrDefault(username, "(none)"));
            return "dashboard";
        }

        @PostMapping("/preferences")
        String changeNickname(Authentication auth,
                              @RequestParam String nickname) {
            String cleaned = nickname.strip();
            if (cleaned.isBlank() || cleaned.length() > 50) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
            }
            nicknames.put(auth.getName(), cleaned);
            return "redirect:/dashboard";
        }

        @GetMapping("/documents/{owner}")
        @ResponseBody
        String document(Authentication auth,
                        @PathVariable String owner) {
            if (!OwnerPolicy.canRead(auth.getName(), owner)) {
                throw new ResponseStatusException(HttpStatus.FORBIDDEN);
            }
            return "Document for " + owner;
        }
    }
}
```

Giải thích: `SecurityFilterChain` bảo vệ URL, `formLogin` khai báo quy trình đăng nhập chuẩn, `logout` cho phép logout chuẩn; **không tắt CSRF**. User chỉ có `alice`, password hash tạo bằng `DelegatingPasswordEncoder`; login sai buộc đi qua filter/provider. `OwnerPolicy` được controller thực sự gọi khi lấy document. Nickname giữ bằng `ConcurrentHashMap` chỉ để có observable state; production cần DB/transaction.

### 4.4. Template: `src/main/resources/templates/dashboard.html`

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Security Test Dashboard</title>
</head>
<body>
    <h1 id="greeting" th:text="|Dashboard: ${username}|">
        Dashboard
    </h1>
    <p id="nickname" th:text="|Nickname: ${nickname}|">
        Nickname
    </p>

    <form id="preferences" method="post"
          th:action="@{/preferences}">
        <label for="nicknameInput">Nickname</label>
        <input id="nicknameInput" name="nickname"
               maxlength="50" required>
        <button id="save" type="submit">Save</button>
    </form>

    <form id="logoutForm" method="post" th:action="@{/logout}">
        <button id="logout" type="submit">Logout</button>
    </form>
</body>
</html>
```

`th:action` cho form POST được tích hợp với `RequestDataValueProcessor` để Spring Security thêm hidden `_csrf` field khi render. Browser test sẽ kiểm DOM sau khi render rồi submit form thật; `@Valid` hoặc `with(csrf())` trong test riêng không chứng minh được template đã sinh token. `th:text` escape text; không dùng `th:utext` với input không tin cậy.

## 5. Unit test: kiểm policy mà không có Spring, HTTP hoặc browser

`src/test/java/demo/OwnerPolicyTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class OwnerPolicyTest {

    @Test
    void ownerCanReadOwnDocument() {
        assertThat(OwnerPolicy.canRead("alice", "alice")).isTrue();
    }

    @Test
    void aliceCannotReadBobDocument() {
        assertThat(OwnerPolicy.canRead("alice", "bob")).isFalse();
    }

    @Test
    void missingIdentityCannotRead() {
        assertThat(OwnerPolicy.canRead(null, "alice")).isFalse();
    }
}
```

Unit tests chứng minh logic `canRead` với dữ liệu đã chọn. Nó không kiểm xem endpoint có gọi policy, không tạo session, không kiểm mật khẩu hoặc filter. Khi logic quyền lớn hơn, viết unit tests cho role/scope mapper, expiration validators, multi-tenant policy, object owner và trạng thái tài khoản với cả case fail-closed.

## 6. Integration test: `MockMvc` chạy Spring Security filters

`src/test/java/demo/SecurityIntegrationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class SecurityIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void publicPageIs200() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public home"));
    }

    @Test
    void anonymousDashboardRedirectsToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    @WithMockUser(username = "ghost", roles = "USER")
    void mockGhostMaySeeDashboard() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().isOk());
    }

    @Test
    void ownerIsAllowedButOtherUserDenied() throws Exception {
        mvc.perform(get("/documents/alice")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("Document for alice"));

        mvc.perform(get("/documents/bob")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void realFormProviderAcceptsCorrectPassword() throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("correct-password"))
                .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void wrongPasswordRejected() throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("wrong-password"))
                .andExpect(unauthenticated());
    }

    @Test
    void unknownUserRejected() throws Exception {
        mvc.perform(formLogin()
                        .user("ghost")
                        .password("anything"))
                .andExpect(unauthenticated());
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/preferences")
                        .with(user("alice").roles("USER"))
                        .param("nickname", "Invalid"))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfCanUpdate() throws Exception {
        mvc.perform(post("/preferences")
                        .with(user("alice").roles("USER"))
                        .with(csrf())
                        .param("nickname", "Valid"))
                .andExpect(status().is3xxRedirection());
    }
}
```

**Điều các test này chứng minh và chưa chứng minh:**

- `@WithMockUser("ghost")` cấp principal không có trong user store, **không** làm password validation. Test 200 chỉ xác minh rule yêu cầu authenticated.
- `with(user("alice"))` tạo principal mock cho request để kiểm policy/CSRF; nó không kiểm user tồn tại.
- `formLogin()` tạo POST login có valid CSRF token; khi filters thật được gắn trong Spring context, `AuthenticationManager`/provider/encoder kiểm username và password. Test sai password/username có giá trị khác `@WithMockUser`.
- `with(csrf())` thêm test token. Nó kiểm filter chấp nhận token, **chưa kiểm HTML form sinh token**.
- `@AutoConfigureMockMvc(addFilters = true)` giữ filters. Nếu tắt filters hoặc dùng `standaloneSetup` thiếu `springSecurity()`, test có thể bỏ qua bảo vệ.
- Dù không mở HTTP port, test này là **integration** vì Spring context, controller, filter chain, user store và authorization được phối hợp.

## 7. Browser test: Playwright với HTTP server và Chromium thật

`src/test/java/demo/BrowserFlowTest.java`:

```java
package demo;

import com.microsoft.playwright.Browser;
import com.microsoft.playwright.BrowserContext;
import com.microsoft.playwright.BrowserType;
import com.microsoft.playwright.Page;
import com.microsoft.playwright.Playwright;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BrowserFlowTest {

    @LocalServerPort
    int port;

    @Test
    void browserFollowsLoginAndKeepsSession() {
        String base = "http://localhost:" + port;

        try (Playwright playwright = Playwright.create()) {
            Browser browser = playwright.chromium().launch(
                    new BrowserType.LaunchOptions().setHeadless(true));
            BrowserContext signedIn = browser.newContext();
            Page page = signedIn.newPage();

            page.navigate(base + "/dashboard");
            assertThat(page.url()).contains("/login");

            // Spring Security sinh form login mặc định.
            page.locator("input[name='username']").fill("alice");
            page.locator("input[name='password']")
                    .fill("correct-password");
            page.locator("button[type='submit']").click();
            page.waitForURL("**/dashboard");

            assertThat(page.locator("#greeting").innerText())
                    .isEqualTo("Dashboard: alice");

            // Kiểm hidden field do view integration tạo ra.
            assertThat(
                    page.locator("#preferences input[name='_csrf']").count())
                    .isEqualTo(1);

            // Browser gửi cookie và CSRF khi submit form thực.
            page.locator("#nicknameInput").fill("Browser verified");
            page.locator("#save").click();
            page.waitForURL("**/dashboard");
            assertThat(page.locator("#nickname").innerText())
                    .isEqualTo("Nickname: Browser verified");

            page.reload();
            assertThat(page.locator("#greeting").innerText())
                    .isEqualTo("Dashboard: alice");

            // Context khác chưa được đăng nhập.
            BrowserContext anonymous = browser.newContext();
            Page newcomer = anonymous.newPage();
            newcomer.navigate(base + "/dashboard");
            assertThat(newcomer.url()).contains("/login");

            anonymous.close();
            signedIn.close();
            browser.close();
        }
    }

    @Test
    void browserRejectsWrongPassword() {
        String base = "http://localhost:" + port;

        try (Playwright playwright = Playwright.create()) {
            Browser browser = playwright.chromium().launch(
                    new BrowserType.LaunchOptions().setHeadless(true));
            Page page = browser.newPage();

            page.navigate(base + "/login");
            page.locator("input[name='username']").fill("alice");
            page.locator("input[name='password']").fill("wrong");
            page.locator("button[type='submit']").click();
            page.waitForURL("**/login?error");

            assertThat(page.url()).contains("/login?error");
            browser.close();
        }
    }
}
```

Browser test này kiểm thứ mà `MockMvc` không thể tự tái hiện: DOM login thật, click form, redirect tự động, browser session cookie, HTML view CSRF hidden field, form POST từ trang thực và context cô lập. Nó không chứng minh cấu hình production TLS/proxy hay tất cả browsers, vì app test chạy local HTTP với in-memory user store.

## 8. Lệnh build, cài Chromium và chạy test

Yêu cầu Java 17+, Maven, OS/libraries phù hợp Playwright. Từ thư mục chứa `pom.xml`:

```bash
mvn -q -DskipTests test-compile
mvn -q exec:java -Dexec.mainClass=com.microsoft.playwright.CLI -Dexec.args="install chromium" -Dexec.classpathScope=test
mvn -q test
mvn -q -DskipTests package
java -jar target/security-test-levels-0.0.1-SNAPSHOT.jar
```

Bước cài Chromium cần chạy trước test browser và có thể đòi system dependencies trong CI/Linux. Nếu binary thiếu, `BrowserFlowTest` sẽ thất bại khi launch; đó là lỗi môi trường chứ chưa chứng minh logic bảo mật sai.

Chạy riêng:

```bash
mvn -q -Dtest=OwnerPolicyTest test
mvn -q -Dtest=SecurityIntegrationTest test
mvn -q -Dtest=BrowserFlowTest test
```

Sau `java -jar`, mở `http://localhost:8080/dashboard`, bạn được redirect sang `/login`. Dùng user `alice` / password `correct-password`; sau login thấy dashboard và form đổi nickname. Không dùng credentials demo hoặc HTTP chưa mã hóa cho production.

## 9. HTTP integration test với `RANDOM_PORT` vẫn không phải browser

Khi chỉ cần status/header/body thật, `TestRestTemplate` hoặc HTTP client kết hợp `@SpringBootTest(webEnvironment = RANDOM_PORT)` thường đủ, nhẹ hơn Playwright:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpStatusExample {

    @Autowired TestRestTemplate client;

    @Test
    void publicEndpointServesHttp() {
        ResponseEntity<String> response =
                client.getForEntity("/", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .isEqualTo("Public home");
    }
}
```

Đây là **fragment** (cần imports và project context). Nó gửi request vào embedded server qua HTTP socket. Nhưng client không render DOM, không chạy JavaScript hay browser cookie policy. Nếu kiểm redirect 302/Location, phải biết HTTP client có tự follow redirect hay không và cấu hình rõ. Với `RANDOM_PORT`, test thread và server thread khác nhau: `@Transactional` ở test method không tự rollback các transaction do request bên server tạo ra; cần data cleanup có chủ đích.

## 10. Các tình huống cần browser test thực sự

### Form login và cookie

Browser xử lý `SameSite`, `Secure`, `HttpOnly`, `Domain`, `Path`, session cookie, redirect và back navigation. `MockMvc` kiểm được Set-Cookie và response status nhưng không mô phỏng mọi chính sách browser. Dùng staging qua HTTPS/domain thật khi test cookie `Secure`/SameSite, reverse proxy hoặc cross-site redirect; localhost HTTP không giống production.

### CSRF từ HTML hoặc SPA

`with(csrf())` xác minh filter chấp nhận token test; browser test mới kiểm form render token, DOM click và thực sự gửi nó. SPA có thể dùng header thay hidden input. Không tắt CSRF theo thói quen; xác định app dùng cookie/session, Basic hoặc Bearer và browser tự gửi credentials thế nào.

### CORS và JavaScript

CORS được browser thực thi, `curl` không chặn response theo origin. Browser test đa-origin có thể phát hiện preflight OPTIONS, cookie credentials, allowed origins và fetch failures. CORS không phải cơ chế authorization, không sửa bằng `permitAll("/**")`. CSP, SPA routing, WebAuthn và lỗi script cũng thường chỉ thấy rõ ở browser.

### OAuth2/OIDC và SSO

`oauth2Login()` hoặc `oidcLogin()` postprocessor tạo principal giả, không test `state`, `nonce`, redirect URI, token endpoint, signature và session thực. Browser test với IdP stub có giá trị cho callback/redirect; staging IdP thật có độ tin cậy cao hơn cho tích hợp, nhưng cần test account riêng. Không sử dụng quyền production chỉ để chạy E2E.

### Authorization theo đối tượng

Frontend ẩn link `/documents/bob` không ngăn Alice tự gửi request. Phải có unit/integration test tại server chứng minh 403/404 đúng; browser test là bổ sung, không thay object-level authorization tests.

## 11. JWT và WebFlux: giữ nguyên nguyên tắc phân tầng

**Resource Server JWT:** unit test `JwtAuthenticationConverter`, claims → roles/scopes và validators; integration test request Bearer chứa token **được ký** qua `BearerTokenAuthenticationFilter`/`JwtDecoder` thật để thử signature đúng/sai, `iss`, `exp`, `nbf`, `aud` khi có audience policy; browser test SPA/OIDC nếu có giao diện liên quan.

`with(jwt())` hoặc `jwt()` helper thường cấp `JwtAuthenticationToken` đã có authorities cho request, **không tự verify chữ ký**. Nếu `JwtDecoder` đã bị mock cho luôn valid, integration test đó không kiểm crypto. Phân biệt status: token sai 401; token hợp lệ nhưng thiếu authority 403; hợp lệ và đủ quyền 200 (theo policy của ứng dụng).

**WebFlux/reactive:** thay Servlet `SecurityFilterChain` bằng `SecurityWebFilterChain`, dùng `WebTestClient` và `mockUser()`/`mockJwt()` cho policy; một test reactive client vẫn không thực thi browser DOM/JS. Ví dụ fragment (không chạy độc lập):

```java
client.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/dashboard")
        .exchange()
        .expectStatus().isOk();
```

Nó cần import `mockUser` từ `SecurityMockServerConfigurers` và `WebTestClient` đã cấu hình security. Nó chứng minh behavior với principal giả, không kiểm password.

## 12. Chiến lược kiểm thử không bỏ sót và không quá tốn kém

| Nhóm hành vi | Unit | Integration | Browser |
| --- | --- | --- | --- |
| Role/scope/tenant/owner policy | Nhiều edge cases | Endpoint allowed/denied | Journey đại diện |
| Password và account state | Provider/encoder khi cần | Đúng/sai/khóa user | Login success/failure |
| CSRF | Ít cần thuần unit | POST thiếu/sai/đúng token | Form render/submit |
| Session/login/logout | Handler/policy | Session create/invalidate | Reload/new context/logout |
| JWT | Claim/validator | Signed token và decoder thật | SPA/SSO flow nếu có |
| CORS | Origin policy | Preflight/header | Cross-origin fetch |
| UI | View-model | HTML/status/redirect | DOM/click/navigation |
| IDOR/BOLA | Logic sở hữu | User A đọc ID của B bị cấm | Có thể bổ sung một journey |

Cho phần lớn thay đổi, chạy unit tests liên tục, integration suite ở CI, và browser smoke tests trên critical journeys. Với feature quan trọng như thanh toán hoặc đổi mật khẩu, mở rộng browser/SSO staging tests theo rủi ro. Khi browser test bắt lỗi, thêm regression test thấp hơn nếu tái hiện được, để giảm flakiness.

**Tránh test flaky:** browser contexts và fixtures độc lập, không hardcode sleep, dùng locator ổn định và `page.waitForURL`, version browser đúng Playwright, không chạy song song test cùng sửa một account nếu chưa cô lập. Khi ghi screenshots/traces/logs trong CI, che password, PII, bearer token, session cookie và CSRF token.

**Đặt tên theo bằng chứng:** `ownerPolicyRejectsDifferentUser`, `wrongPasswordRejectedByFormProvider` và `browserPreservesSessionAfterReload` tốt hơn `securityWorks`. Báo cáo rõ dependency nào bị mock để không diễn giải quá mức.

## 13. Lỗi phổ biến trong code review và kiểm thử

1. Chỉ dùng `@WithMockUser` và kết luận login hoạt động: không kiểm credential.
2. Bỏ filters để hết 403: test có thể bỏ qua toàn bộ Spring Security.
3. Coi mọi `@WebMvcTest` giống production: có thể thiếu service/provider hoặc dùng mock.
4. Coi `MockMvc` là unit test chỉ vì không mở port: bỏ qua bản chất integration.
5. Coi HTTP client `RANDOM_PORT` là browser E2E: không chạy DOM/JS/cookie engine.
6. Tưởng `with(csrf())` pass chứng minh HTML có token: request postprocessor tự cung cấp.
7. Chỉ test happy path, thiếu password sai/CSRF sai/thiếu quyền/owner khác.
8. Dùng `jwt()` có role mock để kết luận JWT signature và issuer đã kiểm.
9. Browser localhost pass rồi suy luận cookie Secure/proxy production chắc đúng.
10. Chỉ kiểm UI ẩn nút thay cho authorization tại backend.
11. Dựa vào rollback `@Transactional` test thread khi server RANDOM_PORT ghi DB.
12. Log screenshots/traces chứa session cookies và credentials thật.
13. Browser tests phụ thuộc thứ tự hoặc `Thread.sleep` cố định làm kết quả flaky.
14. Browser test thành công với IdP giả nhưng tuyên bố IdP production ổn.
15. Không đọc 401/403/302, header, cookie, body hoặc hậu quả state thực.
16. Thiếu negative tests cho token expired, issuer/audience sai, role không đủ.
17. Tạo mock `AuthenticationManager` chấp nhận mọi mật khẩu rồi gọi đó là authentication integration test.
18. Chỉ kiểm phân quyền URL, bỏ qua service/object/tenant authorization.

## 14. Câu hỏi tự luyện

1. Một test `@WithMockUser(username="ghost",roles="ADMIN")` được 200, nhưng DB không có ghost. Nó chứng minh điều gì?
2. Vì sao `with(user("alice"))` không bằng `formLogin().user("alice").password("correct-password")`?
3. `MockMvc` có thể kiểm đúng hành vi nào dù không mở HTTP socket?
4. Vì sao browser test bắt được lỗi CSRF form mà `post(...).with(csrf())` không phát hiện?
5. Khi nào cần `@SpringBootTest(RANDOM_PORT)` + HTTP client thay vì Playwright?
6. Khi user login thành công nhưng refresh trở lại login, nghi ngờ những vấn đề cookie/session nào?
7. `jwt()` helper có kiểm signature/issuer/audience không? Viết các test cần bổ sung.
8. Vì sao frontend không render link tới tài liệu của Bob không đủ ngăn Alice GET đường dẫn đó?
9. Nếu `curl` gọi API thành công nhưng browser báo CORS, tầng nào giúp tái hiện thực?
10. `@Transactional` ở test thread có tự rollback transaction từ server RANDOM_PORT không?
11. Hãy lập ma trận 3 unit, 5 integration và 2 browser cases cho một ứng dụng có form login.
12. Một browser test với IdP stub có chứng minh SSO production đúng không? Vì sao?

## 15. Tài liệu tra cứu chính thức

- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html)
- [Spring Security — Running as a User](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security — Setting Up MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Playwright Java — Installation](https://playwright.dev/java/docs/intro)
- [Playwright Java — Browser binaries](https://playwright.dev/java/docs/browsers)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)

**Tóm lại:** unit test hỏi **logic đúng không**; integration test hỏi **Spring Security và các thành phần kết nối đúng không**; browser E2E hỏi **người dùng có thật sự hoàn thành luồng trên trình duyệt không**. Không lấy một test 200 hoặc một principal giả làm bằng chứng an toàn toàn diện.
