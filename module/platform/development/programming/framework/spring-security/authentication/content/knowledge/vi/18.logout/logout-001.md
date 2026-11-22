# LogoutFilter, LogoutHandler và LogoutSuccessHandler

> **Chủ đề:** Spring Security - authentication — **Đăng xuất** (Servlet). Bài học giải thích đường đi của request logout trong Spring Security, sự khác nhau giữa thành phần phát hiện request, các tác vụ dọn dẹp và phản hồi thành công; sau đó triển khai một ứng dụng **Java 17 + Spring Boot 3.3.5 + Spring Security 6.x** có endpoint logout trả JSON và kiểm thử bảo vệ CSRF/phiên. Đây là logout của ứng dụng sử dụng **HTTP session và form login**. Thu hồi JWT, OAuth2/OIDC và single logout liên hệ nhưng là các vấn đề bổ sung cần phân biệt rõ.

## 1. Ba vai trò không được nhầm lẫn

Một request `POST /logout` thông thường không phải một lệnh controller đơn giản "trả OK". Nó phải kết thúc trạng thái xác thực trên server, xử lý các tài nguyên liên quan, rồi mới trả kết quả cho client. Spring Security chia ba trách nhiệm:

| Thành phần | Nhiệm vụ | Điểm cần nhớ |
| --- | --- | --- |
| `LogoutFilter` | Phát hiện request khớp logout URL/matcher, điều phối chuỗi cleanup rồi gọi success handler | Là **filter** trong `SecurityFilterChain`, chạy trước `AuthorizationFilter` |
| `LogoutHandler` | Thực hiện **một** tác vụ cleanup: xóa context, vô hiệu hóa session, xóa cookie/token, phát event, hoặc cleanup riêng | Có thể có nhiều handler; nên hoàn tất bình thường, **không ném exception** |
| `LogoutSuccessHandler` | Quyết định **phản hồi sau khi cleanup**: redirect, HTTP status, JSON, hoặc protocol-specific response | Được gọi **sau các LogoutHandler**; không nên thay thế bước cleanup |

Ví dụ nếu frontend muốn logout trả JSON thay vì chuyển hướng, giải pháp đúng thường là **giữ `LogoutFilter` và các `LogoutHandler`**, chỉ thay `LogoutSuccessHandler`. Nếu thêm hành vi riêng như audit hoặc xóa cookie đặc thù, thêm một `LogoutHandler` thay vì viết lại toàn bộ quy trình.

### So sánh với authentication

- **Đăng nhập**: `UsernamePasswordAuthenticationFilter` lấy credential, `AuthenticationManager`/provider kiểm chứng, tạo `Authentication` đáng tin và lưu `SecurityContext` khi cần.
- **Đăng xuất**: `LogoutFilter` thấy một request logout hợp lệ, gọi handlers **dọn** trạng thái/credential, sau đó success handler tạo phản hồi. Logout không gọi lại provider để "xác minh password".
- **Phân quyền**: `AuthorizationFilter` đánh giá URL cần auth. Do `LogoutFilter` chạy trước nó, endpoint logout cấu hình theo DSL mặc định không cần được mở riêng bằng `permitAll` để filter xử lý.

**Logout thành công không đồng nghĩa đã thu hồi mọi credential trên mọi thiết bị.** Logout phiên hiện tại khác "logout all sessions", thu hồi OAuth refresh token, vô hiệu hóa JWT chưa hết hạn hoặc đăng xuất khỏi IdP.

## 2. Luồng xử lý request logout theo mặc định

Với Spring Security Servlet 6.x đã bật form login và CSRF:

```text
Browser đã đăng nhập:
  Cookie: JSESSIONID=...
  POST /logout + CSRF token hợp lệ
        |
        v
SecurityFilterChain
  |
  +-> CsrfFilter
  |      |-- token không hợp lệ -> 403
  |      |-- token hợp lệ -> tiếp tục
  |
  +-> LogoutFilter
         |-- URL/phương thức có khớp logout request matcher?
         |     không -> tiếp tục các filter còn lại
         |     có   -> xử lý logout:
         |
         +-> LogoutHandler #1, #2, ... (cleanup)
         |     * SecurityContextLogoutHandler
         |         - invalidate HttpSession nếu được cấu hình
         |         - clear SecurityContextHolder
         |         - clear/save empty SecurityContext theo repository
         |     * CsrfLogoutHandler: dọn CSRF token
         |     * remember-me logout handler nếu được bật
         |     * LogoutSuccessEventPublishingLogoutHandler
         |     * các custom LogoutHandler mà ứng dụng thêm
         |
         +-> LogoutSuccessHandler
               - mặc định redirect /login?logout
               - hoặc trả HTTP 200/204, JSON, v.v.
        |
        +-> Response (không đi tiếp xuống MVC Controller logout)
```

Thứ tự cụ thể của các cleanup handler còn phụ thuộc cấu hình; sơ đồ là **các nhiệm vụ tiêu biểu**, không phải cam kết chính xác từng vị trí trong một danh sách nội bộ bất biến. Các handler có thể được thêm bởi configurers, ví dụ remember-me. **Không dựa vào thứ tự giả định để biến một handler có lỗi thành cơ chế bảo mật bắt buộc.**

### 2.1. Mặc định Spring Security cung cấp những gì?

Khi Spring Security Servlet được cấu hình thông thường:

- `GET /logout`: nếu CSRF bật và trang mặc định được cung cấp, Spring Security hiển thị **trang xác nhận logout** có form POST và CSRF token. Truy cập GET này **không tự logout**.
- `POST /logout`: request có CSRF token hợp lệ được `LogoutFilter` xử lý.
- `SecurityContextLogoutHandler`: mặc định vô hiệu hóa phiên HTTP liên quan, dọn `SecurityContextHolder` và repository.
- `CsrfLogoutHandler`: dọn CSRF token phía server.
- Remember-me integration, nếu bật, dọn remember-me cookie/dữ liệu liên quan theo cơ chế đang dùng.
- `LogoutSuccessEventPublishingLogoutHandler`: phát `LogoutSuccessEvent` phục vụ các listener.
- `LogoutSuccessHandler` mặc định: redirect về `/login?logout`.

**Khi tắt CSRF** trong một cấu hình nhất định, ngữ nghĩa matcher logout có thể thay đổi; trong cấu hình mặc định việc logout bằng GET có thể được chấp nhận. Vì vậy **không tắt CSRF tùy tiện** cho ứng dụng dùng cookie tự động gửi. Với SPA dùng session cookie, frontend cần lấy và gửi CSRF token đúng cách khi POST logout.

### 2.2. Vì sao LogoutFilter chạy trước AuthorizationFilter?

Đây là điều quan trọng khi người dùng đã có session hết hạn hoặc cookie không còn hợp lệ: `LogoutFilter` xử lý logout theo matcher của nó trước khi đến rule HTTP authorization.

Ví dụ:

```java
// Minh họa cấu hình URL; không phải class Java độc lập.
http.logout(logout -> logout.logoutUrl("/logout"));
```

Không cần thêm `requestMatchers("/logout").permitAll()` **chỉ vì** route được xử lý bởi `LogoutFilter`. Ngược lại, nếu tự viết `@PostMapping("/logout-custom")` trong Spring MVC, endpoint đó nằm sau security filters và cần authorization phù hợp — nhưng khuyến nghị chung vẫn là dùng logout DSL để không bỏ sót cleanup.

### 2.3. Authentication đầu vào có thể null

`LogoutFilter` thường lấy `Authentication` hiện tại trong context và truyền cho các handler. Một client chưa đăng nhập vẫn có thể gửi request logout hợp lệ; trong trường hợp đó `authentication` có thể là `null`. Custom `LogoutHandler` hoặc `LogoutSuccessHandler` **không được giả định luôn có principal**.

Do đó không dùng:

```java
// Sai trong custom LogoutHandler: có thể NullPointerException.
String username = authentication.getName();
```

Mà phải kiểm tra:

```java
// Đoạn minh họa bên trong một handler đã nhận authentication.
String username = authentication == null ? null : authentication.getName();
```

Đừng lộ username, session ID hoặc token thô vào response logout. Client không cần biết server đang giữ bao nhiêu phiên để thực hiện logout hiện tại.

## 3. LogoutHandler: các hoạt động cleanup thực sự

Interface `org.springframework.security.web.authentication.logout.LogoutHandler` có phương thức:

```java
void logout(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication authentication);
```

Chữ ký trên là **minh họa API**, cần imports nếu đưa vào tệp Java. Handler có thể truy cập request/response và `Authentication` của phiên hiện tại. Mỗi handler giải quyết một trách nhiệm rõ ràng; khi có nhiều handler, Spring Security có thể ghép bằng `CompositeLogoutHandler`.

### 3.1. Các handler có sẵn

| Tên | Làm gì | Điều không nên giả định |
| --- | --- | --- |
| `SecurityContextLogoutHandler` | Xóa authentication/context, invalidate `HttpSession` khi bật, lưu context trống phù hợp | Không tự thu hồi JWT/refresh token trong kho khác |
| `CsrfLogoutHandler` | Xóa CSRF token đang lưu để phiên mới không tái dùng token cũ | Không thay CSRF filter hay xử lý quyền |
| `CookieClearingLogoutHandler` | Gửi `Set-Cookie` làm hết hạn cookie được chỉ định | Không hủy trạng thái phía server chỉ bằng cách xóa cookie |
| `LogoutSuccessEventPublishingLogoutHandler` | Phát `LogoutSuccessEvent` | Không mặc nhiên là hệ thống audit bền vững |
| `TokenBasedRememberMeServices` / `PersistentTokenBasedRememberMeServices` | Cleanup remember-me theo implementation | Với token-based, cookie đã bị sao chép có thể vẫn replay tới lúc hết hạn/đổi key/password |
| `HeaderWriterLogoutHandler` + `ClearSiteDataHeaderWriter` | Gửi `Clear-Site-Data` để browser dọn cookie/storage/cache theo directive | Chính sách browser support và scope của origin cần được hiểu rõ |

### 3.2. `SecurityContextLogoutHandler` quan trọng nhất đối với session

`SecurityContextLogoutHandler` xử lý phần cốt lõi của logout dựa trên phiên:

1. **Invalidate `HttpSession`** nếu cấu hình cho phép, khiến session ID đang dùng không còn tham chiếu đến trạng thái login đó.
2. **Clear `SecurityContextHolder`** để request/thread hiện tại không còn authentication.
3. **Clear `SecurityContextRepository`** theo cơ chế lưu context đang dùng, tránh một context cũ lại được nạp lên ở request tiếp theo.

Nếu chỉ `SecurityContextHolder.clearContext()` trong controller mà bỏ qua session/repository, request kế tiếp vẫn có thể đọc lại context đã lưu và coi user chưa hề logout.

Nếu chỉ gửi cookie rỗng nhưng vẫn để session server sống, kẻ có bản sao session ID trước đó vẫn có thể dùng nó, tùy cấu hình. **Invalidation server-side mới là bước quan trọng đối với cookie phiên.**

### 3.3. Xóa cookie và xóa session là hai việc khác nhau

Cấu hình sau thêm yêu cầu browser xóa cookie có tên `JSESSIONID`:

```java
// Đoạn DSL minh họa, không phải ứng dụng độc lập.
http.logout(logout -> logout.deleteCookies("JSESSIONID"));
```

Điều này *không thay thế* `invalidateHttpSession(true)`. Ngoài ra cookie xóa phải trùng `Path`/`Domain` phù hợp để browser thực sự loại bỏ; khi triển khai sau reverse proxy, cookie scope có thể khác mặc định. Spring Security nêu rằng cấu hình xóa `JSESSIONID` thường **không cần thiết** nếu session đã được invalidate; ví dụ bên dưới dùng explicit `deleteCookies` như một minh họa, không coi đó là biện pháp bảo mật cốt lõi.

Nếu dùng cookie tùy biến của ứng dụng (ví dụ `PREFS` không phải credential) và có lý do dọn nó khi logout, dùng `CookieClearingLogoutHandler` hoặc DSL `deleteCookies`. Không vô ý xóa cookie thiết yếu của các ứng dụng khác chia sẻ domain.

### 3.4. Custom LogoutHandler: thêm audit hoặc cleanup phụ trợ

Ví dụ handler được đăng ký bằng DSL:

```java
// Minh họa một hàm callback: phải nhận đủ dependency ở class thực tế.
http.logout(logout -> logout.addLogoutHandler(
    (request, response, authentication) -> {
        if (authentication != null) {
            auditService.recordLogout(authentication.getName());
        }
    }
));
```

**Nguyên tắc quan trọng:** Spring Security quy ước `LogoutHandler` là tác vụ cleanup, **không nên ném exception** để chặn chuỗi logout. Nếu audit DB lỗi, nên dùng giải pháp audit đáng tin có xử lý thất bại/bất đồng bộ phù hợp; không để lỗi logging khiến server bỏ qua xóa session. Nếu có yêu cầu pháp lý không được trả thành công khi một hệ thống ngoài chưa xác nhận, phải thiết kế orchestration riêng — đừng vô tình biến `LogoutHandler` thành giao dịch phân tán.

Không đưa authentication thô hoặc session ID vào audit nếu không có kiểm soát bảo mật. Có thể ghi ID người dùng nội bộ đã được xác thực, thời gian, request ID và outcome (theo chính sách quyền riêng tư).

## 4. LogoutSuccessHandler: chỉ quyết định cách trả kết quả

Interface `org.springframework.security.web.authentication.logout.LogoutSuccessHandler` có phương thức:

```java
void onLogoutSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication authentication) throws IOException, ServletException;
```

Đây là **chữ ký API minh họa**. Handler này được gọi khi chuỗi cleanup đã chạy. Nó phù hợp cho:

- Web browser truyền thống: **redirect** về `/login?logout` hoặc trang thông báo đăng xuất.
- SPA/JSON API dùng session cookie: trả **200 OK** kèm JSON, hoặc **204 No Content** để client tự điều hướng.
- Một số giao thức SSO: phối hợp trình tự logout sang IdP bằng implementation riêng, nhưng không tự suy rằng local logout đã thu hồi phiên IdP.

Ví dụ chỉ đổi status:

```java
// Khi chỉ cần HTTP 200 thay cho redirect.
http.logout(logout -> logout
    .logoutSuccessHandler(new HttpStatusReturningLogoutSuccessHandler())
);
```

Ví dụ JSON:

```java
// Chữ ký lambda là (request, response, authentication).
http.logout(logout -> logout.logoutSuccessHandler(
    (request, response, authentication) -> {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write("{\"message\":\"logged out\"}");
    }
));
```

Nếu chỉ muốn URL redirect, dùng `logoutSuccessUrl("/login?logout")`; **không kết hợp hai chiến lược rồi trông đợi cả redirect và JSON đồng thời**.

**Tên "success" có giới hạn ý nghĩa:** khi browser nhận HTTP 200 sau local logout, chưa chứng minh mọi thiết bị, access token phát trước đó, OIDC session hoặc cache của hệ thống thứ ba đã bị thu hồi.

## 5. Ví dụ Spring Boot: form login + LogoutFilter + custom handler và JSON success

Ví dụ này dùng cấu hình logout tiêu chuẩn, không viết `@PostMapping("/logout")`.

Mục tiêu:

- `alice` / `demo-pass123` là tài khoản **demo** (không dùng credential hardcoded trong production).
- `POST /login` với CSRF hợp lệ tạo authenticated `HttpSession`.
- `GET /api/me` yêu cầu người dùng đã đăng nhập.
- `POST /logout` với CSRF hợp lệ:
  - `LogoutFilter` gọi cleanup mặc định và custom `LogoutHandler` ghi bộ đếm audit trong bộ nhớ.
  - Session bị invalidate, context được dọn.
  - `LogoutSuccessHandler` trả **200 + JSON**.
- `POST /logout` **không có CSRF** bị chặn 403 trước khi cleanup.
- Truy cập lại endpoint protected **không gửi session hợp lệ** sẽ bị yêu cầu đăng nhập.

### 5.1. Cấu trúc dự án

```text
logout-filter-demo/
├── pom.xml
├── src/main/java/com/example/logout/LogoutDemoApplication.java
└── src/test/java/com/example/logout/LogoutDemoApplicationTests.java
```

**`pom.xml`:**

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
    <groupId>com.example</groupId>
    <artifactId>logout-filter-demo</artifactId>
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

### 5.2. Ứng dụng Java

Tạo **`src/main/java/com/example/logout/LogoutDemoApplication.java`**:

```java
package com.example.logout;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.concurrent.atomic.AtomicInteger;

@SpringBootApplication
public class LogoutDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("demo-pass123"))
                        .roles("USER")
                        .build()
        );
    }

    // Dùng bộ đếm để test custom LogoutHandler được gọi.
    // Đây KHÔNG phải audit store bền vững trong production.
    @Bean
    LogoutAuditService logoutAuditService() {
        return new LogoutAuditService();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            LogoutAuditService auditService) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login").permitAll()
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            // Form login mặc định; điều hướng thẳng đến endpoint đã có.
            .formLogin(form -> form
                .defaultSuccessUrl("/api/me", true)
            )
            .logout(logout -> logout
                // LogoutFilter, không phải Spring MVC controller.
                .logoutUrl("/logout")
                // Handler tùy chỉnh bổ sung, không thay cleanup mặc định.
                .addLogoutHandler((request, response, authentication) ->
                    auditService.onLogout(authentication)
                )
                // Mặc định hai tùy chọn này đều true; viết ra để minh họa.
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                // Có thể thừa khi session đã bị invalidate.
                .deleteCookies("JSESSIONID")
                // Chỉ thay phản hồi sau cleanup, không bỏ default handlers.
                .logoutSuccessHandler((request, response, authentication) -> {
                    response.setStatus(HttpServletResponse.SC_OK);
                    response.setContentType("application/json");
                    response.setCharacterEncoding("UTF-8");
                    response.getWriter().write(
                            "{\"message\":\"logged out\"}"
                    );
                })
            );

        // Không disable CSRF: form login/logout cần token hợp lệ.
        return http.build();
    }

    static final class LogoutAuditService {
        private final AtomicInteger completedForKnownUsers = new AtomicInteger();

        void onLogout(Authentication authentication) {
            // Unauthenticated logout có thể truyền null; tránh NullPointerException.
            if (authentication != null) {
                completedForKnownUsers.incrementAndGet();
            }
        }

        int completedCount() {
            return completedForKnownUsers.get();
        }
    }

    public record WhoAmI(String username, boolean authenticated) {}

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/api/me")
        WhoAmI me(Authentication authentication) {
            return new WhoAmI(authentication.getName(), authentication.isAuthenticated());
        }
    }
}
```

### 5.3. Giải thích lựa chọn trong ví dụ

1. **Không tự tạo LogoutFilter.** `http.logout(...)` của Spring Security xây dựng filter, matcher, cleanup handlers và success handler. Việc viết riêng một servlet filter và chèn sai vị trí có thể bỏ qua CSRF hoặc dọn context không đầy đủ.
2. **CSRF mặc định vẫn bật.** Vì cookie session được browser tự gửi, một website độc hại không được phép logout người dùng chỉ bằng một request giả mạo. Form/login/logout đều có cơ chế CSRF phù hợp.
3. **Thêm handler, không thay handler mặc định.** `addLogoutHandler` chỉ thêm bộ đếm audit. `SecurityContextLogoutHandler` vẫn chịu trách nhiệm invalidate session và clear context, không cần gọi thủ công trong callback này.
4. **Tránh exception trong cleanup.** Handler demo chỉ tăng `AtomicInteger`; trong ứng dụng thực, audit bền vững nên theo cơ chế có xử lý thất bại. Không gọi hệ thống bên ngoài bằng tác vụ có thể block vô hạn trong logout handler.
5. **Response JSON không quyết định hiệu lực session.** `logoutSuccessHandler` chạy sau cleanup và trả `200`. Nó không tự xóa session, vì thế code không dùng nó để xử lý bảo mật cốt lõi.
6. **Không cần `requestMatchers("/logout").permitAll()`** vì `LogoutFilter` bắt logout trước AuthorizationFilter. `/api/me` cần authentication; `/public` cho phép anonymous.
7. **Cookie `JSESSIONID` không phải bằng chứng duy nhất.** App đã invalidate session, và `deleteCookies` chỉ gửi hướng dẫn xóa browser cookie. Bản sao session ID cũ sẽ không còn tham chiếu đến phiên đã bị hủy trong session store đúng.
8. **Form login thành công chuyển đến `/api/me`**, tránh truy cập `/` mà demo không cung cấp endpoint.
9. **Logout URL không nhận username do client khai.** Mọi cleanup phải dựa vào authentication hiện tại được load từ `SecurityContext`/session của request, không dựa vào `?user=alice` hay JSON body tự nhận người dùng.
10. **Sau logout**, một request mới không có session hợp lệ đến `/api/me` sẽ được chuyển đến login page vì demo bật `formLogin`. Với REST API dùng custom entry point, nó có thể là HTTP 401 thay vì redirect.

## 6. Kiểm thử chính xác hành vi logout bằng MockMvc

Tạo **`src/test/java/com/example/logout/LogoutDemoApplicationTests.java`**:

```java
package com.example.logout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    LogoutDemoApplication.LogoutAuditService auditService;

    private MockHttpSession logIn() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass123"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void logoutRunsCleanupAndReturnsJsonInsteadOfRedirect() throws Exception {
        MockHttpSession session = logIn();

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authenticated").value(true));

        int previousAuditCount = auditService.completedCount();

        mvc.perform(post("/logout").session(session).with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"message\":\"logged out\"}"));

        // MockHttpSession bị invalidated: không dùng session này cho request mới.
        assertTrue(session.isInvalid());
        assertTrue(auditService.completedCount() > previousAuditCount);

        // Request không còn session đã xác thực phải được gửi về login.
        mvc.perform(get("/api/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void postLogoutWithoutCsrfDoesNotDestroySession() throws Exception {
        MockHttpSession session = logIn();

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));

        // Cleanup đúng cách cuối test.
        mvc.perform(post("/logout").session(session).with(csrf()))
                .andExpect(status().isOk());
        assertTrue(session.isInvalid());
    }

    @Test
    void publicResourceRemainsAccessibleToAnonymousClient() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }
}
```

Chạy từ thư mục có `pom.xml`:

```bash
mvn test
```

**Ý nghĩa của các test:**

- Test thứ nhất không chỉ kiểm tra response JSON. Nó login thật qua `UsernamePasswordAuthenticationFilter`, dùng session đó để truy cập endpoint protected, logout bằng `LogoutFilter`, kiểm tra `MockHttpSession.isInvalid()` và audit callback được gọi. Request mới không gửi session không còn được xem là đã đăng nhập.
- Test thứ hai thử **POST logout không có CSRF**, nhận 403 và xác nhận session chưa bị dọn. Sau đó gửi CSRF hợp lệ để thực sự logout.
- Test thứ ba cho thấy endpoint công khai không phụ thuộc session.

**Giới hạn kiểm thử:** `MockMvc` sử dụng mô phỏng servlet request/session. Nó chứng minh đường đi của filter chain và việc invalidate `MockHttpSession`, **không thay thế** bài test với HTTP container thật, cookie Path/Domain, reverse proxy và Redis/distributed session store. Các test Maven trong bài là mã để người học chạy; không nên coi chúng đã được thực thi chỉ vì xuất hiện trong tài liệu.

### Cách đọc HTTP response sau logout

Theo cấu hình demo, kết quả logout hợp lệ dự kiến là **200 OK**:

```http
HTTP/1.1 200 OK
Content-Type: application/json;charset=UTF-8

{"message":"logged out"}
```

Đây là minh họa phần tiêu biểu của response. Header `Set-Cookie` để xóa `JSESSIONID` có thể xuất hiện; giá trị `Path`/`Expires`/`Max-Age` phụ thuộc session container và cấu hình. Không hard-code toàn bộ response byte-by-byte. Một POST thiếu CSRF sẽ bị trả **403 Forbidden** trong cấu hình demo; một GET protected không còn session sẽ redirect đến login page.

## 7. Thực hành bằng trình duyệt hoặc curl

### 7.1. Thử an toàn nhất bằng browser

1. Chạy `mvn spring-boot:run`.
2. Mở `http://localhost:8080/login`, đăng nhập bằng `alice` / `demo-pass123`. Trang form mặc định có CSRF token.
3. Sau khi đăng nhập, trình duyệt đến `/api/me` và nhận JSON cho user `alice`.
4. Mở `http://localhost:8080/logout` bằng GET: ở cấu hình CSRF mặc định, Spring Security có thể hiển thị trang xác nhận logout, **chưa hủy session**.
5. Gửi form xác nhận logout bằng POST và CSRF token. Vì có custom `LogoutSuccessHandler`, response là `{"message":"logged out"}` thay vì redirect mặc định.
6. Truy cập lại `/api/me`: user được yêu cầu đăng nhập trở lại.
7. Nếu thử `POST /logout` bằng JavaScript, nhớ gửi CSRF token từ nguồn mà ứng dụng thực cung cấp. Không khuyến khích thêm URL GET có tác dụng hủy session để tránh CSRF/logout-by-link.

### 7.2. Vì sao `curl -X POST /logout` không đủ?

`curl` không tự lấy CSRF token, không tự nhập username/password và không tự duy trì cookie jar nếu không yêu cầu. Lệnh đơn lẻ:

```bash
curl -i -X POST http://localhost:8080/logout
```

thường bị CSRF filter chặn **403**, chứ không chứng minh logout bị hỏng. Muốn kiểm thử thủ công bằng curl cần:

- Sử dụng `-c cookies.txt` / `-b cookies.txt` để duy trì session cookie (không commit cookie jar vào repository).
- Lấy `_csrf` token từ trang login/logout hoặc một endpoint cấp CSRF token do ứng dụng cung cấp.
- POST `/login` và `/logout` cùng session cookie và token hợp lệ, giữ đúng `Content-Type`, tham số form và URL.
- Không copy raw `JSESSIONID`, CSRF token hoặc cookie nhớ đăng nhập vào chat/log công khai.

Ví dụ kiểm thử tự động `MockMvc` ở mục 6 tạo CSRF token hợp lệ và quản lý phiên cho từng request, thuận tiện hơn curl trong bài học này.

## 8. Kịch bản nâng cao: tự viết logout endpoint và tích hợp nhiều cơ chế

### 8.1. Tại sao không khuyến khích `@PostMapping("/logout")` tự viết?

Đoạn sau **sai/thiếu**:

```java
// Sai: xóa một tham chiếu cục bộ không đảm bảo session store đã được dọn.
@PostMapping("/custom-logout")
String logout() {
    SecurityContextHolder.clearContext();
    return "ok";
}
```

Nếu `SecurityContext` còn được lưu trong `HttpSession` hoặc repository, request sau vẫn có thể khôi phục authentication. Với session login, nên dùng logout DSL.

Khi thực sự bắt buộc có endpoint MVC riêng (ví dụ giao thức/contract đặc thù), cần gọi các handler Spring Security tương đương; đoạn minh họa dưới đây cho thấy **một phần việc cốt lõi**, không phải controller hoàn chỉnh:

```java
// Chỉ minh họa bên trong handler/controller đã có dependencies.
SecurityContextLogoutHandler contextHandler = new SecurityContextLogoutHandler();
contextHandler.setInvalidateHttpSession(true);
contextHandler.logout(request, response, authentication);
```

Phải xử lý CSRF, remember-me, custom cookies, event, response, security context repository và quyền truy cập theo cấu hình thực tế. **Không tạo song song mapping cùng /logout với LogoutFilter**: filter thường bắt request trước MVC nên controller sẽ không được gọi; phân tích này giúp tránh debug nhầm.

### 8.2. Phân biệt `logoutUrl`, `logoutSuccessUrl` và `logoutSuccessHandler`

| Lựa chọn DSL | Tác dụng | Ví dụ |
| --- | --- | --- |
| `logoutUrl("/signout")` | Đổi URL được **LogoutFilter** nhận diện | POST /signout |
| `logoutSuccessUrl("/signed-out")` | Sau cleanup **redirect** đến URL đích | 302 Location: /signed-out |
| `logoutSuccessHandler(...)` | Tùy biến callback tạo response | 200 JSON hoặc 204 |
| `addLogoutHandler(...)` | Bổ sung **cleanup** trước khi response | Ghi audit, xóa app cookie |
| `deleteCookies("PREFS")` | Thêm cookie-clearing logout handler | Set-Cookie làm hết hạn cookie |
| `invalidateHttpSession(true)` | Chỉ định vô hiệu hóa phiên | Tác động server-side |
| `clearAuthentication(true)` | Xóa authentication đang giữ | Không tự thu hồi các token ngoài hệ thống |

**Lưu ý** nếu redirect tới một endpoint MVC tùy chỉnh sau logout, endpoint đích cần được `permitAll` hoặc `logout(...).permitAll()` theo cấu hình để anonymous user truy cập; nếu không có thể bị redirect lại login. Nếu trả JSON trực tiếp từ `LogoutSuccessHandler`, không cần controller success endpoint.

### 8.3. Logout một phiên không phải logout toàn bộ thiết bị

Giả sử alice có session A trên laptop và session B trên điện thoại. `POST /logout` từ A thường chỉ invalidate **session A**. Session B vẫn có thể hợp lệ, trừ khi ứng dụng có chính sách thu hồi mọi phiên và thực thi được ở session store tương ứng.

`SessionRegistry` có thể giúp đánh dấu các phiên khác là expired, nhưng `SessionInformation.expireNow()` **không hủy ngay `HttpSession` ở mọi node**. Với các phiên còn sống, `ConcurrentSessionFilter` xử lý cờ expired ở request tiếp theo. Nếu yêu cầu "logout all devices" tức thời, cần giải pháp thu hồi session/token thật sự và phân tán đúng kiến trúc; đừng chỉ xóa registry metadata.

### 8.4. Logout có remember-me cookie

Nếu ứng dụng bật remember-me, một cookie dài hạn có thể tự tạo authentication sau khi phiên cũ mất. Cấu hình logout tiêu chuẩn tích hợp `RememberMeServices` để xóa cookie và, với persistent-token, dọn bản ghi theo implementation. Nếu tự viết logout và chỉ xóa `JSESSIONID`, remember-me cookie còn lại có thể làm user tự đăng nhập lại.

**Cẩn trọng với token-based remember-me:** xóa cookie trên trình duyệt **không thu hồi** một bản sao cookie đã bị lấy cắp; vì không có store để revoke theo từng cookie, token có thể còn sử dụng được đến lúc hết hạn/đổi key/password hash. Persistent token cho phép chính sách thu hồi hiệu quả hơn khi có repository được quản lý đúng.

### 8.5. Logout với JWT/Bearer access token

Với Resource Server stateless, mỗi request gửi Bearer token độc lập. Xóa `HttpSession` không làm JWT đã phát tự nhiên mất chữ ký hoặc hết `exp`. "Logout" có thể bao gồm:
- Browser xóa access token khỏi bộ nhớ/storage an toàn.
- Authorization Server thu hồi **refresh token** theo giao thức hỗ trợ.
- Access token sống ngắn; nếu cần thu hồi ngay, dùng danh sách revoke/denylist, introspection hoặc cơ chế đồng bộ chính sách khác.
- Client không tiếp tục gửi token và ứng dụng xử lý token hết hạn đúng cách.

Đừng khẳng định `SecurityContextLogoutHandler` có thể vô hiệu hóa mọi JWT trong hệ thống.

### 8.6. OAuth2/OIDC Single Logout, SAML và IdP

Đăng xuất khỏi ứng dụng local **không nhất thiết** đăng xuất khỏi identity provider. Nếu user được SSO, họ có thể lập tức đăng nhập lại qua IdP còn session. Với OIDC có `OidcClientInitiatedLogoutSuccessHandler` để điều phối **RP-initiated logout** ở các nhà cung cấp hỗ trợ; với SAML/CAS có cơ chế single logout riêng.

Đó là **quy trình liên hệ nhiều hệ thống** với redirect và điều kiện riêng; không thay bằng một callback luôn trả JSON. Bài này giải thích local Spring Security Servlet logout trước, rồi nêu ranh giới để không đồng nhất hai khái niệm.

## 9. Lỗi thường gặp và cách tìm đúng nguyên nhân

### 9.1. POST /logout trả 403

Khả năng cao **thiếu hoặc sai CSRF token**, đặc biệt khi frontend SPA chỉ gọi `fetch("/logout", {method: "POST"})` và không gửi header/token. Kiểm tra thứ tự:
1. CSRF còn bật? Với form/session cookie, đây thường là cấu hình đúng.
2. Client đã lấy token từ server và gửi lại token gắn với cùng session chưa?
3. Browser có gửi cookie session phù hợp hay không? Path, Domain, SameSite và credentials mode trong fetch đúng chưa?
4. Token có bị xoay/xóa do login/logout trước đó không?

Không vội thêm `csrf.disable()` vào ứng dụng để "sửa" 403. Bài test cố ý không gửi CSRF và kỳ vọng 403.

### 9.2. Logout trả 200 nhưng refresh lại vẫn đăng nhập

Cần kiểm tra:
- Có dùng `LogoutFilter` hay tự viết controller chỉ trả 200?
- `SecurityContextLogoutHandler` thực sự chạy, invalidate session, clear context/repository không?
- Browser có **remember-me cookie** còn hợp lệ và tự login lại không?
- Có proxy/cache trả dữ liệu authenticated cũ? Có nhiều instance với session store không đồng bộ?
- Access token/refresh token khác còn được browser gửi lại?
- Client có giữ JWT ở localStorage rồi tự đính Authorization header sau khi logout không?

**Không coi status 200 là bằng chứng duy nhất rằng credentials đã được thu hồi.** Test cần chạy request mới và đánh giá theo credential thực sự còn trong request.

### 9.3. GET /logout không làm gì

Khi CSRF bật, GET thường mở confirmation page, **không hủy session**. Đó là cách bảo vệ khỏi logout bởi link/ảnh trên site khác. POST có CSRF mới là hành vi thực. Nếu hệ thống tắt CSRF thì matcher có thể khác, nhưng không nên thiết kế logout đổi trạng thái thông qua GET trong app cookie-based.

### 9.4. Redirect vòng lặp sau logout

Nếu `logoutSuccessUrl("/signed-out")` trỏ tới endpoint yêu cầu `authenticated()`, context đã bị xóa nên user bị redirect về login; nếu login lại redirect về trang sai, có thể thành vòng lặp. Mở public access cho trang hiển thị sau logout hoặc trả JSON/204 trực tiếp.

### 9.5. Logout handler ném exception, session chưa được dọn

`LogoutHandler` dành cho cleanup và **không nên throw**. Ví dụ, gọi dịch vụ audit từ xa mà không timeout có thể làm gián đoạn chuỗi. Tách các tác vụ không quan trọng hoặc áp dụng cơ chế error handling phù hợp. Với callback an ninh quan trọng, phải xác minh thứ tự/durable state theo policy, không giả định một `try/catch` trống là đủ.

### 9.6. Cookie vẫn xuất hiện trong DevTools

Browser có thể giữ cookie khác phạm vi (path/domain) hoặc hiển thị cookie đã hết hạn trước khi refresh. Đặc biệt xóa cookie cần match Path/Domain. Quan trọng hơn, dùng server-side session invalidation để chặn việc tái sử dụng `JSESSIONID` cũ; chỉ xóa browser cookie không bảo vệ khi cookie đã bị sao chép.

### 9.7. Kiểm thử MockMvc sau logout ném lỗi session invalid

Khi `MockHttpSession` đã invalidate, cố đưa **cùng object** `.session(oldSession)` vào request tiếp theo có thể ném lỗi mô phỏng vì session không còn hợp lệ. Đây không phải lỗi logout. Để xác minh logout, kiểm tra `session.isInvalid()` và tạo **request mới không có phiên đã xác thực**; với integration HTTP thật, gửi cookie cũ và xem container từ chối/khởi tạo phiên mới.

## 10. Checklist triển khai và an ninh

- [ ] Logout được xử lý bằng `http.logout(...)`/`LogoutFilter` thay vì controller tự ý xóa một biến.
- [ ] Request logout thay đổi trạng thái sử dụng **POST + CSRF** khi browser gửi session cookie.
- [ ] `SecurityContextLogoutHandler` dọn `SecurityContextHolder`, repository và invalidate session đúng cách.
- [ ] Cleanup cookie riêng, remember-me, CSRF token hoặc token store **nếu ứng dụng thực sự dùng chúng**.
- [ ] `LogoutHandler` bổ sung có trách nhiệm rõ, xử lý `authentication == null` và không ném exception làm ngắt logout.
- [ ] `LogoutSuccessHandler` chỉ điều khiển response; không cho rằng HTTP 200 đã revoke mọi loại credential.
- [ ] Nếu success redirect đến MVC endpoint, endpoint đó có quyền truy cập anonymous phù hợp.
- [ ] Không log/echo session ID, raw cookie, access token hoặc refresh token.
- [ ] Có test 403 khi thiếu CSRF, test session invalidated, test request mới cần login, test remember-me nếu dùng.
- [ ] Nếu cần logout mọi thiết bị, có cơ chế revoke session/token phân tán thật, không dựa vào xóa cookie hiện tại.
- [ ] Nếu có OAuth2/OIDC/SAML, thiết kế riêng logout với IdP và refresh/access tokens.
- [ ] HTTPS, cookie Secure/HttpOnly/SameSite, cache-control và reverse-proxy handling được kiểm tra trên môi trường deploy thật.

## 11. Tự kiểm tra kiến thức

1. Vì sao `LogoutFilter` thường xử lý `POST /logout` trước khi `AuthorizationFilter` đánh giá request?
2. Ba trách nhiệm của `LogoutFilter`, `LogoutHandler` và `LogoutSuccessHandler` khác nhau ra sao?
3. Handler nào invalidate `HttpSession` và dọn `SecurityContext`?
4. Vì sao chỉ `SecurityContextHolder.clearContext()` trong controller có thể không đủ?
5. Trong app có CSRF, `GET /logout` và `POST /logout` khác nhau như thế nào?
6. `addLogoutHandler(...)` dùng khi nào; liệu nó có thay thế toàn bộ cleanup mặc định?
7. Một custom handler được phép giả định `authentication != null` không?
8. Nếu muốn trả `204` thay vì redirect, nên thay thành phần nào?
9. Vì sao xóa `JSESSIONID` trên browser không đồng nghĩa hủy phiên đã bị đánh cắp?
10. Vì sao logout thành công không nhất thiết revoke JWT hoặc logout mọi thiết bị?
11. Khi app có remember-me, cần chú ý điều gì để tránh user tự đăng nhập lại ngay sau logout?
12. Làm cách nào kiểm chứng logout ở mức filter chain mà không nhầm HTTP 200 với security state?

**Gợi ý đáp án:** (1) filter đứng trước authorization; (2) nhận diện/điều phối, cleanup, phản hồi; (3) `SecurityContextLogoutHandler`; (4) repository/session còn context; (5) GET confirmation, POST hợp lệ mới logout; (6) thêm cleanup, không thay default; (7) không, có thể null; (8) `LogoutSuccessHandler`/`HttpStatusReturningLogoutSuccessHandler`; (9) session server phải invalidate; (10) credential phân tán có lifecycle khác; (11) nhớ xóa/thu hồi remember-me đúng cơ chế; (12) thử login có session, POST logout có CSRF, assert session invalid, request mới cần xác thực.

## 12. Tài liệu chính thức

- Spring Security 6.5 — Handling Logouts (kiến trúc, handlers, success handlers, cookie, CSRF, endpoint): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security — LogoutFilter API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/LogoutFilter.html
- Spring Security — LogoutHandler API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/LogoutHandler.html
- Spring Security — LogoutSuccessHandler API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/LogoutSuccessHandler.html
- Spring Security — SecurityContextLogoutHandler API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html
- Spring Security — Testing Logout with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — Remember-Me: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
