# Thiết kế multi-tenant key

Trong chương **Thiết kế case study** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này xây dựng thiết kế quản lý khóa cho một nền tảng SaaS B2B phục vụ nhiều tenant. Mỗi tenant có dữ liệu nghiệp vụ riêng, có thể yêu cầu mức cách ly, vùng lưu trữ, thời hạn lưu giữ và khả năng tự quản lý khóa khác nhau. Thiết kế cần bảo vệ dữ liệu khỏi truy cập chéo tenant, giới hạn tác động khi một key hoặc workload bị compromise, đồng thời hỗ trợ rotation, backup, recovery và offboarding ở quy mô lớn.

Bài học đi từ yêu cầu và threat model tới kiến trúc key hierarchy, envelope encryption, authorization, lifecycle, vận hành và kiểm thử. Các tên dịch vụ và con số trong case study là giả định để minh họa; khi triển khai cần ánh xạ sang KMS/HSM, cloud account, region và chính sách thực tế của tổ chức.

## 1. Bối cảnh case study

Giả sử công ty cung cấp nền tảng SaaS quản lý đơn hàng, hóa đơn và tài liệu cho doanh nghiệp. Một deployment có hàng nghìn tenant; mỗi tenant có nhiều user, project và dữ liệu được lưu trong database cùng object storage. Một số tenant có yêu cầu hợp đồng về data residency, key ownership hoặc thời gian lưu trữ dài.

Các giả định nghiệp vụ:

- Mọi tenant phải được cách ly dữ liệu ở tầng ứng dụng và tầng mật mã.
- Một user chỉ được truy cập tenant mà identity và authorization context cho phép.
- Dữ liệu lưu trữ được mã hóa bằng authenticated encryption.
- Key material được tạo và bảo vệ bởi KMS/HSM; ứng dụng không lưu master key trong database.
- Mỗi tenant có thể được nâng cấp lên key riêng hoặc customer-managed key.
- Hệ thống hỗ trợ rotation mà không làm mất khả năng đọc dữ liệu lịch sử.
- Backup và disaster recovery phải giữ được mapping giữa ciphertext, wrapped DEK và key version.
- Việc xóa tenant phải tuân theo retention, legal hold và destruction policy.

Đây là bài toán multi-tenant key management: key architecture phải cân bằng cách ly, chi phí, độ phức tạp vận hành và khả năng phục hồi.

## 2. Yêu cầu chức năng và phi chức năng

| Nhóm | Yêu cầu |
|---|---|
| Confidentiality | Tenant A không thể giải mã dữ liệu của tenant B |
| Integrity | Thay đổi ciphertext, wrapped DEK hoặc metadata quan trọng phải bị phát hiện |
| Authorization | Mọi operation với key được ràng buộc principal, tenant, action và purpose |
| Isolation | Một lỗi cấu hình hoặc compromise không tự động mở quyền trên toàn bộ tenant |
| Lifecycle | Hỗ trợ create, activate, rotate, retire, revoke, recover và destroy |
| Availability | KMS/HSM outage không gây mất key hoặc làm dữ liệu không thể phục hồi ngoài kế hoạch |
| Scalability | Provisioning, encryption và rotation hoạt động khi số tenant tăng |
| Auditability | Có thể truy vết ai đã sử dụng key nào, cho tenant nào và vì lý do gì |
| Residency | Key và dữ liệu tuân thủ vùng lưu trữ đã cam kết |
| Customer control | Hỗ trợ lựa chọn key do nền tảng quản lý hoặc customer-managed key |
| Portability | Có quy trình migrate tenant, region hoặc key provider mà không mất dữ liệu |

Yêu cầu cần được định lượng trong thiết kế thực tế, ví dụ latency budget cho KMS call, RTO/RPO, số tenant trên một partition, cryptoperiod, retention và mức độ cô lập tối thiểu.

## 3. Threat model cho môi trường nhiều tenant

Các tài sản cần bảo vệ gồm plaintext, ciphertext, DEK, KEK, key metadata, tenant-to-key mapping, KMS policy, workload identity, backup và audit record.

Các đối tượng hoặc lỗi có thể gây rủi ro:

- Attacker chiếm được user token của một tenant.
- Tenant administrator cố truy cập dữ liệu tenant khác bằng cách thay tenant ID trong request.
- Lỗi authorization khiến service dùng tenant ID do client gửi mà không kiểm tra membership.
- SQL injection hoặc database snapshot làm lộ ciphertext và metadata.
- Compromised application workload gọi KMS với quyền rộng.
- Insider có quyền quản trị database hoặc KMS tìm cách giải mã dữ liệu.
- Một bug trong cache hoặc key resolver dùng nhầm key của tenant khác.
- KMS policy dùng wildcard hoặc context condition thiếu tenant binding.
- Backup/restore được thực hiện vào nhầm tenant hoặc region.
- Một key dùng chung bị lộ và ảnh hưởng đồng thời nhiều tenant.
- Tenant ngừng dịch vụ nhưng key bị xóa trước khi hết retention hoặc legal hold.

Thiết kế phải giả định database metadata có thể bị đọc hoặc sửa trái phép, request có thể chứa tenant ID giả mạo và event có thể đến trễ hoặc lặp. Không được coi tenant ID do client cung cấp là bằng chứng authorization.

## 4. Ranh giới tin cậy và nguyên tắc cách ly

Một nền tảng multi-tenant có nhiều ranh giới:

1. Identity boundary: user/service identity và membership của tenant.
2. Application boundary: API, service, background worker và tenant context.
3. Data boundary: database row, object prefix, partition và backup.
4. Cryptographic boundary: key, key version, wrapping operation và encryption context.
5. Administrative boundary: người vận hành, key owner, security approver và customer administrator.
6. Recovery boundary: account, region, backup vault và recovery identity.

Mã hóa bằng key riêng không thay thế authorization ở API/database. Ngược lại, row-level security không thay thế ràng buộc cryptographic context. Cần nhiều lớp kiểm soát để một lỗi đơn lẻ không dẫn tới cross-tenant disclosure.

Nguyên tắc nền tảng:

- Tenant context được suy ra từ identity đã xác thực và authorization service.
- Key resolver chỉ trả key reference thuộc tenant đã được xác minh.
- KMS/HSM authorization kiểm tra tenant scope và action.
- Ciphertext được xác thực với tenant/object context bằng AAD.
- DEK được tạo riêng theo object hoặc data unit phù hợp.
- Key material không rời khỏi KMS/HSM nếu không cần thiết.
- Quyền quản trị key, dữ liệu và audit được tách biệt.
- Mọi thay đổi tenant-to-key mapping đều có audit và kiểm soát cạnh tranh.

## 5. Các mô hình key isolation

Không có một mô hình phù hợp cho mọi tenant. Có thể cung cấp nhiều tier:

| Mô hình | Cách hoạt động | Ưu điểm | Hạn chế |
|---|---|---|---|
| Shared platform key | Nhiều tenant dùng chung một KEK; DEK riêng cho từng object | Chi phí và số lượng key thấp, vận hành đơn giản | Blast radius lớn hơn; isolation phụ thuộc mạnh vào policy và context |
| Per-tenant logical key | Mỗi tenant có key riêng trong cùng KMS account/project | Giảm blast radius, mapping rõ ràng, rotation theo tenant | Tăng số key, quota, policy và công việc vận hành |
| Per-tenant account/project | Key của tenant nằm trong boundary quản trị riêng | Isolation và audit boundary tốt hơn | Provisioning, network, quota và DR phức tạp |
| Dedicated HSM partition/cluster | Tenant lớn hoặc regulated dùng boundary HSM riêng | Tăng mức cô lập phần cứng và quản trị | Chi phí cao, giới hạn capacity và vận hành |
| Customer-managed key (CMK) | Khách hàng sở hữu key trong KMS của họ và cấp quyền cho SaaS | Khách hàng kiểm soát disable/revoke và audit key | Phụ thuộc cross-account IAM, availability và phối hợp hỗ trợ |
| Hold-your-own-key (HYOK) | Khách hàng giữ key trong hệ thống của họ; SaaS gọi operation từ xa hoặc dùng integration | Quyền kiểm soát key material cao | Latency, availability, integration và support phức tạp |

Shared platform key vẫn có thể đáp ứng một số yêu cầu nếu threat model chấp nhận và tenant binding được thực thi đúng. Tuy nhiên, nếu cam kết là một tenant compromise không ảnh hưởng khả năng giải mã tenant khác, per-tenant key boundary hoặc mạnh hơn thường phù hợp hơn.

## 6. Mô hình được chọn cho case study

Nền tảng cung cấp ba tier:

- **Standard:** mỗi tenant có một logical KEK riêng trong KMS; DEK được tạo theo object hoặc data unit.
- **Isolated:** mỗi tenant có KMS key resource và policy boundary riêng, có thể tách theo account/project hoặc region.
- **Customer-managed:** tenant cung cấp key reference trong KMS của họ; SaaS chỉ có quyền operation được cấp.

Tenant mới mặc định dùng Standard. Tenant có yêu cầu hợp đồng, dữ liệu đặc biệt nhạy cảm hoặc cần giảm blast radius được chuyển sang Isolated. Customer-managed chỉ bật sau khi xác minh cross-account authorization, key availability, audit và recovery responsibility.

Không quảng cáo tier Standard là hardware-isolated nếu thực tế chỉ có logical key separation trong cùng KMS account. Mức cách ly cần được mô tả chính xác trong tài liệu dịch vụ và hợp đồng.

## 7. Key hierarchy và envelope encryption

Một thiết kế phổ biến dùng envelope encryption:

- **DEK (Data Encryption Key):** mã hóa dữ liệu thực tế.
- **KEK (Key Encryption Key):** wrap/unwrap DEK.
- **KMS/HSM protected root:** bảo vệ KEK hoặc thực hiện key operation theo cơ chế nội bộ của provider.

Ở mô hình per-tenant, mỗi tenant có một KEK riêng. Mỗi object hoặc data unit có DEK riêng. Ciphertext và wrapped DEK được lưu cùng metadata không bí mật.

~~~mermaid
flowchart TD
    R[KMS/HSM protected root] --> T1[Tenant A KEK]
    R --> T2[Tenant B KEK]
    T1 --> A1[Wrap DEK A-Object-1]
    T1 --> A2[Wrap DEK A-Object-2]
    T2 --> B1[Wrap DEK B-Object-1]
    A1 --> DA[DEK A-Object-1]
    A2 --> DB[DEK A-Object-2]
    B1 --> DC[DEK B-Object-1]
    DA --> CA[Encrypt Tenant A data]
    DB --> CB[Encrypt Tenant A data]
    DC --> CC[Encrypt Tenant B data]
~~~

Sơ đồ là mô hình logic. Với KMS-managed key, root/master key có thể được provider quản lý hoàn toàn và không xuất hiện như một key resource mà ứng dụng có thể đọc. Với BYOK, customer-managed key hoặc HSM hierarchy, boundary thực tế tùy provider.

Không nên tự lưu root key trong database hoặc configuration. Ứng dụng chỉ lưu key reference và ciphertext blob do KMS trả về.

## 8. Per-tenant KEK và per-object DEK

Per-tenant KEK tạo một boundary quản trị cho tenant. Nó có thể được dùng để wrap nhiều DEK của tenant, nhưng không nên dùng trực tiếp làm data encryption key cho mọi object.

Per-object DEK giúp:

- Giảm lượng ciphertext phụ thuộc trực tiếp vào cùng một DEK.
- Cho phép re-encrypt một object mà không phải xử lý toàn tenant.
- Hạn chế tác động khi DEK bị lộ.
- Gắn metadata, AAD và lifecycle theo object.
- Hỗ trợ xóa dữ liệu theo object nếu retention policy cho phép.

Tạo một DEK cho mỗi object có thể làm tăng số lượng wrapped key và KMS operation. Có thể chọn DEK theo record group, file, backup set hoặc data partition tùy volume và threat model. Nếu dùng DEK theo batch, cần ghi rõ phạm vi dữ liệu và blast radius.

Không dùng một DEK toàn cục cho mọi tenant. Cũng không dùng cùng một key cho encryption, HMAC, signing và TLS; purpose separation phải được giữ.

## 9. Metadata cho ciphertext envelope

Mỗi encrypted object cần metadata đủ để xác định đúng key và parameters khi decrypt:

| Field | Ý nghĩa |
|---|---|
| format_version | Phiên bản định dạng envelope |
| tenant_ref | Định danh tenant dạng canonical/opaque |
| object_ref | ID object hoặc data unit |
| key_ref | Logical key reference hoặc KMS resource ID |
| key_version | Version tường minh nếu provider cung cấp |
| algorithm | Thuật toán và mode được allowlist |
| nonce | Nonce/IV của data encryption |
| ciphertext | Dữ liệu đã mã hóa và tag theo format |
| wrapped_dek | DEK được KEK wrap |
| wrapping_key_ref | Key dùng để wrap DEK |
| wrapping_key_version | Version của wrapping key nếu có |
| aad_version | Phiên bản canonical AAD schema |
| created_at | Thời điểm tạo metadata |

Metadata không phải secret nhưng có thể nhạy cảm về topology và tenant. Cần giới hạn quyền đọc và tránh đưa key reference nội bộ vào log công khai.

Không tin metadata chỉ vì nó nằm cùng ciphertext trong database. Dùng AEAD AAD để ràng buộc các trường quan trọng và dùng KMS encryption context để ràng buộc tenant/purpose trong key operation.

## 10. Tenant identity và authorization context

Tenant ID phải được lấy từ security context đã xác thực, ví dụ claim đã được kiểm tra hoặc membership lookup. Không lấy tenant ID từ query parameter hoặc request body rồi dùng trực tiếp để chọn key.

Luồng xác định tenant:

1. Xác thực user/service token.
2. Xác minh issuer, audience, expiry và token integrity.
3. Kiểm tra principal có membership và action phù hợp trong tenant.
4. Tạo immutable request context chứa tenant ID canonical, principal, purpose và correlation ID.
5. Chuyển context này tới data access và key service.
6. Key service kiểm tra mapping và policy trước khi trả key reference hoặc gọi KMS.

Nếu service nhận request nội bộ từ một service khác, cần xác thực workload identity và truyền tenant context theo một contract được bảo vệ. Không tin header tenant do client có thể tự đặt.

## 11. KMS encryption context và AEAD AAD

Hai cơ chế này có mục đích liên quan nhưng nằm ở hai lớp khác nhau:

- **KMS encryption context:** metadata được gửi cùng KMS operation, có thể được policy dùng để ràng buộc operation và thường được provider xác thực cùng ciphertext blob.
- **AEAD AAD:** dữ liệu bổ sung không được mã hóa nhưng được xác thực cùng ciphertext bởi thuật toán AEAD như AES-GCM.

Ví dụ context logic:

~~~json
{
  "tenant_id": "tenant-7f31",
  "purpose": "invoice-document",
  "object_id": "invoice-2026-00128",
  "environment": "production"
}
~~~

Các trường này phải được xây dựng từ trusted server-side context và canonical serialization. Không để client tùy ý chọn tenant hoặc purpose. Nếu provider coi encryption context là plaintext metadata, không đưa PII hoặc secret vào đó.

KMS context không thay thế AEAD AAD của payload. Nếu wrapped DEK được ràng buộc tenant nhưng ciphertext data không ràng buộc object/tenant, lỗi mapping ở application layer vẫn có thể ghép ciphertext sai. Nên xác thực cả wrapped DEK operation và payload metadata.

## 12. Canonical AAD và chống tráo dữ liệu

AAD cần được serialize ổn định. Nếu cùng một object có nhiều cách biểu diễn JSON, việc thay đổi thứ tự field, encoding hoặc normalization có thể khiến decrypt thất bại hoặc tạo ra mapping không nhất quán.

Thiết kế:

- Chọn một schema version rõ ràng.
- Chuẩn hóa UTF-8, field name, type và encoding.
- Không chấp nhận duplicate field.
- Dùng tenant ID canonical từ server.
- Bao gồm object ID, purpose và data format version.
- Không đưa field thay đổi sau khi encrypt vào AAD nếu không có chiến lược cập nhật.
- Lưu đủ metadata để dựng lại chính xác AAD khi decrypt.

AAD không bí mật và không mã hóa nội dung. Nó chỉ ràng buộc tính toàn vẹn. Nếu cần bảo vệ tenant/object metadata khỏi người đọc database, phải có kiểm soát dữ liệu riêng hoặc mã hóa metadata.

## 13. Quy trình encrypt cho một object

Với tenant đã được xác thực:

1. Authorization service xác minh principal được ghi object trong tenant.
2. Data service tạo object ID và immutable tenant context.
3. Key service tra tenant-to-key mapping từ registry đáng tin cậy.
4. KMS/HSM tạo DEK hoặc cấp một DEK test/production theo policy.
5. DEK được dùng để mã hóa payload bằng AEAD.
6. Tenant/object/purpose context được đưa vào KMS encryption context và payload AAD.
7. DEK plaintext được giải phóng khỏi bộ nhớ sớm nhất có thể theo runtime.
8. Ciphertext, wrapped DEK và metadata được ghi một cách nhất quán.
9. Audit event ghi key reference, tenant reference, operation và kết quả.

~~~mermaid
sequenceDiagram
    participant U as User
    participant API as Application API
    participant AUTH as Authorization
    participant KS as Key Service
    participant KMS as KMS/HSM
    participant DB as Storage
    U->>API: Create object
    API->>AUTH: Verify tenant membership and action
    AUTH-->>API: Trusted tenant context
    API->>KS: Encrypt request + tenant/object context
    KS->>KMS: Generate/wrap DEK with tenant KEK
    KMS-->>KS: Plaintext DEK + wrapped DEK
    KS->>KS: AEAD encrypt using canonical AAD
    KS->>DB: Store ciphertext + wrapped DEK + metadata
    KS-->>API: Object reference
~~~

Trong production, API cụ thể của KMS có thể trả plaintext DEK và encrypted DEK, hoặc cung cấp operation khác. Cần giới hạn nơi plaintext DEK tồn tại và không ghi nó vào log, trace, heap dump hay queue.

## 14. Quy trình decrypt cho một object

Decrypt là điểm nhạy cảm nhất đối với cross-tenant access:

1. Xác thực principal và lấy tenant context từ server.
2. Kiểm tra quyền đọc object trong tenant.
3. Đọc encrypted envelope và kiểm tra format version.
4. So sánh tenant/object reference trong metadata với trusted context.
5. Tra key mapping hiện hành và xác minh key thuộc đúng tenant.
6. Gọi KMS unwrap với đúng key reference và encryption context.
7. Dùng DEK để AEAD decrypt với canonical AAD.
8. Chỉ trả plaintext sau khi authentication tag hợp lệ.
9. Ghi audit success/failure với correlation ID.
10. Giải phóng DEK plaintext và các buffer nhạy cảm khi có thể.

Nếu tenant metadata không khớp, phải fail closed trước khi gọi decrypt. Không thử lần lượt KEK của các tenant khác cho tới khi một key giải mã thành công.

## 15. Key registry và tenant-to-key mapping

Key registry lưu mapping giữa tenant và key reference. Registry không chứa raw key material.

Một bản ghi logic có thể gồm:

| Field | Ví dụ |
|---|---|
| tenant_id | tenant-7f31 |
| key_profile | standard |
| key_ref | kms://region-a/keys/tenant-7f31 |
| active_version | version-12 |
| region | region-a |
| key_status | active |
| owner | tenant-platform-security |
| created_at | timestamp |
| rotation_due_at | timestamp |
| policy_version | 4 |

Registry cần:

- Kiểm soát write bằng service identity riêng.
- Read path có authorization và tenant scope.
- Audit mọi thay đổi key_ref, profile, version và status.
- Chống race condition khi rotation hoặc migration.
- Có backup/recovery và integrity protection.
- Có unique constraint bảo đảm một mapping active theo policy.
- Không cho tenant admin tự sửa mapping sang key tùy ý nếu chưa qua approval.

Không để ứng dụng lấy key reference từ một bảng cấu hình không có integrity protection rồi gọi KMS trực tiếp. Key registry là control-plane asset quan trọng.

## 16. Authorization ở KMS/HSM

Application authorization và KMS authorization phải cùng được kiểm tra. Một request được phép đọc object không đồng nghĩa workload có quyền decrypt mọi key.

KMS policy nên giới hạn:

- Principal/workload identity được gọi operation.
- Key resource cụ thể hoặc tenant key set.
- Action như GenerateDataKey, Encrypt, Decrypt, ReEncrypt hoặc Sign.
- Encryption context như tenant ID, purpose và environment nếu provider hỗ trợ condition.
- Account/project/region và network endpoint.
- Thời hạn credential và session.

Ví dụ policy logic:

~~~yaml
policy_name: tenant-data-decrypt
effect: allow
principal: workload:invoice-reader
resource: tenant-key-reference-from-registry
actions:
  - decrypt
conditions:
  tenant_id: trusted-request-context
  purpose: invoice-document
  environment: production
default_effect: deny
explicit_denies:
  - export_key_material
  - update_key_policy
  - schedule_key_deletion
~~~

Đây là pseudo-policy, không phải cú pháp trực tiếp của một KMS. Policy thật cần dùng identity và condition semantics của provider. Nếu một workload có quyền decrypt mọi tenant key, application layer có thể vẫn cách ly bình thường nhưng compromise workload sẽ có blast radius rất lớn.

## 17. Tách quyền và trách nhiệm

Một mô hình trách nhiệm có thể gồm:

- Tenant user: thao tác dữ liệu trong tenant.
- Tenant administrator: quản lý user và cấu hình tenant; không mặc định có quyền dùng key trực tiếp.
- Application workload: thực hiện encrypt/decrypt theo authorization context.
- Key service: kiểm tra mapping, purpose và policy.
- Key administrator: quản lý key resource và lifecycle.
- Security approver: phê duyệt thao tác rủi ro cao.
- Auditor: đọc audit evidence, không có quyền sử dụng key.
- Customer key administrator: quản lý customer-managed key trong boundary của khách hàng.

Người thay đổi key policy không nên tự phê duyệt thay đổi đó. Người có quyền quản trị database không mặc nhiên có quyền gọi KMS decrypt. Tách quyền giúp giảm nguy cơ một insider hoặc credential bị compromise có thể vừa sửa dữ liệu vừa giải mã.

## 18. Tenant provisioning và key onboarding

Khi tạo tenant:

1. Tạo tenant ID canonical và trạng thái Pending.
2. Chọn key profile theo hợp đồng và region.
3. Tạo hoặc liên kết tenant KEK trong KMS/HSM.
4. Thiết lập policy, grant và audit routing.
5. Ghi key mapping vào registry bằng transaction hoặc saga có idempotency.
6. Kiểm thử một encrypt/decrypt operation bằng workload identity.
7. Xác nhận backup/replica và recovery path nếu yêu cầu.
8. Chuyển tenant sang Active sau khi mọi precondition đạt.

Không cho tenant ghi dữ liệu trước khi key mapping và policy đã sẵn sàng. Nếu provisioning thất bại sau khi tạo key nhưng trước khi registry commit, workflow cần tìm lại resource bằng provisioning job ID, không tạo vô hạn key rác.

Với customer-managed key, onboarding còn cần xác minh quyền cross-account, key policy, region, key state, audit visibility, contact khẩn cấp và quy trình khi customer revoke access.

## 19. Rotation cho per-tenant KEK

Rotation có thể được thực hiện độc lập theo tenant:

1. Xác định tenant, key owner và rotation trigger.
2. Kiểm tra dependency, backup và current key state.
3. Tạo key version mới hoặc key resource mới theo provider semantics.
4. Kiểm tra policy và thuộc tính version mới.
5. Activate version mới cho wrap operation.
6. Nếu cần, rewrap DEK từ KEK cũ sang KEK mới.
7. Xác minh unwrap và decrypt trên mẫu dữ liệu.
8. Theo dõi operation còn dùng KEK cũ.
9. Giữ KEK cũ cho backup/archive theo retention.
10. Retire/destroy chỉ khi dependency review và approval đạt.

~~~mermaid
flowchart TD
    A[Rotation due for tenant] --> B[Preflight: owner, policy, dependency]
    B --> C{Checks pass?}
    C -->|No| X[Pause and alert]
    C -->|Yes| D[Create KEK version v2]
    D --> E[Activate v2 for new wraps]
    E --> F[Rewrap DEKs if provider requires]
    F --> G[Verify unwrap and data decrypt]
    G --> H[Monitor old version use]
    H --> I[Retire old version when safe]
    I --> J[Destroy only after retention and approval]
~~~

Nếu KMS quản lý version dưới một logical key và tự chọn version cũ khi unwrap, rewrap có thể không cần thiết. Nếu thay resource, wrapped DEK có thể phải rewrap. Không áp dụng một quy trình cố định mà không hiểu semantics của provider.

## 20. Rewrap và re-encryption khác nhau thế nào?

| Thao tác | Thành phần thay đổi | Ciphertext payload |
|---|---|---|
| KEK rotation nội bộ KMS | Key material version của KEK | Có thể giữ nguyên |
| Rewrap DEK | Wrapped DEK và wrapping key reference | Thường giữ nguyên |
| DEK rotation | DEK mới | Cần re-encrypt payload hoặc tạo object version mới |
| Data format migration | Envelope/metadata schema | Có thể cần đọc và ghi lại |
| Tenant migration | Tenant key mapping và có thể KEK | Tùy chính sách và mức cách ly |

Rewrap giữ nguyên DEK và payload ciphertext; nó chỉ thay cách bảo vệ DEK. Re-encryption dùng DEK mới để mã hóa lại dữ liệu. Rewrap thường nhẹ hơn nhưng không xử lý tình huống DEK plaintext đã bị compromise.

Nếu DEK bị lộ, chỉ rewrap DEK cũ bằng KEK mới không làm DEK đã lộ trở nên an toàn. Cần tạo DEK mới và re-encrypt dữ liệu trong phạm vi bị ảnh hưởng.

## 21. Customer-managed key, BYOK và HYOK

Các mô hình customer key cần phân biệt:

- **BYOK (Bring Your Own Key):** khách hàng cung cấp key material hoặc import key vào KMS của nền tảng theo cơ chế được hỗ trợ. Sau import, key operation có thể do KMS nền tảng quản lý.
- **Customer-managed key:** khách hàng sở hữu key resource trong KMS của họ và cấp quyền cho workload SaaS.
- **HYOK (Hold Your Own Key):** khách hàng giữ quyền kiểm soát key trong hệ thống của họ; SaaS có thể cần gọi dịch vụ key operation từ xa.

Các câu hỏi cần làm rõ:

- Ai kiểm soát key material và ai có thể disable/destroy?
- KMS API có nằm trong cùng region/account không?
- Cross-account principal nào được cấp quyền?
- Nếu khách hàng revoke access, ứng dụng xử lý dữ liệu hiện có ra sao?
- Có SLA và availability agreement cho key operation không?
- Ai chịu trách nhiệm backup/recovery và incident response?
- Có thể export/port key theo hợp đồng hay không?
- Audit event nào khách hàng và SaaS cùng nhìn thấy?

Không gọi BYOK, CMK và HYOK là một mô hình giống nhau. Quyền sở hữu, vị trí key material và trách nhiệm vận hành khác nhau đáng kể.

## 22. Backup, multi-region và disaster recovery

Multi-tenant key design cần bảo đảm ciphertext và key dependency được phục hồi cùng nhau.

Backup cần lưu:

- Ciphertext và envelope metadata.
- Wrapped DEK.
- Key reference/version và provider/region mapping.
- AAD schema version và encryption context cần để reconstruct operation.
- Manifest, checksum/signature và backup timestamp.
- Tenant ownership và retention/legal hold metadata.

Key recovery cần:

- KMS/HSM replication hoặc backup semantics được hiểu rõ.
- Recovery role riêng, least privilege và dual control khi cần.
- Region failover đã được kiểm thử.
- Mapping tenant-to-key được backup có integrity protection.
- Customer-managed key availability được đưa vào RTO/RPO.
- Old key version còn khả dụng trong suốt retention.

~~~mermaid
flowchart LR
    subgraph RegionA[Primary region]
        A1[Tenant registry]
        A2[KMS/HSM tenant KEKs]
        A3[Encrypted data + wrapped DEKs]
    end
    subgraph RegionB[Recovery region]
        B1[Replicated registry]
        B2[Replica/recovery key boundary]
        B3[Backup data + manifest]
    end
    A1 --> B1
    A2 --> B2
    A3 --> B3
    B1 --> R[Recovery workflow]
    B2 --> R
    B3 --> R
~~~

Không giả định KMS key replica tự động bao gồm key policy, grants, alias, audit subscription và application configuration. Recovery test phải xác minh toàn bộ dependency.

## 23. Tenant migration giữa region hoặc key profile

Một tenant có thể chuyển region hoặc nâng từ Standard sang Isolated. Quy trình cần giữ nguyên dữ liệu và audit lineage:

1. Xác nhận migration request, residency và approval.
2. Tạo destination key boundary.
3. Thiết lập policy và workload identity.
4. Kiểm thử encrypt/decrypt ở destination.
5. Copy ciphertext cùng metadata trong phạm vi được phép.
6. Nếu destination không thể dùng wrapped DEK cũ, unwrap/rewrap bằng hai boundary được phê duyệt.
7. Xác minh integrity và số lượng object.
8. Chuyển routing/registry bằng compare-and-set.
9. Theo dõi read/write sau cutover.
10. Giữ source key cho rollback/retention cho tới khi hoàn tất dependency review.
11. Retire source key sau approval và legal hold check.

Không đổi tenant ID hoặc object ID trong AAD mà không có migration plan. Nếu AAD gắn với tenant cũ, việc đổi metadata đơn thuần sẽ làm authentication tag không còn hợp lệ.

## 24. Tenant offboarding và crypto-erasure

Khi tenant kết thúc dịch vụ, không destroy key ngay khi tài khoản bị đóng. Cần xác định:

- Hợp đồng và retention period.
- Legal hold, dispute hoặc investigation.
- Backup/archive còn chứa ciphertext.
- Export data mà khách hàng đã yêu cầu.
- Wrapped DEK còn tồn tại ở replica hoặc region khác.
- Customer-managed key còn được khách hàng giữ hay đã revoke.
- Có yêu cầu crypto-erasure hay chỉ logical deletion.

Quy trình:

1. Chuyển tenant sang Offboarding và chặn write mới.
2. Xác minh owner, contract, retention và legal hold.
3. Export/return dữ liệu theo thỏa thuận.
4. Lập dependency inventory cho key và wrapped DEK.
5. Xóa dữ liệu theo policy, giữ tombstone chống restore ngoài ý muốn.
6. Chờ hết retention hoặc có approval crypto-erasure.
7. Disable/revoke key operation theo đúng thời điểm.
8. Destroy key khi đủ điều kiện và có bằng chứng.
9. Kiểm tra backup, replica, escrow và audit.
10. Lưu destruction evidence không chứa key material.

Crypto-erasure chỉ có hiệu quả nếu mọi bản sao key material hoặc wrapping path cần thiết đều không thể phục hồi. Nếu DEK plaintext, raw key hoặc bản copy khác còn tồn tại, hủy KEK đơn lẻ chưa chắc xóa được khả năng giải mã.

## 25. Audit và monitoring theo tenant

Audit event nên chứa metadata đủ để điều tra:

- Tenant reference và object reference.
- Key ID/version và purpose.
- Principal/workload identity.
- Action: generate, wrap, unwrap, encrypt, decrypt, rotate, disable hoặc destroy.
- Request/correlation ID và timestamp.
- KMS/HSM source, region và policy decision.
- Success/failure và error category.
- Approval/incident/change reference khi áp dụng.

Không ghi DEK plaintext, KEK bytes, private key, password, plaintext hoặc token vào log.

Monitoring nên phát hiện:

- Một workload gọi key của tenant không thuộc scope.
- Một tenant có số decrypt/unwrap tăng bất thường.
- Nhiều tenant bị rotation cùng lúc ngoài change window.
- Key bị disable/revoke trong khi workload vẫn có dependency.
- Tenant key mapping thay đổi không có approval.
- KMS context hoặc AAD mismatch tăng.
- Backup restore thất bại do key version không tồn tại.
- Customer-managed key bị revoke hoặc mất availability.

Audit platform cần tách quyền với key administrator và database administrator. Tenant customer có thể nhận audit view theo phạm vi của họ nhưng không được xem metadata của tenant khác.

## 26. Cô lập blast radius

Blast radius phụ thuộc nhiều hơn số lượng key. Cần xem xét:

- Một principal có thể gọi bao nhiêu tenant key?
- Một KEK bảo vệ bao nhiêu DEK?
- Một DEK mã hóa bao nhiêu object?
- Một key policy có áp dụng wildcard không?
- Một region/account failure ảnh hưởng bao nhiêu tenant?
- Một bug key resolver có thể chọn sai key trên bao nhiêu request?
- Một administrator có thể thay đổi mapping hoặc policy của bao nhiêu tenant?

Các biện pháp giảm blast radius:

- Per-tenant key resource cho tenant cần isolation cao.
- Per-object DEK hoặc DEK scope nhỏ.
- Workload identity tách theo service và purpose.
- KMS context condition và default deny.
- Partition theo account/project/region cho tier phù hợp.
- Rate limit và anomaly detection theo tenant/key.
- Dual control cho policy, import, restore và destruction nhạy cảm.
- Canary rotation và batch giới hạn.

Một shared application role có quyền decrypt mọi tenant key vẫn là rủi ro tập trung. Khi cần isolation mạnh, cân nhắc workload identity theo tenant group, broker service có authorization riêng hoặc key boundary tách biệt.

## 27. Hiệu năng, quota và chi phí

Per-tenant key tăng mức cách ly nhưng làm tăng số key resource, policy, audit event, rotation job và quota usage. Per-object DEK làm tăng wrapped key metadata và có thể tăng KMS call.

Các cách tối ưu:

- Dùng native GenerateDataKey/envelope encryption để tránh tự quản lý raw key.
- Cache metadata/key reference, không cache raw DEK lâu hơn cần thiết.
- Dùng bounded concurrency cho KMS operation.
- Batch rewrap theo tenant và checkpoint.
- Dùng key profile phù hợp với mức rủi ro thay vì cấp dedicated HSM cho mọi tenant.
- Theo dõi quota, latency, throttling và cost per tenant.
- Tránh gọi KMS cho mỗi byte hoặc mỗi database field nếu có thể mã hóa theo data unit hợp lý.

Caching plaintext DEK có thể giảm latency nhưng tăng thời gian tồn tại của key material và blast radius. Nếu dùng cache, cần TTL ngắn, memory protection, tenant-bound cache key, eviction, zeroization best-effort và audit. Không dùng cache chung không có tenant namespace.

## 28. Failure modes và cách xử lý

| Sự cố | Tác động | Hướng xử lý |
|---|---|---|
| Tenant context không xác định | Có thể chọn nhầm key | Fail closed trước KMS call |
| Key registry unavailable | Không resolve được key | Dùng replica có integrity/consistency; không đoán key |
| KMS throttling | Encrypt/decrypt chậm hoặc lỗi | Backoff, bounded concurrency và queue |
| KMS outage | Không thể unwrap DEK | Fail closed; kích hoạt DR đã diễn tập |
| Wrong encryption context | KMS từ chối decrypt | Kiểm tra tenant/purpose/object mapping |
| AEAD tag failure | Ciphertext/AAD/key sai hoặc bị sửa | Dừng, giữ dữ liệu gốc và điều tra |
| Tenant key disabled | Dữ liệu tenant không đọc được | Xác minh lý do, owner và compromise status trước khi enable |
| Rotation timeout | Không rõ version đã tạo chưa | Reconcile theo request/idempotency reference |
| Customer revokes CMK | SaaS không còn decrypt được | Theo customer key outage/offboarding contract |
| Region failover | Key/metadata không đồng bộ | Chạy recovery workflow và verify key version |
| Registry mapping tampering | Có thể route tới key sai | Kiểm tra integrity, audit và CAS |
| Tenant offboarding restore race | Dữ liệu/key bị phục hồi ngoài ý muốn | Tombstone, anti-resurrection và restore guard |

Không tự động enable key bị disable vì compromise. Cũng không tạo key mới cùng ID rồi giả định ciphertext cũ có thể giải mã bằng key mới.

## 29. Java example: tenant-aware envelope service

Ví dụ dưới đây minh họa ranh giới giữa authorization context, key resolver và cryptographic operation. Các interface KMS là abstraction do ứng dụng định nghĩa; không phải API cụ thể của một cloud provider.

~~~java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

record TenantContext(String tenantId, String principalId, String purpose) {}

record KeyReference(String tenantId, String keyId, String version) {}

record EncryptedEnvelope(
        String tenantId,
        String objectId,
        String keyId,
        String keyVersion,
        byte[] wrappedDek,
        byte[] nonce,
        byte[] ciphertextAndTag,
        int formatVersion) {}

interface TenantAuthorizer {
    void requireWrite(TenantContext context, String objectId);
    void requireRead(TenantContext context, String objectId);
}

interface TenantKeyResolver {
    KeyReference resolveActiveKey(String trustedTenantId, String purpose);
    SecretKey unwrapDek(
            KeyReference key,
            byte[] wrappedDek,
            String trustedTenantId,
            String purpose) throws GeneralSecurityException;
    WrappedDek generateAndWrapDek(
            KeyReference key,
            String trustedTenantId,
            String purpose) throws GeneralSecurityException;
}

record WrappedDek(SecretKey plaintextDek, byte[] wrappedDek) {}

public final class TenantEnvelopeService {
    private static final int NONCE_LENGTH = 12;
    private static final int TAG_BITS = 128;

    private final TenantAuthorizer authorizer;
    private final TenantKeyResolver keyResolver;
    private final SecureRandom random = new SecureRandom();

    public TenantEnvelopeService(
            TenantAuthorizer authorizer,
            TenantKeyResolver keyResolver) {
        this.authorizer = authorizer;
        this.keyResolver = keyResolver;
    }

    public EncryptedEnvelope encrypt(
            TenantContext trustedContext,
            String objectId,
            byte[] plaintext) throws GeneralSecurityException {

        authorizer.requireWrite(trustedContext, objectId);
        KeyReference key = keyResolver.resolveActiveKey(
                trustedContext.tenantId(),
                trustedContext.purpose());

        if (!key.tenantId().equals(trustedContext.tenantId())) {
            throw new SecurityException("Tenant/key mapping mismatch");
        }

        WrappedDek generated = keyResolver.generateAndWrapDek(
                key,
                trustedContext.tenantId(),
                trustedContext.purpose());

        byte[] nonce = new byte[NONCE_LENGTH];
        random.nextBytes(nonce);
        byte[] aad = canonicalAad(
                trustedContext.tenantId(), objectId, 1);

        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    generated.plaintextDek(),
                    new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad);
            byte[] ciphertext = cipher.doFinal(plaintext);

            return new EncryptedEnvelope(
                    trustedContext.tenantId(),
                    objectId,
                    key.keyId(),
                    key.version(),
                    generated.wrappedDek(),
                    nonce,
                    ciphertext,
                    1);
        } finally {
            // Best-effort only: provider/JVM may retain internal key copies.
            Arrays.fill(aad, (byte) 0);
            // The DEK SecretKey lifecycle must be handled by the KMS/provider
            // abstraction; do not assume this reference can be zeroized here.
        }
    }

    public byte[] decrypt(
            TenantContext trustedContext,
            EncryptedEnvelope envelope) throws GeneralSecurityException {

        authorizer.requireRead(trustedContext, envelope.objectId());

        if (!trustedContext.tenantId().equals(envelope.tenantId())) {
            throw new SecurityException("Cross-tenant envelope access denied");
        }
        if (envelope.formatVersion() != 1) {
            throw new SecurityException("Unsupported envelope format");
        }

        KeyReference key = new KeyReference(
                trustedContext.tenantId(),
                envelope.keyId(),
                envelope.keyVersion());

        SecretKey dek = keyResolver.unwrapDek(
                key,
                envelope.wrappedDek(),
                trustedContext.tenantId(),
                trustedContext.purpose());

        byte[] aad = canonicalAad(
                trustedContext.tenantId(),
                envelope.objectId(),
                envelope.formatVersion());
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                    Cipher.DECRYPT_MODE,
                    dek,
                    new GCMParameterSpec(TAG_BITS, envelope.nonce()));
            cipher.updateAAD(aad);
            // Plaintext is returned only after GCM tag verification succeeds.
            return cipher.doFinal(envelope.ciphertextAndTag());
        } finally {
            Arrays.fill(aad, (byte) 0);
        }
    }

    private static byte[] canonicalAad(
            String tenantId,
            String objectId,
            int formatVersion) {
        // Production code should use a versioned, unambiguous canonical
        // encoding with length prefixes or a rigorously defined serialization.
        String value = "tenant=" + tenantId
                + "|object=" + objectId
                + "|format=" + formatVersion;
        return value.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

Đây là ví dụ kiến trúc, chưa phải implementation production hoàn chỉnh. Cần bổ sung validation đầu vào, canonical serialization không nhập nhằng, lifecycle cho plaintext DEK theo API provider, error mapping, audit, storage transaction, nonce strategy theo volume và integration test KMS/HSM. Ví dụ cũng giả định key resolver kiểm tra tenant binding và KMS encryption context ở mọi operation.

Không lấy TenantContext trực tiếp từ request body. Đối tượng này phải được tạo sau authentication và authorization. Trong production, nên ưu tiên để KMS/HSM tạo DEK và chỉ đưa plaintext DEK vào process trong thời gian cần thiết; nếu provider hỗ trợ operation phù hợp, có thể giảm việc key material xuất hiện trong ứng dụng.

## 30. Test matrix cho multi-tenant key isolation

| Test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Same-tenant decrypt | Tenant A đọc object A | Allow, plaintext đúng |
| Cross-tenant ID tampering | User A gửi tenant ID B | Deny trước KMS call |
| Envelope tenant mismatch | Envelope B được gửi trong context A | Deny |
| Wrong KMS context | tenant/purpose context sai | KMS deny |
| Wrong AAD | Tenant/object AAD khác lúc encrypt | AEAD authentication failure |
| Registry tampering | Mapping A trỏ sang key B | Integrity/authorization failure |
| Workload overprivilege | Workload A thử gọi key B | KMS deny |
| Wrapped DEK substitution | Đổi wrapped DEK giữa hai tenant | Unwrap/decrypt fail |
| Object substitution | Dùng ciphertext object khác | AAD/tag failure |
| Key version retired | Đọc dữ liệu lịch sử bằng version còn retained | Allow theo policy |
| Key version destroyed | Ciphertext còn dependency nhưng key mất | Test phát hiện recovery failure; không giả định thành công |
| Rotation timeout | Request tạo version không nhận response | Reconcile, không tạo duplicate |
| Partial rewrap | Một phần DEK đã chuyển | Resume theo checkpoint |
| KMS outage | Decrypt không tới được KMS | Fail closed và alert |
| Customer key revoked | CMK không còn grant | Deny và kích hoạt contract/runbook |
| Backup restore | Restore tenant A vào recovery region | Data/key mapping đúng tenant A |
| Tenant offboarding | Tenant đang legal hold | Không destroy key |
| Audit isolation | Tenant A xem audit tenant B | Deny |
| Rate abuse | Tenant tạo quá nhiều KMS operation | Throttle/rate limit theo policy |
| Cache isolation | Cache key của tenant A được request B truy cập | Không có cache hit chéo tenant |

Negative test cần xác minh không có plaintext nào được trả về và không có KMS operation ngoài dự kiến. Chỉ kiểm tra HTTP 403 là chưa đủ nếu backend đã gọi decrypt thành công trước khi từ chối response.

## 31. Kịch bản thực tế: một tenant yêu cầu key riêng

Tenant Northwind đang dùng tier Standard và yêu cầu nâng lên Isolated do hợp đồng mới. Dữ liệu hiện tại đã được mã hóa bằng DEK riêng theo object và bọc bởi tenant KEK hiện tại.

Kế hoạch:

1. Xác minh yêu cầu và region residency.
2. Tạo isolated KMS key resource trong account/project boundary mới.
3. Thiết lập policy chỉ cho workload service được phê duyệt.
4. Kiểm tra key resource mới bằng test encrypt/decrypt.
5. Lập danh sách wrapped DEK và backup phụ thuộc key cũ.
6. Rewrap từng DEK bằng key mới theo batch có checkpoint.
7. Xác minh decrypt payload bằng wrapped DEK mới và AAD cũ.
8. Chuyển tenant registry sang key reference mới bằng compare-and-set.
9. Theo dõi operation và lỗi trong giai đoạn cutover.
10. Giữ key cũ cho backup và rollback trong retention đã duyệt.
11. Sau dependency review, retire key cũ và destruction theo policy.

Vì DEK và payload ciphertext không đổi trong rewrap, migration có thể giảm chi phí xử lý dữ liệu lớn. Tuy nhiên, nếu DEK đã bị lộ hoặc policy yêu cầu thay data key, phải tạo DEK mới và re-encrypt payload.

## 32. Kịch bản thực tế: workload bị nghi ngờ compromise

Một service account có quyền decrypt nhiều tenant key do cấu hình wildcard. SIEM phát hiện service gọi decrypt cho tenant không thuộc request context.

Xử lý:

1. Cô lập workload identity và thu hồi session/credential nghi ngờ.
2. Dừng các job decrypt không thiết yếu.
3. Xác định key, tenant, object và khoảng thời gian bị truy cập.
4. Bảo toàn KMS audit, application logs và network evidence.
5. Thu hẹp policy sang tenant scope và purpose allowlist.
6. Xác minh không có raw DEK hoặc plaintext bị lưu trong log/cache/dump.
7. Đánh giá key/DEK compromise; nếu có khả năng key material bị lộ, re-encrypt dữ liệu bị ảnh hưởng.
8. Tạo workload identity mới và rollout theo canary.
9. Kiểm thử cross-tenant deny và giám sát operation bất thường.
10. Hoàn thành incident review và cập nhật threat model.

Chỉ rotate KEK không đủ nếu attacker đã lấy được plaintext DEK hoặc plaintext dữ liệu. Phải xác định chính xác material nào bị lộ.

## 33. Trade-off và quyết định kiến trúc

| Quyết định | Lựa chọn tiết kiệm | Lựa chọn isolation cao | Câu hỏi quyết định |
|---|---|---|---|
| KEK scope | Shared platform key | Per-tenant key resource | Blast radius nào chấp nhận được? |
| Account boundary | Một account/project | Per-tenant hoặc tenant group | Hợp đồng/regulation yêu cầu gì? |
| DEK scope | Theo batch/data partition | Theo object | Data volume và compromise scope? |
| Customer key | Platform-managed | CMK/HYOK | Ai chịu trách nhiệm availability và recovery? |
| KMS call | Cache/batch có kiểm soát | Operation trực tiếp mỗi lần | Latency so với thời gian tồn tại key? |
| Rotation | Native KMS rotation | Orchestrated per-tenant migration | Provider có giữ old version semantics? |
| DR | Replication cùng boundary | Independent recovery boundary | Mức chống ransomware/insider cần đạt? |

Không có một tier nào tự động tốt nhất. Kiến trúc nên cho phép nâng tenant lên tier isolation cao hơn mà không cần viết lại toàn bộ encryption envelope hoặc application data model.

## 34. Những sai lầm thường gặp

- **Dùng một KEK cho mọi tenant mà không có context:** một lỗi policy có thể mở rộng blast radius toàn hệ thống.
- **Tin tenant ID do client gửi:** attacker có thể chọn key của tenant khác.
- **Chỉ dùng tenant ID trong database query:** ciphertext không được ràng buộc tenant/object bằng AAD.
- **Cho workload quyền decrypt mọi tenant key:** compromise một service có thể ảnh hưởng toàn bộ khách hàng.
- **Dùng chung DEK giữa tenant:** tạo cross-tenant cryptographic dependency.
- **Không lưu key version/format version:** không thể giải mã lịch sử sau migration.
- **Coi KMS encryption context là thay thế payload AAD:** hai lớp có phạm vi khác nhau.
- **Coi non-exportable key là đủ:** API decrypt/sign vẫn có thể bị lạm dụng.
- **Rewrap khi DEK đã compromise:** key material bị lộ vẫn còn giá trị.
- **Destroy KEK ngay sau cutover:** backup hoặc archive có thể không còn restore được.
- **Dùng cache không có tenant namespace:** có thể trả nhầm DEK giữa request.
- **Không tách BYOK, CMK và HYOK:** trách nhiệm và quyền kiểm soát bị mô tả sai.
- **Không kiểm thử region failover:** key replica và registry có thể không đồng bộ.
- **Xóa tenant trước khi xử lý legal hold:** vi phạm retention và mất bằng chứng.
- **Chỉ kiểm tra API response:** backend có thể đã thực hiện decrypt ngoài scope.

## 35. Checklist thiết kế multi-tenant key

- [ ] Có threat model và data classification cho từng tier tenant.
- [ ] Tenant identity được xác thực và authorization trước khi resolve key.
- [ ] Tenant-to-key registry có integrity, audit, backup và chống race.
- [ ] Key isolation tier được mô tả đúng với boundary thực tế.
- [ ] Có per-tenant KEK hoặc boundary mạnh hơn khi yêu cầu risk/contract cần.
- [ ] DEK có scope nhỏ và purpose separation.
- [ ] Envelope lưu key reference/version, algorithm và format version.
- [ ] KMS encryption context ràng buộc tenant và purpose.
- [ ] AEAD AAD ràng buộc tenant/object/format theo canonical schema.
- [ ] KMS/HSM policy dùng least privilege, default deny và condition phù hợp.
- [ ] Không có raw key material trong database, log, source hoặc queue.
- [ ] Rotation hỗ trợ native version semantics hoặc rewrap/re-encrypt có checkpoint.
- [ ] Old key được giữ theo dependency, backup và retention.
- [ ] Customer-managed key có contract về revoke, availability và recovery.
- [ ] Backup/DR giữ được ciphertext, wrapped DEK và key mapping nhất quán.
- [ ] Tenant migration và offboarding có approval, tombstone và anti-resurrection.
- [ ] Audit/monitoring có tenant scope và phát hiện cross-tenant operation.
- [ ] Cache, batch và concurrency được partition theo tenant/key scope.
- [ ] Có test cross-tenant negative, wrong context/AAD và registry tampering.
- [ ] Có diễn tập KMS outage, rotation failure, compromise và restore.

Thiết kế multi-tenant key an toàn phải kết hợp identity, authorization, key isolation, envelope encryption và metadata integrity. Tenant context cần được tạo từ server-side identity, ràng buộc vào KMS operation và AEAD AAD; key registry phải có integrity và audit; DEK/KEK cần scope phù hợp với blast radius. Khi bổ sung rotation, backup, customer-managed key, offboarding và test cross-tenant, nền tảng có thể tăng số lượng tenant mà vẫn duy trì khả năng cách ly, phục hồi và chứng minh trách nhiệm vận hành.
