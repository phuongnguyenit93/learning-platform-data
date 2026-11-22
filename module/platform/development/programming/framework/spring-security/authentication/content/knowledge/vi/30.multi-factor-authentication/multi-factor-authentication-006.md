# Thời điểm xác thực và thời hạn chấp nhận một yếu tố

## 1. Tại sao xác thực thành công không có nghĩa yếu tố luôn được chấp nhận?

Trong xác thực nhiều yếu tố (**MFA – multi-factor authentication**), việc người dùng từng nhập mật khẩu, xác minh TOTP hoặc dùng khóa bảo mật chỉ chứng minh **một sự kiện xác thực tại một thời điểm**. Hệ thống còn cần xác định: **bằng chứng đó được chấp nhận trong bao lâu, với phiên nào, cho loại hành động nào, và khi nào phải thực hiện step-up/re-authentication**.

Ví dụ:

~~~text
08:00   Đăng nhập bằng password
08:02   Xác minh TOTP thành công
08:05   Yêu cầu duyệt giao dịch ngân hàng
08:07   Người dùng vẫn có session hợp lệ
08:20   Yêu cầu thay tài khoản thụ hưởng
~~~

Nếu chính sách của hành động duyệt giao dịch yêu cầu **TOTP trong vòng 5 phút**, bằng chứng từ 08:02 chỉ được chấp nhận **trước 08:07** theo quy tắc thời gian nửa mở. Lúc 08:20 session có thể còn hiệu lực để xem trang thông thường, nhưng giao dịch nhạy cảm phải đòi bằng chứng mới hoặc một phương thức đủ mạnh đáp ứng chính sách.

Các mốc thời gian **không thể thay thế** nhau:

1. **Challenge validity:** mã OTP, nonce hoặc challenge được phép nộp để verifier kiểm tra đến lúc nào?
2. **Factor freshness:** yếu tố đã được verifier xác nhận lần cuối lúc nào; tuổi của bằng chứng đã quá hạn chính sách chưa?
3. **Session lifetime:** phiên ứng dụng còn tồn tại đến lúc nào theo idle/absolute timeout?
4. **Token lifetime:** JWT/OIDC/access token còn được chấp nhận theo `exp`, `nbf` và các validator hay không?
5. **Step-up privilege lifetime:** trạng thái quyền tăng cường sau MFA có thể được giữ bao lâu và cho những hành động nào?

**Thông điệp chính:** hạn một OTP để *nộp mã* khác với hạn *tin việc một yếu tố đã được xác minh*, và cả hai đều khác với hạn của phiên đăng nhập.

## 2. Định nghĩa yếu tố, phương thức và kết quả kiểm chứng

MFA được xây từ các loại yếu tố độc lập như:

- **Knowledge:** thứ người dùng biết, ví dụ password/PIN.
- **Possession:** thứ người dùng sở hữu, ví dụ thiết bị chứa TOTP secret, security key hoặc authenticator.
- **Inherence:** đặc điểm sinh trắc học, thường tham gia xác thực tại thiết bị.

**Hai bước không mặc nhiên là hai yếu tố.** Password và câu hỏi bí mật đều là knowledge, còn hai OTP trên cùng một kênh có thể không tạo được mức độc lập mong muốn. Một passkey/WebAuthn có **user verification (UV)** có thể cung cấp nhiều đặc tính xác thực theo profile, nhưng phải đánh giá authenticator và assurance contract, không kết luận chỉ vì UI hiển thị “Passkey thành công”.

Phân biệt:

| Khái niệm | Ý nghĩa | Thông tin thời gian |
|---|---|---|
| **Challenge** | Yêu cầu xác minh có ID, user/session, purpose, attempts và dữ liệu verifier. | `issuedAt`, `expiresAt`, `consumedAt`. |
| **Accepted factor event** | Verifier đã chấp nhận đúng một phương thức/yếu tố và ghi proof có provenance. | `verifiedAt`, `invalidatedAt`. |
| **Authentication session** | Principal và ngữ cảnh đã xác thực được duy trì qua request. | `createdAt`, `lastAccessedAt`, `idleExpiresAt`, `absoluteExpiresAt`. |
| **Authorization decision** | Có được phép thao tác trên tài nguyên này hay không? | Được đánh giá ở thời điểm hành động, dựa trên freshness hiện tại. |

Chỉ ghi `verifiedAt` **sau khi** server kiểm tra thành công OTP, chữ ký WebAuthn hoặc yếu tố tương ứng; không ghi khi vừa phát hành challenge, gửi SMS, mở form hay client tự trả `mfa=true`.

## 3. Hai loại “thời hạn” thường bị nhầm

### 3.1. Thời hạn nộp challenge

Một mã được gửi lúc 09:00 có thể được server quy định hết hạn lúc 09:05:

~~~text
issuedAt    = 2026-11-06T09:00:00Z
expiresAt   = 2026-11-06T09:05:00Z
maxAttempts = 5
usedAt      = NULL

09:04:59.999   Có thể verify nếu chưa dùng, chưa vượt attempts.
09:05:00.000   Không được verify; đã đến deadline.
~~~

5 phút chỉ là **ví dụ policy**, không phải TTL bắt buộc cho mọi OTP. Đúng mã sau khi hết hạn vẫn phải bị từ chối. Việc challenge expired không có nghĩa một verified-factor event được tạo từ challenge ấy trước đó bị mất hiệu lực ngay lập tức; điều đó do freshness policy riêng quyết định.

### 3.2. Thời hạn tin factor đã được xác minh

Nếu OTP được chấp nhận lúc 09:04:30, policy của hành động yêu cầu **factor age dưới 3 phút**:

~~~text
verifiedAt        = 09:04:30
maxFactorAge      = 00:03:00
freshUntil        = 09:07:30  (exclusive)

Action at 09:07:29.999  -> có thể còn đủ mới
Action at 09:07:30.000  -> không còn đủ mới
~~~

Vì vậy **challenge TTL bắt đầu từ lúc phát hành**, còn **factor freshness bắt đầu từ lúc verifier xác nhận thành công**. Session timeouts lại có điểm bắt đầu và quy tắc gia hạn riêng.

Không cập nhật `verifiedAt` khi refresh browser, tạo access token mới bằng refresh token, tải lại `SecurityContext`, gia hạn idle timeout, mở trang nhạy cảm hoặc nhấn một nút không xác thực. Nếu làm vậy sẽ biến hoạt động bình thường thành chứng minh MFA mới mà không có authenticator thực sự.

## 4. Công thức chính xác và ranh giới tin cậy

Giả sử server giữ một event:

~~~json
{
  "proofId": "pf-104",
  "subjectId": "usr-1042",
  "sessionId": "sid-A",
  "factorKind": "POSSESSION",
  "method": "TOTP",
  "verifiedAt": "2026-11-06T08:02:00Z",
  "invalidatedAt": null,
  "purpose": "PAYMENT_APPROVAL",
  "issuer": "trusted-internal-verifier"
}
~~~

Đây là **server-side record**, không phải JSON client được quyền gửi để tự đánh dấu MFA hoàn thành. Một quy tắc tối thiểu:

~~~text
accept =
  proof exists and was issued by a trusted verifier
  AND proof.subjectId == currentAuthenticatedUserId
  AND proof.sessionId == currentSessionId
  AND proof.factorKind / method / assurance satisfy action policy
  AND proof.purpose/action binding satisfy current action
  AND proof.verifiedAt <= trustedServerNow
  AND trustedServerNow < proof.verifiedAt + policy.maxFactorAge
  AND proof has not been invalidated/revoked/consumed for this action
  AND session/account and all application permissions are still valid
~~~

Với thời gian tuyệt đối nên dùng `Instant` UTC; có thể lưu mốc ở database theo UTC và tiêm `Clock` cho test. Không lấy `now`, `verifiedAt` hay `sessionId` do browser tùy ý đưa vào làm căn cứ bảo mật. Một event “đến từ tương lai” phải bị chặn hoặc xử lý theo chính sách đồng bộ đồng hồ rất hạn chế; **không chấp nhận vô điều kiện**.

Một nút quan trọng: **“MFA fresh” không tự cấp quyền nghiệp vụ**. User không có `PAYMENT_APPROVE` vẫn không duyệt được giao dịch cho dù vừa xác minh TOTP thành công. Ngược lại, user có role nhưng proof quá tuổi vẫn cần step-up.

## 5. TOTP: bước 30 giây và thời hạn proof là hai khái niệm

TOTP theo RFC 6238 sử dụng thời gian để tính counter và giá trị OTP. Một cấu hình phổ biến có **time step 30 giây**:

~~~text
counter = floor((unixTimeSeconds - T0) / stepSeconds)

Example policy:
  stepSeconds = 30
  tolerated steps = previous / current / next (nếu được cấu hình)
~~~

Cửa sổ ±1 step có thể hỗ trợ lệch đồng hồ, nhưng tăng số counter được thử; thời gian thực một mã được chấp nhận còn phụ thuộc **vị trí trong step, clock skew và policy**, không thể kết luận “chính xác 30 giây” ở mọi triển khai.

Khi một TOTP khớp:

1. Verifier xác định authenticator/user/challenge và counter thích hợp.
2. Kiểm tra attempts, trạng thái tài khoản, clock/skew policy.
3. Chống replay: một OTP/time step đã được chấp nhận không được dùng lại như lần xác minh độc lập nếu policy yêu cầu one-time (quản lý trạng thái theo authenticator/counter).
4. Ghi thành công **nguyên tử** để tránh hai request đồng thời cùng được chấp nhận.
5. Tạo trusted event với `verifiedAt` là thời điểm server chấp nhận OTP.
6. Áp action freshness dựa trên event, **không** bằng cách tiếp tục chấp nhận mã OTP cũ.

Ví dụ, người dùng nhập một TOTP thành công lúc 08:02:00. Mã số ấy có thể không còn dùng được lần hai ngay cả lúc 08:02:05; nhưng action policy vẫn có thể công nhận **proof** từ 08:02 đến trước 08:07. Server không cần cho client trình lại OTP để kiểm tra một action trong khoảng proof còn hiệu lực.

**TOTP seed cần được bảo vệ để verifier tính lại mã**, không giống token ngẫu nhiên mà server có thể chỉ lưu hash. Một HMAC/hash một chiều của seed không đủ để tính lại TOTP cho các time step mới. Seed cần KMS/secret manager hoặc cơ chế quản lý key phù hợp, không log hoặc gửi lộ qua telemetry.

TOTP sáu chữ số có không gian mã hữu hạn, nên phải hạn chế đoán online theo user/authenticator/challenge, bảo vệ khỏi brute force và replay. Không nâng cửa sổ clock tolerance quá lớn chỉ để “giảm lỗi” mà không đánh giá rủi ro.

## 6. Email/SMS OTP, HOTP và push approval

Không phải mã OTP nào cũng sinh theo bước TOTP. Với mã phát hành theo challenge (email/SMS), server thường lưu:

~~~text
challengeId       = ch-811
subjectId         = usr-1042
sessionId         = sid-A
purpose           = CHANGE_PAYOUT
issuedAt          = 10:00:00
expiresAt         = 10:03:00
attemptCount      = 0
maxAttempts       = 5
consumedAt        = NULL
~~~

Mã được so sánh với verifier phù hợp, còn hạn, đúng session/purpose và chưa dùng. Nếu code là PIN ngắn, cần rate limit nghiêm ngặt, chống online/offline guessing và giữ verifier bảo mật; không áp dụng giả định entropy 256 bit như với link token dài.

**Email OTP không tự tương đương một out-of-band authenticator đạt assurance cao**: mailbox có thể bị kiểm soát qua cùng một phiên/mật khẩu, và tiêu chuẩn assurance có giới hạn đối với email out-of-band. SMS/voice có nguy cơ SIM swap/chuyển số; mức tin cậy của phương thức tùy profile và policy. Đừng chỉ ghi `mfa=true` rồi bỏ qua chất lượng phương thức.

**HOTP** dựa trên bộ đếm sự kiện thay vì thời gian. Challenge/OTP vẫn cần attempt limit, counter synchronization và chống replay; `verifiedAt` vẫn là timestamp **server xác minh thành công** và không được đánh đồng với counter.

**Push approval** chỉ tạo proof khi server xác minh được response đã bảo vệ từ authenticator, challenge còn hiệu lực, khớp user/device và user đã xác nhận. Việc gửi push notification không phải authentication event. Cần hạn chế MFA fatigue, request flooding, number matching/transaction confirmation theo khả năng sản phẩm và tránh cấp quyền khi một notification được “seen” nhưng chưa approved.

## 7. WebAuthn/FIDO2: challenge expiry khác thời điểm xác thực

WebAuthn sử dụng challenge ngẫu nhiên và chữ ký từ credential private key ở authenticator, đồng thời kiểm tra origin, RP ID, challenge, user presence (UP), user verification (UV) khi cần và các điều kiện đăng ký/assurance.

~~~text
Server issues challenge with expiry
            |
Browser + authenticator signs an assertion
            |
Server validates challenge + origin + RP ID hash
            + signature + UP/UV + credential association
            |
Atomically marks challenge consumed
            |
Creates verified-factor event (verifiedAt = server time)
            |
Action may use proof until freshness deadline
~~~

Challenge hết hạn thì assertion không được dùng, nhưng sau khi xác minh thành công, ứng dụng có thể lưu proof để xét step-up trong thời hạn policy. Assertion **không nên được replay** và claim `verifiedAt` không đến từ client.

WebAuthn có thể chống phishing tốt hơn các mã OTP chuyển qua trang web giả, nhưng cách đánh giá yếu tố và assurance phụ thuộc authenticator, UV, credential registration và chính sách. Một passkey có UV không có nghĩa tự động mọi giao dịch đều đã được người dùng duyệt có ràng buộc nội dung.

Nếu muốn **transaction binding**, phải có thiết kế chứng minh xác nhận phù hợp dữ liệu giao dịch. Chỉ hiển thị số tiền ở UI mà không ràng buộc cryptographic proof với dữ liệu đã xác nhận không tự tạo transaction signing.

## 8. Những thời điểm không được dùng làm `verifiedAt`

| Timestamp | Nên hiểu là | Tại sao không chứng minh factor mới? |
|---|---|---|
| `session.createdAt` | Lúc phiên được tạo. | Có thể tạo phiên trước/sau khi step-up. |
| `session.lastAccessedAt` | Lần tương tác session gần đây. | Click/tải trang không phải xác minh yếu tố. |
| `accessToken.iat` | Access token vừa được phát hành. | Có thể do refresh token, không phải login/MFA mới. |
| `accessToken.exp` | Token hết hạn vào mốc đó. | Không bảo đảm factor được xác minh gần đây. |
| `challenge.issuedAt` | OTP/challenge được tạo. | Chưa có bằng chứng user đã vượt qua kiểm tra. |
| `message.sentAt` | Email/SMS đã được gửi/queued. | Gửi thành công không là verify thành công. |
| `page.visitedAt` | User đã mở trang/form. | Có thể do bot/link scanner. |
| `rememberDeviceAt` | Thiết bị từng được đánh dấu tin cậy. | Không phải yếu tố vừa được chứng minh. |
| `auth_time` (OIDC) | Sự kiện xác thực user tại IdP theo ngữ nghĩa provider. | Không tự chứa giờ gần nhất của **từng yếu tố** cụ thể. |

Nếu ứng dụng chỉ có boolean `mfaVerified` mà không có timestamp, factor method, session binding và invalidation, khó xây một policy freshness chính xác. Một cookie `remember-me` hoặc token có claim `mfa=true` **không được tự động kéo dài proof vô thời hạn**.

## 9. Session timeout và MFA freshness cùng tồn tại

Session có thể sử dụng **idle timeout** và **absolute timeout**:

- Idle timeout hết hạn khi không có hoạt động được chấp nhận trong một thời gian.
- Absolute timeout kết thúc phiên sau một khoảng tối đa từ thời điểm bắt đầu, dù user liên tục thao tác.

MFA proof lại có max age riêng. Ví dụ:

~~~text
Session login:                 08:00
Session idle timeout:          30 min (có thể gia hạn theo activity)
Session absolute timeout:       8 hours
Password verifiedAt:           08:00
TOTP verifiedAt:               08:02
Freshness for payment:          5 min
Payment proof deadline:        08:07 (exclusive)

At 08:20, normal session may remain active
but TOTP proof is stale for sensitive payment.
~~~

Trong Spring Security, `Authentication.isAuthenticated()` là trạng thái object xác thực, không phải phép kiểm tra “TOTP trong 5 phút”. `SecurityContext` có thể được phục hồi qua session sau nhiều request mà không có verifier event mới. Không lấy `HttpSession.getLastAccessedTime()` để thay thời điểm xác minh factor.

**Session renewal** hoặc access-token refresh có thể kéo dài kỹ thuật duy trì phiên nhưng không “cấp lại” MFA theo default. Nếu hệ thống cần assurance sau step-up, phải lưu một proof riêng có TTL/invalidation, hoặc yêu cầu xác thực lại ở thời điểm phù hợp.

Khi logout, account disabled hoặc session revoked, proof bound session phải mất hiệu lực theo policy ngay cả khi `verifiedAt + maxAge` chưa tới deadline.

## 10. OIDC: `auth_time`, `max_age`, `acr` và `amr`

Ở mô hình **SSO qua OpenID Connect**, ứng dụng không trực tiếp kiểm chứng password/TOTP của người dùng; OpenID Provider (IdP) làm việc đó. Ứng dụng nhận các claim *đã xác thực bằng giao thức và chữ ký hợp lệ*.

Ví dụ nội dung claim minh họa:

~~~json
{
  "iss": "https://idp.example.test",
  "sub": "subject-18",
  "aud": "finance-web",
  "iat": 1793944800,
  "exp": 1793948400,
  "auth_time": 1793941200,
  "amr": ["pwd", "otp"],
  "acr": "urn:example:assurance:mfa"
}
~~~

Đây **không phải ID Token thực đã ký**. Trước khi dùng các giá trị phải xác minh issuer, audience, signature, expiry, nonce/state/correlation và các yêu cầu của luồng OIDC.

| Claim | Có thể biểu thị | Không tự chứng minh |
|---|---|---|
| `iat` | Thời điểm phát hành ID Token. | OTP/password vừa được nhập vào lúc phát hành. |
| `exp` | Token không còn hợp lệ sau deadline. | Proof MFA còn đủ mới tới deadline token. |
| `auth_time` | Thời điểm authentication event ở IdP theo OIDC. | Mốc thời gian **từng phương thức** đã dùng. |
| `amr` | Thông tin phương thức IdP xác nhận theo contract. | OTP được thực hiện **trong 5 phút gần nhất**. |
| `acr` | Lớp/mức authentication context do IdP xác nhận. | Mỗi issuer dùng cùng mã `acr` với cùng semantics. |

### `max_age` và yêu cầu đăng nhập lại

OIDC client có thể yêu cầu `max_age=300` để yêu cầu IdP phản ánh rằng authentication time của end-user không quá 5 phút theo ngữ nghĩa flow; kết quả cần được kiểm tra qua `auth_time`. Khi muốn mức đảm bảo cụ thể, sử dụng các cơ chế như `acr_values`/`acr`/`amr` theo khả năng và hợp đồng với IdP.

**Nhưng `max_age` một mình không chứng minh TOTP đã được xác minh riêng trong 5 phút.** Một IdP có thể xác thực password với authentication time mới mà không có assurance cần thiết. Ngược lại, refresh token có `iat` mới không nhất thiết yêu cầu user nhập lại gì.

`prompt=login` có thể yêu cầu IdP hiển thị/tiến hành xác thực lại theo protocol, nhưng client vẫn phải **kiểm tra response** và các tín hiệu assurance. Không tin một chuỗi `acr=mfa` nếu chưa xác định từ IdP cụ thể nó có nghĩa là gì, và không lấy claim do JavaScript frontend tự tạo làm bằng chứng.

Nếu chính sách cần recency của một factor rất cụ thể (như TOTP hoặc phishing-resistant passkey), IdP phải cung cấp **contract xác thực lại và thời điểm đúng** hoặc ứng dụng phải có một local step-up verifier. Không đoán dựa trên token issue time.

## 11. SAML và các hệ thống liên kết danh tính khác

Trong SAML 2.0, một assertion có thể có `AuthnStatement` với `AuthnInstant` và `AuthnContext`. Ứng dụng là Service Provider phải xác minh chữ ký, issuer, audience, recipient, thời gian, correlation và các điều kiện theo profile trước khi tin nó.

**`AuthnInstant` không tự đồng nhất với thời điểm một OTP riêng được xác minh.** Nếu cần xác thực lại hay một mức assurance, phải đàm phán chính sách với IdP và kiểm tra authentication context được trả về. Đừng biến “SAML assertion vẫn còn hiệu lực” thành “MFA vừa hoàn thành”.

Khi một federation gateway chuyển Kerberos/LDAP login thành OIDC/SAML assertion, ứng dụng vẫn chỉ được tin bằng chứng do gateway/IdP phát hành **cho đúng audience** và với semantics được xác nhận. Token hoặc HTTP header mang timestamp không có provenance đáng tin **không đủ** để nâng quyền.

## 12. Step-up authentication trước hành động nhạy cảm

**Step-up** là bước yêu cầu một bằng chứng đủ mới/đủ mạnh khi user **đã có session** nhưng muốn thực hiện thao tác có rủi ro cao hơn.

~~~text
User authenticated, opens /payments/approve
             |
             v
Authorization gate checks:
  - authenticated principal/account active?
  - PAYMENT_APPROVE authority?
  - correct tenant/resource?
  - factor proof is trusted + fresh for this action?
             |
    +--------+---------+
    |                  |
    v                  v
  ALLOW              NEED STEP-UP
    |                  |
    |          issue purpose-bound challenge
    |                  |
    |          user solves factor
    |                  |
    |          verifier checks and consumes atomically
    |                  |
    |          store trusted verifiedAt event
    |                  |
    +<------ retry/confirm action
             |
          recheck authorization
             |
          commit business action
~~~

Một policy cụ thể có thể yêu cầu possession factor trong 5 phút, hoặc một WebAuthn ceremony gắn transaction. Thời hạn ngắn hơn session cho phép user tiếp tục đọc dữ liệu thông thường nhưng buộc step-up khi approve/change MFA.

Không tự nâng role vĩnh viễn thành `ROLE_ADMIN` khi bước MFA thành công. Step-up **không thay authorization**; nó bổ sung một điều kiện. Với hành động giá trị cao, kết quả proof cần có `purpose` hoặc `actionId`, và có thể chỉ được dùng **một lần** cho chính transaction ấy thay vì mọi action trong khoảng 5 phút.

### Chống bypass khi user mở trang lâu

Check freshness lúc render form là chưa đủ:

~~~text
08:04 open payment form -> proof fresh
08:23 submit approval   -> proof no longer fresh
~~~

Ứng dụng phải **đánh giá lại gần thời điểm side effect/commit**. Nếu việc duyệt được đưa vào queue, cần gắn proof/authorization grant theo operation và policy cho worker thực thi, không biến quyết định cũ trên frontend thành quyền không hết hạn.

## 13. Dữ liệu sự kiện MFA nên ghi và những gì phải bảo vệ

Một proof đáng tin có thể chứa:

~~~json
{
  "proofId": "pf-5001",
  "subjectId": "usr-1042",
  "sessionId": "sid-A",
  "factorKind": "POSSESSION",
  "method": "TOTP",
  "authenticatorId": "auth-7",
  "verifiedAt": "2026-11-06T08:02:00Z",
  "invalidatedAt": null,
  "purpose": "PAYMENT_APPROVAL",
  "actionId": null,
  "assurancePolicyVersion": "payment-mfa-v2",
  "issuer": "internal-verifier"
}
~~~

Đây là record server-side; browser không được tự điền `verifiedAt`, `factorKind`, `issuer` hay `userId` để nâng quyền. Cần lưu thông tin đủ để kiểm tra:

- **Provenance:** verifier nào tạo event; đã validate authenticator theo policy hay chưa.
- **Identity binding:** đúng principal/account/tenant hiện tại; không map theo email tùy ý.
- **Session binding:** proof ở session A không tự dùng tại session B nếu chính sách yêu cầu.
- **Factor strength:** password, TOTP, SMS, phishing-resistant WebAuthn có mức rủi ro khác nhau.
- **Purpose/transaction binding:** recovery proof không tự thay cho payment-approval proof.
- **Timing:** verifiedAt, expiry policy, invalidation/cancellation và các điểm thời gian tin cậy.
- **Lifecycle:** nếu authenticator bị xóa, account khóa hoặc security incident xảy ra, proof có thể bị vô hiệu trước deadline.

Không lưu raw OTP, TOTP seed, private key, access token, session cookie hay raw WebAuthn challenge data vô hạn trong access logs. Audit có thể ghi proof ID không phải credential, phương thức, user ID theo privacy policy và kết quả allow/deny.

## 14. Java 17 độc lập: kiểm tra timestamp và deadline chính xác

Ví dụ Java thuần sau **chạy được trên JDK 17+** mà không dùng Spring. Nó chỉ mô phỏng **đánh giá freshness của các proof đã được verifier tin cậy tạo trước đó**; không xác minh OTP, chữ ký WebAuthn, không quản lý HTTP sessions hay database. Tất cả timestamp được kiểm soát để stdout có thể kiểm thử chính xác.

~~~java
import java.time.Duration;
import java.time.Instant;

public class MfaFreshnessExample {
    enum Factor { PASSWORD, TOTP }

    record Session(
            String userId, String sessionId,
            Instant issuedAt, Instant expiresAt) {}

    record Proof(
            String userId, String sessionId, Factor factor,
            Instant verifiedAt, Instant invalidatedAt) {}

    static boolean recent(
            Proof proof, Session session, Factor required,
            Instant now, Duration maxAge) {
        if (proof == null || session == null || now == null
                || maxAge.isZero() || maxAge.isNegative()) {
            return false;
        }
        return proof.userId().equals(session.userId())
            && proof.sessionId().equals(session.sessionId())
            && proof.factor() == required
            && !now.isBefore(session.issuedAt())
            && now.isBefore(session.expiresAt())
            && !proof.verifiedAt().isBefore(session.issuedAt())
            && !proof.verifiedAt().isAfter(now)
            && now.isBefore(proof.verifiedAt().plus(maxAge))
            && (proof.invalidatedAt() == null
                || now.isBefore(proof.invalidatedAt()));
    }

    static boolean approve(
            Session session, Proof password, Proof totp, Instant now) {
        return recent(password, session, Factor.PASSWORD,
                      now, Duration.ofMinutes(30))
            && recent(totp, session, Factor.TOTP,
                      now, Duration.ofMinutes(5));
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-06T08:00:00Z");
        Session session = new Session(
                "usr-1042", "sid-A", start, start.plusSeconds(7200));

        Proof password = new Proof(
                "usr-1042", "sid-A", Factor.PASSWORD, start, null);
        Proof totp = new Proof(
                "usr-1042", "sid-A", Factor.TOTP,
                start.plusSeconds(120), null);

        Instant first = start.plusSeconds(300);
        Instant deadline = start.plusSeconds(420);
        System.out.println("initial approval: "
                + approve(session, password, totp, first));
        System.out.println("session alive at deadline: "
                + deadline.isBefore(session.expiresAt()));
        System.out.println("approval at OTP deadline: "
                + approve(session, password, totp, deadline));

        Session other = new Session(
                "usr-1042", "sid-B", start, start.plusSeconds(7200));
        System.out.println("other session: "
                + recent(totp, other, Factor.TOTP,
                         first, Duration.ofMinutes(5)));
        System.out.println("proof from future: "
                + recent(totp, session, Factor.TOTP,
                         start.plusSeconds(60), Duration.ofMinutes(5)));

        Proof newTotp = new Proof(
                "usr-1042", "sid-A", Factor.TOTP,
                start.plusSeconds(430), null);
        System.out.println("after step-up: "
                + approve(session, password, newTotp,
                          start.plusSeconds(431)));

        Proof revoked = new Proof(
                "usr-1042", "sid-A", Factor.TOTP,
                start.plusSeconds(430), start.plusSeconds(432));
        System.out.println("revoked proof: "
                + approve(session, password, revoked,
                          start.plusSeconds(433)));
    }
}
~~~

Lưu đúng tên `MfaFreshnessExample.java` rồi chạy:

~~~bash
javac MfaFreshnessExample.java
java MfaFreshnessExample
~~~

Stdout chính xác:

~~~text
initial approval: true
session alive at deadline: true
approval at OTP deadline: false
other session: false
proof from future: false
after step-up: true
revoked proof: false
~~~

Tại 08:05, password đã được xác minh 5 phút và TOTP 3 phút nên đủ điều kiện. Tại 08:07, TOTP đã đúng **5 phút tuổi**, không đạt `now < verifiedAt + maxAge`, dù session vẫn còn hạn đến 10:00. Proof của session A không áp cho B; event 08:02 không được chấp nhận ở thời điểm 08:01; sau step-up mới lúc 08:07:10 proof lại đủ mới, rồi có thể bị thu hồi lúc 08:07:12.

Trong production, `Proof`/`Session` chỉ được xây từ **trusted server state**, không phải JSON do client cung cấp. Cần có authenticator verifier, persistent store, concurrency control, clock synchronization, session/account status và method-level authorization bên ngoài demo.

## 15. Spring Security 6: kiểm tra tại đúng authorization boundary

Trong Spring Boot 3.x / Spring Security 6.x (Servlet), một request có `Authentication` trong `SecurityContext` chỉ cho biết framework đã nhận một authentication object đang authenticated. Nó không tự xác nhận bằng chứng MFA còn mới.

Cấu hình:

~~~java
// Chưa đủ cho hành động yêu cầu step-up:
.requestMatchers("/payments/approve")
    .hasAuthority("PAYMENT_APPROVE")
~~~

chỉ kiểm tra authority, không xét `verifiedAt`.

### Tích hợp bằng Method Security

Spring Security có `@EnableMethodSecurity` và `@PreAuthorize` để đặt điều kiện tại service boundary. Ví dụ sau là **mã tích hợp cần dự án Spring**, không phải chương trình `javac` độc lập; bean `factorFreshnessPolicy` phải được ứng dụng hiện thực bằng trusted repository/session/clock.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class SecurityMethodConfig {}
~~~

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PaymentApprovalService {
    private final PaymentRepository payments;

    public PaymentApprovalService(PaymentRepository payments) {
        this.payments = payments;
    }

    @PreAuthorize(
        "hasAuthority('PAYMENT_APPROVE') and " +
        "@factorFreshnessPolicy.recentForPayment(authentication)")
    public void approve(String paymentId) {
        // Service cần xác minh tenant, resource, transaction status,
        // và nếu cần recheck proof tại thời điểm commit.
        payments.approveWithPolicy(paymentId);
    }
}
~~~

Đây là đoạn **minh họa điểm mở rộng**: `PaymentRepository` và `factorFreshnessPolicy` là hợp đồng do hệ thống cung cấp. Bean policy cần kiểm tra userId/sessionId/factorKind/verifiedAt/invalidation/purpose từ nguồn tin cậy và giờ server. Nếu ứng dụng tự gọi một method được bảo vệ từ chính object đó (self-invocation), Spring proxy method security có thể không intercept; phải đặt đúng service boundary và integration test.

### Phác thảo một policy service

~~~java
// Pseudocode Java, không biên dịch độc lập:
boolean recentForPayment(Authentication authentication) {
    String userId = internalIdentityResolver.userId(authentication);
    String sessionId = trustedSessionResolver.sessionId();
    Instant now = clock.instant();
    Duration maxAge = Duration.ofMinutes(5);

    return factorProofStore.hasValidProof(
        userId, sessionId, "PAYMENT_APPROVAL",
        "APPROVED_POSSESSION_FACTOR",
        now.minus(maxAge), now);
}
~~~

**Phương thức `hasValidProof` phải tự kiểm tra toàn bộ contract**: provenance, assurance, exact deadline semantics, event future, invalidation, tenant/account, factor/device status. Đừng tin vào một hàng DB mới được client post lên. Nếu cần strict `now < verifiedAt + 5m` thì query chỉ dựa vào `verifiedAt >= now-5m` có thể bao gồm một proof ở đúng biên; phải dùng predicate đúng ranh giới chính sách trong implementation.

### Sinh proof sau verify thành công

~~~text
POST /mfa/challenges
  -> đòi existing authenticated session
  -> issue challenge bound user/session/purpose/expiry

POST /mfa/challenges/{id}/verify
  -> verify actual authenticator response
  -> enforce attempt limit, expiry and anti-replay atomically
  -> record trusted verifiedAt via server clock
  -> return only step-up outcome

POST /payments/{id}/approve
  -> authenticated principal, permission, tenant, resource
  -> factor-proof freshness, session status, risk
  -> commit action
~~~

Với cookie/session, giữ CSRF protection cho POST và cookie security (`Secure`, `HttpOnly`, `SameSite` phù hợp). Không disable CSRF toàn app chỉ để cho challenge verification endpoint chạy; và không cấp quyền bằng việc thay một flag dễ sửa ở client.

## 16. Atomic verification, replay và time-of-check/time-of-use

OTP/challenge có thể bị nộp đồng thời từ hai request:

~~~text
A: SELECT consumed_at IS NULL -> true
B: SELECT consumed_at IS NULL -> true
A: mark consumed; create new MFA proof
B: mark consumed; create another MFA proof
~~~

Nếu check và update tách rời, cả hai có thể được chấp nhận. Cần **compare-and-set/conditional update** trong DB hoặc atomic store thích hợp, có unique constraint và transaction.

~~~sql
-- Ví dụ PostgreSQL: chỉ một request có thể claim challenge.
-- Cần verify cryptographic OTP/assertion trước bước này.
UPDATE mfa_challenges
   SET consumed_at = CURRENT_TIMESTAMP
 WHERE challenge_id = :challenge_id
   AND subject_id = :user_id
   AND session_id = :session_id
   AND consumed_at IS NULL
   AND revoked_at IS NULL
   AND expires_at > CURRENT_TIMESTAMP
RETURNING factor_kind, purpose;
~~~

Đoạn SQL **không tự kiểm tra OTP hoặc chữ ký**; cần kết hợp với verifier và transaction đúng để không ghi proof khi kiểm tra failed, đồng thời tránh race trong cùng authenticator counter.

Nếu elevated proof **chỉ được dùng một lần cho một transaction**, authorization/commit cũng phải consume proof hoặc action grant nguyên tử. Một proof mới đủ tuổi 10 giây nhưng đã dùng để duyệt giao dịch A không nhất thiết được dùng lại cho giao dịch B. Nếu policy cho phép nhiều action trong freshness window, quyết định đó phải được ghi rõ chứ không phụ thuộc may rủi concurrency.

**TOCTOU:** kiểm tra MFA lúc mở form, sau 20 phút mới thực hiện thay đổi là sai nếu policy là 5 phút. Recheck ở service/transaction boundary gần lúc áp dụng side effect. Với hệ thống qua queue, cần action-bound authorization grant có expiry hoặc chặn thực thi nếu quá hạn; đừng chuyển decision cũ từ UI thành quyền vô thời hạn.

## 17. Invalidation và revoke trước khi hết thời hạn

Một proof có `verifiedAt` gần hiện tại vẫn có thể phải bị từ chối khi:

- User logout hoặc session bị terminate.
- Account disabled, tenant thay đổi, quyền bị thu hồi.
- Authenticator bị xóa, compromise hoặc reset.
- Password/MFA recovery xảy ra, security team đánh dấu risk cao.
- SSO/IdP phát tín hiệu revocation qua contract tương ứng.
- Proof action-bound đã được tiêu thụ cho giao dịch khác.
- Client/session bị đánh giá rủi ro cao: device compromise, suspicious session, hijacking signal.

Do đó freshness chỉ là **một điều kiện trong authorization**, không phải quyết định duy nhất.

**Vấn đề cache:** có thể cache event `verifiedAt` bất biến, nhưng không cache boolean `mfaFresh=true` quá thời hạn. Nếu cache chứa quyết định allow trong 10 phút còn factor maxAge là 5 phút, hệ thống sẽ vô tình kéo dài quyền. Invalidation cần truyền tới mọi instance theo SLA; session storage/DB transaction phải nhất quán với policy.

Không dùng IP/geolocation làm bằng chứng MFA; chúng chỉ là tín hiệu rủi ro. Không cho người ngoài trigger reset/invalidate yếu tố của tài khoản khác bằng cách flood anonymous request (cần rate limit/cooldown).

## 18. Lựa chọn thời hạn theo hành động, không theo một hằng số toàn hệ thống

| Action | Cấp xác thực yêu cầu (ví dụ) | Freshness gợi ý để thảo luận | Khi không đạt |
|---|---|---|---|
| Xem nội dung công khai | Không cần login. | Không áp dụng. | Không yêu cầu MFA. |
| Xem dashboard cá nhân | Authenticated session + account active. | Theo session policy. | Login lại nếu session expired. |
| Đổi thông tin cá nhân | Session và yếu tố bổ sung. | 5–10 phút tùy risk. | Step-up. |
| Đổi mật khẩu | Re-auth hoặc recovery flow mạnh. | Ngắn, đúng thời điểm thao tác. | Re-auth/recovery theo policy. |
| Xóa/thay MFA factor | Assurance cao + chống account takeover. | Cửa sổ ngắn, có thể yêu cầu một transaction. | Step-up/recovery đặc biệt. |
| Phê duyệt chi tiền | Role + fresh possession/passkey + resource context. | 3–5 phút hoặc proof ràng buộc mỗi giao dịch. | Step-up trước commit. |
| Xuất dữ liệu nhạy cảm | Authorization + fresh proof + audit. | Ngắn hơn session bình thường. | Re-auth/deny. |
| Thay chính sách quản trị | Admin role + assurance cao + session an toàn. | Elevation ngắn và giới hạn scope. | Step-up/phê duyệt lại. |

Các số chỉ **minh họa**, phải điều chỉnh theo threat model và yêu cầu assurance/chính sách nội bộ. Thời hạn ngắn giảm khoảng có thể bị lạm dụng khi session bị chiếm nhưng làm tăng MFA fatigue; có thể giảm ma sát nhờ phương thức phishing-resistant và flow transaction signing phù hợp.

Nếu tổ chức áp NIST hoặc một chuẩn cụ thể, cần đối chiếu **phiên bản chuẩn và assurance level thực tế**, không suy từ ví dụ trên ra một luật bắt buộc. Một yếu tố mức thấp không nên được “nâng cấp” thành mức cao chỉ nhờ có timestamp mới.

## 19. Vận hành đồng hồ và trải nghiệm người dùng

- Dùng `Instant` UTC của server/trusted verifier; lưu timezone chỉ để hiển thị.
- Đồng bộ đồng hồ giữa IdP, application nodes và DB, theo dõi drift. Policy clock skew cho token/TOTP có thể khác với policy maxAge của proof.
- Khi proof quá hạn ở bước cuối form, UX nên yêu cầu step-up nhưng **giữ thông tin không nhạy cảm** đã nhập theo cơ chế phù hợp. Đừng tự gia hạn proof để tránh phiền.
- Challenge issuance cần quota, timeout, chống MFA push fatigue, account abuse; mỗi request resend không phải verified event.
- Nếu proof store/IdP lỗi, fail closed cho action nhạy cảm và hiển thị lỗi có thể khắc phục; không fallback sang session alone/role admin.
- Tách success/failure audit theo subject, method, policy version, timestamp và request ID; không log mã OTP, TOTP seed, challenge response hay access token.
- Khi password reset, MFA removal hoặc login session regeneration, định nghĩa rõ proof nào còn hợp lệ; không vô tình kéo proof cũ qua session mới.

**Đồng hồ client không đáng tin.** Browser thay timezone, lùi clock hoặc đóng/mở tab không làm bằng chứng kéo dài. Đo đạc trên nhiều instance phải kiểm thử chính xác thời điểm `now = verifiedAt + maxAge`.

## 20. Bộ kiểm thử bắt buộc

| Test case | Kỳ vọng |
|---|---|
| Challenge verify trước expiry một mili-giây. | Có thể thành công khi đúng code/attempts và chưa consumed. |
| Challenge tại đúng expiry. | Từ chối theo boundary policy. |
| OTP sai, nhưng ứng dụng ghi `verifiedAt`. | Không được xảy ra. |
| OTP được submit đồng thời hai lần. | Một lần thắng theo replay policy; không ghi hai proof độc lập. |
| TOTP được accept 4 phút 59 giây trước, maxAge 5 phút. | Có thể coi fresh nếu mọi điều kiện khác đúng. |
| TOTP đúng 5 phút tuổi. | Không fresh; yêu cầu step-up. |
| Session còn sống, proof quá tuổi. | Action thường có thể tiếp tục, action nhạy cảm bị chặn. |
| Session đã logout, proof 1 giây tuổi. | Từ chối; proof không hồi sinh session. |
| Proof có timestamp từ tương lai. | Từ chối hoặc xử lý rất chặt theo clock policy. |
| Proof user A dùng cho user B. | Từ chối. |
| Proof session A dùng cho session B. | Từ chối khi session-bound. |
| Password mới, TOTP cũ. | Không tự coi cả hai yếu tố đều fresh. |
| OIDC access token `iat` mới, `auth_time` cũ. | Không coi refresh token là re-auth/MFA. |
| IdP trả `amr` có OTP nhưng thiếu recency cụ thể. | Không suy ra OTP vừa xác minh theo policy thời gian. |
| User có role nhưng proof quá hạn. | Deny/step-up. |
| Proof đủ mới nhưng thiếu role. | Authorization deny. |
| Thay đổi authenticator sau proof. | Invalidation theo lifecycle policy. |
| Mở form khi proof fresh, submit sau 20 phút. | Recheck tại commit, không dùng quyết định cũ. |
| Proof transaction A dùng lại cho transaction B. | Chặn nếu action-bound/one-time. |
| Error của Redis/DB/IdP. | Không bypass step-up. |
| Client gửi `verifiedAt=now` trong JSON. | Không ảnh hưởng trusted proof. |
| Tải lại trang/refresh token. | Không tự thay đổi factor verifiedAt. |
| Proof được cache lâu hơn maxAge. | Mỗi quyết định tính lại tuổi; không cho phép quá hạn. |
| Đổi timezone của browser. | Không thay đổi kết quả so sánh server Instant. |

Nên có **unit test** cho boundary với `Clock.fixed(...)`, **integration test** Spring Security + persistent proof store, **concurrency test** khi consume challenge, **SSO test** để xác nhận `auth_time`/`acr` thật sự đáp ứng policy và **end-to-end test** chống TOCTOU. Kết quả HTTP 200 sau một OTP đúng không chứng minh toàn bộ cơ chế đã an toàn.

## 21. Những hiểu nhầm phổ biến và cách sửa

**“TOTP 30 giây nên MFA chỉ có giá trị 30 giây.”** 30 giây là một time step; còn thời hạn chấp nhận proof đã xác minh là chính sách khác. Mã TOTP cũ không được dùng lại.

**“Refresh JWT thì MFA mới lại.”** `iat` mới không đồng nghĩa `auth_time` hoặc factor `verifiedAt` mới.

**“Phiên đang active nên yếu tố vừa được xác minh.”** Session last access/creation không phải event xác thực.

**“Một boolean `mfa=true` là đủ.”** Phải biết factorKind/assurance, verifiedAt, subject, session, provenance, purpose và invalidation.

**“MFA success thì cho mọi hành động admin.”** Cần authorization theo role, tenant, resource và transaction, độc lập với MFA.

**“Mã gửi SMS đã được giao thì coi như user có điện thoại.”** Delivery không phải verification; và phương thức có giới hạn assurance.

**“Thêm 5 phút clock skew cho mọi kiểm tra MFA.”** Tolerance cho TOTP/JWT khác độ mới proof; không gia hạn freshness không có lý do.

**“Kiểm tra MFA ở GET rồi POST khỏi cần.”** Thao tác thực có thể xảy ra sau khi proof hết hạn; recheck gần commit.

**“Mọi passkey tự là hai yếu tố ở assurance cao.”** Cần xác minh UV/policy/credential, không suy từ nhãn sản phẩm.

**“Muốn rút ngắn MFA thì ép user nhập TOTP trên mỗi click.”** Cần kết hợp risk, phishing resistance, transaction binding và UX; việc quá nhiều prompt có thể tăng MFA fatigue.

## 22. Checklist sản phẩm

- [ ] Phân biệt challenge `expiresAt`, factor `verifiedAt`, session expiration và token `exp`.
- [ ] Tạo event chỉ sau verification thành công; provenance và timestamp đến từ server tin cậy.
- [ ] TOTP kiểm tra step/drift, attempts, replay và bảo vệ shared secret.
- [ ] WebAuthn kiểm tra challenge, origin/RP ID, signature, UP/UV và credential policy.
- [ ] Factor independence/assurance được đánh giá, không chỉ số bước.
- [ ] Proof bind đúng user/session/issuer/purpose và action nếu cần.
- [ ] Dùng ranh giới thời gian nhất quán: `now < verifiedAt + maxAge`.
- [ ] Token `iat`/`exp` không được dùng làm timestamp MFA mới; OIDC `auth_time`/`acr`/`amr` phải được hiểu theo IdP contract.
- [ ] Session idle/absolute timeout riêng với proof freshness.
- [ ] Authorization xét cả role/resource và MFA freshness gần thời điểm commit.
- [ ] Challenge consume nguyên tử, có chống replay; elevated one-time grant cũng được consume đúng.
- [ ] Logout, disable account, remove authenticator, recovery và incident làm invalidate proof theo policy.
- [ ] Cache không giữ boolean freshness qua deadline; nhiều instance đồng bộ invalidation.
- [ ] CSRF, session fixation, cookie security, rate limiting và MFA fatigue có kiểm soát.
- [ ] Đồng hồ server/IdP/DB đồng bộ và boundary tests chính xác.
- [ ] UX step-up rõ ràng, có đường phục hồi được kiểm soát khi yếu tố hết hạn.
- [ ] Audit có timestamp, factor method, policy version, request/action ID; không chứa bí mật.

## 23. Kết luận

**Thời điểm xác thực của một yếu tố** phải là lúc verifier xác nhận bằng chứng thành công. **Thời hạn chấp nhận** cần chỉ rõ đang nói đến *mã/challenge có thể nộp*, *proof đã xác minh còn mới*, *session còn hoạt động* hay *token còn hiệu lực*. Bốn mốc đó có thể khác nhau rất xa.

Mô hình an toàn là: **issue challenge có thời hạn → xác minh thực tế và chống replay → ghi factor proof với timestamp đáng tin → bind đúng user/session/action → đánh giá freshness và quyền tại thời điểm thực thi → hết hạn hoặc invalidate → yêu cầu step-up khi cần**.

Nhờ tách các khái niệm, ứng dụng Spring Security có thể giữ phiên hợp lệ để người dùng làm tác vụ thông thường, đồng thời bảo vệ thao tác nhạy cảm bằng yêu cầu **yếu tố đủ mới và đủ mạnh** thay vì một dấu `mfa=true` được ghi từ nhiều giờ trước.

## Tài liệu tham khảo

- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): assurance, authenticator và reauthentication.
- [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): MFA, step-up, recovery và MFA fatigue.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifetime và timeout.
- [RFC 6238 — TOTP](https://www.rfc-editor.org/rfc/rfc6238): bước thời gian và cửa sổ xác minh TOTP.
- [RFC 4226 — HOTP](https://www.rfc-editor.org/rfc/rfc4226): HOTP counter, replay và throttling.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0-final.html): `auth_time`, `max_age`, `acr` và `amr`.
- [W3C Web Authentication](https://www.w3.org/TR/webauthn-3/): challenge, RP ID, origin và authenticator assertions.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): method authorization, `@EnableMethodSecurity` và `@PreAuthorize`.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session lifecycle và SecurityContext.
- [Java 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): thời gian tuyệt đối trên Java Time.
