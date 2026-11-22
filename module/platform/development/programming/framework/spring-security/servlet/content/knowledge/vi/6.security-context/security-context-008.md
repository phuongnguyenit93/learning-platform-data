# Cơ chế explicit save và trách nhiệm lưu ngữ cảnh khi đăng nhập tùy chỉnh

> **Phạm vi:** Spring Security 6 trên **Servlet stack** (Spring Boot 3.x, Java 17+). Chủ đề thuộc **Ngữ cảnh bảo mật**: vì sao việc đặt `Authentication` vào `SecurityContextHolder` mới chỉ xác thực cho request hiện tại, cách `SecurityContextRepository` lưu ngữ cảnh qua các request và trách nhiệm phát sinh khi tự xây dựng luồng đăng nhập. Cơ chế trong WebFlux dùng `ReactiveSecurityContextHolder` và các repository phản ứng, không áp dụng nguyên mẫu Servlet này.

## 1. Vấn đề: đăng nhập thành công trong một request nhưng request sau lại mất phiên

Giả sử ứng dụng có endpoint tự viết `POST /custom-login`, nhận tài khoản và mật khẩu rồi thực hiện:

```java
// Đoạn minh họa, cần đặt trong lớp controller/service có đủ dependency.
Authentication auth = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(username, password));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(auth);
SecurityContextHolder.setContext(context);
```

Ngay sau đó, trong **cùng request**, gọi `SecurityContextHolder.getContext().getAuthentication()` có thể trả về người dùng vừa xác thực. Nhưng request HTTP **tiếp theo** đi vào một thread/request mới; khi Spring Security dùng cơ chế **explicit save**, không có gì bảo đảm context này đã được ghi vào session hoặc một kho lưu trữ bền qua request.

Đó là lý do lỗi sau thường xuất hiện:

```text
POST /custom-login  -> 200 OK ("login succeeded")
GET  /me            -> 401 Unauthorized
```

Nguyên nhân có thể là controller đã **set context nhưng quên gọi `saveContext(...)`**, hoặc ứng dụng dùng chính sách stateless/không lưu session. Thành công của `AuthenticationManager.authenticate(...)` và trạng thái xác thực được lưu qua nhiều request là **hai bước khác nhau**.

**Mệnh đề cần nhớ:** `SecurityContextHolder.setContext(...)` thay đổi trạng thái truy cập trong luồng request; `SecurityContextRepository.saveContext(...)` mới yêu cầu lưu ngữ cảnh theo repository được cấu hình. Riêng phương thức `authenticate(...)` không tự lưu context chỉ vì nó trả về `Authentication` hợp lệ.

## 2. Những đối tượng tham gia và trách nhiệm

| Thành phần | Chức năng | Không tự làm điều gì? |
| --- | --- | --- |
| `AuthenticationManager` | Xác thực credentials bằng provider phù hợp và trả về `Authentication` | Không tự gắn authentication vào holder/session cho mọi cách gọi tùy chỉnh |
| `SecurityContext` | Chứa `Authentication` của ngữ cảnh bảo mật | Không tự tạo HTTP session |
| `SecurityContextHolder` | Cung cấp context cho request/thread đang xử lý qua `SecurityContextHolderStrategy` | Không phải database/session repository; thay đổi ở đây không mặc định bền qua request |
| `SecurityContextHolderFilter` | Lấy context (có thể deferred) từ repository cho request, đưa vào holder và dọn holder khi request hoàn tất | Ở chế độ explicit save, **không tự lưu** context đã thay đổi khi response kết thúc |
| `SecurityContextRepository` | Đọc và lưu context thông qua `loadDeferredContext`/`saveContext` | Không tự xác thực mật khẩu hay quyết định quyền truy cập |
| `HttpSessionSecurityContextRepository` | Lưu context trong `HttpSession` khi cấu hình và điều kiện cho phép | Không hoạt động như persistence xuyên request khi ứng dụng dùng chính sách stateless phù hợp |
| `RequestAttributeSecurityContextRepository` | Giữ context trong request attributes, hỗ trợ những dispatch liên quan trong cùng request | Không dùng để lưu đăng nhập qua các HTTP request độc lập |
| `DelegatingSecurityContextRepository` | Ủy quyền cho nhiều repository, thường kết hợp request attributes và HTTP session | Không biến `SecurityContextHolder` thành kho lưu tự động |

Trên Servlet stack, Spring Security 6 thường dùng `SecurityContextHolderFilter` với hành vi **yêu cầu lưu tường minh**. Cơ chế legacy dựa trên `SecurityContextPersistenceFilter` có thể tự ghi context lúc kết thúc request; không nên dựa vào hành vi legacy khi viết luồng authentication tùy chỉnh cho cấu hình hiện tại.

### Ngữ cảnh được lấy lại ở request tiếp theo ra sao?

```text
Request 1: POST /custom-login
    |
    +-- SecurityContextHolderFilter lấy context ban đầu
    +-- Controller gọi AuthenticationManager.authenticate(...)
    +-- Tạo SecurityContext mới, đặt Authentication đã xác thực
    +-- SecurityContextHolderStrategy.setContext(context)
    +-- SecurityContextRepository.saveContext(context, request, response)
    |      |
    |      +-- HttpSessionSecurityContextRepository ghi vào session
    |      +-- Response có thể phát Set-Cookie session ID
    |
    +-- response hoàn tất; holder của request được dọn

Request 2: GET /me + session cookie
    |
    +-- SecurityContextHolderFilter dùng repository để nạp context
    +-- AuthorizationFilter nhận Authentication đã lưu
    +-- Controller thấy người dùng hợp lệ
```

Nếu bỏ lệnh `saveContext(...)` trong request đầu, context chỉ có thể còn trong request đó; request tiếp theo không có `Authentication` đã được lưu trong session để nạp lại.

## 3. Explicit save trong Spring Security 6

Với `HttpSecurity`, chế độ lưu tường minh có thể được thể hiện như sau:

```java
http.securityContext(security -> security
        .requireExplicitSave(true)
        .securityContextRepository(securityContextRepository));
```

Đoạn này **chỉ là một phần cấu hình**, phải được đặt trong cấu hình `HttpSecurity` hợp lệ. Trong Spring Security 6, `requireExplicitSave(true)` là hướng vận hành mặc định thường gặp của filter quản lý ngữ cảnh. Tùy dự án nâng cấp từ bản cũ, hãy kiểm tra chain và filter được cấu hình thực tế.

Với chế độ này:

1. **Đầu request:** `SecurityContextHolderFilter` chuẩn bị context từ repository; việc load có thể trì hoãn tới khi code thực sự truy cập holder.
2. **Trong request:** một filter, controller hoặc cơ chế authentication có thể thay `Authentication` trong context.
3. **Khi authentication thành công:** **bên thực hiện authentication tùy chỉnh** phải quyết định cách lưu và gọi `SecurityContextRepository.saveContext(...)` khi muốn trạng thái tiếp tục ở request sau.
4. **Cuối request:** filter dọn context khỏi holder/chiến lược tương ứng để tránh rò rỉ trạng thái khi thread được tái sử dụng. Việc dọn này **không đồng nghĩa** với xóa dữ liệu đã được lưu trong session.

Điều này không có nghĩa mọi ứng dụng Spring Security 6 phải tự gọi `saveContext` tại controller. Các cơ chế framework chuẩn như form login được xây dựng bằng authentication filters có thể **tự lưu context sau khi xác thực thành công**. Trách nhiệm bổ sung xuất hiện khi **tự viết** logic authentication nằm ngoài cơ chế đã xử lý việc này.

### Tại sao không sửa đối tượng SecurityContext có sẵn rồi trông chờ tự lưu?

Ví dụ:

```java
// Không phải quy trình đăng nhập đầy đủ:
SecurityContextHolder.getContext().setAuthentication(auth);
```

Lời gọi trên không tạo ra bảo đảm repository sẽ ghi context. Khi chuyển danh tính của request, nên tạo `SecurityContext` mới, gắn `Authentication` hợp lệ, đặt vào holder và **save theo repository**. Việc tạo context mới cũng giảm rủi ro thay đổi cùng một đối tượng context được chia sẻ ngoài ý muốn.

## 4. Gọi saveContext như thế nào cho đúng?

Mẫu cốt lõi khi tự xử lý đăng nhập trong Servlet:

```java
// Đoạn mã minh họa nằm trong luồng xử lý HTTP,
// sau khi đã kiểm tra CSRF và hoàn tất các chính sách session.
Authentication authentication = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(username, password));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
```

Ba tham số của `saveContext` là **context cần lưu**, `HttpServletRequest` và `HttpServletResponse` hiện tại. Truyền response là quan trọng khi repository có thể cần tạo/cập nhật session cookie trước khi response commit.

**Thứ tự thực hiện đúng ý tưởng:** xác thực thành công → xử lý các chiến lược session authentication cần thiết → tạo/đặt context → lưu context → trả response hoặc redirect. Đừng gọi `sendRedirect`, flush body hoặc commit response **trước** khi repository có cơ hội lưu, vì lúc đó header/cookie có thể không còn cập nhật được.

Nếu authentication thất bại, **không lưu** một context có authentication chưa hợp lệ như thể đăng nhập thành công. Với các luồng thay đổi tài khoản đang đăng nhập, cần xác định cách xử lý context hiện có, dọn thông tin khi cần và phản hồi lỗi thích hợp.

## 5. Ví dụ chạy được: đăng nhập tùy chỉnh có explicit save và HTTP session

Bài thực hành dùng **Java 17+, Spring Boot 3.3.5, Spring Security 6.x, Gradle 8.5**. Ta cố ý dùng một **controller tự xử lý login**, thay vì form-login filter chuẩn, để thấy rõ những trách nhiệm cần làm thủ công.

Ứng dụng có:

- `GET /csrf`: cấp CSRF token hợp lệ cho client dùng khi gọi POST.
- `POST /custom-login`: xác thực credentials, áp dụng session authentication strategy, lưu `SecurityContext` tường minh.
- `GET /me`: chỉ người đã xác thực mới gọi được, chứng minh session tồn tại qua request.
- CSRF vẫn **bật** cho POST; không tắt CSRF toàn ứng dụng để làm cho ví dụ đăng nhập “dễ chạy”.
- Session fixation được xử lý bằng đổi session ID; CSRF token cũ được làm mới sau login.

### 5.1. Cây tệp và build

```text
explicit-save-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    LoginController.java
  src/test/java/demo/
    LoginFlowTest.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'explicit-save-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Có thể dùng một Gradle wrapper tương thích để cố định môi trường build. Không cần thêm Spring WebFlux.

### 5.2. Lớp khởi động

Tệp `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 5.3. SecurityConfig: chọn repository và chính sách bảo mật

Tệp `src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import java.util.List;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfTokens) {
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfTokens)));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository contexts,
            CsrfTokenRepository csrfTokens) throws Exception {
        http.securityContext(security -> security
                .requireExplicitSave(true)
                .securityContextRepository(contexts));

        http.csrf(csrf -> csrf.csrfTokenRepository(csrfTokens));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf", "/custom-login").permitAll()
                .anyRequest().authenticated());

        // Dùng HTTP 401 ổn định để dễ kiểm tra khi chưa đăng nhập.
        http.exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, exception) ->
                        response.sendError(HttpServletResponse.SC_UNAUTHORIZED)));

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    AuthenticationManager authenticationManager(
            AuthenticationConfiguration config) throws Exception {
        return config.getAuthenticationManager();
    }
}
```

**Giải thích các lựa chọn:**

- `DelegatingSecurityContextRepository` lưu vào cả request attributes và HTTP session. `RequestAttributeSecurityContextRepository` có ích cho các dispatch liên quan trong cùng request; `HttpSessionSecurityContextRepository` phục vụ request tiếp theo qua session cookie.
- `securityContext(...requireExplicitSave(true))` thể hiện rõ contract: code authentication tùy chỉnh cần gọi repository.
- `HttpSessionCsrfTokenRepository` và `CsrfAuthenticationStrategy` giúp giữ cơ chế CSRF cho request thay đổi trạng thái, đồng thời làm mới CSRF token sau khi login. `ChangeSessionIdAuthenticationStrategy` chống session fixation bằng đổi ID của session hiện có.
- `/custom-login` được `permitAll` vì người dùng chưa đăng nhập vẫn phải truy cập được endpoint login; **permitAll không bỏ qua CSRF**.
- Mẫu dùng account phát triển `learner/study123` chỉ để thực hành cục bộ. Mật khẩu được băm BCrypt trong memory; sản phẩm thực tế phải quản lý bí mật và tài khoản bên ngoài mã nguồn, dùng HTTPS và kiểm soát thêm brute force/rate limiting.

**Tại sao có `SessionAuthenticationStrategy` riêng?** Khi dùng authentication filter có sẵn, Spring Security thường thực hiện session strategy trong lifecycle của filter đó. Controller tự gọi `AuthenticationManager` sẽ không tự động kích hoạt đầy đủ những bước ấy. Vì vậy ví dụ gọi strategy tường minh. Nếu dự án đặt giới hạn phiên đăng nhập đồng thời, dùng session registry, saved request hoặc cơ chế remember-me, luồng tùy chỉnh còn phải tích hợp các chức năng liên quan theo đúng contract; `saveContext` một mình không thay thế chúng.

### 5.4. LoginController: xử lý request và lưu context

Tệp `src/main/java/demo/LoginController.java`:

```java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LoginController {

    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository securityContextRepository;
    private final SessionAuthenticationStrategy sessionStrategy;

    public LoginController(AuthenticationManager authenticationManager,
                           SecurityContextRepository securityContextRepository,
                           SessionAuthenticationStrategy sessionStrategy) {
        this.authenticationManager = authenticationManager;
        this.securityContextRepository = securityContextRepository;
        this.sessionStrategy = sessionStrategy;
    }

    @GetMapping("/csrf")
    public String csrfToken(HttpServletRequest request) {
        // CsrfFilter đặt attribute này vào request.
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());
        return token.getToken();
    }

    @PostMapping("/custom-login")
    public ResponseEntity<String> login(@RequestParam String username,
                                        @RequestParam String password,
                                        HttpServletRequest request,
                                        HttpServletResponse response) {
        try {
            Authentication authentication = authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password));

            // Custom authentication phải tự áp dụng chính sách session.
            sessionStrategy.onAuthentication(authentication, request, response);

            SecurityContext context = SecurityContextHolder.createEmptyContext();
            context.setAuthentication(authentication);
            SecurityContextHolder.setContext(context);

            // Điểm then chốt: lưu trước khi response bị commit.
            securityContextRepository.saveContext(context, request, response);
            return ResponseEntity.ok("login-ok");
        } catch (AuthenticationException exception) {
            SecurityContextHolder.clearContext();
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body("invalid-credentials");
        }
    }

    @GetMapping("/me")
    public String me() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        return authentication.getName();
    }
}
```

**Đọc đúng thứ tự của `login(...)`:** (1) `authenticate` xác minh mật khẩu; (2) strategy thực hiện session fixation/CSRF work; (3) tạo context riêng chứa kết quả đã xác thực; (4) đưa vào holder cho request đang chạy; (5) **`saveContext(context, request, response)`** ghi context vào repository; (6) trả body. Nếu xóa riêng bước (5), test persistence qua request mới sẽ thất bại trong chế độ explicit save.

Trong ví dụ, một `AuthenticationException` như sai mật khẩu dẫn đến HTTP 401 mà không gọi `saveContext` cho authentication đó. Ứng dụng thật cần quản lý trường hợp tài khoản đang đăng nhập thử lại thất bại theo chính sách riêng; nếu cần cưỡng bức đăng xuất hoặc thu hồi session, phải thực hiện quy trình logout/invalidate rõ ràng.

**Lưu ý bảo mật:** `ResponseEntity.ok(...)` không tạo session thay cho repository. Client phải lưu/trả lại session cookie. Nếu API hoàn toàn stateless, cần thiết kế xác thực ở mỗi request thay vì dùng session persistence như ví dụ.

### 5.5. Test: chứng minh explicit save bằng hai HTTP request độc lập

Tệp `src/test/java/demo/LoginFlowTest.java`:

```java
package demo;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousRequestToProtectedEndpointIsUnauthorized() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void customLoginSavesContextForNextRequest() throws Exception {
        MvcResult result = mvc.perform(post("/custom-login")
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().isOk())
                .andExpect(content().string("login-ok"))
                .andReturn();

        HttpSession session = result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/me").session((MockHttpSession) session))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));
    }

    @Test
    void invalidPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/custom-login")
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "incorrect"))
                .andExpect(status().isUnauthorized())
                .andExpect(content().string("invalid-credentials"));
    }

    @Test
    void missingCsrfTokenRejectsPost() throws Exception {
        mvc.perform(post("/custom-login")
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().isForbidden());
    }
}
```

`customLoginSavesContextForNextRequest` là bằng chứng quan trọng: request đầu ghi context vào session; request thứ hai chỉ nhận cùng session, **không gửi lại username/password**, nhưng `/me` vẫn trả `learner`. Không dùng `@WithMockUser` để chứng minh persistence vì annotation đó có thể tạo sẵn authentication cho test, che giấu việc ứng dụng chưa lưu context.

### 5.6. Lệnh chạy và kết quả dự kiến

Từ thư mục `explicit-save-demo`:

```bash
gradle test
gradle bootRun
```

Nếu có Gradle wrapper, dùng `./gradlew test` hoặc `.\gradlew.bat test` trên Windows.

Kết quả kỳ vọng: 4 test **PASS** (mỗi test độc lập, chưa đăng nhập ở test anonymous), endpoint `/me` yêu cầu authentication khi request không có session hợp lệ.

Thử thủ công bằng terminal hỗ trợ `curl`. Lệnh đầu tạo cookie jar, lấy token từ `/csrf`:

```bash
curl -i -c cookies.txt -b cookies.txt http://localhost:8080/csrf
```

Copy **chính xác giá trị token trong body** trả về. Sau đó thay `TOKEN_FROM_CSRF` bằng token vừa nhận:

```bash
curl -i -c cookies.txt -b cookies.txt \
  -H 'X-CSRF-TOKEN: TOKEN_FROM_CSRF' \
  -d 'username=learner' -d 'password=study123' \
  http://localhost:8080/custom-login

curl -i -b cookies.txt http://localhost:8080/me
```

Ở đây `curl -c` ghi cookie mới (kể cả session ID có thể thay đổi sau login), `curl -b` gửi cookie đã lưu. Đảm bảo client dùng cùng cookie jar.

| Thao tác | HTTP status dự kiến | Response body |
| --- | --- | --- |
| `GET /me` không session hợp lệ | **401** | Tùy server |
| `GET /csrf` | **200** | Một CSRF token (giá trị thay đổi) |
| `POST /custom-login` sai password, token hợp lệ | **401** | `invalid-credentials` |
| `POST /custom-login` đúng password, token hợp lệ | **200** | `login-ok` |
| `GET /me` mang cookie session đã được lưu | **200** | `learner` |
| `POST /custom-login` không có token hợp lệ | **403** | Tùy server |

Không dự đoán trước session ID, CSRF token, tên cookie hay header `Set-Cookie` trong output: đó là giá trị runtime. Sau đăng nhập, `CsrfAuthenticationStrategy` làm token cũ hết hiệu lực; client cần gọi lại `GET /csrf` trước một POST tiếp theo.

## 6. Khi nào không nên lưu HTTP session?

### 6.1. Session-based và stateless khác nhau

| Cách vận hành | Cách khôi phục Authentication ở request sau | Vai trò của `saveContext` |
| --- | --- | --- |
| Stateful Servlet + session | Session cookie → `HttpSession` → `HttpSessionSecurityContextRepository` | **Cần** khi tự login mà muốn context bền qua request |
| Stateless API + bearer token | Mỗi request mang token; security filter xác minh và thiết lập context mới | Không dùng HTTP session như cách lưu login; xác thực lại theo token mỗi request |
| Chỉ xử lý request hiện tại | Custom authentication đặt context vào holder rồi kết thúc | Context không mặc định tồn tại ở request khác |

Nếu dùng `SessionCreationPolicy.STATELESS`, đừng trông chờ lệnh `saveContext` tự tạo một session đăng nhập bền. Chính sách stateless thường gắn với repository không lưu (`NullSecurityContextRepository`) hoặc cách lưu riêng. Không nên chữa lỗi bằng cách cưỡng bức tạo session nếu kiến trúc yêu cầu stateless.

### 6.2. RequestAttributeSecurityContextRepository không thay HttpSession

`RequestAttributeSecurityContextRepository` hữu ích để security context có thể xuất hiện trong các dispatch liên quan tới **cùng một servlet request** (ví dụ error dispatch), nhưng nó không khôi phục tài khoản trong một HTTP request độc lập sau đó. Muốn login session-based, repository phải thực sự lưu vào `HttpSession` hoặc một kho lưu có tính liên tục phù hợp.

`DelegatingSecurityContextRepository` có thể ghi sang cả hai. Khi cấu hình repository tùy chỉnh, cần dùng **cùng contract/repository** cho filter đọc context và code thực hiện `saveContext`; nếu mỗi bên dùng kho khác nhau, lưu thành công ở nơi A nhưng request sau lại đọc nơi B.

## 7. Trách nhiệm khác của custom authentication ngoài explicit save

**`saveContext` chỉ là một phần của login lifecycle.** Cơ chế đăng nhập chuẩn của Spring Security thường phối hợp nhiều thành phần; khi tự làm trong controller, phải cân nhắc từng phần sau:

1. **Session fixation protection:** đổi session ID hoặc thực hiện chiến lược tương đương sau authentication. Ví dụ dùng `ChangeSessionIdAuthenticationStrategy` để không giữ nguyên định danh session trước và sau login.
2. **CSRF protection:** với đăng nhập dựa trên session cookie, giữ CSRF protection cho request thay đổi trạng thái; có thể reset/rotate token sau login, như `CsrfAuthenticationStrategy` trong ví dụ.
3. **Session concurrency và session registry:** nếu ứng dụng giới hạn số phiên đăng nhập đồng thời, custom login phải tích hợp chính sách liên quan. Chỉ dùng `ChangeSessionIdAuthenticationStrategy` chưa đủ bảo đảm giới hạn concurrency.
4. **Remember-me, event publishing, success/failure handlers:** nếu hệ thống cần, phải có logic tương đương hoặc tận dụng authentication filters chuẩn. Gọi `AuthenticationManager` không tự kích hoạt mọi callback của một bộ lọc đăng nhập.
5. **Saved request và redirect:** trường hợp người dùng bị chuyển tới login rồi quay về URL ban đầu đòi hỏi request cache/success handler nếu dùng tương tác web; API JSON có thể không cần.
6. **Logout đúng cách:** thu hồi/trống hóa context đã lưu, vô hiệu hóa session nếu chính sách yêu cầu, và xử lý cookie/CSRF thích hợp. Chỉ `SecurityContextHolder.clearContext()` xóa state trong holder hiện tại, không chắc xóa authentication đang lưu trong session.
7. **Thông tin bí mật và lỗi đăng nhập:** không log mật khẩu, không phản hồi quá chi tiết gây lộ tài khoản tồn tại, giới hạn thử sai, dùng HTTPS để bảo vệ credentials và session cookie.

Với chức năng đăng nhập thông thường, nên tận dụng `formLogin`, OAuth2 login hoặc authentication filter phù hợp vì các thành phần đó đã tích hợp nhiều trách nhiệm trên. Tự viết khi yêu cầu của giao thức/ứng dụng đủ rõ để kiểm soát toàn bộ lifecycle.

## 8. Các lỗi thực tế và cách chẩn đoán

### 8.1. “Authentication có trong controller nhưng request tiếp theo bị 401”

Kiểm tra tuần tự:

- Có thật sự gọi `securityContextRepository.saveContext(context, request, response)` sau authentication thành công?
- Filter đầu request và controller lưu context có đang dùng cùng repository không?
- Client có lưu và gửi lại session cookie, nhất là sau đổi session ID không?
- Có `SessionCreationPolicy.STATELESS`, `NullSecurityContextRepository` hoặc một filter khác xóa session/context không?
- Authentication có thuộc loại được repository lưu (khác anonymous/empty context) không?
- `saveContext` có chạy **trước khi response commit** không? Có nhánh redirect/exception nào bỏ qua nó không?

Đừng kết luận lỗi nằm ở password encoder nếu login request đã có `Authentication` hợp lệ.

### 8.2. “Có cần gọi `session.setAttribute("SPRING_SECURITY_CONTEXT", context)` trực tiếp?”

Không nên lấy việc tự ghi session attribute làm API tích hợp chính. Dùng `SecurityContextRepository.saveContext(...)` để giữ đúng policy, lifecycle, request wrapping và cách Spring Security cấu hình repository. Ghi thủ công có thể bỏ qua cơ chế request attribute, không thống nhất với repository đang đọc hoặc bỏ qua chính sách session.

### 8.3. “Thấy `SecurityContextHolder.getContext()` trả Authentication thì chắc đã đăng nhập?”

Chỉ chứng minh trạng thái ở **request/thread hiện tại**. Holder thường dùng chiến lược gắn ngữ cảnh với thread; sau khi filter kết thúc, nó được clear. Cần request thứ hai với session cookie để xác minh context đã được lưu và nạp lại.

### 8.4. “Spring Security 6 không lưu tự động nghĩa là phải tự save ở mọi filter?”

Không. Filter authentication chuẩn của framework có thể tự gọi save khi login thành công. Chỉ code custom thực hiện xác thực riêng mới cần tự đảm trách bước này. Không dùng lệnh save rải rác ở mọi controller để che giấu một luồng authentication thiết kế sai.

### 8.5. “Đổi sang `requireExplicitSave(false)` là sửa xong?”

Đó là cách đổi contract sang hành vi legacy, không giải quyết trách nhiệm thiết kế luồng custom rõ ràng. Ứng dụng mới nên hiểu cơ chế explicit save, bảo đảm đường thành công/lỗi/session được kiểm thử và gọi đúng repository. Chỉ dùng chế độ legacy nếu có lý do tương thích cụ thể và hiểu tác động.

### 8.6. “Vì sao lưu sau redirect vẫn mất session?”

Gửi redirect hoặc commit response trước khi save có thể làm repository không tạo/cập nhật cookie kịp thời. Hãy save context khi authentication và session strategy đã hoàn tất, **trước** `sendRedirect`/flush/response commit. Với custom authentication filter, dùng success handler đúng thứ tự hoặc hook được framework hỗ trợ.

### 8.7. “Session mới đã có, sao thiếu quyền khi async hoặc dispatch lỗi?”

Không suy ra tự động rằng context sẽ lan sang mọi thread bất đồng bộ. Với tác vụ thực thi ngoài request thread, cân nhắc `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` hoặc API tương ứng để truyền đúng context khi thực sự cần. `RequestAttributeSecurityContextRepository` hỗ trợ phạm vi request/dispatch, không phải truyền context tùy ý sang background threads.

### 8.8. “Lưu context có thể vô tình giữ thông tin xác thực đã hết hạn?”

Repository lưu trạng thái authentication tại thời điểm save; ứng dụng vẫn phải quản lý logout, session timeout, account disable/revocation, thay đổi quyền và các yêu cầu re-authentication. Một session còn tồn tại không bảo đảm trạng thái account bên ngoài luôn cập nhật tức thì.

## 9. Checklist triển khai luồng đăng nhập tùy chỉnh

| Kiểm tra | Tiêu chí |
| --- | --- |
| Authentication | `AuthenticationManager.authenticate` thành công và trả identity hợp lệ |
| Context | Tạo context mới, đặt `Authentication` vào holder của request |
| Session policy | Đúng stateful/stateless; nếu stateful, xử lý session fixation và các strategy liên quan |
| Persistence | Dùng `SecurityContextRepository.saveContext` **trước khi response commit** |
| Repository consistency | Filter nạp context và code lưu context dùng cùng cấu hình repository |
| CSRF | POST login/các thao tác thay đổi trạng thái có bảo vệ CSRF khi dùng session cookie |
| Cookie | Client nhận session ID sau authentication và gửi lại ở request sau |
| Failure | Credentials sai không được lưu làm authenticated; lỗi 401/403 được phân biệt |
| Logout | Xóa/ngắt context đã lưu, session/cookie phù hợp chính sách |
| Tests | Request thứ hai không gửi lại credentials vẫn truy cập được khi session hợp lệ; request không session bị chặn |

Để tránh test đánh lừa, hãy **tách request login và request kiểm tra**, dùng cùng session cookie. Đồng thời test một request hoàn toàn mới không cookie để chắc chắn endpoint không vô tình được `permitAll`.

## 10. Tự kiểm tra

1. **Vì sao `SecurityContextHolder.setContext(context)` chưa đủ để giữ đăng nhập?** Vì holder lưu trạng thái trong phạm vi request/thread; chế độ explicit save không tự ghi ngữ cảnh vào repository khi request kết thúc.
2. **Ai chịu trách nhiệm gọi `saveContext` trong custom login?** Code thực hiện authentication thành công, trừ khi giao quyền cho một filter/framework mechanism đã xử lý việc lưu.
3. **Tại sao phải gọi `saveContext` trước khi redirect?** Repository có thể cần tạo session và cập nhật cookie/response; response đã commit làm việc này không còn an toàn.
4. **`RequestAttributeSecurityContextRepository` có lưu qua hai HTTP request khác nhau không?** Không; nó dành cho phạm vi request/dispatch. Dùng `HttpSessionSecurityContextRepository` hoặc kho phù hợp cho persistence liên request.
5. **Custom login có chỉ cần `authenticate`, `setContext`, `saveContext`?** Chưa đủ trong nhiều ứng dụng: còn session fixation, CSRF, logout, concurrency, callbacks và chính sách auth khác.
6. **Với API stateless, có nên lưu SecurityContext vào session?** Thông thường không; mỗi request phải được xác thực từ credential/token phù hợp.
7. **Test quan trọng nhất để chứng minh explicit save đúng là gì?** Login thành công trong request thứ nhất, gửi request thứ hai với cùng session nhưng **không gửi lại credentials**, kiểm tra endpoint bảo vệ nhận đúng Authentication.

**Ghi nhớ:** Trong Spring Security 6 Servlet, `SecurityContextHolderFilter` dùng repository để **nạp** context và dọn holder; chế độ **explicit save** đặt trách nhiệm **lưu** lên cơ chế authentication. Khi tự viết login, xác thực thành công → xử lý session strategy → tạo/đặt `SecurityContext` → gọi `SecurityContextRepository.saveContext(context, request, response)` **trước khi response commit**. Chỉ khi repository, session policy và cookie cùng được cấu hình phù hợp, người dùng mới duy trì được trạng thái đăng nhập ở request tiếp theo.
