# Viết key management policy

Trong bài thực hành này, bạn sẽ xây dựng một **Key Management Policy** cho một nền tảng SaaS đa tenant. Mục tiêu là chuyển các nguyên tắc quản lý khóa thành quy tắc có thể áp dụng, có người chịu trách nhiệm và có cách kiểm chứng. Bản policy cần bao quát vòng đời khóa từ tạo, cấp phát, lưu trữ, sử dụng, rotation, backup, recovery, compromise, revocation đến destruction.

Một chính sách tốt phải giúp các nhóm phát triển Java, vận hành nền tảng, security, kiểm toán và quản lý dữ liệu đưa ra quyết định nhất quán. Tài liệu không chỉ liệt kê thuật toán hoặc yêu cầu “bảo vệ khóa an toàn”; nó cần xác định phạm vi, quyền hạn, điều kiện được phép, quy trình xử lý ngoại lệ và bằng chứng chứng minh kiểm soát đang hoạt động.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

- Phân loại khóa và xác định phạm vi áp dụng của policy.
- Xác định vai trò, owner, custodian, approver và auditor.
- Viết yêu cầu về thuật toán, key generation, key storage và cryptographic module.
- Quy định quyền truy cập theo principal, action, key ID/version và context.
- Xác định cryptoperiod, rotation, retire và điều kiện destruction.
- Thiết kế backup, recovery và xử lý key compromise.
- Đưa audit, monitoring, exception và third-party responsibility vào policy.
- Ánh xạ điều khoản policy sang control, test case, pass criteria và evidence.

## 2. Bối cảnh doanh nghiệp

Bạn là security architect của **Mây Việt**, một công ty giả định cung cấp nền tảng SaaS quản lý hồ sơ khách hàng, đơn hàng và thanh toán cho nhiều doanh nghiệp. Nền tảng được triển khai bằng Java services trên cloud. Dữ liệu của từng tenant phải được cách ly; một workload thuộc tenant A không được phép sử dụng khóa của tenant B.

Kiến trúc hiện tại có các đặc điểm:

- API service, background worker và batch job chạy ở môi trường development, staging và production.
- Dữ liệu nhạy cảm được mã hóa bằng envelope encryption. DEK mã hóa payload; KEK trong cloud KMS/HSM bảo vệ DEK.
- Ứng dụng lưu ciphertext, wrapped DEK và metadata gồm key ID/version, thuật toán, nonce và format version.
- Một signing service dùng khóa bất đối xứng để ký artifact và một số thông điệp nội bộ. Khóa ký được quản lý riêng với khóa mã hóa dữ liệu.
- TLS certificate/private key được dùng cho kết nối dịch vụ.
- Một số ứng dụng Java cũ còn đọc cấu hình từ file và dùng PKCS12 KeyStore; các dịch vụ mới gọi KMS qua workload identity.
- Backup dữ liệu và metadata được sao chép sang region dự phòng. Audit log được chuyển tới tài khoản lưu trữ riêng.
- Nhóm vận hành có thể tạo key version và cập nhật policy; nhóm ứng dụng yêu cầu quyền sử dụng khóa qua quy trình phê duyệt.

Đánh giá nội bộ phát hiện một số vấn đề:

1. Chưa có inventory đầy đủ cho tất cả key ID/version và owner.
2. Một số ứng dụng dùng chung credential để gọi nhiều key.
3. Quyền decrypt và quyền export chưa được tách rõ.
4. Cryptoperiod và tiêu chí rotation chưa được chuẩn hóa.
5. Quy trình backup/recovery chưa được diễn tập thường xuyên.
6. Chưa có tiêu chí rõ ràng để xử lý khóa bị compromise hoặc scheduled for deletion.
7. Một số nhóm chưa biết phải lưu bằng chứng nào để chứng minh đã tuân thủ policy.

Ban điều hành yêu cầu xây dựng policy thống nhất trước khi mở rộng thêm tenant và workload.

## 3. Phạm vi và giả định của bài tập

Policy bạn viết phải áp dụng cho:

- Khóa production và non-production do Mây Việt sở hữu hoặc quản lý.
- Khóa được tạo trong cloud KMS/HSM, HSM do tổ chức vận hành và Java KeyStore thuộc ứng dụng.
- DEK, KEK, master/root key, signing key, certificate private key và HMAC key.
- Các bản sao trong backup, replica, disaster recovery, migration và môi trường kiểm thử.
- Nhân viên, workload identity, service account, nhà cung cấp và bên thứ ba có quyền quản lý hoặc sử dụng khóa.

Các giả định được cung cấp:

| Chủ đề | Giả định |
|---|---|
| Dữ liệu | Có dữ liệu khách hàng và dữ liệu giao dịch cần bảo vệ trong suốt thời gian lưu giữ |
| Mã hóa dữ liệu | Envelope encryption; DEK dùng AEAD; KEK được quản lý bởi KMS/HSM |
| Phân tách tenant | Mỗi tenant có phạm vi key policy hoặc key hierarchy riêng phù hợp với mức rủi ro |
| Khóa ký | Tách khỏi khóa mã hóa dữ liệu và có quyền sử dụng riêng |
| Môi trường | Development, staging và production phải tách biệt key material và quyền |
| Recovery | Có region dự phòng; khả năng replica/restore phụ thuộc dịch vụ KMS/HSM được chọn |
| Audit | Có thể xuất audit log sang vùng lưu trữ độc lập |
| Java | Dịch vụ mới ưu tiên workload identity và KMS API; ứng dụng cũ có thể dùng PKCS12 trong giai đoạn chuyển đổi |

Bạn có thể bổ sung giả định cần thiết, nhưng phải ghi rõ giả định nào do đề bài cung cấp, giả định nào do bạn lựa chọn và vì sao. Không tự coi một tính năng của KMS/HSM là có sẵn nếu chưa kiểm tra semantics của nhà cung cấp.

## 4. Yêu cầu đối với sản phẩm phải nộp

Hãy viết một tài liệu `key-management-policy.md` có thể được trình cho ban điều hành phê duyệt. Tài liệu nên dài khoảng 5–10 trang tương đương, tùy mức chi tiết, và tối thiểu phải có:

1. Mục đích, phạm vi, định nghĩa và tài liệu tham chiếu.
2. Governance, vai trò, owner và phân tách nhiệm vụ.
3. Phân loại khóa và yêu cầu mật mã.
4. Quy tắc tạo, phân phối, lưu trữ và sử dụng khóa.
5. Access control và quản lý đặc quyền.
6. Cryptoperiod, rotation, retire và destruction.
7. Backup, recovery và disaster recovery.
8. Xử lý compromise, revocation và incident response.
9. Audit, monitoring và evidence.
10. Quản lý nhà cung cấp, exception và review policy.

Policy phải dùng ngôn ngữ bắt buộc rõ ràng. Phân biệt:

- **MUST / SHALL:** yêu cầu bắt buộc.
- **SHOULD:** yêu cầu nên áp dụng; nếu không áp dụng cần nêu rationale.
- **MAY:** lựa chọn được phép trong phạm vi policy.

Không dùng các câu mơ hồ như “khóa nên được bảo vệ phù hợp”, “rotation thường xuyên” hoặc “chỉ người có thẩm quyền được truy cập” mà không xác định tiêu chí, chủ thể và cách kiểm tra.

## 5. Nhiệm vụ 1 – Lập inventory và phân loại khóa

Trước khi viết các điều khoản, hãy tạo bảng inventory ban đầu cho hệ thống Mây Việt. Tối thiểu gồm các loại khóa sau:

| Key class | Purpose | Owner gợi ý | Nơi quản lý | Rủi ro chính |
|---|---|---|---|---|
| Tenant DEK | Mã hóa dữ liệu tenant | Data/application owner | KMS data-key workflow + wrapped DEK | Lộ plaintext DEK hoặc mất DEK |
| Tenant KEK | Wrap/unwrap DEK | Key platform owner | Cloud KMS/HSM | Compromise có thể ảnh hưởng nhiều DEK |
| Signing key | Ký artifact/thông điệp | Signing service owner | HSM/KMS signing boundary | Giả mạo chữ ký |
| TLS private key | Xác thực endpoint | Platform/network owner | Certificate manager/KMS/HSM | Impersonation hoặc mất kết nối tin cậy |
| HMAC key | Xác thực message/integrity | Service owner | KMS/secret manager phù hợp | Giả mạo message |
| Recovery/backup key | Phục hồi key object hoặc backup | Key custodian | HSM backup domain hoặc cơ chế được duyệt | Mất khả năng recovery hoặc lạm dụng break-glass |

Với mỗi loại, bổ sung các trường:

- Key ID hoặc naming convention.
- Owner và custodian.
- Purpose và allowed usage.
- Algorithm/profile và key size/parameters.
- Environment, tenant scope và classification.
- Origin: generated internally, KMS/HSM generated hay imported.
- Exportability và storage boundary.
- State, version, creation date, cryptoperiod và planned rotation.
- Backup/recovery dependency.
- Audit source và destruction condition.

**Câu hỏi cần trả lời:** Khóa nào có thể dùng chung? Khóa nào bắt buộc tách theo tenant hoặc environment? Khi owner rời tổ chức, ai tiếp nhận trách nhiệm? Khóa không xác định được owner sẽ được xử lý ra sao?

## 6. Nhiệm vụ 2 – Xác định governance và trách nhiệm

Hãy thiết kế mô hình trách nhiệm để không một cá nhân tự thực hiện toàn bộ thao tác rủi ro cao.

| Vai trò | Trách nhiệm cần ghi trong policy |
|---|---|
| Executive policy owner | Phê duyệt policy, chấp nhận rủi ro ở cấp tổ chức |
| Security architect | Xác định crypto profile, review thiết kế và exception |
| Business/data owner | Xác định dữ liệu, retention và yêu cầu availability |
| Key owner | Quản lý vòng đời, inventory và dependency của key ID/version |
| Key custodian | Vận hành KMS/HSM, backup và recovery theo phê duyệt |
| Application owner | Tích hợp ứng dụng, dùng đúng key purpose và bảo vệ metadata |
| IAM administrator | Quản lý principal, role, grant và access review |
| Incident responder | Điều phối compromise response, containment và evidence |
| Auditor | Đánh giá độc lập policy, control và audit trail |

Tạo ma trận RACI cho ít nhất các hoạt động: tạo khóa, cấp quyền, export, rotation, backup, recovery, disable, revoke, destruction và exception approval.

Hãy xác định rõ những thao tác nào cần:

- Một người yêu cầu và một người phê duyệt độc lập.
- Dual control hoặc quorum M-of-N.
- Ticket/change record và thời hạn phê duyệt.
- Break-glass với quyền tạm thời và review sau thao tác.

**Câu hỏi cần trả lời:** Ai có thể tạo KEK? Ai có thể cấp quyền decrypt? Người phê duyệt có thể tự gọi export không? Auditor có được quyền sử dụng key material không? Nếu KMS administrator và application owner cùng một nhóm thì cần kiểm soát bù trừ nào?

## 7. Nhiệm vụ 3 – Viết crypto baseline

Tạo một standard/profile được policy tham chiếu. Không nhất thiết phải ghi mọi thông số vào policy chính; điều quan trọng là quy trình phê duyệt và cập nhật profile rõ ràng.

Các nội dung cần quyết định:

1. Thuật toán và tham số nào được chấp thuận theo từng purpose?
2. Key size/curve nào phù hợp với yêu cầu và hướng dẫn hiện hành?
3. CSPRNG hoặc provider nào được phép sinh key material?
4. AEAD mode nào được dùng cho payload và nonce phải được quản lý ra sao?
5. RSA scheme nào dùng cho key transport và scheme nào dùng cho signature, nếu có?
6. Khi nào cần KMS/HSM hoặc cryptographic module có validation phù hợp?
7. Làm sao thay provider/algorithm mà vẫn đọc được dữ liệu cũ?

Ví dụ định hướng để bạn xem xét:

| Purpose | Profile minh họa | Điều cần quy định |
|---|---|---|
| Payload encryption | AES-GCM | Nonce không được tái sử dụng với cùng key; tag phải được xác minh |
| Key wrapping | Cơ chế key wrap được chấp thuận hoặc KMS wrap API | Không export KEK dạng plaintext |
| Signing | RSA-PSS hoặc ECDSA theo profile được duyệt | Tách signing key khỏi encryption key; quản lý verify key/certificate |
| Password-derived key | KDF chuyên dụng theo standard nội bộ | Không dùng password trực tiếp làm key; salt và cost parameter được quản lý |

Đây là ví dụ để phân tích, không phải danh sách thuật toán bắt buộc cho mọi môi trường. Hãy đối chiếu NIST SP 800-57 và SP 800-131A cùng yêu cầu pháp lý/hợp đồng mà tổ chức thực sự chịu ràng buộc.

## 8. Nhiệm vụ 4 – Viết quy tắc vòng đời khóa

Với mỗi giai đoạn, viết ít nhất một điều khoản bắt buộc, một control thực thi và một bằng chứng kiểm tra.

| Giai đoạn | Những điều policy phải quy định | Evidence gợi ý |
|---|---|---|
| Create | Ai được tạo, nguồn ngẫu nhiên, crypto profile, naming và owner | KMS create event, key inventory |
| Distribute | Kênh phân phối, xác thực bên nhận, key wrapping và metadata | Provisioning record, access grant |
| Store | KMS/HSM, non-exportable mặc định, backup boundary | Key attributes, configuration snapshot |
| Use | Principal/action/resource/context, purpose và usage limit | KMS audit, allow/deny test |
| Rotate | Trigger, cryptoperiod profile, canary, cutover và migration | Rotation plan, key versions, checkpoint |
| Retire | Ngừng encrypt/sign mới, giữ decrypt/verify nếu cần | State transition, dependency report |
| Revoke/disable | Trigger, người phê duyệt, propagation và xử lý session | Revoke event, propagation report |
| Backup | Phạm vi backup, wrapping, retention và quyền truy cập | Backup record, integrity result |
| Recover | Quorum, recovery identity, canary và RTO/RPO | Recovery drill, approval, decrypt test |
| Destroy | Dependency check, approval, backup copies và bằng chứng | Destruction record, inventory closure |

Phân biệt `ACTIVE`, `WRITE_DISABLED`, `DECRYPT_ONLY`, `DISABLED`, `COMPROMISED`, `PENDING_DELETION` và `DESTROYED` theo state machine phù hợp với KMS/HSM. Không được dùng một trạng thái chung `INACTIVE` nếu các trạng thái có hành vi bảo mật khác nhau.

## 9. Nhiệm vụ 5 – Viết access control

Hãy định nghĩa policy theo principal, action, resource và context. Áp dụng least privilege và default deny.

Ma trận khởi đầu:

| Principal | Encrypt | Decrypt | Sign | Export plaintext | Rotate |
|---|---:|---:|---:|---:|---:|
| `tenant-a-writer` | Allow tenant A | Deny | Deny | Deny | Deny |
| `tenant-a-reader` | Deny | Allow tenant A | Deny | Deny | Deny |
| `signing-service` | Deny | Deny | Allow signing key được chỉ định | Deny | Deny |
| `key-custodian` | Theo nhiệm vụ | Theo phê duyệt | Deny mặc định | Deny mặc định | Allow có kiểm soát |
| `unknown-workload` | Deny | Deny | Deny | Deny | Deny |

Mở rộng ma trận với `WrapKey`, `UnwrapKey`, `ImportKey`, `Disable`, `ScheduleDeletion` và `Destroy`. Ghi rõ các condition như tenant, environment, region, workload identity, purpose, approval và thời hạn.

Hãy viết ít nhất năm test âm:

1. Tenant A thử decrypt key của tenant B.
2. Workload chỉ có Encrypt thử Decrypt.
3. Workload được Decrypt thử export plaintext key.
4. Principal production sử dụng credential staging.
5. Principal đã bị revoke tiếp tục gọi KMS qua cache/session cũ.

Expected result phải xác nhận request bị từ chối, không có plaintext/key material và audit event được tạo.

## 10. Nhiệm vụ 6 – Quy định cryptoperiod và rotation

Không chọn một con số rotation duy nhất cho tất cả khóa. Hãy lập bảng profile theo loại khóa và xác định yếu tố quyết định thời hạn:

- Mức độ nhạy cảm và thời gian dữ liệu cần được bảo vệ.
- Thuật toán, key size, lượng dữ liệu hoặc số lần sử dụng.
- Khả năng compromise và phạm vi ảnh hưởng nếu khóa bị lộ.
- Khả năng rotate mà không gián đoạn dịch vụ.
- Yêu cầu pháp lý, hợp đồng hoặc standard áp dụng.

Template để hoàn thiện:

| Key class | Cryptoperiod/profile | Rotation trigger | Read old version | Owner |
|---|---|---|---|---|
| DEK | `[điền profile]` | `[định kỳ / usage / incident]` | `[có/không và điều kiện]` | `[role]` |
| KEK | `[điền profile]` | `[định kỳ / provider / compromise]` | `[có/không và điều kiện]` | `[role]` |
| Signing key | `[điền profile]` | `[định kỳ / certificate / compromise]` | `[verify lịch sử?]` | `[role]` |
| TLS key | `[điền profile]` | `[certificate lifecycle]` | `[theo trust policy]` | `[role]` |

Policy phải nêu dual-read/single-write hoặc phương pháp tương đương khi chuyển version; lưu key ID/version trong metadata; kiểm tra dữ liệu đã migrate; chỉ retire/destroy khi dependency đã được xử lý. Nêu điều kiện forward recovery nếu khóa cũ bị compromise.

## 11. Nhiệm vụ 7 – Backup và recovery

Viết điều khoản để tổ chức có thể khôi phục dữ liệu khi KMS/HSM, region hoặc key service gặp sự cố.

Hãy trả lời:

- Khóa nào được backup/replicate và khóa nào không được export?
- Backup chứa key material, key object hay chỉ chứa wrapped DEK/metadata?
- Ai có quyền restore? Có cần dual control/quorum không?
- Recovery identity có phụ thuộc vào identity provider chính không?
- Làm sao xác minh backup integrity và đúng key ID/version?
- RTO/RPO nào được business owner phê duyệt cho key service, metadata và ciphertext?
- Cách xử lý khi key đã scheduled for deletion hoặc destroyed?
- Điều kiện nào buộc forward recovery thay vì bật lại khóa cũ?

Thiết kế một runbook ngắn gồm: declare incident, freeze key changes, xác minh key/backup, phê duyệt recovery, restore/replica, canary unwrap/decrypt, cập nhật workload, đối soát dữ liệu, audit và post-incident review.

**Lưu ý:** Backup ciphertext mà thiếu đúng KEK không tạo ra khả năng giải mã. Tạo key mới cùng alias cũng không tái tạo key material cũ. Với managed KMS, hãy dựa vào tính năng replica/backup thực tế được nhà cung cấp hỗ trợ; không tìm cách export plaintext key để vượt giới hạn non-exportable.

## 12. Nhiệm vụ 8 – Compromise, revocation và destruction

Viết quy trình ứng phó cho ba tình huống:

**A. Credential hoặc quyền truy cập bị lộ**

- Thu hồi token/session và credential liên quan.
- Chặn principal hoặc workload identity.
- Kiểm tra propagation tới mọi node/region/cache.
- Xác minh audit và các thao tác khóa đã thực hiện.

**B. KEK hoặc signing key bị compromise**

- Xác định key ID/version và phạm vi dữ liệu/chữ ký bị ảnh hưởng.
- Disable/revoke theo incident authority.
- Tạo khóa sạch, cập nhật policy và workload.
- Rewrap hoặc re-encrypt dữ liệu tùy việc DEK/plaintext có thể đã bị lộ hay không.
- Với signing key, xử lý certificate/relying party và xác minh chữ ký lịch sử theo trust policy.

**C. Khóa hết nhu cầu sử dụng**

- Kiểm tra ciphertext, archive, backup, replica và dependency.
- Thu hồi quyền, disable/retire theo state machine.
- Phê duyệt destruction và xử lý tất cả bản sao theo khả năng nền tảng.
- Lưu bằng chứng destruction; không coi xóa alias là bằng chứng key material đã bị hủy.

## 13. Nhiệm vụ 9 – Audit, monitoring và evidence

Xác định event bắt buộc phải ghi:

- Create/import/export.
- Encrypt/decrypt/sign/verify/wrap/unwrap.
- Policy/grant/role change.
- Rotate/disable/revoke/recovery/destroy.
- Access denied, approval và break-glass.

Định nghĩa schema audit tối thiểu: timestamp, actor/principal, key ID/version, action, decision, outcome, request/correlation ID và reason code. Không ghi key material, private key, password, token hoặc plaintext.

Hãy lập bảng evidence:

| Policy area | Evidence | Owner | Chu kỳ/trigger review |
|---|---|---|---|
| Inventory | Key inventory và orphan-key report | `[role]` | `[điền]` |
| Access | IAM/key policy và access review | `[role]` | `[điền]` |
| Rotation | Rotation report, migration checkpoint | `[role]` | `[điền]` |
| Recovery | Restore drill và canary decrypt | `[role]` | `[điền]` |
| Audit | Event sample, integrity verification, retention | `[role]` | `[điền]` |
| Destruction | Approval và destruction record | `[role]` | `[điền]` |

## 14. Nhiệm vụ 10 – Exception và quản lý nhà cung cấp

Viết quy trình exception gồm:

- Điều khoản nào không thể đáp ứng và vì sao.
- Hệ thống, key ID/version, dữ liệu và môi trường bị ảnh hưởng.
- Rủi ro, compensating control và monitoring bổ sung.
- Người chịu trách nhiệm, approver và ngày hết hạn.
- Kế hoạch khắc phục và điều kiện thu hồi exception sớm.

Với cloud KMS/HSM hoặc dịch vụ bên thứ ba, xác định shared responsibility: nhà cung cấp bảo vệ module/hạ tầng nào; Mây Việt chịu trách nhiệm IAM, key policy, workload, dữ liệu, audit export, region, backup và incident response nào. Yêu cầu bằng chứng assurance phải đúng sản phẩm, phiên bản, module và cấu hình đang dùng.

## 15. Template policy để hoàn thiện

Sử dụng cấu trúc dưới đây làm bản nháp. Thay mọi phần `[điền ...]` bằng quyết định của nhóm và ghi rationale cho các lựa chọn có ảnh hưởng lớn.

```markdown
# Mây Việt – Key Management Policy

## 1. Purpose
[Nêu mục tiêu bảo vệ tính bí mật, toàn vẹn, xác thực và khả năng sẵn sàng của khóa.]

## 2. Scope
[Nêu hệ thống, môi trường, loại khóa, dữ liệu, nhân sự và nhà cung cấp thuộc phạm vi.]

## 3. References and definitions
[Liệt kê NIST/standard áp dụng; định nghĩa DEK, KEK, cryptoperiod, compromise, revoke, retire, destroy.]

## 4. Governance and responsibilities
[Chỉ định policy owner, key owner, custodian, approver, application owner, auditor, incident responder.]
[Nêu RACI và yêu cầu separation of duties/dual control.]

## 5. Key classification and inventory
[Phân loại key; trường inventory bắt buộc; owner và review orphan key.]

## 6. Cryptographic requirements
[Algorithm/profile, key size/parameters, CSPRNG/provider, purpose separation, crypto agility.]

## 7. Key generation, distribution and storage
[Nguồn tạo khóa, kênh phân phối, KMS/HSM, KeyStore, exportability, backup boundary.]

## 8. Access control and use
[Principal/action/resource/context; least privilege; default deny; access review; break-glass.]

## 9. Cryptoperiod and rotation
[Profile theo key class; trigger; dual-read/single-write; migration; retire.]

## 10. Backup and recovery
[Phạm vi backup, wrapping, quorum, recovery identity, RTO/RPO, restore test.]

## 11. Compromise, revocation and destruction
[Incident authority, containment, replacement, rewrap/re-encrypt, dependency check, destruction evidence.]

## 12. Audit and monitoring
[Event taxonomy, schema, log integrity, retention, alert, evidence owner.]

## 13. Third-party and cloud services
[Shared responsibility, assurance evidence, incident notification, exit/migration plan.]

## 14. Exceptions and risk acceptance
[Approval, compensating control, expiry, remediation plan.]

## 15. Compliance and review
[Metrics, test frequency, audit, policy owner, effective date, review date, change history.]
```

## 16. Ví dụ điều khoản policy có thể kiểm thử

Các câu dưới đây là mẫu để bạn chỉnh sửa theo quyết định của tổ chức:

**KMP-INV-01 – Inventory**

> Mỗi key version thuộc phạm vi production MUST có owner, purpose, classification, algorithm, usage, state và dependency được ghi trong key inventory. Key không có owner MUST được đưa vào quy trình xử lý orphan key và không được cấp quyền sử dụng mới cho tới khi có owner được chỉ định.

**KMP-ACC-01 – Least privilege**

> Mọi request sử dụng khóa MUST được đánh giá theo principal, action, key ID/version và context. Hệ thống MUST áp dụng default deny. Quyền `Decrypt` MUST NOT tự động bao gồm quyền `ExportKey` hoặc `Destroy`.

**KMP-STO-01 – Key storage**

> Key material production MUST được lưu trong KMS/HSM hoặc ranh giới bảo vệ được security architect phê duyệt. Key material MUST NOT được ghi vào source code, log, ticket, email hoặc file cấu hình không được bảo vệ. Export plaintext MUST bị cấm mặc định.

**KMP-ROT-01 – Rotation**

> Mỗi key class MUST có cryptoperiod profile và trigger rotation được owner phê duyệt. Rotation MUST lưu key ID/version trong metadata, xác minh dữ liệu đã chuyển đổi và giữ khả năng đọc dữ liệu lịch sử cho tới khi dependency được xử lý.

**KMP-REC-01 – Recovery**

> Recovery của khóa có ảnh hưởng cao MUST yêu cầu dual control hoặc quorum theo profile. Backup MUST được kiểm tra integrity và restore test theo lịch. Recovery MUST tạo audit event có actor, key ID/version, approval và kết quả.

**KMP-DEST-01 – Destruction**

> Key MUST NOT bị destroy khi còn ciphertext, archive, backup hoặc dependency cần key version đó, trừ khi có quyết định xử lý dữ liệu được phê duyệt. Destruction MUST có dependency check, approval và evidence phù hợp với semantics của KMS/HSM.

## 17. Ánh xạ policy sang test và evidence

Sau khi hoàn thiện policy, tạo traceability matrix. Mỗi điều khoản quan trọng phải có control objective, test và evidence.

| Policy ID | Control objective | Test case | Pass criteria | Evidence |
|---|---|---|---|---|
| KMP-INV-01 | Key production có owner và metadata | Tạo key fixture thiếu owner | Guardrail chặn tạo/cấp quyền hoặc phát hiện orphan theo policy | CI report, inventory report |
| KMP-ACC-01 | Chỉ principal/action được cấp mới sử dụng key | Gọi decrypt/export bằng principal khác nhau | Allow đúng action; deny ngoài phạm vi; không có plaintext khi deny | Test report, KMS audit |
| KMP-STO-01 | Key material không xuất hiện ở nơi cấm | Kiểm tra repo/config/log và thử export | Không có secret trong artifact; export trái phép bị deny | Secret scan, KMS response |
| KMP-ROT-01 | Rotation bảo toàn khả năng đọc | Rotate key test và đọc dữ liệu cũ/mới | Version metadata đúng; decrypt thành công; key cũ retire theo điều kiện | Rotation report, test output |
| KMP-REC-01 | Recovery có thể thực hiện an toàn | Restore key test từ backup/replica | Quorum/approval đúng; canary decrypt thành công | Drill report, approval, audit |
| KMP-DEST-01 | Không destroy khi còn dependency | Thử destroy key fixture còn dữ liệu phụ thuộc | Request bị chặn; sau dependency clearance mới được phê duyệt | Dependency report, KMS audit |

Test cần có cả positive, negative và boundary case. Unit test không thay thế integration test với KMS/HSM; tài liệu policy không thay thế bằng chứng runtime. Ghi rõ môi trường, policy version, key ID/version, principal, timestamp và test run ID.

## 18. Rubric tự đánh giá

Tổng điểm: 100. Dùng rubric này để rà soát trước khi trình policy.

| Tiêu chí | Điểm | Dấu hiệu đạt |
|---|---:|---|
| Purpose, scope, definitions và references | 10 | Phạm vi rõ; không bỏ sót môi trường, backup hoặc bên thứ ba |
| Key inventory và classification | 10 | Có owner, purpose, usage, state, version và dependency |
| Governance và separation of duties | 10 | Vai trò, RACI, dual control và approval được xác định |
| Crypto baseline và generation/storage | 15 | Profile có purpose; key generation, KMS/HSM và export được kiểm soát |
| Access control | 10 | Least privilege, default deny, tenant/environment boundary và negative test |
| Lifecycle, cryptoperiod và rotation | 15 | Có trigger, migration, retire, revoke và destruction criteria |
| Backup, recovery và compromise response | 15 | Có recovery identity, quorum, runbook, test và forward recovery |
| Audit, monitoring và evidence | 5 | Event schema, integrity, retention và owner rõ ràng |
| Exception, vendor và policy review | 5 | Có expiry, risk acceptance, shared responsibility và review cycle |
| Traceability và khả năng kiểm thử | 5 | Điều khoản quan trọng có test, pass criteria và evidence |

Gợi ý diễn giải:

- **90–100:** đủ cấu trúc để trình review; vẫn cần kiểm tra pháp lý, kỹ thuật và provider-specific.
- **75–89:** có thể review nội bộ nhưng cần đóng các gap quan trọng trước khi phê duyệt.
- **60–74:** còn thiếu kiểm soát hoặc evidence; cần sửa trước khi áp dụng.
- **Dưới 60:** policy chưa đủ khả năng vận hành; cần thiết kế lại các phần nền tảng.

## 19. Tiêu chí hoàn thành bài thực hành

Bài được xem là hoàn thành khi:

- Có một policy nhất quán, không chỉ là danh sách khuyến nghị rời rạc.
- Mỗi key class có owner, purpose, usage và cách quản lý vòng đời.
- Có phân tách quyền sử dụng, quản trị, export, recovery và destruction.
- Có profile cryptoperiod/rotation được quản lý và nêu cách chọn giá trị.
- Có quy trình backup, recovery, compromise response và destruction.
- Có audit/evidence, exception và trách nhiệm nhà cung cấp.
- Có traceability matrix với positive, negative và boundary test.
- Các quyết định quan trọng có rationale và giả định được ghi rõ.
- Không có điều khoản yêu cầu export plaintext key tùy tiện hoặc tái sử dụng khóa sai mục đích.

## 20. Câu hỏi phản biện

Trước khi nộp, hãy tự trả lời:

1. Nếu key owner rời công ty, ai tiếp quản và bằng chứng nào chứng minh việc bàn giao?
2. Nếu một workload bị xâm nhập, attacker có thể dùng identity đó để decrypt tenant khác không?
3. Nếu KMS outage, recovery có phụ thuộc cùng identity provider hoặc cùng region bị lỗi không?
4. Nếu KEK bị compromise, vì sao failover sang replica cùng key material có thể nguy hiểm?
5. Nếu DEK đã được rewrap một phần, làm sao xác định object nào dùng wrapping key version nào?
6. Nếu audit sink không khả dụng, thao tác decrypt/export/recovery có tiếp tục không và vì sao?
7. Nếu cần giữ chữ ký lịch sử sau khi signing key bị revoke, verifier xác định trust tại thời điểm ký như thế nào?
8. Nếu một exception hết hạn mà hệ thống chưa khắc phục, control nào ngăn nó tồn tại vô thời hạn?
9. Nếu policy nói non-exportable nhưng cấu hình KMS cho phép export, đâu là điểm chặn trong CI/CD và runtime?
10. Bằng chứng nào cho thấy key destruction đã xử lý cả backup và replica?

## 21. Tài liệu tham khảo

- [NIST SP 800-57 Part 1 Rev. 5: Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-130: A Framework for Designing Cryptographic Key Management Systems](https://csrc.nist.gov/pubs/sp/800/130/final)
- [NIST SP 800-53 Rev. 5: Security and Privacy Controls for Information Systems and Organizations](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
- [NIST SP 800-131A Rev. 2: Transitioning the Use of Cryptographic Algorithms and Key Lengths](https://csrc.nist.gov/pubs/sp/800/131/a/r2/final)
- [FIPS 140-3: Security Requirements for Cryptographic Modules](https://csrc.nist.gov/pubs/fips/140-3/final)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
