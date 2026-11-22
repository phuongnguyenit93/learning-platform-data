# Ánh xạ quyền từ cơ sở dữ liệu hoặc claims của hệ thống ngoài

## 1. Bài toán và mục tiêu

Trong Spring Security, **xác thực (authentication)** xác định ai đang gửi yêu cầu, còn **ủy quyền (authorization)** quyết định danh tính đó được làm gì. Một ứng dụng thường lưu quyền ở bảng dữ liệu nội bộ hoặc nhận thông tin nhóm, vai trò, scope từ hệ thống danh tính bên ngoài. Những giá trị như `REPORT_VIEW`, `platform-admin`, `roles`, `groups` hoặc `scope` **không tự động có cùng ý nghĩa** trong Spring Security. Ứng dụng cần chuyển chúng thành các `GrantedAuthority` nhất quán, sau đó mới dùng để kiểm tra truy cập.

Bài học tập trung vào **điểm mở rộng để ánh xạ quyền** trong module *Spring Security - fundamentals*: lựa chọn API phù hợp theo nguồn dữ liệu, chuẩn hóa tên quyền, cấu hình policy, và tránh nâng quyền ngoài ý muốn. Hai đường đi chính:

1. **Dữ liệu ứng dụng**: tài khoản và quan hệ user–role nằm trong cơ sở dữ liệu; `UserDetailsService` tải chúng vào `UserDetails.getAuthorities()` khi xác thực username/password.
2. **Hệ thống danh tính ngoài**: access token đã được xác minh hoặc thông tin user từ OAuth2/OIDC login chứa claims; converter hoặc mapper biến claims thành `GrantedAuthority`.

Kết thúc bài, bạn cần phân biệt được `ROLE_` với `SCOPE_`, viết phép ánh xạ tường minh và có kiểm thử, dùng được ví dụ Java 17+ cho database, hiểu cách cấu hình converter cho JWT, và biết xử lý nguồn quyền kết hợp, thay đổi quyền, multi-tenant và ranh giới tin cậy.

## 2. `GrantedAuthority` là biểu diễn quyền mà Spring Security dùng

Khi một request được xác thực, đối tượng `Authentication` chứa principal và tập `GrantedAuthority`. Những thành phần cấp quyền như `AuthorizationManager` đọc tập authority đó để quyết định. Dạng thường gặp là `SimpleGrantedAuthority`, chứa đúng một chuỗi:

```java
GrantedAuthority reader = new SimpleGrantedAuthority("ROLE_READER");
GrantedAuthority canExport = new SimpleGrantedAuthority("PERM_REPORT_EXPORT");
GrantedAuthority readScope = new SimpleGrantedAuthority("SCOPE_reports.read");
```

Ba chuỗi ở trên **khác nhau hoàn toàn**. Spring Security không tự suy ra `ROLE_READER` từ `reader`, không tự quy đổi `scope=reports.read` thành `ROLE_READER`, và không mặc định hiểu tên nhóm của identity provider. Quy tắc mapping phải có chủ đích.

| Giá trị trong nguồn | Authority mong muốn | Policy phù hợp | Ghi chú |
| --- | --- | --- | --- |
| Vai trò DB `REPORT_VIEW` | `ROLE_READER` | `hasRole("READER")` | `hasRole` mặc định thêm tiền tố `ROLE_` |
| Vai trò DB `OPS_ADMIN` | `ROLE_ADMIN` | `hasRole("ADMIN")` | Đừng gọi `hasRole("ROLE_ADMIN")` |
| Quyền chi tiết `EXPORT_REPORT` | `PERM_REPORT_EXPORT` | `hasAuthority("PERM_REPORT_EXPORT")` | Dùng chuỗi chính xác, không tự thêm tiền tố |
| OAuth2 scope `reports.read` | `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` | Resource Server thường ánh xạ `scope`/`scp` với tiền tố `SCOPE_` |
| Claim nhóm `app_roles=["report_view"]` | `ROLE_READER` nếu đã xác minh, được cho phép | `hasRole("READER")` | Phải có converter/mapper theo quy tắc ứng dụng |

**Vì sao phân biệt role và authority?** Trong Spring Security, role là một quy ước tên trên nền authority. Với mặc định, `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` kiểm tra đúng cùng chuỗi, còn `hasAuthority("ADMIN")` kiểm tra chuỗi khác. Tiền tố role có thể được cấu hình khác, nên thống nhất quy ước trong từng dự án và kiểm thử cấu hình thực tế.

**Không nhầm identity với authority:** `sub`, email, username, tenant ID và user ID xác định tài khoản/đối tượng; chúng không tự chứng minh quyền quản trị. Một claim có tên `isAdmin` cũng không đáng tin nếu chưa xác minh issuer, token, audience và quy tắc cấp quyền của hệ thống phát hành.

## 3. Luồng dữ liệu: nguồn quyền → mapping → authorization

```text
A. Username/password và cơ sở dữ liệu
HTTP Basic / Form Login
       │
       ▼
DaoAuthenticationProvider → UserDetailsService
       │                    ├─ app_user
       │                    └─ app_user_role + app_role
       ▼
UserDetails với GrantedAuthority[]
       │
       ▼
Authentication / SecurityContext
       │
       ▼
authorizeHttpRequests / @PreAuthorize
       │
       ├─ Có authority yêu cầu  → cho phép
       └─ Thiếu authority      → từ chối


B. OAuth2 Resource Server với JWT
Authorization: Bearer <access-token>
       │
       ▼
JwtDecoder: kiểm chữ ký, issuer, exp/nbf, validator liên quan
       │
       ▼
JwtAuthenticationConverter
       ├─ scope/scp → SCOPE_...
       └─ app_roles → ROLE_... theo allowlist của ứng dụng
       │
       ▼
JwtAuthenticationToken với GrantedAuthority[]
       │
       ▼
authorizeHttpRequests / @PreAuthorize
```

Hai pipeline trên có thể tạo ra cùng một authority (chẳng hạn `ROLE_READER`), nhưng dùng **điểm mở rộng khác nhau**. `UserDetailsService` không tự được gọi chỉ vì request chứa JWT; `JwtAuthenticationConverter` không tự xử lý form login hay database username/password. Với OAuth2/OIDC **đăng nhập trình duyệt**, `GrantedAuthoritiesMapper` và `OAuth2UserService`/`OidcUserService` lại là một luồng khác với Resource Server nhận access token.

Có ba bước cần kiểm chứng riêng:

1. **Xác minh nguồn dữ liệu**: user có thực, password được kiểm đúng; JWT có chữ ký/issuer/audience hợp lệ; thuộc tính từ UserInfo được trả bởi provider đáng tin.
2. **Ánh xạ có kiểm soát**: đầu vào đúng kiểu, tên được chuẩn hóa theo bảng ánh xạ, giá trị không được nhận diện không được nâng thành quyền.
3. **Áp dụng policy**: endpoint/method yêu cầu đúng authority đã tạo; thiếu quyền phải bị từ chối.

## 4. Thiết kế bảng ánh xạ trước khi viết mã

Giả sử ứng dụng nội bộ có hai vai trò trong bảng `app_role`, còn hệ thống danh tính ngoài phát claim `app_roles`:

| Nguồn | Giá trị nguồn | Authority nội bộ | Ý nghĩa |
| --- | --- | --- | --- |
| Database `app_role.external_code` | `REPORT_VIEW` | `ROLE_READER` | Được xem báo cáo |
| Database `app_role.external_code` | `OPS_ADMIN` | `ROLE_ADMIN` | Được quản trị API nội bộ |
| JWT claim `app_roles` | `report_view` | `ROLE_READER` | Quyền xem từ issuer được tin cậy |
| JWT claim `app_roles` | `ops_admin` | `ROLE_ADMIN` | Quyền quản trị từ issuer được tin cậy |
| JWT claim `scope` | `reports.read` | `SCOPE_reports.read` | Quyền OAuth2 do provider cấp |

Bảng này là **hợp đồng** giữa nguồn dữ liệu và ứng dụng. `OPS_ADMIN` trong DB không buộc phải trùng `ops_admin` trong JWT; cả hai chỉ có thể quy về `ROLE_ADMIN` vì nghiệp vụ cho phép và đã xác định chủ thể phát quyền.

Nên xác định thêm: ai được thay đổi giá trị nguồn, tenant nào áp dụng, claims nào được chấp nhận, quyền có hiệu lực khi nào, nguồn nào thắng khi mâu thuẫn, và quyền sẽ bị thu hồi sau bao lâu. Nếu không có bảng rõ ràng, việc nối `"ROLE_" + value` vào chuỗi bất kỳ rất dễ tạo ra quyền chưa được phê duyệt.

**Fail closed:** nếu giá trị nguồn không hợp lệ hoặc nằm ngoài danh sách được hỗ trợ, lựa chọn an toàn là không cấp authority đó; với dữ liệu cấu hình nội bộ bất nhất, có thể chủ động từ chối đăng nhập và ghi lỗi cho quản trị viên. Không tự “sửa” `role=superuser` thành một role cao cấp hơn.

## 5. Ví dụ A — ứng dụng Java 17+ lấy quyền từ cơ sở dữ liệu

Ví dụ đầy đủ dùng **Spring Boot 3.5.7**, **Spring Security 6.x**, Spring MVC/Servlet, H2 in-memory và JDBC. Nó mô phỏng mô hình user–role của ứng dụng thật để giải thích phần mapping. HTTP Basic giúp kiểm thử quyền bằng `curl`. Trong dự án production, có thể thay H2 bằng PostgreSQL/MySQL, giữ cùng nguyên tắc.

### 5.1. Yêu cầu cụ thể

- `GET /public`: ai cũng có thể xem.
- `GET /reports`: cần `ROLE_READER`.
- `GET /admin`: cần `ROLE_ADMIN`.
- Tài khoản `alice` có role DB `REPORT_VIEW`, map sang `ROLE_READER`.
- Tài khoản `bob` có role DB `OPS_ADMIN`, map sang `ROLE_ADMIN`.
- Không tạo custom security filter và không tự so sánh mật khẩu trong controller.

Cấu trúc dự án:

```text
db-authorities-demo/
├── pom.xml
└── src/main/
    ├── java/demo/DbAuthoritiesApplication.java
    └── resources/
        ├── application.yml
        └── schema.sql
```

### 5.2. Maven: `pom.xml`

```xml
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

    <groupId>demo</groupId>
    <artifactId>db-authorities-demo</artifactId>
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
```

### 5.3. Kết nối H2: `src/main/resources/application.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:rolesdemo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always
```

Database `rolesdemo` chỉ tồn tại trong runtime demo; dữ liệu demo mất khi ứng dụng dừng. Không dùng H2 in-memory cho dữ liệu tài khoản production.

### 5.4. Lược đồ: `src/main/resources/schema.sql`

```sql
CREATE TABLE app_user (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE app_role (
    external_code VARCHAR(50) PRIMARY KEY
);

CREATE TABLE app_user_role (
    user_id BIGINT NOT NULL,
    role_code VARCHAR(50) NOT NULL,
    PRIMARY KEY (user_id, role_code),
    FOREIGN KEY (user_id) REFERENCES app_user(id),
    FOREIGN KEY (role_code) REFERENCES app_role(external_code)
);

INSERT INTO app_role (external_code) VALUES ('REPORT_VIEW');
INSERT INTO app_role (external_code) VALUES ('OPS_ADMIN');
```

Tách `app_user`, `app_role` và bảng nối giúp biểu diễn **một user có nhiều role**. Trong ví dụ, mỗi user chỉ được gán một role để kiểm tra phép ánh xạ dễ dàng; code phía dưới vẫn đọc danh sách nhiều role.

### 5.5. Ứng dụng chính: `src/main/java/demo/DbAuthoritiesApplication.java`

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DbAuthoritiesApplication {

    public static void main(String[] args) {
        SpringApplication.run(DbAuthoritiesApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(JdbcTemplate jdbc) {
        return username -> {
            List<DbUser> users = jdbc.query(
                    "SELECT id, username, password_hash, enabled "
                    + "FROM app_user WHERE username = ?",
                    (rs, rowNum) -> new DbUser(
                            rs.getLong("id"),
                            rs.getString("username"),
                            rs.getString("password_hash"),
                            rs.getBoolean("enabled")),
                    username);

            if (users.isEmpty()) {
                throw new UsernameNotFoundException("User not found");
            }

            DbUser user = users.get(0);

            List<GrantedAuthority> authorities = jdbc.query(
                    "SELECT r.external_code "
                    + "FROM app_role r "
                    + "JOIN app_user_role ur "
                    + "  ON ur.role_code = r.external_code "
                    + "WHERE ur.user_id = ?",
                    (rs, rowNum) -> new SimpleGrantedAuthority(
                            mapDatabaseRole(rs.getString("external_code"))),
                    user.id());

            UserDetails details = User.withUsername(user.username())
                    .password(user.passwordHash())
                    .disabled(!user.enabled())
                    .authorities(authorities)
                    .build();
            return details;
        };
    }

    private static String mapDatabaseRole(String externalRole) {
        return switch (externalRole) {
            case "REPORT_VIEW" -> "ROLE_READER";
            case "OPS_ADMIN" -> "ROLE_ADMIN";
            default -> throw new IllegalArgumentException(
                    "Unmapped database role: " + externalRole);
        };
    }

    @Bean
    CommandLineRunner seedDemoUsers(
            JdbcTemplate jdbc, PasswordEncoder encoder) {
        return args -> {
            jdbc.update(
                    "INSERT INTO app_user(username, password_hash, enabled) "
                    + "VALUES (?, ?, ?)",
                    "alice", encoder.encode("alice-pass"), true);

            jdbc.update(
                    "INSERT INTO app_user(username, password_hash, enabled) "
                    + "VALUES (?, ?, ?)",
                    "bob", encoder.encode("bob-pass"), true);

            jdbc.update(
                    "INSERT INTO app_user_role(user_id, role_code) "
                    + "SELECT id, ? FROM app_user WHERE username = ?",
                    "REPORT_VIEW", "alice");

            jdbc.update(
                    "INSERT INTO app_user_role(user_id, role_code) "
                    + "SELECT id, ? FROM app_user WHERE username = ?",
                    "OPS_ADMIN", "bob");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/reports").hasRole("READER")
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    private record DbUser(
            long id, String username, String passwordHash, boolean enabled) {}

    @RestController
    static class ApiController {
        @GetMapping("/public")
        String publicEndpoint() {
            return "public";
        }

        @GetMapping("/reports")
        String reports() {
            return "reports";
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
```

Điểm quan trọng về **cách Spring Security sử dụng dữ liệu**:

- `JdbcTemplate` lấy user qua placeholder `?`, tránh nối `username` vào câu SQL. User và các role được tra cứu từ bảng riêng.
- `mapDatabaseRole(...)` là điểm ánh xạ **từ mã role nghiệp vụ sang authority nội bộ**. Việc chọn `switch` allowlist làm các giá trị mới không vô tình được cấp `ROLE_ADMIN`. Với dữ liệu quản trị thực, log có kiểm soát và xử lý cấu hình sai theo quy trình vận hành.
- `UserDetailsService` chỉ chịu trách nhiệm tải user; `DaoAuthenticationProvider` của Spring Security xử lý bước kiểm mật khẩu qua `PasswordEncoder`. Password hash do BCrypt tạo ra khi seed demo; controller không chạm vào mật khẩu.
- `User.withUsername(...).authorities(authorities)` gắn quyền với user đã xác thực. `hasRole("READER")` kiểm tra `ROLE_READER`, và `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN`.
- Bean `SecurityFilterChain` giữ toàn bộ cơ chế xác thực/ủy quyền trong framework. `formLogin` bị tắt riêng để demo dùng HTTP Basic trả 401; **không tắt CSRF** trong ví dụ chỉ có GET.
- Dữ liệu seed gồm mật khẩu dạng rõ trong **mã minh họa**, tuyệt đối không dùng cách này để quản lý secrets cho production. Trong hệ thống thật, hash được tạo tại bước đăng ký/đổi mật khẩu, lưu trong DB và không trả về API.

Nếu database schema đã theo cấu trúc được `JdbcUserDetailsManager` hỗ trợ, có thể sử dụng manager chuẩn và chỉnh truy vấn khi phù hợp. Custom `UserDetailsService` chỉ cần thiết khi schema hoặc quy tắc mapping đặc thù; **không cần viết custom AuthenticationProvider chỉ để JOIN bảng user–role**.

### 5.6. Chạy và kiểm tra kết quả

Yêu cầu Java 17+, Maven, và sử dụng thư mục chứa `pom.xml`:

```bash
mvn -q -DskipTests package
java -jar target/db-authorities-demo-0.0.1-SNAPSHOT.jar
```

Trong terminal khác, chạy:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/reports
curl -i -u alice:alice-pass http://localhost:8080/reports
curl -i -u alice:alice-pass http://localhost:8080/admin
curl -i -u bob:bob-pass http://localhost:8080/admin
curl -i -u bob:bob-pass http://localhost:8080/reports
curl -i -u alice:wrong http://localhost:8080/reports
```

| Request | HTTP status mong đợi | Vì sao |
| --- | --- | --- |
| `/public`, anonymous | **200**; body `public` | `permitAll` |
| `/reports`, anonymous | **401** | Chưa xác thực |
| `/reports`, `alice` | **200**; body `reports` | DB `REPORT_VIEW` → `ROLE_READER` |
| `/admin`, `alice` | **403** | Không có `ROLE_ADMIN` |
| `/admin`, `bob` | **200**; body `admin` | DB `OPS_ADMIN` → `ROLE_ADMIN` |
| `/reports`, `bob` | **403** | Trong demo, ADMIN không tự bao gồm READER |
| `/reports`, sai mật khẩu | **401** | Xác thực thất bại trước khi xét quyền |

**Quan sát có ý nghĩa:** `ROLE_ADMIN` không mặc nhiên kế thừa `ROLE_READER`. Nếu muốn “ADMIN cũng được đọc báo cáo”, phải chọn policy `hasAnyRole("READER", "ADMIN")` hoặc cấu hình role hierarchy có kiểm soát. Đừng mặc định vai trò cao bao hàm mọi vai trò thấp.

**Giới hạn ví dụ:** H2 chỉ mô phỏng database, không đại diện cho connection pooling, phân quyền truy vấn hay tốc độ môi trường thật; cũng chưa có audit, lockout, migration, kiểm thử tự động. Ví dụ dùng để minh họa chính xác chỗ biến role từ DB thành `GrantedAuthority`.

## 6. Tối ưu và củng cố ánh xạ từ database

### 6.1. Không để truy vấn quyền trở thành lỗi bảo mật hoặc nút thắt

Một ứng dụng nhiều user/role nên quan tâm:

- Index và khóa unique trên username, khóa liên kết user–role; truy vấn tham số hóa.
- Không trả trực tiếp bản ghi DB hoặc password hash ra HTTP response; `UserDetails` có thể chứa thông tin xác thực nhạy cảm.
- Mapping code theo **đúng nguồn dữ liệu có quản trị**. Nếu role bị thiếu hoặc sai định dạng, không được tự cấp quyền mặc định quá rộng.
- Trạng thái tài khoản: disabled, locked, expired, credentials-expired nếu có trong schema phải được phản ánh vào `UserDetails` tương ứng.
- Cache user/authorities nếu thực sự cần: quy định TTL và cơ chế invalidation khi quyền bị đổi. Session hoặc cache có thể giữ authority cũ đến khi xác thực lại.
- Việc thay đổi role trong database **không đảm bảo mọi phiên đang tồn tại lập tức đổi quyền**. Thiết kế cách refresh/revoke session hoặc policy tra cứu quyền khi yêu cầu độ tươi cao.

### 6.2. Role rộng và permission chi tiết

`ROLE_ADMIN` phù hợp với vai trò tổ chức; một ứng dụng nhiều chức năng có thể cần permission chi tiết như `INVOICE_APPROVE` hoặc `REPORT_EXPORT`. Có thể map DB table permission sang `PERM_INVOICE_APPROVE` rồi kiểm tra `hasAuthority("PERM_INVOICE_APPROVE")`.

Không biến hàng nghìn ID đối tượng (ví dụ `invoice:12345`) thành hàng nghìn `GrantedAuthority`. Kiểm tra quyền sở hữu thực tế của bản ghi tại service/repository, gắn với subject và tenant đang truy cập. Ví dụ quy tắc “chỉ đọc hóa đơn của chính mình” không thể được giải quyết đúng chỉ bằng `ROLE_READER`.

### 6.3. Dữ liệu nhiều tenant

Nếu hai tổ chức cùng dùng role `ADMIN`, authority `ROLE_ADMIN` chung có thể quá rộng nếu code không kiểm tra tenant. Với quyền theo tenant, cách an toàn là xác định `tenantId` từ nguồn đáng tin rồi kiểm tra tenant và object owner trong lớp nghiệp vụ, hoặc sử dụng thiết kế authority có namespace rõ ràng kèm authorization logic chuyên biệt. **Không** lấy mỗi header `X-Tenant-Id` do client tự gửi làm căn cứ cấp role.

## 7. Ví dụ B — ánh xạ scope và claim quyền trong JWT đã xác minh

Đây là **pipeline khác với ví dụ database**: API nhận `Authorization: Bearer ...`, Spring Security đóng vai trò OAuth2 **Resource Server**. Access token mang claims do nhà phát hành xác thực kiểm soát.

Ví dụ payload minh họa sau là dữ liệu *bên trong* một JWT; **đọc được JSON không có nghĩa token hợp lệ**:

```json
{
  "iss": "https://idp.example.org/realms/sample",
  "sub": "person-42",
  "aud": ["reports-api"],
  "exp": 1893456000,
  "scope": "reports.read",
  "app_roles": ["report_view", "ops_admin", "unknown_role"]
}
```

Giả sử issuer được tin cậy và ứng dụng thật sự cho phép issuer đó quản lý claim `app_roles`. Mục tiêu mapping:

- `scope: "reports.read"` → giữ quyền chuẩn `SCOPE_reports.read`.
- `app_roles: "report_view"` → cấp thêm `ROLE_READER`.
- `app_roles: "ops_admin"` → cấp thêm `ROLE_ADMIN`.
- `"unknown_role"` → **không cấp** authority; không nối prefix vào giá trị lạ.

Lưu ý `sub` là định danh chủ thể tại issuer, không nhất thiết trùng username hoặc user ID tại DB. Trong nhiều hệ thống, một subject phải được định danh bằng cặp `issuer + sub` để tránh đụng nhau giữa các nhà phát hành.

### 7.1. Phụ thuộc và xác minh JWT bằng Spring Security

Trong ứng dụng Spring Boot Servlet cần `spring-boot-starter-security` và `spring-boot-starter-oauth2-resource-server` (cùng web starter). Starter Resource Server cung cấp hỗ trợ xử lý Bearer token và xác minh JWT thông qua các thư viện Spring Security tương ứng.

Ví dụ **`application.yml` trong dự án Resource Server riêng**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/sample
```

URI ở đây là **địa chỉ minh họa, không phải một IdP hoạt động**. Thay bằng issuer thực tế và cấu hình validation thích hợp trước khi chạy end-to-end. Resource Server xử lý việc tải khóa công khai từ metadata/JWK Set và xác minh token theo cấu hình; việc tùy biến authority **không** thay cho xác minh token.

Các checks cần xác nhận:

1. **Signature và thuật toán** được xác minh bằng khóa, thuật toán phù hợp.
2. `iss` khớp issuer được cho phép; `exp`, `nbf` hợp lệ.
3. `aud` khớp API đích khi hệ thống yêu cầu audience cụ thể. **Chỉ khai báo `issuer-uri` không đồng nghĩa đã cấu hình mọi quy tắc audience của ứng dụng.**
4. Token thật sự là **access token** dùng cho resource server; không lấy ID token dành cho client/OIDC login để gọi API.
5. Claim role được quản trị bởi issuer đáng tin; không dùng thông tin roles lấy từ header do client tự điền hoặc từ JWT chưa kiểm chữ ký.

### 7.2. Chọn đúng converter

`JwtGrantedAuthoritiesConverter` mặc định đọc scope phổ biến (`scope` hoặc `scp`) và tạo các authority bắt đầu bằng `SCOPE_`. Để đổi riêng tên claim, API có `setAuthoritiesClaimName(...)`; để đổi prefix, có `setAuthorityPrefix(...)`; với dữ liệu dạng chuỗi, có thể tùy chọn delimiter. Nhưng **thay converter chuẩn bằng converter chỉ đọc `app_roles` có thể làm mất quyền `SCOPE_...`**. Nếu API sử dụng cả scope và role, hãy ghép hai tập với quy tắc minh bạch.

Ví dụ toàn bộ class cấu hình sau áp dụng cho **một ứng dụng Spring MVC Resource Server**, là lựa chọn thay thế cho `SecurityFilterChain` HTTP Basic ở mục 5, không để hai bean chồng nhau trong cùng demo:

**`src/main/java/demo/JwtAuthoritySecurityConfig.java`**:

```java
package demo;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JwtAuthoritySecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers("/api/reports")
                            .hasAuthority("SCOPE_reports.read")
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(jwt -> jwt.jwtAuthenticationConverter(
                                jwtAuthenticationConverter())))
                .build();
    }

    public static JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter standardScopes =
                new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Set<GrantedAuthority> authorities = new LinkedHashSet<>();

            Collection<GrantedAuthority> scopes =
                    standardScopes.convert(jwt);
            if (scopes != null) {
                authorities.addAll(scopes);
            }

            Object claim = jwt.getClaim("app_roles");
            if (claim instanceof Collection<?> rawRoles) {
                for (Object rawRole : rawRoles) {
                    if (!(rawRole instanceof String role)) {
                        continue;
                    }
                    switch (role) {
                        case "report_view" -> authorities.add(
                                new SimpleGrantedAuthority("ROLE_READER"));
                        case "ops_admin" -> authorities.add(
                                new SimpleGrantedAuthority("ROLE_ADMIN"));
                        default -> {
                            // Giá trị ngoài allowlist không cấp quyền.
                        }
                    }
                }
            }

            return authorities;
        });

        return converter;
    }
}
```

**Đọc cơ chế theo thứ tự:**

- `JwtDecoder` của Resource Server phải xác minh token trước; converter nhận một đối tượng `Jwt` đã đi qua quá trình giải mã/kiểm tra khi request thực sự được xử lý. Tự gọi converter với JWT mock trong unit test chỉ kiểm tra mapping, không chứng minh token hợp lệ.
- `standardScopes.convert(jwt)` giữ mặc định `SCOPE_reports.read`. `LinkedHashSet` loại authority trùng mà vẫn giữ thứ tự ổn định khi cần quan sát.
- Claim `app_roles` được kỳ vọng là collection. Nếu claim vắng mặt, sai kiểu hoặc có phần tử lạ, code **không** cấp role tương ứng.
- `JwtAuthenticationConverter` tạo `Authentication` có tập authorities mới; policy kiểm tra `hasAuthority("SCOPE_reports.read")` hoặc `hasRole("ADMIN")` theo chuỗi thực tế.
- Ví dụ cố ý không tự đổi claims `sub`/`iss`, không tự parse chữ ký, không tự ghi `SecurityContextHolder`.
- Chưa bật role hierarchy: `ROLE_ADMIN` không tự bao gồm `ROLE_READER`, cũng không thay cho `SCOPE_reports.read`.

**Quan hệ giữa role và scope cần được thiết kế:** trong ví dụ `/api/reports` yêu cầu scope, nên chỉ `ROLE_ADMIN` cũng chưa đủ. Nếu một endpoint cần **cả** scope và role, viết authorization rule kết hợp hoặc method security phù hợp; nếu chỉ cần một trong hai, policy phải thể hiện rõ. Không coi chúng đồng nghĩa.

### 7.3. Kiểm thử mapping mà không cần IdP thật

Trong dự án Resource Server, thêm `spring-boot-starter-test` với scope `test`. Tập tin test sau chỉ đánh giá **hàm mapping**, không phát sinh token được ký, không gửi HTTP và không kiểm tra chữ ký:

**`src/test/java/demo/JwtAuthoritySecurityConfigTest.java`**:

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class JwtAuthoritySecurityConfigTest {

    @Test
    void mapsKnownRolesAndPreservesScopes() {
        Jwt jwt = Jwt.withTokenValue("mapping-fixture")
                .header("alg", "RS256")
                .claim("sub", "person-42")
                .claim("scope", "reports.read")
                .claim("app_roles", List.of(
                        "report_view", "ops_admin", "unknown_role"))
                .build();

        var authentication = JwtAuthoritySecurityConfig
                .jwtAuthenticationConverter()
                .convert(jwt);

        assertThat(authentication).isNotNull();
        List<String> names = authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .toList();

        assertThat(names).containsExactlyInAnyOrder(
                "SCOPE_reports.read",
                "ROLE_READER",
                "ROLE_ADMIN");
    }

    @Test
    void unknownRoleDoesNotBecomeAuthority() {
        Jwt jwt = Jwt.withTokenValue("mapping-fixture")
                .header("alg", "RS256")
                .claim("sub", "person-42")
                .claim("app_roles", List.of("superuser"))
                .build();

        var authentication = JwtAuthoritySecurityConfig
                .jwtAuthenticationConverter()
                .convert(jwt);

        assertThat(authentication).isNotNull();
        assertThat(authentication.getAuthorities()).isEmpty();
    }
}
```

Chạy `mvn test` trong dự án đã có phụ thuộc test. Kết quả mong đợi: cả hai test pass. Test thứ nhất đảm bảo scope không bị mất và role lạ không được cấp; test thứ hai chứng minh `superuser` không tự biến thành authority nào. Với bảo mật production cần thêm **integration tests** cho token có chữ ký hợp lệ/sai, issuer sai, audience sai, token hết hạn và HTTP 401/403. Đừng xem fixture `Jwt.withTokenValue(...)` là một bằng chứng xác minh chữ ký.

### 7.4. Những kiểu claim khác nhau

Một vài hệ thống dùng:

- `scope: "read write"` hoặc `scp: ["read", "write"]` để thể hiện OAuth2 scopes.
- `roles: ["ADMIN", "READER"]` hoặc `groups: ["analytics", "admins"]`.
- `realm_access.roles`, `resource_access.<client>.roles` hoặc cấu trúc JSON lồng nhiều cấp (phụ thuộc provider).

`JwtGrantedAuthoritiesConverter` phù hợp với claim trực tiếp và quy tắc prefix đơn giản. Với JSON lồng hoặc mapping cần kiểm tra tenant/nguồn, dùng `Converter<Jwt, Collection<GrantedAuthority>>` như ví dụ, xử lý kiểu dữ liệu cụ thể và allowlist. Đừng viết converter mặc định gán `ROLE_ADMIN` vì bất kỳ claim nào chứa chữ “admin”.

Nếu issuer dùng claim tên `roles` và giá trị được quản trị thống nhất, một converter tối giản có thể là:

```java
JwtGrantedAuthoritiesConverter roles = new JwtGrantedAuthoritiesConverter();
roles.setAuthoritiesClaimName("roles");
roles.setAuthorityPrefix("ROLE_");
```

Đoạn trên **chỉ map claim roles** nếu dùng thay converter mặc định; để tiếp tục giữ scopes, cần kết hợp converter với mapping scope như ví dụ đầy đủ.

## 8. OAuth2/OIDC login: điểm mở rộng khác Resource Server

`oauth2Login` dùng để **đăng nhập người dùng qua provider** vào ứng dụng client. Sau login, principal có thể là `OAuth2User` hoặc `OidcUser`; authorities có thể bao gồm `OAuth2UserAuthority` / `OidcUserAuthority` cùng các authority scope. Spring Security cung cấp hai hướng ánh xạ:

1. `GrantedAuthoritiesMapper` khi đã có authorities/attributes/id token từ quá trình login.
2. `OAuth2UserService` hoặc `OidcUserService` tùy biến/delegating nếu phải gọi thêm một API hoặc database để lấy quyền, vì chúng nhận được request/access token và có thể tổ chức dữ liệu trước khi tạo principal.

Ví dụ **bean minh họa gắn trong ứng dụng có `oauth2Login`**, không phải chương trình Java độc lập:

```java
@Bean
GrantedAuthoritiesMapper loginAuthoritiesMapper() {
    return incoming -> {
        Set<GrantedAuthority> mapped = new HashSet<>(incoming);

        for (GrantedAuthority authority : incoming) {
            if (authority instanceof OidcUserAuthority oidc) {
                Object value = oidc.getIdToken()
                        .getClaims().get("groups");

                if (value instanceof Collection<?> groups
                        && groups.contains("reporting-team")) {
                    mapped.add(new SimpleGrantedAuthority("ROLE_READER"));
                }
            }
        }
        return mapped;
    };
}
```

Đoạn này cần các import `GrantedAuthoritiesMapper`, `GrantedAuthority`, `SimpleGrantedAuthority`, `OidcUserAuthority`, `Set`, `HashSet`, `Collection`; cần provider thực sự phát `groups` trong **ID token** và ứng dụng chỉ cấp role khi issuer/claim được tin cậy. Không phải provider nào cũng cung cấp `groups` trong ID token; có thể nằm ở UserInfo hoặc dịch vụ quyền riêng. Trong tình huống đó, kiểm tra `OidcUserService`/`OAuth2UserService` và mapping dựa trên đúng dữ liệu trả về. Đừng giả định mọi login đều có OIDC ID token.

**Điểm khác cốt yếu:** `GrantedAuthoritiesMapper` cho `oauth2Login` không tự áp dụng cho `JwtAuthenticationToken` của Resource Server. Nếu API đang dùng Bearer JWT, hãy chỉnh `JwtAuthenticationConverter` như mục 7. Đừng lấy `groups` từ unverified JWT hoặc HTTP header để cấp quyền.

## 9. Nếu quyền nằm ở cả database và hệ thống ngoài thì làm gì?

Ví dụ: IdP chỉ xác minh user, còn quyền dự án do ứng dụng quản lý trong database. Hãy thiết kế rõ nguồn nào có thẩm quyền:

| Mô hình | Nguồn identity | Nguồn authority | Đổi quyền có hiệu lực |
| --- | --- | --- | --- |
| Database local | Bảng user + mật khẩu / provider nội bộ | DB roles/permissions | Khi authority được nạp lại, phụ thuộc session/cache |
| JWT tự chứa quyền | Access token được IdP ký | Claims trong JWT | Thường đến lần phát token tiếp theo hoặc cơ chế thu hồi |
| OIDC login + DB | `iss + sub` từ provider tin cậy | DB roles truy vấn theo ID đã liên kết | Khi login/refresh quyền hoặc session tái tạo |
| JWT + truy vấn quyền khi request | JWT xác minh `iss/sub/aud` | DB/local authorization service | Có thể gần realtime nhưng thêm latency và dependency |

**Chọn quy tắc hợp nhất rõ ràng.** Nếu quyền từ IdP và DB đều có, việc lấy hợp (`union`) tự động có thể mở rộng đặc quyền ngoài dự kiến. Có hệ thống cần database làm nguồn duy nhất; có hệ thống cần cả IdP group và role nội bộ (giao của điều kiện); có hệ thống dùng IdP quyết định authentication còn DB quyết định authorization. Hãy mô tả bằng chính sách rõ ràng và kiểm thử trường hợp nguồn mâu thuẫn.

**Liên kết danh tính đúng:** không join quyền chỉ bằng email hiển thị vì email có thể thay đổi hoặc trùng giữa các issuer. Với OIDC, `issuer + subject` thường là khóa liên kết ổn định hơn; trong đa tenant cần bổ sung ranh giới tenant đáng tin. Nếu user chưa được liên kết vào tài khoản nội bộ, mặc định không cấp role cao.

**Thay đổi quyền theo thời gian:** JWT thường giữ claims trong suốt hiệu lực token; session đăng nhập có thể giữ authorities đã cấp; cache `UserDetailsService` có thể giữ dữ liệu cũ. Khi cần thu hồi khẩn cấp, cân nhắc token lifetime, cơ chế revocation/introspection phù hợp, session invalidation hoặc kiểm tra quyền động từ nguồn đáng tin. Không hứa “xóa role trong DB thì mọi token cũ lập tức mất quyền” nếu thiết kế không thực sự bảo đảm.

## 10. Áp dụng tại endpoint và method

Phép ánh xạ chỉ có ý nghĩa khi phần kiểm tra quyền tham chiếu tới đúng chuỗi authority. Ví dụ cấu hình Servlet:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**").hasRole("READER")
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/export/**")
        .hasAuthority("PERM_REPORT_EXPORT")
    .anyRequest().authenticated())
```

Đây là **đoạn thay thế trong `SecurityFilterChain`**, không phải class Java độc lập. Nếu đồng thời dùng `@PreAuthorize` ở service, kích hoạt `@EnableMethodSecurity` trong cấu hình và kiểm tra bằng test. Ví dụ:

```java
@PreAuthorize("hasAuthority('PERM_REPORT_EXPORT')")
public byte[] exportReport(long reportId) {
    // Vẫn phải kiểm tra reportId có thuộc tenant của user hay không.
    // ...
}
```

Role/permission **toàn cục** không thay cho kiểm tra quyền trên **đối tượng cụ thể**. Một người có `ROLE_READER` có thể được quyền xem báo cáo, nhưng chưa chắc được đọc báo cáo của tenant khác. Những điều kiện như owner ID, tenant, trạng thái hóa đơn và phạm vi dự án phải được xác minh ở tầng nghiệp vụ/data access.

Với Spring Method Security dựa trên proxy, lời gọi phương thức nội bộ cùng class (`self-invocation`) có thể không đi qua proxy; không thiết kế kiểm soát quyền quan trọng chỉ dựa vào giả định mọi lời gọi đều được intercept.

## 11. Reactive/WebFlux: dùng cùng nguyên tắc, đổi đúng API

Trong Spring WebFlux, các counterpart thông dụng là:

| Servlet/MVC | Reactive/WebFlux |
| --- | --- |
| `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `JwtAuthenticationConverter` cho Servlet Resource Server | `ReactiveJwtAuthenticationConverter` hoặc `ReactiveJwtAuthenticationConverterAdapter` |
| `OAuth2UserService` / `OidcUserService` | `ReactiveOAuth2UserService` với loại request/user phù hợp |

Ví dụ **phác họa bean cho một ứng dụng WebFlux Resource Server đã cấu hình issuer thật**, dùng adapter để tái sử dụng converter đồng bộ khi mapping thuần in-memory, không gọi blocking I/O:

```java
@Bean
SecurityWebFilterChain reactiveApi(ServerHttpSecurity http) {
    var adapter = new ReactiveJwtAuthenticationConverterAdapter(
            JwtAuthoritySecurityConfig.jwtAuthenticationConverter());

    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/api/reports")
                        .hasAuthority("SCOPE_reports.read")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(jwt -> jwt.jwtAuthenticationConverter(adapter)))
            .build();
}
```

Đây là **mảnh cấu hình minh họa** cần import `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtAuthenticationConverterAdapter` và converter phù hợp từ dự án JWT. Đừng gắn servlet `Filter`/`OncePerRequestFilter` vào WebFlux. Nếu cần truy vấn DB reactive để lấy quyền, dùng repository reactive và một điểm mở rộng hỗ trợ `Mono`/`Flux`; không gọi JDBC/blocking API trong event-loop.

## 12. Các lỗi bảo mật thường gặp khi ánh xạ quyền

1. **Tin claim trước khi verify token:** giải mã Base64 JWT hoặc đọc request header rồi gán role. Phải xác minh chữ ký, issuer, thời gian và audience theo policy, sau đó mới dùng claims.
2. **Nối `ROLE_` với mọi dữ liệu đầu vào:** chuỗi `ADMIN` do nguồn không đáng tin tự gửi có thể tạo `ROLE_ADMIN`. Cần nguồn quyền có thẩm quyền, allowlist và validation.
3. **Đánh đồng `scope` và `role`:** mặc định `SCOPE_reports.read` không thỏa `hasRole("READER")`. Chỉ ánh xạ giữa chúng khi nghiệp vụ định nghĩa rõ.
4. **Thay mapper rồi mất scope mặc định:** converter mới chỉ đọc `app_roles` khiến API cần `SCOPE_...` đột ngột trả 403. Hãy giữ hoặc cố ý loại scopes, và viết test chứng minh.
5. **Hiểu sai tiền tố `ROLE_`:** `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN` theo mặc định, còn `hasAuthority("ADMIN")` cần authority `ADMIN` đúng nguyên dạng.
6. **Trùng username/email giữa các issuer hoặc tenant:** join quyền nhầm tài khoản có thể gây nâng quyền. Dùng khóa định danh đã xác minh và giới hạn tenant.
7. **Tự động gán role cao khi claim trống:** ví dụ không có nhóm thì mặc định ADMIN để “cho chạy”. Hãy fail closed; việc thiếu claim cần được xử lý như thiếu quyền.
8. **Không nghĩ đến thời gian thu hồi:** token hoặc session cũ còn authority dù bảng role đã sửa. Cần chiến lược refresh/revoke cụ thể.
9. **Dựa vào mỗi kiểm tra URL:** bỏ qua kiểm soát quyền đối tượng ở service, dẫn đến đọc dữ liệu của người khác qua ID tùy ý.
10. **Dùng user-defined metadata làm bằng chứng quyền:** custom request parameter `role=admin`, cookie, untrusted header và email chưa verified đều không được tự chuyển thành authority.
11. **Để role hierarchy tự suy diễn không kiểm chứng:** nếu admin cần quyền reader, hãy cấu hình quan hệ minh bạch, kiểm thử chiều quyền, tránh bất ngờ mở rộng truy cập.
12. **Đưa mã quyền/raw claims nhạy cảm vào log hoặc response:** audit nên có thông tin đủ truy vết nhưng không dump token, mật khẩu hay thông tin cá nhân không cần thiết.

## 13. Checklist QA và bài tập

Trước khi triển khai mapping, hãy chứng minh các điều kiện:

- [ ] Bảng ánh xạ từ từng nguồn sang `GrantedAuthority` được định nghĩa, có người quản trị và kiểm thử.
- [ ] Mỗi nguồn role/claim được xác minh, có ranh giới issuer/tenant rõ ràng.
- [ ] Claim thiếu, sai kiểu, role lạ hoặc tài khoản bị vô hiệu hóa không được cấp thêm quyền.
- [ ] `hasRole`, `hasAuthority`, `@PreAuthorize` kiểm tra đúng chuỗi mà converter thực sự tạo.
- [ ] Kết quả với user có nhiều role, không có role, một role bị thu hồi và user thuộc tenant khác được kiểm thử.
- [ ] Khi tùy biến JWT, các `SCOPE_...` mặc định còn tồn tại nếu policy cần.
- [ ] Đã kiểm tra 401 khi không xác thực, 403 khi có danh tính nhưng thiếu quyền; phân biệt lỗi CSRF nếu request thay đổi trạng thái.
- [ ] Có chính sách cập nhật authority sau khi thay đổi DB, group, token hoặc session.
- [ ] Không phân tích JWT thủ công, không cấp role từ input do client tùy ý điền, không lộ credentials qua response/log.

**Tự luyện:**

1. Bảng DB chứa `REPORT_VIEW`, rule là `hasRole("READER")`. Vì sao phải ánh xạ thành `ROLE_READER` thay vì trả nguyên giá trị?
2. JWT mang `scope=reports.read` và `app_roles=["ops_admin"]`. Tại sao chỉ sửa `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName("app_roles")` có thể làm hỏng rule dựa trên scope?
3. Ứng dụng tin hai IdP cùng có user `sub=123`. Điều gì xảy ra nếu tra quyền database chỉ bằng `sub` mà không xét issuer?
4. Admin bị gỡ quyền trong database nhưng một JWT cũ vẫn còn `ops_admin`. Có thể xử lý thu hồi quyền thế nào, và độ trễ của mỗi phương án?
5. Vì sao `GrantedAuthoritiesMapper` của OAuth2 Login không phải điểm hook mặc định cho JWT của Resource Server?
6. Người có `ROLE_READER` có mặc nhiên được đọc mọi bản ghi hóa đơn không? Nếu không, cần thêm loại policy nào?

## 14. Tài liệu tra cứu chính thức

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet OAuth2 Resource Server JWT (6.5)](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html)
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [Spring Security — OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)

**Điểm ghi nhớ:** nguồn quyền có thể nằm ở database, access-token claims hoặc user info của provider; điểm mở rộng phải phù hợp với **đường xác thực**, và phép ánh xạ phải được kiểm soát trước khi policy dùng tập `GrantedAuthority` để cấp quyền.
