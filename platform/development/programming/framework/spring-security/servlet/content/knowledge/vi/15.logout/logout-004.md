# Xóa cookie phiên, remember-me và dữ liệu trình duyệt phù hợp

Đăng xuất trong **Spring Security cho ứng dụng Servlet** không chỉ là điều hướng về trang login. Một lần logout an toàn có thể phải xử lý nhiều tầng trạng thái: **SecurityContext**, **HttpSession** phía server, cookie phiên trong browser, cookie **remember-me** và token liên quan, CSRF token, dữ liệu ứng dụng được giữ trong tab/trình duyệt, cũng như cache chứa nội dung nhạy cảm.

Điểm quan trọng: **hủy phiên trên server và xóa cookie trên browser là hai thao tác khác nhau**. Cookie có thể vẫn còn sau khi session bị invalidate, nhưng không còn tra được session hợp lệ. Ngược lại, việc xóa cookie không đương nhiên thu hồi phiên, các remember-me token trong database hay access token đã phát hành. Vì vậy phải chọn các biện pháp phù hợp với **cơ chế authentication thực sự** đang sử dụng.

Bài này tập trung vào Spring Boot 3.x, Spring Security 6.x, Java 17+ trong mô hình **Servlet, form login và session-based authentication**. Nội dung lần lượt giải thích cookie scope, Spring Security `logout` DSL, remember-me dạng token-based/persistent, `Clear-Site-Data`, cookies CSRF, cleanup frontend, ví dụ cấu hình đầy đủ, kiểm thử, lỗi phổ biến và checklist production. Những khác biệt theo phiên bản, servlet container và cấu hình HTTPS/reverse proxy phải được xác minh trên môi trường triển khai.

## 1. Sau khi đăng nhập, trạng thái nằm ở những đâu?

Một ứng dụng web thông thường có thể có nhiều “mảnh” của một lần đăng nhập:

~~~text
Browser                                      Server / infrastructure
+--------------------------------+         +--------------------------------+
| JSESSIONID cookie              | ------> | HttpSession (container/store)  |
| remember-me cookie             | ------> | RememberMeServices + key/token |
| XSRF-TOKEN (nếu dùng repo này) |         | CSRF token repository          |
| localStorage/sessionStorage    |         | SecurityContextRepository      |
| app memory / SPA state         |         | SessionRegistry (nếu có)       |
| browser cache / bfcache        |         | Remember-me persistent DB      |
+--------------------------------+         | JWT/refresh token store/IdP   |
                                           +--------------------------------+
~~~

Mọi thành phần trong sơ đồ **không mặc định đều tồn tại**. Ví dụ: một site dùng CSRF token trong HTTP session sẽ không cần cookie `XSRF-TOKEN`; một resource server stateless chỉ dùng Bearer JWT có thể không có `JSESSIONID` cho authentication; ứng dụng không bật remember-me sẽ không dùng cookie remember-me.

Đối với form login Servlet stateful, các khái niệm chính:

- `HttpSession`: nơi container hoặc Spring Session giữ dữ liệu session. Cookie `JSESSIONID` thường là định danh để tìm phiên, **không chứa trực tiếp SecurityContext** ở dạng plaintext.
- `SecurityContext`: chứa `Authentication` hiện tại. Với session-based login, `SecurityContextRepository` có thể lưu/đọc context qua session; sau logout, context không nên tiếp tục được tái sử dụng.
- `RememberMeServices`: cơ chế nhận diện người dùng ở request sau khi session đã biến mất nhưng browser vẫn còn remember-me cookie hợp lệ; cần logout/cancel đúng.
- `CsrfTokenRepository`: lưu/trả token chống CSRF; có thể dùng session hoặc cookie. Đời sống CSRF token khác đời sống JWT hoặc remember-me.
- Dữ liệu frontend: cache, state, storage và nội dung đã render trong tab có thể còn, kể cả khi server không còn cho phép request mới.

Một UX đăng xuất hoàn chỉnh cần xử lý **trạng thái xác thực bên server** và **dấu vết client theo phạm vi được phép**, không xóa bừa dữ liệu không liên quan.

## 2. Logout chuẩn của Spring Security làm gì?

Với form login mặc định, Spring Security có `LogoutFilter` xử lý endpoint logout được cấu hình. Khi request khớp, filter chạy các `LogoutHandler` để dọn trạng thái rồi gọi `LogoutSuccessHandler` trả response/redirect.

~~~text
POST /logout + CSRF token hợp lệ
          |
          v
CsrfFilter (nếu được bật)
          |
          v
LogoutFilter
          |
          +--> SecurityContextLogoutHandler
          |      +--> invalidate HttpSession theo cấu hình
          |      +--> clear Authentication / SecurityContext
          |      +--> lưu trạng thái context trống theo repo
          |
          +--> CsrfLogoutHandler (nếu được cấu hình trong chain)
          |      +--> dọn CSRF token tương ứng
          |
          +--> RememberMeServices.logout(...) (khi remember-me được bật)
          |      +--> cancel cookie / dữ liệu token theo cơ chế
          |
          +--> LogoutHandler tùy chỉnh nếu có
          |
          v
LogoutSuccessHandler
          +--> redirect /login?logout
          hoặc trả HTTP 200/204/JSON cho API
~~~

Sơ đồ thể hiện **nhiệm vụ**, không cam kết một thứ tự nội bộ bất biến giữa mọi phiên bản hoặc mọi handler tùy chỉnh. Tùy bean/cấu hình, danh sách handler thực tế có thể khác.

### Vòng đời quan trọng

1. **Trước logout:** browser có session cookie; server có thể lưu Authentication trong session. Remember-me cookie có thể tồn tại độc lập.
2. **Trong logout:** server hủy session và xóa context theo chính sách; remember-me service có cơ hội xử lý cookie/token. Nếu custom handler gửi response sai hoặc ném exception, logout có thể không đạt toàn bộ trạng thái mong muốn.
3. **Sau logout:** request tới resource bảo vệ phải không còn được xác thực nhờ session cũ. Trình duyệt có thể cần redirect/login lại. Nếu remember-me vẫn hợp lệ, request sau có thể **tự đăng nhập lại**, tạo cảm giác “logout không có tác dụng”.
4. **Dữ liệu client:** nội dung đang mở trong tab hoặc nằm trong storage có thể vẫn thấy ở UI; phải dọn theo yêu cầu sản phẩm, và server luôn kiểm tra authentication/authorization cho request mới.

### Logout phải dùng POST khi CSRF bật

Với Spring Security form login và CSRF protection mặc định, **POST /logout** kèm CSRF token hợp lệ là thao tác phổ biến. GET /logout trong một số cấu hình có thể chỉ hiển thị trang xác nhận logout, **không thực hiện logout bằng một GET tự phát**. Không tắt CSRF chỉ vì một link GET logout tiện hơn: logout-CSRF có thể khiến người dùng bị logout ngoài ý muốn, và các ứng dụng có hành vi phức tạp còn có rủi ro khác.

## 3. Hai việc riêng biệt: invalidate session và delete cookie

### 3.1. Hủy phiên phía server

Fragment DSL:

~~~java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true));
~~~

`invalidateHttpSession(true)` yêu cầu `SecurityContextLogoutHandler` xử lý invalidation của session phù hợp. `clearAuthentication(true)` dọn Authentication trong context khi logout. Trong cấu hình Spring Security logout chuẩn, những hành vi bảo mật cơ bản thường đã được bật; đặt tường minh giúp người đọc nhìn thấy ý định.

Khi một session bị invalidate:

- Dữ liệu session gắn với ID cũ không còn được truy xuất như một phiên hợp lệ qua session store/container.
- Context lưu trong session cũ không còn được dùng để xác thực request mới.
- Các attribute nghiệp vụ nằm trong session cũng có thể bị xóa, không chỉ Authentication.
- Cookie cũ phía browser **không bị tự động xóa trong mọi container/browser**. Browser có thể vẫn gửi JSESSIONID cũ; nó chỉ không còn trỏ tới session hợp lệ.

**Không dùng việc xóa cookie làm biện pháp thay thế session invalidation.** Xóa cookie là một yêu cầu gửi tới trình duyệt; nó không đảm bảo hủy đối tượng server session đã tồn tại. Bảo mật dựa trên server-side invalidation và authentication checks trước tiên.

### 3.2. Yêu cầu browser xóa cookie

Cookie HTTP không có một lệnh “delete” đặc biệt từ server. Server gửi `Set-Cookie` cho cùng cookie với `Max-Age=0` (hoặc `Expires` đã qua), kèm đúng phạm vi `Path` và `Domain` phù hợp; browser dùng header đó để hết hạn cookie.

~~~http
HTTP/1.1 302 Found
Location: /login?logout
Set-Cookie: JSESSIONID=; Path=/; Max-Age=0; HttpOnly
~~~

Đây là **ví dụ HTTP minh họa**, không khẳng định mọi ứng dụng thực có `Path=/` hoặc thứ tự thuộc tính như vậy. Server có thể dùng `Expires` quá khứ, và cookie có thể được cấu hình `Secure; SameSite=Lax`. Khi HTTPS được dùng, cần kiểm tra các thuộc tính phù hợp với chính sách cookie.

Với Spring Security:

~~~java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .deleteCookies("JSESSIONID")
    .logoutSuccessUrl("/login?logout"));
~~~

`deleteCookies("JSESSIONID")` thêm thao tác gửi cookie hết hạn cho tên đó; nó **không tự biết mọi biến thể Path/Domain** mà những lớp hạ tầng khác từng phát hành. Ứng dụng có `server.servlet.session.cookie.name=SESSIONID` hoặc Spring Session dùng tên cookie khác thì phải xóa đúng tên thực. Trong dự án dùng reverse proxy/context path, kiểm tra header Set-Cookie ở response thật.

### 3.3. Cookie được định danh bởi name, domain và path

Hai cookie có cùng tên nhưng khác Path hoặc Domain có thể cùng tồn tại. Xóa `JSESSIONID` với Path không khớp có thể không tác động cookie cũ.

| Cookie đã phát hành | Set-Cookie để xóa | Kỳ vọng |
| --- | --- | --- |
| `JSESSIONID`, host-only, `Path=/` | Cùng tên, host-only, `Path=/`, `Max-Age=0` | Xóa đúng cookie |
| `JSESSIONID`, host-only, `Path=/portal` | Cùng tên nhưng `Path=/` | **Không xóa** cookie ở /portal |
| `remember-me`, `Domain=example.test`, `Path=/` | Cookie host-only (không Domain) | Có thể không xóa đúng phạm vi Domain cookie |
| `JSESSIONID`, `Path=/portal`, domain phù hợp | Cùng name/domain/path, `Max-Age=0` | Xóa đúng scope |

Cần hiểu Domain/host-only từ response `Set-Cookie` **lúc phát hành**, không suy luận chỉ từ tên cookie. Với các cookie tên đặc biệt như `__Host-...`, quy tắc Secure/Path/Domain của browser phải được tôn trọng khi phát hành và làm hết hạn.

**Lưu ý về Path của servlet app:** Khi ứng dụng chạy dưới `/portal`, cookie session thường có Path=/portal hoặc một giá trị đã được cấu hình; với Spring Session, proxy và load balancer, tên và Path có thể khác. Xóa cookie cần nhất quán với hạ tầng thực sự set cookie.

### 3.4. HttpOnly và JavaScript

Một cookie `HttpOnly` không thể đọc/xóa trực tiếp bằng `document.cookie` từ JavaScript. Đây là chủ đích bảo vệ cookie khỏi việc bị JavaScript truy cập. Phương án đúng: **server trả Set-Cookie hết hạn** và invalidates session. Không bỏ `HttpOnly` chỉ để frontend có thể tự xóa JSESSIONID.

Browser có thể bỏ qua hoặc hạn chế header Set-Cookie trong điều kiện domain, HTTPS, SameSite, CORS hay path không phù hợp. Cần kiểm thử trên browser thật.

## 4. Remember-me: vì sao logout xong lại tự đăng nhập?

Remember-me nhằm cho phép browser khôi phục Authentication ở request sau **khi session không còn nhưng remember-me cookie vẫn hợp lệ**. Nếu chỉ xóa JSESSIONID, ứng dụng có thể gặp:

~~~text
User login + chọn Remember me
   |
   v
Server cấp session + remember-me cookie
   |
   v
User logout, chỉ invalidate session/JSESSIONID
   |
   v
Browser vẫn giữ remember-me cookie
   |
   v
GET /private
   |
   v
RememberMeAuthenticationFilter + RememberMeServices
   |
   v
Tự tạo RememberMeAuthenticationToken hợp lệ theo policy
   |
   v
User thấy như thể chưa từng logout
~~~

Vì vậy cấu hình logout phải tích hợp **`RememberMeServices.logout(...)`** phù hợp; chỉ xóa cookie session là chưa đủ. Với remember-me mặc định thông qua DSL `rememberMe(...)`, Spring Security có thể kết nối remember-me services vào quy trình logout chuẩn.

### Token-based remember-me

`TokenBasedRememberMeServices` có thể tạo cookie chứa dữ liệu cần xác minh bằng khóa/chữ ký theo implementation. Nó khác session cookie: session có thể chết trong khi remember-me vẫn có hiệu lực. Đăng xuất cần làm cookie remember-me phía browser hết hạn. Tuy nhiên với cơ chế **stateless token-based**, việc xóa cookie trên thiết bị hiện tại **không nhất thiết thu hồi ngay các bản sao token nếu chúng đã bị sao chép**; server thường không có record riêng cho từng token để revoke tức thì. Cần xem mô hình đe dọa, key rotation, password change hoặc kiến trúc thu hồi phù hợp nếu sản phẩm đòi hỏi.

Không nhầm cookie remember-me với JWT hoặc refresh token OAuth2. Mỗi cơ chế có nơi lưu/thu hồi khác nhau.

### Persistent remember-me

`PersistentTokenBasedRememberMeServices` có thể dùng `PersistentTokenRepository` để giữ trạng thái token series/token trong database. Trường hợp này server có khả năng **xóa token của người dùng** theo cơ chế service/repository. Sau logout, dữ liệu server và browser cần được cập nhật nhất quán; việc chỉ gửi cookie Max-Age=0 mà giữ token phía DB không đáp ứng mọi chính sách thu hồi.

Một implementation có thể loại các remember-me tokens theo **username** khi logout, ảnh hưởng nhiều thiết bị; chính sách thực tế phải được hiểu, kiểm thử và thiết kế rõ. Không nên hứa “logout thiết bị này chỉ revoke một cookie” hoặc “logout mọi thiết bị” khi chưa kiểm tra implementation và logic bổ sung.

### So sánh hai loại

| Thuộc tính | Token-based remember-me | Persistent remember-me |
| --- | --- | --- |
| Nơi quyết định tính hợp lệ | Dữ liệu cookie + secret/password theo implementation | Dữ liệu cookie và bản ghi repository |
| Cookie bị xóa ở browser | Ngừng auto-login trên browser đó khi cookie không còn | Ngừng auto-login trên browser đó |
| Thu hồi token đã bị sao chép | Không mặc nhiên có danh sách revoke từng token | Có thể hỗ trợ qua server-side repository |
| Logout chuẩn | Nhớ gọi/cấu hình RememberMeServices và clear cookie | RememberMeServices + repository cleanup theo policy |
| Nhiều thiết bị | Không mặc định invalidates mọi bản sao token | Phụ thuộc cách repository xóa tokens của username/series |

### Remember-me cookie name và thời hạn

Tên thường thấy là `remember-me`, nhưng có thể custom. Nếu ứng dụng đổi tên, lệnh `deleteCookies("remember-me")` sẽ không xóa cookie custom. Cần cấu hình **đồng nhất tên cookie khi phát hành và xóa**, xác định Path/Domain và hạn sử dụng, kiểm thử request thật.

Không lưu password trong cookie tự xây, không đưa user role/client-authenticated state vào remember-me token tin cậy nếu server chưa verify, không log cookie remember-me.

## 5. Ví dụ Spring Boot 3: form login, remember-me và logout

Ví dụ sau dùng **HttpSession + form login + remember-me token-based**, tài khoản demo trong bộ nhớ. Khi user logout, cấu hình Spring Security xử lý context/session, remember-me service và gửi yêu cầu browser xóa JSESSIONID. Đây là ví dụ cho môi trường học tập, không phải sẵn sàng production.

### 5.1. Dependencies Maven

Trong project Spring Boot có parent/BOM và build plugin tương thích, dùng:

~~~xml
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
~~~

Java source bên dưới yêu cầu classpath từ Spring Boot và Spring Security; **không chạy được chỉ với javac từ JDK trống**. Một ví dụ Java 17 độc lập nằm ở mục 12.

### 5.2. Main class

Tạo `src/main/java/com/example/logout/LogoutApplication.java`:

~~~java
package com.example.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig

Tạo `src/main/java/com/example/logout/SecurityConfig.java`:

~~~java
package com.example.logout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
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
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {

        // Secret dùng cho chữ ký remember-me, không hardcode production.
        String rememberMeKey = System.getenv("DEMO_REMEMBER_ME_KEY");
        if (rememberMeKey == null || rememberMeKey.isBlank()) {
            throw new IllegalStateException(
                "Set DEMO_REMEMBER_ME_KEY for local demo");
        }

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/private")
                .permitAll())
            .rememberMe(remember -> remember
                .key(rememberMeKey)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessUrl("/login?logout")
                .permitAll());

        // CSRF được giữ bật theo mặc định của Spring Security.
        return http.build();
    }
}
~~~

**Lưu ý cấu hình:**

1. `formLogin(...)` xử lý POST /login và có thể cung cấp trang đăng nhập mặc định. Nếu user chọn ô remember-me, form gửi tham số `remember-me` và remember-me service cấp cookie khi authentication thành công.
2. `rememberMe.key(...)` dùng secret do môi trường cung cấp; không dùng giá trị cố định yếu trong production. Ứng dụng thực cần quản lý secret từ secret manager, rotation và kế hoạch migration tương thích.
3. `rememberMe.userDetailsService(users)` cho cơ chế remember-me biết cách tải lại user khi cần.
4. `logout.invalidateHttpSession(true)` và `clearAuthentication(true)` làm rõ dọn trạng thái session/context.
5. `deleteCookies("JSESSIONID")` yêu cầu browser xóa cookie phiên nếu tên/phạm vi khớp. Đây là **bước bổ sung**, không phải thay thế session invalidation.
6. Vì remember-me được cấu hình qua Spring Security DSL, cơ chế logout chuẩn có thể gọi `RememberMeServices.logout(...)` để cancel cookie remember-me. Không cần tự chế một endpoint xóa remember-me cookie mà bỏ qua service.
7. `logoutSuccessUrl("/login?logout")` điều hướng sau khi logout thành công. Trang này không được yêu cầu session cũ; `permitAll()` hỗ trợ truy cập logout-related URLs.
8. CSRF không bị tắt. Người dùng cần gửi **POST /logout có CSRF token hợp lệ**. GET /logout không nên được dùng làm “đường tắt” phá session.

**Caveat về version:** Spring Security 6.x có một số khác biệt API/constructor/configuration theo minor version; sử dụng BOM tương thích của Spring Boot và kiểm thử với thư viện dự án. Một số ứng dụng Spring Session dùng cookie tên `SESSION` thay vì `JSESSIONID`; khi đó phải điều chỉnh cookie deletion đúng tên và scope, không copy nguyên lệnh một cách máy móc.

### 5.4. Controller để thử logout

Tạo `src/main/java/com/example/logout/Pages.java`:

~~~java
package com.example.logout;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class Pages {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    public String privatePage(Principal principal) {
        return "private for " + principal.getName();
    }
}
~~~

Tất cả method trả text; trang mặc định /login được framework tạo cho form login nếu không custom login page. Khi session không còn, truy cập /private có thể redirect tới /login thay vì gọi controller.

### 5.5. application.properties

Tạo `src/main/resources/application.properties` cho demo:

~~~properties
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
# HTTPS production cần secure cookie và SameSite phù hợp:
# server.servlet.session.cookie.secure=true
~~~

Timeout session 20 phút **không** rút ngắn remember-me cookie 7 ngày; hai cơ chế có vòng đời khác nhau. Nếu browser giữ remember-me cookie, nó có thể tự khôi phục authentication sau khi session hết hạn. Chính vì vậy logout cần cancel remember-me, không chỉ invalidate session.

### 5.6. Chạy demo

Dùng biến môi trường local không chứa secret production:

~~~bash
# Chỉ dùng trong môi trường phát triển, ví dụ Unix-like shell.
export DEMO_REMEMBER_ME_KEY='random-local-demo-key-not-for-production'
./mvnw spring-boot:run
~~~

Mở http://localhost:8080/login, đăng nhập Alice bằng `demo-only-password`, có thể đánh dấu “Remember me”. Trong browser DevTools, quan sát các cookie trước/sau logout **chỉ ở môi trường local**, không copy giá trị cookie thật ra ticket, chat hoặc log. Sau logout, request /private bằng cookie cũ không được lấy lại Authentication nhờ session đã bị hủy hoặc remember-me token đã bị cancel.

Nếu cookie bị xóa mà /private vẫn tự login lại, kiểm tra xem browser còn một remember-me cookie **khác path/domain** hoặc ứng dụng dùng một cơ chế authentication thứ hai (SSO, Bearer token, proxy auth). Không chỉ nhìn response 302 rồi kết luận logout đã hoàn tất.

## 6. CookieClearingLogoutHandler và việc xóa cookie đúng phạm vi

Spring Security hỗ trợ `CookieClearingLogoutHandler`, thường được cấu hình qua `logout().deleteCookies(...)`. Hãy coi nó là cách **tạo response yêu cầu browser expire cookie**, không phải API thu hồi session server.

~~~java
// Fragment: xóa thêm cookie theo các tên ứng dụng thực sự sử dụng.
http.logout(logout -> logout
    .deleteCookies("JSESSIONID", "my-app-pref"));
~~~

`my-app-pref` là cookie giả định phục vụ ứng dụng minh họa. **Không xóa tùy tiện** cookie analytics, consent, accessibility preference hoặc cookie của ứng dụng khác chỉ vì người dùng logout; phải xác định dữ liệu nào thật sự nhạy cảm hoặc dùng để authentication.

### Khi cần custom cookie deletion

Nếu cookie được phát hành với Path/Domain đặc thù, có thể dùng custom LogoutHandler đặt chính xác các thuộc tính. Fragment:

~~~java
// Fragment bên trong cấu hình Spring Security, imports được bổ sung
// theo project: jakarta.servlet.http.Cookie, LogoutHandler, v.v.
LogoutHandler expireCustomCookie = (request, response, auth) -> {
    Cookie cookie = new Cookie("MY_SESSION", "");
    cookie.setPath("/portal");
    cookie.setMaxAge(0);
    cookie.setHttpOnly(true);
    cookie.setSecure(request.isSecure()); // phù hợp khi ứng dụng dùng HTTPS
    response.addCookie(cookie);
};
~~~

Đoạn này **chỉ là ví dụ cho host-only cookie Path=/portal**. Nếu cookie gốc có Domain, cần set Domain khớp. `request.isSecure()` có thể không phản ánh HTTPS ngoài reverse proxy nếu forwarded headers chưa được cấu hình tin cậy; trên production HTTPS, nên dựa vào cookie policy đã biết thay vì suy đoán thuộc tính cookie từ một request header không đáng tin. Browser có thể không xóa cookie nếu thuộc tính không hợp lệ hoặc phạm vi không khớp.

Kết nối vào logout DSL:

~~~java
http.logout(logout -> logout
    .addLogoutHandler(expireCustomCookie));
~~~

`expireCustomCookie` được khai báo trong scope hoặc dưới dạng bean do ứng dụng tạo. Đừng thay toàn bộ LogoutFilter bằng một controller tự viết chỉ để gửi Set-Cookie; cách đó dễ bỏ sót các LogoutHandler mặc định của framework.

## 7. Cookie CSRF, XSRF-TOKEN và logout

Spring Security có thể lưu CSRF token bằng `HttpSessionCsrfTokenRepository` hoặc `CookieCsrfTokenRepository`. Cả hai đều cho request POST/PUT/DELETE dùng token phù hợp; cookie-based repo có thể phát cookie tên `XSRF-TOKEN` theo cấu hình.

Điều cần phân biệt:

- Cookie `JSESSIONID` dùng để tham chiếu session (trong mô hình thường gặp).
- Cookie `remember-me` dùng để tái xác thực trong một thời gian dài nếu phù hợp.
- Cookie `XSRF-TOKEN` có thể dùng để frontend lấy/gửi token chống CSRF; **nó không phải một session ID và không phải remember-me credential**.

Spring Security có `CsrfLogoutHandler` để xóa CSRF token đã lưu khi logout trong cấu hình thích hợp. Với SPA dùng `CookieCsrfTokenRepository`, logout có thể khiến token CSRF trước đó không còn hợp lệ và frontend phải lấy token mới cho các tương tác tiếp theo.

### Có nên deleteCookies("XSRF-TOKEN")?

Không mặc định cần. Với cookie-based CSRF repo, cleanup token có thể đã do repository/handler xử lý. Việc xóa thêm cookie không đồng bộ với trạng thái server có thể khiến frontend có token stale hoặc mất khả năng POST tiếp sau logout. Hãy:

1. Xác định repo CSRF và tên/path/domain token thực tế.
2. Test response/logout xóa CSRF token đúng cách.
3. Cho frontend lấy CSRF token mới khi cần hiển thị/submit login, thay vì dùng lại token trước logout.
4. Không tắt CSRF toàn cục chỉ để thao tác logout dễ hơn khi browser vẫn dựa vào cookie.

**CSRF và CORS không giống nhau.** CORS kiểm soát những script từ origin khác đọc/gửi các loại request theo quy tắc browser; nó không thay thế cơ chế chống cross-site action qua cookie-based authentication.

## 8. Clear-Site-Data: xóa dữ liệu trình duyệt bằng response header

HTTP response header `Clear-Site-Data` có thể yêu cầu browser dọn một số nhóm dữ liệu web site. Directive thường gặp:

~~~http
Clear-Site-Data: "cache", "cookies", "storage"
~~~

Ý nghĩa khái quát:

| Directive | Dữ liệu hướng tới | Rủi ro/cần lưu ý |
| --- | --- | --- |
| `"cache"` | Một số dạng browser cache cho site | Có thể tăng thời gian tải lại |
| `"cookies"` | Cookies thuộc phạm vi do chuẩn/browser quy định | Có thể ảnh hưởng **nhiều app trên cùng domain hoặc subdomain** |
| `"storage"` | Dữ liệu site như localStorage, IndexedDB và những storage được hỗ trợ | Có thể xóa dữ liệu offline/người dùng chưa đồng bộ |
| `"executionContexts"` | Yêu cầu làm mới/ngừng các execution contexts theo hỗ trợ browser | Tác động UX rộng; không mặc định cần cho mọi logout |

**Không nên bật mọi directive vô điều kiện.** Directive `"cookies"` có thể tác động cookie của những ứng dụng khác nằm trên cùng registrable domain, tùy quy tắc và browser. Directive `"storage"` có thể xóa dữ liệu offline/PWA và trạng thái khác ngoài login. Các browser khác nhau có mức độ hỗ trợ khác nhau, và header thường được thực thi trong **secure context (HTTPS)**; kiểm thử tương thích, đặc biệt khi phát triển trên localhost và reverse proxy.

Đối với ứng dụng chỉ cần dọn session và remember-me, thường **không cần** Clear-Site-Data. Nếu hệ thống có chính sách dọn dữ liệu site sau logout và người dùng hiểu tác động, có thể chọn directive hẹp.

### Tùy chọn bổ sung trong Spring Security

Khi đã quyết định cleanup browser cache/storage và đã đánh giá phạm vi tác động, ứng dụng có thể gắn một LogoutHandler gửi header:

~~~java
// Fragment: chỉ áp dụng nếu policy logout yêu cầu xóa cache/storage.
// Đây không phải cấu hình bắt buộc cho mọi ứng dụng.
http.logout(logout -> logout
    .addLogoutHandler((request, response, auth) ->
        response.setHeader(
            "Clear-Site-Data", "\"cache\", \"storage\"")));
~~~

Mã dùng Java string escaping để response thực có giá trị `"cache", "storage"`. Đây là **fragment** đặt trong SecurityFilterChain, không phải file Java độc lập. Với yêu cầu rõ ràng xóa cookies theo Clear-Site-Data, thêm `"cookies"` chỉ sau khi review tác động tới các app khác cùng site, và **vẫn thực hiện server-side invalidation**.

Header chỉ là yêu cầu phía client, không phải cơ chế thu hồi credentials phía server; không bảo đảm mọi browser/phiên bản đều thực thi đầy đủ. Với frontend có data offline quan trọng, cân nhắc thay bằng cleanup chọn lọc theo app keys.

### Cẩn thận với “xóa dữ liệu trình duyệt”

Không thể từ một endpoint logout xóa tùy ý lịch sử duyệt web, cookie của các domain không liên quan, dữ liệu tab của app khác hoặc dữ liệu trình duyệt toàn cục. Browser giới hạn quyền và scope của server script. Khi truyền đạt với người dùng, nên nói chính xác “ứng dụng đã đăng xuất và yêu cầu browser xóa dữ liệu liên quan” thay vì hứa “đã xóa sạch tất cả dấu vết”.

## 9. Frontend nên dọn gì khi logout?

Đăng xuất phía server có thể thành công trong khi giao diện SPA vẫn giữ username, avatar hoặc thông tin nhạy cảm trong state. Vì vậy frontend cần cleanup, nhưng **theo phạm vi ứng dụng và có kiểm soát**.

### 9.1. Dọn app state

Sau response logout thành công hoặc khi session được xác nhận hết hiệu lực:

- Xóa cached user profile và permission trong state store.
- Xóa access token/refresh token **nếu kiến trúc của bạn đang lưu phía frontend**; ưu tiên thiết kế không để long-lived credentials trong localStorage khi có thể.
- Xóa cache của request authenticated để tránh hiển thị dữ liệu user trước cho user tiếp theo.
- Dừng request/polling cần authenticated state, đóng subscription/WebSocket tương ứng.
- Đồng bộ trạng thái logout giữa nhiều tab của cùng origin theo policy frontend.

Một ví dụ **JavaScript frontend fragment**:

~~~javascript
async function logoutCurrentUser(csrfToken) {
  const response = await fetch("/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-TOKEN": csrfToken }
  });

  if (!response.ok && !response.redirected) {
    // Không tự khẳng định server đã logout nếu request bị chặn.
    throw new Error("Logout did not complete");
  }

  // Dọn các key đúng của ứng dụng; KHÔNG gọi localStorage.clear()
  // nếu cùng origin chứa dữ liệu quan trọng của các module khác.
  sessionStorage.removeItem("app-current-user");
  localStorage.removeItem("app-auth-cache");
  window.location.assign("/login?logout");
}
~~~

Đây là fragment minh họa **không phải SDK đầy đủ**: ứng dụng cần cơ chế lấy CSRF token đúng với repo/handler; fetch auto-follow redirect có thể trả HTML, và kiểm tra `response.redirected` không thay thế việc xác nhận logout thành công theo HTTP contract. Với frontend phức tạp nên cung cấp endpoint/logout response 204 hoặc JSON rõ ràng. Trường hợp request mạng lỗi cần xử lý nhất quán, không “clear UI và tuyên bố đã revoke server session” một cách sai lệch.

### 9.2. Không “dọn sạch mọi storage” theo phản xạ

`localStorage.clear()` và `sessionStorage.clear()` xóa toàn bộ key trong phạm vi storage tương ứng, có thể phá dữ liệu draft/offline hoặc ứng dụng khác cùng origin. Ưu tiên key prefix/name do app sở hữu; nếu sản phẩm bắt buộc xóa hết, cần quyết định UX và backup offline data có ý thức.

### 9.3. Tab cũ và Back/Forward Cache

Logout không thể tự làm mọi DOM đã render trong tab khác biến mất ngay. Sau khi người dùng logout rồi nhấn Back, browser có thể hiển thị một snapshot trang cũ từ back/forward cache (bfcache). Trang nhạy cảm nên có chính sách cache và logic kiểm tra session ở các thời điểm thích hợp; quan trọng nhất là server vẫn trả 401/redirect cho **request mới** nếu đã logout.

Các trang/response chứa nội dung nhạy cảm nên xem xét:

~~~http
Cache-Control: no-store
~~~

Spring Security HTTP headers có chính sách cache mặc định cho nhiều response bảo vệ, nhưng không nên giả định mọi trang HTML/API/cache qua CDN đều được áp dụng đúng khi có custom filters/proxies. Kiểm tra header thực tế và cache policy của CDN.

### 9.4. Nhiều tab và cùng origin

Khi logout ở tab A, tab B có thể vẫn hiện user cũ đến khi thực hiện request mới. Có thể dùng `BroadcastChannel` hoặc `storage` event để báo trạng thái logout **không chứa credential** và xóa UI state. Nhưng thông báo giữa tab **không phải bằng chứng bảo mật**; server-side session invalidation/revocation mới chặn request sau.

## 10. Stateless API, Bearer JWT và refresh token: giới hạn của cookie logout

Ứng dụng không dùng HttpSession mà dùng `Authorization: Bearer ...` có bài toán khác. Có thể có:

| Thành phần | Sau logout phải xử lý thế nào? |
| --- | --- |
| Session server | Nếu không có session, không có session để invalidate |
| Access token JWT stateless | Không tự mất hiệu lực chỉ vì browser xóa local copy; cần expiration ngắn hoặc revocation architecture |
| Refresh token | Cần revoke/rotate ở authorization server hoặc token store theo policy |
| Browser storage/cookie chứa token | Xóa cookie/storage đúng phạm vi nhưng không thay thế revocation server |
| OpenID Connect provider session | Có thể cần RP-initiated logout/back-channel/front-channel logout tùy hệ thống |
| API cache chứa user data | Dọn client cache và tránh cache response nhạy cảm |

**Không đưa `deleteCookies("JSESSIONID")` vào resource server stateless rồi coi là đã logout mọi Bearer token.** Token đã phát hành có thể còn hợp lệ tại server cho đến khi hết hạn hoặc bị revoke theo kiến trúc. Nếu ứng dụng federated login, cookie của identity provider ở **origin khác** không thể bị xóa tùy ý bởi logout handler của ứng dụng này.

### Logout mọi thiết bị khác logout thiết bị hiện tại

Một lần logout hiện tại thường invalidate **session hiện tại** và dọn cookie hiện tại. Đăng xuất mọi thiết bị cần cơ chế server-side riêng: quản lý các sessions theo account và registry/session store, revoke refresh tokens, token versions, remember-me repository, event propagation... Một cú `Set-Cookie: Max-Age=0` chỉ gửi tới **browser đang nhận response**, không tác động trực tiếp tới cookie ở thiết bị khác.

Khi sản phẩm yêu cầu “logout everywhere”, cần định nghĩa rành mạch cả session và token/remember-me ở mọi thiết bị, thiết kế transaction/revocation và kiểm thử kỹ. Không tự suy ra Spring Security mặc định đáp ứng toàn bộ.

## 11. Kiểm thử Spring Security logout với MockMvc

Với ứng dụng Spring Boot ở mục 5, nên kiểm tra tối thiểu:

1. POST /logout có CSRF token khi user đã login.
2. HTTP response sau logout có redirect/response theo hợp đồng.
3. Session cũ không còn authenticated sau logout.
4. Response có chỉ dẫn hết hạn cookie phiên nếu đã cấu hình.
5. Remember-me cookie được cancel khi remember-me đã được phát hành.
6. POST /logout thiếu CSRF bị chặn theo policy.
7. Không vô tình xóa cookie không liên quan.
8. Việc xóa cookie qua header không thay thế kiểm tra server-side invalidation.

### 11.1. Test session invalidation và cookie expiry

Tạo `src/test/java/com/example/logout/LogoutIntegrationTest.java`:

~~~java
package com.example.logout;

import java.util.List;
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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void logoutInvalidatesSessionAndExpiresSessionCookie()
            throws Exception {

        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk());

        MvcResult out = mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        List<String> cookies =
            out.getResponse().getHeaders("Set-Cookie");

        assertTrue(cookies.stream()
            .anyMatch(v -> v.startsWith("JSESSIONID=") &&
                (v.contains("Max-Age=0") || v.contains("Expires="))));

        // Session bị invalidate ở server, không chỉ xóa cookie client.
        assertTrue(session.isInvalid());

        // Request mới không có session/remember-me cookie -> chưa login.
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void csrfIsRequiredForLogout() throws Exception {
        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
~~~

Test yêu cầu các bean, class, environment key và filter chain của mục 5 được load đúng. Kỳ vọng cookie JSESSIONID được xóa vì đã gọi `deleteCookies("JSESSIONID")`; tên cookie thực có thể khác trong dự án khác. `MockHttpSession.isInvalid()` kiểm tra session mock đã bị invalidate. Một hệ thống dùng Spring Session với store khác nên kiểm tra storage thực, không chỉ MockHttpSession.

**Caveat:** Các assertion không chứng minh browser thật đã nhận/xóa cookie, bởi MockMvc mô phỏng Servlet request/response. Cần kiểm thử trên embedded server/browser với Path/Domain/Secure/SameSite thật để xác nhận cookie biến mất. Kiểm thử remember-me cancel chính xác nên kiểm tra response Set-Cookie cho tên remember-me đã được phát hành hoặc kiểm tra database token repository khi dùng persistent remember-me; phiên bản Spring Security có thể chọn cách serialize/expire cookie khác nhau.

### 11.2. Kiểm thử remember-me đúng nghĩa

Một integration test chặt chẽ nên tạo phiên đã login với option remember-me, ghi nhận Set-Cookie remember-me, sau đó logout **với cùng cookie/session**, xác minh cookie remember-me bị expire và không còn tự login. Với persistent remember-me, kiểm tra `PersistentTokenRepository` không còn chấp nhận token đã logout (và các thiết bị khác theo policy). Không dùng `@WithMockUser` để chứng minh RememberMeServices đã tham gia login/logout: mock principal bỏ qua phần issuance/token validation thật.

Khi dùng authentication ở nhiều thiết bị, cần test ít nhất hai cookie jars độc lập. Nếu hệ thống muốn logout một thiết bị thay vì mọi thiết bị, kiểm tra chính xác phạm vi revoke của implementation.

### 11.3. Kiểm thử header browser storage

Nếu dùng `Clear-Site-Data`, có thể assert response header:

~~~java
// Fragment test khi logout handler có cấu hình header này.
String header = out.getResponse().getHeader("Clear-Site-Data");
assertEquals("\"cache\", \"storage\"", header);
~~~

Đây là fragment nằm trong method test có `out` và static import `assertEquals`. Assertion kiểm tra header được gửi, **không thể chứng minh browser đã thực hiện dọn storage**. Cần browser integration test riêng và xem xét ảnh hưởng tới dữ liệu offline/đa ứng dụng cùng origin.

## 12. Java 17 độc lập: vì sao xóa cookie sai Path không hiệu quả?

Chương trình sau chạy **chỉ bằng JDK 17**. Nó mô phỏng danh tính cookie bằng bộ `(name, path, domain)`. Đây là mô hình đơn giản để hiểu cookie deletion, không phải parser Set-Cookie hay implementation đầy đủ của RFC/browser (cookie domain normalization, prefix rules và public suffix policy phức tạp hơn).

Lưu file `CookieDeletionScopeDemo.java`:

~~~java
public class CookieDeletionScopeDemo {

    record CookieKey(String name, String path, String domain) {}

    static String delete(CookieKey issued, CookieKey expired) {
        if (issued.equals(expired)) {
            return "REMOVED";
        }
        return "STILL_PRESENT";
    }

    public static void main(String[] args) {
        CookieKey session = new CookieKey("JSESSIONID", "/portal", "");
        CookieKey same = new CookieKey("JSESSIONID", "/portal", "");
        CookieKey wrongPath = new CookieKey("JSESSIONID", "/", "");
        CookieKey wrongName = new CookieKey("SESSION", "/portal", "");

        System.out.println("same: " + delete(session, same));
        System.out.println("wrong-path: " + delete(session, wrongPath));
        System.out.println("wrong-name: " + delete(session, wrongName));

        CookieKey rememberMe =
            new CookieKey("remember-me", "/", "example.test");
        CookieKey hostOnly =
            new CookieKey("remember-me", "/", "");

        System.out.println("domain-mismatch: " +
            delete(rememberMe, hostOnly));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CookieDeletionScopeDemo.java
java CookieDeletionScopeDemo
~~~

Stdout **chính xác**:

~~~text
same: REMOVED
wrong-path: STILL_PRESENT
wrong-name: STILL_PRESENT
domain-mismatch: STILL_PRESENT
~~~

Trong browser thật, `Max-Age=0` hoặc `Expires` quá khứ mới là tín hiệu hết hạn. Mô hình chỉ xác nhận vì sao **name, path và domain** phải đồng nhất; không mô phỏng thời gian, Domain matching theo browser hay cookie prefix constraints. Quan trọng hơn, ngay cả khi cookie bị xóa đúng, server vẫn cần hủy session và token/remember-me theo policy.

## 13. Lỗi thực tế và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
| --- | --- | --- |
| Logout 302 nhưng /private vẫn truy cập được | Session/context không bị invalidate, request có authentication khác | Kiểm tra LogoutFilter, SecurityContextRepository, remember-me, Bearer/SSO |
| JSESSIONID vẫn xuất hiện trong browser | Set-Cookie xóa sai name/path/domain, browser chưa nhận response | So sánh Set-Cookie trước/sau và cookie scope thật |
| Cookie hết mà login vẫn tự khôi phục | remember-me cookie còn hoặc SSO tự login | Kiểm tra RememberMeServices và IdP |
| Nhấn logout trả 403 | POST thiếu/CSRF token sai | Giữ CSRF, gửi token hợp lệ; kiểm tra repo và request |
| GET /logout không thực hiện logout | CSRF bật, GET thường là confirmation page | Dùng POST có CSRF |
| Logout chỉ một tab, tab khác vẫn hiện dữ liệu | Frontend state/bfcache còn | Đồng bộ tab, xóa app cache, revalidate session |
| Cookie XSRF-TOKEN còn/đổi sau logout | Chính sách CSRF repository/renewal khác | Kiểm tra CsrfLogoutHandler và token repo |
| Clear-Site-Data không có tác dụng | Browser không hỗ trợ, HTTP không secure hoặc phạm vi khác | Test trên HTTPS/browser phù hợp; dùng cleanup frontend |
| Clear-Site-Data xóa cả dữ liệu app khác | Directive cookies/storage quá rộng | Thu hẹp directives và xem xét shared domain |
| Sau logout user bị tự login qua OAuth2 SSO | IdP session độc lập còn hợp lệ | Thiết kế RP-initiated logout và kiến trúc SSO |
| Logout thiết bị A nhưng token ở B vẫn dùng được | Chỉ clear cookie của A, chưa revoke token B | Phân biệt logout local vs logout everywhere |
| Dùng CookieClearingLogoutHandler mà session chưa mất | Chỉ xử lý browser cookie | Đảm bảo SecurityContextLogoutHandler thực thi |
| Response nhạy cảm vẫn xem được khi nhấn Back | Browser bfcache/cache giữ snapshot | Cache-Control no-store, revalidation và UI cleanup |
| Cùng tên JSESSIONID có hai cookie | Khác Path/Domain | Kiểm tra DevTools cookie table và các Set-Cookie |
| Persistent remember-me vẫn chấp nhận token | Server repository token chưa được revoke | Kiểm tra RememberMeServices.logout và repo cleanup |

### Quy trình debug có hệ thống

1. Kiểm tra request logout tới đúng **SecurityFilterChain** và matcher/HTTP method. Với CSRF bật, request có token hợp lệ chưa?
2. Xác minh response từ server (status, `Location`, `Set-Cookie`, `Clear-Site-Data` nếu dùng). Không chỉ dựa vào giao diện hiển thị.
3. Đảm bảo server session cũ đã bị invalidate hoặc SecurityContext đã bị dọn theo policy. Kiểm tra thử request mới bằng cookie/session cũ có còn authenticated không.
4. Kiểm tra remember-me services đã tham gia logout; nếu persistent, kiểm tra token store và phạm vi revoke.
5. So sánh cookie name, Path, Domain, Secure/host-only của **cookie được phát hành** và **cookie xóa**.
6. Xác định frontend đang giữ những app keys, memory state, API cache và nhiều tab nào.
7. Nếu còn tự login, xác định authentication source: remember-me, SSO IdP, token Bearer khác hay proxy auth.
8. Kiểm tra browser khác nhau, HTTPS, reverse proxy, context path và CORS/cookie SameSite khi cần.
9. Không log/copy raw session ID, remember-me token, JWT, password, user object chứa credentials vào báo cáo sự cố.

## 14. Bài tập tự kiểm tra

**Bài 1.** Ứng dụng gọi `deleteCookies("JSESSIONID")` nhưng không invalidate HttpSession. Điều gì còn thiếu?

**Đáp án:** Xóa cookie client không chắc đã hủy session phía server. Cần logout handler dọn SecurityContext và invalidate session theo policy. Một session ID đã bị lộ hoặc còn ở nơi khác có thể cần được server từ chối.

**Bài 2.** Browser được cấp JSESSIONID `Path=/portal`; response logout chỉ phát cookie xóa `Path=/`. Cookie cũ có biến mất không?

**Đáp án:** Không thể coi là đã xóa; name/path/domain phải khớp scope của cookie ban đầu. Cần kiểm tra header phát hành và dùng cùng Path/Domain khi expire.

**Bài 3.** Sau logout, user vào /private và ứng dụng ngay lập tức nhận ra họ nhờ remember-me. Đó là lỗi gì?

**Đáp án:** Có thể remember-me cookie/token chưa được cancel đúng. Chỉ hủy session chưa đủ khi remember-me vẫn hoạt động; cần RememberMeServices.logout và xử lý token repository phù hợp.

**Bài 4.** Vì sao xóa cookie remember-me trên browser không bảo đảm revoke một bản sao token stateless đã bị đánh cắp?

**Đáp án:** Server không nhất thiết duy trì record riêng cho từng token stateless để vô hiệu hóa tức thì. Cần chính sách revocation, key rotation/password change hoặc kiến trúc server-side token khi threat model yêu cầu.

**Bài 5.** Một app dùng login qua cookie và CSRF bật. Developer chuyển logout thành GET /logout cho tiện. Rủi ro?

**Đáp án:** Có thể tạo logout-CSRF và không phù hợp flow Spring Security. Nên dùng POST /logout với CSRF token hợp lệ, không tắt CSRF toàn cục cho cookie-based authentication.

**Bài 6.** Vì sao không nên gửi `Clear-Site-Data: "cookies", "storage"` cho mọi site trên một domain dùng chung?

**Đáp án:** Directive có thể ảnh hưởng cookie của app khác và xóa dữ liệu offline/storage dùng chung. Cần đánh giá phạm vi và hỗ trợ browser; ưu tiên cleanup tối thiểu đúng yêu cầu.

**Bài 7.** User logout rồi browser Back vẫn hiển thị trang cá nhân cũ. Có chắc server vẫn authenticated không?

**Đáp án:** Không. Browser có thể hiện snapshot từ cache/bfcache. Phải thử request mới tới endpoint bảo vệ và xử lý cache/frontend theo policy, không nhầm UI cũ với session server còn sống.

**Bài 8.** Một resource server xác thực JWT Bearer, frontend xóa localStorage token khi logout. Token đã phát hành hết hiệu lực ngay tại resource server chưa?

**Đáp án:** Không mặc nhiên. JWT vẫn có thể hợp lệ cho đến expiry hoặc bị revoke theo kiến trúc. Logout phải thiết kế riêng cho access/refresh tokens và authorization server.

**Bài 9.** Frontend có dữ liệu draft offline chưa đồng bộ. Có nên dùng `localStorage.clear()` sau logout?

**Đáp án:** Không nên mặc định. Dọn các key authentication/sensitive thuộc app, cân nhắc dữ liệu draft/offline và chính sách user consent. Directive storage rộng cũng cần xem xét hậu quả tương tự.

**Bài 10.** Một cửa sổ logout thành công nhưng cửa sổ khác trong cùng origin chưa cập nhật giao diện. Đâu là giải pháp?

**Đáp án:** Có thể dùng BroadcastChannel hoặc storage events để đồng bộ UI và dọn cache giữa tabs; nhưng server vẫn phải invalidate session/revoke tokens để bảo vệ request tiếp theo.

## 15. Checklist triển khai logout an toàn

- [ ] Xác định session-based form login, remember-me, SSO hay Bearer token; không áp một cookie logout recipe cho mọi kiến trúc.
- [ ] Đảm bảo LogoutFilter, SecurityContextLogoutHandler và các logout handlers đúng đã chạy, server session/context bị dọn theo policy.
- [ ] POST /logout có CSRF token khi browser dựa vào session cookie; không tự tắt CSRF.
- [ ] Xóa cookie phiên đúng **tên/Path/Domain**, xác minh response Set-Cookie ở browser/HTTPS thật.
- [ ] Nếu bật remember-me, kiểm tra RememberMeServices.logout, remember-me cookie và persistent token repository; phân biệt token-based/stateless với persistent.
- [ ] Đừng coi cookie deletion là token revocation; thiết kế logout mọi thiết bị riêng nếu sản phẩm yêu cầu.
- [ ] Hiểu CsrfLogoutHandler và CookieCsrfTokenRepository nếu dùng XSRF-TOKEN; đảm bảo frontend nhận token mới đúng lúc.
- [ ] Chỉ dùng Clear-Site-Data directives phù hợp sau khi review tác động tới shared domain, offline data và browser support.
- [ ] Dọn app state/cache/storage **chọn lọc**; đồng bộ UI nhiều tab; không xóa dữ liệu không liên quan.
- [ ] Bảo vệ API/private pages khỏi cache không phù hợp và kiểm thử browser Back/bfcache.
- [ ] Kiểm thử login → remember-me → logout → request mới, cookie stale, cookie Path/Domain khác, CSRF, multi-tab, SSO/JWT nếu có.
- [ ] Không log credentials, JWT, raw session ID, remember-me token hay sensitive browser state.

**Kết luận:** Logout an toàn phải kết hợp **hủy trạng thái xác thực ở server**, **yêu cầu browser làm hết hạn đúng cookie**, **cancel remember-me và thu hồi token theo kiến trúc**, rồi **dọn dữ liệu frontend có chọn lọc**. `deleteCookies("JSESSIONID")` hữu ích nhưng không tự hủy session hay remember-me token; `Clear-Site-Data` hữu ích trong một số hệ thống nhưng không phải thao tác mặc định an toàn cho mọi website. Kiểm thử cả server lẫn browser với đúng cookie scope là cách xác nhận người dùng thật sự đã đăng xuất.