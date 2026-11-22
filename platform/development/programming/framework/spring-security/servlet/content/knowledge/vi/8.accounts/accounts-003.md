# JdbcUserDetailsManager: lược đồ tài khoản, quyền và truy vấn

Trong **Spring Security cho ứng dụng Servlet**, `JdbcUserDetailsManager` cho phép quản lý tài khoản và quyền trong **cơ sở dữ liệu quan hệ qua JDBC** thay vì giữ người dùng trong bộ nhớ. Nó vừa là một `UserDetailsService` để cơ chế xác thực tải người dùng, vừa là một `UserDetailsManager` cung cấp các thao tác tạo, cập nhật, xóa tài khoản và thay đổi mật khẩu theo hợp đồng API.

Trọng tâm của bài là ba điều phải khớp nhau: **cấu trúc dữ liệu** (cột, bảng, ràng buộc), **các câu SQL** Spring Security dùng và **ý nghĩa của thông tin quyền** sau khi truy vấn. Sau đó ta xây một ứng dụng Spring Boot minh họa, kiểm thử các trạng thái xác thực và phân tích những lỗi dễ gặp khi đổi tên bảng/cột, lưu mật khẩu hoặc cập nhật tài khoản.

> Phạm vi: Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet, `DataSource` JDBC. API chi tiết và mẫu DDL có thể khác theo phiên bản/hệ quản trị; cần kiểm tra phiên bản thư viện và migration thực tế trước khi triển khai production.

## 1. JdbcUserDetailsManager đứng ở đâu trong luồng xác thực?

Hãy tách rõ việc **tải tài khoản** với **xác minh thông tin đăng nhập**:

~~~text
HTTP Basic / form login / cơ chế đăng nhập Servlet
             |
             v
Authentication filter
             |
             v
AuthenticationManager
             |
             v
DaoAuthenticationProvider
    |                     |
    | loadUserByUsername  | passwordEncoder.matches(...)
    v                     v
JdbcUserDetailsManager   PasswordEncoder
    |
    v
DataSource -> JDBC SQL
    |
    +--> users        : username, password, enabled
    +--> authorities  : username, authority
    |
    v
UserDetails (username, password hash, enabled, authorities)
             |
             v
Authentication thành công
             |
             v
SecurityContext -> SecurityContextHolder cho request hiện tại
             |
             v
AuthorizationFilter / method security áp dụng quy tắc quyền
~~~

Các trách nhiệm riêng biệt:

- `JdbcUserDetailsManager` dùng SQL để **đọc/ghi thông tin user**. Nó **không tự đối chiếu HTTP request với password**.
- `DaoAuthenticationProvider` sử dụng `UserDetailsService` để tải user và `PasswordEncoder` để kiểm tra credential người dùng gửi.
- `Authentication` sau khi xác thực thành công chứa principal và authorities; các thành phần authorization sử dụng chúng để quyết định truy cập.
- `SecurityContextHolder` lưu ngữ cảnh đang được xử lý, không phải kho chứa tài khoản.
- `DataSource` cung cấp kết nối JDBC; `JdbcTemplate` và SQL nằm ở lớp truy cập dữ liệu của manager.
- `JdbcUserDetailsManager` **không phải ORM/JPA repository**; không tự yêu cầu entity `@Entity` hay `JpaRepository`.

Điểm quan trọng: Spring Security **không coi việc có bản ghi trong bảng users là đủ để login**. Cơ chế authentication vẫn phải kiểm tra mật khẩu hoặc chứng cứ phù hợp, trạng thái enabled và các điều kiện bảo mật khác.

## 2. Hai bảng mặc định: users và authorities

Lược đồ JDBC tối thiểu thông dụng của Spring Security có **hai bảng**:

| Bảng | Cột | Vai trò |
| --- | --- | --- |
| `users` | `username` | Khóa định danh người dùng, thường là khóa chính |
| `users` | `password` | **Mật khẩu đã băm/mã hóa một chiều** theo `PasswordEncoder`, không lưu plaintext |
| `users` | `enabled` | Người dùng có được phép xác thực theo trạng thái enabled không |
| `authorities` | `username` | Tham chiếu user sở hữu authority |
| `authorities` | `authority` | Một quyền/role/scope dưới dạng chuỗi |

Quan hệ là **một user có nhiều authority**:

~~~text
users
+-----------+---------------------------------+---------+
| username  | password                        | enabled |
+-----------+---------------------------------+---------+
| alice     | <bcrypt-hash>                   | true    |
| bob       | <bcrypt-hash>                   | false   |
+-----------+---------------------------------+---------+
        1
        |
        | 1:N (theo username)
        v
authorities
+-----------+--------------+
| username  | authority    |
+-----------+--------------+
| alice     | ROLE_USER    |
| alice     | REPORT_READ  |
| bob       | ROLE_USER    |
+-----------+--------------+
~~~

Chuỗi `<bcrypt-hash>` trong bảng trên chỉ là ký hiệu mô tả, **không phải giá trị có thể đăng nhập**. Giá trị thực được tạo bằng encoder có cấu hình tương ứng.

### DDL minh họa chạy được trên H2

File `src/main/resources/schema.sql` sau phù hợp với SQL mặc định đọc user và authorities của `JdbcUserDetailsManager`. Nó dùng kiểu `VARCHAR` thông dụng của H2; trong ứng dụng có chính sách không phân biệt hoa/thường của username, phải thiết kế thêm normalization/collation phù hợp.

~~~sql
CREATE TABLE users (
    username VARCHAR(50) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_authorities_user
        FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uq_username_authority
        UNIQUE (username, authority)
);
~~~

Những ràng buộc có ý nghĩa bảo mật và dữ liệu:

1. **Khóa chính `users.username`**: tránh hai bản ghi trùng tên theo cách DB so sánh username.
2. **Khóa ngoại `authorities.username`**: không để quyền mồ côi gán cho user không tồn tại.
3. **Unique `(username, authority)`**: tránh lưu cùng một quyền nhiều lần cho một user.
4. **NOT NULL `password` và `enabled`**: tránh bản ghi thiếu dữ liệu thiết yếu.
5. **Độ dài cột password đủ lớn**: BCrypt, Argon2 hoặc chuỗi có định dạng `{id}hash` có thể dài hơn password plaintext. Phải chọn độ dài theo encoder sử dụng.

Schema Spring Security cung cấp sẵn thường nằm tại resource `org/springframework/security/core/userdetails/jdbc/users.ddl`; bản schema cụ thể có thể dùng kiểu `varchar_ignorecase` trên một số hệ DB thử nghiệm và chứa thêm các bảng group. **Không áp nguyên DDL dành cho một database sang PostgreSQL, MySQL hay SQL Server mà không kiểm tra kiểu dữ liệu và cú pháp của database đó.** Trong dự án thật, dùng migration versioned bằng Flyway/Liquibase thay vì tự chạy lại CREATE TABLE khi server khởi động.

### Các bản ghi minh họa và quyền

Một người dùng có thể có nhiều hàng trong `authorities`:

~~~sql
-- Chỉ minh họa dữ liệu QUYỀN; tài khoản phải tồn tại trước.
INSERT INTO authorities (username, authority)
VALUES ('alice', 'ROLE_USER');

INSERT INTO authorities (username, authority)
VALUES ('alice', 'REPORT_READ');
~~~

Các ví dụ này chỉ chạy được khi đã có dòng `users.username = 'alice'`. Không chèn password dạng plaintext vào `users`. Cũng không được tạo user bằng một hash BCrypt sao chép từ ví dụ rồi coi đó là mật khẩu được quản trị an toàn: hãy dùng encoder thật, quản lý bí mật qua kênh phù hợp, và không đưa credentials của production vào repository.

## 3. Các truy vấn SELECT mặc định quan trọng nhất

Lúc một provider gọi `loadUserByUsername("alice")`, luồng xử lý thường cần **tải bản ghi người dùng** và **tập quyền**.

Truy vấn user mặc định về mặt logic là:

~~~sql
SELECT username, password, enabled
FROM users
WHERE username = ?;
~~~

Dấu `?` là **tham số JDBC**, được gán bằng username đầu vào. Không tự nối username vào câu SQL để xây truy vấn.

Truy vấn authority mặc định về mặt logic là:

~~~sql
SELECT username, authority
FROM authorities
WHERE username = ?;
~~~

Nội dung truy vấn trong bản mặc định của `JdbcDaoImpl` về cơ bản theo cấu trúc trên. SQL thực tế trong ứng dụng phụ thuộc những setter truy vấn đã thay đổi và những tính năng group được bật.

Nếu truy vấn trên cho user `alice`:

~~~text
users:
alice | <encoded-password> | true

authorities:
alice | ROLE_USER
alice | REPORT_READ
~~~

Thì một `UserDetails` được nạp chứa username `alice`, password đã encode, `enabled=true` và hai `GrantedAuthority`. Nó **chưa** chứng minh password người gọi gửi đúng; provider mới đối chiếu chứng cứ xác thực.

### Ý nghĩa của vị trí các cột

Một truy vấn `usersByUsernameQuery` tùy chỉnh cần trả **ba cột đúng thứ tự**: username, password, enabled. Một truy vấn `authoritiesByUsernameQuery` cần trả **hai cột đúng thứ tự**: username, authority. Dù có thể đổi tên/alias SQL, tốt nhất giữ các tên cột rõ ràng và kiểm thử mapping, vì cấu trúc hàng và việc đọc cột phải tương thích với cơ chế `JdbcDaoImpl` của phiên bản đang dùng.

**Không dùng `SELECT *`** cho các truy vấn cốt lõi. Khi schema thêm cột như `email`, `created_at` hoặc `tenant_id`, `SELECT *` có thể làm thay đổi thứ tự cột và khiến mapping sai dữ liệu.

### “Không tìm thấy tài khoản” không đồng nghĩa “sai mật khẩu”

Nếu `usersByUsernameQuery` không trả hàng nào, `UserDetailsService` có thể ném `UsernameNotFoundException`. Một provider thường chuyển các lỗi authentication thành phản hồi chung để hạn chế lộ sự tồn tại của tài khoản. Nếu bản ghi tồn tại nhưng password sai, quá trình xác minh cũng thất bại. Không nên xây API login trả “username tồn tại nhưng password sai” với nội dung khác biệt dễ bị dò tài khoản.

### Enabled và những cờ trạng thái khác

Mặc định lược đồ có `enabled`. Các cờ như `accountNonLocked`, `accountNonExpired` và `credentialsNonExpired` tồn tại trong hợp đồng `UserDetails`, nhưng **không có các cột tương ứng trong hai bảng mặc định**. Nếu sản phẩm cần khóa tài khoản, hết hạn credential, MFA hoặc status nghiệp vụ riêng, phải thiết kế lược đồ và logic riêng hoặc điều chỉnh `UserDetailsService`, chứ không giả định `JdbcUserDetailsManager` mặc định tự quản lý mọi trạng thái đó.

## 4. ROLE_USER, authority và các quy tắc phân quyền

Spring Security không áp đặt rằng mọi quyền đều là role. Mỗi dòng `authorities.authority` là một giá trị `GrantedAuthority` dạng chuỗi:

| Lưu trong DB | Phương thức kiểm tra | Kết quả theo quy tắc mặc định |
| --- | --- | --- |
| `ROLE_USER` | `hasRole("USER")` | Phù hợp |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Phù hợp |
| `REPORT_READ` | `hasAuthority("REPORT_READ")` | Phù hợp |
| `ADMIN` | `hasRole("ADMIN")` | **Không phù hợp** nếu chưa cấu hình lại role prefix |

Với mặc định, `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`. Khi tạo user:

~~~java
UserDetails user = User.withUsername("alice")
        .password(passwordEncoder.encode("password-from-secure-source"))
        .roles("USER")
        .build();
~~~

`roles("USER")` tự tạo authority `ROLE_USER`. Ngược lại:

~~~java
UserDetails user = User.withUsername("alice")
        .password(passwordEncoder.encode("password-from-secure-source"))
        .authorities("ROLE_USER", "REPORT_READ")
        .build();
~~~

`authorities(...)` lưu đúng chuỗi được truyền. Hai đoạn trên là **fragment thuộc dự án có Spring Security**, với các biến/kiểu đã được import/cung cấp; không dùng chuỗi literal ví dụ này làm mật khẩu production. Chọn một quy ước đặt tên authority và test xuyên suốt từ DB đến `hasRole/hasAuthority`.

Tập quyền từ JDBC có thể được dùng trong filter security hoặc method security. `JdbcUserDetailsManager` chỉ cung cấp quyền đã lưu; nó không tự biết rằng user có được xem báo cáo nào nếu chính sách authorization chưa được khai báo.

## 5. Các API quản trị tài khoản của JdbcUserDetailsManager

Lớp này triển khai các hành vi `UserDetailsManager` thường gặp:

| API | Tác dụng | Lưu ý |
| --- | --- | --- |
| `loadUserByUsername(username)` | Tải user và các authorities | Dùng cho authentication; có thể ném `UsernameNotFoundException` |
| `userExists(username)` | Kiểm tra có bản ghi user phù hợp không | Dùng cho thao tác quản trị; không phơi trực tiếp kết quả cho login công khai |
| `createUser(user)` | Tạo bản ghi user và các authorities | Password phải đã được encode thích hợp; cần quyền quản trị |
| `updateUser(user)` | Cập nhật thuộc tính mặc định và quyền của user | Phải tránh vô tình ghi đè password hash hoặc mất quyền ngoài dự kiến |
| `deleteUser(username)` | Xóa dữ liệu user do manager quản lý | Cân nhắc FK, phiên đăng nhập hiện có và dữ liệu nghiệp vụ liên quan |
| `changePassword(oldPassword, newPassword)` | Đổi mật khẩu cho user theo hợp đồng manager | Phụ thuộc cách xác định user hiện tại và cơ chế xác minh được cấu hình; không thay thế quy trình reset an toàn |

Chữ “quản trị” ở đây là chức năng kỹ thuật của interface; **không có nghĩa API tự bảo đảm người gọi HTTP có quyền quản trị**. Nếu bạn công khai endpoint gọi `createUser(...)`, phải thiết lập authorization ở tầng web/method và xác minh thông tin đầu vào. Dữ liệu truy cập JDBC còn chịu quyền của tài khoản kết nối DB.

### Tạo user an toàn qua Java

Ví dụ fragment bên trong một service được kiểm soát quyền:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.JdbcUserDetailsManager;

UserDetails account = User.withUsername("reporter")
        .password(passwordEncoder.encode(rawPassword))
        .authorities("ROLE_USER", "REPORT_READ")
        .build();

if (!jdbcUserDetailsManager.userExists("reporter")) {
    jdbcUserDetailsManager.createUser(account);
}
~~~

Ở đây `passwordEncoder`, `rawPassword` và `jdbcUserDetailsManager` là đối tượng/giá trị từ ứng dụng; đây là **fragment** chứ không phải một file Java tự chạy. Không log `rawPassword`. Bước kiểm tra rồi tạo user có thể gặp **race condition** nếu hai request đồng thời tạo cùng username, do đó phải dựa thêm vào khóa unique của DB và xử lý ngoại lệ trùng khóa đúng cách. Tránh coi `userExists(...)` là biện pháp chống trùng duy nhất.

### Cập nhật và đổi password: hai thao tác không nên đánh đồng

`updateUser(...)` thường cập nhật các cột do manager quản lý, bao gồm password/authorities lấy từ `UserDetails` truyền vào. Nếu mã xây object cập nhật từ form không chứa password hash hợp lệ, nguy cơ ghi giá trị không đúng vào DB. Khi cập nhật profile đơn thuần (ví dụ email), thường nên dùng service/repository riêng cho thông tin profile thay vì ghi lại toàn bộ security user.

Với `changePassword(...)`, kiểm tra hợp đồng của phiên bản bạn sử dụng và cấu hình authentication manager của manager: đừng mặc định rằng chỉ gọi phương thức này tự thiết lập mọi quy tắc đổi mật khẩu. Trong workflow đổi mật khẩu thực tế phải xác minh user hiện tại, kiểm tra mật khẩu cũ nếu yêu cầu, encode mật khẩu mới, kiểm tra chính sách mật khẩu, chống CSRF khi dùng cookie-based auth và cân nhắc vô hiệu hóa các phiên/token khác. Những chức năng đó là **chính sách của ứng dụng**, không phải toàn bộ đều do manager triển khai tự động.

## 6. Mã hóa mật khẩu và PasswordEncoder

Dữ liệu lưu trong `users.password` cần tương thích với `PasswordEncoder` được authentication provider sử dụng. Một encoder phổ biến là `BCryptPasswordEncoder`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
~~~

Khi tạo tài khoản, **encode trước khi lưu**:

~~~java
String encoded = passwordEncoder.encode(rawPassword);
userManager.createUser(User.withUsername(username)
        .password(encoded)
        .roles("USER")
        .build());
~~~

Đây là fragment sử dụng các biến từ ứng dụng. Spring Security sẽ dùng `passwordEncoder.matches(rawPassword, encodedPassword)` trong quá trình xác minh. BCrypt tạo salt ngẫu nhiên, nên hai lần encode cùng một mật khẩu có thể ra chuỗi khác nhau; **không so sánh hai chuỗi hash bằng equals để xác thực**. Cũng không hash lại một hash đã lưu trước khi ghi, vì sẽ làm mật khẩu thật không còn xác thực được.

### BCrypt trực tiếp và DelegatingPasswordEncoder

Hai kiểu lưu phổ biến:

- Với bean `new BCryptPasswordEncoder()`: cột `password` chứa chuỗi BCrypt như `$2a$...`, không cần prefix `{bcrypt}` để bản thân encoder này xác minh.
- Với `DelegatingPasswordEncoder` (ví dụ từ `PasswordEncoderFactories.createDelegatingPasswordEncoder()`): chuỗi lưu thường có tiền tố nhận diện thuật toán như `{bcrypt}$2a$...` để hệ thống chọn encoder tương ứng.

**Không trộn hai định dạng mà không cấu hình phù hợp.** Nếu dùng `BCryptPasswordEncoder` trực tiếp rồi lưu chuỗi có cả `{bcrypt}`, nó có thể không khớp vì phần tiền tố không phải hash BCrypt thuần. Ngược lại, một delegating encoder mặc định có thể cần prefix để biết thuật toán kiểm tra.

Dù dùng thuật toán nào, không lưu mật khẩu plaintext, không dùng phép hash nhanh không salt dành cho password và không hardcode password thật trong Java hay file cấu hình. Với sản phẩm thật, cần cơ chế thay đổi password, khôi phục tài khoản và quản lý secret đúng tiêu chuẩn.

## 7. Ví dụ Spring Boot hoàn chỉnh: database H2 + HTTP Basic

Đây là một ứng dụng **Spring Boot 3.x, Java 17+, Spring Security 6.x** dùng H2 để học cơ chế JDBC. Các đoạn Spring cần chạy trong dự án Maven với dependency tương ứng, **không thể chỉ biên dịch bằng một lệnh `javac` không có thư viện**.

### 7.1. Dependency Maven

Trong `pom.xml` của dự án Spring Boot đã có parent/plugin phù hợp, thêm dependencies:

~~~xml
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
~~~

Chọn các version được Spring Boot BOM quản lý; tránh khai báo lẫn version Spring Security không tương thích với Spring Boot đang dùng.

### 7.2. Nguồn dữ liệu và khởi tạo bảng

Lưu nội dung DDL mục 2 vào `src/main/resources/schema.sql`. Cấu hình `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:security_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Khi start ứng dụng, cơ chế khởi tạo SQL của Boot có thể chạy `schema.sql` để tạo bảng. Database in-memory trong ví dụ không phải kho tài khoản production và dữ liệu sẽ mất khi tiến trình Java kết thúc. Ở production, thay H2 bằng DataSource được quản lý, dùng migration thay vì tái tạo schema và giới hạn quyền kết nối DB.

### 7.3. Entry point của ứng dụng

Tạo file `src/main/java/com/example/security/JdbcSecurityApplication.java`:

~~~java
package com.example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JdbcSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcSecurityApplication.class, args);
    }
}
~~~

### 7.4. Bean JdbcUserDetailsManager, encoder và security chain

Tạo `src/main/java/com/example/security/JdbcSecurityConfig.java`:

~~~java
package com.example.security;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JdbcSecurityConfig {

    @Bean
    JdbcUserDetailsManager jdbcUserDetailsManager(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JdbcUserDetailsManager users,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);

        http.authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/reports").hasAuthority("REPORT_READ")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    CommandLineRunner seedDemoUser(
            JdbcUserDetailsManager users, PasswordEncoder encoder) {

        return args -> {
            String initialPassword = System.getenv("DEMO_INITIAL_PASSWORD");
            if (initialPassword == null || initialPassword.isBlank()) {
                return; // Không tự sinh tài khoản với mật khẩu mặc định.
            }

            if (!users.userExists("alice")) {
                users.createUser(User.withUsername("alice")
                    .password(encoder.encode(initialPassword))
                    .authorities("ROLE_USER", "REPORT_READ")
                    .build());
            }
        };
    }
}
~~~

**Lưu ý về version:** Ví dụ `DaoAuthenticationProvider()` và `setUserDetailsService(...)` dùng API thuộc dòng Spring Security 6.x; ở một số phiên bản mới các constructor/setter có thể được đánh dấu deprecated hoặc thay bằng constructor nhận `UserDetailsService`. Khi nâng cấp, chọn API phù hợp với version đã khóa trong dự án. Điều quan trọng là provider dùng **cùng manager và cùng PasswordEncoder** để xác thực.

Biến môi trường `DEMO_INITIAL_PASSWORD` chỉ dùng để khởi tạo **user demo ở môi trường phát triển**. Trong production, không dùng một mật khẩu bootstrap chung, không để secret trong lịch sử shell và không tạo user admin ngầm. Nếu dùng ứng dụng thật, cần quy trình provisioning hoặc migration có kiểm soát, logging không tiết lộ credentials và rotation cho bí mật.

### 7.5. Endpoint minh họa

Tạo `src/main/java/com/example/security/DemoController.java`:

~~~java
package com.example.security;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/reports")
    public String reports() {
        return "reports";
    }
}
~~~

### 7.6. Chạy thử

Trong dự án có Maven Wrapper tương thích, thiết lập biến môi trường `DEMO_INITIAL_PASSWORD` theo cách của hệ điều hành và chạy:

~~~bash
# Ví dụ trên Unix-like shell, chỉ cho môi trường thử nghiệm:
export DEMO_INITIAL_PASSWORD='local-dev-secret'
./mvnw spring-boot:run
~~~

Sau khi server khởi động thành công ở cổng 8080 mặc định, thử:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/reports
curl -i -u alice:local-dev-secret http://localhost:8080/reports
curl -i -u alice:wrong-password http://localhost:8080/reports
~~~

Kết quả **dự kiến**, không phải stdout của Java độc lập:

| Request | Điều kiện | Kết quả thường thấy |
| --- | --- | --- |
| `GET /public` | Không cần login | HTTP 200, body `public` |
| `GET /reports` | Không credentials | HTTP 401 do HTTP Basic entry point |
| `GET /reports` với Alice và password đúng | DB có Alice, enabled=true, `REPORT_READ` | HTTP 200, body `reports` |
| `GET /reports` với password sai | Provider không xác thực thành công | HTTP 401 |
| `GET /reports` với user đã xác thực nhưng thiếu quyền | `REPORT_READ` vắng mặt | HTTP 403 |

Nếu không đặt biến môi trường trước khi chạy, `alice` không được seed và lệnh Basic ở trên sẽ không login được. Vì database H2 là in-memory, dữ liệu có thể mất khi restart. Server có thể chạy cổng khác nếu cấu hình `server.port`. Các filter/entry point tùy biến có thể khiến response khác so với ví dụ.

### Kiểm tra dữ liệu trực tiếp bằng SQL

Để đối chiếu quan hệ và quyền đã lưu (qua JDBC console hoặc công cụ DB được cho phép):

~~~sql
SELECT username, enabled
FROM users
ORDER BY username;

SELECT username, authority
FROM authorities
ORDER BY username, authority;
~~~

Không xuất cột `password` ra log/console chia sẻ trừ khi thật sự cần kiểm tra và có biện pháp bảo vệ dữ liệu nhạy cảm. Hash vẫn là thông tin bảo mật cần kiểm soát.

## 8. Chương trình Java 17 độc lập: hiểu cách ghép tài khoản và quyền

Nếu chưa có Spring Boot/H2, có thể chạy một mô phỏng bằng **JDK 17 thuần**. Nó không truy vấn SQL và **không triển khai JdbcUserDetailsManager**; mục đích là cho thấy vì sao mỗi user cần một bản ghi nhưng có thể có nhiều dòng authority, và vì sao không tìm thấy user khác với user bị vô hiệu hóa.

Lưu file `UserAuthorityRowsDemo.java`:

~~~java
import java.util.List;

public class UserAuthorityRowsDemo {
    record UserRow(String username, String passwordHash, boolean enabled) {}
    record AuthorityRow(String username, String authority) {}

    public static void main(String[] args) {
        List<UserRow> users = List.of(
            new UserRow("alice", "encoded-A", true),
            new UserRow("bob", "encoded-B", false)
        );
        List<AuthorityRow> grants = List.of(
            new AuthorityRow("alice", "ROLE_USER"),
            new AuthorityRow("alice", "REPORT_READ"),
            new AuthorityRow("bob", "ROLE_USER")
        );

        for (String name : List.of("alice", "bob", "ghost")) {
            var user = users.stream()
                    .filter(row -> row.username().equals(name))
                    .findFirst();

            if (user.isEmpty()) {
                System.out.println(name + " -> not found");
                continue;
            }

            List<String> authorities = grants.stream()
                    .filter(row -> row.username().equals(name))
                    .map(AuthorityRow::authority)
                    .sorted()
                    .toList();

            System.out.println(name + " enabled=" + user.get().enabled()
                    + " authorities=" + authorities);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac UserAuthorityRowsDemo.java
java UserAuthorityRowsDemo
~~~

Stdout chính xác:

~~~text
alice enabled=true authorities=[REPORT_READ, ROLE_USER]
bob enabled=false authorities=[ROLE_USER]
ghost -> not found
~~~

Các chuỗi `encoded-A` / `encoded-B` chỉ là dữ liệu giả cho mô phỏng. Chúng **không phải password hash hợp lệ** và không được dùng trong bảng thật. Ở hệ thống JDBC, manager nạp đúng user/authority từ SQL, còn provider kiểm tra password đã mã hóa và trạng thái enabled.

## 9. Tùy chỉnh truy vấn khi dùng schema có sẵn của doanh nghiệp

Không phải doanh nghiệp nào cũng đặt bảng `users` và `authorities`. Giả sử có:

~~~text
app_account: login_name, password_hash, active, display_name
app_grant:   login_name, permission_code
~~~

Thay vì đổi toàn bộ database, có thể cấu hình các truy vấn **đọc**:

~~~java
JdbcUserDetailsManager manager = new JdbcUserDetailsManager(dataSource);

manager.setUsersByUsernameQuery(
    "SELECT login_name, password_hash, active " +
    "FROM app_account WHERE login_name = ?");

manager.setAuthoritiesByUsernameQuery(
    "SELECT login_name, permission_code " +
    "FROM app_grant WHERE login_name = ?");
~~~

Đây là **fragment** với biến `dataSource` do ứng dụng cung cấp. Chú ý:

- Truy vấn đầu phải trả ba cột có semantics **username, encoded password, enabled**.
- Truy vấn thứ hai phải trả cặp **username, authority**.
- Dùng `?` để truyền username theo JDBC, không nối chuỗi từ input.
- Nếu username mang tenant ID, nên thiết kế key và lọc tenant rõ ràng. Cơ chế `loadUserByUsername(String)` mặc định chỉ nhận username; không thể mặc nhiên suy ra tenant an toàn từ một biến ThreadLocal bất kỳ.
- Dùng JOIN để truy vấn quyền từ nhiều bảng là được nếu trả đúng cấu trúc cột và xử lý duplicate/authority theo chính sách đã chọn.
- Đảm bảo index cho lookup username và join authorities.

**Cảnh báo quan trọng:** Hai setter trên chỉ đổi **đường đọc**. Nếu ứng dụng còn gọi `createUser(...)`, `updateUser(...)`, `deleteUser(...)` hoặc `userExists(...)`, các thao tác ấy có những câu SQL riêng và có thể vẫn nhắm vào `users` / `authorities` mặc định. Cần cấu hình **toàn bộ tập truy vấn ghi/kiểm tra** của `JdbcUserDetailsManager` tương ứng với schema custom, hoặc dùng `UserDetailsService` tùy biến chỉ đọc kèm service quản trị user riêng. Không nên chỉ sửa hai SELECT rồi cho rằng toàn bộ CRUD đã chuyển sang bảng doanh nghiệp.

### Khi nào nên viết UserDetailsService riêng?

Chọn `JdbcUserDetailsManager` khi nhu cầu quản lý user + authorities khá sát schema mặc định, quy tắc SQL đơn giản và bạn muốn các API quản trị phổ biến. Xem xét triển khai `UserDetailsService` riêng khi:

- Dữ liệu account đã dùng schema lớn hoặc đa tenant.
- Các quyền được tính từ nhóm, phân cấp, đơn vị hoặc policy động.
- Username có nhiều hình thức định danh/alias, hoặc đăng nhập phải kiểm tra trạng thái ngoài enabled.
- Account lifecycle có audit bắt buộc, soft delete, lockout, MFA, sự kiện domain hoặc quy tắc transaction phức tạp.
- User được đồng bộ từ LDAP, IdP, SSO, OAuth2 hoặc cơ chế định danh ngoài cơ sở dữ liệu.

Một custom `UserDetailsService` thường chỉ cần tải user hợp lệ và tạo `UserDetails`. Phần xác thực vẫn do provider thực hiện; nếu cần nhiều cơ chế xác thực, phải thiết kế provider/manager đúng thay vì tự kiểm tra password trong controller.

## 10. Quyền nhóm: groups, group_members và group_authorities

Ngoài quyền gán trực tiếp cho username, bộ schema JDBC do Spring Security cung cấp còn có hỗ trợ **group-based authorities** ở một số cấu hình. Các bảng nhóm thường có vai trò:

| Bảng | Dữ liệu chính | Quan hệ |
| --- | --- | --- |
| `groups` | ID nhóm, tên nhóm | Một nhóm có nhiều thành viên |
| `group_members` | Nhóm và username của thành viên | Gán user vào group |
| `group_authorities` | Nhóm và authority được cấp | Các thành viên có thể nhận quyền của group |

Việc hỗ trợ load quyền nhóm nằm trong cơ chế JDBC với tùy chọn như `setEnableGroups(true)`. **Không tự kết luận mặc định đã bật quyền nhóm chỉ vì bảng `groups` tồn tại.** Nếu bật nhóm, kiểm tra version/schema, query group authorities và cách hợp nhất quyền nhóm với quyền trực tiếp. Xác minh các quy tắc cập nhật/xóa thành viên cùng transaction và foreign key; thiếu cleanup có thể để lại mapping mồ côi.

Quyền theo group không giải quyết mọi bài toán role hierarchy hoặc tenant permission. Khi mô hình quyền phức tạp, nên xác định policy rõ ràng thay vì biểu diễn mọi quan hệ chỉ bằng một bảng `authorities`.

## 11. Transactions, khóa dữ liệu và race condition

Một thao tác `createUser(...)` có thể phải ghi **user trước, authorities sau**. `updateUser(...)` có thể phải cập nhật user và thay tập quyền. Khi có lỗi giữa chừng, tính nhất quán phụ thuộc transaction, cách gọi manager và cấu hình DB:

- Nên thực hiện việc provision/update/delete tài khoản trong **service transaction** được kiểm soát.
- Bảo đảm foreign key, unique index và chính sách on-delete phù hợp; không trông cậy hoàn toàn vào thao tác kiểm tra trong Java.
- Nếu hai request cùng tạo username, một request có thể thất bại vì unique constraint; xử lý lỗi có chủ đích, không biến nó thành thông báo nhạy cảm cho client.
- Khi cập nhật quyền, xem xét audit và concurrency (optimistic locking hoặc mức cô lập phù hợp) nếu nghiệp vụ yêu cầu.
- Khi xóa user, liên kết nghiệp vụ như đơn hàng, lịch sử audit và phiên đăng nhập cần chính sách riêng; không tự động cascade xóa dữ liệu nghiệp vụ quan trọng chỉ để khớp schema security.

**Transaction không tự động giải quyết mọi vấn đề bảo mật.** Ví dụ: user đã bị khóa trong DB nhưng vẫn còn JWT có chữ ký hợp lệ và các quyền đã được nhúng vào token; `JdbcUserDetailsManager` chỉ ảnh hưởng nếu luồng authentication/authorization thực sự nạp lại trạng thái user từ DB hoặc có cơ chế kiểm tra thu hồi.

### Caching UserDetails

Một authentication provider có thể dùng `UserCache` hoặc cache từ tầng ứng dụng. Nếu cache user/authorities, thay đổi trong DB có thể chưa phản ánh ngay ở request kế tiếp. Cần chính sách invalidation và thời hạn cache, nhất là khi khóa tài khoản hoặc thu hồi quyền. Không giả định mỗi request đều chạy cả hai SQL SELECT; luồng authentication và caching quyết định tần suất truy vấn.

## 12. Kiểm thử tích hợp tài khoản JDBC và quyền

Với ứng dụng Spring Boot ở mục 7, thư viện `spring-security-test` cho phép gửi Basic credentials thật đến filter và provider, thay vì chỉ giả lập principal bằng `@WithMockUser`. Một test mẫu:

~~~java
package com.example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JdbcAuthenticationTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcUserDetailsManager users;
    @Autowired PasswordEncoder passwords;

    @BeforeEach
    void setUp() {
        if (!users.userExists("reader")) {
            users.createUser(User.withUsername("reader")
                .password(passwords.encode("reader-test-pass"))
                .authorities("ROLE_USER")
                .build());
        }
        if (!users.userExists("reporter")) {
            users.createUser(User.withUsername("reporter")
                .password(passwords.encode("reporter-test-pass"))
                .authorities("ROLE_USER", "REPORT_READ")
                .build());
        }
    }

    @Test
    void anonymousAndWrongPasswordAreRejected() throws Exception {
        mvc.perform(get("/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/reports")
                .with(httpBasic("reporter", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticationDoesNotGrantEveryAuthority() throws Exception {
        mvc.perform(get("/reports")
                .with(httpBasic("reader", "reader-test-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/reports")
                .with(httpBasic("reporter", "reporter-test-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports"));
    }
}
~~~

Đây là **test sử dụng mật khẩu giả được giới hạn trong test**, không phải secret production. Nếu lược đồ trong `schema.sql` chưa được khởi tạo, hoặc class test không thấy đúng application configuration, test sẽ thất bại vì thiếu DB/bean. Các trạng thái HTTP được kỳ vọng với chính cấu hình HTTP Basic, controller và authority đã nêu; entry point hoặc authorization custom có thể thay đổi status.

Test `@WithMockUser` hữu ích khi chỉ muốn kiểm thử authorization, nhưng **không kiểm chứng** SQL JDBC, `PasswordEncoder` và `DaoAuthenticationProvider` thật. Để học `JdbcUserDetailsManager`, cần ít nhất một integration test đi qua database như trên.

### Kiểm tra các trường hợp khác

- User không tồn tại: `loadUserByUsername(...)` thất bại, login trả thông báo chung.
- User tồn tại nhưng `enabled=false`: authentication không được cấp.
- Password hash/encoder không tương thích: user vẫn được tải nhưng xác thực thất bại.
- User có `ROLE_USER` nhưng endpoint yêu cầu `ROLE_ADMIN`: thường 403 nếu đã xác thực.
- User có nhiều authority: tất cả phải được nạp đúng, tránh mất quyền do JOIN hoặc mapping lỗi.
- Trùng username/authority: DB unique constraint có hiệu lực.
- Thay quyền trong DB: kiểm tra tác động của cache/session/token và chính sách cập nhật.
- SQL custom: kiểm tra column order, tham số username, soft delete, tenant và case sensitivity.

## 13. Những lỗi cấu hình phổ biến

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| SQL báo không tồn tại bảng `users` hoặc `authorities` | Chưa chạy schema, sai DataSource/schema search path | Kiểm tra migrations, JDBC URL, DB user và tên schema |
| Tạo được user nhưng login không thành công | Password lưu sai định dạng hoặc encoder khác | Xem cấu hình PasswordEncoder, quy trình `encode/matches` |
| User `alice` không truy cập được endpoint hasRole("USER") | DB lưu `USER` thay vì `ROLE_USER` | Chuẩn hóa authority string và kiểm tra rule |
| Có `roles("ADMIN")` nhưng người dùng vẫn 403 | Chain/rule khác được chọn, hoặc token/session có quyền cũ | Xác minh selected chain, authorities thực tế, cache |
| `loadUserByUsername` báo không tìm thấy | Username khác hoa/thường, sai SQL hoặc sai datasource | Kiểm tra WHERE, collation, normalization và bind parameter |
| Cập nhật user khiến password hỏng | `updateUser(...)` ghi password không hợp lệ | Không dùng manager để thay field profile tùy tiện; kiểm tra hash |
| Sửa hai câu SELECT nhưng CRUD báo lỗi | SQL ghi/kiểm tra vẫn trỏ bảng cũ | Cấu hình đủ SQL hoặc tách service quản trị riêng |
| User nhận quá nhiều/quá ít quyền | Truy vấn JOIN, group config, quyền trùng, tenant lọc sai | Test tập authorities đầy đủ, indexes và constraints |
| Tạo tài khoản song song đôi khi lỗi unique | Race giữa `userExists` và `createUser` | Dựa vào unique constraint và transaction/exception handling |
| PasswordEncoder báo không có encoder cho id | Dùng delegating encoder nhưng hash thiếu/khác prefix | Thống nhất định dạng lưu và encoder |
| User bị disable nhưng JWT cũ vẫn gọi API được | Resource Server không truy vấn lại user mỗi request | Thiết kế revocation/expiry và chính sách kiểm tra trạng thái |
| Test MockMvc với WithMockUser PASS, chạy thật FAIL | Mock user không đi qua JDBC/password verification | Thêm integration test với `httpBasic` hoặc login thật |

### Bảo vệ truy vấn và dữ liệu

`JdbcUserDetailsManager` dùng SQL tham số hóa khi thực hiện lookup mặc định. Khi custom SQL, vẫn phải giữ cách bind tham số an toàn và không xây dynamic SQL từ input. Cần hạn chế quyền của DB account (chỉ được đọc/ghi các bảng cần thiết), bật TLS cho kết nối DB khi phù hợp, bảo vệ backup và audit những thao tác thay đổi quyền. Không trả message khác biệt giúp attacker dò username, và không log password, hash, token hoặc toàn bộ credentials.

### Hiệu năng và index

Authentication có thể cần ít nhất một lookup user và một lookup authorities. Với nhiều user, index ở `users.username` và `authorities.username` giúp giảm chi phí. Truy vấn custom có JOIN phức tạp phải có index và execution plan phù hợp. Tránh đặt cache bất cẩn cho mật khẩu/quyền mà không có chiến lược thu hồi.

## 14. Bài tập tự kiểm tra

**Bài 1.** Bảng `users` có `alice` enabled=true, và bảng `authorities` có `ROLE_USER`. Endpoint bảo vệ bằng `hasAuthority("ROLE_USER")`. Điều gì cần diễn ra trước khi Alice được vào endpoint?

**Đáp án:** Provider phải tải user, xác minh password/chứng cứ hợp lệ và các trạng thái cần thiết, tạo `Authentication` thành công. Sau đó authorization kiểm tra authority `ROLE_USER`. Chỉ có dữ liệu user trong DB chưa đủ để xác thực.

**Bài 2.** Vì sao `hasRole("ADMIN")` không khớp authority `ADMIN` trong DB theo mặc định?

**Đáp án:** Mặc định `hasRole("ADMIN")` mong authority `ROLE_ADMIN`. Có thể lưu `ROLE_ADMIN` hoặc dùng `hasAuthority("ADMIN")` nếu chính sách dự án chủ động định nghĩa quyền tên `ADMIN`.

**Bài 3.** Một công ty đổi tên bảng `users` thành `app_account`, cột `password` thành `password_hash`. Chỉ sửa `setUsersByUsernameQuery(...)` đã đủ để gọi `createUser(...)` chưa?

**Đáp án:** Chưa. Cần điều chỉnh SQL tạo/cập nhật/xóa/kiểm tra user và authority tương ứng hoặc dùng service quản trị riêng. SQL SELECT tùy chỉnh chỉ tác động phần đọc.

**Bài 4.** Lần thứ hai gọi `passwordEncoder.encode("secret")` tạo hash khác lần đầu. Có phải encoder bị lỗi?

**Đáp án:** Không. Encoder như BCrypt sử dụng salt, nên các hash khác nhau vẫn có thể cùng hợp lệ cho một mật khẩu. Kiểm tra bằng `matches(raw, storedHash)`, không so sánh hash mới với hash cũ bằng equals.

**Bài 5.** Nếu `UserDetailsManager.userExists("bob")` trả false trước `createUser("bob")`, có chắc không thể phát sinh lỗi trùng username không?

**Đáp án:** Không. Hai tác vụ đồng thời có thể cùng thấy false rồi cùng insert. Khóa unique/primary key trong database là tuyến phòng thủ bắt buộc; ứng dụng xử lý lỗi trùng một cách an toàn.

**Bài 6.** Test dùng `@WithMockUser(roles = "ADMIN")` chạy thành công. Có chứng minh BCrypt/JDBC users/authorities đúng không?

**Đáp án:** Không. Mock user bỏ qua xác minh mật khẩu và phần nạp user thật từ DB. Cần integration test với Basic/form login đi qua `DaoAuthenticationProvider` và `JdbcUserDetailsManager`.

**Bài 7.** User được gỡ `REPORT_READ` trong DB, nhưng request mang bearer token JWT cũ vẫn có `REPORT_READ`. Có phải `JdbcUserDetailsManager` tự thất bại trong việc xóa quyền?

**Đáp án:** Không nhất thiết. JWT có thể chứa authorities đã phát hành và request không nạp lại DB. Cần chính sách token expiry/revocation hoặc nạp quyền động theo yêu cầu hệ thống; quyền DB và claim của token là hai phạm vi khác nhau.

## 15. Checklist triển khai thực tế

- Xác định JDBC manager dùng **DataSource**, schema và migration nào; tránh trỏ nhầm môi trường.
- Đảm bảo cột mặc định `username/password/enabled` và `username/authority` tương thích với SQL; khi custom phải cấu hình đầy đủ cả **đọc lẫn ghi**.
- Có khóa chính, foreign key, unique constraint, indexes và quy tắc case sensitivity/tenant rõ ràng.
- Dùng `PasswordEncoder` an toàn, nhất quán với chuỗi hash lưu trong DB; không giữ plaintext/credentials trong log.
- Hiểu authority string: `roles(...)` tạo `ROLE_...`; `hasRole(...)` và `hasAuthority(...)` có semantics khác nhau.
- Phân biệt tải `UserDetails`, đối chiếu credential tại provider và phân quyền tại authorization layer.
- Chỉ công khai thao tác quản trị tài khoản sau khi đã kiểm soát authorization, validation, audit và transaction.
- Test username không tồn tại, password sai, user disabled, đủ/thiếu quyền, SQL custom, cập nhật/tạo đồng thời và cache.
- Khi quản lý identity/permission phức tạp (SSO, MFA, tenant, workflow), cân nhắc `UserDetailsService`/service nghiệp vụ riêng thay vì kéo dài schema mặc định.

**Ghi nhớ:** `JdbcUserDetailsManager` cung cấp chiếc cầu từ **tài khoản và authority trong SQL** tới `UserDetails` mà Spring Security dùng để xác thực, đồng thời hỗ trợ một tập API quản lý user. Độ đúng của nó phụ thuộc vào **lược đồ bảng, truy vấn SQL, PasswordEncoder, cách hiểu authority và cơ chế authentication** cùng nhất quán.