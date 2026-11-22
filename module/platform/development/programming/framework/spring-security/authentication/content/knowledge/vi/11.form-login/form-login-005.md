# CSRF token trong biểu mẫu đăng nhập

> **Chủ đề:** Spring Security — authentication. **Nhóm:** Đăng nhập biểu mẫu. Bài học giải thích vì sao ngay cả form **đăng nhập chưa có người dùng xác thực** vẫn cần chống Cross-Site Request Forgery (CSRF); Spring Security tạo, lưu, đưa vào biểu mẫu và xác minh CSRF token thế nào; cách thực hiện với trang login mặc định và Thymeleaf tùy biến; vì sao POST thiếu token bị **403 trước khi kiểm mật khẩu**; cách kiểm thử, xử lý token sau login/logout, session timeout và cấu hình nhiều filter chain. Phần lab dùng Java 17, Spring Boot 3.5.16 và Spring Security 6.5.x. Các phiên bản được cố định để tái hiện bài học; với dự án mới hãy chọn nhánh còn được hỗ trợ và cập nhật bản vá.

## 1. Bạn sẽ học được gì?

Sau bài này, người học có thể:

1. Phân biệt **authentication**, **authorization**, **CSRF protection**, **CORS**, **SameSite cookie** và **XSS**; hiểu CSRF token không phải mật khẩu hay access token.
2. Mô tả một cuộc tấn công **login CSRF** và tại sao `POST /login` cần token **trước khi** `UsernamePasswordAuthenticationFilter` kiểm chứng username/password.
3. Nêu đúng vai trò của `CsrfFilter`, `CsrfTokenRepository`, `CsrfTokenRequestHandler` và `CsrfToken`; phân biệt lưu trữ token với giá trị token được render.
4. Giải thích `HttpSessionCsrfTokenRepository` mặc định, session cookie, tham số `_csrf`, header CSRF, safe/unsafe HTTP methods.
5. Viết login form dùng Thymeleaf `th:action` để Spring Security tự chèn hidden CSRF input; hoặc chèn thủ công qua `_csrf.parameterName`/`_csrf.token` khi view technology không tự hỗ trợ.
6. Dự đoán kết quả của POST login **thiếu/sai/đúng CSRF token**, kể cả khi username/password đúng hay sai.
7. Hiểu cơ chế deferred CSRF và `XorCsrfTokenRequestAttributeHandler` (BREACH protection) ở Spring Security 6, tránh hardcode và tránh so sánh bừa giá trị token qua các lần GET.
8. Nhận biết CSRF token thường bị xóa sau **đăng nhập thành công** và **đăng xuất**, nên SPA/form cần lấy token mới theo lifecycle phù hợp.
9. Tạo ứng dụng Spring Boot có custom login view, trang sau đăng nhập và logout form, cùng bộ kiểm thử `MockMvc` dùng `csrf()`/`csrf().useInvalidToken()`.
10. Chẩn đoán HTTP 403, login redirect, 404, hết session, khác origin, lỗi reverse proxy và cấu hình nhiều `SecurityFilterChain`.

## 2. CSRF là gì? Vì sao form login cũng có nguy cơ?

### 2.1. Tấn công dựa vào credentials mà browser tự gửi

Một trình duyệt có thể tự gửi cookie xác thực đến một website khi người dùng truy cập hoặc gửi một số loại request tới website đó. Website độc hại có thể tạo HTML form trỏ sang website đích và tìm cách làm trình duyệt nạn nhân gửi request **mà nạn nhân không chủ động thực hiện**.

Ví dụ ứng dụng ngân hàng đang dùng session cookie:

~~~text
Nạn nhân đang có session cookie cho bank.example
  |
  +-- Mở trang độc hại ở evil.example
          |
          +-- Trang độc hại tự submit POST tới bank.example/transfer
                  |
                  +-- Browser có thể tự mang cookie đi theo request
                          |
                          +-- Nếu server chỉ tin session cookie:
                              thao tác chuyển tiền có thể xảy ra
~~~

CSRF token được đặt vào **một phần request mà trang khác origin không thể tự đọc và sao chép theo cơ chế bình thường**, ví dụ hidden form input hoặc header do JavaScript cùng origin bổ sung. Server đối chiếu nó với token kỳ vọng và từ chối request không có bằng chứng phù hợp.

**Lưu ý:** CORS, SameSite cookies và cơ chế browser có thể giảm một số đường tấn công, nhưng không được xem là thay thế phổ quát cho CSRF protection của ứng dụng dùng browser credentials. Khi có XSS trên chính origin đáng tin, kẻ tấn công có thể đọc token; CSRF token **không** giải quyết XSS.

### 2.2. Login CSRF khác “đánh cắp mật khẩu”

Tấn công **login CSRF** là trường hợp attacker ép trình duyệt nạn nhân **đăng nhập vào account mà attacker kiểm soát** trên ứng dụng đích, thay vì account của nạn nhân. Sau đó nạn nhân có thể tưởng đang dùng account của mình và tạo dữ liệu/hành động trong account của attacker. Kẻ tấn công có thể xem những dữ liệu được lưu trong account do mình sở hữu.

~~~mermaid
sequenceDiagram
    participant A as Attacker Site
    participant B as Victim Browser
    participant S as Target Application
    A->>B: Trang chứa form POST /login
    Note over A,B: Credentials của account attacker
    B->>S: POST /login tự động, không CSRF token hợp lệ
    alt Không kiểm CSRF
        S-->>B: Tạo session đăng nhập account attacker
        Note over B,S: Nạn nhân thao tác trong account không mong muốn
    else Spring Security CSRF bật
        S-->>B: HTTP 403, không xác thực theo form
    end
~~~

Tấn công không nhất thiết cần biết mật khẩu của nạn nhân. Chính điều đó lý giải tại sao **“user chưa login nên không cần CSRF” là kết luận sai**. Spring Security documentation nhấn mạnh yêu cầu bảo vệ chính **login requests**.

### 2.3. CSRF không giải quyết những gì?

| Cơ chế | Trả lời câu hỏi gì? | Có thay CSRF token cho form login? |
| --- | --- | --- |
| Password verification | Credential có khớp account không? | Không |
| CSRF token | Request thay đổi trạng thái có đến từ flow hợp lệ của client không? | Chính nó |
| Session cookie | Browser có phiên đã đăng nhập nào? | Không, cookie có thể tự được gửi |
| Authorization | Account này được thao tác tài nguyên không? | Không |
| CORS | JavaScript từ origin khác được đọc/gửi loại cross-origin request nào? | Không phải thay thế tổng quát |
| SameSite cookie | Browser hạn chế cookie trong một số cross-site contexts | Defense-in-depth, không thay thế trong mọi kịch bản |
| MFA | Xác nhận thêm yếu tố đăng nhập | Không thay thế CSRF protection |
| XSS defense | Ngăn script độc hại chạy trên trusted origin | Liên quan nhưng giải quyết rủi ro khác |

CSRF token **không chứng minh mật khẩu đúng**. Một request có token đúng vẫn phải được `AuthenticationManager` xác thực; một request có mật khẩu đúng nhưng thiếu token vẫn có thể bị chặn.

## 3. CsrfFilter kiểm token trước form authentication

Khi CSRF bật, `CsrfFilter` nằm trong security filter chain của Spring Security. Với request cần protection, nó kiểm token trước khi request đi tới `UsernamePasswordAuthenticationFilter`.

~~~mermaid
flowchart TD
    A["Browser POST /login"] --> B["FilterChainProxy chọn SecurityFilterChain"]
    B --> C{"CsrfFilter: method cần CSRF?"}
    C -->|Không, safe method| D["Chuyển tiếp filter chain"]
    C -->|Có, ví dụ POST| E["Lấy CsrfToken kỳ vọng từ repository"]
    E --> F["Resolve token request: _csrf/header"]
    F --> G{"Token hiện diện và hợp lệ?"}
    G -->|Không| H["AccessDeniedHandler: thường 403"]
    G -->|Có| I["UsernamePasswordAuthenticationFilter"]
    I --> J{"Username/password hợp lệ?"}
    J -->|Không| K["AuthenticationFailureHandler"]
    J -->|Có| L["Session/Context success handling"]
~~~

Thứ tự trên quan trọng trong việc debug: `POST /login` bị 403 có thể **chưa hề gọi `UserDetailsService` hoặc `PasswordEncoder`**. Đừng vội kết luận mật khẩu sai khi chưa kiểm CSRF.

### 3.1. Các HTTP methods thường được kiểm

Với cấu hình Servlet CSRF mặc định, các method được coi là safe là **GET, HEAD, TRACE, OPTIONS**; những phương thức khác, bao gồm **POST, PUT, PATCH, DELETE**, thường cần CSRF token.

| Request | Theo matcher mặc định | Ghi chú |
| --- | --- | --- |
| `GET /login` | Không yêu cầu CSRF để được GET | Trang GET có thể *tạo và render* token vào form |
| `POST /login` | Yêu cầu token | Kể cả user chưa xác thực |
| `POST /logout` | Yêu cầu token | Ngăn forced logout |
| `GET /home` | Không yêu cầu token để được GET | GET phải không thực hiện thao tác thay đổi trạng thái |
| `POST /profile` | Yêu cầu token | Dù authorization đã permitAll thì CSRF vẫn có thể kiểm |
| `DELETE /account` | Yêu cầu token | Có thể cần thêm authentication/authorization |
| `OPTIONS /api` | Thường không yêu cầu CSRF | CORS preflight không phải hành động nghiệp vụ |

Không thiết kế **GET có side effect** chỉ để né CSRF. Một đường `GET /logout` thực thi logout hoặc `GET /delete` xóa dữ liệu sẽ phá giả định về safe methods.

### 3.2. 403 khác 401 và redirect login

- **403 do CSRF:** token request bị thiếu hoặc không hợp lệ; `CsrfFilter` từ chối trước authentication.
- **Redirect `/login?error`:** form POST đã qua kiểm CSRF nhưng mật khẩu sai/account status không đạt; failure handler của form login xử lý.
- **Redirect `/home`:** có token hợp lệ, credential hợp lệ và success handler đưa tới trang sau đăng nhập.
- **401:** thường thấy ở HTTP Basic/Bearer endpoints khi chưa có hoặc sai credential, không phải default response cần có của form login.
- **404:** có thể do login processing URL nằm ngoài chain hoặc custom GET page không được triển khai.

**Không đồng nhất 403 với thiếu ROLE_ADMIN**. 403 cũng có thể do `MissingCsrfTokenException`/`InvalidCsrfTokenException`; tìm đúng filter và request trước khi kết luận.

## 4. CsrfToken, CsrfTokenRepository và request handler

Spring Security tách các trách nhiệm liên quan token:

| Thành phần | Vai trò |
| --- | --- |
| `CsrfToken` | Chứa parameter name, header name và token value dùng trong request |
| `CsrfTokenRepository` | Tạo, tải và lưu token kỳ vọng |
| `HttpSessionCsrfTokenRepository` | Repository mặc định trong servlet form app, giữ token ở HTTP session |
| `CookieCsrfTokenRepository` | Lựa chọn dùng cookie, phổ biến với JavaScript frameworks; cần cấu hình handler đúng |
| `CsrfTokenRequestHandler` | Cách token được expose ra request và cách lấy token do client gửi tới |
| `XorCsrfTokenRequestAttributeHandler` | Handler mặc định trong Spring Security 6; bảo vệ khi render token bằng cơ chế masking chống BREACH |
| `CsrfFilter` | Kiểm method, tải/resolve/so sánh token và từ chối hoặc cho đi tiếp |
| `CsrfAuthenticationStrategy` | Dọn token cũ khi authentication success |
| `CsrfLogoutHandler` | Dọn token cũ khi logout |

### 4.1. Tên parameter và header mặc định

Với `HttpSessionCsrfTokenRepository` thông thường:
- Form parameter name: `_csrf`.
- Header name: `X-CSRF-TOKEN`.
- Token: một chuỗi khó đoán, do server sinh và lưu theo session/policy.

Ví dụ HTML render thực tế **chỉ để hiểu format**:

~~~html
<input type="hidden"
       name="_csrf"
       value="example-per-request-masked-csrf-value"/>
~~~

Không copy chuỗi ví dụ này vào một ứng dụng. **Server phải tạo và render token thật** gắn với flow/session đúng; token hardcode hoặc token chung toàn hệ thống không có ý nghĩa bảo vệ.

### 4.2. Vì sao hidden input quan trọng?

Browser tự gửi session cookie theo chính sách cookie, nhưng nó không thể tự biết **token của một trang HTML cùng origin** nếu chỉ được dẫn bởi trang của attacker. Trong synchronizer-token pattern, việc token nằm trong body parameter hoặc header do trusted page tạo khiến một cross-origin form giả không có dữ liệu cần để qua CSRF check.

Đừng đưa token vào query string, URL redirect, Referrer, log hoặc analytics khi có lựa chọn form body/header. Query string dễ bị lưu trong history, proxy logs và các hệ thống giám sát.

### 4.3. CSRF token không phải session identifier

`JSESSIONID` là cookie nhận diện HTTP session. `_csrf` là giá trị được kiểm để xác nhận nguồn gửi unsafe request. Hai giá trị khác trách nhiệm:
- Browser gửi đúng cookie session nhưng **không gửi CSRF token hợp lệ**: POST login vẫn bị 403.
- Browser gửi CSRF token từ session khác nhưng cookie trỏ session hiện tại: token không khớp, bị từ chối.
- Browser có token hợp lệ nhưng password sai: không login thành công.

Không copy một token tùy ý từ user A sang form của user B và mong nó có hiệu lực.

## 5. Chu kỳ GET /login → POST /login → GET /home

Ở dạng thông thường với `HttpSessionCsrfTokenRepository`:

~~~text
GET /login
  -> CsrfFilter đưa CSRF token vào request attribute khi view cần dùng
  -> Thymeleaf render hidden field trong HTML form
  -> Token kỳ vọng được quản lý bằng session/repository

Browser gửi POST /login
  -> Session cookie của browser đi kèm
  -> Form body gồm username, password và _csrf
  -> CsrfFilter so sánh token
  -> Token OK thì UsernamePasswordAuthenticationFilter mới kiểm mật khẩu
  -> Nếu thành công: SecurityContext được thiết lập/lưu theo chính sách

GET /home sau login
  -> Session đã authenticated được nạp lại
  -> Trang có form POST như logout cần CSRF token hợp lệ mới
~~~

### 5.1. Vì sao cần GET trước POST?

Một request POST form login thuần gửi từ tab trống hoặc API client không mang token đã được server cấp có thể bị 403. Trong browser flow, **trang login GET** là nơi client hợp lệ nhận token để gửi lại khi submit.

Không cố bỏ CSRF requirement chỉ vì muốn test POST nhanh bằng curl. Với test backend, Spring Security Test có `csrf()`; với browser, để Thymeleaf render form thật; với client non-browser, thiết kế luồng phù hợp dựa trên threat model.

### 5.2. Form được permitAll nhưng CSRF vẫn chạy

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(form -> form
        .loginPage("/login")
        .permitAll()
    );
~~~

`permitAll` cho phép người chưa login xem trang và gửi request tới login processing path theo authorization policy. Nhưng `CsrfFilter` là một filter độc lập. **permitAll không phải `csrf.disable()`**. Vẫn cần token cho POST.

### 5.3. Nếu custom login page không được phép truy cập?

Một lỗi khác: `GET /login` bị yêu cầu authenticated và bị redirect lại `/login` vô hạn. Với `loginPage("/login").permitAll()` và đúng matcher/chain, tránh vòng lặp này. Nhưng `permitAll` cũng không tạo controller GET; khi dùng custom page, developer phải render view.

## 6. Thymeleaf tự thêm CSRF token vào form POST

Spring Security tích hợp với `RequestDataValueProcessor` để các view như **Thymeleaf** và Spring MVC form tags có thể tự đưa hidden CSRF field vào biểu mẫu dùng unsafe method.

### 6.1. Đoạn template khuyến nghị

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8" />
  <title>Đăng nhập</title>
</head>
<body>
  <form th:action="@{/login}" method="post">
    <label>Tên đăng nhập:
      <input name="username" autocomplete="username" />
    </label>
    <label>Mật khẩu:
      <input type="password" name="password"
             autocomplete="current-password" />
    </label>
    <button type="submit">Đăng nhập</button>
  </form>
</body>
</html>
~~~

Khi Spring MVC/Thymeleaf được kết nối đúng với Spring Security, `th:action="@{/login}"` và `method="post"` khiến Thymeleaf thông qua request data value processor **tự thêm hidden CSRF input hợp lệ** khi render form.

Vì vậy trong template chạy được bên dưới, **không thêm hidden field lần thứ hai**. Hai cách “tự chèn tự động” và “tự viết hidden” đều có chỗ dùng; gắn cả hai không phải cách tăng bảo mật và có thể tạo duplicate parameter gây lỗi.

### 6.2. Chèn token thủ công khi view không có auto-integration

Với view technology hoặc server-rendered HTML không dùng `RequestDataValueProcessor`, lấy request attribute `_csrf` và render:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}" />
~~~

Đây là **phương án thay thế**, không gắn cùng form đang được Thymeleaf tự sinh hidden field trong ví dụ chính. Cách diễn đạt `${_csrf.token}` được hiểu **trong Thymeleaf template**, không phải chuỗi JavaScript/browser tự biết từ client.

Mẫu phía trên cũng chỉ có ý nghĩa khi CSRF request attribute tồn tại, token được server cấp và view có thể truy cập nó. Không tự khởi tạo `CsrfToken` bằng giá trị ngẫu nhiên ở controller nhưng không lưu repository.

### 6.3. Form HTML tĩnh thuần không tự có CSRF

~~~html
<form action="/login" method="post">
  <input name="username" />
  <input type="password" name="password" />
  <button type="submit">Sign in</button>
</form>
~~~

Nếu chỉ phục vụ **file HTML tĩnh** không có server template processor hoặc cơ chế lấy token riêng, form này **không tự có `_csrf`**. Kết quả POST với Spring Security CSRF bật thường là 403. Cần render token server-side, hoặc có một flow lấy CSRF token rồi điền vào form phù hợp, không tắt CSRF để che thiếu sót.

### 6.4. Các field username/password không liên quan tên CSRF

Form login mặc định đọc `username` và `password`. Hidden CSRF field thường là `_csrf` nhưng phải theo `CsrfToken.getParameterName()` nếu cấu hình repository khác.

Nếu đổi `usernameParameter("email")` hoặc `passwordParameter(...)`, cần sửa form tương ứng. Nếu đổi `loginProcessingUrl`, phải sửa `th:action`. Ba loại giá trị **username, password và CSRF token** là ba trách nhiệm riêng.

## 7. Lab hoàn chỉnh Java 17: custom login, CSRF, logout và MockMvc

Dự án chạy trên Spring Boot và Spring Security thật. Mục tiêu là xem **403 từ CsrfFilter** trước authentication và chứng minh login thành công khi CSRF + credential đều hợp lệ.

Để tái hiện cụ thể, ví dụ dùng **Spring Boot 3.5.16** (mốc đã phát hành tháng 6/2026; hiện là bản cuối hỗ trợ OSS của dòng 3.5) và JDK 17. Đây là **lab cố định version**, không phải khuyến nghị dùng nhánh đã kết thúc OSS support cho sản phẩm mới; production cần BOM và bản vá của nhánh được bảo trì.

### 7.1. Cấu trúc dự án

~~~text
csrf-form-login-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/csrflogin/
    │   ├── CsrfFormLoginApplication.java
    │   ├── SecurityConfig.java
    │   └── PageController.java
    ├── main/resources/templates/
    │   ├── login.html
    │   └── home.html
    └── test/java/example/csrflogin/
        └── FormCsrfTests.java
~~~

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'csrf-form-login-lab'
~~~

### 7.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-thymeleaf` quan trọng: nếu chỉ có Web và Security nhưng không có template engine, controller trả view name `login` sẽ không tự render trang template tương ứng. `spring-security-test` cung cấp request post-processors `csrf()` để viết các kiểm thử cần thiết.

### 7.4. CsrfFormLoginApplication.java

~~~java
package example.csrflogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfFormLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfFormLoginApplication.class, args);
    }
}
~~~

### 7.5. SecurityConfig.java

~~~java
package example.csrflogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails linh = User.withUsername("linh")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(linh);
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            // CSRF bật mặc định. Ghi tường minh để người học thấy.
            .csrf(Customizer.withDefaults())
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/home", true)
                .failureUrl("/login?error")
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
            );

        return http.build();
    }
}
~~~

Điểm cần quan sát:

1. `@Bean SecurityFilterChain` này **không dùng securityMatcher hẹp**, nên cả `GET /login`, `POST /login`, `GET /home` và `POST /logout` đều đi qua chain có `CsrfFilter`.
2. `requestMatchers("/login", "/error").permitAll()` cho phép xem trang login; **không vô hiệu kiểm CSRF cho POST**.
3. `loginPage("/login")` là **trang tùy biến**. Spring Security **không tự sinh GET**; controller bên dưới chịu trách nhiệm render.
4. `loginProcessingUrl("/login")` cho `UsernamePasswordAuthenticationFilter` xử lý **POST /login**, không cần `@PostMapping("/login")`.
5. `defaultSuccessUrl("/home", true)` cho đường redirect thành công dự đoán được trong test.
6. `failureUrl("/login?error")` tách sai mật khẩu khỏi 403 do thiếu CSRF.
7. `csrf(Customizer.withDefaults())` dùng repository/handler mặc định ở nhánh Security này; không cần tự tạo token trong `@Controller`.
8. `logoutSuccessUrl(...)` chỉ định redirect sau logout; POST logout với CSRF mới là hành động logout.

### 7.6. PageController.java

~~~java
package example.csrflogin;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/home")
    public String home(Model model, Authentication authentication) {
        model.addAttribute("username", authentication.getName());
        return "home";
    }
}
~~~

Controller **chỉ xử lý GET**. POST login/logout là các endpoint do Spring Security filters sở hữu. Một response từ `GET /home` không chứa secret; tên user chỉ để minh họa đã authenticated.

### 7.7. templates/login.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8" />
    <title>Đăng nhập</title>
</head>
<body>
<h1>Đăng nhập</h1>

<p th:if="${param.error}">Tên đăng nhập hoặc mật khẩu không hợp lệ.</p>
<p th:if="${param.logout}">Bạn đã đăng xuất.</p>

<form th:action="@{/login}" method="post">
    <label>Tên đăng nhập:
        <input type="text"
               name="username"
               autocomplete="username" required />
    </label>
    <label>Mật khẩu:
        <input type="password"
               name="password"
               autocomplete="current-password" required />
    </label>
    <button type="submit">Đăng nhập</button>
</form>

<!-- Spring Security + Thymeleaf tự thêm hidden CSRF input
     cho form POST có th:action. Không viết thêm hidden _csrf thủ công. -->
</body>
</html>
~~~

**Giải thích:**
- `th:action="@{/login}"` tạo action URL phù hợp với context của ứng dụng và phối hợp với `RequestDataValueProcessor`.
- `method="post"` khiến form là unsafe method cần CSRF token.
- Hidden `_csrf` được Thymeleaf/Spring Security chèn **khi render**, không cần xuất hiện nguyên văn trong source template.
- `th:if="${param.error}"` và `th:if="${param.logout}"` dùng query parameter để hiển thị thông báo.
- Browser phải giữ cookie/session đúng từ GET login tới POST login; token một session khác thường không hợp lệ.

### 7.8. templates/home.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8" />
    <title>Trang chính</title>
</head>
<body>
<h1>Xin chào, <span th:text="${username}">người dùng</span></h1>

<form th:action="@{/logout}" method="post">
    <button type="submit">Đăng xuất</button>
</form>

<!-- Thymeleaf cũng tự chèn CSRF token cho POST /logout. -->
</body>
</html>
~~~

Sau login success, request GET `/home` render một form logout mới. Trong Spring Security, authentication success có thể **xóa CSRF token đã lưu trước đó**; form mới sẽ lấy token hợp lệ theo repository. Không lưu một token được render ở trang login vào localStorage để dùng vô hạn qua logout/login.

### 7.9. FormCsrfTests.java — kiểm thử đầy đủ

~~~java
package example.csrflogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormCsrfTests {

    @Autowired
    MockMvc mvc;

    private MockHttpSession loggedInSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "linh")
                    .param("password", "demo-password"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/home"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void loginPageRendersCsrfHiddenInput() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"_csrf\"")))
                .andExpect(content().string(containsString("name=\"password\"")));
    }

    @Test
    void protectedPageRedirectsBeforeLogin() throws Exception {
        mvc.perform(get("/home"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void missingCsrfBlocksEvenCorrectCredentials() throws Exception {
        mvc.perform(post("/login")
                    .param("username", "linh")
                    .param("password", "demo-password"))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfBlocksEvenCorrectCredentials() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf().useInvalidToken())
                    .param("username", "linh")
                    .param("password", "demo-password"))
                .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfButWrongPasswordRedirectsToError() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "linh")
                    .param("password", "wrong-password"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void validCsrfAndCredentialsCreateSession() throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(get("/home").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("linh")));
    }

    @Test
    void postLoginHomeRendersCsrfForLogout() throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(get("/home").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void logoutPostWithoutCsrfIsForbidden() throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutPostWithCsrfSucceeds() throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));
    }
}
~~~

**Giải thích sâu về các test:**

- `loginPageRendersCsrfHiddenInput` kiểm đúng **HTML đã render**, không chỉ source template. Nó giúp phát hiện thiếu Thymeleaf integration hoặc quên `th:action`.
- `missingCsrfBlocksEvenCorrectCredentials` và `invalidCsrfBlocksEvenCorrectCredentials` chứng minh **CSRF được kiểm độc lập với password**.
- `validCsrfButWrongPasswordRedirectsToError` chứng minh request đã vượt CSRF nhưng không vượt credential check.
- `validCsrfAndCredentialsCreateSession` gọi **real `UsernamePasswordAuthenticationFilter`, provider và password encoder**.
- `postLoginHomeRendersCsrfForLogout` xác minh form POST xuất hiện ở trang sau login cũng có hidden field.
- Hai test logout phân biệt CSRF failure và logout processing hợp lệ.
- `with(csrf())` là tiện ích của Spring Security Test để mô phỏng CSRF token hợp lệ; nó **không phải** lời khuyên tự hardcode token vào client.

**Chú ý về tính kiểm thử:** `MockMvc` chạy qua Spring Security filters nhưng không mô phỏng toàn bộ browser cookies/redirect của nhiều tab. Để kiểm session affinity/reverse proxy/token rotation trong môi trường triển khai, thêm end-to-end browser test.

### 7.10. Chạy ví dụ

Tại thư mục `csrf-form-login-lab` với JDK 17+ và Gradle thích hợp:

~~~bash
gradle test
gradle bootRun
~~~

Nếu có Gradle Wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

**Kỳ vọng:** chín test phương thức `@Test` pass với cấu hình lab; output Gradle/Boot phụ thuộc JVM và môi trường nên không có một stdout cố định để chép lại. Những status/redirect quan trọng có thể tóm tắt:

| Tình huống | HTTP | Đích hoặc kết quả |
| --- | --- | --- |
| GET `/login` | 200 | HTML custom có hidden `_csrf` |
| GET `/home` chưa đăng nhập | 302 | Redirect đến `/login` |
| POST `/login` đúng mật khẩu, thiếu CSRF | 403 | CsrfFilter từ chối |
| POST `/login` đúng mật khẩu, CSRF sai | 403 | CsrfFilter từ chối |
| POST `/login` sai mật khẩu, CSRF đúng | 302 | `/login?error` |
| POST `/login` đúng mật khẩu, CSRF đúng | 302 | `/home` + authenticated session |
| GET `/home` trong session hợp lệ | 200 | Trang chào user và form logout có token |
| POST `/logout` thiếu CSRF | 403 | Không thực thi logout thành công |
| POST `/logout` với CSRF hợp lệ | 302 | `/login?logout` |

Bạn có thể mở `http://localhost:8080/login` trong browser, xem source **HTML được render** để kiểm hidden `_csrf`; đăng nhập với username `linh` và password `demo-password` chỉ trên local. **Không đưa credential thật hoặc token vào screenshot/log/ticket**.

Nếu muốn quan sát request trong Developer Tools → Network, kiểm:
1. GET /login trả 200 và session cookie phù hợp.
2. Form POST có các parameters `username`, `password`, `_csrf`.
3. POST trả 302/403 như dự kiến.
4. Browser theo redirect và có authenticated session khi thành công.
5. Form logout mới ở /home cũng có CSRF field.
6. Không copy/raw-log token ra bên ngoài môi trường kiểm thử.

## 8. Spring Security 6: deferred token và XOR/BREACH protection

Hai thay đổi quan trọng so với nhiều hướng dẫn Spring Security cũ:

### 8.1. Deferred CSRF token loading

Spring Security 6 mặc định **trì hoãn tải CSRF token** đến khi thực sự cần. Với GET một tài nguyên không render token và không dùng unsafe method, ứng dụng có thể không cần load HTTP session chỉ để đọc token.

Khi GET `/login` render một form POST cần hidden token, view truy cập token nên repository có thể phải tải/tạo nó. Đây là behavior bình thường; không phải GET đột nhiên trở thành request cần kiểm CSRF.

**Hệ quả khi debug:** có thể thấy một GET public không tạo session, còn GET login page có session vì đã cần token để render. Không suy luận “login đã thành công” chỉ từ việc có JSESSIONID cookie trước khi người dùng nhập mật khẩu.

### 8.2. XorCsrfTokenRequestAttributeHandler

Spring Security 6 dùng `XorCsrfTokenRequestAttributeHandler` mặc định để bảo vệ token được đưa vào response trước các kiểu tấn công nén phản hồi như **BREACH**. Giá trị được render có thành phần ngẫu nhiên/masking cho mỗi response, trong khi token kỳ vọng được quản lý bởi repository.

Điểm dễ nhầm:
- Hai lần GET /login có thể render **hai giá trị hidden token khác nhau** dù cùng session còn hợp lệ.
- Không tự kết luận session bị đổi hoặc CSRF bị hỏng chỉ từ khác biệt chuỗi render.
- `XorCsrfTokenRequestAttributeHandler` biết giải quyết token masked khi POST để so với token kỳ vọng.
- Đừng tự bỏ masking chỉ để token “dễ so sánh” hoặc vì một JavaScript client đang dùng sai mô hình.

**Không tự bóc/đoán XOR token để đưa vào controller.** Hãy để Spring Security xử lý thông qua `CsrfTokenRequestHandler`. Với SPA dùng cookie token thô, cần thiết kế handler riêng theo tài liệu Spring Security thay vì áp dụng mù quáng cấu hình MVC form cho JavaScript.

### 8.3. Debug request attribute trong template

Ở server-rendered view, token có thể xuất hiện dưới request attribute `_csrf`. Một snippet Thymeleaf:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}" />
~~~

Nó chỉ dùng khi **không có automatic CSRF field inclusion** ở form đó. Nếu source template của ứng dụng có `th:action` được xử lý bởi Thymeleaf, ưu tiên cơ chế tự tích hợp để tránh duplicate.

## 9. Token lifecycle sau login và logout

### 9.1. CsrfAuthenticationStrategy

Sau authentication thành công, `CsrfAuthenticationStrategy` có thể xóa CSRF token cũ trong repository như một bước bảo vệ. Vì vậy **token của form đăng nhập trước success không nên được tái sử dụng** cho POST sau đăng nhập.

Flow đúng:
1. Browser nhận login page và token A.
2. POST /login với A và credentials đúng.
3. Authentication success có thể dọn A; session/login lifecycle tiếp diễn.
4. Browser được redirect đến /home.
5. /home render một POST form mới, backend cung cấp token mới thích hợp.
6. POST /logout hoặc form thay đổi trạng thái dùng token của flow hiện tại.

Không cần tự gọi `csrfTokenRepository.saveToken(null, ...)` sau mỗi login vì framework đã tích hợp strategy tương ứng trong cấu hình chuẩn. Custom authentication tự tạo cần kiểm lại lifecycle với repository/strategy.

### 9.2. CsrfLogoutHandler

Logout thành công cũng thường xóa CSRF token cũ. Nếu frontend là SPA giữ token trong memory hoặc cookie, nó phải **yêu cầu token mới sau logout** trước unsafe request tiếp theo theo chính sách.

Trang login GET sau logout sẽ có cơ hội render token mới. Vì vậy một tab mở login từ rất lâu có thể gửi token stale, nhất là khi session đã đổi hoặc một tab khác đã đăng xuất/đăng nhập.

### 9.3. CSRF token rotation không đồng nghĩa password/token rotation

CSRF token đổi/xóa không có nghĩa:
- mật khẩu đã đổi;
- access token JWT bị thu hồi;
- quyền user thay đổi;
- người dùng đã bị khóa;
- server đã reset mọi HTTP session.

Đó là lớp bảo vệ request forgery, khác với lifecycle credential, session và authorization.

### 9.4. Trường hợp nhiều tab

Tab A mở /login với token A; Tab B login thành công, làm session/token thay đổi. Khi Tab A gửi form cũ, request có thể bị 403 vì CSRF token stale. Đây là behavior cần UI giải thích: gợi ý **tải lại trang đăng nhập**, không ép user thử đổi mật khẩu liên tục.

Không khắc phục bằng cách chấp nhận token từ mọi session hoặc tắt CSRF vì “nhiều tab khó chịu”. Có thể thiết kế UX refresh token hợp lệ và kiểm tra timeout/session như một phần của sản phẩm.

## 10. CookieCsrfTokenRepository và JavaScript/SPA

`HttpSessionCsrfTokenRepository` phù hợp với server-rendered forms. `CookieCsrfTokenRepository` là lựa chọn phổ biến khi JavaScript client cần đọc token qua cookie như `XSRF-TOKEN` và gửi nó ở header `X-XSRF-TOKEN`.

Nhưng **cookie chứa token không tự chứng minh request hợp lệ**: browser có thể tự gửi cookie, vì vậy JavaScript phải đọc token trong điều kiện same-origin đáng tin rồi gửi **header riêng**. Server phải resolve và so sánh theo cấu hình tương ứng.

Ví dụ khác nhau:

| Trường hợp | Lưu token kỳ vọng | Cách gửi |
| --- | --- | --- |
| Spring MVC + Thymeleaf form | HTTP session mặc định | Hidden parameter `_csrf` tự chèn |
| JSP/Spring form tags | Thường HTTP session | Hidden field do tag library tạo |
| JavaScript fetch trên cùng origin | Session/cookie theo policy | Header `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` |
| SPA dùng `CookieCsrfTokenRepository` | CSRF cookie | JS đọc cookie phù hợp, gửi header; handler cần xử lý BREACH/deferred |
| API client thuần không dùng cookie/auto credentials | Tùy threat model | Có thể không cần CSRF, nhưng vẫn cần authentication/authorization |

Với SPA, Spring Security docs cảnh báo **mặc định XOR request handler và deferred token** có những khác biệt cần tích hợp. Nếu dùng `CookieCsrfTokenRepository.withHttpOnlyFalse()` để JavaScript có thể đọc cookie, bạn đang thay đổi bề mặt bảo mật; chỉ làm khi thật cần và có kiểm soát XSS, cookie policies, origin, CORS và token refresh.

**Không copy cấu hình SPA cookie vào Thymeleaf form lab** nếu không có nhu cầu; nó làm ví dụ khó hiểu và có thể mở rộng khả năng đọc token cho JavaScript không cần thiết.

## 11. CSRF và login form trong nhiều SecurityFilterChain

Nếu ứng dụng có:
- Chain `@Order(1)` `securityMatcher("/api/**")` cho Bearer/Basic.
- Chain `@Order(2)` catch-all cho form login.

Thì `GET /login` và `POST /login` phải vào **web chain chứa `formLogin` và `CsrfFilter`**. `requestMatchers("/login").permitAll()` trong API chain không thể mở rộng matcher `/api/**`.

Ví dụ sai:

~~~java
http
    .securityMatcher("/secure/**")
    .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
    .formLogin(Customizer.withDefaults());
~~~

Nếu chỉ có chain này, form login filter trong chain xử lý `/login` mặc định, nhưng URL đó **nằm ngoài /secure/**. Browser có thể bị redirect sang /login mà filter không có cơ hội phục vụ; nếu không controller/chain nào khác nhận, kết quả là **404**. Đó **không** phải CSRF 403.

Cách sửa là bảo đảm GET page, POST processing và logout URLs được chain tương ứng chọn, hoặc có một web catch-all. Nếu custom `loginPage("/secure/login")` thì phải render GET /secure/login và cấu hình form action trùng `loginProcessingUrl("/secure/login")`. Sau đó CSRF mới được kiểm trong chain thực sự nhận POST.

**Một endpoint không match security chain thì CsrfFilter của chain đó cũng không chạy.** Vì vậy lỗ hổng do matcher sai có thể gây cả lỗi “login không hoạt động” và nguy cơ URL khác được public ngoài ý muốn.

## 12. Xử lý các lỗi login CSRF thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm và sửa |
| --- | --- | --- |
| GET /login 200 nhưng HTML không có `name="_csrf"` | Form tĩnh, thiếu Thymeleaf starter, thiếu th:action/integration | Xem HTML đã render; dùng th:action và đúng template engine |
| POST /login 403 với mật khẩu đúng | Thiếu/sai/stale CSRF token | Network request body, session cookie, CsrfFilter, token handler |
| POST /login redirect `?error` | CSRF đã qua, credential sai hoặc account state | UserDetailsService, PasswordEncoder, failure handler |
| POST /login 302 /home | Login thành công | Kiểm session và protected page, đừng chỉ nhìn 302 |
| GET /login 404 | Custom GET controller thiếu hoặc chain scope sai | Kiểm loginPage, securityMatcher và MVC mapping |
| POST /login 404 | Path không được login filter xử lý, chain khác hoặc method sai | loginProcessingUrl, HTTP method, filter inventory |
| 403 chỉ xảy ra sau khi login ở tab khác | Token cũ đã bị clear/rotate | Refresh form/token và bảo đảm session phù hợp |
| 403 chỉ trên một instance | Session không shared hoặc routing không ổn định | Kiểm sticky session/Spring Session/session store |
| 403 sau idle lâu | Session expired, expected token bị mất | Refresh login page, UX timeout hợp lý |
| GET login bất ngờ tạo session | Rendering token từ HttpSession repo | Hành vi có thể bình thường với token deferred |
| AJAX gửi X-XSRF-TOKEN nhưng 403 | Raw cookie token và XOR handler không tương thích cấu hình SPA | Dùng hướng dẫn SPA Spring Security phù hợp version |
| Login bị redirect vòng lặp | Login page chưa permitAll hoặc chain ownership sai | Cấu hình formLogin(...).permitAll(), route đúng |
| Một form có hai hidden `_csrf` | Manual token field + Thymeleaf auto injection | Chỉ chọn một cơ chế render |
| POST logout 403 | Thiếu token hoặc token cũ | Dùng form POST có CSRF token mới |
| API Bearer vẫn bị 403 CSRF | API chain bật CSRF cho unsafe methods dù không dùng cookie | Đánh giá threat model rồi giới hạn policy per-chain |
| Trang khác origin không gửi được form hợp lệ | Cơ chế CSRF hoạt động | Không tắt bảo vệ chỉ để cho cross-site form |
| PasswordEncoder log không được gọi | CsrfFilter chặn request trước | Debug filter order trước credential logic |

### 12.1. Debug bằng câu hỏi đúng thứ tự

1. Browser thật gửi `GET /login` vào chain nào? Có đúng custom GET handler không?
2. HTML **đã render** có hidden field `name="_csrf"` không? Giá trị có được tạo từ server?
3. Browser có gửi cookie session tương ứng từ GET sang POST không?
4. POST body có parameter name đúng? Có bị proxy/JS serialize làm rơi token không?
5. `CsrfFilter` có từ chối vì missing/invalid token không? Theo log an toàn là 403 hay failure handler?
6. Nếu CSRF pass, `UsernamePasswordAuthenticationFilter` đã nhận đúng URL/method/fields chưa?
7. Sau authentication, request đến URL nào; session/token có bị rotate/clear?
8. Nếu lỗi chỉ khi load balancing, repository có dùng chung/đúng session routing không?
9. Có multiple security chains hoặc `web.ignoring` làm login không đi qua filter dự kiến?
10. Có dấu hiệu XSS/token leak trong logs, URL hoặc monitoring không?

### 12.2. Không log token để “chẩn đoán cho dễ”

CSRF token tuy không phải password nhưng **vẫn cần bảo vệ khỏi vô tình tiết lộ**. Không đưa nó vào URL, console logs, error report, APM trace, analytics hoặc public issue. Khi debug, ưu tiên ghi:
- CSRF token present/absent;
- loại handler/repository;
- tên parameter/header (không phải giá trị);
- HTTP method/path template;
- exception class như `MissingCsrfTokenException`, `InvalidCsrfTokenException`;
- có/không có HTTP session phù hợp;
- request correlation ID không mang bí mật.

Dùng DevTools cục bộ với dữ liệu demo khi cần xem request thực, không chụp màn hình gửi token của người dùng thật.

## 13. Test nào chứng minh điều gì?

### 13.1. Test chỉ có @WithMockUser chưa đủ

`@WithMockUser` đặt một principal test vào security context để test authorization. Nó **không** chứng minh `POST /login` đã đi qua `CsrfFilter`, form processing filter, BCrypt và tạo session thật.

Với login, dùng request `post("/login")` như lab và `csrf()` từ Spring Security Test. Với logout, có thể dùng @WithMockUser để test logout filter riêng, nhưng bài lab dùng session tạo từ một login thực để tránh nhầm phạm vi.

### 13.2. Spring Security Test: valid/invalid/missing CSRF

~~~java
// Những snippet này nằm trong một test class có MockMvc mvc.
mvc.perform(post("/login")
        .with(csrf())
        .param("username", "linh")
        .param("password", "demo-password"))
    .andExpect(status().is3xxRedirection());

mvc.perform(post("/login")
        .with(csrf().useInvalidToken())
        .param("username", "linh")
        .param("password", "demo-password"))
    .andExpect(status().isForbidden());

mvc.perform(post("/login")
        .param("username", "linh")
        .param("password", "demo-password"))
    .andExpect(status().isForbidden());
~~~

`csrf()` mô phỏng valid CSRF token, `useInvalidToken()` mô phỏng sai token và không gọi `csrf()` nghĩa là thiếu token. Test này **không tự xác minh HTML rendering**; vì vậy bộ test chính thêm assertion đối với hidden field trên GET login.

### 13.3. Test không nên assert token raw hai lần GET phải bằng nhau

Trong Spring Security 6, default XOR masking tạo randomness khi token được render. Nếu bạn so:

~~~text
GET /login lần 1 -> hidden value A
GET /login lần 2 -> hidden value B
A != B
~~~

điều đó **không tự chứng minh** session thay đổi, token repository sinh lại hoặc hệ thống bị lỗi. Test đúng tập trung vào:
- form POST với token đúng của flow đó được chấp nhận;
- token thiếu/sai bị từ chối;
- không rò token qua log/URL;
- login/logout dẫn tới token lifecycle hợp lý.

### 13.4. Test nhiều tab và session timeout

Một bài end-to-end browser test có thể:
1. Mở tab A GET /login, thấy form CSRF.
2. Mở tab B GET /login cùng session.
3. Đăng nhập tab B.
4. Thử gửi form cũ tab A.
5. Quan sát lỗi/refresh hợp lý, không tự bỏ kiểm CSRF.
6. Logout, mở lại trang GET login, lấy token mới.
7. Test session hết hạn hoặc cookie bị xóa trước POST; UX nên đưa user tải lại form thay vì báo “mật khẩu sai”.

Kết quả chi tiết phụ thuộc cookie/session/token handling; mục tiêu là test **dữ liệu đúng kỳ vọng và fail-closed**, không cố định mọi flow đều phải là một mã status duy nhất.

## 14. Khi nào có thể cân nhắc bỏ CSRF?

Trong ứng dụng **browser form login dùng session cookie**, không nên bỏ CSRF cho `POST /login`. Việc endpoint được `permitAll` là bình thường và vẫn cần protection.

Một **API thuần non-browser** dùng bearer token ở header mà browser không tự gửi có thể có threat model khác. Khi cân nhắc disable CSRF:
- Xác định client thực và liệu credential có tự được browser đính kèm hay không.
- Phân biệt Bearer header, cookies, HTTP Basic, mTLS và token trong cookie.
- Giới hạn thay đổi vào **chain/path cụ thể** và viết tests tương ứng.
- Không áp dụng chính sách API cho form login của cùng domain nếu form có session.
- Vẫn giữ authentication, authorization, rate limiting, CORS và XSS protection.

Nếu viết:

~~~java
http.csrf(csrf -> csrf.disable());
~~~

thì **toàn bộ chain đang build** không còn CsrfFilter protection theo cấu hình này, không riêng POST API mong muốn. Không copy dòng này vào lab để cho POST /login chạy không cần token.

`ignoringRequestMatchers(...)` có thể bỏ kiểm CSRF đối với một số path đã phân tích, nhưng **đừng đưa `/login` vào danh sách chỉ vì test thấy 403**. Thay vào đó sửa form rendering/session flow.

## 15. Anti-pattern thường gặp

1. **“Chưa login thì không có CSRF.”** Login CSRF vẫn có thể đăng nhập nạn nhân vào account của attacker.
2. **“permitAll nghĩa là bỏ CsrfFilter.”** Sai, authorization và CSRF là hai filter concerns.
3. **“Mật khẩu đúng thì POST /login phải thành công.”** CSRF token còn phải hợp lệ.
4. **“403 ở login nghĩa PasswordEncoder lỗi.”** CsrfFilter có thể từ chối trước password check.
5. **Dùng form HTML tĩnh không có token khi CSRF bật.** POST thường bị 403.
6. **Dùng th:action rồi lại chèn token thủ công y hệt.** Có thể tạo duplicate parameter.
7. **Hardcode một token trong HTML/JavaScript.** Không gắn với session/repository, dễ sai/vô nghĩa.
8. **Đưa CSRF token vào GET query string.** Tăng nguy cơ leak qua history, logs, Referrer.
9. **Tự tạo token ở controller nhưng không lưu repository.** CsrfFilter không thể so với expected token.
10. **Chỉ chuyển JSESSIONID rồi nghĩ đủ cho POST.** Cookie tự gửi, CSRF cần token riêng.
11. **Dùng token tab cũ sau login/logout mà không refresh.** Token cũ có thể bị xóa.
12. **So sánh literal token render qua các GET rồi khẳng định session bị đổi.** XOR/BREACH masking làm token biểu diễn có thể khác.
13. **Bỏ XorCsrfTokenRequestAttributeHandler để “dễ debug”.** Giảm bảo vệ nén phản hồi khi chưa đánh giá.
14. **CookieCsrfTokenRepository.withHttpOnlyFalse() không có lý do.** Tăng khả năng JavaScript đọc cookie không cần thiết.
15. **Xem SameSite cookie là bảo vệ toàn diện.** Browser/cross-origin semantics có giới hạn và threat model phức tạp.
16. **Dùng HTTP GET để logout hoặc đổi dữ liệu.** Phá giả định safe methods.
17. **Dùng `web.ignoring("/login")`.** Có thể bỏ qua chính login processing filter.
18. **Tắt CSRF toàn chain để sửa một form thiếu hidden input.** Đánh đổi bảo vệ cho lỗi view.
19. **Không test POST logout.** Logout cũng thường cần CSRF token.
20. **Tin `@WithMockUser` là test thực login filter.** Không kiểm form processing/credential.
21. **Quên dùng đúng session cookie giữa GET form và POST.** Token session-bound sẽ không khớp.
22. **Không đồng bộ session giữa nhiều node.** Có thể tạo 403 ngẫu nhiên dưới load balancer.
23. **Cho script từ third-party origin đọc token tùy tiện.** Rủi ro leak, cần XSS/CSP/origin policies.
24. **Nhầm CSRF 403 với authorization 403.** Phải xem exception/filter và request.
25. **Tưởng CSRF token là access token.** Nó không cấp quyền truy cập thay Authentication.
26. **Thay đổi loginProcessingUrl mà quên form action.** POST vào route khác, không đến filter.
27. **Chỉ test GET login 200.** Không chứng minh POST có/đúng token.
28. **Thêm token vào URL hoặc error pages.** Có thể ghi lại secret trong logs hoặc browser.
29. **Không cấp UX cho expired session.** User bị 403 khó hiểu sau khi để form mở lâu.
30. **Sao chép cấu hình SPA JavaScript vào Thymeleaf app mà không cần.** Dễ phát sinh handler mismatch.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `POST /login` cần CSRF khi user chưa authenticated?  
**Đáp án:** Để ngăn login CSRF: attacker ép browser nạn nhân đăng nhập vào account do attacker kiểm soát, gây nhầm account và dữ liệu.

**Câu 2.** `permitAll("/login")` có làm mất CSRF check không?  
**Đáp án:** Không. Nó chỉ ảnh hưởng authorization; `CsrfFilter` vẫn kiểm unsafe methods.

**Câu 3.** Form POST có username/password đúng nhưng không có `_csrf`, kết quả gì theo lab?  
**Đáp án:** HTTP 403. Request bị chặn trước credential authentication.

**Câu 4.** POST có CSRF token hợp lệ nhưng password sai?  
**Đáp án:** `CsrfFilter` cho qua; form authentication failure redirect đến `/login?error` theo lab.

**Câu 5.** POST có cả token đúng và password đúng?  
**Đáp án:** Được xác thực, tạo session và redirect đến `/home` theo lab.

**Câu 6.** Trong Thymeleaf, nên dùng `<form th:action="@{/login}" method="post">` để làm gì?  
**Đáp án:** Có URL action đúng và Spring Security/Thymeleaf tự đưa CSRF hidden field thông qua `RequestDataValueProcessor`.

**Câu 7.** Có cần thêm `<input name="_csrf"...>` thủ công vào chính form đã được Thymeleaf auto-inject?  
**Đáp án:** Không. Chọn một cơ chế render để tránh duplicate.

**Câu 8.** CSRF token có giống JSESSIONID hay JWT không?  
**Đáp án:** Không. Nó chứng minh request có token hợp lệ theo repository, không thay identity/session/access token.

**Câu 9.** Vì sao token render ở hai lần GET có thể khác dù session không đổi?  
**Đáp án:** `XorCsrfTokenRequestAttributeHandler` có masking ngẫu nhiên để bảo vệ BREACH trong Spring Security 6.

**Câu 10.** GET /login có cần CSRF token để được phép GET không?  
**Đáp án:** Không theo default safe methods. Nhưng rendering form POST có thể yêu cầu tạo/lấy token để nhúng vào HTML.

**Câu 11.** Spring Security lưu expected CSRF token ở đâu trong servlet app mặc định?  
**Đáp án:** Qua `HttpSessionCsrfTokenRepository` trong HTTP session.

**Câu 12.** Vì sao token trang login trước success không nên giữ dùng cho logout sau success?  
**Đáp án:** `CsrfAuthenticationStrategy` có thể xóa token cũ; trang sau login cần lấy token hợp lệ mới.

**Câu 13.** POST /logout thiếu CSRF có thể xử lý như thế nào?  
**Đáp án:** Thường 403 khi CSRF bật; logout không được thực thi theo request ấy.

**Câu 14.** Dùng CSRF token có ngăn XSS trên site không?  
**Đáp án:** Không. Script độc hại cùng origin có thể đọc token; XSS defense là lớp riêng.

**Câu 15.** Có thể bỏ CSRF chỉ vì gọi API /api/** không?  
**Đáp án:** Không. Cần biết browser có tự gửi cookie/Basic credentials hay không, và chính sách client cụ thể.

**Câu 16.** Một POST từ trình duyệt đúng token nhưng không có password có tự login được không?  
**Đáp án:** Không. AuthenticationManager vẫn phải xác minh credential.

**Câu 17.** `csrf().useInvalidToken()` trong MockMvc thể hiện điều gì?  
**Đáp án:** Request đưa CSRF token không hợp lệ, kỳ vọng CsrfFilter từ chối 403.

**Câu 18.** Người dùng mở tab login qua đêm rồi POST nhận 403; trước tiên kiểm gì?  
**Đáp án:** Session timeout, token stale, session cookie mất/đổi và request handler; không vội bảo user đổi mật khẩu.

## 17. Checklist cho production

- [ ] Form login POST có CSRF protection; không ignore/disable `/login` nếu đang dùng browser session.
- [ ] GET login page trong đúng `SecurityFilterChain` và được `permitAll`.
- [ ] POST login processing URL/method đúng với form action.
- [ ] Dùng CSRF token do Spring Security quản lý, không hardcode.
- [ ] Nếu dùng Thymeleaf, có `spring-boot-starter-thymeleaf` và `th:action` hoạt động.
- [ ] HTML **đã render** chứa hidden `_csrf` đúng, không duplicate.
- [ ] Browser giữ session cookie tương ứng giữa GET form và POST.
- [ ] POST login token thiếu/sai trả 403; token đúng + sai mật khẩu không authenticate.
- [ ] Token đúng + credential đúng tạo session/authentication theo policy.
- [ ] Logout dùng POST với CSRF token phù hợp; không đổi thành GET tùy tiện.
- [ ] Sau login/logout có cơ chế lấy/render token mới; nhiều tab/stale form có UX phù hợp.
- [ ] Không đưa token vào URL, log, analytics hoặc nơi công khai.
- [ ] Dùng HTTPS, cookie policies, chống XSS và CSP phù hợp.
- [ ] Deferred CSRF/XOR handler được giữ đúng version; SPA cookie integration có cấu hình riêng.
- [ ] Không tự suy ra “CSRF không cần” từ nhãn stateless/API/Bearer.
- [ ] Test các trường hợp 200/302/403, session timeout, wrong password, login/logout.
- [ ] Test trên môi trường nhiều node hoặc session store thật nếu production có load balancer.
- [ ] Có phân biệt 403 CSRF, 403 authorization, 401 authentication và 404 handler/chain.
- [ ] Đã kiểm phiên bản Spring Boot/Security được hỗ trợ và các bản vá bảo mật mới nhất.

**Ghi nhớ:** CSRF token trong biểu mẫu đăng nhập không dùng để kiểm mật khẩu; nó xác nhận request POST phù hợp với flow mà ứng dụng đã cấp. Spring Security có `CsrfFilter` để kiểm, `CsrfTokenRepository` để lưu expected token, `CsrfTokenRequestHandler` để đưa/lấy token, và Thymeleaf có thể tự sinh hidden field. Với form login dùng session, **GET trang login → nhận token → POST token + username/password → kiểm CSRF trước → kiểm credential sau** là một chuỗi đầy đủ. Duy trì bảo vệ này cả khi chưa đăng nhập, sau đăng nhập và lúc logout.

### Tài liệu nguồn

- Spring Security 6.5 — **CSRF (Servlet)**: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — **Form Login**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security 6.5 — **Migration: Deferred CSRF and BREACH**: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/exploits.html
- Spring Security 6.5 — **Servlet Authentication Architecture**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — **SecurityFilterChain / Java Configuration**: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — **CsrfFilter Javadoc**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/CsrfFilter.html
- Spring Security 6.5 — **HttpSessionCsrfTokenRepository Javadoc**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/HttpSessionCsrfTokenRepository.html
- Spring Security 6.5 — **XorCsrfTokenRequestAttributeHandler Javadoc**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/XorCsrfTokenRequestAttributeHandler.html
- Spring Security 6.5 — **Spring Security Test**: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Spring Boot 3.5.16 release (June 2026; last OSS 3.5.x): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- OWASP — **Cross-Site Request Forgery Prevention Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
