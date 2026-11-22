# Endpoint đăng xuất tự viết và sử dụng SecurityContextLogoutHandler trong Spring Security Servlet

## Mục tiêu học tập

Trong ứng dụng Spring Security Servlet dùng form login và HttpSession, **đăng xuất (logout)** không đơn giản là trả về HTTP 200 hay chuyển hướng về trang đăng nhập. Server cần chấm dứt trạng thái xác thực của phiên hiện tại, xử lý SecurityContext đúng cách và, tùy cấu hình, dọn dẹp CSRF token, remember-me token, cookie hoặc phát sự kiện logout.

Spring Security đã cung cấp **LogoutFilter** và cấu hình HttpSecurity.logout(...). Đây thường là cách nên dùng. Tuy nhiên đôi khi ứng dụng cần một **endpoint do chính MVC controller xử lý** để tích hợp nghiệp vụ hoặc hợp đồng HTTP riêng. Khi đó **SecurityContextLogoutHandler** là thành phần chủ chốt để xóa ngữ cảnh bảo mật và vô hiệu hóa HttpSession thích hợp, thay vì tự thao tác lẻ tẻ với SecurityContextHolder.

Sau bài học, bạn có thể:

1. Mô tả luồng logout mặc định của LogoutFilter, các LogoutHandler và LogoutSuccessHandler.
2. Phân biệt đổi URL logout bằng DSL với thật sự viết @PostMapping/@DeleteMapping trong MVC.
3. Biết chính xác SecurityContextLogoutHandler.logout(request, response, authentication) làm việc gì và không làm việc gì.
4. Viết endpoint POST /account/logout với SecurityContextLogoutHandler khi cần custom controller.
5. Giữ bảo vệ CSRF, không cho phép logout qua GET tùy tiện, kiểm tra quyền và session fixation.
6. Biết vì sao logout ở Servlet session **không đồng nghĩa** hủy JWT, revoke mọi thiết bị, xóa cookie trình duyệt ngay lập tức hay vô hiệu hóa request đang thực thi.
7. Viết và kiểm thử một ứng dụng Spring Boot 3.x / Spring Security 6.x / Java 17+ với MockMvc.
8. Chọn extension point phù hợp để thực hiện audit, xóa cookie, remember-me, token revocation hoặc xử lý response API.

Phạm vi: Spring Security **Servlet stack**, một ứng dụng stateful dùng HttpSession/formLogin. Những cơ chế OAuth2/OIDC, SAML, WebFlux hoặc JWT stateless có logout contract riêng, không thay thế bằng việc gọi một handler Servlet duy nhất.

## 1. Đăng xuất khác gì trả về một response?

Sau form login thành công, ứng dụng thường lưu Authentication trong SecurityContext và SecurityContext vào HttpSession thông qua SecurityContextRepository. Browser giữ session ID trong cookie (tên tùy cấu hình, như JSESSIONID hoặc SESSION).

Nếu người dùng chỉ nhấn một liên kết dẫn tới trang /logged-out rồi UI hiển thị “Đã đăng xuất”, phiên trên server **có thể vẫn còn hợp lệ**. Browser gửi lại session cookie ở request tiếp theo và Spring Security vẫn có thể khôi phục Authentication.

Hãy phân biệt:

| Hành động | Có phải logout thực sự? | Lưu ý |
| --- | --- | --- |
| Frontend ẩn nút đăng nhập | Không | Chỉ thay đổi giao diện |
| Trả HTTP 200 “logout ok” | Không chắc | Cần kiểm tra server-side session/security context |
| Xóa một biến JavaScript trên browser | Không chắc | HttpOnly session cookie thường không đọc được bằng JavaScript |
| Xóa cookie phía browser | Chưa đủ | Session server-side có thể vẫn tồn tại |
| HttpSession.invalidate() đơn lẻ | Một phần | Còn cần hiểu SecurityContext và các handler khác |
| SecurityContextHolder.clearContext() đơn lẻ | Một phần | Không chắc phiên cũ đã bị vô hiệu hóa hoặc context được lưu đúng |
| LogoutFilter chạy chuỗi LogoutHandler chuẩn | Có theo hợp đồng đã cấu hình | Hỗ trợ nhiều bước dọn dẹp và success response |
| Endpoint MVC tự gọi SecurityContextLogoutHandler | Có cho session hiện tại nếu tích hợp đúng | Các cleanup bổ sung phải tự xử lý theo yêu cầu |

Một lần logout đúng nên có kết quả quan sát được: **request mới tới tài nguyên cần xác thực không được dùng lại phiên vừa đăng xuất**. Nếu session vẫn còn hoặc một SecurityContext cũ được lưu lại sau request, giao diện logout chỉ là vỏ ngoài.

## 2. LogoutFilter và pipeline mặc định

Trong Servlet, Spring Security cung cấp LogoutFilter. Khi request khớp logout RequestMatcher, filter gọi các LogoutHandler đã đăng ký rồi trao quyền xử lý phản hồi cho LogoutSuccessHandler.

Một sơ đồ tổng quát:

~~~text
Browser: POST /logout + session cookie + CSRF token
    |
Servlet FilterChainProxy / SecurityFilterChain
    |
CsrfFilter kiểm tra token đối với POST được bảo vệ
    |
LogoutFilter: request có khớp logout matcher?
    |
    +-- không khớp -> các filter tiếp theo, MVC...
    |
    +-- khớp:
           |
           +-- LogoutHandler #1
           +-- LogoutHandler #2
           +-- SecurityContextLogoutHandler
           +-- các handler được cấu hình bổ sung
           |
           +-- LogoutSuccessHandler
                  |
                  +-- redirect hoặc HTTP response
~~~

Thứ tự và danh sách handler chính xác phụ thuộc cấu hình/phiên bản. Trong mô hình thông thường có việc xử lý SecurityContext và session; có thể có CSRF cleanup, remember-me cleanup và logout success event tùy điều kiện. Không tự khẳng định một handler cụ thể luôn chạy đúng một lần trong mọi thiết lập custom.

**LogoutFilter hoạt động trước AuthorizationFilter trong chuỗi thông thường.** Vì vậy nếu để filter xử lý đúng URL logout, request có thể được xử lý theo logic logout trước khi đến quyết định authorizeHttpRequests của controller. Trái lại, khi tự viết MVC endpoint và tắt LogoutFilter, URL đó phải nằm trong security chain phù hợp và được phân quyền theo chính sách ứng dụng.

### LogoutHandler so với LogoutSuccessHandler

- **LogoutHandler.logout(request, response, authentication):** thực hiện phần cleanup, ví dụ invalidate session, dọn remember-me token hoặc xóa cookie.
- **LogoutSuccessHandler.onLogoutSuccess(request, response, authentication):** chọn phản hồi sau khi cleanup: redirect, mã trạng thái, JSON, v.v.

Không dùng success handler đơn thuần để thay công đoạn cleanup: hiển thị 200/302 không có nghĩa Authentication đã bị loại bỏ. Ngược lại, LogoutHandler thường không chịu trách nhiệm chọn response cuối cùng.

Các logout handler mặc định được thiết kế cho các thao tác dọn dẹp. Nếu tự viết handler có khả năng ném exception, hãy cân nhắc cách ghi log, retry, transaction và ý nghĩa pháp lý của logout; không làm lộ credentials hoặc session IDs.

## 3. Ưu tiên cách đơn giản nhất: đổi URL bằng HttpSecurity.logout(...)

Nếu yêu cầu chỉ là: “Thay POST /logout thành POST /account/logout và sau đó chuyển người dùng về /logged-out”, **không cần viết @PostMapping**.

Trong cấu hình SecurityFilterChain:

~~~java
http.logout(logout -> logout
        .logoutUrl("/account/logout")
        .logoutSuccessUrl("/logged-out")
        .permitAll());
~~~

Đây là đoạn trích, sẽ được đặt trong file SecurityConfig đầy đủ khi áp dụng. Khi dùng hướng này:

1. LogoutFilter, **không phải MVC controller**, nhận request khớp đường dẫn logout.
2. Các LogoutHandler liên quan sẽ được gọi; bạn không cần tự new SecurityContextLogoutHandler.
3. LogoutSuccessHandler được cấu hình chuyển hướng về /logged-out.
4. Trang /logged-out phải truy cập được sau khi session bị vô hiệu hóa, ví dụ requestMatchers("/logged-out").permitAll().
5. Nếu CSRF đang bật, POST là phương thức logout phù hợp theo cấu hình thông thường; HTML form cần token CSRF hợp lệ.
6. **Không tạo một MVC @PostMapping cùng URL** rồi mong controller chạy trước: LogoutFilter có thể chặn request, xử lý logout và hoàn tất response ngay từ filter chain.

Một cấu hình ngắn (chỉ phần Spring Security DSL):

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/logged-out").permitAll()
        .anyRequest().authenticated());

http.formLogin(withDefaults());

http.logout(logout -> logout
        .logoutUrl("/account/logout")
        .logoutSuccessUrl("/logged-out")
        .permitAll());
~~~

Nếu cần JSON thay redirect sau logout, hãy xem LogoutSuccessHandler tùy biến hoặc logoutSuccessHandler của DSL. Đây vẫn là lựa chọn giữ pipeline chuẩn, thay vì lập tức viết controller logout và làm lại toàn bộ security lifecycle.

## 4. Khi nào thật sự cần endpoint MVC tự viết?

Một controller logout có thể có lý do chính đáng:

- Ứng dụng có hợp đồng URL/method/response đặc thù và muốn gom điều phối tại MVC.
- Cần kết hợp tác vụ nghiệp vụ với logout theo thứ tự rõ ràng, ví dụ ghi lại thao tác hủy phiên hoặc thông báo.
- Muốn triển khai một endpoint đã được thiết kế riêng từ hệ thống legacy, trong khi kiểm soát đầy đủ cấu hình filter và session.
- Muốn minh họa lifecycle logout bằng code thay vì chỉ nhìn DSL.

Nhưng nếu nhu cầu chỉ là đổi URL, xóa cookie hoặc phản hồi JSON, có thể dùng **logoutUrl, addLogoutHandler, deleteCookies, logoutSuccessHandler** của LogoutConfigurer mà không cần MVC endpoint.

Cần quyết định ai “sở hữu” request:

| Cách triển khai | Ai nhận POST /account/logout? | Ai gọi SecurityContextLogoutHandler? |
| --- | --- | --- |
| HttpSecurity.logout().logoutUrl("/account/logout") | LogoutFilter | Pipeline logout do Spring Security cấu hình |
| MVC @PostMapping("/account/logout") và logout filter không match URL | DispatcherServlet → controller | Controller phải chủ động gọi |
| Vừa cấu hình LogoutFilter match URL, vừa tạo @PostMapping cùng URL | Thông thường LogoutFilter xử lý trước | Controller có thể không bao giờ chạy |
| MVC controller chỉ return "redirect:/login" | Controller | Không có ai nếu bạn quên gọi logout handler |

Với mẫu MVC ở phần 6, chúng ta **vô hiệu hóa LogoutFilter mặc định** cho rõ ràng. Điều này có nghĩa ta đã tự nhận trách nhiệm cho những bước dọn dẹp khác vốn được logout DSL xử lý, nên ví dụ chỉ phù hợp học tập/ứng dụng có yêu cầu được kiểm chứng. Không dùng đồng thời cả hai phương án thay thế trong cùng một project mà chưa quyết định đường đi của request.

## 5. SecurityContextLogoutHandler: contract và tác động thực tế

Lớp SecurityContextLogoutHandler thuộc package org.springframework.security.web.authentication.logout. Nó triển khai LogoutHandler và có phương thức:

~~~java
void logout(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication);
~~~

Đây là chữ ký API minh họa, không phải một file Java độc lập. Khi gọi handler trong ứng dụng Servlet stateful:

- Theo cấu hình mặc định, handler **invalidate HttpSession hiện tại nếu có**, thông qua request.getSession(false) và session.invalidate().
- Nó **xóa Authentication khỏi SecurityContext và clear SecurityContextHolder** theo cơ chế của Spring Security.
- Ở các phiên bản Spring Security hiện đại, handler phối hợp với SecurityContextRepository của nó để lưu context rỗng hoặc bảo đảm không tiếp tục dùng lại context cũ theo cấu hình của handler. Nếu ứng dụng dùng một SecurityContextRepository tùy chỉnh, cần kiểm tra wiring/contract cụ thể.
- Nó **không tự điều hướng** sang URL logout success; controller/LogoutSuccessHandler phải quyết định response.
- Nó **không tự hủy JWT đã phát hành**, không đảm bảo revoke refresh token, không xóa cookie tùy biến hay xóa mọi session trên thiết bị khác.
- Nó **không thay CsrfLogoutHandler, RememberMeServices, audit/event handlers** nếu ứng dụng đã phụ thuộc các cleanup này mà bạn bỏ LogoutFilter.

Đoạn gọi thực tế:

~~~java
SecurityContextLogoutHandler handler =
        new SecurityContextLogoutHandler();

Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

handler.logout(request, response, authentication);
~~~

Giải thích:

- Authentication là đối tượng gắn với request vừa được Spring Security xử lý; controller lấy từ SecurityContextHolder tại thời điểm request.
- Handler nhận request/response thực của Servlet. Không được truyền request của một người khác hoặc một cookie tự chế để logout thay.
- Không cần lấy HttpSession rồi tự setAttribute("SPRING_SECURITY_CONTEXT", null) nếu đã dùng handler đúng contract. Việc hardcode tên attribute có thể phụ thuộc implementation và bỏ qua các thao tác dọn dẹp khác.
- Không dùng SecurityContextHolder.clearContext() như bước logout duy nhất; nó chỉ tác động ngữ cảnh gắn với execution hiện tại, không bảo đảm state persisted của phiên cũ đã bị xóa.

Có thể tùy chỉnh handler bằng setInvalidateHttpSession(false) hoặc setClearAuthentication(false), nhưng **không nên** dùng các cờ này chỉ để “giữ giỏ hàng” mà bỏ đánh giá bảo mật. Nếu giữ session sau logout, bạn phải có chiến lược xóa Authentication trong backing repository, quản lý session fixation, CSRF token và attributes nhạy cảm.

### Session ID sau logout thì sao?

Với một session bị invalidate, ID cũ không còn tham chiếu đến phiên hợp lệ. Browser có thể **vẫn còn cookie cũ trong trình duyệt**; request mới mang cookie đó không được coi là đã đăng nhập nếu server đã xóa/invalidate session chính xác.

Muốn xóa cookie khỏi browser cũng cần response Set-Cookie hết hạn với cùng name/path/domain tương ứng. Cấu hình cụ thể khác nhau khi dùng JSESSIONID, Spring Session cookie SESSION, reverse proxy hoặc context path. Vì vậy đừng hardcode xóa một cookie "JSESSIONID" rồi khẳng định mọi Spring Session environment đã logout hoàn toàn. Vô hiệu hóa phiên **phía server** mới là điều kiện cốt lõi; xóa cookie có thể bổ sung cho UX và bảo vệ.

## 6. Thực hành: endpoint POST /account/logout tự viết bằng MVC

Ta làm một Spring Boot Servlet app có:

- Form login mặc định của Spring Security: GET /login và POST /login.
- Tài khoản giả lập student, mật khẩu local-demo-only được băm bằng PasswordEncoder.
- GET /private trả thông tin người dùng, yêu cầu đã đăng nhập.
- POST /account/logout do **MVC controller** nhận và gọi SecurityContextLogoutHandler.
- GET /logged-out công khai sau logout.
- CSRF được giữ mặc định; POST logout thiếu token bị từ chối.
- Test MockMvc xác minh đăng nhập, gọi endpoint và session bị invalidate.

### 6.1. Cấu trúc và dependency

Sử dụng Java 17+, Spring Boot 3.3.x cùng Spring Security 6.x do BOM của Boot quản lý. Tạo project Gradle Groovy DSL:

~~~text
manual-logout-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat    (Gradle Wrapper nếu có)
  src/main/java/dev/example/manuallogout/
    ManualLogoutApplication.java
    SecurityConfig.java
    AccountLogoutController.java
    PagesController.java
  src/test/java/dev/example/manuallogout/
    ManualLogoutIntegrationTest.java
~~~

Tệp settings.gradle:

~~~groovy
rootProject.name = 'manual-logout-demo'
~~~

Tệp build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
~~~

Bạn có thể tạo Gradle Wrapper bằng Gradle tương thích hoặc khởi tạo project bằng Spring Initializr. Các file Java phụ thuộc thư viện Spring nên **không** thể chạy javac trên file đơn lẻ mà không cung cấp classpath của project. Lệnh ./gradlew sẽ cần wrapper thực sự tồn tại.

### 6.2. Spring Boot application

Tệp src/main/java/dev/example/manuallogout/ManualLogoutApplication.java:

~~~java
package dev.example.manuallogout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManualLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManualLogoutApplication.class, args);
    }
}
~~~

### 6.3. SecurityFilterChain và tài khoản demo

Tệp src/main/java/dev/example/manuallogout/SecurityConfig.java:

~~~java
package dev.example.manuallogout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("local-demo-only"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/logged-out").permitAll()
                .anyRequest().authenticated());

        http.formLogin(withDefaults());

        // Ví dụ này cố ý để POST /account/logout vào MVC controller.
        // Không sử dụng LogoutFilter mặc định song song.
        http.logout(logout -> logout.disable());

        return http.build();
    }
}
~~~

Phân tích:

- requestMatchers("/logged-out").permitAll(): sau khi session bị hủy, trình duyệt vẫn có thể xem trang xác nhận. Không bảo vệ nó bằng authenticated() nếu muốn redirect sau logout.
- anyRequest().authenticated(): GET /private và POST /account/logout cần user đã xác thực. Trang login mặc định do formLogin cung cấp vẫn được mở theo cấu hình liên quan.
- formLogin(withDefaults()) dùng filter login mặc định, hỗ trợ tạo/lưu SecurityContext theo cơ chế của Spring Security.
- logout(...disable()) **loại bỏ LogoutConfigurer/LogoutFilter chuẩn** khỏi chain để POST /account/logout có thể đi tới controller. Đó là lựa chọn **chỉ cho bài minh họa custom endpoint**. Trong production, nếu vẫn cần remember-me cleanup, logout event, custom cookies hoặc xử lý token, phải triển khai đầy đủ hoặc ưu tiên sử dụng LogoutFilter với logoutUrl.
- CsrfFilter vẫn hoạt động. Disable LogoutConfigurer **không disable CSRF**.

Không tự gắn @PostMapping("/login"): username/password được UsernamePasswordAuthenticationFilter xử lý. Không hardcode username/password production trong source; tài khoản mẫu chỉ cho localhost.

### 6.4. Controller logout tùy biến

Tệp src/main/java/dev/example/manuallogout/AccountLogoutController.java:

~~~java
package dev.example.manuallogout;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class AccountLogoutController {

    private final SecurityContextLogoutHandler logoutHandler =
            new SecurityContextLogoutHandler();

    @PostMapping("/account/logout")
    public String logout(
            HttpServletRequest request,
            HttpServletResponse response) {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        logoutHandler.logout(request, response, authentication);

        return "redirect:/logged-out";
    }
}
~~~

Đây là điểm chính của bài:

1. Spring MVC xử lý **POST /account/logout** và nhận chính request/response thuộc request hiện tại.
2. Authentication được lấy **trước** khi logout handler dọn SecurityContext.
3. SecurityContextLogoutHandler hủy session hiện hành theo mặc định, clear authentication/context và phối hợp với repository tương ứng.
4. Controller trả redirect tới /logged-out. Việc redirect không thay thế bước logout phía server.
5. Không gọi thêm HttpSession.invalidate() thủ công nếu handler đã xử lý điều đó. Gọi invalidate hai lần với session không hợp lệ có thể gây lỗi và làm flow khó hiểu.
6. Không đặt logic logout trong GET vì GET có thể được browser, crawler, preload hoặc đường dẫn bên ngoài kích hoạt ngoài ý định.

Ở ví dụ này, controller là singleton Spring bean và handler không giữ trạng thái request trong field. Không lưu Authentication hoặc HttpServletRequest vào field của controller vì nhiều request có thể chạy đồng thời. SecurityContextHolder là thread-associated theo strategy đang dùng; nếu tự xử lý async/thread switching thì cần cơ chế propagation/cleanup riêng.

**Lưu ý về SecurityContextRepository tùy biến:** nếu ứng dụng không dùng repository mặc định của SecurityContextLogoutHandler, bạn cần kiểm tra/set repository phù hợp với security chain và bảo đảm context trống được persisted đúng contract. HttpSession invalidate thường đủ cho demo session mặc định, nhưng không được tự suy ra đúng với mọi custom store.

### 6.5. Endpoint kiểm chứng trước và sau logout

Tệp src/main/java/dev/example/manuallogout/PagesController.java:

~~~java
package dev.example.manuallogout;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PagesController {

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "PRIVATE:" + authentication.getName();
    }

    @GetMapping("/logged-out")
    public String loggedOut() {
        return "LOGGED_OUT";
    }
}
~~~

/private được bảo vệ bởi anyRequest().authenticated(). /logged-out không cần session, trả response text đơn giản. Trong ứng dụng thật, trang đăng xuất có thể là HTML hoặc JSON tùy khách hàng.

### 6.6. Chạy và quan sát

Trong project có wrapper:

~~~bash
./gradlew bootRun
~~~

Với Windows PowerShell, thường dùng:

~~~powershell
.\gradlew.bat bootRun
~~~

Mở http://localhost:8080/private khi chưa login: theo formLogin mặc định, bạn thường được redirect đến /login.

Trang đăng nhập do Spring Security sinh sẵn có form và token CSRF phù hợp. Dùng tài khoản demo:

~~~text
Username: student
Password: local-demo-only
~~~

Sau đăng nhập, GET /private trả body:

~~~text
PRIVATE:student
~~~

Để thử endpoint POST /account/logout thủ công bằng browser, cần gửi **đúng session cookie và CSRF token**. Không thể kiểm chứng logout bằng GET /account/logout: controller chỉ khai báo @PostMapping.

Ví dụ form Thymeleaf để tích hợp thêm vào trang ứng dụng (snippet này **không nằm trong project mẫu ở trên**, muốn dùng cần có Spring MVC/Thymeleaf template integration):

~~~html
<form th:action="@{/account/logout}" method="post">
    <button type="submit">Đăng xuất</button>
</form>
~~~

Với Thymeleaf và RequestDataValueProcessor của Spring Security, form method=POST có th:action có thể tự được thêm trường ẩn CSRF; hãy kiểm tra HTML đã render. Nếu dùng plain HTML, phải chủ động lấy token thật từ CSRF repository/request. Không hardcode một CSRF token cố định vào template.

Sau logout thành công, browser chuyển đến /logged-out và thấy LOGGED_OUT. Truy cập /private lần nữa không còn được xác thực bằng session vừa invalidate, nên bị chuyển về /login trong cấu hình formLogin.

**Không ghi cookie session, mật khẩu hoặc CSRF token vào tài liệu/log khi trình diễn.** Request có token sai thường bị CsrfFilter từ chối trước controller; HTTP status 403 trong trường hợp này không có nghĩa SecurityContextLogoutHandler đã chạy.

## 7. Kiểm thử MockMvc cho MVC endpoint

Thêm file src/test/java/dev/example/manuallogout/ManualLogoutIntegrationTest.java:

~~~java
package dev.example.manuallogout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ManualLogoutIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadPrivatePage() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void anonymousCanReadLogoutConfirmation() throws Exception {
        mvc.perform(get("/logged-out"))
                .andExpect(status().isOk())
                .andExpect(content().string("LOGGED_OUT"));
    }

    @Test
    void customLogoutInvalidatesAuthenticatedSession() throws Exception {
        MvcResult login = mvc.perform(
                        post("/login").with(csrf())
                                .param("username", "student")
                                .param("password", "local-demo-only"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/private").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("PRIVATE:student"));

        mvc.perform(post("/account/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/logged-out"));

        assertThat(session.isInvalid()).isTrue();

        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void missingCsrfDoesNotExecuteLogout() throws Exception {
        MvcResult login = mvc.perform(
                        post("/login").with(csrf())
                                .param("username", "student")
                                .param("password", "local-demo-only"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(post("/account/logout").session(session))
                .andExpect(status().isForbidden());

        assertThat(session.isInvalid()).isFalse();
    }

    @Test
    void getMethodDoesNotTriggerLogoutEndpoint() throws Exception {
        MvcResult login = mvc.perform(
                        post("/login").with(csrf())
                                .param("username", "student")
                                .param("password", "local-demo-only"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/account/logout").session(session))
                .andExpect(status().isMethodNotAllowed());

        assertThat(session.isInvalid()).isFalse();
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Các assertions xác minh:

- Anonymous không truy cập được /private.
- Trang xác nhận /logged-out là công khai.
- Login đúng tạo authenticated session và /private trả PRIVATE:student.
- POST logout với csrf() chuyển tới /logged-out, MockHttpSession được đánh dấu invalid.
- POST thiếu CSRF bị từ chối 403 mà không invalidate session.
- GET cùng URL không thực hiện logout do controller chỉ khai báo POST.

**Lưu ý kiểm thử:** Sau khi MockHttpSession đã bị invalidate, không nên tái đưa chính object đó vào một request MockMvc mới để kỳ vọng redirect. MockHttpSession có thể ném IllegalStateException khi cố dùng một phiên đã hết hiệu lực. Bài kiểm tra trực tiếp session.isInvalid() rồi gửi request anonymous mới để chứng minh luồng phân quyền, tránh misuse mock session. Trong integration test chạy container thật, có thể dùng cookie cũ trên request mới để xác minh server không còn nhận phiên đó.

Test dựa trên Spring Boot/Security/Servlet mặc định và không dùng Redis hoặc custom SecurityContextRepository. Với một cấu hình custom, cần viết thêm test cho repository/cookie tương ứng; việc MockMvc PASS không tự bảo đảm mọi node trong cluster đều đã logout.

### Cải thiện: xác minh cookie cũ không còn hiệu lực

Ở kiểm thử end-to-end HTTP thật, một quy trình mạnh hơn là: login lấy cookie sau session fixation; gọi POST logout với cookie và CSRF hợp lệ; tiếp tục GET /private dùng lại cookie đã logout; kỳ vọng không authenticated và nhận redirect/challenge. Cần dùng cookie jar và CSRF token theo flow thật. Không ghi session ID vào log build hoặc screenshot công khai.

## 8. CSRF và phương thức HTTP cho logout

Logout là hành động thay đổi trạng thái. Nếu ứng dụng dùng session cookie để xác thực, request từ một site khác có thể được trình duyệt gửi kèm cookie theo chính sách cookie hiện hành. Bởi vậy Spring Security mặc định bảo vệ logout bằng CSRF khi CSRF protection bật.

Một số quy tắc:

1. Với form login/cookie session, **POST logout có CSRF token hợp lệ** là lựa chọn phổ biến.
2. GET thường dành cho thao tác an toàn, không nên xóa phiên khi user chỉ mở link. Crawler, prefetch hoặc thẻ hình ảnh có thể gọi GET ngoài ý định.
3. requestMatchers("/account/logout").permitAll() chỉ xét authorization; nó **không tự bỏ qua CSRF** cho POST.
4. Khi xây MVC endpoint, CsrfFilter vẫn chạy trước DispatcherServlet. POST thiếu/sai token có thể bị từ chối 403 trước khi controller được gọi.
5. Với SPA/fetch cần gửi token theo header/form field được repository cấu hình, xử lý cookie/SameSite/credentials đúng cross-origin contract.
6. Không disable CSRF toàn bộ security chain chỉ để “curl logout dễ hơn”.

Ví dụ mẫu thô về form **đã render**:

~~~html
<form action="/account/logout" method="post">
    <input type="hidden" name="_csrf"
           value="TOKEN_DO_SERVER_SINH_TRONG_REQUEST_THAT">
    <button type="submit">Đăng xuất</button>
</form>
~~~

Chuỗi TOKEN_DO_SERVER_SINH_TRONG_REQUEST_THAT chỉ là **minh họa**, không phải token hợp lệ. Một template hoàn chỉnh phải lấy token từ Spring Security, không hardcode hoặc trích từ request khác.

### GET /logout là gì khi dùng cấu hình mặc định?

Trong một số cấu hình Spring Security với CSRF bật, GET /logout có thể hiển thị trang xác nhận yêu cầu submit POST logout, chứ **không** ngay lập tức chấm dứt phiên. Hành vi phụ thuộc cấu hình logout handler và framework. Vì vậy không suy từ việc GET /logout trả 200 rằng session đã bị xóa; test trực tiếp request tiếp theo tới tài nguyên bảo vệ.

Nếu tắt CSRF, LogoutConfigurer có thể thay đổi cách match phương thức logout và mở rộng cơ hội logout qua GET, nên phải hiểu rõ hậu quả trước khi thay đổi matcher. Không dựa vào giả định “đường dẫn /logout luôn chỉ POST” trên mọi cấu hình.

## 9. Nếu muốn trả HTTP 204 hoặc JSON thay redirect?

Nhiều SPA muốn POST /account/logout trả 204 No Content thay vì 302. **Nếu LogoutFilter đã đủ nhu cầu**, hãy dùng LogoutSuccessHandler:

~~~java
http.logout(logout -> logout
        .logoutUrl("/account/logout")
        .logoutSuccessHandler((request, response, authentication) -> {
            response.setStatus(204);
        })
        .permitAll());
~~~

Đoạn trích này dùng LogoutFilter pipeline chuẩn, nên thường an toàn hơn việc tự bỏ các cleanup handlers. Thay bằng JSON:

~~~java
http.logout(logout -> logout
        .logoutUrl("/account/logout")
        .logoutSuccessHandler((request, response, authentication) -> {
            response.setStatus(200);
            response.setContentType("application/json");
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write("{\"logout\":\"ok\"}");
        })
        .permitAll());
~~~

Bên gửi request phải chịu trách nhiệm diễn giải 204/200, không mặc định có redirect. Nếu ứng dụng là SPA và dùng cookie authentication, vẫn cần CSRF protection phù hợp.

Với MVC custom controller, có thể dùng @RestController và trả ResponseEntity.noContent().build() sau khi gọi SecurityContextLogoutHandler. Nhưng cần hiểu rằng các cleanup ngoài handler (CSRF/remember-me/custom cookie) không tự xảy ra chỉ vì bạn đổi kiểu trả về từ redirect sang 204.

## 10. SecurityContext, HttpSession và cookie: hiểu đúng ranh giới

### 10.1. HttpSession.invalidate() không tương đương xóa mọi dấu vết

Invalidate session server-side là một phần quan trọng, nhưng browser có thể giữ cookie cũ; người dùng có thể có phiên khác trên thiết bị khác; token API có thể còn sống. Không công bố “logout tất cả thiết bị” nếu chỉ xóa phiên được request gửi lên.

Một ứng dụng có thể dùng Spring Session Redis để chia sẻ HttpSession giữa nhiều node. SecurityContextLogoutHandler vẫn hoạt động ở tầng Servlet session, và invalidate có thể xóa phiên khỏi SessionRepository tương ứng. Tuy nhiên cần kiểm tra TTL, consistency, cookie ID, node failover và request đồng thời. Không dùng log từ một node làm bằng chứng tuyệt đối cho logout đa node.

### 10.2. Session fixation và ID thay đổi khi login

Spring Security thường đổi session ID sau khi xác thực để ngăn session fixation. Cookie trước login và cookie sau login có thể khác. Logout phải áp dụng lên **session hiện đang dùng**, không lấy ID trước login để xóa một bản ghi không còn tương ứng.

Đừng tắt session fixation protection để test logout. Với MockMvc, lấy session từ request **đăng nhập thành công**, rồi dùng session đó ở POST logout như bài kiểm thử.

### 10.3. Dọn cookie đúng name/path/domain

Nếu muốn yêu cầu browser xóa cookie:

- Xác định cookie thật từ Set-Cookie, kể cả JSESSIONID hay SESSION.
- Xác định Path/Domain/context path, Secure, SameSite và phạm vi proxy.
- Gửi cookie xóa có đúng name/path/domain và Max-Age=0 hoặc Expires quá khứ.
- Hiểu rằng xóa cookie là bổ sung, không thay invalidate phiên server.
- Với Spring Session Redis, chính sách cookie có thể nằm trong CookieSerializer và khác container mặc định.

LogoutConfigurer.deleteCookies(...) hoặc CookieClearingLogoutHandler có thể giúp khi dùng LogoutFilter; khi tự viết MVC cần chủ động gắn cleanup tương đương nếu sản phẩm yêu cầu xóa cookie. Hardcode response.addCookie(new Cookie("JSESSIONID", "")) mà không set Path/Max-Age đúng thường không hoạt động như mong muốn.

### 10.4. CSRF token sau logout

Trong cấu hình mặc định dùng session-based CsrfTokenRepository, invalidate session cũng khiến token session cũ không còn hợp lệ. Nhưng nếu dùng CookieCsrfTokenRepository hoặc cơ chế custom, cần **xóa/rotate CSRF token** phù hợp; logout DSL tiêu chuẩn có các bước cleanup mà custom MVC endpoint có thể bỏ lỡ.

Sau logout nếu trang /login cần CSRF token mới, đảm bảo token mới được cấp khi form login tiếp theo render. Đừng giữ token từ phiên cũ và gửi lại cho session mới.

### 10.5. Remember-me token và các cookie phụ

Remember-me authentication có thể dùng cookie/token độc lập với HttpSession. Nếu chỉ invalidate session mà **không xóa remember-me**, request tiếp theo có thể tự xác thực lại người dùng qua remember-me, khiến họ tưởng logout thất bại.

Với LogoutFilter, Spring Security có thể phối hợp RememberMeServices/LogoutHandler theo cấu hình; khi viết MVC endpoint, phải đưa remember-me cleanup vào thiết kế một cách tường minh. Đối với persistent remember-me tokens, có thể cần xóa entry database/token series. Đây là một lý do mạnh để **ưu tiên logout DSL chuẩn** nếu không có nhu cầu đặc thù.

### 10.6. Request đang thực thi và nhiều phiên

Một request khác có thể đã nạp SecurityContext trước khi logout. Invalidate session không đảm bảo dừng tức khắc mọi request **đang xử lý**. Nếu ứng dụng cần thu hồi quyền chặt chẽ, thiết kế kiểm tra bổ sung, ví dụ session version/revocation list/authorization logic cho hành động nhạy cảm.

Logout tại một browser không đồng nghĩa logout mọi thiết bị. Muốn tính năng logout-all, cần index/truy vấn các session của principal theo repository phù hợp và thu hồi từng session/tokens theo chính sách riêng. Không quét session Redis tùy tiện bằng key string tự đoán ở production.

## 11. Mở rộng và điểm tích hợp thường gặp

| Nhu cầu | Cách làm ưu tiên | Lưu ý |
| --- | --- | --- |
| Đổi URL logout | LogoutConfigurer.logoutUrl(...) | Không cần MVC @PostMapping |
| Chuyển về trang thông báo | LogoutConfigurer.logoutSuccessUrl(...) | Trang sau logout phải public |
| Trả 204 hoặc JSON | LogoutConfigurer.logoutSuccessHandler(...) | Giữ pipeline LogoutFilter |
| Thêm một bước dọn token/cookie riêng | LogoutConfigurer.addLogoutHandler(...) | Không sửa trực tiếp LogoutFilter nội bộ |
| Xóa cookie nhất định | deleteCookies(...) hoặc CookieClearingLogoutHandler | Cookie name/path/domain phải đúng |
| Hủy phiên và xóa SecurityContext trong MVC endpoint | SecurityContextLogoutHandler.logout(...) | Không tự động gọi các handler còn lại |
| Xử lý logout OAuth2/OIDC | Cấu hình client/resource-server/OIDC logout phù hợp | Có thể cần end-session endpoint tại IdP |
| Thu hồi bearer/refresh token | Token revocation/introspection hoặc cơ chế provider | Session invalidate không tự revoke JWT |
| Logout mọi thiết bị | Session index/revocation store do ứng dụng thiết kế | Không tương đương logout phiên hiện tại |
| Audit hành động logout | Event/LogoutHandler/hook phù hợp | Không log credentials/session IDs |

Đối với custom LogoutHandler, API nhận request, response và Authentication; handler nên thực thi cleanup an toàn, xử lý retry/idempotency khi cần. Nếu cleanup phụ thuộc dịch vụ bên ngoài, hãy xác định chính sách khi dịch vụ đó bị lỗi; không để một timeout của audit biến thành trạng thái UI ghi “đã logout” trong khi session còn sống.

Trong ứng dụng OAuth2 Login, logout local session không nhất thiết đăng xuất khỏi Identity Provider; người dùng có thể được đăng nhập lại ngay bằng SSO khi chuyển tới login page. Cần phân biệt **local logout**, **RP-initiated logout** và **single logout** theo giao thức. Không dùng một SecurityContextLogoutHandler đơn lẻ để tuyên bố đã xóa mọi SSO session.

## 12. Các lỗi phổ biến và cách sửa

### Lỗi 1 — @PostMapping cùng đường dẫn mà LogoutFilter đang match

Triệu chứng: controller không log/không chạy, nhưng request logout vẫn redirect. Nguyên nhân: LogoutFilter nằm trước MVC và đã xử lý URL. Sửa: nếu chỉ cần đổi hành vi, dùng LogoutConfigurer; nếu thật sự cần controller, để LogoutFilter không match URL hoặc vô hiệu hóa nó **có chủ đích**, đồng thời chịu trách nhiệm cleanup.

### Lỗi 2 — Chỉ return "redirect:/login"

Triệu chứng: frontend báo logout thành công nhưng refresh trang private vẫn xem được. Nguyên nhân: chưa invalidate session và chưa clear SecurityContext. Sửa: gọi SecurityContextLogoutHandler đúng request/response/authentication hoặc dùng LogoutFilter chuẩn.

### Lỗi 3 — Chỉ clear SecurityContextHolder

Triệu chứng: request hiện tại có vẻ anonymous nhưng request tiếp theo vẫn khôi phục Authentication từ HttpSession. Nguyên nhân: context đã lưu/persisted chưa được xóa. Sửa: dùng SecurityContextLogoutHandler, session/repository cleanup, xác minh bằng request mới.

### Lỗi 4 — POST logout thiếu CSRF trả 403

Đây thường là hành vi đúng khi CSRF bật. Sửa: form gửi CSRF token hợp lệ, test với spring-security-test csrf(); không disable CSRF toàn bộ ứng dụng chỉ để test curl.

### Lỗi 5 — GET /account/logout không làm gì

Khi controller chỉ @PostMapping, GET sẽ không thực thi logout. Đây là thiết kế chủ đích tránh logout qua request safe method. Đừng đổi sang @GetMapping vì muốn link dễ bấm; dùng form POST hoặc fetch có CSRF.

### Lỗi 6 — Remember-me tự đăng nhập lại ngay sau logout

Invalidate HttpSession chưa đủ nếu remember-me cookie/persistent token còn hợp lệ. Sửa: dùng LogoutFilter và cleanup tương ứng, hoặc trong MVC endpoint xóa token/cookie remember-me đúng cơ chế đã cấu hình.

### Lỗi 7 — Cookie vẫn còn sau khi logout

Cookie browser tồn tại không tự nghĩa là session server còn sống. Sửa: test request mới đến private endpoint; nếu muốn xóa cookie cho UX, chọn tên/path/domain/flags và Max-Age=0 tương ứng với CookieSerializer.

### Lỗi 8 — Logout một phiên nhưng ứng dụng nói “mọi thiết bị đã đăng xuất”

Một SecurityContextLogoutHandler được gọi trong request hiện tại không xóa mọi session khác hoặc JWT đã cấp. Sửa: chỉ thông báo đúng phạm vi, hoặc xây cơ chế session index/revocation cho yêu cầu logout-all.

### Lỗi 9 — Tắt LogoutFilter rồi quên các handler mặc định khác

Triệu chứng: CSRF cookie/remember-me token không được dọn, logout event không phát, cookie custom còn hợp lệ. Sửa: liệt kê mọi handler đang cần, bổ sung và kiểm thử từng hành vi, hoặc chuyển về LogoutConfigurer.

### Lỗi 10 — Dùng controller logout trong stateless API như thể JWT sẽ bị thu hồi

SecurityContextLogoutHandler không thể vô hiệu hóa chữ ký JWT đã phát hành. Sửa: dùng access-token TTL thích hợp, revocation/introspection/blocklist theo threat model, refresh-token rotation/revocation và logout của IdP nếu liên quan.

### Lỗi 11 — Session được khôi phục sau logout do custom repository

Có thể ứng dụng dùng custom SecurityContextRepository hoặc logic ghi lại Authentication cuối request. Sửa: kiểm tra saveContext/clear repository, thứ tự filter, các cache riêng và test bằng session ID cũ trên request mới; không chỉ test thread-local trong controller.

### Lỗi 12 — Mất CSRF hoặc cookie khi sau logout được redirect

Nếu session đã bị invalidated, token cũ không còn. Trang login mới cần token/session mới khi render. Kiểm tra CSRF repository, cookie serializer và sự tương tác reverse proxy. Không cố tái sử dụng token cũ.

### Lỗi 13 — Logout endpoint không được phân quyền như dự định

Với MVC controller, AuthorizationFilter vẫn có thể chặn request trước khi vào controller nếu endpoint được yêu cầu authenticated hoặc chain khác match trước. Thiết kế rõ hành vi cho logout anonymous và cho endpoint xác thực. Đối với LogoutFilter, endpoint có thể được xử lý sớm trước authorization; hai cách không có cùng yêu cầu permitAll.

### Lỗi 14 — Handler chứa state request trong field singleton

Một Controller/LogoutHandler có thể được dùng đồng thời bởi nhiều request. Không lưu HttpServletRequest, Authentication hoặc cookie cá nhân trong mutable field. Truyền thông tin theo tham số, dùng service thread-safe và đảm bảo không tạo leak.

## 13. Checklist kiểm thử và triển khai production

Trước khi triển khai logout tùy biến:

1. **Chọn cơ chế:** LogoutFilter/LogoutConfigurer hay MVC controller. Không để hai nơi cùng “sở hữu” một URL.
2. **Chọn HTTP method:** ưu tiên POST có CSRF phù hợp cho session cookie web app; tránh GET gây thay đổi trạng thái.
3. **Xác minh route:** URL logout thuộc SecurityFilterChain phù hợp; POST tới đúng controller hoặc LogoutFilter.
4. **Xóa trạng thái đúng cách:** handler invalidate HttpSession và clear SecurityContext; custom SecurityContextRepository cũng được xử lý.
5. **Trả response đúng hợp đồng:** redirect/public success page, 204/200 JSON, không “success” trước khi cleanup tối thiểu có kết quả.
6. **Kiểm tra CSRF:** POST thiếu token bị chặn; token sau logout không được tái sử dụng trái phép.
7. **Kiểm tra cookies:** phiên không còn hiệu lực ngay cả khi cookie cũ được gửi lại; nếu xóa cookie, dùng đúng name/path/domain.
8. **Đừng quên remember-me:** xóa cookie hoặc token store theo cơ chế ứng dụng dùng.
9. **Kiểm tra nhiều phiên/thiết bị:** logout hiện tại khác logout-all; có chính sách revocation riêng nếu yêu cầu.
10. **Đánh giá SSO/OIDC/token:** local logout không thay IDP logout hay token revocation.
11. **Bảo vệ dữ liệu:** không log raw password, JSESSIONID/SESSION, CSRF token hoặc Authorization header.
12. **Test MockMvc và HTTP thật:** login → private 200 → logout → private redirected/challenged; test GET/POST thiếu CSRF và request cookie cũ.
13. **Test môi trường multi-node:** Spring Session Redis/JDBC/replication, request mới sau logout ở node khác không khôi phục phiên cũ.
14. **Xử lý lỗi cleanup:** nhớ audit, rate limit và observability theo chính sách; không hi sinh xóa session vì một phụ thuộc audit bị lỗi.
15. **Kiểm thử phiên bản:** xác minh hành vi trên đúng Spring Boot/Spring Security/Servlet container đang triển khai, đặc biệt custom repository và csrf token storage.

## 14. Tình huống tự luyện

**Câu 1.** Muốn đổi POST /logout thành POST /account/logout và trả 204, có cần @RestController không?

**Đáp án:** không nhất thiết. Có thể dùng logoutUrl("/account/logout") và logoutSuccessHandler trả 204 trong LogoutConfigurer, giữ các LogoutHandler mặc định.

**Câu 2.** Nếu viết @PostMapping("/account/logout") mà trong SecurityFilterChain đã cấu hình logoutUrl("/account/logout"), controller có chạy không?

**Đáp án:** thường không; LogoutFilter xử lý URL phù hợp trước khi đến DispatcherServlet. Phải chọn một chủ sở hữu của đường dẫn.

**Câu 3.** Chỉ gọi SecurityContextHolder.clearContext() thì đủ logout chưa?

**Đáp án:** không chắc. SecurityContext có thể đã được lưu trong HttpSession; request sau có thể đọc lại. Dùng SecurityContextLogoutHandler hoặc pipeline chuẩn để xử lý session/repository.

**Câu 4.** POST logout không có CSRF token trả 403. Đó có phải lỗi password không?

**Đáp án:** không. CsrfFilter có thể từ chối trước controller/logout filter, bảo vệ hành động thay đổi trạng thái.

**Câu 5.** Sau LogoutHandler, cookie JSESSIONID vẫn còn trong browser nhưng GET /private bị redirect /login. User còn đăng nhập không?

**Đáp án:** không theo phiên đã invalidated. Cookie cũ không có session server hợp lệ; xóa cookie thêm chỉ là biện pháp bổ sung theo contract.

**Câu 6.** Vì sao logout thành công rồi refresh lại thấy user đăng nhập do remember-me?

**Đáp án:** remember-me token/cookie có thể độc lập với HttpSession. Nếu custom endpoint bỏ qua remember-me cleanup, request sau có thể tạo Authentication mới.

**Câu 7.** SecurityContextLogoutHandler có xóa access JWT trên mọi thiết bị không?

**Đáp án:** không. JWT stateless cần chính sách revocation/expiry riêng, và logout-all cần thiết kế thu hồi phiên/token trên nhiều thiết bị.

**Câu 8.** Có nên mở GET /logout cho tiện tạo hyperlink?

**Đáp án:** nên tránh logout qua GET vì GET là safe method có thể bị browser/crawler/prefetch kích hoạt. Dùng form POST có token CSRF.

**Câu 9.** Khi dùng Spring Session Redis, gọi invalidate() ở node A có giúp node B không còn nhận phiên đó không?

**Đáp án:** với một SessionRepository dùng chung hoạt động đúng, request mới trên B không tìm được session đã invalidated; vẫn phải kiểm thử consistency, cache và request in-flight.

**Câu 10.** Controller trả 302 /logged-out nhưng không ai gọi logout handler. Bạn kiểm chứng lỗi thế nào?

**Đáp án:** login, gọi controller, rồi gửi GET /private bằng session cookie cũ. Nếu còn 200, logout chưa xóa state. Thêm SecurityContextLogoutHandler hoặc dùng LogoutFilter.

## Kết luận

**Cách ưu tiên:** nếu chỉ cần thay URL, status, redirect hoặc một bước cleanup bổ sung, hãy dùng **HttpSecurity.logout(...)** để giữ pipeline LogoutFilter và các handler đã được cấu hình.

**Khi thực sự dùng endpoint MVC tùy biến:** POST logout phải đi tới controller, CSRF vẫn được áp dụng, controller gọi **SecurityContextLogoutHandler.logout(request, response, authentication)** để vô hiệu hóa phiên và xóa SecurityContext, rồi mới quyết định HTTP response. Những cleanup ngoài handler (CSRF repository tùy biến, remember-me, cookie riêng, token/IdP, session khác) **phải được xử lý riêng theo kiến trúc hệ thống**.

Một logout đúng không được đánh giá bằng việc trang hiển thị “Đăng xuất thành công”, mà bằng **request mới với credential/session cũ không còn được cấp quyền ngoài ý định**, trên đúng SecurityFilterChain và mọi node cần thiết.