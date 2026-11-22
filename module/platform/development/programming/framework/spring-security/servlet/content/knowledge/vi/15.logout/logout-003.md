# Vô hiệu hóa HttpSession và xóa Authentication khỏi SecurityContext trong Spring Security Servlet

**Ngữ cảnh:** Java 17+, Spring Security 6.x, Spring Boot 3.x và Jakarta Servlet. Bài thuộc chủ đề **Đăng xuất**. Mục tiêu là hiểu điều gì thực sự diễn ra khi người dùng đăng xuất khỏi ứng dụng dùng cookie/session, phân biệt xóa authentication trong request với hủy session phía server, cấu hình logout chuẩn và kiểm thử rằng request sau không còn được xem là đã đăng nhập.

**Tình huống:** người dùng đã đăng nhập qua form login, server lưu một <code>SecurityContext</code> có <code>Authentication</code> trong <code>HttpSession</code>; browser gửi cookie <code>JSESSIONID</code> ở các request tiếp theo. Nếu chỉ xóa một biến ở frontend hoặc redirect về trang login, session server có thể vẫn hợp lệ, khiến trình duyệt tiếp tục được nhận dạng khi gửi lại cookie.

Nguyên tắc quan trọng: **đăng xuất đúng là làm mất hiệu lực thông tin xác thực đã được server chấp nhận**, không chỉ ẩn giao diện hay xóa tên người dùng khỏi màn hình.

## 1. Ba trạng thái thường bị nhầm với nhau

| Đối tượng | Được lưu ở đâu? | Tác dụng |
| --- | --- | --- |
| <code>Authentication</code> | Nằm trong <code>SecurityContext</code> của request hoặc phiên | Danh tính, authorities và trạng thái xác thực được Spring Security sử dụng để phân quyền. |
| <code>SecurityContext</code> | Được truy cập qua <code>SecurityContextHolder</code>, có thể được lưu bằng <code>SecurityContextRepository</code> | Bao bọc Authentication hiện hành và hỗ trợ nạp/lưu cho request sau. |
| <code>HttpSession</code> | Servlet container hoặc kho session server-side; thường được tham chiếu bởi <code>JSESSIONID</code> | Chứa trạng thái liên phiên, có thể bao gồm SecurityContext và dữ liệu ứng dụng. |

Phải phân biệt **clear context**, **invalidate session** và **xóa cookie**:

- <code>SecurityContextHolder.clearContext()</code> loại context khỏi strategy đang dùng cho luồng xử lý hiện tại. Nó không tự duyệt các session đã lưu trước đó để xóa.
- <code>request.getSession(false).invalidate()</code> hủy **một HttpSession hiện tại**, xóa các attribute bên trong và làm session ID ấy không còn trỏ đến phiên hợp lệ. Nó không tự dọn context còn giữ trong request/thread nếu không được xử lý tương ứng.
- Xóa cookie <code>JSESSIONID</code> ở browser khiến client không gửi lại ID cũ, nhưng **không phải bằng chứng server đã hủy phiên**. Một ID bị sao chép ở nơi khác vẫn có thể dùng được nếu session server chưa vô hiệu.

Một logout handler chuẩn của Spring Security thực hiện những thao tác liên quan một cách nhất quán, thay vì để controller chỉ làm một nửa.

## 2. Lần theo một request trước và sau đăng xuất

Trước khi logout:

~~~text
Browser                          Servlet / Spring Security
  | Cookie: JSESSIONID=S1                   |
  | GET /me                                |
  |---------------------------------------->|
  |                    SecurityContextRepository lấy context
  |                    Authentication(name=alice, authenticated)
  |                    AuthorizationFilter cho phép
  |<----------------------------------------|
  | 200, body alice                         |
~~~

Khi logout:

~~~text
Browser                          Servlet / Spring Security
  | POST /logout + Cookie S1 + CSRF token  |
  |---------------------------------------->|
  |                    CsrfFilter xác minh request
  |                    LogoutFilter nhận diện /logout
  |                    LogoutHandlers chạy:
  |                      - invalidate HttpSession S1
  |                      - clear SecurityContext
  |                      - clear authentication / lưu context rỗng
  |                      - dọn cookie, remember-me nếu cấu hình
  |                    LogoutSuccessHandler quyết định response
  |<----------------------------------------|
  | 302 Location: /login?logout            |
~~~

Request sau logout:

~~~text
Browser vẫn thử gửi JSESSIONID=S1
  |
  v
Server không còn HttpSession S1 hợp lệ
  |
SecurityContext không nạp được Authentication cũ
  |
GET /me phải xác thực lại
  |
302 đến /login (ví dụ form login)
~~~

Điều cần kiểm thử không phải chỉ là server trả “logout successful”, mà còn là **session đã bị invalidate** và **request sau với trạng thái cũ không thể đọc tài nguyên riêng tư**.

Lưu ý: HTTP status phụ thuộc cơ chế authentication. Form login thường redirect 302, REST API thường dùng 401 cho anonymous. Đừng áp dụng máy móc 302 của form login cho mọi API.

## 3. Spring Security logout theo cơ chế mặc định

Spring Security có <code>LogoutFilter</code> trong <code>SecurityFilterChain</code>, chuyên nhận diện URL đăng xuất và chạy các <code>LogoutHandler</code>. Các thành phần phổ biến:

- <code>SecurityContextLogoutHandler</code>: xử lý clear authentication, clear context và invalidate HttpSession theo cấu hình; đồng thời phối hợp <code>SecurityContextRepository</code> để tránh giữ lại context đã logout.
- <code>CookieClearingLogoutHandler</code>: gửi header/cookie hết hạn để browser ngừng gửi các cookie đã chỉ định, nếu cấu hình.
- <code>LogoutSuccessHandler</code>: quyết định phản hồi sau khi các logout handler chạy, ví dụ redirect tới trang login hoặc trả HTTP 204.
- Remember-me logout handler (nếu remember-me được cấu hình): dọn credential remember-me cần thiết khi logout.
- <code>HttpSessionEventPublisher</code> (khi được đăng ký): đưa các sự kiện hủy session của Servlet container vào Spring application context để những cơ chế như <code>SessionRegistry</code> có thể dọn trạng thái.

Trong cấu hình form login và CSRF mặc định, thao tác logout là **POST /logout** có CSRF token hợp lệ. Một số trang generated login của Spring Security có thể hiển thị trang xác nhận khi truy cập <code>GET /logout</code>, nhưng GET không nên tự thực hiện thao tác đăng xuất có tác dụng thay đổi trạng thái.

### Một số cấu hình có default an toàn

~~~java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessUrl("/login?logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
    .permitAll());
~~~

Mã trên là **đoạn nằm trong bean SecurityFilterChain**, chưa phải class độc lập. Trong Spring Security, vô hiệu session và xóa authentication vốn đã là hành vi mặc định thường dùng của <code>SecurityContextLogoutHandler</code>; ở đây khai báo tường minh để thấy các quyết định.

<code>.deleteCookies("JSESSIONID")</code> hỗ trợ dọn cookie ở phía browser, nhưng việc xóa cookie hiệu quả còn phụ thuộc Path/Domain của cookie do browser lưu và đường đi proxy. **Không dùng xóa cookie làm biện pháp thay thế cho invalidation ở server.**

<code>.permitAll()</code> bảo đảm các URL liên quan logout/success có quyền truy cập phù hợp; **nó không tắt CSRF**. URL logout có thể được <code>LogoutFilter</code> xử lý trước <code>AuthorizationFilter</code>, nên không nên cố sửa lỗi bằng cách bỏ bảo vệ CSRF hoặc mở rộng mọi route thành <code>permitAll("/**")</code>.

## 4. SecurityContextHolder và SecurityContextRepository không phải một thứ

Trong quá trình xử lý request, <code>SecurityContextHolder.getContext()</code> cho phép đọc <code>Authentication</code> hiện tại; strategy mặc định thường gắn context với thread. Ở request kế tiếp, các Spring Security filters có thể dùng <code>SecurityContextRepository</code> để khôi phục context đã được lưu.

Ví dụ minh họa:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

SecurityContextHolder.clearContext();
~~~

Dòng thứ hai **không có nghĩa** context trong HttpSession tự bị xóa. Nếu repository vẫn giữ SecurityContext cũ, một request sau có thể lại nạp Authentication đã xác thực từ session.

Trong Spring Security 6, một số đường đi dùng <code>SecurityContextHolderFilter</code> với chính sách **lưu SecurityContext tường minh**. Nếu tự viết một luồng authentication/logout, cần hiểu <code>SecurityContextRepository</code> thực tế được cấu hình và bảo đảm trạng thái rỗng được lưu hoặc session được hủy phù hợp. Không chỉ gọi <code>setAuthentication(null)</code> trên một context lấy ra rồi hy vọng mọi repository và mọi phiên đều bị xóa.

**Khuyến nghị:** dùng <code>LogoutFilter</code> và <code>SecurityContextLogoutHandler</code> thay vì tự lắp nhiều lời gọi nhỏ để mô phỏng logout.

### Session store sau invalidate

Khi <code>HttpSession.invalidate()</code> thành công, container/session store phải coi session đó là không hợp lệ; các attribute session, kể cả SecurityContext được lưu trong đó, không còn dùng được để xác thực request tiếp theo bằng session ID cũ.

Tuy nhiên, những thao tác bất đồng bộ hoặc service đã giữ tham chiếu dữ liệu riêng có thể còn công việc đang chạy; logout không tự dừng mọi tác vụ đã khởi phát. Nếu có công việc nhạy cảm kéo dài, hệ thống cần cơ chế kiểm soát riêng (ủy quyền tại thời điểm thực hiện, cancellation hoặc kiểm tra lại quyền).

## 5. Khi nào dùng SecurityContextLogoutHandler thủ công?

Spring Security đã cung cấp <code>POST /logout</code>; không cần tự viết controller chỉ để gọi invalidate. Nhưng nếu ứng dụng có một luồng xác thực đặc biệt hoặc một API logout tùy chỉnh, có thể cần gọi <code>SecurityContextLogoutHandler</code> ở **một endpoint được bảo vệ đầy đủ**.

Ví dụ trích đoạn không độc lập:

~~~java
@PostMapping("/account/logout")
public ResponseEntity<Void> logoutCurrent(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication) {

    SecurityContextLogoutHandler handler =
        new SecurityContextLogoutHandler();
    handler.setInvalidateHttpSession(true);
    handler.setClearAuthentication(true);
    handler.logout(request, response, authentication);

    return ResponseEntity.noContent().build();
}
~~~

Ở đây:
- Method được thực thi **sau** khi Spring Security đã xác thực request và kiểm tra CSRF nếu có cơ chế session cookie.
- <code>SecurityContextLogoutHandler.logout()</code> xử lý SecurityContext và HttpSession trong phạm vi request hiện tại, thay vì chỉ gọi <code>request.getSession().invalidate()</code>.
- Nếu ứng dụng dùng remember-me, refresh token hoặc cơ chế logout bổ sung, custom controller phải thực hiện mọi handler cần thiết; ví dụ này **không tự thu hồi token khác**.
- Không mở một URL logout bằng GET để tiện nhấp link, đặc biệt với app dùng cookie/session.
- Nếu dùng <code>SecurityContextRepository</code> tùy chỉnh, cần chắc chắn logout handler phối hợp repository đúng thiết kế.

Ở production, nên tích hợp logic bổ sung thông qua <code>logout.addLogoutHandler(...)</code> hoặc các handler chuẩn hơn là tạo một endpoint thứ hai vô tình có hành vi khác <code>/logout</code>. Khi thêm <code>LogoutHandler</code> gọi dịch vụ bên ngoài, phải thiết kế xử lý lỗi và idempotency phù hợp; logout phía server không nên bị biến thành một yêu cầu có thể giữ session hợp lệ chỉ vì hệ thống audit từ xa tạm thời lỗi.

## 6. Ví dụ chạy được: Spring Boot form login + logout

Dự án ví dụ dùng **Java 17+, Spring Boot 3.3.5, Spring Security 6.x và Maven**. User demo <code>alice</code> đăng nhập bằng form login. Khi gửi <code>POST /logout</code> có CSRF, server invalidate HttpSession, clear Authentication khỏi SecurityContext và redirect về login. Request riêng tư sau đó phải yêu cầu đăng nhập lại.

**Phạm vi demo:** một JVM với HttpSession của embedded Servlet container, account in-memory và mật khẩu thử nghiệm. Không dùng password này hay user store này cho production. Demo không có JWT, refresh token hoặc Identity Provider.

Cấu trúc:

~~~text
spring-logout-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/logoutdemo/
    │       ├── LogoutDemoApplication.java
    │       └── SecurityConfiguration.java
    └── test/
        └── java/com/example/logoutdemo/
            └── LogoutSessionTest.java
~~~

### 6.1. pom.xml

~~~xml
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
    <artifactId>spring-logout-demo</artifactId>
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

### 6.2. Main class và endpoint riêng tư

Tạo <code>src/main/java/com/example/logoutdemo/LogoutDemoApplication.java</code>:

~~~java
package com.example.logoutdemo;

import java.security.Principal;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LogoutDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/private")
    public String privateInfo() {
        return "private-data";
    }
}
~~~

<code>/public</code> có thể đọc khi chưa đăng nhập; <code>/me</code> và <code>/private</code> yêu cầu đã authentication. Không có controller <code>/logout</code>: <code>LogoutFilter</code> của Spring Security nhận request này trực tiếp.

### 6.3. SecurityConfiguration.java

Tạo <code>src/main/java/com/example/logoutdemo/SecurityConfiguration.java</code>:

~~~java
package com.example.logoutdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("local-password-1234"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .permitAll())
            .build();
    }
}
~~~

Phân tích cấu hình:
- Spring Security form login xác minh tài khoản và lưu authentication qua cơ chế session phù hợp; session fixation protection vẫn được framework quản lý.
- <code>anyRequest().authenticated()</code> buộc <code>/me</code> và <code>/private</code> cần đăng nhập.
- <code>logoutUrl("/logout")</code> là endpoint dành cho <code>LogoutFilter</code>, không phải một method MVC.
- <code>invalidateHttpSession(true)</code> hủy HttpSession hiện tại; <code>clearAuthentication(true)</code> làm sạch Authentication trong context.
- <code>deleteCookies("JSESSIONID")</code> giúp browser không giữ cookie session không còn cần thiết. Cookie deletion không thay thế server invalidation.
- <code>logoutSuccessUrl("/login?logout")</code> redirect sau thành công, **không** có nghĩa user vẫn đang authenticated.
- Không có <code>csrf().disable()</code>. Spring Security mặc định yêu cầu CSRF token trên POST, gồm login và logout.
- <code>permitAll()</code> cho phép truy cập các URL logout/success cần thiết, nhưng không cấp quyền truy cập <code>/private</code> cho anonymous.
- <code>PasswordEncoderFactories.createDelegatingPasswordEncoder()</code> tạo password hash có định danh thuật toán, phù hợp với UserDetails trong demo.

Trong sản phẩm thật, dùng tài khoản/credential từ nguồn quản lý danh tính, thiết lập HTTPS, cookie Secure/HttpOnly/SameSite phù hợp, session timeout, audit và ràng buộc quyền của tài nguyên nghiệp vụ.

## 7. Kiểm thử bằng MockMvc: logout phải làm hủy phiên

Tạo <code>src/test/java/com/example/logoutdemo/LogoutSessionTest.java</code>:

~~~java
package com.example.logoutdemo;

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
class LogoutSessionTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "local-password-1234"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void logoutInvalidatesSessionAndRequiresNewAuthentication()
            throws Exception {
        MockHttpSession session = login();

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        // HttpSession đang mang Authentication đã bị invalidate.
        assertThat(session.isInvalid()).isTrue();

        // Request mới không có session đã xác thực phải quay về login.
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfDoesNotDestroySession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertThat(session.isInvalid()).isFalse();

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void logoutOneBrowserDoesNotLogoutOtherBrowser() throws Exception {
        MockHttpSession browserA = login();
        MockHttpSession browserB = login();

        assertThat(browserA.getId()).isNotEqualTo(browserB.getId());

        mvc.perform(post("/logout")
                .session(browserA)
                .with(csrf()))
            .andExpect(redirectedUrl("/login?logout"));

        assertThat(browserA.isInvalid()).isTrue();
        assertThat(browserB.isInvalid()).isFalse();

        mvc.perform(get("/me").session(browserB))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void anonymousAccessRemainsPublicOnly() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Chạy <code>mvn test</code>. Bộ test cần xác minh **ba điều khác nhau**:

1. Logout với session đã đăng nhập và CSRF hợp lệ trả redirect thành công, đồng thời <code>MockHttpSession.isInvalid()</code> trở thành true.
2. Logout thiếu CSRF bị từ chối và session **không** bị hủy. Chỉ kiểm tra status 403 mà không kiểm tra session sẽ bỏ sót khả năng handler chạy sai thứ tự.
3. Logout ở browser A không tự logout browser B: đây là chính sách **logout phiên hiện tại**, không phải “logout everywhere”.

Test cuối kiểm tra đường public/protected. Test <code>get("/private")</code> sau logout tạo request mới không gắn lại phiên cũ; nó minh họa yêu cầu đăng nhập lại, còn <code>isInvalid()</code> mới là bằng chứng trực tiếp session A đã bị hủy trong MockMvc.

**Giới hạn:** MockMvc không mô phỏng hoàn toàn cookie Path/Domain, timeout và sự kiện lifecycle của một Servlet container thật. Để xác minh đầy đủ Set-Cookie và JSESSIONID cũ không dùng được qua mạng, nên bổ sung integration test trên embedded server hoặc staging với hai cookie jars. Mã Java trên được trình bày như ví dụ chạy được, nhưng kết quả cụ thể vẫn cần xác nhận bằng <code>mvn test</code> trên môi trường dự án.

## 8. Thử thủ công bằng trình duyệt và cookie jar

Khởi động:

~~~bash
mvn spring-boot:run
~~~

Truy cập <code>http://localhost:8080/login</code>, đăng nhập bằng <code>alice</code> / <code>local-password-1234</code>, sau đó vào <code>/me</code> để thấy <code>alice</code>. Đăng xuất qua form tạo yêu cầu POST đến <code>/logout</code> có CSRF token hợp lệ. Server chuyển sang <code>/login?logout</code>. Khi truy cập lại <code>/me</code>, browser cần đăng nhập lại.

**Không thử logout chuẩn bằng GET để mong hiệu ứng giống POST.** Với CSRF bật, GET có thể hiển thị trang xác nhận logout, nhưng logout có tác dụng hủy session phải được gửi qua request hợp lệ theo matcher đã cấu hình.

Ví dụ với curl trên Linux/macOS: muốn thử login và logout cần giữ cookie jar **và** truyền CSRF token mà server tạo cho browser/form. Một POST logout trần có cookie nhưng **không có CSRF token** sẽ thường trả 403. Đây là phòng vệ đúng, không phải lỗi bất thường của LogoutFilter.

Nếu test thủ công trên Windows PowerShell, dùng <code>curl.exe</code> để tránh nhầm với alias của PowerShell. Đừng log hoặc chia sẻ nguyên JSESSIONID và CSRF token thu thập từ ứng dụng thật.

### So sánh kết quả trước/sau

| Hành động | Kết quả trong demo |
| --- | --- |
| GET /public khi anonymous | 200, body <code>public</code> |
| GET /me khi anonymous | Redirect tới login |
| POST /login đúng và có CSRF | Authentication thành công, có session |
| GET /me kèm session đã login | 200, body <code>alice</code> |
| POST /logout thiếu CSRF | 403, session vẫn có thể dùng |
| POST /logout có CSRF hợp lệ | Redirect <code>/login?logout</code> và invalidate session |
| GET /me sau logout bằng request không có phiên hợp lệ | Redirect tới login |
| Browser B vẫn có session riêng | Vẫn authenticated, nếu không có chính sách thu hồi khác |

Không suy ra “session đã bị hủy” chỉ từ một response 302 vì redirect có thể do nhiều đường xử lý. Cần đồng thời kiểm tra session validity, SecurityContext và request tiếp theo.

## 9. Vì sao không nên chỉ gọi HttpSession.invalidate()?

Có trường hợp lập trình viên viết:

~~~java
HttpSession session = request.getSession(false);
if (session != null) {
    session.invalidate();
}
return "redirect:/login";
~~~

Đây chỉ là đoạn minh họa logic; không phải endpoint hoàn chỉnh. Nó có thể invalidate session, nhưng **không chủ động dọn SecurityContext của request hiện tại**. Ví dụ một service được gọi sau đó trong cùng request vẫn có thể nhìn thấy Authentication nếu strategy chưa được clear, và logout handlers khác như remember-me cleanup không chạy.

Một sai lầm khác là:

~~~java
SecurityContextHolder.clearContext();
// Không invalidate HttpSession, không xử lý repository đang lưu context.
~~~

Khi request kế tiếp phục hồi SecurityContext từ session store, user có thể lại được xem là authenticated. Tương tự:

~~~java
response.sendRedirect("/login");
// Chỉ đổi vị trí UI, không hủy trạng thái xác thực.
~~~

Điểm khác nhau:
- Hủy HttpSession làm mất session server-side hiện tại nhưng cần dọn context/handlers thích hợp.
- Clear SecurityContext dọn authentication khỏi xử lý hiện tại nhưng chưa chắc vô hiệu hóa bản sao lưu trong session.
- Redirect hoặc xóa cookie chỉ thay đổi client-response, không tự chứng minh trạng thái server không còn hợp lệ.

Hãy dùng <code>SecurityContextLogoutHandler</code> (thông qua built-in LogoutFilter khi có thể) để các trách nhiệm cơ bản được thực hiện nhất quán.

## 10. LogoutFilter, LogoutHandler và LogoutSuccessHandler

Đặt ba loại component đúng vị trí:

~~~text
LogoutFilter: nhận diện request logout hợp lệ
    |
    +--> LogoutHandler #1: SecurityContextLogoutHandler
    |         invalidate session + clear context
    |
    +--> LogoutHandler #2: CookieClearingLogoutHandler (nếu cấu hình)
    |         Set-Cookie / Max-Age=0 cho cookie cần dọn
    |
    +--> LogoutHandler #3: remember-me/token cleanup (nếu cấu hình)
    |         thu hồi loại credential bổ sung
    |
    '--> LogoutSuccessHandler
              redirect /login?logout hoặc trả JSON/204
~~~

Không nhất thiết các handler luôn được chạy theo đúng một thứ tự như hình; framework và cấu hình quyết định chuỗi cụ thể. Điều đáng nhớ là **logout handlers thực hiện side effects**, còn success handler chỉ định phản hồi.

Nếu cần thêm audit:
- Dùng một <code>LogoutHandler</code> riêng được inject vào cấu hình logout, chỉ ghi dữ liệu tối thiểu như account ID, loại sự kiện và thời gian.
- Không log raw session ID, access token, password hoặc cookie.
- Với dịch vụ audit bên ngoài, phân biệt việc gửi event thành công và logout server đã hoàn tất; thiết kế hàng đợi/retry phù hợp nếu yêu cầu audit bền vững.
- Nếu giao thức logout cần invalidate refresh token hoặc IdP session, cần thêm logic riêng và test đúng thứ tự xử lý.

Không nên để một ngoại lệ trong custom handler khiến hệ thống trả “logout thất bại” trong khi một phần session đã bị invalidate và một phần credential còn sống, nếu chưa có kế hoạch bù trừ hay semantics rõ ràng.

## 11. HttpSessionEventPublisher và SessionRegistry sau logout

Nếu ứng dụng dùng <code>SessionRegistry</code> / <code>SessionRegistryImpl</code> để quản lý số phiên đồng thời, <code>HttpSessionEventPublisher</code> thường được đăng ký để phát sự kiện session destroyed từ Servlet container tới Spring Security.

~~~text
POST /logout hợp lệ
       |
SecurityContextLogoutHandler
       |
HttpSession.invalidate()
       |
Servlet container phát sessionDestroyed
       |
HttpSessionEventPublisher -> HttpSessionDestroyedEvent
       |
SessionRegistryImpl loại bản ghi session ID
~~~

Điều này giúp registry không tiếp tục tính một session đã logout là phiên còn hoạt động. Nếu thiếu listener, thông tin cũ có thể tồn tại trong registry và làm chính sách <code>maximumSessions(...).maxSessionsPreventsLogin(true)</code> gây khó cho login sau.

Ví dụ đăng ký listener ở Spring Boot:

~~~java
@Bean
ServletListenerRegistrationBean<HttpSessionEventPublisher> sessionEvents() {
    return new ServletListenerRegistrationBean<>(
        new HttpSessionEventPublisher());
}
~~~

Đây là **trích đoạn configuration**, cần import và bean setup thích hợp; demo phần 6 không bật concurrency nên không cần thêm listener chỉ để logout cơ bản. Không đăng ký publisher hai lần bằng nhiều cơ chế.

**Đừng nhầm <code>SessionInformation.expireNow()</code> với HttpSession.invalidate().** <code>expireNow()</code> đánh dấu một phiên trong registry bị expired; request kế tiếp cần đi qua <code>ConcurrentSessionFilter</code> để xử lý. Hủy HttpSession trực tiếp làm session không còn hợp lệ ở store, còn xóa registry record đơn thuần không có cùng tác dụng.

## 12. Logout một phiên khác với logout mọi thiết bị

Ví dụ người dùng có browser A và B, cả hai đã đăng nhập bằng cùng username:

~~~text
Account alice
  Session A = JSESSIONID:A1
  Session B = JSESSIONID:B2

A gửi POST /logout:
  - HttpSession A invalidated
  - SecurityContext A cleared
  - B vẫn có HttpSession B hợp lệ
~~~

Logout mặc định của Spring Security xử lý **request/session hiện tại**, không mặc định duyệt mọi session của user. Muốn “logout mọi thiết bị”, cần:
- Xác định principal đã được xác minh ở server.
- Tìm mọi session gắn với principal thông qua registry/kho session có index đúng.
- Thu hồi hoặc invalidate những session đó theo semantics mong muốn.
- Xử lý song song những remember-me token, refresh token hoặc kết nối khác nếu ứng dụng có.
- Kiểm thử với hai browser, nhiều node và login/logout đồng thời.

<code>SessionRegistryImpl</code> là bộ nhớ của một JVM; trong hệ thống nhiều replica, nó không tự biết các session của node khác. Spring Session Redis/JDBC có thể hỗ trợ kho session chung; tuy nhiên chỉ thêm shared session store mà vẫn dùng registry in-memory **không tự tạo** chính sách logout everywhere toàn cluster. Phải cấu hình registry/concurrency/revocation tương ứng.

Một phương án thu hồi mạnh hơn dùng <code>securityVersion</code> hoặc <code>credentialsChangedAt</code> lưu theo account và xác minh trạng thái này ở request sau, nhằm ngăn session cũ được chấp nhận kể cả khi một node bỏ lỡ sự kiện revoke. Cần xác định cache freshness, transaction và xử lý failure.

## 13. Remember-me, HTTP Basic, JWT và SSO thay đổi ý nghĩa “đăng xuất”

Không phải hệ thống nào cũng xác thực bằng HttpSession.

| Cơ chế | Logout cần làm gì? | Điều dễ nhầm |
| --- | --- | --- |
| Form login + HttpSession | Invalidate session, clear SecurityContext, xử lý cookie | Xóa browser cookie không đủ nếu server session còn sống. |
| Remember-me | Xóa cookie/token remember-me, có thể thu hồi persistent token ở server | Chỉ xóa JSESSIONID có thể khiến browser được auto-login lại. |
| HTTP Basic | Request sau vẫn có thể tự gửi Authorization header | Invalidate HttpSession không ngăn browser tiếp tục gửi credentials. |
| API dùng bearer JWT | Token đã ký có thể tiếp tục hợp lệ đến khi hết hạn hoặc bị revoke theo thiết kế | Clear SecurityContext của một request không làm token bên client vô hiệu. |
| Refresh token OAuth2 | Revoke refresh token/grant hoặc cơ chế của Authorization Server | Logout local không tự hủy refresh token ở server cấp token. |
| OIDC / SSO | Logout local cùng luồng logout với IdP nếu yêu cầu | Đóng session local không đồng nghĩa session SSO tại IdP đã hết. |
| WebSocket / connection dài | Có thể cần đóng kết nối hoặc kiểm tra lại quyền trên message | Logout HTTP không luôn tự ngắt kết nối đang mở. |

### HTTP Basic

Một browser hoặc client có thể tự tiếp tục gửi <code>Authorization: Basic ...</code> ở request mới. Khi ấy Spring Security xác thực lại trên mỗi request phù hợp, nên thao tác logout session hiện tại **không đảm bảo người dùng sẽ phải nhập lại password**. Muốn chấm dứt quyền dùng credential, phải có chính sách account/credential tương ứng; không thể hứa “logout hết mọi request Basic” bằng <code>clearContext</code>.

### JWT

JWT access token thường được xác minh độc lập với HttpSession. Nếu token chưa hết hạn và server không có revoke check, nó vẫn được chấp nhận dù một request trước đã gọi clearContext. Có thể dùng TTL ngắn, denylist, introspection, token version hoặc thu hồi refresh token tùy kiến trúc. Phải xác minh signature, issuer, audience và thời gian token trước khi xem là đáng tin.

### OIDC / SSO

Một ứng dụng có thể logout thành công khỏi Spring Security nhưng phiên ở Identity Provider vẫn tồn tại. Để logout ở cả hai nơi, cân nhắc RP-initiated logout, front-channel/back-channel logout hoặc cơ chế tương ứng do IdP hỗ trợ. Đây là protocol riêng, không được tự giả định chỉ cần redirect tới trang login local là đủ.

## 14. CSRF, cookie và các mối nguy trong logout

Logout có thể làm gián đoạn phiên làm việc của người dùng; vì vậy với ứng dụng dùng cookie/session, Spring Security thường yêu cầu CSRF cho thao tác logout.

- **POST /logout + token CSRF** giúp request đến từ giao diện hợp lệ và giảm khả năng bị website khác ép browser đăng xuất.
- <code>GET /logout</code> không nên thực hiện hành động hủy trạng thái chỉ vì người dùng lỡ truy cập link; một số cấu hình có trang xác nhận.
- <code>permitAll()</code> cho URL logout liên quan authorization, không bãi bỏ kiểm tra CSRF.
- Cookie <code>HttpOnly</code> giảm rủi ro JavaScript đọc session ID, <code>Secure</code> giới hạn gửi qua HTTPS, SameSite hỗ trợ hạn chế cross-site; chúng **không thay thế CSRF** hay việc server hủy session.
- Nếu frontend khác origin, CORS không phải authorization. Cần cấu hình origin/credentials và cơ chế CSRF theo kiến trúc.
- Browser có thể giữ cache HTML chứa dữ liệu nhạy cảm sau logout; dùng cache headers phù hợp và tránh đưa secret vào client-side storage không bảo vệ.

Tránh logging <code>JSESSIONID</code>, cookie, CSRF token hay access token vào request logs. Session ID là bí mật đủ để chiếm phiên nếu server còn coi nó hợp lệ.

## 15. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Chỉ redirect tới /login | Không hủy Authentication/HttpSession | Dùng LogoutFilter + SecurityContextLogoutHandler. |
| Chỉ gọi <code>SecurityContextHolder.clearContext()</code> | SecurityContext cũ có thể vẫn trong session/repository | Invalidate HttpSession hoặc lưu context rỗng theo chính sách. |
| Chỉ xóa cookie JSESSIONID | Session server có thể còn tồn tại | Invalidate ở server, xóa cookie chỉ là hỗ trợ. |
| Chỉ gọi <code>request.getSession(false).invalidate()</code> | Context request/handlers khác có thể chưa được dọn | Dùng logout handler chuẩn. |
| Dùng <code>request.getSession()</code> trước logout khi không cần | Có thể tạo session mới không mong muốn | Dùng <code>getSession(false)</code> khi chỉ muốn lấy session tồn tại. |
| Dùng GET để logout | Dễ tạo state-changing action không có CSRF | Giữ POST/CSRF và UI phù hợp. |
| Test logout chỉ kiểm tra 302 | Redirect không chứng minh session đã hủy | Assert invalid session và request sau yêu cầu login. |
| Nghĩ logout A tự logout B | Chỉ hủy session A | Thiết kế global/session revocation riêng. |
| Quên remember-me | Browser có thể auto-login lại | Dọn remember-me cookie/token đúng cách. |
| Coi HTTP Basic logout giống session logout | Client vẫn gửi Authorization header | Thiết kế chính sách credential, không hứa logout Basic bằng clearContext. |
| Coi clearContext là revoke JWT | JWT ở client vẫn có thể hợp lệ | Token expiry/revocation/denylist/refresh-token policy. |
| Bỏ qua IdP session của SSO | Người dùng vẫn có phiên SSO | Tích hợp logout protocol của IdP khi cần. |
| Thiếu HttpSessionEventPublisher khi dùng registry | Registry có thể giữ phiên đã hủy | Đăng ký listener và test container lifecycle. |
| Custom filter không lưu/xóa context đúng | Authentication có thể xuất hiện lại | Kiểm tra SecurityContextRepository và explicit-save semantics. |
| Thay đổi nhiều SecurityFilterChain nhưng không test logout URL | Request có thể đi qua chain khác dự kiến | Kiểm tra first-matching chain, logout matcher và filter order. |

## 16. Ma trận kiểm thử trong hệ thống thật

| Tình huống | Bằng chứng cần thu thập |
| --- | --- |
| Login thành công | User có SecurityContext hợp lệ và endpoint riêng tư trả thành công. |
| POST logout hợp lệ | Session hiện tại bị invalidate, response thành công theo contract. |
| POST logout không CSRF | Bị từ chối, session trước đó vẫn tồn tại. |
| Browser gửi session ID cũ sau logout | Request không dùng được Authentication cũ. |
| Hai browser đăng nhập cùng user | Logout A không tự phá B khi policy chỉ logout current. |
| Session timeout | Request sau cần xác thực lại; event cleanup hoạt động nếu có registry. |
| Remember-me đang bật | Logout ngăn auto-login lại theo chính sách và token repository. |
| App có HTTP Basic | Hiểu rõ khả năng browser tái gửi Authorization. |
| Stateless bearer JWT | Có chính sách rõ về hiệu lực token sau logout. |
| Cluster nhiều node | Session invalid/revoke có hiệu lực nhất quán qua load balancer. |
| OIDC | Phân biệt local logout và IdP logout, kiểm thử cả hai nếu sản phẩm yêu cầu. |
| Proxy/cookie Path/Domain | Cookie deletion đúng với cookie đã được set, server invalidation vẫn là nguồn sự thật. |

**Đừng xem một bài MockMvc test là bằng chứng bao trùm toàn bộ cookie/network/cluster.** MockMvc phù hợp để kiểm tra filter-chain behavior và MockHttpSession; kiểm tra Set-Cookie, TLS termination và session store thực cần môi trường tích hợp.

## 17. Câu hỏi tự kiểm tra

**Câu 1:** Nếu gọi <code>SecurityContextHolder.clearContext()</code> mà giữ nguyên HttpSession có lưu SecurityContext, request sau có chắc là anonymous không?  
**Trả lời:** Không. Repository có thể nạp lại Authentication cũ từ session; cần logout handler hoặc cơ chế lưu context rỗng/invalidate phù hợp.

**Câu 2:** Sau khi <code>HttpSession.invalidate()</code> nhưng chưa clear context của request hiện tại, có điểm gì cần lưu ý?  
**Trả lời:** Session bị hủy nhưng Authentication còn tồn tại trong context hiện tại cho đến khi được clear; cần xử lý trọn logout lifecycle và các handlers liên quan.

**Câu 3:** <code>.deleteCookies("JSESSIONID")</code> có thay thế <code>.invalidateHttpSession(true)</code> không?  
**Trả lời:** Không. Cookie deletion thay đổi trạng thái browser; invalidation mới làm mất hiệu lực session phía server.

**Câu 4:** Vì sao POST logout thiếu CSRF trong ví dụ phải bị 403?  
**Trả lời:** Vì request thay đổi trạng thái trong app dùng cookie/session cần token CSRF hợp lệ; không nên tắt CSRF để logout “dễ dùng” hơn.

**Câu 5:** Nếu browser A logout, browser B vẫn đăng nhập cùng tài khoản có chắc bị hủy không?  
**Trả lời:** Không. Logout mặc định xử lý session hiện tại. Muốn logout everywhere phải có cơ chế thu hồi nhiều phiên và token liên quan.

**Câu 6:** Một JWT bearer token có hết hiệu lực chỉ vì gọi clearContext trên một request không?  
**Trả lời:** Không. JWT có vòng đời độc lập, cần cơ chế expiry/revoke/introspection hoặc token version phù hợp.

**Câu 7:** SSO user logout ở ứng dụng nhưng Identity Provider còn phiên. Điều gì có thể xảy ra?  
**Trả lời:** Một lần truy cập ứng dụng sau đó có thể đăng nhập lại qua IdP mà không cần nhập credential mới; nếu yêu cầu global logout, phải tích hợp quy trình logout của IdP.

**Ghi nhớ:** Trong ứng dụng Servlet dùng HttpSession, logout chuẩn phải **vô hiệu hóa phiên server**, **xóa Authentication/SecurityContext đúng cách** và **phản hồi cho client phù hợp**; dọn cookie chỉ là phần hỗ trợ. <code>LogoutFilter</code> và <code>SecurityContextLogoutHandler</code> giúp phối hợp những hành động cơ bản. Logout current session không đồng nghĩa logout mọi session, remember-me, JWT hay phiên tại IdP.
