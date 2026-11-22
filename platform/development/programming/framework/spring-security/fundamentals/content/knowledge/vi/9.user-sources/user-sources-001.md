# UserDetailsService tải dữ liệu người dùng và không tự kiểm tra mật khẩu

Trong Spring Security, `UserDetailsService`, `DaoAuthenticationProvider` và `PasswordEncoder` thường được dùng cùng nhau để đăng nhập bằng username/password. Chúng phối hợp nhưng **không làm cùng một nhiệm vụ**:

- **`UserDetailsService`**: nhận **username**, tìm và tải dữ liệu tài khoản, trả về `UserDetails` chứa username, password hash, authorities và trạng thái tài khoản.
- **`DaoAuthenticationProvider`**: nhận một yêu cầu xác thực chưa đáng tin, dùng `UserDetailsService` để lấy user, kiểm tra password qua `PasswordEncoder` cùng các điều kiện trạng thái, rồi trả một `Authentication` đã xác minh hoặc ném exception.
- **`PasswordEncoder`**: có `encode` để tạo hash khi đặt/đổi password và `matches(rawPassword, storedHash)` để so khớp khi xác thực.

**Tìm thấy user không có nghĩa đã đăng nhập thành công.** Một người có thể biết username `alice` và khiến ứng dụng tìm ra account Alice, nhưng không vì thế mà có quyền truy cập dữ liệu của Alice. Chỉ provider kiểm tra credentials và các điều kiện tài khoản mới được xác lập authentication đáng tin cậy.

Bài lấy **Spring Boot 3, Spring Security 6.5, Java 17+ và Spring MVC/Servlet** làm ví dụ. Một chương trình Java 17 độc lập ở cuối giúp bạn tự quan sát sự khác nhau giữa lookup và password check. Những đoạn Spring Boot yêu cầu Gradle/Maven setup thích hợp; không được biên dịch riêng bằng `javac` nếu thiếu thư viện. Với Spring Security 7 hoặc WebFlux, hãy chọn reference/Javadoc tương ứng với phiên bản và stack đang dùng.

## 1. Bảng ranh giới trách nhiệm

| Thành phần | Nhận gì? | Làm gì? | Trả gì? | Không tự làm |
| --- | --- | --- | --- | --- |
| `UserDetailsService` | `String username` | Tra nguồn user theo tên | `UserDetails` hoặc `UsernameNotFoundException` | Không kiểm tra raw password, không tạo phiên login |
| `UserDetails` | Được load từ nguồn user | Mang hash, authorities, flags và username | Dữ liệu qua getters | Không tự quyết định password có đúng |
| `PasswordEncoder` | Raw password, encoded password | Hash và so khớp | `String` hash hoặc `boolean` từ `matches` | Không tra user hay quyết định quyền trên URL |
| `DaoAuthenticationProvider` | `Authentication` username/password | Lookup + account checks + password matches | `Authentication` đáng tin hoặc exception | Không tự phân quyền trên owner/tenant |
| `AuthenticationManager` / `ProviderManager` | `Authentication` chưa xác thực | Điều phối provider thích hợp | `Authentication` kết quả hoặc exception | Không tự xuất HTTP response |
| `SecurityFilterChain` | HTTP request | Tích hợp filter, authentication, authorization, exploit protection | Cho tiếp tục hoặc chặn request | Không biết tự động mọi chính sách nghiệp vụ |

Hãy tách hai mệnh đề:

1. “Tìm thấy account Alice và lấy được hash đang lưu” → việc **đọc dữ liệu** thành công.
2. “Password do client cung cấp khớp hash, tài khoản hợp lệ, provider chấp nhận” → việc **xác thực** thành công.

`UserDetailsService` chịu trách nhiệm cho mệnh đề thứ nhất. `DaoAuthenticationProvider` và các thành phần authentication chịu trách nhiệm mệnh đề thứ hai.

## 2. Contract chính xác của UserDetailsService

Interface thuộc package `org.springframework.security.core.userdetails` và có đúng một phương thức cốt lõi:

```java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
```

Đây là dạng rút gọn từ API để học.

Bạn có thể thấy ngay:

- Tham số chỉ là **username**. Không có `password`, `HttpServletRequest`, `Jwt` hoặc danh sách role do client khai.
- Kết quả là một `UserDetails` được điền đủ dữ liệu cần thiết cho provider; không có một boolean “password đúng/sai” nào trong kết quả.
- Nếu không tìm thấy user, contract sử dụng `UsernameNotFoundException`. Không nên trả `null` để báo người dùng không tồn tại.
- Interface bản thân chỉ **đọc** user. Muốn create/update/delete user có thể cần `UserDetailsManager` hoặc một service nghiệp vụ khác; đổi password/hash có cơ chế riêng.

Đoạn code này là lookup, chưa phải login:

```java
UserDetails user =
    userDetailsService.loadUserByUsername("alice");

String username = user.getUsername();
String storedHash = user.getPassword();
var authorities = user.getAuthorities();
```

Đoạn này là fragment yêu cầu Spring Security imports và một bean `userDetailsService`. `storedHash` là password đã được encode khi tạo/đổi mật khẩu, **không phải raw password client vừa nhập**. Không in password hash vào log hoặc trả qua API.

### 2.1. Vì sao không có tham số password?

`DaoAuthenticationProvider` có quyền truy cập raw credentials từ `UsernamePasswordAuthenticationToken` do authentication filter tạo. Nó chỉ cần service tìm bản ghi tài khoản, còn việc so khớp password là nhiệm vụ của provider/`PasswordEncoder`. Nhờ ranh giới này:

- Một nguồn user có thể được lấy từ memory, JDBC hay custom repository;
- Quy tắc password hashing/migration được quản lý ở nơi chuyên trách;
- Có thể unit test lookup mà không phải mô phỏng HTTP login;
- Việc đổi nguồn dữ liệu không bắt buộc viết lại toàn bộ password authentication;
- Provider còn có thể kiểm tra trạng thái account, credentials expiry và những ràng buộc khác.

Nếu hệ thống dùng OTP, certificate, LDAP bind hoặc cơ chế không dựa vào hash password chuẩn, bạn có thể cần `AuthenticationProvider`/flow đặc thù. Không tự thêm một phương thức `loadUserByUsername(username, password)` rồi giả định provider mặc định sẽ gọi nó.

### 2.2. Username có thể khác chữ hoa/chữ thường

Javadoc của `UserDetailsService` cho phép implementation tìm username có phân biệt hoặc không phân biệt hoa/thường. Ví dụ lookup `ALICE` có thể trả một `UserDetails` với username chuẩn hóa `alice` nếu nguồn dữ liệu được thiết kế như vậy. Chọn quy ước chuẩn hóa/unique index nhất quán khi đăng ký, đăng nhập và đổi email.

Nếu username chỉ unique **trong một tenant**, bạn phải thiết kế cách xác định tenant trong trust boundary phù hợp. Không tự coi `X-Tenant-Id` hoặc form field do client gửi là bằng chứng quyền truy cập vào tenant đó.

## 3. UserDetails chứa những dữ liệu nào?

`UserDetails` thường có các API sau:

| Phương thức | Dữ liệu | Ai sử dụng? |
| --- | --- | --- |
| `getUsername()` | Username đã load | Provider và code danh tính |
| `getPassword()` | Encoded password / hash | Provider + PasswordEncoder |
| `getAuthorities()` | Role và permission | Authentication kết quả, authorization |
| `isEnabled()` | Có được phép hoạt động? | Provider |
| `isAccountNonLocked()` | Account không bị khóa? | Provider |
| `isAccountNonExpired()` | Account còn hiệu lực? | Provider |
| `isCredentialsNonExpired()` | Credentials còn hiệu lực? | Provider |

Đọc `UserDetails` không đồng nghĩa đặt toàn bộ data này lên response JSON; password hash, account flags và các quyền nội bộ có thể là thông tin nhạy cảm.

### 3.1. Authorities không đến từ request body

Với username/password, role/permission nên đến từ user store hoặc nguồn đáng tin cậy do server kiểm soát:

```text
Account Alice:
    username = alice
    passwordHash = BCrypt(...)
    authorities = [ROLE_USER, report:read]
    enabled = true
```

Sau khi xác thực hợp lệ, các authorities mới có ý nghĩa làm dữ liệu cho các rule như `hasRole("ADMIN")` hoặc `hasAuthority("report:read")`. Không được tự tin mảng `roles: ["ROLE_ADMIN"]` do client gửi rồi tạo một `Authentication` đã được đánh dấu authenticated.

### 3.2. UserDetails không nhất thiết là entity JPA

Một JPA entity có thể chứa quan hệ lazy, dữ liệu nghiệp vụ, trường nhạy cảm và khả năng bị mutate. Thường nên ánh xạ `Account`/`Role` → `UserDetails` hoặc một principal DTO chuyên dụng, thay vì trả entity trực tiếp:

- Tránh `LazyInitializationException` khi provider đọc quyền sau transaction;
- Tránh kéo theo danh sách quan hệ không cần thiết;
- Tránh serialize password/hash/địa chỉ hay dữ liệu cá nhân nhầm;
- Tránh chia sẻ reference có thể bị xóa credentials;
- Giữ ranh giới giữa identity dùng để login và domain object dùng cho nghiệp vụ.

## 4. Luồng xác thực từ filter đến controller

```text
Client: username + raw password
             |
             v
SecurityFilterChain
   |
   +-- BasicAuthenticationFilter / form login filter
   |       |
   |       +-- UsernamePasswordAuthenticationToken
   |             principal = username khai báo
   |             credentials = raw password
   |             authenticated = false
   |
   v
AuthenticationManager / ProviderManager
   |
   v
DaoAuthenticationProvider
   |
   +-- UserDetailsService.loadUserByUsername(username)
   |       +-- Tìm user từ DB / memory
   |       +-- Trả UserDetails với storedHash, authorities, flags
   |
   +-- Kiểm tra account flags
   |
   +-- PasswordEncoder.matches(rawPassword, storedHash)
   |       +-- false -> AuthenticationException
   |       +-- true  -> tiếp tục
   |
   +-- Authentication đã xác thực
                |
                v
         SecurityContext
                |
                v
    authorizeHttpRequests / AuthorizationManager
                |
                v
        Controller / Service
```

Đây là **mô hình logic**. Thứ tự kiểm tra trạng thái, credential, filter và cache có thể khác theo cấu hình; session hợp lệ có thể được khôi phục mà không thực hiện username/password login mới ở mọi request.

### 4.1. Provider là nơi kiểm tra password

Provider có thể làm tương đương:

```java
UserDetails user = service.loadUserByUsername(username);

boolean valid =
    passwordEncoder.matches(rawPassword, user.getPassword());
```

Đây là fragment **minh họa**, chưa phản ánh mọi kiểm tra account state, exception, timing hoặc cache trong provider thật. `loadUserByUsername` chỉ cung cấp user/hash; provider mới đánh giá bằng chứng. Đừng viết:

```java
// Sai khi password hashing sử dụng salt:
passwordEncoder.encode(rawPassword).equals(user.getPassword());
```

Với BCrypt, hai lần `encode` cùng raw password thường có salt khác nhau và trả hash khác nhau. Phải dùng `matches`.

### 4.2. Password đúng vẫn chưa chắc được login

Một `UserDetails` có `enabled=false` hoặc `accountNonLocked=false` vẫn có thể được service load thành công, nhưng provider phải từ chối đăng nhập theo trạng thái tài khoản. Authentication còn có thể phụ thuộc các biện pháp khác như MFA hoặc đánh giá rủi ro, tùy flow.

### 4.3. Authentication kết quả có thể khác đầu vào

`UsernamePasswordAuthenticationToken.unauthenticated("alice",raw)` không đáng tin, dù `getName()` đã trả `alice`. Sau xác thực, provider có thể trả một `Authentication` mới với principal là `UserDetails` và authorities đáng tin. Filter sử dụng kết quả để thiết lập `SecurityContext`.

`UserDetailsService` không tự tạo session cookie, không tự lưu `SecurityContext` và không tự phát hành JWT. Một lời gọi `loadUserByUsername` trực tiếp ở service **không đăng nhập user**.

### 4.4. 401 khác 403

- HTTP Basic chưa có hoặc sai credentials → thường **401 Unauthorized**, có thể kèm `WWW-Authenticate`.
- Đăng nhập đúng nhưng thiếu `ROLE_ADMIN` → thường **403 Forbidden** do authorization.
- POST thiếu CSRF token có thể **403** dù user đã login và có quyền; không đồng nghĩa sai password.
- Form login có thể redirect tới `/login` hoặc `/login?error` tùy cấu hình, không nhất thiết trả 401 JSON.

Đừng suy luận một lỗi 403 là do `UserDetailsService` không tìm được user. Hãy xác định request đi qua filter, provider và authorization rule nào.

## 5. Các nguồn dữ liệu user phổ biến

| Lựa chọn | Nguồn | Khi nào dùng? |
| --- | --- | --- |
| `InMemoryUserDetailsManager` | Dữ liệu trong bộ nhớ | Demo, test, ứng dụng có user cố định |
| `JdbcUserDetailsManager` | Database qua JDBC schema/query | User store JDBC và tác vụ quản lý user |
| `JdbcDaoImpl` | Đọc user/authority qua JDBC | Một implementation UserDetailsService dạng JDBC |
| `CachingUserDetailsService` | Bọc nguồn user với cache | Giảm lookup DB, cần TTL/invalidation |
| Custom `UserDetailsService` | Repository JPA, DB, directory hoặc adapter riêng | Dữ liệu account/role theo domain cụ thể |
| LDAP integration | Directory LDAP | Có thể dùng provider/LDAP strategy riêng, không mặc định là DAO password-hash flow |

`UserDetailsManager` mở rộng `UserDetailsService` với chức năng quản lý user. Interface `UserDetailsService` chỉ có thao tác lookup; nó **không định nghĩa** đăng ký, đổi mật khẩu, thu hồi role hoặc khóa user.

### 5.1. In-memory đơn giản

```java
UserDetails alice = User.withUsername("alice")
    .password(encoder.encode("demo-alice-pass"))
    .authorities("ROLE_USER", "report:read")
    .build();

UserDetailsService source =
    new InMemoryUserDetailsManager(alice);
```

Ở đây `encoder` cần được tạo/inject phù hợp. `source.loadUserByUsername("alice")` đọc object có hash; password đúng hay sai vẫn là việc provider kiểm tra khi có request xác thực.

### 5.2. Khi nào tự implement?

Khi user, hash, role, permission hoặc status nằm trong schema ứng dụng riêng; khi cần ánh xạ account sang `UserDetails`; hoặc khi có policy tenant/username mapping cần kiểm soát. Đừng tự implement chỉ để thay tên class nếu implementation có sẵn đã phù hợp.

## 6. Ví dụ Spring Boot 3 hoàn chỉnh: UserDetailsService chỉ làm lookup

Bộ ví dụ sử dụng **Spring MVC, HTTP Basic, BCrypt và ba user demo**. Chúng ta viết một custom service dùng `Map` như nguồn data để mọi thứ có thể chạy cục bộ. Service lưu **hash** trong bản ghi riêng và **tạo UserDetails mới mỗi lần tra cứu** để không chia sẻ object có thể bị erasure với bản ghi gốc.

Các tệp:

```text
src/main/java/example/userlookup/
  UserLookupApplication.java
  DemoUserDetailsService.java
  SecurityConfig.java
  DemoController.java

src/test/java/example/userlookup/
  UserLookupSecurityTest.java
```

### 6.1. Dependencies

Trong `build.gradle` Groovy DSL của một project Spring Boot 3 đã thiết lập plugin/repository:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây chỉ là đoạn `dependencies`, không phải Gradle build file đầy đủ. Với Maven, dùng các starter tương đương và `spring-security-test` ở `test` scope. Để Boot BOM chọn các phiên bản Spring Security tương thích; không thêm version độc lập cho từng module mà chưa xem dependency graph.

### 6.2. File UserLookupApplication.java

```java
package example.userlookup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UserLookupApplication {
    public static void main(String[] args) {
        SpringApplication.run(UserLookupApplication.class, args);
    }
}
```

### 6.3. File DemoUserDetailsService.java

```java
package example.userlookup;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class DemoUserDetailsService implements UserDetailsService {

    private record AccountRow(
        String passwordHash,
        List<String> authorities,
        boolean enabled
    ) {}

    private final Map<String, AccountRow> accounts;

    public DemoUserDetailsService(PasswordEncoder encoder) {
        this.accounts = Map.of(
            "alice",
            new AccountRow(
                encoder.encode("demo-alice-pass"),
                List.of("ROLE_USER", "report:read"),
                true
            ),
            "admin",
            new AccountRow(
                encoder.encode("demo-admin-pass"),
                List.of("ROLE_USER", "ROLE_ADMIN"),
                true
            ),
            "disabled",
            new AccountRow(
                encoder.encode("demo-disabled-pass"),
                List.of("ROLE_USER"),
                false
            )
        );
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AccountRow row = accounts.get(username);

        if (row == null) {
            throw new UsernameNotFoundException("User not found");
        }

        return User.withUsername(username)
            .password(row.passwordHash())
            .authorities(row.authorities().toArray(String[]::new))
            .disabled(!row.enabled())
            .build();
    }
}
```

Hãy đọc từng trách nhiệm:

1. Class `implements UserDetailsService` và chỉ override `loadUserByUsername(String)`.
2. `AccountRow.passwordHash` chứa password hash, không phải password plaintext.
3. Constructor gọi `encoder.encode(...)` **chỉ để tạo user data demo lúc ứng dụng khởi động**. Database production thường lưu hash đã được sinh ở lúc đăng ký/đổi mật khẩu.
4. `accounts.get(username)` là lookup tương tự repository; không có raw password.
5. Không tìm thấy account → ném `UsernameNotFoundException`, không trả null hoặc tạo user giả.
6. Có account → tạo một `UserDetails` mới với hash, authorities và trạng thái disabled.
7. Không có lời gọi `PasswordEncoder.matches` trong method này: việc xác thực password vẫn nằm ở provider.
8. Không lấy authorities từ header/JSON mà client tự khai.
9. Service không tự thay `SecurityContext` hoặc cấp cookie đăng nhập.

### 6.4. File SecurityConfig.java

```java
package example.userlookup;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DemoUserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new DemoUserDetailsService(encoder);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Tại đây:

- `DemoUserDetailsService` là **Spring bean** có type implement `UserDetailsService`.
- Trong cấu hình username/password mặc định phù hợp, khi không có AuthenticationManager/AuthenticationProvider custom thay thế, Spring Security có thể xây `DaoAuthenticationProvider` dựa trên bean `UserDetailsService` và `PasswordEncoder`.
- `.httpBasic(...)` giúp filter nhận Basic credentials từ HTTP request và gửi tới authentication flow.
- `.authorizeHttpRequests(...)` là **phân quyền**, không phải password checking.
- `hasRole("ADMIN")` mặc định yêu cầu `ROLE_ADMIN`; `hasAuthority("report:read")` so khớp chuỗi `report:read`.
- `anyRequest().denyAll()` từ chối những URL/method chưa có rule, tránh mở nhầm endpoint.
- CSRF của Spring Security Servlet không được tắt bằng cấu hình này; ví dụ dùng GET để quan sát độc lập luồng authentication.

Chỉ có một UserDetailsService bean là điều thuận tiện cho demo. Nếu ứng dụng đã có nhiều provider/manager hoặc nhiều chain, phải kiểm tra instance nào được filter sử dụng. Đừng suy ra chỉ tạo một class có tên `UserDetailsService` là framework tự chọn nó nếu bạn quên đăng ký bean hoặc có cấu hình custom ghi đè.

### 6.5. File DemoController.java

```java
package example.userlookup;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    Map<String, String> publicPage() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .filter(Objects::nonNull)
            .sorted()
            .toList();

        return Map.of(
            "username", authentication.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/api/reports")
    Map<String, String> reports() {
        return Map.of("message", "report available");
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin only");
    }
}
```

Controller nhận `Authentication` đã có trong security context. Nó không tự gọi `loadUserByUsername` hoặc `PasswordEncoder.matches`. API trả DTO gồm những trường được chọn; không trả `Authentication` nguyên vẹn hoặc password hash.

### 6.6. Chạy ứng dụng

Trong dự án có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Với cấu hình mặc định, server ở `http://localhost:8080`. Ba account demo:

| Username | Password dành cho localhost | Authorities | Trạng thái |
| --- | --- | --- | --- |
| `alice` | `demo-alice-pass` | `ROLE_USER`, `report:read` | enabled |
| `admin` | `demo-admin-pass` | `ROLE_USER`, `ROLE_ADMIN` | enabled |
| `disabled` | `demo-disabled-pass` | `ROLE_USER` | disabled |

Các mật khẩu trên là dữ liệu demo cục bộ, tuyệt đối không hardcode credentials production. HTTP Basic dùng Base64 để **encode**, không cung cấp mã hóa bảo mật; production cần HTTPS và quản lý secret phù hợp.

### 6.7. Quan sát bằng curl

```bash
# Public: 200 dù chưa login
curl -i http://localhost:8080/public

# Private: 401 vì thiếu credentials
curl -i http://localhost:8080/api/me

# Alice + password đúng: 200
curl -i -u alice:demo-alice-pass http://localhost:8080/api/me

# Vẫn tìm được Alice, nhưng password sai: 401
curl -i -u alice:wrong-pass http://localhost:8080/api/me

# User không tồn tại: 401
curl -i -u nobody:anything http://localhost:8080/api/me

# Password đúng nhưng account disabled: 401
curl -i -u disabled:demo-disabled-pass http://localhost:8080/api/me

# Alice có report:read: 200
curl -i -u alice:demo-alice-pass http://localhost:8080/api/reports

# Alice thiếu ROLE_ADMIN: 403
curl -i -u alice:demo-alice-pass http://localhost:8080/api/admin

# Admin có ROLE_ADMIN: 200
curl -i -u admin:demo-admin-pass http://localhost:8080/api/admin
```

Kết quả JSON minh họa khi Alice đăng nhập đúng:

```json
{
  "username": "alice",
  "authorities": ["ROLE_USER", "report:read"]
}
```

`authorities` được sort nên thứ tự trong mảng ổn định; thứ tự các **field JSON** không bắt buộc cố định. Không có raw password/hash trong response.

Kết luận từ các request:

| Trường hợp | Lookup Alice | Password / status | Kết quả HTTP mẫu |
| --- | --- | --- | --- |
| Username Alice + đúng password | Thành công | `matches` đúng, enabled | 200 |
| Username Alice + sai password | **Vẫn thành công** | `matches` sai | 401 |
| Username không tồn tại | Ném UsernameNotFoundException | Không xác thực | 401 |
| Account disabled + đúng password | Thành công | Disabled → từ chối | 401 |
| Alice vào admin | Thành công và password đúng | Thiếu role ở authorization | 403 |
| Admin vào admin | Thành công và password đúng | Có role | 200 |

Không nên suy diễn từ HTTP status duy nhất mà không xem filter/handler. Ví dụ POST thiếu CSRF có thể 403 trước khi controller chạy, dù user có đúng password.

## 7. Kiểm thử ranh giới bằng JUnit và MockMvc

Để khẳng định `UserDetailsService` chỉ làm lookup, ta kiểm thử **tầng service**, **PasswordEncoder** và **HTTP filter/provider** một cách riêng biệt. Bộ test dưới đây dùng đúng các file đã khai báo.

Tạo `src/test/java/example/userlookup/UserLookupSecurityTest.java`:

```java
package example.userlookup;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UserLookupSecurityTest {

    @Autowired
    DemoUserDetailsService source;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    MockMvc mvc;

    @Test
    void lookupReturnsDataWithoutPasswordArgument() {
        UserDetails alice = source.loadUserByUsername("alice");

        assertThat(alice.getUsername()).isEqualTo("alice");
        assertThat(alice.getPassword()).isNotEqualTo("demo-alice-pass");
        assertThat(alice.getAuthorities())
            .extracting(a -> a.getAuthority())
            .contains("ROLE_USER", "report:read");
        assertThat(alice.isEnabled()).isTrue();
    }

    @Test
    void missingUsernameThrowsException() {
        assertThatThrownBy(() -> source.loadUserByUsername("nobody"))
            .isInstanceOf(UsernameNotFoundException.class);
    }

    @Test
    void encoderChecksPasswordSeparately() {
        UserDetails alice = source.loadUserByUsername("alice");

        assertThat(encoder.matches(
            "demo-alice-pass", alice.getPassword())).isTrue();
        assertThat(encoder.matches(
            "wrong-pass", alice.getPassword())).isFalse();
    }

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRequiresLogin() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctBasicPasswordAuthenticatesAlice() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"))
            .andExpect(jsonPath("$.authorities[1]").value("report:read"));
    }

    @Test
    void wrongBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void disabledAccountIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("disabled", "demo-disabled-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void reportPermissionIsCheckedAfterLogin() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/reports")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleIsCheckedAfterLogin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isOk());
    }
}
```

Chạy:

```bash
./gradlew test --tests example.userlookup.UserLookupSecurityTest
```

Trong Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.userlookup.UserLookupSecurityTest
```

**Kỳ vọng:** cả **10 phương thức test** pass khi dùng project Boot 3 / Security 6.5 tương thích và các file đúng như trên. Đây là **kết quả dự kiến từ code**, không phải log xác nhận đã chạy Gradle trong bài học này.

| Nhóm test | Điều được xác minh |
| --- | --- |
| Direct lookup | UserDetailsService chỉ nhận username; trả hash, authorities và account flags |
| Username không có | Ném UsernameNotFoundException |
| PasswordEncoder riêng | Raw đúng/sai cho hai kết quả khác nhau dù lookup giống nhau |
| HTTP Basic đúng | Filter/provider xác minh credentials, trả identity |
| HTTP Basic sai | Không đăng nhập thành công dù user tồn tại |
| Account disabled | Provider từ chối dù hash có thể khớp |
| Report/admin | Authentication đúng vẫn cần đúng authority ở authorization |

`@WithMockUser` hoặc `with(user("alice"))` tạo identity **giả lập** để test authorization, **không kiểm tra password** trong `DaoAuthenticationProvider`. Khi muốn kiểm thử login bằng username/password thật, `httpBasic(...)` hoặc một integration test form login là lựa chọn phù hợp.

Nếu sau này thêm POST trong ứng dụng bật CSRF, dùng `with(csrf())` ở những test cần vượt lớp CSRF để kiểm tra authorization tiếp theo. Không tắt CSRF chỉ để biến một 403 thành 200.

## 8. Tích hợp với JPA/Database

Trong ứng dụng thật, service thường dùng repository để lấy bản ghi từ DB. Điều cần giữ nguyên: **query theo username**, đọc hash đã lưu và quyền, rồi trả `UserDetails`. Không nhúng raw password client vào query hoặc cố viết login bằng cách so password plaintext trong SQL.

Ví dụ một fragment kiến trúc:

```java
@Service
public class DatabaseUserDetailsService
        implements UserDetailsService {

    private final AccountRepository accounts;

    public DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) {
        Account account = accounts.findByLogin(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("User not found"));

        String[] authorities = account.getPermissions()
            .stream()
            .map(Permission::getCode)
            .distinct()
            .toArray(String[]::new);

        return User.withUsername(account.getLogin())
            .password(account.getPasswordHash())
            .authorities(authorities)
            .disabled(!account.isEnabled())
            .accountLocked(account.isLocked())
            .build();
    }
}
```

**Đây là fragment**, không phải tệp Java độc lập: nó cần entity `Account`, `Permission`, `AccountRepository`, JPA dependencies, datasource và imports. Không copy nguyên vào demo in-memory rồi yêu cầu `javac` không có Spring/JPA dependencies.

### 8.1. Repository cần đảm bảo gì?

- Có unique index cho username/email theo phạm vi tenant và quy ước normalization.
- Lấy hash đang lưu, **không lưu raw password**.
- Nạp quyền và flags cần thiết trong phạm vi transaction; tránh lazy-loading lỗi hoặc N+1 query không cần thiết.
- Dùng query tham số hóa, tránh SQL injection.
- Quyền phải từ nguồn đáng tin cậy, không phải field user tự chỉnh.
- Khi account bị khóa/disable hoặc quyền bị thu hồi, có chiến lược cache invalidation.
- Không trả entity đầy đủ qua controller hoặc log password hash.

Một schema minh họa:

```text
accounts(id, normalized_username, password_hash, enabled, locked, tenant_id)
roles(id, role_code)
account_roles(account_id, role_id)
permissions(id, permission_code)
role_permissions(role_id, permission_id)
```

### 8.2. Encode password khi nào?

Password được encode khi user đăng ký hoặc đổi mật khẩu, bằng `PasswordEncoder.encode(rawPassword)`. `loadUserByUsername` sau này **đọc hash này**. Trong provider, so khớp bằng `PasswordEncoder.matches(raw, hash)`.

Anti-pattern:

```java
// Sai mục đích: không được tự hash lại password client trong lookup.
String newHash = encoder.encode(passwordFromRequest);
return User.withUsername(username)
    .password(newHash)
    .authorities("ROLE_USER")
    .build();
```

Ngoài việc contract không có `passwordFromRequest`, đoạn này còn phá kiến trúc và dễ gây lỗi với hashing có salt. Nếu credential của hệ thống không phải username/password hash (ví dụ LDAP bind), hãy chọn provider phù hợp.

### 8.3. Tránh mất quyền trên tenant và object

`getAuthorities()` có thể cho phép user vào tính năng `order:read`, nhưng không tự chứng minh user sở hữu đơn ID 123. Domain service phải kiểm tra principal ID, tenant, owner và trạng thái đơn dựa trên dữ liệu server. Đừng dùng một authority cấp tính năng thay thế quyền trên từng bản ghi.

## 9. Caching, credential erasure và đổi password

Một `CachingUserDetailsService` hoặc provider cache có thể giảm database lookups. Khi dùng cache, phải cân nhắc TTL và invalidation khi password hash, role, trạng thái account hoặc tenant thay đổi. Không suy luận “load một lần = quyền luôn đúng”.

`ProviderManager` có thể xóa credentials trên Authentication kết quả thông qua `CredentialsContainer.eraseCredentials()`. Nếu principal/UserDetails kết quả **chia sẻ cùng một object mutable** với cache, việc xóa credentials có thể khiến cache mất hash. Trong bộ demo, `AccountRow` giữ hash riêng và service tạo một `UserDetails` mới cho mỗi lookup, giảm nguy cơ chia sẻ đối tượng này.

Không tắt credential erasure chỉ để giữ password hash trong cache khi chưa đánh giá rủi ro giữ dữ liệu nhạy cảm trong bộ nhớ. Tùy trường hợp, cần return copy, cache immutable records hoặc làm mới object theo cách phù hợp.

### 9.1. UserDetailsPasswordService khác UserDetailsService

| Interface | Trách nhiệm |
| --- | --- |
| `UserDetailsService` | Load user theo username |
| `UserDetailsPasswordService` | Cập nhật encoded password nếu flow/provider được cấu hình để nâng cấp hash |
| `UserDetailsManager` | Quản lý user theo các operation có sẵn trong interface |
| `PasswordEncoder` | `encode`, `matches` và có thể `upgradeEncoding` |

Chỉ implement `UserDetailsService` không có nghĩa provider sẽ tự động update password hash trong database khi thuật toán đổi. Muốn nâng cấp hash, phải thiết kế `UserDetailsPasswordService` hoặc flow migration tương ứng, bảo đảm ghi DB an toàn.

### 9.2. BCrypt so với DelegatingPasswordEncoder

`BCryptPasswordEncoder` xử lý hash BCrypt dạng `$2a$...`. `DelegatingPasswordEncoder` nhận định dạng có id như `{bcrypt}$2a$...` để chọn thuật toán phù hợp. Nếu chuyển encoder mà hash thiếu tiền tố được yêu cầu, bạn có thể gặp lỗi `There is no PasswordEncoder mapped for the id "null"`.

Không “sửa nhanh” bằng `NoOpPasswordEncoder` cho production. Hãy kiểm tra hash format và kế hoạch migration encoder.

## 10. JWT/OIDC có luôn gọi UserDetailsService không?

**Không.** `UserDetailsService` thuộc luồng thường gặp của username/password. Với JWT resource server, `JwtDecoder` và converter có thể xác minh token, tạo principal và authorities mà không gọi `loadUserByUsername` mỗi request.

| Cơ chế | Có bắt buộc UserDetailsService? |
| --- | --- |
| HTTP Basic + DaoAuthenticationProvider | Thường có |
| Form login username/password | Thường có |
| JWT Resource Server | Không bắt buộc |
| OAuth2/OIDC login | Không bắt buộc |
| LDAP bind | Có thể dùng provider LDAP thay cho DAO hash flow |
| API key/mTLS custom | Dùng flow/provider phù hợp |

Nếu hệ thống cần nạp thêm profile sau khi JWT đã được verify, đó là logic ứng dụng riêng; không biến việc lookup thành bước “verify lại raw password” hay tin role do client tự gửi.

Khi có MFA, `loadUserByUsername` cũng không tự xử lý OTP/challenge: cần authentication flow chuyên biệt và trạng thái xác thực đúng từng bước.

## 11. Java 17 độc lập: lookup và password check là hai nhiệm vụ

Chương trình sau **không dùng Spring Security**. Nó chỉ mô phỏng kiến trúc tách source khỏi checker để biên dịch bằng JDK 17 thuần. Để minh họa đơn giản, chương trình dùng **plaintext demo và `String.equals`**, hoàn toàn không an toàn cho ứng dụng thật. Trong production dùng password hashing/encoder chuyên dụng như bộ Spring Boot ở trên.

Tạo file `UserLookupVsPasswordCheck.java`:

```java
import java.util.List;
import java.util.Map;

public class UserLookupVsPasswordCheck {

    record Account(
        String username,
        String demoSecret,
        List<String> authorities,
        boolean enabled
    ) {}

    static final class UserDirectory {
        private final Map<String, Account> rows = Map.of(
            "alice",
            new Account(
                "alice",
                "demo-pass",
                List.of("ROLE_USER", "report:read"),
                true
            )
        );

        Account loadByUsername(String username) {
            Account account = rows.get(username);
            if (account == null) {
                throw new IllegalArgumentException("unknown-user");
            }
            return account;
        }
    }

    static final class DemoPasswordChecker {
        boolean matches(String submitted, String stored) {
            // Đây chỉ là mô phỏng, KHÔNG phải password hashing.
            return submitted.equals(stored);
        }
    }

    public static void main(String[] args) {
        UserDirectory source = new UserDirectory();
        DemoPasswordChecker checker = new DemoPasswordChecker();

        Account alice = source.loadByUsername("alice");

        System.out.println("lookup.username=" + alice.username());
        System.out.println(
            "lookup.authorities="
                + String.join(",", alice.authorities())
        );
        System.out.println("lookup.verifiedPassword=false");
        System.out.println(
            "password.correct="
                + checker.matches("demo-pass", alice.demoSecret())
        );
        System.out.println(
            "password.wrong="
                + checker.matches("wrong", alice.demoSecret())
        );
        System.out.println("account.enabled=" + alice.enabled());

        try {
            source.loadByUsername("nobody");
        } catch (IllegalArgumentException ignored) {
            System.out.println("lookup.unknown=rejected");
        }
    }
}
```

Chạy:

```bash
javac UserLookupVsPasswordCheck.java
java UserLookupVsPasswordCheck
```

**Stdout chính xác theo code:**

```text
lookup.username=alice
lookup.authorities=ROLE_USER,report:read
lookup.verifiedPassword=false
password.correct=true
password.wrong=false
account.enabled=true
lookup.unknown=rejected
```

Ở đây `UserDirectory.loadByUsername` chỉ lấy record. Nó không nhận password request và không đưa ra kết luận password đúng. `DemoPasswordChecker` kiểm tra chuỗi sau lookup. Trong Spring Security thật, `UserDetailsService` cung cấp `UserDetails`, còn provider dùng `PasswordEncoder` để so khớp password/hash; provider cũng kiểm tra các account flags.

Chương trình Java này **không xác thực an toàn**, không tạo Authentication/SecurityContext, không bảo vệ web; chỉ dùng để nhận biết ranh giới trách nhiệm.

## 12. Các lỗi phổ biến và cách debug

| Dấu hiệu | Lý do có thể | Cách kiểm tra |
| --- | --- | --- |
| `UsernameNotFoundException` | Username không có ở nguồn lookup | Repository/query, normalization, tenant boundary |
| API trả 401 dù lookup thấy user | Password sai hoặc account disabled/locked | Encoder matches, account flags và provider |
| Có BCrypt hash nhưng báo encoder id null | DelegatingPasswordEncoder cần `{id}` | Version/format của hash và encoder |
| Login thành công, admin trả 403 | Thiếu `ROLE_ADMIN` / policy khác | Authorities, `hasRole`, object policy |
| Test `@WithMockUser` pass nhưng Basic login fail | Mock đã bỏ qua password provider | Integration test với `httpBasic(...)` |
| Nhiều user có cùng username | Unique constraint/tenant namespace sai | Chọn định danh bất biến và phạm vi unique |
| `getPassword()` trong cached user biến mất | Erase credentials trên shared object | Copy UserDetails, cache design, invalidation |
| Login cũ giữ quyền sau khi DB thu hồi | Session/token/cache authorities chưa refresh | Revoke/TTL và kiểm tra runtime |
| API JWT không gọi service | Đây có thể là flow token mặc định | Đọc JwtDecoder/converter và chain |
| `Cannot resolve UserDetailsService` | Thiếu dependency, import hoặc module | Starter, `org.springframework.security.core.userdetails` |
| Form login chuyển hướng nhưng curl thấy 401 | Khác client/entry point | SecurityFilterChain, HTTP Basic vs form login |
| POST trả 403 | CSRF hoặc authorization | Kiểm tra token và rule trước khi sửa |

### 12.1. Vì sao lỗi username không tồn tại có thể thành BadCredentialsException?

Trong nhiều cấu hình DAO authentication, provider cố tránh tiết lộ user có tồn tại hay không. `UsernameNotFoundException` từ service có thể được **ẩn thành lỗi credentials chung**. Điều này giảm rủi ro user enumeration. Không trả công khai “username có thật, password sai” khi threat model không cho phép.

### 12.2. Đừng dùng source để xác thực login

Anti-pattern:

```java
// Không dùng việc load thành công làm bằng chứng đã login.
UserDetails user = source.loadUserByUsername(request.username());
if (user != null) {
    // Không được cấp quyền hoặc đánh dấu authenticated ở đây.
}
```

Chỉ khi `AuthenticationProvider`/manager tin cậy kiểm tra credentials và account flags thành công mới có Authentication kết quả có thể dùng cho access policy.

### 12.3. Trường hợp nguồn dữ liệu lỗi

Database lỗi, query timeout hay user directory không kết nối không phải là password sai. Hệ thống cần phân loại lỗi và **không tạo Authentication đã xác thực** từ dữ liệu chưa kiểm chứng. Tùy API, có thể phải trả lỗi hạ tầng theo chính sách; không tự cho user đi tiếp do lookup gặp ngoại lệ.

### 12.4. Vì sao không được đưa password vào SQL?

Truy vấn kiểu `WHERE username=? AND password=?` dễ làm lẫn raw password với stored hash và không tương thích password hashing có salt. Query user theo username, tải hash và để provider dùng `matches`. Dữ liệu đầu vào phải được bind parameter hoặc ORM hóa đúng cách, tránh SQL injection.

### 12.5. Người dùng đã đổi role nhưng session vẫn giữ role cũ

Authorities trong Authentication có thể phản ánh thời điểm login hoặc token/phiên được tạo. Nếu role bị thu hồi hoặc user disabled, session/token/cache không nhất thiết tự cập nhật ngay. Cần chính sách TTL, invalidation, revoke hoặc kiểm tra runtime cho hành động nhạy cảm.

## 13. Checklist khi xây một UserDetailsService thật

- `loadUserByUsername` chỉ nhận username và trả `UserDetails` hoặc `UsernameNotFoundException`.
- Định nghĩa rõ case sensitivity, normalization và uniqueness của username/email theo tenant.
- Trả password hash đã lưu, không raw password.
- Không gọi `PasswordEncoder.matches` bên trong lookup tiêu chuẩn.
- Không encode lại một raw password request khi load.
- Trả authorities/flags đúng từ nguồn đáng tin cậy.
- Tránh sử dụng JPA entity với lazy relations chưa load hoặc serialize bí mật.
- Dùng `PasswordEncoder` phù hợp và có chiến lược migration hash.
- Đảm bảo provider thực sự sử dụng source; kiểm tra khi có nhiều provider/manager.
- Không đặt `authenticated=true` từ user tìm thấy hoặc role client tự khai.
- Kiểm soát cache và credential erasure để không dùng dữ liệu quyền/hash lỗi thời.
- Kiểm thử user có/không có, password đúng/sai, disabled/locked, authority có/thiếu.
- Thêm test phân quyền trên owner/tenant/resource tại service hoặc repository.
- Với POST dùng cookie/session, kiểm tra CSRF thích hợp.
- Không ghi log Authorization header, raw password, password hash, token hoặc session ID.
- Khi không xác minh được danh tính/quyền do lỗi hạ tầng, không tự động cấp quyền.

## 14. Câu hỏi tự kiểm tra

**1.** Vì sao `UserDetailsService.loadUserByUsername` không thể tự kiểm tra raw password trong contract chuẩn?

**2.** `UserDetails.getPassword()` nên trả dữ liệu gì?

**3.** Nếu source tìm thấy Alice nhưng người gọi nhập sai password, authentication có thành công không?

**4.** Thành phần nào thường gọi `PasswordEncoder.matches` trong username/password authentication?

**5.** Account có hash đúng nhưng `isEnabled() == false` có được xác thực không?

**6.** Vì sao không nên trả null khi username không tồn tại?

**7.** Sự khác biệt giữa `UserDetailsService` và `UserDetailsManager` là gì?

**8.** `UserDetailsPasswordService` dùng cho trường hợp nào?

**9.** `hasRole("ADMIN")` tìm authority nào theo prefix mặc định?

**10.** Vì sao `@WithMockUser` không đủ để chứng minh password của Alice được provider kiểm tra?

**11.** Vì sao API Resource Server JWT không nhất thiết gọi `loadUserByUsername` ở mỗi request?

**12.** Vì sao cache UserDetails có thể có vấn đề khi ProviderManager xóa credentials?

**13.** Nếu username chỉ unique trong tenant, phải kiểm tra thêm điều gì?

**14.** Sau khi đã login đúng, user có tự được xem mọi report của người khác không?

**15.** Một hash BCrypt lưu trong DB không có tiền tố `{bcrypt}` có thể gặp vấn đề gì khi dùng DelegatingPasswordEncoder?

**Đáp án gợi ý:**

1. Method chỉ nhận username; không có raw password từ request.
2. Encoded password/hash từ nguồn user đáng tin cậy.
3. Không; provider dùng PasswordEncoder kiểm tra và từ chối password sai.
4. `DaoAuthenticationProvider` phối hợp với `PasswordEncoder`.
5. Không. Account status là một trong các điều kiện xác thực.
6. Contract yêu cầu trả UserDetails hoặc ném UsernameNotFoundException.
7. UserDetailsManager bổ sung thao tác quản lý user; service cơ bản chỉ load user.
8. Cập nhật encoded password khi flow hash upgrade/đổi password được thiết kế đúng.
9. `ROLE_ADMIN`.
10. Mock user giả lập Authentication, không gọi provider/encoder thật.
11. JWT được xác minh bằng decoder/converter theo cơ chế resource server.
12. Nếu cache và principal chia sẻ object mutable, erasure có thể xóa hash trong cache.
13. Tenant phải đến từ ranh giới tin cậy và query/unique index phải giới hạn theo tenant đúng.
14. Không; vẫn cần kiểm tra owner, tenant và policy trên object.
15. Delegating encoder có thể không tìm được id mapping; cần kiểm tra và migrate format hash đúng.

## 15. Tài liệu chính thức

- [Spring Security 6.5 – UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 – Username/Password Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/index.html)
- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 – Servlet Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 – MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/)
- [UserDetailsService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html)
