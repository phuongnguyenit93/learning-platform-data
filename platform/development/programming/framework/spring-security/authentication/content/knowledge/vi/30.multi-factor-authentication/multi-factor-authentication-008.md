# Đăng ký yếu tố, recovery code và chính sách thay đổi yếu tố

## 1. Vì sao vòng đời yếu tố MFA quan trọng ngang với bước đăng nhập?

Multi-Factor Authentication (MFA) yêu cầu bằng chứng từ **ít nhất hai yếu tố xác thực độc lập**: thứ người dùng biết (password/PIN), thứ họ sở hữu (security key, ứng dụng sinh OTP), hoặc đặc điểm sinh trắc, tùy cơ chế. Hai mật khẩu khác nhau không trở thành hai yếu tố chỉ vì cần nhập hai lần.

Một hệ thống có bước login MFA rất chặt chẽ vẫn có thể bị chiếm quyền nếu kẻ tấn công chỉ cần lấy một session còn sống, vào **“Thêm thiết bị mới”**, tự đăng ký phương thức của mình rồi xóa yếu tố cũ. Chính vì vậy, **đăng ký yếu tố**, **mã khôi phục (recovery code)** và **quy tắc đổi/gỡ yếu tố** là phần của biên giới bảo mật, không chỉ là các form CRUD trong trang Settings.

Các câu hỏi thiết kế:

1. Ai được bắt đầu đăng ký một authenticator mới? Có cần xác thực lại bằng yếu tố đã đăng ký không?
2. Làm cách nào bảo đảm người dùng **thật sự sở hữu** thiết bị/email/ứng dụng TOTP mới trước khi đánh dấu ACTIVE?
3. Người dùng mất mọi yếu tố thì hồi phục tài khoản thế nào mà không mở đường bypass MFA?
4. Recovery code được sinh, hiển thị, lưu, dùng một lần, thay thế và vô hiệu thế nào?
5. Khi thay đổi yếu tố, các session đang mở, token đăng nhập lâu dài, factor authority và thông báo bảo mật có bị cập nhật không?
6. Hành vi khi hai request đồng thời hoàn tất enrollment, dùng cùng code hoặc xóa yếu tố cuối cùng là gì?

**Phạm vi:** Spring Security **Servlet** và thiết kế dịch vụ quản lý MFA của ứng dụng. Phần ví dụ lập trình gồm Java 17 chạy độc lập cho recovery code và một đoạn cấu hình Spring Security **7.1.x** cho chính sách factor; không đồng nhất các API của Spring Security 7.x với những dự án vẫn dùng 6.x.

### Bốn khái niệm phải tách riêng

| Khái niệm | Dữ liệu | Thời điểm có hiệu lực | Điều KHÔNG suy ra |
| --- | --- | --- | --- |
| **Enrolled factor** | Bản ghi authenticator đã được binding vào user, ACTIVE | Sau khi kiểm chứng sở hữu yếu tố mới | Không chứng minh yếu tố vừa được dùng trong login hiện tại |
| **Satisfied factor** | Bằng chứng người dùng vừa xác thực bằng phương thức cụ thể, có thời điểm | Khi authentication thành công | Không chứng minh authenticator đó vẫn ACTIVE ở repository |
| **Recovery code** | Secret dự phòng, chỉ dùng một lần, do người dùng giữ offline | Khi được phát hành và chưa revoke/consume | Không tương đương mặc nhiên với MFA phishing-resistant |
| **Local session** | Cookie session, SecurityContext/Authentication | Sau login theo policy | Không bảo đảm vừa xác thực lại để thay đổi yếu tố |

Một session được tạo nhiều ngày trước có thể vẫn hợp lệ để xem hồ sơ, nhưng **không nên đủ điều kiện xóa passkey, đổi số điện thoại khôi phục hoặc tạo recovery codes mới**.

## 2. Những phương thức có thể đăng ký và rủi ro riêng

| Yếu tố | Đăng ký/binding | Kiểm tra sở hữu | Điểm cần bảo vệ |
| --- | --- | --- | --- |
| **Passkey/WebAuthn** | Tạo credential public key gắn RP ID, user, credential ID | Xác minh WebAuthn challenge/response, origin, RP ID, chính sách user verification | Chống phishing; lưu public key và metadata, kiểm soát registration CSRF, không chấp nhận origin tùy ý |
| **TOTP** | Sinh secret ngẫu nhiên, trình bày QR/provisioning URI trong phiên bảo mật | Yêu cầu nhập mã TOTP từ app, chưa xác minh thì chưa ACTIVE | Mã theo chu kỳ có thể bị phishing; bảo vệ secret server-side và chống replay |
| **Hardware security key** | WebAuthn/FIDO2 hoặc protocol chuyên biệt | Chứng minh sở hữu khóa trong registration ceremony | Thiết bị bị mất; cần backup authenticator và gỡ theo policy |
| **Email/SMS OTP hoặc OTT** | Chỉ dùng contact đã được xác minh, gắn tài khoản | Challenge gửi out-of-band và được xác nhận | Email/SMS có thể bị chiếm; SIM swap, chuyển tiếp, cùng kênh với password reset |
| **Saved recovery code** | Sinh ngẫu nhiên, chỉ cho chủ tài khoản xem và lưu offline | Xác minh secret trong kho hash, single-use | Nếu lộ code, đường recovery có thể bị chiếm; không phải factor đăng nhập thường ngày |

**Phishing-resistant không đồng nghĩa mọi MFA.** WebAuthn/passkeys ràng buộc RP ID/origin nên chống được một lớp phishing mà TOTP/SMS không có. Một số passkey với xác minh người dùng tại authenticator có thể thỏa các thuộc tính đa yếu tố trong cùng authenticator, nhưng assurance thực tế vẫn theo chính sách NIST, thiết bị và flow xác minh.

### Tên, loại và ID của yếu tố

Không lưu mỗi trường `mfaEnabled=true` rồi coi mọi thiết bị là một. Có thể lưu bản ghi với:

- `factor_id`: ID bất biến, ngẫu nhiên, không phải email/số điện thoại.
- `user_id`: principal ổn định từ hệ thống tài khoản; tenant khi có multi-tenant.
- `type`: `WEBAUTHN`, `TOTP`, `HARDWARE_KEY`, `OUT_OF_BAND`...
- `state`: `PENDING` / `ACTIVE` / `REVOKED`, `created_at`, `verified_at`, `revoked_at`.
- `credential_id` / public key / thuật toán / counter metadata cho WebAuthn; **secret mã hóa** cho TOTP; không lưu plaintext recovery codes.
- `label` do người dùng đặt để phân biệt thiết bị, giới hạn độ dài và escape output; không coi nhãn là định danh bảo mật.
- `factor_version` hoặc `security_stamp` trên user để vô hiệu bằng chứng/session cũ khi nhân tố thay đổi.

Một tài khoản có thể có nhiều credential cùng loại (hai security keys) để tránh khóa tài khoản khi mất một thiết bị. Việc chọn đủ hai yếu tố độc lập tùy threat model, không dựa trên số lượng thiết bị một cách máy móc.

## 3. Đăng ký yếu tố: giao dịch hai pha, không kích hoạt trước khi kiểm chứng

Một sơ đồ trạng thái đơn giản:

```text
UNENROLLED
    |
    | Người dùng đã đăng nhập và vượt kiểm tra step-up
    v
PENDING_ENROLLMENT  -- (quá hạn/hủy) --> EXPIRED/CANCELLED
    |
    | Tạo challenge / TOTP secret / WebAuthn options
    | Lưu state giới hạn TTL, gắn user + request + session
    |
    | Người dùng chứng minh có yếu tố mới
    v
VERIFIED (trong giao dịch, chưa để request khác thấy ACTIVE)
    |
    | Commit atomic vào kho yếu tố
    v
ACTIVE
    |
    | Step-up bằng yếu tố cũ hoặc recovery đã được chấp thuận
    | + thông báo + thu hồi context cũ
    v
REVOKED
```

**Điều kiện trước khi bắt đầu:** kiểm tra account đang hoạt động, identity chủ tài khoản, chính sách enroll, rủi ro phiên hiện tại, xác thực lại đủ mới. Đăng ký lần đầu cần policy onboarding riêng; không để tài khoản đã có MFA sử dụng đường “bootstrap” yếu chỉ dựa vào mật khẩu.

### 3.1. TOTP: chỉ ACTIVE sau khi user nhập mã đúng

1. Backend dùng `SecureRandom` (CSPRNG) sinh secret TOTP, lưu trạng thái `PENDING` ngắn hạn. Không ghi secret vào log, analytics, session serialize không bảo vệ hoặc exception.
2. Render provisioning URI `otpauth://totp/...`/QR qua HTTPS, không cache; chỉ cho người dùng đang step-up thấy.
3. Người dùng quét vào authenticator app và nhập mã đang hiện; backend xác minh HMAC/time-step theo RFC 6238, clock drift có giới hạn, rate limit và chống dùng lại cùng time-step.
4. Khi verification thành công, **atomic commit** thiết bị sang `ACTIVE` cùng user ID. Không kích hoạt ngay khi QR được tạo.
5. Hiển thị hướng dẫn dự phòng và phát saved recovery codes theo policy; thông báo thêm yếu tố qua kênh đã đăng ký.

TOTP secret phải còn khả năng dùng để tính/kiểm tra OTP nên không thể chỉ hash như password; thường cần **mã hóa at rest**, tách khóa và quyền giải mã. Không tự triển khai TOTP từ đầu trong production nếu có thư viện đã được kiểm thử; Spring Security MFA không mặc định có một API “register TOTP + recovery code” cho mọi version.

### 3.2. WebAuthn/passkey: dùng ceremony được framework hỗ trợ

Với Spring Security Servlet **7.1.x** và `spring-security-webauthn`, flow đăng ký gồm hai request (đường dẫn mặc định):

```http
POST /webauthn/register/options HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<opaque-session-id>
X-CSRF-TOKEN: <csrf>

{}
```

Server tạo WebAuthn challenge và registration options, gắn chúng với request/session theo policy. Trình duyệt gọi `navigator.credentials.create(...)` bằng các options sau khi xử lý Base64URL, rồi gửi credential attestation về:

```http
POST /webauthn/register HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<opaque-session-id>
X-CSRF-TOKEN: <csrf>
Content-Type: application/json

{"publicKey":{"credential":{"id":"...","response":{"attestationObject":"...","clientDataJSON":"..."}}}}
```

JSON ở trên **chỉ lược đồ minh họa**, không phải payload WebAuthn đầy đủ để gửi chạy thật. Backend phải dùng verifier chuẩn để kiểm chứng challenge, RP ID, origin, type, chính sách user verification/attestation, credential uniqueness và trạng thái; **không tự tin dữ liệu do browser gửi**. Credential public key và ID được lưu gắn đúng user. Với Spring Security có `PublicKeyCredentialUserEntityRepository` và `UserCredentialRepository`, có các triển khai JDBC; in-memory chỉ phù hợp demo/test không cần persist.

**Cẩn thận khi đăng ký passkey:** việc người dùng đã đăng nhập một lần chưa đủ để cho phép gắn passkey mới khi account đang có MFA; cần fresh step-up ở trang quản lý yếu tố và bảo vệ CSRF. Khi revoke credential, tránh xóa thông tin cần thiết trước khi commit audit/revocation.

### 3.3. Email/SMS: verify contact không đồng nghĩa factor mạnh

Khi cho phép thêm một phương thức nhận OTT qua email/SMS, ứng dụng phải chứng minh contact mới thực sự thuộc user **và** chỉ người có quyền thay đổi MFA mới được bắt đầu quá trình. OTP gửi tới **số điện thoại/email mới** không chứng minh đó là chủ tài khoản: attacker có thể thay địa chỉ nhận rồi tự vượt bước “xác minh contact”.

Bảo vệ gồm: bước re-auth bằng factor **đã đăng ký từ trước**, xác minh contact mới, có delay/risk review khi cần, thông báo tới contact **cũ** và rate limit theo user/IP/tenant. SMS dễ gặp SIM swap và phishing; nếu có lựa chọn, ưu tiên WebAuthn/passkeys cho thao tác nhạy cảm.

## 4. Recovery code: đường dự phòng phải có assurance rõ

**Saved recovery codes** là các secret người dùng nhận **khi đã enroll MFA** (hoặc tái phát hành sau re-auth), lưu **offline** ở nơi an toàn. Khi mất yếu tố chính, họ dùng một code để đi qua quy trình recovery được kiểm soát. Một saved code là **credential**, không phải câu hỏi bảo mật và không phải token OAuth2 hay OTP TOTP.

Theo NIST SP 800-63B-4 (2025), saved recovery codes cần có **ít nhất 64 bit ngẫu nhiên** từ CSPRNG; ví dụ trong bài dùng **128 bit** để dễ chống brute force/offline attacks. Người dùng phải nhận code qua kênh bảo vệ với xác thực đủ mạnh, giữ offline. Kho server **lưu hash chứ không plaintext**, throttle lần thử, invalidate sau mỗi lần dùng và cấp lại saved recovery code khi recovery hoàn tất theo chính sách.

### 4.1. Quy trình phát hành an toàn

1. Người dùng đã đăng nhập và vượt **fresh re-authentication** phù hợp, ví dụ passkey hiện có hoặc password cùng yếu tố thứ hai. Chỉ có cookie session cũ không đủ.
2. Tạo một tập code ngẫu nhiên bằng `SecureRandom`; ví dụ 8–10 mã *chỉ là quyết định UX*, không phải con số bắt buộc của chuẩn. Mỗi mã đủ entropy; không dùng `Random`, timestamp, username hay mã 6 số tự sinh cho saved codes.
3. Với từng code, lưu **hash one-way** trong bản ghi gắn account và code ID/version; không lưu plaintext. Cân nhắc HMAC/pepper trong key store để hạn chế tác động database leak, quản lý rotation key. Nếu mã entropy thấp, cần KDF phù hợp và rate limit rất chặt.
4. Chỉ hiển thị mã **một lần** trong màn hình HTTPS đã re-auth, cho phép tải/in và cảnh báo giữ offline. Trả `Cache-Control: no-store`, không đưa mã vào URL, log, email, trace, screenshot telemetry hay analytics.
5. User xác nhận đã lưu an toàn theo UX phù hợp. Thông báo việc sinh/tái tạo mã qua kênh bảo mật đã đăng ký; audit metadata, **không ghi raw code**.
6. Nếu tạo **bộ mã mới**, vô hiệu **cả bộ mã cũ** bằng transaction/phiên bản, tránh bộ cũ tiếp tục là cửa sau.

### 4.2. Tiêu thụ code

```text
POST /account/recovery/verify
    |
    | account_id đã xác định + raw recovery code + CSRF (nếu browser)
    v
Rate limit / anti-automation / risk check
    |
    v
Tính hash / kiểm tra đối chiếu theo code thuộc account đó
    |
    | Giao dịch atomic: tìm ACTIVE -> đánh dấu USED và commit
    | Chỉ một request thắng được race
    v
Recovery state hẹp, thời gian ngắn, không mặc nhiên full login
    |
    | Thiết lập yếu tố mới theo policy; thông báo + session review
    v
Kết thúc recovery, thu hồi code đã dùng, phát mã thay thế an toàn
```

Không chỉ làm `SELECT` rồi `DELETE` riêng rẽ không có locking/transaction: hai request đồng thời có thể cùng chấp nhận một code. Một cách production là conditional update `UPDATE ... SET used_at=NOW() WHERE user_id=? AND hash=? AND used_at IS NULL`, chấp nhận **chỉ khi số hàng bị update = 1**. Cũng có thể dùng transaction/unique index và cơ chế locking thích hợp.

**Không nâng recovery code thành `FACTOR_WEBAUTHN` hoặc `FACTOR_OTT` bằng cách tự thêm `GrantedAuthority`.** Recovery có thể cho phép bước thay thế yếu tố với quyền rất hẹp nếu policy chấp nhận; nó không chứng minh người dùng có authenticator đã mất. Cân nhắc giới hạn chức năng, giảm độ tin cậy, delay, thông báo trước khi cấp lại toàn quyền.

### 4.3. Saved vs issued recovery code

- **Saved:** tập bí mật tạo từ trước và user giữ offline, ví dụ mã 128-bit in ra giấy. Mỗi mã chỉ dùng một lần.
- **Issued:** mã được cấp mới **lúc recovery** qua kênh khôi phục đã được thiết lập/kiểm chứng trước, như email/phone. Phải kiểm tra kênh đó vẫn đáng tin và chống dùng contact mới bị attacker sửa.

Không gửi saved codes dưới dạng plaintext qua email mặc định, không dùng “trả lời câu hỏi mẹ sinh ở đâu” làm đủ căn cứ. Nếu user **mất cả yếu tố và toàn bộ mã**, chuyển sang quy trình recovery rủi ro cao dựa bằng chứng độc lập (hỗ trợ xác minh danh tính, proofing, thời gian chờ, phê duyệt theo risk), không tự bỏ MFA chỉ vì người dùng biết email.

## 5. Java 17 chạy độc lập: sinh, hash, dùng một lần và rotate recovery codes

Để thấy cơ chế single-use, ta viết **một chương trình Java 17 không cần Spring Boot**, chạy được bằng `javac` và `java`. Chương trình chỉ sử dụng **bộ nhớ một JVM**, không xử lý HTTP, database, CSRF, rate limiting, re-auth, user session hay recovery authorization. Nó **không phải code production**, nhưng giúp kiểm chứng hash-only và việc một code chỉ redeem một lần.

Giả định mã là 16 byte ngẫu nhiên (**128 bit**); Base64URL không padding tạo chuỗi 22 ký tự. Với entropy cao như vậy, SHA-256 dùng làm ví dụ hash one-way phù hợp mục đích minh họa; với mã entropy thấp, phải có KDF và kiểm soát thử sai phù hợp. Dù token ngẫu nhiên, vẫn phải bảo vệ giá trị hiển thị ở browser và bộ nhớ quá trình.

Tạo file `RecoveryCodeDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class RecoveryCodeDemo {
    private final SecureRandom random = new SecureRandom();
    private final Map<String, List<byte[]>> hashedByAccount =
            new HashMap<>();

    // synchronized chỉ giúp atomic trong một JVM demo.
    // Production cần atomic consume trong database/shared store.
    public synchronized List<String> issue(String accountId, int count) {
        Objects.requireNonNull(accountId, "accountId");
        if (count < 1 || count > 12) {
            throw new IllegalArgumentException("invalid count");
        }

        List<String> shownOnce = new ArrayList<>();
        List<byte[]> digests = new ArrayList<>();

        for (int i = 0; i < count; i++) {
            byte[] randomBytes = new byte[16]; // 128 bits
            random.nextBytes(randomBytes);
            String raw = Base64.getUrlEncoder()
                    .withoutPadding().encodeToString(randomBytes);
            shownOnce.add(raw);
            digests.add(sha256(raw));
        }

        // Rotate toàn bộ set: mọi mã cũ không còn được chấp nhận.
        hashedByAccount.put(accountId, digests);
        return List.copyOf(shownOnce);
    }

    public synchronized boolean consume(String accountId, String raw) {
        if (accountId == null || raw == null) {
            return false;
        }

        List<byte[]> digests = hashedByAccount.get(accountId);
        if (digests == null) {
            return false;
        }

        byte[] candidate = sha256(raw);
        Iterator<byte[]> iterator = digests.iterator();
        while (iterator.hasNext()) {
            byte[] stored = iterator.next();
            if (MessageDigest.isEqual(stored, candidate)) {
                iterator.remove(); // single-use trong một JVM
                return true;
            }
        }
        return false;
    }

    private static byte[] sha256(String text) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(text.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException impossibleOnJava17) {
            throw new IllegalStateException(impossibleOnJava17);
        }
    }

    public static void main(String[] args) {
        RecoveryCodeDemo store = new RecoveryCodeDemo();
        List<String> original = store.issue("alice", 2);

        String first = original.get(0);
        String unused = original.get(1);

        System.out.println("firstUse=" + store.consume("alice", first));
        System.out.println("replay=" + store.consume("alice", first));
        System.out.println("wrongAccount=" + store.consume("bob", unused));

        List<String> rotated = store.issue("alice", 2);
        System.out.println("oldAfterRotation="
                + store.consume("alice", unused));
        System.out.println("newAfterRotation="
                + store.consume("alice", rotated.get(0)));
    }
}
```

Chạy với JDK 17+:

```bash
javac RecoveryCodeDemo.java
java RecoveryCodeDemo
```

**Stdout chính xác** (random codes không được in):

```text
firstUse=true
replay=false
wrongAccount=false
oldAfterRotation=false
newAfterRotation=true
```

Tính đúng đắn minh họa:

- Code đầu được tiêu thụ một lần; thử lại trả `false`.
- Một code của Alice không hoạt động với account Bob.
- Tạo bộ mới làm bộ cũ không còn được chấp nhận.
- Không lưu raw code trong map; map chỉ chứa SHA-256 digest.
- `MessageDigest.isEqual` giúp so sánh byte hash, nhưng demo vẫn không chống mọi timing side-channel, không rate limit và không an toàn khi chạy multi-node. Sản phẩm thật phải có transaction, error handling và audit.

**Không dùng output của demo làm bằng chứng an toàn production.** NIST yêu cầu bảo vệ mã ở giai đoạn phát hành, xác minh và sau sử dụng; chỉ viết một đoạn Java hash là chưa đủ.

## 6. Chính sách đổi/gỡ yếu tố và tránh chiếm tài khoản

Thay đổi phương thức MFA là thao tác **high-risk**. Một session đang đăng nhập từ trước, kể cả có cookie hợp lệ, **không đủ** làm bằng chứng cho phép thay yếu tố quan trọng. OWASP khuyến nghị re-authentication bằng yếu tố đã có trước khi thay đổi, kiểm tra rủi ro và thông báo qua kênh ngoài băng.

### Bảng policy theo thao tác

| Thao tác | Bằng chứng cần thiết (ví dụ policy) | Điều kiện commit | Hậu kiểm |
| --- | --- | --- | --- |
| Enroll yếu tố thứ hai lần đầu | Xác thực primary **vừa mới thực hiện**, onboarding risk checks, account chưa có MFA | Yếu tố mới đã chứng minh possession | Phát mã khôi phục, thông báo, cập nhật factor_version |
| Thêm passkey/TOTP thứ ba | Fresh verification bằng yếu tố **đã đăng ký** và rule step-up | Credential mới verified, không trùng | Notification tới kênh cũ, audit, review sessions |
| Đổi TOTP khi còn TOTP cũ | Fresh MFA cũ hoặc passkey đủ assurance | TOTP mới verified; thay thế atomic | Revoke secret cũ, regenerate recovery codes theo policy |
| Xóa factor không phải cuối cùng | Fresh MFA/step-up đủ mạnh | Còn ít nhất một phương thức bảo đảm yêu cầu và recovery hợp lệ | Revoke credential, notification, audit/session invalidation |
| Xóa **yếu tố cuối cùng** | Chính sách riêng nghiêm ngặt; nhiều ứng dụng **không cho phép** | Không được âm thầm hạ MFA toàn tài khoản | Từ chối hoặc chuyển workflow recovery/administrative |
| Regenerate recovery codes | Fresh MFA, không chỉ session | Bộ mới commit atomically, bộ cũ vô hiệu | Show-once, notify, audit |
| Đổi email/số điện thoại dùng cho recovery | Fresh MFA với yếu tố **trước thay đổi**, xác minh contact mới, risk/delay | Contact mới verified, có thể cần cooling period | Thông báo tới contact **cũ**, không chỉ contact mới |
| Mất tất cả yếu tố | Saved recovery code còn hợp lệ hoặc proofing độc lập | Recovery flow có quyền hẹp, approval và rủi ro được chấp nhận | Rebind yếu tố, revoke sessions/codes cũ, notify |
| Nghi ngờ chiếm quyền | Quy trình khôi phục/incident | Đóng băng thay đổi nhạy cảm khi cần | Revoke token, session, device, credential nghi ngờ |

**Ví dụ về lỗi nghiêm trọng:** người dùng đổi số điện thoại nhận OTP; API chỉ gửi mã về **số mới** rồi cho phép xóa số cũ. Kẻ tấn công chiếm session có thể nhập số của mình, xác minh số mới và thay yếu tố. Phải yêu cầu bằng chứng độc lập từ yếu tố **đã tồn tại** hoặc recovery flow đủ mạnh trước khi chấp nhận thay đổi.

### Quy trình thay thế an toàn (đã có yếu tố cũ)

1. User chọn **Add/Replace** từ phiên đã xác thực, server quyết định loại thao tác và yếu tố được phép thay; yêu cầu step-up vừa thực hiện bằng factor đã đăng ký, không chỉ “nhập lại username”.
2. Server tạo `pending_change_id` ngẫu nhiên, gắn `user_id`, `old_factor_id`, type, request/session, `factor_version` và expiry; không chỉ tin ID do client gửi.
3. User thực hiện ceremony trên yếu tố mới (WebAuthn registration hoặc TOTP proof). Server verify và đánh dấu `PENDING_VERIFIED`, nhưng **chưa revoke yếu tố cũ**.
4. Trong một transaction, kiểm tra lại quyền thao tác, factor_version chưa đổi, old factor vẫn thuộc user, new factor verified, policy không khóa user ngoài ý muốn. Commit new ACTIVE, old REVOKED nếu là replace, tăng factor_version.
5. Gửi notification tới kênh đã xác minh **trước đó**, ghi audit metadata, rà soát/invalidate sessions và refresh tokens đang có theo risk. User thấy danh sách yếu tố cập nhật.
6. Nếu timeout/race/mất kết nối, không để state dở dang khiến cả hai yếu tố bị vô hiệu. Có cơ chế retry/idempotency và cleanup pending.

**Cơ chế khóa phiên/step-up:** khi factor_version tăng, mọi bằng chứng "đã xác thực đủ MFA" từ phiên cũ cần được đánh giá lại. Ví dụ middleware so sánh session.factorVersion với user.factorVersion; mismatch → yêu cầu đăng nhập/step-up mới. Không cho user dùng SecurityContext cũ từ node khác như thể chưa có thay đổi.

### Nếu mất yếu tố cũ thì sao?

Đó là **account recovery**, không phải normal factor change. Không cho phép user gọi API replace bình thường bằng password đơn lẻ nếu trước đây account có MFA. Sử dụng recovery code còn hợp lệ và một bằng chứng bổ sung nếu policy yêu cầu; hoặc quy trình proofing độc lập, thời gian chờ, kênh thông báo cũ, support review có audit và chống social engineering. Sau recovery, **đánh giá thu hồi toàn bộ session/credential nghi ngờ**.

Không thể chỉ lấy việc “email inbox thuộc người yêu cầu” là bằng chứng đủ để thay mọi factor nếu email ấy cũng có thể được truy cập từ thiết bị đang bị chiếm.

## 7. Tích hợp Spring Security 7.1.x: quyền truy cập quản lý yếu tố khác quyền xem hồ sơ

Spring Security **7.x** có `FactorGrantedAuthority` để biểu diễn phương thức vừa được dùng trong Authentication. Ví dụ chuẩn gồm `FactorGrantedAuthority.PASSWORD_AUTHORITY`, `OTT_AUTHORITY` và `WEBAUTHN_AUTHORITY`. Dùng `AuthorizationManagerFactories.multiFactor()` để yêu cầu nhiều factor ở một số route, thay vì bắt mọi request đều MFA.

> **Giới hạn phiên bản:** `FactorGrantedAuthority`, `AuthorizationManagerFactories.multiFactor()` và `@EnableMultiFactorAuthentication` được giới thiệu ở **Spring Security 7.0**. **Không chép snippet này vào Spring Security 6.x**; dự án 6.x cần xây cơ chế step-up, bảo đảm Authentication và authorization bằng các API thực sự có trong phiên bản đó hoặc nâng cấp tương thích.

Ví dụ bên dưới là **cấu hình Servlet cần ghép vào ứng dụng Spring Security 7.1.x**. Nó không phải ứng dụng độc lập (cần user service, delivery OTT, controllers, bean quản lý factor, CSRF và state phù hợp). Giả sử user đã có password + OTT và cần cả hai khi đổi yếu tố; bootstrap ban đầu có riêng phương thức xác thực mạnh và policy chặt ở service layer.

```java
package example;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMultiFactorAuthentication(authorities = {})
class FactorManagementSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        var mfaForChange =
            AuthorizationManagerFactories.multiFactor()
                .requireFactors(
                    FactorGrantedAuthority.PASSWORD_AUTHORITY,
                    FactorGrantedAuthority.OTT_AUTHORITY)
                .build();

        var recentPasswordForBootstrap =
            AuthorizationManagerFactories.multiFactor()
                .requireFactor(f -> f
                    .passwordAuthority()
                    .validDuration(Duration.ofMinutes(10)))
                .build();

        return http
            .authorizeHttpRequests(auth -> auth
                // Service MUST additionally verify:
                // - user currently has no enrolled 2nd factor,
                // - account/risk/bootstrap permission.
                .requestMatchers("/security/factors/bootstrap/**")
                    .access(recentPasswordForBootstrap.authenticated())

                // Change/delete/rotate after enrollment:
                // these routes require password + OTT.
                .requestMatchers("/security/factors/manage/**")
                    .access(mfaForChange.authenticated())

                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
    }
}
```

Lưu ý:

- `@EnableMultiFactorAuthentication(authorities = {})` kích hoạt hỗ trợ MFA nhưng **không bắt toàn bộ route** phải MFA, để có thể yêu cầu từng nhóm route.
- `mfaForChange.authenticated()` yêu cầu `FACTOR_PASSWORD` và `FACTOR_OTT` từ cơ chế login thực. Không tự thêm các chuỗi authority này cho request chưa hoàn tất factor.
- `recentPasswordForBootstrap` **chỉ** ví dụ kiểm tra yếu tố password trong 10 phút; với account đã có MFA, bootstrap route phải bị **từ chối ở service layer**. Nếu không, attacker có mật khẩu và session vẫn có thể vào đường bootstrap yếu. App rủi ro cao có thể yêu cầu proofing, invitation/challenge hoặc factor khác ngay cả khi chưa có yếu tố thứ hai.
- Khi đã enroll, thay/gỡ factor nên yêu cầu **fresh step-up** theo từng yêu cầu, không chỉ sự hiện diện của authority lâu ngày. Có thể dùng `validDuration(...)` cho các factor cụ thể và kiểm tra `factor_version` / `reauth_at` ở app layer. Vì vậy snippet không thay một policy re-auth đầy đủ.
- Dùng OTT email như một yếu tố thứ hai trong demo có thể yếu hơn passkey/hardware key và **không phishing-resistant**. Chọn factor đáp ứng assurance và rủi ro thực tế.
- Các route recovery khi user mất factor không được giả vờ đã có `FACTOR_OTT`; thiết kế **security chain/recovery state tách biệt, hẹp quyền**, chống vòng lại bootstrap.
- Với WebAuthn, dùng `spring-security-webauthn`, lưu credential trong repository production. Khi đổi/gỡ key vẫn phải có flow re-auth, CSRF và ghi trạng thái tài khoản.

**Cấu hình route không thể tự chứng minh account record đúng.** Controller/service xử lý yêu cầu thay factor vẫn phải đọc `Authentication.getName()`/user ID server-side, kiểm tra quyền sở hữu factor ID, current factor version và transaction. Không tin `userId` trong JSON body để thay MFA của người khác.

### Pseudocode ở service layer cho thao tác replace

```text
replaceFactor(actorAuthentication, oldFactorId, pendingNewFactorId):
    account = resolveUserFromTrustedAuthentication(actorAuthentication)
    requireFreshExistingFactor(account, actorAuthentication)
    requireNotRecoveryLimitedSession(actorAuthentication)
    transaction:
        lock account and factor records
        require currentFactorVersion == pending.factorVersion
        require oldFactor.userId == account.id && oldFactor.ACTIVE
        require pending.userId == account.id && pending.VERIFIED
        require account policy allows removing this factor
        activate pending new factor
        revoke old factor
        bump account.factorVersion
        commit
    notify old verified channels, audit metadata without secrets
    revoke or re-evaluate existing sessions and long-lived tokens
```

Pseudocode **không phải mã Java chạy độc lập**; trình tự xử lý race và transaction tùy database/domain. Notification/outbox nên gắn với transaction để tránh “đã đổi factor nhưng không gửi được cảnh báo”.

## 8. Kiểm thử: không chỉ thấy màn hình thành công

| Trường hợp | Cấu hình đầu vào | Kết quả mong muốn |
| --- | --- | --- |
| Enroll TOTP mới | Password+MFA cũ vừa xác thực; nhập mã TOTP mới đúng | PENDING → ACTIVE, secret không lộ trong response ngoài ceremony |
| Chỉ mở QR rồi bỏ dở | Chưa nhập mã verify | Factor vẫn PENDING, không cho login bằng nó |
| Enroll WebAuthn origin sai | Challenge hợp lệ nhưng origin/RP ID không đúng | Từ chối, không lưu credential |
| Enroll trùng credential | Credential ID đã thuộc account khác | Từ chối hoặc policy collision an toàn, không chiếm key |
| Đổi factor bằng cookie cũ | Session vẫn authenticated nhưng chưa step-up mới | 403/redirect step-up, không thay dữ liệu |
| Bootstrap khi account đã có MFA | Password đúng nhưng đã enroll yếu tố | Từ chối bootstrap, không bypass policy |
| Thay TOTP thành công | Old factor verified, new proof hợp lệ | New ACTIVE + old REVOKED atomic, tăng factor_version |
| Lỗi trước commit | Pending đã verified nhưng DB lỗi | Giữ old ACTIVE, không khóa tài khoản |
| Thử xóa yếu tố cuối | User chỉ còn một factor bắt buộc | Từ chối hoặc recovery process có kiểm soát |
| Hai request thay factor | Cùng factor_version / cùng oldFactorId | Không cùng commit; một request bị conflict |
| Sinh recovery codes | Fresh MFA | Show once, DB chỉ giữ hash, thông báo an toàn |
| Regenerate codes | Bộ cũ chưa dùng hết | Mọi mã cũ bị revoke; mã mới hợp lệ |
| Redeem cùng code hai lần | 2 POST đồng thời vào shared DB | Chỉ một transaction thành công |
| Code của Alice dùng cho Bob | Đúng raw code, sai user | Từ chối |
| Thử code liên tiếp | Nhiều lần sai trong cửa sổ ngắn | Throttle/rate-limit và alert theo risk |
| User mất mọi yếu tố | Không có backup code | Chỉ đi vào recovery proofing; không có bypass bằng email mới |
| Thay đổi factor xong | Session cũ khác thiết bị/node | Bị invalidated/step-up lại theo policy |
| Notification tới contact cũ | Attacker đổi email/số mới | Contact đã đăng ký trước nhận cảnh báo |
| User bị khóa tài khoản | Có recovery code đúng | Vẫn áp account/risk policy, không mở khóa vô điều kiện |

### JUnit test cho chương trình Java thuần

Bạn có thể chuyển các điều kiện của `RecoveryCodeDemo.main` thành JUnit assertions. Với JUnit Jupiter và test source nằm trong cùng project:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RecoveryCodeDemoTest {
    @Test
    void oneUseAndAccountBinding() {
        RecoveryCodeDemo store = new RecoveryCodeDemo();
        var codes = store.issue("alice", 2);
        assertTrue(store.consume("alice", codes.get(0)));
        assertFalse(store.consume("alice", codes.get(0)));
        assertFalse(store.consume("bob", codes.get(1)));
    }

    @Test
    void rotationInvalidatesUnusedOldCodes() {
        RecoveryCodeDemo store = new RecoveryCodeDemo();
        var old = store.issue("alice", 2);
        var fresh = store.issue("alice", 2);
        assertFalse(store.consume("alice", old.get(1)));
        assertTrue(store.consume("alice", fresh.get(0)));
    }
}
```

Đây là test JUnit cho **demo in-memory**, cần dependency JUnit 5, không phải test Spring Security hay database. Nó không chứng minh atomic consume giữa các node, CSRF, permission check hay login recovery. Test thực tế cần `MockMvc`/integration với session/cookies, database transactions và email sender giả, rồi thử các tình huống race.

## 9. Lỗi phổ biến cần tránh

1. **Xem trang MFA Settings như CRUD thường:** attacker dùng session cũ thêm factor mới. Bắt fresh re-auth bằng factor trước đó.
2. **Đánh dấu TOTP ACTIVE khi chỉ hiện QR:** user chưa chứng minh possession; chỉ ACTIVE sau mã verify.
3. **Cho phép xóa yếu tố cuối không có recovery:** tự hạ assurance và khóa user hoặc mở bypass.
4. **Dùng password+PIN như MFA:** cả hai là yếu tố “biết”, không độc lập.
5. **Email mới tự xác minh bằng OTP mới là đủ để đổi MFA:** attacker đã thay email thì tự nhận OTP. Cần bằng chứng từ factor/kênh trước thay đổi.
6. **Lưu recovery codes plaintext hoặc gửi qua email:** tạo kho credential dễ lộ. Dùng CSPRNG và hash, phát một lần qua kênh bảo vệ, khuyến nghị offline.
7. **Code quá ngắn, không throttle:** brute-force, đặc biệt nếu DB bị lộ. Chọn entropy cao; code thấp entropy phải có KDF và rate limits.
8. **Consume không atomic:** hai request dùng cùng code cùng thành công. Dùng transaction/conditional update trên DB.
9. **Regenerate nhưng bộ mã cũ vẫn active:** attacker giữ ảnh chụp mã cũ có cửa sau. Rotate toàn bộ set.
10. **Không cập nhật session sau thay factor:** credential cũ hoặc SecurityContext cũ còn quyền. Tăng factor_version, revoke hoặc yêu cầu step-up.
11. **Tự thêm `FACTOR_WEBAUTHN` vào Authentication sau recovery:** biến mã recovery thành bằng chứng passkey giả. Giữ recovery state quyền hẹp.
12. **Không gửi notification qua kênh đã biết:** attacker có thể thay yếu tố im lặng, chủ tài khoản không nhận ra.
13. **Đồng nhất passkey với TOTP:** WebAuthn ràng buộc origin/RP ID, TOTP có thể bị phishing; assurance khác nhau.
14. **Chỉ thử unit test in-memory:** không bắt được lỗi transaction, rollout multi-node, stale sessions hay email delivery.

## 10. Checklist khi triển khai

- [ ] Có inventory các yếu tố theo user với trạng thái PENDING/ACTIVE/REVOKED, timestamps, stable ID và factor_version.
- [ ] Enroll cần step-up đủ mới; lần đầu khác thay/gỡ sau khi đã có MFA.
- [ ] Verification của yếu tố mới hoàn tất trước commit; WebAuthn dùng verifier/library tin cậy, TOTP giữ secret bảo mật.
- [ ] Recovery codes được sinh bằng CSPRNG đủ entropy, chỉ hiển thị một lần, hash at rest, throttle và consume atomic.
- [ ] Regenerate/recovery làm mất hiệu lực code cũ, có notification và bảo vệ kênh giao mã.
- [ ] Thay/yêu cầu gỡ cần fresh existing factor; không dựa chỉ vào session hay địa chỉ email mới.
- [ ] Khi mất mọi yếu tố có recovery proofing phù hợp và audit; không lén hạ assurance bằng API bootstrap.
- [ ] Thay yếu tố có atomic transaction, chống race, thông báo contact cũ, quản lý phiên và refresh token.
- [ ] CSRF, rate limiting, logging redaction, tenant/object ownership checks áp dụng cho toàn bộ endpoint factor management.
- [ ] Unit/integration/concurrency/security tests xác nhận tất cả những điểm trên.

**Kết luận:** MFA chỉ bảo vệ tài khoản nếu cả **quy trình tạo và thay đổi authenticator** cũng đòi bằng chứng tin cậy. Saved recovery codes phải là secret entropy cao, single-use và được thu hồi đúng; quy trình thay factor phải re-auth bằng yếu tố hiện có, kiểm chứng yếu tố mới, commit atomic và xử lý session cũ. Spring Security cung cấp cấu phần authentication/authorization và WebAuthn, còn **đăng ký từng loại factor, recovery workflow và policy đổi yếu tố** là trách nhiệm kiến trúc của ứng dụng.

## 11. Tài liệu tham khảo

- Spring Security 7.x — Multi-Factor Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html
- Spring Security 7.x — Passkeys/WebAuthn registration: https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html
- Spring Security — `FactorGrantedAuthority` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html
- Spring Security — `EnableMultiFactorAuthentication` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html
- NIST SP 800-63B-4 (2025) — Authenticator Binding & Account Recovery: https://pages.nist.gov/800-63-4/sp800-63b/events/
- NIST SP 800-63B-4 — Look-Up Secrets: https://pages.nist.gov/800-63-4/sp800-63b/authenticators/
- OWASP — Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- RFC 6238 — TOTP: https://www.rfc-editor.org/rfc/rfc6238
