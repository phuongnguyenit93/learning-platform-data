# Kiểm thử SoD: xác minh phân tách nhiệm vụ từ chính sách đến quyền thực tế

Một hệ thống IAM quy định rằng người **tạo nhà cung cấp** không được đồng thời **phê duyệt thanh toán** cho nhà cung cấp đó. Bộ phận quản trị kiểm tra giao diện: khi một nhân viên đang giữ role `vendor-creator`, nút yêu cầu thêm `payment-approver` bị khóa. Kết quả được ghi “SoD PASS”. Tuy nhiên, một API cấp quyền gọi trực tiếp vẫn chấp nhận yêu cầu; ngoài ra, nhân viên đó có một tài khoản quản trị thứ hai và một group lồng nhau cũng cho phép phê duyệt. **Chính sách có vẻ đúng, nhưng kiểm soát SoD thực tế đã thất bại**.

**Kiểm thử SoD (Segregation/Separation of Duties testing)** là hoạt động xây dựng và thực hiện các kịch bản có thể kiểm chứng để xác nhận rằng **quyền, quy trình phê duyệt, phiên làm việc và giao dịch nhạy cảm không cho một chủ thể hoặc nhóm lợi ích thực hiện những chức năng xung đột trái chính sách**. Kiểm thử phải quan sát **quyết định IAM** và **khả năng thực thi tại ứng dụng đích**, không chỉ nhìn trạng thái một biểu mẫu.

Bài học thuộc chương **Segregation of duties**, đề tài **Kiểm thử SoD**, trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi mô-đun là quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, từ xác minh và tạo tài khoản đến cấp, rà soát và thu hồi quyền khi thay đổi vai trò, có liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Biến **quy tắc SoD** thành **test cases** có điều kiện đầu vào, hành động, kết quả mong đợi và bằng chứng kiểm chứng.
- Phân biệt kiểm thử **Static SoD (SSD)**, **Dynamic SoD (DSD)** và **procedural/maker-checker SoD**.
- Kiểm tra xung đột quyền **trực tiếp, kế thừa, qua nhóm, qua delegation, quyền eligible/JIT và đường nâng đặc quyền**.
- Kiểm thử cả **đường được phép** lẫn **đường phải từ chối**, bao gồm tình huống đồng thời, trạng thái stale và API đi vòng giao diện.
- Xác minh hiệu lực SoD qua **HRIS/IGA/IdP/SSO/SCIM/PAM/ứng dụng**, gắn với Joiner–Mover–Leaver.
- Tổ chức fixture an toàn, tự động hóa kiểm thử, đo coverage, lưu bằng chứng và mở defect/exception đúng rủi ro.

## 1. SoD cần kiểm thử những điều gì?

**SoD** ngăn một chủ thể kiểm soát đồng thời các nhiệm vụ mà policy quy định phải tách biệt để giảm gian lận, sai sót hoặc lạm quyền. Trong IAM, cần kiểm tối thiểu bốn lớp:

1. **Policy/model:** rule xung đột được định nghĩa đúng hành động, tài nguyên, phạm vi và thời gian.
2. **Assignment/eligibility:** hệ thống không gán hoặc cho phép kích hoạt các quyền xung đột trái quy định.
3. **Workflow/transaction:** một người không tự tạo–duyệt–thực hiện những bước bị cấm trên cùng đối tượng.
4. **Effective enforcement:** API/ứng dụng thực sự từ chối thao tác không hợp lệ, kể cả khi user có token, session hoặc account phụ.

### 1.1. Vì sao kiểm thử role name chưa đủ?

| Dữ liệu nhìn thấy | Có thể bỏ sót | Cần kiểm thêm |
| --- | --- | --- |
| Role trực tiếp của user | Quyền qua nested group hoặc role hierarchy. | Effective role và permission graph. |
| IGA approval status | Grant thủ công ngoài IGA. | App-local role, cloud/API grants. |
| User account từ IdP | Admin account phụ cùng Person. | Correlation về canonical subject/Person. |
| Group trong SSO token | Claim cũ, session ứng dụng chưa đổi. | Quyền tại resource và session/token state. |
| SoD rule theo hai role | Quyền qua delegate, credential hoặc role assumption. | Đường hành động thực tế và khả năng nâng quyền. |
| HTTP 200 từ provisioning | Đích vẫn chấp nhận quyền xung đột. | Readback và authorization test. |

**Kết luận kiểm thử không nên là “SoD PASS” toàn bộ nếu mới kiểm một lớp**. Nêu rõ lớp đã kiểm, scope và lớp còn chưa quan sát được.

## 2. Phân loại kịch bản SSD, DSD và procedural SoD

### 2.1. Static SoD (SSD) – xung đột tại thời điểm gán quyền

**SSD** hạn chế cùng một chủ thể **được gán** những role/quyền xung đột trong phạm vi policy quy định, không cần đợi quyền được sử dụng.

Ví dụ:

~~~text
Subject P-1042 có permission vendor.create trong businessUnit=A.
Yêu cầu gán payment.approve trong businessUnit=A.
Policy: không cho cùng subject sở hữu cả hai quyền trong A.

Expected: DENY_GRANT / REQUIRE_CONTROLLED_EXCEPTION.
~~~

Kiểm thử phải thử cả **role trực tiếp** và **quyền tương đương lấy từ nhóm hoặc role khác**. Nếu policy là SSD cấm đồng sở hữu quyền, không được coi “role B chưa active trong session” là lý do cho phép assignment.

### 2.2. Dynamic SoD (DSD) – xung đột khi kích hoạt hoặc dùng quyền

**DSD** có thể cho user đủ điều kiện nắm nhiều role nhưng **không được kích hoạt hoặc dùng** chúng đồng thời theo ràng buộc phiên/giao dịch.

Ví dụ:

~~~text
User được đào tạo cả vai trò initiator và approver.
Trong giao dịch TX-8802:
    actor của bước create = P-1042.
    actor của bước approve không được là P-1042.

Expected:
    P-1042 approve TX-8802 -> DENY.
    P-2088 approve TX-8802 nếu đủ điều kiện khác -> PERMIT.
~~~

DSD thường yêu cầu **lịch sử giao dịch, canonical actor identity và transaction ID**. Chỉ nhìn group membership không chứng minh rule đã được thực thi. Không phải ứng dụng nào cũng hỗ trợ kích hoạt role theo phiên; khi đó phải kiểm ở **điểm quyết định giao dịch**.

### 2.3. Procedural SoD – độc lập trong workflow

Ví dụ yêu cầu cấp quyền production:

~~~text
Requester: người khởi tạo
Beneficiary: người được hưởng quyền
Approver: người có authority phê duyệt
Executor: connector chạy lệnh
Verifier: hệ thống/đội xác minh trạng thái đích
~~~

Test phải chứng minh **beneficiary không tự duyệt**, approver không nằm ngoài phạm vi được ủy quyền, executor không tự tạo quyết định approved và verifier không chỉ tin trạng thái do executor tự ghi.

### 2.4. Cùng một hệ thống có thể cần cả ba

| Kiểm soát | Test cần quan sát | Ví dụ |
| --- | --- | --- |
| **SSD** | Tập quyền hiệu lực sau grant không vi phạm ma trận xung đột. | Không giữ đồng thời vendor.create và payment.approve trong cùng unit. |
| **DSD** | Một actor không thực hiện hai bước xung đột trong cùng transaction. | Người tạo giao dịch không tự duyệt giao dịch. |
| **Procedural** | Người hưởng lợi và người quyết định độc lập theo policy. | Không tự duyệt role admin. |
| **Reconciliation** | Provider không tồn tại grant trái policy ngoài workflow. | Direct local role không được bỏ sót sau khi kiểm SSD ở IGA. |

## 3. Tiêu chí pass/fail phải xuất phát từ policy nghiệp vụ

Một test SoD có ý nghĩa khi mỗi expectation được liên kết tới **quy tắc được phê duyệt**:

| Thành phần rule | Ví dụ | Câu hỏi kiểm thử |
| --- | --- | --- |
| **conflictId** | SOD-PAY-001 | Test nào bảo vệ rule này? |
| **businessPurpose** | Tránh tự tạo vendor và tự trả tiền. | Có đúng mục tiêu nghiệp vụ không? |
| **permissionA/B** | vendor.create / payment.approve | Role nào cấp hai permission đó? |
| **subjectMatching** | canonical Person/controlling principal | Hai account có thể thuộc một người? |
| **scopeMatching** | cùng tenant và businessUnit | Xung đột có áp dụng giữa hai unit? |
| **resource/transaction** | cùng vendor hoặc payment TX | Test có kiểm đúng đối tượng nghiệp vụ? |
| **SoD type** | SSD, DSD, procedural | Kiểm assignment hay hành động? |
| **effectiveTime** | thời điểm role/quan hệ có hiệu lực | Có lệnh cũ hoặc rule mới đến muộn? |
| **exceptionPolicy** | chỉ Security + Risk Owner được chấp thuận trong thời hạn | Ai được cho ngoại lệ và điều kiện nào? |
| **owner/version** | finance-controls / v5 | Ai chịu trách nhiệm khi test thất bại? |

### 3.1. Tiêu chí an toàn và tiêu chí liveness

Kiểm thử SoD không chỉ chứng minh **người không hợp lệ bị từ chối**. Còn phải bảo đảm **người đủ tư cách vẫn thực hiện được thao tác hợp lệ**, tránh quy trình bị khóa hoàn toàn.

- **Safety:** không có đường trái policy dẫn đến trạng thái quyền/giao dịch bị cấm.
- **Liveness:** thao tác đủ phê duyệt, không xung đột, đúng phạm vi vẫn có thể hoàn tất.

Ví dụ một engine trả DENY cho mọi request có thể vượt qua tất cả negative tests nhưng **không đạt yêu cầu vận hành**. Vì vậy mỗi nhóm negative test nên có **positive counterpart**.

## 4. Viết test plan SoD theo phạm vi và rủi ro

Trước khi tự động hóa, cần xác định phạm vi bài kiểm thử và người chịu trách nhiệm.

### 4.1. Test plan tối thiểu

| Trường | Nội dung cần ghi |
| --- | --- |
| **testPlanId/version** | Phiên bản có thể truy vết. |
| **systemUnderTest** | IAM/IGA, approval API, PDP, connector, ứng dụng đích. |
| **policy scope** | Conflict rules và risk tier thuộc bài test. |
| **identity scope** | Employee, Contractor, secondary admin accounts, workload. |
| **entitlement sources** | Direct role, group, hierarchy, local role, JIT, delegation. |
| **environment/data** | Sandbox/staging, dữ liệu giả, hệ thống kiểm thử được ủy quyền. |
| **time semantics** | effectiveAt, expiresAt, timezone, event ordering. |
| **preconditions** | Catalog/fixture/role mapping/account đúng phiên bản. |
| **expected decisions** | PERMIT, DENY, NEED_APPROVAL, INDETERMINATE... theo engine. |
| **verification method** | API response, readback, audit, transaction history và hiệu lực tại PEP. |
| **cleanup/rollback** | Thu hồi fixture roles, session và credential sau test. |
| **owners/sign-off** | Policy owner, application owner, test owner và người xử lý defect. |

### 4.2. Phân tầng theo rủi ro

Ưu tiên cao các cặp quyền:

- **Tạo danh tính + tự cấp đặc quyền**.
- **Reset MFA/credential + giả danh/phê duyệt**.
- **Sửa policy kiểm soát + tắt audit/giám sát**.
- **Tạo vendor + duyệt thanh toán**.
- **Sửa bảng lương + phê duyệt chi lương**.
- **Sửa pipeline production + tự vượt release gate**.
- **Thay classification tài liệu + tự duyệt quyền export**.

Role với tên `viewer` không mặc nhiên là low-risk nếu có khả năng xuất dữ liệu cực kỳ nhạy cảm. Risk tier phải dựa trên **permission và blast radius**, không chỉ tên nhóm.

## 5. Ma trận truy vết yêu cầu → test → bằng chứng

Để tránh kiểm thử tùy hứng, mỗi rule cần ít nhất một test xác nhận **đường từ chối** và một test xác nhận **đường cho phép hợp lệ**.

| Rule ID | Điều kiện bị cấm | Test IDs gợi ý | Evidence cần có |
| --- | --- | --- | --- |
| SOD-SSD-001 | Cùng Person giữ hai role xung đột trong cùng unit. | SSD-01, SSD-02, SSD-03. | Effective entitlements trước/sau, decision, source version. |
| SOD-DSD-002 | Cùng actor create/approve một transaction. | DSD-01, DSD-02, DSD-03. | Transaction history, subject IDs, API result. |
| SOD-WF-003 | Beneficiary tự duyệt role đặc quyền. | WF-01, WF-02, WF-03. | Auth actor, approval record, authority lookup. |
| SOD-WF-004 | Delegation khiến self-approval. | WF-04, WF-05. | Delegator/delegate/beneficiary identity. |
| SOD-JML-005 | Quyền cũ của Mover vẫn tạo conflict. | JML-01, JML-02. | HRIS effectiveAt, IGA/target readback. |
| SOD-JML-006 | Grant đến muộn sau Leaver. | JML-03, JML-04. | Event/version, job retry trace, target state. |
| SOD-JIT-007 | User tự kích hoạt quyền production trái policy. | PAM-01, PAM-02. | Eligible/activated role, approval/session. |
| SOD-API-008 | Executor nhận lệnh không có approval hợp lệ. | API-01, API-02. | Request version, service identity, connector logs. |

Mã rule và test **chỉ là ví dụ**. Trong triển khai thật, một rule có thể cần nhiều case theo tenant, role hierarchy, loại principal, provider hoặc thay đổi phiên bản.

### 5.1. Coverage không chỉ là số test chạy

Nếu 100 test đều dùng **một user với direct role**, việc chạy PASS 100/100 **không chứng minh** nested groups, API bypass, session cũ hoặc cross-tenant đã được kiểm. Cần lập **coverage matrix** theo chiều rule, identity type, grant path, enforcement layer và lifecycle state.

## 6. Chuẩn bị dữ liệu kiểm thử và fixture an toàn

SoD testing cần khả năng kiểm soát role, tài khoản và giao dịch. **Không dùng dữ liệu khách hàng thật hoặc cố tạo giao dịch tài chính thật** nếu không thuộc một kế hoạch được cho phép rõ ràng.

### 6.1. Fixture gợi ý

~~~yaml
# Test fixture nội bộ minh họa, không phải schema tiêu chuẩn của IAM.
testRunId: sod-regression-20261201-01
tenantId: tenant-test-a
policyVersion: sod-finance-v5
subjects:
  - subjectId: test-person-maker
    personId: test-person-100
    engagementId: test-emp-100
    lifecycleState: ACTIVE
  - subjectId: test-person-checker
    personId: test-person-200
    engagementId: test-emp-200
    lifecycleState: ACTIVE
accounts:
  - accountId: maker-user
    subjectId: test-person-maker
  - accountId: maker-admin
    subjectId: test-person-maker
  - accountId: checker-user
    subjectId: test-person-checker
roles:
  - vendor-creator
  - payment-approver
  - read-only-auditor
transactions:
  - transactionId: tx-test-001
    ownerBusinessUnitId: unit-a
    initiatedBySubjectId: test-person-maker
~~~

Fixture cần hỗ trợ **phục hồi trạng thái ban đầu** sau khi test, tránh làm các case kế tiếp phụ thuộc kết quả trước đó.

### 6.2. Tách môi trường

- **Unit tests:** dùng fake identity/permission graph và rule evaluator.
- **Integration tests:** tenant thử nghiệm với IAM/IdP/SCIM/PAM, application API được ủy quyền.
- **End-to-end:** request thật trong môi trường thử nghiệm, không dùng tài khoản sản xuất ngoài phạm vi được cho phép.
- **Production-safe validation:** chỉ đánh giá dữ liệu/quyền có read-only authorization hoặc phương pháp xác minh được duyệt; không thử giao dịch phá hủy.

### 6.3. Hạn chế fixture có quyền quá cao

Test principal nên có ID rõ, scope hẹp, credential giới hạn, thời hạn và owner. Không giữ tài khoản `test-admin` tồn tại vĩnh viễn trong production. Khi test thất bại phải **dọn sạch session, token, nhóm và role đã cấp**, đồng thời theo dõi cleanup failure như một rủi ro riêng.

## 7. Cấu trúc một test case SoD có thể kiểm chứng

Một test case đủ rõ để người khác tái chạy cần:

| Thành phần | Ví dụ |
| --- | --- |
| **Test ID** | SSD-01. |
| **Rule version** | SOD-SSD-001 v5. |
| **Purpose** | Ngăn cùng Person giữ hai quyền xung đột trong cùng unit. |
| **Precondition** | Subject ACTIVE, có vendor.create ở unit-a. |
| **Input/action** | Yêu cầu payment.approve ở unit-a. |
| **Expected decision** | DENY hoặc exception route theo policy. |
| **Expected target state** | Không có payment.approve hiệu lực ở unit-a sau request. |
| **Observation** | IGA decision, connector event, provider readback, authorization result. |
| **Cleanup** | Thu hồi fixture grants và token; restore test state. |
| **Evidence reference** | TestRunID, traceId, policyVersion và snapshot. |

### 7.1. Khi nào test FAIL?

Một case **negative** có thể FAIL nếu:

- API/UI trả **APPROVED** dù policy phải từ chối.
- Workflow hiển thị DENY nhưng connector vẫn gửi grant.
- Connector trả lỗi nhưng role đã được cấp ở đích.
- Group bị từ chối nhưng direct role hoặc nested group vẫn cho quyền xung đột.
- Session hoặc token cũ tiếp tục cho thực hiện hành động bị policy cấm.

Một case **positive** có thể FAIL nếu user độc lập và đủ tư cách bị từ chối không có lý do hợp lệ, khiến workflow không thể thực hiện nghiệp vụ.

## 8. Test matrix cho Static SoD

Giả sử policy **không cho một Person giữ vendor.create và payment.approve trong cùng business unit**, trừ ngoại lệ được phê duyệt riêng. Những ví dụ dưới đây giả định cả hai role đều ánh xạ chính xác tới permission tương ứng.

| ID | Trạng thái trước | Hành động | Expected |
| --- | --- | --- | --- |
| **SSD-01** | User có vendor.create ở unit-a. | Gán payment.approve ở unit-a. | **DENY**; không phát sinh quyền mới. |
| **SSD-02** | User chỉ có vendor.create ở unit-a. | Gán report.read ở unit-a. | **PERMIT** nếu đủ điều kiện khác. |
| **SSD-03** | User có vendor.create ở unit-a. | Gán payment.approve ở unit-b. | Theo **scope policy**; có thể PERMIT nếu khác unit không conflict. |
| **SSD-04** | User có vendor.create qua nested group. | Gán payment.approve trực tiếp. | **DENY** nếu quyền hiệu lực bị xung đột. |
| **SSD-05** | User có quyền tương đương vendor.create qua role khác tên. | Gán payment.approve. | **DENY** dựa permission chứ không chỉ role name. |
| **SSD-06** | User có hai account cùng Person. | Account thứ hai xin payment.approve. | **DENY** nếu policy áp ở cấp Person. |
| **SSD-07** | Vendor role đã expired và đã verified revoked. | Gán payment.approve. | Có thể **PERMIT** khi mọi điều kiện khác đủ. |
| **SSD-08** | Vendor role đã hết hiệu lực trên IGA nhưng app còn direct grant. | Gán payment.approve. | **DENY hoặc chưa cho grant**, mở drift theo policy. |
| **SSD-09** | User có role không xung đột; approval hết hạn. | Gán payment.approve. | **DENY/REQUIRE_REAPPROVAL** dù SSD không conflict. |
| **SSD-10** | User có role cấp cao kế thừa vendor.create. | Gán payment.approve. | **DENY** nếu permission kế thừa tạo conflict. |

**SSD-03 là boundary test quan trọng:** không nên hardcode “mọi quyền vendor.create ở bất kỳ tenant nào đều conflict với payment.approve”, trừ khi policy thực sự yêu cầu phạm vi toàn tổ chức.

### 8.1. Kiểm grant và rollback

Sau DENY:

1. Kiểm request không chuyển sang APPROVED trái phép.
2. Kiểm provisioning queue không chứa tác vụ GRANT đã được ủy quyền.
3. Kiểm provider không có role mới qua direct/group/inherited path.
4. Nếu request tạo thay đổi tạm rồi rollback, phải xác minh **quyền thật không còn hoạt động**, không chỉ log ghi rollback.
5. Ghi trace nguyên nhân từ chối ở mức an toàn, không lộ thông tin nhân sự/credential.

## 9. Test matrix cho Dynamic SoD và giao dịch

Giả sử quy trình thanh toán có hai bước **create payment** và **approve payment**, policy cấm cùng một Person làm cả hai trên cùng giao dịch.

| ID | Người tạo | Người duyệt | Ngữ cảnh | Expected |
| --- | --- | --- | --- | --- |
| **DSD-01** | P-100 | P-100 | Cùng transaction TX-1. | **DENY**. |
| **DSD-02** | P-100 | P-200 | Cùng TX-1, P-200 có authority. | **PERMIT** nếu đủ điều kiện khác. |
| **DSD-03** | P-100 qua account thường | P-100 qua admin account | Cùng TX-1. | **DENY** theo Person. |
| **DSD-04** | P-100 | P-200 | P-200 không đủ quyền trên tenant. | **DENY** dù khác người. |
| **DSD-05** | P-100 | P-100 | Transaction TX-2 không do P-100 tạo. | Kết quả phụ thuộc actor tạo TX-2; không tự suy. |
| **DSD-06** | P-100 | P-200 | P-200 là delegate nhưng delegation expired. | **DENY** do authority không hợp lệ. |
| **DSD-07** | P-100 | P-200 | Transaction bị đổi owner/tenant giữa kiểm và commit. | **Recheck** và tuân theo policy mới. |
| **DSD-08** | P-100 | P-200 | Hai yêu cầu approve cùng TX đến đồng thời. | Không thực hiện phê duyệt trùng/trái quy tắc. |
| **DSD-09** | P-100 | P-200 | Cùng Person được thay đổi subject mapping sau request. | Quyết định theo identity mapping có hiệu lực và có bằng chứng. |

### 9.1. Transaction ID phải do hệ thống sở hữu

Nếu client tự gửi `transactionId` không kiểm chứng, họ có thể thay ID để giả vờ đang duyệt một giao dịch khác. Ứng dụng phải resolve giao dịch thực theo tài nguyên đã xác thực, kiểm **actor lịch sử** và đảm bảo không có đường API bỏ qua SoD.

### 9.2. Không phụ thuộc duy nhất vào session role

Nếu DSD yêu cầu ngăn hai role được kích hoạt cùng lúc, kiểm session activation ở session manager. Nếu rule yêu cầu **hai actor khác nhau trong cùng giao dịch**, kiểm ở **transaction service/PEP**. Một UI hiển thị role A hoặc B không đủ để chứng minh hai hành động trên cùng transaction được phân tách.

## 10. Test matrix cho approval workflow và self-approval

| ID | Thiết lập | Hành động | Expected |
| --- | --- | --- | --- |
| **WF-01** | Requester/beneficiary là P-100. | P-100 tự duyệt role admin. | **DENY** theo procedural SoD. |
| **WF-02** | P-100 có user và admin accounts. | Account admin của P-100 duyệt request của account thường. | **DENY** nếu policy cấm self-approval. |
| **WF-03** | Data owner P-200 có authority, độc lập. | Duyệt request đúng role/scope. | **PERMIT** nếu đủ phê duyệt. |
| **WF-04** | P-200 ủy quyền cho P-100 là beneficiary. | P-100 dùng delegation duyệt chính request. | **DENY**. |
| **WF-05** | Delegate P-300 độc lập, delegation hết hạn. | P-300 duyệt sau expiresAt. | **DENY**, chuyển route hợp lệ. |
| **WF-06** | Approver hiện tại không sở hữu tenant-b. | Duyệt request tenant-b. | **DENY** thiếu scope authority. |
| **WF-07** | Maker P-100 có quyền đổi approver của ticket. | Chọn chính P-100 làm approver. | Không cho bypass; route theo authority registry. |
| **WF-08** | UI chặn nút Approve. | Gọi trực tiếp approval API với body giả approved=true. | **DENY/401/403** tùy layer; không thay decision state. |
| **WF-09** | Request version 2 được duyệt, version 3 mở rộng scope. | Thử thực thi approval của version 2 cho version 3. | **DENY/REAPPROVE**. |
| **WF-10** | Reviewer Mover/Leaver mất authority. | Dùng approval link/token đã cấp trước. | **DENY** và reroute theo policy. |

### 10.1. Đừng chỉ kiểm response code

Một API có thể trả 403 nhưng đã ghi trạng thái APPROVED trước khi lỗi; một event async có thể tiếp tục enqueue GRANT. Sau negative test phải kiểm:

- **Workflow state** không được đổi sang APPROVED.
- Không tạo **authorization artifact** còn hợp lệ.
- **Provisioning queue** không chứa lệnh grant trái policy.
- **Đích không nhận entitlement mới**.
- Audit lưu actor thật, request version và lý do từ chối.

## 11. Kiểm thử liên kết danh tính: một người, nhiều tài khoản

SoD theo Person thường khó hơn SoD theo account ID. Một nhân viên có thể có:

~~~text
canonicalPersonId = P-100
  ├── employee-user@enterprise.example  (IdP A)
  ├── employee-admin@enterprise.example (IdP A)
  ├── employee-vendor@partner.example    (IdP B / federation)
  └── một local admin account ở SaaS
~~~

Một test độc lập cần chứng minh:

1. Các account thật sự thuộc **cùng Person** được nhận diện theo nguồn đáng tin.
2. Các account khác Person nhưng trùng tên hiển thị **không bị gộp sai**.
3. Email/UPN thay đổi **không làm mất liên kết SoD**.
4. Email được tái cấp cho người mới **không chuyển quyền hoặc lịch sử Person cũ**.
5. Rehire cùng Person nhưng engagement mới **không tự khôi phục approval/role cũ**.
6. Nếu mapping mơ hồ, hệ thống **không tự kết luận hai account độc lập để cho phép**.

### 11.1. Những ca kiểm thử correlation

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| ID-01 | Hai account cùng immutable subject/person mapping. | Self-approval và SSD áp dụng đồng nhất. |
| ID-02 | Hai người cùng displayName. | Không bị xác định là cùng Person chỉ vì tên. |
| ID-03 | Đổi email/UPN. | SoD rule vẫn áp trên subject hiện hành. |
| ID-04 | Email cũ được tái cấp. | Không kế thừa grant/approvals cũ. |
| ID-05 | Rehire có engagement mới. | Eligibility và policy được kiểm lại. |
| ID-06 | Account ngoại bộ không resolve được. | Giữ trạng thái UNKNOWN/REVIEW, không tự PERMIT. |

Trong môi trường federation, OIDC `sub` chỉ có nghĩa trong phạm vi `iss` của issuer; không đồng nhất hai tài khoản từ các issuer chỉ vì `sub` giống nhau.

## 12. Kiểm thử RBAC, ABAC và phạm vi xung đột

### 12.1. SoD không chỉ là so hai role

Một policy có thể cấm:

~~~text
vendor.create AND payment.approve
IF subject == same canonical person
AND resource.tenantId == same tenant
AND resource.businessUnitId == same business unit
AND transaction.vendorId == same vendor
~~~

Rule này cần **RBAC/permission graph** để biết actor có hành động nào, **ABAC/resource context** để biết tenant, unit, vendor cụ thể, và **transaction audit** để biết ai tạo giao dịch.

### 12.2. Test boundary

- Cùng tenant, cùng unit và cùng vendor: phải áp dụng conflict theo rule.
- Khác tenant/unit: kết quả đúng theo policy scope, không mặc định deny hay permit.
- Thay resource classification, business unit hoặc owner giữa request và commit: cần reevaluation.
- Role hierarchy bổ sung permission xung đột qua role cấp cao: phải phát hiện.
- Role thiếu owner hoặc permission mapping: không nên mặc định “không conflict”.
- ABAC attribute stale (ví dụ department cũ sau Mover): không cho phép bypass chỉ vì group mới chưa đồng bộ.

### 12.3. Thuộc tính do client gửi

Kịch bản an toàn và cần thiết là kiểm tra **API không tin `departmentId`, `tenantId` hoặc `approverId` do client tự khai** nếu nguồn đó không có thẩm quyền. Thử với dữ liệu giả trong tenant kiểm thử: client sửa thuộc tính, PEP/PDP vẫn phải sử dụng **resource registry và identity source đáng tin**.

## 13. Kiểm thử qua nhiều đường truy cập: UI, API, connector và resource

Một hệ thống có thể có nhiều đường cấp hoặc sử dụng quyền:

~~~mermaid
flowchart TD
    A["Test principal / JML event"] --> UI["UI access request"]
    A --> API["Direct approval / entitlement API"]
    A --> TOKEN["SSO token / active session"]
    UI --> IGA["IGA policy + SoD decision"]
    API --> IGA
    IGA --> CON["Provisioning connector"]
    CON --> IDP["IdP / Directory group"]
    CON --> SCIM["SCIM / App-specific API"]
    IDP --> APP["Ứng dụng / local role"]
    SCIM --> APP
    TOKEN --> APP
    APP --> PEP["Transaction/API PEP"]
    PEP --> RESULT["PERMIT / DENY + audit"]
~~~

### 13.1. Test theo lớp

| Lớp | Kịch bản | Kiểm chứng |
| --- | --- | --- |
| **UI** | Nút self-approval bị ẩn/disabled. | Giao diện hướng dẫn đúng, nhưng chưa đủ security evidence. |
| **Approval API** | Trực tiếp gọi endpoint với actor không đủ authority. | API từ chối và không ghi quyết định hợp lệ. |
| **IGA/Policy engine** | Gán role xung đột SSD. | Conflict rule có hiệu lực theo role/permission/scope. |
| **Provisioning connector** | Request không có approval hợp lệ. | Connector từ chối hoặc không enqueue grant. |
| **Directory/SCIM** | Grant trực tiếp được thêm thủ công trong tenant thử nghiệm. | Reconciliation phát hiện quyền xung đột ở đích. |
| **App authorization** | Gọi transaction approve bằng actor đã tạo. | PEP từ chối, không commit giao dịch. |
| **SSO session** | Role đã thu hồi nhưng session cũ còn mở. | Thao tác bị từ chối hoặc giới hạn theo cơ chế thu hồi được phê duyệt. |

**Kiểm SoD chỉ ở UI không phải kiểm soát bảo mật**; tất cả đường API được hỗ trợ phải thực thi authorization server-side.

## 14. Kiểm thử quyền trực tiếp, quyền kế thừa và khả năng nâng quyền

### 14.1. Test dựa trên effective permission graph

Một user có thể nhận quyền từ:

- Role trực tiếp.
- Directory group, nested group hoặc dynamic group.
- Role hierarchy.
- App-local account/role.
- Resource policy, delegation hoặc cloud role assumption.
- PAM eligible access, JIT elevation.
- Khả năng đọc credential của principal mạnh hơn.

SoD engine phải có cách mô hình hóa hoặc đối soát **những đường có khả năng thực thi quyền xung đột** trong phạm vi được cam kết.

### 14.2. Kịch bản mẫu

| ID | Trạng thái | Expected |
| --- | --- | --- |
| GRAPH-01 | Permission A qua nested group, B trực tiếp. | Conflict được phát hiện khi policy cấm. |
| GRAPH-02 | Role admin kế thừa A, request B. | Conflict từ quyền kế thừa được phát hiện. |
| GRAPH-03 | App-local role B nằm ngoài IGA. | Reconciliation báo drift/xung đột. |
| GRAPH-04 | User có quyền tự gán B qua control-plane. | Được nhận diện là đường nâng quyền cần kiểm soát theo risk. |
| GRAPH-05 | JIT eligible B chưa active. | Đánh giá theo rule về eligibility và activation; không gộp mặc nhiên. |
| GRAPH-06 | User có quyền đọc secret của service principal sở hữu B. | Phân loại đường gián tiếp theo trust/control, yêu cầu review. |

### 14.3. Phân biệt khả năng tiềm tàng và quyền đã thực thi

Không phải mọi **đường nâng quyền tiềm năng** đều tương đương một assignment đang ACTIVE. Báo cáo kiểm thử nên tách:

1. **Direct assignment conflict**: role B đang được gán.
2. **Effective permission conflict**: có thể sử dụng hành động B qua đường hiện hành.
3. **Potential escalation path**: có quyền cấu hình/giả danh để đạt được B.
4. **Active transaction violation**: hành động xung đột đã được thực hiện.

Từng loại cần severity, bằng chứng và test khác nhau. Không tạo false positive bằng cách coi mọi giả thuyết leo thang là một vi phạm đã xảy ra; cũng không bỏ qua khả năng cấp tiếp quyền chỉ vì hiện tại chưa kích hoạt.

## 15. Kiểm thử delegation, maker-checker và sự độc lập

SoD có thể bị phá qua **ủy quyền approver** hoặc **workflow escalation**.

### 15.1. Những kịch bản phải có

1. Requester trùng beneficiary, approver là người khác có authority: xử lý theo policy; không tự cấm requester xin quyền cho mình.
2. Approver trùng beneficiary: **DENY** với rule cấm self-approval.
3. Approver trùng maker khi chính sách yêu cầu four-eyes: **DENY**.
4. Delegator hợp lệ nhưng delegate chính là beneficiary: **DENY**.
5. Delegation hết hạn hoặc vượt app/tenant scope: **DENY**.
6. Delegate xin duyệt tiếp (re-delegation) khi `canRedelegate=false`: **DENY**.
7. Approver chuyển vai trò/Leaver sau khi nhận ticket: decision phải **revalidate authority**.
8. Workflow hết SLA: không tự động **APPROVE** chỉ vì không ai phản hồi.
9. Two-step approval do cùng Person thực hiện qua hai accounts: không được tính là **hai người độc lập**.
10. Shared approver account không có bằng chứng named actor: đánh dấu **unverifiable** hoặc không chấp nhận theo policy nhạy cảm.

### 15.2. Bằng chứng độc lập

Nên lưu `makerSubjectId`, `beneficiarySubjectId`, `approverSubjectId`, `delegateSubjectId`, `approvalScope`, `policyVersion`, `decisionAt` và reference tới authentication/session context. Không lưu raw token hoặc credential.

### 15.3. Tách approval khỏi execution

Một connector có quyền cấp role có thể dùng OAuth token hợp lệ; điều đó **không đồng nghĩa connector có thẩm quyền tự viết approved=true**. Kiểm thử cần chứng minh executor:

- Chỉ nhận request/decision đã ký hoặc được xác minh qua kênh tin cậy.
- Ràng buộc đúng request ID/version, role, target, scope và expiry.
- Không tự cấp quyền khác ngoài nội dung được duyệt.
- Không có API ẩn bỏ qua approval/SoD trong cùng trust boundary.
- Có log và readback để đánh giá kết quả.

## 16. Kiểm thử race condition và Time-of-check–time-of-use (TOCTOU)

**TOCTOU** xảy ra khi hệ thống kiểm điều kiện SoD lúc `t1` nhưng quyền/thẩm quyền thay đổi trước khi lệnh được thực thi ở `t2`.

### 16.1. Hai yêu cầu hợp lệ riêng, xung đột khi kết hợp

~~~text
09:00  Subject P-100 chưa có role A hoặc B.
09:01  Request cấp role A: SoD precheck PASS.
09:01  Request cấp role B: SoD precheck PASS.
09:02  Cả hai được phê duyệt ở các workflow độc lập.
09:03  Hai connector GRANT chạy đồng thời.
09:04  P-100 sở hữu cả A và B, vi phạm SSD.
~~~

**Test concurrency** phải tái tạo tình huống có kiểm soát bằng fixture và barrier đồng bộ ở môi trường thử nghiệm; không chỉ chạy tuần tự các request.

### 16.2. Kỳ vọng

- **Không cho trạng thái cuối** chứa cả hai quyền xung đột ngoài ngoại lệ hợp lệ.
- Recheck entitlement/SoD **ngay trước grant**.
- Có **optimistic concurrency/version, transaction/locking hoặc serialized decision** tùy kiến trúc.
- Nếu không có giao dịch phân tán, cần **compensating action và reconciliation** theo độ trễ chấp nhận được.
- Cập nhật trạng thái FAIL/EXCEPTION nếu từng có cửa sổ xung đột, thay vì chỉ nhìn kết quả đã được sửa cuối cùng.

### 16.3. Các race khác

| ID | Race condition | Expected |
| --- | --- | --- |
| RACE-01 | Hai grant xung đột đến đồng thời. | Không có trạng thái cuối trái SSD; kiểm window và remediation. |
| RACE-02 | Role A được cấp trong lúc request B chờ phê duyệt. | B phải recheck trước execution. |
| RACE-03 | Role catalog thêm permission xung đột sau approval. | Revalidate role/policy version, cần reapproval khi phù hợp. |
| RACE-04 | Resource đổi tenant/owner trước commit. | PEP kiểm theo trạng thái đáng tin tại điểm thực thi. |
| RACE-05 | Reviewer mất authority trong lúc link còn sống. | Link cũ không tạo approved decision. |
| RACE-06 | Leaver đến sau khi request được duyệt nhưng trước grant. | Grant bị chặn theo lifecycle mới. |
| RACE-07 | Client retry cùng request nhiều lần. | Không tạo hai grant/decision độc lập. |

### 16.4. Độ trễ và tính eventual consistency

Một số SCIM/SaaS cập nhật không đồng bộ. Test không nên đặt giả định **mọi provider trả lời ngay lập tức**. Cần định nghĩa:

- Mốc `effectiveAt` từ nguồn có thẩm quyền.
- Thời gian kiểm chứng và **SLA theo rủi ro**.
- Kết quả `PENDING/UNKNOWN` trong lúc chờ replication.
- Biện pháp giảm thiểu khi quyền xung đột có thể sử dụng được.
- Điều kiện đóng test/incident chỉ sau khi trạng thái đích được xác minh.

**Timeout không phải bằng chứng test PASS hoặc FAIL về quyền thực tế**; đây là trạng thái chưa xác định cần readback/điều tra.

## 17. Kiểm thử SoD trong Joiner–Mover–Leaver

Vòng đời danh tính tạo ra nhiều tình huống SoD mà test tĩnh với một user `ACTIVE` sẽ không phát hiện.

### 17.1. Joiner – kiểm thử từ nguồn xác minh tới quyền ban đầu

Giả sử nhân viên bắt đầu làm việc vào ngày 01/12, account được tạo trước đó. Test cần kiểm:

| ID | Trạng thái | Hành động kiểm thử | Expected |
| --- | --- | --- | --- |
| **JML-01** | Account pre-provisioned, Start date chưa tới. | Thử request role đặc quyền. | Không tự kích hoạt role trước effectiveAt nếu policy không cho. |
| **JML-02** | Employee ACTIVE, birthright role đã được policy duyệt. | Provision role không xung đột. | Cho phép đúng scope, không cần phê duyệt sai quy tắc. |
| **JML-03** | Employee ACTIVE, role A xung đột với birthright role B. | Xin role A. | SSD phát hiện xung đột trước grant. |
| **JML-04** | Identity proofing/mapping không rõ Person. | Gán role nhạy cảm. | Không tự coi account là chủ thể hợp lệ; mở review. |
| **JML-05** | Contractor có end date và sponsor. | Xin role vượt hợp đồng. | DENY hoặc routing theo policy; không tự cấp vô thời hạn. |

**Điểm cần phân biệt:** account đã tồn tại không đồng nghĩa engagement đã đến lúc được hoạt động. SoD phải sử dụng **trạng thái có hiệu lực**, không chỉ cờ “user created”.

### 17.2. Mover – hai chiều cấp mới và thu hồi cũ

Một Mover có thể chuyển user từ nhiệm vụ `vendor-creator` sang `payment-approver`. Nếu IGA chỉ cấp role mới, người dùng có thể giữ đồng thời quyền xung đột.

| ID | Tiền điều kiện | Sự kiện | Expected |
| --- | --- | --- | --- |
| **JML-06** | Role A hiện có, role B xung đột. | Mover làm role B trở thành cần thiết. | Lập kế hoạch revoke A và chỉ cấp B theo trạng thái hợp lệ. |
| **JML-07** | Group A đã xóa ở IdP, app vẫn có local A. | Cấp B. | Không kết luận SSD PASS nếu A còn quyền hiệu lực. |
| **JML-08** | Manager chuyển M1 → M2. | M1 duyệt link cũ. | Revalidate, từ chối nếu M1 mất authority. |
| **JML-09** | Department chuyển SALES → FINANCE từ 08:00. | Request dùng claim SALES phát trước 08:00. | Dùng source/effective time đúng; không cấp quyền dựa dữ liệu stale trái policy. |
| **JML-10** | B đang chờ cấp, A được revoke nhưng timeout. | Job B tiếp tục. | Đọc lại A và kiểm ngưỡng rủi ro trước khi cho B. |

Khi hệ thống không bảo đảm **atomic revoke A + grant B**, test phải xác định **cửa sổ nguy cơ được phép hay không** và biện pháp giảm thiểu. Không được che giấu một thời điểm tồn tại cả hai quyền bằng cách chỉ đo trạng thái cuối cùng.

### 17.3. Leaver – không để request/worker cũ phục hồi quyền

| ID | Điều kiện | Hành động | Expected |
| --- | --- | --- | --- |
| **JML-11** | Person đã TERMINATED có hiệu lực. | Request grant role. | DENY/CANCEL theo policy. |
| **JML-12** | Request được duyệt trước Leaver, chưa provision. | Worker xử lý sau Leaver. | Recheck authoritative state, không cấp quyền. |
| **JML-13** | SCIM revoke timeout; grant retry cũ ở hàng đợi. | Retry grant. | Không tái cấp sau Leaver. |
| **JML-14** | IdP disabled, SaaS session cũ còn sống. | Thử thao tác thuộc phạm vi SoD qua app API. | Từ chối theo policy/kiểm soát thu hồi; nếu vẫn dùng được, ghi residual access. |
| **JML-15** | Approver đã Leaver. | Dùng delegated approval cũ. | Không được tạo quyết định hợp lệ. |

**Leaver không phải một chiến dịch review bình thường.** Quyền phải được thu hồi theo chính sách và thời điểm có hiệu lực; test không nên đợi chu kỳ access review rồi mới kiểm.

### 17.4. Rehire và chuyển loại quan hệ

Một Person quay lại có thể mang cùng tên/email, nhưng **engagement mới không tự thừa kế quyền hoặc approval cũ**. Test gồm:

- Quyền xung đột của engagement cũ không được tự bật lại khi account mới được liên kết.
- Grant path còn ở ứng dụng cũ phải được phát hiện trước khi cấp quyền mới.
- Role eligibility được tính theo hợp đồng/department hiện tại.
- Nếu account mapping giữa old/new engagement mơ hồ, không tự “PASS” self-approval chỉ vì IDs khác.

## 18. Kiểm thử tương tác IdP, SSO, SCIM và ứng dụng

SoD có thể được kiểm đúng trong IGA nhưng quyền thực tế không đúng do bất đồng bộ, local grants hoặc token.

### 18.1. Phân biệt từng lớp dữ liệu

~~~text
HRIS: người và trạng thái quan hệ
IGA: expected roles + SoD decisions + approvals
IdP/Directory: tài khoản, group membership và claims
SCIM/API: provisioning trạng thái User/Group/role theo provider
Ứng dụng: actual local grants, session và authorization
PAM/Cloud: active/eligible privileged roles, token/session
~~~

### 18.2. Các ca kiểm thử tích hợp

| ID | Kịch bản | Điều cần xác minh |
| --- | --- | --- |
| **INT-01** | IGA từ chối grant B theo SSD. | Không có SCIM/app API command hợp lệ cho B. |
| **INT-02** | Group bị xóa qua SCIM. | Readback membership và app role; không chỉ dựa HTTP status. |
| **INT-03** | App có direct grant B ngoài SCIM. | Inventory/reconciliation phát hiện effective conflict. |
| **INT-04** | SSO group claim vẫn cũ sau Mover. | API authorization không tiếp tục cho thực hiện giao dịch bị cấm theo chính sách thu hồi. |
| **INT-05** | App có nested group mapping khác IdP. | Permission ở app đúng policy, không bỏ sót tầng kế thừa. |
| **INT-06** | Connector nhận 401/403. | Không dùng đường admin bypass SoD để “sửa lỗi”. |
| **INT-07** | SCIM trả 409/412. | Không ghi đè bừa; đọc version, tính lại delta và kiểm SoD. |
| **INT-08** | SCIM trả 429/503. | Retry/backoff an toàn, không mở quyền trái policy. |
| **INT-09** | SCIM PATCH thành công nhưng app session chưa thay. | Test result **chưa VERIFIED** cho đường quyền còn sống. |
| **INT-10** | Một SaaS không hỗ trợ SCIM roles. | Kiểm mapping với API/role model riêng, không giả định đồng bộ được. |

### 18.3. Hạn chế của SCIM roles và groups

SCIM 2.0 chuẩn hóa các mô hình User/Group và cách thao tác trên chúng, nhưng **không chuẩn hóa toàn bộ authorization semantics của mọi SaaS**. Thuộc tính `roles` có thể có ở một số schema, song khả năng ghi/ánh xạ sang permission ứng dụng tùy provider. Test phải dựa **hợp đồng tích hợp thực tế**, không gửi một request giả định rồi coi thành công nếu chỉ thấy User tồn tại.

### 18.4. OAuth/OIDC/SAML trong thử nghiệm

Kiểm server-side:

- Token/assertion từ issuer đáng tin, đúng audience và thời hạn.
- OIDC subject được định danh bằng **issuer + subject**, không chỉ email.
- ID token không được dùng sai như access token của API.
- Group/role claim là snapshot có thể stale; SoD cần policy thích hợp tại resource.
- Khi token/session hết hạn hoặc role bị thu hồi, quyền thực tế ở API phải phù hợp cơ chế revalidation mà hệ thống công bố.

Không dùng raw token thật làm evidence công khai của testcase; lưu trace/metadata an toàn.

## 19. Kiểm thử PAM, JIT và break-glass

**Privileged Access Management (PAM)** và **Just-in-Time (JIT)** giúp giới hạn quyền mạnh nhưng cũng mở thêm bước phê duyệt/kích hoạt cần kiểm SoD.

### 19.1. Kịch bản JIT eligibility và activation

| ID | Tình huống | Expected |
| --- | --- | --- |
| **PAM-01** | Beneficiary tự phê duyệt yêu cầu JIT admin. | DENY nếu policy yêu cầu approver độc lập. |
| **PAM-02** | Người dùng chỉ có eligible role, chưa được active. | Đánh giá theo rule eligibility, không nhầm là active session. |
| **PAM-03** | Activation yêu cầu MFA/step-up. | Không kích hoạt khi bằng chứng không đạt. |
| **PAM-04** | Scope/time được duyệt là 30 phút ở project-A. | Không có quyền toàn tenant hoặc ngoài thời gian cho phép. |
| **PAM-05** | Person Mover làm mất eligibility trong lúc request chờ. | Revalidate trước elevation. |
| **PAM-06** | Leaver xảy ra khi privileged session đang mở. | Thu hồi hoặc chặn session/access theo khả năng được thiết kế; ghi ngoại lệ nếu chưa xác minh. |
| **PAM-07** | PAM vault credential có thể được xem bởi beneficiary. | Xem xét khả năng giả danh và conflict dù role trực tiếp không có. |
| **PAM-08** | Activation hết hạn nhưng token API còn quyền. | Kiểm cửa sổ effective access, không chỉ kết thúc session UI. |

### 19.2. Break-glass là bài test riêng

Tài khoản khẩn cấp có thể cần hoạt động khi một thành phần xác thực chính bị lỗi; kiểm thử không nên **phá hoại production** để chứng minh kịch bản. Trong môi trường an toàn và có quyền:

1. Kiểm owner, mục đích, phạm vi và phương thức bảo quản.
2. Xác định tình huống được phép bypass luồng approval thường.
3. Xác minh sử dụng tạo **alert, named accountability hoặc session trace** theo thiết kế.
4. Kiểm hậu kiểm độc lập, thời hạn, rotation và revoke sau sử dụng.
5. Xác minh đường emergency không được dùng như shortcut để tự duyệt quyền hằng ngày.

Nếu hệ thống cho phép emergency exception theo SoD, expected outcome phải bao gồm **exception record và kiểm soát bù**, không đơn giản là `PERMIT`.

## 20. Kiểm thử SoD cho service account và workload

Một service principal có thể đồng thời gọi API tạo request, sửa trường approved và provision quyền. Nếu một credential được dùng cho tất cả, phân tách service trên sơ đồ **không mang lại SoD thực chất**.

### 20.1. Các trust boundary cần kiểm

| Thành phần | Chức năng hợp lệ | Hành động phải chặn nếu chưa được phép |
| --- | --- | --- |
| **Request API service** | Tạo request có actor và beneficiary đáng tin. | Tự ghi decision APPROVED. |
| **Approval service** | Kiểm reviewer authority/SoD và ghi decision. | Tự cấp role tại đích ngoài scope chức năng. |
| **Provisioner/SCIM connector** | Thực thi action đã được phê duyệt. | Tự tạo approval hoặc đổi target/role. |
| **Reconciliation service** | Đọc entitlement và báo drift. | Tự sửa policy để che drift. |
| **Audit service** | Lưu trace, quyết định và outcome. | Cho connector sửa/xóa audit. |

### 20.2. Kịch bản non-human

- **NHI-01:** Credential request service gọi approval API: bị từ chối.
- **NHI-02:** Connector cố provision một role khác role trong quyết định: bị từ chối hoặc chặn bởi kiểm scope.
- **NHI-03:** Approval hợp lệ cho tenant-a được dùng để provision tenant-b: bị từ chối.
- **NHI-04:** Replay request approval hết hạn để cấp role: bị từ chối.
- **NHI-05:** Workload đổi owner từ kỹ sư đã Leaver: cần owner hiện hành và quyền được rà soát lại.
- **NHI-06:** Một service principal có thể đọc secret của executor mạnh hơn: ghi đường nâng đặc quyền và đánh giá policy.
- **NHI-07:** Principal không có owner hợp lệ: không tự kết luận PASS chỉ vì job chạy bình thường.

### 20.3. OAuth client credentials và quyền máy

Token dạng app-only có thể mang quyền dành cho ứng dụng thay vì người dùng. Đừng giả định SoD theo **Person** tự áp dụng cho workload; cần rule riêng theo **workload identity, ownerTeam, service trust và approval chain**. Test phải kiểm đúng subject model của API, tránh lấy claim từ ID token người dùng để chứng thực workload.

## 21. Kiểm thử exception và compensating controls

Một policy SoD có thể cho phép ngoại lệ rất hẹp, được **risk owner độc lập** phê duyệt, có thời hạn và kiểm soát bổ sung.

### 21.1. Case matrix

| ID | Ngoại lệ | Expected |
| --- | --- | --- |
| **EXC-01** | Không có exception, role xung đột. | DENY. |
| **EXC-02** | Exception có owner nhưng chưa approved. | DENY hoặc PENDING, chưa GRANT. |
| **EXC-03** | Exception đã duyệt bởi beneficiary. | DENY do self-acceptance khi policy cấm. |
| **EXC-04** | Exception đúng scope và còn hiệu lực. | Có thể cho theo policy, lưu justification và controls. |
| **EXC-05** | Exception đúng role nhưng sai tenant. | DENY ngoài scope. |
| **EXC-06** | Exception đã expired. | Không cho kích hoạt/giữ quyền ngoài quy định; revoke/alert. |
| **EXC-07** | Compensating monitoring chưa bật. | Không coi điều kiện ngoại lệ đã đáp ứng. |
| **EXC-08** | Exception bị thu hồi khi có incident. | Dừng quyền ngoại lệ và xác minh. |

### 21.2. Phân biệt test kết quả và test điều kiện ngoại lệ

Một test `EXCEPTION_PERMITTED` không đạt nếu role được cấp nhưng **cảnh báo sử dụng hoặc hậu kiểm bắt buộc không hoạt động**. Với ngoại lệ có kiểm soát, điều kiện **approval, scope, time và monitoring** đều là phần của expected result.

## 22. Thiết kế negative, positive và boundary tests

Để tránh **false assurance** (tự tin sai), mỗi kiểm soát cần nhiều loại thử nghiệm.

| Loại test | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Positive** | Nhu cầu hợp lệ vẫn chạy. | Checker độc lập và đủ authority duyệt TX-1. |
| **Negative** | Xung đột bị chặn. | Maker tự duyệt TX-1. |
| **Boundary** | Phạm vi/thời gian đúng biên. | Request ngay trước/sau expiresAt; khác tenant. |
| **Tamper/validation** | Input chưa đáng tin không thay kết quả. | Client sửa approverId hoặc role scope trong request. |
| **Race/concurrency** | Trạng thái thay đổi giữa check và use. | Hai GRANT role xung đột song song. |
| **Regression** | Thay đổi role/policy không phá kiểm soát cũ. | Role hierarchy được bổ sung permission B. |
| **Reconciliation** | Drift ngoài workflow được phát hiện. | Local app admin được gán trực tiếp trong test tenant. |
| **Failure injection** | Hệ thống xử lý nguồn lỗi an toàn. | IdP/SCIM timeout hoặc PIP trả attribute stale. |
| **Recovery/cleanup** | Sau lỗi không còn quyền test thừa. | Thu hồi fixture admin và session đúng hạn. |

### 22.1. Fuzz/property-based testing: dùng để bổ sung, không thay policy

Với permission graph lớn, có thể sinh nhiều tổ hợp role/scope/time để kiểm bất biến:

~~~text
PROPERTY: Với mọi subject không có exception hợp lệ,
không tồn tại cặp effective permissions A,B mà
conflict(A,B,subject,resource,context) == true
và cả A,B được phép đồng thời trái policy.
~~~

Tính đúng của property phụ thuộc vào **mô hình quyền và rule**. Dữ liệu sinh tự động phải có **oracle** độc lập đủ tin cậy; nếu dùng chính engine làm kết quả mong đợi, có thể chỉ kiểm hai lần cùng một lỗi.

### 22.2. Mutation testing cho rule SoD

Có thể tạo biến thể policy **cố tình lỗi trong môi trường thử nghiệm**:

- Bỏ điều kiện canonical Person.
- Bỏ scope businessUnit.
- Bỏ ràng buộc thời gian.
- Bỏ kiểm role inheritance.
- Cho phép self-approval.
- Cho connector tự chấp nhận decision chưa ký.

Một bộ test tốt phải phát hiện những thay đổi đó. **Không bao giờ áp dụng mutation trái phép lên policy production**; chỉ dùng fixture/policy clone an toàn.

## 23. Tự động hóa kiểm thử SoD qua các lớp

Một chiến lược thường tách:

1. **Unit:** kiểm conflict evaluator và policy predicates.
2. **Contract:** kiểm mapping User/Group/Role/permission giữa IGA và connector.
3. **Integration:** quyết định và readback ở IdP/SCIM/PAM/ứng dụng thử nghiệm.
4. **End-to-end:** người tạo request → reviewer → provisioner → API/transaction PEP.
5. **Continuous control validation:** phát hiện drift trong quyền thực tế bằng phương pháp giám sát an toàn.

### 23.1. Pseudocode test runner

~~~text
runSodScenario(scenario):
    ensureAuthorizedTestEnvironment(scenario)
    fixture = provisionIsolatedFixture(scenario)
    try:
        assertFixtureMatchesPreconditions(fixture)
        before = readTrustedTargetAndPolicyState(fixture)

        response = invokeWorkflowOrBusinessAction(scenario)
        decision = readDecisionWithActorRuleAndVersion(response)
        actual = readEffectiveEntitlementsAndTransactionState(fixture)

        assertDecisionMatchesOracle(decision, scenario.expectedDecision)
        assertNoUnauthorizedGrantOrCommit(actual, scenario)
        assertExpectedAuditTrailExists(response.traceId, scenario)

        if scenario.requiresSessionVerification:
            assertAuthorizedAccessResultMatchesPolicy(fixture, scenario)

        emitTestEvidence(
            scenario.id, scenario.policyVersion,
            before, decision, actual, response.traceId
        )
    finally:
        revokeFixtureGrantsSessionsAndCredentials(fixture)
        verifyCleanupAndReportAnyResidualAccess(fixture)
~~~

Đây là **giả mã**, không phải tập lệnh triển khai. Khi chạy thực tế, phải có **permission scope của môi trường thử nghiệm**, test data cô lập, rate limit, idempotency và cleanup. Việc gọi API ở cuối chỉ được dùng trong phạm vi kiểm thử có thẩm quyền.

### 23.2. Ví dụ kiểm quy tắc trong unit test

~~~text
canAssign(subject, requestedPermission, requestedScope):
    roles = loadEffectivePermissionGraph(subject)
    conflicts = findApplicableConflicts(
        roles, requestedPermission, requestedScope,
        sourceAttributesAtEvaluationTime()
    )
    if conflicts is not empty:
        return DENY
    if not eligibilityAndApprovalValid(subject, requestedPermission):
        return DENY
    return PERMIT

TEST "deny same-unit conflict":
    existingPermissions = [vendor.create in unit-a]
    requestedPermission = payment.approve in unit-a
    expected = DENY

TEST "permit unrelated permission":
    existingPermissions = [vendor.create in unit-a]
    requestedPermission = report.read in unit-a
    expected = PERMIT if otherwise eligible
~~~

Không nên tin một mock `loadEffectivePermissionGraph` luôn trả đầy đủ. Cần **integration tests** chứng minh role hierarchy, nested group và direct app grants thực sự được thu thập đúng.

## 24. Kiểm thử lỗi nguồn dữ liệu, outage và fail-safe

Độ tin cậy SoD phụ thuộc **nguồn Person/Engagement, role catalog, assignment inventory, resource owner, transaction history và reviewer authority**.

### 24.1. Những failure modes cần thử

| ID | Lỗi mô phỏng | Kỳ vọng an toàn |
| --- | --- | --- |
| **ERR-01** | HRIS không truy vấn được lifecycle. | Không tự coi subject ACTIVE cho grant nhạy cảm; xử lý theo policy. |
| **ERR-02** | Identity correlation trả hai Person candidates. | Không cho self-approval qua mapping mơ hồ. |
| **ERR-03** | PIP trả department stale trước Mover. | Không dùng dữ liệu quá hạn nếu policy yêu cầu fresh. |
| **ERR-04** | Role catalog không có permission mapping. | Không kết luận SSD PASS chỉ vì không tìm thấy conflict. |
| **ERR-05** | Inventory SaaS bị thiếu một trang phân trang. | Báo incomplete inventory, không công bố “0 conflict”. |
| **ERR-06** | Transaction history service timeout. | Không chấp thuận giao dịch nhạy cảm khi thiếu dữ liệu bắt buộc. |
| **ERR-07** | Reviewer authority registry lỗi. | Không tự coi requester là reviewer mặc định. |
| **ERR-08** | SCIM server trả 503. | Retry/exception có kiểm soát; không tự vượt approval. |
| **ERR-09** | Audit sink tạm thời không khả dụng. | Hành vi theo chính sách nhạy cảm: chặn, queue an toàn hoặc bù evidence. |
| **ERR-10** | Đồng hồ service bị lệch. | Kiểm expiry/effectiveAt và source clock đáng tin. |

### 24.2. Các trạng thái kết quả

Nên phân biệt:

~~~text
PASS               Test có bằng chứng expected và actual khớp.
FAIL               Có bằng chứng vi phạm expected.
BLOCKED            Không tạo được tiền điều kiện hoặc thiếu quyền test.
INDETERMINATE      Không thể xác định actual trong phạm vi/hạn định.
NOT_RUN            Chưa thực hiện.
NOT_APPLICABLE     Không áp dụng theo scope được phê duyệt.
~~~

**Không được tính BLOCKED/INDETERMINATE thành PASS** để làm đẹp tỷ lệ. Nếu một nguồn dữ liệu quan trọng lỗi, test nên mở việc điều tra và đánh giá quyền có thể đã bị ảnh hưởng.

## 25. Chứng cứ kiểm thử: từ test input tới quyền thực tế

Kiểm thử SoD có thể được dùng cho **regression, kiểm soát vận hành hoặc audit**. Do vậy, kết quả cần đủ để người khác hiểu **kiểm điều gì, theo policy nào, thực hiện ở đâu và đã quan sát thấy gì**.

### 25.1. Evidence package cho một testcase

| Trường | Mục đích |
| --- | --- |
| **testRunId, testCaseId** | Phân biệt lượt và kịch bản. |
| **requirementId / conflictId** | Truy vết tới SoD rule đã duyệt. |
| **policyVersion / roleCatalogVersion** | Biết permission và điều kiện đã được kiểm theo phiên bản nào. |
| **environment / tenant / target** | Xác định hệ thống và phạm vi thử nghiệm. |
| **fixture subject/account mapping** | Chứng minh actor, beneficiary, reviewer có trùng Person hay không. |
| **precondition evidence** | Quyền thực tế trước khi test. |
| **action/request reference** | API/workflow/transaction nào đã được gọi. |
| **expected outcome** | DENY, PERMIT, NEED_APPROVAL, không cấp role hoặc không commit. |
| **actual outcome** | Quyết định và tình trạng sau thử nghiệm. |
| **target readback / enforcement result** | Quyền, session hoặc transaction ở đích sau thao tác. |
| **source timestamps/version** | Thời điểm và tính mới của HRIS/IGA/SCIM/app dữ liệu. |
| **audit traceId / eventId** | Liên kết giữa request, policy decision, connector và resource. |
| **cleanup result** | Đã dọn role, token, session/fixture chưa. |
| **status, defectId, owner** | PASS, FAIL, BLOCKED, INDETERMINATE và việc tiếp theo. |

### 25.2. Log mẫu không chứa secret

~~~json
{
  "testRunId": "sod-regression-20261201-01",
  "testCaseId": "WF-02",
  "conflictRuleId": "SOD-SELF-APPROVAL-001",
  "policyVersion": "sod-policy-v5",
  "environment": "staging",
  "tenantId": "tenant-test-a",
  "makerSubjectId": "test-person-maker",
  "beneficiarySubjectId": "test-person-maker",
  "approverAccountId": "maker-admin",
  "approverCanonicalSubjectId": "test-person-maker",
  "requestVersion": 3,
  "expectedDecision": "DENY",
  "actualDecision": "DENY",
  "targetRoleGranted": false,
  "traceId": "trace-sod-wf02-001",
  "targetReadback": "NO_UNAUTHORIZED_GRANT",
  "cleanupVerified": true,
  "result": "PASS"
}
~~~

Dữ liệu chỉ là **ví dụ minh họa**; không phải định dạng chuẩn của IAM, IdP hoặc SCIM. `cleanupVerified=true` chỉ có ý nghĩa khi được suy ra từ **bằng chứng readback**, không phải do script đặt cờ mặc định.

### 25.3. Bảo vệ evidence

**Không ghi raw password, API key, access/refresh token, cookie, private key, OTP, hồ sơ HR nhạy cảm hoặc bản sao dữ liệu tài chính** vào report/test log. Dùng reference IDs, metadata được che dữ liệu, redaction, quyền xem hạn chế và thời gian lưu theo policy.

Với test trên production được ủy quyền, cân nhắc tác động từ **đọc quyền, truy vấn log, tài khoản thử nghiệm và cảnh báo** để không gây gián đoạn hoặc tiết lộ dữ liệu người dùng thật.

## 26. Case study 1: kiểm thử SSD phát hiện role qua nested group

**Bối cảnh giả định:** một công ty có rule `SOD-PAY-001` cấm cùng Person giữ `vendor.create` và `payment.approve` trong cùng business unit. Tổ chức đã triển khai IGA approval và kiểm SSD trước cấp.

### 26.1. Trạng thái fixture

~~~text
Person: P-1042, ACTIVE, businessUnit=A

Directory:
    group-support
        └── group-vendor-operators
              └── permission vendor.create (unit=A)

IGA:
    directRoles(P-1042) = [report-reader]

Yêu cầu:
    role payment-approver, unit=A
~~~

Nếu SoD engine chỉ đọc directRoles trong IGA, nó **không thấy vendor.create qua nested group** và có thể chấp nhận grant sai.

### 26.2. Bộ test cần chạy

| Test | Hành động | Expected |
| --- | --- | --- |
| **A1** | P-1042 xin payment.approve cùng unit A. | DENY khi effective graph có vendor.create. |
| **A2** | P-1042 xin report.read ngoài conflict. | PERMIT nếu đủ điều kiện. |
| **A3** | Gỡ membership gián tiếp vendor.create và xác minh. | Chỉ sau khi quyền cũ hết hiệu lực, request mới có thể hợp lệ. |
| **A4** | P-1042 tự thay account IdP khác rồi xin payment.approve. | Vẫn DENY nếu cùng canonical Person và quyền cũ còn. |
| **A5** | Cấp direct local vendor.create ở SaaS thử nghiệm. | Reconciliation phát hiện conflict dù IGA chưa có record. |

### 26.3. Kết quả giả định ban đầu

Test **A1 FAIL**: IGA trả APPROVED; application có cả hai permission. Truy vết cho thấy connector tổng hợp permission bỏ qua nested groups.

**Phân loại:** defect trong **effective-entitlement aggregation/SSD enforcement**, không phải chỉ lỗi hiển thị. Ưu tiên xử lý theo rủi ro và điều tra các subject đang giữ tổ hợp tương tự.

### 26.4. Khắc phục và retest

1. Sửa đường giải group inheritance hoặc nguồn inventory được chỉ định.
2. Bổ sung contract/integration test cho nested membership.
3. Recalculate các assignment đang có, mở exception/thu hồi quyền xung đột theo policy.
4. Re-run A1–A5 với dataset mới.
5. Đọc lại ứng dụng, xác minh **không thể sử dụng hai quyền** trong phạm vi đã kiểm.
6. Lưu test run cũ **FAIL** và run sau **PASS**; không xóa dấu vết lỗi trước sửa.

## 27. Case study 2: DSD bị vượt qua qua API duyệt giao dịch

**Bối cảnh giả định:** ứng dụng kế toán cho phép tạo payment tại UI, và API riêng duyệt payment. UI ẩn nút Approve nếu người xem là người tạo; API lại chỉ kiểm `payment.approve` mà không kiểm lịch sử creator.

### 27.1. Kịch bản

1. Dùng Person P-100 tạo payment `TX-001` ở tenant thử nghiệm.
2. Đăng nhập cùng Person qua một privileged account riêng được cấp role approver theo fixture DSD.
3. Gọi approval API với TX-001 bằng phương pháp được ủy quyền.
4. Kiểm response, transaction status, actor history và audit.
5. Cleanup payment test và session.

### 27.2. Kỳ vọng và quan sát

| Lớp | Expected | Lỗi thường gặp |
| --- | --- | --- |
| **UI** | Không cho maker tự approve cùng TX. | Nút bị ẩn đúng nhưng API không kiểm. |
| **API PEP** | DENY nếu canonical Person của maker = approver. | Kiểm accountId, không kiểm Person. |
| **Transaction service** | TX vẫn PENDING và chưa được commit. | API trả lỗi nhưng đã commit trước khi rollback. |
| **Audit** | Ghi actor thật, TX ID, conflictId, policy version. | Chỉ ghi tên account, không liên kết Person. |
| **Positive control** | P-200 đủ authority được phép approve TX. | Engine deny-all hoặc kiểm sai tenant. |

### 27.3. Bài học

**DSD là kiểm soát ở thời điểm sử dụng**, không thể chứng minh bằng việc IGA từ chối một số role. API và transaction boundary phải đối chiếu đúng **người tạo, người duyệt, transaction ID, tenant và lịch sử trạng thái**.

## 28. Case study 3: Mover, concurrency và grant đến muộn

**Bối cảnh giả định:** An đang giữ `vendor-creator` tại unit A. HRIS gửi Mover để An trở thành `payment-approver` từ 08:00. Lệnh thu hồi vendor role tới SaaS bị timeout; đồng thời manager duyệt role mới.

| Thời điểm giả định | Sự kiện | Tình huống test |
| --- | --- | --- |
| **07:55** | HRIS công bố Mover, effectiveAt 08:00. | Kiểm event có source version và đúng Person. |
| **08:00** | IGA tính expected: revoke A, grant B. | Kiểm SSD không để tồn tại đồng thời A+B trái policy. |
| **08:01** | SCIM remove group vendor timeout. | Không coi revoke verified. |
| **08:02** | B được duyệt bởi reviewer hợp lệ. | Approval đúng chưa đủ để provision. |
| **08:03** | Worker chuẩn bị cấp payment-approver. | Recheck A ở ứng dụng trước grant. |
| **08:04** | App-local vendor grant vẫn ACTIVE. | Phải chặn/hoãn grant hoặc giảm rủi ro theo policy. |
| **08:06** | Reconciliation giải quyết quyền A tồn dư. | Đọc lại mọi grant path A. |
| **08:07** | Grant B được thực hiện khi eligibility/SoD hợp lệ. | Kiểm B active, A không còn effective, audit đầy đủ. |

### 28.1. Biến thể Leaver

Sau khi request B được duyệt, HRIS có thể gửi Leaver hiệu lực trước lúc worker chạy. Test `JML-12` cần xác minh **job không dựa duy nhất vào flag approved đã lưu**, mà kiểm lại **current authoritative lifecycle state**. Kết quả cần là **grant bị hủy**, không chỉ “được cấp rồi xóa sau”.

### 28.2. Bài học về eventual consistency

Không phải mọi provider hỗ trợ cập nhật nhiều role nguyên tử. Do vậy test cần theo dõi:

- Thời điểm cửa sổ xung đột bắt đầu/kết thúc.
- Quyền có được sử dụng trong cửa sổ đó không (nếu có bằng chứng).
- Biện pháp hạn chế tạm theo mức rủi ro.
- Độ trễ cho tới khi `REVOKED_VERIFIED`.
- Kết quả test và defect/exception, không che window bằng trạng thái cuối.

## 29. Báo cáo test run: mẫu kết quả có thể bàn giao

Một báo cáo kiểm thử SoD cần trình bày **coverage và các lỗ hổng được phát hiện**, thay vì chỉ tổng số PASS.

### 29.1. Dataset kiểm thử giả định

| Nhóm test | Planned | Executed | PASS | FAIL | BLOCKED/INDETERMINATE |
| --- | ---: | ---: | ---: | ---: | ---: |
| SSD/direct/inheritance | 20 | 20 | 18 | 2 | 0 |
| DSD/transaction | 15 | 15 | 14 | 1 | 0 |
| Approval/self-review | 20 | 19 | 17 | 1 | 1 |
| JML/temporal/concurrency | 15 | 14 | 12 | 1 | 1 |
| IdP/SCIM/PAM integration | 20 | 18 | 14 | 2 | 2 |
| Workload/exception | 10 | 10 | 9 | 1 | 0 |
| **Tổng** | **100** | **96** | **84** | **8** | **4** |

**Số liệu hoàn toàn giả định.** `Executed` ở ví dụ bao gồm những case đã được thử nhưng bị BLOCKED/INDETERMINATE; mỗi đội cần tài liệu hóa định nghĩa này. 4 case chưa thực hiện cộng 4 case blocked/indeterminate không được xem là PASS.

### 29.2. Các chỉ số từ dataset

~~~text
Execution coverage = 96 / 100 = 96%

PASS rate trên planned = 84 / 100 = 84%

PASS rate trên executed = 84 / 96 = 87,50%

FAIL trên executed = 8 / 96 ≈ 8,33%

Blocked/Indeterminate trên executed = 4 / 96 ≈ 4,17%

Chưa thực hiện = 100 - 96 = 4
~~~

**Kết luận không đúng:** “SoD đạt 96% vì đã chạy 96 test”.

**Kết luận đúng:** “Đã thực hiện 96/100 case; 84 PASS, 8 FAIL, 4 BLOCKED/INDETERMINATE và 4 chưa chạy. Cần đánh giá severity của 8 lỗi, đặc biệt mọi đường privilege/transaction bypass, và xử lý khoảng trống coverage trước khi kết luận kiểm soát đạt yêu cầu.”

### 29.3. Trạng thái theo risk tier

Một fail có thể cho phép tự duyệt quyền quản trị identity trong khi 20 pass là UI validation thông thường. Vì vậy, **điểm trung bình không thể thay thế release gate theo criticality**. Báo cáo nên thể hiện:

~~~text
Critical rule defects:       <số đã xác minh>
Critical coverage gaps:      <số chưa kiểm/không thể kiểm>
High-risk residual grants:   <số đã xác minh>
Open exceptions with owner:  <số và hạn xử lý>
Effective-access verified:   <tỷ lệ theo scope đã định>
~~~

Trong báo cáo thật, những trường chưa có dữ liệu phải ghi **UNKNOWN/NOT_REPORTED**, không tự gán giá trị bằng 0.

## 30. Tích hợp SoD tests vào CI/CD và change management

SoD có thể hỏng khi đổi **role catalog, permission mapping, IdP group, SCIM connector, API authorization, approval routing hoặc HRIS attribute mapping**.

### 30.1. Quality gates theo mức thay đổi

| Thay đổi | Test nên chạy trước triển khai |
| --- | --- |
| **Role mới / quyền mới** | SSD role combinations, hierarchy, permission impact. |
| **Role thêm permission** | Re-evaluate xung đột cho mọi principal đang có role. |
| **Approval policy thay đổi** | Self-approval, owner authority, delegation và expiry. |
| **Directory/IdP group mapping** | Nested/dynamic group, effective entitlements và revoke. |
| **SCIM connector upgrade** | Contract/API readback, conflict error, retry/ETag. |
| **PAM/JIT policy change** | Eligibility, approval, activation, time limit, session revocation. |
| **Business workflow change** | DSD theo transaction và API resource PEP. |
| **HRIS mapping/JML event schema** | Mover/Leaver, manager change, effectiveAt và stale event. |

### 30.2. Gating cho lỗi nghiêm trọng

Một tổ chức có thể định nghĩa release gate:

1. Các negative tests của **critical SoD controls** phải PASS trong phạm vi đã định.
2. Không có defect mới cho phép **self-approval, impersonation hoặc unauthorized grant**.
3. Các test bị BLOCKED ở lớp trọng yếu cần có owner và biện pháp thay thế; không tự coi đã đạt.
4. Thay role permission phải chạy **impact analysis** trên existing assignments.
5. Những ngoại lệ được chấp nhận có **risk owner, expiry và compensating controls**.
6. Test cleanup và quyền sau triển khai phải được xác minh.

Các điều kiện này là **khuyến nghị thiết kế gate**, không phải tiêu chuẩn buộc mọi dự án áp dụng cùng ngưỡng. Ngưỡng và authority cần do quản trị rủi ro quyết định.

### 30.3. Production control validation không đồng nghĩa pentest

Có thể đối soát quyền bằng **API inventory read-only, audit logs, entitlement graph và policy evaluation**; những thử nghiệm thao tác nhạy cảm/đường bypass phải được **cấp phép rõ, cô lập và hạn chế tác động**. Không thực hiện giao dịch tài chính thật, xóa dữ liệu hoặc thay IAM policy production chỉ để lấy test evidence.

## 31. Triage khi testcase FAIL

### 31.1. Tìm lớp sai trước khi sửa

| Dấu hiệu | Nguyên nhân khả dĩ | Điều cần kiểm |
| --- | --- | --- |
| IGA trả APPROVE cho hai role xung đột. | Conflict rule thiếu hoặc role mapping sai. | Rule version, effective permissions, owner. |
| UI DENY nhưng API cho phép. | Authorization chỉ ở frontend. | Server-side PEP và request validation. |
| IGA DENY nhưng role có ở SaaS. | Grant thủ công/local hoặc connector bypass. | Audit của app, direct role và grant paths. |
| Cùng người dùng hai account qua được self-approval. | Identity correlation theo account thay Person. | Person/Engagement mapping và federation namespace. |
| Chỉ lỗi khi chạy đồng thời. | TOCTOU, thiếu lock hoặc stale read. | Snapshot/version và thứ tự job. |
| Mover tạo conflict ngắn hạn. | Revoke thất bại và grant mới chạy trước. | EffectiveAt, queue ordering, target readback. |
| Leaver vẫn approve được. | Link/token cũ không revalidate authority. | Reviewer state và decision endpoint. |
| Test fail khi nguồn HRIS offline. | Policy dùng cache quá hạn hoặc fail-open. | Freshness/Indeterminate behavior. |
| JIT role hết hạn nhưng API vẫn cho action. | Session/token chưa bị invalidated hoặc resource không recheck. | PEP, session lifetime, PAM hooks. |
| Kết quả test lúc pass lúc fail. | Replication delay, nondeterministic fixture hoặc race. | Stable preconditions, wait conditions và audit timestamps. |

### 31.2. Không “sửa” lỗi bằng cách nới quyền

Khi nhận 403 hoặc conflict deny, không nên thử **thêm role admin, tắt SoD rule hoặc đổi approver sang một tài khoản tiện hơn** mà thiếu quy trình phê duyệt. Test trước hết phải chứng minh **kỳ vọng policy** và giải thích đúng nguyên nhân.

### 31.3. Defect report gợi ý

~~~text
Defect ID: SOD-DEF-042
Rule/Test: SOD-SSD-001 / SSD-04
Environment: staging / tenant-test-a
Severity: HIGH (được owner xác nhận)
Expected: DENY payment.approve khi vendor.create còn hiệu lực.
Actual: APPROVED và role B có tại app đích.
Precondition: vendor.create từ nested directory group.
Suspected layer: Effective entitlement collector không giải group nesting.
Evidence: trace IDs, policy version, role catalog, provider readback.
Impact: Có thể tồn tại cả hai quyền ở cùng business unit.
Owner: IAM Policy + Directory Integration
Mitigation: Chặn grant B khi graph không đủ, rà soát assignments đang có.
Retest: SSD-01/04/05/10 và test endpoint liên quan.
Status: OPEN
~~~

**Không đưa secret, token thật hoặc dữ liệu khách hàng** vào defect ticket. Nếu phát hiện qua production, theo dõi dưới quy trình incident phù hợp.

## 32. KPI kiểm thử SoD và chất lượng kiểm soát

| KPI | Cách đo | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **Requirement coverage** | Rule SoD có test hợp lệ ÷ toàn bộ rule trong scope. | Số test nhiều không chứng minh mọi rule được bao phủ. |
| **Grant-path coverage** | Các loại direct/group/hierarchy/local/PAM đã được test ÷ loại thuộc phạm vi. | Không được bỏ qua đường cấp ngoài IGA. |
| **Negative-test pass rate** | Negative cases PASS ÷ negative cases đã xác định. | Một engine deny-all có thể PASS nếu thiếu positive tests. |
| **Positive-test pass rate** | Positive cases hợp lệ PASS ÷ positive cases đã xác định. | Cần bảo đảm nghiệp vụ không bị khóa sai. |
| **Execution coverage** | Cases executed ÷ planned. | Không coi executed là passed. |
| **Critical defect count** | Lỗi kiểm soát rủi ro nghiêm trọng chưa khắc phục. | Một critical fail có thể chặn release dù tỷ lệ PASS cao. |
| **Blocked/Indeterminate tests** | Case không thể kết luận hoặc không tạo được fixture. | Không gộp thành PASS. |
| **Effective-access verification rate** | Cases có bằng chứng actual ở đích ÷ cases cần verify. | HTTP success không thay thế resource verification. |
| **JML SoD regression coverage** | Kịch bản Joiner/Mover/Leaver được test ÷ scope chính sách. | Test static-only dễ bỏ qua event ordering. |
| **Mean/p95 resolution latency** | Từ finding tới verified fix, chia theo severity. | Nên báo số lượng/độ phủ và không dùng trung bình che outliers. |
| **SoD exception expiry compliance** | Exception được thu hồi/tái duyệt đúng hạn ÷ exception đến hạn. | Accepted không đồng nghĩa resolved. |
| **Post-change regression escape** | Vi phạm SoD phát hiện sau deploy mà test trước deploy bỏ sót. | Giúp cải tiến test design. |
| **Test cleanup completeness** | Fixture permissions/sessions đã xác minh thu hồi ÷ tất cả fixture tạo ra. | Tránh quyền test tồn dư. |

### 32.1. Một KPI tốt cần mẫu số, phạm vi và thời gian

Không nên báo “0 SoD violation” nếu chỉ kiểm 10 role ở IdP mà bỏ qua cloud, PAM hoặc application-local grants. Ghi:

- Những conflict rules/tenants/apps được kiểm.
- Source data freshness và các provider không quan sát được.
- Test đã chạy phiên bản policy nào.
- Đã kiểm **assignment**, **activation** hay **business transaction**.
- Có bao nhiêu case **BLOCKED/INDETERMINATE/NOT_RUN**.

## 33. Checklist thực hành kiểm thử SoD

### 33.1. Policy và mô hình quyền

1. Có **conflict rule ID, owner, business rationale, policy version và scope** cho từng rule không?
2. Có phân biệt **SSD, DSD và procedural/maker-checker SoD**, biết lớp nào thực thi mỗi rule không?
3. Các role/permission có mapping canonical và phiên bản catalog phù hợp không?
4. Có xét **role hierarchy, nested/dynamic groups, direct grants, delegation và đường nâng đặc quyền** không?
5. Có **test positive, negative, boundary** tương ứng cho mỗi rule trọng yếu không?
6. Có kiểm scope theo **tenant, unit, resource, transaction và effective time** thay vì so tên role đơn thuần không?

### 33.2. Danh tính, reviewer và workflow

7. Requester, beneficiary, approver, executor có được **resolve về canonical subject/Person** đúng namespace không?
8. Có test **một người nhiều tài khoản, email đổi/tái cấp và rehire** không?
9. Approval API có chống **self-approval, giả approverId, expired delegation, request version cũ** không?
10. Có test **reviewer mất authority** do thay manager/Mover/Leaver khi request đang chờ không?
11. Có test executor/service principal **không tự tạo approved decision** và chỉ được provision đúng role/scope không?
12. Có test escalation khi reviewer vắng mặt **không tự động chấp thuận** quyền nhạy cảm không?

### 33.3. Quyền thực tế và vòng đời

13. Test SSD có đọc **effective entitlements**, không chỉ direct assignments trong IGA không?
14. Test DSD có kiểm **transaction history/PEP**, không chỉ ẩn nút UI không?
15. Có test **API trực tiếp** và các đường provider ngoài UI/workflow không?
16. Có xác minh provider **IdP/SCIM/SaaS/Cloud/PAM** sau grant/revoke bằng readback không?
17. Có test **active session/token** sau thay role hoặc thu hồi không?
18. **Joiner** có kiểm Start date, birthright và role nhạy cảm không cấp sớm không?
19. **Mover** có test đồng thời **revoke old + grant new**, bao gồm conflict window không?
20. **Leaver** có test grant cũ không tái xuất hiện sau retry hoặc event đến muộn không?
21. Có test service account, workload, shared account, credential/vault và JIT eligibility không?

### 33.4. Độ bền và bằng chứng

22. Có kiểm **race/TOCTOU, hai grant đồng thời, policy đổi trong lúc duyệt** không?
23. Có test **timeout/409/412/429/5xx, stale PIP data, missing inventory và fail-safe behavior** không?
24. Exception có **owner độc lập, scope/time limit, compensating controls và expiry** được kiểm không?
25. Mỗi case có **precondition, action, expected, actual, verification và cleanup** không?
26. Có phân biệt kết quả **PASS, FAIL, BLOCKED, INDETERMINATE, NOT_RUN** không?
27. Evidence có truy vết từ **policy/identity → request → decision → connector → actual authorization** không?
28. Test logs và báo cáo có **ẩn raw secret, token, PII và dữ liệu giao dịch thực** không?
29. Các test accounts/roles/sessions có được **cleanup và readback** đúng sau mỗi run không?
30. Có **CI/CD gate và regression suite** khi role catalog, connector, approval routing hoặc JML schema đổi không?
31. Những critical defects, gaps và quyền chưa xác minh có **owner, severity, dueAt và risk mitigation** không?
32. Báo cáo coverage có nêu **giới hạn ứng dụng, provider, grant path và phiên bản policy** không?

## 34. Kết luận: SoD PASS chỉ có ý nghĩa khi hành động bị cấm thật sự không thực hiện được

Kiểm thử SoD đáng tin cần đi qua bốn điểm kiểm chứng:

~~~text
1. POLICY ĐÚNG
   conflict rule và phạm vi có owner, version, nghiệp vụ rõ
                   ↓
2. QUYẾT ĐỊNH ĐÚNG
   IGA/workflow/PDP không approve hoặc assign sai
                   ↓
3. THỰC THI ĐÚNG
   connector và API/transaction PEP không cho đi vòng policy
                   ↓
4. BẰNG CHỨNG THỰC TẾ
   effective entitlements, session, giao dịch và audit khớp expected
                   ↓
5. DRIFT & LIFECYCLE ĐƯỢC QUẢN LÝ
   Joiner–Mover–Leaver, retry, owner, exception, cleanup, regression
~~~

**Ghi nhớ:** **Kiểm thử SoD không chỉ là kiểm một cặp role hay xem nút Approve có bị khóa**. Cần biến rule thành **test case có oracle, phạm vi, tiền điều kiện, negative/positive path và bằng chứng**, rồi xác minh **SSD ở assignment, DSD tại session/giao dịch và procedural SoD trong workflow**. Phải kiểm **cùng Person qua nhiều tài khoản, quyền kế thừa/nested group, API bypass, delegation, race/TOCTOU, credential, JIT/PAM và các sự kiện Joiner–Mover–Leaver**. Kết quả **PASS** chỉ đáng tin trong phạm vi có bằng chứng quyền thực tế tại **IdP, SCIM, ứng dụng và resource PEP**; trường hợp FAIL, UNKNOWN hoặc chưa kiểm phải được báo trung thực, có owner và phương án khắc phục.
