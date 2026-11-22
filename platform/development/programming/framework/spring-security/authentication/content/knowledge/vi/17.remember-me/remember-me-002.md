# RememberMeServices, RememberMeAuthenticationFilter và provider tương ứng

> **Ngữ cảnh:** Spring Security — authentication, nhóm **Ghi nhớ đăng nhập**. Bài viết dùng Spring Security **Servlet 6.x**, ví dụ đầy đủ với **Spring Boot 3.3.5 / Java 17+ / Maven**. Trọng tâm là mối quan hệ giữa `RememberMeServices`, `RememberMeAuthenticationFilter` và `RememberMeAuthenticationProvider`; cơ chế phát/kiểm tra cookie remember-me; mức độ tin cậy của danh tính được khôi phục; và cách triển khai, kiểm thử an toàn.

## 1. Remember-me giải quyết việc gì?

Khi người dùng đóng trình duyệt, session HTTP có thể hết hạn hoặc cookie phiên `JSESSIONID` bị xóa. Nếu họ đã chủ động chọn **"Ghi nhớ đăng nhập"**, ứng dụng có thể phát một cookie nhớ đăng nhập có thời hạn dài hơn cookie phiên. Ở lần truy cập sau, Spring Security dùng cookie đó để **tái tạo `Authentication`** mà không yêu cầu người dùng nhập lại password ngay lúc ấy.

Đây là một cơ chế **đăng nhập lại tự động từ một credential tồn tại dài hạn trong cookie**, không phải chức năng "giữ session mãi mãi". Cookie remember-me phải được coi là **credential nhạy cảm**: người chiếm đoạt có thể giả mạo người dùng trong thời gian cookie còn hiệu lực, tùy loại token và chính sách thu hồi.

Ví dụ hành vi người dùng:

1. Người dùng mở `GET /login` và điền username/password.
2. Người dùng **tích chọn** `remember-me` rồi gửi `POST /login`. Sau khi credential được kiểm chứng, ứng dụng phát cookie `remember-me` cho browser.
3. Người dùng tiếp tục dùng session HTTP bình thường. Khi session còn `SecurityContext` hợp lệ, Spring Security không cần dùng cookie nhớ đăng nhập ở mọi request.
4. Sau khi session biến mất nhưng cookie `remember-me` vẫn còn, request đến một URL được bảo vệ kích hoạt luồng auto-login.
5. Cookie hợp lệ → server xác định user, lấy authorities đáng tin từ `UserDetailsService` và đặt remember-me authentication vào `SecurityContext`. Cookie không hợp lệ/hết hạn → không đăng nhập lại; endpoint được bảo vệ sẽ yêu cầu đăng nhập.
6. Một endpoint nhạy cảm như đổi mật khẩu hoặc chuyển tiền có thể yêu cầu **`fullyAuthenticated()`** để buộc nhập lại credential, thay vì tin chỉ vào remember-me.

### Phân biệt session và remember-me

| Tiêu chí | Session HTTP | Remember-me |
| --- | --- | --- |
| Dấu vết phía browser | Cookie phiên, thường `JSESSIONID` | Cookie tồn tại dài hơn, mặc định thường mang tên `remember-me` |
| Nguồn danh tính cho request kế tiếp | `SecurityContextRepository` đọc context trong session | `RememberMeServices` xác minh cookie khi thiếu `Authentication` |
| Sự kiện tạo | Login thành công và lưu context/session | Login thành công **và** user yêu cầu remember-me (trừ cấu hình `alwaysRemember`) |
| Dữ liệu phía server | Nội dung phiên do container/session store giữ | Token-based: không cần bảng token; persistent-based: có `PersistentTokenRepository` |
| Độ tin cậy | Fresh/interactive login thường được coi là fully authenticated | Remembered login có mức tin cậy **thấp hơn** đối với `fullyAuthenticated()` |
| Logout | Có thể invalidate session và xóa context | Đồng thời phải xóa cookie; phương pháp thu hồi bản copy phụ thuộc loại token |
| Nguy cơ | Session hijacking/fixation | Replay cookie nhớ đăng nhập, token bị đánh cắp, lifetime dài |

**Không nhầm:** `RememberMeAuthenticationToken.isAuthenticated() == true` **không có nghĩa là** `fullyAuthenticated() == true`. Spring Security dùng `AuthenticationTrustResolver` để phân biệt remembered với authentication tương tác đầy đủ.

## 2. Ba thành phần chính và hợp đồng của chúng

### 2.1. `RememberMeServices` — phát, hủy, và đọc cookie

Interface `org.springframework.security.web.authentication.RememberMeServices` cung cấp ba phương thức cốt lõi:

```java
Authentication autoLogin(
    HttpServletRequest request,
    HttpServletResponse response);

void loginSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication successfulAuthentication);

void loginFail(
    HttpServletRequest request,
    HttpServletResponse response);
```

Đây là **chữ ký API rút gọn để học**; cần các import Servlet và Spring Security tương ứng nếu đặt vào tệp Java. Ý nghĩa:

- `loginSuccess`: authentication filter tương tác báo người dùng vừa login thành công. Dịch vụ kiểm tra yêu cầu "remember me" (thường tham số form `remember-me`). Nếu được chọn, nó ký/phát cookie hoặc lưu token rồi phát cookie.
- `loginFail`: tương tác login thất bại; dịch vụ có thể xóa cookie remember-me đã trình, tránh giữ một cookie không còn phù hợp.
- `autoLogin`: request mới chưa có authentication, dịch vụ đọc cookie, kiểm tra định dạng, hạn, chữ ký hoặc bản ghi server; nếu thành công trả đối tượng `Authentication` thích hợp, nếu không thể dùng cookie thường trả `null` hoặc ném `AuthenticationException`.

Hai implementation tiêu biểu của Spring Security:

- `TokenBasedRememberMeServices` — token ký dựa trên user/password hash, hạn và khóa bí mật; **không cần database token riêng**.
- `PersistentTokenBasedRememberMeServices` — series/token ngẫu nhiên có bản ghi trong `PersistentTokenRepository`, thường lưu bằng JDBC; token được đổi khi dùng theo thiết kế.

Cả hai thường cần `UserDetailsService` để tìm user và authorities hiện tại sau khi xác minh cookie. Nếu ứng dụng chỉ có LDAP/custom provider nhưng không cung cấp `UserDetailsService` cho remember-me, cấu hình phải được bổ sung thích hợp.

### 2.2. `RememberMeAuthenticationFilter` — nơi kích hoạt auto-login

`RememberMeAuthenticationFilter` thuộc Servlet `SecurityFilterChain`. Filter chỉ cố tự đăng nhập khi **`SecurityContext` hiện chưa có `Authentication`**. Nó gọi:

```text
RememberMeServices.autoLogin(request, response)
    -> Authentication candidate hoặc null
    -> nếu candidate khác null:
         AuthenticationManager.authenticate(candidate)
         -> Authentication đã được manager chấp nhận
         -> đặt vào SecurityContext
         -> tiếp tục filter chain
    -> nếu thất bại:
         dọn context/cookie theo triển khai
         -> tiếp tục như anonymous / đi tới entry point khi cần
```

Điểm cần nhấn mạnh:

1. Filter **không** đọc password thô từ form ở mọi request. Nó sử dụng cookie remember-me.
2. Filter **không** tự ý coi mọi cookie là hợp lệ. Dịch vụ nhớ đăng nhập kiểm chứng nội dung cookie; manager/provider kiểm tra token nội bộ.
3. Nếu session đã mang `Authentication`, remember-me filter thường **bỏ qua** auto-login. Vì vậy một người cùng lúc có cookie nhớ đăng nhập và session login vẫn có thể đang dùng authentication tương tác đầy đủ.
4. Khi nhớ đăng nhập thành công, cấu hình filter/repository có thể lưu context để request tiếp theo dùng session; cookie vẫn là căn cứ khôi phục khi session không còn.
5. Filter không có nghĩa là mọi API stateless/JWT sẽ tự có chức năng remember-me; nó thuộc luồng Servlet cookie được cấu hình cho web app.

### 2.3. `RememberMeAuthenticationProvider` — kiểm tra token nội bộ

`RememberMeAuthenticationProvider` xử lý `RememberMeAuthenticationToken`. Provider này kiểm tra **key hash** của token có khớp khóa được cấu hình hay không. Nó **không xác minh lại username/password thô** như `DaoAuthenticationProvider` và cũng **không phải** thành phần trực tiếp kiểm tra chữ ký cookie browser.

Ranh giới chính xác:

| Bước | Thành phần | Đang kiểm tra gì? |
| --- | --- | --- |
| POST /login | `UsernamePasswordAuthenticationFilter` + `DaoAuthenticationProvider` | Username/password, password hash, trạng thái user |
| Login thành công có tick remember-me | `RememberMeServices.loginSuccess` | Có opt-in và cách sinh cookie/token |
| Request sau không còn session auth | `RememberMeAuthenticationFilter` | Có cần thử auto-login không? |
| Kiểm chứng cookie dài hạn | `TokenBasedRememberMeServices` hoặc `PersistentTokenBasedRememberMeServices` | Token integrity, expiry, bản ghi trong repository nếu có, tìm user |
| Chấp nhận `RememberMeAuthenticationToken` | `RememberMeAuthenticationProvider` | Token được tạo bằng **key của ứng dụng đáng tin** |
| Phân quyền endpoint | `AuthorizationFilter` + `AuthenticationTrustResolver` | `authenticated()`, `fullyAuthenticated()` và authority |

**Khóa phải đồng bộ:** `RememberMeServices` và `RememberMeAuthenticationProvider` cần thống nhất `key`. Nếu cấu hình provider bằng khóa khác khóa dịch vụ, auto-login không được chấp nhận. Ngược lại, đừng cho phép client tự tạo `RememberMeAuthenticationToken` với quyền tự chọn và đặt vào context — token này chỉ được tạo bên trong cơ chế server đáng tin sau khi cookie đã được xác minh.

Với Java DSL `http.rememberMe(...)` của Spring Security, framework kết nối filter, services và provider tương ứng. Thường **không cần** tự `new RememberMeAuthenticationFilter` và tự thêm provider nếu chỉ dùng remember-me tiêu chuẩn.

## 3. Luồng chi tiết: login lần đầu, mất session và quay trở lại

```text
GIAI ĐOẠN A — LOGIN TƯƠNG TÁC

Browser POST /login
  | username=alice, password=demo-pass123, remember-me=on, CSRF hợp lệ
  v
UsernamePasswordAuthenticationFilter
  |-> AuthenticationManager -> DaoAuthenticationProvider
  |      -> UserDetailsService + PasswordEncoder
  |      -> Authentication tương tác đã xác thực
  |
  +-> SessionAuthenticationStrategy / SecurityContextRepository
  |      -> tạo / đổi session ID và lưu SecurityContext
  |
  +-> RememberMeServices.loginSuccess(request, response, authenticated)
         -> cookie remember-me được phát (nếu opt-in)
  v
HTTP 302 + Set-Cookie: remember-me=... + session cookie khi cần

GIAI ĐOẠN B — SESSION HTTP HẾT / KHÔNG ĐƯỢC GỬI

Browser GET /api/me
  | Cookie: remember-me=...     (không gửi JSESSIONID)
  v
SecurityContextHolderFilter: chưa có Authentication từ session
  v
RememberMeAuthenticationFilter
  -> RememberMeServices.autoLogin(...)
       -> đọc cookie, kiểm tra hash/token và UserDetails
       -> trả RememberMeAuthenticationToken
  -> AuthenticationManager.authenticate(...)
       -> RememberMeAuthenticationProvider kiểm tra key hash
  -> set Authentication đã xác thực vào SecurityContext
  v
AuthorizationFilter: /api/me .authenticated() -> cho phép
  v
Controller thấy rememberMe=true, fullyAuthenticated=false

GIAI ĐOẠN C — HÀNH ĐỘNG NHẠY CẢM

Browser GET /api/high-risk chỉ mang remember-me cookie
  -> /api/high-risk .fullyAuthenticated()
  -> KHÔNG thỏa; entry point mời đăng nhập lại
  -> form login tương tác thành công mới được truy cập
```

**Quan sát quan trọng:** bước A và B dùng **hai loại `Authentication` khác nhau**. Login thường là `UsernamePasswordAuthenticationToken`. Auto-login là `RememberMeAuthenticationToken`; token này đã xác thực về mặt Spring Security nhưng được `AuthenticationTrustResolver` xếp vào mức **remember-me**, không phải fully authenticated.

## 4. Hai cách lưu remember-me token: hash-based và persistent

### 4.1. Token-based: cookie ký, không có bảng token

Mô hình đơn giản dùng `TokenBasedRememberMeServices`. Theo tài liệu Spring Security, nội dung cookie sau Base64 có ý tưởng gần với:

```text
username : expirationTime : algorithmName :
H(username : expirationTime : passwordHash : serverKey)
```

Trong đó:

- `username` để load lại user bằng `UserDetailsService`.
- `expirationTime` là mốc hết hạn, không phải giới hạn phiên `HttpSession`.
- `algorithmName` xác định thuật toán hash được mã hóa trong token ở các phiên bản hỗ trợ.
- `passwordHash` là password đã mã hóa lưu phía server, **không phải raw password của user trong cookie**.
- `serverKey` là khóa bí mật ứng dụng; không được gửi cho client.
- Giá trị hash giúp phát hiện sửa token, nhưng **không mã hóa** toàn bộ cookie thành dữ liệu bí mật. Base64 không phải encryption.

Ưu điểm: cài đặt đơn giản, không cần bảng token, kiểm chứng dựa trên khóa và UserDetails. Nhược điểm lớn: **cookie bị sao chép có thể bị replay trong thời hạn còn hợp lệ**, thường không thể thu hồi riêng một thiết bị với token-based thuần. Đổi password hash hoặc đổi key sẽ làm token cũ mất hiệu lực; cần có chính sách rotate key và tác động lên tất cả browser.

**Lưu ý trong demo:** `UserDetailsService` hash password bằng BCrypt mỗi lần startup. BCrypt có salt ngẫu nhiên, nên dù password text không đổi, hash mới có thể khác. Vì token-based signature phụ thuộc hash lưu trữ, cookie nhớ đăng nhập được tạo trước lúc app restart **có thể mất hiệu lực** trong demo. Production sử dụng hash ổn định được lưu trong database và key ổn định trong secret manager.

### 4.2. Persistent token: series/token trong kho server

`PersistentTokenBasedRememberMeServices` dùng `PersistentTokenRepository`. Cookie thường chứa một **series identifier** và một token ngẫu nhiên. Server tra series trong kho, so token trình tới với token được lưu, rồi **thay token mới** sau khi auto-login thành công. Khi cùng series xuất hiện với token cũ không khớp, có thể coi là dấu hiệu token bị sao chép/đánh cắp, theo chính sách implementation.

Luồng điển hình:

```text
Cookie có series=s1, token=t1
  -> tìm persistent_logins theo series s1
  -> nếu hợp lệ: tạo token mới t2, cập nhật repository, gửi cookie mới
  -> nếu sai token của series tồn tại: xử lý khả năng token bị sao chép
  -> nếu không có series / quá hạn: từ chối auto-login
```

Schema thường dùng với `JdbcTokenRepositoryImpl`:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

Bảng này phải được tạo qua migration của hệ thống, kết nối với `DataSource` đã cấu hình đáng tin. `JdbcTokenRepositoryImpl` không thay thế thiết kế quản lý vòng đời thiết bị: muốn revoke theo user, theo series, hoặc hủy khi account bị khóa phải có chính sách rõ.

| Tiêu chí | Token-based | Persistent-token |
| --- | --- | --- |
| Nơi lưu bằng chứng | Cookie có chữ ký, không cần bảng token | Cookie series/token **và** repository phía server |
| Triển khai | Đơn giản, ít phụ thuộc storage | Cần DB/repository, migration, backup, concurrency handling |
| Kiểm chứng | Signature dựa trên user, expiry, password hash, key | Tra series/token, so khớp, rotate token |
| Thu hồi riêng thiết bị | Khó trong mô hình thuần | Có thể xóa/đình chỉ series nếu thiết kế hỗ trợ |
| Nếu cookie bị copy | Có thể replay tới khi hết hạn/đổi key/password | Rotation giúp phát hiện một số tình huống copy/replay, nhưng không loại bỏ mọi nguy cơ |
| Dùng multi-node | Cần thống nhất signing key và user data | Cần repository dùng chung, nhất quán cho tất cả node |
| Khuyến nghị | Ứng dụng rủi ro thấp, cân nhắc kỹ | Thường phù hợp hơn khi cần theo dõi/thu hồi token |

**Đừng hiểu sai persistent = tuyệt đối an toàn.** Nếu attacker dùng token trước người dùng thật hoặc lấy được cả kho token, vẫn có rủi ro. Cần TLS, cookie bảo mật, rotation, audit, hạn dùng và phòng chống chiếm đoạt thiết bị.

### 4.3. Khi nào không nên dùng remember-me?

Không nên mặc định phát remember-me cho:

- Ứng dụng yêu cầu xác thực lại nghiêm ngặt ở mỗi lần truy cập (tài chính đặc biệt nhạy cảm, quản trị khóa bí mật...).
- Tài khoản có quyền đặc biệt nhưng không có cơ chế giới hạn phạm vi remembered authentication.
- Thiết bị công cộng hoặc shared device.
- Luồng mà pháp lý/chính sách yêu cầu fresh auth/MFA, không thể thỏa bằng cookie dài hạn.
- API chỉ dùng bearer token stateless mà không có nhu cầu browser cookie: không nên bật remember-me chỉ để thay refresh token.

Remember-me không thay thế MFA, step-up authentication, quy trình reset password hoặc quản lý phiên.

## 5. Ứng dụng Spring Boot chạy được: token-based remember-me

Ví dụ giữ nguyên `formLogin` và mặc định CSRF protection. User `alice` với mật khẩu học tập `demo-pass123` có quyền `ROLE_USER`. Có hai endpoint:

- `GET /api/me`: chấp nhận session login hoặc remembered login; trả mức tin cậy thực tế.
- `GET /api/high-risk`: yêu cầu `fullyAuthenticated()`; remembered cookie một mình **không đủ**.

### 5.1. Cấu trúc và Maven

```text
remember-me-demo/
├── pom.xml
├── src/main/java/com/example/rememberme/RememberMeDemoApplication.java
└── src/test/java/com/example/rememberme/RememberMeDemoApplicationTests.java
```

Nội dung `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>remember-me-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

### 5.2. Java application

Tạo `src/main/java/com/example/rememberme/RememberMeDemoApplication.java`:

```java
package com.example.rememberme;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@SpringBootApplication
public class RememberMeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RememberMeDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("demo-pass123"))
                        .roles("USER")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public").permitAll()
                .requestMatchers("/api/high-risk").fullyAuthenticated()
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                // Chỉ để demo: production phải dùng secret mạnh, lưu ngoài source.
                .key("local-demo-key-do-not-use-in-production")
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .rememberMeCookieName("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60)
                .alwaysRemember(false)
            )
            .logout(Customizer.withDefaults());

        // CSRF và session-fixation protection mặc định vẫn được bật.
        return http.build();
    }

    public record UserState(
            String username,
            boolean remembered,
            boolean fullyAuthenticated,
            List<String> authorities
    ) {}

    @RestController
    static class DemoController {
        private final AuthenticationTrustResolver trustResolver =
                new AuthenticationTrustResolverImpl();

        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/api/me")
        UserState me(Authentication authentication) {
            List<String> authorities = authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();

            return new UserState(
                    authentication.getName(),
                    trustResolver.isRememberMe(authentication),
                    trustResolver.isFullyAuthenticated(authentication),
                    authorities
            );
        }

        @GetMapping("/api/high-risk")
        String highRisk() {
            return "fresh-login-required";
        }
    }
}
```

### 5.3. Đọc kỹ cấu hình thay vì chỉ copy

1. `UserDetailsService` phục vụ cả xác thực username/password lúc login và lấy lại user khi verify cookie nhớ đăng nhập. `PasswordEncoder` chứa BCrypt, không so raw password bằng `equals`.
2. `formLogin` kích hoạt login bằng form do Spring Security xử lý. Khi xác thực thành công, authentication filter có thể gọi `RememberMeServices.loginSuccess`.
3. `rememberMe(...).key(...)` thiết lập khóa của remember-me token/provider; khóa trong mã demo **không đủ an toàn production**. Trong triển khai thật, inject secret từ secret manager/cấu hình an toàn và giữ ổn định trên các instance.
4. `rememberMeParameter("remember-me")` đặt tên tham số opt-in. Nếu người dùng **không chọn**, `alwaysRemember(false)` khiến login không tự phát cookie nhớ đăng nhập.
5. `tokenValiditySeconds(7 * 24 * 60 * 60)` đặt thời hạn token 7 ngày cho demo, **không** đổi session timeout. Không nhầm nó với `server.servlet.session.timeout`.
6. `rememberMeCookieName("remember-me")` giúp test dễ xác định cookie. Cookie này **không chứa raw password**; tuy vậy ai lấy được cookie hợp lệ có thể lợi dụng nó.
7. `/api/me` yêu cầu `authenticated()` nên cho cả interactive login và remember-me login. Controller dùng `AuthenticationTrustResolver` để phản ánh mức tin cậy, thay vì suy từ `Authentication.isAuthenticated()`.
8. `/api/high-risk` dùng `fullyAuthenticated()`. Khi chỉ có remember-me, framework sẽ yêu cầu quy trình đăng nhập đủ mạnh; với form login thường là redirect tới trang đăng nhập, không nên kỳ vọng luôn trả HTTP 403.
9. `logout` được `LogoutFilter` xử lý. Không viết custom logout chỉ xóa cookie `JSESSIONID` vì cookie remember-me cũng phải được dọn.
10. `rememberMe` bằng Java DSL tự kết nối `RememberMeAuthenticationFilter` và `RememberMeAuthenticationProvider`. **Không** tạo thêm một filter/provider song song cho cùng cookie, vì có thể dẫn đến xử lý lặp hoặc khác khóa.

**Quan trọng với HTTPS:** cookie chứa bearer-like credential dài hạn nên production phải dùng TLS, `Secure`, `HttpOnly`, chính sách `SameSite` thích hợp, CSRF protection và hạn sử dụng hợp lý. Ở localhost HTTP, không cố bật `Secure` nếu muốn thử bằng curl không có TLS; môi trường thực nên ép HTTPS và secure cookie.

## 6. Thực hành trên trình duyệt: nhớ login khi mất session

Chạy ứng dụng:

```bash
mvn spring-boot:run
```

Thử bằng một browser profile mới ở `http://localhost:8080/login`:

1. Đăng nhập `alice` / `demo-pass123` và **chọn remember-me**. Trang login mặc định của Spring Security có thể cung cấp lựa chọn remember-me khi tính năng được bật; nếu tự làm login page, form phải gửi tham số `remember-me=on` và CSRF hợp lệ. Sau login, kiểm tra cookie `remember-me` trong developer tools.
2. Gọi `http://localhost:8080/api/me` khi session còn. Response thường cho `remembered=false`, `fullyAuthenticated=true`.
3. Để kiểm chứng auto-login, **xóa riêng cookie session `JSESSIONID`**, giữ cookie `remember-me`. Không nhấn logout ở bước này; logout có nghĩa là người dùng chủ động muốn chấm dứt nhớ đăng nhập.
4. Tải lại `/api/me`. Nếu cookie remember-me vẫn hợp lệ, Spring Security khôi phục identity và response cho `remembered=true`, `fullyAuthenticated=false`.
5. Thử `/api/high-risk` với remember-me authentication: URL yêu cầu fresh login, thường chuyển hướng tới `/login`. Sau khi điền password và xác thực tương tác, endpoint mới truy cập được.
6. Logout chính thức. Browser được hướng tới `/login?logout`. Cookie remember-me trên browser bị xóa theo luồng remember-me logout handler. **Lưu ý an ninh:** với token-based, một **bản sao cookie cũ bị đánh cắp** có thể vẫn hợp lệ đến khi hết hạn/đổi key hoặc password; xóa cookie trên browser không đồng nghĩa server đã blacklist token đó.

Response `/api/me` khi login tương tác, ví dụ:

```json
{
  "username": "alice",
  "remembered": false,
  "fullyAuthenticated": true,
  "authorities": ["ROLE_USER"]
}
```

Response sau khi chỉ còn remember-me cookie:

```json
{
  "username": "alice",
  "remembered": true,
  "fullyAuthenticated": false,
  "authorities": ["ROLE_USER"]
}
```

JSON chỉ minh họa **giá trị**; thứ tự key không phải hợp đồng bảo mật. Cả hai trường hợp đều có authority `ROLE_USER` do server lấy từ `UserDetailsService`, nhưng mức độ chứng minh danh tính khác nhau. Một endpoint yêu cầu `hasRole("USER")` nhưng không thêm điều kiện về mức tin cậy có thể chấp nhận remember-me user; với thao tác nhạy cảm cần policy mạnh hơn.

### Nếu muốn thử bằng HTTP client thay vì UI

Dùng client duy trì cookie jar và gửi POST form với token CSRF tương ứng. Khi đăng nhập, tham số form mặc định là `username`, `password` và `remember-me=on`. Một POST thiếu CSRF hợp lệ có thể bị `CsrfFilter` chặn 403 **trước khi** `RememberMeServices.loginSuccess` chạy; không được tắt CSRF chỉ để cho test dễ hơn. Mục kiểm thử MockMvc bên dưới gửi CSRF đúng cách.

## 7. Kiểm thử Spring Security thực với MockMvc

Tạo `src/test/java/com/example/rememberme/RememberMeDemoApplicationTests.java`:

```java
package com.example.rememberme;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void optInIssuesCookieAndCookieRestoresRememberedIdentity() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass123")
                    .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        Cookie rememberCookie = login.getResponse().getCookie("remember-me");
        assertNotNull(rememberCookie);
        assertTrue(rememberCookie.getMaxAge() > 0);

        // Session của interactive login: chưa phải remember-me authentication.
        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.remembered").value(false))
                .andExpect(jsonPath("$.fullyAuthenticated").value(true));

        // Request độc lập không gửi session: CHỈ có remember-me cookie.
        mvc.perform(get("/api/me").cookie(rememberCookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.remembered").value(true))
                .andExpect(jsonPath("$.fullyAuthenticated").value(false))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"));

        // Cookie nhớ đăng nhập không đủ cho endpoint yêu cầu fresh login.
        mvc.perform(get("/api/high-risk").cookie(rememberCookie))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void withoutExplicitOptInNoRememberCookieIsIssued() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass123"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        assertNull(login.getResponse().getCookie("remember-me"));
    }

    @Test
    void forgedRememberCookieCannotAuthenticate() throws Exception {
        Cookie forged = new Cookie("remember-me", "forged.invalid.token");

        // Cookie không có chữ ký hợp lệ: login page được yêu cầu.
        mvc.perform(get("/api/me").cookie(forged))
                .andExpect(status().is3xxRedirection());
    }
}
```

Chạy trong thư mục `remember-me-demo`:

```bash
mvn test
```

Bài test đầu đi qua filter chain thực do Spring Security cấu hình: form login tạo cookie chỉ khi opt-in; request mới **không gửi `JSESSIONID`** mà chỉ có cookie `remember-me` được RememberMeAuthenticationFilter xử lý; endpoint hiển thị `remembered=true`; endpoint yêu cầu `fullyAuthenticated()` không chấp nhận mức tin cậy này. Test thứ hai kiểm tra opt-in; test thứ ba kiểm tra cookie giả không đủ để login.

Lưu ý: `MockMvc` không phải trình duyệt thật và không tự kiểm tra mọi thuộc tính Secure/SameSite trong môi trường production. Kiểm tra HTTPS, cookie flags, restart, cookie expiry và persistent repository bằng integration/E2E tests nếu đây là yêu cầu vận hành.

## 8. Khi muốn dùng PersistentTokenRepository thay token-based

Đây là **đoạn tích hợp bổ sung**, không phải tệp Java độc lập. Khi dùng database, cần `spring-boot-starter-jdbc` và JDBC driver phù hợp, `DataSource` được cấu hình, bảng `persistent_logins` đã migration, rồi thêm bean:

```java
@Bean
PersistentTokenRepository persistentTokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
```

Các import cần thiết cho đoạn trên:

```java
import javax.sql.DataSource;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
```

Trong cấu hình `SecurityFilterChain`, thay phần remember-me token-based bằng:

```java
.rememberMe(remember -> remember
    .key(rememberMeKeyFromSecretManager)
    .userDetailsService(users)
    .tokenRepository(persistentTokenRepository)
    .rememberMeParameter("remember-me")
    .tokenValiditySeconds(7 * 24 * 60 * 60)
)
```

Các biến `users`, `persistentTokenRepository` và `rememberMeKeyFromSecretManager` trong đoạn trích là dependencies được tiêm/cấu hình tại ứng dụng thực. Đoạn này **không biên dịch độc lập** khi copy nguyên văn ra file không có ngữ cảnh. Khi khai báo `tokenRepository(...)`, DSL chọn `PersistentTokenBasedRememberMeServices` phù hợp; không tạo thêm một `TokenBasedRememberMeServices` khác cùng lúc.

`InMemoryTokenRepositoryImpl` chỉ phù hợp thử nghiệm; nó không tồn tại sau restart và không chia sẻ token giữa các node. Với JDBC, không gọi `setCreateTableOnStartup(true)` ở production vì migration/schema thuộc quy trình riêng và có thể gây lỗi khi bảng đã tồn tại.

Một hệ thống thực cần định nghĩa thêm:
- Xóa persistent token khi đổi mật khẩu, khóa user, thu hồi tài khoản hoặc phát hiện lạm dụng.
- Chiến lược revocation theo user/thiết bị; việc `removeUserTokens(username)` tác động đến các series của user.
- Xử lý race khi nhiều request dùng cùng token series gần đồng thời và khi token bị copy.
- Giới hạn lifetime, chính sách thay key, cơ chế bảo vệ database chứa token.
- Lưu audit/metadata thiết bị tách khỏi raw token, không đưa token/series nhạy cảm ra public API.

## 9. Các lỗi cấu hình và cách phân biệt nguyên nhân

### 9.1. Đăng nhập thành công nhưng không có cookie remember-me

Kiểm tra theo thứ tự:

1. User có thực sự gửi tham số `remember-me` trong **POST login** không? Nếu frontend tự viết, checkbox không được truyền sẽ không có opt-in.
2. `alwaysRemember(false)` là lựa chọn mặc định hợp lý. Nếu bật `alwaysRemember(true)`, cookie có thể được tạo ngay cả khi user không chọn — thường không nên làm vậy nếu chưa có đồng ý rõ.
3. `formLogin` có dùng cùng `RememberMeServices` đã cấu hình không? Nếu viết custom JSON login, phải gọi `RememberMeServices.loginSuccess(...)` đúng lúc (sau khi manager xác thực thành công) hoặc cấu hình filter xử lý tương ứng.
4. Request login có bị CSRF filter từ chối trước khi vào authentication filter không?
5. Header `Set-Cookie` có bị reverse proxy/chính sách cookie/trình duyệt loại bỏ không? Cookie `Secure` sẽ không được gửi qua kết nối HTTP thường.
6. Có cấu hình nhiều filter chains nhưng remember-me chỉ nằm trong chain khác không?

### 9.2. Có cookie nhưng vẫn bị yêu cầu login

Kiểm tra cookie có được gửi đúng Domain/Path/SameSite/Secure trên request hay không; sau đó xem:
- Cookie đã hết hạn hay có cấu trúc bị sửa?
- `UserDetailsService` có còn tải được user đó không? User disabled/removed?
- Password hash hoặc `key` đã đổi? Với demo in-memory BCrypt, restart làm hash thay đổi.
- `RememberMeServices` và `RememberMeAuthenticationProvider` có cùng khóa không? Nếu tự wiring, provider đã được manager đăng ký chưa?
- Có cấu hình chain/endpoint loại trừ RememberMeAuthenticationFilter không?
- Một session/`SecurityContext` khác đã được tải, khiến remember-me filter không thử auto-login?
- Endpoint có yêu cầu `fullyAuthenticated()` không? Khi ấy remember-me **được nhận diện** nhưng mức tin cậy không đủ.

### 9.3. Có remember-me mà vẫn phải nhập password khi đổi mật khẩu

Đó thường là **hành vi đúng**. `authenticated()` chấp nhận remembered authentication; `fullyAuthenticated()` yêu cầu identity không phải anonymous và không phải remembered. Với các thao tác rất nhạy cảm, còn có thể yêu cầu step-up MFA hoặc kiểm tra thời gian từ lần xác thực tương tác, không chỉ `fullyAuthenticated()`.

### 9.4. Logout rồi cookie cũ vẫn đăng nhập được?

Cần phân biệt:
- **Cookie còn lưu trên browser**: logout handler phải xóa cookie và session đúng cách.
- **Một bản sao token-based cookie bị đánh cắp trước logout**: vì không có token store để revoke riêng, nó vẫn có thể kiểm chứng thành công cho đến khi hết hạn hoặc thay đổi password hash/key. Đây là giới hạn thiết kế, không phải lỗi của `LogoutFilter`.
- **Persistent token**: repository cho phép xóa token/series server-side; tuy nhiên chính sách logout, all-devices logout và token rotation vẫn cần thiết kế và kiểm thử cụ thể.

Không nói với người dùng rằng "xóa cookie là revoke toàn bộ phiên/thiết bị" nếu server không thực sự làm điều đó.

### 9.5. `RememberMeAuthenticationProvider` có so password không?

**Không.** Nó kiểm tra key hash của `RememberMeAuthenticationToken`. `TokenBasedRememberMeServices` kiểm chứng cookie dựa trên dữ liệu user và khóa; `DaoAuthenticationProvider` mới so username/password ở lần login tương tác. Phân biệt giúp tránh tự triển khai provider sai hoặc giả định remember-me mạnh ngang password login.

## 10. Các nguyên tắc bảo mật cần áp dụng

- **Không log cookie nhớ đăng nhập, raw token, series/token hoặc secret key** trong access log, tracing, exception, metrics label hay response.
- **Chỉ phát cookie theo opt-in** khi chính sách và UX yêu cầu. Không mặc định `alwaysRemember(true)` cho mọi người dùng.
- **Sử dụng HTTPS/TLS**, cookie `Secure`/`HttpOnly` và `SameSite` thích hợp; kiểm tra reverse proxy và domain/path. Cookie dài hạn bị copy có thể bị replay.
- **Không tắt CSRF vô điều kiện**: browser vẫn có thể gửi cookie/session tự động trên request đổi trạng thái.
- **Tách mức độ tin cậy:** `authenticated()` cho endpoint thông thường, `fullyAuthenticated()` hoặc step-up MFA/reauth cho thao tác có rủi ro cao.
- **Giới hạn thời hạn token**, lên kế hoạch thay signing key, revoke và phát hiện nghi ngờ token bị copy.
- **Không cấp authority từ cookie tự chế hay dữ liệu client**; role lấy từ nguồn server đáng tin và được dùng trong `AuthorizationFilter`.
- **Đồng nhất key giữa các node** nếu token-based; nếu persistent, dùng repository dùng chung và chính sách concurrency hợp lý.
- **Kiểm soát user lifecycle**: thay password, khóa tài khoản, rời tổ chức, thay role phải có hành vi rõ với remember-me.
- **Kiểm thử tách session và cookie:** một request có session hoạt động không đủ chứng minh RememberMeAuthenticationFilter thực sự chạy; phải tạo request mới chỉ có cookie nhớ đăng nhập.

## 11. Checklist và bài tập tự kiểm tra

### Checklist trước khi release

- [ ] Có `UserDetailsService` và authentication provider dùng đúng password hash/nguồn user.
- [ ] `RememberMeServices` và `RememberMeAuthenticationProvider` dùng cùng key; không có filter/provider trùng lặp.
- [ ] Chỉ phát token nhớ đăng nhập sau login tương tác hợp lệ và opt-in.
- [ ] Cookie được browser gửi lại ở request cần thiết; HTTPS và thuộc tính cookie được kiểm tra.
- [ ] Request mới **không có `JSESSIONID`** nhưng có remember-me cookie hợp lệ phục hồi đúng user.
- [ ] Cookie hết hạn/bị sửa/user bị xóa/password đổi không tạo authentication hợp lệ.
- [ ] Endpoint nhạy cảm dùng `fullyAuthenticated()` hoặc yêu cầu xác thực lại.
- [ ] Logout dọn cookie browser, và tài liệu giải thích đúng giới hạn replay/revocation.
- [ ] Persistent repository có migration, index, backup, rotation và chính sách thu hồi.
- [ ] Không tiết lộ remember-me cookie, key, hash hoặc token qua log.

### Câu hỏi

1. `RememberMeServices.loginSuccess` và `autoLogin` được gọi ở **hai thời điểm** nào?
2. Khi `SecurityContext` đã có authentication từ session, `RememberMeAuthenticationFilter` có cần auto-login không?
3. Thành phần nào kiểm tra chữ ký cookie token-based, và thành phần nào kiểm tra key hash trong `RememberMeAuthenticationToken`?
4. `RememberMeAuthenticationProvider` có so raw password với password hash như `DaoAuthenticationProvider` không?
5. Vì sao `RememberMeAuthenticationToken.isAuthenticated()` có thể là true nhưng `fullyAuthenticated()` vẫn false?
6. Với `maximumSessions` hoặc logout, remember-me có tự biến mất ở mọi thiết bị không?
7. Khác nhau lớn nhất về revoke riêng thiết bị giữa token-based và persistent-token là gì?
8. Vì sao test phải bỏ `JSESSIONID` nhưng giữ `remember-me` nếu muốn chứng minh auto-login?
9. Nếu dùng BCrypt hash mới mỗi lần startup, remember-me token-based có thể chịu ảnh hưởng ra sao?
10. Nếu người dùng không tick remember-me, tại sao một login thành công thường vẫn có session nhưng không có cookie nhớ đăng nhập?

**Đáp án ngắn:** (1) sau login tương tác và ở request sau thiếu authentication; (2) thường không; (3) service và provider tương ứng; (4) không; (5) remembered là mức tin cậy thấp hơn fresh login; (6) không nhất thiết, cần chính sách session/token rõ; (7) server store cho phép revoke/rotate; (8) tránh test tình cờ dùng session; (9) hash đổi làm chữ ký cookie cũ vô hiệu; (10) session login và remember-me opt-in là hai cơ chế riêng.

## 12. Tham khảo chính thức

- Spring Security — Remember-Me Authentication (Servlet 6.5): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
- Spring Security — `RememberMeServices` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/RememberMeServices.html
- Spring Security — `RememberMeAuthenticationFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/RememberMeAuthenticationFilter.html
- Spring Security — `RememberMeAuthenticationProvider` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/RememberMeAuthenticationProvider.html
- Spring Security — `RememberMeAuthenticationToken` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/RememberMeAuthenticationToken.html
- Spring Security — `AuthenticationTrustResolver` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html
- Spring Security — Authorize HTTP Requests (authenticated vs fullyAuthenticated): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — CSRF (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
