# Credential policy test (Kiểm thử chính sách credential)

> **Chương:** Testing  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Kiểm chứng các chính sách quản lý và sử dụng credential trên toàn bộ vòng đời; kiểm tra yêu cầu tạo, lưu trữ, xác minh, enrollment, sử dụng, rotation, recovery và revocation đối với password, MFA, passkey, certificate, API key, token, session và workload identity; phát hiện policy bypass, cấu hình không nhất quán và đường fallback yếu.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích credential policy test và phân biệt với kiểm thử một luồng login đơn lẻ.
2. Chuyển chính sách credential thành yêu cầu có thể kiểm thử và tiêu chí chấp nhận.
3. Xây dựng ma trận kiểm thử theo loại credential, principal, assurance level và trạng thái vòng đời.
4. Kiểm tra password policy, password blocklist, password hashing và thay đổi verifier.
5. Kiểm thử MFA, passkey, certificate, API key, token và session theo policy tương ứng.
6. Xác minh credential enrollment, rotation, recovery, disable và revocation nhất quán giữa các endpoint.
7. Phát hiện fallback yếu, policy downgrade, credential reuse, replay và privilege escalation.
8. Thiết kế positive, negative, boundary, concurrency, resilience và regression test.
9. Tự động hóa kiểm thử bằng fixture an toàn, API test, integration test và browser test.
10. Đánh giá finding theo khả năng khai thác, phạm vi ảnh hưởng và mức assurance bị suy giảm.

## 1. Credential policy test là gì?

**Credential policy test (kiểm thử chính sách credential)** là quá trình xác minh hệ thống thực thi đúng các quy tắc quy định cách credential được tạo, lưu trữ, xác minh, sử dụng, thay đổi, khôi phục và thu hồi.

Credential có thể là password, passkey, OTP authenticator, certificate, API key, client secret, private key, access token, refresh token hoặc session credential. Mỗi loại có vòng đời, đặc tính và rủi ro riêng. Một policy chỉ an toàn khi mọi đường đi có thể sử dụng credential đều tuân thủ quy tắc tương ứng.

Ví dụ, hệ thống quy định:

- Password phải đạt yêu cầu độ dài và bị từ chối nếu nằm trong blocklist.
- Tài khoản đặc quyền phải dùng MFA phishing-resistant.
- Passkey registration cần một phiên đã xác thực đủ assurance.
- Client certificate phải còn hiệu lực và có identity mapping hợp lệ.
- API key chỉ được dùng trong scope, tenant và thời hạn đã cấp.
- Access token phải đúng issuer, audience, thời hạn và token profile.
- Session bị revoke phải không thể tiếp tục truy cập.
- Recovery không được trở thành đường bỏ qua MFA.

Credential policy test xác minh các quy tắc đó ở cả luồng chính, endpoint phụ, API nội bộ, job nền và các tình huống lỗi.

### Policy test khác login test

Login test có thể chỉ xác minh username/password đúng thì đăng nhập thành công. Credential policy test còn kiểm tra:

- Password có được tạo và lưu đúng không?
- Credential bị compromised có bị từ chối không?
- Enrollment/removal có cần step-up không?
- Factor yếu có thể thay thế factor mạnh ngoài policy không?
- Token có thể được dùng ở sai audience không?
- Credential đã revoke có còn hoạt động ở node khác không?
- Recovery, support và legacy endpoint có áp dụng cùng policy không?

Mục tiêu là xác minh policy được thực thi xuyên suốt hệ thống, không chỉ tại màn hình login.

## 2. Phân biệt credential, authenticator, identity và authorization

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Identity** | Chủ thể được hệ thống biểu diễn. | User subject, workload principal. |
| **Credential** | Bằng chứng hoặc vật liệu bí mật dùng để chứng minh quyền kiểm soát. | Password, private key, API key. |
| **Authenticator** | Thiết bị/phần mềm hoặc cơ chế tạo bằng chứng xác thực. | Passkey authenticator, TOTP app, security key. |
| **Authentication policy** | Quy định credential/factor nào được chấp nhận trong ngữ cảnh nào. | Admin cần phishing-resistant MFA. |
| **Authentication assurance** | Mức tin cậy của quy trình xác thực theo policy/profile. | Step-up gần đây với user verification. |
| **Authorization** | Quyết định principal được làm gì trên resource nào. | User được đọc hồ sơ thuộc tenant của mình. |

Một credential hợp lệ không tự cấp quyền truy cập mọi resource. Ngược lại, một user có role phù hợp vẫn không được bỏ qua yêu cầu xác thực khi credential hoặc session không đáp ứng policy.

### Không gộp các yếu tố khác bản chất

Hai password khác nhau vẫn thuộc cùng loại factor knowledge. Password cộng với một câu hỏi bí mật không nhất thiết tạo MFA độc lập. Việc kiểm thử phải xác minh factor thực sự khác loại và độc lập theo thiết kế, không chỉ đếm số bước giao diện.

## 3. Xác định phạm vi và tài sản kiểm thử

Trước khi viết test case, lập bản đồ nơi credential được tạo, xác minh, lưu, truyền và thu hồi.

~~~mermaid
flowchart TD
    U["User / workload identity"] --> E["Enrollment and provisioning"]
    E --> C["Credential store / key store"]
    U --> A["Authentication endpoint"]
    C --> A
    A --> P["Policy evaluation"]
    P --> S["Session / token issuance"]
    S --> R["Resource API"]
    A --> V["Recovery / rotation / revoke"]
    V --> C
    V --> S
    A --> L["Audit and security events"]
    V --> L
~~~

### Tài sản cần xem xét

- Password verifier, salt và pepper reference.
- Passkey credential ID, public key và authenticator metadata.
- TOTP seed, OTP challenge state và recovery code.
- Certificate, trust bundle, private key reference và revocation state.
- API key verifier, key ID, scope, owner và expiry.
- OAuth client credential, access token và refresh-token family.
- Session identifier, session store và device binding.
- Workload identity, service account và role mapping.
- Recovery email/phone và support approval.
- Policy configuration, exception, allowlist và version.
- Audit event, policy decision và test evidence.

### Phạm vi phải ghi rõ

- Environment: local, test, staging hoặc production được phê duyệt.
- Principal: user thường, admin, service, partner, tenant.
- Credential type và authentication method.
- Endpoint, API, UI, background job và legacy path.
- Policy version, feature flag và configuration source.
- Data classification và tác động nếu test thất bại.

Không chạy test phá hủy, brute force tải lớn hoặc revoke hàng loạt trên production nếu không có phê duyệt, giới hạn và kế hoạch khôi phục.

## 4. Chuyển policy thành yêu cầu có thể kiểm thử

Policy viết bằng ngôn ngữ tự nhiên thường mơ hồ. Hãy chuyển thành điều kiện, phạm vi và expected result cụ thể.

### Ví dụ chuyển đổi

| Policy statement | Điều kiện kiểm thử | Expected result |
| --- | --- | --- |
| Admin phải dùng phishing-resistant MFA. | Admin chỉ có password hoặc password + SMS. | Không được hoàn tất login đặc quyền; yêu cầu factor được chấp nhận. |
| API key có expiry. | Dùng key trước và sau thời điểm hết hạn. | Trước expiry được phép theo scope; sau expiry bị từ chối. |
| Password nằm trong blocklist bị cấm. | Đặt password test thuộc danh sách bị cấm. | Server từ chối và không lưu verifier mới. |
| Session revoke phải có hiệu lực. | Dùng session reference sau khi revoke. | API từ chối request theo SLA. |
| Certificate phải có đúng purpose. | Dùng certificate sai EKU hoặc SAN mapping. | Authentication bị từ chối. |
| Recovery không bypass MFA. | Dùng recovery flow để thay factor cho admin. | Yêu cầu assurance/approval theo policy. |

### Mỗi policy cần các thuộc tính

- Policy ID và version.
- Principal/role/tenant áp dụng.
- Credential type.
- Preconditions và exception.
- Enforcement point.
- Expected deny/allow behavior.
- Audit event cần phát sinh.
- Owner và thời điểm hiệu lực.
- Test ID và evidence.
- Cách xử lý khi dependency unavailable.

Không chỉ kiểm thử policy engine. Cần xác minh mọi endpoint và service thật sự gọi policy đúng version.

## 5. Ma trận credential policy

Một ma trận giúp phát hiện vùng chưa có test hoặc chỉ được test qua một đường truy cập.

| Credential | Create/enroll | Verify/use | Rotate/change | Revoke/recover |
| --- | --- | --- | --- | --- |
| Password | Strength, blocklist, confirmation. | Correct/incorrect, rate limit. | Change, history, reset. | Disable/reset và session response. |
| TOTP/push MFA | Bind đúng account và challenge. | Valid, invalid, expired, replay. | Re-enroll, factor replacement. | Remove, recovery và audit. |
| Passkey | Challenge, origin, RP ID, user verification. | Assertion signature và challenge. | Add/remove credential. | Revoke, lost device recovery. |
| Certificate | Issuer, SAN, EKU, key binding. | Chain, expiry, revocation. | Renew, key rollover. | Revoke và trust update. |
| API key/client secret | Entropy, owner, scope. | Scope, tenant, expiry. | Overlap rotation. | Revoke và usage review. |
| Access/refresh token | Issuance policy. | Issuer, audience, scope, time. | Refresh/rotation. | Grant/session revoke. |
| Session | Session creation and cookie policy. | Binding, timeout, access. | Rotate/renew. | Logout, revoke, global sign-out. |
| Workload identity | Provisioning/attestation. | Principal and audience. | Certificate/token renewal. | Deprovision and deny. |
| Recovery credential | Channel verification and issuance. | One-time and purpose-bound. | Regenerate/change channel. | Consume, expire, revoke. |

## 6. Thiết kế test case và test oracle

Một test case cần cho biết điều kiện đầu, hành động, kết quả mong đợi và bằng chứng.

### Cấu trúc test case

| Trường | Nội dung |
| --- | --- |
| Test ID | Định danh ổn định. |
| Policy ID/version | Quy tắc đang kiểm tra. |
| Principal fixture | User/service/role/tenant giả lập. |
| Credential fixture | Credential test và trạng thái. |
| Preconditions | Account, session, policy và dependency state. |
| Steps | Các thao tác theo thứ tự. |
| Expected result | Allow, deny, challenge hoặc state transition. |
| Security invariant | Điều kiện không được vi phạm. |
| Evidence | Response đã redact, event ID, audit reference. |
| Cleanup | Revoke fixture, xóa session và reset state. |

### Test oracle

Test oracle là tiêu chí xác định kết quả đúng. Ví dụ, sau khi revoke API key:

- API request bằng key cũ bị từ chối.
- Key mới hoạt động theo scope đã cấp.
- Audit ghi revoke thành công.
- Usage counter của key cũ không tăng do request bị chặn.
- Các replica không tiếp tục chấp nhận key cũ ngoài revocation SLA.

Chỉ kiểm tra HTTP status là chưa đủ nếu cần xác minh state, audit và downstream behavior.

## 7. Kiểm thử password policy

Password policy cần cân bằng khả năng chống đoán với khả năng sử dụng và hỗ trợ password manager.

### Các điều kiện nên kiểm thử

- Độ dài tối thiểu/tối đa theo policy.
- Unicode, ký tự đặc biệt, khoảng trắng và normalization.
- Password dài được xử lý mà không bị truncate âm thầm.
- Blocklist chứa password phổ biến hoặc đã biết bị lộ.
- Password mới không được trùng password hiện tại nếu policy cấm.
- Password confirmation không tạo side channel.
- Password reset/change yêu cầu xác minh đủ mạnh.
- Rate limit cho password verification.
- Account disabled/suspended không thể xác thực chỉ nhờ password đúng.
- Password change được áp dụng nhất quán ở API, web và mobile.

### Độ dài và thành phần

Không nên kiểm thử theo giả định mọi password phải có một bộ ký tự viết hoa, số và ký hiệu cố định nếu policy hiện hành không yêu cầu. Hãy xác minh yêu cầu thực tế, ưu tiên độ dài, blocklist, password manager support và chống guessing.

Giới hạn tối đa phải đủ lớn để không cản passphrase hợp lệ nhưng cũng phải chống request quá dài gây tiêu thụ tài nguyên. Test các giá trị sát boundary và Unicode encoding.

### Expiration

Không mặc định password phải đổi định kỳ nếu không có dấu hiệu compromise hoặc yêu cầu policy cụ thể. Nếu tổ chức có expiration, kiểm tra cảnh báo, grace period, reset flow, session handling và khả năng tránh lockout ngoài ý muốn.

## 8. Kiểm thử password verifier và lưu trữ

Password verifier cần dùng password hashing chuyên dụng, salt riêng và cấu hình phù hợp với threat model.

### Kiểm thử

- Password không lưu plaintext hoặc reversible encryption.
- Mỗi password có salt riêng.
- Dùng password hashing phù hợp như Argon2id hoặc lựa chọn đã được tổ chức phê duyệt.
- Cost/work factor được cấu hình và có thể nâng cấp.
- Pepper nếu sử dụng được quản lý tách khỏi database.
- Không ghi password hoặc verifier nhạy cảm vào log/trace.
- Timing và error response không tiết lộ password correctness ngoài policy.
- Password change tạo verifier mới và không làm mất account mapping.
- Migration từ thuật toán cũ không hạ cost hoặc giữ verifier yếu vô thời hạn.
- Backup/restore giữ được khả năng xác minh mà không lộ pepper/key.

### Kiểm thử migration

Một số hệ thống nâng cấp verifier sau khi người dùng đăng nhập thành công. Test cần xác minh:

1. Password đúng với verifier cũ được chấp nhận.
2. Sau xác thực, verifier được nâng cấp theo policy.
3. Password sai không kích hoạt rehash.
4. Hai login đồng thời không ghi đè verifier mới bằng verifier cũ.
5. Lỗi KMS/pepper provider có behavior fail policy rõ.

Không tự viết thuật toán password hashing trong test harness. Dùng implementation đã được kiểm chứng và fixture riêng.

## 9. Kiểm thử MFA policy

MFA policy cần xác định factor được chấp nhận theo principal, transaction và risk.

### Enrollment

- Chỉ account đã được xác minh mới thêm factor.
- Enrollment yêu cầu authentication context phù hợp.
- Challenge gắn đúng user, session và transaction.
- Factor mới không tự nâng quyền trước khi xác minh.
- Thêm hoặc xóa factor tạo audit event.
- Admin account không thể chọn fallback yếu hơn policy.

### Verification

- OTP đúng, sai, hết hạn và đã dùng.
- Push approve, deny, timeout và challenge replay.
- Number matching/context được kiểm tra nếu triển khai.
- Giới hạn retry và resend.
- Không chấp nhận OTP của account khác.
- Không hoàn tất login khi factor bắt buộc thất bại.
- Concurrent request không consume một challenge nhiều lần.

### Factor independence

Password + security question vẫn là hai yếu tố cùng nhóm knowledge. Test policy phải xác minh factor thuộc nhóm hoặc profile được chấp nhận, thay vì chỉ đếm số màn hình.

### Fallback

- Fallback có yêu cầu assurance tương đương hoặc được policy cho phép.
- SMS/email OTP không âm thầm thay thế phishing-resistant MFA cho admin.
- Recovery code one-time và có thể revoke/regenerate.
- Support override có approval, expiry và audit.
- Không có legacy endpoint bỏ qua MFA.

## 10. Kiểm thử passkey và WebAuthn policy

Passkey policy phải kiểm tra registration, authentication, lifecycle và account recovery.

### Registration

- Challenge mới, ngẫu nhiên và có thời hạn.
- Origin khớp RP origin đã cấu hình.
- RP ID hash đúng.
- Registration gắn với đúng account đã xác thực.
- Public key và credential ID được lưu đúng subject.
- User verification đáp ứng policy.
- Attestation được xử lý theo policy; không mặc định mọi attestation đều phải được tin.
- Duplicate credential và credential format sai bị xử lý an toàn.
- Enrollment event và notification được phát sinh.

### Authentication

- Assertion signature hợp lệ.
- Challenge chưa dùng và chưa hết hạn.
- Origin/RP ID đúng.
- Credential thuộc account hoặc discoverable flow được xử lý theo policy.
- User presence/user verification đúng yêu cầu.
- Assertion replay bị từ chối.
- Credential đã revoke không được chấp nhận.
- Credential counter được diễn giải theo loại authenticator/profile; không coi giá trị bằng 0 tự động là bằng chứng clone.

### Policy downgrade

Nếu account yêu cầu passkey hoặc phishing-resistant factor, test các đường password-only, email link, support reset và legacy login. Mọi đường fallback phải tuân thủ policy đã định nghĩa.

## 11. Kiểm thử certificate policy

Certificate có thể xác thực workload, client hoặc người dùng tùy kiến trúc. Cần kiểm tra cả PKI validation lẫn mapping identity.

### Certificate validation

- Chain tới CA được tin cậy.
- Validity period và clock skew.
- Subject Alternative Name (SAN) mapping.
- Extended Key Usage (EKU) phù hợp mục đích.
- Key usage và key algorithm theo policy.
- Revocation qua CRL/OCSP hoặc cơ chế trạng thái tương ứng.
- Issuer và trust domain đúng environment.
- Certificate không được dùng nhầm giữa staging và production.

### Lifecycle

- Provisioning certificate cho đúng workload.
- Private key được bảo vệ và không export ngoài policy.
- Renewal trước expiry.
- Key rotation và overlap.
- Revoke certificate bị compromise.
- Xác minh connection/token cũ không còn được chấp nhận theo SLA.
- Audit ghi issuer, serial/fingerprint reference và action mà không log private key.

### Negative tests

Dùng certificate hết hạn, sai SAN, sai EKU, chain không tin cậy, revoked và certificate của workload khác. Expected result là từ chối ở đúng trust boundary.

## 12. Kiểm thử API key và client secret policy

API key thường là bearer secret; client secret cũng cần được bảo vệ như credential.

### Creation

- Entropy đủ theo thiết kế.
- Key ID tách khỏi secret value.
- Secret chỉ hiển thị theo cơ chế an toàn.
- Owner, purpose, environment, tenant và scope được ghi nhận.
- Expiry/rotation policy rõ.
- Secret verifier được lưu phù hợp, không cần lưu plaintext nếu thiết kế cho phép hash.

### Usage

- Chỉ endpoint và scope đã cấp được phép.
- Tenant/resource được kiểm tra.
- Key hết hạn hoặc disabled bị từ chối.
- Rate limit theo client/key.
- Không truyền key qua URL/query string.
- Không log secret hoặc authorization header.
- Không chấp nhận key của environment khác.

### Rotation và revoke

- Key mới được tạo trước khi key cũ hết hạn nếu có overlap.
- Client chuyển sang key mới.
- Usage của key cũ được theo dõi.
- Revoke key cũ làm request mới bị từ chối.
- Secret xuất hiện trong repository/log phải được coi là compromise.
- Owner được thông báo qua kênh tin cậy khi key bị revoke.

## 13. Kiểm thử access token và refresh token policy

Token policy xác định issuer, audience, scope, thời hạn, binding và vòng đời grant.

### Access token

- Signature hoặc introspection được xác minh.
- Issuer chính xác.
- Audience đúng resource server.
- Exp/nbf và clock skew theo policy.
- Token type/profile phù hợp.
- Scope đủ cho action nhưng không rộng quá mức.
- Tenant/resource context được xác minh.
- ID token không bị dùng thay access token.
- Sender constraint được kiểm tra nếu token bound với certificate/DPoP key.

### Refresh token

- Gắn đúng client/session/user theo grant.
- Rotation hoạt động theo policy.
- Reuse detection phát hiện token cũ đã rotate.
- Revocation của family có hiệu lực.
- Expiry và inactivity timeout được thực thi.
- Client không thể refresh grant đã bị disable.
- Token không xuất hiện trong log hoặc URL.

### Policy consistency

API Gateway và resource server không được có cách hiểu khác nhau về issuer, audience hoặc scope. Test trực tiếp từng resource server và đường bypass gateway nếu kiến trúc cho phép.

## 14. Kiểm thử session credential policy

Session ID/cookie là credential bearer trong nhiều web application.

### Cookie policy

- Secure chỉ gửi qua HTTPS.
- HttpOnly hạn chế JavaScript đọc cookie.
- SameSite phù hợp flow.
- Domain/Path tối thiểu.
- Prefix __Host- hoặc __Secure- nếu điều kiện sử dụng đáp ứng.
- Không đưa session ID vào URL.
- Không lưu raw cookie trong log/trace.

### Session lifecycle

- Session ID rotate sau login và step-up phù hợp.
- Anonymous session cũ không được dùng như authenticated session.
- Idle timeout và absolute timeout được thực thi.
- Logout revoke ở server-side.
- Password reset hoặc account suspension xử lý session theo policy.
- Session concurrency/device limit hoạt động đúng.
- Session cũ bị từ chối sau revoke trong SLA.
- Refresh/renew không kéo dài session vượt policy.

### Boundary test

Test thời điểm ngay trước, đúng và ngay sau expiry; clock skew; nhiều request đồng thời; session store outage; node cache cũ; logout lặp và back-button behavior.

## 15. Kiểm thử workload identity và service credential policy

Workload identity cần được kiểm tra như một principal riêng, không dùng chung với user identity.

### Provisioning và attestation

- Workload chỉ nhận identity từ platform/provider được tin cậy.
- Subject, namespace, service account và environment được allowlist.
- Pod/workload giả mạo không lấy được identity.
- Token/certificate có audience đúng service.
- Identity của dev/staging không được chấp nhận ở production.
- Workload decommission làm credential bị revoke.

### Usage

- Service chỉ gọi API trong allowlist.
- Scope không vượt nhiệm vụ.
- Secret manager chỉ cấp secret đúng workload.
- mTLS peer identity được xác minh.
- Token exchange giữ subject/actor và không nâng quyền.
- Credential rotation không tạo khoảng trống xác thực.

### Negative test

Thử workload sai namespace, service account, issuer, audience, certificate hoặc deployment identity. API phải từ chối và phát audit event phù hợp.

## 16. Kiểm thử recovery và credential replacement

Recovery là một phần của credential policy, không phải chức năng hỗ trợ tách biệt.

### Password recovery

- Reset token đủ entropy, TTL ngắn và one-time.
- Token gắn đúng account và purpose.
- Token đã dùng/hết hạn bị từ chối.
- Reset request không tiết lộ account existence.
- Password mới tuân thủ policy và blocklist.
- Session/token cũ được xử lý theo policy.
- Notification được gửi tới channel đã xác minh.

### MFA/passkey recovery

- Recovery proof phù hợp assurance của account.
- Không tự động bỏ MFA cho admin chỉ bằng email/phone yếu.
- Recovery code one-time và có thể regenerate.
- Thay đổi recovery method yêu cầu step-up/approval theo policy.
- Support override có audit, owner và expiry.
- Authenticator cũ được revoke khi thay thế theo policy.
- Người dùng nhận notification qua channel đã đăng ký trước.

### Recovery không được là đường bypass

Test tất cả endpoint support, legacy, mobile và admin. Một policy mạnh ở login nhưng yếu ở helpdesk reset vẫn có thể dẫn tới account takeover.

## 17. Kiểm thử policy consistency và bypass

Một policy có thể được thực thi ở UI nhưng bị bỏ qua qua API hoặc endpoint cũ.

### Các đường cần kiểm tra

- Web login và mobile login.
- API login và token endpoint.
- Password reset/change.
- MFA enrollment/removal.
- Passkey registration/removal.
- Account recovery và helpdesk.
- SSO callback và federation linking.
- Session refresh và logout.
- Admin console và support API.
- Background job, migration và service-to-service flow.

### Policy drift

- Cùng principal nhưng endpoint khác nhau áp dụng factor khác nhau.
- Feature flag khiến một replica dùng policy cũ.
- Tenant override không được kiểm tra quyền.
- Cache giữ policy đã bị thu hồi.
- Legacy endpoint không gọi policy engine.
- API gateway và backend hiểu scope khác nhau.

Test nên so sánh policy decision theo cùng principal/context qua các entry point và version khác nhau.

## 18. Positive, negative, boundary và concurrency test

Một bộ test đầy đủ cần nhiều lớp.

### Positive

- Credential hợp lệ, đúng scope và còn hiệu lực.
- Factor đủ assurance.
- Certificate đúng trust domain.
- API key đúng tenant.
- Recovery hoàn tất theo policy.

### Negative

- Credential sai, revoked, expired hoặc bị disable.
- Issuer/audience/SAN/EKU sai.
- Factor không đủ assurance.
- Token replay hoặc refresh reuse.
- Actor/tenant không khớp.
- Legacy endpoint bỏ qua policy.

### Boundary

- Ngay trước/sau expiry.
- Password đúng giới hạn độ dài.
- Rate limit sát threshold.
- Certificate sắp hết hạn.
- Token clock skew.
- Recovery token vừa được consume.
- Policy version thay đổi trong lúc request.

### Concurrency

- Hai request dùng cùng one-time OTP.
- Hai request consume cùng recovery token.
- Hai session rotate cùng lúc.
- Credential bị revoke khi request đang xử lý.
- Hai admin cùng thay đổi factor.
- Nhiều replica reload policy đồng thời.

Expected result phải định nghĩa rõ một hay nhiều request được phép thành công và state cuối cùng là gì.

## 19. Resilience và failure-mode test

Credential policy phải an toàn khi dependency lỗi.

| Dependency | Failure scenario | Expected behavior cần định nghĩa |
| --- | --- | --- |
| Policy service | Timeout/unavailable. | Không âm thầm bỏ policy; fail behavior theo mức rủi ro. |
| Secret manager | Không lấy được credential. | Không dùng secret hết hạn ngoài policy. |
| KMS/HSM | Signing/decryption unavailable. | Không fallback sang key yếu hoặc hardcoded. |
| IdP | Outage hoặc metadata stale. | Session hiện có và login mới theo policy rõ. |
| Session store | Read/write lỗi. | Không tạo session giả; revoke semantics được bảo đảm. |
| Certificate status | OCSP/CRL unavailable. | Theo policy fail mode, không mặc định accept mọi certificate. |
| Audit pipeline | Broker/storage outage. | Durable queue/outbox cho event bắt buộc. |
| Clock source | Clock skew. | Không chấp nhận token/challenge ngoài thời gian cho phép. |

Không dùng fail-open một cách mặc định chỉ để giữ availability. Với từng loại credential, xác định hậu quả của accept sai và deny nhầm.

## 20. Test fixtures và bảo vệ dữ liệu kiểm thử

Test cần đủ đa dạng nhưng không dùng credential thật.

### Fixture nên có

- User thường, admin, user suspended và deprovisioned.
- User có password-only, MFA, passkey và nhiều factor.
- User thuộc nhiều tenant.
- Workload identity hợp lệ và giả lập không hợp lệ.
- API key active, expired, revoked và scope hẹp.
- Certificate valid, expired, revoked, wrong SAN/EKU.
- Token đúng issuer/audience và token sai profile.
- Session active, idle-expired, absolute-expired và revoked.
- Recovery token active, expired, consumed và wrong-purpose.

### Bảo vệ fixture

- Dùng domain test và sandbox provider.
- Không dùng password/token production.
- Không đưa secret vào source hoặc test report.
- Mask/redact browser storage và HTTP headers.
- Xóa session, revoke key và reset account sau test.
- Tách test tenant khỏi dữ liệu người dùng thật.
- Hạn chế quyền CI runner và giữ audit log của test.

## 21. Tự động hóa và kiểm thử trong CI/CD

Credential policy nên có test ở nhiều tầng.

| Tầng | Nội dung |
| --- | --- |
| Unit | Policy evaluator, expiry, scope mapping, verifier rules. |
| Integration | Database, secret provider, IdP, session store và key service. |
| API contract | Mọi endpoint thực thi cùng policy contract. |
| Browser/mobile E2E | Enrollment, login, step-up, recovery và logout. |
| Protocol conformance | WebAuthn, OIDC, SAML, mTLS và token profile. |
| Security regression | Replay, bypass, downgrade, revoked credential. |
| Resilience | Timeout, cache stale, rotation và dependency outage. |
| Deployment validation | Policy version, secret injection và environment isolation. |

### Pipeline gợi ý

~~~mermaid
flowchart TD
    A["Policy change / code change"] --> B["Static config and secret scan"]
    B --> C["Unit policy tests"]
    C --> D["Integration and API contract tests"]
    D --> E["Credential lifecycle E2E"]
    E --> F["Security regression and resilience"]
    F --> G["Review evidence and coverage"]
    G --> H["Controlled deployment"]
    H --> I["Post-deploy policy verification"]
~~~

Không chỉ chạy test khi code thay đổi. Policy configuration, issuer metadata, certificate trust bundle và feature flag cũng cần trigger regression test.

## 22. Java: mô hình policy decision có thể kiểm thử

Ví dụ minh họa một policy quyết định factor bắt buộc theo principal và action:

~~~java
import java.util.Set;

public record CredentialContext(
        String principalType,
        String role,
        String action,
        Set<String> verifiedFactors,
        boolean accountActive
) {}

public record PolicyDecision(
        boolean allowed,
        String reasonCode,
        Set<String> requiredFactors
) {}

public final class CredentialPolicy {

    public PolicyDecision evaluate(CredentialContext context) {
        if (!context.accountActive()) {
            return new PolicyDecision(
                    false,
                    "account_inactive",
                    Set.of()
            );
        }

        if ("admin".equals(context.role())) {
            Set<String> required = Set.of("passkey_uv");
            boolean satisfied = context.verifiedFactors().containsAll(required);

            return new PolicyDecision(
                    satisfied,
                    satisfied ? "policy_satisfied" : "phishing_resistant_factor_required",
                    required
            );
        }

        return new PolicyDecision(
                context.verifiedFactors().contains("password"),
                "standard_policy",
                Set.of("password")
        );
    }
}
~~~

Đây là ví dụ đơn giản, không phải policy engine production. Hệ thống thực tế cần policy version, tenant, authentication freshness, risk context, factor binding, exception và audit. Không coi tên factor do client gửi là bằng chứng; verifiedFactors phải đến từ verifier đáng tin cậy.

### Test policy decision

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import org.junit.jupiter.api.Test;

class CredentialPolicyTest {

    private final CredentialPolicy policy = new CredentialPolicy();

    @Test
    void inactiveAccountIsDenied() {
        var context = new CredentialContext(
                "user", "admin", "change_role",
                Set.of("passkey_uv"), false
        );

        var decision = policy.evaluate(context);

        assertFalse(decision.allowed());
        assertEquals("account_inactive", decision.reasonCode());
    }

    @Test
    void adminWithoutRequiredFactorIsDenied() {
        var context = new CredentialContext(
                "user", "admin", "change_role",
                Set.of("password"), true
        );

        var decision = policy.evaluate(context);

        assertFalse(decision.allowed());
        assertEquals(
                "phishing_resistant_factor_required",
                decision.reasonCode()
        );
    }

    @Test
    void adminWithRequiredFactorIsAllowed() {
        var context = new CredentialContext(
                "user", "admin", "change_role",
                Set.of("password", "passkey_uv"), true
        );

        assertTrue(policy.evaluate(context).allowed());
    }
}
~~~

Các test này chỉ kiểm tra logic ví dụ. Integration test phải xác minh factor được verifier phát hành sau khi kiểm tra chữ ký/challenge, không phải do caller tự tạo.

## 23. Audit và evidence cho credential policy test

Mỗi test bảo mật cần lưu đủ bằng chứng để xác định policy đã được thực thi.

### Evidence nên có

- Test ID và policy ID/version.
- Principal fixture reference.
- Credential type và trạng thái, không lưu secret.
- Endpoint/service và environment.
- Request ID/correlation ID.
- Expected/actual decision.
- Reason code.
- Audit event reference.
- Policy version và configuration snapshot.
- Timestamp và cleanup result.

### Không lưu

- Password thật hoặc test password trong report chia sẻ.
- OTP, recovery code, token, cookie và private key.
- Raw HTTP Authorization header.
- Secret manager response.
- Full certificate private key material.

Nếu cần chứng minh credential bị từ chối, lưu reference/hash an toàn hoặc fixture ID; không lưu chính credential có thể sử dụng.

## 24. Đánh giá finding và báo cáo

Finding cần nêu policy nào bị vi phạm, điều kiện khai thác và tác động.

| Mức | Ví dụ |
| --- | --- |
| Critical | Có thể bypass xác thực hoặc policy MFA trên nhiều account đặc quyền; credential có quyền rộng bị chấp nhận toàn hệ thống. |
| High | Recovery bypass, revoked token/session vẫn truy cập dữ liệu nhạy cảm, workload identity bị giả mạo. |
| Medium | Policy inconsistency ở endpoint phụ, expiry/rotation vượt SLA, rate limit yếu trong phạm vi giới hạn. |
| Low | Audit field thiếu hoặc thông báo policy không rõ nhưng không tạo bypass trực tiếp. |
| Informational | Cải thiện coverage, testability hoặc tài liệu policy. |

Severity cần xét principal, asset, assurance, exploitability, tenant count, dữ liệu và control bù. Không xếp mức chỉ theo tên kỹ thuật.

### Cấu trúc finding

- Title và finding ID.
- Policy ID/version bị ảnh hưởng.
- Credential/principal type.
- Affected endpoint/service/environment.
- Preconditions và test fixture.
- Steps to reproduce trong môi trường được phép.
- Expected vs actual behavior.
- Evidence đã redact.
- Impact, scope và severity rationale.
- Recommendation và owner.
- Retest result.

## 25. Ví dụ thực tế: Learning Platform

Learning Platform có học viên, giảng viên, staff admin và các service nội bộ.

### Policy

- Học viên dùng password kết hợp MFA hoặc passkey theo cấu hình.
- Staff admin cần phishing-resistant MFA.
- Password nằm trong blocklist bị từ chối.
- API key của integration chỉ có scope đọc catalog.
- Access token có audience riêng cho Enrollment API.
- Session bị revoke phải bị từ chối ở mọi API node.
- Recovery thay authenticator cần assurance và approval phù hợp.

### Kế hoạch test

1. Tạo fixture cho learner, instructor, admin và service client.
2. Kiểm tra password length, blocklist, Unicode và password change.
3. Kiểm tra verifier không lưu plaintext và nâng cấp hash theo policy.
4. Thử admin login chỉ bằng password; expected deny hoặc challenge.
5. Enroll passkey bằng challenge/origin đúng và sai.
6. Dùng API key catalog gọi endpoint write; expected deny.
7. Gửi token audience Learning API tới Enrollment API; expected deny.
8. Revoke session rồi gửi request từ mọi node.
9. Thử recovery bằng email-only cho admin; expected không bypass policy.
10. Rotate workload certificate và xác minh certificate cũ không được dùng cho kết nối mới.
11. Đối chiếu audit event và policy version cho từng quyết định.
12. Chạy lại toàn bộ regression sau thay đổi policy.

### Ví dụ finding

Test phát hiện Staff Console yêu cầu passkey cho admin nhưng endpoint recovery cho phép support bỏ factor chỉ bằng email xác nhận. Đây là policy bypass qua fallback. Finding cần mô tả actor, subject, recovery endpoint, assurance thiếu, tác động và test evidence. Corrective action có thể yêu cầu step-up/approval, audit và notification; retest phải chứng minh cả web, API và support path đều tuân thủ.

## 26. Test matrix tổng hợp

| Nhóm | Test đại diện | Expected result |
| --- | --- | --- |
| Password strength | Password dưới/đúng/trên boundary. | Policy được áp dụng; không truncate âm thầm. |
| Password blocklist | Password phổ biến/compromised fixture. | Bị từ chối. |
| Password verifier | Kiểm tra DB fixture và log. | Không có plaintext; hash config đúng policy. |
| Password migration | Login với verifier legacy. | Rehash chỉ sau verify thành công. |
| MFA enrollment | Enroll từ session không đủ assurance. | Bị deny hoặc step-up. |
| MFA verification | OTP sai/hết hạn/replay. | Bị từ chối và audit. |
| MFA fallback | Admin chuyển sang SMS/email. | Không downgrade ngoài policy. |
| Passkey registration | Origin/RP ID/challenge sai. | Registration bị từ chối. |
| Passkey authentication | Assertion sai signature hoặc challenge replay. | Authentication bị từ chối. |
| Certificate | Expired/revoked/wrong SAN/EKU. | TLS/client authentication bị từ chối. |
| API key | Wrong scope/tenant/expiry. | Request bị từ chối. |
| API key rotation | Dùng key cũ sau revoke. | Key cũ không mở request mới. |
| Access token | Wrong issuer/audience/exp/type. | Resource server từ chối. |
| Refresh token | Reuse token đã rotate. | Detection/revocation theo policy. |
| Session | Session cũ sau logout/revoke. | Backend từ chối. |
| Workload identity | Sai namespace/service account. | Không cấp hoặc không chấp nhận identity. |
| Recovery | Reset/re-enroll bằng proof yếu. | Không bypass assurance. |
| Policy consistency | Cùng context qua web/API/mobile/legacy. | Quyết định nhất quán. |
| Concurrency | Hai request consume one-time code. | Chỉ một lần được chấp nhận. |
| Resilience | Policy/secret provider outage. | Fail behavior đúng policy. |
| Audit | Kiểm tra event và reason code. | Có evidence, không có secret. |
| CI regression | Chạy test sau policy/config change. | Regression phát hiện drift. |

## 27. Checklist credential policy test

- [ ] Policy có ID/version, owner và phạm vi principal/tenant rõ.
- [ ] Có ma trận credential type × lifecycle × endpoint.
- [ ] Password length, blocklist, Unicode và verifier được kiểm tra.
- [ ] Password không lưu plaintext; hashing/salt/pepper theo policy.
- [ ] MFA factor independence và phishing resistance được xác minh.
- [ ] Enrollment/removal/step-up/fallback tuân thủ cùng policy.
- [ ] Passkey test challenge, origin, RP ID, signature và user verification.
- [ ] Certificate test chain, SAN, EKU, expiry, revocation và rotation.
- [ ] API key/client secret test scope, owner, expiry, storage và revoke.
- [ ] Token test issuer, audience, scope, time, type và sender binding.
- [ ] Session test cookie, rotation, timeout, logout và revoke.
- [ ] Workload identity test attestation, environment, audience và deprovision.
- [ ] Recovery không tạo đường bypass yếu hơn login.
- [ ] Web, API, mobile, support và legacy endpoint được so sánh policy.
- [ ] Có positive, negative, boundary, concurrency và resilience tests.
- [ ] Test fixtures không dùng production credential hoặc dữ liệu thật.
- [ ] Evidence có policy version, correlation và audit reference đã redact.
- [ ] CI/CD chạy regression khi code hoặc policy configuration thay đổi.
- [ ] Finding có severity rationale, owner, recommendation và retest.
- [ ] Có cleanup/revoke fixture và kiểm tra không còn credential test hoạt động.

## 28. Tự kiểm tra

**Câu 1.** Credential policy test khác login test như thế nào?

**Đáp án:** Login test kiểm tra một luồng xác thực; credential policy test kiểm tra quy tắc tạo, lưu, verify, enroll, sử dụng, rotate, recover và revoke trên nhiều credential và entry point.

**Câu 2.** Vì sao cần test cùng policy qua web, API, mobile và recovery?

**Đáp án:** Vì endpoint phụ hoặc legacy path có thể bỏ qua policy của luồng chính, tạo downgrade hoặc bypass.

**Câu 3.** Password policy có nên chỉ kiểm tra chữ hoa, số và ký hiệu không?

**Đáp án:** Không. Cần theo policy thực tế, chú trọng độ dài, blocklist, chống guessing, password manager và verifier an toàn; không áp quy tắc thành phần tùy tiện nếu không có yêu cầu.

**Câu 4.** Vì sao test password verifier cần kiểm tra cả migration?

**Đáp án:** Hệ thống có thể giữ verifier cũ hoặc nâng cấp sai. Cần xác minh rehash chỉ sau verify thành công và không hạ mức bảo vệ.

**Câu 5.** Admin dùng password cộng SMS có đáp ứng policy phishing-resistant MFA không?

**Đáp án:** Không nếu policy yêu cầu factor phishing-resistant. Fallback yếu không được âm thầm thay thế factor bắt buộc.

**Câu 6.** Certificate còn hạn có chắc chắn được chấp nhận không?

**Đáp án:** Không. Còn phải kiểm tra chain, issuer, SAN, EKU, key usage, revocation và mapping tới workload principal.

**Câu 7.** Vì sao token cần audience validation ở từng resource server?

**Đáp án:** Để token dành cho API này không bị sử dụng ở API khác, kể cả khi cùng issuer ký token.

**Câu 8.** Revoke password hoặc API key có tự động kết thúc mọi session không?

**Đáp án:** Không nhất thiết. Cần test session, refresh token, connection đang mở và cache theo policy riêng.

**Câu 9.** Khi policy service unavailable, có nên mặc định allow để giữ availability không?

**Đáp án:** Không. Fail behavior phải được xác định theo mức rủi ro và loại credential; không âm thầm bỏ kiểm soát xác thực.

**Câu 10.** Điều gì chứng minh credential policy test đã thành công?

**Đáp án:** Test evidence cho thấy allow/deny và state transition đúng ở mọi entry point, audit chính xác, credential cũ bị revoke theo SLA và regression được duy trì sau thay đổi.

## Ghi nhớ

**Credential policy test** xác minh các quy tắc bảo vệ credential được thực thi xuyên suốt vòng đời và mọi entry point. Kiểm thử phải bao phủ password/verifier, MFA, passkey, certificate, API key, token, session, workload identity và recovery; đồng thời kiểm tra policy consistency, fallback, rotation, revocation và failure mode.

Chuyển mỗi policy thành testable condition, dùng fixture an toàn, bao phủ positive/negative/boundary/concurrency và kiểm tra cả audit/state ở backend. Đặc biệt chú ý đường recovery, legacy endpoint và cache có thể làm yếu policy. **Một credential policy chỉ đáng tin khi mọi cách tạo, sử dụng, thay thế và thu hồi credential đều tuân thủ cùng ranh giới bảo mật đã định nghĩa.**
