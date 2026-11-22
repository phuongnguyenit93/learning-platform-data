# Đăng ký, xác minh liên hệ và kích hoạt tài khoản trong Spring Security

## 1. Bài toán: đăng ký xong chưa đồng nghĩa được đăng nhập

Giả sử hệ thống cho phép người dùng tự tạo tài khoản bằng email và mật khẩu. Người dùng nhập `lan@example.test` và một mật khẩu đủ mạnh. Tại thời điểm form được chấp nhận, hệ thống **chưa biết người đăng ký có thực sự kiểm soát mailbox `lan@example.test` hay không**. Nếu lập tức cho đăng nhập, một người có thể đăng ký bằng địa chỉ của người khác, chiếm username hoặc nhận quyền đáng lẽ chỉ dành cho người sở hữu liên hệ đó.

Quy trình an toàn thường tách thành các bước:

1. **Registration — đăng ký:** kiểm tra đầu vào, chính sách, trùng lặp và tạo tài khoản ở trạng thái chờ; mật khẩu được lưu bằng `PasswordEncoder`, không lưu plaintext.
2. **Contact verification — xác minh liên hệ:** gửi mã/link có token ngẫu nhiên, thời hạn ngắn, một lần sử dụng qua kênh liên hệ đã khai báo; chỉ khi người nhận hoàn tất bước xác minh mới ghi nhận quyền kiểm soát kênh đó.
3. **Activation — kích hoạt:** cập nhật trạng thái tài khoản thành `ACTIVE` khi đáp ứng **đủ** điều kiện vận hành (ví dụ đã xác minh email và đã được duyệt theo chính sách). Từ lúc đó, cơ chế đăng nhập mới cho phép tài khoản hoạt động.
4. **Sign-in — đăng nhập:** là giao dịch xác thực riêng sau kích hoạt; **không tự tạo session đăng nhập chỉ vì ai đó mở link xác minh**.

Tất cả bước đều liên quan đến **vòng đời tài khoản** trong Spring Security, nhưng không phải bước nào cũng do framework tự triển khai. Spring Security xử lý authentication/authorization, `UserDetails`, `PasswordEncoder` và security filter chain; ứng dụng phải tự thiết kế lưu tài khoản, token xác minh, email/SMS delivery, approval và trạng thái nghiệp vụ.

**Kết quả học tập:** hiểu state machine đăng ký → xác minh → kích hoạt, tự viết token đủ mạnh, nối trạng thái account vào Spring Security, xử lý resend/expiry/race/enum/abuse, và kiểm thử cả trường hợp âm tính.

## 2. Phân biệt bốn sự kiện nghiệp vụ

| Sự kiện | Chứng minh điều gì? | Không chứng minh điều gì? |
| --- | --- | --- |
| **Form đăng ký hợp lệ** | Người gửi đã cung cấp dữ liệu đúng format và vượt qua policy input | Không chứng minh email/số điện thoại thuộc người gửi |
| **Email/SMS được gửi thành công** | Hệ thống giao nội dung cho hạ tầng gửi; có thể chấp nhận xử lý | Không chứng minh người nhận đọc được hoặc sử dụng được link/mã |
| **Liên hệ được xác minh** | Người thực hiện có quyền truy cập kênh liên hệ tại thời điểm xác minh, trong giới hạn assurance của kênh | Không chứng minh giấy tờ nhân thân, vai trò quản trị hoặc danh tính pháp lý |
| **Tài khoản được kích hoạt** | Ứng dụng quyết định đã thỏa điều kiện để cho phép login theo policy | Không đồng nghĩa đã vượt qua MFA, quyền nghiệp vụ hay session authentication |

Email verification **không phải xác thực danh tính mạnh** và không thay thế MFA. Mailbox có thể bị chiếm, forwarding, dùng chung hoặc tái cấp. Với ứng dụng nhạy cảm, cần thêm các bước như duyệt quản trị, xác minh tổ chức, MFA và phân quyền theo tenant.

Một tài khoản có `emailVerifiedAt != null` chưa chắc được phép đăng nhập: account có thể bị `SUSPENDED`, `DISABLED`, `LOCKED` hoặc đang chờ `APPROVAL`. Vì vậy nên lưu **trạng thái tài khoản** và **trạng thái liên hệ** tách biệt.

## 3. Thiết kế state machine rõ ràng

Phiên bản tối thiểu:

~~~text
                    POST /register
                          |
                          v
                 PENDING_VERIFICATION
                          |
             confirm valid one-time token
                          |
                          v
                        ACTIVE
                          |
               security policy / admin
                          |
                          v
                     SUSPENDED
                          |
                 authorized recovery
                          |
                          v
                        ACTIVE
~~~

Trong hệ thống có kiểm duyệt thêm:

~~~text
NEW_REQUEST
    |
    +-- invalid input / blocked rate limit -> REJECTED
    |
    v
PENDING_VERIFICATION
    |
    +-- token expired -> vẫn PENDING, cấp token mới có kiểm soát
    |
    +-- token invalid -> vẫn PENDING, không thay đổi account
    |
    v
PENDING_APPROVAL (nếu tổ chức yêu cầu)
    |
    +-- denied -> REJECTED/DISABLED
    |
    v
ACTIVE
    |
    +-- policy violation / user deactivated -> SUSPENDED/DISABLED
~~~

**Transition phải có điều kiện rõ ràng:**

| Trạng thái hiện tại | Hành động | Điều kiện | Trạng thái tiếp theo |
| --- | --- | --- | --- |
| Chưa tồn tại | Register | Input hợp lệ, không trùng identity theo policy | `PENDING_VERIFICATION` |
| `PENDING_VERIFICATION` | Verify contact | Token đúng purpose, còn hạn, chưa tiêu thụ, gắn đúng account/contact | `ACTIVE` hoặc `PENDING_APPROVAL` |
| `PENDING_VERIFICATION` | Sai/expired token | Token không hợp lệ | **Không đổi**; cho phép yêu cầu gửi lại theo giới hạn |
| `ACTIVE` | Verify token cũ | Token đã tiêu thụ hoặc bị vô hiệu | **Không đổi**; không phát session mới |
| `ACTIVE` | Suspend | Do chủ tài khoản/quản trị/chính sách được phép | `SUSPENDED` |
| `SUSPENDED` | Verify email cũ | Bất kỳ token đăng ký cũ | **Không tự mở khóa** |
| `SUSPENDED` | Restore | Luồng khôi phục được duyệt | `ACTIVE` nếu thỏa lại policy |

Với một service quản lý vòng đời, nên định nghĩa trạng thái như `PENDING_VERIFICATION`, `PENDING_APPROVAL`, `ACTIVE`, `DISABLED`, `SUSPENDED` trong enum; tránh dùng một boolean `active` để gộp tình trạng chưa xác minh, chưa được duyệt, bị khóa và bị cấm truy cập.

## 4. Mô hình dữ liệu tối thiểu

Một thiết kế cơ sở dữ liệu có thể dùng hai bảng: account và verification challenge.

~~~sql
-- Ví dụ PostgreSQL, chỉ minh họa schema/cấu trúc.
CREATE TABLE app_account (
    id UUID PRIMARY KEY,
    email_original TEXT NOT NULL,
    email_lookup TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PENDING_VERIFICATION', 'PENDING_APPROVAL',
                   'ACTIVE', 'SUSPENDED', 'DISABLED')),
    email_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE verification_challenge (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES app_account(id),
    contact_snapshot TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (
        purpose IN ('VERIFY_SIGNUP_EMAIL', 'VERIFY_NEW_EMAIL')),
    token_digest TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_verification_account
    ON verification_challenge(account_id, purpose);
~~~

**Ý nghĩa các trường:**
- `id` là **ID nội bộ bất biến**, không nhất thiết dùng email làm primary key. Khi email đổi, mọi dữ liệu vẫn thuộc về cùng account ID.
- `email_original` phục vụ liên hệ/hiển thị; `email_lookup` được tính theo **chính sách canonicalization nhất quán** để tra cứu/unique.
- `password_hash` là kết quả adaptive `PasswordEncoder` cho password; không lưu raw password, không tự dùng SHA-256 thuần cho mật khẩu do người chọn.
- `status` là quyết định kích hoạt ở cấp tài khoản.
- `email_verified_at` cho biết lần xác minh liên hệ hiện tại (nếu email đổi, phải reset/điều chỉnh trạng thái).
- `purpose` ngăn dùng token đăng ký như token đổi email hoặc reset password.
- `contact_snapshot` giúp chống race: chỉ chấp nhận token nếu nó còn áp dụng cho email mà token được gửi tới.
- `token_digest` lưu digest của token ngẫu nhiên thay vì raw bearer secret; `consumed_at`/`expires_at` ràng buộc một lần và hết hạn.

**Lưu ý email:** theo chuẩn email, phần domain không phân biệt hoa/thường, còn local part về mặt giao thức có thể phân biệt. Một số nhà cung cấp có chính sách dấu chấm/alias riêng. Không mặc định xóa dấu chấm, bỏ `+tag` hoặc lowercase mọi local part theo các mẹo của một provider, vì dễ gộp nhầm hai người dùng. Tổ chức cần xác định policy và quản lý uniqueness trước khi triển khai.

**Ràng buộc dữ liệu:** production phải bảo đảm account/verification token được tạo hoặc tiêu thụ trong transaction phù hợp và có unique index. Chỉ làm `SELECT` rồi `INSERT` mà không dựa vào constraint có thể tạo hai account khi hai request đăng ký đồng thời.

## 5. Quy trình đăng ký an toàn

### 5.1. Input validation không phải identity verification

Ở `POST /account/register`, nhận email và mật khẩu (có thể thêm điều khoản/chính sách riêng). Kiểm tra:
- `email` không trống, độ dài và cú pháp hợp lệ; **không dựa hoàn toàn vào một regex tự viết**; xét Unicode/EAI, IDN và chính sách mailer thực tế.
- `password` thỏa password policy hiện hành; hỗ trợ mật khẩu dài/passphrase, không tự cắt ngắn, chống mật khẩu phổ biến/bị lộ khi có năng lực.
- Kích thước payload, Content-Type và dữ liệu phụ được giới hạn; chống abuse/bot và tạo tài khoản hàng loạt.
- CAPTCHA/abuse challenges là **công cụ bổ sung theo rủi ro**, không thay thế rate limiting, identity proofing hoặc verification.
- Chính sách đồng ý điều khoản/privacy nếu áp dụng, tránh lưu quá nhiều PII.

**Bên server phải tạo ID và trạng thái.** Không tin JSON client gửi `"status":"ACTIVE"`, `"emailVerified":true`, `"role":"ADMIN"` hay `"approvedBy"`. API chỉ cho phép client nhập những trường đã được whitelisted.

### 5.2. Hash password đúng loại

Spring Security có `PasswordEncoderFactories.createDelegatingPasswordEncoder()`; encoder tạo chuỗi như `{bcrypt}...` và hỗ trợ upgrade algorithm theo prefix. Với mật khẩu người dùng, dùng adaptive hash như bcrypt/Argon2id/scrypt/PBKDF2 theo chính sách và khả năng triển khai; **không lưu plaintext** hay dùng `{noop}`.

Mẫu cấu hình:

~~~java
// Bean đầy đủ trong một class @Configuration của Spring Boot.
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
~~~

Ở production, theo dõi cost/độ trễ, memory, giới hạn dữ liệu đầu vào, password compromise checking và migration hash. Chọn encoder theo chính sách bảo mật/phiên bản Spring Security đang dùng.

### 5.3. Chống user enumeration

Nếu trả:
- “Email chưa được đăng ký” khi không tồn tại,
- “Email đã có tài khoản” khi tồn tại,

attacker có thể dò danh sách tài khoản bằng cách gọi hàng loạt.

**Phản hồi công khai nên trung tính và nhất quán**, ví dụ:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"message":"Nếu yêu cầu phù hợp, hướng dẫn xác minh sẽ được gửi."}
~~~

Điều này không có nghĩa server phải luôn gửi email tới mọi địa chỉ. Chỉ gửi thông báo thích hợp dựa trên policy; có thể không gửi gì cho account đã active và không để public API tiết lộ nhánh xử lý. Chú ý cả timing, HTTP status, kích thước response và side channels; thêm rate limit theo IP, account/email, tenant và hành vi.

Không trả raw token trong response đăng ký. Khi debug local, có thể dùng **test mailbox** chỉ truy cập trong test process; không cấp endpoint công khai để đọc token.

## 6. Phát hành token xác minh liên hệ

### 6.1. Cần thuộc tính bảo mật nào?

Một token xác minh email nên:
- **Ngẫu nhiên mật mã**: tạo từ `SecureRandom` hoặc CSPRNG tương đương, có entropy cao, ví dụ 32 byte (256 bit).
- **Không đoán được** và không suy ra từ email, user ID, timestamp, khóa tuần tự.
- **Mục đích duy nhất**: `VERIFY_SIGNUP_EMAIL`; không dùng làm password-reset token hoặc session ID.
- **Gắn với đúng account và email snapshot**, không lấy account ID từ request client ở bước verify.
- **Thời hạn hữu hạn**, tính bằng timestamp UTC/clock của server.
- **Dùng một lần**; consume nguyên tử để hai request đồng thời không cùng kích hoạt.
- **Có thể thu hồi** khi email thay đổi, account bị đình chỉ, có yêu cầu resend hoặc có dấu hiệu lộ.
- **Không lưu raw token** ở database/log. Với token CSPRNG đủ entropy, có thể lưu `SHA-256(token)` và đối chiếu theo digest; khác với mật khẩu do người dùng chọn.

Tạo token:

~~~java
// Trích đoạn Java 17 thuộc service Java, có import SecureRandom/Base64.
byte[] bytes = new byte[32];
SecureRandom random = new SecureRandom();
random.nextBytes(bytes);
String rawToken = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(bytes);
~~~

Chuỗi Base64URL không chứa `+`, `/` hay padding `=`. Không dùng `UUID.randomUUID()` như một giải pháp bất biến về độ dài/entropy, không tạo token bằng `Math.random()` hoặc `Random`.

### 6.2. Lưu digest, kiểm tra thời hạn, single use

Một chuỗi 32 byte ngẫu nhiên có thể băm bằng SHA-256 để lưu hash. Khi verify, server hash token client nộp rồi tra bản ghi chứa digest, kiểm tra:
1. `purpose` đúng với endpoint.
2. Thời gian hiện tại **trước** `expires_at`. Ở thời điểm đúng bằng expiry là **hết hạn**.
3. `consumed_at` còn trống.
4. Account đang `PENDING_VERIFICATION`, chưa bị disabled/suspended.
5. Email hiện tại vẫn khớp `contact_snapshot`.
6. Transition account + consume token **nguyên tử**; không có hai lượt verify đều thành công.

Ví dụ SQL có khóa hàng trong transaction:

~~~sql
BEGIN;

SELECT account_id, contact_snapshot, expires_at, consumed_at
FROM verification_challenge
WHERE token_digest = :digest
  AND purpose = 'VERIFY_SIGNUP_EMAIL'
FOR UPDATE;

-- Ứng dụng kiểm tra row tồn tại, expires_at > now,
-- consumed_at IS NULL, contact snapshot và account status.
-- Trong cùng transaction, khóa account row / kiểm tra status.

UPDATE app_account
SET status = 'ACTIVE',
    email_verified_at = now(),
    updated_at = now()
WHERE id = :accountId
  AND status = 'PENDING_VERIFICATION'
  AND email_lookup = :contactSnapshot;

UPDATE verification_challenge
SET consumed_at = now()
WHERE token_digest = :digest
  AND consumed_at IS NULL;

COMMIT;
~~~

Đây là **mẫu SQL phác thảo**, không phải transaction hoàn chỉnh chỉ cần copy: tầng application phải kiểm tra **row counts**, purpose/expiry và lock order, rollback khi bất kỳ điều kiện nào thất bại. Nên dùng bản ghi challenge/account cùng cơ chế locking hay conditional update bảo đảm atomicity. Trong triển khai nhiều server, `synchronized` ở một JVM không đủ.

**Lưu ý về resend:** tạo token mới có thể làm vô hiệu tất cả token `VERIFY_SIGNUP_EMAIL` cũ cho account, trong một transaction, rồi gửi token mới qua outbox. Không để cùng lúc quá nhiều token có hiệu lực nếu policy không yêu cầu.

### 6.3. Delivery và transactional outbox

Đừng gọi dịch vụ gửi email rồi **sau đó** mới lưu tài khoản/token mà không có kế hoạch rollback. Nếu network mail chấp nhận gửi nhưng transaction DB thất bại, user nhận link không thể xác minh. Nếu DB commit nhưng mail gửi thất bại, account cần resend.

Mô hình bền vững:
1. Transaction ghi account `PENDING_VERIFICATION`, challenge digest và **outbox event** chứa thông tin gửi được bảo vệ phù hợp.
2. Commit transaction; worker email đọc event và giao qua mail provider.
3. Khi nhà cung cấp phản hồi thành công/thất bại, ghi delivery status và retry có giới hạn, giữ idempotency.
4. Không viết raw token vào log; nếu outbox cần tạm giữ token để gửi, **mã hóa payload/giới hạn quyền và thời gian lưu**, hoặc dùng kiến trúc sinh token khi dispatch phù hợp.
5. Đo tỷ lệ gửi/thất bại/delay và có kênh resend an toàn.

Không xem HTTP 202 hoặc “email delivered to provider” là bằng chứng người dùng đã xác minh.

## 7. Link xác minh qua email và rủi ro click tự động

Email thông thường có link:

~~~text
https://accounts.example.org/verify-email?token=<one-time-value>
~~~

URL trong email là **credential ngắn hạn** nên cần thêm lớp bảo vệ:
- Domain/hostname phải được cấu hình cố định, thuộc quyền RP; không xây `verificationUrl` từ `Host`/`X-Forwarded-Host` chưa tin cậy (host header poisoning).
- Chỉ dùng HTTPS, không đưa token vào analytics, third-party scripts, click tracking hay access logs.
- Trang đích đặt `Referrer-Policy: no-referrer`, `Cache-Control: no-store`; tránh tải tài nguyên bên thứ ba có thể nhìn thấy URL.
- Không đặt token vào lưu trữ lâu dài; hết hạn và single-use.
- **Email security scanner/link preview có thể tự truy cập GET link.** Đừng kích hoạt tài khoản ngay bằng một request GET chỉ vì link được mở! Nên cho GET hiển thị trang xác nhận, người dùng chủ động submit **POST** mang token (hoặc cơ chế xác nhận tương đương), rồi consume.
- Nếu redirect sau verify, dùng URL **không chứa token**, không đưa token vào `Location`.
- Không tự đăng nhập sau khi verify; yêu cầu user hoàn thành đăng nhập bình thường theo policy.

Trong ví dụ Spring ở mục 10, không phát email thật: test mailbox giữ mã nội bộ, frontend giả lập `POST /account/verify` với token trong JSON. Đây là cách kiểm tra state machine mà không đưa credential vào URL.

## 8. Liên hệ email và SMS/điện thoại không giống nhau

| Kênh | Cách chứng minh kiểm soát | Giới hạn |
| --- | --- | --- |
| Email | Token ngẫu nhiên qua email và người nhận xác nhận | Mailbox dùng chung, forwarding, bị chiếm, email tái cấp |
| SMS | OTP ngắn qua SMS, người dùng nhập mã | SIM swap, chuyển số, SS7, SMS forwarding, chi phí gửi |
| Phone call | Mã thoại/IVR | Rủi ro chuyển tiếp cuộc gọi, social engineering |
| Authenticator/phương thức mạnh | Passkey, TOTP, thiết bị tổ chức | Phù hợp làm authentication/MFA, không nhất thiết xác minh quyền sở hữu email |

Nếu dùng **OTP số** (thường entropy thấp hơn token 256 bit), cần rate limit số lần đoán, số lần gửi, thời gian sử dụng, số attempt mỗi challenge và anti-abuse mạnh hơn. Không lưu mã thô, không lộ trong logs. Việc kiểm soát số điện thoại tại một thời điểm không chứng minh quyền sở hữu lâu dài; thay SIM/thu hồi số có thể làm thay đổi người nhận.

**Không gộp** `email_verified` và `phone_verified` vào một cờ “verified” duy nhất nếu sản phẩm yêu cầu chính sách riêng cho các kênh. Mỗi kênh nên có verified timestamp/trust level, nhất là ở hệ thống có nhiều kênh khôi phục tài khoản.

## 9. Spring Security thực sự cấm đăng nhập account chờ như thế nào?

Spring Security dùng `UserDetailsService` để lấy người dùng, `PasswordEncoder` để kiểm tra password và `DaoAuthenticationProvider` trong flow xác thực tài khoản/mật khẩu. `UserDetails.isEnabled()` biểu thị account có được phép xác thực hay không.

Ví dụ một `UserDetailsService` đọc trạng thái từ repository:

~~~java
// Mảnh cấu hình minh họa trong Spring Security Servlet.
@Bean
UserDetailsService userDetailsService(AccountRepository accounts) {
    return username -> {
        Account account = accounts.findByEmail(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Bad credentials"));

        return User.withUsername(account.getEmail())
                .password(account.getPasswordHash())
                .authorities("ROLE_USER")
                .disabled(account.getStatus() != AccountStatus.ACTIVE)
                .build();
    };
}
~~~

Đây là **mảnh code**, không phải class độc lập. Nó minh họa `disabled(...)` đối lập `isEnabled()`. Khi account chưa ACTIVE, không thể được xem là authenticated thành công qua provider kiểm tra trạng thái này, dù password khớp.

**Điểm dễ nhầm:**
- `requestMatchers("/account/register").permitAll()` chỉ cho phép truy cập **endpoint đăng ký**, **không** cấp authority hay biến account `ACTIVE`.
- `permitAll()` cho endpoint verify giúp người chưa đăng nhập nộp token, nhưng bản thân service phải xác minh token đúng; không tự cho sửa `status` bằng request JSON.
- `.disabled(true)` bảo vệ login flow có kiểm tra `UserDetails`. Nếu hệ thống còn passkey, OAuth2/OIDC, SAML hay custom authentication provider, phải áp dụng chính sách account ACTIVE nhất quán **sau identity linking** ở mọi cơ chế, không chỉ password login.
- `AccountStatus.ACTIVE` không nói user có quyền `ROLE_ADMIN`. Authorization vẫn kiểm tra role/tenant/ownership.
- Session đã được tạo **trước khi account bị suspend** có thể tiếp tục hợp lệ nếu không có chính sách thu hồi session/cache/refresh; kiểm tra status lúc login chưa đủ cho việc deactivation tức thời.

## 10. Project Spring Boot 3.3.x có thể chạy: đăng ký, xác minh và login gating

Ví dụ là một **lab tự chứa** với Java 17, Spring Boot 3.3.12, Spring Security 6.3.x và một in-memory account store. Để kiểm tra email mà **không gửi thư tới người thật hoặc log token**, ví dụ có `DemoMailbox`, chỉ test Java/JUnit gọi trực tiếp để lấy token giả. **Không triển khai DemoMailbox hoặc Map store ở production.**

Điểm chính: `POST /account/register` tạo `PENDING_VERIFICATION`; token có SHA-256 digest và expiry; `POST /account/verify` kích hoạt đúng một lần; `GET /account/me` chỉ trả thành công khi account đã active và HTTP Basic password hợp lệ. Ở production thay HTTP Basic/demo store bằng authentication flow và database phù hợp.

### 10.1. Các file

~~~text
account-activation-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/lifecycle/
    │   │   ├── LifecycleApplication.java
    │   │   ├── AccountService.java
    │   │   ├── DemoMailbox.java
    │   │   ├── LifecycleController.java
    │   │   └── SecurityConfig.java
    │   └── resources/application.yml
    └── test/java/demo/lifecycle/AccountActivationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'account-activation-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
spring:
  application:
    name: account-activation-lab
~~~

`src/main/java/demo/lifecycle/LifecycleApplication.java`:

~~~java
package demo.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }
}
~~~

### 10.2. DemoMailbox: chỉ dành cho test, không có REST endpoint

`src/main/java/demo/lifecycle/DemoMailbox.java`:

~~~java
package demo.lifecycle;

import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class DemoMailbox {
    private final ConcurrentHashMap<String, String> latest =
            new ConcurrentHashMap<>();

    // Mô phỏng chuyển token tới mail system, không log ra console.
    public void deliver(String normalizedEmail, String rawToken) {
        latest.put(normalizedEmail, rawToken);
    }

    // Test code trong JVM dùng method này; không expose ra HTTP.
    public String readForTest(String normalizedEmail) {
        return latest.get(normalizedEmail);
    }
}
~~~

**Không dùng trong production:** mailbox này giữ token thô ở memory và không thực sự gửi mail. Ở production, thay bằng giao diện gửi email được kiểm soát, transactional outbox, encryption/retention cho payload cần giao và sender domain đã được xác thực SPF/DKIM/DMARC theo chính sách.

### 10.3. AccountService: token ngẫu nhiên, digest, trạng thái

`src/main/java/demo/lifecycle/AccountService.java`:

~~~java
package demo.lifecycle;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AccountService {
    public enum Status { PENDING_VERIFICATION, ACTIVE, SUSPENDED }

    public record Account(
            String email,
            String encodedPassword,
            Status status,
            Instant verifiedAt) {}

    private record Challenge(String email, Instant expiresAt) {}

    private final Map<String, Account> accounts = new ConcurrentHashMap<>();
    private final Map<String, Challenge> pending = new ConcurrentHashMap<>();
    private final SecureRandom secureRandom = new SecureRandom();
    private final PasswordEncoder encoder;
    private final DemoMailbox mailbox;

    public AccountService(PasswordEncoder encoder, DemoMailbox mailbox) {
        this.encoder = encoder;
        this.mailbox = mailbox;
    }

    // Chỉ là chính sách email dùng trong lab, không áp dụng toàn cầu
    // cho mọi nhà cung cấp email: local part có thể phân biệt hoa/thường.
    static String normalize(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }

    public synchronized void register(String rawEmail, String password) {
        String email = normalize(rawEmail);

        // Không trả "đã tồn tại" cho client.
        if (accounts.containsKey(email)) {
            return;
        }

        String encoded = encoder.encode(password);
        accounts.put(email, new Account(
                email, encoded, Status.PENDING_VERIFICATION, null));

        byte[] secret = new byte[32];
        secureRandom.nextBytes(secret);
        String rawToken = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(secret);
        String digest = sha256Hex(rawToken);
        pending.put(digest, new Challenge(
                email, Instant.now().plus(Duration.ofMinutes(20))));

        // Lab only. Production dùng outbox/sender sau DB commit.
        mailbox.deliver(email, rawToken);
    }

    public synchronized boolean verify(String rawToken) {
        if (rawToken == null || rawToken.isBlank()
                || rawToken.length() > 128) {
            return false;
        }

        String digest = sha256Hex(rawToken);
        Challenge challenge = pending.get(digest);
        if (challenge == null) {
            return false;
        }

        // expiresAt == now cũng là expired.
        if (!Instant.now().isBefore(challenge.expiresAt())) {
            pending.remove(digest);
            return false;
        }

        Account account = accounts.get(challenge.email());
        if (account == null
                || account.status() != Status.PENDING_VERIFICATION) {
            return false;
        }

        pending.remove(digest); // consume chỉ một lần trong lab JVM
        accounts.put(account.email(), new Account(
                account.email(), account.encodedPassword(),
                Status.ACTIVE, Instant.now()));
        return true;
    }

    public Account findByEmail(String rawEmail) {
        if (rawEmail == null) {
            return null;
        }
        return accounts.get(normalize(rawEmail));
    }

    private static String sha256Hex(String input) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(input.getBytes(StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossibleOnJava17) {
            throw new IllegalStateException(impossibleOnJava17);
        }
    }
}
~~~

**Phân tích code:**
1. Account mới là `PENDING_VERIFICATION`; không có method public nào cho client tự ghi `ACTIVE`.
2. Secret 32 byte từ `SecureRandom` được encode Base64URL, token digest được lưu trong `pending`; raw token chỉ đi tới test mailbox.
3. `verify` kiểm tra tồn tại, expiry, status và consume digest trước khi chuyển account sang ACTIVE. Với `synchronized` trong **một JVM**, hai lượt verify tuần tự nên token không dùng lại được.
4. Trạng thái `SUSPENDED` không thể bị token đăng ký cũ mở khóa, vì chỉ cho phép transition từ `PENDING_VERIFICATION`.
5. `findByEmail` chỉ cung cấp dữ liệu cho `UserDetailsService`; việc chuyển thành Spring Security Authentication thực hiện trong chain.
6. **Lab thiếu một số điều kiện production**: Map state sẽ mất khi restart, `synchronized` không an toàn cho nhiều node, không có resend, chưa ràng buộc purpose/contact snapshot trong record, không có mail provider, DB transaction, anti-enumeration timing equalization, rate limit/audit hoặc cơ chế revoke session. Mục 4–6 và mục 13 chỉ ra cách bổ sung; không sử dụng trực tiếp service này cho production.

**Email normalization:** `toLowerCase(Locale.ROOT)` trên toàn email chỉ là chính sách đơn giản cho email test `example.test`. Trước khi triển khai cần thống nhất cách canonicalize domain/local part, IDN/Unicode và account uniqueness để tránh identity confusion.

### 10.4. SecurityConfig: PENDING không được authenticate

`src/main/java/demo/lifecycle/SecurityConfig.java`:

~~~java
package demo.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(AccountService accounts) {
        return username -> {
            AccountService.Account acc = accounts.findByEmail(username);
            if (acc == null) {
                throw new UsernameNotFoundException("Bad credentials");
            }

            return User.withUsername(acc.email())
                    .password(acc.encodedPassword())
                    .authorities("ROLE_USER")
                    .disabled(acc.status() != AccountService.Status.ACTIVE)
                    .build();
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .csrf(csrf -> csrf.ignoringRequestMatchers(
                        "/account/register", "/account/verify"))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/account/register",
                                "/account/verify").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**Điểm bảo mật cần hiểu:**
- `.disabled(true)` khiến `UserDetails.isEnabled()` là false; Spring Security `DaoAuthenticationProvider` sẽ không xác thực thành công account PENDING bằng HTTP Basic dù mật khẩu đúng.
- Hai endpoint đăng ký/xác minh được `permitAll` vì người dùng chưa thể đăng nhập, nhưng quyền đổi trạng thái **chỉ nằm trong `AccountService.verify`**.
- Cấu hình CSRF ở đây **chỉ bỏ yêu cầu CSRF token cho hai public POST của lab**; các POST khác trong browser vẫn có CSRF protection mặc định. Production cần đánh giá session cookie, abuse rate limiting và CSRF cho toàn bộ flow; không tắt CSRF toàn bộ chỉ vì verification token.
- `httpBasic()` chỉ để dễ minh họa xác thực qua MockMvc. Với browser thật, ưu tiên login form/session và CSRF phù hợp; không gửi plaintext password trên HTTP, luôn dùng HTTPS.

### 10.5. REST controller nhận dữ liệu rõ kiểu, không nhận status từ client

`src/main/java/demo/lifecycle/LifecycleController.java`:

~~~java
package demo.lifecycle;

import java.security.Principal;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LifecycleController {
    private final AccountService service;

    public LifecycleController(AccountService service) {
        this.service = service;
    }

    public record RegisterRequest(
            @NotBlank @Email String email,
            @NotBlank @Size(min = 12, max = 100) String password) {}

    public record VerifyRequest(@NotBlank String token) {}

    @PostMapping("/account/register")
    public ResponseEntity<Map<String, String>> register(
            @Valid @RequestBody RegisterRequest body) {
        service.register(body.email(), body.password());

        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(Map.of("message",
                        "Neu yeu cau hop le, huong dan se duoc gui."));
    }

    @PostMapping("/account/verify")
    public ResponseEntity<Map<String, String>> verify(
            @Valid @RequestBody VerifyRequest body) {
        if (!service.verify(body.token())) {
            return ResponseEntity.badRequest()
                    .body(Map.of("status", "INVALID_OR_EXPIRED"));
        }
        // Verification không tạo login session.
        return ResponseEntity.ok(Map.of("status", "VERIFIED"));
    }

    @GetMapping("/account/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("username", principal.getName());
    }
}
~~~

Controller công khai chỉ cho nhập `email`, `password` và `token`. Không có trường `role`, `verified` hay `status`, nên client không thể yêu cầu kích hoạt qua mass assignment. Production phải bổ sung giới hạn kích thước request, abuse controls, telemetry an toàn và xử lý lỗi để không rò thông tin tài khoản.

**Lưu ý:** endpoint verify trả “INVALID_OR_EXPIRED” cho token không dùng được mà không nói token thuộc email nào. Một response thực tế có thể dùng trang hỗ trợ resend và không tiết lộ thông tin thêm.

### 10.6. Integration test xác nhận lifecycle và one-time token

`src/test/java/demo/lifecycle/AccountActivationTest.java`:

~~~java
package demo.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AccountActivationTest {
    @Autowired MockMvc mvc;
    @Autowired DemoMailbox mailbox;

    @Test
    void pendingCannotLoginAndVerificationActivatesOnce() throws Exception {
        String email = "learner@example.test";
        String password = "lab-password-long-123";

        mvc.perform(post("/account/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"learner@example.test",
                                 "password":"lab-password-long-123"}
                                """))
                .andExpect(status().isAccepted());

        mvc.perform(get("/account/me").with(httpBasic(email, password)))
                .andExpect(status().isUnauthorized());

        String rawToken = mailbox.readForTest(email);
        org.junit.jupiter.api.Assertions.assertNotNull(rawToken);

        mvc.perform(post("/account/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"token\":\"" + rawToken + "\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("VERIFIED"));

        mvc.perform(get("/account/me").with(httpBasic(email, password)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value(email));

        mvc.perform(post("/account/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"token\":\"" + rawToken + "\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void wrongTokenDoesNotActivate() throws Exception {
        mvc.perform(post("/account/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"reader@example.test",
                                 "password":"reader-password-long-123"}
                                """))
                .andExpect(status().isAccepted());

        mvc.perform(post("/account/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"token\":\"invalid-token\"}"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/account/me")
                        .with(httpBasic("reader@example.test",
                                "reader-password-long-123")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void duplicateRegistrationHasSamePublicResponse() throws Exception {
        String body = """
                {"email":"repeat@example.test",
                 "password":"another-password-123"}
                """;

        for (int attempt = 0; attempt < 2; attempt++) {
            mvc.perform(post("/account/register")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body))
                    .andExpect(status().isAccepted())
                    .andExpect(jsonPath("$.message")
                            .value("Neu yeu cau hop le, huong dan se duoc gui."));
        }
    }
}
~~~

Chạy test với Gradle đã cài hoặc wrapper đã tạo:

~~~bash
gradle test
# Nếu project có Gradle Wrapper:
./gradlew test
# Windows:
# gradlew.bat test
~~~

Kỳ vọng **3 test pass**:
- Account PENDING bị chặn dù mật khẩu đúng; token đúng kích hoạt; sau đó login được; token cũ không dùng lần thứ hai.
- Token sai không kích hoạt.
- Đăng ký email đã tồn tại vẫn có public response cùng status/message.

Không cam kết nguyên văn stdout của Gradle vì console/cache/version có thể khác; các assertion là bằng chứng thực tế. Đây là **lab in-memory một JVM**, không có gửi email thật. Để xem workflow thực với mail provider, phải thay DemoMailbox bằng integration thử nghiệm và không expose readForTest trên môi trường deployed.

## 11. Kiểm thử token expiry/resend, concurrency và abuse

Các test trong mục 10 thể hiện core behavior. Trước production cần thêm:

| Case | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Token hết hạn | `now >= expiresAt` | Không activate; cho phép resend theo policy |
| Token sai | Digest không có trong DB | Không activate; không rò account |
| Token dùng lại | Đã `consumed_at` | Không activate lần hai |
| Token của account khác | Challenge gắn A, client cố gắn B | Không chuyển B sang ACTIVE |
| Account đã `SUSPENDED` | Nộp token đăng ký cũ | Không mở lại account |
| Email đã thay | Token gửi đến email cũ | Không xác minh email mới |
| Hai verify đồng thời | Cùng raw token | Chỉ **một** request thắng; transition/consume atomic |
| Hai register đồng thời | Cùng normalized contact | Unique constraint tạo tối đa một account |
| Resend liên tục | Nhiều yêu cầu đến cùng email/IP | Rate limit và cooldown; không spam gửi mail |
| Token từ flow khác | Password reset token nộp ở verify email | Bị từ chối theo `purpose` |
| Password đúng, account PENDING | HTTP login | Bị từ chối vì `isEnabled() == false` |
| Password đúng, account ACTIVE | HTTP login | Có thể xác thực, còn cần quyền nghiệp vụ |
| Brute-force OTP | Đoán mã nhiều lần | Throttle/lock/abuse mitigation |
| Email spoof/mismatch | Mail link dùng host lạ hoặc contact khác | Không chấp nhận/cấp quyền |
| GET link do scanner | Bot mở email trước user | Không tiêu thụ token và không tự đăng nhập |
| Timezone/clock skew | Đúng biên expiration | Policy nhất quán, dùng UTC/Clock injection khi test |
| Restart/node failover | Challenge/session phân tán | Không mất token hoặc tạo double-use |

**Test clock:** thay `Instant.now()` bằng `Clock` được inject trong service thực để kiểm tra đúng ranh giới expiry mà không cần `Thread.sleep()`. Test không nên phụ thuộc thời gian chờ ngẫu nhiên hoặc thứ tự chạy.

**Test race:** dùng database thật hoặc integration môi trường nhiều instance để kiểm tra row locks/conditional updates. `synchronized` trong demo chỉ an toàn trong tiến trình hiện tại; không có tác dụng qua nhiều pod.

**Test user enumeration:** không chỉ so message. Kiểm tra cả response code, response body, thời gian xử lý, hạn mức, resend và kênh phụ; những khác biệt lớn có thể tiết lộ account đã có.

## 12. Tại sao account phải được kích hoạt trước khi login?

Lỗi phổ biến là tạo account mới với `enabled=true` rồi gửi email verification sau. Lúc đó email chỉ còn là “nhắc việc”; tài khoản đã có thể đăng nhập hoặc dùng API trước khi xác minh.

Trong Spring Security, login handler có thể đọc `UserDetailsService`; `DaoAuthenticationProvider` kiểm tra password và các điều kiện account như enabled/locked/expired. **Hãy lấy status từ nguồn dữ liệu đáng tin cậy** để `isEnabled()` phản ánh đúng `ACTIVE`. Nếu dùng custom JWT authentication:
- Không chỉ xác minh chữ ký token rồi bỏ qua account status khi policy đòi revoke nhanh.
- Cân nhắc token TTL ngắn, session revocation, token version hoặc introspection; phân quyền theo account hiện hành.
- Khi một account vừa active, không tự cấp role cao chỉ vì email được xác minh.
- Khi account bị suspended, thu hồi khả năng truy cập phù hợp với yêu cầu nghiệp vụ, kể cả session/tokens đã phát trước.

Sự khác biệt:
- **Authentication**: credential hợp lệ và account đủ điều kiện dùng.
- **Authorization**: tài khoản được phép làm gì, với dữ liệu nào.
- **Contact verification**: liên hệ có được chứng minh quyền kiểm soát ở một thời điểm không.
- **Activation**: một chuyển trạng thái nghiệp vụ, không phải tự động Authentication.

Nếu có SSO/OIDC/SAML, thông tin `email_verified` từ IdP có thể được dùng **chỉ khi** issuer và claim đã được xác thực, trust contract và user linking đúng. Không chấp nhận một field `email_verified=true` do frontend tự gửi như bằng chứng độc lập.

## 13. Gửi lại xác minh, thay đổi liên hệ và reactivation

### 13.1. Resend

Endpoint `POST /account/verification/resend` nên:
- Trả cùng message chung cho email tồn tại/không tồn tại/đã active, không tiết lộ trạng thái.
- Áp dụng cooldown theo account/contact/IP, hạn số lượt trong thời gian và anti-bot khi cần.
- Nếu account đang PENDING, tạo **token mới** và vô hiệu token trước; chỉ gửi tới contact đang chờ xác minh.
- Không reset password/role/status hoặc tự tạo account thứ hai do resend.
- Không đưa token vào response/log; sử dụng mail provider với retry và delivered status riêng.
- Theo dõi email bounce và các địa chỉ có thể bị lạm dụng để spam người khác.

Nếu user không nhận được mail, hướng dẫn kiểm tra spam/quarantine, nhập đúng email và yêu cầu resend sau cooldown. Không đưa ra phản hồi phân biệt “địa chỉ đó đã có tài khoản” công khai.

### 13.2. Đổi email khi account đang ACTIVE

Đổi email là **thay đổi kênh khôi phục/định danh**, có rủi ro account takeover. Một workflow phổ biến:
1. Yêu cầu user đã authenticated **reauthenticate** khi thay đổi nhạy cảm.
2. Lưu `pending_new_email` riêng; chưa ghi đè verified email hiện tại.
3. Gửi thông báo tới email cũ và mã xác minh tới email mới; với hệ thống nhạy cảm có thể yêu cầu xác nhận cả hai.
4. Xác minh token có purpose `VERIFY_NEW_EMAIL`, bound với account và pending email, single-use và expiry.
5. Trong transaction, chuyển email mới thành verified, cập nhật uniqueness, revoke challenge cũ và audit.
6. Gửi thông báo xác nhận thay đổi, cung cấp phương án thu hồi nếu bất thường.

**Tuyệt đối không** lấy một token `VERIFY_SIGNUP_EMAIL` gửi cho email cũ rồi cho nó kích hoạt email mới. Contact snapshot/purpose là chốt chống race và lẫn flow.

### 13.3. Re-enable account suspended

Một tài khoản bị suspend do security event/vi phạm chính sách **không tự trở lại ACTIVE** bằng email verification link cũ. Cần policy riêng: review, self-service recovery đã được phê duyệt, MFA/re-authentication, reset credential, staff approval và session revocation nếu cần.

Nếu một người bị xóa rồi đăng ký lại bằng email cũ, hệ thống phải quyết định liệu đó là cùng identity hay một identity mới. Email có thể được tái cấp; **không tự phục hồi dữ liệu tài khoản cũ chỉ dựa trên khả năng đọc email**.

## 14. Rủi ro bảo mật thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Account được tạo `ACTIVE` trước verification | Người đăng ký bằng email người khác có thể login | PENDING trước, verify xong mới xét activation |
| Token là `userId+timestamp` dễ đoán | Attacker đoán/bypass bước xác minh | CSPRNG 256 bit, digest, expiry/single-use |
| Lưu raw token trong database/log | Rò token từ DB/observability | Chỉ lưu digest; bảo vệ mail payload/outbox |
| GET link tự kích hoạt | Email scanner/prefetch có thể consume token | GET chỉ render, POST xác nhận |
| Token không ràng buộc purpose/account/email | Có thể dùng nhầm hoặc chiếm account | Purpose + contact snapshot + state check |
| Resend giữ tất cả token cũ còn hiệu lực | Tăng bề mặt tấn công và race | Vô hiệu token trước theo policy |
| `SELECT` rồi `UPDATE` không transaction/lock | Verify race, double use | Atomic update, row lock, unique constraint |
| Phản hồi “email đã đăng ký” công khai | User enumeration | Generic response, rate limit và timing controls |
| Email normalize tùy tiện | Gộp nhầm account, identity confusion | Policy canonicalization rõ, uniqueness đồng bộ |
| Link tạo từ Host header request | Host header poisoning, link bị hướng tới domain attacker | Public URL cố định từ trusted config |
| Token ở URL bị gửi qua analytics/referrer | Lộ bearer verifier | HTTPS, no-referrer/no-store, không third-party; redirect sạch |
| Sau verify tự tạo session ADMIN | Privilege escalation | Verification không phải login và không cấp role |
| Check `enabled` chỉ ở password login | Các cơ chế SSO/token khác bypass suspension | Central status policy mọi auth flow |
| Không giới hạn số email gửi | Email bombing/spam/cost | Rate limit, cooldown, abuse monitoring |
| Không quản lý mail failure | Người dùng bị kẹt PENDING | Outbox, retry, resend và help path |
| Tin `email_verified` do frontend gửi | Bypass verification | Chỉ chấp nhận bằng chứng từ server/IdP đã xác thực |
| Kích hoạt bằng SMS 6 số không throttle | OTP brute-force | Throttle, attempts/TTL giới hạn, hashed OTP |
| Không thu hồi session sau disable | Account bị khóa vẫn truy cập được | Session/token lifecycle, revoke theo SLA |

## 15. Quan sát, bảo mật dữ liệu và vận hành

**Các log nên có:** request ID/correlation ID, event type (`REGISTER_REQUESTED`, `VERIFICATION_SENT`, `VERIFICATION_FAILED`, `ACTIVATED`, `SUSPENDED`), actor/tenant đã được phép, lý do lỗi nội bộ đã phân loại, delivery queue status và timestamp UTC.

**Không log:** mật khẩu, raw verification token, toàn bộ verification URL, OTP, session cookie, toàn bộ email/địa chỉ liên hệ nếu không có cơ sở hợp lệ. Có thể mask/hmac định danh để phân tích abuse trong thời gian retention cho phép; đừng đưa secret vào analytics/traces.

**Metrics hữu ích:** số đăng ký, tỷ lệ xác minh trong TTL, số mail không giao được, số resend/ngày, tỷ lệ expired/invalid token, thời gian từ register đến activated, số attempt nghi abuse và sự cố mail provider. Bảo vệ dữ liệu đo lường vì chúng có thể cho biết tình trạng tài khoản.

**Chính sách retention:** account PENDING không được xác minh sau một thời gian cần được dọn dẹp hoặc đưa vào quy trình xử lý theo luật/policy; không giữ vô thời hạn. Verification tokens đã hết hạn/tiêu thụ nên được xóa theo retention. Khi hủy account, xử lý dữ liệu, session và email liên hệ theo yêu cầu pháp lý.

**Triển khai sau proxy:** luôn dùng URL công khai có HTTPS, trust `Forwarded`/`X-Forwarded-*` chỉ từ reverse proxy đã kiểm soát; không cho attacker đưa host tùy ý vào verification link. Hạn chế URL logging và áp dụng CSP/cookie policy cho trang kích hoạt.

## 16. Bài tập và đáp án

**Câu 1.** Đăng ký thành công nhưng email chưa được người nhận xác minh. `UserDetails.isEnabled()` nên trả gì?  
**False** nếu policy yêu cầu xác minh trước kích hoạt. Không để login hợp lệ chỉ vì password đúng.

**Câu 2.** Link xác minh có token đúng, nhưng đã hết hạn đúng thời điểm hiện tại. Có thể chấp nhận?  
**Không.** Với điều kiện `now < expiresAt`, tại `now == expiresAt` là expired.

**Câu 3.** Một người dùng mở verification URL trong email, và phần mềm chống spam đã mở URL trước. Nên làm gì để tránh consume tự động?  
**Không kích hoạt chỉ với GET**; dùng trang xác nhận và POST khi người dùng chủ động hoàn tất.

**Câu 4.** Account đã ACTIVE, nộp lại token cũ. Có cần tạo session hay cập nhật verifiedAt?  
**Không.** Token đã dùng là invalid; không có quyền đăng nhập tự động.

**Câu 5.** User đổi email trong profile mà không xác minh email mới. Có thể giữ `emailVerifiedAt` cũ không?  
**Không được xem như xác minh email mới.** Cần pending contact, challenge mới và quy trình reauth/notify phù hợp.

**Câu 6.** Server chỉ lưu `SHA-256(token)` nhưng lưu password người dùng cũng bằng SHA-256 thuần. Có an toàn?  
**Không.** Token ngẫu nhiên mạnh và password do con người chọn có entropy khác nhau. Password cần adaptive password hashing/`PasswordEncoder`.

**Câu 7.** Một người đăng ký bằng email của người khác, đoán được URL xác minh?  
Với token CSPRNG dài, xác suất đoán được rất nhỏ; còn cần rate limit và không rò token. Nhưng **phải xử lý** trường hợp email bị chiếm, forwarded hoặc tái cấp; email verification không chứng minh danh tính pháp lý.

**Câu 8.** Account bị khóa vì gian lận, người dùng còn một link verify cũ. Có được mở khóa?  
**Không.** Transition `SUSPENDED → ACTIVE` phải qua policy riêng, không qua verification lần đầu.

### Checklist phát hành

- [ ] Tài khoản mới ở trạng thái chờ; server không tin trạng thái/role từ client.
- [ ] Password được lưu bằng adaptive `PasswordEncoder`.
- [ ] Email canonicalization và unique constraint được thiết kế nhất quán.
- [ ] Token CSPRNG đủ entropy, đúng purpose/account/contact, TTL hữu hạn, single-use và lưu digest.
- [ ] Consume token + activate account nguyên tử trên DB, chống request đồng thời.
- [ ] Delivery có outbox/retry; không lộ raw token trong logs/API/analytics.
- [ ] Link dùng HTTPS, trusted public domain, không consume ở GET scanner.
- [ ] Đăng ký/resend có generic response, rate limit, cooldown và anti-enumeration.
- [ ] `UserDetails.isEnabled()` hoặc policy chung chặn mọi auth method cho account chưa active.
- [ ] Email change, reactivation, account recovery và password reset là flow riêng.
- [ ] Có test negative, expiry, replay, concurrent verification, wrong account/contact, disable.
- [ ] Session/token đã cấp trước khi disable được xử lý theo SLA.
- [ ] Dữ liệu PENDING, token expired và PII có retention chính sách.

## 17. Nguồn tham khảo

- [OWASP — Email Validation and Verification Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html): canonicalization, quyền kiểm soát email, token dùng một lần, chống enumeration và flow đổi email.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): user identifiers, password/authentication, chống dò tài khoản.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): nguyên tắc token ngẫu nhiên, TTL, sử dụng một lần, thông báo trung tính; áp dụng những nguyên tắc tương tự nhưng **không dùng chung token reset và verify**.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): DelegatingPasswordEncoder/adaptive hashing.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): UserDetailsService + PasswordEncoder khi xác thực.
- [Spring Security 6.5 — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): enabled, account non-locked/expired và credential checks.
- [Spring Boot 3.3 Reference](https://docs.spring.io/spring-boot/3.3/reference/): cấu hình và kiểm thử project Spring Boot 3.3.x.

**Ghi nhớ:** Đăng ký là tạo **yêu cầu tài khoản**, xác minh liên hệ là xác nhận **quyền truy cập kênh liên hệ**, và kích hoạt là **quyết định trạng thái nghiệp vụ**. Hãy chỉ cho đăng nhập khi account đủ điều kiện, token xác minh ngẫu nhiên/hết hạn/dùng một lần và các chuyển trạng thái được thực hiện nguyên tử, có kiểm thử âm tính.