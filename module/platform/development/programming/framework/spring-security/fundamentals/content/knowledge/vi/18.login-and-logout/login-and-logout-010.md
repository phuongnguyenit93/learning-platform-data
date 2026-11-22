# Xác thực lại trước thao tác nhạy cảm và khái niệm xác thực nhiều yếu tố (MFA)

## 1. Vì sao đăng nhập thành công vẫn có thể chưa đủ?

Một phiên đã đăng nhập chứng minh rằng ứng dụng từng xác thực người dùng, nhưng **không bảo đảm người đang sử dụng trình duyệt ở thời điểm hiện tại chính là chủ tài khoản**. Trình duyệt có thể bị bỏ quên ở máy dùng chung, cookie phiên có thể bị đánh cắp hoặc thiết bị đã thay đổi người sử dụng. Vì vậy, trước những thao tác gây hậu quả lớn, ứng dụng có thể cần yêu cầu người dùng **chứng minh lại danh tính**.

Ví dụ: một khách hàng đã đăng nhập từ 2 giờ trước và đang đọc lịch sử giao dịch. Khi họ yêu cầu đổi số điện thoại nhận OTP, tạo khóa API mới hoặc thay đổi tài khoản nhận tiền, máy chủ yêu cầu xác thực lại trước khi thực hiện. Người dùng có thể xác nhận bằng mật khẩu hiện tại, passkey hoặc một phương thức xác thực mạnh hơn tùy chính sách. Đây là một bước bảo vệ khác với việc chỉ kiểm tra `authenticated()`.

Sau bài học, bạn cần phân biệt được:

- **Authentication (xác thực):** Ai đang yêu cầu truy cập? Bằng chứng nào xác nhận danh tính?
- **Authorization (phân quyền):** Danh tính đó có quyền làm thao tác này hay không?
- **Reauthentication (xác thực lại):** Yêu cầu bằng chứng xác thực mới trong khi người dùng đã có phiên đăng nhập.
- **Multi-factor authentication – MFA (xác thực nhiều yếu tố):** Dùng bằng chứng thuộc ít nhất hai **nhóm yếu tố độc lập**; có thể xảy ra ở lúc đăng nhập hoặc lúc xác thực lại.
- **Step-up authentication:** Nâng mức bảo đảm khi thao tác hoặc rủi ro đòi hỏi; có thể yêu cầu yếu tố mạnh hơn, thêm yếu tố hoặc chứng minh lại gần thời điểm thao tác.

**Mấu chốt:** `hasRole("ADMIN")` nói về quyền; `authenticated()` nói về trạng thái xác thực; cả hai **không tự chứng minh** người dùng vừa nhập lại mật khẩu hay đã sử dụng MFA. `fullyAuthenticated()` của Spring Security còn phân biệt các kiểu remember-me, nhưng cũng **không đồng nghĩa** với “vừa xác thực vài phút trước”.

## 2. Khi nào cần xác thực lại?

Không nên yêu cầu người dùng nhập lại mật khẩu ở tất cả request. Hãy phân loại hành động theo hậu quả và dấu hiệu rủi ro.

| Tình huống | Mức độ gợi ý | Cách bảo vệ có thể dùng |
| --- | --- | --- |
| Đọc trang công khai | Thấp | Không cần đăng nhập |
| Đọc dữ liệu thông thường của mình | Bình thường | Phiên đăng nhập hợp lệ + quyền truy cập |
| Thay đổi địa chỉ email, mật khẩu, số điện thoại | Cao | Xác thực lại gần thời điểm thay đổi; cân nhắc MFA, thông báo thay đổi |
| Thêm/xóa thiết bị MFA, khóa bảo mật, mã dự phòng | Cao | Xác thực lại bằng phương thức đã đăng ký và được tin cậy; quy trình khôi phục riêng |
| Chuyển tiền, sửa người nhận, xem/tải khóa bí mật | Rất cao | Step-up mạnh, kiểm tra chi tiết giao dịch, giới hạn thời gian và số lần dùng |
| Đăng nhập từ thiết bị lạ, hành vi bất thường, vừa khôi phục tài khoản | Theo rủi ro | Thêm bước xác minh, giới hạn quyền hoặc yêu cầu đăng nhập mới |

Bảng là **ví dụ thiết kế**, không phải bộ thời hạn hoặc mức bảo đảm áp dụng chung cho mọi sản phẩm. Chính sách cụ thể phụ thuộc vào nguy cơ, nghĩa vụ pháp lý, UX và các phương thức xác thực có sẵn.

**Mốc phát sinh reauthentication** có thể dựa vào: hành động nhạy cảm, thời gian từ lần xác thực gần nhất, tăng rủi ro từ thiết bị/địa chỉ IP, thay đổi yếu tố đăng nhập, khôi phục tài khoản, thay đổi mật khẩu hoặc hệ thống phát hiện bất thường. Địa chỉ IP hay “thiết bị quen thuộc” chỉ là **tín hiệu rủi ro**, không được coi là một yếu tố xác thực độc lập.

### 2.1. Tính mới (freshness) và độ mạnh (assurance) là hai chiều khác nhau

Ví dụ:

1. Một người vừa nhập **mật khẩu** 20 giây trước: bằng chứng rất mới nhưng chỉ chứng minh yếu tố “điều biết”.
2. Một người đăng nhập bằng **mật khẩu + khóa bảo mật** 6 giờ trước: lần trước có MFA nhưng chưa chắc đủ mới cho giao dịch sắp thực hiện.
3. Một người vừa xác nhận **passkey có xác minh người dùng**: bằng chứng có thể vừa mới vừa có mức bảo đảm cao, phụ thuộc vào authenticator và kết quả xác minh.

Chính sách step-up thường kiểm tra **cả mức bảo đảm lẫn thời điểm chứng minh**. Không dùng riêng cookie phiên, vai trò người dùng, một boolean `mfaEnabled` hoặc việc từng bật MFA để suy ra lần xác thực hiện tại đạt yêu cầu.

## 3. MFA là gì và thế nào mới được gọi là “nhiều yếu tố”?

Ba nhóm chính thường dùng:

| Nhóm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Something you know** – điều bạn biết | Bí mật ghi nhớ | Mật khẩu, PIN dùng làm credential |
| **Something you have** – vật/phương tiện bạn sở hữu | Bằng chứng kiểm soát một authenticator | Security key FIDO2, ứng dụng tạo TOTP, thiết bị lưu private key |
| **Something you are** – đặc điểm sinh trắc | Đặc điểm sinh trắc của người dùng | Vân tay, khuôn mặt khi được kiểm tra bằng cơ chế đáng tin cậy |

**Hai mật khẩu khác nhau** hoặc **mật khẩu + câu hỏi bí mật** vẫn là hai bằng chứng thuộc nhóm “điều biết”, không tạo thành MFA đúng nghĩa. **Mật khẩu + TOTP từ ứng dụng xác thực** thường là hai yếu tố: biết mật khẩu và kiểm soát thiết bị/secret tạo OTP. **Passkey/WebAuthn được mở khóa bằng sinh trắc hoặc PIN ngay trên authenticator** có thể là authenticator nhiều yếu tố trong một lần xác thực; máy chủ cần xác minh kết quả WebAuthn, gồm yêu cầu `userVerification` theo chính sách, chứ không mặc nhiên suy đoán rằng mọi lần bấm passkey đều đạt cùng mức bảo đảm.

Một số tài liệu liệt kê thêm vị trí hoặc hành vi như tín hiệu xác minh. Trong thiết kế hệ thống, **vị trí IP hay đặc điểm hành vi thường là tín hiệu đánh giá rủi ro**, không được tự coi là một yếu tố MFA độc lập chỉ vì nó khác mật khẩu.

### 3.1. So sánh phương thức phổ biến

| Phương thức | Ưu điểm | Hạn chế cần nhớ |
| --- | --- | --- |
| Password + TOTP (mã thay đổi theo thời gian) | Phổ biến, không cần sóng di động | Có thể bị phishing/relay; phải chống đoán mã và tái sử dụng OTP |
| Password + SMS OTP | Dễ tiếp cận | Rủi ro SIM swap, chuyển hướng SMS, phishing và phụ thuộc nhà mạng |
| Password + email link/one-time token | Dễ triển khai | Phụ thuộc bảo mật tài khoản email; có thể không thực sự độc lập với kênh khôi phục |
| Password + FIDO2 security key | Chống phishing tốt khi xác minh origin/RP ID chính xác | Cần hỗ trợ thiết bị và quản lý khóa dự phòng |
| Passkey có user verification | Trải nghiệm thuận tiện, WebAuthn gắn với RP/origin, chống phishing | Phải đánh giá đồng bộ khóa, loại authenticator và chính sách bảo đảm |
| Push approval | Nhanh | Rủi ro “MFA fatigue” (ép bấm chấp thuận), cần challenge/number matching và giới hạn thông báo |
| Recovery code | Giúp khôi phục tài khoản khi mất thiết bị | Phải bảo vệ như credential, dùng một lần, không phải lý do bỏ qua toàn bộ quy trình phục hồi |

**OTP không đồng nghĩa với phishing-resistant authentication**: người dùng có thể bị lừa nhập mã vào website giả và kẻ tấn công chuyển tiếp mã ngay lập tức. WebAuthn/FIDO2 được thiết kế để gắn bằng chứng với website hợp lệ và ngăn kiểu lừa đảo đó khi triển khai đúng.

Lưu ý thuật ngữ: `TOTP/HOTP` là mã một lần tạo từ secret đã đăng ký, còn **One-Time Token Login (OTT)** của Spring Security là luồng tạo token đăng nhập và gửi tới người dùng (thường qua email/SMS). Chúng **không phải cùng một giao thức**; chỉ bật `oneTimeTokenLogin()` không tự tạo tích hợp ứng dụng xác thực TOTP.

## 4. Luồng xác thực lại an toàn cho một thao tác nhạy cảm

Giả sử người dùng muốn thay đổi khóa API. Luồng đề xuất:

1. **Kiểm tra đăng nhập và quyền hiện có.** Máy chủ vẫn kiểm tra chủ sở hữu tài khoản/nguồn lực, vai trò và chính sách truy cập.
2. **Xác định yêu cầu step-up.** Nếu thiếu bằng chứng đủ mới/đủ mạnh, trả hướng dẫn bắt đầu xác thực lại; không thực hiện thao tác.
3. **Tạo thử thách gắn với ngữ cảnh.** Ghi nhận tài khoản, session/transaction, loại thao tác, mục tiêu cần đổi, thời hạn và nonce/ID ngẫu nhiên phù hợp.
4. **Xác minh bằng chứng mới trên máy chủ.** Ví dụ người dùng nhập lại mật khẩu qua TLS hoặc hoàn tất một WebAuthn assertion/TOTP flow. Không tin biến `verified=true` gửi từ browser.
5. **Cấp bằng chứng ngắn hạn có ràng buộc.** Có thể lưu tại server trong session/challenge store; chỉ cấp sau khi verifier xác nhận hợp lệ. Không đưa password hay OTP vào cookie, JWT tự tạo từ browser hoặc log.
6. **Kiểm tra lại ngay tại endpoint thực thi.** Đúng tài khoản? Đúng thao tác, đối tượng, dữ liệu giao dịch? Chưa hết hạn? Chưa dùng? Còn quyền? Mọi check phải ở **máy chủ**, sát thời điểm thực hiện.
7. **Tiêu thụ bằng chứng và thực thi an toàn.** Với giao dịch thật, cần chặn đua tranh/double submit bằng thao tác nguyên tử ở tầng lưu trữ, có idempotency key và audit.
8. **Thông báo và theo dõi.** Gửi thông báo khi đổi yếu tố đăng nhập hoặc thay đổi bảo mật quan trọng; ghi sự kiện audit nhưng không ghi credentials.

Ví dụ quy tắc “bằng chứng reauthentication có hiệu lực **2 phút và chỉ dùng cho một lần đổi khóa API**” là một **lựa chọn minh họa**, không phải timeout mặc định của Spring Security hay NIST. Hệ thống thực tế cần đánh giá rủi ro và chính sách của mình.

~~~text
Client có session hợp lệ
    |
    v
POST /account/change-sensitive-setting
    |
    +-- Không đủ quyền? ----------> 403 / từ chối
    |
    +-- Chưa có bằng chứng mới? ---> Yêu cầu xác thực lại
    |                                    |
    |                              POST /account/reauthenticate
    |                                    |
    |                              Xác minh mật khẩu / yếu tố khác
    |                                    |
    |                              Lưu dấu xác nhận ngắn hạn
    |                                    |
    +<-----------------------------------+
    |
    v
Kiểm tra danh tính + thao tác + TTL + chưa sử dụng
    |
    +-- Không đạt? ---------------> 403 / thực hiện lại step-up
    |
    v
Tiêu thụ dấu xác nhận và xử lý nghiệp vụ
~~~

Để tránh **time-of-check/time-of-use (TOCTOU)** và tái sử dụng, thao tác có giá trị lớn phải kiểm tra/tiêu thụ proof nguyên tử với cập nhật giao dịch. Không nên tạo một trạng thái `isMfaVerified=true` vĩnh viễn trong profile người dùng rồi cho phép mọi hành động nhạy cảm mãi mãi.

## 5. Spring Security: vị trí đặt kiểm tra

Trong ứng dụng Servlet, `SecurityFilterChain` thường xử lý xác thực và phân quyền request. `SecurityContextHolder` lưu context của request hiện tại; `Authentication` cho biết principal, authorities, cách xác thực và các chi tiết khác. **Spring Security 6 không tự cấp một “mới xác thực trong 2 phút” cho mọi ứng dụng** chỉ vì người dùng đã đăng nhập. Chính sách freshness của nghiệp vụ cần được thực hiện có chủ đích.

Lớp bảo vệ nên gồm:

- **Security chain:** Chặn request chưa đăng nhập và áp dụng rule phân quyền. Ví dụ `.requestMatchers("/account/**").authenticated()`.
- **Bước xác thực lại:** Xác minh credential/second factor bằng verifier uy tín, có rate limit và sự kiện audit; lưu dấu xác nhận chỉ sau khi thành công.
- **Endpoint nhạy cảm:** Tự kiểm tra proof vừa cấp, scope, tuổi thọ và đối tượng. Phải bảo vệ cả API, batch action và endpoint thay thế; ẩn nút giao diện không phải kiểm soát an ninh.
- **Session và CSRF:** Web app cookie-based vẫn phải xử lý CSRF, session fixation, logout, idle timeout, TLS, `Secure`/`HttpOnly`/`SameSite`. Reauthentication không thay thế các lớp bảo vệ này.

Nếu ứng dụng là OAuth2/OIDC client, có thể dùng chính sách reauthentication/step-up của nhà cung cấp danh tính (IdP). Khi đó phải xác thực token và các claim `auth_time`, `acr`, `amr` theo hợp đồng đáng tin cậy; một giá trị yêu cầu `prompt=login` hoặc `max_age=0` chỉ có ý nghĩa nếu IdP thực thi và RP kiểm tra kết quả.

## 6. Ví dụ thực hành: xác thực lại bằng mật khẩu trong Servlet

Ví dụ này **minh họa reauthentication một yếu tố**, **chưa phải MFA**. Sau khi login bằng form, người dùng muốn gọi endpoint mô phỏng thay đổi thiết lập bảo mật. Máy chủ bắt buộc xác minh lại mật khẩu và chỉ cấp một proof trong session có tuổi thọ 2 phút, gắn với user và loại thao tác. Proof bị tiêu thụ ở lần dùng đầu tiên.

Ví dụ sử dụng **Java 17**, **Spring Boot 3.5.0** (Spring Security 6.x, Servlet) và dependencies Web + Security. Code của ví dụ chạy độc lập trong một ứng dụng demo; không cần tự viết trang login vì Spring Security có form login mặc định.

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>step-up-demo</artifactId>
  <version>1.0.0</version>
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
  </dependencies>
</project>
~~~

**`src/main/java/example/stepup/StepUpApplication.java`:**

~~~java
package example.stepup;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.io.Serializable;
import java.time.Duration;
import java.time.Instant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class StepUpApplication {
    public static void main(String[] args) {
        SpringApplication.run(StepUpApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authz -> authz
                .requestMatchers("/account/**").hasRole("USER")
                .anyRequest().permitAll())
            .formLogin(Customizer.withDefaults())
            // Giữ CSRF mặc định cho các POST sử dụng cookie.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails demo = User.withUsername("demo")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(demo);
    }
}

@RestController
@RequestMapping("/account")
class StepUpController {
    private static final String PROOF_KEY =
        StepUpController.class.getName() + ".proof";
    private static final String ACTION = "CHANGE_SENSITIVE_SETTING";
    private static final Duration LIFETIME = Duration.ofMinutes(2);

    private final UserDetailsService users;
    private final PasswordEncoder encoder;

    StepUpController(UserDetailsService users, PasswordEncoder encoder) {
        this.users = users;
        this.encoder = encoder;
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "Đã đăng nhập: " + authentication.getName();
    }

    @PostMapping("/reauthenticate")
    ResponseEntity<String> reauthenticate(
            Authentication authentication,
            @RequestParam String password,
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body("Không có phiên đăng nhập đang hoạt động");
        }

        // Xóa proof cũ kể cả khi xác thực lại thất bại.
        session.removeAttribute(PROOF_KEY);

        UserDetails user;
        try {
            user = users.loadUserByUsername(authentication.getName());
        } catch (UsernameNotFoundException ex) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body("Không thể xác thực lại");
        }

        boolean accountUsable = user.isEnabled()
            && user.isAccountNonLocked()
            && user.isAccountNonExpired()
            && user.isCredentialsNonExpired();
        if (!accountUsable || !encoder.matches(password, user.getPassword())) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body("Không thể xác thực lại");
        }

        // Dấu xác nhận phía server: không ghi mật khẩu vào session.
        session.setAttribute(PROOF_KEY,
            new Proof(authentication.getName(), ACTION, Instant.now()));
        return ResponseEntity.ok("Xác thực lại thành công");
    }

    @PostMapping("/change-sensitive-setting")
    ResponseEntity<String> changeSensitiveSetting(
            Authentication authentication,
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            return forbidden();
        }

        // Tiêu thụ một lần, đồng bộ trong phiên của demo một máy chủ.
        Object stored;
        synchronized (session) {
            stored = session.getAttribute(PROOF_KEY);
            session.removeAttribute(PROOF_KEY);
        }

        Instant now = Instant.now();
        if (!(stored instanceof Proof proof)
                || !proof.username().equals(authentication.getName())
                || !ACTION.equals(proof.action())
                || proof.issuedAt().isAfter(now)
                || Duration.between(proof.issuedAt(), now)
                    .compareTo(LIFETIME) > 0) {
            return forbidden();
        }

        // Chỉ minh họa kiểm soát truy cập, KHÔNG thay dữ liệu thật.
        return ResponseEntity.ok("Cho phép: thao tác mẫu đã được phê duyệt");
    }

    private ResponseEntity<String> forbidden() {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
            .body("Cần xác thực lại trước thao tác nhạy cảm");
    }

    private record Proof(
        String username, String action, Instant issuedAt
    ) implements Serializable {
        private static final long serialVersionUID = 1L;
    }
}
~~~

**Chạy mẫu** (Java 17 và Maven đã cài):

~~~bash
mvn spring-boot:run
~~~

Mở `http://localhost:8080/login`, đăng nhập `demo / demo123`. Sử dụng trình duyệt, Postman hoặc client có **cookie phiên và CSRF token hợp lệ** để gửi hai request POST. Với Spring Security CSRF mặc định, gọi `curl -X POST` mà không gửi token thường nhận **403 trước khi đi tới controller**; đó là hành vi bảo vệ đúng, không phải code reauthentication bị lỗi.

Thứ tự kiểm tra logic server:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Chưa đăng nhập, truy cập `/account/me` | Được đưa tới login |
| Đã đăng nhập nhưng POST `/account/change-sensitive-setting` chưa xác thực lại | 403, yêu cầu reauthentication |
| POST `/account/reauthenticate` với mật khẩu sai | 401, không cấp proof |
| POST `/account/reauthenticate` với mật khẩu đúng | 200, cấp proof trong session |
| Ngay sau đó POST `/account/change-sensitive-setting` | 200, hiển thị kết quả mô phỏng |
| Gọi lại endpoint nhạy cảm lần thứ hai, không xác thực lại | 403 vì proof đã dùng |
| Đợi hơn 2 phút sau reauthentication rồi mới gọi thao tác | 403 vì proof hết hạn |
| Đăng xuất làm vô hiệu session | Không còn proof hợp lệ |

**Giải thích:** Security chain chỉ bảo đảm đã login và có `ROLE_USER`. Controller chịu trách nhiệm **xác minh lại credential** và kiểm tra bằng chứng gần thời điểm thao tác. Ở mẫu này proof chỉ có trong một `HttpSession` và gắn đúng username/action. Mật khẩu được so với mật khẩu đã hash bởi `PasswordEncoder`, không lưu trực tiếp vào session.

**Giới hạn có chủ ý của demo:** dữ liệu người dùng nằm trong memory, password demo được cố định trong source, không có rate limit, audit, khóa tài khoản tự động, phân tán session, cơ chế xử lý cạnh tranh liên node, transaction ID hoặc triển khai thay đổi dữ liệu thật. Với hệ thống thật, xác minh lại qua `AuthenticationManager`/provider phù hợp để áp dụng chính sách đăng nhập và kiểm soát thử sai; lưu challenge trong kho dữ liệu dùng chung và tiêu thụ nguyên tử. Mã trên dạy **nguyên lý của reauthentication**, **không phải mẫu triển khai sản xuất hoặc MFA**.

## 7. Áp dụng MFA trực tiếp trong Spring Security 7 (Servlet)

Spring Security **7.0 trở lên** cung cấp các khả năng chuyên biệt cho MFA trên Servlet như `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication` và `AuthorizationManagerFactories.multiFactor()`. Các API này **không có trong Spring Security 6.x**: ví dụ Spring Boot 3.5.0 ở mục 6 không thể copy nguyên cấu hình dưới đây.

Spring Security 7 ghi nhận thông tin về **yếu tố thực sự được dùng** khi xác thực vào `Authentication` dưới dạng `FactorGrantedAuthority`, ví dụ:

- `FactorGrantedAuthority.PASSWORD_AUTHORITY`: yếu tố password;
- `FactorGrantedAuthority.OTT_AUTHORITY`: one-time token login;
- `FactorGrantedAuthority.WEBAUTHN_AUTHORITY`: WebAuthn.

Quy tắc MFA cần **hai phía**: yêu cầu đủ các factor authorities trong authorization và cấu hình các cơ chế xác thực **có thể cung cấp** những factors đó. Chỉ khai báo một chuỗi authority tự đặt tên hoặc một flag trong database không đủ chứng minh đã qua MFA.

Đoạn cấu hình bên dưới là **mảnh mã đặt trong ứng dụng Spring Security 7.0+**, minh họa chỉ yêu cầu password + OTT đối với `/account/security/**`. Nó **không phải ứng dụng độc lập**: ứng dụng phải có người dùng, cơ chế phát/gửi OTT an toàn và lưu trữ token phù hợp. Khi sử dụng, chọn cấu hình này **thay cho** security chain demo của mục 6, không tạo thêm một chain trùng matcher.

~~~java
package example.stepup;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
@EnableMultiFactorAuthentication(authorities = {})
class SelectiveMfaSecurity {
    @Bean
    SecurityFilterChain mfaChain(HttpSecurity http) throws Exception {
        var mfa = AuthorizationManagerFactories
            .<RequestAuthorizationContext>multiFactor()
            .requireFactors(
                FactorGrantedAuthority.PASSWORD_AUTHORITY,
                FactorGrantedAuthority.OTT_AUTHORITY)
            .build();

        return http
            .authorizeHttpRequests(authz -> authz
                .requestMatchers("/account/security/**")
                    .access(mfa.authenticated())
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

**Cần cấu hình thêm trước khi hoạt động thực tế:**

1. Kênh phát token OTT: Spring Security không biết địa chỉ email/SMS và cách truyền token của ứng dụng. Cần cung cấp `OneTimeTokenGenerationSuccessHandler` để gửi đúng người dùng, không phát lộ token trên log.
2. Kho token: ví dụ Spring Security mặc định có `InMemoryOneTimeTokenService`; khi chạy nhiều instance nên xem xét `JdbcOneTimeTokenService` hoặc backend phù hợp và chính sách hết hạn/tiêu thụ.
3. Tính độc lập của yếu tố: OTT nhận qua cùng một hộp thư có thể có mức bảo đảm không đủ cho nghiệp vụ rủi ro cao. Xem xét WebAuthn/passkey hoặc authenticator khác theo mục tiêu bảo mật.
4. Thời gian xác thực: việc đủ hai factor authorities chứng minh các cơ chế đã được dùng; nếu thao tác yêu cầu **xác thực lại ngay trước khi thực hiện**, phải áp dụng thêm giới hạn freshness hoặc `RequiredFactor`/policy phù hợp. Không đánh đồng MFA với freshness.

**Đặt MFA cho toàn bộ ứng dụng:** Spring Security 7 còn cho phép `@EnableMultiFactorAuthentication(authorities = { FactorGrantedAuthority.PASSWORD_AUTHORITY, FactorGrantedAuthority.OTT_AUTHORITY })` để bổ sung yêu cầu vào các authorization rule phù hợp. Với yêu cầu chỉ dành cho một số route, dùng cấu hình chọn lọc như trên để tránh cản trở mọi request.

**WebAuthn:** hỗ trợ passkey trong Spring Security yêu cầu module `spring-security-webauthn` và đăng ký credential đáng tin cậy với RP ID/origin chính xác. Đừng tự viết verifier WebAuthn bằng cách so sánh chuỗi “passkey” từ client.

**WebFlux:** ví dụ `HttpSecurity` và `SecurityFilterChain` trong mục này áp dụng cho Servlet. Ứng dụng reactive phải sử dụng `ServerHttpSecurity` và `SecurityWebFilterChain` cùng giải pháp MFA/step-up tương thích phiên bản; không trộn trực tiếp các API Servlet vào WebFlux.

## 8. Thiết kế đúng xác thực lại trong OAuth2/OIDC và SSO

Ở hệ thống SSO, ứng dụng thường không giữ mật khẩu của người dùng; việc yêu cầu ứng dụng RP thu lại mật khẩu IdP vào một form tự tạo là không phù hợp. Thay vào đó:

1. RP phát yêu cầu đăng nhập lại qua IdP bằng giao thức đã tích hợp. OIDC có thể dùng các tham số như `max_age`, `prompt=login` hoặc `acr_values` nếu IdP hỗ trợ.
2. IdP thực hiện lại xác thực hoặc step-up. Nếu có yêu cầu MFA, IdP phải dùng phương thức đáp ứng chính sách của tổ chức.
3. RP xác minh ID token/response và đọc các bằng chứng từ issuer đã tin cậy như `auth_time` (thời điểm xác thực), `acr` (authentication context class reference) và `amr` (authentication methods references) **nếu được IdP phát hành và có hợp đồng rõ ràng**.
4. RP so sánh mức bảo đảm và độ mới với yêu cầu của thao tác, gắn thành công của step-up vào đúng người dùng và giao dịch. Nếu claim vắng mặt hoặc không đạt thì từ chối thao tác, không tự chấp nhận theo yêu cầu gửi đi.

Không được kết luận “IdP chắc chắn đã xác thực lại” chỉ vì RP đã gắn `prompt=login` vào URL. Cần kiểm tra **kết quả đã được issuer ký/xác thực** và chính sách của IdP. Tương tự, `scope` hoặc access token tồn tại không đủ chứng minh rằng phiên user đã qua MFA gần đây.

Nếu sử dụng access token cho API, phải quyết định rõ nơi kiểm tra step-up: gateway, resource server, business service hoặc kết hợp. Đừng để endpoint trực tiếp bypass quyết định ở giao diện/gateway.

## 9. Enrollment, recovery và vòng đời các yếu tố MFA

MFA không kết thúc ở màn hình “nhập mã”. Vòng đời yếu tố xác thực thường gồm:

- **Đăng ký:** Người dùng đang có phiên tin cậy; trước khi gắn yếu tố mới cần xác thực lại và xác nhận quyền sở hữu authenticator. Với TOTP, secret/QR enrollment phải được truyền an toàn, không ghi log hoặc hiển thị lại tùy tiện; yêu cầu xác minh mã trước khi kích hoạt.
- **Sử dụng:** TOTP/OTP phải có hết hạn, giới hạn số lần thử, chống replay, xử lý chênh lệch đồng hồ giới hạn; push nên có xác nhận chủ động, chống spam approval. Với WebAuthn cần xác thực challenge, origin, RP ID, chữ ký và user verification theo yêu cầu.
- **Bổ sung/xóa:** Đổi/xóa factor là thao tác rất nhạy cảm; không cho phép một phiên có cookie bị đánh cắp tự tắt MFA. Có thông báo và audit khi thay đổi.
- **Mã khôi phục:** Tạo bằng CSPRNG, lưu dạng hash hoặc cấu trúc bảo vệ thích hợp, hiển thị một lần, dùng một lần, hạn chế yêu cầu và ghi nhận khi đã sử dụng. Không dùng recovery code như đường tắt âm thầm.
- **Mất authenticator:** Có quy trình khôi phục có độ bảo đảm tương xứng, trì hoãn hoặc kiểm tra bổ sung khi cần. Một câu hỏi bí mật yếu có thể làm vô hiệu toàn bộ giá trị của MFA.
- **Đăng xuất/thu hồi:** Thu hồi chứng cứ step-up gắn session hoặc transaction, xóa/revoke credential khi có thay đổi nghiêm trọng, giới hạn thời gian sống.

Nguyên tắc thực tế: **khâu dễ bị tấn công nhất thường là đăng ký lại yếu tố hoặc khôi phục tài khoản**. Phải xem MFA setup, reset, remove và backup như một phần của thiết kế xác thực, không xem là chức năng phụ.

## 10. Mối liên hệ giữa reauthentication, MFA và các biện pháp khác

| Biện pháp | Giải quyết | Không tự giải quyết |
| --- | --- | --- |
| Kiểm tra `authenticated()` | Request gắn với người dùng đã đăng nhập | Freshness, MFA, quyền riêng từng thao tác |
| `hasRole(...)` hoặc policy ABAC | User có quyền với route/tài nguyên | Session bị chiếm, reauthentication |
| Yêu cầu nhập lại mật khẩu | Chủ thể có thể chứng minh biết password gần đây | MFA, phishing resistance nếu chỉ dùng password |
| MFA | Bằng chứng từ nhiều nhóm yếu tố/credential đủ mạnh | Thời điểm xác thực, quyền tác vụ, mục tiêu giao dịch |
| Step-up theo giao dịch | Mức xác minh phù hợp hành động cụ thể | Cơ chế bảo vệ session/XSS/CSRF khác |
| CSRF token | Giảm nguy cơ yêu cầu thay đổi dữ liệu bị kích hoạt chéo từ browser | Session theft, phishing credentials |
| HTTPS + cookie flags | Bảo vệ vận chuyển/session ID trong các tình huống cụ thể | Quyết định quyền hoặc freshness |
| Logging/auditing | Truy vết sự kiện và điều tra | Chặn hành động trái phép nếu thiếu bước enforce |

Đặc biệt, **reauthentication không thay thế CSRF**. Nếu browser tự gửi session cookie tới một endpoint, vẫn phải bảo vệ các request thay đổi dữ liệu. **MFA không tự chữa XSS**: script độc hại chạy trong session hợp lệ có thể truy cập dữ liệu và thực hiện nhiều hành động tùy mô hình phòng thủ.

## 11. Lỗi triển khai thường gặp

**Lỗi 1 – Chỉ làm màn hình nhập mã ở frontend.** Người dùng có thể gọi API nhạy cảm trực tiếp. **Cách sửa:** kiểm tra proof/MFA policy ngay trên server trong endpoint thực thi, với tất cả đường vào tương đương.

**Lỗi 2 – Lưu `mfaVerified=true` vĩnh viễn trong user profile.** Nó chỉ nói rằng một điều kiện từng được đánh dấu, không cho biết phương thức hoặc thời điểm chứng minh. **Cách sửa:** lưu kết quả xác thực có issuer, method, thời điểm, session/action binding và TTL; không dùng boolean toàn cục thay proof.

**Lỗi 3 – Dùng mật khẩu + câu hỏi bí mật và gọi là 2FA.** Cùng là yếu tố “điều biết”. **Cách sửa:** dùng yếu tố độc lập, ưu tiên phishing-resistant authentication phù hợp.

**Lỗi 4 – Chỉ kiểm tra thời gian ở browser.** Người dùng có thể sửa đồng hồ hoặc request. **Cách sửa:** ghi và đánh giá thời gian bằng đồng hồ phía server; xử lý clock skew có giới hạn nếu xác minh token liên hệ nhiều hệ thống.

**Lỗi 5 – Chấp nhận lại OTP/magic link nhiều lần.** Attacker có thể replay credential. **Cách sửa:** token một lần, TTL ngắn, tiêu thụ nguyên tử, rate limit và chống enumeration.

**Lỗi 6 – Xác thực lại xong được làm mọi việc.** Bằng chứng dùng để xem dữ liệu không nên mặc nhiên hợp lệ khi rút tiền hoặc đổi thiết bị MFA. **Cách sửa:** gắn proof với action, tài khoản, mục tiêu hoặc transaction digest và TTL; tiêu thụ sau khi dùng.

**Lỗi 7 – Quên kiểm tra quyền sau reauthentication.** User thường có thể xác thực lại chính mình nhưng vẫn không được phép thực hiện thao tác của admin hoặc của user khác. **Cách sửa:** kết hợp authentication, authorization và step-up; kiểm tra owner tại tầng business.

**Lỗi 8 – Bỏ qua chống brute-force và thông báo thay đổi bảo mật.** Form “nhập lại mật khẩu” là một điểm thử credential mới. **Cách sửa:** rate limiting theo tài khoản/IP/rủi ro, audit an toàn, thông báo khi thay đổi yếu tố; không ghi password, OTP, recovery code, raw token vào logs.

**Lỗi 9 – Nhầm OTT Spring với TOTP authenticator.** OTT cần server tạo và gửi token; TOTP cần shared secret đã thiết lập và thuật toán tạo mã. **Cách sửa:** chọn đúng chuẩn và kiểm tra cách triển khai và độ độc lập của phương thức.

**Lỗi 10 – Cho phép reset MFA qua email yếu hơn hẳn MFA chính.** Attacker chỉ cần đánh cắp email là vượt qua bảo vệ. **Cách sửa:** xây dựng luồng recovery dựa trên mức rủi ro; xác thực đủ mạnh, có trì hoãn/kiểm soát bất thường và thông báo.

## 12. Checklist kiểm thử

Sau khi triển khai, thực hiện kiểm thử ở backend và với browser thật:

1. **Tài khoản chưa đăng nhập:** thao tác nhạy cảm không được thực hiện.
2. **Đã đăng nhập đúng quyền nhưng chưa step-up:** endpoint vẫn từ chối hoặc yêu cầu xác thực lại.
3. **Credential sai/OTP sai/hết hạn:** không tạo proof; rate limit hoạt động; không leak thông tin.
4. **Credential đúng và bước xác minh đạt:** chỉ proof cho đúng user và hành động được cấp; không cấp quyền quá rộng.
5. **Đổi user/session/transaction sau challenge:** proof cũ bị từ chối.
6. **Hết TTL:** proof bị từ chối, kể cả khi session đăng nhập vẫn hợp lệ.
7. **Replay/double submit:** proof không được thực thi hai giao dịch; kiểm thử cạnh tranh song song và đa node.
8. **Không có CSRF token khi dùng cookie authentication:** request thay đổi dữ liệu bị chặn.
9. **Thao tác qua API khác:** không có endpoint nào bỏ qua kiểm tra step-up/authorization.
10. **Logout, reset mật khẩu, xóa MFA, nghi ngờ account takeover:** proof đã cấp bị vô hiệu theo chính sách.
11. **MFA enrollment/recovery:** không có đường tắt làm vô hiệu cơ chế xác thực mạnh.
12. **Audit và riêng tư:** log chứa sự kiện và mã tương quan, không chứa mật khẩu, OTP, recovery codes hoặc cookie/session token.

Nên phân biệt **kiểm thử luồng chuẩn** với **kiểm thử tấn công**: dùng cookie của phiên khác, sửa transaction ID giữa challenge và commit, thử OTP cũ, gửi hai request đồng thời, sử dụng bypass URL, kiểm tra CSRF và đánh giá kết quả theo từng loại lỗi.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Một người có `ROLE_ADMIN`, đã đăng nhập hôm qua. Điều đó có đủ cho thao tác xuất toàn bộ khóa API không? **Không.** Quyền admin khác với việc xác minh danh tính đủ mới và đủ mạnh cho hành động nhạy cảm.

**Câu 2.** Nhập lại mật khẩu trước khi đổi email có tự biến ứng dụng thành MFA không? **Không.** Đây là reauthentication bằng cùng yếu tố password; MFA cần thêm bằng chứng thuộc nhóm độc lập (hoặc một authenticator nhiều yếu tố đáp ứng chính sách).

**Câu 3.** Password + TOTP đã giúp giảm rủi ro; liệu hai yếu tố đó chống phishing hoàn toàn chưa? **Chưa.** Mã có thể bị chuyển tiếp trên trang giả; WebAuthn/FIDO2 là lựa chọn chống phishing mạnh hơn khi triển khai đúng.

**Câu 4.** Nếu ứng dụng đã xác minh MFA lúc login, có thể bỏ mọi bước step-up về sau không? **Không chắc.** Hoạt động nhạy cảm có thể đòi hỏi freshness và ràng buộc theo giao dịch.

**Câu 5.** `oneTimeTokenLogin()` của Spring Security có phải TOTP dùng Google Authenticator không? **Không.** OTT là token dùng một lần mà ứng dụng tạo/gửi, khác với TOTP từ secret đã chia sẻ.

**Câu 6.** Vì sao proof reauthentication phải gắn với session/action và dùng một lần? **Để tránh việc một lần xác thực bị tái dùng cho hành động hoặc tài khoản khác**, giảm replay và hạn chế thời gian lợi dụng nếu session bị chiếm.

## 14. Tài liệu tham khảo

- [Spring Security – Multi-Factor Authentication, Servlet, Spring Security 7](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html)
- [Spring Security – One-Time Token Login](https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html)
- [Spring Security – Passkeys/WebAuthn](https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html)
- [Spring Security – SecurityContext và Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [OWASP Authentication Cheat Sheet – Reauthentication, MFA, Adaptive Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet – Reauthentication after risk events](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [NIST SP 800-63B – Digital Identity Guidelines (current edition)](https://pages.nist.gov/800-63-4/sp800-63b.html)
