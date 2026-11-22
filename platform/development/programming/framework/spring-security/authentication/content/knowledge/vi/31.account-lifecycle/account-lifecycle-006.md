# Thay đổi email, số điện thoại và dữ liệu khôi phục có xác thực lại

## 1. Vì sao đây là thao tác nhạy cảm trong vòng đời tài khoản?

Email, số điện thoại và dữ liệu khôi phục thường được dùng để nhận thông báo bảo mật, đặt lại mật khẩu, nhận mã xác minh hoặc khôi phục khi mất passkey/MFA. Vì vậy, thay đổi chúng không chỉ là cập nhật hồ sơ mà có thể **thay đổi khả năng kiểm soát tài khoản**.

Một session đăng nhập bị đánh cắp không được phép trở thành quyền đổi email, gắn số điện thoại của kẻ khác, xóa passkey cũ hoặc sinh bộ recovery codes mới. Với các thao tác có thể dẫn đến chiếm đoạt lâu dài, thiết kế nên dựa trên chuỗi:

~~~text
Authenticated session
      |
      v
Recent reauthentication bằng yếu tố ĐÃ ĐĂNG KÝ
      |
      v
Tạo yêu cầu PENDING, gắn account + version + TTL
      |
      +--> Thông báo kênh cũ đã xác minh
      |
      +--> Xác minh quyền sở hữu kênh mới
      |    (và xác nhận kênh cũ nếu policy yêu cầu)
      |
      v
Atomic commit, không dùng lại mã cũ
      |
      v
Audit + thông báo + xử lý session/token lifecycle
~~~

**Nguyên tắc chủ đạo:** mã nhận ở email hoặc số điện thoại **mới** chỉ chứng minh người nhận kiểm soát kênh mới. Nó không thay thế chứng minh người yêu cầu đang là chủ tài khoản. Việc có cookie đăng nhập cũng không tự chứng minh chủ tài khoản vừa hiện diện.

Bài học bao gồm: reauthentication, quy trình đổi email/số, recovery contacts/codes, kiểm soát session, Spring Security Servlet, ví dụ Java 17+ và kiểm thử chống race/replay.

## 2. Bốn lớp bảo vệ không thể thay thế nhau

| Lớp | Xác định | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| Authentication | Request thuộc session đăng nhập hợp lệ? | `SecurityContext` có `Authentication` | Session có thể bị chiếm |
| Recent reauthentication | Người dùng vừa chứng minh lại một **yếu tố hiện có**? | Current password, passkey step-up, security key | Không chứng minh email mới thuộc người đó |
| New-channel verification | Kênh mới đang do người yêu cầu kiểm soát? | Mã một lần gửi email/SMS mới | Không thay thế current factor |
| Authorization và business policy | Được phép thay giá trị này, vào lúc này? | User ID, tenant, account trạng thái bình thường, risk checks | Không tự được bảo đảm bởi một mã OTP |

OWASP khuyến nghị xác thực lại khi đổi thông tin tài khoản nhạy cảm và thông báo đến email hiện tại; nên xác nhận email mới trước khi kích hoạt, cân nhắc xác nhận cả email cũ và mới ở môi trường rủi ro cao.

NIST SP 800-63B-4 (2025) cũng nhấn mạnh quản trị việc liên kết authenticator, khôi phục tài khoản và thông báo tới những contact đã ghi nhận.

## 3. Reauthentication khác với “đã đăng nhập”

Reauthentication là yêu cầu một bằng chứng mới về **authenticator đã được ràng buộc trước đó**.

- **Tài khoản password:** yêu cầu current password và kiểm tra ở server bằng `PasswordEncoder.matches(raw, storedHash)`, có rate limit. Không so plaintext và không gửi lại hash cho client.
- **Tài khoản passkey:** yêu cầu một WebAuthn assertion mới, với challenge, RP ID, origin, chữ ký, UV và mapping credential được kiểm tra.
- **Tài khoản TOTP/security key:** xác minh bằng yếu tố đã đăng ký, chống replay, kiểm thời hạn và số lần thử.
- **Tài khoản SSO/OIDC:** thực hiện step-up/reauthentication với IdP theo protocol và kiểm kết quả, chẳng hạn `auth_time`/`acr` khi IdP hỗ trợ và policy yêu cầu. Không coi redirect SSO thành công nhờ cookie cũ là fresh login.

Một nguyên tắc quan trọng: **không dùng số điện thoại hoặc email mới như factor cũ để cho phép thay chính nó**.

### 3.1. Kiểm thời gian và phạm vi

Một hệ thống có thể yêu cầu xác thực lại trong **5 phút** gần nhất trước thay đổi recovery contact. Đây là thời gian **minh họa**, cần tùy risk policy. Server phải:

1. Ghi thời điểm reauth khi đã thực sự xác minh proof.
2. Ràng buộc nó với account/session, loại thao tác và mức bảo đảm.
3. Kiểm TTL tại thời điểm bắt đầu hoặc commit theo policy.
4. Xóa/giảm quyền step-up khi logout, chuyển user, hết hạn hoặc đổi session.
5. Giới hạn số lần thử để chống credential stuffing/OTP brute-force.

`Authentication.isAuthenticated()` hay `@PreAuthorize("isAuthenticated()")` không tự nói được mật khẩu/passkey **vừa** được xác minh lại.

## 4. State machine cho thay đổi thông tin

Một mô hình phổ biến:

~~~text
REAUTH_REQUIRED -> PENDING -> VERIFIED -> COMMITTED
                        |          |
                        +----------+----> CANCELLED
                        +---------------> EXPIRED
~~~

Thông tin của một `pending_account_change` nên gồm:

~~~text
request_id
account_id
change_type                 EMAIL / PHONE / RECOVERY_CONTACT
proposed_value
old_value_reference
created_at / expires_at
reauth_method / reauth_at
account_version_at_request
verification_hash_new
verification_hash_old       (nếu policy dual-confirm)
new_verified / old_verified
status
risk_context
~~~

Đây là **mô hình domain**, không phải entity/schema Spring Security tạo mặc định.

Các điều kiện bất biến:

- **PENDING không phải ACTIVE:** login/password reset vẫn dùng email/số **đã xác minh cũ** đến khi commit.
- **Một mã chỉ phục vụ một purpose + account + request**, có TTL và chỉ tiêu thụ một lần.
- **Yêu cầu mới hủy yêu cầu cũ** nếu policy chỉ cho một pending change.
- **Account version phải còn khớp** khi commit; nếu account đã thay đổi, token cũ không được viết đè.
- **Atomic commit** bằng transaction/database compare-and-set. `synchronized` trong một JVM không thay thế transaction khi chạy nhiều replica.
- **Notification là phát hiện gian lận**, không thay cho reauth hoặc verification.

## 5. Luồng thay đổi email an toàn

Giả sử account đang dùng `old@example.test`, muốn chuyển sang `new@example.test`:

1. Kiểm người dùng đã đăng nhập, đúng account và có quyền đổi email.
2. Hiển thị rõ thông tin hiện tại và lý do cần xác thực lại.
3. Yêu cầu current password/WebAuthn/TOTP hiện hữu, kiểm thật ở server.
4. Kiểm email đề xuất: cú pháp, domain policy, uniqueness, định danh tenant; không chuẩn hóa local-part tùy tiện.
5. Tạo pending change và token mới bằng CSPRNG, kèm TTL và account version.
6. Gửi **cảnh báo tới email cũ** đã xác minh. Với policy rủi ro cao, gửi mã yêu cầu xác nhận cả kênh cũ.
7. Gửi mã/link xác minh một lần đến **email mới**.
8. Chỉ khi đủ điều kiện (new confirmation, old confirmation nếu bắt buộc, TTL, account version, risk checks), commit trong transaction.
9. Audit và thông báo thành công; cập nhật login identifiers/kênh khôi phục sau commit, xử lý session/refresh tokens theo policy.
10. Cho user cách **báo giao dịch không được yêu cầu** qua kênh độc lập.

**Không** đổi email ngay khi user nhập ô “Email mới”. Nếu email là username, nên giữ **account ID nội bộ bất biến**, chỉ thay thuộc tính liên hệ/định danh đăng nhập sau khi được xác minh.

### 5.1. Notification so với xác nhận hai bên

| Chính sách | Quy trình | Thích hợp |
| --- | --- | --- |
| Reauth + xác nhận email mới + thông báo email cũ | Hai kiểm tra độc lập, một kênh phát hiện gian lận | Nhiều ứng dụng thông thường |
| Reauth + xác nhận cả email cũ và mới | Cần hai kênh cùng đồng ý trước commit | Account nhạy cảm, quản trị, tài chính |
| Email cũ không còn truy cập được | Đi qua **account recovery riêng** | Không tự bỏ reauth/dual-confirm |

Email có thể bị forward, chiếm mailbox hoặc lọt qua thiết bị dùng chung. Vì vậy “đã xác minh email mới” không đồng nghĩa “đã xác minh danh tính chủ cũ”.

## 6. Token/email link: những thuộc tính bắt buộc

- Sinh mã ngẫu nhiên bằng `SecureRandom`/CSPRNG; với link/copy-paste token, ví dụ 32 byte ngẫu nhiên trước Base64URL.
- Mã chỉ dùng một lần và ngắn hạn, ví dụ 10 phút theo policy, không tái sử dụng mã khi gửi lại.
- Lưu **digest/hash** của mã (hoặc giá trị được bảo vệ an toàn) thay vì plaintext lâu dài; ràng buộc account, request ID, mục đích, expiry.
- So sánh an toàn và **tiêu thụ mã bằng transaction atomic** để chặn replay/race.
- Kiểm số lần nhập, rate limit resend, không tiết lộ email tồn tại qua response.
- Dùng HTTPS, không ghi mã/full confirmation URL vào log, referrer, analytics hoặc exception.
- Link từ email **không nên commit bằng GET**: hệ thống lọc thư có thể tự mở link. Có thể mở trang xác nhận bằng GET rồi yêu cầu POST có CSRF token/user intent.
- Nếu đã có nhiều yêu cầu pending, ràng buộc mã với chính request/version đã tạo và hủy pending cũ.

Mã 6 chữ số OTP có ít entropy hơn token 32 byte: phải quản lý thời hạn, số lần thử, rate limit nghiêm hơn. Không dùng mã OTP ngắn như recovery credential tồn tại vô hạn.

## 7. Thay đổi số điện thoại: bảo vệ thêm khỏi SIM swap

Đổi số có thể là cập nhật liên hệ đơn thuần **hoặc** thay authenticator SMS đang dùng cho login/khôi phục. Trường hợp thứ hai có rủi ro cao hơn.

Quy trình nên có:

1. Xác thực lại bằng **yếu tố đã đăng ký**, tốt nhất độc lập với số đang thay khi có rủi ro.
2. Chuẩn hóa số theo E.164 bằng thư viện hỗ trợ quốc gia/khu vực; không tự cộng mã vùng tùy tiện.
3. Lưu số đề xuất ở trạng thái PENDING.
4. Gửi mã xác minh tới **số mới**, chống đoán/replay/rate abuse; đây là bước chứng minh kiểm soát kênh mới.
5. Gửi cảnh báo tới **email hoặc số cũ đã xác minh**, có cách báo gian lận.
6. Với tài khoản nhạy cảm, xem xét dấu hiệu SIM swap/number porting, thiết bị lạ, số mới được đổi liên tục; áp dụng hold/step-up mạnh.
7. Chỉ commit khi policy đạt; sau đó cập nhật binding MFA, token reset và notification.

**SMS không phishing-resistant** như WebAuthn. Kẻ gian có thể chiếm số qua SIM swap hoặc phương thức viễn thông khác, nên nhận mã ở số mới không đủ để bỏ qua reauth.

## 8. Dữ liệu khôi phục và recovery codes

“Recovery data” có thể gồm **email dự phòng, số liên hệ dự phòng, recovery codes, thiết bị tin cậy, passkey/security key thứ hai, recovery contact**.

### 8.1. Recovery codes

Một quy trình sinh lại codes an toàn:

1. Yêu cầu recent reauth bằng factor hiện hữu.
2. Thông báo rõ **bộ codes cũ sẽ bị vô hiệu**.
3. Sinh bộ mã CSPRNG có entropy đủ cao.
4. Lưu hash/digest gắn account, purpose, trạng thái unused; chỉ hiển thị raw codes **một lần** cho chủ tài khoản qua HTTPS.
5. Khi dùng một mã, đánh dấu/tiêu thụ atomic để không dùng lại.
6. Audit, cảnh báo qua kênh cũ, giới hạn số lần thử; sau recovery nên yêu cầu đăng ký authenticator mới.
7. Không gửi raw codes qua email thông thường và không log/đưa vào URL theo dõi.

### 8.2. Thay authenticator và recovery contacts

Thêm passkey/TOTP/backup device là **binding một authenticator mới**, không chỉ thêm một dòng database. Cần bước xác thực lại, ceremony xác minh authenticator mới, uniqueness/account binding, thông báo ngoài băng và quy trình thu hồi khi mất thiết bị. Không xóa yếu tố cuối cùng trước khi người dùng có đường khôi phục hợp lệ.

Nếu user **mất mọi authenticator**, phải dùng **account recovery** có bằng chứng/kiểm tra rủi ro độc lập; không biến “Tôi không còn email/số cũ” thành nút bỏ qua hết bảo mật. Câu hỏi bảo mật kiểu “tên thú cưng” không phải yếu tố đáng tin.

## 9. Spring Security giúp được gì?

Với **Spring Boot 3.5.x / Spring Security 6.5.x / Java 17+ (Servlet)**:

- `SecurityFilterChain` và `authorizeHttpRequests` bảo vệ toàn bộ endpoint quản lý account.
- `PasswordEncoder.matches(...)` kiểm current password với hash lưu tại server.
- `@EnableMethodSecurity` và `@PreAuthorize` bảo vệ business service (không bật mặc định chỉ vì dùng starter).
- CSRF protection mặc định bảo vệ POST/PUT/PATCH/DELETE trong ứng dụng dùng session-cookie.
- Form login, session fixation protection, cookie policy và logout cung cấp nền tảng quản lý session.

Spring Security **không tự** cung cấp business workflow đổi email/số, pending state, gửi OTP, dual confirmation, uniqueness, risk/cooldown, account-version transaction hoặc outbox notification. Những phần này thuộc ứng dụng.

### 9.1. Cấu hình minh họa (một fragment)

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/health").permitAll()
            .requestMatchers("/account/security/**").authenticated()
            .anyRequest().denyAll())
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

Đoạn trên nằm trong một class `@Configuration` có import Spring Security tương ứng; **không phải một chương trình độc lập**. CSRF được giữ mặc định. Các POST JSON phải gửi CSRF token qua header nếu dùng cookie-based login; không tắt CSRF chỉ để qua lỗi HTTP 403.

Một service minh họa:

~~~java
@PreAuthorize("isAuthenticated()")
public void requestEmailChange(
        String accountId, String proposedEmail, String currentPassword) {
    // 1. Kiểm principal từ SecurityContext thuộc accountId.
    // 2. passwordEncoder.matches(currentPassword, storedHash).
    // 3. Rate limit, risk checks, xác minh email policy.
    // 4. Sinh pending request + mã CSPRNG, TTL/version.
    // 5. Gửi thông báo/confirmation qua outbox.
}
~~~

**Điểm quan trọng:** `@PreAuthorize("isAuthenticated()")` chỉ yêu cầu đã đăng nhập; nó **không tự kiểm current password**. Các bước ghi chú phải được hiện thực hóa trong domain service khi triển khai thật.

### 9.2. Tài khoản dùng SSO/OIDC

Nếu ứng dụng không có local password, không nên thêm giả một trường “current password”. Thay vào đó yêu cầu step-up với IdP qua giao thức phù hợp, kiểm `auth_time` hoặc assurance claims của token do **issuer tin cậy** ký, đồng thời ràng buộc authentication response với request/session. JWT access token cũ hoặc client tự gửi `reauthenticated=true` không phải bằng chứng fresh reauth.

## 10. Java 17 chạy độc lập: mô phỏng xác nhận kênh cũ và mới

Chương trình sau minh họa một **state machine thuần Java**, không dùng Spring hay gửi thư thật. Nó mô phỏng một người dùng đã vượt qua bước reauth và một yêu cầu PENDING có hai mã khác nhau. Mã chỉ tồn tại trong chương trình thử nghiệm, không gửi ra HTTP; mỗi mã phải đúng và chỉ được chấp nhận một lần. **Đây không phải server xác thực production**: còn thiếu persistence, CSRF, session, mailbox delivery, rate limiting và audit.

Tạo `AccountChangeRulesDemo.java`:

~~~java
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.time.Duration;
import java.util.Base64;

public class AccountChangeRulesDemo {

    static final SecureRandom RANDOM = new SecureRandom();

    static String newCode() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding().encodeToString(bytes);
    }

    static byte[] digest(String input) throws Exception {
        return MessageDigest.getInstance("SHA-256")
                .digest(input.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    static final class Pending {
        final byte[] oldHash;
        final byte[] newHash;
        final String newEmail;
        final Instant expiresAt;
        final long expectedVersion;
        boolean oldConfirmed;
        boolean newConfirmed;

        Pending(String oldCode, String newCode,
                String newEmail, long version, Instant now)
                throws Exception {
            this.oldHash = digest(oldCode);
            this.newHash = digest(newCode);
            this.newEmail = newEmail;
            this.expectedVersion = version;
            this.expiresAt = now.plus(Duration.ofMinutes(10));
        }

        synchronized boolean confirmOld(String code, Instant now,
                long currentVersion) throws Exception {
            if (oldConfirmed || !valid(now, currentVersion)) return false;
            if (!MessageDigest.isEqual(oldHash, digest(code))) return false;
            oldConfirmed = true;
            return true;
        }

        synchronized boolean confirmNew(String code, Instant now,
                long currentVersion) throws Exception {
            if (newConfirmed || !valid(now, currentVersion)) return false;
            if (!MessageDigest.isEqual(newHash, digest(code))) return false;
            newConfirmed = true;
            return true;
        }

        boolean canCommit(Instant now, long currentVersion) {
            return valid(now, currentVersion)
                    && oldConfirmed && newConfirmed;
        }

        private boolean valid(Instant now, long version) {
            return now.isBefore(expiresAt)
                    && expectedVersion == version;
        }
    }

    public static void main(String[] args) throws Exception {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");
        String oldCode = newCode();
        String newCode = newCode();

        Pending pending = new Pending(
                oldCode, newCode, "new@example.test", 3L, now);

        System.out.println("before=" + pending.canCommit(now, 3L));
        System.out.println("old=" +
                pending.confirmOld(oldCode, now, 3L));
        System.out.println("oldReplay=" +
                pending.confirmOld(oldCode, now, 3L));
        System.out.println("new=" +
                pending.confirmNew(newCode, now, 3L));
        System.out.println("ready=" +
                pending.canCommit(now, 3L));
        System.out.println("staleVersion=" +
                pending.canCommit(now, 4L));
        System.out.println("expired=" +
                pending.canCommit(now.plus(Duration.ofMinutes(11)), 3L));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AccountChangeRulesDemo.java
java AccountChangeRulesDemo
~~~

**Stdout chính xác:**

~~~text
before=false
old=true
oldReplay=false
new=true
ready=true
staleVersion=false
expired=false
~~~

Giải thích: trước khi xác nhận đủ hai kênh, không được commit; old code được chấp nhận đúng một lần, mã mới riêng; yêu cầu đã đủ hai code vẫn phải bị từ chối nếu version thay hoặc TTL hết. Trong ứng dụng thật, việc tiêu thụ mã và commit phải là một giao dịch atomic, không chỉ một lời gọi `canCommit(...)` tách rời.

## 11. Các tấn công và lỗi triển khai thường gặp

| Tình huống | Sai lầm | Kiểm soát |
| --- | --- | --- |
| Session bị chiếm | Cho đổi email chỉ vì `authenticated()` | Recent reauth bằng factor cũ |
| CSRF | API POST dùng cookie nhưng disable CSRF | CSRF token + SameSite/Origin policy |
| Token giả | Client tự gửi `verified=true` | Server kiểm mã, account và request ID |
| Email mới bị kẻ khác kiểm soát | Chỉ cần mã email mới là đổi được | Reauth cũ + old notification/confirmation |
| Xác nhận mã hết hạn | Không kiểm TTL | So thời gian server và expire |
| Replay | Mã dùng được nhiều lần | Atomic consume, used marker, TTL |
| Hai tab thay đổi đồng thời | Pending cũ ghi đè pending mới | Account version, transaction/CAS |
| GET từ email scanner | Link GET commit ngay | POST có user intent và CSRF |
| SIM swap | Dựa vào SMS làm chứng minh duy nhất | Factor độc lập, risk/porting signals |
| Account enumeration | Response nói email đã có account | Chống tiết lộ, rate limit, generic responses |
| Recovery yếu | Support đổi số qua security question | Recovery policy riêng, audit |
| IDOR/BOLA | Nhận userId đích từ JSON rồi thay | Account ID từ server-side Authentication |
| Logout sau đổi không revoke session khác | Người lạ tiếp tục dùng session cũ | Session/token revocation theo policy |
| Gửi OTP vào log/URL | Rò mã qua proxy/analytics | Mask và dùng kênh bảo vệ |

### Race và consistency

Nếu xác nhận kênh cũ và mới đến đồng thời qua hai replica, service phải lưu sự kiện vào persistent store và dùng transaction/unique constraint; `synchronized` chỉ bảo vệ **một tiến trình JVM**. Một request `COMMITTED` không được lặp lại, còn bất kỳ pending cũ nào phải bị vô hiệu khi account version thay đổi.

### Thông báo và outbox

Nên phát thông báo an ninh **đến kênh cũ đã xác minh** khi thay email/số/recovery data, có nội dung “Không phải tôi” với quy trình hỗ trợ rõ ràng. Production nên dùng transactional outbox/retry idempotent để không đánh mất audit/notification nếu SMTP/SMS gateway chậm hoặc lỗi.

## 12. Ma trận kiểm thử

- [ ] Chưa đăng nhập: không được tạo pending.
- [ ] Session hợp lệ nhưng current factor sai: không được bắt đầu thay đổi.
- [ ] Current factor đúng, email mới chưa verify: vẫn dùng email cũ.
- [ ] Mã gửi đến kênh cũ **không** xác minh được kênh mới và ngược lại.
- [ ] Xác nhận đủ điều kiện, đúng account/request/version: commit đúng một lần.
- [ ] Mã bị sửa, đã dùng, hết hạn hoặc gửi lại từ yêu cầu cũ: từ chối.
- [ ] Thao tác từ session của user A không đổi được contact của user B.
- [ ] POST cross-origin thiếu CSRF token: bị chặn.
- [ ] Thay số mới có OTP nhưng không có reauth: vẫn bị chặn.
- [ ] Account bị SIM swap/nghi ngờ takeover: thực thi step-up/hold theo policy.
- [ ] Sinh lại recovery codes: codes cũ bị vô hiệu, mã đã dùng không tái sử dụng.
- [ ] Mất mọi yếu tố: đi qua recovery flow riêng, không bypass bằng email mới.
- [ ] Hai tab/replica thay contact đồng thời: token cũ không ghi đè account mới.
- [ ] Sau commit: notification, audit và xử lý session/token đã được kích hoạt.

Kiểm thử không chỉ dựa vào HTTP status: ứng dụng form login có thể trả `302` redirect thay vì `401`. Điều cần kiểm chứng là **không có thay đổi dữ liệu nhạy cảm khi bằng chứng chưa đủ**.

## 13. Checklist triển khai production

**Xác thực và policy:** current factor/step-up phù hợp, reauth age ngắn, rate limiting, account ownership/tenant checks, CSRF, HTTPS, session fixation protection.

**State và persistence:** pending riêng, TTL, hash token, request/account/version binding, atomic compare-and-set, unique contact policy, outbox.

**Email/phone:** xác minh kênh mới, cảnh báo kênh cũ, dual confirmation cho high-risk, xử lý mất kênh cũ qua recovery flow riêng, đánh giá SMS/SIM-swap.

**Recovery:** codes CSPRNG và single-use, mã thô chỉ hiển thị một lần, bảo vệ enrollment/replacement của passkeys/TOTP, không xóa factor cuối nếu chưa có đường khôi phục hợp lệ.

**Vận hành:** audit không chứa secrets, monitoring bất thường, cảnh báo người dùng, incident response, revoke sessions/refresh tokens theo yêu cầu, kiểm thử đa replica.

## 14. Câu hỏi tự kiểm tra

1. Vì sao `isAuthenticated()` chưa đủ để đổi email?
2. Mã email mới chứng minh điều gì, và **không** chứng minh điều gì?
3. Vì sao nên giữ thay đổi ở trạng thái PENDING?
4. Phải gắn mã xác minh với những thuộc tính nào để chống dùng chéo?
5. Tại sao cần kiểm account version và atomic commit?
6. Khi nào cần xác nhận cả email cũ và mới?
7. Nếu user mất email cũ, có được tự bỏ reauth không?
8. Vì sao thay số nhận SMS OTP là thay authenticator binding?
9. Recovery code nên lưu và tiêu thụ thế nào?
10. Một trang GET verification link có thể gặp rủi ro gì với email security scanner?
11. Đối với user OIDC/passwordless, có thể dùng cách nào để reauth?
12. Những việc nào do Spring Security hỗ trợ, những việc nào ứng dụng phải tự triển khai?

**Kết luận:** thay email, số điện thoại hoặc dữ liệu khôi phục là thao tác **thay đổi ranh giới tin cậy** của account. Thiết kế an toàn là **reauth bằng yếu tố hiện tại → pending → xác minh kênh mới → kiểm policy/version và commit atomic → cảnh báo kênh cũ, audit, session lifecycle**; không thay thế từng bước bằng cookie hoặc mã nhận trên kênh mới.

## 15. Tài liệu chính thức

- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Email Validation and Verification](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html)
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP — MFA Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [NIST SP 800-63B-4 (2025) — Authenticator Lifecycle and Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
