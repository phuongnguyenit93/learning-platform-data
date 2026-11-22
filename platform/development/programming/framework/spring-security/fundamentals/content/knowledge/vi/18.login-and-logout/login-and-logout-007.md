# Remember-me khác với kéo dài phiên đăng nhập

> **Spring Security – fundamentals** · Nhóm: **Đăng nhập và đăng xuất**. Bài này phân biệt cơ chế tự xác thực lại bằng remember-me credential với việc giữ một phiên HTTP tồn tại lâu hơn. Trọng tâm là Servlet/Spring MVC và các API Spring Security 6.x; khi dùng phiên bản khác cần đối chiếu tài liệu tương ứng.

## 1. Bạn sẽ học được gì?

Sau bài này, bạn có thể giải thích vòng đời của `HttpSession`, session ID và remember-me cookie; hiểu Spring Security tự đăng nhập lại khi không còn session ra sao; phân biệt `RememberMeAuthenticationToken` với phiên xác thực đầy đủ; so sánh token hash-based và persistent token; cấu hình Java 17/Spring Boot; kiểm thử thực tế và thiết kế an toàn với logout, CSRF, cookie flags, timeout, revocation.

**Ý chính ngay từ đầu:** kéo dài session là **giữ trạng thái xác thực hiện có** lâu hơn; remember-me là **giữ một bằng chứng riêng để xác thực lại** nếu trạng thái phiên cũ đã mất. Chúng có thể cùng tồn tại, nhưng không phải một cơ chế.

## 2. HTTP không tự ghi nhớ user qua các request

HTTP gửi các request độc lập về ngữ nghĩa. Request đến sau không tự mang thông tin của request trước. Ứng dụng web truyền thống duy trì login bằng cách gửi một mã phiên từ browser tới server ở mỗi request:

~~~text
Browser: Cookie: JSESSIONID=sid1
    |
    v
Server tra SessionStore[sid1] -> SecurityContext(Authentication: alice)
    |
    v
Xét quyền cho request hiện tại
~~~

Session thường ở RAM/server-side store; browser giữ mã tra cứu. `JSESSIONID` là tên cookie phổ biến trên Servlet stack, nhưng có thể đổi khi dùng Spring Session hoặc cấu hình container. Cookie không phải toàn bộ đối tượng session. Có cookie `JSESSIONID` cũng **không tự chứng minh user đã đăng nhập**: một anonymous session có thể được tạo để lưu CSRF token hoặc saved request.

Trong Spring Security Servlet, `SecurityContext` chứa `Authentication`. `SecurityContextRepository` phụ trách cách đọc/lưu context; một triển khai phổ biến là `HttpSessionSecurityContextRepository` hoặc một `DelegatingSecurityContextRepository`. `SecurityContextHolder` cung cấp context trong quá trình xử lý request, không phải bản thân kho dữ liệu bền vững qua mọi request.

## 3. “Kéo dài phiên đăng nhập” thực chất thay đổi gì?

Giả sử server cấu hình idle timeout của session từ 20 phút lên 8 giờ:

~~~properties
server.servlet.session.timeout=8h
~~~

Điều này ảnh hưởng thời gian server giữ `HttpSession` không hoạt động, tùy cách container/session store quản lý TTL. Nếu session còn và browser gửi session ID tương ứng, Spring Security có thể khôi phục authentication đã lưu. **Không cần tự xác thực lại bằng remember-me.**

Nếu session hết hạn/bị invalidated hoặc browser không còn gửi đúng session ID, tăng timeout cũng không tạo ra credential mới. Server không thể khôi phục session đã biến mất chỉ nhờ nhớ tên người dùng trong giao diện.

Tăng timeout quá dài có những hệ quả:

- Credential session bị đánh cắp có thể dùng lâu hơn nếu chưa revoke.
- Session store phải giữ nhiều đối tượng hơn, chi phí RAM/cache/replication tăng.
- Phân biệt “người dùng vừa nhập mật khẩu” với “thiết bị đang được nhớ” trở nên khó hơn.
- TTL của cookie browser và idle timeout server không nhất thiết đồng bộ: `Max-Age` của cookie không giữ session server sống mãi.
- Browser có thể khôi phục session cookies sau restart tùy chính sách restore; không nên lấy việc đóng tab làm ranh giới bảo mật.

Vì thế, **“để user không phải login quá thường xuyên”** không luôn đồng nghĩa với **“giữ session một tháng”**.

## 4. Remember-me là gì?

Remember-me, còn gọi là **persistent-login authentication**, là cơ chế để ứng dụng nhận diện lại user sau khi phiên đăng nhập HTTP bình thường không còn. Hệ thống thường cấp **cookie riêng** khi người dùng đăng nhập thành công và chọn “Remember me” hoặc “Remember this device”.

Trong Servlet/Spring Security, khi request không có `Authentication` trong context, `RememberMeAuthenticationFilter` có thể dùng `RememberMeServices.autoLogin(...)` để xác minh remember-me cookie. Nếu hợp lệ, nó tạo `RememberMeAuthenticationToken` cho request. Theo chính sách session, hệ thống có thể tạo/lưu phiên mới, nhưng điều đó **không hồi sinh session cũ**.

### Hai cookie khác mục đích

| Thành phần | Ví dụ tên | Bản chất | Khi nào dùng? |
| --- | --- | --- | --- |
| Session cookie | `JSESSIONID` | Mang session ID để tìm phiên đã tồn tại | Request có session hợp lệ |
| Remember-me cookie | `remember-me` | Mang remember credential để tự xác thực lại | Khi không có authentication hợp lệ trong context |
| CSRF token | `_csrf` trong form hoặc token trong header | Chứng minh request thay đổi trạng thái hợp lệ theo CSRF mechanism | Các thao tác không an toàn như POST/PUT/DELETE |
| User password | Không nên lưu trong cookie | Bí mật để xác thực tương tác | Login/reauthentication |

Tên cookie cuối cùng có thể tùy chỉnh. **Session cookie và remember-me cookie đều là credential nhạy cảm**; người có được bản sao hợp lệ có thể có nguy cơ giả mạo user trong phạm vi chính sách. Không chia sẻ hoặc log giá trị nguyên văn.

## 5. Hai dòng thời gian: khác nhau ở lúc mất session

### Kịch bản A: không có remember-me

~~~text
09:00 Alice login -> tạo session S1 -> JSESSIONID=s1
09:10 request có s1 -> dùng Authentication từ S1
11:00 S1 đã timeout -> không còn Authentication
11:01 request có cookie s1 cũ -> không tìm thấy session hợp lệ
Kết quả: Alice cần login lại
~~~

Việc session timeout có thể do idle timeout, invalidation, hạ tầng store hay logout. Cookie có thể vẫn còn trên browser nhưng server không công nhận session ID cũ.

### Kịch bản B: có remember-me

~~~text
09:00 Alice login + chọn Remember me
      Server tạo S1 và remember token R1
      Browser giữ JSESSIONID=s1 và remember-me=r1

09:10 request gửi s1, r1
      S1 còn hợp lệ => dùng full Authentication từ S1
      RememberMeAuthenticationFilter không cần auto-login

11:00 S1 đã hết hạn
11:01 request mới còn remember-me=r1, không có S1 hợp lệ
      RememberMeServices xác minh r1
          - valid: tạo RememberMeAuthenticationToken cho Alice
          - invalid: không tự login; yêu cầu xác thực lại

11:02 một endpoint nhạy cảm yêu cầu fullyAuthenticated()
      remember token hợp lệ vẫn chưa đủ -> yêu cầu full login
~~~

**Kết luận:** S1 không được “kéo dài”. R1 giúp ứng dụng tạo ra authentication ở mức remember-me **sau khi S1 mất**. Hành động có thể được cho phép hay không còn tùy authorization rule.

## 6. Luồng Spring Security bên trong

Các thành phần cần hiểu:

1. `UsernamePasswordAuthenticationFilter` hoặc filter xác thực tương tác: xử lý username/password.
2. `RememberMeServices`: interface có `loginSuccess(...)`, `loginFail(...)` và `autoLogin(...)`.
3. `RememberMeAuthenticationFilter`: khi chưa có authentication, kiểm tra credential nhớ đăng nhập.
4. `TokenBasedRememberMeServices` hoặc `PersistentTokenBasedRememberMeServices`: xác minh theo từng chiến lược.
5. `RememberMeAuthenticationToken` và `RememberMeAuthenticationProvider`: biểu đạt và xác nhận remember-me authentication.
6. `SecurityContextRepository`/session handling: đọc/lưu context khi cần; không nên nhầm với remember-me token store.
7. `AuthorizationFilter`/method authorization: cuối cùng quyết định endpoint/action có cho phép remember-me authentication hay không.

Sơ đồ tổng quát:

~~~text
Request -> SecurityFilterChain
             |
             v
      Authentication đã có từ session/context?
             | YES                     | NO
             v                         v
       Authorization           RememberMeAuthenticationFilter
                                       |
                               Có remember cookie?
                                /             \
                              NO               YES
                              |                 |
                         anonymous        verify token
                                               |
                                      fail -----+----- valid
                                       |                 |
                                  anonymous   RememberMeAuthenticationToken
                                       \                 /
                                         Authorization
~~~

Đây là mô hình tổng quát, không phải mô tả chi tiết vị trí của mọi filter trong từng phiên bản.

### Khi nào phát remember-me cookie?

Với form login, remember-me service được gọi sau khi authentication thành công. Theo mặc định thường cần parameter checkbox, ví dụ `remember-me=on`. Một số cấu hình có thể dùng `alwaysRemember(true)`, nhưng làm vậy cần cân nhắc sự đồng ý của user trên máy dùng chung.

Nếu user không chọn ghi nhớ, **session bình thường vẫn có thể hoạt động**. Không có remember cookie không có nghĩa chưa login. Và browser có remember cookie nhưng request dùng full session auth thì authentication hiện tại vẫn là full, không phải remember-me.

## 7. Remember-me không ngang mức tin cậy với full login

Spring Security cho phép phân biệt:

| Trạng thái | `authenticated()` | `fullyAuthenticated()` |
| --- | --- | --- |
| Anonymous | Không đạt | Không đạt |
| `RememberMeAuthenticationToken` hợp lệ | Đạt | Không đạt |
| Login tương tác đầy đủ | Đạt | Đạt (theo trust resolver của Spring Security) |

Ví dụ DSL bên trong bean `SecurityFilterChain`:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/profile").authenticated()
    .requestMatchers("/api/strong").fullyAuthenticated()
    .anyRequest().denyAll()
);
~~~

Nếu chỉ còn remember cookie, một user có thể xem profile nhưng không thể thực hiện hành động nhạy cảm yêu cầu full login. Với form-login entry point, bị từ chối vì nhớ đăng nhập thường dẫn tới redirect về trang login, không nhất thiết là HTTP 403; hành vi còn tùy cấu hình.

`fullyAuthenticated()` **không tự chứng minh user vừa làm MFA**, nhập lại password trong 5 phút hay có mức `acr` nhất định. Nếu thao tác là chuyển tiền, đổi password, thêm thiết bị MFA, tạo API key hay xóa dữ liệu, hãy cân nhắc step-up authentication/MFA và chính sách “recent login” riêng.

Ở method security (khi bật `@EnableMethodSecurity`), có thể dùng:

~~~java
@PreAuthorize("isFullyAuthenticated()")
public void changePassword(String newPassword) {
    // Mã nghiệp vụ minh họa, cần xử lý password an toàn thực tế.
}
~~~

Fragment này không phải Java file độc lập. Không đặt password thực vào log hay lưu raw password.

## 8. Hai cơ chế remember-me được Spring Security hỗ trợ

### 8.1. Hash-based token: TokenBasedRememberMeServices

Đây là cơ chế không cần bảng token riêng. Sau login thành công, server tính một giá trị có chữ ký/hash dựa trên username, thời hạn hết hiệu lực, thuật toán, thông tin password lưu trong `UserDetailsService` và secret key. Format tổng quan trong tài liệu:

~~~text
base64(
  username + ":" + expirationTime + ":" + algorithmName + ":" +
  hash(username + ":" + expirationTime + ":" +
       storedPassword + ":" + serverKey)
)
~~~

Công thức chỉ để hiểu cách xác minh, **không tự triển khai crypto theo chuỗi trên**. Khi request đến, Spring Security kiểm tra thời hạn, load user và tái tính giá trị xác minh.

**Ưu điểm:** ít hạ tầng, dễ demo.

**Nhược điểm quan trọng:**

- Credential bị đánh cắp có thể **replay** trên thiết bị khác tới khi hết hạn hoặc đầu vào xác minh thay đổi.
- Không có server-side record cho từng token nên không dễ revoke riêng một thiết bị.
- Đổi password hash hoặc secret key có thể làm các cookie cũ mất hiệu lực; key rotation có thể ảnh hưởng nhiều user.
- Secret key phải mạnh, giữ bí mật và nhất quán giữa các application instances.
- Cookie không chứa raw password, nhưng triển khai này có thể để lộ tên username trong payload đã encode.

### 8.2. Persistent token: PersistentTokenBasedRememberMeServices

Cơ chế này cần `PersistentTokenRepository` với token state ở server, ví dụ JDBC. Bảng truyền thống:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

Cặp `series/token` được dùng để xác minh. Server có thể **đổi token** khi auto-login thành công và cập nhật repository, giúp giảm thời gian một credential cũ có thể tái sử dụng; token cũ xuất hiện lại có thể được coi là dấu hiệu replay/theft theo implementation.

Các class cần biết:

- `PersistentTokenRepository`: interface lưu/tra/đổi/xóa tokens.
- `JdbcTokenRepositoryImpl`: lưu trong database.
- `InMemoryTokenRepositoryImpl`: chỉ phù hợp test/minh họa, không phải production storage.
- `PersistentTokenBasedRememberMeServices`: triển khai remember-me dùng repository.

Với sản phẩm thực tế, schema mặc định chưa cung cấp đầy đủ “quản lý thiết bị”: cần thiết kế device metadata, revoke-all-devices, expiry cleanup, xử lý races/concurrent requests, token theft response và audit. Persistent token vẫn là bearer credential, không thể coi là tuyệt đối an toàn.

### So sánh nhanh

| Tiêu chí | Hash-based | Persistent |
| --- | --- | --- |
| Repository token riêng | Không | Có |
| Thông tin cookie | Username/thời hạn/chữ ký | Series + token |
| Thu hồi riêng một token | Hạn chế | Có thể thiết kế |
| Rotation khi dùng lại | Không theo repository | Có cơ chế cập nhật token |
| Password change | Thường làm cookie cũ không xác minh được | Phải phối hợp revoke token theo policy |
| Multi-instance | Shared secret & user store nhất quán | Shared DB/token store và config |
| Vận hành | Đơn giản hơn | Thêm lưu trữ, cleanup, concurrency |
| Rủi ro khi bị đánh cắp | Replay đến expiry/đổi key/password | Có replay risk nhưng có state/rotation/thu hồi |

Spring Security docs mô tả hai loại chính và yêu cầu `UserDetailsService` phù hợp. Nếu ứng dụng xác thực qua OIDC/LDAP/JWT mà không có `UserDetailsService` tương ứng, không nên mặc định bật remember-me sẽ tự hoạt động.

## 9. Ví dụ thực hành Java 17 + Spring Boot

Ứng dụng demo dùng **Spring Boot 3.5.7** (dòng Spring Security 6.5), **Spring MVC/Servlet**, Java 17+, Maven. Có form login, remember-me hash-based, session ngắn hơn remember token, endpoint profile chấp nhận remember-me và endpoint strong đòi full login.

Cấu trúc:

~~~text
remember-demo/
  pom.xml
  src/main/java/com/example/rememberdemo/
    RememberDemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/main/resources/application.properties
  src/test/java/com/example/rememberdemo/
    RememberFlowTests.java
~~~

### 9.1. pom.xml

~~~xml
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
  <artifactId>remember-demo</artifactId>
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

### 9.2. RememberDemoApplication.java

~~~java
package com.example.rememberdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberDemoApplication.class, args);
    }
}
~~~

### 9.3. SecurityConfig.java

~~~java
package com.example.rememberdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http, UserDetailsService users)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/api/public", "/error").permitAll()
                .requestMatchers("/api/strong").fullyAuthenticated()
                .requestMatchers("/api/profile").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                .key("local-demo-only-replace-with-long-secure-secret")
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .logoutSuccessUrl("/?logout"))
            .csrf(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder encoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

**Lưu ý an toàn:**

- Secret key chuỗi cố định là **chỉ dành cho demo**; production phải đưa secret vào vault/env với rotation policy và bảo đảm ổn định giữa instances.
- BCrypt hash trong user in-memory được tạo mới khi app restart; với hash-based remember-me, token cũ **có thể mất hiệu lực sau restart** vì signature phụ thuộc stored password hash. Sản phẩm cần user store bền vững.
- `tokenValiditySeconds(7 * 24 * 60 * 60)` đặt remember token có hạn **7 ngày**; **không đặt server session tồn tại 7 ngày**.
- `SessionCreationPolicy.IF_REQUIRED` cho phép tạo session khi cần, khác với remember token.
- Không tắt CSRF vì form login/logout qua browser sử dụng cookie. POST login cần CSRF token.
- Đăng nhập bằng username/password dùng demo credential `alice/demo123` chỉ trên localhost; không dùng trong sản phẩm.
- DSL `.rememberMe(...)` tự cấu hình các thành phần Spring Security tương ứng; không tự thêm filter trùng.

### 9.4. DemoController.java

~~~java
package com.example.rememberdemo;

import java.util.Map;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/")
    public String home() {
        return "Demo remember-me: open /api/profile after login";
    }

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/profile")
    public Map<String, Object> profile(Authentication auth) {
        return Map.of(
            "username", auth.getName(),
            "rememberMe", resolver.isRememberMe(auth)
        );
    }

    @GetMapping("/api/strong")
    public String strong() {
        return "full-login-required";
    }
}
~~~

`AuthenticationTrustResolverImpl.isRememberMe(auth)` phản ánh **loại authentication hiện tại**. Khi browser có cả remember cookie lẫn session hợp lệ sau interactive login, request thường dùng full authentication từ session, nên `rememberMe=false` dù checkbox đã tick. Khi mất session, remember cookie tạo authentication khác, nên có thể trả `rememberMe=true`.

### 9.5. application.properties

~~~properties
server.port=8080
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

Chú ý **20 phút** là session idle timeout và **7 ngày** là remember token validity. Cookie Max-Age và server TTL vẫn là hai cơ chế khác nhau.

Trên production, dùng HTTPS, thiết lập `Secure` cho session và remember cookies, kiểm tra `HttpOnly`/`SameSite`/`Domain`/`Path` trên từng cookie, đánh giá HTTPS termination ở reverse proxy. Properties của Servlet session cookie **không nhất thiết áp tự động cho remember-me cookie**. Không công khai token qua log, URL, ảnh chụp hay bug report.

### 9.6. Chạy

Trong thư mục chứa `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Hoặc Maven Wrapper nếu đã tạo qua Spring Initializr:

~~~bash
./mvnw test
./mvnw spring-boot:run
~~~

Trên Windows PowerShell: `.\mvnw.cmd test` và `.\mvnw.cmd spring-boot:run`.

Mở `http://localhost:8080/api/profile` khi chưa login: dự kiến redirect tới `/login`. Đăng nhập với `alice/demo123` và chọn remember-me nếu form hiển thị checkbox. Nếu dùng custom form, phải gửi parameter `remember-me=on` khi login thành công. Kết quả JSON dự kiến khi session còn (thứ tự key có thể khác):

~~~json
{
  "username": "alice",
  "rememberMe": false
}
~~~

Sau đó chỉ **xóa session cookie** trong môi trường thử nghiệm, giữ remember cookie và gọi lại `/api/profile`. Khi cookie còn hợp lệ, kết quả dự kiến:

~~~json
{
  "username": "alice",
  "rememberMe": true
}
~~~

`/api/strong` khi chỉ còn remember cookie phải yêu cầu full authentication, thường redirect tới `/login`. Điều này không chứng minh token vô hiệu; nó chứng minh policy không chấp nhận remember-me cho action nhạy cảm.

Các JSON/status trong bài là **kết quả dự kiến theo cấu hình**; phải chạy app/test ở máy của bạn để xác minh behavior thực tế. Nếu trang login tự sinh không hiển thị checkbox do tùy biến/version, test ở mục kế tiếp vẫn gửi parameter chính xác.

## 10. Kiểm thử bằng MockMvc: không cần session cũ nhưng cần remember cookie

Tạo `src/test/java/com/example/rememberdemo/RememberFlowTests.java`:

~~~java
package com.example.rememberdemo;

import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberFlowTests {

    @Autowired
    MockMvc mvc;

    private MvcResult loginAndRemember() throws Exception {
        return mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    @Test
    void anonymousCannotSeeProfile() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void existingSessionIsFullyAuthenticated() throws Exception {
        MvcResult login = loginAndRemember();
        HttpSession raw = login.getRequest().getSession(false);
        assertNotNull(raw);
        MockHttpSession session = (MockHttpSession) raw;

        mvc.perform(get("/api/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.rememberMe").value(false));

        mvc.perform(get("/api/strong").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void rememberCookieWorksWithoutOldSession() throws Exception {
        MvcResult login = loginAndRemember();
        Cookie remembered = login.getResponse().getCookie("remember-me");
        assertNotNull(remembered);

        // Không truyền MockHttpSession ở request này.
        mvc.perform(get("/api/profile").cookie(remembered))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.rememberMe").value(true));
    }

    @Test
    void rememberOnlyIsNotFullyAuthenticated() throws Exception {
        MvcResult login = loginAndRemember();
        Cookie remembered = login.getResponse().getCookie("remember-me");
        assertNotNull(remembered);

        mvc.perform(get("/api/strong").cookie(remembered))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().isForbidden());
    }
}
~~~

Giải thích:

- `loginAndRemember()` mô phỏng form login thật, có CSRF token và checkbox.
- Test `existingSessionIsFullyAuthenticated` truyền `MockHttpSession` sang request thứ hai: Spring Security khôi phục full authentication.
- Test `rememberCookieWorksWithoutOldSession` **không truyền session**, chỉ truyền remember-me cookie. Nếu request được phép, đó là hành vi auto-login khác với kéo dài S1.
- Test `rememberOnlyIsNotFullyAuthenticated` chứng minh trust-level policy.
- Test CSRF không cho phép POST thiếu token hợp lệ.
- `@WithMockUser` không được dùng ở đây vì nó bỏ qua thử nghiệm flow remember-me cookie/filter.

Chạy `mvn test`. Đây là code mẫu đầy đủ của một project để học; **bài chưa tuyên bố đã chạy Maven thực tế**. Nếu sử dụng Spring Security 7.x hay một security configuration đã tùy biến, đối chiếu API, filter chain và status kỳ vọng với phiên bản triển khai.

## 11. Java thuần: mô phỏng sự khác biệt trong bốn dòng output

Nếu chưa cài Spring, chương trình Java 17 sau giúp kiểm chứng ý tưởng mà không phụ thuộc framework. Nó không phải session system thật và **không an toàn cho production**.

Tạo file `RememberVsSession.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RememberVsSession {
    private static final Map<String, String> sessions = new HashMap<>();
    private static final Map<String, String> rememberTokens = new HashMap<>();

    static String handle(String sid, String remember) {
        if (sid != null && sessions.containsKey(sid)) {
            return "SESSION:" + sessions.get(sid);
        }
        if (remember != null && rememberTokens.containsKey(remember)) {
            return "REMEMBER:" + rememberTokens.get(remember);
        }
        return "ANONYMOUS";
    }

    public static void main(String[] args) {
        sessions.put("sid1", "alice");
        rememberTokens.put("r1", "alice");

        System.out.println(handle("sid1", "r1"));
        sessions.remove("sid1");
        System.out.println(handle("sid1", "r1"));
        System.out.println(handle(null, "r1"));
        rememberTokens.remove("r1");
        System.out.println(handle(null, "r1"));
    }
}
~~~

Lệnh:

~~~bash
javac RememberVsSession.java
java RememberVsSession
~~~

Stdout chính xác:

~~~text
SESSION:alice
REMEMBER:alice
REMEMBER:alice
ANONYMOUS
~~~

Dòng 1: session còn; dòng 2: mất session nhưng remember còn; dòng 3: không gửi session nhưng có remember; dòng 4: mất luôn remember credential nên anonymous. **Không dùng** các ID dễ đoán như `sid1`/`r1` và không dùng `HashMap` tự chế để xác thực thật.

## 12. Persistent token trong thực tế: cần database và vòng đời revoke

Để lưu token phía server, dùng `PersistentTokenRepository`. Ví dụ cấu hình **minh họa, không chạy độc lập với demo chưa có datasource**:

~~~java
@Bean
PersistentTokenRepository tokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repo = new JdbcTokenRepositoryImpl();
    repo.setDataSource(dataSource);
    return repo;
}

@Bean
SecurityFilterChain chain(
        HttpSecurity http,
        UserDetailsService users,
        PersistentTokenRepository repo
) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/profile").authenticated()
            .anyRequest().fullyAuthenticated())
        .formLogin(Customizer.withDefaults())
        .rememberMe(remember -> remember
            .key("use-a-secret-from-secret-manager")
            .userDetailsService(users)
            .tokenRepository(repo)
            .tokenValiditySeconds(7 * 24 * 60 * 60));
    return http.build();
}
~~~

Cần imports `javax.sql.DataSource`, `PersistentTokenRepository`, `JdbcTokenRepositoryImpl`, `HttpSecurity`, `UserDetailsService`, `SecurityFilterChain`, `Bean`, `Customizer`. Muốn chạy phải thêm JDBC driver, `DataSource`, schema migration tạo bảng và logout/CSRF configuration hoàn chỉnh. **Không thêm bean `SecurityFilterChain` thứ hai vào demo** trừ khi đã thiết kế nhiều security chains có `securityMatcher` rõ.

Production cần:

1. Tạo schema bằng Flyway/Liquibase với index/constraint phù hợp; không tự tạo bảng mỗi request.
2. Dùng shared repository khi chạy nhiều instances.
3. Dọn token hết hạn; expired token bị từ chối không nhất thiết bị xóa row tự động.
4. Revoke khi đổi password, khóa tài khoản, báo mất thiết bị hoặc người dùng yêu cầu.
5. Ghi audit tối thiểu mà không log token.
6. Kiểm thử concurrent requests bởi rotation có thể làm token cũ xuất hiện lại. Không tắt phát hiện replay chỉ để “hết lỗi”.

## 13. Logout không đồng nghĩa xóa mọi bản sao remember token

Khi logout hợp lệ, Spring Security có thể invalidate session, clear `SecurityContext` và gửi cookie deletion. Remember-me service cũng có logout handler để xóa cookie tại browser.

**Nhưng**:

- Với **hash-based** cookie, xóa cookie trên thiết bị thật **không bảo đảm bản sao đã bị đánh cắp sẽ hết hiệu lực** ngay. Chữ ký cũ có thể vẫn valid tới expiry hoặc khi password/key thay đổi.
- Với **persistent token**, ứng dụng có server-side token state để xóa/revoke những token tương ứng. Cần phối hợp logout và policy “logout all devices”, không chỉ xóa cookie browser.
- Nếu sản phẩm còn OAuth2 refresh token, session tại Identity Provider hoặc API tokens thì phải xem đó là các credentials có vòng đời riêng.

Đừng triển khai nút **“Đăng xuất mọi thiết bị”** chỉ bằng cách `deleteCookies("remember-me")` tại browser hiện tại. Nó phải thu hồi credentials ở nơi chúng được xác minh.

## 14. Cookie security và CSRF

Remember-me cookie tồn tại lâu hơn session bình thường nên cần kiểm soát nghiêm:

| Biện pháp | Vì sao |
| --- | --- |
| HTTPS + `Secure` | Hạn chế truyền cookie trên kết nối không bảo mật |
| `HttpOnly` | JavaScript không đọc trực tiếp cookie; không loại bỏ mọi tác hại của XSS |
| `SameSite` thích hợp | Hạn chế một số trường hợp cookie tự gửi cross-site; không thay CSRF token |
| Domain/Path tối thiểu | Không gửi cookie tới nơi không cần |
| Token validity hợp lý | Giảm khoảng thời gian replay khi bị đánh cắp |
| Secret manager | Tránh hardcode remember key, nhất quán giữa instances |
| Logout + revoke strategy | Credential bị đánh cắp không được duy trì tùy tiện |
| Full reauth/MFA khi cần | Không lấy remember token làm bằng chứng đủ cho giao dịch nhạy cảm |

CSRF quan trọng vì browser thường tự gửi cookie. Một request POST có session/remember cookie hợp lệ vẫn có thể bị từ chối do thiếu CSRF token, và **đó là hành vi bảo vệ đúng**. Tắt CSRF toàn cục vì muốn POST form login đơn giản hơn có thể mở lỗ hổng. `SameSite` hỗ trợ nhưng không thay thế hoàn toàn CSRF protection trong mọi thiết kế.

`SessionCreationPolicy.STATELESS` không tự cấu hình JWT hay loại bỏ mọi cookie do ứng dụng khác tạo. Với API dùng bearer tokens, hãy thiết kế session/token authentication độc lập; không coi remember-me tích hợp Servlet là OAuth2 refresh token.

## 15. Khi nào nên dùng, khi nào nên tránh?

Remember-me phù hợp hơn khi:

- Sản phẩm là website dùng form login, UX cần quay lại sau vài ngày.
- Cho phép người dùng tự chọn “nhớ thiết bị”, có thông báo rõ.
- Các endpoint nhạy cảm có chính sách full/step-up authentication.
- Có kiểm soát cookie, expiry, revocation, thiết bị và account lifecycle.

Cần tránh hoặc hạn chế khi:

- Ứng dụng chứa giao dịch tài chính/secret cực kỳ nhạy cảm.
- Môi trường kiosk/máy dùng chung.
- Chưa có cơ chế thu hồi token khi thiết bị bị đánh cắp.
- Secret key, HTTPS, CSRF hay hệ thống phát hiện bất thường chưa đáng tin.
- Tích hợp chủ yếu là stateless API/OAuth2, có cơ chế refresh token riêng phù hợp hơn.

Không đặt `alwaysRemember(true)` chỉ để giảm số bước login nếu chưa hiểu sự khác biệt về quyền lựa chọn của user.

## 16. Gỡ lỗi: “Tôi đã chọn Remember me nhưng hôm sau phải đăng nhập”

Kiểm tra theo thứ tự:

1. Form có gửi đúng parameter `remember-me` khi login thành công?
2. Response có thực sự phát remember-me cookie, và browser có lưu không?
3. Browser có gửi lại cookie đúng domain/path/SameSite/Secure không?
4. Token đã hết thời hạn, bị sửa, user bị disabled hay password thay đổi?
5. Secret key giữa các deployment/instances có ổn định không?
6. `UserDetailsService` có tìm thấy user và trả đúng password hash/authorities không?
7. Demo có đang tạo BCrypt hash mới mỗi lần restart khiến hash-based token cũ invalid?
8. Nếu dùng persistent token, token store có chia sẻ giữa instances không? Có xung đột rotation không?
9. Có `SecurityFilterChain` riêng cho URL không bật remember-me?
10. Endpoint có yêu cầu `fullyAuthenticated()` nên đang từ chối remember-me một cách có chủ đích?
11. Logout/password reset/account lock có chủ ý xóa/revoke token không?
12. Mã HTTP 403 đến từ authorization hay CSRF? Đừng vội sửa bằng cách tắt bảo vệ.

Khi debug, chỉ ghi metadata và request ID phù hợp. **Không log session ID hoặc remember-me token đầy đủ**.

## 17. Bài tập kiểm tra hiểu bài

**Bài 1.** Session timeout 20 phút, remember token valid 7 ngày. Sau 2 giờ không hoạt động, user quay lại chỉ với remember-me cookie. User có thể được nhận diện không? Đây là kéo dài session cũ hay auto-login?

**Bài 2.** Vì sao user vừa tick Remember me và còn session hợp lệ lại thấy `rememberMe=false` ở endpoint demo?

**Bài 3.** Tại sao `/api/profile` có thể trả 200 cho remember token, nhưng `/api/strong` yêu cầu login tương tác?

**Bài 4.** Alice logout khỏi browser, nhưng attacker có bản sao hash-based remember-me cookie. Vì sao bản sao có thể vẫn còn hiệu lực? Nêu cách giảm nguy cơ.

**Bài 5.** Hệ thống cần thu hồi riêng token của từng thiết bị. Bạn sẽ ưu tiên cơ chế nào và cần thêm thành phần quản lý gì?

**Bài 6.** Sau khi deploy một bản mới, remember cookie không dùng được dù username/password không đổi. Hãy nêu những thứ có thể thay đổi trong verify token.

**Bài 7.** Có thể chỉ tăng server session timeout lên 30 ngày rồi bỏ CSRF và HTTPS không? Giải thích.

**Bài 8.** Một SPA dùng OAuth2 refresh token. Có thể lấy `RememberMeAuthenticationFilter` xử lý refresh token OAuth2 trực tiếp không? Vì sao?

**Bài 9.** Bạn sẽ test như thế nào để chứng minh remember-me hoạt động **khi không dùng lại session cũ**?

### Đáp án gợi ý

1. Có thể auto-login nếu token hợp lệ; không phải giữ nguyên session.
2. Vì request đang dùng full authentication trong session; cờ phản ánh cách authentication hiện tại được tạo, không phải trạng thái checkbox.
3. `authenticated()` chấp nhận remember, `fullyAuthenticated()` không.
4. Hash-based token copy có thể replay tới expiry; cần revoke bằng đổi password/key hoặc thiết kế persistent store/revocation phù hợp.
5. Persistent token + device record, revoke API, token rotation, audit và shared store.
6. Stored password hash, secret key, user status, token expiry, algorithm/config hoặc persistent store.
7. Không. Session dài làm tăng cửa sổ rủi ro; CSRF và HTTPS là các lớp bảo vệ độc lập.
8. Không. Refresh token thuộc OAuth2 grant/authorization server, không cùng contract với Servlet remember-me services.
9. Trong MockMvc, login với remember parameter, lấy remember cookie từ response rồi gửi request mới chỉ với `.cookie(remembered)`, không dùng `.session(...)`.

## 18. Tóm tắt và nguồn tham khảo

**Kéo dài session** duy trì một `HttpSession` đang có. **Remember-me** cho phép xác thực lại bằng credential riêng sau khi session biến mất. Spring Security biểu đạt mức xác thực này bằng `RememberMeAuthenticationToken`, nhờ đó ứng dụng có thể cho phép tác vụ thông thường nhưng yêu cầu `fullyAuthenticated()` hoặc step-up/MFA với hành động nhạy cảm.

Hãy nhớ: **hai cookie, hai vòng đời, hai mức tin cậy và hai chiến lược revoke**. Nếu thiết kế remember-me như một session timeout dài, bạn sẽ bỏ qua nhiều rủi ro về replay, logout và thiết bị bị chiếm dụng.

Tài liệu chính thức:

- [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html)
- [Spring Security 6.5 — Remember-Me](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Session — Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html)
