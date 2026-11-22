# Endpoint đăng xuất tự viết và SecurityContextLogoutHandler

> **Module:** Spring Security - authentication. **Nhóm:** Đăng xuất. Bài học tập trung vào trường hợp **tự viết Spring MVC/REST endpoint logout** thay vì chỉ cấu hình `http.logout(...)`. Mục tiêu là hiểu chính xác vì sao phải gọi `SecurityContextLogoutHandler`, quan hệ với `SecurityContextHolder`/`SecurityContextRepository`/`HttpSession`, CSRF, quyền truy cập endpoint, các tác vụ mặc định bị bỏ qua khi tự viết và cách kiểm thử. Ví dụ dùng **Java 17, Spring Boot 3.3.5, Spring Security Servlet 6.x và Maven**.

## 1. Khi nào cần endpoint logout tự viết?

Spring Security Servlet đã có sẵn logout qua `LogoutFilter`. Với cấu hình web thông thường, `POST /logout` (khi CSRF bật thì phải có token hợp lệ) thực hiện các cleanup và chuyển hướng về `/login?logout`. Nếu chỉ cần đổi đường dẫn hoặc JSON/status response, nên tùy chỉnh **logout DSL**:

```java
// Trích đoạn DSL trong cấu hình HttpSecurity, không phải tệp Java độc lập.
http.logout(logout -> logout
    .logoutUrl("/api/auth/logout")
    .logoutSuccessHandler((request, response, authentication) -> {
        response.setStatus(204);
    })
);
```

Cách này giữ chuỗi `LogoutHandler` do Spring Security cấu hình: dọn session/context, CSRF, remember-me và những handlers bổ sung. **Đây thường là lựa chọn ưu tiên.**

Tuy nhiên, đôi lúc hệ thống có một API contract đặc thù, cần orchestration ở tầng controller, trả một object JSON riêng hoặc gắn logic nghiệp vụ thực sự vào request logout. Khi đó ứng dụng có thể tạo `@PostMapping("/api/auth/logout")`. Vì một Spring MVC controller được thực thi **sau** security filters, nó **không tự kế thừa** mọi xử lý của `LogoutFilter`. Chính controller phải gọi những thành phần cần thiết, tối thiểu là `SecurityContextLogoutHandler`.

**Chốt ý:** chỉ `return ResponseEntity.ok(...)` hoặc `SecurityContextHolder.clearContext()` không bảo đảm người dùng đã bị logout. Nếu `SecurityContext` vẫn nằm trong session/repository, request kế tiếp có thể khôi phục trạng thái xác thực cũ.

### 1.1. Ba cách thường gặp

| Cách làm | Ai bắt URL? | Ai dọn session/context? | Nên dùng khi |
| --- | --- | --- | --- |
| `http.logout(...).logoutUrl("/signout")` | `LogoutFilter` | Chuỗi handler của Spring Security | Hầu hết trường hợp; đơn giản, ít rủi ro |
| `http.logout(...).logoutSuccessHandler(...)` | `LogoutFilter` | Vẫn là các handler mặc định | Chỉ muốn JSON/HTTP status/redirect khác |
| `@PostMapping("/api/auth/logout")` | Spring MVC controller | **Do bạn chủ động gọi** `SecurityContextLogoutHandler` và những cleanup khác | Có yêu cầu thực sự phải dùng controller riêng |

Không khai báo đồng thời một `LogoutFilter` matcher và một `@PostMapping` **cùng URL** rồi kỳ vọng cả hai chạy: filter bắt request trước, nên MVC controller có thể không được gọi. Nếu cần cả hai cơ chế, đường dẫn phải khác hoặc việc xử lý phải được thiết kế lại rõ ràng.

## 2. Vị trí của custom endpoint trong filter chain

### 2.1. Logout mặc định

```text
Browser POST /logout (CSRF hợp lệ, cookie session)
   |
   v
CsrfFilter
   |
   v
LogoutFilter  <-- matcher nhận /logout
   |  - SecurityContextLogoutHandler
   |  - CsrfLogoutHandler
   |  - remember-me handler nếu có
   |  - logout success event handler
   |  - custom LogoutHandler nếu đã đăng ký
   v
LogoutSuccessHandler -> redirect /login?logout hoặc JSON/status
   |
   +-> Không chuyển vào Spring MVC controller logout
```

### 2.2. Endpoint Spring MVC tự viết

```text
Browser POST /api/auth/logout (CSRF hợp lệ, cookie session)
   |
   v
CsrfFilter
   |  - token không hợp lệ -> 403, không tới controller
   v
LogoutFilter
   |  - không match URL này -> bỏ qua
   v
AuthorizationFilter
   |  - route MVC này cần được explicitly permitAll()
   v
DispatcherServlet -> @PostMapping("/api/auth/logout")
   |
   |  - lấy Authentication hiện tại từ SecurityContext
   |  - gọi SecurityContextLogoutHandler.logout(request, response, auth)
   |        * invalidate HttpSession nếu có
   |        * xóa Authentication trong context
   |        * clear SecurityContextHolder
   |        * clear/save empty context vào SecurityContextRepository
   |  - gọi cleanup bổ sung nếu ứng dụng cần
   v
Controller trả 200 JSON hoặc 204
```

Điểm khác biệt: `LogoutFilter` không quản lý route do controller tự tạo. `AuthorizationFilter` vẫn xét route; vì vậy **phải cấu hình permitAll hoặc một rule tương ứng**. Tài liệu chính thức của Spring Security khuyên custom MVC logout route nên được permit tường minh; điều này giúp cả người dùng có session hết hạn hoặc chưa login vẫn dọn được trạng thái client liên quan. Dù route là `permitAll`, **`CsrfFilter` vẫn bảo vệ POST** nếu CSRF được bật; `permitAll` không đồng nghĩa bỏ CSRF.

**Không lẫn `permitAll` với vô hiệu hóa bảo mật:** đây là quyết định của tầng authorization. Request logout sử dụng cookie tự động gửi vẫn phải chịu kiểm tra CSRF, CORS/cookie scope và phương thức HTTP.

## 3. SecurityContextLogoutHandler thực sự làm gì?

Class `org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler` là một `LogoutHandler` của Spring Security Servlet. API quan trọng:

```java
// Chữ ký rút gọn để học API, không phải một class đầy đủ.
public void logout(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication);

public void setInvalidateHttpSession(boolean invalidate);
public void setClearAuthentication(boolean clear);
public void setSecurityContextRepository(SecurityContextRepository repository);
```

Hai boolean mặc định là `true`; mẫu mã thực tế ở mục 6 sẽ khai báo rõ để người học nhìn thấy. Khi được gọi, handler chịu trách nhiệm:

1. **Vô hiệu hóa HttpSession thực:** tìm phiên hiện hữu bằng `request.getSession(false)` và gọi invalidate khi được bật. Không nhất thiết tạo phiên mới chỉ để xóa.
2. **Làm sạch SecurityContext hiện tại:** xóa authentication hiện có và làm sạch `SecurityContextHolder`, tránh thread xử lý request vẫn giữ principal cũ.
3. **Làm sạch SecurityContextRepository:** ghi trạng thái rỗng phù hợp để request sau không nạp lại authentication đã lưu. `SecurityContextRepository` mới là tầng quyết định context sống qua request như thế nào.

Trong các ứng dụng Spring Security 6, việc lưu/đọc context có thể dùng `HttpSessionSecurityContextRepository`, `RequestAttributeSecurityContextRepository`, `DelegatingSecurityContextRepository` hoặc một implementation tùy chỉnh. Để bảo đảm cleanup đúng **cùng kho đang lưu**, code nên kết nối handler với repository thực mà security chain sử dụng — đặc biệt nếu bạn đã tự cấu hình repository.

### 3.1. Phân biệt holder, repository và session

| Khái niệm | Chứa gì | Khi logout cần gì |
| --- | --- | --- |
| `SecurityContextHolder` | Context của request/thread hiện tại (thường thread-local) | `clearContext()` sau logout |
| `SecurityContext` | `Authentication` và metadata liên quan | Không tiếp tục giữ principal đã logout |
| `SecurityContextRepository` | Cách khôi phục/lưu context giữa request | Dọn dữ liệu lưu, nếu không request sau có thể khôi phục login |
| `HttpSession` | State server của browser, thường liên hệ qua cookie `JSESSIONID` | `invalidate()` để session ID không còn dùng cho phiên cũ |
| Cookie `JSESSIONID` | ID mà browser trình để chỉ tới session | Xóa cookie trên browser khi thích hợp, **không thay thế** invalidation server-side |

**Ranh giới bảo mật:** logout không có nghĩa chỉ dọn Java thread-local. Một request thứ hai có cùng cookie session vẫn có thể đọc `SecurityContext` từ session nếu repository chưa được dọn.

### 3.2. Vì sao không gọi `getSession()` trước khi logout?

`request.getSession()` có thể **tạo session mới** khi chưa có. Khi xử lý logout, thường không nên sinh một session vô ích rồi invalidate nó. `SecurityContextLogoutHandler` tự xử lý session có sẵn. Nếu cần quan sát, chỉ dùng:

```java
// Mã minh họa bên trong controller/filter đã có request.
HttpSession existing = request.getSession(false);
boolean hadSession = existing != null;
```

Đừng lấy ID phiên rồi trả về JSON; session ID là credential cần bảo vệ. Người dùng không cần nhìn thấy raw ID để biết logout đã thành công.

### 3.3. Truyền `Authentication` nào?

Controller có thể nhận `Authentication authentication` do Spring MVC/Spring Security cung cấp. Giá trị này là context đã được security filters tải cho request, **không** phải một object do client tự gửi trong JSON. Người dùng chưa đăng nhập hoặc session đã timeout có thể làm `authentication == null`, và `SecurityContextLogoutHandler` **chấp nhận null**.

Không tạo handler theo tham số `userId` do request đưa vào rồi xóa session tùy tiện của user khác. Logout phiên hiện tại khác quản lý/revoke tất cả phiên thuộc một tài khoản; chức năng sau cần phân quyền quản trị riêng.

## 4. Tại sao chỉ xóa SecurityContextHolder là sai?

Hãy xem một controller **sai**:

```java
// Minh họa lỗi, không phải chương trình độc lập.
@PostMapping("/api/auth/logout")
ResponseEntity<String> badLogout() {
    SecurityContextHolder.clearContext();
    return ResponseEntity.ok("logged out");
}
```

Ở request đó, holder đã được dọn nhưng `HttpSession`/`SecurityContextRepository` có thể vẫn đang lưu `Authentication`. Request sau dùng `JSESSIONID` cũ, filter có thể nạp lại security context cũ. Ứng dụng trả 200 nhưng người dùng vẫn truy cập được tài nguyên bảo vệ.

Một lỗi khác:

```java
// Sai: chỉ yêu cầu browser xóa cookie; server-side session có thể vẫn hợp lệ.
response.addHeader("Set-Cookie", "JSESSIONID=; Max-Age=0; Path=/");
return ResponseEntity.noContent().build();
```

Nếu một attacker đã lấy được session ID cũ, việc xóa cookie trên một browser không làm session server mất hiệu lực. **Invalidation tại server** mới bảo vệ trường hợp đó. Cookie phải có Path/Domain tương ứng nếu muốn xóa chính xác.

Luồng đúng tối thiểu trong endpoint riêng:

```java
// Đoạn lõi; variables được cung cấp bởi controller có dependency phù hợp.
securityContextLogoutHandler.logout(request, response, authentication);
return ResponseEntity.ok(Map.of("message", "logged out"));
```

Trong Spring Security 6, `SecurityContextLogoutHandler` có `setSecurityContextRepository(...)`. Phần ví dụ đầy đủ sẽ cho cả security chain và handler dùng **một repository bean giống nhau**, tránh nhầm "filter lưu ở kho A, logout dọn ở kho B".

## 5. Điều gì endpoint tự viết KHÔNG tự động làm?

`SecurityContextLogoutHandler` đảm nhận cleanup context/session, nhưng **không tự động tái tạo toàn bộ chuỗi** của `LogoutFilter`. Một cấu hình logout tiêu chuẩn còn có thể dùng:

- `CsrfLogoutHandler`: xóa saved CSRF token.
- `TokenBasedRememberMeServices` hoặc `PersistentTokenBasedRememberMeServices`: xóa cookie remember-me và/hoặc trạng thái token tương ứng.
- `LogoutSuccessEventPublishingLogoutHandler`: phát `LogoutSuccessEvent` để listener xử lý.
- `CookieClearingLogoutHandler`: xóa cookie ứng dụng bổ sung.
- `HeaderWriterLogoutHandler` với `ClearSiteDataHeaderWriter`: yêu cầu browser xóa cache/storage/cookies theo directive phù hợp.
- Custom `LogoutHandler`: audit, hủy device session hoặc tác vụ riêng của sản phẩm.

**Trong demo ở mục 6:** dùng form login + `HttpSessionSecurityContextRepository` và **CSRF token mặc định lưu trong HTTP session**. Invalidate phiên sẽ dọn luôn state CSRF lưu trong session. Demo **không bật remember-me**, không có OAuth/OIDC, không dùng CSRF cookie repository, không cần một event listener nghiệp vụ. Do đó gọi `SecurityContextLogoutHandler` là đủ cho phạm vi session logout đã xác định, còn các chức năng khác phải bổ sung bằng chính sách rõ khi ứng dụng thực có chúng.

### 5.1. Nếu chuyển sang CookieCsrfTokenRepository

Lúc đó CSRF token có thể nằm trong cookie phía browser, không còn chỉ ở session. Invalidate `HttpSession` không tự đảm bảo cookie đó được xóa. Cần tích hợp `CsrfLogoutHandler` (với **chính CsrfTokenRepository** đã cấu hình) hoặc cơ chế cleanup tương đương. Đoạn dưới là **minh họa tại nơi có đầy đủ dependency**, không phải chương trình Java độc lập:

```java
CsrfLogoutHandler csrfCleanup = new CsrfLogoutHandler(csrfTokenRepository);
csrfCleanup.logout(request, response, authentication);
securityContextLogoutHandler.logout(request, response, authentication);
```

Chạy cleanup theo thứ tự và exception policy đã thiết kế; các handler phải hoạt động nhất quán với repository thực. Không xóa CSRF cookie bừa bãi mà bỏ qua yêu cầu token hợp lệ trên request đang đổi trạng thái.

### 5.2. Nếu bật remember-me

Cookie `remember-me` có thể tồn tại lâu hơn `JSESSIONID`. Nếu custom logout chỉ invalidate session, request sau vẫn có cookie nhớ đăng nhập và `RememberMeAuthenticationFilter` có thể tự khôi phục danh tính. Vì thế endpoint riêng phải gọi đúng cleanup của `RememberMeServices`/`LogoutHandler` tương ứng. Token-based remember-me có giới hạn thu hồi bản sao cookie bị đánh cắp; persistent token có repository giúp revoke theo thiết kế.

### 5.3. Nếu dùng JWT, refresh token, OAuth2 hoặc OIDC

`SecurityContextLogoutHandler` **không biến một JWT đã phát thành token hết hạn**, không thu hồi mọi OAuth2 refresh token và không logout khỏi identity provider. Với stateless JWT, mỗi request tự mang bearer credential; cần hành vi riêng như xóa token phía client, revocation/denylist/introspection, access token sống ngắn và thu hồi refresh token tại authorization server. Với OIDC SSO, local logout cũng không đồng nghĩa single logout phía IdP.

Không hứa "logout tất cả thiết bị" nếu chỉ có lệnh invalidate session hiện tại.

### 5.4. Nếu dùng nhiều server/session store phân tán

Một `HttpSession` được quản lý bởi Tomcat/Redis/JDBC/Spring Session tùy hạ tầng. Handler cần làm việc qua đúng session/repository/session store đang dùng. Chỉ xóa một map in-memory hoặc context holder ở pod hiện tại không đủ nếu session còn sống trong shared store hoặc JWT vẫn hợp lệ. Kiểm thử từ client thật qua load balancer là cần thiết.

## 6. Ví dụ chạy được: custom JSON logout endpoint + shared repository

### 6.1. Mục tiêu và phạm vi

Ứng dụng có một user demo `alice` với password `demo-pass123`. Spring Security xử lý `POST /login` bằng form login và lưu context vào session. Chúng ta chủ động định nghĩa `POST /api/auth/logout` bằng Spring MVC.

Các nguyên tắc thực hiện:

1. Bật CSRF mặc định. POST thiếu CSRF nhận **403** trước khi vào controller.
2. `/api/auth/logout` được `permitAll`, cho phép xử lý logout kể cả khi session đã hết hạn. Đây chỉ là quy tắc authorization; CSRF vẫn kiểm tra.
3. Dùng **cùng bean `HttpSessionSecurityContextRepository`** cho Spring Security chain và `SecurityContextLogoutHandler`.
4. `SecurityContextLogoutHandler` invalidate phiên, xóa authentication và context; controller trả JSON **sau** cleanup.
5. Tắt DSL logout mặc định **chỉ trong demo có chủ ý**, để không còn route `/logout` chạy song song. Vì vậy demo không tự thừa hưởng remember-me/CSRF-cookie/event cleanup của `LogoutFilter`; khi mở rộng app phải bổ sung chúng.
6. `GET /api/me` chỉ hoạt động khi đã đăng nhập; request mới sau logout không còn session thì chuyển về trang login.

Dự án chỉ chứa các tệp:

```text
custom-logout-demo/
├── pom.xml
├── src/main/java/com/example/customlogout/CustomLogoutApplication.java
└── src/test/java/com/example/customlogout/CustomLogoutApplicationTests.java
```

### 6.2. pom.xml

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
    <artifactId>custom-logout-demo</artifactId>
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

### 6.3. Java application

Tạo **`src/main/java/com/example/customlogout/CustomLogoutApplication.java`**:

```java
package com.example.customlogout;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@SpringBootApplication
public class CustomLogoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomLogoutApplication.class, args);
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

    // Cùng repository cho việc lưu context lúc login và dọn lúc logout.
    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityContextLogoutHandler customSecurityContextLogoutHandler(
            SecurityContextRepository repository) {
        SecurityContextLogoutHandler handler = new SecurityContextLogoutHandler();
        handler.setInvalidateHttpSession(true);
        handler.setClearAuthentication(true);
        handler.setSecurityContextRepository(repository);
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {

        http
            .securityContext(context -> context
                .securityContextRepository(repository)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/api/auth/logout", "/public")
                    .permitAll()
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/api/me", true)
            )
            // Chỉ trong demo: MVC endpoint tự quản lý cleanup.
            // Ứng dụng bình thường nên giữ LogoutFilter/DSL nếu có thể.
            .logout(AbstractHttpConfigurer::disable);

        // CSRF KHÔNG bị disable: POST /login và /api/auth/logout cần token.
        return http.build();
    }

    public record Identity(String username, boolean authenticated) {}

    @RestController
    static class AuthController {
        private final SecurityContextLogoutHandler logoutHandler;

        AuthController(SecurityContextLogoutHandler logoutHandler) {
            this.logoutHandler = logoutHandler;
        }

        @GetMapping("/public")
        String publicResource() {
            return "public";
        }

        @GetMapping("/api/me")
        Identity me(Authentication authentication) {
            return new Identity(authentication.getName(),
                    authentication.isAuthenticated());
        }

        @PostMapping("/api/auth/logout")
        ResponseEntity<Map<String, String>> logout(
                Authentication authentication,
                HttpServletRequest request,
                HttpServletResponse response) {

            // Không lấy userId, token hay trạng thái authenticated từ JSON.
            // Dùng Authentication do Spring Security đã tải cho request này.
            logoutHandler.logout(request, response, authentication);

            // Chỉ tạo response sau khi handler cleanup đã chạy.
            return ResponseEntity.ok(Map.of("message", "logged out"));
        }
    }
}
```

### 6.4. Phân tích mã chạy thật

**`SecurityContextRepository` là điểm trung tâm.** Trong ví dụ, `HttpSessionSecurityContextRepository` được tạo một lần và dùng cho cả:

- `http.securityContext(...securityContextRepository(repository))`: SecurityContext được load/save theo cơ chế session của chain.
- `handler.setSecurityContextRepository(repository)`: khi logout, handler biết chính xác kho nào cần dọn. Nếu app dùng custom repository, chỉ thay nhất quán cả hai điểm, không để chain đọc ở A nhưng controller xóa ở B.

**`formLogin(...)`** cung cấp `UsernamePasswordAuthenticationFilter` để xử lý password và lưu authenticated context sau login. Demo không tự xác minh password ở controller. Password BCrypt được tạo lúc startup để học; ứng dụng thật phải dùng database password hashes, cấu hình account lifecycle và không hardcode user.

**`permitAll("/api/auth/logout")`** bảo đảm MVC endpoint đi qua authorization layer. Để lại rule `anyRequest().denyAll()` ngăn những path ngoài demo bị truy cập ngoài ý định. `permitAll` không bỏ qua CSRF và không cho client tự đặt quyền.

**`logout(AbstractHttpConfigurer::disable)`** cố ý tắt `LogoutFilter` mặc định trong demo để route tự viết là **đường logout duy nhất**. Điều này chỉ chấp nhận được trong phạm vi giới hạn session login thuần. Khi bổ sung remember-me hoặc cơ chế khác, cần bổ sung cleanup của chúng hoặc chuyển về logout DSL; đừng copy dòng disable vào production rồi bỏ quên các tác vụ còn lại.

**Custom MVC controller** không trả `Authentication` hay session ID vào JSON; output là thông báo không chứa secret. `Authentication` có thể null nếu request đến từ anonymous client; `SecurityContextLogoutHandler` hỗ trợ trường hợp đó. Bài học không khuyến khích gọi `getSession()` tạo phiên mới khi logout.

**Session fixation và CSRF:** form login của Spring Security có các cơ chế bảo vệ session fixation tiêu chuẩn; CSRF mặc định dùng request token. Khi user logout, session invalidation khiến các thuộc tính trong session — bao gồm CSRF token session nếu dùng repository mặc định — không còn giá trị.

### 6.5. Tại sao vẫn cần gọi handler khi muốn trả 204 thay vì 200?

Việc đổi output không thay đổi trách nhiệm dọn state. Có thể thay hai dòng cuối endpoint bằng:

```java
// Trích đoạn controller, giữ nguyên lệnh logoutHandler.logout(...) phía trên.
return ResponseEntity.noContent().build();
```

Với mã này, chữ ký method ở controller phải điều chỉnh type trả về tương ứng (chẳng hạn `ResponseEntity<?>`). Không thay đổi behavior dọn security context/session vì cleanup xảy ra trước khi return.

## 7. Kiểm thử tự động bằng Spring Security MockMvc

Tạo **`src/test/java/com/example/customlogout/CustomLogoutApplicationTests.java`**:

```java
package com.example.customlogout;

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
class CustomLogoutApplicationTests {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass123"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void customMvcLogoutInvalidatesSessionAndReturnsJson() throws Exception {
        MockHttpSession session = login();

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authenticated").value(true));

        mvc.perform(post("/api/auth/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"message\":\"logged out\"}"));

        // Phiên do MockMvc tạo phải được invalidated server-side.
        assertTrue(session.isInvalid());

        // Không gửi session đã bị vô hiệu hóa vào request mới.
        mvc.perform(get("/api/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void csrfFailureCannotTriggerCustomLogout() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/api/auth/logout").session(session))
                .andExpect(status().isForbidden());

        // Không có valid CSRF -> controller không được chạy, session còn dùng.
        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));

        // Kết thúc phiên đúng cách trong test.
        mvc.perform(post("/api/auth/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().isOk());
        assertTrue(session.isInvalid());
    }

    @Test
    void anonymousLogoutIsHandledWithoutNullAuthenticationFailure()
            throws Exception {
        mvc.perform(post("/api/auth/logout").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"message\":\"logged out\"}"));
    }

    @Test
    void getDoesNotPerformLogout() throws Exception {
        MockHttpSession session = login();

        // Chỉ có @PostMapping, GET không phải hành động logout.
        mvc.perform(get("/api/auth/logout").session(session))
                .andExpect(status().isMethodNotAllowed());

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk());

        mvc.perform(post("/api/auth/logout").session(session).with(csrf()))
                .andExpect(status().isOk());
    }

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }
}
```

Chạy:

```bash
mvn test
```

Các kiểm thử xác nhận:
- **Dòng chảy thực:** form login → `SecurityContext` trong session → controller logout → invalidate `HttpSession` → request mới cần login.
- **CSRF:** không có token trên POST logout → 403, session đang login vẫn hợp lệ.
- **Anonymous:** controller không giả định `Authentication` luôn có giá trị.
- **HTTP method:** GET cùng URI không làm logout; đây là API nhận POST, không phải link GET có tác dụng đổi trạng thái.
- **Public endpoint:** không phải mọi route đều phải login; authorization được khai đúng scope.

**Giới hạn:** `MockMvc` test chạy trong môi trường servlet mô phỏng; đây là ví dụ để người học sao chép và chạy `mvn test`, **không phải khẳng định Maven đã được thực thi ở đây**. Trong môi trường thật còn cần E2E kiểm tra cookie path/domain, HTTPS, session store phân tán, revocation và các logout handlers bổ sung.

### 7.1. Vì sao không tái sử dụng MockHttpSession đã invalidated?

Sau lệnh logout, `MockHttpSession.isInvalid()` có thể là `true`. Truyền chính object đó bằng `.session(oldSession)` vào request khác có thể gây exception do giả lập một session không còn hợp lệ. Điều đó không phải bug của security handler. Để kiểm tra user đã logout, tạo request **mới không mang phiên đã xác thực**, hoặc dùng HTTP integration thực với cookie cũ và xác nhận container không khôi phục session.

### 7.2. Chỉ kiểm tra HTTP 200 là chưa đủ

Một test chỉ kỳ vọng JSON `{"message":"logged out"}` sẽ **pass cả khi controller không gọi cleanup**, khiến lỗ hổng còn tồn tại. Cần assert trực tiếp session invalidated và kiểm thử request mới không có session auth; với hệ thống thực, nên kiểm chứng **cookie/session ID cũ** không còn đem lại quyền truy cập.

## 8. Chạy thủ công và quan sát response

Khởi động:

```bash
mvn spring-boot:run
```

Trên trình duyệt:

1. Mở `http://localhost:8080/login` và đăng nhập bằng `alice` / `demo-pass123`. Trang login mặc định của Spring Security cung cấp CSRF token.
2. Sau login, `GET /api/me` trả JSON từ authenticated session.
3. Để gọi **custom REST logout**, frontend gửi `POST /api/auth/logout` kèm session cookie và CSRF token hợp lệ.
4. Khi thành công, server trả JSON và invalidate phiên. Truy cập lại `GET /api/me` bằng session đã hết hiệu lực sẽ bị yêu cầu đăng nhập.
5. Nếu thử `GET /api/auth/logout`, controller không thực hiện logout vì mapping chỉ nhận POST. Không dùng GET có tác dụng logout trong ứng dụng dựa trên browser cookie.

Response minh họa khi vẫn login:

```json
{"username":"alice","authenticated":true}
```

Khi logout hợp lệ:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"message":"logged out"}
```

Các header khác phụ thuộc container/proxy. Session cookie có thể vẫn xuất hiện ở browser cho tới khi được dọn về phía client, nhưng session ID đã bị server invalidate thì không còn trỏ tới phiên đăng nhập cũ.

### 8.1. Vì sao `curl -X POST` trả 403?

Lệnh không lưu cookie và không mang CSRF token:

```bash
curl -i -X POST http://localhost:8080/api/auth/logout
```

trong cấu hình demo thường nhận **403 Forbidden**. Đây là hành vi mong đợi do `CsrfFilter`, không có nghĩa controller bị lỗi. Để kiểm thử thủ công bằng HTTP client cần nhận cookie và CSRF token từ cùng phiên, rồi gửi POST có header/form token tương ứng. `MockMvc` dùng `.with(csrf())` để kiểm tra luồng này ổn định.

Không tắt CSRF chỉ để command curl dễ chạy trong ứng dụng browser-session. Nếu muốn API stateless bearer token không dùng cookie, đó là kiến trúc khác và cần đánh giá CSRF/cơ chế thu hồi credential riêng.

### 8.2. Fetch từ frontend SPA

Một SPA dùng session cookie phải đảm bảo gửi cookie (ví dụ `credentials: "include"` khi cross-origin được cho phép), token CSRF hợp lệ và chỉ xử lý thành công sau response server. **Minh họa**, không phải đoạn chạy độc lập vì `csrfTokenFromServer` phải lấy từ cơ chế cấp token của ứng dụng:

```javascript
const response = await fetch("/api/auth/logout", {
  method: "POST",
  credentials: "same-origin",
  headers: { "X-CSRF-TOKEN": csrfTokenFromServer }
});
if (!response.ok) {
  throw new Error("Logout failed");
}
window.location.assign("/login");
```

Nếu `CookieCsrfTokenRepository` hoặc SPA CSRF configuration dùng header khác, phải đặt đúng tên và nguồn token. Không lấy token tùy ý từ localStorage rồi giả định khớp với CSRF repo; thông số cụ thể thuộc cấu hình app.

## 9. Tình huống nâng cao và cách tránh lỗi thiết kế

### 9.1. Để nguyên LogoutFilter nhưng dùng một MVC route khác

Bạn có thể không disable mặc định `/logout`, đồng thời tạo MVC `/api/auth/logout` riêng. Hai route sẽ có thể tồn tại: `/logout` do `LogoutFilter` xử lý, còn `/api/auth/logout` do controller xử lý. **Mối nguy**: hành vi cleanup khác nhau; mặc định có remember-me/event/CSRF cleanup mà custom controller không gọi.

Nếu giữ hai route, cần kiểm thử chúng cho các cơ chế auth đang hỗ trợ. Không ngầm để "đường dễ dùng hơn" vô tình không revoke remember-me/token; khi không cần sự khác biệt, chuyển toàn bộ về logout DSL sẽ dễ bảo trì hơn.

### 9.2. Bỏ lệnh `setSecurityContextRepository`

`SecurityContextLogoutHandler` mặc định dùng `HttpSessionSecurityContextRepository`. Nếu chain cũng dùng repository HTTP session đơn giản, nó thường hoạt động. Tuy nhiên với một `DelegatingSecurityContextRepository` hoặc custom repository (Redis/DB/context propagation), hành động cleanup có thể không trùng đường lưu; cấu hình explicitly cùng repository tránh lệch. Sự tương thích repository và cơ chế lưu context cần được kiểm thử cho từng deployment.

### 9.3. `request.getSession().invalidate()` có đủ không?

Đó là hành động tác động session, nhưng thiếu các phần dọn holder/repository và handlers khác. Trong code tự viết, người dùng có thể nghĩ:

```java
// Minh họa lỗi: chưa tương đương toàn bộ SecurityContextLogoutHandler.
request.getSession().invalidate();
SecurityContextHolder.clearContext();
```

Nó còn **có thể tạo session mới** nếu chưa có. `SecurityContextLogoutHandler` dùng `getSession(false)` và dọn repository/context nhất quán hơn.

### 9.4. Logout của một thiết bị khác logout mọi thiết bị

Custom controller với `SecurityContextLogoutHandler` tác động **session của request hiện tại**. Nó không duyệt mọi session khác của user. Nếu sản phẩm yêu cầu "Đăng xuất mọi thiết bị", cần chính sách quản lý `SessionRegistry`/store, revoke session/token, kiểm tra identity, quyền và khả năng propagation trên nhiều node. `SessionInformation.expireNow()` chỉ đánh dấu expired và có thể cần request tiếp theo để được xử lý, không hủy tức thì mọi session trong container.

### 9.5. Session fixation và cookie path/domain

Sau login, Spring Security có cơ chế session fixation protection; session ID có thể đổi. Logout phải invalidate **session hiện tại**, không dựa trên ID lưu ở một biến bên ngoài. Khi browser giữ cookie cũ, server phải coi session ID đó không còn gắn với authentication; cookie-clearing để có UX tốt còn đòi match Path/Domain.

Không đưa `JSESSIONID` ra URL, query, logs hay JSON; cookie là một loại credential, ai có giá trị đó có thể thử chiếm phiên chưa bị hủy.

### 9.6. Race condition với các request đang chạy

Logout request A có thể xảy ra cùng lúc với request B đã nạp `SecurityContext` trước khi A invalidate session. `SecurityContextLogoutHandler` làm sạch state của A và session, **không nhất thiết dừng tức thì công việc B đang chạy**. Với nghiệp vụ đặc biệt nhạy cảm, dùng authorization/ownership checks ở điểm commit hoặc cơ chế token/session revocation tập trung với semantics rõ. Đừng hứa logout là hủy lập tức mọi HTTP request đồng thời.

### 9.7. Đăng xuất anonymous vẫn nên an toàn

Có thể cho client chưa login gửi POST logout **có CSRF hợp lệ**, controller gọi handler với `authentication == null`, rồi trả 200/204 idempotent. Điều đó giúp frontend dễ quản lý trạng thái khi session timeout nhưng UI vẫn hiện login. Không tạo session mới chỉ để logout và không tiết lộ rằng username nào đang tồn tại.

### 9.8. SSO, OAuth2/OIDC và chuyển hướng logout

Trong SSO, local logout không có nghĩa IdP đã kết thúc phiên. OIDC có luồng RP-initiated logout dành riêng cho nhà cung cấp hỗ trợ. Nếu cần logout khỏi IdP, một controller trả JSON đơn giản sẽ **không thay thế** redirect/protocol đúng. Đánh giá cả local cleanup lẫn IdP/logout callbacks, CSRF/state và redirect URI hợp lệ.

## 10. So sánh hai implementation phù hợp với cùng API contract

### Phương án A — ưu tiên trong sản phẩm

Khi chỉ cần `POST /api/auth/logout` và response JSON/status, cấu hình bằng DSL:

```java
// Đoạn cấu hình trong SecurityFilterChain.
http.logout(logout -> logout
    .logoutUrl("/api/auth/logout")
    .logoutSuccessHandler((request, response, authentication) -> {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("application/json");
        response.getWriter().write("{\"message\":\"logged out\"}");
    })
);
```

Ưu điểm: Spring Security lo các handlers mặc định, dễ bảo trì, ít thiếu cleanup khi bật remember-me. Nếu không có nghiệp vụ phải đặt trong controller, đây là cách nên chọn.

### Phương án B — endpoint tự viết vì có lý do rõ

Chính là `@PostMapping("/api/auth/logout")` ở mục 6, với các điều kiện:
- Tách route để không bị LogoutFilter chặn trước.
- Cho phép route ở `AuthorizationFilter` (thường `permitAll`).
- Bảo vệ POST bằng CSRF trong app cookie-based.
- Gọi đúng `SecurityContextLogoutHandler` với repository tương ứng.
- Bổ sung các cleanup khác tùy những cơ chế xác thực thực sự được bật.
- Test không chỉ response mà cả session invalidation/repository state và request sau.

**Không có "cách B lúc nào cũng linh hoạt hơn".** Nếu bạn cần thêm logic khi logout, có thể thêm `LogoutHandler` vào phương án A, vẫn giữ pipeline đầy đủ.

## 11. Checklist review bảo mật

- [ ] Có lý do rõ để viết MVC logout endpoint thay vì `http.logout()`.
- [ ] Dùng `POST`/method không an toàn với CSRF protection đúng trong web app dùng cookie; không logout bằng GET.
- [ ] Route custom có authorization rule tường minh; không nhầm `permitAll` với bypass CSRF.
- [ ] SecurityContextLogoutHandler được gọi ở controller, **trước khi trả thành công**.
- [ ] Handler dùng repository giống cấu hình `SecurityContextRepository` của chain.
- [ ] Session hiện có bị invalidate; không gọi `getSession()` tạo phiên mới chỉ để hủy.
- [ ] `SecurityContextHolder` và authentication trong repository được dọn, không chỉ xóa browser cookie.
- [ ] `authentication == null` được xử lý an toàn; không nhận principal từ client như bằng chứng.
- [ ] Đã xét CSRF token repo đặc thù, remember-me, logout events, cookies riêng và external token revocation nếu có.
- [ ] Không đưa `JSESSIONID`, auth cookie, CSRF token, JWT/refresh token vào response/log.
- [ ] Có test POST không CSRF trả 403 và không logout.
- [ ] Có test POST hợp lệ invalidate session và request mới cần login.
- [ ] GET cùng URI không đổi trạng thái đăng nhập.
- [ ] Multi-node/session store, race condition và SSO/IdP logout được kiểm thử theo đúng phạm vi yêu cầu.

## 12. Tự kiểm tra kiến thức

1. Vì sao Spring Security khuyến nghị logout DSL thay vì tự viết MVC controller?
2. Custom `@PostMapping` phải có rule `permitAll` trong trường hợp nào? Rule này có bỏ CSRF không?
3. Tại sao `SecurityContextHolder.clearContext()` **một mình** không phải logout hoàn chỉnh?
4. `SecurityContextLogoutHandler` tác động vào ba đối tượng/hệ thống state nào?
5. Tại sao nên dùng **cùng** `SecurityContextRepository` cho security chain và logout handler?
6. Khi `request.getSession(false) == null`, handler nên xử lý thế nào?
7. Trong demo, tại sao không cần cấu hình thêm xóa CSRF cookie? Khi nào cần?
8. Nếu user bật remember-me, điều gì xảy ra khi custom logout chỉ invalidate session?
9. Vì sao return HTTP 200 sau logout không chứng minh token JWT đã bị thu hồi?
10. `GET /api/auth/logout` có thực hiện logout trong demo không? Vì sao?
11. Vì sao test nên kiểm tra `session.isInvalid()` và hành vi request tiếp theo?
12. Khác biệt giữa custom MVC logout và custom `LogoutSuccessHandler` là gì?

**Gợi ý trả lời:** (1) DSL có sẵn pipeline cleanup; (2) controller chạy sau authorization, permitAll không tắt CSRF; (3) repository/session có thể giữ context cũ; (4) HttpSession, SecurityContextHolder và SecurityContextRepository; (5) tránh lưu ở kho A nhưng xóa kho B; (6) không tạo session vô ích, cho phép anonymous; (7) CSRF session token mất khi session invalidate, cookie repo cần handler riêng; (8) cookie nhớ đăng nhập có thể auto-login; (9) JWT còn validity độc lập; (10) không, chỉ PostMapping; (11) HTTP 200 có thể giả trong code lỗi; (12) custom handler đổi output còn controller phải tự dọn state.

## 13. Tài liệu chính thức

- Spring Security 6.5 — Handling Logouts, mục *Creating a Custom Logout Endpoint*: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security API — `SecurityContextLogoutHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html
- Spring Security API — `SecurityContextRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html
- Spring Security API — `LogoutHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/LogoutHandler.html
- Spring Security — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
- Spring Security — CSRF Protection (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — Remember-Me Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
