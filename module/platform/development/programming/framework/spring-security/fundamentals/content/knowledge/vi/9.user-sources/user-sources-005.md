# Kho người dùng JDBC và kho nghiệp vụ qua UserDetailsService tùy chỉnh

## 1. Vì sao phải chọn nguồn người dùng?

Trong những bài học đầu tiên về Spring Security, ta có thể tạo một số user bằng **InMemoryUserDetailsManager** để kiểm thử HTTP Basic hoặc form login. Khi xây ứng dụng thực, tài khoản cần tồn tại qua restart, có quyền được quản trị, bị khóa hoặc thu hồi, đổi password và liên hệ tới dữ liệu nghiệp vụ. Khi đó thông tin xác thực và quyền thường nằm trong cơ sở dữ liệu hoặc hệ thống quản lý danh tính.

Spring Security cung cấp hai con đường phổ biến khi dùng cơ sở dữ liệu quan hệ:

- **JdbcDaoImpl và JdbcUserDetailsManager:** dùng sẵn cách đọc tài khoản và quyền qua JDBC, thường tương ứng bảng users/authorities theo schema của Spring Security.
- **UserDetailsService tùy chỉnh:** tự đọc bảng account/role có sẵn của ứng dụng rồi chuyển chúng sang UserDetails đúng contract Spring Security.

Cả hai nguồn có thể dùng chung **DaoAuthenticationProvider**, **PasswordEncoder** và **SecurityFilterChain**. Điểm khác nhau nằm ở nơi lưu account, câu truy vấn và logic chuyển trạng thái/role thành đối tượng phục vụ xác thực.

Bài dùng **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Spring MVC/Servlet**; chạy demo với **Spring JDBC và H2 in-memory**. Phiên bản được chọn để giải thích API; production phải chọn release còn hỗ trợ và cập nhật bản vá bảo mật, database persistent và quy trình vận hành phù hợp.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt UserDetailsService, UserDetails, UserDetailsManager, JdbcDaoImpl, JdbcUserDetailsManager và DaoAuthenticationProvider.
2. Hiểu schema users/authorities và các SQL queries JDBC mặc định.
3. Xây UserDetailsService đọc bảng app_users/app_user_roles của nghiệp vụ.
4. Ánh xạ BCrypt password hash, enabled, locked và authorities đúng.
5. Chạy cùng một ứng dụng dưới profile **jdbc** và **domain** để so sánh.
6. Kiểm thử bằng curl và MockMvc các nhánh 200, 401, 403.
7. Biết lúc nào nên tùy chỉnh queries của JDBC manager và lúc nào cần service riêng.
8. Tránh các lỗi về SQL injection, prefix ROLE_, user duplication, cache stale, schema migration và quyền trên từng tài nguyên.

## 2. Nguồn user nằm ở đâu trong luồng authentication?

Đối với HTTP Basic hoặc form login, filter lấy username/password, tạo Authentication chưa xác thực, rồi chuyển tới AuthenticationManager. Provider phù hợp, thường là **DaoAuthenticationProvider**, dùng UserDetailsService để tìm account và PasswordEncoder để kiểm chứng credential.

~~~text
HTTP Basic / Form login
         |
         v
AuthenticationFilter
         |
         v
UsernamePasswordAuthenticationToken (chưa xác thực)
         |
         v
AuthenticationManager / ProviderManager
         |
         v
DaoAuthenticationProvider
         |-- loadUserByUsername(username)
         |          |
         |          v
         |      UserDetailsService
         |       /          \
         |      /            \
         | JdbcDaoImpl     Custom Service
         | users/roles     app_users/app_roles
         |      \            /
         |       \          /
         |        UserDetails
         |-- PasswordEncoder.matches(raw, encoded)
         |-- Check enabled, locked, expired
         |
         +-- SUCCESS -> Authentication authenticated
         |                  |
         |                  v
         |             SecurityContext
         |                  |
         |                  v
         |              Authorization
         |
         +-- FAILURE -> AuthenticationException
~~~

Sơ đồ lược bớt các filter để tập trung vào nguồn user. **UserDetailsService chỉ tìm tài khoản**, không tự đánh dấu người gọi đã xác thực và không tự trả HTTP 401. Provider/manager quyết định authentication; filter/entry point xử lý HTTP response.

### 2.1. Bảng trách nhiệm

| Thành phần | Vai trò |
| --- | --- |
| **UserDetailsService** | loadUserByUsername(String), trả UserDetails hoặc UsernameNotFoundException |
| **UserDetails** | Username, encoded password, granted authorities, trạng thái enabled/nonLocked/nonExpired |
| **UserDetailsManager** | Bổ sung thao tác quản lý user: create/update/delete/changePassword/userExists... |
| **JdbcDaoImpl** | UserDetailsService dùng JDBC queries để đọc users và authorities |
| **JdbcUserDetailsManager** | Mở rộng JdbcDaoImpl, triển khai UserDetailsManager để quản lý qua SQL |
| **DaoAuthenticationProvider** | Kiểm tra username/password bằng UserDetailsService và PasswordEncoder |
| **PasswordEncoder** | Tạo hash và matches(rawPassword, hash) |
| **DataSource** | Nguồn kết nối DB được JDBC manager và JdbcTemplate sử dụng |
| **SecurityFilterChain** | Quy tắc URL, httpBasic/formLogin và các security filters |
| **Authentication** | Kết quả danh tính/authorities được xác thực |

### 2.2. Tìm được username chưa chứng minh password đúng

Giả sử user table có row cho alice. UserDetailsService tải row này thành công chỉ chứng minh hệ thống **có bản ghi**. Người gửi request vẫn phải có credential hợp lệ. DaoAuthenticationProvider dùng PasswordEncoder.matches để xác minh.

Không làm theo logic nguy hiểm: “Nếu SELECT tìm thấy user thì trả UsernamePasswordAuthenticationToken.authenticated”. Điều đó cho phép attacker mạo danh bất kỳ username nào có thật.

### 2.3. Không trả UserDetails ra HTTP JSON

UserDetails có encoded password để provider kiểm tra. BCrypt hash vẫn là credential nhạy cảm, không được gửi cho frontend hoặc ghi vào logs. Controller nên trả DTO chứa những trường được phép thay vì trả nguyên UserDetails, Authentication hoặc entity JPA.

## 3. Cách A — JdbcDaoImpl và JdbcUserDetailsManager

### 3.1. JdbcDaoImpl hiểu bảng gì?

**JdbcDaoImpl** là một implementation của UserDetailsService, hỗ trợ những query mặc định đọc:

- Bảng **users**: username, password hash, enabled.
- Bảng **authorities**: username, authority.

Một ví dụ schema H2 tương thích query mặc định:

~~~sql
CREATE TABLE users (
    username VARCHAR(50) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_authorities_users
        FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uq_authorities UNIQUE (username, authority)
);
~~~

Spring Security có tài liệu schema khác nhau theo database dialect. Ví dụ trên dùng kiểu dữ liệu của H2, không phải schema copy-paste bắt buộc cho PostgreSQL/Oracle/MySQL. Trong sản phẩm thực, lựa chọn collation, case sensitivity, index và constraints phải phù hợp chính sách username.

JdbcDaoImpl đọc account bằng truy vấn username, sau đó lấy authorities. Nó biết cờ **enabled**, nhưng schema mặc định không tự mô tả mọi trạng thái nghiệp vụ như locked reason, tenant, subscription hoặc password reset workflow.

### 3.2. JdbcUserDetailsManager khác JdbcDaoImpl ở đâu?

**JdbcUserDetailsManager** mở rộng JdbcDaoImpl và triển khai UserDetailsManager. Ngoài việc đọc account và authorities để xác thực, nó có các phương thức quản lý người dùng như createUser, updateUser, deleteUser, userExists và changePassword.

Tính năng này hữu ích khi ứng dụng dùng schema tương thích Spring Security và cần quản trị tài khoản đơn giản. Nhưng nó **không thay thế toàn bộ chức năng user management của doanh nghiệp**: đăng ký/xác minh email, MFA, audit, quản lý role, đăng xuất mọi thiết bị, chống brute force và quy trình reset password vẫn cần thiết kế.

### 3.3. Authorities và prefix ROLE_

Các giá trị lưu trong bảng authorities là chuỗi quyền cụ thể, ví dụ:

~~~text
username=learner, authority=ROLE_LEARNER
username=admin,   authority=ROLE_ADMIN
~~~

Trong cấu hình thông thường **hasRole("ADMIN")** kiểm tra authority **ROLE_ADMIN**. Nếu database chỉ lưu ADMIN, ứng dụng có thể trả 403 dù đăng nhập thành công.

Có thể thiết kế permission không có ROLE_ như ORDER_READ và dùng hasAuthority("ORDER_READ"). Quan trọng là quy ước role/authority phải nhất quán từ database đến Authentication và SecurityFilterChain.

### 3.4. Khi nào nên chọn JDBC manager?

Khi ứng dụng có account khá đơn giản, có thể dùng schema chuẩn hoặc một biến thể tương thích, muốn ít code truy vấn và có nhu cầu CRUD user cơ bản. Không nên ép schema phức tạp của domain vào mẫu này nếu cần nhiều logic mapping hoặc tenant.

Nếu chỉ cần đọc từ schema khác, có thể tùy biến câu SELECT; nhưng các thao tác ghi trong JdbcUserDetailsManager còn có SQL riêng. Chỉnh hai SELECT không có nghĩa createUser/updateUser/deleteUser sẽ tự hiểu bảng nghiệp vụ.

## 4. Cách B — UserDetailsService tùy chỉnh cho kho nghiệp vụ

Giả sử database hiện tại có:

~~~text
app_users
    id                  BIGINT PRIMARY KEY
    login_name          VARCHAR UNIQUE
    password_hash       VARCHAR
    enabled_flag        BOOLEAN
    locked_flag         BOOLEAN

app_user_roles
    user_id             FK -> app_users.id
    authority           VARCHAR
~~~

Bảng thực tế có thể thêm email, profile, tenant, verification status, failed attempts, password history hoặc quan hệ employee/customer. Chúng không nhất thiết giống users/authorities của JDBC manager.

Một **UserDetailsService tùy chỉnh** chuyển các bảng đó sang UserDetails mà DaoAuthenticationProvider hiểu. Vì provider không cần biết schema, security config không phải đổi khi chuyển store.

### 4.1. Contract của service

Phương thức cần triển khai:

~~~java
@Override
public UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException {
    // Đọc account và authorities từ nguồn tin cậy;
    // trả UserDetails; nếu không có username thì ném exception.
}
~~~

Đây là một **snippet method trong class implements UserDetailsService**, chưa phải Java file độc lập. Service nên:

1. Tra cứu username đã chuẩn hóa theo policy của hệ thống.
2. Nếu không có tài khoản, ném **UsernameNotFoundException**, không trả null.
3. Không bao giờ xác thực raw password tại service.
4. Trả encoded password đúng format PasswordEncoder.
5. Map trạng thái enabled/locked/expired từ nguồn đáng tin.
6. Map authorities từ database, không từ role client tự khai.
7. Không trả nguyên JPA entity phức tạp làm principal.
8. Dùng prepared statement/JdbcTemplate parameters, không nối username trực tiếp vào SQL.
9. Phân biệt lỗi không tìm thấy user với lỗi DB mất kết nối.
10. Kiểm tra uniqueness của username theo chính sách tenant/collation.

### 4.2. Trạng thái tài khoản

UserDetails có các flags enabled, accountNonLocked, accountNonExpired, credentialsNonExpired. Chỉ cần một cờ disabled hoặc locked là có thể làm authentication thất bại theo provider. Nếu nghiệp vụ có nhiều trạng thái (pending, suspended, expired), cần mapping rõ; không tự đánh dấu tất cả active=true chỉ để đăng nhập được.

Trong demo, custom service map enabled_flag sang disabled và locked_flag sang accountLocked. Schema JDBC chuẩn chỉ thể hiện enabled, vì vậy demo JDBC tạo user disabled để so sánh.

### 4.3. Truy vấn role

Một account có thể mang nhiều GrantedAuthority. Nếu database lưu chuỗi ROLE_ADMIN, service có thể tạo **SimpleGrantedAuthority("ROLE_ADMIN")**. Nếu dùng User.withUsername(...).roles("ADMIN"), builder cũng tạo ROLE_ADMIN. Đừng truyền "ROLE_ADMIN" vào roles(...) nếu builder tự thêm prefix; khi đọc chuỗi có prefix sẵn thì nên dùng **authorities(...)**.

## 5. Demo một dự án với hai profile jdbc và domain

Ta sẽ tạo một project Spring Boot duy nhất với hai nguồn xác thực:

| Profile | Bean UserDetailsService được tạo | Bảng |
| --- | --- | --- |
| **jdbc** | JdbcUserDetailsManager | users, authorities |
| **domain** | DomainUserDetailsService | app_users, app_user_roles |

Chúng không active đồng thời. Các endpoint và quy tắc role giống nhau nên **cùng bộ request** kiểm thử được cả hai hướng. Dữ liệu được seed lúc khởi động để học tập; production không seeding password demo và không dùng H2 in-memory.

### 5.1. Dependencies

Tạo dự án Spring Initializr với Spring Boot 3.3.x, Java 17+, Gradle Groovy DSL và Gradle Wrapper. Trong phần **dependencies** của build.gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là phần dependencies của project có Boot plugin/BOM rồi, không phải toàn bộ build.gradle độc lập. JDBC starter cung cấp JdbcTemplate/DataSource integration; H2 driver chỉ dành cho demo.

### 5.2. application.properties

Tạo file **src/main/resources/application.properties**:

~~~properties
spring.datasource.url=jdbc:h2:mem:userstore;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.sql.init.mode=always
spring.profiles.default=jdbc
~~~

Khi không truyền active profile, mặc định là **jdbc**. Khi chạy với **--spring.profiles.active=domain**, Spring chọn profile domain thay thế.

H2 in-memory không giữ dữ liệu qua vòng đời JVM. DB_CLOSE_DELAY=-1 chỉ giữ database trong JVM khi connection cuối đóng, không tạo file persistent. spring.sql.init.mode=always chạy schema.sql khi khởi động demo; với DB production nên dùng Flyway/Liquibase và quản lý migration rõ ràng.

### 5.3. schema.sql

Tạo file **src/main/resources/schema.sql**:

~~~sql
-- Schema đọc/ghi chuẩn của Spring Security JDBC.
CREATE TABLE users (
    username VARCHAR(50) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_authorities_users
        FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uq_authorities UNIQUE (username, authority)
);

-- Schema riêng của nghiệp vụ.
CREATE TABLE app_users (
    id BIGINT NOT NULL PRIMARY KEY,
    login_name VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled_flag BOOLEAN NOT NULL,
    locked_flag BOOLEAN NOT NULL
);

CREATE TABLE app_user_roles (
    user_id BIGINT NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_app_roles
        FOREIGN KEY (user_id) REFERENCES app_users(id),
    CONSTRAINT pk_app_roles PRIMARY KEY (user_id, authority)
);
~~~

Cả hai nhóm bảng được tạo trong H2 demo, nhưng chỉ nguồn user của **profile đang active** được Spring Security sử dụng.

### 5.4. Java source hoàn chỉnh

Tạo file **src/main/java/com/example/userstore/UserStoreApplication.java**:

~~~java
package com.example.userstore;

import java.util.List;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class UserStoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(UserStoreApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/lesson")
                    .hasRole("LEARNER")
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    @Profile("jdbc")
    JdbcUserDetailsManager jdbcUsers(DataSource ds) {
        return new JdbcUserDetailsManager(ds);
    }

    @Bean
    @Profile("jdbc")
    CommandLineRunner seedJdbc(
            JdbcUserDetailsManager users, PasswordEncoder encoder) {
        return args -> {
            if (!users.userExists("learner")) {
                users.createUser(User.withUsername("learner")
                    .password(encoder.encode("learn123"))
                    .roles("LEARNER")
                    .build());
            }
            if (!users.userExists("admin")) {
                users.createUser(User.withUsername("admin")
                    .password(encoder.encode("admin123"))
                    .roles("ADMIN")
                    .build());
            }
            if (!users.userExists("suspended")) {
                users.createUser(User.withUsername("suspended")
                    .password(encoder.encode("suspend123"))
                    .roles("LEARNER")
                    .disabled(true)
                    .build());
            }
        };
    }

    @Bean
    @Profile("domain")
    UserDetailsService domainUsers(JdbcTemplate jdbc) {
        return new DomainUserDetailsService(jdbc);
    }

    @Bean
    @Profile("domain")
    CommandLineRunner seedDomain(
            JdbcTemplate jdbc, PasswordEncoder encoder) {
        return args -> {
            jdbc.update(
                "INSERT INTO app_users " +
                "(id, login_name, password_hash, enabled_flag, " +
                "locked_flag) VALUES (?, ?, ?, ?, ?)",
                1001L, "learner", encoder.encode("learn123"),
                true, false
            );
            jdbc.update(
                "INSERT INTO app_user_roles (user_id, authority) " +
                "VALUES (?, ?)",
                1001L, "ROLE_LEARNER"
            );

            jdbc.update(
                "INSERT INTO app_users " +
                "(id, login_name, password_hash, enabled_flag, " +
                "locked_flag) VALUES (?, ?, ?, ?, ?)",
                1002L, "admin", encoder.encode("admin123"),
                true, false
            );
            jdbc.update(
                "INSERT INTO app_user_roles (user_id, authority) " +
                "VALUES (?, ?)",
                1002L, "ROLE_ADMIN"
            );

            jdbc.update(
                "INSERT INTO app_users " +
                "(id, login_name, password_hash, enabled_flag, " +
                "locked_flag) VALUES (?, ?, ?, ?, ?)",
                1003L, "suspended",
                encoder.encode("suspend123"), false, true
            );
            jdbc.update(
                "INSERT INTO app_user_roles (user_id, authority) " +
                "VALUES (?, ?)",
                1003L, "ROLE_LEARNER"
            );
        };
    }
}

record AccountRow(
    long id,
    String loginName,
    String passwordHash,
    boolean enabled,
    boolean locked
) {}

final class DomainUserDetailsService implements UserDetailsService {

    private final JdbcTemplate jdbc;

    DomainUserDetailsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        List<AccountRow> rows = jdbc.query(
            "SELECT id, login_name, password_hash, " +
            "enabled_flag, locked_flag " +
            "FROM app_users WHERE login_name = ?",
            (rs, rowNum) -> new AccountRow(
                rs.getLong("id"),
                rs.getString("login_name"),
                rs.getString("password_hash"),
                rs.getBoolean("enabled_flag"),
                rs.getBoolean("locked_flag")
            ),
            username
        );

        if (rows.isEmpty()) {
            throw new UsernameNotFoundException("User not found");
        }
        if (rows.size() != 1) {
            throw new IllegalStateException(
                "Duplicate login name in account store");
        }

        AccountRow account = rows.get(0);

        List<SimpleGrantedAuthority> authorities = jdbc.query(
            "SELECT authority FROM app_user_roles WHERE user_id = ?",
            (rs, rowNum) ->
                new SimpleGrantedAuthority(rs.getString("authority")),
            account.id()
        );

        return User.withUsername(account.loginName())
            .password(account.passwordHash())
            .disabled(!account.enabled())
            .accountLocked(account.locked())
            .authorities(authorities)
            .build();
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    Map<String, Object> me(Authentication authentication) {
        var authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", authentication.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/lesson")
    String lessonEndpoint() {
        return "lesson OK";
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

Đây là **một file Java hoàn chỉnh bên trong dự án Boot**, kết hợp application.properties và schema.sql đã liệt kê. Public class trùng tên file, record và class phụ cùng package; Spring Boot phát hiện DemoEndpoints qua component scan. Java 17 có record, var và Stream.toList.

### 5.5. Phân tích wiring theo profile

**Ở mode jdbc:**

- Bean JdbcUserDetailsManager thuộc profile jdbc và thực hiện UserDetailsService.
- Runner seedJdbc tạo ba user bằng createUser và encoded password. Jdbc manager ghi vào users/authorities.
- DaoAuthenticationProvider có thể dùng bean UserDetailsService và PasswordEncoder để kiểm tra thông tin đăng nhập.
- Các rule hasRole không phụ thuộc cách user được truy vấn từ H2.

**Ở mode domain:**

- Bean DomainUserDetailsService thuộc profile domain.
- Runner seedDomain ghi app_users/app_user_roles.
- loadUserByUsername đọc account bằng SQL tham số, đọc authorities qua user_id và tạo UserDetails.
- DaoAuthenticationProvider dùng PasswordEncoder để xác minh hash được service trả về.

**Không kích hoạt cả hai profile cùng lúc trong bài.** Nếu có nhiều UserDetailsService/AuthenticationProvider bean đồng thời, việc Spring Security chọn provider/manager không còn đơn giản; cần cấu hình rõ nguồn user, cơ chế xác thực và thứ tự ưu tiên.

### 5.6. Tại sao có PasswordEncoder bean chung?

UserDetailsService **không so password**. Cả JdbcUserDetailsManager và custom service chỉ trả **hash đã lưu**. BCryptPasswordEncoder có nhiệm vụ so raw password từ HTTP Basic với hash. Nếu đổi encoder mà DB chứa hash theo cơ chế khác, authentication có thể lỗi hàng loạt.

Trong sản phẩm có nhiều kiểu hash, nên dùng **DelegatingPasswordEncoder** với prefix thuật toán thích hợp, có quy trình nâng cấp hash và kiểm thử. Không bật NoOpPasswordEncoder trong production.

### 5.7. Tại sao query dùng dấu hỏi?

Trong DomainUserDetailsService:

~~~java
List<AccountRow> rows = jdbc.query(
    "SELECT id, login_name, password_hash, " +
    "enabled_flag, locked_flag " +
    "FROM app_users WHERE login_name = ?",
    (rs, rowNum) -> new AccountRow(
        rs.getLong("id"),
        rs.getString("login_name"),
        rs.getString("password_hash"),
        rs.getBoolean("enabled_flag"),
        rs.getBoolean("locked_flag")
    ),
    username
);
~~~

**Dấu ? là placeholder** được JdbcTemplate binding với username, giúp tránh SQL injection và lỗi escape. Không nối trực tiếp username do client đưa lên vào chuỗi SQL.

Ứng dụng thật cần thêm policy cho case sensitivity/Unicode normalization, giới hạn độ dài username và unique index. Không tự trim hoặc lowercase nếu chưa thống nhất chính sách và dữ liệu hiện có.

### 5.8. Tại sao UserDetailsService không xử lý HTTP 401?

Khi username không có, service ném UsernameNotFoundException; DaoAuthenticationProvider/AuthenticationManager xử lý AuthenticationException, filter và AuthenticationEntryPoint quyết định HTTP response. Service không truy cập HttpServletResponse hay tự return JSON lỗi.

Nếu database timeout hoặc sai schema, cần báo lỗi hạ tầng đúng cho monitoring; không bắt hết mọi DataAccessException rồi ném UsernameNotFoundException. Public response nên ẩn chi tiết SQL/stack trace.

## 6. Chạy hai profile và so sánh kết quả

### 6.1. Chạy JDBC

Theo application.properties, default profile là jdbc:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell dùng **.\gradlew.bat bootRun**. Boot tạo H2 in-memory, chạy schema.sql, seed user bằng JdbcUserDetailsManager.

### 6.2. Chạy kho nghiệp vụ

Dừng process ở mode jdbc rồi chạy:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=domain'
~~~

PowerShell: **.\gradlew.bat bootRun --args='--spring.profiles.active=domain'**.

Mode domain seed dữ liệu vào app_users/app_user_roles, dùng DomainUserDetailsService. Không sửa Controller hoặc SecurityFilterChain khi đổi profile. Nếu process cũ vẫn chạy ở port 8080, phải dừng nó trước.

### 6.3. Gọi cùng bộ HTTP requests

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u learner:learn123 http://localhost:8080/me
curl -i -u learner:learn123 http://localhost:8080/lesson
curl -i -u learner:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/lesson
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u suspended:suspend123 http://localhost:8080/me
curl -i -u unknown:wrong http://localhost:8080/me
~~~

Trên PowerShell có thể phải dùng **curl.exe** vì curl là alias. Mật khẩu hard-code chỉ dành cho demo localhost. Để tránh mật khẩu xuất hiện trong shell history, có thể dùng **curl -i -u learner URL**, rồi nhập password qua prompt. HTTP Basic truyền credential dạng Base64, nên phải dùng HTTPS qua mạng.

### 6.4. Ma trận kết quả dự kiến

| Request | Profile jdbc | Profile domain | Giải thích |
| --- | --- | --- | --- |
| GET /public anonymous | **200** | **200** | permitAll |
| GET /me anonymous | **401** | **401** | Basic yêu cầu xác thực |
| GET /me learner đúng password | **200** | **200** | Hash matches |
| GET /lesson learner | **200** | **200** | ROLE_LEARNER |
| GET /admin learner | **403** | **403** | Thiếu ROLE_ADMIN |
| GET /lesson admin | **403** | **403** | Thiếu ROLE_LEARNER |
| GET /admin admin | **200** | **200** | ROLE_ADMIN |
| GET /me suspended | **401** | **401** | Account disabled |
| GET /me unknown | **401** | **401** | Không có username |

Đây là kết quả **kỳ vọng theo cấu hình demo**, không phải log đo từ một server đã chạy trong bài viết. Cấu hình proxy, filter bổ sung, entry point hoặc session khác có thể làm response thay đổi.

Với learner gọi /me, JSON dự kiến:

~~~json
{
  "username": "learner",
  "authorities": ["ROLE_LEARNER"]
}
~~~

Thứ tự các key không bảo đảm. Controller chỉ trả fields cần thiết, không serialize UserDetails/Authentication/password hash.

### 6.5. Ý nghĩa kết quả

Hai profile cho cùng authentication/authorization behavior vì UserDetails được tạo nhất quán về username, encoded password, trạng thái account và authorities. **Thay source user không bắt buộc thay policy URL**.

Điều khác nhau là cách quản lý user ở database: JDBC manager biết schema mặc định và cung cấp createUser; custom service đọc domain tables với ID và flags tùy ý.

## 7. MockMvc integration test cho nguồn nghiệp vụ

Trong project có spring-boot-starter-test, tạo file **src/test/java/com/example/userstore/DomainStoreHttpTest.java**:

~~~java
package com.example.userstore;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("domain")
class DomainStoreHttpTest {

    @Autowired
    MockMvc mvc;

    private String basic(String user, String password) {
        String pair = user + ":" + password;
        return "Basic " + Base64.getEncoder().encodeToString(
            pair.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void businessStoreLoadsUserAndAuthorities() throws Exception {
        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "learn123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authorities[0]")
                .value("ROLE_LEARNER"));
    }

    @Test
    void invalidAndDisabledUsersAreRejected() throws Exception {
        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("suspended", "suspend123")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("unknown", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizationUsesRolesLoadedFromDatabase()
            throws Exception {
        mvc.perform(get("/lesson")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "learn123")))
            .andExpect(status().isOk());

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "learn123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("admin", "admin123")))
            .andExpect(status().isOk());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

PowerShell dùng **.\gradlew.bat test**. File test cố định profile domain để kiểm tra schema nghiệp vụ. Có thể tạo test tương đương với @ActiveProfiles("jdbc") để kiểm tra JDBC manager. Nếu chạy nhiều Spring application contexts dùng H2 trong cùng JVM, cần cấu hình database name riêng cho mỗi context hoặc dùng generate-unique-name để tránh chúng dùng chung H2 in-memory database và tạo bảng trùng.

**MockMvc kiểm tra HTTP contract, không chứng minh khả năng chịu tải hoặc mọi cạnh bảo mật.** Production cần test schema migration, stale cache, concurrent login, DB unavailable, SQL injection và update/revoke quyền.

## 8. Có thể chỉ đổi SQL mặc định thay vì viết service riêng?

Nếu schema nghiệp vụ gần với JDBC contract, JdbcDaoImpl/JdbcUserDetailsManager cho phép tùy biến những truy vấn tải user/authority. Snippet:

~~~java
JdbcUserDetailsManager manager = new JdbcUserDetailsManager(dataSource);
manager.setUsersByUsernameQuery(
    "SELECT login_name AS username, password_hash AS password, " +
    "enabled_flag AS enabled " +
    "FROM app_users WHERE login_name = ?"
);
manager.setAuthoritiesByUsernameQuery(
    "SELECT u.login_name AS username, r.authority " +
    "FROM app_users u JOIN app_user_roles r ON r.user_id = u.id " +
    "WHERE u.login_name = ?"
);
~~~

Đây là đoạn cấu hình minh họa trong method có biến dataSource, **không phải file Java chạy độc lập**. Truy vấn phải đáp ứng contract cột mà JdbcDaoImpl version đang dùng; cần kiểm tra qua integration test.

**Cảnh báo:** chỉ đổi hai SELECT **không tự sửa các câu INSERT/UPDATE/DELETE/changepassword** của JdbcUserDetailsManager. Nếu dùng manager để ghi account, bạn phải cấu hình hoặc thay thế toàn bộ SQL liên quan, bảo đảm transaction và audit nhất quán. Với kho nghiệp vụ phức tạp, custom UserDetailsService riêng có thể dễ hiểu và an toàn hơn.

Nếu chỉ muốn đọc và không làm quản lý user qua manager, có thể xem JdbcDaoImpl hoặc service riêng phù hợp. Không biến đối tượng phục vụ authentication thành chỗ chứa mọi thao tác quản trị user.

## 9. Nếu ứng dụng dùng Spring Data JPA?

Thay vì JdbcTemplate, một service có thể inject AccountRepository và RoleRepository để đọc entity/DTO. Logic cơ bản vẫn là **username -> account -> encoded password + account flags + authorities -> UserDetails**.

Snippet minh họa phương thức trong service đã có repository và mapper:

~~~java
@Override
public UserDetails loadUserByUsername(String username) {
    AccountEntity account = repository.findByLoginName(username)
        .orElseThrow(() ->
            new UsernameNotFoundException("User not found"));

    return User.withUsername(account.getLoginName())
        .password(account.getPasswordHash())
        .disabled(!account.isEnabled())
        .accountLocked(account.isLocked())
        .authorities(roleMapper.toGrantedAuthorities(account.getRoles()))
        .build();
}
~~~

Đây không phải ví dụ độc lập vì AccountEntity, repository và roleMapper là thành phần ứng dụng cụ thể. Khi áp dụng thật:

- Đảm bảo transaction/lookup tải đủ role, tránh LazyInitializationException.
- Không trả thẳng entity có password hash, email, số điện thoại, quan hệ JPA làm principal hoặc response.
- Dùng projection/query hợp lý, indexes và unique constraints.
- Không bật Open Session in View chỉ để che lỗi mapping role.
- Xác minh mapping trạng thái account không xung đột với rule nghiệp vụ.

## 10. Dữ liệu và vòng đời credential

### 10.1. Hash là dữ liệu nhạy cảm

BCrypt hash không phải plaintext nhưng vẫn có thể được dùng cho brute-force offline nếu lộ. Cần kiểm soát quyền DB, backup, logs, tracing và API response.

Trong demo, PasswordEncoder.encode chạy khi seed để tạo hash. Với database production, registration/password-change flow cần tạo hash trong service được kiểm soát và không ghi password raw xuống database.

### 10.2. DelegatingPasswordEncoder và migration

Một hệ thống có thể tồn tại nhiều thế hệ hash: BCrypt, PBKDF2 hoặc Argon2 với tham số khác nhau. DelegatingPasswordEncoder hỗ trợ lưu giá trị có prefix thuật toán như {bcrypt} để định tuyến encoder. Nếu đổi từ BCryptPasswordEncoder trực tiếp sang DelegatingPasswordEncoder, phải kiểm tra định dạng password_hash đã tồn tại. Không đổi bean trong production rồi cho rằng dữ liệu cũ tự tương thích.

### 10.3. Credential erasure và caching

ProviderManager thường cố erase credentials trên Authentication thành công nếu object hỗ trợ CredentialsContainer. Nếu UserDetails trong cache và principal dùng cùng object mutable, erasure có thể xóa password trong cache gây lỗi các lần authenticate sau.

Khi caching UserDetails, phải cân nhắc copy object, TTL, invalidation sau đổi password/role, credential lifecycle và account disabled. Không tắt credential erasure chỉ để tránh lỗi mà chưa phân tích rủi ro.

### 10.4. Token/session cũ sau đổi nguồn user

Nếu role hoặc account status được đổi trong DB, một session hoặc JWT được phát hành trước đó có thể còn authorities cũ. Thay UserDetailsService không tự hủy mọi session/token. Cần chiến lược expiry, revocation, refresh hoặc kiểm tra quyền tại request nhạy cảm.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Password đúng vẫn 401 | Encoder không khớp format hash | Kiểm tra stored hash, PasswordEncoder, prefix |
| JDBC báo table users not found | Schema.sql chưa chạy, sai DB/profile | Kiểm tra DataSource, initialization, migration |
| Custom store 401 cho user có thật | SQL query sai field, case sensitivity hoặc flag | Đọc UserDetails kết quả và account state |
| Login đúng nhưng /admin 403 | Authority thiếu ROLE_ADMIN | Xem mapping DB authority và hasRole |
| Có hai UserDetailsService gây cấu hình mơ hồ | Hai profile cùng active hoặc extra bean | Chọn rõ source hoặc cấu hình manager/provider |
| Password hash lộ ở JSON/log | Return nguyên UserDetails/entity/Auth | DTO allowlist, redaction, hạn chế log |
| User bị khóa vẫn login | Service bỏ qua accountLocked mapping | Map status và test nhánh locked/disabled |
| Lookup thành công nhưng DB outage bị 401 | Bắt DataAccessException rồi đổi thành user not found | Phân biệt operational error với not-found |
| Role thay đổi nhưng session còn quyền cũ | Cache/Authentication stale | Invalidation/re-auth/re-check |
| Duplicate username | Thiếu unique constraint hoặc canonicalization | Unique index, migration dữ liệu |
| SQL injection | Nối username vào query string | Dùng parameterized query |
| User domain bị kiểm tra sai tenant | Query chỉ theo username nhưng tenant scoped | Thiết kế identity key và tenant verification |
| H2 mất data khi restart | In-memory database | Dùng persistent DB và migration ở production |
| Seed bị chạy nhiều lần trên DB thật | CommandLineRunner tạo test users vô điều kiện | Seed chỉ local, data migrations riêng |

### 11.1. Tại sao không dùng bean chung cho cả manager JDBC và custom service?

Nếu tạo cả JdbcUserDetailsManager và DomainUserDetailsService cùng lúc, Spring có thể không tự quyết định được UserDetailsService nào là nguồn authentication. Auto-configuration có thể rút lui hoặc provider được tạo khác dự kiến.

Trong demo, @Profile giải quyết rõ ràng. Ứng dụng thật kết hợp nhiều identity sources có thể cần AuthenticationProvider hoặc AuthenticationManager riêng cho từng cơ chế, nhưng phải thiết kế nhất quán cách xác định user, issuer/tenant và quyền, không dùng thứ tự ngẫu nhiên của beans.

### 11.2. Tại sao không tự xây login bằng service?

UserDetailsService không phải API xác thực hoàn chỉnh. Nếu Controller chỉ load user rồi tạo Authentication authenticated=true, client có thể giả mạo danh tính. Hãy để Security filter + AuthenticationManager/DaoAuthenticationProvider thực hiện quy trình.

### 11.3. Vì sao tài khoản admin không tự có quyền learner?

Trong demo, admin có ROLE_ADMIN, learner có ROLE_LEARNER. hasRole("LEARNER") không tự xem ROLE_ADMIN là quyền cao hơn trừ khi bạn thiết kế role hierarchy hoặc granted authorities phù hợp. Vì vậy GET /lesson với admin có thể nhận 403 dù admin login thành công.

## 12. Chuyển từ demo sang production

1. **Chọn nguồn account duy nhất:** JDBC manager, domain DB hoặc IdP; xác định cách username/subject/tenant được định danh ổn định.
2. **Quản lý schema bằng migration:** Flyway/Liquibase, constraints, indexes, rollback và backup. Không dùng schema.sql tạo bảng mỗi start trên DB thật.
3. **Chỉ lưu password hash phù hợp:** chọn encoder, cost, migration và không ghi credential vào log/trace.
4. **Bảo vệ database:** hạn chế quyền account kết nối, TLS cho connection nếu cần, secret management và rotation.
5. **Xác minh status/role:** disabled, locked, expired, password lifecycle, authority mapping và token/session revocation.
6. **Thiết kế authorization trên dữ liệu:** user A không đọc record của B, tenant boundary và permission nghiệp vụ.
7. **Tách HTTP contract khỏi nguồn dữ liệu:** Không return UserDetails, entity, password hash hoặc SQL errors ra response.
8. **Giới hạn brute force:** rate limiting, monitoring, chống password spraying/credential stuffing và account enumeration.
9. **Kiểm thử cả thành công/thất bại:** sai password, user không tồn tại, account locked, DB down, duplicate username và roles thiếu.
10. **Vận hành cache có kiểm soát:** TTL, invalidate sau đổi role/password, account disabled, tránh shared mutable object chứa hash.
11. **Quan sát hiệu năng:** index lookup login_name, authorities query, connection pool size, query time, concurrency.
12. **Thử khi nâng version:** Spring Boot, Spring Security, JDBC driver, H2/production database dialect, SQL migrations.

### 12.1. Lưu ý multi-tenant

Một username có thể không duy nhất giữa các tenant. Contract UserDetailsService.loadUserByUsername chỉ có một tham số username; đừng nối tenant do client khai vào query mà không kiểm tra quyền. Thiết kế identity key rõ ràng, ánh xạ tenant đã được xác minh và kiểm tra quyền trên từng resource.

### 12.2. User identity và business authorization

Có user tồn tại và password đúng chỉ là **authentication**. User đó có được sửa tiến độ bài học, xem đơn hàng hay thay cấu hình tổ chức hay không là **authorization**, cần dữ liệu ownership/role/permission riêng. Không nhét mọi chính sách vào query tìm user.

## 13. Tự kiểm tra kiến thức

**Câu 1.** JdbcDaoImpl và JdbcUserDetailsManager khác nhau gì?  
**Đáp:** JdbcDaoImpl dùng JDBC đọc UserDetails; JdbcUserDetailsManager mở rộng để quản lý user bằng UserDetailsManager.

**Câu 2.** UserDetailsService có nhiệm vụ kiểm tra raw password không?  
**Đáp:** Không. DaoAuthenticationProvider và PasswordEncoder kiểm tra credential.

**Câu 3.** Schema JDBC mặc định cần những cột chính nào?  
**Đáp:** users(username, password, enabled) và authorities(username, authority).

**Câu 4.** Vì sao cần lưu ROLE_ADMIN nếu SecurityFilterChain dùng hasRole("ADMIN")?  
**Đáp:** hasRole thường kiểm tra authority có prefix ROLE_.

**Câu 5.** Đổi profile từ jdbc sang domain có phải đổi SecurityFilterChain không?  
**Đáp:** Không, nếu cả hai nguồn cung cấp UserDetails/authorities nhất quán.

**Câu 6.** Nếu không có username, custom service nên trả null hay ném gì?  
**Đáp:** Ném UsernameNotFoundException theo UserDetailsService contract.

**Câu 7.** Nếu database outage, có nên ném UsernameNotFoundException để tránh lộ lỗi?  
**Đáp:** Không. Cần giữ lỗi vận hành đúng và ẩn chi tiết tại response boundary.

**Câu 8.** Tại sao không dùng SQL string concatenation để tìm username?  
**Đáp:** Có nguy cơ SQL injection; dùng query parameters.

**Câu 9.** Nếu app_users có locked_flag thì map sang đâu?  
**Đáp:** UserDetails.accountNonLocked thông qua accountLocked trong User builder.

**Câu 10.** Tại sao chỉ sửa hai SELECT của JdbcUserDetailsManager chưa đủ để CRUD bảng nghiệp vụ?  
**Đáp:** Các câu quản lý INSERT/UPDATE/DELETE/changePassword có SQL riêng.

**Câu 11.** Vì sao admin đã xác thực vẫn bị 403 ở /lesson?  
**Đáp:** ROLE_ADMIN không tự bao hàm ROLE_LEARNER trong demo.

**Câu 12.** Password hash có an toàn để trả cho frontend không?  
**Đáp:** Không. Hash vẫn là dữ liệu credential nhạy cảm.

**Câu 13.** Khi role bị thu hồi, session/JWT cũ có tự cập nhật không?  
**Đáp:** Không. Cần refresh, invalidation, revocation hoặc business re-check.

**Câu 14.** Tại sao cần unique index trên login_name?  
**Đáp:** Bảo đảm mỗi tên đăng nhập định danh một account theo policy và tránh kết quả lookup không xác định.

**Câu 15.** Một ứng dụng đã dùng JPA có bắt buộc quay lại JdbcTemplate để implement UserDetailsService không?  
**Đáp:** Không. Có thể dùng JPA repository, miễn là ánh xạ UserDetails chính xác và kiểm soát transaction/lazy load.

## 14. Tài liệu chính thức

- Spring Security — JDBC Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/jdbc.html
- Spring Security — Security Database Schema: https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — UserDetails: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — Username/Password Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Boot 3.3 — Database Initialization: https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html
