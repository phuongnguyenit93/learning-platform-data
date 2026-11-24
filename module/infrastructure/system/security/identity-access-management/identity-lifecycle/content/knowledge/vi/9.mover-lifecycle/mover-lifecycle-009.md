# Lưu lịch sử thay đổi trong Mover lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao **lưu lịch sử thay đổi** (change history) là một kiểm soát thiết yếu trong **Mover lifecycle** của Identity and Access Management (IAM).
- Phân biệt **sự kiện nghiệp vụ**, **quyết định phân quyền**, **yêu cầu thực thi**, **thay đổi thực tế tại hệ thống đích** và **bằng chứng đối soát**; biết nên ghi gì cho từng lớp.
- Thiết kế bản ghi thay đổi có thể truy vết **ai, thay đổi gì, từ giá trị nào sang giá trị nào, vì sao, ai phê duyệt, khi nào có hiệu lực, hệ thống nào đã áp dụng và kết quả ra sao**.
- Xử lý sự kiện HRIS đến trễ, thay đổi lặp, sai thứ tự, thu hồi một phần, quyền cấp thủ công và tình huống cần khôi phục sau lỗi.
- Liên hệ lịch sử thay đổi với **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, audit và giảm quyền truy cập tồn dư**.
- Lựa chọn cách lưu trữ, bảo vệ tính toàn vẹn, giới hạn dữ liệu nhạy cảm, thời hạn lưu giữ và các chỉ số vận hành phù hợp.

## 1. Vì sao Mover cần lịch sử thay đổi?

**Mover** là giai đoạn một chủ thể đã có danh tính trong tổ chức **thay đổi vai trò, bộ phận, dự án, người quản lý, loại quan hệ làm việc, đơn vị pháp nhân, địa điểm hoặc phạm vi trách nhiệm**. Nhiều thay đổi không làm trạng thái việc làm rời khỏi **ACTIVE**, nhưng có thể khiến quyền truy cập cũ không còn hợp lệ và quyền mới cần được cấp.

Nếu hệ thống chỉ giữ **trạng thái hiện tại** — chẳng hạn nhân viên đang ở phòng Finance và có role FinanceReader — người vận hành thường không thể trả lời:

- Người đó từng thuộc bộ phận nào và đổi sang Finance lúc nào?
- Quyền Support đã bị yêu cầu thu hồi hay chưa? Hệ thống CRM đã áp dụng chưa?
- Ai đề xuất, ai phê duyệt và chính sách nào cho phép role FinanceReader?
- Có quyền tạm thời, quyền cấp trực tiếp hoặc phiên/token còn hiệu lực sau thay đổi không?
- Nếu một yêu cầu bị lỗi, cần tiếp tục bước nào mà không cấp trùng hoặc phục hồi quyền cũ?
- Khi kiểm toán, bằng chứng nào cho thấy **quyền thực tế** phù hợp với vai trò mới?

**Lưu lịch sử thay đổi** là việc ghi nhận có cấu trúc các biến động liên quan đến danh tính và truy cập, cùng nguồn gốc, ngữ cảnh, quyết định, thao tác thực thi và kết quả xác minh theo thời gian.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, lịch sử thay đổi giúp nối quá trình **Joiner–Mover–Leaver (JML)**: dữ liệu Joiner xác lập chủ thể và tài khoản ban đầu; Mover ghi lại những quyền được thêm, sửa hoặc gỡ; Leaver sử dụng danh mục tài khoản/quyền và dấu vết đó để thu hồi đủ, hạn chế **quyền truy cập tồn dư**.

**Nguyên tắc cốt lõi:** ghi được việc “đã gửi lệnh gỡ quyền” không đồng nghĩa chứng minh “quyền thực tế đã bị gỡ”. Một lịch sử hữu ích phải phân biệt **điều được yêu cầu**, **điều đã thực thi**, và **điều được xác minh**.

### 1.1. Ví dụ ngắn

Ngày 20/11, nhân viên An chuyển từ nhóm Support sang nhóm Finance. IAM nhận thay đổi department từ HRIS, cấp role FinanceReader nhưng cuộc gọi API gỡ nhóm CRM-Support gặp lỗi. Đến ngày 23/11, hệ thống cho thấy An có cả hai quyền.

Nếu chỉ lưu bản ghi cuối **department = Finance**, việc cấp/thu hồi thiếu rất khó tái hiện. Nếu lưu một chuỗi sự kiện có ID liên kết, người phụ trách có thể thấy **quyền cũ cần gỡ**, **thao tác thất bại**, **lần thử lại**, **bằng chứng hệ thống CRM vẫn còn quyền**, và sau cùng **thời điểm gỡ thành công**.

## 2. Những lớp lịch sử phải phân biệt

Một thay đổi Mover thường lan qua nhiều hệ thống. Lịch sử nên theo dõi **các lớp dữ liệu riêng**, tránh gom tất cả vào một dòng “user updated”.

| Lớp | Ví dụ thay đổi | Nguồn hoặc nơi ghi nhận | Ý nghĩa kiểm toán |
| --- | --- | --- | --- |
| **Nguồn nhân sự/hợp đồng** | Department: Support → Finance; manager A → B | HRIS, nguồn nhà thầu có thẩm quyền | Vì sao chuyển vai trò và khi nào có hiệu lực |
| **Danh tính số/quan hệ** | Cập nhật identityId–employment relationship, thuộc tính hiện hành | Identity registry / IGA | Chủ thể nào chịu tác động, thuộc tính nào đổi |
| **Đánh giá chính sách** | Role Support bị gỡ; FinanceReader được duyệt | RBAC/ABAC, access governance | Quyền mong muốn được tính từ điều kiện nào |
| **Phê duyệt/ngoại lệ** | Manager B phê duyệt quyền báo cáo nhạy cảm | Workflow/phê duyệt | Ai chịu trách nhiệm, căn cứ và thời hạn |
| **Thực thi kỹ thuật** | PATCH SCIM, cập nhật group IdP, sửa cloud role | IdP, SCIM/API, cloud IAM, ứng dụng | Yêu cầu nào đã gửi; có lỗi hay hoàn tất |
| **Trạng thái thực tế** | CRM vẫn còn Support; FinanceReader đã tồn tại | Đọc lại hệ thống đích / reconciliation | Có còn lệch với quyền mong muốn không |
| **Phiên/credential liên quan** | Phiên cũ vẫn chứa claim cũ; token cần chấm dứt | IdP, ứng dụng, nền tảng phiên | Quyền trên đường truy cập đã thay đổi đến đâu |
| **Giám sát/sự cố** | Cảnh báo quá hạn thu hồi, phiếu xử lý ngoại lệ | Monitoring, SIEM, ticket | Ai xử lý lệch và xử lý xong khi nào |

**Nguồn nhân sự** có thẩm quyền đối với vai trò và quan hệ việc làm; **IdP** đối với thông tin xác thực/tài khoản mà nó quản lý; **ứng dụng đích** đối với quyền và phiên thực tế do ứng dụng thực thi. Một bản ghi từ một hệ thống không nên được dùng làm bằng chứng thay cho tất cả hệ thống khác.

### 2.1. Ba câu hỏi khác nhau

**Ai/điều gì đã thay đổi?** Cần bản ghi nghiệp vụ gắn với danh tính ổn định, quan hệ làm việc và thuộc tính nguồn.

**Quyền nào nên thay đổi?** Cần kết quả tính toán chính sách tại thời điểm Mover, phê duyệt và trạng thái **desired entitlements**.

**Quyền nào đã thay đổi?** Cần kết quả áp dụng tại IdP/ứng dụng, trạng thái **observed entitlements**, thời điểm xác minh và ngoại lệ.

Chỉ khi đối chiếu đủ ba câu hỏi, tổ chức mới đánh giá được rủi ro *privilege creep* — quyền cũ tích lũy theo những lần chuyển vai trò.

## 3. Những sự kiện cần lưu trong Mover lifecycle

Một lần chuyển việc có thể gây nhiều sự kiện hơn một thay đổi trường department. Danh mục sau là ví dụ cần điều chỉnh theo chính sách.

| Sự kiện | Ví dụ | Điều nên ghi |
| --- | --- | --- |
| **ROLE_OR_ORG_CHANGED** | Chuyển từ Support sang Finance | Old/new values; nguồn; thời điểm hiệu lực; phiên bản |
| **MANAGER_CHANGED** | Đổi người quản lý | Old/new manager ID; quyền phê duyệt bị ảnh hưởng |
| **PROJECT_MEMBERSHIP_CHANGED** | Kết thúc dự án A, tham gia B | Dự án, thời hạn, quyền đã có và quyền cần gỡ |
| **ACCESS_DECISION_EVALUATED** | RBAC/ABAC tính lại quyền | Policy/version, thuộc tính đầu vào, tập quyền mong muốn |
| **ACCESS_REQUEST_APPROVED / DENIED** | Phê duyệt quyền hóa đơn | Người quyết định, phạm vi, hạn hiệu lực, lý do |
| **ENTITLEMENT_GRANT_REQUESTED** | Yêu cầu thêm FinanceReader | Hệ thống, role, requestId, trạng thái gửi |
| **ENTITLEMENT_REVOKE_REQUESTED** | Yêu cầu gỡ CRM-Support | Quyền cụ thể, nguyên nhân, mục tiêu thời gian |
| **TARGET_CHANGE_APPLIED / FAILED** | CRM cập nhật thành công/thất bại | Mã kết quả, thời điểm, thông tin lỗi an toàn |
| **RECONCILIATION_COMPLETED** | Đọc lại danh sách quyền ứng dụng | Desired vs observed, độ lệch, cách xử lý |
| **SESSION_OR_TOKEN_ACTION** | Chấm dứt phiên mang quyền cũ | Loại session/token, hệ thống, kết quả |
| **EXCEPTION_CREATED / CLOSED** | Không thể gỡ role do API lỗi | Owner, hạn xử lý, biện pháp bù trừ và đóng |
| **ACCESS_REVIEW_RESULT** | Data owner xác nhận/thu hồi quyền | Người rà soát, quyết định, ngày, phạm vi |

Một **đơn vị lịch sử** có thể là một thay đổi nhỏ (đổi department) hoặc một **workflow Mover** gồm nhiều thay đổi liên quan. Cần mã tương quan để nối cả hai cấp mà vẫn giữ được kết quả từng thao tác.

## 4. Thiết kế bản ghi: trước/sau, nguồn, lý do và trạng thái

Một bản ghi thay đổi tốt phải **đủ chính xác để diễn giải**, **đủ ít dữ liệu để bảo vệ quyền riêng tư**, và **đủ liên kết để điều tra**.

### 4.1. Các nhóm trường dữ liệu

| Nhóm trường | Ví dụ | Giá trị sử dụng |
| --- | --- | --- |
| **Định danh** | eventId, moverWorkflowId, correlationId | Nhận diện sự kiện và chuỗi thao tác |
| **Chủ thể** | identityId, employmentRelationshipId, identityType | Tránh nhầm người hoặc quan hệ làm việc |
| **Nguồn** | sourceSystem, sourceRecordId, sourceVersion | Biết hệ thống nào tạo sự kiện, chống sự kiện cũ |
| **Người/tác nhân** | initiatedBy, approvedBy, executedBy | Phân biệt yêu cầu con người và tự động hóa |
| **Phạm vi thay đổi** | objectType, objectId, field/entitlement | Biết chính xác tài nguyên nào chịu tác động |
| **Giá trị trước/sau** | oldValue, newValue, before/after snapshot reference | Tái hiện sự thay đổi |
| **Ngữ cảnh** | reasonCode, businessJustification, ticketId | Giải thích tại sao thay đổi |
| **Chính sách** | policyId, policyVersion, approvalId | Biết logic và phê duyệt được áp dụng |
| **Thời gian** | occurredAt, effectiveAt, receivedAt, appliedAt, verifiedAt | Đo độ trễ và truy cứu theo thời điểm |
| **Kết quả** | REQUESTED, APPLIED, FAILED, VERIFIED | Phân biệt dự định với thực tế |
| **Hệ thống đích** | targetSystem, targetAccountId, targetEntitlementId | Đối soát theo ứng dụng |
| **Bằng chứng** | resultCode, evidenceRef, verificationMethod | Truy vết trạng thái mà không lưu bí mật |

Tên trường và giá trị trong bảng là **gợi ý thiết kế**, không phải schema bắt buộc của HRIS, SCIM, OIDC hoặc một nền tảng IAM cụ thể.

### 4.2. Ví dụ sự kiện nhân sự khởi phát Mover

~~~json
{
  "eventId": "hr-event-2208",
  "eventType": "ROLE_OR_ORG_CHANGED",
  "sourceSystem": "HRIS",
  "sourceRecordId": "worker-1042",
  "sourceVersion": 27,
  "identityId": "person-1042",
  "employmentRelationshipId": "employment-8391",
  "oldAttributes": {
    "department": "Support",
    "managerIdentityId": "person-0420"
  },
  "newAttributes": {
    "department": "Finance",
    "managerIdentityId": "person-0023"
  },
  "effectiveAt": "2026-11-20T08:00:00+07:00",
  "publishedAt": "2026-11-19T16:45:00+07:00",
  "correlationId": "mover-20261120-8391"
}
~~~

**Đây là dữ liệu giả định**, không phải định dạng chuẩn. Một nguồn có thể gửi **snapshot trạng thái mới**, nguồn khác gửi **delta**. Bộ điều phối phải biết cách xây dựng thay đổi trước/sau chính xác; không suy ra oldValue chỉ từ bản ghi mới nếu lịch sử nguồn không đủ.

### 4.3. Ví dụ bản ghi thực thi gỡ quyền

~~~json
{
  "changeId": "iam-change-4451",
  "correlationId": "mover-20261120-8391",
  "identityId": "person-1042",
  "targetSystem": "CRM",
  "targetAccountId": "crm-user-722",
  "action": "REVOKE_ENTITLEMENT",
  "entitlementId": "crm-support-reader",
  "expectedBefore": "PRESENT",
  "desiredAfter": "ABSENT",
  "approvalRef": "policy-mover-basic-v4",
  "requestedAt": "2026-11-20T08:00:05+07:00",
  "requestState": "ACCEPTED",
  "targetState": "FAILED",
  "resultCode": "TARGET_RATE_LIMIT",
  "attemptNumber": 1,
  "verifiedAt": null,
  "exceptionId": "iam-exc-2231"
}
~~~

Bản ghi thể hiện **yêu cầu đã được tiếp nhận nhưng chưa gỡ thành công**. Không nên đặt chung trạng thái **COMPLETED** chỉ vì lệnh gửi qua API trả HTTP thành công hoặc hàng đợi nhận bản tin.

### 4.4. Liên kết nhiều bản ghi bằng correlation ID

Một correlationId được dùng xuyên suốt: thay đổi HRIS → quyết định IAM → phê duyệt → request SCIM/API → phản hồi hệ thống đích → đối soát → khắc phục ngoại lệ. Trong từng hệ thống, vẫn cần **ID riêng của bản ghi/sự kiện** để tránh gộp nhầm các lần retry và cho phép truy vết từng bước.

Nếu người dùng có **hai sự kiện Mover gần nhau**, không nên dùng một correlationId duy nhất cho mọi thay đổi trong cả tháng. Hãy phân biệt **workflow ID** từng lần thay đổi và **identityId** chung của chủ thể.

## 5. Thời gian và lịch sử hai chiều: nghiệp vụ và hệ thống

Trong IAM, hỏi “An có quyền này vào ngày nào?” có ít nhất hai cách hiểu:

1. **Theo nghiệp vụ:** ngày nào quyền **đáng lẽ** phải có hoặc bị thu hồi?
2. **Theo thực tế hệ thống:** ngày nào quyền **thật sự** được cấp hoặc mất hiệu lực?

Hai thời điểm có thể lệch nhau do đồng bộ chậm, thiếu approval, lỗi API hoặc phiên tồn dư. Vì vậy lịch sử cần quản lý **thời gian hiệu lực** (*valid time*) và **thời gian ghi nhận/thực thi** (*transaction/observation time*) theo mục đích phân tích.

| Mốc | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **eventOccurredAt** | Sự kiện nguồn được tạo khi nào? | HRIS ghi thay đổi 19/11 |
| **effectiveAt** | Vai trò/quyền nên đổi từ khi nào? | Mover có hiệu lực 08:00 ngày 20/11 |
| **publishedAt** | Nguồn gửi sự kiện khi nào? | 19/11, 16:45 |
| **receivedAt** | IAM nhận sự kiện khi nào? | 19/11, 16:46 |
| **decisionAt** | Policy đánh giá và quyết định khi nào? | 20/11, 07:59 |
| **requestedAt** | Lệnh cập nhật quyền được gửi khi nào? | 20/11, 08:00 |
| **appliedAt** | Hệ thống đích thực thi khi nào? | 20/11, 08:07 |
| **verifiedAt** | Đối soát xác nhận khi nào? | 20/11, 08:08 |
| **sessionEndedAt** | Phiên/token có liên quan hết khả năng truy cập khi nào? | Theo cơ chế hệ thống đích |

Những giá trị trong bảng chỉ minh họa. Hệ thống thực cần thống nhất múi giờ, đồng bộ đồng hồ và định nghĩa thời điểm nào được coi là **thực thi**. Với quyền có rủi ro cao, khoảng từ effectiveAt đến appliedAt/verifiedAt là tín hiệu quan trọng về **truy cập tồn dư**.

### 5.1. Thay đổi hồi tố và thông tin đến muộn

Giả sử ngày 23/11 HRIS sửa dữ liệu với hiệu lực từ 20/11. Nếu IAM chỉ ghi “cập nhật 23/11”, lịch sử không cho biết quyền đáng lẽ phải thu hồi từ ngày 20/11. Ngược lại, không được sửa timestamp thực thi từ 23/11 thành 20/11 để tạo cảm giác đã thu hồi đúng hạn.

Cần lưu **cả mốc hiệu lực nghiệp vụ lẫn ngày hệ thống biết và áp dụng**. Nếu nguồn chỉnh lại một trường cũ, thêm bản ghi hiệu chỉnh tham chiếu bản gốc và lý do; không âm thầm xóa dấu vết đã xảy ra.

### 5.2. Ví dụ tính độ trễ thu hồi

~~~text
08:00  Mover effective: department Support -> Finance
08:01  IAM gửi yêu cầu revoke "crm-support-reader"
08:01  API phản hồi lỗi RATE_LIMIT
08:06  Retry thành công
08:07  Ứng dụng xác nhận role đã mất
08:08  IAM đọc lại observed role = ABSENT

Khoảng chưa đạt desired state:
  effectiveAt -> verifiedAt = 8 phút

Nếu phiên cũ vẫn dùng quyền đến 08:12:
  khả năng truy cập thực tế phải đánh giá thêm ở lớp session/token
~~~

Không nên suy luận chắc chắn người dùng **đã sử dụng quyền** trong 8 phút; đây là **khoảng quyền có thể còn tồn tại**, cần đối chiếu nhật ký truy cập nếu có cảnh báo hoặc điều tra.

## 6. Lưu trạng thái trước/sau và lịch sử quyền hiệu lực

### 6.1. Delta, snapshot và event log

Ba cách lưu dữ liệu thường bổ sung cho nhau:

| Cách lưu | Điểm mạnh | Giới hạn/cần bổ sung |
| --- | --- | --- |
| **Delta (oldValue → newValue)** | Dễ biết trường/role nào đổi, tiết kiệm dữ liệu cho thay đổi nhỏ | Khó dựng toàn bộ trạng thái nếu thiếu sự kiện hoặc không có snapshot gốc |
| **Snapshot tại mốc xác định** | Dễ xem toàn bộ thuộc tính/quyền ở một thời điểm | Có thể tốn chỗ; hai snapshot không giải thích đầy đủ ai ra quyết định |
| **Append-only event/audit log** | Giữ trình tự, nguồn, quyết định và trạng thái thao tác | Cần schema, tính nhất quán, kiểm soát toàn vẹn và đối soát hiện trạng |

**Kết hợp khuyến nghị:** lưu sự kiện/thao tác có cấu trúc; lưu snapshot quyền mong muốn/thực tế ở các mốc cần thiết hoặc tham chiếu đến snapshot; có cơ chế dựng lại lịch sử khi cần kiểm toán.

Không nên gọi hệ thống “event sourced” chỉ vì có audit log. **Event sourcing** là một phương pháp kiến trúc nơi sự kiện là nguồn để dựng trạng thái ứng dụng; nhiều hệ thống IAM chỉ cần **change history/audit trail** và trạng thái hiện tại có đối soát.

### 6.2. Quyền mong muốn và quyền thực tế

Một bản ghi Mover nên giúp so sánh:

~~~text
Identity: person-1042
Before (đã được duyệt):
  department = Support
  desired = {crm-support-reader, vpn-basic}

After (đã được duyệt):
  department = Finance
  desired = {finance-report-reader, vpn-basic}

Observed tại 08:02:
  {crm-support-reader, finance-report-reader, vpn-basic}

Delta sai lệch:
  EXTRA  = {crm-support-reader}
  MISSING = {}

Observed tại 08:08:
  {finance-report-reader, vpn-basic}
  -> Kết quả gỡ quyền cũ được xác minh
~~~

**Tập quyền thực tế** có thể không tương đương một danh sách group: cần xét role kế thừa, ACL, quyền cấp trực tiếp, chính sách ABAC, session, token và các tài khoản khác cùng chủ thể. Nếu chỉ lưu thay đổi group IdP mà không kiểm tra quyền trong ứng dụng, lịch sử vẫn thiếu một phần rủi ro.

### 6.3. Quyền được gán và quyền hiệu lực

**Assigned entitlement** là quyền/role được gán trực tiếp hoặc gián tiếp. **Effective permission** là quyền hệ thống thực thi sau khi đánh giá kế thừa, điều kiện, deny policy hoặc ngữ cảnh.

Ví dụ role FinanceReader đã được gán nhưng policy ABAC hạn chế dữ liệu theo organizationUnit. Lịch sử Mover cần lưu:

- Role đã được cấp hoặc gỡ.
- Thuộc tính dùng trong chính sách (department, organizationUnit, workerType...).
- Phiên bản policy và thời gian áp dụng, nhất là nếu policy đổi đồng thời.
- Kết quả kiểm tra quyền hiệu lực tại tài nguyên có rủi ro liên quan khi khả thi.

Một account **có role** nhưng **không được phép truy cập** do điều kiện ABAC là tình huống khác với account **không còn role**. Đừng đánh đồng hai trạng thái trong báo cáo.

## 7. Lưu phê duyệt, lý do nghiệp vụ và phân tách nhiệm vụ

Mover thường kéo theo quyền mới, đặc biệt nếu chuyển sang bộ phận tài chính, vận hành sản xuất hoặc quản trị hệ thống. Lịch sử thay đổi phải chỉ rõ **quyền dựa trên chính sách tự động** hay **ngoại lệ có phê duyệt**.

Những trường thông dụng:

- **requester/initiator:** ai hoặc hệ thống nào yêu cầu.
- **approver:** người hoặc vai trò có thẩm quyền chấp thuận.
- **requestReason/businessJustification:** nhiệm vụ cần quyền.
- **approvalPolicyId/version:** chính sách được sử dụng.
- **effectiveFrom/effectiveUntil:** thời gian quyền có hiệu lực.
- **segregationOfDutiesResult:** kiểm tra xung đột quyền.
- **compensatingControl:** kiểm soát bù trừ khi ngoại lệ được duyệt.
- **approvalRecordedAt:** thời điểm quyết định, tách với ngày hiệu lực.

**SoD (Segregation of Duties)** đòi hỏi kiểm soát tổ hợp quyền. Ví dụ một người vừa có quyền tạo nhà cung cấp vừa có quyền phê duyệt thanh toán là xung đột ở nhiều môi trường. Trong Mover, ghi cả kết quả đánh giá **trước và sau** thay đổi; một role riêng lẻ có thể hợp lệ nhưng tổ hợp role lại không hợp lệ.

### 7.1. Rủi ro phê duyệt sau khi quyền đã cấp

Nếu IAM cấp quyền đặc biệt lúc 08:00 nhưng chỉ nhận approval lúc 09:00, không được viết lại lịch sử như thể quyền có phê duyệt từ trước. Hãy lưu sự kiện **cấp trước, phê duyệt sau**, lý do, phạm vi, người chịu trách nhiệm và biện pháp xử lý theo chính sách. Lịch sử đầy đủ giúp phân biệt **ngoại lệ hợp lệ** với một bước kiểm soát bị bỏ qua.

## 8. Tích hợp IdP, SSO, SCIM, RBAC/ABAC và hệ thống đích

Một lần Mover có thể lan qua nhiều thành phần nhưng **mỗi thành phần có ý nghĩa và trách nhiệm khác nhau**.

### 8.1. HRIS → Identity Registry / IGA

HRIS hoặc nguồn hợp đồng gửi thay đổi công việc với mã danh tính và thời điểm hiệu lực. Identity registry/IGA đối chiếu chủ thể, lưu phiên bản thuộc tính, tính lại quyền hợp lệ và khởi chạy workflow.

**Cần ghi:** nguồn, version, old/new attributes, identityId, employmentRelationshipId, trạng thái trước/sau của workflow và chính sách đã dùng.

### 8.2. IdP và SSO

IdP có thể cập nhật nhóm, thuộc tính và chính sách xác thực; SSO qua OIDC/SAML đưa các claim được phép tới ứng dụng. Trong Mover:

- Claim trong token cũ có thể vẫn phản ánh department/role cũ cho tới khi token hết hạn hoặc phiên được đánh giá lại.
- Khóa hoặc đổi nhóm tại IdP **không tự đảm bảo** mọi ứng dụng loại bỏ phiên đang tồn tại.
- Thay đổi cấu hình federation và group claim cũng cần audit vì một mapping sai có thể cấp quyền rộng cho nhiều người.

**Cần ghi:** accountId, group/claim mapping bị đổi, thời điểm token/phiên được đánh giá/thu hồi nếu chính sách yêu cầu; tránh ghi giá trị token bí mật.

### 8.3. SCIM/API provisioning

SCIM chuẩn hóa việc quản lý tài nguyên user/group cho các hệ thống hỗ trợ. Nó có thể giúp đổi group hoặc trạng thái account ở ứng dụng, nhưng không mặc nhiên hỗ trợ mọi role, ACL, session hoặc thông tin xác thực riêng.

**Cần ghi:** lệnh cập nhật, idempotency/request ID, tài khoản đích, quyền được đề nghị thêm/gỡ, phản hồi API, số lần retry, lỗi, observed state sau đối soát.

### 8.4. RBAC và ABAC

**RBAC** phụ thuộc role được gán. **ABAC** còn phụ thuộc thuộc tính hiện hành của chủ thể, tài nguyên, hành động và ngữ cảnh. Một sự kiện Mover có thể đổi quyền dù role không đổi nếu department, region hoặc project thay đổi.

Ví dụ mã giả minh họa:

~~~text
ALLOW report.read WHEN
    subject.lifecycleStatus == ACTIVE
    AND subject.approvedRole == FinanceReader
    AND subject.department == resource.department
    AND resource.sensitivity <= subject.clearance
ELSE DENY
~~~

Đây là **mã giả**, không phải policy engine tiêu chuẩn. Để hiểu một quyết định lịch sử, cần biết **phiên bản policy và thuộc tính đã được sử dụng tại thời điểm đánh giá**, thay vì áp chính sách hôm nay lên dữ liệu cũ rồi suy luận lịch sử.

### 8.5. Tại sao không chỉ ghi một dòng “moved successfully”?

~~~mermaid
flowchart TD
  A["HRIS: department Support -> Finance"] --> B["IGA: xác định desired access"]
  B --> C["Phê duyệt và kiểm tra SoD"]
  C --> D["IdP: cập nhật thuộc tính, nhóm"]
  C --> E["SCIM/API: gỡ quyền cũ, cấp quyền mới"]
  D --> F["SSO / session: đánh giá điều kiện cũ"]
  E --> G["Ứng dụng / Cloud: trạng thái thực tế"]
  F --> H["Reconciliation"]
  G --> H
  H --> I{"Desired == Observed?"}
  I -->|"Không"| J["Exception + retry / xử lý có owner"]
  J --> H
  I -->|"Có"| K["Lưu verifiedAt, evidence, đóng workflow"]
~~~

Tại mỗi nút phải có trạng thái và bằng chứng riêng. Một API thành công không chứng minh những nút còn lại đã hoàn thành.

## 9. Lịch sử thay đổi phải bền vững trước lỗi và trùng sự kiện

### 9.1. Idempotency và event ordering

HRIS, message broker và SCIM/API có thể gửi lại một sự kiện, mất kết nối hoặc thay đổi thứ tự chuyển đến. Bộ điều phối nên lưu:

- **eventId/sourceRecordVersion:** nhận ra sự kiện cũ/lặp.
- **workflowId/correlationId:** liên kết tất cả thao tác thuộc một lần Mover.
- **changeId/idempotencyKey:** tránh thêm role hoặc tạo bản ghi trùng khi retry.
- **attemptNumber/resultCode:** theo dõi từng lần thử mà không ghi đè lỗi cũ.
- **sourceCurrentVersion:** kiểm tra trạng thái nghiệp vụ mới nhất trước khi áp.
- **desiredAccessVersion:** bảo đảm task đến muộn không khôi phục quyền đã bị gỡ.

Một sự kiện Mover cũ đến sau Leaver có thể **tái tạo quyền của người đã nghỉ** nếu hệ thống chỉ chạy các lệnh “add group” một cách cơ học. Lịch sử phiên bản và kiểm tra nguồn hiện tại là chốt kiểm soát quan trọng.

### 9.2. Ghi lại cả lần thất bại

Ví dụ:

~~~text
changeId=iam-4451, action=REVOKE, target=CRM
  attempt 1 | 08:01 | FAILED  | RATE_LIMIT
  attempt 2 | 08:05 | ACCEPTED
  verify    | 08:08 | VERIFIED | role absent

Kết luận:
  - Workflow có một lỗi thực thi tạm thời.
  - Quyền cũ tồn tại qua một khoảng sau effectiveAt.
  - Yêu cầu thu hồi cuối cùng đã được xác minh lúc 08:08.
~~~

Nếu chỉ lưu trạng thái cuối **VERIFIED**, tổ chức sẽ mất dữ liệu về độ trễ và nguyên nhân lỗi. Nếu chỉ lưu **FAILED**, sẽ không biết đã khắc phục thành công.

### 9.3. Một thay đổi trải rộng nhiều hệ thống

Không có giao dịch cơ sở dữ liệu duy nhất bao trùm mọi SaaS, IdP, VPN và cloud IAM. Mover thường dùng cơ chế **điều phối nhiều bước**, với khả năng **thành công một phần** và xử lý bù trừ.

Ví dụ:

| Hệ thống | Yêu cầu | Trạng thái | Bước tiếp theo |
| --- | --- | --- | --- |
| IdP | Gỡ nhóm Support | VERIFIED | Đóng bước |
| ERP | Cấp FinanceReader | VERIFIED | Đóng bước |
| CRM | Gỡ SupportReader | FAILED | Retry/can thiệp có owner |
| VPN | Giữ BasicVPN | NO_CHANGE | Chỉ ghi nhận chính sách không cần thay |
| Session | Chấm dứt phiên cũ theo chính sách | PENDING | Thực hiện và xác minh riêng |

Workflow tổng thể chỉ nên **COMPLETED** khi các bước bắt buộc được xác minh, hoặc các ngoại lệ được giải quyết theo tiêu chí được tổ chức định nghĩa. Việc không thay đổi VPN cũng là một **quyết định** có thể cần truy vết khi đánh giá quyền.

## 10. Tránh việc sửa lịch sử để che lỗi hoặc làm sai điều tra

### 10.1. Append-only và bản ghi hiệu chỉnh

Với dữ liệu kiểm toán, nguyên tắc hữu ích là **không âm thầm sửa/xóa những sự kiện đã ghi**. Nếu phát hiện sai, tạo **sự kiện hiệu chỉnh** tham chiếu sự kiện cũ:

~~~json
{
  "eventId": "audit-correction-5502",
  "eventType": "CORRECTION",
  "correctsEventId": "hr-event-2208",
  "correctionReason": "Wrong effective date confirmed by HR",
  "oldEffectiveAt": "2026-11-20T08:00:00+07:00",
  "newEffectiveAt": "2026-11-21T08:00:00+07:00",
  "recordedAt": "2026-11-23T10:00:00+07:00",
  "authorizedBy": "hr-approver-18"
}
~~~

Bản ghi hiệu chỉnh là **dữ liệu ví dụ**. Cách tổ chức xử lý thay đổi có thể khác, nhưng phải giữ được vết **đã biết gì tại thời điểm nào** và **khi nào nhận được thông tin chính xác hơn**.

### 10.2. Tính toàn vẹn và kiểm soát truy cập

“Append-only” trong ứng dụng không tự làm log bất biến nếu tài khoản quản trị hệ thống vẫn có thể sửa/xóa dữ liệu nền. Kiểm soát thực tế có thể gồm:

- Phân tách quyền **ghi log**, **đọc log**, **quản trị lưu trữ** và **xóa theo chính sách**.
- Gửi log qua hệ thống tập trung với quyền tối thiểu và kênh bảo vệ.
- Bảo vệ tính toàn vẹn bằng ký số/hàm băm liên kết hoặc tính năng chống sửa đổi của kho lưu trữ khi phù hợp.
- Sao lưu, phát hiện xóa/sửa bất thường và giám sát cấu hình.
- Đồng bộ thời gian và lưu trạng thái nguồn để tránh nhầm thứ tự.
- Kiểm tra khôi phục dữ liệu và khả năng truy xuất khi kiểm toán.

Cơ chế hash-chain hoặc chữ ký **có thể giúp phát hiện thay đổi** nếu khóa và điểm neo được bảo vệ; nó không tự bảo đảm dữ liệu đầu vào **đúng**. Nếu một hệ thống gửi giá trị department sai, log vẫn có thể toàn vẹn nhưng chứa dữ liệu nghiệp vụ sai.

### 10.3. Quyền riêng tư và giảm dữ liệu nhạy cảm

Lịch sử Mover có thể chứa thông tin nhân sự như tổ chức, người quản lý, địa điểm, thay đổi hợp đồng và đôi khi lý do riêng tư. Không nên ghi **mật khẩu, API token, private key, mã khôi phục MFA, bản quét giấy tờ**, hoặc thông tin cá nhân không cần cho mục đích kiểm toán.

Có thể lưu **mã lý do và tham chiếu** tới hồ sơ có kiểm soát thay vì sao chép nội dung nhạy cảm vào mọi audit event. Đặt thời hạn lưu theo nhu cầu bảo mật, pháp lý và chính sách của tổ chức; giới hạn đối tượng có thể tra cứu lịch sử. Nhiệm vụ chứng minh truy cập hợp lệ không đòi hỏi mọi người xem được toàn bộ hồ sơ nhân sự.

## 11. Khôi phục, đảo ngược và xử lý sai lệch

Một thay đổi Mover có thể sai do HRIS nhập nhầm department, role mapping sai hoặc hệ thống đích áp không đúng. **Rollback** cần được thiết kế cẩn thận: phục hồi “bộ quyền cũ” nguyên vẹn có thể mở lại quyền quá rộng hoặc vi phạm chính sách mới.

### 11.1. Phân biệt ba hành động

- **Correction:** sửa dữ liệu nguồn hoặc chính sách sai; giữ lịch sử đã xảy ra.
- **Compensating action:** chạy hành động có chủ đích để giảm hậu quả của thao tác đã thực hiện, ví dụ gỡ role vừa cấp sai.
- **Rollback:** đưa một hệ thống trở lại trạng thái trước đó khi an toàn và có cơ sở nghiệp vụ; phải xét thay đổi khác phát sinh ở giữa.

Ví dụ nhân viên chuyển từ Support sang Finance, sau đó HRIS sửa lại Finance thành Legal. Hệ thống không nên “rollback Finance sang Support” theo snapshot cũ; **desired access mới** có thể phải là Legal. Tính lại quyền từ trạng thái nguồn mới nhất và ghi đầy đủ các hành động bù trừ.

### 11.2. Một quy tắc điều phối minh họa

~~~text
onMoverEvent(event):
    verifyTrustedSourceAndIdentityLink(event)

    current = readCurrentAuthoritativeState(event.relationshipId)
    if isDuplicate(event.eventId):
        return existingWorkflowStatus
    if isStale(event.sourceVersion, current.version):
        appendAudit("IGNORED_STALE_EVENT", event.eventId)
        return NO_ACCESS_CHANGE

    desired = evaluateCurrentPolicies(current)
    observed = readActualEntitlements(event.identityId)

    appendAudit("DESIRED_ACCESS_COMPUTED", desired.policyVersion)
    plan = diff(observed, desired)

    for each change in plan:
        appendAudit("CHANGE_REQUESTED", change)
        result = applyIdempotently(change)
        appendAudit("CHANGE_RESULT", result)

    verified = reconcileTargets(event.identityId, desired)
    appendAudit("RECONCILIATION_RESULT", verified)

    if not verified.allMandatoryTargetsMatch:
        createOwnedExceptionWithDeadline(verified.gaps)
        return PARTIAL
    return COMPLETED
~~~

Đoạn mã là **mã giả**, không phải hàm sẵn có trong SCIM, HRIS hoặc thư viện cụ thể. Một triển khai thực tế cần xử lý cạnh tranh giữa các workflow, transaction boundary, timeout, retry, bảo vệ thông tin cá nhân và chính sách an toàn khi nguồn chưa sẵn sàng.

### 11.3. Điều tra một quyền tồn dư

Giả sử phát hiện vào ngày 23/11 rằng tài khoản vẫn có quyền CRM-Support sau khi Mover ngày 20/11:

1. Dựa vào identityId và account link để tìm đúng người/tài khoản.
2. Đọc HRIS lịch sử: department nào, Mover có hiệu lực lúc nào?
3. Đọc quyết định IAM: quyền nào **đáng lẽ phải gỡ**?
4. Đọc request history: đã gửi lệnh chưa, lỗi hay thành công?
5. Đọc trạng thái CRM và quyền hiệu lực; kiểm tra vai trò cấp trực tiếp hoặc group lồng nhau.
6. Kiểm tra session/token có thể còn được dùng trong khoảng lệch theo khả năng của nền tảng.
7. Thu hồi quyền không hợp lệ, xác minh lại, đánh giá nhật ký truy cập theo yêu cầu và cập nhật root cause.

Lịch sử đầy đủ giúp làm rõ **điểm đứt của quy trình** và ưu tiên sửa nguyên nhân, thay vì chỉ chỉnh một role rồi bỏ qua lỗi đồng bộ.

## 12. Tài khoản dịch vụ và danh tính phi con người khi thay đổi chủ sở hữu

Một người chuyển vai trò có thể đang là **owner** của service account, workload identity, bot hoặc pipeline CI/CD. Danh tính phi con người không chuyển phòng ban như nhân viên, nhưng **mối quan hệ sở hữu và quyền quản trị nó** có thể thay đổi.

Cần ghi lịch sử các sự kiện:

| Thay đổi | Rủi ro | Bằng chứng cần lưu |
| --- | --- | --- |
| Owner A → Owner B | Không có người chịu trách nhiệm nếu bàn giao thiếu | Old/new owner, chấp thuận nhận bàn giao, effectiveAt |
| Đổi nhóm vận hành workload | Quyền admin/secret cũ còn ở người chuyển bộ phận | Thao tác gỡ quyền người cũ, gán quyền người mới, xác minh |
| Rotate credential | Token/khóa cũ có thể tiếp tục dùng | Credential reference, thời điểm rotate/revoke, trạng thái xác minh |
| Đổi môi trường/purpose | Scope tài khoản dịch vụ không còn phù hợp | Old/new purpose/environment, quyền trước/sau, policy |
| Retirement | Workload hết sử dụng nhưng principal còn hoạt động | Quy trình vô hiệu hóa, xử lý phụ thuộc, bằng chứng thu hồi |

**Không ghi bí mật thực tế vào lịch sử.** Lưu identifier hoặc tham chiếu bảo vệ của credential, cùng trạng thái vòng đời. Không xóa vội workload đang phục vụ sản xuất chỉ vì owner cũ chuyển việc; cần chuyển giao có trách nhiệm, giảm quyền của owner cũ và kiểm tra phụ thuộc.

## 13. Ví dụ tổng hợp: Mover nhiều hệ thống

Giả sử nhân viên **Hà** chuyển từ nhóm Infrastructure Operations sang Finance Analytics ngày **20/11/2026 lúc 08:00**. Trước khi chuyển, Hà có quyền xem log sản xuất và quản trị một repository nội bộ; vai trò mới cần đọc báo cáo tài chính.

### 13.1. Dòng sự kiện

| Mốc | Hành động | Bản ghi cần giữ |
| --- | --- | --- |
| 19/11, 17:00 | HRIS xác nhận thay đổi có hiệu lực ngày 20/11 | Event nguồn, version, before/after, effectiveAt |
| 19/11, 17:01 | IGA xác định quyền cần thu hồi/cấp | Policy version, desired access, SoD |
| 19/11, 17:05 | Finance data owner phê duyệt quyền mới | approvalId, approver, scope |
| 20/11, 08:00 | IdP đổi group | RequestId, trạng thái, timestamp |
| 20/11, 08:01 | Cloud IAM gỡ quyền log sản xuất | Target role, kết quả API |
| 20/11, 08:02 | Git API không gỡ được role maintainer | Failure code, retry, exception owner |
| 20/11, 08:03 | Finance app cấp FinanceReader | AccountId, entitlement, kết quả |
| 20/11, 08:10 | Retry gỡ Git maintainer thành công | Attempt history, observed permission |
| 20/11, 08:11 | Reconciliation xác nhận không còn quyền cũ | Desired/observed, verifiedAt |

**Sai lầm cần tránh:** chỉ ghi “Mover completed 08:03” khi Git maintainer vẫn tồn tại đến 08:10. Trạng thái workflow tổng có thể là **PARTIAL** tới lúc quyền bắt buộc được xác minh.

### 13.2. Bằng chứng về quyền thực tế

Nhóm IAM cần tính đến quyền được cấp theo group, role trực tiếp và policy. Một bảng đối chiếu có thể là:

| Tài nguyên | Quyền cũ | Quyền mong muốn | Quyền lúc 08:03 | Quyền lúc 08:11 |
| --- | --- | --- | --- | --- |
| Production logs | Read | None | None | None |
| Git repository | Maintainer | None | Maintainer | None |
| Finance reports | None | FinanceReader | FinanceReader | FinanceReader |
| Basic VPN | Basic | Basic | Basic | Basic |

Ngoài việc gỡ quyền Git, cần đánh giá liệu phiên đang có hoặc token cá nhân có còn cho phép thao tác quản trị theo giới hạn nền tảng. **Một role bị gỡ không bảo đảm token đã phát hành bị vô hiệu hóa tức thì**, nên nếu chính sách yêu cầu chấm dứt truy cập ngay, hành động đối với phiên/token phải có lịch sử riêng.

### 13.3. Sau một tháng

Nếu kiểm toán hỏi “Hà có khả năng thao tác maintainer lúc 08:05 ngày 20/11 không?”, hệ thống phải tìm **bản ghi trạng thái thực tế và hạn hiệu lực phiên/token**, không chỉ nhìn role đang có hôm nay. Có thể cần nói rõ **dữ liệu quan sát không đủ để khẳng định** mọi phiên/token tại thời điểm đó. Không được biến lịch sử “request success” thành bằng chứng không có truy cập.

## 14. Mô hình lưu trữ và truy vấn lịch sử

Dữ liệu thay đổi có thể được giữ trong audit store hoặc các bảng có cấu trúc, với liên kết tới trạng thái hiện tại. Không nhất thiết chọn một kiến trúc lưu trữ duy nhất; điều quan trọng là **tái hiện được hành vi, trạng thái và bằng chứng**.

### 14.1. Cấu trúc dữ liệu minh họa

~~~text
identity_change_event
  event_id
  correlation_id
  identity_id
  employment_relationship_id
  source_system, source_record_id, source_version
  event_type, old_value_ref, new_value_ref
  effective_at, received_at, recorded_at

access_change_decision
  decision_id, correlation_id, identity_id
  target_system, account_id, entitlement_id
  old_desired_state, new_desired_state
  policy_id, policy_version, approval_id

access_change_execution
  execution_id, decision_id, attempt_number
  requested_at, applied_at, result_state, result_code
  target_request_id

access_change_verification
  verification_id, decision_id
  observed_state, verified_at, evidence_ref
  exception_id
~~~

Các bảng là **sơ đồ logic minh họa**, không phải schema SQL có thể chạy trực tiếp. Dữ liệu lớn có thể dùng sự kiện và tài liệu tham chiếu, nhưng phải giữ khả năng query theo **identityId + thời gian**, **correlationId**, **hệ thống đích**, **entitlement**, **đối tượng phê duyệt** và **trạng thái thất bại**.

### 14.2. Ví dụ truy vấn các lần thu hồi chưa được xác minh

~~~sql
SELECT
    d.identity_id,
    d.target_system,
    d.entitlement_id,
    d.decision_id,
    d.effective_at
FROM access_change_decision AS d
LEFT JOIN access_change_verification AS v
  ON v.decision_id = d.decision_id
WHERE d.new_desired_state = 'ABSENT'
  AND d.effective_at <= CURRENT_TIMESTAMP
  AND (v.verification_id IS NULL OR v.observed_state <> 'ABSENT');
~~~

**Lưu ý:** truy vấn này dùng **bảng giả định** và đơn giản hóa việc chọn bản ghi verification mới nhất. Một hệ thống thực cần xử lý **nhiều lần xác minh**, ngoại lệ hợp lệ, quyền được cấp lại do sự kiện mới hơn và quan hệ identity–account thay đổi. Nếu không, kết quả có thể báo sai lệch giả hoặc bỏ sót quyền thực sự còn tồn tại.

### 14.3. Đọc lịch sử theo thời điểm

Khi xây dựng trang điều tra, người dùng cần chọn **thời điểm nghiệp vụ** và **thời điểm hệ thống đã biết thông tin**. Ví dụ:

- “Theo hồ sơ HR đã hiệu lực vào 08:00, Hà **nên** còn quyền gì?”
- “Theo quyền đọc lại từ Git lúc 08:05, Hà **đang được gán** quyền gì?”
- “Hôm nay ta biết một thay đổi được sửa hồi tố; điều đó ảnh hưởng cách diễn giải dữ liệu tại 08:05 như thế nào?”

Khả năng trả lời những câu hỏi này gần với **lịch sử hai chiều (bitemporal)**. Không bắt buộc mọi doanh nghiệp xây dựng cơ sở dữ liệu bitemporal đầy đủ, nhưng phải lưu các mốc để không trộn lẫn **thời gian hiệu lực** với **thời gian ghi nhận**.

## 15. Chỉ số vận hành dựa trên lịch sử thay đổi

| Chỉ số | Cách tính/diễn giải | Vì sao hữu ích |
| --- | --- | --- |
| **Mover completion time** | Từ effectiveAt đến verifiedAt của các bước bắt buộc | Đo thời gian hoàn tất chuyển vai trò |
| **Revoke latency** | Từ lúc quyền không còn cần đến khi target xác nhận mất quyền | Đo khoảng quyền có thể tồn dư |
| **Residual entitlement count** | Số quyền thực tế không còn thuộc desired access sau Mover | Phát hiện privilege creep |
| **Partial/failed Mover rate** | Workflow thiếu ít nhất một bước xác minh cần thiết / tổng workflow | Theo dõi lỗi tích hợp |
| **Unapproved change count** | Thao tác cấp/đổi quyền không có căn cứ policy hoặc approval phù hợp | Phát hiện cấp quyền ngoài luồng |
| **Stale-event rejection rate** | Sự kiện nguồn trùng/cũ bị bỏ qua / tổng sự kiện | Giám sát chất lượng event feed |
| **Overdue exceptions** | Ngoại lệ thu hồi chưa đóng sau thời hạn chính sách | Nhận biết rủi ro tồn đọng |
| **Account-to-identity coverage** | Tỷ lệ tài khoản liên kết được identity/owner hợp lệ | Hỗ trợ offboarding và điều tra |
| **Audit completeness** | Tỷ lệ thay đổi có đủ nguồn, approval, kết quả, verifiedAt | Đo chất lượng bằng chứng |
| **Service owner transfer completion** | Tỷ lệ tài khoản dịch vụ đổi owner được ghi/đối soát đủ | Giảm danh tính phi con người thiếu người chịu trách nhiệm |

Không nên sử dụng chỉ một con số “tỷ lệ API thành công” để đánh giá Mover. Có thể API trả thành công nhưng quyền tại ứng dụng còn hiệu lực do caching hoặc mapping. **Mẫu số, phạm vi hệ thống và thời điểm đo phải được định nghĩa rõ** để so sánh có ý nghĩa.

## 16. Bảng kiểm tra khi triển khai lịch sử thay đổi Mover

| Câu hỏi kiểm tra | Bằng chứng kỳ vọng |
| --- | --- |
| Lịch sử có liên kết đúng chủ thể không? | identityId ổn định, relationshipId, account links |
| Có lưu thuộc tính trước/sau và nguồn HRIS không? | Old/new values, source version, effectiveAt |
| Có phân biệt quyết định quyền và thao tác kỹ thuật không? | DecisionId, policy version, execution result |
| Có lưu phê duyệt và lý do nghiệp vụ không? | Approver, approvalId, ticket, expiry |
| Có kiểm tra SoD khi role mới kết hợp role cũ không? | Kết quả kiểm tra tổ hợp quyền |
| Có lịch sử gỡ quyền cũ, không chỉ cấp quyền mới không? | Revoke request, target observed state |
| Có phân biệt requested/applied/verified không? | Trạng thái và timestamp ở từng hệ thống |
| Có xử lý phiên/token độc lập với group không? | Session action/verification trong scope |
| Retry có lưu lỗi và chống trùng không? | EventId, idempotency key, attempt log |
| Sự kiện cũ có thể mở lại quyền sau Leaver không? | Version/current-state guard, audit ignored event |
| Có quản lý quyền cấp thủ công ngoài IdP không? | Đối soát hệ thống đích và owner exception |
| Có lưu sự kiện sửa sai mà không xóa lịch sử gốc không? | Correction reference, actor, recordedAt |
| Audit có được bảo vệ khỏi sửa/xóa trái phép không? | Phân quyền, lưu trữ bảo vệ, giám sát tính toàn vẹn |
| Có tránh lưu secret/dữ liệu nhân sự quá mức không? | Data minimization và retention policy |
| Chuyển chủ sở hữu service account có được ghi nhận không? | Old/new owner, rotate/revoke credential, xác minh |
| Có dựng được quyền tại một mốc trong quá khứ không? | Snapshot/delta, event, observed evidence, thời gian |
| Có thể đo độ trễ và quyền tồn dư không? | effectiveAt, appliedAt, verifiedAt và KPI |

## 17. Câu hỏi tự đánh giá

1. Vì sao bản ghi HRIS **department = Finance** chưa đủ để chứng minh quyền Support đã bị thu hồi?
2. Phân biệt **business event**, **access decision**, **execution result** và **reconciliation evidence** bằng một ví dụ chuyển vai trò.
3. Cần ghi những mốc thời gian nào để phát hiện quyền còn tồn tại sau effectiveAt?
4. API SCIM báo thành công nhưng ứng dụng vẫn cho phép thao tác bằng token cũ. Lịch sử nên phản ánh điều gì?
5. Vì sao lưu “mỗi người có những role gì hôm nay” khác với lưu lịch sử quyền đã có ở một thời điểm?
6. Một sự kiện Mover cũ đến muộn sau khi người dùng đã Leaver. Làm thế nào để chặn việc cấp lại quyền và vẫn lưu đủ audit?
7. Khi HRIS sửa ngày chuyển bộ phận hồi tố, tại sao không nên sửa cả appliedAt cho giống effectiveAt?
8. Khi nhân viên chuyển phòng ban, một service account do họ quản lý vẫn chạy. Cần ghi những thay đổi ownership và credential nào?
9. Vì sao snapshot trạng thái và delta thay đổi thường cần bổ sung cho nhau?
10. Trong trường hợp chuyển quyền bị lỗi một phần, khi nào workflow có thể được kết luận COMPLETED? Bằng chứng tối thiểu là gì?

## 18. Ghi nhớ

Trong **Mover lifecycle**, lưu lịch sử thay đổi là cách giữ một **chuỗi bằng chứng xuyên suốt** từ **nguồn nhân sự và sự kiện thay đổi vai trò** đến **quyết định cấp/thu hồi quyền**, **phê duyệt**, **thực thi tại IdP/SSO/SCIM, ứng dụng và hạ tầng**, rồi **đối soát trạng thái thực tế**.

Một lịch sử có giá trị phải cho thấy **trước/sau**, **nguồn**, **người chịu trách nhiệm**, **lý do**, **thời điểm hiệu lực**, **thời điểm thực thi**, **thời điểm xác minh**, **lỗi và cách khắc phục**. Kết hợp log có kiểm soát toàn vẹn, snapshot/delta quyền, policy RBAC/ABAC, quản trị tài khoản dịch vụ và kiểm toán sẽ giúp tổ chức phát hiện **privilege creep**, kiểm soát **quyền truy cập tồn dư**, điều tra sự cố và đảm bảo một người chuyển vai trò chỉ giữ những quyền thực sự còn phù hợp.
