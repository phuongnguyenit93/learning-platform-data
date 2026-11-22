# AuthenticationException và những lỗi trạng thái tài khoản

> **Chủ đề:** Bộ máy xác thực trong Spring Security Servlet. Bài học giải thích cây `AuthenticationException`, các lỗi trạng thái tài khoản, điểm phát sinh lỗi ở `AuthenticationManager`/`AuthenticationProvider`, cách chúng được chuyển thành phản hồi HTTP, và cách kiểm chứng bằng ứng dụng Java 17+ Spring Boot. Trọng tâm là username/password; với bearer token, OIDC hay cơ chế khác, loại lỗi và giao thức phản hồi sẽ có đặc thù riêng.

## 1. Một đăng nhập thất bại có thể có nhiều nguyên nhân

Client gửi username và mật khẩu vào ứng dụng. Khi không đăng nhập được, ta cần phân biệt ít nhất những trường hợp sau:

1. Username không có trong nguồn danh tính.
2. Có user nhưng mật khẩu hoặc bằng chứng xác thực không đúng.
3. User đang **bị vô hiệu hóa** bởi quản trị/chính sách.
4. User đang **bị khóa**, có thể do bảo mật hoặc quyết định quản trị.
5. Tài khoản đã **hết hạn sử dụng**.
6. Credential đã **hết hạn**, ví dụ cần thay mật khẩu.
7. Dịch vụ danh tính/database không hoạt động, nên không thể xác minh.
8. Đăng nhập **thành công** nhưng tài khoản không có quyền truy cập chức năng cụ thể.

Nhóm 1–7 liên quan tới **xác thực (authentication)**. Nhóm 8 là **phân quyền (authorization)**. Các nhóm có thể có phản hồi bên ngoài tương tự nhau, nhưng nguyên nhân nội bộ, cách theo dõi và hành động xử lý khác nhau.

Spring Security dùng `AuthenticationException` để biểu diễn lỗi xảy ra khi xác thực. Với trạng thái user, các subclass `AccountStatusException` giúp chỉ rõ lý do nội bộ. Tuy nhiên, **không nên trả nguyên tên exception ra client chưa xác thực**: trả khác nhau cho username không tồn tại, username bị khóa và password sai có thể giúp dò tài khoản.

### Một tình huống minh họa

Giả sử tài khoản `an` bị khóa vì chính sách; tài khoản `binh` vẫn bình thường nhưng nhập sai mật khẩu. Cả hai request đều không có một `Authentication` đăng nhập thành công. Với HTTP Basic API, người gọi thường nhận **401**. Bên trong, provider có thể ném `LockedException` cho An và `BadCredentialsException` cho Bình. Đây là sự phân biệt hữu ích cho audit, vận hành và quy trình mở khóa, nhưng không mặc định được phơi bày qua response công khai.

## 2. `AuthenticationException` và các nhánh cần biết

`org.springframework.security.core.AuthenticationException` là một unchecked exception (kế thừa `RuntimeException`) làm nền cho các lỗi xác thực. Các implementation của `AuthenticationManager` hoặc `AuthenticationProvider` thường ném subclass thích hợp khi kiểm tra không đạt.

Cây phân loại **rút gọn**:

```text
AuthenticationException
├── BadCredentialsException
├── UsernameNotFoundException
├── AccountStatusException
│   ├── DisabledException
│   ├── LockedException
│   ├── AccountExpiredException
│   └── CredentialsExpiredException
├── AuthenticationServiceException
│   └── InternalAuthenticationServiceException
├── ProviderNotFoundException
└── InsufficientAuthenticationException
```

Cây này chỉ mô tả các loại nổi bật trong bài, không phải toàn bộ API. Có các exception khác cho những cơ chế xác thực khác.

| Exception | Đặc trưng | Điều không nên suy luận |
| --- | --- | --- |
| `BadCredentialsException` | Credential được cung cấp không hợp lệ | Không khẳng định username thực sự có trong hệ thống |
| `UsernameNotFoundException` | `UserDetailsService` không tìm thấy user | Không nên mặc định truyền nguyên ra client |
| `DisabledException` | User bị vô hiệu hóa | Không chứng minh password đã đúng |
| `LockedException` | User bị khóa | Không chứng minh password đã đúng |
| `AccountExpiredException` | Hiệu lực của chính tài khoản đã hết | Không đồng nghĩa password hết hạn |
| `CredentialsExpiredException` | Hiệu lực credential đã hết | Không đồng nghĩa account bị vô hiệu hóa |
| `AuthenticationServiceException` | Lỗi từ hệ thống xác thực | Không nên coi là người dùng nhập sai |
| `ProviderNotFoundException` | Không có provider hỗ trợ loại `Authentication` nhận vào | Có thể là vấn đề cấu hình/hợp đồng xác thực |
| `InsufficientAuthenticationException` | Mức độ tin cậy của xác thực chưa đủ | Không đơn giản là “password sai” |

**Điểm tách quan trọng:** `AccessDeniedException` thuộc **authorization**, không phải một subclass của `AuthenticationException`. Nếu An đã được xác thực thành công nhưng không có quyền admin, đây là quyết định quyền truy cập, không có lý do nói mật khẩu của An sai.

### Exception Java và HTTP status khác nhau

Gọi `authenticationManager.authenticate(request)` trực tiếp là thao tác Java. Thành công thì trả `Authentication`; thất bại thì ném `AuthenticationException`. Trạng thái HTTP như 401/403 do các thành phần web/filter/handler quyết định sau đó. Không có quy tắc “mọi `AuthenticationException` trong mọi ứng dụng đều có cùng body hoặc status”.

## 3. Bốn lỗi trạng thái tài khoản

`AccountStatusException` là lớp cha cho bốn trạng thái user thường được kiểm tra ở đường xác thực username/password.

### 3.1. `DisabledException` — tài khoản vô hiệu hóa

Có thể xuất hiện khi quản trị viên tắt tài khoản, tài khoản đang chờ kích hoạt theo chính sách hoặc hệ thống quyết định user chưa được phép đăng nhập. Cờ liên quan trong `UserDetails` là `isEnabled()`.

Điểm đáng lưu ý: một provider có thể kiểm tra **trạng thái trước** khi đối chiếu password. Do đó, thấy `DisabledException` **không chứng minh password đã đúng**. Một giao diện công khai không nên dùng điều này để cho biết “tài khoản có thật và đã bị vô hiệu hóa” khi chưa có cơ chế bảo vệ thông tin.

### 3.2. `LockedException` — tài khoản bị khóa

Khóa có thể do quản trị viên hoặc chính sách chống tấn công. Cờ liên quan là `isAccountNonLocked()`. Một lock có thể là vĩnh viễn, có thời hạn, hoặc cần quy trình xác minh để mở.

**Khóa tài khoản khác rate limiting**: Spring Security cung cấp khả năng nhận diện cờ locked và exception, nhưng không tự động cung cấp toàn bộ bộ đếm nhập sai, chiến lược khóa 15 phút, storage phân tán, cảnh báo và quy trình mở khóa. Nếu ứng dụng cần khóa sau N lần sai, phải thiết kế cơ chế đếm/ghi trạng thái tin cậy, có giới hạn tần suất và xử lý đồng thời.

### 3.3. `AccountExpiredException` — tài khoản hết hạn

Phản ánh hiệu lực của tài khoản đã kết thúc, tương ứng `isAccountNonExpired() == false`. Ví dụ account khách hoặc account thời vụ có ngày hết hạn.

Không nhất thiết dùng lỗi xác thực cho mọi trường hợp subscription/hợp đồng hết hạn. Nếu người dùng vẫn cần đăng nhập để xem lịch sử thanh toán hoặc gia hạn, có thể phải xử lý bằng **quy tắc phân quyền/nghiệp vụ** thay vì cấm xác thực toàn bộ tài khoản.

### 3.4. `CredentialsExpiredException` — bằng chứng xác thực hết hạn

Ví dụ chính sách yêu cầu đổi mật khẩu sau một khoảng thời gian. Cờ liên quan là `isCredentialsNonExpired()`. User còn tồn tại nhưng không được sử dụng credential cũ để tạo xác thực đầy đủ.

Lỗi này **không tự tạo** màn hình đổi mật khẩu hoặc reset-flow. Cần thiết kế một luồng đổi/khôi phục credential có xác minh danh tính, giới hạn quyền và biện pháp chống lạm dụng phù hợp.

### Bảng bốn cờ của `UserDetails`

| Method | `true` có nghĩa là | Khi `false`, checker có thể ném |
| --- | --- | --- |
| `isEnabled()` | Tài khoản được phép sử dụng | `DisabledException` |
| `isAccountNonLocked()` | Tài khoản **không** bị khóa | `LockedException` |
| `isAccountNonExpired()` | Tài khoản **chưa** hết hạn | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credential **chưa** hết hạn | `CredentialsExpiredException` |

Ba method có chữ `Non` thường gây nhầm khi triển khai mapping database. Ví dụ `isAccountNonLocked() == false` nghĩa là **đang bị khóa**, không phải “không khóa”.

Nếu cùng lúc có nhiều trạng thái sai, exception quan sát phụ thuộc thứ tự checker/provider. Không lấy thứ tự đó làm luật phân quyền nghiệp vụ; nên xác định rõ trạng thái hiệu lực và chiến lược xử lý chính sách.

## 4. Exception phát sinh ở đâu trong bộ máy xác thực?

Một chuỗi xử lý điển hình cho username/password với `DaoAuthenticationProvider`:

```text
Request có username/password (chưa được tin cậy)
             |
             v
Authentication Filter
             |
             v
AuthenticationManager (ví dụ ProviderManager)
             |
             v
DaoAuthenticationProvider
             |
             +-- UserDetailsService.loadUserByUsername(...)
             |       +-- Không có user -> UsernameNotFoundException
             |                               (có thể che thành BadCredentialsException)
             |
             +-- Kiểm tra trạng thái trước credential
             |       +-- locked / disabled / account expired
             |
             +-- PasswordEncoder.matches(raw, encoded)
             |       +-- Sai -> BadCredentialsException
             |
             +-- Kiểm tra trạng thái sau credential
             |       +-- credentials expired
             |
             +-- Thành công -> Authentication đã xác thực
                                        |
                                        v
                                 SecurityContext
                                        |
                                        v
                                Authorization
```

Luồng trên là **mô hình thường gặp** của `DaoAuthenticationProvider` và các user-details checker trong Spring Security. Với custom provider, cache, MFA hoặc cơ chế token, các bước có thể khác.

### Vì sao tải được hồ sơ vẫn chưa phải đăng nhập thành công?

`UserDetailsService` tải account, password hash, flags và authorities từ nguồn ứng dụng. Nó không tự xác minh credential. Khi `loadUserByUsername("an")` trả về user, `an` vẫn chỉ là danh tính người gọi **khai báo**; provider phải thực hiện các kiểm tra rồi mới tạo kết quả xác thực thành công.

### Username không tồn tại có thể trở thành `BadCredentialsException`

`AbstractUserDetailsAuthenticationProvider` có chính sách `hideUserNotFoundExceptions`, thường **bật theo mặc định**. Khi `UserDetailsService` báo không tìm thấy user, provider có thể chuyển thành `BadCredentialsException`. Mục đích là giảm khả năng attacker phân biệt “user không tồn tại” và “user tồn tại nhưng password sai” thông qua một loại exception đơn giản.

Do đó **không phải cứ bắt được `BadCredentialsException` là có một account cụ thể để tăng biến đếm lockout**. Bộ đếm và policy chống tấn công cần dữ liệu đã được kiểm tra và thiết kế chống user enumeration.

### Checker trước/sau khi kiểm tra mật khẩu

Trong luồng DAO thông thường, các cờ locked/disabled/account-expired được kiểm tra trước bước kiểm tra password; hạn credential có thể được kiểm tra sau bước đó. Điều này không làm thay đổi quy tắc: một lần đăng nhập chỉ thành công khi mọi điều kiện cần đều đạt. Cũng không được kết luận credential đúng chỉ từ một exception trạng thái vì thứ tự xử lý, custom provider và biến thể cấu hình có thể khác.

## 5. Phân biệt xác thực thất bại và thiếu quyền

Ví dụ API có endpoint `GET /me` yêu cầu login và `GET /admin` yêu cầu `ROLE_ADMIN`:

| Request | Ý nghĩa | Phản hồi điển hình |
| --- | --- | --- |
| Không gửi credential khi gọi `/me` | Chưa xác thực | HTTP 401/challenge trong Basic |
| Gửi password sai | Xác thực thất bại | HTTP 401 |
| Gửi password đúng cho account disabled | Xác thực thất bại | Thường HTTP 401 trong Basic |
| Đã xác thực nhưng không có `ROLE_ADMIN` | Thiếu quyền | HTTP 403 |
| Kho user bị lỗi mạng | Không thể xử lý authentication | Phụ thuộc error policy, cần cảnh báo hạ tầng |

**HTTP 401** thường yêu cầu authentication/credential. **HTTP 403** thường biểu thị truy cập bị từ chối do quyền. Tuy nhiên, filter, entry point, form login, reverse proxy và giao thức token có thể thay đổi cách biểu diễn. Không suy ra nguyên nhân chính xác chỉ từ một status code.

Đặc biệt, `AccessDeniedException` phát sinh khi đánh giá quyền; nếu request chưa được xác thực hoặc là anonymous, Spring Security có thể **bắt đầu quy trình xác thực** thay vì luôn trả 403.

## 6. Spring Security đưa exception ra HTTP như thế nào?

Có ba điểm mở rộng quan trọng:

### `AuthenticationEntryPoint`

Khởi động một cơ chế xác thực khi request cần xác thực. Với HTTP Basic, `BasicAuthenticationEntryPoint` thường trả HTTP 401 cùng `WWW-Authenticate` challenge; với form login có thể redirect sang trang đăng nhập.

### `AuthenticationFailureHandler`

Các filter xác thực như form-login filter có thể trực tiếp bắt authentication failure và gọi handler. Handler quyết định route, response, message hoặc redirect tùy ứng dụng. Vì vậy, **không phải mọi lỗi đăng nhập đều đi qua `ExceptionTranslationFilter`**.

### `ExceptionTranslationFilter` và `AccessDeniedHandler`

`ExceptionTranslationFilter` dịch các `AuthenticationException`/`AccessDeniedException` phát sinh từ phần **downstream** của filter chain sang đường xử lý HTTP thích hợp:

```text
ExceptionTranslationFilter
       |
       +-- AuthenticationException --> AuthenticationEntryPoint
       |
       +-- AccessDeniedException
                    |
                    +-- Chưa xác thực/anonymous --> AuthenticationEntryPoint
                    |
                    +-- Đã xác thực -----------> AccessDeniedHandler
```

Filter này **không tự kiểm tra password**; một filter như `BasicAuthenticationFilter` có đường xử lý authentication failure riêng và có thể gọi `AuthenticationEntryPoint` trực tiếp.

### Vì sao `@RestControllerAdvice` có thể không bắt được lỗi?

Security filter xử lý request trước MVC controller. Nhiều lỗi authentication xảy ra ở filter chain và được xử lý trước khi vào controller, nên `@ExceptionHandler(AuthenticationException.class)` trong `@RestControllerAdvice` không phải cách thay thế toàn bộ bảo mật web. Cần chọn `AuthenticationEntryPoint`, `AuthenticationFailureHandler` hoặc `AccessDeniedHandler` phù hợp với nguồn lỗi. Controller advice vẫn có vai trò với exception trong MVC khi thực sự thuộc phạm vi MVC.

## 7. Ví dụ Java 17+ chạy được: quan sát trực tiếp bốn trạng thái

Ví dụ dùng Spring Boot Servlet với dependency **Spring Web** và **Spring Security**. Để nhận thấy các class exception thực sự, `CommandLineRunner` gọi trực tiếp `AuthenticationManager.authenticate(...)` rồi chỉ in loại lỗi. Một `SecurityFilterChain` HTTP Basic giúp quan sát mã phản hồi ngoài web.

Tạo dự án Spring Initializr Java 17+ tương thích với Spring Boot đang sử dụng, rồi tạo file `src/main/java/com/example/autherrors/AuthErrorsApplication.java`:

```java
package com.example.autherrors;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthErrorsApplication.class, args);
    }

    @Bean
    CommandLineRunner showFailures(AuthenticationManager manager) {
        return args -> {
            check(manager, "active", "demo-pass", "valid");
            check(manager, "active", "wrong", "wrong-password");
            check(manager, "unknown", "demo-pass", "unknown-user");
            check(manager, "disabled", "demo-pass", "disabled-user");
            check(manager, "locked", "demo-pass", "locked-user");
            check(manager, "expired", "demo-pass", "expired-account");
            check(manager, "stale", "demo-pass", "expired-credential");
        };
    }

    private static void check(AuthenticationManager manager,
                              String username,
                              String password,
                              String label) {
        try {
            Authentication result = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password));
            System.out.println(label + " -> AUTHENTICATED:"
                    + result.getName());
        } catch (AuthenticationException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }
}

@Configuration(proxyBeanMethods = false)
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");

        UserDetails active = User.withUsername("active")
                .password(hash).roles("USER").build();

        UserDetails disabled = User.withUsername("disabled")
                .password(hash).roles("USER")
                .disabled(true).build();

        UserDetails locked = User.withUsername("locked")
                .password(hash).roles("USER")
                .accountLocked(true).build();

        UserDetails expired = User.withUsername("expired")
                .password(hash).roles("USER")
                .accountExpired(true).build();

        UserDetails stale = User.withUsername("stale")
                .password(hash).roles("USER")
                .credentialsExpired(true).build();

        return new InMemoryUserDetailsManager(
                active, disabled, locked, expired, stale);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http,
                              AuthenticationManager manager)
            throws Exception {
        return http
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "principal=" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }
}
```

### Vai trò của từng phần

- `UserDetailsService` chứa năm tài khoản demo. Một tài khoản hoạt động và bốn tài khoản có lỗi trạng thái riêng.
- `PasswordEncoder` dùng BCrypt; các tài khoản có cùng mật khẩu học tập nhưng thực tế tuyệt đối không dùng mật khẩu chung mặc định.
- `DaoAuthenticationProvider` đọc user, kiểm tra các cờ và so khớp credential theo cơ chế chuẩn.
- `ProviderManager` gọi provider đó; một exception phát ra từ authentication làm lần xác thực thất bại.
- `CommandLineRunner` gọi manager **trực tiếp**, nên có thể quan sát subclass trước khi được dịch thành HTTP. Demo không log password/hash/token.
- `SecurityFilterChain` dùng manager được cấu hình và bảo vệ endpoint bằng Basic; `/admin` yêu cầu `ROLE_ADMIN`, trong khi mọi user demo chỉ có `ROLE_USER`.

Điều kiện demo được xây sao cho mỗi user chỉ có **một** lỗi trạng thái, tránh phụ thuộc thứ tự ưu tiên khi nhiều cờ sai đồng thời.

### Chạy bằng build tool

Với project Gradle dùng wrapper:

```bash
./gradlew bootRun
```

Với Maven:

```bash
./mvnw spring-boot:run
```

Trên PowerShell dùng `.\gradlew.bat bootRun` hoặc `.\mvnw.cmd spring-boot:run`. Vì file phụ thuộc Spring Boot/Spring Security, không thể biên dịch bằng lệnh `javac` đơn thuần mà thiếu classpath/dependency.

Sau khi ứng dụng khởi động, ngoài các log Spring Boot, `CommandLineRunner` dự kiến in:

```text
valid -> AUTHENTICATED:active
wrong-password -> BadCredentialsException
unknown-user -> BadCredentialsException
disabled-user -> DisabledException
locked-user -> LockedException
expired-account -> AccountExpiredException
expired-credential -> CredentialsExpiredException
```

Kết quả này dựa trên `DaoAuthenticationProvider` với cài đặt mặc định che `UsernameNotFoundException`. Nếu đổi provider, custom checker hay chính sách che user, loại exception có thể khác.

### Kiểm thử qua HTTP

Trong một terminal khác:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u active:demo-pass http://localhost:8080/me
curl -i http://localhost:8080/me
curl -i -u active:wrong http://localhost:8080/me
curl -i -u disabled:demo-pass http://localhost:8080/me
curl -i -u locked:demo-pass http://localhost:8080/me
curl -i -u active:demo-pass http://localhost:8080/admin
```

Nếu PowerShell ánh xạ `curl` thành lệnh khác, dùng `curl.exe`. Trong ứng dụng này:

| Lệnh | Kết quả quan sát |
| --- | --- |
| `/public/ping` anonymous | Body `pong` |
| `/me` với credential hợp lệ | Body `principal=active` |
| `/me` thiếu credential | HTTP 401 |
| `/me` với password sai | HTTP 401 |
| `/me` với disabled/locked | HTTP 401 |
| `/admin` với `active` có `ROLE_USER` | HTTP 403 |

Header và body lỗi phụ thuộc Spring Boot/Spring Security/version/cấu hình, nên không dựa vào một chuỗi cụ thể ngoài status và nội dung của hai endpoint thành công. Với HTTP Basic, `WWW-Authenticate` thường đi kèm 401. Basic chỉ dùng Base64, **không mã hóa bí mật**; môi trường thật phải dùng HTTPS.

**Đối chiếu hai mức quan sát:** ở backend, `disabled-user` là `DisabledException`; ở client Basic, nó thường là 401. Hai dữ kiện không mâu thuẫn: backend phân loại nguyên nhân, còn HTTP endpoint áp chính sách thông báo.

## 8. Chuyển trạng thái từ database thành `UserDetails` đúng nghĩa

Ví dụ dùng cờ cố định. Ứng dụng thực có thể lưu các trường:

```text
users:
  user_id
  username
  password_hash
  enabled
  locked_until
  account_expires_at
  credentials_expires_at
```

Một bộ chuyển đổi cần xác định `UserDetails` từ nguồn **được quản lý phía server**. Với một chính sách thời gian minh họa, logic:

```java
boolean enabled = user.isEnabled();
boolean accountNonLocked =
        user.getLockedUntil() == null
                || !now.isBefore(user.getLockedUntil());
boolean accountNonExpired =
        user.getAccountExpiresAt() == null
                || now.isBefore(user.getAccountExpiresAt());
boolean credentialsNonExpired =
        user.getCredentialsExpiresAt() == null
                || now.isBefore(user.getCredentialsExpiresAt());
```

Đây là **mảnh mã thiết kế** chứ không phải chương trình tự biên dịch: cần entity `user`, `now` và contract thời gian. Với cờ khóa **vĩnh viễn**, chỉ `locked_until` là chưa đủ; cần thêm trạng thái khóa tương ứng. `now` nên đến từ `Clock` hoặc nguồn thời gian nhất quán. Cần định nghĩa rõ tính chất biên `expires_at` và múi giờ.

Không dùng `isAccountNonLocked()` để trả nguyên cờ `locked` từ DB; tên method phủ định của trạng thái lỗi.

### Account state có hiệu lực khi nào?

Thông thường trạng thái trong `UserDetails` được kiểm tra **khi xác thực**. Một session đã được tạo có thể giữ `Authentication` cũ. Nếu admin khóa tài khoản sau login, session cũ **không tự biến mất chỉ vì cờ `enabled` đã thay đổi trong DB**.

Để trạng thái khóa/disable có hiệu lực đúng hạn, hệ thống có thể cần:

- Vô hiệu hóa session hiện tại hoặc yêu cầu đăng nhập lại.
- Token TTL phù hợp, revocation/rotation/introspection.
- Chính sách kiểm tra trạng thái hiện hành ở thao tác rủi ro cao.
- Kiểm soát user cache và propagation giữa các instance.
- Kiểm thử cả request mới và session/token đã tồn tại trước sự kiện khóa.

Việc có `LockedException` trong một lần login mới không đảm bảo mọi request từ session cũ bị chặn.

### Đếm lỗi đăng nhập phải được thiết kế như một quy trình riêng

Nếu cần khóa sau nhiều lần sai, phải xác định key đếm (user/IP/thiết bị), cửa sổ thời gian, cập nhật atomic/transactional, giới hạn tốc độ, mở khóa và tránh dùng thông tin sai để dò username. Hệ thống phân tán không thể dựa vào bộ đếm trong bộ nhớ của một instance khi cần trạng thái nhất quán.

Cẩn thận: `BadCredentialsException` cũng có thể đến từ **username không tồn tại** sau bước che lỗi. Không tự động suy ra rằng có một user thực cần tăng counter chỉ từ tên exception.

## 9. Chính sách phản hồi và phòng chống lộ thông tin user

Một API có thể trả lỗi xác thực chung, ví dụ:

```json
{
  "error": "authentication_failed",
  "message": "Không thể xác thực yêu cầu."
}
```

Đây là **mẫu chính sách** của ứng dụng, không phải nội dung mặc định từ framework. Với Basic, cần có status/challenge phù hợp; với form login thì có thể redirect/failure handler; với OAuth2 Resource Server cần tuân giao thức token.

### User enumeration là gì?

Nếu `POST /login` trả “không có username này” cho An nhưng “tài khoản đang khóa” cho Bình, người chưa xác thực có thể lập danh sách tài khoản hợp lệ. Rủi ro còn đến từ thời gian phản hồi khác nhau, payload không đồng nhất hoặc lỗi SQL/backend bị lộ.

Một chiến lược:

1. **Bên ngoài:** thông báo trung lập, không tiết lộ password đúng/sai hay trạng thái tài khoản nếu chưa có xác minh phù hợp.
2. **Bên trong:** ghi loại lỗi, request ID/correlation ID, nguồn provider và trạng thái để hỗ trợ điều tra; không log password hoặc token.
3. **Khôi phục tài khoản:** dùng quy trình đã xác minh quyền sở hữu; có thể cung cấp chi tiết hơn trong kênh đã tin cậy.
4. **Chống lạm dụng:** giới hạn tốc độ, giám sát bất thường, xử lý brute force và credential stuffing.
5. **Bảo mật credential:** HTTPS, password hashing chuẩn, không ghi raw Authorization header/session cookie.

Không nhất thiết che mọi trạng thái trong mọi ngữ cảnh. Ví dụ, sau khi đã kiểm chứng bằng phương thức độc lập, có thể chỉ dẫn người dùng đổi credential. Nhưng endpoint login public không nên mặc định tiết lộ nguyên văn `LockedException` hay `UsernameNotFoundException`.

### Tùy biến Basic entry point nếu trả JSON

Trong cấu hình `HttpSecurity`, có thể thay `.httpBasic(Customizer.withDefaults())` bằng:

```java
.httpBasic(basic -> basic.authenticationEntryPoint((request, response, ex) -> {
    response.setStatus(401);
    response.setHeader("WWW-Authenticate", "Basic realm=\"api\"");
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write("{\"error\":\"authentication_failed\"}");
}))
```

Đây là **mảnh DSL minh họa**, không phải chương trình độc lập. Header `WWW-Authenticate` giữ yêu cầu challenge của HTTP Basic. Tránh trực tiếp đưa `ex.getMessage()` vào JSON công khai vì thông điệp nội bộ có thể chứa thông tin tài khoản hoặc hạ tầng.

### Lỗi dịch vụ không nên bị nhầm thành sai password

`AuthenticationServiceException` hoặc `InternalAuthenticationServiceException` phản ánh sự cố xử lý ở dịch vụ xác thực. Nếu database lỗi, cần ghi nhận vận hành và áp chính sách phản hồi phù hợp, chứ không mặc định kết luận mọi client “nhập sai”. Một API tùy biến có thể chọn trạng thái 503 khi dịch vụ tạm không khả dụng, nhưng **không có mapping HTTP 503 mặc định cố định** cho toàn bộ các exception này.

## 10. Theo dõi sự kiện và vị trí xử lý

Để tìm nguyên nhân, hỏi lần lượt:

- Request có credential chưa, filter tương ứng có nhận không?
- `AuthenticationManager` có provider hỗ trợ loại token này không?
- `UserDetailsService` hoặc nguồn IDP có tìm được user và có hoạt động không?
- Checker có từ chối vì disabled/locked/expired không?
- Mật khẩu/token có được xác minh bằng cơ chế phù hợp không?
- `Authentication` có được trả thành công và đặt vào `SecurityContext` không?
- Nếu đã thành công, authorization có từ chối do quyền/tài nguyên không?
- Ai dịch exception sang response: Basic filter, entry point, failure handler hay exception translation filter?

### Authentication events

Spring Security cung cấp `AuthenticationEventPublisher` và `DefaultAuthenticationEventPublisher`. Khi được cấu hình và kết nối với manager phù hợp, có thể phát các sự kiện như:

| Exception | Sự kiện điển hình |
| --- | --- |
| `BadCredentialsException` | `AuthenticationFailureBadCredentialsEvent` |
| `DisabledException` | `AuthenticationFailureDisabledEvent` |
| `LockedException` | `AuthenticationFailureLockedEvent` |
| `AccountExpiredException` | `AuthenticationFailureExpiredEvent` |
| `CredentialsExpiredException` | `AuthenticationFailureCredentialsExpiredEvent` |
| `AuthenticationServiceException` | `AuthenticationFailureServiceExceptionEvent` |

Không nên giả định một `ProviderManager` được tạo thủ công luôn tự có publisher; cần xác minh wiring. Mapping sự kiện mặc định thường phân biệt class exception cụ thể, nên custom subclass có thể cần cấu hình ánh xạ bổ sung.

Telemetry nên chứa loại lỗi đã chuẩn hóa, thời điểm, request/correlation ID, provider, loại flow, quyết định từ chối và HTTP status. Không ghi plaintext password, bearer token, session cookie, password hash hoặc toàn bộ đối tượng `Authentication` vào log công khai.

## 11. Ma trận kiểm thử đúng trọng tâm

| Kịch bản | Kiểm chứng ở tầng AuthenticationManager | Kiểm chứng ở HTTP |
| --- | --- | --- |
| User hoạt động, đúng password | Trả authenticated `Authentication` | Cho phép endpoint bảo vệ |
| User hoạt động, sai password | `BadCredentialsException` | Không đăng nhập; Basic thường 401 |
| Username không tồn tại | Mặc định có thể che thành `BadCredentialsException` | Không tiết lộ user có tồn tại |
| User disabled | `DisabledException` | Không cấp phiên mới |
| User locked | `LockedException` | Không cấp phiên mới |
| Account expired | `AccountExpiredException` | Không cấp phiên mới |
| Credential expired | `CredentialsExpiredException` | Chỉ dẫn recovery qua luồng tin cậy |
| Provider thiếu | `ProviderNotFoundException` hoặc lỗi tương ứng | Không báo đăng nhập thành công |
| DB/IDP lỗi | Nhận diện service failure | Cảnh báo vận hành, response an toàn |
| Login đúng nhưng thiếu role | Authentication thành công | Authorization từ chối, thường 403 |
| Đã khóa sau khi có session | Session cũ có thể còn thông tin | Kiểm tra chính sách thu hồi thực tế |
| Dò username | So sánh username đúng/sai | Response công khai trung lập |

Khi viết test, kiểm tra **hai mặt**: exception/event nội bộ dùng để điều tra, và phản hồi công khai dùng cho client. Một hệ thống trả 401 vẫn có thể sai nếu đã cấp session trước khi kiểm tra trạng thái, hoặc vô tình ghi password vào log.

### Những lỗi hiểu nhầm thường gặp

1. **“Mọi authentication failure đều là `BadCredentialsException`.”** Không đúng; account status, service lỗi hoặc thiếu provider có loại khác.
2. **“`DisabledException` chứng tỏ password đã đúng.”** Không đúng; có thể được kiểm tra trước password.
3. **“Account expired cũng là credentials expired.”** Hai thứ có vòng đời và chính sách khác nhau.
4. **“Bật `accountLocked(true)` là framework tự đếm lỗi nhập sai.”** Không đúng; việc đếm và khóa là policy bổ sung.
5. **“`UsernameNotFoundException` luôn được trả nguyên vẹn.”** Dao provider thường che thành BadCredentialsException.
6. **“`@RestControllerAdvice` bắt mọi lỗi của security filter.”** Không đúng; lỗi filter có handler riêng.
7. **“Disable user trong database làm session cũ lập tức chết.”** Không được bảo đảm; cần lifecycle rõ.
8. **“403 luôn là lỗi xác thực.”** Không; thường là authorization failure.
9. **“Exception class phải được gửi ra browser để người dùng tự xử lý.”** Có thể gây lộ trạng thái username/account.
10. **“Dịch vụ xác thực bị lỗi nghĩa là password sai.”** Không; cần đánh giá sự cố vận hành.

### Tự kiểm tra kiến thức

**Câu 1.** Account bị disable, client nhập password sai. `DisabledException` có chứng minh password đúng không?  
**Trả lời:** Không. Trạng thái có thể được kiểm tra trước password.

**Câu 2.** Vì sao username không tồn tại có thể xuất hiện dưới dạng `BadCredentialsException`?  
**Trả lời:** `DaoAuthenticationProvider` thường che `UsernameNotFoundException` để tránh dò user.

**Câu 3.** `isCredentialsNonExpired() == false` tương ứng với exception nào?  
**Trả lời:** `CredentialsExpiredException` trong checker chuẩn.

**Câu 4.** User có `ROLE_USER` gọi `/admin` đòi `ROLE_ADMIN` và bị từ chối. Đây là `BadCredentialsException` sao?  
**Trả lời:** Không. Login có thể đã thành công; đây là authorization failure.

**Câu 5.** Muốn trả 401 JSON cho HTTP Basic, nên tùy biến ở đâu?  
**Trả lời:** `AuthenticationEntryPoint` của Basic, đồng thời giữ Basic challenge phù hợp.

**Câu 6.** Tại sao không nên trả chính xác loại `LockedException` cho mọi client chưa đăng nhập?  
**Trả lời:** Vì nó có thể tiết lộ tài khoản tồn tại và trạng thái của tài khoản.

**Câu 7.** User bị khóa sau khi đã có phiên đăng nhập. Có chắc phiên cũ tự bị vô hiệu hóa?  
**Trả lời:** Không. Cần chiến lược quản lý session/token, cache và chính sách cập nhật trạng thái.

## 12. Ghi nhớ cốt lõi

`AuthenticationException` mô tả **vì sao yêu cầu chưa xác thực được**. Các subclass của `AccountStatusException` phân biệt **tài khoản bị vô hiệu hóa, bị khóa, hết hạn hoặc credential hết hạn**. `BadCredentialsException` thường báo bằng chứng không hợp lệ; `AuthenticationServiceException` phản ánh sự cố xử lý; `AccessDeniedException` khác nhóm vì liên quan quyền sau khi nhận diện.

Thiết kế đúng gồm ba lớp trách nhiệm: **nguồn trạng thái tin cậy**, **provider kiểm tra và phát Authentication/exception đúng**, và **web handler trả response phù hợp mà không làm lộ thông tin user**. Ngoài ra phải quản lý session/token đã tồn tại và luồng khôi phục tài khoản. Một exception đúng tên chưa thể thay thế toàn bộ chính sách bảo mật.

### Tài liệu chính thức

- [Spring Security — AuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [Spring Security — AccountStatusException API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AccountStatusException.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security — Security Filters/ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html)