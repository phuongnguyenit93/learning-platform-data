# Vòng đời token dùng một lần: phát hành, gửi, hết hạn và chống phát lại trong Spring Security Servlet

## 1. Vấn đề: vì sao token "hết hạn sau 10 phút" vẫn chưa đủ?

Một ứng dụng Spring Boot có chức năng **quên mật khẩu**, **xác minh email**, **đăng nhập bằng liên kết một lần (magic link)** hoặc **xác nhận một thao tác nhạy cảm**. Hệ thống phát token cho người dùng, gửi qua một kênh được chỉ định và cho phép người nhận dùng token đó để hoàn tất một hành động.

Một sai lầm phổ biến là chỉ kiểm tra `expiresAt > now`. Nếu token còn hạn 10 phút và server không ghi nhận việc sử dụng, **bất cứ ai giữ bản sao token vẫn có thể gọi lại trong 10 phút**. Thời hạn sống (**TTL**) và tính dùng một lần (**single-use**) là hai thuộc tính độc lập.

Trong Spring Security Servlet, cần thiết kế trọn vẹn vòng đời:

1. **Phát hành:** sinh token đủ entropy bằng bộ sinh ngẫu nhiên mật mã, gắn với một người dùng, một mục đích, một thời hạn và ngữ cảnh cần thiết.
2. **Lưu:** chỉ lưu bản đại diện không khôi phục lại token gốc (digest/HMAC) cùng metadata; giới hạn số token có hiệu lực và quản lý thu hồi.
3. **Gửi:** chuyển token qua kênh ngoài luồng hoặc UI được kiểm soát; không đưa vào log, analytics hay response công khai ngoài ý muốn.
4. **Xác minh và tiêu thụ:** kiểm tra token tồn tại, đúng mục đích, đúng người/ngữ cảnh khi cần, chưa hết hạn và chưa tiêu thụ; **đánh dấu sử dụng bằng thao tác nguyên tử** để chỉ một request chiến thắng.
5. **Hết hạn, thu hồi, dọn dẹp:** từ chối token hết hạn, vô hiệu hóa token sau sử dụng hoặc sau sự kiện bảo mật, xóa dữ liệu quá hạn theo retention.
6. **Quan sát và thử nghiệm:** xác minh replay, double-click, race condition, token giả, expiration boundary, lỗi gửi và lỗi dịch vụ.

Bài học dùng **password reset** làm ví dụ chính vì nó minh họa rõ sự khác biệt giữa xác thực quyền kiểm soát kênh liên hệ và việc cập nhật trạng thái tài khoản. Các nguyên tắc cũng áp dụng cho email verification, invitation, magic link, step-up challenge, nhưng **hành động sau khi tiêu thụ** và chính sách phân quyền của từng loại phải được thiết kế riêng.

## 2. Những loại token dễ nhầm

| Loại | Mục đích | Một lần hay tái sử dụng? | Điều kiện an toàn |
| --- | --- | --- | --- |
| **Password reset token** | Xác nhận người nhận được phép đặt lại mật khẩu của tài khoản liên quan | **Một lần**, ngắn hạn | Đúng purpose, hết hạn và tiêu thụ nguyên tử, chống đoán |
| **Email verification token** | Xác minh quyền truy cập địa chỉ email | Thường **một lần** | Gắn user/email version; vô hiệu hóa khi email đổi |
| **Magic-link login token** | Đăng nhập thông qua kênh gửi link | **Một lần** | Xác minh, tiêu thụ rồi tạo phiên an toàn; chống URL leak |
| **One-time password (OTP) 6 chữ số** | Thử thách ngắn hạn, có thể dùng MFA nếu thiết kế phù hợp | Một lần theo challenge/time step | Giới hạn lần thử, rate limit, chống replay; entropy thấp |
| **CSRF token** | Xác nhận request thay đổi trạng thái trong bối cảnh browser session | **Không mặc định dùng một lần** | Binding với phiên/handler của Spring Security |
| **OAuth2 access token** | Gọi resource API trong phạm vi được cấp quyền | Thường có thể sử dụng đến hạn/thu hồi | Kiểm chữ ký/issuer/audience/scope hoặc introspection |
| **JWT chứa `exp` và `jti`** | Token tự mô tả, có thời hạn và ID | **Không tự dùng một lần** | Muốn single-use phải có state theo `jti` để tiêu thụ |

**Không dùng access token hoặc JWT chỉ có `exp` như một token một lần mà không có trạng thái phía server.** Việc chứng thực chữ ký và `exp` chỉ nói token hợp lệ tại thời điểm đó; chúng không chứng minh token chưa từng được sử dụng. Với JWT dùng một lần vẫn phải lưu/đối chiếu `jti` (hoặc cơ chế tương đương) và áp dụng cập nhật nguyên tử.

MFA TOTP khác password reset link: TOTP dựa trên một mã ngắn thay đổi theo time step, nên chính sách chống replay, cửa sổ đồng hồ và giới hạn lần thử cần thiết kế riêng. Không thay một hệ thống MFA bằng gửi email password-reset token mà mặc định coi email là yếu tố xác thực mạnh.

## 3. Máy trạng thái của một token dùng một lần

Một token có thể có trạng thái logic như sau:

~~~text
                     request issue
                          |
                          v
                       ISSUED
                          |
               +----------+----------+
               |                     |
               v                     v
            DELIVERED           DELIVERY_FAILED
               |                 (cần quy tắc retry)
               |
          Presented for use
               |
         Validate atomically
               |
       +-------+-------+----------------+
       |               |                |
       v               v                v
    CONSUMED         EXPIRED          REVOKED
       |               |                |
       +---------------+----------------+
                       |
                 REJECT all reuse
~~~

`DELIVERED` là trạng thái vận chuyển riêng; **không** đồng nghĩa token đã được người dùng sử dụng. Với email/SMS, gửi thành công đến provider chỉ là đã nhận yêu cầu gửi, không đảm bảo người nhận đã đọc. Có thể thiết kế data model có `deliveryStatus` riêng thay vì nhét tất cả vào một cột status duy nhất.

Bất biến an toàn (**invariants**) của phần xác minh:

- Token không được đoán được từ tài khoản, thời gian, sequence ID, email hay `Math.random()`.
- Token chỉ có hiệu lực cho đúng **purpose** và tài khoản đã lưu khi phát hành.
- `now < expiresAt`; **đúng tại `expiresAt` thì hết hạn**.
- `consumedAt IS NULL` và `revokedAt IS NULL` là điều kiện bắt buộc để sử dụng.
- Với cùng token, **không quá một request được phép thay đổi trạng thái**.
- Khi token thất bại hoặc đã hết hạn, response và log không được lộ token gốc.

Có thể có nhiều token được phát hành cho một người dùng nếu thiết kế cho phép. Nếu chính sách chỉ cho **một token đang hoạt động trên mỗi user + purpose**, lần phát hành mới phải thu hồi bản trước **trong giao dịch** hoặc sử dụng generation/version để làm token cũ không còn hiệu lực. Không mặc định một `ConcurrentHashMap` ở một máy chủ đại diện cho trạng thái của mọi instance trong hệ thống phân tán.

## 4. Phát hành: SecureRandom, entropy và token format

Đối với **link token dài**, lựa chọn đơn giản trong Java 17 là 32 byte (256 bit) từ `java.security.SecureRandom`, mã hóa **Base64 URL-safe** không padding. 32 byte thường tạo ra chuỗi 43 ký tự chỉ gồm chữ, số, dấu `-` và `_`, phù hợp gửi qua URL hoặc form.

~~~java
import java.security.SecureRandom;
import java.util.Base64;

SecureRandom random = new SecureRandom();
byte[] bytes = new byte[32];
random.nextBytes(bytes);

String rawToken = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(bytes);

// Không log hoặc lưu rawToken lâu dài.
~~~

Đây là **mảnh Java**, dùng trong service chứ chưa phải file độc lập. Một giá trị cụ thể không thể dự đoán, vì vậy không có stdout cố định để tài liệu có thể liệt kê. Không tạo token bằng `UUID.randomUUID().toString()` nếu quy ước yêu cầu 256-bit entropy, càng không dùng `System.currentTimeMillis()`, username hoặc các giá trị đoán được.

**Hash trước khi lưu:** nếu token có entropy cao 256 bit, lưu `SHA-256(rawToken)` thay cho raw token là phương án hữu ích. Nếu database bị lộ, kẻ tấn công không có raw token để dùng trực tiếp. Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

static String sha256(String rawToken) {
    try {
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(rawToken.getBytes(StandardCharsets.UTF_8));
        return HexFormat.of().formatHex(hash);
    } catch (NoSuchAlgorithmException e) {
        throw new IllegalStateException("SHA-256 unavailable", e);
    }
}
~~~

Dùng `token_digest` làm khóa tra cứu; đối chiếu trên cùng digest mà ứng dụng tính từ input. Với **OTP 6 chữ số**, SHA-256 không đủ chống brute-force offline nếu database lộ vì không gian tìm kiếm quá nhỏ; cần thiết kế khác (ví dụ HMAC có khóa bí mật được bảo vệ riêng, attempt counter, rate limit và khóa thử thách). Không dùng chậm hash mật khẩu như BCrypt cho token 256 bit chỉ theo thói quen; mục tiêu và entropy khác nhau.

## 5. Gắn token với purpose và đối tượng đích

Một token nên được quản lý bằng bản ghi logic:

~~~text
one_time_token
    id              UUID hoặc khóa DB nội bộ
    token_digest    SHA-256 của raw token, UNIQUE
    account_id      Tài khoản được gắn tại lúc issue
    purpose         PASSWORD_RESET | VERIFY_EMAIL | INVITE | ...
    created_at      Thời điểm phát hành
    expires_at      Hạn chót (UTC/Instant)
    consumed_at     null hoặc thời điểm đã dùng
    revoked_at      null hoặc thời điểm thu hồi
    delivery_status Trạng thái gửi riêng nếu cần
~~~

Khi hoàn tất password reset, **không nhận `accountId` hoặc `email` từ client rồi dùng token để cho phép đổi password tài khoản đó**. Phải tìm **accountId gắn sẵn trong bản ghi token**. Nếu backend nhận `token=aliceToken` và `email=bob@example.org`, thao tác không được phép đổi mật khẩu của Bob.

Tương tự, token xác minh địa chỉ email cần gắn với **email cụ thể đang được xác minh** (và phiên bản email khi có thể thay đổi), thay vì chỉ gắn userId rồi chấp nhận một email khác. Token mời tham gia workspace cần gắn workspace, role được duyệt và người được mời; token xác nhận chuyển tiền cần gắn giao dịch/giá trị đã phê duyệt hoặc yêu cầu bước xác thực mạnh hơn.

**Token phải bị giới hạn quyền sử dụng.** Không dùng một raw token chung cho cả xác minh email, reset password và đăng nhập, vì cách này tạo đường đổi purpose có nguy cơ nâng quyền.

## 6. Gửi token: bảo mật kênh vận chuyển và chống lộ

Kênh gửi có thể là email, SMS, push notification hoặc ứng dụng xác thực. Mỗi loại có độ tin cậy và rủi ro riêng. Với password reset qua email:

1. Người dùng gọi endpoint yêu cầu đặt lại mật khẩu. Server **luôn trả thông báo chung** kiểu “Nếu tài khoản tồn tại, hướng dẫn sẽ được gửi”, không trả `404` cho email lạ và `200` chỉ với email có thật.
2. Server sinh token **chỉ cho account đủ điều kiện**, lưu digest + TTL, rồi đưa raw token đến dịch vụ gửi email qua interface nội bộ.
3. Email chứa link tới **origin HTTPS cố định được cấu hình** (không lấy origin từ header `Host` tùy ý), ví dụ `https://app.example.org/reset?token=...`.
4. GET trang reset chỉ **hiển thị form**, không tiêu thụ token; yêu cầu hoàn tất sử dụng POST. Đây là điểm quan trọng vì email security scanners, link-preview bots hoặc browser prefetch có thể mở GET trước người dùng.
5. Khi hoàn tất, form gửi token + mật khẩu mới qua HTTPS. Server xác minh và tiêu thụ token **một lần** trước khi áp dụng thay đổi.

**Giảm rò rỉ token trong URL:** URL query có thể xuất hiện trong browser history, access log, reverse proxy log, analytics, Referer hoặc screenshot. Trang nhận link nên dùng `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, không tải bên thứ ba không cần thiết; sau khi lấy token để đưa vào form, có thể dùng `history.replaceState` để bỏ query khỏi address bar. Không ghi raw token vào URL của liên kết khác, không gửi nó tới analytics. URL trong email phải dùng host cố định được phép, tránh **Host Header Poisoning**.

Kênh email không phải giấy phép bỏ mọi kiểm tra khác. Trước khi cho phép đặt lại mật khẩu của tài khoản có đặc quyền cao, cân nhắc MFA/recovery policy, phát cảnh báo bảo mật và vô hiệu hóa phiên/cookie/remember-me theo mức rủi ro. Với magic-link login, việc tạo phiên mới cần thêm **session fixation protection**, cookie flags, CSRF/session policy và quy trình xác thực phù hợp.

**Không đưa raw token vào response của endpoint yêu cầu** trong production. Ví dụ chạy ở phần sau dùng một `TokenSender` giả để không phải có SMTP; unit test dùng sender ghi lại token **chỉ trong bộ nhớ test**. Ứng dụng demo vì vậy chứng minh logic nhưng không tự gửi mail thật.

## 7. Tiêu thụ phải nguyên tử: chống double-click và race condition

Một anti-pattern:

~~~java
// SAI: Hai request có thể cùng đọc "unused" trước khi update.
TokenRow row = repository.findByDigest(digest);
if (row != null && !row.isUsed() && row.getExpiresAt().isAfter(now)) {
    resetPassword(row.getAccountId(), newPassword);
    repository.markUsed(digest);
}
~~~

Giữa `findByDigest` và `markUsed`, hai request song song có thể đều thấy token chưa dùng rồi cùng thực hiện nghiệp vụ. Một mutex ở JVM hiện tại không bảo vệ đủ nếu có **nhiều instance**.

Trong cơ sở dữ liệu hỗ trợ cập nhật có điều kiện, dùng **một UPDATE nguyên tử** và kiểm tra số hàng bị thay đổi. Ví dụ với **PostgreSQL** (minh họa dùng bind parameters, `RETURNING` là cú pháp PostgreSQL):

~~~sql
BEGIN;

UPDATE one_time_token
   SET consumed_at = CURRENT_TIMESTAMP
 WHERE token_digest = :digest
   AND purpose = 'PASSWORD_RESET'
   AND consumed_at IS NULL
   AND revoked_at IS NULL
   AND expires_at > CURRENT_TIMESTAMP
RETURNING account_id;

-- Chỉ tiếp tục nếu UPDATE RETURNING trả đúng 1 account_id.
-- UPDATE mật khẩu tài khoản này trong cùng transaction nếu hệ thống hỗ trợ.
-- Nếu không có hàng: rollback hoặc kết thúc thất bại chung.

COMMIT;
~~~

Nếu hai request dùng cùng digest, chỉ **một request** được cập nhật `consumed_at` từ NULL sang timestamp. Bản ghi thứ hai sau khi chờ lock sẽ không còn thỏa điều kiện. Với nghiệp vụ có thể cùng transaction (token và password ở cùng database), hãy đặt **consume + change password trong một transaction** để không có trạng thái “token đã tiêu thụ nhưng mật khẩu chưa đổi” do lỗi giữa chừng. Nếu tác động diễn ra qua hệ thống ngoài, dùng state machine/outbox/idempotency được thiết kế rõ, tránh gọi side effect hai lần.

Trong một **demo một JVM**, có thể đạt tính nguyên tử *trong cùng process* bằng `ConcurrentHashMap.compute(key, ...)`; ví dụ đầy đủ bên dưới dùng cách này để tập trung vào ý tưởng, đồng thời nói rõ phải thay bằng DB transaction khi triển khai nhiều instance.

**Tiêu thụ trước hay sau tác động?** Không có công thức chung cho mọi side effect; yêu cầu quan trọng là hai bước phải có **ngữ nghĩa giao dịch nhất quán**. Với password reset lưu cùng database, transaction là lựa chọn tự nhiên. Với việc gửi email thông báo hoặc gọi downstream service, cần xác định idempotency và cách hồi phục khi nửa chừng thất bại.

## 8. Mẫu đầy đủ: Java 17, Spring Boot 3.3.5, Spring Security Servlet

Ta xây ví dụ password reset gồm:

- `POST /password-reset/request`: nhận email và **luôn trả 202** với thông báo chung; nếu có tài khoản demo, sinh token 256-bit và gọi `TokenSender`.
- `POST /password-reset/complete`: nhận raw token và mật khẩu mới; xác minh TTL, purpose, unused bằng tiêu thụ nguyên tử; cập nhật BCrypt password hash; thành công trả **204**, token sai/hết hạn/đã dùng trả **400**.
- `GET /csrf`: cấp CSRF token để client browser hoặc lệnh thử HTTP gửi trong header. Các POST **vẫn chịu CsrfFilter**, kể cả khi endpoint `permitAll()`.
- `MemoryTokenStore`: lưu **digest**, chặn replay bằng `ConcurrentHashMap.compute`; **không** dùng làm storage production.
- `TokenSender` mặc định là **no-op** để mã chạy không cần mail server và không làm lộ raw token qua log. Test thay bằng capturing sender.

Cấu trúc file:

~~~text
one-time-reset-demo/
  pom.xml
  src/main/java/example/onetime/OneTimeResetApplication.java
  src/test/java/example/onetime/ResetServiceTests.java
  src/test/java/example/onetime/ResetHttpTests.java
~~~

### 8.1. Maven dependencies

**pom.xml:**

~~~xml
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
    <groupId>example</groupId>
    <artifactId>one-time-reset-demo</artifactId>
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
~~~

### 8.2. Ứng dụng và logic token

**src/main/java/example/onetime/OneTimeResetApplication.java:**

~~~java
package example.onetime;

import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OneTimeResetApplication {

    public static void main(String[] args) {
        SpringApplication.run(OneTimeResetApplication.class, args);
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DemoAccounts demoAccounts(PasswordEncoder encoder) {
        return new DemoAccounts(encoder);
    }

    @Bean
    MemoryTokenStore memoryTokenStore() {
        return new MemoryTokenStore();
    }

    @Bean
    TokenSender tokenSender() {
        // Demo không vận chuyển token ra ngoài; unit test dùng
        // CapturingSender. Production thay bằng mail sender riêng.
        return (email, rawToken) -> { };
    }

    @Bean
    ResetService resetService(
            DemoAccounts accounts,
            MemoryTokenStore tokens,
            TokenSender sender,
            PasswordEncoder encoder,
            Clock clock) {
        return new ResetService(accounts, tokens, sender, encoder, clock);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/csrf", "/password-reset/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class CsrfController {
        @GetMapping("/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            CsrfToken token = (CsrfToken) request.getAttribute(
                    CsrfToken.class.getName());
            return Map.of(
                    "headerName", token.getHeaderName(),
                    "token", token.getToken());
        }
    }

    @RestController
    @RequestMapping("/password-reset")
    static class ResetController {
        private final ResetService service;

        ResetController(ResetService service) {
            this.service = service;
        }

        record ResetRequest(String email) {}
        record CompleteRequest(String token, String newPassword) {}

        @PostMapping("/request")
        ResponseEntity<Map<String, String>> request(
                @RequestBody ResetRequest input) {

            service.requestReset(input.email());
            return ResponseEntity.accepted().body(Map.of(
                    "message",
                    "If the account exists, instructions will be sent"));
        }

        @PostMapping("/complete")
        ResponseEntity<Void> complete(
                @RequestBody CompleteRequest input) {
            boolean success = service.complete(
                    input.token(), input.newPassword());
            return success
                    ? ResponseEntity.noContent().build()
                    : ResponseEntity.badRequest().build();
        }
    }

    @FunctionalInterface
    interface TokenSender {
        void send(String destination, String rawToken);
    }

    // Directory giả lập một tài khoản; không phù hợp nhiều instance.
    static final class DemoAccounts {
        private final Account account;

        DemoAccounts(PasswordEncoder encoder) {
            account = new Account(
                    "account-1",
                    "alice@example.test",
                    new AtomicReference<>(
                            encoder.encode("initial-password-123")));
        }

        Optional<Account> findByEmail(String email) {
            if (email == null || email.length() > 254) {
                return Optional.empty();
            }
            return email.strip().equalsIgnoreCase(account.email())
                    ? Optional.of(account)
                    : Optional.empty();
        }

        void changePassword(String accountId, String newEncodedPassword) {
            if (!account.id().equals(accountId)) {
                throw new IllegalStateException("Account missing");
            }
            account.passwordHash().set(newEncodedPassword);
        }

        boolean passwordMatches(String rawPassword, PasswordEncoder encoder) {
            return encoder.matches(rawPassword, account.passwordHash().get());
        }
    }

    record Account(
            String id,
            String email,
            AtomicReference<String> passwordHash) {}

    record StoredGrant(
            String accountId,
            String purpose,
            Instant expiresAt,
            boolean consumed) {}

    static final class MemoryTokenStore {
        private final ConcurrentHashMap<String, StoredGrant> byDigest =
                new ConcurrentHashMap<>();

        void save(String digest, StoredGrant grant) {
            byDigest.put(digest, grant);
        }

        Optional<String> consume(
                String digest, String requiredPurpose, Instant now) {
            AtomicReference<String> acceptedAccount = new AtomicReference<>();

            // compute() là atomic per-key trong cùng JVM.
            byDigest.compute(digest, (key, grant) -> {
                if (grant == null || grant.consumed()
                        || !requiredPurpose.equals(grant.purpose())
                        || !now.isBefore(grant.expiresAt())) {
                    return grant; // giữ nguyên, không chấp nhận
                }
                acceptedAccount.set(grant.accountId());
                return new StoredGrant(
                        grant.accountId(),
                        grant.purpose(),
                        grant.expiresAt(),
                        true);
            });

            return Optional.ofNullable(acceptedAccount.get());
        }

        void removeExpired(Instant now) {
            byDigest.entrySet().removeIf(entry ->
                    !now.isBefore(entry.getValue().expiresAt()));
        }
    }

    static final class ResetService {
        static final Duration TTL = Duration.ofMinutes(10);
        private static final String PURPOSE = "PASSWORD_RESET";

        private final DemoAccounts accounts;
        private final MemoryTokenStore tokens;
        private final TokenSender sender;
        private final PasswordEncoder encoder;
        private final Clock clock;
        private final SecureRandom secureRandom = new SecureRandom();

        ResetService(
                DemoAccounts accounts,
                MemoryTokenStore tokens,
                TokenSender sender,
                PasswordEncoder encoder,
                Clock clock) {
            this.accounts = accounts;
            this.tokens = tokens;
            this.sender = sender;
            this.encoder = encoder;
            this.clock = clock;
        }

        void requestReset(String email) {
            Optional<Account> account = accounts.findByEmail(email);
            if (account.isEmpty()) {
                return; // Controller vẫn trả response chung
            }

            byte[] bytes = new byte[32];
            secureRandom.nextBytes(bytes);
            String rawToken = Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(bytes);

            String digest = sha256(rawToken);
            tokens.save(digest, new StoredGrant(
                    account.get().id(),
                    PURPOSE,
                    clock.instant().plus(TTL),
                    false));

            // Chỉ TokenSender được nhận rawToken.
            sender.send(account.get().email(), rawToken);
        }

        boolean complete(String rawToken, String newPassword) {
            if (rawToken == null
                    || !rawToken.matches("[A-Za-z0-9_-]{43}")
                    || newPassword == null
                    || newPassword.length() < 12
                    || newPassword.length() > 128) {
                return false;
            }

            String digest = sha256(rawToken);

            Optional<String> accountId = tokens.consume(
                    digest, PURPOSE, clock.instant());
            if (accountId.isEmpty()) {
                return false;
            }

            // Nếu bước này thất bại, demo vẫn đã tiêu thụ token:
            // yêu cầu token mới. Production nên đặt consume và
            // password change trong cùng DB transaction.
            accounts.changePassword(
                    accountId.get(), encoder.encode(newPassword));

            return true;
        }

        private static String sha256(String rawToken) {
            try {
                byte[] hash = MessageDigest.getInstance("SHA-256")
                        .digest(rawToken.getBytes(StandardCharsets.UTF_8));
                return HexFormat.of().formatHex(hash);
            } catch (NoSuchAlgorithmException e) {
                throw new IllegalStateException(
                        "SHA-256 unavailable", e);
            }
        }
    }
}
~~~

**Đọc mã đúng ngữ cảnh:**

- `SecureRandom` cấp 32 byte token mỗi lần; Base64URL tạo 43 ký tự. Chỉ **digest** được đưa vào `MemoryTokenStore`.
- `StoredGrant` gắn `accountId`, `purpose`, `expiresAt`, `consumed`; client không thể đổi mục tiêu tác động bằng cách gửi email khác.
- `MemoryTokenStore.consume` kiểm tra condition và đổi `consumed` trong một `ConcurrentHashMap.compute`, nên **trong một JVM** chỉ một request dùng token được phép. `removeExpired` minh họa cleanup, cần job định kỳ hoặc TTL persistence khi triển khai thật.
- `Clock` được inject để test expiration boundary không phụ thuộc `Thread.sleep`.
- `PasswordEncoder` dùng BCrypt; không lưu plaintext password. Demo account duy nhất có mật khẩu ban đầu chỉ để giải thích cách kiểm thử.
- `TokenSender` mặc định là no-op: server chạy nhưng **không gửi email**. Để kiểm trọn chu trình, unit test thay bằng fake sender ghi raw token vào RAM test. Production phải thay bằng SMTP/email API có secret, queue/outbox và quan sát trạng thái gửi.
- `permitAll()` chỉ bỏ yêu cầu login cho reset endpoint. **CSRF vẫn áp dụng với POST** vì cấu hình `csrf(Customizer.withDefaults())`; `spring-security-test` cho phép test bằng `with(csrf())`.

**Giới hạn có chủ ý của demo:** Map, trạng thái mật khẩu và token chỉ trong memory nên restart mất dữ liệu và không đồng bộ giữa nhiều instance. Không có rate limiter, email thật, persistent transaction hay thu hồi các phiên sau password reset. Đây là **mẫu giảng dạy cơ chế**, chưa phải hệ thống reset mật khẩu sẵn sàng cho production.

### 8.3. Chạy HTTP và quan sát CSRF

Ở thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Nhờ `/csrf`, một client mô phỏng browser có thể lấy token CSRF và cookie phiên. Các lệnh dưới đây dùng Bash/Git Bash, `curl` và Python 3:

~~~bash
# Lấy CSRF token gắn với cookie jar.
CSRF=$(curl -fsS -c demo-cookies.txt http://localhost:8080/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

# POST không CSRF token: Spring Security thường trả 403.
curl -i -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.test"}' \
  http://localhost:8080/password-reset/request

# POST cùng cookie và CSRF token: trả 202 với thông báo chung.
curl -i -b demo-cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.test"}' \
  http://localhost:8080/password-reset/request
~~~

Request email không tồn tại cũng có **response body/status như trên** nếu gửi JSON hợp lệ và CSRF hợp lệ. Bởi `TokenSender` của ứng dụng là no-op, bạn không thể lấy raw token qua HTTP response demo để tự gọi `/complete`; hãy chạy unit test bên dưới. Không bổ sung endpoint công khai `GET /last-token` để thuận tiện thử nghiệm vì nó có thể làm lộ mọi token đang hoạt động.

Việc trả 202 chung là bước chống **account enumeration**, nhưng production còn cần phân tích khác biệt về thời gian phản hồi, rate limit, chính sách gửi và hành vi với tài khoản disabled. Khi người dùng đã xác thực, có thể dùng cơ chế reauthentication/step-up thay vì email reset cho các thao tác đặc biệt nhạy cảm.

## 9. Unit test: phát hành, một lần, đúng hạn, hết hạn và chống race

Test service trực tiếp để không phụ thuộc SMTP hoặc LDAP/IdP. `CapturingSender` chỉ tồn tại trong test và giữ token gốc để thực hiện xác minh.

**src/test/java/example/onetime/ResetServiceTests.java:**

~~~java
package example.onetime;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;

class ResetServiceTests {

    private static final Instant START =
            Instant.parse("2026-01-01T00:00:00Z");
    private static final String EMAIL = "alice@example.test";

    static final class CapturingSender
            implements OneTimeResetApplication.TokenSender {
        String latest;

        @Override
        public void send(String destination, String rawToken) {
            latest = rawToken;
        }
    }

    record Fixture(
            OneTimeResetApplication.DemoAccounts accounts,
            OneTimeResetApplication.MemoryTokenStore tokens,
            CapturingSender sender,
            PasswordEncoder encoder,
            OneTimeResetApplication.ResetService service) {}

    private static Fixture fixture(Instant now) {
        PasswordEncoder encoder = new BCryptPasswordEncoder(4);
        var accounts =
                new OneTimeResetApplication.DemoAccounts(encoder);
        var tokens =
                new OneTimeResetApplication.MemoryTokenStore();
        var sender = new CapturingSender();
        var service = new OneTimeResetApplication.ResetService(
                accounts, tokens, sender, encoder,
                Clock.fixed(now, ZoneOffset.UTC));
        return new Fixture(accounts, tokens, sender, encoder, service);
    }

    @Test
    void newTokenCanResetExactlyOnce() {
        Fixture f = fixture(START);
        f.service().requestReset(EMAIL);

        String token = f.sender().latest;
        assertThat(token).matches("[A-Za-z0-9_-]{43}");

        assertThat(f.service().complete(
                token, "a-new-password-123")).isTrue();
        assertThat(f.accounts().passwordMatches(
                "a-new-password-123", f.encoder())).isTrue();

        // Cùng token không thể đặt lại mật khẩu lần thứ hai.
        assertThat(f.service().complete(
                token, "another-password-456")).isFalse();
        assertThat(f.accounts().passwordMatches(
                "a-new-password-123", f.encoder())).isTrue();
    }

    @Test
    void expiresExactlyAtDeadline() {
        Fixture f = fixture(START);
        f.service().requestReset(EMAIL);

        var serviceAtDeadline =
                new OneTimeResetApplication.ResetService(
                        f.accounts(), f.tokens(), f.sender(), f.encoder(),
                        Clock.fixed(
                                START.plus(Duration.ofMinutes(10)),
                                ZoneOffset.UTC));

        assertThat(serviceAtDeadline.complete(
                f.sender().latest, "a-new-password-123")).isFalse();
    }

    @Test
    void unknownAddressDoesNotDeliverAnyToken() {
        Fixture f = fixture(START);
        f.service().requestReset("unknown@example.test");
        assertThat(f.sender().latest).isNull();
    }

    @Test
    void onlyOneConcurrentRequestCanConsumeTheToken()
            throws Exception {
        Fixture f = fixture(START);
        f.service().requestReset(EMAIL);
        String token = f.sender().latest;

        var executor = Executors.newFixedThreadPool(2);
        var start = new CountDownLatch(1);

        try {
            Future<Boolean> a = executor.submit(() -> {
                start.await();
                return f.service().complete(token, "new-password-111");
            });
            Future<Boolean> b = executor.submit(() -> {
                start.await();
                return f.service().complete(token, "new-password-222");
            });

            start.countDown();
            int successes = (a.get(5, TimeUnit.SECONDS) ? 1 : 0)
                    + (b.get(5, TimeUnit.SECONDS) ? 1 : 0);

            assertThat(successes).isEqualTo(1);
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Điều đáng chú ý là test concurrent không chỉ gọi `complete` hai lần tuần tự: hai thread chờ cùng `CountDownLatch`, rồi cùng tranh chấp một digest. `ConcurrentHashMap.compute` đảm bảo chỉ một nhận được tài khoản; test yêu cầu **đúng một** kết quả `true`. Với hệ thống đa instance, test phải chuyển thành integration test trên database thật và cơ chế claim token bằng giao dịch có điều kiện.

### 9.1. Test HTTP: permitAll vẫn phải qua CsrfFilter

**src/test/java/example/onetime/ResetHttpTests.java:**

~~~java
package example.onetime;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResetHttpTests {

    @Autowired
    MockMvc mvc;

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/password-reset/request")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"alice@example.test\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void existingAndUnknownEmailsHaveSameResponse()
            throws Exception {
        String existing = mvc.perform(
                post("/password-reset/request").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"alice@example.test\"}"))
                .andExpect(status().isAccepted())
                .andReturn().getResponse().getContentAsString();

        String unknown = mvc.perform(
                post("/password-reset/request").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"unknown@example.test\"}"))
                .andExpect(status().isAccepted())
                .andReturn().getResponse().getContentAsString();

        assertThat(existing).isEqualTo(unknown);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kỳ vọng test**, khi mã và dependency ở trên được dùng nguyên vẹn: service tests xác nhận raw token dài 43 ký tự, reset thành công một lần, replay thất bại, đúng ranh giới hết hạn không còn hợp lệ, email lạ không phát token, hai request song song chỉ một thành công. MVC tests xác nhận POST thiếu CSRF bị chặn và hai địa chỉ email có response như nhau. Test không xác nhận vận chuyển email thật, chứng chỉ HTTPS hay giao dịch PostgreSQL; cần kiểm riêng những tầng đó.

## 10. Từ demo in-memory đến triển khai database đáng tin cậy

Trong production, phần sau thường cần thay đổi:

### 10.1. Database và transaction

Tạo `token_digest` có unique index, gắn `account_id`, `purpose`, `expires_at`, `consumed_at`, `revoked_at`. Thực hiện kiểm tra điều kiện hạn và `consumed_at IS NULL` **trong UPDATE nguyên tử**, kiểm số hàng thành công, rồi cập nhật mật khẩu cùng transaction. Dùng clock nguồn nhất quán (ví dụ timestamp database cho điều kiện hết hạn trong câu SQL). Đặt các thao tác đã được xác minh cạnh nhau để tránh time-of-check/time-of-use.

Nếu cập nhật mật khẩu nằm ở hệ thống khác không tham gia cùng transaction, cần quy trình bù trừ hoặc state transition đáng tin cậy; không chỉ đánh dấu consumed rồi bỏ qua lỗi downstream. Luôn thiết kế idempotency cho side effect như gửi thông báo hoặc gọi payment/invitation service.

### 10.2. Giới hạn phát hành và chống đoán token

- Rate limit theo IP, tài khoản/email đã canonicalize, tenant và device signal phù hợp; đưa các tình huống abuse vào hệ thống phát hiện. Không dựa duy nhất vào rate limit theo IP vì shared IP/proxy.
- Chống spam email/SMS và gửi lặp; cân nhắc cooldown, quota và token đang hoạt động. Không khóa tài khoản nạn nhân chỉ vì kẻ khác liên tục bấm “quên mật khẩu”.
- Với token 256-bit ngẫu nhiên, việc đoán online là không thực tế khi entropy đúng, nhưng **endpoint vẫn cần rate limit và chống DoS**. Với OTP ngắn, cần giới hạn số lần thử trên từng challenge và tránh dùng lại trong time window.
- Không tiết lộ account existence qua status/body; để ý thời gian xử lý, nội dung email và phản hồi của hệ thống gửi.
- Không trả token từ endpoint request, không ghi token vào log, database cột raw, telemetry hoặc crash report.

### 10.3. Vô hiệu hóa khi thay đổi trạng thái

Sau password reset thành công, cân nhắc vô hiệu hóa các reset token khác của cùng account, xóa remembered devices/tokens, đổi session identifier hoặc thu hồi phiên đã mở theo yêu cầu bảo mật. Không nên mặc định phiên cũ tự mất hiệu lực chỉ vì BCrypt hash đã thay đổi: **session HTTP đang hoạt động có thể vẫn hợp lệ** nếu chưa bị invalidated.

Với email verification, khi email được đổi, token dùng xác minh email cũ phải mất hiệu lực. Với invitation, khi lời mời bị hủy hoặc role/workspace thay đổi, token trước đó không được giữ nguyên quyền. Các điều kiện phụ thuộc phải được lưu hoặc xác minh lại ngay lúc consume.

### 10.4. Retention và phân quyền dữ liệu

Digest cũng là dữ liệu nhạy cảm ở mức vận hành; hạn chế ai được đọc bảng token, bảo vệ backup, cleanup expired/consumed theo lịch và audit việc phát hành/tiêu thụ qua request ID thay vì raw token. Phân biệt log sự kiện (“issue requested”, “token consumed”, “expired/replayed”) với nội dung bí mật. Khi xử lý incident, không chia sẻ password reset token qua ticket/chat.

### 10.5. Tính khả dụng của kênh gửi

Một token được lưu nhưng không gửi đến người dùng cần chiến lược retry/timeout và khả năng phát lại **thông báo** an toàn; không được tự ý ghi raw token vào log để giúp support. Với mail queue/outbox, thiết kế sao cho raw token tồn tại càng ngắn càng tốt và tránh payload thô trong queue lâu dài nếu có lựa chọn khác. Chú ý SMTP bounce, email delayed delivery: TTL bắt đầu tại lúc **issue**, không mặc định từ thời điểm người nhận mở thư. Nếu TTL 10 phút và email đến sau 15 phút, token phải bị từ chối và người dùng cần xin mới.

## 11. Những trường hợp cần test thêm

| Tình huống | Kết quả đúng |
| --- | --- |
| Token đúng, chưa hết hạn, chưa dùng | Thành công một lần |
| Dùng cùng token lần hai, kể cả ngay sau lần đầu | Từ chối |
| Hai request song song cùng token | Tối đa một thành công |
| `now == expiresAt` hoặc muộn hơn | Từ chối |
| Token bị thay một ký tự | Từ chối |
| Token đúng nhưng purpose khác | Từ chối |
| Token hợp lệ của user A và client gửi `email=userB` | Không cập nhật user B; luôn dùng accountId trong grant |
| Token đã revoked | Từ chối |
| Đổi mật khẩu thành công rồi cố dùng reset token cũ khác | Theo policy, thu hồi/invalidate các token liên quan |
| Email không tồn tại | HTTP response chung; không gửi token |
| POST hoàn tất reset thiếu/sai CSRF trong web có session | Bị CsrfFilter xử lý theo cấu hình; kiểm với MockMvc |
| Mật khẩu mới không đạt policy | Từ chối **trước** khi tiêu thụ token để người dùng có thể sửa, hoặc định nghĩa rõ policy khác |
| DB/queue lỗi giữa consume và update | Không xuất hiện hành động lặp; rollback/recovery theo thiết kế transaction |
| Máy chủ chạy nhiều instance | Cần persistence/atomic claim chung, không tin lock từng JVM |
| GET reset link bị email scanner/prefetch mở trước | Không tiêu thụ token chỉ vì GET |
| Token trong URL bị lộ qua Referer/log | Có biện pháp giảm rò rỉ, token ngắn hạn và bị thu hồi khi sử dụng |

Test nên bao gồm failure path, không chỉ happy path. Các trường hợp “đã hết hạn nhưng vẫn được dùng” hoặc “double-click reset cập nhật hai lần” là lỗi **logic vòng đời**, không thể sửa bằng cách chỉ tăng entropy của token.

## 12. Phân tích các lỗi thường gặp

**Lỗi 1 — Kiểm TTL mà không lưu trạng thái đã dùng.** `expiresAt` không bảo vệ replay. Thêm bản ghi token/state và atomic consume.

**Lỗi 2 — Dùng JWT chứa `exp` và cho rằng `jti` tự chống replay.** `jti` chỉ là định danh; server phải lưu/claim nó với thao tác nguyên tử nếu thật sự cần single-use.

**Lỗi 3 — Chỉ viết `find unused` rồi `mark used`.** Hai request cạnh tranh cùng đi qua. Dùng UPDATE có điều kiện/transaction, hoặc `ConcurrentHashMap.compute` **chỉ trong demo một JVM**.

**Lỗi 4 — Trả raw token cho frontend ở bước “request token”.** Mọi người chỉ cần biết email nạn nhân sẽ tự lấy được token đặt lại. Chuyển qua kênh sở hữu đã được xác minh và trả thông báo chung.

**Lỗi 5 — Hash OTP 6 chữ số bằng SHA-256 rồi gọi là an toàn.** Không gian 1 triệu giá trị dễ brute-force offline nếu lộ database; dùng cơ chế chuyên biệt có secret/attempt limit và thời hạn phù hợp.

**Lỗi 6 — Token trong email chứa URL xây từ untrusted `Host`.** Attacker có thể lừa backend gửi link có domain do họ kiểm soát. Dùng **base URL cố định đã cấu hình**.

**Lỗi 7 — Người dùng bấm email link và GET đã đánh dấu token used.** Security scanner mở link trước làm người dùng không thể hoàn tất. GET hiển thị form/confirmation; chỉ POST hợp lệ mới consume.

**Lỗi 8 — Ghi token vào log hoặc analytics.** Token trong query string đặc biệt dễ lộ qua request log, Referer và browser history. Tối thiểu hóa nơi token đi qua, thiết lập referrer/cache policy và không log query bí mật.

**Lỗi 9 — Quên account binding.** Token của Alice bị dùng kèm email Bob để đổi mật khẩu Bob. Derive account từ grant server-side, không tin mục tiêu do client gửi.

**Lỗi 10 — Không kiểm mục đích.** Token `VERIFY_EMAIL` có thể qua endpoint `PASSWORD_RESET`. Mọi consume phải kiểm `purpose` đúng.

**Lỗi 11 — Đổi mật khẩu nhưng không thu hồi phiên cũ.** Session/cookie đã xác thực có thể tiếp tục hoạt động. Thiết kế session revocation riêng theo yêu cầu an toàn.

**Lỗi 12 — `permitAll()` được xem là tự bỏ CSRF.** Authorization và CSRF độc lập. Với Spring Security Servlet, anonymous POST vẫn có thể phải mang CSRF token; đừng tắt CSRF toàn ứng dụng chỉ vì curl bị 403.

**Lỗi 13 — Không có cleanup.** Bản ghi hết hạn và đã dùng tăng vô hạn; đặt retention, TTL index hoặc job cleanup. Nhưng cleanup không được biến token đã dùng thành hợp lệ trở lại.

**Lỗi 14 — Mọi request đều trả lỗi “expired”, “already used”, “unknown token” chi tiết.** Phản hồi quá cụ thể có thể cung cấp tín hiệu cho kẻ tấn công. Dùng thông báo chung cho client, lưu lý do phân loại ở log nội bộ không chứa raw token.

**Lỗi 15 — Token tồn tại trên nhiều application instance nhưng chỉ lock một instance.** Request khác instance vẫn có thể dùng lại. Atomic claim phải nằm ở shared store, DB transaction hoặc state service có tính nhất quán thích hợp.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Token còn 5 phút và được dùng thành công. Có được gửi tiếp cùng token không?  
**Không.** Single-use và TTL độc lập; sau khi consume phải từ chối ngay.

**Câu 2.** Dùng `Math.random()` cộng timestamp để sinh reset token có ổn không?  
**Không.** Dùng `SecureRandom` với đủ entropy, ví dụ 32 byte.

**Câu 3.** Có thể lưu `SHA-256(rawToken)` thay vì token gốc không?  
**Có**, khi raw token là chuỗi ngẫu nhiên entropy cao; server hash token client gửi rồi tra cứu/claim digest.

**Câu 4.** Cùng một `token_digest` có thể bị hai request hoàn tất đồng thời không?  
**Không nên.** Phải có atomic consume/conditional UPDATE, kiểm một lần thành công.

**Câu 5.** Tại thời điểm `now == expiresAt`, token còn hợp lệ không?  
**Không**, nếu quy tắc hiệu lực là `now.isBefore(expiresAt)`.

**Câu 6.** Sau khi reset mật khẩu, mọi session cũ tự hết hạn không?  
**Không mặc định.** Hash mật khẩu thay đổi không trực tiếp invalidates tất cả SecurityContext đã được lưu; cần chính sách thu hồi session/remember-me/token riêng.

**Câu 7.** Người dùng reset token được gửi qua email nhưng URL bị một mail scanner mở GET trước. Có nên tiêu thụ token ngay khi GET không?  
**Không.** Chỉ tiêu thụ khi người dùng gửi yêu cầu hoàn tất phù hợp (thường POST), tránh link preview làm token mất hiệu lực.

**Câu 8.** CSRF token và password reset token có giống nhau không?  
**Không.** CSRF token bảo vệ request trong bối cảnh browser/session; reset token là credential một lần, gắn với account/purpose/TTL và phải được tiêu thụ nguyên tử.

**Câu 9.** Token JSON Web Token có `exp` và `jti`; đã đảm bảo dùng một lần chưa?  
**Chưa.** Cần server-side consumed/revoked state gắn với `jti` hoặc tương đương.

**Câu 10.** Với hệ thống nhiều instance và PostgreSQL, lớp nào chịu trách nhiệm single-use?  
**Database claim/transaction có điều kiện**, không phải `synchronized` ở từng instance Java.

## 14. Checklist trước khi triển khai

- **Issue:** `SecureRandom` đủ entropy; chỉ phát khi policy cho phép; purpose, account, TTL, metadata liên quan được lưu đúng.
- **Store:** hash/HMAC theo entropy/threat model; unique digest; giới hạn truy cập DB; có expiry/consumed/revoked state và cleanup.
- **Deliver:** kênh phù hợp, TLS, không lộ raw token qua response/log/analytics/Host header; GET link không thực hiện side effect.
- **Verify:** kiểm format, purpose, account binding, expiry boundary, revoked, attempted/used state; rate limit và phản hồi không lộ chi tiết.
- **Consume:** thao tác nguyên tử tại shared store; cập nhật tác động trong transaction hoặc thiết kế recovery/idempotency.
- **After:** thu hồi token liên quan, cân nhắc hủy phiên cũ, thông báo người dùng về thay đổi bảo mật, giữ audit không chứa token.
- **Test:** success, expired, replay, double-submit, concurrent requests, delivery failure, multi-instance và CSRF; kiểm báo cáo không suy diễn rằng test unit chứng minh email/DB/TLS đã hoạt động.

**Ghi nhớ:** một token dùng một lần an toàn không chỉ cần **khó đoán** và **có hạn sử dụng**, mà còn phải có **phạm vi quyền rõ ràng, kênh gửi phù hợp, tiêu thụ nguyên tử và thu hồi có kiểm soát**. Trong Spring Security Servlet, cơ chế xác thực/phân quyền và CsrfFilter tiếp tục bảo vệ những request thật; việc phát hành/tiêu thụ reset token là nghiệp vụ riêng của ứng dụng cần thiết kế đủ cả vòng đời.
