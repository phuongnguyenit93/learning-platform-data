# Đăng xuất qua chuyển hướng cho web hoặc phản hồi trạng thái cho API trong Spring Security

## 1. Mục tiêu bài học

Đăng xuất (logout) không đơn thuần là gửi người dùng đến trang khác hoặc trả một mã HTTP. Một luồng đăng xuất dựa trên cookie/session cần **xóa trạng thái xác thực an toàn**, sau đó mới chọn phản hồi phù hợp với loại client.

Hai kiểu phản hồi phổ biến:

- **Ứng dụng web truyền thống (server-rendered web):** sau khi người dùng bấm Đăng xuất, server trả **HTTP 302/303 redirect** về trang đăng nhập hoặc một trang xác nhận đã đăng xuất. Browser tự điều hướng đến trang mới.
- **API cho SPA/mobile/JavaScript:** sau khi hoàn thành logout, server trả **HTTP 204 No Content** (không có body) hoặc **HTTP 200 OK** kèm JSON ngắn. Client tự cập nhật giao diện và tự quyết định có điều hướng hay không.

Ví dụ:

~~~http
POST /web/logout HTTP/1.1
Cookie: JSESSIONID=...
X-CSRF-TOKEN: ...

HTTP/1.1 302 Found
Location: /signed-out
~~~

~~~http
POST /api/logout HTTP/1.1
Cookie: JSESSIONID=...
X-CSRF-TOKEN: ...

HTTP/1.1 204 No Content
~~~

**Điểm trọng tâm:** redirect hay 204 **chỉ là kết quả HTTP sau logout**; chúng không phải thao tác hủy phiên. Trong Spring Security Servlet, `LogoutFilter` và các `LogoutHandler` xử lý dọn dẹp. `LogoutSuccessHandler` mới quyết định phản hồi.

Bài thực hành dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet MVC**, kết hợp một luồng form login dựa trên HTTP session với hai URL logout để minh họa rõ sự khác biệt. Nếu ứng dụng xác thực bằng bearer JWT stateless, cơ chế thu hồi token khác với việc hủy session; phần 14 phân tích riêng.

Sau bài này, bạn có thể:

1. Giải thích vai trò khác nhau của `LogoutFilter`, `LogoutHandler` và `LogoutSuccessHandler`.
2. Cấu hình redirect cố định bằng `logoutSuccessUrl`/`SimpleUrlLogoutSuccessHandler` cho web.
3. Trả HTTP 204 qua `HttpStatusReturningLogoutSuccessHandler(HttpStatus.NO_CONTENT)` cho API.
4. Hiểu tại sao logout cần POST và CSRF token trong ứng dụng dùng browser cookie.
5. Tích hợp session invalidation, clear `SecurityContext`, cookie/remember-me cleanup và xử lý request sau logout.
6. Tránh open redirect, lỗi CORS/SPA, phản hồi 204 có body và nhầm lẫn giữa logout session với revoke JWT.
7. Kiểm thử các điều kiện trên bằng MockMvc và dự án Spring Security chạy được.

## 2. Luồng logout có những tầng trách nhiệm nào?

~~~text
                  Browser hoặc SPA
                         |
        POST /web/logout hoặc /api/logout
                         |
                         v
                   SecurityFilterChain
                         |
                         v
          CsrfFilter kiểm tra CSRF cho POST
                         |
              +----------+----------+
              |                     |
          token sai             token hợp lệ
              |                     |
              v                     v
          403 Forbidden          LogoutFilter
                                    |
                        RequestMatcher có khớp?
                                    |
                                    v
                           LogoutHandler chain
                         +----------------------+
                         | invalidate session   |
                         | clear SecurityContext|
                         | clear CSRF token     |
                         | remember-me cleanup  |
                         | custom cleanup nếu có|
                         +----------------------+
                                    |
                                    v
                           LogoutSuccessHandler
                               /         \
                              /           \
                             v             v
                      WEB response     API response
                       302/303         204 No Content
                       Location        (no body)
                             |             |
                             v             v
                       Browser đi     SPA tự đổi state
                       sang trang     / điều hướng
~~~

Thứ tự quan trọng:

- `LogoutFilter` khớp URL/method dành cho logout, điều phối các `LogoutHandler`.
- `SecurityContextLogoutHandler` thường invalidate `HttpSession`, xóa `Authentication` và `SecurityContextHolder`, đồng thời làm sạch context repository.
- `CsrfLogoutHandler` xóa token CSRF cũ. Request thay đổi trạng thái tiếp theo cần token phù hợp với phiên mới.
- Nếu bật remember-me, `RememberMeServices` có thể tham gia cleanup cookie nhớ đăng nhập.
- `LogoutSuccessHandler#onLogoutSuccess(request, response, authentication)` chạy **sau** các công việc dọn dẹp; nó chọn redirect, status code hoặc response khác.

**Không đồng nhất “HTTP 204” với “đã thu hồi mọi credential”.** 204 chỉ cho biết server báo thành công tại endpoint logout. Việc còn JWT nào hoạt động, OAuth2/OIDC IdP có bị đăng xuất không, browser có một cookie khác hay không phải được thiết kế, kiểm thử riêng.

### API chính của success handler

~~~java
public interface LogoutSuccessHandler {
    void onLogoutSuccess(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication
    ) throws IOException, ServletException;
}
~~~

`authentication` có thể bằng `null` nếu logout được gọi khi không có danh tính đăng nhập. Một success handler phù hợp nên xử lý an toàn cả trường hợp đó, nhất là với API idempotent.

## 3. Lựa chọn phản hồi cho web và API

| Tiêu chí | Web server-rendered | SPA / REST API |
| --- | --- | --- |
| Client chủ yếu | Browser có điều hướng trang | `fetch`/Axios/mobile |
| Kết quả phổ biến | `302 Found` đến `/login?logout` hoặc `/signed-out` | `204 No Content`; đôi khi `200 OK` JSON |
| Cơ chế trong Spring Security | `logoutSuccessUrl` hoặc `SimpleUrlLogoutSuccessHandler` | `HttpStatusReturningLogoutSuccessHandler` |
| Ai quyết định màn hình tiếp theo? | Browser theo `Location` | Frontend tự điều hướng/thay state |
| HTTP body cần thiết? | Thường không, vì redirect | 204 không được chứa body |
| CSRF khi dùng cookie | Giữ CSRF cho POST logout | Vẫn giữ CSRF nếu browser tự gửi cookie |
| Xử lý logout thật | `LogoutHandler` | Chính `LogoutHandler` đó, không bỏ qua |

**Trường hợp 200 JSON hợp lệ:** sản phẩm cần trả `{"status":"logged_out"}` để ứng dụng hiển thị thông báo. Cần dùng một `LogoutSuccessHandler` custom ghi status 200 và `Content-Type: application/json`. Nếu chỉ cần báo thành công, 204 thường gọn hơn và không phải thiết kế JSON contract.

**Không tự tạo redirect phía server cho API chỉ vì web có redirect.** Nhiều HTTP client tự follow 302 khiến lời gọi logout cuối cùng nhận HTML trang login; SPA dùng `response.json()` sẽ lỗi. Ngược lại, trả 204 cho một form logout thuần HTML có thể khiến người dùng nhìn thấy một trang trống thay vì quay về màn hình thích hợp.

## 4. Cách ngắn gọn: web redirect với logoutSuccessUrl

Nếu ứng dụng chỉ có web session login, cấu hình ngắn gọn:

~~~java
// Đặt bên trong SecurityFilterChain, không phải file chạy độc lập.
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessUrl("/login?logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .permitAll()
);
~~~

Khi POST `/logout` có CSRF token hợp lệ, Spring Security chạy logout handler chain rồi redirect về `/login?logout`. Đây là **URL cố định do server cấu hình**. `/login?logout` chỉ đóng vai trò trang hiển thị thông báo đã đăng xuất, không phải thao tác dọn dẹp.

Mặc định Spring Security hỗ trợ `/logout`, thường redirect về `/login?logout` sau thành công. Với CSRF bật, `GET /logout` phục vụ màn hình xác nhận chứ không phải một phương thức đăng xuất tức thì; hành động thật nên thực hiện bằng `POST /logout` có CSRF token.

### Tại sao không dùng GET để logout?

GET được kỳ vọng là safe/idempotent theo ý nghĩa HTTP về không cố ý tạo thay đổi trạng thái. Nếu `GET /logout` tự hủy phiên, một ảnh/đường link tải tự động, prefetch, crawler hoặc trang khác có thể làm user bị logout ngoài dự kiến. Hơn nữa, browser cookie có thể được tự đính kèm vào request cross-site.

**Khuyến nghị:** dùng POST với CSRF protection khi browser xác thực bằng cookie. Không gỡ bảo vệ CSRF toàn cục chỉ để đổi logout sang GET.

## 5. Cách ngắn gọn: API logout trả status

Với API dựa trên session cookie, có thể sử dụng:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.authentication.logout
    .HttpStatusReturningLogoutSuccessHandler;

// Đoạn cấu hình trong SecurityFilterChain:
http.logout(logout -> logout
    .logoutUrl("/api/logout")
    .logoutSuccessHandler(
        new HttpStatusReturningLogoutSuccessHandler(
            HttpStatus.NO_CONTENT))
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .permitAll()
);
~~~

Trong mã Java thật, import phải nằm **trên một dòng**:

~~~java
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;
~~~

Constructor không tham số của `HttpStatusReturningLogoutSuccessHandler` trả mặc định **HTTP 200 OK**. Để trả **204**, hãy chỉ rõ `HttpStatus.NO_CONTENT`. Đừng nhầm rằng instance mặc định đã trả 204.

Một success handler 204 không được ghi JSON:

~~~java
LogoutSuccessHandler noContent = (request, response, authentication) -> {
    response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    // Không gọi getWriter().write(...).
};
~~~

**HTTP 204 không có message body.** Nếu frontend gọi `await response.json()` trên phản hồi 204, nó có thể gặp lỗi parse. Thay vào đó kiểm tra `response.status === 204` hoặc `response.ok` và không đọc body.

Tùy hệ thống có thể chọn 200 JSON, ví dụ:

~~~java
LogoutSuccessHandler jsonSuccess = (request, response, authentication) -> {
    response.setStatus(HttpServletResponse.SC_OK);
    response.setContentType("application/json");
    response.getWriter().write("{\"status\":\"logged_out\"}");
};
~~~

Đây là đoạn handler minh họa, không tự thực hiện dọn session; nó chỉ thay cách trả response **sau** logout handler chain.

## 6. Cấu hình logout mặc định thực sự xóa những gì?

Theo Spring Security 6.5 Servlet, khi logout thành công, các handler được cấu hình thường thực hiện:

1. **Invalidate HTTP session** để session không còn hiệu lực.
2. **Clear `SecurityContextHolderStrategy`** và làm sạch `SecurityContextRepository`.
3. **Dọn remember-me cookie** nếu cơ chế remember-me tương ứng đã được cấu hình.
4. **Xóa CSRF token** đang gắn với phiên hoặc repository.
5. **Phát `LogoutSuccessEvent`** để các thành phần khác quan sát khi phù hợp.

Ứng dụng có thể bổ sung `LogoutHandler` riêng cho cache/server-side state khác. Nhưng logout handler nên tập trung vào cleanup và **không ném exception** trong quá trình dọn dẹp nếu có thể tránh; success handler là nơi phù hợp hơn để quyết định redirect/response.

**Lưu ý về `JSESSIONID`:** khi `HttpSession` bị invalidate, session ID cũ không còn truy cập lại nội dung đã xác thực. Browser có thể vẫn hiển thị cookie `JSESSIONID` trong một số môi trường cho đến khi được cập nhật/xóa. Việc cookie còn hiện diện không chứng minh session ở server còn hợp lệ. Spring Security docs cũng lưu ý không nhất thiết cần cấu hình `deleteCookies("JSESSIONID")` khi session đã được invalidate; nếu có cookie tùy chỉnh, cần xóa với domain/path tương ứng.

**Remember-me stateless:** xóa cookie nhớ đăng nhập trên trình duyệt hiện tại không thu hồi được **bản sao signed cookie đã bị đánh cắp**. Khi cần revoke riêng từng remember-me token hoặc thiết bị, xem cơ chế persistent-token/revocation phù hợp.

**Clear-Site-Data:** có thể bổ sung một `HeaderWriterLogoutHandler` với `ClearSiteDataHeaderWriter` để yêu cầu browser xóa cookie/site data. Phải cân nhắc phạm vi (đặc biệt `Directive.ALL` có thể xóa cache/storage của ứng dụng) và browser support; không coi header này là cách thu hồi token đang tồn tại trên thiết bị khác.

## 7. Ví dụ hoàn chỉnh: một ứng dụng có cả web redirect và API 204

Mục tiêu demo:
- Form login chuẩn `POST /login`, dùng user/password in-memory, BCrypt và HTTP session.
- Trang `GET /web/home` có form POST `/web/logout` với CSRF token.
- `POST /web/logout` hủy session và redirect cố định `/signed-out`.
- `POST /api/logout` hủy session qua **cùng cơ chế dọn dẹp**, trả `204 No Content`.
- `GET /api/me` chỉ phục vụ người đã đăng nhập; không có phiên sẽ trả **401** thay vì redirect HTML.
- `GET /api/csrf` trả CSRF token cho frontend/API session client.
- `POST /api/logout` thiếu/sai CSRF token trả **403** trước khi đến logout handler.

Hai đường logout dùng **một `LogoutFilter` duy nhất** với matcher cho hai đường. Success handler được định tuyến theo **đường dẫn server đã cấu hình**, không dựa vào query `next` hay `Referer` từ client.

### 7.1. Cấu trúc dự án

~~~text
dual-logout-demo/
├── pom.xml
└── src/
    ├── main/java/demo/logout/DualLogoutApplication.java
    └── test/java/demo/logout/DualLogoutApplicationTests.java
~~~

File `pom.xml` dành cho Java 17 và Spring Boot 3.5.7 (quản lý Spring Security 6.5.x):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>dual-logout-demo</artifactId>
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
~~~

Khi tạo sản phẩm thực, hãy dùng nhánh Spring Boot/Spring Security được bảo trì và bản vá phù hợp. Ví dụ cố định version để minh họa API Spring Security 6.x; không dùng nguyên mật khẩu demo ở production.

### 7.2. Mã ứng dụng

Tạo file `src/main/java/demo/logout/DualLogoutApplication.java`:

~~~java
package demo.logout;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;
import org.springframework.security.web.authentication.logout.SimpleUrlLogoutSuccessHandler;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DualLogoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(DualLogoutApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        // Dành cho form web: redirect về URL CỐ ĐỊNH.
        SimpleUrlLogoutSuccessHandler webRedirect =
            new SimpleUrlLogoutSuccessHandler();
        webRedirect.setDefaultTargetUrl("/signed-out");
        webRedirect.setAlwaysUseDefaultTargetUrl(true);

        // Dành cho API: HTTP 204, tuyệt đối không có body.
        HttpStatusReturningLogoutSuccessHandler apiNoContent =
            new HttpStatusReturningLogoutSuccessHandler(
                HttpStatus.NO_CONTENT);

        // Một LogoutFilter cho cả hai URL. Điều hướng theo
        // servlet path đã biết, KHÔNG theo next/returnUrl từ client.
        LogoutSuccessHandler responseByRoute =
            (request, response, authentication) -> {
                String path = request.getServletPath();

                if ("/api/logout".equals(path)) {
                    apiNoContent.onLogoutSuccess(
                        request, response, authentication);
                } else if ("/web/logout".equals(path)) {
                    webRedirect.onLogoutSuccess(
                        request, response, authentication);
                } else {
                    response.sendError(
                        HttpServletResponse.SC_NOT_FOUND);
                }
            };

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/login", "/signed-out", "/api/csrf"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.POST, "/login", "/web/logout", "/api/logout"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                // Default login page GET /login do Spring Security tạo.
                .defaultSuccessUrl("/web/home", true)
                .permitAll()
            )
            // Request API thiếu login -> 401 thay vì HTML redirect.
            .exceptionHandling(ex -> ex.defaultAuthenticationEntryPointFor(
                (request, response, error) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED),
                new AntPathRequestMatcher("/api/**")
            ))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            .logout(logout -> logout
                .logoutRequestMatcher(new OrRequestMatcher(
                    new AntPathRequestMatcher(
                        "/web/logout", "POST"),
                    new AntPathRequestMatcher(
                        "/api/logout", "POST")
                ))
                // Cleanup do Spring Security LogoutHandlers quản lý.
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessHandler(responseByRoute)
                .permitAll()
            );
        // Không disable CSRF: mặc định bật cho POST login/logout.
        return http.build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/api/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            // CsrfFilter đưa token vào attribute của request.
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());

            return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken());
        }

        @GetMapping("/api/me")
        Map<String, String> me(
                org.springframework.security.core.Authentication auth) {
            return Map.of("username", auth.getName());
        }

        @GetMapping(
            value = "/web/home",
            produces = MediaType.TEXT_HTML_VALUE
        )
        String webHome(HttpServletRequest request) {
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());

            // Demo chạy tại context path "/".
            // Production nên render form qua template engine có escaping.
            return "<!doctype html><html><body>"
                + "<h1>Đã đăng nhập</h1>"
                + "<form action='/web/logout' method='post'>"
                + "<input type='hidden' name='"
                + token.getParameterName()
                + "' value='"
                + token.getToken()
                + "'>"
                + "<button type='submit'>Đăng xuất</button>"
                + "</form></body></html>";
        }

        @GetMapping(
            value = "/signed-out",
            produces = MediaType.TEXT_HTML_VALUE
        )
        String signedOut() {
            return "<!doctype html><html><body>"
                + "<h1>Bạn đã đăng xuất</h1>"
                + "<a href='/login'>Đăng nhập lại</a>"
                + "</body></html>";
        }
    }
}
~~~

### 7.3. Những chi tiết cần chú ý trong code

**Không tạo endpoint `@PostMapping("/api/logout")` để tự xóa vài biến.** Cả `POST /web/logout` và `POST /api/logout` được `LogoutFilter` xử lý **trước khi request tới Spring MVC controller**. Dùng DSL giữ được các LogoutHandlers chuẩn như cleanup session/context và CSRF.

**Matcher chỉ nhận POST.** `OrRequestMatcher` gồm đúng hai `AntPathRequestMatcher` có phương thức `POST`. Vì vậy `GET /api/logout` hay `GET /web/logout` không phải thao tác logout. Đường dẫn cần được kiểm soát chặt, không dựa vào `Referer` hoặc `Accept` để chọn có xóa session hay không.

**Phản hồi sau logout tách biệt.** `responseByRoute` chỉ chạy khi logout handler chain đã hoàn tất. Với `/api/logout` nó gọi `apiNoContent`, với `/web/logout` nó gọi `webRedirect`. Một `LogoutFilter` thực hiện cùng cleanup, chỉ khác cách phản hồi.

**Redirect cố định:** `webRedirect.setDefaultTargetUrl("/signed-out")` và `setAlwaysUseDefaultTargetUrl(true)`. Đích không lấy từ query parameter `next` hoặc `returnUrl`. URL `/signed-out` là trang do server kiểm soát và phải được phép truy cập sau khi đã xóa session.

**API 401 riêng:** `exceptionHandling.defaultAuthenticationEntryPointFor` xử lý request đến `/api/**` khi chưa authenticated bằng HTTP 401. Nếu thiếu cấu hình này, `formLogin` có thể khiến client API nhận redirect đến màn hình HTML login, rất bất tiện cho SPA.

**Trang form:** `/web/home` hiển thị form POST/logout và hidden CSRF field; ví dụ này giả định ứng dụng chạy ở root context path. Đối với web production, dùng template engine có escaping, hỗ trợ context path/locale, hiển thị thông báo phù hợp và không ghép HTML từ dữ liệu người dùng không tin cậy.

**CSRF token phải còn hợp lệ khi logout:** post logout dùng token vừa lấy từ session đang hoạt động. Sau khi logout, CSRF token/session cũ bị xóa nên không nên tái sử dụng token đó ở các POST tiếp theo.

**HTTP 204:** handler chỉ ghi status code, không ghi JSON body. Với SPA, hãy tự xóa state/cache phía client rồi điều hướng bằng router nếu cần.

**Không phụ thuộc cookie Set-Cookie bị xóa tức thì.** Việc server invalidate session đủ khiến session ID cũ không còn quyền. Trong môi trường multi-instance cần shared session store hoặc session routing hợp lệ; tránh giả định một cookie `JSESSIONID` có thể truy cập lại context sau logout.

## 8. Trình tự chạy thủ công

### 8.1. Khởi động

Trong thư mục dự án (Java 17+ và Maven đã cài):

~~~bash
mvn test
mvn spring-boot:run
~~~

`mvn test` chạy bài test tích hợp bên dưới. `mvn spring-boot:run` chạy server, mặc định ở `http://localhost:8080` nếu không thay cấu hình. Không dùng `javac DualLogoutApplication.java` đơn lẻ khi thiếu classpath Spring Security/Spring Boot/Jakarta Servlet.

### 8.2. Đăng nhập qua browser (luồng web)

Mở:

~~~text
http://localhost:8080/login
~~~

Spring Security tự hiển thị trang login mặc định. Đăng nhập bằng:
- Username: `student`
- Password: `demo-password`

Khi thành công, browser được chuyển đến `/web/home`. Trang này có form `POST /web/logout` với CSRF token do server phát. Nhấn **Đăng xuất**; browser nhận redirect `302` (status cụ thể tùy redirect strategy) tới `/signed-out` và hiển thị thông báo đã đăng xuất.

Thử mở lại `/web/home` sau khi logout: vì session cũ không còn authentication, Spring Security sẽ yêu cầu đăng nhập lại.

### 8.3. API session login và logout qua curl

Bước đầu lấy CSRF token và session cookie:

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
~~~

Response JSON có dạng:

~~~json
{"headerName":"X-CSRF-TOKEN","token":"<token-thuc-te>"}
~~~

Đây chỉ là cấu trúc ví dụ. Dùng **giá trị token thật** từ server, không điền nguyên văn text trong dấu ngoặc.

Gửi form login, giữ cookie:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'X-CSRF-TOKEN: <token-thuc-te>' \
  --data-urlencode 'username=student' \
  --data-urlencode 'password=demo-password' \
  http://localhost:8080/login
~~~

Nếu credentials đúng, login filter trả redirect đến `/web/home` và cookie phiên được ghi/điều chỉnh. Vì ví dụ demo dùng flow form chung, một client API có thể đăng nhập bằng form rồi gọi API cùng session cookie.

Kiểm tra phiên trước khi logout:

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Kỳ vọng:

~~~json
{"username":"student"}
~~~

**Lấy CSRF token mới sau khi đăng nhập** với cookie đang dùng:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/csrf
~~~

Token trước login có thể đã bị xóa/rotate bởi session strategy. Gửi logout API:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -X POST http://localhost:8080/api/logout \
  -H 'X-CSRF-TOKEN: <token-moi-thuc-te>'
~~~

Kỳ vọng status:

~~~http
HTTP/1.1 204 No Content
~~~

Không có body. Request tiếp theo dùng session cũ:

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Kỳ vọng **HTTP 401 Unauthorized** (hoặc session cookie không còn ý nghĩa và endpoint yêu cầu đăng nhập lại). Không nên assert rằng browser bắt buộc xóa mọi cookie vật lý ngay lập tức chỉ dựa vào response này; kiểm tra auth state mới là điều cốt lõi.

### 8.4. So sánh redirect từ web

Với session đã đăng nhập và token CSRF hiện tại, nếu gửi:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -X POST http://localhost:8080/web/logout \
  -H 'X-CSRF-TOKEN: <token-hien-tai>'
~~~

Kỳ vọng `302 Found` (hoặc 3xx redirect thích hợp) và:

~~~http
Location: /signed-out
~~~

`curl -i` mặc định không tự follow `Location`; browser thì thường có. Không gọi tuần tự cả hai logout trên **cùng session đã bị hủy** rồi cho rằng đây là một phép so sánh cùng trạng thái. Để thử web logout độc lập, phải đăng nhập lại/tạo session mới.

## 9. Kiểm thử bằng MockMvc

Test cả **kết quả trả về** lẫn **hành động xóa session**, vì 204/302 chỉ là HTTP response. Những bài test sau chạy với Spring Security Test và app Spring Boot được nêu ở mục 7.

File `src/test/java/demo/logout/DualLogoutApplicationTests.java`:

~~~java
package demo.logout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DualLogoutApplicationTests {

    @Autowired
    MockMvc mvc;

    private MockHttpSession loginSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/web/home"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(session);
        return session;
    }

    @Test
    void webLogoutRedirectsToFixedPageAndInvalidatesSession()
            throws Exception {

        MockHttpSession session = loginSession();

        mvc.perform(post("/web/logout")
                .session(session)
                .with(csrf())
                .param("next", "https://evil.example"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signed-out"));

        assertTrue(session.isInvalid());
    }

    @Test
    void apiLogoutReturns204WithNoBodyOrRedirect()
            throws Exception {

        MockHttpSession session = loginSession();

        mvc.perform(post("/api/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""))
            .andExpect(header().doesNotExist("Location"));

        assertTrue(session.isInvalid());
    }

    @Test
    void apiLogoutWithoutCsrfIsRejectedBeforeCleanup()
            throws Exception {

        MockHttpSession session = loginSession();

        mvc.perform(post("/api/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void webLogoutWithoutCsrfIsRejectedBeforeCleanup()
            throws Exception {

        MockHttpSession session = loginSession();

        mvc.perform(post("/web/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
    }

    @Test
    void getApiLogoutDoesNotPerformLogout() throws Exception {
        MockHttpSession session = loginSession();

        mvc.perform(get("/api/logout").session(session))
            .andExpect(status().isNotFound());

        assertFalse(session.isInvalid());
        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void afterApiLogoutNewUnauthenticatedRequestGets401()
            throws Exception {

        MockHttpSession session = loginSession();

        mvc.perform(post("/api/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().isNoContent());

        assertTrue(session.isInvalid());
        // Dùng request mới không mang session cũ.
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void signedOutPageIsPublic() throws Exception {
        mvc.perform(get("/signed-out"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                org.hamcrest.Matchers.containsString("đăng xuất")));
    }

    @Test
    void csrfEndpointIsPublic() throws Exception {
        mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kỳ vọng sau khi tạo đúng các file và tải dependency:** 8 test chạy qua trong môi trường tương thích. Những test trên là mẫu được cung cấp để thực hành, **không phải kết quả đã được chạy thực tế** trong hệ thống của người học.

### Các bất biến được kiểm thử

| Test | Bất biến |
| --- | --- |
| `webLogoutRedirectsToFixedPageAndInvalidatesSession` | Redirect luôn đến `/signed-out`, không nhận `next` từ client, session bị hủy |
| `apiLogoutReturns204WithNoBodyOrRedirect` | API 204 không có body và không có header `Location` |
| `apiLogoutWithoutCsrfIsRejectedBeforeCleanup` | CSRF sai/thiếu không được logout user ngoài ý muốn |
| `webLogoutWithoutCsrfIsRejectedBeforeCleanup` | Web form cần CSRF tương tự |
| `getApiLogoutDoesNotPerformLogout` | GET không bị cấu hình nhầm thành logout |
| `afterApiLogoutNewUnauthenticatedRequestGets401` | Request mới không mang session không được tự xác thực |
| `signedOutPageIsPublic` | Trang đích sau logout không yêu cầu session |
| `csrfEndpointIsPublic` | Client có thể lấy token để gửi POST hợp lệ |

Để kiểm thử chặt hơn ở production, còn cần test domain/path cookie, remember-me, session fixation, OIDC SSO, logout trên nhiều node, cache state và tình huống client gửi JWT song song với cookie.

**Giới hạn của test session:** `MockHttpSession.isInvalid()` chứng minh session được invalidate trong môi trường MockMvc. Để xác nhận cookie thực, CORS, redirect và reverse proxy, phải chạy thêm end-to-end test với browser hoặc HTTP client thật.

## 10. React, Vue, Angular và fetch: xử lý phản hồi 204 đúng cách

Với SPA xác thực qua session cookie, một flow có thể là:

~~~javascript
async function logout() {
  // Token này đã được app lấy qua endpoint /api/csrf.
  const csrfToken = getCsrfTokenFromAppState();

  const response = await fetch("/api/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRF-TOKEN": csrfToken
    }
  });

  if (response.status !== 204) {
    throw new Error("Logout did not complete");
  }

  // Không gọi response.json() vì HTTP 204 không có body.
  clearSensitiveClientState();
  window.location.assign("/signed-out");
}
~~~

Đây là **đoạn minh họa**, không phải file JS độc lập: `getCsrfTokenFromAppState` và `clearSensitiveClientState` là các hàm của SPA cần được triển khai trong app. Trong môi trường cross-origin, phải cấu hình `credentials`, CORS, `SameSite` và HTTPS theo policy. `credentials: "include"` chỉ nên dùng khi cần và server có allowlist origin đúng.

Cần xóa/điều chỉnh state phía client sau khi server xác nhận logout: cache user profile, UI auth flags, dữ liệu nhạy cảm trong bộ nhớ, WebSocket subscriptions hoặc query cache nếu chứa dữ liệu người dùng. Không coi việc frontend `window.location = "/login"` tự nó là logout; server session vẫn có thể còn.

**Về redirect 3xx:** `fetch` mặc định có thể follow redirect, nên `response.status` cuối cùng có thể là 200 của trang HTML thay vì 302 của logout. Khi API yêu cầu JSON/status, cấu hình `LogoutSuccessHandler` trả 204 thay vì dựa vào redirect của web. Tránh xử lý bằng cách parse HTML response thành JSON.

### Khi nào trả 200 JSON thay vì 204?

Có thể sử dụng 200:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"logged_out"}
~~~

Nếu contract frontend cần hiển thị thông báo từ server, đó là lựa chọn hợp lý. Nhưng 200 JSON không có nghĩa cleanup khác với 204. Cả hai đều phải đi qua LogoutHandlers chuẩn và đáp ứng yêu cầu auth/security như nhau.

### Có cần 401 khi logout mà user đã hết phiên?

Không có một đáp án duy nhất; nhiều API chọn logout **idempotent**: gửi POST hợp lệ khi đã hết phiên vẫn trả 204, vì trạng thái cuối là “không còn xác thực”. Tùy sản phẩm có thể yêu cầu xác thực để xử lý thu hồi token cụ thể. Với Spring Security logout DSL, `LogoutFilter` nằm trước `AuthorizationFilter` và có thể xử lý logout ngay cả khi `Authentication` đang null. Dù vậy, CSRF cho logout dùng cookie vẫn cần được thiết kế thích hợp.

Không nên trả thông tin về tài khoản, session hoặc token từ logout response nếu client không có quyền biết.

## 11. Tại sao nên dùng LogoutFilter thay vì tự viết controller logout?

Một controller tưởng như đơn giản:

~~~java
// Không đủ để logout an toàn:
@PostMapping("/api/logout")
public ResponseEntity<Void> logout() {
    return ResponseEntity.noContent().build();
}
~~~

Đoạn trên chỉ trả 204, không hủy `HttpSession`, không xóa `SecurityContextHolder`, không làm sạch repository, không xử lý remember-me và CSRF. Người dùng có thể vẫn được xem là authenticated ở request sau.

Nếu bắt buộc tự xây controller, cần gọi những logout handler thích hợp như `SecurityContextLogoutHandler` và xử lý các nhiệm vụ khác theo chính sách, nhưng dễ bỏ sót thành phần. Spring Security chính thức khuyến nghị dùng `http.logout(...)`, và nếu cần hành động dọn bổ sung thì đăng ký `addLogoutHandler(...)`.

Ví dụ thêm cleanup của chính ứng dụng:

~~~java
// Minh họa: serverCacheService là một service ứng dụng đã định nghĩa.
LogoutHandler cleanup = (request, response, authentication) -> {
    if (authentication != null) {
        serverCacheService.evictFor(authentication.getName());
    }
};

http.logout(logout -> logout
    .addLogoutHandler(cleanup)
    .logoutSuccessHandler(
        new HttpStatusReturningLogoutSuccessHandler(
            HttpStatus.NO_CONTENT))
);
~~~

Đây **không phải đoạn code độc lập**; `serverCacheService` phải được triển khai. Cleanup handler không nên tùy tiện ghi success response, cũng không nên ném runtime exception khiến những handler khác không chạy. Cần thiết kế hành vi khi cache backend lỗi.

## 12. Chọn redirect cố định và phòng open redirect

Người dùng có thể yêu cầu logout rồi trở về một trang cụ thể. Tuy nhiên, nếu ứng dụng tin vào query `returnUrl` / `next`, kẻ tấn công có thể tạo một link:

~~~text
https://app.example.com/web/logout?next=https://evil.example
~~~

Nếu server dùng giá trị đó làm `Location` sau logout, browser bị đưa đến domain do kẻ tấn công điều khiển. Đây là **open redirect (CWE-601)**, có thể làm tăng hiệu quả phishing ngay sau thao tác đăng xuất.

Những giá trị nguy hiểm thường gặp:
- `https://evil.example/login` — URL tuyệt đối sang host khác.
- `//evil.example/path` — network-path URL chuyển sang host khác.
- `https://app.example.com.evil.example/` — host nhìn giống nhưng không đúng.
- URL có userinfo hoặc encoding bất thường khiến kiểm tra prefix bị qua mặt.
- Các biến thể của path traversal và encoded slash nếu ứng dụng tự ghép đường dẫn.

**Giải pháp mặc định tốt nhất:** không cho client chọn đích logout; dùng `logoutSuccessUrl("/signed-out")` hoặc handler `setDefaultTargetUrl("/signed-out")` và `setAlwaysUseDefaultTargetUrl(true)`. Đây là những URL do server quyết định.

Nếu sản phẩm bắt buộc redirect động, chỉ cho các đường dẫn nội bộ hợp lệ hoặc allowlist origin/host được kiểm tra sau khi parse/canonicalize URL. Không kiểm tra `startsWith("https://app.example.com")`; host `app.example.com.evil.example` sẽ vượt qua cách kiểm tra prefix yếu.

**Chú ý thêm:** sử dụng HTTP `Referer` để xác định trang trở về không an toàn vì header có thể thiếu, bị kiểm soát hoặc khác origin. Không mặc định chuyển người dùng đến URL từ `Referer` sau logout.

## 13. CSRF, cookie, caching và các trạng thái dễ bỏ sót

### 13.1. CSRF ở POST logout

Khi browser tự gửi session cookie, một trang khác có thể cố gắng ép request để đăng xuất người dùng (logout CSRF). Spring Security mặc định bật CSRF cho các phương thức không an toàn như POST.

- `GET /logout` trong flow mặc định có CSRF thường là **trang xác nhận**, không phải hành động.
- `POST /logout` hoặc custom `POST /web/logout`/`POST /api/logout` cần CSRF token hợp lệ.
- Nếu thiếu token: `CsrfFilter` thường trả **403 Forbidden**, logout handlers **không chạy**.
- Không gỡ CSRF toàn bộ chỉ để API dễ gọi hơn nếu frontend dựa trên cookie.

Nếu API thực sự stateless và chỉ dùng bearer token trong `Authorization`, chính sách CSRF có thể khác. Đó không phải bằng chứng để tắt CSRF cho tất cả đường web cookie.

### 13.2. Cookie và trạng thái client

Logout có thể làm server hủy session trong khi browser vẫn còn cookie cũ về mặt lưu trữ. Xóa thêm cookie tùy chỉnh chỉ làm đúng khi `Path` và `Domain` phù hợp; nếu không, trình duyệt vẫn giữ cookie ở phạm vi khác.

**Remember-me:** nếu bật `rememberMe`, cấu hình logout nên có cleanup token/cookie nhớ đăng nhập. Với signed stateless remember-me, bản sao bị đánh cắp có thể còn hợp lệ đến khi expiry/key/password hash thay đổi; không thể thu hồi riêng từng bản sao chỉ bằng HTTP 204/302.

**CSRF token:** sau logout, phiên và CSRF token cũ có thể đã bị xóa; ứng dụng nên lấy token mới khi cần thực hiện POST tiếp theo.

### 13.3. Browser back button và cache

Sau logout, browser có thể hiển thị nội dung trang trước đó từ lịch sử/Back-Forward Cache mà không liên hệ server. Điều này **không đồng nghĩa** user vẫn có quyền API sau logout. Tuy nhiên, nội dung nhạy cảm không nên bị cache công khai và UI nên ẩn/refresh trạng thái sau logout.

Spring Security mặc định có các security response headers hỗ trợ cache-control cho nhiều response. Với dữ liệu nhạy cảm, kiểm tra header cache và reverse proxy riêng, đồng thời làm sạch client-side caches khi phù hợp.

### 13.4. Nhiều tab và race condition

Một tab có thể vừa logout, tab khác còn giữ UI “đã đăng nhập”. Request tiếp theo của tab đó phải bị chặn khi session bị invalidate. Với SPA nhiều tab, có thể dùng `BroadcastChannel` hoặc cơ chế phù hợp để đồng bộ UI state; đây là một tối ưu trải nghiệm, không thay thế kiểm soát server-side.

### 13.5. Nhiều thiết bị, nhiều session

Logout thông thường hủy **session hiện tại**, không nhất thiết hủy tất cả session của tài khoản trên mọi thiết bị. Nếu tính năng “đăng xuất tất cả thiết bị” được yêu cầu, cần `SessionRegistry`/shared session store/revocation hoặc một user-session version, cùng kiểm thử race và multi-instance.

## 14. API stateless, bearer JWT và logout có ý nghĩa gì?

Đây là điểm phân biệt quan trọng:

~~~text
Session cookie authentication:
  logout -> invalidate HttpSession / clear SecurityContext
         -> request dùng session cũ không còn authenticated

Bearer JWT authentication:
  logout -> xóa token ở client?
         -> server vẫn có thể chấp nhận JWT còn hạn
            nếu không có revocation / introspection / policy khác
~~~

Với Resource Server JWT stateless, `http.logout(...)` mặc định không thể “xóa” access token đã phát hành ở authorization server chỉ bằng việc invalidate `HttpSession` (thậm chí ứng dụng có thể không dùng session).

Cần quyết định rõ:
- Nếu client dùng access token ngắn hạn và không có refresh token, logout phía client có thể chỉ xóa token đang giữ; token bị đánh cắp vẫn có thể dùng cho tới khi hết hạn.
- Nếu có refresh token, phải thu hồi refresh token/refresh-token family hoặc thực hiện cơ chế server-side khác theo authorization server.
- Nếu token cần bị thu hồi ngay, dùng token introspection, denylist có TTL, token version hoặc cơ chế phù hợp; xem xét tải, tính nhất quán và khả năng mở rộng.
- Với OAuth2/OIDC SSO, logout khỏi ứng dụng cục bộ **không tự đăng xuất khỏi nhà cung cấp danh tính**. Cần thiết kế RP-initiated logout/Single Logout nếu chính sách yêu cầu, ví dụ `OidcClientInitiatedLogoutSuccessHandler` trong Spring Security client.
- Browser logout xong nhưng IdP session vẫn hoạt động có thể dẫn đến login lại “không cần nhập password” qua SSO; đó là trạng thái của IdP, không nhất thiết là session local còn sống.

Do đó, API trả `204 No Content` nên được hiểu theo contract thực tế của endpoint: đã xóa session local hoặc đã thực hiện token revocation nào, không tuyên bố “mọi credential đã vô hiệu” nếu hệ thống không có cơ chế đó.

## 15. Nhiều SecurityFilterChain và logout URL

Một ứng dụng có thể dùng hai chain:
- `/web/**`: form login, session và redirect logout.
- `/api/**`: API session-based với status response, hoặc bearer JWT stateless có chính sách riêng.

Khi cấu hình `securityMatcher`, phải bảo đảm URL logout được bao phủ bởi **đúng chain** và filter logout của chain đó. Chẳng hạn chain chỉ match `/api/**` sẽ không xử lý `/logout` nếu URL nằm ngoài phạm vi. Đây là lỗi hay gặp khi nâng cấp từ một chain lên nhiều chain.

Ví dụ cấu hình ngắn cho chain API (chỉ mang tính minh họa, chưa đủ bean/matcher cho dự án độc lập):

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .logout(logout -> logout
            .logoutUrl("/api/logout")
            .logoutSuccessHandler(
                new HttpStatusReturningLogoutSuccessHandler(
                    HttpStatus.NO_CONTENT)));
    return http.build();
}
~~~

Ở môi trường thực, cấu hình form login, csrf/exception handling, method security và chain web riêng nếu cần. **Không** dùng một `AuthenticationManager`/session policy không đúng cho các cơ chế khác nhau chỉ vì cùng ứng dụng.

Ví dụ chính chọn **một chain + hai logout request matchers** để người học thấy cùng cleanup được chia ra hai kiểu response mà không cần thiết kế nhiều chain.

## 16. Xử lý lỗi, trạng thái HTTP và idempotency

| Trường hợp | Response thường gặp | Ghi chú |
| --- | --- | --- |
| Web POST logout với CSRF hợp lệ | 302/303 tới trang được chọn | Handler quyết định redirect |
| API POST logout với CSRF hợp lệ | 204 No Content | Không ghi JSON body |
| API logout cần JSON contract | 200 OK + JSON | Chỉ dùng khi client cần body |
| Thiếu/sai CSRF trong flow cookie | 403 Forbidden | Thường bị `CsrfFilter` chặn trước LogoutFilter |
| API GET logout trong ví dụ | Không chạy logout; có thể 404 | Không tạo side effect qua GET |
| API GET tài nguyên sau logout | 401 Unauthorized | Không còn authenticated session |
| Web GET trang bảo vệ sau logout | Redirect về login | Form login entry point xử lý |
| Logout khi session đã hết | Thường 204 hoặc redirect giống bình thường | Có thể idempotent, tùy contract |
| Logout qua bearer JWT nhưng không có revocation | Status không chứng minh JWT đã vô hiệu | Phải kiểm tra auth server/resource server |

Đối với API, nhiều nhóm muốn logout **idempotent**: gọi hai lần đều cho kết quả cuối cùng “đã đăng xuất”. Điều đó thường giúp frontend dễ xử lý reconnect/retry. Tuy nhiên, không nên bật retry không giới hạn, và một request thiếu CSRF token vẫn phải bị xử lý theo chính sách bảo mật dù session đã hết.

Không cần phản hồi các trường chứa tên user, token, session ID hay lý do cụ thể nhạy cảm sau logout. Nếu cần audit, ghi sự kiện bằng mã an toàn và correlation ID, tránh log giá trị cookie/Authorization header.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ `return "redirect:/login"` trong controller | Session và SecurityContext có thể còn | Dùng `http.logout(...)` hoặc gọi đúng LogoutHandlers |
| Chỉ `return ResponseEntity.noContent()` | 204 nhưng không logout thực sự | Đảm bảo `LogoutFilter` xử lý trước response |
| API dùng logout mặc định redirect về login HTML | SPA follow redirect, parse JSON lỗi | `HttpStatusReturningLogoutSuccessHandler(NO_CONTENT)` |
| Web form logout trả 204 | Browser hiển thị trang trắng | Redirect về trang hợp lệ sau logout |
| Đặt `logoutSuccessUrl` lấy trực tiếp từ `next` | Open redirect | Đích cố định hoặc allowlist server-side |
| Cho GET trực tiếp xóa phiên | Logout CSRF, prefetch làm đăng xuất ngoài ý muốn | POST có CSRF |
| Tắt CSRF chỉ vì frontend dùng JSON | Cookie vẫn tự gửi trong một số bối cảnh | Giữ CSRF theo threat model |
| Trả 204 và ghi JSON body | Sai HTTP semantics; client xử lý khó | 204 body rỗng, 200 khi có JSON |
| Frontend gọi `response.json()` trên 204 | Parse error | Không đọc body cho 204 |
| Gọi `location.href="/login"` nhưng không POST logout | Session server vẫn còn | Gọi API logout trước khi đổi route |
| Ghi log `Cookie`/`Authorization` lúc logout | Rò credential | Redact secrets, log audit metadata |
| Tin rằng xóa cookie JS làm server logout | Session server có thể còn sống | Invalidate server session |
| Tưởng logout chỉ ảnh hưởng session là toàn bộ SSO | IdP có thể vẫn giữ session | RP-initiated logout / Single Logout khi cần |
| Tưởng xóa JWT client là revoke token | JWT còn hạn có thể dùng | Token revocation/introspection/TTL theo policy |
| Không permit trang `/signed-out` | Redirect tới trang lại yêu cầu login | Permit trang đích |
| Sai `securityMatcher` ở nhiều chain | LogoutFilter không chạy trên URL định dùng | Kiểm tra chain, URL/method và thứ tự |
| Cookie custom có path/domain sai khi xóa | Browser vẫn gửi cookie cũ | Dùng scope cookie phù hợp |
| Không test session invalidated | UI có vẻ logout nhưng cookie cũ vẫn xác thực | Kiểm tra post-logout protected request |
| SessionRegistry chỉ có trên một node | Logout trên node A không cập nhật node B đúng | Shared session store/registry đúng kiến trúc |

## 18. Checklist review cho production

- [ ] Có quyết định rõ client nhận redirect hay HTTP status, không “tùy cảm hứng” theo `Accept` không đáng tin.
- [ ] Logout URL/method có matcher chính xác và thuộc đúng `SecurityFilterChain`.
- [ ] Logout được thực hiện bởi `LogoutFilter`/LogoutHandlers, không chỉ return 204/302 từ controller.
- [ ] `SecurityContextLogoutHandler` invalidate session và clear context theo chính sách.
- [ ] Nếu có remember-me, cơ chế cleanup cookie/token tương ứng được gọi.
- [ ] Với cookie-based login, POST logout cần CSRF token hợp lệ.
- [ ] Web redirect dùng đích do server kiểm soát; không mở open redirect.
- [ ] Trang sau logout được phép truy cập khi chưa có session.
- [ ] API 204 không chứa body/JSON và không có `Location`.
- [ ] SPA xử lý 204 an toàn và xóa auth state/cache sau khi logout thành công.
- [ ] API chưa authenticated nhận 401 theo contract thay vì HTML login page nếu cần.
- [ ] Test logout thành công, CSRF 403, GET không logout, session invalidated, protected resource bị chặn sau logout.
- [ ] Với SSO/OIDC/SAML, có chính sách logout local và logout IdP tách biệt.
- [ ] Với JWT bearer, có chính sách revoke/refresh/access-token expiry độc lập với HTTP session.
- [ ] Cookie và session store hoạt động nhất quán qua load balancer, proxy và nhiều instance.
- [ ] Cookie/session/token không bị ghi vào log; site data/cache được dọn phù hợp.
- [ ] Có quy trình logout all devices hoặc account compromise nếu sản phẩm yêu cầu.

## 19. Câu hỏi tự kiểm tra

1. `LogoutSuccessHandler` có thực hiện invalidate `HttpSession` thay `LogoutHandler` không?
2. Vì sao cùng một logout cleanup có thể dùng cho web redirect và API 204?
3. `logoutSuccessUrl("/signed-out")` khác gì với `HttpStatusReturningLogoutSuccessHandler(HttpStatus.NO_CONTENT)`?
4. Constructor không tham số của `HttpStatusReturningLogoutSuccessHandler` mặc định trả status nào?
5. Vì sao SPA gọi `response.json()` sau 204 có thể lỗi?
6. Vì sao cần POST và CSRF token trong logout khi dùng session cookie?
7. Vì sao trả HTTP 302/204 từ controller mà không gọi logout handlers là chưa đủ?
8. Vì sao cần cho phép `/signed-out` truy cập không cần đăng nhập?
9. Tại sao URL `next=https://evil.example` không nên quyết định `Location` sau logout?
10. Sau khi logout, cookie `JSESSIONID` còn xuất hiện trong browser có chứng minh session vẫn tồn tại ở server không?
11. Vì sao session logout không thể tự thu hồi access token JWT đã phát hành?
12. Local logout trong OIDC có đồng nghĩa đăng xuất khỏi IdP không?
13. Khi dùng hai `SecurityFilterChain`, tại sao `securityMatcher` có thể khiến logout URL không hoạt động?
14. Làm sao test bảo đảm một request thiếu CSRF token không vô tình làm user logout?
15. Trong API nhiều lần logout, khi nào trả 204 dù không có session vẫn hợp lý?

## 20. Tài liệu tham khảo

1. Spring Security 6.5 — Handling Logouts (LogoutFilter, LogoutHandler, custom success handler, CSRF): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
2. Spring Security 6.5 API — `LogoutSuccessHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/LogoutSuccessHandler.html
3. Spring Security 6.5 API — `HttpStatusReturningLogoutSuccessHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/HttpStatusReturningLogoutSuccessHandler.html
4. Spring Security 6.5 API — `SimpleUrlLogoutSuccessHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SimpleUrlLogoutSuccessHandler.html
5. Spring Security 6.5 API — `SecurityContextLogoutHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html
6. Spring Security 6.5 API — `LogoutConfigurer`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/LogoutConfigurer.html
7. Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
8. Spring Security 6.5 — MockMvc testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
9. Spring Security 6.5 — Java Configuration with multiple filter chains: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
10. OWASP — Unvalidated Redirects and Forwards Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

**Ghi nhớ:** Trong Spring Security Servlet, **logout handlers dọn trạng thái**, còn **logout success handler chọn phản hồi**. Web thường cần redirect cố định để browser điều hướng; API thường cần 204 không body để frontend tự cập nhật giao diện. Cả hai phải bảo đảm logout thực sự diễn ra, giữ CSRF khi dùng cookie và không nhầm session logout với token/SSO revocation.