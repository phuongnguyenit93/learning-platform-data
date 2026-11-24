# Review theo application trong IAM: rà soát quyền truy cập theo từng ứng dụng

**Review theo application (application-centric access review)** là hoạt động tập hợp và đánh giá toàn bộ các danh tính, tài khoản, vai trò, quyền trực tiếp và đường truy cập đang có hiệu lực đối với **một ứng dụng hoặc một hệ thống nghiệp vụ cụ thể**. Người có thẩm quyền của ứng dụng xem xét ai còn cần truy cập, phạm vi quyền có đúng nhiệm vụ hay không, những ngoại lệ có hợp lệ không, rồi quyết định **giữ, điều chỉnh, thu hồi hoặc điều tra**. Kết quả chỉ đáng tin nếu những thay đổi được **thực thi và xác minh tại ứng dụng**, không dừng ở việc người duyệt bấm nút trong một chiến dịch IAM.

Bài **“Review theo application”** thuộc chương **Access review**, trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module nghiên cứu vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi đổi vai trò hoặc nghỉ việc. Một application review phải phối hợp **HRIS, IGA, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán**, nhất là để tìm **quyền truy cập tồn dư** không còn phù hợp với trạng thái nhân sự hiện tại.

**Tình huống dẫn nhập:** Công ty dùng ứng dụng Finance Portal để đọc và duyệt hóa đơn. Danh sách nhóm trong IdP cho thấy nhân viên An đã rời nhóm Finance. Nhưng Finance Portal còn một vai trò Approver được cấp trực tiếp và một phiên đăng nhập cục bộ chưa hết hạn; tài khoản dịch vụ invoice-sync cũng có quyền đọc dữ liệu production mà không còn chủ sở hữu. Nếu chỉ rà soát nhóm IdP, chiến dịch có thể kết luận “không còn quyền” dù ứng dụng vẫn chấp nhận thao tác. Review theo application cần tìm, phân loại và kiểm chứng các đường truy cập đó.

## 1. Tư duy application-centric: ứng dụng là đơn vị rà soát

Một **application** trong phạm vi review không nhất thiết là một màn hình web. Nó có thể bao gồm:

- Giao diện web/mobile và API backend.
- SSO/OIDC/SAML configuration cùng các phiên đăng nhập được tạo từ đó.
- Tài khoản và vai trò **cục bộ** trong ứng dụng.
- Các **tenant, workspace, project, environment** của cùng sản phẩm.
- Groups và entitlements đồng bộ qua directory, IGA hoặc SCIM.
- Direct ACL, delegated access, quyền chia sẻ, API keys và personal access tokens.
- Service accounts, OAuth clients, workloads, integrations và các jobs chạy nền.
- Quyền quản trị ứng dụng, cấu hình policy, xuất dữ liệu và tài khoản khẩn cấp.

### Ba câu hỏi của một application review

1. **Ai đang có thể truy cập?** Không chỉ user trong IdP mà cả local accounts, external users, contractors, bots và service principals.
2. **Họ có thể làm gì?** Read, create, export, approve, delete, administer, impersonate, quản lý secrets hoặc thay đổi phân quyền; quyền được giới hạn bởi tenant/resource/context nào?
3. **Có còn nên được làm như vậy không?** Đối chiếu công việc hiện tại, owner approval, trạng thái HRIS, SoD, expiry và chính sách least privilege.

Review theo ứng dụng khác với việc hỏi mỗi quản lý “nhân viên của anh/chị còn cần hệ thống này không?”. **Manager có thể xác nhận nhu cầu công việc**, nhưng **application owner/data owner** thường hiểu cấu trúc role, mức nhạy cảm dữ liệu và hậu quả khi giữ quyền quá rộng.

## 2. Phân biệt application review với các kiểu access review khác

| Kiểu review | Điểm bắt đầu | Câu hỏi chính | Khi nào đặc biệt hữu ích |
| --- | --- | --- | --- |
| **Theo application** | Một ứng dụng và các tài khoản/entitlements bên trong. | Ai đang có quyền gì trong ứng dụng này? | Finance, CRM, HR, ERP, SaaS có vai trò/phân quyền riêng. |
| **Theo user/identity** | Một người hoặc danh tính kỹ thuật. | Chủ thể này có những quyền gì trên toàn hệ thống? | Mover, Leaver, nhân viên có nhiều đặc quyền. |
| **Theo entitlement/role** | Một role hoặc permission cụ thể. | Ai có quyền nhạy cảm này và vì sao? | Admin role, export dữ liệu, payment approval. |
| **Theo nhóm/quản lý** | Người trực thuộc một manager. | Ai còn làm những công việc cần quyền tương ứng? | Recertification nhân sự định kỳ. |
| **Theo SoD/risk** | Một tập quyền xung đột hay phơi bày cao. | Có tổ hợp quyền nào bị cấm hoặc thiếu kiểm soát? | Maker-checker, tài chính, quản trị IAM. |
| **Theo workload** | Một service/app integration. | Principal kỹ thuật có owner và quyền tối thiểu không? | OAuth clients, CI/CD, cloud service accounts. |

Các góc nhìn **bổ sung**, không thay thế nhau. Một application review có thể chứng minh quyền trong CRM đã đúng nhưng không tự chứng minh người dùng đó không còn đặc quyền thừa trong Vault hoặc CI/CD.

## 3. Ranh giới ứng dụng và nguồn sự thật

Trước khi review, cần xác định **application boundary**: hệ thống nào là đích, những đường truy cập nào do nó hoặc một hệ thống tích hợp cho phép, và quyền nào có nguồn quản lý khác.

~~~mermaid
flowchart TD
    HR["HRIS / Contractor Registry<br/>Joiner–Mover–Leaver"] --> IGA["IGA / IAM<br/>Approved access & campaigns"]
    DIR["Directory / IdP<br/>Identity + groups"] --> IGA
    IGA --> CONN["SCIM / API connectors"]
    CONN --> APP["Ứng dụng đích<br/>Accounts + roles + ACL"]
    DIR --> SSO["SSO / OIDC / SAML"]
    SSO --> APP
    WORK["Service accounts / OAuth clients"] --> APP
    APP --> API["API / Resource Server<br/>PEP & business authorization"]
    API --> EV["Audit & effective access"]
    APP --> EV
    EV --> CAM["Application access review"]
    IGA --> CAM
    CAM --> FIX["KEEP / CHANGE / REVOKE / INVESTIGATE"]
    FIX --> CONN
~~~

| Loại thông tin | Nguồn có thẩm quyền theo thiết kế | Vai trò khi review |
| --- | --- | --- |
| **Employment status/effectiveAt** | HRIS hoặc nguồn hợp đồng được duyệt. | Leaver, suspended, pre-hire hay contractor expiry có còn đủ điều kiện? |
| **Business purpose/approval** | IGA, business owner và hệ thống phê duyệt. | Vì sao quyền còn cần? Có hết hạn? |
| **Stable subject identity** | Identity registry/IdP, mapping đã xác minh. | Liên kết đúng tài khoản giữa HRIS, directory và application. |
| **Application-local roles** | API/admin interface của ứng dụng. | Quyền thực sự đang có, kể cả quyền ngoài SCIM. |
| **Resource ownership/tenant** | Database/tài nguyên hoặc catalog được quản trị. | Quyền có đúng đối tượng và không vượt tenant? |
| **SCIM users/groups** | Target application và connector mappings. | Desired state có được provision đúng và readback chưa? |
| **Sessions/tokens** | IdP, Authorization Server, SP và Resource Server. | Quyền cũ có còn thực thi dù account/role đã bị gỡ? |
| **Workload credentials** | Vault, IAM workload manager, client registry. | Có service identity vô chủ hoặc quyền ngoài mục đích? |

**Không dùng email làm khóa ghép duy nhất**: email có thể đổi, được tái sử dụng hoặc tồn tại nhiều bản ghi ở các tenant. Nên dùng **stable subject ID** và **target account ID** có mapping đáng tin để tránh duyệt nhầm hoặc thu hồi nhầm người.

## 4. Kiểm kê những gì phải đưa vào review

Một danh sách Users đơn giản thường chưa đủ. Nên tạo **application inventory** có:

| Thành phần | Câu hỏi rà soát | Ví dụ sai lệch |
| --- | --- | --- |
| Internal users | Có quan hệ làm việc hiện hành? Đúng tenant? | Nhân viên đã Leaver nhưng app account ACTIVE. |
| External/guest users | Sponsor/contract còn hiệu lực? | Guest không owner, chưa có ngày hết hạn. |
| Local accounts | Có được quản trị ngoài SSO/SCIM không? | Tài khoản local admin không thuộc IGA. |
| Roles/role hierarchy | Role chứa những actions nào? Có kế thừa? | “Viewer” được sửa thành “Exporter” sau đợt trước. |
| Groups/nested groups | Quyền được cấp gián tiếp qua đâu? | Gỡ nhóm IdP nhưng nested app group còn giữ quyền. |
| Direct grants/ACL | Quyền cấp thẳng cho user/resource? | Shared folder quyền ghi còn sau Mover. |
| Temporary/JIT entitlements | Expiry và activation có hiệu lực không? | Phiên JIT hết hạn nhưng admin role còn active. |
| Administrative accounts | Ai có thể cấp quyền cho người khác? | Self-grant, global admin đứng thường trực. |
| API keys/PATs | Ai sở hữu, dùng scope nào, còn hợp lệ? | PAT tồn tại sau khi user bị disable. |
| OAuth/SAML integrations | Client/app registrations, token audience, cert/trust. | Client không owner hoặc scope production quá rộng. |
| Workload/service identities | Owner, namespace, secret/key, runtime. | Job đã ngừng nhưng service account còn wildcard. |
| Resource scopes | Tenant, project, invoice class, document owner. | Role hợp lệ nhưng mở chéo tenant. |
| Session/cache paths | App local session, API auth cache, presigned links. | Quyền mới bị gỡ nhưng session cũ vẫn truy cập. |
| Audit/telemetry | Có thể chứng minh usage và allow/deny? | Một export worker không ghi log authorization. |

### Phạm vi review phải đủ cụ thể

Ví dụ ứng dụng có ba tenant và hai môi trường:

~~~yaml
campaignId: finance-app-review-2026-q4
application:
  appId: finance-portal
  tenantScope: [tenant-vn, tenant-sg]
  environments: [production]
include:
  - direct_and_inherited_roles
  - local_accounts
  - privileged_actions
  - external_users
  - workload_and_service_accounts
  - group_and_acl_grants
  - token_and_session_exposure_review
exclude:
  - environment: sandbox
    reason: separate_campaign
owner: finance-application-owner
status: PREPARATION
~~~

Đây là **YAML minh họa**, không phải schema của một nền tảng IGA. Phần loại trừ cần **lý do và chiến dịch chịu trách nhiệm**, không bỏ ứng dụng khó kết nối khỏi số liệu mà không công bố.

## 5. Người tham gia và trách nhiệm phê duyệt

Một chiến dịch review theo ứng dụng cần tách **người xác nhận nhu cầu** khỏi **người thực thi thay đổi và người kiểm chứng**.

| Vai trò | Trách nhiệm | Điểm cần tránh |
| --- | --- | --- |
| **Application owner** | Xác nhận phạm vi ứng dụng, role catalog, owner và mức rủi ro. | Không thể tự hiểu mọi nhu cầu của từng nhân viên nếu thiếu manager. |
| **Business/data owner** | Xác định ai được thao tác trên dữ liệu/tài nguyên nhạy cảm. | Không phê duyệt theo tên role mà không biết action thực. |
| **Line manager/sponsor** | Xác nhận nhu cầu làm việc và thời hạn nhân sự/đối tác. | Không tự cấp global admin ngoài thẩm quyền. |
| **IAM/IGA operator** | Tạo campaign, thu dữ liệu, định tuyến và điều phối remediation. | Không tự đánh dấu KEEP mọi quyền thay owner. |
| **Security/SoD reviewer** | Đánh giá quyền nhạy cảm, SoD, ngoại lệ và dấu hiệu lạm dụng. | Không dùng risk score làm lý do bỏ qua hard policy. |
| **Application administrator/connector** | Cấp/gỡ quyền được duyệt trên đúng target. | Không tự mở rộng scope hoặc chỉnh dữ liệu approval. |
| **Verifier/auditor** | Kiểm readback, quyền hiệu lực, evidence và ngoại lệ. | Không chỉ dựa vào HTTP success hoặc email xác nhận. |

**Self-certification** cho quyền admin của chính người duyệt thường cần cấm hoặc có **independent reviewer** theo mức rủi ro. Nếu owner ứng dụng đã nghỉ/chuyển công tác, campaign cần cơ chế **reassignment có kiểm soát**, không auto-approve vì không ai nhận.

## 6. Mô hình đối tượng cần chứng nhận: account, role, entitlement

Một application review nên có **đơn vị quyết định** rõ ràng. Ví dụ:

\[
\text{ReviewItem} =
(\text{Application}, \text{Account}, \text{Entitlement}, \text{Scope}, \text{Validity})
\]

| Đơn vị | Ví dụ | Điều phải kiểm |
| --- | --- | --- |
| App-level access | Người dùng có quyền truy cập Finance Portal. | Còn nhu cầu dùng ứng dụng? |
| Role membership | person-4821 có FINANCE_READER. | Role đúng công việc và chỉ mang các actions cần thiết? |
| Privileged entitlement | FINANCE_APPROVER trong tenant VN. | SoD, hạn mức, authority, step-up và expiry? |
| Resource-specific ACL | READ của invoice project-7. | Còn thuộc dự án? Resource owner có phê duyệt? |
| Temporal grant | Admin JIT trong một cửa sổ 60 phút. | Quyền có hết hạn đúng và được revoke? |
| Workload identity | invoice-sync client được invoice.read. | API/tenant/scope phù hợp, có owner/credential policy? |

**Review “người này còn cần app không?” không đủ** khi ứng dụng có nhiều mức quyền. Người cần đăng nhập để đọc dữ liệu không nhất thiết cần export, approve hoặc quản lý user.

### Ghi nhận nguồn grant

Nếu quyền phát sinh từ **group**, **ACL** và **role direct** cùng lúc, cần lưu cả ba nguồn. Khi reviewer chọn REVOKE, chỉ xóa một group chưa chắc giảm **effective access**; quyền còn có thể được cấp từ nguồn khác.

## 7. Chuẩn hóa dữ liệu và bảo đảm tính hiện hành

Một campaign đáng tin cần ghép đúng **desired access** và **actual/effective access** tại một mốc review.

~~~text
Desired state:
  HRIS / contract status
  Business task and approvals
  IGA roles, SoD and exceptions
  Validity/effectiveAt

Actual state:
  Application users + role assignments
  Local groups, direct ACL and inherited permissions
  API keys/PATs, OAuth clients, workloads
  Sessions, grants and relevant enforcement state

Comparison:
  KEEP / CHANGE / REVOKE / INVESTIGATE
  + priority + responsible owner + proof requirements
~~~

### Các dữ liệu phải có provenance

- **Subject ID, target account ID, tenant và environment.**
- **Role/entitlement definition version** để biết nội dung quyền tại thời điểm review.
- **Snapshot/cutoff timestamp** và nguồn đã chụp.
- **HR/contract revision, effectiveAt, status** tại thời điểm quyết định.
- **Owner, justification, approval và expiry** cho quyền nhạy cảm.
- **Nguồn grant và inheritance**: group, direct assignment, ACL, delegated access.
- **Connector capability**: có thể readback/disable/revoke không.

### Không kết luận sai từ dữ liệu cũ

Ví dụ campaign tạo lúc 08:00, nhân viên nghỉ việc có hiệu lực lúc 09:00 nhưng reviewer bấm KEEP lúc 10:00. Khi xử lý, hệ thống phải đối chiếu **HRIS hiện hành**, không để approval trên snapshot cũ mở lại quyền Leaver.

Với các quyền rủi ro cao, cần **revalidate trước remediation/provisioning** và bảo vệ event ordering bằng revision/idempotency.

## 8. Quy trình chiến dịch review theo application

~~~mermaid
flowchart TD
    A["Chọn application theo rủi ro, lịch hoặc JML"] --> B["Xác nhận scope và owner"]
    B --> C["Inventory: accounts, roles, ACL, workload, tokens"]
    C --> D["Link identity + HRIS/IGA + trusted attributes"]
    D --> E["Phân loại quyền, risk, SoD và ngoại lệ"]
    E --> F["Gửi từng review item đến reviewer có thẩm quyền"]
    F --> G{"Quyết định?"}
    G -->|KEEP| H["Lưu justification + hạn chứng nhận"]
    G -->|CHANGE| I["Thu hẹp quyền / scope / TTL"]
    G -->|REVOKE| J["Thu hồi từ nguồn và target"]
    G -->|INVESTIGATE| K["Bổ sung evidence / escalation"]
    I --> L["Readback + effective access tests"]
    J --> L
    K --> E
    H --> M["Audit + lần review tiếp"]
    L --> N{"Required targets VERIFIED?"}
    N -->|Có| M
    N -->|Không| O["Remediation / coverage gap"]
    O --> L
~~~

Quy trình này **không đồng nhất “review completed” với “remediation completed”**. Một chiến dịch có thể đạt 100% quyết định từ reviewer nhưng vẫn còn 10 quyền REVOKE chưa được gỡ tại SaaS. Báo cáo cần giữ hai trạng thái riêng.

### Những bước có thể tự động hóa

Thu thập account/role, phát hiện Leaver, expiry, ownerless workload, gửi nhắc người duyệt và so sánh desired–actual có thể tự động hóa. Tuy nhiên tự động **giữ** quyền khi reviewer không trả lời là nguy hiểm cho quyền nhạy cảm; fallback phải tuân theo policy và mức rủi ro.

## 9. Reviewer cần thấy gì để ra quyết định có căn cứ?

Một giao diện review chỉ hiện **user ID – tên role – nút Approve** sẽ khiến người duyệt khó hiểu quyền đó có ý nghĩa gì. Với từng review item, nên hiển thị:

| Nhóm thông tin | Ví dụ nội dung | Mục đích |
| --- | --- | --- |
| **Subject** | Stable person ID, manager, department, employee/contractor/workload. | Kiểm đúng chủ thể, nguồn trạng thái. |
| **Lifecycle** | ACTIVE/MOVER/LEAVER, effectiveAt, expiry hợp đồng. | Tránh giữ quyền sau thay đổi vai trò. |
| **Ứng dụng** | Finance Portal production, tenant VN, account ID. | Biết đúng hệ thống và phạm vi. |
| **Entitlement** | Finance Approver; cho phép approve payment dưới hạn mức. | Hiểu hành động thực chứ không chỉ tên role. |
| **Grant source** | SCIM group, direct role, delegated ACL, local account. | Biết đường thu hồi nào phải xử lý. |
| **Business justification** | Đối soát hóa đơn tháng, dự án có owner. | Có còn nhiệm vụ cần quyền? |
| **Risk/SoD** | High risk, conflict requester–approver, cross-tenant. | Định tuyến phê duyệt và ưu tiên. |
| **Usage** | Dùng lần cuối, độ đầy đủ telemetry, phiên quan sát. | Tín hiệu hỗ trợ, không phải bằng chứng duy nhất. |
| **Validity** | Grant có hạn tới ngày X hay standing. | Đánh giá TTL và nhu cầu tiếp tục. |
| **Lần review trước** | Quyết định, reviewer, thời gian, thay đổi vai trò từ đó. | Phát hiện grant bị giữ lặp không giải trình. |
| **Effectiveness** | Quyền hiện có hiệu lực ở API nào, target readback. | Không đánh đồng assigned với effective access. |

### Một bản giải thích dễ đọc

~~~text
Application     : Finance Portal / Production / tenant-vn
Target account  : finance-user-527
Identity        : person-4821, ACTIVE, department=FINANCE
Entitlement     : FINANCE_INVOICE_APPROVER v4
Capability      : Approve invoice trong hạn mức, không self-approve
Grant source    : Direct role assignment
Business reason : Quy trình kiểm soát hóa đơn tháng
Risk            : HIGH, cần owner độc lập
Last observed   : 31 ngày trước; telemetry đầy đủ cho action này
Previous review : KEEP, đã hết hiệu lực chứng nhận
Decision        : KEEP / CHANGE / REVOKE / INVESTIGATE
~~~

Nếu dữ liệu là **UNKNOWN**, giao diện phải hiện đúng tình trạng đó. Không biến ngày sử dụng cuối cùng bị thiếu thành “chưa từng sử dụng”.

## 10. Quyết định review và những hành động tiếp theo

| Quyết định | Ý nghĩa | Việc cần làm | Điều kiện hoàn tất |
| --- | --- | --- | --- |
| **KEEP** | Quyền vẫn cần, đúng scope và chính sách. | Ghi justification, owner và kỳ rà soát lại. | Approval hợp lệ; không có hard policy violation. |
| **CHANGE/REDUCE** | Quyền còn cần nhưng quá rộng hoặc quá dài. | Hạ role, giới hạn tenant/resource, đổi sang JIT, thêm expiry. | Readback cho thấy chỉ scope đã duyệt còn hiệu lực. |
| **REVOKE** | Quyền không còn cần hoặc không được phép. | Gỡ grant từ nguồn và app, xử lý phiên/token liên quan. | Effective access bị từ chối tại target bắt buộc. |
| **INVESTIGATE** | Chưa rõ identity, owner, role effect hoặc usage. | Thu dữ liệu, chuyển reviewer đúng, xác minh risk. | Có quyết định cuối và bằng chứng, không auto-KEEP. |
| **EXCEPTION** | Một phạm vi tạm được chấp nhận theo quy trình riêng. | Xác nhận owner, approval, giới hạn hành động, thời gian, controls. | Ngoại lệ có hạn, giám sát và expiry/revoke proof. |

**Không phê duyệt bằng sự im lặng** đối với quyền rủi ro cao. Khi chiến dịch quá hạn hoặc người duyệt vắng mặt, chuyển tuyến/escalate theo chính sách; với quyền đặc biệt nguy hiểm có thể cần biện pháp chặn tạm nếu rủi ro đã được xác nhận.

### Quyết định có thể bị thay đổi bởi dữ liệu mới

Giả sử manager chọn KEEP lúc 08:30; HRIS phát Leaver effectiveAt 09:00; connector chuẩn bị apply lúc 09:05. Workflow phải **revalidate trạng thái**, không để quyết định KEEP cũ tái kích hoạt account. Các approval cần gắn **snapshot/version và thời điểm hiệu lực**, không giữ giá trị vĩnh viễn.

## 11. Review theo role catalog và least privilege

Tên role đôi khi gây hiểu nhầm: role **ReportReader** có thể được sửa thành có quyền export toàn bộ hồ sơ; role **Support** có thể thừa hưởng admin quyền qua group lồng.

Review nên có hai lớp:

1. **Role definition review:** role hiện chứa những permissions nào, scope và conditions ra sao? Có được phê duyệt bởi app/data owner, đúng version hay không?
2. **Role assignment review:** những ai đang có role đó và còn cần nó không? Quyền hiệu lực có bị mở rộng bởi grant trực tiếp/ACL không?

### Bảng phân loại ví dụ

| Role | Các hành động điển hình | Mức rà soát gợi ý | Câu hỏi |
| --- | --- | --- | --- |
| PortalViewer | Đọc trang nội bộ giới hạn. | Theo rủi ro, theo chu kỳ. | Có đúng tenant/project? |
| InvoiceReader | Đọc hóa đơn đã duyệt. | Owner dữ liệu xác nhận. | Có chứa dữ liệu nhạy cảm, phạm vi tenant nào? |
| InvoiceExporter | Xuất dữ liệu hàng loạt. | Review riêng quyền nhạy cảm. | Có mục đích và TTL? |
| PaymentApprover | Duyệt giao dịch. | SoD, hạn mức và assurance. | Có tự duyệt giao dịch mình tạo không? |
| AppAdmin | Quản lý user, grants, cấu hình. | Độc lập, ưu tiên least privilege/JIT. | Có khả năng tự cấp quyền? |
| EmergencyAdmin | Truy cập khẩn. | Kiểm emergency policy và hậu kiểm. | Có standing access quá lâu không? |

**Không so sánh “mỗi user chỉ có một role” với least privilege.** Một role wildcard có thể mạnh hơn nhiều role hẹp. Đánh giá nên dựa trên **actions, scope, duration và risk**, kể cả quyền được kế thừa.

### Xác nhận quyền cũ đã mất sau giảm role

Nếu chuyển người dùng từ AppAdmin sang Viewer, cần kiểm **role admin cũ, group/nested grant, token/session và admin endpoints**. Chỉ nhìn role mới hiện trên UI không chứng minh API quản trị đã bị chặn.

## 12. Rà soát quyền gán trực tiếp, ACL và các đường ngoài SSO

**Direct grants** là nguồn quyền tồn dư phổ biến vì chúng không luôn xuất hiện trong danh sách nhóm IdP hoặc IGA. Những đường cần đối soát:

1. **Direct app role** gắn vào user tại console SaaS.
2. **Object ACL** như quyền mở một folder, project, document hoặc dashboard.
3. **Nested group / team membership** do ứng dụng tự quản lý.
4. **Delegation**: trợ lý được đọc/hành động thay cấp quản lý.
5. **Shared link/capability** và URL tải xuống còn hạn.
6. **Local admin account** không phụ thuộc SSO.
7. **Personal access token / API key** được tạo trực tiếp tại app.
8. **App-integrated workload principal** có quyền đọc/ghi bằng client credential.
9. **Background export/job** đã được lên lịch trước khi role bị gỡ.

### Phân biệt assigned và effective access

\[
\text{GrantedSources} =
\{\text{Groups}, \text{Roles}, \text{ACL}, \text{Delegations}, \ldots\}
\]

Không thể kết luận **effective permission** bằng cách hợp các grants một cách cơ học. **Explicit deny, RBAC/ABAC, tenant boundary, resource state, session/token policy** và quyền được kiểm ở backend còn quyết định request ALLOW hay DENY.

Ví dụ một nhóm FinanceReader vẫn tồn tại, nhưng tài khoản đã LEAVER; API phải từ chối nghiệp vụ theo policy. Ngược lại, gỡ FinanceReader có thể chưa đủ nếu user còn direct role FinanceAdmin.

### Phép thử xác nhận thu hồi

Khi reviewer chọn REVOKE, cần kiểm:

- Đúng user/target ID, tenant và entitlement đã được gỡ.
- Không còn nguồn grant khác cho cùng capability.
- Một **positive control** chứng minh API đang hoạt động bình thường.
- Một **negative access probe** với test principal/context phù hợp bị từ chối bởi authorization, không chỉ lỗi mạng.
- Với thao tác ghi, **không có side effects** như job, file, bản ghi, message hoặc cập nhật quyền.

## 13. Rà soát JML theo application: Joiner, Mover, Leaver

JML là phép kiểm quan trọng nhất của application review vì ứng dụng có thể tiếp tục giữ quyền sau khi trạng thái nhân sự thay đổi.

| Sự kiện | Câu hỏi review ở ứng dụng | Kết quả cần chứng minh |
| --- | --- | --- |
| **Joiner** | Account được tạo đúng người, đúng ngày hiệu lực, đúng role baseline không? | Không có quyền trước ngày đủ điều kiện; đủ quyền hợp lệ sau phê duyệt. |
| **Mover** | Role/group/ACL cũ có bị gỡ? Quyền mới có tạo SoD không? | DENY quyền cũ, ALLOW quyền mới trong phạm vi duyệt. |
| **Leaver** | Account, session, token, PAT, role local có bị chặn không? | Không còn quyền truy cập tồn dư ngoài policy/SLA. |
| **Suspension** | Tài khoản tạm bị đình chỉ có thể dùng session cũ không? | Chặn theo trạng thái tạm khóa, không phá hủy dữ liệu cần giữ. |
| **Rehire** | Có tạo đúng identity link hay tự khôi phục grants lịch sử? | Chỉ quyền mới được xét duyệt; không cấp lại vai trò cũ. |
| **Contract expiry** | Sponsor và account đối tác có hết hạn đúng? | Các grants/keys/sessions không còn sau hợp đồng theo SLA. |

### Joiner: pre-provision không đồng nghĩa được truy cập

SCIM có thể tạo user trước ngày đi làm. Review phải phân biệt **account tồn tại** với **account đang có quyền hiệu lực**: account pre-hire không nên được phép truy cập tài nguyên trước ngày hiệu lực hoặc khi chưa hoàn tất identity proofing theo chính sách.

### Mover: quyền cũ có thể tồn tại theo nhiều đường

Một nhân viên chuyển Sales → Finance có thể mất nhóm IdP Sales, nhưng vẫn còn:

- CRM direct role Exporter.
- Quyền đọc tài liệu qua ACL trực tiếp.
- Một ứng dụng giữ role trong local session.
- OAuth access token chứa claim cũ, còn hạn.
- Quyền truy cập vault/workload credential của bộ phận cũ.

Review ứng dụng phải tìm những đường **effective access** này. Đồng thời kiểm quyền Finance mới không tạo SoD hoặc quá rộng.

### Leaver: hiệu lực thu hồi phải đo ở target

Tắt account IdP và gửi SCIM disable **không bảo đảm** mọi phiên SaaS và API key hết hiệu lực ngay. Những target có local session, JWT access token hoặc personal token cần kiểm riêng theo thiết kế:

\[
\text{RevocationLatency} =
t_{\mathrm{verified\_deny\ at\ required\ targets}} - t_{\mathrm{effectiveAt}}
\]

Đừng dùng timestamp **“revocation requested”** để kết luận đã thu hồi. Nếu target chưa hỗ trợ readback/probe, đánh dấu **UNVERIFIED** và chuyển owner xử lý thay vì gán PASS.

## 14. SSO, IdP, SCIM, OAuth/OIDC và app-local authorization

Trong review theo ứng dụng, cần biết **các công nghệ tương tác ở đâu và không đảm bảo điều gì**:

| Thành phần | Có thể cung cấp | Không nên suy ra |
| --- | --- | --- |
| **IdP/SSO** | Authentication, session tại IdP, group/claim. | Mọi local session của ứng dụng đã được thu hồi. |
| **OIDC ID token** | Kết quả xác thực để client thiết lập phiên. | Token này là quyền gọi tất cả APIs. |
| **OAuth access token** | Token dành cho resource server, có scope/audience. | Scope một mình đủ cho business authorization. |
| **SCIM User/Group** | Provisioning trạng thái account và nhóm. | App-local role, PAT, ACL và session đều do SCIM điều khiển. |
| **RBAC** | Quyền theo role/hierarchy. | Role không có điều kiện tenant/resource khác. |
| **ABAC** | Quyền theo thuộc tính subject/resource/context. | Mọi PEP có thuộc tính đủ mới hoặc đã gọi PDP. |
| **Application local policy** | Chốt owner, object, tenant và workflow. | Policy luôn đồng bộ với desired state IGA. |

### Token và session cũ

Một JWT access token tự chứa có thể tiếp tục được chấp nhận đến khi hết hạn nếu RS chỉ kiểm chữ ký và expiry. Thu hồi refresh token giúp chặn token mới nhưng **không tự động xóa mọi access token đã phát**. Review phải hiểu **TTL, introspection, denylist, entitlement checks và session revocation** được app/AS/RS hỗ trợ tới đâu.

**Không hứa thu hồi tức thời** nếu kiến trúc chỉ có token ngắn hạn và không có stateful revocation. Thay vào đó ghi **cửa sổ quyền tồn dư, SLA được chấp thuận, kiểm soát bù trừ và bằng chứng tại PEP**.

### Mapping identity trên ứng dụng

Một user ở IdP có thể tương ứng với nhiều account ở ứng dụng do tenant, email lịch sử, external identity hoặc merge/split. Review cần phân biệt:

- **Identity source ID** ổn định.
- **IdP subject/issuer** đúng trust.
- **SCIM target User.id / externalId** theo mapping thực tế.
- **Application account ID** và tenant.
- **Các tài khoản local/legacy** không map được.

Một account không map được phải vào **INVESTIGATE/ORPHANED**, không tự xóa hoặc kết luận không có người sở hữu chỉ từ email không khớp.

## 15. Service accounts, bots và tích hợp bên thứ ba

Application review chỉ xem nhân viên sẽ bỏ sót **machine-to-machine access**. Workload có thể dùng client credentials, managed identity, workload federation, mTLS hoặc API key tùy nền tảng.

| Loại quyền kỹ thuật | Cần rà soát |
| --- | --- |
| OAuth confidential client | Client owner, allowed grant, scopes, audiences, secret/key rotation và decommission. |
| Managed/workload identity | Cluster/namespace/service binding, trust, environment và tenant. |
| Service account cục bộ | Quyền API/DB, credential, owner, nhóm ứng dụng nào sử dụng. |
| CI/CD integration | Quyền deploy, sửa release, đọc secrets, approval và cross-environment access. |
| SaaS automation bot | Actions, dữ liệu, project, TTL, admin privileges. |
| Third-party connector | Dữ liệu có thể đọc/xuất, trust/contract, sponsor và revoke path. |

### Chuyển chủ sở hữu khi nhân viên nghỉ

Nếu người từng sở hữu service account đã Leaver, **không nhất thiết xóa workload đang vận hành hợp lệ**. Cần chuyển owner, thu hồi quyền truy cập của người cũ vào vault/repository/trust, đánh giá có phải **rotate keys/secrets** hay không, kiểm scope và đảm bảo khả năng vận hành liên tục.

### Quyền gián tiếp của workload

Một user không có role Finance Portal nhưng có quyền **đọc secret invoice-sync** hoặc **sửa CI/CD pipeline** của ứng dụng có thể kiểm soát API bằng danh tính dịch vụ. Review theo ứng dụng cần kiểm những đường **impersonation, secret access, assume-role và trust-policy modification** liên quan, nhất là quyền production.

## 16. Review các quyền nhạy cảm, SoD và quyền khẩn

Những quyền nên có tuyến review riêng và bằng chứng mạnh hơn:

- **Global/Application Admin:** tạo user, gán role, sửa policy hoặc cấu hình authentication.
- **Sensitive Export:** xuất hàng loạt dữ liệu PII/tài chính/secret.
- **Payment Approver:** duyệt giao dịch; có nguy cơ tự tạo tự duyệt.
- **Impersonation/Delegation:** hành động thay user khác hoặc service principal.
- **Break-glass/Emergency:** khả năng phục hồi khi SSO/PAM chính gặp sự cố.
- **Service credential read:** truy cập private key, API token, DB credential.

### Separation of Duties theo ngữ cảnh

Ví dụ ứng dụng Finance có role **PaymentCreator** và **PaymentApprover**. Review phải xét cả:

1. Có được giữ **đồng thời** hai role không (static SoD)?
2. Nếu cùng có hai role do ngoại lệ, user có thể **tự duyệt giao dịch mình tạo** không (dynamic SoD)?
3. App có **hạn mức, step-up, transaction state và audit** đúng không?
4. Người duyệt access review có được **tự xác nhận quyền Approver của mình** không?

Một manager xác nhận “người này cần ứng dụng” không đủ để chấp nhận xung đột SoD cấm.

### Emergency/break-glass

Tài khoản khẩn có thể không được dùng trong thời gian dài mà vẫn cần cho disaster recovery. Review cần kiểm **owner, vault, phương thức xác thực, giới hạn sử dụng, session logging, bảo quản credential, sự kiện đã dùng và hậu kiểm**. Không tự động xóa mọi quyền dormant; cân nhắc **eligible/JIT, dual control, TTL và diễn tập**.

## 17. Quyền không dùng, quyền quá hạn và ngoại lệ

**Last-used** là tín hiệu hữu ích nhưng chưa đủ để quyết định REVOKE. Một quyền admin phục hồi thảm họa có thể chưa dùng nhiều tháng, trong khi một quyền xuất dữ liệu trái policy có thể được dùng thường xuyên.

| Tình trạng | Hướng xử lý |
| --- | --- |
| Quyền đã hết hạn/Leaver rõ ràng | Ưu tiên thu hồi và xác minh, không đợi reviewer định kỳ. |
| Không sử dụng và không có business owner | INVESTIGATE, đánh giá risk, cân nhắc chặn theo policy. |
| Không sử dụng nhưng là quyền DR được duyệt | Giữ theo mô hình emergency/JIT hợp lệ, kiểm readiness. |
| Dùng nhiều nhưng vượt chức năng được duyệt | Không tự KEEP; xem xét lạm dụng, giảm scope hoặc revoke. |
| Temporary access còn trước expiry | Kiểm cần giữ tới hết hạn, không tự gia hạn. |
| Ngoại lệ đang còn hiệu lực | Có owner, approval, action/resource scope, expiry, monitoring. |
| Ngoại lệ đã quá hạn | Revoke và verify DENY, báo SLA nếu quá hạn. |

### Không coi thiếu telemetry là dormant

Nếu ứng dụng không ghi last-used cho quyền export, trường dữ liệu phải là **UNKNOWN**, không phải “không dùng”. Review cần thấy **cửa sổ quan sát, nguồn audit, retention và độ đầy đủ** để đưa ra quyết định có căn cứ.

## 18. Lịch review và ưu tiên ứng dụng theo rủi ro

Không có một chu kỳ bắt buộc phù hợp mọi ứng dụng. Tần suất và độ sâu nên dựa trên **mức rủi ro và tốc độ thay đổi quyền**.

| Tính chất application | Ví dụ | Cách review phù hợp |
| --- | --- | --- |
| **Rất nhạy cảm** | IAM admin, production secrets, thanh toán. | Review thường xuyên, độc lập, theo JML/incident và thay role quan trọng. |
| **Nhạy cảm** | Finance, HR, CRM có PII hoặc export. | Định kỳ theo risk và khi có Mover/Leaver/owner change. |
| **Mức trung bình** | Quản lý dự án, báo cáo nội bộ. | Theo dự án, thay manager và chu kỳ governance. |
| **Ít nhạy cảm** | Trang nội bộ chỉ đọc. | Chu kỳ phù hợp, có kiểm account lifecycle. |
| **Không owner/khó kết nối** | Legacy app, integration tự quản. | Ưu tiên điều tra và xử lý coverage gap, không bỏ qua. |

### Trigger cần mở review ngoài lịch

- Leaver, Mover, rehire hoặc contractor expiry.
- Quyền admin được cấp mới, sự kiện break-glass hoặc phát hiện SoD conflict.
- Role catalog hoặc policy ABAC thay đổi nội dung quyền.
- Ứng dụng bị migrate, tách tenant, thay SSO/SCIM integration.
- Có sự cố rò rỉ token, credential, account takeover hoặc shadow admin.
- Application owner nghỉ việc, dự án kết thúc hoặc SaaS sắp decommission.
- Directory/app restore từ backup có thể làm sống lại quyền lịch sử.

**Thời hạn review định kỳ không được làm chậm thu hồi Leaver**. Deprovisioning là quy trình theo sự kiện với SLA riêng; campaign là một lớp phát hiện sai lệch và chứng nhận bổ sung.

## 19. Xử lý một review item như một state machine

Một quyết định từ reviewer và một thay đổi tại ứng dụng phải được theo dõi ở **hai lớp trạng thái**:

~~~mermaid
stateDiagram-v2
    [*] --> DISCOVERED
    DISCOVERED --> READY_FOR_REVIEW: Linked identity + entitlement
    DISCOVERED --> INVESTIGATE: Missing owner / mapping
    READY_FOR_REVIEW --> AWAITING_DECISION: Assigned reviewer
    AWAITING_DECISION --> KEEP_DECIDED: KEEP with justification
    AWAITING_DECISION --> CHANGE_DECIDED: Scope reduction
    AWAITING_DECISION --> REVOKE_DECIDED: No longer needed
    AWAITING_DECISION --> INVESTIGATE: Insufficient evidence
    INVESTIGATE --> READY_FOR_REVIEW: Evidence resolved
    CHANGE_DECIDED --> REMEDIATING
    REVOKE_DECIDED --> REMEDIATING
    REMEDIATING --> VERIFYING: Connector applied change
    VERIFYING --> VERIFIED: Target readback + policy probes pass
    VERIFYING --> REMEDIATING: Drift or residual access
    VERIFYING --> BLOCKED: Target cannot be verified
    KEEP_DECIDED --> CERTIFIED: Approval valid, no hard conflict
    VERIFIED --> CLOSED
    CERTIFIED --> CLOSED
    BLOCKED --> INVESTIGATE: Remediation or approved exception
    CLOSED --> [*]
~~~

**Tên trạng thái chỉ minh họa**; một tổ chức có thể có quy trình khác. Điều quan trọng là:

- **REVOKE_DECIDED** chỉ có nghĩa reviewer yêu cầu thu hồi.
- **REMEDIATING** nghĩa connector hoặc admin đang xử lý.
- **VERIFIED** cần bằng chứng tại target theo scope/SLA.
- **CLOSED** phải ghi trạng thái thực và mọi ngoại lệ được duyệt, không ẩn target thất bại.

### Điều kiện tránh đóng sai

Một campaign có 400 quyết định KEEP và 100 quyết định REVOKE không thể được coi là hoàn tất remediation nếu **20 REVOKE vẫn chưa có readback**. Tỷ lệ review completion có thể là 100%, trong khi **remediation verification chỉ 80/100 = 80%** trên các mục cần thu hồi.

## 20. Rà soát application từ snapshot tới quyền có hiệu lực

### Dữ liệu đầu vào

Lấy danh sách account/entitlement tại application, nhưng gắn từng bản ghi với:

- **Target account ID và environment/tenant**.
- **HR/IGA subject ID** hoặc flag account chưa map được.
- **Entitlement ID/version, grant source và trạng thái**.
- **Application owner, business/data owner, policy**.
- **Observed usage**, chỉ khi telemetry đủ tin cậy.
- **Grant validity và last approved review**.
- **Risk/SoD sensitivity** và khả năng thu hồi ở target.

### Đối soát theo nhiều tập quyền

\[
\text{PotentialExcess} =
\text{EffectiveAccessAtApp} \setminus \text{DesiredAccessNow}
\]

Đây chỉ là **khung tư duy**. Với RBAC/ABAC, một quyền có thể áp dụng cho nhiều object/tenant và phụ thuộc thời gian; phép so tập cần chuẩn hóa action/resource/context thay vì chỉ so tên role.

| Nhóm đối soát | Ý nghĩa | Hành động gợi ý |
| --- | --- | --- |
| **MATCHED** | Có trong desired state và effective access. | Review necessity, risk và TTL; không tự KEEP tất cả. |
| **EXCESS_CANDIDATE** | Quyền có hiệu lực không có căn cứ hiện hành tương ứng. | Ưu tiên owner review, REVOKE/CHANGE hoặc tìm approval còn thiếu. |
| **MISSING_REQUIRED** | Quyền đã duyệt nhưng app chưa cho phép. | Điều tra provisioning/false deny; không tự cộng thêm wildcard. |
| **ORPHANED_IDENTITY** | Account không map được hoặc owner không còn. | Điều tra, bảo vệ quyền nhạy cảm, link cẩn thận. |
| **UNVERIFIED** | Không thể đọc/tự thử quyền tại target. | Coverage gap, owner, SLA, kiểm soát bù trừ. |
| **EXCEPTION_APPROVED** | Ngoại lệ có phạm vi và hạn theo policy. | Theo dõi expiry và chứng minh tự thu hồi. |

**Một quyền “ít sử dụng” không tự nằm trong EXCESS_CANDIDATE.** Nó chỉ trở thành ứng viên khi không khớp nhu cầu hợp lệ hoặc có dấu hiệu khác cần xem xét.

## 21. Ví dụ SQL: phát hiện tài khoản và entitlement cần rà soát

Đoạn SQL sau giả định **schema tự thiết kế**, không áp dụng trực tiếp cho Google Workspace, Microsoft Entra ID, SCIM hay một sản phẩm IGA cụ thể. Mục tiêu là minh họa cách kết hợp **target accounts**, **desired access** và **snapshot**.

~~~sql
-- Snapshot cùng measurement/review run, identifier đã được chuẩn hóa.
SELECT
    a.review_run_id,
    a.application_id,
    a.target_account_id,
    a.subject_id,
    a.tenant_id,
    e.entitlement_id,
    e.grant_source,
    e.is_effective,
    CASE
      WHEN a.subject_id IS NULL THEN 'ORPHANED_IDENTITY'
      WHEN e.verification_status <> 'VERIFIED'
        THEN 'UNVERIFIED'
      WHEN d.subject_id IS NULL THEN 'EXCESS_CANDIDATE'
      ELSE 'MATCHED'
    END AS review_bucket
FROM application_account_snapshot a
JOIN application_entitlement_snapshot e
  ON e.review_run_id = a.review_run_id
 AND e.target_account_id = a.target_account_id
 AND e.application_id = a.application_id
LEFT JOIN desired_entitlement_snapshot d
  ON d.review_run_id = a.review_run_id
 AND d.subject_id = a.subject_id
 AND d.application_id = a.application_id
 AND d.tenant_id = a.tenant_id
 AND d.entitlement_id = e.entitlement_id
 AND d.approval_status = 'APPROVED'
WHERE a.review_run_id = :review_run_id
  AND e.is_effective = TRUE;
~~~

### Cảnh báo khi triển khai SQL thật

- Phép so entitlement ID **không đánh giá** role inheritance, tenant expressions, ABAC conditions và permission wildcard. Cần resolver/policy engine tương ứng.
- **Đừng coi mọi account không tìm thấy HRIS ID là attacker**: có thể là account kỹ thuật hoặc guest với registry riêng.
- Approval record thiếu có thể do lỗi đồng bộ IGA; cần owner xác minh trước khi gọi một grant là confirmed excessive.
- Nếu một ứng dụng không có collector, câu SQL không tự phát hiện mất coverage. Phải có bảng **application_coverage** để hiển thị target chưa được thu thập.
- Snapshot từ các hệ thống **khác thời điểm** cần timestamp/revision hoặc có cơ chế reconcile để tránh false positives.

**SQL chỉ tạo danh sách ứng viên cần review**, không tự thực hiện lệnh REVOKE trên production.

## 22. Java pseudocode: điều phối application access review

Mã sau mô tả các ranh giới dữ liệu và trạng thái cần kiểm. Đây là **pseudocode kiến trúc**, không phải SDK IAM hay đoạn mã chạy được ngay:

~~~java
ReviewReport reviewApplication(ApprovedCampaignScope scope) {
    campaignPolicy.requireApprovedScope(scope);

    ApplicationInventory inventory =
        applicationRegistry.resolve(scope.applicationId());
    WorkforceSnapshot workforce =
        hrRegistry.currentTrustedSnapshot();
    DesiredAccess desired =
        igaPolicy.calculateForApplication(workforce, inventory, scope);
    ApplicationAccessSnapshot actual =
        targetConnector.readAccountsAndEntitlements(inventory, scope);

    ReviewReport report = new ReviewReport(scope.campaignId());

    for (ApplicationGrant grant : actual.grants()) {
        IdentityLink link = identityResolver.linkStableIdentity(grant);
        if (!link.isVerified()) {
            report.markInvestigate(grant, "identity_mapping_unknown");
            continue;
        }

        ReviewContext context = new ReviewContext(
            link.subjectId(),
            workforce.state(link.subjectId()),
            grant.applicationId(),
            grant.entitlementId(),
            grant.tenantId(),
            grant.grantSource(),
            scope.policyVersion()
        );

        // Reviewer phải thấy nhu cầu nghiệp vụ và rủi ro thực tế,
        // không chỉ kết quả so một tên role.
        ReviewItem item = reviewCatalog.buildItem(
            grant, context, desired, inventory.roleDefinition(grant));

        if (context.isLeaverEffective() || item.violatesNonWaivablePolicy()) {
            remediationQueue.enqueuePriorityRevocation(item);
        } else {
            reviewerRouter.assignByAuthority(item);
        }
        report.add(item);
    }

    report.recordCoverage(inventory, actual.readbackCapabilities());
    auditStore.persistMetadataWithoutSecrets(report);
    return report;
}
~~~

Đoạn code không tự chứng minh mọi cấp quyền có hiệu lực. Sau quyết định **REVOKE/CHANGE**, một job khác phải:

~~~java
RevocationEvidence applyReviewDecision(ApprovedDecision decision) {
    decisionPolicy.verifyReviewerAuthority(decision);
    decisionPolicy.verifyBoundSnapshot(decision);

    // Không thực thi một quyết định cũ trên subject/target đã đổi.
    LifecycleState state =
        hrRegistry.current(decision.stableSubjectId());
    decisionPolicy.assertCompatibleWithCurrentState(decision, state);

    targetConnector.applyIdempotently(
        decision.approvedTargetChange(),
        decision.idempotencyKey()
    );

    VerifiedAccess observed = verifier.readAndProbeAtTarget(
        decision.applicationId(),
        decision.targetAccountId(),
        decision.entitlementId(),
        decision.tenantId()
    );

    if (!observed.matchesApprovedDecision(decision)) {
        incidentWorkflow.openRemediation(decision, observed.safeSummary());
        return RevocationEvidence.unverified();
    }

    auditStore.recordVerifiedDecision(decision, observed.evidenceRef());
    return RevocationEvidence.verified(observed.evidenceRef());
}
~~~

### Những điều kiện production cần bổ sung

1. **Approval authority + SoD:** reviewer không tự duyệt đặc quyền của mình, quyết định đúng phạm vi.
2. **Concurrency/idempotency:** retry và event cũ không tái cấp quyền Leaver.
3. **Actual vs desired reconciliation:** mọi nguồn grant khác cần được nhận diện.
4. **Application session/token handling:** không chỉ gỡ role trên directory.
5. **Positive/negative probes:** kiểm hiệu lực ở API, không hiểu lỗi 503 là DENY.
6. **Coverage gaps:** target không readback phải được báo UNVERIFIED.
7. **Privacy:** audit không chứa token, mật khẩu, API keys hoặc hồ sơ HR đầy đủ.

## 23. Thu hồi quyền đúng quy trình sau quyết định REVOKE

Đây là giai đoạn quyết định hiệu quả của cả chiến dịch:

~~~mermaid
sequenceDiagram
    participant REV as Reviewer
    participant IGA as IGA Campaign
    participant HR as HRIS / Desired State
    participant CON as SCIM / App Connector
    participant APP as Target Application
    participant PEP as Protected API / PEP
    participant AUD as Evidence
    REV->>IGA: REVOKE grant + reason + approval context
    IGA->>HR: Revalidate subject lifecycle and policy
    HR-->>IGA: Current state + revision
    IGA->>CON: Revoke exact entitlement/account mapping
    CON->>APP: Remove direct/group role or disable account
    APP-->>CON: Applied response
    CON-->>IGA: Applied metadata
    IGA->>APP: Readback actual role/ACL/session controls
    APP-->>IGA: Observed state
    IGA->>PEP: Authorized negative probe
    PEP-->>IGA: DENY + no unauthorized side effect
    IGA->>AUD: VERIFIED result or remediation gap
~~~

### Nhiều nguồn grant: gỡ tới khi không còn quyền không hợp lệ

Giả sử một người có FinanceApprover qua **direct role** và **nested app group**. Nếu quyết định review yêu cầu xóa quyền Approver, chỉ gỡ direct role sẽ chưa đủ. Phải tính **effective access** và gỡ/thay những grants không hợp lệ theo nguồn có thẩm quyền, không xóa bừa nhóm hợp lệ của người khác.

### Khi connector báo thành công nhưng kết quả chưa đúng

Một SCIM PATCH hoặc API revoke thành công có thể chưa cập nhật local role, cache hoặc token đã phát. Khi kiểm PEP, nếu quyền cũ vẫn ALLOW, trạng thái phải là **REMEDIATION_REQUIRED**, không phải VERIFIED. Điều này cần owner và thời hạn xử lý, đặc biệt với quyền export/admin.

### Positive control trước negative probe

Nếu API trả 503 do hệ thống down, không được kết luận quyền đã bị chặn. Sử dụng **test principal hợp lệ** chứng minh endpoint hoạt động và dữ liệu thử tồn tại; sau đó thử điều kiện DENY tương ứng trong môi trường được ủy quyền.

## 24. Ngoại lệ, quyền khó xác minh và xử lý quá hạn

Không phải ứng dụng nào cũng có SCIM, API audit hoặc ability to revoke sessions. Review phải có **quy trình ngoại lệ và coverage gap** công khai.

| Tình huống | Hướng xử lý có trách nhiệm |
| --- | --- |
| Legacy app không xuất danh sách ACL | Manual export được kiểm soát hoặc công cụ hỗ trợ, đánh dấu giới hạn. |
| App owner đã nghỉ hoặc không phản hồi | Reassign owner theo workflow, security escalation cho quyền cao. |
| Target không hỗ trợ disable API key | Cân nhắc rotate credential, revoke user, gateway block hoặc compensating controls. |
| SAML SSO đã disable nhưng local session còn hoạt động | Xác minh SP session handling và resource policy, không chốt complete vội. |
| Quyền đặc biệt cần cho DR, ít được dùng | Review owner/runbook và chuyển JIT nếu phù hợp; không xóa chỉ do dormant. |
| Temporary handover sau Mover | Exception có scope, approval, expiry, audit và proof thu hồi. |
| Đợt review hết hạn, người duyệt chưa quyết định | Escalate, ghi UNREVIEWED; không tự chứng nhận. |
| Không thể link tài khoản với người | INVESTIGATE; nếu quyền cao, cân nhắc hạn chế theo risk. |

### Trạng thái ngoại lệ

Một ngoại lệ hợp lệ cần **application/tenant, account, entitlement, business reason, owner, approver, thời gian bắt đầu–hết hạn và kiểm soát bù trừ**. Sau expiry phải có tác vụ thu hồi và bằng chứng; không để ngoại lệ hết hạn vẫn ghi KEEP theo review cũ.

**Không biến manual exception thành trạng thái hợp lệ mãi mãi.** Nếu không thể đáp ứng yêu cầu kiểm chứng đối với quyền Critical, phải cân nhắc chặn, thay thiết kế hoặc chấp nhận rủi ro theo thẩm quyền thực sự, không cho worker/connector tự quyết.

## 25. Tình huống thực hành: review Finance Portal theo application

### Bối cảnh

Finance Portal có:

- Người dùng Finance đăng nhập bằng OIDC/SSO.
- RBAC roles **Reader, Exporter, Approver, AppAdmin**.
- ABAC giới hạn theo **tenant, classification, trạng thái hóa đơn**.
- SCIM đồng bộ một số user/group từ IGA.
- Vai trò **gán trực tiếp** trên console ứng dụng.
- OAuth client **invoice-sync** chạy job đồng bộ dữ liệu.
- Một đường **local administrator** phục vụ emergency recovery.

Ứng dụng sắp có đợt review quý IV. Mốc snapshot là 09:00 ngày 23/11; các dữ liệu và tên trong tình huống chỉ là giả định đào tạo.

### Bước 1 – Lập inventory và liên kết danh tính

| Account | Loại | Quyền đang ghi nhận | Sự kiện vòng đời | Mức ưu tiên |
| --- | --- | --- | --- | --- |
| **An** | Nhân viên | Reader tenant VN, direct Exporter. | Mover sang Sales trước ngày review. | HIGH: quyền Finance tồn dư. |
| **Bình** | Nhân viên | Approver tenant VN. | Leaver effectiveAt 08:30. | CRITICAL: tài khoản đã nghỉ. |
| **Chi** | Nhân viên | Reader tenant VN. | ACTIVE Finance, công việc cần đọc hóa đơn. | LOW/MEDIUM theo data classification. |
| **Dung** | Contractor | Viewer project temporary. | Hợp đồng hết hạn ngày 20/11. | HIGH: account không còn sponsor hợp lệ. |
| **invoice-sync** | Workload | invoice.read + export scope. | Owner trước đây đã Leaver. | HIGH: ownerless service principal. |
| **local-admin-1** | Emergency account | AppAdmin. | Đang ACTIVE, không qua SSO. | CRITICAL: quyền quản trị độc lập. |

**Review theo application giúp thấy tất cả account trên cùng tài nguyên**, kể cả workload và admin local mà một chiến dịch chỉ lấy nhóm IdP có thể bỏ sót.

### Bước 2 – Cung cấp quyết định mong đợi cho reviewer

| Review item | Reviewer có thẩm quyền | Expected decision | Giải thích |
| --- | --- | --- | --- |
| An: Reader | Finance application/data owner | REVOKE | Không còn nhiệm vụ Finance sau Mover. |
| An: Exporter direct | Data owner + security | REVOKE | Export nhạy cảm, có grant trực tiếp. |
| Bình: Approver | IAM deprovisioning và Finance owner | REVOKE ngay theo Leaver | Không đợi hết campaign để xử lý. |
| Chi: Reader | Finance manager + data owner | KEEP | Đúng job function và tenant. |
| Dung: Viewer | Contractor sponsor + app owner | REVOKE | Contract đã hết hạn. |
| invoice-sync: scopes | Workload owner + API/security owner | INVESTIGATE/CHANGE | Chưa rõ owner, export có thể quá rộng. |
| local-admin-1: AppAdmin | Security/PAM + application owner độc lập | INVESTIGATE | Cần bảo đảm emergency controls và không self-review. |

Reviewer phải thấy **role meaning và dữ liệu JML**. Nếu app không thể chứng minh một grant đến từ nguồn nào, ghi investigation thay vì suy đoán.

### Bước 3 – Xử lý quyền ở nguồn và ứng dụng

IAM áp các thay đổi đã duyệt:

1. Gỡ An khỏi các quyền Finance; gỡ **direct Exporter** trên ứng dụng thay vì chỉ SCIM group.
2. Disable account Bình, xử lý quyền Approver và các session/token tại ứng dụng.
3. Thu hồi tài khoản/role Dung sau khi xác minh mapping đúng target.
4. Giữ Reader cho Chi, kiểm không có quyền Exporter hoặc Admin ngoài nhiệm vụ.
5. Chuyển ownership của invoice-sync cho đội hiện hành; thu hẹp export scope nếu không được phê duyệt, đánh giá secret rotation.
6. Rà soát tài khoản local-admin-1 theo emergency runbook, vault/dual control/audit; không để chủ sở hữu tự chứng nhận.

### Bước 4 – Kiểm quyền thực tế

Tạo dữ liệu thử ở tenant VN và một tenant khác để kiểm:

| Probe sau remediation | Kết quả đúng | Cách chứng minh |
| --- | --- | --- |
| An dùng token cũ gọi invoice export. | DENY theo SLA. | PEP log, no export artifact. |
| Bình dùng session SaaS cũ gọi approve. | DENY. | Ứng dụng còn hoạt động, authorization chính xác. |
| Chi đọc invoice APPROVED tenant VN. | ALLOW. | Positive control trên resource được phép. |
| Chi đọc hóa đơn tenant khác. | DENY. | Tenant ABAC. |
| Dung dùng account sau contract expiry. | DENY. | Account disable + API probe. |
| invoice-sync gọi API ngoài approved scope. | DENY. | OAuth audience/scope và workload policy. |
| Người dùng thường gọi admin endpoint. | DENY. | BFLA test, không dựa menu UI. |
| Emergency admin activation hợp lệ. | ALLOW có kiểm soát. | Approval/assurance/audit và expiry đúng runbook. |

Nếu Bình bị disable nhưng một local session vẫn gọi API Approve thành công, remediation **không được coi đã hoàn tất**, bất kể SCIM và IdP báo success.

### Bước 5 – Kết luận chiến dịch

Ứng dụng có thể ghi:

~~~text
Review Decisions:
  KEEP=1, REVOKE=4, INVESTIGATE=2

Target Verification:
  Verified revoked=3
  Revoke still allowing access=1
  Investigation pending=2

Campaign:
  Reviewer decisions recorded? YES
  Remediation fully verified? NO
  Overall status: REMEDIATION_REQUIRED
~~~

Các số liệu chỉ minh họa. **Không báo “campaign complete” theo nghĩa bảo mật** khi có một quyền đã quyết định REVOKE mà PEP vẫn ALLOW.

## 26. Kiểm thử application review: bộ hồi quy theo tình huống

Bộ test cần áp dụng cho môi trường và principal **được ủy quyền**; dùng dữ liệu giả, tránh thử khai thác tài khoản thật hoặc truy vấn dữ liệu khách hàng ngoài phạm vi.

| ID | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| AR01 | Ứng dụng có user qua SSO và role trực tiếp. | Inventory hiển thị cả hai nguồn grant. |
| AR02 | Một user giữ cùng quyền qua hai nhóm lồng. | Không đếm nhầm hai effective capabilities; lưu cả nguồn grant. |
| AR03 | User không map với HRIS vì email đã thay. | INVESTIGATE mapping, không xóa/gộp tự động. |
| AR04 | Hai tài khoản local cùng email nhưng khác tenant. | Review tách theo target account ID/tenant. |
| AR05 | Pre-Joiner có user SCIM đã tạo nhưng chưa effectiveAt. | Không có quyền nghiệp vụ active. |
| AR06 | Mover mất IdP group nhưng còn direct app role. | Phát hiện và xử lý residual access. |
| AR07 | Leaver có ticket KEEP cũ đang chờ apply. | Revalidate trạng thái, không tái cấp quyền. |
| AR08 | Contractor hết hạn nhưng local session còn. | Review/verification không PASS cho tới khi bị chặn. |
| AR09 | Reviewer bấm REVOKE, SCIM trả success nhưng app role còn. | REMEDIATION_REQUIRED, không VERIFIED. |
| AR10 | Reviewer chọn CHANGE Reader thay Admin, token cũ còn Admin. | PEP phải chặn admin theo SLA thiết kế. |
| AR11 | Role Viewer được sửa thành có quyền Exporter. | Role-definition drift buộc đánh giá lại. |
| AR12 | Account có quyền export qua API key riêng. | Đưa PAT/API key vào inventory và review. |
| AR13 | Quyền temporary hết hạn nhưng worker vẫn ALLOW. | FAIL expiry verification, xử lý tồn dư. |
| AR14 | User được KEEP nhưng nay đã chuyển tenant. | Không giữ quyền tenant cũ trái policy. |
| AR15 | Data owner tự review quyền đặc biệt của chính mình. | Chặn self-certification hoặc định tuyến độc lập. |
| AR16 | App owner không còn ACTIVE. | Reassign có audit, không auto-KEEP. |
| AR17 | Manager xác nhận nhu cầu ứng dụng nhưng không biết role Admin. | Yêu cầu reviewer có authority về quyền nhạy cảm. |
| AR18 | Unknown usage do audit log chưa bật. | Hiển thị UNKNOWN; không quy thành dormant. |
| AR19 | Break-glass hiếm dùng nhưng có runbook hợp lệ. | Review bảo đảm controls, không auto-delete. |
| AR20 | Service account owner Leaver, workload còn cần. | Chuyển owner, thu hồi quyền cá nhân, đánh giá credential. |
| AR21 | Staging OAuth client có scope production. | Phát hiện cross-environment/trust risk. |
| AR22 | SCIM User active=false nhưng app API vẫn nhận JWT cũ. | Chưa VERIFIED; cần RS policy/revocation. |
| AR23 | Một entitlement được cấp từ direct role và ACL. | REVOKE chỉ PASS khi mọi đường ngoài policy mất hiệu lực. |
| AR24 | API chính có PEP, bulk export worker thiếu PEP. | Coverage gap/security regression được ghi. |
| AR25 | PEP trả 503 do downtime cho negative probe. | Không tính đây là DENY đúng policy. |
| AR26 | Resource ID ngoài tenant được gọi với token hợp lệ. | Backend từ chối BOLA/cross-tenant. |
| AR27 | User thường gọi endpoint admin trực tiếp. | Backend từ chối BFLA. |
| AR28 | Reviewer chọn KEEP không có business reason đối với quyền High. | Không hoàn tất theo chính sách yêu cầu justification. |
| AR29 | Reviewer không phản hồi sau deadline. | Escalate, ghi UNREVIEWED, không giả APPROVED. |
| AR30 | Ngoại lệ hết hạn nhưng vẫn giữ grant. | Revoke/verify và đánh dấu exception breach. |
| AR31 | Event Mover cũ đến sau Leaver. | Không tạo lại role/account, xử lý revision. |
| AR32 | Account rehire có email cũ nhưng subject ID thay. | Identity link được xác minh, không tự khôi phục grant lịch sử. |
| AR33 | Review snapshot và target readback khác revision. | Báo cần reconcile, không so như cùng trạng thái. |
| AR34 | App connector không trả role-level readback. | Coverage gap/compensating verification theo policy. |
| AR35 | Denied request vẫn tạo export job. | FAIL no-side-effect, xử lý enforcement bug. |
| AR36 | Review quyết định giảm scope từ all tenants sang tenant VN. | Connector chỉ áp approved delta; target readback đúng VN. |
| AR37 | App có 100% quyết định reviewer nhưng 10% REVOKE chưa VERIFIED. | Hai KPI tách biệt, không báo remediation complete. |
| AR38 | Risk model không xét local admin account. | Inventory/policy coverage không đạt. |
| AR39 | Quyền quản lý OAuth client bị bỏ sót khi review service identity. | Bổ sung owner, token grants và trust/impersonation routes. |
| AR40 | Hợp đồng đối tác bị hủy trong lúc reviewer đang KEEP. | Revalidate trước apply, chặn quyền theo current state. |

### Thiết kế test oracle và bằng chứng

Expected decision phải xuất phát từ **chính sách đã duyệt, HRIS/IGA hiện hành và business owner**, không dùng chính API đang được kiểm làm nguồn xác định đúng/sai. Đối với negative tests, luôn kiểm:

- Target/API **đang hoạt động** bằng positive control.
- Tài nguyên thử **thực sự tồn tại** và có owner/tenant xác định.
- Quyền thiếu được từ chối bởi **authorization policy**, không phải network error.
- Dữ liệu không bị lộ trong response, file, queue hoặc log.
- Với thao tác ghi, không có side effect xảy ra trước khi trả lỗi.

## 27. Audit và dữ liệu evidence cho một application review

Một hồ sơ có thể dùng cấu trúc như sau:

~~~yaml
campaignId: finance-review-2026-11
applicationRef: finance-portal
reviewItemId: review-item-4821
scope:
  tenantId: tenant-vn
  environment: production
identity:
  subjectRef: person-4821
  targetAccountRef: finance-account-527
  sourceRevision: hris-205
entitlement:
  id: FINANCE_APPROVER
  roleDefinitionVersion: 4
  grantSource: DIRECT_ROLE
decision:
  value: REVOKE
  reviewerRef: finance-data-owner
  authorityVerified: true
  decidedAt: "2026-11-23T03:00:00Z"
implementation:
  connectorResult: APPLIED
  targetReadback: REMOVED
  resourceAccessProbe: DENY_VERIFIED
  verifiedAt: "2026-11-23T03:06:00Z"
  evidenceRef: access-probe-527
overallStatus: VERIFIED
~~~

Đây chỉ là **schema minh họa**. Một review item có nhiều grant sources hoặc target cần nhiều bằng chứng hơn một record đơn. **Không ghi access token, refresh token, mật khẩu, private key, OTP, cookie phiên hoặc dữ liệu tài chính nhạy cảm** vào ticket/evidence.

### Phân biệt bốn dấu thời gian

| Timestamp | Ý nghĩa |
| --- | --- |
| **effectiveAt** | Khi quyền phải thay đổi theo HR/IGA/policy. |
| **decidedAt** | Khi reviewer ra quyết định. |
| **appliedAt** | Khi connector/ứng dụng báo đã áp thay đổi. |
| **verifiedAt** | Khi các target bắt buộc được kiểm chứng hiệu lực. |

Đối với Leaver, đo độ trễ từ **effectiveAt tới verifiedAt** theo scope; không tính từ decidedAt nếu reviewer trễ. Nếu còn target chưa kiểm, phải báo **partial/unknown**, không gán thời điểm hoàn tất giả.

### Bằng chứng tối thiểu cho kiểm toán

1. Danh sách ứng dụng/target nằm trong scope và exclusions có lý do.
2. Snapshot account–role–ACL cùng identity mapping có nguồn.
3. Policy, role definition version, desired state và risk/SoD findings.
4. Reviewer identity, authority, quyết định, justification, time.
5. Approved changes và kết quả connector/app readback.
6. Probe tại API/PEP cho quyền nhạy cảm sau REVOKE/CHANGE.
7. Exceptions, owner, expiry và monitoring.
8. Coverage gaps, SLA breach, remediations và sign-off.

**Audit không thay thế authorization**: log chỉ ghi rằng request được cho phép hay từ chối; nếu chính sách hoặc PEP sai, có log đầy đủ vẫn không làm quyền an toàn.

## 28. KPI: đo chất lượng review và chất lượng thu hồi riêng

| KPI | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| **Application inventory coverage** | Bao nhiêu ứng dụng/tenant và loại account đã thu đủ. | Không bỏ legacy/high-risk apps khỏi mẫu số. |
| **Reviewer completion rate** | Tỷ lệ item đã có quyết định hợp lệ. | Không đồng nghĩa đã gỡ các quyền REVOKE. |
| **Revocation verification rate** | Tỷ lệ REVOKE/CHANGE được kiểm chứng tại target. | Cần phân biệt áp cấu hình với effective DENY. |
| **Reviewer overdue items** | Những quyền quá hạn review theo risk tier. | Người duyệt vắng không được auto-KEEP. |
| **Orphaned account count** | Account thiếu owner/identity mapping hợp lệ. | Cần phân loại guest và workload riêng. |
| **High-risk entitlements retained** | Quyền Admin/Export/Approve vẫn được KEEP. | Cần justification, owner và expiry/review cadence. |
| **SoD findings** | Xung đột tạo–duyệt, tự cấp quyền hoặc tổ hợp cấm. | Có thể phụ thuộc resource/transaction, không chỉ role name. |
| **Residual access after JML** | Quyền Mover/Leaver còn được dùng sau mốc policy. | Đo trên PEP/session/token/ACL. |
| **Revocation latency** | Thời gian đến verified DENY ở target bắt buộc. | Chú thích SLA theo mức rủi ro. |
| **Exception aging** | Ngoại lệ sắp/quá hạn, thiếu owner, scope rộng. | Không ẩn exception khỏi báo cáo. |
| **False deny / business impact** | Quyền hợp lệ bị gỡ nhầm hoặc mất sau review. | Least privilege cần giữ khả năng làm việc hợp lệ. |
| **Review data freshness** | Độ mới của HRIS/IGA/app snapshot và policy version. | Chống quyết định trên dữ liệu cũ. |

### Ví dụ phân biệt hai tỷ lệ

Một chiến dịch có 200 review items. Cả 200 đã có decision hợp lệ, tức **reviewer completion 100%**. Trong đó 50 items cần thu hồi hoặc giảm quyền; 40 đã được xác minh tại target, 5 chưa xử lý và 5 không thể kiểm do thiếu API.

\[
\text{Verification Rate} = \frac{40}{50}\times100\%=80\%
\]

**20% còn lại không thể được tính đã an toàn**. Cần hiển thị riêng 5 pending và 5 unverified, owner chịu trách nhiệm và biện pháp bù trừ.

### Trend và phạm vi

Nếu kỳ này mở rộng review từ 10 ứng dụng lên 30 ứng dụng, số account “orphaned” có thể tăng vì **coverage tốt hơn**, không nhất thiết hệ thống tệ đi. Nên so sánh **fixed cohort** và công bố policy/campaign version, app list và cách lấy dữ liệu.

## 29. Bảo vệ dữ liệu, quyền riêng tư và độ tin cậy của kết quả

Application review có thể tập hợp **thông tin nhân sự, quyền ứng dụng, dự án, nhóm nhạy cảm và dấu vết sử dụng tài nguyên**. Vì vậy bản review không chỉ là báo cáo nội bộ thông thường.

### Nguyên tắc xử lý dữ liệu

- **Data minimization:** cung cấp cho reviewer đủ thông tin về quyền, lý do nghiệp vụ và trạng thái cần thiết, không đính kèm toàn bộ hồ sơ HR.
- **Purpose limitation:** chỉ dùng access logs cho đánh giá theo policy và mục đích được phép, không suy đoán hành vi cá nhân từ một tín hiệu thiếu ngữ cảnh.
- **Least privilege cho reviewer:** người duyệt Finance không tự động được xem danh sách secret/role của tất cả ứng dụng khác.
- **Retention:** thời hạn lưu campaign snapshots, decisions, audit và exports theo nghĩa vụ tổ chức và quy định hiện hành.
- **Encryption/access logging:** bảo vệ file export chứa danh tính–quyền; ghi ai đã tải và truy cập.
- **Token/secret hygiene:** không đưa access token, refresh token, PAT, private key hoặc mật khẩu vào CSV, email, evidence hay ticket.
- **Independent approvals:** người quản trị quyền review và chính họ có thể cần reviewer riêng cho các quyền Critical.
- **Deletion/cleanup:** dọn dữ liệu tạm hoặc bản export sau khi dùng theo chính sách, không để snapshot trong thư mục chia sẻ không kiểm soát.

### Khi dùng last-used data

Một dấu thời gian **không có hoạt động** có thể do hệ thống không ghi audit hoặc quyền chỉ dùng trong DR/cuối quý. Vì vậy, reviewer cần thấy **thời gian quan sát, nguồn log, việc log có bật và loại hành động được ghi**. Không sử dụng một chỉ số thiếu dữ liệu để tự thu hồi quyền hợp lệ hoặc để biện minh KEEP quyền ngoài chính sách.

### Tính tin cậy của bằng chứng

Một screenshot console ở thời điểm A, bản HRIS ở thời điểm B và token được phát trước đó có thể mô tả các trạng thái khác nhau. Để quyết định an toàn, record cần **timestamp, phiên bản policy/role, revision của nguồn và phạm vi target** rõ ràng. Nếu còn sai lệch thời gian quan trọng, phải **reconcile** trước khi kết luận.

## 30. Những sai lầm thường gặp trong application access review

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ xuất nhóm từ IdP. | Bỏ sót local admin, direct ACL, PAT, service principal. | Application inventory nhiều nguồn, có coverage report. |
| Hỏi manager “còn cần app không?” cho mọi role. | Không phân biệt Viewer với Admin/Exporter. | Review ở entitlement/action/resource scope. |
| Mặc định KEEP khi reviewer không trả lời. | Quyền nguy hiểm tồn tại nhờ im lặng. | Escalation và xử lý theo risk policy. |
| Cho app owner tự duyệt admin của mình. | Self-certification, thiếu SoD. | Independent approver cho quyền nhạy cảm. |
| Dùng email làm identity key duy nhất. | Map sai người, đặc biệt khi rehire/tenant khác. | Stable subject ID và target account mapping. |
| Coi account ACTIVE tại app là employment ACTIVE. | Leaver vẫn còn quyền. | HRIS/contract source và lifecycle gate. |
| Bỏ qua contractor/guest. | Người ngoài tiếp tục truy cập sau hợp đồng. | Sponsor, owner, expiry và review riêng. |
| Không review bots/service accounts. | Principal không owner giữ admin/wildcard. | Workload inventory, owner và credential lifecycle. |
| Chỉ review role assigned, không xem role meaning. | Catalog drift làm quyền mở rộng. | Role definition version và action-level review. |
| Xóa một group rồi tin đã thu hồi. | Direct grants hoặc cached sessions vẫn cho quyền. | Readback mọi grant source và verify API. |
| Coi SCIM 200/204 là bằng chứng cuối. | Target role hoặc local session chưa đổi. | Effective access probes/đối soát. |
| Coi HTTP 503 là DENY. | Lỗi khả dụng bị nhầm security control. | Positive control và policy decision evidence. |
| Gỡ mọi quyền không dùng 90 ngày. | Mất quyền DR/chu kỳ nghiệp vụ hiếm dùng. | Review justification, telemetry và JIT. |
| Review người dùng Leaver theo lịch quý. | Quyền tồn dư nhiều tuần. | Deprovision event-driven, review là lớp bổ sung. |
| Chỉ thống kê review completion. | Quyền REVOKE chưa gỡ vẫn “campaign complete”. | Theo dõi remediation verification riêng. |
| Không test bulk/export/async paths. | API phụ không dùng PEP. | Coverage theo action và đường thực thi. |
| Duyệt dựa trên snapshot đã cũ. | Mover/Leaver được tái cấp quyền. | HR revision và revalidation trước apply. |
| Ngoại lệ không expiry. | Grant tạm trở thành standing. | TTL, owner, auto-revoke và review lại. |
| Không có xử lý partial failure. | Một phần role được gỡ, phần còn lại tồn tại. | Reconciliation, idempotent retry và trạng thái PARTIAL. |
| Không đo quyền thiếu sau review. | Người dùng không làm được việc, phát sinh đường vòng. | Positive tests và missing-required access metrics. |
| Không quản lý file evidence xuất ra. | Rò rỉ PII và cấu trúc phân quyền. | Mã hóa, phân quyền, retention và cleanup. |

## 31. Checklist đóng một application access review

Trước khi báo một campaign đạt yêu cầu, kiểm đủ các nhóm điều kiện:

1. **Scope được duyệt:** application ID, environments, tenants, thời điểm, kỳ review và exclusions rõ ràng.
2. **Application owner hợp lệ:** người chủ trì còn ACTIVE, có thẩm quyền và không tự chứng nhận đặc quyền của mình.
3. **Inventory đầy đủ:** user, guest, contractor, local admin, workload, role, group, ACL, token/capability và quyền tạm.
4. **Identity linking:** stable subject ID, target account ID, tenant mapping và orphaned identities đã xử lý hoặc escalated.
5. **Role definitions:** tên và nội dung role/permission theo version đúng, có inheritance và direct grants.
6. **Nguồn JML hiện hành:** HRIS/contract registry, IGA approvals, effectiveAt/revision được đối chiếu.
7. **Business necessity:** owner xác định ai cần quyền gì và lý do, không chỉ xác nhận quyền hiện có.
8. **Risk/SoD:** quyền admin, export, payment approval, impersonation, tenant boundary và xung đột được xét.
9. **Quyết định có thẩm quyền:** KEEP/CHANGE/REVOKE/INVESTIGATE/EXCEPTION có justification, reviewer và timestamp.
10. **Không giữ theo im lặng:** các mục chưa review được escalated; không tự auto-certify.
11. **Approved snapshot:** entitlement, target, scope và thời hạn của quyết định không bị sửa sau approval.
12. **Remediation tại nguồn/đích:** group, direct ACL, local role, account, secret và các kênh còn lại được xử lý.
13. **Session/token:** kiểm thời hạn/khả năng chặn access token, refresh token, local session và PAT theo SLA.
14. **No unauthorized effects:** DENY thực sự chặn API và không tạo file, job, message hoặc thay đổi dữ liệu ngoài quyền.
15. **Readback tại PEP:** những quyền REVOKE/CHANGE trọng yếu có bằng chứng hiệu lực theo đúng tenant/resource.
16. **Workloads:** owner, service account, environment trust, secret age/scope và decommission được đánh giá.
17. **JML latency:** quyền tồn dư sau Mover/Leaver được đo, không lấy timestamp connector làm verifiedAt.
18. **Coverage gaps:** ứng dụng/target khó quan sát có owner, mức rủi ro, hạn xử lý và controls bù trừ.
19. **Exception governance:** ngoại lệ có phạm vi, approval, expiry và kiểm chứng sau hết hạn.
20. **Báo cáo hai chiều:** reviewer completion **và** remediation verification, false deny, residual risk.
21. **Audit/bảo mật dữ liệu:** evidence có nguồn, version, timestamp và không chứa credential hoặc dữ liệu không cần.
22. **Closure/sign-off:** mọi mục bắt buộc đạt hoặc còn tồn dư được ghi **PARTIAL/BLOCKED/EXCEPTION_APPROVED** minh bạch, không đánh dấu VERIFIED sai.

**Nguyên tắc nghiệm thu:** người duyệt đã trả lời là một kết quả **governance**; quyền đã thay đổi và được kiểm chứng tại ứng dụng là kết quả **enforcement**. Một chiến dịch đáng tin cần cả hai.

## 32. Câu hỏi tự kiểm tra

**Câu 1.** Review theo application khác review theo từng user thế nào?

**Trả lời:** Review theo application bắt đầu từ một ứng dụng, liệt kê mọi account, workload, role, ACL và quyền liên quan của ứng dụng đó. Review theo user bắt đầu từ một danh tính và có thể bao phủ nhiều ứng dụng. Hai góc nhìn bổ sung nhau.

**Câu 2.** Vì sao người quản lý xác nhận “nhân viên còn cần Finance Portal” chưa đủ?

**Trả lời:** Nhân viên có thể chỉ cần Reader nhưng đang giữ Approver, Exporter hoặc AppAdmin. Cần rà soát entitlement và phạm vi, đặc biệt với quyền nhạy cảm và SoD.

**Câu 3.** IdP đã gỡ nhóm của một Leaver. Có thể coi Finance Portal đã thu hồi toàn bộ quyền không?

**Trả lời:** Chưa. Ứng dụng có thể giữ direct role, ACL, local session, PAT hoặc JWT access token cũ. Phải kiểm đường thực thi quyền tại ứng dụng theo SLA.

**Câu 4.** Có cần review tài khoản invoice-sync chạy bằng Client Credentials không?

**Trả lời:** Có. Workload cần owner, mục đích, scope/audience, trust, thời hạn và credential lifecycle riêng. Không tự coi service account là nhân viên hay bỏ khỏi campaign.

**Câu 5.** Tại sao không dùng email để ghép mọi account trong review?

**Trả lời:** Email có thể đổi, trùng, tái sử dụng và tồn tại trên nhiều tenant. Cần stable identity ID và target account ID cùng mapping đã được xác minh.

**Câu 6.** Reviewer chọn REVOKE nhưng connector trả HTTP 204. Đã hoàn tất chưa?

**Trả lời:** Chưa chắc. Cần readback role/ACL và kiểm quyền tại PEP; session/token hoặc một grant source khác có thể vẫn cho phép hành động.

**Câu 7.** Một ứng dụng có 100% review items được quyết định nhưng 10% yêu cầu REVOKE chưa thực thi. Có thể nói campaign đã đóng an toàn không?

**Trả lời:** Không. Cần báo riêng reviewer completion và remediation verification. Các quyền còn tồn dư phải có owner, risk, hạn và trạng thái PARTIAL/REMEDIATION.

**Câu 8.** Quyền không dùng trong 180 ngày có chắc phải bị thu hồi không?

**Trả lời:** Không. Quyền phục hồi thảm họa hay thao tác định kỳ có thể hợp lệ; telemetry cũng có thể thiếu. Cần business justification, owner, rủi ro và mô hình JIT nếu phù hợp.

**Câu 9.** Vì sao application review phải kiểm cả role definition?

**Trả lời:** Nội dung của role có thể thay đổi sau khi user được cấp hoặc sau kỳ review trước. Role tên “Reader” có thể mang thêm quyền export/admin, nên quyết định KEEP phải dựa trên khả năng thực tế.

**Câu 10.** Người kiểm thử nhận HTTP 503 khi thử API bằng account đã Leaver. Có được coi là đã DENY đúng không?

**Trả lời:** Không. 503 là lỗi khả dụng, không chứng minh authorization deny. Cần positive control và bằng chứng điểm thực thi từ chối theo policy.

**Câu 11.** Với Mover, vì sao cần kiểm cả DENY quyền cũ và ALLOW quyền mới?

**Trả lời:** Để bảo đảm không còn quyền thừa trong vai trò cũ và vẫn đáp ứng công việc hợp lệ ở vai trò mới; nếu chỉ DENY mọi request có thể làm gián đoạn nghiệp vụ.

**Câu 12.** Nếu ứng dụng legacy không cho đọc role thực tế, nên kết luận như thế nào?

**Trả lời:** Ghi coverage gap/UNVERIFIED, tìm phương án kiểm chứng thay thế phù hợp, có owner và thời hạn. Không tự gán PASS vì không thấy bằng chứng lỗi.

**Câu 13.** Vì sao cần phân biệt application account, IdP subject và SCIM User.id?

**Trả lời:** Chúng là các định danh ở những hệ thống khác nhau; mapping không đúng có thể thu hồi nhầm người, tạo account trùng hoặc bỏ sót quyền local.

**Câu 14.** Những bằng chứng nào cần có để chốt một review item REVOKE?

**Trả lời:** Approved decision và reviewer authority, đúng subject/target/entitlement/scope, timestamp và policy revision, connector/app readback, effective-access DENY evidence, xử lý những session/token/ACL liên quan, cùng audit an toàn.

---

**Ghi nhớ:** **Review theo application không chỉ là xác nhận một người còn cần đăng nhập vào ứng dụng.** Đó là quá trình đối soát **mọi danh tính con người và workload, mọi role, ACL, local account, token và đường quyền** với nhu cầu nghiệp vụ, chính sách least privilege và trạng thái **Joiner–Mover–Leaver** hiện hành. Giá trị cuối cùng nằm ở hai điều: **người có thẩm quyền ra quyết định đúng** và **quyền không còn hợp lệ thực sự bị chặn tại ứng dụng/PEP**, được lưu bằng chứng để giảm **quyền truy cập tồn dư**.
