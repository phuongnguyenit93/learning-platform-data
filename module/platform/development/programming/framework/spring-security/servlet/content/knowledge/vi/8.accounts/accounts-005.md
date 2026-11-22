# DaoAuthenticationProvider và quá trình đối chiếu thông tin đăng nhập

> **Ngữ cảnh:** Spring Security **Servlet**, Java 17+, Spring Security 6.x. Nội dung tập trung vào cách `DaoAuthenticationProvider` kiểm tra username/password với tài khoản do `UserDetailsService` cung cấp. Ví dụ cuối bài dùng Spring Boot 3.x để có ứng dụng Servlet chạy được; cơ chế provider vẫn áp dụng khi khởi tạo Spring Security mà không dùng Boot.

## 1. Vai trò của DaoAuthenticationProvider

Khi người dùng gửi username và mật khẩu, ứng dụng mới nhận được một **lời khai danh tính và bằng chứng**. Chưa thể coi người dùng đã được xác thực hoặc tin các role gửi từ client. Phải kiểm tra bằng chứng dựa trên dữ liệu tài khoản đáng tin cậy, rồi mới tạo `Authentication` có trạng thái đã xác thực.

`DaoAuthenticationProvider` là một `AuthenticationProvider` của Spring Security cho **username/password authentication**. Nó lấy thông tin tài khoản bằng `UserDetailsService`, kiểm tra trạng thái tài khoản, sử dụng `PasswordEncoder` đối chiếu mật khẩu đầu vào với hash đã lưu, rồi trả `Authentication` hợp lệ hoặc ném `AuthenticationException`.

“DAO” không có nghĩa provider chỉ dùng được với JDBC/JPA. Provider không trực tiếp biết bảng `users` hay `UserRepository`; `UserDetailsService` có thể được cài bằng database, dịch vụ danh tính hoặc in-memory store.

| Thành phần | Trách nhiệm | Không có trách nhiệm |
| --- | --- | --- |
| `BasicAuthenticationFilter` / `UsernamePasswordAuthenticationFilter` | Lấy credentials từ HTTP request, tạo authentication request, gọi manager và xử lý HTTP success/failure | Không tự kiểm tra BCrypt hash |
| `AuthenticationManager` | Hợp đồng `authenticate(Authentication)` | Không phải DAO tải entity |
| `ProviderManager` | Triển khai manager phổ biến, chọn `AuthenticationProvider` tương thích | Không biết schema bảng users |
| **`DaoAuthenticationProvider`** | Kiểm tra username/password dựa trên `UserDetailsService` và `PasswordEncoder` | Không trực tiếp thiết lập HTTP session hoặc cấp quyền truy cập URL |
| `UserDetailsService` | Tìm và trả `UserDetails` theo username | Không tự xác thực mật khẩu |
| `PasswordEncoder` | Hash khi lưu mật khẩu, so `matches(raw, encoded)` khi đăng nhập | Không tìm người dùng |
| `UserDetails` | Cung cấp encoded password, trạng thái tài khoản và authorities từ nguồn tin cậy | Không tự xác nhận HTTP request hợp lệ |

Cần phân biệt **authentication** và **authorization**. Dao provider chỉ kiểm tra credentials/tài khoản. Người dùng xác thực thành công vẫn có thể bị `AuthorizationFilter` từ chối vì thiếu quyền truy cập endpoint.

## 2. Luồng tổng thể trong ứng dụng Servlet

```text
HTTP request: Basic Authorization header hoặc POST login form
                  |
                  v
Spring Security filter trong Servlet filter chain
  - đọc username/password
  - tạo UsernamePasswordAuthenticationToken chưa xác thực
                  |
                  v
AuthenticationManager.authenticate(request)
                  |
                  v
ProviderManager
  - tìm AuthenticationProvider có supports() phù hợp
                  |
                  v
DaoAuthenticationProvider
  +--> UserDetailsService.loadUserByUsername(username)
  +--> Kiểm tra account non-locked, enabled, non-expired
  +--> PasswordEncoder.matches(rawPassword, storedPasswordHash)
  +--> Kiểm tra credentials non-expired
  +--> Tạo Authentication đã xác thực
                  |
         +--------+------------+
         |                     |
    Authentication       AuthenticationException
    có principal,        (BadCredentials, Disabled,
    authorities           Locked, ...)
         |                     |
         v                     v
Filter lưu/đặt         Filter/entry point
SecurityContext       xử lý thất bại (ví dụ HTTP 401)
         |
         v
AuthorizationFilter: kiểm tra quyền của request
         |
         v
Controller hoặc 403 nếu không đủ quyền
```

**Một yêu cầu chưa xác thực** thường có kiểu `UsernamePasswordAuthenticationToken` với username và raw password. Khi thành công, provider tạo đối tượng `Authentication` khác với principal/authorities đã được xác minh. `ProviderManager` thường xóa credentials khỏi result khi có thể. Sau đó **security filter**, chứ không phải DAO provider, xử lý `SecurityContext`, cookie/session/HTTP response.

`DaoAuthenticationProvider` kế thừa behavior từ `AbstractUserDetailsAuthenticationProvider`, vì vậy có cả các bước kiểm tra account status và cơ chế cache/retry tùy cấu hình.

## 3. Đầu vào của provider phải là yêu cầu chưa được tin

Ví dụ một token chưa xác thực:

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "lan", "mat-khau-tu-form");

System.out.println(request.isAuthenticated()); // false
System.out.println(request.getName());          // lan
```

Đây là **fragment** để hiểu contract, không phải class độc lập. `principal` thường ban đầu là username dạng chuỗi; `credentials` là mật khẩu vừa gửi; `authorities` chưa được cấp. Không lấy role/authorities do client gửi để tạo kết quả authenticated trước khi provider kiểm chứng.

`DaoAuthenticationProvider` chủ yếu hỗ trợ `UsernamePasswordAuthenticationToken`. Method `supports(Class<?>)` chỉ trả lời **provider có khả năng xử lý kiểu authentication này không**, không kết luận thông tin đăng nhập đúng.

Đầu ra thành công có thể là `UsernamePasswordAuthenticationToken` đã authenticated, nhưng principal thường chuyển thành `UserDetails` (hoặc String nếu cấu hình thay đổi). Bởi vậy việc cast `authentication.getPrincipal()` sang `String` một cách mù quáng không an toàn. Với mã tổng quát, `authentication.getName()` thường thuận tiện hơn.

## 4. UserDetailsService tải tài khoản, không kiểm chứng mật khẩu

Hợp đồng của Spring Security:

```java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
```

Đây là chữ ký rút gọn để minh họa, **không cần định nghĩa interface này** trong dự án vì Spring Security đã có.

`UserDetailsService` cung cấp `UserDetails`, thường chứa:

| Method/thuộc tính | Ý nghĩa khi so khớp |
| --- | --- |
| `getUsername()` | Username đã lấy từ kho tài khoản |
| `getPassword()` | **Password hash đã lưu**, không phải plaintext |
| `getAuthorities()` | Quyền/role đáng tin cậy từ server hoặc IdP |
| `isEnabled()` | Tài khoản được kích hoạt hay không |
| `isAccountNonLocked()` | `false` nghĩa tài khoản bị khóa |
| `isAccountNonExpired()` | `false` nghĩa tài khoản hết hiệu lực |
| `isCredentialsNonExpired()` | `false` nghĩa credentials hết hạn |

Ví dụ từ bảng `users` có cột `password_hash`, `enabled`, `locked`: implementation `UserDetailsService` cần ánh xạ các field này chính xác. Nếu `locked=true` trong database thì phải trả `isAccountNonLocked()==false`; nếu quên mapping, tài khoản đã khóa vẫn có thể được đăng nhập. Các role phải lấy từ dữ liệu được tin cậy, không lấy từ `role` trong JSON người dùng tự khai.

Nếu không tìm thấy username, service ném `UsernameNotFoundException`. Theo cấu hình mặc định, `DaoAuthenticationProvider` thường **che chi tiết này thành `BadCredentialsException`** để thông báo thất bại đăng nhập không tiết lộ tài khoản có tồn tại hay không.

Trong môi trường thật, nên có unique constraint hoặc quy tắc chuẩn hóa username/email rõ ràng; cẩn thận với chữ hoa/thường, Unicode và việc đổi username. Tránh tiết lộ thông tin kho tài khoản qua exception message.

## 5. Quá trình đối chiếu: kiểm tra từng lớp

### 5.1. Chọn provider tương thích

`ProviderManager` thường quản lý một danh sách `AuthenticationProvider`. Với token `UsernamePasswordAuthenticationToken`, nó chọn provider báo `supports(...)` phù hợp. Nếu không có provider nào hỗ trợ và không có parent manager giải quyết, có thể gặp `ProviderNotFoundException`.

Một `ProviderManager` có thể có nhiều providers. Một provider có thể trả `null` để nhường xử lý; với một số `AuthenticationException`, manager có thể xét providers khác tùy loại lỗi; lỗi trạng thái tài khoản nghiêm trọng có thể khiến quá trình dừng ngay. Không suy diễn “tất cả providers đều được gọi” hoặc “chỉ provider đầu tiên luôn được gọi”.

### 5.2. Tải UserDetails

DAO provider lấy username từ input, gọi `loadUserByUsername`, rồi có được encoded password, flags và authorities. Nó không tin password hash do client gửi. Một số cấu hình dùng `UserCache`; khi cache hiện diện, provider có thể lấy thông tin cũ rồi thử lại từ nguồn dữ liệu trong một số tình huống. Cần thiết kế cache invalidation khi đổi password, role, disabled/locked.

### 5.3. Kiểm tra trạng thái trước khi so mật khẩu

Theo cơ chế mặc định của `AbstractUserDetailsAuthenticationProvider`, các tình huống thường bị từ chối:

- `isAccountNonLocked()==false` → `LockedException`.
- `isEnabled()==false` → `DisabledException`.
- `isAccountNonExpired()==false` → `AccountExpiredException`.

Các bước account status này tách biệt với việc raw password có khớp hash hay không. Một tài khoản bị khóa không được “qua” chỉ vì mật khẩu đúng.

### 5.4. PasswordEncoder.matches kiểm chứng password

Điểm cốt lõi là:

```java
// Fragment khái niệm: provider tự gọi tương đương phép so này.
boolean correct = encoder.matches(rawPassword, storedPasswordHash);
```

`rawPassword` đến từ request; `storedPasswordHash` đến từ `UserDetails.getPassword()`. Với BCrypt, hash chứa salt/cost và `matches` hiểu cách kiểm tra. Vì vậy **không** làm:

```java
// SAI đối với hash có salt: hai lần encode không nhất thiết giống nhau.
boolean correct = encoder.encode(rawPassword)
        .equals(storedPasswordHash);
```

Cũng không lưu plaintext trong DB, không coi password hashing là encryption để giải mã lại. `PasswordEncoder.matches` có thể trả false khi sai mật khẩu, và provider sẽ ném `BadCredentialsException` theo behavior bình thường. Nếu gặp lỗi encoder id/định dạng hash khi chuyển thuật toán, đó là vấn đề cấu hình dữ liệu cần giải quyết, không phải mặc định user gõ sai mật khẩu.

**Khi chọn encoder:**

- `BCryptPasswordEncoder` nhận hash BCrypt do chính `encode` tạo, thường có tiền tố BCrypt đặc trưng như `$2a$`.
- `DelegatingPasswordEncoder` dùng format lưu thường có id ở đầu, ví dụ `{bcrypt}...`, để biết thuật toán. Hash không kèm id có thể không được decoder mặc định xử lý nếu chưa đặt phương án tương thích.
- Có thể thay đổi work factor/cost theo mục tiêu hiệu năng và bảo mật. Việc nâng cấp hash khi người dùng đăng nhập có thể dùng `PasswordEncoder.upgradeEncoding` và `UserDetailsPasswordService` khi đã cấu hình, **không tự xảy ra chỉ nhờ đổi bean**.

### 5.5. Kiểm tra credentials hết hạn

`isCredentialsNonExpired()==false` thường dẫn đến `CredentialsExpiredException`. Điều này khác với “mật khẩu đã nhập sai”; ứng dụng có thể cần flow đổi mật khẩu thay vì cấp phiên truy cập bình thường.

### 5.6. Tạo Authentication thành công

Sau khi đạt các kiểm tra, provider tạo result có `isAuthenticated()==true`, `principal` đáng tin cậy và `GrantedAuthority` từ user. Ví dụ user được cấp `ROLE_READER` sẽ có authority `ROLE_READER`; không tạo `ROLE_ADMIN` chỉ vì request muốn vào `/admin`.

`ProviderManager` mặc định cố xóa credentials trên result thông qua `CredentialsContainer.eraseCredentials()` nếu khả dụng. Thực tế không nên phụ thuộc mọi provider luôn trả `getCredentials()==null`; hãy chủ động không log secrets. Cẩn thận khi object `UserDetails` được cache/share mà có thể bị tác động bởi việc xóa credentials.

## 6. Kết quả thành công và các thất bại cần phân biệt

| Tình huống | Exception/kết quả thường gặp | Hướng xử lý |
| --- | --- | --- |
| Username/password đúng và account hợp lệ | Authenticated `Authentication` có authorities | Filter ghi context rồi authorization kiểm tra quyền |
| Mật khẩu không khớp | `BadCredentialsException` | Phản hồi login thất bại an toàn, tránh lộ chi tiết |
| Không có username | Thường `BadCredentialsException` ở bề mặt provider | Tránh username enumeration |
| Account locked | `LockedException` | Theo chính sách khóa/mở khóa |
| Account disabled | `DisabledException` | Kiểm tra trạng thái kích hoạt |
| Account expired | `AccountExpiredException` | Chính sách hết hạn tài khoản |
| Credentials expired | `CredentialsExpiredException` | Flow đổi/reset credentials |
| Không provider nào hỗ trợ token | `ProviderNotFoundException` | Xem wiring của manager/provider và kiểu token |
| Data store/service lỗi | Thường thuộc `AuthenticationServiceException` hoặc lỗi hạ tầng | Xử lý lỗi dịch vụ, không giả là mật khẩu sai |

`DaoAuthenticationProvider` **không tự trả HTTP 401, 403 hay 302**. Nó trả `Authentication` hoặc ném `AuthenticationException`. Ở Servlet filter layer, entry point và failure handler quyết định status hoặc redirect phù hợp: HTTP Basic thường 401; form login có thể redirect về trang login. Nếu xác thực thành công nhưng thiếu authority mà endpoint yêu cầu thì authorization thường trả 403.

## 7. Ví dụ chạy được: Java 17 + Spring Security 6 + Servlet HTTP Basic

Tạo ứng dụng Maven với Spring Boot 3.3.5, dependencies web/security. Ví dụ dùng in-memory accounts để thấy rõ các case thành công, sai password, user bị khóa hoặc vô hiệu hóa. Mọi mật khẩu trong code **chỉ phục vụ học tập**; không đem tài khoản demo vào hệ thống thật.

| Username | Mật khẩu demo | Trạng thái | Role |
| --- | --- | --- | --- |
| `lan` | `lan-pass` | Bình thường | `READER` |
| `quan` | `quan-pass` | Bình thường | `ADMIN` |
| `khoa` | `khoa-pass` | Locked | `READER` |
| `my` | `my-pass` | Disabled | `READER` |

Cấu trúc:

```text
dao-auth-demo/
├── pom.xml
└── src/main/java/demo/daologin/
    ├── DaoAuthApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 7.1. `pom.xml`

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
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>dao-auth-demo</artifactId>
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

### 7.2. `DaoAuthApplication.java`

```java
package demo.daologin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DaoAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(DaoAuthApplication.class, args);
    }
}
```

### 7.3. `SecurityConfig.java`

```java
package demo.daologin;

import java.util.List;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("lan-pass"))
                .roles("READER")
                .build();
        UserDetails quan = User.withUsername("quan")
                .password(encoder.encode("quan-pass"))
                .roles("ADMIN")
                .build();
        UserDetails khoa = User.withUsername("khoa")
                .password(encoder.encode("khoa-pass"))
                .roles("READER")
                .accountLocked(true)
                .build();
        UserDetails my = User.withUsername("my")
                .password(encoder.encode("my-pass"))
                .roles("READER")
                .disabled(true)
                .build();
        return new InMemoryUserDetailsManager(lan, quan, khoa, my);
    }

    @Bean
    DaoAuthenticationProvider daoProvider(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    AuthenticationManager authenticationManager(DaoAuthenticationProvider provider) {
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager) throws Exception {
        // Bắt HTTP Basic dùng đúng manager/provider được khai báo.
        http.authenticationManager(manager);
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/whoami").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    ApplicationRunner verifyDaoFlow(AuthenticationManager manager) {
        return args -> {
            Authentication input =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "lan", "lan-pass");

            System.out.println("input.authenticated=" + input.isAuthenticated());
            Authentication success = manager.authenticate(input);
            System.out.println("output.authenticated=" + success.isAuthenticated());
            System.out.println("output.name=" + success.getName());
            System.out.println("output.authorities=" + success.getAuthorities());
            System.out.println("output.credentialsErased="
                    + (success.getCredentials() == null));

            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "lan", "wrong"));
            } catch (BadCredentialsException e) {
                System.out.println("wrongPassword=" + e.getClass().getSimpleName());
            }
            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "missing", "anything"));
            } catch (BadCredentialsException e) {
                System.out.println("unknownUser=" + e.getClass().getSimpleName());
            }
            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "khoa", "khoa-pass"));
            } catch (LockedException e) {
                System.out.println("lockedUser=" + e.getClass().getSimpleName());
            }
            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "my", "my-pass"));
            } catch (DisabledException e) {
                System.out.println("disabledUser=" + e.getClass().getSimpleName());
            }
        };
    }
}
```

**Phân tích code:**

1. `InMemoryUserDetailsManager` chứa `UserDetails`; `password(encoder.encode(...))` lưu hash BCrypt, không giữ raw password trong thuộc tính password của user.
2. Bean `DaoAuthenticationProvider` biết `UserDetailsService` và `PasswordEncoder`, không cần biết hệ thống lưu trữ phía sau là gì.
3. `ProviderManager(List.of(provider))` quản lý provider để xác thực. `http.authenticationManager(manager)` nối HTTP Basic filter của chain với manager này.
4. `verifyDaoFlow` chạy khi khởi động, gọi manager trực tiếp để nhìn **đầu vào chưa xác thực và result đã xác thực**. Gọi manager trực tiếp **không tự lưu `SecurityContext` vào session**; flow HTTP do security filter xử lý.
5. `getAuthorities()` lấy role từ user store: `ROLE_READER`, không phải từ request. `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN` theo prefix mặc định.
6. Các case sai mật khẩu, unknown user, locked và disabled dùng kiểu exception cụ thể để minh họa các nhánh kiểm tra. Ngoài bài học không nên trả toàn bộ thông tin exception nội bộ cho client.
7. Ví dụ chỉ xử lý GET để không cần thay đổi chính sách CSRF. Ứng dụng thật phải xem xét CSRF theo cơ chế cookie/session, API authentication và cách client hoạt động.

### 7.4. `DemoController.java`

```java
package demo.daologin;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/whoami")
    public String whoami(Authentication authentication) {
        return "user:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
```

### 7.5. Build, chạy và quan sát stdout

Trong thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Khi khởi động thành công, ngoài các dòng log mặc định của Spring Boot, `ApplicationRunner` in theo thứ tự (kỳ vọng với cấu hình mẫu):

```text
input.authenticated=false
output.authenticated=true
output.name=lan
output.authorities=[ROLE_READER]
output.credentialsErased=true
wrongPassword=BadCredentialsException
unknownUser=BadCredentialsException
lockedUser=LockedException
disabledUser=DisabledException
```

Từ kết quả có thể thấy: password đúng dẫn đến `Authentication` có authority của user, trong khi password sai và username không có được che dưới cùng nhóm lỗi. Locked/disabled không được xem là đăng nhập thành công. Result trả bởi `ProviderManager` được xóa credentials khi token hỗ trợ cơ chế đó.

### 7.6. Kiểm tra luồng Servlet qua HTTP Basic

Các lệnh `curl` sau dành cho shell POSIX. Chú thích phía dưới là **HTTP status/body dự kiến** với ứng dụng mẫu tại `localhost:8080`.

```bash
# Chưa xác thực:
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/whoami
# 401

# Sai mật khẩu:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u lan:wrong http://localhost:8080/whoami
# 401

# Username/password đúng:
curl -s -u lan:lan-pass http://localhost:8080/whoami
# user:lan

# Đã xác thực nhưng không có ROLE_ADMIN:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u lan:lan-pass http://localhost:8080/admin
# 403

# Có ROLE_ADMIN:
curl -s -u quan:quan-pass http://localhost:8080/admin
# admin:quan

# Account bị khóa:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u khoa:khoa-pass http://localhost:8080/whoami
# 401

# Account disabled:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u my:my-pass http://localhost:8080/whoami
# 401
```

Tất cả password trên chỉ để học local. HTTP Basic chuyển credential trong header, chỉ dùng với **HTTPS** trên hệ thống thật. Không đưa password thật vào lịch sử shell/log.

**Vì sao `lan` nhận 403 ở `/admin` dù đúng password?** `DaoAuthenticationProvider` đã làm đúng việc xác thực `lan`, nhưng policy `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN`; `lan` chỉ có `ROLE_READER`. Lỗi 403 thuộc tầng **authorization**, không phải dấu hiệu provider so mật khẩu sai.

## 8. Khi dùng database thật

Thay `InMemoryUserDetailsManager` bằng một implementation của `UserDetailsService`. Provider vẫn làm việc với interface:

```text
POST login hoặc Basic header
        |
        v
DaoAuthenticationProvider
        |
        v
UserDetailsService.loadUserByUsername
        |
        v
UserRepository / JDBC / external user store
        |
        v
UserDetails: password hash + flags + authorities
        |
        v
PasswordEncoder.matches(raw, encoded)
        |
        v
Authentication thành công hoặc exception
```

Ví dụ mapping từ JPA (fragment **không chạy độc lập** vì project cần khai báo `UserRepository`, `UserEntity` và hàm ánh xạ authorities):

```java
@Override
public UserDetails loadUserByUsername(String username) {
    UserEntity entity = repository.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException("User not found"));

    return User.withUsername(entity.getUsername())
            .password(entity.getPasswordHash())
            .disabled(!entity.isEnabled())
            .accountLocked(entity.isLocked())
            .authorities(mapTrustedAuthorities(entity))
            .build();
}
```

Chú ý khi tích hợp:

- `getPasswordHash()` phải trả **hash encoded nguyên vẹn** tương thích với `PasswordEncoder`; không gọi `encode` mỗi lần tải user để làm “mới” password hash.
- Dùng unique constraint, chuẩn hóa username/email nhất quán và xem xét Unicode/case-sensitivity.
- Role/permission phải đến từ nguồn tin cậy; ánh xạ `ROLE_...` và các authority nghiệp vụ phù hợp policy.
- Account flags được ánh xạ chính xác; dữ liệu locked/disabled phải phản ánh sang `UserDetails`.
- Nếu có cache, cần invalidation khi thay password/role/flags. Đặc biệt tránh object cache bị tác động ngoài ý muốn bởi `eraseCredentials`.
- Không hạ chính sách mật khẩu trong quá trình chuyển từ BCrypt sang Delegating encoder. Có thể sử dụng chiến lược `upgradeEncoding` + `UserDetailsPasswordService` nếu thực sự thiết kế cơ chế lưu hash mới.
- Tăng cường rate limiting, chống credential stuffing, audit log an toàn, HTTPS, bảo vệ session/cookie và CSRF theo thiết kế ứng dụng. DAO provider không tự cung cấp toàn bộ các lớp bảo vệ này.

## 9. Những nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Sai mật khẩu mà login vẫn thành công | Code tự dựng authenticated token từ input, bỏ qua provider | Bảo đảm filter gọi `AuthenticationManager`, quyền chỉ cấp sau khi kiểm chứng |
| `ProviderNotFoundException` | Manager không có provider hỗ trợ token | Kiểm tra `ProviderManager` và `supports` |
| Mọi user đều 401 sau khi thay encoder | Password hash trong store không tương thích decoder | Kiểm tra BCrypt/Delegating, prefix `{bcrypt}`, lưu trữ và migration |
| Unknown user có `BadCredentialsException` | Cơ chế che chi tiết username tồn tại | Đây thường là thiết kế bảo vệ chống dò tài khoản |
| User bị khóa vẫn có thể login | `UserDetails.isAccountNonLocked()` mapping sai hoặc filter dùng provider khác | Đối chiếu flags và manager wiring |
| Đăng nhập đúng nhưng `/admin` báo 403 | Không đủ `ROLE_ADMIN` hoặc CSRF/policy khác | Kiểm tra authorities và authorization rules |
| Không thấy password trong result | `ProviderManager` đã erase credentials | Không phụ thuộc vào credentials ở authenticated result |
| User đã đổi role nhưng request vẫn quyền cũ | Session `SecurityContext` hoặc user cache còn dữ liệu cũ | Thiết kế refresh/re-auth/invalidation phù hợp |
| DB down và HTTP response như mật khẩu sai | Layer xử lý lỗi dịch vụ chưa phân biệt | Xử lý `AuthenticationServiceException`/hạ tầng an toàn |
| Basic credentials lộ trong logs | Log raw header hoặc `Authentication` trước khi xóa secret | Redact credentials và phân quyền người xem logs |

Quy trình debug tốt là: **filter có lấy đúng username/password → `ProviderManager` chọn đúng provider → `UserDetailsService` tải đúng user → flags hợp lệ → `PasswordEncoder.matches` đúng → output có authorities → HTTP authorization quyết định**.

Đừng thêm `permitAll()` hoặc tắt CSRF để chữa lỗi mật khẩu; đó là các tầng khác nhau.

## 10. So sánh với JWT, form login và các cơ chế khác

- **Form login** dùng `UsernamePasswordAuthenticationFilter`; username/password thường được DAO provider xác minh, sau đó filter sử dụng session/context và success/failure handlers.
- **HTTP Basic** dùng `BasicAuthenticationFilter`; credentials vẫn có thể được `DaoAuthenticationProvider` kiểm tra, nhưng client gửi header vào mỗi request.
- **JWT Resource Server** dùng cơ chế xác thực JWT riêng (decoder, validators, provider phù hợp), không đưa JWT string cho DAO provider và mong nó tự xác minh chữ ký/issuer/audience.
- **OAuth2/OIDC login, WebAuthn, OTP hoặc API key** cũng cần authentication components phù hợp. Có thể kết hợp với hệ thống username/password, nhưng DAO provider không tự xử lý mọi bằng chứng.

**DaoAuthenticationProvider không thay thế SecurityFilterChain.** Security chain chọn filter, authentication entry point, session và authorization rules. Provider chỉ là khâu kiểm chứng username/password bên trong luồng đó.

## 11. Câu hỏi tự ôn

1. **UserDetailsService có so mật khẩu không?** Không. Nó tải user; provider dùng `PasswordEncoder.matches`.
2. **DaoAuthenticationProvider có biết table users không?** Không. Nó phụ thuộc `UserDetailsService`.
3. **Vì sao phải dùng `matches(raw, encoded)` thay cho `encode(raw).equals(encoded)`?** Thuật toán như BCrypt dùng salt; mỗi lần encode có thể tạo hash khác.
4. **Tài khoản locked nhưng password đúng được login không?** Không, bị từ chối theo account status.
5. **Unknown user có thể thành BadCredentialsException không?** Có, cơ chế che chi tiết là hành vi thường gặp mặc định.
6. **Dao provider tự đặt SecurityContext và HTTP session?** Không. Security filter và context repository xử lý phần đó.
7. **Result authentication có role ADMIN vì user gửi role ADMIN lên API không?** Không. Authorities phải được lấy từ nguồn tin cậy sau khi kiểm chứng.
8. **Vì sao password đúng nhưng HTTP 403?** Authentication thành công nhưng authorization thiếu role/permission hoặc chính sách request khác từ chối.
9. **Nếu thay in-memory bằng JPA phải viết lại provider?** Thường chỉ thay `UserDetailsService` và cấu hình data/encoder, không cần sửa logic DAO provider.
10. **Password hash có luôn nâng cấp tự động sau khi thay encoder?** Không, cần cơ chế tương ứng như `UserDetailsPasswordService` và điều kiện nâng cấp.

## 12. Checklist triển khai

- [ ] Nhận username/password như một `Authentication` **chưa xác thực**; không tin role do client cung cấp.
- [ ] Dùng `UserDetailsService` trả hash/flags/authorities chính xác từ server-side store.
- [ ] `PasswordEncoder` khớp format hash, dùng `matches` để kiểm tra, không lưu raw password.
- [ ] Kiểm tra locked/disabled/expired/credential-expired, không cấp quyền khi không đạt.
- [ ] Xử lý `AuthenticationException` ở filter/entry point phù hợp, không tiết lộ username enumeration.
- [ ] Không log mật khẩu, Basic header, bearer token hoặc encoded password một cách tùy tiện.
- [ ] Test đúng password, sai password, unknown user, locked/disabled và user xác thực nhưng thiếu quyền.
- [ ] Bảo đảm HTTP filter gọi đúng manager/provider; không nhầm authentication với authorization.
- [ ] Dùng HTTPS, chống brute force, audit có kiểm soát và chính sách session/CSRF phù hợp.
- [ ] Quản lý migration password hash, account status, user cache và quyền theo vòng đời tài khoản.

**Tóm tắt cơ chế:** `DaoAuthenticationProvider` thực hiện **tìm UserDetails → kiểm tra account status → `PasswordEncoder.matches` → kiểm tra credential expiry → trả Authentication đáng tin cậy hoặc ném AuthenticationException**. `ProviderManager` điều phối provider; các Servlet security filters kết nối quá trình này với HTTP request, `SecurityContext` và phần kiểm soát truy cập.