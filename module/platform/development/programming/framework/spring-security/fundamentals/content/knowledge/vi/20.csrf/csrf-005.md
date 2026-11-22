# Gửi CSRF token trong biểu mẫu hoặc header

> **Spring Security fundamentals → CSRF.** Một ứng dụng có session/cookie đăng nhập cần gửi **CSRF token** trong một trường biểu mẫu (thường mang tên `_csrf`) hoặc trong HTTP header (thường `X-CSRF-TOKEN` hay `X-XSRF-TOKEN`) khi gửi những request thay đổi trạng thái. Bài này trình bày nguyên lý, flow Servlet, code Spring Boot 3.x / Spring Security 6.x / Java 17+, kiểm thử thực tế bằng MockMvc, và những lưu ý cho JavaScript/SPA, BREACH, cookie, logout, session timeout và WebFlux.

## 1. Vì sao CSRF token phải đi kèm request?

Khi một người dùng đã đăng nhập một website bằng cookie, trình duyệt có thể tự gắn cookie phù hợp vào request. Một trang thuộc website khác có thể khiến browser phát request tới website hợp lệ thông qua form, navigation hoặc một số thao tác khác. Nếu backend chỉ nhìn thấy cookie đăng nhập và chấp nhận mọi thao tác, request giả mạo có thể thực hiện thay đổi dưới danh tính nạn nhân.

Ví dụ đoạn HTML sau đến từ **website khác**, không phải một form tin cậy:

```html
<form action="https://accounts.example.org/profile/email" method="post">
  <input type="hidden" name="newEmail" value="other@example.net">
  <button type="submit">Continue</button>
</form>
```

Tùy `SameSite`, chính sách browser và môi trường, request có thể mang cookie đăng nhập của người dùng. Website lạ không cần biết mật khẩu để kích hoạt request.

**Ý tưởng synchronizer token pattern:** Server tạo một token gắn với phiên hoặc ngữ cảnh tin cậy. UI hợp lệ đọc token do server cung cấp rồi gửi nó **qua field trong body hoặc header riêng**. Browser **không tự tạo/gửi field/header đó chỉ vì có cookie**. Server đối chiếu token với giá trị kỳ vọng ở `CsrfTokenRepository` và chặn request thiếu hoặc sai token **trước khi thực hiện mutation**.

```text
Browser có session cookie                  Spring Security
    |                                           |
    | GET /form hoặc GET /csrf                  |
    |------------------------------------------>|
    | trang/JSON chứa CSRF token hợp lệ         |
    |<------------------------------------------|
    |                                           |
    | POST /api/preference                     |
    | Cookie: JSESSIONID=...                   |
    | _csrf=<token>  HOẶC                      |
    | X-CSRF-TOKEN: <token>                    |
    |------------------------------------------>|
    |                                           |
    |             CsrfFilter kiểm tra token     |
    |                    |                      |
    |          +---------+---------+            |
    |          |                   |            |
    |       hợp lệ              thiếu/sai        |
    |          |                   |            |
    |  authentication/        từ chối,           |
    |  authorization/         thường 403         |
    |  controller                               |
```

**CSRF token không thay thế authentication hoặc authorization.** Một request mang token đúng vẫn phải kiểm tra người dùng đã đăng nhập và có quyền sửa tài nguyên hay không. Ngược lại, người dùng đã đăng nhập nhưng không gửi CSRF token đúng vẫn bị từ chối trên request cần protection.

### 1.1. Threat model và phạm vi

CSRF chủ yếu liên quan những credential mà browser **tự gửi** theo ngữ cảnh như session cookie và đôi khi HTTP Basic/cookie-stored token. Nếu một API thuần stateless chỉ chấp nhận Bearer access token được client **chủ động đưa vào `Authorization`**, và không có credential tự động đính kèm, nguy cơ CSRF theo mô hình cookie khác đi. Nhưng endpoint refresh/logout dùng cookie, SPA có session hoặc hệ thống hybrid vẫn cần đánh giá CSRF. Không kết luận “API REST thì luôn tắt CSRF”.

Cookie `SameSite`, Origin/Referer validation, CORS và CSRF token có vai trò bổ sung chứ không hoàn toàn tương đương. XSS trong origin hợp lệ có thể đọc hoặc sử dụng token mà UI được cấp; vì vậy phải phòng chống XSS riêng.

## 2. Request nào cần token và vị trí nào phù hợp?

Theo HTTP semantics, `GET`, `HEAD`, `OPTIONS` và `TRACE` là các method được xem là safe; Spring Security Servlet mặc định thường bỏ qua CSRF cho chúng. Những request `POST`, `PUT`, `PATCH`, `DELETE` được bảo vệ khi CSRF bật.

**Điều kiện quan trọng:** GET phải thực sự không thay đổi dữ liệu. Nếu thiết kế `GET /remove-account` để xóa tài khoản, ứng dụng đã phá vỡ giả định safe method; việc browser prefetch link hoặc một site lạ đưa link/ảnh vào trang có thể gây side effect.

| Client / nội dung | Cách gửi token thường hợp lý | Lưu ý |
|---|---|---|
| HTML form dùng POST | Hidden input `_csrf` trong form body | Value lấy từ server trong đúng session |
| Server-rendered Thymeleaf/JSP | Hidden input tự thêm hoặc tự render | Template engine phải tích hợp CSRF |
| Fetch/AJAX gửi JSON | Header `X-CSRF-TOKEN` | Client phải chủ động đọc token và gửi header |
| Spring SPA dùng CSRF cookie | Cookie `XSRF-TOKEN` được JS đọc rồi đưa vào `X-XSRF-TOKEN` | Cần xử lý raw vs masked token của Spring Security 6 |
| Multipart upload | Ưu tiên header nếu phù hợp | Tránh phải parse body upload trước CSRF filter |
| Backend stateless Bearer | Quyết định theo credential transport | Không bật/tắt CSRF bằng suy đoán |
| Request GET chỉ đọc | Thông thường không cần CSRF | Vẫn phải có authorization nếu private |

**Không đặt CSRF token trong query URL.** URL dễ bị ghi vào access log, browser history, analytics, link preview hoặc Referer. Dùng request parameter trong body hoặc header.

## 3. Các thành phần Spring Security

| Thành phần | Chức năng |
|---|---|
| `CsrfFilter` | Kiểm tra token trên request cần bảo vệ trước khi đi tiếp filter chain |
| `CsrfToken` | Cung cấp `getToken()`, `getParameterName()`, `getHeaderName()` |
| `CsrfTokenRepository` | Sinh, lưu, tìm token kỳ vọng |
| `HttpSessionCsrfTokenRepository` | Lưu expected token trong Servlet `HttpSession`; cơ chế mặc định thông dụng |
| `CookieCsrfTokenRepository` | Dùng cookie chứa token, thường `XSRF-TOKEN` |
| `CsrfTokenRequestHandler` | Expose token cho view và resolve token được gửi từ parameter/header |
| `XorCsrfTokenRequestAttributeHandler` | Mặc định phổ biến trong Spring Security 6, thêm masking để giảm rủi ro BREACH |
| `CsrfTokenRequestAttributeHandler` | Không dùng XOR masking; có vai trò khi xử lý raw token từ header SPA |
| `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` | Có thể xóa token cũ khi authentication/logout thành công |
| `AccessDeniedHandler` | Chọn cách trả lỗi khi bị từ chối, bao gồm lỗi CSRF |

Một request unsafe đi qua logic tương tự:

```text
POST /api/preference
    |
    v
CsrfFilter
    |
    +--> Có cần CSRF không?
    |      |
    |      +--> Không: tiếp tục
    |      |
    |      +--> Có: tải/tạo token kỳ vọng từ repository
    |               |
    |               v
    |          Request handler đọc token
    |          trong _csrf parameter hoặc header
    |               |
    |               v
    |          So khớp với expected token
    |            |               |
    |           đúng             sai/thiếu
    |            |               |
    |         tiếp tục         403 (thường)
    |
    v
Authentication + HTTP/Method/Object authorization
    |
    v
Controller và service
```

Spring Security 6 có cơ chế **deferred CSRF token** để tránh tạo/đọc session không cần thiết. Lời gọi `getToken()` từ view/controller sẽ khiến token cần thiết được load/generate khi thực sự sử dụng.

## 4. Cách 1 — CSRF token trong HTML form

### 4.1. Hidden input

HTML form hợp lệ phải đưa token của server vào chính form gửi request:

```html
<form method="post" action="/api/preference">
  <label for="theme">Theme</label>
  <select id="theme" name="theme">
    <option value="light">Light</option>
    <option value="dark">Dark</option>
  </select>
  <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_RENDER">
  <button type="submit">Lưu</button>
</form>
```

Chuỗi `TOKEN_DO_SERVER_RENDER` trong tài liệu là **minh họa**, không phải token dùng được. Giá trị thật phải được thay bằng `CsrfToken.getToken()` do Spring Security cung cấp cho phiên/view. Form gửi dữ liệu dưới dạng:

```http
POST /api/preference HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-cookie>

theme=dark&_csrf=<token-do-server-cap>
```

Browser tự mang cookie; token được gửi vì nó có trong form hợp lệ mà người dùng đang thao tác. Một form khác đến từ website lạ không biết token gắn với phiên của nạn nhân.

**Không đoán cứng tên field khi ứng dụng đã tùy biến:** `CsrfToken.getParameterName()` cho biết tên hiện hành; `getToken()` trả giá trị cần đưa vào field theo request handler. Giá trị token không nên được cache như một đoạn HTML public dùng cho mọi người.

### 4.2. Thymeleaf và template engines

Với template engine tích hợp `RequestDataValueProcessor` như Thymeleaf trong một số Spring MVC setup, hidden CSRF input có thể được chèn tự động cho form unsafe method. Nếu dùng JSP hoặc render HTML thủ công, có thể truy cập request attribute `_csrf` và đưa field vào.

Khi tự viết, phải bảo đảm:
- Hidden input thật sự nằm **trong form** được submit.
- Không có hai field cùng tên với token khác nhau.
- Value đến từ request/phiên hiện tại, không phải hard-code hoặc một token của user khác.
- Nếu form submit sau khi session hết hạn/login/logout, UI phải lấy token mới.
- HTML escaping phù hợp với template, và response có cache policy đúng cho nội dung riêng phiên.

Một ví dụ JSP-style:

```html
<input type="hidden"
       name="CSRF_PARAMETER_NAME_FROM_REQUEST"
       value="CSRF_TOKEN_VALUE_FROM_REQUEST">
```

Ở đây hai giá trị viết hoa chỉ minh họa vị trí dữ liệu động; thay bằng expression của view engine đang sử dụng, không copy làm literal vào app.

### 4.3. CSRF token không phải khóa bí mật ngăn user xem

Người dùng có thể xem `_csrf` trong DevTools. Đây không phải lỗi: token chống việc origin khác không đọc được nội dung trang hợp lệ, chứ không ngăn chủ phiên quan sát. Nếu người dùng có quyền trên giao diện nhưng không có quyền sửa bản ghi khác, server vẫn phải kiểm tra ownership/tenant/permission.

## 5. Cách 2 — CSRF token trong HTTP header

Ứng dụng dùng fetch hoặc AJAX có thể đọc token qua HTML meta tag hoặc endpoint `GET /csrf`, rồi gửi header khi POST/PUT/PATCH/DELETE.

```http
POST /api/preference HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-cookie>
X-CSRF-TOKEN: <token-do-server-cap>

theme=dark
```

Không cần gửi đồng thời cả `_csrf` và header; chọn một cơ chế nhất quán với repository/request handler. Header không thay cho cookie đăng nhập khi ứng dụng sử dụng session; **cả hai cùng có mục đích khác nhau**.

### 5.1. Header name phụ thuộc repository

| Thiết lập thông dụng | Field name | Header name |
|---|---|---|
| `HttpSessionCsrfTokenRepository` | `_csrf` | `X-CSRF-TOKEN` |
| `CookieCsrfTokenRepository` | `_csrf` | `X-XSRF-TOKEN` |
| Custom repository/handler | Tùy cấu hình | Tùy cấu hình |

Tốt nhất lấy `CsrfToken.getHeaderName()` từ server thay vì giả sử mọi ứng dụng đều dùng `X-CSRF-TOKEN`.

### 5.2. Fetch same-origin

Trong ví dụ chạy ở mục 6, `GET /csrf` cung cấp JSON chứa field name, header name, token; JS có thể dùng:

```javascript
async function updateTheme(theme) {
  const bootstrap = await fetch("/csrf", {
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!bootstrap.ok) {
    throw new Error("Không tải được CSRF token");
  }
  const csrf = await bootstrap.json();

  const response = await fetch("/api/preference", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      [csrf.headerName]: csrf.token,
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body: new URLSearchParams({ theme })
  });
  if (!response.ok) {
    throw new Error("POST bị từ chối hoặc thất bại");
  }
  return response.json();
}
```

Ở đây JavaScript **không tự sinh token**, không dựa vào session ID làm token, và không lưu token trong URL. Nếu token phải được gửi trong JSON request, body JSON vẫn được gửi bình thường; token ở header được `CsrfFilter` xử lý trước controller, không bắt buộc body phải là form-urlencoded.

## 6. Ví dụ Spring Boot 3.x / Java 17+ chạy được

Tạo project với Spring Initializr, Java 17+, chọn **Spring Web** và **Spring Security**. Dùng Gradle Wrapper do project cung cấp.

### 6.1. Dependencies

Trong `build.gradle` của project đã có Boot plugin/repositories:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây **chỉ là khối dependencies**, không phải toàn bộ `build.gradle`. `spring-security-test` cung cấp helper `csrf()`, `csrf().asHeader()` và `user()`.

### 6.2. Tệp Java hoàn chỉnh

Tạo `src/main/java/example/csrf/CsrfFormHeaderApplication.java`:

```java
package example.csrf;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CsrfFormHeaderApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfFormHeaderApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/form", "/csrf", "/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/preference")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/preference")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            // Mặc định bật CSRF. Không gọi csrf.disable().
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}

@RestController
class DemoController {
    private final Map<String, String> themes =
        new ConcurrentHashMap<>();

    @GetMapping("/public/ping")
    String ping() {
        return "ok";
    }

    @GetMapping(value="/form", produces=MediaType.TEXT_HTML_VALUE)
    String form(CsrfToken csrf) {
        return """
            <!doctype html>
            <html lang="vi">
              <head><meta charset="UTF-8"></head>
              <body>
                <form action="/api/preference" method="post">
                  <select name="theme">
                    <option value="dark">Dark</option>
                    <option value="light">Light</option>
                  </select>
                  <input type="hidden" name="%s" value="%s">
                  <button type="submit">Lưu</button>
                </form>
              </body>
            </html>
            """.formatted(
                csrf.getParameterName(), csrf.getToken());
    }

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> csrf(CsrfToken token) {
        // Chỉ cung cấp cho JS cùng origin; tránh shared cache.
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "parameterName", token.getParameterName(),
                "headerName", token.getHeaderName(),
                "token", token.getToken()));
    }

    @PostMapping("/api/preference")
    Map<String, String> update(
            @RequestParam String theme, Authentication auth) {
        if (!"dark".equals(theme) && !"light".equals(theme)) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.BAD_REQUEST,
                "Unsupported theme");
        }
        themes.put(auth.getName(), theme);
        return Map.of("user", auth.getName(), "theme", theme);
    }

    @GetMapping("/api/preference")
    Map<String, String> read(Authentication auth) {
        return Map.of(
            "user", auth.getName(),
            "theme", themes.getOrDefault(auth.getName(), "unset"));
    }
}
```

### 6.3. Diễn giải từng phần

1. `/form` và `/csrf` mở cho anonymous để học cách tải token, nhưng controller không cho user anonymous thay dữ liệu. Với production, thiết kế origin/CORS/cache để token không bị lộ qua cross-origin read.
2. `/api/preference` GET và POST yêu cầu `authenticated()`. `anyRequest().denyAll()` từ chối các endpoint chưa khai báo.
3. `formLogin` của Spring Security có trang login mặc định; cả login POST cũng được CSRF protection bảo vệ.
4. `GET /form` yêu cầu `CsrfToken` từ framework, gọi `getToken()` để kích hoạt token và in hidden field. Với Spring Security 6, giá trị render có thể là **masked** để giảm BREACH.
5. `GET /csrf` trả token theo `headerName` mà client cần gắn vào POST. `Cache-Control: no-store` giảm nguy cơ cache response chứa token phiên.
6. `POST /api/preference` sẽ không được gọi nếu `CsrfFilter` từ chối; sau khi qua filter, vẫn có authentication và ràng buộc theme.
7. Map trong memory chỉ minh họa; không phải storage đa node, không có database hay tenant. Để kiểm tra quy tắc owner/role, phải thiết kế thêm policy ở service/repository.
8. `{noop}` **không hash password**. Chỉ dùng local demo; production dùng password hashing/identity provider, HTTPS, session cookie hardening và audit thích hợp.

### 6.4. Chạy bằng Gradle

```bash
./gradlew bootRun
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
.\gradlew.bat test
```

Chạy từng lệnh theo mục đích: `bootRun` giữ tiến trình server, `test` chạy kiểm thử trong tiến trình Gradle riêng.

Các bước thử trong browser:

1. Vào `http://localhost:8080/login`, đăng nhập `alice/demo123` bằng form mặc định.
2. Mở `http://localhost:8080/form` sau login để lấy CSRF token mới nhất. Token trước login có thể được xóa khi xác thực thành công.
3. Xem HTML thật trong DevTools: hidden input tên `_csrf` phải có giá trị do server cung cấp.
4. Gửi form và nhận JSON tương tự `{"user":"alice","theme":"dark"}` nếu chọn dark.
5. Xóa hidden field rồi submit khi vẫn login: Spring Security phải từ chối request (thường 403).
6. Thử `GET /api/preference` khi đã login: GET không cần token nhưng vẫn đòi authentication.

Khi ứng dụng chạy dưới context path khác root, form action `/api/preference` cần điều chỉnh bằng URL generation của template engine/router. Không copy session cookie hoặc CSRF token thật vào screenshot, issue hay log.

### 6.5. Gửi header bằng curl giữ cùng session

Trên máy local có `curl` và `jq`, khi server chạy:

```bash
csrf="$(curl -fsS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')"

curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "username=alice" \
  --data-urlencode "password=demo123" \
  --data-urlencode "_csrf=$csrf" \
  http://localhost:8080/login

# Refresh token sau đăng nhập, vì token cũ có thể bị xóa.
csrf="$(curl -fsS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')"

curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  --data-urlencode "theme=dark" \
  http://localhost:8080/api/preference
```

Chính `cookies.txt` giữ session giữa việc tải CSRF token và gửi request; token không tự hoạt động ở session khác. Khi dùng tài khoản thật, không lưu lộ cookie jar hoặc token trong lịch sử shell/log. Với trình duyệt, cookie jar được quản lý theo chính sách browser thay vì file này.

## 7. Kiểm thử MockMvc: form, header, thiếu token, sai token

Tạo `src/test/java/example/csrf/CsrfFormHeaderApplicationTest.java`:

```java
package example.csrf;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfFormHeaderApplicationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void htmlFormContainsTokenField() throws Exception {
        MvcResult page = mvc.perform(get("/form"))
            .andExpect(status().isOk())
            .andReturn();
        String html = page.getResponse().getContentAsString();
        assertThat(html).contains("name=\"_csrf\"");
        assertThat(html).contains("method=\"post\"");
        assertThat(page.getRequest().getSession(false))
            .isNotNull();
    }

    @Test
    void missingTokenRejectsAuthenticatedPost() throws Exception {
        mvc.perform(post("/api/preference")
                .with(user("alice"))
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenRejectsAuthenticatedPost() throws Exception {
        mvc.perform(post("/api/preference")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validFormParameterWorks() throws Exception {
        mvc.perform(post("/api/preference")
                .with(user("alice"))
                .with(csrf())
                .param("theme", "dark"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void validHeaderWorks() throws Exception {
        mvc.perform(post("/api/preference")
                .with(user("alice"))
                .with(csrf().asHeader())
                .param("theme", "light"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void endpointTokenAndSameSessionWork() throws Exception {
        MvcResult getToken = mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName")
                .value("X-CSRF-TOKEN"))
            .andReturn();

        JsonNode tokenJson = mapper.readTree(
            getToken.getResponse().getContentAsString());
        String token = tokenJson.path("token").asText();
        assertThat(token).isNotBlank();

        MockHttpSession session =
            (MockHttpSession) getToken.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(post("/api/preference")
                .session(session)
                .with(user("alice"))
                .header("X-CSRF-TOKEN", token)
                .param("theme", "dark"))
            .andExpect(status().isOk());
    }

    @Test
    void anotherSessionCannotReuseToken() throws Exception {
        MvcResult first = mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andReturn();
        String token = mapper.readTree(
            first.getResponse().getContentAsString())
            .path("token").asText();

        mvc.perform(post("/api/preference")
                .session(new MockHttpSession())
                .with(user("alice"))
                .header("X-CSRF-TOKEN", token)
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginPostNeedsCsrfAsWell() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void authenticatedGetNeedsNoCsrf() throws Exception {
        mvc.perform(get("/api/preference")
                .with(user("alice")))
            .andExpect(status().isOk());
    }
}
```

`MockMvc` ở đây gọi app Spring context với filter chain thật. `csrf()` helper của `spring-security-test` tạo token hợp lệ trong test và `csrf().asHeader()` đặt token trong header; `useInvalidToken()` cố tình cho token sai. Test `endpointTokenAndSameSessionWork` còn đọc giá trị thật từ `GET /csrf` rồi gửi cùng `MockHttpSession`, nhằm kiểm tra tích hợp frontend một cách sát thực hơn.

| Ca kiểm thử | Kỳ vọng | Ý nghĩa |
|---|---|---|
| Form có hidden `_csrf` | 200 HTML | UI xuất token |
| POST đã login nhưng thiếu token | 403 | Authentication không thay CSRF |
| POST đã login nhưng token sai | 403 | Server kiểm tra tính hợp lệ |
| POST với `csrf()` | 200 | Form parameter hợp lệ |
| POST với `csrf().asHeader()` | 200 | Header hợp lệ |
| Token JSON + đúng session | 200 | API bootstrap token hoạt động |
| Token phiên A + phiên B | 403 | Không dùng chung toàn hệ thống |
| POST /login thiếu token | 403 | Login POST cũng cần protection |
| POST /login có token đúng | 3xx | Thực hiện form login |
| GET đã login | 200 | Không yêu cầu CSRF cho safe GET |

**Giới hạn:** `with(user("alice"))` tạo authentication cho request test để tách bài toán CSRF, chứ không kiểm tra chính sách mật khẩu. `MockMvc` không thay browser/network test cho cookie Domain/Secure/SameSite, CORS, reverse proxy hoặc session store phân tán. Test có thể cần cập nhật cho phiên bản dependency thực tế.

## 8. Spring Security 6: masked token, BREACH và deferred token

Spring Security 6 có những điểm dễ gây bất ngờ:

**(1) BREACH masking.** `XorCsrfTokenRequestAttributeHandler` thường dùng mặc định. Khi token xuất hiện trong HTML/response có nén, handler dùng masking ngẫu nhiên. Hai lần render có thể đưa ra **hai chuỗi khác nhau** mặc dù expected token trong session không đổi. Đừng assert hai chuỗi hiển thị phải giống nhau, và đừng thay handler chỉ để “token cố định”.

**(2) Request handler giải quyết field/header.** Handler đọc `_csrf` từ request parameter hoặc `X-CSRF-TOKEN` / `X-XSRF-TOKEN` theo cấu hình, giải mã masked representation nếu cần rồi so với token thật. Vì vậy một value copy từ repository raw không phải lúc nào cũng có cùng biểu diễn với value expose trong view.

**(3) Deferred token.** Token có thể chỉ được load/generate khi cần. Nếu SPA dựa vào cookie token xuất hiện sau GET, hãy đảm bảo một thành phần yêu cầu token thật sự được tải; chỉ khai báo repository không bảo đảm cookie mới được gửi ở mọi response.

**(4) Auth transition.** Khi login/logout thành công, token cũ có thể bị xóa bởi `CsrfAuthenticationStrategy`/`CsrfLogoutHandler`. Client phải lấy token mới để gửi request unsafe tiếp theo.

Phân biệt các thành phần:

```text
Expected token trong HttpSession hoặc CookieCsrfTokenRepository
    |
    +--> Expose để render HTML: có thể XOR-mask theo handler
    |
    +--> Form _csrf: gửi token được render, handler decode
    |
    +--> SPA đọc XSRF-TOKEN cookie: thường thấy raw token
          và cần handler chấp nhận raw header đúng cách
```

## 9. SPA dùng cookie XSRF-TOKEN / header X-XSRF-TOKEN

Với một số SPA (Angular hoặc frontend JS được cấu hình), backend có thể phát cookie `XSRF-TOKEN` để frontend đọc và gửi lại trong header `X-XSRF-TOKEN`. Đó **không phải** session cookie. Cookie đăng nhập như `JSESSIONID` nên giữ `HttpOnly` phù hợp; chỉ cookie **CSRF** mới có thể được cấu hình readable bởi JS khi thật sự cần.

### 9.1. Cookie repository

```java
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()));
```

**Đây chưa là cấu hình SPA hoàn chỉnh cho Spring Security 6.** `CookieCsrfTokenRepository` cung cấp raw token cho cookie, trong khi `XorCsrfTokenRequestAttributeHandler` mặc định có thể chờ masked token. Cần request handler giải quyết khác biệt này.

### 9.2. Handler mẫu: raw header, masked form

Đoạn dưới đây là **class minh họa** (cần tích hợp vào Servlet config của ứng dụng, không phải chương trình độc lập):

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.function.Supplier;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler masked =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> tokenSupplier) {
        masked.handle(request, response, tokenSupplier);
        tokenSupplier.get(); // tải deferred token khi cần cookie
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request, CsrfToken expected) {
        String header = request.getHeader(expected.getHeaderName());
        return (StringUtils.hasText(header) ? plain : masked)
            .resolveCsrfTokenValue(request, expected);
    }
}
```

Tích hợp trong **cùng security chain đang bảo vệ SPA**:

```java
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(
        new SpaCsrfTokenRequestHandler()));
```

Cần import `CookieCsrfTokenRepository`. Với header `X-XSRF-TOKEN`, request handler đọc raw token; với form `_csrf`, handler dùng masked representation. Code tương đương ý tưởng trong Spring Security reference; phải kiểm tra compatibility của framework/config trong dự án.

### 9.3. Trình tự SPA

```text
GET /csrf hoặc API bootstrap
  → server load/generate CSRF token
  → Set-Cookie: XSRF-TOKEN=<raw-token> nếu cấu hình

Frontend same-origin:
  → đọc XSRF-TOKEN từ document.cookie
  → fetch POST với credentials phù hợp
  → X-XSRF-TOKEN: <raw-token>
  → CsrfFilter kiểm tra qua SPA handler
```

Trường hợp token không đọc được:
- `HttpOnly` đang bật cho CSRF cookie mà frontend cần đọc (khác cookie auth).
- Cookie Path/Domain/SameSite/Secure khiến browser không lưu/gửi được.
- Deferred token chưa bị load, nên chưa có cookie.
- Token đã bị xóa khi login/logout, SPA chưa refresh.
- CORS/credential origin configuration sai, hoặc frontend framework không tự thêm header như tưởng.
- API dùng một `SecurityFilterChain` khác không có repository/handler tương ứng.

Không mở CORS cho mọi website kèm credentials chỉ để “lấy token hoạt động”. Nên dùng same-origin khi có thể; nếu bắt buộc cross-origin, thiết kế allowlist và CSRF policy rõ ràng.

## 10. Tại sao CSRF và CORS không thay nhau?

CSRF kiểm soát việc một request state-changing có chứng minh xuất phát từ flow hợp lệ hay không, trong khi CORS quản lý quyền browser JS đọc response và sử dụng một số kiểu cross-origin request.

Một HTML form cross-site thường có thể được gửi mà không cần bên gửi đọc response; vì vậy chỉ dựa vào CORS không đủ để ngăn request thay đổi trạng thái. Ngược lại, custom header có thể tạo preflight, nhưng nếu CORS mở quá rộng thì nguy cơ vẫn tồn tại. Cần đồng thời:
- CSRF token theo threat model credential tự động gửi;
- CORS origins, methods, headers, credentials chính xác;
- SameSite, Secure, HttpOnly cookie policy;
- HTTPS, trusted reverse proxy, chống XSS;
- authentication/authorization cho từng resource.

## 11. Xử lý 403 có hệ thống

**403 không mặc định nghĩa CSRF.** Có thể do quyền, CSRF, session hết hạn hoặc policy khác. Chẩn đoán:

1. Xác nhận request method và `CsrfFilter` có yêu cầu token không.
2. Kiểm tra user/session cookie đang sử dụng, có cùng session lúc lấy token không.
3. Kiểm tra form thật có field `_csrf`, JS thật có header đúng tên.
4. Nếu dùng cookie SPA, phân biệt raw token và XOR-masked token.
5. Sau login/logout, lấy token mới; không sử dụng token của phiên trước.
6. Kiểm tra cookie Path/Domain/SameSite/Secure và proxy forwarded headers.
7. Nếu đã có token hợp lệ mà vẫn 403, kiểm tra `@PreAuthorize`, role/authority, tenant và ownership.
8. Khi logging, ghi loại lỗi/request ID thay vì raw CSRF token, session ID hoặc Authorization header.
9. Tạo negative test với user đã xác thực nhưng token thiếu và sai để tách lỗi CSRF.
10. Không tắt CSRF hoặc đổi mọi method thành GET để làm test xanh.

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
|---|---|---|
| Form POST luôn 403 | Hidden input thiếu/hết hạn | Render CSRF token của session hiện tại |
| Fetch POST 403 nhưng form được | Header sai hoặc không gửi | Dùng `getHeaderName()`, kiểm tra Network |
| SPA cookie/header giống nhau vẫn 403 | Raw cookie và XOR handler không khớp | SPA handler chuyên biệt |
| Vừa login xong POST đầu 403 | Token bị clear khi login | Lấy token mới sau login |
| Session A token gửi từ session B 403 | Binding không đúng | Không dùng lại token khác phiên |
| POST /login bị 403 | Thiếu token trong login form | Gửi hidden token hoặc helper test |
| GET vẫn 200 | Safe GET mặc định không đòi token | Không chuyển mutation sang GET |
| CSRF đúng vẫn 403 | Thiếu quyền nghiệp vụ | Kiểm tra authorization, không disable CSRF |
| Browser báo CORS | Cross-origin config/cookie sai | Thiết kế trusted origins và credentials |
| Multipart upload 403 | Token ở body chưa được đọc theo filter order | Xem multipart chain, cân nhắc header |

## 12. Form login, logout, session timeout và multipart

- **Login:** `POST /login` thường cần CSRF token. Spring Security form-login page tích hợp có thể cung cấp token; với custom login page cần chắc chắn đưa token vào.
- **Logout:** POST logout giúp tránh một link GET vô tình logout user. Logout success có thể xóa token, nên client cần bootstrap lại nếu tiếp tục dùng app.
- **Session timeout:** UI giữ hidden token trong tab lâu có thể gửi lại khi session đã hết hạn. Request cần xử lý 403/redirect hợp lý, không tự tắt protection.
- **Session fixation:** Sau khi authentication thành công, session ID thường được đổi. Dữ liệu/token liên quan đến authentication boundary phải được kiểm thử, không assume token cũ còn dùng được.
- **Multi-tab:** Tab A login/logout làm token/session state đổi, tab B có thể phải tải lại token. Xử lý UX để người dùng không mất form draft.
- **Multipart:** Đặt token trong header giúp CSRF filter có thể đọc nó mà không phụ thuộc parse multipart body trước. Đừng đặt token trong query trừ khi có lý do và threat-model review rõ ràng.
- **Method override:** `HiddenHttpMethodFilter` có thể biến form POST thành PUT/DELETE ở server. Filter order và chính sách CSRF cho HTTP method hiệu lực phải được kiểm thử.
- **WebFlux:** `ServerHttpSecurity`, `ServerCsrfTokenRepository` và `WebSessionServerCsrfTokenRepository` thuộc reactive stack; không chép nguyên `HttpServletRequest`/`HttpSessionCsrfTokenRepository` vào WebFlux.

## 13. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Disable CSRF để POST không còn 403 | Mất lớp bảo vệ browser session | Sửa token transport |
| Hard-code cùng CSRF token cho mọi user | Không ràng buộc session | Dùng server repository |
| Token chỉ nằm trong cookie và không gửi field/header | Browser tự gửi cookie trong CSRF | Gửi qua đường riêng |
| Thêm token vào query URL | Dễ rò qua logs/history | Hidden field hoặc header |
| Dùng `Math.random()` sinh token ở frontend | Server không có expected token đáng tin | Token server cấp |
| Tắt HttpOnly cho **session cookie** để JS lấy CSRF | Session credential dễ bị JS đọc | Nếu cần, chỉ cookie CSRF readable |
| Cookie SPA raw nhưng handler chỉ hiểu masked | 403 khó hiểu | Dùng handler kết hợp raw/header |
| Không refresh token sau login/logout | Token cũ không còn hợp lệ | Bootstrap lại |
| Chỉ test `csrf()` helper mà không test frontend | Bỏ sót cookie/CORS/JS issues | Browser/integration test thật |
| Dùng CSRF token thay role/owner kiểm tra | Có token nhưng vẫn truy cập sai object | Authorization ở service/DB |
| GET mutation vì muốn né CSRF | Link hoặc prefetch gây tác động | Dùng unsafe method đúng |
| Log mọi request headers | Rò token/cookie/bearer | Redaction và logging tối thiểu |
| Cho phép mọi cross-origin credential | Tăng bề mặt nguy hiểm | CORS trusted allowlist |
| Dùng cùng token sau session expiration | 403 hoặc điều hướng lỗi | Reauthenticate/reload token |

## 14. Checklist trước khi release

- [ ] Chọn rõ session-cookie, SPA-cookie hay stateless Bearer authentication; hiểu credential tự gửi hay không.
- [ ] Mọi mutation dùng unsafe HTTP method, không có GET gây thay đổi trạng thái.
- [ ] Form server-rendered có token do `CsrfToken` cấp trong hidden field đúng tên.
- [ ] API fetch/AJAX có header đúng tên và token từ phiên đang sử dụng.
- [ ] Với CookieCsrfTokenRepository, xử lý raw/masked và deferred-token theo Spring Security version.
- [ ] Login và logout POST được bảo vệ; SPA refresh token sau authentication transition.
- [ ] Session/cookie, SameSite, Secure, HttpOnly và proxy hoạt động đúng.
- [ ] CORS không cho origin không đáng tin đọc token hoặc gửi credential tùy ý.
- [ ] Token không xuất hiện trên URL, analytics, shared cache hay logs.
- [ ] Test POST có token hợp lệ (form), có token hợp lệ (header), thiếu token và token sai.
- [ ] Test session A/B, login/logout, session timeout, multipart và đa tab khi ứng dụng có tính năng liên quan.
- [ ] Test authorization riêng (thiếu role hoặc sai owner vẫn bị chặn dù token đúng).
- [ ] Trong vận hành, có thể phân biệt lỗi CSRF và authorization mà không log secret.

## 15. Bài tập và đáp án

**Câu 1.** Đã đăng nhập, request POST chứa `JSESSIONID` đúng nhưng không có `_csrf`/header. Có đủ không?

**Đáp án:** Không. Cookie có thể bị browser tự gửi khi request được kích hoạt từ website khác; CSRF token cần ở đường field/header riêng.

**Câu 2.** `X-XSRF-TOKEN` và `X-CSRF-TOKEN` có giống nhau mọi nơi không?

**Đáp án:** Không. Repository/handler khác nhau có tên header khác nhau. Dùng `CsrfToken.getHeaderName()` và network test.

**Câu 3.** Vì sao `XSRF-TOKEN` cookie của SPA có thể gây 403 với Spring Security 6 mặc dù JavaScript gửi header giống cookie?

**Đáp án:** Cookie thường chứa raw token, còn handler mặc định XOR có masked representation. Cần handler giải quyết raw header đúng cách.

**Câu 4.** Token có thể cũ sau login không?

**Đáp án:** Có. `CsrfAuthenticationStrategy` có thể xóa token. Client nên tải lại token sau login thành công.

**Câu 5.** MockMvc dùng `csrf().asHeader()` thì có phải frontend chắc chắn đúng?

**Đáp án:** Không. Test helper chỉ mô phỏng request với token hợp lệ; frontend còn cần cookie, CORS, header name và session lifecycle thật.

**Câu 6.** CSRF token đúng có cho phép người dùng sửa document của người khác không?

**Đáp án:** Không. CSRF chỉ chống request giả mạo; quyền document phải được kiểm tra bằng HTTP/method/service/query scope.

**Câu 7.** Cách gửi token nào thuận tiện hơn khi upload multipart qua JS?

**Đáp án:** Header thường phù hợp hơn vì filter có thể kiểm tra token mà không cần parse multipart body trước, tùy cấu hình middleware.

**Câu 8.** Dùng Authorization Bearer token trong client JS, không có cookie auth, có tự động phải dùng CSRF token không?

**Đáp án:** Phụ thuộc threat model. Nếu credential không được browser tự gửi, CSRF cookie-based khác đi; vẫn phải xét refresh cookie, hybrid auth, XSS và CORS.

## 16. Tham khảo chính thức

- [Spring Security — CSRF (Servlet, Spring Security 6.5)](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): form, header, repository, deferred token, BREACH, SPA và logout.
- [Spring Security — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, `csrf().asHeader()`, `csrf().useInvalidToken()`.
- [Spring Security — CSRF (Reactive)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): WebFlux và ServerCsrfTokenRepository.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, double-submit cookie và defense-in-depth.
- [OWASP — XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): vì sao phải chống XSS cùng CSRF.

**Kết luận:** Trong ứng dụng browser-session, CSRF token cần được gửi qua **hidden form input** hoặc **HTTP header** trên request thay đổi trạng thái; browser tự gửi cookie đăng nhập **không đủ**. Với Spring Security MVC nên dùng token thực do repository/request handler cung cấp; với SPA dùng cookie, phải chú ý raw/masked token và refresh sau login/logout. Bảo vệ CSRF, authentication và authorization phải luôn đi cùng nhau.
