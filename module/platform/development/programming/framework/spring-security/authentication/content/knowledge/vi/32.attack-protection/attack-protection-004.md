# Phản hồi, thời gian xử lý và nguy cơ dò sự tồn tại của tài khoản

## 1. Mục tiêu và phạm vi

Một ứng dụng xác thực có thể bảo vệ mật khẩu bằng BCrypt, bật HTTPS, khóa tài khoản và MFA nhưng vẫn vô tình tiết lộ **tài khoản nào tồn tại**. Kẻ tấn công không nhất thiết phải đăng nhập thành công: chỉ cần phân biệt hai kết quả khi gửi một địa chỉ email hay username, họ đã có thể xây danh sách người dùng để phục vụ password spraying, phishing, social engineering hoặc các cuộc tấn công tiếp theo.

Lỗi này gọi là **account enumeration / username enumeration** (dò sự tồn tại của tài khoản). Kênh tiết lộ không chỉ là thông báo “Email chưa đăng ký”; nó có thể là **HTTP status, redirect, nội dung/độ dài response, response headers, cookie, hành vi UI, số bước xử lý, thời gian phản hồi, giới hạn tốc độ, email side effect** hay sự khác biệt ở các dịch vụ khác.

Mục tiêu sau bài học:

1. Giải thích account enumeration và phân biệt nó với kiểm thử mật khẩu hoặc brute force.
2. Nhận diện các **discrepancy factors** (tín hiệu khác biệt) trên tất cả luồng đăng nhập, đăng ký và phục hồi.
3. Hiểu tại sao cùng một câu thông báo **chưa đủ** nếu đường xử lý nhanh/chậm khác nhau.
4. Hiểu `DaoAuthenticationProvider`, `UserDetailsService`, `PasswordEncoder`, `hideUserNotFoundExceptions` và cơ chế giảm timing leak sẵn có của Spring Security.
5. Thiết kế phản hồi công khai chung, xử lý email/reset bất đồng bộ, kiểm soát rate limiting và log nội bộ mà không làm lộ thông tin.
6. Viết ví dụ Spring Boot 3.x, Spring Security 6.x, Java 17+ và unit/integration test cho khả năng chống dò tài khoản.
7. Đánh giá các giới hạn: khó đạt thời gian **giống hệt tuyệt đối** qua mạng, trade-off UX và nguy cơ denial-of-service khi dùng các biện pháp chống đoán sai cách.

**Phạm vi:** ứng dụng **Spring Security Servlet/Spring MVC**, đặc biệt luồng username/password và forgot-password; mở rộng sang OTT, OTP, SSO, REST, GraphQL, API và đăng ký tài khoản. Spring Security 7.x còn tiếp tục những khái niệm cốt lõi này; ví dụ cấu hình chính dùng Spring Security 6.5 / Spring Boot 3.x.

## 2. Account enumeration hoạt động như thế nào?

Hãy tưởng tượng hai request tới cùng endpoint:

```http
POST /login
Content-Type: application/x-www-form-urlencoded

username=alice&password=invalid-password
```

```http
POST /login
Content-Type: application/x-www-form-urlencoded

username=does-not-exist&password=invalid-password
```

Nếu một request trả **“Mật khẩu không đúng”**, request còn lại trả **“Không tìm thấy tài khoản”**, người ngoài đã có một phép thử để phân loại username, dù không biết mật khẩu.

Ngay cả khi cả hai cùng trả:

```json
{"error":"INVALID_CREDENTIALS"}
```

vẫn có thể rò rỉ:

```text
Username tồn tại     -> DB lookup + BCrypt.matches(...) -> phản hồi chậm
Username không tồn tại -> DB lookup + return ngay       -> phản hồi nhanh
```

Người quan sát có thể lặp lại các phép thử, xử lý nhiễu và suy ra hai nhóm độ trễ. Đây là **timing side channel** (kênh phụ qua thời gian).

**Phân biệt các mục tiêu:**

| Vấn đề | Kẻ tấn công muốn biết/làm gì? | Dữ liệu cần dùng |
| --- | --- | --- |
| Account enumeration | Xác định user/email có trong hệ thống hay không | Một username và sự khác biệt trong response |
| Password guessing | Tìm password đúng của một account | Tập password |
| Password spraying | Thử vài password phổ biến trên nhiều account | Nhiều username; enumeration giúp tăng hiệu quả |
| Credential stuffing | Thử username/password đã lộ từ hệ thống khác | Danh sách credentials |
| Account takeover | Chiếm quyền điều khiển tài khoản | Có thể kết hợp enumeration, reset, phishing, lộ session |

Giảm enumeration làm nhỏ bề mặt tấn công nhưng **không thay thế** MFA, mật khẩu an toàn, rate limit, cảnh báo đăng nhập bất thường và kiểm soát chiếm tài khoản.

## 3. Những nơi dễ tiết lộ tài khoản tồn tại

Một sản phẩm có nhiều đường kiểm tra danh tính, không chỉ `/login`.

| Luồng / endpoint | Tín hiệu nguy hiểm | Cách phản hồi nên cân nhắc |
| --- | --- | --- |
| Form login | “Không tồn tại user” khác “Sai mật khẩu” | Thông báo thất bại chung |
| REST `/api/auth/login` | 404 khi user không có, 401 khi password sai | Cùng status/body khi credentials không hợp lệ |
| Forgot password | “Email chưa được đăng ký” | “Nếu tài khoản phù hợp tồn tại, hướng dẫn sẽ được gửi” |
| Yêu cầu magic link/OTT | “Đã gửi link cho alice”, hoặc status khác | Phản hồi tiếp nhận yêu cầu chung; chỉ giao token tới kênh đã xác minh |
| Gửi mã OTP/SMS | “Số điện thoại chưa liên kết account” | Không xác nhận công khai liên kết account/phone |
| Đăng ký account | “Email đã dùng” so với “Đã tạo account” | Cân nhắc xác minh email trước khi tiết lộ thông tin hoặc dùng luồng xác nhận chung |
| Đăng ký tổ chức/SSO | Redirect khác khi tenant/email tồn tại | Ràng buộc routing chính đáng, tránh tiết lộ membership |
| Đăng nhập WebAuthn/passkey | Hiển thị “Không có passkey của user này” | Dùng luồng không tiết lộ membership khi khả thi và kiểm soát fallback |
| Lấy lại mã khôi phục MFA | Cho biết account có bật MFA/TOTP không | Không tiết lộ trạng thái factor trước khi xác minh quyền truy cập |
| API kiểm tra username | Boolean `available` công khai | Xem đây là nguồn enumeration, thêm rate limit và chính sách tiết lộ |
| GraphQL | `USER_NOT_FOUND` khác `INVALID_PASSWORD` trong `errors.extensions` | Chuẩn hóa mã lỗi công khai cho operation xác thực |
| Support chat/help desk | Người hỗ trợ xác nhận “Email này có trong hệ thống” | Quy trình xác minh người hỏi, hạn chế chia sẻ membership |

**Một điểm kiểm soát được `/login` chưa có nghĩa những endpoint còn lại đã được bảo vệ.** Đặc biệt, chức năng reset mật khẩu và magic-link thường là đường dò tài khoản vì thiết kế UI dễ nói quá nhiều.

## 4. Discrepancy factors: không chỉ là dòng chữ thông báo

Những người xây ứng dụng thường chỉ sửa message, nhưng người dùng bên ngoài nhìn thấy **toàn bộ HTTP exchange**.

| Lớp quan sát | Ví dụ khác biệt khi user có/không tồn tại |
| --- | --- |
| Status code | `200` so với `404`, `401` so với `403` |
| JSON fields | `{ "reason": "USER_NOT_FOUND" }` so với `{ "reason": "WRONG_PASSWORD" }` |
| HTML | Error block khác nhau; nội dung “Gợi ý khôi phục” chỉ hiện cho user hợp lệ |
| Độ dài body | 180 byte so với 326 byte, kể cả text chính có vẻ giống |
| HTTP headers | `Location`, `WWW-Authenticate`, `Cache-Control`, `Content-Type` khác |
| Cookie | `Set-Cookie`/session thay đổi chỉ khi username tồn tại |
| Redirect chain | Redirect tới `/verify-otp` chỉ cho account hợp lệ trước khi xác minh password |
| Thời gian | Bỏ qua password hash khi không tìm thấy account |
| Mạng phụ trợ | Có account thì gọi mail/CRM/LDAP; không có thì return ngay |
| Rate limit | Account hợp lệ mới bị trả `429` sau một số lần thử |
| Side effects | Gửi email/SMS, push notification, đổi trạng thái hoặc lưu audit khác |
| Localized UI | Tiếng Việt và tiếng Anh hiển thị lỗi khác theo từng branch |
| API error details | Stack trace, exception type, `error_description` hé lộ trạng thái account |

**Phản hồi nhất quán** cần được đánh giá ở mức **điều người ngoài thực sự thấy**: status, headers, body, cache behavior, redirect, thời gian tương đối và hành vi tương tác. Không có quy tắc bắt buộc mọi lỗi hệ thống đều trả `401`: phải phân biệt **credentials sai** với **sự cố hạ tầng** theo một chính sách có cân nhắc.

Ví dụ phản hồi lỗi đăng nhập nhất quán cho tài khoản không tồn tại, password sai, account bị khóa hoặc vô hiệu hóa:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store

{"error":"INVALID_CREDENTIALS"}
```

Đây là **hình thức minh họa** của một API; một giao diện form có thể thống nhất chuyển hướng về `/login?error` thay vì dùng JSON. Quy tắc không phải “mọi response đều 401”, mà là **hai nguyên nhân không nên phân biệt công khai** phải được xử lý nhất quán.

## 5. Thông điệp công khai và thông tin log nội bộ

### Đăng nhập

**Không nên**:

```json
{"error":"USER_NOT_FOUND","message":"Tài khoản không tồn tại"}
```

```json
{"error":"WRONG_PASSWORD","message":"Mật khẩu không đúng"}
```

**Nên** dùng một kiểu lỗi chung:

```json
{"error":"INVALID_CREDENTIALS","message":"Thông tin đăng nhập không hợp lệ"}
```

Trường hợp locked/disabled cũng cần được cân nhắc để tránh tiết lộ trạng thái trước khi người dùng chứng minh quyền sở hữu. Tuy nhiên vẫn cần **thông báo đủ hữu ích qua kênh tin cậy** khi người dùng thật cần khôi phục account. Ví dụ sau khi xác thực kênh email đã đăng ký, người dùng có thể được hướng dẫn chi tiết mà không tiết lộ với người lạ tại login form.

### Quên mật khẩu

**Không nên**:

```text
Không tìm thấy địa chỉ email này.
```

**Nên**:

```text
Nếu tài khoản phù hợp tồn tại, hướng dẫn khôi phục sẽ được gửi tới kênh đã đăng ký.
```

Không được trả về reset token hoặc link cho bên yêu cầu. Kênh gửi là **email/phone đã xác minh thuộc account**, không phải một địa chỉ mới do người gửi tự nhập để nhận quyền truy cập account người khác.

### Đăng ký

Trường hợp user muốn tạo account bằng một email đã dùng là bài toán UX thực tế: đôi khi cần cho biết username đã bị chiếm. Phải cân nhắc mô hình kinh doanh và mức nhạy cảm của membership. Một lựa chọn là phản hồi “Hãy kiểm tra hộp thư nếu địa chỉ đủ điều kiện” rồi xử lý **đăng ký mới / khôi phục có kiểm soát** thông qua kênh email, không công khai khẳng định địa chỉ đã có account. Với username hiển thị công khai, có thể chấp nhận tiết lộ tính khả dụng có giới hạn và rate limit; không được suy rộng chính sách đó sang email cá nhân/nhóm nhân sự nhạy cảm.

### Ghi log

Nội bộ có thể cần biết lý do thất bại để vận hành: `USER_NOT_FOUND`, `BAD_PASSWORD`, `LOCKED`, `DISABLED`, `RATE_LIMITED`, `BACKEND_ERROR`. Tuy nhiên:
- Không log password, OTP, reset token, raw session ID hay Bearer token.
- Tránh ghi email/username thô vào log rộng quyền; dùng ID nội bộ hoặc giá trị pseudonymized có kiểm soát khi phù hợp.
- Chặn log injection/CRLF từ input, dùng structured logging.
- Quyền đọc log phải hẹp; retention và audit theo chính sách.
- **Không phản chiếu** internal reason sang response/header/GraphQL error extension.

## 6. Timing side channel: vì sao cùng message vẫn bị dò?

Mô tả đường xử lý sai:

```text
POST /login
  |
  +--> tìm username trong DB
          |
          +-- không tồn tại --> trả lỗi ngay (rất nhanh)
          |
          `-- tồn tại --> tính BCrypt.matches(...) (tốn thời gian)
                             |
                             `--> trả cùng lỗi công khai
```

Mật khẩu được lưu bằng thuật toán băm có chủ đích **tốn CPU/bộ nhớ** (BCrypt/Argon2/PBKDF2 theo policy). Khi username tồn tại, `PasswordEncoder.matches` có thể mất đáng kể thời gian. Khi username không có và code return ngay, chênh lệch có thể đủ lớn để quan sát thống kê, dù HTTP body giống hệt.

Cũng có thể có **tín hiệu ngược**:
- Chỉ account hợp lệ mới đi qua service kiểm tra trạng thái, gọi MFA provider hoặc LDAP.
- Account mới có session/cookie/captcha, account không có trả ngay.
- Có account mới gửi email đồng bộ qua SMTP.
- Có account bị khóa chỉ gọi DB update/transaction khác.
- Một số backend có cache nóng cho account phổ biến và đường lookup khác cho username sai.
- Lỗi timeout/LDAP bind chỉ diễn ra khi user tồn tại.

**Không có bảo đảm mọi request có đúng cùng latency qua Internet.** Mạng, load balancer, GC, cache, traffic và scheduler tạo nhiễu. Mục tiêu thực tế là **không để tồn tại chênh lệch có hệ thống, dễ khai thác** giữa các nhánh công khai, không phải cam kết `time_total` từng request bằng nhau đến từng nanosecond.

## 7. Spring Security `DaoAuthenticationProvider` làm gì?

Trong luồng username/password điển hình:

```text
UsernamePasswordAuthenticationFilter
             |
             v
ProviderManager (AuthenticationManager)
             |
             v
DaoAuthenticationProvider
       |
       +--> UserDetailsService.loadUserByUsername(username)
       |
       +--> PasswordEncoder.matches(rawPassword, encodedPassword)
       |
       +--> Kiểm tra trạng thái UserDetails, tạo Authentication hoặc lỗi
             |
             v
AuthenticationFailureHandler / HTTP response
```

`DaoAuthenticationProvider` sử dụng `UserDetailsService` để tìm account và `PasswordEncoder` để so mật khẩu. `UserDetailsService` **phải ném `UsernameNotFoundException`** khi account không tồn tại; trả `null` vi phạm hợp đồng và gây lỗi nội bộ.

### 7.1. `hideUserNotFoundExceptions` mặc định là `true`

`AbstractUserDetailsAuthenticationProvider` (lớp cha của `DaoAuthenticationProvider`) có `setHideUserNotFoundExceptions(boolean)`.

Mặc định, nếu username không tồn tại **hoặc** mật khẩu sai, bên gọi thấy `BadCredentialsException` chung; đặt `false` làm username không tồn tại bị ném `UsernameNotFoundException` rõ hơn. Việc đặt `false` được Javadoc coi là **kém an toàn hơn**.

Không nên cấu hình:

```java
// Không khuyến nghị trên dịch vụ đăng nhập công khai:
provider.setHideUserNotFoundExceptions(false);
```

Ngay cả khi che tên exception, ứng dụng có `AuthenticationFailureHandler` tùy chỉnh vẫn có thể làm lộ sự khác biệt nếu đọc exception nội bộ, gọi service riêng hoặc trả redirect/status khác. Kiểm tra toàn bộ pipeline, không chỉ `UserDetailsService`.

### 7.2. Giảm chênh lệch timing khi username không tồn tại

Trong các phiên bản Spring Security hiện đại, mã nguồn `DaoAuthenticationProvider` dùng giá trị password mã hóa dành cho **user không tồn tại** và vẫn gọi `PasswordEncoder.matches(...)` cho nhánh đó, thay vì bỏ qua toàn bộ công việc so mật khẩu. Đây là biện pháp giảm timing discrepancy (được nhắc đến với issue `SEC-2056`).

Kết luận:
- **Không cần** tự chèn `Thread.sleep(...)` chỉ vì muốn “cân bằng” nhánh user-not-found khi đang dùng `DaoAuthenticationProvider` chuẩn.
- Cơ chế này **không** làm response time hoàn toàn constant-time, không tự bảo vệ network/LDAP/DB/service custom.
- Nếu override provider, thêm caching, custom encoder hoặc dùng một authentication manager khác, phải kiểm tra lại đường xử lý thực tế.
- Hash không tồn tại được chuẩn bị và dùng theo implementation; không suy ra app đang dùng loại hash cố định nếu `PasswordEncoder` tùy chỉnh.
- Tài khoản `disabled`/`locked`, mật khẩu đang dùng encoder khác cost, hoặc các hook kiểm tra bổ sung vẫn có thể khác thời gian; phải test theo **đúng phiên bản ứng dụng**.

Trong Spring Security 7.1 có API `setAlwaysPerformAdditionalChecksOnUser(...)` được Javadoc mô tả để kiểm soát một số trường hợp pre-auth checks; không mặc nhiên dùng tên method đó trên bản 6.x.

### 7.3. Đừng vô hiệu hóa password hashing để cho nhanh như nhau

Biện pháp sai:

```java
// SAI: so sánh password plaintext hoặc hash nhanh không giải quyết an toàn.
// if (presentedPassword.equals(account.getPassword())) ...
```

Password storage phải tiếp tục dùng `PasswordEncoder` phù hợp (BCrypt/Argon2/PBKDF2), có chi phí bảo vệ chống tấn công offline. Điều chỉnh timing chỉ là **một lớp** của thiết kế, không được làm yếu password verification.

## 8. Ví dụ ứng dụng Spring Boot 3.x + Spring Security 6.x

Ví dụ Servlet dưới đây cho thấy:
- Username/password theo `DaoAuthenticationProvider` mặc định.
- `PasswordEncoder` mạnh thay vì `{noop}`.
- Tất cả lỗi authentication của form login được chuyển thành **một status + một JSON body**.
- **Không** cho client biết exception class hoặc account status.

Đây là demo một đường đăng nhập; các policy rate limiting, session, mail recovery, MFA và giám sát cần bổ sung riêng.

### 8.1. Dependencies

Dùng trong `build.gradle` của project Spring Boot 3.x đã có plugin Spring Boot/Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không tự pha trộn các bản Spring Security major khác nhau ngoài BOM/Dependency Management của Spring Boot.

### 8.2. Cấu hình security và failure handler

File `src/main/java/example/enumeration/EnumerationSafeSecurityConfig.java`:

```java
package example.enumeration;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class EnumerationSafeSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Tài khoản/mật khẩu cố định CHỈ dành cho demo local.
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-password-not-for-production"))
            .authorities("ROLE_USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/account/recover").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .failureHandler((request, response, exception) -> {
                    // Không phản chiếu exception.getMessage().
                    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                    response.setContentType(
                        MediaType.APPLICATION_JSON_VALUE
                    );
                    response.setCharacterEncoding(
                        StandardCharsets.UTF_8.name()
                    );
                    response.setHeader("Cache-Control", "no-store");
                    response.getWriter().write(
                        "{\"error\":\"INVALID_CREDENTIALS\"}"
                    );
                })
            );

        return http.build();
    }
}
```

**Tại sao dùng `failureHandler`?** Trong form login, lỗi authentication phát sinh tại Spring Security filter, **không** phải controller Spring MVC. `@RestControllerAdvice` không mặc định bắt những exception này. Hook `AuthenticationFailureHandler` là nơi phù hợp để quyết định cách trả response cho đường form login.

**Lưu ý demo:**
- Handler trả JSON trên endpoint form `/login` để dễ kiểm thử; ứng dụng HTML có thể chọn một **redirect chung** thay vì JSON, miễn hai loại credential failure không tạo khác biệt công khai.
- `UserDetailsService` demo chỉ có `alice`; trong hệ thống thật thay bằng repository có trạng thái account đầy đủ, không lưu mật khẩu demo trong mã.
- `formLogin` mặc định dùng `POST /login`, field `username`, `password`; khi bật CSRF, request phải kèm token CSRF hợp lệ.
- Không tự bật remember-me hoặc HTTP Basic chỉ để “dễ test”: mỗi đường authentication mới cần chính sách và kiểm thử riêng.
- Không biến mọi `AuthenticationException` thành cùng một lỗi hạ tầng không thể giám sát: log/telemetry nội bộ vẫn cần phân loại failure an toàn.
- Cấu hình này **không** tự tạo REST JWT login API; nó chỉ thể hiện một cách chuẩn hóa response của form-login filter.

File `src/main/java/example/enumeration/EnumerationDemoApplication.java`:

```java
package example.enumeration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EnumerationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EnumerationDemoApplication.class, args);
    }
}
```

Chạy với Gradle wrapper của project:

```bash
./gradlew bootRun
```

Khi ứng dụng chạy local, mẫu request **thiếu CSRF token** có thể bị trả `403` ngay tại CSRF filter, **trước** khi tới kiểm tra username/password. Đừng hiểu đó là hành vi của `DaoAuthenticationProvider`. Dùng form login được Spring Security tạo để lấy CSRF token hợp lệ, hoặc thực hiện MockMvc test với `.with(csrf())` như mục 9.

## 9. Kiểm thử Spring Security: cả username không có và password sai

Tạo `src/test/java/example/enumeration/EnumerationFailureTest.java`:

```java
package example.enumeration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@SpringBootTest
@AutoConfigureMockMvc
class EnumerationFailureTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicFailureResponsesAreIdentical() throws Exception {
        MockHttpServletResponse wrongPassword =
            mvc.perform(post("/login").with(csrf())
                    .param("username", "alice")
                    .param("password", "definitely-wrong"))
                .andReturn().getResponse();

        MockHttpServletResponse unknownAccount =
            mvc.perform(post("/login").with(csrf())
                    .param("username", "not-registered")
                    .param("password", "definitely-wrong"))
                .andReturn().getResponse();

        assertEquals(401, wrongPassword.getStatus());
        assertEquals(401, unknownAccount.getStatus());

        assertEquals(
            wrongPassword.getContentAsString(),
            unknownAccount.getContentAsString()
        );
        assertEquals(
            wrongPassword.getContentType(),
            unknownAccount.getContentType()
        );
        assertEquals(
            "{\"error\":\"INVALID_CREDENTIALS\"}",
            wrongPassword.getContentAsString()
        );
    }
}
```

**Import cần là một dòng thật.** Trong Java, `import static` phía trên phải viết nguyên một dòng:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

Nếu copy file test, dùng **dòng import đầy đủ** này thay hai dòng đã bẻ cho dễ hiển thị. `MockMvc` không cần browser/SMTP, nhưng test context phải tìm thấy class `EnumerationDemoApplication` và bean `SecurityFilterChain`.

Điều bài test chứng minh:
- Hai lần login thất bại có **cùng HTTP status, Content-Type và JSON body**.
- Test chạy qua filter Spring Security với CSRF hợp lệ, không bỏ qua filter như khi tự gọi controller.
- Không trả trực tiếp `UsernameNotFoundException` ra client.

Điều nó **không** chứng minh:
- Không có timing discrepancy qua mạng thật.
- Không có khác biệt `Set-Cookie`, các headers khác hoặc đường proxy/CDN.
- Các endpoint password reset, signup, OTT hoặc API mobile cũng an toàn.
- Dữ liệu account trạng thái locked/disabled có response giống các nhánh trên.
- Mã nguồn đã triển khai rate limit, captcha hoặc cơ chế chống enumeration liên dịch vụ.

### 9.1. Unit test provider cho hai exception

Có thể kiểm tra `DaoAuthenticationProvider` mặc định bằng Java/JUnit nếu custom provider được cấu hình thủ công:

```java
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

// Trong một @Test, với imports và Assertions.assertThrows(...).
var encoder = new BCryptPasswordEncoder();
var service = (org.springframework.security.core.userdetails.UserDetailsService)
    username -> {
        if (!"alice".equals(username)) {
            throw new UsernameNotFoundException("Not found");
        }
        return User.withUsername("alice")
            .password(encoder.encode("secret"))
            .roles("USER").build();
    };

var provider = new DaoAuthenticationProvider(service);
provider.setPasswordEncoder(encoder);

var wrong = UsernamePasswordAuthenticationToken.unauthenticated(
    "alice", "incorrect");
var missing = UsernamePasswordAuthenticationToken.unauthenticated(
    "unknown", "incorrect");

assertThrows(BadCredentialsException.class,
    () -> provider.authenticate(wrong));
assertThrows(BadCredentialsException.class,
    () -> provider.authenticate(missing));
```

`assertThrows` trong snippet là static import từ `org.junit.jupiter.api.Assertions.assertThrows`. Đây là **đoạn code minh họa trong một `@Test`** chứ không phải class Java đầy đủ. Nó kiểm tra masking của loại exception; **không** dùng ngưỡng tuyệt đối để khẳng định phương thức chạy constant-time.

## 10. Forgot password: đường rò rỉ qua email và công việc đồng bộ

Giả sử controller:

```java
// SAI: sai nội dung, sai status và timing.
if (accountRepository.existsByEmail(email)) {
    mailService.sendResetEmail(email); // SMTP blocking
    return ResponseEntity.ok("Đã gửi email");
}
return ResponseEntity.status(404).body("Email không tồn tại");
```

Nhánh có user vừa có nội dung khác, vừa có network call SMTP lâu hơn. Sửa mỗi text không đủ nếu vẫn:

```java
// Vẫn có timing discrepancy nếu một nhánh gọi SMTP đồng bộ.
if (accountRepository.existsByEmail(email)) {
    mailService.sendResetEmail(email);
}
return ResponseEntity.ok("Nếu tài khoản phù hợp tồn tại...");
```

### Kiến trúc tốt hơn: chỉ xác nhận đã nhận yêu cầu

```text
POST /account/recover
       |
       v
Validate input cơ bản + anti-automation
       |
       v
Đưa một công việc vào queue bất đồng bộ
       |
       +--> HTTP 202 + message chung (không chờ DB/SMTP)
       |
       v
Worker phía server:
  -> tra cứu account
  -> nếu đủ điều kiện: phát reset token và gửi tới kênh đã xác minh
  -> nếu không đủ điều kiện: không phát token
  -> log nội bộ, audit, giới hạn tần suất và xử lý retry
```

Nhánh HTTP trước khi phản hồi nên gần giống nhau với account có/không có. Trong worker, phải bảo đảm **không** gửi reset token tới địa chỉ tùy ý do người gửi request chọn cho một account khác.

Ví dụ contract của controller (Java 17+, Spring MVC); **cần triển khai bean `RecoveryJobQueue` thực** bằng hàng đợi bền vững, đây là kiến trúc tham chiếu, không phải hệ thống email độc lập:

```java
package example.enumeration;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RecoveryController {
    private final RecoveryJobQueue queue;

    public RecoveryController(RecoveryJobQueue queue) {
        this.queue = queue;
    }

    @PostMapping(
        path = "/account/recover",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> recover(
            @RequestParam("email") String email) {

        queue.enqueue(email); // Enqueue cùng cách, không lookup user ở đây.
        return ResponseEntity.accepted()
            .body("Nếu tài khoản phù hợp tồn tại, hướng dẫn sẽ được gửi.");
    }
}
```

Interface của queue:

```java
package example.enumeration;

public interface RecoveryJobQueue {
    void enqueue(String email);
}
```

**Đây là hai file Java khác nhau**, chưa có implementation của `RecoveryJobQueue`; phải cung cấp bean thực và cấu hình retry/TTL/error monitoring trước khi chạy. Nếu queue bị lỗi hoặc quá tải, cần chính sách trả lỗi hệ thống đúng và an toàn; không im lặng tuyên bố đã xử lý khi không hề có công việc nào được nhận.

### Token reset hợp lệ phải có gì?

- Sinh bằng nguồn ngẫu nhiên mật mã (`SecureRandom` hoặc dịch vụ tương đương), entropy đủ và không thể đoán.
- Bind đúng account và **mục đích** password reset; không dùng token login/OTT một cách tùy tiện.
- TTL ngắn, single-use, consume nguyên tử.
- Lưu verifier/hash token an toàn; tránh lưu raw token trong log/database nếu không cần thiết.
- Trả token **chỉ** qua kênh email/phone đã được verify của account thật.
- Rate limit theo kênh/account/IP và giám sát abuse.
- Không tự đăng nhập với assurance/MFA hoàn chỉnh chỉ nhờ reset password.

### Xử lý side-channel trên email delivery

Không thể luôn giấu được rằng email đã thực sự đến mailbox thuộc về account, vì người sở hữu mailbox hợp lệ có thể quan sát nó. Mục tiêu chống enumeration công khai là người lạ **không nhận được câu trả lời xác nhận membership từ endpoint** và không được gửi email chứa bí mật về kênh do họ chọn. Bảo mật ở đây là giảm rò rỉ cho **người yêu cầu không được chứng thực**, không phải giả vờ không có side effect trong mọi hệ thống.

## 11. Đăng ký tài khoản và kiểm tra username có sẵn

Đăng ký luôn phải kiểm tra trùng để giữ tính duy nhất, nhưng cách **công bố kết quả** là quyết định bảo mật riêng.

### Các mẫu cần cân nhắc

**Mẫu A — Chỉ xác nhận qua email:** người dùng gửi email, server xử lý bất đồng bộ, UI nói chung “Vui lòng kiểm tra hộp thư nếu địa chỉ đủ điều kiện”. Với email đã có account, có thể gửi hướng dẫn an toàn tới chính mailbox đó hoặc đơn giản không gửi (tùy policy). Việc một ai đó gửi request lặp đi lặp lại phải bị throttling.

**Mẫu B — Username công khai:** một social network có thể cho biết username đã được dùng, vì username vốn là public identifier. Vẫn nên rate limit và chống bulk scraping. Điều này **không** đồng nghĩa được tiết lộ email/số điện thoại của user.

**Mẫu C — Chỉ sau xác minh quyền sở hữu:** có thể xác nhận trạng thái chi tiết sau khi requester chứng minh điều khiển email qua một challenge, nhưng phải xác minh challenge, TTL, single-use và giới hạn phạm vi.

**Mẫu nguy hiểm:** `GET /users/exists?email=...` trả boolean không auth và không giới hạn tần suất. Một API như vậy biến hệ thống thành dịch vụ tra danh sách khách hàng.

Tính duy nhất ở DB vẫn phải được bảo vệ bằng unique constraint và transaction, không chỉ thông qua UI kiểm tra trước. Tránh trả nguyên nội dung lỗi từ database như `DuplicateKeyException: email ... already exists` ra JSON/API khi mục tiêu là ẩn membership.

## 12. OTT, OTP, WebAuthn và MFA: đừng lộ bước kế tiếp quá sớm

Những flow không dùng password cũng có nguy cơ enumeration:

### One-Time Token / magic link

Nếu `POST /ott/generate` cho biết “User không tồn tại” hoặc chỉ user có mới bị redirect tới trang “đã gửi mail”, hệ thống lộ trạng thái account. Phản hồi tiếp nhận yêu cầu nên thống nhất. `OneTimeTokenGenerationSuccessHandler` và service giao email phải chọn **kênh đã xác minh** sau khi kiểm tra account, không trả raw token cho requester. Rate limit để chống email flooding và abuse.

### TOTP/HOTP

Nếu user nhập username, hệ thống hiển thị form “Nhập mã từ Google Authenticator” **chỉ** với account đã enroll và lỗi “Chưa đăng ký OTP” với account khác, người ngoài có thể đoán cả sự tồn tại account lẫn trạng thái MFA. Cân nhắc chỉ hiện bước factor sau khi đã kiểm tra một bước xác thực thích hợp hoặc dùng lời nhắc chung theo thiết kế. Không hạ MFA vì UX muốn tránh một nhánh chậm.

### Passkey/WebAuthn

Trước khi user xác thực, việc công bố danh sách credential hoặc trạng thái “Tài khoản này có passkey” có thể lộ membership. Luồng discoverable credential/usernameless passkey giúp giảm một số truy vấn công khai theo username, nhưng không tự giải quyết mọi rò rỉ từ fallback và recovery.

### Reset MFA / recovery code

Endpoint công khai không nên cho biết account có TOTP, passkey hay recovery codes đã được phát. Nếu user không có factor, phải có recovery policy, chứ không hiển thị “Bạn chưa bật MFA” cho mọi request chứa email.

### SSO / liên kết danh tính

Home-realm discovery (chọn IdP theo email domain) có thể phải công bố domain tổ chức nhưng không nên xác nhận **cá nhân** có tồn tại ở tenant. Tránh cho `registrationId`/error URL hoặc claim từ IdP không đáng tin trở thành kênh dò membership. Nếu cần khác biệt để định tuyến tổ chức, document threat model và giới hạn tiết lộ.

## 13. API bearer, OAuth2, GraphQL và các lỗi khác

### API đăng nhập tự xây dựng

Nếu `/api/login` tự gọi `UserDetailsService` rồi trả `404` với unknown user, framework không thể tự sửa response. Sử dụng `AuthenticationManager.authenticate(...)` và một lớp response normalization có chủ đích, không tạo authenticated token khi chưa xác minh password/token.

### OAuth 2.0 Resource Server

Một token sai/chưa có khác nhau về loại lỗi OAuth2 theo chuẩn; mục tiêu account enumeration chủ yếu liên quan đến **luồng cấp token / account lookup** hoặc API tự xây, không phải ép tất cả `401 invalid_token` thành một response mơ hồ. Resource Server phải tuân theo RFC/protocol và kiểm tra issuer, audience, signature, expiry, scope. Không phản chiếu nguyên exception chi tiết chứa email/account existence vào `WWW-Authenticate` hoặc body.

### GraphQL

GraphQL thường có HTTP `200 OK` dù resolver trả lỗi trong payload. Nếu lỗi được trả:

```json
{
  "errors": [
    {
      "message": "USER_NOT_FOUND",
      "extensions": {"reason": "UNKNOWN_EMAIL"}
    }
  ]
}
```

thì vẫn lộ membership. Cần chuẩn hóa cả `errors.message`, `extensions.code`, path, nullability behavior và số bước xử lý; không chỉ status HTTP.

### Mobile và legacy clients

Có thể web login trả chung, nhưng app mobile version cũ hoặc endpoint Basic còn nói “invalid user”. Hãy rà soát **mọi client/channel** chung authentication backend, không chỉ trang UI đang được phát triển. Các API test/staging công khai cũng có thể tiết lộ danh sách account thật nếu dùng chung database.

## 14. Timing mitigation: chọn giải pháp đúng, tránh “sleep” bừa bãi

Các nguyên tắc:

1. **Cùng công việc mật mã thiết yếu**: khi xác thực password, đối với user không tồn tại, provider nên tránh bỏ qua hoàn toàn password hash verification. `DaoAuthenticationProvider` hiện đại đã có cơ chế dummy password hash cho nhánh user-not-found.
2. **Đồng nhất public response**: status, content/body, headers, redirect, encoding và page template giữa các lỗi cần ẩn.
3. **Async side effects**: xử lý gửi email, SMS, CRM/LDAP enrichment ở worker phù hợp, không chỉ nhánh known-account chờ một network call trước phản hồi.
4. **Không cho client chọn nhánh xử lý nhạy cảm**: account status, role, MFA enrollment không được tiết lộ trước bằng chứng nhận diện thích hợp.
5. **Đồng bộ chính sách các instances**: cache, rate limit, backends nhiều node có thể tạo nhóm latency dễ nhận biết.
6. **Thử nghiệm bằng thống kê**: đo nhiều mẫu trong staging, warm-up, kiểm soát network/cache/load và so sánh phân phối, không so một cặp request.
7. **Giữ hiệu năng có giới hạn**: không cố làm mọi request tốn BCrypt nhiều vòng khiến API dễ bị CPU exhaustion.
8. **Bảo vệ API trước automation**: rate limit, quota, bot detection hợp lý để giảm khả năng kẻ tấn công thu thập mẫu.

### Sai lầm: `Thread.sleep(500)` cho username không tồn tại

```java
// Không khuyến nghị:
if (user == null) {
    Thread.sleep(500);
    return genericError();
}
```

Vì:
- `sleep` cố định vẫn tạo phân phối khác khi database/hash/network thay đổi.
- Nó chỉ sửa một branch; email/MFA/provider khác vẫn rò.
- Nó giữ request thread bận, dễ bị lạm dụng làm từ chối dịch vụ.
- Kẻ tấn công có thể lấy nhiều mẫu để giảm nhiễu.
- Nó khó tương thích với deadline, load và nhiều instance.

Một hệ thống có thể cân nhắc **minimum response time có giới hạn hoặc jitter** như lớp defense-in-depth sau đánh giá, nhưng không được thay cho xử lý tương đương, throttling và quan sát. Đặt delay có giới hạn và tránh nhân CPU workload không cần thiết; không quảng cáo bảo đảm constant-time HTTP tuyệt đối.

### Sai lầm: tạo hash mới mỗi request để làm cho “nặng”

Không nên gọi `encoder.encode(randomPassword)` nhiều lần cho mọi request unknown để tạo thời gian. Điều này vừa hao CPU và tài nguyên, vừa không nhất thiết cân nhắc cùng cost với password của user thật. Cơ chế dummy encoded password được giữ lại là biện pháp gần đúng hợp lý hơn ở nhánh user-not-found, nhưng triển khai custom cần cân nhắc encoding version/cost và rate limiting.

## 15. Java 17 thuần JDK: kiểm tra sự nhất quán của response

Đoạn chương trình này **không** xác thực mật khẩu hoặc gọi Spring; nó minh họa một mapper công khai thống nhất. Mục tiêu là test deterministic với stdout chính xác. Một hệ thống thật phải gắn mapper với authentication handler và HTTP response.

File `PublicFailureMappingDemo.java`:

```java
import java.util.List;

public class PublicFailureMappingDemo {

    enum InternalReason {
        USER_NOT_FOUND,
        WRONG_PASSWORD,
        ACCOUNT_LOCKED,
        ACCOUNT_DISABLED
    }

    record PublicReply(int status, String error) {}

    static PublicReply toPublicReply(InternalReason reason) {
        // Phân loại nội bộ không được đi vào contract lỗi công khai.
        return new PublicReply(401, "INVALID_CREDENTIALS");
    }

    public static void main(String[] args) {
        List<InternalReason> reasons = List.of(
            InternalReason.USER_NOT_FOUND,
            InternalReason.WRONG_PASSWORD,
            InternalReason.ACCOUNT_LOCKED,
            InternalReason.ACCOUNT_DISABLED
        );

        PublicReply baseline = toPublicReply(reasons.get(0));
        boolean identical = true;

        for (InternalReason reason : reasons) {
            PublicReply response = toPublicReply(reason);
            identical &= baseline.equals(response);
            System.out.println(
                reason.name() + ": " + response.status()
                    + " " + response.error()
            );
        }
        System.out.println("public-identical=" + identical);
    }
}
```

Lệnh chạy:

```bash
javac PublicFailureMappingDemo.java
java PublicFailureMappingDemo
```

**stdout chính xác:**

```text
USER_NOT_FOUND: 401 INVALID_CREDENTIALS
WRONG_PASSWORD: 401 INVALID_CREDENTIALS
ACCOUNT_LOCKED: 401 INVALID_CREDENTIALS
ACCOUNT_DISABLED: 401 INVALID_CREDENTIALS
public-identical=true
```

Bài học ở đây là phân loại lỗi nội bộ và “public contract” phải tách biệt. Mapper này **không đo timing**, không so header/cookie, không là bộ xác thực. Dữ liệu `InternalReason` phải xuất phát từ pipeline server tin cậy; không gửi enum này về frontend hoặc đưa nó vào URL redirect để lộ sự khác biệt.

## 16. Kịch bản kiểm thử từ tầng unit đến end-to-end

Một test suite chống enumeration không chỉ kiểm tra body:

### 16.1. HTTP contract test

| Cặp trường hợp | Cần so sánh |
| --- | --- |
| Username không có ↔ password sai | HTTP status, media type, body, redirect |
| Account locked/disabled ↔ password sai | Cùng public login failure contract |
| Email reset đã đăng ký ↔ email lạ | Cùng response tiếp nhận yêu cầu |
| Đã enroll OTP ↔ chưa enroll OTP | Không tiết lộ trạng thái trước bằng chứng thích hợp |
| OTT account có ↔ không có | Cùng response công khai và không trả token |
| Registration email trùng ↔ email mới | Theo chính sách tiết lộ; nếu ẩn, so public response |
| GraphQL user lạ ↔ sai credential | `errors.message` và `extensions` không khác |
| Mobile client v1 ↔ web hiện đại | Cùng mức bảo vệ, không còn legacy enumeration |

Nên kiểm tra cả `Content-Length`, headers, `Set-Cookie`, `Location` và độ dài/structure JSON. Nếu response phải có `requestId` khác nhau thì test **chuẩn hóa những trường được phép khác** thay vì so nguyên byte tùy tiện. Không cho có trường như `userExists`, `matchedAccount`, `lockedUntil` trong public error.

### 16.2. Timing experiment an toàn trong staging

Thực hiện với **tài khoản thử nghiệm do nhóm kiểm soát**, không kiểm tra danh sách người dùng thật:

1. Chuẩn bị nhóm A: username hợp lệ nhưng password sai.
2. Nhóm B: username không tồn tại, cùng độ dài/định dạng, password giống nhóm A.
3. Nhóm C: account thử nghiệm locked/disabled nếu policy cần kiểm tra.
4. Warm-up service, DB pool, JIT và encoder; giữ môi trường tải ổn định.
5. Gửi các request có tần suất **giới hạn/được phép**, trộn thứ tự ngẫu nhiên để tránh hiệu ứng tải hoặc cache.
6. Ghi thời gian phía server và phía client tách biệt; so sánh phân phối `p50`, `p90`, `p95`, độ lệch và tail latency.
7. Kiểm tra cả proxy/load balancer/CDN và mạng nội bộ, không chỉ direct controller call.
8. Test thêm khi DB chậm, mail queue chậm, multi-instance, cache cold/warm và rate limit bắt đầu kích hoạt.
9. Đặt mức rủi ro chấp nhận được theo threat model, rồi sửa **nguyên nhân** chênh lệch; không tự đặt ngưỡng ms phổ quát.
10. Đảm bảo test không kích hoạt khóa account thật, gửi email hàng loạt hoặc tạo tải không kiểm soát.

**Không có magic threshold cố định** (ví dụ “chênh dưới 5 ms là an toàn”). Đối thủ có thể đo nhiều lần từ nhiều đường mạng; mức dễ khai thác phụ thuộc số lần thử được phép, độ khác biệt, nhiễu và chất lượng bảo vệ automation.

### 16.3. Test rate limit và side effects

Kiểm thử những trường hợp:
- User hợp lệ và user lạ cùng bị chặn theo chính sách public phù hợp, không lộ membership qua status `429`.
- Backend queue đã nhận yêu cầu recovery cho cả hai trường hợp; mail chỉ gửi tới account thật, không có email gửi cho người lạ.
- Reset token có TTL/single-use; không có đường nhận reset token qua response.
- Khi mail/DB lỗi, có logging/monitoring, không ghi secret, không biến lỗi thành “user exists”.
- Khi account bị khóa, response không vô tình cung cấp `lockedUntil` hay dữ liệu nội bộ.
- Hệ thống phân tán giữ trạng thái rate limiting và token consumption nhất quán.

## 17. Rate limiting: cần thiết nhưng cũng có thể tiết lộ thông tin

Rate limiting giúp giảm tốc độ đoán username/password, spam mail và khả năng lấy mẫu timing. Nhưng một hệ thống chỉ ghi bộ đếm cho account tồn tại có thể vô tình tạo chênh lệch:

```text
Tài khoản đã tồn tại: sau 5 lần -> 429 TOO_MANY_REQUESTS
Tài khoản không tồn tại: luôn -> 401 INVALID_CREDENTIALS
```

Tín hiệu `429` như vậy **chính là một phép dò sự tồn tại**.

Thiết kế tốt hơn:
- Kết hợp giới hạn **theo IP/network, client/device, hashed/normalized username input, account thật khi có** và hệ thống chống bot; chỉ có một bộ đếm theo username tồn tại là không đủ.
- Tính **cả username lạ** vào bucket theo input hoặc nguồn request phù hợp để public policy khó phân biệt.
- Với API công khai, có thể trả `429` cho giới hạn theo IP chung thay vì tiết lộ account-specific lockout; triển khai chi tiết tùy threat model.
- Dùng backoff, quota và monitoring, tránh permanent lockout chỉ vì người ngoài spam username của người thật (đó là DoS).
- Nếu dùng CAPTCHA, đừng chỉ hiển thị với tài khoản tồn tại; policy challenge cần dựa vào yếu tố rủi ro không tiết lộ membership.
- Đồng bộ trạng thái rate limit trên cluster. Test phân phối `429` theo cả user có và không có.

Rate limit **không làm body đồng nhất** và không xóa timing side channel, nhưng làm giảm số phép thử mà kẻ tấn công có thể thực hiện. Đây là một lớp bổ sung chứ không phải biện pháp duy nhất.

## 18. Account status: locked, disabled, expired và MFA enrolment

`UserDetails` có các thuộc tính như `isAccountNonLocked()`, `isEnabled()`, `isAccountNonExpired()` và `isCredentialsNonExpired()`. Spring Security có thể ném các exception khác nhau cho các trạng thái này. Chúng hữu ích cho kiểm soát account và log nội bộ, nhưng việc trả “tài khoản bị vô hiệu hóa” trước khi chứng minh quyền sở hữu có thể biến thành enumeration.

Một số cân nhắc:

- Nếu cần hỗ trợ account bị khóa thật, gửi hướng dẫn qua **kênh đã xác minh** sau một quy trình kiểm tra quyền.
- Không hiển thị số lần nhập sai còn lại chỉ cho account tồn tại nếu muốn ẩn membership.
- Account status check có thể chạy trước password verification; **timing** vì vậy có thể khác với branch mật khẩu sai. Kiểm thử trạng thái locked/disabled riêng.
- Không “chữa” discrepancy bằng cách **bỏ qua account status check** để tất cả user đăng nhập được.
- Nếu phải cung cấp thông tin locked cho user đã xác thực yếu tố phù hợp, tách **bước xác minh quyền** và **kênh hiển thị** thay vì tiết lộ từ login công khai.
- Với MFA, không công bố đăng ký passkey/TOTP của một account chỉ vì requester biết email; báo chung trước khi có bằng chứng nhận diện.
- Các thao tác recovery phải tiếp tục áp dụng account policy, tránh người lạ dùng reset flow để kích hoạt login với account bị disable.

Đây là sự khác biệt giữa **nội bộ phải biết vì sao từ chối** và **người chưa xác thực được quyền biết bao nhiêu**.

## 19. Logging, metrics và điều tra không tạo kênh phụ mới

Cần có khả năng điều tra abuse trong khi giữ privacy:

**Metrics nên xem xét:**
- Số lần thất bại trên endpoint/source và nhóm reason nội bộ.
- Tỷ lệ `401`, `403`, `429`, `5xx` theo route, client và risk level (đảm bảo không tạo public API tra reason).
- Request latency server side `p50`, `p95`, `p99` theo các luồng lỗi ở môi trường kiểm soát.
- Lượng reset/OTT requests, queue errors, email delivery errors, retry/backoff.
- Số lần user enumeration test phát hiện body/status/header/timing khác.
- Account lockout/credential stuffing cảnh báo với các rule tránh DoS.

**Đừng log**:
- Password/OTP, reset link, raw OTT, session ID, JWT/refresh token.
- Nội dung toàn bộ body authentication, nhất là dữ liệu nhạy cảm.
- Exception stack trace được trả lại response.
- Email/số điện thoại không cần thiết cho mục đích đo lường và điều tra.

Gửi event nội bộ tới hệ thống audit có giới hạn quyền. Nếu dùng pseudonymization, lưu ý một hash email thuần SHA-256 vẫn có thể bị đảo bằng dictionary khi không có secret và input entropy thấp; cần đánh giá kỹ cách bảo vệ danh tính.

## 20. Cách xử lý các trade-off UX và sản phẩm

Một số sản phẩm cần thông báo hữu ích: “Tên đăng nhập đã tồn tại” trong đăng ký, “Bạn chưa có tài khoản” trong trang hỗ trợ. Quy tắc **không phải che mọi dữ liệu bằng mọi giá**. Hãy cân nhắc:

1. Membership của hệ thống có phải thông tin nhạy cảm? Với dịch vụ y tế, tài chính, nhân sự, thông tin này có thể rất nhạy cảm.
2. Người đang hỏi đã chứng minh quyền sở hữu email/phone/identity chưa?
3. Username có được công bố công khai trong sản phẩm không?
4. Có thể chuyển hướng dẫn chi tiết vào **email gửi cho chủ tài khoản** mà không nói ra tại request công khai không?
5. Có cách hỗ trợ người dùng thật bằng recovery UI chung, help desk đã xác minh, hoặc thông báo kèm thông tin an toàn mà không tiết lộ account cho người lạ?
6. Có API/mobile/SSO flow khác vẫn cho phép suy ra membership không?
7. Có rate limit và quan sát abuse mà không biến lockout thành tín hiệu mới không?

**Một chính sách công khai phải nhất quán**, nhưng không làm hỏng những phản hồi cần thiết theo giao thức hoặc ẩn mọi lỗi vận hành. Ví dụ, server hỏng database không nhất thiết được giả làm lỗi password; thay vào đó cần xử lý an toàn, quan sát và không tiết lộ nguyên nhân liên quan đến một account cụ thể.

## 21. Checklist trước khi đưa vào production

- [ ] Đã inventory `/login`, API auth, reset password, registration, OTT/OTP, passkey, SSO, GraphQL, mobile/legacy và help desk.
- [ ] Không có response công khai chứa `USER_NOT_FOUND`, `"unknown email"`, account locked/disabled hoặc trạng thái factor trước khi có bằng chứng phù hợp.
- [ ] Hai trường hợp **username không có** và **password sai** có status, body, Content-Type, redirect, headers nhất quán.
- [ ] `DaoAuthenticationProvider` không tắt `hideUserNotFoundExceptions`; custom provider/handler có cùng nguyên tắc.
- [ ] Password verification tiếp tục dùng `PasswordEncoder` thích hợp, không plaintext/fast unsalted hash.
- [ ] Đường user-not-found không return sớm bỏ qua toàn bộ công việc mật mã nếu dùng custom provider.
- [ ] Password reset/OTT request không chờ SMTP/SMS chỉ trên nhánh account có; delivery tách qua queue có giám sát.
- [ ] Reset/OTT token entropy cao, TTL, single-use, gửi tới kênh đã xác minh, không trả trong response.
- [ ] Rate limit trên IP/client/input phù hợp, kể cả username không tồn tại; không để `429` tiết lộ account existence.
- [ ] Account lockout không trở thành DoS bằng cách kẻ lạ spam username thật.
- [ ] Các trạng thái locked/disabled/expired không tạo public side channel dễ phân biệt.
- [ ] Các chuỗi phản hồi được kiểm thử cả tiếng Việt và locale khác.
- [ ] Không có `WWW-Authenticate`, `Location`, `Set-Cookie`, response size hoặc GraphQL extensions khác theo lý do nội bộ.
- [ ] QA timing bằng tài khoản test thuộc sở hữu team, nhiều mẫu, warm-up, network/proxy, cache, cluster.
- [ ] Không dùng delay ngủ cố định làm biện pháp duy nhất; có throttling, metric và threat model.
- [ ] Nội bộ log đủ reason/code để điều tra, nhưng không ghi secrets/PII không cần thiết và không đưa reason ra client.
- [ ] Sau thay đổi backend/email/IdP/login flow, chạy regression tests chống enumeration.
- [ ] Có phương án hỗ trợ người dùng thật mà không xác nhận membership công khai.

## 22. Bài tập tự kiểm tra

**Câu 1.** API trả `401` cho cả user tồn tại và không tồn tại, nhưng username thật cần 120 ms, username lạ chỉ 4 ms. Đã an toàn chưa?

**Trả lời:** Chưa. Còn timing discrepancy có thể khai thác bằng lặp mẫu. Xem lại password verification, DB/service calls, caching và response path; dùng provider có cơ chế giảm timing attack và đo trong môi trường staging.

**Câu 2.** Đặt `setHideUserNotFoundExceptions(true)` đã đủ để bảo vệ mọi luồng account recovery?

**Trả lời:** Không. Thuộc tính liên quan `AbstractUserDetailsAuthenticationProvider` trong luồng xác thực; recovery/controller/email/OTT/custom API phải có chính sách riêng.

**Câu 3.** Forgot-password endpoint luôn trả “Đã tiếp nhận” nhưng chỉ khi user tồn tại mới đợi SMTP 300 ms. Vấn đề là gì?

**Trả lời:** Timing side channel qua SMTP. Cân nhắc queue bất đồng bộ và trả response chung; email chỉ giao tới kênh đã xác minh ở worker sau đó.

**Câu 4.** Một API rate limit theo username trả `429` sau 5 lần cho account có thật, nhưng account lạ mãi `401`. Có bảo vệ không?

**Trả lời:** Nó giảm một số tấn công đoán password nhưng tạo **enumeration oracle** mới. Cần policy rate limit không tiết lộ membership công khai.

**Câu 5.** Có nên ẩn lỗi “password sai” bằng cách trả `200 OK` và tạo session giả?

**Trả lời:** Không. Trả response thất bại chung theo contract (có thể 401/redirect), **không tạo Authentication hoặc session được xác thực** khi credential sai.

**Câu 6.** Vì sao `@ControllerAdvice` chưa chắc áp dụng cho lỗi authentication trong Spring Security form login?

**Trả lời:** `UsernamePasswordAuthenticationFilter` và `AuthenticationFailureHandler` nằm ở filter chain ngoài controller MVC. Phải cấu hình failure behavior đúng tầng và test qua filter thật.

**Câu 7.** Đăng ký account báo “Email đã được dùng” có luôn là lỗi bảo mật bắt buộc cấm không?

**Trả lời:** Tùy threat model và mức công khai của identifier. Với membership nhạy cảm, nên tránh; với username công khai có thể chấp nhận theo policy và rate limit. Quan trọng là quyết định **có ý thức**, không vô tình tiết lộ dữ liệu cá nhân.

## 23. Tóm tắt

Account enumeration là lỗi lộ thông tin qua **sự khác biệt quan sát được** giữa trường hợp tài khoản có và không tồn tại. Khác biệt có thể là thông báo, HTTP status, URL, JSON, cookie, headers, SMTP side effect hoặc thời gian phản hồi.

Để giảm rủi ro trong Spring Security:

- **Thông báo chung**, không phản chiếu exception nội bộ cho người chưa xác thực.
- **Password verification hợp lý**: dùng `DaoAuthenticationProvider`/`PasswordEncoder` đúng chuẩn, không tự short-circuit nhánh username không tồn tại; kiểm tra cả locked/disabled.
- **Recovery và OTT an toàn**: trả lời chung, queue bất đồng bộ, token có entropy/TTL/single-use và gửi đúng kênh đã xác minh.
- **Automation controls**: rate limit/anti-bot có thiết kế, không tạo `429` hay CAPTCHA đặc biệt chỉ cho account có thật.
- **QA đa lớp**: test HTTP contract, headers/cookie, định dạng JSON, timing distributions, multi-node, alternate login, GraphQL/API và logs.
- **Trade-off có chủ đích**: bảo vệ membership mà vẫn giữ khả năng trợ giúp người dùng đã được xác minh và báo cáo sự cố hạ tầng.

Mục tiêu không phải “mọi request chạy đúng 100 ms”, mà là **không vô tình cung cấp một phép thử đáng tin cậy để kẻ khác xây danh sách tài khoản**.

## 24. Tài liệu tham khảo chính thức

- OWASP Authentication Cheat Sheet — Authentication responses và discrepancy factors: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Forgot Password Cheat Sheet — response thống nhất và timing: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- OWASP Credential Stuffing Prevention Cheat Sheet — giảm automation: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security Javadoc — `AbstractUserDetailsAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security Javadoc — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — CSRF for Servlet applications: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security source — DaoAuthenticationProvider timing mitigation (`SEC-2056`): https://github.com/spring-projects/spring-security/blob/main/core/src/main/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.java
