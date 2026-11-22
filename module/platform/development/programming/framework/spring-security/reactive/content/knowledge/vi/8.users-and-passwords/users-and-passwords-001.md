# ReactiveUserDetailsService, UserDetails và mô hình dữ liệu người dùng

## 1. Bối cảnh và mục tiêu

Trong một ứng dụng **Spring Security reactive** (Spring WebFlux), xác thực username/password cần có cách tìm tài khoản mà có thể ghép vào chuỗi xử lý Reactor. `ReactiveUserDetailsService` đảm nhận bước **tra cứu người dùng theo username**, còn `UserDetails` là **mô hình dữ liệu bảo mật** mô tả tên đăng nhập, mật khẩu đã băm, quyền và trạng thái tài khoản. Đây là hai thành phần riêng, nhưng thường được dùng cùng một `ReactiveAuthenticationManager`.

Ví dụ: khi client gửi HTTP Basic với `reader:reader-pass`, server cần tra `reader`, nhận `UserDetails` có password hash và authorities, xác minh mật khẩu qua `PasswordEncoder`, kiểm tra trạng thái tài khoản, rồi mới tạo một `Authentication` đã xác thực. **Chỉ tìm thấy user không đồng nghĩa với đăng nhập thành công.**

Bạn sẽ học được cách:
1. Đọc hợp đồng `ReactiveUserDetailsService.findByUsername(String)` và ba khả năng của một `Mono<UserDetails>`.
2. Hiểu đầy đủ các thuộc tính trong `UserDetails`, bao gồm authorities và bốn trạng thái tài khoản.
3. Phân biệt entity/domain model, security user model và principal trả cho tầng HTTP.
4. Khai báo user mẫu qua `MapReactiveUserDetailsService`, `User.withUsername(...)` và `PasswordEncoder`.
5. Kết nối user store với `UserDetailsRepositoryReactiveAuthenticationManager` và `SecurityWebFilterChain` trong WebFlux.
6. Thiết kế adapter từ kho dữ liệu reactive thật, xử lý user không tồn tại, bảo vệ password hash và tránh I/O blocking.
7. Kiểm chứng hành vi bằng `StepVerifier`, `WebTestClient` và các trường hợp 200/401/403.

**Phạm vi:** mô hình người dùng và hợp đồng truy vấn trong Spring Security **reactive**, trọng tâm là username/password. Bài không triển khai database production, quản lý phiên, JWT/OAuth2 hay đăng nhập liên kết.

## 2. `ReactiveUserDetailsService` là gì?

Đây là interface thuộc package `org.springframework.security.core.userdetails`. Chữ ký khái niệm:

```java
public interface ReactiveUserDetailsService {
    Mono<UserDetails> findByUsername(String username);
}
```

Đây là **chữ ký API rút gọn để giải thích**, không cần tạo file interface này vì Spring Security đã cung cấp sẵn.

- **Input:** `String username` được hệ thống authentication chuyển đến để tìm user.
- **Output:** `Mono<UserDetails>`, tức publisher tạo tối đa một `UserDetails` rồi hoàn tất, hoặc hoàn tất rỗng, hoặc phát lỗi.
- **Trách nhiệm:** tìm và cung cấp dữ liệu user đáng tin cậy để tầng xác thực kiểm tra.
- **Không phải trách nhiệm:** so sánh raw password với password hash, tự cấp `ROLE_ADMIN`, trả HTTP 401 hay lưu `SecurityContext`.

`Mono` là abstraction reactive; nó có thể đại diện lookup in-memory, tra cứu R2DBC hoặc một hệ thống danh tính với API non-blocking. Tuy nhiên, **chỉ vì method trả `Mono` không chứng minh implementation non-blocking**. Nếu bên trong gọi JDBC/SDK đồng bộ trên event loop, ứng dụng vẫn có thể bị nghẽn.

### Tín hiệu của `Mono<UserDetails>`

| Tín hiệu | Diễn giải | Gợi ý xử lý |
| --- | --- | --- |
| `onNext(userDetails)` rồi `onComplete()` | Đã tìm được bản ghi bảo mật của một user | Manager kiểm tra password, trạng thái và authorities |
| `onComplete()` không có phần tử | Không có user trong một implementation chọn biểu diễn thiếu dữ liệu bằng empty | Tầng authentication phải xử lý tình huống không tìm thấy như thất bại đăng nhập |
| `onError(error)` | Lookup thất bại hoặc implementation chọn báo lỗi cho username không tồn tại | Phân loại lỗi kỹ thuật và lỗi không tìm thấy theo chính sách |

Hợp đồng API mô tả kết quả `UserDetails` **không được là `null`**. Cách biểu diễn user không tồn tại có thể khác giữa implementation và version: một repository reactive thường trả `Mono.empty()` khi không có bản ghi, trong khi một implementation có thể phát `UsernameNotFoundException`. **Không tự giả định mọi `ReactiveUserDetailsService` trả empty cho username lạ.** Thực hiện kiểm thử đúng implementation được sử dụng.

Đặc biệt, `Mono.empty()` ở đây (lookup không có user) **khác ngữ cảnh** với `Mono.empty()` của `ReactiveAuthenticationManager.authenticate(...)` (manager không thể quyết định/có thể không hỗ trợ token). Đừng sử dụng một tín hiệu thành công giả để che giấu trường hợp username không tồn tại.

### So sánh với Servlet

| WebFlux / reactive | Spring MVC / Servlet |
| --- | --- |
| `ReactiveUserDetailsService` | `UserDetailsService` |
| `findByUsername(String)` | `loadUserByUsername(String)` |
| `Mono<UserDetails>` | `UserDetails` trực tiếp |
| `ReactiveAuthenticationManager` | `AuthenticationManager` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `ServerHttpSecurity` | `HttpSecurity` |

Đừng nhầm hai loại service và hai DSL. Với WebFlux, bạn cần `ReactiveUserDetailsService` và `ServerHttpSecurity`; ví dụ Servlet `InMemoryUserDetailsManager`/`HttpSecurity` không thay trực tiếp cho cấu hình reactive.

## 3. `UserDetails`: cấu trúc bảo mật của một người dùng

`UserDetails` là interface thuộc `org.springframework.security.core.userdetails`. Các getter quan trọng:

```java
public interface UserDetails extends java.io.Serializable {
    java.util.Collection<? extends GrantedAuthority> getAuthorities();
    String getPassword();
    String getUsername();

    boolean isAccountNonExpired();
    boolean isAccountNonLocked();
    boolean isCredentialsNonExpired();
    boolean isEnabled();
}
```

Đây là **chữ ký rút gọn để học**, không phải đoạn code cần sao chép thành interface khác. `GrantedAuthority` thuộc `org.springframework.security.core`.

### Thuộc tính và cách dùng

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `getUsername()` | Tên đăng nhập mà hệ thống xác thực dùng để nhận diện account | `reader` |
| `getPassword()` | **Password hash đã lưu**, không phải raw password | Chuỗi BCrypt như `$2a$...` |
| `getAuthorities()` | Quyền được cấp từ nguồn tin cậy | `reports:read`, `ROLE_ADMIN` |
| `isEnabled()` | Tài khoản có được kích hoạt không | `false` khi vô hiệu hóa |
| `isAccountNonExpired()` | Tài khoản **chưa hết hạn** | `false` khi tài khoản đã hết hạn |
| `isAccountNonLocked()` | Tài khoản **không bị khóa** | `false` khi bị lock |
| `isCredentialsNonExpired()` | Credentials **chưa hết hạn** | `false` khi buộc đổi mật khẩu theo chính sách |

Lưu ý tên **phủ định kép** của ba getter `Non...`. `isAccountNonLocked() == true` nghĩa là **không bị khóa**. Nếu dùng builder `.accountLocked(true)` thì `isAccountNonLocked()` sẽ là `false`.

Các cờ trạng thái này cung cấp dữ liệu đầu vào cho authentication manager. Không tự suy ra rằng mọi loại token và mọi manager đều áp dụng y hệt bốn cờ; ví dụ username/password manager dựa trên `UserDetails` thường thực hiện kiểm tra thông qua thành phần của Spring Security.

### Tạo `UserDetails` với builder chính thức

```java
UserDetails reader = User.withUsername("reader")
        .password(passwordEncoder.encode("reader-pass"))
        .authorities("reports:read")
        .build();

UserDetails admin = User.withUsername("admin")
        .password(passwordEncoder.encode("admin-pass"))
        .authorities("reports:read", "ROLE_ADMIN")
        .build();

UserDetails disabled = User.withUsername("disabled")
        .password(passwordEncoder.encode("disabled-pass"))
        .authorities("reports:read")
        .disabled(true)
        .build();
```

Đoạn này **minh họa trong một method** đã có `PasswordEncoder passwordEncoder` và imports `User`, `UserDetails`. Chương trình đầy đủ có ở phần 8.

Với builder, các cờ trạng thái mặc định là đang hoạt động/không hết hạn/không khóa trừ khi bạn cấu hình khác đi. Đây là lựa chọn tiện lợi cho demo, nhưng hệ thống thật phải ánh xạ các cờ từ chính sách và trạng thái tài khoản ở database.

## 4. Authorities và roles: mô hình quyền phải rõ ràng

`GrantedAuthority` có thể là quyền chi tiết hoặc role. `SimpleGrantedAuthority` chứa một chuỗi authority, ví dụ `reports:read`. Spring Security cung cấp tiện ích `User.withUsername(...).authorities(...)` và `.roles(...)`.

Hai khái niệm:

- `.authorities("reports:read")`: tạo authority **đúng chuỗi** `reports:read`. Rule phù hợp là `hasAuthority("reports:read")`.
- `.roles("ADMIN")`: tiện ích tạo authority **có tiền tố mặc định** `ROLE_ADMIN`. Rule phù hợp là `hasRole("ADMIN")`.

Ví dụ:

```java
UserDetails editor = User.withUsername("editor")
        .password(passwordEncoder.encode("editor-pass"))
        .authorities("reports:read", "reports:write", "ROLE_EDITOR")
        .build();
```

**Cẩn thận khi gọi `.roles(...)` và `.authorities(...)` nối tiếp trong cùng một builder.** Mỗi lời gọi thiết lập tập authorities; nếu tưởng thao tác sau là thêm vào tập cũ, bạn có thể vô tình mất role. Cách dễ đọc là tổng hợp đầy đủ authorities trong một lần `.authorities("reports:read", "ROLE_EDITOR")` hoặc chỉ dùng `.roles(...)` nếu tất cả quyền đều là role.

Cũng không gán authorities theo các chuỗi do client tự gửi như `X-Role: ADMIN`. Vai trò phải lấy từ nguồn tin cậy, do application/server quản lý và kiểm chứng. Nếu một hệ thống áp dụng role hierarchy, custom prefix hay method security, cần xem chính sách quyền tương ứng thay vì giả định một role tự bao hàm mọi permission.

### Authentication khác authorization

- **Authentication:** xác nhận người gửi credential là ai; sử dụng user store, password encoder và manager.
- **Authorization:** quyết định danh tính đã xác thực có quyền truy cập URL/phương thức dữ liệu không; sử dụng authorities/roles và rules.

Một user đăng nhập đúng mật khẩu nhưng chỉ có `reports:read` vẫn bị `403 Forbidden` khi truy cập `/admin` yêu cầu `ROLE_ADMIN`. `403` không chứng tỏ lookup username hay kiểm tra password thất bại.

## 5. Password hash không phải password thô

Trong `UserDetails`, `getPassword()` chứa giá trị mà manager sẽ đưa vào `PasswordEncoder.matches(rawPassword, storedEncodedPassword)`. Với ứng dụng thật, mật khẩu phải được băm bằng thuật toán thích hợp như BCrypt/Argon2/scrypt/PBKDF2 theo chính sách và khả năng hạ tầng; không lưu cleartext hay tự dùng SHA-256 không salt để thay thế password hashing.

Ví dụ với BCrypt:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String hash = encoder.encode("reader-pass");
boolean valid = encoder.matches("reader-pass", hash);
boolean invalid = encoder.matches("wrong-pass", hash);

// valid == true, invalid == false.
// hash khác nhau giữa các lần encode là hành vi bình thường vì có salt.
```

Đây là **đoạn code minh họa**, cần imports `PasswordEncoder` và `BCryptPasswordEncoder`. Không in giá trị hash và mật khẩu thô ra log trong ứng dụng thật.

Một lựa chọn khác là `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, nơi encoded password mang tiền tố thuật toán như `{bcrypt}...`. **Hai kiểu lưu trữ có định dạng khác nhau**: raw BCrypt hash từ `BCryptPasswordEncoder` thường bắt đầu bằng `$2a$...`, còn `DelegatingPasswordEncoder` đòi hỏi prefix như `{bcrypt}` để chọn encoder theo id, trừ khi có cấu hình đặc biệt. Đừng thay encoder mà không chuẩn hóa/migrate dữ liệu.

**Bảo vệ dữ liệu:** Không đưa `UserDetails.getPassword()` vào DTO response, JSON log, exception, trace hoặc audit event. Ngay cả hash cũng là thông tin xác thực nhạy cảm cần bảo vệ. Không ghi raw password, token hay HTTP Authorization header vào log.

## 6. Phân biệt domain user và security user

Một ứng dụng thực tế có thể có ba lớp mô hình:

| Lớp | Dữ liệu điển hình | Chức năng |
| --- | --- | --- |
| Domain/persistence entity | `id`, `username`, `passwordHash`, `status`, `createdAt`, business profile, roles/permissions | Lưu và quản trị tài khoản theo nghiệp vụ |
| `UserDetails` | Username, encoded password, authorities, account flags | Đưa dữ liệu cần cho authentication tới Spring Security |
| HTTP response DTO | `id`, display name, profile được phép xem | Trả dữ liệu công khai theo chính sách, **không có password hash** |

Không buộc entity database phải `implements UserDetails`. Nếu trộn mọi thuộc tính ORM, security và HTTP serialization vào cùng một class, một thay đổi JSON có thể vô tình làm lộ hash, hoặc việc chỉnh sửa entity vô tình cấp quyền. Tách model và **ánh xạ có chủ đích** giúp hệ thống dễ kiểm toán.

Ví dụ domain model Java 17:

```java
public record AccountRecord(
        long id,
        String username,
        String passwordHash,
        boolean enabled,
        java.util.Set<String> authorities,
        String displayName) {
}
```

Đây là **mô hình minh họa** ở tầng domain; không thay cho `UserDetails`. `displayName` là dữ liệu hiển thị, không nên tự động được dùng làm username đăng nhập; `authorities` nên được tạo từ dữ liệu quyền đã được server xác minh.

Một adapter mapping điển hình:

```java
UserDetails toUserDetails(AccountRecord account) {
    return User.withUsername(account.username())
            .password(account.passwordHash())
            .disabled(!account.enabled())
            .authorities(account.authorities().toArray(String[]::new))
            .build();
}
```

Đây là **method minh họa** nằm trong class có import `User` và `UserDetails`. Cần map thêm `accountExpired`, `accountLocked`, `credentialsExpired` nếu domain có chính sách tương ứng. Đừng tự cấp mọi user `ROLE_ADMIN`; authorities phải đến từ nguồn tin cậy.

### Mô hình dữ liệu nên chứa gì?

Tối thiểu, tài khoản phục vụ username/password thường cần:
- ID nội bộ ổn định, độc lập username có thể đổi.
- Username/email chuẩn hóa theo chính sách rõ ràng và unique trong phạm vi cần xác thực.
- Password hash có định dạng được `PasswordEncoder` hỗ trợ, kèm cơ chế migration/version khi cần.
- Trạng thái enabled/locked/expired và metadata phục vụ audit/quản trị.
- Quyền hoặc quan hệ đến role/permission được cấp bởi hệ thống tin cậy.
- Thông tin profile công khai trong DTO riêng.

Ở production, cần thêm cơ chế reset password an toàn, giới hạn thử đăng nhập, khóa tài khoản, audit, MFA theo yêu cầu, bảo vệ PII, quản lý vòng đời và quyền truy cập dữ liệu. Bài này tập trung vào **cầu nối giữa domain model và authentication**, không thiết kế một dịch vụ quản lý danh tính đầy đủ.

## 7. Luồng xác thực username/password trong WebFlux

Hình dung HTTP Basic:

```text
GET /me
Authorization: Basic <credentials>
          |
          v
Spring Security WebFilter / Authentication converter
          |
          v
Authentication request (username + raw password)
          |
          v
ReactiveAuthenticationManager
          |
          +--> ReactiveUserDetailsService.findByUsername(username)
          |             |
          |             +--> Mono<UserDetails> (user, hash, authorities, flags)
          |
          +--> PasswordEncoder.matches(raw, storedHash)
          +--> Account status checks
          |
          +--> Success: authenticated Authentication
          |        |
          |        v
          |  SecurityContext trong Reactor Context
          |        |
          |        v
          |  authorizeExchange: kiểm tra authorities
          |        |
          |        v
          |    Handler / response
          |
          +--> Failure: AuthenticationException -> challenge/handler (Basic thường 401)
```

Sơ đồ là **luồng khái niệm**, không phải mô tả class nội bộ bắt buộc của mọi version/kiểu login. `ReactiveUserDetailsService` không trực tiếp tạo `Authentication` thành công. `UserDetailsRepositoryReactiveAuthenticationManager` kết hợp lookup và kiểm tra, còn `SecurityWebFilterChain` định nghĩa cách bảo vệ HTTP request.

Một user bị `disabled` có thể **vẫn tồn tại** trong `ReactiveUserDetailsService`, nhưng authentication manager từ chối cho đăng nhập. Do đó kiểm thử lookup và kiểm thử đăng nhập là hai nhóm test riêng biệt.

Thông tin authentication của WebFlux được truyền qua **Reactor Context**; không lấy `SecurityContextHolder` dạng `ThreadLocal` của ứng dụng Servlet làm nguồn dữ liệu đáng tin khi pipeline có thể đổi thread.

## 8. Ví dụ hoàn chỉnh Java 17+ với Spring Boot 3.3.5

Ví dụ này dùng user in-memory để toàn bộ demo có thể chạy mà không phụ thuộc database. Nó làm rõ `ReactiveUserDetailsService`, `UserDetails` và manager kết nối với security chain như thế nào. Dự án sử dụng Spring Boot **3.3.5**, Java **17+**, Gradle **8.5** hoặc một wrapper tương thích, với dependency Spring Security do Spring Boot quản lý.

Cấu trúc:

```text
reactive-user-details-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/userdetails/
    │   ├── ReactiveUserDetailsApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/dev/example/userdetails/
        └── UserDetailsIntegrationTests.java
```

### 8.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-user-details-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` chọn reactive web stack. Tránh thêm `spring-boot-starter-web` khi muốn học WebFlux thuần: nếu cả hai có mặt, Spring Boot thông thường chọn MVC/Servlet. `reactor-test` cung cấp `StepVerifier` để kiểm chứng tín hiệu của `Mono`. Test HTTP dùng `WebTestClient` từ Spring Test.

### 8.2. Class khởi động

`src/main/java/dev/example/userdetails/ReactiveUserDetailsApplication.java`:

```java
package dev.example.userdetails;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveUserDetailsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveUserDetailsApplication.class, args);
    }
}
```

### 8.3. Bean user store, encoder, manager và security chain

`src/main/java/dev/example/userdetails/SecurityConfig.java`:

```java
package dev.example.userdetails;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .authorities("reports:read")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .authorities("reports:read", "ROLE_ADMIN")
                .build();

        UserDetails disabled = User.withUsername("disabled")
                .password(encoder.encode("disabled-pass"))
                .authorities("reports:read")
                .disabled(true)
                .build();

        return new MapReactiveUserDetailsService(reader, admin, disabled);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {
        return http
                .authenticationManager(manager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/reports").hasAuthority("reports:read")
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Giải thích:

1. `PasswordEncoder` là bean BCrypt dùng để tạo hash trong dữ liệu mẫu và so password trong authentication manager.
2. `MapReactiveUserDetailsService` là implementation `ReactiveUserDetailsService` lưu user ở bộ nhớ. Constructor nhận `UserDetails...`; với danh sách lớn hoặc database thật, thay implementation phù hợp.
3. `reader` có authority `reports:read`; `admin` có `reports:read` và `ROLE_ADMIN`; `disabled` có user record nhưng `isEnabled() == false`.
4. `UserDetailsRepositoryReactiveAuthenticationManager` nhận `ReactiveUserDetailsService` và `PasswordEncoder`, chịu trách nhiệm xác thực username/password. Không phải tự gọi `findByUsername` từ controller.
5. `SecurityWebFilterChain` xác định ba mức truy cập: `/public` công khai; `/reports` cần authority `reports:read`; `/admin` cần role ADMIN. Mọi URL khác yêu cầu đã đăng nhập.
6. `.httpBasic(...)` bật HTTP Basic phục vụ demo, còn `.formLogin(form -> form.disable())` tắt form login để quan sát rõ status HTTP.
7. Không hề tự cấp quyền từ query parameter/header; authorities trong bean user store là dữ liệu do server tạo.

Bản demo chứa mật khẩu **rõ trong source** chỉ để chạy localhost; những mật khẩu đó được băm khi tạo `UserDetails`. Không dùng tài khoản/mật khẩu mẫu trên dịch vụ công khai.

### 8.4. Controller WebFlux

`src/main/java/dev/example/userdetails/DemoController.java`:

```java
package dev.example.userdetails;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    public Mono<String> me(Principal principal) {
        return Mono.just("user=" + principal.getName());
    }

    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("reports-ok");
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

Các handler trả `Mono<String>`. `/me` sử dụng `Principal` đã xác thực do framework cung cấp. Không cần tự gọi `users.findByUsername(...)` trong mỗi request handler; làm như vậy vừa dư thừa, vừa dễ vô tình lộ password hash nếu trả nguyên `UserDetails` qua HTTP.

## 9. Chạy demo bằng Gradle và kiểm tra HTTP

Từ thư mục `reactive-user-details-demo`:

```bash
gradle bootRun
```

Nếu dự án đã có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Các lệnh sau giả sử server đã khởi động trên port 8080. Mở terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/reports
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
curl -i -u disabled:disabled-pass http://localhost:8080/me
curl -i -u reader:wrong-pass http://localhost:8080/me
curl -i -u unknown:guess http://localhost:8080/me
```

Kết quả **dự kiến**:

| Request | Status / response chính | Diễn giải |
| --- | --- | --- |
| `GET /public`, anonymous | 200, `public` | Endpoint công khai |
| `GET /me`, anonymous | 401 | Chưa xác thực |
| `GET /me`, reader đúng password | 200, `user=reader` | Username/password hợp lệ |
| `GET /reports`, reader đúng password | 200, `reports-ok` | Có `reports:read` |
| `GET /admin`, reader đúng password | 403 | Đã xác thực nhưng không có `ROLE_ADMIN` |
| `GET /admin`, admin đúng password | 200, `admin-ok` | Có `ROLE_ADMIN` |
| `GET /me`, disabled đúng password | 401 | User tồn tại nhưng bị disable |
| `GET /me`, reader sai password | 401 | Sai credentials |
| `GET /me`, username không tồn tại | 401 | Không có account hợp lệ để đăng nhập |

HTTP Basic thường phản hồi `WWW-Authenticate` khi cần cung cấp credentials. Các status/body chính ở bảng là dự kiến theo cấu hình ví dụ; header chi tiết hoặc response lỗi có thể khác theo version. Mọi lệnh ở đây dùng GET nên không đụng CSRF cho các yêu cầu thay đổi trạng thái. Khi thử POST/PUT/DELETE, cần kiểm tra chính sách CSRF riêng.

**Quan trọng:** `401` có thể xuất phát từ user không tồn tại, sai password, disabled hoặc account locked, nên **không** để HTTP response phân biệt chính xác trường hợp nhạy cảm, tránh user enumeration. Cần kiểm soát thông tin lỗi trả ra client và thông tin audit nội bộ.

## 10. Kiểm thử `UserDetails`, manager và security chain

`src/test/java/dev/example/userdetails/UserDetailsIntegrationTests.java`:

```java
package dev.example.userdetails;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class UserDetailsIntegrationTests {

    @Autowired
    ReactiveUserDetailsService users;

    @Autowired
    ReactiveAuthenticationManager manager;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    WebTestClient client;

    @Test
    void readerLookupReturnsEncodedPasswordAndAuthority() {
        StepVerifier.create(users.findByUsername("reader"))
                .assertNext(user -> {
                    assertEquals("reader", user.getUsername());
                    assertTrue(encoder.matches(
                            "reader-pass", user.getPassword()));
                    assertTrue(user.getAuthorities().stream()
                            .anyMatch(a ->
                                    a.getAuthority().equals("reports:read")));
                    assertTrue(user.isEnabled());
                    assertTrue(user.isAccountNonExpired());
                    assertTrue(user.isAccountNonLocked());
                    assertTrue(user.isCredentialsNonExpired());
                })
                .verifyComplete();
    }

    @Test
    void disabledUserIsStillPresentButNotEnabled() {
        StepVerifier.create(users.findByUsername("disabled"))
                .assertNext(user -> {
                    assertEquals("disabled", user.getUsername());
                    assertFalse(user.isEnabled());
                })
                .verifyComplete();
    }

    @Test
    void managerAuthenticatesCorrectPassword() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "reader-pass");

        assertFalse(request.isAuthenticated());

        StepVerifier.create(manager.authenticate(request))
                .assertNext(result -> {
                    assertTrue(result.isAuthenticated());
                    assertEquals("reader", result.getName());
                    assertTrue(result.getAuthorities().stream()
                            .anyMatch(a ->
                                    a.getAuthority().equals("reports:read")));
                })
                .verifyComplete();
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "wrong-pass");

        StepVerifier.create(manager.authenticate(request))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void publicEndpointIsOpen() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void anonymousCannotReadMe() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanReadMe() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user=reader");
    }

    @Test
    void readerCanReadReports() {
        client.get().uri("/reports")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("reports-ok");
    }

    @Test
    void readerCannotAccessAdmin() {
        client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdmin() {
        client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void disabledCannotAuthenticate() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("disabled", "disabled-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void incorrectPasswordIsRejected() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void nonexistentUserIsRejected() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("unknown", "guess"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Chạy:

```bash
gradle test
```

**Kỳ vọng:** 13 test thành công khi dùng các file và dependency đồng nhất ở trên. Đây là **kết quả dự kiến từ mã học tập**, không phải tuyên bố đã chạy Gradle trong môi trường của bạn. Gradle output chi tiết có thể thay đổi theo phiên bản.

Hai nhóm test trả lời hai câu hỏi khác nhau:
- `StepVerifier` với `users.findByUsername(...)`: dữ liệu user trả về có đúng username, password hash, authorities và trạng thái không? Người bị disable vẫn có thể tra ra bản ghi.
- HTTP `WebTestClient` và `manager.authenticate(...)`: hệ thống có xác minh raw credentials, từ chối user disabled và áp dụng authorization đúng không?

Nếu bạn chỉ test `findByUsername` rồi kết luận đăng nhập an toàn thì chưa đủ. Kho user có thể chứa dữ liệu đúng nhưng password encoder/manager/security chain cấu hình sai.

## 11. Từ `MapReactiveUserDetailsService` sang repository reactive thật

`MapReactiveUserDetailsService` hữu ích vì lưu dữ liệu cố định trong RAM và triển khai `ReactiveUserDetailsService`. Với production cần persistence, có thể tạo adapter giữ nguyên hợp đồng nhưng lấy dữ liệu từ R2DBC hoặc một API reactive phù hợp.

Sơ đồ thiết kế:

```text
HTTP Basic / authentication request
        |
        v
UserDetailsRepositoryReactiveAuthenticationManager
        |
        v
ReactiveUserDetailsService (adapter ứng dụng)
        |
        v
AccountRepository.findByUsername(username)
        |
        v
Mono<AccountRecord> (domain/persistence)
        |
        v
map(AccountRecord -> UserDetails)
        |
        v
Mono<UserDetails>
```

**Ví dụ mã adapter ở đây là cấu trúc minh họa riêng**, không được thêm đồng thời vào demo phần 8 khi chưa thay thế bean `MapReactiveUserDetailsService`. Hai bean `ReactiveUserDetailsService` cùng có thể tạo ambiguity khi inject, và một ứng dụng production phải chọn rõ nguồn user nào được dùng.

### 11.1. Model và repository contract

```java
package dev.example.accounts;

import java.util.Set;
import reactor.core.publisher.Mono;

record AccountRecord(
        Long id,
        String username,
        String passwordHash,
        boolean enabled,
        boolean locked,
        Set<String> authorities) {
}

interface AccountRepository {
    Mono<AccountRecord> findByUsername(String username);
}
```

Đây là **khai báo mô hình và hợp đồng**, chưa có implementation database. Với Spring Data R2DBC, entity và repository sẽ có annotations, query, schema, driver và migration riêng theo thiết kế hệ thống. `Mono<AccountRecord>` thường hoàn tất empty khi không tìm thấy row, nhưng phải kiểm chứng repo implementation cụ thể.

### 11.2. Adapter security

```java
package dev.example.accounts;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import reactor.core.publisher.Mono;

final class AccountReactiveUserDetailsService
        implements ReactiveUserDetailsService {

    private final AccountRepository repository;

    AccountReactiveUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return repository.findByUsername(username)
                .map(this::toUserDetails);
    }

    private UserDetails toUserDetails(AccountRecord account) {
        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .authorities(
                        account.authorities().toArray(String[]::new))
                .build();
    }
}
```

Các class ở phần 11.1 và 11.2 có thể biên dịch với Reactor + Spring Security Core, nhưng chưa tự chạy thành một ứng dụng vì **chưa có repository implementation, persistence và cấu hình bean**. Điểm cần nắm:
- `findByUsername` chỉ lấy dữ liệu và ánh xạ sang `UserDetails`. Nó không tự so mật khẩu.
- `Mono.map(...)` chỉ chạy mapping khi repository phát `AccountRecord`. Nếu repository rỗng, chuỗi tiếp tục empty; exception từ repository được chuyển tiếp thành `onError`.
- `passwordHash` phải được lưu theo định dạng encoder đang dùng; không gọi `encoder.encode(account.passwordHash())` một lần nữa khi đọc, vì đó là **double hash**.
- `locked` trong domain chuyển thành `.accountLocked(true)`, làm `isAccountNonLocked() == false`.
- `Set<String> authorities` phải đến từ bảng quyền hoặc logic tin cậy; không lấy trực tiếp danh sách do client gửi.
- Không sử dụng JDBC blocking bên trong `repository.findByUsername(...)` nếu muốn giữ pipeline non-blocking.

### 11.3. Có nên tự thực hiện `switchIfEmpty`?

Nếu service trả `Mono.empty()` cho user không tồn tại, authentication manager phải coi request username/password tương ứng là xác thực thất bại. Tùy hợp đồng nội bộ, adapter cũng có thể chuyển thành:

```java
return repository.findByUsername(username)
        .map(this::toUserDetails)
        .switchIfEmpty(Mono.error(
                new UsernameNotFoundException("User not found")));
```

Đây là **đoạn thay thế bên trong method adapter**, cần import `UsernameNotFoundException` và đảm bảo policy lỗi của Spring Security manager phù hợp. Không để thông điệp public phân biệt cụ thể “username sai” với “password sai”. Không chuyển mọi lỗi database thành `Mono.empty()`: outage, timeout và lỗi query cần được giám sát, không ngụy trang thành không có account.

## 12. `ReactiveUserDetailsPasswordService` và nâng cấp password hash

Có một interface riêng là `ReactiveUserDetailsPasswordService` với method `Mono<UserDetails> updatePassword(UserDetails user, String newPassword)`. Nó hỗ trợ nhu cầu **cập nhật encoded password trong user store**, ví dụ khi cơ chế authentication phát hiện cần nâng cấp hash sang thuật toán/chi phí mới.

Đây **không phải** method có sẵn trên mọi `ReactiveUserDetailsService`. Một class có thể triển khai cả hai interface; `MapReactiveUserDetailsService` là ví dụ như vậy, nhưng thay đổi trong RAM không tự trở thành persistence an toàn sau khi restart.

Trong repository production, việc thay đổi hash cần:
- Mật khẩu mới được **encode** đúng chuẩn trước khi lưu, dựa trên thiết kế encoder và API gọi.
- Cập nhật bản ghi tương ứng, xử lý race/concurrency nếu hai request đăng nhập cùng lúc nâng cấp hash.
- Không lưu raw password, không log hash; giới hạn quyền update.
- Dùng transaction/optimistic locking nếu persistence và policy cần tính nhất quán.
- Trả `UserDetails` phiên bản đã cập nhật qua `Mono`.

Vì thế, quản lý username/password còn bao gồm **vòng đời và migration dữ liệu**, không chỉ việc tạo user ban đầu.

## 13. Chuẩn hóa username, quyền và dữ liệu nhạy cảm

### 13.1. Quy tắc username phải nhất quán

Một hệ thống có thể chọn username phân biệt hoa/thường hoặc không; không có quy tắc chung phù hợp mọi sản phẩm. Nếu policy dùng email case-insensitive, cần chuẩn hóa nhất quán khi **đăng ký, tạo unique index, tra cứu và migration**. Không âm thầm lowercase mọi tài khoản cũ vì có thể tạo xung đột khi dữ liệu trước đây cho phép các tên khác nhau theo case.

Nếu hệ thống đa tenant, `username` có thể chỉ unique **trong tenant**, chứ không unique toàn bộ. Khi đó service mặc định nhận một `String username` không tự mang tenant id; cần thiết kế key hoặc context đáng tin cậy, và không dựa vào một query parameter tenant do client tự khai báo để chọn danh tính.

### 13.2. Trạng thái tài khoản khác trạng thái phiên

`enabled=false` có thể chặn đăng nhập username/password mới, nhưng thu hồi những session/token đã cấp trước đó là vấn đề **khác**. Một JWT đã phát có thể vẫn hợp lệ đến khi hết hạn nếu không có cơ chế thu hồi; thay đổi account flag không bảo đảm tự động chặn mọi bearer token. Cần thiết kế chính sách account disable/revocation phù hợp loại authentication thực tế.

### 13.3. Cache user details

Cache có thể giảm tải repository nhưng cũng làm authorities hoặc trạng thái locked/disabled bị cũ. Nếu cache `UserDetails`, hãy xác định TTL, invalidation khi đổi password/roles/trạng thái và yêu cầu thu hồi quyền. Đừng dùng `Mono.cache()` tùy tiện trên một publisher dùng chung cho nhiều username.

Trong hệ thống nhiều instance, `MapReactiveUserDetailsService` chỉ có dữ liệu RAM của từng process. Dù có method cập nhật password, thay đổi đó không tự đồng bộ các instance hoặc tồn tại sau restart. Cần repository tập trung hoặc hệ thống danh tính chuyên dụng nếu muốn quản trị thực.

### 13.4. Đừng return nguyên `UserDetails` qua REST

Sai về ý định:

```java
// Minh họa RỦI RO: có thể serialize dữ liệu nhạy cảm.
@GetMapping("/user")
public Mono<UserDetails> user(@RequestParam String username) {
    return users.findByUsername(username);
}
```

Phương thức trên **chỉ là minh họa trong controller**, biến `users` phải được inject và `@RequestParam` cần import. Việc expose username lookup như vậy còn gây nguy cơ **user enumeration** và lộ password hash/authorities/trạng thái tài khoản. Tránh thiết kế này.

Tốt hơn: ở endpoint `/me` sau authentication, ánh xạ một principal đã xác thực sang DTO cho phép công khai, chỉ gồm ID/display name hoặc các trường hợp lệ theo quyền truy cập. Không dùng `getPassword()`, `getCredentials()`, refresh token hoặc secret trong response.

## 14. Các lỗi hay gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Ứng dụng WebFlux dùng `UserDetailsService` đồng bộ | Nhầm giao diện Servlet với reactive | Dùng `ReactiveUserDetailsService`, `Mono<UserDetails>` |
| User tồn tại nhưng đăng nhập vẫn 401 | Raw password không khớp hash; encoder sai; user disabled/locked/expired | Kiểm tra manager, encoder và account flags |
| `getPassword()` chứa password rõ | Dữ liệu user được tạo trực tiếp từ raw secret | Encode trước khi lưu, dùng `PasswordEncoder` đúng chuẩn |
| Đổi sang `DelegatingPasswordEncoder` rồi lỗi id null | Stored hash thiếu `{id}` prefix | Migration/chuẩn hóa hash hoặc cấu hình encoder tương thích |
| `.roles(...)` rồi `.authorities(...)` làm mất role | Builder thiết lập lại authorities | Tổng hợp đầy đủ quyền trong một lời gọi |
| `hasRole("ADMIN")` không match | Chỉ có authority `ADMIN` thay vì `ROLE_ADMIN` | Dùng `.roles("ADMIN")` hoặc `.authorities("ROLE_ADMIN")` nhất quán |
| Không tìm thấy user bị coi là thành công | Tự dùng `defaultIfEmpty(fakeAdmin)` hoặc cấp principal mặc định | Treat missing user as failed authentication |
| Database timeout bị biến thành user không tồn tại | `onErrorResume(ex -> Mono.empty())` quá rộng | Phân loại lỗi hệ thống, không che outage |
| `ReactiveUserDetailsService` trả `Mono` nhưng request vẫn nghẽn | Repository gọi blocking driver trên event loop | Dùng R2DBC/reactive API, hoặc cô lập blocking thật sự |
| 403 ở admin dù login đúng | Thiếu authority hoặc rule security từ chối | Phân biệt authentication và authorization |
| Trả `UserDetails` ra JSON | Lộ hash/authorities và gây enumeration | Dùng DTO an toàn; chỉ cho phép truy cập dữ liệu phù hợp |
| User vừa bị khóa nhưng request vẫn vào được | Cache hoặc token cũ/phiên chưa thu hồi | Kiểm tra TTL, revocation và cache invalidation |
| Hai user trùng username ở các tenant | Thiếu tenant-aware identity key | Thiết kế lookup key/unique constraint theo ranh giới tenant |
| Gọi `block()` trong WebFlux filter/handler | Blocking thread, có thể gây lỗi và giảm throughput | Kết hợp bằng Reactor operators, để framework subscribe |

### Ba phân biệt cần nhớ

1. **Có `UserDetails`** chỉ chứng minh tra được user; **có `Authentication` thành công** cần kiểm tra credentials và status.
2. **Có authorities trong account record** không tự cấp quyền: phải đưa qua model đáng tin, tạo kết quả xác thực và kiểm tra authorization rule tương ứng.
3. **Có `Mono`** không chứng minh mọi thao tác phía sau non-blocking: implementation repository quyết định có I/O blocking hay không.

## 15. Tự kiểm tra kiến thức

**Câu 1.** `ReactiveUserDetailsService` có method gì và trả về kiểu nào?  
**Đáp án:** `findByUsername(String username)` trả `Mono<UserDetails>`.

**Câu 2.** `findByUsername` có tự xác minh password không?  
**Đáp án:** Không. Nó tra user; authentication manager kiểm tra credential bằng `PasswordEncoder` và trạng thái tài khoản.

**Câu 3.** `UserDetails.getPassword()` thường chứa gì?  
**Đáp án:** Password hash đã lưu, tương thích `PasswordEncoder`; không phải password rõ và không được expose qua HTTP.

**Câu 4.** `isAccountNonLocked() == false` nghĩa là gì?  
**Đáp án:** Tài khoản đang bị khóa. Tên getter là phủ định kép.

**Câu 5.** `.roles("ADMIN")` tương đương authority nào theo prefix mặc định?  
**Đáp án:** `ROLE_ADMIN`.

**Câu 6.** `.authorities("reports:read")` kết hợp với rule nào?  
**Đáp án:** `hasAuthority("reports:read")`.

**Câu 7.** User `disabled` trong ví dụ có tìm được bằng service không? Có login được không?  
**Đáp án:** Service có thể trả `UserDetails` của user đó, nhưng manager từ chối authentication vì `isEnabled() == false`.

**Câu 8.** Repository trả `Mono.empty()` khi username không tồn tại: có thể lập tức coi đăng nhập thành công không?  
**Đáp án:** Không. Tầng authentication phải chuyển tình huống thiếu user thành thất bại đăng nhập theo hợp đồng.

**Câu 9.** Nên lưu domain entity bằng cách implement trực tiếp `UserDetails` ở mọi ứng dụng?  
**Đáp án:** Không bắt buộc; thường nên tách entity/domain, security model và response DTO, với mapper rõ ràng.

**Câu 10.** Vì sao đổi `enabled=false` không bảo đảm mọi JWT đã cấp trước đó bị thu hồi ngay?  
**Đáp án:** Vì token/session revocation là một cơ chế riêng, phụ thuộc chiến lược xác thực và hạ tầng.

**Câu 11.** Vì sao gọi JDBC từ `findByUsername` rồi bọc trong `Mono.just(...)` vẫn có nguy cơ nghẽn?  
**Đáp án:** JDBC call đã thực thi blocking khi tính đối số; `Mono.just` không làm nó non-blocking.

**Câu 12.** Hash BCrypt thay đổi mỗi lần gọi `encode` dù cùng password có phải lỗi không?  
**Đáp án:** Không. Salt tạo ra hash khác, nhưng `matches` vẫn kiểm tra đúng.

### Bài tập thực hành

1. Thêm `editor` vào `MapReactiveUserDetailsService` có authorities `reports:read` và `reports:write`. Thêm endpoint `GET /reports/write` chỉ cho phép `reports:write`; test 200 với editor và 403 với reader.
2. Thêm user `locked` bằng builder `.accountLocked(true)`. Kiểm tra bằng `StepVerifier` rằng lookup vẫn trả user với `isAccountNonLocked() == false`, rồi test login bị 401.
3. Viết lại đoạn mapper ở phần 11 để domain record chứa thêm `accountExpired` và `credentialsExpired`, ánh xạ sang `.accountExpired(...)`/`.credentialsExpired(...)` đúng ý nghĩa.
4. Viết test chứng minh `user.getPassword()` không bằng chuỗi `reader-pass` nhưng `encoder.matches("reader-pass", hash)` trả true.
5. Thiết kế DTO `AccountProfileResponse(id, displayName)` và endpoint chỉ trả profile của principal đã xác thực; không đưa hash hoặc authorities vào JSON.
6. Xem lại trường hợp username không tồn tại và backend timeout. Viết test riêng cho hai nhánh để không vô tình biến lỗi hạ tầng thành tài khoản không có.

**Mẫu thay thế cho bài tập 2** (đặt trong bean `users(...)` đã có biến `encoder`):

```java
UserDetails locked = User.withUsername("locked")
        .password(encoder.encode("locked-pass"))
        .authorities("reports:read")
        .accountLocked(true)
        .build();

// Thêm locked vào constructor MapReactiveUserDetailsService.
```

Đoạn này là **fragment**, không phải chương trình Java độc lập. Kết quả dự kiến: `locked.isAccountNonLocked() == false`; nếu dùng manager username/password trong demo, request Basic của locked phải bị từ chối.

## 16. Tài liệu chính thức

- [Spring Security API — ReactiveUserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html): `findByUsername` và kiểu `Mono<UserDetails>`.
- [Spring Security API — UserDetails](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html): username, password, authorities và các cờ trạng thái tài khoản.
- [Spring Security API — MapReactiveUserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html): implementation dùng map trong RAM.
- [Spring Security API — UserDetailsRepositoryReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html): xác thực username/password dựa vào user store reactive.
- [Spring Security API — ReactiveUserDetailsPasswordService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsPasswordService.html): hợp đồng cập nhật encoded password.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): password encoder, thuật toán băm và migration.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): cấu hình security chain trong WebFlux.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): kiểm thử `Mono` bằng `StepVerifier`.

**Ghi nhớ:** `ReactiveUserDetailsService` **tìm dữ liệu user** dưới dạng `Mono<UserDetails>`; `UserDetails` cung cấp **password hash, authorities và account flags**; `ReactiveAuthenticationManager` mới thực hiện **xác minh credentials** và tạo kết quả authentication. Hãy tách domain model khỏi security model/response DTO và đảm bảo dữ liệu, quyền, hash, lỗi và luồng reactive được xử lý đúng ở từng tầng.