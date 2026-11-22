# SessionRegistry, HttpSessionEventPublisher và theo dõi phiên đang hoạt động trong Spring Security Servlet

**Ngữ cảnh:** Spring Security 6.x, Spring Boot 3.x, Java 17+ và Jakarta Servlet. Bài thuộc nhóm **Quản lý phiên**. Mục tiêu là hiểu cách Spring Security đăng ký các phiên đăng nhập đã xác thực, phát hiện phiên bị đánh dấu hết hạn, nhận sự kiện vòng đời HttpSession từ Servlet container và kiểm thử trạng thái phiên bằng request thật.

Điều cốt lõi: **SessionRegistry không phải kho chứa tất cả HttpSession**, còn **HttpSessionEventPublisher không phải cơ chế đăng xuất toàn bộ thiết bị**. Hai thành phần chỉ phát huy vai trò khi được kết nối với session authentication strategy, filter và Servlet container đúng cách.

## 1. Bài toán: một tài khoản, nhiều phiên

Giả sử tài khoản <code>alice</code> đã đăng nhập từ laptop A, laptop B và điện thoại C. Mỗi trình duyệt có thể sở hữu một cookie <code>JSESSIONID</code> trỏ đến một HttpSession khác nhau. Với form login dùng HttpSession, các request tiếp theo lấy Authentication tương ứng từ SecurityContext đã lưu.

~~~text
Browser A -- cookie JSESSIONID=A1 --+
Browser B -- cookie JSESSIONID=B2 --+--> Servlet container/session store
Phone C   -- cookie JSESSIONID=C3 --+                   |
                                                        v
                                               Spring Security
                                                        |
                                                        v
                                               SessionRegistry
                                               principal: alice
                                               session IDs: A1,B2,C3
~~~

Ứng dụng có thể muốn tối đa hai phiên đồng thời; khi thiết bị thứ ba đăng nhập, nó sẽ từ chối login mới hoặc cho phép login mới và buộc phiên ít hoạt động hơn hết hiệu lực. Một tính năng khác là “đăng xuất các thiết bị khác”, nghĩa là phiên đang thao tác tiếp tục có hiệu lực còn các phiên đã đăng ký khác phải bị chặn ở lần request tiếp theo.

**Phân biệt thiết bị, browser, tab và session:** hai tab chung browser profile thường dùng cùng cookie và cùng một HttpSession. Hai profile/cookie jar riêng thường có các session khác nhau. SessionRegistry theo dõi session ID, **không** tự nhận dạng số thiết bị vật lý.

## 2. Những thành phần nào tham gia?

| Thành phần | Chức năng |
| --- | --- |
| <code>HttpSession</code> | Session cấp Servlet, do container hoặc session store quản lý, thường được truy cập qua JSESSIONID. |
| <code>SecurityContext</code> | Chứa Authentication hiện tại; ứng dụng stateful có thể lưu vào HttpSession. |
| <code>SessionRegistry</code> | Interface quản lý danh mục phiên theo principal và session ID. |
| <code>SessionRegistryImpl</code> | Triển khai mặc định dạng bộ nhớ trong một JVM, chứa các <code>SessionInformation</code>. |
| <code>SessionInformation</code> | Thông tin về một phiên: sessionId, principal, lastRequest, cờ expired. |
| <code>SessionAuthenticationStrategy</code> | Được gọi khi login thành công để kiểm soát số phiên, chống fixation và đăng ký phiên. |
| <code>ConcurrentSessionFilter</code> | Kiểm tra phiên expired khi request tiếp theo đi qua và refresh lastRequest. |
| <code>HttpSessionEventPublisher</code> | Servlet listener phát các sự kiện lifecycle HttpSession sang Spring application context. |
| <code>HttpSessionDestroyedEvent</code> | Event Spring Security hỗ trợ thông báo việc session thực sự bị hủy để registry dọn bản ghi. |

Các thành phần không tự liên kết chỉ nhờ tạo bean. Nếu tự viết authentication filter và chỉ đặt <code>SecurityContextHolder.setContext(...)</code> mà không gọi các session authentication strategy tương ứng, <code>SessionRegistry</code> có thể **trống dù request đã xác thực**.

### Luồng khi một form login thành công

~~~text
POST /login với username/password + CSRF
                |
                v
UsernamePasswordAuthenticationFilter
                |
                v
AuthenticationManager kiểm tra credentials
                |
                v
Authentication thành công
                |
                v
SessionAuthenticationStrategy
   1. Kiểm tra giới hạn phiên đồng thời
   2. Thực hiện chiến lược chống session fixation
   3. Đăng ký session ID + principal
                |
                v
SecurityContext được lưu theo chính sách stateful
                |
                v
Browser gửi request với JSESSIONID
                |
                v
ConcurrentSessionFilter kiểm tra expired và refresh lastRequest
                |
                v
Controller / authorization / response
~~~

Vị trí chi tiết của các filter và session strategies có thể phụ thuộc phiên bản và kiểu authentication. Để xác minh, hãy kiểm thử đường đăng nhập thật qua Spring SecurityFilterChain, không chỉ khởi tạo thủ công một HttpSession.

## 3. API quan trọng của SessionRegistry

Interface <code>org.springframework.security.core.session.SessionRegistry</code> cung cấp:

~~~java
// Những câu lệnh minh họa trong class đã inject SessionRegistry.
List<Object> principals = registry.getAllPrincipals();

List<SessionInformation> active =
    registry.getAllSessions(principal, false);

List<SessionInformation> allKnown =
    registry.getAllSessions(principal, true);

SessionInformation sessionInfo =
    registry.getSessionInformation(sessionId);

registry.registerNewSession(sessionId, principal);
registry.refreshLastRequest(sessionId);
registry.removeSessionInformation(sessionId);
~~~

Giải thích:
- <code>getAllPrincipals()</code> liệt kê những principal có bản ghi phiên trong registry; **không** phải toàn bộ user trong database.
- <code>getAllSessions(principal, false)</code> lấy các session được đăng ký **chưa bị đánh dấu expired**. “Active” ở đây là trạng thái theo registry, không phải chứng cứ browser còn đang mở hoặc người dùng đang thao tác.
- <code>getAllSessions(principal, true)</code> bao gồm cả session đã expired nếu vẫn còn được registry lưu.
- <code>getSessionInformation(id)</code> tra một session hoặc trả null khi registry không có bản ghi.
- <code>registerNewSession(id, principal)</code> được <code>RegisterSessionAuthenticationStrategy</code> sử dụng trong một cấu hình concurrency hợp lệ. Thông thường controller không tự gọi method này.
- <code>refreshLastRequest(id)</code> ghi nhận thời điểm request gần nhất được cơ chế registry quan sát; <code>ConcurrentSessionFilter</code> thường thực hiện trên request có session phù hợp.
- <code>removeSessionInformation(id)</code> chỉ xóa bản ghi **trong registry**, không trực tiếp invalidate một HttpSession của Servlet container.

### Principal và equals/hashCode

SessionRegistryImpl dùng principal làm khóa nhóm. Nếu một custom principal được tạo mới ở từng lần login nhưng <code>equals()</code>/<code>hashCode()</code> dùng object identity hoặc thuộc tính biến động, hai phiên của cùng tài khoản có thể bị tính thành hai nhóm khác nhau. Hậu quả: giới hạn phiên và danh sách session theo người dùng sai.

Một principal dùng để theo dõi session nên có định danh ổn định, ví dụ account ID, với equality được thiết kế rõ. Với user thuộc nhiều tenant, cần quyết định giới hạn session theo account hay theo account+tenant và bảo đảm không làm trộn quyền của các tenant. Ví dụ bài học dùng <code>org.springframework.security.core.userdetails.User</code> chuẩn của Spring Security nên tránh phần phức tạp này.

## 4. Expired, destroyed, invalidated và removed: khác nhau như thế nào?

| Hành động | Registry biết gì? | Servlet session bị xử lý ngay chưa? |
| --- | --- | --- |
| Login thành công và đăng ký | Có SessionInformation, <code>expired=false</code> | Session đã được tạo/đăng ký theo login strategy. |
| Request hợp lệ | lastRequest được cập nhật nếu concurrency filter chạy | Session vẫn hoạt động. |
| <code>SessionInformation.expireNow()</code> | Đặt <code>expired=true</code> | **Không** tự invalidate session ngay tức thì. |
| Request sau từ phiên expired | ConcurrentSessionFilter phát hiện và xử lý | Thường logout/invalidate và redirect hoặc trả failure response. |
| <code>HttpSession.invalidate()</code> | Nếu event được gửi tới registry, bản ghi sẽ được dọn | Có: chính session đó bị invalidate. |
| Session timeout ở container | Có thể nhận destroyed event và xóa bản ghi | Session bị hủy theo timeout/session store. |
| <code>registry.removeSessionInformation(id)</code> | Bản ghi biến mất | **Không bảo đảm** HttpSession tương ứng bị hủy. |

Đoạn sau **chỉ đánh dấu**, không phải logout tức thì trên máy từ xa:

~~~java
SessionInformation info = registry.getSessionInformation(otherSessionId);
if (info != null) {
    info.expireNow();
}
~~~

Browser kia có thể vẫn giữ cookie; khi nó gửi request đi qua <code>ConcurrentSessionFilter</code>, Spring Security phát hiện cờ expired và thực thi expired-session strategy. Nếu browser không gửi request nào, bản ghi expired có thể tiếp tục tồn tại đến khi session thực sự timeout/destroyed.

Đừng dùng <code>removeSessionInformation(id)</code> như một API “revoke” thay thế <code>expireNow()</code>. Xóa bản ghi quá sớm có thể khiến filter không còn biết phiên cần bị từ chối.

## 5. HttpSessionEventPublisher và vòng đời session

Khi Servlet container tạo/hủy session (hoặc đổi session ID theo sự kiện có hỗ trợ), nó gọi servlet listener đã đăng ký. <code>HttpSessionEventPublisher</code> là cầu nối đưa lifecycle event tương ứng vào Spring Security application context. Đặc biệt, <code>HttpSessionDestroyedEvent</code> cho phép <code>SessionRegistryImpl</code> loại session ID đã bị hủy.

~~~text
Logout / invalidate / session timeout
                 |
                 v
          Servlet container
                 |
          HttpSessionListener
                 |
          HttpSessionEventPublisher
                 |
          HttpSessionDestroyedEvent
                 |
          SessionRegistryImpl
                 |
       removeSessionInformation(id)
~~~

Không có listener, registry in-memory có thể giữ phiên mà container đã hủy, dẫn đến thống kê sai hoặc cơ chế <code>maxSessionsPreventsLogin(true)</code> tiếp tục coi user đã đạt giới hạn. Listener không phải một tiến trình nền quét registry, và cũng không biến registry local thành registry toàn cluster.

Spring Boot embedded Servlet có thể đăng ký listener như sau:

~~~java
@Bean
ServletListenerRegistrationBean<HttpSessionEventPublisher> sessionEvents() {
    return new ServletListenerRegistrationBean<>(
        new HttpSessionEventPublisher());
}
~~~

Khi chuyển sang standalone Servlet container có cách đăng ký listener khác, phải bảo đảm **đúng một registration**. Khi dùng session fixation protection hoặc <code>changeSessionId()</code>, cần xác minh registry phản ánh session ID **sau khi login thành công**, không mặc định ID trước authentication vẫn là khóa cần dùng.

## 6. Hai chính sách về maximumSessions

**Cho login mới nhưng expire một phiên cũ:**

~~~java
http.sessionManagement(session -> session
    .maximumSessions(2)
        .maxSessionsPreventsLogin(false)
        .sessionRegistry(registry));
~~~

Khi đã đạt hai phiên chưa expired và browser C đăng nhập, concurrency strategy chọn phiên ít hoạt động hơn để đánh dấu expired, sau đó đăng ký phiên C. Phiên bị đánh dấu sẽ bị xử lý khi request sau đi qua filter.

**Ngăn login mới nếu đã đạt giới hạn:**

~~~java
http.sessionManagement(session -> session
    .maximumSessions(2)
        .maxSessionsPreventsLogin(true)
        .sessionRegistry(registry));
~~~

Với mode này, login mới vượt giới hạn bị từ chối nhưng các phiên đang dùng vẫn hoạt động. Form login có thể redirect về màn hình báo lỗi; không nên tự gán một HTTP status cố định cho mọi cấu hình Spring Security.

Trong cả hai trường hợp, <code>maximumSessions</code> kiểm soát **những session đã xác thực mà cơ chế session management đăng ký**, không phải mọi session do ứng dụng tự tạo hay mọi JWT đang lưu ở client. Số phiên nên được chọn theo nhu cầu bảo mật và trải nghiệm user.

## 7. Ví dụ chạy được: theo dõi hai phiên của một tài khoản

Ví dụ sử dụng **Java 17+, Spring Boot 3.3.5 (Spring Security 6.x), Maven**, form login, HttpSession và SessionRegistryImpl. Nó cố ý chỉ chạy trong **một JVM** để nhìn rõ vòng đời registry.

Yêu cầu:
1. <code>alice</code> đăng nhập tối đa hai phiên đồng thời.
2. <code>GET /me</code> trả username sau khi đã đăng nhập.
3. <code>GET /sessions/count</code> trả số session **chưa expired** của principal hiện tại.
4. <code>POST /sessions/revoke-others</code> đánh dấu những session khác hết hiệu lực, giữ session hiện tại.
5. Khi một browser đã bị expire gửi request mới, nó được redirect đến <code>/login?expired</code>.
6. CSRF được bật mặc định trên các POST.

Cấu trúc dự án:

~~~text
session-registry-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/sessionregistry/
    │   ├── SessionRegistryApplication.java
    │   ├── SecurityConfiguration.java
    │   └── SessionController.java
    └── test/java/com/example/sessionregistry/
        └── SessionTrackingTest.java
~~~

### 7.1. pom.xml

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
    <artifactId>session-registry-demo</artifactId>
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

### 7.2. Application entry point

Tạo <code>src/main/java/com/example/sessionregistry/SessionRegistryApplication.java</code>:

~~~java
package com.example.sessionregistry;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionRegistryApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionRegistryApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfiguration.java

Tạo <code>src/main/java/com/example/sessionregistry/SecurityConfiguration.java</code>:

~~~java
package com.example.sessionregistry;

import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

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
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    ServletListenerRegistrationBean<HttpSessionEventPublisher> sessionEvents() {
        return new ServletListenerRegistrationBean<>(
            new HttpSessionEventPublisher());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SessionRegistry registry) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(sessions -> sessions
                .maximumSessions(2)
                    .maxSessionsPreventsLogin(false)
                    .expiredUrl("/login?expired")
                    .sessionRegistry(registry))
            .build();
    }
}
~~~

Giải thích:
- <code>InMemoryUserDetailsManager</code> cấp UserDetails với principal có equality ổn định. Password được băm bằng <code>DelegatingPasswordEncoder</code>, không lưu chuỗi thô.
- <code>SessionRegistryImpl</code> là bộ đăng ký phiên dùng chung trong **JVM của demo**.
- <code>HttpSessionEventPublisher</code> nhận sự kiện hủy/timeout session từ Servlet container để registry có thể loại bản ghi đã mất.
- <code>maximumSessions(2)</code> kích hoạt đăng ký và kiểm soát phiên concurrent. <code>maxSessionsPreventsLogin(false)</code> expire phiên cũ khi cần thay vì chặn login mới.
- <code>expiredUrl("/login?expired")</code> dùng cho request tiếp theo của phiên expired.
- <code>anyRequest().authenticated()</code> bảo vệ các endpoint quan sát trạng thái session; không cho anonymous đọc danh sách.
- Spring Security mặc định bảo vệ CSRF. Không tắt CSRF chỉ vì muốn thử POST từ command-line.
- Đây là demo, không phải giải pháp production dùng user/password cố định hay registry local trên cluster.

### 7.4. SessionController.java

Tạo <code>src/main/java/com/example/sessionregistry/SessionController.java</code>:

~~~java
package com.example.sessionregistry;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    private final SessionRegistry registry;

    public SessionController(SessionRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/sessions/count")
    public String count(Authentication authentication) {
        int active = registry.getAllSessions(
            authentication.getPrincipal(), false).size();
        return Integer.toString(active);
    }

    @PostMapping("/sessions/revoke-others")
    public ResponseEntity<String> revokeOthers(
            Authentication authentication, HttpServletRequest request) {

        HttpSession current = request.getSession(false);
        if (current == null) {
            return ResponseEntity.badRequest().body("No active HttpSession");
        }

        String currentId = current.getId();
        int revoked = 0;

        for (SessionInformation info :
                registry.getAllSessions(authentication.getPrincipal(), false)) {
            if (!currentId.equals(info.getSessionId())) {
                info.expireNow();
                revoked++;
            }
        }

        return ResponseEntity.ok("revoked:" + revoked);
    }
}
~~~

Controller xác định principal từ <code>Authentication</code> được Spring Security quản lý, không tin username do client tự gửi. Nó chỉ đếm/expire phiên của người đang xác thực. Không xuất các session ID raw ra HTTP response để tránh tăng nguy cơ lộ credential phiên.

<code>POST /sessions/revoke-others</code> không tự hủy tất cả HttpSession ở những browser khác ngay lập tức. Nó đặt cờ expired trên các bản ghi trong registry; <code>ConcurrentSessionFilter</code> xử lý khi những browser đó gửi request tiếp. Với sản phẩm thật, đây còn là thao tác nhạy cảm nên có thể cần re-authentication, audit, rate limit và cơ chế revocation liên node.

## 8. Thử bằng hai browser profile độc lập

Chạy trong thư mục chứa <code>pom.xml</code>:

~~~bash
mvn test
mvn spring-boot:run
~~~

Mở một cửa sổ thường và một cửa sổ riêng tư (hoặc hai browser profile độc lập), truy cập <code>http://localhost:8080/login</code>, nhập <code>alice / local-password-1234</code> ở cả hai. Mỗi profile có cookie session khác nhau.

| Thao tác | Browser A | Browser B |
| --- | --- | --- |
| GET /me trước login | Redirect login | Redirect login |
| Đăng nhập | Session A được đăng ký | Session B được đăng ký |
| GET /me sau login | <code>alice</code> | <code>alice</code> |
| GET /sessions/count | <code>2</code> | <code>2</code> |
| A gửi POST /sessions/revoke-others có CSRF hợp lệ | <code>revoked:1</code> | Phiên B được đánh dấu expired |
| B gọi GET /me tiếp | A vẫn dùng được | B redirect <code>/login?expired</code> |
| A gọi GET /sessions/count | <code>1</code> | B không còn là phiên active theo registry |

Phải gửi CSRF token do server tạo khi POST. Nếu dùng curl chỉ gửi cookie nhưng không có CSRF token, phản hồi 403 là **đúng với cấu hình demo**, không phải lỗi SessionRegistry. Việc login trên hai tab chia chung cookie có thể chỉ tạo một session, nên phải thử với cookie jars tách biệt.

Đăng nhập ở browser C khi A và B vẫn có hai phiên chưa expired: cấu hình <code>maximumSessions(2)</code> chọn một phiên cũ/ít hoạt động hơn để expire, rồi đăng ký C. Phiên bị chọn phụ thuộc <code>lastRequest</code> và không nhất thiết là browser đăng nhập trước nếu nó vừa có request mới.

## 9. Kiểm thử tự động với MockMvc

Tạo <code>src/test/java/com/example/sessionregistry/SessionTrackingTest.java</code>:

~~~java
package com.example.sessionregistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.annotation.DirtiesContext;
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
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionTrackingTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    SessionRegistry registry;

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
    void twoSessionsCanBeTrackedAndOneExpired() throws Exception {
        MockHttpSession a = login();
        MockHttpSession b = login();

        assertThat(a.getId()).isNotEqualTo(b.getId());
        assertThat(registry.getSessionInformation(a.getId())).isNotNull();
        assertThat(registry.getSessionInformation(b.getId())).isNotNull();

        mvc.perform(get("/sessions/count").session(a))
            .andExpect(status().isOk())
            .andExpect(content().string("2"));

        // Thiếu CSRF: không được phép revoke.
        mvc.perform(post("/sessions/revoke-others").session(a))
            .andExpect(status().isForbidden());

        mvc.perform(post("/sessions/revoke-others")
                .session(a).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("revoked:1"));

        SessionInformation other =
            registry.getSessionInformation(b.getId());
        assertThat(other).isNotNull();
        assertThat(other.isExpired()).isTrue();

        mvc.perform(get("/sessions/count").session(a))
            .andExpect(status().isOk())
            .andExpect(content().string("1"));

        mvc.perform(get("/me").session(b))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?expired"));

        mvc.perform(get("/me").session(a))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void aThirdLoginLeavesAtMostTwoNonExpiredSessions()
            throws Exception {
        MockHttpSession a = login();
        MockHttpSession b = login();
        MockHttpSession c = login();

        assertThat(registry.getSessionInformation(c.getId())).isNotNull();

        long stillActive = java.util.stream.Stream.of(a, b, c)
            .map(s -> registry.getSessionInformation(s.getId()))
            .filter(s -> s != null && !s.isExpired())
            .count();

        assertThat(stillActive).isLessThanOrEqualTo(2);
    }
}
~~~

Vì sao test dùng POST login thật? <code>@WithMockUser</code> thích hợp để test authorization, nhưng không nhất thiết chạy <code>SessionAuthenticationStrategy</code> và không tự tạo bản ghi registry. Bài test phải qua filter form login để chứng minh session registration.

<code>@DirtiesContext</code> ở đây cô lập trạng thái registry in-memory giữa hai test; nếu dùng chung registry và login ở test trước không được hủy, test sau có thể vi phạm giới hạn phiên ngoài ý muốn.

**Giới hạn của MockMvc:** nó không nhất thiết phát các servlet lifecycle events giống embedded Tomcat thực. Test trên xác nhận registration/expired behavior, nhưng không chứng minh 100% <code>HttpSessionEventPublisher</code> dọn bản ghi sau timeout/logout thực ở Servlet container. Với mục đích đó, viết test tích hợp trên server thực (<code>@SpringBootTest(webEnvironment = RANDOM_PORT)</code> hoặc HTTP client qua server đã chạy), cho logout/invalidate/timeout rồi xác nhận registry không còn bản ghi.

## 10. Theo dõi session online không giống đếm session chưa expired

Khi gọi <code>getAllSessions(principal, false)</code>, “active” mang nghĩa **chưa bị registry đánh dấu expired**. Nó không khẳng định user vẫn mở tab hay vừa thao tác gần đây; browser có thể đóng mà session còn tồn tại đến khi timeout. Một HttpSession tạo thủ công mà không đi qua session registration cũng có thể không có trong registry.

<code>SessionInformation.getLastRequest()</code> là thời điểm registry được refresh khi request qua cơ chế concurrency tương ứng. <code>HttpSession.getLastAccessedTime()</code> lại là metadata của Servlet container. Hai timestamp không luôn đồng bộ tuyệt đối vì filter chain, dispatcher, session store và các loại request có thể khác nhau.

Đừng dùng <code>SessionRegistry.getAllPrincipals().size()</code> làm chỉ số chính xác tuyệt đối của số người “đang online” hay toàn bộ tài khoản có session ở mọi máy chủ. Với monitoring, có thể theo dõi thêm số session trong store, login success/failure, số expired chờ cleanup, session destroyed events và độ trễ thu hồi.

Không expose nguyên các principal hoặc session IDs trong dashboard công khai. Session ID là credential nhạy cảm; nếu cần UI “thiết bị đã đăng nhập”, chỉ cung cấp metadata tối thiểu, được server xác minh thuộc account đang đăng nhập và không để người dùng tùy chọn username của account khác.

## 11. Logout, timeout và HttpSessionDestroyedEvent

Một luồng logout stateful thông thường:

~~~text
POST /logout + CSRF token
      |
Spring Security logout handler
      |
SecurityContext được xóa
      |
HttpSession hiện tại bị invalidate
      |
Servlet container phát sessionDestroyed
      |
HttpSessionEventPublisher chuyển thành Spring event
      |
SessionRegistryImpl xóa session ID khỏi registry
~~~

Khi session tự timeout, container cũng có thể phát destroyed event và registry dọn bản ghi. Nếu thiếu listener, registry có nguy cơ tiếp tục giữ session không còn tồn tại, nhất là nguy hiểm với <code>maxSessionsPreventsLogin(true)</code>: user có thể bị chặn login vì registry nghĩ họ vẫn có đủ phiên.

Phân biệt việc expire từ concurrency:
- <code>expireNow()</code> đánh dấu cờ expired nhưng không lập tức làm mất session.
- Browser đã expired gửi request; <code>ConcurrentSessionFilter</code> chạy expired strategy, thường logout/invalidate phiên.
- Container phát destroyed event khi session bị hủy; publisher giúp registry loại bản ghi.

Nếu browser không gửi request nữa, bản ghi expired có thể tồn tại cho đến timeout/session destroyed thực. **Không** kết luận việc còn bản ghi expired đồng nghĩa user vẫn hoạt động.

## 12. Session fixation và thay session ID

Khi xác thực thành công, Spring Security thường áp dụng session fixation protection trên Servlet hiện đại, có thể dùng <code>changeSessionId()</code>. Session chưa login có ID <code>PRE</code>, sau login là <code>POST</code>. Registry phải theo dõi ID **sau** thay đổi.

Nếu custom authentication code tự đăng ký session quá sớm, rồi tự đổi ID hoặc không gọi strategy tương ứng, registry có thể bị lệch. Khi viết custom filter, cần bảo đảm SessionAuthenticationStrategy, SecurityContextRepository và session fixation strategy được phối hợp đúng.

Test nên kiểm tra <code>registry.getSessionInformation(session.getId())</code> trên session lấy **sau login**, thay vì lấy ID trước login rồi dự đoán registry luôn giữ nguyên. Đừng ghi session ID vào URL, log public hoặc response debug.

## 13. Hệ thống nhiều node và Spring Session

Trong một cluster:

~~~text
                    +-- App node A / SessionRegistryImpl A
Client -> gateway --+-- App node B / SessionRegistryImpl B
                    +-- App node C / SessionRegistryImpl C
                            |
                       Database chung
~~~

Dù cùng database tài khoản, mỗi SessionRegistryImpl in-memory chỉ biết những session đã được đăng ký ở **tiến trình của nó**. Giới hạn 2 phiên có thể thành “2 phiên mỗi node”, không phải 2 phiên toàn cluster. Gọi <code>expireNow</code> trên node A không tự chuyển cờ expired tới node B. HttpSessionEventPublisher trong node A cũng không tự broadcast cho B/C.

Khi yêu cầu quản lý phiên toàn cluster, có thể dùng:
- Spring Session với Redis/JDBC hoặc kho phiên dùng chung.
- Repository hỗ trợ index theo principal để tìm các session thuộc cùng tài khoản.
- Registry/concurrency integration phân tán phù hợp repository, ví dụ <code>SpringSessionBackedSessionRegistry</code> trong phiên bản hỗ trợ.
- Credential/session version hoặc revocation state dùng chung nếu cần đảm bảo chặn mọi phiên cũ trên request tiếp theo.
- Kiểm thử nhiều instance và route qua load balancer, không chỉ test một JVM.

**Lưu ý:** thêm Spring Session Redis không tự biến <code>SessionRegistryImpl</code> in-memory thành registry toàn cluster. Tích hợp registry phân tán có các semantics và giới hạn riêng, cần xem đúng phiên bản và kiểm thử thực tế.

Ví dụ pseudocode cho một repository có principal index (không phải file Java độc lập):

~~~java
var sessions = indexedRepository.findByPrincipalName(username);
for (String sessionId : sessions.keySet()) {
    indexedRepository.deleteById(sessionId);
}
~~~

Muốn dùng đoạn đó thật phải có <code>FindByIndexNameSessionRepository</code> hoặc contract tương ứng, index principal chính xác, <code>username</code> từ nguồn server tin cậy và quyền thao tác được giới hạn. Xóa session trực tiếp trong store khác với đánh dấu <code>SessionInformation.expireNow()</code> tại registry.

Nếu hệ thống dùng JWT stateless, SessionRegistry không quản lý access token đang ở client. Việc revoke phụ thuộc expiry, refresh-token revocation, token version, denylist/introspection hoặc cơ chế phù hợp khác.

## 14. Bảng lỗi phổ biến và cách xử lý

| Lỗi / triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Có SessionRegistry bean nhưng danh sách session rỗng | Đường login không gọi session registration strategy | Bật concurrency management, test POST /login thật |
| Đã logout nhưng registry còn session | Thiếu publisher hoặc event cleanup | Đăng ký HttpSessionEventPublisher và test container thật |
| Gọi expireNow nhưng browser khác vẫn giữ cookie | Đó là thao tác đánh dấu | Test request tiếp theo qua ConcurrentSessionFilter |
| Gọi removeSessionInformation để logout | Registry quên session nhưng HttpSession có thể vẫn dùng | Dùng logout/invalidate hoặc revocation đúng |
| Hai lần login cùng user bị tính hai principal | Custom principal equals/hashCode không ổn định | Dùng định danh account ổn định |
| Coi nhiều tab là nhiều phiên | Các tab chia cookie | Thử hai browser profiles/cookie jars |
| MockMvc @WithMockUser không tạo session registry | Không đi qua form login strategy | Login thật qua MockMvc |
| Người dùng bị khóa login dù đã timeout | Registry không nhận session destroyed events | Kiểm tra listener, timeout và cấu hình prevents-login |
| Test local đúng nhưng production sai | Nhiều app replicas, registry local | Dùng shared session/index và test xuyên node |
| “Online count” lớn hơn số browser đang dùng | Session chưa timeout hoặc cờ expired chưa dọn | Phân biệt online presence với active-in-registry |
| Custom authentication không đăng ký session | Bỏ qua SessionAuthenticationStrategy | Tích hợp và test custom filter |
| Thay session ID sau đăng ký làm registry lệch | Không đồng bộ chiến lược fixation/registration | Dùng Spring Security session strategies đúng thứ tự |
| Endpoint hiển thị session IDs raw | Lộ identifier nhạy cảm | Chỉ trả metadata cần thiết, kiểm soát quyền |
| Nghĩ JWT stateless được registry theo dõi | Không có HttpSession login tương ứng | Thiết kế quản lý token riêng |
| Multiple SecurityFilterChain nhưng đặt registration sai chain | Request đi qua chain khác | Kiểm tra first-matching chain và filter order |

## 15. Checklist kiểm thử và vận hành

1. Xác định application đang dùng session-based authentication; nếu chỉ JWT stateless, SessionRegistry không phải công cụ quản lý token tương đương.
2. Khai báo SessionRegistry và đăng ký vào **đúng SecurityFilterChain** dùng form login hoặc custom authentication.
3. Bật concurrency/session authentication strategy, chọn maxSessions và mode expire-versus-prevent.
4. Đăng ký HttpSessionEventPublisher với Servlet container đúng một lần.
5. Test hai session riêng của cùng account bằng browser profiles độc lập; xác minh registry ghi đúng hai session IDs.
6. Test expireNow và request tiếp theo của session bị expire; phiên này không còn truy cập được.
7. Test logout/session timeout và cleanup bản ghi trong container thật; MockMvc không phải bằng chứng duy nhất.
8. Test chống CSRF và kiểm soát quyền trên endpoint xem/revoke session, không expose session ID.
9. Với nhiều node, kiểm tra shared session registry và tính nhất quán của chính sách toàn cluster.
10. Giữ log/metrics tối thiểu, không xuất cookie, session ID hoặc thông tin cá nhân không cần thiết.
11. Khi thay authentication filters hoặc session fixation strategy, test cả session ID trước/sau login.
12. Khi tăng/giảm maximumSessions, xem xét user experience và các phiên đang tồn tại.

## 16. Câu hỏi tự kiểm tra

**Câu 1:** <code>getAllSessions(principal, false)</code> trả hai phiên. Có chắc hai người đang sử dụng app không?  
**Đáp án:** Không. Đó là hai phiên registry biết và chưa expired; browser có thể đã đóng và session chưa timeout.

**Câu 2:** <code>expireNow()</code> có tức thì xóa HttpSession và cookie trên browser khác không?  
**Đáp án:** Không. Nó đánh dấu expired; filter xử lý ở request tiếp theo. Session có thể chỉ bị hủy khi expired strategy/timeout xảy ra.

**Câu 3:** Vì sao cần <code>HttpSessionEventPublisher</code>?  
**Đáp án:** Để những sự kiện session destroyed từ Servlet container đến Spring Security, cho phép registry xóa thông tin session đã chết.

**Câu 4:** Đã có SessionRegistry bean; có cần cấu hình gì để phiên được đăng ký khi login?  
**Đáp án:** Có. Cần SessionAuthenticationStrategy/concurrency integration hoặc luồng custom gọi registration phù hợp. Chỉ tạo bean không đủ.

**Câu 5:** <code>maximumSessions(2)</code> và <code>maxSessionsPreventsLogin(false)</code> có ý nghĩa gì?  
**Đáp án:** Khi đã có hai phiên, login mới được phép nhưng một phiên cũ/ít hoạt động hơn bị đánh dấu expired.

**Câu 6:** Ba node cùng database, mỗi node dùng SessionRegistryImpl. Có chắc giới hạn hai phiên trên toàn cluster không?  
**Đáp án:** Không. RegistryImpl chỉ chứa thông tin trong JVM của chính nó; cần cơ chế chia sẻ và kiểm thử xuyên node.

**Câu 7:** Gọi <code>removeSessionInformation(id)</code> thay cho invalidate có chắc logout không?  
**Đáp án:** Không. Đó chỉ là xóa bản ghi registry, HttpSession có thể vẫn tồn tại và có Authentication hợp lệ.

**Ghi nhớ:** <code>SessionRegistry</code> theo dõi các session được đăng ký, <code>SessionInformation</code> cho biết thời điểm request và cờ expired, <code>ConcurrentSessionFilter</code> xử lý phiên bị đánh dấu expired, còn <code>HttpSessionEventPublisher</code> đưa sự kiện hủy phiên của Servlet container tới Spring Security. Đừng nhầm **expired, destroyed, invalidated và removed**, và đừng coi registry local là một kho session toàn cluster.
