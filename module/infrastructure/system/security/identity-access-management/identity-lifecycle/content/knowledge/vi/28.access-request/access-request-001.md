# Access request là gì trong quản lý vòng đời danh tính IAM?

## 1. Khái niệm Access request

**Access request** là một **yêu cầu có cấu trúc để xin cấp, thay đổi, gia hạn hoặc thu hồi quyền truy cập** vào tài nguyên, ứng dụng hoặc chức năng cụ thể. Trong **Identity and Access Management (IAM)**, yêu cầu này là đầu vào của một **quy trình ra quyết định và thực thi có kiểm soát**: xác định người cần quyền, lý do, phạm vi, điều kiện, người có thẩm quyền phê duyệt, thời hạn và bằng chứng kết quả.

Ví dụ, Lan là nhân viên mới của bộ phận Finance. Lan cần được xem báo cáo chi phí, nên gửi yêu cầu xin quyền **reports.read** trong ứng dụng Finance Portal. Yêu cầu có thể đi qua người quản lý và chủ dữ liệu. Khi được phê duyệt, IAM mới điều phối việc gán nhóm hoặc entitlement ở ứng dụng. Cuối cùng, hệ thống cần **đọc lại quyền tại đích** để xác minh Lan thật sự có thể truy cập đúng báo cáo được phép mà không có quyền thừa.

**Access request không đồng nghĩa access granted.** Việc bấm nút “Gửi yêu cầu”, nhận email “Đã phê duyệt”, hay thậm chí connector trả “HTTP 200” chưa đủ để kết luận quyền đã hoạt động đúng. Request, approval, provisioning, authorization và reconciliation là các trạng thái hoặc trách nhiệm riêng.

Bài học thuộc chương **Access request** trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi mô-đun gồm quản lý danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh chủ thể, tạo account và cấp quyền đến rà soát/thu hồi sau thay đổi vai trò; liên kết **IdP, SSO, SCIM, RBAC/ABAC, service account, kiểm toán** và giảm **quyền truy cập tồn dư**.

### Mục tiêu sau bài học

Sau khi học, người đọc có thể:

1. Giải thích Access request và phân biệt với authentication, authorization, approval và fulfillment.
2. Nhận diện thông tin cần có của một yêu cầu cấp quyền hợp lệ.
3. Mô tả vòng đời request, những bên tham gia và các trạng thái có thể phát sinh.
4. Hiểu cách **risk, least privilege, SoD, RBAC/ABAC và JIT access** ảnh hưởng quyết định.
5. Kết nối quy trình request với **IdP/SSO/SCIM**, entitlement thực tế và vòng đời JML.
6. Thiết kế xử lý timeout, từ chối, lỗi provisioning, sửa yêu cầu, hết hạn và thu hồi.
7. Ghi audit và đo lường sự khác biệt giữa **đã yêu cầu – đã duyệt – đã cấp – đã xác minh**.

## 2. Phân biệt các thuật ngữ thường bị nhầm

| Khái niệm | Câu hỏi nó trả lời | Ví dụ | Điều không tự bảo đảm |
|---|---|---|---|
| **Identity proofing** | Người đăng ký gắn với danh tính khai báo đến mức nào? | HRIS và hồ sơ đã được xác minh | Có quyền truy cập một ứng dụng |
| **Authentication** | Ai đang kiểm soát phiên/credential này? | Lan đăng nhập IdP bằng security key | Được duyệt truy cập dữ liệu Finance |
| **Access request** | Ai xin quyền nào, trên đối tượng nào và vì sao? | Xin reports.read cho project Alpha | Yêu cầu chắc chắn sẽ được chấp nhận |
| **Approval** | Chủ thể có thẩm quyền đồng ý cấp quyền chưa? | Chủ dữ liệu phê duyệt | Connector đã tạo group ở đích |
| **Provisioning** | Hệ thống có cập nhật account/group/entitlement? | SCIM thêm thành viên nhóm | Phiên/token cũ đã hết quyền khác |
| **Authorization** | Action có được phép tại thời điểm request? | API cho phép đọc báo cáo cụ thể | Đã thực hiện xong access review |
| **Fulfillment** | Yêu cầu đã được thực thi đủ các thao tác cần thiết? | IAM hoàn thành cấp quyền | Không có sai lệch quyền nếu chưa readback |
| **Reconciliation** | Trạng thái thực tế khớp trạng thái mong muốn? | Readback nhóm và thử kiểm soát policy | Mọi hệ thống ngoài phạm vi đều an toàn |
| **Access review/attestation** | Quyền đang có còn cần và hợp lệ không? | Manager chứng nhận role theo quý | Mọi quyền không hợp lệ đã được gỡ thật |

**Request là một đối tượng nghiệp vụ trong workflow**, còn **permission, entitlement, group, role** là các đối tượng dùng để biểu diễn và thực thi quyền.

### Một câu dễ nhớ

**Request → Decision → Provision → Verify** là chuỗi logic phổ biến. Khi có thay đổi danh tính hoặc hết thời hạn, chuỗi còn cần **Revoke → Verify revoked**.

## 3. Vì sao doanh nghiệp cần quy trình Access request?

Nếu quyền được cấp bằng email tự do hoặc tin nhắn “cho mình admin với”, tổ chức thường gặp các vấn đề:

- Không có cách thống nhất để biết **ai đang xin quyền** và **xin thay cho ai**.
- Không ghi nhận được **mục đích nghiệp vụ, thời hạn và phạm vi**.
- Người cấp quyền dựa vào quan hệ cá nhân, không xác minh **owner** hoặc SoD.
- Một yêu cầu chung chung có thể dẫn tới role quá rộng, trái **least privilege**.
- Không có cơ chế phát hiện entitlement đã hết hạn nhưng vẫn hoạt động.
- Một nhân viên đổi phòng ban được **cộng quyền mới mà không thu hồi quyền cũ**.
- Khi người nghỉ việc, IAM không biết quyền nào được cấp theo **quan hệ** nào để thu hồi.
- Kiểm toán chỉ có email hoặc ticket không thể nối tới **thay đổi quyền thực tế**.

Access request chuyển quyết định cấp quyền thành một quá trình **có thể truy vết, giải thích, tự động hóa và đối soát**. Tuy nhiên, tăng số bước phê duyệt không tự nâng bảo mật; những yêu cầu rủi ro thấp có thể được **tự động phê duyệt theo policy** nếu đã xác minh đủ điều kiện.

## 4. Ai tham gia một Access request?

| Vai trò | Trách nhiệm điển hình | Giới hạn cần giữ |
|---|---|---|
| **Requester** | Người khởi tạo yêu cầu | Không mặc nhiên có quyền phê duyệt |
| **Beneficiary / subject** | Người hoặc workload sẽ được nhận quyền | Có thể khác requester |
| **Manager** | Xác minh nhu cầu công việc, chức năng và thời hạn | Không nhất thiết là owner dữ liệu |
| **Resource owner / Data owner** | Quyết định ai được truy cập tài nguyên nhạy cảm | Không nên phê duyệt ngoài phạm vi sở hữu |
| **Application owner** | Xác minh entitlement và khả năng cấp quyền ở ứng dụng | Không tự thay thế SoD/security policy |
| **IAM/IGA** | Điều phối request, policy, approval và fulfillment | Không nên cấp ngoài quyết định được phê duyệt |
| **Security / Compliance** | Quy định mức rủi ro, SoD, ngoại lệ và kiểm toán | Không thể chỉ dựa vào tên role để đánh giá quyền |
| **IdP** | Authentication/MFA/SSO và trạng thái danh tính | Không tự biết toàn bộ quyền local app |
| **Provisioning connector** | Gọi SCIM/API/CLI theo scope được phép | HTTP success chưa đủ là readback |
| **Policy engine / PEP** | Kiểm quyền tại action và resource thực tế | Phải có dữ liệu được xác minh |
| **Auditor** | Đánh giá quá trình, evidence và ngoại lệ | Không tự cấp quyền cho chính mình |

### Xin quyền cho người khác

Quản lý có thể xin quyền cho nhân viên mới, hoặc người bảo trợ xin quyền cho nhà thầu. Hệ thống phải ghi **requesterId** và **beneficiaryId** **riêng**. Quyền kiểm tra phải áp lên **beneficiary**, còn quyền được phép gửi yêu cầu thay người khác phải áp lên **requester**.

Ví dụ, yêu cầu có thể do manager gửi nhưng account cần provision là user của nhân viên; gửi đúng request không cho phép manager tự đăng nhập bằng account người đó.

## 5. Những loại Access request phổ biến

| Loại yêu cầu | Mục đích | Ví dụ |
|---|---|---|
| **Grant** | Cấp một quyền chưa có | Gán role REPORT_READER |
| **Modify / Change** | Đổi phạm vi hoặc điều kiện của quyền | Chuyển region North sang South |
| **Revoke / Remove** | Chủ động yêu cầu gỡ quyền | Thu hồi nhóm SALES_EXPORT |
| **Renew / Extend** | Gia hạn quyền có thời hạn | Gia hạn quyền truy cập dự án thêm hai tuần |
| **Temporary / JIT** | Cấp quyền trong cửa sổ ngắn | production.deploy trong 30 phút |
| **Privileged access** | Yêu cầu action quản trị nhạy cảm | user.assignRole, database.admin |
| **Delegated access** | Quyền theo ủy quyền được kiểm soát | Người thay thế duyệt đơn trong thời hạn |
| **Contractor/Partner access** | Quyền gắn quan hệ hợp đồng | Đối tác vào portal dự án |
| **Non-human access** | Credential/scope cho service/workload | Batch job đọc bucket cụ thể |
| **Emergency / Break-glass** | Truy cập khẩn cấp theo thủ tục riêng | Xử lý sự cố khi luồng duyệt chuẩn không khả dụng |

Một hệ thống có thể gom các loại trong một portal, nhưng **policy xét duyệt và cơ chế thu hồi không nhất thiết giống nhau**. Ví dụ, request đổi department không nên được dùng như cách tự gia hạn quyền Admin.

### Access request khác incident/change ticket

- **Incident** mô tả sự cố cần khắc phục.
- **Change request** mô tả thay đổi dự kiến của hệ thống.
- **Access request** mô tả cụ thể entitlement hoặc hành động truy cập được xin.

Các ticket có thể liên kết với nhau qua **purposeRef**, nhưng một incident được mở **không tự có nghĩa yêu cầu quyền đặc biệt được phê duyệt**.

## 6. Access catalog: làm sao để người dùng xin đúng quyền?

**Access catalog** là danh mục những quyền hoặc gói quyền mà một đối tượng đủ điều kiện có thể yêu cầu. Nó giúp tránh người dùng phải đoán tên group kỹ thuật như **app_fin_read_v3**.

Một mục catalog nên mô tả:

- **Tên nghiệp vụ** và mục đích dễ hiểu.
- **Application/resource** được bảo vệ.
- **Action hoặc entitlement** thực sự cấp.
- **Phạm vi**: tenant, region, project, bộ dữ liệu, môi trường.
- **Mức rủi ro** và điều kiện xác thực/MFA.
- **Eligibility**: vai trò, quan hệ, đội ngũ nào có thể yêu cầu.
- **Approval route**: manager, data owner, security hoặc policy tự duyệt.
- **Thời hạn mặc định/tối đa**.
- **Fulfillment method**: SCIM Group, API hoặc PAM.
- **Owner và kỳ access review**.

### Ví dụ mục catalog

~~~json
{
  "catalogItemId": "finance-report-reader",
  "displayName": "Xem báo cáo chi phí Finance",
  "applicationId": "finance-portal",
  "allowedActions": ["report.read"],
  "resourceScopeType": "department",
  "eligiblePopulation": "ACTIVE_FINANCE_EMPLOYEES",
  "riskLevel": "MODERATE",
  "approvalRoute": ["LINE_MANAGER", "DATA_OWNER"],
  "maxDurationDays": 90,
  "fulfillmentType": "SCIM_GROUP_MEMBERSHIP",
  "technicalEntitlement": "finance-report-read",
  "ownerTeam": "Finance-Data"
}
~~~

Đây là **schema minh họa**, không phải SCIM core schema. Giá trị **technicalEntitlement** là định danh cần được mapping tới hệ thống đích; không nên để người dùng tự nhập một tên role bất kỳ rồi yêu cầu IAM cấp ngay.

### Giảm role explosion

Catalog nên ưu tiên **business access** có ranh giới rõ. Tách những thuộc tính như region, tenant hoặc project thành scope được xác minh khi thích hợp, thay vì sinh một role mới cho mọi tổ hợp. Nhưng những **chức năng nghiệp vụ khác biệt** như **report.read** và **payment.approve** vẫn cần phân quyền riêng.

## 7. Thông tin tối thiểu của một Access request

Một yêu cầu đủ điều kiện tự động hóa thường cần các trường:

| Trường | Mục đích | Quy tắc |
|---|---|---|
| **requestId** | ID của workflow | Sinh ở server, không trùng |
| **requestType** | Grant/Change/Revoke/Renew/JIT | Chọn trong loại hỗ trợ |
| **requesterId** | Ai tạo yêu cầu | Xác minh từ session/ticket được tin |
| **beneficiaryId** | Ai nhận quyền | Gắn identity bền vững và quan hệ |
| **relationshipId** | Căn cứ công việc/hợp đồng | Phân biệt nhiều quan hệ của cùng người |
| **applicationId** | Ứng dụng đích | Chọn từ catalog đã quản trị |
| **catalogItemId** | Quyền được xin | Không nhận quyền không tồn tại |
| **resourceScope** | Phạm vi tài nguyên | Tenant/region/project theo chính sách |
| **justification** | Mục đích nghiệp vụ | Đủ cụ thể và tránh chứa dữ liệu nhạy cảm không cần |
| **requestedFrom/Until** | Thời điểm hiệu lực | Có timezone và không vượt TTL |
| **approvals** | Ai duyệt và trên căn cứ nào | Độc lập, có timestamp và policy |
| **state/version** | Trạng thái và phiên bản workflow | Hỗ trợ retry/concurrency |
| **correlationId** | Liên kết event/connector/audit | Không dùng làm credential |
| **sourceEventId** | Tham chiếu JML khi có | Tránh xử lý sự kiện cũ |
| **idempotencyKey** | Hạn chế request trùng khi hỗ trợ | Gắn với ngữ nghĩa giao dịch ổn định |

**Không đặt password, access token, private key, mã recovery hay token connector vào request.** Request mô tả nhu cầu và quyết định, không phải kho lưu bí mật.

## 8. Ví dụ JSON yêu cầu cấp quyền

~~~json
{
  "requestId": "ar-20261123-0018",
  "requestType": "GRANT",
  "requesterId": "person-7812",
  "beneficiaryId": "person-2046",
  "relationshipId": "employment-2046-v1",
  "applicationId": "finance-portal",
  "catalogItemId": "finance-report-reader",
  "requestedAccess": {
    "action": "report.read",
    "scope": {
      "tenantId": "org-vn",
      "department": "Finance"
    }
  },
  "purposeRef": "TASK-2026-1427",
  "justification": "Xử lý báo cáo chi phí của nhóm được phân công",
  "requestedFrom": "2026-12-01T08:00:00+07:00",
  "requestedUntil": "2027-02-28T17:00:00+07:00",
  "requestState": "PENDING_APPROVAL",
  "policyVersion": "finance-access-v4",
  "correlationId": "corr-b3e5"
}
~~~

Ví dụ này minh họa **một bản ghi workflow đã được tạo hoặc bổ sung dữ liệu phía server**, không phải payload khách hàng được quyền chọn mọi trường. Trong hệ thống thật, server cần tự sinh requestId, xác minh requesterId từ phiên, xác định beneficiary/relationship và xác thực thời hạn/tenant.

### Những khái niệm dễ sai

- **requesterId khác beneficiaryId:** manager đang xin quyền cho nhân viên.
- **requestedUntil không phải grantedUntil:** thời hạn được phê duyệt có thể **ngắn hơn** thời hạn xin.
- **GRANT request không phải ACTIVE entitlement:** trạng thái request vẫn đang PENDING_APPROVAL.
- **Scope không nên suy từ email:** tenant và department phải được đối chiếu nguồn tin cậy.
- **Policy version không tự bảo đảm policy đúng:** phải được quản lý, review và kiểm thử.

## 9. Quy trình Access request từ đầu tới cuối

~~~mermaid
flowchart TD
    START[Người dùng hoặc sự kiện JML] --> SUB[Submit access request]
    SUB --> VAL{Identity / catalog / scope hợp lệ?}
    VAL -->|Không| REJ[Reject / yêu cầu bổ sung]
    VAL -->|Có| ELIG{Eligibility + risk + SoD}
    ELIG -->|Không đạt| REJ
    ELIG -->|Đạt| APP{Cần phê duyệt?}
    APP -->|Có| ROUTE[Manager / Resource owner / Security]
    ROUTE --> DEC{Approval decision}
    DEC -->|Deny| REJ
    DEC -->|Approve| PROV[Provision theo desired state]
    APP -->|Policy auto-approve| PROV
    PROV --> VERIFY{Readback target + authorization}
    VERIFY -->|Chưa đúng| FIX[Retry / remediation / escalation]
    FIX --> PROV
    VERIFY -->|Đúng| GRANT[Fulfilled / access verified]
    GRANT --> EVENT[Expiry / Mover / Leaver / revoke]
    EVENT --> REMOVE[Remove entitlements + revoke token/session]
    REMOVE --> CHECK[Verify revoked và audit]
~~~

Đây là **một workflow tham khảo**, không phải mọi sản phẩm đều triển khai các trạng thái như nhau. **Vòng retry cần giới hạn và có owner**; nếu không thể cấp hoặc gỡ quyền đúng, workflow phải ghi **PARTIAL/FAILED** thay vì lặp vô hạn.

### Tám bước nên có

1. **Submit:** xác nhận người yêu cầu và nhu cầu.
2. **Validate:** kiểm tra dữ liệu, quan hệ, catalog và thời điểm hiệu lực.
3. **Evaluate:** đánh giá least privilege, eligibility, SoD, risk và thời hạn.
4. **Approve:** thu quyết định từ những chủ thể/phần mềm có thẩm quyền.
5. **Fulfill:** điều phối cập nhật account, group, entitlement hoặc JIT grant.
6. **Verify:** đọc trạng thái đích và đánh giá quyền thực thi.
7. **Notify:** phản hồi chính xác, không thông báo thành công giả.
8. **Review/revoke:** kiểm tra khi hạn đến, vai trò thay đổi hoặc Leaver.

## 10. Request state machine: có những trạng thái nào?

Một hệ thống nên phân biệt rõ **trạng thái request** và **trạng thái entitlement**.

| Request state minh họa | Ý nghĩa | Có thể dùng quyền chưa? |
|---|---|---|
| **DRAFT** | Chưa gửi yêu cầu | Không vì request này |
| **SUBMITTED** | Đã gửi và có mã theo dõi | Chưa |
| **VALIDATING** | Đang kiểm tra đầu vào và eligibility | Chưa |
| **PENDING_APPROVAL** | Chờ người/policy có thẩm quyền | Chưa |
| **REJECTED** | Không chấp thuận | Không |
| **CANCELED** | Người yêu cầu hoặc chính sách hủy | Không; nếu đã cấp một phần phải rollback/revoke |
| **APPROVED** | Có quyết định cho phép fulfillment | Chưa chắc |
| **PROVISIONING** | Đang cập nhật ứng dụng đích | Chưa chắc |
| **VERIFYING** | Đang đọc lại trạng thái | Chưa khẳng định |
| **FULFILLED** | Quyền được cấp và xác minh trong phạm vi | Có thể, tùy hiệu lực thời gian và phiên |
| **PARTIAL/FAILED** | Có sai lệch hoặc thất bại | Không được kết luận hoàn thành |
| **EXPIRED/REVOKED** | Quyền liên quan đã kết thúc | Không nên cho action tiếp tục |

Không nhất thiết mọi hệ thống giữ đủ các trạng thái. Điều quan trọng là **phân biệt mốc quyết định, thao tác ở đích và quyền sử dụng thực tế**.

### Trạng thái entitlement riêng

Một quyền có thể ở trạng thái **NOT_GRANTED, ACTIVE, SUSPENDED, EXPIRED, REVOKED**. Sau khi request FULFILLED, một sự kiện Leaver có thể khiến entitlement REVOKED, trong khi lịch sử request vẫn giữ **FULFILLED** như sự kiện cấp quyền đã diễn ra trong quá khứ. Không được dùng status lịch sử để quyết định quyền ở thời điểm hiện tại.

### Yêu cầu thay đổi hoặc hủy giữa chừng

Nếu request được sửa **scope, thời hạn hoặc người hưởng quyền**, hệ thống phải đánh giá lại ảnh hưởng lên approval. Không được giữ nguyên chữ ký phê duyệt cho một yêu cầu khác bản chất. Nếu request bị hủy **sau khi connector đã cấp một phần quyền**, phải có **compensating action** và đối soát phần đã thực hiện.

## 11. Eligibility: ai được quyền xin?

**Eligibility** quyết định một chủ thể có **được phép gửi yêu cầu cho loại quyền/phạm vi cụ thể** hay không. Nó khác với **đã được cấp quyền**.

Ví dụ:

- Nhân viên Finance ACTIVE có thể xin quyền Finance Reader.
- Kỹ sư nằm trong lịch on-call có thể xin quyền JIT restart đúng service.
- Nhà thầu chỉ được xin quyền ở project có sponsor và hợp đồng còn hiệu lực.
- Người đã Leaver không được kích hoạt quyền mới.
- Một manager có thể gửi request thay nhân viên thuộc đội mình nhưng không xin quyền cho người ngoài tenant trái chính sách.

### Những điều kiện cần xem

| Điều kiện | Ví dụ | Nguồn đáng tin |
|---|---|---|
| **Lifecycle state** | ACTIVE, chưa đến effectiveAt của Leaver | HRIS/IAM |
| **Relationship** | Hợp đồng còn hiệu lực | HRIS/contract registry |
| **Job function** | Nhân viên Finance | HRIS/IGA approved mapping |
| **Resource ownership** | Thuộc project hoặc tenant đúng | Registry/tài nguyên |
| **Training/certification** | Có chứng nhận khi policy yêu cầu | Hệ thống được ủy quyền |
| **Existing access** | Đã có hoặc không có quyền tương đương | Target readback |
| **SoD constraints** | Không giữ quyền xung đột | IAM policy và lịch sử nghiệp vụ |
| **Risk/MFA/device** | Phiên đủ assurance | IdP, thiết bị được quản lý |
| **Time** | Chưa quá hạn và đúng cửa sổ | Clock server và policy |

**Không để người dùng tự điền lifecycleState=ACTIVE hoặc roles=ADMIN rồi sử dụng trực tiếp trong policy.** Mọi attribute bảo mật cần có nguồn được xác minh.

## 12. Least privilege: xin đúng action, resource và thời hạn

Yêu cầu quyền nên bám theo ba chiều:

\[
AccessNeed = (Action,\ ResourceScope,\ TimeWindow)
\]

Ví dụ:

| Nhu cầu | Yêu cầu quá rộng | Yêu cầu đúng hơn |
|---|---|---|
| Xem báo cáo tháng | Finance Global Admin | report.read trên department được giao |
| Restart một service | Cloud Owner toàn subscription | service.restart cho service cụ thể, 30 phút |
| Xuất dữ liệu phục vụ kiểm toán | Database superuser | report.export dataset đã duyệt, có masking |
| Quản lý nhóm một dự án | Directory Admin | project.member.add trên project đó |
| Tạo deployment | Production Admin thường trực | JIT deployment.deploy trên service/environment |

**Mục đích phải gắn với quyền.** Một request “cần admin để làm việc” thiếu mô tả nhiệm vụ có thể cần yêu cầu bổ sung. Ngược lại, không nên yêu cầu diễn giải quá dài cho các quyền baseline rủi ro thấp khi đã có bằng chứng chính thức.

### Để tránh role explosion

Quyền yêu cầu có thể được biểu diễn bằng **role chức năng** cộng **resource scope** thay vì tạo role riêng cho mọi vùng, tenant, dự án. Điều kiện này chỉ an toàn khi ứng dụng đích **thực sự thực thi scope**; một catalog ghi “region=north” nhưng connector gán global-admin vẫn là sai quyền.

## 13. Approval workflow: ai quyết định cấp quyền?

Approval nhằm bảo đảm quyền phù hợp nhu cầu và rủi ro. Một route có thể gồm:

- **Manager approval:** xác nhận nhiệm vụ và lý do.
- **Resource/Data owner approval:** xác nhận được phép truy cập dữ liệu hoặc hệ thống.
- **Application owner approval:** xác nhận entitlement đúng và ứng dụng chịu tác động.
- **Security/Compliance approval:** xử lý quyền đặc quyền, SoD hoặc ngoại lệ.
- **Automatic policy approval:** khi điều kiện đủ rõ, ít rủi ro và được phê duyệt trước qua policy.

### Ma trận approval minh họa

| Yêu cầu | Tính chất | Cơ chế xét |
|---|---|---|
| Đọc wiki của bộ phận | Baseline thấp | Policy có thể tự duyệt |
| Finance report reader | Dữ liệu nội bộ | Manager + data owner khi policy yêu cầu |
| Xuất dữ liệu khách hàng nhạy cảm | Rủi ro cao | Owner + risk controls/MFA |
| production.deploy | Đặc quyền tạm | JIT, step-up, SoD và approver độc lập |
| user.assignRole | Quyền quản trị IAM | Security/IAM owner phù hợp |
| Service account secret.read | Credential nhạy cảm | Workload owner + secret owner |
| Contractor admin | Quan hệ bên ngoài | Sponsor, owner và thời hạn chặt |

**Không phải tất cả request cần cùng số vòng phê duyệt.** Một quy trình quá nhiều bước có thể khiến mọi người tìm đường vòng. Mục tiêu là kiểm soát dựa trên **rủi ro, chính sách và trách nhiệm**, không phải số nút Approve.

## 14. SoD và những trường hợp không được tự duyệt

**Separation of Duties (SoD)** ngăn một người vừa tạo, duyệt, thực thi hoặc kiểm chứng những bước xung đột trong cùng một quy trình khi chính sách cấm.

### Ví dụ static SoD

Người có quyền **vendor.create** không được đồng thời có quyền **vendor.payment.approve** trong cùng phạm vi nếu quy định nội bộ cấm kết hợp.

### Ví dụ dynamic SoD

Lan có role **FINANCE_APPROVER**, nhưng không được **invoice.approve** đối với hóa đơn do chính Lan tạo. Approval của request cấp role không thay thế kiểm tra SoD ở từng hóa đơn.

### Những kiểm tra quan trọng

1. Requester có đang tự duyệt request của mình không?
2. Approver có được cấp quyền duyệt đúng **scope** và còn ACTIVE không?
3. Approver có quan hệ phụ thuộc/xung đột cần tách nhiệm vụ không?
4. Grant mới có làm người nhận đồng thời nắm hai quyền xung đột không?
5. Existing direct grants, nested groups và role inheritance có bị bỏ sót không?
6. Ủy quyền phê duyệt có còn hạn và không bị mở rộng quyền ngoài policy không?

**Đừng chỉ kiểm tên role.** Phải xem **effective permissions**, resource scope và lịch sử thao tác khi có dynamic SoD.

## 15. Risk-based approval và MFA

Hệ thống có thể đánh giá rủi ro dựa trên **độ nhạy của resource, action, phạm vi dữ liệu, thời hạn, đặc quyền, trạng thái thiết bị và dấu hiệu hành vi**.

| Mức rủi ro | Ví dụ | Hướng kiểm soát |
|---|---|---|
| **Thấp** | Đọc tài liệu nội bộ thông thường | Điều kiện eligibility + auto-approval phù hợp |
| **Trung bình** | Xem dữ liệu khách hàng theo team | Manager/resource owner và scope |
| **Cao** | Export hàng loạt, sửa quyền IAM | Approval độc lập, MFA/step-up, monitoring |
| **Rất cao/khẩn cấp** | Break-glass, root production, secret read | PAM/JIT, thời hạn ngắn, giám sát và post-review |

### MFA không đồng nghĩa approval

**MFA** chứng minh phiên đang đáp ứng điều kiện xác thực, còn **approval** là quyết định cấp quyền có căn cứ nghiệp vụ. Một người có security key không tự trở thành admin; một approver bấm đồng ý cũng không thay thế điều kiện **phishing-resistant MFA** nếu policy yêu cầu.

### Thời điểm xác thực

Với action đặc quyền, có thể yêu cầu **step-up gần thời điểm activation hoặc thực thi**. Một session SSO đã xác thực từ nhiều giờ trước không mặc nhiên đáp ứng tất cả quyết định rủi ro cao.

## 16. Policy evaluation trước và sau approval

Các điều kiện an toàn cần được kiểm tra ở **thời điểm quyết định** và, khi tình huống đòi hỏi, **ngay trước lúc cấp quyền**.

Giả sử request được duyệt lúc 09:00 nhưng chờ queue. Đến 09:05, HRIS phát Leaver hiệu lực ngay. Nếu connector lúc 09:10 vẫn cấp quyền chỉ vì request đã APPROVED thì hệ thống đã tạo truy cập trái chính sách.

### Giả mã minh họa

~~~text
function evaluateAccessRequest(request, phase):
    requester = loadTrustedIdentity(request.requesterId)
    beneficiary = loadTrustedIdentity(request.beneficiaryId)
    relationship = loadCurrentRelationship(request.relationshipId)
    catalogItem = loadApprovedAccessCatalog(request.catalogItemId)

    if not requesterCanRequestFor(requester, beneficiary):
        return DENY

    if not relationship.belongsTo(beneficiary):
        return DENY

    if not relationship.isActiveFor(request.requestedFrom):
        return DENY

    if not catalogItem.allows(request.target, request.scope):
        return DENY

    if not meetsLeastPrivilegeAndDuration(request, catalogItem):
        return DENY

    if hasSeparationOfDutiesConflict(beneficiary, request):
        return DENY

    if requiresStrongAuth(request) and not verifiedAssuranceSatisfied():
        return REQUIRE_STEP_UP

    if not approvedUnderCurrentRules(request):
        return PENDING_APPROVAL

    if phase == BEFORE_PROVISIONING:
        latest = readCurrentAuthoritativeLifecycle(beneficiary)
        if latest.isTerminatedOrSuspendedFor(request):
            return DENY
        if request.version != loadLatestRequestVersion(request.id):
            return STALE_REQUEST

    return PERMIT_FULFILLMENT
~~~

Đây là **giả mã định hướng**, không phải ngôn ngữ tiêu chuẩn SCIM/OIDC hoặc code production. Một số grant hợp lệ trong tương lai có thể được provision trước effectiveAt nhưng **không được thực thi sớm**. Quy trình cần mô hình riêng cho **prepared vs active**, không đánh đồng “chưa ACTIVE” với “tuyệt đối không thể chuẩn bị”.

### Chính sách không làm thay provisioning

Policy trả **PERMIT_FULFILLMENT** chỉ cho phép thực hiện bước cấp quyền. Kết quả thành công cuối còn phụ thuộc vào **connector, trạng thái đích, RBAC/ABAC và reconciliation**.

## 17. Từ Access request đến RBAC/ABAC/PBAC và action thật

Một request có thể chỉ định **business entitlement**, còn backend ứng dụng cần đánh giá quyền thực tế.

Ví dụ Lan xin **Finance Reports Reader**. IGA ánh xạ catalog item tới nhóm SCIM **finance-report-read**. Khi Lan gọi API, hệ thống có thể kiểm:

~~~text
permit if
    identity.lifecycleState == ACTIVE
    and action == "report.read"
    and subject.hasPermission("finance.report.read")
    and resource.tenantId == subject.tenantId
    and resource.department in subject.allowedDepartments
    and resource.classification <= subject.clearance
    and session.meetsAuthenticationPolicy
else deny
~~~

Đây là giả mã logic; so sánh classification cần dùng thứ bậc chuẩn do tổ chức quản lý, không so sánh chuỗi tùy ý.

### Những lớp không thể bỏ qua

- **RBAC:** role/group cho phép loại thao tác nào.
- **ABAC:** thuộc tính người, tài nguyên, ngữ cảnh giới hạn phạm vi.
- **PBAC:** kết hợp rule và guardrail.
- **ReBAC:** quyền do quan hệ như owner/member/delegated approver nếu có.
- **Object-level authorization:** có quyền trên báo cáo **nào**.
- **SoD:** có xung đột với các quyền/hành động khác không.
- **Session/MFA:** phiên còn hiệu lực và đủ mức xác thực không.

**Access request được duyệt không thay thế việc kiểm quyền tại mỗi action.** Nếu ứng dụng chỉ kiểm route hoặc chỉ thấy token có scope read, người dùng có thể truy cập tài nguyên ngoài tenant.

## 18. IdP, SSO, SCIM và Access request phối hợp thế nào?

### IdP/SSO

IdP xác thực người dùng, thực thi MFA và cung cấp federation (SAML/OIDC). **SSO không tự tạo tất cả entitlement**. Người dùng có thể đăng nhập ứng dụng thành công nhưng thiếu group hoặc role.

### SCIM provisioning

SCIM 2.0 thường đồng bộ **User/Group** qua HTTP API. IAM/IdP provisioning connector có thể thêm User vào Group sau phê duyệt và gỡ quyền khi hết hạn.

Điểm cần hiểu:

- **SCIM User** không phải Access request; bản ghi User phản ánh tài khoản ở SP.
- **SCIM User.groups** trong core schema là read-only; thay membership thường qua **Group.members** khi đích hỗ trợ.
- SCIM không định nghĩa một workflow **approval request** chung trong core User/Group.
- **active=false** thường được dùng để yêu cầu deactivate User, nhưng không mặc nhiên thu hồi mọi local session hoặc access token.
- Một số role/license/permission ở SaaS cần **API riêng**, không chỉ Group API.

### Kiến trúc liên kết

~~~mermaid
flowchart LR
    HR[HRIS / contract authority] --> IAM[IAM / IGA]
    U[Requester / beneficiary] --> PORTAL[Access request portal]
    PORTAL --> IAM
    IAM --> POLICY[Eligibility / Approval / SoD]
    POLICY --> PROV[Provisioning / SCIM / API]
    PROV --> APP[Ứng dụng đích]
    IAM --> IDP[IdP / SSO / MFA]
    IDP -->|SAML/OIDC| APP
    APP --> AUTH[RBAC/ABAC/PBAC tại action]
    APP --> RECON[Target readback / Reconciliation]
    RECON --> IAM
    IAM --> AUDIT[Audit / Access review]
~~~

**Cấp account, xác thực và phân quyền là ba lớp riêng**. Access request giúp chúng có cùng căn cứ và evidence, nhưng không thay thế một lớp bằng lớp khác.

## 19. Fulfillment: thực hiện quyền ở hệ thống đích

Khi đã được phê duyệt, fulfillment có thể gồm nhiều tác vụ:

1. Tạo hoặc xác minh account tại hệ thống đích.
2. Liên kết identity ID với target account ID đáng tin.
3. Gán Group/Role/Entitlement theo catalog mapping.
4. Điều chỉnh scope, effectiveFrom/Until hoặc conditional policy.
5. Cấp credential ngắn hạn hoặc mở PAM session nếu là JIT.
6. Đánh dấu kết quả từng connector và ghi evidence.
7. Đọc lại trạng thái đích để kiểm tính đúng đắn.

### Một request có thể cần nhiều connector

Ví dụ quyền Finance Analyst yêu cầu một group ở SaaS, một cloud role và quyền đọc view ở database. Nếu hai thao tác thành công và một thất bại, không được thông báo “toàn bộ quyền đã cấp”. Hệ thống cần thể hiện **PARTIAL** và quyết định có cần rollback hoặc hoàn tất nốt theo policy.

### Không gán quyền rộng để che lỗi

Nếu role FINANCE_READER chưa map được ở ứng dụng, đội vận hành không nên “cấp tạm Admin cho chạy”. Cần xử lý catalog/connector mapping, áp quyền tối thiểu và ghi exception có hạn nếu tổ chức cho phép.

## 20. Idempotency, timeout và sự kiện đến sai thứ tự

Hệ thống IAM thường bất đồng bộ: request qua queue, connector timeout, webhook gửi trùng, HRIS cập nhật sau. Access request cần **retry có kiểm soát**.

### Tình huống 1: cấp thành công nhưng response mất

IAM gửi SCIM PATCH thêm Group.members; ứng dụng đã thêm thành viên nhưng mạng timeout trước khi trả response. Nếu worker retry mù quáng, có thể phát sinh sai lệch hoặc lỗi tùy provider.

**Xử lý:** đọc lại membership, đối chiếu targetUserId/GroupId và desired state trước khi retry. Không coi timeout là “chắc chắn chưa làm”.

### Tình huống 2: tạo User trùng

Sau POST /Users timeout, retry POST mà không lookup có thể tạo account trùng hoặc nhận 409. Cần **mapping bằng immutable ID**, target readback và xử lý nhiều ứng viên thay vì chọn account đầu tiên có email giống.

### Tình huống 3: Leaver xảy ra khi request đang chờ

Một request đã được APPROVED cho nhân viên, nhưng trước khi fulfillment người đó đã Leaver. Worker không được thực hiện grant bằng snapshot cũ. Phải **kiểm lại authoritative lifecycle** và chặn các workflow lỗi thời bằng **version/fencing**.

### Tình huống 4: sửa request sau approval

Yêu cầu được duyệt cho **read**, nhưng requester sửa thành **export**. Approval cũ không còn bao phủ action mới; phải **invalidate quyết định cũ** và đưa request qua quy trình xét phù hợp.

### Nguyên tắc ổn định

- Mỗi request có **requestId** ổn định.
- Mỗi operation có **correlation/operation ID** và desired state rõ.
- Worker có cơ chế **deduplication** và kiểm version.
- **Read-before-create** cho outcome chưa xác định.
- Retry có **backoff, giới hạn và cảnh báo**.
- Không dùng job cũ để tái cấp quyền sau Mover/Leaver.
- Phân biệt **acknowledgment** với trạng thái sau readback.

## 21. Access request trong Joiner lifecycle

Joiner liên quan danh tính mới và quyền cần thiết để bắt đầu công việc. Có thể kết hợp **birthright access** tự động với Access request cho quyền đặc biệt.

### Birthright access là gì?

Đây là nhóm quyền baseline được policy xác định từ vị trí/quan hệ chính thức, ví dụ nhân viên mới được cấp tài khoản email và quyền xem tài liệu đào tạo. **Không nhất thiết phải tạo request thủ công cho mọi quyền baseline**, nhưng vẫn nên có event/provisioning evidence và khả năng audit.

### Khi nào Joiner cần Access request riêng?

- Cần quyền dữ liệu nhạy cảm ngoài baseline.
- Cần quyền quản trị hoặc xuất dữ liệu.
- Cần phê duyệt của chủ tài nguyên.
- Cần truy cập project theo nhiệm vụ không suy được từ job role.
- Cần quyền có thời hạn, nhà thầu hoặc đối tác.

### Luồng Joiner

1. HRIS/nguồn hợp đồng xác minh personId, relationshipId, effectiveAt.
2. IAM kiểm tra identity proofing, tránh tài khoản trùng, chuẩn bị account IdP.
3. Enrollment/MFA được hoàn thành theo yêu cầu.
4. Policy tính baseline access và eligibility request.
5. Request riêng được gửi khi cần, với approval và phạm vi.
6. SCIM/API provisioning tài khoản và entitlement ở đích.
7. Ứng dụng kiểm RBAC/ABAC tại action; IAM readback.
8. Chỉ thông báo sẵn sàng khi các quyền **cần cho nhiệm vụ tại thời điểm đó** đã đạt.

**Account được tạo trước ngày đi làm không có nghĩa request được phép kích hoạt quyền trước effectiveAt.** Một số hệ thống có thể chuẩn bị sớm nhưng phải chặn thực thi cho đến khi điều kiện hợp lệ.

## 22. Access request trong Mover lifecycle

Mover xảy ra khi nhân viên đổi bộ phận, vai trò, manager, dự án, hợp đồng hoặc phạm vi. Cần quản lý **quyền mới cần cấp** và **quyền cũ phải gỡ**.

### Ví dụ

Lan chuyển từ Sales sang Finance:

| Entitlement/action | Trước Mover | Sau Mover mong muốn | Tác vụ |
|---|---|---|---|
| CRM Sales Reader | Có | Không | Revoke |
| Customer Export | Có qua ngoại lệ | Không | Revoke sớm |
| Finance Report Reader | Không | Có | Grant theo policy |
| Invoice Approver | Không | Chỉ nếu được duyệt | Access request + SoD |
| Production Admin | Không | Không | Không cấp |

### Vấn đề khi chỉ xử lý request mới

Nếu IAM chỉ thấy “đã cấp Finance Reader” và đóng Mover, tài khoản có thể vẫn giữ quyền export khách hàng. Đây là **privilege accumulation**. Mover cần **so sánh tập quyền mong muốn với quyền đang có**, tạo revoke operations và xác minh tại đích.

### Request đang chờ khi thay đổi vai trò

Một request xin quyền Sales chưa được duyệt khi Lan chuyển sang Finance nên được **đánh giá lại hoặc hủy**. Không nên gửi thông báo approved của một nhiệm vụ cũ rồi cấp entitlement vào tài khoản hiện tại. Policy cần xét **relationship/job version** tại thời điểm quyết định và fulfillment.

## 23. Access request trong Leaver lifecycle

Khi quan hệ nhân sự kết thúc, hệ thống phải xử lý **mọi yêu cầu còn mở** và **những quyền đã cấp** liên quan.

### Danh sách công việc

1. Xác minh sự kiện Leaver từ nguồn có thẩm quyền, relationshipId và effectiveAt.
2. **Chặn request mới**, activation hoặc gia hạn trái policy.
3. **Hủy/đình chỉ request đang chờ** có căn cứ đã hết hiệu lực.
4. **Thu hồi entitlement** đã cấp qua những request trước đây theo phạm vi quan hệ.
5. Disable hoặc hạn chế account IdP/SSO và hủy phiên phù hợp.
6. Deactivate/thu hồi group tại ứng dụng qua SCIM/API.
7. Xử lý local account, PAT, API key, SSH key, access/refresh token, PAM session và credential độc lập.
8. Chuyển owner dữ liệu/workload khi cần, không xóa mù quáng tài nguyên nghiệp vụ.
9. Đối soát quyền thực tế; nếu chưa thu hồi được, giữ workflow **PARTIAL/OPEN**.

### Trường hợp Leaver khẩn cấp

Nếu nhân viên nghỉ hiệu lực ngay lúc 16:00 trong khi một access request đã được duyệt lúc 15:50 nhưng chưa cấp, hệ thống phải **chặn fulfillment**. Nếu đã cấp một phần, phải có compensation/revocation ở đích.

### Một người có nhiều quan hệ

Một cá nhân có thể có đồng thời quan hệ **employee** và **contractor** được phép. Khi một quan hệ kết thúc, cần thu hồi quyền phát sinh từ quan hệ đó; không nên xóa nhầm mọi quyền hợp lệ của quan hệ khác. **Relationship ID và nguồn cấp quyền** giúp xác định đúng phạm vi.

### Yêu cầu đã FULFILLED trước đây có phải xóa?

Không. Thông thường cần giữ **bằng chứng lịch sử** theo chính sách lưu giữ, nhưng trạng thái quyền hiện tại phải là revoked/absent khi quan hệ không còn căn cứ. **Không dùng trạng thái FULFILLED lịch sử làm quyết định cho request đăng nhập mới.**

## 24. Renewal, expiration và Just-in-time access

Nhiều quyền chỉ nên được cấp **trong thời gian cần thiết**:

- Access theo dự án tới ngày đóng dự án.
- Nhà thầu tới ngày hết hợp đồng.
- Quyền export trong một kỳ kiểm toán.
- Privileged access 30–60 phút hoặc một cửa sổ tác vụ.
- Delegated approval khi người có trách nhiệm vắng mặt.

### Cửa sổ hiệu lực

Một cách mô hình hóa:

\[
GrantValid(t) \iff effectiveFrom \leq t < effectiveUntil
\]

Mốc effectiveUntil là **exclusive bound**; tại hoặc sau thời điểm đó, grant không còn được phép. Cần kiểm tra thời gian server đáng tin, timezone và clock skew.

### Renewal có phải tự động?

Không nên coi renewal là một thuộc tính tự nối dài. Gia hạn cần kiểm tra lại **quan hệ đang ACTIVE, nhiệm vụ còn hợp lệ, owner, approval, SoD, mức rủi ro và giới hạn tổng thời gian**. Đặc biệt với quyền nhạy cảm, không nên để chuỗi renewal tự động biến JIT thành standing access.

### Eligible không đồng nghĩa Active

Trong JIT/PAM/PIM:

- **Eligible:** được phép **xin kích hoạt** một quyền.
- **Active:** grant đã kích hoạt, có phạm vi và thời hạn.
- **Expired/Revoked:** không được dùng làm căn cứ Permit.

Một access request được duyệt để **eligible** không có nghĩa role đang Active. Hệ thống cần ghi rõ outcome thuộc loại nào.

## 25. Nhà thầu, đối tác và delegated request

Access request không chỉ phục vụ nhân viên nội bộ.

### Contractor/Partner

Khi một nhà thầu cần quyền vào project:

- Sponsor và source hợp đồng phải xác minh **quan hệ, scope và ngày hết hạn**.
- Tài khoản có thể được federation tới IdP của đối tác hoặc tạo guest account theo policy.
- Quyền phải có **resource owner** và giới hạn môi trường.
- Request expiry không được vượt điều kiện hợp đồng nếu policy cấm.
- Khi hợp đồng chấm dứt, ngừng cả **eligibility, grants, phiên và credential** liên quan.
- Không mặc định HRIS nhân viên nội bộ là nguồn đầy đủ của tất cả contractor.

### Delegated requester

Người quản lý hoặc service desk có thể tạo request thay người khác. Cần:

- Kiểm quyền **canRequestFor(requester, beneficiary)**.
- Xác định **beneficiary** bằng ID tin cậy, không chỉ email.
- Hạn chế cấp quyền vào tenant, region hoặc app ngoài phạm vi quản lý.
- Ghi rõ **ai khởi tạo, ai phê duyệt, ai hưởng quyền**.
- Tránh cho người được ủy quyền tạo request tự phê duyệt dưới danh nghĩa người khác.

### Delegated access

Yêu cầu được **ủy quyền thực thi action** (ví dụ trợ lý duyệt thay) khác với yêu cầu “gửi thay”. Nó cần policy riêng về **principal, action, resource, duration và giới hạn ủy quyền**.

## 26. Service account, workload và non-human Access request

Service account, bot, thiết bị và workload cũng cần truy cập, nhưng thường **không có lifecycle nhân sự trực tiếp**. Request cần dựa trên **workload registry và technical owner**.

| Yếu tố | Ví dụ |
|---|---|
| **Beneficiary** | workload:reporting-batch |
| **Owner** | Analytics Platform Team |
| **Action** | object.read |
| **Resource** | bucket reports-prod/approved |
| **Environment** | production |
| **Purpose** | Job tạo báo cáo định kỳ |
| **Grant mechanism** | Workload identity federation hoặc IAM role hẹp |
| **Credential** | Token ngắn hạn, managed identity, certificate |
| **Review/expiry** | Theo dự án, workload lifecycle |
| **Owner Leaver handling** | Chuyển owner, rà soát secret và quyền |

**Không cho bot dùng mật khẩu SSO của nhân viên hoặc chia sẻ account admin chung.** Khi nhân viên owner nghỉ việc, không nhất thiết xóa workload sản xuất hợp lệ; cần **thay owner và đánh giá lại quyền/secret**.

### Tránh confused deputy

Nếu service A xin quyền gọi API B, token/grant phải rõ **subject, client, audience và resource**. Không truyền token dành cho API A tới mọi dịch vụ khác rồi coi là đã ủy quyền phù hợp.

## 27. Break-glass: Access request khẩn cấp

**Break-glass** dành cho tình huống khẩn cấp được quy định trước, khi luồng bình thường có thể không đủ nhanh hoặc không khả dụng.

| Kiểm soát | Yêu cầu |
|---|---|
| **Eligibility** | Tài khoản/chủ thể được xác định trước |
| **Purpose** | Incident thực sự và lý do khẩn cấp |
| **Approval/alternative** | Đường kiểm soát thay thế đã được tổ chức phê duyệt |
| **Scope** | Quyền tối thiểu có thể đạt trong sự cố |
| **Credential** | Vault/offline protection tùy kiến trúc, không chia sẻ vô kiểm soát |
| **Duration** | Giới hạn và thu hồi sớm khi sự cố qua |
| **Audit/Alert** | Cảnh báo gần thời gian thực và ghi bằng chứng |
| **Post-review** | Phân tích sau sự cố, xác nhận không lạm dụng |
| **Testing** | Đảm bảo đường khẩn cấp thật sự hoạt động khi IdP/PAM outage |

**Break-glass không phải đường bỏ qua kiểm toán hoặc Permit-all vĩnh viễn.** Nếu tạm nới một số điều kiện, phải có căn cứ và compensating controls. Không đánh đồng mọi request “URGENT” với break-glass hợp lệ.

## 28. Audit trail: những sự kiện cần ghi lại

Để trả lời “vì sao người này có quyền này?”, chuỗi audit cần nối các điểm:

1. **RequestCreated** – requester, beneficiary, scope, catalog item, purpose.
2. **Validated/Rejected** – kết quả eligibility và lý do.
3. **ApprovalRequested** – approver route và mốc.
4. **ApprovalGranted/Denied** – quyết định, actor, policy version.
5. **ProvisioningStarted** – connector, target, operation ID.
6. **ProvisioningAcknowledged** – kết quả API, không chứa bí mật.
7. **EntitlementObserved** – readback account/role/group và thời điểm.
8. **AccessActivated** – từ thời điểm nào, phạm vi nào.
9. **AccessUsed** – action, resource, outcome tại điểm thực thi khi cần.
10. **AccessExpired/Revoked** – nguyên nhân, phiên/token và target cleanup.
11. **RevocationObserved** – bằng chứng chặn truy cập.
12. **AccessReviewAttested** – reviewer và quyết định tiếp tục/gỡ quyền.

### Ví dụ audit event

~~~json
{
  "eventId": "audit-ar-20261123-029",
  "correlationId": "corr-b3e5",
  "requestId": "ar-20261123-0018",
  "operationId": "scim-add-finance-report-2046",
  "subjectId": "person-2046",
  "targetSystem": "finance-portal",
  "targetAccountId": "app-user-7839",
  "entitlement": "finance-report-read",
  "eventType": "EntitlementObserved",
  "observedState": "PRESENT",
  "sourcePolicyVersion": "finance-access-v4",
  "eventTime": "2026-12-01T08:03:00+07:00"
}
~~~

Ví dụ này không phải schema audit chuẩn. Mọi log phải bảo vệ PII theo quyền truy cập/retention, và **không chứa password, access token, refresh token, private key hoặc session cookie**.

### Phê duyệt và thực thi phải tách evidence

Một bản ghi ApprovalGranted cho biết quyết định; một bản ghi EntitlementObserved cho biết trạng thái đích. Nếu không tìm được evidence đích, không thể khẳng định việc phê duyệt đã được thực thi đủ.

## 29. Reconciliation: chứng minh quyền đã cấp đúng hoặc thu hồi đúng

**Reconciliation** đối chiếu:

- **Desired state** – IAM tính từ JML, policy, approval và các request còn hiệu lực.
- **Observed state** – account, group, role, direct grants, session/credential đọc được tại hệ thống đích.

| Sai lệch | Tình huống | Hướng xử lý |
|---|---|---|
| **MISSING_ENTITLEMENT** | Đã duyệt nhưng target chưa cấp | Retry hợp lệ, điều tra connector |
| **EXCESS_ENTITLEMENT** | Target giữ quyền không thuộc desired state | Gỡ/điều tra căn cứ quyền |
| **WRONG_TARGET_ACCOUNT** | Gán quyền vào account trùng email | Khóa mapping, sửa theo identity ID |
| **EXPIRED_BUT_ACTIVE** | Quyền hết hạn vẫn được thực thi | Thu hồi/chặn và ghi incident |
| **LEAVER_RESIDUAL_ACCESS** | Account đã Leaver nhưng còn session/API key | Xử lý đa lớp |
| **DUPLICATE_REQUEST** | Hai request cấp cùng quyền không rõ source | Deduplicate, không xóa quyền còn căn cứ hợp lệ |
| **UNOWNED_GRANT** | Không có owner hoặc căn cứ approval | Review/thu hồi theo rủi ro |
| **PARTIAL_FULFILLMENT** | Một số connector thành công, số khác thất bại | Compensation và tiếp tục đối soát |

### Bằng chứng từ từng hệ thống

- SCIM/API GET/lookup về User và Group.
- Cloud IAM role binding/permission readback.
- Database privileges và active sessions.
- SaaS local role/direct entitlement.
- Token introspection/RS state khi áp dụng.
- PAM session/grant status.
- Resource/action authorization tests có kiểm soát.

**Một request trạng thái FULFILLED không chứng minh mọi đường truy cập khác ngoài phạm vi đã thu hồi.** Báo cáo phải ghi **coverage và khoảng trống khả năng quan sát**.

## 30. SLA, sự cố và các chỉ số vận hành

### Một số SLA cần phân biệt

- **Time to first decision:** từ Submitted đến được xử lý/nhận quyết định.
- **Approval lead time:** từ chờ phê duyệt đến quyết định.
- **Provisioning lead time:** từ Approved đến connector hoàn tất thao tác.
- **Time to verified access:** từ Approved đến readback quyền hoạt động đúng.
- **Time to revoke:** từ mốc hết hiệu lực/Leaver đến hệ thống đích ngừng chấp nhận quyền.
- **Exception resolution time:** thời gian finding còn mở.

Đối với quyền bình thường, hiệu quả là **thời gian cấp hợp lý và quyền đúng**; đối với Leaver hoặc thu hồi khẩn cấp, ưu tiên là **thời gian chặn thực tế**.

### Metrics gợi ý

| Chỉ số | Ý nghĩa |
|---|---|
| **Request volume by access type** | Loại quyền thường được xin, phục vụ cải thiện catalog |
| **Auto-approval rate by risk tier** | Tỷ lệ tự duyệt với rủi ro phù hợp |
| **Approval aging** | Request chờ lâu, owner hoặc approver không phản hồi |
| **Rejection and rework rate** | Chất lượng catalog/đầu vào và policy |
| **Fulfillment success rate** | Tỷ lệ cấp đúng trên toàn bộ connector bắt buộc |
| **Partial provisioning backlog** | Quyền cấp một phần còn chưa xử lý |
| **Verified grant coverage** | Tỷ lệ request có readback đích |
| **Expired rights still active** | Quyền hết hạn chưa bị thu hồi |
| **Mover excess entitlement count** | Quyền cũ còn sau chuyển vai trò |
| **Leaver revoke latency** | Độ trễ chặn sau effectiveAt |
| **Unowned access catalog items** | Quyền không có owner hoặc approval route |
| **SoD violations prevented** | Số request xung đột được chặn |
| **Request-to-identity mapping errors** | Sai beneficiary/target ID |
| **Break-glass usage** | Số lượt khẩn cấp và nguyên nhân |
| **Audit/reconciliation coverage** | Mức bằng chứng và hệ thống được bao phủ |

Không đánh giá thành công chỉ dựa vào **số request được phê duyệt**: phê duyệt nhanh nhưng cấp sai phạm vi hoặc không thể thu hồi có thể làm tăng rủi ro.

## 31. Runbook: xử lý Access request bị kẹt hoặc cấp sai

### A. Request chờ phê duyệt quá lâu

1. Xác minh request chưa hết hạn, beneficiary còn quan hệ hợp lệ.
2. Kiểm approval route và owner của catalog item.
3. Tìm trường hợp approver đã đổi role/Leaver.
4. Escalate theo chính sách, không tự đổi approver sang chính requester.
5. Nếu nhu cầu đã hết, cancel request thay vì duyệt muộn.

### B. APPROVED nhưng chưa có quyền

1. Kiểm target account mapping (immutable ID thay vì email).
2. Kiểm connector được phép gọi đúng tenant/endpoint.
3. Đọc kết quả từng operation và lỗi HTTP/API.
4. Với timeout, readback trước khi retry.
5. Kiểm Group/Role/Permission tại target và thời điểm hiệu lực.
6. Kiểm SSO/MFA/session nếu quyền đã provision mà user vẫn không dùng được.
7. Không cấp quyền Admin rộng để sửa một request Reader.

### C. Đã thu hồi ở IAM nhưng vẫn dùng được

1. Ưu tiên chặn action rủi ro tại ứng dụng/gateway theo khả năng.
2. Kiểm target direct grants, nested groups và local account.
3. Kiểm token còn hạn, session cookie, refresh token và cache role.
4. Kiểm kết quả SCIM/API và eventual consistency.
5. Đối soát từng hệ thống trong phạm vi và lập finding nếu còn tồn dư.
6. Chỉ đóng khi bằng chứng đích xác nhận đã bị chặn hoặc ngoại lệ được quản lý rõ ràng.

### D. Quyền bị cấp nhầm người

1. Xác định target account thực nhận entitlement.
2. Ngăn quyền không đúng và đánh giá tác động dữ liệu.
3. So sánh requester/beneficiary, identity/relationship và mapping target.
4. Kiểm request trùng, email đã tái sử dụng hoặc filter trả nhiều user.
5. Sửa mapping theo nguồn có thẩm quyền, không tự sửa bằng username giống nhau.
6. Ghi incident/audit và bổ sung kiểm thử chống tái diễn.

## 32. Ví dụ xuyên suốt: Access request qua Joiner–Mover–Leaver

Giả sử Lan gia nhập công ty, ban đầu là nhân viên Sales rồi chuyển sang Finance. Tổ chức có IdP dùng SSO, IGA và các ứng dụng được provision qua SCIM/API.

### Giai đoạn 1 — Joiner

HRIS ghi nhận Lan bằng **person-2046**, relationshipId và ngày hiệu lực. IAM tạo account IdP và cấp baseline Sales. Lan hoàn thành enrollment MFA. Lan cần đọc báo cáo Sales cho project Alpha nên gửi **Access request** với action **report.read**, resource scope và thời hạn. Manager xác nhận nhiệm vụ, data owner chấp thuận. SCIM connector tạo membership tại ứng dụng, IAM readback xác nhận quyền đúng tenant. Lan đăng nhập SSO và chỉ đọc được dữ liệu được cho phép.

### Giai đoạn 2 — Yêu cầu đặc quyền có thời hạn

Lan hỗ trợ sự cố cần xuất dữ liệu để đối chiếu trong 45 phút. Lan không được tự có standing **DATA_ADMIN**. JIT broker kiểm eligibility, MFA, ticket và approval rồi kích hoạt **report.export** trên dataset được phép trong cửa sổ đã duyệt. Khi hết hạn, hệ thống phải gỡ grant và kiểm token/phiên để không còn export trái policy.

### Giai đoạn 3 — Mover

Lan chuyển sang Finance. HRIS cập nhật job/relationship version. IAM tính lại desired state: gỡ quyền Sales, cấp Finance Reader theo policy và đưa một request xin **invoice.approve** qua SoD/phê duyệt riêng. Một request Sales export cũ còn chờ phải bị hủy hoặc đánh giá lại, không được cấp sau Mover.

### Giai đoạn 4 — Leaver

Lan nghỉ việc, sự kiện Leaver có hiệu lực. IdP disable login, các request đang chờ bị vô hiệu, IGA thu hồi các entitlement và JIT grants thuộc quan hệ. SCIM/API deprovision account/group ở ứng dụng, đồng thời xử lý local session, PAT, OAuth token, secret và các đường truy cập ngoài SSO. Nếu connector báo thành công nhưng API vẫn chấp nhận token cũ, workflow **chưa được xem là thu hồi hoàn tất**.

### Giai đoạn 5 — Rejoiner

Lan quay lại làm việc tại vị trí khác. IAM có thể liên kết lịch sử identity theo chính sách, nhưng phải xác minh quan hệ mới. Các approval, access request hay entitlement cũ **không tự phục hồi**. Việc cấp quyền mới dựa trên nhiệm vụ và nguồn phê duyệt hiện tại.

### Bài học rút ra

**Access request là bản ghi nhu cầu và quyết định cấp quyền, không phải trạng thái quyền vĩnh viễn.** Để bảo đảm an toàn xuyên suốt JML, mỗi request phải được gắn đúng identity/relationship, qua policy và approval phù hợp, fulfillment có kiểm soát, readback và thu hồi khi căn cứ quyền kết thúc.

## 33. Checklist thiết kế hệ thống Access request

1. **Định nghĩa:** đã tách request, approval, provisioning, authorization và reconciliation?
2. **Chủ thể:** requester và beneficiary được lưu riêng với identity ID tin cậy?
3. **Quan hệ:** relationshipId, effectiveAt và nguồn HRIS/contract có được kiểm tra?
4. **Catalog:** quyền xin có tên nghiệp vụ, scope, owner và mapping entitlement?
5. **Action/resource:** đã xác định action cụ thể và tài nguyên/tenant/environment?
6. **Least privilege:** request không mặc định gán role quá rộng hoặc vô thời hạn?
7. **Eligibility:** người hưởng quyền còn ACTIVE và thuộc population được xin?
8. **Approval:** approver có đủ thẩm quyền, không tự phê duyệt sai SoD?
9. **MFA/risk:** action nhạy cảm có step-up và controls tương ứng?
10. **Request state:** có phân biệt SUBMITTED, APPROVED, PROVISIONING, VERIFIED, PARTIAL?
11. **Timeout/retry:** connector có readback trước khi retry outcome không rõ?
12. **Concurrent changes:** request version và source JML version có ngăn grant lỗi thời?
13. **SSO/SCIM:** đã phân biệt đăng nhập và provisioning tài khoản/nhóm?
14. **RBAC/ABAC/PBAC:** API vẫn kiểm action/object/context khi sử dụng?
15. **Joiner:** baseline được cấp đúng lúc, quyền đặc biệt cần request riêng?
16. **Mover:** quyền cũ bị thu hồi, request đang chờ được đánh giá lại?
17. **Leaver:** request đang chờ bị vô hiệu và quyền/token/session/credential bị xử lý?
18. **Expiry/JIT:** quyền tạm có thời hạn và được thu hồi thật?
19. **Rejoiner:** approval/role cũ không tự được kích hoạt lại?
20. **Contractor:** sponsor và thời hạn hợp đồng được đưa vào eligibility?
21. **Non-human:** workload có owner, client identity và credential riêng?
22. **Break-glass:** có quy trình khẩn cấp có kiểm soát, audit và post-review?
23. **Evidence:** lưu request, decision, target operation, readback và revocation với correlation ID?
24. **PII/secrets:** log không chứa token, private key, password hoặc dữ liệu nhạy cảm không cần?
25. **Metrics:** đo time-to-verified-access và time-to-revoke, không chỉ approve rate?
26. **Coverage:** đã biết rõ các app/credential ngoài SSO và những giới hạn reconciliation?
27. **Closure:** chỉ đóng fulfillment/revocation khi trạng thái đích đạt yêu cầu và sai lệch được xử lý?

### Ghi nhớ

**Access request là yêu cầu có căn cứ để cấp, thay đổi, gia hạn hoặc thu hồi quyền của một chủ thể trên tài nguyên xác định.** Một request hợp lệ phải trả lời **ai xin, ai hưởng, quyền gì, ở đâu, vì sao, khi nào, ai duyệt và cách xác minh kết quả**. **Submitted không phải Approved; Approved không phải Provisioned; Provisioned chưa chắc đã Verified.** Trong **IAM Identity Lifecycle**, Access request phải phối hợp với **identity proofing, IdP/SSO, SCIM, RBAC/ABAC, JIT/least privilege, session/token management và reconciliation**; khi **Mover hoặc Leaver**, cần gỡ quyền không còn căn cứ, xử lý request lỗi thời và xác minh **không còn quyền truy cập tồn dư**.
