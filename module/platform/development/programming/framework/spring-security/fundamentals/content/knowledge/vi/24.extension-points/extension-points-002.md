# Tùy chỉnh nguồn người dùng qua `UserDetailsService` trong Spring Security

> **Phạm vi:** Spring Security cho ứng dụng Servlet, xác thực bằng username/password với Java 17+ và Spring Boot 3.x. Mục tiêu là thay nguồn người dùng mặc định bằng nguồn dữ liệu do ứng dụng quản lý, hiểu cách Spring Security dùng dữ liệu đó, và kiểm chứng các trường hợp thành công/thất bại. Không đồng nhất `UserDetailsService` với cơ chế xác thực JWT/OIDC hay `ReactiveUserDetailsService` của WebFlux.

## 1. Khi nào cần `UserDetailsService` tùy chỉnh?

Một ứng dụng ban đầu có thể dùng tài khoản mẫu của Spring Boot hoặc `InMemoryUserDetailsManager`. Khi triển khai thật, tài khoản thường nằm trong database với các trường như username, password hash, trạng thái khóa/kích hoạt và danh sách quyền. **`UserDetailsService` là điểm mở rộng để lấy dữ liệu tài khoản đó theo username.** Nhờ vậy ứng dụng vẫn dùng các cơ chế bảo mật chuẩn của Spring Security thay vì tự viết toàn bộ quy trình đăng nhập.

Sau bài học, bạn cần làm được:

1. Phân biệt nhiệm vụ **tải thông tin người dùng** với **kiểm tra password**.
2. Ánh xạ bản ghi nguồn dữ liệu thành `UserDetails` đúng hợp đồng.
3. Đăng ký bean service để luồng username/password dùng được tài khoản riêng.
4. Kiểm thử tài khoản không tồn tại, mật khẩu sai, account bị khóa, đăng nhập hợp lệ và thiếu role.
5. Biết khi nào phải dùng `AuthenticationProvider` khác hoặc cơ chế chuyên dụng cho JWT/OIDC.

## 2. Hợp đồng của `UserDetailsService`

Interface cơ bản:

```java
package org.springframework.security.core.userdetails;

public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
```

`loadUserByUsername` **chỉ nhận username**, không nhận password thô. Nó phải trả một `UserDetails` đầy đủ, **không được trả `null`**. Nếu không tìm thấy user, phải ném `UsernameNotFoundException`. Theo hợp đồng interface, user không có `GrantedAuthority` cũng có thể được xem là không thể tải hợp lệ.

`UserDetails` cung cấp dữ liệu mà provider cần:

| Thành phần | Ý nghĩa khi authentication |
| --- | --- |
| `getUsername()` | Tên đăng nhập/định danh tài khoản. |
| `getPassword()` | **Hash đã lưu**, không phải password thô và không phải giá trị mới hash lại lúc đọc. |
| `getAuthorities()` | Quyền đã được hệ thống tin cậy cấp: `ROLE_USER`, `ROLE_ADMIN`, v.v. |
| `isEnabled()` | Tài khoản có được kích hoạt không. |
| `isAccountNonLocked()` | Tài khoản không bị khóa. |
| `isAccountNonExpired()` | Tài khoản chưa hết hiệu lực. |
| `isCredentialsNonExpired()` | Credentials chưa hết hiệu lực. |

Có thể dùng class `org.springframework.security.core.userdetails.User` và builder `User.withUsername(...)` để chuyển từ bản ghi database sang `UserDetails`. Chỉ tự implement `UserDetails` khi thật sự cần dữ liệu principal riêng và hiểu vòng đời credentials.

### 2.1. Ranh giới trách nhiệm

| Đối tượng | Trách nhiệm |
| --- | --- |
| `AccountRepository` do ứng dụng định nghĩa | Đọc tài khoản và quyền từ database hoặc dịch vụ nội bộ. |
| Custom `UserDetailsService` | Chuyển account thành `UserDetails`, ném `UsernameNotFoundException` nếu thiếu. |
| `PasswordEncoder` | `encode` password khi đăng ký/đổi mật khẩu; `matches` để kiểm tra password thô với hash. |
| `DaoAuthenticationProvider` | Gọi service và encoder, kiểm tra điều kiện account trong quá trình xác thực username/password. |
| `AuthenticationManager` | Điều phối các `AuthenticationProvider` đã đăng ký. |
| Security filters | Đọc credentials HTTP, gọi authentication và thiết lập `SecurityContext`. |
| Authorization rules | Đối chiếu quyền sau xác thực để cho phép/từ chối tài nguyên. |

**Không tự kiểm tra password trong `loadUserByUsername`**: method này không có tham số password và `DaoAuthenticationProvider` đã chịu trách nhiệm so khớp qua encoder. Cũng không cấp `ROLE_ADMIN` chỉ vì client yêu cầu role đó; authorities phải xuất phát từ dữ liệu/quy tắc phía server.

## 3. Luồng xác thực username/password

```text
HTTP Basic hoặc form login
        |
        v
Authentication Filter
        | tạo UsernamePasswordAuthenticationToken chưa xác thực
        v
AuthenticationManager (thường ProviderManager)
        |
        v
DaoAuthenticationProvider
        | gọi loadUserByUsername(username)
        v
Custom UserDetailsService -> AccountRepository
        |
        v
UserDetails (username, stored hash, authorities, account flags)
        |
        +--> kiểm tra trạng thái account
        +--> PasswordEncoder.matches(rawPassword, storedHash)
        |
        +-- thất bại --> authentication failure (API thường 401)
        |
        v
Authentication thành công -> SecurityContext
        |
        v
Authorization rule kiểm tra authorities
        |-- đủ quyền --> controller
        +-- thiếu quyền --> thường 403
```

Sơ đồ là mô hình khái niệm, không biểu diễn chính xác thứ tự mọi bước nội bộ hoặc mọi `SecurityFilterChain`.

**Phân biệt các kết quả:**

- Không có credentials vào endpoint bảo vệ: **chưa xác thực**, API HTTP Basic thường 401.
- Username không tồn tại, password sai, account bị khóa: **xác thực thất bại**, API HTTP Basic thường 401. Server nên tránh báo ra ngoài chi tiết giúp dò tài khoản.
- Username/password hợp lệ nhưng thiếu authority: **đã xác thực, thiếu quyền**, API thường 403.
- Username/password hợp lệ, đủ quyền: endpoint tiếp tục xử lý, ví dụ 200 khi thành công.

Với form login, ứng dụng có thể **redirect** đến trang `/login` hoặc `/login?error` thay vì trả 401 trực tiếp. `UserDetailsService` không quyết định HTTP response.

## 4. Ví dụ Java 17+ chạy được

Ví dụ dùng một repository tự tạo trong bộ nhớ. Đây là **custom source** vì `UserDetailsService` đọc qua repository riêng; nếu chuyển sang JPA/JDBC chỉ cần thay adapter repository. HTTP Basic được bật để nhìn rõ 401 và 403.

### 4.1. Cấu hình Gradle

Tạo `settings.gradle`:

```groovy
rootProject.name = 'userdetails-source-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3.5 là phiên bản được ghim để tái lập ví dụ, **không phải tuyên bố phiên bản mới nhất**. Dùng Gradle 8.x và JDK 17+, cần kết nối để tải dependencies lần đầu.

### 4.2. Mã nguồn đầy đủ

Tạo `src/main/java/demo/userdetails/UserDetailsSourceDemoApplication.java`:

```java
package demo.userdetails;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class UserDetailsSourceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(UserDetailsSourceDemoApplication.class, args);
    }
}

record Account(
    String username,
    String passwordHash,
    List<String> authorities,
    boolean enabled,
    boolean locked
) {}

interface AccountRepository {
    Optional<Account> findByUsername(String username);
}

@Repository
class MapAccountRepository implements AccountRepository {
    private final Map<String, Account> accounts;

    MapAccountRepository(PasswordEncoder encoder) {
        accounts = Map.of(
            "reader", new Account(
                "reader", encoder.encode("reader123"),
                List.of("ROLE_USER"), true, false
            ),
            "admin", new Account(
                "admin", encoder.encode("admin123"),
                List.of("ROLE_USER", "ROLE_ADMIN"), true, false
            ),
            "locked", new Account(
                "locked", encoder.encode("locked123"),
                List.of("ROLE_USER"), true, true
            )
        );
    }

    @Override
    public Optional<Account> findByUsername(String username) {
        return Optional.ofNullable(accounts.get(username));
    }
}

@Service
class AccountUserDetailsService implements UserDetailsService {
    private final AccountRepository repository;

    AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        Account account = repository.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Invalid credentials")
            );

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities().toArray(String[]::new))
            .disabled(!account.enabled())
            .accountLocked(account.locked())
            .build();
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}

@RestController
class DemoApi {
    @GetMapping("/api/public")
    String publicApi() {
        return "public";
    }

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/admin")
    String adminApi() {
        return "admin";
    }
}
```

**Giải thích từng phần:**

1. `MapAccountRepository` giữ ba account giả, mỗi account có **hash BCrypt**, tập quyền và trạng thái. Interface `AccountRepository` giúp thay nguồn dữ liệu mà không sửa security code.
2. `AccountUserDetailsService` là bean `@Service`, implement đúng `loadUserByUsername`; nếu repository không tìm thấy, ném `UsernameNotFoundException`, **không trả `null`**.
3. Mapper cung cấp `account.passwordHash()` trực tiếp. `DaoAuthenticationProvider` sẽ dùng bean `PasswordEncoder` kiểm tra password thô; service **không hash lại và không gọi `matches`**.
4. `.authorities(...)` gán quyền được lưu phía server. Reader có `ROLE_USER`, admin có thêm `ROLE_ADMIN`.
5. `.accountLocked(account.locked())` giữ trạng thái khóa. Nếu bỏ mapping, tài khoản locked có thể bị coi là đang mở.
6. `hasRole("ADMIN")` mặc định kiểm tra authority `ROLE_ADMIN`; những đường dẫn còn lại yêu cầu `authenticated()`, trừ `/api/public`.
7. `.httpBasic(...)` bật Basic; `.formLogin(...disable)` tắt redirect login, giúp minh họa status API. Các endpoint chỉ dùng GET nên không cần tắt CSRF.
8. Trong cấu hình username/password cơ bản, bean service cùng encoder có thể được Spring Security nối vào `DaoAuthenticationProvider`. Nếu ứng dụng đã có manager/provider tùy chỉnh, phải xem lại wiring thực tế.

**Chỉ dùng các account và mật khẩu ví dụ trong môi trường học tập.** Production cần HTTPS, lưu hash/role trong kho dữ liệu bảo vệ, cơ chế chống brute force và quản trị vòng đời tài khoản.

### 4.3. Chạy và quan sát

Từ thư mục dự án, nếu đã có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows, dùng `gradlew.bat bootRun`; nếu không có wrapper, dùng `gradle bootRun` từ bản Gradle 8.x tương thích. Mặc định HTTP server chạy ở `http://localhost:8080`.

Mỗi dòng dưới đây là một lệnh chạy riêng trong terminal Bash có `curl`:

```bash
# 1. Chưa gửi credentials
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me

# 2. Username không tồn tại
curl -s -o /dev/null -w '%{http_code}\n' -u nobody:wrong http://localhost:8080/api/me

# 3. Password sai
curl -s -o /dev/null -w '%{http_code}\n' -u reader:wrong http://localhost:8080/api/me

# 4. Account bị khóa
curl -s -o /dev/null -w '%{http_code}\n' -u locked:locked123 http://localhost:8080/api/me

# 5. Reader đăng nhập hợp lệ
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader123 http://localhost:8080/api/me

# 6. Reader thiếu quyền ADMIN
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader123 http://localhost:8080/api/admin

# 7. Admin đủ quyền
curl -s -o /dev/null -w '%{http_code}\n' -u admin:admin123 http://localhost:8080/api/admin

# 8. Tài nguyên công khai
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/public
```

Kết quả dự kiến theo thứ tự, mỗi lệnh một dòng:

```text
401
401
401
401
200
403
200
200
```

Ngoài ra, `curl -s -u reader:reader123 http://localhost:8080/api/me` trả nội dung `reader`. Điều này giúp xác nhận principal thực sự có username từ repository.

**Giải thích:** (1) chưa xác thực; (2) không tìm thấy record; (3) password sai; (4) account bị khóa; cả bốn thường là 401 với Basic. (5) đúng credentials; (6) xác thực thành công nhưng thiếu role nên 403; (7) đủ quyền; (8) `permitAll()`.

### 4.4. Kiểm thử bằng MockMvc, tránh bypass luồng thật

Tạo `src/test/java/demo/userdetails/UserDetailsFlowTest.java`:

```java
package demo.userdetails;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UserDetailsFlowTest {
    @Autowired MockMvc mvc;

    @Test
    void badPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void lockedAccountIsRejected() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("locked", "locked123")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validReaderCanSeeProfile() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk());
    }

    @Test
    void readerCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk());
    }
}
```

Chạy `./gradlew test` hoặc `gradlew.bat test` trên Windows. `httpBasic(...)` gửi credentials qua request thật của `MockMvc`, để filter/provider gọi custom service. Ngược lại, **chỉ dùng `@WithMockUser` có thể bỏ qua `UserDetailsService` và password comparison**, nên không đủ để kiểm thử điểm mở rộng này.

## 5. Chuyển từ Map sang database

Trong hệ thống thật, nguồn user có thể là PostgreSQL/MySQL, JDBC, JPA hoặc dịch vụ nội bộ. **Giữ interface `AccountRepository`**, thay `MapAccountRepository` bằng adapter database. Một schema tối giản mang tính minh họa:

```sql
CREATE TABLE app_users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,
    locked BOOLEAN NOT NULL
);

CREATE TABLE user_authorities (
    user_id BIGINT NOT NULL REFERENCES app_users(id),
    authority VARCHAR(100) NOT NULL,
    PRIMARY KEY (user_id, authority)
);
```

Cú pháp DDL tùy hệ quản trị; cần chọn quy tắc **phân biệt chữ hoa/chữ thường của username**, unique index và dữ liệu đã chuẩn hóa nhất quán. Với JPA, dùng repository query trả `Optional<AppUser>`, nạp authorities và chuyển entity sang `Account`. Phải bảo đảm đủ dữ liệu trong transaction: lazy-loaded authorities truy cập sau khi đóng session có thể gây `LazyInitializationException`. Có thể dùng fetch join, entity graph hoặc mapping trong phạm vi transaction đọc.

Đoạn sau **chỉ minh họa adapter**, không chạy độc lập vì cần các class `AppUserEntity`, `AuthorityEntity`, `AppUserJpaRepository` cùng cấu hình Spring Data JPA:

```java
@Override
public Optional<Account> findByUsername(String username) {
    return jpaRepository.findWithAuthoritiesByUsername(username)
        .map(entity -> new Account(
            entity.getUsername(),
            entity.getPasswordHash(),
            entity.getAuthorities().stream()
                .map(AuthorityEntity::getName)
                .toList(),
            entity.isEnabled(),
            entity.isLocked()
        ));
}
```

**Password:** Khi tạo/đổi mật khẩu, dùng `passwordEncoder.encode(raw)` **một lần để lưu hash**. Khi đăng nhập, repository trả đúng hash; `DaoAuthenticationProvider` dùng `PasswordEncoder.matches(raw, storedHash)`. BCrypt tạo salt ngẫu nhiên, nên hai lần `encode` trên cùng mật khẩu thường tạo hai hash khác nhau. **Không so sánh bằng `encode(raw).equals(storedHash)`**. Nếu dùng `DelegatingPasswordEncoder`, lưu đúng định dạng có prefix như `{bcrypt}`; lỗi “no PasswordEncoder mapped for id null” thường do hash thiếu prefix hoặc cấu hình encoder không khớp.

**Authorities:** `hasRole("ADMIN")` mặc định đòi `ROLE_ADMIN`; `hasAuthority("ADMIN")` đòi chuỗi `ADMIN`. `User.withUsername(...).roles("ADMIN")` tự thêm prefix `ROLE_`; khi dữ liệu đã là `ROLE_ADMIN`, dùng `.authorities("ROLE_ADMIN")`. Không nhận role từ input client để cấp quyền. Thay đổi role trong database cũng không tự động làm mất quyền của mọi session/token đã được cấp từ trước.

**Độ tin cậy:** Không nối chuỗi SQL từ username; dùng query parameter/ORM. Tránh trả entity JPA hoặc password hash qua API. Không log password thô, hash hoặc token. User/account không tồn tại nên có response lỗi đăng nhập chung nhằm giảm rò rỉ thông tin. Đặt index, timeout cho truy vấn và xác định xử lý khi database không sẵn sàng; **không tự cho phép đăng nhập vì lookup lỗi**.

## 6. Các tình huống đặc biệt cần cân nhắc

### 6.1. Tại sao `loadUserByUsername` không được gọi?

Có nhiều nguyên nhân hợp lệ:

- Request thuộc `SecurityFilterChain` khác hoặc dùng `AuthenticationProvider` khác.
- App có custom `AuthenticationManager` nên bean mới không tự được sử dụng như kỳ vọng.
- Endpoint `permitAll()` và request không gửi credentials.
- Request đã có `SecurityContext`/session xác thực, không cần tra user từ repository mỗi lần.
- App đang dùng Resource Server JWT, OAuth2/OIDC login hoặc cơ chế SSO khác.
- Có nhiều `UserDetailsService` bean làm autowiring/provider selection không rõ.

**Cách kiểm tra:** xem chain và provider đang active, test bằng HTTP Basic/form login thật, theo dõi invocation của custom service và logs bảo mật an toàn. Không suy luận service không hoạt động chỉ từ một breakpoint không được gọi trong request đã có session.

### 6.2. Caching, khóa tài khoản và vòng đời quyền

Cache `UserDetails` có thể giảm tải nguồn dữ liệu, nhưng dễ bị stale khi user đổi mật khẩu, bị khóa hoặc mất quyền. Cần chính sách TTL/invalidation rõ ràng. Đồng thời `AuthenticationManager` có thể xóa credentials khỏi principal sau xác thực; nếu cache dùng chung instance `UserDetails` bị xóa password, lần xác thực sau có thể thất bại bất ngờ. Đừng tự bật cache mà không kiểm chứng cách cache tương tác với `CredentialsContainer` và credential erasure.

Việc khóa account ở database không mặc định hủy các session đang đăng nhập hoặc Bearer token đã phát hành. Nếu nghiệp vụ yêu cầu khóa ngay lập tức, thiết kế thêm cơ chế thu hồi/kiểm tra token, vô hiệu hóa session và đồng bộ authorization.

### 6.3. Khi nào `UserDetailsService` không phù hợp?

| Nhu cầu | Cơ chế phù hợp |
| --- | --- |
| Demo user in-memory | `InMemoryUserDetailsManager`. |
| User trong JDBC schema tương thích | `JdbcUserDetailsManager` hoặc `JdbcDaoImpl`. |
| User trong schema database riêng | Custom `UserDetailsService` + repository. |
| Xác thực bằng credentials không phải username/password | Custom `AuthenticationProvider` hoặc provider chuyên dụng. |
| Bearer JWT / opaque-token API | OAuth2 Resource Server + decoder/introspector/provider. |
| OAuth2/OIDC Login | `OAuth2UserService` / `OidcUserService` tương ứng. |
| WebFlux reactive | `ReactiveUserDetailsService`. |

`UserDetailsService` là chiến lược **đọc dữ liệu user** cho cơ chế xác thực password. Nó không tự thực hiện decode JWT, validate chữ ký, trao đổi OAuth2 authorization code hoặc cung cấp non-blocking reactive authentication.

## 7. Lỗi thường gặp và cách sửa

**Lỗi 1: trả `null` khi không tìm thấy user.** Sai hợp đồng. Hãy dùng:

```java
Account account = repository.findByUsername(username)
    .orElseThrow(() -> new UsernameNotFoundException("Invalid credentials"));
```

Dòng này thuộc method `loadUserByUsername` đã minh họa ở phần 4, không phải chương trình Java độc lập.

**Lỗi 2: hash lại password hash lúc đọc.** Nếu database có BCrypt hash, đừng gọi `encoder.encode(account.passwordHash())`: bạn đang hash một hash, khiến password thô không so khớp. Trả nguyên `account.passwordHash()`.

**Lỗi 3: mapper quên flag `locked` hoặc `enabled`.** Một account bị khóa trong database có thể được Spring Security xem là hợp lệ nếu `UserDetails` được dựng với defaults mở khóa. Phải phản ánh đúng các trạng thái account/credentials mà hệ thống hỗ trợ.

**Lỗi 4: authority có sai tiền tố.** Provider xác thực thành công nhưng controller nhận 403 vì database lưu `ADMIN` trong khi `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN`. Sửa mapping hoặc dùng rule phù hợp, không gán bừa quyền cao hơn để hết lỗi.

**Lỗi 5: dữ liệu `UserDetails` không đầy đủ.** Trả user không có authorities, password hash rỗng hoặc username không nhất quán với DB có thể làm authentication thất bại hoặc authorization sai. Bảo đảm repository nạp đủ authorities trong transaction.

**Lỗi 6: phân biệt chữ hoa/chữ thường không nhất quán.** Login `Alice` so với `alice` tùy cách tra cứu; nếu nghiệp vụ cần case-insensitive, chuẩn hóa ở cả ghi/đọc và unique constraint. Tránh sửa username một chiều rồi vô tình ánh xạ sai account.

**Lỗi 7: dùng `@WithMockUser` và kết luận custom service đã được test.** `@WithMockUser` tạo authentication giả, thường bỏ qua provider/`UserDetailsService`. Dùng Basic credentials thật hoặc form login request để kiểm tra integration.

**Lỗi 8: mọi 401/403 đều đổ cho service.** 401 có thể do password, account flags, provider/encoder; 403 là thiếu quyền hoặc chính sách như CSRF. Kiểm tra chain, method, path, authority và response handler trước khi sửa source.

## 8. Checklist áp dụng

- [ ] Xác định một nguồn dữ liệu authoritative và unique username/canonicalization policy.
- [ ] `loadUserByUsername` trả `UserDetails` đầy đủ hoặc ném `UsernameNotFoundException`.
- [ ] `getPassword()` trả hash đã lưu; `PasswordEncoder` được cấu hình nhất quán.
- [ ] Authorities, enabled/locked/expired flags phản ánh chính xác dữ liệu server.
- [ ] Bean `UserDetailsService` được provider/chain username-password thực sự sử dụng.
- [ ] Test đủ user không tồn tại, sai password, locked, hợp lệ và thiếu role.
- [ ] Có chính sách về logs bảo mật, HTTPS, brute-force protection và khóa tài khoản.
- [ ] Khi dùng DB/cache, quản lý transaction, query/index, invalidation và session/token cũ.

## 9. Câu hỏi kiểm tra

**Q1.** Một user có mật khẩu đúng nhưng `locked=true` trong database, muốn chặn login. Cần làm gì?  
**A1.** Mapper phải đặt `.accountLocked(true)` trên `UserDetails`; provider kiểm tra trạng thái account khi xác thực.

**Q2.** Tại sao `loadUserByUsername` không nhận password?  
**A2.** Nó là API tra cứu user; kiểm tra mật khẩu thuộc `DaoAuthenticationProvider` và `PasswordEncoder`.

**Q3.** `getPassword()` nên trả plaintext hay bcrypt hash?  
**A3.** Trả hash đã lưu. Mật khẩu thô chỉ dùng trong password verification của provider, không lưu và không log.

**Q4.** User hợp lệ có authority `ROLE_USER`, API yêu cầu `hasRole("ADMIN")` trả gì?  
**A4.** Thông thường 403 do thiếu `ROLE_ADMIN`, dù username/password đã đúng.

**Q5.** App chỉ xác thực Bearer JWT, `UserDetailsService` không được gọi. Đây có phải lỗi?  
**A5.** Không nhất thiết; JWT Resource Server dùng provider/decoder riêng. Chỉ kết hợp với DB nếu thiết kế yêu cầu.

## 10. Tóm tắt và tài liệu chính thức

**`AccountRepository` đọc user ở đâu; custom `UserDetailsService` định hình user cho Spring Security; `DaoAuthenticationProvider` và `PasswordEncoder` kiểm tra username/password; `UserDetails` mang các authorities và trạng thái được kiểm soát ở server.** Một triển khai đúng phải được kiểm chứng bằng authentication requests thực, không chỉ bằng test giả lập principal.

Tài liệu tham khảo:

- [UserDetailsService trong Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [UserDetails và credentials](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html)
- [DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Username/Password Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/)
- [Password storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
