# Credential retention: lưu giữ credential đúng thời hạn và mục đích

> **Chương:** Compliance  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào credential retention: xác định dữ liệu xác thực nào cần tồn tại, lưu trong bao lâu, ai được phép truy cập, khi nào phải thu hồi hoặc xóa, và cách chứng minh việc xử lý tuân thủ chính sách mà không giữ secret lâu hơn nhu cầu.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt retention period, credential validity, session lifetime và legal hold.
2. Lập inventory dữ liệu xác thực theo loại, mục đích, owner và nơi lưu.
3. Áp dụng data minimization và retention schedule cho password, MFA, passkey, token, certificate và API key.
4. Phân biệt secret cần xóa với metadata/audit evidence cần giữ.
5. Thiết kế revoke, delete, archive và crypto-shredding theo vòng đời dữ liệu.
6. Xử lý backup, replica, cache, log và dữ liệu trong hệ thống downstream.
7. Áp dụng legal hold và incident preservation có giới hạn, approval và audit.
8. Thiết kế access control, encryption, key management và evidence cho retention.
9. Triển khai retention workflow bằng Java/Spring và kiểm thử deletion/expiry.
10. Xây dựng governance, ownership và kiểm tra định kỳ để chứng minh chính sách được thực thi.

## 2. Credential retention là gì?

**Credential retention** là tập hợp chính sách và cơ chế xác định dữ liệu xác thực nào được lưu giữ, vì mục đích nào, trong thời hạn bao lâu, ở đâu, ai có thể truy cập và điều kiện nào kích hoạt việc thu hồi hoặc xóa.

Retention không đồng nghĩa với việc giữ credential cho tới khi hết hạn. Một API key có thể còn hiệu lực theo hệ thống nhưng không còn cần thiết sau khi integration bị gỡ bỏ. Ngược lại, một audit event về việc key đã bị revoke có thể cần được giữ lâu hơn chính key để phục vụ điều tra hoặc kiểm toán.

Các câu hỏi cốt lõi:

- Dữ liệu này có cần thiết để xác thực hoặc vận hành không?
- Mục đích xử lý đã được xác định và phê duyệt chưa?
- Thời hạn lưu tối đa là bao lâu?
- Khi credential hết hạn hoặc bị revoke, secret và metadata được xử lý thế nào?
- Dữ liệu có bản sao trong backup, replica, cache, log hoặc support bundle không?
- Có legal hold hoặc incident preservation hợp lệ không?
- Ai chịu trách nhiệm xóa và chứng minh việc xóa?

Retention tốt giảm lượng dữ liệu nhạy cảm có thể bị đánh cắp, giới hạn hậu quả của breach và giúp tổ chức thực hiện nghĩa vụ privacy, security và governance.

## 3. Phân biệt retention với validity và lifetime

Các khái niệm này có liên quan nhưng không thể dùng thay nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Credential validity | Khoảng thời gian credential được chấp nhận | Certificate còn hiệu lực tới ngày hết hạn |
| Session lifetime | Thời gian một phiên có thể được sử dụng | Session tối đa 8 giờ |
| Token lifetime | Thời hạn của token | Access token 10 phút |
| Retention period | Thời gian dữ liệu được lưu trong hệ thống | Audit metadata giữ 1 năm theo policy |
| Revocation | Vô hiệu hóa credential trước hoặc tại thời điểm kết thúc | API key bị thu hồi ngay khi integration bị gỡ |
| Deletion | Xóa dữ liệu khỏi hệ thống lưu trữ theo quy trình | Xóa secret version không còn cần |
| Legal hold | Tạm dừng xóa dữ liệu thuộc phạm vi bảo toàn hợp lệ | Giữ audit evidence cho vụ việc đang điều tra |

Một certificate đã hết hạn không nhất thiết bị xóa khỏi kho audit ngay lập tức; metadata phát hành/thu hồi có thể cần lưu để xác minh chữ ký hoặc điều tra. Nhưng private key không nên được giữ chỉ vì certificate record còn cần cho audit.

## 4. Nguyên tắc thiết kế retention

1. **Purpose limitation:** mỗi loại dữ liệu có mục đích rõ ràng.
2. **Data minimization:** chỉ thu thập và giữ những gì cần thiết.
3. **Storage limitation:** không lưu lâu hơn thời hạn đã xác định.
4. **Least privilege:** chỉ người và workload có nhiệm vụ mới được truy cập.
5. **Secure deletion:** xóa khỏi nơi lưu chính và xử lý bản sao theo kế hoạch.
6. **Lifecycle consistency:** revoke, rotate, expire và delete phải có semantics rõ.
7. **Accountability:** có owner, policy version, evidence và audit trail.
8. **Privacy by design:** không biến metadata thành hồ sơ theo dõi quá mức.
9. **Recoverability with controls:** backup phục vụ khôi phục nhưng không hồi sinh credential đã revoke.
10. **Exception governance:** legal hold và emergency retention có phạm vi, approval và expiry/review.

Không đặt một thời hạn chung cho mọi loại credential. Password verifier, TOTP seed, passkey public key, refresh token, private key và audit event có mục đích cùng rủi ro khác nhau.

## 5. Data inventory và phân loại dữ liệu xác thực

Trước khi đặt retention period, cần biết dữ liệu nào đang tồn tại và bản sao ở đâu.

| Nhóm dữ liệu | Ví dụ | Mức nhạy cảm và lưu ý |
|---|---|---|
| Authentication secret | Password, TOTP seed, API key | Bí mật; hạn chế tối đa và mã hóa phù hợp |
| Password verifier | Salt, hash, algorithm parameters | Nhạy cảm; có thể hỗ trợ offline guessing nếu lộ |
| Private key material | Client signing key, TLS key | Rất nhạy cảm; ưu tiên HSM/KMS, không export |
| Public credential material | Passkey public key, certificate | Không phải secret nhưng vẫn gắn với danh tính và cần bảo vệ integrity/privacy |
| Token/session material | Refresh token, session handle, recovery token | Bearer material; có thể cấp quyền trực tiếp |
| Credential metadata | Credential ID, type, created_at, status | Có thể nhận diện user hoặc cấu trúc hệ thống |
| Security/audit evidence | Issue, read, rotate, revoke events | Cần integrity, access control và retention rõ |
| Diagnostic data | Error, trace, dump, support bundle | Có thể vô tình chứa secret/PII |
| Backup/replica | Snapshot, archive, replica log | Bản sao vẫn chịu yêu cầu bảo vệ và retention |

Inventory nên ghi owner, system of record, purpose, classification, encryption, region, downstream copies, retention trigger, retention duration, deletion method và evidence source.

## 6. Tìm mọi bản sao, không chỉ database chính

Credential data có thể xuất hiện ở nhiều nơi:

- Secret manager hoặc vault.
- Primary database và read replica.
- Cache, Redis và local memory.
- Message queue và dead-letter queue.
- Backup, snapshot và archive.
- Application log, access log và distributed trace.
- APM, crash dump và heap dump.
- CI/CD variable, build artifact và test report.
- Browser storage, mobile secure storage và local backup.
- Support ticket, incident attachment và export file.
- Data warehouse hoặc analytics pipeline.

Một quy trình delete chỉ xóa record trong primary database chưa chứng minh dữ liệu đã được xử lý hết. Cần xác định bản sao, TTL, retention lock, backup expiry và trách nhiệm của downstream processor.

Không copy secret vào analytics hoặc data warehouse để tiện báo cáo. Nếu chỉ cần biết credential được tạo/thu hồi lúc nào, hãy lưu event metadata không chứa secret value.

## 7. Retention schedule

Retention schedule quy định loại dữ liệu, mục đích, trigger bắt đầu tính thời gian, thời hạn, cách xử lý khi hết hạn và ngoại lệ.

Ví dụ minh họa để thiết kế policy, không phải thời hạn pháp lý áp dụng chung:

| Dữ liệu | Trigger | Chính sách xử lý gợi ý |
|---|---|---|
| Password plaintext | Không được lưu | Không tạo retention period; loại bỏ ngay khỏi processing path |
| Password verifier | Account closure hoặc verifier replacement | Xóa khi không còn mục đích xác thực/khôi phục và hết hold hợp lệ |
| TOTP seed | Factor revoke/re-enroll | Xóa secret sau khi revoke; giữ metadata/audit tối thiểu |
| Passkey public key record | Credential removed | Vô hiệu hóa và xóa theo policy; giữ evidence tối thiểu nếu cần |
| API key secret | Key revoked/rotated | Không reveal lại; xóa secret cũ theo workflow |
| Refresh token | Expiry/revoke/family termination | Không chấp nhận sau revoke; xóa hoặc tombstone metadata theo policy |
| Session state | Logout/expiry/revoke | Invalidate ngay; cleanup record theo TTL |
| Private signing key | Key retirement/compromise | Disable/revoke; destroy theo key management policy |
| Certificate metadata | Expiry/revocation | Có thể giữ metadata phục vụ validation/audit theo schedule |
| Audit event | Event creation | Giữ theo purpose, legal/regulatory requirement và schedule đã duyệt |
| Diagnostic bundle | Incident/support closure | Xóa sau thời hạn điều tra/retention đã phê duyệt |

Retention schedule phải được Legal/Privacy/Security và data owner xác nhận theo jurisdiction, hợp đồng và ngành. Không suy ra thời hạn luật định chỉ từ loại dữ liệu.

## 8. Xác định retention trigger và thời điểm bắt đầu

Một thời hạn chỉ có ý nghĩa khi biết nó bắt đầu từ đâu:

- Từ lúc credential được tạo.
- Từ lần sử dụng cuối.
- Từ lúc credential bị revoke.
- Từ lúc account đóng.
- Từ lúc incident kết thúc.
- Từ lúc audit event được tạo.
- Từ lúc legal hold được gỡ.

Không chọn trigger chỉ vì dễ triển khai. Ví dụ, tính retention của session từ lần tạo có thể khác với tính từ lần kết thúc; audit evidence thường tính từ thời điểm event được ghi.

Với rolling retention, phải xác định sự kiện nào reset clock. Nếu mọi lần đọc secret đều kéo dài retention vô hạn, dữ liệu có thể không bao giờ được xóa. Chỉ reset khi policy có mục đích rõ và được phê duyệt.

## 9. Password và password verifier

Password plaintext không được lưu trữ. Hệ thống nên chỉ giữ verifier được tạo bằng password hashing scheme phù hợp, salt riêng và tham số cost đã được quản lý.

Retention cần xem:

- Verifier còn cần khi account active.
- Khi password đổi, verifier cũ không còn dùng để đăng nhập.
- Password history chỉ được giữ nếu policy có mục đích hợp lệ; lưu verifier lịch sử cũng làm tăng lượng dữ liệu nhạy cảm.
- Reset token có lifetime ngắn, one-time và bị xóa/đánh dấu consumed sau khi sử dụng.
- Account đóng cần xóa verifier khi hết mục đích và không có hold hợp lệ.
- Pepper/KMS key có vòng đời và access policy riêng.

Không giữ password cũ dưới dạng plaintext để hỗ trợ support. Không log verifier đầy đủ trong error hoặc debug output. Nếu cần password history để ngăn reuse, giới hạn số lượng, thời hạn và quyền truy cập; không giữ vô hạn.

## 10. MFA seed, recovery code và passkey

### TOTP seed

TOTP seed là secret có thể tạo mã xác thực. Nó cần được mã hóa khi lưu, chỉ giải mã trong phạm vi verify, và bị xóa hoặc làm không thể sử dụng khi factor bị revoke.

Khi user thay authenticator:

1. Xác minh user theo policy.
2. Enroll seed mới ở trạng thái pending.
3. Xác minh proof từ authenticator mới.
4. Kích hoạt factor mới và revoke factor cũ theo transaction.
5. Xóa hoặc disable seed cũ.
6. Ghi audit metadata, không ghi seed hoặc provisioning URI.

### Recovery code

Recovery code thường chỉ hiển thị một lần. Hệ thống nên lưu verifier/hash phù hợp, đánh dấu consumed nguyên tử và xóa/disable khi dùng hoặc khi bộ code được thay thế.

Không giữ bản plaintext trong email, ticket, log hoặc support database.

### Passkey

Passkey/WebAuthn thường lưu public key và credential metadata ở server; private key nằm trong authenticator/platform. Public key không phải secret như private key nhưng credential ID, user handle, transports và attestation metadata vẫn có thể liên kết với danh tính/thiết bị.

Khi passkey bị xóa:

- Không còn chấp nhận credential đó cho authentication.
- Gỡ binding khỏi account theo transaction.
- Xóa metadata không còn mục đích theo retention policy.
- Giữ audit evidence tối thiểu về thời điểm và actor thực hiện.
- Không yêu cầu server lưu private key của authenticator.

## 11. API key, client secret và workload credential

API key/client secret là bearer credential. Nếu bị lộ, người có key có thể gọi API trong phạm vi được cấp.

Retention/lifecycle:

- Cấp key có owner, purpose, scope, environment và expiry/rotation policy.
- Secret value chỉ hiển thị theo thiết kế reveal-once.
- Metadata có thể giữ key ID, created_at, last_used_at, status và owner.
- Khi rotate, key mới phải hoạt động trước khi key cũ bị revoke nếu cần overlap.
- Key cũ bị disable/revoke ngay khi hết overlap hoặc có compromise.
- Secret cũ được xóa theo policy; audit metadata về rotation/revoke có thể được giữ lâu hơn.
- Workload offboarding phải thu hồi credential, service identity và permission liên quan.

Không giữ API key cũ để rollback vô thời hạn. Rollback cần cơ chế được phê duyệt và key thay thế an toàn; nếu key cũ đã compromise thì không tái kích hoạt.

## 12. Token, session và federation artifacts

Các artifact cần policy riêng:

- Access token: lifetime ngắn; không cần lưu plaintext lâu hơn nhu cầu nếu có thể xác minh stateless.
- Refresh token: lưu verifier hoặc dạng bảo vệ phù hợp; rotation, reuse detection và revocation.
- ID token: thường là artifact truyền qua protocol; không lưu lâu nếu không có purpose rõ.
- Authorization code: one-time, short-lived, consumed atomically.
- OAuth state/nonce/PKCE verifier: gắn transaction, xóa sau callback hoặc timeout.
- SAML assertion: không ghi raw assertion vào log; nếu phải lưu evidence, mã hóa, giới hạn access và retention.
- Session handle: invalidate ngay khi logout/revoke; cleanup theo TTL.
- Recovery grant: one-time, scope hẹp và expiry ngắn.

Không giữ raw bearer token để phục vụ audit. Ghi token ID/reference, issuer, audience, scope, timestamps và lifecycle event ở mức cần thiết.

## 13. Certificate và private key retention

Certificate và private key có vòng đời khác nhau:

- Certificate là public artifact có validity, issuer, serial và status.
- Private key là secret material cần bảo vệ nghiêm ngặt.
- Public key/certificate metadata có thể cần để verify chữ ký cũ hoặc điều tra.
- Private key đã retired có thể cần destroy hoặc archive theo key management policy; không được export tùy tiện chỉ để giữ backup.

Khi key bị compromise:

1. Disable/revoke key theo incident policy.
2. Phát hành key mới qua trust process.
3. Cập nhật verifier/consumer và trust bundle.
4. Đánh giá token/certificate/chữ ký phát hành bằng key cũ.
5. Giữ metadata và evidence phục vụ điều tra.
6. Destroy private key material khi đã bảo toàn yêu cầu pháp lý/kỹ thuật hợp lệ.

Không xóa public certificate metadata quá sớm nếu cần kiểm tra chữ ký lịch sử; nhưng cũng không lấy nhu cầu lưu metadata làm lý do giữ private key có khả năng ký mới.

## 14. Credential lifecycle và retention state machine

Một credential có thể đi qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> ACTIVE: approved and issued
    REQUESTED --> REJECTED
    ACTIVE --> ROTATING: rotation requested
    ROTATING --> ACTIVE: new credential activated
    ACTIVE --> REVOKED: revoke / compromise / offboarding
    ACTIVE --> EXPIRED: validity ended
    REVOKED --> RETENTION_PENDING: preserve required metadata
    EXPIRED --> RETENTION_PENDING
    RETENTION_PENDING --> DELETED: retention elapsed
    RETENTION_PENDING --> HOLD: approved legal hold
    HOLD --> RETENTION_PENDING: hold released
    DELETED --> [*]
    REJECTED --> [*]
~~~

State machine cần phân biệt credential authentication state với data retention state. Ví dụ credential có thể REVOKED nhưng metadata vẫn RETENTION_PENDING. Không dùng một cột status duy nhất để biểu diễn đồng thời validity, revocation và deletion.

## 15. Revoke, delete, archive và tombstone

Các hành động có ý nghĩa khác nhau:

- **Revoke:** credential không còn được chấp nhận.
- **Disable:** tạm ngừng sử dụng, có thể được kích hoạt lại nếu policy cho phép.
- **Delete:** xóa dữ liệu khỏi nơi lưu.
- **Archive:** chuyển sang kho lưu giữ với access hạn chế.
- **Tombstone:** giữ một dấu vết tối thiểu rằng record đã bị xóa/revoke, tránh import hoặc restore làm sống lại.
- **Crypto-shredding:** hủy key mã hóa dữ liệu để ciphertext còn lại không thể giải mã theo thiết kế.

Thứ tự thường là revoke trước, sau đó xóa hoặc archive khi đã hết mục đích. Không chờ tới ngày xóa mới vô hiệu hóa credential.

Tombstone chỉ nên giữ metadata tối thiểu như opaque ID, status, timestamp và reason code. Không lưu secret value hoặc PII không cần thiết.

## 16. Secure deletion và crypto-shredding

Xóa logic khỏi database không đồng nghĩa dữ liệu đã biến mất khỏi mọi media:

- Database page có thể còn trong free space.
- Replica có thể chưa nhận delete.
- Backup snapshot có thể chứa bản cũ.
- Cache hoặc local disk có thể còn record.
- Queue/dead-letter có thể chứa payload.
- Log/trace có thể đã copy secret.

Các phương pháp:

- Delete theo lifecycle và xác nhận downstream.
- TTL/expiration cho cache và ephemeral record.
- Purge/compaction theo khả năng storage engine.
- Key destruction khi dữ liệu được mã hóa bằng per-record/per-tenant key và thiết kế hỗ trợ crypto-shredding.
- Backup expiry theo schedule.
- Secure media sanitization theo nền tảng và threat model.

Crypto-shredding chỉ hiệu quả nếu mọi bản sao ciphertext đều phụ thuộc vào key đã hủy và key không có bản sao khôi phục ngoài kiểm soát. Phải kiểm tra key hierarchy, wrapped key backup, replica và export. Không tuyên bố dữ liệu đã bị xóa vật lý chỉ vì ứng dụng xóa row.

## 17. Backup, replica và disaster recovery

Backup có thể cần tồn tại lâu hơn primary data theo recovery policy, nhưng điều này tạo nguy cơ credential đã revoke xuất hiện lại khi restore.

Kiểm soát:

- Mã hóa backup và giới hạn restore authority.
- Retention riêng cho full/incremental backup và snapshot.
- Có backup catalog, owner và expiry.
- Restore vào isolated environment trước khi mở traffic.
- Reconcile account status, credential revocation và security epoch sau restore.
- Không khôi phục private key đã compromise.
- Có quy trình xóa backup hết hạn và xác minh.
- Kiểm tra replica lag và delete propagation.

Một pattern hữu ích là lưu revocation/security journal hoặc epoch trong miền dữ liệu có độ bền phù hợp, để sau restore có thể áp dụng các thay đổi bảo mật xảy ra sau thời điểm backup.

## 18. Legal hold và incident preservation

Legal hold có thể yêu cầu tạm dừng xóa một số records liên quan tới vụ việc. Incident response cũng có thể cần bảo toàn evidence trước khi rotate hoặc purge.

Một hold hợp lệ cần:

- Authority/owner phê duyệt.
- Matter/incident reference.
- Dataset/resource scope rõ ràng.
- Purpose và thời điểm bắt đầu.
- Người được phép truy cập.
- Review date và điều kiện release.
- Audit mọi lần truy cập/export.
- Xử lý lại retention schedule sau khi hold được gỡ.

Không đặt hold vô thời hạn cho toàn bộ credential store chỉ vì có một incident. Hold chỉ áp dụng cho dữ liệu trong phạm vi cần thiết và phải được review định kỳ.

Nếu private key đang bị compromise, bảo toàn evidence không có nghĩa tiếp tục chấp nhận key đó. Có thể giữ forensic copy được mã hóa và cách ly theo quy trình được phê duyệt, trong khi operational key bị revoke ngay.

## 19. Privacy và data subject lifecycle

Credential metadata có thể là dữ liệu cá nhân hoặc dữ liệu có khả năng liên kết với cá nhân:

- User ID, email, phone.
- Passkey credential ID và device metadata.
- MFA enrollment history.
- Last-used timestamp.
- IP/device/location context.
- Recovery events.
- Account linking records.
- Session history.

Khi account đóng hoặc có yêu cầu xóa hợp lệ, cần xác định:

- Credential nào phải revoke ngay.
- Secret nào phải delete.
- Metadata nào cần giữ cho fraud/security/legal purpose.
- Audit evidence nào có retention riêng.
- Bản sao downstream nào cần xóa hoặc hạn chế.
- Có legal hold hay nghĩa vụ bắt buộc nào không.

Không xóa bừa audit evidence nếu cần bảo toàn theo nghĩa vụ hợp lệ; cũng không dùng security purpose chung chung để giữ mọi dữ liệu vô thời hạn. Cần phân tích mục đích, căn cứ xử lý và thời hạn theo từng nhóm.

## 20. Access control trong thời gian retention

Dữ liệu càng được giữ lâu, số người hoặc hệ thống có thể tiếp cận càng cần được giới hạn.

Phân tách quyền:

- Runtime workload: chỉ đọc credential đang active và đúng scope.
- Credential owner: quản lý lifecycle trong phạm vi được giao.
- Security operator: revoke/rotate theo approval.
- Auditor: đọc metadata/evidence, không đọc secret.
- Backup operator: vận hành backup, không mặc nhiên decrypt nội dung.
- Privacy/legal role: quản lý hold và retention decision theo thẩm quyền.
- Database administrator: không tự động có quyền plaintext secret nếu encryption boundary được thiết kế riêng.

Mọi privileged read/export/restore cần audit. Quyền đọc metadata không đồng nghĩa quyền reveal secret.

## 21. Encryption và key management cho retained data

Credential material và metadata nhạy cảm cần được bảo vệ khi lưu và truyền:

- TLS cho network transfer.
- Encryption at rest cho database/object storage.
- Envelope encryption với KMS/HSM khi phù hợp.
- Key separation theo environment/tenant/data class.
- Rotation và access policy cho encryption key.
- Audit key use, decrypt và export.
- Backup key được bảo vệ độc lập.
- Không hard-code encryption key trong source/config.

Encryption không thay retention. Dữ liệu mã hóa nhưng giữ vô thời hạn vẫn tạo rủi ro; key có thể bị compromise hoặc quyền decrypt bị cấp sai.

Nếu dùng crypto-shredding, key lifetime phải gắn với data lifecycle và có bằng chứng hủy theo policy. Cần xác minh không còn wrapped key hoặc key backup có thể khôi phục.

## 22. Retention trong log, metric, trace và audit

Telemetry có thể chứa credential metadata hoặc secret vô tình:

- Access log ghi query parameter chứa token.
- Trace ghi Authorization header.
- Exception ghi connection string.
- Audit event ghi secret value.
- Metric label chứa user/session ID.
- Support bundle chứa heap dump.

Tách retention theo loại:

| Telemetry | Thiết kế retention |
|---|---|
| Security audit | Theo policy evidence và yêu cầu áp dụng; integrity/access control cao |
| Application log | Ngắn hơn hoặc theo operational need; redact từ source |
| Metrics | Aggregate, không chứa identifier; retention theo monitoring use |
| Trace | Sampling và retention ngắn hơn nếu có request context nhạy cảm |
| Diagnostic dump | Chỉ theo incident, access rất hạn chế, expiry rõ |
| Immutable archive | Retention lock theo policy và legal hold |

Không copy raw credential vào audit để “giữ bằng chứng”. Giữ event metadata, key ID, version, actor, action và outcome.

## 23. Deletion workflow và evidence

Một deletion workflow cần có thể truy vết:

1. Xác định record và data class.
2. Kiểm tra owner, purpose, retention deadline và legal hold.
3. Revoke credential trước nếu còn khả năng sử dụng.
4. Tạo deletion job với idempotent operation ID.
5. Xóa primary record và secret material.
6. Gửi deletion event tới replica, cache, queue và downstream processor.
7. Xác nhận các bản sao online đã được xử lý.
8. Đưa backup vào expiry schedule hoặc áp dụng crypto-shredding nếu thiết kế hỗ trợ.
9. Ghi audit evidence về outcome, timestamp và system acknowledgement.
10. Reconcile job thất bại và retry an toàn.

Evidence nên chứng minh hành động đã xảy ra mà không chứa secret. Có thể ghi opaque resource reference, data class, policy version, deletion method, systems acknowledged và result.

Không tuyên bố xóa toàn bộ nếu backup immutable vẫn còn trong retention window. Báo rõ trạng thái: operational access revoked, primary deleted, replicas processed, backup expires at date hoặc hold remains.

## 24. Java/Spring: retention metadata và policy

Ví dụ model metadata tách biệt khỏi secret:

~~~java
record CredentialRecord(
    UUID id,
    String ownerId,
    String credentialType,
    Instant createdAt,
    Instant expiresAt,
    Instant revokedAt,
    Instant deleteAfter,
    String status,
    String policyVersion
) {}
~~~

Không đưa secret value vào record audit/retention. Secret có thể nằm trong vault hoặc encrypted store riêng; record trên chỉ là metadata minh họa.

### Tính thời điểm xóa

~~~java
class RetentionPolicy {
    private final Clock clock;
    private final Duration revokedMetadataRetention;

    RetentionPolicy(
            Clock clock,
            Duration revokedMetadataRetention) {
        this.clock = clock;
        this.revokedMetadataRetention = revokedMetadataRetention;
    }

    Instant deleteAfter(Instant revokedAt) {
        return revokedAt.plus(revokedMetadataRetention);
    }

    boolean eligibleForDeletion(
            Instant deleteAfter,
            boolean legalHold) {
        return !legalHold
            && !clock.instant().isBefore(deleteAfter);
    }
}
~~~

Đây là ví dụ đơn giản. Production cần kiểm tra policy version, jurisdiction, data owner, legal hold, dependency copies và trạng thái revoke. Không tính retention chỉ từ một duration hard-coded trong application.

## 25. Java/Spring: idempotent deletion job

~~~java
@Service
class CredentialDeletionService {
    private final CredentialRepository repository;
    private final SecretVault vault;
    private final RetentionPolicyService policies;
    private final DeletionAuditPublisher audit;

    void deleteIfEligible(UUID credentialId) {
        CredentialRecord record = repository.findById(credentialId)
            .orElse(null);
        if (record == null) {
            return;
        }

        RetentionDecision decision = policies.evaluate(record);
        if (!decision.eligible()) {
            audit.skipped(record.id(), decision.reasonCode());
            return;
        }

        vault.deleteSecret(record.id());
        repository.markDeleted(record.id(), decision.policyVersion());
        audit.deleted(record.id(), decision.policyVersion());
    }
}
~~~

Đây là pseudocode. Production cần transaction/outbox hoặc workflow orchestration vì vault và database thường không chia sẻ một ACID transaction. Xử lý retry/idempotency để job chạy lại không gây lỗi hoặc đánh dấu deleted khi secret chưa được xử lý. Nếu vault delete thành công nhưng database update thất bại, workflow phải có reconciliation.

### Legal hold check

Legal hold cần được kiểm tra gần thời điểm thực hiện deletion, không chỉ khi job được tạo. Hold có thể được đặt trong lúc job đang chờ. Với thao tác destructive, cần version/lock hoặc compare-and-set để tránh race giữa hold và delete.

## 26. Governance và ownership

Mỗi data class cần có:

- Business/data owner.
- Security owner.
- Privacy/Legal contact khi cần.
- System of record.
- Approved purpose.
- Retention schedule/version.
- Deletion method.
- Backup/replica owner.
- Legal hold authority.
- Evidence location.
- Review cadence.

Review định kỳ:

- Tìm secret không có owner hoặc không có last-used metadata.
- Tìm credential đã hết hạn nhưng vẫn active.
- Tìm key không có expiry/rotation policy.
- Tìm log/trace chứa secret hoặc PII.
- Kiểm tra deletion job backlog.
- Kiểm tra backup vượt retention.
- Kiểm tra legal hold quá hạn review.
- Kiểm tra quyền đọc/export.

Không để mỗi service tự đặt retention tùy ý mà không có policy registry và governance thống nhất.

## 27. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng một retention period cho mọi credential | Lưu quá lâu hoặc xóa quá sớm | Schedule theo data class/purpose |
| Coi expiry là deletion | Secret cũ vẫn tồn tại và có thể bị lộ | Revoke, delete và xử lý bản sao |
| Giữ plaintext password để support | Credential exposure nghiêm trọng | Không lưu plaintext; dùng verifier |
| Giữ API key cũ vô thời hạn để rollback | Key bị compromise vẫn có thể được dùng lại | Overlap có giới hạn và revoke |
| Xóa primary row nhưng quên replica/backup | Dữ liệu còn ở bản sao | Inventory downstream và backup expiry |
| Restore backup làm sống lại revoked key | Credential cũ được chấp nhận | Reconcile revocation journal/security epoch |
| Giữ private key vì cần audit certificate | Có thể ký mới bằng key retired | Giữ public metadata, destroy private material theo policy |
| Legal hold không có review | Dữ liệu bị giữ vô hạn | Scope, authority, review date và release |
| Dùng security purpose chung chung | Retention vượt mục đích | Gắn purpose và căn cứ cụ thể |
| Log raw token để điều tra | Log trở thành bearer credential store | Token reference và lifecycle metadata |
| Deletion job không idempotent | Retry gây trạng thái không nhất quán | Operation ID, state machine và reconciliation |
| Crypto-shredding nhưng key backup còn | Dữ liệu vẫn có thể giải mã | Kiểm tra toàn bộ key hierarchy và backup |
| Không audit quyền đọc/export | Không biết ai truy cập dữ liệu retained | Audit privileged access |
| Xóa evidence cùng lúc với secret | Không thể chứng minh revoke/rotation | Tách secret lifecycle và audit retention |

## 28. Ma trận kiểm thử credential retention

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Credential active trong retention window | Được lưu và chỉ caller đủ quyền mới truy cập |
| Credential hết validity | Không được xác thực dù record còn metadata |
| Credential bị revoke | Bị từ chối ngay theo revocation contract |
| Secret hết retention | Deletion workflow được thực hiện |
| Account đóng | Credential bị revoke; dữ liệu được xử lý theo schedule/hold |
| TOTP factor bị remove | Seed không còn được verify; metadata xử lý theo policy |
| Passkey bị remove | Credential public key record không còn được chấp nhận |
| API key rotate | Key mới hoạt động, key cũ revoke đúng overlap |
| Refresh token bị revoke | Không refresh được; family state đúng contract |
| Authorization code đã consume | Không thể dùng lại |
| Private key retired | Không thể ký; key material xử lý theo key policy |
| Certificate metadata cần giữ | Có thể verify/audit lịch sử mà không giữ private key |
| Legal hold active | Deletion bị dừng trong đúng scope |
| Legal hold released | Retention workflow tiếp tục theo schedule |
| Hold đặt ngay trước deletion | Job kiểm tra lại và không xóa ngoài ý muốn |
| Backup restore | Credential đã revoke không trở lại active |
| Replica lag | Deletion/revoke status được reconcile |
| Cache còn secret cũ | Cache bị invalidate/TTL theo policy |
| Queue chứa secret payload | Payload được xử lý/xóa theo retention và không log |
| Diagnostic log chứa canary secret | Scanner phát hiện; pipeline ngăn hoặc cảnh báo |
| Deletion job chạy hai lần | Kết quả idempotent |
| Vault delete thành công, DB update lỗi | Reconciliation hoàn tất trạng thái |
| DB record đánh dấu deleted nhưng vault còn secret | Test phát hiện inconsistency và không báo complete |
| Crypto-shredding | Mọi key copy/wrapped key cần thiết đã bị hủy theo thiết kế |
| Auditor đọc metadata | Không thể reveal secret |
| Runtime workload đọc secret | Chỉ đúng scope/owner/environment |
| Retention schedule đổi version | Record/job dùng policy version có thể truy vết |
| Deletion evidence export | Export được audit và không chứa secret |

Kiểm thử cả logical access, storage state, replica, cache, backup workflow và audit evidence. Một HTTP response thành công không chứng minh mọi bản sao đã được xử lý.

## 29. Tình huống phân tích

### Tình huống A: API key cũ vẫn dùng được sau rotation

Integration đã được chuyển sang key mới, nhưng key cũ vẫn được chấp nhận nhiều tháng để “phòng trường hợp rollback”.

**Phân tích:** overlap không có deadline biến key cũ thành credential thường trực. Đặt overlap ngắn, theo dõi usage, revoke key cũ và giữ audit metadata thay vì secret.

### Tình huống B: xóa account nhưng giữ TOTP seed

Account đã đóng nhưng seed vẫn còn trong database và có thể được export bởi admin.

**Phân tích:** account closure phải kích hoạt credential lifecycle. Revoke factor, xóa seed theo policy, giới hạn backup retention và giữ audit event tối thiểu.

### Tình huống C: backup restore làm sống lại refresh token

Database được restore từ snapshot trước thời điểm token family bị revoke.

**Phân tích:** cần revocation journal/security epoch độc lập và reconciliation trước khi mở traffic. Không coi backup là source of truth đầy đủ cho security state hiện tại.

### Tình huống D: legal hold giữ toàn bộ vault

Một incident chỉ liên quan tới một service nhưng tổ chức đặt hold toàn bộ secret store không thời hạn.

**Phân tích:** hold phải giới hạn theo matter, resource và purpose; có authority, review date và release. Không giữ secret operational nếu có thể bảo toàn metadata/evidence đã đủ.

### Tình huống E: crypto-shredding nhưng wrapped key còn trong backup

Ứng dụng xóa data key trong database nhưng backup KMS vẫn chứa wrapped key có thể phục hồi.

**Phân tích:** crypto-shredding chưa hoàn tất. Kiểm tra key hierarchy, wrapped key copies, KMS backup và recovery process trước khi xác nhận không thể giải mã.

## 30. Quy trình triển khai credential retention

Trước khi đưa policy vào production, hãy xác định:

1. Data inventory bao phủ primary, replica, cache, queue, log, backup và downstream chưa?
2. Mỗi data class có purpose, owner, classification và system of record chưa?
3. Validity, revocation, retention và deletion được tách riêng chưa?
4. Trigger và retention duration có căn cứ/approval không?
5. Password verifier, TOTP seed, passkey metadata, API key, token và private key có policy riêng không?
6. Credential bị revoke có bị từ chối ngay dù record còn lưu không?
7. Delete workflow có idempotency, audit và reconciliation không?
8. Legal hold có scope, authority, review và release không?
9. Backup restore có thể hồi sinh credential cũ không?
10. Crypto-shredding có bao phủ key hierarchy và backup không?
11. Log/trace/metric/support bundle có secret hoặc PII không?
12. Access control có phân biệt runtime, owner, auditor, operator và backup role không?
13. Retention job backlog/failure có monitoring không?
14. Evidence có chứng minh được revoke, delete và downstream acknowledgement không?
15. Có review định kỳ orphan credential, expired key và hold quá hạn không?

## 31. Ghi nhớ trọng tâm

- **Retention không phải validity.** Credential hết hạn hoặc bị revoke vẫn có thể còn metadata cần giữ; secret operational phải bị vô hiệu hóa ngay khi cần.
- **Mỗi loại credential có vòng đời riêng.** Password verifier, TOTP seed, passkey record, API key, token, certificate và private key không dùng chung một schedule.
- **Data inventory phải bao phủ mọi bản sao.** Primary database không phải nơi duy nhất chứa credential.
- **Revoke trước, delete theo schedule.** Không chờ tới ngày xóa mới ngăn credential được sử dụng.
- **Tách secret khỏi audit evidence.** Giữ actor, action, resource reference, version và outcome; không giữ raw secret.
- **Backup không được hồi sinh credential đã revoke.** Reconcile security epoch/revocation state sau restore.
- **Legal hold có scope và review.** Không biến ngoại lệ thành retention vô thời hạn.
- **Crypto-shredding cần hủy mọi đường khôi phục key.** Wrapped key hoặc backup còn dùng được thì dữ liệu chưa thực sự bị vô hiệu hóa theo mục tiêu.
- **Deletion cần evidence và reconciliation.** Không báo hoàn tất nếu replica, cache hoặc vault vẫn còn secret.
- **Retention là trách nhiệm governance.** Data owner, Security, Privacy/Legal và platform operator cần phối hợp.

Credential retention có trách nhiệm giữ lại đúng dữ liệu cần cho xác thực, bảo mật và bằng chứng, đồng thời loại bỏ secret khi mục đích sử dụng kết thúc. Khi lifecycle, schedule, access control, backup, legal hold và deletion evidence được thiết kế thống nhất, tổ chức giảm được rủi ro credential cũ bị lạm dụng và có thể chứng minh dữ liệu được xử lý theo policy đã phê duyệt.
