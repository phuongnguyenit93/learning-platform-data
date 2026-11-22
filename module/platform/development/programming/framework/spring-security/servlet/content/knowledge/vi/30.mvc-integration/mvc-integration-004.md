# HttpServletRequest.authenticate, login và logout trong Spring Security Servlet

> **Ngữ cảnh:** Ứng dụng Java 17+, Spring Boot 3.x và Spring Security 6.x theo mô hình **Servlet / Spring MVC**. Ba phương thức `HttpServletRequest.authenticate(HttpServletResponse)`, `login(String, String)` và `logout()` là API của Servlet để làm việc với trạng thái xác thực của request. Spring Security có tích hợp với Servlet API, nhưng cần hiểu ai thực sự xử lý lời gọi, cách duy trì `SecurityContext` và sự khác biệt với filter xác thực/đăng xuất thông thường.

## 1. Mục tiêu học tập và tình huống thực tế

Sau bài này, bạn có thể:

- Phân biệt **container-managed authentication** và xác thực được **Spring Security** xử lý thông qua `SecurityContextHolderAwareRequestFilter`.
- Giải thích đầu vào, kết quả, ngoại lệ và tác động lên HTTP response của `request.authenticate(response)`.
- Dùng `request.login(username, password)` khi có nhu cầu đăng nhập theo chương trình và biết vì sao phải cấu hình `AuthenticationManager` hoặc cơ chế xác thực tương ứng.
- Hiểu phạm vi `request.logout()`, không nhầm logout của ứng dụng với logout khỏi Identity Provider, thu hồi token hoặc mọi thiết bị.
- Đọc `request.getUserPrincipal()`, `getRemoteUser()`, `isUserInRole(...)` sau xác thực và đánh giá sự nhất quán với `SecurityContextHolder`.
- Viết Spring MVC Controller minh họa ba API, kiểm thử bằng MockMvc với CSRF, phân biệt 302/401/403/204 và tránh rò credentials.

Tình huống: một ứng dụng MVC có màn hình tài khoản. Người dùng đăng nhập qua form chuẩn; một số chức năng legacy lại yêu cầu gọi Servlet API trong controller. Nếu không hiểu cơ chế tích hợp, team có thể gọi `request.login(...)` trong khi Spring Security không có authentication manager phù hợp, gọi `request.logout()` rồi cho rằng phiên IdP cũng đã kết thúc, hoặc gửi cả redirect login lẫn JSON trong cùng một response.

Ba phương thức này không thay thế toàn bộ hạ tầng xác thực; chúng là **cửa vào theo chuẩn Servlet** để yêu cầu xác thực, đăng nhập hoặc đăng xuất trong ngữ cảnh một HTTP request.

## 2. Hai cách một Servlet request có thể được xác thực

### 2.1. Servlet container tự quản lý xác thực

Jakarta Servlet định nghĩa API trong `jakarta.servlet.http.HttpServletRequest`. Khi application server có realm, security constraints, login mechanism và role mapping được cấu hình, container có thể:

1. Xác thực người dùng theo policy của nó.
2. Cung cấp `request.getUserPrincipal()`, `getRemoteUser()` và `isUserInRole(...)`.
3. Thực hiện `request.authenticate(response)` để khởi động/tiếp tục cơ chế xác thực đã cấu hình.
4. Thử đăng nhập với `request.login(username, password)` nếu cơ chế container hỗ trợ.
5. Thực hiện `request.logout()` đối với danh tính do container quản lý.

Không có cấu hình bảo mật container phù hợp thì việc gọi những API này **không tự sinh ra form login, cơ sở người dùng hay mật khẩu hợp lệ**.

### 2.2. Spring Security bao request và tích hợp Servlet API

Khi request đi qua `FilterChainProxy`, Spring Security có `SecurityContextHolderAwareRequestFilter`. Filter này có thể cung cấp một `HttpServletRequestWrapper` để những API Servlet liên quan tới principal và xác thực hoạt động cùng `SecurityContextHolder`, `AuthenticationManager` và cơ chế entry point/logout của Spring Security.

Sơ đồ giản lược:

```text
HTTP request
   |
Servlet container
   |
Spring Security FilterChainProxy
   +-- tải/chuẩn bị SecurityContext
   +-- authentication filters / anonymous / authorization
   +-- SecurityContextHolderAwareRequestFilter
   |        |
   |        +-- request wrapper tương thích Servlet API
   |
DispatcherServlet
   |
@Controller / @RestController
   |
request.authenticate(response) / request.login(...) / request.logout()
   |
Spring Security integration (nếu request đã được bao đúng)
   |
HTTP response / security context / session
```

**Quan trọng:** cùng một chữ ký phương thức nhưng kết quả và integration point phụ thuộc **request thực tế được truyền tới controller**. Nếu endpoint bị loại khỏi Spring Security qua `web.ignoring()`, một filter tự tạo giữ raw request, hoặc request đi qua chain không như kỳ vọng, bạn không được giả định đã nhận wrapper tích hợp của Spring Security.

Trong dự án Spring Boot với Spring Security thông thường, `servletApi` integration thường được cấu hình trong filter chain. Khi cần rõ chủ đích, có thể dùng `http.servletApi(Customizer.withDefaults())` nếu API đó có ở phiên bản đang dùng. Hãy kiểm chứng bằng test trên phiên bản đã khóa, không đoán từ hành vi của application server khác.

**Không đánh đồng principal container với principal Spring Security.** Với wrapper của Spring Security, `getUserPrincipal()` phản ánh `Authentication` hiện tại (trừ anonymous theo cơ chế wrapper); còn một `HttpServletRequest` chưa được bao có thể lấy principal từ container realm. Vì vậy, khi debug cần biết **request object do ai cung cấp**, chain nào xử lý và `SecurityContext` nào đang có hiệu lực.

## 3. So sánh trực tiếp ba phương thức

| API Servlet | Đầu vào | Ý nghĩa chính | Kết quả/ngoại lệ | Không làm thay |
|---|---|---|---|---|
| `boolean authenticate(HttpServletResponse response)` | Response hiện tại | Bảo đảm xác thực hoặc kích hoạt cơ chế authentication đã cấu hình | `true` khi được xác thực; `false` khi tiến trình/challenge chưa hoàn tất; có thể ném `IOException`/`ServletException` | Không yêu cầu username/password từ controller, không tự cấp role/MFA |
| `void login(String username, String password)` | Username và password | Đề nghị xác thực theo chương trình bằng credential do ứng dụng nhận | Trả về bình thường nếu thành công; có thể ném `ServletException` nếu không xác thực được/không hỗ trợ/trạng thái không hợp lệ | Không tự tạo user, không tự làm reset password hoặc policy MFA |
| `void logout()` | Không có tham số | Yêu cầu xóa trạng thái xác thực của caller theo cơ chế đang quản lý request | Có thể ném `ServletException`; hiệu ứng session/context tùy cơ chế tích hợp | Không mặc nhiên logout mọi ứng dụng SSO, revoke OAuth access token hay xóa mọi cookie |

Ba phương thức là **lời gọi có tác dụng phụ**, không chỉ là getter. `authenticate` có thể gửi redirect hoặc challenge và làm response committed; `login` thay đổi security state; `logout` thay đổi trạng thái hiện hành. Không dùng chúng trong hàm getter hoặc interceptor chỉ để “kiểm tra xem đã login chưa”.

Để chỉ đọc danh tính, dùng getter theo contract:

```java
Principal principal = request.getUserPrincipal();
String username = (principal != null) ? principal.getName() : "anonymous";
boolean admin = request.isUserInRole("ADMIN");
```

Đoạn trên chỉ là minh họa bên trong Servlet/controller, không phải class độc lập. Cần kiểm tra mapping role cho cả container và Spring Security; trong Spring Security, convention `ROLE_` ảnh hưởng cách `isUserInRole(...)` đối chiếu với `GrantedAuthority`.

## 4. request.authenticate(response): chủ động kích hoạt challenge

Chữ ký Jakarta Servlet:

```java
boolean authenticate(HttpServletResponse response)
        throws IOException, ServletException;
```

### 4.1. Trạng thái cần phân biệt

- **Đã có danh tính được xác thực:** phương thức có thể trả `true`; controller mới tiếp tục xử lý nội dung cần xác thực.
- **Chưa xác thực:** phương thức yêu cầu cơ chế authentication đã cấu hình. Với form login, response có thể được redirect tới trang login; với HTTP Basic, response có thể là 401 cùng header `WWW-Authenticate`; cơ chế container/IdP có cách xử lý khác. Nếu challenge chưa hoàn tất, kết quả thường là `false`.
- **Có lỗi giao thức hoặc tích hợp:** có thể ném `IOException` hoặc `ServletException`; không tự nuốt lỗi rồi cho request qua rule `permitAll`.
- **Response đã được xử lý bởi entry point/container:** controller **không được viết thêm JSON/HTML**, không gửi redirect thứ hai và không đổi status tùy tiện.

Ví dụ minh họa bên trong controller:

```java
@GetMapping("/session/ensure")
public void ensure(HttpServletRequest request,
                   HttpServletResponse response)
        throws IOException, ServletException {
    if (request.authenticate(response) && !response.isCommitted()) {
        response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    }
    // Nếu false, authentication mechanism đã xử lý challenge.
    // Không ghi tiếp body hoặc sendRedirect tại đây.
}
```

Đây là một handler method, cần đặt trong class `@Controller` hoặc `@RestController` có import tương ứng. Endpoint chỉ là minh họa hợp đồng HTTP; dự án thực tế có thể để Spring Security tự khởi động authentication khi URL protected được truy cập, không cần mỗi controller gọi `authenticate`.

### 4.2. Vì sao không mặc định 401?

Một request anonymous tới URL cần đăng nhập có thể nhận **302** đến trang login nếu ứng dụng dùng form login, **401** nếu dùng HTTP Basic hoặc bearer token entry point, hay một challenge khác từ container. `authenticate` không có hợp đồng “luôn trả 401”; status do cơ chế authentication entry point quyết định.

Nếu `authenticate(response)` trả `false`, đừng tiếp tục logic nghiệp vụ; điều đó không chứng minh request đã được authenticate. Nếu đã được authenticate, **authorization vẫn cần kiểm tra**: người dùng đã login chưa chắc được phép vào trang admin.

### 4.3. authenticate không phải một bước MFA mặc định

Gọi `request.authenticate(response)` trên phiên đã login có thể trả `true` mà không yêu cầu người dùng thực hiện yếu tố mới. Nếu ứng dụng cần step-up, phải có chính sách kiểm tra assurance/authentication age/factors, hoặc buộc flow riêng qua IdP rồi xác minh kết quả có chữ ký và đúng contract. Đừng coi việc gọi API này là hành động “re-authenticate bằng MFA”.

## 5. request.login(username, password): đăng nhập bằng chương trình

Chữ ký:

```java
void login(String username, String password) throws ServletException;
```

Đây là công cụ khi ứng dụng đã có giao diện/luồng nhận username/password và muốn yêu cầu cơ chế xác thực hiện hành thực hiện login. Nó **không tự biết cơ sở user, password encoder hay group mapping**; những thành phần này phải được cấu hình ở container hoặc Spring Security.

### 5.1. Trình tự hợp lý

```text
POST /session/programmatic-login
   |
Chỉ qua HTTPS; CSRF token hợp lệ nếu dùng session browser
   |
Nhận username/password từ request body (không qua query URL)
   |
request.login(username, password)
   |
   +-- thất bại --> ServletException
   |                 báo lỗi chung, không lộ password
   |
   +-- thành công --> request principal/SecurityContext có thể cập nhật
                       theo cơ chế tích hợp đang dùng
   |
Kiểm tra session/security-context persistence và fixation policy
   |
Trả 204 hoặc redirect theo hợp đồng API, không chứa credential
```

Khi Spring Security xử lý lời gọi qua wrapper, credentials có thể được đưa tới `AuthenticationManager`. Việc thành công phụ thuộc các `AuthenticationProvider` hiện có và sự tích hợp thực sự của request. Một chuỗi chỉ cấu hình OAuth2 login hoặc X.509 **không có nghĩa** tự chấp nhận username/password qua `request.login`.

Không nên gọi `request.login` trên một request đã xác thực mà không thiết kế rõ switch-user/re-authentication: Servlet API có thể từ chối trạng thái này bằng `ServletException`, và quy trình đổi identity phải tránh session confusion.

### 5.2. Các biện pháp bắt buộc ở endpoint nhận credentials

- **HTTPS và bảo vệ thông tin:** không dùng `GET /login?username=...&password=...`, không đưa credential vào URL, redirect, exception, audit hoặc log HTTP.
- **CSRF cho browser session:** login CSRF cũng đáng quan tâm; Spring Security thường áp dụng CSRF cho POST. Không tắt CSRF toàn ứng dụng chỉ để test POST login/logout.
- **Chống brute force/credential stuffing:** giới hạn tốc độ theo identity/IP/device, backoff, phát hiện bất thường và lockout phù hợp. Spring Security không thay thế toàn bộ risk engine.
- **Phản hồi lỗi chung:** không tiết lộ user có tồn tại hoặc mật khẩu sai qua message khác nhau.
- **Session fixation:** verify session ID rotation/chính sách session authentication strategy thực tế. Programmatic login là đường riêng nên phải kiểm thử tương đương form login; đừng chỉ giả định mọi hook của `UsernamePasswordAuthenticationFilter` được gọi.
- **MFA:** username/password thành công chỉ chứng minh yếu tố biết mật khẩu. Nếu endpoint nhạy cảm đòi nhiều yếu tố, không cho truy cập ngay chỉ vì `request.login` đã hoàn thành.
- **Chỉ lưu trạng thái khi phù hợp:** sau login, test `SecurityContextRepository`/session persistence trên request **tiếp theo**; việc một request hiện tại có principal không tự chứng minh phiên sẽ còn hợp lệ sau redirect.

### 5.3. request.login khác với tự đặt SecurityContext

Hai mẫu sau **không tương đương**:

```java
// Cơ chế Servlet/Spring Security tích hợp:
request.login(username, password);
```

```java
// Chỉ minh họa lỗi thiết kế: không xác thực gì cả.
SecurityContextHolder.getContext().setAuthentication(unverifiedAuth);
```

Ở mẫu thứ hai, nếu `unverifiedAuth` được dựng từ thông tin client chưa được `AuthenticationManager` kiểm tra, ứng dụng có thể tạo lỗ hổng nghiêm trọng. Ngay cả với một `Authentication` hợp lệ, code tự xây vẫn phải xử lý security context persistence, session strategy, failure handling và audit. Ưu tiên filter/DSL đăng nhập tiêu chuẩn trừ khi có yêu cầu ứng dụng rõ ràng cần programmatic login.

## 6. request.logout(): đăng xuất là dọn trạng thái nào?

Chữ ký:

```java
void logout() throws ServletException;
```

Khi request được Spring Security bao và cấu hình servlet integration thích hợp, `request.logout()` sẽ gọi logic đăng xuất của Spring Security để làm sạch authentication context và những trạng thái session được các `LogoutHandler` liên quan quản lý. Với container-managed security, nó yêu cầu container loại bỏ danh tính hiện tại theo cơ chế của container.

**Không áp một kết quả session/cookie duy nhất cho mọi implementation.** Cần kiểm tra thực nghiệm phiên bản, chain, logout handlers, session repository và container. Đặc biệt:

- **Session ứng dụng:** default logout handler của Spring Security thường invalidate `HttpSession` và clear `SecurityContext`; custom handler hoặc request không được bao có thể có hành vi khác.
- **Cookie:** việc server invalidate session không bảo đảm trình duyệt đã xóa mọi cookie tùy chỉnh. Có thể cần cấu hình `Clear-Site-Data` hoặc cookie deletion phù hợp (path/domain/SameSite), sau khi đánh giá tác động.
- **OIDC/SAML SSO:** logout local không luôn logout IdP hoặc các ứng dụng còn lại. RP-initiated logout hay SAML Single Logout phải được cấu hình theo hợp đồng.
- **Bearer token:** xóa session browser không revoke token còn hiệu lực ở client khác; token revocation, expiry và audience cần được thiết kế riêng.
- **Remember-me/persistent login:** nếu có cơ chế nhớ đăng nhập, cần biết handler nào xóa token và cookie.
- **Phiên ở thiết bị khác:** logout của request hiện tại không nhất thiết hủy các session đang hoạt động ở thiết bị khác.

Trong Spring Security Servlet, **`POST /logout` do `LogoutFilter` xử lý là con đường tiêu chuẩn** khi dùng cấu hình `logout()` và CSRF. Gọi `request.logout()` từ controller là lựa chọn API khác: chỉ dùng khi thực sự cần tích hợp/luồng legacy. Không nên tạo hai endpoint logout không nhất quán (một endpoint clear context, endpoint kia còn giữ remember-me token).

### 6.1. Vì sao ưu tiên POST logout?

Logout là thao tác thay đổi trạng thái. Nếu mở `GET /logout-now` để bất kỳ trang nào nhúng liên kết có thể kích hoạt logout, dễ dẫn tới logout CSRF hoặc hành vi ngoài dự kiến. Với ứng dụng sử dụng session và CSRF protection, để logout qua **POST cùng CSRF token hợp lệ**. Không dùng `csrf().disable()` chỉ để có thể gọi logout bằng curl đơn giản.

### 6.2. Logic controller sau logout

Nếu logout thành công, trả 204 No Content hoặc redirect tới trang public. Đừng sử dụng `getUserPrincipal()` sau đó để ghi thông tin người dùng vào response, vì context có thể đã được xóa. Nếu logout ném `ServletException`, cần log sự kiện an toàn và trả lỗi thích hợp; không trả thông báo chứa token/cookie/credential.

## 7. Ví dụ Spring Boot 3.3.x + Spring Security 6.x có thể chạy

Ví dụ này dùng **in-memory user** và form login chuẩn của Spring Security. Ngoài `/login` và `/logout` do filter chuẩn quản lý, ứng dụng còn cung cấp ba handler minh họa Servlet API. Đây là demo local dành cho học tập, **không phải** một dịch vụ đăng nhập production; nó không có MFA, user registration hoặc throttling.

Điểm quan trọng: controller được xử lý **bên trong security filter chain**, có `SecurityContextHolderAwareRequestFilter` tích hợp; chương trình không dựa vào application server realm độc lập.

### 7.1. Cấu trúc và dependency

`build.gradle`:

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

Với một dự án có Gradle Wrapper, tạo package `demo.servletapi` và ba lớp bên dưới.

### 7.2. Ứng dụng chính

File `src/main/java/demo/servletapi/ServletApiApplication.java`:

```java
package demo.servletapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletApiApplication.class, args);
    }
}
```

### 7.3. Cấu hình SecurityFilterChain

File `src/main/java/demo/servletapi/SecurityConfig.java`:

```java
package demo.servletapi;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
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
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${DEMO_PASSWORD}") String demoPassword) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode(demoPassword))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/").permitAll()
                .requestMatchers(HttpMethod.GET, "/session/ensure")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/session/programmatic-login")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/session/me")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/session/programmatic-logout")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .servletApi(Customizer.withDefaults())
            .build();
    }
}
```

**Giải thích:**

- `InMemoryUserDetailsManager` chỉ dùng cho demo. Username `learner` có `ROLE_USER`, password được BCrypt hash khi ứng dụng khởi động.
- `formLogin` cung cấp cơ chế form authentication/entry point và trang đăng nhập mặc định. Nó không cần được tắt để dùng Servlet API.
- `servletApi` công khai chủ đích dùng tích hợp Servlet request wrapper với Spring Security. Kiểm tra hỗ trợ DSL theo phiên bản Spring Security đang chạy.
- `/session/programmatic-login` được `permitAll` để người dùng chưa có principal có thể nộp credentials. Nhưng POST vẫn chịu **CSRF filter**.
- `/session/ensure` được `permitAll` để controller chủ động gọi `request.authenticate(response)`. Nếu chưa đăng nhập, entry point xử lý challenge.
- `/session/me` và logout demo cần principal hợp lệ. Không có rule `permitAll` trên mọi `/session/**`.
- Không gọi `csrf.disable()`, không đưa mật khẩu vào query và không tạo người dùng admin mặc định.

### 7.4. Controller minh họa ba API

File `src/main/java/demo/servletapi/SessionController.java`:

```java
package demo.servletapi;

import java.io.IOException;
import java.security.Principal;
import java.util.Map;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {
    @GetMapping("/")
    public String home() {
        return "public";
    }

    @GetMapping("/session/me")
    public Map<String, String> me(HttpServletRequest request) {
        Principal user = request.getUserPrincipal();
        return Map.of("user", user.getName());
    }

    @GetMapping("/session/ensure")
    public void ensure(HttpServletRequest request,
                       HttpServletResponse response)
            throws IOException, ServletException {
        if (request.authenticate(response) && !response.isCommitted()) {
            response.setStatus(HttpServletResponse.SC_NO_CONTENT);
        }
        // Khi false, không ghi thêm body: entry point đã xử lý challenge.
    }

    @PostMapping("/session/programmatic-login")
    public void login(HttpServletRequest request,
                      HttpServletResponse response,
                      @RequestParam String username,
                      @RequestParam String password)
            throws IOException {
        try {
            request.login(username, password);
            response.setStatus(HttpServletResponse.SC_NO_CONTENT);
        } catch (ServletException invalidCredentialsOrState) {
            // Không phản hồi nội dung exception: có thể lộ thông tin.
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED,
                    "Authentication failed");
        }
    }

    @PostMapping("/session/programmatic-logout")
    public void logout(HttpServletRequest request,
                       HttpServletResponse response)
            throws ServletException {
        request.logout();
        response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    }
}
```

**Chú ý:** handler login ở ví dụ chỉ minh họa API, chưa có rate limit, email verification, audit và tài khoản production. Handler giả định Spring Security đã bao request đúng cách và có `AuthenticationManager` tương thích username/password. Nếu dùng môi trường container realm thay vì Spring Security request wrapper, hành vi có thể khác; cần test trên cấu hình cụ thể.

Endpoint `GET /session/me` được `authenticated()` bảo vệ; vì thế `user.getName()` chỉ được dùng sau khi Spring Security cho request đi qua. Trong ứng dụng nhiều cơ chế authentication, code cần xử lý khả năng principal null phòng trường hợp chain/dispatch thay đổi.

### 7.5. Chạy bằng Gradle Wrapper

Với môi trường Bash:

```bash
export DEMO_PASSWORD='a-long-local-demo-password'
./gradlew bootRun
```

Giữ secret demo ngoài Git. Trên PowerShell dùng cú pháp environment variable tương ứng, không copy nguyên lệnh `export`.

Truy cập `http://localhost:8080/`:

```text
public
```

Truy cập `http://localhost:8080/session/me` khi chưa đăng nhập: form login entry point sẽ redirect đến `/login`. Nhập `learner` và password demo trên trang login chuẩn để tạo session; khi đó `/session/me` trả JSON có trường `"user":"learner"`.

Để thử **programmatic login/logout** bằng HTTP thật, browser/client phải gửi **CSRF token hợp lệ gắn với session**. Không đơn giản POST mật khẩu bằng curl mà bỏ CSRF; nếu nhận 403 thì cần phân biệt CSRF failure với login failure. Bộ test MockMvc bên dưới là cách kiểm chứng chính xác có CSRF mà không vô hiệu hóa bảo vệ.

## 8. Kiểm thử Servlet API bằng MockMvc

Các test quan trọng kiểm chứng **request thực sự đi qua Spring Security**, không chỉ gọi controller method bằng mock không có filter chain. `MockMvc` với `@SpringBootTest` và `@AutoConfigureMockMvc` giúp chạy filter chain trong môi trường test; `with(csrf())` mô phỏng CSRF token hợp lệ theo cơ chế `spring-security-test`.

File `src/test/java/demo/servletapi/ServletApiSecurityTest.java`:

```java
package demo.servletapi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "DEMO_PASSWORD=local-test-password")
@AutoConfigureMockMvc
class ServletApiSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk());
    }

    @Test
    void authenticateCanStartFormLoginChallenge() throws Exception {
        mvc.perform(get("/session/ensure"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    @WithMockUser(username = "learner", roles = "USER")
    void authenticatedRequestHasPrincipal() throws Exception {
        mvc.perform(get("/session/me"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    void loginRequiresCsrfEvenWhenEndpointPermitsAnonymous() throws Exception {
        mvc.perform(post("/session/programmatic-login")
                .param("username", "learner")
                .param("password", "local-test-password"))
            .andExpect(status().isForbidden());
    }

    @Test
    void programmaticLoginCreatesUsableSession() throws Exception {
        MvcResult login = mvc.perform(post("/session/programmatic-login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "local-test-password"))
            .andExpect(status().isNoContent())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/session/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    void logoutClearsCurrentSession() throws Exception {
        MvcResult login = mvc.perform(post("/session/programmatic-login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "local-test-password"))
            .andExpect(status().isNoContent())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/session/programmatic-logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().isNoContent());

        assertTrue(session.isInvalid());
    }
}
```

Chạy:

```bash
./gradlew test
```

**Phạm vi kiểm thử:** `@WithMockUser` chỉ kiểm tra principal/authority trong request test; nó **không kiểm chứng password encoder hoặc cơ chế login thật**. Test `programmaticLoginCreatesUsableSession` mới kiểm tra bằng credential trong in-memory store và tình trạng session request tiếp theo. Test logout xác nhận session bị invalidate **với cấu hình mặc định của ví dụ**, không bảo đảm cho mọi container hoặc custom logout handler.

Với dự án đã thay `SecurityContextRepository`, chạy nhiều chain, thêm filter tùy chỉnh, cấu hình session stateless hoặc IdP, cần sửa test để phản ánh security contract mới. Một test xanh trong MockMvc **không thay** E2E với browser thực, cookie flags, TLS/reverse proxy và IdP logout.

## 9. So sánh các cách đăng nhập/đăng xuất trong Spring MVC

| Cách | Điểm vào | Dùng khi | Đặc điểm cần lưu ý |
|---|---|---|---|
| `request.authenticate(response)` | Servlet API | Controller/Servlet cần yêu cầu xác thực hiện tại | Kích hoạt entry point nếu chưa có auth, có thể commit response |
| `request.login(username,password)` | Servlet API | Legacy MVC/cơ chế programmatic login có username/password | Phải có backend authentication manager/realm; tự chịu trách nhiệm nhận credential an toàn |
| `request.logout()` | Servlet API | Tích hợp logout programmatic ở request đã bao | Phải test session handlers, external IdP và cookie |
| `formLogin()` + mặc định `POST /login` | `UsernamePasswordAuthenticationFilter` | Browser dùng form login chuẩn | Spring Security kiểm soát failure, success, session strategy/redirect, CSRF theo config |
| `logout()` + mặc định `POST /logout` | `LogoutFilter` | Browser logout chuẩn | Các `LogoutHandler`, logout success handler và CSRF hoạt động thống nhất |
| `oauth2Login()` | OIDC/OAuth2 client filters | Browser đăng nhập với IdP | Không nhận password IdP bằng `request.login`; local logout khác SSO logout |
| `saml2Login()` | SAML2 service provider | Doanh nghiệp dùng SAML SSO | Cần xác minh SAML response, metadata và Single Logout riêng |
| `oauth2ResourceServer()` | Bearer token filter | Stateless API | Không dựa vào session login/logout như web MVC |
| Container realm + Servlet API | Container security machinery | Ứng dụng chạy trên application server có realm đã cấu hình | Principal/roles của container cần được trust/mapping đúng; Spring Security wrapper có thể không phải tầng xác thực chính |

Không nên triển khai song song nhiều endpoint login/reset/logout mà **không có chính sách chung**. Chẳng hạn app đã dùng OIDC thì một endpoint mới chấp nhận password qua `request.login` có thể vô tình tạo đường đăng nhập phụ bỏ qua MFA của IdP.

### 9.1. getUserPrincipal và isUserInRole dưới request wrapper

Với request được Spring Security tích hợp:

```java
Principal principal = request.getUserPrincipal();
String name = (principal == null) ? null : principal.getName();
boolean permitted = request.isUserInRole("ADMIN");
```

Thành công của `isUserInRole("ADMIN")` phụ thuộc role mapping/`GrantedAuthority`. Đừng giả định tên role do container cấp sẽ khớp trực tiếp với prefix Spring Security trong mọi deployment. Ở business code, các kiểm tra phức tạp nên dùng method security/authorization service có chính sách nhất quán thay vì chỉ kiểm `isUserInRole` ở một controller rồi bỏ sót API khác.

### 9.2. SecurityContextHolder không phải “session tự động”

`SecurityContextHolder` thường mang thông tin xác thực của request đang chạy. Việc lưu `SecurityContext` giữa các request còn phụ thuộc `SecurityContextRepository`, session policy và cơ chế authentication filter. Khi tự xây login hoặc đặt `Authentication` bằng tay trong Spring Security 6, phải hiểu thời điểm **saveContext**. Programmatic Servlet login tích hợp cũng cần test persistence thực tế, như test trong mục 8.

Một app API stateless với bearer token có thể không có session để invalidate; `request.logout()` khi đó không thể biến một access token ở client thành token không hợp lệ. Phải phân biệt **logout phiên web** và **token revocation**.

## 10. Những lỗi thiết kế và cách xử lý

**Lỗi 1 — Gọi authenticate rồi ghi response khi đã challenge.** Sau `request.authenticate(response) == false`, redirect/401 có thể đã được gửi; viết thêm JSON tạo double-commit hoặc response không nhất quán. Kiểm tra boolean và `isCommitted()` trước khi ghi tiếp.

**Lỗi 2 — Dùng authenticate để “kiểm tra đăng nhập” mà không muốn redirect.** Nếu chỉ muốn đọc trạng thái để hiển thị UI, dùng `getUserPrincipal()` hoặc Spring Security authentication state. `authenticate` có tác dụng kích hoạt mechanism.

**Lỗi 3 — Đặt login vào GET/query string.** Password dễ lộ trong logs, lịch sử trình duyệt, proxy và analytics. Dùng POST body trên HTTPS, CSRF với session browser, giới hạn brute force, không log credentials.

**Lỗi 4 — Thêm request.login khi chỉ cấu hình OIDC.** API nhận username/password nhưng `AuthenticationManager`/container không có cơ chế xác thực tương ứng. Cần chọn form login chuẩn hoặc dùng redirect OIDC theo contract, không tự thu thập mật khẩu IdP.

**Lỗi 5 — Giả định login thành công trong một request nghĩa là request tiếp theo đã login.** SecurityContext repository, session policy, SaveContext, authentication strategy và filter chain có thể khác. Test qua hai HTTP requests thực, xem session fixation và cookie.

**Lỗi 6 — Gọi request.logout rồi tuyên bố đã logout toàn bộ SSO.** Local session, IdP session và refresh/access tokens là các trạng thái riêng. Cần RP-initiated logout/Single Logout, token revocation hoặc expiration theo thiết kế.

**Lỗi 7 — Cho logout qua GET để dễ nhấp link.** Logout là thay đổi trạng thái, dễ bị kích hoạt ngoài ý muốn. Ưu tiên POST với CSRF token hợp lệ cho web session.

**Lỗi 8 — Bỏ qua yêu cầu phân quyền sau authenticate.** `authenticate` chỉ xác minh caller; role/resource authorization phải được kiểm tra riêng.

**Lỗi 9 — Dùng `web.ignoring()` cho controller muốn tích hợp Servlet API.** Request có thể không đi qua các filter Spring Security và không được bao, dẫn tới principal và logout behavior khác dự kiến.

**Lỗi 10 — Trộn nhiều chain/filter/entry point.** Một chain dùng form login cho browser, chain khác dùng Basic hoặc bearer token cho API có challenge khác nhau. Cần xác định chain xử lý URL và test status/redirect/cookie trên endpoint đó.

**Lỗi 11 — Tin request wrapper là boundary duy nhất.** Nếu container realm, reverse proxy hoặc gateway đã xác thực, cần đảm bảo request trực tiếp không bypass identity enforcement và header forwarded không giả mạo được. Spring Security không tự xác minh header `X-User` tùy ý của client.

**Lỗi 12 — Đánh đồng CSRF 403 với “mật khẩu sai”.** Với POST login/logout, thiếu CSRF token khiến request có thể bị chặn **trước controller**. Theo dõi đúng filter/event, không mở CSRF toàn hệ thống để che lỗi.

## 11. Thiết kế test matrix cho ứng dụng thực tế

| Trường hợp | Kỳ vọng | Bằng chứng cần có |
|---|---|---|
| Anonymous GET public | 200 | Không có principal vẫn xem được tài nguyên public |
| Anonymous GET protected | 302 login hoặc 401 theo entry point | Không trả dữ liệu protected |
| request.authenticate khi đã login | `true` / handler tiếp tục | Principal hợp lệ, response không bị challenge lại |
| request.authenticate khi chưa login | `false` / challenge tùy cơ chế | Không viết body nghiệp vụ sau entry point |
| request.login đúng password | Thành công | Principal đúng trên request hiện tại **và request kế tiếp** khi có session |
| request.login sai password | Không tạo phiên | Lỗi chung, không lộ thông tin tài khoản |
| POST login thiếu CSRF | Bị từ chối ở CSRF filter | Handler login không xử lý credentials |
| POST login có CSRF | Được đánh giá bởi authentication manager | Kiểm tra status và session/cookie |
| request.logout ở phiên hiện tại | Xóa context/session theo contract | Request sau không còn quyền; session invalidation nếu có |
| POST logout thiếu CSRF | Bị chặn | Không phá phiên ngoài ý muốn |
| Request có role không đủ | 403 | Authentication có thể thành công nhưng authorization vẫn deny |
| User dùng OIDC/SAML | Local logout không mặc định logout IdP | So sánh IdP session với app session |
| API stateless dùng bearer token | Không dùng session logout để thu hồi token | Token còn hiệu lực/đã bị revoke theo chính sách riêng |
| Container realm lỗi | Không cho phép bypass | Request không giả danh principal qua header hay alternate URL |

Để điều tra cần log **request ID, endpoint, auth mechanism, kết quả xác thực, loại lỗi và thời điểm**. Không log raw password, `Authorization`, session ID, one-time token hoặc toàn bộ exception có chứa dữ liệu nhạy cảm. Hãy phân biệt status do Spring Security filter, Servlet container, Spring MVC và proxy phát ra.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `request.authenticate(response)` có thể trả `false` dù không ném exception?

**Trả lời:** Cơ chế authentication đã khởi động challenge/redirect nhưng chưa hoàn thành. Controller không được giả định caller đã đăng nhập hoặc ghi response tiếp.

**Câu 2.** Nếu `request.login("learner", "password")` thành công, có phải đã thực hiện MFA?

**Trả lời:** Không. Nó chỉ xác thực theo provider/realm đang cấu hình với credential cung cấp. MFA/step-up là chính sách riêng và phải được thực thi/kiểm chứng.

**Câu 3.** Vì sao người dùng bị 403 khi POST programmatic login mà log controller không có gì?

**Trả lời:** Spring Security CSRF filter có thể từ chối POST không có token **trước khi tới controller**. Cần lấy token đúng thay vì tắt CSRF.

**Câu 4.** Tại sao `request.logout()` không thể đăng xuất mọi phiên OAuth2/OIDC ở các app khác?

**Trả lời:** Nó làm việc với trạng thái xác thực mà Servlet/container/Spring Security ứng dụng hiện tại quản lý. Phiên IdP, ứng dụng khác và token còn hiệu lực là các trạng thái độc lập; muốn hủy phải có giao thức/quy trình liên quan.

**Câu 5.** Có thể gọi `request.login` trong controller không đi qua Spring Security filter chain không?

**Trả lời:** API Servlet vẫn tồn tại, nhưng thành công lúc đó phụ thuộc cơ chế container/realm; không có đảm bảo nó cập nhật `SecurityContextHolder`. Cần xác định request wrapper và security owner của endpoint trước khi thiết kế.

**Câu 6.** Khi nào dùng `request.authenticate(response)` thay vì chỉ kiểm tra `getUserPrincipal()`?

**Trả lời:** Khi nghiệp vụ thực sự muốn **khởi động cơ chế authentication** nếu chưa xác thực. Nếu chỉ cần đọc trạng thái đăng nhập mà không challenge, dùng getter/authentication state thay vì phương thức có tác dụng phụ.

## 13. Checklist và ghi nhớ

- [ ] Biết Servlet container hay Spring Security đang xử lý lời gọi `authenticate/login/logout`.
- [ ] Endpoint đã đi qua đúng `SecurityFilterChain`; `SecurityContextHolderAwareRequestFilter` có hiệu lực khi cần.
- [ ] `authenticate` không ghi response sau khi entry point xử lý challenge; không coi `true` là đủ quyền nghiệp vụ.
- [ ] `login` chỉ nhận credentials trên HTTPS POST body, có CSRF với browser session, rate limit và thông báo lỗi chung.
- [ ] Có user store/provider/realm phù hợp để `login` thực sự xác thực; không tự tạo Authentication chưa được kiểm chứng.
- [ ] Test security-context persistence, session fixation, logout handlers và cookie lifecycle trên **request tiếp theo**.
- [ ] Logout được gọi qua POST có CSRF; phân biệt local session, IdP session, remember-me và bearer token.
- [ ] Có test quyền thấp/quyền cao, lỗi CSRF, password sai, phiên hết hạn, nhiều chain và reverse proxy.
- [ ] Không log credential/token/session ID; audit outcome bằng request ID.
- [ ] Không dùng API Servlet như đường tắt để bỏ qua MFA, authorization hay filter chain.

**Tóm tắt:** `HttpServletRequest.authenticate(response)` **yêu cầu đảm bảo xác thực hoặc kích hoạt challenge**; `login(username,password)` **yêu cầu xác thực bằng credentials theo chương trình**; `logout()` **yêu cầu xóa trạng thái xác thực hiện hành**. Trong Spring Security Servlet, các phương thức này có thể được tích hợp qua request wrapper, nhưng tính đúng đắn còn phụ thuộc `AuthenticationManager`, entry point, `SecurityContextRepository`, session, logout handlers và quy tắc phân quyền. Với login/logout browser thông thường, ưu tiên filter tiêu chuẩn `formLogin()` và `logout()`; dùng Servlet API khi có nhu cầu tích hợp cụ thể và có kiểm thử end-to-end.