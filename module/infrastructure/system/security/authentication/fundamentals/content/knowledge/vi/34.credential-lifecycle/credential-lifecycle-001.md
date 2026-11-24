# Credential issuance: cấp phát credential an toàn

> **Chương:** Credential lifecycle  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích cách một hệ thống cấp phát credential có thẩm quyền: xác định đúng subject, kiểm tra điều kiện cấp, tạo hoặc tiếp nhận bí mật/khóa, liên kết credential với danh tính và mục đích, phân phối an toàn, kích hoạt, ghi nhận và chuẩn bị cho rotation/revocation.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích credential issuance và phân biệt issuance với identity proofing, enrollment, authentication và provisioning.
2. Xác định issuer, subject, credential holder, verifier và authority trong từng mô hình.
3. Thiết kế quy trình phê duyệt cấp credential dựa trên danh tính, quyền hạn và assurance.
4. Phân biệt credential do server tạo với key pair được tạo ở authenticator/client.
5. Cấp phát password bootstrap, API key, certificate và workload credential theo nguyên tắc least privilege.
6. Bảo vệ quá trình tạo, phân phối, lưu trữ, kích hoạt và ghi nhận credential.
7. Ngăn mis-issuance, credential substitution, replay, duplicate issuance và cấp quyền quá rộng.
8. Thiết kế trạng thái credential, rotation, suspension và revocation ngay từ đầu.
9. Tổ chức issuance service trong Java/Spring và xây dựng ma trận kiểm thử.

## 2. Credential issuance là gì?

**Credential issuance** là quy trình một authority có thẩm quyền tạo, phê duyệt hoặc xác nhận một credential và gắn nó với một subject, mục đích và phạm vi sử dụng cụ thể.

Credential là dữ liệu hoặc vật mang bằng chứng mà verifier dùng để xác thực một chủ thể hoặc kiểm tra quyền kiểm soát. Ví dụ:

- Password hoặc bootstrap secret.
- Passkey/WebAuthn credential, trong đó authenticator giữ private key và RP lưu public key.
- TOTP shared secret.
- Client certificate hoặc user certificate trong PKI.
- API key hoặc client secret cho ứng dụng.
- Workload identity credential, token hoặc certificate ngắn hạn.
- Recovery code.

Một credential có thể được tạo bởi server, authenticator, người dùng hoặc CA. Issuer là thành phần có thẩm quyền chấp nhận và liên kết credential với danh tính; issuer không nhất thiết tự biết hoặc giữ private key.

Ví dụ:

- Với WebAuthn, authenticator tạo key pair; RP xác minh registration ceremony và lưu public key. RP chấp nhận credential vào account.
- Với X.509, client có thể tự tạo key pair và gửi CSR; CA xác minh yêu cầu rồi ký certificate liên kết public key với identity/attributes theo policy.
- Với API key, service có thể tạo secret ngẫu nhiên, lưu verifier và hiển thị secret một lần cho client.

Issuance an toàn không chỉ là sinh một chuỗi ngẫu nhiên. Hệ thống phải chứng minh đúng chủ thể được nhận credential, đúng credential được liên kết, đúng quyền được cấp và đúng kênh phân phối được bảo vệ.

## 3. Phân biệt issuance, identity proofing, enrollment và authentication

| Hoạt động | Câu hỏi | Kết quả |
|---|---|---|
| **Identity proofing** | Người yêu cầu là ai và có đủ điều kiện được nhận danh tính không? | Danh tính/thuộc tính được xác minh theo assurance |
| **Credential issuance** | Authority có cấp credential này cho subject và purpose này không? | Credential record hoặc certificate/key/secret được phát hành |
| **Authenticator enrollment** | Credential/authenticator có được liên kết với đúng account và chứng minh được quyền kiểm soát không? | Credential được chấp nhận và kích hoạt |
| **Authentication** | Request hiện tại có proof hợp lệ từ credential đã đăng ký không? | Authentication event/context |
| **Provisioning** | Tài khoản, nhóm, quyền và tài nguyên được tạo/cập nhật ở hệ thống đích ra sao? | Account/resource state |
| **Authorization** | Subject có quyền thực hiện action trên resource không? | Allow/deny/policy decision |

Các bước có thể liên kết trong một quy trình nhưng không thể thay thế nhau. Một certificate có chữ ký CA hợp lệ chưa chắc được phép truy cập API; một API key được tạo thành công chưa chứng minh người nhận có quyền trên mọi tenant.

## 4. Mô hình trust trong credential issuance

Các vai trò cần được phân biệt:

- **Subject:** danh tính mà credential đại diện, như user, device, client hoặc workload.
- **Requester:** người hoặc service yêu cầu cấp credential.
- **Issuer/authority:** hệ thống có thẩm quyền phê duyệt và phát hành.
- **Holder:** bên nắm giữ hoặc sử dụng credential.
- **Authenticator:** thành phần tạo proof, chẳng hạn passkey authenticator hoặc smart card.
- **Verifier:** hệ thống kiểm tra credential/proof.
- **Relying party/resource server:** ứng dụng quyết định chấp nhận kết quả và áp dụng authorization.

~~~mermaid
flowchart TD
    Q["Requester"] --> I["Identity / eligibility verification"]
    I --> P["Issuance policy and approval"]
    P --> A["Credential authority"]
    A --> G["Generate or validate key / secret / request"]
    G --> B["Bind credential to subject, client and purpose"]
    B --> D["Secure delivery / registration"]
    D --> V["Proof of possession / activation"]
    V --> R["Credential registry and verifier"]
    R --> U["Use in authentication"]
    R --> L["Lifecycle: rotate, suspend, revoke"]
~~~

Ranh giới tin cậy:

1. Requester không tự quyết định subject hoặc quyền được cấp.
2. Identity source phải có authority rõ ràng.
3. Issuance service chỉ cấp theo policy và approval hợp lệ.
4. Secret/key generation phải dùng nguồn ngẫu nhiên hoặc cryptographic provider phù hợp.
5. Delivery channel không được để credential lộ qua log, URL hoặc kênh không xác minh.
6. Verifier phải kiểm tra credential state và proof, không chỉ sự tồn tại của record.
7. Audit phải ghi ai yêu cầu, ai phê duyệt, issuer nào phát hành và kết quả mà không lưu secret.

## 5. Điều kiện trước khi cấp credential

Trước khi phát hành, authority cần xác định:

- Subject đã tồn tại và có định danh ổn định chưa?
- Danh tính/thuộc tính có được xác minh ở mức phù hợp không?
- Requester có quyền yêu cầu credential cho subject đó không?
- Credential dành cho user, client, device hay workload?
- Mục đích, audience/resource, scope và thời hạn là gì?
- Credential có yêu cầu phê duyệt của manager/admin hoặc dual control không?
- Có credential tương tự đang active hoặc request pending không?
- Account có bị khóa, suspended, offboarded hoặc đang trong incident không?
- Kênh phân phối có được xác minh và phù hợp với mức nhạy cảm không?

Không cấp credential chỉ vì request body chứa account ID, role hoặc tenant ID. Những thuộc tính này phải được lấy từ identity store/policy server-side có thẩm quyền.

### Least privilege tại thời điểm cấp

Credential nên được giới hạn ngay khi phát hành:

- Chỉ dành cho một subject/client/workload.
- Chỉ có audience/resource cần thiết.
- Chỉ có scope/action cần thiết.
- Thời hạn phù hợp với rủi ro.
- Môi trường và tenant cụ thể.
- Không có quyền quản trị mặc định.

Nếu quyền thay đổi sau khi phát hành, hệ thống cần policy để cập nhật, rotate hoặc revoke credential. Không dùng một API key dài hạn với quyền admin chỉ để tránh quản lý nhiều key.

## 6. Sinh credential: server-generated và holder-generated

### 6.1. Server-generated secret

Với API key, recovery code hoặc bootstrap secret, server có thể tạo giá trị ngẫu nhiên bằng cryptographically secure random number generator (CSPRNG).

Yêu cầu:

- Entropy đủ lớn và không dựa trên timestamp, UUID không phù hợp hoặc thông tin cá nhân.
- Không tái sử dụng secret giữa account/client.
- Secret có prefix hoặc key ID không bí mật để tra cứu nếu cần.
- Secret được hiển thị một lần và không lưu plaintext.
- Lưu verifier/hash hoặc dùng secret manager phù hợp.
- Giới hạn scope, audience, expiry và trạng thái ngay từ lúc tạo.

### 6.2. Holder-generated key pair

Với passkey, smart card hoặc client certificate, private key thường nên được tạo và giữ ở holder/authenticator hoặc thiết bị được quản lý. Issuer nhận public key hoặc CSR để xác minh và liên kết.

Ưu điểm:

- Private key không cần truyền qua mạng tới issuer.
- Có thể giữ khóa trong secure hardware/OS keystore.
- Issuer lưu public key/certificate để verifier kiểm tra proof.

Rủi ro:

- Client có thể gửi public key không thuộc quyền kiểm soát của subject.
- CSR có thể yêu cầu SAN/identity attributes không được phép.
- Attestation có thể bị hiểu sai hoặc tạo fingerprint.
- Thiết bị có thể mất hoặc private key bị compromise sau issuance.

Do đó, issuance cần proof-of-possession và kiểm tra subject binding; không chỉ nhận public key rồi cấp credential.

## 7. Credential issuance cho password

Trong hệ thống password, người dùng thường tự chọn password sau khi account được tạo hoặc recovery. Nếu hệ thống tạo bootstrap password tạm thời, secret này phải có thời hạn ngắn và buộc đổi/thiết lập password ngay lần đầu.

Nguyên tắc:

- Không gửi password mặc định chung cho nhiều người.
- Không sinh password từ username, ngày sinh hoặc dữ liệu dự đoán được.
- Không lưu plaintext; dùng password hashing phù hợp như Argon2id, scrypt hoặc bcrypt theo policy/khả năng nền tảng.
- Không ghi password vào log, audit, analytics hoặc email.
- Với bootstrap secret, dùng one-time token có purpose binding và expiry.
- Rate limit việc yêu cầu cấp/reset credential.
- Không cho bootstrap password yếu mở quyền đặc quyền.

Password reset là một luồng recovery; không phải lý do để phát hành lại một password cố định. Sau reset, hệ thống cần xem xét session/token cũ theo policy.

## 8. Credential issuance cho passkey/WebAuthn

Trong WebAuthn, authenticator tạo key pair trong registration ceremony. RP không tạo private key cho user. RP phát hành challenge và policy options; authenticator tạo credential; server xác minh response rồi lưu public key.

Các bước chính:

1. Xác định account đã được xác minh và session đủ tin cậy.
2. Tạo challenge ngẫu nhiên, gắn với account/session/RP ID và thời hạn.
3. Tạo PublicKeyCredentialCreationOptions với user handle, RP, algorithms và authenticator selection.
4. Browser gọi WebAuthn API; authenticator tạo credential và trả attestation response.
5. Server xác minh challenge, origin, RP ID hash, credential ID, public key, flags và attestation policy.
6. Kiểm tra credential ID chưa được liên kết với account khác.
7. Lưu public key và metadata cần thiết, chuyển trạng thái sang active.
8. Thông báo và ghi audit.

Server chỉ lưu public key/credential metadata theo policy; không nhận hoặc lưu private key của passkey. Registration proof phải được ràng buộc với đúng account và session để ngăn credential substitution.

### Attestation không phải lúc nào cũng cần

Attestation có thể cung cấp thông tin về authenticator theo trust model cụ thể. Chỉ yêu cầu khi tổ chức cần kiểm soát loại thiết bị hoặc nguồn gốc authenticator. Nếu không cần, giảm attestation requirements để bảo vệ quyền riêng tư và tăng tương thích.

## 9. Credential issuance cho TOTP

TOTP dùng shared secret được chia sẻ giữa verifier và authenticator app. Khi cấp TOTP:

1. Xác minh user/session đủ tin cậy.
2. Sinh shared secret ngẫu nhiên.
3. Lưu secret pending được mã hóa.
4. Tạo provisioning URI/QR code cho user quét.
5. Yêu cầu user nhập mã hiện tại để chứng minh đã cài đúng secret.
6. Chỉ sau khi xác minh mới chuyển credential sang active.
7. Hủy pending secret khi hết hạn hoặc user hủy flow.

QR code/URI chứa secret tương đương credential. Không ghi QR, URI hoặc seed vào log. Khi reset TOTP, revoke seed cũ; không chỉ tạo seed mới mà vẫn chấp nhận seed cũ.

## 10. Certificate issuance và PKI

Trong PKI, Certificate Authority (CA) phát hành X.509 certificate liên kết public key với subject/identity attributes theo certificate policy.

Flow thường gặp:

1. Subject/device tạo key pair trong thiết bị hoặc HSM.
2. Subject tạo Certificate Signing Request (CSR) chứa public key và subject/SAN yêu cầu.
3. CA xác minh requester, quyền yêu cầu certificate và proof-of-possession của private key tương ứng.
4. CA kiểm tra profile, SAN, key usage, extended key usage, algorithm, validity và policy.
5. CA ký certificate bằng signing key được bảo vệ.
6. Certificate được phân phối tới subject; private key vẫn ở holder.
7. Verifier kiểm tra chain, validity, name constraints, key usage, revocation và policy khi certificate được sử dụng.

~~~text
Device / workload
  -> Generate private key locally
  -> Create CSR(public key + requested identity)
  -> Submit CSR to enrollment authority

CA / enrollment service
  -> Authenticate requester
  -> Verify subject authorization and proof of possession
  -> Validate SAN / profile / key usage / validity
  -> Sign certificate
  -> Return certificate chain

Holder
  -> Store certificate with corresponding private key
  -> Prove possession during TLS/client authentication
~~~

CA không nên chấp nhận SAN tùy ý từ CSR. Subject Alternative Name phải được lấy từ identity inventory hoặc policy server-side, không lấy trực tiếp từ nội dung requester tự khai.

### Certificate profile

Certificate profile quy định:

- Subject/SAN nào được cấp.
- Key algorithm/size/curve được phép.
- Key Usage và Extended Key Usage.
- Thời hạn tối đa.
- CA/issuer chain.
- Có yêu cầu hardware-backed key hay không.
- Cơ chế revocation và OCSP/CRL.
- Quy tắc renewal và overlap khi rotate.

Certificate hợp lệ về chữ ký không tự động được phép cho mọi mục đích. Verifier cần kiểm tra EKU, SAN, trust anchor và authorization context.

## 11. API key và client secret issuance

API key thường là bearer secret đại diện cho client/application. Ai lấy được key có thể sử dụng trong phạm vi quyền của key.

Một API key an toàn cần:

- Sinh ngẫu nhiên bằng CSPRNG.
- Gắn với một client/service principal cụ thể.
- Có tên hiển thị và key ID không bí mật để quản lý.
- Có scope, audience, tenant và expiry.
- Lưu hash/verifier thay vì plaintext.
- Hiển thị secret đúng một lần.
- Có chức năng rotate/revoke và audit last-used.
- Rate limit và giám sát bất thường.

Không dùng một API key chung cho toàn bộ developer/team. Cấp key riêng theo workload/environment để thu hồi một key không làm gián đoạn mọi service.

### Client secret khác password người dùng

Client secret xác thực confidential OAuth client. Nó cần được lưu trong secret manager hoặc vault, xoay vòng và không đưa vào browser/mobile binary. Public client không thể giữ client secret một cách đáng tin chỉ bằng cách nhúng vào ứng dụng.

## 12. Workload identity và credential ngắn hạn

Service-to-service credential thường được cấp cho workload thay vì người dùng. Ví dụ:

- Certificate ngắn hạn từ internal CA.
- Federated workload token.
- OAuth client credential.
- SPIFFE/SVID hoặc mô hình workload identity tương đương.

Nguyên tắc:

- Identity gắn với workload/service account, environment và deployment boundary.
- Credential lifetime ngắn nếu có thể.
- Không nhúng long-lived secret vào image/container hoặc source code.
- Cấp theo runtime identity/attestation đáng tin cậy.
- Tách dev/staging/production.
- Giới hạn audience và scope cho API cụ thể.
- Có rotation tự động và revoke khi workload bị compromise.

Không dùng credential của developer để chạy production service. Tách human identity và workload identity giúp audit và thu hồi chính xác hơn.

## 13. Delivery và bootstrap channel

Credential có thể được tạo đúng nhưng vẫn bị lộ trong quá trình phân phối.

Các nguyên tắc:

- Dùng kênh đã xác minh và phù hợp assurance.
- Không gửi secret dài hạn qua email/chat/plain text.
- Không đặt token/secret trong URL query hoặc referrer.
- Hiển thị secret một lần qua TLS; không cung cấp chức năng xem lại.
- Với certificate, gửi certificate/public chain; private key vẫn ở holder.
- Với password bootstrap, dùng activation link/token một lần thay vì password dùng chung.
- Với API key, yêu cầu user copy ngay và lưu trong secret manager.
- Redact credential khỏi reverse proxy, application log, tracing và error report.
- Không dùng kênh vừa được thêm trong cùng recovery flow làm bằng chứng độc lập cho chính việc thêm đó.

### Delivery không đồng nghĩa activation

Một credential đã gửi email nhưng chưa được xác minh hoặc chưa chứng minh proof-of-possession nên ở trạng thái pending. Chỉ sau khi người nhận hoàn tất activation và server kiểm tra proof mới chuyển sang active.

## 14. Credential binding: gắn với đúng subject và purpose

Credential record cần thể hiện rõ:

- Subject/account/client/workload owner.
- Issuer và issuance authority.
- Credential type và identifier.
- Purpose và audience/resource.
- Scope/permission được cấp.
- Thời điểm tạo, kích hoạt, hết hạn.
- Trạng thái và phiên bản policy.
- Cách thu hồi/rotation.
- Approver và nguồn proofing khi cần.

Không liên kết credential chỉ bằng email hoặc display name. Với federation identity, dùng issuer + subject. Với service, dùng workload identity ổn định. Với certificate, xác minh SAN/subject theo profile. Với API key, gắn key ID với client record phía server.

### Purpose binding

Một credential được cấp cho password reset không được dùng như API key. Một token activation không được dùng để reset MFA. Một certificate clientAuth không mặc định được dùng code signing.

Purpose cần được ghi trong metadata/policy và kiểm tra tại verifier/resource server.

## 15. Trạng thái credential và activation

Credential nên có trạng thái rõ ràng:

| Trạng thái | Ý nghĩa | Có được chấp nhận không? |
|---|---|---|
| requested | Có yêu cầu nhưng chưa được phê duyệt | Không |
| pending | Đã tạo/phân phối nhưng chưa hoàn tất proof/activation | Không |
| active | Đã xác minh và được phép sử dụng | Có, theo policy |
| suspended | Tạm ngừng do risk, incident hoặc yêu cầu admin | Không |
| revoked | Đã thu hồi có chủ đích | Không |
| expired | Hết thời hạn | Không |
| replaced | Đã được credential mới thay thế | Không |

Không chỉ dùng boolean enabled. Chuyển trạng thái cần được thực hiện server-side, có audit và kiểm soát concurrency. Credential pending không được dùng đăng nhập.

~~~mermaid
stateDiagram-v2
    [*] --> requested
    requested --> pending: approved and generated
    requested --> revoked: denied or cancelled
    pending --> active: proof and activation verified
    pending --> expired: activation deadline passed
    pending --> revoked: cancelled
    active --> suspended: risk or incident
    active --> revoked: revoke
    active --> replaced: rotation completed
    suspended --> active: reviewed and restored
    suspended --> revoked: confirmed compromise
    replaced --> [*]
    revoked --> [*]
    expired --> [*]
~~~

## 16. Rotation, renewal và revocation ngay từ lúc issuance

Issuance cần thiết kế đường kết thúc credential ngay từ đầu:

- **Rotation:** thay credential bằng credential mới, có overlap ngắn nếu cần để tránh downtime.
- **Renewal:** cấp lại certificate/credential trước expiry sau khi kiểm tra identity và policy.
- **Suspension:** tạm ngừng chấp nhận khi có dấu hiệu compromise hoặc investigation.
- **Revocation:** đánh dấu credential không còn hợp lệ và cập nhật verifier/resource server.
- **Replacement:** liên kết credential mới và vô hiệu credential cũ theo quy tắc rõ.

Với API key, rotation có thể cho phép hai key cùng active trong khoảng ngắn để service chuyển cấu hình. Với certificate, renewal có thể phát hành cert mới trước khi cert cũ hết hạn. Với TOTP/passkey, thay thế cần xác minh authenticator mới trước khi xóa phương thức cuối cùng.

Không để credential cũ active vô thời hạn chỉ vì chưa chắc tất cả consumer đã cập nhật. Xác định overlap window, owner, telemetry và deadline thu hồi.

## 17. Audit và inventory

Credential inventory giúp trả lời:

- Credential nào tồn tại?
- Thuộc subject/client/workload nào?
- Ai đã yêu cầu và phê duyệt?
- Khi nào được tạo, kích hoạt, sử dụng gần nhất?
- Scope, audience và expiry là gì?
- Đang active, suspended, revoked hay expired?
- Có credential nào không còn owner hoặc vượt thời hạn không?

Audit nên ghi:

- Issuance request ID và credential ID/key ID.
- Subject/client/workload ID nội bộ.
- Issuer/authority và policy version.
- Loại credential, purpose, scope/audience metadata.
- Requester, approver, thời gian và kết quả.
- Activation/rotation/revocation events.

Không ghi:

- Password, API key secret, client secret.
- Private key hoặc recovery code.
- TOTP seed/QR provisioning URI.
- Raw access/refresh token hoặc session cookie.
- CSR/private material nếu chứa thông tin nhạy cảm không cần cho audit.

Credential inventory nên được đối chiếu với directory, service catalog, PKI/secret manager và runtime usage để phát hiện credential mồ côi.

## 18. Các lỗi issuance thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Cấp credential chỉ dựa trên account ID client gửi | Credential gắn nhầm subject | Lấy subject từ identity context đã xác minh |
| Tự sinh private key rồi gửi cho user | Private key có thêm bản sao và tăng nguy cơ lộ | Ưu tiên holder-generated key khi phù hợp |
| CA tin SAN do CSR tự khai | Mis-issuance và giả mạo identity | Map SAN từ inventory/policy server-side |
| API key có quyền admin mặc định | Lộ key gây blast radius lớn | Least privilege, audience/scope cụ thể |
| Secret hiển thị nhiều lần | Tăng số bản sao có thể bị lộ | One-time display và rotation |
| Credential active ngay khi tạo | Chưa chứng minh holder kiểm soát | Pending → proof → active |
| Dùng email vừa thay làm kênh xác minh duy nhất | Recovery/issuance circular trust | Kênh cũ và bằng chứng độc lập |
| Không có expiry hoặc owner | Credential mồ côi, khó thu hồi | Inventory, owner và lifetime |
| Không có rotation/revocation plan | Credential bị lộ tiếp tục hoạt động | Thiết kế lifecycle ngay khi cấp |
| Ghi secret vào log | Log thành kho credential | Redaction và secret scanning |
| Dùng chung key giữa môi trường | Dev compromise ảnh hưởng production | Tách identity/credential theo environment |
| Chỉ kiểm tra certificate chain | Certificate đúng CA nhưng sai EKU/SAN/purpose | Kiểm tra profile, identity và authorization |
| Cấp trùng credential khi retry | Nhiều key active ngoài dự kiến | Idempotency key và duplicate detection |
| Không xử lý approval race | Requester tự phê duyệt hoặc cấp hai lần | Separation of duties và atomic state transition |

## 19. Java: tạo API key và lưu verifier

Ví dụ dưới đây minh họa tạo API key có entropy cao, hiển thị secret một lần và chỉ lưu SHA-256 verifier cùng key ID. Cách hash này phù hợp với secret ngẫu nhiên entropy cao; không dùng để lưu password người dùng hoặc mã ngắn dễ đoán.

~~~java
record IssuedApiKey(
    String keyId,
    String plaintextOnce,
    Instant expiresAt
) {}

record ApiKeyRecord(
    String keyId,
    UUID clientId,
    byte[] verifierHash,
    Set<String> scopes,
    String audience,
    Instant expiresAt,
    String status
) {}

@Service
class ApiKeyIssuer {
    private final SecureRandom random = new SecureRandom();
    private final ApiKeyRepository repository;

    ApiKeyIssuer(ApiKeyRepository repository) {
        this.repository = repository;
    }

    IssuedApiKey issue(
            UUID clientId,
            Set<String> approvedScopes,
            String approvedAudience,
            Instant expiresAt) {

        byte[] raw = new byte[32];
        random.nextBytes(raw);

        String secret = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(raw);
        String keyId = UUID.randomUUID().toString();

        ApiKeyRecord record = new ApiKeyRecord(
            keyId,
            clientId,
            sha256(secret),
            Set.copyOf(approvedScopes),
            approvedAudience,
            expiresAt,
            "PENDING_ACTIVATION"
        );

        repository.insert(record);
        return new IssuedApiKey(keyId, secret, expiresAt);
    }

    private byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
~~~

Đây là ví dụ khung. Trước khi gọi issue, service phải xác minh requester được phép cấp key cho client, scope/audience nằm trong allowlist và expiry tuân theo policy. Secret chỉ được trả một lần qua TLS; không log object chứa plaintext. Nếu cần activation, key chỉ được chuyển sang active sau khi client chứng minh possession theo flow đã thiết kế.

### Verify API key

~~~java
boolean verify(String presentedSecret, ApiKeyRecord record) {
    byte[] supplied = sha256(presentedSecret);
    return record.status().equals("ACTIVE")
        && record.expiresAt().isAfter(Instant.now())
        && MessageDigest.isEqual(record.verifierHash(), supplied);
}
~~~

Trong production, cần rate limit, constant-time comparison, xử lý null/format, tra cứu bằng key ID/prefix không bí mật, kiểm tra client status và cập nhật last-used an toàn. API key hợp lệ vẫn phải qua authorization theo scope, audience, tenant và resource.

## 20. Java: cấp certificate qua CSR

Ví dụ này mô tả orchestration, không tự triển khai X.509 parsing/signing:

~~~java
record CertificateRequest(
    UUID requesterId,
    String csrPem,
    String requestedProfile
) {}

@Service
class CertificateIssuanceService {
    private final RequestAuthorizer authorizer;
    private final CsrVerifier csrVerifier;
    private final SubjectDirectory directory;
    private final CertificateAuthority ca;
    private final CertificateRepository certificates;

    CertificateIssuanceService(
            RequestAuthorizer authorizer,
            CsrVerifier csrVerifier,
            SubjectDirectory directory,
            CertificateAuthority ca,
            CertificateRepository certificates) {
        this.authorizer = authorizer;
        this.csrVerifier = csrVerifier;
        this.directory = directory;
        this.ca = ca;
        this.certificates = certificates;
    }

    IssuedCertificate issue(CertificateRequest request) {
        Subject subject = directory.requireAuthorizedSubject(
            request.requesterId()
        );
        authorizer.requireCertificateIssuance(subject, request.requestedProfile());

        VerifiedCsr csr = csrVerifier.verifyProofOfPossession(request.csrPem());
        CertificateProfile profile =
            directory.requireAllowedProfile(subject, request.requestedProfile());

        profile.validateRequestedKeyAndUsage(csr.publicKey());
        profile.validateSubjectNames(subject, csr.requestedNames());

        IssuedCertificate issued = ca.sign(
            subject,
            csr.publicKey(),
            profile
        );
        certificates.save(issued.metadata());
        return issued;
    }
}
~~~

Các interface là abstraction do ứng dụng/PKI provider cung cấp. CsrVerifier phải xác minh chữ ký CSR và key constraints; subject names phải được tạo/cho phép từ directory/policy, không tin trực tiếp SAN do requester tự khai. CA private key phải được bảo vệ trong HSM/KMS hoặc cơ chế tương đương.

## 21. Ma trận kiểm thử credential issuance

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Requester không được phép cấp credential | Từ chối |
| Request body đổi accountId/tenantId | Không làm thay đổi subject/policy server-side |
| Subject disabled hoặc offboarded | Từ chối issuance |
| Scope vượt quyền requester/client | Từ chối hoặc chỉ cấp scope được duyệt |
| Hai request retry cùng idempotency key | Không tạo credential trùng |
| API key được sinh | Secret có entropy cao, chỉ hiển thị một lần |
| Database bị đọc | Chỉ có verifier/hash, không có plaintext API key |
| API key pending activation được dùng | Verifier từ chối |
| API key hết hạn/revoked | Verifier từ chối |
| API key đúng nhưng audience sai | Resource server từ chối |
| WebAuthn registration challenge sai | RP từ chối |
| Credential ID đã thuộc account khác | Không cho liên kết trùng |
| TOTP seed chưa xác minh | Credential vẫn pending |
| CSR signature/proof-of-possession sai | CA từ chối |
| CSR yêu cầu SAN không thuộc subject | CA từ chối |
| Certificate EKU/key usage không phù hợp | Verifier từ chối cho purpose đó |
| Certificate chain hợp lệ nhưng SAN sai | Verifier từ chối identity mapping |
| Issuance request chưa được approver duyệt | Không phát hành |
| Requester tự phê duyệt request của mình | Separation-of-duties chặn |
| Secret xuất hiện trong application log | Secret scanner phát hiện; log phải được sửa/redact |
| Credential owner bị offboarded | Credential bị suspend/revoke theo policy |
| Rotation hoàn tất | Credential cũ bị revoke sau overlap window |
| Revocation provider lỗi | Trạng thái pending/retry được ghi nhận; không báo hoàn tất sai |
| Backup restore | Không làm sống lại credential đã revoked/expired |

Kiểm thử trong môi trường test bằng subject, key, certificate và secret giả lập. Không sử dụng private key, client secret hoặc API key production trong fixture hoặc báo cáo.

## 22. Tình huống phân tích

### Tình huống A: API key được cấp với quyền quá rộng

Một developer yêu cầu key để đọc báo cáo. Issuance service cấp key có quyền admin trên tất cả tenant vì client template mặc định dùng full access.

**Phân tích:** lỗi nằm ở policy cấp phát. Lấy scope từ request đã được phê duyệt, giới hạn audience/tenant, cấp key riêng cho workload và đặt expiry/owner rõ ràng.

### Tình huống B: CA ký SAN do CSR tự khai

Một workload gửi CSR yêu cầu SAN của service quản trị. CA chỉ kiểm tra chữ ký CSR rồi cấp certificate.

**Phân tích:** proof-of-possession chỉ chứng minh requester kiểm soát private key, không chứng minh họ có quyền nhận identity trong SAN. CA phải xác minh requester và map SAN từ inventory/policy.

### Tình huống C: Secret được gửi qua email

Ứng dụng tạo client secret dài hạn rồi gửi plaintext qua email để developer copy.

**Phân tích:** mailbox và email archive tạo thêm bản sao secret. Dùng secret manager/one-time display, hạn chế scope, rotation và audit; không log hoặc gửi lại plaintext.

### Tình huống D: Credential được cấp nhưng chưa activation

Hệ thống tạo TOTP seed và đánh dấu active ngay khi hiển thị QR. User không quét QR, nhưng seed vẫn được chấp nhận.

**Phân tích:** issuance chưa chứng minh holder kiểm soát authenticator. Giữ pending cho đến khi user gửi mã TOTP hợp lệ; hủy seed pending khi hết hạn.

### Tình huống E: Workload credential còn sống sau khi service bị xóa

Một service account bị xóa khỏi catalog nhưng certificate/API key vẫn active và có thể gọi API.

**Phân tích:** provisioning/offboarding chưa gắn với credential lifecycle. Khi workload bị disable, phát sự kiện suspend/revoke, kiểm tra verifier và inventory, đồng thời theo dõi thời gian propagation.

## 23. Quy trình thiết kế và vận hành

Trước khi phát hành credential, hãy xác định:

1. Issuer/authority nào có quyền cấp loại credential này?
2. Subject/requester đã được xác minh và được phép nhận credential chưa?
3. Credential đại diện cho user, client, device hay workload?
4. Key/secret do ai tạo; private key có rời khỏi holder không?
5. Credential được gắn với purpose, audience, scope, tenant và expiry nào?
6. Có yêu cầu approval, dual control hoặc proof-of-possession không?
7. Delivery channel có phù hợp và được bảo vệ không?
8. Credential có pending/activation flow hay được active ngay theo policy?
9. Secret/private key/public key/certificate được lưu ở đâu và ai có quyền truy cập?
10. Inventory có owner, issuer, status, expiry và last-used không?
11. Rotation/renewal/revocation và overlap window được thiết kế thế nào?
12. Khi account/workload offboarded, credential downstream được thu hồi ra sao?
13. Audit có đủ truy vết mà không lưu secret không?
14. Có kiểm thử mis-issuance, subject substitution, scope escalation, duplicate issuance và partial failure không?

## 24. Ghi nhớ trọng tâm

- **Credential issuance là quyết định cấp quyền tin cậy.** Không chỉ tạo secret; phải xác minh subject, requester, purpose và authority.
- **Identity proofing, issuance, enrollment và authentication là các hoạt động khác nhau.**
- **Phân biệt server-generated secret với holder-generated key pair.** Private key nên ở holder/authenticator khi mô hình cho phép.
- **Proof-of-possession không tự chứng minh quyền nhận identity.** CSR ký hợp lệ vẫn cần CA kiểm tra subject/SAN.
- **Least privilege phải được áp dụng ngay khi cấp.** Giới hạn scope, audience, tenant, expiry và owner.
- **Credential cần trạng thái pending/active/suspended/revoked/expired.** Chưa activation thì chưa được sử dụng.
- **Delivery là một trust boundary.** Hiển thị secret một lần, bảo vệ kênh và không ghi log.
- **Rotation/revocation phải được thiết kế từ đầu.** Không để credential mồ côi hoặc active vô thời hạn.
- **Audit và inventory không được chứa bearer secret/private key.**
- **Credential hợp lệ vẫn cần authorization.** Verifier phải kiểm tra purpose, audience, scope và quyền trên resource.

Credential issuance an toàn bắt đầu từ authority và subject đúng, tiếp tục qua việc tạo/tiếp nhận key hoặc secret, binding với mục đích, phân phối và activation có xác minh. Khi inventory, rotation và revocation được thiết kế cùng lúc, hệ thống có thể cấp credential có kiểm soát và thu hồi chúng kịp thời khi danh tính, thiết bị hoặc workload thay đổi.
