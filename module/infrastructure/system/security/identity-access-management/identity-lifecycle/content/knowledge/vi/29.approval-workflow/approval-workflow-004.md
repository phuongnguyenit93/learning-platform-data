# Resource owner approval – phê duyệt quyền truy cập bởi chủ sở hữu tài nguyên

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **resource owner approval** trong **Identity and Access Management (IAM)**, phân biệt quyết định của chủ sở hữu tài nguyên với xác thực người dùng, phê duyệt cấp quản lý và thao tác provision tài khoản.
- Nhận diện **resource owner, application owner, data owner, manager, requester, approver, IAM/IGA operator, Policy Decision Point (PDP) và Policy Enforcement Point (PEP)**; hiểu trách nhiệm của từng vai trò.
- Thiết kế **resource ownership registry** đủ tin cậy để định tuyến yêu cầu tới đúng người có thẩm quyền, bao gồm delegation, owner vắng mặt và thay đổi owner.
- Mô hình hóa yêu cầu quyền theo **subject, resource, action, scope, tenant, environment, justification, time window, approval chain** và các ràng buộc.
- Áp dụng **least privilege, Segregation of Duties (SoD), maker–checker, deny by default** và kiểm soát phê duyệt chính mình.
- Mô tả vòng đời **submitted → evaluated → pending approval → approved/rejected → provisioned → verified → revoked/expired** và xử lý timeout, retry, concurrency, request cũ.
- Giải thích mối liên hệ giữa phê duyệt, **Joiner–Mover–Leaver (JML)**, **IdP/SSO**, **SCIM**, **RBAC/ABAC**, quyền đặc quyền, service account và kiểm toán.
- Xây dựng dữ liệu audit, tiêu chí reconciliation, bộ kiểm thử âm tính và quy trình xử lý ngoại lệ để giảm **quyền truy cập tồn dư**.

## 1. Resource owner approval là gì?

**Resource owner approval** là bước **chủ sở hữu có thẩm quyền của một tài nguyên xem xét và chấp thuận hoặc từ chối một yêu cầu cấp/quản lý quyền truy cập vào tài nguyên đó** theo mục đích, phạm vi và chính sách của tổ chức.

Ví dụ: nhân viên phòng kinh doanh xin quyền xem bộ dữ liệu doanh thu của đơn vị Finance. Người quản lý trực tiếp có thể xác nhận nhân viên có nhu cầu công việc; nhưng **chủ sở hữu dữ liệu Finance** mới là người chịu trách nhiệm đánh giá yêu cầu có phù hợp với **mức nhạy cảm, phạm vi dữ liệu, chính sách chia sẻ và trách nhiệm sử dụng** hay không.

Phê duyệt không tự động có nghĩa hệ thống đã cấp quyền. Trong một workflow an toàn:

1. Xác minh danh tính và trạng thái quan hệ làm việc.
2. Xác định chính xác tài nguyên và quyền được yêu cầu.
3. Kiểm tra policy, role eligibility, SoD và mức rủi ro.
4. Định tuyến tới **resource owner đúng thẩm quyền**.
5. Ghi quyết định phê duyệt hoặc từ chối cùng phạm vi và thời hạn.
6. Nếu được phép, provisioning hoặc JIT activation thực thi quyền ở hệ thống đích.
7. **Reconciliation/PEP** kiểm chứng quyền thực tế đúng với quyết định; tiếp tục thu hồi khi hết hạn, Mover hoặc Leaver.

**Điểm cốt lõi:** phê duyệt là **một điều kiện quản trị quyền**, không thay thế kiểm tra chính sách hay thực thi quyền tại API.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, resource owner approval nối dữ liệu HRIS, identity proofing và hồ sơ quyền với vòng đời **Joiner–Mover–Leaver**. Nó giúp bảo đảm quyền ở **IdP, SSO, SCIM, ứng dụng, cloud, RBAC/ABAC và tài khoản dịch vụ** chỉ được cấp trong phạm vi hợp lệ, rồi được đối soát và thu hồi thay vì tích lũy vô thời hạn.

### 1.1. Phê duyệt không đồng nghĩa những việc gì?

| Hoạt động | Mục đích | Tại sao khác resource owner approval? |
| --- | --- | --- |
| **Authentication** | Chứng minh ai đang đăng nhập | Đăng nhập đúng không chứng minh nhu cầu đọc dữ liệu |
| **Identity proofing** | Xác minh danh tính ngoài đời/hồ sơ | Không quyết định người đó được dùng tài nguyên nào |
| **Manager approval** | Xác nhận nhu cầu công việc, nhiệm vụ hoặc ngân sách | Manager không mặc nhiên là owner của dữ liệu đích |
| **Resource owner approval** | Quyết định yêu cầu có phù hợp với quyền sở hữu tài nguyên | Không tự kích hoạt một role trên hệ thống đích |
| **Security/SoD review** | Kiểm chính sách bảo mật, xung đột nhiệm vụ và rủi ro | Owner không được tự bỏ qua một security DENY |
| **Provisioning** | Thực thi tạo account, group, entitlement | Kết quả kỹ thuật có thể chậm hoặc thất bại |
| **Authorization enforcement** | Chặn/cho phép từng thao tác tại tài nguyên | Có thể từ chối dù trước đó đã được duyệt |
| **Access certification** | Rà soát lại quyền đã tồn tại | Là kiểm tra định kỳ hoặc theo sự kiện, không thay phê duyệt ban đầu |

## 2. Các vai trò và ranh giới trách nhiệm

| Vai trò | Trách nhiệm chính | Không nên được phép mặc định |
| --- | --- | --- |
| **Requester** | Nêu nhu cầu, resource, action, lý do và thời hạn | Tự phê duyệt quyền của mình |
| **Beneficiary / Subject** | Identity thực nhận quyền; có thể khác requester | Tự nâng quyền bằng cách đổi đối tượng trong request |
| **Line manager** | Xác nhận vai trò công việc, trách nhiệm và thời gian cần quyền | Duyệt thay resource owner ngoài thẩm quyền |
| **Resource owner** | Chịu trách nhiệm quyết định ai được dùng resource ở phạm vi nào | Bỏ qua security deny/SoD hoặc tự cấu hình quyền vượt policy |
| **Data owner** | Quyết định mục đích sử dụng dữ liệu, phân loại và chia sẻ | Cấp quyền hạ tầng nếu không sở hữu hạ tầng |
| **Application/system owner** | Xác định trách nhiệm vận hành hệ thống và phạm vi ứng dụng | Tự đại diện cho mọi data owner nếu không có ủy quyền |
| **Delegated approver** | Duyệt thay owner trong phạm vi và thời gian được ủy quyền | Mở rộng quyền ủy quyền hoặc tự ủy quyền |
| **Security/IAM/IGA** | Policy, SoD, định tuyến, workflow, giám sát và đối soát | Hợp thức hóa yêu cầu chỉ vì workflow cần hoàn thành |
| **Provisioning connector** | Áp thay đổi tới hệ thống đích qua API/SCIM | Tự chọn phạm vi entitlement ngoài quyết định |
| **PDP/PEP** | Đánh giá và thực thi authorization hiện hành | Chấp nhận approval như quyền vượt mọi policy |
| **Auditor/reviewer** | Kiểm chứng chuỗi yêu cầu, phê duyệt và tác động | Sửa lịch sử approval đã được lưu |

### 2.1. Chủ sở hữu tài nguyên không nhất thiết là người quản lý nhân sự

Giả sử người dùng **Lan** thuộc nhóm Operations xin truy cập cơ sở dữ liệu khách hàng do Product sở hữu:

- Manager Operations biết Lan có đang làm dự án hay không.
- Data owner Product biết phạm vi dữ liệu, mức phân loại và giới hạn chia sẻ.
- System owner Database biết tác động kỹ thuật của việc tạo DB account.
- Security kiểm điều kiện về dữ liệu nhạy cảm, SoD hoặc quyền đặc quyền.
- IAM/IGA điều phối để không tạo nhiều quyền độc lập không có trách nhiệm rõ ràng.

Có thể cần **một hoặc nhiều bước phê duyệt**, tùy loại quyền và policy. Không mặc định luôn cần tất cả vai trò vì điều đó có thể gây chậm trễ không cần thiết.

### 2.2. Ai là người chịu trách nhiệm cuối cùng?

**Accountable resource owner** chịu trách nhiệm về quyết định liên quan quyền sử dụng tài nguyên. Tuy nhiên trách nhiệm này bị giới hạn bởi **chính sách an ninh, pháp lý, quyền riêng tư và mô hình phân tách nhiệm vụ**. Owner có thể từ chối quyền dù manager đã chấp thuận, và cũng không thể cấp một quyền mà chính sách toàn hệ thống đã cấm.

## 3. Resource ownership registry – nguồn thẩm quyền để định tuyến

Không thể triển khai resource owner approval đáng tin nếu hệ thống không biết **ai sở hữu tài nguyên nào**, với phạm vi và trạng thái hiện hành ra sao.

Một **resource ownership registry** có thể chứa:

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **resourceId** | `fin-dataset-2026` | Định danh ổn định của tài nguyên |
| **resourceType** | `DATASET`, `APPLICATION`, `CLOUD_ROLE` | Loại tài nguyên và cách kiểm quyền |
| **tenant / environment** | `tenant-a`, `production` | Phạm vi sở hữu |
| **ownerIdentityId** | `person-502` | Người được công nhận là owner |
| **ownerTeamId** | `finance-data-owners` | Nhóm chịu trách nhiệm nếu được phép |
| **ownerEffectiveFrom / Until** | Timestamp có timezone | Thời gian hiệu lực của ownership |
| **classification** | `CONFIDENTIAL` | Cấp độ dữ liệu và điều kiện phê duyệt |
| **approvalPolicyId/version** | `finance-access/v4` | Quy tắc định tuyến và kiểm tra |
| **delegateReferences** | `delegation-71` | Các ủy quyền có giới hạn |
| **lifecycleStatus** | `ACTIVE`, `RETIRED` | Trạng thái tài nguyên |
| **lastVerifiedAt** | Timestamp | Lần xác minh gần nhất |
| **sourceSystem / version** | Catalog, CMDB, resource registry | Nguồn xác nhận và version |

**Tên resource hoặc email của owner không nên là khóa bền vững duy nhất.** Tên có thể đổi hoặc email có thể được tái sử dụng. Nên dùng ID do nguồn đáng tin quản lý, cùng version/quan hệ sở hữu.

### 3.1. Owner có thể thay đổi

Tài nguyên Finance chuyển quyền quản lý từ một nhóm sang nhóm khác. Nếu workflow đã mở trước sự kiện chuyển owner, yêu cầu phê duyệt vẫn đang nằm trong inbox của người cũ.

Hệ thống phải quy định:

1. Ownership nào có hiệu lực khi yêu cầu được tạo?
2. Ownership nào phải được dùng **khi người duyệt bấm Approve**?
3. Khi owner thay đổi, quyết định đang chờ có cần định tuyến lại không?
4. Một approval từ owner cũ còn hợp lệ để cấp quyền sau thời điểm bàn giao không?

Đối với quyền nhạy cảm, nên **kiểm lại thẩm quyền tại thời điểm quyết định và trước provisioning**. Không cho phép một owner đã hết thẩm quyền duyệt quyền mới chỉ vì request được tạo từ trước.

### 3.2. Tài nguyên không có owner

Nếu registry không có owner đáng tin:

- Không tự chọn người đầu tiên có role Admin làm approver.
- Không mặc định requester hoặc manager thành resource owner.
- Đưa yêu cầu vào trạng thái **OWNER_UNRESOLVED** hoặc chặn cấp quyền.
- Chuyển xử lý ownership qua quy trình đã được phê duyệt, có accountable team.
- Chỉ tiếp tục workflow khi ownership được xác minh hoặc có ngoại lệ hợp lệ.

**Không có owner không đồng nghĩa bỏ qua bước owner approval.**

## 4. Xác định và ủy quyền cho approver

Một người được phép approve khi **đúng identity, quyền sở hữu hoặc ủy quyền còn hiệu lực, resource scope và loại quyết định**.

### 4.1. Owner cá nhân, owner nhóm và delegated owner

- **Named owner:** identity cụ thể được registry chỉ định.
- **Owner group:** nhóm có trách nhiệm; policy xác định ai trong nhóm có quyền ra quyết định và có cần quorum hay không.
- **Delegated approver:** người được ủy quyền trong một thời gian, tài nguyên và cấp độ quyền cụ thể.
- **Fallback/escalation owner:** người/nhóm tiếp nhận khi owner vắng hoặc quá hạn theo policy.

Không phải ai là thành viên của một nhóm chat `finance-owners` đều được phép Approve. Phải kiểm **membership trong hệ thống định danh đáng tin và thẩm quyền áp dụng cho resource**.

### 4.2. Ví dụ bản ghi delegation

~~~json
{
  "delegationId": "delegation-71",
  "delegatorIdentityId": "person-502",
  "delegateIdentityId": "person-609",
  "resourceIds": ["fin-dataset-2026"],
  "allowedApprovalKinds": ["READ_ACCESS"],
  "allowedRiskTiers": ["LOW", "MEDIUM"],
  "validFrom": "2026-12-01T00:00:00+07:00",
  "validUntil": "2026-12-15T23:59:59+07:00",
  "reason": "owner-on-leave",
  "status": "ACTIVE"
}
~~~

Đây là **JSON minh họa**, không phải schema bắt buộc của một sản phẩm IGA.

Tại thời điểm duyệt phải xác minh **delegator thực sự sở hữu tài nguyên, delegate còn ACTIVE, delegation không hết hạn/chưa bị thu hồi, loại permission và risk tier nằm trong scope**.

### 4.3. Ủy quyền không mở rộng quyền

Một delegate được duyệt READ_ACCESS không được tự nâng thành OWNER_ADMIN hoặc cấp wildcard cho production. Người được ủy quyền cũng không được **ủy quyền tiếp** nếu không có quy định rõ ràng.

Một owner đã Leaver hoặc bị thay thế có thể không còn thẩm quyền; những delegation phụ thuộc owner đó cũng cần được đánh giá và thu hồi theo policy.

## 5. Một access request cần có những dữ liệu nào?

Resource owner cần thông tin **đủ chính xác để quyết định**, không phải một nút Approve cho yêu cầu mơ hồ.

### 5.1. Mô hình dữ liệu yêu cầu

| Thuộc tính | Ví dụ | Tại sao cần |
| --- | --- | --- |
| **requestId** | `access-req-884` | Theo dõi duy nhất, idempotency |
| **requesterIdentityId** | `person-1042` | Ai mở yêu cầu |
| **beneficiaryIdentityId** | `person-1042` | Ai thực nhận quyền |
| **resourceId** | `fin-dataset-2026` | Tài nguyên cụ thể |
| **resourceVersion** | `32` | Phát hiện owner/classification thay đổi |
| **action/entitlement** | `dataset.read` | Quyền chính xác |
| **scope** | `tenant-a`, Finance only | Không cấp rộng hơn nhu cầu |
| **environment** | `production` | Phân biệt dev/prod |
| **purpose/justification** | `quarterly-report` | Lý do nghiệp vụ |
| **requestedFrom/Until** | Khoảng thời gian có timezone | Tránh quyền không hạn |
| **relationshipId** | `employment-1042-A` | Xác định quan hệ công việc |
| **riskTier** | `HIGH` | Xác định chuỗi approval và controls |
| **approvalPolicyVersion** | `finance-access/v4` | Quy tắc áp dụng |
| **sourceTicket** | `CHG-2041` | Gắn bối cảnh thay đổi |
| **requestStatus** | `PENDING_RESOURCE_OWNER` | Trạng thái workflow |

### 5.2. JSON minh họa

~~~json
{
  "requestId": "access-req-884",
  "requesterIdentityId": "person-1042",
  "beneficiaryIdentityId": "person-1042",
  "relationshipId": "employment-1042-A",
  "resource": {
    "resourceId": "fin-dataset-2026",
    "resourceVersion": 32,
    "tenantId": "tenant-a",
    "environment": "production"
  },
  "entitlement": "dataset.read",
  "requestedScope": {
    "ownerDepartment": "Finance",
    "exportAllowed": false
  },
  "justification": "quarterly-report",
  "requestedFrom": "2026-12-01T09:00:00+07:00",
  "requestedUntil": "2026-12-15T18:00:00+07:00",
  "riskTier": "MEDIUM",
  "approvalPolicyVersion": "finance-access/v4"
}
~~~

Tất cả giá trị trên chỉ để **minh họa cấu trúc**. Trong sản phẩm thực tế, nguồn của `resourceVersion`, `riskTier`, actor và scope phải được xác minh; không coi JSON từ frontend là dữ liệu quyền đã được kiểm chứng.

### 5.3. Yêu cầu mơ hồ nên xử lý thế nào?

Yêu cầu “cấp toàn quyền Finance cho Lan” không xác định:

- Tài nguyên nào thuộc Finance?
- Read, write, approve, delete hay grant role?
- Dữ liệu của tenant/pháp nhân nào?
- Production hay test?
- Có quyền export toàn bộ không?
- Trong bao lâu, liên quan nhiệm vụ nào?

Chính sách an toàn nên **yêu cầu bổ sung thông tin, chọn role được định nghĩa sẵn hoặc từ chối**, không tự diễn giải thành một nhóm quyền quản trị rộng.

## 6. Phê duyệt là điều kiện, không phải quyền đã thực thi

Một approval có thể là **bằng chứng điều kiện cấp quyền**: owner chấp thuận một subject dùng resource/action trong scope và thời hạn đã nêu.

Nhưng còn các bước khác:

~~~text
Request hợp lệ
  -> Resource owner quyết định
  -> Security/SoD policy cho phép
  -> IAM/IGA tạo desired entitlement
  -> Connector provision role/account
  -> Target xác nhận applied state
  -> PEP đánh giá và thực thi quyền ở từng thao tác
  -> Reconciliation kiểm tra observed access
~~~

### 6.1. Approval không thể bỏ qua explicit DENY

Ví dụ người dùng đã bị security block nhưng resource owner vẫn nhấn Approve. PDP/IGA phải từ chối cấp quyền hoặc không thực thi request vì security block cao hơn approval.

Một policy minh họa:

~~~text
PERMIT access.grant WHEN
    request.approvedByCurrentResourceOwner
    AND request.approvalIsForExactScope
    AND subject.lifecycleStatus == ACTIVE
    AND subject.hasVerifiedIdentityLink
    AND requestedEntitlement.isAllowedByPolicy
    AND request.hasNoSoDConflict
    AND request.withinTimeWindow
    AND NOT subject.securityBlocked
ELSE DENY
~~~

Đây là mã giả, không phải cú pháp PBAC/ABAC chuẩn.

### 6.2. Phê duyệt và trạng thái ứng dụng đích

Nếu connector SCIM/API báo success, điều đó chưa chứng minh role đã được áp theo đúng phạm vi, còn API có thể cache quyền trước đó.

Phải phân biệt:

- **APPROVED:** chủ sở hữu đồng ý trong phạm vi yêu cầu.
- **PROVISIONING:** đang áp thay đổi.
- **PROVISIONED:** hệ thống đích báo đã áp.
- **VERIFIED:** đọc lại hoặc kiểm tra hiệu lực quyền đã đúng.
- **ACTIVE_ACCESS:** quyền đang có hiệu lực trong thời gian được phép.
- **REVOKED/EXPIRED:** đường cấp quyền không còn hợp lệ.
- **EXCEPTION:** trạng thái chưa thể xác minh, có owner xử lý.

## 7. Kiến trúc workflow với IAM/IGA, PDP/PEP và SCIM

~~~mermaid
flowchart LR
    U["Requester / Beneficiary"] --> PORTAL["Access request portal"]
    HR["HRIS / Identity Registry"] --> PIP["PIP: JML, manager, roles"]
    CAT["Resource catalog / Owner registry"] --> PIP
    PORTAL --> WF["Workflow engine"]
    PIP --> WF
    WF --> PDP["PDP: Eligibility / SoD / Risk"]
    PDP --> ROUTE["Owner resolution + approval routing"]
    ROUTE --> OWNER["Resource owner / Delegate"]
    OWNER --> WF
    WF --> PROV["Provisioning: SCIM / API / Directory"]
    PROV --> APP["Target application / Resource"]
    APP --> PEP["PEP: Resource authorization"]
    WF --> AUD["Audit / Decision log"]
    PROV --> REC["Reconciliation"]
    APP --> REC
    REC --> AUD
    PEP --> AUD
~~~

Sơ đồ thể hiện các vai trò logic, không bắt buộc tất cả doanh nghiệp sử dụng một dịch vụ workflow hay một PDP độc lập. Điều quan trọng là **nguồn dữ liệu, thẩm quyền owner, quyết định policy, thao tác cấp quyền và bằng chứng** được liên kết không mơ hồ.

### 7.1. Điểm kiểm tra tại từng ranh giới

1. **Submit request:** xác thực requester; kiểm beneficiary không bị giả mạo.
2. **Resolve owner:** đọc registry có nguồn và độ mới, không nhận email approver từ request.
3. **Evaluate eligibility:** xác định JML status, tenant, workerType, role, SoD và classification.
4. **Owner decision:** kiểm đúng actor có thẩm quyền, approval scope và expiry.
5. **Provisioning:** kiểm lại trạng thái hiện hành, không cấp vì một approval cũ.
6. **Enforcement:** chặn thao tác ngoài resource/action/scope dù role đã được cấp.
7. **Reconciliation:** xác nhận actual entitlement và kiểm quyền tồn dư.
8. **Audit:** lưu chain từ request tới decision và observed state.

## 8. State machine của resource owner approval

Một workflow có thể có các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SUBMITTED: Submit
    SUBMITTED --> VALIDATING: Validate subject/resource/policy
    VALIDATING --> REJECTED: Invalid / policy DENY
    VALIDATING --> OWNER_UNRESOLVED: No valid owner
    OWNER_UNRESOLVED --> VALIDATING: Ownership resolved
    VALIDATING --> PENDING_OWNER: Approver resolved
    PENDING_OWNER --> REJECTED: Owner denies
    PENDING_OWNER --> EXPIRED: Timeout / no valid decision
    PENDING_OWNER --> APPROVED: Owner approves exact scope
    APPROVED --> REVALIDATING: Before provisioning
    REVALIDATING --> REJECTED: Identity/policy/resource changed
    REVALIDATING --> PROVISIONING: Still eligible
    PROVISIONING --> FAILED: Target error
    FAILED --> PROVISIONING: Controlled retry
    PROVISIONING --> VERIFYING: Connector reported success
    VERIFYING --> ACTIVE: Observed entitlement correct
    VERIFYING --> EXCEPTION: Mismatch / cannot verify
    ACTIVE --> REVOKING: Expiry / Mover / Leaver
    REVOKING --> REVOKED: Observed no unauthorized access
    REVOKING --> EXCEPTION: Failed revoke
    REJECTED --> [*]
    EXPIRED --> [*]
    REVOKED --> [*]
~~~

Đây là **state machine minh họa**, không phải tiêu chuẩn bắt buộc. Từng sản phẩm có thể tách bước manager, owner, security review hoặc JIT activation.

### 8.1. Các invariant an toàn

- Không có `PENDING_OWNER → ACTIVE` khi thiếu các bước authorization và provisioning.
- Một `REJECTED` hoặc `EXPIRED` không tự chuyển thành APPROVED chỉ vì retry kỹ thuật.
- Một approval không được áp cho **beneficiary, resource, action hoặc tenant khác**.
- Approval cũ không được dùng để cấp lại quyền sau `REVOKED` nếu policy yêu cầu request mới.
- Nếu request bị sửa **tăng scope hoặc thời gian**, approval cũ không còn bao phủ phần mở rộng.
- Chỉ đánh dấu `VERIFIED` khi có chứng cứ từ hệ thống đích, không dựa vào trạng thái UI.
- Lỗi provisioning phải lưu nguyên **approval và request ID** để xử lý có kiểm soát, không cấp thêm permission tùy tiện.

### 8.2. APPROVED khác ACTIVE

Một owner đã duyệt nhưng connector chưa cấp role: người dùng **chưa có quyền** tại target. Ngược lại, target có role do cấp thủ công ngoài workflow: đó có thể là **quyền trái phép** dù không có approval. Reconciliation phải phát hiện cả hai.

## 9. Segregation of Duties và chống self-approval

**Segregation of Duties (SoD)** nhằm tránh một người hoặc một nhóm kiểm soát đồng thời các bước xung đột.

### 9.1. Maker–checker

Một mẫu kiểm soát phổ biến:

- **Maker:** người tạo yêu cầu.
- **Checker:** người có thẩm quyền đánh giá và duyệt.
- **Provisioner:** dịch vụ hoặc người thực thi quyền theo quyết định.
- **Auditor:** bên đánh giá lại, độc lập với hành động cấp quyền khi cần.

Không mặc định một identity có thể vừa **tạo, duyệt, cấp và xóa audit** của chính quyền admin.

### 9.2. Những xung đột thường gặp

| Tình huống | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Requester = resource owner | Tự duyệt quyền đặc biệt của mình | Định tuyến approver độc lập/higher authority |
| Approver = beneficiary | Approver hưởng trực tiếp quyền | Chặn hoặc yêu cầu độc lập theo policy |
| Delegator = delegate có quan hệ xung đột | Ủy quyền vòng tránh SoD | Validation chain và review |
| Người duyệt có thể sửa owner registry | Tự tạo thẩm quyền approve | SoD, ownership change approval và audit |
| Resource owner vừa tạo vừa duyệt giao dịch tài chính | Thiếu kiểm tra nhiệm vụ xung đột | Business SoD ở tài nguyên |
| Requester đổi người nhận sau approval | Approval bị tái sử dụng | Bind approval với beneficiary immutable |
| Người có quyền cấp role tự approve grant admin | Nâng quyền không độc lập | PAM/IGA approval và evidence riêng |

**Không phải mọi yêu cầu đều cấm owner tự xin quyền xem dữ liệu mình sở hữu**, nhưng những trường hợp có thể tự phê duyệt phải được **policy định nghĩa rõ theo rủi ro**, không phải do workflow bỏ qua kiểm tra.

### 9.3. SoD theo giao dịch chứ không chỉ theo role

Ví dụ người tạo hóa đơn không được tự phê duyệt chính hóa đơn đó. Dù cả hai role được cấp hợp lệ, PEP cần kiểm:

~~~text
DENY payment.approve WHEN
    payment.createdByIdentityId == currentActor.identityId
~~~

Đây là policy nghiệp vụ minh họa. Resource owner approval cho một role không thể tự vô hiệu hóa các kiểm soát SoD tại giao dịch cụ thể.

## 10. Định tuyến approval theo mức rủi ro

Không phải mọi permission đều yêu cầu cùng một số người duyệt.

| Loại truy cập | Ví dụ | Workflow gợi ý |
| --- | --- | --- |
| **Low risk** | Đọc tài liệu nội bộ đã phân loại công khai với nhân viên | Có thể auto-approve theo policy được owner phê duyệt trước |
| **Medium risk** | Đọc dataset nội bộ theo dự án | Manager hoặc resource owner tùy phân quyền |
| **High risk** | Export dữ liệu nhạy cảm, sửa cấu hình production | Resource owner + security/SoD review và time-bound |
| **Privileged** | Cloud admin, DBA production, IAM role.grant | JIT, step-up, owner approval và PAM controls |
| **Regulated/sensitive** | Dữ liệu chịu quy định bảo vệ chặt | Data owner, purpose/need-to-know và compliance controls theo policy |
| **Non-human** | Service principal truy cập secret/API | Resource owner + workload owner, expiry/audience/scope |
| **Emergency** | Break-glass ứng phó sự cố | Quy trình ngoại lệ có trách nhiệm, TTL, giám sát và hậu kiểm |

Các hàng chỉ là **mẫu thiết kế**, không phải quy định của một chuẩn hoặc doanh nghiệp cụ thể. Tổ chức phải xác định mức rủi ro, quyền cần auto-approve và thứ tự kiểm soát.

### 10.1. Approval tuần tự và song song

- **Sequential:** manager chấp thuận nhu cầu trước, resource owner duyệt quyền sau.
- **Parallel:** data owner và security đánh giá đồng thời, chỉ cấp khi đủ tất cả quyết định bắt buộc.
- **Conditional:** quyền nhạy cảm mới cần DPO/security hoặc PAM owner bổ sung.
- **Quorum:** một tập approver nhất định phải duyệt theo policy, ví dụ 2/3 người; không mặc định một người duyệt thay cả nhóm.

Workflow phải định nghĩa **quy tắc kết hợp**: một DENY có phủ quyết không, có được bỏ qua approver quá hạn không, kết quả của approver rời công ty có còn hiệu lực không.

### 10.2. Pre-approved access models

Một resource owner có thể phê duyệt **mẫu role/access package** từ trước để các yêu cầu thỏa điều kiện được cấp tự động. Đây là **phê duyệt policy/access package**, không phải mặc định mọi requester sau này đều đủ điều kiện.

Tự động cấp vẫn phải kiểm membership, JML, risk, scope, SoD, expiry và ghi evidence rằng quyền dựa trên **approved package version** nào.

## 11. Quyết định của owner phải ràng buộc đúng phạm vi

Một approval không nên chỉ là boolean `true`.

### 11.1. Decision contract minh họa

~~~json
{
  "decisionId": "decision-4882",
  "requestId": "access-req-884",
  "approverIdentityId": "person-502",
  "approvalAuthorityRef": "resource-owner:fin-dataset-2026:v32",
  "decision": "APPROVE",
  "approvedBeneficiaryIdentityId": "person-1042",
  "approvedResourceId": "fin-dataset-2026",
  "approvedEntitlement": "dataset.read",
  "approvedTenantId": "tenant-a",
  "approvedScope": {
    "ownerDepartment": "Finance",
    "exportAllowed": false
  },
  "approvedUntil": "2026-12-15T18:00:00+07:00",
  "decisionAt": "2026-11-30T15:10:00+07:00",
  "approvalPolicyVersion": "finance-access/v4",
  "reasonCode": "BUSINESS_NEED_VERIFIED"
}
~~~

Đây là dữ liệu minh họa. Nội dung thực tế cần có kiểm soát integrity, actor authentication và quyền xem.

### 11.2. Quyết định thu hẹp scope

Owner có thể nhận yêu cầu `dataset.read + export` trong 90 ngày nhưng chỉ duyệt **read không export, 14 ngày**. Nếu workflow hỗ trợ **counter-offer/partial approval**, phải:

- Hiển thị rõ phạm vi được duyệt khác yêu cầu ban đầu.
- Lưu decision và scope bất biến, không chỉnh request gốc âm thầm.
- Provision **chỉ phần được duyệt**.
- Xử lý sự chấp nhận hoặc xác nhận lại khi policy yêu cầu.
- Từ chối nếu hệ thống đích không biểu diễn được scope hẹp.

**Không được coi “owner đã APPROVE” là cho phép mọi quyền từng xuất hiện trong yêu cầu.**

### 11.3. Approval có điều kiện

Nếu owner ghi “Approve nếu có MFA”, điều kiện MFA phải được **mô hình hóa và PEP/PAM kiểm tra**, không chỉ lưu trong comment mà connector bỏ qua.

Điều kiện như **time window, classification, approval ticket, assurance, device health, network zone, rate limit hoặc export restriction** cần có nơi thực thi và chứng cứ.

## 12. Kiểm thẩm quyền tại thời điểm ra quyết định

Một yêu cầu có thể chờ trong nhiều ngày; trong thời gian đó owner có thể đổi vai trò, bị Leaver hoặc resource có thể đổi mức phân loại.

Khi approver nhấn Approve, workflow nên kiểm:

1. **Actor đã xác thực** qua IdP/SSO và đủ assurance nếu yêu cầu.
2. `approverIdentityId` là identity được công nhận, không chỉ email/username.
3. Actor đang là owner/delegate hợp lệ cho resource.
4. Delegation còn thời gian, scope, risk tier, không bị thu hồi.
5. Request chưa hết hạn, bị hủy hoặc có một decision xung đột.
6. Resource còn ACTIVE, tenant và classification vẫn như điều kiện duyệt.
7. Beneficiary còn quan hệ làm việc phù hợp, không có security block.
8. Approval không vi phạm SoD hoặc luật phê duyệt cấp bậc.
9. Các entitlement được yêu cầu vẫn hợp lệ theo policy phiên bản hiện hành.
10. Quyết định được ghi bằng **atomic state transition** để chống nhấn lặp.

### 12.1. Không tin link trong email như bằng chứng quyền

Email có thể chứa deep link tới request. Link giúp mở giao diện nhưng **không nên là chứng cứ approver đã xác thực**; nếu ai có link đều có thể approve, link bị lộ hoặc chuyển tiếp sẽ tạo bypass.

Cần yêu cầu đăng nhập, xác minh authority tại server và có CSRF/replay protection phù hợp.

### 12.2. Approval cũ sau thay đổi owner

Nếu người cũ đã duyệt khi còn là owner nhưng provisioning chưa chạy sau một lần đổi ownership, policy có thể yêu cầu **revalidation hoặc tái phê duyệt**. Tính hợp lệ phải được xác định bằng **thời điểm, ownership transition và mức rủi ro**, không tự động vô hiệu hóa mọi approval lịch sử cũng không tự động giữ mãi.

## 13. Bằng chứng phê duyệt và audit trail

Một workflow quản trị cần để lại chuỗi bằng chứng có thể kiểm tra:

~~~text
Access request
    -> Requester / Beneficiary identity
    -> Resource ownership snapshot
    -> Policy/risk/SoD evaluation
    -> Approver identity + authority
    -> Decision + approved scope + expiry
    -> Provisioning job / target account
    -> Observed entitlement / enforcement evidence
    -> Revocation / expiration evidence
~~~

### 13.1. Metadata quyết định nên có

| Nhóm | Ví dụ thông tin | Tác dụng |
| --- | --- | --- |
| **Yêu cầu** | requestId, requesterId, beneficiaryId, resourceId, role, scope, thời gian | Tìm lại điều đã xin |
| **Thẩm quyền** | ownerRegistryVersion, delegationId, approverId | Vì sao người này được phép duyệt |
| **Policy** | policyId/version, riskTier, SoD result | Vì sao workflow yêu cầu phê duyệt này |
| **Quyết định** | APPROVE/DENY, reason, timestamp, approved scope | Nội dung quyết định |
| **Provisioning** | taskId, connector, targetAccount, appliedAt | Đã cấp gì và ở đâu |
| **Đối soát** | desired vs observed, verifiedAt, exception | Phát hiện sai lệch |
| **Thu hồi** | revoke request, target result, session/token status | Bằng chứng ngừng quyền |
| **Bảo vệ log** | actor, integrity, access/review events, retention | Điều tra và tránh sửa trái phép |

Không ghi token thô, mật khẩu, OTP, private key hoặc toàn bộ dữ liệu cá nhân không cần thiết vào approval log. Audit phải **được bảo vệ khỏi người có lợi ích xung đột**, và có retention theo chính sách.

### 13.2. Audit log không tự chứng minh quyền đích

Một dòng `OWNER_APPROVED` có giá trị chứng minh **quyết định chủ sở hữu**. Nó không chứng minh `SCIM_PATCH_SUCCEEDED`, càng không chứng minh `TARGET_PERMISSION_VERIFIED`.

Để kết luận đã cấp hoặc thu hồi đúng, cần đối chiếu **observed state** tại target và trạng thái phiên/token khi có liên quan.

### 13.3. Thay đổi lịch sử approval

Quyết định đã ghi nên có **tính bất biến logic**. Nếu phát hiện duyệt nhầm, tạo event **CANCELED/REVOKED/SUPERSEDED** với nguồn và lý do; không sửa lén nội dung approval cũ rồi xem đó là lịch sử duy nhất.

## 14. SLA, reminder và escalation

Resource owner có thể bận, nghỉ phép hoặc nghỉ việc. Workflow cần xử lý chậm trễ mà **không tự mở quyền sai**.

### 14.1. SLA xử lý

Một tổ chức có thể phân loại:

- Quyền thông thường: deadline theo ngày làm việc và mức ưu tiên.
- Quyền dữ liệu nhạy cảm: review chặt, có thể cần nhiều bên.
- Quyền đặc quyền khẩn cấp: deadline ngắn, có cơ chế escalation hoặc break-glass riêng.
- Workflow chưa định danh owner: deadline xử lý **ownership** chứ không auto-approve.

Những khoảng thời gian cụ thể là **quy định nội bộ**, không có SLA chung áp dụng cho mọi hệ thống.

### 14.2. Khi quá hạn

- Gửi reminder an toàn, tránh lộ dữ liệu nhạy cảm qua email.
- Escalate tới **delegate/fallback approver có thẩm quyền** theo registry.
- Chuyển `EXPIRED` hoặc `OWNER_UNRESOLVED` nếu không tìm được thẩm quyền.
- Cho requester chỉnh/hủy yêu cầu, nhưng **không bypass các phê duyệt bắt buộc**.
- Ghi audit số lần nhắc, lần định tuyến lại, SLA và người xử lý.

**Timeout không đồng nghĩa APPROVED.** Nếu chính sách có auto-approval ở một tập quyền ít rủi ro, đó phải là **quy tắc được owner phê duyệt từ trước**, không phải tác dụng phụ của việc inbox không ai trả lời.

## 15. Tính toàn vẹn của workflow và xử lý lỗi

Những lỗi hệ thống thường dễ bị nhầm với quyết định nghiệp vụ:

| Tình huống | Không được suy luận | Cách xử lý |
| --- | --- | --- |
| Không gửi được email approver | Owner đã từ chối | Retry thông báo, giữ request đúng trạng thái |
| Owner login thất bại | Decision DENY về quyền tài nguyên | Ghi lỗi authentication riêng |
| PIP/owner registry timeout | Manager mặc nhiên được duyệt | Chặn hoặc đưa exception xử lý ownership |
| Hai approver cùng nhấn | Cấp hai lần hai quyền | Atomic decision, idempotency |
| Connector trả HTTP timeout | Chắc chắn chưa cấp quyền | Query target và dùng idempotent retry |
| SCIM trả success nhưng target role sai | Quyền đã VERIFIED | Readback và reconciliation |
| Request hủy trong lúc provisioning | Lệnh cấp cũ cứ hoàn tất là hợp lệ | Version guard và compensating revoke |
| Resource bị xóa/đổi owner | Approval cũ luôn còn hiệu lực | Revalidate resource và policy |
| Approver Leaver | Inbox vẫn để owner cũ duyệt | Reroute đến owner mới có thẩm quyền |
| IAM outage trong phiên đặc quyền | Có approval nên cho mọi hành động | Fail-safe hoặc break-glass được kiểm soát |

### 15.1. Idempotency và event ordering

Một yêu cầu có `requestId` và `idempotencyKey` giúp hạn chế cấp quyền nhiều lần khi retry. Nhưng **idempotency một mình không ngăn task cũ chạy sau khi người dùng bị Leaver**.

Cần thêm:

- **State/version guard** trước khi ghi quyết định và trước khi provision.
- So sánh event version hoặc effectiveAt từ nguồn có thẩm quyền.
- Chặn replay các quyết định/handoff đã bị hủy hoặc hết hạn.
- **Revoke/compensation** nếu đã cấp quyền sau khi yêu cầu không còn hợp lệ.
- Chỉ đóng workflow khi reconciliation xác minh kết quả.

## 16. Resource owner approval trong Joiner lifecycle

Trong **Joiner**, HRIS hoặc nguồn hợp đồng xác nhận mối quan hệ làm việc, identity proofing xác minh danh tính, IdP tạo tài khoản, nhưng **quyền trên một tài nguyên cụ thể vẫn phải được cấp theo chính sách và approval tương ứng**.

### 16.1. Quy trình Joiner

1. HRIS cung cấp identityId, relationshipId, workerType, manager và `effectiveAt`.
2. IGA liên kết identity với account và tính những access package có thể cấp.
3. Các quyền ít rủi ro có thể tự động cấp nếu resource owner đã phê duyệt policy/package từ trước.
4. Quyền nhạy cảm cần yêu cầu chỉ rõ resource, action, tenant, scope, mục đích và thời hạn.
5. Resource owner được xác minh thẩm quyền trước khi đưa ra quyết định.
6. SoD/security review hoàn tất nếu policy yêu cầu.
7. Connector SCIM/API/Directory cấp quyền không sớm hơn thời điểm hợp lệ.
8. PEP ứng dụng kiểm quyền tại mỗi hành động; reconciliation xác minh đúng trạng thái đích.

### 16.2. Preboarding khác production access

Một nhân viên có account IdP từ ngày 25/11 nhưng bắt đầu làm việc ngày 01/12. Owner có thể duyệt trước để chuẩn bị cấp quyền, song approval **không có nghĩa quyền production được mở ngay**.

~~~text
approvedAt = 2026-11-25T14:00:00+07:00
grantFrom  = 2026-12-01T09:00:00+07:00
grantUntil = 2026-12-15T18:00:00+07:00

Before grantFrom: DENY production access.
After grantUntil: entitlement must expire/revoke.
~~~

Một cổng preboarding có thể có quyền rất hạn chế theo policy riêng. Không nhầm tài khoản đã được tạo với quyền đã được phê duyệt và có hiệu lực.

### 16.3. Hủy hoặc dời ngày bắt đầu

Nếu ứng viên không nhận việc, workflow phải hủy pending/approved grants chưa thực thi, chặn task cũ qua version guard, gỡ quyền đã cấp và xác minh ở ứng dụng đích. Nếu ngày bắt đầu đổi, phải xem có cần revalidation hoặc reapproval.

**Không dùng approval của Joiner đã hủy để tự động cấp quyền ở một sự kiện tuyển dụng mới.**

## 17. Resource owner approval trong Mover lifecycle

**Mover** thay đổi nhiệm vụ, vị trí, department, dự án, pháp nhân hoặc manager. Người dùng có thể vẫn ACTIVE nhưng mất nhu cầu sử dụng tài nguyên cũ.

~~~text
Trước Mover:
  role = SupportAgent
  access = CRM-CustomerRecords/read
  approval = CRM Resource Owner

Sau Mover:
  role = FinanceAnalyst
  desired access = Finance-Reports/read
  approver = Finance Data Owner
  CRM access = revoke
~~~

### 17.1. Không tái sử dụng approval của tài nguyên cũ

Approval của CRM owner không cấp quyền Finance Reports. Yêu cầu Finance phải được định tuyến tới đúng owner, tenant và scope, dù user đang có account SSO hợp lệ.

### 17.2. Thời hạn approval không chứng minh nhu cầu còn hợp lệ

Nếu role/dự án đã thay đổi, approval có thể **còn hạn trên giấy** nhưng không còn cơ sở nghiệp vụ. IGA nên:

- Tính lại desired entitlements theo quan hệ hiện hành.
- Rà approval ràng buộc vào role/project/manager cũ.
- Gỡ EXTRA_ACCESS, xử lý role local và group ở SaaS.
- Hủy request cũ chưa provision nếu điều kiện không còn đúng.
- Thu hồi hoặc đánh giá lại session/token khi cần.
- Yêu cầu approval mới cho tài nguyên mới.
- Reconciliation xác minh trạng thái ở từng target.

### 17.3. Thay manager không đồng nghĩa đổi resource owner

Manager mới xác nhận người dùng có nhiệm vụ mới; nhưng quyền sử dụng dữ liệu do một owner độc lập quản trị. Không tự gửi request tới manager thay vì owner khi policy bắt buộc owner review.

## 18. Resource owner approval trong Leaver lifecycle

**Leaver** đòi hỏi chặn đường truy cập thực tế khi quan hệ làm việc/hợp đồng hết hiệu lực.

~~~mermaid
flowchart TD
    HR["HRIS: Leaver effectiveAt"] --> IAM["IGA: xác định revoke scope"]
    IAM --> PEND["Cancel pending/approved grants chưa áp"]
    IAM --> PROV["SCIM/API/Directory: disable và gỡ roles"]
    IAM --> PEP["PDP/PEP: chặn quyền hiện hành"]
    IAM --> SESS["IdP/PAM/SaaS: session và token controls"]
    PEND --> REC["Audit + reconciliation"]
    PROV --> REC
    PEP --> REC
    SESS --> REC
    REC --> Q{"Đường truy cập trong scope đã chặn?"}
    Q -->|"Chưa"| EX["Exception + owner + escalation"]
    Q -->|"Đã xác minh"| DONE["Đóng Leaver"]
    EX --> REC
~~~

### 18.1. Approve trước Leaver, provision sau Leaver

Giả sử owner nhấn Approve lúc 17:59; quan hệ kết thúc lúc 18:00; connector chạy lúc 18:03.

Nếu worker chỉ nhìn `approvalStatus=APPROVED`, nó có thể cấp quyền cho một Leaver. Cần kiểm **lifecycle status và version tại thời điểm áp quyền**, chặn task cũ hoặc compensation nếu lệnh đã chạy.

### 18.2. Các lớp còn có quyền

- IdP khóa account không tự chấm dứt mọi ứng dụng đã lập session.
- SCIM disable user không tự revoke mọi credential đã phát.
- Cloud IAM role, VPN, SSH key hoặc local admin có thể độc lập.
- PAM JIT grant và privileged session có thể còn hoạt động.
- Access token chứa role cũ có thể còn hạn; API cần policy kiểm trạng thái phù hợp.

**Owner approval không miễn trừ Leaver.** Quyền truy cập sau ngày kết thúc phải dựa trên một quan hệ/quy trình đủ thẩm quyền mới, không tái dùng approval cũ.

### 18.3. Nhiều quan hệ việc làm

Một người kết thúc hợp đồng ở pháp nhân A nhưng còn hợp đồng hợp lệ ở B. Cần xét **relationship nào cấp quyền cho resource** để thu hồi chính xác. Không chỉ dựa trên email hoặc một cờ TERMINATED ở một nguồn mà hủy nhầm quyền hợp lệ còn lại.

## 19. Resource owner approval và RBAC/ABAC/PBAC

### 19.1. RBAC: vai trò có thể thay đổi định nghĩa

Role `FinanceReader` có thể ban đầu chỉ cho phép xem hóa đơn, rồi được sửa thành có thể export. Approval ban đầu cho READ **không nhất thiết bao phủ permission mới**.

Đối với quyền nhạy cảm, nên lưu role ID, version, permission scope và theo dõi thay đổi role definition. Không cho một lần owner approval biến thành quyền wildcard khi role map mở rộng.

### 19.2. ABAC: approval là một điều kiện

~~~text
PERMIT dataset.read WHEN
    subject.lifecycleStatus == ACTIVE
    AND subject.tenantId == resource.tenantId
    AND subject.hasApprovedRole("Analyst")
    AND approval.validFor(
        subject.identityId,
        resource.id,
        "dataset.read",
        now
    )
    AND NOT subject.securityBlocked
ELSE DENY
~~~

Mã giả này thể hiện **approval là một đầu vào cho authorization**. PEP vẫn phải kiểm resource ownership, classification, scope và policy hiện hành.

### 19.3. PBAC: version và yêu cầu mới

Policy v3 có thể chỉ yêu cầu owner; policy v4 thêm review của security cho dữ liệu CONFIDENTIAL. Một approval từ v3 **không tự đáp ứng mọi yêu cầu v4**. Cần revalidation theo policy đang active trước provisioning hoặc hành động rủi ro cao.

## 20. IdP, SSO, SCIM và authorization thực tế

| Thành phần | Nhiệm vụ | Không tự bảo đảm |
| --- | --- | --- |
| **IdP/SSO/OIDC/SAML** | Xác thực và cung cấp phiên/token | Owner đã duyệt quyền resource |
| **IGA/workflow** | Thu thập nhu cầu, routing, review, approval | Role đã được cấp đúng |
| **SCIM/API/Directory** | Provision/deprovision account hoặc group | Mọi token, session và role local bị thu hồi |
| **RBAC/ABAC/PBAC** | Định nghĩa logic quyền | Hành động thực tế được chặn nếu không có PEP |
| **PEP** | Chặn hoặc thực hiện thao tác theo policy | Audit/approval chain được lưu đúng nếu nguồn khác lỗi |
| **Reconciliation** | So desired và observed access | Không tự chặn truy cập nếu runtime vẫn PERMIT |

### 20.1. Token có role cũ

Sau khi approval bị revoke, token SSO hoặc session có thể còn group/role cũ. Nếu API chỉ kiểm token còn hạn, quyền có thể tồn dư. Với tài nguyên nhạy cảm, cần **current entitlement check, token/session invalidation, TTL hoặc revocation/introspection** theo khả năng nền tảng.

### 20.2. JIT provisioning không được bỏ qua approval

Một SaaS có thể tạo tài khoản tại lần SSO đầu tiên. Nếu JIT tự gán role Finance theo email domain, nó có thể bỏ qua owner approval. Cần kiểm **issuer + subject, identity link, eligibility, lifecycle status và access package được duyệt**.

### 20.3. Bằng chứng từ target

`SCIM PATCH succeeded` không đồng nghĩa API có thể thực thi ngay, cũng không chứng minh scope nhỏ hơn đã được áp. Phải **đọc lại quyền đích**, và khi cần kiểm PEP với hành động/resource cụ thể.

## 21. Quyền đặc quyền, JIT và resource owner approval

Quyền production admin hoặc IAM role.grant thường có rủi ro cao. Nên tách:

- **Eligibility:** người dùng đủ điều kiện xin quyền.
- **Owner decision:** chấp thuận target/action/purpose/time cụ thể.
- **Security/SoD review:** xác định xung đột và các điều kiện bổ sung.
- **JIT activation:** mở quyền trong khoảng ngắn.
- **PAM/session control:** broker credential, audit, recording khi phù hợp.
- **Expiry/revocation:** kết thúc grant và xử lý phiên, token/credential.

### 21.1. Ví dụ request JIT

~~~text
Requester: SRE-1042
Target: prod-db-07
Action: db.schema.migrate
Scope: application database only
Resource owner: Production DB Owner
Ticket: CHG-2041
Window: 22:00-22:30
Additional controls: MFA, approval, PAM session, audit
~~~

Đây là dữ liệu minh họa. Owner đồng ý migration ở một DB **không cho phép dùng credential DBA toàn quyền trên mọi database**.

### 21.2. JIT hết hạn nhưng phiên còn mở

Hết 30 phút grant không chắc làm SSH/RDP/DB session hoặc background process kết thúc. Cần điều khiển phiên, kiểm thời điểm, thu hồi quyền target và đối soát. **Session recording chỉ là chứng cứ, không phải công cụ thu hồi tự động**.

### 21.3. Break-glass

Trong khẩn cấp có thể dùng quy trình riêng đã định trước với incident ID, actor được xác thực, scope hẹp, TTL, giám sát, audit và hậu kiểm owner. Không giả vờ đây là owner approval thường lệ.

## 22. Service account, workload identity và resource owner

Tài khoản dịch vụ, bot, pipeline CI/CD và managed identity cần **purpose, owner, expiry và scope**, dù không có người ngồi đăng nhập.

### 22.1. Hai dạng owner

- **Workload owner:** đội chịu trách nhiệm chạy pipeline/service.
- **Resource owner:** người/đội có thẩm quyền cho phép resource được truy cập.

Một service principal muốn đọc secret production có thể cần cả hai cấp review theo policy. Không tự coi người tạo pipeline là chủ sở hữu secret.

### 22.2. Yêu cầu quyền workload minh họa

~~~json
{
  "requestId": "svc-access-204",
  "principalType": "WORKLOAD",
  "beneficiaryPrincipalId": "pipeline-prod-deploy",
  "workloadOwnerTeam": "platform-operations",
  "resourceId": "cloud-prod-cluster-01",
  "requestedActions": [
    "deployment.read",
    "deployment.create"
  ],
  "audience": "deployment-api",
  "environment": "production",
  "validUntil": "2027-01-31T23:59:59Z",
  "purpose": "production-release"
}
~~~

Đây là JSON minh họa. Chủ thể workload có thể dùng OIDC federation ngắn hạn nhưng vẫn cần **permission ở cloud/API và approval tương ứng**. Không cho wildcard chỉ vì credential có TTL ngắn.

### 22.3. Owner Mover/Leaver

Khi người phụ trách service nghỉ hoặc đổi vai trò, cần bàn giao owner, gỡ quyền cá nhân cũ, rà token/secret/trust, đánh giá approval còn hiệu lực và reconcile actual access.

Không xóa ngay workload đang phục vụ production nếu chỉ vì owner cũ Leaver; nhưng cũng không để workload **mồ côi hoặc dùng credential của người cũ**.

## 23. Đọc, export, chia sẻ và xóa dữ liệu là các action khác nhau

| Action | Ý nghĩa | Tác động tới phê duyệt |
| --- | --- | --- |
| **dataset.read** | Đọc dữ liệu trong scope | Owner có thể duyệt đọc |
| **dataset.export** | Mang dữ liệu khỏi phạm vi xem | Có thể cần điều kiện riêng |
| **dataset.share** | Mở cho identity hoặc tenant khác | Cần kiểm recipient, scope và privacy |
| **dataset.delete** | Xóa dữ liệu | Có thể cần SoD/approval bổ sung |
| **dataset.grant** | Cấp quyền cho người khác | Kiểm quyền grant và ownership |
| **dataset.admin** | Quản lý cấu hình toàn hệ | Workflow đặc quyền/JIT |

**Approval READ không tự bao gồm EXPORT, DELETE hoặc SHARE.** PEP phải kiểm action thực tế, không chỉ tên role.

Nếu classification của resource đổi từ INTERNAL sang CONFIDENTIAL, những approval còn hiệu lực có thể cần re-review theo policy mới; không để phạm vi cũ âm thầm bao phủ dữ liệu nhạy cảm hơn.

## 24. Mẫu triển khai workflow phía backend

Backend phải lấy **actor identity từ security context**, tra resource registry và state request ở nguồn đáng tin. Không tin `approverId`, `role=OWNER` hay `approved=true` do client tự khai.

### 24.1. Mã giả duyệt request

~~~text
decide(authenticatedActor, requestId, requestedDecision):
    request = requestStore.lockAndLoad(requestId)

    require request.status == PENDING_OWNER
    require request.isWithinDecisionDeadline
    require requestedDecision in [APPROVE, DENY]

    owner = resourceRegistry.readCurrent(request.resourceId)
    require owner.resourceIsActive
    require owner.mayDecide(
        authenticatedActor.identityId,
        request.entitlement,
        request.riskTier,
        now
    )

    require authenticatedActor.isActive
    require sodPolicy.allowsDecision(authenticatedActor, request)
    require request.resourceVersionAndScopeStillValid
    require approvalPolicy.currentRulesSatisfied(request)

    event = writeImmutableDecisionAndTransitionAtomically(
        request.id, authenticatedActor, requestedDecision,
        request.scope, owner.version, approvalPolicy.version
    )

    if requestedDecision == APPROVE:
        outbox.enqueueGrantWithStateGuard(request.id)

    return event.decisionReference
~~~

Mã giả không phải API của một framework. Quyết định và đổi trạng thái nên được xử lý bằng **transaction/outbox** phù hợp, tránh ghi log APPROVED nhưng state không đổi do một lần ghi thất bại.

### 24.2. Java/Spring service skeleton

~~~java
// Mẫu định hướng, không phải code độc lập có thể chạy.
@Service
class ResourceApprovalService {
    private final RequestRepository requests;
    private final OwnershipRegistry owners;
    private final ApprovalPolicy policy;
    private final Outbox outbox;

    @Transactional
    public DecisionResult decide(
            AuthenticatedActor actor,
            String requestId,
            OwnerDecision decision) {

        AccessRequest req = requests.findForUpdate(requestId);

        if (!req.isPendingOwner() || req.isExpired()) {
            return DecisionResult.denied("INVALID_STATE");
        }

        OwnerAuthority authority =
                owners.readCurrent(req.resourceId());

        if (!policy.mayApprove(actor, req, authority)) {
            return DecisionResult.denied("UNAUTHORIZED_APPROVER");
        }

        if (!req.isStillEligibleForCurrentPolicy()) {
            return DecisionResult.denied("REVALIDATE");
        }

        requests.saveDecisionAndTransition(req, actor, decision);
        outbox.append(req.id(), decision);
        return DecisionResult.recorded(req.id());
    }
}
~~~

Các class/service là giả định. Implementation phải bổ sung authentication, CSRF, SoD, delegation expiry, error handling, database locking, validation, audit và retry đúng kiến trúc. **Không dùng annotation hay transaction riêng như bằng chứng đã chống mọi race condition.**

### 24.3. Connector worker

Worker nhận event APPROVED nên kiểm lại:

- request chưa CANCELLED/REVOKED/EXPIRED;
- lifecycle status của beneficiary;
- resource còn tồn tại, đúng owner và classification theo policy;
- scope/role không bị tăng;
- approval và security gates còn hiệu lực;
- event version không cũ hơn trạng thái mới;
- grant TTL/target identity đúng.

Sau đó mới apply bằng SCIM/API/Directory, đọc lại kết quả và ghi observed state. Nếu trạng thái thay đổi sau apply, cần **compensating revoke** và exception.

## 25. Race condition, idempotency và approval replay

### 25.1. TOCTOU giữa approve và provision

~~~text
09:00 Owner duyệt dataset.read
09:01 IAM xếp task cấp quyền
09:02 Security block identity
09:03 Connector xử lý task cũ
09:04 Nếu không revalidate: quyền vẫn được cấp
~~~

Đây là **Time-of-check to time-of-use (TOCTOU)**. Kiểm tra lúc Approve chưa đủ cho hành động cấp quyền ở thời điểm sau.

### 25.2. Chống replay

- Gắn decision với requestId, beneficiary, resource, action, tenant, scope và expiry.
- Yêu cầu state transition nguyên tử, tránh hai nút Approve cùng gây cấp nhiều lần.
- Dùng idempotency key khi gửi API với retry có thể lặp.
- Không dùng approval EXPIRED/REVOKED/CANCELLED để cấp lại.
- Kiểm version guard trước khi xử lý queue event.
- Nếu yêu cầu mở rộng từ READ sang EXPORT, cần decision mới.

### 25.3. Bulk approval

Approve hàng loạt có thể hữu ích nhưng phải kiểm **từng request** có approver, SoD, target, scope, policy, expiry riêng. Không dùng một quyết định chung mở rộng quyền ngoài tập đã xem xét.

## 26. Thu hồi, hết hạn và recertification

Một approval không có nghĩa quyền tồn tại vĩnh viễn. Nó có thể mất giá trị khi:

- Hết thời hạn hoặc dự án kết thúc.
- Owner rút chấp thuận.
- Mover đổi vai trò/department.
- Leaver hoặc security block.
- SoD conflict mới.
- Resource đổi owner, tenant hoặc classification.
- Workload decommissioned hoặc mất owner.

### 26.1. Ba trạng thái khác nhau

~~~text
APPROVAL_REVOKED
    != TARGET_ENTITLEMENT_REMOVED
    != EFFECTIVE_ACCESS_DENIED
~~~

Khi owner rút approval, phải xử lý quyền ở target, session/token khi cần và **reconciliation**.

### 26.2. Access certification

Owner định kỳ hoặc khi có sự kiện cần review quyền đã cấp: người dùng còn phù hợp không, mục đích còn tồn tại không, scope có rộng hơn nhu cầu không, có local permission ngoài workflow không, service account còn owner không.

**Certification nhìn quyền hiệu lực hiện tại**, không chỉ xem lại một approval cũ. Những quyền không còn cần phải revoke và xác minh.

## 27. Ngoại lệ và break-glass có kiểm soát

Một yêu cầu khẩn cấp có thể không đủ thời gian để xin owner approval theo luồng thường. Quy trình break-glass phải được định nghĩa **trước sự cố**, có:

- Incident/ticket và lý do bắt buộc.
- Principal được xác thực, MFA/step-up phù hợp.
- Scope/action/target/TTL hẹp.
- Quyền kích hoạt ngoại lệ riêng, không do requester tự tạo.
- Giám sát, recording/target audit khi phù hợp.
- Thông báo resource owner và security.
- Hậu kiểm, thu hồi, reconciliation và báo cáo.

Không biến **owner bận hoặc deadline thông thường** thành lý do bypass, và không ghi `APPROVED_BY_OWNER` cho quyết định khẩn cấp không do owner đưa ra.

## 28. Reconciliation: chứng minh quyền thực tế

| Trạng thái approval/desired | Observed tại target | Kết luận |
| --- | --- | --- |
| Approved READ, còn hạn | READ đúng resource/tenant | **MATCH** |
| Approved READ | READ và EXPORT | **EXTRA_ACCESS** |
| Approved READ | Không thấy READ | **MISSING_ACCESS** |
| DENIED | Target có READ | **UNAUTHORIZED_ACCESS** |
| PENDING | Target đã cấp role | **PREMATURE_PROVISIONING** |
| EXPIRED/REVOKED | Quyền vẫn tồn tại | **RESIDUAL_ACCESS** |
| Approved, target unavailable | Không biết actual rights | **UNKNOWN**, không đánh dấu VERIFIED |
| Owner đã thay đổi | Request còn gán owner cũ | **ROUTING_DRIFT** |
| Beneficiary Leaver | Provision job cấp role mới | **LIFECYCLE_VIOLATION** |

### 28.1. Dữ liệu cần đối chiếu

- HRIS/identity registry: relationship, active status và effectiveAt.
- Ownership registry: owner/delegate, resource/classification/tenant.
- Approval engine: decision, scope, policy version, expiry.
- SCIM/Directory/API: user/account/role thực tế.
- IdP/SSO: session/token và claim mapping.
- PAM/cloud/PEP: privilege còn hiệu lực, active sessions.
- Audit/SIEM: correlation IDs, exceptions và remediation.

Một workflow chỉ nên **đóng VERIFIED** sau khi có bằng chứng ở scope yêu cầu, không chỉ dựa vào connector đã gửi lệnh.

## 29. Chỉ số vận hành approval

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Owner coverage** | Tỷ lệ tài nguyên có owner còn hiệu lực |
| **Correct routing rate** | Yêu cầu gửi đúng người có thẩm quyền |
| **Decision latency / SLA** | Thời gian từ request tới owner decision |
| **Unresolved owner rate** | Tài nguyên thiếu owner hoặc delegation rõ |
| **Self-approval prevented** | SoD chặn các yêu cầu tự cấp quyền |
| **Stale approval count** | Approval cũ vì owner/role/JML/policy đổi |
| **Approval-to-verified latency** | Từ quyết định tới khi target đúng |
| **Post-approval extra access** | Quyền thực tế vượt scope được duyệt |
| **Expired access still active** | Quyền tồn dư sau expiry/revoke |
| **Mover/Leaver pending grants** | Task chờ hoặc cấp sai sau JML |
| **Workload owner coverage** | Service principal có owner/purpose |
| **Break-glass review completion** | Ngoại lệ đã được kiểm hậu sự cố |
| **Audit completeness** | Đủ actor, resource, decision, policy, outcome |

Một hệ thống có số request APPROVED cao chưa chắc tốt. Chất lượng thể hiện ở **đúng owner, đúng scope, đúng thời gian, đúng enforcement và quyền được thu hồi khi không còn hợp lệ**.

## 30. Tình huống tổng hợp: dữ liệu Finance

### 30.1. Joiner: phê duyệt quyền đúng scope

**Minh** vào nhóm Analytics ngày 01/12/2026, cần đọc bộ dữ liệu Finance trong 14 ngày.

- HRIS xác nhận identity/effectiveAt.
- Manager xác nhận nhu cầu dự án.
- Finance Data Owner duyệt `dataset.read` thuộc tenant-a, không export.
- IGA kiểm policy/SoD; SCIM cấp role đúng scope.
- PEP chặn export dù user đăng nhập SSO hợp lệ.
- Reconciliation xác minh không có FinanceAdmin/EXPORT.

### 30.2. Mover: role cũ không được giữ

Minh chuyển sang Operations. Mặc dù approval Finance chưa hết hạn, IGA đánh giá lại nhu cầu, thu hồi role cũ và yêu cầu owner Operations duyệt tài nguyên mới. Token cũ có thể chứa role Finance, nên API phải kiểm quyền hiện hành phù hợp.

### 30.3. Leaver: queue task cũ

Nhà thầu An được Approve lúc 17:58, hợp đồng kết thúc lúc 18:00, connector chạy lúc 18:03. **State guard** chặn cấp role; nếu lệnh đã chạy do race, hệ thống revoke, mở exception và xác minh target.

### 30.4. Owner bàn giao

Trong khi một request đang PENDING, data owner mới được bổ nhiệm. Workflow đọc ownerRegistryVersion mới, hủy thẩm quyền của owner cũ cho quyết định mới và định tuyến lại, giữ audit của bước chuyển.

### 30.5. Security block

Resource owner đã Approve nhưng subject bị security block. IGA không provision, PEP DENY và audit phân biệt **approval hợp lệ trong lịch sử** với **quyền hiện tại không được phép**.

## 31. Ma trận kiểm thử âm tính

| Tình huống | Kỳ vọng |
| --- | --- |
| Requester tự Approve khi SoD cấm | DENY |
| Manager không phải resource owner | Không cho owner decision |
| Delegation hết hạn hoặc chỉ có READ nhưng xin ADMIN | DENY |
| Resource không có owner xác minh được | OWNER_UNRESOLVED |
| Owner đã Leaver | Không duyệt được request mới |
| Resource đổi owner khi PENDING | Revalidate/reroute |
| Beneficiary Leaver trước provisioning | Không cấp, audit task stale |
| Beneficiary Mover mất nhu cầu | Revoke hoặc re-review |
| Approval READ được dùng cho EXPORT | DENY |
| Approval tenant-a được dùng tenant-b | DENY |
| Approval hết hạn nhưng connector retry | Không cấp |
| Hai approver bấm gần như đồng thời | Một state transition hợp lệ |
| Request bị Cancel khi provisioning đang chạy | Chặn hoặc compensating revoke |
| SCIM báo success nhưng role vượt scope | EXTRA_ACCESS |
| Target API timeout | UNKNOWN, query trước khi retry |
| Token role cũ sau revoke | PEP chặn theo policy hiện hành |
| Security block sau owner Approve | DENY |
| Link email được forward cho người khác | Không được approve |
| Bulk approve chứa một item không đủ SoD | Item đó không được cấp |
| Break-glass không có incident/authority | DENY |
| Workload thiếu owner hợp lệ | Không cấp hoặc xử lý ngoại lệ có thẩm quyền |
| JIT đã hết hạn nhưng phiên còn mở | Áp policy session revoke/terminate |
| Resource registry unavailable | Không tự chọn approver giả định |
| Quyền đích không thể kiểm chứng | UNKNOWN, không tuyên bố VERIFIED |

### 31.1. Kiểm thử end-to-end

Một phép thử đủ mạnh không dừng khi UI đổi sang APPROVED. Cần xác minh:

~~~text
Authenticated request
  -> resolved accountable resource owner
  -> eligible decision + SoD
  -> immutable approved scope and expiry
  -> state/version guard
  -> provision at target
  -> observed entitlements
  -> runtime authorization
  -> expiry / Mover / Leaver revoke
  -> reconciliation evidence
~~~

## 32. Checklist triển khai

| Câu hỏi | Bằng chứng |
| --- | --- |
| Có registry owner theo resourceId/tenant/environment? | Versioned ownership records |
| Owner hiện còn ACTIVE và đúng phạm vi? | JML + owner validation |
| Phân biệt line manager, data owner, app owner? | RACI và approval policy |
| Có delegation với scope, TTL và audit? | Delegation registry |
| Có ngăn self-approval và SoD conflict? | Policy và negative tests |
| Request có beneficiary riêng với requester? | Identity IDs |
| Action/resource/scope/expiry đủ chi tiết? | Immutable request |
| Có kiểm classification và risk tier? | Risk-based routing |
| Có xử lý owner unresolved/vắng mặt? | Escalation không auto-approve |
| Approval có authority/policy version? | Decision artifact |
| Có revalidate owner tại thời điểm nhấn? | Server-side check |
| Có chống link forwarding/CSRF/replay? | Authentication và binding |
| Có phân biệt APPROVED, PROVISIONED, VERIFIED? | State machine, target readback |
| Connector kiểm lại JML trước provision? | State/version guard |
| Có idempotent retry và compensating revoke? | Outbox/queue tests |
| Mover/Leaver có hủy request cũ? | Lifecycle event tests |
| Approval expiry dẫn tới thực thu hồi? | Scheduled revoke + reconciliation |
| Có tách READ/EXPORT/SHARE/ADMIN? | Action-level permissions |
| IdP/SSO không được nhầm với approval? | Integration tests |
| SCIM/API cấp đúng scope và role? | Observed entitlement evidence |
| Privileged JIT có xử lý session quá hạn? | PAM controls |
| Workload có owner, audience, purpose? | Non-human inventory |
| Break-glass có hậu kiểm và thời hạn? | Incident evidence |
| Audit có correlation IDs, decision, outcome? | Protected log |
| Có giám sát extra/residual access? | KPI, exception owner |

## 33. Những nhầm lẫn thường gặp

1. **“Manager duyệt thì data owner đã duyệt.”** Hai vai trò có thể khác.
2. **“Ai có role Admin đều là resource owner.”** Cần ownership registry.
3. **“Approval chỉ cần một boolean.”** Phải gắn subject/resource/action/scope/expiry.
4. **“Gửi email tới người nhận là đã xác minh thẩm quyền.”** Phải kiểm lại ở server.
5. **“Timeout thì tự động cấp quyền.”** Chỉ auto-approve nếu policy cho phép từ trước.
6. **“Owner có thể tự duyệt bất kỳ quyền nào của mình.”** SoD có thể cấm.
7. **“Owner đồng ý thì bỏ qua security DENY.”** Không được vượt policy.
8. **“APPROVED nghĩa là role đã có.”** Còn provisioning và verification.
9. **“SCIM success là toàn bộ quyền đúng scope.”** Cần readback.
10. **“Approval chưa hết hạn nên quyền cũ vẫn hợp lệ sau Mover.”** Nhu cầu công việc đã đổi.
11. **“Disable IdP là Leaver hoàn tất.”** Session, token, SaaS và cloud vẫn cần xử lý.
12. **“READ tự bao gồm EXPORT.”** Action khác cần permission tương ứng.
13. **“Owner mới tự kế thừa mọi pending decision.”** Phải revalidation.
14. **“Dùng email đủ để liên kết account.”** Email có thể đổi/tái sử dụng.
15. **“Rút approval là quyền tự mất ở mọi hệ thống.”** Cần revoke và đối soát.
16. **“Owner bận là lý do dùng break-glass.”** Không phải nếu chưa đạt điều kiện khẩn cấp.
17. **“Workload không cần approval.”** Non-human identity có owner và impact.
18. **“JIT hết hạn thì shell sẽ tự ngừng.”** Session/process cần kiểm riêng.
19. **“Log APPROVED chứng minh người dùng được phép mọi thao tác.”** PEP vẫn phải check từng action.
20. **“Certification thay thế runtime authorization.”** Rà soát và enforcement là hai lớp khác nhau.

## 34. Câu hỏi tự đánh giá

1. Resource owner approval giải quyết yêu cầu quản trị nào?
2. Line manager, application owner và resource/data owner khác nhau thế nào?
3. Vì sao ownership registry cần resourceId, owner identityId, version và effectiveAt?
4. Owner không tìm thấy thì workflow nên xử lý thế nào?
5. Delegated approver cần thỏa những điều kiện nào?
6. Vì sao link từ email không đủ để chứng minh actor có quyền Approve?
7. Một request cần những thông tin nào để quyết định có trách nhiệm?
8. Owner Approve READ có cho phép provision EXPORT không? Giải thích.
9. Các trạng thái APPROVED, PROVISIONED và VERIFIED khác nhau ra sao?
10. Maker–checker và SoD ngăn lỗi nào trong workflow?
11. Trong Joiner, vì sao tài khoản có thể tồn tại trước khi quyền có hiệu lực?
12. Trong Mover, approval còn hạn có thể bị thu hồi vì sao?
13. Leaver effective lúc 18:00, task cấp chạy 18:03: guard nào cần có?
14. Vì sao SCIM trả success chưa thể xác nhận effective access?
15. OIDC SSO có thay thế owner approval hay không?
16. Service principal xin quyền secret production cần xem những owner nào?
17. Owner đổi khi request PENDING: giải pháp nào giảm sai thẩm quyền?
18. Tại sao phải phân biệt requester và beneficiary?
19. TOCTOU có thể xảy ra ở bước nào giữa approval và provisioning?
20. Làm sao chống approve hai lần hoặc replay quyết định cũ?
21. Sau khi rút approval, làm sao chứng minh quyền đã bị chặn?
22. Break-glass cần điều kiện và evidence nào?
23. Viết ba negative tests cho self-approval, wrong tenant và Leaver.
24. Nêu năm KPI đánh giá chất lượng workflow ngoài tốc độ duyệt.
25. Vì sao policy DENY có thể phủ quyết resource owner approval?

## 35. Ghi nhớ

**Resource owner approval** là **quyết định có thẩm quyền của chủ sở hữu tài nguyên** về việc cho phép **một beneficiary cụ thể** truy cập **đúng resource, action, tenant, scope và khoảng thời gian**. Quyết định phải dựa trên **ownership registry đáng tin, approver đã xác thực, delegation hợp lệ, policy/SoD, nhu cầu nghiệp vụ và các điều kiện của vòng đời danh tính**, đồng thời có audit đủ để tái hiện.

Trong **Joiner–Mover–Leaver**, **HRIS/identity proofing** xác lập danh tính và quan hệ làm việc, **IdP/SSO** xác thực, **IGA/approval workflow** quyết định điều kiện cấp quyền, **SCIM/API/Directory** provision hoặc revoke account/role, **RBAC/ABAC/PBAC và PEP** thực thi quyền, còn **reconciliation** xác minh trạng thái thực. **APPROVED không có nghĩa quyền đã được cấp; approval còn hạn không chứng minh quyền vẫn hợp lệ sau Mover/Leaver; owner không được vượt explicit security DENY.** Thiết kế đúng phải chống **self-approval, sai owner, replay, race condition, vượt phạm vi, request cũ và quyền truy cập tồn dư**.
