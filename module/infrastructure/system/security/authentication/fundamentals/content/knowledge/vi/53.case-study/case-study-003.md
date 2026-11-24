# Đăng nhập bằng passkey

> **Chương:** Case study  
> **Bối cảnh module:** **SECURITY_AUTHENTICATION_FUNDAMENTALS** giúp người học hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản; đồng thời biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay và lạm dụng đăng nhập. Case study này phân tích một hệ thống SaaS đa tenant chuyển luồng đăng nhập web sang passkey, từ thiết kế WebAuthn ceremony đến xác minh assertion, tạo session, fallback, vận hành và xử lý sự cố.

## 1. Bối cảnh doanh nghiệp

Northstar Cloud là một nền tảng SaaS quản lý dự án cho doanh nghiệp. Người dùng truy cập qua trình duyệt, một số người dùng qua ứng dụng di động, còn nhân viên hỗ trợ và quản trị viên có các chức năng đặc quyền.

Hệ thống hiện dùng email và password. Sau khi password hợp lệ, một số nhóm người dùng phải nhập thêm TOTP. Trong năm gần đây, đội vận hành ghi nhận:

- Credential stuffing làm tăng lượng login thất bại và tải password verifier.
- Người dùng bị lừa nhập password vào trang phishing có giao diện gần giống trang thật.
- Password reuse làm một lần lộ credential ở dịch vụ khác ảnh hưởng tới Northstar.
- Reset password và hỗ trợ MFA làm tăng chi phí vận hành.
- Người dùng muốn đăng nhập nhanh trên thiết bị có sẵn biometric hoặc screen lock.

Ban lãnh đạo quyết định bổ sung passkey theo chuẩn WebAuthn/FIDO2. Giai đoạn đầu, passkey được triển khai như phương thức đăng nhập chính cho nhóm người dùng đã enroll; password và recovery vẫn tồn tại trong thời gian chuyển đổi có kiểm soát.

Mục tiêu là giảm phụ thuộc vào password, chống phishing ở tầng xác thực và cải thiện trải nghiệm. Dự án không giả định rằng chỉ cần thêm nút “Sign in with passkey” là toàn bộ rủi ro identity biến mất.

## 2. Phạm vi và tiêu chí thành công

Phạm vi của case study:

- Đăng nhập passkey trên web bằng discoverable credential, cho phép usernameless flow.
- Xác minh assertion tại backend.
- Liên kết credential với đúng account và tenant context.
- Tạo session an toàn sau khi xác minh thành công.
- Xử lý cancellation, timeout, credential không tìm thấy và authenticator không đáp ứng policy.
- Fallback sang phương thức đã đăng ký hoặc recovery flow có kiểm soát.
- Theo dõi adoption, lỗi và dấu hiệu lạm dụng mà không log assertion hoặc secret.

Tiêu chí thành công:

1. Assertion chỉ được chấp nhận khi challenge, origin, RP ID, chữ ký và trạng thái credential đều hợp lệ.
2. Challenge chỉ được dùng một lần và gắn với đúng authentication transaction.
3. Session ID được rotate ở ranh giới pre-authentication sang authenticated.
4. Usernameless login xác định đúng account từ credential ID/user handle đã đăng ký.
5. User thuộc tenant nào chỉ nhận quyền tương ứng sau bước authorization.
6. Fallback không âm thầm hạ assurance hoặc tạo account linking ngoài ý muốn.
7. Các luồng failure không làm lộ account existence hoặc dữ liệu credential.
8. Metrics/audit đủ cho vận hành nhưng không chứa raw assertion, cookie hay private key.

## 3. Kiến trúc và các bên tham gia

Các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| Browser | Gọi WebAuthn API và gửi assertion tới RP backend |
| Authenticator/platform | Tạo proof bằng private key được bảo vệ trên thiết bị hoặc credential provider |
| Northstar Web RP | Khởi tạo challenge, xác minh assertion và tạo session |
| Account service | Quản lý account, user handle và trạng thái người dùng |
| Credential store | Lưu credential ID, public key và metadata cần thiết |
| Session service | Tạo, rotate, validate và revoke session |
| Policy/risk service | Đánh giá action, account state, risk và step-up requirement |
| Audit/monitoring | Ghi lifecycle event, kết quả và metrics đã giảm thiểu dữ liệu |

~~~mermaid
flowchart LR
    U["User"] --> B["Browser"]
    B <--> A["Platform authenticator / passkey provider"]
    B --> RP["Northstar Web RP"]
    RP --> CS["Challenge store"]
    RP --> CR["Credential store"]
    RP --> AS["Account service"]
    RP --> POL["Policy / risk"]
    RP --> SS["Session service"]
    RP --> AU["Audit and metrics"]
~~~

Browser và authenticator không được coi là backend authority. Browser chuyển dữ liệu WebAuthn giữa authenticator và RP; backend vẫn phải xác minh toàn bộ assertion theo RP configuration và credential đã đăng ký.

## 4. Trust boundaries

Hệ thống có các ranh giới tin cậy chính:

1. **Browser ↔ RP backend:** request từ browser có thể bị sửa; không tin các field account/tenant do client tự khai.
2. **Browser ↔ authenticator:** browser điều phối ceremony; authenticator giữ private key và yêu cầu user presence/verification theo capability.
3. **RP ↔ credential store:** public key và credential metadata phải được bảo vệ integrity; chỉ credential đã gắn với account đúng mới được xác minh.
4. **RP ↔ account/policy service:** account state và authorization context phải đến từ nguồn server-side có thẩm quyền.
5. **RP ↔ session store:** session state, expiry và revocation phải nhất quán theo policy.
6. **RP ↔ observability:** log/trace chỉ nhận dữ liệu đã allowlist và redact.

Private key passkey không được gửi về server trong authentication ceremony. Server giữ public key và dùng nó để xác minh chữ ký. Tuy vậy, public key record, credential ID, user handle và thiết bị metadata vẫn cần access control và privacy protection.

## 5. Passkey và WebAuthn trong bài toán này

Passkey là credential dựa trên cặp khóa công khai/bí mật, thường được đồng bộ an toàn giữa các thiết bị hoặc gắn với authenticator. WebAuthn định nghĩa API và protocol giữa relying party (RP), browser/client và authenticator.

Trong luồng đăng nhập:

- RP tạo challenge ngẫu nhiên, dùng một lần.
- Browser gọi WebAuthn API để lấy credential assertion.
- Authenticator yêu cầu user presence và có thể yêu cầu user verification như biometric, PIN hoặc screen lock.
- Authenticator ký dữ liệu liên quan challenge bằng private key.
- Browser gửi assertion về RP.
- RP xác minh challenge, origin, RP ID hash, flags và signature bằng public key đã lưu.

Passkey có khả năng chống phishing vì proof được ràng buộc với RP ID/origin. Một trang giả mạo ở domain khác không thể tạo assertion hợp lệ cho RP thật chỉ bằng cách thu thập password hoặc OTP.

Không nên diễn giải passkey thành “biometric được gửi lên server”. Biometric thường được xử lý cục bộ bởi platform/authenticator; server nhận assertion và metadata cần thiết để xác minh.

## 6. Đăng ký credential đã diễn ra trước case login

Case study tập trung vào login, nhưng backend chỉ có thể xác minh passkey nếu user đã enroll credential.

Trong registration ceremony, RP đã:

1. Xác minh user bằng phương thức hiện tại hoặc quy trình enrollment đủ assurance.
2. Tạo challenge registration ngẫu nhiên và transaction-bound.
3. Cung cấp RP ID, user ID/opaque user handle và user name/display name phù hợp.
4. Nhận attestation/credential response từ browser.
5. Xác minh type, challenge, origin, RP ID hash và các policy liên quan.
6. Lưu credential ID, public key, algorithm, user handle mapping và metadata được phép.
7. Ghi audit event về credential được thêm vào account.

Attestation có thể giúp RP đánh giá authenticator provenance trong một số policy, nhưng không phải mọi passkey deployment đều cần hoặc nên yêu cầu attestation. Chính sách attestation phải được xác định theo risk, privacy và ecosystem compatibility.

Credential public key phải được liên kết với account sau khi xác minh ownership. Không cho client gửi userId tùy ý để gắn credential vào account khác.

## 7. Vì sao chọn usernameless login?

Northstar muốn người dùng nhấn “Sign in with passkey” và chọn passkey từ browser/authenticator, thay vì luôn nhập email trước.

Đây là discoverable credential flow:

- RP có thể gửi allowCredentials rỗng hoặc bỏ qua danh sách credential cụ thể theo API contract.
- Authenticator/browser tìm credential phù hợp với RP ID.
- Assertion có thể chứa userHandle để RP xác định user account.
- Backend tra credential ID và/hoặc user handle mapping đã lưu để xác định principal.

Usernameless không có nghĩa server tin username do browser gửi. Credential ID và user handle phải được tra cứu trong credential registry có thẩm quyền; account phải còn active.

Nếu dùng username-first flow, backend có thể tra account trước rồi gửi allowCredentials phù hợp. Cả hai flow đều cần xác minh assertion đầy đủ.

## 8. Chuẩn bị challenge cho login

Khi user chọn passkey, browser gửi request bắt đầu authentication tới RP. Server tạo transaction:

~~~text
transaction_id = opaque random reference
challenge = 32 bytes from a CSPRNG
rp_id = login.northstar.example
created_at = server time
expires_at = created_at + short challenge lifetime
status = PENDING
purpose = WEBAUTHN_GET
pre_auth_session = bound server-side reference
~~~

Challenge cần:

- Đủ entropy từ cryptographically secure random generator.
- Được gắn với purpose, RP ID, transaction và pre-auth session.
- Có expiry ngắn theo policy.
- Chỉ được consume một lần.
- Không thể thay đổi bằng request từ client.
- Được lưu server-side hoặc bảo vệ bằng cơ chế transaction integrity tương đương.

Ví dụ lifetime vài phút có thể phù hợp với UX, nhưng giá trị chính xác cần dựa trên threat model và browser behavior. Không dùng challenge cố định hoặc chỉ dựa timestamp.

### PublicKeyCredentialRequestOptions

Server trả options tương đương:

~~~json
{
  "challenge": "<base64url-encoded-random-challenge>",
  "rpId": "login.northstar.example",
  "timeout": 180000,
  "userVerification": "required"
}
~~~

Với usernameless flow, allowCredentials có thể được bỏ qua hoặc để danh sách rỗng tùy API/implementation. Nếu policy cần giới hạn credential, RP có thể cung cấp danh sách credential ID đã tra theo account.

userVerification=required yêu cầu authenticator thực hiện user verification theo khả năng của nó. RP vẫn phải kiểm tra cờ UV trong authenticator data; không suy luận UV thành công chỉ từ việc browser trả response.

## 9. Browser gọi WebAuthn API

Browser nhận request options rồi gọi:

~~~javascript
const publicKey = decodeRequestOptions(serverOptions);

const assertion = await navigator.credentials.get({
  publicKey
});

if (assertion) {
  await sendAssertionToServer(encodeAssertion(assertion));
}
~~~

Đây là pseudocode. Hàm encode/decode phải chuyển base64url thành ArrayBuffer và ngược lại đúng cách; không gửi JavaScript object tùy tiện rồi kỳ vọng server tự hiểu các binary field.

Browser có thể trả các tình huống:

- User chọn passkey và xác minh thành công.
- User hủy dialog.
- Không có credential phù hợp.
- Authenticator không hỗ trợ user verification bắt buộc.
- Request hết timeout.
- Browser/platform gặp lỗi tạm thời.

Cancel hoặc timeout không đồng nghĩa password sai hay account không tồn tại. Backend nên phân biệt client cancellation với assertion validation failure ở telemetry nội bộ, nhưng public response vẫn cần tránh account enumeration.

## 10. Assertion gửi về server gồm những gì?

Một PublicKeyCredential authentication response thường có:

- id/rawId: credential identifier.
- type: phải là public-key.
- response.clientDataJSON.
- response.authenticatorData.
- response.signature.
- response.userHandle nếu có.
- clientExtensionResults.

Các field này là input không tin cậy cho tới khi backend xác minh. Không dùng id, userHandle, origin hoặc flags do client gửi như dữ kiện đã được xác thực.

Không log raw assertion. Payload có thể chứa challenge, credential identifier, authenticator metadata và các dữ liệu liên quan tới thiết bị/user.

## 11. Backend xác định credential và account

Trong usernameless flow, backend cần tìm credential record:

~~~text
credential_id -> credential record
credential record:
  account_id
  opaque_user_handle
  public_key
  algorithm
  status
  rp_id
  created_at
  last_used_at
  sign_count (if meaningful)
  backup_eligibility/state (if supported)
~~~

Các kiểm tra:

- Credential ID tồn tại và thuộc RP/tenant context hợp lệ.
- Credential đang active, không bị revoke hoặc remove.
- Account còn active và không bị disable.
- User handle nếu có phải khớp mapping đã đăng ký.
- Public key và algorithm thuộc profile được hỗ trợ.
- Không cho một credential ID bị liên kết với nhiều account trái policy.

Opaque user handle nên ổn định theo account nhưng không nhất thiết là database primary key có thể đoán hoặc chứa PII. Không dùng email làm user handle nếu không có lý do rõ.

Nếu credential không tìm thấy, trả kết quả login thất bại chung. Không tiết lộ rằng một credential ID cụ thể có tồn tại trong hệ thống.

## 12. Xác minh clientDataJSON

Server parse clientDataJSON và kiểm tra:

1. type đúng là webauthn.get.
2. challenge khớp chính xác challenge của transaction pending.
3. origin khớp allowlist origin đã cấu hình cho RP.
4. Cross-origin/top-origin context phù hợp với deployment policy nếu được sử dụng.
5. JSON và encoding hợp lệ, không có dữ liệu cấu trúc bất thường.

Không so origin bằng substring. Ví dụ https://northstar.example.attacker.test không được coi là https://northstar.example.

Origin phải được chuẩn hóa và so khớp theo semantics của WebAuthn, scheme/host/port và deployment configuration. Không lấy expected origin từ header Host hoặc query parameter không được trust.

## 13. Xác minh authenticatorData và RP ID hash

Server kiểm tra:

- rpIdHash bằng SHA-256 của RP ID được cấu hình.
- User Presence (UP) flag theo yêu cầu.
- User Verification (UV) flag nếu policy yêu cầu.
- Reserved/extension flags theo parser và WebAuthn version được hỗ trợ.
- Authenticator data có cấu trúc và độ dài hợp lệ.

UP chứng minh authenticator đã thực hiện ceremony với user presence theo protocol. UV cho biết user verification đã được thực hiện theo cơ chế authenticator. Nếu policy đặt userVerification=required, assertion thiếu UV phải bị từ chối.

Không đồng nhất UP với UV. User presence không nhất thiết chứng minh biometric/PIN verification.

## 14. Xác minh chữ ký

WebAuthn assertion signature được xác minh bằng public key đã lưu khi registration. Về khái niệm, dữ liệu được ký là:

\[
\text{authenticatorData} \; || \; SHA256(\text{clientDataJSON})
\]

Backend:

1. Lấy public key từ credential record đã xác định.
2. Xác định thuật toán theo credential registration/profile đã chấp nhận.
3. Tạo signed bytes đúng WebAuthn encoding.
4. Xác minh signature bằng thư viện WebAuthn/crypto đã được kiểm chứng.
5. Từ chối nếu signature sai, key không phù hợp hoặc payload không hợp lệ.

Không tự viết parser/cryptographic verifier tối giản cho production. Sử dụng thư viện WebAuthn được duy trì, cấu hình RP ID/origin rõ ràng và kiểm thử bằng test vector.

Không chấp nhận algorithm do client tự khai nếu algorithm đó không thuộc danh sách đã được registration policy cho phép.

## 15. Challenge one-time và replay protection

Sau khi assertion được xác minh, challenge phải được consume nguyên tử:

- Transaction phải còn PENDING.
- Chưa hết hạn.
- Purpose phải là WEBAUTHN_GET.
- Challenge phải khớp.
- Chỉ một request có thể chuyển transaction sang CONSUMED.

Nếu hai request đồng thời gửi cùng assertion, chỉ một request được phép hoàn tất transaction. Request thứ hai phải bị từ chối.

Không chỉ xóa challenge sau khi tạo session mà không có atomicity; hai request song song có thể cùng đọc trạng thái pending và đều thành công. Dùng compare-and-set, transaction hoặc atomic consume tại store.

Challenge reuse, transaction ID reuse và assertion replay phải được kiểm thử. Session creation cũng cần idempotency/transaction semantics để timeout sau commit không tạo hai session ngoài ý muốn.

## 16. Signature counter và passkey đồng bộ

WebAuthn authenticator data có thể chứa signature counter. Một số authenticator truyền thống tăng counter sau mỗi lần ký; counter bất thường có thể là tín hiệu clone hoặc credential sharing.

Tuy nhiên, passkey có thể được đồng bộ giữa thiết bị hoặc do platform quản lý. Một số credential có counter luôn bằng 0 hoặc không đảm bảo monotonic theo cách RP mong đợi.

Vì vậy:

- Lưu counter nếu profile/library cung cấp và policy cần.
- So sánh theo semantics authenticator đã biết.
- Xem counter không tăng như một tín hiệu risk, không tự động kết luận credential bị clone.
- Không từ chối tất cả passkey chỉ vì counter bằng 0.
- Kết hợp risk signal, authenticator policy và hành vi account.

Không dùng counter như biện pháp replay protection duy nhất. Challenge one-time và signature verification mới là các kiểm soát cốt lõi của ceremony.

## 17. Xác minh account, tenant và policy

Sau khi cryptographic assertion hợp lệ, RP vẫn cần kiểm tra:

- Account có active không?
- Credential có thuộc đúng account không?
- User có quyền vào tenant/workspace đang chọn không?
- Có incident lock hoặc risk restriction không?
- Có yêu cầu step-up cho route/action tiếp theo không?
- Account có vừa đổi recovery method hoặc revoke toàn bộ session không?

Không coi passkey thành công là quyền truy cập mọi tenant. Nếu một user tham gia nhiều tổ chức, membership và role phải được kiểm tra riêng.

Nếu tenant được chọn sau login, chỉ lưu tenant context sau khi xác minh membership server-side. Không tin tenantId do browser gửi.

## 18. Tạo authenticated session

Chỉ sau khi toàn bộ kiểm tra passkey và account policy thành công, RP mới tạo authenticated session.

Các bước:

1. Consume challenge transaction.
2. Xác định principal và authentication context.
3. Rotate hoặc tạo session ID mới từ pre-auth state.
4. Ghi auth_time, phương thức xác thực và assurance theo semantics nội bộ.
5. Áp dụng idle và absolute timeout.
6. Lưu session state an toàn.
7. Phát cookie với Secure, HttpOnly, SameSite và scope phù hợp.
8. Ghi audit event thành công bằng metadata, không ghi cookie/assertion.
9. Điều hướng về trang đã được kiểm tra allowlist.

Passkey assertion thành công không tự động có nghĩa mọi action đều được step-up. Policy có thể yêu cầu reauthentication hoặc approval riêng cho thay đổi email, thêm authenticator hoặc chuyển tiền.

### Session cookie

Ví dụ minh họa:

~~~http
Set-Cookie: __Host-NS_SESSION=opaque-reference; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nếu dùng prefix __Host-, cookie phải có Secure, Path=/ và không có Domain. Cookie value là opaque bearer reference; không đưa vào log, URL hoặc analytics.

## 19. Luồng tổng thể

~~~mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant R as Northstar RP
    participant C as Challenge Store
    participant K as Credential Store
    participant S as Session Service
    U->>B: Select Sign in with passkey
    B->>R: POST /passkey/authentication/options
    R->>C: Create transaction + random challenge
    R-->>B: PublicKeyCredentialRequestOptions
    B->>U: Request authenticator verification
    U->>B: Approve with device verification
    B->>B: navigator.credentials.get()
    B->>R: POST assertion
    R->>C: Load pending transaction
    R->>K: Load credential public key/account mapping
    R->>R: Verify type, challenge, origin, RP ID, flags, signature
    R->>C: Atomically consume challenge
    R->>S: Create rotated authenticated session
    S-->>R: Session reference
    R-->>B: Set-Cookie + redirect
~~~

Nếu bất kỳ bước xác minh nào thất bại, RP không tạo authenticated session. Có thể ghi reason code nội bộ và request reference để điều tra.

## 20. Fallback và recovery

Northstar vẫn cần phương thức dự phòng cho trường hợp:

- User mất thiết bị hoặc không còn truy cập passkey provider.
- Platform không hỗ trợ WebAuthn.
- Browser không có credential phù hợp.
- Passkey bị remove hoặc revoke nhầm.
- User cần chuyển thiết bị.

Fallback policy:

- Ưu tiên passkey khác đã enroll.
- Có thể dùng authenticator TOTP đã đăng ký nếu risk/assurance policy cho phép.
- Recovery code chỉ dùng một lần và có giới hạn.
- Account recovery qua support cần identity proofing, approval và audit.
- Không tự động hạ xuống password-only cho account bắt buộc MFA hoặc đặc quyền.
- Thông báo cho user về việc thêm/xóa credential và thay đổi recovery method.

Không liên kết account chỉ vì email trong IdP mới giống email trong Northstar. Account linking cần chứng minh quyền kiểm soát cả hai danh tính và ghi audit.

Recovery là một đường authentication khác với assurance riêng. Nếu recovery yếu hơn passkey, attacker có thể bỏ qua passkey bằng cách tấn công recovery; vì vậy cần threat model recovery ngang mức quan trọng với login.

## 21. Threat scenarios và cách xử lý

| Tình huống | Nguy cơ | Kiểm soát |
|---|---|---|
| Phishing ở domain giả | Attacker muốn lấy proof đăng nhập | Origin/RP ID binding, passkey ceremony đúng domain |
| Challenge replay | Dùng assertion cũ | Challenge random, expiry và atomic one-time consume |
| Origin mismatch | Assertion từ origin ngoài allowlist | Exact origin validation |
| RP ID hash mismatch | Credential không thuộc RP dự kiến | Kiểm tra rpIdHash |
| Signature sai | Assertion giả hoặc payload bị sửa | Verify bằng stored public key |
| Credential đã revoke | Credential cũ tiếp tục đăng nhập | Check status server-side |
| User handle bị sửa | Liên kết sai account | Kiểm tra credential mapping và userHandle |
| Tenant ID bị sửa | Cross-tenant access | Membership/authorization server-side |
| Session fixation | Attacker biết session trước login | Rotate session ID sau authentication |
| Assertion gửi hai lần đồng thời | Hai session được tạo từ một challenge | Atomic consume và idempotency |
| Counter không tăng | Có thể là clone hoặc passkey sync behavior | Risk signal theo authenticator semantics |
| Recovery abuse | Bỏ qua passkey bằng recovery yếu | Strong proofing, one-time grant, approval và notification |

## 22. Lỗi thường gặp trong triển khai

1. Chỉ kiểm tra chữ ký mà bỏ qua challenge, origin hoặc RP ID hash.
2. So origin bằng substring hoặc lấy expected origin từ request header không đáng tin.
3. Tin username/user ID do browser gửi trong usernameless flow.
4. Chấp nhận userHandle không khớp credential mapping.
5. Không kiểm tra UV dù policy yêu cầu.
6. Dùng signature counter làm replay defense duy nhất.
7. Không consume challenge atomically.
8. Tạo session trước khi account status và credential status được kiểm tra.
9. Không rotate session ID sau login.
10. Coi passkey authentication là authorization cho mọi tenant/resource.
11. Log raw assertion, cookie hoặc WebAuthn payload.
12. Fallback tự động sang password yếu hơn khi authenticator timeout.
13. Cho phép redirect URL tùy ý sau login.
14. Liên kết account dựa trên email trùng mà không xác minh ownership.

## 23. Java/Spring: mô hình transaction và credential

Ví dụ domain model tối giản:

~~~java
enum WebAuthnTransactionStatus {
    PENDING, CONSUMED, EXPIRED, CANCELLED
}

record WebAuthnLoginTransaction(
    UUID id,
    byte[] challenge,
    String rpId,
    String preAuthSessionRef,
    Instant expiresAt,
    WebAuthnTransactionStatus status
) {}

record PasskeyCredential(
    String credentialId,
    UUID accountId,
    byte[] publicKey,
    String algorithm,
    String rpId,
    String opaqueUserHandle,
    boolean active,
    long signatureCounter
) {}
~~~

Đây là ví dụ cấu trúc. Production cần bảo vệ serialization, giới hạn kích thước input, dùng loại byte/encoding phù hợp, không log challenge/public key blob tùy tiện và quản lý schema/version khi thay thư viện.

## 24. Java/Spring: service orchestration

Pseudocode cho backend:

~~~java
@Service
class PasskeyLoginService {
    private final ChallengeRepository challenges;
    private final PasskeyCredentialRepository credentials;
    private final WebAuthnVerifier verifier;
    private final AccountPolicy accountPolicy;
    private final SessionIssuer sessions;
    private final SecurityAudit audit;

    LoginResult finish(
            String transactionId,
            WebAuthnAssertion assertion,
            RequestOrigin requestOrigin) {

        WebAuthnLoginTransaction tx =
            challenges.requirePending(transactionId);

        PasskeyCredential credential =
            credentials.requireActive(assertion.credentialId());

        VerificationResult result = verifier.verify(
            assertion,
            tx.challenge(),
            tx.rpId(),
            requestOrigin,
            credential.publicKey()
        );

        if (!result.valid()) {
            audit.passkeyLoginDenied(
                credential.credentialId(),
                result.reasonCode()
            );
            throw new AuthenticationException();
        }

        accountPolicy.requireLoginAllowed(credential.accountId());
        challenges.consumeAtomically(tx.id());

        SessionReference session = sessions.createRotated(
            credential.accountId(),
            result.authenticationContext()
        );

        audit.passkeyLoginSucceeded(
            credential.credentialId(),
            session.reference()
        );
        return LoginResult.authenticated(session);
    }
}
~~~

Đây là pseudocode định hướng, không phải verifier WebAuthn hoàn chỉnh. Thứ tự thực tế cần bảo đảm challenge consume, account status, session creation và audit có transaction/idempotency semantics rõ. Có thể cần consume challenge trước session issuance sau khi signature hợp lệ để chống replay; nếu session creation lỗi sau consume, client phải khởi tạo transaction mới thay vì replay assertion cũ.

RequestOrigin phải được lấy từ context đã chuẩn hóa và cấu hình trusted proxy phù hợp. Không cho client gửi một giá trị tùy ý để tự quyết định expected origin.

## 25. Java/Spring: endpoint options và finish

Một API contract có thể tách hai endpoint:

~~~http
POST /api/auth/passkey/options
Content-Type: application/json

{}
~~~

~~~http
POST /api/auth/passkey/finish
Content-Type: application/json

{
  "transactionId": "opaque-transaction-reference",
  "credential": {
    "id": "base64url-credential-id",
    "type": "public-key",
    "response": {
      "clientDataJSON": "base64url-data",
      "authenticatorData": "base64url-data",
      "signature": "base64url-signature",
      "userHandle": "base64url-user-handle"
    }
  }
}
~~~

API contract cần:

- Giới hạn body size và field lengths.
- Parse base64url nghiêm ngặt.
- Chống transaction ID guessing/rate abuse.
- Không trả thông tin account existence.
- Không log body raw.
- Xác minh CSRF nếu endpoint dựa trên cookie pre-auth session.
- Chỉ phát authenticated cookie sau khi assertion hợp lệ.

## 26. Observability và audit

Northstar theo dõi:

### Metrics

- Passkey options requested.
- Assertion validation success/denied/error.
- Challenge expired/replay detected.
- WebAuthn verification latency.
- User cancellation và timeout aggregate.
- Credential not found aggregate.
- Session creation result.
- Fallback method usage.

### Audit events

- Passkey login success/denied.
- Credential status changed.
- Credential added/removed.
- Account recovery started/completed.
- Step-up requested/completed.
- Session created/revoked.
- Policy or RP configuration changed.

### Privacy

- Không log raw assertion, challenge, signature, cookie hoặc session ID.
- Dùng opaque account/credential references trong audit.
- Không đưa credential ID hoặc user ID vào metric labels có cardinality cao.
- Giới hạn quyền đọc device metadata.
- Có retention riêng cho security audit và diagnostic event.

Metrics giúp nhận diện xu hướng; audit event có access control phục vụ điều tra. Không dùng một hệ thống metric để lưu từng authentication transaction.

## 27. Rollout theo giai đoạn

Northstar triển khai theo các giai đoạn:

### Giai đoạn 1: Compatibility

- Xác minh browser/platform support.
- Chọn RP ID và origin ổn định.
- Kiểm thử passkey registration/login trên các platform mục tiêu.
- Thiết lập credential store và backup/restore policy.

### Giai đoạn 2: Pilot

- Mời nhóm nhân viên và khách hàng thử nghiệm.
- Theo dõi success/cancel/error rate.
- Kiểm tra recovery và support workflow.
- Thu thập phản hồi mà không thu raw credential data.

### Giai đoạn 3: Optional enrollment

- Cho phép user đăng ký passkey sau khi reauthenticate.
- Gửi notification khi credential mới được thêm.
- Hiển thị danh sách passkey metadata để user quản lý.
- Cho phép revoke credential bị mất.

### Giai đoạn 4: Preferred sign-in

- Đặt passkey là lựa chọn ưu tiên.
- Giữ fallback đã được risk-assess.
- Step-up cho action nhạy cảm.
- Theo dõi nhóm user chưa có passkey để tránh khóa ngoài ý muốn.

### Giai đoạn 5: Policy tightening

- Giảm phụ thuộc password theo cohort.
- Có thể yêu cầu passkey cho nhóm rủi ro/đặc quyền nếu recovery đã đủ mạnh.
- Đánh giá password disable chỉ khi migration, support và recovery sẵn sàng.

Không ép toàn bộ người dùng chuyển đổi trước khi kiểm chứng accessibility, device compatibility, account recovery và support capacity.

## 28. Ma trận kiểm thử

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Assertion hợp lệ, credential active | Login thành công và tạo session mới |
| Challenge sai | Từ chối |
| Challenge hết hạn | Từ chối |
| Challenge đã consume | Từ chối replay |
| Hai request cùng consume challenge | Chỉ một request thành công |
| clientDataJSON.type không phải webauthn.get | Từ chối |
| Origin không nằm trong allowlist | Từ chối |
| Origin chỉ gần giống domain thật | Từ chối |
| RP ID hash sai | Từ chối |
| Signature sai | Từ chối |
| Credential ID không tồn tại | Login thất bại chung |
| Credential đã revoke | Từ chối |
| Account disabled | Từ chối |
| User handle không khớp mapping | Từ chối |
| UV thiếu khi policy yêu cầu | Từ chối |
| UP thiếu khi policy yêu cầu | Từ chối |
| Algorithm không được hỗ trợ | Từ chối |
| Authenticator counter bằng 0 với passkey sync | Xử lý theo policy, không tự động kết luận clone |
| Session ID trước login được tái sử dụng | Không được chấp nhận sau authentication |
| Session creation lỗi sau challenge consume | Không cho replay assertion; transaction mới được yêu cầu |
| Tenant ID bị client sửa | Không đổi tenant authorization |
| Redirect URL ngoài allowlist | Từ chối hoặc dùng default safe route |
| Browser user cancel | Không tạo authenticated session |
| Authenticator timeout | Không tạo session; có retry path hợp lý |
| Recovery code đã dùng | Từ chối reuse |
| Fallback password cho account bắt buộc passkey/MFA | Không downgrade ngoài policy |
| Assertion gửi vào log | Secret/privacy scanner phát hiện |
| Credential mới được enroll | Audit và notification được tạo |
| Credential bị remove | Credential không thể login tiếp |
| Multi-tenant user | Chỉ truy cập tenant có membership |
| Concurrent login | Session policy được thực thi đúng |

## 29. Tình huống sự cố và quyết định

### Tình huống A: User đổi thiết bị và không thấy passkey

User chọn passkey nhưng browser không hiển thị credential.

**Phân tích:** Có thể user dùng profile/browser khác, passkey provider chưa đồng bộ hoặc credential không discoverable. Hướng dẫn chọn passkey khác đã enroll hoặc recovery đã xác minh. Không tiết lộ account có credential nào.

### Tình huống B: Origin mismatch sau đổi domain

Đội web đổi login domain từ login.northstar.example sang auth.northstar.example, nhưng RP configuration chưa cập nhật.

**Phân tích:** Assertion phải bị từ chối vì origin/RP ID mismatch. Cần kế hoạch domain migration, credential compatibility và thông báo người dùng; không nới origin check thành wildcard.

### Tình huống C: Challenge bị gửi hai lần

Browser retry request finish sau timeout và hai backend node cùng nhận assertion.

**Phân tích:** Atomic challenge consumption bảo đảm chỉ một request thành công. Nếu request đầu đã tạo session nhưng response bị mất, transaction/idempotency record cho phép xử lý kết quả an toàn mà không chấp nhận assertion như một login mới.

### Tình huống D: Signature counter không tăng

Một user dùng passkey đồng bộ trên nhiều thiết bị và server thấy counter bằng 0.

**Phân tích:** Không coi đây là bằng chứng chắc chắn credential clone. Áp dụng semantics của authenticator, kết hợp risk signals và các kiểm soát replay challenge.

### Tình huống E: Passkey login thành công nhưng user truy cập tenant khác

User có membership trong tenant A và tenant B. Sau login, browser gửi tenant B dù user hiện chỉ được cấp quyền ở A.

**Phân tích:** Authentication xác minh principal; authorization kiểm tra membership và action theo tenant. Không tin tenant ID từ client.

### Tình huống F: Support muốn bỏ qua passkey

Người dùng gọi support vì mất thiết bị. Nhân viên đề nghị tắt passkey ngay sau khi xác minh email.

**Phân tích:** Email đơn lẻ có thể không đủ proof. Recovery phải có assurance, approval, delay/notification khi phù hợp và audit. Việc xóa credential cũ cần kiểm tra account ownership và các factor còn lại.

## 30. Quy trình thiết kế và vận hành

Trước khi đưa passkey login vào production, hãy xác định:

1. RP ID, allowed origins và domain migration plan là gì?
2. Dùng discoverable credential hay username-first flow?
3. Credential registration đã xác minh account ownership và user handle chưa?
4. Challenge có CSPRNG, expiry, purpose binding và atomic one-time consumption không?
5. Backend có kiểm tra type, challenge, origin, RP ID hash, UP/UV và signature không?
6. Credential ID/public key/account mapping có integrity và lifecycle rõ không?
7. Account state, tenant membership và risk policy được kiểm tra ở đâu?
8. Session có được tạo sau khi mọi validation hoàn tất và rotate ID không?
9. Cookie, CSRF, idle/absolute timeout và logout được cấu hình thế nào?
10. Signature counter được diễn giải phù hợp với synced passkey không?
11. Fallback/recovery có assurance đủ mạnh và không tạo bypass không?
12. Account linking yêu cầu proof of control cho cả hai identity không?
13. Metrics/audit có tránh raw assertion, challenge, cookie và credential ID labels không?
14. Có test replay, origin mismatch, UV, concurrent consume và tenant isolation không?
15. Rollout có pilot, compatibility, support và rollback plan không?

## 31. Ghi nhớ trọng tâm

- **Passkey login là một WebAuthn authentication ceremony.** RP tạo challenge, authenticator ký proof và backend xác minh assertion.
- **Phishing resistance đến từ RP ID/origin binding.** Không thay exact origin validation bằng substring hoặc wildcard tùy tiện.
- **Private key ở authenticator; server lưu public key.** Không gửi hoặc lưu private key passkey ở backend.
- **Usernameless không có nghĩa tin user ID từ client.** Xác định account bằng credential registry và user handle mapping đã xác minh.
- **Challenge phải ngẫu nhiên, transaction-bound, hết hạn và consume một lần nguyên tử.**
- **Kiểm tra type, challenge, origin, RP ID hash, flags và signature.** Chỉ kiểm tra chữ ký là chưa đủ.
- **UP và UV khác nhau.** Nếu policy yêu cầu user verification, backend phải kiểm tra UV flag.
- **Signature counter không phải replay defense duy nhất.** Synced passkey có thể không tăng counter theo cách truyền thống.
- **Authentication không thay authorization.** Tenant membership, role và object permission vẫn phải được kiểm tra.
- **Fallback/recovery là một phần của threat model.** Đường dự phòng yếu có thể vô hiệu hóa lợi ích phishing resistance.
- **Session chỉ được cấp sau khi assertion và account policy hợp lệ.** Rotate session ID và bảo vệ cookie.
- **Không log raw assertion hoặc cookie.** Dùng audit metadata và metrics có cardinality thấp.

Case study cho thấy triển khai passkey thành công đòi hỏi phối hợp browser, authenticator, RP backend, credential store, account policy và session service. Khi challenge được ràng buộc đúng transaction, assertion được xác minh đầy đủ, account/tenant được kiểm tra riêng và recovery được bảo vệ tương xứng, passkey có thể giảm đáng kể rủi ro phishing mà vẫn duy trì khả năng vận hành và hỗ trợ người dùng.
