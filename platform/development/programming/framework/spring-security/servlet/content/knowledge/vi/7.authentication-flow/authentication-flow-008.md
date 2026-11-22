# AuthenticationException và các trạng thái tài khoản không hợp lệ

> **Phạm vi:** Spring Security 6 trên **Servlet stack** (Spring Boot 3.x, Java 17+). Bài này giải thích cơ chế báo lỗi xác thực qua `AuthenticationException`, các trạng thái tài khoản trong `UserDetails`, quá trình kiểm tra của `DaoAuthenticationProvider`, và cách lỗi được chuyển thành phản hồi HTTP trong form login, HTTP Basic hoặc luồng đăng nhập tùy chỉnh. Phân biệt rõ lỗi **không xác thực được danh tính** với lỗi **không đủ quyền truy cập**.

## 1. Authentication thất bại không đồng nghĩa chỉ sai mật khẩu

Khi ứng dụng nhận username/password, hệ thống có thể không cho đăng nhập vì nhiều nguyên nhân:

- Sai mật khẩu, username không tồn tại hoặc thông tin xác thực không hợp lệ.
- Tài khoản **bị khóa** (`locked`), ví dụ bị khóa theo chính sách bảo mật.
- Tài khoản **bị vô hiệu hóa** (`disabled`), ví dụ chưa kích hoạt hoặc bị quản trị viên tắt.
- **Tài khoản hết hạn** (`account expired`), dù mật khẩu có thể vẫn đúng.
- **Thông tin xác thực hết hạn** (`credentials expired`), ví dụ chính sách buộc đổi mật khẩu.
- Không có provider hỗ trợ token xác thực, hoặc dịch vụ tra cứu danh tính bị lỗi.

Spring Security biểu diễn những tình huống này bằng những lớp kế thừa `org.springframework.security.core.AuthenticationException`. Ngoại lệ có thể mang thông tin chi tiết cho tầng nội bộ, nhưng **không nên tự động công khai nguyên văn cho client**: việc cho biết “tài khoản tồn tại nhưng bị khóa” có thể hỗ trợ kẻ tấn công dò tài khoản.

Điểm quan trọng: một chuỗi như “đăng nhập thất bại” là **kết quả nghiệp vụ**, còn `AuthenticationException` là **tín hiệu kỹ thuật** để cơ chế xác thực và HTTP security xử lý thất bại.

## 2. Các ngoại lệ quan trọng và ý nghĩa

`AuthenticationException` là lớp ngoại lệ gốc cho lỗi xác thực của Spring Security (unchecked exception). Một số nhánh thường gặp:

```text
AuthenticationException
├── BadCredentialsException
├── UsernameNotFoundException
├── AuthenticationCredentialsNotFoundException
├── InsufficientAuthenticationException
├── ProviderNotFoundException
├── AuthenticationServiceException
│   └── InternalAuthenticationServiceException
└── AccountStatusException
    ├── LockedException
    ├── DisabledException
    ├── AccountExpiredException
    └── CredentialsExpiredException
```

Đây là **những nhánh tiêu biểu**, không phải toàn bộ lớp con trong thư viện.

| Lớp ngoại lệ | Ý nghĩa chính | Ví dụ |
| --- | --- | --- |
| `BadCredentialsException` | Credentials được cung cấp không được chấp nhận | Sai password, hoặc username không tồn tại nhưng được che giấu |
| `UsernameNotFoundException` | `UserDetailsService` không tìm được người dùng | `loadUserByUsername("missing")` không tìm thấy dữ liệu |
| `LockedException` | Tài khoản đang bị khóa | `UserDetails.isAccountNonLocked() == false` |
| `DisabledException` | Tài khoản chưa được bật/đã bị vô hiệu hóa | `UserDetails.isEnabled() == false` |
| `AccountExpiredException` | Thời hạn sử dụng tài khoản đã hết | `UserDetails.isAccountNonExpired() == false` |
| `CredentialsExpiredException` | Credentials của tài khoản đã hết hạn | `UserDetails.isCredentialsNonExpired() == false` |
| `AuthenticationCredentialsNotFoundException` | Không tìm thấy authentication phù hợp trong ngữ cảnh khi nó được yêu cầu | Một đường gọi yêu cầu credentials nhưng chưa có context phù hợp |
| `InsufficientAuthenticationException` | Mức độ xác thực hiện tại chưa đủ cho thao tác | Cơ chế yêu cầu xác thực mạnh hơn, tùy cấu hình |
| `ProviderNotFoundException` | Không có `AuthenticationProvider` nào hỗ trợ token được gửi | `ProviderManager` nhận loại `Authentication` không provider nào hỗ trợ |
| `AuthenticationServiceException` / `InternalAuthenticationServiceException` | Trục trặc xử lý ở hạ tầng xác thực | User store lỗi, truy vấn danh tính thất bại, provider không thể hoàn thành |

**Đừng gộp lỗi hạ tầng vào “password sai” khi chẩn đoán nội bộ.** Với client, có thể dùng thông báo an toàn và không tiết lộ chi tiết, nhưng log/metrics nội bộ cần phân biệt lỗi dịch vụ với thông tin đăng nhập không hợp lệ.

### Nhánh AccountStatusException

Bốn ngoại lệ `LockedException`, `DisabledException`, `AccountExpiredException` và `CredentialsExpiredException` đều thuộc `AccountStatusException`. Chúng cho biết **trạng thái tài khoản không thỏa chính sách**, khác với `BadCredentialsException` cho việc kiểm tra credentials.

Nếu cần bắt chung để xử lý theo nhóm trong một service nội bộ:

```java
try {
    Authentication result = authenticationManager.authenticate(requestToken);
    // Xử lý sau khi có Authentication thành công.
} catch (AccountStatusException exception) {
    // Tài khoản bị khóa, tắt, hết hạn tài khoản hoặc credentials.
} catch (BadCredentialsException exception) {
    // Credentials không hợp lệ hoặc người dùng không được tìm thấy theo policy che giấu.
} catch (AuthenticationServiceException exception) {
    // Lỗi hạ tầng / dịch vụ xác thực: cần telemetry và xử lý sự cố.
}
```

Đây là **đoạn minh họa bên trong một phương thức**, không phải chương trình Java độc lập; `requestToken` là `Authentication` chưa xác thực, và `authenticationManager` là dependency đã được cung cấp. Trong mã thực tế, mỗi `catch` phải quyết định việc trả lỗi/điều hướng phù hợp, đồng thời giữ nguyên các quy tắc bảo mật.

## 3. Bốn trạng thái UserDetails mà DAO provider kiểm tra

Spring Security mô tả khả năng đăng nhập của một tài khoản qua `UserDetails`, gồm bốn cờ:

| Cờ `UserDetails` | Giá trị cho phép đăng nhập | Khi `false`, lỗi điển hình |
| --- | --- | --- |
| `isAccountNonLocked()` | `true` | `LockedException` |
| `isEnabled()` | `true` | `DisabledException` |
| `isAccountNonExpired()` | `true` | `AccountExpiredException` |
| `isCredentialsNonExpired()` | `true` | `CredentialsExpiredException` |

Tên thuộc tính đôi khi dễ gây nhầm: `isAccountNonLocked() == true` nghĩa là **không bị khóa**, còn `isCredentialsNonExpired() == false` nghĩa là **credentials đã hết hạn**. Các boolean này là trạng thái do **ứng dụng/UserDetailsService** cung cấp; Spring Security không tự quyết định ngày nào tài khoản hoặc mật khẩu hết hạn nếu bạn chưa xây dựng dữ liệu/quy tắc tương ứng.

Ví dụ chuyển trạng thái từ dữ liệu ứng dụng sang `UserDetails`:

```java
UserDetails principal = User.withUsername("han")
        .password(passwordEncoder.encode("study123"))
        .roles("USER")
        .accountLocked(true)
        .build();
```

Đây là một đoạn minh họa trong môi trường có `PasswordEncoder` và `User` của Spring Security. Tài khoản `han` bị khóa cho tới khi logic quản trị thay đổi dữ liệu trạng thái; encoder chỉ xử lý mật khẩu, **không** quyết định mở khóa.

### Thứ tự kiểm tra trong DaoAuthenticationProvider

Đối với phương thức xác thực username/password qua `DaoAuthenticationProvider`, luồng điển hình là:

1. `AuthenticationManager` chọn provider hỗ trợ `UsernamePasswordAuthenticationToken`.
2. `DaoAuthenticationProvider` nhờ `UserDetailsService.loadUserByUsername(...)` lấy `UserDetails`.
3. `AbstractUserDetailsAuthenticationProvider` chạy **pre-authentication checks**: tài khoản chưa bị khóa, đang enabled, tài khoản chưa hết hạn. Nếu check sai, ném `LockedException`, `DisabledException` hoặc `AccountExpiredException`.
4. Provider kiểm tra password được cung cấp với password hash theo `PasswordEncoder.matches(...)`. Sai password dẫn tới `BadCredentialsException`.
5. Chạy **post-authentication check** cho credentials chưa hết hạn. Nếu sai, ném `CredentialsExpiredException`.
6. Chỉ khi mọi kiểm tra thành công, provider tạo/trả `Authentication` đã xác thực, với principal và authorities phù hợp.

```text
UsernamePasswordAuthenticationToken (chưa authenticated)
            |
            v
        ProviderManager
            |
            v
   DaoAuthenticationProvider
            |
   UserDetailsService.loadUserByUsername(...)
            |
   +--> Unknown username? --> thường BadCredentialsException ra ngoài
            |
   +--> Locked?          --> LockedException
   +--> Disabled?        --> DisabledException
   +--> Account expired? --> AccountExpiredException
            |
   PasswordEncoder.matches(rawPassword, encodedPassword)
            |
   +--> Mismatch?        --> BadCredentialsException
            |
   Credentials expired?  --> CredentialsExpiredException
            |
            v
    Authentication thành công
```

**Thứ tự có ý nghĩa:** trong `DaoAuthenticationProvider` mặc định, kiểm tra khóa/tắt/hết hạn tài khoản diễn ra **trước** việc xác thực password; kiểm tra credentials hết hạn diễn ra **sau** bước kiểm tra password. Vì vậy một tài khoản vừa khóa vừa nhập sai password có thể ném `LockedException`. Không nên suy luận rằng ngoại lệ đầu tiên luôn xác nhận người gọi đã biết password.

Luồng này mô tả provider DAO tiêu chuẩn; custom `AuthenticationProvider`, LDAP, OAuth2, MFA hoặc cấu hình checks tùy chỉnh có thể có quy tắc khác.

## 4. Vì sao UsernameNotFoundException thường bị đổi thành BadCredentialsException?

`UserDetailsService.loadUserByUsername(...)` có thể ném `UsernameNotFoundException` khi không tìm thấy username. Tuy nhiên, `AbstractUserDetailsAuthenticationProvider` mặc định bật `hideUserNotFoundExceptions`, nên ở ranh giới xác thực nó thường chuyển lỗi này thành `BadCredentialsException`.

Hai trường hợp:

```text
Input: username=han, password=SaiMatKhau
    -> user tồn tại nhưng PasswordEncoder.matches(...) == false
    -> BadCredentialsException

Input: username=khongTonTai, password=BatKy
    -> UserDetailsService ném UsernameNotFoundException
    -> provider che giấu thông tin tồn tại tài khoản
    -> BadCredentialsException
```

Cách che giấu giúp client khó phân biệt “username sai” với “password sai”. Ngay cả khi provider giữ ngoại lệ nội bộ riêng, **thông báo trả ra ngoài vẫn nên chung**, ví dụ “Thông tin đăng nhập không hợp lệ”. Nếu cần nhắc người dùng đang bị khóa, phải thiết kế luồng khôi phục an toàn, xác minh danh tính và hạn chế dò tài khoản.

Đừng bật `setHideUserNotFoundExceptions(false)` chỉ để hiển thị thông báo “username không tồn tại” cho client. Nếu cần điều tra dữ liệu, dùng telemetry server-side và chính sách kiểm soát truy cập log.

## 5. AuthenticationException khác AccessDeniedException thế nào?

Cùng một endpoint được bảo vệ có thể từ chối request ở **hai giai đoạn**:

- **Authentication:** hệ thống chưa thiết lập được danh tính đủ điều kiện. `AuthenticationException` xuất hiện từ quá trình đăng nhập hoặc thiếu authentication cần thiết.
- **Authorization:** danh tính đã được xác thực nhưng không được cấp quyền để làm việc được yêu cầu. `AccessDeniedException` thuộc nhánh authorization, **không phải** lớp con của `AuthenticationException`.

| Tình huống | Loại xử lý chủ yếu | HTTP thường thấy (phụ thuộc cấu hình) |
| --- | --- | --- |
| Chưa có credentials cho API dùng HTTP Basic | Yêu cầu xác thực qua `AuthenticationEntryPoint` | **401** với `WWW-Authenticate` |
| Username/password sai hoặc account status không hợp lệ trong HTTP Basic | Authentication failure, đi qua entry point phù hợp | **401** |
| Form login sai password | `AuthenticationFailureHandler` xử lý | Redirect về trang lỗi hoặc phản hồi cấu hình riêng |
| Đã đăng nhập nhưng thiếu role cho URL | `AccessDeniedException`, `AccessDeniedHandler` | **403** |
| Request POST vi phạm CSRF | Từ chối ở filter CSRF | Thường **403**, kể cả chưa qua controller |
| Provider hoặc user store lỗi hệ thống | Lỗi xác thực hạ tầng | Tùy framework/handler; không nên mặc định coi là password sai |

**Không thể suy ra chỉ từ tên ngoại lệ rằng mọi ứng dụng sẽ trả cùng một HTTP status.** Form login có thể redirect; HTTP Basic thường trả 401; custom REST controller tự catch rồi trả status riêng. Mặt khác `ExceptionTranslationFilter` có thể xử lý `AuthenticationException` hoặc `AccessDeniedException` phát sinh ở phía downstream của nó, đưa request tới entry point/denied handler; `BasicAuthenticationFilter` cũng có đường xử lý authentication failure riêng.

Một quy tắc thực dụng: **401** nghĩa là cần credentials phù hợp để xác thực cho tài nguyên; **403** nghĩa là server từ chối request trong chính sách hiện tại (thường do thiếu quyền hoặc CSRF). Đây là cách diễn giải phổ biến, **không phải phép ánh xạ một-một** của từng lớp Java với mã HTTP.

## 6. Ví dụ Spring Boot chạy được: từng trạng thái tài khoản và ngoại lệ

Ví dụ sử dụng **Java 17+, Spring Boot 3.3.5, Spring Security 6.x, Gradle 8.5**. Chúng ta tạo năm tài khoản trong bộ nhớ có cùng mật khẩu thử nghiệm để cô lập nguyên nhân lỗi: một tài khoản bình thường, một bị khóa, một disabled, một hết hạn account và một hết hạn credentials.

Ứng dụng có `GET /public` và `GET /me`. Với HTTP Basic, endpoint `/me` chỉ trả về username khi người dùng qua được authentication. Test vừa kiểm tra **loại ngoại lệ Java từ AuthenticationManager**, vừa kiểm tra **HTTP 401 an toàn** cho các account không hợp lệ.

### 6.1. Cấu trúc dự án

```text
account-status-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    AuthenticationStatusTest.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'account-status-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

### 6.2. Lớp khởi động

Tệp `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 6.3. Cấu hình xác thực và năm tài khoản

Tệp `src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String encodedPassword = encoder.encode("study123");

        UserDetails active = User.withUsername("active")
                .password(encodedPassword)
                .roles("USER")
                .build();

        UserDetails locked = User.withUsername("locked")
                .password(encodedPassword)
                .roles("USER")
                .accountLocked(true)
                .build();

        UserDetails disabled = User.withUsername("disabled")
                .password(encodedPassword)
                .roles("USER")
                .disabled(true)
                .build();

        UserDetails accountExpired = User.withUsername("accountExpired")
                .password(encodedPassword)
                .roles("USER")
                .accountExpired(true)
                .build();

        UserDetails credentialsExpired = User.withUsername("credentialsExpired")
                .password(encodedPassword)
                .roles("USER")
                .credentialsExpired(true)
                .build();

        return new InMemoryUserDetailsManager(
                active, locked, disabled, accountExpired, credentialsExpired);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager) throws Exception {
        http.authenticationManager(manager);

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

`DaoAuthenticationProvider` nhận `UserDetailsService` và `PasswordEncoder` rõ ràng. Việc công khai `AuthenticationManager` như một bean cho phép cùng một cấu hình được dùng ở HTTP security chain và trong test. Constructor mặc định của `DaoAuthenticationProvider` có trong dòng Spring Security dùng ở ví dụ; với các phiên bản mới hơn, nên đối chiếu API constructor thích hợp của phiên bản đã chọn.

**Ý nghĩa các account:**

| Username | Cờ đặc biệt | Kết quả xác thực với password `study123` |
| --- | --- | --- |
| `active` | Mọi trạng thái hợp lệ | Thành công |
| `locked` | `accountLocked(true)` | `LockedException` |
| `disabled` | `disabled(true)` | `DisabledException` |
| `accountExpired` | `accountExpired(true)` | `AccountExpiredException` |
| `credentialsExpired` | `credentialsExpired(true)` | `CredentialsExpiredException` |

`User.UserBuilder` hỗ trợ các method diễn đạt trạng thái **tiêu cực** (`disabled(true)`, `accountLocked(true)`, ...), trong khi các getter trên `UserDetails` dùng tên **tích cực** (`isEnabled()`, `isAccountNonLocked()`, ...). Đây là sự khác biệt về tên method cần chú ý.

Mật khẩu `study123` chỉ dùng cho demo cục bộ. Trên hệ thống thật, cần lưu hash mật khẩu an toàn, quản lý bí mật, thực hiện rate limit/lockout phù hợp, không hard-code tài khoản và sử dụng HTTPS.

### 6.4. Controller

Tệp `src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String currentUser(Authentication authentication) {
        return authentication.getName();
    }
}
```

`/public` được cấp quyền công khai. `/me` phải có authentication phù hợp mới đến controller; từ đó có thể quan sát tài khoản nào vượt qua các kiểm tra.

### 6.5. Kiểm thử AuthenticationManager và HTTP Basic

Tệp `src/test/java/demo/AuthenticationStatusTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationStatusTest {

    @Autowired
    AuthenticationManager manager;

    @Autowired
    MockMvc mvc;

    private Authentication authenticate(String username, String password) {
        return manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password));
    }

    @Test
    void activeUserAuthenticatesSuccessfully() {
        Authentication result = authenticate("active", "study123");
        assertEquals(true, result.isAuthenticated());
        assertEquals("active", result.getName());
    }

    @Test
    void lockedAccountThrowsLockedException() {
        assertThrows(LockedException.class,
                () -> authenticate("locked", "study123"));
    }

    @Test
    void disabledAccountThrowsDisabledException() {
        assertThrows(DisabledException.class,
                () -> authenticate("disabled", "study123"));
    }

    @Test
    void expiredAccountThrowsAccountExpiredException() {
        assertThrows(AccountExpiredException.class,
                () -> authenticate("accountExpired", "study123"));
    }

    @Test
    void expiredCredentialsThrowsCredentialsExpiredException() {
        assertThrows(CredentialsExpiredException.class,
                () -> authenticate("credentialsExpired", "study123"));
    }

    @Test
    void wrongPasswordAndMissingUsernameBothThrowBadCredentials() {
        assertThrows(BadCredentialsException.class,
                () -> authenticate("active", "wrong-password"));

        assertThrows(BadCredentialsException.class,
                () -> authenticate("doesNotExist", "study123"));
    }

    @Test
    void httpBasicDoesNotExposeInvalidAccountStates() throws Exception {
        for (String username : new String[] {
                "locked", "disabled", "accountExpired", "credentialsExpired"
        }) {
            mvc.perform(get("/me").with(httpBasic(username, "study123")))
                    .andExpect(status().isUnauthorized());
        }
    }

    @Test
    void httpBasicSeparatesAnonymousAndValidUser() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));

        mvc.perform(get("/me"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("active", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("active"));
    }
}
```

**Kết quả kỳ vọng với cấu hình này:** 8 test **PASS**; hai phép thử `authenticate("active", "wrong-password")` và `authenticate("doesNotExist", ...)` đều ném `BadCredentialsException`. Bốn trạng thái account phát sinh đúng ngoại lệ riêng ở API Java nhưng cùng trả **401** qua HTTP Basic trong ví dụ.

Các test HTTP đi qua Spring Security filter chain được `MockMvc` cấu hình bởi Spring Boot; không cần gửi request mạng thực tế. Không dùng `@WithMockUser` trong những bài test này vì annotation có thể đặt sẵn authentication vào context và bỏ qua bước xác thực username/password cần kiểm tra.

### 6.6. Chạy chương trình

Cài JDK 17 trở lên và Gradle tương thích, ví dụ Gradle 8.5. Chạy tại thư mục `account-status-demo`:

```bash
gradle test
gradle bootRun
```

Nếu dự án có Gradle wrapper, dùng `./gradlew test` và `./gradlew bootRun` trên macOS/Linux, hoặc `.\gradlew.bat test` và `.\gradlew.bat bootRun` trên Windows PowerShell.

Ở terminal khác, lần lượt chạy:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u active:study123 http://localhost:8080/me
curl -i -u locked:study123 http://localhost:8080/me
curl -i -u disabled:study123 http://localhost:8080/me
curl -i -u accountExpired:study123 http://localhost:8080/me
curl -i -u credentialsExpired:study123 http://localhost:8080/me
curl -i -u doesNotExist:study123 http://localhost:8080/me
```

Với HTTP Basic mặc định trong demo, dự kiến:

| Lời gọi | HTTP status | Body khi thành công |
| --- | --- | --- |
| `GET /public` (anonymous) | **200** | `public` |
| `GET /me` (anonymous) | **401** | — |
| `GET /me` (active, password đúng) | **200** | `active` |
| `GET /me` (locked) | **401** | — |
| `GET /me` (disabled) | **401** | — |
| `GET /me` (accountExpired) | **401** | — |
| `GET /me` (credentialsExpired) | **401** | — |
| `GET /me` (username không tồn tại) | **401** | — |

Các header/body lỗi cụ thể do entry point và server tạo ra, không cần cố đoán toàn bộ chuỗi byte. **Mấu chốt:** API Java có thể phân biệt chính xác nguyên nhân để audit/khắc phục, nhưng endpoint public không nên phát thông điệp chi tiết làm lộ trạng thái account.

## 7. Khi viết đăng nhập tùy chỉnh, xử lý AuthenticationException ra sao?

Một controller/service tự gọi `AuthenticationManager` phải phân biệt **luồng thành công** và **luồng lỗi**:

```text
Request login
    |
    v
AuthenticationManager.authenticate(...)
    |
    +-- success -> Authentication hợp lệ
    |              -> áp dụng session strategy/context persistence nếu cần
    |              -> trả response thành công
    |
    +-- AuthenticationException -> không thiết lập phiên đăng nhập thành công
                                    -> ghi sự kiện/metric server-side an toàn
                                    -> trả lỗi chung theo contract public
```

Đừng viết:

```java
// SAI về mặt an ninh: vô tình coi mọi ngoại lệ là đăng nhập thành công.
try {
    Authentication authentication = manager.authenticate(token);
    SecurityContextHolder.getContext().setAuthentication(authentication);
} catch (AuthenticationException ignored) {
    return "ok";
}
```

Đoạn này chỉ minh họa anti-pattern và **không phải mã Java độc lập**. Một `catch` nuốt lỗi khiến client tưởng đã đăng nhập; nếu request trước còn context cũ thì có thể làm sai lệch trạng thái. Khi login thất bại phải tuân thủ chính sách giữ/xóa session/context cũ của hệ thống, không tự lưu authentication từ request lỗi.

Một controller JSON có thể áp dụng chiến lược:

- **Phía client:** lỗi chung như “Thông tin đăng nhập không hợp lệ hoặc tài khoản chưa thể sử dụng”, status 401 theo API contract; không trả `exception.getMessage()` hoặc tên subclass trong body public.
- **Phía server:** log có cấu trúc với mã loại lỗi nội bộ, correlation ID, username đã được chuẩn hóa/mask theo chính sách; không log password/raw token. Gắn metric để phát hiện khóa tài khoản hàng loạt hoặc hệ thống identity store gặp sự cố.
- **Lỗi hạ tầng:** phân biệt `AuthenticationServiceException` trong quan sát/alerting; tùy thiết kế, có thể trả lỗi server hoặc service unavailable thay vì cố coi là sai mật khẩu. Nếu muốn cùng một body để chống enumeration, vẫn phải đảm bảo vận hành phân biệt được sự cố.
- **Luồng khôi phục:** “quên mật khẩu”, mở khóa, kích hoạt tài khoản phải kiểm tra danh tính và giới hạn yêu cầu; đừng cấp quyền chỉ vì client gửi đúng username.

Với `formLogin` của Spring Security, `AuthenticationFailureHandler` là điểm chuẩn để xử lý sau authentication failure, thông thường redirect tới trang lỗi hoặc xử lý response riêng. Với HTTP Basic, `AuthenticationEntryPoint` thường gửi 401 và challenge. Với custom REST login, controller hoặc filter do bạn viết phải chủ động chuyển `AuthenticationException` thành phản hồi đúng contract; không mặc định mọi exception đều được `@ControllerAdvice` hoặc `ExceptionTranslationFilter` bắt ở đúng vị trí.

## 8. Trạng thái tài khoản trong cơ sở dữ liệu thực tế

Các cờ của `UserDetails` phải có **nguồn sự thật** từ ứng dụng. Một bảng người dùng có thể chứa:

```text
username
password_hash
enabled
locked_until
account_expires_at
password_changed_at
password_expires_at
```

Đây chỉ là ví dụ trường dữ liệu, không phải một schema bắt buộc của Spring Security. Logic `UserDetailsService` có thể tính:

- `isEnabled()` từ quy trình kích hoạt, vô hiệu hóa tài khoản hoặc quyết định quản trị.
- `isAccountNonLocked()` từ trạng thái khóa thủ công hoặc chính sách khóa theo thời gian; cần quy định thời điểm tự mở khóa nếu dùng `locked_until`.
- `isAccountNonExpired()` từ hạn sử dụng tài khoản, ví dụ tài khoản thời vụ.
- `isCredentialsNonExpired()` từ policy vòng đời mật khẩu, **không** lấy đơn thuần từ hạn của JWT/access token.

**Khóa do đăng nhập sai không tự có chỉ vì bạn dùng Spring Security.** Cần xây dựng bộ đếm thử sai, giới hạn tốc độ, thiết lập khóa, quản lý race condition và cơ chế khôi phục. Khi username không tồn tại, áp dụng policy chống enumeration và tránh tiết lộ trạng thái qua thời gian phản hồi nếu yêu cầu an ninh cao.

**Mật khẩu hết hạn khác token hết hạn:** `CredentialsExpiredException` trong DAO authentication thường phản ánh `UserDetails.isCredentialsNonExpired()`, không phải ngoại lệ mặc định cho JWT quá hạn. Các cơ chế OAuth2/JWT sẽ có loại lỗi token và đường xử lý khác.

### Có nên dùng AccountStatusUserDetailsChecker?

`AccountStatusUserDetailsChecker` là lớp tiện ích kiểm tra trạng thái một `UserDetails` và ném các ngoại lệ account status phù hợp. Nó hữu ích khi một provider/luồng tùy chỉnh thật sự cần cơ chế kiểm tra account status. Tuy nhiên, `DaoAuthenticationProvider` đã có các pre/post checks của nó; không cần gọi checker lần nữa trong mỗi controller như một thủ thuật “vá” đăng nhập.

Nếu viết custom `AuthenticationProvider`, bạn phải xác định **đầy đủ** bước tra cứu, kiểm tra trạng thái account, kiểm tra credentials, phản hồi lỗi và tạo `Authentication` an toàn. Không nên chỉ trả token `authenticated=true` rồi bỏ qua trạng thái tài khoản.

## 9. Lỗi dễ gặp và cách khắc phục

### 9.1. Tài khoản bị khóa nhưng HTTP response vẫn 401: có lỗi không?

Không nhất thiết. HTTP Basic dùng `AuthenticationEntryPoint` thường trả 401 cho các trạng thái không thể xác thực, kể cả locked/disabled. Client không cần biết chính xác subclass; hãy kiểm tra log/các bài test trực tiếp của `AuthenticationManager` để xác định nguyên nhân nội bộ.

### 9.2. Cấu hình có `hasRole("ADMIN")` nhưng người dùng `USER` bị 403

Đây là lỗi **authorization**: user đã đăng nhập thành công nhưng không đủ authority. Đừng gán nhầm thành `DisabledException` hay `BadCredentialsException`. Kiểm tra `GrantedAuthority` và luật `authorizeHttpRequests`/method security.

### 9.3. Đã trả 401 cho invalid credentials nhưng POST login nhận 403

Một nguyên nhân có thể là CSRF: filter CSRF chặn POST trước khi logic đăng nhập kiểm tra credentials. Cần gửi token CSRF hợp lệ trong ứng dụng dùng session/cookie, hoặc thiết kế chính sách CSRF phù hợp kiến trúc. **Không tắt CSRF toàn ứng dụng** chỉ để thông báo sai mật khẩu xuất hiện.

### 9.4. Không tìm thấy username nhưng exception là BadCredentialsException

Đây có thể là hành vi mặc định của `hideUserNotFoundExceptions` nhằm tránh lộ account tồn tại. Kiểm tra phân biệt ở log nội bộ khi được phép; không bật thông tin này trong response public.

### 9.5. Vừa password sai vừa account locked: exception nào ưu tiên?

Trong `DaoAuthenticationProvider` chuẩn, pre-auth checks cho trạng thái locked/disabled/account expired diễn ra trước password comparison, vì vậy có thể ném `LockedException` trước. Với provider khác hoặc cấu hình tùy chỉnh, thứ tự có thể thay đổi. Tuyệt đối không xem `LockedException` là bằng chứng password đúng.

### 9.6. Tài khoản credentials expired nhưng request trước đó vẫn dùng session

`CredentialsExpiredException` thuộc **giai đoạn xác thực lại bằng provider**. Một phiên đăng nhập đã được xác thực và lưu context có thể không tự gọi lại `DaoAuthenticationProvider` ở mỗi HTTP request. Nếu chính sách yêu cầu thu hồi phiên ngay khi password hết hạn, cần thêm session invalidation, revalidation hoặc cơ chế revocation; đổi một cờ trong database chưa tự động khiến mọi session hiện có thất hiệu lực.

### 9.7. Lỗi kết nối database bị hiển thị là sai mật khẩu

Đừng nuốt `InternalAuthenticationServiceException`/`AuthenticationServiceException` trong xử lý nội bộ rồi ghi metric “wrong password”. Phân loại sự cố danh tính/store riêng, tránh alert giả cho brute force và tìm đúng root cause; response public phải tránh rò rỉ thông tin nội bộ.

### 9.8. Mọi lỗi đều catch AuthenticationException rồi trả 200

Một endpoint login báo 200 trong nhánh thất bại phá vỡ contract giữa client và server, khiến UI/session logic hiểu nhầm. Dùng đúng HTTP status/redirect và failure handling; bảo đảm test có cả tài khoản hợp lệ, sai password, nonexistent, locked, disabled và expired.

## 10. Checklist QA cho luồng xác thực

1. **Password đúng và account hợp lệ:** authenticate thành công, `Authentication.isAuthenticated()` là `true`, có authorities phù hợp.
2. **Password sai và username không tồn tại:** kết quả public chung, không rò trạng thái; đường nội bộ ghi nhận loại lỗi phù hợp.
3. **Locked, disabled, account expired, credentials expired:** kiểm chứng chính xác bằng `AuthenticationManager`/provider test và response public đúng chính sách.
4. **Role/permission không đủ:** test authorization riêng để tránh nhầm `AccessDeniedException` thành authentication failure.
5. **CSRF và HTTP method:** với login qua POST, test token CSRF, form login và request thiếu token; không chỉ kiểm thử GET qua HTTP Basic.
6. **Session/cookies/remember-me:** account bị vô hiệu hóa sau khi login có được thu hồi session hay phải chờ reauthentication? Quy định phải rõ.
7. **Thông báo và logs:** không trả exception class, password, hash, stack trace, trạng thái nhạy cảm trong response; metric nội bộ phân biệt bad credentials, account state và hạ tầng.
8. **Kiểm thử nhiều provider:** nếu có nhiều `AuthenticationProvider`, kiểm chứng provider nào nhận token và không có đường fallback vô tình bypass account status checks.

## 11. Tự kiểm tra

1. **`DisabledException` xuất hiện với cờ nào?** Với `UserDetails.isEnabled() == false` trong cơ chế kiểm tra DAO tiêu chuẩn.
2. **`LockedException` có chứng minh password đúng không?** Không; kiểm tra account bị khóa có thể diễn ra trước bước so mật khẩu.
3. **Vì sao username không tồn tại lại nhận `BadCredentialsException`?** Provider mặc định che giấu `UsernameNotFoundException` để giảm khả năng dò username.
4. **`CredentialsExpiredException` có giống JWT expired không?** Không; nó thường bắt nguồn từ `UserDetails.isCredentialsNonExpired()`, còn JWT có vòng đời và cơ chế xác thực token riêng.
5. **`AccessDeniedException` có phải là `AuthenticationException` không?** Không; đây là ngoại lệ authorization, thường dẫn đến 403 khi user đã xác thực nhưng thiếu quyền.
6. **Vì sao public API nên dùng thông báo chung cho các lỗi login?** Để giảm lộ thông tin tài khoản; thông tin chi tiết vẫn có thể được lưu ở log/telemetry server-side có kiểm soát.
7. **Dùng HTTP Basic nhưng bắt buộc bị khóa phải trả 403?** Không có quy tắc như vậy; trong cấu hình demo, các authentication failures trả 401, còn 403 thường liên quan quyền hoặc CSRF.
8. **Thay đổi cờ disabled trong database có tự đăng xuất session hiện có?** Không được giả định; cần quản lý vòng đời session hoặc kiểm tra lại trạng thái khi policy yêu cầu.

**Ghi nhớ:** `AuthenticationException` cho biết quá trình thiết lập danh tính thất bại. Với `DaoAuthenticationProvider`, `LockedException`, `DisabledException`, `AccountExpiredException` và `CredentialsExpiredException` phản ánh những trạng thái `UserDetails` khác nhau; `BadCredentialsException` thường đại diện cả sai password và username không tồn tại đã được che giấu. Tách nguyên nhân nội bộ để khắc phục, nhưng giữ phản hồi login công khai an toàn; phân biệt rõ authentication failure với `AccessDeniedException` của authorization.
