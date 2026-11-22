# Tích hợp JPA hoặc kho nghiệp vụ thông qua UserDetailsService

> **Bối cảnh:** Spring Security – authentication, nhóm kiến thức **Kho tài khoản**. Bài học tập trung vào cách đưa dữ liệu tài khoản từ Spring Data JPA hoặc một dịch vụ nghiệp vụ có sẵn vào cơ chế xác thực username/password của Spring Security. Ví dụ sử dụng **Java 17+**, **Spring Boot 4**, **Spring Security 7**, Spring Data JPA và H2; giải thích ranh giới trách nhiệm, thiết kế truy vấn, mapping `UserDetails`, kiểm thử và những rủi ro thực tế.

## 1. Vì sao cần một UserDetailsService riêng?

Ứng dụng thường đã có hệ thống người dùng trước khi thêm Spring Security:

- Bảng `app_accounts` quản lý username, password hash, trạng thái tài khoản.
- Bảng liên quan chứa role, permission hoặc quan hệ tài khoản – tổ chức.
- Một dịch vụ nghiệp vụ hoặc identity service có API tìm tài khoản.
- Quy trình đăng ký, thay đổi password, khóa tài khoản, cấp và thu hồi quyền.

Spring Security cần kiểm chứng credential nhưng **không biết** schema riêng của ứng dụng. Nếu đưa trực tiếp entity JPA vào mọi thành phần bảo mật, mã sẽ phụ thuộc vào persistence, lazy loading và cấu trúc nghiệp vụ. Nếu viết lại logic so sánh password trong controller, dễ bỏ qua account status, error handling hoặc các cơ chế bảo mật sẵn có.

`UserDetailsService` giải quyết bài toán này bằng một **hợp đồng đọc dữ liệu**: Spring Security yêu cầu “tải hồ sơ xác thực theo username”, còn ứng dụng quyết định tìm tài khoản ở đâu và chuyển nó sang `UserDetails` như thế nào.

```text
HTTP Basic / Form Login: username, password do client gửi
                          |
                          v
                 Authentication Filter
                          |
                          v
                AuthenticationManager
                          |
                          v
               DaoAuthenticationProvider
                    |              |
                    |              +--> PasswordEncoder
                    |                   kiểm tra password với hash
                    v
             UserDetailsService
                    |
                    +--> Spring Data JPA Repository
                    |         |
                    |         +--> Database account + authorities
                    |
                    +--> Hoặc domain account service đáng tin
                    |
                    v
               UserDetails adapter
               username, hash, flags, authorities
                    |
                    v
          Authentication đã xác thực (nếu hợp lệ)
                    |
                    v
          SecurityContext + authorization
```

**Mấu chốt:** `UserDetailsService` **tải hồ sơ**, còn `DaoAuthenticationProvider`/**`PasswordEncoder`** **xác minh** credential. Việc tìm thấy một username trong database chưa chứng minh người đang gửi request sở hữu tài khoản đó.

## 2. Hợp đồng chính xác của UserDetailsService

Interface `org.springframework.security.core.userdetails.UserDetailsService` có một phương thức cốt lõi:

```java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
```

Đây là **chữ ký API rút gọn**, chưa phải file Java độc lập. Những điểm trong contract:

1. `username` là định danh tìm kiếm từ yêu cầu xác thực; nó **chưa phải danh tính đã được chứng minh**.
2. Kết quả phải là `UserDetails` đã được điền những trường cần cho bước kiểm tra tiếp theo.
3. **Không trả `null`** khi không tìm được tài khoản. Ném `UsernameNotFoundException`.
4. Contract cũng xem trường hợp user không có `GrantedAuthority` là không tìm được user; khi chính sách nghiệp vụ cho phép account không có quyền, cần xác định rõ cách biểu diễn quyền tối thiểu hoặc chính sách thay thế, không âm thầm gán quyền nhạy cảm.
5. `UserDetailsService` là **read-only contract**; nó không chịu trách nhiệm tạo user, đổi mật khẩu hoặc login. Các tác vụ quản trị thuộc service/repository riêng hoặc `UserDetailsManager` nếu ứng dụng chọn contract đó.
6. Không tạo `Authentication` thành công, không gắn `SecurityContextHolder`, không tự trả token/cookie trong `loadUserByUsername`.
7. Username của `UserDetails` có thể khác chữ hoa/thường so với chuỗi được yêu cầu khi ứng dụng hỗ trợ lookup không phân biệt hoa/thường. Phải có chính sách chuẩn hóa/unique ở database tương thích.

### UserDetails chứa gì?

Một implementation của `UserDetails` thường cung cấp:

| Method | Nguồn giá trị | Mục đích |
| --- | --- | --- |
| `getUsername()` | Username được quản lý bởi server | Tên tài khoản sau khi tìm |
| `getPassword()` | **Password hash**, không phải plaintext | Provider chuyển cho `PasswordEncoder.matches(...)` |
| `getAuthorities()` | Role/permission đã được mapping từ nguồn tin cậy | Phân quyền sau authentication |
| `isEnabled()` | Cờ kích hoạt tài khoản | Có thể dẫn đến `DisabledException` |
| `isAccountNonLocked()` | `true` khi không khóa | `false` có thể dẫn đến `LockedException` |
| `isAccountNonExpired()` | `true` khi tài khoản còn hạn | `false` có thể dẫn đến `AccountExpiredException` |
| `isCredentialsNonExpired()` | `true` khi credential còn hạn | `false` có thể dẫn đến `CredentialsExpiredException` |

Spring Security có implementation `org.springframework.security.core.userdetails.User` và builder `User.withUsername(...)` để tránh phải tự implement toàn bộ interface trong bài demo. Đối với principal của ứng dụng có **ID nội bộ ổn định**, có thể tạo custom `UserDetails` hoặc converter riêng, nhưng không nên đưa thẳng JPA entity giàu dữ liệu nhạy cảm vào principal.

### Những gì UserDetailsService không làm

- **Không so sánh mật khẩu thô với hash**: việc này thuộc `PasswordEncoder` và provider.
- **Không quyết định quyền trên từng tài nguyên**: `report:read` chỉ là authority tổng quát; xem báo cáo thuộc tenant khác còn phải được domain authorization kiểm tra.
- **Không thay thế OAuth2 Resource Server**: JWT/bearer token thường đi qua decoder/converter, không mặc nhiên gọi `UserDetailsService`.
- **Không bảo đảm quyền được làm mới mỗi request**: session, token và cache có vòng đời riêng.

## 3. Chia trách nhiệm giữa persistence, adapter và security

Một cấu trúc đơn giản có ba tầng:

```text
                    ┌─────────────────────────────┐
                    │ Security Filter / Provider  │
                    │ credential + account status │
                    └─────────────┬───────────────┘
                                  │
                                  v
                    ┌─────────────────────────────┐
                    │ JpaUserDetailsService       │
                    │ implements UserDetailsService│
                    │ chuyển DomainAccount -> User │
                    └─────────────┬───────────────┘
                                  │
                                  v
                    ┌─────────────────────────────┐
                    │ AccountRepository           │
                    │ @EntityGraph(authorities)   │
                    └─────────────┬───────────────┘
                                  │
                                  v
                    ┌─────────────────────────────┐
                    │ Database: accounts + grants │
                    └─────────────────────────────┘
```

**Repository** chịu trách nhiệm truy vấn JPA. **Service/adapter** áp đặt hợp đồng danh tính, xác minh dữ liệu nguồn có thể dùng được, ánh xạ trạng thái và quyền. **Provider** chịu trách nhiệm kiểm tra credential và phát kết quả authentication đáng tin. **SecurityFilterChain** chọn cách nhận credential và chính sách truy cập HTTP.

Tránh đặt toàn bộ logic SQL, kiểm tra mật khẩu, chuyển tên quyền và tạo HTTP response trong một controller `/login`. Cũng không nên đưa `HttpServletRequest` vào domain account service chỉ để lấy username/tenant: cần ranh giới truyền thông tin đáng tin và policy rõ.

### Nguồn dữ liệu dùng JPA có gì đặc biệt?

- Entity do JPA quản lý có thể chứa quan hệ `LAZY`. Sau khi đóng transaction, đọc role/authority dễ gặp `LazyInitializationException`.
- Nhiều truy vấn nhỏ có thể gây N+1 queries.
- Entity có thể bị thay đổi trong transaction; không dùng entity mutable làm phiên bản user principal kéo dài nhiều request.
- Query username cần chính sách unique rõ ràng và cần tính đến đồng thời/đổi tên.
- Database có thể lỗi tạm thời. Không nên “fail open” bằng cách cấp một user mặc định.
- Một tài khoản có thể tồn tại nhưng bị disable, locked hoặc credential expired; chúng vẫn là hồ sơ có thật với trạng thái cần ánh xạ.

Trong ví dụ dưới, ta dùng `@Transactional(readOnly = true)` để thực hiện việc đọc trong transaction và `@EntityGraph` để tải collection authorities cho đúng lần lookup.

## 4. Thiết kế bảng account tối thiểu để phục vụ xác thực

Ví dụ dùng hai bảng:

```text
app_accounts
  id                 UUID PRIMARY KEY
  username           VARCHAR UNIQUE NOT NULL
  password_hash      VARCHAR NOT NULL
  enabled            BOOLEAN NOT NULL
  locked             BOOLEAN NOT NULL
  account_expired    BOOLEAN NOT NULL
  credentials_expired BOOLEAN NOT NULL

app_account_authorities
  account_id         UUID REFERENCES app_accounts(id)
  authority          VARCHAR NOT NULL
```

Bảng thứ hai chứa **authority name đã qua hợp đồng nghiệp vụ**, chẳng hạn `ROLE_USER` và `report:read`. Đây là **mô hình minh họa** giúp tập trung vào JPA/`UserDetailsService`. Trong ứng dụng lớn hơn, domain có thể lưu `users`, `roles`, `permissions`, `user_roles`, `role_permissions` rồi map thành chuỗi tương ứng.

### Vì sao lưu hash thay vì plaintext?

Khi user đăng ký hoặc đổi mật khẩu, server nhận mật khẩu **chỉ tại thời điểm tạo/đổi** rồi dùng `PasswordEncoder.encode(raw)` để lưu hash phù hợp. Khi đăng nhập, `DaoAuthenticationProvider` dùng `PasswordEncoder.matches(raw, encoded)` để kiểm tra, không lấy plaintext từ DB và không tự hash raw rồi so sánh chuỗi hash theo cách ngây thơ (BCrypt dùng salt nên hai lần encode cùng input có thể khác nhau).

### Cờ trạng thái phải nhất quán

Trong domain schema ta lưu `locked`, `accountExpired`, `credentialsExpired` dưới dạng cờ “đang lỗi”. Khi chuyển sang `UserDetails`, builder dùng các method `accountLocked(true)`, `accountExpired(true)`, `credentialsExpired(true)`. Nếu tự implement `UserDetails`, các method `isAccountNonLocked()`, `isAccountNonExpired()` và `isCredentialsNonExpired()` có nghĩa **phủ định**, nên cần đảo giá trị đúng.

Lưu ý: “subscription hết hạn” không luôn là “account expired”. Nhiều hệ thống vẫn cho người dùng đăng nhập để xem hóa đơn hoặc gia hạn; đó là quy tắc nghiệp vụ khác.

## 5. Ví dụ chạy được: Spring Boot 4 + Spring Data JPA + H2

Ví dụ sau cung cấp **các file hoàn chỉnh** để chạy bằng Java 17+. Tạo project Maven mới theo cấu trúc:

```text
jpa-auth-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jpaauth/
    │   ├── JpaAuthDemoApplication.java
    │   ├── AccountEntity.java
    │   ├── AccountRepository.java
    │   ├── JpaAccountUserDetailsService.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── resources/application.properties
```

Mô hình có ba tài khoản:

| Username | Mật khẩu demo | Trạng thái | Authorities |
| --- | --- | --- | --- |
| `an` | `demo-pass` | Hoạt động | `ROLE_USER`, `report:read` |
| `binh` | `demo-pass` | Hoạt động | `ROLE_ADMIN` |
| `khoa` | `demo-pass` | Bị khóa | `ROLE_USER` |

Dữ liệu chỉ để học tập, không phải credential an toàn cho môi trường thật.

### 5.1. `pom.xml`

Spring Boot 4 sử dụng starter `spring-boot-starter-webmvc` cho Spring MVC. Maven parent quản lý phiên bản của các dependency còn lại.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jpa-auth-demo</artifactId>
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
            <artifactId>spring-boot-starter-data-jpa</artifactId>
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

Có thể dùng Spring Initializr để sinh Maven wrapper và một phiên bản ổn định cùng nhánh Spring Boot 4.x; nếu chọn nhánh khác cần kiểm tra tên starter/API tương thích. Ví dụ ghim `4.0.0` để người học có một cấu hình tái lập được, không phải yêu cầu mọi dự án production dùng phiên bản này.

### 5.2. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:authdemo;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

`create-drop` xóa/tạo schema cho **demo H2 in-memory**, không dùng cho production vì có thể làm mất dữ liệu. `spring.jpa.open-in-view=false` giúp phát hiện những chỗ vô ý truy cập quan hệ LAZY sau transaction, đồng thời khuyến khích adapter tải đầy đủ dữ liệu cần thiết bên trong ranh giới giao dịch. Database in-memory biến mất khi ứng dụng dừng.

### 5.3. `AccountEntity.java` — entity JPA, không phải principal

```java
package com.example.jpaauth;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

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
public class AccountEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, unique = true, length = 100)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 100)
    private String passwordHash;

    @Column(nullable = false)
    private boolean enabled;

    @Column(nullable = false)
    private boolean locked;

    @Column(name = "account_expired", nullable = false)
    private boolean accountExpired;

    @Column(name = "credentials_expired", nullable = false)
    private boolean credentialsExpired;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
            name = "app_account_authorities",
            joinColumns = @JoinColumn(name = "account_id"))
    @Column(name = "authority", nullable = false, length = 120)
    private Set<String> authorities = new HashSet<>();

    protected AccountEntity() {
        // JPA cần constructor không tham số.
    }

    public AccountEntity(String username,
                         String passwordHash,
                         boolean enabled,
                         boolean locked,
                         boolean accountExpired,
                         boolean credentialsExpired,
                         Set<String> authorities) {
        this.username = username;
        this.passwordHash = passwordHash;
        this.enabled = enabled;
        this.locked = locked;
        this.accountExpired = accountExpired;
        this.credentialsExpired = credentialsExpired;
        this.authorities = new HashSet<>(authorities);
    }

    public UUID getId() {
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

    public boolean isLocked() {
        return locked;
    }

    public boolean isAccountExpired() {
        return accountExpired;
    }

    public boolean isCredentialsExpired() {
        return credentialsExpired;
    }

    public Set<String> getAuthorities() {
        return Set.copyOf(authorities);
    }
}
```

Những điều cần nhìn ra:

- `id` là UUID do persistence tạo và có thể dùng làm **internal user ID ổn định**, kể cả khi username đổi. Ví dụ này chưa đưa ID vào principal; nếu service nghiệp vụ cần ID, thiết kế custom principal riêng, không dùng username làm khóa sở hữu.
- `passwordHash` phục vụ kiểm tra mật khẩu, không được trả thẳng ra API hoặc ghi log.
- `authorities` là `LAZY`. `@EntityGraph` ở repository sẽ yêu cầu nạp collection trong lần lookup dành cho authentication.
- `AccountEntity` **không implements UserDetails**. Tách entity khỏi Security API giúp kiểm soát dữ liệu nào được đưa vào `Authentication`.
- `getAuthorities()` trả bản sao không thay đổi được, tránh việc code bên ngoài vô tình sửa tập quyền đang lưu trong entity.
- Entity có no-arg constructor `protected` để JPA khởi tạo; không thêm những setter dư thừa chỉ để tiện cho security adapter.

### 5.4. `AccountRepository.java` — truy vấn account và quyền

```java
package com.example.jpaauth;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository
        extends JpaRepository<AccountEntity, UUID> {

    @EntityGraph(attributePaths = "authorities")
    Optional<AccountEntity> findByUsername(String username);

    boolean existsByUsername(String username);
}
```

`@EntityGraph(attributePaths = "authorities")` yêu cầu JPA nạp tập quyền cùng account trong lần lookup này. Với một collection nhỏ như demo, cách này dễ theo dõi. Khi có nhiều collection/role/permission phức tạp, cần đo truy vấn thực tế; nhiều fetch join có thể gây cartesian product hoặc memory pressure. Không áp `EAGER` cho mọi quan hệ entity chỉ vì `UserDetailsService` cần authority.

`Optional<AccountEntity>` biểu diễn trạng thái không tìm được hồ sơ. Adapter sẽ đổi nó thành `UsernameNotFoundException` theo contract. Không dùng `Optional.get()` mà không kiểm tra rỗng.

### 5.5. `JpaAccountUserDetailsService.java` — adapter xác thực

```java
package com.example.jpaauth;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JpaAccountUserDetailsService
        implements UserDetailsService {

    private final AccountRepository accounts;

    public JpaAccountUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AccountEntity account = accounts.findByUsername(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Unknown user"));

        String[] authorityNames =
                account.getAuthorities().toArray(String[]::new);

        if (authorityNames.length == 0) {
            // Demo chọn từ chối account không có authority.
            throw new UsernameNotFoundException(
                    "Account has no authorities");
        }

        return User.withUsername(account.getUsername())
                .password(account.getPasswordHash())
                .authorities(authorityNames)
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .accountExpired(account.isAccountExpired())
                .credentialsExpired(account.isCredentialsExpired())
                .build();
    }
}
```

**Đây là ranh giới chính của bài:**

1. `AccountRepository` tìm dữ liệu theo username.
2. Adapter đọc password hash, trạng thái và quyền trong transaction chỉ đọc.
3. Nếu không có user, ném `UsernameNotFoundException`; **không trả null, không trả user giả với quyền cao**.
4. Tập quyền nguồn đã chuẩn hóa được đưa vào `UserDetails` dưới dạng các chuỗi authority. `User.UserBuilder` chuyển chúng thành `GrantedAuthority`.
5. Adapter **không** gọi `PasswordEncoder.matches(...)` và **không** tự tạo một authenticated token.
6. Mapping builder sử dụng cờ dạng “bad state”: `disabled(!enabled)`, `accountLocked(locked)`, `accountExpired(accountExpired)`, `credentialsExpired(credentialsExpired)`.
7. Sau khi method kết thúc, `UserDetails` là một đối tượng ngoài JPA entity; provider không phụ thuộc vào việc transaction JPA còn mở.

Với dữ liệu không có authority, demo chọn từ chối. Tùy nghiệp vụ, bạn có thể có một authority tối thiểu `ROLE_USER` cho tài khoản chỉ được xem hồ sơ, nhưng chỉ cấp khi **đó là chính sách đã được xác định**, không tự thêm `ROLE_ADMIN` hoặc `report:read` vì thiếu dữ liệu.

### 5.6. `SecurityConfiguration.java` — provider, encoder và rule

```java
package com.example.jpaauth;

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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JpaAccountUserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder)
            throws Exception {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(userDetailsService);
        provider.setPasswordEncoder(passwordEncoder);

        return http
                .authenticationProvider(provider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/reports")
                            .hasAuthority("report:read")
                        .requestMatchers("/admin")
                            .hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

`DaoAuthenticationProvider` lấy `UserDetails` từ adapter và dùng BCrypt để đối chiếu password. Nếu username/password/status hợp lệ, Spring Security phát `Authentication` của request. Nếu credential sai, tài khoản bị khóa hoặc vô hiệu hóa, cơ chế tạo lỗi xác thực thích hợp.

Rule `hasAuthority("report:read")` đòi đúng chuỗi `report:read`. Rule `hasRole("ADMIN")` mặc định tìm `ROLE_ADMIN`. Chúng là **quy tắc phân quyền**, độc lập với việc tìm tài khoản ở database.

Ví dụ chỉ có **GET** và HTTP Basic để minh họa. Trong ứng dụng dùng trình duyệt, session/cookie và thao tác thay đổi dữ liệu, cần giữ/thiết kế cơ chế CSRF phù hợp; không tắt CSRF toàn cục chỉ để làm cho một demo đăng nhập chạy.

### 5.7. `JpaAuthDemoApplication.java` — nạp dữ liệu demo

```java
package com.example.jpaauth;

import java.util.Set;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class JpaAuthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JpaAuthDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner seedAccounts(
            AccountRepository repository,
            PasswordEncoder encoder) {

        return args -> {
            if (!repository.existsByUsername("an")) {
                repository.save(new AccountEntity(
                        "an", encoder.encode("demo-pass"),
                        true, false, false, false,
                        Set.of("ROLE_USER", "report:read")));
            }

            if (!repository.existsByUsername("binh")) {
                repository.save(new AccountEntity(
                        "binh", encoder.encode("demo-pass"),
                        true, false, false, false,
                        Set.of("ROLE_ADMIN")));
            }

            if (!repository.existsByUsername("khoa")) {
                repository.save(new AccountEntity(
                        "khoa", encoder.encode("demo-pass"),
                        true, true, false, false,
                        Set.of("ROLE_USER")));
            }
        };
    }
}
```

`CommandLineRunner` tạo dữ liệu sau khi JPA/H2 khởi động. `repository.save(...)` thực hiện thao tác ghi để H2 có tài khoản dùng khi kiểm thử. Mật khẩu được lưu dưới dạng BCrypt hash; việc ghi cùng password demo cho ba user chỉ để đơn giản hóa quan sát.

Trong production, tạo account phải là luồng có xác thực đầu vào, kiểm tra password policy, unique username, transaction và xử lý race condition; không tạo tài khoản quản trị bằng `CommandLineRunner` hoặc hardcode password.

### 5.8. `DemoController.java` — quan sát Authentication

```java
package com.example.jpaauth;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "principal=" + authentication.getName();
    }

    @GetMapping("/reports")
    String reports() {
        return "reports ok";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin ok";
    }
}
```

Controller không nhận password, không gọi repository để “kiểm tra lại user”, cũng không đọc `?role=...` từ client để cấp quyền. Nó đọc tên principal đã được cơ chế xác thực đặt vào `Authentication`. Mục đích của `/me` là minh họa đường đi; ứng dụng thực nên cân nhắc chỉ trả ID/profile cần thiết và không xuất raw `Authentication` ra JSON.

## 6. Chạy ví dụ và kiểm tra đầu ra

Cần JDK 17+, Maven 3.9+ hoặc wrapper tương thích và quyền tải dependencies Maven. Từ thư mục `jpa-auth-demo`:

```bash
mvn spring-boot:run
```

Nếu tạo project qua Spring Initializr có wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell có thể chạy `.\mvnw.cmd spring-boot:run`. H2 in-memory bắt đầu rỗng, schema được tạo và ba account được seed khi ứng dụng khởi động. Không gọi `javac` trực tiếp cho từng file vì chúng cần dependency của Spring Boot/JPA/Security.

Mở một terminal khác và thực hiện:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-pass http://localhost:8080/me
curl -s -u an:demo-pass http://localhost:8080/reports
curl -s -u binh:demo-pass http://localhost:8080/admin
```

**Body dự kiến đúng theo thứ tự của bốn lệnh:**

```text
pong
principal=an
reports ok
admin ok
```

Thử các trường hợp từ chối:

```bash
curl -i http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
curl -i -u khoa:demo-pass http://localhost:8080/me
curl -i -u an:demo-pass http://localhost:8080/admin
curl -i -u binh:demo-pass http://localhost:8080/reports
```

Với cấu hình HTTP Basic của demo, **ba request đầu** thường trả **401 Unauthorized** (chưa có credential, password sai, account locked). **Hai request sau** trả **403 Forbidden** vì caller đã xác thực nhưng thiếu authority cần thiết. Error body/header tùy version/cấu hình; Basic challenge thường chứa `WWW-Authenticate` trên 401.

Nếu dùng PowerShell và `curl` bị ánh xạ thành cmdlet khác, thay bằng `curl.exe`. HTTP Basic chỉ mã hóa credential bằng Base64, **không phải mã hóa bảo mật**. Demo dùng localhost; ứng dụng thật phải triển khai HTTPS và quản lý mật khẩu/secret đúng cách.

### Phân tích một request thành công

Khi chạy `curl -u an:demo-pass /reports`:

1. Basic authentication filter đọc header chứa username/password.
2. Provider gọi `JpaAccountUserDetailsService.loadUserByUsername("an")`.
3. Repository lấy account và authority `ROLE_USER`, `report:read` từ H2; `@EntityGraph`/transaction bảo đảm dữ liệu có sẵn khi mapping.
4. Adapter trả `UserDetails` với BCrypt hash, flags và authorities.
5. `DaoAuthenticationProvider` kiểm tra password thô với hash; thành công mới trả authenticated `Authentication`.
6. Rule `hasAuthority("report:read")` được thỏa nên controller trả `reports ok`.

Khi dùng `curl -u binh:demo-pass /reports`, provider vẫn xác thực được Bình, nhưng `Authentication` chỉ có `ROLE_ADMIN` theo policy demo. Rule yêu cầu `report:read` **không được đáp ứng**, nên request bị chặn. `ROLE_ADMIN` không tự hàm ý mọi permission nếu hệ thống không cấu hình mapping/hierarchy khác.

### Làm sao biết app thật sự đang dùng database?

Thử thay đổi account từ nguồn dữ liệu được quản lý và khởi động/xác thực mới theo quy trình, rồi xem quyền cập nhật theo chính sách; với H2 `create-drop`, dữ liệu biến mất giữa các lần restart. Trong môi trường thật, dùng database persistent, schema migrations và kiểm thử repository/SQL chứ không dựa vào một tài khoản Spring Security mặc định được sinh tự động.

## 7. Sử dụng kho nghiệp vụ khác thay cho JPA

`UserDetailsService` không ép buộc sử dụng Spring Data JPA. Có thể là:

- `JdbcTemplate`/SQL trực tiếp với query có tham số.
- Một account/domain service đã có sẵn trong cùng ứng dụng.
- Một dịch vụ người dùng nội bộ cung cấp kết quả qua API tin cậy.
- Directory hoặc LDAP phù hợp với mô hình của tổ chức.
- Một adapter tới kho dữ liệu khác có cơ chế đọc, kiểm tra trạng thái và quyền rõ ràng.

Một skeleton cho kho nghiệp vụ:

```java
@Service
class DomainUserDetailsService implements UserDetailsService {

    private final AccountQueryService accountQueries;

    DomainUserDetailsService(AccountQueryService accountQueries) {
        this.accountQueries = accountQueries;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        DomainAccount account = accountQueries.findByLogin(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Unknown user"));

        return User.withUsername(account.login())
                .password(account.encodedPassword())
                .authorities(account.authorityNames().toArray(String[]::new))
                .disabled(!account.enabled())
                .build();
    }
}
```

Đây là **mảnh mã thiết kế**, cần các import Spring Security, `AccountQueryService` và `DomainAccount` của ứng dụng để biên dịch. Không đặt song song hai bean `UserDetailsService` cùng mục đích mà chưa quy định rõ provider nào sử dụng cái nào. Cơ chế xác thực nên được cấu hình tường minh nếu có nhiều kho.

**Contract không đổi:** lookup user -> lấy hash/flags/authorities từ nguồn tin cậy -> chuyển thành `UserDetails` -> để provider kiểm tra credential. Nếu dịch vụ bên ngoài **đã xác thực bằng giao thức riêng** mà không trả password hash hợp lệ, đừng cố làm giả `UserDetails.getPassword()` để dùng DAO provider; cần `AuthenticationProvider` hoặc giải pháp OIDC/OAuth2/LDAP thích hợp.

### Khi account service ở xa

Một remote call không đáng tin chỉ vì nó “ở trong mạng nội bộ”. Phải xác định xác thực giữa các service, timeout, retry, circuit breaker, nguồn cấp authority, audit và cách xử lý khi dịch vụ không khả dụng. Nếu không thể xác minh danh tính hoặc lấy quyền bắt buộc, thông thường **từ chối authentication/authorization**, không fallback thành `ROLE_USER` hoặc `ROLE_ADMIN` tùy ý.

Không log raw password, raw bearer token hay session cookie trong request/tracing; hạn chế dữ liệu cá nhân và credential lưu trong cache/message. Một IDP chuyên dụng có thể phù hợp hơn cho hệ thống nhiều dịch vụ cần SSO.

## 8. Truy vấn JPA hiệu quả và tránh lỗi LazyInitializationException

### Vì sao LAZY dễ lỗi?

Giả sử `AccountEntity` có `@OneToMany(fetch = LAZY)` hoặc `@ManyToMany(fetch = LAZY)` đối với roles. Nếu adapter trả JPA entity làm principal rồi code đọc role sau khi transaction đóng, Hibernate có thể không tải được collection. Để tránh:

- Lấy đủ trường cần cho authentication trong transaction.
- Dùng `@EntityGraph(attributePaths = ...)` hoặc query/projection được thiết kế theo nhu cầu.
- Map **ngay** entity sang `UserDetails` là đối tượng độc lập với session JPA.
- Không bật `spring.jpa.open-in-view=true` chỉ để che lỗi ở controller; điều đó giữ persistence context mở lâu hơn và có thể khiến truy vấn ngầm xảy ra trong web layer.

### `@EntityGraph` và N+1

Demo chỉ có một tập `authorities`, `@EntityGraph` giúp một lần lookup có sẵn authority. Nhưng với domain phức tạp (roles, permissions, groups, tenants), fetch nhiều collection trong cùng query có thể tạo nhiều dòng join, tiêu tốn memory hoặc gặp những giới hạn ORM. Hãy đo SQL:

| Vấn đề | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| Lazy access sau transaction | `LazyInitializationException` | Map trong transaction và fetch đúng quan hệ |
| N+1 | Một query account kéo theo nhiều query roles/permissions | Projection/query chuyên dụng, batch fetch hoặc entity graph phù hợp |
| Cartesian product | Một query trả rất nhiều dòng do join nhiều collection | Chia query, tránh fetch nhiều collection đồng thời |
| Query không dùng index | Lookup username chậm | Unique index/normalization đúng nhu cầu |
| Duplicate username | Không rõ chọn user nào | DB uniqueness, xử lý phân biệt hoa/thường |
| Tài khoản thiếu authority | Lỗi hoặc quy tắc không nhất quán | Chính sách empty-authority được xác định trước |

Chỉ thêm `@Transactional(readOnly = true)` lên method **không thay thế** việc thiết kế truy vấn tốt; nó cho biết đây là thao tác đọc và giữ transaction trong quá trình mapping. Với kho bên ngoài không phải JPA, semantics transaction/read-only khác nhau.

### Query projection có thể tốt hơn entity đầy đủ

Nếu entity user rất lớn hoặc role được lưu qua nhiều bảng, bạn có thể viết query chỉ trả về `username`, `passwordHash`, status flags và authority names, rồi build `UserDetails`. Điều này giảm nguy cơ vô tình nạp PII/profile dữ liệu. Tuy vậy phải xử lý uniqueness, multiplicity và consistency khi ghép các kết quả.

## 9. PasswordEncoder, trạng thái tài khoản và lỗi xác thực

### PasswordEncoder

`PasswordEncoder` là thành phần xác minh credential:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String encoded = encoder.encode("demo-pass");
boolean valid = encoder.matches("demo-pass", encoded);
System.out.println(valid); // true
```

Đây là **mảnh Java minh họa**, cần các import Spring Security và đặt trong method hoặc JShell có classpath. Password hash BCrypt có salt, nên gọi `encode` nhiều lần thường tạo chuỗi khác nhau. Không dùng `encoded.equals(encoder.encode(raw))` để so khớp.

Với kho đã dùng nhiều thuật toán hash theo thời kỳ, có thể dùng `DelegatingPasswordEncoder` theo định dạng có tiền tố `{id}` và chiến lược migration được quản lý. Không chọn `{noop}` hoặc plain text làm giải pháp production chỉ để “đăng nhập được”.

### Account flags

Chuyển các flag chính xác:

| Entity field | Builder call | Ý nghĩa |
| --- | --- | --- |
| `enabled=true` | `disabled(false)` | Không vô hiệu hóa |
| `locked=true` | `accountLocked(true)` | Account đang bị khóa |
| `accountExpired=true` | `accountExpired(true)` | Account đã hết hạn |
| `credentialsExpired=true` | `credentialsExpired(true)` | Credential đã hết hạn |

Trong DAO provider, account status có thể dẫn đến `DisabledException`, `LockedException`, `AccountExpiredException`, `CredentialsExpiredException`. Nếu username không có, `UserDetailsService` ném `UsernameNotFoundException`; provider mặc định thường che để client không dễ dò account. Không trả nguyên exception message hoặc SQL error ra HTTP public.

Một account có thể bị khóa sau khi **đã có session đăng nhập từ trước**. Việc thay cờ trong database không tự hủy mọi session/token hiện hữu; cần có chính sách invalidation, token expiry, revoke hoặc kiểm tra status hiện hành ở tác vụ nhạy cảm.

### Lỗi DB khác lỗi password

Nếu database timeout, kết nối bị lỗi hoặc schema migration chưa hoàn thành, adapter phải để hệ thống ghi nhận một **lỗi hạ tầng**, không tự trả một user giả hoặc bỏ qua xác thực. Nơi xử lý exception của framework có thể đưa ra phản hồi HTTP tùy cơ chế, nhưng telemetry cần phân biệt sai mật khẩu với sự cố datasource. Không log JDBC URL chứa credential, mật khẩu hoặc thông tin nhạy cảm trong error response.

## 10. Bảo vệ lookup username và tránh lỗi phân biệt hoa/thường

Username/email là **lookup key**, không nhất thiết là khóa ID ổn định. Khi ứng dụng hỗ trợ thay đổi username/email, nên dùng internal account ID (ví dụ UUID) trong foreign key, ownership, audit. `Authentication.getName()` của DAO user details thông thường trả username, không đương nhiên là UUID của database.

### Quy tắc chuẩn hóa

Một số lựa chọn:

- Username phân biệt hoa/thường: `An` và `an` có thể là hai account khác nhau nếu DB/schema cho phép.
- Username không phân biệt hoa/thường: định nghĩa canonical form và unique constraint hỗ trợ, tránh hai username khác nhau chỉ do chữ hoa/thường.
- Login bằng email: email có thể đổi và cần xác minh theo chính sách; không dùng email làm khóa sở hữu bất biến.
- Multi-tenant: có thể cần khóa duy nhất `(tenant_id, normalized_username)` thay vì username toàn cục.

Không tự `trim()` hoặc `toLowerCase()` input một cách không đồng nhất giữa đăng ký, đăng nhập và lookup; việc chuẩn hóa cần có hợp đồng rõ, xử lý Unicode và unique index tương ứng. Với hệ thống đa tenant, tenant ID do caller gửi cũng phải được xác minh theo context/giao thức đáng tin; không chỉ nhận header tự khai rồi dùng làm ranh giới bảo mật.

### Dò tài khoản

Không nên thông báo “username không tồn tại” cho một request public nhưng “password sai” cho username có thật. Để hạn chế user enumeration, cơ chế DAO provider có chính sách che username-not-found, nhưng ứng dụng còn phải quản lý timing, rate limiting, monitoring và luồng khôi phục tài khoản an toàn. Không suy luận rằng cứ gặp `BadCredentialsException` thì chắc chắn account tồn tại.

## 11. Mapping quyền nghiệp vụ sang GrantedAuthority

Với demo, `app_account_authorities` lưu sẵn các chuỗi Spring Security đọc được: `ROLE_USER`, `ROLE_ADMIN`, `report:read`. Trong domain thật, nguồn có thể lưu:

```text
users(id, username, password_hash, enabled)
roles(id, role_code)
permissions(id, permission_code)
user_roles(user_id, role_id)
role_permissions(role_id, permission_id)
user_permissions(user_id, permission_id)
```

Adapter hoặc domain permission service cần quyết định:

1. Role code `ADMIN` được chuyển thành `ROLE_ADMIN` (theo prefix mặc định).
2. Permission code `report:read` được giữ thành `report:read` và dùng qua `hasAuthority("report:read")`.
3. Permission từ nhiều role/direct grant được hợp nhất, loại trùng.
4. Unknown role/permission không trở thành quyền cao tùy ý; xử lý theo policy đã được định nghĩa.
5. Authority không tự bao hàm owner/tenant checks. `report:read` chỉ thỏa điều kiện quyền chung, chưa quyết định user được đọc báo cáo nào.

Nếu user có role `ADMIN`, điều đó **không tự** thỏa `hasAuthority("report:read")` nếu mapping không cấp permission ấy; đừng ngầm cho toàn quyền chỉ vì tên “ADMIN”.

**Không nhận list role/permission do client gửi khi login** rồi chuyển thành `SimpleGrantedAuthority`. Quyền phải đến từ nguồn server/issuer được tin cậy sau khi xác minh các điều kiện cần.

## 12. Caching và vòng đời UserDetails

Cache có thể giảm truy vấn khi lượng login lớn, nhưng cache sai khiến quyền/trạng thái cũ kéo dài:

- `UserDetails` có thể chứa password hash, nên vị trí lưu/cache phải được bảo vệ và TTL phù hợp.
- Khi password, role, khóa account hoặc trạng thái enabled thay đổi, cần chính sách invalidate/refresh.
- `ProviderManager` có thể xóa credentials khỏi `Authentication`/principal sau thành công theo contract; nếu cache dùng chung đối tượng `UserDetails`, phải hiểu ảnh hưởng của credential erasure để không làm cache lỗi.
- Session-based login có thể giữ `Authentication` trong session, không tự gọi `UserDetailsService` ở mọi request.
- JWT bearer token có quy trình xác minh/claim mapping riêng; không mặc định mỗi request JWT sẽ hỏi JPA để nạp quyền trừ khi bạn thiết kế như vậy.

Nếu cần quyền hiện hành cho giao dịch nhạy cảm, có thể kiểm tra ở policy service thay vì tin hoàn toàn snapshot từ lúc login. Quy tắc TTL/revoke phải được kiểm thử trong tình huống user bị disable hoặc mất role khi session/token vẫn còn hiệu lực.

## 13. Testing: kiểm tra repository, adapter và HTTP theo mục tiêu

Nên kiểm thử theo ranh giới trách nhiệm, tránh chỉ test controller trả 200:

| Tầng | Trường hợp | Kết quả cần có |
| --- | --- | --- |
| Repository | Tìm username tồn tại | Trả đúng account và authority được nạp |
| Repository | Username không tồn tại | `Optional.empty()` |
| Adapter | Account tồn tại | `UserDetails` có username, hash, flags, authorities đúng |
| Adapter | Không có account | Ném `UsernameNotFoundException`, không trả `null` |
| Adapter | Account không có authority | Xử lý theo policy fail closed, không cấp quyền lạ |
| Provider | Password đúng + account active | Authentication thành công |
| Provider | Password sai | Authentication thất bại |
| Provider | Account locked | Authentication thất bại dù password đúng |
| HTTP | `/reports` với `an` | Thành công vì `report:read` |
| HTTP | `/reports` với `binh` | 403 vì không có `report:read` |
| HTTP | `/admin` với `binh` | Thành công vì `ROLE_ADMIN` |
| HTTP | Credential sai/không có | 401 ở Basic demo |
| Lifecycle | Thu hồi quyền sau login | Hiệu lực theo cơ chế refresh/revoke đã xác định |
| Database | H2 không hoạt động/thiếu bảng | Thất bại an toàn, có telemetry |

Với integration test, có thể dùng H2/test database và `@DataJpaTest` hoặc `@SpringBootTest` theo dependency test phù hợp. Với Spring Boot 4, các starter test được tách theo module; cần chọn dependency test phù hợp với công nghệ thực tế. Không bắt buộc tự viết test cho từng getter của entity; trọng tâm là hành vi nạp account, mapping quyền và quyết định truy cập.

### Một bài kiểm tra thay đổi account

Thử mô phỏng: tài khoản An đang có `report:read`; người quản trị thu hồi quyền. Kiểm tra lần xác thực mới và session/token đã tồn tại. Hai kết quả có thể khác nhau vì session/cache lưu snapshot; một thiết kế đúng phải quy định và thực thi thời điểm thu hồi có hiệu lực.

### Kiểm tra SQL thực tế

Dùng công cụ giám sát truy vấn của môi trường dev/test để quan sát `findByUsername` có phát sinh thêm N query cho các quyền không; kiểm tra plan/index username và không log mật khẩu/token trong quá trình debug. Với production, tránh bật log SQL chứa thông tin bí mật một cách vô kiểm soát.

## 14. Sai lầm thường gặp và cách xử lý

| Sai lầm | Vấn đề | Cách làm phù hợp |
| --- | --- | --- |
| `UserDetailsService` tự so sánh password với hash | Lặp sai trách nhiệm, dễ bỏ sót policy | Provider dùng `PasswordEncoder.matches` |
| Trả `null` khi không tìm thấy user | Vi phạm contract | Ném `UsernameNotFoundException` |
| Trả JPA entity làm principal lâu dài | Lazy loading, mutation, rò dữ liệu | Map sang `UserDetails`/principal tối thiểu |
| Đưa password thô vào DB | Lộ credential | Lưu password hash bằng encoder phù hợp |
| Dùng `{noop}` chỉ để demo rồi đem lên production | Mật khẩu không được hash | BCrypt/Argon2/DelegatingPasswordEncoder theo policy |
| Dùng `getAuthorities()` từ relation LAZY sau transaction | `LazyInitializationException` | Transaction + fetch/projection, map tại adapter |
| Bật EAGER mọi quan hệ | N+1 hoặc query rất lớn | Query đúng cho lần lookup authentication |
| Mặc định unknown role thành ADMIN | Privilege escalation | Validate/fail closed |
| Dùng username/email làm owner ID | Thay đổi/reuse làm nhầm dữ liệu | Dùng ID nội bộ bất biến |
| Không kiểm tra uniqueness username | Có thể tìm nhầm nhiều account | Unique index + canonicalization |
| Cho Basic chạy qua HTTP public | Dễ lộ credential | HTTPS, TLS, bảo vệ logging |
| Đặt `?role=ADMIN` làm quyền | Caller tự nâng quyền | Chỉ đọc nguồn quyền tin cậy |
| Coi auth success là đủ quyền tài nguyên | IDOR, cross-tenant | Resource/tenant authorization |
| Disable user nhưng không xét session cũ | Quyền tiếp tục tồn tại ở phiên cũ | Session/token revoke/refresh |
| Lỗi DB thì tạo user “fallback” | Fail open | Từ chối xác thực, cảnh báo vận hành |
| Dùng raw `Authentication` làm JSON trả client | Có thể rò hash/PII/claims | DTO giới hạn dữ liệu cần thiết |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `loadUserByUsername("an")` trả `UserDetails`, vậy An đã đăng nhập thành công chưa?  
**Trả lời:** Chưa. Đây chỉ là bước nạp hồ sơ; `DaoAuthenticationProvider` vẫn phải xác minh credential và trạng thái account.

**Câu 2.** Dùng `@Transactional(readOnly = true)` trên adapter có thay thế `@EntityGraph` không?  
**Trả lời:** Không. Transaction giữ phạm vi persistence khi đọc; entity graph/projection quyết định dữ liệu nào được nạp. Hai thành phần giải quyết vấn đề khác nhau.

**Câu 3.** Repository trả `Optional.empty()`. Adapter có được trả `null` không?  
**Trả lời:** Không. Ném `UsernameNotFoundException` theo `UserDetailsService` contract.

**Câu 4.** Vì sao không nên cho entity `AccountEntity` trực tiếp implements `UserDetails` trong mọi trường hợp?  
**Trả lời:** Có thể làm persistence phụ thuộc security, khiến lazy collection, mutable state, hash và các trường không cần thiết đi vào principal lâu dài. Adapter tách trách nhiệm và dữ liệu.

**Câu 5.** Database lưu authority `ROLE_ADMIN`. Rule `hasAuthority("report:read")` có tự cho phép không?  
**Trả lời:** Không. Chuỗi authority phải khớp rule hoặc policy/hierarchy được cấu hình đúng.

**Câu 6.** Tại sao password hash từ repository phải được đưa vào `UserDetails.getPassword()`?  
**Trả lời:** Vì `DaoAuthenticationProvider` cần hash và `PasswordEncoder` để kiểm tra raw password từ request. Không lưu/so sánh plaintext trong repository.

**Câu 7.** Nếu account bị khóa sau khi đã có session, liệu `UserDetailsService` được gọi lại ở request sau?  
**Trả lời:** Không bảo đảm. Session có thể giữ authentication cũ; cần chính sách thu hồi/refresh/kiểm tra account state.

**Câu 8.** Một API khác xác thực qua JWT đã ký, có nhất thiết gọi JPA `UserDetailsService` cho mỗi request?  
**Trả lời:** Không. Resource server thường dùng decoder/converter. Nếu cần mapping sang account nội bộ thì thiết kế một bước riêng có hợp đồng và cache/validation rõ.

**Câu 9.** Vì sao `findByUsername` cần uniqueness ở database, kể cả khi service có kiểm tra?  
**Trả lời:** Để bảo đảm một lookup xác thực chỉ ánh xạ một tài khoản, tránh race condition và duplicate trong thao tác tạo/sửa. Unique constraint là lớp bảo vệ dưới cùng.

**Câu 10.** Khi nào nên dùng một adapter tới kho nghiệp vụ thay JPA?  
**Trả lời:** Khi nguồn sự thật về tài khoản đã được quản lý bởi domain/identity service khác, hoặc ứng dụng cần cơ chế lưu trữ không phải JPA. `UserDetailsService` chỉ cần thực thi đúng contract và tin cậy nguồn dữ liệu.

## Kết luận

`UserDetailsService` là **cầu nối đọc dữ liệu giữa kho tài khoản nghiệp vụ và cơ chế xác thực username/password của Spring Security**. Cách tích hợp đúng là lấy user/hash/trạng thái/quyền từ repository hoặc service tin cậy, chuyển thành `UserDetails` đầy đủ **trong transaction đọc phù hợp**, rồi để `DaoAuthenticationProvider` và `PasswordEncoder` thực hiện xác thực. Kết quả thành công mới được đặt vào `Authentication`/`SecurityContext` và dùng để kiểm tra quyền.

Một thiết kế tốt giữ persistence tách khỏi principal, sử dụng query hiệu quả, xử lý user không tồn tại bằng exception đúng contract, kiểm soát password hash/PII, đồng bộ authority và có chính sách session/token khi account thay đổi.

**Ghi nhớ:** *Repository biết dữ liệu tài khoản; `UserDetailsService` biết cách biểu diễn dữ liệu cho Spring Security; `AuthenticationProvider` biết kiểm tra credential; authorization quyết định request đã xác thực được phép làm gì.*

### Tài liệu tham khảo chính thức

- [Spring Security 7 — UserDetailsService](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 7 — UserDetails](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/user-details.html)
- [Spring Security 7 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 7 — Username/Password Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/index.html)
- [Spring Boot 4 — Developing Your First Application (WebMVC starter)](https://docs.spring.io/spring-boot/4.0/tutorial/first-application/index.html)
- [Spring Boot 4 — SQL Databases and JPA](https://docs.spring.io/spring-boot/4.0/reference/data/sql.html)
- [Spring Data JPA — Reference Documentation](https://docs.spring.io/spring-data/jpa/reference/)
