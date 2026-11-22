# UserDetails, UserDetailsService và UserDetailsManager: vai trò riêng

## 1. Ba khái niệm, ba trách nhiệm trong Spring Security Servlet

Khi xây dựng chức năng đăng nhập bằng username/password trong ứng dụng Spring Security Servlet, ta thường gặp ba kiểu có tên gần giống nhau:

- **`UserDetails`** mô tả **một tài khoản được dùng để xác thực và phân quyền**: tên đăng nhập, mật khẩu đã mã hóa, quyền (authorities) và trạng thái tài khoản.
- **`UserDetailsService`** là hợp đồng **tra cứu** `UserDetails` theo username. Nó không tự kiểm tra password và không định nghĩa API tạo/sửa/xóa tài khoản.
- **`UserDetailsManager`** mở rộng `UserDetailsService`, bổ sung **thao tác quản lý tài khoản** như tạo, cập nhật, xóa, đổi mật khẩu và kiểm tra username tồn tại.

Tên các kiểu được viết đúng như trong Spring Security:

```java
org.springframework.security.core.userdetails.UserDetails
org.springframework.security.core.userdetails.UserDetailsService
org.springframework.security.provisioning.UserDetailsManager
```

Ba dòng này là tên kiểu để định vị package, **không phải chương trình Java độc lập**.

Điểm then chốt: **`UserDetails` là dữ liệu / principal; `UserDetailsService` là hợp đồng đọc; `UserDetailsManager` là hợp đồng đọc + ghi**. Các lớp xác thực như `DaoAuthenticationProvider` sử dụng chúng thông qua API thích hợp, còn controller quản lý tài khoản là trách nhiệm của ứng dụng.

### So sánh nhanh

| Tiêu chí | `UserDetails` | `UserDetailsService` | `UserDetailsManager` |
| --- | --- | --- | --- |
| Bản chất | Interface mô tả một tài khoản | Interface tra cứu tài khoản | Interface quản lý tài khoản, kế thừa `UserDetailsService` |
| Phương thức trọng tâm | `getUsername`, `getPassword`, `getAuthorities`, các trạng thái tài khoản | `loadUserByUsername` | `createUser`, `updateUser`, `deleteUser`, `changePassword`, `userExists` và `loadUserByUsername` kế thừa |
| Đối tượng trả về | Một triển khai `UserDetails` chính là dữ liệu | `UserDetails` hoặc ném `UsernameNotFoundException` | Tùy thao tác; `loadUserByUsername` cũng trả `UserDetails` |
| Có kiểm tra mật khẩu người dùng nhập? | Không | Không | Không phải trách nhiệm chính của interface |
| Có tạo/sửa/xóa user? | Không | Không | Có các operation tương ứng |
| Triển khai có sẵn | `org.springframework.security.core.userdetails.User` | Service tùy biến, hoặc một manager cụ thể | `InMemoryUserDetailsManager`, `JdbcUserDetailsManager` |

## 2. Vị trí trong luồng xác thực username/password

Với HTTP Basic hoặc form login sử dụng `DaoAuthenticationProvider` và một kho tài khoản thông thường, có thể hình dung dòng chảy:

```text
HTTP request kèm username/password
      |
      v
Authentication Filter (Basic / Form Login)
      |
      v
AuthenticationManager (thường ProviderManager)
      |
      v
DaoAuthenticationProvider
      |
      +---- UserDetailsService.loadUserByUsername(username)
      |                |
      |                v
      |           UserDetails
      |        username/password-hash/
      |        authorities/account flags
      |
      +---- PasswordEncoder.matches(rawPassword, encodedPassword)
      |
      +---- Kiểm tra account flags, thực hiện các bước xác thực liên quan
      |
      +---- Thành công: authenticated Authentication
      |                  (có principal, authorities)
      |
      +---- Thất bại: AuthenticationException phù hợp
      |
      v
Các cơ chế quản lý SecurityContext / response
      |
      v
Các filter phân quyền và controller nếu được cho phép
```

Đây là **luồng điển hình**, không phải danh sách đầy đủ hoặc thứ tự bất biến của mọi provider. Spring Security có nhiều cơ chế đăng nhập: JWT, OAuth2, SAML, pre-authentication hoặc custom provider có thể **không gọi `UserDetailsService`**.

Đặc biệt:

1. `UserDetailsService` **không nhận password ứng viên**; nó chỉ có tham số username.
2. `DaoAuthenticationProvider` mới sử dụng `PasswordEncoder` để so sánh mật khẩu người dùng nhập với **mật khẩu đã mã hóa** trong `UserDetails`.
3. Sau xác thực, thông tin dùng trong `SecurityContext` được biểu diễn bởi `Authentication`. `UserDetails` có thể là `principal` của `Authentication`, nhưng **`Authentication` và `UserDetails` không đồng nghĩa**.
4. `UserDetailsManager` **không phải thành phần bắt buộc** trong xác thực. Một `UserDetailsService` chỉ đọc là đủ nếu việc quản lý tài khoản do hệ thống khác đảm nhiệm.

## 3. UserDetails: tài khoản được biểu diễn như thế nào?

`UserDetails` là interface trong `org.springframework.security.core.userdetails`. Nó cho framework biết dữ liệu cần để kiểm tra danh tính, mật khẩu và trạng thái tài khoản, cũng như những quyền đã cấp.

Một bản tóm tắt các phương thức liên quan:

```java
// Chữ ký rút gọn để giải thích, không phải toàn bộ mã nguồn interface.
String getUsername();
String getPassword();
Collection<? extends GrantedAuthority> getAuthorities();

boolean isAccountNonExpired();
boolean isAccountNonLocked();
boolean isCredentialsNonExpired();
boolean isEnabled();
```

Trong đó `GrantedAuthority` thuộc `org.springframework.security.core`. Các phương thức `is...` thể hiện điều kiện **được phép hoạt động**, nên `isAccountNonLocked() == true` nghĩa là tài khoản **không bị khóa**.

### 3.1. Ba nhóm dữ liệu

**Danh tính:** `getUsername()` là tên được dùng cho lookup. Nó không nhất thiết là email hoặc khóa chính database, nhưng chính sách chuẩn hóa username phải nhất quán giữa bước đăng ký và bước đăng nhập.

**Thông tin kiểm tra xác thực:** `getPassword()` thường trả về **chuỗi password hash** có format mà `PasswordEncoder` tương ứng hiểu được. Không lưu mật khẩu plaintext. Một số cơ chế xác thực không dựa trên password có thể dùng UserDetails theo cách khác; đừng suy luận rằng mọi principal đều có password.

**Thông tin phân quyền:** `getAuthorities()` trả các `GrantedAuthority` như `ROLE_READER`, `ROLE_ADMIN` hoặc `order:read`. Authority là đơn vị chuỗi quyền; role là một cách quy ước authority, thường có tiền tố `ROLE_`.

### 3.2. Trạng thái tài khoản

| Phương thức | Ý nghĩa khi trả `true` | Một ví dụ |
| --- | --- | --- |
| `isEnabled()` | Tài khoản được bật | Tài khoản đã xác minh/không bị vô hiệu hóa |
| `isAccountNonLocked()` | Tài khoản không bị khóa | Không bị khóa vì chính sách bảo mật |
| `isAccountNonExpired()` | Tài khoản còn hiệu lực | Không vượt thời hạn sử dụng |
| `isCredentialsNonExpired()` | Credentials còn hiệu lực | Mật khẩu chưa đến hạn phải thay |

`DaoAuthenticationProvider` kiểm tra các điều kiện này khi xác thực, và có thể ném ngoại lệ tương ứng cho tài khoản không hợp lệ. Việc bật/tắt các cờ phải xuất phát từ quy định nghiệp vụ và bảo mật; không đặt tất cả thành `true` một cách vô điều kiện nếu ứng dụng có yêu cầu khóa/hết hạn.

### 3.3. Dùng User có sẵn hay tạo lớp UserDetails riêng?

Spring Security có lớp `User` triển khai `UserDetails`:

```java
UserDetails reader = User.withUsername("reader")
    .password(encodedPassword)
    .roles("READER")
    .disabled(false)
    .build();
```

Đây là **đoạn nằm trong code có sẵn `encodedPassword`**; cần import `org.springframework.security.core.userdetails.User` và `UserDetails`. `roles("READER")` tạo authority `ROLE_READER` theo quy ước mặc định. Nếu dùng `authorities("ROLE_READER")` thì cung cấp chính xác authority, không tự thêm tiền tố.

Khi ứng dụng có id, tenant, tên hiển thị hoặc thuộc tính tùy biến thật sự cần lúc xác thực, có thể tạo lớp implements `UserDetails`, hoặc chuyển entity thành `User`/principal riêng. **Không dùng trực tiếp JPA entity làm principal nếu điều đó làm lộ dữ liệu nhạy cảm, kéo theo lazy-loading ngoài transaction hoặc ràng buộc security layer quá chặt vào persistence layer.**

## 4. UserDetailsService: chỉ định cách tìm user theo username

Giao diện tối giản:

```java
@FunctionalInterface
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
```

Đây là **trích giản lược hợp đồng**. Điểm quan trọng là tên username được cung cấp và giá trị trả về là một `UserDetails`. Nếu không tìm thấy tài khoản, hợp đồng yêu cầu báo lỗi bằng `UsernameNotFoundException`; không trả `null` để biểu thị “không tìm thấy”.

### 4.1. UserDetailsService không tự xác thực mật khẩu

Không viết logic như sau trong service:

```java
// Sai về phân chia trách nhiệm:
if (rawPassword.equals(account.getPasswordHash())) {
    return account;
}
```

Bên cạnh việc so sánh sai hash, `loadUserByUsername` không được thiết kế để nhận `rawPassword`. Hãy để `DaoAuthenticationProvider` và `PasswordEncoder` xử lý password verification.

### 4.2. Ánh xạ tài khoản domain sang UserDetails

Ví dụ **minh họa tích hợp persistence**, cố ý dùng hai abstraction `AccountRepository` / `AccountRecord` do ứng dụng định nghĩa, nên **không phải chương trình tự chạy độc lập**:

```java
@Service
public class AccountLookupService implements UserDetailsService {
    private final AccountRepository repository;

    public AccountLookupService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountRecord record = repository.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        return User.withUsername(record.username())
            .password(record.passwordHash()) // Hash đã lưu, không encode lại.
            .authorities(record.authorities().toArray(String[]::new))
            .disabled(!record.enabled())
            .accountLocked(record.locked())
            .build();
    }
}
```

Các kiểu `AccountRepository`/`AccountRecord` là giả định của ví dụ. Phần code cần imports `@Service`, `UserDetails`, `UserDetailsService`, `User`, `UsernameNotFoundException` và các lớp domain thích hợp. Trong ứng dụng thực, repository có thể dùng JDBC, JPA, LDAP hoặc API dịch vụ khác; không có yêu cầu bắt buộc phải dùng JPA.

Quy trình:

- Tìm record theo username với chính sách chuẩn hóa thống nhất.
- Không tìm thấy → `UsernameNotFoundException`.
- Tìm thấy → chuyển sang `UserDetails`, đưa hash sẵn có vào `password`, map authority và trạng thái chính xác.
- Authentication provider lấy `UserDetails` để tiến hành xác thực; service chỉ chịu trách nhiệm lookup.

**Lưu ý về rò rỉ thông tin tài khoản:** thông báo trả tới HTTP client không nên cho phép dò username tồn tại hay không. Framework/provider có cơ chế che giấu khác biệt nhất định, nhưng thông báo, timing, log và endpoint riêng của ứng dụng vẫn cần được rà soát.

### 4.3. Vì sao tên là "Service" nhưng chỉ có một phương thức?

Ở đây “Service” mô tả hợp đồng truy xuất phục vụ authentication, **không phải application service CRUD tổng quát**. Ứng dụng có thể có `AccountApplicationService` với các nghiệp vụ tạo user, gửi email, đổi mật khẩu, xác minh danh tính, audit; không cần ép toàn bộ nghiệp vụ đó vào `UserDetailsService`.

## 5. UserDetailsManager: mở rộng tra cứu để thay đổi user

`UserDetailsManager` kế thừa `UserDetailsService`, bổ sung các thao tác quản trị user:

```java
// Chữ ký cốt lõi, không phải toàn bộ mã nguồn interface.
void createUser(UserDetails user);
void updateUser(UserDetails user);
void deleteUser(String username);
void changePassword(String oldPassword, String newPassword);
boolean userExists(String username);

// loadUserByUsername(String username) được kế thừa từ UserDetailsService.
```

Điều này dẫn đến một quan hệ kiểu rất cụ thể:

```java
UserDetailsManager manager = obtainUserDetailsManager();
UserDetailsService lookup = manager; // Hợp lệ vì Manager extends Service.
UserDetails account = lookup.loadUserByUsername("reader");
```

Đoạn trên là **minh họa với hàm `obtainUserDetailsManager()` giả định**, không phải chương trình độc lập.

### 5.1. Các implementation thường gặp

**`InMemoryUserDetailsManager`:** giữ tài khoản trong bộ nhớ của tiến trình. Phù hợp với ví dụ, bài test, prototype hoặc danh sách tài khoản đơn giản cố định. Không phải lựa chọn lưu trữ bền vững cho tài khoản sản xuất: restart thường làm mất thay đổi runtime.

**`JdbcUserDetailsManager`:** quản lý tài khoản bằng JDBC với schema hoặc truy vấn tương ứng. Cần `DataSource` và bảng/cấu hình phù hợp; không thể chỉ đổi class trong ứng dụng mà bỏ qua database/schema. Nó phù hợp khi muốn dùng mô hình dữ liệu mặc định hoặc tùy biến truy vấn trong phạm vi hợp đồng.

**Custom manager:** có thể tự triển khai interface nếu cần CRUD trên hệ thống riêng, nhưng phải xử lý thêm transaction, kiểm tra quyền thay đổi tài khoản, concurrency, username uniqueness, mật khẩu, audit và các ràng buộc domain.

### 5.2. Không phải ứng dụng nào cũng cần UserDetailsManager

Nếu user được cấp bởi một hệ thống ngoài, ứng dụng có thể chỉ cần `UserDetailsService` để đọc dữ liệu phục vụ xác thực. Nếu dùng JWT được phát hành bởi identity provider, có thể cả ba kiểu này không tham gia đường xác thực request.

Ngược lại, khi muốn tạo/xóa tài khoản qua Spring Security interface, `UserDetailsManager` là một abstraction hữu ích. Nhưng `createUser`/`deleteUser` là **API server-side**; chúng không tự tạo endpoint HTTP và cũng không tự kiểm tra người gọi có phải admin hay không. Authorization, validation và audit cho endpoint quản lý tài khoản thuộc trách nhiệm ứng dụng.

### 5.3. Cẩn thận với changePassword

`changePassword(oldPassword, newPassword)` biểu diễn nghiệp vụ thay mật khẩu theo hợp đồng manager. Tùy implementation, hoạt động này có thể cần `Authentication` hiện tại trong `SecurityContextHolder` và có cơ chế kiểm tra mật khẩu cũ. Không nên gọi nó như API quản trị “reset mật khẩu bất kỳ tài khoản nào” khi chưa hiểu implementation.

Không nhầm đổi mật khẩu do chủ tài khoản thực hiện với reset password qua token xác minh, quản lý phiên đăng nhập và thu hồi session. Các quy trình đó cần thiết kế riêng.

## 6. Ví dụ Spring Boot 3 + Java 17 hoàn chỉnh

Ví dụ này có thể chạy với Spring Boot 3.3.5, Java 17, Maven và Servlet stack. Nó dùng `InMemoryUserDetailsManager` làm **cả `UserDetailsManager` lẫn `UserDetailsService`**, `DaoAuthenticationProvider` của cấu hình authentication tương ứng để kiểm tra password, và HTTP Basic để quan sát phản hồi.

Các tài khoản là dữ liệu **học tập** trong bộ nhớ. Ứng dụng thật cần cơ chế cấp phát secrets, lưu trữ và audit thích hợp.

### 6.1. Cấu trúc dự án

```text
account-interfaces-demo/
  pom.xml
  src/
    main/java/demo/accounts/
      AccountsApplication.java
      SecurityConfig.java
      AccountController.java
    test/java/demo/accounts/
      AccountInterfacesTest.java
```

### 6.2. Maven pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>account-interfaces-demo</artifactId>
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

### 6.3. Lớp khởi động

`src/main/java/demo/accounts/AccountsApplication.java`:

```java
package demo.accounts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountsApplication.class, args);
    }
}
```

### 6.4. SecurityConfig: UserDetailsManager làm bean cung cấp tài khoản

`src/main/java/demo/accounts/SecurityConfig.java`:

```java
package demo.accounts;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.provisioning.UserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsManager userDetailsManager(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password(encoder.encode("locked-pass"))
            .roles("READER")
            .accountLocked(true)
            .build();

        return new InMemoryUserDetailsManager(reader, admin, locked);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Điểm quan sát:

1. Bean `UserDetailsManager` thực tế là `InMemoryUserDetailsManager`, đồng thời thỏa hợp đồng `UserDetailsService` để provider tải tài khoản.
2. Mỗi password gốc chỉ xuất hiện để tạo dữ liệu thử; `PasswordEncoder` tạo hash BCrypt trước khi `UserDetails` được lưu.
3. `roles("ADMIN")` tạo `ROLE_ADMIN`; do đó `hasRole("ADMIN")` được thỏa mãn.
4. User `locked` vẫn **có thể được tra cứu** từ service, nhưng authentication phải bị từ chối vì `isAccountNonLocked()` là `false`.
5. `httpBasic(...)` bật HTTP Basic; username/password không nên truyền trên đường HTTP không mã hóa ở môi trường thực. Sử dụng HTTPS.
6. `UserDetailsManager` không tạo endpoint quản trị. Cấu hình chỉ có các route được khai báo ở controller.

Trong cấu hình thông thường, khi có bean `UserDetailsService`/`UserDetailsManager` và `PasswordEncoder` thích hợp, Spring Security thiết lập đường xác thực DAO tương ứng để HTTP Basic sử dụng. Nếu ứng dụng còn tự định nghĩa `AuthenticationProvider` hoặc `AuthenticationManager`, phải kiểm tra cấu hình thực tế vì cách chọn provider có thể khác.

### 6.5. Controller dùng principal, không gọi loadUserByUsername thủ công

`src/main/java/demo/accounts/AccountController.java`:

```java
package demo.accounts;

import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String me(@AuthenticationPrincipal UserDetails principal) {
        String role = principal.getAuthorities()
            .iterator().next().getAuthority();
        return principal.getUsername() + " | " + role;
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin";
    }
}
```

Với bộ user thử nghiệm này, mỗi tài khoản có đúng một authority nên `iterator().next()` là hợp lệ. Trong ứng dụng thật, không được giả định mọi principal có đúng một authority hoặc luôn implements `UserDetails`: một số cơ chế xác thực có principal dạng `Jwt`, `OAuth2User` hoặc kiểu tùy chỉnh. Controller ở ví dụ nhận dữ liệu principal **sau khi framework xác thực**, không tự gọi `loadUserByUsername` để “xác thực lại”.

### 6.6. Kiểm thử thực sự đi qua lookup và PasswordEncoder

`src/test/java/demo/accounts/AccountInterfacesTest.java`:

```java
package demo.accounts;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.UserDetailsManager;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountInterfacesTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    UserDetailsManager manager;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void meRequiresAuthentication() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsLoadReader() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader | ROLE_READER"));
    }

    @Test
    void invalidPasswordIsRejected() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("reader", "bad-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void lockedAccountCannotAuthenticate() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("locked", "locked-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void managerCanCreateUpdateAndDeleteUser() {
        String username = "temporary-learner";
        UserDetails temporary = User.withUsername(username)
            .password(encoder.encode("temporary-pass"))
            .roles("READER")
            .build();

        try {
            manager.createUser(temporary);
            assertTrue(manager.userExists(username));

            UserDetails changed = User.withUserDetails(temporary)
                .roles("ADMIN")
                .build();
            manager.updateUser(changed);

            UserDetails stored = manager.loadUserByUsername(username);
            assertTrue(stored.getAuthorities().contains(
                new SimpleGrantedAuthority("ROLE_ADMIN")));
        } finally {
            if (manager.userExists(username)) {
                manager.deleteUser(username);
            }
        }

        assertFalse(manager.userExists(username));
    }
}
```

Test `httpBasic(username, password)` gửi thông tin HTTP Basic qua filter chain thay vì đặt sẵn principal bằng `user(...)`. Do đó các test hợp lệ/sai password và tài khoản bị khóa thực sự quan sát **đường xác thực username/password**, khác với `.with(user(...))` vốn dựng một user đã được xác thực trong test mà không cần kiểm tra password qua `UserDetailsService`.

Test CRUD cuối cùng trực tiếp gọi `UserDetailsManager` và dọn tài khoản `temporary-learner` trong `finally` để hạn chế ảnh hưởng tới test khác. Đây là tài khoản thử trong bộ nhớ; nó không được tự động public thành REST API.

### 6.7. Lệnh chạy và kết quả mong đợi

Tại thư mục dự án có `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

`mvn test` kiểm tra tám test case; nếu cấu hình và môi trường phù hợp, tất cả đều pass. Stdout của Maven/Spring Boot phụ thuộc máy và phiên bản nên không có chuỗi chính xác cố định. Các kết quả HTTP có thể kiểm chứng là:

| Thao tác | Kết quả |
| --- | --- |
| `GET /public` không có credential | 200, body `public` |
| `GET /me` không có credential | 401 |
| `GET /me` với `reader/reader-pass` | 200, body `reader \| ROLE_READER` |
| `GET /me` với password sai | 401 |
| `GET /me` với `locked/locked-pass` | 401 |
| `GET /admin` với `reader/reader-pass` | 403 |
| `GET /admin` với `admin/admin-pass` | 200, body `admin` |

Lưu ý: bảng trên mô tả cấu hình **HTTP Basic cụ thể**. Nếu dùng form login, một request anonymous có thể nhận 302 redirect; không khái quát mọi thất bại xác thực đều là 401.

Muốn thử thủ công sau khi server chạy, dùng HTTPS trong môi trường thật; tại localhost chỉ để học:

```bash
curl -i http://localhost:8080/public
curl -i -u reader:reader-pass http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
```

Các credential trên là tài khoản học tập và không được sao chép sang production.

## 7. Chạy độc lập Java 17: minh họa hợp đồng đọc và quản lý

Đoạn dưới mô phỏng chính sự phân chia giữa **record người dùng**, **hợp đồng lookup**, **hợp đồng quản lý**. Các interface `Lookup` và `Manager` được viết riêng, **không phải API Spring Security**, và không có password authentication. Mục đích là quan sát luồng đọc và thao tác CRUD bằng một file Java chạy độc lập.

Tạo `AccountContractsDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class AccountContractsDemo {
    record Account(String username, String authority) {}

    interface Lookup {
        Account load(String username);
    }

    interface Manager extends Lookup {
        void create(Account account);
        void update(Account account);
        void delete(String username);
        boolean exists(String username);
    }

    static class MemoryManager implements Manager {
        private final Map<String, Account> accounts = new LinkedHashMap<>();

        public Account load(String username) {
            Account account = accounts.get(username);
            if (account == null) {
                throw new IllegalArgumentException("Unknown account");
            }
            return account;
        }

        public void create(Account account) {
            if (exists(account.username())) {
                throw new IllegalArgumentException("Already exists");
            }
            accounts.put(account.username(), account);
        }

        public void update(Account account) {
            if (!exists(account.username())) {
                throw new IllegalArgumentException("Unknown account");
            }
            accounts.put(account.username(), account);
        }

        public void delete(String username) {
            accounts.remove(username);
        }

        public boolean exists(String username) {
            return accounts.containsKey(username);
        }
    }

    public static void main(String[] args) {
        MemoryManager manager = new MemoryManager();
        manager.create(new Account("mai", "ROLE_READER"));

        Lookup lookup = manager; // Manager cung cấp cả hợp đồng đọc.
        System.out.println("lookup: " + lookup.load("mai").authority());

        manager.update(new Account("mai", "ROLE_ADMIN"));
        System.out.println("updated: " + lookup.load("mai").authority());

        manager.delete("mai");
        System.out.println("exists: " + manager.exists("mai"));
    }
}
```

Biên dịch và chạy:

```bash
javac AccountContractsDemo.java
java AccountContractsDemo
```

Stdout **chính xác**:

```text
lookup: ROLE_READER
updated: ROLE_ADMIN
exists: false
```

Mô hình này không hash password, không tạo `SecurityContext` và không thực hiện `DaoAuthenticationProvider`; các phần đó nằm ở ví dụ Spring Boot thật. Cả hai ví dụ củng cố một ý: **manager hỗ trợ lookup vì kế thừa service; record dữ liệu không trở thành service hoặc manager.**

## 8. Thiết kế với database thật

Với dữ liệu tài khoản doanh nghiệp, có thể tổ chức các lớp theo ranh giới:

```text
Domain/Persistence:
  AccountEntity + AccountRepository
          |
          +--> đọc bằng username
          |
          v
Security integration:
  AccountUserDetailsService
          |
          +--> map AccountEntity thành UserDetails/principal
          |
          v
DaoAuthenticationProvider + PasswordEncoder
          |
          v
Authentication / SecurityContext

Application management:
  AccountManagementService
          |
          +--> kiểm tra quyền, validation, transaction, audit
          |
          +--> tạo user, cấp quyền, đổi mật khẩu, khóa/xóa account
          |
          v
AccountRepository
```

**Không bắt buộc** mọi ứng dụng phải triển khai `UserDetailsManager` riêng. Nếu cần interface này, có thể cho application service/adapter triển khai và giữ nghiệp vụ đúng tầng. Cần tách rõ **tra cứu phục vụ xác thực** khỏi **quản lý vòng đời tài khoản**, tránh để một endpoint REST gọi thẳng `deleteUser` mà thiếu xác minh quyền và audit.

Một số quyết định thực tế:

- **Username uniqueness:** enforce cả ở database; kiểm tra trước bằng `userExists` chỉ là kiểm tra tiện lợi, không thay thế unique constraint và xử lý race condition.
- **Password storage:** hash bằng `PasswordEncoder` tại thời điểm tạo/đổi; khi load từ database, trả hash đã lưu **không encode lại**. Có chính sách nâng cấp thuật toán/chi phí hash khi cần.
- **Role mapping:** phân biệt `roles("ADMIN")` và `authorities("ROLE_ADMIN")`. Đừng lẫn tên role domain với chuỗi `GrantedAuthority` thực tế.
- **Account state:** ánh xạ cờ locked/disabled/expired đúng nghiệp vụ; tránh tự bật cờ mặc định làm mất hiệu lực khóa tài khoản.
- **Transaction và audit:** các thay đổi quyền, khóa hoặc xóa cần được ghi nhận và giao dịch nhất quán, nhất là khi dùng nhiều bảng.
- **Cache:** nếu cache `UserDetails`, phải có chiến lược vô hiệu hóa/cập nhật sau khi đổi password, role hoặc trạng thái tài khoản.
- **Existing sessions/tokens:** thay đổi role hoặc vô hiệu hóa account không nhất thiết tự cập nhật tất cả `Authentication` đã tồn tại trong session/JWT. Cần chính sách session invalidation hoặc token revocation/revalidation thích hợp theo hệ thống.
- **Multi-tenant:** xác định username có unique toàn hệ thống hay theo tenant. Chỉ nhận username trong hợp đồng đơn giản không tự giải quyết tenant isolation.
- **Đăng ký và xác minh:** `UserDetailsManager.createUser` không thay thế các bước email verification, consent, chống abuse, rate limiting hay các quy tắc khác của nghiệp vụ.
- **User enumeration:** tránh trả thông báo khác nhau cho “user không tồn tại” và “password sai” theo cách để người ngoài dò danh sách tài khoản.

## 9. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Coi `UserDetailsService` là nơi kiểm tra password | Ghép sai trách nhiệm, dễ so sánh plaintext với hash | Service chỉ load user; provider + encoder kiểm tra credential |
| `loadUserByUsername` trả `null` nếu không thấy | Vi phạm hợp đồng, có thể dẫn đến lỗi khó hiểu | Ném `UsernameNotFoundException` |
| Gọi `encoder.encode` trên hash đã lấy từ database | Mật khẩu đúng vẫn không match | Khi lưu password mới thì encode; khi load thì trả hash nguyên vẹn |
| Dùng `roles("ROLE_ADMIN")` | Tiền tố role có thể bị áp dụng sai hoặc builder từ chối | Dùng `roles("ADMIN")` hoặc `authorities("ROLE_ADMIN")` |
| Tưởng `getAuthorities` là danh sách username/tenant | Phân quyền sai hoặc lộ dữ liệu | Map thành quyền thực sự và kiểm tra chính sách |
| Coi `isAccountNonLocked()==false` là đã được phép đăng nhập | Bỏ qua ý nghĩa cờ | `false` nghĩa là đang bị khóa |
| Gán `UserDetails` vào mọi `Authentication.getPrincipal()` bằng ép kiểu cứng | Lỗi runtime với JWT/OAuth2/custom principal | Kiểm tra kiểu principal và cơ chế xác thực đang dùng |
| Dùng `.with(user(...))` trong test để chứng minh tra password | Test bypasses credential verification | Dùng `httpBasic(...)` hoặc request đăng nhập thật qua filters |
| Dùng `InMemoryUserDetailsManager` để lưu user sản xuất dài hạn | Mất thay đổi sau restart; không có persistence độc lập | Dùng persistence phù hợp, schema và transaction rõ ràng |
| Công khai `UserDetailsManager` thành API CRUD không có authorization | Có thể cấp quyền/xóa tài khoản trái phép | Tạo application layer, authorization, validation, audit |
| Cho rằng đổi role trong DB sẽ cập nhật ngay mọi session/JWT | Quyền cũ có thể còn tồn tại | Có chính sách revalidation/revocation/session management |
| Tạo đồng thời nhiều `UserDetailsService`/`AuthenticationProvider` mà không hiểu thứ tự chọn | Có thể dùng nhầm nguồn người dùng hoặc provider | Kiểm tra cấu hình AuthenticationManager thực tế |
| Log `getPassword()` hoặc credential nhập vào | Lộ thông tin bảo mật | Không log hash/password/token hoặc credential nhạy cảm |

## 10. Cách debug khi đăng nhập hoặc quyền truy cập sai

Khi cùng username nhưng đăng nhập thất bại hoặc quyền không đúng, lần lượt kiểm tra:

1. **SecurityFilterChain nào khớp request?** Có thực sự dùng HTTP Basic/form login và provider DAO mong muốn không?
2. **Provider nào đang được gọi?** Nếu là JWT/OAuth2, `UserDetailsService` có thể không được dùng cho request đó.
3. **Bean lookup nào được inject?** Có nhiều `UserDetailsService` hoặc `UserDetailsManager` cùng tồn tại không? Mỗi bean có nguồn dữ liệu nào?
4. **Username lookup:** đúng case-sensitivity, chuẩn hóa và tenant chưa? Không tìm thấy có được chuyển thành `UsernameNotFoundException` không?
5. **PasswordEncoder:** hash đang lưu có đúng format/algorithm không? Có ai encode hash lần thứ hai hoặc lưu plaintext không?
6. **Account flags:** `isEnabled`, `isAccountNonLocked`, `isAccountNonExpired`, `isCredentialsNonExpired` có phù hợp trạng thái user không?
7. **Authorities:** `getAuthorities()` thật sự chứa gì, `ROLE_` prefix thế nào, quy tắc `hasRole`/`hasAuthority` yêu cầu gì?
8. **Sau xác thực:** `SecurityContext` và authentication đã được lưu/khôi phục đúng nếu ứng dụng session-based chưa? Nếu stateless, request tiếp theo có credential/token cần thiết không?
9. **HTTP response:** phân biệt failure của authentication (thường 401 với Basic) và authorization (thường 403 với user đã đăng nhập). Method security hoặc filter khác cũng có thể tác động.

Trong môi trường phát triển có thể dùng log chẩn đoán:

```properties
logging.level.org.springframework.security=DEBUG
```

Tránh bật logging nhạy cảm ở môi trường production mà không kiểm soát. Đừng ghi password gốc, password hash, session ID hoặc access token.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `UserDetailsService.loadUserByUsername("lan")` trả về tài khoản `lan` cùng password hash. Người dùng nhập password sai. Interface nào có nhiệm vụ so sánh?

**Đáp án:** `UserDetailsService` chỉ tra cứu. Trong luồng DAO thông thường, `DaoAuthenticationProvider` gọi `PasswordEncoder.matches(...)` để kiểm tra password, và xác thực thất bại nếu không khớp.

**Câu 2.** Một tài khoản có `isAccountNonLocked() == false` và mật khẩu đúng. Có được xác thực thành công không?

**Đáp án:** Không theo luồng kiểm tra trạng thái của `DaoAuthenticationProvider`, vì tài khoản bị khóa.

**Câu 3.** Tại sao `UserDetailsManager` có thể được inject vào biến kiểu `UserDetailsService`?

**Đáp án:** Vì `UserDetailsManager extends UserDetailsService`. Nó có tất cả khả năng tra cứu của service và thêm thao tác quản lý.

**Câu 4.** `roles("ADMIN")` và `authorities("ROLE_ADMIN")` có gì giống nhau?

**Đáp án:** Theo quy ước prefix mặc định, cả hai tạo authority `ROLE_ADMIN`. `roles("ROLE_ADMIN")` không phải cách truyền role name phù hợp.

**Câu 5.** Bạn cần đăng ký user, xác minh email, ghi audit, khóa tài khoản khi cần và reset password bằng token. Chỉ `UserDetailsManager` đã đủ chưa?

**Đáp án:** Chưa. Interface manager cung cấp một số thao tác user cơ bản; các nghiệp vụ xác minh, authorization, token, audit và transaction cần application/domain layer.

**Câu 6.** Một test dùng `.with(user("reader"))` thì có chứng minh mật khẩu của `reader` được xác minh qua `PasswordEncoder` không?

**Đáp án:** Không. Nó cung cấp principal thử nghiệm đã xác thực. Muốn chứng minh credential lookup và password verification, dùng đường đăng nhập thật như HTTP Basic trong `MockMvc`.

**Câu 7.** Sau khi cấp thêm `ROLE_ADMIN` trong database, session hiện có có tự nhận role mới không?

**Đáp án:** Không có bảo đảm. `Authentication` đã được tạo trong session/token có thể giữ authority cũ. Cần thiết kế chính sách làm mới hoặc thu hồi ngữ cảnh phiên/token phù hợp.

## 12. Ghi nhớ

- `UserDetails`: **bản mô tả tài khoản** gồm username, password hash, authorities và cờ trạng thái.
- `UserDetailsService`: **hợp đồng chỉ đọc**, `loadUserByUsername` trả `UserDetails` hoặc ném `UsernameNotFoundException`.
- `UserDetailsManager`: **mở rộng service để quản lý**, có CRUD và đổi mật khẩu; `InMemoryUserDetailsManager` và `JdbcUserDetailsManager` là ví dụ.
- `DaoAuthenticationProvider` cùng `PasswordEncoder` xử lý kiểm tra password; không dồn việc này vào `UserDetailsService`.
- `Authentication` là kết quả/ngữ cảnh xác thực; principal có thể là `UserDetails` nhưng không bắt buộc ở mọi cơ chế.
- Vai trò quản lý tài khoản cần policy, authorization và audit riêng. Các interface Spring Security cung cấp nền tảng, không tự biến thành API ứng dụng an toàn.
