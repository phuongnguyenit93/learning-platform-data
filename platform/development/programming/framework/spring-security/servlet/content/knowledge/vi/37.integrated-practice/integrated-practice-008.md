# Bài thực hành phiên đồng thời, remember-me và thu hồi truy cập

**Module:** Spring Security – Servlet  
**Chủ đề cha:** Thực hành tổng hợp

## 1. Tình huống, mục tiêu và tiêu chí nghiệm thu

Một ứng dụng web dùng Spring MVC, session cookie và form login muốn đáp ứng các yêu cầu sau:

1. Mỗi tài khoản chỉ duy trì tối đa **một phiên đăng nhập tương tác hợp lệ** ở thời điểm kiểm tra. Nếu Alice đăng nhập trên trình duyệt B sau trình duyệt A, phiên A phải được **đánh dấu hết hiệu lực**, không được tiếp tục sử dụng khi request tiếp theo đến server.
2. Người dùng có thể chọn **Remember me** để được nhận một cookie dài hạn, giúp đăng nhập lại khi session ngắn hạn không còn, nhưng **cookie đó không được coi là phiên đang đăng nhập** và phải có cơ chế thu hồi.
3. Logout phải kết thúc phiên hiện tại và xóa cookie remember-me của browser; với persistent remember-me, phải xử lý token series ở server theo cơ chế tương ứng.
4. Quản trị viên được **thu hồi quyền truy cập của một tài khoản**: đánh dấu các phiên được quản lý là expired và yêu cầu xóa các persistent remember-me tokens của user đó.
5. POST logout và POST thu hồi vẫn yêu cầu **CSRF token hợp lệ**; chỉ người có quyền ADMIN mới được gọi chức năng thu hồi.
6. Có **kiểm thử tự động** xác nhận login/logout, authorization, CSRF, remember-me cookie, chính sách một phiên và logic xóa token.
7. Không đưa ra lời hứa bảo mật quá mức: một phiên bị đánh dấu expired thường chỉ bị thực sự chặn/invalidated ở request tiếp theo. **Request đang chạy** không nhất thiết bị hủy tức khắc; **môi trường nhiều node** cần cơ chế quản lý trạng thái dùng chung.

**Kết quả học tập:** hiểu khác nhau giữa session authentication, remember-me authentication và revocation; triển khai đúng `maximumSessions`, `SessionRegistry`, `PersistentTokenRepository`; biết cách test và vận hành mà không dựa vào một user giả hoặc dữ liệu in-memory ở production.

### Sơ đồ luồng tổng thể

~~~text
Alice / trình duyệt A                        Ứng dụng Servlet
       | POST /login + username/password + _csrf |
       |----------------------------------------->|
       |  Session A, SecurityContext = alice      |
       |<-----------------------------------------|
       | GET /me -> 200                           |
       |----------------------------------------->|

Alice / trình duyệt B
       | POST /login + password + _csrf           |
       |----------------------------------------->|
       |  SessionRegistry: tối đa 1 session       |
       |  Đánh dấu Session A = expired            |
       |  Đăng ký Session B = active              |
       |<-----------------------------------------|

Trình duyệt A: GET /me
       |----------------------------------------->|
       | ConcurrentSessionFilter phát hiện A     |
       | invalidates session, điều hướng hết hạn  |
       |<-----------------------------------------|

Admin
       | POST /admin/revoke + target=alice + _csrf|
       |----------------------------------------->|
       | SessionRegistry: expire các session Alice|
       | PersistentTokenRepository: remove tokens|
       |<-----------------------------------------|

Các request tiếp theo dùng session/token đã thu hồi:
       |--> phiên expired bị chặn khi được xử lý
       |--> remember-me token series đã xóa không còn hợp lệ
~~~

**Phạm vi:** đây là Spring Security **Servlet**, không phải WebFlux. Dự án dùng **Spring Boot 3.3.5, Java 17 và một JVM**, tập trung vào cơ chế và các giới hạn cần biết trước khi thiết kế production.

## 2. Ba loại trạng thái không được nhầm lẫn

| Đối tượng | Nơi lưu/truyền | Công dụng | Bị ảnh hưởng bởi hành động nào? |
| --- | --- | --- | --- |
| **HTTP session** | Server và cookie session (thường JSESSIONID) | Liên kết trình duyệt với `SecurityContext` xác thực | Logout, session timeout, session invalidation, concurrency expiry |
| **SessionRegistry** | Registry theo dõi session IDs và principal | Đếm, tra cứu và đánh dấu phiên cho concurrent session control | Login đăng ký, session destroy/expire, admin gọi `expireNow()` |
| **Persistent remember-me token** | Cookie ở browser + token series trong repository | Có thể khôi phục authentication sau khi phiên không còn | Logout, token rotation, explicit repository revocation, token expiry, cookie loss |

**SessionRegistry không phải kho lưu trữ HTTP session** và **PersistentTokenRepository không phải nơi lưu SecurityContext**. Bất kỳ thao tác “thu hồi truy cập” nào cũng phải xác định chính xác cần vô hiệu hóa lớp nào, trên thiết bị nào, trong bao lâu và với độ trễ chấp nhận được.

Ví dụ: xóa session A nhưng vẫn để remember-me cookie hợp lệ có thể khiến trình duyệt A đăng nhập lại tự động. Ngược lại, chỉ xóa token remember-me mà **không** expire session đang authenticated sẽ không khiến những request tiếp theo qua session hiện tại mất quyền ngay.

### 2.1. Authentication sau remember-me là gì?

Trong Spring Security, khi remember-me xác thực thành công, principal thường được tạo thành `RememberMeAuthenticationToken` và có thể được coi là đã authenticated cho những endpoint dùng `authenticated()`.

Với thao tác nhạy cảm như đổi mật khẩu hoặc chuyển tiền, nên cân nhắc **`fullyAuthenticated()`** hoặc step-up authentication theo threat model, vì một authentication đến từ remember-me không nhất thiết chứng minh người dùng vừa nhập lại mật khẩu. `fullyAuthenticated()` loại anonymous và remember-me authentication khỏi quyền truy cập theo semantics Spring Security.

**Không** chỉ đọc `authentication.isAuthenticated()` rồi kết luận người dùng vừa đăng nhập tương tác; cần xem loại Authentication và policy cụ thể.

## 3. Concurrent sessions trong Spring Security Servlet

### 3.1. maximumSessions(1)

Ví dụ cấu hình hiện đại:

~~~java
// Snippet bên trong HttpSecurity DSL của Spring Security 6.
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(false)
    .sessionRegistry(sessionRegistry)
);
~~~

Ý nghĩa:

- `maximumSessions(1)`: giới hạn session đồng thời theo principal được registry nhận diện.
- `maxSessionsPreventsLogin(false)`: đăng nhập mới được phép và **session cũ bị đánh dấu expired** để nhường chỗ. Cách này phù hợp với yêu cầu “thiết bị mới thay thế thiết bị cũ”.
- `maxSessionsPreventsLogin(true)`: thay vì đẩy session cũ, **từ chối đăng nhập mới** khi đạt giới hạn. Khi đổi tùy chọn, cần test login thất bại và trải nghiệm người dùng.
- `sessionRegistry(sessionRegistry)`: cung cấp registry dùng chung cho cơ chế concurrency và thành phần quản trị.

Trong trường hợp mặc định `false`, login mới **không gọi remote terminate tức thì** mọi request đang chạy của phiên trước; một `SessionInformation` được đánh dấu expired và `ConcurrentSessionFilter` xử lý khi phiên đó gửi request tiếp theo.

### 3.2. SessionRegistryImpl và HttpSessionEventPublisher

Trong một JVM demo:

~~~java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

`SessionRegistryImpl` theo dõi principal và session IDs **trong bộ nhớ tiến trình**. `HttpSessionEventPublisher` giúp Spring Security nhận sự kiện tạo/hủy session từ servlet container để làm sạch registry trong cấu hình thông thường.

Nếu bỏ session destroy events, registry có thể giữ session IDs đã hết hạn/hủy và làm quyết định số lượng phiên không phản ánh thực tế. **Đừng coi có bean `HttpSessionEventPublisher` là giải pháp cho session ở nhiều node.**

### 3.3. Kiểm tra bằng hai browser

1. Mở Chrome profile A, vào `/login`, đăng nhập bằng Alice.
2. Profile B (cookie/session độc lập) đăng nhập cũng bằng Alice.
3. Ở profile B, `GET /me` vẫn hoạt động.
4. Ở profile A, request tiếp theo tới `/me` phải bị xử lý như **session expired**; tùy cấu hình mặc định có thể redirect tới `/login?expired`.
5. Lặp lại với `maxSessionsPreventsLogin(true)`: profile B phải bị từ chối login khi A đang có phiên hợp lệ.

**Phải dùng hai kho cookie độc lập.** Hai tab trong cùng browser profile thường **chia sẻ cùng session cookie**, nên mở tab thứ hai không chứng minh có hai session độc lập.

**Mấu chốt:** session concurrency áp lên các phiên mà Spring Security **theo dõi**, thường qua authentication thành công; hành vi remember-me auto-login, session fixation, custom filters và asynchronous operations cần được kiểm thử riêng. Không diễn giải `maximumSessions(1)` như một cam kết tuyệt đối rằng không bao giờ có hai HTTP request in-flight của một người dùng.

## 4. Remember-me: cookie không phải session

Spring Security Servlet cung cấp remember-me theo hai hướng phổ biến:

- **Token-based remember-me**: cookie có thông tin được ký/kiểm tra theo secret; đơn giản hơn nhưng việc thu hồi từng token có thể khó nếu không có server-side tracking bổ sung.
- **Persistent token-based remember-me**: cookie lưu series/token, còn server lưu **persistent token record** theo series và username. Token được thay đổi/rotate khi dùng để đăng nhập lại; server có thể xóa các series của user để thu hồi.

Trong bài thực hành này dùng **persistent remember-me** qua `PersistentTokenRepository`. Demo dùng `InMemoryTokenRepositoryImpl`; hệ thống thật nên dùng repository được lưu bền vững ở database hoặc kho dữ liệu dùng chung, với chính sách bảo mật, backup, HA và cleanup token hết hạn.

### 4.1. Luồng remember-me

~~~text
POST /login (username, password, _csrf, remember-me=on)
    |
    +--> Xác thực password thành công
    |
    +--> PersistentTokenRepository.createNewToken(series, token, user)
    |
    +--> Set-Cookie: remember-me=... (HTTP-only theo cấu hình)
    |
    +--> Browser lưu cookie
              |
              +--> Session cookie mất/hết hạn, remember-me vẫn còn
                      |
                      +--> RememberMeAuthenticationFilter
                      +--> Tìm token series trong repository
                      +--> Xác thực token và luân chuyển token mới
                      +--> Authentication kiểu RememberMeAuthenticationToken
~~~

Không ghi raw remember-me cookie/token vào log, dashboard, tài liệu hoặc URL. Cookie token là **credential có thể bị đánh cắp**; dùng HTTPS, `Secure`, `HttpOnly`, `SameSite` phù hợp và giới hạn thời hạn. `SameSite` là phòng vệ bổ sung, không thay tất cả kiểm soát CSRF.

Persistent token series có thể được xóa qua `removeUserTokens(username)`. Đây là cơ chế thu hồi server-side, hữu ích hơn việc chỉ ra lệnh browser xóa cookie (browser khác vẫn giữ bản sao).

### 4.2. Remember-me logout và thu hồi

Trong cấu hình có remember-me, `LogoutFilter` thường gọi `RememberMeServices.logout` để xóa remember-me cookie và cập nhật token repository theo implementation. Đối với persistent implementation, logout có thể xóa series của user theo contract tương ứng. **Cần kiểm tra và test phiên bản cụ thể**, đừng dựa vào suy đoán rằng logout chỉ xóa session.

Khi quản trị viên thu hồi, ta thực hiện hai việc độc lập:

1. `SessionInformation.expireNow()` cho mọi session được registry theo dõi của tài khoản.
2. `PersistentTokenRepository.removeUserTokens(username)` để cookie remember-me cũ không còn token record server-side.

Với token bị xóa, browser vẫn có thể hiển thị cookie vật lý cho đến khi server gửi cookie xóa hoặc browser tự loại bỏ. **Cookie còn tồn tại không có nghĩa credential còn hợp lệ**. Ngược lại, không được tuyên bố đã chặn mọi thiết bị ngay tức thì: request đang xử lý, JWT truy cập độc lập và node khác không chia sẻ registry có thể vẫn hoạt động theo policy riêng.

## 5. Sơ đồ các tác động và giới hạn thu hồi

| Hành động | HTTP session hiện tại | Session khác | Persistent remember-me |
| --- | --- | --- | --- |
| User logout chuẩn | Session của request logout bị invalidated theo config | Không mặc định invalidated tất cả session khác | Cookie của browser bị xóa; implementation xử lý token repository |
| Đăng nhập mới với maximumSessions(1), preventsLogin=false | Session mới active | Phiên đã theo dõi cũ bị mark expired | Không mặc định xóa mọi remember-me series |
| Admin expireNow theo username | Phiên của user trong registry được mark expired | Các phiên khác **trong cùng registry** được mark expired | **Không đổi** nếu chỉ expireNow |
| Admin removeUserTokens(username) | **Không tự invalidate session đã authenticated** | Không tự invalidate | Xóa persistent records của user trong repository |
| Admin thực hiện cả hai | Các session được quản lý sẽ bị chặn ở lần xử lý tiếp theo | Tương tự trong vùng registry bao phủ | Các cookie series cũ không xác thực lại được |
| Đổi password | Tùy chính sách, **không mặc định đảm bảo thu hồi mọi session/token** | Tùy implementation | Nên có luồng revocation tường minh sau đổi password |

**Điều kiện của ví dụ:** tất cả request được gửi đến **một instance**. Trong cluster cần kho session + registry + token repository chia sẻ được, cùng một chính sách đồng bộ việc thu hồi.

## 6. Dự án thực hành chạy được — Spring Boot 3.3.5 / Java 17

Dự án gồm form login mặc định, một trang form quản trị render bằng Thymeleaf, endpoint hiển thị danh tính và service thu hồi. Mật khẩu cứng chỉ để học trên localhost.

### 6.1. Cấu trúc thư mục

~~~text
session-revocation-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── SessionLabApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   ├── AccessRevocationService.java
    │   │   └── LabController.java
    │   └── resources/
    │       ├── application.yml
    │       └── templates/revoke-form.html
    └── test/java/demo/
        ├── LabHttpSecurityTests.java
        └── AccessRevocationServiceTests.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>session-revocation-lab</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

`starter-security` cung cấp Servlet security/remember-me/concurrent session infrastructure, `starter-thymeleaf` render admin form, `spring-security-test` hỗ trợ `csrf()`, `user()` và kiểm tra login trong MockMvc. Không thêm Spring Session hay JDBC trong demo **một JVM**; production xem mục 11.

### 6.3. src/main/resources/application.yml

~~~yaml
app:
  remember-me:
    key: ${APP_REMEMBER_ME_KEY}

server:
  servlet:
    session:
      timeout: 20m
~~~

`APP_REMEMBER_ME_KEY` là **biến môi trường bắt buộc**. Không hard-code secret trong source repository hoặc dùng key mẫu trong production. Với môi trường có nhiều instance, key và repository phải nhất quán theo kế hoạch key rotation.

Phần `server.servlet.session.timeout` đặt timeout session ngắn hạn; remember-me validity bên dưới là 7 ngày. Session timeout và remember-me cookie expiry là **hai thông số khác nhau**.

### 6.4. src/main/java/demo/SessionLabApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLabApplication.class, args);
    }
}
~~~

### 6.5. src/main/java/demo/SecurityConfiguration.java

~~~java
package demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.rememberme.InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // DEMO ONLY: không dùng password hard-code trong production.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("demo-only"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-only"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    PersistentTokenRepository persistentTokenRepository() {
        // In-memory chỉ phục vụ thực hành trong một JVM.
        return new InMemoryTokenRepositoryImpl();
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            UserDetailsService users,
            SessionRegistry sessionRegistry,
            PersistentTokenRepository tokenRepository,
            @Value("${app.remember-me.key}") String rememberKey)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/", "/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin/revoke-form",
                    "/admin/sessions").hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/admin/revoke")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll()
            )
            .rememberMe(remember -> remember
                .key(rememberKey)
                .userDetailsService(users)
                .tokenRepository(tokenRepository)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60)
            )
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.migrateSession())
                .maximumSessions(1)
                .maxSessionsPreventsLogin(false)
                .sessionRegistry(sessionRegistry)
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            );

        // CSRF mặc định BẬT cho login, logout và admin POST.
        return http.build();
    }
}
~~~

**Giải thích cấu hình:**

1. `@EnableMethodSecurity` cho phép `@PreAuthorize` ở service thu hồi; HTTP rule bảo vệ endpoint là lớp thứ nhất, method security là lớp thứ hai.
2. `SessionRegistryImpl` dùng để tìm phiên theo principal, không phải kho session bền vững. `HttpSessionEventPublisher` giúp làm sạch thông tin phiên khi container thông báo session destroy.
3. `maximumSessions(1)` + `maxSessionsPreventsLogin(false)` ưu tiên phiên đăng nhập mới, đánh dấu phiên cũ expired.
4. `PersistentTokenRepository` cấp storage server-side cho persistent remember-me. `InMemoryTokenRepositoryImpl` **mất dữ liệu khi restart** và không chia sẻ giữa node.
5. Secret remember-me được inject từ environment; trong production phải bảo vệ key, cookie, HTTPS và có kế hoạch rotation.
6. `formLogin(...permitAll())` cho phép dùng trang login mặc định/processing endpoints; không mở toàn bộ URL.
7. `anyRequest().denyAll()` giúp những endpoint chưa khai báo không tự public.
8. Spring Security quản lý logout và CSRF; không gọi `csrf.disable()` chỉ để gọi admin POST từ curl.
9. Method `migrateSession()` bảo vệ chống session fixation bằng thay session ID/session migration theo semantics của Servlet runtime.
10. `ROLE_ADMIN` (do `.roles("ADMIN")`) mới được phép thu hồi, không phải user thông thường.

**Chú ý về giới hạn:** nhớ-me auto-authentication có thể phát sinh session theo một vòng đời riêng; để bảo đảm giới hạn đồng thời trong nhiều loại authentication/provider, cần test end-to-end cho cả remember-me và login tương tác trên stack của ứng dụng. `maximumSessions(1)` không phải giải pháp “global device inventory” độc lập với session registry.

### 6.6. src/main/java/demo/AccessRevocationService.java

~~~java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.stereotype.Service;

@Service
public class AccessRevocationService {

    private final SessionRegistry registry;
    private final PersistentTokenRepository tokens;

    public AccessRevocationService(
            SessionRegistry registry,
            PersistentTokenRepository tokens) {
        this.registry = registry;
        this.tokens = tokens;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public int revoke(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("Invalid username");
        }

        int expired = 0;
        for (Object candidate : registry.getAllPrincipals()) {
            if (candidate instanceof UserDetails details
                    && username.equals(details.getUsername())) {
                for (SessionInformation info
                        : registry.getAllSessions(candidate, false)) {
                    info.expireNow();
                    expired++;
                }
            }
        }

        // Thu hồi persistent remember-me series của username.
        tokens.removeUserTokens(username);
        return expired;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public int activeSessions(String username) {
        int count = 0;
        for (Object candidate : registry.getAllPrincipals()) {
            if (candidate instanceof UserDetails details
                    && username.equals(details.getUsername())) {
                count += registry.getAllSessions(candidate, false).size();
            }
        }
        return count;
    }
}
~~~

**Giải thích các giới hạn chính xác:**

- `SessionRegistry#getAllPrincipals()` trả principal objects, không nhất thiết là string username. Demo dùng `UserDetails` do form login in-memory tạo; nếu OAuth2/OIDC login, custom principal hoặc một số provider khác, logic nhận diện **phải chỉnh theo kiểu principal và khóa định danh ổn định**. Chỉ so username khi đây là khóa chính được bảo đảm duy nhất trong phạm vi ứng dụng.
- `getAllSessions(candidate, false)` trả các phiên chưa expired mà registry biết. `expireNow()` **chỉ đánh dấu**, không phải HTTP call ngắt một phiên đang xử lý.
- `removeUserTokens(username)` trả `void`, nên service **không thể nói chính xác có bao nhiêu token đã bị xóa**. Response sẽ chỉ xác nhận đã **yêu cầu thực hiện** thao tác removal; không gắn số lượng token ảo.
- Nếu target user đã đổi password, có session từ node khác hoặc access token JWT riêng, hai bước trên **không tự giải quyết tất cả**. Xem mục 11.
- Trong production, cần audit người thực hiện, lý do thu hồi, kiểm tra target, authorization chi tiết, CSRF, rate limiting và không làm lộ dữ liệu session ID trong response.
- `@PreAuthorize` có tác dụng khi service được gọi qua **Spring-managed bean/proxy**. Tạo service bằng `new` trong unit test bên dưới chỉ kiểm tra **logic thu hồi**, không kiểm tra method-security proxy; HTTP test kiểm tra quyền.

### 6.7. src/main/java/demo/LabController.java

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class LabController {

    private final AccessRevocationService revocation;

    public LabController(AccessRevocationService revocation) {
        this.revocation = revocation;
    }

    @GetMapping("/")
    @ResponseBody
    public Map<String, String> home() {
        return Map.of("message", "session-lab");
    }

    @GetMapping("/health")
    @ResponseBody
    public Map<String, String> health() {
        return Map.of("status", "up");
    }

    @GetMapping("/me")
    @ResponseBody
    public Map<String, Object> me(Authentication authentication) {
        List<String> roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList();

        return Map.of(
            "user", authentication.getName(),
            "authenticationType",
                authentication.getClass().getSimpleName(),
            "authorities", roles
        );
    }

    @GetMapping("/admin/revoke-form")
    public String revokeForm() {
        return "revoke-form";
    }

    @GetMapping("/admin/sessions")
    @ResponseBody
    public Map<String, Object> activeSessions(
            @RequestParam String username) {
        return Map.of(
            "user", username,
            "activeSessions", revocation.activeSessions(username)
        );
    }

    @PostMapping("/admin/revoke")
    @ResponseBody
    public Map<String, Object> revoke(
            @RequestParam String username) {
        int expired = revocation.revoke(username);
        return Map.of(
            "user", username,
            "sessionsMarkedExpired", expired,
            "rememberMeTokenRemovalRequested", true
        );
    }
}
~~~

`/admin/revoke` **không** trả session ID hoặc raw token. `sessionsMarkedExpired` chỉ là số phiên registry đã đánh dấu, không phải bằng chứng mọi trình duyệt hoặc mọi access token toàn hệ thống đã bị thu hồi.

Phía controller chỉ nhận target `username`; danh tính **quản trị viên** phải được xác thực qua `Authentication` và kiểm tra quyền bằng filter + method security, không lấy quyền từ một hidden field như `isAdmin=true`.

### 6.8. src/main/resources/templates/revoke-form.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Thu hồi truy cập</title>
</head>
<body>
    <h1>Thu hồi phiên và remember-me token</h1>
    <p>Chỉ tài khoản ROLE_ADMIN truy cập được trang này.</p>

    <form method="post" action="/admin/revoke">
        <label for="username">Tài khoản cần thu hồi</label>
        <input id="username" name="username" type="text"
               maxlength="100" required>
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">
        <button type="submit">Thu hồi</button>
    </form>
</body>
</html>
~~~

Form POST chứa field CSRF **tường minh** lấy từ Spring Security request. `action="/admin/revoke"` giả định demo chạy ở root context path; nếu đặt dưới context path khác, dùng Thymeleaf `@{/admin/revoke}` và kiểm tra HTML cuối. Nếu dùng `th:action`, Spring/Thymeleaf có thể tự chèn CSRF input; tránh thêm hai field giống nhau.

Trang GET chỉ được xem bởi admin, nhưng **ẩn nút hoặc ẩn form không phải kiểm soát quyền**. Chính `SecurityFilterChain` và `@PreAuthorize` phải chặn POST trái phép.

## 7. Chạy thực hành bằng hai browser profile

### 7.1. Chuẩn bị secret và chạy Maven

Trên PowerShell (dùng key local, **không** dùng trong production):

~~~powershell
$env:APP_REMEMBER_ME_KEY = "LOCAL-DEMO-ONLY-change-to-a-long-random-key"
mvn spring-boot:run
~~~

Trên bash/zsh:

~~~bash
export APP_REMEMBER_ME_KEY="LOCAL-DEMO-ONLY-change-to-a-long-random-key"
mvn spring-boot:run
~~~

Mở địa chỉ:

~~~text
http://localhost:8080/login
~~~

Tài khoản demo:

| Username | Password | Quyền |
| --- | --- | --- |
| `alice` | `demo-only` | `ROLE_USER` |
| `bob` | `demo-only` | `ROLE_USER` |
| `admin` | `demo-only` | `ROLE_ADMIN` |

Đây là tài khoản giả dùng trên localhost. Production phải dùng store xác thực thích hợp, password hashing được bảo vệ, MFA khi phù hợp, HTTPS và session cookie được cấu hình an toàn.

### 7.2. Kịch bản A: tối đa một phiên đăng nhập

1. Mở browser profile A, đăng nhập Alice tại `/login`.
2. Truy cập `/me`; JSON phải có `"user":"alice"`.
3. Mở browser profile B độc lập cookie và đăng nhập Alice.
4. Truy cập `/me` trên B, kỳ vọng B vẫn xác thực.
5. Reload `/me` trên A: với `maxSessionsPreventsLogin(false)`, session A được coi là expired; hành vi chuyển hướng/thông báo có thể tùy cấu hình/handler, thường dẫn về login với tham số hết hạn.
6. Đăng nhập Bob trong profile khác: không được coi là cùng principal Alice, trừ khi ứng dụng tùy biến identity mapping.

Đừng dùng hai tab chung profile để kiểm chứng vì thường chung cookie. Không giả định request A đang chạy bị hủy ngay khi B login; kiểm tra **request mới** ở A.

### 7.3. Kịch bản B: nhớ đăng nhập

1. Đăng nhập Alice và chọn remember-me (nếu trang login mặc định không hiển thị tùy bản cấu hình, form custom có thể gửi field `remember-me=on` cùng CSRF).
2. Quan sát response login có cookie `remember-me`. **Không copy giá trị cookie ra log hoặc chia sẻ ảnh chứa secret.**
3. Mất session cookie hoặc để session timeout nhưng giữ remember-me cookie hợp lệ.
4. Gọi `/me`: nếu remember-me được chấp nhận, Authentication có thể trở thành `RememberMeAuthenticationToken`; JSON demo trả `authenticationType` giúp phân biệt.
5. Đăng xuất bằng POST `/logout` có CSRF token. Cookie remember-me phải được xử lý xóa và repository xử lý token liên quan.
6. Thử giữ cookie cũ nhưng đã bị thu hồi: yêu cầu xác thực remember-me bằng token series không còn ở repository phải thất bại.

**Không** xóa tay session cookie trong môi trường thực chỉ để thử bypass; dùng browser profile/test environment có quyền kiểm soát.

### 7.4. Kịch bản C: admin thu hồi Alice

1. Đăng nhập Alice ở profile A, có thể tích chọn remember-me.
2. Đăng nhập admin ở profile C.
3. Admin mở `/admin/revoke-form`, nhập `alice`, nhấn Thu hồi.
4. Response JSON có `sessionsMarkedExpired` (theo registry), không có session IDs hay token.
5. Alice thử request **mới** tới `/me`: session đã mark expired phải bị xử lý là hết hiệu lực; remember-me series cũ bị xóa nên không khôi phục lại bằng cookie đó.
6. Alice **vẫn có thể đăng nhập lại bằng mật khẩu đúng**. “Thu hồi session/token” **không phải khóa tài khoản** hoặc thay password; nếu muốn chặn login tương lai, phải thêm chính sách disable/lock account và cập nhật/kiểm thử provider.

Kiểm tra `GET /admin/sessions?username=alice` dưới admin role: số phiên active trong registry dự kiến giảm về 0 sau khi đánh dấu. Nếu có node khác không dùng chung registry, đây **chưa phải tổng số phiên toàn hệ thống**.

### 7.5. Kịch bản D: quyền và CSRF

- Alice gọi `GET /admin/revoke-form` → **403** khi đã đăng nhập nhưng thiếu `ROLE_ADMIN`.
- Alice gọi `POST /admin/revoke` có CSRF token → **403** do authorization.
- Admin gọi `POST /admin/revoke` **thiếu CSRF token** → **403** do CSRF.
- Admin gọi `POST /admin/revoke` **có CSRF token hợp lệ** → vào controller và service, nhận JSON thu hồi.
- Người chưa login truy cập `/me` → thường được chuyển tới `/login` qua form-login entry point.

Tách test CSRF và test role, vì cùng một mã **403** có thể được tạo bởi hai lý do khác nhau.

## 8. MockMvc và unit tests: tái hiện hành vi mà không lộ token

### 8.1. src/test/java/demo/LabHttpSecurityTests.java

~~~java
package demo;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties =
    "app.remember-me.key=unit-test-only-long-random-placeholder")
class LabHttpSecurityTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    SessionRegistry registry;

    @Test
    void homeIsPublic() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("session-lab"));
    }

    @Test
    void anonymousProfileRedirectsToLogin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isFound())
            .andExpect(header().string(
                HttpHeaders.LOCATION, containsString("/login")));
    }

    @Test
    void loggedInUserCanReadOwnIdentity() throws Exception {
        mvc.perform(get("/me").with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void nonAdminCannotSeeRevocationForm() throws Exception {
        mvc.perform(get("/admin/revoke-form")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanSeeCsrfProtectedForm() throws Exception {
        mvc.perform(get("/admin/revoke-form")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("name=\"_csrf\"")));
    }

    @Test
    void adminPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/admin/revoke")
                .with(user("admin").roles("ADMIN"))
                .param("username", "alice"))
            .andExpect(status().isForbidden());
    }

    @Test
    void userPostWithCsrfStillForbidden() throws Exception {
        mvc.perform(post("/admin/revoke")
                .with(user("alice").roles("USER"))
                .with(csrf())
                .param("username", "bob"))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminPostWithCsrfIsAllowed() throws Exception {
        mvc.perform(post("/admin/revoke")
                .with(user("admin").roles("ADMIN"))
                .with(csrf())
                .param("username", "not-currently-signed-in"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.rememberMeTokenRemovalRequested").value(true));
    }

    @Test
    void validPasswordCreatesInteractiveLogin() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "bob")
                .param("password", "demo-only"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/me"));
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "bob")
                .param("password", "incorrect"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void rememberMeLoginIssuesCookie() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only")
                .param("remember-me", "on"))
            .andExpect(status().isFound())
            .andReturn();

        Cookie cookie = result.getResponse().getCookie("remember-me");
        assertThat(cookie).isNotNull();
        assertThat(cookie.getMaxAge()).isPositive();
    }

    @Test
    void laterLoginMarksEarlierSessionExpired() throws Exception {
        MvcResult first = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only"))
            .andExpect(status().isFound())
            .andReturn();

        MockHttpSession sessionA =
            (MockHttpSession) first.getRequest().getSession(false);
        assertThat(sessionA).isNotNull();

        MvcResult second = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only"))
            .andExpect(status().isFound())
            .andReturn();

        MockHttpSession sessionB =
            (MockHttpSession) second.getRequest().getSession(false);
        assertThat(sessionB).isNotNull();
        assertThat(sessionB.getId()).isNotEqualTo(sessionA.getId());

        boolean firstExpired = registry.getAllPrincipals().stream()
            .filter(p -> p instanceof UserDetails details
                && details.getUsername().equals("alice"))
            .flatMap(p -> registry.getAllSessions(p, true).stream())
            .anyMatch(info -> info.getSessionId().equals(
                sessionA.getId()) && info.isExpired());

        assertThat(firstExpired).isTrue();
    }

    @Test
    void logoutRequiresCsrf() throws Exception {
        mvc.perform(post("/logout")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validLogoutRedirects() throws Exception {
        mvc.perform(post("/logout")
                .with(user("alice").roles("USER"))
                .with(csrf()))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/login?logout"));
    }

    @Test
    void unlistedPathIsNotPublic() throws Exception {
        mvc.perform(get("/not-listed")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Lưu ý về tính độc lập test:** các test HTTP đăng nhập có thể tạo session/remember-me state trong `SessionRegistry` hoặc repository chung của một `ApplicationContext`. Trong bộ test thực tế, nên cleanup có chủ đích từng session/token hoặc tạo fixture riêng để không phụ thuộc thứ tự chạy, đặc biệt khi chạy song song. Test concurrency ở đây tạo **hai session mới** và khẳng định session A được mark expired sau login B, nhưng một suite production nên thêm kiểm thử request tiếp theo của session A, cookie rotation và trạng thái repository qua test containers/session store thật.

Các test với `.with(user())` **chỉ giả Authentication trên request**, không kiểm tra password login thật. Vì vậy có test POST login với đúng/sai password riêng. `@TestPropertySource` cung cấp secret giả riêng cho test, không phải secret production.

### 8.2. src/test/java/demo/AccessRevocationServiceTests.java

~~~java
package demo;

import java.util.Date;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.web.authentication.rememberme.InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentRememberMeToken;

import static org.assertj.core.api.Assertions.assertThat;

class AccessRevocationServiceTests {

    @Test
    void marksSessionExpiredAndDeletesPersistentToken() {
        var registry = new SessionRegistryImpl();
        var tokens = new InMemoryTokenRepositoryImpl();
        var service = new AccessRevocationService(registry, tokens);

        var alice = User.withUsername("alice")
            .password("{noop}not-used")
            .roles("USER")
            .build();

        registry.registerNewSession("demo-session-1", alice);
        tokens.createNewToken(new PersistentRememberMeToken(
            "alice", "demo-series-1", "demo-token-1", new Date()
        ));

        assertThat(service.activeSessions("alice")).isEqualTo(1);
        assertThat(tokens.getTokenForSeries("demo-series-1"))
            .isNotNull();

        int expired = service.revoke("alice");

        assertThat(expired).isEqualTo(1);
        assertThat(registry.getSessionInformation(
            "demo-session-1").isExpired()).isTrue();
        assertThat(service.activeSessions("alice")).isZero();
        assertThat(tokens.getTokenForSeries("demo-series-1"))
            .isNull();
    }
}
~~~

**Đây là unit test thuần** của logic `AccessRevocationService`: dùng `new AccessRevocationService(...)`, không qua proxy nên không kiểm tra `@PreAuthorize`. HTTP tests trước đó chứng minh chỉ ROLE_ADMIN được gọi endpoint; để kiểm tra method security trực tiếp qua proxy, bổ sung `@SpringBootTest` với `@Autowired AccessRevocationService` và `@WithMockUser` cho cả trường hợp admin và user bị `AccessDeniedException`.

### 8.3. Chạy test và kỳ vọng

~~~bash
mvn test
~~~

Theo các file trên, có **16 test**: 15 MockMvc tests và 1 unit test của revocation service. Mục tiêu là các test đều pass khi project được cấu hình đúng.

**Đây là kết quả kỳ vọng, không phải output Maven đã chạy thực tế trong lúc soạn bài.** Với test concurrency ở environment có listener/session simulation khác, cần xác nhận hoạt động của `MockHttpSession` và session events trên phiên bản cụ thể. Một integration test với embedded server và hai cookie jars thường phản ánh hành vi browser/sessions thực tế tốt hơn.

Chạy riêng lớp:

~~~bash
mvn -Dtest=LabHttpSecurityTests test
mvn -Dtest=AccessRevocationServiceTests test
~~~

Không gọi `csrf.disable()` chỉ để giúp test POST pass: điều đó khiến test ngừng mô phỏng chính lớp phòng vệ cần kiểm tra.

## 9. Phân tích lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Hai browser vẫn dùng được cùng lúc | Thực ra cùng cookie; SessionRegistry không đăng ký đúng; login không đi qua session strategy; test chưa gửi request sau expiry | Dùng hai browser profiles; kiểm tra session IDs, registry, login pipeline và next request |
| Người mới login bị chặn | `maxSessionsPreventsLogin(true)`, session cũ chưa được cleanup, registry giữ record cũ | Chọn policy chính xác; bật session destroy events; kiểm tra registry |
| Session A bị expire nhưng vẫn hiện trang cache | Browser cache hoặc request chưa chạm server | Dùng request bảo vệ mới, xác minh network status và session |
| Remember-me không sinh cookie | Form không gửi `remember-me`, login thất bại, rememberMe config thiếu users/repository, cookie policy | Kiểm tra POST fields, cookie attributes; không log cookie value |
| Remember-me mất tác dụng sau restart | InMemoryTokenRepositoryImpl mất record | Dùng persistent shared token repository trong production |
| Logout xong user vẫn đăng nhập lại ở thiết bị khác | Logout thường xử lý phiên/browser hiện tại, không mặc định hết mọi session khác | Dùng admin/global revocation nếu nghiệp vụ yêu cầu |
| Xóa persistent tokens nhưng session vẫn có quyền | Token repo độc lập session | Expire session registry hoặc invalidate session tương ứng |
| Mark session expired nhưng remember-me lại xác thực | Cookie remember-me chưa bị thu hồi | Xóa token series user, kiểm tra remember-me behavior |
| Admin POST trả 403 | Thiếu CSRF hoặc ROLE_ADMIN | Với test role gửi `csrf()` hợp lệ; kiểm tra authority thật |
| Role `ADMIN` không match `hasRole("ADMIN")` | Thiếu prefix `ROLE_` | Dùng `.roles("ADMIN")` hoặc `authorities("ROLE_ADMIN")` |
| SessionRegistry báo 0 dù user còn request được | Một node khác; remember-me auto-auth không theo dõi như interactive login; principal không cùng identity | Dùng registry chia sẻ, audit auth types, xác định identity ổn định |
| Token bị đánh cắp vẫn dùng được sau đổi password | Chưa có workflow revoke token/sessions khi đổi password | Gọi revocation sau password reset, khóa tài khoản khi cần |
| `@PreAuthorize` bị bỏ qua trong unit test | Service tạo bằng `new`, không qua Spring proxy | Dùng Spring-managed bean cho method-security integration test |
| Session quá nhiều sau khi đóng tab | Đóng tab không mặc nhiên invalidate server session; hết hạn dựa vào timeout/events | Cấu hình timeout, cleanup và đo đạc registry |
| Xảy ra logout liên tục trên nhiều node | Session registry chỉ trong memory, shared key/token repository không nhất quán | Spring Session/backed registry và kho persistent tokens dùng chung |
| Session fixation sau login | Chưa áp session fixation protection đúng ở web app | Kiểm tra migration session ID và cookie sau login |
| Response logout trả 302 nhưng vẫn còn dữ liệu | Logout redirect không tự chứng minh session/token đã bị thu hồi | Kiểm tra session invalidation, repo và request sau logout |

## 10. Bảo mật và vận hành thực tế

### 10.1. Cơ sở dữ liệu cho persistent remember-me

`InMemoryTokenRepositoryImpl` chỉ phù hợp cho bài học. Một cấu hình production có thể dùng `JdbcTokenRepositoryImpl` và một bảng persistent token có schema tương thích release. Khi sử dụng `JdbcTokenRepositoryImpl`, cần:

- Khởi tạo schema `persistent_logins` bằng migration được quản lý (Flyway/Liquibase), không bật “tạo bảng mỗi lần” bừa bãi.
- Index/unique constraint đúng với series, bảo vệ DB backups và quyền SELECT/UPDATE/DELETE.
- Có chính sách xóa token hết hạn và giới hạn thời gian lưu.
- Giám sát tỷ lệ remember-me authentication thất bại bất thường, token reuse và hoạt động thu hồi.
- Không đưa raw token/cookie/DB secret vào log, ticket hoặc báo cáo.
- Khi rotate key, phân tích tác động lên cookie đã phát và rollout đồng bộ các node.

Đây là định hướng production; ví dụ runnable không giả vờ có DB/H2/JDBC khi `pom.xml` chưa khai báo dependencies đó.

### 10.2. Spring Session cho nhiều node

Nếu có nhiều instance sau load balancer, `SessionRegistryImpl` chỉ biết sessions của **JVM hiện tại**. Cần thiết kế session store phân tán, chẳng hạn Spring Session cùng registry tương thích (ví dụ `SpringSessionBackedSessionRegistry` khi dùng repository tương ứng), hoặc cơ chế quản lý active sessions riêng theo domain nghiệp vụ.

**Không tự động suy rằng** chỉ thêm Redis vào ứng dụng sẽ làm admin `expireNow()` của `SessionRegistryImpl` thu hồi mọi node. Cần dùng đúng registry tích hợp store và kiểm thử propagation/revocation ở môi trường multi-node.

### 10.3. Thu hồi quyền không đồng nghĩa khóa tài khoản

Giả sử admin gọi revoke cho Alice tại thời điểm T:

- Session đã theo dõi được mark expired.
- Persistent remember-me records của Alice bị xóa.
- Request đang xử lý tại T có thể đã qua authorization và tiếp tục hoàn tất.
- Nếu Alice vẫn biết đúng password, có thể **login mới** ngay sau đó.
- Nếu ứng dụng có access token JWT tự chứa claims với `exp` còn dài, các API stateless có thể tiếp tục chấp nhận JWT **trừ khi** có cơ chế token revocation, session/credential version, introspection hoặc expiry ngắn kèm refresh-token revocation.
- Nếu có API keys hay mTLS certificates, cần workflow thu hồi riêng cho từng credential type.

Vì thế, với sự cố tài khoản bị xâm phạm, thường cần **disable/lock account hoặc reset credential**, revoke refresh tokens/API keys, rotate secrets nếu cần, expire sessions, remove remember-me tokens và ghi audit. Chỉ một lệnh `expireNow()` là chưa đủ để gọi là “đăng xuất mọi nơi ngay lập tức”.

### 10.4. Cookie và browser safety

- Dùng **HTTPS** và `Secure` cho cookie trên production; local HTTP demo không đại diện cấu hình production.
- `HttpOnly` để script bình thường không đọc cookie; thêm `SameSite` phù hợp với form login/SSO flow.
- Kiểm tra Domain/Path và behavior sau reverse proxy; không log `Cookie`/`Set-Cookie` có token.
- CSRF token cho POST logout/revoke phải đến từ server; `permitAll()` không thay kiểm tra CSRF.
- Có session timeout và remember-me token lifetime riêng; không cho cookie vô hạn.
- Đối với endpoint nhạy cảm, cân nhắc step-up authentication, `fullyAuthenticated()`, MFA, audit và notification tới chủ tài khoản.

### 10.5. Revocation audit và race conditions

Một quy trình thu hồi trưởng thành nên ghi nhận **ai**, **đối tượng nào**, **thời điểm**, **lý do**, **số session mark expired** và **kết quả thực hiện repository operation** mà không ghi raw tokens hay session IDs vào log ứng dụng chung.

Nếu request được xác thực **trước** thời điểm T rồi thực thi đến sau T, việc mark expired ở T có thể không ngăn thao tác đã khởi chạy. Nếu nghiệp vụ yêu cầu hard cutoff cho giao dịch tài chính/quyền cao, phải đặt kiểm tra trạng thái tài khoản/credential version ngay trong transaction/service authorization và thiết kế cơ chế hủy/rollback phù hợp, không chỉ dựa vào servlet session concurrency.

## 11. Checklist nghiệm thu bài thực hành

- [ ] Form login dùng password đã encode; demo password không đưa vào production.
- [ ] Browser A và B **không chia sẻ cookie jar**, có thể xác định session riêng.
- [ ] `maximumSessions(1)` kết hợp `maxSessionsPreventsLogin(false)` đúng yêu cầu.
- [ ] `SessionRegistry` được dùng thống nhất giữa concurrency policy và revocation service.
- [ ] `HttpSessionEventPublisher` được đăng ký trong servlet runtime thích hợp.
- [ ] Session cũ bị mark expired sau login mới và bị xử lý ở **request tiếp theo**.
- [ ] Remember-me chỉ phát cookie khi login yêu cầu và authentication thành công.
- [ ] Session timeout không được nhầm với remember-me token expiry.
- [ ] Remember-me token repository có server-side persistence khi yêu cầu thu hồi bền vững.
- [ ] Logout POST kèm CSRF, invalidates session và xử lý remember-me.
- [ ] Admin revoke POST kèm CSRF và cần ROLE_ADMIN ở URL **và** service.
- [ ] Revocation expire active sessions **và** remove persistent tokens; không báo số token đã xóa nếu API không cung cấp.
- [ ] Dữ liệu response không chứa raw cookie, token, password hoặc session ID.
- [ ] Test có cả positive/negative cho authorization và CSRF để tránh false positive.
- [ ] Test concurrency bao phủ hai phiên khác nhau; production có integration test với browser hoặc embedded server.
- [ ] Nếu chạy nhiều node, có shared session registry/store, persistent token store, keys và end-to-end revocation test.
- [ ] Nếu cần “khóa tài khoản”, có disable/credential revocation riêng; không nhầm session expiry với vô hiệu hóa password/JWT.
- [ ] Có quan sát, audit và cleanup token/sessions hết hạn nhưng không tiết lộ secrets.

## 12. Câu hỏi và bài tập mở rộng

**1.** Vì sao xóa cookie remember-me trong browser không đảm bảo thu hồi mọi thiết bị?

**Trả lời:** Browser khác có thể giữ cookie riêng. Server phải xóa record token tương ứng trong persistent repository hoặc có cơ chế revocation tương đương.

**2.** `SessionInformation.expireNow()` có chủ động hủy ngay HTTP request đang xử lý không?

**Trả lời:** Không. Nó đánh dấu phiên hết hiệu lực; filter kiểm tra ở request tiếp theo. Một request đang chạy có thể tiếp tục nếu đã qua bước xác thực/quyền.

**3.** Nếu Alice bị revoke nhưng vẫn biết password, điều gì xảy ra?

**Trả lời:** Alice có thể login mới, trừ khi tài khoản đã bị disable/lock hoặc credential thay đổi. Revocation session/token không tự là khóa account.

**4.** Tại sao phải dùng `SessionRegistry` chung cho policy giới hạn phiên và admin revoke?

**Trả lời:** Nếu hai thành phần xem hai registry khác nhau, admin có thể không thấy các phiên được cấu hình concurrency theo dõi. Trong cluster còn phải chia sẻ trạng thái qua store phù hợp.

**5.** `maxSessionsPreventsLogin(true)` khác `false` ra sao?

**Trả lời:** `true` từ chối login mới khi đạt giới hạn; `false` cho login mới, đánh dấu phiên cũ expired. Cần chọn theo trải nghiệm người dùng và threat model.

**6.** Tại sao admin POST có `ROLE_ADMIN` mà vẫn gặp 403?

**Trả lời:** CSRF token có thể thiếu/sai. Với test quyền cần thêm token hợp lệ; với test CSRF giữ đúng role nhưng bỏ token.

**7.** `RememberMeAuthenticationToken` có luôn ngang mức xác thực password vừa nhập không?

**Trả lời:** Không. Với thao tác nhạy cảm, dùng `fullyAuthenticated()` hoặc step-up authentication khi cần.

**8.** Khi một node có `SessionRegistryImpl`, node khác tự động biết session của Alice không?

**Trả lời:** Không. Registry trong memory là cục bộ JVM. Multi-node cần registry/store phân tán và kiểm thử đồng bộ.

**9.** Nếu xóa persistent remember-me series nhưng session đã authenticated vẫn còn, user đã hết quyền chưa?

**Trả lời:** Chưa. Xóa token không tự làm session hiện hành mất SecurityContext. Cần expire/invalidate session và kiểm tra chính sách cấp quyền phù hợp.

**10.** Cách kiểm thử revocation có chất lượng hơn một assertion HTTP 200 là gì?

**Trả lời:** Kiểm tra session record đã mark expired, persistent series đã bị xóa, request tiếp theo bị chặn, browser cookie cũ không tái xác thực được, và user thiếu quyền không thể gọi endpoint — ở môi trường multi-node cần kiểm tra qua các instance khác nhau.

### Bài tập A: chính sách “giữ thiết bị cũ”

Đổi `maxSessionsPreventsLogin(false)` thành `true`. Kiểm tra profile A vẫn dùng được và profile B không tạo phiên mới khi A đang active. Mô tả cách xử lý UX khi đăng nhập bị từ chối mà không tiết lộ session ID hoặc thiết bị của người khác.

### Bài tập B: buộc xác thực mạnh lại

Thêm một endpoint `POST /account/change-password` được bảo vệ bằng `fullyAuthenticated()` và CSRF. So sánh phản hồi khi user có authentication từ form login và khi chỉ tự động trở lại bằng remember-me; không cho phép thay password chỉ dựa vào cookie dài hạn.

### Bài tập C: thiết kế production

Phác thảo migration `InMemoryTokenRepositoryImpl` sang `JdbcTokenRepositoryImpl`, chuyển session sang shared store, thay registry bằng giải pháp tương thích store, thêm audit/lock account/refresh token revocation. Giải thích kết quả mong muốn với request in-flight và eventual consistency của từng node.

---

**Kết luận:** Session concurrency, remember-me và thu hồi truy cập là **ba vấn đề liên quan nhưng không đồng nhất**. `maximumSessions(1)` giới hạn session được registry theo dõi; persistent remember-me lưu credential dài hạn riêng; revocation đáng tin cần đánh dấu session expired **và** xóa persistent token series. Logout một browser không mặc định chặn mọi device; `expireNow()` không ngắt request đang chạy; và mô hình in-memory chỉ phục vụ một JVM. Hãy kết hợp đúng filter, registry, repository, method/URL authorization, CSRF, cookie security, test và vận hành để đạt mức bảo vệ mà sản phẩm thực sự yêu cầu.