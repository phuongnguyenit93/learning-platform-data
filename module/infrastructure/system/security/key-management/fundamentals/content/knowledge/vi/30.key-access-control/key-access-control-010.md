# Destroy key permission

**Destroy key permission** là quyền cho phép một principal khởi tạo hoặc thực hiện quy trình hủy key material. Đây là quyền có mức tác động rất cao vì khi key material bị hủy không thể khôi phục, dữ liệu đã mã hóa bằng key đó có thể không còn giải mã được và hệ thống có thể mất khả năng xác minh hoặc xử lý dữ liệu lịch sử.

Trong hệ thống quản lý khóa, quyền destroy cần được kiểm soát riêng với quyền sử dụng key, quyền disable, quyền revoke, quyền schedule deletion và quyền cancel deletion. Một người có quyền quản trị ứng dụng hoặc quyền dùng key không mặc nhiên được quyền hủy key. Quyết định hủy phải dựa trên danh tính người yêu cầu, phạm vi key cụ thể, dependency, retention, legal hold, trạng thái provider, phê duyệt độc lập và bằng chứng audit.

Bài học trình bày cách thiết kế authorization cho thao tác hủy key trong KMS/HSM và hệ thống tự quản lý: phân tách vai trò, least privilege, maker-checker, quorum, policy theo context, kiểm tra dependency, quy trình delayed deletion, chống race condition và kiểm thử negative authorization.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc cần có khả năng:

- Giải thích vì sao destroy key là một quyền đặc biệt và có blast radius lớn.
- Phân biệt destroy với disable, revoke, retire, schedule deletion, cancel deletion và xóa metadata.
- Mô hình hóa quyết định authorization theo principal, resource, action, context và policy.
- Thiết kế default deny, least privilege và quyền theo key version/purpose/tenant.
- Phân tách người yêu cầu, người phê duyệt và người thực thi.
- Áp dụng maker-checker, dual control hoặc quorum với danh tính độc lập.
- Kiểm tra dependency, retention, backup, restore, legal hold và khả năng đọc dữ liệu lịch sử trước khi cho phép hủy.
- Hiểu semantics khác nhau của KMS, HSM và key store tự quản lý.
- Dùng pending deletion/grace period và cancel permission như các kiểm soát bổ sung.
- Ngăn TOCTOU, stale approval, alias substitution và race giữa writer với destroy workflow.
- Ghi audit evidence và xây dựng kiểm thử cho cả allow và deny path.

Phạm vi chính là quyền hủy cryptographic key trong môi trường tổ chức. Các API, tên permission và trạng thái cụ thể phụ thuộc KMS/HSM/provider. Policy mẫu trong bài là mô hình khái niệm, không phải policy có thể sao chép nguyên trạng sang mọi cloud.

## 2. Destroy key permission là gì?

Destroy key permission là quyền cho phép một principal yêu cầu, phê duyệt hoặc thực hiện thao tác làm key material không còn khả năng sử dụng theo semantics của provider.

Quyền này có thể áp dụng cho:

- DEK dùng mã hóa dữ liệu.
- KEK dùng wrap/unwrap DEK.
- Signing private key.
- MAC/HMAC key.
- Key dùng cho key agreement hoặc derivation.
- Recovery key hoặc key bảo vệ backup.
- Key version cụ thể trong một logical key.
- Toàn bộ key object và các version liên quan.

Không nên biểu diễn mọi quyền này bằng một quyền chung như admin hoặc manage-key. Một principal có thể cần quyền xem metadata, disable key hoặc schedule deletion mà không được phép purge key material.

### Các câu hỏi authorization

Trước khi cho phép destroy, policy cần trả lời:

1. Ai đang yêu cầu?
2. Người đó có identity đã xác thực và role phù hợp không?
3. Key nào, version nào, thuộc tenant và environment nào?
4. Action được yêu cầu là request, approve, schedule, cancel hay execute?
5. Key đang ở trạng thái nào?
6. Có dữ liệu hoặc backup nào còn phụ thuộc không?
7. Có retention, legal hold hoặc recovery requirement không?
8. Có đủ phê duyệt độc lập và còn hiệu lực không?
9. Dependency snapshot có còn mới tại thời điểm thực thi không?
10. Provider có xác nhận đúng key ID/version và trạng thái không?

Một request chỉ hợp lệ khi toàn bộ điều kiện bắt buộc được thỏa mãn. Thiếu dữ liệu hoặc trạng thái không xác định phải dẫn tới từ chối hoặc tạm dừng quy trình theo policy.

## 3. Phân biệt destroy, disable, revoke và delete

Các thao tác thường bị nhầm lẫn:

| Thao tác | Tác động | Khả năng khôi phục |
|---|---|---|
| Disable | Ngăn một số operation dùng key | Có thể enable lại nếu provider/policy cho phép |
| Suspend | Tạm đình chỉ key theo trạng thái quản trị | Có thể resume nếu chưa revoke/compromise |
| Revoke | Làm credential/certificate/key authorization không còn được chấp nhận | Thường cần phát hành hoặc đăng ký lại |
| Retire | Ngừng dùng key cho operation mới, giữ quyền đọc lịch sử nếu policy cho phép | Có thể giữ decrypt/verify theo giới hạn |
| Schedule deletion | Đưa key vào trạng thái chờ xóa theo provider | Có thể có quyền cancel trong grace period |
| Destroy | Hủy key material theo semantics của provider | Thông thường không thể đảo ngược |
| Delete metadata | Xóa record hoặc alias quản lý | Không đảm bảo key material đã bị hủy |

Disable key không đồng nghĩa destroy key. Xóa một alias hoặc bản ghi trong database cũng không chứng minh key material đã bị xóa khỏi HSM, replica hoặc backup.

Quyền request destroy có thể khác quyền execute destroy. Quyền schedule deletion cũng có thể khác quyền finalize/purge. Thiết kế policy phải ánh xạ chính xác từng action của provider.

## 4. Vì sao destroy cần quyền riêng?

Destroy key có thể gây mất dữ liệu không thể phục hồi. Nếu attacker hoặc operator có quyền quá rộng, họ có thể:

- Hủy KEK khiến hàng loạt DEK không thể unwrap.
- Hủy DEK khiến dữ liệu tenant không thể decrypt.
- Hủy private key cần để giải mã archive hoặc xác minh quy trình cũ.
- Hủy key bảo vệ backup, làm mất khả năng khôi phục sau disaster.
- Hủy signing key trước khi hoàn tất lưu trữ bằng chứng và chuyển đổi.
- Hủy key của tenant khác do nhầm alias hoặc phạm vi.
- Hủy key đang được ứng dụng tạo dữ liệu mới sử dụng.
- Phá hủy khả năng điều tra incident hoặc đáp ứng legal hold.

Vì vậy, quyền destroy phải có phạm vi hẹp hơn quyền quản trị thông thường, có quy trình phê duyệt độc lập và được kiểm tra lại ngay trước thao tác tại provider.

## 5. Mô hình authorization: principal, resource, action và context

Một quyết định authorization có thể mô hình hóa như sau:

~~~~mermaid
flowchart TD
    P[Principal và identity]
    R[Resource: key ID và version]
    A[Action: request / approve / execute]
    C[Context: tenant, env, purpose, state]
    L[Lifecycle và dependency gates]
    Q[Approval và quorum]
    D{Policy decision}
    ALLOW[Allow đúng action]
    DENY[Deny và audit]
    P --> D
    R --> D
    A --> D
    C --> D
    L --> D
    Q --> D
    D -->|All conditions pass| ALLOW
    D -->|Any condition fails| DENY
~~~~

### Principal

Principal là người, workload, service account hoặc automation thực hiện hành động. Identity phải được xác thực bằng cơ chế phù hợp và gắn với tổ chức/team/tenant cụ thể.

Không dùng display name hoặc email text do request tự gửi làm bằng chứng identity. Lấy principal ID từ identity provider hoặc security context đã xác thực.

### Resource

Resource cần được định danh chính xác, thường gồm:

- Provider/account/project.
- Key ID bất biến.
- Key version hoặc generation.
- Tenant/namespace.
- Environment.
- Key purpose và algorithm.
- Resource owner.

Không dùng alias có thể đổi đích làm đối tượng duy nhất của approval. Nếu request bắt đầu từ alias, resolve sang immutable key ID/version, lưu kết quả và xác minh alias không đổi trước khi execute.

### Action

Tách riêng các action:

- key.destroy.request
- key.destroy.approve
- key.destroy.schedule
- key.destroy.cancel
- key.destroy.execute
- key.destroy.audit.read

Các tên trên là action minh họa. Trong provider thực tế, dùng permission/action name theo tài liệu chính thức và ánh xạ về policy nội bộ.

### Context

Context có thể bao gồm tenant, environment, purpose, classification, state, reason, change ticket, thời điểm, source network, workload attestation và trạng thái dependency.

Không dựa vào context do caller tự khai báo nếu có thể lấy từ inventory hoặc hệ thống authoritative.

## 6. Default deny và least privilege

Policy destroy phải mặc định từ chối. Chỉ cấp quyền khi principal có đúng role, resource nằm trong phạm vi được giao và mọi điều kiện bổ sung được thỏa mãn.

Các nguyên tắc:

- Không cấp destroy qua role Developer, ApplicationAdmin hoặc KeyUser thông thường.
- Không dùng wildcard resource cho quyền destroy ở production.
- Tách quyền xem metadata khỏi quyền đọc key material.
- Tách quyền encrypt/decrypt/sign khỏi quyền destroy.
- Cấp quyền theo key ID/version, tenant và environment.
- Giới hạn quyền theo thời gian hoặc approval request khi phù hợp.
- Dùng explicit deny cho key production, key root, CA, recovery và backup nếu không có quy trình chuyên biệt.
- Không cho phép quyền thừa kế rộng từ nhóm quản trị cloud nếu không có guardrail tương ứng.
- Rà soát định kỳ principal và role có quyền destroy.

### Ví dụ policy khái niệm

~~~~yaml
policy:
  default: deny
  actions:
    key.destroy.request:
      allow:
        roles:
          - KeyLifecycleOperator
        resource_scope:
          - approved-key-inventory
        conditions:
          - key_state_is_retired
          - dependencies_cleared
          - retention_cleared
          - no_legal_hold
    key.destroy.approve:
      allow:
        roles:
          - KeyCustodian
          - SecurityApprover
        conditions:
          - approver_is_not_requester
          - approval_is_bound_to_exact_key_version
    key.destroy.execute:
      allow:
        roles:
          - KeyDestructionExecutor
        conditions:
          - quorum_approved
          - approval_not_expired
          - dependency_snapshot_unchanged
          - provider_key_id_matches
          - deletion_window_elapsed
~~~~

Đây là policy minh họa để thảo luận cấu trúc. Nó không phải cú pháp IAM của một provider cụ thể. Khi triển khai, phải chuyển các điều kiện thành resource policy, IAM policy, key policy, approval workflow và kiểm soát ở ứng dụng tương ứng.

## 7. Phân tách quyền theo từng giai đoạn

Không nên để một principal tự yêu cầu, tự phê duyệt và tự thực thi destroy.

| Vai trò | Trách nhiệm | Quyền nên có |
|---|---|---|
| Key owner | Xác nhận mục đích, dependency và retention | Xem metadata, request destroy |
| Key lifecycle operator | Chuẩn bị inventory và workflow | Tạo request, schedule theo policy |
| Security approver | Đánh giá rủi ro và policy | Approve/reject |
| Data owner | Xác nhận dữ liệu không còn cần key | Approve dependency/retention clearance |
| Key custodian | Kiểm soát custody và ceremony | Tham gia quorum hoặc xác nhận |
| Destruction executor | Thực hiện thao tác tại provider | Execute đúng request đã duyệt |
| Auditor | Kiểm tra bằng chứng | Read audit, không có quyền destroy |
| Break-glass operator | Xử lý tình huống khẩn cấp | Quyền tạm thời, giới hạn và audit đặc biệt |

Vai trò có thể được gộp ở tổ chức nhỏ, nhưng các key có blast radius lớn nên giữ separation of duties rõ ràng. Một người không nên vừa là requester vừa là approver cho cùng một request.

## 8. Maker-checker, dual control và quorum

**Maker-checker** yêu cầu người tạo request khác người kiểm tra/phê duyệt.

**Dual control** yêu cầu nhiều người cùng tham gia để một thao tác nhạy cảm được phép thực hiện.

**Quorum** yêu cầu đủ số lượng approval hợp lệ trong một tập người được phép.

Một quy trình có thể yêu cầu:

- 1 requester là key owner hoặc lifecycle operator.
- 1 security approver.
- 1 data owner xác nhận dependency và retention.
- 1 executor riêng.
- Với key cấp nền tảng, yêu cầu 2-of-3 hoặc 3-of-5 custodians.

Số lượng approver phải dựa trên blast radius và yêu cầu quản trị. Hai tài khoản do cùng một người kiểm soát không tạo ra tính độc lập thực sự.

### Kiểm soát độc lập

- Approver phải có identity riêng và MFA phù hợp.
- Approval phải gắn với đúng key ID/version, action, reason và request ID.
- Không cho phép tái sử dụng approval cho key khác hoặc lần destroy khác.
- Approval có expiry và bị vô hiệu khi dependency snapshot thay đổi.
- Người execute không được sửa nội dung request đã được duyệt.
- Thay đổi key target hoặc thời gian execute cần approval mới.
- Quorum phải được xác minh từ approval record có integrity protection.

Không xem một comment “đồng ý” trong ticket là approval đủ mạnh nếu hệ thống không xác thực actor, nội dung và thời điểm.

## 9. Những key cần kiểm soát đặc biệt

Không phải key nào cũng có cùng blast radius.

| Key type | Tác động nếu destroy sai | Kiểm soát bổ sung |
|---|---|---|
| Per-object DEK | Mất dữ liệu của object | Kiểm tra object/version/backup |
| Tenant DEK | Mất dữ liệu của một tenant | Data owner và tenant dependency scan |
| KEK | Không unwrap được nhiều DEK | Rewrap inventory, backup và recovery test |
| Root/master key | Có thể ảnh hưởng toàn hệ thống | Quorum, independent recovery, explicit deny |
| Signing private key | Không tạo chữ ký mới; có thể ảnh hưởng workflow lịch sử | Lưu public key và evidence, kiểm tra purpose |
| Decryption private key | Không giải mã được ciphertext lịch sử | Archive/recipient usage và restore dependency |
| HMAC key | Không tạo/xác minh MAC theo policy cũ | Chuyển signer/verifier và lưu bằng chứng |
| CA key | Ảnh hưởng cấp/revoke certificate và trust ecosystem | CA ceremony, PKI migration, trust-anchor plan |
| Backup/recovery key | Mất khả năng restore | DR owner, restore test và escrow dependency |

Public key thường không cần giữ bí mật và có thể vẫn cần lưu sau khi private key bị hủy. Tuy nhiên, việc destroy private key chỉ an toàn sau khi đã xác định mọi operation lịch sử, dữ liệu cần decrypt và bằng chứng cần verify.

## 10. Dependency gate trước khi cho phép destroy

Authorization không nên chỉ kiểm tra role. Nó phải kiểm tra key có còn dependency hay không.

Các dependency cần rà soát:

- Ciphertext đang hoạt động và các object version.
- Wrapped DEK/EDK phụ thuộc KEK.
- Database, object storage, file archive và message payload.
- Backup, snapshot, replica, WAL/CDC và DR copy.
- Offline archive, legal hold và retention period.
- Key escrow, recovery package và disaster recovery procedure.
- Signature, MAC hoặc certificate evidence cần xác minh.
- Consumer/service vẫn gọi operation bằng key.
- Derived key hoặc key material có thể tái tạo từ secret/seed khác.
- Cache, memory dump, export và bản sao key ngoài provider.

### Dependency graph

~~~~mermaid
flowchart TD
    K[KEK-v1]
    D1[Wrapped DEK A]
    D2[Wrapped DEK B]
    D3[Recovery package]
    C1[Ciphertext A]
    C2[Ciphertext B]
    B[Backup archive]
    K --> D1 --> C1
    K --> D2 --> C2
    K --> D3 --> B
    D1 --> B
    D2 --> B
~~~~

Nếu KEK còn cần unwrap bất kỳ DEK nào trong graph, destroy KEK có thể làm dữ liệu không thể phục hồi. Nếu DEK còn cần decrypt object hoặc backup, destroy DEK cũng chưa an toàn.

Một dependency scan phải có coverage và freshness. “Không tìm thấy dependency” chỉ có giá trị khi inventory bao gồm mọi region, archive, backup, tenant và consumer trong phạm vi.

## 11. Retention, legal hold và data owner approval

Trước khi hủy key, cần xác nhận dữ liệu phụ thuộc đã hết retention hoặc đã được xử lý theo quyết định hợp lệ.

Các điều kiện cần kiểm tra:

- Retention period đã kết thúc.
- Không có legal hold, litigation hold hoặc investigation hold.
- Data owner xác nhận không còn nhu cầu đọc/restore.
- Backup và archive đã được xử lý.
- Các bản sao ở region khác đã được rà soát.
- Không có nghĩa vụ khôi phục hoặc lưu trữ theo hợp đồng.
- Quyết định destruction có owner và evidence.

Legal hold phải được kiểm tra từ hệ thống quản lý retention/compliance authoritative, không chỉ dựa vào checkbox do requester gửi. Nếu trạng thái hold không truy cập được hoặc không xác định, từ chối destroy cho tới khi có kết quả rõ ràng.

Không cho key owner tự xác nhận thay data owner khi họ không có thẩm quyền với dữ liệu.

## 12. Key lifecycle state và điều kiện được destroy

Một lifecycle model có thể gồm:

~~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> DISABLED: Stop new operations
    DISABLED --> RETIRED: No new use
    RETIRED --> DESTROY_REQUESTED: Request with evidence
    DESTROY_REQUESTED --> APPROVED: Independent approval
    APPROVED --> PENDING_DELETION: Provider schedule
    PENDING_DELETION --> CANCELLED: Authorized cancel
    CANCELLED --> RETIRED
    PENDING_DELETION --> DESTROYED: Provider finalizes
    DESTROYED --> [*]
    DESTROY_REQUESTED --> REJECTED: Gate fails
    REJECTED --> RETIRED
~~~~

Đây là state machine khái niệm. Provider có thể dùng tên state khác, chẳng hạn enabled/disabled/pending deletion/destroyed, hoặc thực hiện ceremony riêng trong HSM.

Một key thường chỉ được đưa vào destruction workflow khi:

- Không còn được phép tạo dữ liệu mới.
- Consumer đã được chuyển sang key khác hoặc ngừng hoạt động.
- Dependency scan đã hoàn tất.
- Retention và legal hold đã được giải quyết.
- Backup/restore requirement đã được đáp ứng.
- Approval/quorum còn hiệu lực.
- Key ID/version và provider state khớp request.
- Không có incident hoặc hold đang chặn thao tác.

Không dựa vào trạng thái DISABLED đơn lẻ để kết luận key có thể destroy. Key disabled vẫn có thể cần decrypt/unwrap dữ liệu lịch sử.

## 13. Schedule deletion và grace period

Một số KMS cho phép schedule deletion với thời gian chờ. Trong khoảng này, key có thể ở trạng thái pending deletion và provider có thể cho phép cancel.

Grace period là lớp bảo vệ hữu ích nhưng không thay thế authorization trước khi schedule. Một request sai vẫn có thể làm gián đoạn workload trong thời gian chờ.

Cần kiểm soát riêng:

- Quyền schedule deletion.
- Quyền cancel deletion.
- Quyền thay đổi deletion date nếu provider hỗ trợ.
- Quyền finalize/purge nếu provider có action riêng.
- Quyền xem trạng thái pending deletion.
- Quyền thay đổi alias hoặc key policy trong thời gian chờ.

Không giả định mọi provider đều có cùng thời gian chờ hoặc khả năng cancel. Một số HSM yêu cầu quorum/ceremony; một số dịch vụ quản lý key có pending deletion; một số hệ thống tự quản lý có thể xóa ngay khi lệnh được chấp nhận.

### Cancel deletion cũng là quyền nhạy cảm

Cancel có thể khôi phục key vào trạng thái hoạt động hoặc giữ key có thể dùng lại. Chỉ cấp cho role có trách nhiệm recovery, và yêu cầu lý do/audit. Không để requester tự cancel rồi schedule lặp lại nhằm né kiểm soát.

## 14. Policy theo tenant, environment và purpose

Trong hệ thống multi-tenant, resource scope phải ràng buộc tenant. Không dùng key alias do tenant gửi để suy ra quyền.

Ví dụ:

| Context | Quy tắc |
|---|---|
| Development key | Có thể dùng quy trình đơn giản hơn nhưng vẫn có owner và audit |
| Staging key | Giới hạn executor và dependency theo môi trường |
| Production tenant DEK | Cần tenant data owner và dependency clearance |
| Shared KEK | Cần platform owner, security approver và rewrap evidence |
| Root/recovery key | Explicit deny mặc định, quorum và ceremony độc lập |
| CA/signing key | PKI/signing governance riêng, kiểm tra archive và public evidence |

Policy phải xác định environment từ resource registry/provider metadata, không chỉ từ tag do caller tự khai báo. Nếu key có tag tenant không khớp inventory hoặc provider, từ chối và điều tra.

Key dùng chung nhiều tenant có blast radius lớn. Không cho một tenant admin destroy key dùng chung nếu không có quyền quản trị platform và approval phù hợp.

## 15. Permission ở KMS, HSM và ứng dụng

Quyền destroy có thể được enforcement ở nhiều lớp:

- IAM identity policy.
- Resource/key policy.
- Organization policy hoặc guardrail.
- KMS grants và role assignment.
- HSM partition, slot, quorum hoặc operator role.
- Application workflow và approval service.
- Network boundary, workload identity và device attestation.

Các lớp này bổ sung cho nhau. Application approval không đủ nếu principal vẫn có quyền gọi API destroy trực tiếp ngoài workflow. Ngược lại, IAM deny không thay thế dependency review và data owner approval.

### Phân tách control plane và data plane

Data plane thực hiện encrypt/decrypt/sign/verify/wrap/unwrap. Control plane quản lý key metadata, policy, version, disable, schedule deletion và destroy.

Một ứng dụng có thể được cấp quyền Encrypt hoặc Decrypt mà không có quyền ScheduleDeletion. Operator quản lý key metadata có thể xem state nhưng không được export key material hoặc thực hiện cryptographic operation.

Không gán role quản trị control plane quá rộng cho workload runtime.

## 16. Ví dụ policy resource-scoped

Policy khái niệm sau chỉ cho phép executor destroy key version cụ thể sau khi request được duyệt và dependency clearance còn mới:

~~~~yaml
version: 1
resource:
  provider: kms-prod
  keyId: key-tenant-42-data
  keyVersion: version-7
  tenant: tenant-42
actions:
  - key.destroy.execute
effect: allow
conditions:
  principalRole: KeyDestructionExecutor
  requestState: APPROVED
  approvalQuorum: 2
  requesterDifferentFromExecutor: true
  dependencySnapshotFresh: true
  retentionCleared: true
  legalHold: false
  providerState: PENDING_DELETION
  exactKeyVersionMatch: true
~~~~

Policy này minh họa các điều kiện. Trong thực tế, quorum và dependency evidence thường được xác minh bởi workflow service, còn KMS/IAM chỉ enforcement một phần action. Phải bảo đảm không có đường API khác cho phép principal bypass approval service.

## 17. Approval phải gắn với request bất biến

Một approval không nên chỉ nói “đồng ý destroy key”. Nó cần gắn với nội dung request cụ thể.

Approval record nên chứa:

- Request ID duy nhất.
- Provider/account/project.
- Immutable key ID và version.
- Tenant, environment và purpose.
- Action được duyệt.
- Lý do và change/incident reference.
- Dependency snapshot ID và thời điểm tạo.
- Retention/legal hold check result.
- Người yêu cầu và người phê duyệt.
- Quorum requirement và kết quả.
- Thời điểm phê duyệt và expiry.
- Scheduled deletion time.
- Integrity signature hoặc audit reference.

Nếu key ID, version, dependency snapshot hoặc action thay đổi, approval cũ phải hết hiệu lực. Không chuyển approval của key staging sang key production chỉ bằng cách đổi resource field trong request.

## 18. Chống TOCTOU và stale dependency

TOCTOU (time-of-check to time-of-use) xảy ra khi điều kiện đúng tại lúc kiểm tra nhưng thay đổi trước khi thao tác destroy thực sự chạy.

Ví dụ:

1. Workflow kiểm tra key không còn dependency.
2. Một service cũ vẫn tạo ciphertext mới bằng key.
3. Approval được ký.
4. Executor thực hiện destroy theo kết quả scan cũ.
5. Dữ liệu vừa tạo không thể giải mã.

Các biện pháp:

- Đóng quyền tạo dữ liệu mới trước khi dependency scan cuối.
- Chuyển key sang trạng thái retired/disabled theo operation policy.
- Ghi inventory revision hoặc dependency snapshot ID.
- Dùng compare-and-set để kiểm tra state version.
- Recheck legal hold và retention ngay trước execute.
- Xác minh provider key ID/version không đổi.
- Khóa hoặc serialize destruction workflow theo resource.
- Hủy approval nếu có dependency mới hoặc trạng thái thay đổi.
- Có reconciliation sau thao tác.

Không dựa vào một báo cáo dependency được tạo nhiều ngày trước khi execute.

## 19. Java 17: policy gate trước khi destroy

Ví dụ sau mô phỏng authorization gate. Nó chỉ đánh giá metadata và approval; không gọi KMS/HSM và không thực hiện thao tác hủy.

~~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public final class KeyDestroyAuthorization {
    public enum KeyState {
        ACTIVE,
        DISABLED,
        RETIRED,
        PENDING_DELETION,
        DESTROYED
    }

    public record KeyFacts(
            String provider,
            String keyId,
            String keyVersion,
            String tenantId,
            KeyState state,
            Instant deletionEligibleAt,
            boolean dependenciesCleared,
            boolean retentionCleared,
            boolean legalHold,
            String inventoryRevision
    ) {
        public KeyFacts {
            Objects.requireNonNull(provider);
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(keyVersion);
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(state);
            Objects.requireNonNull(deletionEligibleAt);
            Objects.requireNonNull(inventoryRevision);
        }
    }

    public record DestroyRequest(
            String requestId,
            String requesterId,
            String provider,
            String keyId,
            String keyVersion,
            String tenantId,
            String inventoryRevision,
            Set<String> approverIds,
            Instant approvedAt,
            Instant approvalExpiresAt
    ) {
        public DestroyRequest {
            Objects.requireNonNull(requestId);
            Objects.requireNonNull(requesterId);
            Objects.requireNonNull(provider);
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(keyVersion);
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(inventoryRevision);
            approverIds = Set.copyOf(approverIds);
            Objects.requireNonNull(approvedAt);
            Objects.requireNonNull(approvalExpiresAt);
        }
    }

    private KeyDestroyAuthorization() {
    }

    public static void authorizeExecute(
            String executorId,
            Set<String> executorRoles,
            KeyFacts key,
            DestroyRequest request,
            Instant now
    ) {
        Objects.requireNonNull(executorId);
        Objects.requireNonNull(executorRoles);
        Objects.requireNonNull(key);
        Objects.requireNonNull(request);
        Objects.requireNonNull(now);

        if (!executorRoles.contains("KeyDestructionExecutor")) {
            throw new SecurityException("Executor role is required");
        }

        if (executorId.equals(request.requesterId())
                || request.approverIds().contains(executorId)) {
            throw new SecurityException(
                    "Requester, approver and executor must be separated"
            );
        }

        if (request.approverIds().size() < 2
                || request.approverIds().contains(request.requesterId())) {
            throw new SecurityException("Independent approval quorum is missing");
        }

        if (now.isBefore(request.approvedAt())
                || !now.isBefore(request.approvalExpiresAt())) {
            throw new SecurityException("Approval is not currently valid");
        }

        if (!key.provider().equals(request.provider())
                || !key.keyId().equals(request.keyId())
                || !key.keyVersion().equals(request.keyVersion())
                || !key.tenantId().equals(request.tenantId())) {
            throw new SecurityException("Key resource does not match request");
        }

        if (!key.inventoryRevision().equals(request.inventoryRevision())) {
            throw new SecurityException("Dependency inventory has changed");
        }

        if (key.state() != KeyState.PENDING_DELETION) {
            throw new SecurityException(
                    "Key must be pending deletion before final execution"
            );
        }

        if (now.isBefore(key.deletionEligibleAt())) {
            throw new SecurityException("Provider deletion window has not elapsed");
        }

        if (!key.dependenciesCleared()
                || !key.retentionCleared()
                || key.legalHold()) {
            throw new SecurityException("Key destruction gates are not satisfied");
        }
    }
}
~~~~

Đây là policy gate minh họa, không phải authorization engine production. approverIds chỉ là metadata trong ví dụ; hệ thống thật phải xác minh chữ ký/identity/role của từng approval, quorum theo policy và tính độc lập của approver. Phải đọc trạng thái authoritative từ provider và inventory ngay trước thao tác; không tin KeyFacts do client gửi. Sau khi gate thành công, adapter provider vẫn phải kiểm tra exact key ID/version và quyền API.

## 20. Quy trình destroy có kiểm soát

~~~~mermaid
sequenceDiagram
    participant O as Key owner
    participant W as Workflow service
    participant D as Dependency inventory
    participant A as Independent approvers
    participant E as Executor
    participant K as KMS/HSM
    O->>W: Request destroy exact key version
    W->>D: Check dependencies and retention
    D-->>W: Snapshot and revision
    W->>A: Submit immutable request
    A-->>W: Approve / reject with identity
    W->>W: Verify quorum and expiry
    W->>E: Authorize execution
    E->>D: Recheck snapshot and holds
    D-->>E: Current status
    E->>K: Schedule/finalize per provider policy
    K-->>E: Provider state and operation ID
    E->>W: Record result and evidence
~~~~

Các bước vận hành:

1. **Inventory:** xác định key ID/version, owner, purpose, provider và consumer.
2. **Retire:** ngừng tạo dữ liệu mới bằng key; chuyển consumer sang key khác.
3. **Dependency scan:** rà soát ciphertext, wrapped DEK, backup, archive, DR và legal hold.
4. **Request:** requester tạo request bất biến với lý do và bằng chứng.
5. **Approval:** approver độc lập xác nhận theo quorum.
6. **Schedule:** executor schedule deletion nếu provider hỗ trợ grace period.
7. **Wait/recheck:** trong thời gian chờ, theo dõi dependency mới, hold và trạng thái provider.
8. **Execute:** thực hiện final action khi đủ điều kiện và policy cho phép.
9. **Verify:** đọc lại provider state, kiểm tra key không còn dùng được theo semantics.
10. **Audit:** lưu operation ID, actor, approvals, thời điểm và kết quả.

Không được coi thao tác gửi API thành công là bằng chứng key đã bị destroy. Provider có thể trả về trạng thái pending deletion hoặc operation accepted. Cần theo dõi tới trạng thái cuối theo tài liệu provider.

## 21. Emergency destroy và break-glass

Tình huống compromise có thể cần disable/revoke khẩn cấp, nhưng không phải mọi incident đều nên destroy key ngay. Hủy key có thể làm mất dữ liệu điều tra hoặc khả năng phục hồi.

Phân biệt:

- **Containment:** disable key, chặn quyền, cô lập workload hoặc thu hồi credential.
- **Revocation:** làm certificate/credential không còn được chấp nhận.
- **Emergency destruction:** hủy key material khi incident policy yêu cầu và dependency/impact đã được đánh giá ở mức khẩn cấp.
- **Forensic preservation:** giữ metadata, audit và evidence cần cho điều tra mà không tiếp tục cho phép key operation.

Break-glass policy cần:

- Identity đặc biệt, MFA mạnh và thiết bị/đường truy cập được kiểm soát.
- Approval hoặc quorum khẩn cấp phù hợp với mức độ sự cố.
- Thời hạn quyền ngắn.
- Scope đúng key/provider/account.
- Ghi audit độc lập và thông báo ngay sau thao tác.
- Review hậu kiểm bắt buộc.
- Không dùng break-glass để bỏ qua legal hold hoặc giữ lại quyền rộng vĩnh viễn.

Khi key bị compromise, thường cần chặn operation trước và điều tra ảnh hưởng. Destroy ngay chỉ phù hợp khi có quyết định incident rõ ràng và hệ thống đã đánh giá hậu quả với ciphertext, backup và recovery.

## 22. Audit và bằng chứng

Audit cho destroy key phải trả lời được ai đã yêu cầu, ai phê duyệt, ai thực thi, key nào bị tác động và bằng chứng nào cho thấy quy trình hợp lệ.

Các trường nên lưu:

- Request ID và operation ID của provider.
- Provider/account/project và immutable key ID/version.
- Tenant, environment, purpose và key owner.
- Actor ID, role, authentication context.
- Action: request, approve, reject, schedule, cancel, execute.
- Reason, ticket/incident/change reference.
- Dependency snapshot ID/revision.
- Retention và legal hold result.
- Approval identities, quorum và timestamp.
- Provider response/state và thời điểm hoàn tất.
- Kết quả verification sau destroy.
- Ngoại lệ, break-glass và hậu kiểm.

Không ghi raw key material, secret value, PIN hoặc token vào audit. Log phải được bảo vệ khỏi sửa/xóa bởi chính principal có quyền destroy. Với key trọng yếu, gửi audit event sang hệ thống độc lập hoặc immutable log store.

## 23. Monitoring và cảnh báo

Các tín hiệu cần theo dõi:

- Principal mới được cấp destroy permission.
- Policy wildcard hoặc explicit deny bị thay đổi.
- Request destroy cho production/root/KEK/CA/recovery key.
- Request không có dependency snapshot hoặc approval quorum.
- Approval được tạo bởi requester hoặc executor.
- Một principal schedule nhiều key trong thời gian ngắn.
- Alias/key version thay đổi sau approval.
- Pending deletion sắp tới thời điểm finalize.
- Cancel deletion bất thường hoặc lặp lại.
- Provider state không đồng bộ với workflow.
- Destroy request bị từ chối nhiều lần.
- Có operation destroy ngoài change window hoặc source network dự kiến.

Alert nên gửi tới security/key custodian theo mức độ, không chỉ tới chính requester. Cần có cơ chế phát hiện thay đổi policy làm tăng quyền destroy trước khi một key cụ thể bị tác động.

## 24. Kiểm thử authorization cho destroy

Không chỉ kiểm thử happy path. Phần lớn giá trị của destroy permission nằm ở khả năng từ chối đúng trường hợp.

| Test | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Authorized request | Owner đúng, key retired, dependency cleared | Cho phép tạo request |
| Runtime role | Workload chỉ có Encrypt/Decrypt | Từ chối destroy |
| Developer role | Principal không có destroy role | Từ chối |
| Wildcard scope | Request nhắm mọi key | Từ chối |
| Wrong tenant | Key thuộc tenant khác | Từ chối |
| Alias substitution | Alias đổi key sau approval | Từ chối và yêu cầu approval mới |
| Wrong key version | Version không khớp request | Từ chối |
| Active key | Key còn tạo dữ liệu mới | Từ chối |
| Dependency exists | Còn ciphertext/backup/wrapped DEK | Từ chối |
| Legal hold | Có hold | Từ chối |
| Stale snapshot | Inventory revision thay đổi | Từ chối |
| Missing quorum | Không đủ approver | Từ chối |
| Self approval | Requester tự approve | Từ chối |
| Executor is approver | Executor nằm trong approval set | Từ chối theo policy separation |
| Expired approval | Approval hết hạn | Từ chối |
| Reused approval | Approval đã dùng cho request khác | Từ chối |
| Provider mismatch | Provider/key ID không khớp | Từ chối |
| Pending deletion | Chưa hết grace period | Không finalize |
| Break-glass | Không có emergency identity/approval | Từ chối |
| Audit unavailable | Không ghi được audit bắt buộc | Fail closed theo policy |
| Provider timeout | Không rõ trạng thái operation | Reconcile trước khi retry |
| Duplicate execution | Retry cùng operation ID | Idempotent, không tạo action ngoài ý muốn |

### Kiểm thử race condition

- Tạo dependency mới ngay sau khi approval.
- Thay alias giữa lúc request và execute.
- Thay key policy hoặc provider state trước khi finalize.
- Hai executor cùng thực hiện một request.
- Cancel và finalize xảy ra đồng thời.
- Inventory service timeout hoặc trả snapshot cũ.
- Provider nhận request nhưng response bị mất.

Kết quả mong đợi là workflow phát hiện trạng thái không còn nhất quán, dừng thao tác hoặc reconcile theo operation ID. Không retry một lệnh destructive mù quáng sau timeout.

## 25. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gộp destroy vào admin role | Nhiều principal có quyền hủy key | Tách action và role |
| Cho requester tự approve | Không có kiểm soát độc lập | Maker-checker/quorum |
| Chỉ kiểm tra key disabled | Có thể mất quyền decrypt lịch sử | Dependency và retention gate |
| Approval chỉ gắn alias | Alias có thể trỏ key khác | Bind immutable key ID/version |
| Approval không hết hạn | Có thể dùng lại sau khi context đổi | Expiry và invalidation |
| Dependency scan cũ | TOCTOU và mất dữ liệu mới | Snapshot revision và recheck |
| Chỉ xóa metadata | Key material vẫn tồn tại | Dùng provider destruction workflow |
| Không có cancel role | Không thể xử lý nhầm schedule deletion | Tách cancel permission |
| Log chứa key bytes | Audit trở thành nguồn rò rỉ | Chỉ log metadata |
| Retry destroy không idempotent | Có thể gây trạng thái không xác định | Operation ID và reconciliation |
| Break-glass vĩnh viễn | Bỏ qua separation of duties | TTL, hậu kiểm và revoke quyền |
| Không kiểm tra backup/DR | Không thể restore dữ liệu | Dependency inventory toàn hệ thống |

## 26. Tình huống thực tế

### Tình huống A: Destroy tenant DEK

Một tenant yêu cầu xóa dữ liệu sau khi hết retention. DEK của tenant được dùng cho nhiều object version và backup.

Key owner tạo destroy request, data owner xác nhận retention và legal hold, dependency service kiểm tra object store, replica, backup và archive. Security approver duyệt request, executor schedule deletion. Sau grace period, workflow kiểm tra snapshot không đổi và provider key version khớp trước khi finalize.

Nếu còn một backup legal hold, request phải bị từ chối hoặc tạm hoãn. Không destroy chỉ vì dữ liệu chính đã bị xóa.

### Tình huống B: Destroy KEK sau rewrap

Một KEK cũ đã được thay bằng KEK mới. Trước khi destroy KEK cũ, hệ thống phải chứng minh mọi wrapped DEK cần giữ đã được rewrap, bao gồm backup, snapshot, archive và DR.

Nếu chỉ kiểm tra database hiện hành mà bỏ sót offline archive, dữ liệu cũ có thể không còn phục hồi được. Dependency snapshot phải bao phủ toàn bộ retention domain và có bằng chứng restore test.

### Tình huống C: Signing private key hết cryptoperiod

Một signing key không còn được dùng để ký mới. Hệ thống đã chuyển signer sang key mới và giữ public key cũ để xác minh chữ ký lịch sử.

Destroy private key cũ có thể phù hợp sau khi kiểm tra không còn nhu cầu ký lại hoặc decrypt bằng private key đó, archive evidence được bảo toàn và policy phê duyệt. Public key/certificate và dữ liệu audit vẫn có thể cần giữ lại.

### Tình huống D: Operator cố destroy key qua API trực tiếp

Một operator có quyền schedule deletion gọi thẳng API provider mà không tạo workflow request. Nếu chỉ có approval service kiểm tra nhưng IAM vẫn cho phép direct API call, quy trình có thể bị bypass.

Giải pháp là giới hạn provider permission cho workflow executor, dùng resource policy/guardrail, ghi audit độc lập và kiểm thử cả đường gọi trực tiếp.

## 27. Checklist triển khai

### Policy và identity

- [ ] Destroy là action riêng, không gộp vào quyền admin chung.
- [ ] Default deny và resource scope theo immutable key ID/version.
- [ ] Principal được xác thực và có owner rõ ràng.
- [ ] Requester, approver và executor được phân tách.
- [ ] Quorum dựa trên identity độc lập.
- [ ] Approval gắn với request bất biến và có expiry.
- [ ] Break-glass có scope, TTL và hậu kiểm.

### Dependency và lifecycle

- [ ] Key đã retired hoặc state đủ điều kiện.
- [ ] Không còn operation mới phụ thuộc key.
- [ ] Ciphertext, DEK, KEK, backup và archive đã được inventory.
- [ ] Retention và legal hold đã được kiểm tra.
- [ ] Data owner xác nhận dependency clearance.
- [ ] Dependency snapshot còn mới tại execute.
- [ ] Provider key ID/version khớp request.

### Provider và vận hành

- [ ] Phân biệt schedule, cancel, finalize và destroy.
- [ ] Hiểu grace period và provider-specific semantics.
- [ ] IAM không cho phép bypass workflow.
- [ ] Có operation ID và reconciliation khi timeout.
- [ ] Audit được lưu độc lập và không chứa key material.
- [ ] Có alert cho policy change và pending deletion.
- [ ] Có negative test cho self-approval, wrong tenant và stale snapshot.
- [ ] Có quy trình khôi phục/cancel nếu provider hỗ trợ và còn trong thời hạn.

## 28. Câu hỏi tự kiểm tra

**1. Destroy key permission là gì?**

Quyền yêu cầu hoặc thực hiện thao tác hủy key material theo policy và semantics của provider.

**2. Vì sao destroy cần quyền riêng?**

Vì thao tác có thể làm mất khả năng decrypt, unwrap, sign hoặc phục hồi dữ liệu không thể đảo ngược.

**3. Disable key có đồng nghĩa destroy key không?**

Không. Disable thường chặn operation nhưng key material vẫn còn và có thể được enable lại nếu policy/provider cho phép.

**4. Xóa alias có chứng minh key material đã bị hủy không?**

Không. Alias là metadata/reference; phải xác minh provider destruction state.

**5. Default deny có ý nghĩa gì?**

Mọi action destroy bị từ chối trừ khi có policy allow rõ ràng và tất cả điều kiện bắt buộc được thỏa mãn.

**6. Vì sao tách requester, approver và executor?**

Để một người không thể tự khởi tạo, tự duyệt và tự thực hiện thao tác có tác động lớn.

**7. Quorum có luôn bảo đảm dual control không?**

Không nếu nhiều account cùng do một người kiểm soát hoặc identity không độc lập.

**8. Approval phải gắn với thông tin nào?**

Request ID, immutable key ID/version, provider, tenant, action, reason, dependency snapshot và expiry.

**9. Vì sao alias không nên là resource duy nhất trong approval?**

Alias có thể đổi đích; approval phải ràng buộc vào key ID/version bất biến.

**10. Dependency gate kiểm tra những gì?**

Ciphertext, wrapped DEK, backup, archive, DR, legal hold, retention và consumer còn sử dụng key.

**11. Vì sao key disabled vẫn có thể chưa được destroy?**

Nó có thể còn cần decrypt/unwrap hoặc phục hồi dữ liệu lịch sử.

**12. Schedule deletion khác destroy thế nào?**

Schedule deletion đặt key vào trạng thái chờ xóa; destroy là trạng thái hủy cuối theo provider.

**13. Grace period có thay thế approval không?**

Không. Grace period chỉ là lớp bảo vệ bổ sung sau khi request đã được authorization.

**14. Ai nên có cancel deletion permission?**

Role recovery/custodian được chỉ định, có scope và audit riêng.

**15. TOCTOU trong destroy workflow là gì?**

Dependency hoặc key state thay đổi sau khi kiểm tra nhưng trước khi thực thi destroy.

**16. Cách giảm TOCTOU?**

Dùng immutable resource ID, snapshot revision, compare-and-set và recheck ngay trước execute.

**17. Có nên destroy KEK ngay sau khi tạo KEK mới không?**

Không. Phải rewrap mọi DEK cần giữ và xử lý backup/archive/DR trước.

**18. Destroy signing private key có cần giữ public key không?**

Có thể cần giữ public key/certificate và evidence để xác minh chữ ký lịch sử.

**19. Khi provider timeout sau lệnh destroy, có nên retry ngay không?**

Không. Phải reconcile operation ID và provider state trước khi retry.

**20. Audit destroy cần tránh ghi gì?**

Không ghi raw key material, secret value, PIN hoặc token; chỉ ghi metadata và evidence cần thiết.

## 29. Tài liệu tham khảo

- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management: lifecycle, usage period, protection và destruction.
- NIST SP 800-53 Rev. 5 — Security and Privacy Controls: access enforcement, separation of duties, least privilege và audit.
- NIST SP 800-88 Rev. 2 — Guidelines for Media Sanitization: phân biệt key destruction/crypto erase với sanitization media.
- ISO/IEC 27001 và ISO/IEC 27002 — kiểm soát truy cập, quản lý tài sản và quản lý khóa.
- Tài liệu IAM, key policy, deletion scheduling, pending deletion, cancel và purge của KMS đang triển khai.
- Tài liệu HSM về key lifecycle, operator roles, quorum, dual control và destruction ceremony.
- Tài liệu nội bộ về data retention, legal hold, backup, recovery và incident response.

