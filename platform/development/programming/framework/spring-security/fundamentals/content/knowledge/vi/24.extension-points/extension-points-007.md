# Tùy chỉnh phản hồi thành công, thất bại và đăng xuất trong Spring Security

> **Ngữ cảnh:** Spring Security trên **Servlet/Spring MVC**, Spring Boot 3.x, Java 17+. Thuộc nhóm **Điểm mở rộng**. Bài học giải thích đúng các điểm mở rộng của luồng đăng nhập, đăng nhập thất bại và đăng xuất; hướng dẫn tùy biến HTTP response cho giao diện HTML và ứng dụng gọi API, đồng thời giữ nguyên các bảo vệ về phiên, CSRF và xử lý quyền.

## 1. Vì sao cần tùy chỉnh phản hồi?

Spring Security đã có hành vi mặc định hữu ích cho web app dùng form: đăng nhập thành công thường chuyển hướng về trang ban đầu hoặc trang mặc định; thất bại thường trở về trang đăng nhập có báo lỗi; đăng xuất xong được chuyển về trang đăng nhập. Nhưng ứng dụng có thể cần:

- Giao diện HTML: chuyển đến `/dashboard`, `/login?error` hay `/login?logout`; ghi trạng thái cần thiết cho UI.
- SPA hoặc client gọi API: trả **200 với JSON** khi đăng nhập thành công, **401 với JSON** khi sai thông tin đăng nhập, **204 không có body** khi đăng xuất.
- Chính sách nghiệp vụ: phân loại lỗi ở server mà không làm lộ người dùng có tồn tại hay không; ghi sự kiện kiểm toán, xử lý request đã lưu, hoặc đồng bộ trạng thái đăng nhập trên giao diện.
- Phân biệt **đăng nhập thất bại** với việc client chưa đăng nhập khi gọi endpoint khác, và phân biệt logout nội bộ với thu hồi token ở hệ thống ngoài.

Tùy chỉnh phản hồi là thay đổi cách **truyền kết quả đến client** sau khi Spring Security đã xử lý bước xác thực hoặc logout; không có nghĩa handler tùy chỉnh được tự ý bỏ qua cơ chế xác thực, lưu `SecurityContext`, phòng chống session fixation, CSRF hay dọn phiên.

### Mục tiêu học tập

Sau bài này, bạn cần:

1. Xác định đúng `AuthenticationSuccessHandler`, `AuthenticationFailureHandler`, `LogoutHandler` và `LogoutSuccessHandler` trong filter chain.
2. Phân biệt `401` của đăng nhập sai với `401` khi truy cập tài nguyên chưa xác thực, `403` khi thiếu quyền hoặc CSRF sai, và `200/204/3xx` của các phản hồi thành công.
3. Viết cấu hình `SecurityFilterChain` Java 17+ bằng DSL `formLogin`, `logout`, `exceptionHandling`.
4. Duy trì CSRF với session cookie và hiểu vì sao phải lấy token CSRF mới sau login/logout.
5. Kiểm thử luồng: thành công, thất bại, không có CSRF token, đăng xuất và truy cập sau đăng xuất.

## 2. Đặt handler vào đúng giai đoạn

```text
Browser / client
  |
  +-- POST /api/auth/login (username, password, CSRF token)
  |       |
  |       +-- CsrfFilter: yêu cầu token hợp lệ nếu CSRF bật
  |       |
  |       +-- UsernamePasswordAuthenticationFilter
  |                |
  |                +-- AuthenticationManager.authenticate(...)
  |                          |
  |                          +-- SUCCESS
  |                          |      -> session/security-context processing
  |                          |      -> AuthenticationSuccessHandler
  |                          |           -> 302 redirect hoặc 200 JSON
  |                          |
  |                          +-- FAILURE
  |                                 -> AuthenticationFailureHandler
  |                                      -> 302 redirect hoặc 401 JSON
  |
  +-- GET /api/private (chưa xác thực)
  |       -> AuthenticationEntryPoint -> thường 401 hoặc redirect
  |
  +-- GET /api/private (đã xác thực nhưng thiếu quyền)
  |       -> AccessDeniedHandler -> thường 403
  |
  +-- POST /api/auth/logout (CSRF token hợp lệ)
          |
          +-- LogoutFilter -> LogoutHandler(s): dọn phiên/context/token
          |
          +-- LogoutSuccessHandler -> 302 redirect, 204 hoặc 200 JSON
```

Đây là **mô hình khái niệm**, không phải danh sách thứ tự đầy đủ của mọi filter. Các loại xác thực HTTP Basic, Bearer JWT, OAuth2 và form login có thành phần xử lý khác nhau. Thứ tự và khả năng xử lý lỗi còn phụ thuộc `SecurityFilterChain` nào khớp với request.

Bốn tên dễ nhầm:

| Thành phần | Khi nào chạy? | Trách nhiệm chính | Ví dụ phản hồi |
| --- | --- | --- | --- |
| `AuthenticationSuccessHandler` | Bộ lọc xác thực tương ứng báo thành công | Quyết định cách trả kết quả/điểm đến sau đăng nhập | 302 tới dashboard hoặc 200 JSON |
| `AuthenticationFailureHandler` | Một **lần thử đăng nhập** thất bại ở authentication filter | Trả kết quả cho login attempt sai | 302 `/login?error` hoặc 401 JSON |
| `LogoutHandler` | Giai đoạn **thực hiện logout** | Dọn `SecurityContext`, session, remember-me, CSRF, tài nguyên liên quan | Thường không trực tiếp quyết định body cuối |
| `LogoutSuccessHandler` | Sau chuỗi logout handler hoàn tất | Quyết định phản hồi cuối sau logout | 302, 204, 200 JSON |

Các thành phần khác có nghĩa riêng:

- `AuthenticationEntryPoint`: request đến tài nguyên được bảo vệ nhưng cần bắt đầu xác thực; không nhất thiết có **POST login thất bại** trước đó.
- `AccessDeniedHandler`: request bị từ chối vì không đủ quyền, hoặc lỗi như CSRF không hợp lệ được phân loại phù hợp; không phải một lần kiểm tra mật khẩu sai.
- `@RestControllerAdvice`: xử lý exception thuộc vòng đời MVC; các phản hồi do security filter thực hiện thường **không tự đi qua** advice.
- `AuthenticationEventPublisher` hoặc listener: phục vụ việc nhận sự kiện thành công/thất bại tách khỏi servlet response. Dùng sự kiện cho kiểm toán hoặc metric khi hợp lý; handler phản hồi không nên trở thành nơi chứa toàn bộ business logic.

## 3. Hành vi mặc định của form login

Với `formLogin` trên Servlet stack, Spring Security dùng một authentication filter để xử lý thông tin đăng nhập từ biểu mẫu. Mặc định, request xử lý login là **POST `/login`** với các form parameter `username` và `password`; trang login và mục tiêu chuyển hướng có thể do Spring Security sinh/cấu hình.

### 3.1. Đăng nhập thành công

`SavedRequestAwareAuthenticationSuccessHandler` thường được dùng làm handler thành công mặc định. Khi người dùng truy cập một URL yêu cầu xác thực, `ExceptionTranslationFilter` có thể lưu request ban đầu thông qua `RequestCache`. Sau login, success handler ưu tiên đưa họ trở lại URL đã lưu, nếu có, rồi mới dùng đích mặc định.

Ví dụ:

```text
GET /reports/weekly    -> yêu cầu login, lưu request mục tiêu
GET /login             -> hiển thị form
POST /login            -> xác thực thành công
302 Location: /reports/weekly
GET /reports/weekly    -> request mới đã có session xác thực
```

Nếu bạn thay success handler bằng lambda luôn trả JSON 200, redirect được lưu **sẽ không tự xuất hiện** nữa. Đây có thể là điều mong muốn với SPA; client phải tự điều hướng theo contract của API. Nếu muốn giữ hành vi trở về trang ban đầu của website HTML, hãy giữ hoặc cấu hình `SavedRequestAwareAuthenticationSuccessHandler` thay vì viết redirect handler mới một cách vội vàng.

### 3.2. Đăng nhập thất bại

Khi `AuthenticationManager` không chấp nhận thông tin đăng nhập, filter phù hợp gọi `AuthenticationFailureHandler`. Với form login mặc định do Spring Security cấu hình, trình duyệt thường được chuyển hướng về trang đăng nhập có tham số báo lỗi (ví dụ `/login?error`); với handler lỗi được cấu hình khác, status và body có thể thay đổi.

**Không suy rằng mọi login sai đều trả 401:** đó là chính sách thường hợp lý cho API, còn web form redirect thường dùng HTTP 302. Nếu `CsrfFilter` từ chối trước khi tới authentication filter, failure handler **không được gọi** và kết quả thường là 403.

### 3.3. Đăng xuất

Spring Security mặc định hỗ trợ `POST /logout` để thực hiện đăng xuất. Khi CSRF đang bật, `GET /logout` có thể hiển thị trang xác nhận, còn request thực hiện logout cần method và CSRF token phù hợp. Sau cleanup, `LogoutSuccessHandler` mặc định thường redirect đến `/login?logout`.

Chuỗi logout mặc định có thể xử lý session, `SecurityContextHolder`, `SecurityContextRepository`, remember-me và CSRF token thông qua các `LogoutHandler` phù hợp. **Đừng tự thay toàn bộ chuỗi này bằng một controller chỉ gọi `session.invalidate()`** nếu không hiểu các thành phần cần dọn.

## 4. Chọn contract HTTP cho từng loại ứng dụng

Hai kiểu phản hồi có thể đều đúng; chọn theo phương thức gọi và hành vi UI.

| Sự kiện | Web HTML theo điều hướng trang | API/session cho SPA |
| --- | --- | --- |
| Login thành công | 302 tới trang đã lưu hoặc dashboard | 200 JSON như `{"code":"LOGIN_OK"}` |
| Login sai credentials | 302 tới trang có thông báo lỗi | 401 JSON như `{"code":"INVALID_CREDENTIALS"}` |
| Truy cập tài nguyên chưa đăng nhập | 302 tới trang login | 401 `AUTH_REQUIRED` |
| Đã đăng nhập nhưng không có quyền | 403 hoặc trang thông báo tương ứng | 403 JSON `FORBIDDEN` |
| CSRF thiếu/sai | 403 | 403, client phải lấy token phù hợp |
| Logout thành công | 302 `/login?logout` | 204 No Content hoặc 200 JSON |
| Logout bị từ chối vì CSRF | 403 | 403; không giả vờ rằng đã xóa session |

**204 No Content** không được kèm JSON body. Nếu cần trả thông điệp như `{"code":"LOGOUT_OK"}`, hãy chọn 200. Không trả 200 cho login thất bại chỉ để UI dễ xử lý: điều đó làm hỏng semantic HTTP, logging và nhận diện lỗi.

Các JSON trong bài là **ví dụ hợp đồng ứng dụng**, không phải cấu trúc response được Spring Security tự tạo sẵn. Khi dùng API công khai, nên thống nhất schema, content type, status và mã lỗi ổn định.

## 5. Tùy chỉnh kiểu chuyển hướng cho web HTML

Nếu ứng dụng là website server-rendered và muốn tiếp tục sử dụng redirect, một cấu hình ngắn thường đủ:

```java
@Bean
SecurityFilterChain htmlSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form
            .loginPage("/login")
            .defaultSuccessUrl("/dashboard", false)
            .failureUrl("/login?error")
            .permitAll()
        )
        .logout(logout -> logout
            .logoutSuccessUrl("/login?logout")
            .permitAll()
        );
    return http.build();
}
```

Đây là **đoạn cấu hình bên trong lớp `@Configuration`**, cần import `@Bean`, `HttpSecurity` và `SecurityFilterChain`. Khi dùng `loginPage("/login")`, chính ứng dụng phải cung cấp endpoint/view GET `/login` và form POST login có CSRF token. Spring Security không tự tạo HTML cho một custom login page.

Ý nghĩa của `defaultSuccessUrl("/dashboard", false)`:

- `false`: khi có *saved request* hợp lệ, ưu tiên request đó; nếu không, tới `/dashboard`.
- `true`: luôn dùng URL `/dashboard`, kể cả khi có saved request; cân nhắc ảnh hưởng trải nghiệm.
- `failureUrl` thường tương ứng với `SimpleUrlAuthenticationFailureHandler`; thông báo cụ thể nên do UI tạo, tránh đưa exception detail vào query string.

**Không cấu hình đồng thời `defaultSuccessUrl(...)` và một custom `successHandler(...)` rồi trông đợi hai chiến lược cùng điều khiển response.** Handler được cấu hình cuối cùng có thể thay thế chiến lược trước, tùy cách thiết lập; hãy chọn một chính sách rõ ràng và kiểm thử.

### 5.1. Redirect tùy vai trò hoặc ngữ cảnh

Một `AuthenticationSuccessHandler` có thể chuyển tới trang khác nhau theo quyền. Ví dụ logic:

```java
AuthenticationSuccessHandler handler = (request, response, authentication) -> {
    boolean isAdmin = authentication.getAuthorities().stream()
        .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

    response.sendRedirect(request.getContextPath()
        + (isAdmin ? "/admin/home" : "/dashboard"));
};
```

Đoạn này là **minh họa tùy chọn**: phải cấu hình handler vào `formLogin(...successHandler(handler))` và đảm bảo các route đích được bảo vệ tương ứng. Việc redirect theo role **không thay thế** kiểm tra quyền trên route và service. Với trang yêu cầu login thông qua URL ban đầu, chuyển hướng theo role có thể bỏ qua saved request; cân nhắc dùng `SavedRequestAwareAuthenticationSuccessHandler` nếu muốn giữ điều đó.

**Chống open redirect:** không gửi `response.sendRedirect(request.getParameter("next"))` dựa trên URL do client tùy ý cung cấp. Chỉ cho phép path nội bộ/allowlist đã được xác minh, và vẫn dùng authorization ở điểm đến; không cho client ép redirect tới domain lạ hoặc URL có cấu trúc nhập nhằng.

## 6. Demo Spring Boot: JSON cho login, login lỗi, logout

Demo dưới đây tạo một **session-based API** cho cùng origin. Nó minh họa đầy đủ handler ở đúng chỗ. Các request login/logout dùng cookie phiên và CSRF token. Đây là ví dụ học tập; tài khoản/mật khẩu hard-code **chỉ dành cho môi trường local**.

Sơ đồ file:

```text
security-responses-demo/
  build.gradle
  settings.gradle
  src/main/java/com/example/securityresponses/
    SecurityResponsesApplication.java
    SecurityConfig.java
    DemoApiController.java
  src/test/java/com/example/securityresponses/
    AuthResponseTest.java
```

### 6.1. `settings.gradle`

```groovy
rootProject.name = 'security-responses-demo'
```

### 6.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

Cần JDK 17+ và Gradle tương thích với plugin trong ví dụ; nếu dùng Gradle wrapper của dự án, chạy `./gradlew` thay cho lệnh `gradle`. Khi tích hợp vào repo có build logic chung, giữ dependency/version theo hệ thống quản lý phiên bản đang sử dụng.

### 6.3. `SecurityResponsesApplication.java`

```java
package com.example.securityresponses;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityResponsesApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityResponsesApplication.class, args);
    }
}
```

### 6.4. `SecurityConfig.java` — đầy đủ và tự chứa

```java
package com.example.securityresponses;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
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
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, ObjectMapper objectMapper) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/auth/csrf").permitAll()
                .requestMatchers("/api/private").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .loginProcessingUrl("/api/auth/login")
                .successHandler((request, response, authentication) ->
                    writeJson(response, objectMapper,
                        HttpServletResponse.SC_OK,
                        Map.of(
                            "code", "LOGIN_OK",
                            "username", authentication.getName()
                        ))
                )
                .failureHandler((request, response, exception) ->
                    writeJson(response, objectMapper,
                        HttpServletResponse.SC_UNAUTHORIZED,
                        Map.of("code", "INVALID_CREDENTIALS"))
                )
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/api/auth/logout")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT)
                )
                .permitAll()
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, exception) ->
                    writeJson(response, objectMapper,
                        HttpServletResponse.SC_UNAUTHORIZED,
                        Map.of("code", "AUTH_REQUIRED"))
                )
                .accessDeniedHandler((request, response, exception) ->
                    writeJson(response, objectMapper,
                        HttpServletResponse.SC_FORBIDDEN,
                        Map.of("code", "FORBIDDEN"))
                )
            );

        // Không gọi csrf.disable(): session cookie dùng cho trình duyệt.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("learner")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(user);
    }

    private static void writeJson(
            HttpServletResponse response,
            ObjectMapper mapper,
            int status,
            Map<String, String> payload) throws IOException {

        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");
        mapper.writeValue(response.getOutputStream(), payload);
    }
}
```

**Từng phần làm gì:**

- `authorizeHttpRequests`: cho phép lấy CSRF token trước login; `/api/private` bắt buộc authenticated; mọi đường khác bị deny trừ các request login/logout do các configurer tương ứng mở quyền qua `permitAll()`.
- `formLogin.loginProcessingUrl("/api/auth/login")`: filter nhận **POST form-urlencoded** có param `username`, `password`, sau khi đi qua CSRF; **không tự parse JSON** dạng `{"username":"...","password":"..."}`.
- `successHandler`: khi xác thực thành công, trả **200** và JSON có `code`, `username`. Spring Security thực hiện các bước chuẩn về xác thực trước khi handler này viết response; handler không tự ghi `SecurityContext`.
- `failureHandler`: khi credential không đúng hoặc authentication filter báo failure, trả **401** cùng mã lỗi chung, không trả nguyên `exception.getMessage()`.
- `logout.logoutUrl`: dùng `LogoutFilter` của framework; với CSRF bật, logout được thực hiện bằng **POST** có token hợp lệ.
- `logoutSuccessHandler`: sau cleanup, trả **204**, không body. `authentication` của logout success handler có thể `null`, nên không nên phụ thuộc vào nó để khẳng định có phiên hợp lệ trước đó.
- `exceptionHandling.authenticationEntryPoint`: khi một request khác cần login, trả `401 AUTH_REQUIRED`. Trường hợp này **khác** `401 INVALID_CREDENTIALS` khi thử login sai.
- `exceptionHandling.accessDeniedHandler`: trả `403 FORBIDDEN` khi Security từ chối quyền hoặc CSRF. Sản phẩm thật có thể muốn mã lỗi CSRF riêng ở server log, nhưng tránh tiết lộ thông tin không cần thiết.
- `PasswordEncoder` và `UserDetailsService`: tài khoản demo `learner` được lưu mật khẩu BCrypt trong bộ nhớ; dùng database/identity provider của hệ thống thực khi triển khai.
- `ObjectMapper`: serialize JSON đúng, thay vì tự nối chuỗi; mọi response JSON cùng chuẩn ký tự UTF-8 và tránh lưu cache.

**Lưu ý:** mật khẩu demo được cố định chỉ để dễ thử. Tuyệt đối không đưa cấu hình này nguyên trạng lên production. Một số sản phẩm cần trang login HTML hoặc các đường đi khác; khi đổi sang schema JSON, người gọi phải hiểu rõ hợp đồng về session và CSRF.

### 6.5. `DemoApiController.java`

```java
package com.example.securityresponses;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoApiController {

    @GetMapping("/api/auth/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }

    @GetMapping("/api/private")
    public Map<String, String> privateData(Authentication authentication) {
        return Map.of(
            "message", "Hello",
            "username", authentication.getName()
        );
    }
}
```

`/api/auth/csrf` là endpoint lấy CSRF token đã được Spring Security cấp cho request. Kết quả chứa các trường tương đương `token`, `headerName` và `parameterName`. Đối với session-based application, client giữ cookie phiên đi kèm; trên các request ghi dữ liệu phải gửi token trong header/parameter phù hợp. Đây là pattern được tài liệu Spring Security mô tả cho client cần lấy CSRF token chủ động.

**Không nhầm token CSRF với access token:** nó bảo vệ thao tác phụ thuộc cookie/session khỏi cross-site request forgery; không phải credential đăng nhập và không cấp quyền truy cập resource. Client chỉ được coi thành công khi cả cookie/session và cơ chế xác thực phù hợp.

### 6.6. Trình tự HTTP có thể kiểm chứng

Với application vừa chạy ở `localhost:8080`, cần bảo toàn cookie jar **qua toàn bộ các request**. Trên môi trường Bash có `curl` và `jq`, dùng ví dụ sau:

```bash
# 1) Lấy session cookie và CSRF token trước khi login.
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/auth/csrf | jq -r '.token')

# 2) Gửi thông tin login dưới dạng form parameter, kèm CSRF token.
curl -i -c cookies.txt -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  --data-urlencode "username=learner" \
  --data-urlencode "password=demo-password" \
  http://localhost:8080/api/auth/login

# 3) Cookie jar từ login đã lưu phiên đăng nhập.
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/private

# 4) Lấy CSRF token mới sau login (token cũ có thể đã bị xóa).
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/auth/csrf | jq -r '.token')

# 5) Logout bằng POST có token; chỉ 204, không body.
curl -i -X POST -c cookies.txt -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  http://localhost:8080/api/auth/logout

# 6) Session đã logout: đường private không còn trả dữ liệu.
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/private
```

Ở bước 2, code mẫu chỉ hỗ trợ `application/x-www-form-urlencoded`: `--data-urlencode` khiến curl gửi POST form phù hợp. Không thể thay nguyên body bằng JSON rồi kỳ vọng `UsernamePasswordAuthenticationFilter` đọc được. Nếu ứng dụng cần **đăng nhập bằng JSON**, phải triển khai cơ chế chuyển request thành `Authentication` phù hợp và kiểm thử việc lưu security context, session fixation, failure handling; đây là một phần thiết kế authentication khác.

**Kỳ vọng về status/body:** response thành công login chứa `200`, JSON `LOGIN_OK`; GET private chứa `200` và tên `learner`; POST logout `204` và body rỗng; GET private sau logout `401 AUTH_REQUIRED`. Header session cookie và token là giá trị động, không gán cứng hoặc so sánh bằng chuỗi mẫu.

**Thử sai credential riêng biệt:** trước khi login thành công, lấy CSRF token như bước 1 rồi gửi `password=wrong` tới `/api/auth/login`. Kỳ vọng `401 INVALID_CREDENTIALS`, không phải `401 AUTH_REQUIRED`. Nếu bỏ header CSRF, request có thể bị chặn `403 FORBIDDEN` **trước** khi xác thực mật khẩu, nên test đó không đánh giá được failure handler.

### 6.7. Vì sao phải lấy CSRF mới sau login và logout?

Trong Spring Security, các chiến lược như `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` thường loại bỏ token CSRF cũ khi đăng nhập thành công hoặc đăng xuất. Điều này hỗ trợ vòng đời của token liên quan trạng thái authentication. Vì vậy, một SPA/session client nên:

1. Lấy token khi khởi tạo ứng dụng hoặc trước unsafe request đầu tiên.
2. Gửi token cùng cookie session với POST login.
3. **Lấy lại token sau login** trước các unsafe request tiếp theo.
4. Gửi token mới với POST logout.
5. **Lấy lại token sau logout** trước thao tác ghi tiếp theo, nếu giao diện còn cần tương tác.

Với Spring Security 6.x, token CSRF có thể được xử lý qua `XorCsrfTokenRequestAttributeHandler` để chống BREACH. Dùng token mà endpoint được Spring Security trả về; **không tự đoán/chỉnh sửa encoding**. Cách trao đổi CSRF token khác nhau tùy client server-rendered, SPA và cookie repository. Việc cấu hình `CookieCsrfTokenRepository.withHttpOnlyFalse()` để JavaScript đọc cookie còn cần xem xét kỹ handler hỗ trợ SPA và chính sách an ninh của hệ thống; không thay nó cho endpoint session một cách tùy tiện.

## 7. Kiểm thử với MockMvc

Dự án demo đã có `spring-security-test`. Tệp `src/test/java/com/example/securityresponses/AuthResponseTest.java`:

```java
package com.example.securityresponses;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthResponseTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginSuccessReturnsJson200() throws Exception {
        mvc.perform(post("/api/auth/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-password"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("LOGIN_OK"))
            .andExpect(jsonPath("$.username").value("learner"));
    }

    @Test
    void wrongPasswordReturnsJson401() throws Exception {
        mvc.perform(post("/api/auth/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value("INVALID_CREDENTIALS"));
    }

    @Test
    void anonymousPrivateRequestUsesEntryPoint() throws Exception {
        mvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value("AUTH_REQUIRED"));
    }

    @Test
    void missingCsrfTokenReturns403() throws Exception {
        mvc.perform(post("/api/auth/login")
                .param("username", "learner")
                .param("password", "demo-password"))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void logoutReturns204WithoutBody() throws Exception {
        mvc.perform(post("/api/auth/logout")
                .with(user("learner"))
                .with(csrf()))
            .andExpect(status().isNoContent());
    }
}
```

Các test này chứng minh **đúng điểm mở rộng xử lý response**. `with(csrf())` là công cụ test cung cấp CSRF token hợp lệ, không có nghĩa production có thể bỏ việc gửi token. `with(user("learner"))` tạo ngữ cảnh người dùng cho test logout; luồng cookie và session sống thật vẫn cần kiểm chứng bằng HTTP như mục 6.6. Không dùng `@WithMockUser` để “kiểm thử login”: nó có thể bỏ qua quá trình xác thực thông tin đăng nhập cần kiểm tra.

Khi muốn kiểm thử chặt hơn, bổ sung test kiểm tra session persistence sau login thành công, không thể truy cập private sau logout, chống fixation, không có thông điệp lộ credential và thông số cookie trong môi trường thật. `MockMvc` không thay thế hết reverse proxy/HTTPS/browser cookie behavior.

Lệnh chạy ví dụ:

```bash
# Trong project có Gradle wrapper:
./gradlew test
./gradlew bootRun

# Trên máy có Gradle tương thích nhưng chưa tạo wrapper:
gradle test
gradle bootRun
```

Không cần tự biên dịch từng class Spring bằng `javac` vì chương trình dùng dependency và auto-configuration của Spring Boot; Gradle xử lý classpath. Các test không có stdout cố định; kết quả pass/fail được trình chạy JUnit/Gradle tổng hợp.

## 8. Thêm xử lý nghiệp vụ quanh login/logout đúng cách

### 8.1. Trong success handler nên làm gì?

Nên làm:

- Chọn redirect nội bộ hợp lệ hoặc body JSON phù hợp.
- Đọc `Authentication.getName()` hay các authority cần thiết để **hiển thị** thông tin tối thiểu cho UI.
- Kết nối một cơ chế giám sát/kiểm toán an toàn nếu có yêu cầu, sao cho việc ghi metric không vô tình làm hỏng phản hồi xác thực.
- Giữ đúng content type, status và cấu trúc lỗi.
- Nếu dùng request cache, quyết định rõ cách xử lý saved request và việc chuyển trang.

Tránh:

- Tự lưu lại plaintext password hoặc token vào body/log.
- Chỉ gọi `SecurityContextHolder.setContext(...)` theo cảm tính để “hoàn tất đăng nhập”; đây là trách nhiệm của authentication mechanism.
- Đưa quyền tối cao cho user chỉ vì `successHandler` chạy; quyền phải đến từ nguồn xác thực/authorization đáng tin.
- Ghi response rồi tiếp tục gửi redirect/JSON lần thứ hai.
- Chuyển hướng theo URL client cung cấp mà chưa kiểm tra.
- Chạy tác vụ DB/remote call không thiết yếu theo cách làm mọi login bị treo nếu hệ thống ngoài tạm lỗi.

### 8.2. Trong failure handler nên làm gì?

Sai mật khẩu, tài khoản không tồn tại, bị khóa hoặc hết hạn có thể phát sinh các subclass của `AuthenticationException`. Bạn có thể phân loại **ở server** để audit/support, nhưng phản hồi công khai nên tránh giúp kẻ tấn công đoán được tài khoản có tồn tại hay không.

Ví dụ handler trong demo luôn trả một mã chung `INVALID_CREDENTIALS`. Nếu UI cần phân biệt tình huống như “tạm khóa do quá nhiều lần thử”, cần phối hợp với chính sách chống brute force, thông báo tổng quát và kiểm soát kênh thông tin; không trả exception detail raw.

Phân biệt:

- **Login failure**: đã vào filter xác thực, credentials không đạt yêu cầu; `AuthenticationFailureHandler`.
- **Missing CSRF**: request bị chặn trước xác thực; không phải cơ chế báo “sai mật khẩu”.
- **User chưa đăng nhập truy cập /private**: `AuthenticationEntryPoint`.
- **User đã đăng nhập thiếu quyền**: `AccessDeniedHandler`.
- **Lỗi code/DB khi xử lý login**: không tùy tiện đổi mọi exception thành 401; cần điều tra lỗi server và status đúng.
- **HTTP Basic/Bearer**: cơ chế xác thực và challenge header khác form login; không giả định failure handler của `formLogin` chạy cho mọi phương thức.

### 8.3. LogoutHandler và LogoutSuccessHandler khác nhau ra sao?

Một `LogoutHandler` được gọi **để thực hiện hành động dọn dẹp**: session, context, remember-me cookie, dữ liệu phiên liên quan hoặc các side effects đã xác định. Spring Security khuyến nghị `LogoutHandler` thông thường **không ném exception** vì cleanup cần tiếp tục ổn định.

Một `LogoutSuccessHandler` quyết định **response cuối cùng** sau khi cleanup. Ví dụ:

```java
.logout(logout -> logout
    .logoutUrl("/api/auth/logout")
    .logoutSuccessHandler((request, response, authentication) ->
        response.setStatus(HttpServletResponse.SC_NO_CONTENT)
    )
)
```

Đoạn code trên chỉ thay cách trả response; các cleanup handler mặc định của Spring Security vẫn có vai trò. Nếu cần xóa cookie bổ sung, có thể cấu hình:

```java
.logout(logout -> logout
    .logoutUrl("/api/auth/logout")
    .deleteCookies("JSESSIONID", "remember-me")
    .logoutSuccessHandler((request, response, authentication) ->
        response.setStatus(HttpServletResponse.SC_NO_CONTENT)
    )
)
```

Đây là **một phiên bản thay thế** của phần `logout`, không gắn đồng thời cả hai vào chain. Xóa cookie dựa trên `Set-Cookie` phải khớp tên, Path, Domain và đặc điểm của deployment; tài liệu Spring Security lưu ý việc xóa session cookie bằng configurer không được đảm bảo giống nhau ở mọi servlet container. Sau khi response trả 204, client có thể cập nhật local UI state; việc browser thực sự bỏ cookie cần test.

**Không biến `LogoutSuccessHandler` thành nơi duy nhất thu hồi phiên**: nếu cleanup bị bỏ qua, ứng dụng có thể báo `LOGOUT_OK` nhưng request tiếp theo vẫn mang security context hợp lệ. Giữ đường xử lý qua `LogoutFilter` và `LogoutHandler` thay vì tự tạo một endpoint gọi service bất kỳ rồi trả 200.

## 9. Cookie, phiên và an toàn khi logout

### 9.1. Session-based form login

Thành công login thường kết hợp với session cookie (ví dụ `JSESSIONID`), lưu trạng thái xác thực theo kiến trúc ứng dụng. Hệ thống có cơ chế bảo vệ chống **session fixation** và cơ chế lưu `SecurityContext`; tùy chỉnh success handler **không được phá vỡ** chúng.

Điểm cần kiểm tra:

- `Secure`/`HttpOnly`/`SameSite`/`Path`/`Domain` của cookie phù hợp HTTPS và chính sách cross-origin.
- Logout hủy session/context và làm client không còn dùng được thông tin phiên cũ.
- CSRF token được xử lý lại sau login/logout.
- Browser và CDN không cache response chứa thông tin nhạy cảm.
- Nếu ứng dụng chạy qua proxy, cấu hình forwarded headers/trusted proxy đúng; đừng tự suy scheme/host từ header client cung cấp.
- Nếu hệ thống có “remember me”, phải xác minh cookie/token nhớ đăng nhập cũng được dọn.

### 9.2. Stateless JWT/Bearer

Một API dùng access token tự chứa (JWT) và `SessionCreationPolicy.STATELESS` có cơ chế rất khác. Khi client “logout” bằng cách xóa JWT local:

- Client ngừng gửi token, nhưng token đã phát hành **có thể vẫn hợp lệ** cho đến khi hết hạn nếu resource server không có cơ chế từ chối/thu hồi.
- `LogoutFilter` của session không tự revoke mọi access token, refresh token hoặc session của authorization server.
- Nếu cần thu hồi sớm, thiết kế token revocation/denylist/ngắn hạn, quản lý refresh token, và phối hợp provider theo giao thức.
- Với OAuth2/OIDC/SAML, single logout khỏi identity provider là một luồng riêng; chỉ logout session của ứng dụng không đồng nghĩa kết thúc SSO toàn hệ thống.

Không dùng ví dụ session-cookie ở trên như hướng dẫn tự động để xử lý JWT API; xác định rõ stateful hay stateless trước khi chọn handler.

### 9.3. CSRF và logout

Với trình duyệt tự động gửi cookie xác thực, CSRF vẫn cần được xử lý ngay cả khi API trả JSON. **Không tắt toàn bộ CSRF chỉ để POST login/logout thuận tiện hơn.**

Spring Security có các phương án cho client server-rendered, SPA hoặc client không dựa vào cookie. Cách cấu hình cần dựa trên mô hình đe dọa: không phải API nào cũng cần một chính sách y hệt. Với demo cookie session, giải pháp là endpoint lấy CSRF token và gửi token trong header đúng chuẩn.

Đăng xuất bằng `GET /logout` như một hành động thay đổi trạng thái mà không có CSRF là nguy hiểm; có thể dẫn tới logout CSRF. Với mặc định có CSRF, `GET /logout` thường chỉ phục vụ xác nhận, còn POST mới thực hiện logout. Nếu bạn đổi `logoutRequestMatcher`, cần hiểu tác động an toàn trước khi cho GET thực hiện logout.

## 10. Thiết kế UI tránh lỗi thường gặp

### 10.1. Với SPA/session client

Một state machine đơn giản:

```text
APP_START
  -> GET /api/auth/csrf       (giữ cookie + token)
  -> UNKNOWN / ANONYMOUS

LOGIN_SUBMIT
  -> POST /api/auth/login     (form-urlencoded + CSRF)
       200 -> AUTHENTICATED, refresh CSRF, load profile
       401 -> ANONYMOUS, generic credential error
       403 -> CSRF_ERROR, refetch CSRF, retry chỉ khi an toàn
       5xx -> SERVER_ERROR, không giả thành password sai

REQUEST_PRIVATE
  -> 200 -> render data
  -> 401 -> yêu cầu login/refresh auth state
  -> 403 -> insufficient permission, không logout bừa

LOGOUT_SUBMIT
  -> POST /api/auth/logout    (CSRF mới + cookie)
       204 -> clear local auth UI/cache, refetch CSRF nếu cần
       403 -> kiểm tra CSRF/session, không tự tuyên bố logout
       5xx -> trạng thái logout chưa xác định; kiểm tra lại session
```

Với response 204, frontend **không parse JSON**; gọi `response.json()` trên body rỗng có thể gây parse error và làm UI báo logout thất bại dù server đã dọn phiên. Cần phân nhánh theo status.

Một UI nên tránh việc “cứ nhận 401 là logout ngay” khi có nhiều concurrent request và đang refresh CSRF/token. Đánh dấu auth state dựa trên hợp đồng endpoint và phân biệt 401 của login attempt với 401 của protected resource.

### 10.2. Với HTML form

- Dùng `defaultSuccessUrl`/`failureUrl`/`logoutSuccessUrl` khi yêu cầu chỉ là điều hướng.
- Đưa CSRF token vào form POST theo hỗ trợ của framework/template engine.
- Hiển thị thông điệp lỗi thân thiện; không chép nguyên thông điệp internal exception vào URL.
- Bảo đảm trang được chuyển đến có kiểm tra quyền thực tế.
- Sau logout, không để trình duyệt quay lại trang nhạy cảm bằng response được cache; thiết kế cache headers và kiểm tra auth ở server.

### 10.3. Vì sao không nên trộn redirect và JSON ngẫu nhiên?

Một endpoint login mà đôi khi trả 302 HTML, đôi khi 200 JSON tùy `Accept` hoặc header khác cần contract rõ ràng và test riêng. Nếu client là SPA luôn dùng `fetch`, redirect tự động của browser fetch có thể dẫn đến việc client nhận HTML login page và cố parse thành JSON. Nếu app cần cả web UI lẫn API, hãy định nghĩa route/security chain hoặc request matcher cụ thể, hoặc đặt bộ xử lý phản hồi rõ ràng theo loại client. Đừng dựa vào dò đoán header để phân quyền.

## 11. Tùy chỉnh form login và JSON login không giống nhau

Form login mặc định đọc form parameter; thay success/failure handler **chỉ thay hành vi sau authentication**. Nó không biến cơ chế đầu vào thành JSON.

Nếu một SPA gửi:

```http
POST /api/auth/login HTTP/1.1
Content-Type: application/json

{"username":"learner","password":"demo-password"}
```

thì cấu hình `formLogin.loginProcessingUrl(...)` trong demo **không cung cấp sẵn một JSON username/password converter**. Để thiết kế login JSON đúng nghĩa có thể cần một filter `AuthenticationFilter`/`AuthenticationConverter` hoặc cách xác thực chuyên biệt, cùng việc quản lý session, CSRF, failure response, brute-force protection và tests. Không tự viết controller nhận password rồi gọi `SecurityContextHolder.setAuthentication(...)` mà bỏ qua persistence/session strategy.

Tương tự, tùy chỉnh `formLogin.successHandler(...)` không tự áp dụng cho:

- HTTP Basic authentication filter;
- bearer token/JWT resource-server filter;
- OAuth2/OIDC redirect login filter;
- SAML2 login;
- phương thức custom authentication khác.

Mỗi cơ chế có thể có handler riêng hoặc cấu hình adapter tương ứng, ví dụ `oauth2Login(oauth2 -> oauth2.successHandler(...))`; các claim, redirect và logout với nhà cung cấp ngoài cần quy trình riêng.

## 12. Những lỗi triển khai cần tránh

1. **Lạm dụng một handler cho mọi HTTP 401/403:** login sai, chưa login, thiếu quyền và CSRF sai có nguồn gốc khác nhau. Gắn handler đúng filter/extension point.
2. **Vô hiệu hóa CSRF vì không biết lấy token:** nguy hiểm với ứng dụng dùng cookie/session trong browser. Dùng endpoint CSRF hoặc form integration thích hợp.
3. **Tắt security session handling khi đổi response sang JSON:** success handler không thay thế `SessionAuthenticationStrategy`, persistence và session fixation protection.
4. **Trả `204` rồi ghi JSON:** vi phạm ý nghĩa `No Content`; phía client có thể lỗi parser hoặc nhìn response sai.
5. **Quên `return` hoặc ghi hai lần:** handler quyết định response cuối; không vừa `sendRedirect(...)` vừa ghi JSON trong cùng nhánh.
6. **Lộ lý do xác thực quá chi tiết:** công khai “user không tồn tại” so với “password sai” có thể tạo account enumeration.
7. **Dựa vào logout success body để khẳng định thu hồi JWT/SSO:** session logout không đương nhiên thu hồi token hoặc session bên identity provider.
8. **Tự tạo POST `/logout` controller thay `LogoutFilter`:** dễ quên cleanup mặc định, remember-me, CSRF, security context.
9. **Tin rằng handler luôn có `Authentication` khác null:** failure handler không có principal thành công; logout success handler có thể nhận `null`.
10. **Custom redirect tới URL từ query không xác minh:** có thể sinh open redirect và làm người dùng chuyển sang website không tin cậy.
11. **Tưởng `failureHandler` sẽ bắt CSRF invalid:** `CsrfFilter` có thể chặn trước authentication.
12. **Cấu hình nhiều `SecurityFilterChain` không khớp login/logout route:** `securityMatcher` quyết định chain; nếu URL không được chain đúng xử lý, có thể nhận 404, 403 hoặc behavior khó hiểu.
13. **Đăng ký trùng một success/failure handler bằng nhiều configurer rồi không biết cái nào có hiệu lực:** chỉ định một contract, test mỗi route.
14. **Lấy exception message để trả nguyên cho client:** có thể lộ credential, loại tài khoản hoặc thông tin hệ thống.
15. **Chỉ test mock mà không kiểm tra cookie thật:** thay đổi session ID, Path/SameSite/Secure, proxy và logout cookie phải được test bằng browser/live HTTP.

## 13. Checklist QA cho mỗi thay đổi về response

| Mục kiểm tra | Câu hỏi cần xác nhận |
| --- | --- |
| Matching | `POST login` và `POST logout` có khớp đúng SecurityFilterChain và filter? |
| Form body | Param `username`/`password` có đúng tên và content type? Nếu dùng JSON, đã có converter đúng? |
| Login success | Status/body/redirect đúng; cookie/session và context được duy trì; request cache có hợp đồng rõ? |
| Login failure | 401/redirect đúng; không leak thông tin tài khoản; rate limiting/giám sát vẫn hoạt động? |
| Anonymous resource | `AuthenticationEntryPoint` trả 401 hoặc redirect đúng với client? |
| Authorization fail | `AccessDeniedHandler` trả 403, không bị nhầm thành 401? |
| CSRF | Thiếu token bị chặn; token được refresh sau login/logout; browser gửi cookie và header đúng? |
| Logout | `LogoutHandler` mặc định vẫn chạy; cookie/context/session thực sự không sử dụng lại được? |
| Response body | JSON content type đúng; 204 không body; không ghi hai lần? |
| HTTP headers | Cookie an toàn, cache hợp lý, Basic/Bearer challenge không bị mất nếu dùng scheme đó? |
| Integration | Test MockMvc và live HTTP/browser qua cấu hình proxy thực tế? |
| Audit | Log không chứa password, bearer token, raw cookie hay chi tiết lỗi nội bộ? |

### Câu hỏi tự kiểm tra

1. Vì sao `AuthenticationFailureHandler` không xử lý request thiếu CSRF token khi POST login?
2. Khác biệt giữa `AuthenticationFailureHandler` và `AuthenticationEntryPoint` là gì?
3. Vì sao thay `AuthenticationSuccessHandler` bằng JSON response có thể làm mất redirect về saved request?
4. `LogoutHandler` và `LogoutSuccessHandler` có thể thay thế cho nhau được không?
5. Tại sao logout trả `204` thì client không nên gọi `response.json()`?
6. Khi dùng cookie session, vì sao cần lấy CSRF token lại sau login và logout?
7. Vì sao bỏ cookie JWT ở client không bảo đảm JWT đã bị vô hiệu hóa ở server?
8. Nếu ứng dụng dùng `formLogin` mặc định, vì sao body JSON login không tự hoạt động?
9. Khi redirect dựa trên quyền, tại sao vẫn phải bảo vệ route và service?
10. Vì sao thay entry point mặc định của HTTP Basic/Bearer cần giữ đúng các header challenge?

**Gợi ý:** (1) `CsrfFilter` có thể chặn trước authentication; (2) login attempt sai so với request chưa được xác thực cần khởi đầu auth; (3) handler mới không tự dùng `RequestCache`; (4) một bên cleanup, một bên quyết định response sau cleanup; (5) body rỗng; (6) token cũ bị xóa bởi authentication/logout strategy; (7) token vẫn hợp lệ tới khi hết hạn/được thu hồi; (8) filter đọc form params; (9) response routing không cấp quyền; (10) đó là yêu cầu protocol để client xác thực đúng.

## Tài liệu tham khảo chính thức

- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — `AbstractAuthenticationProcessingFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html
- Spring Security — Logout: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
