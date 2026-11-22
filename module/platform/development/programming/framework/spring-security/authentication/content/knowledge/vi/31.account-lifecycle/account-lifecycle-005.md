# Đặt lại mật khẩu với token độc lập với token đăng nhập

> **Bối cảnh:** Spring Security – Authentication, nhóm **Vòng đời tài khoản**. Bài học hướng dẫn thiết kế quy trình **forgot/reset password** cho tài khoản có mật khẩu nội bộ. Trọng tâm: **reset token chỉ có một quyền rất hẹp — đổi mật khẩu sau khi được xác minh — và tuyệt đối không phải login/access token**. Ví dụ Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet stack) và PostgreSQL; các đoạn tích hợp Spring cần được ghép với repository, email, database và phiên người dùng của dự án thực tế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **password reset**, **password change**, **email verification**, **magic login**, **OAuth2 access token**, **refresh token**, HTTP session và reset token.
2. Giải thích vì sao việc **tái sử dụng token đăng nhập cho reset** hoặc để **reset token đăng nhập thẳng** làm xuất hiện rủi ro chiếm đoạt tài khoản.
3. Thiết kế reset token ngẫu nhiên có entropy cao, TTL ngắn, **purpose riêng**, lưu hash, dùng một lần và được xác minh trong một transaction.
4. Chọn nguồn email nhận link đã được xác minh, gửi phản hồi trung tính để chống **account enumeration**, chống spam và xây URL từ hostname công khai được cấu hình.
5. Cập nhật password bằng Spring Security `PasswordEncoder`, chặn replay, đảm bảo **đổi mật khẩu và tiêu thụ token cùng thành công hoặc cùng rollback**.
6. Giải quyết các vấn đề khó: hai request reset đồng thời, nhiều reset token chưa dùng, thay đổi email, khóa account, session/token cũ, MFA và account recovery.
7. Viết kiểm thử bảo mật cho tính **phân tách quyền**, hạn dùng, race condition, xác thực lại, session revocation, token leakage và trạng thái tài khoản.

## 1. Bối cảnh: quên mật khẩu không phải là đăng nhập

Người dùng `lan` quên mật khẩu. Ứng dụng cho nhập email đã đăng ký, gửi link:

```text
https://account.example.org/password/reset?token=BASE64URL_RANDOM_SECRET
```

Người nắm link trong khoảng thời gian hợp lệ có thể nộp token **tại endpoint reset** để đặt mật khẩu mới cho đúng account gắn với token. Đây là một cơ chế **khôi phục quyền kiểm soát tài khoản**, không phải phiên làm việc thông thường.

**Điểm thiết kế cốt lõi:** token reset phải **độc lập về ngữ nghĩa, nơi lưu trữ, phạm vi quyền, TTL, cách tiêu thụ và trạng thái thu hồi** so với token được sử dụng để đăng nhập hoặc gọi API.

```text
                 ┌────────────────────┐
                 │ Người dùng quên mật│
                 │ khẩu, nhập email   │
                 └─────────┬──────────┘
                           │
                           ▼
                  POST /password/forgot
                           │
                 Tạo PASSWORD_RESET secret
                           │
                           ▼
                  Email chứa reset link
                           │
                GET /password/reset?token=...
                           │
             Chỉ hiển thị form, không đăng nhập
                           │
              POST /password/reset + CSRF
                           │
         Verify purpose, subject, TTL, single-use
                           │
            Transaction: đổi hash + dùng token
                           │
                      Commit thành công
                           │
        Thu hồi/đánh dấu lại phiên, gửi thông báo
                           │
             Yêu cầu đăng nhập bình thường
```

**Không** làm:

```text
Có reset token  → coi như Bearer access token
Có reset token  → tạo SecurityContext / ROLE_USER ngay
Đang có session → cho đổi password từ "forgot password" mà không
                  xác minh password cũ hoặc reset token riêng
Reset xong      → tự động phát JWT mới và đăng nhập không kiểm soát
```

Việc reset password được xem là thao tác nhạy cảm vì nó có thể thay đổi khả năng đăng nhập của chủ tài khoản. **Chứng minh quyền kiểm soát hộp thư đã xác minh** qua một token reset **không đương nhiên** chứng minh toàn bộ các yếu tố MFA khác; không cho dùng reset flow để tắt MFA hoặc thay thế security key bằng cách đi đường vòng.

## 2. Bảng so sánh các loại token và tính độc lập

| Credential / Token | Được cấp khi nào? | Dùng để làm gì? | Tuyệt đối không được dùng để |
|---|---|---|---|
| **Password reset token** | User yêu cầu khôi phục, server gửi tới contact đã xác minh | Đặt mật khẩu mới **một lần**, trước khi hết hạn | Đăng nhập, gọi API, đổi email, tắt MFA, nhận role |
| HTTP session ID | Sau khi login thành công (hoặc session trước login bị giới hạn) | Nhận diện phiên web có quyền đã xác minh | Thay reset token trong luồng quên mật khẩu |
| OAuth2 access token/JWT | Sau OAuth2 grant | Gọi API có audience/scope đã cấp | Thay reset token hoặc dùng làm mật khẩu |
| OAuth2 refresh token | Theo grant/IdP | Xin access token mới theo policy | Đặt mật khẩu nội bộ mà không có xác thực recovery riêng |
| Magic-login token | Khi ứng dụng chủ ý phát token dùng một lần cho **đăng nhập** | Xác thực đăng nhập theo chính sách | Tự động biến thành reset password token |
| Email verification token | Khi cần chứng minh quyền kiểm soát một email cụ thể | Xác minh **địa chỉ** | Đăng nhập, reset password, đổi địa chỉ khôi phục khác |
| Change-password action | User đã đăng nhập và xác thực lại (old password/MFA tùy policy) | Đổi password tài khoản đang sở hữu | Vượt qua policy quên mật khẩu hoặc dùng token của người khác |

**Nguyên tắc purpose separation:** cùng một chuỗi bí mật không được có cả hai ý nghĩa “tôi được phép đổi mật khẩu” và “tôi đã đăng nhập”. Có thể dùng cùng một hạ tầng cơ sở dữ liệu/queue nhưng các record cần **type/purpose**, endpoint và verifier tách biệt. An toàn hơn là **namespace/bảng riêng** cùng policy riêng cho reset.

### 2.1. Tại sao dùng chung token nguy hiểm?

Xét các sai lầm:

- Lấy JWT access token rồi đưa vào `POST /password/reset`, chỉ kiểm tra signature/`sub` và cho đổi password: bất cứ client hoặc thiết bị bị lộ access token đều có thể **chiếm tài khoản dài hạn** bằng đổi password. Audience/scope login không chứng minh ý định khôi phục mật khẩu.
- Lấy reset token gửi email rồi gắn vào `Authorization: Bearer ...` và cho API chấp nhận: token khôi phục trong email biến thành một credential có toàn bộ quyền của user, dù chưa hề hoàn tất đăng nhập hay MFA.
- Dùng một bảng `tokens(token_value,user_id,expires_at)` cho cả email verification, password reset và login mà không kiểm tra `purpose`: token phát cho tác vụ nhẹ có thể bị dùng cho tác vụ mạnh hơn (**cross-purpose token confusion**).
- Dùng signed JWT reset token không theo dõi `jti`/consumed-state: token còn chữ ký/hạn sử dụng có thể đổi mật khẩu nhiều lần, trái cam kết “một lần”.
- Dùng access token của IdP bên ngoài để tự đặt lại local password không qua policy nội bộ: làm lẫn ranh giới account, provider và tenant.

**Biện pháp:** reset verifier **chỉ** nhìn vào reset-token store/cấu trúc có purpose `PASSWORD_RESET` và trạng thái còn dùng; login verifier **không** tham chiếu reset-token store. Ngay cả khi hai chuỗi vô tình có hình thức giống nhau, hệ thống phải từ chối việc dùng sai kênh.

### 2.2. Cùng một `userId` không có nghĩa cùng một quyền

Một reset token thường gắn với `local_user_id=42`, giống dữ liệu session hoặc JWT `sub=42`. Nhưng `userId` chỉ là **đối tượng** mà credential nói tới, không phải quyền. Để cấp quyền, phải xác minh **loại credential, người phát hành, mục đích, thời gian, đối tượng, trạng thái và chính sách**.

Không dùng `Authentication.isAuthenticated()==true` của một phiên sơ cấp hay một JWT đã giải mã để bỏ qua reset-token policy. Việc **biết ai** và **được làm gì** là hai khía cạnh khác nhau.

## 3. Luồng chuẩn an toàn khi người dùng quên mật khẩu

### Bước A — Nhận yêu cầu khôi phục

User mở `GET /password/forgot` rồi gửi form `POST /password/forgot` với email/username. Server **không** xác thực người gửi request bằng việc họ nhập một email có tồn tại.

- Chuẩn hóa định danh theo quy tắc ứng dụng (ví dụ quy tắc email đã lưu) nhưng không tự thay đổi chủ sở hữu account vì dấu cộng/dấu chấm ở Gmail hoặc Unicode.
- Tra tài khoản theo **user store** và chỉ chọn **contact khôi phục đã được xác minh** theo chính sách. Không gửi token tới email mới tự nhập trong form nếu chưa được gắn xác minh với account.
- Trả cùng thông điệp cho account tồn tại hoặc không tồn tại: “Nếu tài khoản có thể khôi phục, chúng tôi sẽ gửi hướng dẫn tới kênh đã đăng ký”.
- Tránh khác biệt quá lớn về thời gian, status/body giữa hai trường hợp. Có thể dùng queue và xử lý bất đồng bộ với giao diện trung tính.
- Rate-limit theo account/contact, IP, thiết bị, ASN/risk signal và số lượng thư. Tránh để request reset làm khóa ngay account của nạn nhân hoặc spam inbox.
- Không đổi password, không vô hiệu hóa account, không cập nhật `last_login` và không tạo session ngay lúc yêu cầu link.

OWASP Forgot Password Cheat Sheet đề nghị response nhất quán, hạn chế enumeration và **chỉ thay đổi trạng thái tài khoản sau khi đã có bằng chứng reset hợp lệ**.

### Bước B — Phát token phục hồi riêng

Nếu tài khoản đáp ứng chính sách, server tạo bí mật bằng **cryptographically secure pseudorandom number generator (CSPRNG)**, ví dụ `SecureRandom` 32 byte (256 bit), mã Base64url không padding để dùng trong URL.

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class PasswordResetSecret {
    private static final SecureRandom RANDOM = new SecureRandom();

    private PasswordResetSecret() {}

    public static String issueRawSecret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
    }
}
```

**Lưu ý:** class Java trên chỉ tạo bí mật ngẫu nhiên; **chưa phải quy trình reset**. Bạn còn phải lưu hash ở server, gắn user ID, purpose, TTL, phiên bản credential và thực hiện consume nguyên tử.

**Không** dùng `Math.random()`, timestamp, UUID dễ đoán theo cách triển khai yếu, email/username, hash của password hiện tại, hoặc access token/JWT session đã có để làm reset token. Không đặt secret vào logs, telemetry, analytics hay exception message.

### Bước C — Lưu token ở server với quyền hạn hẹp

Mô hình lưu trữ đề nghị:

```text
token_hash           = SHA-256(raw secret 256-bit) hoặc HMAC-SHA-256
purpose              = PASSWORD_RESET
local_user_id        = 42
credential_version   = 7
contact_version      = 3 (nếu cần kiểm tra email recovery đã đổi)
created_at           = ...
expires_at           = ...
consumed_at          = null
requested_context    = audit metadata, không phải raw token
```

- **Hash secret, không lưu raw secret**. Với token ngẫu nhiên 256-bit, SHA-256 đủ để không thể dò ngược thực tế từ database; HMAC còn giúp tách namespace và hạn chế phân tích trên một số threat model. Không lạm dụng `PasswordEncoder` chậm để hash token 256-bit cần tra cứu trực tiếp: hash SHA-256/HMAC có rủi ro khác với password do người đặt (entropy thấp).
- Chọn TTL **ngắn và phù hợp kênh email** (ví dụ 10–30 phút theo policy; không phải con số bắt buộc từ framework). TTL không thay cho cơ chế **one-time use**.
- Mỗi token liên kết **một local user ổn định** và **một mục đích**, không dựa vào email hiển thị để định chủ.
- Nếu account đổi password hoặc contact khôi phục trong lúc token đang sống, có thể dùng `credential_version`/`contact_version` để vô hiệu token phát trước đó, bảo vệ khỏi link cũ.
- Có thể giới hạn chỉ token mới nhất được phép dùng, hoặc nhiều token cùng sống nhưng **đổi password lần đầu làm các token còn lại vô hiệu** thông qua version/transaction. Chọn chính sách rõ, test concurrency.

### Bước D — Gửi liên kết đến đúng nguồn liên hệ

Ứng dụng sinh link bằng **canonical public origin** được cấu hình, ví dụ:

```text
https://account.example.org/password/reset?token=<random-base64url>
```

Không ghép scheme/host từ `HttpServletRequest.getServerName()`, `Host`, `Forwarded`, `X-Forwarded-Host` do client có thể tác động, nhất là phía sau reverse proxy. **Host Header Injection** có thể làm thư reset trỏ đến domain attacker và tiết lộ secret.

Địa chỉ nhận phải lấy từ bản ghi contact đủ điều kiện trong kho user, không phải giá trị email tùy ý ở request. Nếu có nhiều tenant/custom domains, dùng mapping **tenant đã xác minh → origin HTTPS được quản trị**; không dùng chuỗi domain chưa kiểm chứng từ người dùng.

Email chỉ chứa một lần link, diễn giải thời hạn và cảnh báo nếu không yêu cầu; không gửi mật khẩu mới qua email.

### Bước E — Mở link: không đổi password bằng GET

`GET /password/reset?token=...` nên **chỉ** hiển thị form nhập mật khẩu mới, kiểm tra sơ bộ format/expiry nếu cần và thiết lập các response headers an toàn; nó **không nên** đổi password hoặc tự đăng nhập.

Vì hệ thống email có scanner/prefetch tự mở link, việc tiêu thụ token ngay khi GET có thể làm hỏng trải nghiệm và tạo cơ hội lạm dụng. Bước thay đổi thật nên là một **POST được bảo vệ CSRF phù hợp**, chứa raw secret do user nộp từ form và password mới. Khi request POST tới, server verify và tiêu thụ atomically.

Response cho token sai/hết hạn/đã dùng nên thống nhất, không tiết lộ người sở hữu link. Giao diện chỉ dẫn người dùng yêu cầu link mới.

### Bước F — POST xác minh token và đặt mật khẩu mới

Với `POST /password/reset`, backend thực hiện:

1. Kiểm tra request size, input và CSRF; áp chính sách giới hạn lần thử.
2. Băm raw reset secret đúng cơ chế và tra **password reset store**; tuyệt đối không hỏi API login token validator.
3. Kiểm tra `purpose=PASSWORD_RESET`, thời hạn, `consumed_at IS NULL`, user/contact/credential version hợp lệ, account trạng thái cho phép reset.
4. Kiểm tra mật khẩu mới theo chính sách (độ dài, compromised/common passwords, danh sách cấm; tránh quy tắc composition không cần thiết); nếu có xác nhận lại mật khẩu, so khớp hai ô.
5. Mã hóa password bằng `PasswordEncoder` được quản lý (Argon2id/bcrypt/PBKDF2/scrypt theo policy) và lưu **hash**, không lưu plain text.
6. Trong **cùng transaction**: nhận quyền tiêu thụ token một lần, lock/check user, cập nhật password hash, tăng phiên bản credential, làm vô hiệu các reset tokens cũ theo chính sách.
7. Commit thành công rồi **không tự đăng nhập**. Hướng người dùng về login thông thường; nếu MFA được bật, yêu cầu MFA như trước.
8. Gửi thông báo đổi password tới contact đã đăng ký; **không gửi raw password**. Thu hồi/đánh giá lại session, refresh token, remember-me, recovery grants theo policy và đảm bảo các API thực sự tôn trọng thu hồi.

Nếu thao tác thay password thất bại, transaction phải rollback **cả việc tiêu thụ token**. Đừng đánh dấu token đã dùng, gọi database cập nhật password ở transaction khác rồi lỡ để hệ thống ở trạng thái nửa thành công.

## 4. Cơ sở dữ liệu: tách biệt password reset và login credential

Giả định bảng `local_users` có khóa `id`, `password_hash`, `credential_version`, `recovery_contact_version` và trạng thái tài khoản phù hợp. Ví dụ PostgreSQL:

```sql
CREATE TABLE password_reset_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_hash BYTEA NOT NULL UNIQUE,
    local_user_id BIGINT NOT NULL REFERENCES local_users(id),
    purpose VARCHAR(32) NOT NULL DEFAULT 'PASSWORD_RESET',
    credential_version BIGINT NOT NULL,
    recovery_contact_version BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CONSTRAINT reset_purpose_only CHECK (purpose = 'PASSWORD_RESET'),
    CONSTRAINT reset_expiry_valid CHECK (expires_at > created_at)
);

CREATE INDEX password_reset_user_idx
    ON password_reset_tokens(local_user_id);

CREATE INDEX password_reset_expiry_idx
    ON password_reset_tokens(expires_at);
```

**Giải thích schema:**

- `token_hash` là digest của **raw reset secret**, không phải password hash; dùng `BYTEA` 32 byte cho SHA-256.
- `purpose` cố định là `PASSWORD_RESET`; nếu dùng bảng riêng, ràng buộc này giúp bảo vệ invariant và ngăn confusion.
- `credential_version` và `recovery_contact_version` là các thuộc tính phiên bản hiện tại của account lúc phát token. Việc tăng các giá trị này có thể làm các reset link cũ mất hiệu lực mà không cần tìm/xóa từng token.
- `expires_at`/`consumed_at` là điều kiện bắt buộc; có index để cleanup token đã hết hạn, nhưng việc cleanup **không thay cho xác minh hạn ở lúc dùng**.
- `local_user_id` là khóa nội bộ; thay đổi email hiển thị không chuyển ownership token.
- Không cho user tùy ý chọn `user_id` bằng request body trong bước hoàn tất; owner **phải đọc từ record reset token**.

Bảng login tokens / session của ứng dụng (nếu có) **khác** bảng này:

```text
password_reset_tokens:
  token_hash → local_user_id, purpose=PASSWORD_RESET, expires_at, used_at

http_sessions / access_tokens / refresh_tokens:
  session_id hoặc bearer credential → authenticated principal, quyền,
  thời hạn, audience, revoked_state theo từng cơ chế

Không có truy vấn/validator nào dùng hàng password_reset_tokens
để tạo principal đăng nhập trực tiếp.
```

### 4.1. Atomic consume để chống replay

Không viết:

```text
SELECT token WHERE consumed_at IS NULL
if found:
    updatePassword()
    UPDATE token SET consumed_at=now()
```

Hai request có thể đọc cùng một token trước khi cùng cập nhật; nếu không có khóa/transaction, password có thể bị ghi đè hai lần. Với PostgreSQL, **claim token nguyên tử** trong transaction là cách khả thi:

```sql
UPDATE password_reset_tokens
SET consumed_at = CURRENT_TIMESTAMP
WHERE token_hash = :digest
  AND purpose = 'PASSWORD_RESET'
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP
RETURNING local_user_id,
          credential_version,
          recovery_contact_version;
```

Nếu trả **0 hàng**, token sai/hết hạn/đã dùng. Nếu trả một hàng, transaction **chưa commit**; backend còn phải:

- Khóa đúng `local_users` row qua `SELECT ... FOR UPDATE` (hoặc concurrency mechanism tương đương).
- So sánh `credential_version` và `recovery_contact_version` với giá trị hiện tại.
- Kiểm tra trạng thái tài khoản và password policy.
- Cập nhật `password_hash`, tăng credential version; bảo đảm không có một reset token phát cùng phiên bản nào dùng lại.
- Commit chỉ khi mọi bước trên thành công; exception phải rollback cả `consumed_at`.

**Nuance quan trọng:** nếu hai token khác nhau được cấp cho cùng user và cùng `credential_version`, hai transaction có thể cùng claim **hai row reset token khác nhau**. Khóa và so version của row `local_users` sau khi claim là yếu tố quyết định: transaction đổi password đầu tăng version, transaction sau thấy version không khớp và rollback. Chỉ dựa vào `UNIQUE(token_hash)` là chưa đủ để chặn hai link khác nhau cùng đổi password.

### 4.2. Session/token cũ sau khi đổi password

Đổi `password_hash` không tự làm mất hiệu lực tất cả những thứ sau:

- HttpSession/remember-me cookie đã đăng nhập từ trước.
- JWT access token đã được cấp có `exp` còn xa.
- OAuth2 refresh token, SSO session hoặc session ở thiết bị khác.
- Password reset token khác chưa dùng, nếu không có version/revocation.
- WebSocket connections hoặc API token riêng theo ứng dụng.

Đặt chính sách rõ: thường nên **thu hồi các phiên hiện có, refresh/remember-me tokens và recovery grants có liên quan** khi password reset thành công, hoặc ít nhất cho user lựa chọn “đăng xuất khỏi tất cả thiết bị” theo mức rủi ro. Với rủi ro account takeover, thu hồi trên diện rộng thường phù hợp hơn.

Cần triển khai **thực tế**:

- Spring HTTP session: xóa phiên trong session repository hoặc đánh dấu user `session_version` để filter/gate từ chối những phiên cũ.
- Stateless JWT: tăng claim/record `authz_version`/`session_version`, dùng denylist/introspection/TTL ngắn để Resource Servers chặn token cũ; chỉ thay password hash không sửa JWT.
- Remember-me: xoá persistent remember-me series/tokens hoặc tăng phiên bản tương ứng.
- Refresh token/IdP: gọi API thu hồi khi provider hỗ trợ; lưu ý có thể có propagation delay.

Nếu gọi một dịch vụ revoke ở mạng khác, giao dịch database địa phương **không làm atomic toàn hệ thống**. Có thể ghi **outbox event trong cùng transaction** để retry đáng tin cậy; đối với endpoint cần hiệu lực tức thời, ứng dụng/API phải kiểm tra trạng thái phiên bản dùng chung tại request, không chờ consumer sự kiện. Không tuyên bố “đã revoke ngay lập tức” khi chỉ gửi message bất đồng bộ.

## 5. URL khôi phục, Host Header Injection và token leakage

### 5.1. Canonical origin tin cậy

Ví dụ cấu hình deployment:

```yaml
app:
  password-reset:
    public-origin: ${PASSWORD_RESET_PUBLIC_ORIGIN:https://account.example.org}
    token-ttl: PT15M
```

`PASSWORD_RESET_PUBLIC_ORIGIN` là cấu hình do quản trị viên/secret deployment cung cấp, có kiểm tra HTTPS, hostname, không có userinfo/query/fragment hoặc path ngoài dự kiến. Với nhiều tenant, map origin từ tenant verified. **Không** tính link gửi email từ `request.getRequestURL()`, `Host`, `X-Forwarded-Host` hoặc bất kỳ header/URL do client gửi.

Email chỉ nên dẫn đến **domain chính thức** của ứng dụng. HTTPS bảo vệ link trên đường truyền, nhưng không bảo vệ nếu server cố tạo link sai domain do Host injection.

### 5.2. Raw token trong query là bí mật

Một URL chứa reset token có thể lộ qua browser history, email forwarding, link scanner, proxy access logs, WAF logs, APM, analytics, Referer hoặc screenshot. Bảo vệ các nơi đó:

```http
Referrer-Policy: no-referrer
Cache-Control: no-store
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'none'
```

Dòng CSP là ví dụ **phải điều chỉnh theo trang, nonce và asset thực tế**. Trên trang hiển thị reset token, tránh third-party JS, fonts, ảnh và analytics gửi full URL ra ngoài. Không log request query/cookies có token raw, không đưa token vào exception, trace IDs hoặc metrics labels. Sau khi reset, redirect đến đường không chứa token.

Cẩn thận với open redirect: không nhận `next=https://evil.example` rồi gọi `sendRedirect(next)`. Nếu cần điều hướng, dùng **mã đích được allowlist server-side** như `login → /login`; không chép lại token vào `Location`.

### 5.3. GET và link scanning

Mail gateway có thể tự mở link bằng GET. Bước `GET /password/reset?token=...` chỉ nên trả form, **không cập nhật account** hay auto-login/auto-consume token. Sau POST hợp lệ, tiêu thụ một lần và đổi password.

Nếu bạn cần tránh để token xuất hiện trong URL lâu, giao diện có thể dùng cách chuyển secret vào một bước POST an toàn rồi điều hướng tới URL sạch, nhưng phải kiểm soát CSRF, XSS và trình duyệt bị mất phiên. **Đừng** dùng JavaScript chạy ngay khi GET để tự đổi mật khẩu bằng token mà không có ý định người dùng.

## 6. Spring Security 6.x: cấu hình web endpoint phù hợp

Spring Security cung cấp xác thực, authorization, CSRF, session security và password encoding. **Forgot-password token issuance/redemption thường là logic ứng dụng tự xây dựng**; đừng nhầm với `oneTimeTokenLogin()` dùng cho mục đích đăng nhập, `OAuth2 token` dùng cho API hoặc `remember-me`.

### 6.1. Dependencies (Gradle, Spring Boot 3.x)

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Các thành phần JPA, email, database và form templates chỉ là những lựa chọn triển khai; có thể thay bằng JDBC/jOOQ/Redis hoặc mail provider khác theo kiến trúc dự án. Spring Security **không tự gửi email reset** nếu chỉ thêm starter.

### 6.2. Bean PasswordEncoder chuẩn

`src/main/java/com/example/security/PasswordEncodingConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordEncodingConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }
}
```

`PasswordEncoder.encode(newPassword)` dành để lưu mật khẩu mới. Spring Security `DelegatingPasswordEncoder` hỗ trợ nhiều thuật toán hash có prefix `{id}` để thuận tiện thay đổi/migrate. Không lưu raw password, không mã hóa password bằng SHA-256 đơn thuần, không dùng `NoOpPasswordEncoder` và không cho client tự cung cấp hash để tránh bypass password policy.

**Phân biệt hashing:**

| Dữ liệu | Đặc tính | Cách lưu phù hợp |
|---|---|---|
| Password do người đặt | Entropy thường thấp, bị thử offline khi DB lộ | Adaptive password hashing qua `PasswordEncoder` |
| Reset token 256-bit do server sinh | Entropy cao, giá trị chỉ cần lookup theo token đã nộp | SHA-256/HMAC digest + TTL + one-use |
| Access/session token | Credential theo cơ chế OAuth/session | Kho token/session độc lập, audience/purpose/expiry riêng |

Không dùng `PasswordEncoder.matches()` để xác thực reset token như thể nó là password; reset token verifier phải kiểm tra **đúng record mục đích PASSWORD_RESET và trạng thái one-time**.

### 6.3. SecurityFilterChain và CSRF

Đoạn cấu hình minh họa cho app có form login bình thường; `POST /password/forgot` và `POST /password/reset` được phép gửi **không cần phiên đăng nhập**, nhưng **không miễn CSRF**:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/password/forgot", "/password/reset").permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/password/forgot", "/password/reset").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // Spring Security CSRF được giữ bật cho POST form.
        return http.build();
    }
}
```

`permitAll()` chỉ có nghĩa anonymous client có thể **đến endpoint** theo HTTP; nó không làm request reset thành đã chứng minh tài khoản. Việc đổi password thực sự vẫn cần reset token hợp lệ trong service. Khi dùng Spring MVC form/Thymeleaf, đưa CSRF token vào POST theo cách framework hỗ trợ. Không dùng `csrf.disable()` chỉ để người dùng đang quên mật khẩu gửi được POST.

**Chú ý với API thuần stateless:** ứng dụng có thể thiết kế một reset endpoint không dùng session cookie, nhưng vẫn phải đánh giá CSRF, origin, rate limit, token possession, anti-automation và threat model. Cách cấu hình bảo vệ không được suy từ việc “API là JSON” mà tự động coi mọi cross-site request vô hại.

### 6.4. Controller tách GET và POST

Mẫu sau là **skeleton Spring MVC**, cần template `password-forgot`, `password-reset`, `password-done` và service tương ứng; **không** phải app độc lập chạy bằng `javac`:

```java
package com.example.security;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class PasswordResetPages {

    private final PasswordResetUseCase reset;

    public PasswordResetPages(PasswordResetUseCase reset) {
        this.reset = reset;
    }

    @GetMapping("/password/forgot")
    String forgotPage() {
        return "password-forgot";
    }

    @PostMapping("/password/forgot")
    String request(@RequestParam String account) {
        // Service luôn trả UI giống nhau, kể cả account không tồn tại.
        reset.requestReset(account);
        return "password-sent";
    }

    @GetMapping("/password/reset")
    String resetPage(@RequestParam String token, Model model) {
        // KHÔNG tiêu thụ token hoặc đổi mật khẩu ở GET.
        model.addAttribute("resetToken", token);
        return "password-reset";
    }

    @PostMapping("/password/reset")
    String finish(@RequestParam String token,
                  @RequestParam String newPassword) {
        reset.completeReset(token, newPassword);
        return "password-done";
    }
}
```

Contract service để đoạn controller được type-check trong dự án:

```java
package com.example.security;

public interface PasswordResetUseCase {
    void requestReset(String account);
    void completeReset(String rawToken, String newPassword);
}
```

**Thực thi quan trọng nằm trong implementation service**, không nằm ở controller. `requestReset` phải sinh token CSPRNG và gửi email theo policy; `completeReset` phải dùng repository atomic consume + update password transaction. Nếu ứng dụng render template chứa `resetToken`, phải HTML-escape đúng cách; thêm CSRF hidden input và không gửi token tới script/analytics. Controller trên **không** tự thực hiện password policy, chống enumeration timing, headers hay audit nếu không bổ sung các lớp tương ứng.

### 6.5. Transaction xử lý password reset (pseudocode)

Ví dụ thuật toán phía service, **không phải code Java có thể copy chạy độc lập**:

```text
completeReset(rawToken, newPassword):
    validate request size, password policy and rate limits
    tokenHash = SHA256(rawToken)

    begin database transaction
        grant = claimUnusedResetToken(tokenHash, purpose=PASSWORD_RESET,
                                      unexpired=true)
        require grant exists

        user = SELECT local_users WHERE id=grant.user_id FOR UPDATE
        require user exists and mayResetPassword(user)
        require user.credential_version == grant.credential_version
        require user.recovery_contact_version == grant.contact_version

        passwordHash = PasswordEncoder.encode(newPassword)
        UPDATE local_users
           SET password_hash = passwordHash,
               credential_version = credential_version + 1
         WHERE id = user.id

        invalidate outstanding PASSWORD_RESET grants for this user
        write durable outbox event PASSWORD_RESET_COMPLETED(user.id)
        commit transaction

    keep browser unauthenticated; redirect to normal login
    reliably notify user of change (no password in email)
    revoke/deny old sessions/tokens per security policy
```

**Thứ tự có thể thay đổi** khi dùng optimistic locking, JPA hoặc JDBC, miễn là các điều kiện bất biến được bảo đảm. Nếu session revocation yêu cầu hiệu lực tức thời, sử dụng shared credential/session version được Resource Servers kiểm tra, thay vì chỉ chờ outbox.

**Không tự gán `SecurityContextHolder.getContext().setAuthentication(...)` sau reset**. Token reset không qua password/MFA login. OWASP cũng khuyến cáo user quay lại **luồng đăng nhập thông thường** sau khi đặt mật khẩu.

## 7. Java 17 chạy độc lập: không thể dùng reset token như login token

Chương trình sau là **mô hình chính sách** chạy được với JDK 17+, không cần Spring hay database. Nó minh họa:

- Login credential và reset token được giữ **hai namespace khác nhau**.
- Reset token chỉ được dùng một lần để tăng phiên bản credential, không tự đăng nhập.
- Token login không thể dùng ở reset endpoint và ngược lại.
- Token hết hạn hoặc phát trước lần đổi password đã hoàn tất bị từ chối.

**Cảnh báo:** các chuỗi token trong `main` là dữ liệu cố định để demo stdout, **không có entropy thực**. Production phải dùng `SecureRandom`; demo chỉ giả định các chuỗi đã được tạo bởi hệ thống tin cậy. Bộ nhớ `HashMap`/`Set` không thay cho database transaction và shared token store trên nhiều nodes.

Lưu thành `ResetVsLoginTokenDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;

public class ResetVsLoginTokenDemo {

    record ResetGrant(
        String tokenDigest,
        String userId,
        Instant expiresAt,
        long issuedVersion,
        boolean consumed
    ) {
        ResetGrant consume() {
            return new ResetGrant(
                tokenDigest, userId, expiresAt, issuedVersion, true);
        }
    }

    static final class Policy {
        private final Map<String, ResetGrant> resetGrants = new HashMap<>();
        private final Map<String, Long> userVersions = new HashMap<>();
        private final Set<String> activeLoginTokens = new HashSet<>();

        void addUser(String userId) {
            userVersions.put(userId, 1L);
        }

        // Namespace phiên đăng nhập tách riêng namespace reset.
        void addLoginToken(String token) {
            activeLoginTokens.add(token);
        }

        String login(String bearer) {
            return activeLoginTokens.contains(bearer)
                ? "LOGIN_ACCEPTED" : "LOGIN_REJECTED";
        }

        void issueForDemo(
                String resetSecret, String userId, Instant expiresAt) {
            long version = userVersions.get(userId);
            resetGrants.put(
                digest(resetSecret),
                new ResetGrant(
                    digest(resetSecret), userId, expiresAt, version, false));
        }

        synchronized String reset(String secret, Instant now) {
            String key = digest(secret);
            ResetGrant grant = resetGrants.get(key);

            if (grant == null
                    || grant.consumed()
                    || !now.isBefore(grant.expiresAt())) {
                return "RESET_REJECTED";
            }

            long currentVersion = userVersions.getOrDefault(
                grant.userId(), -1L);

            if (currentVersion != grant.issuedVersion()) {
                return "RESET_REJECTED";
            }

            resetGrants.put(key, grant.consume());
            userVersions.put(grant.userId(), currentVersion + 1L);
            return "PASSWORD_CHANGED_LOGIN_REQUIRED";
        }
    }

    static String digest(String raw) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                .digest(raw.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(bytes);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-01-01T12:00:00Z");
        Policy policy = new Policy();
        policy.addUser("user-42");

        String resetSecret = "demo-only-reset-secret-A";
        String anotherReset = "demo-only-reset-secret-B";
        String loginToken = "demo-only-login-session";

        policy.addLoginToken(loginToken);
        policy.issueForDemo(resetSecret, "user-42", now.plusSeconds(300));
        policy.issueForDemo(anotherReset, "user-42", now.plusSeconds(300));

        System.out.println("Reset used as login: " +
            policy.login(resetSecret));
        System.out.println("Login used as reset: " +
            policy.reset(loginToken, now));
        System.out.println("Valid reset: " +
            policy.reset(resetSecret, now));
        System.out.println("Replayed reset: " +
            policy.reset(resetSecret, now));
        System.out.println("Older second link: " +
            policy.reset(anotherReset, now));
        System.out.println("After reset login: " +
            policy.login(resetSecret));
        System.out.println("Old session example: " +
            policy.login(loginToken));
    }
}
```

Biên dịch và chạy:

```bash
javac ResetVsLoginTokenDemo.java
java ResetVsLoginTokenDemo
```

Stdout chính xác:

```text
Reset used as login: LOGIN_REJECTED
Login used as reset: RESET_REJECTED
Valid reset: PASSWORD_CHANGED_LOGIN_REQUIRED
Replayed reset: RESET_REJECTED
Older second link: RESET_REJECTED
After reset login: LOGIN_REJECTED
Old session example: LOGIN_ACCEPTED
```

**Giải thích từng dòng:**

1. `resetSecret` không nằm trong `activeLoginTokens` nên không thể đăng nhập.
2. `loginToken` không nằm trong `resetGrants` nên không thể đổi password.
3. Reset hợp lệ tăng phiên bản `user-42` từ 1 lên 2, nhưng chỉ trả `PASSWORD_CHANGED_LOGIN_REQUIRED`, không tạo login.
4. Cùng reset token lần hai có `consumed=true` nên bị từ chối.
5. Một reset token khác được phát ở version 1 cũng bị vô hiệu sau password change vì current version là 2.
6. Reset token sau khi dùng vẫn không thể login.
7. **Old session example: LOGIN_ACCEPTED** là kết quả có chủ đích nhấn mạnh hạn chế: **đổi password không tự thu hồi phiên đăng nhập đã có**. Production cần session revocation hoặc session version check theo policy.

`synchronized` trong demo chỉ tránh race trong **một JVM**, không bảo vệ cluster. Production cần transaction, row locking/version check và shared store. Demo không lưu password hash thật, không gửi email, không xác minh account contact và không cấp quyền Spring Security.

## 8. Hai trường hợp dễ nhầm: đổi mật khẩu khi đang đăng nhập và quên mật khẩu

### 8.1. Đổi mật khẩu (change password)

Người dùng đã login và muốn thay mật khẩu theo ý mình. Cần xác thực lại bằng password hiện tại hoặc MFA/reauth phù hợp mức rủi ro, ngăn CSRF và session theft. Ứng dụng có thể ghi audit, revoke sessions khác theo policy. Không phát password reset token chỉ vì người dùng đang đăng nhập.

```text
authenticated session
    → recent reauthentication
    → enter new password
    → hash/store/update credential_version
    → session policy and notification
```

### 8.2. Quên mật khẩu (forgot/reset)

Người dùng **không có password hiện tại**. Bằng chứng là **password reset token purpose-bound** gửi qua kênh recovery đã xác minh:

```text
anonymous request
    → generic response / rate limit
    → email reset token
    → POST token + new password + CSRF
    → atomic consume + password update
    → require normal login
```

Không gọi `authenticationManager.authenticate(new UsernamePasswordAuthenticationToken(user, resetToken))` để “xác minh” reset token bằng password provider. Password provider dùng để so khớp **password**, còn reset service dùng token store purpose-bound. Trộn hai con đường có thể tạo bypass.

### 8.3. Người dùng SSO/OIDC không có mật khẩu nội bộ

Nếu account đăng nhập **chỉ qua IdP bên ngoài**, không tự tạo password nội bộ và gửi link reset chỉ vì biết email claim IdP. Việc khôi phục mật khẩu thường thuộc IdP. Nếu sản phẩm muốn cho thêm local password, đó là **hành động enrollment nhạy cảm** với bằng chứng sở hữu tài khoản local/SSO và chính sách rõ ràng, không phải reset mặc định.

Không dùng `email_verified=true` từ IdP làm bằng chứng duy nhất cho local account khác có email trùng. Cặp định danh ngoài hợp lệ và ownership account được kiểm soát qua cơ chế liên kết riêng.

## 9. Mật khẩu, bảo đảm xác thực và MFA sau khi reset

### 9.1. Mật khẩu mới cần đạt password policy

- Hỗ trợ mật khẩu đủ dài; không ép yêu cầu composition tùy tiện làm người dùng chọn pattern dễ đoán.
- Kiểm tra common/breached passwords khi có dịch vụ phù hợp, không gửi raw password tới bên thứ ba thiếu bảo vệ.
- Không giới hạn độ dài quá ngắn; có mức tối đa thực tế để chống DoS khi hash.
- Dùng `PasswordEncoder` thích hợp, có chi phí hash theo hạ tầng; không log/password email.
- Nếu dùng pepper, quản lý ở secret manager với quy trình rotation; không commit key vào source.
- Không lưu password history dạng plaintext; nếu policy ngăn reuse, kiểm tra qua hashes và kho history được bảo vệ.

### 9.2. Reset password không đồng nghĩa reset MFA

- Reset link tới email không được tự động **xóa TOTP/WebAuthn registrations**, backup codes, security keys hoặc cấp quyền admin.
- Nếu user cũng mất MFA device, cần một **recovery policy riêng**: backup codes dùng một lần, security key dự phòng, helpdesk được kiểm soát, thông báo và audit, có thể trì hoãn hành động rủi ro cao.
- Với account đặc biệt nhạy cảm, thay đổi password hoặc phục hồi account có thể phải thông qua bước xác minh bổ sung theo chính sách.
- Sau reset, phiên đăng nhập mới vẫn phải làm **MFA bình thường** nếu account yêu cầu.

Reset flow được thiết kế quá yếu có thể biến thành đường vòng để bỏ qua phương thức đăng nhập mạnh; vì vậy phải đánh giá **toàn bộ vòng đời tài khoản**, không chỉ endpoint login.

### 9.3. Account disabled, locked, deleted

Chính sách phải phân biệt:

- **Đang bị khóa vì nhập sai password:** Có thể cho phép khôi phục mật khẩu nhưng cần hành vi unlock có chủ đích; không tự mở khóa tài khoản bị admin block.
- **Bị vô hiệu hóa vì vi phạm/quyết định bảo mật:** Reset password không nên tự kích hoạt lại account.
- **Bị xóa hoặc đang trong quy trình xóa:** Không tự tái tạo user hoặc cho token cũ hồi sinh account.
- **Thay email khôi phục:** Token gửi tới địa chỉ cũ có thể phải bị vô hiệu bằng `contact_version`.
- **MFA recovery:** Là workflow riêng, không được “mượn” reset token.

Phần này cần một policy có trạng thái machine rõ ràng, thay vì gom mọi account thành cờ `enabled=true/false` rồi coi reset luôn hợp lệ.

## 10. Ngăn tấn công phổ biến

| Nguy cơ | Kịch bản | Phòng vệ |
|---|---|---|
| **Account enumeration** | Từ response/timing biết email có tồn tại | Thông điệp và thời gian tương đồng, rate limit, queue |
| Email flooding | Attacker gửi hàng nghìn reset requests | Per-account/IP throttling, abuse detection, cooldown |
| Token guessing | Mã yếu, ngắn hoặc theo timestamp | CSPRNG 256-bit, TTL, chống brute force |
| Token replay | Dùng link lần hai | Atomic consume + `consumed_at` |
| Two-token race | Hai link còn hạn cùng đổi password | User row lock + `credential_version` |
| Login-token confusion | Dùng access/session token để reset | Namespace purpose riêng, verifier riêng |
| Reset-token confusion | Dùng reset secret cho API/login | Không tạo session/Authentication từ reset token |
| Host Header Injection | Thư reset trỏ domain attacker | Public HTTPS origin cấu hình, gateway kiểm soát Host |
| Token leakage | Referrer/log/analytics chứa token | `no-referrer`, `no-store`, CSP, log redaction |
| GET consumption | Scanner mở email link làm thay đổi trạng thái | GET hiển thị form, POST mới consume |
| CSRF | Attacker ép browser gửi POST reset/change | CSRF protection và session/input binding phù hợp |
| Insecure password hash | Lưu plain/MD5/SHA-256 password | Spring `PasswordEncoder` adaptive hash |
| Session persistence | Password đổi nhưng cookie/JWT cũ còn quyền | Session/token revocation hoặc version check |
| Recovery downgrade | Reset password đồng thời tắt MFA | Recovery phân tách, step-up cho thay factor |
| Cross-tenant confusion | Link tenant A đặt password cho user tenant B | User ID + tenant binding và validation |
| Email not verified | Link được gửi tới contact attacker khai | Chỉ recovery contact đã verified |
| Automatic login after reset | Link hộp thư trở thành full session | Yêu cầu đăng nhập lại đúng flow |
| OAuth-only account | Tạo mật khẩu cho account SSO không có local credential | Chặn reset sai loại account, dùng IdP recovery |

## 11. Ma trận kiểm thử

### 11.1. Cấp link và giao tiếp email

| Tình huống | Kỳ vọng |
|---|---|
| Email tồn tại và verified | Email chỉ tới contact được lưu, link canonical HTTPS |
| Email không tồn tại | Cùng phản hồi UI/status chung, không lộ account |
| Email tồn tại nhưng chưa verified | Không gửi link quyền reset tới contact chưa tin, UI không tiết lộ |
| Account SSO-only | Theo chính sách chuyển sang IdP recovery, không tự thêm password |
| Host giả `attacker.example` | Link vẫn chứa domain chính thức hoặc gateway từ chối |
| `X-Forwarded-Host` giả | Không ảnh hưởng URL reset trong email |
| Request spam theo IP/user | Rate limit và audit; không spam thư vô hạn |
| Send email lỗi | Có retry/queue policy nhưng không tiết lộ account existence |
| Hai tenant có email trùng | Link gắn đúng local user + tenant, không sang owner khác |

### 11.2. Token và thay đổi password

- Raw reset token đúng nhưng đã quá `expires_at`: **từ chối**, không đổi password.
- Raw reset token giả hoặc bị sửa một ký tự: **từ chối**, không tạo session.
- Token `purpose=EMAIL_VERIFY` nộp vào password reset endpoint: **từ chối**.
- JWT access token, refresh token hoặc session cookie dùng thay reset token: **từ chối**.
- Reset token nộp cho `Authorization: Bearer ...` để gọi API: **không được xác thực**.
- Password reset token chỉ có hiệu lực đối với **đúng local user ID** gắn trong record; không chấp nhận `userId` client gửi khác.
- Token đúng nhưng account disabled/admin-blocked: **từ chối** theo chính sách.
- Token đúng nhưng `credential_version` đã tăng vì password đổi từ thiết bị khác: **từ chối**.
- Token đúng nhưng `recovery_contact_version` đã đổi: **từ chối**.
- Hai POST với cùng reset token đồng thời: tối đa **một** transaction commit.
- Hai POST với hai reset tokens khác nhau nhưng cùng credential version: chỉ **một** lần đổi password theo policy version.
- Transaction đổi password lỗi: token không nên bị đánh dấu consumed nếu update không commit.
- Password mới không đạt policy: không lưu hash không hợp lệ, không tự tạo session.
- Sau khi reset thành công, dùng lại token: **từ chối**.
- Sau reset, password cũ không còn đăng nhập được; password mới đăng nhập qua chính sách bình thường.
- Sau reset, MFA vẫn được yêu cầu nếu trước đó account dùng MFA.
- Không có đường API nào cho phép reset token dùng như cookie/access token.

### 11.3. Session, CSRF và rò dữ liệu

- GET reset link bằng bot email scanner → không đổi password, không tạo login.
- POST form thiếu CSRF token khi CSRF đang bật → bị chặn.
- Trang reset không tải scripts/analytics từ bên ngoài mang theo full URL/token.
- Response có `Referrer-Policy: no-referrer` và `Cache-Control: no-store`; redirect sau reset không mang token.
- HTTP logs, tracing, exception và mailer debug không ghi raw token/password.
- Session hoặc refresh token phát trước reset phải bị thu hồi/kiểm tra version theo chính sách xác định; test ở nhiều API nodes.
- Mọi thông báo sau reset gửi tới kênh đáng tin, không chứa password; alert nếu reset không do user khởi tạo.
- Endpoint reset không tự cấp `ROLE_ADMIN` hoặc thừa hưởng quyền của một access token ngẫu nhiên.
- Admin disable account sau khi phát link nhưng trước POST → reset không hồi sinh account.

### 11.4. Test mục đích độc lập (quan trọng nhất)

Đặt tên test theo bảo đảm mong muốn:

```text
passwordResetTokenMustNotAuthenticateApi()
loginAccessTokenMustNotResetPassword()
emailVerificationTokenMustNotResetPassword()
passwordResetTokenMustBeSingleUse()
expiredPasswordResetTokenMustBeRejected()
twoConcurrentResetRequestsMustNotBothCommit()
secondResetTokenIssuedBeforePasswordChangeMustFail()
passwordResetDoesNotBypassMfa()
oldSessionsRevokedOrVersionCheckedAfterReset()
resetLinkHostMustNotComeFromRequestHeaders()
```

Không chỉ kiểm tra rằng “email đã được gửi” hoặc “newPassword đã lưu”. Các test an ninh phải cố tình gửi **sai loại token** qua từng endpoint để phát hiện confusion và bypass.

## 12. Checklist production và xử lý sự cố

1. **Token riêng đúng purpose:** bảng/namespace reset độc lập, verifier riêng; login API không đọc reset store.
2. **Token không đoán được:** ≥128 bit entropy, thường chọn 256 bit CSPRNG; TTL ngắn và one-use.
3. **Contact đã verified:** chỉ gửi secret tới kênh recovery được kiểm soát; account enumeration response trung tính.
4. **Atomic database:** consume + password hash update + version increment trong transaction; chống replay và race giữa hai link.
5. **Password hash chuẩn:** dùng Spring `PasswordEncoder`; kiểm tra password policy, không lưu/gửi plaintext.
6. **Public URL đáng tin:** cố định HTTPS origin; không lấy `Host` hoặc header forwarding từ client; hạn chế redirect.
7. **Không làm gì nhạy cảm ở GET:** tránh email scanner tự tiêu thụ; POST được bảo vệ CSRF và rate limits.
8. **Giảm lộ token:** no-referrer, no-store, CSP, không third-party analytics/log query, không gửi token qua redirect.
9. **Không auto-login:** sau khi reset thành công, điều hướng tới luồng đăng nhập thật và MFA tương ứng.
10. **Phiên cũ:** xác định và test chiến lược thu hồi HttpSession, JWT, refresh/remember-me và other sessions.
11. **Độc lập với MFA/recovery:** reset password không tự tắt WebAuthn/TOTP hoặc trao quyền mới.
12. **Audit & incident response:** ghi event `PASSWORD_RESET_REQUESTED`, `PASSWORD_RESET_COMPLETED`, `PASSWORD_RESET_REJECTED`, `SESSIONS_REVOKED` với user/tenant IDs đã kiểm chứng; không log raw token/email ngoài nhu cầu.
13. **Đa node/đa tenant:** transaction/locking trên database shared, version checks, TTL, clock sync và tenant binding; đo độ trễ propagation khi revoke.
14. **Kiểm tra với các loại account:** local password, SSO-only, disabled, locked, email đang đổi, account bị xóa; không áp cùng một reset policy máy móc.
15. **Quy trình vận hành:** có khả năng rollback sự cố an toàn, support xác minh account và audit; không để helpdesk đọc raw reset tokens hay bypass MFA tùy ý.

## 13. Câu hỏi tự đánh giá

**Câu 1.** Vì sao không được lấy bearer access token đang còn hạn làm token đặt lại mật khẩu?  
**Trả lời:** Access token có mục đích/audience/scope riêng; nếu chấp nhận nó để reset, người giữ token API tạm thời có thể giành quyền truy cập lâu dài bằng cách đổi password. Reset cần bằng chứng khôi phục và verifier purpose-bound riêng.

**Câu 2.** Vì sao reset token chưa hết hạn vẫn không được tự động đăng nhập?  
**Trả lời:** Nó chỉ trao quyền hẹp để đổi password một lần; login cần đi qua password/MFA hoặc cơ chế xác thực được thiết kế cho login. Trộn hai quyền dẫn đến token confusion và bỏ qua assurance.

**Câu 3.** Hai reset links khác nhau cho cùng user, cùng phiên bản credential, có thể cùng dùng được không?  
**Trả lời:** Không nên nếu chính sách yêu cầu lần đổi password đầu vô hiệu mọi link cũ. User row lock + so `credential_version` trong transaction ngăn hai lần đổi password đồng thời.

**Câu 4.** Đã lưu hash token bằng SHA-256 thì có cần TTL và one-use không?  
**Trả lời:** Vẫn cần. Hash bảo vệ token raw khi database bị lộ; TTL giới hạn thời gian, one-use chống replay, user/version binding giữ đúng owner.

**Câu 5.** Có thể gửi reset link tới địa chỉ email vừa được user nhập mà chưa có trong account store không?  
**Trả lời:** Không như một đường khôi phục tài khoản đã tồn tại. Chỉ dùng recovery contact đáng tin đã verified hoặc quy trình recovery riêng phù hợp.

**Câu 6.** Reset thành công đã tự thu hồi JWT access token cũ chưa?  
**Trả lời:** Chưa. JWT có thể tiếp tục hợp lệ tới `exp` nếu Resource Server chỉ kiểm tra offline. Cần denylist, introspection, version checks, TTL và revocation theo policy.

**Câu 7.** Tại sao không đổi mật khẩu ở GET khi người dùng bấm link email?  
**Trả lời:** Email scanners có thể tự mở GET; state-changing action phải ở bước POST được kiểm soát, sau khi người dùng nhập password mới.

**Câu 8.** Spring Security có tự động cấp `PasswordResetToken` khi thêm `spring-boot-starter-security` không?  
**Trả lời:** Không có quy trình forgot-password đầy đủ được tự động bật theo starter. Ứng dụng phải thiết kế issuing, delivery, storage, redemption và password update; Spring Security cung cấp password encoder và các thành phần bảo vệ request/session.

**Câu 9.** Sau khi đổi password, hệ thống có nên tự tắt tất cả authenticator MFA vì user đã kiểm soát email không?  
**Trả lời:** Không. MFA enrollment/recovery là workflow riêng với bảo đảm đủ mạnh; reset password không tự nâng quyền hay làm mất lớp bảo vệ.

## Nguồn tham khảo

- [OWASP Cheat Sheet — Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): response chung và thời gian tương đồng, token ngẫu nhiên/one-use/expiry, URL origin tin cậy, xử lý sau reset.
- [OWASP Cheat Sheet — Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): chống enumeration, xác thực lại, password recovery và các kênh bảo đảm.
- [OWASP Cheat Sheet — Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): cách hash mật khẩu do người dùng đặt.
- [OWASP Cheat Sheet — Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session ID, vòng đời phiên và các cơ chế thu hồi.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`, `DelegatingPasswordEncoder` và quản lý thay đổi mật khẩu.
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): bảo vệ các POST form thay đổi trạng thái.
- [Spring Security — Servlet Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): security context/session và các lựa chọn quản trị phiên.
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): access token được gửi cho API, không phải reset token.
