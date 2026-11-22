# RememberMeAuthenticationFilter, RememberMeServices và AuthenticationProvider trong Spring Security Servlet

> **Phạm vi:** Ghi nhớ đăng nhập trong Spring Security Servlet, với Java 17+, Spring Boot 3.x và Spring Security 6.x. Trọng tâm: filter quyết định thời điểm phục hồi, services kiểm tra cookie, provider xác thực remember-me token nội bộ, cùng vòng đời và rủi ro của chúng.

## 1. Remember-me thực chất là gì?

Người dùng thường muốn không phải nhập lại password mỗi lần HTTP session hết hạn hoặc sau khi đóng rồi mở trình duyệt. **Remember-me** cho phép ứng dụng cấp một cookie có thể được kiểm tra ở các request sau để khôi phục danh tính khi không còn authentication trong session/context. Đây là cơ chế **xác thực lại bằng credential nhớ đăng nhập**, không phải chỉ kéo dài thời hạn `JSESSIONID`.

Để tránh nhầm lẫn, hãy tách bốn thứ:

- **Đăng nhập chính**: người dùng cung cấp password hoặc thông tin mạnh hơn, `AuthenticationManager`/provider xác minh và tạo `Authentication`.
- **Phiên HTTP**: có thể lưu `SecurityContext` của lần xác thực chính và thường tồn tại trong thời gian ngắn hơn cookie remember-me.
- **Remember-me cookie**: là credential được gửi lại để server khôi phục authentication khi context trống; phải được xem như một **bearer secret**.
- **Authorization**: quyết định request được làm gì. Một `RememberMeAuthenticationToken` được đánh dấu authenticated nhưng thường **không phải fully authenticated**.

Ba tên trong tiêu đề tương ứng ba vai trò độc lập:

1. **`RememberMeAuthenticationFilter`**: nhận biết request nào chưa có authentication trong security context, rồi thử sử dụng remember-me.
2. **`RememberMeServices`**: quản lý việc tạo cookie khi login thành công, đọc/kiểm tra cookie để tự đăng nhập, và xử lý login thất bại; những triển khai khác nhau dùng chữ ký hoặc server-side token repository.
3. **`RememberMeAuthenticationProvider`**: xác minh `RememberMeAuthenticationToken` do services tạo có thuộc đúng shared-key configuration trước khi `AuthenticationManager` chấp nhận.

**Ghi nhớ:** filter không tự xác minh chữ ký cookie; provider không tự đọc cookie browser; services không tự ban phát quyền truy cập endpoint. Chúng phối hợp với `SecurityContext`, `AuthenticationManager` và authorization.

## 2. Hai pha của remember-me: cấp cookie và tự đăng nhập

Một remember-me implementation phải làm được hai việc khác nhau.

### Pha A — phát cookie sau login bằng password

```text
Browser POST /login
  username + password + CSRF + checkbox remember-me
          |
          v
UsernamePasswordAuthenticationFilter
          |
          v
AuthenticationManager -> DaoAuthenticationProvider
          |
       xác minh credential thành công
          |
          +--> SessionAuthenticationStrategy / SecurityContext
          |
          +--> RememberMeServices.loginSuccess(...)
                  |
              cookie được tạo nếu chính sách/checkbox cho phép
                  |
              Set-Cookie: remember-me=...
          |
          v
AuthenticationSuccessHandler -> redirect
```

Khi password sai, login filter xử lý nhánh thất bại và có thể gọi `RememberMeServices.loginFail(...)` trước `AuthenticationFailureHandler`. **Không phải mọi lần login thành công đều cấp cookie**: mặc định checkbox phải được chọn, trừ khi ứng dụng chủ động dùng `alwaysRemember(true)`.

### Pha B — khôi phục khi session authentication đã mất

```text
Browser GET /profile + remember-me cookie
              |
              v
FilterChainProxy chọn SecurityFilterChain
              |
              v
RememberMeAuthenticationFilter
   SecurityContext chưa có Authentication
              |
              v
RememberMeServices.autoLogin(request,response)
   |         |
   |         +--> cookie invalid/expired/absent -> null hoặc lỗi
   |
   +--> cookie hợp lệ -> tạo RememberMeAuthenticationToken
              |
              v
AuthenticationManager.authenticate(...)
              |
              v
RememberMeAuthenticationProvider kiểm tra key hash
              |
              v
SecurityContext chứa Authentication dạng remember-me
              |
              v
Authorization: authenticated() / fullyAuthenticated()
              |
              v
MVC controller, nếu policy cho phép
```

Đây là sơ đồ chức năng, không phải thứ tự mọi filter bất biến trong mọi phiên bản. Nếu request vẫn có `Authentication` trong security context (ví dụ session login), filter remember-me thường không gọi `autoLogin`. Vì thế việc thấy trình duyệt đăng nhập thành công sau refresh **không chứng minh** remember-me đã được thử.

### Ba tình huống thực tế

| Tình huống | Cơ chế có thể quyết định authentication |
| --- | --- |
| POST /login với password đúng | Form login filter và password provider |
| GET /profile với session chứa Authentication hợp lệ | SecurityContext được phục hồi; remember-me có thể không cần chạy |
| GET /profile không có session auth nhưng có remember-me cookie hợp lệ | RememberMeAuthenticationFilter → RememberMeServices → RememberMeAuthenticationProvider |

Thiết kế test phải **tách các tình huống này**, đặc biệt khi muốn chứng minh cookie nhớ đăng nhập thực sự có hiệu lực.

## 3. `RememberMeServices`: API và ý nghĩa từng callback

Contract phổ biến thuộc `org.springframework.security.web.authentication.RememberMeServices` gồm ba phương thức:

```java
// Chữ ký tham khảo, không phải toàn bộ interface độc lập.
Authentication autoLogin(
    HttpServletRequest request,
    HttpServletResponse response);

void loginFail(
    HttpServletRequest request,
    HttpServletResponse response);

void loginSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication successfulAuthentication);
```

Đây là chữ ký API rút gọn; để compile phải đặt trong lớp/interface với import Spring Security và Servlet đúng.

**`loginSuccess`** được gọi sau một lần xác thực chính thành công (thường là form login). Nó quyết định cookie remember-me có được phát hành hay không, dựa vào checkbox/alwaysRemember và implementation. Nếu checkbox không chọn, không mặc nhiên cấp cookie.

**`loginFail`** cho phép dọn cookie hoặc trạng thái nhớ đăng nhập khi lần login chính bị thất bại. Đừng nhầm callback này với HTTP 403 do thiếu quyền ở một endpoint sau login: request bị từ chối authorization không phải là một lần POST login thất bại.

**`autoLogin`** đọc cookie từ request và kiểm tra xem có thể tạo một `Authentication` candidate hay không. Với token-based, việc kiểm tra thường bao gồm hạn dùng/chữ ký và tải `UserDetails`. Với persistent tokens, nó tra và cập nhật server-side token repository. Nó có thể trả `null` khi không có thông tin phù hợp hoặc từ chối token không hợp lệ.

Một ứng dụng có thể thay `RememberMeServices` nếu có nhu cầu đặc biệt, nhưng cần đáp ứng đầy đủ các đường `autoLogin`, `loginSuccess`, `loginFail`, cookie cleanup và logout. Chỉ override hàm tạo cookie mà quên cách parse hoặc revoke sẽ tạo rủi ro.

### Form checkbox phải đồng bộ tên với cấu hình

```html
<form method="post" action="/login">
  <input name="username" autocomplete="username">
  <input name="password" type="password"
         autocomplete="current-password">
  <label>
    <input name="remember-me" type="checkbox">
    Ghi nhớ đăng nhập
  </label>
  <!-- Phải có CSRF token do server cung cấp trong ứng dụng bật CSRF. -->
  <button type="submit">Đăng nhập</button>
</form>
```

Đây là **fragment UI**; chưa đủ để dùng trong ứng dụng bật CSRF nếu chưa render CSRF hidden parameter thực tế. Nếu đổi `rememberMeParameter("keepSignedIn")`, frontend phải đổi `name` checkbox tương ứng. Đừng cho rằng chỉ đổi label hiển thị là đủ.

## 4. `RememberMeAuthenticationFilter`: điều kiện chạy và giới hạn

Filter là nơi kích hoạt pha B. Logic ý niệm:

```text
request vào chain có bật remember-me
    |
    +--> SecurityContext đã có Authentication?
    |       |
    |       +-- Có -> không chạy autoLogin
    |       |
    |       +-- Không
    |            |
    |            v
    |     RememberMeServices.autoLogin(...)
    |            |
    |            +-- null/không hợp lệ -> không phục hồi
    |            |
    |            +-- có candidate -> AuthenticationManager.authenticate(...)
    |                                  |
    |                                  +-- provider chấp nhận
    |                                  |     -> ghi Authentication vào context
    |                                  |
    |                                  +-- provider từ chối
    |                                        -> clear/failure path
    |
    v
tiếp tục authorization và MVC
```

Trong cấu hình tiêu chuẩn, remember-me filter chạy trước anonymous authentication processing, để một request chưa có identity có cơ hội được khôi phục bằng cookie. Cần phân biệt **context chưa có Authentication** với request đã trở thành anonymous sau một filter khác.

Hành vi lưu `SecurityContext` sau remember-me thành công phụ thuộc Spring Security version, filter strategy và `SecurityContextRepository`. Không giả định tất cả ứng dụng đều lưu remember-me auth vào một `HttpSession` mới, và cũng không giả định mọi request nhớ đăng nhập đều stateless.

Filter **không phải** nơi:

- So sánh password form với mật khẩu hash.
- Quyết định URL admin có được truy cập hay không.
- Tự kiểm tra checksum/signature cookie mà không thông qua services.
- Cấp lại cookie long-lived vô điều kiện mỗi GET.
- Loại bỏ CSRF cho request POST/PUT/PATCH/DELETE.
- Thu hồi mọi HTTP session hoặc JWT chỉ vì remember-me cookie đã bị xóa.

Khi có nhiều `SecurityFilterChain`, URL cần phục hồi phải được chain chứa remember-me filter xử lý. `http.rememberMe(...)` ở một chain không tự tạo filter cho mọi chain khác.

## 5. `RememberMeAuthenticationToken` và `RememberMeAuthenticationProvider`

Sau khi `RememberMeServices` kiểm tra cookie, nó có thể tạo `RememberMeAuthenticationToken`: một đối tượng `Authentication` phía server mang principal và authorities ở mức remember-me. Đối tượng này **khác với raw browser cookie**; đừng nghĩ provider đang trực tiếp decode cookie từ HTTP header.

`RememberMeAuthenticationProvider` nhận token này qua `AuthenticationManager` và kiểm tra **key hash**. Key ở services và provider phải khớp. Mục đích là đảm bảo remember-me token được tạo dưới cấu hình tin cậy; provider không đóng vai trò `PasswordEncoder` và không tự kiểm tra cookie signature hoặc database series/token.

```text
cookie bytes
    |
    v
RememberMeServices
   kiểm tra signature/expiry hoặc persistent token store
   tải UserDetails/authorities
    |
    v
RememberMeAuthenticationToken(sharedKey, principal, authorities)
    |
    v
AuthenticationManager
    |
    v
RememberMeAuthenticationProvider(sharedKey)
   so sánh key hash
    |
    v
Authentication mức remember-me
```

Nếu bạn cần tự wire provider trong cấu hình nâng cao, fragment minh họa:

```java
String keyFromSecureConfiguration = "example-only-shared-key";
RememberMeAuthenticationProvider provider =
    new RememberMeAuthenticationProvider(keyFromSecureConfiguration);
```

Fragment yêu cầu import `org.springframework.security.authentication.RememberMeAuthenticationProvider`. Key trên chỉ minh họa, không dùng trong production. Provider phải thực sự được lắp vào authentication manager phù hợp. Khi dùng `http.rememberMe(...)`, Spring Security DSL đã cung cấp đường tích hợp; không nên tạo provider/filter trùng lặp.

### Vì sao một remember-me token có thể authenticated nhưng không fully authenticated?

`RememberMeAuthenticationToken.isAuthenticated()` có thể trả `true`, song nó biểu thị một lần khôi phục danh tính bằng cookie tồn tại trước đó thay vì một login chính trong lần tương tác hiện tại. `AuthenticationTrustResolver` và các authorization manager hỗ trợ phân biệt anonymous, remember-me và fully authenticated.

| Kiểm tra | Form login thành công | Remember-me cookie được phục hồi |
| --- | --- | --- |
| `authentication != null` | Đúng | Đúng |
| `authentication.isAuthenticated()` | Thường `true` | Cũng có thể `true` |
| `AuthenticationTrustResolver.isRememberMe(auth)` | Thường `false` | `true` |
| `authenticated()` authorization | Thường cho phép | Có thể cho phép |
| `fullyAuthenticated()` authorization | Cho phép nếu không còn điều kiện khác | **Không** thỏa nhớ đăng nhập đơn lẻ |
| Yêu cầu MFA/step-up nghiệp vụ | Vẫn tùy chính sách | Nên yêu cầu cơ chế mạnh hơn cho thao tác nhạy cảm |

Một đoạn code kiểm tra `isAuthenticated()` rồi kết luận "vừa nhập password" là không an toàn cho nghiệp vụ yêu cầu xác thực lại. Hãy dùng authorization rule, trust resolver hoặc cơ chế step-up/MFA có chứng cứ rõ.

## 6. Authenticated và fullyAuthenticated: thiết kế quyền theo mức độ tin cậy

Ví dụ trong `HttpSecurity`:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/profile").authenticated()
    .requestMatchers("/sensitive").fullyAuthenticated()
    .anyRequest().denyAll()
)
```

- `authenticated()`: chấp nhận identity đã xác thực không phải anonymous, trong đó remember-me có thể được chấp nhận theo cấu hình.
- `fullyAuthenticated()`: yêu cầu authentication không phải anonymous và không chỉ remember-me. Rule này **không tự đảm bảo MFA** hoặc "password vừa nhập trong 5 phút"; nếu cần recency/MFA phải thiết kế riêng.
- `rememberMe()` trong authorization config là một điều kiện chuyên biệt cho authentication được trust resolver coi là remember-me; không nên dùng nó để thay yêu cầu full auth cho endpoint nhạy cảm.

Những hành động như thay password, đổi thông tin khôi phục, xác nhận thanh toán, cấp quyền admin hoặc xem dữ liệu có độ nhạy cao thường nên yêu cầu **full authentication** hoặc step-up mạnh hơn. Đừng chỉ dựa vào việc người dùng có cookie nhớ đăng nhập để phê duyệt giao dịch rủi ro.

### Phân biệt 302/401/403

Khi một remembered user truy cập `/sensitive` yêu cầu `fullyAuthenticated()`, Spring Security có thể đưa người dùng tới entry point/login page hoặc tạo status lỗi tùy filter chain và cách cấu hình. Việc nhận 302 thay vì 403 không có nghĩa cookie không hợp lệ; rule có thể cố ý yêu cầu login lại. Đừng hardcode một suy luận duy nhất từ status khi chưa nhìn rule và authentication type.

## 7. Token-based remember-me: đơn giản nhưng khó thu hồi riêng từng cookie

`TokenBasedRememberMeServices` tạo một remember-me cookie có dữ liệu phục vụ việc kiểm tra thời hạn và chữ ký. Nó dùng key bí mật ở server và thông tin account để nhận diện token. Định dạng cookie, thuật toán và chi tiết ký **có thể khác giữa các phiên bản/cấu hình Spring Security**; không tự viết parser dựa vào một Base64 string nhìn thấy trong browser.

Sơ đồ:

```text
Login password thành công + chọn remember-me
         |
TokenBasedRememberMeServices phát token/cookie có expiry và signature
         |
Browser giữ remember-me cookie
         |
Request mới không có session Authentication
         |
TokenBasedRememberMeServices.autoLogin(...)
         |
check cookie/expiry/signature, tải UserDetails
         |
RememberMeAuthenticationToken
         |
RememberMeAuthenticationProvider
         |
Authorization cho request
```

Ưu điểm: không nhất thiết cần bảng token cho từng cookie; dễ dùng trong ứng dụng nhỏ hoặc demo. Nhưng có các giới hạn:

1. **Thu hồi chọn lọc khó**: nếu cookie bị sao chép, việc xóa cookie ở browser gốc không xóa bản sao. Không có server-side token series để revoke từng thiết bị.
2. **Key phải mạnh và ổn định**: đổi key thường làm cookie đã cấp trước đó hết hiệu lực. Các node phục vụ cùng ứng dụng cần chia sẻ secret key nếu muốn cookie hoạt động khi request chuyển node.
3. **Password change/user removal** có thể làm token-based cookie không còn hợp lệ theo cách signature và user lookup hoạt động. Tuy nhiên không được suy rằng đổi password đồng thời thu hồi mọi session, refresh token hoặc access token khác.
4. **TTL dài tăng rủi ro**: cookie tồn tại lâu là bearer credential dài hạn. Giới hạn `tokenValiditySeconds` theo nhu cầu và kiểm soát Secure/HttpOnly/HTTPS.
5. **UserDetails cache** nếu stale có thể gây trễ hiệu lực thay đổi user/authorities. Nếu account bị khóa, cần đánh giá riêng checks/revocation thay vì chỉ đoán mọi provider đều kiểm tra account status như `DaoAuthenticationProvider`.

Một chính sách "đăng xuất toàn bộ thiết bị ngay" thường cần server-side revocation hoặc chiến lược khác ngoài token-based thuần.

## 8. Persistent remember-me: server lưu series/token và hỗ trợ revoke

`PersistentTokenBasedRememberMeServices` sử dụng `PersistentTokenRepository`. Cookie chứa thông tin series/token, server tra bản ghi để xác nhận và cập nhật token khi sử dụng. Các thành phần thường gặp:

- `PersistentTokenBasedRememberMeServices`: implementation remember-me đọc, rotate và ghi cookie/token theo repository.
- `PersistentTokenRepository`: contract lưu/truy vấn/cập nhật/xóa token.
- `JdbcTokenRepositoryImpl`: triển khai repository bằng JDBC.
- `InMemoryTokenRepositoryImpl`: dùng cho test hoặc minh họa, không bền khi restart và không thích hợp cluster.
- `CookieTheftException`: lỗi liên quan mismatch có thể được hiểu là tín hiệu token đã bị sao chép hoặc race; cần xử lý vận hành phù hợp.

```text
cookie nhớ đăng nhập
  series = S12
  token  = T_old
       |
       v
PersistentTokenBasedRememberMeServices
       |
       v
PersistentTokenRepository tìm bản ghi series S12
       |
       +--> không có -> từ chối
       |
       +--> token khác -> mismatch/theft handling
       |
       +--> token khớp -> load user, rotate/update token,
                          gửi cookie mới nếu policy yêu cầu
       |
       v
RememberMeAuthenticationToken -> provider -> context
```

Vì có bản ghi server-side, ứng dụng có thể xóa token theo user/series và thiết kế quản lý thiết bị tốt hơn. Nhưng **persistent không đồng nghĩa không thể replay**: bản sao token hợp lệ vẫn có thể được thử trước khi rotate/revoke. Request đồng thời dùng cùng cookie có thể gây mismatch và false-positive theft detection; một thiết kế production phải kiểm thử concurrency, retry, multi-node và thiết bị thực.

### Bảng so sánh

| Tiêu chí | Token-based | Persistent token |
| --- | --- | --- |
| Token store cho từng cookie | Không bắt buộc | Có, qua `PersistentTokenRepository` |
| Kiểm tra giá trị cookie | Chữ ký/hạn/key và user info theo implementation | Series/token so với bản ghi server-side |
| Thu hồi riêng một token | Khó nếu không bổ sung state/revocation | Có cơ chế quản lý từ repository; có thể cần API mở rộng cho từng thiết bị |
| Phụ thuộc server-side dữ liệu | User details/key | User details, token DB và key/provider config |
| Multi-node | Cần key đồng nhất và user store đúng | Cần token repository chia sẻ/đồng bộ, xử lý concurrency |
| Replay/theft | Cookie valid có thể bị dùng | Token rotation/mismatch detection hỗ trợ nhưng không tuyệt đối |
| Vận hành | Đơn giản hơn | Schema, cleanup, migration, reliability cao hơn |
| Migration | Đổi key/format có thể làm cookie cũ hết hiệu lực | Đổi schema/repository/cookie format cần kế hoạch |

Không đặt một cookie tự thiết kế rồi giả định `RememberMeServices` mặc định sẽ hiểu; chỉ dùng token format do implementation được chọn hỗ trợ.

## 9. Ví dụ hoàn chỉnh Spring Boot 3.x + Java 17: form login và remember-me

Ví dụ sẽ dùng **token-based remember-me** để thấy filter/services/provider phối hợp mà chưa cần database token store. Các điểm quan sát:

- Browser login bằng password và chọn checkbox `remember-me`.
- `GET /profile` chấp nhận remembered user.
- `GET /sensitive` yêu cầu `fullyAuthenticated()`.
- Controller cho biết `Authentication` đang là token loại gì để học (không nên dùng class name làm public API contract trong production).
- Logout chuẩn giữ CSRF bật, giúp dọn cookie browser theo services.

### Dependencies

Trong project Gradle Spring Boot 3.x đã thiết lập plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo tệp `src/main/java/example/rememberdemo/RememberDemoApplication.java`:

```java
package example.rememberdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RememberDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    // Chỉ dành cho local demo. Production dùng secret manager,
    // không hardcode key trong code hoặc public repository.
    private static final String DEMO_REMEMBER_KEY =
        "local-demo-remember-key-never-use-for-production-2026";

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/profile").authenticated()
                .requestMatchers("/sensitive").fullyAuthenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                .key(DEMO_REMEMBER_KEY)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(14 * 24 * 60 * 60)
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
            )
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "profile=" + authentication.getName()
            + "; authType=" + authentication.getClass().getSimpleName();
    }

    @GetMapping("/sensitive")
    String sensitive(Authentication authentication) {
        return "sensitive=" + authentication.getName();
    }
}
```

**Giải thích các lựa chọn:**

- Java 17 cho phép một public class có cùng tên tệp và các top-level class package-private trong cùng file. `@SpringBootApplication` quét package `example.rememberdemo`.
- `UserDetailsService` demo giữ account trong memory, password được băm bằng delegating encoder. Không đưa demo credentials hoặc demo key lên môi trường production.
- `.formLogin(Customizer.withDefaults())` kích hoạt `UsernamePasswordAuthenticationFilter`; GET `/login` thường được Spring Security tạo tự động khi chưa có trang riêng.
- `.rememberMe(...)` đăng ký remember-me pipeline với key và `UserDetailsService` nhất quán. **Không cần** tạo thủ công `RememberMeAuthenticationFilter`/`RememberMeAuthenticationProvider`.
- `.rememberMeParameter("remember-me")` nối đúng checkbox của form; `.tokenValiditySeconds(...)` thiết lập thời gian hợp lệ của token, không làm session dài 14 ngày.
- `.authenticated()` cho phép remembered identity trên `/profile` còn `.fullyAuthenticated()` yêu cầu login mạnh hơn trên `/sensitive`.
- `.logout(...)` dùng cơ chế logout có CSRF và remember-me services. Không giả định logout ở một browser sẽ thu hồi mọi bản sao token đã bị đánh cắp.

### Chạy ứng dụng

Trong root của dự án Gradle có wrapper:

```bash
./gradlew bootRun
```

Với Windows PowerShell có thể chạy `./gradlew.bat bootRun`.

Mở các URL local:

```text
http://localhost:8080/public
http://localhost:8080/profile
```

**Kỳ vọng:** `/public` trả body `public`; `/profile` của anonymous sẽ điều hướng tới trang login. Nhập `learner` / `demo-pass` và chọn checkbox **Remember me** nếu form mặc định/biểu mẫu của bạn hiển thị đúng lựa chọn.

Sau khi đăng nhập bằng password, controller `/profile` có thể trả:

```text
profile=learner; authType=UsernamePasswordAuthenticationToken
```

Nếu **không còn session authentication** nhưng browser vẫn gửi remember-me cookie hợp lệ, filter phục hồi và controller có thể trả:

```text
profile=learner; authType=RememberMeAuthenticationToken
```

Đây là **output dự kiến theo code**, chưa phải kết quả chạy thực tế. Nếu session vẫn hoạt động, request có thể tiếp tục dùng `UsernamePasswordAuthenticationToken`; refresh trang **không tự xóa session**. Muốn kiểm chứng remember-me, phải tạo request không có session cookie hoặc session đã hết hạn nhưng vẫn giữ cookie remember-me.

### Về login page tùy biến

Một form tối thiểu có checkbox:

```html
<form method="post" action="/login">
  <input name="username" autocomplete="username">
  <input type="password" name="password"
         autocomplete="current-password">
  <label>
    <input name="remember-me" type="checkbox">
    Ghi nhớ đăng nhập
  </label>
  <!-- Render hidden CSRF input do Spring Security cấp. -->
  <button type="submit">Đăng nhập</button>
</form>
```

Fragment HTML chưa đủ để chạy trên ứng dụng bật CSRF nếu thiếu CSRF token thực từ server; hãy dùng MVC view/template integration để render token và context path đúng. Nếu tự đặt `loginPage(...)` thì Spring Security không tự tạo HTML page đó; cần khai báo GET controller/view và quyền truy cập phù hợp.

## 10. MockMvc: chứng minh `autoLogin` thay vì chỉ chứng minh session

Trong integration test, quan trọng nhất là **sau lần login đầu, tạo một HTTP request mới chỉ mang remember-me cookie và không mang session authentication**. Khi đó mới có thể quan sát `RememberMeAuthenticationFilter`/services/provider phục hồi.

Thêm dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo tệp `src/test/java/example/rememberdemo/RememberMeSecurityTest.java`:

```java
package example.rememberdemo;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeSecurityTest {

    @Autowired
    MockMvc mvc;

    private Cookie loginAndGetRememberCookie() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        Cookie cookie = login.getResponse().getCookie("remember-me");
        assertNotNull(cookie, "Opt-in successful login should issue cookie");
        return cookie;
    }

    @Test
    void successfulOptInIssuesRememberMeCookie() throws Exception {
        Cookie cookie = loginAndGetRememberCookie();
        assertNotNull(cookie.getValue());
    }

    @Test
    void cookieAloneCanRestoreRememberMeAuthentication()
            throws Exception {
        Cookie cookie = loginAndGetRememberCookie();

        // Không truyền HttpSession từ login sang request này.
        mvc.perform(get("/profile").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString(
                "authType=RememberMeAuthenticationToken")));
    }

    @Test
    void rememberMeIsNotFullyAuthenticated() throws Exception {
        Cookie cookie = loginAndGetRememberCookie();
        mvc.perform(get("/sensitive").cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void anonymousNeedsLoginForProfile() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void notCheckingRememberMeDoesNotIssueCookie()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertNull(login.getResponse().getCookie("remember-me"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Test code và assertion trên được xây dựng cho cấu hình đã mô tả; **không có lần chạy thật nào được thực hiện khi viết tài liệu**. MockMvc không mô phỏng hoàn chỉnh hành vi browser về cookie `Secure`/`SameSite` hoặc thời gian đóng browser. Trong production nên test thêm qua browser thật, HTTPS và reverse proxy.

Các test bổ sung quan trọng: cookie bị sửa; cookie hết hạn; key thay đổi; user bị xóa; khóa tài khoản; nhiều request song song; logout; password change; cache stale; persistent token series bị xóa; behavior khi `fullyAuthenticated()` yêu cầu login lại.

## 11. Dùng persistent token store với JDBC khi cần quản lý revoke

Nếu hệ thống yêu cầu thu hồi server-side hoặc theo dõi token, có thể chuyển sang `JdbcTokenRepositoryImpl`. Đây là **hướng dẫn mở rộng**; các fragment tiếp theo không phải một application độc lập và không được dán thêm song song với config token-based mà không thay DSL tương ứng.

Thêm dependencies JDBC và driver phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2' // Chỉ dành cho demo local.
}
```

Bean repository trong một `@Configuration`:

```java
@Bean
PersistentTokenRepository persistentTokenRepository(
        javax.sql.DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
```

Import:

```java
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
```

Trong `HttpSecurity`, thay remember-me configuration bằng variant dùng repository:

```java
.rememberMe(remember -> remember
    .key(rememberMeKey)
    .userDetailsService(users)
    .tokenRepository(persistentTokenRepository)
    .tokenValiditySeconds(14 * 24 * 60 * 60)
)
```

Đoạn code giả định `rememberMeKey`, `users`, `persistentTokenRepository` đã được inject/tạo đúng kiểu. Cần tạo bảng token bằng migration trước khi dịch vụ hoạt động. DDL minh họa cho schema thông dụng:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

Schema cần tương thích database/dialect và implementation thực tế; sử dụng migration tool ở production, không tự động cấp quyền DDL quá rộng cho account ứng dụng web.

**Lưu ý riêng của persistent remember-me:**

- **Tính nhất quán multi-node**: cùng repository và cấu hình key, xử lý token rotation đồng thời.
- **Khả năng revoke**: thiết kế chính sách delete token khi logout, reset password, khóa account; không xem cookie browser bị xóa là đã xóa mọi token server-side.
- **Device-aware controls**: nếu cần "quên thiết bị này" hoặc danh sách devices, có thể phải mở rộng repository vì `removeUserTokens(username)` là thao tác theo user, không phải API phong phú sẵn có cho mọi device.
- **Token mismatch**: có thể báo hiệu theft, nhưng concurrent requests cũng có thể gây race; không vô hiệu hóa toàn bộ kiểm tra chỉ vì test hai tab bị lỗi.
- **Cleanup và observability**: dọn token expired, rate-limit bất thường, không ghi raw token vào logs hay metrics.
- **Persistence**: `InMemoryTokenRepositoryImpl` mất dữ liệu khi restart và không phải lựa chọn production cluster.

## 12. Logout, key rotation và thay đổi trạng thái tài khoản

### Logout trong browser

Cơ chế logout thường dọn `SecurityContext`, invalidate session theo policy, xóa cookie remember-me phía browser bằng `RememberMeServices.logout` và xử lý token store nếu implementation có. Spring Security logout filter/handlers được cấu hình phù hợp; POST logout có thể cần CSRF token.

**Không đồng nhất ba sự kiện**:

1. Xóa `JSESSIONID` không đồng nghĩa xóa remember-me cookie.
2. Xóa remember-me cookie ở browser không đồng nghĩa vô hiệu bản sao cookie đã bị đánh cắp.
3. Revoke remember-me token không đồng nghĩa mọi session/JWT/refresh token khác cũng bị thu hồi.

Với token-based remember-me, logout phía client không đảm bảo một cookie đã bị sao chép trở thành vô dụng ngay; nếu security requirement là revoke-all, cần server-side strategy hoặc thay đổi key/dữ liệu ký theo chính sách. Với persistent token, khả năng revoke tốt hơn nhưng phải kiểm tra đường logout thực tế có đủ authentication/user context để xóa đúng bản ghi.

### Key rotation

Key là secret server-side. Các node cần key nhất quán, và đổi key có thể làm cookie cũ không còn hợp lệ. Nếu cần vòng đời key, lập kế hoạch downtime, rollout multi-node, cơ chế migration/invalidating old credentials, monitoring và trải nghiệm đăng nhập lại. Không cho client tự chọn key, không disable keyHash verification để "cứu" cookie cũ.

### Account bị khóa hoặc thay password

Khi admin khóa user hoặc tước quyền:

- `UserDetailsService` cần cung cấp dữ liệu mới và cache phải được invalidate.
- `RememberMeServices` thường tải user, nhưng **`RememberMeAuthenticationProvider` không tự chạy lại đầy đủ pre/post account checks giống `DaoAuthenticationProvider`**. Do đó không mặc nhiên kết luận `isAccountNonLocked=false` chắc chắn chặn mọi remember-me token còn sống.
- Persistent repository có thể cần xóa token theo user/series; token-based có thể cần chính sách key/password change/invalidation phù hợp.
- Session đã có authentication trước khi khóa vẫn có thể sống; phải có session revoke hoặc request-time check khi yêu cầu "khóa ngay".
- JWT và các access/refresh tokens khác có đường revoke riêng, không tự động mất hiệu lực theo remember-me.

Nếu cần đáp ứng một SLA "khóa tài khoản có hiệu lực sau tối đa 10 giây", hãy thiết kế giải pháp và **đo** từ lúc DB commit đến khi mọi request/sessions/tokens bị chặn; đừng chỉ xác nhận đã gọi `removeUserTokens` ở một node.

## 13. Cookie flags, HTTPS, XSS/CSRF và session management

Remember-me cookie là credential. Chỉ bảo vệ password hash trong database mà để lộ remember cookie qua HTTP hoặc logs vẫn có nguy cơ mất tài khoản.

**Cookie flags và scope:**

- **Secure**: trên public HTTPS, cookie chỉ nên được gửi qua kết nối HTTPS. Khi có TLS termination phía proxy, cấu hình forwarded headers đáng tin cậy.
- **HttpOnly**: hạn chế JavaScript đọc cookie; nó không ngăn script XSS cùng origin khởi động hành động dưới danh tính user.
- **SameSite**: dùng `Lax`/`Strict` hoặc chính sách phù hợp với login/cross-site flows; không coi SameSite là giải pháp duy nhất cho CSRF.
- **Domain/Path**: chỉ mở phạm vi cần thiết; không chia remember-me cookies giữa nhiều ứng dụng không cùng trust boundary.
- **Max-Age/Expires**: thời gian browser giữ cookie và thời gian server chấp nhận token có thể khác nhau; browser có thể xóa sớm, server phải kiểm tra expiry.

**HTTPS và credential hygiene:** TLS ở production là bắt buộc; không log cookie value, Base64 token, password, Authorization header, query string chứa credential hoặc raw `Authentication` object.

**CSRF:** browser tự gắn cookie nhớ đăng nhập cho request đến domain đích, do đó **CSRF protection vẫn quan trọng** cho state-changing operations. Spring Security Servlet thường bật CSRF mặc định; không gọi `.csrf(...disable...)` chỉ vì "đã dùng remember-me".

**XSS:** nếu attacker có JavaScript cùng origin, họ có thể gây thao tác dù không đọc cookie HttpOnly; dùng output encoding, CSP và phương pháp tránh XSS độc lập.

**Session:** session cố định sau password login nên được bảo vệ bằng strategy phù hợp. Remember-me phục hồi có thể tương tác với session context tùy config; không giả định mọi lần nhớ đăng nhập luôn tạo session hoặc luôn bỏ qua session.

## 14. Các vấn đề hay gặp khi vận hành

| Triệu chứng | Nguyên nhân có thể | Hướng chẩn đoán |
| --- | --- | --- |
| Cookie `remember-me` có nhưng GET vẫn anonymous | Cookie hết hạn/sai key/path/domain, không được gửi, user lookup fail, sai chain | Kiểm tra cookie flags và filter chain, logging đã redact |
| Login password thành công nhưng không có cookie | Checkbox không chọn/sai name, `alwaysRemember` false, chưa bật DSL | Kiểm tra POST parameter và `.rememberMe(...)` |
| Nhớ đăng nhập vẫn bị đưa tới /login ở endpoint nhạy cảm | `fullyAuthenticated()` yêu cầu login mạnh hơn | Kiểm tra authorization rule, không đổ lỗi token |
| Reload trang vẫn thấy form auth bình thường | Session chưa hết hạn; remember-me filter không cần chạy | Test request cookie-only không có session |
| App chạy một node được, đổi node bị login lại | Key khác nhau/token repository không chung | Secret config/cluster DB, deployment strategy |
| Restart xong cookie không dùng được | Key mỗi lần start thay đổi; token store in-memory mất | Secret ổn định, repository bền, migration |
| Logout rồi bản sao cookie cũ còn dùng được | Token-based không có revoke per-cookie | Chọn persistent/revocation strategy |
| Sau đổi password, nhớ đăng nhập có behavior lạ | Password hash/secret changed, cache stale hoặc cookie mismatch | Kiểm tra implementation, invalidation |
| Tài khoản locked nhưng remembered access còn hợp lệ | Chưa áp account-status check/revoke cho remember-me, session cũ còn sống | Security policy cho account state + session/token revoke |
| Persistent token báo theft sau hai request đồng thời | Rotation race/mismatch | Test concurrency, audit và error handling |
| POST /logout trả 403 | CSRF token thiếu/sai | Dùng POST với CSRF hợp lệ, không disable bảo vệ |
| Cookie bị gửi sai origin/scheme | Proxy/TLS/Domain/SameSite/Secure sai | Rà soát public HTTPS origin, trusted forwarded headers |

### Cách debug có phương pháp

1. Xác nhận `SecurityFilterChain` được chọn, request matcher và `RememberMeAuthenticationFilter` có hiện diện.
2. Xác nhận cookie được **gửi tới server**, không chỉ xuất hiện trong browser storage.
3. Kiểm tra context đã có auth từ session không; nếu có, remember-me có thể không chạy.
4. Xác định `RememberMeServices` đang là token-based hay persistent.
5. Kiểm tra token expiry, key, user lookup, persistent repository/series (nếu dùng), không in giá trị raw.
6. Kiểm tra provider cho `RememberMeAuthenticationToken` và authentication manager.
7. Kiểm tra authorization rule `authenticated()` hay `fullyAuthenticated()`.
8. Kiểm tra logout, session invalidation, password/role/locked changes và các loại token khác.
9. Xác minh trong môi trường multi-node và HTTPS thay vì chỉ local MockMvc.
10. Nếu cần debug logs, giới hạn thời gian, audience và dữ liệu nhạy cảm, rồi tắt sau khi chẩn đoán.

## 15. Những sai lầm về khái niệm

### "Remember-me chỉ là một session cookie sống lâu"

Không đúng. Remember-me credential có thể được dùng **sau khi session authentication đã mất**, và được khôi phục qua một filter/services/provider khác.

### "RememberMeAuthenticationProvider đọc cookie và so sánh chữ ký"

Không. Nó xác minh `RememberMeAuthenticationToken` bằng shared key hash; logic cookie/token store thuộc `RememberMeServices`.

### "Có RememberMeAuthenticationToken và isAuthenticated=true tức là user vừa nhập password"

Không. Hãy dùng `AuthenticationTrustResolver`, `fullyAuthenticated()` và chính sách step-up/recency khi cần.

### "Bật rememberMe() là đủ để tạo cookie cho mọi login"

Không nếu chính sách yêu cầu checkbox. Kiểm tra `remember-me` parameter hoặc `alwaysRemember` nếu lựa chọn đó được phê duyệt.

### "Xóa browser cookie là xóa mọi token đã bị đánh cắp"

Không. Với token-based, bản sao có thể tiếp tục dùng. Với persistent, thu hồi phụ thuộc server-side repository và đúng path revoke.

### "Token persistent tự động giải quyết tất cả replay"

Không. Rotation/mismatch detection giúp ích, nhưng cần xem race/concurrency, token store reliability và xử lý stolen copies.

### "Khóa account thì mọi remember-me auth tự bị từ chối"

Không được mặc định giả định điều đó. Cần kiểm tra code path của services và provider, cache, sessions, persistent token revocation và nghiệp vụ.

### "Xóa UserDetails cache thì session cũ tự biến mất"

Không. Session đã có `Authentication` riêng, và cookie/token cũng có vòng đời độc lập.

### "Remember-me không cần CSRF vì chỉ là cookie hỗ trợ UX"

Sai. Một browser có thể tự gửi remember-me credential, nên unsafe operations cần CSRF mitigation theo threat model.

## 16. Bài tập và câu hỏi kiểm tra

**Câu 1.** Browser còn `JSESSIONID` chứa `Authentication` chính. Có phải `RememberMeAuthenticationFilter` luôn gọi `autoLogin` ở mỗi request?

**Đáp án:** Không. Khi `SecurityContext` đã có authentication, filter thường không cần tự đăng nhập bằng remember-me cookie.

**Câu 2.** `RememberMeServices` và `RememberMeAuthenticationProvider` cùng sử dụng key, vậy chức năng nào trùng nhau?

**Đáp án:** Key nhất quán là điều kiện phối hợp, nhưng chức năng khác nhau: services kiểm tra cookie/token và tạo candidate; provider xác minh key hash của remember-me token nội bộ qua authentication manager.

**Câu 3.** Cookie tồn tại nhưng user vẫn không xem được `/sensitive`; endpoint đó dùng `fullyAuthenticated()`. Đây có phải cookie bị hỏng không?

**Đáp án:** Chưa chắc. Remember-me authentication có thể hợp lệ nhưng không đạt mức fully authenticated. Đây có thể là hành vi bảo mật mong muốn.

**Câu 4.** Vì sao MockMvc test POST /login có Set-Cookie không đủ để chứng minh remember-me hoạt động?

**Đáp án:** Chưa kiểm tra pha autoLogin. Cần thực hiện request khác chỉ có remember cookie và không có session authentication, rồi quan sát `RememberMeAuthenticationToken`.

**Câu 5.** Admin tước quyền hoặc khóa user, chỉ xóa cookie phía browser có bảo đảm mọi phiên và JWT bị chặn không?

**Đáp án:** Không. Cần policy cho account state, UserDetails cache, remember-me token revocation, active sessions và các loại tokens khác.

**Câu 6.** Lợi thế của persistent token repository so với token-based cookie khi cần "quên thiết bị" là gì?

**Đáp án:** Có server-side token state để revoke/rotate; có thể cần mở rộng repository/model để quản lý thiết bị một cách chính xác.

**Câu 7.** Vì sao key hardcoded trong source và key khác nhau trên mỗi node gây lỗi?

**Đáp án:** Hardcoded key có nguy cơ rò rỉ, key khác nhau dẫn tới provider/services không chấp nhận token xuyên node. Production cần secret an toàn và đồng nhất.

**Câu 8.** Khi user có remember-me auth, check `authentication.isAuthenticated()` trả true. Có nên cho phép đổi password mà không xác thực lại không?

**Đáp án:** Không nên chỉ dựa vào flag. Tùy policy cần full authentication, step-up, MFA hoặc xác minh lại credential hợp lệ.

**Câu 9.** Persistent cookie báo token mismatch sau hai request song song. Có thể bỏ qua mismatch để không gây phiền không?

**Đáp án:** Không nên. Cần phân tích race và điều kiện token theft thực sự; bỏ qua mismatch tùy tiện làm giảm hiệu quả cơ chế bảo vệ.

**Câu 10.** Token-based remember-me không cần token table. Vậy có cần database user không?

**Đáp án:** Vẫn cần nguồn danh tính `UserDetailsService` hoặc tương đương để load account/authorities theo implementation, cũng như hệ thống quản lý account và password hash.

## 17. Checklist để nghiệm thu remember-me

- [ ] Xác định đúng chain có `RememberMeAuthenticationFilter` và không cấu hình filter trùng lặp.
- [ ] Chọn token-based/persistent phù hợp yêu cầu thu hồi cookie và vận hành.
- [ ] `RememberMeServices` quản lý `loginSuccess`, `loginFail`, `autoLogin` đúng kịch bản.
- [ ] `AuthenticationManager` có `RememberMeAuthenticationProvider` key đồng nhất.
- [ ] Checkbox `remember-me` thực sự được gửi và không phát cookie ngoài ý định nếu không `alwaysRemember`.
- [ ] Key dài/ngẫu nhiên, quản lý qua secret manager, đồng bộ giữa nodes, có kế hoạch rotation.
- [ ] Cookie `Secure` trên HTTPS, `HttpOnly`, Domain/Path/SameSite và TTL phù hợp.
- [ ] Kiểm thử login password, cookie-only restore, expired/corrupt token, wrong key và no-cookie.
- [ ] Kiểm thử `authenticated()` chấp nhận remembered identity khi được phép nhưng `fullyAuthenticated()` yêu cầu login lại.
- [ ] Không để remember-me vượt qua CSRF, authorization hay MFA/step-up cho tác vụ nhạy cảm.
- [ ] Logout/revoke và "logout all devices" được kiểm tra trên cả browser lẫn token store.
- [ ] Khóa user, đổi password, tước role có chính sách riêng cho remember-me, session và token khác.
- [ ] Nếu persistent: token table migration/cleanup, retry/rotation race, multi-node DB và audit được kiểm thử.
- [ ] Chạy browser/HTTPS/proxy integration tests, không chỉ dựa vào MockMvc.
- [ ] Không in cookie values, password, hash hoặc token secrets vào logs/metrics.

## Kết luận

**`RememberMeAuthenticationFilter`** quyết định thời điểm cần khôi phục login; **`RememberMeServices`** quản lý giá trị cookie và điều kiện chấp nhận nó; **`RememberMeAuthenticationProvider`** xác minh remember-me token nội bộ dưới shared key trước khi authentication manager chấp nhận. Sau đó `SecurityContext` và authorization quyết định request nào được phép.

Điểm cốt lõi là remember-me authentication **không đồng nhất với full authentication**. Một cookie dài hạn có tính chất credential nên phải được bảo vệ, quản lý TTL, logout/revoke, key và account status; ở những thao tác nhạy cảm cần xác thực lại hoặc step-up theo chính sách, không chỉ kiểm tra `isAuthenticated()`.
