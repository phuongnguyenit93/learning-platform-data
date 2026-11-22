# Không để nội dung phản hồi giúp dò tài khoản hoặc trạng thái khóa

**Module:** Spring Security – authentication. **Nhóm:** Trạng thái tài khoản.

## 1. Vì sao “thông báo đăng nhập thất bại” là một vấn đề bảo mật?

Hãy xem hai phản hồi:

- Người dùng nhập `an@example.com` và sai mật khẩu: **“Sai mật khẩu”**.
- Người dùng nhập `khongtontai@example.com`: **“Không tìm thấy tài khoản”**.

Chỉ cần thử nhiều email, người chưa đăng nhập đã biết email nào có tài khoản trong hệ thống. Nếu phản hồi còn nói **“Tài khoản đã bị khóa”**, **“Chưa xác minh email”** hoặc **“Tài khoản đang bị vô hiệu hóa”**, kẻ tấn công không chỉ dò được sự tồn tại mà còn biết **trạng thái của một danh tính cụ thể**.

Đây là hiện tượng **account/user enumeration** (dò sự tồn tại của tài khoản) và **account-state disclosure** (tiết lộ trạng thái tài khoản). Nó có thể hỗ trợ:

- Credential stuffing: ưu tiên thử các username thực sự tồn tại cùng mật khẩu rò rỉ.
- Password spraying: thử một hoặc vài mật khẩu phổ biến trên danh sách tài khoản đã được xác minh.
- Phishing: giả danh bộ phận hỗ trợ vì đã biết người nào đang bị khóa hoặc chờ kích hoạt.
- Tấn công có chủ đích vào tài khoản giá trị cao, hoặc quấy rối người dùng bằng quy trình khóa/reset.
- Suy đoán thông tin nhạy cảm về việc một người có sử dụng sản phẩm hay không.

**Mục tiêu thiết kế:** Với một **yêu cầu không có danh tính đáng tin**, phản hồi công khai cho những lần đăng nhập **không thành công vì không có tài khoản, sai password, khóa, disable hoặc hết hạn** nên được chuẩn hóa đủ mức để không cho kẻ bên ngoài phân biệt các trường hợp. Đồng thời hệ thống vẫn phải giữ thông tin nguyên nhân chính xác **bên trong** phục vụ xử lý sự cố, chống lạm dụng và chăm sóc người dùng theo kênh đã xác minh.

**Không có nghĩa:** mọi thao tác đều phải trả HTTP 200, mọi lỗi hệ thống đều phải che giấu, hoặc người sở hữu tài khoản vĩnh viễn không được biết tài khoản mình bị khóa. Quyết định cho biết trạng thái chi tiết **sau khi đã chứng minh quyền sở hữu/danh tính** là một luồng riêng, có kiểm soát.

## 2. Phân biệt thất bại nội bộ với phản hồi cho bên ngoài

Trong Spring Security, `AuthenticationManager`/`AuthenticationProvider` cần nhận diện nguyên nhân đủ chính xác để từ chối đăng nhập:

| Tình huống nội bộ | Exception/điều kiện thường gặp | Có nên tiết lộ trực tiếp ở màn hình login công khai? |
| --- | --- | --- |
| Username không tồn tại | `UsernameNotFoundException` bên `UserDetailsService`; `DaoAuthenticationProvider` thường chuyển thành `BadCredentialsException` | **Không** |
| Password sai | `BadCredentialsException` | **Không** |
| Account bị khóa | `LockedException` | **Không** |
| Account disabled | `DisabledException` | **Không** |
| Account expired | `AccountExpiredException` | **Không** |
| Password/credentials expired | `CredentialsExpiredException` | **Không** trên login công khai; dùng luồng đổi mật khẩu có xác minh |
| Provider/cấu hình gặp vấn đề | `AuthenticationServiceException`, `InternalAuthenticationServiceException` hoặc lỗi hạ tầng | Không phơi thông tin hạ tầng; ghi audit và trả lỗi vận hành thích hợp |
| Người dùng đã xác thực nhưng thiếu permission | `AccessDeniedException`/quyết định authorization | Đây là **authorization**, không phải nguyên nhân login thất bại |

Ví dụ, **cùng một phản hồi công khai** cho nhóm lỗi auth do danh tính/credential:

~~~json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "Đăng nhập không thành công. Vui lòng kiểm tra thông tin hoặc dùng chức năng hỗ trợ."
}
~~~

Trong nội bộ vẫn phân biệt:

~~~text
internal_reason=BAD_CREDENTIALS
internal_reason=LOCKED
internal_reason=DISABLED
internal_reason=CREDENTIALS_EXPIRED
~~~

Các giá trị `internal_reason` **không phải** trường gửi cho browser/API client chưa xác thực. Không đưa exception class, username tồn tại hay cờ `locked=true` vào response body, URL, header, GraphQL extensions hoặc mã lỗi client.

### Cần chuẩn hóa cả “hợp đồng phản hồi”

Không chỉ text trong giao diện. Một attacker có thể quan sát:

1. **HTTP status**: `401` cho username sai nhưng `423 Locked` cho account bị khóa là kênh tiết lộ.
2. **Body**: thông điệp, code, JSON schema, số lượng field, độ dài response, HTML khác nhau.
3. **Redirect/URL**: `/login?error=wrong_password` và `/login?error=account_locked`.
4. **Header/cookie**: `X-Account-Status: disabled`, `Retry-After` chỉ có cho tài khoản tồn tại, `Set-Cookie` khác biệt.
5. **Timing**: username có thật chạy BCrypt, username không có thật trả ngay; hoặc account locked bị từ chối trước khi kiểm tra password.
6. **Side effects có thể quan sát**: email, SMS, mã CAPTCHA, khóa tạm, tốc độ rate-limit khác nhau, reset flow hay thông báo khác.
7. **Đầu ra máy chủ khác**: WebSocket/SSE, GraphQL error path, logs công khai, monitoring endpoint, trang hỗ trợ.

Vì vậy không thể kết luận “đã chống enumeration” chỉ vì câu trả lời chữ giống nhau.

## 3. Nguyên tắc generic response theo OWASP

Một chiến lược thường dùng cho **login công khai** là:

~~~text
Không thấy username  ─┐
Sai password          ─┤
Account locked        ─┼─> CÙNG status + body + headers chính
Account disabled      ─┤          cho nhóm lỗi xác thực này
Account expired       ─┘
~~~

Ví dụ cho API:

- HTTP: `401 Unauthorized` khi credential login không hợp lệ hoặc account không thể xác thực.
- Body: cùng `AUTHENTICATION_FAILED` và message chung, không trả username/exception.
- Headers liên quan tới login error: không mang trạng thái tài khoản.
- Cache: `Cache-Control: no-store` để không lưu phản hồi chứa dữ liệu phiên hoặc thông tin login.

Với **form login** dùng redirect, có thể chọn **cùng URL `/login?error`** cho các loại lỗi trên. Còn REST API thường trả JSON; chọn giao thức nào thì giữ **nhất quán** trong giao thức đó, không nhất thiết ép form và JSON dùng status giống nhau.

**Phân biệt với thành công:** Login thành công rõ ràng phải khác login thất bại, vì client cần được cấp session/token. Mục đích không phải giấu rằng một cặp username/password **đúng** có thể đăng nhập, mà là không cho người chưa sở hữu credential chính xác phân biệt **các lý do thất bại**.

**Đối với 429/rate limit:** Có thể trả `429 Too Many Requests` khi giới hạn tốc độ dựa trên chính sách chống lạm dụng. Nhưng threshold, thời gian phản hồi và header limit **không được trở thành oracle** tiết lộ username tồn tại. Một counter chỉ tăng khi username có thật là thiết kế nguy hiểm.

## 4. Tại sao Spring Security chưa giải quyết hết chỉ bằng cấu hình mặc định?

### 4.1. `hideUserNotFoundExceptions`

`AbstractUserDetailsAuthenticationProvider` là lớp cơ sở của `DaoAuthenticationProvider`. Thuộc tính:

~~~java
// Trong code cấu hình provider; minh họa, không phải class độc lập.
daoAuthenticationProvider.setHideUserNotFoundExceptions(true);
~~~

Theo Spring Security 6.5, giá trị mặc định là **`true`**:

- `UserDetailsService` báo `UsernameNotFoundException` → provider chuyển sang `BadCredentialsException`;
- Password sai → `BadCredentialsException`.

Điều này giúp che khác biệt **“không có user” so với “sai password”** ở loại exception người gọi thường nhìn thấy.

**Nhưng đây chỉ là một lớp bảo vệ:**

- `LockedException` và `DisabledException` vẫn có thể được ném từ account-status checks.
- Thứ tự/tốc độ xử lý account có thật, không có hoặc bị khóa có thể khác.
- Failure handler tự viết có thể vô tình đưa `exception.getMessage()` ra client.
- Cấu hình custom provider/LDAP/OIDC/OTP không nhất thiết tuân theo đúng ánh xạ này.
- `hideUserNotFoundExceptions=true` không tự chuẩn hóa signup, reset password, password recovery, HTTP headers hay rate limit.

**Không nên đặt `setHideUserNotFoundExceptions(false)` chỉ để hiển thị thông báo “username không tồn tại” trên login công khai**. Spring Security coi việc phân biệt lỗi người dùng không tồn tại như vậy là kém an toàn hơn.

### 4.2. Các cờ UserDetails và exception nội bộ

`UserDetails` có các cờ:

~~~java
boolean isEnabled();
boolean isAccountNonLocked();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
~~~

Các cờ phản ánh policy account trong kho tài khoản. `DaoAuthenticationProvider` và các checker phù hợp sử dụng chúng để quyết định đăng nhập. **Chúng không phải dữ liệu mà form login công khai được quyền công bố.**

Một account có mật khẩu đúng nhưng `isAccountNonLocked() == false` vẫn phải bị từ chối. Ngược lại, che câu “account locked” **không có nghĩa bỏ qua việc kiểm tra khóa**. Logic security được giữ nguyên; chỉ **đường xuất phản hồi** không phân biệt từng nguyên nhân nhạy cảm.

### 4.3. Exception nào đã được Spring Security xử lý trước controller?

Với **Spring Security Servlet**, `UsernamePasswordAuthenticationFilter`/`AbstractAuthenticationProcessingFilter` thường bắt `AuthenticationException`, gọi `AuthenticationFailureHandler` và dọn context không thành công theo luồng filter.

Do đó, chỉ thêm `@ControllerAdvice @ExceptionHandler(AuthenticationException.class)` **không đảm bảo** kiểm soát được các thất bại login do security filter đã bắt và xử lý. Cần cấu hình **failure handler đúng filter/chain**.

Ngược lại, một REST controller tự gọi `AuthenticationManager.authenticate(...)` có thể tự xử lý exception trong controller/service, nhưng phải giữ nguyên các bước quản lý `SecurityContext`, session strategy, CSRF, rate limit và success/failure policy thích hợp. Không nên tự viết login mới chỉ để đổi câu thông báo.

## 5. Kiến trúc hai kênh: phản hồi an toàn và chẩn đoán nội bộ

~~~text
        POST /login (public, chưa được xác minh)
                        |
                        v
           Auth filter / API boundary
                        |
                        v
            AuthenticationManager
                        |
             +----------+-----------+
             |                      |
          THÀNH CÔNG              THẤT BẠI
             |                      |
             v                      v
        Session/token       AuthenticationException
             |                      |
             v             +--------+--------+
       Login success       |                 |
                          v                 v
                    Internal audit      Public mapper
                   reason/category      fixed failure
                   actor? trace id      status/body/header
                   rate-limit event          |
                          |                   v
                          v             Client/browser
                    Security metrics
                    alerts/support
~~~

**Tính năng audit và public mapper có trách nhiệm khác nhau:**

- **Public mapper:** nhận lỗi nội bộ, cho ra phản hồi chung, ổn định, không tiết lộ trạng thái. Cần xét tất cả status/body/header/redirect.
- **Audit:** ghi nguyên nhân có cấu trúc và ID request, các biến cần cho điều tra/đo lường. Chỉ truy cập bởi nhân sự có thẩm quyền; giới hạn dữ liệu cá nhân, retention và quyền xem.
- **Rate limiter:** hạn chế dò username và credential stuffing/spraying ngay cả khi phản hồi đã generic.
- **Recovery/step-up:** cho người dùng thực xác minh quyền sở hữu rồi mới nhận hướng dẫn cụ thể về khóa, disable hoặc reset.

Trong audit, việc ghi toàn bộ `Authentication`, password hoặc token không được xem là “cần thiết để debug”. Đừng log `exception` bằng cơ chế tự động nếu stack trace/cause có thể chứa dữ liệu nhạy cảm từ custom provider; cần chính sách logging/sanitization.

## 6. Demo Java 17 chạy được: bốn nguyên nhân thất bại, một phản hồi công khai

Bài demo sử dụng **Spring Security Core 6.5.11** với `InMemoryUserDetailsManager`, `DaoAuthenticationProvider` và `ProviderManager`. Chúng ta tạo:

- Một tài khoản có thể đăng nhập nhưng nhập **sai mật khẩu**.
- Một username **không tồn tại**.
- Một tài khoản **bị khóa**.
- Một tài khoản **bị disable**.
- Một tài khoản **đăng nhập thành công** làm đối chứng.

Các exception nội bộ được **đếm bằng class trong bộ nhớ chương trình**, còn `PublicResponse` chỉ chứa status/message chung. Demo không chạy web server; đây là minh họa đúng boundary mà ứng dụng web cần áp dụng trong failure handler.

### 6.1. Cấu trúc thư mục

~~~text
login-privacy/
├── build.gradle
└── src/main/java/example/LoginPrivacyDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'example.LoginPrivacyDemo'
}
~~~

**File `src/main/java/example/LoginPrivacyDemo.java`:**

~~~java
package example;

import java.util.HashMap;
import java.util.Map;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class LoginPrivacyDemo {

    record PublicResponse(int status, String body) {}

    private static final PublicResponse PUBLIC_FAILURE =
            new PublicResponse(401, "Đăng nhập không thành công.");

    private static final PublicResponse PUBLIC_SUCCESS =
            new PublicResponse(200, "Đăng nhập thành công.");

    private static PublicResponse attempt(
            AuthenticationManager manager,
            String username,
            String rawPassword,
            Map<String, Integer> internalAuditCounts) {

        try {
            Authentication result = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, rawPassword
                    )
            );

            if (!result.isAuthenticated()) {
                // Defense in depth: không cấp success khi chưa xác thực.
                return PUBLIC_FAILURE;
            }

            return PUBLIC_SUCCESS;
        } catch (AuthenticationException exception) {
            // Chỉ lưu bộ đếm theo loại exception vào khu vực nội bộ.
            // Không ghi raw password, token hoặc thông tin account vào log.
            internalAuditCounts.merge(
                    exception.getClass().getSimpleName(), 1, Integer::sum
            );
            return PUBLIC_FAILURE;
        }
    }

    private static void show(
            String label, PublicResponse response) {
        System.out.println(label + ": status=" + response.status()
                + " body=" + response.body());
    }

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        UserDetails normal = User.withUsername("an")
                .password(encoder.encode("good-password"))
                .roles("USER")
                .build();

        UserDetails locked = User.withUsername("binh")
                .password(encoder.encode("locked-password"))
                .roles("USER")
                .accountLocked(true)
                .build();

        UserDetails disabled = User.withUsername("chi")
                .password(encoder.encode("disabled-password"))
                .roles("USER")
                .disabled(true)
                .build();

        InMemoryUserDetailsManager users =
                new InMemoryUserDetailsManager(normal, locked, disabled);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        provider.setHideUserNotFoundExceptions(true);

        AuthenticationManager manager = new ProviderManager(provider);
        Map<String, Integer> auditCounts = new HashMap<>();

        PublicResponse wrongPassword = attempt(
                manager, "an", "wrong-password", auditCounts);
        PublicResponse unknown = attempt(
                manager, "not-registered", "anything", auditCounts);
        PublicResponse lockedAccount = attempt(
                manager, "binh", "locked-password", auditCounts);
        PublicResponse disabledAccount = attempt(
                manager, "chi", "disabled-password", auditCounts);
        PublicResponse valid = attempt(
                manager, "an", "good-password", auditCounts);

        // Phần public: không biết thất bại vì sao.
        show("wrongPassword", wrongPassword);
        show("unknownUser", unknown);
        show("lockedUser", lockedAccount);
        show("disabledUser", disabledAccount);
        show("validUser", valid);

        System.out.println("failuresEqual="
                + wrongPassword.equals(unknown)
                + "," + unknown.equals(lockedAccount)
                + "," + lockedAccount.equals(disabledAccount));

        // Chỉ để minh họa metrics NỘI BỘ, không phải response HTTP.
        System.out.println("internal.badCredentials="
                + auditCounts.getOrDefault(
                        "BadCredentialsException", 0));
        System.out.println("internal.locked="
                + auditCounts.getOrDefault("LockedException", 0));
        System.out.println("internal.disabled="
                + auditCounts.getOrDefault("DisabledException", 0));
    }
}
~~~

**Chạy** trong thư mục `login-privacy`, với JDK 17+ và Gradle tương thích:

~~~bash
gradle -q run
~~~

Nếu có Gradle Wrapper trong dự án, dùng `./gradlew -q run`; trên Windows dùng `gradlew.bat -q run`. Mạng có thể cần thiết ở lần đầu tải dependencies từ Maven Central.

**Stdout do chính chương trình in** (không kể log riêng của Gradle hoặc thư viện khi cấu hình thêm):

~~~text
wrongPassword: status=401 body=Đăng nhập không thành công.
unknownUser: status=401 body=Đăng nhập không thành công.
lockedUser: status=401 body=Đăng nhập không thành công.
disabledUser: status=401 body=Đăng nhập không thành công.
validUser: status=200 body=Đăng nhập thành công.
failuresEqual=true,true,true
internal.badCredentials=2
internal.locked=1
internal.disabled=1
~~~

### 6.2. Đọc đúng ý nghĩa kết quả

- `wrongPassword` và `unknownUser` đều bị ánh xạ thành `BadCredentialsException`, vì `hideUserNotFoundExceptions=true`; điều này giúp che khác biệt ở mức loại lỗi provider.
- `lockedUser` phát sinh `LockedException`; `disabledUser` phát sinh `DisabledException` do kiểm tra trạng thái account. **Trong nội bộ vẫn có thể phân biệt** hai lý do.
- `failuresEqual=true,true,true` chỉ chứng minh **status/body của `PublicResponse` trong demo giống nhau**. Nó không chứng minh network timing, headers hay tác động phụ là giống nhau; ứng dụng web phải test thêm.
- Các dòng `internal.*` là **metrics trong process**, chỉ để học nguyên nhân. Không gửi chúng trong JSON, response header, redirect parameter hay giao diện chưa xác minh.
- `validUser` khác các thất bại vì credential và account state hợp lệ; demo không tạo session/token HTTP thực tế.

**Bảo mật:** Mật khẩu trong demo là mẫu giả cho học tập. Ứng dụng thực dùng secret hợp lệ, chính sách mật khẩu, TLS, session/CSRF protection và rate limiting. Không xuất class name của exception cho người chưa xác thực.

## 7. Tích hợp Spring Security Servlet: failure handler chung

Với form login sử dụng `UsernamePasswordAuthenticationFilter`, nơi chuẩn hóa phản hồi là `AuthenticationFailureHandler`. Ví dụ sau là **đoạn cấu hình ứng dụng Spring Boot Servlet**, không phải chương trình độc lập. Nó cố ý chọn **phản hồi JSON thống nhất** cho lỗi đăng nhập – thích hợp khi client AJAX gọi endpoint login form-encoded; UI sử dụng redirect truyền thống có thể dùng một URL `/login?error` chung thay thế.

~~~java
// Các import chính trong ứng dụng Spring Boot Servlet:
// org.springframework.context.annotation.Bean;
// org.springframework.security.web.SecurityFilterChain;
// org.springframework.security.web.authentication.AuthenticationFailureHandler;
// org.springframework.security.config.annotation.web.builders.HttpSecurity;
// org.springframework.security.config.Customizer;

@Bean
AuthenticationFailureHandler genericLoginFailureHandler() {
    return (request, response, exception) -> {
        // Có thể audit exception phía server, với log đã được bảo vệ.
        // KHÔNG ghi exception.getMessage() ra client.

        response.setStatus(401);
        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/json");
        response.setHeader("Cache-Control", "no-store");

        response.getWriter().write(
            "{\"code\":\"AUTHENTICATION_FAILED\","
          + "\"message\":\"Đăng nhập không thành công.\"}"
        );
    };
}

@Bean
SecurityFilterChain webSecurity(
        HttpSecurity http,
        AuthenticationFailureHandler genericLoginFailureHandler)
        throws Exception {

    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    http.formLogin(form ->
            form.failureHandler(genericLoginFailureHandler));

    return http.build();
}
~~~

**Các điểm cần ghi nhớ:**

1. `failureHandler` nhận `AuthenticationException`; có thể ghi log nội bộ (an toàn) nhưng **không đưa `exception.getMessage()` hay subclass vào response**.
2. `http.formLogin(...)` xử lý luồng form login Servlet, thường nhận username/password dạng form parameters. Đoạn code không định nghĩa REST JSON login filter và không hỗ trợ “POST JSON” chỉ nhờ thay `Content-Type` trả về.
3. Việc phản hồi `401` JSON thích hợp cho client của luồng này nếu client được thiết kế tương ứng. Nếu ứng dụng cần HTML redirect, mọi lỗi nhạy cảm nên tới **cùng** trang `/login?error` và cùng thông báo chung.
4. CSRF vẫn cần xử lý đúng: đối với browser session/cookie, request POST thiếu CSRF token có thể bị `403` **trước khi xác thực**. Đó không phải tín hiệu account bị khóa và không nên vô hiệu CSRF tùy tiện.
5. `SecurityFilterChain` có thể được cấu hình theo nhiều chain, mỗi chain có filter/entry point/failure handler khác nhau. Phải kiểm tra đúng chain thực sự xử lý `/login`; một handler trong chain khác không bảo vệ endpoint hiện tại.
6. Login dùng HTTP Basic, bearer token, OAuth2/OIDC, passkey hay custom filter có failure/entry point riêng. Chính sách **generic public response** phải được áp dụng ở đúng ranh giới của từng cơ chế.

### Nếu chỉ dùng form redirect

Một định hướng đơn giản cho HTML form là:

~~~java
// MÃ MINH HỌA: cùng URL cho tất cả lỗi auth ở login form.
http.formLogin(form -> form
        .failureUrl("/login?error"));
~~~

Ứng dụng cần bảo đảm trang `/login` được phép truy cập khi chưa đăng nhập và chỉ hiển thị text chung, **không** dùng query parameter chứa nguyên nhân chi tiết. Đừng trả `/login?locked=true` hoặc `/login?user_exists=false`.

## 8. API tự viết gọi AuthenticationManager

Nếu controller thực sự gọi `authenticationManager.authenticate(...)`, áp dụng mapping ở tầng HTTP boundary:

~~~java
// MÃ PHÁC THẢO: chưa phải class độc lập.
// Chỉ áp dụng khi đã có AuthenticationManager + request DTO,
// security context/session strategy và rate limiter phù hợp.
try {
    Authentication auth = authenticationManager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                    body.username(), body.password()
            )
    );

    // Xử lý success bằng cơ chế web được thiết kế đầy đủ.
} catch (AuthenticationException ex) {
    auditSafely(ex); // internal only, không log credential

    return ResponseEntity.status(401)
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                    "code", "AUTHENTICATION_FAILED",
                    "message", "Đăng nhập không thành công."
            ));
}
~~~

Không dùng ví dụ này để thay `formLogin` mà bỏ các bước quản lý session, session fixation protection, CSRF, security context persistence, logout, failure throttling và auditing. Nếu hệ thống có endpoint custom, phải thiết kế **trọn vẹn** vòng đời đăng nhập, không chỉ khối `try/catch`.

`@ControllerAdvice` cho controller không mặc định xử lý exception đã bị filter Spring Security bắt. Khi viết tests, phải gửi request qua **security filter chain thật**, không chỉ gọi trực tiếp method Java.

## 9. Luồng “Quên mật khẩu” cũng phải chống dò tài khoản

### 9.1. Thông báo an toàn

**Không nên:**

~~~text
Email này không có trong hệ thống.
Đã gửi email reset tới tài khoản an@example.com.
Tài khoản này đang bị khóa nên không thể reset.
~~~

**Nên (cho request công khai):**

~~~text
Nếu tài khoản phù hợp tồn tại, chúng tôi sẽ gửi hướng dẫn qua kênh liên hệ đã đăng ký.
~~~

Đầu ra **không tiết lộ tài khoản có tồn tại hay không**. Có thể dùng `202 Accepted` để biểu diễn request đã được tiếp nhận xử lý, nhưng chỉ khi endpoint được thiết kế như một tác vụ async; không nên dùng status đó để cam kết email chắc chắn đã được gửi.

### 9.2. Kiến trúc đề xuất

~~~text
POST /forgot-password
       |
       v
Validate cú pháp email (như nhau cho account có/không)
       |
       v
Rate limit / abuse detection không phụ thuộc userExists
       |
       v
Tạo response công khai cố định
       |
       v
Queue xử lý bên trong
       |
       +-- Nếu account hợp lệ, phát token reset ngẫu nhiên
       |   có TTL ngắn, one-time use, lưu hash/ID bảo vệ
       |   và gửi qua kênh đã đăng ký.
       |
       +-- Nếu account không tồn tại, không phát token
           và không tiết lộ sự khác biệt qua HTTP.
~~~

Queue và xử lý async giúp giảm khác biệt thời gian “có email thật → gửi email” so với “không có user → trả ngay”. Tuy nhiên, vẫn phải kiểm tra kích thước payload, đường đi network, status code, race, rate limiting và lỗi gửi mail có tạo ra dấu hiệu quan sát được không. Không có giải pháp timing tuyệt đối chỉ bằng một queue.

### 9.3. Chống lạm dụng cơ chế phục hồi

Nếu một người có thể gửi hàng nghìn email reset, hệ thống trở thành công cụ quấy rối. Cần giới hạn theo IP/thiết bị, tín hiệu rủi ro, định danh có thể băm bằng HMAC server-side, giới hạn gửi mail, thời hạn token, audit và thông báo an toàn cho chủ tài khoản.

Lúc sử dụng reset token, **đó là một luồng chứng minh quyền sở hữu khác**; sau khi token được xác minh đầy đủ, hệ thống có thể cung cấp hướng dẫn cụ thể phù hợp. Không nên biến trang nhập email ban đầu thành endpoint kiểm tra tồn tại tài khoản.

## 10. Đăng ký mới cũng có thể tiết lộ tài khoản

Một API tạo account công khai dễ trả:

~~~text
409 Conflict: Email đã được sử dụng.
201 Created: Đăng ký thành công.
~~~

Nếu attacker chỉ cần biết email nào đã đăng ký, đây là một oracle. Tùy yêu cầu sản phẩm có thể cần trade-off về UX, nhưng phải **nhận diện và quyết định rủi ro**, không xem đó là tình tiết không liên quan đến bảo mật.

Các cách giảm rò rỉ:

- Đăng ký theo email và gửi quy trình xác minh ownership; trả phản hồi trung tính “Nếu địa chỉ đủ điều kiện, hãy kiểm tra email để tiếp tục”.
- Không tiết lộ tài khoản hiện hữu khi gửi lại email kích hoạt hoặc lời mời.
- Vẫn enforce unique email/username trong database/identity service và xử lý concurrent requests; generic response **không thay unique constraint**.
- Giới hạn tốc độ, CAPTCHA/challenge thích nghi nếu cần; kiểm thử bot có thể suy ra account qua khác biệt về captcha hoặc thời gian không.
- Khi doanh nghiệp buộc phải báo “email đã tồn tại” vì UX, coi đây là **quyết định công bố có chủ đích**, kết hợp rate limiting, monitoring và xem xét mức độ nhạy cảm của dịch vụ.

Không dùng email đã xác minh ở hệ thống khác làm bằng chứng một requester có quyền xem trạng thái tài khoản tại sản phẩm này.

## 11. Khóa tài khoản, throttling và nguy cơ denial-of-service

Khóa tài khoản là cơ chế phòng brute-force, nhưng thực hiện đơn giản có thể tạo **hai lỗ hổng**:

1. Nếu UI trả “account locked” cho user có thật, attacker dò được trạng thái.
2. Nếu vài login sai có thể khóa vĩnh viễn một username, attacker có thể chủ động khóa tài khoản của người khác (**account lockout DoS**).

Chính sách thực tế nên cân nhắc:

- Rate limit theo nhiều tín hiệu: IP/thiết bị, nguồn mạng, username canonicalized hoặc khóa HMAC, session, hành vi bất thường. Không dùng IP duy nhất nếu có NAT/proxy; không tin `X-Forwarded-For` từ client không đáng tin.
- Chậm dần/adaptive delay/challenge/risk scoring khi nhiều lần thất bại; giới hạn chi phí xử lý hash để tránh bị bão tài nguyên.
- Nếu áp dụng account lockout, ưu tiên khóa tạm/thời hạn hợp lý và có kênh phục hồi phù hợp; điều chỉnh theo loại tài khoản.
- **Giữ cùng phản hồi công khai cho locked/disabled/unknown**; chính sách limit/captcha không được chỉ kích hoạt đối với username có thật theo cách có thể quan sát.
- Thông báo chủ tài khoản qua **kênh đã xác minh** nếu phát hiện đăng nhập lạ/khóa, nhưng chống spam và không tạo feedback oracle ở login.
- Không để exception stack trace hoặc counter chi tiết lộ qua GraphQL errors, endpoint metrics công khai hay web socket.

**HTTP 429** có thể cần thiết khi vượt rate limit; nếu client nhận `429` chỉ sau khi thử một username có thật, nó vẫn là side channel. Phải kiểm thử cả **thứ tự** “check username tồn tại → giới hạn” và “giới hạn trước khi truy vấn account”.

## 12. Timing: nội dung giống nhau vẫn có thể bị dò

Ví dụ backend naive:

~~~java
// MÃ PHÁC THẢO KHÔNG AN TOÀN.
UserDetails user = users.find(username);

if (user == null) {
    return genericFailure(); // rất nhanh
}

if (!passwordEncoder.matches(rawPassword, user.getPassword())) {
    return genericFailure(); // BCrypt tốn thời gian hơn
}
~~~

Hai nhánh trả text giống nhau, nhưng thời gian trung bình khác. Attackers có thể gửi nhiều mẫu để ước lượng phân phối thời gian, nhất là khi rate limit yếu.

### Hướng phòng thủ nhiều lớp

1. **Dùng provider chuẩn** thay vì tự xây handler password nếu không cần. `DaoAuthenticationProvider` có xử lý việc xác minh credential và ẩn user-not-found trong phạm vi của nó; tuy vậy không được tuyên bố mọi nhánh luôn constant-time.
2. Khi tự xây password provider, thiết kế **dummy password-hash verification** cho username không tồn tại nếu phù hợp, dùng hash được cấu hình cùng thuật toán/cost. Không dùng dummy user như account có thể login, và phải bảo đảm username không tồn tại luôn thất bại.
3. Đừng trả nguyên thông điệp/loại lỗi; chuẩn hóa status, body và các header liên quan.
4. Cân nhắc xử lý async cho reset và thông báo email để loại bỏ chi phí gửi ngoài luồng phản hồi.
5. Dùng rate limiting, threat detection và monitoring để giảm khả năng thu thập mẫu timing ở quy mô lớn.
6. Đo **phân phối độ trễ theo nhóm trường hợp** dưới tải thực tế; không chỉ đo một lần.
7. Không thêm một `Thread.sleep(500)` cố định rồi tuyên bố đã hết timing oracle. Jitter mạng, nhánh DB, cache, state checks, rate limiter và CPU vẫn tạo khác biệt; random sleep thậm chí có thể tăng tải, không phải giải pháp xác minh.

**Lưu ý:** Một số provider kiểm tra trạng thái locked/disabled **trước** kiểm tra password, nên độ trễ có thể khác. Để đạt bảo vệ tốt hơn cần threat model thực tế và kiểm thử ở boundary ngoài hệ thống. Không can thiệp vào account-state checks để “làm đều thời gian” mà vô tình cấp đăng nhập sai.

## 13. Thông báo cho người dùng thật mà không tiết lộ cho người lạ

Generic response thường kém tiện lợi hơn “tài khoản đang khóa”. Có thể dung hòa:

- **Màn hình login công khai:** “Đăng nhập không thành công. Hãy kiểm tra thông tin hoặc chọn hỗ trợ.”
- **Email khôi phục:** gửi hướng dẫn đến địa chỉ **đã được kiểm chứng từ trước** mà không nói trong HTTP có email được gửi hay không.
- **Trong session đã xác thực:** cung cấp thông báo trạng thái hoặc hướng dẫn khi mức tin cậy của session cho phép; cần kiểm tra tình huống session cũ có thể bị chiếm.
- **Sau step-up** (MFA, recovery code, link one-time, xác minh danh tính): có thể cung cấp nguyên nhân hoặc thao tác mở khóa theo policy.
- **Bộ phận support:** phải có quy trình xác minh danh tính/ủy quyền của người gọi trước khi xem hoặc tiết lộ account status.

Không trả “tài khoản đã bị khóa” ngay khi client nhập một email hợp lệ vì **biết email không phải bằng chứng sở hữu email**.

Khi dùng ngôn ngữ trung tính, vẫn cần đáp ứng accessibility và hướng dẫn người dùng hành động được: ví dụ nút “Quên mật khẩu?” hoặc “Liên hệ hỗ trợ”, thay vì thông báo mơ hồ không có bước tiếp theo.

## 14. Audit an toàn và quan sát tấn công

Một event nội bộ được cấu trúc, ví dụ:

~~~json
{
  "event": "authentication_failed",
  "reason": "ACCOUNT_LOCKED",
  "request_id": "req_example",
  "source_group": "network-risk-bucket",
  "occurred_at": "2026-11-05T00:00:00Z"
}
~~~

**Chỉ là JSON minh họa nội bộ**, không phải response công khai. Thời gian/ID giả; không chứa raw username, password, bearer token hoặc cookie. Nếu cần theo dõi theo user để chống abuse, dùng định danh nội bộ/pseudonym và chính sách retention/quyền xem; một HMAC keyed digest có thể giúp nhóm sự kiện mà giảm lộ username trực tiếp, nhưng không biến dữ liệu thành vô hại.

Audit thường cần theo dõi:

| Metric/sự kiện | Mục đích |
| --- | --- |
| Số lần `authentication_failed` theo nhóm nguyên nhân | Phát hiện brute-force, credential stuffing hoặc lỗi cấu hình |
| Số lần rejected do locked/disabled | Quan sát policy, hỗ trợ chủ tài khoản qua kênh xác minh |
| Số request `forgot-password`, giới hạn mail | Phát hiện abuse/recovery spam |
| Chênh lệch response time các nhóm thất bại | Phát hiện timing oracle |
| Tần suất `429` và challenge | Đo hiệu quả/rủi ro của rate limiting |
| Username probing từ nguồn bất thường | Phát hiện phân phối enumeration |
| Tỉ lệ lỗi theo filter chain/API version | Tránh bỏ sót endpoint không áp chính sách chung |

Không cho người chưa đăng nhập truy cập các metric hoặc log chứa lý do chi tiết. Với hệ thống đa node, dùng correlation/request ID, kiểm soát độ chính xác thời gian và tránh ghi credential vào tracing baggage.

## 15. Kiểm thử API: một ma trận phản hồi đầy đủ

### 15.1. Tạo các fixture riêng biệt

Chuẩn bị user có các trạng thái:

1. Username **không tồn tại**.
2. Username tồn tại, **mật khẩu sai**.
3. Account **locked**.
4. Account **disabled**.
5. Account **expired**.
6. Credentials **expired**.
7. Tài khoản bình thường với **credential đúng**.

Với mỗi trường hợp thất bại, gửi request qua **cùng endpoint**, cùng giao thức và cùng cơ chế rate limit/challenge trừ các khác biệt được chấp nhận, rồi kiểm tra:

| Thuộc tính | Kỳ vọng cho nhóm thất bại nhạy cảm |
| --- | --- |
| Status | Cùng status trong cùng endpoint; ví dụ `401` |
| `Content-Type` | Cùng media type/charset |
| Body JSON/HTML | Cùng schema, code và nội dung chung |
| Redirect URL | Cùng URL, không có query ghi reason |
| Header | Không chứa account-state marker/username; các header có ý nghĩa giống nhau |
| Cookie | Không cấp phiên authenticated; không phân biệt user tồn tại |
| Timing | Không có chênh lệch dễ khai thác trong kiểm thử phân phối dưới tải/điều kiện tương đương |
| Rate-limit | Không tạo oracle theo username tồn tại |
| Reset/signup | Không có phản hồi “found/not found” qua các lớp quan sát công khai |
| Nội bộ | Audit ghi đúng nguyên nhân, nhưng không lộ cho client |
| Success | Chỉ credential hợp lệ + account đủ điều kiện mới được login |

### 15.2. Ví dụ kiểm thử tích hợp (minh họa)

Đoạn code bên dưới **không độc lập chạy**, vì phụ thuộc `MockMvc`, security config, seed user, fake clock và các endpoint trong project. Nó biểu đạt hợp đồng cần kiểm tra:

~~~java
// PSEUDO-TEST trong Spring Boot integration test; không standalone.
var wrongPassword = login("an", "bad");
var unknownUser = login("nonexistent", "bad");
var locked = login("binh", "any");
var disabled = login("chi", "any");

assertThat(wrongPassword.getStatus()).isEqualTo(401);
assertThat(unknownUser.getStatus()).isEqualTo(401);
assertThat(locked.getStatus()).isEqualTo(401);
assertThat(disabled.getStatus()).isEqualTo(401);

assertThat(unknownUser.getContentAsString())
        .isEqualTo(wrongPassword.getContentAsString());
assertThat(locked.getContentAsString())
        .isEqualTo(wrongPassword.getContentAsString());
assertThat(disabled.getContentAsString())
        .isEqualTo(wrongPassword.getContentAsString());

// Kiểm tra thêm headers, redirect, cookies, rate-limit,
// các response khi user expired/credentials expired và timing.
~~~

Nên chạy test qua **`SecurityFilterChain` thực tế** bằng `MockMvc` hoặc test HTTP end-to-end, không chỉ gọi trực tiếp Java failure mapper. Nếu có nhiều chain/tenant/locale, thử đủ các biến thể. Với hệ thống distributed, đo timing và phản hồi từ điểm attacker thật sự nhìn thấy, không chỉ trong local unit test.

### 15.3. Test hiệu năng có ý nghĩa

Đặt số lượng mẫu phù hợp và so sánh **phân phối** latency của username không tồn tại, sai password, locked, disabled trong điều kiện cache/warmup/DB tương đương. Giới hạn tải, thực hiện trên môi trường được cho phép, tránh tạo traffic tấn công production. Không tự tuyên bố “constant-time” dựa trên average của vài request.

Kiểm tra `Content-Length` khi nén, header `Retry-After`, cookie, 302 Location, email side effect và response khi backend timeout. Đặc biệt phải thử lúc cache miss, worker xử lý reset, lỗi DB và rate limit.

## 16. Các lỗi triển khai thường gặp

| Lỗi | Vì sao có thể bị khai thác | Hướng sửa |
| --- | --- | --- |
| `return ex.getMessage()` trong failure handler | Lộ “User account is locked”/“User is disabled” | Trả chuỗi generic cố định, audit riêng |
| Catch `BadCredentialsException` nhưng không catch `LockedException` | Locked đi qua đường phản hồi khác | Chuẩn hóa toàn bộ nhóm `AuthenticationException` theo threat model |
| `hideUserNotFoundExceptions=false` cho login công khai | Lộ lớp exception của username không tồn tại | Để mặc định true và vẫn chuẩn hóa boundary |
| Return `404` cho username không tồn tại, `401` cho password sai | HTTP status thành account oracle | Dùng cùng status cho nhóm lỗi |
| Dùng `/login?locked=true` | URL/redirect tiết lộ trạng thái | Dùng `/login?error` chung |
| Tạo `X-Reason` hoặc GraphQL extensions reason | Client dù text giống nhau vẫn đọc metadata | Không xuất lý do trong bất kỳ field công khai nào |
| Username không có → skip BCrypt; có user → BCrypt | Timing khác nhau | Provider chuẩn, dummy verification khi tự viết, rate-limit và đo |
| Captcha chỉ xuất hiện cho username thật | Challenge thành account oracle | Dùng risk policy không phân biệt existence theo cách lộ |
| Reset password trả “Email không tồn tại” | Dò được tài khoản qua API công khai | Trả neutral receipt và xử lý trong backend |
| Rate limit chỉ khi userExists=true | Khác biệt `429` theo username | Rate-limit trước lookup hoặc theo tín hiệu không lộ |
| Đăng ký trả `409` cho tài khoản có thật trong dịch vụ nhạy cảm | Signup trở thành oracle | Cân nhắc xác minh email + generic response |
| Account lock vĩnh viễn sau vài lần sai | Đối thủ làm khóa hàng loạt (DoS) | Lockout có giới hạn, adaptive throttle/recovery |
| Tự trả `200 OK` cho mọi lỗi hạ tầng | Che hỏng hệ thống và phá client semantics | Phân biệt lỗi vận hành an toàn, không lộ nguyên nhân account |
| `@ControllerAdvice` nhưng filter có handler khác | Handler không được gọi | Cấu hình đúng `SecurityFilterChain`/filter |
| Log/password trong response debug | Rò credential/PII | Internal audit có kiểm soát, không phơi secrets |
| Test chỉ so message | Status/headers/timing vẫn phân biệt | Test toàn bộ contract + side effects |
| Mặc định role/account state từ client | Cho phép bypass policy | Provider kiểm tra trạng thái từ nguồn tin cậy |

**Đừng “sửa” enumeration bằng cách cho phép login của account locked hoặc disabled.** Việc thực thi chính sách khóa vẫn phải đúng; chỉ phản hồi công khai mới được chuẩn hóa.

## 17. Khác biệt theo authentication mechanism

| Cơ chế | Điểm chặn thông tin dễ rò |
| --- | --- |
| `formLogin` Servlet | `AuthenticationFailureHandler`, redirect URL, trang login, CSRF và session |
| HTTP Basic | `AuthenticationEntryPoint`/WWW-Authenticate, status và thông điệp lỗi |
| REST JSON login custom | Controller/filter riêng, mapper exception và context persistence |
| OAuth2/OIDC login | IdP có thể trả error code riêng; mapping tại callback và hợp đồng với IdP, không tùy tiện lộ account linking state |
| Password reset/activation | API nhận request, email/SMS side effects, token validation và rate limit |
| OTP/MFA | Không trả “user này chưa bật MFA” cho anonymous khi trạng thái đó nhạy cảm; giữ policy per-state có xác minh |
| Resource Server Bearer | Phân biệt token invalid/expired và thiếu quyền theo giao thức; không đính account trạng thái riêng vào error một cách tùy tiện |
| WebFlux | `ServerAuthenticationFailureHandler`/WebFilter và context reactive; không sao chép nguyên config Servlet |

Đừng ép mọi trường hợp về một JSON `AUTHENTICATION_FAILED` theo cách **phá tiêu chuẩn protocol**, chẳng hạn HTTP challenge bắt buộc hoặc phản hồi của OAuth/OIDC. Mục tiêu là không tiết lộ **sự tồn tại/trạng thái tài khoản** vượt quá thông tin protocol thực sự cần.

## 18. Checklist review trước production

1. **Threat model:** liệt kê login, signup, reset, unlock, resend activation, SSO callback và API liên quan đến danh tính.
2. **User state:** đảm bảo locked/disabled/expired thật sự bị từ chối; không làm yếu xác thực để đồng nhất phản hồi.
3. **Generic public mapping:** có chính sách status/body/error code/redirect/header cho tất cả trường hợp auth thất bại nhạy cảm.
4. **Spring Security:** kiểm tra `hideUserNotFoundExceptions=true` ở username/password provider và cấu hình failure handler của chain đúng.
5. **Không dùng `ex.getMessage()` công khai:** response không có exception type, stack trace hoặc internal reason.
6. **Timing:** cân nhắc hash cost, dummy verification trong custom provider, async reset và phân phối latency; không hứa constant-time tuyệt đối.
7. **Abuse prevention:** rate limiting/adaptive protection, tránh per-account lockout DoS và CAPTCHA oracle.
8. **Recovery:** generic response cho anonymous; sau ownership verification mới đưa ra thông tin trạng thái/hướng dẫn cụ thể.
9. **Audit:** internal reason/metrics phục vụ support, có bảo vệ quyền xem, không chứa credentials.
10. **Regression tests:** so sánh response public cho unknown/bad/locked/disabled/expired, cả JSON, HTML, status, headers, redirects, cookies.
11. **Hoạt động phân tán:** load balancer, cache, IdP, email queue, replicas và error paths không tạo khác biệt quan sát rõ ràng.
12. **Documentation:** quy định trường hợp được phép công bố account existence cho UX, ai phê duyệt và biện pháp bù trừ.
13. **Tài khoản nhạy cảm:** admin/privileged/recovery xử lý rate limit, MFA và thông báo theo mức độ rủi ro.
14. **Accessibility:** thông điệp chung vẫn chỉ đường đến recovery/support có xác minh, không gây bế tắc cho người dùng thật.

## 19. Câu hỏi tự kiểm tra

**1.** Hai endpoint login cùng trả “Đăng nhập không thành công”, nhưng username không tồn tại trả HTTP 404 và account locked trả HTTP 423. Đã ngăn enumeration chưa?  
**Trả lời:** Chưa. Status code là một kênh quan sát; phải chuẩn hóa contract cho nhóm lỗi nhạy cảm.

**2.** Vì sao `setHideUserNotFoundExceptions(true)` không đủ để che account locked?  
**Trả lời:** Nó xử lý riêng UsernameNotFoundException; `LockedException`/`DisabledException` vẫn có thể phát sinh và bị failure handler công khai nếu không chuẩn hóa.

**3.** Có nên xem `exception.getMessage()` là thông báo UI đăng nhập?  
**Trả lời:** Không. Message là thông tin kỹ thuật, có thể phản ánh khóa/disable, provider hoặc nội bộ; public mapper chọn text chung riêng.

**4.** Người dùng nhập email ở “Quên mật khẩu”, nhưng API trả “Không tìm thấy email”. Nguy cơ gì?  
**Trả lời:** Endpoint biến thành nơi dò tài khoản. Nên trả thông báo trung tính và gửi hướng dẫn qua kênh đã xác minh khi đủ điều kiện.

**5.** Một form có message generic và status giống nhau nhưng username có thật mất 200 ms, username không có thật mất 3 ms. Nguy cơ?  
**Trả lời:** Timing side channel. Cần giảm khác biệt theo cách có kiểm thử, kết hợp rate limit, không chỉ thêm sleep.

**6.** Tại sao không nên cho mọi lần thử sai lập tức khóa tài khoản vô thời hạn?  
**Trả lời:** Kẻ tấn công có thể cố tình khóa tài khoản người khác; nên có chính sách throttle/lockout và recovery phù hợp.

**7.** Sau khi một người đã hoàn thành xác minh email/step-up, có được hướng dẫn họ cách mở khóa cụ thể không?  
**Trả lời:** Có thể, nếu quy trình kiểm chứng danh tính/ủy quyền đáp ứng mức rủi ro. Không nhầm với login công khai chỉ biết username.

**8.** Test unit `failureMapper(BadCredentialsException)` trả message chung đã đủ chưa?  
**Trả lời:** Chưa. Cần test cả Locked/Disabled/Expired, filter chain thật, header/status/redirect, tốc độ và các API reset/signup khác.

**9.** “Internal audit có reason=LOCKED” có trái với việc chống enumeration không?  
**Trả lời:** Không, miễn là audit không được tiết lộ cho người chưa xác minh, có bảo vệ quyền truy cập và không log dữ liệu nhạy cảm.

## 20. Tham khảo chính thức

- [OWASP Authentication Cheat Sheet – Authentication and Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages): generic errors, timing và các kênh lộ account existence.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): thông điệp nhất quán và quy trình recovery.
- [OWASP Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): chống tấn công tự động, rate limit và adaptive defenses.
- [Spring Security 6.5 – AbstractUserDetailsAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): `hideUserNotFoundExceptions` và account checks.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`/`AuthenticationProvider` và các loại AuthenticationException.
- [Spring Security 6.5 – AuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): xử lý xác thực thất bại ở filter.
- [Spring Security 6.5 – UsernamePasswordAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/UsernamePasswordAuthenticationFilter.html): form login.
- [Spring Security 6.5 – UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): locked, enabled, account expired và credentials expired.

**Tóm lại:** Hệ thống phải **kiểm chứng và từ chối đúng theo trạng thái account ở bên trong**, nhưng **không cho người chưa xác minh phân biệt những trạng thái đó qua phản hồi công khai**. Thành công ở mặt câu chữ thôi chưa đủ: kiểm tra HTTP status, JSON, headers, URL, timing, rate limit, recovery và các luồng ngoại lệ; chỉ công bố thông tin trạng thái sau khi đã chứng minh quyền sở hữu phù hợp.
