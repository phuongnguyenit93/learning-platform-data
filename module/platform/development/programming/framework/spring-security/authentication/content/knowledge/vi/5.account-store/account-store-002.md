# Tùy chỉnh truy vấn JDBC để phù hợp dữ liệu sẵn có

## Mục tiêu

Nhiều hệ thống đã có cơ sở dữ liệu tài khoản trước khi tích hợp Spring Security: bảng không mang tên `users`, mật khẩu nằm ở cột `pwd_digest`, trạng thái là `active`, và role được lưu qua các bảng quan hệ. **Không cần đổi toàn bộ schema chỉ để dùng JDBC authentication.** Ta có thể cấu hình các câu SQL mà Spring Security sử dụng để tải `UserDetails` và `GrantedAuthority`.

Bài thuộc nhóm **Kho tài khoản** trong module *Spring Security - authentication*. Tập trung vào **tùy chỉnh truy vấn đọc tài khoản/quyền trong Spring Security Servlet** bằng `JdbcDaoImpl`, phân biệt trường hợp cần `JdbcUserDetailsManager` để ghi dữ liệu, và các điều kiện để cấu hình an toàn. Các đoạn Java dùng Spring Boot 3.x, Spring Security 6.x, Java 17+; SQL thử nghiệm dùng H2. Khi áp dụng PostgreSQL, MySQL, SQL Server hoặc Oracle cần đổi cú pháp theo dialect tương ứng.

Hoàn thành bài, bạn sẽ biết:

1. Hai truy vấn mặc định của `JdbcDaoImpl` cần những cột nào, **thứ tự** nào và tham số nào.
2. Dùng `setUsersByUsernameQuery(...)` và `setAuthoritiesByUsernameQuery(...)` để ánh xạ schema sẵn có mà không làm giả schema `users`/`authorities`.
3. Xây và chạy ví dụ Spring Boot: tài khoản, password hash, role qua bảng liên kết, HTTP Basic, kiểm thử `200`/`401`/`403`.
4. Xử lý khi schema dùng ID thay username, trạng thái không phải boolean, role có/không có tiền tố `ROLE_`, hoặc quyền được lưu theo group.
5. Phân biệt **đọc dữ liệu đăng nhập** với **ghi tài khoản**; chọn `JdbcDaoImpl`, `JdbcUserDetailsManager` hay `UserDetailsService` tự viết cho đúng nhu cầu.
6. Chẩn đoán các lỗi SQL column order, sai hash, thiếu authority, user trùng, SQL injection, sai tenant và cấu hình DataSource.

## 1. JDBC authentication đặt ở đâu trong luồng xác thực?

Khi ứng dụng dùng username/password, chuỗi trách nhiệm điển hình:

~~~text
HTTP Basic / form login filter
          |
          v
AuthenticationManager (thường ProviderManager)
          |
          v
DaoAuthenticationProvider
          |
          +---> UserDetailsService.loadUserByUsername(username)
          |          |
          |          +---> JdbcDaoImpl
          |                  |-- usersByUsernameQuery
          |                  +-- authoritiesByUsernameQuery
          |                            |
          |                            v
          |                          DataSource / JDBC / database
          |
          +---> PasswordEncoder.matches(raw, storedHash)
          +---> kiểm tra trạng thái account và credentials
          |
          v
   Authentication thành công hoặc AuthenticationException
          |
          v
  SecurityContext + authorization filter
~~~

`JdbcDaoImpl` là một implementation của `UserDetailsService`: nó **tải tài khoản và danh sách authority**. Bản thân câu `SELECT` thành công **không có nghĩa** mật khẩu đã đúng. `DaoAuthenticationProvider` mới kiểm tra password và trạng thái account, sau đó `AuthenticationManager` trả kết quả. Filter là thành phần xử lý request và đưa authentication đã được tin cậy vào security context.

Đừng đặt password thô vào SQL lookup, chẳng hạn `WHERE username = ? AND password = ?`: với mật khẩu lưu dưới dạng hash, kiểm tra như vậy vừa sai thiết kế vừa dễ tạo rủi ro. Lookup chỉ dùng username; mật khẩu do `PasswordEncoder` kiểm tra bằng thuật toán khớp với dữ liệu lưu trữ.

Hai lựa chọn phổ biến:

| Nhu cầu | Thành phần phù hợp | Ghi chú |
| --- | --- | --- |
| Chỉ **đọc** thông tin account và quyền từ JDBC | `JdbcDaoImpl` | Thường đủ khi đang dùng hệ thống account sẵn có |
| Đọc **và** tạo/sửa/xóa người dùng, đổi mật khẩu qua API quản trị | `JdbcUserDetailsManager` | Kế thừa `JdbcDaoImpl` nhưng truy vấn ghi cũng phải được ánh xạ |
| Domain phức tạp (tenant, flags, trạng thái, policy riêng) | `UserDetailsService` tùy chỉnh + repository/JdbcTemplate | Linh hoạt, phải tự ánh xạ `UserDetails` chính xác |
| Chỉ xác thực bearer JWT/OIDC bằng token hợp lệ | Resource server/OAuth2 machinery | Không nhất thiết gọi `UserDetailsService` |

## 2. Hợp đồng truy vấn của JdbcDaoImpl

Các bảng mặc định trong ví dụ Spring Security có cấu trúc gần như:

~~~sql
-- Mô tả schema mặc định ở mức tối giản, KHÔNG chạy
-- đoạn này cùng schema legacy ở phần ví dụ.
CREATE TABLE users (
    username VARCHAR(50) PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(50) NOT NULL
);
~~~

Tương ứng, hai truy vấn mặc định đọc tài khoản và quyền là:

~~~sql
SELECT username, password, enabled
FROM users
WHERE username = ?;

SELECT username, authority
FROM authorities
WHERE username = ?;
~~~

Đây là **hai câu SELECT độc lập**. Mỗi câu dùng **một tham số `?`**, được Spring JDBC bind từ username cần tìm. Hai SQL không tự nối bằng cách app viết code; `JdbcDaoImpl.loadUserByUsername(...)` chạy lookup account rồi thu thập authorities.

### 2.1. usersByUsernameQuery: ba cột theo đúng thứ tự

Truy vấn này phải tạo result set có các cột theo vị trí:

| Cột | Giá trị mà JdbcDaoImpl cần | Ví dụ legacy |
| --- | --- | --- |
| 1 | `username` (hoặc khóa dùng theo cấu hình đặc biệt) | `login_name AS username` |
| 2 | `password` đã lưu (hash) | `pwd_digest AS password` |
| 3 | `enabled` boolean/trạng thái có thể đọc bằng `ResultSet.getBoolean(3)` | `active_flag AS enabled` |

Ví dụ ánh xạ:

~~~sql
SELECT
    a.login_name AS username,
    a.pwd_digest AS password,
    a.active_flag AS enabled
FROM app_accounts a
WHERE a.login_name = ?;
~~~

**Thứ tự quan trọng.** Chỉ đổi alias mà giữ thứ tự sai chưa đủ. `JdbcDaoImpl` đọc ba cột theo vị trí trong đường ánh xạ truyền thống; nếu trả `password, username, enabled` hoặc `id, username, enabled` thì có thể xác thực sai hoặc phát sinh lỗi mapping. Dùng cả thứ tự đúng **và** alias có nghĩa giúp người đọc SQL, driver và công cụ test dễ kiểm tra hơn.

### 2.2. authoritiesByUsernameQuery: hai cột theo đúng thứ tự

Truy vấn quyền phải trả:

| Cột | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| 1 | username/giá trị khóa phù hợp với lookup | `a.login_name AS username` |
| 2 | chuỗi authority | `p.code AS authority` |

~~~sql
SELECT a.login_name AS username, p.code AS authority
FROM app_accounts a
JOIN app_account_permissions ap ON ap.account_id = a.id
JOIN app_permissions p ON p.id = ap.permission_id
WHERE a.login_name = ?;
~~~

Mỗi dòng quyền ứng với một `GrantedAuthority`, ví dụ `ROLE_READER` hoặc `SCOPE_reports.read`. Đừng trả dấu phẩy ghép `ROLE_USER,ROLE_ADMIN` như một chuỗi duy nhất trừ khi bạn tự viết mapper tương ứng: `JdbcDaoImpl` chuẩn sẽ coi đó là **một** authority sai tên.

Mặc định, `JdbcDaoImpl` bật tải authorities riêng lẻ (`enableAuthorities=true`), không tự bật tải quyền group (`enableGroups=false`). Nếu user không có bất kỳ authority nào được tải, `JdbcDaoImpl` tiêu chuẩn có thể ném `UsernameNotFoundException` dù dòng account tồn tại. Hãy xác minh chính sách cho user chưa được cấp quyền thay vì “chữa” bằng việc gán `ROLE_ADMIN` hoặc role mặc định quá rộng.

### 2.3. Vì sao có ký tự `?` trong SQL?

Spring JDBC dùng prepared statement và bind username vào placeholder, không ghép username trực tiếp vào chuỗi SQL. Đúng:

~~~sql
SELECT login_name, pwd_digest, active_flag
FROM app_accounts
WHERE login_name = ?;
~~~

Sai và dễ bị SQL injection:

~~~java
// SAI. Đừng dựng query từ username chưa tin cậy.
String sql = "SELECT * FROM app_accounts WHERE login_name = '"
    + usernameFromRequest + "'";
~~~

`JdbcDaoImpl` tự bind tham số, nên hãy giữ **một placeholder `?`** cho truy vấn lookup. Tên bảng hoặc cột không thể được bind bằng `?`, do đó hãy cấu hình schema cố định, được kiểm soát bởi server. Nếu cần thay đổi theo tenant, tuyệt đối không nối trực tiếp tên schema/table do client gửi; dùng mapping allowlist hoặc datasource/connection được định tuyến từ một tenant identity đã xác minh.

## 3. Trường hợp thực tế: schema tài khoản đã có sẵn

Giả sử hệ thống nghiệp vụ dùng:

~~~text
app_accounts
    id               BIGINT
    login_name       VARCHAR
    pwd_digest       VARCHAR  (BCrypt hash)
    active_flag      BOOLEAN

app_permissions
    id               BIGINT
    code             VARCHAR  ("ROLE_READER", "ROLE_ADMIN")

app_account_permissions
    account_id       BIGINT -> app_accounts.id
    permission_id    BIGINT -> app_permissions.id
~~~

Những tên này **không trùng** `users`, `password`, `enabled`, `authorities` mặc định. Chúng ta sẽ giữ nguyên cách đặt tên như một schema legacy, ánh xạ bằng hai truy vấn đọc trong `JdbcDaoImpl`.

Các mối quan hệ có chủ đích:

- `app_accounts.id` là khóa nội bộ; `login_name` là username dùng khi đăng nhập.
- `pwd_digest` chứa hash do `BCryptPasswordEncoder` tạo; không lưu password rõ.
- `active_flag=false` nghĩa là account disabled.
- Danh sách role là kết quả JOIN account → bảng liên kết → bảng quyền.
- `p.code` đã chứa tiền tố `ROLE_`; không dùng cấu hình tự thêm tiền tố lần nữa.

Một tài khoản hợp lệ được tìm thấy với `usersByUsernameQuery`, còn quyền được nạp từ một hoặc nhiều dòng `authoritiesByUsernameQuery`. Đây là hai khía cạnh dữ liệu khác nhau.

## 4. Ví dụ Spring Boot 3.x / Java 17+ chạy từ đầu đến cuối

Ví dụ sử dụng H2 **chỉ trong môi trường học**, JDBC, Spring MVC và HTTP Basic. Nó có thể chạy ngay sau khi tạo project Maven với những dependency đã liệt kê. Không cần cài database ngoài. Trong production, không dùng H2 memory, không seed mật khẩu demo, phải dùng HTTPS và cấu hình data source/secret an toàn.

### 4.1. Tạo project

Tạo dự án từ Spring Initializr với:

- Spring Boot **3.x**, Java **17+**, Maven.
- Group `com.example`, artifact `legacy-auth`, package `com.example.demo`.
- Dependencies: **Spring Web**, **Spring Security**, **JDBC API / Spring JDBC** (tên starter Maven là `spring-boot-starter-jdbc`), **H2 Database**.
- Các dependency Maven tương ứng gồm `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-jdbc` và `com.h2database:h2` ở scope runtime.

Cây file cần có:

~~~text
legacy-auth/
├── pom.xml                         (Spring Initializr sinh)
└── src/main/
    ├── java/com/example/demo/
    │   └── LegacyJdbcAuthApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 4.2. Tạo schema legacy trong H2

Nội dung **`src/main/resources/schema.sql`**:

~~~sql
CREATE TABLE app_accounts (
    id BIGINT PRIMARY KEY,
    login_name VARCHAR(80) NOT NULL UNIQUE,
    pwd_digest VARCHAR(100) NOT NULL,
    active_flag BOOLEAN NOT NULL
);

CREATE TABLE app_permissions (
    id BIGINT PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE app_account_permissions (
    account_id BIGINT NOT NULL,
    permission_id BIGINT NOT NULL,
    PRIMARY KEY (account_id, permission_id),
    FOREIGN KEY (account_id) REFERENCES app_accounts(id),
    FOREIGN KEY (permission_id) REFERENCES app_permissions(id)
);
~~~

Đây là schema **demo** đủ để chạy. Trong ứng dụng legacy thật, giữ DDL hiện hành; chỉ thay SQL đọc để phù hợp. Không import `users.ddl` mặc định của Spring Security rồi chạy chồng lên schema đang có: nó tạo các bảng không phù hợp, dễ làm người phát triển tưởng authentication đang dùng DB cũ trong khi thực tế lấy dữ liệu từ bảng demo.

### 4.3. Cấu hình DataSource

Nội dung **`src/main/resources/application.properties`**:

~~~properties
spring.datasource.url=jdbc:h2:mem:legacy_auth;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=embedded
~~~

Spring Boot tải `schema.sql` cho embedded database theo cấu hình này trước khi chạy `CommandLineRunner` seed dữ liệu. `DB_CLOSE_DELAY=-1` chỉ phù hợp ví dụ H2 memory. Trong production, nên dùng Flyway/Liquibase hoặc quy trình migration được quản lý thay vì khởi tạo bảng account mỗi lần khởi động.

### 4.4. Định nghĩa UserDetailsService JDBC và AuthenticationProvider

Nội dung đầy đủ file **`src/main/java/com/example/demo/LegacyJdbcAuthApplication.java`**:

~~~java
package com.example.demo;

import java.util.List;
import java.util.stream.Collectors;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.jdbc.JdbcDaoImpl;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class LegacyJdbcAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(LegacyJdbcAuthApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(DataSource dataSource) {
        JdbcDaoImpl jdbc = new JdbcDaoImpl();
        jdbc.setDataSource(dataSource);

        jdbc.setUsersByUsernameQuery("""
            SELECT
                a.login_name AS username,
                a.pwd_digest AS password,
                a.active_flag AS enabled
            FROM app_accounts a
            WHERE a.login_name = ?
            """);

        jdbc.setAuthoritiesByUsernameQuery("""
            SELECT
                a.login_name AS username,
                p.code AS authority
            FROM app_accounts a
            JOIN app_account_permissions ap
              ON ap.account_id = a.id
            JOIN app_permissions p
              ON p.id = ap.permission_id
            WHERE a.login_name = ?
            """);

        return jdbc;
    }

    @Bean
    AuthenticationManager authenticationManager(
        UserDetailsService users,
        PasswordEncoder encoder
    ) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain security(
        HttpSecurity http,
        AuthenticationManager authenticationManager
    ) throws Exception {
        return http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    CommandLineRunner seed(JdbcTemplate jdbc, PasswordEncoder encoder) {
        return args -> {
            jdbc.update(
                "INSERT INTO app_accounts "
                    + "(id, login_name, pwd_digest, active_flag) "
                    + "VALUES (?, ?, ?, ?)",
                101L, "alice", encoder.encode("demo-pass"), true
            );
            jdbc.update(
                "INSERT INTO app_accounts "
                    + "(id, login_name, pwd_digest, active_flag) "
                    + "VALUES (?, ?, ?, ?)",
                102L, "bob", encoder.encode("demo-pass"), true
            );
            jdbc.update(
                "INSERT INTO app_accounts "
                    + "(id, login_name, pwd_digest, active_flag) "
                    + "VALUES (?, ?, ?, ?)",
                103L, "disabled", encoder.encode("demo-pass"), false
            );

            jdbc.update(
                "INSERT INTO app_permissions (id, code) VALUES (?, ?)",
                1L, "ROLE_READER"
            );
            jdbc.update(
                "INSERT INTO app_permissions (id, code) VALUES (?, ?)",
                2L, "ROLE_ADMIN"
            );

            jdbc.update(
                "INSERT INTO app_account_permissions "
                    + "(account_id, permission_id) VALUES (?, ?)",
                101L, 1L
            );
            jdbc.update(
                "INSERT INTO app_account_permissions "
                    + "(account_id, permission_id) VALUES (?, ?)",
                102L, 2L
            );
            jdbc.update(
                "INSERT INTO app_account_permissions "
                    + "(account_id, permission_id) VALUES (?, ?)",
                103L, 1L
            );
        };
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String publicEndpoint() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            String roles = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));

            return "user=" + authentication.getName()
                + "; authorities=" + roles;
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
~~~

#### Tại sao cấu hình này hợp lệ?

1. `userDetailsService(DataSource)` tạo `JdbcDaoImpl`, gắn đúng `DataSource` và thay hai SQL mặc định. Nó không ghi user vào database khi được tạo.
2. `DaoAuthenticationProvider` sử dụng service JDBC để tìm hash và authorities, rồi `PasswordEncoder` để so sánh mật khẩu.
3. `ProviderManager` chứa provider đó. `HttpSecurity.authenticationManager(...)` gắn manager tường minh cho HTTP filter chain, tránh dựa vào suy đoán auto-wiring khi có nhiều provider.
4. `httpBasic(withDefaults())` cho phép gửi credentials bằng HTTP Basic. `authorizeHttpRequests(...)` bảo vệ `/me`, yêu cầu role ADMIN cho `/admin` và cho phép truy cập `/public`.
5. `CommandLineRunner` chỉ seed H2 sau khi schema đã được Spring Boot khởi tạo. Mật khẩu trong DB được **hash bằng BCrypt lúc chạy**; không dùng password rõ trong cột `pwd_digest`.
6. `DemoController` nhận `Authentication` đã xác thực; nó chỉ hiển thị username và authorities, không trả về hash hoặc credentials.

**Giới hạn ví dụ:** password `demo-pass` và H2 memory chỉ dành cho máy học. Seed bằng `CommandLineRunner` khiến ứng dụng ghi dữ liệu mỗi lần khởi động; đừng sao chép bean seed sang môi trường dùng database thật. Tất cả endpoint demo dùng GET nên không cần tắt CSRF để chạy; không thêm `csrf.disable()` chỉ vì bạn dùng HTTP Basic.

### 4.5. Chạy và kiểm tra bằng curl

Tại thư mục chứa `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

PowerShell trên Windows dùng `.\mvnw.cmd spring-boot:run`. Mở terminal khác:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/me
curl -i -u alice:wrong http://localhost:8080/me
curl -i -u bob:demo-pass http://localhost:8080/admin
curl -i -u alice:demo-pass http://localhost:8080/admin
curl -i -u disabled:demo-pass http://localhost:8080/me
curl -i -u nobody:demo-pass http://localhost:8080/me
~~~

Nếu `curl` là alias của PowerShell, dùng `curl.exe` thay thế. Khi chạy đúng code và H2 seed:

| Request | Status kỳ vọng | Dữ liệu quan sát |
| --- | --- | --- |
| `GET /public`, không gửi credentials | `200` | Body `public` |
| `GET /me`, không gửi credentials | `401` | HTTP Basic challenge |
| `GET /me` với `alice:demo-pass` | `200` | Body **chính xác** `user=alice; authorities=ROLE_READER` |
| `GET /me` với `alice:wrong` | `401` | Password không khớp hash |
| `GET /admin` với `bob:demo-pass` | `200` | Body `admin` |
| `GET /admin` với `alice:demo-pass` | `403` | Alice được xác thực nhưng thiếu `ROLE_ADMIN` |
| `GET /me` với `disabled:demo-pass` | `401` | Tài khoản có dữ liệu và hash đúng nhưng `enabled=false` |
| `GET /me` với `nobody:demo-pass` | `401` | Username không được tìm thấy |

Các header và response body khi lỗi phụ thuộc version/filter/servlet container; trọng tâm là các status và body của response thành công. Khi đổi port cấu hình, thay URL tương ứng.

Bạn có thể quan sát những gì đã được nạp bằng cách đặt breakpoint tại `JdbcDaoImpl.loadUserByUsername(...)`, `JdbcDaoImpl.loadUserAuthorities(...)`, `DaoAuthenticationProvider.retrieveUser(...)` và bước `PasswordEncoder.matches(...)`. Không log raw password, header Authorization hoặc hash đầy đủ.

### 4.6. Tự kiểm tra hai câu SELECT tại database

Trong một SQL client dành cho môi trường thử nghiệm, chạy hai query dưới đây sau khi seed (ở SQL console bạn dùng giá trị literal chỉ để đối chiếu; trong ứng dụng vẫn dùng `?`):

~~~sql
SELECT
    a.login_name AS username,
    a.pwd_digest AS password,
    a.active_flag AS enabled
FROM app_accounts a
WHERE a.login_name = 'alice';

SELECT
    a.login_name AS username,
    p.code AS authority
FROM app_accounts a
JOIN app_account_permissions ap ON ap.account_id = a.id
JOIN app_permissions p ON p.id = ap.permission_id
WHERE a.login_name = 'alice';
~~~

Truy vấn 1 phải cho đúng **một dòng** với ba cột `username=alice`, `password=<BCrypt hash>`, `enabled=true`. Giá trị hash khác nhau giữa các lần chạy vì BCrypt tạo salt ngẫu nhiên — đó là hành vi bình thường. Truy vấn 2 phải cho dòng `username=alice`, `authority=ROLE_READER`. Nếu truy vấn 1 có dòng nhưng truy vấn 2 không có dòng, Spring Security có thể báo không tìm thấy `UserDetails`/không có authority, không phải tự động cấp quyền trống.

## 5. Những biến thể schema thực tế và cách viết query

### 5.1. Cột trạng thái không phải BOOLEAN

Có hệ thống dùng `status_code` như `ACTIVE`, `DISABLED` thay vì `active_flag`. Nếu SQL dialect hỗ trợ `CASE`, bạn có thể trả một giá trị boolean:

~~~sql
SELECT
    a.login_name AS username,
    a.password_hash AS password,
    CASE WHEN a.status_code = 'ACTIVE'
         THEN TRUE ELSE FALSE END AS enabled
FROM app_accounts a
WHERE a.login_name = ?;
~~~

Đây là **mẫu điều chỉnh**, không dùng nguyên văn với schema H2 đã chạy phía trên (trong ví dụ đó cột là `active_flag`). Nếu database dùng kiểu `CHAR(1)` như `Y/N` hoặc `1/0`, hãy dùng phép biến đổi phù hợp với dialect; kiểm tra JDBC driver đọc cột 3 qua `ResultSet.getBoolean(3)` đúng kỳ vọng.

Không nên dùng hằng `TRUE AS enabled` chỉ vì bảng không có cột này nếu nghiệp vụ thực tế có trạng thái khóa/vô hiệu hóa: làm vậy có thể bỏ qua kiểm soát account. Nếu domain thật sự không quản lý enabled, bạn có thể dùng một constant boolean đã được quyết định có chủ đích, kèm test và tài liệu chính sách.

### 5.2. Quyền lưu theo bảng liên kết nhiều cấp

Nếu role là `role_id` và bảng quyền dùng mã nghiệp vụ `ADMIN`/`READER`, truy vấn có thể chuẩn hóa ngay:

~~~sql
SELECT a.login_name AS username,
       CONCAT('ROLE_', r.role_code) AS authority
FROM app_accounts a
JOIN app_account_roles ar ON ar.account_id = a.id
JOIN app_roles r ON r.id = ar.role_id
WHERE a.login_name = ?;
~~~

Mẫu này có tính minh họa: đổi tên bảng và hàm concat theo database đang dùng. **Không dùng đồng thời** `CONCAT('ROLE_', ...)` và `JdbcDaoImpl.setRolePrefix("ROLE_")`; kết quả sẽ có dạng `ROLE_ROLE_ADMIN`, làm `hasRole("ADMIN")` thất bại. Ngược lại, nếu DB đã lưu `ROLE_ADMIN` như ví dụ chạy, không thêm prefix.

Lưu ý phân biệt role và authority:

- `hasRole("ADMIN")` thường kiểm tra authority `ROLE_ADMIN` theo prefix mặc định.
- `hasAuthority("reports.read")` kiểm tra đúng chuỗi authority `reports.read`, không tự thêm `ROLE_`.
- Khi dùng một prefix tùy chỉnh toàn hệ thống, cần đồng bộ configuration và tests; đừng chỉ đổi chuỗi ở một trong các câu SQL.

### 5.3. DB dùng khóa số thay username

Giả sử `app_accounts.id` là khóa chính, còn username là `login_name`. Cách ít bất ngờ nhất là **truy vấn user vẫn trả `login_name` ở cột 1**, sau đó JOIN các bảng quyền qua ID trong cùng SQL; mẫu demo mục 4 đã làm như vậy.

`JdbcDaoImpl` còn có tùy chọn `setUsernameBasedPrimaryKey(false)` cho những thiết kế mà cột đầu tiên của kết quả lookup không phải username, và câu query authority được thực hiện bằng khóa tương ứng. Tuy nhiên, khi chọn hướng này phải kiểm thử kỹ cách user lookup, key truyền qua query quyền và username được trả lại, vì sai kiểu hoặc cấu hình có thể gây lỗi account khác nhau theo identity store. Không nên bật cờ chỉ vì database có cột ID: schema demo vẫn dùng ID để join và **không cần** bật cờ.

Nếu username được phép đổi, cân nhắc tác động tới session, cache, audit và cơ chế truy vấn thông qua key ổn định; không tự biến thông tin username thành ID hay ngược lại nếu domain chưa có chính sách mapping rõ ràng.

### 5.4. DB có phân biệt chữ hoa, chuẩn hóa username

`WHERE login_name = ?` có thể so sánh phân biệt hoa/thường hoặc không tùy collation và database. Ví dụ `Alice` và `alice` có thể là hai bản ghi khác nhau trong một môi trường nhưng giống nhau ở môi trường khác.

Bạn có thể có policy **case-insensitive** đã chuẩn hóa và đánh index tương ứng:

~~~sql
SELECT
    a.login_name AS username,
    a.pwd_digest AS password,
    a.active_flag AS enabled
FROM app_accounts a
WHERE LOWER(a.login_name) = LOWER(?);
~~~

Đây là mẫu độc lập, không nên mặc định áp vào mọi DB: biểu thức `LOWER(column)` có thể khiến index thông thường không được dùng, yêu cầu function-based index hoặc normalized column; ngoài ra chuẩn hóa Unicode/email không đơn giản bằng `LOWER`. Ràng buộc UNIQUE và rules tạo account phải thống nhất cùng một quy tắc. **Query lookup phải trả một danh tính xác định**, không chấp nhận nhiều account trùng sau khi normalize.

### 5.5. Quyền gán qua group

`JdbcDaoImpl` hỗ trợ tải group authorities qua:

~~~java
jdbc.setEnableGroups(true);
jdbc.setGroupAuthoritiesByUsernameQuery("""
    SELECT
        g.id,
        g.group_name,
        p.code
    FROM app_groups g
    JOIN app_group_members gm ON gm.group_id = g.id
    JOIN app_group_permissions gp ON gp.group_id = g.id
    JOIN app_permissions p ON p.id = gp.permission_id
    WHERE gm.login_name = ?
    """);
~~~

**Đây chỉ là đoạn minh họa** đặt trong cấu hình `JdbcDaoImpl jdbc` nếu schema thực tế có thêm `app_groups`, `app_group_members` và `app_group_permissions`. **Không** chép thêm ngay vào ứng dụng demo, vì `schema.sql` ví dụ không tạo các bảng đó. Truy vấn group chuẩn có ba cột theo thứ tự: **group ID, group name, authority**. Chế độ group mặc định tắt; cần `setEnableGroups(true)`. Có thể đồng thời dùng authorities trực tiếp và theo group, hoặc chủ động `setEnableAuthorities(false)` khi chỉ có group; với trường hợp thứ hai phải bảo đảm group query tải được quyền cần thiết.

### 5.6. Không dùng JOIN làm nhân bản account trong usersByUsernameQuery

Một lỗi thiết kế thường gặp:

~~~sql
-- SAI CHO LOOKUP ACCOUNT KHI USER CÓ NHIỀU ROLE.
SELECT a.login_name, a.pwd_digest, a.active_flag
FROM app_accounts a
JOIN app_account_permissions ap ON ap.account_id = a.id
WHERE a.login_name = ?;
~~~

Nếu Alice có ba roles, truy vấn này có thể tạo **ba dòng cùng account**. `JdbcDaoImpl` mong danh tính lookup có một record xác định; không nên dựa vào hành vi lấy dòng đầu tiên để hợp thức hóa dữ liệu trùng. Hãy trả đúng một dòng account ở `usersByUsernameQuery`, và đọc nhiều quyền ở `authoritiesByUsernameQuery`. Đặt `UNIQUE` cho username theo chính sách và kiểm thử tài khoản nhiều role.

## 6. Khi dùng JdbcUserDetailsManager thì phải tùy chỉnh cả truy vấn ghi

`JdbcUserDetailsManager` kế thừa `JdbcDaoImpl` và triển khai `UserDetailsManager`: nó có API như `createUser`, `updateUser`, `deleteUser`, `changePassword`, `userExists` và quản lý authorities/groups. Điều này hữu ích **nếu ứng dụng thực sự được phép ghi tài khoản**.

Nhưng việc thay hai SELECT không tự khiến các lệnh INSERT/UPDATE/DELETE mặc định phù hợp schema legacy. Ngoài `setUsersByUsernameQuery` và `setAuthoritiesByUsernameQuery`, implementation hỗ trợ các phương thức như:

- `setCreateUserSql(...)`, `setUpdateUserSql(...)`, `setDeleteUserSql(...)`.
- `setCreateAuthoritySql(...)`, `setDeleteUserAuthoritiesSql(...)`.
- `setUserExistsSql(...)`, `setChangePasswordSql(...)`.
- Các phương thức SQL riêng cho group nếu quản lý group qua manager.

**Đừng gọi `createUser(...)` trên một `JdbcUserDetailsManager` chỉ đổi hai truy vấn SELECT rồi mong lưu được vào `app_accounts`.** Phải điều chỉnh từng DML, thứ tự placeholder, transaction boundaries, khóa ngoại, hashing, audit và phân quyền thao tác.

Ví dụ **chỉ minh họa shape và không chạy trong ứng dụng phía trên**:

~~~java
JdbcUserDetailsManager manager = new JdbcUserDetailsManager(dataSource);

manager.setUsersByUsernameQuery(
    "SELECT login_name, pwd_digest, active_flag "
        + "FROM app_accounts WHERE login_name = ?"
);
manager.setAuthoritiesByUsernameQuery(
    "SELECT a.login_name, p.code FROM app_accounts a "
        + "JOIN app_account_permissions ap ON ap.account_id = a.id "
        + "JOIN app_permissions p ON p.id = ap.permission_id "
        + "WHERE a.login_name = ?"
);

// Nếu thật sự dùng createUser/updateUser/deleteUser,
// cần thiết kế đủ DML cho schema có PK số và bảng liên kết.
// Không được giả định hai SELECT bên trên đủ cho CRUD.
~~~

`JdbcUserDetailsManager` có constructor nhận `DataSource` ở Spring Security 6.5. Ví dụ này không cung cấp DML nên **chỉ nên dùng để đọc như `UserDetailsService`** nếu không có implementation ghi; trong thực tế read-only hãy dùng `JdbcDaoImpl` như ví dụ hoàn chỉnh.

Nếu schema dùng auto-generated ID, nhiều bảng liên kết, audit columns và logic transaction đa bước, một domain service có `@Transactional`/repository thường rõ ràng hơn việc ép mọi thao tác qua các câu SQL cấu hình sẵn. Đừng để user có quyền quản trị account chỉ vì ứng dụng chứa bean `JdbcUserDetailsManager`; endpoint gọi CRUD vẫn phải được bảo vệ bởi authorization phù hợp.

### 6.1. RowMapper tùy chỉnh khi SELECT không đủ

Một số bản Spring Security hiện đại (ví dụ `JdbcUserDetailsManager` từ 6.5) có thêm cấu hình `setUserDetailsMapper(RowMapper<UserDetails>)` và `setGrantedAuthorityMapper(RowMapper<GrantedAuthority>)`. Đây là tùy chọn nâng cao khi kết quả SQL cần mapping riêng. Với `JdbcDaoImpl` truyền thống, hai setter SELECT theo thứ tự cột là con đường ổn định hơn.

Nếu domain cần giữ locked/expired flags hoặc principal chứa account ID và trường bổ sung, đừng tin rằng `JdbcDaoImpl` mặc định sẽ tự map mọi cột thêm vào `UserDetails`. Nó chủ yếu tải username, password, enabled và authorities. Cân nhắc viết `UserDetailsService` riêng:

~~~java
// MẪU MINH HỌA: không phải file chạy độc lập.
@Override
public UserDetails loadUserByUsername(String username) {
    AccountRecord a = accountRepository.findByLogin(username)
        .orElseThrow(() ->
            new UsernameNotFoundException("Unknown account"));

    return User.withUsername(a.loginName())
        .password(a.passwordHash())
        .authorities(a.authorities())
        .disabled(!a.active())
        .accountLocked(a.locked())
        .build();
}
~~~

Đoạn này giả định `AccountRecord`/`accountRepository` là domain types và methods do ứng dụng định nghĩa; không nên chép vào file demo mà không cung cấp repository. Khi dữ liệu bảo mật thay đổi, cache/session/token đã phát cũng cần chính sách cập nhật hoặc thu hồi thích hợp.

## 7. Thử nghiệm độc lập query và tích hợp authentication

Bài toán dữ liệu cũ rất dễ “SELECT chạy được” nhưng “đăng nhập sai”. Hãy chia bài test thành ba lớp.

### 7.1. Kiểm tra SQL trực tiếp

Cho từng username kiểm thử:

| Dữ liệu đầu vào | usersByUsernameQuery | authoritiesByUsernameQuery | Kết quả mong muốn |
| --- | --- | --- | --- |
| Username tồn tại, active=true, 1 quyền | 1 dòng | 1 dòng quyền | Có thể xác thực nếu password đúng |
| Username tồn tại, nhiều quyền | 1 dòng | N dòng | Authorities tổng hợp chính xác |
| Username không tồn tại | 0 dòng | 0 dòng | `UsernameNotFoundException` phía lookup |
| Username tồn tại, không có quyền | 1 dòng | 0 dòng | Kiểm tra chính sách/đặc tính `JdbcDaoImpl` trước khi triển khai |
| Account disabled | 1 dòng enabled=false | Có thể có quyền | Provider từ chối dù password khớp |
| Username trùng theo collation/normalize | Có nguy cơ >1 dòng | Có nguy cơ quyền trộn | **Lỗi dữ liệu** cần giải quyết bằng constraint/policy |

Có thể chạy SQL test bằng database client hoặc integration test `JdbcTemplate.query(...)`. Với H2 demo, các dữ liệu Alice/Bob/disabled cho ba nhánh tiêu biểu.

### 7.2. Kiểm tra UserDetailsService

Một test Spring context có thể inject service và xác nhận dữ liệu (đoạn minh họa, cần starter test):

~~~java
// Trong một @SpringBootTest test class đã inject UserDetailsService:
UserDetails alice = userDetailsService.loadUserByUsername("alice");
assertEquals("alice", alice.getUsername());
assertTrue(alice.isEnabled());
assertTrue(alice.getAuthorities().stream()
    .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
~~~

Kết quả lookup này **không** chứng minh raw password đã được kiểm tra. Muốn xác minh login, phải kiểm thử qua `AuthenticationManager`/HTTP Basic hoặc form login.

### 7.3. Kiểm tra end-to-end HTTP

Các lệnh `curl` tại mục 4 chứng minh ba tầng phân biệt:

1. **Lookup:** Alice được nạp từ `app_accounts` bằng query tùy chỉnh.
2. **Authentication:** mật khẩu khớp BCrypt và account enabled → `200`; sai password/disabled/unknown → `401`.
3. **Authorization:** Bob có `ROLE_ADMIN` vào được `/admin`; Alice có `ROLE_READER` nhận `403`.

Khi thay SQL thật vào dự án đã tồn tại, ưu tiên regression test cho ít nhất: user không tồn tại, active/disabled, nhiều authorities, tên có dấu/Unicode, username case policy, mật khẩu hash cũ và mới, vai trò admin, user thiếu quyền, lỗi database và tenant boundary.

## 8. Chẩn đoán lỗi thường gặp

### Lỗi 1. `BadSqlGrammarException` hoặc báo “table/column not found”

**Nguyên nhân:** SQL dùng bảng `users` mặc định dù database chỉ có `app_accounts`; tên schema khác; alias sai; SQL dialect khác; DataSource trỏ nhầm database.

**Cách xử lý:** xác minh kết nối, tên schema, quyền SELECT, tên cột thực tế; chạy từng SQL với giá trị mẫu rồi thay lại `?`. Kiểm tra query log an toàn và mapping active flag. Không sửa database production trực tiếp chỉ để SQL mẫu chạy.

### Lỗi 2. Username tải đúng nhưng `BadCredentialsException`

**Nguyên nhân thường gặp:** cột 2 không phải hash, query trả cột sai thứ tự, hash dùng thuật toán khác encoder, hoặc nhập sai password. Password thật không thể được tái tạo bằng cách so sánh với chuỗi hash.

**Cách xử lý:** xác nhận result set cột 2 là chuỗi hash thực tế; kiểm tra encoder định dạng phù hợp, ví dụ BCrypt. Với legacy algorithm, hãy lập chiến lược migration hash và dùng `DelegatingPasswordEncoder` khi phù hợp; không bật `NoOpPasswordEncoder` trong production.

### Lỗi 3. User có trong app_accounts nhưng lại “không tìm thấy”

**Nguyên nhân:** authority query trả 0 dòng, điều kiện JOIN sai, username bị khác chữ hoa/thường, hoặc dữ liệu đầu vào/driver không đúng collation. `JdbcDaoImpl` có thể ném `UsernameNotFoundException` khi user không có authority.

**Cách xử lý:** chạy riêng hai query với đúng username; kiểm tra khóa ngoại và mapping quyền. Đừng sửa bằng cách tự gán quyền admin hoặc tắt kiểm tra account status.

### Lỗi 4. `hasRole("ADMIN")` luôn 403 dù tài khoản có quyền

**Nguyên nhân:** DB trả `ADMIN` trong khi policy cần `ROLE_ADMIN`, hoặc vô tình thêm prefix hai lần. Một chuỗi `ADMIN,READER` cũng không tương đương hai authorities.

**Cách xử lý:** quyết định quy ước duy nhất và kiểm tra `Authentication.getAuthorities()` sau khi login trong môi trường dev, không log các thông tin nhạy cảm khác. Nếu dùng custom role prefix, đồng bộ toàn bộ authorization configuration.

### Lỗi 5. User có nhiều role nhưng load sai

**Nguyên nhân:** đưa JOIN roles vào `usersByUsernameQuery` nên nó trả nhiều dòng account, hoặc authority query chỉ lấy dòng đầu tiên/nhầm cột.

**Cách xử lý:** truy vấn user trả đúng một dòng; truy vấn authority trả N dòng, mỗi dòng một tên quyền. Kiểm tra `DISTINCT`/UNIQUE ở quan hệ nhiều-nhiều nếu dữ liệu có trùng.

### Lỗi 6. `enabled=true` nhưng account đã khóa trong domain

**Nguyên nhân:** `JdbcDaoImpl` mặc định không biết tất cả flags nghiệp vụ (lock, expiry, soft-delete, MFA). Query chỉ trả ba cột, trong đó enabled có thể đang ánh xạ sai chính sách.

**Cách xử lý:** xác định rõ những trạng thái cần từ chối đăng nhập, chuyển thành enabled=false khi phù hợp, hoặc viết `UserDetailsService`/provider tùy chỉnh để xử lý các cờ khác. Không coi mọi trạng thái domain chỉ là một boolean.

### Lỗi 7. Tài khoản xác thực được ở môi trường test, production bị lỗi JDBC

**Nguyên nhân:** syntax `TRUE/FALSE`/`CONCAT`/identifier quoting khác dialect, schema name khác, permission thiếu, connection pool không đủ, SSL/certificate DB khác hoặc migration chưa chạy.

**Cách xử lý:** integration test với cùng database engine/dialect hoặc môi trường tương đương production, kiểm tra read permissions và migration. H2 có thể chạy được SQL mà PostgreSQL/Oracle không chấp nhận y hệt.

### Lỗi 8. Lookup lấy nhầm người dùng của tenant khác

**Nguyên nhân:** username chỉ unique trong từng tenant nhưng query `WHERE login_name = ?` bỏ qua tenant; hoặc tenant ID lấy từ HTTP header chưa được xác minh.

**Cách xử lý:** thiết kế lookup với khóa danh tính phù hợp tenant và tín hiệu tenant đáng tin cậy. Có thể cần custom authentication token/provider/`UserDetailsService` hoặc routing DataSource theo policy. **Không** chắp vá bằng cách thêm tham số `?` tùy ý vào query `JdbcDaoImpl`: contract truy vấn chuẩn chỉ tự bind **username**. Nếu thực sự cần tham số thứ hai, phải có tích hợp tùy chỉnh đúng cơ chế.

### Lỗi 9. Không thấy SQL được gọi ở request tiếp theo

**Nguyên nhân:** đã có `SecurityContext` trong session, có cache provider, hoặc request đang đi qua cơ chế authentication khác. Không suy ra query hỏng chỉ vì mỗi request không gọi service.

**Cách xử lý:** xác định filter chain/authentication mechanism, test phiên mới và truy dấu `UserDetailsService.loadUserByUsername(...)`. Đừng cấu hình cache/session chỉ để buộc mỗi request hit DB nếu điều đó không phù hợp kiến trúc.

### Lỗi 10. Đổi SELECT xong, gọi `JdbcUserDetailsManager.createUser` thất bại

**Nguyên nhân:** lệnh ghi mặc định vẫn kỳ vọng bảng mặc định. **Cách xử lý:** chỉ dùng read-only `JdbcDaoImpl` khi không cần CRUD; nếu cần CRUD, cấu hình DML đầy đủ và bảo đảm transaction/ID handling, hoặc dùng domain service thích hợp.

## 9. Lưu ý bảo mật và vận hành với dữ liệu legacy

1. **Password hash:** không bao giờ lưu raw password trong DB hay log, không so sánh string trực tiếp. Kiểm tra hash hiện tại tương thích encoder, dùng migration policy khi cần. H2 demo dùng BCrypt; dữ liệu thật có thể cần nâng cấp thuật toán.
2. **Prepared statement:** giữ `?` cho username và để Spring JDBC bind parameter. Không ghép chuỗi client vào SQL, kể cả câu tra quyền.
3. **Nguyên tắc quyền tối thiểu:** DataSource phục vụ authentication read-only chỉ cần quyền SELECT trên những bảng/view cần thiết. Nếu cùng DataSource được dùng để ghi account, quản lý permissions theo vai trò và endpoint riêng.
4. **Quyền tối thiểu của tài khoản:** ánh xạ chính xác quyền đã cấp; không tự thêm role rộng khi user chưa có authority. Test user role thấp và tài khoản bị disable.
5. **Ranh giới tenant:** nếu username có thể tồn tại ở nhiều tenant, khóa lookup phải mang đủ ngữ cảnh và nguồn tenant phải đáng tin. Sai join trong authorities query có thể gây vượt quyền nghiêm trọng.
6. **Tính nhất quán khi đọc:** hai SELECT liên tiếp có thể nhìn thấy thay đổi DB khác nhau trong một hệ thống concurrent/multi-node. Với yêu cầu mạnh về consistency hoặc revoke tức thì, cần thiết kế transaction/cache/session/token policy thay vì tin tuyệt đối vào hai truy vấn rời.
7. **Hiệu năng:** đặt index trên username, foreign keys và các cột JOIN; thử query plan với dữ liệu đủ lớn, không chỉ H2 dataset ba user. Đừng để N+1 query hoặc query role quá nặng làm login bị nghẽn.
8. **Thất bại phải an toàn:** lỗi connection, timeout, thiếu bảng/cột không được biến thành authenticated user. Đảm bảo monitoring phân biệt lỗi hạ tầng với sai password nhưng response public không tiết lộ thông tin account.
9. **Không thay đổi schema ngoài ý muốn:** tách migration và code; không chạy `schema.sql` demo lên database thật. Quản lý rollout và rollback schema/query theo một phiên bản.
10. **Kết nối và secrets:** DB password nằm trong secret manager/config của deployment, dùng TLS tới DB nếu yêu cầu, hạn chế log JDBC parameters và audit truy cập nhạy cảm.

## 10. Bài tập suy luận

**Bài A — sai thứ tự cột.** Query trả `SELECT pwd_digest AS password, login_name AS username, active_flag AS enabled ...`. Dù alias chính xác, có ổn không?

**Đáp án:** không. `JdbcDaoImpl` thông thường dựa trên **vị trí cột** (1=username, 2=password, 3=enabled). Cần đổi thứ tự SELECT hoặc dùng mapper phù hợp nếu thực sự cần thiết.

**Bài B — thiếu quyền.** Query account trả Alice active=true, query role trả 0 dòng vì bảng liên kết chưa seed. `loadUserByUsername` có chắc vẫn trả account chỉ với mảng authority rỗng không?

**Đáp án:** không được giả định. `JdbcDaoImpl` chuẩn có thể ném `UsernameNotFoundException` khi không tải được `GrantedAuthority`; hãy kiểm tra đúng contract và thiết kế cấp quyền tối thiểu theo nghiệp vụ.

**Bài C — tiền tố ROLE.** Database đã trả `ROLE_ADMIN` nhưng bạn đặt `jdbc.setRolePrefix("ROLE_")`. `hasRole("ADMIN")` sẽ thế nào?

**Đáp án:** có nguy cơ thất bại vì tên quyền thành `ROLE_ROLE_ADMIN`. Dùng một chiến lược prefix duy nhất.

**Bài D — người dùng có bốn quyền.** Bạn đặt JOIN role trong query user và nhận bốn dòng. Thiết kế đúng?

**Đáp án:** không. Query account phải trả một dòng duy nhất; query authorities mới trả nhiều dòng quyền.

**Bài E — database không có enabled nhưng có deletedAt.** Có được trả hằng `TRUE AS enabled` cho mọi account?

**Đáp án:** không nên nếu soft-delete/disabled có ý nghĩa bảo mật. Hãy ánh xạ điều kiện còn hiệu lực thành boolean theo SQL dialect hoặc dùng service domain có policy rõ.

**Bài F — schema dùng account ID.** Khi login bằng username, có cần bật `setUsernameBasedPrimaryKey(false)` chỉ vì bảng có cột `id` không?

**Đáp án:** không. Nếu query user vẫn trả `login_name` ở vị trí 1 và query role join bằng ID rồi lọc theo username như demo, không cần đổi flag.

**Bài G — hai tenant dùng chung login_name.** Có nên sửa `WHERE login_name = ?` thành `WHERE login_name = ? AND tenant_id = ?` rồi chỉ gọi `setUsersByUsernameQuery(...)`?

**Đáp án:** không đủ. `JdbcDaoImpl` thông thường chỉ bind username cho SQL này. Cần thay cơ chế lookup/identity mapping để có tenant đã xác minh và truyền tham số thứ hai an toàn.

## 11. Checklist trước khi ghép vào hệ thống có sẵn

- [ ] Đã xác định chính xác bảng account, cột username/password hash/enabled và các bảng quyền trong schema thật.
- [ ] `usersByUsernameQuery` trả **một** bản ghi với đúng thứ tự username, password, enabled và **một** placeholder username.
- [ ] `authoritiesByUsernameQuery` trả đúng thứ tự username, authority; có thể có nhiều dòng; đã test user không có quyền.
- [ ] Đã kiểm tra quy tắc `ROLE_` hoặc authority name thống nhất giữa DB và authorization.
- [ ] Đã kiểm tra format hash với `PasswordEncoder` thực tế; không dùng raw password trong SQL.
- [ ] `DataSource` trỏ đúng DB/schema; app user có quyền SELECT phù hợp và connection an toàn.
- [ ] Đã thử username không tồn tại, sai password, disabled/locked, user có nhiều role, user không có role và lỗi hạ tầng.
- [ ] Không vô tình ghép user giữa các tenant hoặc query lộ account thuộc miền danh tính khác.
- [ ] Nếu dùng `JdbcUserDetailsManager` để ghi, đã thiết kế đầy đủ mọi DML cần thiết, transaction và authorization; không chỉ thay SELECT.
- [ ] Đã test trên dialect giống production, kiểm tra hiệu năng/index và cơ chế khôi phục session/cache khi thông tin tài khoản thay đổi.

**Kết luận:** muốn tích hợp JDBC authentication với schema cũ, hãy giữ kho tài khoản hiện hữu và **ánh xạ hai câu SELECT theo hợp đồng dữ liệu** của `JdbcDaoImpl`. Query user trả `username, password, enabled` theo vị trí; query quyền trả `username, authority`. `DaoAuthenticationProvider` cùng `PasswordEncoder` mới thực hiện xác thực mật khẩu, còn `SecurityFilterChain` điều khiển HTTP và authorization. Khi nhu cầu vượt hai SELECT — trạng thái domain phức tạp, tenant bổ sung, quản lý user đa bảng — chọn tầng mapping/custom service phù hợp thay vì phá hợp đồng SQL chuẩn.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — JDBC Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/jdbc.html)
- [Spring Security 6.5 — JdbcDaoImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/jdbc/JdbcDaoImpl.html)
- [Spring Security 6.5 — JdbcUserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/JdbcUserDetailsManager.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Security Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
