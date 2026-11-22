# Token xác minh liên hệ: mục đích, thời hạn và sử dụng một lần

## 1. Mục tiêu và ngữ cảnh vòng đời tài khoản

Khi một người đăng ký tài khoản hoặc yêu cầu đổi email/số điện thoại, ứng dụng phải phân biệt **thông tin liên hệ được khai báo** với **thông tin liên hệ đã được chứng minh có quyền truy cập**. Nhập `alice@example.org` vào form không chứng minh người nhập kiểm soát hộp thư này. Một quy trình phổ biến là phát hành **contact verification token** và gửi nó qua kênh cần xác minh; người nhận trình lại token để hệ thống ghi nhận việc kiểm soát kênh đó.

Một token xác minh liên hệ an toàn phải đáp ứng **ba ràng buộc đồng thời**:

1. **Đúng mục đích (purpose-bound):** token phát hành để `VERIFY_EMAIL` không được dùng cho `RESET_PASSWORD`, `CHANGE_EMAIL`, thêm MFA, đăng nhập hay hành động quản trị khác.
2. **Có thời hạn (time-limited):** token chỉ hợp lệ trước `expires_at`. Sau thời điểm đó, dù chuỗi token không bị sửa, yêu cầu phải bị từ chối.
3. **Dùng một lần (single-use):** sau lần **xác minh thành công**, cùng token không thể kích hoạt thêm lần nào, kể cả có hai request tới nhiều instance cùng lúc.

Ngoài ra token phải đủ ngẫu nhiên để không đoán được, liên kết đúng **tài khoản + liên hệ đích**, được gửi đúng kênh, không bị lộ trong log và được kiểm tra nguyên tử với thay đổi trạng thái tài khoản.

**Đây không phải access token đăng nhập.** Xác minh quyền truy cập email/số điện thoại không tự động chứng minh danh tính pháp lý, không tương đương xác thực đa yếu tố và không được cấp phiên đăng nhập hoặc quyền admin một cách ngầm định.

### Kết quả học tập

Sau bài này, bạn có thể:
- Phân biệt email/phone verification với password reset, login token và session.
- Thiết kế schema token với `purpose`, `subject`, `target_contact`, `expires_at`, `consumed_at`.
- Sinh token đủ entropy bằng `SecureRandom`, chỉ lưu digest của token.
- Xác minh thời hạn, trạng thái, liên hệ đích và tiêu thụ token **trong transaction**.
- Tích hợp trạng thái `email_verified` / `enabled` với Spring Security một cách có kiểm soát.
- Xử lý resend, thay liên hệ, email link scanner, enumeration, race condition, revocation và kiểm thử bảo mật.

## 2. Phân biệt trạng thái liên hệ và trạng thái xác thực tài khoản

Một account có thể có email nhưng chưa được xác minh:

~~~text
Tài khoản mới
    |
    v
PENDING_EMAIL_VERIFICATION
    |  gửi link đến email cần xác minh
    |  chỉ chấp nhận token hợp lệ
    v
EMAIL_VERIFIED
    |  theo chính sách sản phẩm
    v
ACTIVE

Đổi email:
ACTIVE(oldEmail đã verified)
    |
    v
PENDING_EMAIL_CHANGE(newEmail chưa verified)
    |
    +-- token gửi tới newEmail, email hiện tại giữ nguyên
    |
    v
NEW_EMAIL_VERIFIED
    |
    v
ACTIVE(email mới được áp dụng theo policy)
~~~

Có hai lựa chọn phổ biến:
- **Khóa toàn bộ đăng nhập** đến khi email được xác minh: account `enabled=false` hoặc `status=PENDING` trong nguồn `UserDetailsService`.
- **Cho truy cập hạn chế khi chưa xác minh:** chỉ mở các thao tác đủ an toàn, chưa cho sử dụng chức năng nhạy cảm; authorization cần kiểm tra cờ xác minh đúng mức.

Cả hai đều cần định nghĩa rõ chính sách. Không được coi `email_verified_at` là tương đương `isAuthenticated()` của một request. `isAuthenticated()` nói về principal/phiên đang gửi request; `email_verified_at` nói về **bằng chứng một kênh liên hệ** tại thời điểm đã xác minh.

**Đổi email khác đăng ký mới:** với account đã active, email cũ nên được giữ là địa chỉ chính cho đến khi hoàn tất xác minh email mới; yêu cầu đổi thường cần reauthentication/step-up và thông báo đến email cũ.

## 3. "Mục đích" phải được kiểm tra ở server

### 3.1. Token là capability có phạm vi hành động

Ví dụ các mục đích cần phân biệt:

| Purpose | Hành động sau khi token được chấp nhận | Có được dùng thay thế nhau? |
|---|---|---|
| `VERIFY_SIGNUP_EMAIL` | Xác minh email cho account đang chờ kích hoạt | Không |
| `VERIFY_NEW_EMAIL` | Xác minh email mới của account đã tồn tại | Không |
| `VERIFY_PHONE` | Ghi nhận số điện thoại đang được kiểm soát | Không |
| `RESET_PASSWORD` | Cho phép quy trình đặt password mới | Không |
| `CONFIRM_SENSITIVE_ACTION` | Cho phép hành động được ràng buộc cụ thể | Không |
| `MAGIC_LOGIN` | Xác thực phiên nếu product chủ động thiết kế magic link | Không |

**Token chỉ cấp đúng quyền đã thiết kế khi phát hành.** Một link xác minh email tuyệt đối không được mang đặc quyền reset password chỉ vì hai loại link cùng gửi qua email.

### 3.2. Server không tin mục đích do client tự đổi

Giả sử token lưu trong DB:

~~~json
{
  "accountId": 42,
  "purpose": "VERIFY_SIGNUP_EMAIL",
  "targetEmail": "alice@example.org",
  "expiresAt": "2030-01-01T10:15:00Z",
  "consumedAt": null
}
~~~

Client tự sửa `purpose=RESET_PASSWORD` trên query/body không thể thay tác dụng của token. Handler password reset phải tìm **bản ghi server-side có purpose RESET_PASSWORD**, không tìm bất kỳ token nào có cùng chuỗi.

Một bản ghi token được liên kết với ít nhất:
- **Subject:** account ID bất biến, không chỉ email;
- **Destination:** địa chỉ liên hệ đang cần chứng minh;
- **Purpose:** hành động duy nhất được phép;
- **Lifecycle:** issued, expiry, consumed/revoked;
- **Context:** tenant/app/channel hoặc phiên thay đổi liên hệ nếu cần.

Với ứng dụng multi-tenant, cùng một email có thể xuất hiện ở những tenant khác nhau. Vì vậy key cần ràng buộc cả `tenant_id` hoặc account namespace nếu sản phẩm dùng.

## 4. Token ngẫu nhiên, định dạng và cách lưu trữ

### 4.1. Sinh token không thể đoán

Với **verification link gửi email**, có thể dùng 32 byte từ `SecureRandom` (256 bit), rồi Base64URL không padding thành 43 ký tự:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

SecureRandom rng = new SecureRandom();
byte[] bytes = new byte[32];
rng.nextBytes(bytes);
String rawToken = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(bytes);
~~~

Đây là **đoạn minh họa** đặt trong class/method Java, không phải file độc lập vì thiếu khai báo class. Mỗi lần gọi phải sinh bytes mới, không ghép từ timestamp, email, UUID rút ngắn, `Math.random()` hay mã tăng dần.

32 byte ngẫu nhiên từ CSPRNG có không gian tìm kiếm rất lớn. Quy tắc “đủ entropy” quan trọng hơn việc làm chuỗi dài để nhìn có vẻ phức tạp. Không cần đặt account ID hoặc email vào raw token; metadata nằm ở server.

### 4.2. Chỉ lưu digest, không lưu raw token

Luồng hợp lý:

~~~text
Issue:
    rawToken = SecureRandom(32 bytes) → Base64URL
    tokenDigest = SHA-256(rawToken)
    DB chỉ lưu tokenDigest + purpose + account + target + expiry
    gửi rawToken vào email đích

Redeem:
    nhận rawToken
    tokenDigest = SHA-256(rawToken)
    lookup digest trong DB
    verify purpose/account/target/expiry/unused
    chuyển trạng thái trong transaction
~~~

Ví dụ lưu `token_digest_hex` dưới dạng 64 ký tự hex. Vì raw token có **256 bit entropy ngẫu nhiên**, SHA-256 đơn giản dùng để lookup ở ví dụ này là hợp lý. Nếu bạn gửi **OTP ngắn 6 chữ số**, entropy thấp hơn rất nhiều: không thể coi SHA-256 trần đủ chống dò ngoại tuyến khi DB lộ. Với OTP cần thêm rate limit chặt, attempt cap, TTL rất ngắn, phương án lưu bằng HMAC với server-side key/pepper hoặc giải pháp OTP chuyên dụng theo mô hình rủi ro.

**Không nhầm hash token với hash password.** Password do người dùng đặt có entropy thấp; nó cần thuật toán password hashing có work factor như Argon2id/bcrypt/PBKDF2. Một random token 256 bit không cần đối xử y hệt password nếu mục tiêu là tránh lưu plaintext.

### 4.3. Token ID có cần tách riêng không?

Có thể dùng định dạng `tokenId.secret`, DB index theo `tokenId` và chỉ kiểm tra secret digest ở bản ghi đó; hoặc dùng digest của toàn bộ random token làm lookup key. Hai cách đều hợp lý nếu định nghĩa rõ:
- `tokenId` là định danh để tra cứu, **không phải credential**;
- `secret`/raw token là bí mật cần bảo vệ;
- token được kiểm tra bằng đúng purpose/destination/account đã lưu;
- response không lộ token tồn tại hay không.

Ví dụ cuối bài chọn **lookup bằng SHA-256 của raw token 43 ký tự**, tránh phải xử lý hai thành phần.

## 5. Thời hạn: token còn hiệu lực đến khi nào?

### 5.1. Quy tắc chính xác

Với `issued_at = T0`, `expires_at = T0 + TTL`, tại thời điểm `now`:

~~~text
Valid if:
    now < expires_at
    AND consumed_at IS NULL
    AND revoked_at IS NULL (nếu có)
    AND purpose/account/target đúng

Invalid if:
    now >= expires_at
    OR token đã tiêu thụ/thu hồi
    OR trạng thái account/target không còn phù hợp
~~~

**Đúng tại `expires_at` phải từ chối.** Một số hệ thống cho phép clock skew nhỏ với token phân tán, nhưng phải xác định rõ policy; không tự kéo dài TTL không kiểm soát.

### 5.2. TTL nên đặt như thế nào?

Không có TTL cố định phù hợp mọi sản phẩm. Ví dụ chính sách *tham khảo* (không phải chuẩn bắt buộc):

| Loại xác minh | TTL minh họa | Lý do |
|---|---:|---|
| Link xác minh email đăng ký | 15–60 phút | Cân bằng thời gian mở email và cửa sổ lộ link |
| Link xác minh email mới | 10–30 phút | Rủi ro thay đổi danh tính/liên hệ cao hơn |
| Mã OTP SMS 6 chữ số | 3–10 phút | Mã ngắn cần giảm thời gian thử |
| Xác nhận hành động nhạy cảm | 5–15 phút | Giảm khả năng dùng link cũ |

Tổ chức phải chọn thời hạn theo rủi ro, độ trễ email/SMS, UX, quy định nội bộ và kiểm soát rate limit. TTL dài hơn không tự an toàn vì token có nhiều entropy: nếu link bị lộ, attacker có thể **dùng token thật**, không cần brute force.

### 5.3. Dùng thời gian server/DB đáng tin

- Trong Java, ưu tiên `Instant` và injectable `Clock` thay vì thao tác thời gian theo múi giờ của browser.
- Với nhiều instance, đồng bộ NTP; trong câu lệnh SQL chọn `CURRENT_TIMESTAMP`/DB clock nhất quán.
- Không lấy `expiresAt` từ request do client tự gửi.
- Không cộng TTL lại mỗi khi user refresh trang verification.
- Resend tạo **token mới**, có quy tắc vô hiệu hóa/cắt hạn token cũ.

Nếu email đến chậm, không “gia hạn” raw token đã phát hành bằng cách sửa token client; cung cấp quy trình resend có rate limit và timestamp mới.

## 6. "Dùng một lần" phải được bảo đảm nguyên tử

### 6.1. Vì sao chỉ gọi `find` rồi `save` là chưa đủ?

Hai request gần như đồng thời có thể xảy ra:

~~~text
Instance A                         Instance B
  SELECT token unused                SELECT token unused
  → thấy chưa dùng                   → thấy chưa dùng

  UPDATE user verified               UPDATE user verified
  UPDATE token consumed              UPDATE token consumed

  → cả A và B đều cho rằng mình đã sử dụng token thành công
~~~

Nếu token cho phép hành động quan trọng hơn (đổi email, cấp quyền hoặc xác nhận giao dịch), việc xử lý hai lần có thể tạo side effect trùng lặp hoặc an ninh sai.

**Một lần** không có nghĩa “xóa token ở client sau khi click” hay “đặt cờ sau khi đã hoàn tất”. Nó có nghĩa **tại server, tối đa một request được phép hoàn tất state transition**.

### 6.2. Cơ chế an toàn trong database

Có hai mẫu phổ biến:
- **Transaction + `SELECT ... FOR UPDATE`:** khóa bản ghi token cho tới commit; kiểm tra chưa dùng và chưa hết hạn rồi cập nhật account + token trong cùng transaction.
- **Compare-and-set (`UPDATE ... WHERE consumed_at IS NULL ... RETURNING`):** chỉ một request giành quyền tiêu thụ. Các thay đổi account và token phải ở **cùng transaction** nếu muốn tránh tiêu thụ nhưng chưa cập nhật account.

Đối với email xác minh, transaction cần giữ nguyên tắc:

~~~text
BEGIN TRANSACTION
    lookup/lock token còn hợp lệ
    confirm đúng purpose, account, destination
    confirm account vẫn ở trạng thái chờ đúng contact
    update account.email_verified_at/status
    update token.consumed_at
    invalidate related pending verification tokens if required
COMMIT

Nếu bất kỳ bước nào fail:
    ROLLBACK
    không có trạng thái nửa vời
~~~

**Trình tự hoặc transaction boundary thiếu đúng là lỗi nghiệp vụ.** Ví dụ đánh dấu token đã dùng, commit, rồi gửi request update account vào hệ thống khác có thể dẫn đến token mất quyền sử dụng nhưng account chưa verified. Với hệ phân tán, cần cơ chế outbox/saga/idempotency được thiết kế riêng.

### 6.3. Replay sau khi thành công

Lần dùng đầu hợp lệ cập nhật account và token; các lần tiếp theo nhận một thông báo chung như “Liên kết không hợp lệ hoặc đã hết hạn”. Không cần tiết lộ token đã được dùng hay tài khoản nào. Nếu UX yêu cầu idempotent response “đã xác minh”, chỉ có thể làm vậy sau khi kiểm tra account hiện tại **một cách không làm lộ thông tin**; không thực hiện lại tác vụ nhạy cảm.

## 7. Liên kết token với liên hệ đích (target binding)

Một số lỗi không nằm ở việc đoán token mà ở **liên kết token sai dữ liệu**.

### 7.1. Account ID khác email string

Token cần gắn với một account ổn định (`account_id`) và với **địa chỉ đang chờ xác minh**. Không dùng mỗi email để xác định account vì:
- email có thể bị sửa sau khi token được gửi;
- email có thể trùng ở tenant khác, hoặc bị tái sử dụng theo vòng đời nhà cung cấp;
- dữ liệu email cần chính sách canonicalization nhất quán;
- attacker có thể dùng việc đổi email giữa issuance và redeem để xác minh nhầm địa chỉ mới.

Ví dụ:

~~~text
T0: account 42 pendingEmail = alice@example.org
T1: phát hành token X cho account 42 + alice@example.org
T2: account 42 đổi pendingEmail = mallory@example.org
T3: click token X cũ

ĐÚNG: từ chối X vì target trong token khác contact đang chờ.
SAI: đánh dấu account 42 emailVerified=true bất kể email hiện tại.
~~~

### 7.2. Xác minh email mới không thể tái dùng token cũ

Khi đổi email:
1. Người dùng đã đăng nhập cần reauthenticate/step-up theo rủi ro.
2. Lưu `pending_email` **chưa dùng làm email đăng nhập/chính thức**.
3. Phát hành token `VERIFY_NEW_EMAIL` cho **pending_email** và account hiện hành.
4. Gửi thông báo đến email cũ; cân nhắc quy trình xác nhận thêm từ email cũ cho hệ thống rủi ro cao.
5. Khi token hợp lệ, trong transaction đảm bảo `pending_email` còn đúng, cập nhật email và trạng thái đã verified theo policy.
6. Vô hiệu hóa các token của thay đổi cũ, cập nhật login identifier/session nếu cần và gửi thông báo.

Không được dùng `VERIFY_SIGNUP_EMAIL` làm `VERIFY_NEW_EMAIL` chỉ vì đều có `purpose=email`. Scope của hành động phải đủ cụ thể để tránh cross-flow reuse.

### 7.3. Chuẩn hóa email cẩn thận

OWASP khuyên định nghĩa chính sách canonicalization thống nhất. Domain thường không phân biệt hoa/thường; local part có quy tắc phức tạp hơn. Không tự xóa dấu chấm hoặc dấu `+` trong Gmail cho mọi provider; không tự lower-case local part nếu có thể gây nhập nhằng/chồng tài khoản. Lưu cả giá trị gốc để hiển thị và giá trị chuẩn hóa theo chính sách để so sánh, bảo đảm quy tắc giống nhau ở signup, login, recovery và contact verification.

## 8. Một token xác minh nên lưu những gì?

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE app_accounts (
    id                 BIGINT PRIMARY KEY,
    email_canonical    VARCHAR(320) NOT NULL,
    email_verified_at  TIMESTAMPTZ,
    status             VARCHAR(24) NOT NULL
                       CHECK (status IN ('PENDING', 'ACTIVE', 'DISABLED'))
);

CREATE TABLE contact_verification_tokens (
    id                 BIGSERIAL PRIMARY KEY,
    token_digest_hex   CHAR(64) NOT NULL UNIQUE,
    account_id         BIGINT NOT NULL
                       REFERENCES app_accounts(id),
    purpose            VARCHAR(40) NOT NULL,
    target_contact     VARCHAR(320) NOT NULL,
    issued_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at         TIMESTAMPTZ NOT NULL,
    consumed_at        TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    CONSTRAINT chk_contact_token_expires
        CHECK (expires_at > issued_at)
);

CREATE INDEX idx_contact_tokens_account_purpose
    ON contact_verification_tokens(account_id, purpose);
~~~

Đây là schema **minh họa**, không phải bảng do Spring Security tự tạo. Production cần migrations, transaction/index, ownership/tenant, chính sách xóa dữ liệu cá nhân, trạng thái liên hệ hiện tại, constraint duy nhất của email nếu business yêu cầu, và lịch dọn bản ghi cũ.

Trường dữ liệu quan trọng:
- `token_digest_hex`: digest của raw token ngẫu nhiên, không phải raw token;
- `purpose`: đúng hành động, không tự sinh quyền;
- `account_id`: account cụ thể, tránh liên kết chỉ bằng email;
- `target_contact`: giá trị liên hệ cần chứng minh;
- `issued_at`/`expires_at`: giới hạn thời gian;
- `consumed_at`: chứng minh token đã được xử lý một lần;
- `revoked_at`: rút lại token khi đổi contact, resend, phát hiện bất thường, xóa account.

**SQL phải kiểm tra tất cả điều kiện hợp lệ**; một token có `consumed_at IS NULL` vẫn bị từ chối nếu `revoked_at` khác NULL, expires hoặc account không còn đúng trạng thái.

## 9. Demo Java 17 độc lập: purpose, TTL và single-use

Ví dụ sau chạy **không cần Spring**, tập trung vào logic in-memory để thấy ranh giới. Nó tạo raw token 256 bit, chỉ lưu SHA-256 digest, gắn token với account/target/purpose/expiry và sử dụng `ConcurrentHashMap.computeIfPresent` để chặn hai lần tiêu thụ cùng key trong **một JVM**.

**Giới hạn:** bộ nhớ một JVM không phải database transaction. Demo **không gửi email thật**, không thay đổi user trong DB và không bảo đảm cross-instance hoặc cập nhật account nguyên tử. Phần 10 trình bày cách làm ở Spring/JDBC production.

File `ContactVerificationDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class ContactVerificationDemo {

    enum Purpose {
        VERIFY_SIGNUP_EMAIL,
        VERIFY_NEW_EMAIL
    }

    record Entry(
            long accountId,
            String targetEmail,
            Purpose purpose,
            Instant expiresAt) {
    }

    static final class MutableClock extends Clock {
        private final AtomicReference<Instant> current;

        MutableClock(Instant start) {
            current = new AtomicReference<>(start);
        }

        void advance(Duration duration) {
            current.updateAndGet(t -> t.plus(duration));
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            if (!ZoneOffset.UTC.equals(zone)) {
                throw new IllegalArgumentException("UTC only");
            }
            return this;
        }

        @Override
        public Instant instant() {
            return current.get();
        }
    }

    static final class TokenService {
        private final SecureRandom random = new SecureRandom();
        private final Clock clock;
        private final ConcurrentHashMap<String, Entry> rows =
                new ConcurrentHashMap<>();

        TokenService(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        String issue(
                long accountId,
                String targetEmail,
                Purpose purpose,
                Duration ttl) {

            if (accountId <= 0 || targetEmail == null
                    || targetEmail.isBlank()
                    || purpose == null || ttl == null
                    || ttl.isZero() || ttl.isNegative()) {
                throw new IllegalArgumentException("Invalid issuance");
            }

            byte[] bytes = new byte[32];
            random.nextBytes(bytes);

            String rawToken = Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(bytes);

            String digest = sha256Hex(rawToken);

            Entry entry = new Entry(
                    accountId,
                    targetEmail,
                    purpose,
                    clock.instant().plus(ttl));

            if (rows.putIfAbsent(digest, entry) != null) {
                throw new IllegalStateException("Duplicate token digest");
            }
            return rawToken;
        }

        boolean consume(
                String rawToken,
                long accountId,
                String targetEmail,
                Purpose purpose) {

            if (rawToken == null || rawToken.length() != 43
                    || !rawToken.matches("[A-Za-z0-9_-]{43}")) {
                return false;
            }

            String digest = sha256Hex(rawToken);
            AtomicBoolean accepted = new AtomicBoolean(false);

            rows.computeIfPresent(digest, (key, entry) -> {
                boolean matches = entry.accountId() == accountId
                        && entry.targetEmail().equals(targetEmail)
                        && entry.purpose() == purpose
                        && clock.instant().isBefore(entry.expiresAt());

                if (matches) {
                    accepted.set(true);
                    return null; // Remove atomically for this map key.
                }
                return entry;
            });
            return accepted.get();
        }

        private static String sha256Hex(String input) {
            try {
                byte[] bytes = input.getBytes(StandardCharsets.US_ASCII);
                byte[] hash = MessageDigest.getInstance("SHA-256")
                        .digest(bytes);
                return HexFormat.of().formatHex(hash);
            } catch (NoSuchAlgorithmException e) {
                throw new IllegalStateException("SHA-256 unavailable", e);
            }
        }
    }

    public static void main(String[] args) {
        MutableClock clock = new MutableClock(
                Instant.parse("2030-01-01T10:00:00Z"));
        TokenService service = new TokenService(clock);

        String token = service.issue(
                42, "alice@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL,
                Duration.ofMinutes(15));

        System.out.println("wrong-purpose=" + service.consume(
                token, 42, "alice@example.org",
                Purpose.VERIFY_NEW_EMAIL));
        System.out.println("wrong-target=" + service.consume(
                token, 42, "mallory@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL));
        System.out.println("first=" + service.consume(
                token, 42, "alice@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL));
        System.out.println("replay=" + service.consume(
                token, 42, "alice@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL));

        String expiring = service.issue(
                42, "alice@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL,
                Duration.ofSeconds(5));
        clock.advance(Duration.ofSeconds(5));

        System.out.println("expired=" + service.consume(
                expiring, 42, "alice@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ContactVerificationDemo.java
java ContactVerificationDemo
~~~

**Stdout chính xác:**

~~~text
wrong-purpose=false
wrong-target=false
first=true
replay=false
expired=false
~~~

Giải thích:
- Sai purpose/target **không tiêu thụ** token đúng; mục đích là từ chối cross-flow/cross-contact.
- Lần đầu đủ điều kiện trả `true`, map loại bản ghi; lần thứ hai trả `false`.
- Đúng tại `expiresAt` bị từ chối vì `Instant.isBefore` trả `false`.
- `MutableClock` chỉ dùng trong demo để kiểm tra expiry mà không phải `sleep`; trong ứng dụng thật inject `Clock.systemUTC()` hoặc lấy đồng hồ DB.
- Không in raw token, tránh lộ bí mật qua stdout.
- Logic trong map chỉ giữ **single-use nội bộ một process**. Đừng dùng làm bằng chứng đã có transaction an toàn trên nhiều server/DB.

## 10. Spring Boot 3.x + Spring Security 6.x: kiểm chứng bằng transaction

Trong ứng dụng Java/Spring thực tế, token được lưu vào database, còn `@Transactional` giúp cập nhật account và đánh dấu token đã tiêu thụ **cùng commit hoặc rollback**. Dưới đây là một ví dụ repository/service cụ thể dùng **Spring JDBC + PostgreSQL** với schema ở phần 8.

### 10.1. Dependencies

Trong `pom.xml` đã có Spring Boot 3.x parent hoặc BOM, dùng Java 17+:

~~~xml
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
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Đây là **đoạn dependency cho một project Spring Boot**, không phải file POM đầy đủ độc lập. Cần datasource PostgreSQL đã cấu hình, migration tạo bảng ở phần 8 và flow phát hành/gửi email riêng.

### 10.2. Service tiêu thụ email verification token

File `src/main/java/com/example/account/EmailVerificationService.java`:

~~~java
package com.example.account;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EmailVerificationService {

    private final JdbcTemplate jdbc;

    public EmailVerificationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    record TokenRow(
            long id,
            long accountId,
            String targetEmail) {
    }

    @Transactional
    public boolean verifySignupEmail(String rawToken) {
        if (rawToken == null ||
                !rawToken.matches("[A-Za-z0-9_-]{43}")) {
            return false;
        }

        String digest = sha256Hex(rawToken);

        // FOR UPDATE serializes use of this token row.
        List<TokenRow> rows = jdbc.query("""
                SELECT id, account_id, target_contact
                  FROM contact_verification_tokens
                 WHERE token_digest_hex = ?
                   AND purpose = 'VERIFY_SIGNUP_EMAIL'
                   AND consumed_at IS NULL
                   AND revoked_at IS NULL
                   AND expires_at > CURRENT_TIMESTAMP
                 FOR UPDATE
                """, (rs, rowNum) -> new TokenRow(
                    rs.getLong("id"),
                    rs.getLong("account_id"),
                    rs.getString("target_contact")),
                digest);

        if (rows.size() != 1) {
            return false;
        }

        TokenRow token = rows.get(0);

        // Bind confirmation to the SAME account + pending email.
        int updated = jdbc.update("""
                UPDATE app_accounts
                   SET email_verified_at = CURRENT_TIMESTAMP,
                       status = 'ACTIVE'
                 WHERE id = ?
                   AND email_canonical = ?
                   AND status = 'PENDING'
                   AND email_verified_at IS NULL
                """, token.accountId(), token.targetEmail());

        if (updated != 1) {
            throw new IllegalStateException(
                    "Account state no longer permits verification");
        }

        int consumed = jdbc.update("""
                UPDATE contact_verification_tokens
                   SET consumed_at = CURRENT_TIMESTAMP
                 WHERE id = ?
                   AND consumed_at IS NULL
                   AND revoked_at IS NULL
                   AND expires_at > CURRENT_TIMESTAMP
                """, token.id());

        if (consumed != 1) {
            throw new IllegalStateException(
                    "Verification token could not be consumed");
        }

        // Once verified, older signup verification links should not work.
        jdbc.update("""
                UPDATE contact_verification_tokens
                   SET revoked_at = CURRENT_TIMESTAMP
                 WHERE account_id = ?
                   AND purpose = 'VERIFY_SIGNUP_EMAIL'
                   AND id <> ?
                   AND consumed_at IS NULL
                   AND revoked_at IS NULL
                """, token.accountId(), token.id());

        return true;
    }

    private static String sha256Hex(String input) {
        try {
            byte[] bytes =
                    input.getBytes(StandardCharsets.US_ASCII);
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(bytes);
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(
                    "SHA-256 is required", e);
        }
    }
}
~~~

**Vì sao đây là single-use thực sự khi dùng một DB transaction?**

- `SELECT ... FOR UPDATE` giữ row lock cho bản ghi token trong PostgreSQL. Hai request với **cùng token** không thể đồng thời vượt qua bước kiểm tra unused dưới isolation thông thường `READ COMMITTED` và commit thành công như hai lần độc lập.
- `UPDATE app_accounts` kiểm tra account còn `PENDING`, email hiện tại đúng giá trị được token liên kết và chưa verified. Không thể dùng token cũ để xác minh địa chỉ mới.
- `UPDATE contact_verification_tokens` chỉ đánh dấu consumed khi chưa consumed, chưa revoked và chưa hết hạn tại lúc update.
- Cả hai update chạy trong transaction nhờ `@Transactional`. Nếu update account thành công mà token update thất bại, `IllegalStateException` là runtime exception và **Spring rollback cả transaction**.
- Sau khi thành công, server thu hồi các link signup verification còn pending của account. Với race của **hai token khác nhau cùng account**, chỉ một giao dịch được phép chuyển account `PENDING → ACTIVE`; giao dịch còn lại fail/rollback.
- `@Transactional` có tác dụng khi method được gọi qua Spring proxy từ bean khác; một self-invocation trong cùng instance có thể bỏ qua transaction proxy. Production phải có transaction manager đúng datasource.
- Handler bên ngoài nên chuyển lỗi trạng thái và token hết hạn thành thông báo công khai **không tiết lộ account tồn tại**. Log server đủ để điều tra nhưng không log raw token.

Ví dụ chỉ triển khai purpose `VERIFY_SIGNUP_EMAIL`. Với `VERIFY_NEW_EMAIL`, logic cập nhật phải khác: so khớp `pending_email`, giữ email cũ cho đến khi hoàn tất, và có thể đòi step-up trước khi phát hành. Không copy đoạn `status='PENDING'` cho user đã active.

### 10.3. Spring Security kiểm soát endpoint và account chưa verified

Một verification endpoint phải có thể truy cập bởi người **chưa đăng nhập** (ví dụ account pending không có phiên), nhưng điều đó không đồng nghĩa cho phép truy cập mọi API khác.

Ví dụ `SecurityFilterChain` dùng trong project Servlet:

~~~java
package com.example.account;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/verify-email",
                                "/verification-result", "/error")
                            .permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

**Giữ CSRF protection mặc định** cho form POST; link GET chỉ mở trang xác minh. Trong ứng dụng dùng `UserDetailsService`, có thể map `account.status == ACTIVE` và `email_verified_at != null` vào `UserDetails.isEnabled()` để chặn login trước khi verify (nếu chính sách yêu cầu). Nhưng `permitAll()` chỉ bỏ yêu cầu đăng nhập đối với endpoint, **không làm bước xác minh token bên trong tự an toàn**.

Khi trạng thái account được thay đổi trong DB, các session cũ có thể vẫn lưu `Authentication` trước đó. Với thao tác thu hồi/đổi contact hoặc account bị disabled, cần đánh giá session invalidation/revalidation ở các endpoint nhạy cảm; không kỳ vọng flag trong DB tự cập nhật tức thời vào mọi session.

### 10.4. Link email, GET và POST phải có trách nhiệm khác nhau

Đường dẫn gửi đến email có thể là:

~~~text
https://app.example.org/verify-email?token=<random-token>
~~~

Trong link thật, `<random-token>` được thay bằng raw token được phát hành riêng. **Không tạo URL từ `Host` hay `X-Forwarded-Host` không đáng tin**; dùng `publicBaseUrl` cố định trong config hoặc allowlist hostname.

Nên thiết kế:

~~~text
GET /verify-email?token=...
    └─ Render trang thông báo "Xác nhận email"
       Không tiêu thụ token.
       Referrer-Policy: no-referrer
       Cache-Control: no-store
       Không có third-party script/tracking pixel.
       Form hidden token + CSRF token.

User bấm nút xác nhận:
POST /verify-email (token + CSRF)
    └─ EmailVerificationService.verifySignupEmail(...)
       Transaction cập nhật account và consumed_at
       Redirect sang đường dẫn KHÔNG chứa token
~~~

**Tại sao không kích hoạt ngay khi GET?** Hệ thống chống spam, email security gateway, link previewer và browser prefetch có thể tự mở link. Nếu GET có side effect, token có thể bị tiêu thụ trước khi người dùng chủ động nhấn xác nhận.

**Vì sao email link vẫn phải bảo vệ khỏi rò rỉ URL?** Token trong query string có thể xuất hiện trong access logs, browser history, analytics và referer. Cần redaction ở proxy/app/monitoring, `Referrer-Policy: no-referrer`, CSP phù hợp, không nhúng tài nguyên bên thứ ba vào trang chứa token, và hạn chế TTL. Một số hệ thống dùng link có fragment rồi browser chuyển token sang POST; cách này tránh token tới server trong URL đầu tiên nhưng không tự chống XSS, nên vẫn cần thiết kế đầy đủ.

### 10.5. Phát hành token và gửi email qua side channel

Một issuance flow đúng phải:
1. Chỉ phát hành cho account ở trạng thái phù hợp; kiểm tra email đích canonical ở server.
2. Rate limit theo account, email/IP/device và số lần resend.
3. Sinh raw token mới bằng CSPRNG, lưu **digest + metadata**.
4. Tạo notification email tới **đúng target đã lưu**, dùng URL HTTPS từ cấu hình tin cậy.
5. Tránh lộ raw token ở HTTP response, app logs, traces hoặc DB.
6. Nếu gửi bất đồng bộ, dùng **transactional outbox**/queue phù hợp và quy tắc hết hạn, retry/idempotency rõ ràng. Đừng gửi email trước DB commit rồi để link chứa token chưa tồn tại.
7. Quy định resend: có thể thu hồi token trước, phát hành token mới và cập nhật notification; tránh email bão hoặc nhiều token còn valid không kiểm soát.

Thông báo email cần giải thích **đây là xác minh liên hệ**, không phải mật khẩu, và người dùng không phải thực hiện nếu không tạo yêu cầu. Với SMS, mã OTP ngắn cần TTL và rate limit nghiêm, giới hạn số lần nhập sai, chống đoán tự động và lưu code an toàn.

## 11. Luồng resend và thay đổi contact

### 11.1. Resend không nên "gửi lại raw token" từ DB

Nếu chỉ lưu digest, bạn **không thể xem lại raw token**. Quy trình resend tạo raw token khác, lưu digest khác, gửi link mới.

Có hai chiến lược rõ ràng:
- **Only latest valid:** thu hồi toàn bộ token verification cũ cho cùng account/purpose/target rồi phát hành token mới.
- **Several pending valid:** cho tồn tại một số link đến khi token đầu tiên xác minh thành công, lúc đó thu hồi các link còn lại.

Only-latest dễ giải thích bảo mật, nhưng email gửi không theo thứ tự có thể khiến người dùng click link đã bị thu hồi. Chọn UX dựa trên độ trễ email/SMS và rủi ro; **đừng vô tình gửi nhiều link tồn tại vô hạn**.

### 11.2. Thay email trong lúc link cũ còn tồn tại

Khi `pending_email` thay đổi:
- invalidate các token gắn với email cũ;
- tạo token mới với `target_contact` mới;
- khi redeem, kiểm tra target trong token bằng contact còn pending của account;
- nếu đã active, chỉ áp dụng địa chỉ mới **sau khi xác minh**, không ghi đè email đã verified trước đó.

Cần phân biệt xác minh địa chỉ mới với thông báo thay đổi sang địa chỉ cũ. Đối với hành động rủi ro cao, cân nhắc xác nhận cả email cũ lẫn email mới hoặc thêm MFA/step-up.

### 11.3. "Single-use" khác "idempotent"

Một endpoint có thể trả thông báo thân thiện khi user click lại link đã dùng, nhưng **không được thực hiện lại side effect**. Ví dụ:
- Lần đầu: account được chuyển thành verified và ghi audit.
- Lần thứ hai: server không chạy lại transaction xác minh; có thể hiển thị “Liên kết không còn hiệu lực”.
- Nếu nghiệp vụ cần idempotent presentation, xác định riêng trạng thái account và thông điệp không lộ dữ liệu cho client không xác thực.

**Tối đa một lần hoàn tất hành động** khác **tối đa một lần trả HTTP 200**. Trong thực tế, HTTP response của request thành công có thể bị mất và browser retry; server phải xử lý retry an toàn.

## 12. Chống lộ token và lạm dụng

### 12.1. Những nơi token có thể bị lộ

| Nguồn rò rỉ | Nguy cơ | Kiểm soát |
|---|---|---|
| URL trong access log/proxy/APM | Người có quyền đọc log có thể lấy raw token | Redact query params / headers chứa token |
| Browser history | Link còn trong lịch sử máy dùng chung | TTL ngắn, không để token trong URL sau POST |
| Referer đến website thứ ba | URL có thể lộ sang analytics hoặc ảnh ngoài | `Referrer-Policy: no-referrer`, không third-party assets |
| Inbox bị truy cập trái phép | Kẻ khác có thể bấm link thay chủ hộp thư | Tăng bảo mật tài khoản email; link ngắn hạn |
| Log gửi mail hoặc support ticket | Nhân viên thấy link chứa token | Log notification ID, không log URL đầy đủ |
| HTTP không dùng TLS | Token bị nghe lén trên đường truyền | HTTPS + certificate validation |
| XSS ở trang verification | Script trên origin thật có thể đọc token | Escape output, CSP, chống XSS, bảo vệ JS |
| Client gửi link qua chat | Người nhận khác có thể dùng token | Giải thích link là bí mật, TTL và single-use |

Không đưa raw token vào analytics event, monitoring span hay thông báo lỗi. `tokenDigest` cũng không cần đưa cho client; nội bộ nên log `verificationRequestId` không dùng được như credential.

### 12.2. User enumeration

Endpoint gửi lại link không nên trả:
- “Email này chưa có trong hệ thống” cho một trường hợp;
- “Đã gửi link cho account của Alice” cho trường hợp khác.

Thay bằng phản hồi chung kiểu **“Nếu địa chỉ đủ điều kiện, chúng tôi sẽ gửi hướng dẫn”**, áp dụng tương quan thời gian phản hồi phù hợp và rate limit/abuse monitoring. Với signup, chính sách thông báo trùng email có thể khác tùy UX, nhưng phải phân tích rò rỉ account existence.

### 12.3. Chống spam và brute force

- Giới hạn số lần phát hành, resend và consume theo account/email/IP/device và cửa sổ thời gian.
- Với OTP ngắn, giới hạn số lần sai/khóa yêu cầu; không chỉ dựa vào TTL.
- Không cho request gửi email đến địa chỉ khác ngoài `target_contact` đang được server chờ.
- Có captcha/risk-based checks khi lạm dụng, nhưng không dùng chúng làm thay thế entropy và authorization.
- Ghi audit an toàn cho issue, resend, consume thành công/thất bại, revoke, account change.

### 12.4. Liên hệ đã verified không có nghĩa mãi mãi vẫn thuộc cùng người

Địa chỉ email có thể đổi chủ, bị chiếm quyền hoặc bị nhà cung cấp thu hồi. Phone number có thể bị tái cấp, SIM swap. Vì vậy trạng thái `verified` là bằng chứng đã kiểm soát **ở thời điểm xác minh**, không phải danh tính bất biến. Với thao tác rủi ro cao, sử dụng MFA/step-up, thông báo thay đổi và cơ chế recovery mạnh hơn.

## 13. JWT có phù hợp làm contact verification token không?

Có thể mã hóa mục đích, account, target và thời hạn trong một **JWT ký số**. Tuy nhiên:

- Chữ ký JWT chỉ chống sửa nội dung, không chống **sao chép toàn token**.
- `exp` giới hạn thời gian, nhưng **không làm JWT tự động dùng một lần**.
- Muốn single-use phải lưu `jti`/nonce server-side, kiểm tra đã dùng/chưa revoked, chuyển state atomically.
- Cần kiểm tra issuer, audience, thuật toán ký và purpose/target chính xác; không tự tin claim chỉ vì decode được payload.
- JWT dễ vô tình đưa email/PII vào URL hoặc log dưới dạng payload có thể decode.

Với use case đơn giản **xác minh email bằng link**, một token opaque 256-bit, lưu digest + metadata thường **đơn giản hơn để quản lý expiry/revocation/single-use**. Không chọn JWT chỉ để tránh dùng DB nhưng đồng thời yêu cầu single-use.

## 14. Các lỗi thường gặp

1. **Dùng cùng token cho email verification và reset password.** Mất scope của token; phải tách `purpose` rõ ràng.
2. **Chỉ dựa vào `email` do client gửi để tìm account.** Dễ liên kết sai, đặc biệt khi email đổi/đa tenant.
3. **Dùng timestamp hoặc UUID rút gọn làm secret.** Dễ đoán hơn cần thiết; dùng CSPRNG.
4. **Lưu raw token trong DB.** DB leak biến thành credential leak; lưu digest của random token.
5. **Coi hash SHA-256 đủ với OTP 6 chữ số.** Code ngắn brute-force được ngoại tuyến; dùng bảo vệ phù hợp entropy thấp.
6. **Cho token dùng sau `expires_at`.** Quy tắc đúng là `now < expires_at`, không phải `now <= expires_at`.
7. **Đánh dấu consumed ngoài transaction cập nhật account.** Có thể mất token nhưng account chưa verified hoặc thực hiện hai lần.
8. **SELECT rồi UPDATE không khóa/không condition.** Hai instance có thể cùng thực hiện một hành động.
9. **Chỉ kiểm tra token valid rồi không so khớp target hiện tại.** Link cũ có thể xác minh nhầm liên hệ mới.
10. **Tự kích hoạt khi HTTP GET.** Email scanners/link preview có thể mở link trước user.
11. **Nhúng link xác minh vào logs/analytics hoặc tải ảnh third-party trên trang.** Token lộ qua URL/referer.
12. **Tạo link dựa trên `Host` header tùy ý.** Host-header poisoning có thể tạo link sang website attacker.
13. **Resend phát hành hàng trăm link cùng còn hiệu lực.** Tăng attack surface, gây nhầm UX và spam.
14. **Trả lỗi khác nhau cho email có/không có account.** Có thể dẫn tới enumeration.
15. **Coi `email_verified` là authenticated principal.** Proof of contact không tạo session và không có nghĩa đã MFA.
16. **Đổi email chính trước khi email mới được xác minh.** Có thể làm mất khả năng recovery hoặc chiếm account.
17. **Coi JVM synchronized/ConcurrentHashMap đủ cho cluster.** Cần DB/atomic compare-and-set xuyên instance.
18. **Tin trạng thái account trong session không đổi.** Account disabled/revoked sau login cần chính sách revalidation.
19. **Bỏ qua việc email/phone có thể đổi chủ.** Verification status là thông tin theo thời điểm.
20. **Từ chối idempotent retry bằng side effect lại.** Browser/network retry phải không khiến hành động chạy lần hai.

## 15. Ma trận kiểm thử

| Trường hợp | Kết quả an toàn |
|---|---|
| Token phát hành và gửi đúng email, trong TTL | Verify thành công **một lần**, cập nhật contact |
| Replay cùng token sau thành công | Từ chối, không thay đổi trạng thái lần nữa |
| Hai POST cùng token đồng thời (2 replica) | Chỉ một transaction hoàn tất, request kia không ghi lại |
| Token đúng nhưng sai purpose | Từ chối, không reset password/đổi email |
| Token đúng nhưng account ID không khớp | Từ chối |
| Token đúng nhưng pending contact đã đổi | Từ chối; không verify liên hệ mới |
| Token hết hạn, `now == expires_at` | Từ chối |
| Token revoked do resend/change | Từ chối |
| Token giả 43 ký tự cùng định dạng | Từ chối; không lộ account existence |
| Token có thêm ký tự hoặc định dạng sai | Từ chối trước khi truy vấn DB |
| Account đã active hoặc disabled không còn chờ | Không thực hiện state transition |
| Account verification SQL update lỗi sau row lock | Rollback, token không bị consumed riêng |
| Token update lỗi sau account update | Rollback cả account và token |
| Two valid tokens của cùng account được dùng song song | Một account transition; sibling token không tạo hành động thứ hai |
| GET link bởi email security scanner | Không tiêu thụ token |
| POST xác minh thiếu CSRF trong form session-based | Bị CSRF policy từ chối |
| Log request chứa token | Hệ thống redaction bảo vệ raw token |
| Resend liên tục | Có rate limit, không gửi spam vô hạn |
| Query email không tồn tại | Phản hồi chống enumeration |
| Link bị đổi sang host do Host header giả | URL issuance luôn dùng trusted base URL |
| Token email verification được dùng làm login token | Không tạo phiên đăng nhập |
| OTP 6 chữ số thử nhiều lần | Có attempt cap/rate limiting chặt |
| Thay email trong thời gian link đang bay | Token cũ vô hiệu; chỉ target mới được xác minh |
| Login sau xác minh | Account policy cho phép; session được tạo **bằng auth flow riêng** |

**Test điều kiện cạnh tranh rất quan trọng:** unit test đơn luồng không phát hiện vấn đề “hai request cùng thấy unused”. Với PostgreSQL, dùng integration test thực, ít nhất hai connection/transaction và barrier để tăng xác suất race, rồi assert **một** cập nhật account thành công và không có side effect trùng lặp.

Trong Spring Security, test `permitAll` chỉ chứng minh route được phép truy cập chưa login, **không chứng minh token verification logic an toàn**. Test domain service và DB transaction riêng, cộng E2E test link/CSRF/browser.

## 16. Checklist triển khai

- [ ] Xác định mục đích token bằng enum/constant rõ ràng, không dùng token thay cho login/session.
- [ ] Token liên kết đúng account ID + contact hiện tại + tenant/context + purpose.
- [ ] Raw token sinh từ CSPRNG đủ entropy; không in/log, DB chỉ lưu digest.
- [ ] TTL rõ ràng, kiểm tra `now < expires_at` và revoked/consumed.
- [ ] Database có unique digest và transaction/row-lock hoặc conditional UPDATE.
- [ ] Thay đổi trạng thái account và tiêu thụ token cùng commit; xử lý rollback.
- [ ] Resend, đổi contact, xóa account đều vô hiệu hóa token không còn phù hợp.
- [ ] Account chưa verified bị giới hạn đúng chính sách login/authorization.
- [ ] Email change cần reauthentication/step-up, notify email cũ và verify email mới.
- [ ] Public GET chỉ render form; POST có tác dụng, có CSRF theo kiến trúc browser.
- [ ] Link HTTPS có trusted base URL, no-referrer, no-store, không third-party assets.
- [ ] Rate limit issue/resend/consume; lỗi và response chống enumeration.
- [ ] Không gửi raw token qua HTTP response của API request resend.
- [ ] Email/SMS delivery có retry, outbox/idempotency và giám sát độ trễ thích hợp.
- [ ] Mã OTP ngắn có attempt cap và chính sách lưu trữ riêng.
- [ ] Test expired, replay, wrong-purpose, wrong-target, concurrent requests, rollback và multi-instance.
- [ ] Log audit không chứa full email/token/verification URL; retention và quyền xem phù hợp.

## 17. Ghi nhớ

Một token xác minh liên hệ an toàn có thể mô tả ngắn gọn:

~~~text
ValidContactVerification =
    secret đúng
    + đúng purpose
    + đúng account và target đang chờ
    + đúng tenant/context
    + chưa hết hạn
    + chưa revoked / chưa consumed

Thực thi thành công =
    thay đổi trạng thái contact
    VÀ consumed token
    TRONG MỘT transaction
~~~

**Purpose giới hạn việc được làm, TTL giới hạn khoảng thời gian, single-use giới hạn số lần.** Ba điều kiện phải được kiểm tra ở phía server, cùng với việc bảo vệ token và liên kết đúng thông tin liên hệ. Xác minh email/phone là một bước trong vòng đời tài khoản, không phải một cơ chế cấp mọi quyền đăng nhập.

## 18. Tài liệu tham khảo

1. [OWASP — Email Validation and Verification Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html): single-use, expiry, email ownership, canonicalization, anti-enumeration và email change.
2. [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): secure token generation/storage, purpose-limited flows, URL leak, Host header và rate limit. Các nguyên tắc bảo vệ token có thể áp dụng tương tự cho contact verification, dù đây là hai purpose khác nhau.
3. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): identity, reauthentication, responses và account security.
4. [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): hạn chế rò rỉ credential và quản lý secret.
5. [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction boundary và rollback rules.
6. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `permitAll`, `authenticated`, security chain.
7. [Spring Security 6.5 API — UserDetails](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/core/userdetails/UserDetails.html): `isEnabled` và account state khi đăng nhập.
8. [Oracle Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): random bytes đủ mạnh cho token.
9. [Oracle Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 digest.
