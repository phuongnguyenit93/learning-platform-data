# isEnabled và trạng thái tài khoản được phép sử dụng

## Mục tiêu và ngữ cảnh

Một username có tồn tại và một password có khớp hash **chưa đủ** để quyết định account được phép đăng nhập. Tài khoản có thể chưa kích hoạt, bị quản trị viên vô hiệu hóa, bị khóa, hết hạn hoặc có credential đã hết hạn. Trong Spring Security, `UserDetails.isEnabled()` là một trong các thuộc tính mô tả **tình trạng được phép sử dụng tài khoản**, bên cạnh các cờ trạng thái khác.

Bài học thuộc nhóm **Trạng thái tài khoản** trong module *Spring Security - authentication*. Trọng tâm là ý nghĩa của `isEnabled()`, cách `DaoAuthenticationProvider` kiểm tra flag này, cách ánh xạ trạng thái miền nghiệp vụ và giới hạn của cơ chế khi đã có phiên đăng nhập/token. Ví dụ hoàn chỉnh dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x** và Servlet HTTP Basic. Các phần về JWT, OAuth2 hay WebFlux chỉ làm rõ ranh giới trách nhiệm, không phải hướng dẫn triển khai đầy đủ các cơ chế đó.

Sau bài học, bạn có thể:

1. Giải thích `isEnabled() == true/false` và phân biệt với `isAccountNonLocked`, `isAccountNonExpired`, `isCredentialsNonExpired`.
2. Xác định thành phần nào tải account, thành phần nào kiểm tra mật khẩu và trạng thái, thành phần nào tạo authentication kết quả.
3. Dự đoán `DisabledException`, `LockedException`, `AccountExpiredException` và `CredentialsExpiredException` trong một flow username/password chuẩn.
4. Chạy ví dụ Spring Boot với tài khoản active, disabled, locked, expired, credentials-expired và so sánh kết quả của `AuthenticationManager` với HTTP `401/403`.
5. Ánh xạ trạng thái `ACTIVE`, `PENDING_VERIFICATION`, `DISABLED`, `SUSPENDED`, `DELETED` vào hợp đồng Spring Security mà không trộn lẫn authority hay MFA.
6. Biết vì sao đổi account sang disabled không tự thu hồi mọi session/JWT đã được cấp, và cách kiểm thử yêu cầu chặn truy cập sau khi vô hiệu hóa.

**Điều cần nhớ:** `isEnabled()` là **một điều kiện trong quá trình xác thực sử dụng UserDetails**; nó không tự chứng minh người dùng đã đăng nhập và không phải cơ chế thu hồi session hay token toàn diện.

## 1. isEnabled nằm trong hợp đồng nào?

`org.springframework.security.core.userdetails.UserDetails` đại diện thông tin account do `UserDetailsService` hoặc một nguồn dữ liệu được provider sử dụng trả về. Hợp đồng cung cấp username, password hash, authorities và các cờ trạng thái. Phần API liên quan có thể nhìn như sau:

~~~java
public interface UserDetails extends java.io.Serializable {
    String getUsername();
    String getPassword();
    Collection<? extends GrantedAuthority> getAuthorities();

    boolean isEnabled();
    boolean isAccountNonLocked();
    boolean isAccountNonExpired();
    boolean isCredentialsNonExpired();
}
~~~

Đây là **đoạn rút gọn để minh họa**, không phải file source đầy đủ và không tự chạy. Trong Spring Security 6.x đời mới, các phương thức trạng thái của interface có thể có implementation mặc định trả `true`. Vì vậy, một class `UserDetails` tự viết nhưng không ánh xạ `isEnabled()` từ trạng thái thực tế có thể vô tình luôn coi tài khoản là active. Hãy kiểm tra API phiên bản đang dùng và tạo test cho mọi cờ.

Hợp đồng `isEnabled()` trả:

- `true`: account không bị đánh dấu disabled theo dữ liệu được nạp vào `UserDetails`; **vẫn phải** qua kiểm tra credentials và những cờ khác.
- `false`: account bị đánh dấu disabled, không được hoàn tất xác thực qua cơ chế chuẩn kiểm tra trạng thái `UserDetails`, tiêu biểu là `DaoAuthenticationProvider`.

`isEnabled() == true` **không phải** là `Authentication.isAuthenticated() == true`. Cái thứ nhất là thuộc tính của một record người dùng; cái thứ hai là trạng thái của authentication token sau một flow. Chỉ nhìn thấy user trong database hoặc nhận `UserDetails` từ service chưa đủ để được cấp quyền truy cập.

### 1.1. Bốn cờ thường gặp

| UserDetails API | `true` có nghĩa | `false` có nghĩa | Ngoại lệ điển hình |
| --- | --- | --- | --- |
| `isEnabled()` | Account được bật | Account bị disable | `DisabledException` |
| `isAccountNonLocked()` | Không bị khóa | Đang bị khóa | `LockedException` |
| `isAccountNonExpired()` | Account còn hiệu lực | Account đã hết hạn | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Password/credential còn hiệu lực | Credentials hết hạn | `CredentialsExpiredException` |

Ba tên có chữ **Non** rất dễ gây sai logic. `isAccountNonLocked() == false` nghĩa là *bị khóa*, không phải được mở. Trong lớp dựng sẵn `User`, các method của `User.UserBuilder` lại mang kiểu tên ngược:

~~~java
UserDetails disabled = User.withUsername("bob")
    .password(encodedHash)
    .roles("USER")
    .disabled(true)
    .build();

UserDetails locked = User.withUsername("carol")
    .password(encodedHash)
    .roles("USER")
    .accountLocked(true)
    .build();

UserDetails expired = User.withUsername("dave")
    .password(encodedHash)
    .roles("USER")
    .accountExpired(true)
    .build();

UserDetails changePassword = User.withUsername("erin")
    .password(encodedHash)
    .roles("USER")
    .credentialsExpired(true)
    .build();
~~~

Đây là **mã minh họa trong một method có biến `String encodedHash`**, không phải chương trình Java độc lập. `disabled(true)` tạo record có `isEnabled()==false`; `accountLocked(true)` tạo record có `isAccountNonLocked()==false`. Không nên map thẳng boolean với cùng tên mà quên đảo nghĩa.

Nếu một account bị cả locked lẫn disabled, provider có thể ném một exception ở bước kiểm tra đầu tiên, chứ không phải trả tất cả lỗi cùng lúc. Muốn xem đầy đủ các trạng thái để quản trị, hãy đọc domain status riêng, không suy toàn bộ từ một exception cuối.

### 1.2. Account status không phải role/authority

`GrantedAuthority` mô tả quyền, chẳng hạn `ROLE_USER`, `ROLE_ADMIN` hoặc `SCOPE_read`. `isEnabled` cho biết account có đủ điều kiện đăng nhập theo cơ chế liên quan hay không. Hai lớp này độc lập.

Alice enabled=true và có `ROLE_USER`: password đúng → có thể được xác thực và gọi `/me`; nhưng `/admin` cần `ROLE_ADMIN` → `403 Forbidden`.

Bob enabled=false nhưng có `ROLE_ADMIN`: với `DaoAuthenticationProvider`, password đúng vẫn không tạo login thành công. Quyền admin không làm cờ disabled mất hiệu lực.

Không nên “disable” account bằng cách xóa một role quan trọng rồi giữ `authenticated()` cho mọi URL: account có thể vẫn truy cập được các vùng không đòi role đó. Ngược lại, không nên bật account chỉ để cho phép truy cập một endpoint recovery mà chưa có bước xác minh hợp lệ.

## 2. Ai kiểm tra isEnabled trong Spring Security?

Luồng username/password thông thường:

~~~text
Client gửi username + password
   |
   v
Security filter (HTTP Basic / form login)
   |  tạo UsernamePasswordAuthenticationToken chưa xác thực
   v
AuthenticationManager (thường ProviderManager)
   |
   v
DaoAuthenticationProvider
   |
   +--> UserDetailsService.loadUserByUsername(username)
   |        |
   |        +--> trả UserDetails chứa hash, flags, authorities
   |
   +--> UserDetailsChecker và các kiểm tra account status
   |        |
   |        +--> disabled / locked / expired?
   |
   +--> PasswordEncoder.matches(rawPassword, storedHash)
   |
   +--> kiểm tra credentials expired và các chính sách khác
   |
   +--> Authentication đã xác thực HOẶC AuthenticationException
   |
   v
Filter: cập nhật SecurityContext / xử lý lỗi HTTP
   |
   v
Authorization: kiểm tra quyền truy cập URL/method
~~~

Sơ đồ thể hiện **các trách nhiệm**, không hứa thứ tự gọi chính xác từng phương thức ở mọi bản vá Spring Security. Trong các bản cập nhật chống timing attack, provider có thể thực hiện bước kiểm tra credentials ngay cả khi pre-check trạng thái phát hiện vấn đề nhằm giảm khác biệt thời gian phản hồi. Tuy nhiên, outcome chuẩn vẫn là account disabled bị từ chối.

- `UserDetailsService` chỉ **tải** record theo username; nó không tự gọi `setAuthenticated(true)`.
- `DaoAuthenticationProvider` sử dụng `UserDetails`, `PasswordEncoder` và checkers để đưa ra kết quả authentication.
- `AuthenticationManager.authenticate(...)` trả kết quả hoặc ném `AuthenticationException`.
- Filter xử lý request, exception, `SecurityContext`, entry point/failure handler.
- Authorization quyết định request đã xác thực có quyền cụ thể hay không.

**Không phải mọi authentication mechanism đều dùng `UserDetailsService`**. JWT resource server, OAuth2/OIDC login, certificate/pre-auth và custom providers có thể có cách đọc danh tính/trạng thái riêng, nên cờ `isEnabled` của account local không tự có hiệu lực trên tất cả.

### 2.1. Các pre/post checks chuẩn

`AbstractUserDetailsAuthenticationProvider` phân biệt kiểm tra **trước** và **sau** giai đoạn xác minh credentials:

| Nhóm | Điều kiện bất lợi | Kết quả |
| --- | --- | --- |
| Pre-check | `!isAccountNonLocked()` | `LockedException` |
| Pre-check | `!isEnabled()` | `DisabledException` |
| Pre-check | `!isAccountNonExpired()` | `AccountExpiredException` |
| Post-check | `!isCredentialsNonExpired()` | `CredentialsExpiredException` |

Checker mặc định thường kiểm tra locked trước disabled, sau đó account expired; credential expiry được kiểm tra sau. Một custom checker/provider có thể có chính sách khác. Không nên dùng “ngoại lệ đầu tiên xuất hiện” để xác định account chỉ có duy nhất một trạng thái bất lợi.

Với cơ chế password chuẩn, `DisabledException` kế thừa `AccountStatusException`, một `AuthenticationException`. Hãy giữ ranh giới này: account disabled là **authentication failure**, không phải người dùng đã authenticated rồi bị thiếu `ROLE_USER`.

### 2.2. Tại sao password đúng vẫn không đăng nhập được?

Ví dụ: database chứa Alice enabled=false, password hash hợp lệ. `UserDetailsService` vẫn có thể trả record Alice đầy đủ. Provider kiểm tra trạng thái và từ chối, dù password raw khớp. Có record ≠ login thành công.

Tương tự, khi account enabled=true nhưng password sai, provider ném `BadCredentialsException` thay vì thành công. Nếu chỉ gọi:

~~~java
UserDetails user = userDetailsService.loadUserByUsername("alice");
boolean enabled = user.isEnabled();
~~~

thì mới là **lookup dữ liệu**. Đoạn này nằm trong method đã inject service, không phải chương trình độc lập. Không được từ đó tạo authenticated token rồi đưa vào `SecurityContextHolder` để “bỏ qua” bước kiểm tra password.

### 2.3. Phản hồi 401 hay 403?

Trong ứng dụng HTTP Basic được cấu hình thông thường:

| Trường hợp | Kết quả điển hình |
| --- | --- |
| Request chưa có thông tin xác thực | HTTP `401 Unauthorized` |
| Username không tồn tại hoặc password sai | HTTP `401` |
| Tài khoản disabled, locked, expired hoặc credentials-expired | HTTP `401` |
| Authentication thành công nhưng thiếu authority cần thiết | HTTP `403 Forbidden` |
| Authentication thành công và quyền đủ | HTTP `200 OK` |

Với **form login** cho browser, authentication failure có thể dẫn đến redirect `302` về trang login lỗi; custom API entry point/failure handler cũng có thể đổi phản hồi. Không khẳng định một class exception tự quyết định status HTTP ở mọi hệ thống.

**Public login không nhất thiết phải tiết lộ “Tài khoản này bị khóa/disabled”**. Lý do nội bộ có thể được audit, nhưng thông điệp công khai thường nên được chuẩn hóa để tránh đối tượng không được xác thực dò user tồn tại.

## 3. Ví dụ Spring Boot đầy đủ: enabled, disabled, locked, expired

Ví dụ chạy trên Spring Boot 3.x, Spring Security 6.x và Java 17+. Ta dùng HTTP Basic và một `AuthenticationManager` tường minh, cho phép quan sát cùng policy qua Java và HTTP. Không cần database: service demo tạo `UserDetails` trực tiếp, mỗi lần lookup là **một instance mới** để tránh lỗi tái sử dụng principal mutable sau khi `ProviderManager` xóa credentials.

### 3.1. Khởi tạo project

Tạo Maven project bằng Spring Initializr:

- Java **17 hoặc 21**, Spring Boot **3.x**.
- Group `com.example`, artifact `account-status`, package `com.example.demo`.
- Dependencies **Spring Web** (`spring-boot-starter-web`) và **Spring Security** (`spring-boot-starter-security`).

Tạo file `src/main/java/com/example/demo/AccountStatusApplication.java`:

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class AccountStatusApplication {

    public static void main(String[] args) {
        SpringApplication.run(AccountStatusApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String storedHash = encoder.encode("demo-pass");

        // Mỗi lookup sinh UserDetails mới. Không tái sử dụng principal
        // mutable đã có thể bị xóa credentials sau authentication.
        return username -> switch (username) {
            case "active" -> User.withUsername("active")
                .password(storedHash).roles("USER")
                .build();

            case "disabled" -> User.withUsername("disabled")
                .password(storedHash).roles("ADMIN")
                .disabled(true)
                .build();

            case "locked" -> User.withUsername("locked")
                .password(storedHash).roles("USER")
                .accountLocked(true)
                .build();

            case "expired" -> User.withUsername("expired")
                .password(storedHash).roles("USER")
                .accountExpired(true)
                .build();

            case "credentials-expired" ->
                User.withUsername("credentials-expired")
                    .password(storedHash).roles("USER")
                    .credentialsExpired(true)
                    .build();

            default -> throw new UsernameNotFoundException("Unknown user");
        };
    }

    @Bean
    AuthenticationManager authenticationManager(
        UserDetailsService users,
        PasswordEncoder encoder
    ) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain security(
        HttpSecurity http,
        AuthenticationManager manager
    ) throws Exception {
        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    CommandLineRunner probe(AuthenticationManager manager) {
        return args -> {
            for (String name : List.of(
                "active", "disabled", "locked", "expired",
                "credentials-expired", "unknown"
            )) {
                try {
                    manager.authenticate(
                        UsernamePasswordAuthenticationToken
                            .unauthenticated(name, "demo-pass")
                    );
                    System.out.println("PROBE " + name + " => OK");
                }
                catch (AuthenticationException failure) {
                    System.out.println(
                        "PROBE " + name + " => "
                        + failure.getClass().getSimpleName()
                    );
                }
            }
        };
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String open() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "authenticated=" + authentication.getName();
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
~~~

Cấu hình này chủ động nối một `DaoAuthenticationProvider` với `UserDetailsService` và `BCryptPasswordEncoder`, rồi gắn manager vào `HttpSecurity`. Nhờ đó, `CommandLineRunner` và HTTP Basic sử dụng **cùng một provider**. Mỗi user có cùng raw password demo để tập trung vào status; password được hash bằng BCrypt khi ứng dụng khởi động. Không đưa mật khẩu demo hoặc đoạn probe vào production.

**Vì sao mỗi lookup trả User mới?** Lớp `User` của Spring Security có thể được dùng làm principal. Provider manager mặc định hỗ trợ việc xóa credentials trên authentication thành công. Nếu một implementation service trả đi trả lại cùng instance mutable chứa password hash, principal bị xóa credentials có thể ảnh hưởng những lần xác thực sau. Demo chủ động tạo instance mới để tách state.

### 3.2. Chạy ứng dụng và nhìn exception nội bộ

Trong thư mục Maven project do Initializr sinh:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell chạy `.\mvnw.cmd spring-boot:run`. Khi khởi động xong, các dòng **do chương trình in ra** (không tính log Boot) sẽ có dạng:

~~~text
PROBE active => OK
PROBE disabled => DisabledException
PROBE locked => LockedException
PROBE expired => AccountExpiredException
PROBE credentials-expired => CredentialsExpiredException
PROBE unknown => BadCredentialsException
~~~

`unknown` thông thường được `DaoAuthenticationProvider` chuyển lỗi user không tồn tại thành `BadCredentialsException` để giảm tiết lộ sự tồn tại của account (cấu hình mặc định che `UsernameNotFoundException`). Những exception trên là kết quả theo provider/checker chuẩn, với password đúng đối với các user tồn tại. Cấu hình custom hoặc phiên bản khác cần được test lại.

Tài khoản `disabled` có `ROLE_ADMIN` nhưng vẫn nhận `DisabledException`. Cờ disabled được áp dụng ở **authentication**, trước khi có một identity được xác thực để authorization chấp nhận.

### 3.3. Gửi request qua HTTP Basic

Ở terminal thứ hai:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u active:demo-pass http://localhost:8080/me
curl -i -u active:wrong http://localhost:8080/me
curl -i -u disabled:demo-pass http://localhost:8080/me
curl -i -u locked:demo-pass http://localhost:8080/me
curl -i -u expired:demo-pass http://localhost:8080/me
curl -i -u credentials-expired:demo-pass http://localhost:8080/me
curl -i -u unknown:demo-pass http://localhost:8080/me
curl -i -u active:demo-pass http://localhost:8080/admin
~~~

Trong PowerShell, nếu `curl` là alias, dùng `curl.exe`. Kết quả kỳ vọng:

| Request | Status | Ý nghĩa |
| --- | --- | --- |
| `GET /public`, anonymous | `200` | Body `public` |
| `GET /me`, anonymous | `401` | Chưa authentication |
| `GET /me`, `active:demo-pass` | `200` | Body **chính xác** `authenticated=active` |
| `GET /me`, `active:wrong` | `401` | Password sai |
| `GET /me`, `disabled:demo-pass` | `401` | `isEnabled() == false` |
| `GET /me`, `locked:demo-pass` | `401` | `isAccountNonLocked() == false` |
| `GET /me`, `expired:demo-pass` | `401` | Account expired |
| `GET /me`, `credentials-expired:demo-pass` | `401` | Credential expired |
| `GET /me`, `unknown:demo-pass` | `401` | Không tìm thấy account |
| `GET /admin`, `active:demo-pass` | `403` | Authentication thành công nhưng thiếu `ROLE_ADMIN` |

Chi tiết HTTP headers và response body khi lỗi có thể khác theo container/entry point. Không cần tắt CSRF để chạy các GET này. Basic authentication phải dùng **HTTPS** trong hệ thống thật: Base64 không bảo vệ password khỏi nghe lén.

### 3.4. Cấu hình này KHÔNG làm gì?

- Không tạo trang form login hoặc một endpoint cấp JWT.
- Không lưu status vào database; user chỉ tồn tại trong factory demo.
- Không tự phát email kích hoạt, mở khóa, đặt lại password.
- Không bảo đảm session hoặc token đã cấp trước khi disabled được thu hồi.
- Không kiểm tra account trạng thái mới ở mọi framework/custom provider một cách tự động.

Kết quả 401/403 trên demo xác nhận hành vi khi **gửi một authentication attempt mới** thông qua provider đã cấu hình; đừng suy rộng thành “thay status trong DB là mọi client mất quyền ngay”.

## 4. Mapping trạng thái từ database: chọn chính sách trước khi viết code

Một schema thật có thể là:

~~~text
app_accounts
  id
  login_name
  password_hash
  status_code        ACTIVE | PENDING | DISABLED | SUSPENDED | DELETED
  locked_until
  account_expires_at
  credentials_expires_at
  updated_at
~~~

Spring Security không tự hiểu `status_code`. Bạn phải ánh xạ trạng thái nghiệp vụ vào các cờ của `UserDetails` bằng policy có chủ đích. Ví dụ:

| Domain status | Enabled theo policy ví dụ | Ý nghĩa |
| --- | --- | --- |
| `ACTIVE` | `true` | Cho phép thử authentication, vẫn cần credential hợp lệ |
| `PENDING` / `PENDING_VERIFICATION` | `false` | Chưa hoàn tất xác minh/kích hoạt |
| `DISABLED` | `false` | Ngừng quyền đăng nhập thông thường |
| `SUSPENDED` | `false` hoặc cờ khóa riêng | Tùy semantics: disabled hay locked |
| `DELETED` (soft delete) | `false` hoặc không trả record | Không cho account được khôi phục như active |

Đây là ví dụ policy, **không** phải một bảng mapping bắt buộc. Nếu `SUSPENDED` biểu thị khóa tạm thời, `isAccountNonLocked()==false` có thể diễn tả chính xác hơn. Nếu account có quyền sử dụng nhưng phải đổi credential, dùng `isCredentialsNonExpired()==false` thay vì đánh dấu disabled mà không có lý do.

### 4.1. UserDetailsService custom cho trạng thái phức tạp

Ví dụ dưới đây là **đoạn adapter minh họa**, không phải file có thể chạy độc lập: nó giả định domain có `AccountRepository`, `AccountRecord`, `AccountStatus.ACTIVE` và method như comment, và có bean `Clock`.

~~~java
@Service
public class AccountDetailsService implements UserDetailsService {

    private final AccountRepository repository;
    private final Clock clock;

    public AccountDetailsService(
        AccountRepository repository,
        Clock clock
    ) {
        this.repository = repository;
        this.clock = clock;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountRecord account = repository.findByLogin(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        Instant now = Instant.now(clock);

        boolean enabled =
            account.status() == AccountStatus.ACTIVE;

        boolean locked = account.lockedUntil() != null
            && now.isBefore(account.lockedUntil());

        boolean expired = account.accountExpiresAt() != null
            && !now.isBefore(account.accountExpiresAt());

        boolean credentialsExpired =
            account.credentialsExpiresAt() != null
            && !now.isBefore(account.credentialsExpiresAt());

        return User.withUsername(account.loginName())
            .password(account.passwordHash())
            .authorities(account.authorities())
            .disabled(!enabled)
            .accountLocked(locked)
            .accountExpired(expired)
            .credentialsExpired(credentialsExpired)
            .build();
    }
}
~~~

Yêu cầu imports: `java.time.Clock`, `java.time.Instant`, `org.springframework.stereotype.Service`, `org.springframework.security.core.userdetails.*` liên quan; domain classes do dự án tự định nghĩa. `account.authorities()` được giả định trả `Collection<? extends GrantedAuthority>`; hash phải phù hợp encoder.

Điểm quan trọng:

- `disabled(!enabled)` **cố ý đảo boolean** từ policy enabled sang API builder.
- `lockedUntil`, `accountExpiresAt` và `credentialsExpiresAt` là các timestamp do server quản lý, nên so sánh với `Clock` nhất quán, có test tại ranh giới.
- `accountExpiresAt == now` được tính là đã hết hạn theo ví dụ `!now.isBefore(...)`.
- Nếu domain cần account expiry khác thời hạn lock, không dùng một cột cho hai nghĩa.
- Adapter chỉ **tải và ánh xạ dữ liệu**. Provider/manager mới xác minh password và đánh giá trạng thái.
- Hãy xác định trường hợp user thay đổi username, hai tenant trùng login hoặc soft delete; lookup sai account là lỗi bảo mật.

### 4.2. Nếu dùng JdbcDaoImpl

`JdbcDaoImpl` là implementation `UserDetailsService` dựa JDBC, có thể đổi `usersByUsernameQuery`. Hợp đồng truy vấn user truyền thống là ba cột theo thứ tự `username, password, enabled`. Với schema có `status_code`, một mẫu SQL là:

~~~sql
SELECT
    login_name AS username,
    password_hash AS password,
    CASE WHEN status_code = 'ACTIVE'
         THEN TRUE ELSE FALSE END AS enabled
FROM app_accounts
WHERE login_name = ?;
~~~

Đoạn SQL chỉ là **mẫu cho database hỗ trợ cú pháp CASE/BOOLEAN tương ứng**, không dùng trong project demo không có DB. Query được bind bằng placeholder `?`, không nối username client trực tiếp.

`JdbcDaoImpl` đọc enabled và authorities nhưng không tự ánh xạ mọi cờ nghiệp vụ như locked-until hoặc credentials expiry. Nếu ứng dụng cần logic phong phú, custom `UserDetailsService` thường rõ ràng hơn việc cố nhét mọi thứ vào một biểu thức enabled.

### 4.3. Dữ liệu kiểm thử ranh giới

Với policy theo thời gian, nên có unit test:

- Account status `ACTIVE`: enabled=true.
- `PENDING_VERIFICATION`, `DISABLED`, `DELETED`: enabled=false.
- `lockedUntil = now + 1s`: locked.
- `lockedUntil = now`: hết khóa theo quy tắc của ví dụ.
- `accountExpiresAt = now`: expired.
- `credentialsExpiresAt = now`: credentials expired.
- Sai hoặc thiếu record: ném `UsernameNotFoundException`.
- Account có nhiều trạng thái bất lợi: xác minh semantics mong muốn; không ép một cờ đại diện cho tất cả.

`Clock.fixed(...)` giúp test không phụ thuộc thời gian thực và tránh lỗi khi test chạy qua mốc giây.

## 5. isEnabled không tự động thu hồi phiên đã có

Giả sử Alice đăng nhập lúc 09:00, Spring Security lưu một `Authentication` đã xác thực trong `SecurityContext` của session. Lúc 09:10, admin đổi account sang disabled trong database. Lúc 09:15, Alice dùng cùng cookie gọi `/dashboard`.

**Không có bảo đảm mặc định rằng mọi request sẽ gọi lại `UserDetailsService.loadUserByUsername(...)` hoặc `DaoAuthenticationProvider` để kiểm tra `isEnabled`.** Nếu một request chỉ khôi phục `Authentication` đã có trong session, nó có thể vẫn được coi là authenticated cho tới khi session/token bị thu hồi hoặc re-check theo cơ chế được thiết kế riêng.

Tương tự, một JWT đã ký vẫn còn hạn và hợp lệ có thể được resource server chấp nhận sau khi account local disabled nếu resource server chỉ kiểm tra signature, issuer, audience, expiry và scopes từ token mà không hỏi trạng thái account.

### 5.1. So sánh theo kiểu authentication

| Cơ chế | isEnabled thường được kiểm tra ở đâu? | Disable database có chặn ngay request cũ? |
| --- | --- | --- |
| Form login + session | Khi login username/password và provider dùng `UserDetails` | Không mặc định, session đã có có thể được dùng lại |
| HTTP Basic | Thường khi mỗi request thực hiện password authentication | Không cam kết với mọi cache/session/filter cấu hình |
| JWT resource server | Không mặc định dùng `UserDetails.isEnabled` | Không nếu chỉ validate token độc lập |
| OAuth2/OIDC login | Tùy tích hợp với local account policy | Không tự động |
| Custom/pre-auth | Do implementation quyết định | Phải kiểm thử implementation |
| Re-check account DB mỗi request | Tùy filter/policy được thiết kế riêng | Có thể đáp ứng thu hồi nhanh nhưng phải quản lý cache/race/failure |

### 5.2. Các bước cần có khi disable phải chặn truy cập ngay

1. Cập nhật trạng thái account trong một transaction có authorization và audit.
2. Vô hiệu hóa các session server-side của user theo hệ thống session registry/session store đang sử dụng, kể cả nhiều thiết bị và nhiều node nếu cần.
3. Thu hồi remember-me token, refresh token và token lưu server-side.
4. Với JWT access token, cân nhắc TTL ngắn, revocation list, token version per user hoặc introspection; chọn theo SLA và kiến trúc.
5. Invalidate các cache `UserDetails`, account status và authorities liên quan.
6. Kiểm thử bằng một **session/token đã đăng nhập từ trước khi disable**, không chỉ thử đăng nhập mới.
7. Khi DB hoặc status service lỗi, không được tự coi account enabled hoặc cho qua vì không kiểm tra được (fail-open).

Không gọi `HttpSession.invalidate()` trên request admin rồi nghĩ rằng mọi session của một user khác đã bị vô hiệu hóa. Thao tác đó thường liên quan session hiện tại, không phải toàn bộ device. `SessionRegistry` cũng phải được cấu hình và tích hợp đúng với lưu trữ phân tán nếu có nhiều instance.

### 5.3. Cache và xóa credentials

`UserCache`, caching ở repository, hoặc một authentication cũ trong session có thể mang cờ enabled từ trước khi admin đổi trạng thái. Hãy xác định cache invalidation/TTL và nguồn sự thật.

Ngoài ra, Spring Security có cơ chế xóa credentials sau khi xác thực thành công nếu object hỗ trợ `CredentialsContainer`. Lớp `User` có thể bị biến đổi khi xóa password. Không tái sử dụng một instance `User` mutable làm cả dữ liệu cache và principal đã bị erase; trả instance riêng hoặc thiết kế cache đúng. Đừng tắt credential erasure chỉ để che lỗi dùng lại object nếu có giải pháp tốt hơn.

## 6. Trạng thái account, email verification và MFA

`enabled=false` phù hợp với account chưa được kích hoạt hoặc bị disable theo policy chung. Tuy nhiên, những luồng sau cần tách rõ:

- **Email verification:** một user chưa xác minh email có thể vẫn truy cập endpoint xác nhận email bằng token một lần/ngắn hạn mà không có quyền truy cập ứng dụng chính. Không cần bật account tạm chỉ để người dùng xác minh.
- **Password reset:** account disabled không thể tự bypass status bằng cách gửi username và link do client tự tạo. Quy trình recovery phải xác minh quyền sở hữu và dùng token bảo mật phù hợp.
- **Lockout do sai password:** có thể dùng `isAccountNonLocked` và `lockedUntil`, nhưng cần rate limiting và chính sách tránh attacker cố tình khóa user khác.
- **MFA:** `isEnabled=true` không chứng minh OTP, passkey, push approval hoặc yếu tố bổ sung đã được hoàn thành. Thiết kế authentication flow thực hiện riêng, không chỉ đổi một cờ rồi coi multi-factor thành công.
- **User nghỉ việc/thu hồi tài khoản:** disable account nên đi kèm session/token revocation, chứ không chỉ thay một cột boolean.

Việc một account được mở lại (`enabled=true`) cũng không bảo đảm login thành công: mật khẩu có thể sai, account vẫn locked, credentials expired, hoặc policy của provider khác không đáp ứng. Các trạng thái cần được kiểm tra độc lập.

## 7. Bảo mật chống dò tài khoản: không lộ trạng thái chi tiết

Một API đăng nhập công khai không nên mặc định tiết lộ chính xác user tồn tại và trạng thái của họ:

~~~json
{
  "error": "ACCOUNT_DISABLED",
  "username": "alice",
  "registeredEmail": "alice@example.com"
}
~~~

Đây là **ví dụ payload không nên trả mặc định cho người chưa được xác thực**. Attacker có thể dùng nó để phân biệt account tồn tại, đang active hay bị disabled. Thông điệp công khai có thể là “Không thể đăng nhập bằng thông tin đã cung cấp”, trong khi audit nội bộ (quyền truy cập hạn chế) ghi mã trạng thái thực tế.

Sau khi người dùng đã chứng minh quyền sở hữu account qua một kênh recovery đáng tin, ứng dụng có thể đưa ra hướng dẫn thích hợp, miễn không biến public login thành oracle dò user. Không log raw password, cookie, bearer token, toàn bộ authentication object hoặc password hash.

### 7.1. Cảnh báo bảo mật CVE-2026-22746

Ngày **20/04/2026**, Spring công bố **CVE-2026-22746**: trong một số phiên bản Spring Security, dùng `UserDetails#isEnabled`, `isAccountNonExpired` hoặc `isAccountNonLocked` cùng `DaoAuthenticationProvider` có thể làm suy yếu chống dò account qua **khác biệt thời gian phản hồi**.

Advisory chính thức ghi nhận các nhánh bị ảnh hưởng và bản sửa, bao gồm **Spring Security 6.5.10** và **7.0.5**. Xem [Spring — CVE-2026-22746: User Attribute Enumeration when Using DaoAuthenticationProvider](https://spring.io/security/cve-2026-22746).

Nếu ứng dụng sử dụng các status flags này, hãy kiểm tra **phiên bản Spring Security được resolve thực tế**, nâng lên bản đã vá/bản bảo mật mới tương thích, và kiểm thử timing-related behavior sau nâng cấp. Chỉ ẩn câu chữ exception trong HTTP response không đủ nếu có rò rỉ thời gian. Đừng tùy tiện tắt các bước kiểm tra credentials bổ sung mà không đánh giá rủi ro.

### 7.2. Không nhận isEnabled từ client

Dữ liệu như `X-Account-Enabled: true`, `X-User-Status: ACTIVE` hoặc `accountStatus` từ JSON request đều là input do client có thể sửa. **Không** dùng chúng để đặt cờ enabled. Status phải đến từ DB/identity provider/policy engine đáng tin, gắn với đúng user và tenant sau khi được kiểm chứng.

Nếu username chỉ unique trong mỗi tenant, tra cứu `WHERE username=?` không kèm tenant đáng tin có thể trả nhầm tài khoản. Đây là vấn đề identity boundary; đừng sửa bằng cách tin header `X-Tenant` chưa được xác minh.

## 8. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| DB đã disabled nhưng login mới vẫn thành công | `UserDetailsService` map sai, default `isEnabled` vẫn true, hoặc provider không kiểm tra status | Test mapper và authentication manager thực tế |
| `disabled(true)` nhưng dev nghĩ đã bật account | Đảo nghĩa trong `User.UserBuilder` | `disabled(true)` → `isEnabled()==false` |
| User có `ROLE_ADMIN` nhưng vẫn nhận 401 | Account disabled/locked hoặc password sai | Kiểm tra authentication trước authorization |
| User active vào /me được, /admin bị 403 | Thiếu authority | Đúng mô hình; thêm quyền nếu thực sự hợp lệ |
| Account bị locked nhưng nhận DisabledException | Các cờ bất lợi chồng nhau; thứ tự checker hoặc policy | Thiết kế status rõ; xem record đầy đủ |
| Account disabled vẫn truy cập bằng cookie cũ | Session/token chưa được thu hồi | Thiết kế revocation và recheck theo SLA |
| Password đã đổi nhưng Basic login sai | Hash/encoder không khớp hoặc credential hết hạn | Kiểm tra `PasswordEncoder` và mapping |
| Mở lại account vẫn không login được | Cache giữ disabled, vẫn locked/expired, sai password | Invalidate cache, kiểm tra từng flag |
| Public login tiết lộ tài khoản bị disabled | Handler trả exception chi tiết | Dùng thông điệp chung, giữ audit nội bộ |
| App dùng JWT vẫn chấp nhận account disabled | JWT không mặc định check local UserDetails | Dùng token policy/introspection/revocation |
| Nhiều account cùng username giữa tenant | Lookup thiếu tenant context | Tách identity namespace, xác minh nguồn tenant |
| Test chỉ chạy login mới rồi kết luận thu hồi tức thì | Chưa test session/token đã tồn tại | Tạo test disable giữa phiên thật |

## 9. Kiểm thử và bài tập

### 9.1. Unit test mapping và provider

Ít nhất nên kiểm tra status trước/sau thời điểm:

- Account `ACTIVE` → enabled true.
- `PENDING_VERIFICATION`, `DISABLED`, `DELETED` → enabled false theo policy ví dụ.
- `lockedUntil == now + 1s` → locked; `lockedUntil == now` → hết khóa.
- `accountExpiresAt == now` → expired.
- `credentialsExpiresAt == now` → credentials expired.
- DB không tìm thấy account → `UsernameNotFoundException` trong service, nhưng public login có thể được provider chuẩn chuyển thành lỗi chung.
- Password sai với active user → `BadCredentialsException`.
- Status disabled với password đúng → `DisabledException` trong manager.

Ví dụ **mã test minh họa**, không phải file độc lập (cần JUnit 5, Spring test configuration và manager đã inject):

~~~java
DisabledException thrown = assertThrows(
    DisabledException.class,
    () -> manager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "disabled", "demo-pass"
        )
    )
);
~~~

Các import tương ứng từ JUnit `Assertions.assertThrows`, Spring Security `DisabledException` và `UsernamePasswordAuthenticationToken`. Không gọi `UserDetailsService.loadUserByUsername(...)` rồi khẳng định đã test authentication; nó chỉ test lookup.

### 9.2. Tình huống A — database record có tồn tại

`loadUserByUsername("alice")` trả user với `isEnabled()==true` và một role. Được phép tự tạo token authenticated rồi đặt vào `SecurityContextHolder` mà không kiểm tra password không?

**Đáp án:** không. Record tồn tại không chứng minh người gửi request sở hữu credentials; phải qua authentication mechanism hợp lệ.

### 9.3. Tình huống B — đã disable nhưng session chưa mất

Alice đăng nhập sáng nay. Admin chuyển status sang disabled giữa ngày. Alice dùng cookie cũ vẫn vào `/dashboard`. Đây có nhất thiết là bug của `isEnabled` không?

**Đáp án:** chưa chắc. `isEnabled` thường được kiểm tra khi xác thực bằng provider, không tự recheck session cũ. Hãy kiểm thử session invalidation hoặc account recheck đã được thiết kế.

### 9.4. Tình huống C — role admin

Bob có `ROLE_ADMIN` nhưng `isEnabled()==false`. Password đúng. Bob có thể vào `/admin` không?

**Đáp án:** không, với `DaoAuthenticationProvider` tiêu chuẩn. Account status ngăn authentication trước khi authorization đánh giá role.

### 9.5. Tình huống D — hai trạng thái đồng thời

`isAccountNonLocked()==false` và `isEnabled()==false`. Vì sao code có thể nhận `LockedException` chứ không phải `DisabledException`?

**Đáp án:** checker chuẩn xét lock trước disabled. Một ngoại lệ không đại diện toàn bộ tình trạng account. Public login cũng không nên lộ chi tiết này.

### 9.6. Tình huống E — JWT chưa hết hạn

JWT có `scope=read` còn 15 phút. Account local disabled nhưng resource server chỉ xác minh signature và `exp`. Token có bị từ chối ngay không?

**Đáp án:** không mặc định. Phải có revocation, introspection, giới hạn TTL hoặc cơ chế account-status check cụ thể.

### 9.7. Tình huống F — UserDetails tự viết

Trong phiên bản có default `isEnabled()==true`, một class `UserDetails` custom không override `isEnabled`. DB lại có `status=DISABLED`. Cấu hình đó an toàn không?

**Đáp án:** không. Flag có thể vẫn true. Phải map status rõ, viết unit test và xác nhận provider thực sự kiểm tra cờ.

## 10. Checklist triển khai

- [ ] Đã định nghĩa rõ enabled/disabled, locked, expired, credentials-expired, pending verification và deleted trong domain.
- [ ] `UserDetailsService` trả đúng cờ và không vô tình dùng giá trị mặc định true khi DB đã disabled.
- [ ] `DaoAuthenticationProvider`, `PasswordEncoder` và `AuthenticationManager` thật sự dùng service/policy đã cấu hình.
- [ ] Tài khoản disabled bị từ chối dù password đúng, có role mạnh hoặc trước đây đã đăng nhập.
- [ ] Đã thử bằng HTTP: active đúng password, password sai, disabled, locked, expired, credentials-expired, username không tồn tại và role thiếu.
- [ ] Không trộn `401` do authentication failure với `403` do authorization failure.
- [ ] Có kế hoạch xóa cache, invalidation session, remember-me, refresh token và JWT theo mức độ thu hồi tài khoản cần thiết.
- [ ] Account status đến từ nguồn đáng tin, không nhận cờ do client tự khai báo hoặc tenant header chưa xác minh.
- [ ] Không log/tiết lộ thông tin nhạy cảm, thông điệp status chi tiết hoặc khác biệt thời gian dễ dò account.
- [ ] Kiểm tra phiên bản Spring Security trước cảnh báo CVE-2026-22746 và nâng cấp theo advisory tương ứng.
- [ ] Có regression test cho **phiên đã xác thực trước thời điểm disabled**, không chỉ login mới.

**Kết luận:** `UserDetails.isEnabled()` xác định account đang được bật hay bị disable. Với `DaoAuthenticationProvider` chuẩn, khi flag false sẽ không tạo authentication thành công và có thể ném `DisabledException`, kể cả username tồn tại và password đúng. Nhưng flag này không thay thế kiểm tra credentials, role, MFA và cũng không tự thu hồi session/token đã cấp. Muốn bảo mật toàn diện cần mapping trạng thái đúng, authentication provider đúng, cơ chế thu hồi phiên cùng các bài test đa lớp.

## Tài liệu tham khảo

- [Spring Security 6.5 — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security 6.5 — User và UserBuilder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security 6.5 — AbstractUserDetailsAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html)
- [Spring Security 6.5 — UserDetailsChecker](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsChecker.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring — CVE-2026-22746: User Attribute Enumeration (20/04/2026)](https://spring.io/security/cve-2026-22746)
