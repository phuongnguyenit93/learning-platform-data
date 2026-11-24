# Backup credential — Sao lưu credential an toàn và khôi phục có kiểm soát

## 1. Backup credential là gì?

**Backup credential** là việc bảo vệ khả năng khôi phục thông tin và trạng thái cần thiết để người dùng hoặc dịch vụ tiếp tục xác thực sau khi thiết bị, kho dữ liệu hoặc hệ thống chính bị mất, hỏng hay gián đoạn. Dữ liệu cần backup có thể gồm bản ghi credential, public key, metadata, trạng thái thu hồi, cấu hình authenticator, recovery code verifier và các khóa bí mật được phép sao lưu theo policy.

Ví dụ: một nhân viên mất điện thoại chứa ứng dụng TOTP. Nếu tổ chức đã chuẩn bị phương thức dự phòng, người dùng có thể xác minh qua passkey dự phòng hoặc recovery code, sau đó đăng ký TOTP secret mới. Hệ thống vẫn giữ bản ghi binding cũ để điều tra và đánh dấu nó đã thu hồi. Việc khôi phục không có nghĩa sao chép secret cũ sang thiết bị mới một cách tự động.

Trong chương **Lưu trữ credential** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, backup credential kết nối mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần phân biệt dữ liệu có thể sao lưu với bí mật không nên xuất, mô hình hóa ranh giới tin cậy của backup, bảo vệ khóa mã hóa, chống rollback và replay, đồng thời kiểm thử quy trình restore.

**Backup không đồng nghĩa với nhân bản mọi private key hoặc secret.** Một số credential được thiết kế không thể xuất khỏi authenticator; một số khác có thể được đồng bộ qua hệ sinh thái được bảo vệ; có loại nên thu hồi và cấp mới khi mất. Quyết định backup phải dựa trên loại credential, threat model, yêu cầu khôi phục và mức assurance.

## 2. Vì sao cần backup credential?

Backup và recovery chuẩn bị cho nhiều tình huống:

- Người dùng mất hoặc làm hỏng điện thoại, máy tính hay khóa bảo mật.
- Ứng dụng bị gỡ cài đặt hoặc thiết bị được thay mới.
- Kho credential, database hoặc vùng triển khai gặp sự cố.
- Hệ thống bị ransomware hoặc xóa nhầm dữ liệu.
- Khóa mã hóa backup bị mất hoặc cần rotation.
- Một authenticator bị compromise và phải thay thế.
- Tổ chức cần khôi phục dịch vụ sau disaster recovery.
- Người dùng mất phương thức MFA chính nhưng vẫn cần khôi phục quyền truy cập.

Không có backup phù hợp có thể khiến người dùng mất quyền truy cập lâu dài hoặc khiến tổ chức không thể phục hồi dịch vụ. Nhưng backup bí mật quá rộng lại tạo thêm một mục tiêu có giá trị cao cho attacker. Thiết kế cần cân bằng khả năng phục hồi với nguy cơ tạo bản sao có thể bị đánh cắp.

## 3. Phân loại dữ liệu credential cần bảo vệ

Không phải mọi dữ liệu trong credential registry đều là bí mật:

| Dữ liệu | Có thể backup? | Cách bảo vệ |
| --- | --- | --- |
| Credential ID, principal, tenant, status | Có | Kiểm soát truy cập, integrity, version và retention. |
| Public key của passkey/WebAuthn | Có | Bảo vệ integrity và liên kết đúng credential/account. |
| Private key không exportable | Không xuất trực tiếp | Giữ trong authenticator/secure hardware; chuẩn bị credential dự phòng hoặc re-enrollment. |
| TOTP secret | Có thể, nếu policy cho phép | Mã hóa mạnh, giới hạn người đọc, quản lý wrapping key riêng. |
| Password hash | Có | Mã hóa backup, kiểm soát quyền và bảo vệ chống offline cracking nếu backup bị lộ. |
| Recovery code verifier/hash | Có | Bảo vệ integrity/confidentiality; không thể suy ra mã bản rõ. |
| Recovery code bản rõ | Thông thường không lưu server | Hiển thị một lần để người dùng lưu an toàn; cấp bộ mới khi cần. |
| Client certificate/public certificate | Có | Bảo vệ chain, trạng thái và mapping tới private key. |
| Certificate private key | Chỉ khi được phép | HSM/KMS hoặc backup mã hóa theo PKI policy; nhiều key nên reissue thay vì export. |
| API key/client secret | Có thể, theo secret-management policy | Secret manager, envelope encryption, access audit và rotation. |
| Session cookie/access token | Không nên backup để phục hồi đăng nhập | Revoke/expire và tạo session/token mới qua authentication. |
| Refresh token | Thường không backup như dữ liệu khôi phục | Quản lý token family; revoke hoặc reauthenticate sau sự cố. |

Backup public key và metadata thường giúp phục hồi registry. Backup private key hoặc shared secret có thể tạo thêm bản sao có khả năng xác thực, vì vậy cần tiêu chuẩn bảo vệ cao hơn.

## 4. Phân biệt backup, synchronization, escrow và recovery

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| **Backup** | Tạo bản sao có thể khôi phục sau mất mát hoặc hỏng dữ liệu. | Snapshot credential registry và bản mã hóa của secret được phép backup. |
| **Synchronization** | Đồng bộ credential giữa các thiết bị theo mô hình của nền tảng. | Passkey sync qua hệ sinh thái nhà cung cấp. |
| **Escrow** | Gửi hoặc giữ khóa trong một cơ chế lưu ký có kiểm soát để đáp ứng nhu cầu được định nghĩa. | Private key mã hóa được lưu trong HSM backup domain theo policy. |
| **Recovery** | Quy trình xác minh và khôi phục quyền kiểm soát tài khoản/credential. | Dùng passkey dự phòng để đăng ký authenticator mới. |
| **Reissuance** | Cấp credential mới và thu hồi credential cũ. | Cấp certificate mới sau khi private key cũ bị mất. |

Các khái niệm này không thể thay thế lẫn nhau. Sync không nhất thiết là backup độc lập; backup không chứng minh người yêu cầu restore là chủ tài khoản; escrow không tự động được phép sử dụng để impersonate người dùng. Recovery cần identity verification và policy riêng.

## 5. Ranh giới tin cậy trong kiến trúc backup

Một hệ thống có thể gồm credential service, secret store, encryption/KMS, backup service, kho backup tách biệt và quy trình restore:

~~~mermaid
flowchart LR
    APP["Identity / credential service"]
    DB[("Credential registry")]
    KMS["KMS / HSM<br/>wrapping keys"]
    ENC["Backup worker<br/>encrypt + integrity"]
    VAULT[("Backup vault<br/>immutable/offline copy")]
    OPS["Restore operator<br/>dual control"]
    RESTORE["Restore environment"]
    AUDIT[("Audit / monitoring")]
    APP <--> DB
    APP --> ENC
    DB --> ENC
    KMS <--> ENC
    ENC --> VAULT
    OPS --> RESTORE
    VAULT --> RESTORE
    KMS --> RESTORE
    RESTORE --> AUDIT
    ENC --> AUDIT
~~~

Credential service quyết định dữ liệu nào được backup. Backup worker đọc dữ liệu theo quyền tối thiểu, mã hóa và ghi integrity metadata. KMS/HSM quản lý wrapping key. Backup vault lưu bản sao tách biệt khỏi hệ thống vận hành. Restore operator chỉ được khôi phục theo runbook có phê duyệt; môi trường restore phải kiểm tra trạng thái thu hồi và version trước khi phục vụ xác thực.

Không để cùng một tài khoản quản trị có quyền đọc secret bản rõ, xuất wrapping key, xóa backup và tự phê duyệt restore. Tách nhiệm vụ giúp giảm rủi ro insider và tài khoản quản trị bị chiếm.

## 6. Quyết định credential nào nên backup

Phân loại theo khả năng xuất, hậu quả nếu bị lộ và cách thay thế:

| Loại credential | Hướng xử lý khi mất |
| --- | --- |
| Passkey đồng bộ | Dựa trên cơ chế sync/recovery của nền tảng và policy; quản lý thiết bị/tài khoản đồng bộ. |
| Passkey device-bound hoặc khóa bảo mật không exportable | Dùng authenticator dự phòng hoặc recovery; đăng ký khóa mới nếu mất. |
| TOTP secret | Có thể backup mã hóa theo policy; nếu nghi lộ, revoke và tạo secret mới. |
| Password | Không backup bản rõ; password hash có thể nằm trong backup database được bảo vệ. |
| Recovery code | Người dùng lưu bản cấp một lần; server lưu verifier và trạng thái tiêu thụ. |
| Client certificate | Backup certificate/public metadata; private key theo PKI policy hoặc reissue. |
| API key/client secret | Secret manager có version/rotation; không đưa vào bản backup không kiểm soát. |
| Session/access token | Không dùng backup để khôi phục session; xác thực lại và phát hành mới. |

Nếu một credential không thể backup an toàn, hãy thiết kế khả năng re-enrollment trước khi người dùng mất nó: đăng ký nhiều authenticator độc lập, recovery code, quy trình helpdesk hoặc certificate reissuance.

## 7. Backup passkey và WebAuthn credential

WebAuthn credential thường gồm credential ID, public key và metadata ở phía relying party; private key được giữ bởi authenticator. Server thường chỉ cần backup public key, credential status, user handle, RP ID, sign counter/metadata liên quan và mapping tới principal.

### Passkey đồng bộ

Một số nền tảng hỗ trợ passkey sync giữa các thiết bị thông qua tài khoản/hệ sinh thái của nhà cung cấp. Trong mô hình này, credential có thể được phục hồi trên thiết bị khác theo cơ chế bảo vệ và xác thực của nền tảng. Ứng dụng relying party không nên tự xuất private key hoặc giả định nó kiểm soát quy trình sync.

Cần đánh giá:

- Tài khoản nền tảng dùng để sync có MFA/recovery đủ mạnh không?
- Thiết bị mới có cần xác minh bổ sung không?
- Người dùng có thể thu hồi thiết bị hoặc phiên sync bị mất không?
- Credential có thuộc loại syncable hay device-bound?
- Policy assurance của ứng dụng có chấp nhận mô hình sync đó không?

### Passkey device-bound

Với khóa không exportable hoặc gắn với một authenticator cụ thể, server không thể tái tạo private key từ public key backup. Khi thiết bị mất, dùng credential dự phòng hoặc account recovery để đăng ký passkey mới. Không cố backup bằng cách đọc private key từ authenticator.

### Counter và metadata

Một số authenticator cung cấp sign counter hoặc metadata giúp phát hiện clone theo semantics của giao thức. Không được rollback metadata một cách tùy tiện khi restore. Với passkey sync, counter có thể có semantics khác; relying party cần tuân thủ hướng dẫn WebAuthn và không coi một giá trị counter đơn lẻ là bằng chứng tuyệt đối về compromise.

## 8. Backup TOTP và authenticator secret

TOTP secret là bí mật dùng chung giữa authenticator và verifier. Ai có secret có thể tạo mã hợp lệ, nên backup secret tạo thêm bản sao có khả năng xác thực.

Nếu policy cho phép backup:

- Mã hóa secret trước khi ghi vào backup vault.
- Dùng envelope encryption với data encryption key (DEK) riêng cho từng đối tượng hoặc nhóm phù hợp.
- Wrapping DEK bằng key được quản lý trong KMS/HSM.
- Giới hạn ai và dịch vụ nào có thể decrypt.
- Ghi audit cho thao tác export, decrypt và restore.
- Không đưa secret vào log, analytics, ticket hoặc notification.
- Không hiển thị QR provisioning lần nữa chỉ vì restore database.

Nếu thiết bị mất hoặc secret nghi bị sao chép, revoke TOTP binding và enrollment secret mới. Khôi phục secret cũ chỉ phù hợp khi có bằng chứng rằng bản sao backup vẫn được bảo vệ và policy cho phép; cần đánh giá replay state và trạng thái binding.

## 9. Backup password và password hash

Không bao giờ backup hoặc gửi mật khẩu bản rõ như một phần của quy trình khôi phục tài khoản.

Password database thường lưu password hash cùng salt và tham số thuật toán. Backup database vẫn nhạy cảm vì attacker có thể thực hiện offline guessing nếu lấy được bản sao:

- Mã hóa backup bằng key riêng và quản lý key tách biệt.
- Giữ cấu hình Argon2id, scrypt hoặc bcrypt và metadata cần thiết.
- Không dùng MD5/SHA-1/SHA-256 trực tiếp làm password hash.
- Bảo vệ pepper nếu hệ thống dùng pepper; không lưu pepper cùng backup database.
- Kiểm soát quyền đọc backup và giới hạn thời gian retention.
- Theo dõi truy cập bất thường và có quy trình rotate/upgrade hash parameters.

Sau restore, nếu backup cũ có thể chứa password hash trước một sự cố compromise, cần cân nhắc buộc reset mật khẩu, tăng security epoch và revoke session/token được phát hành sau mốc không đáng tin.

## 10. Recovery code và backup phía người dùng

Recovery code thường được tạo một lần khi người dùng thiết lập MFA hoặc quản lý tài khoản. Mỗi mã có entropy đủ cao, dùng một lần và server lưu verifier/hash cùng trạng thái consumed.

Hệ thống nên:

- Hiển thị mã bản rõ một lần sau khi tạo.
- Hướng dẫn người dùng lưu offline hoặc trong password manager được bảo vệ.
- Không gửi recovery code qua email hoặc SMS.
- Không log mã hoặc yêu cầu người dùng đọc mã cho helpdesk.
- Khi tạo bộ mới, consume/revoke bộ cũ theo policy.
- Khi dùng mã, cập nhật trạng thái nguyên tử để chống hai request đồng thời.

Backup recovery code là trách nhiệm bảo vệ bản sao phía người dùng. Server không thể khôi phục lại mã bản rõ từ verifier/hash; nếu người dùng mất toàn bộ mã, cần recovery flow mới và cấp bộ mã mới sau khi xác minh.

## 11. Backup certificate và private key

Certificate có thể được sao lưu dưới dạng public certificate, chain, metadata và trạng thái PKI. Private key là tài sản riêng cần policy nghiêm ngặt:

- Nếu private key được tạo non-exportable trong HSM/TPM/secure hardware, thường không thể và không nên xuất ra file backup thông thường.
- HSM có thể hỗ trợ backup/replication key theo cơ chế wrapping và quorum của nhà cung cấp.
- Với certificate không cần giữ private key cũ, có thể reissue certificate và revoke certificate cũ.
- Nếu key compromise, không restore key đó để tiếp tục sử dụng.
- Backup phải giữ mapping certificate, subject/SAN, issuer, serial, validity và revocation state.
- CA/PKI signing key cần quy trình backup, custody, quorum và disaster recovery riêng.

Không nhầm backup certificate với backup private key. Public certificate không đủ để ký hoặc giải mã; private key backup có thể mở rộng khả năng giả mạo danh tính hoặc giải mã dữ liệu.

## 12. Backup API key, client secret và workload credential

API key và client secret thường là bearer secret. Nên quản lý bằng secret manager có version, access policy và rotation:

- Tách key theo workload, tenant, môi trường và scope.
- Lưu secret đã mã hóa; chỉ workload được cấp quyền mới có thể lấy.
- Ghi metadata như owner, purpose, created/expiry, version và status.
- Có thể khôi phục version cũ trong tình huống vận hành nếu key chưa bị compromise và policy cho phép.
- Không restore secret đã bị revoke hoặc nghi lộ.
- Sau restore phải kiểm tra consumer nào còn dùng version cũ.
- Có kế hoạch rotate và revoke nhanh khi phát hiện lộ secret.

Không đưa API key vào file cấu hình, source code, image container hoặc bản backup không mã hóa. Nếu secret đã lộ, backup cũ không phải cách phục hồi; phải tạo key mới và cập nhật consumer.

## 13. Mã hóa backup: envelope encryption

Backup chứa secret cần mã hóa trước khi rời vùng dữ liệu tin cậy. Một mô hình phổ biến là **envelope encryption**:

1. Sinh DEK ngẫu nhiên cho đối tượng hoặc tập backup.
2. Dùng AEAD như AES-GCM hoặc ChaCha20-Poly1305 để mã hóa payload.
3. Dùng KMS/HSM wrapping key (KEK) để wrap DEK.
4. Lưu ciphertext, wrapped DEK, thuật toán, nonce, tag và metadata version.
5. Khi restore, dịch vụ có quyền yêu cầu KMS unwrap DEK rồi xác minh AEAD trước khi sử dụng dữ liệu.

~~~mermaid
flowchart TD
    P["Credential payload"]
    D["Random DEK"]
    E["AEAD encrypt"]
    C["Ciphertext + nonce + tag"]
    K["KMS/HSM KEK"]
    W["Wrapped DEK"]
    V["Backup vault"]
    P --> E
    D --> E
    E --> C
    K -->|"Wrap"| W
    C --> V
    W --> V
~~~

Metadata quan trọng như backup ID, object type, schema version, tenant reference và purpose nên được xác thực bằng associated data hoặc integrity mechanism phù hợp. Nếu metadata không được bảo vệ, attacker có thể tráo ciphertext giữa tenant hoặc loại credential.

Không tự thiết kế thuật toán mã hóa hoặc dùng cùng một nonce dưới cùng key AEAD khi thuật toán yêu cầu nonce duy nhất. Dùng thư viện và dịch vụ quản lý khóa được duy trì.

## 14. Quản lý encryption key và separation of duties

Backup an toàn phụ thuộc vào bảo vệ khóa mã hóa:

- Wrapping key nằm trong KMS/HSM hoặc hệ thống quản lý khóa tách biệt.
- Quyền encrypt, decrypt, rotate và destroy được phân tách.
- Backup operator không mặc nhiên có quyền decrypt nội dung.
- Restore cần approval độc lập hoặc dual control cho secret rủi ro cao.
- Key rotation có version và kế hoạch decrypt bản backup cũ.
- Có bản sao/escrow key theo quy trình disaster recovery đã kiểm thử.
- Audit mọi lần sử dụng key và cảnh báo truy cập bất thường.
- Không lưu KEK bản rõ cạnh ciphertext hoặc trong cùng backup vault.

Nếu mất KEK, ciphertext có thể không thể phục hồi. Nếu KEK bị lộ, attacker có thể giải mã nhiều backup. Vì vậy key recovery và key custody cần được thiết kế cùng backup strategy, không phải bổ sung sau.

## 15. Integrity, authenticity và chống rollback

Mã hóa confidentiality không tự bảo đảm backup là bản mới nhất hoặc đến từ nguồn đáng tin. Backup cần integrity/authenticity và cơ chế phát hiện rollback:

- AEAD tag hoặc chữ ký manifest bảo vệ nội dung và metadata.
- Manifest ghi backup ID, source, thời điểm, schema version, object count và hash/checksum.
- Version hoặc monotonic epoch giúp phát hiện snapshot cũ bị phục hồi trái phép.
- Chữ ký manifest dùng khóa ký riêng được bảo vệ.
- Restore kiểm tra manifest và provenance trước khi nhập dữ liệu.
- Audit restore ghi rõ snapshot, version, approver và kết quả.

### Rollback attack

Attacker có thể thay bản registry hiện tại bằng snapshot cũ, trong đó credential đã revoke lại mang trạng thái active hoặc recovery code đã dùng trở lại unused. Nếu chỉ kiểm tra checksum của snapshot, bản cũ vẫn có thể hợp lệ về integrity.

Biện pháp:

- Duy trì revocation log hoặc security epoch ngoài backup snapshot.
- Không để restore làm lùi trạng thái revoke/consumed.
- Hợp nhất tombstone và event phát sinh sau thời điểm snapshot.
- Nếu không thể chứng minh trạng thái mới nhất, vô hiệu hóa credential/session không chắc chắn và yêu cầu reauthentication/re-enrollment.
- Kiểm tra snapshot sequence/version với nguồn độc lập hoặc immutable log.

## 16. Backup consistency và transaction boundary

Credential registry có thể thay đổi liên tục trong khi backup đang chạy. Nếu snapshot lấy các bảng ở những thời điểm khác nhau, có thể tạo trạng thái không nhất quán:

- Credential mới được backup nhưng account mapping chưa có.
- Session đã revoke nhưng refresh token family vẫn active trong snapshot.
- Recovery code đã consume nhưng verifier snapshot vẫn ghi unused.
- Certificate đã revoke nhưng revocation state không nằm cùng backup set.

Cần snapshot nhất quán hoặc quy trình capture có watermark:

1. Xác định transaction boundary và version/watermark.
2. Snapshot các bảng liên quan theo cùng điểm nhất quán.
3. Ghi event log/outbox sau watermark để replay khi restore.
4. Bảo đảm thứ tự sự kiện và xử lý idempotent.
5. Kiểm tra ràng buộc principal, tenant, credential, session và token family sau restore.

Không khôi phục riêng bảng credential mà bỏ qua trạng thái revocation hoặc account lifecycle liên quan.

## 17. Immutable/offline backup và chống ransomware

Nếu attacker chiếm quyền quản trị production, họ có thể cố xóa cả dữ liệu chính và backup. Một số biện pháp:

- Immutable/WORM retention hoặc object lock.
- Bản sao offline hoặc tài khoản/vùng quản trị độc lập.
- Tách backup identity khỏi production identity.
- MFA chống phishing và dual control cho thao tác xóa/retention change.
- Alert khi số lượng object bị xóa hoặc retention policy bị thay đổi bất thường.
- Kiểm tra restore từ bản sao độc lập, không chỉ backup trong cùng account.
- Mã hóa backup trước khi truyền và khi lưu.

Immutable backup vẫn có thể chứa credential đã bị compromise hoặc trạng thái đã lỗi thời. Không tự động đưa snapshot trở lại production mà chưa hợp nhất revocation và incident timeline.

## 18. Retention, deletion và privacy

Backup có thể giữ dữ liệu lâu hơn bản ghi production. Cần quy định:

- Mục đích và thời hạn retention cho từng loại credential data.
- Xóa/ẩn danh dữ liệu khi hết hạn theo chính sách và nghĩa vụ áp dụng.
- Cách xử lý yêu cầu xóa khi dữ liệu vẫn nằm trong immutable backup.
- Quyền truy cập và vị trí lưu trữ theo tenant/data residency.
- Không backup metadata thiết bị hoặc thông tin cá nhân không cần thiết.
- Không dùng backup làm nguồn analytics hoặc theo dõi người dùng.
- Khi restore, áp dụng lại deletion/tombstone đã phát sinh sau snapshot.

Một bản backup immutable có thể cần chờ hết retention mới bị xóa vật lý, nhưng dữ liệu đã có yêu cầu xóa phải được đánh dấu để không phục hồi lại vào hệ thống hoạt động. Cần tài liệu hóa thời gian và cách áp dụng tombstone.

## 19. Quy trình restore an toàn

Restore credential data cần nhiều bước hơn việc giải nén database:

1. Mở incident/change record và xác định lý do, phạm vi, RPO/RTO.
2. Chọn snapshot có provenance, integrity và version phù hợp.
3. Xác minh approver, operator và quyền truy cập KMS/HSM.
4. Restore vào môi trường cô lập trước khi đưa traffic vào.
5. Kiểm tra schema, checksum, AEAD tag, manifest và quan hệ dữ liệu.
6. Hợp nhất revocation log, security epoch, tombstone và sự kiện sau snapshot.
7. Revoke session/token/credential không thể xác minh trạng thái.
8. Reconcile credential registry với IdP, PKI, secret manager và nguồn authoritative.
9. Chạy kiểm thử xác thực, thu hồi và recovery trên môi trường restore.
10. Phê duyệt cutover; theo dõi lỗi và có rollback plan an toàn.

Không cho phép người vận hành dùng snapshot cũ để làm sống lại account, passkey, API key hoặc refresh token đã bị revoke.

## 20. RPO, RTO và lựa chọn backup

Hai chỉ số vận hành quan trọng:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, thường biểu thị khoảng thời gian dữ liệu.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.

RPO thấp cần snapshot/log thường xuyên hoặc replication phù hợp. RTO thấp cần runbook, automation, key availability và restore test. Nhưng replication không thay thế backup: lỗi hoặc xóa nhầm có thể được nhân bản sang replica.

| Loại dữ liệu | Yêu cầu cần cân nhắc |
| --- | --- |
| Credential registry/status | RPO thấp; giữ event revoke và version bền vững. |
| Secret/TOTP binding | Backup mã hóa, access hạn chế, key recovery được kiểm thử. |
| Public key/certificate metadata | Snapshot nhất quán và mapping đúng principal/issuer. |
| Password hash | Confidentiality cao; kiểm soát offline cracking và retention. |
| Session/refresh token state | Cân nhắc không restore session cũ; có thể buộc reauthentication sau DR. |
| Recovery code verifier | Giữ consumed state; chống rollback để không tái dùng mã. |

Không cần giữ mọi session lâu dài trong backup. Sau disaster recovery, việc yêu cầu đăng nhập lại có thể an toàn và đơn giản hơn khôi phục các phiên không chắc chắn.

## 21. Kiểm thử backup và restore

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Backup credential registry | Snapshot có manifest, version, integrity và mapping đầy đủ. |
| Backup chứa TOTP secret được phép | Secret được mã hóa bằng DEK; DEK được wrap bằng KMS/HSM. |
| Operator không có quyền decrypt | Không thể đọc secret bản rõ. |
| Restore với manifest sai hoặc AEAD tag lỗi | Từ chối; không nhập dữ liệu. |
| Restore snapshot cũ có credential đã revoke | Revocation log/epoch giữ trạng thái revoke; credential không sống lại. |
| Restore snapshot có recovery code đã dùng | Consumed state không bị rollback. |
| KMS key rotation | Bản backup cũ vẫn decrypt theo quy trình được phê duyệt; key version được kiểm soát. |
| KMS/HSM unavailable | Không fail open hoặc bỏ qua xác minh integrity. |
| Một bảng restore thiếu quan hệ | Validation phát hiện orphan/mismatch trước cutover. |
| Ransomware xóa production | Có bản immutable/offline độc lập để khôi phục. |
| Restore session/token cũ | Chỉ phục hồi nếu policy cho phép và trạng thái revoke được xác minh; nếu không thì buộc reauthentication. |
| Secret bị xác nhận compromise | Không restore để tái sử dụng; rotate/reissue credential. |
| Concurrent backup/update | Snapshot nhất quán hoặc có watermark/event replay. |
| Deletion phát sinh sau snapshot | Tombstone được áp dụng để dữ liệu không bị phục hồi trái phép. |
| Restore diễn tập | Đạt RPO/RTO mục tiêu và có audit/approval. |

### Kiểm thử định kỳ

- Thực hiện restore drill theo lịch và sau thay đổi lớn.
- Kiểm tra quyền KMS/HSM và quy trình key recovery.
- Kiểm tra bản immutable/offline từ tài khoản quản trị độc lập.
- Đo thời gian restore thực tế, không chỉ thời gian tạo backup.
- Xác minh credential revoked, session invalid và recovery code consumed sau restore.
- Diễn tập mất key mã hóa, mất region và ransomware.

## 22. Mã giả: backup và restore credential data

Mã giả dưới đây mô tả nguyên tắc, không thay thế hệ thống backup, KMS/HSM hoặc thư viện mã hóa được kiểm thử:

~~~text
createCredentialBackup(snapshot):
    require backupJobAuthorized()
    require snapshotHasConsistentWatermark()

    payload = collectAllowlistedCredentialData(snapshot)
    manifest = buildManifest(
        backupId = randomId(),
        source = trustedSourceId,
        watermark = snapshot.watermark,
        schemaVersion = currentSchemaVersion,
        objectCounts = countObjects(payload)
    )

    dek = generateRandomDataEncryptionKey()
    aad = canonicalize(manifest)
    ciphertext, nonce, tag = AEAD_Encrypt(dek, payload, aad)
    wrappedDek = KMS_Wrap(dek, approvedBackupKeyVersion)

    signedManifest = signManifest(manifest, backupSigningKey)
    writeImmutableBackup(ciphertext, nonce, tag, wrappedDek, signedManifest)
    appendAudit("backup_created", manifest.backupId)
    destroyInMemory(dek)

restoreCredentialBackup(backupId, approval):
    require restoreApprovalValid(approval)
    backup = loadBackupFromVault(backupId)
    require verifyManifestSignature(backup.manifest)
    require verifyBackupProvenanceAndVersion(backup.manifest)

    dek = KMS_Unwrap(backup.wrappedDek, approvedRestoreRole)
    payload = AEAD_Decrypt(
        dek,
        backup.ciphertext,
        backup.nonce,
        backup.tag,
        canonicalize(backup.manifest)
    )
    destroyInMemory(dek)

    validateSchemaAndRelationships(payload)
    restoreIntoIsolatedEnvironment(payload)
    mergePostSnapshotRevocationAndDeletionEvents()
    enforceCurrentSecurityEpochAndCredentialStatus()
    revokeUnverifiableSessionsAndTokens()
    runAuthenticationAndRecoveryTests()
    require cutoverApproval()
    cutoverAndMonitor()
    appendAudit("backup_restored", backupId)
~~~

Trong triển khai thật:

- Payload phải được allowlist; không tự động backup mọi secret trong database.
- KMS unwrap chỉ thực hiện dưới role và approval phù hợp.
- Manifest và associated data phải canonical, có version và được xác thực.
- DEK phải được quản lý trong memory an toàn nhất có thể và không log.
- Restore phải chạy trong môi trường cô lập trước cutover.
- Revocation/tombstone/security epoch mới hơn snapshot phải thắng dữ liệu cũ.
- Nếu không thể chứng minh trạng thái hiện tại, vô hiệu hóa credential/session không chắc chắn và yêu cầu reauthentication.

## 23. Tình huống thực tế: khôi phục sau khi mất kho credential

Một tổ chức gặp sự cố ở vùng lưu trữ chính. Database credential registry và secret store không thể truy cập. Backup vault vẫn có snapshot gần nhất, nhưng sau snapshot đã có một số credential bị revoke và một nhân viên báo mất thiết bị.

### Rủi ro nếu restore trực tiếp

- Credential đã revoke có thể trở lại active.
- Recovery code đã dùng có thể trở lại trạng thái unused.
- Session/token cũ có thể được chấp nhận lại.
- TOTP secret hoặc API key bị compromise có thể được phục hồi.
- Account đã deprovision có thể xuất hiện như đang active.

### Quy trình xử lý

1. Mở incident và khóa quyền ghi vào hệ thống restore.
2. Chọn snapshot có manifest và integrity hợp lệ.
3. Khôi phục vào môi trường cô lập bằng KMS/HSM role được phê duyệt.
4. Đối chiếu immutable audit/revocation log và event sau snapshot.
5. Áp dụng tombstone, security epoch và trạng thái account mới nhất.
6. Thu hồi hoặc rotate credential nghi bị compromise; không phục hồi private key đã lộ.
7. Không restore session/refresh token nếu không xác minh được trạng thái; yêu cầu đăng nhập lại.
8. Reconcile với IdP, HR/SCIM, PKI và secret manager.
9. Chạy test login, MFA, revoke, recovery và authorization.
10. Phê duyệt cutover, theo dõi anomaly và thông báo người dùng theo incident plan.

Backup chỉ giúp khôi phục dữ liệu; nó không thay thế việc xác minh timeline và trạng thái bảo mật phát sinh sau snapshot.

## 24. Checklist thiết kế backup credential

- [ ] Phân loại dữ liệu credential và xác định loại nào được backup, loại nào phải reissue.
- [ ] Không backup mật khẩu bản rõ hoặc session cookie/access token để tái sử dụng.
- [ ] Phân biệt backup, sync, escrow, recovery và reissuance.
- [ ] Xác định nguồn authoritative và snapshot consistency/watermark.
- [ ] Mã hóa backup bằng AEAD và envelope encryption.
- [ ] Quản lý KEK trong KMS/HSM; DEK riêng và wrapping có version.
- [ ] Bảo vệ manifest, metadata, tenant mapping và provenance.
- [ ] Tách backup operator, decrypt role, restore approver và key custodian.
- [ ] Có immutable/offline copy tách khỏi production account.
- [ ] Có revocation log, security epoch và tombstone chống rollback.
- [ ] Không phục hồi credential đã compromise; rotate/reissue khi cần.
- [ ] Giữ consumed state của recovery code và token.
- [ ] Kiểm soát retention, deletion, data residency và privacy.
- [ ] Restore vào môi trường cô lập, kiểm tra integrity/schema/relationships trước cutover.
- [ ] Reconcile account, credential, session, token, PKI và federation state sau restore.
- [ ] Xác định RPO/RTO và đo qua restore drill thực tế.
- [ ] Kiểm thử mất KMS key, ransomware, replica lag, snapshot cũ và event replay.
- [ ] Ghi audit backup/restore nhưng không ghi secret hoặc key material.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao backup public key không giúp khôi phục private key của passkey device-bound?

**Gợi ý:** Public key chỉ dùng để xác minh chữ ký; private key có thể không exportable và cần authenticator dự phòng hoặc re-enrollment.

**Câu 2.** Vì sao TOTP secret cần được mã hóa riêng trong backup?

**Gợi ý:** Secret có thể tạo mã xác thực hợp lệ; backup tạo thêm bản sao có khả năng xác thực nếu bị giải mã.

**Câu 3.** Vì sao không nên backup password bản rõ?

**Gợi ý:** Nó tạo kho bí mật có thể bị sử dụng trực tiếp. Hệ thống lưu password hash chuyên dụng và cần bảo vệ cả bản backup khỏi offline guessing.

**Câu 4.** Envelope encryption giúp gì cho backup credential?

**Gợi ý:** DEK mã hóa payload, KEK trong KMS/HSM wrap DEK; quyền truy cập và rotation được quản lý tách biệt.

**Câu 5.** Vì sao snapshot cũ có thể làm sống lại credential đã revoke?

**Gợi ý:** Snapshot có thể chứa trạng thái active trước khi revoke; cần merge revocation log, epoch và tombstone mới hơn.

**Câu 6.** Có nên restore refresh token sau disaster recovery không?

**Gợi ý:** Chỉ khi policy và trạng thái token family có thể được xác minh. Thường an toàn hơn khi revoke và yêu cầu reauthentication.

**Câu 7.** Immutable backup có tự bảo đảm restore an toàn không?

**Gợi ý:** Không. Nó bảo vệ bản sao khỏi sửa/xóa, nhưng có thể chứa dữ liệu cũ hoặc credential đã compromise; cần integrity, provenance và reconciliation.

## 26. Ghi nhớ

**Backup credential phải bảo vệ khả năng khôi phục mà không tạo thêm một kho bí mật dễ bị chiếm.** Hãy phân loại public metadata, password hash, TOTP secret, passkey, certificate, API key, recovery code và session theo cách lưu trữ phù hợp; không xuất private key không exportable hoặc phục hồi credential đã compromise. Backup secret cần AEAD/envelope encryption, KMS/HSM, separation of duties, immutable/offline copy và audit. Restore phải xác minh provenance/integrity, giữ trạng thái revoke/consumed/deprovision mới hơn snapshot, reconcile session/token và chạy trong môi trường cô lập trước cutover. Backup chỉ hoàn tất khi quy trình restore được diễn tập, đạt RPO/RTO và chứng minh không làm sống lại credential hoặc phiên đã bị thu hồi.
