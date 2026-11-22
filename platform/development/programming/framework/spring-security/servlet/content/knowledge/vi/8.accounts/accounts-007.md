# Ánh xạ quyền từ dữ liệu nghiệp vụ sang GrantedAuthority trong Spring Security Servlet

**Phạm vi:** Java 17+, Spring Security 6.x và ứng dụng Spring Boot chạy trên Jakarta Servlet. Bài này thuộc nhóm **Tài khoản**. Trọng tâm là chuyển dữ liệu người dùng, vai trò và quyền của hệ thống nghiệp vụ thành các <code>GrantedAuthority</code> mà Spring Security hiểu được, sau đó kiểm thử authentication/authorization thực tế. Ví dụ đầy đủ dùng Spring Boot 3.3.5, Spring JDBC, H2, HTTP Basic và MockMvc.

Trong một sản phẩm thật, database có thể lưu người dùng thuộc nhóm “Kế toán”, “Quản trị”, “Người xem báo cáo”, hoặc quyền riêng như “Được xuất báo cáo”. Spring Security không tự suy ra ý nghĩa của những mã này. Ứng dụng phải xây dựng một bước **mapping tin cậy, nhất quán và có kiểm thử** trước khi Spring Security dùng dữ liệu để quyết định có cho request đi tiếp không.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Tài khoản nghiệp vụ** | Bản ghi account ID 42, username <code>analyst</code>, trạng thái ACTIVE | Danh tính và trạng thái tài khoản; có thể liên quan phòng ban, tổ chức, tenant |
| **Vai trò (business role)** | <code>ANALYST</code>, <code>ADMIN</code> | Nhóm trách nhiệm thường gán cho người dùng trong mô hình nghiệp vụ |
| **Quyền thao tác (permission)** | <code>report:read</code>, <code>report:export</code> | Năng lực cụ thể mà ứng dụng muốn cho phép hoặc từ chối |
| **GrantedAuthority** | <code>ROLE_ANALYST</code> hoặc <code>report:read</code> | Biểu diễn quyền đã được xác minh trong Spring Security để các rule so khớp |

<code>GrantedAuthority</code> là interface thuộc <code>org.springframework.security.core</code>; phương thức quan trọng của nó là <code>String getAuthority()</code>. <code>SimpleGrantedAuthority</code> là triển khai thông dụng, lưu một chuỗi authority. Khi authentication thành công, <code>Authentication.getAuthorities()</code> chứa danh sách authority được gắn vào danh tính đã xác thực.

**Vai trò nghiệp vụ không tự động là authority.** Hệ thống phải định nghĩa quy tắc chuyển mã vai trò, quyền nghiệp vụ và phạm vi áp dụng. Không nên lấy một trường tự khai trong JSON của request, ví dụ <code>{"role":"ADMIN"}</code>, để tự tạo <code>SimpleGrantedAuthority("ROLE_ADMIN")</code>. Giá trị cấp quyền phải đến từ nguồn đã được xác minh hoặc cơ chế xác thực được tin cậy.

### Vai trò và permission liên quan thế nào?

Giả sử nghiệp vụ có hai vai trò:

| Role trong database | Quyền trong database | GrantedAuthority tạo ra |
| --- | --- | --- |
| <code>ANALYST</code> | <code>report:read</code> | <code>ROLE_ANALYST</code>, <code>report:read</code> |
| <code>ADMIN</code> | <code>report:read</code>, <code>report:export</code> | <code>ROLE_ADMIN</code>, <code>report:read</code>, <code>report:export</code> |

Ví dụ trên **không có mặc định “ADMIN tự bao hàm mọi permission”**. Quyền của ADMIN được cấp rõ ràng qua quan hệ role–permission. Nếu muốn role hierarchy hay kế thừa quyền, phải cấu hình và kiểm thử riêng, không tự suy ra từ tên ADMIN.

## 2. Phân biệt hasRole và hasAuthority

Trong Spring Security, hai biểu thức thường gặp:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
.requestMatchers("/reports").hasAuthority("report:read")
~~~

Ở cấu hình mặc định, <code>hasRole("ADMIN")</code> tìm authority <code>ROLE_ADMIN</code>. Ngược lại, <code>hasAuthority("report:read")</code> so khớp đúng chuỗi <code>report:read</code>; nó **không tự thêm prefix**.

| Đang có authority | Kiểm tra | Kết quả |
| --- | --- | --- |
| <code>ROLE_ADMIN</code> | <code>hasRole("ADMIN")</code> | Đạt |
| <code>ADMIN</code> | <code>hasRole("ADMIN")</code> | Không đạt với prefix mặc định |
| <code>ROLE_ADMIN</code> | <code>hasAuthority("ROLE_ADMIN")</code> | Đạt |
| <code>report:export</code> | <code>hasAuthority("report:export")</code> | Đạt |
| <code>ROLE_ANALYST</code> | <code>hasAuthority("report:read")</code> | Không tự động đạt; cần mapping permission hoặc rule role riêng |

**Quy ước gợi ý:** mã role nghiệp vụ lưu trong database ở dạng <code>ADMIN</code>, <code>ANALYST</code>; khi mapping sang Spring Security thêm <code>ROLE_</code>. Mã permission dùng tên ổn định, ví dụ <code>report:read</code>, và giữ nguyên khi đưa vào <code>SimpleGrantedAuthority</code>. Không lẫn lộn hai namespace này.

Ví dụ tạo trực tiếp:

~~~java
GrantedAuthority role =
    new SimpleGrantedAuthority("ROLE_ADMIN");
GrantedAuthority permission =
    new SimpleGrantedAuthority("report:export");
~~~

Đoạn trên minh họa cú pháp trong một class có import <code>GrantedAuthority</code> và <code>SimpleGrantedAuthority</code>; nó chưa chứng minh người dùng thật có các quyền ấy. Bước chứng minh đến từ dữ liệu nghiệp vụ đáng tin, trạng thái account và các ràng buộc sở hữu tài nguyên.

## 3. Luồng chuyển đổi dữ liệu thành quyền trong ứng dụng Servlet

Với HTTP Basic hoặc form login dựa vào username/password và <code>DaoAuthenticationProvider</code>, luồng điển hình:

~~~text
HTTP request + username/password
    |
    v
Spring Security authentication filters
    |
    v
AuthenticationManager / DaoAuthenticationProvider
    |
    v
UserDetailsService.loadUserByUsername(username)
    |
    +-- Đọc account: password hash + trạng thái
    +-- Đọc các role đã được cấp
    +-- Đọc các permission tương ứng role
    +-- Kiểm tra mã quyền hợp lệ
    '-- Mapping -> Collection<GrantedAuthority>
    |
    v
Kiểm tra password / trạng thái account
    |
    v
Authentication đã xác thực + GrantedAuthority
    |
    v
SecurityContext -> AuthorizationFilter / method security
    |
    v
hasRole / hasAuthority / chính sách tài nguyên
~~~

<code>UserDetailsService</code> chỉ có nhiệm vụ nạp <code>UserDetails</code> từ tên người dùng; **nó không tự so sánh password**. Thành phần authentication thích hợp kiểm tra password hash qua <code>PasswordEncoder</code> và kiểm tra trạng thái tài khoản. <code>UserDetails.getAuthorities()</code> cung cấp authorities để Spring Security dùng ở bước phân quyền.

Trong ứng dụng lưu authentication trong session, dữ liệu authority thường được nạp lúc đăng nhập và có thể được giữ trong <code>SecurityContext</code> qua các request. Nếu vai trò trong database vừa thay đổi, authentication đang được giữ **không mặc nhiên cập nhật ngay**. Với HTTP Basic, credentials thường được xác thực lại theo request, nhưng cache và cách cấu hình authentication có thể ảnh hưởng thời điểm đọc lại. Chính sách thu hồi quyền cần được thiết kế rõ.

Đối với OAuth2/OIDC hoặc JWT resource server, Spring Security còn có đường đi khác: converter ánh xạ claims/scopes sang authority; <code>UserDetailsService</code> không phải lúc nào cũng được gọi. Phải xác định **nguồn quyền thực sự đang được dùng** trước khi sửa code mapping.

## 4. Mô hình database: account, role, permission

Ví dụ dữ liệu nghiệp vụ được chuẩn hóa thành năm bảng:

~~~text
app_account
  id, login_name, password_hash, status
       |
       | 1 - n
       v
app_account_role ------------> app_role
  account_id, role_code         role_code
                                       |
                                       | 1 - n
                                       v
                              app_role_permission
                              role_code, permission_code
                                       |
                                       v
                                 app_permission
                                 permission_code
~~~

Các quy tắc:
- <code>app_account.status</code> có thể ACTIVE hoặc DISABLED. Tài khoản DISABLED không được đăng nhập dù vẫn có role trong bảng.
- Một account có thể có nhiều role, một role có nhiều permission và permission có thể thuộc nhiều role.
- Primary key/foreign key ngăn một số lỗi trùng dữ liệu và tham chiếu role không tồn tại.
- Nguồn cấp role/permission phải được bảo vệ bằng workflow quản trị có phân quyền, audit, và chỉ cho phép các mã đã được phê duyệt.
- Với mô hình có tenant, association phải gắn tenant và kiểm tra ở từng tài nguyên; **không tự động nâng quyền của một tenant thành quyền toàn hệ thống**.

Ví dụ role ANALYST mang <code>report:read</code>. Role ADMIN mang cả <code>report:read</code> và <code>report:export</code>. Một account có cả hai role sẽ nhận tập authority hợp nhất, không tạo nhiều bản sao <code>report:read</code>.

## 5. Dự án Spring Boot chạy được

Cấu trúc:

~~~text
business-authorities/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/businessauth/
    │   │   ├── BusinessAuthApplication.java
    │   │   ├── BusinessSecurityConfiguration.java
    │   │   ├── BusinessUserDetailsService.java
    │   │   └── ReportController.java
    │   └── resources/
    │       └── schema.sql
    └── test/
        └── java/com/example/businessauth/
            └── BusinessAuthorityTest.java
~~~

Bài demo dùng H2 in-memory để chạy độc lập; H2 và tài khoản thử nghiệm **không đại diện cho cơ chế lưu trữ và quản lý mật khẩu production**. Trong dự án thật, thay H2 bằng nguồn dữ liệu đã được quản lý, dùng migration như Flyway/Liquibase, và nối với hệ thống identity của tổ chức.

### 5.1. pom.xml

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
  <artifactId>business-authorities</artifactId>
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
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
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

### 5.2. schema.sql

Tạo <code>src/main/resources/schema.sql</code>:

~~~sql
CREATE TABLE app_account (
    id BIGINT PRIMARY KEY,
    login_name VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE app_role (
    role_code VARCHAR(40) PRIMARY KEY
);

CREATE TABLE app_permission (
    permission_code VARCHAR(80) PRIMARY KEY
);

CREATE TABLE app_account_role (
    account_id BIGINT NOT NULL,
    role_code VARCHAR(40) NOT NULL,
    PRIMARY KEY (account_id, role_code),
    FOREIGN KEY (account_id) REFERENCES app_account(id),
    FOREIGN KEY (role_code) REFERENCES app_role(role_code)
);

CREATE TABLE app_role_permission (
    role_code VARCHAR(40) NOT NULL,
    permission_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (role_code, permission_code),
    FOREIGN KEY (role_code) REFERENCES app_role(role_code),
    FOREIGN KEY (permission_code) REFERENCES app_permission(permission_code)
);
~~~

Spring Boot với H2 embedded và SQL initialization mặc định sẽ thực thi <code>schema.sql</code> khi khởi tạo DataSource. Demo sẽ seed dữ liệu qua <code>ApplicationRunner</code> sau khi schema sẵn sàng. Nếu đổi sang PostgreSQL/MySQL trong dự án thật, cần cấu hình migration và thứ tự khởi tạo theo database đó thay vì dựa vào H2 demo.

### 5.3. Main class và dữ liệu mẫu

Tạo <code>src/main/java/com/example/businessauth/BusinessAuthApplication.java</code>:

~~~java
package com.example.businessauth;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class BusinessAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(BusinessAuthApplication.class, args);
    }

    @Bean
    ApplicationRunner seedData(JdbcTemplate db, PasswordEncoder encoder) {
        return args -> {
            db.update("INSERT INTO app_role(role_code) VALUES (?)", "ANALYST");
            db.update("INSERT INTO app_role(role_code) VALUES (?)", "ADMIN");

            db.update("INSERT INTO app_permission(permission_code) VALUES (?)",
                    "report:read");
            db.update("INSERT INTO app_permission(permission_code) VALUES (?)",
                    "report:export");

            db.update("INSERT INTO app_role_permission(role_code, permission_code) "
                    + "VALUES (?, ?)", "ANALYST", "report:read");
            db.update("INSERT INTO app_role_permission(role_code, permission_code) "
                    + "VALUES (?, ?)", "ADMIN", "report:read");
            db.update("INSERT INTO app_role_permission(role_code, permission_code) "
                    + "VALUES (?, ?)", "ADMIN", "report:export");

            db.update("INSERT INTO app_account(id, login_name, password_hash, status) "
                    + "VALUES (?, ?, ?, ?)", 1L, "analyst",
                    encoder.encode("analyst-pass"), "ACTIVE");
            db.update("INSERT INTO app_account(id, login_name, password_hash, status) "
                    + "VALUES (?, ?, ?, ?)", 2L, "admin",
                    encoder.encode("admin-pass"), "ACTIVE");
            db.update("INSERT INTO app_account(id, login_name, password_hash, status) "
                    + "VALUES (?, ?, ?, ?)", 3L, "suspended",
                    encoder.encode("suspended-pass"), "DISABLED");

            db.update("INSERT INTO app_account_role(account_id, role_code) "
                    + "VALUES (?, ?)", 1L, "ANALYST");
            db.update("INSERT INTO app_account_role(account_id, role_code) "
                    + "VALUES (?, ?)", 2L, "ADMIN");
            db.update("INSERT INTO app_account_role(account_id, role_code) "
                    + "VALUES (?, ?)", 3L, "ANALYST");
        };
    }
}
~~~

Demo tạo ba tài khoản: analyst, admin và suspended. Account suspended vẫn có role ANALYST để làm rõ rằng **có role không đồng nghĩa được phép xác thực**. Mật khẩu được mã hóa qua <code>PasswordEncoder</code> trước khi lưu, không lưu chuỗi rõ trong database. Những password cố định ở ví dụ chỉ là fixture dùng tại localhost.

### 5.4. Bước mapping chính: UserDetailsService

Tạo <code>src/main/java/com/example/businessauth/BusinessUserDetailsService.java</code>:

~~~java
package com.example.businessauth;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class BusinessUserDetailsService implements UserDetailsService {

    private static final Set<String> KNOWN_ROLES =
            Set.of("ANALYST", "ADMIN");
    private static final Set<String> KNOWN_PERMISSIONS =
            Set.of("report:read", "report:export");

    private final JdbcTemplate db;

    public BusinessUserDetailsService(JdbcTemplate db) {
        this.db = db;
    }

    private record Account(
            long id, String login, String passwordHash, String status) { }

    @Override
    public UserDetails loadUserByUsername(String username) {
        List<Account> matches = db.query(
            "SELECT id, login_name, password_hash, status "
                    + "FROM app_account WHERE login_name = ?",
            (rs, index) -> new Account(
                rs.getLong("id"),
                rs.getString("login_name"),
                rs.getString("password_hash"),
                rs.getString("status")),
            username
        );

        if (matches.isEmpty()) {
            throw new UsernameNotFoundException("Account not found");
        }
        Account account = matches.get(0);

        List<String> roles = db.queryForList(
            "SELECT role_code FROM app_account_role "
                    + "WHERE account_id = ? ORDER BY role_code",
            String.class, account.id()
        );

        List<String> permissions = db.queryForList(
            "SELECT DISTINCT rp.permission_code "
                    + "FROM app_account_role ar "
                    + "JOIN app_role_permission rp "
                    + "ON rp.role_code = ar.role_code "
                    + "WHERE ar.account_id = ? "
                    + "ORDER BY rp.permission_code",
            String.class, account.id()
        );

        Set<GrantedAuthority> unique = new LinkedHashSet<>();

        for (String roleCode : roles) {
            if (!KNOWN_ROLES.contains(roleCode)) {
                throw new IllegalStateException("Unknown business role");
            }
            unique.add(new SimpleGrantedAuthority("ROLE_" + roleCode));
        }

        for (String permissionCode : permissions) {
            if (!KNOWN_PERMISSIONS.contains(permissionCode)) {
                throw new IllegalStateException("Unknown business permission");
            }
            unique.add(new SimpleGrantedAuthority(permissionCode));
        }

        if (!Set.of("ACTIVE", "DISABLED").contains(account.status())) {
            throw new IllegalStateException("Unknown account status");
        }

        return User.withUsername(account.login())
            .password(account.passwordHash())
            .authorities(new ArrayList<>(unique))
            .disabled(!"ACTIVE".equals(account.status()))
            .build();
    }
}
~~~

**Tại sao code mapping như trên?**

1. Đọc account bằng câu SQL có tham số <code>?</code>; không nối <code>username</code> trực tiếp vào SQL.
2. Đọc các role mà account được cấp qua bảng quan hệ có foreign key, rồi lấy toàn bộ permission tương ứng role.
3. Kiểm tra mã role/permission theo tập mã đã được ứng dụng nhận diện; mã mới không được ngầm cấp đặc quyền chỉ vì xuất hiện trong dữ liệu.
4. Role được thêm prefix <code>ROLE_</code>; permission giữ nguyên <code>report:read</code>/<code>report:export</code>.
5. <code>LinkedHashSet</code> loại authority bị trùng nếu nhiều role cùng có một permission.
6. Tài khoản DISABLED trả <code>UserDetails</code> có <code>isEnabled() == false</code>; authentication provider sẽ không chấp nhận login dù password đúng.
7. <code>User.withUsername(...)</code> là cách dùng <code>UserDetails</code> chuẩn. Với hệ thống cần account ID hoặc tenant context ở principal, có thể tạo custom <code>UserDetails</code> và kiểm tra các thuộc tính đó trong chính sách ứng dụng.

Các tập <code>KNOWN_ROLES</code> và <code>KNOWN_PERMISSIONS</code> cố ý cố định trong demo để thể hiện **fail closed**: muốn thêm mã quyền mới phải cập nhật contract và test tương ứng. Trong hệ thống lớn có registry role/permission được quản trị và migration kiểm soát. Nếu dữ liệu chứa mã không biết, ví dụ ném lỗi thay vì âm thầm cấp quyền. Cần cảnh báo vận hành và xử lý migration đồng bộ để tránh gây lỗi đăng nhập không mong muốn; không biến “unknown role” thành “ADMIN”.

**Không nên chỉ chuyển tên phòng ban hoặc chức danh hiển thị thành authority** bằng cách nối prefix. “Kế toán”, “Phòng kinh doanh” có thể là label thay đổi; authority cần mã ổn định, có namespace và quy trình cấp quyền.

### 5.5. SecurityFilterChain và PasswordEncoder

Tạo <code>src/main/java/com/example/businessauth/BusinessSecurityConfiguration.java</code>:

~~~java
package com.example.businessauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BusinessSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/info")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/admin/panel")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/reports/export")
                    .hasAuthority("report:export")
                .requestMatchers(HttpMethod.GET, "/reports")
                    .hasAuthority("report:read")
                .anyRequest()
                    .denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình trên dùng chain mặc định bao phủ tất cả request, với <code>denyAll()</code> ở cuối. Những endpoint chưa được liệt kê không được mặc nhiên mở. HTTP Basic giúp dễ thực nghiệm mapping; ứng dụng thật có thể dùng form login, OIDC, token hoặc cơ chế xác thực khác.

<code>PasswordEncoderFactories.createDelegatingPasswordEncoder()</code> mặc định tạo hash có định danh thuật toán như <code>{bcrypt}</code> trong chuỗi lưu trữ. Khi đăng nhập, Spring Security dùng encoder phù hợp để đối chiếu mật khẩu. Không tự so sánh password string với database hash và không viết custom plaintext password encoder để sửa lỗi login.

**CSRF mặc định vẫn bật.** Ví dụ chỉ dùng các GET không làm thay đổi trạng thái, nên không cần tắt CSRF. Khi bổ sung POST/PUT/DELETE và cơ chế cookie/session, phải thiết kế token CSRF phù hợp; không liên hệ nhầm bài toán CSRF với quyền <code>GrantedAuthority</code>.

### 5.6. Controller để quan sát quyền

Tạo <code>src/main/java/com/example/businessauth/ReportController.java</code>:

~~~java
package com.example.businessauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/public/info")
    public String info() {
        return "public";
    }

    @GetMapping("/reports")
    public String reports() {
        return "report-list";
    }

    @GetMapping("/reports/export")
    public String exportReports() {
        return "report-export";
    }

    @GetMapping("/admin/panel")
    public String adminPanel() {
        return "admin-panel";
    }
}
~~~

Controller không cần tự đọc bảng user_roles để cấp quyền mỗi lần; rule Spring Security dùng authority của authentication. Tuy nhiên, nếu endpoint truy cập tài nguyên cụ thể theo <code>reportId</code> hoặc <code>tenantId</code>, quyền gọi route là điều kiện **cần nhưng chưa đủ**: còn phải kiểm tra account được xem/chỉnh tài nguyên nào, như sẽ phân tích ở phần 9.

## 6. Chạy ứng dụng và dự đoán kết quả

Trong thư mục chứa <code>pom.xml</code>:

~~~bash
mvn test
mvn spring-boot:run
~~~

H2 in-memory được tạo khi ứng dụng khởi động. <code>schema.sql</code> tạo bảng, <code>ApplicationRunner</code> thêm dữ liệu mẫu. Khi restart, database H2 trong bộ nhớ được khởi tạo lại.

Dùng curl:

~~~bash
# Công khai, không cần đăng nhập.
curl -i http://localhost:8080/public/info

# Không có credentials -> HTTP 401.
curl -i http://localhost:8080/reports

# Analyst có report:read -> HTTP 200.
curl -i -u analyst:analyst-pass http://localhost:8080/reports

# Analyst thiếu report:export -> HTTP 403.
curl -i -u analyst:analyst-pass http://localhost:8080/reports/export

# Admin có report:export -> HTTP 200.
curl -i -u admin:admin-pass http://localhost:8080/reports/export

# Admin có ROLE_ADMIN -> HTTP 200.
curl -i -u admin:admin-pass http://localhost:8080/admin/panel

# Analyst thiếu ROLE_ADMIN -> HTTP 403.
curl -i -u analyst:analyst-pass http://localhost:8080/admin/panel

# Account bị DISABLED dù password đúng -> HTTP 401.
curl -i -u suspended:suspended-pass http://localhost:8080/reports
~~~

Bảng mong đợi:

| Người gọi | GET /reports | GET /reports/export | GET /admin/panel |
| --- | --- | --- | --- |
| Anonymous | 401 | 401 | 401 |
| analyst / analyst-pass | 200 | 403 | 403 |
| admin / admin-pass | 200 | 200 | 200 |
| suspended / suspended-pass | 401 | 401 | 401 |

Kết quả phụ thuộc chính xác vào code demo vừa tạo, chưa xét custom exception handler, gateway, session hoặc filter khác. Chuỗi status là kết quả **dự kiến khi chạy**, không phải log từ một lần chạy đã thực hiện.

Nếu kiểm tra chỉ một tài khoản ADMIN, bạn có thể không phát hiện bug cấp quyền cho ANALYST. Phải test cả quyền có và không có, account vô hiệu hóa và những URL mới chưa khai báo.

## 7. Kiểm thử mapping và behavior bằng MockMvc

Tạo <code>src/test/java/com/example/businessauth/BusinessAuthorityTest.java</code>:

~~~java
package com.example.businessauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BusinessAuthorityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    UserDetailsService users;

    @Test
    void businessRolesAndPermissionsBecomeAuthorities() {
        UserDetails analyst = users.loadUserByUsername("analyst");
        UserDetails admin = users.loadUserByUsername("admin");

        assertThat(analyst.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder("ROLE_ANALYST", "report:read");

        assertThat(admin.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder(
                "ROLE_ADMIN", "report:read", "report:export");
    }

    @Test
    void analystCanReadButCannotExport() throws Exception {
        mvc.perform(get("/reports")
                .with(httpBasic("analyst", "analyst-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-list"));

        mvc.perform(get("/reports/export")
                .with(httpBasic("analyst", "analyst-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminHasBothPermissionAndRole() throws Exception {
        mvc.perform(get("/reports/export")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-export"));

        mvc.perform(get("/admin/panel")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-panel"));
    }

    @Test
    void missingCredentialsAndDisabledAccountAreRejected() throws Exception {
        mvc.perform(get("/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/reports")
                .with(httpBasic("suspended", "suspended-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unlistedRouteIsDeniedForAuthenticatedUser() throws Exception {
        mvc.perform(get("/new-admin-feature")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

Bộ kiểm thử xác nhận hai khía cạnh **riêng biệt**:
- **Mapping:** account/role/permission thực tế tạo đúng tập authority trong <code>UserDetails</code>.
- **Behavior:** khi request đi qua security filter chain, chỉ account có quyền phù hợp được truy cập endpoint.

Không nên chỉ assert rằng service trả về <code>ROLE_ADMIN</code> rồi xem như đã test toàn bộ authorization: matcher URL, HTTP method, SecurityFilterChain và dữ liệu tài nguyên đều có thể gây lỗi khác. Test thêm endpoint thật qua MockMvc hoặc HTTP integration.

Test account không tồn tại cũng hữu ích: <code>loadUserByUsername</code> phải từ chối thay vì trả tài khoản mặc định với role được cấp. Với quyền mới, cập nhật test mapping và test HTTP tương ứng ngay trong PR bổ sung quyền.

## 8. Khi nào cấp role, khi nào cấp permission?

Cấp role như <code>ROLE_ADMIN</code> hữu ích cho chính sách cấp cao, ví dụ quyền vào khu vực quản trị. Cấp permission như <code>report:export</code> hữu ích để diễn đạt một hành động nghiệp vụ độc lập với tên vai trò.

Giả sử ngày mai có vai trò <code>SUPERVISOR</code> được quyền xem và xuất báo cáo nhưng không quản trị người dùng. Nếu controller chỉ kiểm tra <code>hasRole("ADMIN")</code> cho xuất báo cáo, bạn sẽ phải sửa code authorization mỗi khi xuất hiện vai trò mới. Nếu controller dùng <code>hasAuthority("report:export")</code>, hệ thống chỉ cần cấp permission đó cho role SUPERVISOR thông qua quy trình quản trị được kiểm soát, đồng thời thêm test.

Mặt khác, không nên tạo hàng trăm chuỗi permission tùy ý theo tên màn hình. Thiết kế mã permission theo hành động ổn định và đối tượng nghiệp vụ rõ ràng, ví dụ:

| Mã | Ý nghĩa |
| --- | --- |
| <code>report:read</code> | Được xem báo cáo thuộc phạm vi cho phép |
| <code>report:export</code> | Được xuất báo cáo thuộc phạm vi cho phép |
| <code>invoice:approve</code> | Được phê duyệt hóa đơn sau khi qua điều kiện nghiệp vụ |
| <code>user:manage</code> | Được thao tác quản lý người dùng trong phạm vi được cấp |

Authority trong <code>Authentication</code> biểu thị **quyền loại hành động**, không tự cấp quyền với mọi bản ghi. Ví dụ <code>report:read</code> chỉ là điều kiện cho phép gọi chức năng xem báo cáo; ứng dụng vẫn phải kiểm tra người dùng có quyền xem báo cáo cụ thể hay không.

### Rule ở cấp HTTP và method

Với một quyền đã mapping, có thể kiểm tra ở lớp web:

~~~java
.requestMatchers(HttpMethod.GET, "/reports")
.hasAuthority("report:read")
~~~

Hoặc ở tầng service qua method security:

~~~java
@PreAuthorize("hasAuthority('report:export')")
public byte[] exportReport(long reportId) {
    return reportService.export(reportId);
}
~~~

Đoạn method security trên là **minh họa**, chưa là class Java độc lập: cần bật <code>@EnableMethodSecurity</code>, có bean service phù hợp và áp dụng kiểm tra quyền trên bản ghi bên trong nghiệp vụ. Method security đặc biệt hữu ích nếu service được gọi qua nhiều endpoint/cơ chế, nhưng không nên tưởng một proxy method đã xử lý toàn bộ truy cập nội bộ (ví dụ self-invocation không đi qua proxy theo cơ chế thông thường).

## 9. Trường hợp multi-tenant: không nâng quyền có phạm vi thành quyền toàn cục

Giả sử account <code>mai</code> có vai trò <code>ADMIN</code> **chỉ trong tenant A**. Nếu mapping ngây thơ:

~~~java
new SimpleGrantedAuthority("ROLE_ADMIN");
~~~

rồi dùng <code>hasRole("ADMIN")</code> cho mọi URL tenant, bạn có thể vô tình cho Mai dùng quyền quản trị trên tenant B. Dữ liệu nghiệp vụ thực tế thường có chiều không gian:

~~~text
account_id | tenant_id | role_code
-----------+-----------+----------
42         | A         | ADMIN
42         | B         | VIEWER
~~~

Một trong những cách thiết kế rõ ràng là tách:

1. **Authority tổng quát:** account có năng lực thuộc nhóm chức năng nào trong ứng dụng, không hàm ý quyền với mọi tenant.
2. **Authorization theo đối tượng:** với mỗi <code>tenantId</code>/<code>reportId</code>, kiểm tra membership, role trong tenant, ownership và trạng thái của bản ghi bằng nguồn dữ liệu có thẩm quyền tại thời điểm cần thiết.

Ví dụ check cần thực hiện về mặt nghiệp vụ:

~~~text
User 42 gọi GET /tenants/B/reports/900
    -> request đã xác thực?
    -> report 900 thực thuộc tenant B?
    -> user 42 có membership hiệu lực trong tenant B?
    -> role trong tenant B có report:read?
    -> resource 900 có thêm ràng buộc owner/trạng thái?
    -> chỉ khi mọi điều kiện đều đạt mới cho phép
~~~

Không tin trực tiếp vào tenant ID trong URL, header hay claim do người dùng tự đặt để xác định quyền. Đặc biệt, không chỉ dựa vào <code>hasAuthority("TENANT_A_ADMIN")</code> mà quên kiểm tra tenant trong tài nguyên được lấy từ database. Một hệ thống có thể dùng authority có namespace tenant, hoặc một authorization service chuyên biệt; điểm cốt lõi là **quyền và phạm vi phải được liên kết rõ và kiểm tra trên đối tượng thực**.

### Một quy tắc tổng quát

**RBAC** (role-based access control) phù hợp để xác định nhóm hành động; **ABAC** hoặc kiểm tra thuộc tính đối tượng/người gọi phù hợp cho điều kiện như tenant, owner, trạng thái chứng từ, hạn mức phê duyệt, quan hệ phòng ban. Hai cơ chế có thể dùng chung; <code>GrantedAuthority</code> không thay cho mọi kiểm tra nghiệp vụ.

## 10. Kiểm soát vòng đời quyền và cập nhật tại runtime

Dữ liệu role/permission thay đổi theo thời gian: nhân sự chuyển bộ phận, bị thu hồi quyền, account bị khóa hoặc tổ chức thay đổi chính sách. Cần trả lời chính xác ba câu hỏi:

**Khi nào load quyền?** Trong mẫu HTTP Basic, account/authority được nạp khi authentication diễn ra theo request (có thể chịu ảnh hưởng của cache/configuration). Với form login, <code>SecurityContext</code> có thể được giữ trong HttpSession; với JWT, authorities có thể xuất phát từ claims được phát hành trước đó.

**Khi nào quyền thay đổi có hiệu lực?** Không mặc nhiên ở request tiếp theo trong mọi mô hình. Session còn sống có thể giữ snapshot cũ; JWT có thể còn hiệu lực đến lúc hết hạn; cache có TTL riêng. Những quyền nhạy cảm cần cơ chế thu hồi hoặc kiểm tra quyền hiện thời ở server.

**Ai được chỉnh quyền?** Chỉ nghiệp vụ quản trị đã xác thực, được phân quyền, có audit trail và kiểm soát thay đổi. Việc ghi vào <code>app_account_role</code> và <code>app_role_permission</code> là thao tác cấp quyền cao; không để endpoint tự phục vụ thay đổi role từ payload người dùng.

| Cơ chế authentication | Nguồn authority thường gặp | Cần xem xét khi thu hồi quyền |
| --- | --- | --- |
| HTTP Basic + UserDetailsService | Account/role/permission tải khi authenticate | Cache user, chi phí DB và thời điểm nạp lại |
| Form login + HttpSession | Authorities được lưu trong authentication/session | Session hiện hành, re-authentication, invalidate/refresh |
| JWT resource server | Claims được xác minh rồi chuyển thành authority | Token lifetime, refresh, revoke/introspection nếu áp dụng |
| Opaque token introspection | Thông tin server introspection cung cấp | Cache/introspection freshness và revoke |
| Authentication custom | Converter/provider do dự án thiết kế | Cần test rõ nguồn, tính mới và ngữ cảnh tenant |

Không cập nhật authorities của một session bằng cách chỉnh thẳng database rồi giả định Spring Security sẽ tự đồng bộ. Cần một chiến lược hiệu lực, thu hồi và caching đã được kiểm thử.

## 11. Mapping trong OAuth2/JWT khác UserDetailsService

Khi ứng dụng Spring Security là OAuth2 resource server, token có thể chứa scope như <code>reports.read</code>. Spring Security thường chuyển scope thành chuỗi authority có prefix <code>SCOPE_</code>, ví dụ <code>SCOPE_reports.read</code> theo converter mặc định. Điều này **khác** việc database của bài tạo <code>report:read</code> và <code>ROLE_ANALYST</code>.

Nếu chính sách authorization đang dùng:

~~~java
.hasAuthority("report:read")
~~~

thì authority <code>SCOPE_reports.read</code> không tự khớp. Phải chọn convention phù hợp cho cả nguồn quyền và cấu hình rule, hoặc viết converter đáng tin để chuẩn hóa. Với JWT, không được tin một claim chỉ vì đọc được JSON; trước tiên phải xác minh issuer, audience, chữ ký, thời hạn và điều kiện token theo cấu hình xác thực của hệ thống.

Cũng không nên lấy tùy ý một trường <code>roles</code> từ request body hoặc header rồi truyền trực tiếp vào <code>Authentication</code>. Phân biệt rõ dữ liệu client tự khai với claim đã qua xác minh và quyền từ kho nghiệp vụ do server quản lý.

## 12. Tính nhất quán, hiệu năng và an toàn của mapper

Một mapper vận hành tốt cần đáp ứng:

- **Mã ổn định:** role/permission dùng enum hoặc registry có quản trị; có tài liệu ý nghĩa và migration khi đổi tên.
- **Fail closed:** account không tồn tại, disabled, role/permission không hợp lệ không được mặc nhiên cấp quyền. Phân biệt lỗi dữ liệu (cần cảnh báo) với không đủ quyền (quy tắc nghiệp vụ).
- **Loại trùng:** một permission do nhiều role cấp không xuất hiện dư thừa nhiều lần; dùng <code>Set</code> khi tạo authority.
- **Nguồn đáng tin:** authority được sinh từ dữ liệu do server/identity provider xác minh, không phải trường client tự điền.
- **Ràng buộc transaction:** nếu thay đổi role và permission cần nhất quán, đặt quy trình cập nhật dữ liệu trong transaction; cân nhắc snapshot hoặc transaction phù hợp khi đọc nhiều bảng ở tải cao.
- **Hiệu năng:** tránh N+1 query cho mỗi role; truy vấn join lấy quyền trong một lần như ví dụ, thêm index theo account/role và cache có chính sách thu hồi nếu cần.
- **Không rò dữ liệu:** không log password hash, session ID, access token hoặc danh sách quyền nhạy cảm vào nơi công khai.
- **Least privilege:** không cấp tất cả quyền khi thiếu mã quyền hoặc lỗi kết nối DB; không dùng <code>permitAll</code> để “chữa lỗi” mapper.
- **Kiểm thử biên:** role không biết, account disabled, không có role, nhiều role chung permission, sai tenant, revoked permission và đường dẫn chưa khai báo.

Ví dụ minh họa xử lý một tài khoản có nhiều role:

~~~text
account roles = [ANALYST, ADMIN]
role permissions:
    ANALYST -> report:read
    ADMIN   -> report:read, report:export

Unique GrantedAuthority:
    ROLE_ANALYST
    ROLE_ADMIN
    report:read
    report:export
~~~

Không có ý nghĩa “ROLE_ADMIN mạnh hơn ROLE_ANALYST” trong <code>SimpleGrantedAuthority</code> chỉ vì tên. Đó chỉ là các chuỗi; việc suy ra vai trò kế thừa hoặc logic “được phép nếu có một trong các authority” do policy hoặc role hierarchy có chủ đích quy định.

## 13. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng/lỗi | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| User có mã ADMIN nhưng <code>hasRole("ADMIN")</code> trả 403 | Mapper tạo <code>ADMIN</code> thay vì <code>ROLE_ADMIN</code> | Kiểm tra chính xác <code>Authentication.getAuthorities()</code> và prefix |
| Account có quyền report nhưng <code>hasAuthority("report:read")</code> từ chối | Mã permission không khớp hoặc thiếu join | Kiểm tra bảng role–permission và dữ liệu UserDetails |
| User vừa bị khóa vẫn dùng được phiên cũ | Session/token/cache còn giữ authentication cũ | Kiểm tra chiến lược revoke/invalidate, TTL |
| Người quản trị tenant A xem được tenant B | Đã flatten tenant role thành quyền toàn cục | Ràng buộc membership và ownership theo tài nguyên |
| Nhiều role tạo permission lặp | Dữ liệu join trả nhiều bản ghi | Dùng SELECT DISTINCT hoặc Set |
| Role mới không hoạt động | Registry/mapper chưa nhận mã mới | Migration, rollout code và test quyền mới |
| Lỗi dữ liệu DB lại cấp quyền mặc định | Mapper fallback quá rộng | Fail closed và cảnh báo lỗi dữ liệu |
| Mọi route trở thành 200 sau khi debug | Vô tình đổi thành permitAll | Kiểm tra SecurityFilterChain và integration tests |
| HTTP 401 thay vì 403 | Credentials không xác thực được hoặc account bị disabled | Phân biệt authentication thất bại với thiếu authority |
| Admin thấy 403 dù đã có authority | Rule URL/method hoặc filter chain khác dự kiến | Test request thật và xem chain được chọn |
| Test mapper đạt nhưng API vẫn lộ | Chỉ test UserDetails, chưa test HTTP behavior | Thêm MockMvc test với anonymous/role sai/đường dẫn khác |

**Phân biệt 401 và 403:** HTTP Basic thường trả 401 khi chưa xác thực hoặc credentials không hợp lệ; user đã xác thực nhưng thiếu authority thường trả 403. Tuy nhiên security entry point, exception handler và cơ chế CSRF có thể thay đổi kết quả; cần kiểm thử ứng dụng thật, không suy diễn tuyệt đối từ status.

## 14. Checklist khi đưa ánh xạ quyền vào ứng dụng thật

1. Xác định business role, permission và cách biểu diễn phạm vi (tenant, đơn vị, tài nguyên) trong schema.
2. Ràng buộc dữ liệu bằng khóa ngoại/unique constraint; quản trị các mã permission được chấp nhận và audit hoạt động cấp quyền.
3. Nạp user/account status/password hash từ nguồn xác thực phù hợp; xác minh trạng thái và credentials qua authentication provider.
4. Mapping role thành <code>ROLE_...</code> nếu dùng <code>hasRole</code>, mapping permission thành mã chính xác cho <code>hasAuthority</code>. Không lấy authority từ input client không đáng tin.
5. Loại trùng và từ chối mã lạ; không tự suy quyền toàn cục từ quyền có phạm vi.
6. Xác định freshness và revocation cho session, cache và token; đặc biệt khi thay đổi quyền quan trọng.
7. Đặt rule phân quyền ở URL hoặc service theo nhu cầu; kiểm tra thêm ownership/tenant trong nghiệp vụ.
8. Test mapping trực tiếp, test request có/không có authority, account disabled, multiple roles, tenant khác, quyền bị thu hồi và route mới.
9. Quan sát log an toàn khi cần debug: có thể log tên authority ở môi trường phát triển được kiểm soát, không log password, token hoặc thông tin tài khoản nhạy cảm.
10. Xác nhận policy và bề mặt endpoint trong môi trường triển khai thật; một unit test của mapper không thể thay thế integration test của Spring SecurityFilterChain.

## 15. Câu hỏi tự kiểm tra

**Câu 1:** Database lưu role <code>ADMIN</code>, code tạo <code>SimpleGrantedAuthority("ADMIN")</code>, nhưng URL dùng <code>hasRole("ADMIN")</code>. Vì sao bị 403?  
**Trả lời:** Với prefix mặc định, <code>hasRole("ADMIN")</code> tìm <code>ROLE_ADMIN</code>. Cần mapping role thành đúng authority hoặc thiết kế lại rule một cách nhất quán.

**Câu 2:** User có hai role cùng cấp <code>report:read</code>. Có cần hai GrantedAuthority <code>report:read</code> không?  
**Trả lời:** Không. Một authority duy nhất là đủ; dùng Set để loại trùng, tránh tạo dữ liệu thừa.

**Câu 3:** Account DISABLED vẫn có role ADMIN trong database. Spring Security nên cho đăng nhập không?  
**Trả lời:** Không. UserDetails phải phản ánh trạng thái bị vô hiệu hóa và authentication provider cần từ chối login.

**Câu 4:** User có <code>report:read</code>, có được xem mọi báo cáo của mọi tenant không?  
**Trả lời:** Không mặc nhiên. Authority chỉ là một điều kiện; còn phải kiểm tra tenant membership và quyền đối với từng báo cáo.

**Câu 5:** Sau khi xóa role ADMIN trong database, mọi session/JWT đang tồn tại có lập tức mất authority cũ không?  
**Trả lời:** Không có bảo đảm như vậy. Cần cơ chế cập nhật, invalidate hoặc kiểm tra quyền hiện hành tùy hệ thống và thời gian sống của session/token/cache.

**Ghi nhớ:** <code>GrantedAuthority</code> là **định dạng quyền mà Spring Security tiêu thụ**, không phải nguồn quyết định nghiệp vụ ban đầu. Hãy thiết kế mapping có nguồn tin cậy, quy ước mã ổn định, kiểm soát trạng thái account và phạm vi tenant; sau đó xác minh bằng cả test UserDetails lẫn HTTP/method authorization.
