# Đổi mật khẩu, đặt lại mật khẩu và những phiên cần thu hồi

Trong Spring Security, **đổi mật khẩu** (*change password*) và **đặt lại mật khẩu** (*reset password*) không phải cùng một quy trình. Chúng có thể cùng kết thúc bằng việc tạo password hash mới, nhưng khác **bằng chứng xác minh danh tính**, **quyền thực hiện** và **vòng đời những phiên đăng nhập đã cấp trước đó**.

**Vấn đề bảo mật thường bị bỏ quên:** lưu hash mới trong database **không mặc nhiên thu hồi** HTTP session, cookie remember-me, refresh token hoặc JWT access token đã phát hành. Một kẻ tấn công nắm được session cookie có thể tiếp tục được coi là authenticated dù nạn nhân đã đổi mật khẩu, nếu ứng dụng không có cơ chế thu hồi phù hợp.

Bài học này dành cho **Spring Boot 3, Spring Security 6.x, Java 17+ (Servlet/MVC)** và tách ba việc rõ ràng:

1. Đổi mật khẩu khi đã đăng nhập: xác thực lại theo mức rủi ro, kiểm tra mật khẩu hiện tại hoặc nhân tố phù hợp, tạo hash mới và áp dụng chính sách thu hồi phiên.
2. Quên mật khẩu: yêu cầu reset qua kênh khôi phục đáng tin cậy, nhận token bí mật đủ ngẫu nhiên, chỉ dùng một lần, hết hạn, sau đó đặt mật khẩu mới **mà không tự đăng nhập**.
3. Thu hồi những bằng chứng truy cập cũ: phân biệt session phía server, remember-me, refresh token, access token tự chứa, cookie client, OAuth2/SSO và recovery token.

Các ví dụ trong bài có Java 17 độc lập và ứng dụng Spring Security mẫu. Dữ liệu/hạ tầng demo trong bộ Spring Boot là **in-memory** để quan sát dễ dàng, **không phải** một hệ thống reset mật khẩu production. Phần production yêu cầu database transaction, rate limiting, MFA/step-up, CSRF, email/outbox, audit, thiết kế multi-node và chính sách thu hồi rõ ràng.

## 1. Change password, reset password và logout-all khác nhau

| Hoạt động | Bằng chứng | Khi nào đổi hash? | Phiên đang tồn tại |
| --- | --- | --- | --- |
| Change password | User đã authenticated, có recent re-auth/current password hoặc factor tương đương | Sau khi kiểm tra actor, policy và credentials | Nên có policy rõ: revoke tất cả, hoặc giữ phiên hiện tại sau re-auth/rotate session ID |
| Reset request | Chỉ có email/username để gửi thử thách | **Không đổi** | Không tự revoke chỉ vì có người gửi request |
| Reset confirm | Reset token hợp lệ, còn hạn, chưa dùng, đúng account/purpose | Sau khi consume token **atomically** | Thường revoke các phiên cũ, refresh tokens, các recovery links còn lại |
| Logout một phiên | Session/token hiện tại | Không cần đổi password | Chỉ một phiên, trừ khi có logout-all policy |
| Logout mọi thiết bị | Một thao tác có xác minh/quyền phù hợp | Không nhất thiết đổi password | Phải làm những session/token cũ bị server từ chối |
| Phục hồi account bị chiếm | Bằng chứng độc lập đủ mạnh, review MFA/recovery bindings | Thường cần đổi password và các secrets liên quan | Cần phạm vi thu hồi rộng hơn và kiểm tra các authenticator/recovery channel bị attacker chỉnh sửa |

Một email có thể được bất kỳ ai biết. Vì vậy `POST /reset/request` không chứng minh người yêu cầu là chủ account; không được tự động khóa tài khoản, thu hồi mọi session của nạn nhân hay cấp reset token trong HTTP response chỉ vì email đó tồn tại.

## 2. Vì sao thay password hash không đủ để logout?

Giả sử Alice đang có:

```text
Account alice
  passwordHash = hash(oldPassword)

Browser A: JSESSIONID=A, Authentication của Alice đã lưu
Browser B: JSESSIONID=B, Authentication của Alice đã lưu
Mobile C: refreshToken=R3
API D: JWT accessToken=T4, exp còn 12 phút
Reset link P5: chưa dùng

Alice đổi mật khẩu:
  passwordHash = hash(newPassword)

Các bằng chứng A, B, R3, T4, P5 không tự biến mất.
```

Khi login lần đầu, `UsernamePasswordAuthenticationToken` với raw password có thể được gửi qua `AuthenticationManager` và `DaoAuthenticationProvider`. Sau đó Spring Security lưu một `Authentication` đã xác thực vào `SecurityContext` theo cơ chế session. Những request HTTP tiếp theo thường dựa vào cookie/session chứ không chạy `PasswordEncoder.matches` trên raw password ở mỗi lần.

Hệ quả:

- Cập nhật hash làm những **lần login mới** với mật khẩu cũ thất bại.
- Session đã tạo từ trước vẫn có `Authentication` và có thể được chấp nhận cho tới khi bị hủy/expire/revoke.
- Refresh token còn sống có thể tiếp tục lấy access token mới nếu authorization server chưa revoke.
- JWT access token đã ký không tự mất hiệu lực khi DB password thay đổi.
- Recovery link phát trước đó có thể tiếp tục đặt lại mật khẩu trừ khi bị hủy.
- Xóa cookie hiện tại trên browser không xóa bản copy cookie mà attacker đã lấy, nếu session server vẫn tồn tại.

**Định nghĩa đúng “thu hồi phiên”:** server/authorization service phải **từ chối sử dụng bằng chứng cũ**. Tác động lên giao diện/cookie client là bổ sung, không thay cho việc hủy hoặc kiểm tra trạng thái phía server.

## 3. Đổi mật khẩu khi đã đăng nhập

### 3.1. Luồng đề xuất

```text
POST /account/change-password
  |
  +-- Spring Security authentication & authorization
  +-- CSRF check (với cookie/session browser)
  |
  v
Server lấy principal ID từ Authentication đáng tin
  |
  +-- Xác minh lại current password hoặc step-up factor phù hợp
  +-- Rate limit các lần thử current password
  +-- Kiểm tra trạng thái account, MFA/risk policy
  +-- Kiểm tra password mới (length, breached-password rules...)
  |
  v
Transaction:
  - PasswordEncoder.encode(newPassword)
  - Update password_hash
  - Increment credentialVersion/authVersion
  - Invalidate pending reset challenges
  - Persist audit/outbox event
  |
  v
Revoke sessions/token families theo policy
  |
  +-- Hiển thị kết quả, không tiết lộ secrets
  +-- Thông báo user qua kênh đã xác nhận
  +-- Chuyển tới login lại nếu current session bị revoke
```

Không nhận user ID cần đổi mật khẩu từ request body như dữ liệu đáng tin. Nếu controller có `Authentication authentication`, dùng ID nội bộ tương ứng từ principal, không cho client chọn Alice/Bob bằng `userId` tùy ý. Chức năng quản trị đổi mật khẩu hộ người khác phải là luồng tách biệt, có phân quyền, audit và tránh “đặt password biết được cho admin” không cần thiết.

### 3.2. Vì sao đã đăng nhập vẫn cần xác minh lại?

Browser có session còn hiệu lực không có nghĩa người đang cầm máy là chủ tài khoản. Cookie có thể bị đánh cắp, một browser có thể chưa được khóa hoặc session có thể đã tồn tại lâu. Thao tác đổi password, MFA và recovery email là hành động nhạy cảm nên thường cần **recent authentication** hoặc **step-up**.

Với tài khoản có mật khẩu cục bộ, service có thể kiểm tra:

```java
boolean valid =
    passwordEncoder.matches(
        submittedCurrentPassword, storedPasswordHash
    );
```

Đây là fragment sử dụng Spring Security `PasswordEncoder`. Không so raw password với hash bằng `equals` và không dùng `encoder.encode(raw).equals(stored)` vì salt có thể thay đổi mỗi lần encode.

Nếu user đăng nhập bằng passkey, OIDC hoặc MFA mà không có mật khẩu cục bộ, current password không phải bằng chứng hợp lệ cho mọi tài khoản. Dùng phương pháp xác minh lại phù hợp với phương thức login và mức assurance, đừng bắt mọi account nhập một password không tồn tại.

### 3.3. Password policy, hashing và cập nhật

Sau khi xác minh actor và current credentials:

- Kiểm tra password mới đủ độ dài/chính sách, tránh các password đã lộ; xử lý Unicode và giới hạn độ dài của encoder đúng theo version.
- Gọi `PasswordEncoder.encode(newPassword)` (ví dụ BCrypt/Argon2id/PBKDF2 theo policy) rồi **chỉ lưu hash**.
- Không log password cũ/mới, hash, reset token hay Authorization header.
- Cập nhật password hash và **mốc thu hồi** (`authVersion`, `credentialVersion`, `validAfter`) nhất quán.
- Nếu hai yêu cầu change-password cùng lúc, dùng optimistic lock/CAS/row lock thay vì cho request chậm ghi đè password mới.
- Hủy các outstanding reset tokens/recovery links cũ.
- Ghi audit metadata tối thiểu và thông báo sau commit theo chính sách.

Không mở rộng “đổi mật khẩu” thành việc tự động cấp `ROLE_ADMIN` hoặc bỏ qua authorization trên owner/tenant. Authentication và authorization vẫn là hai tầng riêng.

### 3.4. Giữ hay hủy phiên đang đổi password?

Có hai chính sách hợp lệ tùy threat model:

**A. Thu hồi mọi phiên, cả phiên hiện tại.** Đơn giản để giải thích: đổi mật khẩu thành công, user phải đăng nhập lại; các session/token trước đó hết quyền sử dụng. Khi nghi bị chiếm account, đây thường là lựa chọn phù hợp hơn.

**B. Giữ phiên hiện tại sau re-auth, thu hồi các phiên khác.** Yêu cầu cập nhật session version cho phiên hiện tại, rotate session ID khi policy cần, bảo vệ session fixation và đảm bảo phiên đó có assurance đủ mạnh. Nếu chỉ tăng authVersion mà không cập nhật phiên đang giữ, chính phiên đó sẽ bị từ chối ở request tiếp theo.

Trong bài mẫu phía dưới, chọn **A**: current session bị logout ngay, sessions khác bị từ chối qua `authVersion` ở request kế tiếp.

## 4. Yêu cầu đặt lại mật khẩu khi không nhớ mật khẩu cũ

### 4.1. Reset request không phải login

Người quên mật khẩu chưa có current password để cung cấp. Họ cần chứng minh quyền kiểm soát account qua kênh khôi phục phù hợp. Mẫu request:

```text
POST /reset/request
username hoặc email
  |
  +-- Giới hạn số lần yêu cầu (IP/account/device/risk)
  +-- Không tiết lộ account tồn tại qua response/timing
  +-- Nếu có account: tạo reset challenge ngẫu nhiên
  +-- Lưu verifier của token + purpose + expiry
  +-- Gửi link qua email/side channel đã được xác minh
  |
  v
202 Accepted: "Nếu tài khoản phù hợp tồn tại,
               hướng dẫn sẽ được gửi"
```

Không trả “email này không tồn tại” ở một nhánh và “đã gửi mã” ở nhánh khác. **Phản hồi generic về nội dung là chưa đủ nếu chênh lệch thời gian lộ account tồn tại**; production phải có biện pháp giảm timing enumeration hợp lý, phối hợp rate limit/abuse monitoring thay vì chèn delay cứng gây DoS.

Không dùng header `Host` do client cung cấp để ghép domain link reset; dùng origin/domain chính thức cấu hình sẵn, HTTPS và policy liên quan đến redirect/referrer.

### 4.2. Reset token phải có những thuộc tính gì?

Một reset token tốt cần:

- Sinh bằng **CSPRNG**, ví dụ `SecureRandom`, với entropy cao, ví dụ 32 bytes (~256 bit).
- URL-safe encoding như Base64url; encoding **không tăng entropy**, chỉ giúp đưa token vào link.
- Chỉ dùng cho **password reset**, không được coi là access token chung.
- Gắn với account ID, purpose, time issued, expiry; thời gian sống ngắn theo threat model, ví dụ 15 phút.
- **Một lần sử dụng**, cập nhật consume trạng thái **nguyên tử** với password update.
- Có thể bị revoke khi password thay đổi hoặc user yêu cầu reset link mới.
- Không lưu raw token trong application logs/analytics; ưu tiên lưu digest/verifier ở server.
- Không gửi lại token trong public HTTP response; chỉ gửi qua side channel phù hợp.
- Rate limiting để tránh spam email, đoán code và abuse.

Fragment Java 17 sinh token:

```java
byte[] randomBytes = new byte[32];
new SecureRandom().nextBytes(randomBytes);

String rawToken = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(randomBytes);
```

Token trên là bí mật; không log `rawToken`. Với token ngẫu nhiên 256 bit, lưu một SHA-256 digest của token để tìm verifier trong database là phương án có thể dùng: attacker khó brute force không gian token entropy cao. Điều này **không áp dụng** cho password do con người chọn: lưu `SHA256(password)` một lần là không đủ vì mật khẩu dễ đoán và cần password KDF chậm.

### 4.3. Khi mở link reset

Client cung cấp token và password mới; server kiểm tra:

1. Verifier/token hash có tồn tại đúng mục đích và account?
2. Token còn hạn, chưa bị consume/revoke?
3. Tài khoản còn hợp lệ và recovery policy có cho phép thao tác?
4. Password mới đạt policy và các bước step-up bổ sung nếu yêu cầu?
5. Server có thể **consume một lần** và cập nhật hash/version trong một transaction?
6. Đã invalidated những reset links còn tồn tại, và có kế hoạch revoke sessions/tokens?
7. Thông báo user qua kênh tin cậy sau thành công?

Không tự login user sau reset. OWASP khuyến nghị cho user thực hiện login bình thường sau bước reset, bởi việc cấp session trực tiếp từ reset link làm tăng rủi ro và độ phức tạp.

### 4.4. Atomic consume: chống dùng token hai lần

Nếu code chỉ làm:

```text
if token.used == false:
   update password
   token.used = true
```

thì hai request đồng thời có thể cùng quan sát `used=false` và cùng thành công. Cần transaction, row lock/CAS hoặc một update có điều kiện để chỉ **một request** được consume thành công.

Mô hình SQL minh họa:

```sql
UPDATE password_reset_tokens
SET consumed_at = CURRENT_TIMESTAMP
WHERE token_digest = ?
  AND purpose = 'PASSWORD_RESET'
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP;
```

Chỉ khi **affected rows = 1** mới tiếp tục đổi hash/version **trong cùng transaction**. Nếu update password thất bại, rollback cả việc consume token. Khi nhiều reset links có thể cùng hợp lệ, cần hủy tất cả link khác của cùng account sau một reset thành công.

### 4.5. Sau reset có nên tự logout nạn nhân ở bước request?

Không. Kẻ xấu có thể gửi vô hạn request theo email mà không kiểm soát account; tự revoke chỉ vì `/reset/request` sẽ tạo cơ chế denial of service. **Thu hồi phiên sau bước xác minh reset thành công**, không phải sau một yêu cầu reset chưa có bằng chứng.

## 5. Những phiên cần thu hồi: không phải chỉ có JSESSIONID

| Loại bằng chứng | Cách hoạt động | Biện pháp revoke |
| --- | --- | --- |
| Servlet `HttpSession` | Server giữ SecurityContext, browser mang `JSESSIONID` | Invalidate session server, xóa session từ repository, hoặc check authVersion |
| Remember-me cookie/token | Có thể tạo Authentication mới sau khi phiên hết hạn | Clear cookie hiện tại và revoke persistent tokens ở store |
| Refresh token | Xin access token mới, thường sống lâu | Revoke token/family ở authorization server; xét rotation/reuse detection |
| JWT access token tự chứa | Verify chữ ký, issuer, audience và `exp` | `jti` denylist, user/token version, `validAfter` hoặc chấp nhận hết TTL |
| Opaque access token | Introspection/store trạng thái server | Revoke tại auth server, kiểm soát cache introspection |
| OAuth2/OIDC SSO session | IdP/authorization server và RP có state riêng | Logout/revocation theo provider, có thể cần end-session/backend coordination |
| Reset token/recovery challenge | Token dành cho một tác vụ | Consume, revoke mọi challenge còn hiệu lực theo user/purpose |
| API key dài hạn | Bí mật riêng của thiết bị/tích hợp | Rotate/revoke key ID theo policy riêng; không tự đồng nhất với password |
| Thiết bị/MFA/recovery factor | Authenticator bindings | Thu hồi những yếu tố bị chiếm; verify lại recovery methods |

**Đổi hash không đồng nghĩa revoke JWT.** Một JWT access token đã được ký có thể tiếp tục pass chữ ký/expiration check dù password của user đã đổi. Nếu chỉ revoke refresh token mà resource server không có runtime access-token revocation, access token cũ có thể sống đến hết `exp`.

### 5.1. Khi nghi tài khoản bị chiếm

Tình huống compromise cần xem xét rộng hơn:

- Hủy **tất cả** active HTTP sessions và refresh token families.
- Thu hồi remember-me và reset links/recovery codes còn hiệu lực.
- Kiểm tra access tokens hiện có, khả năng denylist/version check, TTL còn lại.
- Xem lại connected OAuth apps, API keys, thiết bị đã tin cậy, passkeys và MFA factors.
- Rà soát recovery email/phone vừa thay đổi; không tin kênh do attacker mới gắn.
- Audit tác vụ bất thường và bảo vệ dữ liệu đã bị truy cập.
- Thông báo user bằng kênh đáng tin, hướng dẫn re-auth sạch.
- Không quảng cáo “logout mọi nơi ngay lập tức” nếu kiến trúc còn token sống được vài phút do thiếu revoke.

## 6. Logout trong Spring Security: một phiên khác mọi phiên

Spring Security Servlet có logout tích hợp. Khi CSRF bật, `POST /logout` có thể được `LogoutFilter` xử lý: `SecurityContextLogoutHandler` thường invalidate HttpSession, clear authentication/context và các logout handlers khác có thể xử lý remember-me, CSRF và event tùy cấu hình.

Một fragment cấu hình:

```java
@Bean
SecurityFilterChain chain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .logout(Customizer.withDefaults())
        .build();
}
```

Đoạn này cần project, imports và user authentication config; không chạy riêng bằng `javac`. Logout từ browser A không mặc nhiên tìm/cancel sessions B/C trên thiết bị khác.

Khi tự viết controller change-password, một handler có thể hủy session **hiện tại**:

```java
SecurityContextLogoutHandler handler =
    new SecurityContextLogoutHandler();

handler.logout(request, response, authentication);
```

Đây là fragment trong servlet HTTP request. Nó chỉ xử lý context/session của request đó; khi cần remember-me, CSRF logout cleanup và audit, hãy xem toàn bộ Spring Security logout chain hoặc gắn handlers thích hợp. **Chỉ xóa cookie client** nhưng không hủy session server không bảo vệ khỏi attacker đang giữ bản cookie đó.

### 6.1. SessionRegistry/ConcurrentSessionFilter

Spring Security có `SessionRegistry` khi ứng dụng cấu hình theo dõi concurrent sessions. Một pattern đánh dấu những session có trong registry:

```java
for (SessionInformation session :
        registry.getAllSessions(principal, false)) {
    session.expireNow();
}
```

Đây là snippet cần registry đã được đăng ký trong flow, không phải code chạy độc lập. **`expireNow()` đánh dấu session expired**; `ConcurrentSessionFilter` có thể thực hiện xử lý/hủy khi request sau đến, không đảm bảo xóa tức thì mọi session ở storage ngay thời điểm gọi. `SessionRegistryImpl` thường nằm trong memory một JVM và không tự quản lý sessions ở mọi node. Nếu dùng custom principal, thiết kế `equals/hashCode` nhất quán để registry nhận diện đúng user.

### 6.2. Spring Session có shared session repository

Trong ứng dụng dùng Spring Session + backend Redis/JDBC, nếu principal index được cấu hình đúng, có thể tìm session IDs theo principal và xóa ở store chia sẻ:

```java
Map<String, ? extends Session> owned =
    repository.findByPrincipalName(principalName);

for (String sessionId : owned.keySet()) {
    repository.deleteById(sessionId);
}
```

Đây là fragment thuộc Spring Session, cần `FindByIndexNameSessionRepository` và các imports/dependencies tương ứng. Không giả định index principal đã có nếu chưa kiểm tra; cách định danh nên dùng immutable user ID/tenant scope để tránh trùng username. Cache và replication có thể khiến revocation có độ trễ cần đo.

### 6.3. authVersion / sessionVersion

Một kiến trúc khác là lưu **version** khi phiên được phát, rồi đối chiếu với version authoritative trong account:

```text
Account alice: authVersion = 5
Session A: authVersionAtLogin = 5
Session B: authVersionAtLogin = 5

Change/reset password (committed):
  passwordHash = newHash
  authVersion = 6

Request với Session A: 5 != 6 => từ chối/hủy phiên
Request với Session B: 5 != 6 => từ chối/hủy phiên
Login mới: authVersionAtLogin = 6 => được phép
```

Phương pháp này phù hợp multi-node nếu **mọi node đọc nguồn authoritative chung** và kiểm tra ở đúng filter/request boundary. Trong ứng dụng stateless JWT có thể kiểm tra tokenVersion claim ở resource server hoặc sử dụng denylist, nhưng phải đánh giá chi phí DB/cache và failure behavior.

**Spring Security không tự check authVersion nếu bạn chỉ thêm một field vào entity.** Bạn phải tự xây cơ chế lưu/stamp/check version và test.

### 6.4. Race giữa revoke và request đang chạy

Một request đã vượt version filter **trước** khi password reset được commit có thể đang xử lý các thao tác nhạy cảm. Đối với thao tác như chuyển tiền, đổi MFA hoặc xóa dữ liệu, cần recheck version/recent authentication tại service/transaction boundary, không cho rằng filter đầu request chặn tuyệt đối mọi concurrency.

## 7. CSRF và session fixation

Đổi mật khẩu, reset confirm và logout thường là POST. Với cookie-based sessions, browser tự đính kèm cookie cho request cùng phạm vi; kẻ xấu có thể lợi dụng điều đó để gửi request giả mạo. Spring Security bật CSRF protection theo mặc định cho các HTTP methods cần bảo vệ.

**`permitAll()` không đồng nghĩa bỏ CSRF.** Một form reset công khai vẫn có thể cần CSRF token khi được gửi từ browser. Với MockMvc, dùng `.with(csrf())` để kiểm tra flow đi qua lớp CSRF; nếu thiếu, 403 có thể xuất phát từ CSRF chứ không phải thiếu role.

Nếu giữ current session sau đổi password, cân nhắc rotate session ID/renew credentials và chống session fixation. Nếu hủy current session và yêu cầu login lại, framework thường thực hiện session fixation protection ở lần login mới; vẫn phải kiểm tra cấu hình thật và cookie flags (Secure, HttpOnly, SameSite theo ứng dụng).

## 8. Thiết kế database và transaction thực tế

Ví dụ schema (minh họa, không phải migration chạy thẳng):

```sql
accounts (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT,
    normalized_login VARCHAR(255),
    password_hash VARCHAR(255) NOT NULL,
    auth_version BIGINT NOT NULL,
    password_changed_at TIMESTAMP NOT NULL,
    enabled BOOLEAN NOT NULL
);

password_reset_tokens (
    id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL,
    token_digest VARCHAR(64) UNIQUE NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    consumed_at TIMESTAMP NULL
);

refresh_token_families (
    id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL,
    revoked_at TIMESTAMP NULL
);
```

Production cần foreign keys/indexes, uniqueness theo tenant, atomic update với concurrency control, UTC timestamps, retention/cleanup và key/secret management đúng.

### 8.1. Transaction change-password

- Đọc account và verify expected credential version.
- Xác minh current password hoặc completed step-up theo flow.
- Tạo hash mới bằng `PasswordEncoder.encode`.
- Cập nhật `password_hash`, tăng `auth_version` và timestamp.
- Xóa/revoke reset tokens cũ trong cùng transaction nếu cùng DB.
- Lưu outbox event cho external session/token revoke, notification và audit.
- Commit trước khi gọi email/HTTP downstream, hoặc dùng transactional outbox để retry.

Nếu event bus/downstream lỗi, mốc authVersion authoritative đã đổi vẫn khiến phiên cũ bị từ chối khi request đến. Nếu server chỉ phụ thuộc vào một job xóa session nhưng job thất bại, có thể còn phiên cũ chưa bị revoke: cần monitor/retry và chính sách fail closed.

### 8.2. Transaction reset-password

- Không cho reset token hết hạn/đã dùng vào transaction đổi hash.
- Consume token đúng một lần bằng lock hoặc CAS.
- Update hash và authVersion atomically.
- Invalidate những reset tokens còn lại của same user.
- Tạo audit/outbox event.
- Sau commit thông báo user, thu hồi token families/session store theo policy.

Thay đổi password **không tự thay đổi MFA/recovery methods**. Trong sự cố account takeover, kiểm tra những yếu tố đó riêng.

## 9. Ví dụ Spring Boot 3: change/reset có authVersion guard

Bộ demo dùng Spring MVC form login, server-side session, một user `alice` và in-memory account/reset store. Nó minh họa đường kiểm tra **password hiện tại**, reset token **32 bytes**, tiêu thụ token một lần và thu hồi session bằng version. Chỉ dùng cho học tập, **không** copy nguyên service in-memory/reset delivery vào production.

Các file:

```text
src/main/java/example/recovery/
  RecoveryApplication.java
  DemoDelivery.java
  DemoAccounts.java
  SessionVersionFilter.java
  SecurityConfig.java
  RecoveryController.java

src/test/java/example/recovery/
  RecoveryFlowTest.java
```

Trong dự án Gradle Spring Boot 3 với Java 17, dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là phần dependencies, cần plugin/repositories/toolchain tương thích để chạy. Với Maven dùng starters tương ứng và `spring-security-test` test scope.

### 9.1. Main application

```java
package example.recovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RecoveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(RecoveryApplication.class, args);
    }
}
```

Tệp: `src/main/java/example/recovery/RecoveryApplication.java`.

### 9.2. DemoDelivery.java: chỉ dành cho test

```java
package example.recovery;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/** TEST DOUBLE ONLY: lưu raw token trong memory để test lấy được.
 *  Production cần email/outbox adapter bảo mật và KHÔNG expose token.
 */
@Component
public class DemoDelivery {
    private final Map<String, String> latest = new ConcurrentHashMap<>();

    public void deliver(String user, String token) {
        latest.put(user, token);
    }

    public String lastForTest(String user) {
        return latest.get(user);
    }
}
```

Không xây public endpoint `GET /reset/token?user=alice` trả token từ adapter này. Trong sản phẩm, chỉ gửi link qua kênh recovery được xác minh; URL reset phải có origin HTTPS được cấu hình cố định. Hạn chế leakage qua referrer, logging, analytics và browser history.

### 9.3. DemoAccounts.java: nguồn user, token và authVersion

```java
package example.recovery;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Base64;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class DemoAccounts implements UserDetailsService {

    private static final class Account {
        String hash;
        long version;

        Account(String hash, long version) {
            this.hash = hash;
            this.version = version;
        }
    }

    private record Reset(String user, Instant expiresAt) {}

    private final Map<String, Account> accounts = new HashMap<>();
    private final Map<String, Reset> resets = new HashMap<>();
    private final SecureRandom random = new SecureRandom();
    private final Clock clock = Clock.systemUTC();
    private final PasswordEncoder encoder;
    private final DemoDelivery delivery;

    public DemoAccounts(PasswordEncoder encoder, DemoDelivery delivery) {
        this.encoder = encoder;
        this.delivery = delivery;
        accounts.put(
            "alice",
            new Account(encoder.encode("old-demo-password-123"), 1L)
        );
    }

    @Override
    public synchronized UserDetails loadUserByUsername(String user) {
        Account account = accounts.get(user);
        if (account == null) {
            throw new UsernameNotFoundException("User not found");
        }
        // Mỗi lookup trả object mới; tránh làm mất hash trong store.
        return User.withUsername(user)
            .password(account.hash)
            .roles("USER")
            .build();
    }

    public synchronized long version(String user) {
        Account account = accounts.get(user);
        return account == null ? -1 : account.version;
    }

    public synchronized boolean change(
            String user, String current, String next) {
        Account account = accounts.get(user);
        if (account == null || current == null || !validNext(next)) {
            return false;
        }
        if (!encoder.matches(current, account.hash)
                || encoder.matches(next, account.hash)) {
            return false;
        }

        account.hash = encoder.encode(next);
        account.version++;
        resets.entrySet().removeIf(e -> e.getValue().user().equals(user));
        return true;
    }

    public synchronized void requestReset(String user) {
        if (!accounts.containsKey(user)) {
            return; // Controller vẫn trả response chung.
        }
        resets.entrySet().removeIf(e -> e.getValue().user().equals(user));

        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String raw = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);

        resets.put(
            digest(raw),
            new Reset(user, clock.instant().plus(15, ChronoUnit.MINUTES))
        );
        delivery.deliver(user, raw); // TEST ONLY, không expose qua API.
    }

    public synchronized boolean confirm(
            String token, String next) {
        if (token == null || !validNext(next)) {
            return false;
        }

        String id = digest(token);
        Reset grant = resets.get(id);
        if (grant == null || !clock.instant().isBefore(
                grant.expiresAt())) {
            return false;
        }

        Account account = accounts.get(grant.user());
        if (account == null) {
            return false;
        }

        // Demo: lock trong một JVM. Production dùng DB transaction/CAS.
        resets.remove(id);
        account.hash = encoder.encode(next);
        account.version++;
        resets.entrySet().removeIf(
            e -> e.getValue().user().equals(grant.user())
        );
        return true;
    }

    private static boolean validNext(String value) {
        // Demo length-only; production thêm breached-password checks.
        return value != null && value.length() >= 12
            && value.length() <= 128;
    }

    private static String digest(String raw) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(raw.getBytes(StandardCharsets.US_ASCII));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
```

**Đây không phải reset store production:** `synchronized` chỉ có hiệu lực trong một JVM; `HashMap` không bền qua restart, không đảm bảo atomicity multi-node; store cần purge các token hết hạn. Đoạn demo `requestReset` có timing khác nhau cho account tồn tại và không tồn tại, nên production cần giải quyết timing enumeration và rate limiting. `DemoDelivery` giữ raw token trong RAM để test, không thể xem là side channel an toàn. Password policy chỉ kiểm tra độ dài để demo, chưa có MFA/passkeys/breached-password checks.

Reset token dùng SHA-256 vì **raw token có entropy 256 bit từ CSPRNG**. Không suy ra password người dùng có thể lưu SHA-256 một lần: dùng `PasswordEncoder` với password KDF.

### 9.4. SessionVersionFilter.java

```java
package example.recovery;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.web.filter.OncePerRequestFilter;

public class SessionVersionFilter extends OncePerRequestFilter {

    private final DemoAccounts accounts;
    private final SecurityContextLogoutHandler logout =
        new SecurityContextLogoutHandler();

    public SessionVersionFilter(DemoAccounts accounts) {
        this.accounts = accounts;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth != null && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken)) {

            HttpSession session = request.getSession(false);
            Object stamped = session == null
                ? null : session.getAttribute("authVersion");

            long current = accounts.version(auth.getName());

            if (!(stamped instanceof Long v)
                    || v.longValue() != current) {
                logout.logout(request, response, auth);
                response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            }
        }

        chain.doFilter(request, response);
    }
}
```

Vì filter so version, session khác có `Authentication` cũ sẽ bị từ chối trong request sau khi hash/version đổi. Ví dụ demo dùng một form-login chain duy nhất; không gắn nguyên filter lên JWT/stateless flows. Khi DB version tạm không đọc được, production cần fail-closed và kiểm soát availability, không tự cho phiên đi tiếp.

### 9.5. SecurityConfig.java

```java
package example.recovery;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.SecurityContextHolderFilter;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // Cost 10 cho demo; production benchmark/cấu hình mạnh hơn.
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            DemoAccounts accounts) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/reset/request", "/reset/confirm")
                    .permitAll()
                .requestMatchers("/api/me", "/account/change-password")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .successHandler((request, response, authentication) -> {
                    long v = accounts.version(authentication.getName());
                    request.getSession(true).setAttribute(
                        "authVersion", v
                    );
                    response.sendRedirect("/api/me");
                })
            )
            .logout(logout -> logout.logoutUrl("/logout"))
            .addFilterAfter(
                new SessionVersionFilter(accounts),
                SecurityContextHolderFilter.class
            )
            .build();
    }
}
```

Giải thích:

- Spring Security sử dụng `DemoAccounts implements UserDetailsService` cùng `PasswordEncoder` cho login username/password theo cấu hình tiêu chuẩn. Không cần tự viết `AuthenticationManager` cho demo.
- Sau thành công, success handler stamp `authVersion` vào session rồi redirect. Các session trước khi đổi/reset giữ version cũ.
- `SessionVersionFilter` kiểm tra sau bước security context được nạp và từ chối version không khớp.
- Filter được tạo trong chain và **không đánh dấu @Component**, tránh nguy cơ Spring Boot auto-register nó thêm ở ngoài security chain.
- `/reset/request` và `/reset/confirm` permitAll về authorization, **nhưng CSRF mặc định vẫn bật** trên POST.
- Đây là demo form login; muốn dùng stateless JWT cần flow riêng, không dùng JSESSIONID version attr.
- Controller không tạo cookie/session mới sau reset; yêu cầu user login lại.
- Mọi response/notification production phải được chuẩn hóa, hạn chế thông tin nhạy cảm và xử lý request lỗi.

### 9.6. RecoveryController.java

```java
package example.recovery;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RecoveryController {

    private final DemoAccounts accounts;
    private final SecurityContextLogoutHandler logout =
        new SecurityContextLogoutHandler();

    public RecoveryController(DemoAccounts accounts) {
        this.accounts = accounts;
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @PostMapping("/account/change-password")
    public ResponseEntity<Void> change(
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response,
            @RequestParam String currentPassword,
            @RequestParam String newPassword) {

        if (!accounts.change(
                authentication.getName(), currentPassword, newPassword)) {
            return ResponseEntity.badRequest().build();
        }

        logout.logout(request, response, authentication);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/reset/request")
    public ResponseEntity<Void> requestReset(
            @RequestParam String username) {
        accounts.requestReset(username);
        // Không tiết lộ account tồn tại hoặc raw token.
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/reset/confirm")
    public ResponseEntity<Void> confirm(
            @RequestParam String token,
            @RequestParam String newPassword) {

        return accounts.confirm(token, newPassword)
            ? ResponseEntity.noContent().build()
            : ResponseEntity.badRequest().build();
    }
}
```

Current password chỉ đến từ request của phiên đã authenticated; server xác định username từ principal, không lấy `userId` ở body. Khi đổi thành công, handler invalidate current session; sessions khác bị version filter từ chối khi request mới đến. Khi reset thành công, API **không tự login**.

**Lưu ý:** code demo nhận form parameters để dễ test. Production cần validation, password input handling, HTTPS, CSRF UX, rate limits và thiết kế response/error phù hợp. Session handler riêng chưa đủ để thay thế mọi logout handlers của Spring Security (remember-me, CSRF token, event).

### 9.7. Kiểm thử bằng JUnit và MockMvc

Tạo `src/test/java/example/recovery/RecoveryFlowTest.java`:

```java
package example.recovery;

import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class RecoveryFlowTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DemoDelivery delivery;

    private MockHttpSession login(String password) throws Exception {
        MvcResult result = mvc.perform(
            post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", password)
        ).andExpect(status().is3xxRedirection())
         .andExpect(redirectedUrl("/api/me"))
         .andReturn();

        HttpSession session = result.getRequest().getSession(false);
        assertThat(session).isInstanceOf(MockHttpSession.class);
        return (MockHttpSession) session;
    }

    @Test
    void loginSessionCanReadIdentity() throws Exception {
        MockHttpSession session = login("old-demo-password-123");

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void wrongCurrentPasswordDoesNotChangeAccount()
            throws Exception {
        MockHttpSession session = login("old-demo-password-123");

        mvc.perform(post("/account/change-password")
                .session(session)
                .with(csrf())
                .param("currentPassword", "incorrect")
                .param("newPassword", "new-strong-password-987"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void changeRevokesSessionsAndOldPassword()
            throws Exception {
        MockHttpSession a = login("old-demo-password-123");
        MockHttpSession b = login("old-demo-password-123");

        mvc.perform(post("/account/change-password")
                .session(a)
                .with(csrf())
                .param("currentPassword", "old-demo-password-123")
                .param("newPassword", "new-strong-password-987"))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/me").session(b))
            .andExpect(status().isUnauthorized());

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "old-demo-password-123"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));

        MockHttpSession fresh = login("new-strong-password-987");
        mvc.perform(get("/api/me").session(fresh))
            .andExpect(status().isOk());
    }

    @Test
    void changeRequiresCsrf() throws Exception {
        MockHttpSession session = login("old-demo-password-123");

        mvc.perform(post("/account/change-password")
                .session(session)
                .param("currentPassword", "old-demo-password-123")
                .param("newPassword", "new-strong-password-987"))
            .andExpect(status().isForbidden());
    }

    @Test
    void resetRequestResponseIsGeneric() throws Exception {
        mvc.perform(post("/reset/request")
                .with(csrf())
                .param("username", "nobody"))
            .andExpect(status().isAccepted());

        mvc.perform(post("/reset/request")
                .with(csrf())
                .param("username", "alice"))
            .andExpect(status().isAccepted());

        assertThat(delivery.lastForTest("nobody")).isNull();
        assertThat(delivery.lastForTest("alice")).isNotBlank();
    }

    @Test
    void resetTokenOneTimeAndOldSessionRejected()
            throws Exception {
        MockHttpSession old = login("old-demo-password-123");

        mvc.perform(post("/reset/request")
                .with(csrf())
                .param("username", "alice"))
            .andExpect(status().isAccepted());

        String token = delivery.lastForTest("alice");
        assertThat(token).isNotBlank();

        mvc.perform(post("/reset/confirm")
                .with(csrf())
                .param("token", token)
                .param("newPassword", "reset-password-new-123"))
            .andExpect(status().isNoContent());

        mvc.perform(post("/reset/confirm")
                .with(csrf())
                .param("token", token)
                .param("newPassword", "another-long-password"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/api/me").session(old))
            .andExpect(status().isUnauthorized());

        MockHttpSession fresh = login("reset-password-new-123");
        mvc.perform(get("/api/me").session(fresh))
            .andExpect(status().isOk());
    }

    @Test
    void invalidResetTokenCannotChangePassword()
            throws Exception {
        mvc.perform(post("/reset/confirm")
                .with(csrf())
                .param("token", "invalid-token")
                .param("newPassword", "reset-password-new-123"))
            .andExpect(status().isBadRequest());
    }
}
```

Chạy:

```bash
./gradlew test --tests example.recovery.RecoveryFlowTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.recovery.RecoveryFlowTest
```

**Kết quả dự kiến:** bảy phương thức test pass khi toàn bộ project Spring Boot 3 / Spring Security 6.x, dependencies và files được thiết lập đúng. Đây là **kỳ vọng theo code**, chưa phải kết quả Gradle thực thi trong bài viết.

`@DirtiesContext(AFTER_EACH_TEST_METHOD)` tạo trạng thái account/store mới cho từng test vì bộ demo thay password và authVersion. Đây là lựa chọn cho test, không phải chiến lược quản lý account thực tế.

Bộ test xác minh session có thể dùng sau login, current password sai bị từ chối, change làm phiên trên thiết bị khác mất hiệu lực, CSRF, reset response không tiết lộ username trực tiếp, reset token single-use và session cũ bị từ chối. Nó **không chứng minh** transaction multi-node, timing enumeration, email security, expired-token clock, JWT/refresh revocation hay hạ tầng production đã đúng: những phần đó cần integration/security tests bổ sung.

## 10. Java 17 độc lập: phiên cũ bị thu hồi bằng session version

Nếu chưa có Spring Boot, chương trình JDK 17 này minh họa logic epoch rõ ràng. Nó **cố ý dùng password plaintext và token đếm tăng** để tập trung vào state machine: **không copy cách lưu password/tạo token này vào production**. Mã Spring ở phần trước dùng BCrypt và CSPRNG; production cần DB/transaction và thiết kế danh tính.

Tạo file `SessionRevocationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class SessionRevocationDemo {

    record Session(long versionAtLogin) {}

    static final class SystemModel {
        private String password = "old-demo-password";
        private long authVersion = 1;
        private int sequence = 0;

        private final Map<String, Session> sessions =
            new HashMap<>();
        private final Map<String, Boolean> resets =
            new HashMap<>();

        String login(String candidate) {
            if (!password.equals(candidate)) {
                return null;
            }
            String id = "session-" + (++sequence);
            sessions.put(id, new Session(authVersion));
            return id;
        }

        boolean active(String sessionId) {
            Session session = sessions.get(sessionId);
            return session != null
                && session.versionAtLogin() == authVersion;
        }

        boolean change(String current, String next) {
            if (!password.equals(current) || next.length() < 12) {
                return false;
            }
            password = next;
            authVersion++;
            resets.clear();
            return true;
        }

        String requestReset() {
            String token = "demo-token-" + (++sequence);
            resets.put(token, true);
            return token;
        }

        boolean confirmReset(String token, String next) {
            if (next.length() < 12 || resets.remove(token) == null) {
                return false;
            }
            password = next;
            authVersion++;
            resets.clear();
            return true;
        }
    }

    public static void main(String[] args) {
        SystemModel system = new SystemModel();

        String a = system.login("old-demo-password");
        String b = system.login("old-demo-password");

        System.out.println("before.a=" + system.active(a));
        System.out.println("before.b=" + system.active(b));
        System.out.println("change.wrong="
            + system.change("wrong", "changed-password"));
        System.out.println("change.correct="
            + system.change("old-demo-password", "changed-password"));
        System.out.println("afterChange.a=" + system.active(a));
        System.out.println("afterChange.b=" + system.active(b));
        System.out.println("oldLogin="
            + (system.login("old-demo-password") != null));

        String c = system.login("changed-password");
        System.out.println("newSession=" + system.active(c));

        String token = system.requestReset();
        System.out.println("reset.correct="
            + system.confirmReset(token, "reset-password-123"));
        System.out.println("reset.reuse="
            + system.confirmReset(token, "another-password"));
        System.out.println("afterReset.c=" + system.active(c));
        System.out.println("newLogin="
            + (system.login("reset-password-123") != null));
    }
}
```

Biên dịch/chạy bằng JDK 17:

```bash
javac SessionRevocationDemo.java
java SessionRevocationDemo
```

**Stdout chính xác theo logic chương trình:**

```text
before.a=true
before.b=true
change.wrong=false
change.correct=true
afterChange.a=false
afterChange.b=false
oldLogin=false
newSession=true
reset.correct=true
reset.reuse=false
afterReset.c=false
newLogin=true
```

Đọc logic:

1. Khi Alice login, mỗi session giữ `versionAtLogin=1`.
2. Change password đúng tăng `authVersion` lên 2. Sessions cũ vẫn có ID trong Map, nhưng `active` trả false.
3. Mật khẩu cũ không tạo session mới được.
4. Session mới mang version 2.
5. Reset thành công tăng version lên 3, khiến session phiên bản 2 không active.
6. Reset token bị remove khỏi Map nên tái sử dụng thất bại.
7. User đăng nhập bằng mật khẩu vừa reset để có session version 3.

Đây chỉ là **mô hình trạng thái**, không có HTTPS, CSRF, secure cookies, DB hay password hashing. Đặc biệt `demo-token-1` dự đoán được, không phải reset token thật; Spring Boot ví dụ dùng `SecureRandom` và 32 bytes. Không dùng model này để bảo vệ dữ liệu thực.

## 11. Các quyết định vận hành cần làm rõ

### 11.1. Session-based, stateless JWT và SSO

Nếu ứng dụng chỉ dùng Servlet sessions, thu hồi qua session store hoặc authVersion guard có thể phù hợp. Nếu là JWT resource server, cần xem `JwtDecoder`, token claims, expiration và runtime policy. Nếu có refresh tokens ở IdP, revoke ở authorization server. Với SSO, logout một ứng dụng không nhất thiết logout toàn bộ hệ thống; cần flow provider hỗ trợ.

### 11.2. “Đăng xuất tất cả thiết bị ngay” nghĩa gì?

Trên backend, yêu cầu này có thể có độ trễ:

- Registry expired chỉ bị xử lý ở request kế tiếp;
- JWT không check revocation có thể sống đến `exp`;
- Cache có TTL/replication delay;
- Request đã được authorization trước lúc revoke commit có thể tiếp tục;
- Email/outbox token-revocation event có thể bị retry.

Chỉ dùng từ “ngay lập tức” khi cơ chế đảm bảo bằng các guard/đo đạc tương ứng, và định nghĩa độ trễ tối đa chấp nhận được.

### 11.3. Kiểm tra từng loại token

Trước khi code, liệt kê những luồng xác thực ứng dụng thực dùng: form login, Basic, OAuth2, JWT, refresh, remember-me, SSO, API keys. Chọn cơ chế revoke cho **từng** loại và viết integration test với một token/phiên đã được cấp **trước** khi đổi/reset.

### 11.4. Chỉ lưu version trong JVM là chưa đủ

Với nhiều replicas/pods, mỗi instance phải đọc cùng nguồn authoritative hoặc nhận invalidation đồng bộ. `HashMap` trong demo không bảo đảm điều này. Nếu DB không đọc được, hành động nhạy cảm không nên tự cho phiên cũ qua.

## 12. Những anti-patterns phổ biến

**1. Chỉ update hash rồi kết luận logout-all.** Cũ còn session/token độc lập. Thêm server-side revoke/version guard.

**2. Nhận userId từ JSON body để đổi password.** Dễ tạo BOLA/IDOR. Lấy actor từ principal và kiểm tra quyền.

**3. Yêu cầu reset xong là logout user.** Bất kỳ người lạ biết email cũng gây được DoS. Chỉ thay trạng thái sau recovery verification.

**4. Trả raw reset token trong response API công khai.** Attacker có thể tự đổi password. Dùng side channel đã xác nhận.

**5. Token đặt lại có thể đoán được.** Timestamp, counter, hash(email) không đủ. Dùng `SecureRandom` đủ entropy.

**6. Không có expiry/single-use.** Link cũ có thể bị dùng lại; consume token atomically.

**7. Hai request cùng token đều được chấp nhận.** Kiểm tra và consume không nguyên tử. Dùng DB transaction/CAS.

**8. Không invalidate reset links khác.** Link cũ có thể ghi đè password vừa reset.

**9. Xóa browser cookie nhưng session server còn.** Bản cookie attacker giữ vẫn hoạt động; phải hủy server-side state.

**10. Dùng SessionRegistry nhưng sessions không được đăng ký hoặc app nhiều JVM.** Code trả rỗng, tưởng đã revoke. Kiểm tra cấu hình và storage.

**11. Revoke refresh token nhưng bỏ qua access JWT còn hạn.** Mô tả rõ TTL/revocation check của access tokens.

**12. Tự rotate signing key để logout một user.** Có thể ảnh hưởng mọi account; dùng per-user token family/version/jti.

**13. Bỏ CSRF trên change/reset vì permitAll.** Authorization permitAll không thay CSRF. Kiểm tra browser/cookie threat model.

**14. Để reset tự tạo authenticated session.** Tăng nguy cơ session fixation/assurance bypass. Yêu cầu login lại.

**15. Không kiểm tra timing enumeration.** Response generic nhưng account tồn tại xử lý khác rõ ràng. Cần kiểm soát timing/rate limit.

**16. Không recheck phiên ở transaction boundary.** In-flight request có thể còn làm side effect sau revoke.

**17. Không review MFA/recovery factors sau compromise.** Attacker có thể giữ kênh khôi phục; password mới không khắc phục.

**18. Quên test login cũ sau reset.** Test phải xác nhận password cũ bị từ chối, token dùng lại thất bại, phiên cũ hết hiệu lực và phiên mới hợp lệ.

**19. Không phân biệt reset token với access token.** Reset token chỉ cho một mục đích, không cho phép đọc API tùy ý.

**20. Log reset link hoặc gửi link qua domain do Host header điều khiển.** Có thể lộ token hoặc dẫn người dùng tới miền attacker. Cố định trusted origin và hạn chế referrer/logs.

## 13. Checklist triển khai

**Change password**

- [ ] Endpoint chỉ nhận actor từ Authentication/immutable user ID đã xác minh.
- [ ] Có current password hoặc step-up phù hợp; kiểm soát lần thử.
- [ ] Password mới đạt policy, sử dụng `PasswordEncoder.encode` và không log secrets.
- [ ] Update hash + authVersion theo transaction/version control.
- [ ] Invalidate reset links cũ và đưa ra policy giữ/hủy current session.
- [ ] Thu hồi other sessions/refresh/remember-me theo phạm vi đã công bố.
- [ ] CSRF, TLS, cookie flags và session fixation được kiểm tra.
- [ ] Có notification/audit an toàn và cơ chế retry nếu revoke store lỗi.

**Reset password**

- [ ] Request trả generic response, không tiết lộ account qua content/timing.
- [ ] Token sinh từ CSPRNG, entropy đủ cao, có purpose/account/expiry/single-use.
- [ ] Raw token không trả public, không log; gửi qua side channel đáng tin.
- [ ] Không tự thay password hoặc revoke session ngay ở bước request.
- [ ] Confirm token atomically với password update/version bump.
- [ ] Invalidate các reset tokens cũ và tất cả sessions theo policy.
- [ ] Không tự login sau reset; chuyển qua authentication flow chuẩn.
- [ ] Có rate limiting, email flood protection, audit và test concurrency.

**Session/token revocation**

- [ ] Xác định HTTP sessions, remember-me, refresh, JWT, opaque, SSO, API key.
- [ ] Session registry/index hoạt động với custom principal, multi-node và tenant.
- [ ] Nếu dùng version, request nào cũng kiểm tra version authoritative.
- [ ] Access JWT có TTL/denylist/version check rõ ràng.
- [ ] Revoke refresh tokens/families, không chỉ xóa cookie/browser storage.
- [ ] Dùng immutable user ID, tránh revoke nhầm tài khoản khác tenant.
- [ ] Test sessions cũ, token cũ, request đã chạy và failure path hạ tầng.
- [ ] UI không hứa độ trễ thu hồi mạnh hơn cơ chế thật.

## 14. Câu hỏi tự kiểm tra

**1.** Tại sao đổi `password_hash` không tự invalid HTTP sessions đã login?

**2.** Change password khác reset password ở bằng chứng nào?

**3.** Vì sao request reset chỉ nhận email không được tự logout nạn nhân?

**4.** Vì sao reset token cần CSPRNG, expiry và single-use?

**5.** Có thể lưu SHA-256 digest của reset token ngẫu nhiên 256-bit nhưng không lưu SHA256(password) của người dùng vì sao?

**6.** Vì sao `permitAll()` vẫn có thể bị CSRF 403?

**7.** `SecurityContextLogoutHandler` giải quyết phiên nào?

**8.** `SessionInformation.expireNow()` có xóa ngay các sessions trên nhiều node không?

**9.** Ý tưởng authVersion hoạt động thế nào?

**10.** JWT access token còn hạn có tự không hợp lệ khi password đổi không?

**11.** Vì sao revoke refresh token rất quan trọng?

**12.** Vì sao reset thành công thường không tự cấp login session?

**13.** Khi account bị chiếm, vì sao phải review recovery email và MFA factors?

**14.** Hai request cùng reset token cần được xử lý ra sao?

**15.** Nếu resource server không check tokenVersion/denylist, UI có thể hứa logout JWT ngay không?

**16.** Vì sao cần test bằng session được tạo *trước* lúc change/reset?

**Đáp án gợi ý**

1. Vì session SecurityContext có vòng đời khác password hash và không verify raw password mỗi request.
2. Change có principal đã xác minh và re-auth; reset dùng recovery token/side channel.
3. Vì email không phải credential, kẻ xấu có thể gây DoS/logout cho người khác.
4. Để token không bị đoán, không tồn tại quá lâu, không dùng lại.
5. Token high entropy có không gian đoán cực lớn; password con người thường entropy thấp và cần KDF chậm.
6. Vì CSRF filter bảo vệ state-changing requests độc lập với permitAll authorization.
7. Current request/context/session, không tự revoke mọi thiết bị.
8. Không mặc định; có thể chỉ đánh dấu expired, cần registry/filter/shared storage đúng.
9. Session lưu version khi login; khi account tăng version, phiên cũ bị từ chối.
10. Không, trừ khi resource server có revocation guard hoặc token hết hạn.
11. Vì refresh token có thể tiếp tục mint access tokens mới.
12. OWASP khuyên quay về login bình thường, giảm complexity/assurance risk.
13. Attacker có thể đã thêm/chiếm các factor và kênh khôi phục.
14. Chỉ một request được consume thành công trong transaction/CAS.
15. Không. Phải nêu rõ giới hạn tới `exp` hoặc triển khai revoke runtime.
16. Chỉ test phiên mới không chứng minh phiên cũ đã bị revoke.

## 15. Tài liệu tham khảo chính thức

- [OWASP – Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [Spring Security 6.5 – Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 – Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 – CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security – SecurityContextLogoutHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html)
- [Spring Security – SessionInformation API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/SessionInformation.html)
- [Spring Session – FindByIndexNameSessionRepository API](https://docs.spring.io/spring-session/docs/current/api/org/springframework/session/FindByIndexNameSessionRepository.html)
- [NIST SP 800-63B – Authentication và account recovery](https://pages.nist.gov/800-63-4/sp800-63b.html)
