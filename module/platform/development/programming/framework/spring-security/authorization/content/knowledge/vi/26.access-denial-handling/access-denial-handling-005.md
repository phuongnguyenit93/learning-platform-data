# Phản hồi JSON cho API và điều hướng phù hợp giao diện web

Trong Spring Security (Servlet), cùng một quyết định từ chối truy cập có thể cần hai cách phản hồi khác nhau: client gọi API cần **HTTP status và JSON có cấu trúc**, còn người dùng đang điều hướng trên website thường cần **trang đăng nhập hoặc trang thông báo không đủ quyền**. Bài này đặt trong chủ đề **Xử lý từ chối** của Spring Security Authorization; trọng tâm là xử lý tại tầng security filter, không nhầm với xử lý lỗi nghiệp vụ trong controller.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt **chưa được xác thực** với **đã xác thực nhưng không đủ quyền**, chọn đúng HTTP 401/403 và hành vi phía trình duyệt.
- Giải thích vai trò của `ExceptionTranslationFilter`, `AuthenticationEntryPoint` và `AccessDeniedHandler`.
- Cấu hình API trả JSON nhất quán, còn website dùng form login và trang 403 mà không làm rò rỉ phản hồi HTML vào API.
- Tách đường dẫn API và website bằng hai `SecurityFilterChain`; kiểm thử cả trạng thái, header, body lẫn hướng điều hướng.

## 2. Hai loại từ chối và hợp đồng phản hồi

**Authentication** xác định người gọi là ai; **authorization** xác định danh tính đó có được phép thực hiện thao tác hay không. Không nên coi mọi lỗi bảo mật là 403.

| Tình huống | API (máy/SPA/mobile client) | Trang web điều hướng bằng trình duyệt |
| --- | --- | --- |
| Chưa đăng nhập/chưa có credential hợp lệ, gọi tài nguyên bảo vệ | Thường `401 Unauthorized` + JSON; với HTTP Basic/Bearer cần header `WWW-Authenticate` tương ứng | `302` chuyển tới `/login` trong mô hình form login; sau đăng nhập có thể quay lại URL ban đầu |
| Đã đăng nhập, thiếu role/authority | `403 Forbidden` + JSON | `403` + trang giải thích quyền truy cập bị từ chối; có thể *forward* đến trang 403 |
| Đường dẫn API công khai, không yêu cầu đăng nhập | `200` hoặc status nghiệp vụ tương ứng | Không áp dụng |
| Người dùng gửi thông tin đăng nhập sai vào form login | Phụ thuộc cơ chế xác thực API; Basic/Bearer có hành vi challenge riêng | Form login thường chuyển về `/login?error`; đây là lỗi đăng nhập, không phải lỗi thiếu quyền của tài nguyên |

Lưu ý: `401` có nghĩa là cần xác thực hoặc xác thực không hợp lệ; tên tiếng Anh “Unauthorized” dễ gây nhầm với authorization. `403` là quyền truy cập bị từ chối. Dù status là 401/403, nội dung cho client phải đủ ổn định để xử lý mà không tiết lộ chi tiết phân quyền, mật khẩu, token hay stack trace.

Với API dùng Basic trong ví dụ dưới đây, một phản hồi có thể là:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
Content-Type: application/json;charset=UTF-8
Cache-Control: no-store

{"status":401,"error":"AUTHENTICATION_REQUIRED","message":"Cần xác thực để sử dụng API."}
```

Nếu đã xác thực nhưng thiếu quyền:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json;charset=UTF-8
Cache-Control: no-store

{"status":403,"error":"ACCESS_DENIED","message":"Bạn không có quyền truy cập tài nguyên này."}
```

Các mã `error` là hợp đồng ứng dụng tự định nghĩa. Client nên dựa vào **HTTP status** trước, sau đó đọc `error` để hiển thị thông điệp hoặc chọn hành động. Không dùng status 200 với `"error": 403` vì middleware, client và hệ thống giám sát sẽ hiểu sai.

## 3. Spring Security xử lý ở đâu?

Trên luồng Servlet, `FilterChainProxy` chọn `SecurityFilterChain` phù hợp. Trong chuỗi filter, `AuthorizationFilter` có thể từ chối truy cập. `ExceptionTranslationFilter` chuyển các ngoại lệ bảo mật phù hợp thành phản hồi HTTP:

```text
HTTP request
  |
  v
FilterChainProxy -> SecurityFilterChain phù hợp
  |
  v
ExceptionTranslationFilter
  |  gọi các filter/ứng dụng phía sau
  +-- AuthenticationException / người gọi chưa xác thực đủ
  |      -> AuthenticationEntryPoint
  |         API: 401 + JSON | Web: chuyển đến login
  |
  +-- AccessDeniedException, đã xác thực đủ nhưng thiếu quyền
         -> AccessDeniedHandler
            API: 403 + JSON | Web: trang 403
```

Đây là sơ đồ luồng khái niệm, không phải danh sách đầy đủ thứ tự mọi filter. Khi `AccessDeniedException` xảy ra với anonymous (và trong một số trường hợp remember-me chưa đủ mức xác thực), Spring Security khởi động lại quá trình xác thực qua `AuthenticationEntryPoint`. Nếu người dùng đã xác thực đủ, nó gọi `AccessDeniedHandler`. Do đó không nên tự viết quy tắc cứng “cứ gặp AccessDeniedException là 403” mà bỏ qua trạng thái xác thực.

- `AuthenticationEntryPoint`: quyết định cách yêu cầu người gọi xác thực. `LoginUrlAuthenticationEntryPoint` phù hợp form login; API có thể dùng entry point trả JSON 401 hoặc entry point cho Bearer/Basic.
- `AccessDeniedHandler`: quyết định cách trả lời khi đã xác thực nhưng thiếu quyền. Handler có thể gửi status/body JSON hoặc đưa đến trang 403.
- `RequestCache`: với web, giúp lưu yêu cầu để quay lại sau đăng nhập; với API stateless thường không cần lưu yêu cầu vào HTTP session.
- `@ControllerAdvice` / `@ExceptionHandler`: hữu ích cho lỗi trong MVC controller, nhưng **không phải cách thay thế đáng tin cậy** cho xử lý từ chối ở security filter trước controller.

## 4. Chọn cách tách API và web

Khi đường dẫn phân biệt rõ (ví dụ `/api/**` và các trang còn lại), **hai `SecurityFilterChain`** làm chính sách minh bạch:

1. Chain có `@Order(1)` và `securityMatcher("/api/**")` chỉ xử lý API. Khai báo JSON 401/403, chiến lược xác thực API, request cache và session phù hợp.
2. Chain web không đặt `securityMatcher` nên là cấu hình bao phủ phần còn lại. Bật `formLogin`, cho phép truy cập trang đăng nhập, cấu hình trang 403.
3. Trong mỗi chain, `authorizeHttpRequests().requestMatchers(...)` quy định ai được truy cập **bên trong phạm vi chain đó**. `securityMatcher` chọn chain, còn `requestMatchers` chọn rule authorization; hai khái niệm không thay thế nhau.
4. Chain cụ thể phải đứng trước chain tổng quát. Nếu không chain nào khớp một request, Spring Security không bảo vệ request đó; vì thế nên có chain bao phủ mặc định.

Không nên chỉ nhìn header `Accept: application/json` để suy ra một request là API: nhiều client gửi `*/*`, browser `fetch()` có thể tự theo 302, proxy có thể thay đổi header. Đường dẫn hoặc hợp đồng endpoint rõ ràng thường đáng tin hơn. Khi cùng một URL thực sự phục vụ cả JSON và HTML, có thể cân nhắc `defaultAuthenticationEntryPointFor(...)` và `defaultAccessDeniedHandlerFor(...)` với `RequestMatcher`, nhưng phải kiểm thử trường hợp header thiếu/không rõ ràng.

## 5. Ví dụ Java 17+ chạy được: JSON cho /api/**, trang phù hợp cho web

Ví dụ dùng **Spring Boot 3.x / Spring Security 6.x (Servlet)**, Maven, Java 17 trở lên. Nó cố tình dùng HTTP Basic cho các URL API chỉ có GET để thao tác bằng `curl`; website dùng form login với session. Trong hệ thống thực, chọn cơ chế xác thực API phù hợp (chẳng hạn Bearer token/OAuth2 Resource Server) và dùng mật khẩu đã mã hóa, không dùng tài khoản demo.

Tạo hai tệp:

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>com.example</groupId>
    <artifactId>security-responses</artifactId>
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

**`src/main/java/com/example/denial/SecurityResponseApplication.java`**

```java
package com.example.denial;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityResponseApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityResponseApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password("{noop}reader123")
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin123")
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http, ObjectMapper mapper)
            throws Exception {
        AuthenticationEntryPoint json401 = (request, response, exception) -> {
            // Đây là demo HTTP Basic; challenge header là một phần giao thức.
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"api\"");
            writeJson(mapper, response, 401, "AUTHENTICATION_REQUIRED",
                    "Cần xác thực để sử dụng API.");
        };

        AccessDeniedHandler json403 = (request, response, exception) ->
                writeJson(mapper, response, 403, "ACCESS_DENIED",
                        "Bạn không có quyền truy cập tài nguyên này.");

        http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .requestCache(cache -> cache
                        .requestCache(new NullRequestCache()))
                .httpBasic(basic -> basic.authenticationEntryPoint(json401))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(json401)
                        .accessDeniedHandler(json403));

        // Giữ CSRF mặc định; demo chỉ có các API GET.
        // Xem mục bảo mật trước khi bổ sung POST/PUT/DELETE.
        return http.build();
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/forbidden", "/error")
                        .permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .exceptionHandling(errors -> errors
                        .accessDeniedPage("/forbidden"));
        return http.build();
    }

    private static void writeJson(
            ObjectMapper mapper, HttpServletResponse response,
            int status, String error, String message) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", status);
        body.put("error", error);
        body.put("message", message);
        mapper.writeValue(response.getWriter(), body);
    }

    @RestController
    static class DemoEndpoints {

        @GetMapping("/api/public")
        Map<String, String> publicApi() {
            return Map.of("result", "public");
        }

        @GetMapping("/api/me")
        Map<String, String> me(Principal principal) {
            return Map.of("username", principal.getName());
        }

        @GetMapping("/api/admin/report")
        Map<String, String> adminReport() {
            return Map.of("report", "ready");
        }

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        String home() {
            return "<h1>Home</h1><a href='/admin/panel'>Admin panel</a>";
        }

        @GetMapping(value = "/admin/panel", produces = MediaType.TEXT_HTML_VALUE)
        String adminPanel() {
            return "<h1>Admin panel</h1>";
        }

        @GetMapping(value = "/forbidden", produces = MediaType.TEXT_HTML_VALUE)
        ResponseEntity<String> forbiddenPage() {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .contentType(MediaType.TEXT_HTML)
                    .body("<h1>403 - Không đủ quyền</h1>"
                            + "<a href='/'>Về trang chủ</a>");
        }
    }
}
```

**Giải thích những dòng quan trọng:**

- `apiChain` có độ ưu tiên cao và chỉ khớp `/api/**`. Mọi API không được `permitAll` đều cần đăng nhập; `/api/admin/**` còn đòi `ROLE_ADMIN` (`hasRole("ADMIN")` tự thêm tiền tố `ROLE_`).
- `json401` được gắn vào **cả** `exceptionHandling` và `httpBasic`. Vì lỗi credential không hợp lệ có thể được xử lý trực tiếp bởi `BasicAuthenticationFilter`, gắn cả hai giúp body JSON nhất quán cho cả thiếu và sai credential. `WWW-Authenticate: Basic ...` giữ đúng challenge của HTTP Basic.
- `json403` chỉ trả JSON 403 cho caller đã được xác thực nhưng không đạt rule. Hàm chung `writeJson` dùng Jackson để escape chuỗi hợp lệ, gửi HTTP status đúng và chống cache nội dung lỗi.
- `STATELESS` và `NullRequestCache` tránh sử dụng session/request replay cho API demo. Với web chain, form login dùng session và cơ chế lưu request mặc định để trình duyệt có thể trở về trang đang truy cập sau login.
- `formLogin(Customizer.withDefaults())` sử dụng trang đăng nhập mặc định do Spring Security cung cấp, nên không cần viết controller `GET /login`. Khi làm form login tùy biến bằng `loginPage("/login")`, bạn phải tự cung cấp trang đó.
- `accessDeniedPage("/forbidden")` **forward nội bộ** tới endpoint HTML với HTTP 403. URL trong thanh địa chỉ vẫn là tài nguyên bị từ chối. Endpoint `/forbidden` được cho phép đi qua security để render trang lỗi và tự trả status 403.

Tài khoản demo `reader/reader123` chỉ có `ROLE_USER`; `admin/admin123` có `ROLE_ADMIN`. Tiền tố `{noop}` chỉ nhằm đơn giản hóa ví dụ học tập, tuyệt đối không dùng cho mật khẩu thật.

### Chạy và quan sát

Từ thư mục chứa `pom.xml`, với JDK 17+ và Maven đã cài:

```bash
mvn spring-boot:run
```

Kiểm tra API công khai:

```bash
curl -i http://localhost:8080/api/public
```

Kết quả: `HTTP 200` với JSON `{"result":"public"}`.

Chưa xác thực:

```bash
curl -i http://localhost:8080/api/me
```

Kết quả: `HTTP 401`, `WWW-Authenticate: Basic realm="api"` và body JSON mã `AUTHENTICATION_REQUIRED`. Đây không phải HTML của `/login`.

Đã xác thực nhưng thiếu quyền:

```bash
curl -i -u reader:reader123 http://localhost:8080/api/admin/report
```

Kết quả: `HTTP 403`, JSON `ACCESS_DENIED`. Trong khi đó:

```bash
curl -i -u admin:admin123 http://localhost:8080/api/admin/report
```

Kết quả: `HTTP 200` và `{"report":"ready"}`.

Trang web chưa đăng nhập:

```bash
curl -i -H "Accept: text/html" http://localhost:8080/admin/panel
```

Kết quả: HTTP `302` với `Location` hướng đến `/login`. Dùng trình duyệt mở `http://localhost:8080/admin/panel`, đăng nhập với `reader/reader123`: bạn nhận **trang HTML 403** bởi `reader` không có quyền admin. Đăng nhập bằng `admin/admin123`: trang quản trị hiển thị. Form login của Spring Security có CSRF token; muốn mô phỏng đăng nhập bằng `curl` phải xử lý token và cookie phiên, không chỉ gửi cặp username/password.

### Bảng kiểm thử cần có

| Trường hợp | Status dự kiến | Kiểm tra thêm |
| --- | --- | --- |
| `GET /api/public` không credential | 200 | JSON công khai |
| `GET /api/me` không credential | 401 | JSON; header challenge; không `Location: /login` |
| `GET /api/me` sai Basic credential | 401 | JSON thống nhất; không trả HTML |
| `GET /api/admin/report` với `reader` | 403 | JSON; mã `ACCESS_DENIED` |
| `GET /api/admin/report` với `admin` | 200 | Nội dung report |
| `GET /admin/panel` chưa login | 302 | Đích là login |
| `GET /admin/panel` đã login bằng `reader` | 403 | Trang HTML; request được forward đến `/forbidden` |
| `GET /admin/panel` đã login bằng `admin` | 200 | Trang HTML admin |

Các header bổ sung như `Content-Length`, `Set-Cookie` và đường dẫn tuyệt đối/tương đối trong `Location` có thể thay đổi theo môi trường; dùng status và ý nghĩa của `Location` làm tiêu chí chính. Khi test bằng `fetch`, nhớ rằng redirect mặc định được theo tự động: request có thể kết thúc bằng **HTML 200 của trang login** sau một **302 ban đầu**, rồi phát sinh lỗi ở `response.json()`.

## 6. Forward trang 403 và redirect khác nhau thế nào?

Có hai cách điều hướng phổ biến, nhưng trạng thái HTTP quan sát được khác nhau:

- **Forward** (ví dụ `accessDeniedPage("/forbidden")`): server xử lý trang lỗi nội bộ, không yêu cầu browser gửi request mới. Có thể giữ `403` và URL gốc. Phù hợp trang “Bạn không đủ quyền”.
- **Redirect** (ví dụ `response.sendRedirect("/forbidden")`): server trả `302`, browser gửi request mới đến `/forbidden`. Cần cân nhắc việc mất status `403` ở phản hồi đầu tiên, thay đổi URL và vòng lặp điều hướng nếu chính trang đích cũng bị chặn. Không dùng redirect như cách thay thế mọi lỗi 403 API.
- **Login redirect** khi chưa xác thực là hành vi đúng cho **trang HTML có tương tác**, do `AuthenticationEntryPoint` của form login chịu trách nhiệm. Với SPA, có thể giữ status 401 JSON và cho phía frontend tự chuyển sang màn hình login sau khi đọc status.

Cũng không nên redirect đến URL do tham số người dùng cung cấp mà thiếu kiểm tra, vì dễ tạo **open redirect**. Khi triển khai giao diện, tạo trang lỗi có đường dẫn quay lại an toàn, lời giải thích vừa đủ và không hiển thị thông tin nhạy cảm.

## 7. Những điều cần kiểm tra trước khi áp dụng thật

**Chính sách CSRF và kiểu xác thực.** Ví dụ trên chỉ có GET API và **giữ CSRF mặc định**. HTTP Basic credential mà trình duyệt tự gửi hoặc cookie session có thể chịu rủi ro CSRF khi có endpoint thay đổi dữ liệu. Không sao chép tùy tiện `csrf.disable()` vào mọi API. Với API Bearer token gửi rõ ràng trong `Authorization` và không dựa vào credential tự gửi từ trình duyệt, có thể cân nhắc cấu hình CSRF khác dựa trên threat model. Nếu bật CSRF, một POST thiếu token có thể thành 403 **dù đã login**: đó không nhất thiết là thiếu role.

**Challenge tuân thủ giao thức.** Với HTTP Basic, `401` cần `WWW-Authenticate: Basic ...`. Với OAuth2 Resource Server/Bearer token, hãy dùng `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` (hoặc giữ header/challenge đúng chuẩn khi tùy biến body JSON). Không ép mọi `401` thành cùng một header Basic nếu app dùng Bearer.

**Đường dẫn và filter chain.** Nếu API có nhiều prefix (ví dụ `/api/v1/**` và `/internal/**`), khai báo đầy đủ phạm vi chain, không bỏ sót route. Không đặt catch-all chain trước API chain. Một URL không được filter chain nào khớp có thể bị bỏ qua bảo vệ. Đừng quên các endpoint login/logout do chính filter cung cấp cũng phải nằm trong chain thích hợp.

**Xử lý lỗi thống nhất.** Nếu app dùng `ProblemDetail`/RFC 9457 cho lỗi nghiệp vụ, bạn có thể thiết kế payload 401/403 tương thích; vẫn cần handler ở tầng Security. Kiểm thử cùng mã lỗi, `Content-Type`, charset và việc không để lộ ngoại lệ. Không cho frontend dò quyền bằng chuỗi message dễ thay đổi theo bản dịch.

**CORS, proxy và content negotiation.** CORS preflight (OPTIONS) không mang credential như request thật; hãy cấu hình CORS đúng thay vì diễn giải mọi 403 preflight là thiếu role. Với reverse proxy/context path, kiểm tra URL chuyển đến login, HTTPS và forwarded headers. Dùng API route hoặc matcher rõ ràng để client không bị nhận HTML ngoài mong đợi.

**Method security.** Các rule `@PreAuthorize`/`@PostAuthorize` cũng có thể phát sinh `AccessDeniedException`. Kiểm tra đường đi ngoại lệ qua Spring Security và MVC trong cấu hình thực tế, nhất là khi có `@ControllerAdvice` tùy biến. Mục tiêu vẫn là API nhận JSON phù hợp và trang web nhận HTML phù hợp.

## 8. Lỗi thường gặp và cách khắc phục

1. **API trả 302 về /login:** form login đang áp dụng cho API hoặc chain API không khớp. Xác minh `@Order`, `securityMatcher` và `AuthenticationEntryPoint`; không chỉ vá bằng `@ControllerAdvice`.
2. **Tất cả trường hợp đều trả 403:** không phân biệt anonymous với người đã xác thực, hoặc tự gửi `sendError(403)` trong custom filter. Dùng entry point cho trường hợp chưa xác thực và denied handler cho trường hợp thiếu quyền.
3. **API trả JSON khi thiếu credential nhưng trả HTML khi mật khẩu Basic sai:** đã cấu hình `exceptionHandling.authenticationEntryPoint` nhưng quên entry point của `httpBasic`. Gắn cùng handler cho cả hai đường như ví dụ.
4. **Trang 403 thành 302 hoặc 200:** dùng `sendRedirect` thay vì forward/response 403, hoặc endpoint trang lỗi tự đặt lại status. Kiểm tra request thật bằng DevTools Network, không chỉ nhìn trang hiển thị.
5. **Lặp redirect /login hoặc /forbidden:** URL trang login/trang lỗi chưa được `permitAll` hoặc login endpoint nằm ngoài phạm vi filter chain.
6. **API POST bị 403 dù có ROLE_ADMIN:** điều tra CSRF, CORS, authentication và rule theo thứ tự; đừng tự kết luận chỉ từ status.
7. **React/Vue gặp “Unexpected token <” khi parse JSON:** API đã trả HTML (thường sau redirect login). Kiểm tra `response.redirected`, URL cuối, `Content-Type` và thiết kế trả 401 JSON.
8. **Client xử lý theo text lỗi của framework:** nội dung có thể đổi theo phiên bản, ngôn ngữ hoặc exception. Duy trì error code ứng dụng ổn định và log chi tiết trên server, không gửi stack trace ra ngoài.

## 9. Bài tập áp dụng

Giả sử ứng dụng có `GET /api/orders`, `DELETE /api/orders/{id}` và `GET /admin/orders`. Hãy xác định contract:

- Caller API chưa xác thực: HTTP 401 JSON theo đúng cơ chế xác thực đang dùng.
- Caller API đã xác thực nhưng thiếu quyền xóa: HTTP 403 JSON; **không** đưa về trang login.
- Browser chưa đăng nhập vào `/admin/orders`: chuyển tới trang đăng nhập; sau khi đăng nhập, điều hướng trở lại trang phù hợp.
- Browser đã đăng nhập nhưng không có quyền quản trị: HTML 403, liên kết về trang an toàn.
- Với `DELETE`, xác minh CSRF theo **cách credential được gửi**; không chỉ kiểm tra role.

Tự kiểm tra bằng Network tab hoặc HTTP client: với mỗi tình huống, ghi **status, Location, WWW-Authenticate, Content-Type, body và URL cuối**. Nếu không giải thích được vì sao một response thuộc `AuthenticationEntryPoint` hay `AccessDeniedHandler`, hãy truy vết chain và trạng thái `Authentication` trước.

## 10. Tài liệu chính thức

- Spring Security — [Handling Security Exceptions](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-exceptiontranslationfilter) (`ExceptionTranslationFilter`).
- Spring Security — [Java Configuration / Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) (`securityMatcher` và nhiều chain).
- Spring Security — [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) (quy tắc authorization).
- Spring Security — [Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html) (đăng nhập web).
- Spring Security API — [AccessDeniedHandlerImpl](https://docs.spring.io/spring-security/site/docs/6.1.x/api/org/springframework/security/web/access/AccessDeniedHandlerImpl.html) (403 và forward).

**Ghi nhớ:** Chọn phản hồi theo **trạng thái xác thực và hợp đồng của endpoint**: API nhận status/JSON/challenge chuẩn giao thức; website nhận hướng điều hướng tới login hoặc trang 403 với status có ý nghĩa.