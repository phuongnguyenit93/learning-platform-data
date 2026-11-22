# JdbcUserDetailsManager và lược đồ người dùng, quyền

Khi một ứng dụng Spring Security xác thực username/password, bộ máy xác thực cần đọc một tài khoản đáng tin từ kho lưu trữ: username, **password verifier đã mã hóa một chiều**, trạng thái cho phép đăng nhập và các **authorities** do server cấp. Với dữ liệu trong cơ sở dữ liệu quan hệ, Spring Security cung cấp `JdbcDaoImpl` để đọc `UserDetails` qua JDBC và `JdbcUserDetailsManager` để **đọc lẫn quản lý** người dùng theo hợp đồng `UserDetailsManager`.

Điểm cốt lõi của bài này là **hai bảng liên kết `users` và `authorities`, những câu SQL Spring Security mặc định dùng, cách quản lý dữ liệu và giới hạn của lược đồ có sẵn**. Có bean `JdbcUserDetailsManager` chưa có nghĩa tài khoản đã được xác thực: filter tiếp nhận username/password, `DaoAuthenticationProvider` gọi kho người dùng và `PasswordEncoder` kiểm credential, sau đó authorization mới quyết định quyền truy cập tài nguyên.

Bài thuộc phần **Kho tài khoản** trong chủ đề *Spring Security - authentication*. Ví dụ chạy trên **Java 17+, Spring Boot 3.3.x, Spring Security 6.x, Spring JDBC và H2** để thấy chính xác dữ liệu trong bảng tác động tới HTTP authentication ra sao.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt vai trò `JdbcDaoImpl`, `JdbcUserDetailsManager`, `UserDetailsService`, `UserDetailsManager`, `DaoAuthenticationProvider`, `PasswordEncoder` và `DataSource`.
2. Tự tạo hai bảng `users`, `authorities` cùng khóa chính, khóa ngoại và ràng buộc unique phù hợp với default SQL queries.
3. Giải thích ý nghĩa `users.username`, `users.password`, `users.enabled`, `authorities.username`, `authorities.authority` và liên hệ tới `UserDetails`.
4. Dùng `JdbcUserDetailsManager` tạo, cập nhật, xóa, kiểm tồn tại và tải người dùng theo cơ chế quản lý được ủy quyền.
5. Chạy chương trình Spring Boot sử dụng cơ sở dữ liệu H2; quan sát login thành công, sai password, tài khoản disabled và quyền không đủ.
6. Chẩn đoán các lỗi “user không tồn tại”, “không có authority”, SQL sai schema, hash/encoder lệch, role prefix sai, và sự khác biệt giữa login với authorization.
7. Hiểu khi nào cần tùy chỉnh SQL, thêm quyền theo group, hoặc tự triển khai store cho tenant, account lock, password expiration và chính sách nghiệp vụ phức tạp.

## 2. Các lớp làm gì và kết nối thế nào?

| Thành phần | Trách nhiệm cụ thể | Điều không tự thực hiện |
| --- | --- | --- |
| `DataSource` | Cung cấp JDBC connections tới đúng database/schema. | Không biết password người dùng có hợp lệ. |
| `JdbcDaoImpl` | Thực thi các câu SQL để trả `UserDetails` có username, password hash, enabled và authorities. | Không quản lý CRUD tài khoản. |
| `JdbcUserDetailsManager` | Kế thừa `JdbcDaoImpl`, triển khai `UserDetailsManager` để CRUD user/authority và các thao tác quản lý được hỗ trợ. | Không trở thành HTTP login filter chỉ vì được đăng ký bean. |
| `UserDetailsService` | Hợp đồng đọc một user bằng `loadUserByUsername(String)`. | Không tự kiểm raw password từ request. |
| `UserDetailsManager` | Mở rộng `UserDetailsService` cho một số thao tác quản lý user như `createUser`, `updateUser`, `deleteUser` và `userExists`. | Không thay thế toàn bộ quy trình đăng ký, xác nhận email, MFA hoặc quản trị nghiệp vụ. |
| `DaoAuthenticationProvider` | Dùng user store và `PasswordEncoder` kiểm thông tin đăng nhập username/password và trạng thái account. | Không tự tạo database tables hoặc cấp quyền dựa vào request param. |
| `PasswordEncoder` | Lưu/kiểm password verifier bằng `encode` và `matches`. | Không mã hóa TLS, không thực hiện JDBC query. |
| `Authentication` / `SecurityContext` | Mang kết quả principal và authorities được xác thực tới xử lý request. | Không đảm bảo một user có quyền với mọi đối tượng dữ liệu. |

Luồng điển hình trong Spring Security Servlet:

```text
HTTP Basic hoặc form login
     |
     v
Authentication filter tạo UsernamePasswordAuthenticationToken
     |
     v
AuthenticationManager / ProviderManager
     |
     v
DaoAuthenticationProvider
     |
     +--> JdbcUserDetailsManager.loadUserByUsername(username)
     |        |
     |        +--> DataSource/JDBC
     |                | users: username, password, enabled
     |                + authorities: username, authority (nhiều hàng)
     |        |
     |        +--> UserDetails (security view)
     |
     +--> account status + PasswordEncoder.matches(raw, storedHash)
     |
     v
Authentication đã xác thực: principal + authorities
     |
     v
SecurityContext -> Authorization -> Controller/Service
```

**Ranh giới bảo mật:** `users.password` là **encoded password verifier** được lưu trong server-side database, không phải password gốc nhận từ request. `authorities.authority` là giá trị server cấp; không lấy từ header `X-Role`, field JSON `isAdmin` hoặc tham số URL. Một account record tìm thấy trong database **chưa đủ** để tạo `Authentication` thành công.

## 3. Lược đồ mặc định: hai bảng users và authorities

Spring Security cung cấp default DDL cho kho username/password trong resource:

```text
org/springframework/security/core/userdetails/jdbc/users.ddl
```

Mẫu trong tài liệu Spring Security sử dụng `varchar_ignorecase` để mô tả một số kiểu chuỗi; đây là kiểu **phụ thuộc database dialect**, không có sẵn ở mọi RDBMS. Ý tưởng lược đồ logic:

```text
users
  username  PK
  password  encoded verifier
  enabled   boolean

authorities
  username  FK -> users.username
  authority string
  UNIQUE(username, authority)
```

Một user có thể có **nhiều authority**, nên đây là quan hệ 1–N từ `users` sang `authorities`; khóa ghép unique ngăn cấp trùng cùng quyền cho một user. Bảng `authorities` thường không cần thêm bảng `roles` nếu ứng dụng chỉ cần lưu chuỗi `GrantedAuthority`. Role vẫn là một loại authority theo quy ước prefix, ví dụ `ROLE_READER`.

### 3.1 SQL portable cho ví dụ H2 và database hỗ trợ VARCHAR/BOOLEAN

File `src/main/resources/schema.sql`:

```sql
CREATE TABLE users (
    username VARCHAR(100) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(100) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_auth_user
        FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uq_auth_username
        UNIQUE (username, authority)
);
```

DDL này phù hợp với default JDBC queries và chạy với **H2** trong ví dụ. Trong PostgreSQL, MySQL, Oracle hoặc SQL Server, điều chỉnh kiểu, collation, giới hạn độ dài, identity/sequence và migration phù hợp; đặc biệt không copy `varchar_ignorecase` của tài liệu lên mọi RDBMS.

**Giải thích từng cột và constraint:**

| Cột/constraint | Mục đích | Điều cần nhớ |
| --- | --- | --- |
| `users.username` | Khóa nhận diện login trong schema đơn giản. | Chính sách chữ hoa/thường, Unicode, chuẩn hóa và uniqueness phải rõ. |
| `users.password` | Verifier đã `PasswordEncoder.encode(...)`. | Dùng cột đủ dài cho cả prefix `{id}` và encoded password; **không lưu plaintext**. |
| `users.enabled` | Điều kiện active của account. | `false` được diễn giải là disabled trong `UserDetails`. |
| `authorities.username` | Khóa ngoại trỏ tới tài khoản. | Quyền phải thuộc user có thật, tránh bản ghi mồ côi. |
| `authorities.authority` | Một chuỗi authority, ví dụ `ROLE_READER` hoặc `orders:read`. | Không phải boolean “được phép tất cả”; authorization vẫn kiểm endpoint/object. |
| `PRIMARY KEY(users.username)` | Chỉ một record cho mỗi username trong namespace hiện tại. | Multi-tenant có thể cần khóa ghép `(tenant_id, username)`. |
| `UNIQUE(username, authority)` | Không lưu trùng authority cho cùng user. | Tránh duplicate data, hỗ trợ thao tác CRUD và integrity. |
| `FOREIGN KEY` | Ngăn authority tham chiếu tới user không tồn tại. | Khi xóa user, phải xử lý authorities trước hoặc thiết kế cascade rõ ràng. |

**Schema mặc định đơn giản có giới hạn chủ đích:** `users` không có sẵn `id` UUID, `tenant_id`, `locked_until`, `account_expired_at`, `password_changed_at`, `credentials_expired`, MFA fields hay lịch sử trạng thái. `JdbcDaoImpl` mặc định chủ yếu nạp **username, password, enabled và authorities**; không suy ra nó kiểm được account lock và credential expiration chỉ vì giao diện `UserDetails` có các getter đó.

### 3.2 Vì sao cần cả bảng authorities?

Dùng trực tiếp một cột `role` trong `users` chỉ biểu diễn một giá trị và không khớp default authorities query. Khi user có `ROLE_READER` và `orders:read`, bảng được lưu thành hai dòng. Ví dụ minh họa dữ liệu sau khi tạo user:

```text
users
+----------+---------------------+---------+
| username | password            | enabled |
+----------+---------------------+---------+
| alice    | {bcrypt}<hash...>    | true    |
| disabled | {bcrypt}<hash...>    | false   |
+----------+---------------------+---------+

authorities
+----------+-------------+
| username | authority   |
+----------+-------------+
| alice    | ROLE_READER |
| alice    | orders:read |
| disabled | ROLE_READER |
+----------+-------------+
```

**Đây là bảng minh họa, không phải hash thật để dùng đăng nhập.** Dữ liệu hash Bcrypt có salt ngẫu nhiên nên mỗi lần tạo có thể khác nhau. Chuỗi `{bcrypt}` là prefix của `DelegatingPasswordEncoder`, không phải phần mật khẩu người dùng nhập vào.

Trong Javadoc của `UserDetailsService`, `loadUserByUsername` có thể ném `UsernameNotFoundException` **khi không tìm thấy user hoặc user không có `GrantedAuthority`**. Vì vậy user tồn tại trong `users` nhưng không có authority trong `authorities` có thể bị biểu hiện như “not found”. Khi debug hãy kiểm **cả hai bảng**, đừng chỉ `SELECT * FROM users`.

## 4. Default SQL mà JdbcDaoImpl dùng để nạp UserDetails

Với lược đồ mặc định, cơ chế lookup tương đương các câu SQL sau:

```sql
SELECT username, password, enabled
FROM users
WHERE username = ?;

SELECT username, authority
FROM authorities
WHERE username = ?;
```

Dấu `?` là JDBC bind parameter. Hệ thống truyền username qua prepared statement/binding, không nối username trực tiếp vào SQL string. **Không tự xây `"... WHERE username='" + input + "'"`** vì có thể tạo SQL injection.

### 4.1 Hai query phục vụ hai loại dữ liệu

- Query `usersByUsernameQuery` nạp **một user** với username, encoded password, enabled. Dữ liệu phải có cấu trúc/alias mà `JdbcDaoImpl` mong đợi. Nếu query trả nhiều rows cho một username, namespace tài khoản đã không rõ.
- Query `authoritiesByUsernameQuery` nạp **nhiều authority** cho cùng username; dùng chúng dựng `GrantedAuthority` mà `Authentication` nhận sau thành công.
- `JdbcDaoImpl` có cơ chế lấy group authorities riêng khi được bật, xem phần 9. Không bắt buộc tạo group tables nếu ứng dụng không dùng group mode.
- Tên cột, thứ tự cột trả ra và kiểu `enabled` cần phù hợp mapper mặc định. Dùng một alias `enabled` từ biểu thức tùy tiện có thể biến mọi tài khoản thành enabled, gây lỗi chính sách.

### 4.2 Phân biệt query tìm user với query kiểm password

Đây là cách hiểu sai:

```sql
-- Sai về trách nhiệm nếu coi SQL này tự hoàn thành authentication:
SELECT * FROM users WHERE username = ?;
```

SQL tìm được record chỉ cho `UserDetails` chứa verifier; **`PasswordEncoder.matches(rawPassword, storedHash)` mới kiểm credential** trong provider. Nếu người dùng nhập sai password, user vẫn được tìm thấy nhưng không tạo được một authentication hợp lệ.

Không dùng truy vấn so password plaintext trong SQL như `WHERE username=? AND password=?` khi cột chứa password hash thích hợp. Hash với salt/chi phí phải được kiểm qua password encoder theo đúng định dạng.

### 4.3 Độ nhạy của authority

`ROLE_ADMIN`, `ROLE_READER` và `orders:approve` là những chuỗi mang nghĩa do policy của ứng dụng quy định. `JdbcDaoImpl` nạp chúng, **không tự xác nhận tại sao một user được cấp role đó**. Việc cấp/quản lý authority phải nằm ở một workflow có thẩm quyền (admin, approved provisioning, identity sync) và được audit.

- `hasRole("ADMIN")` trong cấu hình mặc định kiểm authority `ROLE_ADMIN`.
- `hasAuthority("orders:read")` kiểm chuỗi đúng bằng `orders:read`.
- `User.withUsername(...).roles("READER")` thêm prefix `ROLE_` khi tạo `UserDetails`.
- Nếu database đã chứa `ROLE_READER`, không thêm prefix lần thứ hai khi load. `JdbcDaoImpl` có tùy chọn role prefix; chỉ dùng khi dữ liệu thực sự cần và hiểu tác động tới authorization.

Một user có `ROLE_READER` chỉ chứng minh hệ thống đã cấp một authority chung; vẫn phải kiểm **quyền trên object** và tenant. Authentication thành công không được đồng nhất với quyền đọc mọi đơn hàng.

## 5. JdbcDaoImpl so với JdbcUserDetailsManager

`JdbcDaoImpl` đã đủ khi yêu cầu chỉ là **load tài khoản để đăng nhập**, còn quy trình đăng ký/quản trị user do một service riêng sở hữu. `JdbcUserDetailsManager` mở rộng để quản lý dữ liệu theo `UserDetailsManager`:

| API/khả năng | Mục đích | Điều cần kiểm trong nghiệp vụ |
| --- | --- | --- |
| `loadUserByUsername(username)` | Nạp security view cho provider. | Username đúng namespace và tồn tại; có authorities. |
| `userExists(username)` | Kiểm username đã có trong kho chưa. | Không dùng một check đơn lẻ làm bảo đảm uniqueness trong truy cập đồng thời. |
| `createUser(userDetails)` | Chèn bản ghi user và authorities theo cấu hình SQL. | Password đã encode, role từ nguồn tin cậy, transaction/constraint. |
| `updateUser(userDetails)` | Cập nhật dữ liệu user/authorities được manager hỗ trợ. | Không ghi đè quyền vô tình; kiểm authorization của người thay đổi. |
| `deleteUser(username)` | Xóa account/authority theo các câu SQL cấu hình. | Quy định foreign key, soft delete, audit, giữ dữ liệu nghiệp vụ liên quan. |
| `changePassword(old,new)` | Thao tác đổi password theo ngữ cảnh user và cấu hình liên quan. | Kiểm current user, encoder, old-password verification, invalidate sessions theo policy. |
| `setUsersByUsernameQuery(...)` | Đổi SQL tìm account hiện hữu. | Query trả đúng username/password/enabled theo mapper. |
| `setAuthoritiesByUsernameQuery(...)` | Đổi SQL tải authorities hiện hữu. | Một hoặc nhiều rows với username/authority. |
| Các `set...Sql(...)` dành cho CRUD | Đổi câu SQL insert/update/delete/check khi schema khác. | Đọc Javadoc theo phiên bản, giữ tính nhất quán dữ liệu khi thay đổi. |

**Không nên dùng `JdbcUserDetailsManager` làm public account administration API**. Nếu endpoint đăng ký gọi `createUser`, backend phải xác thực quyền gọi, validate input, encode password, đặt quyền mặc định ít nhất cần thiết và xử lý conflict/idempotency. Client không được gửi `authorities=["ROLE_ADMIN"]` rồi server sao chép nguyên xi vào DB.

### 5.1 Một thao tác user thường đụng hai bảng

Ví dụ tạo một user với hai authorities cần tối thiểu thao tác lưu user và các dòng authority. Xóa cũng cần bảo đảm authorities được xóa hoặc quản lý FK. Thất bại giữa chừng có thể tạo state không nhất quán; ở service quản lý account thực tế, **xem xét transaction boundary** hoặc dùng cơ chế Spring JDBC/manager với transaction quản trị phù hợp, kiểm rollback bằng integration test.

`JdbcUserDetailsManager` là một công cụ; consistency, audit, policy và transaction ở cấp nghiệp vụ vẫn phải được thiết kế. Không được coi một phương thức CRUD “tự bao trùm mọi workflow đăng ký nhiều hệ thống”.

### 5.2 Với mật khẩu, đầu vào là encoded verifier

Nếu dùng `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, hãy tạo verifier mới bằng `encoder.encode(rawPassword)` rồi đưa vào `UserDetails` trước khi `createUser`. `JdbcUserDetailsManager` không có nghĩa tự băm mật khẩu từ input plaintext. Không lưu `{noop}secret` ngoài demo. Với `updateUser`/`changePassword`, kiểm hợp đồng encoding của phiên bản và service caller để tránh lưu password raw, double-hashing hoặc vô tình bỏ qua xác thực hiện tại.

### 5.3 Kết quả loadUserByUsername

Hợp đồng là trả `UserDetails` hợp lệ hoặc ném `UsernameNotFoundException`. Không bao giờ trả `null` để đánh dấu không có user. Đặc biệt, **user có record trong bảng `users` nhưng không có authority hợp lệ** có thể bị xem là không tìm được user; cần kiểm bảng quyền và group mode.

## 6. Ví dụ chạy được: Spring Boot 3.3.13 + JDBC + H2

Ví dụ tạo một H2 database trong memory, khởi tạo hai bảng bằng `schema.sql`, dùng `JdbcUserDetailsManager` thêm hai tài khoản demo:

- `alice` với `ROLE_READER` và `orders:read`, enabled.
- `disabled` với `ROLE_READER` nhưng `enabled=false`.

HTTP Basic gọi `DaoAuthenticationProvider` kiểm password hash đã lưu. Controller chỉ trả principal/authorities, không trả hash. Cả hai tài khoản đều dùng raw password **local demo** `local-demo-password`, chỉ dành cho môi trường học. Spring Boot 3.3.13 là bản đã phát hành của nhánh 3.3.x, không phải khuyến nghị chọn version EOL cho production mới.

### 6.1 Cấu trúc dự án

```text
jdbc-auth-lesson/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/JdbcAuthLessonApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

File `settings.gradle`:

```groovy
rootProject.name = 'jdbc-auth-lesson'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

**Vì sao cần `spring-boot-starter-jdbc`?** `JdbcDaoImpl` và `JdbcUserDetailsManager` cần JDBC/DataSource; chỉ thêm web/security starter không bảo đảm HikariCP, JDBC support và datasource được cấu hình cho kho user.

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:authlesson;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
spring.sql.init.continue-on-error=false
```

Spring Boot chạy `schema.sql` cho datasource embedded theo cơ chế SQL initialization, trước khi bean runner tạo user. `DB_CLOSE_DELAY=-1` giữ in-memory database tồn tại tới khi process kết thúc (trong JVM hiện tại). **Password trống của user H2 `sa` chỉ dành cho database in-memory dùng để học**, không phải cài đặt production. Tắt H2 console công khai; không gửi password DB thật vào source control.

File `src/main/resources/schema.sql` chính là hai câu `CREATE TABLE` ở mục 3.1. Ví dụ **không** cần thêm `data.sql`, bởi `ApplicationRunner` ở dưới sẽ dùng API quản lý để tạo account có hash hợp lệ.

### 6.2 Mã Java đầy đủ

File `src/main/java/demo/JdbcAuthLessonApplication.java`:

```java
package demo;

import java.util.Map;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.jdbc.JdbcDaoImpl;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JdbcAuthLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcAuthLessonApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    JdbcUserDetailsManager userDetailsManager(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }

    @Bean
    ApplicationRunner seedDemoAccounts(
            JdbcUserDetailsManager users,
            PasswordEncoder encoder) {

        return args -> {
            if (!users.userExists("alice")) {
                UserDetails alice = User.withUsername("alice")
                        .password(encoder.encode("local-demo-password"))
                        .authorities("ROLE_READER", "orders:read")
                        .build();
                users.createUser(alice);
            }

            if (!users.userExists("disabled")) {
                UserDetails disabled = User.withUsername("disabled")
                        .password(encoder.encode("local-demo-password"))
                        .roles("READER")
                        .disabled(true)
                        .build();
                users.createUser(disabled);
            }
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/me").authenticated()
                        .requestMatchers("/api/orders").hasAuthority("orders:read")
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class JdbcDemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, Object> currentUser(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/orders")
    String orders() {
        return "orders-readable";
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin";
    }
}
```

Dòng import `JdbcDaoImpl` không được dùng trực tiếp trong Java class trên; có thể bỏ dòng import đó mà không thay đổi chương trình. Nó chỉ nhắc đến lớp nguồn mà `JdbcUserDetailsManager` kế thừa. Các import còn lại phục vụ đúng bean/filter/controller.

**Tại sao bean manager đủ để xác thực ở ví dụ này?** `JdbcUserDetailsManager` triển khai `UserDetailsService`; khi đây là user service áp dụng và có `PasswordEncoder`, cấu hình username/password thông thường của Spring Security có thể dùng `DaoAuthenticationProvider`. `httpBasic()` cung cấp cơ chế tiếp nhận raw password. Trong dự án có custom `AuthenticationManager`/nhiều `SecurityFilterChain`, phải xác minh manager/filter thực sự nối với user store; thêm bean không tự gắn vào mọi chain.

### 6.3 Chạy và quan sát

Dùng Gradle wrapper của project nếu có:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu chưa có wrapper nhưng đã cài Gradle phù hợp, có thể chạy `gradle bootRun`. **Không thể `javac JdbcAuthLessonApplication.java` đơn lẻ** vì class cần dependency của Spring Boot, Spring Security và JDBC; Gradle giải quyết classpath.

Trên một terminal khác, gửi request:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -u alice:local-demo-password http://localhost:8080/api/me
curl -i -u alice:local-demo-password http://localhost:8080/api/orders
curl -i -u alice:local-demo-password http://localhost:8080/api/admin
curl -i -u disabled:local-demo-password http://localhost:8080/api/me
```

Trong PowerShell, nếu `curl` là alias khác thì dùng `curl.exe`. Đầu ra HTTP chi tiết có thể chứa headers khác nhau theo phiên bản/container; các **kết quả kiểm thử đáng tin** là:

| Request | HTTP kỳ vọng | Ý nghĩa |
| --- | --- | --- |
| `/public` không credential | `200`, body `public` | URL được `permitAll()`. |
| `/api/me` không credential | `401` (HTTP Basic challenge) | Chưa có principal đã xác thực. |
| `alice:wrong` vào `/api/me` | `401` | User được tìm thấy nhưng password match thất bại. |
| `alice:local-demo-password` vào `/api/me` | `200` | Password verifier match; authorities từ JDBC được gán. |
| Alice vào `/api/orders` | `200`, body `orders-readable` | Có authority `orders:read`. |
| Alice vào `/api/admin` | `403` | Authentication thành công nhưng thiếu `ROLE_ADMIN`. |
| `disabled` vào `/api/me` | `401` | `enabled=false` khiến user bị từ chối đăng nhập. |

Body `GET /api/me` với Alice tương đương (thứ tự JSON keys không cố định):

```json
{
  "username": "alice",
  "authorities": ["ROLE_READER", "orders:read"]
}
```

Dù JSON ở endpoint có username và authorities, **nó không được có `password` hay hash của password**. Code chỉ xuất metadata cần thiết. Bcrypt sinh salt ngẫu nhiên nên không được so sánh raw text của hash giữa các lần chạy.

### 6.4 Điều gì đã được xác minh qua ví dụ?

1. Spring Boot tạo `DataSource` H2 và chạy `schema.sql` khi startup.
2. `ApplicationRunner` tạo user/authority bằng `JdbcUserDetailsManager`, password được encode trước.
3. `BasicAuthenticationFilter` chuyển HTTP Basic credentials thành yêu cầu authentication.
4. `DaoAuthenticationProvider`/`JdbcDaoImpl` tải username/hash/enabled/authority rows và kiểm mật khẩu.
5. Nếu thành công, `Authentication` chứa principal và authorities tương ứng.
6. Authorization quyết định `/api/orders` theo `orders:read` và `/api/admin` theo `ROLE_ADMIN`, nên 200 hoặc 403 tùy chính sách.
7. Nếu `enabled=false` hoặc raw password không đúng, request không có kết quả xác thực thành công.

Điểm quan trọng: phương thức `userExists()` ở runner có ích khi chạy code nhiều lần trong cùng database nhưng **không thay được unique constraint hoặc transaction trong hệ thống có concurrency**. Ví dụ không sử dụng cơ chế phân tán hay nhiều instance cùng seed vào một database lâu dài.

## 7. Tùy chỉnh schema khi có bảng account sẵn

Trong ứng dụng thật, bảng hiện có có thể là:

```text
account
  id, tenant_id, login_name, password_hash,
  active, locked_at, ...
account_permission
  account_id, permission_code, ...
```

Nếu muốn tái sử dụng `JdbcDaoImpl`, bạn có thể cấu hình hai câu SQL **read** trả đúng dữ liệu mà mapper mặc định cần:

```java
@Bean
JdbcUserDetailsManager userDetailsManager(DataSource dataSource) {
    JdbcUserDetailsManager manager =
            new JdbcUserDetailsManager(dataSource);

    manager.setUsersByUsernameQuery("""
        SELECT login_name, password_hash, active
        FROM account
        WHERE login_name = ?
        """);

    manager.setAuthoritiesByUsernameQuery("""
        SELECT a.login_name, ap.permission_code
        FROM account a
        JOIN account_permission ap ON ap.account_id = a.id
        WHERE a.login_name = ?
        """);

    return manager;
}
```

**Đây là ví dụ cấu hình SQL read cho schema giả định**, không phải code nguyên vẹn có thể thay vào demo mặc định: muốn dùng schema này phải tạo bảng tương ứng và xử lý multi-tenant. Hai query vẫn lấy một username bind parameter, trả cột theo thứ tự **username/password/enabled** và **username/authority**. Nếu schema có nhiều tenant cùng `login_name`, query chỉ lọc username như trên là **không an toàn**: phải thiết kế subject key/tenant boundary từ nguồn đáng tin trước khi query hoặc dùng `UserDetailsService` phù hợp với multi-tenant architecture.

Quan trọng hơn, **chỉ thay hai query đọc chưa làm CRUD của `JdbcUserDetailsManager` hợp lệ với bảng mới**. Các phương thức `createUser`, `updateUser`, `deleteUser` và `userExists` vẫn có SQL mặc định riêng; muốn quản lý trên schema custom, phải đồng bộ toàn bộ SQL liên quan theo phiên bản API hoặc tách riêng service quản lý user. Không dùng manager với custom read queries rồi kỳ vọng createUser tự ghi vào bảng `account`.

### 7.1 Username, ID và tenant không tự hoán đổi

Default schema coi username là primary key. Trong hệ thống đa tenant, `alice` ở tổ chức A và `alice` ở tổ chức B có thể là hai tài khoản riêng:

```text
(tenant=A, username=alice) -> account #101
(tenant=B, username=alice) -> account #205
```

Một query kiểu `WHERE username = ?` không chọn được đúng account theo tenant. Các hướng thiết kế hợp lý có thể là:

- Key danh tính toàn cục được gán ở server, chẳng hạn `tenant:accountId`, với quy tắc ánh xạ và canonicalization rõ ràng.
- `AuthenticationManagerResolver`/user service phân vùng theo tenant **đã được xác thực/được phép sử dụng**, không tin arbitrary `X-Tenant` do client tự gửi.
- Custom `UserDetailsService` lấy account theo subject/tenant tin cậy, giữ mã account ổn định làm principal ID và trả authorities đúng namespace.

Không dùng query string hoặc request body để đổi tenant rồi tra account khác mà không có kiểm soát ranh giới tin cậy. Authorizations sau login vẫn phải xét tenant và tài nguyên cụ thể.

### 7.2 Chứng cứ nào được phép quyết định enabled?

Mặc định `enabled` là một boolean trong `users`, đủ cho enabled/disabled. Nếu ứng dụng cần xử lý `locked_until`, email chưa xác minh, password age, account expiry hoặc pending review, hãy quyết định:

- Viết query/mapper hoặc custom `UserDetailsService` thể hiện đầy đủ trạng thái trong `UserDetails` và provider/checker phù hợp.
- Tránh ép mọi trạng thái vào một boolean `enabled` rồi đánh mất lý do và vòng đời cần thiết.
- Tách điều kiện **cho phép login** khỏi **quyền thực hiện hành động nghiệp vụ**. Một account có thể login để thanh toán hóa đơn quá hạn dù gói dịch vụ không còn quyền chạy một chức năng.

Không khẳng định mặc định `JdbcDaoImpl` tự tôn trọng `isAccountNonLocked` và `isCredentialsNonExpired` dựa vào các cột không có trong schema. Khi cần, xây custom security adapter và test flags.

## 8. Groups: khi quyền được cấp qua nhóm thay vì từng user

Spring Security JDBC có chế độ quản lý authorities theo **group**. Khi bật group authorities, dữ liệu thường dùng thêm ba bảng:

| Bảng | Nội dung | Quan hệ |
| --- | --- | --- |
| `groups` | ID nhóm và tên nhóm. | Mỗi group có thể có nhiều members và authorities. |
| `group_members` | Username là thành viên của group nào. | Nhiều user liên kết nhiều group. |
| `group_authorities` | Authority được cấp cho một group. | Một group có nhiều authorities. |

Schema nhóm mặc định trong tài liệu:

```sql
CREATE TABLE groups (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    group_name VARCHAR(50) NOT NULL
);

CREATE TABLE group_members (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    group_id BIGINT NOT NULL,
    CONSTRAINT fk_group_members_group
        FOREIGN KEY (group_id) REFERENCES groups(id)
);

CREATE TABLE group_authorities (
    group_id BIGINT NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_group_auth_group
        FOREIGN KEY (group_id) REFERENCES groups(id)
);
```

Trên đây là **DDL nhóm được diễn giải cho H2/SQL phổ thông**, không phải khẳng định byte-for-byte giống resource `users.ddl` của tất cả phiên bản. Cần cân nhắc unique constraints trên memberships và group authorities, khóa ngoại username nếu phù hợp, cùng migration cho database thực tế.

Để lấy authorities từ groups, cấu hình `JdbcDaoImpl` qua `setEnableGroups(true)`; theo thiết kế có thể giữ `enableAuthorities=true` để nạp cả authorities trực tiếp hoặc đặt `setEnableAuthorities(false)` nếu chỉ muốn quyền từ groups. Phải tạo group tables trước khi bật group queries; nếu không, login có thể lỗi SQL dù hai bảng `users/authorities` tồn tại.

Group-based authority **không mặc định đồng nghĩa hệ thống role hierarchy**. Group chỉ là cách lưu/ghép authority; một role có bao hàm role khác hoặc policy ABAC/RBAC nào phụ thuộc cấu hình authorization riêng.

## 9. Quản lý user/authority an toàn trong production

### 9.1 Password hashing và đổi credential

- Dùng `PasswordEncoder` thích hợp (ví dụ `DelegatingPasswordEncoder` với bcrypt hoặc thuật toán password hashing được tổ chức phê duyệt).
- Khi tạo/đổi password, encode từ raw password đúng một lần; dữ liệu `users.password` là hash định dạng nhất quán.
- Không lưu raw password trong logs, query params, audit events, database migration hay sample public.
- Với password reset, tạo recovery flow có hạn, chống replay và xác minh quyền sở hữu; sau reset quyết định invalidate sessions/refresh grants theo policy.
- Khi hash cũ cần migrate, thiết kế upgrade path có kiểm soát; không sửa encoder rồi mặc định toàn bộ dữ liệu cũ vẫn xác thực được.

### 9.2 Quản lý quyền tại nguồn có thẩm quyền

- Chỉ admin/provisioning service có quyền mới được thay `authorities`.
- Cấp quyền ít nhất cần thiết; mọi thay đổi cần audit (ai, hành động, thời điểm, tenant, phạm vi).
- Cấm client truyền `ROLE_ADMIN` trong form rồi mapper tự lưu.
- Khi quyền bị thu hồi, xét cache `UserDetails` và security session còn lưu authority cũ; database update **không tự thay đổi mọi session/JWT đã cấp**.
- Kiểm race conditions trong việc cấp/xóa quyền, nhất là thao tác của nhiều admin hoặc nhiều service đồng thời.

### 9.3 Transaction, uniqueness và concurrency

Một user gồm record chính + authorities, nên ghi nhiều row liên quan cần transaction boundary thích hợp nếu workflow đòi hỏi atomicity. Tạo user có thể cùng lúc với một request khác: `userExists(...)` trước `createUser(...)` là check hữu ích nhưng vẫn có **TOCTOU race**. Dùng unique constraint làm điểm bảo đảm cuối, xử lý `DuplicateKeyException` hoặc lỗi phù hợp và quyết định retry ở cấp nghiệp vụ.

Xóa user cần xử lý FK; lựa chọn hard-delete/soft-delete phụ thuộc luật lưu giữ, audit và domain references. Nếu soft-delete, bảo đảm login bị vô hiệu hóa và các truy vấn security không trả lại tài khoản đã xóa.

### 9.4 DataSource và khả năng vận hành

- Dùng connection pool có giới hạn, timeout và quyền DB tối thiểu; nếu auth service chỉ cần đọc, cân nhắc phân quyền SELECT riêng khỏi provisioning write.
- Đường đăng nhập cần index phù hợp trên username/namespace và authority FK; tránh query N+1 ở policy khác.
- Đặt TLS/credential DB trong secret manager, không hardcode production secrets vào `application.properties`.
- Database downtime/timeout phải dẫn đến authentication **thất bại an toàn** (không tự cấp anonymous quyền authenticated).
- Dùng database migration tool (Flyway/Liquibase) để quản lý schema production có version; tránh vừa chạy SQL initializer tự động vừa dùng migration tool trên cùng schema trừ khi có kế hoạch rõ ràng.
- Giới hạn việc log SQL bind parameters có thể chứa usernames/PII; không bật trace database JDBC trong production để soi password.
- Quy định độ mới cache và cơ chế thu hồi khi disabled hoặc role thay đổi; không cho rằng request sau tự reload `UserDetails` trong mọi cơ chế/session.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm | Hướng khắc phục |
| --- | --- | --- |
| Login thất bại dù user có trong bảng `users` | Thiếu `authorities` rows, sai username/case, wrong DataSource, SQL query. | Kiểm hai bảng trên **đúng database/schema**; lookup yêu cầu user có authority. |
| `BadCredentialsException` | Raw password không khớp encoded verifier; prefix `{id}` hoặc encoder sai. | Kiểm tạo hash, encoding policy; không đổi sang `{noop}` cho qua lỗi. |
| `DisabledException` / HTTP 401 | `enabled=false` hoặc mapper trạng thái sai. | Kiểm nguồn status và chính sách login, không sửa DB thành enabled nếu không có phê duyệt. |
| SQL syntax/table not found | Chưa chạy `schema.sql`, chạy sai datasource/schema, dialect khác, tên bảng/cột khác. | Kiểm cấu hình datasource, migration và default query; tránh đoán từ tên DB. |
| “User not found” khi authorities là rỗng | Loader không trả user có authorities hợp lệ. | Cấp authorities theo policy hoặc dùng custom user store khi semantics thật sự cần rỗng. |
| Login thành công nhưng `403` | Thiếu authority, `ROLE_` prefix sai, endpoint yêu cầu quyền khác, CSRF với request thay đổi state. | Kiểm `Authentication.getAuthorities()` đã được làm sạch và authorization rule; không sửa password store vô lý. |
| `createUser` lỗi SQL khi custom schema | Chỉ đổi SQL read; SQL create/insert vẫn trỏ bảng mặc định. | Đồng bộ CRUD queries hoặc dùng provisioning service riêng. |
| Tài khoản đã khóa vẫn đăng nhập được | Default schema không có lock flag; custom mapping/provider chưa kiểm. | Bổ sung security view và status checker đúng trách nhiệm. |
| Case “Alice” khác “alice” | Collation và kiểu cột tùy database; query chuẩn hóa không đồng bộ. | Chốt canonical username policy, unique index/collation phù hợp. |
| User A và B trùng username ở hai tenant | Query thiếu namespace/tenant. | Dùng identity key và trust boundary đa tenant đúng, không dựa vào header tự khai. |
| DB status/role đã đổi nhưng phiên cũ vẫn dùng | Authentication trong session là snapshot; cache/JWT chưa thu hồi. | Xác định refresh/revoke/invalidate policy; test cả session cũ. |
| Dữ liệu users/authorities chỉ còn một nửa | Create/update/delete nhiều SQL thiếu transaction hoặc lỗi concurrent writes. | Thêm transaction boundary, FK, unique constraints và integration tests. |

### 10.1 Khi gặp 401, tìm đúng tầng lỗi

Lần lượt kiểm: request có đi qua đúng `SecurityFilterChain`? `httpBasic()` đã được áp dụng? Filter tạo đúng authentication? Provider dùng `JdbcUserDetailsManager` này hay bean khác? SQL lookup lấy đúng account và authority không? `PasswordEncoder.matches(...)` có khớp? `enabled` có true? Nếu 401 sau khi tìm đúng user, không suy ra ngay lỗi JDBC query.

### 10.2 Khi gặp 403, kiểm authorization

Nếu response là 403, user có thể đã **xác thực đúng** nhưng thiếu quyền `ROLE_ADMIN` hoặc `orders:read`, hoặc thất bại CSRF đối với request dùng session/cookie. Xem authority của principal và policy trên endpoint/đối tượng; không tự thêm quyền cao chỉ để endpoint trả 200.

### 10.3 Ranh giới quan sát

Không log raw password, encoded password, `Authorization`, `Cookie`, bearer token hoặc JDBC credentials. Thông tin hữu ích gồm request ID, kết quả authentication, loại exception đã chuẩn hóa, tên component, SQL error code đã làm sạch, thời gian truy vấn. Cẩn thận SQL debug logs vì bind params có thể chứa định danh cá nhân.

## 11. Ma trận kiểm thử

| Phép thử | Kết quả mong đợi |
| --- | --- |
| Schema mới được init | Hai bảng và FK/unique constraints tồn tại trước khi seed users. |
| `createUser` với hai authorities | Có đúng một users row và hai authorities rows, không duplicate. |
| `loadUserByUsername("alice")` | Trả đúng username, encoded password, enabled=true và hai authorities. |
| `userExists("alice")` | True sau tạo, false sau xóa theo workflow. |
| Username không tồn tại | `loadUserByUsername` ném `UsernameNotFoundException`. |
| User không có authority row | Không thể load thành user có quyền theo mặc định; kiểm lỗi thực tế. |
| Password đúng, enabled=true | HTTP 200 ở endpoint authenticated; không xuất hash trong response. |
| Password sai | HTTP 401, không có principal được cấp quyền. |
| Enabled=false | HTTP 401 dù raw password đúng. |
| Alice có `orders:read` | `GET /api/orders` trả 200. |
| Alice thiếu `ROLE_ADMIN` | `GET /api/admin` trả 403. |
| Bản ghi authority trùng | Unique constraint từ chối insert trùng. |
| Authority username không tồn tại | Foreign key chặn insert mồ côi. |
| Đổi role trong database | Kết quả request mới phản ánh theo freshness/session policy đã thiết kế. |
| Custom read queries nhưng CRUD mặc định | Cần xác nhận create/update/delete tương thích, không chỉ login. |
| Login multi-tenant | Không lấy nhầm account cùng username từ tenant khác. |
| Tạo user đồng thời | Unique constraint và transaction tránh duplicate/bản ghi dở. |
| DB ngắt kết nối | Không tự coi authentication thành công; lỗi được xử lý an toàn. |
| Group mode được bật | Group tables tồn tại, authorities đúng, không nhân đôi role ngoài ý muốn. |

Với integration test, dùng datasource/migration gần production và kiểm cả authentication + query behavior. Unit test của một repository giả không đủ chứng minh cột/constraint/default SQL tương thích với database thực tế.

## 12. Bài tập tự kiểm tra

**Câu 1.** Một tài khoản `alice` có trong `users`, `enabled=true` và password hash hợp lệ nhưng không có dòng nào trong `authorities`. Vì sao login có thể bị lỗi như không tìm thấy user?

**Đáp án:** `JdbcDaoImpl`/`UserDetailsService` mặc định yêu cầu có `GrantedAuthority`; với không authority, loader có thể ném `UsernameNotFoundException`. Kiểm bảng quyền hoặc chọn kiến trúc khác nếu hệ thống có chủ ý cho account hoàn toàn không authority.

**Câu 2.** Database lưu `ROLE_EDITOR` nhưng code dùng `hasRole("EDITOR")`. Có cần thêm prefix `ROLE_` lần nữa khi truy xuất?

**Đáp án:** Không. `hasRole("EDITOR")` mặc định đối chiếu `ROLE_EDITOR`. Nếu nạp quyền từ database đã có prefix, không thêm `ROLE_` hai lần.

**Câu 3.** User có password hash đúng nhưng `enabled=false`. JDBC manager có chấp nhận login không?

**Đáp án:** Provider username/password tiêu chuẩn từ chối vì `isEnabled=false`, dù password đúng. Trường enabled là điều kiện account status, khác mật khẩu.

**Câu 4.** Muốn dùng bảng `app_accounts(login,hash,active)` thay `users`, chỉ đổi `usersByUsernameQuery` là đủ cho `createUser` chưa?

**Đáp án:** Chưa. Cần đổi cả query authorities và các SQL CRUD nếu muốn manager ghi/xóa trên schema mới, hoặc tách read-only `UserDetailsService` khỏi provisioning service custom.

**Câu 5.** Trong multi-tenant, hai tổ chức có username `sam`. Có nên dùng câu SQL `WHERE login = ?` làm toàn bộ quyết định danh tính?

**Đáp án:** Không. Cần namespace/tenant từ nguồn tin cậy, key hợp lệ và query đúng phạm vi, ngăn truy cập chéo; không tin mỗi header client tự báo.

**Câu 6.** Vì sao `JdbcUserDetailsManager` không đủ để hỗ trợ khóa account 15 phút sau 5 lần sai password theo mặc định?

**Đáp án:** Lược đồ mặc định chỉ lưu `enabled`, không có `lock_until`, failure counter hoặc logic status policy. Cần nguồn trạng thái, cơ chế cập nhật số lần sai, thời hạn khóa và checker phù hợp; test concurrency/recovery.

**Câu 7.** Có dùng `{noop}password` cho DB demo được không? Trong production có nên không?

**Đáp án:** `{noop}` có thể dùng để chứng minh flow trong bài học giới hạn, nhưng không bảo vệ password. Production phải dùng thuật toán password hashing được phê duyệt, cấu hình chi phí và secret policy thích hợp.

**Câu 8.** Alice login thành công, gọi `/api/admin` và nhận 403. Có phải password hash trong `users` sai không?

**Đáp án:** Không. Authentication đã thành công; Alice thiếu authority mà authorization yêu cầu. Kiểm bảng authorities và policy, không sửa password để chữa lỗi quyền.

## 13. Nguồn chính thức và đọc tiếp

- Spring Security — [JDBC Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/jdbc.html): `JdbcDaoImpl`, `JdbcUserDetailsManager`, default `users/authorities` schema và group tables.
- Spring Security — [JdbcDaoImpl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/jdbc/JdbcDaoImpl.html): các SQL lookup, mapping UserDetails, enableAuthorities, enableGroups, hỗ trợ/trở ngại schema.
- Spring Security — [JdbcUserDetailsManager Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/provisioning/JdbcUserDetailsManager.html): các API quản lý user và cấu hình SQL CRUD.
- Spring Security — [UserDetailsService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html): user không tồn tại hoặc không có GrantedAuthority.
- Spring Security — [DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): provider kiểm password và trạng thái từ `UserDetails`.
- Spring Security — [Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`, format verifier và nâng cấp hash.
- Spring Boot — [Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `schema.sql`/`data.sql`, datasource embedded và các cơ chế migration.

**Nguyên tắc ghi nhớ:** `JdbcUserDetailsManager` quản lý một *kho tài khoản có cấu trúc rõ*, trong đó `users` cung cấp **username + encoded password + enabled**, `authorities` cung cấp **quyền được cấp theo username**. SQL phải khớp schema và namespace, dữ liệu đến từ nguồn tin cậy, còn `DaoAuthenticationProvider` và `PasswordEncoder` mới quyết định credential hợp lệ. Sau xác thực, authorization vẫn quyết định người dùng được làm gì.