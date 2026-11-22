# Thay kho tài khoản mẫu bằng nguồn dữ liệu riêng trong Spring Security

> **Bài thực hành tổng hợp — Spring Security Fundamentals (Servlet / Spring MVC).** Mục tiêu là thay nguồn người dùng minh họa `InMemoryUserDetailsManager` hoặc tài khoản mặc định của Spring Boot bằng dữ liệu ứng dụng tự quản lý, trong khi vẫn để Spring Security xác minh mật khẩu, xử lý trạng thái tài khoản và áp quy tắc truy cập. Ví dụ đầy đủ dùng **Java 17, Spring Boot 3.3.0, Spring Security 6.x, Spring Data JPA và H2**. H2 trong bộ ví dụ là database **chỉ để học**, dữ liệu mất khi ứng dụng dừng; triển khai thật cần database, schema migration và quản trị tài khoản phù hợp.

## 1. Kết quả cần đạt và ranh giới công việc

Sau bài này, bạn phải có thể:

1. Giải thích quá trình đăng nhập từ HTTP Basic/form login tới `AuthenticationManager`, `DaoAuthenticationProvider`, `UserDetailsService`, `PasswordEncoder` và `SecurityContext`.
2. Nhận diện chính xác **kho người dùng mẫu** đang được dùng, rồi thay bằng một `UserDetailsService` truy vấn repository/database.
3. Chuyển dữ liệu user riêng (`username`, password hash, enabled, authorities) thành `UserDetails` mà không tự so sánh mật khẩu thô trong repository.
4. Giữ nguyên chính sách `SecurityFilterChain` và phân quyền: user tồn tại, mật khẩu đúng, account active, authority phù hợp.
5. Chạy thử được đường đi thành công **200**, chưa xác thực **401**, thiếu quyền **403**, tài khoản vô hiệu hóa và tài khoản vừa được thêm vào database.
6. Phân biệt giải pháp demo với quy trình vận hành production: mật khẩu hash, khóa tài khoản, role, migration, unique index, transaction, cache và test hồi quy.

Bài tập chỉ thay **nguồn dữ liệu phục vụ xác thực bằng username/password**. Nó không tự xây màn hình đăng ký, reset mật khẩu, MFA, refresh token, OAuth2 Authorization Server hay một hệ thống IAM hoàn chỉnh. Những tính năng ấy có thể dùng thêm thành phần Spring Security hoặc hệ thống bên ngoài, nhưng cần thiết kế riêng.

## 2. Hiểu bản chất: thay nguồn dữ liệu, giữ cơ chế xác thực

Ở cấu hình mẫu, bạn thường gặp một trong hai trường hợp:

**Trường hợp A — Spring Boot tự sinh user phát triển:** thêm `spring-boot-starter-security`, chưa có `UserDetailsService`/`AuthenticationProvider`/`AuthenticationManager` tự định nghĩa. Boot có thể tạo user `user` và in một password phát sinh lúc khởi động. Đây chỉ là cấu hình tiện lợi cho development.

**Trường hợp B — dự án tự tạo user trong bộ nhớ:**

```java
@Bean
UserDetailsService userDetailsService(PasswordEncoder encoder) {
    UserDetails demo = User.withUsername("demo")
        .password(encoder.encode("demo-pass"))
        .roles("USER")
        .build();
    return new InMemoryUserDetailsManager(demo);
}
```

Đây là **fragment của cấu hình mẫu**, không còn được giữ nguyên khi đổi sang nguồn database. User được định nghĩa ở code và mất khả năng quản lý độc lập qua dữ liệu ứng dụng; sửa password/role phải sửa code hoặc điều khiển chính instance đang chạy.

**Kiến trúc đích:**

```text
Client (username + raw password)
    │
    ▼
SecurityFilterChain / filter nhận HTTP Basic hoặc form login
    │
    ▼
AuthenticationManager → DaoAuthenticationProvider
                          ├─ gọi UserDetailsService.loadUserByUsername(username)
                          │      │
                          │      ▼
                          │   AccountRepository → Database
                          │      │
                          │      ▼
                          │   UserDetails (username, password HASH, enabled, authorities)
                          │
                          └─ dùng PasswordEncoder.matches(raw, storedHash)
    │
    ├─ Sai credential / disabled / không tìm thấy → authentication failure
    ▼
Authentication hợp lệ, chứa authorities
    │
    ▼
AuthorizationFilter → requestMatchers / hasRole / authenticated
    │
    ▼
Controller / Service
```

Trách nhiệm từng lớp:

| Thành phần | Nhiệm vụ | Không nên làm |
| --- | --- | --- |
| `AccountRepository` | Đọc/ghi tài khoản và authority từ database | Không kiểm tra mật khẩu thô trong SQL; không gửi hash ra API. |
| `UserDetailsService` | Tìm user bằng username, chuyển dữ liệu sang `UserDetails`, báo `UsernameNotFoundException` nếu thiếu | Không so sánh password, không gọi trực tiếp `SecurityContextHolder`, không tự cấp quyền mặc định khi DB thiếu dữ liệu. |
| `PasswordEncoder` | `encode(raw)` lúc tạo/đổi mật khẩu, `matches(raw, encoded)` lúc xác thực | Không mã hóa raw để so sánh hai hash BCrypt; không lưu `{noop}` cho production. |
| `DaoAuthenticationProvider` | Dùng `UserDetailsService` + `PasswordEncoder`, kiểm tra credential và trạng thái người dùng | Không cần tự cài lại nếu yêu cầu là username/password thông thường. |
| `SecurityFilterChain` | Chọn kiểu xác thực và rule HTTP, ví dụ USER/ADMIN | Không nên viết câu SQL lấy account trong `requestMatchers`. |
| Service nghiệp vụ | Kiểm tra quyền với dữ liệu thực: owner/tenant/resource | Không tin vào `userId` hoặc `role` do client tự gửi. |

**Một bean `UserDetailsService` tự định nghĩa** sẽ khiến cấu hình user mặc định của Spring Boot nhường chỗ, với điều kiện không có các cấu hình `AuthenticationProvider`/`AuthenticationManager` khác can thiệp. Nếu ứng dụng đang có provider đặc thù, LDAP, OAuth2 hoặc multi-chain, phải kiểm tra đường xác thực thực tế trước khi kết luận custom service đã được sử dụng.

## 3. Hợp đồng `UserDetailsService`: đầu vào, đầu ra và lỗi

Chữ ký quan trọng:

```java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
```

`loadUserByUsername` **chỉ nhận username**. Password thô được giữ ở luồng authentication, để `DaoAuthenticationProvider` so với hash mà service trả về. Một `UserDetails` tối thiểu cung cấp `username`, `password` ở dạng **đã mã hóa**, danh sách `GrantedAuthority` và trạng thái tài khoản.

Cách ánh xạ dữ liệu:

| Cột của ứng dụng | Thuộc tính `UserDetails` | Quy tắc |
| --- | --- | --- |
| `username` | `getUsername()` | Unique, canonicalize theo policy, không trùng người dùng. |
| `password_hash` | `getPassword()` | Chứa hash đã mã hóa, không phải plain text. |
| `enabled` | `isEnabled()` | Nếu false, xác thực theo provider chuẩn không được thành công. |
| `authorities` | `getAuthorities()` | Chuỗi authority rõ ràng, ví dụ `ROLE_USER`, `ROLE_ADMIN`. |
| `locked`, `expired`, `credentialsExpired` (nếu có) | `isAccountNonLocked()`, `isAccountNonExpired()`, `isCredentialsNonExpired()` | Chỉ trả đúng mặc định nếu sản phẩm **chưa có** các trạng thái đó; nếu có phải ánh xạ thực tế. |

Trong ví dụ sau, bảng chỉ có `enabled`, nên các cờ còn lại dùng mặc định của builder `User.withUsername(...)`. Đừng biến một quy tắc “tài khoản đang bị khóa” trong database thành việc chỉ trả `enabled=true`.

### Role khác authority ở cách đặt tên

`User.withUsername(...).roles("ADMIN")` tạo authority `ROLE_ADMIN`. Khi dữ liệu đã lưu dạng `ROLE_ADMIN`, hãy dùng `.authorities("ROLE_ADMIN")` hoặc `.authorities(Collection...)`, **không** gọi `.roles("ROLE_ADMIN")`: cách gọi này sẽ sai quy ước tiền tố. `hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN`; `hasAuthority("invoice:approve")` so chuỗi quyền chính xác. Không tin role lấy trực tiếp từ request JSON.

## 4. Chuẩn bị dự án chạy được

Ví dụ dùng Maven; không cần copy một cấu hình cũ từ hàng/bài khác. Tạo thư mục dự án:

```text
custom-account-store/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/accounts/
    │   │   ├── AccountsApplication.java
    │   │   ├── Account.java
    │   │   ├── AccountRepository.java
    │   │   ├── DatabaseUserDetailsService.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DemoAccounts.java
    │   │   └── AccountController.java
    │   └── resources/application.yml
    └── test/java/example/accounts/
        └── AccountSecurityTest.java
```

### 4.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>custom-account-store</artifactId>
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
            <artifactId>spring-boot-starter-data-jpa</artifactId>
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
```

Dùng phiên bản **pinned** giúp ví dụ minh họa nhất quán với Spring Boot 3 / Spring Security 6 và `jakarta.persistence`. Đây là baseline để học API, không phải chỉ dẫn triển khai bản cũ lên production. Khi làm dự án thực, chọn release đang được hỗ trợ, bản vá mới phù hợp và chạy lại test theo tài liệu cùng phiên bản.

### 4.2. `src/main/resources/application.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:accounts_demo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
  h2:
    console:
      enabled: false
```

H2 in-memory cho phép thực hành repository mà không cần cài PostgreSQL. `create-drop` để Hibernate dựng schema khi chạy demo và bỏ schema khi đóng EntityManagerFactory. **Không đưa `ddl-auto: create-drop` vào production**, vì đó không phải cơ chế migrate dữ liệu an toàn. Chưa bật H2 console cũng giảm một bề mặt truy cập không cần thiết.

### 4.3. `src/main/java/example/accounts/AccountsApplication.java`

```java
package example.accounts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountsApplication.class, args);
    }
}
```

`@SpringBootApplication` ở package `example.accounts` cho phép quét `@Entity`, repository, service và config cùng các package con. Không cần liệt kê thêm `@ComponentScan` cho cấu trúc này.

## 5. Tạo model dữ liệu tài khoản

Đây là dữ liệu **nguồn của ứng dụng**; `UserDetails` chỉ là đối tượng mà Spring Security dùng khi xác thực. Không nhất thiết ép entity JPA implements `UserDetails`: tách chúng giúp model persistence không phụ thuộc trực tiếp vào Spring Security và tránh vô tình serialize hash ra response.

Tạo `src/main/java/example/accounts/Account.java`:

```java
package example.accounts;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "app_accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    @Column(nullable = false)
    private boolean enabled;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(
        name = "app_account_authorities",
        joinColumns = @JoinColumn(name = "account_id")
    )
    @Column(name = "authority", nullable = false, length = 100)
    private Set<String> authorities = new HashSet<>();

    protected Account() {
        // Constructor JPA.
    }

    public Account(String username, String passwordHash,
                   boolean enabled, Set<String> authorities) {
        this.username = Objects.requireNonNull(username);
        this.passwordHash = Objects.requireNonNull(passwordHash);
        this.enabled = enabled;
        this.authorities = new HashSet<>(Objects.requireNonNull(authorities));
    }

    public Long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public Set<String> getAuthorities() {
        return Set.copyOf(authorities);
    }
}
```

Điểm cần nắm:

- `username` phải unique ở **database**, không chỉ ở Java. Case-sensitivity và canonicalization cần policy nhất quán với collation DB. Với tên/email, quy tắc chuyển chữ thường và giữ dấu phải được quyết định **trước** khi nạp dữ liệu thật.
- `password_hash` đủ độ dài cho định dạng hash đang dùng, kể cả tiền tố `{bcrypt}` của `DelegatingPasswordEncoder`. Không lưu password gốc hay reversible encryption như một “hash”.
- `enabled` là thuộc tính mà `DaoAuthenticationProvider` có thể kiểm tra qua `UserDetails`.
- `authorities` lưu từng chuỗi như `ROLE_USER`. EAGER ở đây để ví dụ lấy authority trọn vẹn trong thao tác tra username. Ở hệ lớn, chọn cách load/DTO/query thích hợp để tránh N+1, dữ liệu dư thừa hoặc quá nhiều authorities trên mỗi lần đăng nhập.
- `getAuthorities()` trả bản sao bất biến, nhưng **không** phải một API công khai để trả toàn entity ra HTTP. Giới hạn dữ liệu ở DTO, không expose hash hoặc trạng thái nội bộ tùy ý.

Tạo `src/main/java/example/accounts/AccountRepository.java`:

```java
package example.accounts;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository extends JpaRepository<Account, Long> {
    Optional<Account> findByUsername(String username);
}
```

Spring Data JPA xây truy vấn từ tên `findByUsername` dựa trên thuộc tính entity `username`. Mục đích của repository là **đọc một account**, không tự sinh `Authentication` hay quyết định mật khẩu đúng/sai.

## 6. Thay `InMemoryUserDetailsManager` bằng `UserDetailsService` riêng

Tạo `src/main/java/example/accounts/DatabaseUserDetailsService.java`:

```java
package example.accounts;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    public DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        Account account = accounts.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        return User.withUsername(account.getUsername())
            .password(account.getPasswordHash())
            .disabled(!account.isEnabled())
            .authorities(account.getAuthorities().toArray(String[]::new))
            .build();
    }
}
```

**Tại sao đoạn này là điểm thay thế chính?**

- `@Service` đăng ký bean triển khai `UserDetailsService` với Spring container. Khi không có provider/manager tùy biến xung đột, `DaoAuthenticationProvider` trong cấu hình username/password dùng bean này để tra tài khoản.
- `loadUserByUsername()` lấy account đúng username. Nếu không có dữ liệu, **ném `UsernameNotFoundException`**; không tự đăng ký user mới hay trả một tài khoản mặc định.
- `.password(account.getPasswordHash())` trả **hash đã lưu**, không đưa `PasswordEncoder.encode(raw)` vào lúc lấy user.
- `.authorities(...)` giữ các chuỗi authority từ database. Nếu DB chứa `ROLE_ADMIN`, `hasRole("ADMIN")` mới khớp.
- `.disabled(!account.isEnabled())` ánh xạ cờ `enabled`. Trả `isEnabled() == false` khiến provider chuẩn từ chối xác thực.
- `@Transactional(readOnly=true)` bao quanh truy vấn và đọc collection trong cùng transaction; đây là lựa chọn phục vụ JPA, không thay đổi ngữ nghĩa authentication.

**Không tạo thêm một bean `InMemoryUserDetailsManager`** ở cấu hình khác: có nhiều `UserDetailsService`/provider, Spring Security có thể không tự chọn bean bạn mong đợi. Nếu hệ thống thật cần nhiều nguồn, phải xây chuỗi `AuthenticationProvider`/routing rõ ràng rồi kiểm thử từng cách đăng nhập.

## 7. Giữ cơ chế mã hóa mật khẩu và quy tắc HTTP

Tạo `src/main/java/example/accounts/SecurityConfig.java`:

```java
package example.accounts;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
```

Với ví dụ này, **không cần tự khai báo `DaoAuthenticationProvider` hoặc `AuthenticationManager` bean**: có một `UserDetailsService` và một `PasswordEncoder` để cơ chế username/password tiêu chuẩn sử dụng. Nếu dự án của bạn đã tự khai báo `AuthenticationProvider` hay `AuthenticationManager`, không áp dụng giả định autoconfiguration này một cách máy móc; hãy cấu hình injection rõ ràng và kiểm thử provider đang được gọi.

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` trong baseline này mặc định tạo hash mới với id `{bcrypt}`. Định dạng tổng quát:

```text
{id}encodedPassword
{bcrypt}$2a$...              # giá trị minh họa, không phải hash dùng để login
```

`encode("alice-pass")` sinh hash có salt; cùng raw password thường cho hash **khác nhau**. Muốn kiểm tra login, dùng `passwordEncoder.matches("alice-pass", storedHash)`; **không** so chuỗi `encode(raw).equals(storedHash)`. Khi cần chuyển đổi hash cũ, xem phần migration, không tự thêm `{noop}` cho toàn bộ password.

Cấu hình `SecurityFilterChain` phía trên dùng HTTP Basic để quan sát status dễ dàng. Ở ứng dụng trình duyệt dùng session/form login, có thể chọn `.formLogin(Customizer.withDefaults())` và kiểm tra CSRF/redirect/UX tương ứng. Các ví dụ GET không cần tắt CSRF; **đừng** tắt CSRF để làm hết lỗi 403 khi chưa biết ứng dụng có dùng cookie/session tự gửi bởi browser hay không.

## 8. Seed dữ liệu demo trong database, không đưa tài khoản vào SecurityConfig

Một database H2 trống lúc khởi động không có account để thử. Tạo `src/main/java/example/accounts/DemoAccounts.java`:

```java
package example.accounts;

import java.util.Set;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class DemoAccounts {

    @Bean
    CommandLineRunner insertDemoAccounts(
            AccountRepository accounts,
            PasswordEncoder passwordEncoder) {

        return args -> {
            if (accounts.count() > 0) {
                return;
            }

            accounts.save(new Account(
                "alice",
                passwordEncoder.encode("alice-pass"),
                true,
                Set.of("ROLE_USER")
            ));

            accounts.save(new Account(
                "admin",
                passwordEncoder.encode("admin-pass"),
                true,
                Set.of("ROLE_ADMIN")
            ));

            accounts.save(new Account(
                "blocked",
                passwordEncoder.encode("blocked-pass"),
                false,
                Set.of("ROLE_USER")
            ));
        };
    }
}
```

Đây là **dữ liệu khởi tạo cho học tập**, không phải giải pháp production. Khi dùng database thật, không seed username/password hard-code; cần tạo tài khoản qua một quy trình an toàn, migrations/provisioning, và secret management. Chỉ dùng cấu hình seed này trong môi trường demo hoặc gắn với profile riêng được khóa chặt. Câu lệnh `accounts.count()>0` chỉ phục vụ H2 demo; không nên dùng nó thay migration hay tạo tài khoản từng phần trong hệ thống thật.

Điều quan trọng ở đây là các user `alice`, `admin`, `blocked` **được lưu trong bảng JPA**, không còn là `UserDetails` được hard-code và giữ trong `InMemoryUserDetailsManager`. Để sửa trạng thái/quyền sau này, thay đổi dữ liệu theo use case và transaction phù hợp.

## 9. Tạo API để quan sát xác thực và phân quyền

Tạo `src/main/java/example/accounts/AccountController.java`:

```java
package example.accounts;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "hello:" + authentication.getName();
    }

    @GetMapping("/admin/report")
    public String report() {
        return "admin-ok";
    }
}
```

`Authentication` được Spring MVC lấy từ security context của request đã được xác thực. Ứng dụng có thể đọc `authentication.getName()` và authorities để thực hiện tác vụ; không lấy username từ query parameter làm identity đáng tin. Endpoint demo chỉ trả username, **không trả toàn entity**, password hash hoặc stack trace.

### 9.1. Chạy dự án

Cần **JDK 17+**, Maven 3.9+ (hoặc bản Maven tương thích với Spring Boot 3.3) và network để tải dependencies lần đầu:

```bash
java -version
mvn test
mvn spring-boot:run
```

`mvn test` chạy bộ integration tests ở phần 10. `mvn spring-boot:run` khởi động Tomcat cổng mặc định 8080 nếu chưa cấu hình cổng khác.

Ở terminal thứ hai (macOS/Linux), thử:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public/ping
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/profile
curl -s -o /dev/null -w '%{http_code}\n' -u alice:alice-pass http://localhost:8080/profile
curl -s -o /dev/null -w '%{http_code}\n' -u alice:wrong http://localhost:8080/profile
curl -s -o /dev/null -w '%{http_code}\n' -u blocked:blocked-pass http://localhost:8080/profile
curl -s -o /dev/null -w '%{http_code}\n' -u alice:alice-pass http://localhost:8080/admin/report
curl -s -o /dev/null -w '%{http_code}\n' -u admin:admin-pass http://localhost:8080/admin/report
```

Kết quả **dự kiến** với chính xác cấu hình trong bài:

```text
200
401
200
401
401
403
200
```

Giải thích:

- `/public/ping` mở vì `permitAll()`, nên **200**.
- `/profile` thiếu Authorization header nên HTTP Basic yêu cầu credentials, **401**.
- `alice` có hash đúng và account enabled, nên `/profile` trả **200** với body `hello:alice`.
- Password sai: `PasswordEncoder.matches()` không khớp, nên **401**.
- `blocked` có password đúng nhưng `enabled=false`, nên **401**.
- Alice chỉ có `ROLE_USER`, trong khi `/admin/**` yêu cầu `ROLE_ADMIN`, nên **403**.
- Admin có `ROLE_ADMIN`, nên **200**.

Trên Windows PowerShell, dùng `curl.exe` thay `curl` để tránh alias; thay `/dev/null` bằng `NUL` nếu chạy trực tiếp trên Windows. Status có thể khác ở ứng dụng bật form login (ví dụ chuyển hướng 302), nên test theo cấu hình auth thực tế.

## 10. Integration test chứng minh dữ liệu thực được dùng

Tạo `src/test/java/example/accounts/AccountSecurityTest.java`:

```java
package example.accounts;

import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AccountRepository accounts;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void publicEndpointWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotViewProfile() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanAuthenticateUsingDatabaseHash() throws Exception {
        mvc.perform(get("/profile").with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:alice"));
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mvc.perform(get("/profile").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUserIsRejected() throws Exception {
        mvc.perform(get("/profile").with(httpBasic("unknown", "whatever")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void disabledAccountIsRejected() throws Exception {
        mvc.perform(get("/profile").with(httpBasic("blocked", "blocked-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userCannotAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/report").with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/report").with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));
    }

    @Test
    void passwordIsStoredAsHash() {
        Account alice = accounts.findByUsername("alice").orElseThrow();

        assertThat(alice.getPasswordHash()).startsWith("{bcrypt}");
        assertThat(alice.getPasswordHash()).isNotEqualTo("alice-pass");
        assertThat(encoder.matches("alice-pass", alice.getPasswordHash())).isTrue();
        assertThat(encoder.matches("wrong", alice.getPasswordHash())).isFalse();
    }

    @Test
    void newlyCreatedDatabaseAccountCanAuthenticate() throws Exception {
        String username = "fresh-" + UUID.randomUUID();
        Account created = accounts.save(new Account(
            username,
            encoder.encode("fresh-pass"),
            true,
            Set.of("ROLE_USER")
        ));

        try {
            mvc.perform(get("/profile")
                    .with(httpBasic(username, "fresh-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("hello:" + username));
        } finally {
            accounts.deleteById(created.getId());
        }
    }
}
```

**Kỳ vọng:** khi chạy `mvn test` với đúng source, **10 bài test thành công**. Đây là kết quả mong đợi về logic; không phải báo cáo đã chạy build trên workspace hiện tại.

Bài test cuối có giá trị đặc biệt: nó **tạo tài khoản mới trong repository**, rồi dùng tài khoản đó đăng nhập ngay qua HTTP Basic. Nếu ứng dụng vẫn xác thực chỉ bằng danh sách user hard-code, test này sẽ không đạt. Dùng username ngẫu nhiên và xóa bản ghi ở `finally` để tránh làm bẩn dữ liệu khi kiểm thử. Trong hệ test song song, có thể dùng database riêng hoặc isolation chặt hơn.

### 10.1. Bài test nào bắt được lỗi nào?

| Hành vi | Dấu hiệu đúng | Lỗi có thể phát hiện |
| --- | --- | --- |
| Public endpoint | 200 | Vô tình khóa hết API khi thay `SecurityFilterChain`. |
| Anonymous vào protected endpoint | 401 | Endpoint bị mở nhầm hoặc thiếu filter chain. |
| Alice password đúng | 200 | UserDetailsService chưa kết nối, hash lưu không đúng format. |
| Alice password sai | 401 | Tự viết check mật khẩu không đúng hoặc bỏ qua password. |
| Username không tồn tại | 401 | Service trả một fallback user không an toàn. |
| Account disabled | 401 | Bỏ qua trường `enabled` hoặc mapping ngược logic. |
| USER vào admin | 403 | Role prefix không chính xác, rule matcher sai. |
| ADMIN vào admin | 200 | Role không được nạp từ DB hoặc policy quá chặt. |
| Kiểm tra hash | `{bcrypt}` và `matches()` đúng | Lưu password thô hoặc encode sai thời điểm. |
| User mới từ DB đăng nhập | 200 | Ứng dụng vẫn dùng `InMemoryUserDetailsManager` thay vì DB. |

**Phân biệt 401 và 403:** 401 điển hình khi thiếu/thất bại authentication; 403 khi principal đã xác thực nhưng không có authority. Với form login, failure có thể chuyển hướng đến login; phải test behavior thực tế, không áp dụng cứng status của HTTP Basic cho mọi ứng dụng.

## 11. Di chuyển dữ liệu thật từ kho cũ sang database

Trong dự án thực, “thay kho mẫu” thường có hai bước: đổi **đường đọc account khi login** và **nạp/migrate dữ liệu account đang được sản phẩm sở hữu**. Không thực hiện bước nạp mà chỉ thay service thì toàn bộ user có thể bị 401.

### 11.1. Kiểm kê dữ liệu đầu vào

Trước khi thay, lập mapping chi tiết:

| Nguồn hiện có | Cột đích đề xuất | Việc phải kiểm tra |
| --- | --- | --- |
| Username/email dùng để login | `username` | Chữ hoa/chữ thường, Unicode, uniqueness, trường hợp account trùng. |
| Mật khẩu | `password_hash` | Thuật toán lưu hiện tại, salt, work factor, prefix id, có hash không tương thích không. |
| Trạng thái account | `enabled`, `locked`, ... | Đang bị khóa/hết hạn có bị bật nhầm khi chuyển không. |
| Role/group/scope | `app_account_authorities` hoặc role mapping chuẩn | `ROLE_` prefix, quan hệ nhiều-nhiều, phân quyền tenant. |
| ID user | `id` và các foreign key liên quan | Không làm gãy quan hệ đơn hàng, audit, file owner hoặc dữ liệu khác. |
| Metadata vận hành | createdAt, updatedAt, version, lastPasswordChange | Cần cho quản trị, kiểm toán, đồng bộ, thay đổi quyền. |

Nếu nguồn là `InMemoryUserDetailsManager` với vài user test, **không tự mang tài khoản test sang production**. Với kho hiện có hàng triệu user, cần kế hoạch backfill và cutover có đo lường, rollback phù hợp, không sửa toàn bộ record theo một vòng lặp trong request login.

### 11.2. Schema migration cho database thật

Thay H2 demo bằng PostgreSQL/MySQL phù hợp ứng dụng. Một ví dụ DDL **minh họa PostgreSQL** để hình dung schema (không chạy song song với Hibernate `create-drop`):

```sql
CREATE TABLE app_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE app_account_authorities (
    account_id BIGINT NOT NULL
        REFERENCES app_accounts(id) ON DELETE CASCADE,
    authority VARCHAR(100) NOT NULL,
    PRIMARY KEY (account_id, authority)
);
```

Đặt DDL trong migration của Flyway/Liquibase, chuyển ứng dụng production sang schema validation (`spring.jpa.hibernate.ddl-auto=validate`), kiểm tra backfill và index trước cutover. Khóa unique ở database bảo vệ khỏi các đăng ký username trùng khi có nhiều instance. Schema thật có thể cần các cột khác (lock, tenant, version, reset token metadata) nhưng phải xuất phát từ policy ứng dụng; không thêm tùy tiện vào ví dụ rồi coi là đủ cho mọi sản phẩm.

### 11.3. Mật khẩu cũ: đừng “mã hóa lại” hash đang lưu

- Nếu nguồn đã lưu BCrypt, PBKDF2, scrypt hoặc Argon2, bạn không biết password gốc. **Không thể** chuyển một hash cũ sang hash mới bằng `encode(oldHash)` rồi mong người dùng đăng nhập được.
- `DelegatingPasswordEncoder` lưu prefix kiểu `{bcrypt}`, `{pbkdf2}`... để chọn đúng decoder. Khi nhập dữ liệu cũ **đã hash nhưng không có prefix**, cần xây mapping encoder có kiểm chứng hoặc thêm prefix **tương ứng đúng thuật toán**, tuyệt đối không gắn `{bcrypt}` cho hash thuộc thuật toán khác.
- Lộ trình thông dụng là verify bằng thuật toán cũ được chấp nhận tạm thời rồi **rehash từ raw password mới nhận ở lần đăng nhập thành công**, thông qua thành phần có quyền cập nhật hash (ví dụ `UserDetailsPasswordService` khi cấu hình phù hợp). Điều kiện: thuật toán cũ vẫn cho phép xác minh an toàn trong thời gian chuyển đổi.
- Nếu chỉ có password plaintext cũ (tình huống bảo mật nghiêm trọng), ưu tiên kế hoạch xử lý rủi ro, chuyển sang hashing mạnh hoặc reset có kiểm soát, không log hoặc truyền password qua kênh không bảo vệ.
- Nếu muốn đổi work factor, lên kế hoạch đo hiệu năng và từng bước chuyển đổi; BCrypt có salt và chi phí tính toán, không phải một hàm hash tổng quát tốc độ cao.

### 11.4. Cắt chuyển nguồn (cutover) và rollback

Một quy trình thực tế:

1. Chốt đường login hiện tại, các provider và nguồn user thực tế, ghi baseline test 200/401/403.
2. Thiết kế schema và chuẩn hóa dữ liệu username/authority/password hash; kiểm tra các account đặc biệt.
3. Deploy migration schema trong môi trường thử nghiệm và backfill có kiểm chứng: tổng bản ghi, unique collisions, null/missing role, account disabled.
4. Tạo `UserDetailsService` mới, test trực tiếp repository và authentication trong môi trường tương tự production.
5. Thử login của nhiều cohort (user cũ/mới, role đặc biệt, bị khóa), đo lỗi và độ trễ query.
6. Cutover theo kế hoạch được phê duyệt, quan sát authentication failure và connection-pool health; có phương án rollback schema/code **không làm mất dữ liệu**.
7. Sau khi ổn định, xóa kho mẫu khỏi cấu hình production và ngừng chấp nhận credentials demo.

Đừng tạo fallback “nếu database lỗi thì đăng nhập bằng demo user”. Khi nguồn identity thật bị lỗi, việc xác thực cần thất bại một cách có kiểm soát, cùng monitoring/incident response phù hợp.

## 12. Những phương án khác: chọn theo cấu trúc dữ liệu hiện có

**A. Schema riêng với JPA (ví dụ chính).** Phù hợp khi hệ thống đã có entity/user table và muốn tích hợp với service/repository. Cần model cẩn thận, migration, query và transaction.

**B. JDBC chuẩn của Spring Security.** `JdbcUserDetailsManager` là implementation có sẵn cho dạng schema `users` và `authorities` mà Spring Security định nghĩa. Ví dụ **thay thế riêng, không cài đồng thời với bean `DatabaseUserDetailsService` ở trên**:

```java
@Bean
UserDetailsService jdbcUserDetailsService(DataSource dataSource) {
    return new JdbcUserDetailsManager(dataSource);
}
```

Fragment cần các import của `DataSource`, `UserDetailsService`, `JdbcUserDetailsManager` và một `@Configuration`. Cấu hình mặc định mong đợi schema và tên cột tương ứng; nếu dùng bảng `app_accounts` của ví dụ, không tự chạy được trừ khi chỉnh query/mapping. JDBC cũng có thể dùng SQL truy vấn tùy biến trên schema riêng; vẫn cần bảo đảm trả password hash/status/authorities đúng kiểu.

**C. LDAP/Active Directory hoặc Identity Provider.** Nếu tổ chức sở hữu user ở LDAP/IdP, có thể tích hợp provider phù hợp; không nhất thiết copy toàn bộ password vào database ứng dụng. Với OAuth2/OIDC login hoặc Resource Server, cơ chế xác thực khác nhau và **không phải mọi request** đều đi qua `UserDetailsService`. Nên chọn module theo mô hình xác thực, tránh ép một identity flow qua `DaoAuthenticationProvider` khi không phù hợp.

**D. Nhiều nguồn account.** Nếu cần chia người dùng nội bộ/khách hàng hoặc chuyển đổi từng phần, thiết kế rõ thứ tự provider, namespace username, nguồn authority, xử lý account trùng và hành vi khi nguồn hỏng. Không để fallback làm hạ cấp mức xác thực.

## 13. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Login bằng user mới luôn 401 | `DatabaseUserDetailsService` chưa là bean đang được provider sử dụng, hoặc username không có trong DB | Test tạo account qua repository rồi login; kiểm tra cấu hình provider/manager. |
| Log `There is no PasswordEncoder mapped for id "null"` | Hash cũ thiếu prefix trong khi dùng `DelegatingPasswordEncoder` | Xác định thuật toán cũ và mapping tương thích, không tắt encode. |
| 401 dù password gõ đúng | Hash bị mã hóa hai lần, lưu raw, hoặc user disabled/locked | Kiểm tra `encoder.matches(raw, storedHash)` và trạng thái. |
| 403 khi user truy cập `/admin/**` | DB lưu `ADMIN` nhưng rule `hasRole("ADMIN")` mong `ROLE_ADMIN` | Kiểm tra `GrantedAuthority` thực của `UserDetails`. |
| 500 hoặc LazyInitializationException khi đọc authorities | Collection JPA lazy được truy cập ngoài transaction | Fetch rõ ràng hoặc map sang DTO trong transaction. |
| Có hai/many `UserDetailsService` beans | Còn `InMemoryUserDetailsManager` cũ hoặc có cấu hình auth khác | Loại bean mẫu hoặc định tuyến provider tường minh, kiểm thử. |
| Không có user sau restart | Đang dùng H2 memory hoặc `ddl-auto=create-drop` | Dùng DB bền vững, migration và backup đúng môi trường. |
| Tài khoản bị disable vẫn dùng được session hiện tại | Tình trạng user chỉ được kiểm tra ở lần xác thực; session/token có vòng đời riêng | Xây policy session invalidation, token lifetime/revocation, authorization thời điểm truy cập khi cần. |
| Query DB đột nhiên chậm | N+1 authorities, connection pool quá nhỏ, thiếu index username | Phân tích query plan, fetch strategy, metrics và caching. |
| Truy cập sai tenant vẫn 200 | Chỉ kiểm tra role chung, không kiểm tra owner/tenant của tài nguyên | Bổ sung authorization ở service/repository; test truy cập chéo tenant. |
| Basic chưa login trả 302 thay vì 401 | Bật form login/entry point khác | Đọc cấu hình `SecurityFilterChain` và test theo auth mechanism thực. |
| Login thất bại khi DB downtime | DB là nguồn xác thực đang không sẵn sàng | Monitor/retry theo thiết kế; không fallback sang password mẫu. |

### Gợi ý debug theo từng tầng

Khi nhận 401, kiểm tra theo thứ tự: request có credential chưa → security filter chain có match chưa → provider thực đang dùng là gì → repository có trả account không → hash và encoder có khớp không → `enabled/locked/expired` ra sao. Với 403, tách tình huống đã xác thực nhưng thiếu authority với tình huống CSRF bị chặn; không chỉ nhìn một status rồi kết luận.

Có thể bật logging Spring Security ở mức DEBUG **trong môi trường thử nghiệm** để quan sát chain và authentication path, nhưng không ghi raw password, token, hash hoặc thông tin nhạy cảm vào log. Đặc biệt khi trả lỗi cho client, tránh thông báo phân biệt quá rõ “user không tồn tại” và “mật khẩu sai” nếu điều đó làm lộ danh sách account.

## 14. Kiểm tra an toàn trước khi đưa lên production

- [ ] Đã loại `InMemoryUserDetailsManager` hoặc tài khoản mặc định khỏi đường auth production; nếu có nhiều provider, đã ghi rõ thứ tự và định tuyến.
- [ ] DB có unique username, dữ liệu được chuẩn hóa theo policy và được quản lý qua migration có thể kiểm chứng.
- [ ] Password được mã hóa bởi `PasswordEncoder` phù hợp, có prefix/legacy migration đúng; không lưu raw password.
- [ ] Cờ `enabled`, `locked`, `expired` và authority từ DB được map trung thực vào `UserDetails`.
- [ ] Authority được cấp qua nghiệp vụ đáng tin, không nhận role tùy ý từ client.
- [ ] Có test thành công, sai password, user thiếu, user disabled, role thiếu, role hợp lệ, account mới từ DB.
- [ ] Có biện pháp xử lý thay đổi quyền khi còn session/JWT, cache và các request đang chạy; chấp nhận giới hạn consistency đã xác định.
- [ ] DB connections dùng TLS/secret quản lý ngoài source; schema migrations, backups và audit hoạt động.
- [ ] Không expose entity chứa hash trong controller/JSON; lỗi auth không lộ credential hoặc thông tin nội bộ.
- [ ] Có chính sách rate limiting/lockout/abuse prevention phù hợp, log sự kiện an ninh và privacy.
- [ ] Production có CSRF/session/CORS/HTTPS được kiểm tra theo loại client và threat model; không tắt CSRF theo thói quen.
- [ ] Đã chạy test hồi quy sau nâng Spring Boot/Spring Security và xác minh phiên bản dependency thực.

## 15. Tài liệu chính thức để tự học tiếp

- Spring Security — `UserDetailsService`: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — Username/Password Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/
- Spring Security — Password Storage / `DelegatingPasswordEncoder`: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — JDBC Authentication / schema mặc định: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/jdbc.html
- Spring Boot 3.3 — Spring Security auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Data JPA — Query Methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html

**Kết quả của bài thực hành:** nguồn account được chuyển từ cấu hình mẫu sang một repository có dữ liệu riêng; `UserDetailsService` trả đúng hash/trạng thái/authority từ database; `DaoAuthenticationProvider` vẫn đảm nhiệm xác thực mật khẩu; `SecurityFilterChain` vẫn đảm nhiệm HTTP authorization. Khi test thêm tài khoản mới trong database rồi login thành công mà không đổi code security, bạn đã chứng minh sự thay thế đúng ranh giới.
