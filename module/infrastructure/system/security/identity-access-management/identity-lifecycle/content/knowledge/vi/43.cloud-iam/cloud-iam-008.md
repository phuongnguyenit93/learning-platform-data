# Cloud access review

**Chương:** Cloud IAM  
**Chủ đề:** Cloud access review (rà soát và tái chứng nhận quyền truy cập đám mây)  
**Ngữ cảnh:** Quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**; phối hợp HRIS, Identity Provider (IdP), SSO, SCIM, RBAC/ABAC, danh tính workload, kiểm toán và ngăn quyền truy cập tồn dư.

## 1. Cloud access review là gì?

**Cloud access review** là quy trình có chủ sở hữu và bằng chứng để xác định liệu **quyền truy cập hiện có của một người hoặc workload vào tài nguyên cloud còn phù hợp, được phê duyệt và nằm trong giới hạn cần thiết hay không**. Quy trình không kết thúc ở việc gửi biểu mẫu cho quản lý; phải ghi quyết định và **thực hiện, kiểm chứng** các thay đổi tại hệ thống cấp quyền thực tế.

Ví dụ: Một kỹ sư từng vận hành dịch vụ thanh toán nay chuyển sang nhóm dữ liệu. Tài khoản IdP đã đổi nhóm nhưng người đó vẫn có role quản trị ở một AWS account production. Đợt rà soát phải phát hiện role đó, xác định quyền không còn hợp lệ, thu hồi đúng đường cấp quyền và chứng minh người đó không còn quyền quản trị tương ứng.

Trong môi trường đa cloud, quyền có thể nằm ở nhiều lớp:

- Quyền đăng nhập qua **IdP/SSO** và nhóm directory.
- **AWS IAM Identity Center permission set assignment**, IAM role, policy và trust.
- **Azure RBAC role assignment**, quyền qua nhóm, scope kế thừa và danh tính Microsoft Entra.
- **Google Cloud IAM allow policy binding**, role, điều kiện và quyền impersonation.
- Resource-based policy, liên kết cross-account/cross-tenant, tài khoản cloud-local, guest và bên thứ ba.
- **Managed identity, service account, workload federation**, access key hoặc secret của automation.
- Token/role session đã phát hành; chính sách có thể chưa ngăn được tất cả phiên cũ tức thời.

**Mục tiêu cuối cùng:** Không chỉ “người quản lý đã xác nhận”, mà là **quyền hợp lệ được giữ, quyền không còn nhu cầu được thu hồi, các ngoại lệ được quản trị và kết quả được chứng minh tại cloud target**.

### 1.1. Kết quả người học cần đạt

Sau bài này, người học có thể:

1. Phân biệt **access review**, **access certification**, **access request**, **audit log review** và **effective permission analysis**.
2. Xác định đầy đủ danh tính, tài nguyên, entitlement và đường cấp quyền cần rà soát.
3. Thiết kế chiến dịch định kỳ và theo sự kiện **Joiner–Mover–Leaver**, ưu tiên theo rủi ro.
4. Hiểu các khác biệt quan trọng giữa AWS, Azure/Microsoft Entra và Google Cloud.
5. Tổ chức quyết định Keep, Revoke, Modify hoặc Exception có phê duyệt, thời hạn và người chịu trách nhiệm.
6. Tự động hóa đối soát **desired – assigned – effective access**, chống quyền tích tụ và privilege escalation.
7. Thu thập bằng chứng đáp ứng kiểm toán mà không làm lộ token, secret hoặc dữ liệu không cần thiết.

## 2. Phân biệt review, chứng nhận và thu hồi quyền

| Hoạt động | Câu hỏi | Đầu ra |
| --- | --- | --- |
| **Access request/approval** | Có nên cấp quyền mới không? | Phê duyệt hoặc từ chối trước khi cấp |
| **Provisioning/deprovisioning** | Làm thế nào để áp thay đổi ở đích? | Role, binding, group, account được sửa |
| **Access review** | Quyền đang tồn tại có còn cần và đúng phạm vi không? | Quyết định có owner và lý do |
| **Access certification/attestation** | Người có thẩm quyền xác nhận trạng thái quyền dựa trên bằng chứng nào? | Bản ghi xác nhận có thể kiểm toán |
| **Permission analysis** | Chủ thể thực sự có thể làm gì, kể cả quyền gián tiếp? | Kết quả phân tích quyền hiệu lực |
| **Audit/event review** | Quyền đã được sử dụng hoặc thay đổi khi nào? | Dấu vết và tín hiệu rủi ro |
| **Reconciliation** | Trạng thái ở cloud có khớp trạng thái mong muốn không? | Sai lệch, hành động khắc phục, readback |
| **Incident response** | Nếu có nghi vấn lộ quyền, phải chặn gì ngay? | Hành động giảm thiểu và điều tra |

**Access review không thay thế deprovisioning JML tức thời.** Một người nghỉ việc hôm nay không được tiếp tục giữ quyền chờ chiến dịch review tháng sau. Review định kỳ là một lớp bổ sung để tìm sai lệch, quyền thừa hoặc đường truy cập bị bỏ sót.

**Không đồng nhất “đã gửi yêu cầu thu hồi” với “đã thu hồi”.** Nếu quyết định là Revoke nhưng assignment vẫn còn ở cloud, kiểm soát chưa hoàn tất. Nếu assignment đã mất nhưng role khác hoặc resource policy vẫn cấp quyền tương đương, phải tiếp tục đánh giá.

### 2.1. Access review theo người hay theo tài nguyên?

Có ít nhất hai góc nhìn bổ sung:

- **Identity-centric:** Một người hoặc service account được quyền gì trên các cloud? Hữu ích cho Mover/Leaver, quyền tích tụ và rà soát toàn bộ dấu vết của principal.
- **Resource-centric:** Ai hoặc workload nào có thể truy cập một dữ liệu, secret, subscription, project hoặc môi trường production? Hữu ích cho owner hệ thống và dữ liệu nhạy cảm.

Chỉ xem một góc nhìn sẽ thiếu thông tin. Đối tác được cấp quyền trực tiếp trên một bucket có thể không xuất hiện trong báo cáo nhóm IdP; ngược lại, người có nhiều quyền trên nhiều account cần được rà soát toàn cục để phát hiện xung đột chức trách.

## 3. Kiến trúc dữ liệu cho cloud access review

Một chiến dịch có chất lượng cần biết **nguồn danh tính**, **quyền được duyệt**, **quyền được gán**, **quyền có thể sử dụng thực tế** và **nguồn bằng chứng**.

~~~mermaid
flowchart TD
    HR["HRIS / contractor registry<br/>Trạng thái và JML"] --> IGA["IGA / Review orchestrator<br/>Desired access và phê duyệt"]
    OWN["Service catalog / CMDB<br/>Resource và workload owner"] --> IGA
    IDP["IdP / Directory / SCIM<br/>User, group, membership"] --> COL["Entitlement collectors"]
    AWS["AWS IAM + Identity Center<br/>Role, assignment, trust"] --> COL
    AZ["Azure RBAC + Entra<br/>Role assignment, group"] --> COL
    GCP["Google Cloud IAM<br/>Bindings, impersonation"] --> COL
    WK["Workload registry<br/>Service account, CI, key"] --> COL
    COL --> NORMAL["Chuẩn hóa principal + grant<br/>Scope, source, condition"]
    NORMAL --> IGA
    IGA --> REV["Reviewer có trách nhiệm<br/>Keep / Revoke / Modify / Exception"]
    REV --> EXEC["Provisioning / Cloud IAM API<br/>Thực hiện thay đổi"]
    EXEC --> VERIFY["Readback + effective-access checks"]
    VERIFY --> AUD["Audit evidence / SIEM"]
    VERIFY --> IGA
~~~

Sơ đồ là mô hình logic. Không phải một API hoặc công cụ có thể liệt kê hoàn chỉnh mọi **effective permission** trên cả ba cloud. Cần kết hợp các nguồn phù hợp, mô hình kế thừa và những giới hạn của từng provider.

### 3.1. Inventory tối thiểu cho một entitlement

| Trường | Nội dung cần lưu | Vì sao cần? |
| --- | --- | --- |
| Stable principal ID | ID người/workload trong nguồn thẩm quyền | Tránh phụ thuộc email hoặc tên có thể thay |
| Principal type | Employee, contractor, guest, service account, workload | Chọn owner và quy trình review |
| Issuer/source | IdP, tenant, CI OIDC issuer hoặc cloud-local | Biết đường xác thực và thu hồi |
| Target ID | AWS account, Azure subscription, GCP project/resource | Xác định đúng ranh giới |
| Resource scope | Organization/folder/project/resource group/resource | Phát hiện quyền kế thừa hoặc quá rộng |
| Role/policy/permission ID | Tập quyền được gắn | Đánh giá chức năng và rủi ro |
| Grant source | Direct, group, nested group, trust, resource policy | Biết nơi phải sửa khi thu hồi |
| Conditions/expiration | Ngữ cảnh, JIT, thời hạn | Đánh giá quyền còn hiệu lực |
| Business justification | Tác vụ và mục đích nghiệp vụ | Trả lời có còn cần quyền không |
| Owner và reviewer | Người chịu trách nhiệm dịch vụ/dữ liệu và người xác nhận | Giảm phê duyệt tùy tiện |
| Source approval/event | Ticket, Joiner/Mover/Leaver, hợp đồng | Có nguồn quyết định đáng tin |
| Last used (nếu có) | Tín hiệu hoạt động quyền từ nguồn có sẵn | Tìm quyền thừa, không đủ để tự quyết định |
| Verification status | Trạng thái sau khi áp quyết định | Tách review khỏi thực thi |

Phải bảo vệ inventory quyền vì nó tiết lộ cấu trúc IAM, tài nguyên nhạy cảm và các đường có thể bị lạm dụng.

### 3.2. Định danh ổn định và dữ liệu đã lỗi thời

Email, tên hiển thị và chức danh có thể thay đổi. Với người dùng, liên kết **ID nhân sự + issuer + subject** theo dữ liệu có thẩm quyền; với workload, dùng **workload ID + owner + issuer/subject hoặc cloud principal ID**. Không gộp hai principal chỉ vì có email hoặc tên giống nhau.

Review cũng phải ghi rõ **thời điểm snapshot** của quyền. Nếu inventory được lấy hôm qua nhưng role thay đổi sáng nay, reviewer cần thấy hoặc được cảnh báo về thay đổi sau snapshot, tránh phê duyệt trạng thái không còn tồn tại.

## 4. Desired, assigned và effective access

Đây là ba lớp không được đánh đồng:

1. **Desired access:** Quyền được tổ chức cho phép dựa trên trạng thái người/workload, công việc, phê duyệt, scope và hạn dùng.
2. **Assigned access:** Group membership, role assignment, IAM binding, policy, trust, key hoặc quyền trực tiếp đang cấu hình.
3. **Effective access:** Hành động mà principal thực sự được phép làm sau khi xét quyền kế thừa, deny, điều kiện, resource policy, session và quy tắc của dịch vụ.

Một grant được gán nhưng bị policy chặn vẫn là **cấu hình cần kiểm kê**; nó có thể trở nên có hiệu lực sau khi guardrail thay đổi. Ngược lại, xóa một grant trực tiếp chưa đủ nếu quyền còn qua nhóm hoặc impersonation.

### 4.1. Mô hình tính sai lệch

~~~text
Principal = (issuer, stableSubject, identityType)
Grant = (principal, roleOrPermission, resourceScope, grantSource, conditions)

Desired = entitlementsFromApprovedBusinessPolicy(principal)
Assigned = entitlementsDiscoveredAtCloudTargets(principal)

CandidateStale = normalize(Assigned) - normalize(Desired)
CandidateMissing = normalize(Desired) - normalize(Assigned)

For each candidate:
    evaluateInheritanceAndAlternativePaths()
    validateBusinessContextAndRisk()
    decideActionAndRecordOwner()
    applyChangeAtCorrectTarget()
    verifyActualAndEffectiveAccess()
~~~

Đây là **giả mã nghiệp vụ**, không phải công thức suy ra đầy đủ effective access. Một role Reader tại project và role cùng tên tại organization khác về phạm vi; cùng permission có thể được cấp qua nhiều đường; một số policy được đánh giá theo điều kiện runtime.

### 4.2. Quyền gián tiếp phải được nhìn thấy

Các đường dễ bị bỏ sót:

- Nhóm lồng nhau hoặc membership tại IdP chưa đồng bộ.
- Role ở scope cha được kế thừa xuống tài nguyên con.
- Permission set/assignment ở lớp quản trị tập trung và IAM role tại account đích.
- Resource-based policy cấp quyền cross-account.
- Service account impersonation hoặc quyền assume role khác.
- Principal có thể sửa policy/role hoặc đọc secret chứa credential có quyền mạnh.
- Guest, cloud-local user và external identities không có trong nguồn HRIS.
- Phiên tạm thời đã phát hành trước khi role/trust bị thu hồi.

Review phải xét **đường nâng đặc quyền** chứ không chỉ các role có tên Administrator, Owner hoặc Editor.

## 5. Khi nào cần thực hiện review?

Review gồm **định kỳ** và **theo sự kiện**. Chu kỳ nên dựa trên mức rủi ro và yêu cầu quản trị, không áp một lịch duy nhất cho mọi quyền.

| Đối tượng | Kích hoạt thường gặp | Mức ưu tiên |
| --- | --- | --- |
| Privileged admin trên production | Review thường xuyên, sau nâng quyền hoặc incident | Rất cao |
| Quyền sửa IAM, trust, secret, key | Định kỳ ngắn và sau thay đổi cấu hình | Rất cao |
| Cross-tenant/cross-account access | Khi hợp đồng hoặc trust thay đổi; review định kỳ | Cao |
| Guest/contractor | Ngày hết hợp đồng, sponsor đổi, kỳ review | Cao |
| Workload có quyền production | Khi repo, issuer, owner, service hoặc environment đổi | Cao |
| Nhân viên đổi nhóm/role | Ngay khi sự kiện Mover có hiệu lực | Theo quyền bị ảnh hưởng |
| Nhân viên nghỉ việc | Ngay khi Leaver có hiệu lực, ưu tiên chặn truy cập | Khẩn cấp |
| Quyền chỉ đọc dev được giới hạn | Định kỳ tùy chính sách | Thấp hơn |
| Account/Project không có owner | Khi phát hiện orphan hoặc thay đổi tổ chức | Cao |

Ví dụ nội bộ có thể đặt lịch **hàng tháng** cho quyền quản trị production, **hàng quý** cho quyền nhạy cảm và **hàng nửa năm** cho một số quyền thấp hơn. Đây chỉ là **minh họa chính sách**, không phải tần suất bắt buộc của mọi chuẩn tuân thủ. Phải xác định lịch thật theo rủi ro, cam kết và yêu cầu pháp lý/kiểm toán hiện hành.

### 5.1. Review theo sự kiện JML không được chờ lịch

**Joiner:** Sau khi cấp quyền, kiểm tra người nhận, scope, approval và quyền không cần thiết.  
**Mover:** Khi đổi chức trách, tính lại desired access; thu hồi quyền cũ và review quyền mới trước hoặc cùng lúc cấp.  
**Leaver:** Chặn khả năng xác thực/tái cấp mới và thu hồi quyền ở cloud target ngay theo quy trình; review hồi tố dùng để xác minh không còn đường truy cập bỏ sót.

Những sự kiện khác cần review: resource đổi owner, workload được di trú, CI repository đổi cấu trúc, trust policy được sửa, phát hiện credential lộ, đối tác kết thúc hợp đồng hoặc tài nguyên chuyển mức phân loại dữ liệu.

## 6. Quy trình access review từ đầu đến cuối

~~~mermaid
flowchart TD
    S["Xác định phạm vi, thời điểm và mục tiêu"] --> I["Inventory principal, resource, grant và owner"]
    I --> N["Chuẩn hóa và phân loại rủi ro"]
    N --> R["Giao reviewer phù hợp + ngữ cảnh"]
    R --> D{"Quyết định"}
    D -->|Keep| K["Xác nhận lý do, scope và hạn review tiếp"]
    D -->|Revoke| X["Thu hồi đúng đường cấp quyền"]
    D -->|Modify| M["Giảm/sửa role, scope, thời hạn"]
    D -->|Exception| E["Phê duyệt ngoại lệ có owner + expiry"]
    X --> V["Đọc lại trạng thái cloud và effective access"]
    M --> V
    E --> V
    K --> A["Lưu bằng chứng và theo dõi thay đổi"]
    V --> Q{"Kết quả đạt desired state?"}
    Q -->|Có| A
    Q -->|Chưa| F["Remediation failure / escalation"]
    F --> V
~~~

### 6.1. Pha 1 — Thiết lập chiến dịch

Xác định rõ:

- Các cloud/tenant/account/subscription/project, role và mức nhạy cảm.
- Người hay workload nào thuộc phạm vi; cách xử lý external principal.
- Thời điểm inventory/snapshot và thời hạn hoàn tất.
- Chủ sở hữu dữ liệu/tài nguyên, reviewer và người thực thi quyết định.
- Quy tắc xử lý khi không có owner, reviewer không trả lời hoặc có tranh chấp.
- Bằng chứng bắt buộc trước khi được kết thúc campaign.

Không để danh sách “truy cập cloud” chung chung mà không có **scope và loại quyền**; reviewer sẽ không biết chính xác họ đang xác nhận điều gì.

### 6.2. Pha 2 — Thu thập, chuẩn hóa và ưu tiên

Collector phải lấy quyền từ đúng hệ thống: group/IdP, IAM của từng provider, resource policy và workload identities có liên quan. Sau đó hợp nhất các bản ghi về cùng một stable principal ID, nhưng **không làm mất grant source hoặc scope**.

Phân loại rủi ro gồm: production, dữ liệu nhạy cảm, quyền IAM mutation, trust bên ngoài, credential dài hạn, session đặc biệt, thời gian chưa review và các xung đột chức trách.

### 6.3. Pha 3 — Người có trách nhiệm ra quyết định

Reviewer cần thấy **vai trò và hành động có thể thực hiện**, không chỉ tên role lạ. Họ phải biết:

- Đây là ai hoặc workload nào, còn active không?
- Quyền xuất phát từ đâu và tác động lên hệ thống/dữ liệu nào?
- Người đó có nhiệm vụ cụ thể cần quyền này không?
- Quyền có vượt scope hoặc thời gian cần thiết không?
- Có xung đột **Separation of Duties (SoD)** hoặc đường nâng quyền gián tiếp không?
- Nếu gỡ quyền, dịch vụ nào có nguy cơ bị gián đoạn và phương án chuyển giao?

Đối với quyền cao, nên có **reviewer độc lập** hoặc cấp phê duyệt bổ sung theo chính sách. Không để principal tự chứng nhận quyền đặc biệt của mình là hợp lệ.

### 6.4. Pha 4 — Thực thi có kiểm soát

Quyết định thường gồm:

| Quyết định | Ý nghĩa | Thao tác tiếp theo |
| --- | --- | --- |
| **KEEP** | Quyền đúng nhu cầu và phạm vi | Ghi lý do, owner, review/expiry kế tiếp |
| **REVOKE** | Không còn nhu cầu hoặc không được phê duyệt | Gỡ membership/assignment/binding/trust/key đúng nguồn |
| **MODIFY** | Cần quyền nhưng đang quá rộng | Chỉnh role, resource scope, điều kiện hoặc thời hạn |
| **EXCEPTION** | Chưa thể điều chỉnh ngay vì lý do chính đáng | Ghi rủi ro, biện pháp giảm thiểu, owner, approver, deadline |
| **ESCALATE** | Thiếu thông tin hoặc có tranh chấp/khẩn cấp | Chuyển đúng bộ phận, giữ trạng thái chưa hoàn tất |

**Im lặng không được tự động xem là KEEP.** Nếu reviewer không phản hồi, chính sách cần quy định quy trình nhắc, escalation và cách giảm rủi ro đối với quyền nhạy cảm. Với workload quan trọng, không nên tự động xóa quyền có thể làm gián đoạn production nếu chưa kiểm tra dependency; nhưng quyền rủi ro cao cũng không được giữ vô hạn vì lo gián đoạn.

### 6.5. Pha 5 — Verification và closure

Sau REVOKE/MODIFY:

1. Đọc lại cấu hình IAM ở cloud target.
2. Xác định quyền trực tiếp, nhóm, scope kế thừa và đường trust liên quan còn không.
3. Kiểm tra effective access bằng công cụ provider hoặc bài kiểm thử được phép.
4. Xử lý session/token đã phát hành theo cơ chế thực tế; ghi giới hạn nếu chưa thể thu hồi ngay.
5. Lưu bằng chứng thời gian, hệ thống đích, kết quả và người thực hiện.
6. Chỉ đóng trạng thái hoàn tất khi đáp ứng chính sách xác minh; ngoại lệ phải có owner và thời hạn.

## 7. Ai nên làm reviewer?

| Vai trò | Điều có thể xác nhận | Giới hạn trách nhiệm |
| --- | --- | --- |
| **Line manager** | Nhân viên có còn làm công việc cần quyền không? | Có thể không hiểu chi tiết IAM action/resource |
| **Application owner** | Workload hoặc người dùng có cần quyền cho ứng dụng không? | Không được tự bỏ qua rủi ro bảo mật |
| **Data owner** | Mục đích xử lý dữ liệu và mức truy cập có hợp lệ không? | Cần IAM specialist giải thích kỹ thuật |
| **Cloud platform owner** | Role/scope phù hợp kiến trúc và vận hành không? | Không tự xác định lý do nghiệp vụ của mọi người |
| **Security/IAM reviewer** | Privilege escalation, trust, SoD và policy drift | Không thể tự suy đoán nhu cầu của từng sản phẩm |
| **Third-party sponsor** | Guest/đối tác còn nhu cầu và hợp đồng hợp lệ không? | Không có quyền tự cấp vượt phạm vi đã duyệt |
| **Workload owner** | Service còn chạy, dependency và quyền máy cần gì? | Cần kiểm tra quyền thực tế bằng cloud collector |

**Reviewer phải có thẩm quyền và đủ ngữ cảnh.** Với quyền ở production nhạy cảm, có thể dùng hai cấp xác nhận: business/data owner xác nhận nhu cầu; IAM/security xác nhận phạm vi kỹ thuật và rủi ro.

### 7.1. Xử lý owner mồ côi

Một account hoặc service account không có owner là **vấn đề phải xử lý**, không phải lý do bỏ khỏi review. Có thể:

1. Truy vết nguồn tạo account, audit logs và service catalog.
2. Gán owner tạm theo cấp quản trị được phê duyệt.
3. Giới hạn quyền/rủi ro trong khi xác minh dependency.
4. Cập nhật inventory và ngày review gần nhất.
5. Nếu không còn workload hợp lệ, thực hiện decommission/deprovision có kiểm soát.

Tránh tự giữ quyền “vì chưa biết ai dùng”, đặc biệt với privileged role, service account key hoặc cross-account trust.

## 8. AWS: rà soát quyền trên account và organization

AWS có nhiều đường cấp quyền. Một chiến dịch chỉ xem **IAM users** sẽ bỏ sót IAM roles, IAM Identity Center, federation, cross-account access và resource policies.

### 8.1. Các đối tượng cần kiểm tra

| Đối tượng AWS | Điều cần review |
| --- | --- |
| **IAM Identity Center** | Users/groups, AWS account assignments, permission sets và scope account |
| **IAM roles** | Trust policy, identity-based permissions, ai được assume role |
| **IAM users và access keys** | User còn cần tồn tại không; key có owner/rotation không |
| **Identity-based policies** | Wildcard action/resource, quyền IAM mutation, điều kiện |
| **Resource-based policies** | Quyền cấp cho principal/account bên ngoài trên dịch vụ hỗ trợ |
| **AWS Organizations / SCP** | Guardrail nào giới hạn quyền; không nhầm SCP là quyền cấp |
| **Session/role assumption** | Phiên STS đã phát, identity nguồn và hạn sử dụng |
| **Workload identities** | EC2 instance profile, Lambda/ECS/EKS role, federation từ CI/CD |
| **Root/break-glass** | Bảo vệ, kiểm soát sử dụng và review theo quy trình đặc biệt |

Một **permission set assignment** trong IAM Identity Center không đồng nghĩa mọi đường quyền khác trong account đều biến mất. Khi gỡ membership, vẫn cần phát hiện direct role trust, local IAM user và các grant ngoài IAM Identity Center.

### 8.2. Công cụ và tín hiệu liên quan

**AWS IAM Access Analyzer** có thể hỗ trợ phân tích policy và các kiểu truy cập theo khả năng của công cụ, chẳng hạn external access, policy validation hoặc những phân tích quyền được hỗ trợ. **CloudTrail** cung cấp dấu vết API và thay đổi IAM khi đã cấu hình logging phù hợp.

**Thông tin sử dụng quyền gần đây/last accessed** hỗ trợ ưu tiên review nhưng không phải bằng chứng tuyệt đối rằng quyền chưa bao giờ cần: độ đầy đủ, loại hành động được ghi, thời gian quan sát và lịch chạy workload có thể tạo khoảng trống. Không xóa role của job phục hồi khẩn cấp chỉ vì chưa có event trong vài tuần.

### 8.3. Ví dụ AWS cross-account access

Một đối tác có IAM role trong account của họ được trust cho phép assume role đọc dữ liệu tại AWS account của doanh nghiệp. Review phải trả lời:

1. Đối tác và hợp đồng có còn hợp lệ?
2. Principal nguồn nào có thể assume, có bị trust quá rộng không?
3. Role đích cho phép những actions/resources nào?
4. Có cơ chế phân biệt bên thứ ba và ngăn **confused deputy** nếu ngữ cảnh yêu cầu không?
5. Có nguồn khác được assume cùng role hoặc cùng resource policy không?
6. Nếu quyết định REVOKE, ai sửa trust và kiểm tra session còn sống?

Xóa nhóm nhân viên trong IdP công ty **không tự thu hồi** cross-account trust đã cấp cho đối tác.

## 9. Azure/Microsoft Entra: access review và Azure RBAC

Trong môi trường Microsoft, cần phân biệt ba lớp:

- **Microsoft Entra ID:** Danh tính, nhóm, guest, ứng dụng và những cơ chế quản trị/đánh giá quyền hỗ trợ.
- **Azure RBAC:** Role assignment của security principal tại management group, subscription, resource group hoặc resource.
- **Quyền ở dịch vụ và data plane:** Ví dụ quyền đọc dữ liệu storage hoặc quyền do ứng dụng tự quản lý; phải rà soát theo cơ chế riêng.

### 9.1. Microsoft Entra access reviews

**Microsoft Entra ID Governance / access reviews** hỗ trợ các kịch bản chứng nhận quyền trên nhóm, ứng dụng và một số phạm vi quản trị đặc quyền theo sản phẩm, cấu hình và giấy phép phù hợp. Không giả định một chiến dịch Entra access review tự liệt kê, đánh giá hoặc thu hồi mọi Azure RBAC assignment trực tiếp và quyền dữ liệu.

Trong tổ chức có sử dụng cơ chế này, một chiến dịch có thể giao người quản lý, owner hoặc người được chỉ định xem xét membership/assignment phù hợp, với quy tắc theo dõi kết quả và áp quyết định. Tính năng chính xác và cơ chế tự động áp kết quả phụ thuộc loại đối tượng/phiên bản cấu hình.

### 9.2. Azure RBAC theo scope

~~~text
Azure RBAC assignment
    = (principal ID, role definition ID, scope)

Các scope thường gặp:
    management group
      -> subscription
        -> resource group
          -> resource
~~~

Role **Reader** trên resource group khác Reader trên toàn subscription; một role assignment ở scope cha có thể kế thừa xuống resource. Review phải:

- Lấy principal ID, role ID và scope đầy đủ.
- Phân biệt quyền gán trực tiếp với quyền kế thừa.
- Phân biệt **Azure RBAC role** với **Microsoft Entra directory role**.
- Phân biệt management-plane permissions và data-plane permissions.
- Kiểm tra assignment conditions, deny assignments hoặc các hạn chế liên quan khi được hỗ trợ.
- Rà soát những principal có thể sửa IAM hoặc gán role cho người khác.

### 9.3. Managed identity và service principal

**System-assigned managed identity** thường gắn vòng đời với một tài nguyên. **User-assigned managed identity** có vòng đời độc lập và có thể được dùng chung bởi nhiều resource. Nếu ứng dụng bị xóa, user-assigned identity và các RBAC assignments vẫn có thể tồn tại.

Review workload phải xem: owner, ứng dụng đang dùng, role scope, federated identity credentials, client secret/certificate còn tồn tại, quyền của principal nguồn và khả năng tự gán/mở rộng quyền.

### 9.4. Guest và đối tác

Tài khoản guest cần có **sponsor**, lý do truy cập, resource scope và hạn kết thúc hợp đồng. Không coi việc đối tác vẫn xác thực thành công tại IdP của họ là lý do để giữ RBAC role. Quyền ở tenant đích cần được tổ chức sở hữu dữ liệu phê duyệt và thu hồi khi hết nhu cầu.

## 10. Google Cloud: review IAM binding và access boundary

Google Cloud thường cấp quyền thông qua **IAM allow policy bindings**: role được gắn với principal tại organization, folder, project hoặc resource hỗ trợ. Cần xét quyền từ phạm vi cha, điều kiện, deny policies và các giới hạn tổ chức có liên quan.

### 10.1. Những đối tượng cần review

| Đối tượng Google Cloud | Câu hỏi |
| --- | --- |
| **IAM allow binding** | Principal nào được gán role nào, tại scope nào? |
| **Basic/predefined/custom role** | Role có vượt permission tối thiểu không? |
| **IAM Conditions** | Điều kiện có thực sự giới hạn phạm vi và thời gian theo ý định không? |
| **Inherited bindings** | Role tại folder/organization có mở rộng đến project không? |
| **IAM deny / organization constraints** | Quyền/cấu hình nào bị chặn, không nhầm hạn chế với quyền cấp |
| **Service account** | Owner, role trên dữ liệu và workload dùng danh tính này |
| **Service account impersonation** | Ai có thể nhận credential hoặc hành động dưới service account mạnh hơn? |
| **Workforce/workload federation** | Pool/provider, issuer, attribute mappings, principal và IAM bindings |
| **Service account key** | Key tĩnh có còn cần, có owner và cơ chế rotation không? |

### 10.2. Công cụ phân tích

Các chức năng thuộc **Google Cloud Policy Intelligence** (chẳng hạn Policy Analyzer, IAM Recommender theo hỗ trợ và khả năng truy cập hiện hành) có thể giúp tìm đường quyền hoặc gợi ý giảm permissions. Kết quả phải được đánh giá bằng ngữ cảnh nghiệp vụ: role ít dùng có thể bảo vệ tác vụ khẩn cấp hoặc job định kỳ hiếm chạy.

Một binding tại project không được xem xét tách rời binding được kế thừa từ folder/organization. Tương tự, role trực tiếp hẹp không loại bỏ khả năng principal **impersonate** service account có quyền mạnh.

### 10.3. Ví dụ service account qua CI/CD

Một pipeline bên ngoài Google Cloud được phép impersonate service account để triển khai staging. Khi review, cần xem:

- Issuer OIDC nào và subject/environment nào được tin?
- Principal nguồn có thể impersonate những service account nào?
- Service account đích sở hữu role/binding nào tại project?
- Khi repository đổi tên hoặc ngừng, trust và binding có được thay/xóa không?
- Có key tĩnh của cùng service account nằm ngoài federation không?

**Xóa một pipeline không tự thu hồi service account IAM binding**. Phải quản lý vòng đời riêng của principal, role và trust.

## 11. Quyền qua IdP, SSO, SCIM và nhóm

Trong kiến trúc doanh nghiệp, HRIS có thể cung cấp trạng thái nhân sự; IdP quản lý user/group; SSO giúp đăng nhập; SCIM hoặc provisioning API đồng bộ user/group ở những dịch vụ hỗ trợ; cloud IAM gán role và kiểm tra quyền.

### 11.1. Vì sao review chỉ tại IdP là chưa đủ?

Một principal có thể:

- Nằm trong nhóm được ánh xạ tới role.
- Được gán role trực tiếp tại cloud.
- Có cloud-local user hoặc access key riêng.
- Được cho phép qua resource policy của một bucket.
- Có quyền assume role, impersonate service account hoặc dùng tài khoản đối tác.
- Giữ session đã cấp trước khi bị loại khỏi nhóm.

Gỡ thành viên khỏi nhóm IdP chỉ giải quyết **một đường cấp quyền**. Kết quả review phải đối soát ở cloud target.

### 11.2. SCIM không phải công cụ kiểm kê mọi IAM entitlement

**SCIM** chủ yếu giúp tạo, cập nhật và vô hiệu hóa người dùng/nhóm trong những hệ thống hỗ trợ. SCIM có thể là một phần của provisioning, nhưng không phải API chuẩn để tự động sửa **mọi** AWS IAM trust, Azure RBAC assignment hoặc Google Cloud IAM binding.

Nếu hệ thống cloud không đồng bộ loại entitlement cần gỡ qua SCIM, IGA phải dùng connector/API quản trị quyền riêng, rồi đọc lại trạng thái đích.

### 11.3. Role mapping và thuộc tính ABAC

Review cần thấy một mapping từ nhóm/thuộc tính tới role ở cloud:

~~~yaml
# Giả mã mô tả chính sách, không phải cấu hình deploy trực tiếp
source:
  identityType: employee
  group: platform-readers
target:
  cloud: azure
  scope: resource-group:platform-dev
  role: Reader
governance:
  owner: platform-team
  approval: standard-access-policy
  reviewCadence: risk-based
~~~

Nếu quyền phụ thuộc thuộc tính như department, project hoặc environment, phải biết thuộc tính được cập nhật từ nguồn nào và liệu principal có thể tự sửa nó để tăng quyền không. Review ABAC không chỉ là xem role: còn phải xem **thuộc tính và chính sách điều kiện** đang dẫn đến quyền đó.

## 12. Access review cho workload và tài khoản dịch vụ

**Non-human identities** thường không có người quản lý trực tiếp như nhân viên, nhưng có thể sở hữu quyền production lớn và sống lâu sau khi dịch vụ ngừng hoạt động. Không được loại chúng khỏi access review chỉ vì không nằm trong HRIS.

### 12.1. Nguồn vòng đời workload

Nguồn chuẩn có thể là service catalog, CMDB, repository, CI/CD system, deployment registry hoặc workflow phê duyệt. Một hồ sơ cần:

| Trường | Mục đích |
| --- | --- |
| Workload ID và cloud principal ID | Gắn danh tính kỹ thuật với service |
| Owner chính và owner dự phòng | Có người chịu trách nhiệm review/remediation |
| Runtime / repository / environment | Xác nhận workload còn tồn tại |
| Issuer/subject hoặc metadata identity | Kiểm tra trust đã cấp |
| Cloud account/project/subscription | Xác định đúng phạm vi |
| Roles, bindings, policies, impersonation | Tập đường truy cập thực tế |
| Credential type, TTL, key age | Phân biệt credential ngắn hạn và key tĩnh |
| Last deployment / usage | Tín hiệu tham khảo, không phải bằng chứng quyết định |
| Trạng thái lifecycle và ngày retire | Kích hoạt Mover/Leaver của workload |

### 12.2. Review một pipeline CI/CD

Pipeline chỉ triển khai staging không nên có role sửa IAM production. Reviewer phải xem **hai mặt**:

1. **Trust:** OIDC issuer, audience, subject, repository, branch/environment và ai có thể sửa pipeline.
2. **Permissions:** Role đích cho phép action/resource nào; liệu có quyền impersonate principal mạnh hơn không?

Nếu repository đã archive nhưng trust vẫn cho cả tổ chức CI assume role, đó là **quyền tồn dư** dù token có TTL ngắn. Thu hồi trust và quyền đích khi không còn nhu cầu, rồi xác minh token mới không thể nhận session ngoài phạm vi.

### 12.3. Khi nhân viên sở hữu workload nghỉ việc

Leaver của một kỹ sư có thể buộc **chuyển owner service account và pipeline**, xem lại các access key do người đó quản lý và quyền sửa workflow. Dịch vụ hợp lệ vẫn nên hoạt động bằng identity riêng. **Không tiếp tục sử dụng token cá nhân của người nghỉ việc** chỉ để tránh gián đoạn ứng dụng.

### 12.4. Không tự xóa role dùng chung

Nếu service A retire, thường cần thu hồi role binding, trust và credential riêng của A. Đừng xóa role definition đang dùng hợp lệ bởi service B và C. Ngược lại, nếu một role không còn bất kỳ chủ thể/ứng dụng hợp lệ nào cần, có thể đưa vào quy trình retire role sau khi đánh giá phụ thuộc.

## 13. Privileged access và quyền nâng đặc quyền gián tiếp

Nguy cơ không chỉ nằm ở những role có tên Owner/Administrator. Những quyền sau thường cần review rủi ro cao:

| Khả năng | Vì sao đặc biệt nhạy cảm? |
| --- | --- |
| Sửa IAM policy, role, trust hoặc assignment | Principal có thể tự tạo quyền mới |
| Tạo access key/service account token | Có thể tạo credential đại diện cho chủ thể mạnh |
| Impersonate service account hoặc assume privileged role | Có đường nâng quyền gián tiếp |
| Đọc secret của ứng dụng production | Có thể sử dụng credential của workload khác |
| Sửa CI/CD workflow hoặc IaC production | Có thể chạy mã bằng deployment role |
| Xóa backup, sửa audit logging | Cản trở phục hồi và điều tra |
| Quản lý identity provider hoặc nhóm cấp quyền cao | Thay đổi tập principal đủ điều kiện nhận quyền |
| Cấp quyền cross-account/cross-tenant | Mở đường cho chủ thể từ miền tin cậy khác |

### 13.1. Separation of Duties (SoD)

**SoD** ngăn một principal nắm các chức năng xung đột, chẳng hạn vừa tự phê duyệt vừa tự thực hiện thay đổi production có rủi ro lớn. Review cần kiểm tra **tổ hợp quyền** chứ không chỉ từng role riêng lẻ.

Ví dụ, một người vừa có quyền duyệt yêu cầu cấp IAM Administrator vừa có quyền tự sửa nhóm nhận role Administrator. Hai quyền cùng tồn tại có thể tạo khả năng vượt quy trình phê duyệt.

### 13.2. Privileged Identity Management, JIT và break-glass

Quyền đặc biệt nên được quản lý bằng cơ chế có thời hạn, phê duyệt, MFA phù hợp và audit khi nền tảng hỗ trợ. Nhưng **JIT access** là vòng đời entitlement có hạn, còn **temporary credential** là chứng thực phiên có TTL; phải kiểm tra cả hai.

Tài khoản **break-glass** hoặc role khẩn cấp có thể ít sử dụng nhưng vẫn hợp lệ trong kiến trúc phục hồi. Không tự revoke chỉ vì “last used” bằng không; cần có owner, chính sách kích hoạt, kiểm tra định kỳ và log mỗi lần dùng.

## 14. Rà soát quyền bên thứ ba và external users

Đối tác và nhà thầu có thể được liên kết qua SAML/OIDC, tài khoản guest, workforce federation hoặc cross-account trust. Rủi ro phát sinh khi hợp đồng đã hết nhưng principal nguồn vẫn xác thực được hoặc quyền ở đích chưa được gỡ.

Một access review cho external identity nên có:

1. **Sponsor nội bộ** còn làm việc và nhận trách nhiệm.
2. **Tổ chức đối tác** và nguồn danh tính được tin cậy.
3. **Mục đích cụ thể**: dự án, dữ liệu, support ticket, hợp đồng.
4. **Scope và role tối thiểu**, không cấp quyền toàn organization khi chỉ cần một resource.
5. **Ngày bắt đầu/kết thúc**, ngày review và trạng thái thỏa thuận.
6. **Bằng chứng thu hồi** khi sponsor thay đổi, hợp đồng hết hoặc principal không còn thuộc nhóm đủ điều kiện.

Không dựa hoàn toàn vào lời hứa “đối tác sẽ tự tắt tài khoản nhân viên nghỉ việc”. Doanh nghiệp sở hữu tài nguyên cloud cần có sự kiện Leaver nội bộ và cơ chế thu hồi quyền đích.

## 15. Review có điều kiện ABAC và chính sách kế thừa

Khi dùng **Attribute-Based Access Control (ABAC)**, quyền có thể phát sinh từ điều kiện về thuộc tính principal, tài nguyên và request. Ví dụ policy cho phép một workload đọc dữ liệu khi team của workload khớp với nhãn owner team của resource.

~~~yaml
# Giả mã policy, không dùng trực tiếp cho AWS/Azure/GCP
principal:
  status: active
  team: analytics
  workload: reporting-api
resource:
  environment: dev
  ownerTeam: analytics
request:
  action: reports.read
allowWhen:
  - principal.status == active
  - principal.team == resource.ownerTeam
  - resource.environment == dev
~~~

Review phải xác nhận:

- Thuộc tính nào là nguồn thẩm quyền? Ai được sửa?
- Khi nhân viên/workload Mover, thuộc tính có được cập nhật và đồng bộ đúng thời hạn không?
- Nhãn trên tài nguyên có thể bị principal tự sửa để nhận quyền rộng hơn không?
- Có chính sách cho phép khác bỏ qua điều kiện này không?
- Quyền ở scope cha hoặc deny/guardrail ảnh hưởng kết quả thế nào?

**Một nhãn do chính workload tự sửa không nên được xem là nguồn bảo mật độc lập để chứng nhận quyền của workload đó.**

## 16. Xử lý quyết định review và ngoại lệ

Một chiến dịch thường có nhiều kết quả đồng thời; nên tách **quyết định nghiệp vụ**, **trạng thái triển khai** và **kết quả xác minh**.

### 16.1. Mô hình trạng thái

~~~text
OPEN             Cần reviewer quyết định
DECIDED_KEEP     Được duyệt giữ, có lý do và thời hạn
DECIDED_REVOKE   Quyết định cần gỡ quyền
DECIDED_MODIFY   Quyết định cần thu hẹp/sửa quyền
EXCEPTION        Ngoại lệ có owner, risk acceptance và hạn
APPLY_PENDING    Đang thực thi thay đổi
APPLIED          Cloud API báo thay đổi thành công
VERIFIED         Đọc lại/quyền thực tế đạt điều kiện được kiểm tra
FAILED           Thay đổi hoặc kiểm chứng không thành công
ESCALATED        Cần thẩm quyền xử lý bổ sung
~~~

Trạng thái **APPLIED** chưa chứng minh effective access đã thay đổi đúng. Ngoài ra, một chiến dịch có nhiều grants có thể chỉ hoàn tất khi **mọi mục thuộc phạm vi** đều có quyết định và các việc thu hồi được xác minh hoặc ngoại lệ hợp lệ được theo dõi.

### 16.2. Ngoại lệ hợp lệ cần gì?

Ví dụ, quyền quản trị tạm phải được giữ thêm để ứng cứu sự cố đang diễn ra. Ngoại lệ phải ghi:

- Quyền, principal, resource scope và rủi ro cụ thể.
- Lý do nghiệp vụ, ticket, người đề xuất và người chấp thuận có thẩm quyền.
- Biện pháp giảm thiểu như MFA, giới hạn thao tác, theo dõi session.
- Hạn kết thúc ngoại lệ và hành động bắt buộc khi hết hạn.
- Owner theo dõi, thời điểm rà soát lại và bằng chứng đóng.

Không dùng ngoại lệ “chưa biết” hoặc “để tránh lỗi” vô thời hạn cho quyền production nhạy cảm.

### 16.3. Review không được phá vỡ dịch vụ

Khi một role không được sử dụng gần đây, trước khi thu hồi hãy:

1. Kiểm tra lịch tác vụ (backup, disaster recovery, quarterly batch).
2. Xác định dependency và owner của workload.
3. Đề xuất thay role rộng bằng quyền hẹp nếu có thể.
4. Thực hiện thay đổi có kiểm soát, khả năng rollback và giám sát.
5. Xác minh thao tác cần thiết vẫn hoạt động trong khi thao tác ngoài phạm vi bị từ chối.

An toàn không đồng nghĩa xóa mọi quyền không thấy log. Review tốt phải cân bằng **giảm quyền thừa** với **duy trì các khả năng nghiệp vụ hợp lệ**.

## 17. Automation và idempotent remediation

Tự động hóa review giúp xử lý hàng nghìn entitlements, nhưng **quyết định quan trọng cần bằng chứng và phê duyệt đúng mức**. Không tạo một hệ thống tự revoke production mà bỏ qua owner, thay đổi đồng thời hoặc dependency.

### 17.1. Giả mã workflow

~~~text
campaign = createReviewCampaign(scope, snapshotTime, riskPolicy)
entries = collectAndNormalizeEntitlements(campaign.scope)

for entry in entries:
    identity = resolveStablePrincipal(entry)
    owner = resolveResponsibleReviewer(entry.resource, identity)
    approved = calculateDesiredAccess(identity, entry.resource)
    actual = queryActualGrants(entry.resource, identity)
    risk = classifyRisk(entry, actual, approved)

    decision = requestAndValidateReview(owner, entry, risk)
    recordDecisionWithEvidence(campaign, entry, decision)

    if decision in {REVOKE, MODIFY}:
        if targetStateChangedSinceSnapshot(entry):
            refreshAndReapproveIfNeeded(entry)
        applyIdempotentChange(entry, decision)
        verify = readBackAndAssessEffectiveAccess(entry)
        if verify.matchesApprovedState:
            markVerified(entry, verify)
        else:
            recordExceptionWithOwnerAndDeadline(entry, verify)
    else if decision == KEEP:
        scheduleNextReview(entry)
    else:
        escalateForResolution(entry)
~~~

Đây là giả mã thiết kế hệ thống. Trong triển khai cần xử lý **pagination, rate limits, eventual consistency, concurrency, retries và quyền của automation** theo từng provider.

### 17.2. Bảo vệ tính nhất quán

- **Idempotency:** Cùng một quyết định được gửi lại không được tạo entitlement trùng hoặc thay đổi ngoài dự kiến.
- **Optimistic concurrency:** Kiểm tra grant/policy có bị sửa từ sau snapshot không; tránh xóa nhầm grant mới được phê duyệt.
- **Target-specific readback:** Đọc lại chính account/project/subscription đã được thay đổi.
- **Partial failure:** Azure thành công, AWS thất bại phải được ghi từng target, không đánh dấu cả campaign thành công.
- **Retry có giới hạn:** Có backoff và escalation; không retry vô hạn bằng quyền admin.
- **Auditability:** Liên kết event nguồn, review decision, API call và kết quả xác minh.
- **Separation of duties:** Automation chỉ có quyền đủ để thực hiện thao tác được duyệt.

### 17.3. Khi không thể xác định effective access chính xác

Đôi khi công cụ chỉ đưa ra **assigned grants** và không suy được đầy đủ điều kiện tài nguyên hoặc phiên đã phát. Không được tự ghi VERIFIED trên một giả định chưa được kiểm tra. Hãy ghi **độ phủ kiểm chứng**, các đường chưa được hỗ trợ, giới hạn API và ngoại lệ có trách nhiệm. Điều này đặc biệt quan trọng với cross-account trust, resource policies và quyền impersonation.

## 18. Bằng chứng kiểm toán và quyền riêng tư

Một bản ghi review có giá trị cần cho thấy **ai xác nhận quyền gì, vì sao, trên tài nguyên nào, khi nào và hệ thống đích thực sự thay đổi ra sao**.

### 18.1. Ví dụ bản ghi audit

~~~json
{
  "reviewId": "CLOUD-REVIEW-2026-Q4-0132",
  "sourceEvent": "JML-MOVER-0132",
  "principalId": "EMP-7316",
  "principalType": "employee",
  "target": {
    "provider": "aws",
    "resourceScope": "account:payments-production",
    "role": "payments-incident-operator"
  },
  "grantSource": "direct-account-assignment",
  "reviewer": "payments-service-owner",
  "decision": "REVOKE",
  "reason": "Chuyển sang đội analytics, không còn nhiệm vụ production",
  "decisionAt": "2026-11-23T08:10:00Z",
  "execution": {
    "status": "APPLIED",
    "appliedAt": "2026-11-23T08:12:00Z"
  },
  "verification": {
    "status": "PENDING",
    "checkedAt": null
  }
}
~~~

**Đây là dữ liệu giả định**, không phải tên API hoặc bản ghi nguyên bản của AWS. Trạng thái verification = PENDING thể hiện **chưa thể kết luận hoàn tất**, dù thao tác thu hồi đã báo thành công.

### 18.2. Bằng chứng cần lưu

| Loại bằng chứng | Ví dụ |
| --- | --- |
| Snapshot ban đầu | Principal/role/scope/nguồn cấp quyền tại thời điểm bắt đầu |
| Căn cứ nghiệp vụ | Chức trách, hợp đồng, ticket JML, owner |
| Decision trail | Reviewer ID, quyết định, lý do, thời điểm |
| Phê duyệt bổ sung | Approval cho quyền cao hoặc ngoại lệ |
| Change trail | API/cấu hình thay đổi, actor/automation, trạng thái |
| Readback | Quyền thực tế sau khi thay đổi, thời điểm kiểm tra |
| Effective-access evidence | Kết quả phân tích, simulation hoặc test được phép |
| Session/credential handling | Đã revoke/chặn tái cấp, TTL/ngoại lệ còn lại |
| Closure | Tình trạng VERIFIED, FAILED hoặc EXCEPTION và owner |

Log nên giữ theo chính sách dữ liệu và kiểm toán được duyệt; phân quyền truy cập log tương ứng độ nhạy cảm. **Không ghi access token, password, access key, refresh token, private key hoặc SAML assertion thô** vào bằng chứng review.

### 18.3. Phạm vi bảo mật và tối thiểu hóa dữ liệu

Reviewer không cần đọc mọi thông tin cá nhân trong HRIS. Chỉ cung cấp trạng thái employment, nhóm nghiệp vụ, owner và dữ liệu cần thiết để quyết định. Giới hạn quyền xem báo cáo privilege; tránh để một chiến dịch review làm lộ cấu trúc secret, danh sách tài khoản đặc quyền hoặc dữ liệu khách hàng cho người không có thẩm quyền.

## 19. Tình huống thực tế: Mover và workload mồ côi

Một công ty vận hành ứng dụng Learning trên AWS, Azure và Google Cloud. Có ba phạm vi:

| Phạm vi | Nhiệm vụ | Chủ sở hữu |
| --- | --- | --- |
| AWS account payments-production | Dịch vụ giao dịch production | Payment Platform |
| Azure resource group analytics-dev | Phân tích và thử nghiệm | Data Platform |
| Google Cloud project audit-reporting | Báo cáo log đã được chọn | Security Operations |

Nhân viên **Minh** có identity ID **EMP-7316**, đang chuyển từ Payment Platform sang Data Platform. Bên cạnh đó có pipeline **learning-report-exporter** đã ngừng nhưng service account vẫn tồn tại.

### 19.1. Snapshot trước review

| Principal | Quyền phát hiện | Nguồn cấp | Đánh giá ban đầu |
| --- | --- | --- | --- |
| EMP-7316 | PaymentIncidentOperator ở AWS production | Assignment trực tiếp | Không còn phù hợp chức trách mới |
| EMP-7316 | Reader ở analytics-dev | Nhóm Data | Có thể giữ nếu đúng nghiệp vụ |
| EMP-7316 | IAM viewer ở GCP audit-reporting | Binding qua nhóm cũ | Cần hỏi owner, có dấu hiệu thừa |
| learning-report-exporter | Đọc object và impersonate service account ở GCP | Federation + IAM binding | Workload đã retire, cần thu hồi |

**Không được suy luận** role Reader luôn vô hại: scope rộng, quyền kế thừa hoặc khả năng truy cập dữ liệu nhạy cảm vẫn có thể làm quyền này rủi ro.

### 19.2. Reviewer ra quyết định

Payment owner xác nhận Minh đã chuyển đội và chọn **REVOKE** quyền production. Data owner xác nhận vẫn cần Reader ở resource group dev với phạm vi hạn chế và chọn **KEEP**. Security owner kiểm tra quyền GCP, quyết định **REVOKE** nếu không còn nhu cầu. Platform owner xác nhận pipeline đã retire, cho phép xóa trust và service account impersonation không còn hợp lệ.

### 19.3. Remediation và xác minh

~~~mermaid
sequenceDiagram
    participant H as HRIS / Service catalog
    participant G as Review orchestrator
    participant O as Business / resource owner
    participant C as Cloud IAM target
    participant A as Audit
    H->>G: Mover và workload retirement
    G->>C: Truy vấn actual grants/trust
    C-->>G: Entitlements + scope
    G->>O: Giao quyền cần review, ngữ cảnh rủi ro
    O-->>G: Keep / Revoke / Modify
    G->>C: Thu hồi grant và trust không còn hợp lệ
    C-->>G: API applied
    G->>C: Readback + kiểm tra effective access
    C-->>G: Kết quả thực tế
    G->>A: VERIFIED hoặc EXCEPTION với bằng chứng
~~~

Sau thao tác, cần kiểm tra quyền còn lại qua scope kế thừa và đường cấp khác. Nếu một phiên cloud phát hành trước Mover còn sống, phải ghi rõ cơ chế xử lý và hạn dự kiến thay vì coi việc gỡ assignment là xóa phiên tức thời.

### 19.4. Khi có thay đổi trong lúc review

Giả sử team đã cấp cho Minh một quyền mới có phê duyệt sau thời điểm snapshot. Automation không được chỉ so hai bản dữ liệu cũ rồi vô tình thu hồi grant mới. Phải xác minh **nguồn sự kiện và version của entitlement** trước khi áp thay đổi. Nếu quyền mới hợp lệ, reviewer xác nhận lại phạm vi thực tế.

### 19.5. Kết quả cuối

Sự kiện Mover và workload retirement chỉ được xem đã xử lý về mặt kiểm soát khi:

- Quyền cũ không hợp lệ đã bị thu hồi ở từng cloud target.
- Workload không còn đường federation/impersonation trái dự kiến.
- Quyền được giữ có căn cứ và owner rõ.
- Những session/token chưa thể vô hiệu hóa ngay được quản trị và theo dõi.
- Kết quả readback/kiểm chứng cùng ngoại lệ có bằng chứng kiểm toán.

## 20. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ xuất danh sách user IdP | Bỏ sót cloud-local user, direct role và cross-account trust | Thu thập actual grants ở từng cloud target |
| Reviewer chỉ thấy tên role | Không hiểu scope và action thực tế | Hiển thị principal – role – resource – condition – risk |
| Manager xác nhận mọi quyền của chính mình | Thiếu độc lập, đặc biệt với đặc quyền cao | Reviewer có thẩm quyền độc lập theo rủi ro |
| Không phản hồi mặc định là Keep | Quyền lỗi thời được giữ vô hạn | Escalation, thời hạn và chính sách xử lý rõ |
| Gỡ group nhưng không readback | Quyền direct/inherited có thể vẫn còn | Đối soát tại target và effective access |
| Đánh dấu hoàn tất ngay khi API trả 200 | Lỗi đồng bộ, policy drift hoặc session còn sống | Phân biệt APPLIED với VERIFIED |
| Dùng last-used làm điều kiện thu hồi duy nhất | Gỡ quyền của batch job, DR hoặc break-glass hợp lệ | Kết hợp owner, mục đích và lịch tác vụ |
| Bỏ workload/service account khỏi chiến dịch | Key/role mồ côi không ai chịu trách nhiệm | Workload registry, owner và review riêng |
| Dùng cùng một reviewer cho mọi cloud | Không hiểu RBAC và scope của provider khác | Giao đúng resource/data/IAM owner |
| Nhầm SCP/deny với quyền cấp | Đánh giá sai effective permissions | Phân biệt lớp Allow và restriction |
| Bỏ qua service account impersonation | Principal giữ đường nâng quyền gián tiếp | Phân tích cả source và target principal |
| Quyền ngoại lệ không có hạn | Privileged access tồn tại không kiểm soát | Owner, approval, expiry và theo dõi đóng |
| Chỉ chạy review định kỳ mà không gắn JML | Leaver chờ tới kỳ rà soát sau | Event-driven revocation và review xác minh |
| Không xử lý grant biến đổi sau snapshot | Automation xóa nhầm quyền mới hợp lệ | Concurrency/version check và reapproval |
| Review xong nhưng không lưu evidence | Không chứng minh được quyền đã thu hồi | Decision trail, change log và readback |

## 21. Chỉ số và mục tiêu vận hành

| Chỉ số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **Coverage** | Tỷ lệ account/project/resource và principal thuộc phạm vi đã được kiểm kê | Không chỉ đếm identity trong IdP |
| **On-time review completion** | Tỷ lệ review hoàn tất trong hạn | Không đồng nghĩa remediation đã xong |
| **Verified remediation rate** | Tỷ lệ quyết định REVOKE/MODIFY đã được xác minh tại đích | Chỉ tính VERIFIED, không tính APPLIED |
| **Stale grant count** | Số quyền không còn hợp lệ còn tồn tại | Phân loại mức đặc quyền và môi trường |
| **P95 revoke time after Leaver** | Từ thời điểm Leaver có hiệu lực đến khi quyền được xác minh thu hồi | Phân nhóm cloud và loại quyền |
| **Orphan principal rate** | Service account/guest/role không có owner hợp lệ | Ưu tiên principal đặc quyền |
| **Privileged access review coverage** | Tỷ lệ role IAM mutation, secret, production admin được rà soát | Kết hợp quyền gián tiếp |
| **Exception age** | Thời gian ngoại lệ vẫn mở | Không để ngoại lệ quá hạn |
| **Policy drift count** | Số thay đổi IAM ngoài nguồn đã duyệt | Cần kiểm tra và tái chứng nhận |
| **Reviewer disagreement / escalation** | Trường hợp thiếu bối cảnh hoặc mâu thuẫn quyết định | Gợi ý cải thiện role catalog |
| **False-positive revoke / disruption** | Quyết định sai làm gián đoạn công việc hoặc dịch vụ | Đo để cải thiện ngữ cảnh và dependency |
| **Repeat stale grants** | Quyền cũ xuất hiện trở lại sau remediation | Kiểm tra provisioning hoặc nguồn cấp chưa sửa |

Một hệ thống có tỷ lệ hoàn thành 100% nhưng vẫn còn quyền production đã quyết định revoke chưa được áp dụng **không phải hệ thống review hiệu quả**. Báo cáo phải trình bày đồng thời **quyết định**, **thực thi** và **xác minh**.

## 22. Bài tập tự kiểm tra

### Bài 1 — Mover đã đổi IdP group

Một nhân viên chuyển đội; nhóm IdP cũ đã được xóa, nhưng AWS IAM role vẫn cho phép họ assume thông qua một trust khác.

**Câu hỏi:** Có thể chứng nhận Mover hoàn tất không?

**Đáp án:** Chưa. Phải xác định trust và đường quyền còn hợp lệ hay không, thu hồi nếu không được duyệt, xử lý session cũ theo khả năng hỗ trợ và xác minh tại AWS account đích.

### Bài 2 — Azure Reader ở scope nào?

Reviewer thấy role Reader nhưng không thấy principal ID hoặc scope. Một người cho rằng có thể giữ vì role “chỉ đọc”.

**Đáp án:** Không đủ thông tin. Cần biết role ID, scope, quyền kế thừa, loại dữ liệu, owner và mục đích. Reader ở scope cha có thể bao phủ nhiều tài nguyên hơn một assignment tại resource group dev.

### Bài 3 — Google service account không được dùng gần đây

Một service account chỉ được dùng khi khôi phục thảm họa, nên không xuất hiện trong log sử dụng gần đây.

**Đáp án:** Không tự revoke. Phải xác nhận runbook DR, owner, quyền thực sự cần, bảo vệ credential và lịch kiểm tra; thu hẹp quyền thừa hoặc thay đổi sau review phù hợp.

### Bài 4 — Reviewer chọn Revoke nhưng campaign đóng

Người quản lý quyết định thu hồi một Azure RBAC assignment. API sửa quyền báo lỗi; campaign vẫn hiển thị Done.

**Đáp án:** Đây là lỗi kiểm soát. Cần tách quyết định khỏi remediation, giữ trạng thái FAILED/ESCALATED, retry có kiểm soát và chỉ ghi VERIFIED khi readback tại Azure target xác nhận quyền đạt trạng thái mong muốn.

### Bài 5 — Pipeline bị xóa

Repository CI/CD đã archive nhưng Google Cloud federation provider vẫn tin cả tổ chức CI, và principal còn quyền impersonate service account có role Editor.

**Đáp án:** Phải review trust và quyền impersonation lẫn role của service account đích; thu hồi hoặc giới hạn đúng scope, kiểm tra token exchange và kết quả effective access. Xóa repo đơn thuần không đủ.

### Bài 6 — Ngoại lệ quyền production

Một kỹ sư cần giữ quyền admin thêm hai ngày để xử lý incident, nhưng không có thời hạn hoặc approver rõ ràng.

**Đáp án:** Chưa phải ngoại lệ được quản trị. Cần xác định scope tối thiểu, người phê duyệt độc lập, thời hạn, điều kiện sử dụng, giám sát và kiểm chứng sau kết thúc.

## 23. Checklist triển khai cloud access review

1. **Rõ phạm vi:** Account/subscription/project, environment, loại principal và cấp độ rủi ro.
2. **Đủ inventory:** User, group, role, policy, trust, resource grant, key, service account và external principal.
3. **Định danh bền vững:** Nối HRIS/IdP/workload registry bằng stable ID và issuer/subject.
4. **Scope chính xác:** Xác định role ở cấp organization, folder, subscription, resource group hay resource.
5. **Nguồn cấp quyền rõ:** Direct, qua nhóm, kế thừa, cross-account, impersonation, federation.
6. **Ngữ cảnh đầy đủ:** Công việc, owner, approval, dữ liệu nhạy cảm, ngày bắt đầu và hết hạn.
7. **Reviewer có thẩm quyền:** Business owner, data owner, security/IAM khi cần; tránh tự chứng nhận quyền đặc biệt.
8. **Theo rủi ro:** Privileged, production, external, non-human và break-glass có kiểm soát riêng.
9. **JML đúng hạn:** Joiner cấp đúng, Mover rút quyền cũ, Leaver thu hồi không chờ review định kỳ.
10. **Quyết định rõ:** KEEP, REVOKE, MODIFY, EXCEPTION hoặc ESCALATE với lý do.
11. **Không mặc định Keep:** Quyền thiếu owner hoặc review quá hạn phải được xử lý.
12. **Remediation an toàn:** Idempotent, kiểm tra thay đổi sau snapshot và dependency.
13. **Readback bắt buộc:** Truy vấn trạng thái cloud và đường quyền hiệu lực sau thay đổi.
14. **Session/credential được xét:** Không mặc định disable IdP sẽ hủy mọi temporary credential.
15. **Ngoại lệ có hạn:** Risk owner, approval, deadline và kế hoạch giảm rủi ro.
16. **Bằng chứng an toàn:** Lưu quyết định, người thực hiện, thời gian, kết quả; không lộ token/secret.
17. **Phản hồi vào thiết kế:** Tìm nguyên nhân cấp quyền thừa và sửa role catalog/provisioning thay vì chỉ dọn hậu quả.

## 24. Tổng kết

**Cloud access review** là vòng kiểm soát xác nhận **đúng người hoặc workload – đúng quyền – đúng tài nguyên – đúng thời điểm** trong AWS, Azure và Google Cloud. Nó phải bao gồm cả quyền qua IdP/SSO/SCIM, role assignment, IAM binding, trust, resource policy, service account, workload federation và những đường nâng đặc quyền gián tiếp.

Quy trình tốt không chỉ yêu cầu reviewer bấm “Approve”; nó kết nối **nguồn danh tính, trạng thái JML, inventory quyền, người có trách nhiệm, quyết định, remediation và readback**. Trong Joiner–Mover–Leaver, các quyền cũ phải được thu hồi kịp thời, không phụ thuộc vào kỳ review định kỳ. Kết quả chỉ có giá trị kiểm toán khi **quyền thực tế ở cloud target đã được xác minh**, ngoại lệ có owner và thời hạn, đồng thời mọi bằng chứng được bảo vệ thích hợp.
