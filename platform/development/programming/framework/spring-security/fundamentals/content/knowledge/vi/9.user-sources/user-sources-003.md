# InMemoryUserDetailsManager cho học tập và kiểm thử

> **Trọng tâm:** `InMemoryUserDetailsManager` là một cách tạo và quản lý `UserDetails` ngay trong bộ nhớ của tiến trình Java. Nó rất hữu ích để học **username/password authentication**, thử `roles`/`authorities`, xây test độc lập với database và tái hiện nhanh các trường hợp đăng nhập đúng, sai mật khẩu, không đủ quyền hoặc tài khoản bị khóa. Nó **không phải kho người dùng bền vững**: restart ứng dụng thì các thay đổi runtime không được giữ lại, các instance/nút triển khai không tự đồng bộ và việc hard-code mật khẩu thật vào code là nguy hiểm.

Bài thuộc nhóm **Nguồn người dùng** của module **Spring Security – fundamentals**. Ví dụ chính sử dụng **Java 17+, Spring Boot 3.5.16, Spring Security 6.5.x, Spring MVC/Servlet**, HTTP Basic và JUnit/MockMvc. Có hai lớp kiểm thử độc lập: kiểm thử HTTP qua filter chain và kiểm thử trực tiếp API quản lý user. Phần cuối làm rõ cách giới hạn user mẫu trong profile test, cách tránh rò rỉ trạng thái giữa các bài test và thời điểm chuyển sang kho người dùng production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Vẽ đúng mối quan hệ `UserDetailsService` → `InMemoryUserDetailsManager` → `DaoAuthenticationProvider` → `PasswordEncoder` → `AuthenticationManager`.
2. Tạo nhiều tài khoản với mật khẩu BCrypt hash, quyền `ROLE_USER`/`ROLE_ADMIN` và authority riêng như `TASK_WRITE`.
3. Phân biệt **xác thực** người dùng bằng username/password với **phân quyền** cho HTTP method, endpoint và resource.
4. Hiểu `UserDetails`, các cờ account state (`enabled`, `accountNonLocked`, `accountNonExpired`, `credentialsNonExpired`) và các lỗi thường nhận qua HTTP.
5. Sử dụng `loadUserByUsername`, `userExists`, `createUser`, `updateUser`, `deleteUser` và `updatePassword` trong bài test có trạng thái riêng.
6. Viết integration tests dùng `httpBasic(...)` để đi qua **password validation thật** và phân biệt với `@WithMockUser` hoặc `user(...)`.
7. Tạo ma trận test `200 / 401 / 403`, quyền theo method, CSRF và account locked mà không chạy database hoặc hệ thống nhận dạng bên ngoài.
8. Nhận ra giới hạn về persistence, đa instance, quản lý quyền, password lifecycle, revoke và bảo mật test fixtures.
9. Biết lúc nào nên dùng `@TestConfiguration` hoặc test profile để tách danh tính mẫu khỏi môi trường production.

## 2. InMemoryUserDetailsManager nằm ở đâu trong Spring Security?

Hãy bắt đầu từ luồng HTTP Basic:

```text
GET /me
Authorization: Basic <username:password được Base64>
           |
           v
Servlet SecurityFilterChain
           |
           v
BasicAuthenticationFilter
           |
           v
UsernamePasswordAuthenticationToken (chưa xác thực)
           |
           v
AuthenticationManager (thường ProviderManager)
           |
           v
DaoAuthenticationProvider
     |                         |
     v                         v
UserDetailsService        PasswordEncoder
     |                    matches(raw, hash)
     v                         ^
InMemoryUserDetailsManager     |
     |                         |
     +---- UserDetails --------+
             |
      username, hash,
      authorities,
      account flags
             |
             v
Authentication thành công hoặc AuthenticationException
             |
             v
SecurityContext (request hiện tại)
             |
             v
AuthorizationFilter -> Controller -> Service
```

`InMemoryUserDetailsManager` là implementation của `UserDetailsService` và `UserDetailsManager`, đồng thời hỗ trợ cơ chế cập nhật password cho `UserDetails`. Nó **cung cấp dữ liệu user** cho provider. Bản thân manager này **không phải HTTP filter**, **không nhận REST request login**, **không xác minh quyền sở hữu bản ghi**, và **không tự thay `SecurityFilterChain`**.

Khi `DaoAuthenticationProvider` nhận một username/password request, nó yêu cầu `UserDetailsService.loadUserByUsername(username)` và so raw password với hash bằng `PasswordEncoder.matches(...)`. Nếu mọi điều kiện hợp lệ, provider trả `Authentication` đã xác thực với authorities tin cậy từ `UserDetails`.

### Bảng phân vai

| Thành phần | Nhiệm vụ | Cần tránh nhầm với |
| --- | --- | --- |
| `UserDetails` | Một mô tả user: username, password hash, authorities, trạng thái tài khoản | Không phải JPA `@Entity` bắt buộc |
| `UserDetailsService` | Hợp đồng đọc user: `loadUserByUsername(String)` | Không tự quyết định URL được mở |
| `UserDetailsManager` | Mở rộng UserDetailsService với API thêm, sửa, xóa user | Không có nghĩa kho dữ liệu được persist |
| `InMemoryUserDetailsManager` | Lưu `UserDetails` trong bộ nhớ của một Java process | Không phải database hoặc distributed user store |
| `DaoAuthenticationProvider` | Kiểm tra credential/account state cho username/password | Không phải nơi khai báo route policy |
| `PasswordEncoder` | Hash và so khớp mật khẩu | Không mã hóa dữ liệu mạng; HTTP cần TLS |
| `AuthenticationManager` | Điều phối provider, trả kết quả xác thực hoặc exception | Không tự tạo user hay ghi HTTP response |
| `SecurityFilterChain` | Chọn HTTP filters và quy tắc URL/method/authority | Không tự suy ra quyền owner/tenant |
| `@WithMockUser`/`user(...)` trong test | Chèn principal giả để kiểm thử authorization | Không kiểm tra mật khẩu với user store thật |

### Vì sao gọi là “UserDetailsManager” thay vì chỉ “UserDetailsService”?

`UserDetailsService` có một method chính:

```java
UserDetails loadUserByUsername(String username)
    throws UsernameNotFoundException;
```

`UserDetailsManager` cung cấp thêm `createUser`, `updateUser`, `deleteUser`, `userExists` và `changePassword`. `InMemoryUserDetailsManager` implement những method này trên dữ liệu trong RAM. Tên “manager” nói về khả năng sửa user **trong kho này**, không nói rằng nó quản lý tập trung mọi user trong hệ thống hay bảo đảm ACID/durability như database.

## 3. Khi nào InMemoryUserDetailsManager hữu ích?

Nó đặc biệt phù hợp với bốn tình huống:

- **Bài thực hành Spring Security:** khởi tạo Alice, Bob, admin và một user bị khóa để hiểu authentication khác authorization.
- **Integration test của API:** xác nhận đúng Basic credentials và kiểm thử 200/401/403 mà không phụ thuộc database/migration/seed/Identity Provider.
- **Kiểm thử logic quanh UserDetailsManager:** thử create/update/delete, authority và trạng thái tài khoản bằng một manager mới trong từng test.
- **PoC/local demo ngắn hạn:** dựng chức năng nhanh để học filter chain, form login/Basic auth hoặc method security.

Cần nhìn nhận giới hạn của nó:

1. **Không persist:** Dữ liệu được tạo/sửa/xóa runtime sẽ mất khi JVM restart; các user khai báo bằng bean có thể được tái tạo từ code mỗi lần start.
2. **Không chia sẻ đa instance:** Hai replica chạy hai bộ nhớ khác nhau; cập nhật quyền/user ở replica A không tự hiện ở B.
3. **Không có nghiệp vụ account đầy đủ:** MFA, self-service reset, verification email, lockout theo lịch sử, audit, quản lý khóa, xác thực liên kết đều cần thiết kế riêng.
4. **Không tự revoke session/token:** Đổi quyền trong manager không đảm bảo các `Authentication` đã lưu ở session hoặc token tự mang claims lập tức bị cập nhật.
5. **Không phải nơi lưu credential production:** Dù password được hash bằng BCrypt khi vào RAM, việc hard-code plaintext trước khi hash trong source vẫn làm lộ bí mật nếu repository bị đọc.
6. **Không bảo vệ domain resource:** `ROLE_USER` không quyết định Alice có thể đọc đơn hàng của Bob hay không.
7. **Không giống reactive user store:** WebFlux dùng `MapReactiveUserDetailsService` và `ReactiveUserDetailsService` để phù hợp reactive pipeline.

**Tiêu chí chọn:** Nếu bài tập cần test authentication/authorization nhưng chưa cần persistence, InMemoryUserDetailsManager giúp giữ setup đơn giản. Nếu có tài khoản thật, phân quyền thay đổi thường xuyên, triển khai nhiều replica hoặc yêu cầu audit/lifecycle, hãy thiết kế kho user/IdP phù hợp.

## 4. Khởi tạo UserDetails đúng cách

### 4.1. Tài khoản đơn giản

Ví dụ snippet trong cấu hình Spring:

```java
@Bean
InMemoryUserDetailsManager users(PasswordEncoder encoder) {
    UserDetails alice = User.withUsername("alice")
        .password(encoder.encode("demo-pass"))
        .roles("USER")
        .build();

    return new InMemoryUserDetailsManager(alice);
}
```

`User.withUsername(...)` là builder do Spring Security cung cấp. `.roles("USER")` thêm authority `ROLE_USER` theo quy ước prefix mặc định. Password được hash trước khi đưa vào `UserDetails`. Phương thức `users(...)` trả bean mà Spring Security có thể dùng làm nguồn người dùng khi cấu hình authentication phù hợp.

**Đừng viết:**

```java
// Phản ví dụ: lưu plaintext trong UserDetails thay vì hash thích hợp.
User.withUsername("alice")
    .password("demo-pass")
    .roles("USER")
    .build();
```

Khi có `BCryptPasswordEncoder`, một password không được hash như vậy không khớp quy tắc xác minh và có thể làm login thất bại. Trong mọi trường hợp, đưa mật khẩu thật vào source là rủi ro không chấp nhận được trong production.

### 4.2. Roles và authorities

```java
UserDetails reader = User.withUsername("reader")
    .password(encoder.encode("demo-pass"))
    .roles("USER")
    .build();

UserDetails writer = User.withUsername("writer")
    .password(encoder.encode("demo-pass"))
    .authorities("ROLE_USER", "TASK_WRITE")
    .build();

UserDetails admin = User.withUsername("admin")
    .password(encoder.encode("demo-pass"))
    .roles("ADMIN")
    .build();
```

| Cách tạo | Authority được cấp | Rule tương ứng |
| --- | --- | --- |
| `roles("USER")` | `ROLE_USER` | `hasRole("USER")` |
| `roles("ADMIN")` | `ROLE_ADMIN` | `hasRole("ADMIN")` |
| `authorities("TASK_WRITE")` | `TASK_WRITE` | `hasAuthority("TASK_WRITE")` |
| `authorities("ROLE_USER", "TASK_WRITE")` | Cả hai giá trị | `hasRole("USER")` và `hasAuthority("TASK_WRITE")` có thể được dùng |
| `roles("USER", "ADMIN")` | `ROLE_USER`, `ROLE_ADMIN` | User có cả hai role |

**Chú ý prefix:** `hasRole("ADMIN")` thường tìm `ROLE_ADMIN`. Không dùng `roles("ROLE_ADMIN")` trong builder vì `roles` đã xử lý prefix; khi cần gán chuỗi authority chính xác, dùng `authorities("ROLE_ADMIN")`.

Một user có quyền `TASK_WRITE` chưa tự động có quyền `ROLE_ADMIN`. Không cấp các authority cấp quản trị rộng chỉ để test một endpoint ghi.

### 4.3. Trạng thái tài khoản

Spring Security `UserDetails` cung cấp các kiểm tra:

| Thuộc tính | Ý nghĩa khi true | Lệnh builder để tạo trạng thái chặn |
| --- | --- | --- |
| `isEnabled()` | Tài khoản đang được phép xác thực | `disabled(true)` |
| `isAccountNonLocked()` | Tài khoản không bị khóa | `accountLocked(true)` |
| `isAccountNonExpired()` | Tài khoản chưa hết hạn | `accountExpired(true)` |
| `isCredentialsNonExpired()` | Credential chưa hết hạn | `credentialsExpired(true)` |

Ví dụ:

```java
UserDetails locked = User.withUsername("locked")
    .password(encoder.encode("demo-pass"))
    .roles("USER")
    .accountLocked(true)
    .build();
```

Dù password đúng, `DaoAuthenticationProvider` thường từ chối login nếu account bị khóa. Với HTTP Basic, client có thể chỉ thấy `401`. Để kiểm tra nguyên nhân kỹ thuật, dùng provider-level test và `LockedException`, không thiết kế response phân biệt quá mức khiến đối tượng ngoài có thể dò trạng thái tài khoản.

### 4.4. PasswordEncoder là thiết yếu

`BCryptPasswordEncoder` tạo password hash có salt:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
```

Khi test:

```java
String encoded = passwordEncoder.encode("demo-pass");
boolean valid = passwordEncoder.matches("demo-pass", encoded);
```

`valid` phải true. **Đừng so sánh hai kết quả `encode(...)` bằng `equals`**: bcrypt sử dụng salt, nên cùng một plaintext thường sinh hash khác nhau. Sử dụng `matches(rawPassword, storedHash)`. Với chính sách password mới, ngoài thuật toán hash cần quản lý secret, reset, điều kiện phức tạp hợp lý và giới hạn brute force.

Spring Security cũng có `DelegatingPasswordEncoder`, dùng prefix như `{bcrypt}` để chọn thuật toán. Hai trường hợp khác nhau:

```text
BCryptPasswordEncoder trực tiếp:
    password được lưu là "$2a$..." (không cần {bcrypt} prefix)

DelegatingPasswordEncoder:
    password được lưu thường là "{bcrypt}$2a$..."
```

Không trộn trực tiếp BCryptPasswordEncoder với một giá trị lưu kèm `{bcrypt}` rồi kỳ vọng always matches; cấu hình encoder phải phù hợp với định dạng stored hash.

### 4.5. withDefaultPasswordEncoder, {noop} và password mẫu

Tài liệu Spring Security có ví dụ `User.withDefaultPasswordEncoder()` hoặc tiền tố `{noop}` để học nhanh, nhưng:

- `User.withDefaultPasswordEncoder()` chỉ phù hợp demo/bắt đầu học và bị đánh dấu không phù hợp production. Password plaintext trong source vẫn lộ qua Git/decompile, dù builder hash nó trước khi lưu.
- `{noop}` cho phép password không mã hóa/hashing phù hợp chỉ với ví dụ đặc biệt; không nên chọn làm cấu hình mật khẩu thực tế.
- Với một bài test có mật khẩu cố định, có thể dùng BCrypt và test fixture mẫu không chứa thông tin cá nhân. Đừng để fixture trở thành cấu hình production.
- Khi không muốn dự án chứa secret trong source, nhập qua test configuration/secret injection phù hợp; password chỉ tồn tại trong process test và không được log.

## 5. Quan hệ giữa Spring Boot default user và manager bạn tự tạo

Với Spring Boot MVC có `spring-boot-starter-security`, nếu ứng dụng chưa có cấu hình identity phù hợp, Boot có thể tạo user in-memory mặc định tên `user` và mật khẩu ngẫu nhiên được ghi vào log để phát triển. Một phần quá trình này do `UserDetailsServiceAutoConfiguration` đảm nhiệm.

Khi bạn tạo bean `InMemoryUserDetailsManager` của mình (nó là một `UserDetailsService`), **auto-configuration tạo generated user có thể nhường quyền** theo điều kiện đã có nguồn người dùng. Vì vậy:

```text
Ban đầu:
  spring-boot-starter-security
  -> Boot có thể tạo user mặc định: username=user, password ngẫu nhiên

Sau khi thêm bean:
  @Bean InMemoryUserDetailsManager users(...)
  -> Ứng dụng dùng user mẫu bạn khai báo, ví dụ alice/writer/admin
  -> Không tự suy ra default user "user" vẫn tồn tại

Nhưng:
  Tạo UserDetailsService không có nghĩa đã thay URL authorization.
  Tạo SecurityFilterChain không tự đảm bảo generated user biến mất.
```

Đây là hai trách nhiệm riêng:

- **Authentication source:** `InMemoryUserDetailsManager`/`UserDetailsService` cung cấp user, hash và authorities.
- **HTTP authorization:** `SecurityFilterChain`/`authorizeHttpRequests` quyết định endpoint nào public, user nào được vào.

Một sai lầm phổ biến là chỉ tạo bean user rồi tưởng `GET /public` tự public, hoặc chỉ thêm `requestMatchers("/admin").hasRole("ADMIN")` mà không có user nào sở hữu `ROLE_ADMIN`.

Nếu project thêm OAuth2 Resource Server/OIDC/SAML hoặc authentication provider riêng, điều kiện Boot auto-configuration có thể khác. Kiểm tra bean thực tế và test HTTP; đừng dựa vào mật khẩu generated trong log nếu đã chủ động quản lý source.

## 6. Demo đầy đủ: Spring Boot + InMemoryUserDetailsManager

**Mục tiêu demo:**

- `GET /public` không cần login.
- `GET /me` cần authentication.
- `GET /admin` yêu cầu `ROLE_ADMIN`.
- `POST /tasks` yêu cầu `TASK_WRITE`, và vẫn được CSRF protection kiểm tra.
- Một user `locked` bị từ chối dù password đúng.
- Test request bằng HTTP Basic qua chính `SecurityFilterChain` và test đọc dữ liệu manager.

**Version được cố định để tái hiện bài:** Java 17+, Spring Boot `3.5.16`, Spring Security 6.5.x do Boot BOM quản lý. Spring Boot 3.5.16 được phát hành ngày 25/06/2026 và là bản OSS cuối của nhánh 3.5. Khi triển khai production mới, chọn dòng Boot còn được hỗ trợ (như Boot 4.x) và kiểm tra lại thay đổi của Security 7. Các user demo không dành cho production.

### 6.1. Cấu trúc tệp

```text
inmemory-users-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/inmemory/InMemoryDemoApplication.java
    └── test/
        └── java/demo/inmemory/
            ├── InMemoryHttpSecurityTests.java
            └── InMemoryManagerUnitTests.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>inmemory-users-demo</artifactId>
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
```

### 6.3. Ứng dụng Java đầy đủ

Tạo `src/main/java/demo/inmemory/InMemoryDemoApplication.java`:

```java
package demo.inmemory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class InMemoryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(InMemoryDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        UserDetails writer = User.withUsername("writer")
            .password(encoder.encode("demo-pass"))
            .authorities("ROLE_USER", "TASK_WRITE")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-pass"))
            .roles("ADMIN")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .accountLocked(true)
            .build();

        return new InMemoryUserDetailsManager(
            alice, writer, admin, locked);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/tasks")
                    .hasAuthority("TASK_WRITE")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(Customizer.withDefaults())
            // CSRF vẫn bật để tách kiểm tra CSRF khỏi authority.
            .csrf(Customizer.withDefaults())
            .build();
    }
}

@RestController
class DemoRoutes {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String currentUser(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }

    @PostMapping("/tasks")
    String createTask(Authentication authentication) {
        // Chỉ mô phỏng thao tác tạo, không có database.
        return "created:" + authentication.getName();
    }
}
```

**Đọc code đúng lớp trách nhiệm:**

1. `users(...)` là bean `InMemoryUserDetailsManager`, Spring Security dùng nó làm nguồn người dùng. Password được hash bằng một `PasswordEncoder` bean chung.
2. Alice chỉ có `ROLE_USER`. Writer có cả `ROLE_USER` và `TASK_WRITE`. Admin chỉ có `ROLE_ADMIN`. Locked có password đúng nhưng không được xác thực do trạng thái tài khoản.
3. `securityFilterChain(...)` xác định quyền HTTP. `/public` public vì `permitAll()`, không phải vì tên path hoặc username nào đó. `anyRequest().denyAll()` đóng những route chưa khai báo trong phạm vi chain.
4. HTTP Basic nhận credential từ header và chuyển vào authentication provider. In-memory manager cung cấp user record và hash để provider kiểm tra.
5. `SessionCreationPolicy.STATELESS` chọn demo “mỗi request mang credential”; không dùng login session để tái sử dụng Alice ở request sau. Điều này làm bài test dễ chứng minh request độc lập.
6. CSRF protection vẫn được bật: `POST /tasks` có thể bị `403` ngay cả khi user có quyền `TASK_WRITE` nếu thiếu token. Trong ứng dụng browser dùng Basic/cookie credential tự gửi, CSRF có ý nghĩa riêng; không tắt chỉ để làm curl POST chạy.
7. Endpoint trả chuỗi tối thiểu, không trả `UserDetails` hay hash ra client. Đối với ứng dụng thật, DTO cần được thiết kế không lộ credential.
8. Đây là danh tính **mẫu cho học tập**. Không dùng password `demo-pass` hoặc in-memory users này làm cấu hình thực tế trên máy chủ public.

### 6.4. Kiểm tra bằng curl (kết nối localhost)

Ở thư mục dự án:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Sau khi server khởi động ở `localhost:8080`:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u writer http://localhost:8080/me
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
curl -i -u locked http://localhost:8080/me
```

`curl -u alice` (không ghi mật khẩu vào command) sẽ hỏi password. Nhập `demo-pass` trên máy local. Trên PowerShell cũ có thể cần `curl.exe` thay vì alias `curl`.

| Thử nghiệm | Status kỳ vọng | Lý do |
| --- | --- | --- |
| `GET /public` anonymous | 200 | `permitAll` |
| `GET /me` anonymous | 401 | HTTP Basic yêu cầu xác thực |
| `GET /me` với Alice password đúng | 200, body `me:alice` | User tồn tại, BCrypt matches |
| `GET /me` với writer đúng | 200, body `me:writer` | User tồn tại, có authentication |
| `GET /admin` với Alice đúng | 403 | Không có `ROLE_ADMIN` |
| `GET /admin` với admin đúng | 200, body `admin` | Có `ROLE_ADMIN` |
| `GET /me` với locked đúng | 401 | Provider không chấp nhận account locked |

Nếu dùng sai mật khẩu, `GET /me` cũng thường nhận `401`. Đừng tiết lộ quá chi tiết “username có tồn tại/đang bị khóa” trong response công khai; HTTP response nên tránh username enumeration.

**HTTP Basic không mã hóa password trên đường truyền**; Base64 chỉ là biểu diễn của `username:password`. Tất cả lệnh HTTP này chỉ dành cho `localhost`. Với hệ thống thật, bắt buộc HTTPS và phương thức identity phù hợp. Để thử POST có CSRF token hợp lệ, dùng MockMvc ở phần sau.

## 7. Integration test: dùng user in-memory nhưng đi qua xác thực thật

Tạo `src/test/java/demo/inmemory/InMemoryHttpSecurityTests.java`:

```java
package demo.inmemory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class InMemoryHttpSecurityTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    InMemoryUserDetailsManager users;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void userStoreContainsEncodedPasswordsAndExpectedRoles() {
        assertTrue(users.userExists("alice"));
        assertTrue(users.userExists("writer"));
        assertTrue(users.userExists("admin"));
        assertTrue(users.userExists("locked"));
        assertFalse(users.userExists("nobody"));

        UserDetails alice = users.loadUserByUsername("alice");
        assertEquals("alice", alice.getUsername());
        assertFalse(alice.getPassword().equals("demo-pass"));
        assertTrue(encoder.matches("demo-pass", alice.getPassword()));
        assertTrue(alice.isEnabled());
        assertTrue(alice.isAccountNonLocked());

        UserDetails locked = users.loadUserByUsername("locked");
        assertFalse(locked.isAccountNonLocked());
    }

    @Test
    void checksRealPasswordViaHttpBasic() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:alice"));

        mvc.perform(get("/me").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("nobody", "demo-pass")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("locked", "demo-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void rolesAndFineGrainedAuthoritiesHaveDifferentEffects()
            throws Exception {

        mvc.perform(get("/admin")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));

        // ROLE_ADMIN không tự có TASK_WRITE.
        mvc.perform(post("/tasks")
                .with(httpBasic("admin", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        // Alice cũng không có TASK_WRITE.
        mvc.perform(post("/tasks")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfAndPermissionMustBothPass() throws Exception {
        // Writer đủ TASK_WRITE nhưng thiếu CSRF token.
        mvc.perform(post("/tasks")
                .with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isForbidden());

        // Có token nhưng token sai cũng bị từ chối.
        mvc.perform(post("/tasks")
                .with(httpBasic("writer", "demo-pass"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        // Có quyền và CSRF hợp lệ thì controller chạy.
        mvc.perform(post("/tasks")
                .with(httpBasic("writer", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:writer"));
    }

    @Test
    void statelessRequestsDoNotInheritPreviousAuthentication()
            throws Exception {

        mvc.perform(get("/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk());

        // Request sau không có Authorization header vẫn anonymous.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        // Đường chưa được cấp quyền bị deny.
        mvc.perform(get("/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

**Tại sao test này có ý nghĩa?**

- `@SpringBootTest` nạp application context/bean thật; `@AutoConfigureMockMvc` gắn Spring MVC và filter chain cho request test.
- `httpBasic("alice", "demo-pass")` thêm header `Authorization: Basic ...`. Spring Security thực sự dùng `DaoAuthenticationProvider` + `InMemoryUserDetailsManager` + `PasswordEncoder` để kiểm tra mật khẩu.
- `users.loadUserByUsername` cho phép xác minh fixture và hash; đó là test trực tiếp nguồn user, không thay thế integration test qua HTTP.
- Các user có quyền khác nhau chứng minh login thành công chưa có nghĩa được gọi mọi endpoint.
- `csrf()` và `csrf().useInvalidToken()` kiểm tra độc lập exploit protection và authority. Thiếu CSRF có thể bị 403 trước khi authentication filter kết thúc, vì vậy **đừng suy ra chỉ từ một mã 403 rằng password đã được chấp nhận**.
- Test request kế tiếp không credential chứng minh không tự tái sử dụng authenticated principal trong demo stateless.
- Chỉ đọc `users` trong integration test, không mutate bean dùng chung; những test sửa user được chuyển sang unit test với một instance mới.

Nếu build/test đúng môi trường, kỳ vọng các assertion đạt. Đây là mã được cung cấp để chạy; kết quả `BUILD SUCCESS` là **kỳ vọng**, không phải kết quả đã thực thi trong bài viết này.

## 8. Unit test độc lập: thêm, sửa, xóa user mà không làm nhiễm test khác

`InMemoryUserDetailsManager` là object có **trạng thái thay đổi**. Nếu trong một `@SpringBootTest` bạn gọi `deleteUser("alice")` trên bean dùng chung, bài test HTTP khác có thể bắt đầu thất bại tùy thứ tự chạy, test context cache hoặc chạy song song. Vì vậy hãy tạo **manager mới trong mỗi test mutating**, không chỉnh bean của ứng dụng đang phục vụ các test khác.

Tạo `src/test/java/demo/inmemory/InMemoryManagerUnitTests.java`:

```java
package demo.inmemory;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class InMemoryManagerUnitTests {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder();

    @Test
    void createUpdateChangeAndDeleteUserInOneIsolatedManager() {
        InMemoryUserDetailsManager users =
            new InMemoryUserDetailsManager();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode("first-pass"))
            .authorities("ROLE_USER", "TASK_WRITE")
            .build();

        users.createUser(editor);
        assertTrue(users.userExists("editor"));
        assertTrue(encoder.matches("first-pass",
            users.loadUserByUsername("editor").getPassword()));

        // Không được tạo trùng username trong cùng manager.
        assertThrows(IllegalArgumentException.class,
            () -> users.createUser(editor));

        // Thay quyền và password bằng một UserDetails mới.
        UserDetails updated = User.withUserDetails(editor)
            .password(encoder.encode("second-pass"))
            .authorities("ROLE_USER")
            .build();

        users.updateUser(updated);

        UserDetails loaded = users.loadUserByUsername("editor");
        assertTrue(encoder.matches("second-pass", loaded.getPassword()));
        assertFalse(loaded.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch("TASK_WRITE"::equals));

        // API updatePassword nhận password đã được encode.
        users.updatePassword(updated, encoder.encode("third-pass"));

        UserDetails withNewPassword =
            users.loadUserByUsername("editor");
        assertTrue(encoder.matches("third-pass",
            withNewPassword.getPassword()));

        users.deleteUser("editor");
        assertFalse(users.userExists("editor"));
        assertThrows(UsernameNotFoundException.class,
            () -> users.loadUserByUsername("editor"));
    }

    @Test
    void daoProviderChecksPasswordAndAccountLock() {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("correct-pass"))
            .roles("USER")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password(encoder.encode("correct-pass"))
            .roles("USER")
            .accountLocked(true)
            .build();

        InMemoryUserDetailsManager users =
            new InMemoryUserDetailsManager(alice, locked);

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager authenticationManager =
            new ProviderManager(provider);

        Authentication verified = authenticationManager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "correct-pass"));

        assertTrue(verified.isAuthenticated());
        assertEquals("alice", verified.getName());
        assertTrue(verified.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch("ROLE_USER"::equals));

        assertThrows(BadCredentialsException.class,
            () -> authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "wrong-pass")));

        assertThrows(LockedException.class,
            () -> authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "locked", "correct-pass")));
    }
}
```

**Giải thích:**

- Mỗi test tự tạo `new InMemoryUserDetailsManager(...)`, vì vậy create/delete/update không làm đổi dữ liệu được Spring Boot application context dùng ở `InMemoryHttpSecurityTests`.
- `createUser` từ chối username tồn tại trong cùng manager. `updateUser` thay user record theo `UserDetails` mới; test kiểm tra quyền `TASK_WRITE` đã mất và hash mới hoạt động.
- `updatePassword` nhận **password đã mã hóa** trong ví dụ này. Không gửi plaintext tới manager rồi tưởng nó tự BCrypt hash. Đây là API phục vụ việc cập nhật credential theo contract, không phải một REST endpoint cho bất kỳ ai đổi password.
- `DaoAuthenticationProvider` và `ProviderManager` được tạo trực tiếp để test kết quả xác thực bằng source thật. Sai password ném `BadCredentialsException`; account bị khóa ném `LockedException`. Ở HTTP production, hai tình huống có thể cùng trả `401` để hạn chế dò thông tin tài khoản.
- Test dùng BCrypt hash được tạo ngay trong process, không copy hash cố định từ môi trường khác. Hash được so bằng `matches`.

### 8.1. Cẩn thận với changePassword(old, new)

`UserDetailsManager.changePassword(oldPassword, newPassword)` là API riêng với ngữ nghĩa “đổi password của **current authenticated user**”. `InMemoryUserDetailsManager` có thể sử dụng `SecurityContextHolder` để tìm user hiện tại và **chỉ xác minh mật khẩu cũ nếu một `AuthenticationManager` phù hợp đã được gắn vào manager**. Vì vậy không nên tự đưa thẳng method này thành endpoint tự phục vụ cho user và cho rằng tất cả kiểm soát đã có sẵn.

Khi thiết kế đổi password thực sự, cần:

1. Xác minh current user từ context tin cậy, không lấy username tuỳ ý do client gửi.
2. Bắt buộc re-authentication hoặc policy step-up thích hợp.
3. Hash password mới theo encoder/password policy; không nhận “newHash” do client tự chỉ định nếu có thể làm sai định dạng.
4. Kiểm tra CSRF cho web cookie auth và giới hạn tần suất yêu cầu.
5. Cập nhật user store bền vững, thu hồi session/token khi cần và ghi audit an toàn.
6. Test toàn bộ flow; không chỉ assert `userExists`.

Trong **bài học**, dùng `updateUser`/`updatePassword` trực tiếp trên instance mới là đủ để minh họa kỹ thuật. Production nên dùng user repository hoặc IdP quản lý vòng đời đầy đủ.

## 9. @WithMockUser khác với HTTP Basic dùng InMemoryUserDetailsManager thế nào?

Đây là phân biệt quan trọng nhất khi **kiểm thử security**.

### 9.1. Dùng mock user

```java
@Test
@WithMockUser(username = "ghost-admin", roles = "ADMIN")
void anAdminRoleCanOpenAdminEndpoint() throws Exception {
    mvc.perform(get("/admin"))
        .andExpect(status().isOk());
}
```

Đây là snippet đặt trong test class có `MockMvc mvc`, các import JUnit và `WithMockUser` tương ứng. User `ghost-admin` **không cần tồn tại trong `InMemoryUserDetailsManager`**; annotation cung cấp authentication giả lập trong test. Điều này rất tốt để kiểm tra **authorization rule** mà không phụ thuộc cơ sở dữ liệu hay password.

Nhưng test xanh **không chứng minh**:

- Có account `ghost-admin` thật.
- Password hash/encoder hoạt động.
- `DaoAuthenticationProvider` chọn đúng source.
- Login form hoặc Basic filter xác minh credential thành công.
- Account locked/disabled/expired bị từ chối đúng.

### 9.2. Dùng Basic header với manager thật

```java
mvc.perform(get("/admin")
        .with(httpBasic("admin", "demo-pass")))
    .andExpect(status().isOk());
```

Khi đã cấu hình Spring Security filter chain trong MockMvc, request gửi Basic credential tới filter, provider tải user từ in-memory manager và so password với hash. Nó kiểm tra đồng thời **authentication và authorization** trong application context.

### 9.3. Bảng lựa chọn

| Cần chứng minh | `@WithMockUser` / `user()` | `httpBasic(...)` + InMemory manager |
| --- | --- | --- |
| URL yêu cầu ROLE_ADMIN | Phù hợp | Phù hợp |
| Rule `hasAuthority("TASK_WRITE")` | Phù hợp | Phù hợp |
| PasswordEncoder.matches đúng | **Không** | **Có** |
| User có tồn tại trong source không | **Không** | **Có** |
| Account locked/disabled có bị từ chối | Không, trừ khi mô phỏng theo chính sách | Có, nếu provider thực thi account checks |
| Tích hợp BasicAuthenticationFilter với provider | Không | Có |
| Kiểm thử session/form login thực | Không | Basic test không thay form-login test |
| Không phụ thuộc test identity provider | Có | Có, vì source in-memory |
| Tốc độ đơn vị khi chỉ test policy | Thường rất thuận tiện | Cần Spring/context hoặc provider phù hợp |

Tùy mục tiêu, hãy dùng cả hai loại test. Test controller/service được phép dùng mock user để tập trung chính sách. Test cấu hình authentication phải có ít nhất một đường **credential thật** qua provider/filter.

## 10. Dữ liệu test nên sống ở đâu?

### 10.1. Tránh đặt test users vào cấu hình production

Demo trên đặt test users trong `src/main` chỉ để người học chạy ngay trên localhost. Trong sản phẩm thực, cách này có thể khiến các tài khoản “demo-pass” bị đóng gói vào bản phát hành. Nên tách:

- Production: identity provider, database hoặc user service được quản lý, có chính sách secret và audit rõ.
- Integration test: `InMemoryUserDetailsManager` với password giả, profile dành riêng test hoặc `@TestConfiguration`.
- Unit test: tạo instance InMemory mới trong method hoặc `@BeforeEach`, không phụ thuộc singleton application context.

Ví dụ khi dùng **profile** có chủ đích:

```java
@Configuration(proxyBeanMethods = false)
@Profile("test")
class TestUsersConfiguration {

    @Bean
    InMemoryUserDetailsManager testUsers(PasswordEncoder encoder) {
        UserDetails tester = User.withUsername("tester")
            .password(encoder.encode("test-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(tester);
    }
}
```

Đây là snippet cần các import Spring/Security tương ứng và được đặt trong module test hoặc cấu hình không đi vào bản production. Nếu đặt trong `src/test/java`, class không có trong production artifact. Với profile khác, bảo đảm ứng dụng có source người dùng thực tế; **không** để một profile test lẫn vào deployment public.

Kích hoạt profile đúng trong bài test:

```java
@SpringBootTest
@ActiveProfiles("test")
@AutoConfigureMockMvc
class ProfileBasedSecurityTests {
    // Test sẽ thấy các bean ứng với active profile "test".
}
```

Tránh khai báo hai bean `UserDetailsService` không phân biệt rồi để provider không biết nên dùng bean nào. Với dự án dùng `@Primary` hoặc `@TestConfiguration` để override source, phải xác định rõ điều kiện và lựa chọn duy nhất. Khi test cấu hình Production, nên test production security chain theo hướng độc lập với fake users.

### 10.2. Vì sao nên có một manager mới cho mỗi test thay đổi dữ liệu?

Spring Test có cơ chế cache `ApplicationContext` để tiết kiệm thời gian. `InMemoryUserDetailsManager` là một bean giữ **state**; gọi `updateUser`/`deleteUser` trong test có thể thay đổi dữ liệu mà test khác nhìn thấy ở cùng context. Khi các test chạy song song, kết quả càng khó ổn định.

Các cách hợp lý:

- Dùng `new InMemoryUserDetailsManager()` trong test unit cần create/update/delete.
- Dùng fixture factory tạo manager riêng cho từng test.
- Với integration test không cần sửa user, chỉ đọc bean và thử request HTTP.
- Nếu thật sự phải mutate bean trong context, tái tạo/reset state bằng chiến lược kiểm soát rõ (có thể dùng `@DirtiesContext` nhưng tốn thời gian), tránh làm mặc định cho mọi test.
- Không dùng `@TestMethodOrder` như cách chữa state bị rò; test tốt không nên phụ thuộc vào bài test trước chạy thành công.

### 10.3. Không đặt fixture secret trong log hoặc snapshot

Ngay cả `test-pass` là dữ liệu mẫu, việc ghi raw Basic header hoặc nguyên `Authentication` vào log có thể tạo thói quen xấu. Với dữ liệu người dùng thật, tuân thủ redaction/secret management và tránh đẩy thông tin vào issue/CI artifact. Trong test chỉ assert status, authority và tên tài khoản; không chụp giá trị cookie/password.

## 11. API CRUD của InMemoryUserDetailsManager: những ranh giới cần nhớ

### 11.1. createUser

`createUser(UserDetails user)` thêm account vào store hiện tại. Nếu username đã tồn tại, implementation ném lỗi thay vì âm thầm cấp quyền đè lên tài khoản cũ. Validate đầu vào và sử dụng API đăng ký user đúng policy trong sản phẩm thật.

### 11.2. updateUser

`updateUser(UserDetails user)` thay thông tin user có sẵn. Khi chỉ muốn thay một authority, xây `UserDetails` mới giữ các thuộc tính còn lại một cách rõ ràng; `User.withUserDetails(existing)` giúp sao chép cơ sở của user. Kiểm tra lại account flags và password hash sau update để tránh làm tài khoản bất ngờ bị khóa/mở.

### 11.3. deleteUser

`deleteUser(username)` xóa user khỏi manager đang chạy. Nó **không tự thu hồi** JWT đã cấp hoặc authenticated session ở một filter chain khác. Trong hệ thống thật, deprovisioning còn cần invalidate session, revoke token/refresh token, event/audit và bảo vệ dữ liệu.

### 11.4. userExists và loadUserByUsername

`userExists(username)` cho phép kiểm tra sự tồn tại trong store. `loadUserByUsername(username)` trả `UserDetails` hoặc ném `UsernameNotFoundException`. **Không expose trực tiếp** những method này thành API công khai cho phép người lạ dò username; trả thông báo đăng nhập chung và rate limiting khi cần.

### 11.5. updatePassword và changePassword

`updatePassword(UserDetails user, String newPassword)` nhận một password đã mã hóa để cập nhật user được chỉ định; thường được dùng bởi cơ chế nâng cấp hash qua `UserDetailsPasswordService`. `changePassword(oldPassword, newPassword)` gắn với người dùng hiện tại và điều kiện re-authentication nếu manager được cấu hình. Hai method khác về ý định; không đưa chúng ra REST endpoint không kiểm soát.

### 11.6. Mức bảo đảm khi nhiều request cùng sửa

Implementation lưu trữ trong-memory cung cấp các thao tác quản lý user trong một process, nhưng đừng thiết kế account lifecycle sản xuất dựa vào assumption “mọi cập nhật quyền là transactional và ngay lập tức nhất quán trên cluster”. Đối với thay role đồng thời với login, session caching, revoke hoặc nhiều replica, cần kho persistent và policy nhất quán với ứng dụng của bạn.

## 12. Các trường hợp dễ hiểu sai

### Trường hợp A: Có user nhưng vẫn 403

Alice có username/password đúng và provider đã xác thực; request `GET /admin` trả `403` vì thiếu `ROLE_ADMIN`. Tạo user trong manager **không** tự cấp mọi URL permission. Test role-specific paths riêng.

### Trường hợp B: POST bị 403 dù writer có TASK_WRITE

CSRF filter có thể chặn POST trước bước phân quyền. Khi test, gửi `csrf()` và kiểm tra lại. Đừng tắt CSRF toàn bộ chỉ để POST trả 200; phải xét credential tự gắn trong browser và threat model thực tế.

### Trường hợp C: Lưu hash nhưng login 401

Có thể đang dùng `DelegatingPasswordEncoder` đòi prefix `{bcrypt}` trong khi stored value không có prefix, hoặc dùng BCryptPasswordEncoder với stored value có prefix. Kiểm tra **encoder bean** và định dạng stored hash; không đổ lỗi cho InMemoryUserDetailsManager trước.

### Trường hợp D: Tạo bean user rồi vẫn thấy account “user” từ Boot

Có thể bạn đang chạy một profile/context khác, có nhiều user stores, hoặc bean custom không được component scan/auto-configuration thấy. Kiểm tra runtime context, active profiles và conditional configuration. Đừng dựa vào sự tồn tại của username “user” ở một lần chạy cũ.

### Trường hợp E: Đổi password trong test A làm test B thất bại

Test A mutate singleton manager thuộc cached `ApplicationContext`. Tách test mutating bằng manager mới; đừng cố sắp thứ tự test cho “ổn định”.

### Trường hợp F: @WithMockUser đăng nhập ghost-admin thành công

Đây là hành vi hợp lý của mock security context. Test đó chỉ chứng minh rule `hasRole("ADMIN")` hoạt động. Muốn kiểm tra user store/BCrypt, dùng `httpBasic(...)` hoặc gọi provider thật.

### Trường hợp G: Restart rồi user vừa tạo mất

In-memory user store không có persistence. Nếu cần giữ user qua restart, dùng database, LDAP hoặc IdP. Việc serialize một `HashMap` thủ công để cứu tài khoản demo không phải hướng quản lý danh tính sản xuất thích hợp.

### Trường hợp H: Một replica có user, replica kia không có

Hai JVM có bộ nhớ độc lập; copy code không tạo shared storage. Với production dùng nhiều replica, phải dùng source dùng chung và session/token/revocation policy phù hợp.

### Trường hợp I: Đã xóa user nhưng session cũ vẫn vào được

Nếu request sử dụng authentication đã lưu trong session, nó không nhất thiết tải lại user từ store ở mỗi request. Deletion của manager không tự làm mọi session của người đó biến mất. Thiết kế session invalidation/reauth và kiểm tra quyền ở domain cần là bước riêng.

### Trường hợp J: Cho client gửi role trong JSON

`InMemoryUserDetailsManager` là nguồn user do server kiểm soát; không lấy `roles` từ request body rồi tự tạo account admin mà không có policy. Role assignment phải có quyền quản trị, kiểm tra người thực hiện và audit.

## 13. Học sâu hơn: In-memory users, session và quyền thay đổi

Một request HTTP Basic stateless có thể đi qua provider ở **mỗi request**. Nếu Alice được cấp/bỏ `TASK_WRITE` trong in-memory store, request mới được xác thực lại có thể thấy quyền mới. Nhưng với session-based form login, user đã authenticated có thể có `Authentication` chứa authorities cũ trong session và không tự lấy lại user ở mỗi request.

```text
Request đầu: Alice đăng nhập
 -> UserDetails lấy authorities [ROLE_USER, TASK_WRITE]
 -> Authentication được lưu vào session

Admin sửa user store:
 -> Alice mới chỉ có [ROLE_USER]

Request sau với cùng session:
 -> Nếu context cũ được khôi phục nguyên, authorities có thể còn TASK_WRITE
 -> Không được giả định thay user store = thu hồi tức thì mọi session
```

Muốn thay đổi quyền có hiệu lực tức thì, ứng dụng cần chiến lược riêng: invalidate/revoke session, làm mới principal, kiểm tra quyền tại resource, hoặc version hóa grant. Điều này vượt phạm vi bộ nhớ local và trở nên quan trọng khi có multi-instance.

**Quyền truy cập tài nguyên:** Ngay cả khi Alice có `TASK_WRITE` thì vẫn phải xác minh có được tạo task trong tenant X hay không; không dựa vào quyền route để cho Alice thay thông tin của tenant Y.

## 14. Bảng kiểm thử cần có cho một bài học hoàn chỉnh

| Nhóm | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Source | `userExists("alice")` | true |
| Source | `loadUserByUsername("nobody")` | UsernameNotFoundException |
| Hash | `encoder.matches(raw, storedHash)` | true với đúng password |
| Hash | So hai BCrypt hashes riêng biệt | Không cần bằng nhau |
| HTTP | `GET /public` anonymous | 200 |
| HTTP | `GET /me` anonymous | 401 với Basic entry point |
| HTTP | `GET /me` password đúng | 200 |
| HTTP | `GET /me` password sai | 401 |
| HTTP | `GET /me` user locked | 401; provider-level test xác nhận LockedException |
| Authz | `GET /admin` Alice | 403 |
| Authz | `GET /admin` admin | 200 |
| CSRF | `POST /tasks` writer thiếu token | 403 |
| CSRF | `POST /tasks` writer có token sai | 403 |
| Authz | `POST /tasks` Alice có CSRF | 403 vì thiếu TASK_WRITE |
| Authz | `POST /tasks` writer có CSRF | 200 |
| Isolation | CRUD trong manager mới | Không ảnh hưởng test HTTP khác |
| Isolation | Request mới không credential ở demo stateless | 401 |
| Safety | User bị xóa khỏi manager | Không tồn tại ở manager đó, chưa suy ra mọi session đã bị revoke |
| Domain | User từ tenant A truy cập object tenant B | Bị từ chối bởi service/resource policy |

Kết quả HTTP còn phụ thuộc `AuthenticationEntryPoint`, filter chain, CSRF và framework version; ma trận trên là hợp đồng **của demo trong bài**, không phải mọi ứng dụng Spring Security đều có cùng status nếu dùng form login hoặc OAuth2.

## 15. Mở rộng khi nào và bằng cách nào?

Khi mục tiêu là **học và test**, tiếp tục dùng InMemoryUserDetailsManager với fixture rõ ràng. Khi cần người dùng thật, chọn source theo ngữ cảnh:

| Lựa chọn | Điểm phù hợp | Điều cần thiết kế thêm |
| --- | --- | --- |
| `InMemoryUserDetailsManager` | Demo, unit/integration test, PoC ngắn | Cách tách khỏi production, test isolation |
| `JdbcUserDetailsManager` | Bài học JDBC schema mặc định hoặc ứng dụng đơn giản | Database, schema, migration, transaction, password reset |
| Custom `UserDetailsService` với JPA/repository | App có user domain riêng | Ánh xạ entity → UserDetails, cache, transaction, lockout, role policy |
| LDAP/Active Directory | Tổ chức có directory service | Kết nối an toàn, group mapping, lifecycle |
| OIDC/OAuth2 Identity Provider | SSO, đa ứng dụng, MFA | Trust issuer/audience, session/token, grant mapping |
| Reactive `MapReactiveUserDetailsService` | WebFlux demo và test | Reactor Context, WebFilterChain, reactive authentication |
| JWT Resource Server | API Bearer token từ issuer tin cậy | Decoder, chữ ký, expiry, issuer/audience, scope/authority mapping |

**Không nhất thiết phải tự xây bảng users** nếu tổ chức đã có IdP. Chọn nguồn danh tính theo cơ chế xác thực mà ứng dụng thực sự dùng. `UserDetailsService` đặc biệt liên quan username/password do `DaoAuthenticationProvider` kiểm tra; JWT không mặc nhiên đi qua manager in-memory này.

### Khi chuyển từ in-memory sang database

Giữ HTTP policy và test behavior ở mức contract, thay **source người dùng** một cách có chủ đích:

```text
Trước:
  DaoAuthenticationProvider
       |
       v
  InMemoryUserDetailsManager

Sau:
  DaoAuthenticationProvider
       |
       v
  Custom UserDetailsService -> UserRepository -> database
```

Bộ test có thể tiếp tục kiểm tra `401`, `403`, `200`, role/method, CSRF và owner/tenant. Chỉ thay fixture/setup thích hợp. Phân tách authentication provider, authorization rules và domain policy giúp migration dễ review.

## 16. Câu hỏi tự đánh giá

**Câu 1.** Có `InMemoryUserDetailsManager` rồi, Spring Security đã tự cấp `ROLE_ADMIN` cho mọi account chưa?

**Đáp án:** Chưa. Manager chỉ chứa user/authorities bạn khai báo. `roles("ADMIN")` tạo `ROLE_ADMIN` cho user tương ứng, còn filter chain cần rule `hasRole("ADMIN")` để bảo vệ route.

**Câu 2.** Vì sao `encoder.encode("x").equals(encoder.encode("x"))` có thể false với BCrypt dù mật khẩu giống nhau?

**Đáp án:** BCrypt sử dụng salt; mỗi lần encode có thể sinh hash khác. Dùng `encoder.matches("x", encodedHash)`.

**Câu 3.** `@WithMockUser(username="admin", roles="ADMIN")` chạy được GET /admin. Điều đó chứng minh mật khẩu admin đúng không?

**Đáp án:** Không. Mock user tạo SecurityContext test, không tải/so password với store. Dùng `httpBasic(...)` qua filter chain hoặc provider-level test để kiểm tra credential thật.

**Câu 4.** Bạn gọi `users.deleteUser("alice")` ở một test. Test khác `GET /me` với Alice bỗng nhận 401. Nguyên nhân?

**Đáp án:** Có thể hai test dùng cùng bean InMemory và Spring cached context, nên test trước đã xóa Alice. Test CRUD nên tạo manager riêng.

**Câu 5.** Vì sao writer có `TASK_WRITE` vẫn nhận 403 khi POST /tasks bằng curl?

**Đáp án:** Có thể CSRF token thiếu/sai, hoặc HTTP policy khác từ chối. Cần kiểm thử cả authority và CSRF; không tự động tắt CSRF.

**Câu 6.** Tạo user mới lúc runtime rồi restart app, tại sao user biến mất?

**Đáp án:** In-memory store không persist. Bean được tạo lại, chỉ chứa dữ liệu cấu hình ban đầu.

**Câu 7.** Alice có `ROLE_USER` và login đúng; có đọc được hóa đơn của Bob không?

**Đáp án:** Không thể suy ra từ role. Service phải kiểm tra quyền trên object, owner/tenant và context nghiệp vụ.

**Câu 8.** Tại sao API đổi password không nên gọi `changePassword` tùy tiện khi không cấu hình manager xác minh mật khẩu cũ?

**Đáp án:** Contract và implementation cho phép behavior phụ thuộc AuthenticationManager đã được gắn; nếu không reauthenticate đúng, code có thể bỏ qua bước kiểm tra quan trọng. Thiết kế endpoint đổi password cần re-auth/step-up, hash, CSRF và audit rõ ràng.

**Câu 9.** Hai Spring Boot replica đều có InMemoryUserDetailsManager. Admin cập nhật user ở replica A thì B có tự đổi không?

**Đáp án:** Không. Mỗi tiến trình có bộ nhớ riêng, không có shared persistence/synchronization.

**Câu 10.** Test nào xác minh xác thực thật, test nào chỉ xác minh phân quyền?

**Đáp án:** `httpBasic(...)` với application context/provider thật kiểm tra credential và URL policy; `@WithMockUser`/`user(...)` chủ yếu kiểm tra policy với principal giả lập.

## 17. Checklist thực hành

- [ ] Có hiểu manager là **user store** trong RAM, không phải authentication filter?
- [ ] Đã tạo bean `PasswordEncoder` và lưu password hash đúng định dạng?
- [ ] Không dùng `{noop}` hoặc `withDefaultPasswordEncoder` cho user thật?
- [ ] Đã phân biệt `roles("USER")` với `authorities("TASK_WRITE")` và prefix `ROLE_`?
- [ ] Test thành công, sai password, username không tồn tại, account locked và insufficient authority?
- [ ] Integration test có sử dụng HTTP Basic header để đi qua provider thực, ngoài test dùng mock principal?
- [ ] POST có CSRF protection được kiểm tra độc lập với permission?
- [ ] Có test request mới không kế thừa context của request trước khi dùng stateless?
- [ ] Test CRUD tạo manager mới và không mutate singleton state của suite?
- [ ] Các test fixtures nằm dưới `src/test` hoặc profile an toàn nếu dự án production?
- [ ] Không đưa demo accounts/password trong source production hoặc container public?
- [ ] Nếu account thay đổi/khóa/xóa, đã xem xét session/token cũ và multi-instance?
- [ ] Quyền actor trên đối tượng/tenant được kiểm tra ở service, không chỉ HTTP path?
- [ ] Version Java, Boot, Security và API phù hợp; Maven tests được chạy trong môi trường thật?

## 18. Ghi nhớ

1. **`InMemoryUserDetailsManager` lưu `UserDetails` trong RAM và implement `UserDetailsService`/`UserDetailsManager`** để học hoặc test nhanh.
2. **`DaoAuthenticationProvider` mới kiểm tra credential** cùng `PasswordEncoder`; manager cung cấp user, password hash, authorities và account state.
3. **`roles("ADMIN")` tạo `ROLE_ADMIN`**; `authorities("TASK_WRITE")` là permission riêng. Cần `SecurityFilterChain` để áp dụng chúng lên route.
4. **BCrypt so bằng `matches`**, không so hai hash với nhau và không lưu plaintext trong production.
5. **Mock user khác password authentication thực.** Dùng `@WithMockUser` để test quyền, dùng `httpBasic(...)`/provider để test đường credential.
6. **CRUD trên in-memory store có state**. Tạo manager riêng cho test mutate; thay đổi runtime không bền qua restart hoặc đồng bộ giữa nhiều JVM.
7. **Không dùng nó như kho user production**. Với user thật, cần persistence/IdP, audit, revoke/session, secret handling và policy tài nguyên.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html)
- [Spring Security 6.5 — InMemoryUserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html)
- [Spring Security 6.5 — UserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/UserDetailsManager.html)
- [Spring Security 6.5 — UserDetails / User Builder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Password Storage / PasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Testing HTTP Basic with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — Running a Test as a User](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security 6.5 — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot 3.5 — Spring Security Auto-Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Boot 3.5.16 Release and OSS Support](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
