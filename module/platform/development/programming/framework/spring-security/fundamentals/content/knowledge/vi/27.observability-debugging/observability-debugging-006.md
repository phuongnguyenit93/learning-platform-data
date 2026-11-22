# Điều tra mất đăng nhập do cookie, phiên hoặc ngữ cảnh không được lưu

> **Bối cảnh:** Spring Security — fundamentals / Quan sát và gỡ lỗi. Bài này giải quyết hiện tượng *đăng nhập thành công nhưng request kế tiếp lại bị coi là chưa đăng nhập*, với trọng tâm ứng dụng **Servlet** dùng **cookie phiên + HttpSession + SecurityContextRepository**. Ví dụ đầy đủ sử dụng Java 17+, Spring Boot 3.5.0 và Spring Security 6.x. Phần riêng giải thích vì sao ứng dụng JWT/HTTP Basic stateless không nhất thiết lưu phiên.

## 1. Xác định đúng triệu chứng

Quy trình có vấn đề thường là:

1. Người dùng nhập username/password và nhận thông báo thành công; server có thể trả `302` để chuyển trang.
2. Người dùng điều hướng hoặc refresh.
3. `GET /api/me` nhận `401`, trình duyệt bị chuyển về `/login`, hoặc SPA hiển thị trạng thái anonymous.

**Đừng vội kết luận session bị mất.** Một `403` có thể do thiếu quyền hoặc CSRF; redirect `302` có thể xảy ra vì request chưa xác thực, nhưng response login cũng có thể redirect thành công. Việc thấy `JSESSIONID` cũng không chứng minh user đã đăng nhập: session có thể tồn tại chỉ để giữ CSRF token/saved request.

Có ba tầng phải kiểm tra theo đúng thứ tự:

| Tầng | Câu hỏi | Nếu không đạt |
|---|---|---|
| **Cookie phía client** | Server có phát cookie đúng và browser có gửi lại cookie hiện hành không? | Browser/client không mang định danh phiên tới server |
| **Phiên phía server** | Cookie có dẫn tới một `HttpSession` đang tồn tại ở đúng instance/store không? | Cookie còn nhưng session timeout, invalidated, restart, hoặc mất qua nhiều node |
| **Ngữ cảnh Spring Security** | `SecurityContextRepository` có lưu và khôi phục `Authentication` đã xác minh cho request tiếp theo không? | Session tồn tại nhưng Spring Security coi user là anonymous |

**Mục tiêu điều tra:** thu được bằng chứng từ ít nhất **hai HTTP requests liên tiếp**: login và request ngay sau login. Chỉ sửa mắt xích đã xác định, không tắt các bảo vệ để làm lỗi biến mất.

## 2. Vòng đời một session login

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security
    participant R as SecurityContextRepository
    participant H as HttpSession
    C->>S: POST /login + credentials + CSRF
    S->>S: Xác thực qua AuthenticationManager
    S->>S: Tạo SecurityContext chứa Authentication
    S->>R: saveContext(context, request, response)
    R->>H: Lưu context trong session
    S-->>C: 302 + Set-Cookie session ID
    Note over C,S: Có thể đổi session ID để chống session fixation
    C->>S: GET /api/me + Cookie session ID mới
    S->>R: load context cho request mới
    R->>H: Truy hồi session theo ID
    H-->>R: SecurityContext đã lưu
    R-->>S: Authentication của user
    S-->>C: 200: principal đã xác minh
~~~

`SecurityContextHolder` **không phải bộ nhớ phiên**. Trong Servlet stack, mặc định context gắn với thread xử lý request; Spring Security dọn context khi request kết thúc để không rò danh tính sang thread/request khác. Vì vậy, thấy `SecurityContextHolder` không còn Authentication sau request **không phải lỗi**. Điều cần xác minh là repository có lưu và tải lại context hay không.

Ba thứ thường bị nhầm:

- **Cookie `JSESSIONID`**: định danh tham chiếu tới session; tên có thể được cấu hình lại (hoặc dùng `SESSION` với Spring Session).
- **`HttpSession`**: nơi servlet container/session store giữ dữ liệu cho nhiều request.
- **`SecurityContext`**: chứa `Authentication` đã xác thực, thường được repository liên kết với session.

Một session được tạo để lưu `CsrfToken` có thể tồn tại **trước login**. Sau login, ID có thể đổi do session fixation protection; client phải cập nhật cookie mới nhất.

## 3. Bảng khoanh vùng nguyên nhân

| Bằng chứng | Giả thuyết ưu tiên | Kiểm tra tiếp |
|---|---|---|
| Login `302`, request sau thiếu `Cookie` | `SameSite`, `Secure`, `Path`, `Domain`, cookie bị chặn/hết hạn, thiếu `fetch.credentials` | DevTools → Network/Cookies → blocked reasons; so host, scheme, origin |
| Có Cookie, `getSession(false)` là null | Session timeout, logout/invalidate, restart, session store không chia sẻ giữa node | TTL, session store, node A/B, logout events, cookie ID sau login |
| Có session, không có saved `SecurityContext` | Custom login quên `saveContext`, `NullSecurityContextRepository`, `STATELESS`, repo không đồng nhất | Login success code, repo của chain, session policy |
| Context tồn tại nhưng Authentication anonymous | Login không thành công; context bị thay/clear; concurrent-session handling | Authentication events, failure handler, logout, principal |
| Authentication đúng nhưng `403` | Thiếu authority hoặc CSRF; không hẳn mất login | Rule `authorizeHttpRequests`, `@PreAuthorize`, CSRF |
| Curl dùng cookie jar được, browser không được | Cookie hoặc browser cross-origin/CORS | `Set-Cookie`/cookie policy, fetch credentials, frontend URL |
| Lúc được lúc mất sau cân bằng tải | Session memory riêng từng node, không có shared store | Instance ID, Spring Session/Redis/JDBC, affinity |
| Request Bearer không có session nhưng thành công | Stateless là thiết kế đúng | JWT/Basic request credentials, `SessionCreationPolicy` |

`401 Unauthorized` thường là chưa có credentials hợp lệ cho API; `302` có thể là redirect của form login; `403 Forbidden` có thể do user đã xác thực nhưng thiếu quyền hoặc thiếu CSRF token. Không đánh đồng ba loại phản hồi.

## 4. Điều tra trên browser bằng hai HTTP exchanges

Bật **Network → Preserve log** trong DevTools, thực hiện login rồi gọi API bảo vệ. Ghi các trường sau, nhưng **không lưu nguyên giá trị cookie/token**:

1. Request login: URL, method, scheme/host/port, status, `Location` nếu redirect.
2. Response login: header `Set-Cookie` có không, tên cookie, `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`, `Max-Age/Expires`. Đôi khi cookie đã được tạo từ request CSRF trước login.
3. Application → Cookies: browser có thật sự lưu cookie không? Có “blocked reason” hoặc domain/path khác với API không?
4. Request **kế tiếp** `GET /api/me`: có header `Cookie` với cookie hiện hành không? Request đến đúng API host không?
5. Response sau login: HTTP status thực, header redirect, body, log server. Nếu request có cookie, kiểm tra session lookup và SecurityContext load.
6. Với nhiều node, ghi **node phục vụ login và node phục vụ request sau**.

Ví dụ header được **ẩn giá trị bí mật**:

~~~http
HTTP/1.1 302 Found
Location: /
Set-Cookie: JSESSIONID=REDACTED; Path=/; HttpOnly; SameSite=Lax
~~~

Request kế tiếp:

~~~http
GET /api/me HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=REDACTED
~~~

Nếu không có cookie ở request thứ hai, điều tra client/cookie. Nếu có cookie nhưng server không nhận ra session, điều tra session store/timeout. Nếu session tồn tại mà không có Authentication, điều tra cách lưu `SecurityContext`.

**Không in raw `Cookie`, `Set-Cookie`, session ID, Bearer token, username/password hay CSRF token vào log/ticket.** Cookie phiên có thể hoạt động như credential; lộ giá trị là nguy cơ chiếm phiên.

## 5. Thuộc tính cookie và nguyên nhân bị trình duyệt bỏ qua

### Domain, host và Path

Cookie host-only chỉ được gửi đến host đã tạo nó. `api.example.com` và `web.example.com` không phải cùng host. `localhost` và `127.0.0.1` là hai host khác nhau. `Domain=example.com` có thể mở rộng phạm vi đến các subdomain hợp lệ, nhưng không nên đặt rộng hơn mức cần thiết.

Cookie `Path=/app` không tự gửi vào `/api/me`; nếu reverse proxy thay context path hoặc không đồng bộ `Set-Cookie Path`, request có thể thiếu cookie. Port không thuộc phạm vi cookie, **nhưng có ảnh hưởng tới origin/CORS**.

### Secure

Cookie `Secure` chỉ được gửi qua kết nối an toàn theo quy tắc browser; một số trình duyệt có ngoại lệ `localhost` nhưng production không được phụ thuộc vào đó. Nếu trang login dùng HTTPS còn API dùng HTTP, cookie session có thể không được gửi. **Dùng HTTPS nhất quán và cấu hình proxy đúng** thay vì tắt `Secure` trên production.

### HttpOnly

`HttpOnly` che cookie khỏi JavaScript thông thường (`document.cookie`), không ngăn browser tự gửi cookie trong HTTP request đủ điều kiện. Vì vậy “không thấy JSESSIONID trong document.cookie” **không có nghĩa cookie biến mất**. Xem DevTools Storage/Network, đừng tắt `HttpOnly`.

### SameSite

- `Strict`: giới hạn cookie với nhiều request cross-site.
- `Lax`: thường phù hợp ứng dụng web điều hướng thông thường; cross-site `fetch` POST hoặc subresource có thể không mang cookie.
- `None`: cho phép trường hợp cross-site theo chính sách browser, nhưng cần `Secure`; third-party cookie blocking/partitioning vẫn có thể ảnh hưởng.

**Same-site không đồng nghĩa same-origin.** `https://app.example.com` và `https://api.example.com` có thể cùng site nhưng vẫn là hai origins khác nhau; `http://localhost:3000` và `http://localhost:8080` khác origin do port.

### Max-Age/Expires so với session timeout

Cookie có `Max-Age` hoặc `Expires` có thể bị browser xóa theo thời hạn. Session cookie không đặt thời hạn rõ ràng thường phụ thuộc vòng đời trình duyệt (một số browser có session restore). **Session timeout server** là thông số khác: cookie có thể còn khi server đã xóa phiên. Logout, chính sách giới hạn phiên đồng thời hoặc sự kiện invalidate cũng có thể kết thúc session.

## 6. SPA, CORS và credentials: cookie có nhưng request API không gửi

Ví dụ frontend ở `https://web.example.com`, backend ở `https://api.example.com`. Vì hai địa chỉ **khác origin**, request browser cần được xử lý cả về `fetch`, CORS và cookie:

~~~javascript
// Chạy ở frontend, không phải một chương trình Java độc lập.
const response = await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});
~~~

Các điều kiện độc lập:

1. `credentials: "include"` giúp gửi cookie trong request cross-origin khi cookie được phép.
2. Server phải trả CORS headers phù hợp: origin **cụ thể** và `Access-Control-Allow-Credentials: true` khi cho phép gửi credentials. `Access-Control-Allow-Origin: *` không hợp lệ cho credentialed response.
3. Cookie phải khớp Domain/Path/Secure/SameSite và không bị chính sách browser chặn.
4. Backend phải còn session/context hợp lệ.

Nếu API trả cookie `SameSite=None` nhưng thiếu `Secure`, browser có thể từ chối lưu. Nếu frontend `fetch("/api/me")` trên `web.example.com` mà không có proxy tương ứng, nó gửi request tới **web**, không phải **api**. Kiểm tra Request URL thực trước khi thay backend.

**CORS không phải biện pháp chống CSRF.** Cookie browser có thể được gửi tự động trên request trong các tình huống tấn công; endpoint thay đổi trạng thái cần CSRF protection hoặc một thiết kế khác đã đánh giá rủi ro.

## 7. Spring Security 6: ai lưu và ai tải SecurityContext?

Có ba vai trò:

- `SecurityContextHolder`: context đang được dùng trong request hiện tại, thường `ThreadLocal`.
- `SecurityContextRepository`: cơ chế lưu/tải context.
- `Authentication`: principal và authorities đã được xác thực, đặt trong `SecurityContext`.

Các implementation chính:

| Repository | Công dụng | Có giúp nhớ login đa request không? |
|---|---|---|
| `HttpSessionSecurityContextRepository` | Liên kết context với `HttpSession` | **Có**, nếu session còn và client gửi đúng cookie |
| `RequestAttributeSecurityContextRepository` | Duy trì context qua các dispatch trong **cùng request**, ví dụ error dispatch | **Không** cho request HTTP độc lập sau |
| `DelegatingSecurityContextRepository` | Ủy thác load/save tới nhiều repository; thường kết hợp hai loại trên | **Có** nếu bao gồm repository lưu session |
| `NullSecurityContextRepository` | Không lưu context | **Không**, dùng khi muốn stateless |

Spring Security 6 mặc định dùng một `DelegatingSecurityContextRepository` kết hợp request-attribute và HTTP session trong cấu hình Servlet thông thường.

### SecurityContextHolderFilter và explicit save

`SecurityContextHolderFilter` **nạp context** nhưng **không tự lưu** nó lúc request kết thúc. Nếu tự viết filter/controller login, không được giả định chỉ gọi `SecurityContextHolder.setContext(...)` sẽ tạo phiên đăng nhập lâu dài. Một cơ chế trước đây như `SecurityContextPersistenceFilter` có thể tự phát hiện/lưu context vào cuối request; không suy ra ứng dụng Spring Security 6 của bạn vẫn hoạt động theo cách đó.

Mã minh họa cho custom session authentication:

~~~java
// Mảnh code: cần AuthenticationManager, repository và Servlet request/response.
// "candidate" là Authentication CHƯA xác thực lấy từ input của client.
Authentication verified = authenticationManager.authenticate(candidate);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// Lưu trước khi gửi redirect/commit response.
securityContextRepository.saveContext(context, request, response);
response.sendRedirect("/dashboard");
~~~

Đây **không phải class độc lập**. Custom login production còn phải xử lý `SessionAuthenticationStrategy`/session fixation, CSRF, success/failure, remember-me nếu có, và phải dùng cùng repository với filter chain của request sau. Nếu chỉ cần form login tiêu chuẩn, dùng **Spring Security built-in `formLogin()`** thay vì tự triển khai cơ chế này.

### SessionCreationPolicy

| Chính sách | Hành vi chính |
|---|---|
| `ALWAYS` | Spring Security chủ động tạo `HttpSession` |
| `IF_REQUIRED` | Spring Security tạo session khi thực sự cần, phù hợp session login |
| `NEVER` | Không tự tạo, nhưng có thể dùng session có sẵn |
| `STATELESS` | Không tạo hoặc sử dụng session để lấy `SecurityContext` cho Spring Security |

`STATELESS` không đồng nghĩa “không thể có JSESSIONID trong mọi trường hợp”; thư viện/code servlet khác vẫn có thể tạo session. Nhưng nó không đáp ứng yêu cầu “lần request sau tự khôi phục Authentication từ session” của form login truyền thống.

Nếu auth mechanism là JWT/HTTP Basic stateless, việc xây lại Authentication ở mỗi request là **bình thường**. Đừng ép lưu session khi sản phẩm không yêu cầu.

## 8. Ví dụ Java 17 chạy được: formLogin và endpoint kiểm tra danh tính

Mục tiêu: tạo một baseline **có thể chạy** để so sánh với ứng dụng lỗi. Spring Security tự xử lý form login, chống session fixation và lưu context; chúng ta tạo `GET /api/me` yêu cầu login và `GET /api/csrf` cho curl lấy CSRF token.

Cấu trúc:

~~~text
session-debug-demo/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/sessiondebug/
│   ├── SessionDebugApplication.java
│   ├── SecurityConfig.java
│   └── DiagnosticController.java
└── src/test/java/com/example/sessiondebug/
    └── SessionLoginTest.java
~~~

**Yêu cầu:** JDK 17+, Maven 3.9+, internet hoặc dependency Maven được cache. Password `pw` và `{noop}` **chỉ để học trên localhost**, tuyệt đối không dùng production.

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>session-debug-demo</artifactId>
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
~~~

### 8.2. application.properties

~~~properties
server.servlet.session.timeout=15m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
spring.main.banner-mode=off
~~~

Demo chạy `http://localhost:8080`, nên **không ép `Secure=true` trên localhost** để dễ kiểm thử. Production cần HTTPS, cookie `Secure` và cấu hình reverse proxy/forwarded headers đáng tin. `15m` chỉ là giá trị học tập, không tự là policy đúng cho mọi hệ thống.

### 8.3. SessionDebugApplication.java

~~~java
package com.example.sessiondebug;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDebugApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDebugApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig.java

~~~java
package com.example.sessiondebug;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SecurityContextRepository repository)
            throws Exception {
        http
            .securityContext(ctx -> ctx
                .securityContextRepository(repository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyRequest().denyAll())
            .formLogin(form -> form.permitAll())
            .exceptionHandling(errors -> errors
                .defaultAuthenticationEntryPointFor(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED),
                    new AntPathRequestMatcher("/api/**")));
        // Mặc định vẫn bật CSRF.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}pw")
                .roles("USER")
                .build()
        );
    }
}
~~~

**Giải thích:** `IF_REQUIRED` cho phép session; `HttpSessionSecurityContextRepository` lưu context nhất quán; `formLogin` built-in xử lý `POST /login`; `GET /api/csrf` cho curl lấy token cùng phiên; `GET /api/me` là endpoint bảo vệ. `HttpStatusEntryPoint` khiến API chưa đăng nhập trả `401` thay vì redirect HTML. `formLogin().permitAll()` chủ động cho phép các URL login mặc định; các URL khác ngoài allowlist bị denyAll. CSRF vẫn bật cho POST.

`AntPathRequestMatcher` có thể được cảnh báo deprecated ở những phiên bản Spring Security mới hơn; đoạn này nhắm Spring Security 6.x của project. Không nên sao chép nguyên bản sang Spring Security 7 mà không kiểm API tương ứng.

### 8.5. DiagnosticController.java

~~~java
package com.example.sessiondebug;

import java.util.List;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiagnosticController {

    @GetMapping("/api/csrf")
    public CsrfView csrf(HttpServletRequest request) {
        CsrfToken csrf = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        // Kích hoạt việc truy hồi/tạo token khi CSRF được deferred.
        return new CsrfView(csrf.getParameterName(), csrf.getToken());
    }

    @GetMapping("/api/me")
    public UserView me(Authentication authentication) {
        List<String> roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
        return new UserView(authentication.getName(), roles);
    }

    public record CsrfView(String parameterName, String token) {}
    public record UserView(String name, List<String> roles) {}
}
~~~

Endpoint CSRF là tiện ích **chỉ để minh họa** trong demo, không phải API public mà mọi ứng dụng production nên mở. CSRF token cần được trả theo chính sách same-origin/CORS của app; không log token. Endpoint `/api/me` không trả session ID, credentials hoặc dữ liệu nhạy cảm.

### 8.6. SessionLoginTest.java

~~~java
package com.example.sessiondebug;

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
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionLoginTest {
    @Autowired MockMvc mvc;

    @Test
    void loginPersistsAuthenticationForNextRequest() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "pw"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.roles[0]").value("ROLE_USER"));

        // Không gửi session vừa đăng nhập: request mới phải là anonymous.
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfCannotSubmitLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "pw"))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfTokenCanBeRetrievedBeforeLogin() throws Exception {
        mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.parameterName").value("_csrf"))
            .andExpect(jsonPath("$.token").isNotEmpty());
    }

    @Test
    void unauthenticatedApiIs401() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Test đầu tiên phân biệt **thành công trong request login** và **danh tính vẫn tồn tại ở request kế tiếp**, bằng cách gửi cùng `MockHttpSession`. Test không mang session xác nhận endpoint bảo vệ trả 401. Test CSRF chỉ ra 403 trên POST không đồng nghĩa cookie đã mất.

`MockMvc` kiểm servlet filter chain và session giả lập trong Spring Test nhưng **không mô phỏng chính xác chính sách cookie của browser**, CORS, proxy và multi-node. Phải bổ sung kiểm thử HTTP/browser thực tế cho các vấn đề đó.

## 9. Chạy ví dụ và tái hiện lỗi bằng curl cookie jar

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

`mvn test` kiểm thử, `mvn spring-boot:run` mở server ở `http://localhost:8080` nếu port chưa bị chiếm. Kết quả chạy thật tùy dependency/môi trường; không coi đoạn tài liệu này là báo cáo đã build.

**Bước A — request không có cookie:**

~~~bash
curl -i http://localhost:8080/api/me
~~~

Kỳ vọng status `401`.

**Bước B — lấy CSRF token, đồng thời giữ session cookie.** Với bash và `jq` đã cài:

~~~bash
csrf=$(curl -fsS -c cookies.txt \
    http://localhost:8080/api/csrf | jq -r '.token')
test -n "$csrf" && echo "CSRF token received"
~~~

Kỳ vọng stdout: `CSRF token received`. `-c cookies.txt` lưu cookie của session gắn token. Không in token thật lên log.

**Bước C — POST login với cùng session, lưu cookie mới nếu ID bị đổi:**

~~~bash
curl -i -b cookies.txt -c cookies.txt \
    --data-urlencode "username=alice" \
    --data-urlencode "password=pw" \
    --data-urlencode "_csrf=$csrf" \
    http://localhost:8080/login
~~~

Kỳ vọng login hợp lệ trả `302` tới trang kế tiếp. `-b` gửi cookie hiện tại và `-c` lưu cookie server thiết lập sau đăng nhập. Đừng bỏ `-c` khi session ID có thể được đổi nhằm chống session fixation.

**Bước D — so sánh request có và không có cookie:**

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
curl -i http://localhost:8080/api/me
~~~

Lệnh đầu kỳ vọng `200` với dữ liệu (thứ tự field JSON không bắt buộc):

~~~json
{"name":"alice","roles":["ROLE_USER"]}
~~~

Lệnh thứ hai kỳ vọng `401`. Đây là phép thử đơn giản để chứng minh vấn đề có nằm ở việc **truyền cookie** hay không.

**Thử cố tình tạo lỗi trong môi trường học tập:** không gửi `-b` ở request sau; không lưu `-c` sau login; đợi hết timeout 15 phút không hoạt động; restart app khi session chỉ ở memory; thay cấu hình stateful bằng STATELESS ở môi trường thử riêng. Mỗi trường hợp có thể dẫn đến 401 nhưng có root cause khác nhau.

File `cookies.txt` chứa credential phiên; không commit/chia sẻ, giữ quyền đọc chặt chẽ và xóa sau khi thử. Ví dụ password `pw` chỉ dùng ở localhost.

## 10. Custom login quên saveContext: triệu chứng và cách sửa

Mã hay gây lỗi:

~~~java
// SAI khi muốn nhớ phiên giữa các request:
Authentication verified = authenticationManager.authenticate(candidate);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
response.sendRedirect("/dashboard");
// Thiếu saveContext: request kế tiếp có thể anonymous.
~~~

Hợp đồng đúng với explicit save:

~~~java
// Minh họa: chưa phải class độc lập để copy chạy.
Authentication verified = authenticationManager.authenticate(candidate);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
response.sendRedirect("/dashboard");
~~~

Cần save trước khi commit response và dùng repository mà filter chain **request sau** sẽ tải. Đoạn snippet không thay thế toàn bộ authentication filter; production còn cần `SessionAuthenticationStrategy` (chống session fixation), xử lý CSRF, event, remember-me, failure/success, rate limiting và cleanup. Với form login thông thường, ưu tiên cơ chế có sẵn của Spring Security.

Dùng breakpoint hoặc log có kiểm soát:

~~~text
POST /login:
  authenticate(candidate) -> thành công?
  SecurityContextHolder -> có Authentication đáng tin?
  saveContext(...) -> có được gọi?
  HttpSession -> tồn tại?
  Response -> redirect và session cookie hiện hành?

GET /api/me:
  Cookie -> gửi đúng không?
  getSession(false) -> tồn tại?
  SecurityContextRepository -> load được context không?
  SecurityContextHolder -> principal/authorities đúng?
  Authorization/CSRF -> loại nào từ chối?
~~~

Nếu cookie **không đến server**, sửa context không giúp. Nếu cookie đến, session còn nhưng context không được khôi phục, đây là nhánh kiểm tra `saveContext` và repository.

## 11. Đọc đúng cấu hình và sự kiện session

### SessionCreationPolicy và filter chains

`SessionCreationPolicy.STATELESS` không phù hợp nếu sản phẩm yêu cầu form-login session được dùng lại. `NullSecurityContextRepository` làm context không được lưu. `RequestAttributeSecurityContextRepository` chỉ phục vụ trong một request và các dispatch của request đó, không phải session persistence.

Với nhiều `SecurityFilterChain`, chain login `/auth/**` và chain API `/api/**` có thể dùng repository/policy khác nhau. Kiểm tra cả **`securityMatcher`, thứ tự chain, `securityContextRepository`, `SessionCreationPolicy`** của hai request. Đừng mặc định repository trong chain login cũng áp dụng cho chain API.

### Logout, timeout, concurrent sessions

Cookie vẫn gửi nhưng session có thể đã bị `invalidate()` bởi logout, timeout, đổi mật khẩu, chính sách maximum sessions hoặc cơ chế revoke. Tìm audit event tương ứng. Spring Security thường thay session ID sau login để phòng session fixation — **đổi ID không phải lỗi**, nhưng curl/browser phải lưu ID mới.

### Async và thread khác

Nếu chỉ công việc chạy bằng `@Async`/executor báo không có `SecurityContextHolder` trong khi HTTP vẫn login được, đó là vấn đề **propagation qua thread**, không hẳn session. Dùng integration chuyên dụng như `DelegatingSecurityContextExecutor` hoặc cơ chế async đúng với dự án; không bật `MODE_GLOBAL` trong server đa người dùng.

### Stateful khác stateless

- **Form login/browser:** thường lưu Authentication trong session.
- **HTTP Basic:** credentials gửi lại mỗi request.
- **Resource Server Bearer/JWT:** thường xác minh token ở từng request, không phải ghi login vào HttpSession.
- **OAuth2 Login/OIDC client:** có thể sử dụng session cho login flow và browser session sau callback; debug thêm `state`, cookie qua redirect, code exchange và repository.

Chỉ sửa “không nhớ login” khi kiến trúc thật sự yêu cầu **lưu Authentication giữa requests**.

## 12. Proxy, load balancer và session store

### HTTPS termination / forwarded headers

Client có thể truy cập `https://app.example.com` nhưng proxy gửi HTTP tới backend. Nếu server không nhận đúng scheme/host công khai, `Location`, cookie `Secure` và callback URL có thể sai. Kiểm tra `Forwarded`/`X-Forwarded-Proto` tại **proxy tin cậy**, cấu hình `server.forward-headers-strategy` khi thích hợp và việc rewrite `Set-Cookie Path/Domain`.

Không tin header `X-Forwarded-*` từ client Internet một cách trực tiếp: proxy cần lọc/ghi đè tại trust boundary.

### Hai node không chia sẻ session

~~~text
POST /login -> instance A: JSESSIONID được tạo ở A
GET /api/me -> instance B: cookie đúng, nhưng B không có session
Kết quả: anonymous / 401 dù browser đã gửi cookie.
~~~

Dấu hiệu thường là lỗi ngẫu nhiên theo load balancer, sau deploy/rollout hoặc khi autoscale. Kiểm tra instance ID, session lookup hit/miss, TTL và session store. Với ứng dụng cần session lâu dài nhiều node, cân nhắc **Spring Session + Redis/JDBC** hoặc chiến lược hạ tầng phù hợp. Sticky session có thể giúp affinity nhưng không thay thế shared store nếu node bị restart.

Nếu dùng Spring Session, kiểm tra namespace/TTL, serialization, phiên bản class, cache eviction và kết nối Redis/DB. Không dump object `Authentication` chứa dữ liệu nhạy cảm vào log.

### Cookie đúng mà vẫn 403

Nếu `GET /api/me` trả 200 nhưng `POST /api/transfer` trả 403, nguyên nhân có thể là CSRF hoặc authorization, không phải session. So phương thức/đường dẫn/CSRF token và authorities trước khi sửa cookie.

## 13. Observability an toàn và bảng quyết định

Các trường log có giá trị:

| Nên ghi | Không ghi |
|---|---|
| Correlation ID, route pattern, method/status, instance ID | Raw `Cookie`/`Set-Cookie` và session ID |
| `hasSessionCookie`, `getSession(false) != null` | Password, Authorization Basic/Bearer, refresh token |
| `contextLoaded`, `authenticated` (cờ boolean) | `SecurityContext` nguyên bản hoặc credentials |
| Authentication success/failure type | CSRF token, authorization code OAuth |
| Cookie attribute policy và session timeout config | Request body login và bí mật trong query string |

Khi quan sát server, dùng `request.getSession(false)` để tránh **tạo session mới chỉ bằng việc debug**. Có thể bật tạm:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Chỉ bật trong môi trường an toàn, thời gian ngắn và không tự động log toàn bộ headers. Bật TRACE hoặc dump credentials trên production là nguy cơ rò dữ liệu.

Ví dụ bảng so sánh hai request sau khi đã ẩn danh:

~~~text
                    POST /login       GET /api/me
Instance            node-A            node-B
Cookie đến server   yes               yes
Session tìm thấy    yes               no
Context active      yes               no
HTTP status         302               401

Nhánh ưu tiên: session store / routing giữa hai node.
Chưa có bằng chứng browser làm mất cookie.
~~~

Tương tự, nếu session tìm thấy ở cả hai request nhưng context load bị null ở GET, nhánh ưu tiên là `saveContext` hoặc repository/chain selection, không phải Domain/SameSite cookie.

## 14. Cây quyết định gỡ lỗi

~~~mermaid
flowchart TD
    A["Request sau login bị coi là anonymous"] --> B{"Login thực sự xác thực thành công?"}
    B -->|"Không"| X["Authentication provider / credentials / failure handler"]
    B -->|"Có"| C{"Request sau có cookie session đúng?"}
    C -->|"Không"| D["Set-Cookie, SameSite, Secure, Domain/Path, CORS, credentials"]
    C -->|"Có"| E{"Server tìm được HttpSession?"}
    E -->|"Không"| F["Timeout, logout/invalidate, restart, LB node, shared store"]
    E -->|"Có"| G{"SecurityContextRepository tải được Authentication?"}
    G -->|"Không"| H["saveContext, Null repository, STATELESS, chain khác"]
    G -->|"Có"| I{"Principal và authorities đúng?"}
    I -->|"Không"| J["Context bị thay, logout/revoke, identity"]
    I -->|"Có"| K["Kiểm authorization/CSRF; chưa chứng minh mất login"]
~~~

**Chỉ sửa đúng nhánh:**

1. Cookie không gửi → xác minh cấu hình browser/cookie, domain/path, HTTPS/Secure, SameSite và frontend credentials/CORS.
2. Session không còn → xác minh thời gian timeout, logout, node routing, shared session store, ID mới sau login.
3. Context không load → xác minh `SecurityContextRepository`, explicit `saveContext`, session policy và nhiều filter chains.
4. Context load đúng nhưng request bị từ chối → kiểm role/permission/CSRF.
5. Stateless token-based login → yêu cầu client gửi token mỗi request, không cần cố lưu session.

## 15. Test plan sau khi sửa

| Trường hợp | Bằng chứng đạt |
|---|---|
| Login với CSRF và cookie đúng | Login thành công; response/header hợp đồng hợp lệ |
| Request kế tiếp có cookie mới nhất | `/api/me` trả đúng principal |
| Không gửi cookie | Không có identity, `401` trong demo |
| Session khác của người dùng khác | Không lẫn principal |
| Cookie cũ sau logout | Không khôi phục Authentication đã logout |
| Session hết hạn server | Client phải đăng nhập lại dù cookie có thể còn |
| Session ID đổi sau login | Cookie jar cập nhật ID mới, session vẫn hoạt động |
| POST thiếu/sai CSRF | Bị từ chối; không vì thế kết luận session mất |
| Request qua hai instance | Identity khôi phục nếu ứng dụng yêu cầu shared session |
| Browser/API khác origin | Cookie/CORS được kiểm bằng browser thật |
| HTTPS và reverse proxy | Không bị chuyển về HTTP, cookie Secure đúng |
| API stateless | Bearer/Basic được xác minh từng request; không cần session |

**An toàn sau sửa:** logout phải làm hết hiệu lực phiên; session hết hạn không tiếp tục cấp quyền; Alice không thành Bob; 403 của API thiếu quyền vẫn phải đúng. Không được “chữa mất login” bằng cách giữ phiên vô hạn, bỏ HTTPS/CSRF hoặc nới quyền endpoint.

## 16. Lỗi suy luận phổ biến và câu hỏi tự kiểm tra

- **“Có JSESSIONID tức đã login.”** Sai: session có thể được tạo trước login để lưu CSRF.
- **“Không thấy cookie trong document.cookie tức bị mất.”** Sai: `HttpOnly` giấu nó khỏi JavaScript.
- **“Login trả 302 tức đã lưu SecurityContext.”** Chưa đủ: cần request sau khôi phục context.
- **“Đổi session ID là bug.”** Không nhất thiết: đó có thể là session fixation protection.
- **“Có 403 tức mất Authentication.”** Không nhất thiết: CSRF/role có thể từ chối.
- **“Tắt CSRF để sửa login.”** Có thể mở lỗ hổng; hãy gửi token đúng.
- **“STATELESS vẫn tự nhớ login bằng session.”** Không phù hợp với ý nghĩa của policy.
- **“Chỉ gọi setContext là đủ cho mọi request.”** Không đúng với cơ chế explicit-save.
- **“Nếu một node chạy được thì cả cụm đều chạy được.”** Shared session/routing cần kiểm chứng.
- **“Mở CORS * là sẽ hết mất cookie.”** Credentialed responses không thể dùng wildcard origin, và cookie vẫn chịu browser policy.
- **“Bật TRACE rồi in Cookie để điều tra.”** Dễ lộ credential phiên; dùng correlation có kiểm soát.

Tự trả lời:

1. Nếu `POST /login` trả 302 và `GET /api/me` trả 401, tại sao phải xem `Cookie` ở request thứ hai trước?
2. Cookie vẫn đến server nhưng `getSession(false)==null`: những nguyên nhân nào thuộc session store?
3. Nếu session tồn tại, repository không tải được context, bạn đặt breakpoint/log ở đâu trong custom authentication?
4. Vì sao `RequestAttributeSecurityContextRepository` không thay thế `HttpSessionSecurityContextRepository` cho request độc lập?
5. Phân biệt `SessionCreationPolicy.IF_REQUIRED` và `STATELESS`.
6. Vì sao browser cross-origin cần cả `fetch(credentials:"include")`, CORS phù hợp và cookie hợp lệ?
7. Một request 403 do CSRF khác gì 401 do anonymous?
8. Test MockMvc xác nhận session persistence như thế nào, và tại sao vẫn cần kiểm bằng browser/proxy?
9. Những bảo vệ nào phải giữ khi sửa cookie (Secure, HttpOnly, SameSite, CSRF, chống session fixation)?
10. Nếu hai node nhận cookie giống nhau nhưng một node không có session, giải pháp hạ tầng nào có thể phù hợp?

**Kết luận:** “Mất đăng nhập” cần điều tra theo một chuỗi nhân quả có thể đo được: **cookie được lưu/gửi → HttpSession được tìm thấy → SecurityContext được lưu/tải → Authentication được thiết lập → authorization/CSRF cho phép**. Ghi bằng chứng từ hai requests liên tiếp, phân biệt stateful với stateless, và chỉ sửa cơ chế thực sự gây lỗi.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Boot 3.5 — SameSite Session Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Session — Reference](https://docs.spring.io/spring-session/reference/)
- [MDN — HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
