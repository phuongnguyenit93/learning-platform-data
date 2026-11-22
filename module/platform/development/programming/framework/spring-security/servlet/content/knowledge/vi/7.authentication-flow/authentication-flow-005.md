# AbstractAuthenticationProcessingFilter và các bước trước, sau xác thực trong Spring Security Servlet

Trong một ứng dụng Spring MVC chạy trên Servlet stack, khi người dùng gửi username/password, việc xác thực không chỉ là so sánh hai chuỗi. Spring Security cần nhận diện request đăng nhập, tạo yêu cầu xác thực, chọn `AuthenticationProvider`, thiết lập `SecurityContext`, xử lý session và quyết định phản hồi khi thành công hoặc thất bại.

`AbstractAuthenticationProcessingFilter` là lớp cơ sở cung cấp **khung điều phối** cho những Servlet filter chủ động thực hiện authentication ở một endpoint xác định. Implementation phổ biến nhất là `UsernamePasswordAuthenticationFilter` dùng cho form login. Hiểu khung này giúp bạn giải thích vì sao request login bị CSRF từ chối, vì sao đăng nhập thành công nhưng request sau thành anonymous, hoặc vì sao lỗi mật khẩu trả redirect thay vì HTTP 401.

**Phạm vi:** Spring Security **Servlet** (Spring MVC, `HttpSecurity`, `SecurityFilterChain`, `HttpServletRequest`), trọng tâm cơ chế thông dụng ở Spring Security 6.x. Ví dụ dùng Spring Boot 3.3.5 và Java 17+ làm mốc học tập, không khẳng định đây là bản mới nhất hoặc còn được hỗ trợ tại thời điểm đọc. Spring WebFlux có các thành phần reactive riêng, không dùng lớp này trong `SecurityWebFilterChain`.

## 1. Vị trí của AbstractAuthenticationProcessingFilter trong filter chain

```text
HTTP client / browser
       |
Servlet container
       |
DelegatingFilterProxy -> FilterChainProxy
       |
SecurityFilterChain phù hợp với request
       |
(các security filters khác trước authentication filter)
       |
UsernamePasswordAuthenticationFilter
   extends AbstractAuthenticationProcessingFilter
       |
       +-- requiresAuthentication(request, response)?
       |     |
       |     +-- NO  -> filterChain.doFilter(...)
       |     |
       |     +-- YES -> attemptAuthentication(...)
       |                    |
       |              AuthenticationManager
       |                    |
       |              AuthenticationProvider
       |                    |
       |           Authentication / null / exception
       |
       +-- success -> session strategy -> successfulAuthentication(...)
       |
       +-- failure -> unsuccessfulAuthentication(...)
       |
       +-- result null -> kết thúc nhánh đang chờ xác thực
       |
       +-- SuccessHandler / FailureHandler quyết định response
```

Sơ đồ là mô hình logic; **số filter và thứ tự chính xác** tùy cấu hình, loại authentication và phiên bản. Khi `requiresAuthentication` không khớp, filter chỉ chuyển tiếp request; các filter khác vẫn có thể xử lý xác thực hoặc phân quyền. Ngược lại, khi request thực sự được dùng để đăng nhập, một success/failure handler thường tạo redirect hoặc response, nên request đó không nhất thiết đi đến controller của ứng dụng.

Ví dụ với `formLogin()` mặc định:

- `GET /login` thường hiển thị trang login được framework tạo hoặc trang tự khai báo. Nó không phải request thử username/password của filter.
- `POST /login` với form fields `username` và `password` là endpoint xử lý xác thực mặc định; matcher của `UsernamePasswordAuthenticationFilter` hướng tới request này.
- `GET /profile` không phải endpoint xử lý login. Login filter sẽ chuyển tiếp request; authentication có thể được nạp từ session và bộ authorization sẽ quyết định quyền truy cập.

**`permitAll()` không vô hiệu hóa authentication filter.** Nó cho phép request tại bước authorization, còn CSRF, authentication, session và các filter khác vẫn chạy theo cấu hình.

## 2. Bản hợp đồng của lớp cơ sở

Lớp cơ sở xử lý ba kết quả từ method trừu tượng:

```java
public abstract Authentication attemptAuthentication(
        HttpServletRequest request,
        HttpServletResponse response)
        throws AuthenticationException, IOException, ServletException;
```

Đây là **chữ ký API để giải thích**, không phải chương trình Java có thể chạy độc lập. Lớp con phải triển khai cách lấy dữ liệu request, tạo một yêu cầu xác thực **chưa đáng tin**, rồi nhờ `AuthenticationManager` xác minh.

| Kết quả từ `attemptAuthentication` | Ý nghĩa | Nhánh tiếp theo |
|---|---|---|
| Trả về `Authentication` xác thực thành công | Manager/provider đã xác minh bằng chứng theo cơ chế đã chọn | Chạy `SessionAuthenticationStrategy` rồi gọi `successfulAuthentication` |
| Trả về `null` | Xác thực chưa hoàn tất trong request hiện tại | Filter dừng nhánh của request này; không tự gọi success/failure handler |
| Ném `AuthenticationException` | Yêu cầu xác thực thất bại hoặc không được chấp nhận | Gọi `unsuccessfulAuthentication` và failure handler |

`null` **không đồng nghĩa sai mật khẩu**. Nó có thể biểu thị một giao thức nhiều bước chưa hoàn tất, khi lớp con tự quản lý response và trạng thái cần thiết. Ngược lại, sai credential thường tạo `BadCredentialsException` thuộc `AuthenticationException`.

### UsernamePasswordAuthenticationFilter làm gì?

Implementation cho form login thường lấy các tham số request `username` và `password`, tạo `UsernamePasswordAuthenticationToken` chưa xác thực, rồi gọi `AuthenticationManager.authenticate(...)`. Filter này **không tự quyết định** password hợp lệ.

Một luồng xác thực điển hình:

```text
POST /login
    |
UsernamePasswordAuthenticationFilter.attemptAuthentication(...)
    |
UsernamePasswordAuthenticationToken (untrusted)
    |
AuthenticationManager.authenticate(...)
    |
ProviderManager
    |
Provider hỗ trợ username/password
    +-- UserDetailsService đọc thông tin tài khoản
    +-- PasswordEncoder kiểm tra mật khẩu đã mã hóa
    +-- quy tắc trạng thái tài khoản (khóa, disabled, expired ...)
    |
Authentication đã xác thực hoặc AuthenticationException
```

Không tạo một `UsernamePasswordAuthenticationToken` đã gắn authorities rồi tự đưa vào `SecurityContextHolder` chỉ từ giá trị username do client gửi. Các factory method như `UsernamePasswordAuthenticationToken.unauthenticated(username, password)` diễn đạt rõ dữ liệu ban đầu chưa được tin cậy. Đối tượng Authentication đã xác thực phải đến từ manager/provider đáng tin.

Provider có thể phục vụ cơ chế khác với form login, và một manager có thể điều phối nhiều provider. Sự tồn tại của `UserDetailsService` không có nghĩa mọi request, kể cả JWT Bearer hay OIDC callback, đều được xác minh bằng form password.

## 3. Trước khi thử authentication: RequestMatcher, HTTP method, CSRF

Method `requiresAuthentication(request, response)` dựa vào `RequestMatcher` của filter. Matcher phải khớp HTTP path và method chính xác với request dự kiến.

Với form login mặc định, request xử lý xác thực thường là `POST /login`. Có thể thay URL:

```java
http.formLogin(form -> form
    .loginProcessingUrl("/signin")
    .permitAll());
```

Đây là **mảnh code bên trong cấu hình HttpSecurity**. Khi đổi login processing URL, client cũng phải gửi POST tới URL mới, đồng thời trang hiển thị form GET cần được cấu hình/kiểm tra tương ứng. `loginPage` và `loginProcessingUrl` không phải một khái niệm.

Trước khi login filter thử mật khẩu, request có thể đã bị một thành phần khác chặn:

1. **`CsrfFilter`** kiểm tra CSRF token với POST trong website dùng session/cookie. Thiếu token có thể tạo HTTP 403 **trước khi `attemptAuthentication` chạy**.
2. **Servlet firewall/matcher** xác định path được chuẩn hóa phù hợp, hoặc từ chối request không hợp lệ.
3. **Filter bảo mật khác** xử lý headers, session, CORS hoặc cơ chế xác thực khác tùy cách sắp xếp.
4. **SecurityFilterChain selection** quyết định request có đi vào filter login hay không. Một `securityMatcher` quá hẹp hoặc một quy tắc `WebSecurityCustomizer.ignoring` sai có thể khiến POST login không đi qua chain dự kiến.

Do đó khi POST login trả 403, **đừng mặc định mật khẩu đã được kiểm tra**. Xem CSRF token và chain trước khi điều tra provider.

## 4. Sau khi xác thực thành công: thứ tự quan trọng

Với `AbstractAuthenticationProcessingFilter` của Spring Security 6, sau khi `attemptAuthentication` trả về kết quả hợp lệ, luồng cơ bản gồm:

1. **`SessionAuthenticationStrategy.onAuthentication(...)`**: áp dụng chính sách liên quan session nếu có, ví dụ đổi session id để chống session fixation, giới hạn phiên hoặc quy tắc session khác. Nếu chính sách này ném authentication exception, flow có thể chuyển sang nhánh thất bại.
2. **`successfulAuthentication(...)`**: tạo một `SecurityContext` mới, đặt `Authentication` đã xác thực vào context, thiết lập cho `SecurityContextHolder` rồi lưu qua `SecurityContextRepository` theo cấu hình của filter.
3. **Remember-me và sự kiện:** nếu được cấu hình, thông báo `RememberMeServices.loginSuccess(...)`; có thể phát `InteractiveAuthenticationSuccessEvent`.
4. **`AuthenticationSuccessHandler.onAuthenticationSuccess(...)`**: trả response phù hợp, thường là redirect sau form login hoặc response được định nghĩa riêng cho client.

```text
Authentication result
       |
SessionAuthenticationStrategy.onAuthentication(...)
       |
successfulAuthentication(...)
       |
SecurityContextHolder <- SecurityContext(Authentication)
       |
SecurityContextRepository.saveContext(...)
       |
RememberMeServices.loginSuccess(...) / event khi được cấu hình
       |
AuthenticationSuccessHandler.onAuthenticationSuccess(...)
       |
302 redirect, JSON/HTTP status, hoặc response theo handler
```

**Vì sao phải save context?** Holder thường gắn với vòng đời xử lý request/thread hiện tại. Redirect tạo ra một **HTTP request mới**; nếu muốn form login tiếp tục giữ người dùng đã xác thực, SecurityContext phải được lưu qua repository phù hợp, thường liên quan `HttpSessionSecurityContextRepository`. Một `RequestAttributeSecurityContextRepository` chỉ giữ context trong cùng HTTP request hoặc dispatch.

Trong mô hình explicit save của Spring Security 6, chỉ thực hiện `SecurityContextHolder.setContext(...)` trong custom code chưa bảo đảm context tồn tại ở request kế tiếp. Các authentication filter chuẩn có thể thực hiện việc lưu; với custom flow phải xác định rõ repository và lúc `saveContext` được gọi. Lưu trước khi response commit/redirect để cookie session có cơ hội tới trình duyệt.

### Success handler và request cache

Một người chưa đăng nhập truy cập `/profile` có thể được chuyển tới trang login. `RequestCache` có thể lưu request dự định ban đầu; khi login thành công, `SavedRequestAwareAuthenticationSuccessHandler` có thể đưa người dùng quay lại trang họ định xem.

Nếu không có saved request, handler có thể redirect trang mặc định. Với cấu hình `defaultSuccessUrl("/profile", true)`, handler sẽ ưu tiên URL cố định `/profile` thay vì saved request. Một redirect thành công **không chứng minh** session/cookie đã được lưu đúng: phải gửi request kế tiếp và kiểm tra.

### continueChainBeforeSuccessfulAuthentication

Lớp cơ sở có tùy chọn `continueChainBeforeSuccessfulAuthentication` cho phép tiếp tục filter chain **trước** callback thành công. Mặc định thông thường không bật. Nếu bật không có lý do rõ, downstream filter/controller có thể chạy trước khi context mới được lưu, làm luồng khó dự đoán. Cần test riêng nếu hệ thống thực sự có yêu cầu đó.

## 5. Sau khi xác thực thất bại: unsuccessfulAuthentication

Khi provider/manager ném `AuthenticationException`, hoặc một điều kiện session authentication không cho phép hoàn tất, filter đi qua `unsuccessfulAuthentication(request, response, exception)`.

Các thao tác cơ bản của lớp cơ sở:

- Dọn `SecurityContextHolder` để request hiện tại không tiếp tục dùng authentication không phù hợp.
- Thông báo `RememberMeServices.loginFail(...)` khi có cơ chế remember-me.
- Gọi `AuthenticationFailureHandler.onAuthenticationFailure(...)` để quyết định status/redirect/response.

```text
attemptAuthentication(...) / SessionAuthenticationStrategy
             |
        AuthenticationException
             |
    unsuccessfulAuthentication(...)
             |
    SecurityContextHolder.clearContext()
             |
    RememberMeServices.loginFail(...)
             |
    AuthenticationFailureHandler
             |
    302 /login?error hoặc 401 tùy chính sách ứng dụng
```

**Không có quy tắc “login thất bại luôn HTTP 401”.** Form login thường redirect tới trang hiển thị lỗi, ví dụ `302 Location: /login?error`. Một API tự thiết kế JSON login có thể trả 401, nhưng phải cấu hình failure handler rõ ràng.

Đừng đưa chi tiết “tài khoản không tồn tại” hoặc “mật khẩu sai” vào phản hồi cho người dùng khác biệt quá mức, tránh lộ danh sách tài khoản. Không ghi raw password, CSRF token, session id hoặc toàn bộ credential vào log.

Việc dọn holder khi thất bại **không tự đồng nghĩa** mọi session đã tồn tại đều bị invalidate, mọi security context cũ bị xóa vĩnh viễn hoặc mọi thiết bị bị logout. Đó là trách nhiệm của session/logout policy riêng.

### Khác gì với ExceptionTranslationFilter?

`ExceptionTranslationFilter` chủ yếu chuyển authentication/authorization exception từ các phần security chain liên quan thành phản hồi qua `AuthenticationEntryPoint` hoặc access-denied handler. Lỗi xử lý **POST login** thường được chính `AbstractAuthenticationProcessingFilter` chuyển qua failure handler. Đừng gộp hai luồng này khi phân tích status 401/302/403.

## 6. Chọn đúng điểm mở rộng

| Muốn làm gì? | Điểm mở rộng thường phù hợp |
|---|---|
| Đổi redirect khi login thành công | `AuthenticationSuccessHandler` hoặc `defaultSuccessUrl` |
| Hiển thị lỗi login chung, trả JSON 401 | `AuthenticationFailureHandler` |
| Hỗ trợ kiểu credential mới | Authentication filter phù hợp + `AuthenticationManager`/`AuthenticationProvider` |
| Kiểm tra username/password | `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder` |
| Chống session fixation hoặc giới hạn số phiên | `SessionAuthenticationStrategy` / session management |
| Lưu context qua request | `SecurityContextRepository` và chính sách session |
| Ghi audit, monitoring | Event/listener, handler hoặc hook an toàn, không log secrets |
| Bảo vệ API endpoint sau login | `authorizeHttpRequests`, method security, kiểm tra quyền nghiệp vụ |

Phần lớn việc tùy chỉnh **redirect hoặc nội dung response** không đòi phải kế thừa `AbstractAuthenticationProcessingFilter`. Chọn đúng handler giúp giữ nguyên những thao tác chuẩn về context, remember-me và session.

### Ví dụ success/failure handler ngắn

Các đoạn sau là **mảnh cấu hình thay thế**, không dùng đồng thời với cấu hình default redirect trong ví dụ runnable ở mục 7 nếu chưa cập nhật test.

```java
.formLogin(form -> form.successHandler((request, response, authentication) -> {
    response.setStatus(200);
    response.setContentType("text/plain;charset=UTF-8");
    response.getWriter().write("LOGIN_OK");
}))
```

```java
.formLogin(form -> form.failureHandler((request, response, exception) -> {
    response.sendError(401, "Authentication failed");
}))
```

Handler chịu trách nhiệm phản hồi, không nên tự xác minh raw password hay tự đánh dấu một Authentication là authenticated. Đối với app trả JSON, cần thiết kế cả session/cookie, CSRF, logout, xử lý lỗi và client; HTTP 200 đơn lẻ chưa nói lên chất lượng của authentication flow.

## 7. Ví dụ hoàn chỉnh Spring Boot MVC với formLogin

Dự án ví dụ dùng **Spring Boot 3.3.5, Java 17+, Maven và Spring Security 6 do Boot quản lý**. Mốc version chỉ để trình bày cấu hình đồng nhất và kiểm thử có kỳ vọng rõ; với dự án mới, hãy chọn bản stable còn trong vòng hỗ trợ và xem migration notes.

Mục tiêu quan sát:

- GET public đi qua authorization mà không cần login.
- GET private khi anonymous chuyển đến trang login.
- POST login hợp lệ chạy authentication filter, success handler redirect tới URL cố định; request tiếp theo giữ context bằng session.
- POST login sai mật khẩu đi nhánh failure.
- POST login thiếu CSRF token bị chặn **trước** khi filter xác minh mật khẩu.

### 7.1. Maven: pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>auth-filter-flow</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Không khai báo version lẻ của các module Security/Framework vì chúng do Spring Boot parent căn đồng bộ.

### 7.2. Entry point

Tạo `src/main/java/example/authflow/AuthFlowApplication.java`:

```java
package example.authflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthFlowApplication.class, args);
    }
}
```

### 7.3. REST controller

Tạo `src/main/java/example/authflow/ProfileController.java`:

```java
package example.authflow;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC_OK";
    }

    @GetMapping("/profile")
    public String profile(Principal principal) {
        return "Hello, " + principal.getName();
    }
}
```

`Principal` chỉ được dùng khi request đã vượt qua authorization ở URL yêu cầu đăng nhập. Nếu cần kiểm tra vai trò/sở hữu dữ liệu, phải thêm quy tắc tương ứng; xác thực thành công không tự cấp mọi quyền nghiệp vụ.

### 7.4. Cấu hình SecurityFilterChain và tài khoản thử nghiệm

Tạo `src/main/java/example/authflow/SecurityConfig.java`:

```java
package example.authflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("correct-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/profile", true)
                .failureUrl("/login?error")
                .permitAll())
            .build();
    }
}
```

Cấu hình mẫu **không tắt CSRF**. `formLogin` kích hoạt xử lý form POST qua authentication filter chuẩn; `GET /login` có thể được Spring Security sinh trang mặc định. `defaultSuccessUrl("/profile", true)` ép redirect tới `/profile` sau login thành công để kiểm thử ổn định. Tài khoản trong memory chỉ là fixture; production cần user storage, chính sách mật khẩu và session management phù hợp.

### 7.5. JUnit/MockMvc integration tests

Tạo `src/test/java/example/authflow/AuthenticationFlowTest.java`:

```java
package example.authflow;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void anonymousPrivateRouteRedirectsToLogin() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void successfulLoginPersistsAuthenticationInSession() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("alice").password("correct-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/profile"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, alice"));
    }

    @Test
    void wrongPasswordInvokesFailureHandler() throws Exception {
        mvc.perform(formLogin().user("alice").password("wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void csrfFilterRejectsLoginPostWithoutToken() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "correct-password"))
            .andExpect(status().isForbidden());
    }
}
```

Helper `formLogin()` từ `spring-security-test` tạo request đăng nhập theo convention và tích hợp CSRF cho test. Request `post("/login")` thủ công cuối cùng cố tình **không có CSRF token**. Tất cả test đi qua web security filter chain nhờ `@SpringBootTest` và `@AutoConfigureMockMvc`.

Chạy với JDK 17+ tương thích, Maven và kết nối dependency repository/cache:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

**Kỳ vọng**: 5 test thành công khi project được tạo đúng và dependencies resolve được. Stdout của Maven/Boot thay đổi theo môi trường nên không có transcript cố định; đây là kết quả dự kiến, không phải khẳng định đã chạy lệnh. Với server đang chạy trên port 8080 mặc định, truy cập `http://localhost:8080/login`, đăng nhập bằng fixture `alice / correct-password` rồi xem `/profile` trả chính xác body:

```text
Hello, alice
```

Đây là kết quả của controller cho phiên đăng nhập hợp lệ; HTML trang login, cookie và response headers còn tùy cấu hình thực tế.

**Vì sao test dùng formLogin thay vì @WithMockUser?** `@WithMockUser` đặt principal giả cho một test và hữu ích để kiểm tra authorization, nhưng nó không chứng minh `UsernamePasswordAuthenticationFilter.attemptAuthentication` và provider đã chạy với mật khẩu thật.

## 8. Khi cần tạo custom filter thực sự

Chỉ tạo filter mới khi yêu cầu một cơ chế thu thập và xác thực credential không được hỗ trợ bởi filter sẵn có. Khi đó cần xác định request matcher, AuthenticationManager, session strategy, repository, success/failure handler và filter order. Có thể override các hook:

```java
@Override
public Authentication attemptAuthentication(
        HttpServletRequest request,
        HttpServletResponse response) throws AuthenticationException {
    // Tạo yêu cầu xác thực chưa đáng tin từ dữ liệu đã kiểm soát.
    // Gọi AuthenticationManager rồi trả Authentication đã xác thực.
}

@Override
protected void successfulAuthentication(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain,
        Authentication result) throws IOException, ServletException {
    // Audit an toàn, không in credentials.
    super.successfulAuthentication(request, response, chain, result);
}

@Override
protected void unsuccessfulAuthentication(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException exception)
        throws IOException, ServletException {
    // Ghi nhận lỗi an toàn, tránh tiết lộ user existence.
    super.unsuccessfulAuthentication(request, response, exception);
}
```

Đây là **phác thảo hook, không phải class Java độc lập có thể biên dịch**: `attemptAuthentication` còn thiếu implementation và `return`; class thực tế cần các import, constructor, matcher, manager, registration và tests. Tài liệu không đưa ra custom login filter chưa hoàn chỉnh rồi coi đó là một giải pháp production.

Lời gọi `super.successfulAuthentication(...)` và `super.unsuccessfulAuthentication(...)` có ý nghĩa: chúng giữ logic chuẩn về security context, repository, remember-me, event và handler. Nếu bỏ `super`, phải chịu trách nhiệm tái tạo đầy đủ contract; nếu không, login có thể trả thành công nhưng request kế tiếp mất context.

**Không tự đăng ký cùng một filter vào cả Servlet container và Spring Security chain** nếu không chủ ý; đăng ký trùng có thể khiến authentication chạy hai lần. Dùng cơ chế đăng ký filter đúng của Spring Security và kiểm thử vị trí. Một authentication filter không phải nơi thích hợp để nhét toàn bộ authorization nghiệp vụ.

## 9. Những điểm dễ nhầm khi triển khai

**Nhầm 1 — GET login cũng gọi attemptAuthentication.** Không đúng trong form login thông dụng. GET thường dùng hiển thị form, POST mới xử lý xác thực. Kiểm tra login processing URL, method và matcher.

**Nhầm 2 — permitAll trên POST login đủ để bỏ qua CSRF.** Không. CSRF filter có thể chặn request trước authentication; `permitAll` chỉ là rule authorization.

**Nhầm 3 — Password đúng thì controller phải chạy ngay.** Thường thành công được success handler xử lý bằng redirect. Controller nhận request **sau redirect**; nếu muốn trả response JSON cần success handler tương ứng.

**Nhầm 4 — Success handler phải tự lưu session.** Bước lưu context thuộc flow authentication filter/repository. Handler quyết định response; custom code không nên làm loạn session và security context.

**Nhầm 5 — Lỗi mật khẩu buộc phải trả 401.** Form login thường trả 302 về trang lỗi. HTTP Basic/bearer hoặc JSON login API có thể trả 401 tùy cơ chế và handler.

**Nhầm 6 — Chỉ đặt authentication vào SecurityContextHolder đã đủ cho request sau.** Holder thường được dọn ở ranh giới request; phải lưu/nạp qua repository khi cần phiên đăng nhập.

**Nhầm 7 — Mọi authentication filter đều kế thừa AbstractAuthenticationProcessingFilter.** Không. HTTP Basic, bearer token, OIDC/OAuth2 và cơ chế khác có các filter/chương trình xử lý riêng. Khái niệm AuthenticationManager/SecurityContext có thể dùng chung nhưng điểm tích hợp khác nhau.

**Nhầm 8 — Authentication thành công nghĩa là có quyền vào mọi endpoint.** Không. AuthorizationFilter, method security và quy tắc ownership/tenant còn quyết định khả năng truy cập.

**Nhầm 9 — Tắt session fixation protection để đăng nhập hoạt động.** Không nên. Tìm nguyên nhân chính sách session hoặc cookie rồi sửa đúng; tránh bỏ cơ chế phòng vệ chỉ vì lỗi tích hợp.

**Nhầm 10 — Logging toàn bộ Authentication sẽ giúp debug.** Có thể lộ thông tin nhạy cảm. Chỉ log metadata an toàn, correlation ID, loại lỗi đã chuẩn hóa và tuyệt đối không log raw credentials/token.

## 10. Quy trình debug và checklist bảo mật

1. **Xác định HTTP stack:** Spring MVC Servlet dùng `HttpSecurity`/`SecurityFilterChain`; tránh nhầm WebFlux.
2. **Kiểm tra request thực tế:** path, method, content type, username/password parameter names, CSRF token và session cookie.
3. **Tìm chain và matcher:** `FilterChainProxy` có chọn chain chứa login filter không, có `securityMatcher` hoặc `ignoring` làm request bypass không?
4. **Quan sát attempt:** request đã vào `attemptAuthentication` chưa, token truyền cho manager có đúng loại không, provider có hỗ trợ không?
5. **Phân biệt ba kết quả:** Authentication success, `null` chưa hoàn tất, hoặc `AuthenticationException` thất bại.
6. **Kiểm tra hậu xử lý success:** `SessionAuthenticationStrategy`, context repository, cookie, remember-me và success handler.
7. **Kiểm tra failure handler:** status/redirect, cách truyền thông báo lỗi và tránh leak dữ liệu.
8. **Thử request kế tiếp:** cùng session và không có session, GET private trước/sau login, password sai và POST thiếu CSRF token.
9. **Đối chiếu quyền nghiệp vụ:** test một người đã đăng nhập nhưng không có quyền với dữ liệu khác tenant; đó là authorization, không thuộc nhiệm vụ password authentication.
10. **Bật log có kiểm soát:** logging `org.springframework.security` ở mức DEBUG trong môi trường phát triển, tránh để log nhạy cảm trên production.

### Tự kiểm tra

**Câu 1.** Vì sao `GET /login` có trang đăng nhập nhưng `attemptAuthentication` chưa chạy?  
**Đáp án:** GET thường hiển thị form; mặc định POST mới khớp endpoint login processing.

**Câu 2.** `attemptAuthentication` trả `null` khác ném `BadCredentialsException` thế nào?  
**Đáp án:** `null` biểu thị authentication chưa hoàn tất; exception kích hoạt nhánh failure.

**Câu 3.** Ai quyết định redirect `/login?error` khi password sai?  
**Đáp án:** `unsuccessfulAuthentication` chuyển kết quả cho `AuthenticationFailureHandler` đã cấu hình.

**Câu 4.** Password đúng và trả redirect, nhưng request sau anonymous. Kiểm tra gì?  
**Đáp án:** `SecurityContextRepository.saveContext`, session/cookie, repository được dùng bởi các filter và thời điểm response commit.

**Câu 5.** Muốn đổi success redirect, có cần viết class kế thừa `AbstractAuthenticationProcessingFilter`?  
**Đáp án:** Thường không; cấu hình `AuthenticationSuccessHandler` hoặc `defaultSuccessUrl` phù hợp hơn.

**Câu 6.** Một user đã xác thực có tự động được quyền xem đơn hàng của người khác không?  
**Đáp án:** Không. Xác thực danh tính và phân quyền trên đối tượng nghiệp vụ là hai bước riêng.

**Ghi nhớ:** `AbstractAuthenticationProcessingFilter` điều phối **match request → thử xác thực → session strategy → success/failure → context/repository → response handler**. Hiểu đúng điểm mở rộng giúp triển khai luồng đăng nhập Servlet an toàn mà không bỏ quên CSRF, session, quyền truy cập và phản hồi HTTP.