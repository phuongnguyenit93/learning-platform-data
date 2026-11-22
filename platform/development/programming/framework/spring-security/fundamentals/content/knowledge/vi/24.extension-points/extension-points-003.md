# Tùy chỉnh kiểm tra thông tin bằng AuthenticationProvider trong Spring Security

> **Phạm vi:** Spring Security cho ứng dụng Servlet/Spring MVC, Java 17+, Spring Boot 3.x và Spring Security 6.x. Chủ đề là cách tự xây dựng, đăng ký và kiểm thử `AuthenticationProvider` để xác minh credential theo yêu cầu riêng của ứng dụng. Ví dụ dùng HTTP Basic và dữ liệu tài khoản trong bộ nhớ để tập trung vào điểm mở rộng.

## 1. Khi nào cần AuthenticationProvider tùy chỉnh?

Trong Spring Security, **authentication** trả lời “người gửi yêu cầu là ai và bằng chứng nhận dạng có hợp lệ không?”. **Authorization** trả lời “danh tính đã xác minh có quyền làm thao tác này không?”. Hai việc này không thay thế nhau.

`AuthenticationProvider` là giao diện phụ trách **xác thực một loại đối tượng `Authentication`**. Nó có thể tra cứu tài khoản, kiểm tra password/token, đánh giá trạng thái tài khoản và trả lại một `Authentication` đã xác thực chứa principal cùng authorities. Nếu kiểm tra thất bại, nó ném ngoại lệ xác thực thích hợp.

Các trường hợp có thể cần provider tùy chỉnh: kiểm tra credential trên hệ thống tài khoản cũ; xác thực người dùng phải đáp ứng điều kiện kích hoạt riêng; sử dụng cơ chế truy cập đặc biệt với token tùy chỉnh; phối hợp một dịch vụ xác thực nội bộ. Tuy nhiên, **không phải ứng dụng nào cũng cần viết lại provider**: nếu chỉ đổi cách đọc user từ database và kiểm tra mật khẩu như thông thường, nên ưu tiên `UserDetailsService` + `PasswordEncoder` + `DaoAuthenticationProvider`.

Mục tiêu học tập:

1. Nắm vai trò của `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`, filter và `SecurityContext`.
2. Hiểu hợp đồng `supports(Class<?>)`, `authenticate(Authentication)` và ba kết quả có thể xảy ra.
3. Tự viết provider kiểm tra password bằng BCrypt, kiểm tra trạng thái tài khoản và cấp authority an toàn.
4. Đăng ký provider với `SecurityFilterChain` và kiểm chứng kết quả HTTP 200/401/403.
5. Biết kiểm thử độc lập, phân biệt xác thực với phân quyền, và tránh các lỗi bảo mật khi tùy biến.

## 2. Vị trí của AuthenticationProvider trong luồng xác thực

Luồng thường gặp trong ứng dụng Servlet dùng HTTP Basic:

```text
HTTP request (Authorization: Basic ...)
     |
     v
BasicAuthenticationFilter
     | tạo UsernamePasswordAuthenticationToken chưa xác thực
     v
AuthenticationManager (thường là ProviderManager)
     | gọi provider phù hợp với loại token
     v
Custom AuthenticationProvider
     | tra tài khoản / kiểm tra credential / kiểm tra trạng thái
     +---------------------------+
     |                           |
     v                           v
Kết quả Authentication       AuthenticationException
đã xác thực                 (BadCredentialsException,
     |                        DisabledException, ...)
     v                           |
Authentication filter            v
ghi SecurityContext       Cơ chế Basic phản hồi
     |                     lỗi xác thực (thường 401)
     v
AuthorizationFilter / AuthorizationManager
     |                           |
     v                           v
Có quyền                       Thiếu quyền
     |                           |
     v                           v
Controller / HTTP 200       Từ chối (thường 403)
```

| Thành phần | Trách nhiệm |
| --- | --- |
| `Authentication` | Chứa principal, credentials, authorities và trạng thái xác thực; là đầu vào chưa xác thực hoặc kết quả đã xác thực. |
| `AuthenticationProvider` | Kiểm tra một loại `Authentication` và trả thành công, từ chối, hoặc nhường provider khác. |
| `AuthenticationManager` | Giao diện `authenticate(Authentication)` mà cơ chế đăng nhập gọi. |
| `ProviderManager` | Triển khai manager phổ biến; duyệt các provider, dùng `supports` để chọn các ứng viên. |
| `Authentication filter` | Đọc thông tin từ HTTP request, tạo token đầu vào, gọi manager, xử lý kết quả và ngữ cảnh xác thực. |
| `SecurityContextHolder` | Cung cấp `SecurityContext` hiện tại; filter thường chịu trách nhiệm cập nhật sau khi manager thành công. |
| `AuthorizationManager` / `AuthorizationFilter` | Quyết định có cấp quyền cho tài nguyên dựa trên `Authentication` và chính sách truy cập. |
| `AuthenticationEntryPoint` / failure handler | Quyết định phản hồi yêu cầu xác thực, ví dụ HTTP Basic 401 hoặc redirect form login. |

**Quan trọng:** Một provider mới **không tự biết cách đọc header/cookie/body mới**. Nếu muốn xác thực header riêng như `X-Api-Key`, bạn còn phải thêm cơ chế lấy credential từ request và tạo loại `Authentication` tương ứng trước khi gọi manager/provider. Ngược lại, Basic/form login đã cung cấp filter cho username/password.

## 3. Hợp đồng của AuthenticationProvider

Giao diện Spring Security có hai phương thức chính (đây là khai báo minh họa; giao diện có sẵn trong thư viện):

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

### 3.1. supports(Class<?>) kiểm tra kiểu token

`supports` nhận lớp Java của token, **không kiểm tra role, username, đường dẫn URL hoặc nội dung mật khẩu**.

Ví dụ provider cho username/password:

```java
@Override
public boolean supports(Class<?> authenticationType) {
    return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(authenticationType);
}
```

`isAssignableFrom` cho phép cả lớp con của `UsernamePasswordAuthenticationToken`. Trả `true` chỉ nghĩa là provider **có thể đánh giá** loại token này; không bảo đảm sẽ xác thực thành công. Nếu phải nhận loại credential khác, thiết kế token và `supports` đúng kiểu thay vì trả `true` cho mọi `Authentication`.

### 3.2. authenticate(Authentication) có ba loại kết quả

| Kết quả | Ý nghĩa |
| --- | --- |
| Trả về `Authentication` đã xác thực | Credential hợp lệ; principal và granted authorities đến từ nguồn tin cậy. |
| Trả về `null` | Provider không thể đưa ra kết luận cho đầu vào này; `ProviderManager` có thể thử provider kế tiếp. |
| Ném `AuthenticationException` | Xác thực thất bại hoặc có sự cố xác thực; chẳng hạn `BadCredentialsException`, `DisabledException`, `LockedException`, `AuthenticationServiceException`. |

Nếu đúng loại token và password sai, provider kiểm tra password thường **ném `BadCredentialsException`**, không trả `null` như thể không quan tâm. Khi có nhiều provider, cách trả `null` và thứ tự thử ảnh hưởng hành vi. `ProviderManager` có thể tiếp tục duyệt sau một số ngoại lệ xác thực; với các lỗi trạng thái tài khoản thuộc `AccountStatusException`, quá trình có thể dừng ngay. Không dựa vào giả định “provider đầu tiên luôn là provider cuối cùng”.

Đầu vào username/password thường được biểu diễn bởi token chưa xác thực:

```java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "reader", "reader-pass");
```

Khi đã kiểm tra thành công, provider có thể trả:

```java
return UsernamePasswordAuthenticationToken.authenticated(
        username,
        null,
        List.of(new SimpleGrantedAuthority("ROLE_USER")));
```

Hai đoạn trên là **mảnh mã minh họa** trong phạm vi phương thức, cần import/biến phù hợp. Kết quả có `isAuthenticated() == true`; `credentials` đặt `null` để không giữ mật khẩu thô. Tuyệt đối không tạo token thành công chỉ dựa vào việc client tự gửi `username` hay `role`.

## 4. Ví dụ hoàn chỉnh chạy được trên Spring Boot

Ta sẽ cung cấp ba tài khoản demo:

| Username | Mật khẩu minh họa | Trạng thái | Authority |
| --- | --- | --- | --- |
| `reader` | `reader-pass` | Hoạt động | `ROLE_USER` |
| `admin` | `admin-pass` | Hoạt động | `ROLE_ADMIN` |
| `disabled` | `disabled-pass` | Vô hiệu hóa | `ROLE_USER` |

Provider sẽ (1) tra username từ `Map`, (2) so khớp mật khẩu bằng BCrypt, (3) kiểm tra `enabled` và (4) trả token chứa authority. Tài khoản demo được tạo trong bộ nhớ khi khởi động, chỉ phục vụ học tập; production phải lưu hash và trạng thái trong kho dữ liệu thực, quản lý secret an toàn.

### 4.1. Dependency

Trong dự án Spring Boot 3.x đã có Gradle plugin và Java 17+, thêm các starter dưới đây vào `dependencies` của `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là đoạn khai báo dependency, **không phải toàn bộ file `build.gradle`**. Với Maven, dùng các starter tương đương.

### 4.2. Toàn bộ mã nguồn

Tạo file `src/main/java/demo/DemoApplication.java` đúng tên, đúng package:

```java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AuthenticationProvider demoAuthenticationProvider(PasswordEncoder encoder) {
        return new DemoAuthenticationProvider(encoder);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationProvider demoAuthenticationProvider) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .authenticationProvider(demoAuthenticationProvider)
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

record DemoAccount(String passwordHash, boolean enabled, String role) {
}

final class DemoAuthenticationProvider implements AuthenticationProvider {
    private final PasswordEncoder encoder;
    private final Map<String, DemoAccount> users;
    private final String dummyPasswordHash;

    DemoAuthenticationProvider(PasswordEncoder encoder) {
        this.encoder = encoder;
        this.users = Map.of(
                "reader", new DemoAccount(
                        encoder.encode("reader-pass"), true, "ROLE_USER"),
                "admin", new DemoAccount(
                        encoder.encode("admin-pass"), true, "ROLE_ADMIN"),
                "disabled", new DemoAccount(
                        encoder.encode("disabled-pass"), false, "ROLE_USER")
        );
        this.dummyPasswordHash = encoder.encode("unused-dummy-password");
    }

    @Override
    public Authentication authenticate(Authentication input)
            throws AuthenticationException {
        String username = input.getName();
        Object credentials = input.getCredentials();
        String rawPassword = credentials instanceof String value ? value : "";

        DemoAccount account = users.get(username);
        String hash = account == null
                ? dummyPasswordHash
                : account.passwordHash();

        boolean matches = encoder.matches(rawPassword, hash);
        if (account == null || !matches) {
            throw new BadCredentialsException("Bad credentials");
        }
        if (!account.enabled()) {
            throw new DisabledException("Account disabled");
        }

        return UsernamePasswordAuthenticationToken.authenticated(
                username,
                null,
                List.of(new SimpleGrantedAuthority(account.role()))
        );
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(authenticationType);
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile() {
        return "profile";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }
}
```

**Đây là một chương trình Java đầy đủ trong một file**, sử dụng duy nhất lớp `public DemoApplication`. Các lớp còn lại là top-level package-private cùng package `demo`, được Spring Boot quét khi khởi động. Cú pháp `record` và pattern matching `instanceof String value` yêu cầu Java 17 trở lên.

Trong mã này, `.authenticationProvider(demoAuthenticationProvider)` là chỗ gắn provider tùy chỉnh vào cấu hình HTTP Security. HTTP Basic cung cấp cơ chế đọc username/password và gọi manager. `.requestMatchers("/admin").hasRole("ADMIN")` là kiểm tra **authorization**, được áp dụng sau khi credential hợp lệ. Theo quy ước, `hasRole("ADMIN")` đòi authority `ROLE_ADMIN`.

### 4.3. Chạy chương trình và đối chiếu HTTP

Với Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Mặc định, nếu không cấu hình cổng khác, ứng dụng chạy tại `http://localhost:8080`. Dùng terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u reader:wrong-pass http://localhost:8080/profile
curl -i -u reader:reader-pass http://localhost:8080/profile
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
curl -i -u disabled:disabled-pass http://localhost:8080/profile
```

Nếu PowerShell ánh xạ `curl` thành `Invoke-WebRequest`, dùng lệnh `curl.exe` thay cho `curl`.

| Tình huống | HTTP kỳ vọng | Vì sao? |
| --- | --- | --- |
| `GET /public` không đăng nhập | 200, body `public` | `permitAll`. |
| `GET /profile` không đăng nhập | 401 | HTTP Basic cần xác thực. |
| `reader` nhập sai mật khẩu | 401 | Provider ném `BadCredentialsException`. |
| `reader` nhập đúng mật khẩu, gọi `/profile` | 200, body `profile` | Kết quả `Authentication` hợp lệ. |
| `reader` nhập đúng mật khẩu, gọi `/admin` | 403 | Đã xác thực nhưng thiếu `ROLE_ADMIN`. |
| `admin` nhập đúng mật khẩu, gọi `/admin` | 200, body `admin` | Vượt qua cả xác thực lẫn phân quyền. |
| `disabled` nhập mật khẩu đúng | 401 | Provider ném `DisabledException`, Basic phản hồi lỗi xác thực. |

`curl -i` hiển thị cả status, header và body; phản hồi HTTP Basic 401 thường có `WWW-Authenticate`. Đây là kết quả **theo cấu hình ví dụ**. Form login có thể redirect thay vì 401; Bearer token dùng cơ chế challenge riêng. Nếu cố gửi header Basic sai vào endpoint `/public`, Basic filter có thể từ chối trước khi tới `permitAll`; endpoint công khai nên được thử mà không gửi credential sai.

## 5. Giải thích logic trong provider

### 5.1. Đọc credential đúng loại

`input.getName()` lấy định danh, `input.getCredentials()` trả `Object`. Với `UsernamePasswordAuthenticationToken` do HTTP Basic tạo, credentials thường là `String`. Đoạn `credentials instanceof String value ? value : ""` tránh ép kiểu nguy hiểm và coi thiếu credential là xác thực không hợp lệ.

Nếu app dùng loại token riêng, không nên áp dụng phép ép kiểu/password assumption của ví dụ; hãy định nghĩa rõ contract của token đó, rồi viết `supports` và `authenticate` tương ứng.

### 5.2. Bảo vệ mật khẩu và dữ liệu tài khoản

`PasswordEncoder.matches(rawPassword, storedHash)` xác minh password đã được hash bằng BCrypt. Không so sánh mật khẩu thô với mật khẩu lưu trữ, không lưu password ở plaintext, không dùng `{noop}` trong production. Ví dụ tự tạo hash khi chạy để dễ học; trong sản phẩm thực tế phải lưu hash bền vững, có quy trình nâng cấp hash và không hard-code password.

Khi username không tồn tại, ví dụ vẫn chạy `encoder.matches(...)` với `dummyPasswordHash`. Mục đích là giảm một khác biệt thời gian dễ quan sát giữa “tài khoản không tồn tại” và “password sai”; đây **không phải bảo đảm thời gian hằng số**. Còn cần rate limiting, phát hiện brute-force, kiểm soát input và thông báo lỗi chung chung cho client.

### 5.3. Kiểm tra trạng thái tài khoản

`BadCredentialsException` phản ánh credential không được chấp nhận; `DisabledException` phản ánh tài khoản đã biết nhưng bị vô hiệu hóa sau khi password hợp lệ. Các hệ thống khác có thể phân biệt `LockedException`, `AccountExpiredException` và `CredentialsExpiredException` theo nghiệp vụ.

Không lộ thông báo nội bộ như “username này tồn tại nhưng đã bị khóa” qua API công khai. Việc ném exception có ý nghĩa nội bộ giúp giám sát đúng nguyên nhân; việc diễn đạt lỗi với client do entry point/failure handler chịu trách nhiệm.

### 5.4. Trả token kết quả an toàn

`UsernamePasswordAuthenticationToken.authenticated(username, null, authorities)` chỉ được gọi sau khi kiểm chứng xong. Trong ví dụ:

- `principal` là username đã được xác minh.
- `credentials` là `null` để không giữ mật khẩu thô.
- `authorities` lấy từ tài khoản phía server, không đọc role do client khai.

`ProviderManager` còn có hành vi xóa credential nhạy cảm khỏi kết quả thành công khi có thể. Nếu ứng dụng trả nguyên đối tượng `UserDetails` được dùng chung từ cache, cần hiểu ảnh hưởng của việc xóa credential đối với đối tượng cache đó.

### 5.5. Không sửa SecurityContextHolder từ provider

`AuthenticationProvider` tập trung vào kiểm tra và **trả kết quả**. Trong luồng HTTP Basic, filter gọi `AuthenticationManager` và cập nhật `SecurityContext` sau khi thành công; provider không tự đặt `SecurityContextHolder.getContext().setAuthentication(...)`. Nếu ứng dụng tự gọi manager ở controller hoặc service, phải chủ động tích hợp kết quả với chiến lược lưu security context/session thích hợp, không coi `authenticate` là một phiên đăng nhập hoàn chỉnh.

## 6. Đăng ký provider, nhiều provider và nhiều filter chain

Trong ví dụ có hai phần quan trọng:

```java
@Bean
AuthenticationProvider demoAuthenticationProvider(PasswordEncoder encoder) {
    return new DemoAuthenticationProvider(encoder);
}
```

và phần cấu hình `HttpSecurity`:

```java
.authenticationProvider(demoAuthenticationProvider)
.httpBasic(Customizer.withDefaults())
```

Hai đoạn này là **mảnh cấu hình bên trong `SecurityConfig` đã hoàn chỉnh ở mục 4**, không tự chạy nếu tách riêng.

`HttpSecurity.authenticationProvider(...)` bổ sung provider dùng khi xây dựng authentication manager của security chain. Nếu thật sự cần kiểm soát manager riêng, có thể tạo `ProviderManager` với danh sách provider được thiết kế cụ thể rồi cấu hình `http.authenticationManager(...)`. Không cần sử dụng đồng thời mọi cách đăng ký chỉ vì chúng tồn tại.

Nếu dự án có nhiều provider, kiểm tra:

1. `supports` của từng provider có chồng lấn kiểu token không.
2. Khi cùng hỗ trợ một kiểu token, thứ tự duyệt và việc ném exception/trả `null` có đáp ứng chính sách không.
3. Provider có làm nhầm “credential sai” thành “để provider khác thử” hay không.
4. Có filter tạo đúng loại `Authentication` được provider nhận không.
5. Có nhiều `SecurityFilterChain` với `securityMatcher` khác nhau không; provider phải nằm trong phạm vi chain thật sự xử lý request.

Nếu dùng Resource Server JWT, OAuth2/OIDC, LDAP hoặc SAML, thường đã có provider/cơ chế chuyên biệt. Một custom username/password provider không xác thực JWT chỉ vì đã được đăng ký như Spring bean.

## 7. Khi nào DaoAuthenticationProvider là lựa chọn tốt hơn?

`DaoAuthenticationProvider` đã triển khai username/password authentication bằng `UserDetailsService` và `PasswordEncoder`. Thường không cần viết một provider mới chỉ để đổi cách tra cứu tài khoản trong database. So sánh:

| Yêu cầu | Giải pháp nên cân nhắc |
| --- | --- |
| Đọc user từ bảng/database tùy chỉnh | Cài `UserDetailsService`; sử dụng `DaoAuthenticationProvider`. |
| Đổi thuật toán hoặc nâng cấp hash mật khẩu | Cấu hình `PasswordEncoder` và cơ chế nâng cấp mật khẩu. |
| Xác thực với logic/credential thật sự riêng | `AuthenticationProvider` tùy chỉnh hoặc thành phần chuyên dụng. |
| Chấp nhận API key ở header riêng | Filter/converter đọc request, token riêng và provider phù hợp. |
| Quyền truy cập theo URL, role hoặc scope | `authorizeHttpRequests`/`AuthorizationManager`; method security nếu cần. |
| Định dạng lỗi 401/403 | `AuthenticationEntryPoint`, `AccessDeniedHandler`, login failure handler. |

Ví dụ **mảnh cấu hình thay thế** trong lớp `@Configuration` dùng Spring Security 6.x:

```java
@Bean
AuthenticationProvider standardProvider(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {
    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);
    return provider;
}
```

Các import bổ sung khi dùng đoạn này:

```java
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
```

Đoạn trên không phải một phần của ví dụ `DemoAuthenticationProvider` chạy ở mục 4. Không tự động đăng ký cả hai provider cho cùng token nếu chưa thiết kế thứ tự và các tình huống thất bại. Với cấu hình tiêu chuẩn, Spring Boot/Spring Security thường có thể tự tạo cơ chế xác thực khi dự án cung cấp `UserDetailsService` hợp lệ.

## 8. Kiểm thử provider độc lập

Provider viết đúng có thể được test bằng JUnit mà không cần khởi chạy server. Với `spring-boot-starter-test`, tạo `src/test/java/demo/DemoAuthenticationProviderTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

class DemoAuthenticationProviderTest {
    private final DemoAuthenticationProvider provider =
            new DemoAuthenticationProvider(new BCryptPasswordEncoder());

    @Test
    void validPasswordProducesAuthenticatedResult() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "reader-pass");

        Authentication result = provider.authenticate(request);

        assertTrue(result.isAuthenticated());
        assertEquals("reader", result.getName());
        assertNull(result.getCredentials());
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));
    }

    @Test
    void wrongPasswordIsRejected() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "wrong");

        assertThrows(BadCredentialsException.class,
                () -> provider.authenticate(request));
    }

    @Test
    void unknownUsernameIsRejected() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "missing", "anything");

        assertThrows(BadCredentialsException.class,
                () -> provider.authenticate(request));
    }

    @Test
    void disabledAccountIsRejected() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "disabled", "disabled-pass");

        assertThrows(DisabledException.class,
                () -> provider.authenticate(request));
    }

    @Test
    void supportsUsernamePasswordType() {
        assertTrue(provider.supports(
                UsernamePasswordAuthenticationToken.class));
    }
}
```

Chạy:

```bash
./gradlew test
```

Nên bổ sung kiểm thử tích hợp với `MockMvc` hoặc HTTP thực để chứng minh `SecurityFilterChain` thật sự gọi provider, status là 401 khi credential sai/disabled và 403 khi đúng credential nhưng thiếu role. Test unit chứng minh logic trong provider; test web chứng minh cách nối provider với filter và handler.

## 9. Lỗi thường gặp và checklist triển khai

**Các lỗi dễ gặp:**

- Trả token đã xác thực trước khi kiểm tra credential, hoặc lấy authority trực tiếp từ payload client.
- Đặt toàn bộ kiểm tra credential trong controller rồi bỏ qua `AuthenticationManager` và filter.
- Đăng ký bean provider nhưng không có filter/converter tạo loại token tương ứng.
- Viết `supports` trả `true` cho mọi `Authentication`, gây chồng lấn và xung đột giữa providers.
- Trả `null` cho mọi password sai khiến provider khác có cơ hội xử lý không đúng mục đích.
- Ném `BadCredentialsException` cho lỗi database/gateway timeout, làm khó phân biệt lỗi vận hành.
- Log password, Authorization header hoặc thông điệp exception nhạy cảm; tiết lộ việc username có tồn tại.
- Nhầm `AuthenticationException` với `AccessDeniedException`: người dùng đã xác thực nhưng thiếu `ROLE_ADMIN` cần authorization xử lý, thông thường trả 403.
- Vội tắt CSRF khi thấy 403; có thể lỗi do token CSRF thiếu, không liên quan provider.
- Dùng HTTP Basic trên HTTP không mã hóa ngoài môi trường localhost; cần HTTPS và giải pháp bảo vệ trước brute-force.

**Trước khi đưa vào production:** dùng TLS, kho hash/password encoder được duyệt, giới hạn số lần thử đăng nhập, chống dò username, kiểm soát timeout của dịch vụ ngoài, không lộ thông tin nhạy cảm, xử lý trạng thái tài khoản đúng ngữ nghĩa, có metrics/log an toàn và kiểm thử cả thành công lẫn thất bại. `AuthenticationProvider` nên có trách nhiệm rõ, hoạt động ổn định với concurrency và không lưu credential từng request vào field dùng chung trong singleton bean.

## 10. Câu hỏi tự luyện

1. `AuthenticationProvider.supports(...)` trả `true` dựa trên loại thông tin nào? Nó có xác nhận password hợp lệ không?
2. Khi password sai trong một provider đã nhận `UsernamePasswordAuthenticationToken`, nên ném `BadCredentialsException` hay trả `null`? Vì sao?
3. Vì sao `reader` đúng password nhưng gọi `/admin` thường nhận 403, còn `reader` sai password nhận 401?
4. Nếu muốn đọc API key từ header `X-Api-Key`, chỉ cài đặt `AuthenticationProvider` là đủ chưa?
5. Khi chỉ cần tải user từ bảng riêng và dùng BCrypt, có nhất thiết viết custom provider không?
6. Vì sao kết quả provider dùng `credentials = null` và authorities do server cung cấp?
7. Điều gì xảy ra nếu dùng chung một provider cho nhiều `SecurityFilterChain` nhưng không gắn nó vào chain xử lý đúng request?
8. Lỗi dịch vụ xác thực bên ngoài bị timeout nên được theo dõi như lỗi hạ tầng hay ghi thành “sai mật khẩu” một cách âm thầm?

**Hướng giải:** (1) kiểu `Authentication`; (2) ném exception phù hợp khi đã xét credential và xác thực thất bại; (3) xác thực khác với phân quyền; (4) cần thành phần trích xuất request và tạo token; (5) thường `UserDetailsService` + `DaoAuthenticationProvider`; (6) ngăn lộ secret và role giả; (7) provider có thể không được dùng; (8) phân biệt và ghi nhận lỗi hạ tầng an toàn.

## Tài liệu chính thức

- [Spring Security — Servlet Authentication Architecture, AuthenticationManager, ProviderManager](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security 6.5 — AuthenticationProvider API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security 6.5 — HttpSecurity.authenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — PasswordEncoder](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/password-encoder.html)