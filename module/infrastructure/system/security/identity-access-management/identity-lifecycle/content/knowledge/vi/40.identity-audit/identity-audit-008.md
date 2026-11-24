# Revocation evidence – chứng cứ thu hồi quyền trong kiểm toán danh tính IAM

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **revocation evidence** là gì, tại sao một lệnh thu hồi hoặc phản hồi HTTP thành công chưa chứng minh quyền truy cập đã bị chặn.
- Phân biệt **quyết định thu hồi, yêu cầu, thực thi, trạng thái quan sát được, quyền hiệu lực và bằng chứng xác minh** trong chuỗi Joiner–Mover–Leaver.
- Xác định chứng cứ phù hợp cho **tài khoản, nhóm/role/entitlement, session/cookie, OAuth access/refresh token, credential, privileged access, service account và workload identity**.
- Thiết kế mô hình chứng cứ có **identityId, relationshipId, actor, source authority, resource, target, tenant, effectiveAt, correlation/causation, policy version, timestamps, kết quả và evidence reference**.
- Lựa chọn phương pháp **target readback, kiểm tra PEP/PDP, controlled access probe, session termination verification, API audit correlation** và cách giải thích giới hạn độ tin cậy của chúng.
- Vận dụng **IdP/SSO/OIDC/SAML, SCIM, RBAC/ABAC/PBAC, PAM/JIT, HRIS, service identity và reconciliation** để thu thập, bảo vệ và kiểm tra chứng cứ.
- Xử lý **event trễ, token còn hạn, cache/replication, race condition, target không hỗ trợ API, partial failure và quyền truy cập tồn dư** với trạng thái minh bạch.
- Áp dụng nguyên tắc **tamper-evident audit, chain of custody, data minimization, retention, SoD** và ví dụ Java/SQL để bảo đảm chứng cứ có thể được sử dụng trong kiểm toán.
- Xây dựng **kiểm thử âm tính, KPI, quy trình hậu kiểm và hồ sơ kết thúc** cho từng tình huống thu hồi quyền.

## 1. Revocation evidence là gì?

**Revocation evidence (chứng cứ thu hồi)** là tập hợp các bản ghi có thể truy vết giúp tổ chức **chứng minh một yêu cầu thu hồi quyền đã được quyết định đúng thẩm quyền, được truyền tới đúng hệ thống, được xử lý và được kiểm tra kết quả**, trong **phạm vi, thời điểm và mức độ bảo đảm được tuyên bố**.

Ví dụ: HRIS báo nhân viên nghỉ việc lúc 18:00; IGA phát lệnh gỡ quyền; IdP trả “User disabled”; SCIM trả HTTP thành công; nhưng người đó vẫn có session ERP và token API chưa hết hạn. Khi đó **có chứng cứ yêu cầu và một phần thực thi**, nhưng **chưa có đủ chứng cứ quyền truy cập đã bị chặn tại mọi đích**.

Bài học thuộc chương **Identity audit** trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Nội dung gắn với **quản trị vòng đời Joiner–Mover–Leaver từ xác minh danh tính, tạo account, cấp quyền, đổi vai trò đến thu hồi**, sử dụng **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**.

### 1.1. Ba câu hỏi không được đánh đồng

1. **Có quyết định thu hồi hợp lệ không?** Ai/nguồn nào yêu cầu, vì sao, từ lúc nào, trên quyền nào?
2. **Hệ thống đích đã thay đổi trạng thái chưa?** Account, group, role, session, grant, key và policy được cập nhật ra sao?
3. **Quyền thực sự còn dùng được không?** Tại API, SaaS, database, máy chủ hoặc phiên đang mở, hành động bị DENY theo phạm vi nào?

Một câu trả lời ở tầng 1 **không thay thế** bằng chứng tầng 2 hoặc 3.

### 1.2. “Chứng minh không còn quyền” cần nêu giới hạn

Trong hệ phân tán, **không dễ chứng minh tuyệt đối rằng không tồn tại bất kỳ đường truy cập nào ở mọi thời điểm**. Một phép thử một token trên một API chỉ chứng minh kết quả của **một điều kiện thử**, không chứng minh mọi token/thiết bị/target đều đã bị chặn.

Hồ sơ tốt phải nêu **đích nào thuộc phạm vi, trạng thái nào đã quan sát, phép thử bao phủ những gì, nguồn chứng cứ và các ngoại lệ chưa xác minh**, không dùng tuyên bố tuyệt đối thiếu cơ sở.

## 2. Cần thu hồi cái gì? Không chỉ là user account

| Đối tượng | Ví dụ | Bằng chứng cần tìm |
| --- | --- | --- |
| **Human identity eligibility** | Quan hệ nhân sự đã kết thúc | HRIS effective event, identity registry state |
| **IdP account** | Tài khoản corporate SSO bị disable | Native IdP readback và authentication outcome |
| **Target account** | ERP/CRM account inactive | SCIM/target API readback, local account status |
| **Group/role/entitlement** | SalesAdmin hoặc FinanceApprover bị gỡ | Target role list, group expansion, current policy |
| **Application session** | Cookie web ở SaaS còn đăng nhập | Local session termination, protected test |
| **IdP/SSO session** | Phiên OIDC OP hoặc SAML IdP | OP/IdP session status, RP logout outcome |
| **OAuth refresh grant** | Native app không thể xin token mới | Grant/family revocation, token endpoint test theo policy |
| **OAuth access token** | JWT/opaque token cũ không còn được chấp nhận | Introspection/denylist/PEP deny hoặc TTL bound |
| **Credential** | Password, API key, cert, client secret | Issuer/key inventory, rotation/revocation, denied use |
| **PAM/JIT elevation** | Cloud admin tạm thời bị thu hồi | Activation state và target privileged action |
| **SSH/RDP/VPN/DB session** | Kết nối đã mở bị chấm dứt | Session inventory, terminate outcome, target verification |
| **Delegated capability** | Token/job làm thay user | Delegation/grant state, consumer policy |
| **Workload/robot principal** | OAuth client, bot ERP, K8s/cloud trust | Principal disabled, trust/key/role removed, API readback |
| **Network exception** | Tunnel/ACL mở tạm khi emergency | Firewall/network config readback và kiểm đường truy cập |

**Không phải mọi hệ thống đều hỗ trợ mọi kiểu thu hồi.** Một hồ sơ chứng cứ phải dựa vào **capability thực tế** của từng nền tảng và phân biệt “NOT_SUPPORTED” với “VERIFIED”.

### 2.1. Gỡ quyền và đóng phiên là hai lớp

Một người bị gỡ role `payment.approve` nhưng còn phiên browser có thể vẫn **được đăng nhập** để đọc báo cáo. Đó có thể là trạng thái hợp lệ sau Mover. Ngược lại, logout hoàn tất nhưng role admin vẫn được cấp sẽ khiến người đó có lại quyền khi đăng nhập tiếp.

Do đó phải biết mong muốn là **revoke account, revoke entitlement, revoke session, revoke credential hay kết hợp**.

## 3. Chuỗi bằng chứng từ lý do đến kết quả

~~~mermaid
flowchart TD
    SRC["Authoritative trigger: HRIS / security / owner"] --> DEC["Revocation decision + scope + policy"]
    DEC --> CMD["Command issued / queued"]
    CMD --> CONN["IdP / SCIM / PAM / cloud connector"]
    CONN --> ACK["Delivery / API acknowledgment"]
    ACK --> OBS["Target state readback"]
    OBS --> EFF["Effective access verification at PEP"]
    EFF --> Q{"Scope and assurance satisfied?"}
    Q -->|"Yes"| CLOSE["Verified closure + audit evidence"]
    Q -->|"Partial / Unknown"| EX["Exception, owner, mitigation, retry"]
    EX --> OBS
    CMD --> AUD["Immutable/tamper-evident audit references"]
    ACK --> AUD
    OBS --> AUD
    EFF --> AUD
~~~

### 3.1. Sáu mốc cần định danh

| Mốc | Ví dụ sự kiện | Bằng chứng chứng minh được |
| --- | --- | --- |
| **DECIDED** | Resource owner quyết định revoke | Thẩm quyền, phạm vi và thời điểm |
| **REQUESTED** | IGA tạo task thu hồi | Yêu cầu được ghi và theo dõi |
| **SENT/ACKNOWLEDGED** | SCIM PATCH nhận 2xx | Connector/target nhận hoặc xử lý theo API contract |
| **APPLIED** | Target báo role đã gỡ | Thay đổi ở control plane của target |
| **OBSERVED** | Readback cho thấy role không còn | Snapshot hiện tại của entitlement/account |
| **VERIFIED_DENIED** | PEP từ chối thao tác từng được phép | Hiệu lực tại phép thử/đường kiểm được xác định |

Cần tách **executionOutcome** khỏi **verificationOutcome**. Một target có thể đã áp dụng thay đổi nhưng chưa có phương thức kiểm thử trực tiếp; hồ sơ phải nêu rõ giới hạn đó.

### 3.2. Một kết quả HTTP 200 không nói hết

`HTTP 200` từ endpoint revoke token, `HTTP 204` từ SCIM PATCH hoặc một ticket “Done” có **ngữ nghĩa phụ thuộc API**. Không tự diễn giải “200 = không còn bất kỳ quyền nào” nếu chưa đọc contract và kiểm trạng thái đích.

### 3.3. Trạng thái PARTIAL không phải lỗi định dạng

Một workflow có 8 target, 7 đích đã xác minh nhưng VPN đang offline, nên báo **PARTIAL/UNKNOWN** với owner, severity và cách xử lý. Không được nâng tổng thể lên `COMPLETE` chỉ vì đa số đã thành công.

## 4. Khác biệt giữa evidence, assertion và claim

**Assertion/claim** có thể là lời khẳng định được một hệ đưa ra; **evidence** phải có nguồn, phạm vi và cách kiểm để người khác đánh giá được mức độ hỗ trợ cho kết luận.

Ví dụ:

~~~text
Assertion:
  "Quyền CRM của person-1042 đã bị thu hồi."

Evidence A:
  IGA có lệnh revoke role CRM.

Evidence B:
  CRM admin API trả role list không chứa SalesAdmin.

Evidence C:
  CRM PEP từ chối SalesDiscountApprove với phiên/identity
  đã được kiểm trong điều kiện thử được phê duyệt.

Kết luận:
  CRM SalesAdmin đã được gỡ trong scope được kiểm.
  Cần ghi rõ các sessions, tokens, tenants và đường khác
  chưa bao phủ, nếu có.
~~~

### 4.1. Thứ bậc chứng cứ là theo mục đích, không tuyệt đối

| Loại chứng cứ | Mạnh ở khẳng định nào? | Không tự chứng minh |
| --- | --- | --- |
| **Approval artifact** | Quyết định có thẩm quyền | Target đã gỡ |
| **IAM command log** | Yêu cầu gửi đi | Target đã áp |
| **Connector API acknowledgment** | Lời gọi được tiếp nhận/xử lý theo contract | Session/token ngừng hiệu lực |
| **Target account/role readback** | Trạng thái resource ở thời điểm đọc | Mọi phiên và quyền gián tiếp |
| **Issuer grant/credential state** | Token issuance hoặc key state | JWT cũ bị mọi API chặn |
| **PEP enforcement log** | Một request cụ thể PERMIT/DENY | Tất cả đường truy cập khác |
| **Controlled access probe** | Kết quả của phép thử đã xác định | Mọi token/thiết bị không được thử |
| **Independent reconciliation** | So desired/observed từ nhiều nguồn | Tính toàn vẹn tuyệt đối của mọi nguồn |
| **Tamper-evident evidence chain** | Dấu hiệu sửa/xóa sau khi thu | Hoạt động bị thiếu ngay từ nguồn |

### 4.2. Một phép thử bị 401 chưa chắc vì đã thu hồi

HTTP 401 có thể do **token sai audience, hết hạn, invalid signature hoặc API không còn reachable qua đường được dùng**. Muốn khẳng định lệnh revoke có hiệu quả, cần xác minh **điều kiện trước/sau, nguyên nhân từ chối, target sẵn sàng và nguyên nhân thay đổi**.

## 5. Phạm vi và khóa định danh của hồ sơ thu hồi

Một người có thể có nhiều **employment relationships**, accounts, tenants, devices, OAuth clients và service identities liên quan.

### 5.1. Các định danh cần tách

- **identityId:** danh tính nhân sự/đối tác được identity registry công nhận.
- **relationshipId:** căn cứ việc làm/hợp đồng/đơn vị có quyền.
- **issuer + subject (`iss` + `sub`):** định danh của user ở OIDC/IdP.
- **targetAccountId:** account thực sự ở CRM, ERP, directory hoặc SaaS.
- **principalId:** service/robot/workload identity nếu đối tượng không phải người.
- **sessionRef/grantRef:** tham chiếu an toàn đến phiên/quyền ủy quyền.
- **resourceId/entitlementId:** quyền, role, action hoặc tài nguyên cụ thể.
- **tenantId/environment:** ranh giới cấp quyền.
- **deviceRef/clientId:** máy hoặc ứng dụng liên quan.

Không dùng **email, displayName hoặc username** làm khóa duy nhất vì có thể đổi hoặc được tái sử dụng.

### 5.2. Phân biệt actor, subject, owner và verifier

Ví dụ:

~~~text
Subject:             person-1042, relationship employment-A
Revocation initiator: IAM workflow from HRIS event
Approver:            security/owner theo policy
Executor:            SCIM connector service principal
Target:              finance-saas
Verifier:            reconciliation worker / PEP audit
Resource owner:      finance-security-team
~~~

Những vai trò trên **có thể là những identity khác nhau**. Không tự gán mọi event cho nhân viên bị thu hồi.

### 5.3. Quyền theo nhiều quan hệ

Một người nghỉ ở tenant-a nhưng còn hợp đồng hợp lệ với tenant-b. Cần chứng minh **các quyền dựa vào relationship-a** đã bị thu hồi. Không kết luận “mọi quyền của identity đã hết” nếu policy chỉ yêu cầu thu hồi một phạm vi.

Nếu incident compromise tác động toàn identity, phạm vi có thể được mở rộng theo thẩm quyền, phải ghi quyết định.

## 6. Mô hình chứng cứ tối thiểu

Một **evidence package** nên đủ để người kiểm toán tái dựng quá trình mà không cần mở bí mật hay suy luận từ một ảnh chụp UI.

| Nhóm | Trường nên có | Ý nghĩa |
| --- | --- | --- |
| **Context** | `revocationId`, `reasonCode`, `sourceEventRef` | Vì sao tạo quy trình |
| **Subject** | `identityId`, `relationshipId`, `principalType` | Ai/đối tượng nào bị tác động |
| **Scope** | `targetSystemId`, `tenantId`, `resourceId`, `entitlementId` | Cái gì phải thu hồi |
| **Authority** | `initiatedBy`, `approvedBy`, `policyRevision` | Thẩm quyền và quyết định |
| **Time** | `occurredAt`, `effectiveAt`, `requestedAt`, `appliedAt`, `observedAt`, `verifiedAt` | Khi nào từng mốc diễn ra |
| **Execution** | `connectorRef`, `operationRef`, `targetAck`, `targetOutcome` | Lời gọi/đích xử lý |
| **Verification** | `method`, `verifierRef`, `result`, `testedScope` | Bằng chứng thực thi |
| **Provenance** | `evidenceRef`, `sourceSystem`, `schemaVersion`, `captureMethod` | Nguồn và cách thu |
| **Integrity** | `digestRef`, `signatureRef`, `retentionPolicyRef` | Chống chỉnh sửa và lưu trữ |
| **Exception** | `gapReason`, `owner`, `severity`, `remediationDueAt` | Điều chưa xác minh |
| **Lineage** | `correlationId`, `causationId`, `sourceVersion` | Nối chuỗi sự kiện |

Không cần mọi trường ở mọi event. Ví dụ một kết quả API DENY có thể không có approval; phải có liên kết an toàn tới **hồ sơ quyết định**.

### 6.1. JSON package minh họa

~~~json
{
  "revocationId": "rev-20261123-8842",
  "reasonCode": "LEAVER",
  "sourceEventRef": "hris-terminate-1881",
  "subject": {
    "principalType": "HUMAN",
    "identityId": "person-1042",
    "relationshipId": "employment-A-1042",
    "tenantId": "tenant-a"
  },
  "scope": {
    "targetSystemId": "finance-saas",
    "targetAccountRef": "saas-account-722",
    "entitlementId": "FinanceApprover",
    "mode": "REMOVE_ENTITLEMENT"
  },
  "decision": {
    "policyRevision": "jml-offboarding-v7",
    "authorizedInitiatorRef": "iam-lifecycle-processor"
  },
  "times": {
    "effectiveAt": "2026-11-23T18:00:00+07:00",
    "requestedAt": "2026-11-23T18:00:02+07:00",
    "appliedAt": "2026-11-23T18:00:05+07:00",
    "verifiedAt": "2026-11-23T18:00:09+07:00"
  },
  "execution": {
    "connectorOperationRef": "scim-op-913",
    "targetAckStatus": "SUCCESS"
  },
  "verification": {
    "result": "VERIFIED_DENIED",
    "method": "ROLE_READBACK_AND_SAFE_AUTHZ_PROBE",
    "scopeCovered": ["FinanceApprover", "finance-saas/tenant-a"],
    "evidenceRefs": ["evidence-readback-81", "evidence-pep-18"]
  },
  "integrity": {
    "manifestRef": "manifest-8842",
    "retentionPolicyRef": "iam-audit-prod"
  }
}
~~~

Đây là **mẫu giáo dục**, không phải schema chuẩn. Các trường `VERIFIED_DENIED`, `SUCCESS` chỉ được đặt nếu có **bằng chứng thực tế**; dữ liệu ví dụ không chứng minh một hệ thống thật đã xử lý.

### 6.2. Không đưa chứng cứ bí mật vào message bus

`evidenceRef` trỏ tới một kho được bảo vệ; không nhúng **password, raw access token/refresh token, session cookie, private key, recovery code, ảnh giấy tờ xác minh hoặc dữ liệu nghiệp vụ nhạy cảm** vào payload/log rộng.

## 7. Thời gian: mốc hiệu lực và mốc thu thập bằng chứng

Một chuỗi revocation có thể có nhiều đồng hồ.

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **sourceOccurredAt** | HRIS/security record được tạo/cập nhật | 17:20 |
| **effectiveAt** | Quyền cần bị thu hồi từ lúc nào | 18:00 |
| **requestedAt** | IAM phát yêu cầu | 18:00:01 |
| **sentAt** | Connector gửi target API | 18:00:02 |
| **acknowledgedAt** | Target phản hồi | 18:00:04 |
| **appliedAt** | Target xác nhận local state | 18:00:05 |
| **observedAt** | Readback chụp trạng thái | 18:00:07 |
| **verifiedAt** | Kiểm hiệu lực được ghi nhận | 18:00:09 |
| **ingestedAt** | Audit/SIEM nhận bản ghi | 18:00:11 |

### 7.1. Nguy cơ dùng nhầm `ingestedAt`

Một Leaver effective lúc 18:00 nhưng sự kiện tới lúc 18:12. Không đổi effectiveAt thành 18:12 để che 12 phút exposure. Hồ sơ phải lưu **event lateness** và các action trong khoảng 18:00–18:12 theo mức rủi ro.

### 7.2. Đồng hồ và độ chính xác

- Sử dụng timestamp có timezone rõ ràng, ưu tiên chuẩn hóa UTC cho phân tích.
- Ghi nguồn timestamp, độ lệch đồng hồ nếu được biết.
- Không dựa hoàn toàn vào timestamp để xử lý event sai thứ tự; dùng **version/sequence** khi có.
- Nếu target chỉ cho biết trạng thái tại thời điểm readback, **không tự suy ra chính xác giây quyền hết hiệu lực**.
- Phân biệt thời điểm **thực hiện phép thử** và thời điểm **lưu kết quả vào audit**.

### 7.3. Latency đúng nghĩa

~~~text
Effective-to-request lag      = requestedAt - effectiveAt
Request-to-apply latency      = appliedAt - requestedAt
Apply-to-verify latency       = verifiedAt - appliedAt
Effective-to-denial latency   = firstVerifiedDeniedAt - effectiveAt
~~~

Khi thiếu một timestamp đáng tin, chỉ số tương ứng là **UNKNOWN/UNMEASURABLE**, không lấy số 0 để báo cáo hiệu suất.

## 8. Chất lượng, độ tin cậy và giới hạn chứng cứ

Một hồ sơ chứng cứ không chỉ hỏi **có bản ghi hay không**, mà phải đánh giá **đầy đủ, chính xác, còn mới, nhất quán, đáng tin và có thể kiểm tra lại**.

### 8.1. Các tiêu chí chất lượng

- **Authenticity:** nguồn phát có được xác thực, được phép báo kết quả về target này không?
- **Integrity:** bản ghi có bị sửa/xóa trái phép sau khi lưu không?
- **Completeness:** tất cả target/accounts/roles/sessions bắt buộc đã có outcome chưa?
- **Timeliness:** chứng cứ được thu khi nào, có nằm trong deadline/snapshot freshness không?
- **Scope correctness:** đúng identity/relationship/tenant/client/resource không?
- **Semantic correctness:** `ACKNOWLEDGED` có bị trình bày thành `VERIFIED` không?
- **Independence:** kết quả có được xác nhận độc lập với executor khi risk yêu cầu?
- **Reproducibility:** có thể đọc lại trạng thái hoặc kiểm lại an toàn không?
- **Privacy/confidentiality:** bằng chứng có lộ PII/secrets không?
- **Retention/accessibility:** chứng cứ được giữ và truy xuất đúng quyền trong kỳ kiểm toán không?

### 8.2. Gợi ý các mức assurance nội bộ

| Mức | Chứng cứ hiện có | Kết luận có thể nêu |
| --- | --- | --- |
| **E0 – REQUEST_ONLY** | Quyết định và command | Đã yêu cầu, chưa biết target |
| **E1 – TARGET_ACK** | API response/connector acknowledgment | Đích đã phản hồi theo contract |
| **E2 – OBSERVED_REMOVAL** | Readback account/role/credential | Trạng thái đích đã thay đổi trong snapshot |
| **E3 – EFFECTIVE_DENIAL_TESTED** | Controlled PEP/target verification | Quyền bị DENY trong phạm vi thử |
| **E4 – MULTI_SOURCE_RECONCILED** | Independent review + target coverage + exceptions | Phạm vi kiểm soát được đối soát với mức bảo đảm cao hơn |

Các ký hiệu **E0–E4 là phân loại minh họa của bài**, không phải chuẩn công nghiệp hay “chứng minh tuyệt đối”. E3 có thể không phù hợp nếu phép thử gây rủi ro; E2 + native logs và policy coverage có thể là bằng chứng chấp nhận được trong một trường hợp cụ thể.

### 8.3. Bằng chứng mạnh nhưng sai scope vẫn không đủ

Một API probe `invoice.read` bị DENY không chứng minh `invoice.approve`, database admin hay session ở tenant khác đã hết hiệu lực. **Phạm vi kiểm chứng** phải khớp **phạm vi thu hồi được tuyên bố**.

## 9. Nguồn chân lý và ma trận chứng cứ theo hệ thống

Không có một nguồn dữ liệu duy nhất luôn mô tả đầy đủ mọi quyền.

| Nguồn | Giỏi chứng minh | Giới hạn |
| --- | --- | --- |
| **HRIS** | Quan hệ việc làm, effective JML | Không quan sát target session |
| **Identity registry** | Stable identity mapping, relationship state | Có thể chậm nếu nguồn không đồng bộ |
| **IGA/approval** | Desired access, quyết định và policy | Không tự chứng minh target applied |
| **IdP/Directory** | Account/credential/group state và phiên do nó quản lý | SaaS local session/API key độc lập |
| **SCIM connector** | Request/response provisioning theo capability | Không mặc định có session termination |
| **SaaS native admin API** | Target account/role state | PEP cache, active sessions có thể khác |
| **API gateway/resource PEP** | Authorization decision tại request | Chưa bao phủ đường bypass khác |
| **PAM/VPN/OS/DB** | Active privileged sessions và termination | Không chắc xóa được keys mới tạo |
| **Cloud IAM** | Principals, roles, trust policies | Token đã phát còn có thể được dùng |
| **Vault/PKI** | Credential issuance/rotation/revocation | Không biết mọi credential copy đã dùng |
| **Audit/SIEM** | Event sequence, anomalies, correlation | Thiếu log không chứng minh không có hoạt động |
| **Reconciliation** | Desired vs observed/effective drift | Phụ thuộc coverage và freshness của sources |

### 9.1. Phải chỉ rõ thẩm quyền từng trường

`employmentStatus` có thể lấy từ HRIS; `targetRoleAssignments` từ SaaS native API; `privilegedSessionActive` từ PAM/host; `effectivePermission` từ PEP. **Không để dashboard SIEM tự trở thành nguồn chân lý duy nhất** cho mọi trạng thái.

### 9.2. Giám sát thiếu dữ liệu là một phần kiểm toán

Khi một target API trả 503 hoặc log pipeline bị đứt, trạng thái là **UNKNOWN**, không phải “không thấy hoạt động = không còn quyền”. Event capture health và ingestion completeness phải được theo dõi riêng.

## 10. Quyết định và phê duyệt thu hồi: chứng cứ thẩm quyền

Việc thu hồi có thể được kích hoạt bởi:

- HRIS Leaver/contract end có hiệu lực.
- Mover làm thay đổi role eligibility.
- Access recertification với quyết định REVOKE.
- Resource owner rút một entitlement.
- Security incident nghi credential/session compromise.
- PAM JIT expiry hoặc break-glass cleanup.
- Workload/robot retirement.
- Vi phạm SoD, policy, tenant hoặc risk score.

### 10.1. Cần lưu gì?

- **Trigger reference** từ source có thẩm quyền.
- **Subject/relationship** được tác động.
- **Resource/role/session scope** và căn cứ từng quyền.
- **Decision maker** hoặc automation policy, được phép quyết định scope đó.
- **Policy version, SoD/risk finding, effectiveAt**.
- **Approval/cancellation/escalation** khi policy yêu cầu.
- **Correlation ID** để nối các command và target outcomes.

### 10.2. Không mọi thu hồi đều cần manager duyệt

Khi HRIS báo Leaver có thẩm quyền, hệ có thể **tự động khóa truy cập** theo policy; không nên đợi một người bấm approval khiến quyền rủi ro cao tồn dư. Các quyết định đặc biệt như **tạm hoãn thu hồi hoặc giữ ngoại lệ** có thể cần approval/SoD riêng.

### 10.3. Quyết định KEEP/REVOKE khác applied

Trong kỳ access recertification, reviewer chọn REVOKE là **chứng cứ quyết định**, không chứng minh role đã gỡ. Cần evidence từ target và reconciliation trước khi đóng remediation.

### 10.4. Mọi ngoại lệ phải hữu hạn

Nếu phải giữ quyền một thời gian chuyển giao sau Mover, exception nên có **owner, justification, role/scope, expiry, compensating controls và review date**; không chỉ ghi comment “business need” vô thời hạn.

## 11. SCIM và tài khoản SaaS: ba lớp kiểm chứng

SCIM có thể provision/deprovision users/groups qua API nếu target hỗ trợ. **SCIM không phải công cụ terminate mọi session hoặc revoke mọi token của mọi SaaS.**

### 11.1. Ví dụ deactivation

~~~text
Step A – Command:
  SCIM PATCH /Users/{targetId}: active=false

Step B – Response:
  Target trả success theo contract

Step C – Management readback:
  GET /Users/{targetId} trả active=false

Step D – Authorization verification:
  Local session/token cũ bị chặn?
  Target roles còn không?
  API keys còn dùng được không?
~~~

Nếu chỉ có A và B, mức chứng cứ chủ yếu là **lệnh/ack**. Nếu C đạt, có thể chứng minh **trạng thái quản lý target**. Để tuyên bố “không còn effective access”, cần kiểm D hoặc công bố rõ giới hạn của cơ chế nền tảng.

### 11.2. Giới hạn của SCIM response

- API có thể trả success cho thay đổi **bất đồng bộ**.
- `active=false` không nhất thiết gỡ mọi group role ngay.
- SaaS có native local accounts ngoài provisioning connector.
- Các OAuth clients, user-generated API keys hoặc mobile sessions có vòng đời riêng.
- SCIM không tự quản lý mọi **workload/service principals** hoặc X.509 certificates.
- Target không có API hỗ trợ có thể phải dựa vào chứng cứ vận hành khác, được chấp nhận theo risk.

### 11.3. Evidence tối thiểu

| Mốc | Evidence | Đánh giá |
| --- | --- | --- |
| Command | Operation ID, target ID, authorized scope | Requested |
| API result | HTTP status + sanitized response code | Acknowledged |
| Target state | Account active/group list ở timestamp đáng tin | Observed |
| Effective check | Safe API/PEP deny, token status hoặc policy evidence | Verified theo scope |
| Exception | Session/token chưa xử lý được, owner/SLA | Partial/Unknown |

Không log access token dùng gọi SCIM hoặc bản ghi user chứa PII không cần thiết.

## 12. IdP/SSO và chứng cứ chặn đăng nhập

Một IdP có thể disable một identity, revoke SSO sessions hoặc credential, nhưng một Relying Party/SaaS vẫn có **local session** riêng.

### 12.1. Phân biệt ba đích cần chứng minh

1. **New sign-in blocked:** người dùng không thể tạo authentication mới tại IdP theo policy.
2. **Existing OP session revoked:** session IdP cũ không còn hợp lệ.
3. **Relying party/local session terminated:** ứng dụng đã xóa/không chấp nhận session cũ.

Các mục này không tự suy ra nhau.

### 12.2. OIDC logout

- **RP-Initiated Logout:** RP yêu cầu OP kết thúc phiên nếu hỗ trợ.
- **Front-channel Logout:** phụ thuộc browser/redirect/iframe/cookie behavior.
- **Back-channel Logout:** OP gửi logout notification tới RP; RP phải xác minh và invalidate local session.
- **OAuth grant revocation:** cần xử lý riêng access/refresh tokens theo issuer/target.

**Logout event được gửi không có nghĩa mọi RP đã xử lý**. Bằng chứng cần có mapping issuer/subject/session, RP outcome và session status.

### 12.3. SAML SLO

SAML Service Provider có thể hỗ trợ Single Logout theo binding/profile cụ thể. Nếu SP offline hoặc không hỗ trợ, **IdP logout không chứng minh SP session đã đóng**. Capability matrix của từng ứng dụng phải nêu rõ.

### 12.4. Không chỉ kiểm “login mới bị từ chối”

Một browser cũ có session cookie còn hiệu lực có thể tiếp tục đọc dữ liệu mà không cần gọi IdP. Verification cần quan tâm **existing session path**, không chỉ tạo login mới.

## 13. OAuth access/refresh token và revocation evidence

**OAuth 2.0 Token Revocation (RFC 7009)** hỗ trợ yêu cầu revoke token. **Token Introspection (RFC 7662)** có thể kiểm token active status/metadata khi nền tảng hỗ trợ.

### 13.1. Refresh token và access token khác nhau

- Thu hồi **refresh token/grant** thường nhằm chặn khả năng xin access token mới.
- **Access token JWT đã phát** có thể còn hợp lệ tới `exp` nếu resource server xác minh offline mà không kiểm revocation state.
- **Opaque token** có thể được kiểm active qua introspection, nhưng cache tại PEP tạo cửa sổ trễ.
- **Client credential rotation** không tự làm mọi access token đã phát bị từ chối.

### 13.2. Chuỗi chứng cứ ví dụ

~~~text
18:00  Security revokes refresh-token family R.
18:00  Issuer confirms grant disabled.
18:01  New refresh attempt with R denied.
18:02  Old access JWT A (exp 18:15) still PERMIT at API.
18:03  PEP revocation epoch updated.
18:04  Same JWT A denied for resource action in tested scope.

Conclusions:
  - Refresh grant revocation: verified at issuer.
  - Access token effective denial: verified at API from 18:04
    for the tested action/environment.
  - Exposure window 18:00–18:04 requires review if relevant.
~~~

### 13.3. Không gọi token revocation HTTP 200 là “đã hết mọi token”

RFC 7009 có ngữ nghĩa tránh lộ token tồn tại hay không; response success **không phải bằng chứng issuer vừa tìm thấy đúng token hoặc mọi resource server đã làm token vô hiệu**. Phải xác nhận grant/token coverage và phương thức thực thi.

### 13.4. JWT revocation-aware PEP

Các cơ chế giảm residual window gồm:

- `jti` denylist với TTL và trusted event propagation.
- Session/grant revocation epoch hoặc entitlement version.
- Resource-side current lifecycle/security-state checks.
- Short-lived access tokens có thời hạn chấp nhận được.
- Sender-constrained tokens trong profile hỗ trợ để giảm replay ở nơi khác.
- Token introspection/central authorization cho action rủi ro cao.

Phải đo **cửa sổ thực tế**, bao gồm cache/replication, thay vì chỉ ghi “revoke JWT = success”.

## 14. Cookie, browser session và chứng cứ session termination

Với application session backed bởi Redis/DB, một lệnh `invalidate(sessionId)` có thể chấm dứt local state. Tuy nhiên:

- Xóa cookie phía client không chặn bản sao cookie bị đánh cắp nếu server chưa revoke.
- Xóa session trên một node không đủ nếu replica khác vẫn cache.
- Một tab/browser khác hoặc thiết bị khác có session ID riêng.
- API token có thể độc lập với browser session.
- Request/stream đã bắt đầu trước revoke có thể tiếp tục tùy thực thi.

### 14.1. Chuỗi kiểm

~~~text
Revocation requested for sessionRef S
  -> Application session store marks S invalid
  -> Replicas/cache receive invalidation
  -> Authorized safe probe using S is DENIED
  -> No new session created while identity security-blocked
  -> Outcome recorded with tested scope and timestamp
~~~

### 14.2. Không log raw session ID

Session ID/cookie thường là **bearer credential**. Evidence package có thể giữ **non-authenticating reference hoặc fingerprint an toàn**, và lưu raw credential thử nghiệm trong môi trường kiểm soát nếu thực sự cần; tuyệt đối không đưa vào log phổ thông.

### 14.3. Chứng cứ của logout một phiên vs all devices

Một ứng dụng có thể chỉ thu hồi **current session**. Để tuyên bố “all sessions”, cần có **inventory** các sessions/grants thuộc scope và kết quả từng client/device/target, hoặc capability bảo đảm rõ ràng từ issuer với verification phù hợp.

## 15. RBAC, ABAC, PBAC và quyền hiện hành

Một quyền có thể được cấp qua **direct assignment, group membership, nested group, dynamic policy, resource ACL, cloud role hoặc delegated grant**.

### 15.1. Tránh kết luận từ một bảng role

Ví dụ:

~~~text
Desired:
  person-1042 không còn FinanceApprover.

Observed direct grants:
  FinanceApprover removed.

Observed group-derived grants:
  Group FinanceManagers vẫn chứa person-1042.

Effective:
  PEP vẫn PERMIT invoice.approve qua group.
~~~

Một readback chỉ kiểm direct grants **không chứng minh quyền đã bị thu hồi** nếu còn đường group-derived.

### 15.2. Phương pháp xác minh

- Đọc target **effective entitlements** nếu API hỗ trợ.
- Phân tích **group/role expansion**, inherited permissions và explicit deny.
- Kiểm **ABAC attributes** (department, tenant, employment status, classification, device, time).
- Kiểm policy version đã được PEP nạp hay cache còn cũ.
- Xác minh action/resource cụ thể bằng policy evaluation/PEP audit hoặc probe an toàn.
- Kiểm delegated/impersonation/access proxy paths.

### 15.3. PDP DENY không có nghĩa PEP đã chặn

PDP có thể trả DENY nhưng ứng dụng bỏ qua kết quả hoặc có route bypass. **Evidence cần phân biệt policy decision với enforcement outcome**; kiểm target action không thực hiện, không chỉ kiểm một log từ PDP.

### 15.4. SoD và quyền tồn dư sau Mover

Người chuyển từ Sales sang Finance có thể được cấp Finance role trước khi SalesAdmin bị gỡ, dẫn đến xung đột SoD. Evidence của Mover phải bao gồm **quyền cũ đã mất đúng lúc, quyền mới được phê duyệt đúng thẩm quyền và không có overlap trái policy**.

## 16. PAM/JIT và chứng cứ thu hồi đặc quyền

Đối với privileged access, một event “JIT elevation expired” hoặc “PAM checkout closed” chưa chắc chứng minh **active session và quyền phát sinh** đã được gỡ.

### 16.1. Các lớp cần kiểm

| Đối tượng | Chứng cứ cần | Đường truy cập còn lại có thể là |
| --- | --- | --- |
| **PAM activation** | Elevation/grant state, expiry, revoke outcome | Active shell vẫn chạy |
| **SSH/RDP** | Session terminate/logoff, host session inventory | Background process, port forwarding |
| **Database admin** | DB role revoke và active connections | Connection pool/transaction đang mở |
| **Cloud admin** | Role assignment/temporary credentials | Access token/API keys đã phát |
| **Emergency/break-glass** | Incident authorization, usage, cleanup | Credential/factor và exception vẫn tồn tại |
| **Network tunnel** | VPN/firewall/ACL state | Đường network mở tạm chưa đóng |
| **Created credentials** | Key/cert/client inventory diff | Backdoor/service principal mới |

### 16.2. Không tự coi session closed là mọi thay đổi đã hoàn tác

Một người đã tạo cloud access key mới trong phiên PAM. Khi phiên bị terminate, **key mới có thể còn giá trị**. Phải rà `role.grant`, credential creation, trust changes, scheduled tasks và network exceptions, không chỉ video/session-end event.

### 16.3. JIT expiry không hoàn tác tác vụ đã commit

Thu hồi quyền không tự rollback một database transaction đã hoàn tất. Cần **business compensation, change review và forensic evidence** riêng cho các action đã xảy ra trước khi quyền hết.

### 16.4. Break-glass cần hậu kiểm độc lập

Emergency account có thể không phụ thuộc IdP/PAM khi hệ chính bị outage, nhưng phải có **custody logs/native audit, incident reference, session/credential resecure, kiểm tạm quyền và independent post-use review**. Khi SIEM không khả dụng, evidence được đồng bộ sau phục hồi và ghi `PARTIAL` nếu thiếu.

## 17. Service account, robot và workload: chứng cứ thu hồi non-human identity

**Non-human identities** có thể là OAuth clients, cloud managed identities, Kubernetes ServiceAccounts, SPIFFE/SPIRE workloads, bots/RPA, CI/CD pipelines hoặc service accounts trong database. Chúng có vòng đời riêng với nhân sự.

| Loại | Đối tượng cần gỡ | Bằng chứng |
| --- | --- | --- |
| **OAuth client** | Client secret/private key, registration, grants | Issuer state, failed token issuance, API enforcement |
| **Cloud workload identity** | Principal, role, federated trust binding | Cloud IAM readback, API decision |
| **Kubernetes ServiceAccount** | ServiceAccount/RBAC, external identity trust | K8s API readback và cloud role/grant readback |
| **SPIFFE/SPIRE** | Registration/trust, SVID issuance | Registry/CA state và peer-auth checks |
| **Robot/RPA** | ERP account, vault permission, active jobs | Orchestrator job state, target account/roles, sessions |
| **DB service account** | DB role/login/credential, active connections | DB role/session inventory |
| **CI/CD principal** | Repository/environment trust, cloud roles | CI identity + external IAM readback |
| **Legacy API key** | Key ở nhiều target | Target inventory và valid/denied-use evidence |

### 17.1. Owner Leaver khác service retirement

Technical owner nghỉ việc trong khi `billing-sync-prod` vẫn phục vụ nghiệp vụ. Hồ sơ chứng cứ cần tách:

- **Human Leaver:** người cũ không còn quyền với vault, CI/CD, cloud trust, OAuth client registrations.
- **Ownership transfer:** người/đội mới chịu trách nhiệm vận hành và credential rotation.
- **Credential custody:** secrets người cũ từng có khả năng xem/mint được đánh giá và xử lý theo risk.
- **Workload legitimacy:** principal vẫn có mục đích, target và entitlements hợp lệ.
- **Future retirement:** có kế hoạch revoke principal/trust/role/credential khi service thật sự hết nhu cầu.

Không xóa service production chỉ vì owner nghỉ, nhưng cũng không giữ một **orphaned privileged principal** không có owner.

### 17.2. Token cũ và client đã disabled

Khi OAuth client bị disable, access JWT được phát trước đó có thể vẫn được API chấp nhận đến `exp` nếu không có current-state check. `client.disabled` chỉ chứng minh trạng thái đăng ký/cấp token mới tại issuer trong scope đã kiểm; muốn kết luận API không còn nhận token, cần **resource enforcement evidence**.

### 17.3. Robot stop job không phải revoke account

Robot dừng lịch trên orchestrator nhưng password ERP vẫn hợp lệ. Chứng cứ retirement phải bao gồm **job disabled, secrets/grants revoked, session termination, target user inactive, role readback và xử lý alternate access**.

## 18. Joiner: chứng cứ khi hủy danh tính và quyền cấp sớm

**Joiner** thông thường liên quan cấp quyền, nhưng có trường hợp phải thu hồi ngay: ứng viên hủy nhận việc, preboarding bị ngừng, provisioning sai account hoặc approval bị rút.

### 18.1. Tình huống

~~~text
01/12 08:00: dự kiến nhân viên bắt đầu.
25/11 14:00: HRIS tạo PENDING_START.
26/11 09:00: IGA tạo account preboarding.
27/11 10:00: HRIS phát StartCancelled.
27/11 10:05: IdP disable preboarding account.
27/11 10:06: SaaS preboarding vẫn có group mặc định.
~~~

### 18.2. Hồ sơ cần có

1. **StartCancelled event** từ HRIS với relationship ID và timestamp.
2. Inventory **preboarding accounts, groups, sessions, temporary credentials** đã cấp.
3. Commands và target outcomes của IdP/SCIM/ứng dụng.
4. Readback account/role và xác minh session/grant phù hợp.
5. Kiểm **pending jobs** không tái tạo account hoặc quyền sau cancel.
6. Exception có owner cho target chưa xác minh, đồng thời giữ audit đúng retention.

### 18.3. “Không cấp quyền sớm” là khẳng định theo khoảng thời gian

Không thấy role production trong một snapshot **không chứng minh role đó chưa từng tồn tại**. Cần lịch sử entitlement, kiểm policy gate, event timeline và logs đủ coverage để nêu kết luận hợp lý.

### 18.4. Rehire không tái mở token cũ

Khi một người quay lại, identityId có thể giữ ổn định nhưng **relationship mới**. Chứng cứ cũ phải giữ nguyên, quyền mới cần căn cứ/approval mới; không phục hồi toàn bộ sessions hoặc roles thời trước do trùng username.

## 19. Mover: chứng cứ gỡ quyền cũ và tránh privilege creep

**Mover** có thể chuyển department, manager, project, tenant hoặc responsibility. Có quyền cần thu hồi, có quyền cần giữ, quyền mới có thể phải phê duyệt.

### 19.1. Ví dụ Sales → Finance

~~~text
Before:
  SalesAdmin = granted via role Sales
  CorporateMail = baseline entitlement
  FinanceReader = absent

After Mover effective:
  SalesAdmin must be removed
  CorporateMail remains
  FinanceReader only after resource approval
~~~

### 19.2. Chuỗi chứng cứ

- HRIS/IGA Mover event với **relationship/source version/effectiveAt**.
- Desired entitlement diff **trước/sau**, role source và SoD results.
- Quyết định thu hồi `SalesAdmin`, giữ quyền chung và yêu cầu phê duyệt mới.
- Target role/group readback, bao gồm **inherited/group-derived permissions**.
- JWT/session hoặc delegated grants cũ có còn quyền Sales không.
- Kết quả cấp quyền FinanceReader (nếu hợp lệ) và xác minh target.
- Bằng chứng không có **xung đột SoD do tạm giữ cả quyền cũ và mới**.
- Reconciliation và xử lý residuals nếu cần.

### 19.3. Không coi mọi quyền còn lại là drift

Một entitlement có thể được cấp qua **role phòng ban và project approval** cùng lúc. Khi Mover gỡ nguồn role phòng ban, nếu project approval còn hợp lệ, role có thể vẫn được giữ. Phải kiểm **grant provenance**, không chỉ “role vẫn có” rồi tự động gỡ.

### 19.4. Stale JWT role claim

IdP đã gỡ group Sales nhưng JWT phát trước Mover vẫn chứa claim cũ. Chứng cứ cần đo **PEP behavior/cache window**; group removal timestamp không tự chứng minh các API đã DENY.

### 19.5. Mover cross-tenant

Cần chứng cứ theo tenant và relationship. Một email có ở tenant-a và tenant-b không chứng minh thu hồi ở A đã xử lý quyền ở B.

## 20. Leaver: hồ sơ kết thúc truy cập toàn diện

Leaver là bài toán multi-target với thời điểm hiệu lực và SLA rõ.

~~~mermaid
sequenceDiagram
    autonumber
    participant HR as HRIS
    participant IAM as IGA / Revocation coordinator
    participant IDP as IdP
    participant SaaS as SaaS / SCIM
    participant PAM as PAM / VPN
    participant REC as Evidence / Reconciliation
    HR->>IAM: RelationshipEnded with effectiveAt
    IAM->>IAM: Validate authority and identity version
    IAM->>REC: Store decision and required no-access scope
    par IdP
        IAM->>IDP: Disable login and revoke sessions/grants
        IDP-->>REC: Ack + readback
    and SaaS
        IAM->>SaaS: Deactivate / remove entitlements
        SaaS-->>REC: Ack + readback
    and Privileged
        IAM->>PAM: Revoke JIT and terminate sessions
        PAM-->>REC: Target outcomes
    end
    REC->>REC: Compare desired, observed and effective state
    REC-->>IAM: VERIFIED / PARTIAL / UNKNOWN
~~~

### 20.1. Đường thực thi cần kiểm

- Chặn **new sign-in** tại IdP và target.
- Chặn **new sessions/grants** sau effectiveAt.
- Revoke roles/entitlements tại SaaS, directory, cloud và local systems.
- Terminate privileged PAM/VPN/SSH/DB sessions theo capability.
- Chặn access tokens hoặc giới hạn residual token window ở PEP.
- Rà delegated access, devices và robot/service credentials từng liên quan.
- Đối soát các target accounts và exception.

Các lệnh độc lập có thể chạy song song an toàn, nhưng **evidence chain vẫn phải lưu từng outcome riêng**.

### 20.2. Khi event đến trễ

Nếu HRIS Leaver có hiệu lực 18:00 nhưng IAM nhận 18:12:

- Lưu `effectiveAt` và `ingestedAt` không bị ghi đè.
- Rà **PEP PERMIT, token issuance, session creation, role changes** trong khoảng trễ.
- Ghi thời điểm đầu tiên phát hiện denial ở các hệ nhạy cảm.
- Mở exception/incident nếu access sau effective time không phù hợp.
- Không tính latency bằng 0 từ thời điểm IAM biết sự kiện.

### 20.3. Partial không được tô xanh

~~~text
HRIS relationship: ENDED
IdP account: DISABLED
Refresh grants: REVOKED
Finance SaaS account: DISABLED
Finance SaaS existing session: UNKNOWN
PAM session: TERMINATED
Cloud API key: RESIDUAL

Overall: PARTIAL / HIGH-RISK EXCEPTION
~~~

Nếu SaaS không có API terminate session, phải ghi **NOT_SUPPORTED**, compensating controls, owner, expiry và giới hạn kết luận. Không viết `ALL_ACCESS_REVOKED`.

## 21. Access recertification: từ reviewer quyết định đến target verification

Một chiến dịch recertification tạo các quyết định **KEEP, REVOKE, ESCALATE** cho những entitlements đã cấp.

~~~text
ReviewItemAssigned
  -> Reviewer decision REVOKE
  -> Decision stored with approval, scope and policy
  -> Remediation command issued
  -> Target role removed
  -> Target observed entitlement absent
  -> Effective access check when warranted
  -> Review item closed or exception documented
~~~

### 21.1. Chứng cứ thẩm quyền reviewer

Nếu reviewer đã Mover/Leaver, cần lưu **assignment/reassignment/delegation**, vai trò reviewer lúc ra quyết định, policy version và authority. Không gán quyết định thực tế cho người duyệt trước đó.

### 21.2. Decision KEEP không thay các security policies

Reviewer KEEP một entitlement không tự hợp thức hóa SoD conflict hoặc quyền khác ngoài item. Vẫn cần policy evaluation và resource owner authorization.

### 21.3. Chứng cứ backlog

Nếu quyết định REVOKE đã có nhưng SCIM chưa gỡ được role nhiều ngày, đó là **remediation backlog**. Evidence cần owner, SLA, target status, retry và risk, không chỉ ticket “Done”.

## 22. Các phương pháp xác minh quyền bị thu hồi

Không phải hệ nào cũng cho phép một **active probe** dùng credential/session cũ. Chọn phương pháp dựa trên rủi ro và sự cho phép.

### 22.1. Target readback

Đọc **account, group, role, key, session và trust bindings** qua API native đã được phê duyệt.

**Ưu điểm:** quan sát trạng thái thật mà không thực hiện giao dịch nhạy cảm.

**Giới hạn:** inherited role, local session, access token đã phát và PEP cache có thể không được API quản trị phản ánh.

### 22.2. Policy simulation / what-if

Dùng công cụ chính thức để hỏi principal/action/resource có được PERMIT theo policy đang áp không. Không gây tác động nghiệp vụ nhưng **có thể khác runtime enforcement** nếu gateway/PEP/ứng dụng có logic bổ sung hoặc cache.

### 22.3. Safe authorization probe

Một **controlled probe** dùng test fixture/session được cấp hợp lệ và endpoint read-only/không phá dữ liệu để kiểm kết quả.

- Chỉ thử với **thẩm quyền và dữ liệu an toàn**, không dùng stolen token hoặc credential người đã nghỉ một cách tùy tiện.
- Chọn resource/action phản ánh quyền được thu hồi và known-good test conditions.
- Ghi audience, client, tenant, timestamp, expected denial reason, policy/PEP reference.
- Phân biệt **401 vì invalid token, 403 do policy, 404 masking, resource không tồn tại và network timeout**.
- Không thực hiện destructive action thật chỉ để chứng minh quyền đã hết.
- Nếu không thể active probe, ghi **assurance limitation** và dựa vào readback/native audit theo policy được chấp nhận.

### 22.4. Native enforcement logs

PEP/audit logs chứng minh **request cụ thể** được xử lý thế nào. Không có request PERMIT sau revoke không tự chứng minh **không thể PERMIT**.

### 22.5. Session inventory

Đối với PAM/VPN/SSH/RDP/DB, kiểm **active connections, process, session termination results**, nhưng credential đã phát cho phiên khác vẫn cần rà riêng.

### 22.6. So sánh phương pháp

| Phương pháp | Khẳng định có thể hỗ trợ | Giới hạn |
| --- | --- | --- |
| Target readback | Account/role/key đã đổi theo snapshot | Active token/session chưa chắc |
| Issuer grant status | Không thể lấy token mới qua grant đã revoke | JWT cũ vẫn có thể PERMIT |
| PDP evaluation | Policy cho DENY ở scope kiểm | PEP thực thi có thể khác |
| Safe PEP probe | Đường thử bị DENY | Không bao phủ mọi path |
| Native audit | Action thực đã bị chặn hoặc session kết thúc | Không chứng minh mọi thời điểm |
| Independent reconciliation | Desired/observed/effective match theo nguồn | Phụ thuộc freshness và scope |
| Hash/integrity manifest | Artifact đã lưu không bị đổi theo cơ chế kiểm | Không chứng minh capture completeness |

## 23. Bao phủ phạm vi và giới hạn của negative proof

Một hồ sơ `VERIFIED_DENIED` cần nêu **principal, target, tenant, client/session/token, action/resource, path, thời gian, phương pháp, verifier và coverage**.

### 23.1. Một DENY không đủ cho mọi quyền

API `invoice.read` trả 403 không chứng minh `payment.approve`, database admin, cloud console, tenant-b hay một session/refresh family khác đã hết quyền.

### 23.2. 404 không nhất thiết là DENY

Nhiều API trả 404 để **che resource tồn tại**. Nếu test dùng một tài nguyên không có thực, 404 có thể xảy ra ngay cả khi token còn quyền. Cần target PEP reason hoặc synthetic fixture được biết tồn tại.

### 23.3. Bằng chứng cấp quyền gián tiếp

Direct role đã gỡ nhưng inherited/group-derived grant còn. Readback nên bao phủ **effective permissions**, hoặc tính quyền từ group closure, ABAC attributes, policy version và ACL.

### 23.4. Không biến phép thử thành sự cố

Test quyền xóa dữ liệu, chuyển tiền hoặc thay policy trên production cần **simulator, dry-run, synthetic environment hoặc evidence native** có thẩm quyền, không thử lệnh nguy hiểm thực sự.

### 23.5. Quyền bị từ chối trong một snapshot không phải cam kết vĩnh viễn

Một admin có thể cấp lại role sau khi hồ sơ đóng. Evidence vẫn đúng **trong thời gian/điều kiện đã kiểm**, nhưng cần monitoring và recertification để phát hiện regrant.

## 24. Partial failure, eventual consistency và race condition

IAM thường vận hành qua nhiều broker, IdP, SaaS, gateway, region và cache. **Một lệnh được nhận tại control plane không tự có hiệu lực ngay ở data plane**.

### 24.1. Các dạng lỗi và chứng cứ tương ứng

| Failure mode | Triệu chứng | Xử lý/chứng cứ |
| --- | --- | --- |
| **SCIM timeout** | Không biết target đã xử lý chưa | UNKNOWN, retry idempotent + readback |
| **Event delayed** | Leaver đến sau effectiveAt | Lưu lateness, review exposure window |
| **Duplicate command** | Yêu cầu revoke gửi nhiều lần | Stable event/command ID và outcome correlation |
| **Out-of-order event** | Mover đến sau Leaver | Monotonic relationship/source version |
| **Stale JWT** | PEP còn PERMIT | Denylist/epoch/TTL, ghi cửa sổ tồn dư |
| **Cross-region lag** | Region A deny, B còn permit | Kiểm coverage theo region, cache invalidation |
| **Session recreation** | Async login tạo phiên mới sau revoke | Chặn new issuance bằng lifecycle guard |
| **Unsupported API** | SaaS không terminate session | NOT_SUPPORTED + compensating controls |
| **Audit outage** | Không có native/SIEM logs trong một khoảng | Evidence gap, source recovery |
| **Wrong identity link** | Revoke nhầm hoặc bỏ sót target account | Mapping conflict và remediation |
| **Manual regrant** | Admin cấp lại role sau khi gỡ | Alert, review authority |
| **Alternate key** | Password rotate nhưng API key khác còn | Credential inventory và target verification |

### 24.2. Race tạo session mới

~~~text
18:00  Leaver revocation begins
18:01  Coordinator lists sessions S1, S2
18:02  Pending login task creates session S3
18:03  Coordinator deletes S1 and S2
18:04  S3 still permits access
~~~

Chứng cứ “đã xóa mọi session trong snapshot 18:01” **không chứng minh** không còn phiên lúc 18:04. Cần **block new login/token issuance** dựa trên current lifecycle/security epoch và kiểm new sessions sau thời điểm revoke.

### 24.3. Không đoán thời điểm thực tế từ hai timestamp

Nếu `APPLIED at 18:00:05` và probe lúc 18:00:09 DENY, có thể chứng minh **đã quan sát DENY lúc 18:00:09**. Không nhất thiết biết chính xác giây PEP bắt đầu chặn nếu không có audit ở mức đó.

### 24.4. Retry không được hồi sinh quyền

Một Joiner event cũ có thể đến trễ sau Leaver. Mọi **grant** cần current-state, version và policy guard, không chỉ dedup ID. Khi phát hiện stale action, cần audit và chặn tái cấp.

## 25. Kiến trúc thu thập revocation evidence

~~~mermaid
flowchart LR
    HR["HRIS / Identity registry"] --> GOV["IGA / revocation policy"]
    SEC["Security / Access review"] --> GOV
    GOV --> OUT["Durable revocation outbox"]
    OUT --> DIS["Authorized connectors / service identities"]
    DIS --> IDP["IdP / directory / issuer"]
    DIS --> TGT["SCIM / SaaS / cloud / PAM"]
    IDP --> NAT["Native logs / readback"]
    TGT --> NAT
    NAT --> VER["Independent verifier"]
    GOV --> VER
    VER --> STATE["Desired vs observed vs effective"]
    STATE --> EVD["Protected evidence store + manifest"]
    STATE --> EX["Exception + SOC/remediation"]
    EX --> VER
~~~

### 25.1. Tách executor và verifier

- **Trigger source:** HRIS/security/resource owner được phép đưa ra sự kiện nghiệp vụ.
- **Coordinator:** xác định identity, scope, policy, effectiveAt và commands.
- **Connector executor:** chỉ được thao tác những target và role đã ủy quyền.
- **Evidence collector:** đọc native state/audit, không mặc định có quyền cấp lại access.
- **Verifier:** đánh giá coverage, consistency, effective outcome và các ngoại lệ.
- **Auditor:** xem evidence phù hợp với role, không được âm thầm sửa hồ sơ đã lưu.

Tách **executor** và **verifier** giúp giảm rủi ro “người tự báo đã xóa đúng quyền của mình”, đặc biệt với quyền đặc biệt cao.

### 25.2. SIEM không nên là nguồn duy nhất

SIEM có thể nhận log trễ hoặc mất một phần vì collector lỗi. Cần giữ **native source references, readback API evidence, collector health, offsets và gap alerts** theo rủi ro. Không dùng “không thấy PERMIT trong SIEM” như bằng chứng chắc chắn rằng không còn access.

### 25.3. Truy vết nhân quả

~~~text
HRIS event / access review decision
  -> revocationId
  -> connector command ID
  -> target operation ID
  -> target native audit or readback
  -> verifier result ID
  -> evidence manifest ID
  -> exception/closure ID
~~~

`correlationId` gom một workflow, còn `causationId` giúp tìm lệnh hoặc sự kiện gây ra bước tiếp theo. Hai trường không tự chứng minh quyền đã thay đổi nhưng giúp auditor **theo được nguồn**.

### 25.4. Outage của evidence store

Khi kho evidence không khả dụng, nên có **durable buffering** hoặc cơ chế ghi được bảo vệ nếu kiến trúc cho phép. Không xử lý lệnh thu hồi nhạy cảm rồi đánh dấu VERIFIED nếu hoàn toàn mất dấu kết quả. Khi phục hồi phải kiểm ingestion completeness và lưu gap.

## 26. Transactional outbox, idempotency và versioning

Một IGA service vừa cập nhật desired state vừa phải gửi command tới target. Nếu DB commit nhưng broker publish thất bại, workflow có thể mất yêu cầu thu hồi. **Transactional outbox** là mẫu đáng cân nhắc.

~~~text
Local DB transaction:
  desired entitlement -> REVOKE_PENDING
  outbox append command with stable commandId
Commit

Dispatcher:
  deliver with controlled retry

Target:
  apply role/account/session change or report error

Verifier:
  read back target; test effective access where appropriate
  persist evidence and exception state
~~~

### 26.1. Outbox giải quyết được điều gì?

Outbox giúp đồng bộ **state change và ý định phát message trong local transaction**. Nó **không** biến SCIM/SaaS/IdP APIs thành một transaction toàn cục và không bảo đảm side effect external exactly once.

### 26.2. Idempotency trong thu hồi

Một SCIM PATCH bị timeout có thể đã áp dụng. Retry an toàn cần **command ID, target ID, desired final state, scope và state readback**. Không tạo lại role để “đưa account về trạng thái trước khi revoke” chỉ vì response khó hiểu.

### 26.3. Version guard

~~~text
v41: ACTIVE, role Sales
v42: MOVER to Finance
v43: LEAVER effective

Delayed v42 grant:
  must not re-enable access after v43
~~~

Mọi command **cấp mới** cần kiểm current authoritative state. Commands revoke cũng phải kiểm tenant/relationship và hạn chế event cũ làm ảnh hưởng quan hệ mới được rehire.

### 26.4. Broker ACK không phải chứng cứ target đã xóa

Một outbox event được broker ACK chỉ chứng minh **delivery progress**, không phải `APPLIED` hoặc `VERIFIED_DENIED`. Muốn closure phải có kết quả nguồn target hoặc phương thức kiểm được phê duyệt.

## 27. Integrity, provenance và chain of custody

Evidence audit phải có khả năng **phát hiện sửa/xóa không hợp lệ** và truy được nguồn từ target.

### 27.1. Các lớp bảo vệ

- **Structured audit events:** source, schema, timestamp, correlation, result.
- **Authenticated transport:** TLS/mTLS, token/signature theo thiết kế.
- **Least privilege:** admin có quyền revoke không tự có quyền xóa log.
- **Tamper-evident/append-only storage:** version và integrity manifest.
- **Source capture:** lưu native source/event reference, bản chuẩn hóa và provenance.
- **Monitoring:** collector heartbeat, delivery gaps, outbox backlog, retention policy change.
- **Cryptographic safeguards:** checksum, digital signature hoặc hash chain theo risk.
- **Access audit:** ai đã xem/export/redact evidence.
- **Independent review:** đối chiếu IAM event với target trạng thái thực.

### 27.2. Hash không chứng minh completeness

Một hash có thể xác nhận artifact hiện tại khớp nội dung đã ghi tại một thời điểm. Nhưng nếu **một API action chưa từng được log**, hash chain vẫn có thể hợp lệ. Cần **sequence gap checks, native activity readback, heartbeat, monitoring và nguồn độc lập**.

### 27.3. Chain of custody

Khi evidence được đưa vào điều tra hoặc kiểm toán có yêu cầu nghiêm ngặt, lưu:

1. Nguồn sinh artifact.
2. Actor/system thu thập và quyền được cấp.
3. Thời gian và phạm vi capture.
4. Định dạng/schema gốc, mọi chuyển đổi hoặc redaction.
5. Integrity digest/signature và trust key reference.
6. Storage location, encryption, access controls và retention.
7. Lịch sử truy cập/chuyển giao cần thiết.
8. Reviewer, kết luận và evidence refs hỗ trợ.

Chỉ lưu **tham chiếu tới artifact có kiểm soát**, không đính kèm raw token hoặc tài liệu HR nhạy cảm vào mọi event.

### 27.4. Khi SIEM bị outage

Có thể lấy native IdP/SaaS/PAM logs sau khi hệ thống phục hồi và bổ sung incident journal được bảo vệ. Nhưng nếu mất một khoảng logging không thể phục hồi, phải ghi **EVIDENCE_GAP / PARTIAL** thay vì tự tạo lại sự kiện như thể đã quan sát trực tiếp.

### 27.5. Chữ ký hợp lệ không đảm bảo event đúng

Nếu credential của producer đã bị chiếm, attacker có thể phát event ký hợp lệ nhưng sai. Phải phối hợp authentication với **thẩm quyền, event-semantic validation, source status và reconciliation**.

## 28. Privacy, retention và giới hạn chia sẻ chứng cứ

Chứng cứ thu hồi có thể chứa **trạng thái việc làm, thông tin định danh, role nhạy cảm, device/network metadata, session refs và audit hành động**.

### 28.1. Data minimization

Chỉ giữ trường thực sự cần để chứng minh **decision, scope, target outcome và verification**. Không đưa vào log thông thường:

- Password, OTP, TOTP seed, passkey/private key.
- Raw OAuth access/refresh tokens, session cookies, reusable assertions.
- Giấy tờ định danh, biometric images hoặc HR case details không cần.
- Nội dung hóa đơn/dữ liệu khách hàng nếu resource reference đã đủ.
- Key material, secret values hoặc recovery code.

### 28.2. Role-based evidence access

| Người xem | Nên xem |
| --- | --- |
| **IAM operator** | Workflow status, sanitized target outcomes |
| **Security responder** | Evidence cần cho incident theo quyền |
| **Resource owner** | Quyền/tài nguyên trong tenant được giao |
| **Auditor** | Decision, outcome, integrity manifests, exceptions |
| **Privacy/legal** | Retention, redaction và legal hold khi phù hợp |
| **Developer thường** | Metrics/synthetic data, không mặc định PII |

### 28.3. Không coi pseudonym là anonymous

`person-1042` có thể được nối về con người trong identity registry. Token fingerprint có thể linkable. Chúng vẫn là dữ liệu cần bảo vệ theo mục đích và quyền truy cập.

### 28.4. Retention do chính sách quyết định

Không có một số ngày chung cho mọi quốc gia và mọi loại chứng cứ. Cần tuân theo **purpose, classification, policy, nghĩa vụ pháp lý nếu áp dụng, legal hold và deletion workflow**.

### 28.5. Redaction giữ provenance

Khi chia sẻ bản đã che PII, cần ghi đó là **redacted copy**, giữ bản gốc trong kho được phép nếu còn hạn và lưu ai đã redaction, lúc nào, mục đích nào khi quy trình yêu cầu.

## 29. Reconciliation: desired, observed và effective state

**Reconciliation** nối các command IAM với trạng thái tài khoản, quyền và phiên thực tế.

### 29.1. Ba lớp dữ liệu

~~~text
DESIRED:
  person-1042 không có SalesAdmin theo employment-A.
  No privileged sessions after effectiveAt.

OBSERVED:
  Direct SalesAdmin grant absent in CRM.
  Group-derived SalesAdmin still present.
  VPN session ACTIVE.
  Legacy client key still enabled.

EFFECTIVE:
  Sales API still PERMITS approval via inherited role.
  VPN still provides access.
  Client key can still mint token.
~~~

### 29.2. Mã drift

| Code | Nghĩa | Nguồn kiểm |
| --- | --- | --- |
| **EXTRA_ENTITLEMENT** | Role vượt desired | Target effective permissions |
| **STALE_SESSION** | Session còn sau revoke | Session store/PEP |
| **TOKEN_RESIDUAL** | JWT/opaque token vẫn PERMIT | API enforcement |
| **CREDENTIAL_RESIDUAL** | Key/secret còn hợp lệ | Issuer/vault/target inventory |
| **PRIVILEGED_RESIDUAL** | PAM/cloud admin còn | PAM, cloud grants, target |
| **ORPHAN_ACCOUNT** | Account không còn owner/relationship | Registry + target |
| **DELEGATION_RESIDUAL** | Token thay user cũ còn | Grant/actor readback |
| **NETWORK_PATH_RESIDUAL** | Tunnel, ACL hoặc VPN chưa đóng | Network/host audit |
| **TARGET_UNAVAILABLE** | Không lấy được observed state | Exception, retry |
| **EVIDENCE_GAP** | Thiếu source/assurance | Provenance and gap record |
| **VERSION_CONFLICT** | Snapshot lệch thời điểm | Source versions/timestamps |
| **WRONG_SCOPE** | Thu hồi nhầm tenant | Identity-link verification |

### 29.3. Reconciliation không được tự cấp role để “chữa drift”

Nếu một quyền đang thiếu tại target, phải kiểm **approval/authority/SoD/current lifecycle** trước khi grant lại. Không tự cấp wildcard admin để làm dashboard xanh.

### 29.4. `UNKNOWN` không phải `NO_ACCESS`

Một connector không đọc được role vì network lỗi **không chứng minh role vắng mặt**. Đặt `UNKNOWN` với owner, deadline và risk mitigation.

### 29.5. Regrant sau closure

Nếu admin cấp lại quyền sau khi hồ sơ đã VERIFIED, evidence quá khứ vẫn đúng **tại mốc và scope đã kiểm**, nhưng monitoring phải tạo event mới để phát hiện regrant trái phép.

## 30. Điều kiện đóng hồ sơ thu hồi

Một closure policy phải có **định nghĩa đo được**.

~~~text
IF
  authoritative trigger and scope verified
  AND required target outcomes recorded
  AND current identity / relationship state checked
  AND target roles/accounts/sessions/credentials removed
  AND effective-denial requirements satisfied in covered scope
  AND exceptions and limitations explicitly tracked
  AND audit integrity / retention requirements satisfied
THEN
  CLOSED_VERIFIED for covered scope
ELSE
  PARTIAL / UNKNOWN / EXCEPTION with accountable owner
~~~

### 30.1. Không yêu cầu probe nguy hiểm

Nếu target không cho phép active probe, hồ sơ có thể được đóng ở assurance phù hợp dựa trên **native readback + policy/PEP contract + target evidence**, nhưng phải **trình bày rõ không có trực tiếp effective-use test**.

### 30.2. Closure theo target

Một revocation có nhiều target outcomes, mỗi target có kết luận riêng. Tổng thể chỉ được VERIFIED khi đủ các target/phạm vi **bắt buộc**; không bỏ đích chưa xong khỏi mẫu số.

### 30.3. Chấp nhận ngoại lệ khác xác minh không còn quyền

`EXCEPTION_ACCEPTED` là một trạng thái có risk acceptance/compensating controls, không phải `VERIFIED_DENIED`. Ghi reviewer, scope, expiry, owner và kế hoạch xử lý.

### 30.4. Session và key có thể sống lâu hơn grant

Kiểm closure phải tính **access tokens đã phát, active sessions, alternate keys, delegated grants và role inheritance** theo threat model; không chỉ danh sách group hiện tại.

## 31. Java: mô hình chứng cứ bằng record bất biến

Một hệ IAM viết bằng Java có thể định nghĩa **RevocationEvidence** là dữ liệu có kiểu rõ, liên kết quyết định, target và outcome. Ví dụ dưới đây minh họa thiết kế, **không phải thư viện đầy đủ có thể build ngay**.

~~~java
// Mô hình giáo dục: package/imports omitted.
enum RevocationStage {
    DECIDED, REQUESTED, SENT, ACKNOWLEDGED,
    APPLIED, OBSERVED, VERIFIED_DENIED,
    PARTIAL, UNKNOWN, FAILED, NOT_SUPPORTED
}

record SubjectScope(
    String identityId,
    String relationshipId,
    String principalType,
    String tenantId,
    String targetSystemId,
    String targetAccountRef,
    String entitlementRef
) {}

record EvidenceReference(
    String evidenceId,
    String sourceSystem,
    String captureMethod,
    String digestReference,
    Instant capturedAt
) {}

record RevocationEvidence(
    String revocationId,
    String sourceEventRef,
    String reasonCode,
    SubjectScope scope,
    String authorizedInitiatorRef,
    String policyVersion,
    Instant effectiveAt,
    Instant recordedAt,
    RevocationStage stage,
    String verificationMethod,
    String verifiedByRef,
    List<EvidenceReference> evidenceRefs,
    String exceptionRef
) {}
~~~

### 31.1. DTO không tự kiểm thẩm quyền

Record có thể chứa actor tự khai hoặc `stage=VERIFIED_DENIED` không có evidence. Cần **authenticated source, schema/semantic validation, authority checks, state guards và audit**.

### 31.2. State transition phải có điều kiện

Ví dụ không cho chuyển:

- REQUESTED → VERIFIED_DENIED khi không có target result/verification hợp lệ.
- UNKNOWN → VERIFIED_DENIED chỉ vì retry đã được xếp hàng.
- FAILED → APPLIED chỉ vì support ticket “resolved” mà chưa đọc target.
- VERIFIED_DENIED cho **một target** thành VERIFIED cho **toàn bộ identity** không có coverage.

### 31.3. Không lưu secret ở evidenceRef

`digestReference` hoặc `evidenceId` không phải raw token, password hay private key. Các artifact thực phải nằm ở **secured evidence store** có ACL/retention riêng.

## 32. Java/Spring: coordinator ghi command và outbox

Một coordinator có thể lưu quyết định và command trong một transaction, sau đó giao công việc cho connectors.

~~~java
// PSEUDOCODE: các type/repository minh họa.
@Service
class RevocationCoordinator {

    private final IdentityRegistry identities;
    private final RevocationRepository revocations;
    private final CommandOutbox outbox;
    private final AuthorityPolicy authority;

    @Transactional
    public String requestRevocation(
            VerifiedLifecycleEvent event,
            AuthenticatedActor caller) {

        authority.requireCanRevoke(caller, event);

        IdentityRecord identity = identities.current(
            event.identityId(), event.relationshipId());

        if (!identity.matchesTenant(event.tenantId())) {
            throw new IllegalArgumentException("Wrong tenant");
        }

        if (event.sourceVersion() < identity.sourceVersion()) {
            throw new IllegalStateException("Stale lifecycle event");
        }

        RevocationJob job = revocations.createIdempotently(
            event.id(),
            identity.id(),
            event.scope(),
            event.effectiveAt()
        );

        for (TargetScope target : job.targetsToRevoke()) {
            outbox.appendRevokeCommand(
                job.id(), target.id(), job.sourceVersion());
        }

        return job.id();
    }
}
~~~

### 32.1. Đoạn minh họa cần hoàn thiện gì khi triển khai thật?

- Phân biệt **current state/relationship** và event effectiveAt tương lai.
- Chặn new grants/login theo policy khi Leaver/security block.
- Unique constraint tránh tạo hai jobs do event duplicate.
- Target command authorization, tenant-scoped connector identity.
- Source version check không bỏ qua hợp lệ một event đến trễ cần xử lý exposure.
- Transactional outbox, retries và poison-message handling.
- Không trả `COMPLETE` chỉ vì method `requestRevocation` hoàn thành.

### 32.2. Chưa có bằng chứng ở target

Sau khi transaction commit, coordinator chỉ có **REQUESTED / COMMAND_QUEUED**. Để đạt VERIFIED cần chạy collector và verifier độc lập.

## 33. Java: verifier đối chiếu target state và evidence

~~~java
// PSEUDOCODE: API, stores và result types do hệ thống định nghĩa.
@Service
class RevocationVerifier {

    private final TargetStateReader targetReader;
    private final AuthorizationPolicyEvaluator evaluator;
    private final EvidenceStore evidenceStore;
    private final ExceptionRegistry exceptions;

    public VerificationResult verify(RevocationJob job, TargetScope target) {
        TargetSnapshot snapshot = targetReader.readCurrent(target);

        if (snapshot.isUnavailable() || snapshot.isStale()) {
            exceptions.openOrUpdate(
                job.id(), target.id(), "TARGET_STATE_UNKNOWN"
            );
            return VerificationResult.unknown();
        }

        if (snapshot.hasTargetedEntitlement()) {
            exceptions.openOrUpdate(
                job.id(), target.id(), "RESIDUAL_ENTITLEMENT"
            );
            return VerificationResult.partial();
        }

        // Policy evaluation can strengthen but may not replace
        // runtime enforcement evidence for higher-risk targets.
        PolicyResult policyResult =
            evaluator.evaluateExpectedDeny(job.scope(), snapshot);

        if (!policyResult.isDeny()) {
            return VerificationResult.partial();
        }

        EvidenceReference ref = evidenceStore.persistValidated(
            job.id(), target.id(), snapshot, policyResult
        );

        return VerificationResult.observedRemoved(
            ref, "READBACK_PLUS_POLICY_CHECK"
        );
    }
}
~~~

**Quan trọng:** tên `observedRemoved` trong ví dụ thể hiện kết luận **quyền đã vắng trong readback và policy trả DENY**. Nó **không tự tương đương `VERIFIED_DENIED` ở runtime PEP**. Muốn kết luận đó cần native PEP evidence hoặc một phép thử truy cập được phê duyệt, kết hợp với scope/coverage được xác định.

### 33.1. Các lỗi phổ biến

- Verifier đọc target **trước khi lệnh được áp**, rồi ghi sai thất bại vĩnh viễn.
- Readback có cache cũ nhưng không ghi snapshot freshness.
- Chỉ đọc direct grant, bỏ qua nested group/ABAC.
- Dùng quyền admin để thử resource và nhận PERMIT, dù user đã bị revoke.
- Tự nhận `401` do network/API failure là revoked.
- Dùng một principal giả không tương ứng credential từng bị thu hồi.
- Cất raw token trong logs của test harness.
- Ghi `VERIFIED` khi only policy simulation, không nêu giới hạn.

### 33.2. Chứng cứ là một object, không chỉ Boolean

Một kết quả tối thiểu nên có **method, expected vs actual, source/authority, test scope, capturedAt, verifier identity, target version và evidence reference**. Một Boolean `revoked=true` thiếu provenance khó bảo vệ khi kiểm toán.

## 34. SQL kiểm tra độ đầy đủ của hồ sơ thu hồi

Ví dụ dùng **PostgreSQL-style SQL** trên những bảng đã chuẩn hóa và có quyền truy cập phù hợp:

- `revocation_target(revocation_id, target_id, required, effective_at)` – đích cần thu hồi theo scope.
- `revocation_evidence(revocation_id, target_id, evidence_type, result, verified_at, evidence_ref)` – kết quả đã được lưu.
- `observed_entitlement(identity_id, tenant_id, target_id, entitlement_id, snapshot_at)` – trạng thái target.
- `desired_entitlement(identity_id, tenant_id, target_id, entitlement_id, snapshot_at)` – quyền hợp lệ theo policy.

Các bảng/tên cột là **minh họa**, không phải schema của một sản phẩm.

### 34.1. Tìm target bắt buộc chưa có kết quả xác minh

~~~sql
SELECT
    t.revocation_id,
    t.target_id,
    t.effective_at,
    MAX(e.verified_at) AS last_verified_at
FROM revocation_target AS t
LEFT JOIN revocation_evidence AS e
    ON e.revocation_id = t.revocation_id
   AND e.target_id = t.target_id
   AND e.result = 'VERIFIED_DENIED'
WHERE t.required = TRUE
GROUP BY
    t.revocation_id,
    t.target_id,
    t.effective_at
HAVING COUNT(e.evidence_ref) = 0;
~~~

**Giới hạn:** query này chỉ tìm thiếu record `VERIFIED_DENIED`; không chứng minh record hiện có đáng tin hoặc đủ test coverage. Hệ thật phải tính **scope, evidence freshness, method, source integrity và exceptions**.

### 34.2. Phát hiện quyền observed vượt desired

~~~sql
SELECT
    o.identity_id,
    o.tenant_id,
    o.target_id,
    o.entitlement_id,
    o.snapshot_at
FROM observed_entitlement AS o
LEFT JOIN desired_entitlement AS d
    ON d.identity_id = o.identity_id
   AND d.tenant_id = o.tenant_id
   AND d.target_id = o.target_id
   AND d.entitlement_id = o.entitlement_id
WHERE d.identity_id IS NULL;
~~~

Đây là mô hình đối soát **EXTRA_ENTITLEMENT**. Trong production phải xử lý **snapshot versions, hiệu lực theo thời gian, multiple relationships, nested group, ABAC, deny policies, target account mapping và propagation window**. Không tự revoke mọi hàng trả về trước risk/authority checks.

### 34.3. Tính thời gian từ effectiveAt tới verifiedAt

~~~sql
SELECT
    t.revocation_id,
    t.target_id,
    EXTRACT(
        EPOCH FROM (MIN(e.verified_at) - t.effective_at)
    ) AS effective_to_verified_seconds
FROM revocation_target AS t
JOIN revocation_evidence AS e
    ON e.revocation_id = t.revocation_id
   AND e.target_id = t.target_id
   AND e.result = 'VERIFIED_DENIED'
WHERE t.required = TRUE
  AND e.verified_at IS NOT NULL
GROUP BY
    t.revocation_id,
    t.target_id,
    t.effective_at;
~~~

Thời gian tới lần đầu **quan sát xác minh** khác thời gian quyền thực sự mất hiệu lực nếu chưa có audit liên tục. Không coi những đích không có `verifiedAt` là 0 giây; chúng **không có phép đo**, phải được báo trong coverage/UNKNOWN.

### 34.4. Không để BI dashboard quyết định thu hồi

Các bảng analytics có thể đến chậm và chứa dữ liệu chưa kiểm. IGA thực thi grant/revoke phải dựa trên **authoritative identity state, approval/policy và target connector**; SQL có thể giúp **phát hiện drift hoặc bằng chứng thiếu**, không được tự cấp lại quyền chỉ vì query trả MISSING.

## 35. Case study A: Leaver với SCIM 200 nhưng session ERP còn dùng

### 35.1. Bối cảnh

Doanh nghiệp dùng HRIS, IdP SSO, ERP SaaS, API gateway và VPN. Một nhà thầu kết thúc hợp đồng lúc **18:00**, có web ERP session và API access token còn hạn.

### 35.2. Chuỗi sự kiện

~~~text
17:30  HRIS records termination with effectiveAt 18:00
18:00  IAM computes no access for employment-A
18:00  IdP blocks new login
18:01  SCIM PATCH active=false -> 200
18:02  SaaS readback active=false
18:03  Existing browser session still PERMITS invoice.read
18:04  Reconciliation emits RESIDUAL_SESSION
18:05  SaaS session termination initiated
18:07  ERP PEP DENIES tested invoice.read
18:09  VPN connection termination verified
~~~

### 35.3. Evidence package hợp lệ

| Mốc | Chứng cứ |
| --- | --- |
| HR event | RelationshipId, effectiveAt, source version |
| IAM decision | Policy `Leaver`, target scopes, command IDs |
| IdP | Disable account và session/grant results |
| SCIM | Operation ID, HTTP result và native state |
| Residual detected | ERP PERMIT after effectiveAt, audit reference |
| Remediation | SaaS session termination command |
| Verification | ERP DENY test at 18:07 và scope |
| VPN | Connection termination readback |
| Closure | Target coverage, exposure window review, exceptions |

### 35.4. Kết luận đúng

Không thể viết “thu hồi hoàn tất lúc 18:01” chỉ vì SCIM thành công. Có chứng cứ ERP vẫn truy cập được lúc 18:03; **cửa sổ tồn dư ít nhất phải được đánh giá**. Có thể nói ERP được quan sát DENY ở phép thử 18:07, với những giới hạn về các session/đường khác.

### 35.5. Bài học

Bằng chứng quan trọng đôi khi là **kết quả PERMIT trái mong muốn**, chứ không phải một loạt response success. Không xóa sự kiện thất bại để báo cáo đẹp.

## 36. Case study B: Mover và JWT giữ quyền cũ

### 36.1. Bối cảnh

Nhân viên A chuyển từ Sales sang Finance lúc 09:15. JWT access token đã cấp từ 09:00 chứa `SalesAdmin`, hết hạn lúc 10:00. IdP cập nhật group vào 09:16.

### 36.2. Control plane và data plane lệch nhau

~~~text
09:15 HRIS Mover effective.
09:16 IGA removes SalesAdmin from group.
09:17 CRM API accepts old JWT SalesAdmin.
09:19 PEP current-entitlement check deployed/updated.
09:20 CRM API denies sales.discount.approve with old JWT.
~~~

### 36.3. Chứng cứ cần giữ

- Mover event, policy mapping và approval scope.
- Group removal readback tại IdP.
- Token issuer/audience/scopes/exp **dưới dạng metadata an toàn**, không log raw JWT.
- PEP PERMIT at 09:17 chứng minh risk window.
- PEP DENY at 09:20 và policy version.
- Chứng cứ Finance entitlement chỉ được cấp sau approval và không vi phạm SoD.

### 36.4. Bài học

`RoleRemoved` không chứng minh `EffectiveAccessDenied` khi token claim hoặc cache còn cũ. Thời gian hoàn tất phải dựa trên **observable enforcement**, không chỉ commit metadata.

## 37. Case study C: emergency admin, PAM và quyền tồn dư

### 37.1. Bối cảnh

Một lần SSO outage khiến đội vận hành dùng **break-glass account** khôi phục quản trị cloud. Sau sự cố, PAM session đóng nhưng có thêm role admin tạm và API key mới.

### 37.2. Hồ sơ hậu kiểm

~~~text
Incident ID: INC-1041
Emergency access authorization: APPROVED
Emergency account login: OBSERVED
PAM/session recording: CLOSED
Temporary cloud role: STILL ACTIVE
New API key: STILL VALID
Credential custody: RESECURE PENDING
Overall closure: PARTIAL / PRIVILEGED_RESIDUAL
~~~

### 37.3. Bằng chứng xử lý đúng

- Native cloud IAM readback cho role và key.
- Lệnh revoke role/API key; kiểm issuance/use sau thu hồi theo capability.
- Session/token/network path cleanup.
- Evidence custody và reviewer độc lập.
- Credential/factor resecure với readiness retest cho recovery account.
- Chỉ đóng khi risk được xử lý hoặc exception được phê duyệt, có hạn và giám sát.

### 37.4. Bài học

**Một video phiên đã kết thúc không chứng minh không còn admin capability được tạo trong phiên.** Revocation evidence phải rà **những quyền phát sinh** trong cửa sổ đặc quyền.

## 38. Ma trận kiểm thử âm tính cho Revocation evidence

| Kiểm thử | Tình huống | Kỳ vọng |
| --- | --- | --- |
| **1. Request-only** | Có IAM command, target chưa phản hồi | REQUESTED, không VERIFIED |
| **2. SCIM 200 only** | Chưa readback | ACKNOWLEDGED |
| **3. SaaS local session** | Account inactive, cookie vẫn PERMIT | RESIDUAL_SESSION |
| **4. JWT old role** | IdP group gỡ nhưng API PERMIT | TOKEN/ENTITLEMENT_RESIDUAL |
| **5. Wrong audience** | Probe 401 do audience sai | Không coi là revoke verified |
| **6. Wrong resource** | 404 vì resource không tồn tại | Không coi là AuthZ deny verified |
| **7. API unavailable** | Probe timeout | UNKNOWN |
| **8. Readback stale** | Snapshot trước revoke | Không dùng làm kết luận mới |
| **9. Nested group** | Direct role mất, inherited còn | EXTRA_ENTITLEMENT |
| **10. Cross-tenant** | Revoke tenant-a, tenant-b còn | Kết luận đúng scope |
| **11. Multi-relationship** | Contract A kết thúc, B còn | Không xóa nhầm B |
| **12. Joiner canceled** | Pending job phát lại grant | Current-state guard chặn |
| **13. Mover after Leaver** | Event v10 tới sau v11 | Không re-enable |
| **14. Token refresh family** | Refresh token cũ được dùng | Reuse detection theo issuer |
| **15. Secret rotated** | Alternate key vẫn active | CREDENTIAL_RESIDUAL |
| **16. Service owner Leaver** | Worker vẫn cần chạy | Revoke human quyền, transfer owner |
| **17. Robot retired** | Scheduler off, ERP account enabled | ORPHAN/RESIDUAL |
| **18. PAM session closed** | Background process còn admin | PRIVILEGED_RESIDUAL |
| **19. Emergency key** | Cloud API key mới còn sau incident | Không đóng cleanup |
| **20. SSH tunnel** | JIT expired nhưng tunnel còn | NETWORK_PATH_RESIDUAL |
| **21. WebSocket** | Session revoked, stream vẫn gửi | Close/revalidate, flag gap |
| **22. Two regions** | Region A DENY, B PERMIT | PARTIAL, measure propagation |
| **23. Session recreate race** | Async task tạo S-new sau revoke | Chặn creation/current-state |
| **24. Target NOT_SUPPORTED** | Không có API terminate | Exception và controls, không VERIFIED |
| **25. Forged audit** | Executor tự khai target denied | Source validation / independent review |
| **26. Tampered artifact** | File evidence bị sửa | Integrity verification fail |
| **27. Missing audit gap** | SIEM outage, không có native log | EVIDENCE_GAP |
| **28. Raw token in log** | Collector in Bearer token | Privacy/security test fail |
| **29. Duplicate command** | Retry sau timeout | Idempotent, readback |
| **30. Manual regrant** | Admin cấp lại role sau closure | New event, alert/review |
| **31. Wrong principal** | Test bằng admin verifier thay user | Không kết luận user denial |
| **32. Wrong device** | Chỉ revoke mobile grant | Không gọi all devices revoked |
| **33. Deferred effectiveAt** | Leaver chưa đến giờ | Không áp sớm nếu policy không cho |
| **34. HR event late** | EffectiveAt đã qua 12 phút | Exposure analysis |
| **35. Source conflict** | Mapping account không chắc | Stop/review, không revoke mù |
| **36. PDP DENY** | Application vẫn thực thi action | ENFORCEMENT_GAP |
| **37. Policy simulator only** | Chưa có PEP runtime result | OBSERVED/POLICY_CHECK scope, không overclaim |
| **38. Audit log absent** | Không thấy request PERMIT | Không coi là proof of no access |
| **39. Exception accepted** | SaaS phiên hết sau TTL lâu | Accepted risk, không VERIFIED |
| **40. Replay after close** | Lệnh grant lịch sử được chạy lại | Version/policy guard và alert |

### 38.1. Kiểm thử end-to-end

~~~text
Authoritative decision
  -> Revocation scope/actor/policy validated
  -> Commands persisted and dispatched
  -> Target reports and native readback collected
  -> Sessions, tokens, credentials and inherited roles checked
  -> Effective denial assessed in required scope
  -> Independent verification and exception review
  -> Evidence manifest stored with integrity and retention
  -> Closure only within declared assurance/coverage
~~~

Một test chỉ xác nhận **command được gửi hoặc trả HTTP success** chưa đủ để chứng minh quyền đã bị ngăn tại resource.

## 39. KPI đo chất lượng revocation evidence

| KPI | Ý nghĩa | Tránh nhầm |
| --- | --- | --- |
| **Required-target evidence coverage** | Tỷ lệ đích bắt buộc có outcome hợp lệ | Không bỏ UNKNOWN khỏi mẫu số |
| **Revocation-to-effective-denial latency** | Từ thời điểm hiệu lực đến khi quan sát DENY | Không lấy command ACK làm deny time |
| **Request-to-apply latency** | Thời gian connector/target xử lý | Khác data-plane denial |
| **Residual privilege count** | Role/session/key còn sau revoke | Không chỉ đếm account inactive |
| **High-risk residual age** | Quyền nguy hiểm còn tồn tại bao lâu | Không đóng exception không owner |
| **Evidence integrity verification rate** | Artifact pass integrity checks | Hash không đo capture completeness |
| **Independent review coverage** | Hồ sơ rủi ro cao được kiểm độc lập | Executor tự xác nhận |
| **Unknown/unsupported targets** | Target không thể xác minh/không hỗ trợ | Không báo 100% success |
| **Stale token acceptance rate** | JWT/opaque token còn PERMIT sau revoke | Cần phân theo TTL/cache |
| **Effective-time event lag** | HRIS/security event đến trễ | Không lẫn ingestedAt với effectiveAt |
| **Post-revoke session recreation** | Session mới xuất hiện dù subject blocked | Kiểm race/new issuance |
| **Audit provenance completeness** | Có source, actor, target, verifier, scope | Không chứa bí mật |
| **Target snapshot freshness** | Readback đủ mới so với revoke | Snapshot cũ không chứng minh |
| **Exception remediation SLA** | Thời gian xử lý phần còn thiếu | Exception accepted khác verified |
| **Service identity orphan coverage** | Workload/robot không owner hoặc retired | Đừng bỏ non-human accounts |
| **Cross-region consistency** | Mọi PEP/region trong scope cùng DENY | Chỉ test một gateway |
| **Manual regrant after revoke** | Quyền được cấp lại không có authority | Cần phát hiện sau closure |
| **Evidence collection pipeline health** | Heartbeat, backlog, DLQ, ingestion gaps | Không có log không phải không có hoạt động |

### 39.1. Phân đoạn chỉ số theo risk

Một tỷ lệ 99% có thể che 1% **global admin accounts** còn hiệu lực. Nên phân tách theo **risk tier, tenant, human/non-human, target system, role privilege và method assurance**.

### 39.2. Không có SLA phổ quát

Mục tiêu thời gian phụ thuộc criticality, công nghệ và policy. Phải **đo bằng dữ liệu quan sát** và ghi công khai những target không có capability, không bịa cam kết thời gian thực.

## 40. Checklist để xây dựng hồ sơ Revocation evidence

| Câu hỏi kiểm tra | Bằng chứng cần |
| --- | --- |
| Xác định đúng lý do thu hồi, source authority? | HRIS/security/review event |
| Có identityId, relationshipId và principalType đúng? | Identity registry mapping |
| Có tenant/environment/target chính xác? | Scope contract |
| Actor, subject, approver và executor được tách? | Decision audit |
| Có effectiveAt và các timestamps riêng? | Event timeline |
| Có policy/approval/SoD version? | Decision artifact |
| Có target list đầy đủ và source of truth? | Target inventory |
| Có command ID, source event ID, correlation? | Outbox/connector logs |
| Có bảo đảm idempotency và chống stale events? | Version/replay tests |
| SCIM status có được readback? | Native target evidence |
| IdP disable có kiểm existing RP sessions không? | Session/SSO capabilities |
| Có kiểm refresh grants và access JWT còn sống? | Issuer/PEP evidence |
| Có đánh giá quyền qua nested groups/ABAC? | Effective permission readback |
| PAM/JIT/SSH/VPN có terminate sessions? | Native session evidence |
| Có kiểm key/token tạo thêm trong privileged session? | Credential inventory diff |
| Robot/service principal có retirement evidence? | Owner/credential/role lifecycle |
| Owner Mover/Leaver có gỡ vault/CI/CD quyền cá nhân? | Human JML readback |
| Có test DENY an toàn hoặc phương thức thay thế? | Verification method/scope |
| Phép thử có phân biệt 401/403/404/network error? | Probe design |
| Có kiểm nhiều region/cache khi cần? | Propagation tests |
| Có giám sát quyền được tái cấp sau revoke? | Regrant event/alert |
| Có phân biệt REQUESTED, APPLIED, OBSERVED, VERIFIED? | State machine |
| Có trạng thái UNKNOWN/PARTIAL/NOT_SUPPORTED? | Exception register |
| Có owner, deadline và compensating controls cho gap? | Remediation workflow |
| Evidence collector độc lập với executor khi risk cao? | SoD design |
| Có native source refs, integrity manifest? | Evidence package |
| Audit có bị xóa/sửa bởi người đang cấp quyền không? | Storage ACL/integrity |
| Có kiểm log pipeline bị thiếu event? | Heartbeat/sequence monitoring |
| Có giảm PII và không lưu raw secret/token? | Privacy audit |
| Có retention, legal hold và quyền export phù hợp? | Governance |
| Có báo assurance/coverage/limitations ở closure? | Review/closure artifact |
| STEP 4 chỉ viết bài, không tự chạy QA chuyên môn? | Quy trình tạo nội dung của module |

## 41. Những nhầm lẫn thường gặp

1. **“Đã gửi lệnh revoke là đã hết quyền.”** Chưa biết target áp dụng.
2. **“SCIM trả 200 thì mọi session SaaS đóng.”** Cần kiểm session/token riêng.
3. **“IdP disabled thì JWT cũ không dùng được.”** Token offline có thể còn hạn.
4. **“Gỡ direct role nghĩa không còn quyền.”** Có thể còn group-inherited/ABAC permissions.
5. **“PDP DENY bảo đảm business action không chạy.”** PEP có thể bị bypass.
6. **“Một 401 chứng minh session đã revoke.”** Có thể do token sai hoặc lỗi khác.
7. **“404 chứng minh không có quyền.”** Có thể resource không tồn tại.
8. **“Không thấy log PERMIT tức không thể PERMIT.”** Có thể không có request hoặc logging gap.
9. **“Một probe bị DENY chứng minh mọi access paths bị chặn.”** Scope cần rõ.
10. **“Hash chứng minh không có event nào bị bỏ sót.”** Hash chỉ hỗ trợ integrity của artifact có mặt.
11. **“Target không liên lạc được coi như không có quyền.”** Trạng thái UNKNOWN.
12. **“Exception accepted tức là revoked verified.”** Khác nhau về assurance.
13. **“Logout đủ xử lý privileged session.”** Shell/SSH/tunnel có thể còn.
14. **“Stop bot nghĩa ERP account hết hiệu lực.”** Principal/credential còn.
15. **“Owner Leaver thì xóa mọi service.”** Workload hợp lệ có thể cần tiếp tục, quyền người cũ phải gỡ.
16. **“Mọi Mover phải thu hồi tất cả sessions.”** Phụ thuộc role, risk và scope.
17. **“Email là khóa revocation duy nhất.”** Cần stable identity/relationship/tenant.
18. **“Dữ liệu audit luôn chính xác vì có chữ ký.”** Producer có thể sai hoặc bị chiếm.
19. **“Chứng cứ càng chứa nhiều PII và token càng tốt.”** Tăng rủi ro bảo mật.
20. **“Thay policy rồi là mọi PEP đã cập nhật.”** Cache/region có thể lệch.
21. **“Command retry là lỗi.”** At-least-once delivery cần idempotency.
22. **“Event đến sau luôn mới hơn.”** Có thể stale/out-of-order.
23. **“Access review REVOKE đồng nghĩa target role đã gỡ.”** Cần remediation/readback.
24. **“Một bằng chứng verified giữ giá trị vĩnh viễn.”** Regrant về sau có thể đổi trạng thái.
25. **“Evidence từ executor là đủ trong mọi trường hợp.”** Quyền cao cần independent verification khi policy yêu cầu.
26. **“Mọi hệ phải active probe.”** Probe có thể không an toàn/không được cho phép; có phương pháp thay thế.
27. **“Đo latency từ lúc nhận HR event là đủ.”** Effective time có thể sớm hơn.
28. **“100% target được gửi command là 100% verified.”** Hai KPI khác nhau.
29. **“Xóa role đồng nghĩa rollback mọi hành động đã commit.”** Business compensation là vấn đề khác.
30. **“Hồ sơ đóng rồi không cần giám sát.”** Vẫn cần phát hiện regrant và drift.

## 42. Câu hỏi tự đánh giá

1. Revocation evidence khác revocation request và audit log kỹ thuật ở đâu?
2. Nêu ít nhất sáu mốc từ quyết định thu hồi tới VERIFIED_DENIED.
3. Vì sao HTTP 200 của SCIM không chứng minh local session đã bị đóng?
4. Vì sao IdP disabled vẫn có thể để lại JWT access token còn dùng?
5. Phân biệt refresh grant revocation và access-token effective denial.
6. Một user Mover còn Finance role nhờ project approval: đó có phải quyền tồn dư không?
7. Vì sao phải phân biệt identityId với relationshipId?
8. Actor, subject, resource owner, executor và verifier khác nhau thế nào?
9. Evidence package cần những trường nào để auditor tái dựng quyết định?
10. `effectiveAt`, `appliedAt`, `verifiedAt` khác nhau thế nào?
11. Làm sao đo exposure window khi HRIS gửi Leaver event trễ?
12. Phép thử 401 từ token sai audience có phải chứng minh revoke thành công không?
13. Khi nào 404 không thể dùng làm chứng cứ AuthZ deny?
14. Vì sao một phép thử DENY không bao phủ mọi session và tenant?
15. Phân biệt target management readback và policy simulation.
16. Khi nào cần safe PEP probe và khi nào nên tránh?
17. Một SaaS không hỗ trợ session termination phải báo trạng thái gì?
18. Vì sao target UNKNOWN không được coi là NO_ACCESS?
19. Vai trò của independent verifier trong thu hồi quyền đặc biệt cao?
20. Một PAM session đóng nhưng cloud API key mới vẫn hoạt động: còn bước nào?
21. Vì sao stop RPA job không chứng minh robot account đã bị thu hồi?
22. Khi service owner Leaver nhưng workload vẫn cần chạy, các loại evidence nào cần thu?
23. Kể ba cơ chế xử lý JWT stale và giới hạn từng cơ chế.
24. Tại sao source version guard quan trọng khi Mover event tới sau Leaver?
25. Transactional outbox giúp gì? Có bảo đảm SCIM target đã áp dụng không?
26. Hash/digest bảo đảm điều gì và không bảo đảm điều gì về completeness?
27. Chain of custody cần ghi những thông tin tối thiểu nào?
28. Vì sao không nên đưa raw token và PII nhạy cảm vào audit event?
29. Reconciliation phải so sánh desired, observed và effective state như thế nào?
30. Hãy thiết kế một query/report tìm các target bắt buộc chưa có verification.
31. KPI effective-to-denial latency khác request-to-apply latency thế nào?
32. Vì sao cần kiểm quyền group-derived khi direct role đã bị gỡ?
33. Một admin cấp lại role sau closure: chứng cứ cũ sai hay có sự kiện mới?
34. Tạo checklist tối thiểu để đóng một hồ sơ Leaver có IdP, ERP, VPN và OAuth client.
35. Trình bày một kết luận kiểm toán trung thực khi 7/8 target đã VERIFIED nhưng target còn lại UNKNOWN.

## 43. Ghi nhớ

**Revocation evidence** là **chứng cứ có nguồn gốc, phạm vi, thời điểm và kết quả rõ ràng** để xác minh rằng một quyền, tài khoản, phiên, credential hoặc đường truy cập đã được thu hồi theo quyết định hợp lệ. Cần phân biệt **DECIDED → REQUESTED → ACKNOWLEDGED → APPLIED → OBSERVED → VERIFIED_DENIED** và lưu cả các trạng thái **PARTIAL, UNKNOWN, NOT_SUPPORTED, EXCEPTION**. **Không có một HTTP response, event, screenshot hay phép thử đơn lẻ nào tự chứng minh mọi quyền ở mọi hệ đã hết**, nếu thiếu xác định scope, nguồn và mức bảo đảm.

Trong quản lý vòng đời **Joiner–Mover–Leaver**, **HRIS/identity registry** xác định căn cứ quyền và effectiveAt; **IGA/owner approval** tạo quyết định; **IdP/SSO, SCIM/API, RBAC/ABAC/PBAC, PAM/JIT và workload identity systems** thực thi thay đổi; **resource PEP, target readback, audit và reconciliation** giúp xác minh hiệu lực. Thiết kế đạt yêu cầu khi có **identity/relationship mapping đúng, event/command lineage, chống stale/replay, bảo vệ chứng cứ và PII, kiểm inherited roles/tokens/sessions, independent review theo risk, SLA cho quyền tồn dư và closure trung thực về coverage**. Mục tiêu không chỉ là báo “đã thu hồi” mà là **có thể giải thích, kiểm tra lại và giới hạn chính xác điều đã được xác minh**.
