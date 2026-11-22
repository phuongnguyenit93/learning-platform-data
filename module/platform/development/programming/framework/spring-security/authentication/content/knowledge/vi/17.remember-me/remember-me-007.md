# Thu hồi token ghi nhớ khi đăng xuất hoặc thay đổi thông tin tài khoản

## Mục tiêu bài học

**Remember-me** (ghi nhớ đăng nhập) cho phép trình duyệt được xác thực tự động ở lần truy cập sau khi phiên HTTP thông thường đã kết thúc. Spring Security Servlet hỗ trợ cách dùng **cookie có chữ ký/hash** và cách dùng **persistent token lưu phía server**. Khi người dùng đăng xuất, đổi mật khẩu, khôi phục tài khoản, khóa tài khoản hoặc thay đổi thông tin bảo mật, chúng ta phải quyết định **token nào còn được phép tự đăng nhập**.

Bài học này hướng dẫn **thu hồi (revocation) remember-me token**, không chỉ xóa cookie trên trình duyệt. Đây là một khác biệt bảo mật quan trọng: cookie bị xóa ở thiết bị hiện tại vẫn có thể tồn tại trong bản sao do kẻ tấn công hoặc thiết bị khác giữ.

Sau bài học, bạn có thể:

1. Giải thích chính xác sự khác nhau giữa `TokenBasedRememberMeServices` và `PersistentTokenBasedRememberMeServices`.
2. Hiểu luồng **remember-me cookie → RememberMeAuthenticationFilter → RememberMeServices → PersistentTokenRepository → Authentication**.
3. Phân biệt **xóa cookie**, **xóa token trong repository**, **hủy HttpSession** và **thu hồi các phiên đang hoạt động**.
4. Biết vì sao Spring Security persistent remember-me thường xóa **toàn bộ token của một username** khi logout có Authentication, nhưng việc đổi mật khẩu hoặc đổi thông tin tài khoản vẫn cần logic thu hồi explicit.
5. Tạo ứng dụng Java 17+ / Spring Boot Servlet / JDBC remember-me, có endpoint đổi mật khẩu đồng thời xóa token và yêu cầu đăng nhập lại.
6. Viết kịch bản kiểm thử cookie cũ, hai thiết bị, thay đổi password, CSRF và rủi ro khi token đã bị đánh cắp.

**Phạm vi:** Spring Security Servlet 6.5.x / Spring Boot 3.5.x và cơ chế remember-me do ứng dụng quản lý. Đây **không phải** OAuth2 Refresh Token, OIDC logout, JWT blacklist hoặc Spring Session, mặc dù chúng cũng có vấn đề thu hồi riêng. Ví dụ dùng H2 in-memory cho mục đích học; production phải dùng kho persistent an toàn và phiên bản Spring đang còn hỗ trợ.

## 1. Ba trạng thái khác nhau: HttpSession, remember-me cookie, token phía server

Một trình duyệt có thể đồng thời mang:

- **Cookie phiên HTTP**, thường `JSESSIONID`: giúp server khôi phục SecurityContext đã lưu trong HttpSession, cho đến khi phiên hết hạn hoặc bị hủy.
- **Cookie remember-me**, mặc định thường tên `remember-me`: là chứng cứ để Spring Security tự tạo Authentication khi request **chưa có Authentication phù hợp** trong SecurityContext.
- **Bản ghi persistent token** trong database, nếu ứng dụng chọn `PersistentTokenBasedRememberMeServices`. Bản ghi này cho phép server kiểm tra và xoay thông tin cookie.

Đường đi điển hình:

~~~text
1. POST /login: username + password + remember-me=on
      |
      +--> AuthenticationManager xác thực thành công
      +--> RememberMeServices.loginSuccess(...)
      +--> tạo cookie remember-me
      +--> (nếu dùng persistent) tạo row persistent_logins
      |
      v
2. GET /me: JSESSIONID còn hợp lệ
      |
      +--> SecurityContext được đọc từ HttpSession
      +--> thường KHÔNG cần tự login lại bằng remember-me
      |
      v
3. GET /me: không còn JSESSIONID, còn cookie remember-me
      |
      +--> RememberMeAuthenticationFilter
      +--> RememberMeServices.autoLogin(...)
      +--> kiểm tra cookie / repository / UserDetailsService
      +--> có thể tạo RememberMeAuthenticationToken
      +--> nếu hợp lệ: tiếp tục như người dùng đã xác thực
~~~

Từ đó suy ra:

- **Logout hủy session** không đồng nghĩa một cookie remember-me bị đánh cắp đã mất hiệu lực.
- **Xóa remember-me token** không mặc nhiên hủy những HttpSession đã có Authentication. Request đã có session hợp lệ có thể không cần remember-me cookie nữa.
- **Đổi password** có thể tác động khác nhau đến hai loại remember-me.
- **Đổi quyền/khóa account** cần xét cả token remember-me và **phiên đã xác thực trước đó**, không chỉ một bảng token.

## 2. Hai kiểu remember-me và khả năng thu hồi

### 2.1. TokenBasedRememberMeServices: cookie có chữ ký/hash

Cơ chế hash-based lưu thông tin xác thực trong cookie dạng encode, có ràng buộc tới username, thời hạn, mật khẩu đã lưu của người dùng và secret key của ứng dụng. Công thức khái niệm của Spring Security:

~~~text
cookie = Base64(
    username : expiryTime : algorithmName : signature
)

signature = hash(
    username : expiryTime : passwordHashFromUserDetails : applicationKey
)
~~~

Công thức trên minh họa dữ liệu tham gia xác minh; định dạng và thuật toán chính xác phụ thuộc phiên bản/thuộc tính Spring Security. Không thiết kế lại chữ ký remember-me thủ công.

**Cách vô hiệu hóa:**

- **Đổi password hash** của người dùng: cookie cũ không còn xác minh đúng vì password hash server đã thay đổi.
- **Đổi secret key**: có thể làm vô hiệu hóa cookie cũ của **mọi người dùng** dùng key đó.
- **Đợi hết hạn**: cookie không còn hợp lệ sau thời hạn kiểm tra.

**Giới hạn:** server **không có danh sách từng token** của người dùng để xóa. Khi logout, Spring Security có thể xóa cookie trong response của thiết bị hiện tại, nhưng một bản sao cookie hash-based đã bị lấy cắp có thể còn hợp lệ cho tới khi password/key thay đổi hoặc token hết hạn.

Nếu yêu cầu “Đăng xuất khỏi tất cả thiết bị” hoặc “Thu hồi một thiết bị cụ thể” thật sự, hash-based remember-me có giới hạn quan trọng. Có thể bổ sung security version/token version phía server vào một cơ chế tự thiết kế, hoặc chuyển sang **persistent remember-me**; không nên tuyên bố xóa cookie client là thu hồi server-side.

### 2.2. PersistentTokenBasedRememberMeServices: server kiểm tra theo series

Cơ chế persistent dùng `PersistentTokenRepository`, thường là `JdbcTokenRepositoryImpl`, lưu các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `username` | Chủ sở hữu token, dùng để quản lý và xóa token theo user |
| `series` | ID chuỗi token, unique/primary key; nhận diện một chuỗi remember-me |
| `token` | Giá trị token hiện tại của chuỗi, cần khớp cookie |
| `last_used` | Thời điểm dùng gần nhất, phục vụ kiểm tra tuổi token |

Schema SQL thường dùng:

~~~sql
create table persistent_logins (
    username varchar(64) not null,
    series varchar(64) primary key,
    token varchar(64) not null,
    last_used timestamp not null
);
~~~

Cookie persistent thường chứa **series + token**, không cần chứa username plaintext. Server tìm series trong database, kiểm tra token hiện tại và hạn sử dụng.

**Token rotation:** sau khi auto-login thành công, Spring Security có thể tạo **token value mới trong cùng series**, cập nhật repository rồi gửi cookie mới. Một bản cookie cũ có thể không còn hợp lệ ngay sau lần sử dụng đó. Nếu series vẫn tồn tại nhưng token khác, framework có thể coi là dấu hiệu đánh cắp cookie (`CookieTheftException`) và gọi `removeUserTokens(username)`.

**Cơ chế xóa chủ động:** interface `PersistentTokenRepository` có:

~~~java
void removeUserTokens(String username);
~~~

Phương thức này xóa **các remember-me token của user được chỉ định**. Với repository JDBC mặc định, nó xóa các row phù hợp trong `persistent_logins`. Sau khi xóa, cookie đã phát trước đó không còn được repository xác nhận khi trình duyệt chỉ có cookie remember-me.

Lưu ý: API mặc định **không cung cấp thao tác xóa một series theo ID**. Nếu muốn “đăng xuất chỉ thiết bị hiện tại”, cần mở rộng repository và remember-me service/handler với kiểm tra chủ sở hữu series và xử lý race/rotation; không nên cố biến `removeUserTokens(username)` thành hàm per-device.

## 3. Điều gì xảy ra khi người dùng logout?

### 3.1. Đường logout do Spring Security quản lý

Với Servlet app có `formLogin()`, `rememberMe()` và `logout()` tiêu chuẩn, `LogoutFilter` phối hợp các `LogoutHandler`:

~~~text
POST /logout (CSRF hợp lệ)
       |
       v
LogoutFilter
       |
       +--> SecurityContextLogoutHandler
       |      - invalidate HttpSession (theo cấu hình)
       |      - clear SecurityContext
       |
       +--> RememberMeServices logout handling
       |      - xóa cookie remember-me ở response
       |      - persistent remember-me: có thể xóa token server-side
       |
       +--> CsrfLogoutHandler / event-related handlers
       |
       v
LogoutSuccessHandler (mặc định thường redirect /login?logout)
~~~

**Không cần tự viết controller `POST /logout`** chỉ để xóa remember-me cookie. Dùng `http.logout(...)` và tích hợp remember-me đúng cách để framework gọi toàn bộ các handler cần thiết.

### 3.2. Chi tiết đặc biệt của persistent remember-me

Ở Spring Security 6.5, `PersistentTokenBasedRememberMeServices.logout(request, response, authentication)` gọi logic hủy cookie của lớp cha và, **khi Authentication không null**, xóa token của username qua `PersistentTokenRepository.removeUserTokens(authentication.getName())`.

Hệ quả thường thấy:

1. **Logout trên thiết bị A** khi đang có Authentication hợp lệ → cookie nhớ đăng nhập ở A bị xóa.
2. **Toàn bộ row remember-me của username** có thể bị xóa khỏi repository.
3. Một thiết bị B vẫn giữ cookie remember-me cũ, nhưng nếu **không có HttpSession đã xác thực**, nó không thể dùng cookie đã bị thu hồi để tự đăng nhập lại.
4. Nếu B **đang có HttpSession hợp lệ**, B có thể vẫn tiếp tục truy cập bằng session đó. Xóa row remember-me **không tự hủy session B**.

Đây là lý do câu “logout thì tất cả thiết bị bị đăng xuất ngay” là **quá mạnh**. Chính xác hơn: với persistent remember-me tích hợp chuẩn, logout có Authentication có thể **thu hồi khả năng auto-login bằng nhớ đăng nhập của tất cả thiết bị**, nhưng không mặc nhiên hủy mọi session đang hoạt động.

**Trường hợp Authentication null:** triển khai persistent chỉ xóa token server-side khi có Authentication để biết username. Nếu request logout không có Authentication, bạn không được mặc định rằng toàn bộ row của user đã bị xóa. Cần xác định hành vi và fallback theo threat model.

### 3.3. Xóa cookie không phải biện pháp duy nhất

Ví dụ cấu hình bổ sung:

~~~java
http.logout(logout -> logout
    .deleteCookies("remember-me")
);
~~~

Đoạn trên **chỉ minh họa xóa cookie**. Với persistent remember-me, lớp dịch vụ remember-me chuẩn đã có hook logout; việc xóa cookie riêng **không thay thế thao tác thu hồi row** nếu bạn đang tự viết logout endpoint hoặc dùng custom RememberMeServices.

Nếu ứng dụng đổi tên cookie, domain/path hoặc có reverse proxy, hãy bảo đảm cookie xóa sử dụng đúng tên, path/domain và thuộc tính liên quan. Một `Set-Cookie` được trả về chưa chắc đã xóa đúng cookie nếu path/domain không trùng. Không yêu cầu phía browser gửi credential bí mật trong response/log để “debug”.

## 4. Tại sao đổi mật khẩu cần chiến lược thu hồi riêng?

Giả sử người dùng đổi password vì nghi ngờ tài khoản bị truy cập trái phép.

### Với cookie hash-based

Vì chữ ký remember-me phụ thuộc password hash ở `UserDetails`, **nếu password hash thật sự thay đổi** thì các cookie cũ sẽ không vượt qua kiểm tra hash ở lần auto-login tiếp theo.

Giới hạn:

- Cơ chế này không tự hủy HttpSession hiện có.
- Đổi **email, phone, MFA, trạng thái account hoặc quyền** không nhất thiết đổi password hash, nên remember-me token có thể vẫn hợp lệ.
- Nếu custom `UserDetailsService` không trả hash nhất quán hoặc ứng dụng thay đổi thuật toán/chìa khóa, cần kiểm thử tính tương thích.

### Với persistent token

Record `persistent_logins` **không phụ thuộc trực tiếp vào password hash**. Do đó **đổi password không bảo đảm** token persistent cũ tự mất hiệu lực.

Cách làm có chủ đích:

~~~java
// Trong service xử lý cập nhật bảo mật cho tài khoản đã xác thực.
// username lấy từ danh tính server đáng tin, không từ JSON do client tự khai.
userService.updatePassword(username, newEncodedPassword);
persistentTokenRepository.removeUserTokens(username);
~~~

Đây là **mã minh họa**, không phải class Java độc lập. Cần kiểm tra mật khẩu hiện tại/step-up authentication, đảm bảo atomicity và xử lý failure. Không xóa bằng một `username` tùy ý do caller gửi trong request để tránh xóa token người khác.

Những sự kiện thường nên thu hồi remember-me token:

| Sự kiện | Chính sách nên cân nhắc |
| --- | --- |
| **Đổi password** theo yêu cầu user | Xóa toàn bộ remember-me tokens của user; tùy threat model hủy các session khác |
| **Quên mật khẩu / reset password** qua email | Xóa remember-me tokens sau reset thành công; kiểm tra các session hiện có |
| **Đổi email dùng làm username** | Xóa token theo username **cũ** trước/đồng thời với việc đổi khóa định danh |
| **Đổi phone hoặc MFA/2FA** | Yêu cầu xác thực lại, xóa token nếu chính sách bảo mật coi đó là thay đổi nhạy cảm |
| **Khóa/vô hiệu hóa tài khoản** | Thu hồi remember-me tokens, xử lý sessions và từ chối xác thực mới |
| **Xóa tài khoản** | Xóa tokens và sessions liên quan, dọn dữ liệu theo chính sách |
| **Nghi ngờ đánh cắp cookie** | Thu hồi toàn bộ remember-me tokens, cảnh báo/điều tra và có thể hủy phiên khác |
| **Đổi vai trò/quyền** | Không chỉ xóa token; xem xét Authentication đã cache trong session và phân quyền lại |
| **Đăng xuất tất cả thiết bị** | Thu hồi remember-me tokens và hủy/invalidate các session đang hoạt động theo chính sách |

**Đổi email hiển thị không phải email đăng nhập** có thể có rủi ro khác; áp dụng policy theo threat model và kiểu identifier thực tế.

## 5. Ví dụ chạy được: Persistent remember-me với JDBC và đổi password

Mục tiêu demo:

- Dùng **Spring Boot 3.5.16, Java 17+**, Spring Security Servlet và H2 in-memory.
- Người dùng `demo` có mật khẩu ban đầu `change-me`, đăng nhập form và chọn **remember-me**.
- `JdbcTokenRepositoryImpl` lưu token vào bảng `persistent_logins`.
- Endpoint `POST /account/change-password` kiểm tra password hiện tại, cập nhật password hash và **gọi removeUserTokens(username)** trong cùng transaction JDBC.
- Khi đổi thành công, hủy **session hiện tại** và xóa cookie remember-me, buộc client đăng nhập lại.
- Hỗ trợ lấy CSRF token qua `GET /csrf` để thử bằng curl. **Không tắt CSRF**.

**Giới hạn demo:** database H2 in-memory sẽ mất dữ liệu khi ứng dụng dừng. Tài khoản demo và remember-me key trong properties chỉ dùng local. Spring Boot 3.5.16 là bản cuối OSS của nhánh 3.5; **production mới nên chọn nhánh Spring Boot còn hỗ trợ** và phiên bản Spring Security tương thích.

### 5.1. Cấu trúc project

~~~text
remember-revocation-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/resources/schema.sql
  src/main/java/example/remember/RememberRevocationApplication.java
~~~

**settings.gradle:**

~~~groovy
rootProject.name = 'remember-revocation-demo'
~~~

**build.gradle:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

**src/main/resources/application.properties:**

~~~properties
spring.datasource.url=jdbc:h2:mem:rememberdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

server.port=8080
app.remember-me.key=local-demo-only-not-a-production-secret
~~~

**Lưu ý:** với production, lấy `app.remember-me.key` từ secret manager/biến môi trường an toàn, không đưa key thật vào Git. Các instance của cùng ứng dụng cần cấu hình key tương thích; xoay key sẽ vô hiệu hóa các cookie hash-based và có thể ảnh hưởng tính tương thích của remember-me service. Không dùng H2 in-memory để chia sẻ remember-me giữa nhiều instance.

**src/main/resources/schema.sql:**

~~~sql
create table users (
    username varchar(50) not null primary key,
    password varchar(500) not null,
    enabled boolean not null
);

create table authorities (
    username varchar(50) not null,
    authority varchar(50) not null,
    constraint fk_authorities_users
        foreign key (username) references users(username)
);

create unique index ix_auth_username
    on authorities (username, authority);

create table persistent_logins (
    username varchar(64) not null,
    series varchar(64) primary key,
    token varchar(64) not null,
    last_used timestamp not null
);
~~~

Hai bảng đầu tương thích với các truy vấn mặc định của `JdbcUserDetailsManager` cho kịch bản đơn giản. Bảng `persistent_logins` là schema remember-me persistent được Spring Security mô tả. Với production, dùng migration có phiên bản, index/constraint phù hợp database, giới hạn kết nối, backup và cleanup; không chạy `create table` mỗi lần khởi động.

### 5.2. Code Java hoàn chỉnh

Tạo file **src/main/java/example/remember/RememberRevocationApplication.java**:

~~~java
package example.remember;

import java.util.Map;

import javax.sql.DataSource;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.CookieClearingLogoutHandler;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RememberRevocationApplication {

    public static void main(String[] args) {
        SpringApplication.run(RememberRevocationApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    JdbcUserDetailsManager users(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }

    @Bean
    PersistentTokenRepository persistentTokenRepository(
            DataSource dataSource) {
        JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
        repository.setDataSource(dataSource);
        return repository;
    }

    @Bean
    ApplicationRunner seedDemoUser(
            JdbcUserDetailsManager users, PasswordEncoder encoder) {
        return args -> {
            if (!users.userExists("demo")) {
                users.createUser(User.withUsername("demo")
                    .password(encoder.encode("change-me"))
                    .roles("USER")
                    .build());
            }
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JdbcUserDetailsManager users,
            PersistentTokenRepository persistentTokens,
            Environment environment) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf").permitAll()
                // Hành động nhạy cảm: remember-me-only không đủ.
                .requestMatchers("/account/change-password")
                    .fullyAuthenticated()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                .key(environment.getRequiredProperty("app.remember-me.key"))
                .userDetailsService(users)
                .tokenRepository(persistentTokens)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60)
            )
            .logout(Customizer.withDefaults());

        return http.build();
    }

    @Service
    public static class PasswordChangeService {
        private final JdbcUserDetailsManager users;
        private final PasswordEncoder encoder;
        private final PersistentTokenRepository persistentTokens;

        public PasswordChangeService(
                JdbcUserDetailsManager users,
                PasswordEncoder encoder,
                PersistentTokenRepository persistentTokens) {
            this.users = users;
            this.encoder = encoder;
            this.persistentTokens = persistentTokens;
        }

        // Cả updateUser và removeUserTokens cùng dùng một DataSource.
        @Transactional
        public boolean changePassword(
                String verifiedUsername,
                String currentPassword,
                String newPassword) {

            if (currentPassword == null
                    || newPassword == null
                    || newPassword.length() < 12) {
                return false;
            }

            // Danh tính đi từ Authentication đã xác minh.
            UserDetails current = users.loadUserByUsername(
                verifiedUsername
            );

            if (!encoder.matches(
                    currentPassword, current.getPassword())) {
                return false;
            }

            UserDetails updated = User.withUserDetails(current)
                .password(encoder.encode(newPassword))
                .build();

            users.updateUser(updated);

            // Thu hồi TẤT CẢ remember-me tokens của user.
            persistentTokens.removeUserTokens(verifiedUsername);

            return true;
        }
    }

    @RestController
    public static class Api {
        private final PasswordChangeService passwords;

        public Api(PasswordChangeService passwords) {
            this.passwords = passwords;
        }

        public record ChangePassword(
                String currentPassword, String newPassword) {
        }

        public record CsrfInfo(String headerName, String token) {
        }

        @GetMapping("/csrf")
        public CsrfInfo csrf(CsrfToken token) {
            return new CsrfInfo(
                token.getHeaderName(),
                token.getToken()
            );
        }

        @GetMapping("/")
        public String home(Authentication authentication) {
            return "hello, " + authentication.getName();
        }

        @GetMapping("/me")
        public Map<String, String> me(Authentication authentication) {
            return Map.of(
                "username", authentication.getName(),
                "authenticationType",
                    authentication.getClass().getSimpleName()
            );
        }

        @PostMapping("/account/change-password")
        public ResponseEntity<Void> changePassword(
                @RequestBody ChangePassword body,
                Authentication authentication,
                HttpServletRequest request,
                HttpServletResponse response) {

            boolean changed = passwords.changePassword(
                authentication.getName(),
                body.currentPassword(),
                body.newPassword()
            );

            if (!changed) {
                return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                    .build();
            }

            // Xóa cookie trên browser hiện tại (demo root path).
            new CookieClearingLogoutHandler("remember-me")
                .logout(request, response, authentication);

            // Hủy phiên và SecurityContext hiện tại.
            new SecurityContextLogoutHandler()
                .logout(request, response, authentication);

            return ResponseEntity.noContent().build();
        }
    }
}
~~~

### 5.3. Giải thích luồng thu hồi trong code

**1. Có kho token server-side.** `PersistentTokenRepository` được kết nối với H2 qua `JdbcTokenRepositoryImpl`. Khi `http.rememberMe().tokenRepository(...)` được cấu hình, Spring Security dùng persistent remember-me thay vì cookie hash-based mặc định.

**2. Mật khẩu được lưu dạng encoded.** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` sinh password hash có prefix thuật toán, thay vì lưu mật khẩu plaintext. Tài khoản demo chỉ được seed khi chưa tồn tại.

**3. Endpoint đổi mật khẩu yêu cầu xác thực đầy đủ.** Rule `.fullyAuthenticated()` không cho một request chỉ có `RememberMeAuthenticationToken` thực hiện thao tác nhạy cảm; người dùng cần đăng nhập tương tác bằng credential. Ngoài ra service vẫn xác minh **currentPassword**.

**4. Không tin username do client gửi.** Username đi từ `Authentication.getName()`, không có tham số body `username`. Điều này giảm rủi ro xóa token của tài khoản khác.

**5. Update password + remove tokens cùng transaction.** `@Transactional` trên service phối hợp `JdbcUserDetailsManager.updateUser(...)` và `PersistentTokenRepository.removeUserTokens(...)` dùng cùng DataSource/transaction manager. Nếu một thao tác database thất bại và exception được ném, transaction thông thường rollback. **Không bắt exception rồi trả success** nếu việc thu hồi token chưa hoàn thành.

**6. Sau thành công mới cleanup ở response.** Controller xóa cookie remember-me ở browser và gọi `SecurityContextLogoutHandler` để hủy session hiện tại. Vì service transactional được gọi qua Spring proxy, giao dịch được hoàn tất trước khi controller trả 204.

**7. Các session khác không bị hủy tự động.** Code trên không có distributed session registry hoặc tính năng “logout all active sessions”. Nó **thu hồi remember-me tokens của user** và **hủy session của request hiện tại**. Nếu hai trình duyệt còn active HttpSession, muốn kết thúc cả hai phải bổ sung quản lý session theo ID/user.

**8. Không vô hiệu hóa CSRF.** POST login, POST logout và POST change-password cần token hợp lệ; trình duyệt gửi cookie tự động là một lý do quan trọng cần chống CSRF. `GET /csrf` phục vụ client cùng origin lấy token sau khi Spring Security cần cấp/đổi token.

**9. Cookie path/domain phải khớp.** `CookieClearingLogoutHandler("remember-me")` phù hợp đường dẫn root mặc định của demo. Nếu ứng dụng đổi cookie name/path/domain/SameSite, phải dùng cấu hình cleanup tương ứng. Không sao chép nguyên ví dụ vào nhiều subdomain rồi kỳ vọng mọi cookie đều xóa đúng.

**10. Validation trong demo là tối thiểu.** Production cần policy mật khẩu, rate limit, audit, thay đổi email/MFA có step-up authentication, chống brute force và bảo vệ dữ liệu cá nhân. Dữ liệu H2 in-memory mất khi app dừng nên không dùng để tuyên bố persistence production.

## 6. Chạy ứng dụng và kiểm chứng bằng curl

Từ thư mục project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu project chưa có wrapper nhưng máy đã cài Gradle tương thích, dùng `gradle bootRun`. Spring Boot ví dụ lắng nghe `http://localhost:8080`.

Các lệnh dưới dùng **Bash/WSL/Git Bash**, `curl` và `python3`. Bạn có thể chuyển sang PowerShell/curl.exe với cách đọc JSON tương ứng. **Không commit file cookie jar lên repository hoặc gửi nó vào log/chat.**

### 6.1. Lấy CSRF token ban đầu

~~~bash
csrf=$(curl -fsS -c login-cookies.txt \
  http://localhost:8080/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

test -n "$csrf"
~~~

Endpoint `GET /csrf` có thể tạo session để lưu token CSRF. Dùng `-c` và `-b` để giữ cookie nhất quán trong những request tiếp theo.

### 6.2. Form login và chọn ghi nhớ đăng nhập

~~~bash
curl -i -b login-cookies.txt -c login-cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  --data-urlencode "username=demo" \
  --data-urlencode "password=change-me" \
  --data-urlencode "remember-me=on" \
  http://localhost:8080/login
~~~

Kết quả thường là **302 Redirect** sau đăng nhập thành công. Response có thể cập nhật cookie phiên và gửi cookie **remember-me**. Tùy trình duyệt/curl, thứ tự header khác nhau; hãy dựa vào status và cookie thực tế.

Trong kho H2 sẽ có một row `persistent_logins` cho user demo. Row đó là bằng chứng server-side của remember-me; không chỉ là một cookie trong browser.

### 6.3. Chuẩn bị cookie remember-me riêng trước khi thu hồi

Trường hợp muốn mô phỏng một bản cookie cũ được sao chép, ta cần **loại JSESSIONID** khỏi cookie jar. Nếu không, request có thể thành công nhờ HttpSession, khiến bạn kết luận sai về khả năng thu hồi remember-me.

File cookie dạng Netscape do curl ghi có tên cookie ở cột thứ sáu. Lọc bỏ cookie JSESSIONID:

~~~bash
awk -F '\t' '$6 != "JSESSIONID"' \
  login-cookies.txt > remembered-before.txt
~~~

File `remembered-before.txt` còn giữ cookie **remember-me** (và có thể các cookie không liên quan), nhưng không giữ JSESSIONID. **Không dùng cookie remember-me này để auto-login trước khi làm bài test thu hồi**, bởi persistent remember-me có cơ chế **token rotation**: nếu dùng trước, token có thể đổi và bản lưu cũ vốn đã không hợp lệ, làm phép thử revocation thiếu ý nghĩa.

Muốn kiểm tra auto-login **trước thu hồi**, hãy làm thành một kịch bản login riêng và để curl ghi cập nhật cookie mới; đừng dùng lại một token cũ sau khi nó đã được rotate.

### 6.4. Logout và thử phát lại cookie remember-me cũ

Lấy token CSRF mới sau login, vì token trước login có thể đã được xóa/đổi:

~~~bash
csrf=$(curl -fsS -b login-cookies.txt -c login-cookies.txt \
  http://localhost:8080/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -i -b login-cookies.txt -c login-cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  -X POST http://localhost:8080/logout
~~~

Kết quả thường **302** tới `/login?logout`. Với persistent remember-me, logout có Authentication hợp lệ còn gọi cơ chế xóa token của username.

Thử replay cookie remember-me cũ mà không gửi session:

~~~bash
curl -i -b remembered-before.txt \
  http://localhost:8080/me
~~~

**Kỳ vọng:** request không được xác thực tự động bằng cookie đã thu hồi; với form login, kết quả thường **302** tới trang `/login` (không phải luôn 401). Nếu chỉ gọi `/me` bằng jar còn JSESSIONID hợp lệ, phép thử không cô lập remember-me.

### 6.5. Đổi mật khẩu và buộc đăng nhập lại

Bắt đầu một lần login **mới** bằng password cũ và `remember-me=on`, tạo file `password-cookies.txt` khác. Lấy CSRF và login tương tự mục 6.1–6.2, rồi sao chép cookie remember-me trước khi đổi:

~~~bash
awk -F '\t' '$6 != "JSESSIONID"' \
  password-cookies.txt > password-remembered-before.txt
~~~

Lấy CSRF hiện tại sau login rồi gọi endpoint:

~~~bash
csrf=$(curl -fsS -b password-cookies.txt -c password-cookies.txt \
  http://localhost:8080/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -i -b password-cookies.txt -c password-cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: $csrf" \
  --data '{"currentPassword":"change-me","newPassword":"new-strong-pass-2026"}' \
  http://localhost:8080/account/change-password
~~~

**Kỳ vọng:** **204 No Content**. Service cập nhật password hash và xóa token persistent của user; cookie ở browser và session hiện tại được dọn. Khi phát lại `password-remembered-before.txt` mà không có JSESSIONID:

~~~bash
curl -i -b password-remembered-before.txt \
  http://localhost:8080/me
~~~

**Kỳ vọng:** không thể tự đăng nhập; ứng dụng dùng form login thường redirect sang `/login`. Mật khẩu mới có thể dùng để login tương tác; mật khẩu cũ không còn hợp lệ.

**Chú ý trạng thái dữ liệu demo:** H2 `jdbc:h2:mem:` mất dữ liệu khi process dừng. Trong môi trường test, không restart app giữa bước đổi mật khẩu và replay cookie; nếu restart H2, row token mất vì DB reset, dẫn đến một phép thử “vô hiệu hóa” không có ý nghĩa.

## 7. Các giới hạn thu hồi cần nói chính xác

### 7.1. Thu hồi remember-me không tương đương logout all sessions

Ví dụ:

~~~text
Thiết bị A:
  - JSESSIONID = session-A
  - remember-me = series-A/token-A

Thiết bị B:
  - JSESSIONID = session-B (còn hạn)
  - remember-me = series-B/token-B

User đổi password ở A:
  - delete persistent_logins where username = user
  - invalidate session-A
  - clear remember-me cookie trên A

Sau đó:
  - A phải login lại
  - B có thể vẫn truy cập bằng session-B đang hợp lệ
  - Nếu session-B hết hạn thì remember-me cookie B không tự đăng nhập lại
~~~

Muốn **kết thúc mọi phiên đã xác thực**, cần quản lý sessions theo principal và xóa/invalidate chúng trong kho phiên tương ứng. Với ứng dụng multi-node có Spring Session, có thể dùng các API tìm session theo principal khi có indexed repository phù hợp. Nếu dùng local HttpSession, mỗi node chỉ biết sessions của mình. Không dùng xóa cookie đơn lẻ để khẳng định revoke toàn cluster.

Một số hệ thống chọn **security version/account epoch**: lưu số phiên bản bảo mật của account, đưa phiên bản đó vào thông tin session/token và kiểm tra lại khi request tới. Khi account thay đổi, tăng version để vô hiệu hóa trạng thái cũ. Đây là thiết kế bổ sung, không phải hành vi mặc định của `PersistentTokenBasedRememberMeServices`.

### 7.2. Logout trên một thiết bị và logout trên tất cả thiết bị

Với persistent remember-me mặc định, `removeUserTokens(username)` xóa tất cả series của user. Nếu muốn “chỉ thoát trên thiết bị hiện tại” nhưng giữ remember-me của thiết bị khác, bạn cần một mô hình token repository tùy biến có **delete-by-series**.

Các yêu cầu cần thiết:

- Xác định series từ cookie và xác minh quyền sở hữu nó trước khi xóa.
- Chống race giữa auto-login rotation và revocation, đặc biệt khi nhiều request song song.
- Không cho một user tự chỉ định series của người khác để xóa.
- Vẫn cung cấp đường **revoke all** khi mất thiết bị, reset password hoặc thay đổi bảo mật.
- Cân nhắc event/audit và hiệu lực sau khi transaction commit.

Không thể dùng đúng `PersistentTokenRepository.removeUserTokens(username)` rồi tuyên bố chỉ xóa một thiết bị.

### 7.3. Hai request đồng thời và rotation

Một số browser có thể gửi nhiều request gần như đồng thời bằng cùng cookie remember-me **trước khi phiên mới được thiết lập**. Nếu request đầu làm token rotation, request thứ hai có thể mang token cũ của cùng series. Framework có thể coi đây là mismatched token/cookie theft và xóa các token của user.

Vì vậy, khi test nhiều tab hoặc load lớn, đừng replay cookie cũ nhiều lần và nhầm cơ chế chống đánh cắp với lỗi ngẫu nhiên. Sản phẩm thật cần kiểm thử concurrency, cookie race và điều phối login session phù hợp; **không tắt token rotation hoặc bỏ qua CookieTheftException chỉ để test xanh**.

### 7.4. Token hết hạn nhưng row chưa được dọn

`PersistentTokenBasedRememberMeServices` từ chối token quá tuổi theo `tokenValiditySeconds`, nhưng không mặc nhiên xóa mọi row đã quá hạn khỏi database.

Hãy triển khai **dọn dữ liệu định kỳ** cho `persistent_logins.last_used` dựa trên chính sách lưu trữ/hiệu lực thực tế, ví dụ SQL minh họa:

~~~sql
-- Chạy theo lịch trong môi trường production khi đã đánh giá TTL.
delete from persistent_logins
where last_used < CURRENT_TIMESTAMP - INTERVAL '30' DAY;
~~~

Cú pháp thời gian khác nhau giữa H2/PostgreSQL/MySQL; điều chỉnh cho đúng dialect và chính sách. Đừng xóa row theo một tuổi ngắn hơn tokenValiditySeconds nếu không muốn người dùng bị logout sớm. Không nhầm việc cleanup expired rows với hành động revoke ngay khi có sự kiện bảo mật.

## 8. Thay đổi account trong một transaction: quan điểm nhất quán

### 8.1. Trường hợp cùng một database

Trong demo, `JdbcUserDetailsManager` và `JdbcTokenRepositoryImpl` sử dụng cùng **DataSource**. Dưới `@Transactional`:

~~~text
BEGIN TRANSACTION
  -> verify current credential / policy
  -> UPDATE users SET password = ...
  -> DELETE FROM persistent_logins WHERE username = ...
COMMIT

Sau COMMIT:
  -> clear cookie trên response
  -> invalidate session hiện tại
  -> client phải đăng nhập lại
~~~

Nếu database update password thành công nhưng xóa token lỗi và transaction bị rollback, thay đổi không được báo thành công. Điều này đáp ứng tốt hơn yêu cầu “đổi password phải đồng thời thu hồi khả năng remember-me”.

**Không nên viết:**

~~~java
// Minh họa CÁCH LÀM KHÔNG AN TOÀN.
try {
    persistentTokenRepository.removeUserTokens(username);
} catch (Exception ignored) {
    // Sau đó trả 200 "đã đổi mật khẩu" dù token cũ còn hợp lệ.
}
~~~

Nếu security policy yêu cầu token đã thu hồi, **không được nuốt lỗi rồi trả thành công**. Hãy fail closed, log sự kiện không lộ secret và có quy trình khôi phục.

### 8.2. Khi user store và token store khác nhau

Ví dụ account nằm trong PostgreSQL còn remember-me token nằm trên Redis/dịch vụ khác. Không thể giả định một `@Transactional` thông thường bao trùm cả hai.

Cần thiết kế consistency:

- Thực hiện revoke/token version update theo thứ tự bảo mật đã định.
- Dùng outbox/event delivery có retry và idempotency nếu phù hợp.
- Trong thời gian xử lý chưa xong, bảo đảm token cũ **không tiếp tục mở quyền trái chính sách**; có thể cần account security epoch được kiểm tra ở lớp xác thực.
- Tránh rollback “ảo”: cập nhật DB A nhưng mất kết nối store B không được tuyên bố đã revoke ở B.
- Theo dõi sự kiện revocation thất bại, có cảnh báo và reconciliation.

Với thay đổi nhạy cảm (password reset sau nghi ngờ chiếm tài khoản), ưu tiên trạng thái **không chấp nhận token cũ** cho tới khi hoàn tất, thay vì chấp nhận một cửa sổ token cũ vẫn dùng được mà không được thông báo.

### 8.3. Đổi username/email dùng làm ID

`PersistentTokenRepository.removeUserTokens` dùng `username`. Nếu hệ thống đổi login identifier từ `old@example.com` sang `new@example.com`, phải xác định:

1. Bản ghi `persistent_logins.username` đang dùng **ID nào**?
2. Có bắt buộc xóa theo **username cũ** trước/đồng thời update username không?
3. `UserDetailsService.loadUserByUsername` có chấp nhận ID cũ nữa không?
4. Các active session của user cần invalidation hoặc cập nhật principal thế nào?

Chỉ gọi `removeUserTokens(newUsername)` sau khi đổi tên có thể bỏ lại các row gắn username cũ. Với production, nên dùng **stable account ID** cho các hệ thống token tự thiết kế và map rõ vào user; với JDBC remember-me chuẩn, hãy hiểu khóa username của repository trước khi đổi identifier.

## 9. Khi nào nên yêu cầu xác thực lại?

Remember-me thường được coi là mức tin cậy thấp hơn lần nhập credential trực tiếp, vì cookie có thể tồn tại trên thiết bị lâu ngày. Với các hành động như đổi password, thay MFA, thay email đăng nhập, tạo API key hoặc xem dữ liệu nhạy cảm, nên yêu cầu:

- **Interactive/fresh authentication**, không chỉ `RememberMeAuthenticationToken`.
- Xác minh credential hiện tại hoặc step-up MFA theo chính sách.
- CSRF protection nếu dùng cookie trong browser.
- Rate limit các thao tác nhạy cảm và ghi audit đã bỏ dữ liệu bí mật.

Spring Security cung cấp authorization expression **`fullyAuthenticated()`** để phân biệt request được xác thực đầy đủ với remember-me-only. Trong ví dụ:

~~~java
.requestMatchers("/account/change-password").fullyAuthenticated()
~~~

Điều đó ngăn một người chỉ sở hữu remember-me cookie thực hiện trực tiếp endpoint đổi password trong demo. Tuy vậy `fullyAuthenticated()` không tự chứng minh MFA vừa được thực hiện hoặc phiên còn mới; ứng dụng có yêu cầu cao cần kiểm tra **thời điểm re-auth** và yếu tố xác thực bổ sung.

## 10. Ma trận kiểm thử revoke đúng

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Login form không chọn remember-me | Không tự cấp cookie persistent remember-me mới |
| Login với remember-me | Row persistent token được lưu; cookie được phát |
| JSESSIONID còn hợp lệ | User có thể được xác thực từ session, chưa cần remember-me |
| Chỉ có remember-me cookie hợp lệ | Tự login được, token có thể rotate |
| Logout có Authentication hợp lệ | Session hiện tại kết thúc; cookie hiện tại được clear; persistent tokens của username bị xóa |
| Replay cookie remember-me cũ **không kèm session** sau logout | Không tự login được |
| Đổi password thành công | Password hash đổi, tất cả persistent tokens của user bị xóa, session hiện tại invalidated |
| Current password sai | Không cập nhật password hoặc thu hồi theo luồng đổi mật khẩu thành công |
| POST đổi password thiếu CSRF | 403 trước controller, không đổi dữ liệu |
| Chỉ có remember-me Authentication gọi endpoint fullyAuthenticated | Bị từ chối, cần đăng nhập đầy đủ |
| Password mới, interactive login | Thành công |
| Password cũ sau đổi | Thất bại |
| Một session khác còn đang hoạt động | Có thể tiếp tục nếu chưa có chính sách invalidate toàn bộ session |
| Auto-login đồng thời bằng cùng cookie | Phải xử lý rotation/race; không giả định mọi request đều success |
| Database lỗi khi removeUserTokens | Không báo đổi bảo mật đã revoke thành công nếu thao tác chưa hoàn tất |

### Gợi ý tích hợp Spring Security Test

Khi dự án có `spring-security-test` và `MockMvc`, kiểm thử ở tầng Servlet:

~~~groovy
testImplementation 'org.springframework.security:spring-security-test'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
~~~

Ở test tích hợp, dùng `MockMvc`/cookie jar để:

- Đăng nhập bằng form với `remember-me=on` và CSRF hợp lệ.
- Kiểm tra repository lưu token theo username.
- Logout, sau đó đọc lại repository/DB xác nhận row đã bị xóa.
- Gửi riêng remember-me cookie cũ **không kèm HttpSession**, xác minh bị từ chối.
- Đổi mật khẩu trong phiên fully authenticated, xác minh hash mới, số row token về 0 và session hiện tại bị vô hiệu hóa.
- Kiểm thử account update rollback khi repository xóa token ném exception.
- Kiểm tra các phiên khác theo chính sách hệ thống (nếu có invalidate-all).

**Không chỉ assert HTTP 302/204.** 302 có thể xảy ra vì user chưa login hoặc vì CSRF; cần kiểm tra dữ liệu repository và behavior replay cookie.

## 11. Vận hành production và các rủi ro bổ sung

### 11.1. Cookie bảo mật

- Chỉ truyền remember-me cookie qua **HTTPS/TLS**; bật `Secure`, `HttpOnly` và `SameSite` phù hợp; cookie domain/path càng hẹp càng tốt.
- Không gắn cookie vào URL, email, redirect query hoặc log.
- Không coi `remember-me` là thay thế cho session, MFA hay quản lý revoke ở server.
- Thời hạn `tokenValiditySeconds` cân bằng trải nghiệm và rủi ro: cookie sống lâu tạo thêm thời gian tấn công khi bị mất.
- Với nhiều instance, cấu hình key/cookie/store phải tương thích; không dùng `InMemoryTokenRepositoryImpl` trong cluster production.

### 11.2. PersistentTokenRepository và độ an toàn dữ liệu

- Với JDBC, bảo vệ database bằng least privilege, backup và migration; chỉ application/service cần thiết được truy cập `persistent_logins`.
- Bảo vệ `series` và `token` như dữ liệu nhạy cảm, không log raw hoặc cho user xem bảng token.
- Nếu dùng thiết bị danh sách online, không tùy tiện expose series/token trong response; chỉ trả metadata đã giới hạn như device label/time, và xác minh quyền sở hữu khi revoke.
- Rà soát concurrency giữa login/rotation/revoke. Giao dịch và unique constraint cho series giúp tránh va chạm nhưng không giải quyết mọi race liên quan nhiều request.
- Dọn row hết hạn theo lịch; không phụ thuộc framework tự xóa mọi row cũ.

### 11.3. Thông báo bảo mật và audit

Khi đổi mật khẩu, reset password, khóa account hoặc phát hiện token theft, ghi sự kiện có cấu trúc: account ID, action, timestamp, IP/trusted proxy metadata và correlation ID đã chuẩn hóa, không lưu token/cookie/password. Gửi thông báo cho người dùng qua kênh đã xác minh nếu theo chính sách sản phẩm.

Nếu người dùng báo mất máy, cần luồng revoke all + kiểm tra active sessions; chỉ “đã xóa cookie trên thiết bị đang dùng” là không đủ. Nếu user có token API, OAuth refresh token hay session SSO khác, remember-me revoke không thay thế việc thu hồi các credential loại đó.

### 11.4. Những câu trả lời bảo mật cần tránh

- “Đổi password tự xóa tất cả persistent remember-me tokens”: **sai nếu không có logic removeUserTokens**.
- “Logout chỉ xóa cookie, nên persistent remember-me hoàn toàn không revoke trên server”: **sai với triển khai persistent chuẩn có Authentication**, vì nó xóa token theo username.
- “Xóa persistent_logins sẽ lập tức logout mọi browser”: **sai** nếu browser còn HttpSession đã xác thực.
- “Remember-me cookie là JSESSIONID”: **sai**, đó là hai loại cookie với nhiệm vụ khác nhau.
- “Dùng persistent token là không cần chống CSRF”: **sai**, browser vẫn có thể gửi cookie tự động.
- “Một row persistent token tương đương một phiên HttpSession”: **không đúng**, vòng đời và số lượng không nhất thiết một-một.
- “Có thể kiểm tra revoke bằng cách dùng cookie đã rotate cũ”: **thiếu cơ sở**, vì bản cookie đó đã không hợp lệ trước revoke.

## 12. Bài tập tự kiểm tra

**Câu 1.** Người dùng logout với persistent remember-me và Authentication hợp lệ. Repository thường làm gì?

**Đáp án:** `PersistentTokenBasedRememberMeServices.logout(...)` có thể gọi `removeUserTokens(username)`, thu hồi các row remember-me của username, đồng thời hủy cookie trên response.

**Câu 2.** Sau logout ở thiết bị A, thiết bị B vẫn đang có HttpSession được xác thực. B có bị logout lập tức không?

**Đáp án:** Không nhất thiết. Thu hồi remember-me token ngăn **auto-login về sau**, còn HttpSession đang hoạt động phải được invalidated riêng nếu yêu cầu logout tất cả phiên.

**Câu 3.** Đổi password có làm mất hiệu lực cookie hash-based không?

**Đáp án:** Thường có, vì chữ ký phụ thuộc password hash mà `UserDetailsService` trả về; nhưng không tự hủy HttpSession.

**Câu 4.** Với persistent remember-me, chỉ đổi password trong bảng users đã đủ chưa?

**Đáp án:** Chưa. Persistent token không trực tiếp dựa vào password hash; cần chủ động gọi `PersistentTokenRepository.removeUserTokens(username)` và xem xét active sessions.

**Câu 5.** Vì sao không được xóa `removeUserTokens(requestBody.username)` theo username client gửi?

**Đáp án:** Client có thể chọn username khác để xóa token người khác. Chủ thể phải lấy từ Authentication đã xác thực hoặc workflow quản trị có kiểm tra quyền.

**Câu 6.** Khi đổi username/email đăng nhập, xóa row theo username nào?

**Đáp án:** Cần xác minh key đang lưu trong persistent_logins. Thường phải xóa theo **username cũ** trước/đồng thời đổi identifier, không mặc nhiên xóa theo username mới.

**Câu 7.** Hai request mang cùng cookie persistent được xử lý đồng thời, một request rotate token. Request còn lại có thể gặp lỗi gì?

**Đáp án:** Token của cùng series không còn khớp, có thể bị phát hiện như cookie theft và dẫn tới xóa các token của user. Phải kiểm thử race và không replay token cũ bừa bãi.

**Câu 8.** Vì sao cần transaction cho đổi password và xóa persistent tokens?

**Đáp án:** Tránh báo tài khoản đã được bảo vệ sau khi password đổi mà token cũ vẫn tồn tại do lỗi xóa. Khi dùng cùng DB, `@Transactional` có thể giúp rollback các thay đổi liên quan nếu xảy ra exception.

**Câu 9.** Khi chỉ có remember-me authentication, endpoint đổi password nên dùng authorization nào trong ví dụ?

**Đáp án:** `fullyAuthenticated()`, kèm xác minh current password hoặc step-up theo policy, và CSRF protection.

**Câu 10.** Nếu phải thu hồi một thiết bị cụ thể mà không ảnh hưởng thiết bị khác, API mặc định `removeUserTokens(username)` có phù hợp không?

**Đáp án:** Không. Nó xóa mọi series của user. Cần repository và service tùy biến hỗ trợ revoke theo series đã được xác minh thuộc về user.

## Tài liệu chính thức

- [Spring Security 6.5 — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html)
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — PersistentTokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html)
- [Spring Security 6.5 — PersistentTokenRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenRepository.html)
- [Spring Security 6.5 — RememberMeConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/RememberMeConfigurer.html)
- [Spring Security 6.5 — JDBC Authentication and UserDetailsManager](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/jdbc.html)
- [Spring Security 6.5 — Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
