# Phân biệt OTT do máy chủ phát hành với TOTP hoặc HOTP

## 1. Bối cảnh và mục tiêu học tập

Trong hệ thống xác thực, cụm từ **one-time** (dùng một lần) được dùng cho nhiều cơ chế khác nhau. Spring Security có tính năng **One-Time Token Login (OTT)** dành cho đăng nhập bằng token do **máy chủ cấp** và chuyển tới người dùng, ví dụ qua email trong một magic link. Trong khi đó, **HOTP** và **TOTP** là hai thuật toán tạo **One-Time Password (OTP)**: thiết bị và máy chủ cùng sở hữu một khóa bí mật, rồi tính các mã ngắn dựa trên bộ đếm hoặc thời gian.

Hai nhóm cùng hướng tới giảm giá trị sử dụng lại của mã đăng nhập nhưng **không thể thay thế cấu hình cho nhau**. `HttpSecurity.oneTimeTokenLogin(...)` không đồng nghĩa với việc Spring Security đã triển khai xác minh mã sáu chữ số từ ứng dụng authenticator.

Sau bài này, bạn có thể:

- Giải thích nguồn phát hành, cách gửi, vòng đời, trạng thái và nguyên tắc dùng một lần của **OTT**.
- Viết công thức, mô tả chuẩn **HOTP (RFC 4226)** và **TOTP (RFC 6238)**, hiểu tại sao cả hai cần enrollment khóa bí mật.
- Thiết lập **Spring Security OTT** với `oneTimeTokenLogin`, `OneTimeTokenGenerationSuccessHandler`, `OneTimeTokenService`, endpoint tạo/nhập token và cơ chế xác thực tài khoản.
- Phân biệt **passwordless magic link**, **mã OTP trong ứng dụng authenticator**, **OTP gửi qua SMS/email**, **token phục hồi/reset password**, và **Bearer access token**.
- Đánh giá replay, brute force, đồng bộ thời gian/counter, bảo vệ secret, rate limit, lộ URL, mail scanner, phishing và yêu cầu MFA.
- Kiểm thử việc tiêu thụ một lần của OTT và dùng chương trình **Java 17+** để đối chiếu HOTP/TOTP với test vector RFC.

**Phạm vi:** Spring Security Servlet/Spring MVC, trọng tâm Spring Security 6.4–6.5 và các phiên bản 7.x; HOTP/TOTP ở mức thuật toán độc lập, không ngụ ý framework tự cung cấp form TOTP end-to-end.

## 2. Bảng đối chiếu quan trọng nhất

| Tiêu chí | OTT do máy chủ phát hành | HOTP | TOTP |
| --- | --- | --- | --- |
| Tên đầy đủ | One-Time Token | HMAC-Based One-Time Password | Time-Based One-Time Password |
| Ai tạo giá trị gửi để xác minh? | **Máy chủ**, qua `OneTimeTokenService` | Thường **authenticator/client** dùng shared secret | Thường **authenticator/client** dùng shared secret |
| Đầu vào sinh giá trị | Random token/opaque identifier gắn với account và expiry | `K` (secret) và `C` (counter) | `K` và time-step `T` |
| Điều kiện chuẩn bị | Cần phương tiện liên hệ đã được xác minh; không cần cài authenticator trước | Enrollment/chia sẻ secret và đồng bộ counter | Enrollment/chia sẻ secret và đồng bộ thời gian |
| Cách người dùng nhận | Link/email/SMS/kênh ngoài luồng do máy chủ gửi | Authenticator/hardware OTP | Authenticator/hardware OTP |
| Mã thường thấy | Chuỗi dài, URL token/magic link | 6–8 chữ số (hay dùng) | 6–8 chữ số (hay dùng) |
| Thời hạn | Expiry do máy chủ chỉ định, ví dụ vài phút | Theo **bộ đếm sự kiện**, không tự hết hạn theo đồng hồ | Theo **cửa sổ thời gian**, thường 30 giây |
| Chặn dùng lại | Xóa/đánh dấu đã tiêu thụ **nguyên tử** trên server | Tăng counter sau khi xác minh, không nhận counter cũ | Theo dõi time-step đã dùng để chặn reuse trong cùng cửa sổ |
| Trạng thái server | Token→account/expiry/used, cache/DB | Secret và counter được chấp nhận tiếp theo | Secret, chính sách clock skew và trạng thái replay |
| Hỗ trợ sẵn trong Spring Security | **`oneTimeTokenLogin` từ 6.4** | Không phải chức năng của `oneTimeTokenLogin` | Không phải chức năng của `oneTimeTokenLogin` |
| Tình huống phổ biến | Passwordless login, magic link | Hardware token/bộ đếm sự kiện | Mã trong authenticator, thường là bước MFA |

**Kết luận:** tiêu chí cốt lõi không nằm ở “có sáu chữ số hay không”, mà ở **cách token được tạo và xác minh**. Một OTT cũng có thể được thiết kế thành mã ngắn do máy chủ gửi qua SMS, nhưng nếu phía nhận chỉ tra một mã lưu trên server thì **nó không phải HOTP/TOTP theo RFC**.

## 3. Các thuật ngữ dễ nhầm

### OTT trong Spring Security

`OTT` ở đây là thông tin xác thực ngẫu nhiên, server tạo theo yêu cầu và liên kết với username, thời hạn. Ứng dụng gửi token cho người nhận qua kênh được thiết kế; người dùng gửi token trở lại endpoint login. Server kiểm tra token, **tiêu thụ** nó và tạo phiên `Authentication`.

Ví dụ (chỉ là chuỗi minh họa):

```text
Ứng dụng -> email người dùng:
https://login.example.org/login/ott?token=8a3ddab3-...-random

Người dùng bấm liên kết -> browser tới trang nhập/xác nhận.
Browser gửi token tới endpoint xử lý OTT.
Server xác minh token chưa hết hạn/chưa dùng -> đăng nhập -> token mất hiệu lực.
```

Tính chất **single-use** đến từ trạng thái và thao tác consume do server quản lý, không phải từ một công thức HMAC dựa trên giây hiện tại. Cùng một token được gửi lại lần hai phải thất bại.

### OTP là họ mã xác thực, không mặc định là TOTP

`OTP` là khái niệm rộng. Những hệ thống khác nhau có thể gọi một mã ngẫu nhiên SMS do máy chủ phát hành là “OTP”. Vì vậy:

- **OTP gửi SMS/email** có thể là mã ngẫu nhiên lưu DB, tức mô hình **server-issued code** gần OTT về mặt kiến trúc.
- **HOTP** phải được tính từ shared secret và counter theo RFC 4226.
- **TOTP** phải được tính từ shared secret và time-step theo RFC 6238.
- **Recovery code** là mã dự phòng dùng một lần, thường được tạo trước, lưu/đối chiếu an toàn ở máy chủ. Nó không đương nhiên là TOTP/HOTP.
- **Password reset token** xác minh quyền được đặt lại password, không nên được dùng như phiên đăng nhập chung nếu sản phẩm không chủ đích cho phép.
- **Bearer access token** (JWT/opaque) cũng được gọi là token nhưng thường được dùng lại cho nhiều request cho tới khi hết hạn/thu hồi; nó **không tự là OTT**.

### Passwordless và MFA là hai câu hỏi khác nhau

**Passwordless** là đăng nhập không cần password truyền thống ở bước đó. Một magic link OTT tới email có thể tạo phiên bằng việc chứng minh quyền kiểm soát mailbox.

**MFA** đòi hỏi nhiều yếu tố xác thực thuộc các nhóm khác nhau theo chính sách (biết, sở hữu, sinh trắc...), và việc các yếu tố có độc lập hay không. TOTP thường được dùng **sau password**, nhưng bản thân một ô nhập TOTP không tự chứng minh ứng dụng đã thực hiện MFA. Tương tự, OTT gửi email không tự trở thành “yếu tố thứ hai” nếu toàn bộ phiên dựa vào cùng một mailbox chưa được kiểm soát.

## 4. Luồng OTT: máy chủ phát hành, giao nhận và tiêu thụ

Spring Security Servlet cung cấp DSL `oneTimeTokenLogin(...)` từ **6.4**. Cơ chế gồm hai bước:

```text
Browser                      Spring Security                    Delivery
  |                                |                               |
  | POST /ott/generate             |                               |
  | username=linh                  |                               |
  |------------------------------->| GenerateOneTimeTokenFilter    |
  |                                | -> OneTimeTokenService.generate
  |                                |    (username, expiresAt)      |
  |                                | -> handler nhận OneTimeToken  |
  |                                |------------------------------>| Email/SMS
  |<-------------------------------| response chung                |
  |                                |                               |
  | Người dùng nhận magic link/token                             |
  | GET /login/ott?token=...       |                               |
  |------------------------------->| Default submit page          |
  | POST token tới login processor |                               |
  |------------------------------->| OneTimeTokenAuthenticationFilter
  |                                | -> AuthenticationProvider     |
  |                                | -> OneTimeTokenService.consume
  |                                | -> user lookup/authorities    |
  |<-------------------------------| session/login hoặc lỗi       |
  |                                |                               |
  | Gửi lại token cũ              |                               |
  |------------------------------->| consume thất bại             |
  |<-------------------------------| không được xác thực lần hai  |
```

Các điểm cần hiểu:

1. **Phát hành (`generate`)**: nhận thông tin account, TTL, tạo một token khó đoán và lưu khả năng kiểm chứng/tiêu thụ trên server. Trên implement mặc định in-memory, giá trị được tạo ngẫu nhiên; không có khóa HMAC chia sẻ với ứng dụng authenticator.
2. **Giao token**: Spring Security không biết email hay điện thoại nào thuộc user; cần một `OneTimeTokenGenerationSuccessHandler` gửi tới kênh đã được xác minh. Không trả token trong response công khai cho người yêu cầu.
3. **Nộp token**: người dùng nhập hoặc dùng link dẫn tới trang submit. Browser chuyển token tới authentication filter.
4. **Tiêu thụ (`consume`)**: một token hợp lệ chỉ được xác nhận **một lần**, kể cả có hai request đồng thời. Implement server-side phải bảo đảm atomicity trong multi-instance.
5. **Đăng nhập**: sau khi consume, authentication provider nạp `UserDetails`/authorities phù hợp; authorization vẫn là bước khác.
6. **Hết hạn**: không có quyền dùng lại khi quá TTL; việc giải phóng dữ liệu token hết hạn phải được quản lý.
7. **Yêu cầu không hợp lệ**: token lạ, đã dùng, hết hạn, bị hủy phải thất bại. Không nói cho người ngoài biết username có tồn tại.

Cụ thể, mặc định Spring Security dùng `POST /ott/generate` để yêu cầu mã và trang submit `GET /login/ott`; `loginProcessingUrl` có thể tùy biến. Xem API thực tế để xác định POST URL và tham số khi thay form. Hình thức đường dẫn chỉ là cấu hình HTTP, không quy định thuật toán OTT.

## 5. Thành phần Spring Security cần nhận biết

| Thành phần | Vai trò |
| --- | --- |
| `HttpSecurity.oneTimeTokenLogin(...)` | Bật đường đăng nhập OTT trong Servlet `SecurityFilterChain` |
| `GenerateOneTimeTokenFilter` | Nhận yêu cầu phát hành token |
| `OneTimeTokenGenerationSuccessHandler` | Gửi token qua email/SMS hoặc kênh tin cậy sau khi tạo |
| `OneTimeTokenService` | `generate(GenerateOneTimeTokenRequest)` và `consume(OneTimeTokenAuthenticationToken)` |
| `OneTimeToken` | Mang `tokenValue`, `username`, `expiresAt` |
| `OneTimeTokenAuthenticationFilter` | Nhận token do người dùng nộp ở login endpoint |
| `OneTimeTokenAuthenticationProvider` | Xác thực pre-auth token và tra user, làm việc với service |
| `DefaultOneTimeTokenSubmitPageGeneratingFilter` | Tạo trang nhập OTT mặc định khi bật tính năng tương ứng |
| `InMemoryOneTimeTokenService` | Lưu token trong bộ nhớ một instance, thích hợp demo/test |
| `JdbcOneTimeTokenService` | Một lựa chọn persistent được Spring Security cung cấp cho triển khai dùng DB |
| `UserDetailsService` | Nạp tài khoản/authorities của người được đăng nhập |

**Phân biệt tên dễ nhầm:** `OneTimeTokenAuthenticationToken` là object triển khai `Authentication` dùng trong pipeline; nó không phải token OAuth Bearer để đặt trong header. `OneTimeToken` là đối tượng thể hiện giá trị bí mật với thông tin account và expiry.

### Cảnh báo an toàn về account status

Ở một số dòng Spring Security hiện hành, `OneTimeTokenAuthenticationProvider` **không mặc định kiểm tra đầy đủ** trạng thái `disabled`, `locked`, `accountExpired`. Kiểm tra Javadoc của phiên bản và cấu hình `AccountStatusUserDetailsChecker` cho provider nếu chính sách sản phẩm cần từ chối tài khoản bị vô hiệu hóa. Chỉ tạo `UserDetails` với `enabled(false)` chưa đủ để tự kết luận mọi phiên bản OTT đều chặn nó.

## 6. Ví dụ Spring Boot 3.4+/Spring Security 6.4+ (Servlet, Java 17)

Ví dụ sau minh họa **một đường đăng nhập OTT**, không có TOTP. Để tránh khuyến khích gửi token công khai, ví dụ sử dụng email delivery và chỉ dùng danh bạ email đã được xác minh. Các địa chỉ `example.org` chỉ là dữ liệu giả lập; ứng dụng thực tế phải cung cấp SMTP và record user có thật.

### 6.1. Dependencies

Trong `build.gradle` của một dự án Spring Boot đã cấu hình plugin và BOM tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Dùng Spring Boot **3.4+** hoặc cấu hình dependency có Spring Security **6.4+** cho API `oneTimeTokenLogin`. Một project Spring Boot 3.3 dùng Spring Security 6.3 mặc định sẽ không có API này chỉ vì copy code. Để dùng `JdbcOneTimeTokenService` trong production còn cần JDBC/DataSource và schema database thích hợp; ví dụ chưa bật JDBC.

`application.yml`:

```yaml
app:
  public-base-url: ${PUBLIC_BASE_URL:https://login.example.org}
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
```

`PUBLIC_BASE_URL` phải là HTTPS hostname của SP thực tế, được cấu hình từ deployment và không nhận thẳng từ `Host`/`X-Forwarded-*` do client tùy ý gửi. SMTP credentials là bí mật vận hành, không commit vào code hoặc file ví dụ trong Git.

### 6.2. SecurityFilterChain và user lookup

File `src/main/java/example/ott/OttSecurityConfig.java`:

```java
package example.ott;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class OttSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/login", "/login/ott",
                                 "/ott/generate", "/ott/sent")
                    .permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll()
            )
            // Không bật formLogin/httpBasic cho demo passwordless này.
            .oneTimeTokenLogin(withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails user = User.withUsername("demo")
            // Demo: không có login bằng password được bật trong filter chain.
            .password("{noop}unusable-for-real-login")
            .authorities("ROLE_USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }
}
```

Ở trên, mật khẩu `UserDetails` không được dùng để kiểm tra OTT và đường `formLogin`/`httpBasic` không được bật. **Không mang password `{noop}` này sang ứng dụng production**, nhất là nếu sau này có login bằng password ở chain khác. Hệ thống thật phải dùng repository account, trạng thái account và quyền theo nghiệp vụ. Login OTT được chấp nhận chỉ khi nạp được account hợp lệ theo chính sách provider đã kiểm tra.

### 6.3. Danh bạ email đã được xác minh

File `src/main/java/example/ott/VerifiedEmailDirectory.java`:

```java
package example.ott;

import java.util.Optional;

@FunctionalInterface
public interface VerifiedEmailDirectory {
    Optional<String> findVerifiedEmail(String username);
}
```

Thêm bean **chỉ dùng trong demo** vào một class `@Configuration` hoặc class cấu hình phía trên:

```java
@Bean
VerifiedEmailDirectory verifiedEmailDirectory() {
    return username ->
        "demo".equals(username)
            ? java.util.Optional.of("demo@example.org")
            : java.util.Optional.empty();
}
```

Đây là **đoạn chèn vào class config** (đã import `@Bean` ở file 6.2), không phải file độc lập. Trong môi trường thật, thay bằng tra cứu email **đã xác minh** và được liên kết với account. Không cho phía yêu cầu tùy ý chỉ định địa chỉ nhận bằng form `email=...` rồi gửi token đăng nhập của username khác.

### 6.4. Handler gửi magic link qua email

File `src/main/java/example/ott/EmailOttSuccessHandler.java`:

```java
package example.ott;

import java.io.IOException;
import java.util.Optional;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.web.authentication.ott.RedirectOneTimeTokenGenerationSuccessHandler;

@Component
public class EmailOttSuccessHandler
        implements OneTimeTokenGenerationSuccessHandler {

    private final JavaMailSender mail;
    private final VerifiedEmailDirectory directory;
    private final String baseUrl;

    public EmailOttSuccessHandler(
            JavaMailSender mail,
            VerifiedEmailDirectory directory,
            @Value("${app.public-base-url}") String baseUrl) {
        this.mail = mail;
        this.directory = directory;
        this.baseUrl = baseUrl;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            OneTimeToken oneTimeToken)
            throws IOException, ServletException {

        Optional<String> destination =
            directory.findVerifiedEmail(oneTimeToken.getUsername());

        if (destination.isPresent()) {
            String link = UriComponentsBuilder.fromUriString(baseUrl)
                .path("/login/ott")
                .queryParam("token", oneTimeToken.getTokenValue())
                .build().encode().toUriString();

            SimpleMailMessage message = new SimpleMailMessage();
            message.setTo(destination.get());
            message.setSubject("Link đăng nhập một lần");
            message.setText("Chỉ dùng một lần, hết hạn sau thời gian quy định: "
                    + link);

            mail.send(message);
        }

        // Phản hồi cùng kiểu cho username có/không có email xác minh.
        new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent")
            .handle(request, response, oneTimeToken);
    }
}
```

`@Component` cho handler giúp DSL chọn `OneTimeTokenGenerationSuccessHandler`. Spring Security chỉ cung cấp hook giao token, **không tự biết** email nào đáng tin của user. Handler này dùng `PUBLIC_BASE_URL` tĩnh để tránh link đăng nhập bị đầu độc bởi header host. Nếu không có SMTP hợp lệ, email không gửi và demo không thể hoàn tất đăng nhập.

**Cảnh báo quan trọng:** xử lý lỗi SMTP trong production cần có chính sách chống dò user, retry có giới hạn, telemetry bảo mật và cùng một thông báo công khai cho cả user tồn tại/không tồn tại. Một lỗi email không được làm lộ token cho người yêu cầu. Email có thể bị forward và URL có thể xuất hiện trong browser history; triển khai cookie/session, referrer policy, log redaction, TLS và one-time consumption cẩn thận.

### 6.5. Controller kiểm tra user và trang phản hồi

File `src/main/java/example/ott/OttController.java`:

```java
package example.ott;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OttController {

    @GetMapping("/ott/sent")
    public String requested() {
        return "If the account is eligible, a sign-in link has been sent.";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }
}
```

File `src/main/java/example/ott/OttDemoApplication.java`:

```java
package example.ott;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OttDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OttDemoApplication.class, args);
    }
}
```

Khi project Spring Boot có SMTP, `VerifiedEmailDirectory` demo và account `demo` hợp lệ, kích hoạt:

```bash
./gradlew bootRun
```

Tại UI mặc định của Spring Security, dùng form tạo OTT để gửi `POST /ott/generate` với CSRF token hợp lệ. Nếu đang đăng nhập từ domain khác public `https://login.example.org`, phải bảo đảm browser trỏ đúng máy chủ ứng dụng và cookie/session được cấu hình chính xác.

Dự kiến sau khi nhấp link và submit token:
- `/me` hiển thị `demo` khi phiên đã xác thực.
- Đăng xuất rồi thử lại chính token vừa dùng **không** được đăng nhập lần nữa.
- Token hết hạn **không** còn dùng được.

Đây là **kết quả nghiệp vụ kỳ vọng**, không phải stdout cố định: bài chưa chứa SMTP thực, TLS config, hoặc user ngoài demo. Việc kích hoạt passwordless login bằng OTT **không** tạo TOTP seed/QR code.

## 7. Lưu trữ token OTT: in-memory, JDBC, TTL, atomicity

### InMemoryOneTimeTokenService

Spring Security cung cấp `InMemoryOneTimeTokenService` mặc định khi không có service do ứng dụng cung cấp. Theo Javadoc Spring Security 6.5, service này dùng `ConcurrentHashMap` và giá trị token random UUID; `generate` trả `OneTimeToken`, `consume` trả đối tượng token khi hợp lệ hoặc `null` khi không thể dùng.

Vì lưu trong RAM của process:

- Restart ứng dụng sẽ mất các token đang chờ.
- Hai instance A/B có bộ nhớ khác nhau sẽ không tự chia sẻ token.
- Không được dùng nó làm nơi lưu OTT phân tán trong production mà vẫn kỳ vọng token từ A tiêu thụ ở B.
- TTL không đồng nghĩa một tác vụ tự động làm sạch tất cả record ngay lập tức; xem chính sách cleanup của phiên bản cụ thể.

### JdbcOneTimeTokenService và lưu trữ bền vững

Với môi trường production nhiều instance, cân nhắc `JdbcOneTimeTokenService` và DataSource chung (hoặc service tùy chỉnh tương đương) để nắm được trạng thái token. Kiểm tra schema DB được framework hỗ trợ, yêu cầu index/cleanup, transaction, khóa/hàng và hành vi hai request đồng thời. Không tự thiết kế `SELECT` trước rồi `DELETE` sau theo hai transaction độc lập: có thể gây **double consume**.

Nguyên tắc cơ bản:

```text
Có token còn hạn và chưa dùng?
       |
       +-- không -> authentication thất bại
       |
       `-- có -> đánh dấu consumed hoặc delete một cách nguyên tử
                    |
                    `-- đúng một request thắng -> login
```

Với custom store, nên lưu **hash/digest có bảo vệ phù hợp** thay vì token thô nếu mô hình lookup cho phép, giới hạn TTL và gắn token với mục đích, username, phiên yêu cầu nếu có. Đây là khuyến nghị thiết kế custom service; **không được suy diễn** Spring `JdbcOneTimeTokenService` mặc định đã áp dụng chính xác mô hình hash nào nếu chưa kiểm tra implementation.

### Unit test consume một lần (Spring Security 6.4+)

File `src/test/java/example/ott/OttConsumeTest.java`:

```java
package example.ott;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.InMemoryOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.authentication.ott.OneTimeTokenAuthenticationToken;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class OttConsumeTest {

    @Test
    void generatedTokenCanBeConsumedOnlyOnce() {
        var service = new InMemoryOneTimeTokenService();
        OneTimeToken generated =
            service.generate(
                new GenerateOneTimeTokenRequest("demo", Duration.ofMinutes(2))
            );

        assertEquals("demo", generated.getUsername());

        var input = OneTimeTokenAuthenticationToken.unauthenticated(
            generated.getTokenValue()
        );

        assertNotNull(service.consume(input));
        assertNull(service.consume(input));
    }
}
```

Lệnh chạy trong project Gradle phù hợp:

```bash
./gradlew test --tests example.ott.OttConsumeTest
```

Bài test dùng thư viện Spring Security của project và một token ngẫu nhiên ở bộ nhớ, nên **không** có token string/stdout cố định. Test xác minh **single-use của service**, nhưng không test email delivery, HTTP/CSRF, login `Authentication` hay khả năng atomicity trên hai node JDBC. Muốn test case hết hạn, dùng `setClock(Clock)` của in-memory service để dựng `Clock.fixed`/`Clock.offset` theo thời điểm xác định thay vì `Thread.sleep`.

## 8. HOTP theo RFC 4226: bí mật chung và counter

**HOTP** là thuật toán sinh mã từ:

- `K`: khóa bí mật đã được chia sẻ lúc enrollment; cần giữ kín ở cả authenticator và server.
- `C`: counter (số nguyên 64-bit không âm) đại diện cho event/trạng thái kế tiếp.
- `HMAC-SHA1(K, C)`: MAC của counter được biểu diễn dưới dạng 8 byte big-endian.
- **Dynamic truncation**: cắt 31 bit từ HMAC với offset xác định, rồi lấy modulo `10^digits`.

Ký pháp:

```text
HOTP(K, C) = DynamicTruncate(HMAC-SHA1(K, C)) mod 10^Digits
```

Ví dụ cùng secret, các counter khác nhau sinh các mã khác nhau:

```text
Counter 0 -> 755224
Counter 1 -> 287082
Counter 2 -> 359152
```

Đây là **test vector RFC 4226** cho `K = ASCII("12345678901234567890")` và 6 chữ số. Không dùng key công khai đó trong production.

### HOTP được xác minh thế nào?

```text
Authenticator sở hữu K, counter_client
       |
       | HOTP(K, counter_client) -> mã người dùng nhập
       v
Server sở hữu K, counter_server
       |
       | Tìm trong [counter_server, counter_server + lookAhead]
       |
       +-- match tại C* -> cập nhật counter_server = C* + 1 (atomic)
       |                -> chấp nhận một lần
       `-- no match   -> từ chối, rate limit
```

Lỗi dễ mắc: chỉ so bằng secret/counter rồi **không tăng counter sau khi chấp nhận**. Khi đó một mã HOTP có thể được dùng nhiều lần, trái yêu cầu chống replay. Cửa sổ look-ahead phải đủ nhỏ để giới hạn rủi ro brute force. Nếu thiết bị và server mất đồng bộ, cần cơ chế resynchronization được kiểm soát và xác minh bổ sung.

HOTP không tự hết hạn theo 30 giây; **counter là moving factor**. Một mã có thể tiếp tục hợp lệ nếu server chưa nâng counter và chính sách không giới hạn tuổi của mã.

## 9. TOTP theo RFC 6238: HOTP với time-step

**TOTP** kế thừa HOTP, thay counter sự kiện bằng bộ đếm thời gian:

```text
T = floor((UnixTimeSeconds - T0) / X)
TOTP(K, now) = HOTP(K, T)
```

Trong đó:
- `K` vẫn là shared secret đã enrollment.
- `T0` thường là Unix epoch `0`.
- `X` thường là **30 giây**; hai bên phải thống nhất time-step.
- `Digits` thường là **6** hoặc **8**; hai bên phải thống nhất chiều dài và thuật toán HMAC.
- RFC 6238 hỗ trợ HMAC-SHA1, SHA256, SHA512; đa số authenticator tương thích phổ biến dùng SHA1 theo cấu hình provisioning.

Ví dụ ở UTC timestamp 59 giây, `X=30`, ta có `T=1`. Với secret test của RFC 6238 và 8 chữ số SHA1, mã là **94287082**.

### Enrollment là bước bắt buộc

Đường đi điển hình:

```text
Account đã xác thực với phương thức mạnh và có re-auth
           |
           v
Server tạo secret K ngẫu nhiên đủ mạnh
           |
           v
App authenticator nhận K qua QR/provisioning bảo vệ
           |
           v
Server lưu secret K được mã hóa và metadata (digits, period, algorithm)
           |
           v
User chứng minh biết K bằng một mã TOTP hợp lệ
           |
           v
Đánh dấu factor TOTP đã enrolled
```

Một provisioning URI kiểu thông dụng:

```text
otpauth://totp/Example:linh?secret=JBSWY3DPEHPK3PXP&issuer=Example&algorithm=SHA1&digits=6&period=30
```

`JBSWY3DPEHPK3PXP` chỉ là **secret demo công khai**, không có giá trị bảo mật. Trong production, không đưa secret thật vào logs, analytics, URL được browser gửi ra ngoài, mã QR công khai hoặc tài liệu. QR/URI phải được xem như **bí mật tương đương quyền tạo mã của user**. Lưu secret đã mã hóa với key quản trị riêng, giới hạn người/process được quyền giải mã.

### Xác minh TOTP không chỉ là so mã ở thời điểm hiện tại

Server thường cho phép một cửa sổ lệch đồng hồ nhỏ, ví dụ time-step `T-1`, `T`, `T+1` tùy rủi ro. Cần:
- Đồng bộ đồng hồ NTP; xác định `Clock` dùng UTC Unix epoch, không phụ thuộc múi giờ giao diện.
- So sánh mã hợp lệ theo chính sách và rate limit, khóa tạm/backoff khi thử sai.
- **Ghi nhớ time-step đã chấp nhận** cho mỗi account/factor và chặn sử dụng lại chính time-step đó (đặc biệt với nhiều request đồng thời).
- Không chấp nhận vô hạn số step lệch nhằm khắc phục đồng hồ sai; cửa sổ càng rộng, xác suất đoán đúng càng cao.
- Chống replay phân tán bằng cập nhật nguyên tử/cơ sở dữ liệu chung khi có nhiều instance.

Nói “mã thay đổi mỗi 30 giây” **không đủ** để bảo đảm one-time: nếu cùng một mã TOTP được nộp hai lần trong cùng time-step mà server không lưu trạng thái đã dùng, cả hai có thể được chấp nhận. Đây là điểm khác biệt lớn so với OTT `consume` ở server.

## 10. Java 17 thuần JDK: minh họa HOTP và TOTP theo RFC

Đoạn chương trình sau **chạy độc lập**, không cần Spring hoặc thư viện bên ngoài. Nó thực thi HMAC-SHA1, dynamic truncation, counter 8 byte big-endian và zero padding. Ví dụ giới hạn digits là 6 hoặc 8 để tránh sai số `10^digits` với `int`.

Tạo file `HmacOtpDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class HmacOtpDemo {

    static String hotp(byte[] secret, long counter, int digits) throws Exception {
        if (secret == null || secret.length == 0 || counter < 0
                || (digits != 6 && digits != 8)) {
            throw new IllegalArgumentException("Invalid HOTP parameters");
        }

        byte[] counterBytes = ByteBuffer.allocate(Long.BYTES)
            .putLong(counter)
            .array(); // ByteBuffer mặc định BIG_ENDIAN.

        Mac mac = Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec(secret, "HmacSHA1"));
        byte[] hash = mac.doFinal(counterBytes);

        int offset = hash[hash.length - 1] & 0x0f;
        int binary =
              ((hash[offset]     & 0x7f) << 24)
            | ((hash[offset + 1] & 0xff) << 16)
            | ((hash[offset + 2] & 0xff) << 8)
            |  (hash[offset + 3] & 0xff);

        int modulus = (digits == 6) ? 1_000_000 : 100_000_000;
        int code = binary % modulus;
        return String.format(Locale.ROOT, "%0" + digits + "d", code);
    }

    static String totp(
            byte[] secret, long unixSeconds, long periodSeconds, int digits)
            throws Exception {
        if (periodSeconds <= 0 || unixSeconds < 0) {
            throw new IllegalArgumentException("Invalid time or period");
        }
        long timeCounter = unixSeconds / periodSeconds; // T0 = 0.
        return hotp(secret, timeCounter, digits);
    }

    public static void main(String[] args) throws Exception {
        byte[] testSecret =
            "12345678901234567890".getBytes(StandardCharsets.US_ASCII);

        System.out.println("HOTP counter=0: " + hotp(testSecret, 0, 6));
        System.out.println("HOTP counter=1: " + hotp(testSecret, 1, 6));
        System.out.println("TOTP time=59: " + totp(testSecret, 59, 30, 8));
        System.out.println(
            "TOTP time=1111111109: "
            + totp(testSecret, 1_111_111_109L, 30, 8)
        );
    }
}
```

Lệnh chạy với JDK 17+:

```bash
javac HmacOtpDemo.java
java HmacOtpDemo
```

**stdout chính xác theo RFC 4226/6238:**

```text
HOTP counter=0: 755224
HOTP counter=1: 287082
TOTP time=59: 94287082
TOTP time=1111111109: 07081804
```

Giải thích:
- `ByteBuffer` đóng gói counter thành 8 byte; không được HMAC chuỗi thập phân `"0"` hay `"59"`.
- `Mac` tạo HMAC-SHA1; dynamic truncation lấy offset từ 4 bit thấp của byte cuối và tạo số **31 bit không dấu**.
- `modulus` và `String.format` giữ đủ số chữ số, bao gồm các số 0 đầu như `07081804`.
- Với TOTP, ta dùng `unixSeconds / periodSeconds` khi `T0=0`. Với `59 / 30` ra time-step `1`.
- `HmacSHA1` ở ví dụ được chọn để so **RFC test vector**, không có nghĩa mọi thiết bị TOTP chỉ hỗ trợ SHA1.
- Không dùng nguyên chương trình này làm dịch vụ login production: nó **chỉ sinh mã**, không lưu secret an toàn, không enrollment, không so sánh constant-time, không replay prevention, không rate limit, không kiểm tra account status.

### Tại sao ví dụ không có API Spring Security OTT?

Đây là **thuật toán HOTP/TOTP** theo RFC; nó không gọi `OneTimeTokenService`. Ngược lại, ví dụ OTT ở mục 6 tạo và tiêu thụ token bằng Spring Security mà **không** biết `K`, `C` hay time-step. Mục tiêu là phân biệt rõ hai cơ chế, không cấy mã HOTP vào `OneTimeTokenGenerationSuccessHandler` rồi gọi đó là triển khai TOTP chính thức.

## 11. So sánh xác minh và chống replay bằng tình huống

### Tình huống A — Người dùng nhận OTT qua email

1. Linh yêu cầu magic link từ ứng dụng.
2. Server phát `tokenA`, gắn với Linh, hết hạn sau ít phút.
3. Link được gửi đến mailbox đã xác minh.
4. Linh nhấp link, submit `tokenA`. Server **consume** và đăng nhập.
5. Linh mở lại URL cũ: bị từ chối vì tokenA đã tiêu thụ.
6. Nếu hacker chặn link và dùng **trước** Linh, token vẫn là một bearer credential có thể bị chiếm dụng. Single-use không bảo vệ chống việc dùng trước bởi kẻ tấn công.

### Tình huống B — Authenticator tạo TOTP

1. Linh enroll secret `K` với account.
2. Authenticator tại thời điểm `T` sinh mã `123456` (ví dụ, không phải giá trị dự đoán của demo).
3. Server tính và so mã tại các time-step cho phép.
4. Nếu xác minh thành công, server ghi nhận `T` đã dùng.
5. Gửi lại `123456` trong time-step cũ phải bị từ chối theo chính sách chống replay.
6. Khi sang time-step mới, app sinh mã mới và người dùng không phải chờ email.

Điểm tinh tế: nếu triển khai TOTP chỉ tính `T` hiện tại rồi so sánh mã mà **không theo dõi đã dùng**, một mã có thể hợp lệ nhiều lần trong cùng 30 giây. Tính chất **time-based** không thay thế yêu cầu **one-time acceptance**.

### Tình huống C — HOTP trên thiết bị vật lý

1. Token phần cứng có secret `K`, counter thiết bị ban đầu `C=8`.
2. Người dùng bấm nút, thiết bị tạo HOTP cho `C=8` rồi tăng counter.
3. Server giữ counter tiếp theo mong đợi `Cserver=8`; sau khi xác minh mã tại 8, cập nhật 9.
4. Một người bấm thiết bị nhiều lần không dùng mã có thể làm counter phía client chạy trước server.
5. Server cần cửa sổ look-ahead hoặc resynchronization có chính sách; không dùng time-window của TOTP để sửa counter của HOTP.

## 12. Chọn công nghệ đúng theo mục tiêu

| Mục tiêu | Gợi ý |
| --- | --- |
| Đăng nhập không mật khẩu qua email tới người đã có mailbox xác minh | OTT/magic link với token được server cấp |
| Người dùng đã đăng nhập bằng password và cần yếu tố bổ sung trong authenticator | TOTP nếu chính sách cho phép OTP; cân nhắc WebAuthn/passkeys cho chống phishing mạnh hơn |
| Thiết bị/hardware key sinh mã theo lần bấm, không dựa vào đồng hồ | HOTP |
| Gửi mã ngắn qua SMS/email mà người dùng chưa cài app | Mã do server cấp và xác minh server-side; **không gọi nó là TOTP/HOTP** nếu không theo RFC |
| Chứng thực giao dịch/động tác nhạy cảm | Yếu tố có liên kết tới giao dịch/nguồn gốc yêu cầu, re-auth và chính sách chống phishing; không tự kết luận OTT/TOTP đơn lẻ đủ |
| Hệ thống nhiều node cần token không bị dùng hai lần | Token store chung với atomic consume; với OTP lưu replay/counter state chung |
| Muốn bảo vệ tốt trước phishing và AitM | WebAuthn/FIDO2/passkey với ràng buộc origin, so với OTT/TOTP có thể bị phish |

Đừng quyết định chỉ bằng số chữ số hoặc cảm giác “token nào cũng giống token”. Phải bắt đầu từ **người dùng sở hữu gì, server tin thông tin nào, cơ chế nào ngăn replay và có cần enrollment không**.

## 13. Các nguy cơ an ninh và biện pháp cụ thể

### Với OTT / magic link

- **Bí mật của token:** URL chứa OTT là credential. Không ghi raw URL/query token vào access logs, analytics, APM, chat hoặc hệ thống báo lỗi.
- **TLS:** gửi qua HTTPS; không dùng HTTP bên ngoài môi trường local cô lập.
- **Phát hành:** giới hạn số lần tạo token trên account/IP/device, chống email flooding/SMS abuse, dùng phản hồi chung chống username enumeration.
- **Gửi tới đúng người:** địa chỉ email/điện thoại phải đã được verify, không nhận địa chỉ mới từ request chưa được chứng thực để tránh account takeover.
- **Single-use:** `consume` phải nguyên tử; không cho hai request cùng token thành công.
- **Expiry:** TTL ngắn hợp lý; token mới có làm token cũ vô hiệu không phải giả định chung, hãy định nghĩa và kiểm thử policy của service.
- **Mail link scanner/prefetch:** bot kiểm tra liên kết có thể tự **GET** URL. Thiết kế để GET chỉ mở trang xác nhận/submit; không tự đổi thành authenticated session khi GET nếu sản phẩm cần chống prefetch.
- **Session binding:** xem xét rủi ro login CSRF, session fixation, đổi session sau đăng nhập và browser khác mở link; tránh một đường link bị dùng để đăng nhập nạn nhân vào account kẻ tấn công.
- **Logging:** chỉ ghi request ID và lý do failure ở mức vừa đủ, không ghi token.
- **Trạng thái user:** khóa/vô hiệu hóa account hoặc đổi email phải được áp dụng vào OTT login theo policy, không chỉ rely vào dữ liệu của token đã phát.
- **Khôi phục:** mailbox bị chiếm có thể đồng nghĩa account bị chiếm; cần điều kiện khôi phục và phát hiện rủi ro độc lập.

### Với HOTP/TOTP

- **Secret K:** sinh bằng CSPRNG, độ dài/thuật toán theo policy, bảo vệ khi lưu, backup và vận chuyển; nếu K bị lộ, kẻ khác tạo mã giống authenticator.
- **Enrollment:** yêu cầu re-auth cho thêm/xóa/reset authenticator; có xác minh mã trước khi bật và cảnh báo người dùng khi cấu hình factor thay đổi.
- **Rate limit:** mã 6 chữ số chỉ có khoảng một triệu khả năng trước khi xét cửa sổ chấp nhận; cần giới hạn số lần đoán, chống phân tán brute force.
- **Clock/counter:** TOTP cần đồng bộ thời gian và drift limit; HOTP cần quản lý counter atomically, resync có giới hạn.
- **Replay:** theo dõi last accepted step/counter; đừng chỉ dựa vào câu “mã đã hết hạn”.
- **Phishing:** mã OTP có thể bị kẻ tấn công dụ nộp và dùng ngay; OTP không mặc nhiên phishing-resistant.
- **Backup/recovery:** recovery codes phải phát riêng, lưu an toàn, mỗi code tiêu thụ một lần, và reset factor phải qua quy trình tin cậy.

### Hai nhóm cùng cần chính sách bổ sung

Không cho phép input người dùng chọn `username` của người khác rồi **bypass** yêu cầu verify email/secret. Quyền vào endpoint sau login vẫn dựa trên `Authentication`/authorization. Khóa hoặc thu hồi phương thức login là thao tác riêng với việc vô hiệu hóa session đã tồn tại.

## 14. Kiểm thử và QA theo cơ chế

| Bài kiểm thử | OTT | HOTP/TOTP |
| --- | --- | --- |
| Sinh giá trị hợp lệ | `OneTimeTokenService.generate` | Test vector RFC / thuật toán HMAC |
| Giá trị gửi đi đến ai? | Địa chỉ liên hệ **đã xác minh** | Secret được enrollment đúng thiết bị |
| Dùng lại cùng giá trị | Lần thứ hai `consume` phải fail | Counter/time-step đã chấp nhận phải bị từ chối |
| Hết hạn | TTL/token expiry | TOTP hết time-window; HOTP dùng counter, không có TTL 30 giây mặc định |
| Hai request đồng thời | Đúng một consume thắng | Replay state/counter phải update nguyên tử |
| User không tồn tại | Response ngoài không tiết lộ | Không có secret/enrollment hợp lệ |
| User locked/disabled | Check account status/provider | Check account status trước khi xác minh/hoàn tất login |
| Rate limit | Chặn spam generate và brute-force consume | Chặn brute-force theo user/IP/device/time window |
| Lệch thời gian | Chủ yếu dựa trên expiry của server | TOTP phải thử drift có giới hạn |
| Lệch counter | Không áp dụng | HOTP look-ahead/resynchronization |
| Mất DB/node | Kiểm tra token store shared, expiry, consistency | Kiểm tra secret, last accepted step/counter được lưu bền |
| Thay đổi secret hoặc mailbox | Hủy token cũ/verify email mới theo policy | Thu hồi/re-enroll secret và invalidation phù hợp |

**OTT integration test** cần quan sát HTTP flow, CSRF, email delivery (mail test server), cookie/session và lần login đầu vs lần hai. **HOTP/TOTP unit test** cần dùng RFC vector và failure paths; sau đó integration test hành vi MFA và account recovery. Một JUnit test chỉ gọi hàm tính HMAC không khẳng định hệ thống đã chống phishing, chống replay hoặc thực thi MFA đúng.

## 15. Khác biệt API theo phiên bản Spring Security

| Phiên bản | Trạng thái/hướng triển khai |
| --- | --- |
| **Trước 6.4** | Không có `oneTimeTokenLogin` DSL như ví dụ bài này; muốn magic link phải tự triển khai quy trình hoặc nâng cấp |
| **6.4** | Thêm hỗ trợ OTT Login, `OneTimeTokenService`, handler và các filter liên quan |
| **6.5** | Mở rộng tùy chỉnh request tạo OTT; dùng `GenerateOneTimeTokenRequestResolver` trong Servlet |
| **7.x** | OTT vẫn tồn tại; xem đúng Javadoc của phiên bản vì method URL config và account status/MFA có thể thay đổi giữa minor; không copy nhầm API Servlet và Reactive |
| **Reactive/WebFlux** | Có thành phần reactive riêng như `ReactiveOneTimeTokenService` và `ServerOneTimeTokenGenerationSuccessHandler`; không gắn `OneTimeTokenAuthenticationFilter` Servlet trực tiếp vào `SecurityWebFilterChain` |

Với Spring Security 6.5, ví dụ thay TTL mặc định 5 phút thành 10 phút bằng một bean **chèn vào** class cấu hình (import thích hợp cho package Servlet `web.authentication.ott`):

```java
@Bean
GenerateOneTimeTokenRequestResolver generateOneTimeTokenRequestResolver() {
    DefaultGenerateOneTimeTokenRequestResolver delegate =
        new DefaultGenerateOneTimeTokenRequestResolver();

    return request -> {
        GenerateOneTimeTokenRequest original = delegate.resolve(request);
        return new GenerateOneTimeTokenRequest(
            original.getUsername(), Duration.ofMinutes(10)
        );
    };
}
```

Code này dùng `GenerateOneTimeTokenRequest` ở package `org.springframework.security.authentication.ott`, còn `GenerateOneTimeTokenRequestResolver`/`DefaultGenerateOneTimeTokenRequestResolver` ở `org.springframework.security.web.authentication.ott`; cần các import phù hợp và `java.time.Duration`. **Đây là snippet trong cấu hình**, không phải một file Java độc lập; phiên bản 6.4 có thể chưa cung cấp hook tùy biến này.

Ở 6.5, tài liệu Servlet còn dùng tên cấu hình URL **`generateTokenUrl(...)`**, trong khi một số Javadoc/tài liệu 7.x dùng **`tokenGeneratingUrl(...)`**. Chỉ áp dụng method phù hợp version trong dependency tree của project. Các thay đổi tên URL config không biến OTT thành thuật toán TOTP hay HOTP.

## 16. Câu hỏi tự kiểm tra

**Câu 1:** Người dùng nhập `123456` nhận từ SMS của server. Có đủ chứng cứ kết luận đó là TOTP không?

**Đáp:** Không. Cần biết mã được **tính bằng K và time-step** hay chỉ là random code server đã lưu để tra cứu. Việc có sáu chữ số và TTL 30 giây không chứng minh TOTP.

**Câu 2:** TOTP có dùng lại được trong cùng 30 giây không?

**Đáp:** Nếu verifier chỉ kiểm tra HMAC/time-window mà không nhớ **step đã nhận**, cùng mã có thể được chấp nhận lại. Thiết kế bảo mật cần chống replay rõ ràng.

**Câu 3:** Magic link dùng một lần có chắc là MFA không?

**Đáp:** Không. Có thể là **passwordless single-factor** dựa vào quyền truy cập mailbox. Để gọi MFA cần xác định yếu tố độc lập được kiểm tra theo policy.

**Câu 4:** Spring `oneTimeTokenLogin()` có đọc seed Base32 trong Google Authenticator không?

**Đáp:** Không. DSL cấu hình **server-issued OTT**. Muốn TOTP cần enrollment, tạo/giữ secret, verifier RFC 6238, replay store, rate limit và tích hợp vào luồng authentication phù hợp (hoặc dùng giải pháp IdP/MFA chuyên dụng).

**Câu 5:** Một token OTT được `consume` thành công rồi cần xóa khỏi DB không?

**Đáp:** Điều bắt buộc là nó **không thể được xác thực lại**. Xóa/đánh dấu đã dùng trong một thao tác nguyên tử là cách thiết kế tương ứng; cách lưu vật lý phụ thuộc `OneTimeTokenService` implementation.

**Câu 6:** HOTP và TOTP đều có chữ “one-time”, vậy server có thể bỏ trạng thái replay không?

**Đáp:** Không. HOTP phải cập nhật counter tiếp theo; TOTP phải ngăn tái sử dụng step đã chấp nhận. Một mã ngắn đúng công thức chưa đủ để đạt tính one-time ở tầng xác minh.

## 17. Tóm tắt

OTT, HOTP và TOTP đều có thể giúp người dùng xác thực bằng giá trị ngắn hạn hoặc dùng một lần, nhưng chúng **khác nhau ở nguồn sinh giá trị, trạng thái cần lưu, cách phát và cách xác minh**:

- **OTT (Spring Security 6.4+):** server sinh token, lưu và phát qua kênh ngoài luồng, sau đó **consume một lần**. Cơ chế hợp với magic link/passwordless login; phải bảo vệ email delivery, TLS, token store, account status, CSRF và session.
- **HOTP (RFC 4226):** cả authenticator và server có `K`, dùng **counter C**, server tăng counter sau thành công, hỗ trợ resync có kiểm soát.
- **TOTP (RFC 6238):** cả hai có `K`, dùng **time-step T**, server cho phép clock skew nhỏ và phải ngăn replay trong cửa sổ còn hiệu lực.

Không chọn giải pháp bằng nhãn “OTP/OTT” trong UI. Hãy xác định mục tiêu (passwordless, MFA, recovery), mức rủi ro, phương tiện người dùng sở hữu, khả năng bảo vệ secret, yêu cầu chống replay và kiến trúc nhiều instance, rồi chọn công cụ phù hợp.

## 18. Tài liệu chính thức

- Spring Security 6.5 — One-Time Token Login (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html
- Spring Security 7.1 — One-Time Token Login: https://docs.spring.io/spring-security/reference/7.1/servlet/authentication/onetimetoken.html
- Spring Security 6.5 API — `OneTimeTokenService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html
- Spring Security 6.5 API — `InMemoryOneTimeTokenService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/InMemoryOneTimeTokenService.html
- Spring Security 6.5 API — `OneTimeTokenGenerationSuccessHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/ott/OneTimeTokenGenerationSuccessHandler.html
- RFC 4226 — HOTP: https://www.rfc-editor.org/rfc/rfc4226.html
- RFC 6238 — TOTP: https://www.rfc-editor.org/rfc/rfc6238.html
