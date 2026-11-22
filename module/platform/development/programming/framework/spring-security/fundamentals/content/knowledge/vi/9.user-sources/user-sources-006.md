# Ánh xạ vai trò, quyền và trạng thái từ cơ sở dữ liệu

Giả sử ứng dụng có hai tài khoản trong database: `mai` và `admin`. Mai thuộc vai trò `STAFF`, được đọc tài liệu nhưng không được chỉnh sửa. Admin có vai trò `ADMIN`, được đọc, sửa tài liệu và mở khu vực quản trị. Cơ sở dữ liệu còn ghi Mai đang hoạt động, một đồng nghiệp bị vô hiệu hóa và một tài khoản khác bị khóa đến ngày hôm sau.

Khi người dùng đăng nhập, Spring Security cần biết **mật khẩu được lưu dưới dạng hash nào, tài khoản còn được dùng không, đang có vai trò nào và những quyền cụ thể nào**. Nếu ứng dụng chỉ trả username/password từ repository và bỏ qua các bảng role, permission hoặc trạng thái, việc xác thực có thể thành công nhưng phân quyền sai, hoặc tài khoản bị khóa vẫn đăng nhập được.

Chủ đề này giải thích cách đưa dữ liệu quan hệ thành `UserDetails` và `GrantedAuthority` cho Spring Security: **vai trò (role)**, **quyền (permission/authority)**, **trạng thái tài khoản (enabled/locked/expired)**, cùng các vấn đề khó hơn như đa tenant, quyền bị thu hồi, truy vấn đồng thời, cache và kiểm thử.

Ví dụ chính là một ứng dụng **Java 17+**, **Spring Boot 4.1.2**, **Spring Security do Boot BOM quản lý**, **Spring JDBC + H2 in-memory**. Ví dụ minh họa bằng database thật và HTTP Basic, không đòi hỏi PostgreSQL/MySQL bên ngoài. Các mật khẩu trong bài là dữ liệu giả chỉ dành cho chạy local.

## 1. Từ bảng dữ liệu đến đối tượng xác thực

Ba lớp trách nhiệm chính:

| Lớp | Dữ liệu nó quản lý | Câu hỏi mà nó trả lời |
| --- | --- | --- |
| **Repository/Database** | Account, password hash, role, permission, quan hệ gán và trạng thái hiện tại | Dữ liệu nghiệp vụ **hiện đang được lưu** là gì? |
| **`UserDetailsService` và `UserDetails`** | Biểu diễn user phục vụ xác thực, gồm tên, password hash, cờ trạng thái và authorities | Spring Security cần dữ liệu gì để **kiểm tra login**? |
| **`Authentication` và authorization** | Principal, authorities đã nhận từ provider và chính sách cho request/resource | Chủ thể đã được xác minh có **được làm thao tác này** không? |

Luồng thường gặp với username/password:

~~~text
HTTP Basic / form login
        |
        v
UsernamePasswordAuthenticationToken (chưa authenticated)
        |
        v
AuthenticationManager / DaoAuthenticationProvider
        |
        +--> UserDetailsService.loadUserByUsername(username)
                    |
                    v
              Database (app_accounts)
                    |
               +----+------------------------------+
               |                                   |
       password hash + flags               roles -> permissions
               |                                   |
               +----------> UserDetails <----------+
                                |
                                v
           isEnabled / isAccountNonLocked / expiry checks
                       + PasswordEncoder.matches
                                |
                     +----------+----------+
                     |                     |
                    FAIL                  SUCCESS
                     |                     |
          AuthenticationException         v
                                Authentication có authorities
                                             |
                                             v
                                HttpSecurity authorizeHttpRequests
                                             |
                                             v
                                 Controller + domain authorization
~~~

**`UserDetailsService` không tự xác minh mật khẩu**. Phương thức `loadUserByUsername` chỉ tải dữ liệu đáng tin từ nguồn được cấu hình; `DaoAuthenticationProvider` dùng `PasswordEncoder` so sánh raw password do người dùng gửi với hash lưu trong `UserDetails`. Sau đó Spring Security kiểm tra quyền dựa trên authorities được cung cấp, tùy policy.

## 2. Phân biệt role, permission, authority và trạng thái

Trong nhiều dự án, bốn thuật ngữ bị trộn lẫn:

| Khái niệm | Ví dụ ở database | Biểu diễn khi đưa vào Spring Security | Dùng cho |
| --- | --- | --- | --- |
| Role | `STAFF`, `ADMIN` | `ROLE_STAFF`, `ROLE_ADMIN` | Nhóm quyền lớn, vai trò tổ chức |
| Permission | `DOC_READ`, `DOC_WRITE`, `USER_MANAGE` | `DOC_READ`, `DOC_WRITE`, `USER_MANAGE` | Quyền trên một loại hành động/chức năng |
| `GrantedAuthority` | Được tạo từ role hoặc permission | `new SimpleGrantedAuthority("DOC_READ")` | Kiểu dữ liệu mà bộ phân quyền Spring Security tiêu thụ |
| Account status | `enabled`, `locked_until`, `account_expires_at` | Bốn cờ trong `UserDetails` | Cấm hoặc cho phép **xác thực mới** theo trạng thái |

**Role và permission đều có thể trở thành `GrantedAuthority`.** Với cách cấu hình mặc định, `hasRole("ADMIN")` tìm authority `ROLE_ADMIN`, còn `hasAuthority("DOC_WRITE")` tìm **đúng chuỗi** `DOC_WRITE`. Spring Security không tự nhìn bảng `roles` hay `permissions`; nó chỉ thấy authorities mà ứng dụng đã ánh xạ hoặc `AuthenticationProvider` tạo ra.

Ví dụ:

~~~text
Database:
  account mai -> role STAFF
  role STAFF -> permission DOC_READ

UserDetails.getAuthorities() cho Mai:
  ROLE_STAFF
  DOC_READ

Kiểm tra:
  hasRole("STAFF")          -> true
  hasRole("ADMIN")          -> false
  hasAuthority("DOC_READ")  -> true
  hasAuthority("DOC_WRITE") -> false
~~~

Đây là mô hình **RBAC có role-permission mapping**. Không có quy tắc bắt buộc mọi hệ thống phải lưu roles và permissions trong hai bảng; hệ thống nhỏ có thể lưu authorities trực tiếp. Việc tách bảng hữu ích khi một role được gán cho nhiều người và một permission được chia sẻ giữa nhiều role.

### Prefix ROLE_ có ý nghĩa thế nào?

Cách gán bằng builder:

~~~java
User.withUsername("mai")
    .password(encodedPassword)
    .roles("STAFF")
    .build();
~~~

Cách viết `.roles("STAFF")` tạo authority `ROLE_STAFF`. Không truyền `"ROLE_STAFF"` vào `.roles(...)`, vì builder tự thêm tiền tố và không cho phép giá trị đã bắt đầu bằng `ROLE_`.

Nhưng khi lấy dữ liệu từ bảng `roles`, bạn có thể tự thêm tiền tố:

~~~java
String roleCodeFromDatabase = "ADMIN";
GrantedAuthority authority =
        new SimpleGrantedAuthority("ROLE_" + roleCodeFromDatabase);
~~~

Sau đó rule `hasRole("ADMIN")` có thể khớp. Nếu database đã lưu nguyên chuỗi `ROLE_ADMIN`, **không** thêm tiền tố lần nữa; nên chọn một quy ước ổn định ngay từ schema và migration.

**Điểm dễ nhầm:** gọi cả `.roles("STAFF")` và sau đó `.authorities("DOC_READ")` trên cùng builder có thể khiến lời gọi sau **thay thế** danh sách authorities, chứ không tự động hợp nhất hai tập. Cách minh bạch là **tổng hợp role và permission trước thành một collection**, rồi gọi `.authorities(allAuthorities)` một lần.

## 3. Thiết kế schema quan hệ tối thiểu

Để minh họa toàn bộ chủ đề, ta dùng năm bảng:

~~~text
app_accounts
  account_id (PK)
  username (UNIQUE)
  password_hash
  enabled
  locked_until_ms
  account_expires_ms
  credentials_expires_ms
        |
        | 1:N
        v
account_roles (account_id, role_code)
        |
        | N:1
        v
roles (role_code PK)
        |
        | 1:N
        v
role_permissions (role_code, permission_code)
        |
        | N:1
        v
permissions (permission_code PK)
~~~

**Chức năng của từng bảng:**

- `app_accounts`: nguồn user và credential hash cho username/password login; định danh nội bộ ổn định là `account_id`.
- `roles`: danh mục role do quản trị viên/hệ thống kiểm soát; ví dụ `STAFF` hoặc `ADMIN`.
- `permissions`: danh mục hành động; ví dụ `DOC_READ`, `DOC_WRITE`.
- `account_roles`: gán các role cho account, nhiều-nhiều.
- `role_permissions`: gán các quyền cụ thể cho role, nhiều-nhiều.

**Ràng buộc quan trọng:** dùng foreign keys, uniqueness và primary keys để hạn chế bản ghi mồ côi hoặc gán trùng. Role và permission không được lấy từ dữ liệu tự khai của client; chỉ quy trình quản trị có phân quyền mới có thể thay đổi bảng này.

Không lưu raw password trong `password_hash`. Hệ thống phải dùng một `PasswordEncoder` được cấu hình tương thích với định dạng hash và có chính sách nâng cấp độ khó khi cần. Ví dụ dùng bcrypt.

### Trạng thái và thời gian

Ví dụ giữ thời điểm ở các cột `*_ms` dạng epoch milliseconds chỉ để SQL demo đơn giản và tránh lệ thuộc cú pháp timestamp của DB. Với PostgreSQL/MySQL thật, có thể dùng `TIMESTAMP WITH TIME ZONE` hoặc kiểu phù hợp cùng quy ước UTC rõ ràng.

| Cột | Ví dụ | Quy tắc ánh xạ |
| --- | --- | --- |
| `enabled` | `true` | `isEnabled()` lấy trực tiếp từ dữ liệu đáng tin |
| `locked_until_ms` | Thời điểm tương lai | Nếu `now < locked_until`, account đang bị khóa |
| `account_expires_ms` | Thời điểm quá khứ | Nếu `now >= expiresAt`, account đã hết hạn |
| `credentials_expires_ms` | Thời điểm quá khứ | Nếu `now >= credentialsExpiresAt`, credential đã hết hạn |
| Giá trị thời gian `NULL` | Không đặt hạn | Không áp điều kiện hết hạn tương ứng |

Lựa chọn “đúng tại thời điểm hết hạn thì không còn hiệu lực” cần được thống nhất giữa ứng dụng, DB và test. Trong kiến trúc nhiều node, nên dùng đồng hồ/UTC đáng tin cậy, kiểm soát lệch thời gian, và không tự lấy timestamp do browser gửi để quyết định trạng thái.

## 4. Một policy hoàn chỉnh cần cả trạng thái lẫn quyền

Giả sử tài khoản Mai có `ROLE_STAFF` và `DOC_READ`, nhưng `enabled=false` vì đã nghỉ việc. Không thể nói “Mai có `DOC_READ`, vậy được đọc tài liệu” rồi bỏ qua trạng thái.

Với login mới, `DaoAuthenticationProvider` kiểm tra các cờ trạng thái của `UserDetails` cùng password. Một account bị vô hiệu hoặc khóa thường **không hoàn tất xác thực**, dù mật khẩu đúng và có authorities.

Một cách phân biệt:

~~~text
Authentication:
  Đúng mật khẩu?
  Tài khoản enabled/non-locked/non-expired?
  Credentials chưa hết hạn?
       |
       +--> thất bại -> không cấp Authentication tin cậy

Authorization:
  Đã có Authentication hợp lệ?
  Có authority phù hợp?
  Có được phép với bản ghi/tenant cụ thể?
       |
       +--> thất bại -> từ chối thao tác
~~~

**Xác thực (authentication) khác phân quyền (authorization)**. Một tài khoản active có thể vẫn thiếu `DOC_WRITE` và nhận 403 khi sửa tài liệu. Một tài khoản disabled có thể nhận 401 ngay từ HTTP Basic login. Hai mã này xuất phát từ hai lớp quyết định khác nhau.

### Không nhầm account expired với subscription expired

Nếu gói dịch vụ của công ty hết hạn, có khi bạn vẫn muốn cho người dùng đăng nhập để thanh toán gia hạn hoặc xuất dữ liệu. Không nên tự đổi `subscription_expires_at` thành `UserDetails.isAccountNonExpired=false` nếu chỉ cần chặn chức năng của một gói. Tương tự, hết membership ở tenant A không có nghĩa người dùng phải mất khả năng đăng nhập vào tenant B.

Trạng thái `UserDetails` phù hợp với quyết định cho phép **xác thực danh tính**. Quyền theo gói, tổ chức hoặc tài nguyên riêng phải được kiểm tra ở lớp authorization nghiệp vụ.

## 5. Dự án thực hành: Java 17 + Spring Boot 4.1.2 + H2 + JDBC

Đây là một ứng dụng Servlet/HTTP Basic có thể học và chạy trên máy local. Mục đích là xác minh **cách nạp account, role, permission và trạng thái từ database**, không xây dựng hệ thống người dùng production.

Các thành phần của project:

~~~text
db-security-lab/
  pom.xml
  src/main/resources/
    application.properties
    schema.sql
  src/main/java/com/example/dbsecurity/
    DbSecurityLabApplication.java
    DatabaseUserDetailsService.java
    SecurityConfiguration.java
    DemoController.java
~~~

Các API sử dụng:

- `JdbcTemplate` để đọc database bằng truy vấn có parameter `?`.
- `UserDetailsService` để chuyển account data thành `UserDetails`.
- `SimpleGrantedAuthority` để chuyển role/permission thành authorities.
- `DaoAuthenticationProvider` với `PasswordEncoder` để kiểm tra password.
- `SecurityFilterChain` để chứng minh `hasRole` và `hasAuthority`.
- H2 in-memory database để không cần cài DB server.

### 5.1. pom.xml

Tạo tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>db-security-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

Spring Boot parent quản lý versions của Spring Security, Spring JDBC, H2 và các thành phần khác qua BOM. Đừng thêm một phiên bản `spring-security-core` riêng chỉ vì xem được số version mới hơn trên Maven Central. `spring-boot-starter-webmvc` là starter cho ứng dụng Spring MVC trong Boot 4; `spring-boot-starter-web` xuất hiện trong nhiều bài Boot 3 trước đó.

### 5.2. Cấu hình database local

Tạo `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:securitylab;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.driver-class-name=org.h2.Driver

spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql

server.port=8080
~~~

H2 ở đây chạy **trong bộ nhớ**: khi ứng dụng dừng, dữ liệu sẽ mất. Tài khoản `sa` và password trống là cấu hình local cho cơ sở dữ liệu nhúng, **không phải khuyến nghị production**. Với hệ thống thật dùng database được quản lý, secret nằm trong secret manager/config của môi trường, kết nối được bảo vệ, database roles có quyền tối thiểu và migration được thực hiện qua Flyway/Liquibase hoặc công cụ được tổ chức chọn.

Tạo `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE app_accounts (
    account_id BIGINT PRIMARY KEY,
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,
    locked_until_ms BIGINT,
    account_expires_ms BIGINT,
    credentials_expires_ms BIGINT
);

CREATE TABLE roles (
    role_code VARCHAR(60) PRIMARY KEY
);

CREATE TABLE permissions (
    permission_code VARCHAR(80) PRIMARY KEY
);

CREATE TABLE account_roles (
    account_id BIGINT NOT NULL,
    role_code VARCHAR(60) NOT NULL,
    PRIMARY KEY (account_id, role_code),
    FOREIGN KEY (account_id) REFERENCES app_accounts(account_id),
    FOREIGN KEY (role_code) REFERENCES roles(role_code)
);

CREATE TABLE role_permissions (
    role_code VARCHAR(60) NOT NULL,
    permission_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (role_code, permission_code),
    FOREIGN KEY (role_code) REFERENCES roles(role_code),
    FOREIGN KEY (permission_code) REFERENCES permissions(permission_code)
);
~~~

Khóa chính kép ngăn gán cùng một vai trò/quyền hai lần. Dù có ràng buộc SQL, ứng dụng vẫn cần tránh cấp quyền từ đầu vào không đáng tin và kiểm tra thẩm quyền của người cập nhật bảng.

### 5.3. Main class và dữ liệu demo

Tạo `src/main/java/com/example/dbsecurity/DbSecurityLabApplication.java`:

~~~java
package com.example.dbsecurity;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class DbSecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(DbSecurityLabApplication.class, args);
    }

    @Bean
    CommandLineRunner seedData(
            JdbcTemplate jdbc, PasswordEncoder encoder, Clock clock) {
        return args -> {
            jdbc.update("INSERT INTO roles(role_code) VALUES (?)", "STAFF");
            jdbc.update("INSERT INTO roles(role_code) VALUES (?)", "ADMIN");

            for (String code : new String[] {
                    "DOC_READ", "DOC_WRITE", "USER_MANAGE"}) {
                jdbc.update(
                    "INSERT INTO permissions(permission_code) VALUES (?)",
                    code);
            }

            grantPermission(jdbc, "STAFF", "DOC_READ");
            grantPermission(jdbc, "ADMIN", "DOC_READ");
            grantPermission(jdbc, "ADMIN", "DOC_WRITE");
            grantPermission(jdbc, "ADMIN", "USER_MANAGE");

            long now = clock.instant().toEpochMilli();
            long tomorrow = clock.instant()
                    .plus(Duration.ofDays(1)).toEpochMilli();
            long yesterday = clock.instant()
                    .minus(Duration.ofDays(1)).toEpochMilli();

            saveUser(jdbc, encoder, 101L, "mai", true,
                    null, null, null);
            saveUser(jdbc, encoder, 102L, "admin", true,
                    null, null, null);
            saveUser(jdbc, encoder, 103L, "linh", false,
                    null, null, null);
            saveUser(jdbc, encoder, 104L, "khoa", true,
                    tomorrow, null, null);
            saveUser(jdbc, encoder, 105L, "an", true,
                    null, yesterday, null);
            saveUser(jdbc, encoder, 106L, "tue", true,
                    null, null, yesterday);

            grantRole(jdbc, 101L, "STAFF");
            grantRole(jdbc, 102L, "ADMIN");
            grantRole(jdbc, 103L, "STAFF");
            grantRole(jdbc, 104L, "STAFF");
            grantRole(jdbc, 105L, "STAFF");
            grantRole(jdbc, 106L, "STAFF");
        };
    }

    private static void saveUser(
            JdbcTemplate jdbc,
            PasswordEncoder encoder,
            long id,
            String username,
            boolean enabled,
            Long lockedUntil,
            Long accountExpires,
            Long credentialsExpires) {
        jdbc.update(
            "INSERT INTO app_accounts " +
            "(account_id, username, password_hash, enabled, " +
            "locked_until_ms, account_expires_ms, credentials_expires_ms) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            id, username, encoder.encode("demo-password"),
            enabled, lockedUntil, accountExpires, credentialsExpires);
    }

    private static void grantRole(
            JdbcTemplate jdbc, long id, String role) {
        jdbc.update(
            "INSERT INTO account_roles(account_id, role_code) " +
            "VALUES (?, ?)", id, role);
    }

    private static void grantPermission(
            JdbcTemplate jdbc, String role, String permission) {
        jdbc.update(
            "INSERT INTO role_permissions(role_code, permission_code) " +
            "VALUES (?, ?)", role, permission);
    }
}
~~~

Đây là **seed demo local** được chạy ở startup, không phải cơ chế tạo account production. Password dùng chung là `demo-password`, được bcrypt hash bởi `PasswordEncoder` trước khi ghi vào DB. Hash bcrypt có salt ngẫu nhiên nên các chuỗi hash trong DB **không cố định giữa hai lần chạy**, nhưng kiểm tra login vẫn hoạt động.

Tài khoản:

| Username | Password demo | Trạng thái | Role |
| --- | --- | --- | --- |
| `mai` | `demo-password` | Active | STAFF |
| `admin` | `demo-password` | Active | ADMIN |
| `linh` | `demo-password` | Disabled | STAFF |
| `khoa` | `demo-password` | Locked tạm đến ngày sau | STAFF |
| `an` | `demo-password` | Account expired từ ngày trước | STAFF |
| `tue` | `demo-password` | Credentials expired từ ngày trước | STAFF |

Biến `now` ở demo thể hiện thời điểm tham chiếu nhưng các giá trị thời gian được tính từ `Clock` và không cần in ra. Với production, không hardcode mật khẩu, không seed tài khoản quản trị mặc định và không cấp quyền ADMIN qua một runner tương tự.

### 5.4. UserDetailsService đọc dữ liệu từ JDBC

Tạo `src/main/java/com/example/dbsecurity/DatabaseUserDetailsService.java`:

~~~java
package com.example.dbsecurity;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Clock;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final JdbcTemplate jdbc;
    private final Clock clock;

    public DatabaseUserDetailsService(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    private record AccountRow(
            long id,
            String username,
            String passwordHash,
            boolean enabled,
            Long lockedUntilMs,
            Long accountExpiresMs,
            Long credentialsExpiresMs) {
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        List<AccountRow> rows = jdbc.query(
            "SELECT account_id, username, password_hash, enabled, " +
            "locked_until_ms, account_expires_ms, credentials_expires_ms " +
            "FROM app_accounts WHERE username = ?",
            (rs, rowNum) -> new AccountRow(
                rs.getLong("account_id"),
                rs.getString("username"),
                rs.getString("password_hash"),
                rs.getBoolean("enabled"),
                nullableLong(rs, "locked_until_ms"),
                nullableLong(rs, "account_expires_ms"),
                nullableLong(rs, "credentials_expires_ms")),
            username
        );

        if (rows.isEmpty()) {
            throw new UsernameNotFoundException("Unknown user");
        }

        AccountRow account = rows.get(0);

        List<String> roles = jdbc.queryForList(
            "SELECT role_code FROM account_roles WHERE account_id = ?",
            String.class, account.id());

        List<String> permissions = jdbc.queryForList(
            "SELECT DISTINCT rp.permission_code " +
            "FROM role_permissions rp " +
            "JOIN account_roles ar ON ar.role_code = rp.role_code " +
            "WHERE ar.account_id = ?",
            String.class, account.id());

        Set<String> codes = new TreeSet<>();
        for (String role : roles) {
            codes.add("ROLE_" + role);
        }
        codes.addAll(permissions);

        List<GrantedAuthority> granted = codes.stream()
            .map(SimpleGrantedAuthority::new)
            .map(authority -> (GrantedAuthority) authority)
            .toList();

        long now = clock.millis();
        boolean locked = account.lockedUntilMs() != null
                && now < account.lockedUntilMs();
        boolean accountExpired = account.accountExpiresMs() != null
                && now >= account.accountExpiresMs();
        boolean credentialsExpired =
                account.credentialsExpiresMs() != null
                && now >= account.credentialsExpiresMs();

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .accountLocked(locked)
                .accountExpired(accountExpired)
                .credentialsExpired(credentialsExpired)
                .authorities(granted)
                .build();
    }

    private static Long nullableLong(ResultSet rs, String column)
            throws SQLException {
        long value = rs.getLong(column);
        return rs.wasNull() ? null : value;
    }
}
~~~

Đây là phần **quan trọng nhất** của bài. Đọc từ trên xuống:

1. `loadUserByUsername` nhận username do cơ chế xác thực đang xử lý và dùng JDBC **parameter binding (`?`)**; không nối username vào SQL.
2. Nếu không có bản ghi, ném `UsernameNotFoundException`, **không trả `null`** và không tự tạo một account giả có quyền.
3. Truy vấn `account_roles` để lấy role codes theo **`account_id` ổn định**.
4. Truy vấn join `account_roles` với `role_permissions` để lấy các permission mà account được cấp qua roles.
5. Biến role thành `ROLE_...`, còn permission giữ nguyên code. Dùng `TreeSet` để loại trùng và giữ thứ tự ổn định khi quan sát.
6. Tính `locked`, `accountExpired`, `credentialsExpired` từ timestamp hiện tại.
7. Trả `UserDetails` của Spring Security với **password hash**, trạng thái và một danh sách authorities đã tổng hợp.

`TreeSet` ở đây chỉ nhằm xử lý danh sách trong memory; nó không kiểm chứng độ tin cậy của role/permission. Chỉ role/permission đã được máy chủ quản lý ở DB mới được đưa vào `GrantedAuthority`.

**Đừng sửa code thành `.roles(roles).authorities(permissions)` rồi kỳ vọng hai lời gọi tự nối danh sách.** Chúng ta tính `granted` trước và gọi `.authorities(granted)` một lần.

### 5.5. Cấu hình SecurityFilterChain và PasswordEncoder

Tạo `src/main/java/com/example/dbsecurity/SecurityConfiguration.java`:

~~~java
package com.example.dbsecurity;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            DatabaseUserDetailsService users,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        return http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/docs/edit")
                    .hasAuthority("DOC_WRITE")
                .requestMatchers("/docs")
                    .hasAuthority("DOC_READ")
                .requestMatchers("/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Bằng việc gọi `authenticationProvider(provider)`, chain này sử dụng một `DaoAuthenticationProvider` được cấu hình rõ với `DatabaseUserDetailsService` và `BCryptPasswordEncoder`. Mục tiêu là dễ theo dõi luồng học tập; dự án Boot bình thường cũng có thể dựa vào cơ chế cấu hình xác thực mặc định theo những bean đã khai báo phù hợp.

Ba rule minh họa:

- `GET /docs` yêu cầu authority `DOC_READ`.
- `GET /docs/edit` yêu cầu authority `DOC_WRITE`.
- `GET /admin` yêu cầu role `ADMIN`, tương ứng authority `ROLE_ADMIN`.

`anyRequest().authenticated()` là fallback để tránh những endpoint chưa khai báo trong ví dụ bị công khai ngoài ý muốn. Nó **không tự thay kiểm tra quyền đối với từng bản ghi** của hệ thống thật.

Không có `formLogin` trong ví dụ. HTTP Basic giúp dùng `curl` để minh họa mapping; trong production phải có **HTTPS**, chính sách credentials/secret phù hợp và cân nhắc cơ chế login thích hợp. CSRF mặc định của Spring Security vẫn cần được đánh giá nếu thêm các endpoint có tác động ghi dữ liệu, đặc biệt trong ứng dụng browser/cookie; demo chỉ có các GET không thay đổi dữ liệu.

### 5.6. Controller minh họa phân quyền

Tạo `src/main/java/com/example/dbsecurity/DemoController.java`:

~~~java
package com.example.dbsecurity;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/docs")
    public String docs() {
        return "docs-readable";
    }

    @GetMapping("/docs/edit")
    public String edit() {
        return "docs-editable";
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin-area";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "hello-" + authentication.getName();
    }
}
~~~

Controller không tự tìm role bằng `if`. Spring Security áp dụng rule trước khi request tới controller. Trong ứng dụng thật, những thao tác ghi dữ liệu nên dùng HTTP method đúng (`POST`, `PATCH`, `PUT`, `DELETE`), kiểm soát CSRF khi phù hợp và bổ sung authorization theo bản ghi/tenant ở service.

### 5.7. Build và chạy

Yêu cầu JDK 17+ và Maven phù hợp; lần đầu cần truy cập kho dependency:

~~~bash
java -version
mvn -version
mvn -q -DskipTests package
mvn spring-boot:run
~~~

Nếu port 8080 đang có chương trình khác, đổi `server.port` rồi sửa URL trong lệnh kiểm tra. Do H2 in-memory, khi dừng project và chạy lại, schema được tạo lại và runner seed dữ liệu mới. Ví dụ không ghi dữ liệu vào hệ thống bên ngoài.

Trên terminal thứ hai, thử (mật khẩu `demo-password` chỉ là **demo local**, không dùng password thật trên command line):

~~~bash
curl -s -o /dev/null -w 'mai-docs=%{http_code}\n' \
  -u mai:demo-password http://localhost:8080/docs

curl -s -o /dev/null -w 'mai-edit=%{http_code}\n' \
  -u mai:demo-password http://localhost:8080/docs/edit

curl -s -o /dev/null -w 'admin-edit=%{http_code}\n' \
  -u admin:demo-password http://localhost:8080/docs/edit

curl -s -o /dev/null -w 'admin-area=%{http_code}\n' \
  -u admin:demo-password http://localhost:8080/admin

curl -s -o /dev/null -w 'linh-disabled=%{http_code}\n' \
  -u linh:demo-password http://localhost:8080/profile

curl -s -o /dev/null -w 'khoa-locked=%{http_code}\n' \
  -u khoa:demo-password http://localhost:8080/profile

curl -s -o /dev/null -w 'an-expired=%{http_code}\n' \
  -u an:demo-password http://localhost:8080/profile

curl -s -o /dev/null -w 'tue-expired-password=%{http_code}\n' \
  -u tue:demo-password http://localhost:8080/profile
~~~

Kết quả status dự kiến theo chính sách và dữ liệu của project:

~~~text
mai-docs=200
mai-edit=403
admin-edit=200
admin-area=200
linh-disabled=401
khoa-locked=401
an-expired=401
tue-expired-password=401
~~~

Ở PowerShell Windows, gọi `curl.exe` thay `curl` nếu `curl` là alias; ký tự `\` nối dòng thuộc shell Bash, nên trên Windows có thể đặt mỗi lệnh thành một dòng riêng hoặc dùng cú pháp PowerShell phù hợp.

Thử thêm:

~~~bash
curl -s -u mai:demo-password http://localhost:8080/profile
~~~

Body dự kiến:

~~~text
hello-mai
~~~

Giải thích các mã:

- Mai có `ROLE_STAFF` và `DOC_READ`: được đọc `/docs` nhưng thiếu `DOC_WRITE`, nên `/docs/edit` trả 403.
- Admin có `ROLE_ADMIN`, `DOC_READ`, `DOC_WRITE`, `USER_MANAGE`: được vào `/admin` và `/docs/edit`.
- Linh disabled, Khoa locked, An account expired, Tuệ credentials expired: dù mật khẩu demo đúng, provider kiểm tra trạng thái và từ chối xác thực mới; HTTP Basic thường đáp lại 401.
- Người chưa đăng nhập vào `/profile` cũng nhận 401 theo HTTP Basic, **không đồng nghĩa đã có một lần nhập sai mật khẩu**.

HTTP status được phân tích theo chain demo; nếu thêm form login, entry point, proxy hoặc cấu hình khác, response có thể chuyển hướng hoặc đổi định dạng. **Không công khai nguyên nhân “username tồn tại nhưng bị khóa”** cho người chưa xác minh, để giảm khả năng dò tài khoản.

## 6. Chú ý: UserDetails builder nhận cờ “bad state”, interface nhận cờ “good state”

Đây là lỗi dễ gặp khi mapper đọc trạng thái:

| Dữ liệu domain | Method builder | Method tương ứng trên `UserDetails` |
| --- | --- | --- |
| `enabled=true` | `.disabled(false)` | `isEnabled()==true` |
| Account đang locked | `.accountLocked(true)` | `isAccountNonLocked()==false` |
| Account đã expired | `.accountExpired(true)` | `isAccountNonExpired()==false` |
| Credentials đã expired | `.credentialsExpired(true)` | `isCredentialsNonExpired()==false` |

Cú pháp này dễ gây sai vì builder viết theo **trạng thái lỗi**, còn các phương thức interface hầu hết chứa chữ `Non`.

Ví dụ sai:

~~~java
// SAI nếu enabled nghĩa là tài khoản đang hoạt động.
.disabled(account.enabled())
~~~

Ví dụ đúng:

~~~java
.disabled(!account.enabled())
~~~

Trong bài thực hành, ba điều kiện thời gian đều tính từ `Clock`, không lấy đồng hồ trong controller. Có thể inject `Clock.fixed(...)` trong unit test để kiểm tra chính xác các thời điểm ngay trước, đúng tại và sau hạn. Khi thời gian bằng `account_expires_ms`, `accountExpired` là `true` theo quy ước ví dụ.

**Chú ý:** nếu database có một cờ `manually_locked` và một thời hạn khóa tạm, cần tính `locked = manuallyLocked || now < lockedUntil` để không tự mở khóa một tài khoản bị quản trị viên cấm. Schema demo chỉ có khóa theo thời gian để tập trung chủ đề.

## 7. Khi nào dùng JdbcUserDetailsManager thay vì viết UserDetailsService?

Spring Security có `JdbcDaoImpl` triển khai `UserDetailsService` và `JdbcUserDetailsManager` mở rộng để quản lý user qua JDBC. Chúng hữu ích khi dữ liệu của bạn phù hợp **schema mặc định** hoặc bạn điều chỉnh các truy vấn được hỗ trợ.

Schema mặc định của JDBC authentication gồm các bảng `users` và `authorities`, thường có trường username, password, enabled và authority. Spring Security có tài liệu và script mẫu riêng.

Ví dụ ý tưởng:

~~~java
@Bean
UserDetailsManager users(DataSource dataSource) {
    return new JdbcUserDetailsManager(dataSource);
}
~~~

Đây là **mảnh cấu hình** chỉ phù hợp khi bạn đã tạo schema đúng với các truy vấn mặc định hoặc cấu hình truy vấn tùy chỉnh. Chưa có seed user, chưa có web/security chain và không phải chương trình chạy độc lập.

So sánh:

| Lựa chọn | Phù hợp | Giới hạn cần nhận thức |
| --- | --- | --- |
| `JdbcUserDetailsManager` với schema mặc định | Ứng dụng nhỏ, muốn quản lý users/authorities theo cấu trúc chuẩn | Không tự biết các bảng role_permissions/status phức tạp của domain |
| `JdbcDaoImpl` với truy vấn tùy biến | Schema khác một phần, mapping vẫn tương đối đơn giản | Phải hiểu cấu trúc trả về và điều kiện của implementation |
| `UserDetailsService` tự viết như demo | Muốn join nhiều bảng, account status, permission, audit hoặc tenant rõ ràng | Bạn chịu trách nhiệm query, mapping, performance, fail closed và test |
| `AuthenticationProvider` tùy biến | Cơ chế xác thực không phải username/password JDBC hoặc có yêu cầu đặc thù | Phải tự bảo đảm logic xác minh và exception đúng, không đánh dấu authenticated từ dữ liệu chưa kiểm chứng |

Không có nghĩa `JdbcUserDetailsManager` tự động đọc đủ `locked_until`, `account_expires_at`, `credential_expires_at` từ schema nghiệp vụ bất kỳ. Nếu cần các trạng thái đó, hãy xem liệu implementation có hỗ trợ cấu hình tương ứng hay cần `UserDetailsService` tùy biến như bài này.

## 8. Quan hệ role-permission nhiều cấp và trùng quyền

Một account có thể có hai role:

~~~text
Role STAFF -> DOC_READ, REPORT_READ
Role REVIEWER -> DOC_READ, DOC_APPROVE
Account mai -> STAFF + REVIEWER
~~~

Khi hợp nhất:

~~~text
ROLE_STAFF
ROLE_REVIEWER
DOC_READ
REPORT_READ
DOC_APPROVE
~~~

Quyền `DOC_READ` xuất hiện ở hai role nhưng chỉ cần một authority `DOC_READ` trong `UserDetails`. Có thể dùng `Set` và `DISTINCT` ở query, như demo, để tránh duplicates.

### Không mặc định ROLE_ADMIN có mọi quyền

Trong Spring Security, `hasRole("ADMIN")` chỉ yêu cầu `ROLE_ADMIN` theo convention. Nó **không tự cấp tất cả** `DOC_READ`, `DOC_WRITE`, `USER_MANAGE`. Nếu hệ thống muốn role ADMIN có các quyền ấy, phải ánh xạ chúng từ DB hoặc cấu hình `RoleHierarchy`/policy có chủ đích.

Một role hierarchy có thể thể hiện `ADMIN > STAFF` theo quy tắc riêng, nhưng không nên giả định có hierarchy khi chưa cấu hình. Quyền cụ thể theo tài nguyên vẫn cần policy phù hợp, dù có role ADMIN.

### Quyền “deny” và dữ liệu trong DB

Nếu có cả bảng `allow` và `deny`, một danh sách `GrantedAuthority` đơn thuần không tự giải quyết ưu tiên deny-overrides/allow-overrides. Đó là quyết định thiết kế authorization: có thể cần `AuthorizationManager` riêng, policy engine hoặc logic service. Không cấp authority tương đương allow chỉ vì tìm thấy một bản ghi permission có trạng thái `DENIED`.

**Quy tắc mặc định:** nếu không xác định được quyền đáng tin, đừng tự cấp quyền rộng hơn. Tuy nhiên cũng không nên coi lỗi database là “người dùng không có quyền” nếu thực chất hệ thống mất khả năng xác minh; cần giữ đúng nguyên nhân trong log và phản hồi an toàn.

## 9. Đa tenant: một role không nhất thiết có phạm vi toàn hệ thống

Ở ứng dụng SaaS, Mai có thể là `ADMIN` trong công ty A nhưng chỉ là `VIEWER` trong công ty B:

~~~text
account_id = 101

memberships:
  (account=101, tenant=A, role=ADMIN)
  (account=101, tenant=B, role=VIEWER)
~~~

Nếu `UserDetailsService` vô điều kiện gộp mọi role thành `ROLE_ADMIN`, rule `hasRole("ADMIN")` có thể vô tình cấp quyền admin **ở cả B**. Vì vậy schema demo chỉ minh họa **global roles** và **global permissions**.

Với ứng dụng đa tenant, cần định nghĩa **phạm vi**:

- Role cấp toàn hệ thống khác role trong tenant.
- Membership phải gắn với account ID và tenant ID do server xác minh.
- Nếu client gửi `X-Tenant-Id` hoặc tenant trong URL, đó là **yêu cầu lựa chọn tenant**, không phải bằng chứng membership.
- Policy phải kiểm tra account hiện tại còn thuộc tenant, có quyền với thao tác và tài nguyên đó.
- Nhiều trường hợp nên dùng permission check từ service/repository có `tenant_id` thay vì dồn mọi role của mọi tenant vào authorities chung.

Một policy điển hình:

~~~text
allow(account, action, resource, tenant)
  = authenticated(account)
    AND currentAccountEnabled(account)
    AND isMember(account, tenant)
    AND resource.tenantId == tenant
    AND hasTenantPermission(account, tenant, action, resource)
~~~

Đây là mô hình nghiệp vụ, không phải API được Spring Security tự cài sẵn. Các quyền có thể được cung cấp bởi `AuthorizationManager`, `@PreAuthorize` gọi policy service, hoặc tầng truy vấn dữ liệu được giới hạn theo tenant.

**Đừng dựa vào role tên `ADMIN` để cho phép đọc tùy ý mọi bản ghi**. Cần kiểm tra IDOR/BOLA: nếu `/documents/102` nhận một ID do client đổi từ 101 thành 102, server phải kiểm tra quyền sở hữu/chia sẻ và tenant, không chỉ username đã đăng nhập.

## 10. Dữ liệu DB có thể đổi sau khi xác thực

Giả sử lúc 09:00, Mai đăng nhập và `Authentication` được tạo với `DOC_WRITE`. Lúc 09:05, quản trị viên rút quyền `DOC_WRITE` từ bảng `role_permissions`. Mai vẫn đang giữ một HTTP session có `Authentication` được tạo lúc trước.

~~~text
09:00 DB: STAFF -> DOC_READ, DOC_WRITE
      login tạo Authentication với 2 permissions

09:05 DB: STAFF -> DOC_READ
      role_permissions đã đổi

09:06 Session cũ:
      Authentication.getAuthorities() có thể VẪN chứa DOC_WRITE
      nếu ứng dụng không làm mới/thu hồi context

09:10 Login mới:
      UserDetailsService đọc DB -> chỉ còn DOC_READ
~~~

**Không mặc định thay đổi DB lập tức làm mất quyền trên mọi session/JWT đang tồn tại.** `UserDetailsService` thường tham gia **xác thực mới**; một request sử dụng session cũ có thể không gọi lại `loadUserByUsername`.

Các chiến lược được dùng tùy yêu cầu:

| Trường hợp | Chiến lược có thể áp dụng | Đánh đổi |
| --- | --- | --- |
| Ứng dụng stateless kiểm tra DB ở mỗi request | Query trạng thái/quyền hiện tại | Latency và tải DB |
| HTTP session lưu authorities | Thu hồi session khi đổi role/trạng thái, hoặc làm mới theo TTL/version | Quản lý nhiều phiên trên nhiều node |
| JWT chứa roles/permissions | Token có TTL ngắn, refresh và revocation/version/introspection | Thông tin trong JWT có thể cũ đến khi hết hạn |
| Hành động nhạy cảm | Kiểm tra owner/tenant/permission hiện hành ngay ở service | Thêm kiểm tra theo hành động |
| Cache UserDetails/permission | TTL, cache invalidation theo event và bản quyền có version | Cần kiểm soát race condition và độ trễ |

Không có một đáp án duy nhất. Đối với thao tác nhạy cảm như cấp quyền quản trị, chuyển tiền hoặc xuất dữ liệu, cần xác định **độ trễ thu hồi chấp nhận được** và test rõ.

### Cẩn thận khi cache UserDetails

Spring Security có cơ chế `CredentialsContainer.eraseCredentials()` dọn thông tin nhạy cảm trên kết quả xác thực. Nếu một `UserDetails` mutable có password hash được cache rồi dùng chung object làm principal, thao tác dọn credentials có thể làm thay đổi chính object trong cache. Đừng tối ưu performance bằng cách chia sẻ mutable principal không kiểm soát.

Giải pháp thường là copy `UserDetails` cho luồng xác thực, giới hạn cache lifetime hoặc tách dữ liệu password hash khỏi danh tính/principal được giữ lâu. **Không tắt `eraseCredentialsAfterAuthentication` một cách tùy tiện** chỉ vì muốn cache hoạt động.

## 11. Những yêu cầu an toàn khi nạp role và permission từ DB

### 11.1. Không nhận roles/authorities từ request

Ví dụ request body:

~~~json
{
  "username": "mai",
  "role": "ADMIN",
  "permissions": ["DOC_WRITE"]
}
~~~

Đây là dữ liệu **do client tự khai**. Không dùng nó để xây dựng `Authentication` đã xác thực hoặc `SimpleGrantedAuthority` cho Mai. Role, permission và account status phải được lấy từ **nguồn tin cậy** sau khi danh tính được xác minh, với một quy trình quản trị riêng.

Một lỗi điển hình là cho phép `POST /register` nhận và lưu nguyên `role=ADMIN` vào `account_roles`. Đó là privilege escalation. Với self-registration, server phải quyết định role mặc định an toàn và xác minh quyền nếu có thao tác cấp quyền đặc biệt.

### 11.2. Giới hạn quyền cập nhật bảng bảo mật

Các bảng `account_roles` và `role_permissions` chứa chính sách bảo mật. Thao tác thêm/sửa/xóa phải có authorization, transaction, audit, kiểm tra tenant và đôi khi yêu cầu xác nhận nhiều người.

Không cho một account tự đổi `enabled`, `locked_until_ms`, `role_code` hoặc `permission_code` theo ý muốn chỉ vì có quyền cập nhật hồ sơ. API “edit profile” nên dùng DTO giới hạn trường được phép sửa.

### 11.3. Fail closed khi không đọc được DB

Nếu `JdbcTemplate` báo lỗi kết nối, `UserDetailsService` không nên tạo user giả với `ROLE_USER` rồi cho login tiếp. Một lỗi storage là **không xác minh được**, khác với “username không tồn tại”.

Spring Security có các subtype của `AuthenticationException` để phân biệt `BadCredentialsException` và `AuthenticationServiceException`. Hãy để nguyên nhân lỗi được quan sát chính xác trong hệ thống, nhưng không trả stack trace, SQL hay hostname DB cho người chưa xác thực.

### 11.4. Dùng parameter binding và truy vấn chỉ đọc

Ví dụ đúng:

~~~java
jdbc.queryForList(
    "SELECT role_code FROM account_roles WHERE account_id = ?",
    String.class, accountId);
~~~

Không nối trực tiếp username/tenant từ request vào SQL. Với JPA hoặc Hibernate, cũng phải dùng bind parameters và hiểu cách fetch/join để tránh SQL injection và N+1 queries.

Cơ sở dữ liệu có thể cấp một DB user **chỉ đọc** cho các truy vấn xác thực (trừ khi ứng dụng cần cập nhật lockout counters/trạng thái ở nơi khác). Tách các thao tác quản trị ghi role/permission theo principle of least privilege khi khả thi.

### 11.5. Quy tắc đặt tên authority phải rõ

Chọn conventions như:

~~~text
roles.role_code:
  STAFF
  ADMIN

permissions.permission_code:
  DOC_READ
  DOC_WRITE
  USER_MANAGE

Runtime authorities:
  ROLE_STAFF
  ROLE_ADMIN
  DOC_READ
  DOC_WRITE
  USER_MANAGE
~~~

Nếu cho phép admin tạo custom role name, cần validate độ dài, ký tự, uniqueness và tránh tên trùng convention quan trọng. Không để permission code trùng một role authority theo cách gây hiểu nhầm. Migrate dữ liệu cũ trước khi đổi convention.

## 12. Hiệu năng và tính nhất quán khi nhiều người dùng đăng nhập

Ví dụ demo sử dụng ba query mỗi login: account, roles, permissions. Với hệ thống nhỏ điều này thường đủ minh bạch. Khi tải tăng, cần xem:

1. **Indexes:** username unique cho lookup; `account_roles(account_id, role_code)` có PK giúp tìm roles; `role_permissions(role_code, permission_code)` giúp join.
2. **N+1 queries:** nếu duyệt từng role rồi gọi query riêng để lấy permissions, số truy vấn tăng theo số role; trong demo chúng ta join một lần để lấy tất cả permissions.
3. **Data consistency:** nếu role bị đổi giữa ba query, request có thể thấy snapshot không nhất quán. Với hệ thống yêu cầu chính xác cao, cần transaction isolation thích hợp hoặc versioning, không chỉ cache.
4. **Cache:** có thể giảm DB round-trips nhưng phải quản lý TTL, invalidation, principal mutation và trạng thái bị khóa sau login.
5. **Connection pool:** database outage hoặc connection exhaustion ảnh hưởng login; cần timeout và giám sát, không retry vô hạn trên cùng request.
6. **Query projection:** chỉ lấy các cột cần cho authentication, không load toàn bộ đồ thị entity hoặc dữ liệu profile nhạy cảm.
7. **Case sensitivity:** cần quy định có phân biệt hoa/thường ở username/email không; DB collation, normalization và unique index phải nhất quán.
8. **Resource authorization:** permission theo tenant/bản ghi có thể cần query riêng, tránh cố nhét toàn bộ dữ liệu thuộc tính bản ghi vào token.

Có thể thiết kế `AuthSnapshot` chứa ID, version, authorities và status được nạp nhất quán trong một transaction, nhưng phải có chiến lược làm mới khi permission thay đổi. Không kết luận một snapshot từ DB luôn là dữ liệu mới nhất khi dùng lại trong session.

### Sự cố database và phân quyền

Một cách xử lý **không an toàn** là: khi query quyền lỗi, mặc định thêm `ROLE_ADMIN` để “không gián đoạn”. Một cách khác cũng gây khó vận hành là giả vờ password sai cho mọi DB outage. Nên từ chối cấp quyền khi không thể xác minh, giữ lỗi hệ thống chính xác cho metrics/audit, và trả phản hồi bên ngoài phù hợp.

## 13. Kiểm thử mapping theo nhiều lớp

Có thể kiểm thử ở ba tầng:

- **Tầng dữ liệu:** SQL join trả đúng roles và permissions cho một account; không nhân quyền sai qua quan hệ trùng.
- **Tầng authentication:** `UserDetailsService` cung cấp đúng hash, flags và authorities; `DaoAuthenticationProvider` từ chối disabled/locked/expired và mật khẩu sai.
- **Tầng authorization qua HTTP:** các đường `/docs`, `/docs/edit`, `/admin` thực sự trả status đúng qua filter chain.

Ma trận kiểm thử tối thiểu:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Mai có STAFF -> DOC_READ | `hasRole("STAFF")` và `hasAuthority("DOC_READ")` true |
| Mai thiếu DOC_WRITE | `GET /docs/edit` trả 403 khi login hợp lệ |
| Admin có ADMIN -> DOC_WRITE | `GET /admin` và `GET /docs/edit` trả 200 |
| Password của Mai sai | Xác thực thất bại, HTTP Basic thường 401 |
| Username không tồn tại | Xác thực thất bại; thông báo không dò được account |
| Linh disabled | Không login mới dù password đúng |
| Khoa locked đến thời điểm tương lai | Không login trước `locked_until_ms` |
| Clock vừa đúng `locked_until_ms` | Điều kiện khóa thời gian được gỡ theo quy ước ví dụ |
| An account expired | Không login mới dù có role STAFF |
| Tuệ credentials expired | Không login mới dù password hash khớp |
| Nhiều roles có cùng DOC_READ | `UserDetails` không có duplicate DOC_READ |
| Thu hồi DOC_WRITE ngay sau login | Kiểm tra session/token cũ theo chính sách refresh/revocation |
| Quyền Admin thuộc tenant A, request vào tenant B | Phải bị chặn nếu không có membership/quyền ở B |
| DB roles/permissions tạm lỗi | Không tự cấp role fallback; ghi lỗi hệ thống |
| Đồng thời đổi trạng thái và login | Kiểm soát transaction, race và độ trễ thu hồi |

Đừng dùng riêng `@WithMockUser(roles="ADMIN")` để kết luận **mapping từ database đúng**: annotation dựng sẵn `Authentication`, thường bỏ qua `UserDetailsService` và `DaoAuthenticationProvider`. Test ấy phù hợp kiểm tra policy, nhưng muốn xác minh pipeline dữ liệu thì phải gửi credentials qua login thật hoặc gọi `AuthenticationManager` đã cấu hình.

### Kiểm tra authorities thực tế

Trong môi trường test, có thể lấy:

~~~java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

for (GrantedAuthority authority : auth.getAuthorities()) {
    System.out.println(authority.getAuthority());
}
~~~

Đây là fragment, cần imports và một security context đã xác thực; không phải chương trình độc lập. **Không dùng code trên như endpoint production công khai**. Từ Spring Security 7, provider có thể bổ sung authority liên quan yếu tố xác thực (ví dụ `FACTOR_PASSWORD`), nên khi kiểm thử hãy kiểm tra **các quyền nghiệp vụ mong đợi có trong tập**, không nhất thiết assert danh sách phải bằng đúng số phần tử role/permission do DB cung cấp.

## 14. Những lỗi thường gặp khi viết mapper

1. **“Lưu role ADMIN trong DB thì Spring Security tự tìm được.”** Không: ứng dụng phải nạp và ánh xạ thành authority.
2. **“`hasRole("ADMIN")` tìm `ADMIN` không tiền tố.”** Mặc định nó tìm `ROLE_ADMIN`.
3. **“Gọi `.roles(...)` rồi `.authorities(...)` là nối hai tập.”** Không nên giả định; hãy tổng hợp trước rồi gọi một lần.
4. **“Role ADMIN mặc định có mọi quyền.”** Không: các permission phải được gán hoặc có hierarchy/policy rõ.
5. **“Permission DOC_WRITE và ROLE_DOC_WRITE là cùng một thứ.”** Không; hai chuỗi authority khác nhau.
6. **“Chỉ có `enabled=true` là tài khoản chắc chắn được login.”** Còn locked, account expiry, credential expiry và password check.
7. **“`.disabled(account.enabled())` sẽ giữ tài khoản active.”** Sai: đảo chiều logic.
8. **“Locked_until đã qua nhưng flag vẫn mãi false.”** Có thể do mapper/cached `UserDetails` không tính lại hoặc cache không được invalidated.
9. **“Dùng email làm khóa join role luôn ổn.”** Email có thể đổi; ID nội bộ bất biến thường an toàn hơn.
10. **“Gán role từ JSON đăng ký là tiện.”** Có nguy cơ privilege escalation.
11. **“Một account có role ADMIN ở tenant A sẽ là admin toàn hệ thống.”** Sai nếu quyền có phạm vi tenant.
12. **“Thay đổi role trong database có hiệu lực tức thì trong mọi session/JWT.”** Không mặc định.
13. **“DB query lỗi cứ cho user có ROLE_USER để tiếp tục hoạt động.”** Không được cấp quyền khi không xác minh được.
14. **“Role-permission join nhiều dòng nghĩa có nhiều quyền khác nhau.”** Cần `DISTINCT`/`Set` để loại trùng.
15. **“UserDetailsService tự so mật khẩu.”** Sai: provider dùng PasswordEncoder.
16. **“Password hash của DB có thể trả ra DTO vì không phải plaintext.”** Không; hash vẫn nhạy cảm.
17. **“UserDetailsService trả `null` khi không có account.”** Vi phạm hợp đồng; cần ném `UsernameNotFoundException`.
18. **“Không có authority nào thì nên tự thêm ADMIN để tránh lỗi.”** Không; thiếu quyền thì không cấp quyền.
19. **“`@PreAuthorize` có thể dùng mà không cần bật method security.”** Với cấu hình điển hình cần `@EnableMethodSecurity`; ví dụ chính dùng web URL rules.
20. **“Một `hasAuthority("DOC_READ")` bảo vệ được quyền xem tất cả documents.”** Không; owner/tenant/object-level authorization vẫn cần.
21. **“Roles từ cache luôn đồng bộ với DB.”** Không; cache TTL và invalidation phải được thiết kế.
22. **“Thêm tài khoản vào DB đã đủ để đăng nhập.”** Còn cần hash phù hợp, trạng thái hợp lệ, role/permission và SecurityFilterChain/provider.
23. **“Dùng SQL nối username là không sao vì user đã login.”** Input của login chưa được xác thực; luôn bind parameter.
24. **“Có 403 tức mật khẩu sai.”** Không: 403 thường là thiếu quyền/CSRF; xác thực thất bại theo Basic thường là 401.

## 15. Bài tập tự luyện

**Bài 1 — thêm một role mới.** Thêm `REVIEWER` vào bảng `roles`, cấp `DOC_READ` và `DOC_APPROVE` cho role. Gán role cho Mai. Xác minh `UserDetails.getAuthorities()` chứa `ROLE_STAFF`, `ROLE_REVIEWER`, `DOC_READ`, `DOC_APPROVE` và không chứa `DOC_READ` hai lần.

**Bài 2 — kiểm tra trạng thái theo thời gian.** Thử đặt `locked_until_ms` ngay trước và ngay sau thời điểm do một `Clock.fixed` cung cấp, rồi kiểm tra `UserDetails.isAccountNonLocked()`. Cần định nghĩa đúng ranh giới bằng `now < lockedUntil`.

**Bài 3 — cấp permission không cấp role.** Cân nhắc schema `account_permissions(account_id, permission_code)` để hỗ trợ ngoại lệ trực tiếp. Nếu thêm, phải xác định thứ tự allow/deny, nguồn được quyền gán và cập nhật mapper sao cho không bỏ qua permission từ role.

**Bài 4 — rút quyền sau login.** Cho Mai quyền `DOC_WRITE`, đăng nhập bằng session stateful, rút `DOC_WRITE` trong DB và gọi lại API. Quan sát quyền cũ còn không; đề xuất một chính sách invalidation/refresh phù hợp yêu cầu độ trễ của hệ thống.

**Bài 5 — đa tenant.** Thêm `tenant_id` vào membership, cho Mai ADMIN ở tenant A và VIEWER ở tenant B. Kiểm tra request vào tài nguyên B không được hưởng quyền ADMIN từ A.

**Bài 6 — thất bại database.** Mô phỏng DB tạm ngừng khi login. Đảm bảo hệ thống không tạo `UserDetails` giả, không tự cấp authorities và phân loại lỗi dịch vụ để vận hành xử lý.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Database lưu `STAFF`, `ADMIN`. Khi dùng `hasRole("ADMIN")` với convention mặc định, cần authority nào?

*Trả lời:* `ROLE_ADMIN`. Mapper phải thêm tiền tố `ROLE_` nếu database lưu role code chưa có tiền tố.

**Câu 2.** `hasAuthority("DOC_WRITE")` có tự động hiểu `ROLE_ADMIN` không?

*Trả lời:* Không. Nó tìm authority chuỗi chính xác `DOC_WRITE`; phải gán permission đó qua DB hoặc policy tương ứng.

**Câu 3.** `UserDetailsService` có cần tự gọi `PasswordEncoder.matches` khi đọc user không?

*Trả lời:* Không trong luồng chuẩn của `DaoAuthenticationProvider`. Service nạp username/hash/flags/authorities; provider so credentials.

**Câu 4.** Nếu `.disabled(account.enabled())` được dùng với `enabled=true`, điều gì xảy ra?

*Trả lời:* Đánh dấu user disabled, đảo ngược ý nghĩa dữ liệu. Cần `.disabled(!account.enabled())`.

**Câu 5.** Một user có hai role cùng cấp `DOC_READ`. Có cần tạo hai `SimpleGrantedAuthority("DOC_READ")` không?

*Trả lời:* Không. Có thể `DISTINCT` trong SQL hoặc dùng `Set` trong mapper để hợp nhất.

**Câu 6.** Vì sao không nên lấy role từ `POST /register` rồi tạo `Authentication` có `ROLE_ADMIN`?

*Trả lời:* Client có thể tự cấp quyền quản trị. Chỉ dữ liệu role được quản lý bởi nguồn tin cậy và quy trình đã phân quyền mới dùng để tạo authorities.

**Câu 7.** Sau khi admin đổi role trong DB, mọi `Authentication` đang ở session có tự thay đổi không?

*Trả lời:* Không mặc định. Cần thiết kế cách thu hồi/làm mới session, JWT, cache hoặc kiểm tra authorization hiện hành.

**Câu 8.** Vì sao một `ROLE_ADMIN` của tenant A không nên tự được dùng ở tenant B?

*Trả lời:* Nó thiếu phạm vi tenant; authorization phải gắn role/membership với đúng tenant và tài nguyên.

**Câu 9.** `JdbcUserDetailsManager` mặc định có tự đọc `locked_until_ms` và `role_permissions` trong schema tùy chỉnh không?

*Trả lời:* Không; các truy vấn mặc định dành cho schema JDBC user/authorities chuẩn. Muốn mapping phức tạp cần tùy biến hoặc triển khai `UserDetailsService` riêng.

**Câu 10.** Truy vấn role từ DB báo lỗi kết nối. Có nên cấp quyền mặc định `ROLE_USER` để ứng dụng hoạt động?

*Trả lời:* Không. Không thể xác minh quyền nghĩa là phải từ chối cấp quyền, đồng thời phân loại lỗi hạ tầng phù hợp để giám sát.

**Câu 11.** Nếu status account đã hết hạn nhưng permission `DOC_READ` vẫn còn trong DB, có thể login không?

*Trả lời:* Với `DaoAuthenticationProvider` áp dụng kiểm tra `UserDetails` chuẩn, account expired không được xác thực mới dù role/permission vẫn tồn tại.

**Câu 12.** Điều gì cần kiểm tra ngoài `hasAuthority("DOC_READ")` khi đọc một tài liệu cụ thể?

*Trả lời:* Owner, tenant, membership, trạng thái dữ liệu và chính sách chia sẻ của bản ghi đó. Authority chung không tự thực hiện object-level authorization.

## 17. Checklist trước khi áp dụng vào hệ thống thật

- [ ] Có schema rõ cho account, role, permission và quan hệ gán; foreign keys, unique/indexes phù hợp.
- [ ] Có **account ID ổn định**, không dùng display name hoặc email thay đổi làm khóa quyền lâu dài.
- [ ] Password được lưu bằng hash an toàn, `PasswordEncoder` được quản lý phù hợp và không trả hash ra client.
- [ ] `UserDetailsService` lấy dữ liệu thật từ nguồn tin cậy, dùng parameter binding và không trả `null`.
- [ ] Roles được ánh xạ đúng thành `ROLE_...`, permissions thành đúng authority code; không double prefix.
- [ ] Hợp nhất roles và permissions trước khi gán vào `UserDetails`, loại trùng có chủ đích.
- [ ] Enabled, locked, account expired, credentials expired được chuyển đúng chiều thành cờ trong `UserDetails`.
- [ ] Quy tắc timezones/UTC và ranh giới expiry được thống nhất và test bằng `Clock`.
- [ ] `DaoAuthenticationProvider` có `UserDetailsService` và `PasswordEncoder` đúng; `SecurityFilterChain` có rule phù hợp.
- [ ] Không nhận quyền từ request tự khai; APIs cấp/sửa quyền có authorization, kiểm tra tenant, audit và transaction.
- [ ] Có kiểm tra owner/tenant/object-level permission ngoài authority chức năng.
- [ ] Có chiến lược khi DB role/status đổi sau login: session/JWT revocation, refresh, version hoặc policy lookup.
- [ ] Cache user không chia sẻ mutable `UserDetails` bị credential erasure làm sai lần đăng nhập sau.
- [ ] Khi DB lỗi, không tạo quyền fallback; log/metrics giữ đúng nguyên nhân để khôi phục.
- [ ] Tối ưu query bằng indexes/join thích hợp, tránh N+1 và kiểm soát snapshot/transaction khi cần.
- [ ] Test bao phủ quyền đủ/thiếu, user không tồn tại, mật khẩu sai, bị khóa, disabled, hết hạn và nhiều roles.
- [ ] Test permission bị thu hồi trên session/token cũ theo đúng SLA bảo mật.
- [ ] Dự án production dùng migration, backup, secrets/TLS, audit, bản vá Security và DB user quyền tối thiểu.

**Một công thức tư duy hữu ích:** database nói account đang có những role, permission và trạng thái gì; `UserDetailsService` chuyển chúng thành **password hash + flags + GrantedAuthority**; `DaoAuthenticationProvider` quyết định lần login có đủ tin cậy hay không; `SecurityFilterChain` và service policy quyết định **chủ thể ấy được làm hành động nào, với dữ liệu nào**. Khi tách rõ các trách nhiệm, bạn sẽ tránh được cả lỗi cấp quyền thừa và lỗi khóa/hết hạn không có hiệu lực.

### Tài liệu chính thức

- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — JDBC Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/jdbc.html)
- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security — User Builder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Spring Boot — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
