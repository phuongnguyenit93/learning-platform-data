# Đăng ký, khôi phục và quản trị tài khoản thuộc vòng đời nghiệp vụ của ứng dụng

> **Ý chính:** Spring Security cung cấp những khối xây dựng để **xác thực danh tính** và **phân quyền truy cập**: `SecurityFilterChain`, `AuthenticationManager`, `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder`, session và method security. Nhưng Spring Security **không tự định nghĩa quy trình nghiệp vụ đầy đủ** cho việc đăng ký tài khoản, xác minh email, khôi phục quyền truy cập, đổi địa chỉ liên hệ, cấp hoặc thu hồi vai trò, khóa tài khoản hay xóa dữ liệu theo yêu cầu. Các chức năng này phải được thiết kế như **vòng đời Account của ứng dụng**, kết nối đúng với cơ chế xác thực và các yêu cầu an toàn.

Bài thuộc nhóm **Nguồn người dùng** của **Spring Security – fundamentals**. Trọng tâm là ứng dụng Java 17+, Spring Boot 3.5.16, Spring Security 6.5.x dùng username/password trên Spring MVC/Servlet. Mô hình vẫn hữu ích với OIDC/SSO, nhưng nơi quản lý vòng đời tài khoản sẽ khác nếu danh tính do Identity Provider (IdP) kiểm soát.

## 1. Kết quả học tập

Học xong, bạn có thể:

1. Giải thích **Account** (bản ghi nghiệp vụ) khác **UserDetails** (cách Spring Security đọc credential/quyền cho một authentication mechanism) như thế nào.
2. Thiết kế các trạng thái tài khoản và chuyển trạng thái hợp lệ: `PENDING_VERIFICATION` → `ACTIVE` → `SUSPENDED` hoặc `CLOSED`.
3. Mô tả đầy đủ các flow đăng ký, xác minh email, quên mật khẩu, đặt lại mật khẩu, đổi mật khẩu khi đã đăng nhập, đổi email, khóa/mở khóa và đóng tài khoản.
4. Phân biệt token xác minh/khôi phục với **access token**, **refresh token**, session cookie và CSRF token.
5. Thiết kế recovery token khó đoán, **hết hạn, dùng một lần, lưu dạng băm**, không bị dùng đồng thời hai lần và không tiết lộ tài khoản có tồn tại.
6. Biết chỗ nào cần transaction, unique constraint, versioning, outbox email, idempotency, audit và rate limiting.
7. Gắn `UserDetailsService`/`DaoAuthenticationProvider` với kho tài khoản nhưng **không đặt mọi logic đăng ký/khôi phục trong `loadUserByUsername`**.
8. Phân quyền quản trị bằng role/authority lấy từ server; không cho người đăng ký công khai tự yêu cầu `ROLE_ADMIN`.
9. Viết và kiểm thử một demo độc lập: đăng ký → chưa được đăng nhập → xác minh → đăng nhập → yêu cầu reset → đổi mật khẩu → vô hiệu hóa tài khoản.
10. Xác định giới hạn của demo in-memory và cách chuyển sang database/IdP với dữ liệu thật.

## 2. Ranh giới trách nhiệm: Spring Security và ứng dụng

### 2.1. Sơ đồ tổng quan

```text
CLIENT / BROWSER
  |
  +-- POST /auth/register --------------------------+
  +-- POST /auth/verify ----------------------------+
  +-- POST /auth/recovery/request ------------------+
  +-- POST /auth/recovery/complete -----------------+--> Account API
  +-- POST /account/change-password ---------------+       |
  +-- POST /admin/accounts/{id}/suspend -----------+       v
  |                                              AccountLifecycleService
  |                                               / policy + transaction
  |                                                |          |
  |                                                v          v
  |                                         AccountRepository  Email/Outbox
  |                                                |
  |                                                v
  |                                           user/status/roles
  |
  +-- GET /me, GET /orders, POST /payments ...
                     |
                     v
              Spring Security Filter Chain
              AuthenticationManager/Provider
                     |
                     v
              UserDetailsService / OIDC / JWT verifier
                     |
                     v
              Account lookup/status/authorities
                     |
                     v
              HTTP authorization
                     |
                     v
              Controller -> service/domain authorization
```

Phân tách này rất quan trọng:

- **Spring Security:** xác thực credential, thiết lập authenticated principal, thực thi filter/method authorization và bảo vệ giao thức (như CSRF, session) theo cấu hình.
- **Account domain:** ai được đăng ký, thông tin bắt buộc, email đã xác minh chưa, ai được khóa tài khoản, chính sách recovery, kiểm toán và dữ liệu liên quan khi đóng tài khoản.
- **Infrastructure:** database, transaction, hàng đợi email/SMS, IdP, audit store, chống spam/rate limiting, cơ chế revoke session/token.
- **Product/legal policy:** quy định về retention, xác minh danh tính, người dùng vị thành niên, xử lý dữ liệu cá nhân và thủ tục hỗ trợ; điều này tùy sản phẩm/pháp luật liên quan.

**Spring Security không cung cấp một lệnh “enableRegistration()” để tạo toàn bộ hệ thống đăng ký và khôi phục an toàn.** Có `UserDetailsService` không đồng nghĩa ứng dụng có endpoint `POST /auth/register`. Cũng không nên gắn xử lý gửi email, tạo reset token hoặc xóa tài khoản trực tiếp vào `loadUserByUsername()`.

### 2.2. Bảng phân vai cụ thể

| Thành phần | Nên chịu trách nhiệm | Không nên bị giao làm thay |
| --- | --- | --- |
| `Account` / `User` domain entity | ID ổn định, email, trạng thái, hash, vai trò, metadata, audit/version | Không làm Servlet filter hoặc phát JWT tùy ý |
| `AccountLifecycleService` | Đăng ký, xác minh, recovery, status transition, quy tắc nghiệp vụ | Không xác nhận mật khẩu qua cách tự so sánh chuỗi |
| `AccountRepository` | Truy xuất/cập nhật, unique constraints, optimistic locking/transaction | Không tự quyết định actor có quyền làm thao tác |
| `VerificationTokenRepository` | Lưu hash/token purpose/expiry/used trạng thái | Không chứa plaintext password hoặc access token |
| `MailGateway` / outbox worker | Gửi thông báo và liên kết trên kênh đã kiểm chứng | Không trả raw token vào HTTP response công khai |
| `UserDetailsService` | Tải credential hash, authorities và account flags cho provider | Không gửi email/reset password/đăng ký |
| `DaoAuthenticationProvider` | Kiểm tra mật khẩu bằng `PasswordEncoder` và trạng thái tài khoản | Không tự kích hoạt tài khoản chờ xác minh |
| `SecurityFilterChain` | Cấp quyền HTTP cho anonymous/member/admin, CSRF/session | Không thay policy owner/tenant trong service |
| `AccountAdministrationService` | Cho staff thực hiện tác vụ quản trị được phép, có audit | Không tin `role` do frontend gửi lên |
| `SecurityContextRepository` / token service | Khôi phục authentication/phiên theo cơ chế | Không phải kho token xác minh email hoặc reset password |

## 3. Mô hình Account là tài nguyên nghiệp vụ

### 3.1. ID, email và username

Một thiết kế minh họa:

```text
Account
  id                  UUID hoặc ID ổn định bất biến
  normalizedEmail     unique theo chính sách email của sản phẩm
  emailVerifiedAt     nullable
  passwordHash        hash một chiều, có version/algorithm
  status              PENDING_VERIFICATION | ACTIVE | SUSPENDED | CLOSED
  roles               các grant do server quản lý
  credentialVersion   dùng phục vụ revoke/invalidate theo chính sách
  createdAt
  updatedAt
  version             optimistic locking
  closedAt            nullable

AccountActionToken
  id
  accountId
  purpose             VERIFY_EMAIL | RESET_PASSWORD | VERIFY_NEW_EMAIL
  tokenDigest         hash/HMAC của chuỗi ngẫu nhiên
  expiresAt
  consumedAt          nullable
  createdAt
  requestMetadata     giới hạn; không lưu secret không cần thiết

AuditEvent
  id, actorId, subjectAccountId, action, outcome, occurredAt
  correlationId, metadata tối thiểu và an toàn
```

Email có thể thay đổi; **đừng dùng email làm khóa ngoại bất biến** cho orders, payments, owner hoặc audit. Dùng `account.id` ổn định, còn email là địa chỉ liên lạc/login identifier theo thiết kế. Một hệ thống có thể cho đăng nhập bằng username riêng, phone, SSO subject (`issuer` + `sub`), hoặc nhiều phương thức.

**Normalization:** Email/domain có những quy tắc so sánh phức tạp; tránh tự ý xóa dấu chấm, xóa phần `+tag` hoặc biến đổi local-part theo một provider cụ thể. Demo có thể dùng `trim()` và `toLowerCase(Locale.ROOT)` để đơn giản hóa, nhưng production cần quy tắc chuẩn hóa được sản phẩm chấp nhận, unique constraint theo cùng quy tắc, xử lý IDN và kiểm tra địa chỉ qua email thực tế. Không coi regex email đơn giản là bằng chứng inbox thuộc về người đăng ký.

### 3.2. Trạng thái đề xuất

```text
                  đăng ký
                     |
                     v
            PENDING_VERIFICATION
                     |
             verify token hợp lệ
                     |
                     v
                   ACTIVE
                 /       \
      quản trị khóa     chủ tài khoản đóng
               v         v
           SUSPENDED    CLOSED
               |
        review / mở khóa
               |
               v
             ACTIVE
```

Một flow thực còn có `INVITED`, `LOCKED` do đăng nhập lỗi, `PENDING_REVIEW`, `DELETION_SCHEDULED`, `DELETED` hoặc `ANONYMIZED`, tùy nghiệp vụ. Không nhất thiết gộp “tạm khóa vì sai password” và “staff đình chỉ vì vi phạm” vào một trạng thái: lý do, thời hạn và cách mở khác nhau.

| Transition | Ai quyết định? | Điều kiện | Hệ quả tối thiểu |
| --- | --- | --- | --- |
| Chưa có → PENDING_VERIFICATION | Public signup service | Dữ liệu hợp lệ, email unique, chống bot/abuse | Lưu hash, phát token xác minh, gửi thông báo |
| PENDING → ACTIVE | Token verifier | Token hợp lệ, chưa hết hạn/đã dùng, đúng purpose và account | Đánh dấu `emailVerifiedAt`, cho phép auth |
| ACTIVE → SUSPENDED | Admin/risk service | Authority và business policy | Chặn login mới, thu hồi session/token theo yêu cầu |
| SUSPENDED → ACTIVE | Người có quyền review | Lý do khóa đã được xử lý | Audit, gửi notification; không tự nâng role |
| ACTIVE → CLOSED | Chủ account qua flow xác thực mạnh hoặc admin hợp lệ | Kiểm tra nghĩa vụ dữ liệu/thanh toán/retention | Vô hiệu đăng nhập, chặn phát token, xử lý dữ liệu |
| ACTIVE → ACTIVE (reset password) | Chủ sở hữu kênh recovery/flow mạnh | Reset token hợp lệ, policy mới, bảo vệ lạm dụng | Đổi password hash, revoke phiên/token theo chính sách |

**Invariant:** Account chưa xác minh hoặc bị đình chỉ không được đăng nhập bằng username/password bình thường. Reset mật khẩu **không tự kích hoạt** một account đang bị suspend. Role do người dùng tự khai trong JSON **không bao giờ** được đưa thẳng vào tập `GrantedAuthority`.

## 4. Flow đăng ký tài khoản

### 4.1. Các bước nghiệp vụ

```text
1. Anonymous POST /auth/register
   { email, password, ...các trường được phép }
            |
            v
2. Validate dữ liệu + password policy + abuse checks
            |
            v
3. Transaction: tạo Account(PENDING_VERIFICATION)
   - passwordHash = PasswordEncoder.encode(rawPassword)
   - roles = [ROLE_USER] do SERVER gán
   - normalizedEmail có UNIQUE constraint
            |
            v
4. Tạo verification token random có purpose + expiry
   - lưu digest, không lưu raw token ở database
   - outbox event "SEND_VERIFY_EMAIL"
            |
            v
5. Commit transaction
            |
            v
6. Email worker gửi link qua origin cấu hình cố định
            |
            v
7. User xác minh -> atomically consume token -> ACTIVE
            |
            v
8. User có thể đăng nhập qua Spring Security provider
```

Không nên để user ACTIVE ngay khi nhận email chưa xác minh nếu email ownership là điều kiện bắt buộc của sản phẩm. Nếu sản phẩm cho phép dùng hạn chế trước khi xác minh, phải định nghĩa explicit capability/permission và thời hạn; đừng vô tình cấp mọi chức năng.

### 4.2. Vì sao phải có unique constraint ở database?

Hai request đăng ký cùng email có thể chạy đồng thời:

```text
Request A: tìm chưa có email
Request B: tìm chưa có email
Request A: insert
Request B: insert
```

Nếu chỉ kiểm tra `existsByEmail` rồi insert, cả hai có thể cùng thấy “chưa tồn tại”. Phải có unique index/constraint tại database, kết hợp transaction, bắt lỗi trùng và trả response phù hợp. Khi cần chống enumeration, câu trả lời công khai của signup nên cân nhắc thống nhất để không tiết lộ account; UX và bảo mật phải được cân bằng theo policy sản phẩm.

### 4.3. User không được tự yêu cầu role

**Phản ví dụ nguy hiểm:**

```json
{
  "email": "new@example.test",
  "password": "ExamplePassphrase2026",
  "roles": ["ROLE_ADMIN"]
}
```

Nếu backend map thẳng request JSON vào entity rồi lưu roles, anonymous có thể tự nâng đặc quyền. DTO đăng ký công khai chỉ chứa những field cần cho signup; trong service tạo account với role mặc định từ server. Role của staff/admin phải do flow invitation/provisioning/approval có kiểm toán xử lý.

### 4.4. Email validation và verification không giống nhau

- **Validation:** Chuỗi có format và độ dài theo quy tắc hệ thống; kiểm tra input rỗng, control character, Unicode, độ dài.
- **Verification:** Một người thực sự kiểm soát inbox/kênh nhận email thông qua token dùng một lần. Verify domain MX hay chỉ kiểm regex **không chứng minh** người dùng nhận được email.
- **Identity proofing:** Có thể đòi hỏi bằng chứng mạnh hơn email, tùy rủi ro (tài chính, y tế, tổ chức); email verification không chứng minh tên tuổi pháp lý.
- **Re-verification:** Khi thay email, nên xác minh email mới và thông báo kênh cũ; không âm thầm đổi login identifier chỉ từ một request ở session bị chiếm.

## 5. Recovery: “quên mật khẩu” là một giao dịch bảo mật đặc biệt

### 5.1. Hai endpoint có nhiệm vụ khác nhau

```text
POST /auth/recovery/request
   Body: { "email": "alice@example.test" }
   -> trả thông báo chung, ví dụ HTTP 202
   -> nếu có tài khoản đủ điều kiện, gửi token qua kênh đã đăng ký

POST /auth/recovery/complete
   Body: { "token": "<opaque token>", "newPassword": "..." }
   -> xác minh/consume token và đổi password hash
   -> không tự đăng nhập
   -> thông báo password đã đổi qua kênh phù hợp
```

**Không gửi password mới qua email.** Email/link reset là bằng chứng quyền kiểm soát kênh recovery ở mức sản phẩm chấp nhận, chứ không phải password. Chỉ sau khi người dùng tự chọn mật khẩu mới và token hợp lệ thì hash được thay đổi.

### 5.2. Thuộc tính cần có của reset token

- **Sinh từ CSPRNG:** ví dụ 32 bytes bằng `SecureRandom`, encode URL-safe Base64. Không dùng `Random`, timestamp, userId hoặc email làm secret.
- **Sufficient entropy:** 256 bit ngẫu nhiên đủ mạnh cho bài học; không cần tính toán từ thông tin công khai.
- **Có purpose:** token reset password không dùng thay token verify email, login access token hay refresh token.
- **Hết hạn:** ví dụ 15 phút trong demo; production chọn TTL theo rủi ro/UX rồi test.
- **Dùng một lần:** consume theo cách **atomic**; hai request race chỉ một request thành công.
- **Lưu an toàn:** lưu SHA-256/HMAC digest của token ngẫu nhiên trong DB, không lưu plaintext; hash nhanh phù hợp vì token đủ ngẫu nhiên (khác mật khẩu có entropy thấp).
- **Giới hạn phát hành:** rate limit theo account/IP/device/ASN/risk; hạn chế resend, spam và DoS; trả thông báo chung cả với email không tồn tại.
- **Không làm lộ:** tránh log token, analytics, browser referrer, cache, URL redirect ngoài origin; dùng HTTPS, `Referrer-Policy: no-referrer` khi hiển thị form có token trong URL.
- **Không auto-login sau reset:** recovery token dùng để đổi mật khẩu, không phải session credential để vào ứng dụng ngay.
- **Chính sách phiên:** sau đổi mật khẩu, thường thu hồi các session/refresh token cũ và yêu cầu login lại, tùy threat model.

### 5.3. Tránh dò tài khoản (account enumeration)

**Sai:**

```http
POST /auth/recovery/request
{"email":"not-found@example.test"}

HTTP/1.1 404
{"error":"Email này không tồn tại"}
```

Response như vậy giúp attacker xác nhận email nào có account. Phương án tốt hơn là thông báo chung, ví dụ:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"message":"Nếu tài khoản đủ điều kiện, hướng dẫn sẽ được gửi."}
```

Áp dụng thông báo chung cho account tồn tại/không tồn tại, trạng thái suspended và policy điều kiện phù hợp. **Timing cũng có thể rò rỉ:** nếu account có thật sinh token + gọi SMTP đồng bộ nhưng email không tồn tại thì trả ngay, attacker có thể đo thời gian. Production nên dùng enqueue/outbox theo chiến lược giảm chênh lệch, kiểm soát tải và rate limit; không hứa một response cố định tự giải quyết hết enumeration.

### 5.4. Vì sao SHA-256 của reset token khác password hash?

Password con người thường đoán được từ từ điển, nên dùng `PasswordEncoder` thích hợp như bcrypt/Argon2/PBKDF2 với work factor được đánh giá. Token random 32 bytes được tạo từ CSPRNG không có cấu trúc đoán được; có thể lưu `SHA-256(token)` hoặc HMAC digest server-side để đối chiếu. Mất DB chỉ thấy digest và khó tìm token gốc bằng brute force.

**Không bao giờ lấy `SHA-256(password)` đơn thuần thay cho password hashing.** Hai loại bí mật có threat model/entropy rất khác nhau.

### 5.5. Token link và email scanner

Nhiều hệ thống email có link scanner tự truy cập URL. Vì thế **GET link trong email không nên thực hiện thay đổi mật khẩu hay tiêu thụ token chỉ vì được mở**. Nó nên hiển thị form/confirmation, sau đó client gửi POST đã xác nhận với token và password mới. Nếu thiết kế verify email bằng link GET, phải cân nhắc khả năng scanner tự kích hoạt và yêu cầu bước xác nhận phù hợp với rủi ro sản phẩm.

Link thường xây từ **origin chính thức trong cấu hình**, ví dụ `https://accounts.example.test/reset?token=...`. Không sử dụng trực tiếp `Host` hoặc `X-Forwarded-Host` do client kiểm soát để ghép link reset gửi email, vì dễ dẫn tới host-header poisoning/phishing. Token trong URL cần xử lý referrer/cache/history và không đưa vào log tại reverse proxy.

## 6. Đổi mật khẩu khi đã đăng nhập khác khôi phục mật khẩu

| Trường hợp | Bằng chứng yêu cầu | Kênh thực hiện | Rủi ro chính |
| --- | --- | --- | --- |
| Đổi password trong session | Phiên hợp lệ + kiểm tra lại password/MFA khi cần | `POST /account/change-password` | Chiếm session, CSRF, bỏ qua re-auth |
| Quên password | Token recovery một lần từ kênh đã xác minh | `POST /auth/recovery/complete` | Đoán/đánh cắp token, enumeration |
| Admin khởi tạo reset | Staff có quyền + policy review | Admin API phát workflow, không đặt password tùy tiện | Abuse nội bộ, lộ reset link |
| Đổi email | Session + re-auth + xác minh email mới | Account workflow | Chiếm tài khoản bằng đổi kênh recovery |
| SSO/OIDC user | Theo chính sách IdP | IdP self-service hoặc quản trị | Thay nhầm credential không thuộc ứng dụng |

Một UI “đổi mật khẩu” đang ở phiên đăng nhập thường yêu cầu mật khẩu hiện tại hoặc step-up (MFA, passkey) cho hành động nhạy cảm. Không chỉ tin một cookie session dài ngày. Với account vừa được khôi phục, nên thông báo qua các kênh còn tin cậy, cân nhắc revoke phiên và yêu cầu đăng nhập mới.

## 7. Quản trị tài khoản: khóa, mở, phân vai, đóng và audit

### 7.1. Quản trị là một tập quyền riêng

Ví dụ API:

```text
POST /admin/accounts/{id}/suspend
POST /admin/accounts/{id}/reinstate
POST /admin/accounts/{id}/role-grants
POST /admin/accounts/{id}/revoke-sessions
POST /admin/accounts/{id}/close
```

Tất cả là thao tác **state-changing**. Cần ít nhất:

- Authentication staff thực, authority tối thiểu tương ứng (`ACCOUNT_SUSPEND`, `ROLE_GRANT`, `ACCOUNT_CLOSE`), không nhất thiết một ROLE_ADMIN duy nhất.
- Policy về actor, subject account, tenant và phạm vi quyền. Một admin của tổ chức A **không đương nhiên** được khóa user thuộc tổ chức B.
- Re-auth/step-up hoặc quy trình phê duyệt đối với grant admin, reset MFA, thay quyền nhạy cảm.
- Audit event có actor, account ID, before/after (có redaction), lý do, correlation ID, outcome; không ghi secret.
- Biện pháp chống IDOR/BOLA: xác minh subject account có nằm trong phạm vi staff phụ trách.
- Session/token revocation phù hợp khi bị suspend/close/đổi credential, không chỉ set field trong DB.
- Idempotency/transaction để retry request không gửi email hoặc lặp audit theo cách nguy hiểm.

### 7.2. Khi nào UserDetails.isEnabled() có tác dụng?

Trong cơ chế password authentication dùng `DaoAuthenticationProvider`, custom `UserDetailsService` có thể ánh xạ:

```java
boolean allowed = account.status() == AccountStatus.ACTIVE;

return User.withUsername(account.email())
    .password(account.passwordHash())
    .authorities(account.authorities().toArray(String[]::new))
    .disabled(!allowed)
    .build();
```

Khi account chưa verified/suspended, provider thường từ chối password authentication vì disabled. **Nhưng:** điều này không có nghĩa các session đã đăng nhập từ trước bị thu hồi tức thời. Nếu Spring Security khôi phục một `Authentication` từ session, provider không nhất thiết tra user store lại ở mỗi request. Phải thiết kế cơ chế invalidate/revoke session, denylist/token version/validation tùy cách xác thực.

### 7.3. Account đóng không nhất thiết xóa toàn bộ dữ liệu ngay

Đóng account có thể đi qua `DELETION_SCHEDULED`, `CLOSED`, `ANONYMIZED` và các bước retention hợp lệ cho lịch sử giao dịch hoặc tuân thủ. Quy định cụ thể thuộc product/legal/data governance; không dùng `repository.deleteById` ngay mà bỏ qua foreign keys, payments, audit và nghĩa vụ lưu trữ. Sau khi đóng, chặn login và khả năng cấp token mới, hủy những recovery token còn hiệu lực và quản lý dữ liệu liên quan.

### 7.4. Cấp quyền không thể phụ thuộc email/display name

Quyền phải được quản lý theo **ID của account** hoặc principal đáng tin, role/permission được lưu bởi server, và context tenant/organization. Không viết `if (email.endsWith("@company.com")) grant ADMIN`; domain email không chứng minh một người hiện tại còn là nhân viên có quyền admin. Với IdP, mapping role từ claims phải xác minh issuer, audience, signature, expiry và chính sách nhóm/tenant.

## 8. Kiến trúc dữ liệu và transaction cho ứng dụng nhiều instance

Bên dưới là thiết kế cơ sở dữ liệu khái niệm. Tên kiểu và cú pháp SQL có thể cần điều chỉnh theo PostgreSQL/MySQL và migration tool:

```sql
CREATE TABLE accounts (
    id                UUID PRIMARY KEY,
    normalized_email  VARCHAR(320) NOT NULL UNIQUE,
    password_hash     VARCHAR(255) NOT NULL,
    status            VARCHAR(40) NOT NULL,
    email_verified_at TIMESTAMP NULL,
    credential_version BIGINT NOT NULL DEFAULT 0,
    version           BIGINT NOT NULL DEFAULT 0,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL
);

CREATE TABLE account_roles (
    account_id UUID NOT NULL,
    authority  VARCHAR(120) NOT NULL,
    PRIMARY KEY (account_id, authority)
);

CREATE TABLE account_action_tokens (
    id          UUID PRIMARY KEY,
    account_id  UUID NOT NULL,
    purpose     VARCHAR(40) NOT NULL,
    token_hash  VARCHAR(128) NOT NULL UNIQUE,
    expires_at  TIMESTAMP NOT NULL,
    consumed_at TIMESTAMP NULL,
    created_at  TIMESTAMP NOT NULL
);

CREATE TABLE account_outbox (
    id             UUID PRIMARY KEY,
    event_type     VARCHAR(100) NOT NULL,
    account_id     UUID NOT NULL,
    payload_ciphertext TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    delivered_at   TIMESTAMP NULL
);
```

**Lưu ý:** Đây là sơ đồ minh họa chứ chưa phải migration độc lập với mọi database. Production nên có foreign keys phù hợp, index cho lookup token/account, constraints trạng thái, audit, TTL cleanup và quy trình bảo vệ payload của outbox. Nếu outbox chứa raw reset token để email worker gửi sau commit, payload cần được mã hóa/giới hạn truy cập và xóa theo retention rất ngắn; không để token plaintext nằm mãi trong bảng. Một phương án khác là thiết kế worker tạo token và lưu digest trong giao dịch riêng có kiểm soát.

### 8.1. Transaction đăng ký

```text
BEGIN
  INSERT account(status=PENDING_VERIFICATION, password_hash, default_roles)
  INSERT account_action_token(hash, purpose=VERIFY_EMAIL, expires_at)
  INSERT outbox_message(SEND_EMAIL_VERIFICATION)
COMMIT
Background dispatcher delivers message; retry bằng idempotency key.
```

Tạo account và token/outbox như một đơn vị logic để tránh account bị kẹt không có email vì transaction rollback giữa chừng. Không gửi email trực tiếp rồi mới commit: nếu DB commit thất bại, người dùng có thể nhận link không hợp lệ.

### 8.2. Transaction tiêu thụ reset token

```text
BEGIN
  Tìm token qua digest với lock hoặc atomic UPDATE:
    purpose=RESET_PASSWORD
    consumed_at IS NULL
    expires_at > now()
  Chỉ cho một request đánh dấu consumed_at = now().
  Kiểm tra account còn ACTIVE và token thuộc đúng account.
  UPDATE accounts SET password_hash=?, credential_version=version+1, ...
  Invalidate những token cùng loại còn hiệu lực nếu policy yêu cầu.
  INSERT outbox notification / audit event.
COMMIT
Sau commit:
  Gửi notification, invalidate session/refresh token theo cơ chế đã thiết kế.
```

Nếu chỉ làm:

```java
if (tokenRepository.find(token).isValid()) {
    account.setPasswordHash(newHash);
    tokenRepository.delete(token);
}
```

thì hai request đồng thời có thể đều thấy token hợp lệ trước khi token bị xóa. Cần transaction kết hợp row lock, optimistic locking hoặc một atomic consume update có điều kiện. Retry request sau lần đầu phải thất bại mà không đổi mật khẩu lần nữa. Không sử dụng một token cho cả verify email và reset password.

### 8.3. Không tự động cấp session sau reset

Reset token là chứng cứ đủ để đặt password mới theo risk model; nó **không phải access token**. Sau khi reset thành công, phản hồi nên yêu cầu người dùng đăng nhập bình thường, có thể buộc MFA lại theo policy. Session/refresh token hiện có cần được thu hồi khi chính sách yêu cầu; việc tăng `credential_version` chỉ có tác dụng nếu pipeline xác thực/session/token thật sự **kiểm tra version này** khi truy cập.

## 9. Demo thực hành: Spring Boot 3.5.16 + vòng đời Account in-memory

Demo này dùng **in-memory state** để làm rõ flow và dễ chạy với Java 17, Spring Security 6.5; nó **không triển khai persistence/transaction database, gửi email thật, distributed rate limiting hoặc revoke token sản xuất**. Trong demo, một `DemoOutbox` ghi token vào RAM để **JUnit đọc trực tiếp**, không có API trả raw token cho client. Không đóng gói cấu hình/lưu token như vậy vào production.

**Phiên bản:** `Spring Boot 3.5.16` (phát hành 25/06/2026, bản OSS cuối của nhánh 3.5.x) và Security 6.5.x từ Boot BOM; khi tạo ứng dụng mới triển khai production nên dùng Boot 4.x còn được hỗ trợ và migration guide của Spring Security 7 nếu phù hợp.

### 9.1. Cấu trúc

```text
account-lifecycle-lab/
├── pom.xml
└── src/
    ├── main/java/demo/lifecycle/AccountLifecycleApplication.java
    └── test/java/demo/lifecycle/
        ├── AccountLifecycleHttpTests.java
        └── AccountLifecycleServiceTests.java
```

Đây là hai test sử dụng cùng mã nguồn ứng dụng nhưng phục vụ mục tiêu khác nhau: một kiểm tra HTTP filter/permission; một kiểm tra state machine/token một lần ở cấp service.

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>account-lifecycle-lab</artifactId>
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
```

### 9.3. Toàn bộ mã ứng dụng

Tạo `src/main/java/demo/lifecycle/AccountLifecycleApplication.java`. Để tiện cho lab, các class package-private nằm trong một file; ở dự án thật nên chia thành `account/api`, `domain`, `repository`, `security` và `messaging`.

```java
package demo.lifecycle;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class AccountLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountLifecycleApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
class WebSecurityConfig {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(AccountLifecycleService accounts) {
        return email -> {
            Account account = accounts.find(email)
                .orElseThrow(() ->
                    new UsernameNotFoundException("User not found"));

            return User.withUsername(account.email())
                .password(account.passwordHash())
                .authorities(account.authorities().toArray(String[]::new))
                .disabled(account.status() != AccountStatus.ACTIVE)
                .build();
        };
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/auth/register",
                    "/auth/verify",
                    "/auth/recovery/request",
                    "/auth/recovery/complete").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.POST,
                    "/admin/accounts/*/suspend").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Giữ CSRF: anonymous POST cũng có thể cần CSRF token.
            .csrf(Customizer.withDefaults())
            .build();
    }
}

enum AccountStatus {
    PENDING_VERIFICATION, ACTIVE, SUSPENDED
}

enum TokenPurpose {
    VERIFY_EMAIL, RESET_PASSWORD
}

record Account(
    String email,
    String passwordHash,
    AccountStatus status,
    Set<String> authorities
) {
    Account {
        authorities = Set.copyOf(authorities);
    }

    Account withStatus(AccountStatus next) {
        return new Account(email, passwordHash, next, authorities);
    }

    Account withPassword(String encoded) {
        return new Account(email, encoded, status, authorities);
    }
}

record ActionToken(
    String email,
    TokenPurpose purpose,
    Instant expiresAt
) {}

/**
 * Chỉ là hộp thư fake cho demo/test.
 * Raw tokens nằm trong RAM; không triển khai bean này vào production.
 */
@Component
class DemoOutbox {
    private final Map<String, EnumMap<TokenPurpose, String>> mailbox =
        new HashMap<>();

    synchronized void deliver(String email, TokenPurpose purpose,
            String rawToken) {
        mailbox.computeIfAbsent(email,
            key -> new EnumMap<>(TokenPurpose.class))
            .put(purpose, rawToken);
    }

    synchronized String lastToken(String email, TokenPurpose purpose) {
        EnumMap<TokenPurpose, String> tokens = mailbox.get(email);
        return tokens == null ? null : tokens.get(purpose);
    }
}

@Service
class AccountLifecycleService {

    private static final Duration TOKEN_TTL = Duration.ofMinutes(15);

    private final Map<String, Account> accounts = new HashMap<>();
    private final Map<String, ActionToken> actionTokens = new HashMap<>();
    private final SecureRandom random = new SecureRandom();

    private final PasswordEncoder encoder;
    private final Clock clock;
    private final DemoOutbox outbox;

    AccountLifecycleService(PasswordEncoder encoder, Clock clock,
            DemoOutbox outbox) {
        this.encoder = encoder;
        this.clock = clock;
        this.outbox = outbox;
    }

    synchronized Optional<Account> find(String email) {
        return Optional.ofNullable(accounts.get(normalize(email)));
    }

    synchronized void register(String rawEmail, String password) {
        String email = validatedEmail(rawEmail);
        validatePassword(password);

        // Public response phải giống nhau khi email đã tồn tại.
        if (accounts.containsKey(email)) {
            return;
        }

        // Role mặc định được quyết định bởi server.
        Account account = new Account(
            email,
            encoder.encode(password),
            AccountStatus.PENDING_VERIFICATION,
            Set.of("ROLE_USER")
        );

        accounts.put(email, account);
        issueToken(email, TokenPurpose.VERIFY_EMAIL);
    }

    synchronized boolean verifyEmail(String rawToken) {
        ActionToken action =
            consume(rawToken, TokenPurpose.VERIFY_EMAIL);

        if (action == null) {
            return false;
        }

        Account account = accounts.get(action.email());

        if (account == null ||
                account.status() != AccountStatus.PENDING_VERIFICATION) {
            return false;
        }

        accounts.put(account.email(),
            account.withStatus(AccountStatus.ACTIVE));
        return true;
    }

    synchronized void requestPasswordReset(String rawEmail) {
        // Cố ý không tiết lộ email có tồn tại trong HTTP response.
        String email = normalize(rawEmail);
        Account account = accounts.get(email);

        if (account == null || account.status() != AccountStatus.ACTIVE) {
            return;
        }

        issueToken(email, TokenPurpose.RESET_PASSWORD);
    }

    synchronized boolean resetPassword(String rawToken,
            String newPassword) {
        validatePassword(newPassword);

        ActionToken action =
            consume(rawToken, TokenPurpose.RESET_PASSWORD);

        if (action == null) {
            return false;
        }

        Account account = accounts.get(action.email());

        // Reset không có quyền mở lại account bị đình chỉ.
        if (account == null || account.status() != AccountStatus.ACTIVE) {
            return false;
        }

        accounts.put(account.email(),
            account.withPassword(encoder.encode(newPassword)));

        // Demo: hủy mọi action token còn lại của account.
        actionTokens.entrySet().removeIf(e ->
            e.getValue().email().equals(account.email()));

        // Production: audit, notification và session/refresh-token revocation.
        return true;
    }

    synchronized void suspend(String rawEmail) {
        String email = normalize(rawEmail);
        Account account = accounts.get(email);

        if (account == null) {
            throw new IllegalArgumentException("Invalid account");
        }

        accounts.put(email,
            account.withStatus(AccountStatus.SUSPENDED));

        actionTokens.entrySet().removeIf(e ->
            e.getValue().email().equals(email));
    }

    private void issueToken(String email, TokenPurpose purpose) {
        // Một token chưa dùng / purpose / account tại một thời điểm.
        actionTokens.entrySet().removeIf(e ->
            e.getValue().email().equals(email)
                && e.getValue().purpose() == purpose);

        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String raw = Base64.getUrlEncoder()
            .withoutPadding().encodeToString(bytes);

        actionTokens.put(digest(raw),
            new ActionToken(email, purpose,
                clock.instant().plus(TOKEN_TTL)));

        // Production: lưu digest + outbox atomically trong DB,
        // email worker gửi raw link qua kênh đã kiểm soát.
        outbox.deliver(email, purpose, raw);
    }

    private ActionToken consume(String rawToken, TokenPurpose purpose) {
        String hash = digest(rawToken);

        if (hash == null) {
            return null;
        }

        ActionToken action = actionTokens.get(hash);

        if (action == null || action.purpose() != purpose) {
            return null;
        }

        // Gỡ token trước khi áp dụng state transition.
        // synchronized bảo đảm dùng một lần trong MỘT JVM lab.
        actionTokens.remove(hash);

        if (!clock.instant().isBefore(action.expiresAt())) {
            return null;
        }

        return action;
    }

    private static String digest(String rawToken) {
        if (rawToken == null || rawToken.isBlank()
                || rawToken.length() > 200) {
            return null;
        }

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(rawToken.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    private static String normalize(String rawEmail) {
        return rawEmail == null ? ""
            : rawEmail.trim().toLowerCase(Locale.ROOT);
    }

    private static String validatedEmail(String rawEmail) {
        String email = normalize(rawEmail);

        // Validation đơn giản CHỈ CHO DEMO; email thực tế cần policy riêng.
        if (email.length() > 254
                || !email.matches("[^@\\s]+@[^@\\s]+\\.[^@\\s]+")) {
            throw new IllegalArgumentException("Invalid email");
        }

        return email;
    }

    private static void validatePassword(String password) {
        // Password không được trim hoặc tự cắt.
        if (password == null ||
                password.length() < 12 || password.length() > 128) {
            throw new IllegalArgumentException("Invalid password");
        }
    }
}

@Service
class AccountAdministrationService {
    private final AccountLifecycleService accounts;

    AccountAdministrationService(AccountLifecycleService accounts) {
        this.accounts = accounts;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void suspendAccount(String email) {
        // Production: actor/subject/tenant checks, approval và audit.
        accounts.suspend(email);
    }
}

record RegistrationRequest(String email, String password) {}
record VerifyRequest(String token) {}
record EmailRequest(String email) {}
record ResetRequest(String token, String newPassword) {}
record Notice(String message) {}

@RestController
class AccountController {

    private static final Notice GENERIC_NOTICE =
        new Notice("If eligible, instructions will be sent.");

    private final AccountLifecycleService accounts;
    private final AccountAdministrationService administration;

    AccountController(AccountLifecycleService accounts,
            AccountAdministrationService administration) {
        this.accounts = accounts;
        this.administration = administration;
    }

    @PostMapping("/auth/register")
    ResponseEntity<Notice> register(@RequestBody RegistrationRequest request) {
        accounts.register(request.email(), request.password());
        return ResponseEntity.accepted().body(GENERIC_NOTICE);
    }

    @PostMapping("/auth/verify")
    ResponseEntity<Void> verify(@RequestBody VerifyRequest request) {
        if (!accounts.verifyEmail(request.token())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid or expired token");
        }
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/auth/recovery/request")
    ResponseEntity<Notice> requestRecovery(@RequestBody EmailRequest request) {
        accounts.requestPasswordReset(request.email());
        return ResponseEntity.accepted().body(GENERIC_NOTICE);
    }

    @PostMapping("/auth/recovery/complete")
    ResponseEntity<Void> completeRecovery(@RequestBody ResetRequest request) {
        if (!accounts.resetPassword(
                request.token(), request.newPassword())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid or expired token");
        }
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/admin/accounts/{email}/suspend")
    ResponseEntity<Void> suspend(@PathVariable String email) {
        administration.suspendAccount(email);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "me:" + authentication.getName();
    }
}

@RestControllerAdvice
class ValidationErrors {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Notice> invalidInput() {
        return ResponseEntity.badRequest()
            .body(new Notice("Invalid request"));
    }
}
```

### 9.4. Đọc code theo trách nhiệm

- `register(...)` tạo account `PENDING_VERIFICATION` với `ROLE_USER` cố định server-side; request DTO không chứa role.
- `verifyEmail(...)` chỉ nhận token `VERIFY_EMAIL`, kiểm tra TTL và trạng thái rồi chuyển `ACTIVE`. Token đã dùng bị xóa.
- `requestPasswordReset(...)` chỉ phát token cho account ACTIVE, nhưng **HTTP response giống nhau** với email không tồn tại.
- `resetPassword(...)` xác minh token `RESET_PASSWORD`, thay password hash bằng `DelegatingPasswordEncoder`, không làm `SUSPENDED` thành `ACTIVE`.
- `digest(...)` băm token ngẫu nhiên trước khi lưu; `SecureRandom` cấp token entropy cao và `Base64 URL-safe` để token có thể đưa vào liên kết.
- Các method của service dùng `synchronized` để tránh hai request tiêu thụ cùng token trên **một JVM**. Chúng không giải quyết concurrency đa replica; chuyển sang DB phải dùng transaction và atomic update.
- `DemoOutbox` cố ý là hộp thư giả giữ raw token để test lấy trực tiếp. Ứng dụng thật phải dùng mail gateway/outbox an toàn và không có endpoint đọc token.
- `UserDetailsService` là adapter của kho Account cho Spring Security. Tài khoản chưa ACTIVE được map thành disabled; provider từ chối login.
- `AccountAdministrationService` yêu cầu `ROLE_ADMIN` ở cả HTTP và method level. Demo không cung cấp cách tự đăng ký admin: đây là chủ ý vì quyền quản trị phải được provision qua kênh đáng tin.
- `SessionCreationPolicy.STATELESS` dùng Basic credential trong từng request. Account được suspend sẽ bị chặn ở lần xác thực Basic kế tiếp; với session/JWT cần thiết kế revoke riêng.
- CSRF vẫn bật cho POST. Một SPA browser dùng cookie/Basic có thể gửi credential tự động; không tắt CSRF khi chưa đánh giá mô hình xác thực.
- `ValidationErrors` trả lỗi chung khi dữ liệu sai. Demo chưa có gửi email thật, rate limiting, abuse controls hay handling transactional failure. Những phần đó cần thiết trước production.

### 9.5. Integration test HTTP: từ đăng ký đến suspend

Tạo `src/test/java/demo/lifecycle/AccountLifecycleHttpTests.java`:

```java
package demo.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountLifecycleHttpTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    DemoOutbox outbox;

    private static final String EMAIL = "alice107@example.test";
    private static final String ORIGINAL = "FirstPassphrase2026!";
    private static final String CHANGED = "SecondPassphrase2026!";

    @Test
    void completeLifecycleWithAuthenticationAndAuthorization()
            throws Exception {

        // Anonymous POST thiếu CSRF bị từ chối.
        mvc.perform(post("/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"alice107@example.test",
                     "password":"FirstPassphrase2026!"}
                    """))
            .andExpect(status().isForbidden());

        // Đăng ký trả lời 202, không trả raw token.
        mvc.perform(post("/auth/register")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"alice107@example.test",
                     "password":"FirstPassphrase2026!"}
                    """))
            .andExpect(status().isAccepted());

        // Chưa verify email => provider từ chối login.
        mvc.perform(get("/me")
                .with(httpBasic(EMAIL, ORIGINAL)))
            .andExpect(status().isUnauthorized());

        // Test-only: lấy token trong fake outbox, không qua HTTP.
        String verify = outbox.lastToken(
            EMAIL, TokenPurpose.VERIFY_EMAIL);

        mvc.perform(post("/auth/verify")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"token\":\"" + verify + "\"}"))
            .andExpect(status().isNoContent());

        // Token verify chỉ dùng một lần.
        mvc.perform(post("/auth/verify")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"token\":\"" + verify + "\"}"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/me")
                .with(httpBasic(EMAIL, ORIGINAL)))
            .andExpect(status().isOk())
            .andExpect(content().string("me:" + EMAIL));

        // Public reset request không leak account existence.
        mvc.perform(post("/auth/recovery/request")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"nobody@example.test\"}"))
            .andExpect(status().isAccepted());

        mvc.perform(post("/auth/recovery/request")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"" + EMAIL + "\"}"))
            .andExpect(status().isAccepted());

        String reset = outbox.lastToken(
            EMAIL, TokenPurpose.RESET_PASSWORD);

        mvc.perform(post("/auth/recovery/complete")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"token\":\"" + reset + "\"," +
                    "\"newPassword\":\"" + CHANGED + "\"}"))
            .andExpect(status().isNoContent());

        // Reset token không còn dùng được.
        mvc.perform(post("/auth/recovery/complete")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"token\":\"" + reset + "\"," +
                    "\"newPassword\":\"SomeOtherPass2026!\"}"))
            .andExpect(status().isBadRequest());

        // Basic kiểm tra hash mới: password cũ không còn hiệu lực.
        mvc.perform(get("/me")
                .with(httpBasic(EMAIL, ORIGINAL)))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic(EMAIL, CHANGED)))
            .andExpect(status().isOk());

        // User thường không được gọi admin API.
        mvc.perform(post("/admin/accounts/" + EMAIL + "/suspend")
                .with(httpBasic(EMAIL, CHANGED))
                .with(csrf()))
            .andExpect(status().isForbidden());

        // Tài khoản staff là mock test để xác minh admin policy.
        // Demo không cung cấp public endpoint tạo ROLE_ADMIN.
        mvc.perform(post("/admin/accounts/" + EMAIL + "/suspend")
                .with(user("staff").roles("ADMIN"))
                .with(csrf()))
            .andExpect(status().isNoContent());

        mvc.perform(get("/me")
                .with(httpBasic(EMAIL, CHANGED)))
            .andExpect(status().isUnauthorized());
    }
}
```

**Giải thích kỹ test:**

1. Request đăng ký được phép về **authorization**, nhưng vì CSRF bật, POST không có CSRF token vẫn nhận 403. `permitAll` không đồng nghĩa bỏ qua `CsrfFilter`.
2. Tài khoản vừa đăng ký chưa được verify bị từ chối đăng nhập dù password đúng.
3. Test lấy raw verification/reset token chỉ qua `DemoOutbox` Java bean, không qua một HTTP endpoint công khai.
4. Verify token đúng chuyển tài khoản sang ACTIVE; gọi lại token nhận 400.
5. HTTP Basic dùng chính `UserDetailsService` của app và `PasswordEncoder`, nên test có đường xác thực thật; khác với `@WithMockUser`.
6. Reset password thay hash đã lưu; Basic với password cũ nhận 401, password mới 200; token reset được tiêu thụ một lần.
7. `user("staff").roles("ADMIN")` là authentication **giả lập** để test authorization quản trị. Nó không kiểm chứng account admin production hay password thật. Tài khoản thường vẫn bị chặn.
8. Sau suspend, account bị disabled đối với lần xác thực Basic tiếp theo. Nếu dùng session/OIDC/JWT production, còn phải xác minh cơ chế revoke đã được triển khai.

Bài test này dùng một email fixture cố định và một method duy nhất đi qua vòng đời, vì service demo lưu trạng thái trong RAM. Khi thêm nhiều test độc lập, dùng email ngẫu nhiên theo test, factory tạo instance mới hoặc context isolation; không để test sau phụ thuộc thứ tự hoặc session/tokens của test trước.

### 9.6. Service test: token hết hạn và không thể đổi sai trạng thái

Tạo `src/test/java/demo/lifecycle/AccountLifecycleServiceTests.java`:

```java
package demo.lifecycle;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AccountLifecycleServiceTests {

    private static final String EMAIL = "student@example.test";
    private static final String ORIGINAL = "LongPassphrase2026!";
    private static final String NEW_PASSWORD = "AnotherPassphrase2026!";

    static final class MutableClock extends Clock {
        private Instant now = Instant.parse("2026-11-04T00:00:00Z");

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return Clock.fixed(now, zone);
        }

        @Override
        public Instant instant() {
            return now;
        }

        void advance(Duration duration) {
            now = now.plus(duration);
        }
    }

    @Test
    void verificationIsSingleUseAndRecoveryExpires() {
        MutableClock clock = new MutableClock();
        DemoOutbox outbox = new DemoOutbox();
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        AccountLifecycleService service =
            new AccountLifecycleService(encoder, clock, outbox);

        service.register(EMAIL, ORIGINAL);

        Account pending = service.find(EMAIL).orElseThrow();
        assertEquals(
            AccountStatus.PENDING_VERIFICATION, pending.status());
        assertEquals(java.util.Set.of("ROLE_USER"),
            pending.authorities());
        assertTrue(encoder.matches(
            ORIGINAL, pending.passwordHash()));

        String verify = outbox.lastToken(
            EMAIL, TokenPurpose.VERIFY_EMAIL);
        assertNotNull(verify);

        // Reset token không thể thay verification token.
        assertFalse(service.resetPassword(
            verify, NEW_PASSWORD));

        assertTrue(service.verifyEmail(verify));
        assertFalse(service.verifyEmail(verify));
        assertEquals(AccountStatus.ACTIVE,
            service.find(EMAIL).orElseThrow().status());

        service.requestPasswordReset(EMAIL);
        String reset = outbox.lastToken(
            EMAIL, TokenPurpose.RESET_PASSWORD);
        assertNotNull(reset);

        // Token 15 phút: hết hạn tại đúng expiry.
        clock.advance(Duration.ofMinutes(16));

        assertFalse(service.resetPassword(reset, NEW_PASSWORD));
        assertTrue(encoder.matches(
            ORIGINAL, service.find(EMAIL).orElseThrow().passwordHash()));

        service.requestPasswordReset(EMAIL);
        String fresh = outbox.lastToken(
            EMAIL, TokenPurpose.RESET_PASSWORD);

        assertTrue(service.resetPassword(fresh, NEW_PASSWORD));
        assertFalse(service.resetPassword(fresh, NEW_PASSWORD));
        assertTrue(encoder.matches(
            NEW_PASSWORD, service.find(EMAIL).orElseThrow().passwordHash()));

        service.suspend(EMAIL);
        assertEquals(AccountStatus.SUSPENDED,
            service.find(EMAIL).orElseThrow().status());

        // Recovery không tự mở lại account bị suspend.
        service.requestPasswordReset(EMAIL);
        assertFalse(service.resetPassword(
            fresh, "ThirdPassphrase2026!"));
    }

    @Test
    void duplicateRegistrationCannotGrantAdminPrivilege() {
        DemoOutbox outbox = new DemoOutbox();
        AccountLifecycleService service = new AccountLifecycleService(
            PasswordEncoderFactories.createDelegatingPasswordEncoder(),
            Clock.fixed(Instant.parse("2026-11-04T00:00:00Z"),
                ZoneOffset.UTC),
            outbox
        );

        service.register(EMAIL, ORIGINAL);
        service.register(EMAIL, "DifferentPassphrase2026!");

        Account unchanged = service.find(EMAIL).orElseThrow();

        assertEquals(java.util.Set.of("ROLE_USER"),
            unchanged.authorities());

        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();
        assertTrue(encoder.matches(
            ORIGINAL, unchanged.passwordHash()));
        assertFalse(encoder.matches(
            "DifferentPassphrase2026!", unchanged.passwordHash()));
    }
}
```

**Giới hạn của unit test:** `MutableClock` giúp tái hiện expiry mà không gọi `Thread.sleep`. `synchronized` bảo vệ thao tác trong một instance service; chưa có test đa JVM/transaction hay SMTP thật. Test cho production nên thêm cạnh tranh đồng thời của hai reset requests, optimistic lock/unique constraints, outbox delivery/retry, rate limiting, CSRF và revoke session/token.

### 9.7. Chạy và quan sát

Tại thư mục `account-lifecycle-lab`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Sau khi server chạy ở localhost, có thể thử endpoint public với curl và JSON; **POST cần CSRF token** theo cấu hình. Vì demo không cung cấp flow browser lấy CSRF token hoặc SMTP thật, hãy dùng **MockMvc tests ở trên** để chạy trọn luồng xác minh/recovery một cách tái lập. Không tắt CSRF và không đưa token từ fake outbox lên endpoint public chỉ để thuận tiện thử bằng curl.

Trên hệ thống product thật, frontend đăng ký/khôi phục phải có cơ chế lấy/gửi CSRF token theo `CsrfTokenRepository` nếu sử dụng browser credentials có nguy cơ CSRF; hoặc được cấu hình rõ chính sách khác cho pure Bearer API theo threat model. Kết quả mong đợi khi chạy đúng dependency và JDK:

| Request | Kỳ vọng | Bằng chứng |
| --- | --- | --- |
| POST register thiếu CSRF | 403 | Filter CSRF |
| POST register có CSRF, email mới | 202 generic | Không trả raw verification token |
| GET /me với email vừa tạo | 401 | Chưa verified, disabled |
| POST verify với token hợp lệ | 204 | ACTIVE |
| POST verify dùng lại token | 400 | Single-use |
| GET /me + Basic đúng sau verify | 200 | UserDetailsService/PasswordEncoder |
| POST request recovery email không tồn tại | 202 generic | Giảm enumeration |
| POST complete reset token hợp lệ | 204 | Đổi hash |
| POST complete dùng lại token | 400 | Single-use |
| GET /me với password cũ | 401 | Hash đã đổi |
| GET /me với password mới | 200 | Provider dùng hash mới |
| POST admin suspend với user thường | 403 | Không có ROLE_ADMIN |
| POST admin suspend với mock staff | 204 | Admin policy |
| GET /me sau suspend | 401 | Account disabled |

**Những gì chưa có trong demo:** Email thật, thông báo khi password được đổi, reset flow UI, timeout chống enumeration bằng hàng đợi, persistent repository, transaction distributed, revoke session và abuse monitoring. Không nên dùng demo như một sản phẩm sẵn sàng triển khai.

## 10. Khi đưa vào database: mapping UserDetailsService nên làm gì?

Một adapter minh họa, chỉ mô tả cách nối Spring Security với kho nghiệp vụ:

```java
@Service
class DatabaseUserDetailsService implements UserDetailsService {
    private final AccountRepository repository;

    DatabaseUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        AccountEntity account = repository
            .findByLoginIdentifier(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Invalid credentials"));

        return User.withUsername(account.getId().toString())
            .password(account.getPasswordHash())
            .authorities(account.getAuthorities()
                .toArray(String[]::new))
            .disabled(account.getStatus() != AccountStatus.ACTIVE)
            .accountLocked(account.isRiskLocked())
            .build();
    }
}
```

**Đây là snippet thiết kế, không phải file biên dịch độc lập:** `AccountRepository`/`AccountEntity` và mappings tùy dự án. Nếu `username` trong `UserDetails` đổi thành ID, cần xác định rõ cách login identifier được tra cứu và `Authentication.getName()` sẽ là gì. Với các hệ thống dùng email login, có thể trả username là email như demo nhưng nên cung cấp principal domain chứa immutable ID khi cần ownership check.

`UserDetailsService` chỉ tải user cho mechanism username/password. Không nhét gửi email hoặc tạo reset token vào method này. Nếu dùng OIDC/JWT, thông tin có thể đến từ IdP/verified claims, và tài khoản nội bộ được liên kết qua subject ổn định, không tin email chưa xác minh hoặc không dùng `issuer`.

### 10.1. Cần transaction ở service, không phải ở web filter

Các thao tác cập nhật account nên có transaction ở domain service:

```java
@Transactional
public void verifyEmail(String rawToken) {
    // Validate purpose/expiry; lock/atomic consume token.
    // Transition PENDING_VERIFICATION -> ACTIVE.
    // Insert audit + outbox event in cùng transaction.
}
```

**Snippet trên là pseudocode định hướng**, không có đủ repository và exception classes để chạy độc lập. Với Spring Data JPA, mapping entity, version và các repository method phải phù hợp transaction isolation. Không dựa riêng vào annotation `@Transactional` để đảm bảo single-use nếu code vẫn đọc rồi cập nhật không khóa/không điều kiện. Kiểm thử race cụ thể.

## 11. Quy tắc bảo mật cho từng workflow

### 11.1. Đăng ký

- Kiểm tra dữ liệu, bảo vệ chống bot/spam/rate limiting và tránh duplicate.
- Áp password policy phù hợp, hỗ trợ passphrase dài, kiểm tra compromised password khi có khả năng.
- Hash password bằng `PasswordEncoder`; không log raw password.
- Tạo default role từ server, không mass assignment.
- Xác minh email/kênh liên hệ trước khi cấp những quyền cần verified identity.
- Unique constraint + transaction + outbox để tránh trạng thái dở dang.
- Bảo vệ verification endpoint khỏi token replay và gửi resend tràn lan.
- Không tự đăng nhập trước khi hoàn tất yêu cầu verification/step-up của sản phẩm.

### 11.2. Quên/đặt lại mật khẩu

- Response chung cả account tồn tại/không tồn tại và account không đủ điều kiện.
- Giới hạn request theo actor/IP/account/device; phát hiện abuse.
- Token random đủ dài, purpose riêng, TTL ngắn, một lần, hash-only storage, consume atomic.
- Link HTTPS với domain tin cậy từ config, chống host-header poisoning, không leak token qua logs/referrer.
- POST hoàn tất reset sau khi người dùng xác nhận, tránh link scanner tự thay đổi trạng thái.
- Không gửi password mới qua email; người dùng tự đặt password.
- Sau đổi: thông báo, invalidate/revoke session và refresh tokens theo policy, không auto-login.
- Yêu cầu re-auth/MFA hoặc hỗ trợ thủ công được xác minh khi recovery có rủi ro cao.

### 11.3. Thay email

- Session đã xác thực **chưa chắc** đủ cho thay danh tính: yêu cầu step-up nếu nhạy cảm.
- Gửi thông báo địa chỉ cũ; xác minh địa chỉ mới trước khi dùng làm login/recovery.
- Kiểm tra unique constraint và tranh chấp với account khác.
- Lưu pending new email riêng, không xóa ngay email đang dùng trước verification.
- Chặn thay email của user khác bằng accountId từ body nếu actor không có quyền.
- Xử lý các IdP có email claim không verified hoặc email thay đổi.

### 11.4. Đổi quyền/quản trị

- Có permission riêng, xác minh tenant/scope và nguyên tắc least privilege.
- Role/authority không đến từ frontend.
- Admin grant/revoke cần audit, đôi khi approval hai người hoặc step-up.
- Suspension phải chặn login mới và thu hồi access đang tồn tại theo policy; không dựa vào boolean trong DB nếu session/JWT chưa kiểm lại.
- Khi mở khóa, xác nhận chủ thể, lý do, bằng chứng và thông báo.
- Đóng/xóa account phải xử lý dữ liệu và retention phù hợp, không gọi `deleteAll` một cách tùy tiện.

### 11.5. Kiểm thử và vận hành

- Có test tích cực và tiêu cực: đúng/sai token, hết hạn, replay, sai purpose, account suspended.
- Test concurrency với DB thật nếu có atomic consume, không chỉ một JUnit tuần tự.
- Test API không leak account existence qua response **và timing** trong điều kiện có tải.
- Dùng HTTPS/TLS, secret redaction, CSP/referrer policy thích hợp, cookie flags, CORS/CSRF policy.
- Audit không chứa password/hash/token; quản lý retention và quyền đọc log.
- Monitor signup/reset rate, deliverability, unusual recovery/suspension, failure spikes.
- Nếu dùng external IdP, kiểm thử lifecycle thuộc IdP thay vì dựng một user store cạnh tranh không đồng bộ.

## 12. Những lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Cho rằng `UserDetailsService` tự cung cấp endpoint đăng ký | Không có flow nghiệp vụ/account store | Tách Account API/service/repository |
| Chỉ có `InMemoryUserDetailsManager` cho người dùng thật | Mất dữ liệu restart, không chia sẻ replica | Database/IdP, migration và vận hành |
| DTO signup chứa `roles` và copy vào entity | Leo thang quyền | Role mặc định từ server |
| Lưu password plaintext/MD5/SHA-256 đơn thuần | Dễ lộ/mò mật khẩu | `PasswordEncoder` phù hợp, work factor |
| Email chưa verified đã được xác thực đầy đủ | Dùng địa chỉ người khác, spam/abuse | Pending state và verification |
| Forgot API trả 404 “email không có” | Account enumeration | Phản hồi chung, timing/rate limits |
| Token reset là timestamp/userId/UUID đoán được | Có thể brute force | CSPRNG 32 bytes, TTL, hash |
| Dùng reset token nhiều lần | Replay/đổi mật khẩu lần hai | Atomic consume, consumedAt/expiry |
| Token verify dùng được để reset | Cross-purpose privilege | Purpose riêng, kiểm tra ở server |
| GET link tự đổi password | Mail scanner/CSRF ngoài dự kiến | Form xác nhận và POST |
| Token reset xuất hiện trong server log | Đánh cắp recovery credential | Redaction, no-referrer, log hygiene |
| Reset làm account SUSPENDED thành ACTIVE | Vượt quyết định quản trị | Chuyển trạng thái rõ và kiểm tra điều kiện |
| Reset xong tự đăng nhập | Nâng recovery token thành session | Yêu cầu login lại theo policy |
| Đổi mật khẩu xong không revoke session | Session bị chiếm vẫn dùng được | Session/token revocation thực sự |
| Đổi role trong DB là đủ để cập nhật JWT cũ | Claim quyền cũ vẫn được chấp nhận | TTL, denylist/version/reauth |
| Chỉ `hasRole("ADMIN")`, bỏ qua tenant | Admin tổ chức A quản lý B | Object/tenant authorization ở service |
| Gửi email trước DB commit | Link vô hiệu nếu transaction rollback | Transactional outbox |
| Chỉ `@Transactional` mà không khóa token | Hai request cùng consume | Conditional update/lock + test race |
| Log raw request body/reset token | Lộ secret và PII | Log metadata tối thiểu |
| Chỉ test signup happy path | Bỏ sót abuse, expiry, replay | Ma trận state + negative tests |

## 13. Ma trận kiểm thử theo trạng thái và tác nhân

| Tình huống | Actor/account | Kỳ vọng |
| --- | --- | --- |
| Đăng ký hợp lệ | Anonymous, email mới | Account PENDING; response chung |
| Đăng ký lại | Anonymous, email cũ | Không ghi đè password/role; response không leak |
| Đăng nhập trước verify | PENDING | Từ chối |
| Verify đúng | PENDING, token còn hạn | Chuyển ACTIVE |
| Verify lại | Token đã dùng | Từ chối |
| Verify sau TTL | Token hết hạn | Từ chối |
| Dùng token RESET ở endpoint VERIFY | Sai purpose | Từ chối |
| Login đúng sau verify | ACTIVE | Được xác thực |
| Recovery request email không tồn tại | Anonymous | Response chung như email tồn tại |
| Reset đúng | ACTIVE, token chưa dùng | Hash mới, token consumed |
| Reset bằng token cũ | Token đã dùng | Từ chối |
| Reset token hết hạn | ACTIVE | Từ chối, password giữ nguyên |
| Login bằng password cũ sau reset | ACTIVE | Từ chối |
| Login bằng password mới sau reset | ACTIVE | Thành công |
| Suspend account | Staff có permission | Chuyển SUSPENDED, audit/revoke |
| Suspend account | User thường | 403, trạng thái không đổi |
| Login sau suspend | SUSPENDED | Từ chối |
| Reset sau suspend | SUSPENDED | Không tự mở khóa |
| Đổi email | User đã re-auth, token email mới | Cập nhật sau verification |
| Truy cập account tenant khác | Admin giới hạn tenant | Từ chối ở service |
| Đóng account | Đã được authorize và hết nghĩa vụ | Không login, thực hiện retention |
| Hai request dùng cùng reset token song song | ACTIVE | Chỉ một request commit |
| Token bị scan qua GET | Chưa POST xác nhận | Không tự đổi mật khẩu |
| Session cũ sau reset/suspend | Đang login từ trước | Bị revoke theo chính sách |
| User từ IdP | Đã xác thực IdP | Map đúng subject/tenant, không dựa email chưa verified |

## 14. Câu hỏi tự đánh giá

**Câu 1.** Đã có `DaoAuthenticationProvider` và `UserDetailsService`, vì sao vẫn cần `AccountLifecycleService`?

**Trả lời:** Hai thành phần đầu tải và xác minh user cho request authentication. Đăng ký, xác minh email, recovery, khóa/mở và audit là nghiệp vụ nhiều bước, gồm persistence, transaction, notification và policy riêng.

**Câu 2.** User gửi JSON có `"roles":["ROLE_ADMIN"]` khi đăng ký. Backend nên làm gì?

**Trả lời:** Không tin hoặc không tiếp nhận role từ signup DTO; gán quyền mặc định do server quyết định. Admin role chỉ được cấp qua flow có phân quyền và audit.

**Câu 3.** Vì sao reset token có thể được băm SHA-256 trong khi mật khẩu phải dùng BCrypt/Argon2/PBKDF2?

**Trả lời:** Token do CSPRNG sinh ra có entropy cao, khó brute force. Mật khẩu con người có entropy thấp và dễ đoán, cần password hash có work factor. Không dùng SHA-256 thô để lưu mật khẩu.

**Câu 4.** Client nhận 202 từ `/auth/recovery/request` có nghĩa email chắc chắn tồn tại không?

**Trả lời:** Không. Response cố tình giống nhau dù account tồn tại hay không; server chỉ gửi hướng dẫn nếu account đủ điều kiện.

**Câu 5.** Token reset đã hết hạn nhưng vẫn được chấp nhận vì server chỉ kiểm hash. Thiếu gì?

**Trả lời:** Phải kiểm tra purpose, expiry, consumed state và account status, với atomic consume trong transaction. Digest khớp chỉ chứng minh biết token, chưa chứng minh token còn hợp lệ.

**Câu 6.** Sau khi suspend account, một phiên browser đang đăng nhập vẫn có thể vào ứng dụng. Vì sao?

**Trả lời:** Session có thể chứa authentication đã xác minh trước đó; provider không tự chạy lại trên mọi request. Cần session/token revocation hoặc kiểm tra account state theo cơ chế đã thiết kế.

**Câu 7.** Tại sao email recovery không được ghép từ `Host` request tùy ý?

**Trả lời:** Header có thể bị giả mạo, dẫn đến gửi link trỏ đến domain attacker. Dùng base origin tin cậy từ config và kiểm soát proxy/forwarded headers.

**Câu 8.** Có thể dùng một token xác minh email để hoàn tất reset password không?

**Trả lời:** Không. Token phải ràng buộc purpose và action. Code cần từ chối nếu purpose sai dù digest và account có thật.

**Câu 9.** `@Transactional` có bảo đảm token single-use nếu hai request cùng đọc row chưa consumed không?

**Trả lời:** Chưa chắc. Cần lock hoặc atomic update với điều kiện `consumed_at IS NULL`/`expires_at > now`, kiểm tra số row cập nhật và test concurrency.

**Câu 10.** App dùng OIDC, có cần tự lưu và reset password của tất cả user SSO không?

**Trả lời:** Thường không. Password/MFA và recovery của tài khoản liên kết thuộc IdP. Ứng dụng vẫn có account/profile, tenant, role và lifecycle nội bộ, nhưng phải đồng bộ đúng qua subject đáng tin.

## 15. Checklist khi review triển khai thật

- [ ] Domain account có ID ổn định, trạng thái và unique login identifier phù hợp?
- [ ] Có phân tách registration/recovery/admin domain khỏi `UserDetailsService`/filter?
- [ ] Signup chỉ nhận field cho phép, server gán default role, chống mass assignment?
- [ ] Email verification token CSPRNG, purpose riêng, TTL, single-use, hash-only store?
- [ ] Password hash dùng `PasswordEncoder` an toàn, có policy password và nâng version?
- [ ] Forgot endpoint phản hồi chung, kiểm soát timing và rate limiting?
- [ ] Reset link dùng HTTPS/origin tin cậy, không leak qua logs/referrer/cache?
- [ ] GET link chỉ hiển thị form; POST thực hiện thay đổi và xử lý CSRF theo threat model?
- [ ] Consume token atomic trong transaction, có test race và retry?
- [ ] Email/outbox/audit được xử lý đúng trước/sau commit, không làm mất message?
- [ ] Reset không tự login và không bypass trạng thái SUSPENDED/CLOSED?
- [ ] Sau reset/suspend/đổi role, phiên và refresh token được revoke hoặc cập nhật theo policy?
- [ ] Thay email có re-auth, xác minh email mới và thông báo kênh cũ?
- [ ] Admin operations kiểm tra authority, tenant scope, role escalation và audit?
- [ ] Logout/session expiration/token rotation được kiểm thử ngoài username/password?
- [ ] Account đóng có retention, xóa/anonymize và nghĩa vụ dữ liệu rõ ràng?
- [ ] Test bao gồm happy path, bad password, expired/replayed token, wrong purpose, disabled account, concurrent reset, owner/tenant?
- [ ] Demo in-memory/fake outbox/credential mẫu không được deploy production?
- [ ] Nếu dùng IdP, flow quản lý credential/recovery nằm đúng tại IdP thay vì tự trùng lặp?

## 16. Ghi nhớ

1. **Account lifecycle thuộc domain nghiệp vụ của ứng dụng.** Spring Security cung cấp hạ tầng xác thực/phân quyền; nó không tự tạo toàn bộ signup/recovery/admin workflow.
2. **Account entity khác UserDetails:** Entity sở hữu trạng thái, ID, business invariants; `UserDetailsService` chỉ chuyển dữ liệu đáng tin sang Spring Security khi xác thực password.
3. **Registration cần transaction + unique constraint + verification**, server gán quyền mặc định và hạn chế abuse.
4. **Recovery là đường bảo mật nhạy cảm:** token CSPRNG, ngắn hạn, dùng một lần, lưu hash, chống enumeration, không auto-login sau reset.
5. **Quản trị không chỉ là hasRole:** phải xét actor, tenant, resource, audit, step-up và thu hồi phiên/token.
6. **Thay đổi trạng thái trong DB không tự thu hồi authentication đã cấp.** Thiết kế rõ session/refresh-token/JWT revocation và kiểm thử.
7. **Demo in-memory chỉ để học.** Production cần persistence, transaction, email/outbox, ratelimit, audit, secret protection và policy dữ liệu.

## Tài liệu tham khảo

- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Password Storage / DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Email Validation and Verification Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [Spring Boot 3.5.16 release (25/06/2026)](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
