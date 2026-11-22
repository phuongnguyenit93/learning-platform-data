# Tích hợp kho người dùng riêng qua UserDetailsService

> **Phạm vi:** Spring Security trên **Servlet stack**, Java 17+, Spring Boot 3.x và Spring Security 6.x. Bài này hướng dẫn tích hợp bảng tài khoản do ứng dụng tự thiết kế vào luồng xác thực username/password qua interface `UserDetailsService`, từ mô hình dữ liệu, adapter tra cứu, ánh xạ tài khoản và quyền, đến cấu hình, kiểm thử và bảo mật. Các ví dụ Spring bên dưới là mã thuộc **một dự án Spring Boot** có dependency phù hợp; riêng ví dụ Java SE ở cuối có thể biên dịch độc lập bằng JDK 17.

## 1. Bài toán: dữ liệu người dùng không nằm trong schema mặc định

Nhiều dự án đã có kho tài khoản riêng, chẳng hạn:

- Bảng `app_account` chứa username, password hash, trạng thái tài khoản, khóa đăng nhập.
- Bảng `app_account_role` lưu quyền/nhóm quyền của từng tài khoản.
- Quy trình đăng ký, thay đổi mật khẩu, disable/lock, audit và quản lý quyền do nghiệp vụ sở hữu.

Spring Security **không yêu cầu** bạn chuyển toàn bộ dữ liệu sang schema mặc định của thư viện. Thay vào đó, một `UserDetailsService` có thể đóng vai trò **adapter đọc** giữa mô hình tài khoản nội bộ và hợp đồng xác thực của Spring Security.

~~~text
POST /login  (username + password)
     |
     v
UsernamePasswordAuthenticationFilter
     |
     v
AuthenticationManager / ProviderManager
     |
     v
DaoAuthenticationProvider
     |                                     
     +--> UserDetailsService.loadUserByUsername(username)
     |       |
     |       v
     |   AccountRepository -> app_account + app_account_role
     |       |
     |       v
     |   UserDetails {username, passwordHash, enabled, locked, authorities}
     |
     +--> PasswordEncoder.matches(rawPassword, encodedPassword)
     +--> kiểm tra trạng thái tài khoản
     |
     v
Authentication đã xác thực (hoặc AuthenticationException)
     |
     v
SecurityContext và các bước lưu/response tùy cơ chế đăng nhập
~~~

Điểm cốt lõi: **`UserDetailsService` không tự xác thực password**. Nó chỉ **tải dữ liệu người dùng**. `DaoAuthenticationProvider` mới kết hợp dữ liệu đó với `PasswordEncoder` và các kiểm tra trạng thái để quyết định có cho đăng nhập hay không.

## 2. Bốn ranh giới trách nhiệm cần giữ rõ

| Thành phần | Phải làm | Không nên làm |
| --- | --- | --- |
| `AccountRepository` / DAO | Đọc bản ghi tài khoản, vai trò và metadata từ kho dữ liệu của ứng dụng. | Trực tiếp tạo HTTP session, response hay login redirect. |
| `UserDetailsService` | Chuyển username thành một `UserDetails` đúng hợp đồng Spring Security hoặc ném `UsernameNotFoundException`. | Đọc raw password từ HTTP request, tự so password, tự đặt authenticated flag. |
| `DaoAuthenticationProvider` | Dùng `UserDetailsService`, `PasswordEncoder` và trạng thái account để kiểm chứng username/password. | Quyết định thay ứng dụng toàn bộ chiến lược quyền truy cập từng URL. |
| `SecurityFilterChain`, authentication filter và context | Quy định endpoint, cơ chế login, authorization, success/failure handler, scope của `SecurityContext`. | Đọc SQL trực tiếp cho từng controller chỉ để làm lại logic đăng nhập. |

Nhờ sự phân tách này, bạn có thể thay JDBC bằng JPA, LDAP adapter hay service nội bộ mà không cần viết lại `UsernamePasswordAuthenticationFilter`. Ngược lại, thay password encoder không buộc phải đổi bảng dữ liệu nếu schema hash hỗ trợ định dạng tương ứng.

### Interface trung tâm

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
~~~

Đây là **chữ ký rút gọn của API Spring Security**, không phải một interface tự định nghĩa lại trong dự án. Các kiểu liên quan:

- `org.springframework.security.core.userdetails.UserDetailsService`
- `org.springframework.security.core.userdetails.UserDetails`
- `org.springframework.security.core.userdetails.UsernameNotFoundException`

Hàm nhận **username dùng để tra cứu**; không có tham số raw password. Nếu người dùng không tồn tại, phải ném `UsernameNotFoundException`. Nếu database mất kết nối, đó là **lỗi hạ tầng** và không nên bị biến thành “không có tài khoản” một cách vô điều kiện.

## 3. Hợp đồng `UserDetails`: dữ liệu nào cần ánh xạ?

`UserDetails` biểu diễn dữ liệu mà Spring Security cần cho cơ chế username/password. Nó có các phương thức quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `getUsername()` | Tên đăng nhập hoặc khóa danh tính dùng trong quá trình authentication. |
| `getPassword()` | **Hash/encoded password** đã lưu, không phải raw password do client gửi. |
| `getAuthorities()` | Các `GrantedAuthority` đã được cấp từ nguồn đáng tin cậy. |
| `isEnabled()` | Tài khoản có được phép sử dụng theo chính sách hay không. |
| `isAccountNonLocked()` | `false` nếu tài khoản đã bị khóa. |
| `isAccountNonExpired()` | `false` nếu tài khoản hết hiệu lực. |
| `isCredentialsNonExpired()` | `false` nếu credentials cần thay/đã hết hiệu lực. |

Bạn có thể **tự implement `UserDetails`** để mang thêm các field domain, nhưng phần lớn trường hợp nên **dùng `org.springframework.security.core.userdetails.User`** để ánh xạ. Điều này làm giảm mã bảo trì và hạn chế sai logic `isAccountNonLocked()`, `isCredentialsNonExpired()`.

Ví dụ quy tắc ánh xạ:

~~~text
Domain record                        Spring Security UserDetails
username = "learner"       ------->  username = "learner"
password_hash = "{bcrypt}..." ---->  password = "{bcrypt}..."
enabled = true             ------->  enabled = true
locked = false             ------->  accountNonLocked = true
roles = ["ROLE_LEARNER"]   ------->  authorities = ["ROLE_LEARNER"]
~~~

**Đặc biệt dễ sai:** field domain `locked=true` cần biểu diễn thành `isAccountNonLocked()=false`, tức logic đảo chiều. Với builder `User.withUsername(...)`, có thể gọi `.accountLocked(account.locked())` để tránh tự tính sai.

### Quyền `role` và `authority`

Spring Security cuối cùng kiểm tra các giá trị `GrantedAuthority`. Theo convention thường dùng:

- `.roles("LEARNER")` tạo quyền `ROLE_LEARNER`.
- `.authorities("ROLE_LEARNER")` cung cấp nguyên giá trị `ROLE_LEARNER`.
- `.hasRole("LEARNER")` thường tương đương kiểm tra `ROLE_LEARNER`.
- `.hasAuthority("ROLE_LEARNER")` kiểm tra tên authority đầy đủ.

Nếu database đã lưu `ROLE_LEARNER`, hãy dùng `authorities(...)` và **không** đưa `ROLE_LEARNER` vào `roles(...)` vì dễ tạo sai tiền tố. Nếu hệ thống có quyền chi tiết như `orders:read`, chúng có thể là authority riêng, không bắt buộc mang tiền tố `ROLE_`.

## 4. Tích hợp ví dụ: kho tài khoản riêng với JDBC

Ví dụ là một ứng dụng Spring Boot 3.x sử dụng **H2 in-memory** để người học có thể chạy nhanh. Thiết kế repository/adapter tương tự có thể chuyển sang PostgreSQL hoặc MySQL bằng cách thay datasource và điều chỉnh cú pháp SQL thích hợp. H2 chỉ dành cho demo; không dùng database in-memory hoặc tài khoản thử nghiệm làm kho người dùng production.

Các dependencies cần có:

- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-jdbc`
- `com.h2database:h2` (runtime/demo)
- `spring-boot-starter-test` và `spring-security-test` (test)

Tạo các file Java trong package `com.example.securitydemo` (hoặc package được `@SpringBootApplication` scan). Các ví dụ bên dưới dùng `JdbcTemplate` để phần adapter rõ ràng; không phụ thuộc Hibernate/JPA.

### 4.1. Schema SQL — `src/main/resources/schema.sql`

~~~sql
CREATE TABLE app_account (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    locked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE app_account_role (
    account_id BIGINT NOT NULL,
    role_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (account_id, role_code),
    CONSTRAINT fk_account_role_account
        FOREIGN KEY (account_id) REFERENCES app_account(id)
);
~~~

Điểm chủ đích trong schema:

1. `password_hash` dài đủ để chứa hash có prefix thuật toán như `{bcrypt}...`; không lưu raw password.
2. `username` có ràng buộc `UNIQUE`. Khi dùng username không phân biệt hoa thường, hãy định nghĩa quy tắc chuẩn hóa/collation và unique index tương ứng **nhất quán** giữa đăng ký và đăng nhập.
3. `enabled` và `locked` tách riêng; quy tắc hết hạn account/credentials có thể bổ sung cột mới nếu nghiệp vụ cần.
4. `role_code` lưu tên authority đã chuẩn hóa như `ROLE_LEARNER`, **không** nhận nguyên danh sách quyền từ client trong lúc đăng nhập.
5. Khóa ngoại đảm bảo role không bị mồ côi; các migration production nên quản lý qua Flyway/Liquibase hoặc cơ chế migration thống nhất thay vì chạy lại `CREATE TABLE` theo mỗi lần deploy.

### 4.2. Cấu hình datasource — `src/main/resources/application.properties`

~~~properties
spring.datasource.url=jdbc:h2:mem:securitydemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.h2.console.enabled=false
~~~

Đây là cấu hình **chỉ dành cho môi trường học tập**. Boot sẽ chạy `schema.sql` cho datasource trong demo; không tự suy ra ứng dụng production cũng phải tạo lại schema mỗi lần khởi động. Không commit username/password của database production vào source.

### 4.3. Domain record — `AppAccount.java`

~~~java
package com.example.securitydemo;

public record AppAccount(
        long id,
        String username,
        String passwordHash,
        boolean enabled,
        boolean locked
) {}
~~~

Record của Java 17 giúp model dữ liệu đơn giản và bất biến. Nó là **domain read model**, không phải `UserDetails` và cũng không phải servlet principal của request. Các thao tác đổi mật khẩu, khóa tài khoản hay phân quyền nên đi qua application service có kiểm soát, không mutate một object `UserDetails` đang được dùng để xác thực.

### 4.4. Repository — `JdbcAccountRepository.java`

~~~java
package com.example.securitydemo;

import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class JdbcAccountRepository {
    private final JdbcTemplate jdbc;

    public JdbcAccountRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<AppAccount> findByUsername(String username) {
        List<AppAccount> rows = jdbc.query(
                """
                SELECT id, username, password_hash, enabled, locked
                FROM app_account
                WHERE username = ?
                """,
                (rs, rowNum) -> new AppAccount(
                        rs.getLong("id"),
                        rs.getString("username"),
                        rs.getString("password_hash"),
                        rs.getBoolean("enabled"),
                        rs.getBoolean("locked")
                ),
                username
        );
        return rows.stream().findFirst();
    }

    public List<String> findRoleCodes(long accountId) {
        return jdbc.query(
                """
                SELECT role_code
                FROM app_account_role
                WHERE account_id = ?
                ORDER BY role_code
                """,
                (rs, rowNum) -> rs.getString("role_code"),
                accountId
        );
    }
}
~~~

**Giải thích:**

- Dấu `?` là tham số bind qua `JdbcTemplate`, tránh nối username trực tiếp vào SQL và giảm rủi ro SQL injection.
- Truy vấn đầu tiên chỉ lấy **một username**; unique index đảm bảo có tối đa một account tương ứng.
- Role query dùng account ID từ bản ghi đã đọc, **không tin** ID do client tự gửi.
- Nếu có nhiều authority/tenant/permission được tính theo quy tắc nghiệp vụ, lớp repository và mapper phải có hợp đồng rõ ràng về quyền nào thực sự được dùng để authorize.
- Đọc account và role bằng **hai truy vấn** là đơn giản cho demo. Với hệ thống lớn có độ trễ cao, cân nhắc transaction nhất quán, JOIN phù hợp hoặc cache có invalidation; không suy diễn việc dùng hai query luôn đủ nhanh.

Một sự cố kết nối DB sẽ gây lỗi truy cập dữ liệu; **không nên** bắt toàn bộ exception rồi trả `Optional.empty()`. Nếu làm vậy, hạ tầng hỏng sẽ bị hiểu nhầm là username không tồn tại, khó phát hiện sự cố và có thể sai chiến lược giám sát.

### 4.5. Adapter `UserDetailsService` — `AccountUserDetailsService.java`

~~~java
package com.example.securitydemo;

import java.util.List;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public final class AccountUserDetailsService implements UserDetailsService {
    private final JdbcAccountRepository accounts;

    public AccountUserDetailsService(JdbcAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AppAccount account = accounts.findByUsername(username)
                .orElseThrow(() ->
                    new UsernameNotFoundException("Invalid username or password"));

        List<String> authorities = accounts.findRoleCodes(account.id());

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .authorities(authorities.toArray(String[]::new))
                .build();
    }
}
~~~

**Đây là điểm tích hợp quan trọng nhất của bài.**

1. `@Service` làm cho adapter trở thành một bean của Spring. Khi ứng dụng có một `UserDetailsService` phù hợp và không có cơ chế xác thực khác ghi đè, Spring Security có thể cấu hình `DaoAuthenticationProvider` dùng bean này trong authentication flow username/password.
2. Nếu tài khoản không tồn tại, ném `UsernameNotFoundException` theo hợp đồng thay vì trả `null`.
3. `.password(account.passwordHash())` phải nhận **encoded password lấy từ database**, không phải password do client đang nhập; adapter **không gọi `matches(...)`**.
4. `.disabled(!account.enabled())` và `.accountLocked(account.locked())` phản ánh chính xác quy tắc trạng thái. Với account expired/credentials expired, cần mở rộng domain + mapping tương ứng.
5. `.authorities(...)` dùng quyền được đọc từ hệ thống của server. Không lấy `role=ADMIN` từ form đăng nhập rồi đặt thành authority của user.
6. Nếu kho dữ liệu chưa có role cho một user, có thể trả danh sách rỗng tùy policy; user có thể qua bước authentication nhưng vẫn không được cấp quyền đối với endpoint cần role. Nên có ràng buộc nghiệp vụ rõ về role mặc định và việc cấp quyền.

**Không nhầm lỗi "user không tồn tại" với lỗi password sai:** `DaoAuthenticationProvider` thường che `UsernameNotFoundException` thành lỗi credentials chung ở phía authentication để hạn chế user enumeration. Phần HTTP response cũng nên dùng thông điệp đăng nhập thất bại chung. Điều này không đồng nghĩa bỏ mọi logging vận hành; chỉ không công khai dữ liệu nhạy cảm cho client.

## 5. Cấu hình SecurityFilterChain và PasswordEncoder

Tạo `SecurityConfig.java`:

~~~java
package com.example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(a -> a
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Tại sao dùng `DelegatingPasswordEncoder`?**

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo encoder hỗ trợ nhận biết thuật toán theo prefix hash, ví dụ `{bcrypt}$2a$...`. Khi gọi `encode(...)` trong cấu hình mặc định, mật khẩu được hash bằng BCrypt kèm prefix `{bcrypt}`; khi login, `matches(raw, storedEncoded)` dựa vào prefix để chọn encoder phù hợp. Cách này hữu ích khi cần thay thuật toán hash trong tương lai mà vẫn đọc được hash cũ được hỗ trợ.

Không lưu `"training-only"` trực tiếp vào `password_hash`; cũng không tự hash bằng `SHA-256(password)` thuần. Mật khẩu cần thuật toán chuyên dùng cho password với work factor thích hợp như BCrypt, Argon2 hoặc PBKDF2 theo chính sách hiện tại.

**Một lưu ý về bean auto-configuration:** Với một `UserDetailsService` và một `PasswordEncoder` bean, nhiều cấu hình Spring Security username/password sẽ tự ghép chúng vào `DaoAuthenticationProvider`. Nhưng nếu dự án tự định nghĩa `AuthenticationManager`, `AuthenticationProvider`, có **nhiều** `UserDetailsService`, hoặc nhiều `SecurityFilterChain` với cơ chế riêng, không nên mặc định bean mới sẽ tự được dùng. Hãy kiểm tra authentication manager/provider áp dụng cho đúng chain; khi cần, cấu hình provider một cách tường minh tương thích phiên bản bạn sử dụng.

### Controller kiểm tra đăng nhập — `DemoController.java`

~~~java
package com.example.securitydemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }
}
~~~

`/public` là endpoint công khai, `/me` cần đăng nhập, `/admin` cần `ROLE_ADMIN`. Việc một user có thể đăng nhập thành công **không** tự động cho phép user đó truy cập `/admin`.

### Main class — `SecurityDemoApplication.java`

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

Đặt tất cả class ở chung package `com.example.securitydemo` hoặc package con của package main để Spring Boot component scan tìm thấy `@Service`, `@Repository`, `@Configuration` và `@RestController`.

## 6. Tạo một tài khoản demo đúng cách: chỉ chạy khi bật profile `demo`

Để test integration có dữ liệu, có thể seed một user `learner` với role `ROLE_LEARNER`. Không nhúng mật khẩu demo cố định vào mã ứng dụng production. Ví dụ dưới sử dụng **biến môi trường `DEMO_SEED_PASSWORD`**, chỉ tạo dữ liệu khi kích hoạt profile `demo`.

Tạo `DemoUserInitializer.java`:

~~~java
package com.example.securitydemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
@Profile("demo")
public class DemoUserInitializer {

    @Bean
    ApplicationRunner seedDemoAccount(
            JdbcTemplate jdbc,
            PasswordEncoder encoder,
            @Value("${DEMO_SEED_PASSWORD}") String password) {

        return args -> {
            if (password == null || password.isBlank()) {
                throw new IllegalStateException("Demo password is missing");
            }

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM app_account WHERE username = ?",
                    Integer.class,
                    "learner"
            );
            if (count != null && count > 0) {
                return;
            }

            jdbc.update(
                    """
                    INSERT INTO app_account(username, password_hash, enabled, locked)
                    VALUES (?, ?, ?, ?)
                    """,
                    "learner", encoder.encode(password), true, false
            );

            Long id = jdbc.queryForObject(
                    "SELECT id FROM app_account WHERE username = ?",
                    Long.class,
                    "learner"
            );
            jdbc.update(
                    """
                    INSERT INTO app_account_role(account_id, role_code)
                    VALUES (?, ?)
                    """,
                    id, "ROLE_LEARNER"
            );
        };
    }
}
~~~

**Giới hạn:** `@Profile("demo")` làm bean seed chỉ tồn tại khi profile này được bật. Đây vẫn là demo, không phải hệ thống provisioning production: nó không xử lý hết race condition giữa hai instance, rotation, migration và audit. Trong production hãy quản lý user qua quy trình đăng ký/đổi mật khẩu/quản trị có transaction và kiểm soát truy cập.

Lưu ý khi đặt placeholder Java trong annotation: trong tệp Java thực, nội dung là `@Value("${DEMO_SEED_PASSWORD}")` **không có dấu gạch chéo**. Ký hiệu gạch chéo trong bản Markdown này chỉ dùng cho escape khi soạn tài liệu; annotation cuối cùng cần ghi `@Value("$"+"{DEMO_SEED_PASSWORD}")` theo ý nghĩa một chuỗi placeholder Spring hoàn chỉnh. 

### Chạy demo

Trong terminal Unix/macOS, với Maven Wrapper và ứng dụng Boot đã được tạo:

~~~bash
SPRING_PROFILES_ACTIVE=demo DEMO_SEED_PASSWORD=training-only ./mvnw spring-boot:run
~~~

Trên Windows PowerShell, tương đương:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "demo"
$env:DEMO_SEED_PASSWORD = "training-only"
.\mvnw.cmd spring-boot:run
~~~

`training-only` chỉ là password minh họa cho môi trường local; không dùng nó để bảo vệ tài khoản thật. Trong H2 in-memory, dữ liệu được tạo lại khi process được khởi động mới. Đối với JDBC database production, dữ liệu phải nằm trong DB có persistence và các migration/quy trình cấp quyền chặt chẽ.

### Diễn tiến của một lần login

~~~text
GET /me khi chưa đăng nhập
  -> security chain yêu cầu authenticated user
  -> trình duyệt được chuyển đến form login

POST /login (username=learner, password=training-only, CSRF hợp lệ)
  -> UsernamePasswordAuthenticationFilter tạo token chưa xác thực
  -> AuthenticationManager -> DaoAuthenticationProvider
  -> AccountUserDetailsService.loadUserByUsername("learner")
       -> JDBC tìm account id, password_hash, enabled, locked
       -> JDBC lấy ROLE_LEARNER
       -> Spring UserDetails chứa {bcrypt}... và trạng thái account
  -> PasswordEncoder.matches("training-only", hash) == true
  -> Provider trả Authentication đã xác thực
  -> authentication filter đặt result vào SecurityContext
  -> lưu context/session và success handler theo cấu hình
  -> response redirect theo flow đăng nhập hiện có

GET /me khi browser gửi lại session hợp lệ
  -> SecurityContext được nạp lại theo repository
  -> Authentication.getName() == "learner"
  -> HTTP 200, body "learner"

GET /admin trong cùng session
  -> user chỉ có ROLE_LEARNER, không có ROLE_ADMIN
  -> thường HTTP 403 Forbidden
~~~

Với form login mặc định, CSRF protection thường được bật cho POST; dùng browser form hoặc test helper có CSRF token hợp lệ. **Không** tắt CSRF chỉ để làm mẫu `curl -d "username=...&password=..."` hoạt động.

## 7. Kiểm thử integration: thật sự có đi qua UserDetailsService không?

`MockMvc` + `spring-security-test` kiểm tra request theo servlet security chain, thay vì chỉ mock `UserDetailsService` và tự khẳng định “đã xác thực”.

Tạo `src/test/java/com/example/securitydemo/AccountLoginIntegrationTest.java`:

~~~java
package com.example.securitydemo;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest(properties = "DEMO_SEED_PASSWORD=training-only")
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class AccountLoginIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validPasswordLogsInAndSessionRetainsUser() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("learner").password("training-only"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("learner"))
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("learner"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(formLogin().user("learner").password("wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(unauthenticated());
    }
}
~~~

Vì `@ActiveProfiles("demo")` tạo user H2 khi khởi động test context và `@SpringBootTest(properties=...)` cung cấp demo password, test có dữ liệu đầu vào cụ thể. `formLogin()` là **request builder từ spring-security-test**, không phải `http.formLogin(...)`; nó gửi login request hợp lệ cho cấu hình mặc định và hỗ trợ CSRF. Test thể hiện ba hành vi:

1. Username/password hợp lệ dẫn đến kết quả authenticated.
2. Sau khi login, session dùng lại có thể đọc `/me` với principal `learner`.
3. `ROLE_LEARNER` không được phép truy cập endpoint yêu cầu `ROLE_ADMIN`.

Test sai mật khẩu xác nhận không tạo authenticated principal mới. Output log của Maven/Gradle phụ thuộc môi trường, nên không khẳng định stdout cụ thể. Trên một dự án đã có Maven Wrapper, chạy:

~~~bash
./mvnw test
~~~

**Không suy rộng test này sang mọi cấu hình:** nếu ứng dụng dùng stateless bearer token, đổi login URL, custom success/failure handler, nhiều chain hoặc custom session management, cách assert session/redirect phải thay đổi tương ứng. Tại production, cần thêm test kiểm tra database thật và migration, không chỉ H2.

### Test các trạng thái tài khoản

Bổ sung các ca kiểm thử có thể chạy trên test database biệt lập:

| Dữ liệu trong DB | Hành vi cần quan sát |
| --- | --- |
| Không có username | `loadUserByUsername` ném `UsernameNotFoundException`; login cuối cùng không xác thực. |
| Username có nhưng password sai | `PasswordEncoder.matches(...)` từ chối; không cấp authentication mới. |
| `enabled=false` | Account bị từ chối dù password đúng. |
| `locked=true` | Account bị từ chối theo policy dù password đúng. |
| `ROLE_LEARNER` | Đăng nhập được nhưng bị từ chối ở endpoint yêu cầu `ROLE_ADMIN`. |
| `ROLE_ADMIN` được cấp hợp lệ | Có thể qua check `hasRole("ADMIN")` khi các điều kiện khác hợp lệ. |
| Không có role nào | Đăng nhập có thể thành công nhưng không tự có quyền admin. |
| Database không sẵn sàng | Hệ thống báo/ghi nhận lỗi hạ tầng, không lặng lẽ coi là username không tồn tại. |

Tránh viết test nối tiếp trực tiếp trên dữ liệu dùng chung mà không reset vì thay đổi trạng thái account trong một test có thể làm test khác thất bại không ổn định. Có thể dùng DB riêng, fixture có transaction phù hợp, hoặc strategy dọn dữ liệu có kiểm soát.

## 8. Ví dụ Java 17 độc lập: chuyển một domain account thành principal

Ví dụ Spring ở trên cần Spring Boot/classpath nên không thể `javac` một file mà chạy. Để tự nhìn thấy bước mapping **mà không giả vờ đã xác thực password**, ví dụ Java SE sau mô phỏng repository và view tương đương dữ liệu đầu vào của `UserDetails`.

Tạo `AccountMappingDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

public class AccountMappingDemo {

    record StoredAccount(
            String username, String encodedPassword,
            boolean enabled, boolean locked, List<String> roles) {}

    record PrincipalView(
            String username, boolean enabled,
            boolean accountNonLocked, List<String> authorities) {}

    static PrincipalView load(
            Map<String, StoredAccount> database, String username) {
        StoredAccount account = database.get(username);
        if (account == null) {
            throw new NoSuchElementException("No matching account");
        }
        return new PrincipalView(
                account.username(),
                account.enabled(),
                !account.locked(),
                List.copyOf(account.roles())
        );
    }

    public static void main(String[] args) {
        Map<String, StoredAccount> database = Map.of(
                "learner", new StoredAccount(
                        "learner", "encoded-value-for-demo",
                        true, false, List.of("ROLE_LEARNER"))
        );

        PrincipalView user = load(database, "learner");
        System.out.println("username=" + user.username());
        System.out.println("enabled=" + user.enabled());
        System.out.println("accountNonLocked=" + user.accountNonLocked());
        System.out.println("authorities=" + user.authorities());

        try {
            load(database, "missing");
        } catch (NoSuchElementException ex) {
            System.out.println("missing user rejected");
        }
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac AccountMappingDemo.java
java AccountMappingDemo
~~~

Stdout chính xác:

~~~text
username=learner
enabled=true
accountNonLocked=true
authorities=[ROLE_LEARNER]
missing user rejected
~~~

Đây là **mô phỏng dữ liệu**, không phải hệ thống đăng nhập: `encoded-value-for-demo` không phải BCrypt hash hợp lệ, không gọi `PasswordEncoder.matches(...)` và không cấp `Authentication` thật. Mục tiêu là nhận ra adapter lấy dữ liệu từ domain (không tin client), đảo `locked` thành `accountNonLocked` và đưa role thành danh sách authority. Phần xác minh password phải nằm trong cơ chế provider của Spring Security.

## 9. Dùng JPA hoặc API nội bộ thay JDBC

`UserDetailsService` chỉ yêu cầu method `loadUserByUsername(...)`. Kho người dùng phía sau có thể là:

- **Spring Data JPA:** `JpaRepository<AccountEntity, Long>` với method tìm account theo username, mapping relationship roles. Cần chú ý `LAZY` role collection, `LazyInitializationException`, số lượng query và transaction read-only. Dùng `@EntityGraph`, fetch join hoặc DTO projection thích hợp khi cần lấy roles trong cùng đơn vị truy cập.
- **JDBC như ví dụ:** kiểm soát SQL rõ ràng, đơn giản, dễ nhìn truy vấn và mapping.
- **Dịch vụ tài khoản nội bộ:** adapter gọi service qua client có timeout/circuit-breaker, xác định nguồn quyền, xử lý lỗi hạ tầng; không chuyển raw password qua mạng không an toàn.
- **LDAP hoặc kho tập trung:** có thể dùng các provider/adapter chuẩn tương ứng thay vì tự viết `UserDetailsService` gọi SQL.
- **`JdbcUserDetailsManager` tích hợp sẵn:** phù hợp nếu cấu trúc bảng và truy vấn đơn giản đáp ứng các hợp đồng của nó; bạn có thể cấu hình custom queries trong phạm vi API, nhưng một adapter riêng giúp mapping domain và trạng thái phức tạp minh bạch hơn.

### Vì sao JPA dễ gặp lỗi lazy load?

Giả sử entity `AccountEntity` có `@OneToMany(fetch=LAZY)` hoặc `@ManyToMany(fetch=LAZY)` cho role. Nếu service lấy account, transaction/persistence context đã đóng rồi mới gọi `account.getRoles()`, có thể ném `LazyInitializationException`. Hãy lấy đủ dữ liệu cần cho `UserDetails` trong transaction đọc hoặc query chuyên biệt. Không nên bật `EAGER` bừa bãi cho mọi quan hệ vì dễ tạo query nặng/N+1.

Nếu các role và account status phải có hiệu lực gần như ngay lập tức khi bị thu hồi, cân nhắc chính sách cache. Một `UserDetailsService` có cache tùy chỉnh có thể trả dữ liệu cũ, và session đã đăng nhập có thể đang giữ authorities từ lần xác thực trước. **Khóa tài khoản trong database không tự bảo đảm mọi session đang mở bị vô hiệu hóa ngay**; yêu cầu này cần cơ chế thu hồi session/token/cache hoặc kiểm tra quyền mỗi request phù hợp với mô hình.

## 10. Trường hợp nhiều tenant, email/username và ánh xạ danh tính

### Username không phải lúc nào là khóa duy nhất toàn hệ thống

Ứng dụng multi-tenant có thể chỉ có unique constraint `(tenant_id, username)`. Nếu chỉ gọi `findByUsername(username)`, ứng dụng có thể lấy nhầm account của tenant khác. Cần bảo đảm tenant được xác định bởi ngữ cảnh **đáng tin** và có trong truy vấn DB. Ví dụ ý tưởng:

~~~sql
SELECT id, username, password_hash, enabled, locked
FROM app_account
WHERE tenant_id = ? AND username = ?
~~~

Đây là **SQL minh họa** cho schema multi-tenant, không dùng trực tiếp với bảng demo mục 4 (bảng đó chưa có `tenant_id`). Không tự tin `tenantId` lấy từ form chưa xác thực để cấp quyền cross-tenant. Với kiến trúc phức tạp, có thể cần một authentication provider chuyên biệt, principal có tenant identity rõ và quy tắc phân quyền luôn ràng buộc tenant.

### Email dùng làm username

Bạn có thể truyền email vào tham số `loadUserByUsername`; tên method cố định của interface không có nghĩa bắt buộc hệ thống phải dùng trường `username` theo đúng tên. Nhưng nếu muốn không phân biệt hoa/thường hoặc loại khoảng trắng, phải chuẩn hóa **thống nhất** lúc tạo tài khoản và tra cứu, với constraint chống trùng tương ứng.

Đừng “thử hết mọi account” hay fallback sang username khác khi tìm không ra, vì dễ tạo ambiguity, account takeover hoặc lộ danh tính. Một định danh người dùng phải có ngữ nghĩa tra cứu ổn định.

### Principal nào nên trả về?

Trong nhiều dự án, `org.springframework.security.core.userdetails.User` là đủ. Nếu cần ID domain trong principal, có thể tạo custom `UserDetails` bất biến hoặc dùng lớp principal chuyên biệt. Tránh nhét vào principal toàn bộ JPA entity, raw password, token truy cập dịch vụ, quyền đang thay đổi hoặc object có lazy relationship chưa tải. Principal có thể được giữ trong session, được serialize hoặc log trong các tầng không mong muốn.

## 11. Bảo mật: những điều adapter phải và không được làm

1. **Hash mật khẩu đúng:** ở lúc đăng ký/đổi mật khẩu, gọi `PasswordEncoder.encode(raw)` để lưu; lúc login `DaoAuthenticationProvider` dùng `matches(raw, encoded)`. Với `DelegatingPasswordEncoder`, dữ liệu cũ thiếu prefix `{id}` cần migration hoặc cấu hình tương thích có kiểm soát; không bỏ qua kiểm tra bằng cách nhận plaintext.
2. **Không log secrets:** không log raw password, cột `password_hash`, access token, session cookie hay toàn bộ `UserDetails`. Logging username cũng cần xem xét yêu cầu riêng tư và chống lộ dữ liệu.
3. **Chống user enumeration:** thông điệp thất bại gửi client không cho biết tài khoản tồn tại hay không. Đừng tạo API `/user-exists` không giới hạn chỉ để kiểm tra đăng nhập.
4. **Chống brute-force/credential stuffing:** rate limiting, lockout/backoff có cân nhắc rủi ro, MFA và theo dõi sự kiện bất thường ở tầng xác thực tương ứng. Chỉ tích hợp `UserDetailsService` không tự cung cấp các cơ chế này.
5. **Trạng thái account:** ánh xạ đúng `enabled`, `locked`, expiration. Có thể có logic nghiệp vụ bổ sung cần được enforced trước/cùng với provider.
6. **Phân quyền đáng tin:** authorities được lấy từ nguồn do server quản lý, không tin các trường role do client gửi trong login form.
7. **Tra cứu nhất quán:** username normalization và unique constraint phải tương thích; nếu nhiều tenant, scope truy vấn theo tenant đáng tin.
8. **Phân biệt lỗi dữ liệu và lỗi hệ thống:** DB timeout không phải password sai. Không bắt mọi `Exception` rồi ném `UsernameNotFoundException`; cần alert/metric phù hợp.
9. **Session và CSRF:** trong form login dựa trên cookie, giữ bảo vệ CSRF theo threat model, HTTPS, cookie flags thích hợp, session fixation protection và logout/session revocation. `UserDetailsService` không thay thế chúng.
10. **Không lạm dụng cache:** password đổi, user bị khóa hoặc role bị thu hồi phải có chính sách refresh/invalidation tương ứng; đừng trông chờ session cũ tự cập nhật role.
11. **Thông tin tồn tại trong context:** một `UserDetails` đọc từ DB chỉ là dữ liệu; nó không tự biến thành authenticated `Authentication`. Chỉ provider có trách nhiệm xác thực mới cung cấp kết quả đáng tin.
12. **Giới hạn dữ liệu từ DB:** tránh load toàn bộ quan hệ/PII để trả `UserDetails`; chỉ dữ liệu bắt buộc cho login/authorization.

## 12. Lỗi thường gặp khi triển khai `UserDetailsService`

| Hiện tượng | Nguyên nhân hay gặp | Cách kiểm tra |
| --- | --- | --- |
| Spring vẫn dùng user mặc định thay user trong DB | Bean `UserDetailsService` không được scan, có nhiều beans hoặc custom provider/manager khác chi phối. | Kiểm tra package scan, security config và provider thực tế. |
| `UsernameNotFoundException` dù DB có bản ghi | Query sai tên cột, khác quy tắc hoa/thường/trim hoặc nhầm datasource/tenant. | Kiểm tra query có bind tham số và key tra cứu nhất quán. |
| `BadCredentialsException` dù password “đúng” | Hash lưu sai format, dùng raw password trong DB, encoder không khớp hoặc có thay đổi normalization password không mong muốn. | Kiểm tra prefix và `PasswordEncoder.matches(...)` bằng fixture test, không log password. |
| Đăng nhập được nhưng luôn `403` | Role/authority mapping sai, thiếu `ROLE_` hoặc policy yêu cầu quyền khác. | Xem `GrantedAuthority` được trả và rule `hasRole/hasAuthority`. |
| User bị khóa vẫn đăng nhập được | Custom principal mapping đảo sai `locked` hoặc custom provider bỏ qua state check. | Test `locked=true` và `isAccountNonLocked()==false`. |
| Tài khoản bị disable nhưng session cũ vẫn truy cập | Role/status được kiểm tra lúc login, còn session đang giữ authentication cũ. | Xác định yêu cầu revoke phiên và thực thi chính sách invalidation/re-check. |
| Lỗi `LazyInitializationException` | JPA role association lazy và transaction đã đóng. | Dùng query đủ dữ liệu/transaction read-only. |
| Mỗi request gọi quá nhiều SQL | Authentication per request, N+1 roles, cache hoặc chain cấu hình chưa phù hợp. | Profile query, tối ưu fetch và đánh giá rủi ro dữ liệu cache cũ. |
| Login đúng trong request đầu, request sau mất login | SecurityContextRepository/session policy, explicit-save, cookie không được duy trì. | Phân biệt cơ chế xác thực với lưu context/session. |
| API Bearer token không gọi `UserDetailsService` | Flow sử dụng `JwtAuthenticationProvider` hoặc opaque token provider, không phải Dao provider. | Kiểm tra chain và authentication mechanism. |
| Lỗi `403` ngay lúc POST /login | Thiếu/sai CSRF token ở ứng dụng dùng cookie/form login. | Gửi token hợp lệ, không vội tắt CSRF. |

## 13. Câu hỏi tự kiểm tra

**1. `UserDetailsService` nhận mật khẩu người dùng từ form ở đâu?** Không nhận. Nó chỉ nhận username, đọc `UserDetails`. Password do client cung cấp được authentication filter/manager/provider xử lý riêng để so với encoded password từ `getPassword()`.

**2. Nếu user không có trong database, có nên trả `null`?** Không. Hợp đồng `loadUserByUsername(...)` yêu cầu báo `UsernameNotFoundException` khi không tìm thấy. Lỗi database thật cần được phân biệt với user không tồn tại.

**3. Vì sao `locked=true` không được ánh xạ thẳng sang `isAccountNonLocked()==true`?** Vì tên method mang nghĩa **chưa bị khóa**; `locked=true` tương đương `accountNonLocked=false`.

**4. Tại sao database lưu `ROLE_LEARNER` mà code lại dùng `.authorities(...)`?** Vì `authorities` nhận nguyên authority name. `roles("LEARNER")` mới tự thêm tiền tố `ROLE_` theo convention.

**5. Muốn thay MySQL bằng PostgreSQL có cần viết lại `UsernamePasswordAuthenticationFilter` không?** Không. Giữ hợp đồng `UserDetailsService`, chỉ thay datasource/repository/migration cho đúng hệ quản trị CSDL.

**6. Nếu tài khoản bị disable trong DB, session đang tồn tại có hết hiệu lực ngay không?** Không chắc. Authentication đã được lưu trong session có thể còn hiệu lực đến khi có chính sách kiểm tra lại/thu hồi session hoặc token tương ứng.

**7. `UserDetailsService` có phải cơ chế phù hợp cho mọi JWT bearer request không?** Không. Resource server JWT thường dùng decoder/provider chuyên biệt và không bắt buộc gọi `UserDetailsService`. Chọn adapter theo đúng loại authentication.

**8. Khi cần thêm nhiều phương thức đăng nhập thì nên nhét hết vào `loadUserByUsername(...)`?** Không. Dịch vụ này chỉ phục vụ tra cứu user cho những authentication provider phù hợp. OAuth2/OIDC, JWT hoặc login bất đồng bộ có các hợp đồng/provider riêng.

**Ghi nhớ:** `Kho tài khoản riêng → Repository/DAO → UserDetailsService → UserDetails đáng tin từ server → DaoAuthenticationProvider + PasswordEncoder → Authentication đã xác thực`. Hãy giữ **tra cứu người dùng**, **xác minh credentials**, **quản lý session/context** và **kiểm tra quyền** ở đúng tầng. Đó là chìa khóa để tích hợp một user store tùy chỉnh mà không làm suy yếu mô hình bảo mật của Spring Security.
