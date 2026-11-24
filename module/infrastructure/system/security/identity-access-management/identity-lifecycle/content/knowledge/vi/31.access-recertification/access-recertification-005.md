# Thu hồi quyền sau Access recertification: từ quyết định rà soát đến quyền truy cập đã được chặn

**Thu hồi quyền** (*access revocation*) trong **Access recertification** là quá trình biến một quyết định rà soát rằng **một entitlement không còn được phép duy trì** thành các thay đổi có hiệu lực trên **account, role, group, policy, credential hoặc session** tại hệ thống đích, rồi **kiểm chứng** rằng đường truy cập không còn căn cứ đã thật sự bị chặn. Đây không phải việc đổi một ô trong bảng chứng nhận từ `KEEP` sang `REVOKE` và cũng không phải chỉ gỡ dấu tick trên giao diện quản trị.

Ví dụ, đợt rà soát quý phát hiện Lan vẫn thuộc nhóm `production-deployers` dù đã chuyển từ Operations sang Finance. Application owner quyết định **REVOKE**. IAM phải xác định đúng **person identity → target account → group/role grant**, gỡ membership ở **nguồn có thẩm quyền**, đối soát việc quyền được đồng bộ xuống ứng dụng, và kiểm tra những đường cấp khác (role trực tiếp, nhóm lồng nhau, session, API token) nếu mục tiêu là loại bỏ toàn bộ quyền triển khai production. Chỉ khi các tiêu chí kiểm chứng được đáp ứng, quyết định mới nên được ghi nhận là **revocation verified**.

Bài thuộc chương **Access recertification** của module **Security — Identity and Access Management (IAM) — Identity Lifecycle**. Trọng tâm là quản lý vòng đời **Joiner–Mover–Leaver (JML)**, kết hợp **HRIS, IdP, SSO, SCIM provisioning, RBAC/ABAC, PAM, tài khoản dịch vụ, audit và giảm quyền truy cập tồn dư**. Mục tiêu sau bài học là phân biệt **review decision** với **thực thi thu hồi**, chọn đúng phạm vi, thiết kế quy trình không cấp nhầm/thu hồi nhầm, xử lý kết quả bất đồng bộ và chứng minh *actual effective access*.

> **Nguyên tắc:** `REVOKE` trong kết quả recertification là **yêu cầu thay đổi trạng thái quyền**. `SCIM PATCH 200`, `group removed` hoặc `account disabled` là những bằng chứng trung gian. **Hoàn tất** phải dựa trên quyền hiệu lực tại target và các điều kiện kiểm chứng được định nghĩa cho loại quyền đó.

## 1. Access recertification và ý nghĩa của quyết định thu hồi

**Access recertification**, còn gọi là **access review** hoặc **access certification**, là hoạt động người có thẩm quyền xác nhận những quyền đã cấp **có còn phù hợp với nhiệm vụ, quan hệ lao động/hợp đồng, phạm vi tài nguyên và chính sách hay không**. Kết quả có thể phát sinh lệnh giữ, thu hồi, giảm phạm vi, yêu cầu bổ sung bằng chứng hoặc xử lý ngoại lệ.

### 1.1. Phân biệt các quyết định

| Quyết định review | Ý nghĩa nghiệp vụ | Tác động kỹ thuật phù hợp |
| --- | --- | --- |
| **KEEP / CERTIFY** | Quyền vẫn có căn cứ tại thời điểm review. | Không tự mở rộng quyền; ghi chứng cứ, có thể đặt lần review kế tiếp. |
| **REVOKE** | Một grant/entitlement không còn được duy trì. | Lập kế hoạch gỡ đúng grant/đường cấp quyền và kiểm chứng. |
| **MODIFY / REDUCE** | Cần quyền hẹp hơn hoặc thời hạn ngắn hơn. | Cấp cấu hình hẹp đúng policy, thu hồi phần rộng dư thừa, verify. |
| **CONDITIONAL KEEP** | Chỉ được giữ khi đáp ứng điều kiện bổ sung. | Theo policy: áp điều kiện/approval/time-box, nếu không đạt thì thu hồi. |
| **DEFER / NEEDS_INFO** | Chưa có đủ dữ liệu để đưa ra kết luận hợp lệ. | Giữ trạng thái review chưa hoàn tất; xử lý theo risk, không coi mặc định là KEEP. |
| **EXCEPTION APPROVED** | Được phép giữ một quyền ngoài baseline trong giới hạn cụ thể. | Gắn owner, scope, expiry, compensating controls và kỳ rà soát; không giữ vĩnh viễn. |

Tên trạng thái thực tế tùy IGA/product. **Không giả định mọi phần mềm hỗ trợ cùng các từ khóa hay điều kiện xử lý.** Một doanh nghiệp có thể định nghĩa chính sách “không phản hồi sau SLA” dẫn tới escalated review hoặc hạn chế quyền, nhưng không nên suy diễn mọi timeout đều là Approve hay Revoke không qua owner được chỉ định.

### 1.2. Review khác revoke và khác deprovisioning account

| Hoạt động | Đối tượng | Ví dụ |
| --- | --- | --- |
| **Review** | Quyết định có còn căn cứ cho quyền. | Manager đánh giá Lan có cần `report:export` không. |
| **Entitlement revocation** | Gỡ hoặc giảm một grant cụ thể. | Gỡ Lan khỏi `finance-exporters`. |
| **Account deactivation** | Chặn account truy cập ứng dụng. | `User.active=false` hoặc trạng thái khóa target. |
| **Session/token revocation** | Chặn đường truy cập đã có hiệu lực trước thay đổi. | Kết thúc PAM session, revoke refresh token. |
| **Identity offboarding** | Đóng các đường truy cập cần thu hồi khi Leaver. | Disable IdP, target, local accounts, privileged sessions và credential. |
| **Reconciliation** | So desired access với actual access và giải thích sai lệch. | Phát hiện role vẫn tồn tại qua direct grant. |

**Thu hồi một role không đồng nghĩa xóa account.** Một nhân viên còn làm việc có thể mất quyền `ProductionAdmin` nhưng vẫn cần SSO và các quyền đọc hợp lệ. Ngược lại, Leaver có thể cần chặn mọi access path ngay cả khi một đợt recertification định kỳ chưa diễn ra.

## 2. Đối tượng thu hồi: điều gì thực sự cần biến mất?

Một review row thường là biểu diễn rút gọn của nhiều quan hệ kỹ thuật. Trước khi thực thi `REVOKE`, phải xác định row đang mô tả:

| Loại đối tượng | Ví dụ | Thao tác thu hồi có thể cần |
| --- | --- | --- |
| **User–role assignment** | Lan → `ERP_PaymentApprover`. | Gỡ assignment ở app/IGA/connector có thẩm quyền. |
| **Group membership** | Lan thuộc `ops-prod-deployers`. | Gỡ membership trong IdP hoặc SCIM target đúng nơi quản lý. |
| **Inherited permission** | `ReportEditor >= ReportReader`. | Gỡ senior role nếu không còn căn cứ; không xóa global hierarchy tùy tiện. |
| **Direct/resource grant** | Lan được `project-owner` trên `project-alpha`. | Gỡ grant tại cloud/resource policy. |
| **Delegation/exception** | Quyền export theo dự án 14 ngày. | Hủy delegation hoặc để expiry được enforced, verify. |
| **PAM/JIT eligibility** | Được phép yêu cầu `DBAdmin`. | Gỡ eligibility; kiểm tra activation đang mở. |
| **Active privileged session** | SSH/DB session qua PAM. | Kết thúc/giới hạn phiên theo khả năng target. |
| **Local account** | `lan-db-admin` không quản lý bằng SSO. | Disable/deprovision local account theo quyết định. |
| **Token/credential** | PAT, API key, SSH key, certificate. | Revoke/rotate hoặc hạ scope với bằng chứng. |
| **Service/workload grant** | Job `billing-etl` có quyền read-all. | Thu hẹp workload role/dataset, không nhầm vòng đời với chủ sở hữu là người. |

### 2.1. Thu hồi đúng grant không đồng nghĩa cắt mọi quyền tương đương

Giả sử Lan nhận `report:read` qua:
- Một role trực tiếp `ReportReader` từ dự án A.
- Một role senior `ReportEditor` thuộc assignment B.
- Một group `all-finance-staff` có quyền đọc báo cáo chung.

Reviewer chọn REVOKE **grant dự án A**. Việc gỡ đúng grant có thể thành công, nhưng Lan vẫn có `report:read` qua B hoặc group chung — và điều đó **có thể hợp lệ** nếu những assignment kia còn căn cứ. Không được gỡ mọi nguồn bằng mọi giá khi review chỉ yêu cầu xóa **một đường cấp**.

Ngược lại, nếu quyết định là **“Lan không còn được truy cập báo cáo X qua bất kỳ đường nào”**, phải truy vết và xử lý **tất cả các đường cho phép** hành động đó. **Phạm vi thu hồi phải được diễn đạt rõ**: grant-specific hay effective-access-specific.

### 2.2. Không dùng tên hiển thị làm khóa

Một identity có thể có:
- IAM identity: `person-2048`.
- IdP account: `idp-user-581`.
- SCIM User.id tại app: `u-9008`.
- Local privileged account: `lan-admin-2`.
- Tên hiển thị/email: có thể thay đổi hoặc tái sử dụng.

Lệnh gỡ quyền phải dùng **target ID/account binding** đã xác minh cùng **tenant, provider, nguồn grant**; không chọn account đầu tiên trùng email. Một lỗi identity correlation trong thu hồi có thể **khóa nhầm người**, gây gián đoạn và vẫn để lại quyền của người cần thu hồi.

## 3. Vì sao quyền tồn dư dễ xuất hiện sau kỳ rà soát?

Quyền tồn dư (*residual access*) có thể tồn tại vì một hoặc nhiều lý do:

1. **Decision chỉ được ghi tại IGA**, chưa tạo remediation ticket/connector job.
2. **Connector lỗi hoặc bị giới hạn quyền**, không xóa được group/role ở target.
3. **Grant nằm ngoài IAM**, như direct role tại app hoặc tài khoản local.
4. **Role hierarchy/nested group** còn đường kế thừa khác.
5. **Dữ liệu recertification là snapshot cũ**; target/HRIS thay đổi khi reviewer xem.
6. **Session/token/credential còn hiệu lực** sau khi group/role đã gỡ.
7. **Đồng bộ bất đồng bộ** giữa IdP, SCIM target và authorization cache.
8. **Exception/JIT/delegation** chưa hết hạn hoặc được cấp lại.
9. **Owner không rõ** khiến quyết định không có executor hoặc không có người nhận lỗi.
10. **Đóng ticket sớm** khi lệnh API trả 200, không có readback.

Vì vậy cần **một vòng khép kín**: *Review → Revocation plan → Execute → Readback → Verify effective access → Close or remediate*.

## 4. Nguồn dữ liệu đầu vào trước khi thu hồi

Trước khi dùng lệnh gỡ, IAM/IGA phải có **evidence** từ những nguồn có thẩm quyền:

| Nguồn | Cung cấp gì? | Giới hạn |
| --- | --- | --- |
| **HRIS/contractor registry** | Employment status, manager, department, end date, assignment. | Có thể chưa chứa entitlement tại từng ứng dụng. |
| **IAM identity registry** | Person identity và mapping tới IdP/target accounts. | Binding thiếu hoặc stale cần review thủ công. |
| **IdP/directory** | Groups, app assignments, SSO state. | Không bao gồm mọi local/direct grant của app. |
| **SCIM target** | User/Group theo provider capability. | Không chuẩn hóa mọi role/PAM session/entitlement. |
| **Application/cloud/DB IAM API** | Roles, resource policies, local accounts. | API/permission model riêng; cần target owner. |
| **PAM/session/credential registry** | Eligibility, activation, session, credential checkout. | Không chắc kiểm soát mọi đường trực tiếp ngoài PAM. |
| **Approval/review system** | Review decision, certifier authority, snapshot/version. | Không thay thế bằng chứng target đã thu hồi. |
| **Audit/activity logs** | Usage, last used, hành động và bất thường. | Không hoạt động trong kỳ không tự chứng minh quyền không cần thiết. |

### 4.1. Snapshot review và trạng thái hiện hành

Đợt review có thể tạo snapshot ngày 01/11, reviewer quyết định ngày 10/11, nhưng account đã chuyển vai trò ngày 05/11 hoặc có một grant mới ngày 09/11. Nếu làm theo snapshot mà không kiểm tra state mới có thể:
- Gỡ một quyền **đã được approve hợp lệ bởi assignment mới**.
- Xóa group mà ứng dụng đã thay đổi ID/owner.
- Bỏ sót direct grant phát sinh sau snapshot.
- Re-add quyền cũ khi reconciliation không kiểm soát nguồn.

**Phải phân biệt:** `reviewSnapshotAt`, `decisionAt`, `executedAt`, `verifiedAt` và `effectiveAt`. Nếu có thay đổi quan trọng giữa các mốc, cần **revalidate phạm vi** hoặc escalated review theo policy.

### 4.2. Người duyệt có thẩm quyền

- Manager xác nhận người còn cần quyền cho công việc không.
- App/resource owner xác nhận role và scope đúng không.
- Data owner xác nhận access tới dữ liệu nhạy cảm.
- Security/IGA xác nhận SoD, đặc quyền và policy.

Không để beneficiary **tự chứng nhận** quyền nhạy cảm của mình nếu chính sách yêu cầu reviewer độc lập. Hai account của cùng một người không phải hai approver khác nhau. Cần có **delegation/alternate approver** rõ khi owner vắng mặt.

## 5. Quyết định REVOKE phải cụ thể đến đâu?

Một quyết định có thể ở ba độ chi tiết:

| Granularity | Ví dụ | Lưu ý |
| --- | --- | --- |
| **Account-level** | “Không còn được vào ERP”. | Có thể cần disable account, sessions, local login, API tokens. |
| **Entitlement-level** | “Gỡ role `InvoiceApprover` trên ERP”. | Không được disable toàn account nếu còn role hợp lệ. |
| **Effective-permission-level** | “Không còn `payment:approve` trong tenant-vn qua bất kỳ đường nào”. | Phải kiểm tra mọi assigned/inherited/direct grant. |

Quyết định phải có **beneficiary, target, permission/role/group, scope, source và effective deadline**. Nếu reviewer chỉ nhìn một nhãn “Finance” không rõ role nào, hệ thống phải bổ sung thông tin chứ không tự mở rộng phạm vi thu hồi.

### 5.1. REVOKE và REDUCE khác nhau

- **REVOKE:** loại bỏ grant/đường quyền không còn căn cứ.
- **REDUCE:** thay grant rộng bằng cấu hình hẹp hơn.

Ví dụ role `GlobalReportExporter` có thể được giảm xuống `FinanceReportReader` trong tenant-vn. Một cutover an toàn cần **bảo đảm quyền hẹp hợp lệ tồn tại**, sau đó thu hồi role rộng và chứng minh việc đọc hợp lệ vẫn hoạt động trong khi export-all đã bị chặn. Không “rollback” bằng cách cấp lại GlobalAdmin vĩnh viễn nếu cấu hình hẹp thiếu một permission.

### 5.2. Exception phải có cấu trúc

Một quyền được reviewer đánh dấu REVOKE nhưng còn cần 7 ngày để bàn giao chỉ có thể được giữ khi chính sách chấp nhận **exception có owner, lý do, scope, approval, thời hạn, compensating controls**. Không chuyển quyết định thành KEEP vĩnh viễn chỉ vì application owner hứa sẽ xử lý sau.

## 6. End-to-end workflow từ chứng nhận đến thu hồi

~~~mermaid
flowchart TD
    S["Review snapshot + authoritative identity binding"] --> C["Certifier: KEEP / REVOKE / REDUCE / EXCEPTION"]
    C -->|REVOKE/REDUCE| V["Validate decision, target, source, policy"]
    C -->|KEEP| K["Record certification + next review"]
    V --> G["Discover direct + indirect grant paths"]
    G --> P["Plan scoped revocation and impact"]
    P --> A{"Approval/SoD/ownership checks required?"}
    A -->|Chưa đạt/không rõ| Q["Escalate, manual review or containment"]
    A -->|Đạt| X["Execute via IdP / SCIM / app API / PAM / manual"]
    X --> R["Readback actual account/role/group/credential state"]
    R --> E{"Effective access matches desired?"}
    E -->|Có| F["VERIFIED + immutable audit"]
    E -->|Không| M["REMEDIATION_REQUIRED with owner/SLA"]
    M --> X
    Q --> P
~~~

Lưu ý: đây là đường tham khảo. Một **Leaver khẩn hoặc quyền nguy hiểm đang vi phạm policy** có thể cần chặn trước theo nguồn có thẩm quyền, **không chờ một approval cấp quyền mới**. Điều kiện approval trong sơ đồ là **phê duyệt có liên quan đến thay đổi/ngoại lệ nhạy cảm**, không phải một quyền veto tùy tiện chống lại revocation bắt buộc.

### 6.1. Bước 1 — Chốt quyết định và phạm vi

Lưu:
- Campaign/review ID và decision ID.
- Reviewer identity, authority và timestamp.
- Beneficiary IAM identity, target account binding.
- Grant/role/group ID, tenant và scope.
- Decision: REVOKE hoặc REDUCE, effective deadline.
- Business reason và risk severity.
- Policy version và yêu cầu xác minh.
- Owner/connector chịu trách nhiệm thực hiện.

### 6.2. Bước 2 — Tính current desired state

Kết hợp review decision với:
- Current HR/JML status.
- Các assignment đang có hiệu lực.
- Approval/exception còn hợp lệ.
- Role hierarchy/ABAC scope.
- Các nguồn grant được phép.
- System owner/automation guardrails.

**Không cho phép một batch cũ ghi đè desired state mới** mà không reconcile. Đặc biệt, một quyền được review REVOKE ở project cũ có thể được approve lại trong assignment mới với scope khác — cần phân biệt rõ grant source.

### 6.3. Bước 3 — Thực thi, readback và đóng

Thực thi ở **nguồn có quyền quản lý grant**, nhận target response, rồi đọc lại để kiểm tra. Nếu quyền đã mất do workflow khác, vẫn cần chứng minh trạng thái đích và ghi **ALREADY_COMPLIANT** hoặc kết quả phù hợp, tránh gửi thao tác phá hủy không cần thiết.

**Không đồng nhất request accepted với effective revocation**. Với quyền admin hoặc dữ liệu nhạy cảm, cần kiểm tra cả **khả năng thực hiện hành động thực tế** ở scope mà review yêu cầu.

## 7. Thu hồi group membership tại IdP/SCIM

Một trường hợp phổ biến là reviewer quyết định User không còn nên thuộc một **group ứng dụng**.

### 7.1. Tìm đúng Group và User trước PATCH

IAM có thể biết:
- `targetGroupId = g-prod-23`.
- `targetUserId = u-9008`.
- Group display name `ops-prod-deployers`.

Dùng **ID đã xác minh tại đúng SCIM service provider/tenant**, không mặc định IAM person ID là SCIM User.id. Nếu chưa có ID, phải tra target theo cơ chế được hỗ trợ, đánh giá uniqueness/source; không tự gỡ “người đầu tiên trùng email”.

### 7.2. PATCH Group remove member

Ví dụ **SCIM 2.0** nếu provider hỗ trợ PATCH:

~~~http
PATCH /scim/v2/Groups/g-prod-23 HTTP/1.1
Authorization: Bearer <provisioning-access-token>
Content-Type: application/scim+json
Accept: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"u-9008\"]"
    }
  ]
}
~~~

Ở đây:
- `/Groups/g-prod-23` là **Group cần sửa**.
- `members[value eq "u-9008"]` là **SCIM PATCH valuePath** chọn một member theo target User ID.
- `remove` yêu cầu gỡ membership.
- Hỗ trợ, mã response và hành vi khi member không tồn tại có thể khác nhau theo provider.
- Sau thao tác, cần **GET lại Group/membership** và đối soát quyền tại ứng dụng.

**SCIM không chuẩn hóa đầy đủ mọi semantics role hierarchy, dynamic group hoặc quyền đặc biệt của từng sản phẩm.** Một PATCH Group thành công không bảo đảm local role, personal access token hoặc session cũ đều mất quyền.

### 7.3. Phân biệt IdP group và target group

| Nguồn | Gỡ ở đâu? | Điều cần kiểm tra |
| --- | --- | --- |
| **Group authoritative tại IdP** | IdP/directory, rồi chờ connector provisioning. | IdP membership, target membership, session/claim. |
| **SCIM Group target authoritative** | Target API/SCIM theo hợp đồng. | Target Group ID, member list, local role mapping. |
| **Dynamic group** | Policy/attributes tạo điều kiện membership. | Source attribute/rule; gỡ manual có thể bị tự thêm lại. |
| **Nested group** | Group con/cha hoặc app membership engine. | Đường kế thừa effective; gỡ một nhánh có đủ không. |
| **Direct role tại app** | App-specific admin/API. | SCIM Group readback không thay thế app role readback. |

**Nguồn có thẩm quyền phải rõ.** Nếu IdP là source và connector mỗi đêm đồng bộ, gỡ trực tiếp ở target có thể bị **re-provision**. Sửa đúng source, theo dõi downstream và kiểm tra drift.

## 8. Thu hồi role, direct grant và quyền kế thừa RBAC

### 8.1. Role trực tiếp

Khi review nói “gỡ `ProductionOperator` khỏi Lan”, thao tác thông thường là **xóa User–Role Assignment** của Lan trong scope xác định. Không phải xóa **role definition** `ProductionOperator` khỏi toàn bộ hệ thống — điều đó có thể làm nhiều người khác mất quyền.

### 8.2. Role hierarchy làm quyền tồn tại gián tiếp

Giả sử:

~~~text
PlatformAdmin >= PlatformOperator >= PlatformViewer

User assignments:
  Lan -> PlatformAdmin
  Lan -> IncidentResponder

IncidentResponder >= PlatformViewer
~~~

Gỡ `PlatformAdmin` sẽ loại quyền operator kế thừa nếu không còn đường khác, nhưng Lan có thể vẫn có `PlatformViewer` qua `IncidentResponder`. Nếu mục tiêu chỉ REVOKE `PlatformAdmin`, quyền xem qua incident role có thể vẫn hợp lệ. Nếu mục tiêu **không còn bất kỳ production access**, phải rà soát cả incident role, direct grants và policy khác.

### 8.3. Không sửa cạnh hierarchy toàn cục để thu hồi một User

Thay đổi `Senior >= Junior` ảnh hưởng **mọi user có Senior hoặc ancestor roles**, có thể gây overgrant/overrevoke hàng loạt. Review cấp User thường nên thực hiện ở **assignment/grant source**. Sửa toàn bộ hierarchy chỉ khi có **role design change** được đánh giá riêng, approved impact analysis và target verification.

### 8.4. Direct/resource policy grants

Các nền tảng cloud/DB/Kubernetes có thể chứa quyền:
- IAM resource policy.
- Database GRANT.
- Kubernetes RoleBinding/ClusterRoleBinding.
- Delegated permission hoặc impersonation.
- Owner privilege đối với resource.
- Service principal role assignment.

Không phải tất cả các quyền trên đều thể hiện thành SCIM Group. Cần provider-specific inventory, executor có thẩm quyền và readback đúng resource/namespace.

## 9. ABAC, dynamic entitlement và điều kiện theo ngữ cảnh

**ABAC** quyết định access dựa trên **subject, resource, action, environment attributes**. Người dùng có thể còn role `ReportReader` nhưng bị từ chối đọc dữ liệu cũ sau Mover nhờ condition `subject.department == resource.department`.

~~~text
allowRead =
    subject.lifecycleStatus == "ACTIVE"
    AND rolePermissions(subject.roles).contains("report:read")
    AND subject.tenantId == resource.tenantId
    AND subject.department == resource.department
    AND subject.clearanceRank >= resource.classificationRank
~~~

**Đây là pseudocode**, không phải định dạng SCIM/OPA/Cedar/XACML bắt buộc. Các thuộc tính cần được lấy từ nguồn đáng tin.

### 9.1. Tại sao ABAC Deny chưa phải là thu hồi entitlement?

Một role vẫn tồn tại tại target, có thể được ứng dụng khác sử dụng không áp cùng policy; token cũ có thể mang claim của bộ phận cũ. Khi recertification xác định **role không còn căn cứ**, phải **deprovision role/group** chứ không chỉ dựa vào một condition đang từ chối.

### 9.2. Không tự xóa thuộc tính HRIS để chặn quyền

Nếu muốn thu hồi quyền vào một ứng dụng, đừng sửa `department` giả từ Finance thành Unknown hoặc xóa manager ID để làm policy Deny. Cần sửa **grant/assignment** đúng nguồn, hoặc áp account lock/deny policy phù hợp với quyết định đã được duyệt.

Dữ liệu HRIS phải phản ánh **thực tế nhân sự**, không bị dùng như “công tắc quyền” ngoài quản trị.

## 10. Session, SSO và token sau khi thu hồi

**IdP/SSO** có thể chặn đăng nhập mới, nhưng **application session, OAuth access token, refresh token, PAT, SSH key hoặc certificate** có thể còn khả dụng.

### 10.1. Mốc thời gian ví dụ

~~~text
08:00  User nhận access token có quyền production, exp=09:00
08:10  Reviewer quyết định REVOKE production access
08:12  IAM gỡ group ở IdP
08:14  SCIM target đã gỡ membership
08:15  Resource server chỉ kiểm JWT signature/exp từ token cũ
09:00  Access token hết hạn nếu không có kiểm soát khác

08:14 đến 09:00: có thể tồn tại residual access
nếu ứng dụng không đánh giá lại quyền hoặc có cơ chế chặn khác.
~~~

Token được ký hợp lệ chứng minh issuer đã phát hành nó; **không chứng minh quyền vẫn được phép ở thời điểm hiện tại**. Cần hiểu kiến trúc thực tế: short-lived tokens, introspection, revocation, session invalidation, forced reauthentication hoặc policy check mỗi request theo khả năng.

### 10.2. Các lớp cần kiểm tra khi recertify privileged access

| Lớp | Câu hỏi |
| --- | --- |
| IdP/directory | Group/role/assignment đã gỡ chưa? |
| Application | Local role/entitlement có còn không? |
| PAM | Eligibility/JIT activation đã revoke? |
| Session | Phiên SSH/RDP/DB/admin UI có còn cho thao tác? |
| OAuth tokens | Access/refresh tokens hoặc token grants còn hợp lệ? |
| API key/PAT | Credential cá nhân có còn scope nhạy cảm? |
| Direct resource policy | Có đường quyền ngoài IAM không? |
| Effective-access test | Hành động bị cấm có thật sự bị chặn? |

Không phải mọi sản phẩm hỗ trợ hủy mọi JWT ngay. Phải đặt **revocation SLA** theo rủi ro và có containment khi không thể đạt hạn yêu cầu.

### 10.3. Không nhầm ID token và access token

Trong OIDC, **ID token** dành cho xác thực ở relying party, còn **OAuth access token** dành cho truy cập resource server. Khi kiểm tra quyền API, không được dùng ID token như credential thay access token. Kiểm chứng token cần issuer, audience, signature, expiration, binding và chính sách phù hợp.

## 11. Thu hồi qua PAM/JIT và đặc quyền

**Privileged Access Management (PAM)** có thể quản lý eligibility, activation, credential vault và brokered session. Khi reviewer REVOKE một quyền admin:

1. Gỡ **standing privileged grant** hoặc role rộng không còn cần.
2. Gỡ **PAM eligibility** để user không xin lại activation trái policy.
3. Thu hồi **JIT activation** còn mở nếu không hợp lệ.
4. Kết thúc hoặc giới hạn **privileged sessions** theo khả năng.
5. Đánh giá credential đã checkout, token/SSH key hoặc local admin account ngoài PAM.
6. Kiểm tra **privileged action thực tế** đã bị chặn.
7. Ghi owner, reason, timestamp và remediation nếu còn residual access.

### 11.1. JIT expiry khác revocation verified

Một JIT grant có `expiresAt=10:45` nhưng session kéo dài tới 11:00 vẫn thực thi `service:restart` thì **chưa đạt mục tiêu** nếu policy yêu cầu hết quyền lúc 10:45. Cần verify target enforcement chứ không chỉ state của ticket hoặc PAM UI.

### 11.2. Break-glass

Account break-glass có thể cần tồn tại để khôi phục khi IdP/PAM lỗi. Recertification phải đánh giá:
- Vì sao cần, ai là owner.
- Những người có khả năng dùng và cơ chế bảo vệ credential.
- Scope, alerting, logging, rotation, post-use review.
- Đường truy cập có phụ thuộc thành phần sẽ bị sự cố không.
- Mức quyền rộng nào có căn cứ, ngoại lệ có thời hạn/kỳ kiểm tra hay không.

**Không tự xóa break-glass account** chỉ vì ít dùng trong log, nhưng cũng không dùng “emergency” làm lý do giữ GlobalAdmin thường trực không kiểm soát.

## 12. Joiner: sửa grant sai trong đợt rà soát đầu tiên

Trong **Joiner**, HRIS/sponsor xác nhận identity và assignment có hiệu lực. Quyền baseline có thể provision tự động theo RBAC/ABAC; các quyền nhạy cảm cần approval.

Một review đầu kỳ có thể phát hiện:
- Tài khoản bị tạo trong sai tenant.
- Role `Admin` được gán thay `Viewer`.
- Quyền pre-start/onboarding vẫn còn sau ngày bắt đầu.
- Group cấp cho nhân viên trước đó được tái sử dụng.
- Account target trùng email nhưng không phải cùng người.

**Cách xử lý:** xác minh person–target binding, thu hồi grant sai theo nguồn có thẩm quyền, không khóa nhầm account dùng chung hoặc xóa toàn bộ user khi chỉ cần gỡ một role. Nếu identity liên kết sai, ưu tiên **identity correlation review và containment** trước thao tác phá hủy.

### 12.1. Pre-start và quyền có hiệu lực

Account có thể được tạo sớm để đăng ký MFA, nhưng production entitlements phải tuân thủ `effectiveFrom` và approval. Một review thấy role production active trước start date là cơ sở để **chặn/sửa entitlement sớm**, ngay cả khi nhân viên vẫn sẽ đến làm.

## 13. Mover: kiểm soát privilege accumulation

**Mover** là khi nhân viên đổi vai trò, phòng ban, vị trí hoặc dự án. Tình huống điển hình là **quyền mới được thêm, quyền cũ không được gỡ**.

### 13.1. KEEP / REMOVE / GRANT / REVIEW

| Loại | Ví dụ | Xử lý |
| --- | --- | --- |
| **KEEP** | `AllEmployees`. | Giữ nếu vẫn hợp lệ. |
| **REMOVE** | `OpsProductionOperator`. | Deprovision theo effectiveAt và verify. |
| **GRANT** | `FinanceReportReader`. | Cấp sau policy/approval/SoD. |
| **REVIEW** | `CloudAdmin`, JIT exception, quyền hỗ trợ dự án. | Kiểm tra scope, expiration và owner. |

Một quyết định REVOKE của campaign có thể trùng với **Mover event**. Cần tránh hai job xung đột và ghi được source event cho mỗi thay đổi.

### 13.2. Không chờ role mới được approve mới gỡ role cũ

Nếu quyền Operations đã hết căn cứ, IAM phải xử lý thu hồi theo policy **độc lập** với việc quyền Finance mới đang chờ phê duyệt. Việc bàn giao trong 7 ngày, nếu được phép, phải là **exception có owner, quyền hẹp và hạn**, không phải giữ `OpsAdmin` vô thời hạn.

### 13.3. SoD khi chuyển nhiệm vụ

Chuyển từ tạo thanh toán sang phê duyệt đòi hỏi xem `payment:create` và `payment:approve` có xung đột qua **role hierarchy, direct grants hoặc group**. Trước khi kích hoạt role mới, cần theo policy **thu hồi và xác minh quyền cũ**, hoặc có compensating controls/exception riêng khi được phép.

## 14. Leaver: không để campaign trì hoãn offboarding

Khi HRIS/contractor source xác nhận **Leaver** có hiệu lực, mục tiêu là chặn các đường truy cập phải bị chặn **đúng SLA**, không chờ kỳ recertification tiếp theo hay người rà soát bấm nút.

### 14.1. Hai workflow liên quan nhưng khác trigger

- **Scheduled recertification**: rà soát các quyền đã cấp theo kỳ hoặc dựa trên risk.
- **Event-driven deprovisioning**: xử lý ngay khi JML state yêu cầu, nhất là Leaver và Mover nhạy cảm.

Kết quả recertification có thể phát hiện lỗi offboarding cũ, nhưng **không thay thế nguồn Leaver có thẩm quyền**.

### 14.2. Leaver có thể có nhiều account

| Loại | Kiểm soát |
| --- | --- |
| IdP SSO account | Chặn login mới theo policy. |
| SCIM User/Group ở SaaS | Disable account/gỡ entitlements và readback. |
| Local app account | Disable independent login/credentials. |
| Privileged account | Revoke admin role, PAM eligibility và sessions. |
| OAuth tokens/PAT/API keys | Revoke/expire theo khả năng hệ thống. |
| SSH keys/certificates | Thu hồi, rotate hoặc chặn theo risk. |
| Delegations/temporary grants | Hủy grant còn active. |
| Service/workload ownership | Bàn giao owner, revoke quyền quản lý cá nhân. |

**Không xóa ngay mọi tài khoản dịch vụ** mà người nghỉ từng quản lý nếu workload vẫn phục vụ doanh nghiệp. Thu hồi quyền **cá nhân**, đánh giá credential bị lộ, chuyển owner và review quyền workload.

## 15. Service account và non-human identity trong recertification

**Service accounts, workload identities, service principals và automation identities** có thể không có nhân sự HR tương ứng nhưng lại giữ quyền rất rộng. Đợt review cần có **owner/team và mục đích sử dụng**.

### 15.1. Những câu hỏi review riêng cho workload

1. Workload còn chạy và có mục đích kinh doanh được xác nhận không?
2. Owner team/sponsor hiện là ai?
3. Quyền đã cấp có rộng hơn resource/action thật sự dùng không?
4. Có long-lived secret, PAT hoặc admin role không cần thiết?
5. Có thể dùng workload identity federation/managed identity hoặc credential ngắn hạn không?
6. Tài khoản có bị bỏ rơi khi người owner cũ nghỉ việc không?
7. Có phương án rollback và kiểm thử không làm gián đoạn nghiệp vụ?

### 15.2. Ví dụ giảm quyền workload

~~~text
Workload: billing-etl
Current: DatabaseSuperuser trên toàn DB
Actual job:
  - SELECT view hóa đơn của tenant-vn
  - INSERT bảng summary
  - Không tạo schema/user, không đọc secret khác

Recertification decision: REDUCE
Desired:
  - SELECT đúng view/tenant hợp lệ
  - INSERT đúng bảng
  - Không DDL, không manage roles, không read-all
  - Credential trust/owner/expiry rõ
~~~

Không xóa account đang chạy chỉ vì phát hiện overprivilege. Có thể **provision quyền hẹp trước**, kiểm thử tác vụ hợp lệ, rồi thu hồi superuser và xác minh không còn quyền ngoài scope.

### 15.3. Shared accounts

Với một account `root`/`Administrator` được nhiều người dùng, review row theo “owner account” chưa đủ xác định người đang thực sự sử dụng. Cần IAM-person binding qua PAM/session broker, credential rotation, audit và đánh giá chuyển sang named privileged accounts.

## 16. Exception, appeal và quyền bị tranh chấp

Một reviewer có thể đánh dấu REVOKE nhưng beneficiary cho rằng quyền vẫn cần. Quy trình hợp lý không phải tự động bỏ decision; thay vào đó cần:

- Lưu review decision và căn cứ.
- Cho owner/bên liên quan nộp **appeal/new access request** với business justification.
- Re-evaluate eligibility, least privilege, SoD và risk.
- Phê duyệt exception theo thẩm quyền, scope, effective time và compensating controls.
- Quy định thời điểm revocation có thể tạm hoãn **nếu chính sách cho phép**.
- Ghi audit ai đã cho giữ quyền và vì sao.
- Khi exception hết hạn, revoke và readback.

**Với Leaver hoặc quyền nguy hiểm đang bị lạm dụng, không trì hoãn containment chỉ vì có appeal đang chờ**, trừ trường hợp được quản trị rõ theo chính sách áp dụng.

### 16.1. Quyền cần thiết nhưng reviewer không đủ dữ liệu

Có thể yêu cầu bằng chứng, escalated review hoặc safe temporary limitation. Không suy `KEEP` từ việc reviewer không trả lời, đặc biệt với quyền admin. Với quyền có tác động lớn, có thể áp **giới hạn/disable tạm** khi nguồn authority đủ căn cứ và policy cho phép, đồng thời bảo vệ tính sẵn sàng nghiệp vụ.

## 17. Thiết kế state machine để không đóng sớm

Một revocation record nên phản ánh các giai đoạn kỹ thuật:

| State | Ý nghĩa | Không được hiểu là |
| --- | --- | --- |
| `REVIEW_DECIDED_REVOKE` | Certifier đã quyết định loại quyền. | Target đã gỡ. |
| `PENDING_SCOPE_VALIDATION` | Chưa xác minh identity, target và nguồn grant. | Có thể xóa theo email ngay. |
| `READY_FOR_EXECUTION` | Desired state, scope và owner đã được xác định. | Quyền đã mất. |
| `REVOKING` | Đang thực thi trên IdP/SCIM/app/PAM. | API result cuối cùng. |
| `PENDING_PROPAGATION` | Source đã gỡ, chờ sync/cache/target. | Được Verified ngay. |
| `PENDING_RECONCILIATION` | Chờ readback và kiểm tra effective access. | Mọi đường đã chặn. |
| `VERIFIED_REVOKED` | Các tiêu chí thu hồi bắt buộc đã được xác minh. | Mọi access khác của user đều phải mất. |
| `ALREADY_COMPLIANT` | Target đã không còn grant lúc kiểm tra. | Không cần chứng minh state. |
| `REMEDIATION_REQUIRED` | Còn quyền hoặc lỗi cần owner xử lý. | Decision được phép bỏ qua. |
| `EXCEPTION_ACTIVE` | Exception có authority, scope/time hợp lệ. | Giữ quyền vĩnh viễn. |
| `SUPERSEDED` | Quyết định bị thay thế theo quy trình có audit. | Một batch cũ được tiếp tục chạy tùy ý. |

Đây là **mô hình minh họa**, không phải bộ status chuẩn của SCIM hay IGA. Một sản phẩm có thể có state khác nhưng cần **phân biệt quyết định, thực thi và verification**.

### 17.1. Sơ đồ chuyển trạng thái

~~~mermaid
stateDiagram-v2
    [*] --> REVIEW_DECIDED_REVOKE
    REVIEW_DECIDED_REVOKE --> PENDING_SCOPE_VALIDATION
    PENDING_SCOPE_VALIDATION --> READY_FOR_EXECUTION: binding + owner verified
    PENDING_SCOPE_VALIDATION --> REMEDIATION_REQUIRED: ambiguous identity/source
    READY_FOR_EXECUTION --> REVOKING
    REVOKING --> PENDING_PROPAGATION: source updated
    REVOKING --> REMEDIATION_REQUIRED: connector/permission failure
    PENDING_PROPAGATION --> PENDING_RECONCILIATION
    PENDING_RECONCILIATION --> VERIFIED_REVOKED: desired == actual
    PENDING_RECONCILIATION --> REMEDIATION_REQUIRED: residual access
    REMEDIATION_REQUIRED --> READY_FOR_EXECUTION: remediation plan approved
    VERIFIED_REVOKED --> [*]
~~~

### 17.2. Đóng campaign khác đóng remediation

Một campaign recertification có thể **hoàn tất tất cả decisions**, nhưng còn 12 revocation tasks chưa Verified. Báo cáo cần tách:
- `reviewCompletionRate`.
- `revocationExecutionRate`.
- `verifiedClosureRate`.
- `overdueResidualAccessCount`.

Không tuyên bố “100% access certified” như bằng chứng 100% quyền đã được thu hồi đúng hạn.

## 18. Idempotency, concurrency và xử lý sự kiện đua

Các hệ thống IdP, SCIM và application API thường bất đồng bộ. Một thao tác thu hồi cần có khả năng **retry an toàn**, chống ghi nhầm hoặc thay đổi quyền ngoài ý định.

### 18.1. Tình huống dễ sai

| Tình huống | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Connector timeout sau khi target đã gỡ membership. | Retry có thể báo lỗi không tồn tại. | Readback state trước retry; coi target đã đúng là success theo workflow. |
| Một reviewer REVOKE trong khi manager approve quyền mới khác. | Gỡ nhầm assignment mới hợp lệ hoặc quyền bị thêm lại. | Phân biệt grant source và policy version; re-evaluate desired state. |
| Mover event và campaign cùng thu hồi group. | Hai job cạnh tranh hoặc gửi patch lặp. | Idempotency key, target state reconciliation. |
| Group thay đổi membership đồng thời. | PUT snapshot cũ xóa member người khác. | PATCH chọn phần tử, concurrency/ETag nếu hỗ trợ. |
| Account email được tái sử dụng. | Thu hồi nhầm người mới. | Stable target ID và authoritative identity binding. |
| Leaver tới hạn khi exception đang pending. | Người đã nghỉ vẫn giữ role. | JML state thắng theo policy; containment và hủy task cũ. |
| Directory sync tự thêm user lại vào dynamic group. | Quyền trở lại sau một giờ. | Sửa nguồn policy/attribute; theo dõi re-grant. |
| Reviewer sửa quyết định sau khi lệnh chạy. | Workflow mâu thuẫn. | Immutable decision events, supersede + new grant request. |

### 18.2. Nguyên tắc desired-state reconciliation

Một vòng lặp khái niệm:

~~~text
for each revocationTask:
    verify task targets a current identity and target account
    desired = evaluateCurrentAuthorizedAccess(
        lifecycle, approvedAssignments, reviewDecision, exceptions
    )

    actual = readTargetGrantsAndRelevantSessions(task.target)

    if actual already meets desired:
        record ALREADY_COMPLIANT or VERIFIED_REVOKED with evidence
        continue

    plan = calculateScopedRemovals(actual, desired, task.reviewScope)
    validate owner, SoD, target version, concurrency
    execute changes through authoritative source
    read target state again
    if effectiveAccessMatchesPolicy:
        record VERIFIED_REVOKED
    else:
        record REMEDIATION_REQUIRED with owner and deadline
~~~

Đây là **pseudocode ý tưởng**, không phải thuật toán có thể chạy trực tiếp. Nhiều target không cung cấp API để liệt kê mọi credential/session hoặc test mọi permission; phải thiết kế evidence phù hợp từng hệ thống, không giả vờ kiểm chứng tuyệt đối.

### 18.3. Không dùng PUT mảng group từ snapshot cũ

Nếu group có 50 thành viên và một reviewer yêu cầu gỡ 1 người, gửi `PUT Group` thay toàn bộ `members` bằng dữ liệu snapshot cũ có thể xóa nhầm người mới hoặc thêm lại người vừa được gỡ. Nếu provider hỗ trợ, dùng **PATCH targeted remove**; khi phải replace, cần **version/If-Match, reconciliation và readback**.

### 18.4. Không retry vô hạn

Với `401/403` cần kiểm tra credential/scope; `429` cần backoff và rate limits; timeout/5xx cần kiểm tra trạng thái target trước retry. Có **retry budget, idempotency, dead-letter/remediation queue** và owner escalation.

## 19. Kiểm chứng quyền đã mất: đọc gì và thử gì?

### 19.1. Hai lớp kiểm chứng

**Configuration readback**: grant/account/group/token state trên target phản ánh desired state.

**Effective-access verification**: một hành động **trước đây được cấp** nay **bị từ chối đúng theo policy**, không phải chỉ mất trong UI.

| Loại quyền | Readback thích hợp | Kiểm chứng bổ sung |
| --- | --- | --- |
| SCIM Group member | `GET /Groups/{id}` và members tương ứng. | App role mapping/effective permission. |
| IdP group | Group membership ở IdP và target sync. | Claim/session mới, app access. |
| Local app role | App-specific permission API/admin state. | Từ chối hành động ngoài scope. |
| Cloud resource grant | IAM policy/role binding hiệu lực. | Resource-level authorization test được phép. |
| PAM/JIT | Eligibility, activation, session state. | Admin action không còn hoạt động sau revocation. |
| API key/PAT | Credential state/revocation log. | Test an toàn với key đã được chỉ định, nếu policy cho phép. |
| Workload role | Service principal/DB grants và owner. | Job hợp lệ còn hoạt động, hành động quá quyền bị từ chối. |

**Không thử đăng nhập trái phép, lấy credential của người khác hoặc gửi request phá hủy chỉ để “kiểm chứng”.** Sử dụng sandbox, tài khoản kiểm thử được ủy quyền, policy simulation, log target và negative tests có kiểm soát. Với quyền sản xuất nhạy cảm, chọn bằng chứng phù hợp để không gây gián đoạn hay rò rỉ dữ liệu.

### 19.2. Kiểm tra cả positive và negative

Khi hạ `GlobalAdmin` xuống `ReportReader`:
- **Positive:** user vẫn đọc được báo cáo thuộc scope hợp lệ.
- **Negative:** không thể sửa role, không đọc được dữ liệu ngoài tenant và không thực hiện hành động admin.
- **Session:** token/phiên cũ không cho bypass quyết định thu hồi.
- **Timing:** quyền phải bị chặn trước SLA/effective deadline.

Một quy trình chỉ kiểm tra `403` tăng lên có thể gây **over-revocation** và gián đoạn nhiệm vụ hợp lệ.

## 20. Audit evidence và truy vết quyết định

Mỗi revocation task nên có thể giải thích:

- **Ai** quyết định REVOKE và theo authority nào?
- **Quyền gì** trong tenant/resource nào?
- **Tại sao** không còn căn cứ: Mover, Leaver, stale entitlement, SoD, privilege risk?
- **Khi nào** quyết định và mốc phải hoàn tất?
- **Nguồn grant nào** được sửa?
- **Executor/connector** nào đã thực thi?
- **Target** báo gì, có lỗi/propagation delay không?
- **Actual effective access** đã khớp policy chưa?
- **Nếu chưa**, owner/remediation/SLA là gì?

### 20.1. JSON audit record minh họa

~~~json
{
  "campaignId": "AR-2026-Q4-FINANCE",
  "reviewDecisionId": "DEC-4281",
  "revocationTaskId": "REV-2026-0881",
  "decision": {
    "type": "REVOKE",
    "reviewerIdentityId": "person-320",
    "approvedAuthorityRef": "finance-app-owner",
    "decisionTime": "2026-11-23T09:00:00+07:00",
    "reasonCode": "MOVER_OLD_ACCESS"
  },
  "subject": {
    "iamIdentityId": "person-2048",
    "targetAccountId": "u-9008"
  },
  "target": {
    "system": "analytics-app",
    "tenant": "tenant-vn",
    "grantType": "GROUP_MEMBERSHIP",
    "groupId": "g-prod-23"
  },
  "execution": {
    "sourceOfAuthority": "analytics-scim",
    "idempotencyKey": "rev-2026-0881-v1",
    "result": "PATCH_ACCEPTED",
    "requestId": "scim-patch-901"
  },
  "verification": {
    "groupMembership": "ABSENT",
    "effectiveAccess": "DENIED_AS_REQUIRED",
    "verifiedAt": "2026-11-23T09:05:00+07:00",
    "status": "VERIFIED_REVOKED"
  }
}
~~~

**Đây là schema nội bộ minh họa**, không phải chuẩn audit của SCIM/IGA. Trường `effectiveAccess` chỉ được ghi là Verified khi có evidence theo thiết kế. Không ghi access token, password, OTP, private key, secrets hoặc PII không cần thiết vào event.

### 20.2. SoD và tính toàn vẹn log

Người quản trị quyền không nên tùy tiện thay review decision hoặc xóa log sau khi cấp quyền cho mình. Cần phân tách approver/executor/auditor khi rủi ro yêu cầu, bảo vệ immutable/event history, audit trail của delegation và exceptional overrides.

## 21. Metrics và cách đo closure thực chất

| Chỉ số | Định nghĩa gợi ý | Cạm bẫy |
| --- | --- | --- |
| **Review completion rate** | Review rows có decision hợp lệ / tổng rows cần review. | Không đo đã thu hồi. |
| **Revoke decision rate** | Decisions REVOKE / quyết định hoàn tất. | Cao chưa chắc tốt; phụ thuộc chất lượng baseline. |
| **Execution success rate** | Tasks có thao tác target thành công / tasks cần chạy. | HTTP 200 không chứng minh quyền mất. |
| **Verified revocation rate** | Tasks đã qua readback và kiểm chứng / tasks cần revoke. | Không đếm `ALREADY_COMPLIANT` nếu chưa có evidence. |
| **Revocation latency** | Từ effective due time đến khi actual access chặn theo policy. | Không lấy thời điểm reviewer bấm nút làm thời điểm đã chặn. |
| **Overdue privileged revocations** | Đặc quyền vượt SLA chưa Verified. | Cần phân tầng risk/containment. |
| **Re-grant recurrence** | Grants bị revoke nhưng xuất hiện lại trái desired state. | Có thể do dynamic group hoặc source mapping sai. |
| **Access drift count** | Grants hiện tại ngoài desired state sau review. | Không bỏ direct grants, nested/privileged roles. |
| **Incorrect revocation incidents** | Gỡ nhầm người/quyền hợp lệ. | Không chỉ tối ưu số lượt REVOKE. |
| **Unowned service identities** | Non-human accounts không có owner hợp lệ. | Không đồng nghĩa nên xóa hết workloads. |
| **Unverified session/token residual** | Token/phiên còn khả dụng sau revoke deadline. | Không chỉ kiểm tra login IdP. |
| **Exception overdue count** | Quyền ngoại lệ vượt expiry chưa được xử lý. | Không biến exception thành quyền thường trực. |

### 21.1. Phân biệt SLA và thời gian chờ kỹ thuật

Có thể theo dõi riêng:
- `decisionToExecution` — reviewer chọn REVOKE tới khi connector gửi lệnh.
- `executionToPropagation` — source cập nhật tới target sync.
- `propagationToVerification` — target cập nhật tới khi kiểm chứng.
- `deadlineToClosure` — quyền đã bị chặn đúng hạn hay chưa.

Đặc quyền cao hoặc Leaver thường cần **SLA chặt hơn** entitlement đọc ít nhạy cảm; không có một ngưỡng thời gian đúng cho mọi doanh nghiệp. **Yêu cầu tổ chức và khả năng target** phải quyết định deadline và containment.

## 22. Tình huống xuyên suốt: quyết định REVOKE sau Mover

**Bối cảnh:** Doanh nghiệp dùng HRIS, IAM/IGA, IdP/SSO và ứng dụng Analytics hỗ trợ SCIM. Lan có IAM identity `person-2048`, account Analytics `u-9008`. Trước đây Lan thuộc Operations và có membership `ops-prod-deployers`. HRIS đã ghi nhận Lan chuyển Finance, nhưng kỳ review phát hiện group cũ vẫn còn.

### 22.1. Review decision

App owner nhìn:
- Lan hiện ở Finance.
- Grant `ops-prod-deployers` không còn assignment Operations hợp lệ.
- Role có permission triển khai production.
- Không có exception handover còn hiệu lực.

App owner quyết định **REVOKE**, gắn decision ID, target Group ID và deadline theo risk.

### 22.2. Lập kế hoạch

IAM xác minh:
- `person-2048` liên kết với `u-9008` đúng target/tenant.
- Grant được quản lý bởi SCIM/IdP nào.
- Có direct cloud role hoặc nested group nào cho deploy không?
- Có PAM JIT activation, access token/SSH key đang hiệu lực không?
- Có Finance entitlement nào vẫn cần giữ?

Mục tiêu: **mất production deploy**, **giữ Finance report read**.

### 22.3. Thực thi

Connector gỡ membership theo source có thẩm quyền, không dùng snapshot PUT toàn bộ Group. Nếu dynamic group rule vẫn còn cho Lan vào nhóm, phải sửa **attribute/policy source** đúng quy trình. Không xóa nhóm của cả đội.

### 22.4. Xác minh

- IdP/source group không còn Lan.
- SCIM target Group membership absent.
- App/cloud effective deploy permission không còn qua đường khác.
- Token/session/PAM grants được kiểm tra theo risk.
- Lan vẫn dùng được Finance Reader đúng scope.
- Evidence có owner/timestamp, remediation mở nếu có drift.

### 22.5. Nếu quyền xuất hiện lại

Hai ngày sau, reconciliation phát hiện direct grant `production:deploy` được cấp lại bởi automation cũ. Đây là **re-grant recurrence**, không thể sửa bằng cách lặp mãi PATCH Group. Cần tìm **source automation/policy mapping**, ngăn tiếp tục provision trái desired state và audit tại sao role được thêm lại.

### 22.6. Bài học

**Review đúng không đủ nếu enforcement sai.** Grant source, identity binding, role hierarchy, session/token và automation re-grant phải được xét đồng bộ để quyền đã bị thu hồi **không tự xuất hiện lại**.

## 23. Checklist vận hành và bài tập tự kiểm tra

### 23.1. Checklist đóng một quyết định REVOKE

- [ ] Decision có campaign ID, reviewer authority, scope, timestamp và reason.
- [ ] Biết chính xác beneficiary IAM identity và target account/tenant.
- [ ] Phân biệt grant-specific revoke với effective-access revoke.
- [ ] Kiểm tra review snapshot và các HR/JML assignments hiện hành.
- [ ] Tìm direct role/group, nested/dynamic membership, role hierarchy và resource policy.
- [ ] Kiểm tra quyền hợp lệ từ assignment khác trước khi gỡ.
- [ ] Dùng đúng source of authority để không bị re-provision.
- [ ] Nếu là REDUCE, quyền hẹp hợp lệ được provision/test trước cutover khi phù hợp.
- [ ] Xét privileged/PAM eligibility, activation và active sessions.
- [ ] Xét OAuth/PAT/API keys, local accounts, credential và IdP/SSO sessions theo risk.
- [ ] SCIM/API operation có quyền, target ID, idempotency và concurrency safeguards.
- [ ] Không coi connector HTTP 200 là bằng chứng quyền đã mất.
- [ ] Readback tài nguyên và check effective permission ở target.
- [ ] Positive tests bảo vệ quyền hợp lệ; negative tests chặn action không còn căn cứ.
- [ ] Khi target lỗi, có owner, retry budget, containment và remediation SLA.
- [ ] Mover revoke track không chờ grant track; Leaver xử lý theo authoritative event ngay.
- [ ] Exception có approver, scope, expiration và audit, không giữ vô hạn.
- [ ] Service/workload identity có owner/lifecycle riêng, không bị xóa vì owner người nghỉ.
- [ ] Ghi đủ decision, source, executor, action, evidence và verified timestamp.
- [ ] Chỉ đánh dấu `VERIFIED_REVOKED` khi tiêu chí required target state đã đạt.
- [ ] Reconciliation sau review phát hiện direct grants và re-grant recurrence.

### 23.2. Bài tập A — Thu hồi role nhưng giữ quyền đọc hợp lệ

Lan có `ReportReader` trực tiếp từ project A và `ReportEditor` từ project B, trong khi Editor kế thừa Reader. Reviewer REVOKE grant project A. Sau thao tác, Lan vẫn đọc được báo cáo. Đây có phải lỗi không? Hãy phân biệt **grant-specific** và **effective-access-specific** revocation.

### 23.3. Bài tập B — SCIM Group PATCH không giải quyết quyền direct

IdP đã gỡ group `ops-prod-deployers`, SCIM target báo membership absent, nhưng Lan vẫn deploy production qua cloud resource policy. Hãy liệt kê những **grant paths** cần kiểm tra và target evidence để đóng task.

### 23.4. Bài tập C — JWT cũ sau revoke

Một access token chứa role `ReportExporter` có thời hạn còn 40 phút. IAM đã gỡ role tại target nhưng resource server chỉ kiểm chữ ký/`exp`. Vì sao decision REVOKE chưa thành công theo nghĩa **effective-access revocation**? Thiết kế biện pháp ngắn hạn và lâu dài.

### 23.5. Bài tập D — Mover và review snapshot cũ

Campaign chốt dữ liệu đầu tháng, reviewer REVOKE quyền `project-alpha:read` vì người dùng chuyển bộ phận. Trong lúc chờ, người dùng được approve một assignment mới hợp lệ vào project-alpha. Làm sao thu hồi **grant cũ** mà không xóa quyền mới đúng căn cứ?

### 23.6. Bài tập E — Leaver không chờ quarterly review

HRIS phát Leaver có hiệu lực ngay trong khi kỳ review kết thúc tháng sau. IAM nên kích hoạt những bước nào? Tại sao không được chờ reviewer xác nhận lại để disable IdP, local account và PAM sessions?

### 23.7. Bài tập F — Service account owner nghỉ

Workload `billing-etl` giữ quyền `DatabaseSuperuser`. Owner nhân viên nghỉ việc nhưng dịch vụ còn chạy. Hãy thiết kế cách **bàn giao owner, kiểm tra credential exposure, giảm quyền DB đúng bảng và scope, test job hợp lệ, rồi revoke admin**.

### 23.8. Bài tập G — Dynamic group tự thêm quyền

Reviewer quyết định REVOKE, connector gỡ membership, nhưng ngày hôm sau IdP dynamic rule thêm user lại vì `department=Operations` đã cũ. Nguồn nào phải được cập nhật? Ai có trách nhiệm điều tra stale attribute và re-provision?

### 23.9. Bài tập H — PUT snapshot cũ làm hỏng group

Connector lấy danh sách 50 member lúc 09:00, reviewer muốn gỡ một người, rồi gửi PUT danh sách 49 member lúc 09:20. Trong khoảng đó owner đã thêm hai thành viên hợp lệ. Vì sao thao tác có thể làm mất membership của người khác? Cách dùng PATCH, ETag/If-Match và readback ra sao?

### 23.10. Bài tập I — Đo chất lượng campaign

Một campaign có 100% rows đã được reviewer quyết định, nhưng chỉ 80% REVOKE tasks có target readback và 10 quyền đặc biệt đã quá hạn. Có thể báo cáo “đã thu hồi 100% quyền không cần thiết” không? Hãy thiết kế dashboard riêng cho **decision, execution, verification và overdue residual access**.

**Điểm cần ghi nhớ:** **Thu hồi quyền trong Access recertification** là quá trình **khép kín** từ quyết định của certifier tới **đúng grant/đường cấp quyền** tại target, không phải thao tác đánh dấu trong bảng review. Phải xác minh **identity/account binding, role/group/direct grants, RBAC inheritance, ABAC context, IdP/SSO, SCIM, PAM, credential/session/token và tình trạng JML hiện hành**, tránh xóa nhầm quyền hợp lệ hoặc để nguồn khác tự cấp lại quyền đã bị thu hồi. Chỉ khi **desired state khớp actual effective access** theo tiêu chí phù hợp và có **readback, audit cùng remediation ownership**, quyết định REVOKE mới được xem là hoàn tất.

