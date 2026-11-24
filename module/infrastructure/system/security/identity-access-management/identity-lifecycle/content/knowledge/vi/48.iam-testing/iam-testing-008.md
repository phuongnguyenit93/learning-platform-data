# Test authorization policy trong vòng đời danh tính IAM

## 1. Mục tiêu và phạm vi

**Authorization policy** là tập quy tắc quyết định một chủ thể đã được nhận diện có thể thực hiện **hành động nào trên tài nguyên nào, trong ngữ cảnh nào**. Authentication (AuthN) xác minh danh tính; authorization (AuthZ) áp dụng quyền. Người dùng đăng nhập SSO thành công vẫn phải bị từ chối khi gọi API nằm ngoài entitlement đã được duyệt.

Trong chương **IAM testing** của module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`, kiểm thử authorization phải theo sát vòng đời **Joiner–Mover–Leaver (JML)**. Joiner nhận quyền tối thiểu theo vai trò; Mover bổ sung quyền mới và thu hồi quyền cũ; Leaver mất quyền truy cập khi không còn quan hệ hợp lệ. Việc cập nhật qua HRIS, IAM, IdP, SCIM và ứng dụng có thể bị trễ hoặc lỗi một phần. Do đó, kiểm thử cần quan sát **quyết định policy** và **quyền có hiệu lực tại điểm thực thi**.

Mục tiêu kiểm thử bao gồm:

1. Chủ thể, hành động, tài nguyên và ngữ cảnh được đánh giá theo đúng phiên bản chính sách.
2. Những quyền được phê duyệt được cho phép; những quyền không được phê duyệt bị từ chối.
3. RBAC, ABAC, quyền trực tiếp, quyền kế thừa, ngoại lệ và Separation of Duties (SoD) được xử lý nhất quán.
4. Thay đổi trạng thái JML được phản ánh tại mọi ứng dụng trong SLA.
5. Không còn quyền truy cập tồn dư từ nhóm lồng nhau, phiên cũ, token cũ hoặc ACL nằm ngoài IdP.
6. Mỗi quyết định có bằng chứng kiểm toán đủ để giải thích, đối soát và khắc phục sai lệch.

## 2. Mô hình quyết định quyền: subject, action, resource, context

Một yêu cầu kiểm tra quyền có thể mô tả bằng bốn thành phần:

~~~json
{
  "subject": {
    "personId": "test-person-720",
    "employmentStatus": "ACTIVE",
    "department": "SALES",
    "region": "VN",
    "roles": ["sales-reader"]
  },
  "action": "customer.read",
  "resource": {
    "type": "crm-customer",
    "id": "test-customer-31",
    "region": "VN",
    "ownerGroup": "sales-vn"
  },
  "context": {
    "time": "2026-12-03T10:00:00+07:00",
    "deviceTrusted": true
  }
}
~~~

Đây là dữ liệu minh họa, không phải schema cố định. Một hệ thống dùng **RBAC** thường ánh xạ `roles` sang tập hành động được phép. Hệ thống **ABAC** còn so sánh thuộc tính chủ thể, tài nguyên và ngữ cảnh, chẳng hạn chỉ cho người thuộc vùng VN đọc dữ liệu khách hàng VN. Cả hai có thể kết hợp.

**Policy Decision Point (PDP)** đưa ra quyết định (ALLOW/DENY hoặc kết quả đặc thù); **Policy Enforcement Point (PEP)** thực sự chặn hoặc cho phép request; **Policy Information Point (PIP)** cung cấp thuộc tính cần thiết. Khi dùng bộ nhớ đệm, thời điểm PDP quyết định và thời điểm PEP áp dụng có thể khác nhau.

~~~mermaid
flowchart LR
    U[Client đã xác thực] --> E[PEP: API Gateway / Service]
    E --> D[PDP: Evaluate policy]
    I[PIP: HRIS / IdP / Attributes] --> D
    P[Policy & approved exceptions] --> D
    D -->|ALLOW| E
    D -->|DENY| E
    E --> R[Protected Resource]
    E --> L[Audit decision + enforcement]
~~~

Kiểm thử phải kiểm tra **hai lớp riêng**: PDP trả đúng kết quả mong đợi và PEP thực thi đúng kết quả đó. PDP trả DENY nhưng API vẫn trả dữ liệu là lỗi nghiêm trọng, dù log IAM có vẻ đúng.

## 3. Xây dựng policy oracle độc lập

**Test oracle** là cách tính kết quả kỳ vọng mà không chỉ sao chép kết quả từ chính hệ thống cần kiểm thử. Trước tiên lấy baseline policy đã được phê duyệt: roles, permissions, điều kiện ABAC, thứ tự ưu tiên deny/allow, ngoại lệ, thời điểm hiệu lực và cách giải quyết xung đột.

Ví dụ policy minh họa:

| Điều kiện | Kỳ vọng |
|---|---|
| Nhân viên Sales VN đọc CRM vùng VN | ALLOW |
| Nhân viên Sales VN đọc CRM vùng khác | DENY |
| Sales xuất toàn bộ dữ liệu khách hàng | DENY |
| Finance đọc báo cáo thuộc nhiệm vụ được duyệt | ALLOW |
| Chủ thể có `employmentStatus=TERMINATED` | DENY với truy cập tương tác |
| Role quản trị chưa được phê duyệt | DENY quyền quản trị |
| Thuộc tính phân quyền bắt buộc bị thiếu | DENY theo chính sách fail-closed |
| Ngoại lệ có phê duyệt và còn hạn | ALLOW trong phạm vi ngoại lệ |
| Ngoại lệ hết hạn | DENY phần quyền chỉ được cấp nhờ ngoại lệ |

Mô hình oracle đơn giản:

~~~text
expected(subject, action, resource, context):
    if lifecycleStatus(subject) not in allowedStates:
        return DENY
    if anyApplicableExplicitDeny(subject, action, resource, context):
        return DENY
    if approvedGrantApplies(subject, action, resource, context):
        return ALLOW
    return DENY
~~~

Thứ tự trên là **ví dụ chính sách deny-overrides**, không phải quy chuẩn cho mọi policy engine. Nếu sản phẩm dùng quy tắc kết hợp khác, oracle phải phản ánh cấu hình đã duyệt. Cần phân biệt **không có quyền** với **lỗi tra cứu thuộc tính**: hệ thống thường phải từ chối an toàn khi thiếu dữ liệu phân quyền trọng yếu, đồng thời ghi nhận sự cố thay vì im lặng cho phép.

## 4. Thiết kế dữ liệu thử và ma trận truy cập

Tạo các danh tính thử: Joiner chưa có hiệu lực, nhân viên active, người đổi phòng ban, người bị đình chỉ, Leaver, người có quyền đặc biệt, nhà thầu sắp hết hạn và service principal. Tạo tài nguyên có chủ sở hữu, vùng dữ liệu và mức độ nhạy cảm khác nhau. Các tài nguyên phải có dữ liệu thử để xác minh API không trả thông tin trái phép.

| Chủ thể | Hành động | Tài nguyên | Kết quả kỳ vọng |
|---|---|---|---|
| Sales VN active | `customer.read` | Customer VN | ALLOW |
| Sales VN active | `customer.read` | Customer SG | DENY |
| Sales VN active | `customer.export.all` | CRM | DENY |
| Finance active | `report.read` | Finance report đúng phạm vi | ALLOW |
| Finance active | `iam.role.admin` | IAM role | DENY |
| Sales chưa đến ngày bắt đầu | `customer.read` | Customer VN | DENY |
| Leaver | `customer.read` | Customer VN | DENY |
| Service principal chỉ đọc báo cáo | `report.delete` | Finance report | DENY |

Để tránh chỉ kiểm thử “happy path”, mỗi ca ALLOW nên có ca đối ứng DENY. Với ứng dụng đa tenant, phải thử cùng ID tài nguyên thuộc tenant khác để phát hiện **Broken Object Level Authorization (BOLA)**. Với API có trường nhạy cảm, kiểm tra **quyền trên thuộc tính/field** và hành động ghi, không chỉ kiểm HTTP GET.

## 5. Kiểm thử RBAC: role, inheritance và quyền trực tiếp

RBAC có thể cấp quyền qua role trực tiếp, group mapping, role kế thừa hoặc nhóm lồng nhau. Kiểm thử:

- Role được phê duyệt có đúng tập quyền và không vô tình chứa quyền quản trị.
- Người dùng có nhiều role nhận hợp quyền theo thuật toán policy thực tế.
- Group lồng nhau hoặc role kế thừa không tạo quyền vượt phạm vi.
- Thu hồi role trực tiếp không đủ nếu quyền còn tồn tại qua group khác.
- Cập nhật mapping tại IdP/SCIM thực sự thay đổi quyền tại ứng dụng.
- Quyền được gán trực tiếp trong ứng dụng được phát hiện và quản lý như một nguồn entitlement riêng.

Ví dụ user `test-person-720` bị gỡ khỏi `sales-admin` tại IdP nhưng còn quyền `crm.export.all` qua một role local. Test kiểm membership IdP có thể PASS, trong khi test API export phải FAIL và phát hiện quyền tồn dư.

Nên đối chiếu **effective grants** với **approved grants**:

~~~text
actual = resolveDirectAndInheritedGrants(subject, applications)
expected = approvedPermissions(subject, policyVersion, effectiveTime)
unexpected = actual - expected
missing = expected - actual
PASS khi unexpected = {} và missing = {}
~~~

Tập `actual` phải bao gồm cả quyền đặc thù ứng dụng và đường cấp quyền gián tiếp, không chỉ danh sách group tại IdP.

## 6. Kiểm thử ABAC: thuộc tính, ranh giới dữ liệu và thời gian

ABAC sử dụng thuộc tính của subject, resource, action và environment. Với mỗi thuộc tính có ảnh hưởng quyết định, tạo lớp tương đương và giá trị biên:

| Thuộc tính | Ca đúng | Ca âm tính/biên |
|---|---|---|
| `region` | Subject và resource đều VN | Khác vùng, null, chuỗi không hợp lệ |
| `department` | Bộ phận phù hợp quyền | Bộ phận cũ, sai mã |
| `contractEndAt` | Trước hạn | Đúng tại hạn và sau hạn |
| `classification` | Đúng mức truy cập | Tài nguyên nhạy cảm hơn mức cho phép |
| `deviceTrusted` | Thiết bị đủ điều kiện | False, thiếu hoặc giá trị chưa xác minh |
| `projectId` | Cùng dự án đã duyệt | Tài nguyên thuộc dự án khác |

Kiểm tra múi giờ, so sánh đúng tại `effectiveAt`, và các thay đổi sát thời điểm policy refresh. Nếu ABAC phụ thuộc token claim, session đã cấp trước Mover có thể chứa `region=VN` dù HRIS đã chuyển sang vùng khác. Test cần xác minh PEP không chấp nhận quyền cũ quá SLA được định nghĩa.

**Không tin thuộc tính do client tự gửi** nếu server không xác thực được. Ví dụ request body chứa `department=FINANCE` không được phép tự nâng quyền. Test thay đổi claim/header không đáng tin cậy và kiểm tra quyết định vẫn dựa trên nguồn thuộc tính đã được xác minh.

## 7. Kiểm thử Separation of Duties và đặc quyền tạm thời

**Separation of Duties (SoD)** ngăn một chủ thể sở hữu hoặc sử dụng các quyền xung đột, ví dụ đồng thời tạo và phê duyệt cùng khoản thanh toán khi chính sách cấm. Kiểm thử ở hai cấp:

1. **Static SoD:** khi gán role, IAM phát hiện xung đột và từ chối hoặc yêu cầu phê duyệt ngoại lệ.
2. **Dynamic SoD:** khi thực hiện giao dịch, PEP kiểm tra điều kiện như người tạo không được là người duyệt cùng giao dịch, kể cả khi cả hai vai trò được cấp hợp lệ.

Một ngoại lệ tạm thời phải có actor phê duyệt, lý do, phạm vi, thời hạn và dấu vết; test cần chứng minh ngoại lệ chỉ có hiệu lực trong phạm vi và hết hạn đúng lúc. Với quyền quản trị đặc biệt (privileged access), kiểm tra quyền thực tế ở console/API sau khi phê duyệt, sau khi hết hạn và khi chủ thể đổi vai trò.

## 8. JML: các thay đổi quyền và thứ tự sự kiện

### Joiner

Người mới có thể được tạo account trước ngày hiệu lực nhưng chưa có quyền sử dụng. Sau khi xác minh và phê duyệt, cấp tập quyền tối thiểu theo role và thuộc tính. Test phải kiểm quyền đủ dùng và quyền ngoài phạm vi bị từ chối.

### Mover

Người dùng chuyển Sales sang Finance: kỳ vọng quyền Finance được thêm, quyền Sales không còn hợp lệ bị gỡ. Kiểm tra quyền trực tiếp, nested groups, ABAC cache, token chứa claim cũ và khả năng truy cập API trong giai đoạn chuyển tiếp. Nếu có khoảng thời gian cần giữ quyền cũ, chỉ cho phép khi policy/ngoại lệ nêu rõ.

### Leaver

Khi Leaver có hiệu lực, chặn quyền tương tác và xử lý quyền ứng dụng, phiên và credentials trong SLA. Không chỉ dựa vào `active=false` tại SCIM; dùng session/token trước thời điểm Leaver thử truy cập tài nguyên thật.

### Sự kiện trùng hoặc ngoài thứ tự

~~~text
v10 JOINER: SALES
v11 MOVER: FINANCE
v12 LEAVER: TERMINATED

Thứ tự nhận: v10, v12, v11
Kỳ vọng cuối: TERMINATED; event v11 đến muộn không cấp lại FINANCE.
~~~

Hệ thống cần cơ chế version hoặc đối chiếu nguồn tin cậy trước khi phục hồi quyền. Test replay cùng sự kiện không được tạo grant trùng hoặc thêm quyền ngoài ý muốn.

## 9. Kiểm thử policy ở IdP, SSO, SCIM và ứng dụng

IdP/Directory thường cung cấp group, role và thuộc tính; SCIM đồng bộ chúng sang ứng dụng; SSO truyền identity/claim trong phiên. PEP tại ứng dụng có thể dùng claim token hoặc truy vấn quyền thời gian thực.

Các kiểm tra cần thực hiện:

1. **Policy engine:** PDP trả đúng quyết định cho request được xây dựng từ dữ liệu chính sách.
2. **IdP mapping:** group, role, claims và các thuộc tính quan trọng khớp source of truth.
3. **SCIM provisioning:** cập nhật nhóm/thu hồi quyền được ứng dụng nhận và readback chính xác.
4. **Token/session:** claim cũ không dẫn tới quyền quá hạn; timeout, refresh và revoke được xử lý theo thiết kế.
5. **API enforcement:** request ALLOW thực sự thành công, request DENY không trả dữ liệu và không thay đổi tài nguyên.
6. **Local grants:** tài khoản có role cục bộ không tạo đường vòng ngoài policy trung tâm.
7. **Failure behavior:** khi policy engine hoặc PIP lỗi, ứng dụng xử lý theo chế độ đã duyệt và không vô tình fail-open đối với tài nguyên nhạy cảm.

Với API trả `401 Unauthorized` khi chưa xác thực hoặc `403 Forbidden` khi thiếu quyền, cần phân biệt lớp gây lỗi. Test không nên chỉ kiểm mã HTTP: phải xác minh dữ liệu nhạy cảm không bị lộ và thao tác ghi không có side effect.

## 10. Ma trận testcase authorization

| ID | Tình huống | Kỳ vọng | Ưu tiên |
|---|---|---|---|
| Z01 | Role hợp lệ truy cập tài nguyên đúng phạm vi | ALLOW | Cao |
| Z02 | Role thiếu quyền gọi thao tác nhạy cảm | DENY | Rất cao |
| Z03 | Thay đổi resource ID sang tenant khác | DENY, không lộ dữ liệu | Rất cao |
| Z04 | Nhóm lồng nhau cấp quyền ngoài dự kiến | Phát hiện entitlement thừa | Rất cao |
| Z05 | Claim/attribute bị thiếu hoặc sai kiểu | Quyết định an toàn theo policy | Cao |
| Z06 | ABAC chuyển vùng | Không còn truy cập vùng cũ sau SLA | Rất cao |
| Z07 | Joiner chưa hiệu lực | Không cấp quyền truy cập | Rất cao |
| Z08 | Mover đổi role | Thêm quyền mới, thu hồi quyền cũ | Rất cao |
| Z09 | Leaver với phiên/token cũ | Không còn truy cập ngoài deadline | Rất cao |
| Z10 | SoD tĩnh hoặc động bị vi phạm | DENY hoặc ngoại lệ có duyệt | Rất cao |
| Z11 | Ngoại lệ đặc quyền hết hạn | DENY ngoài thời gian cho phép | Rất cao |
| Z12 | SCIM cập nhật thất bại một đích | Partial failure, alert, reconciliation | Cao |
| Z13 | Event cũ đến sau Leaver | Không kích hoạt lại grant | Rất cao |
| Z14 | Quyền local còn sau gỡ IdP group | Phát hiện quyền tồn dư ở API | Rất cao |
| Z15 | PIP/PDP không sẵn sàng | Xử lý theo policy lỗi, không bypass | Rất cao |
| Z16 | Service principal gọi API vượt scope | DENY | Cao |

Ngoài quyết định ALLOW/DENY, test cần xác nhận đúng phiên bản chính sách, đúng tài nguyên, thời điểm, kết quả truy cập và audit correlation ID.

## 11. Tự động hóa kiểm thử end-to-end

Mã giả Python minh họa kiểm thử policy và enforcement. Các client, `eventually` và policy là abstraction của test harness, không phải API chuẩn:

~~~python
def test_authorization_after_mover(hris, iam, crm, finance, policy):
    person_id = "test-person-720"
    event = {
        "eventId": "mover-720-v18",
        "personId": person_id,
        "type": "MOVER",
        "version": 18,
        "department": "FINANCE",
        "approved": True,
        "effectiveAt": policy.test_effective_at,
    }
    hris.publish(event)

    eventually(
        lambda: finance.request_as(person_id, "report.read").allowed,
        timeout_seconds=policy.grant_sla_seconds,
    )
    eventually(
        lambda: crm.request_as(person_id, "customer.read.vn").denied,
        timeout_seconds=policy.revoke_sla_seconds,
    )
    assert crm.request_as(person_id, "customer.export.all").denied
    assert iam.audit_contains(event_id=event["eventId"])

    hris.publish(event)
    assert iam.identity_count(person_id) == 1
~~~

Để kiểm tra quyền tồn dư do session, test cần giữ một token/phiên đã phát trước Mover rồi gọi lại chính API bị cấm. Với resource ID, nên thử cả ID hợp lệ được phép và ID thuộc người khác/tenant khác. Không dùng mock policy để thay thế kiểm thử PEP thực tế.

## 12. Audit, reconciliation và điều kiện hoàn thành

Mỗi kết quả kiểm thử authorization phải truy vết được:

- **Intent:** chính sách, role/attribute, ngoại lệ, phê duyệt và sự kiện JML.
- **Decision:** PDP đã quyết định thế nào và vì sao, phiên bản policy và điều kiện liên quan.
- **Execution:** IdP/SCIM update, API enforcement, kết quả thực thi và lỗi đồng bộ.
- **Observation:** quyền có hiệu lực, thử truy cập ALLOW/DENY, thời điểm hội tụ và mức độ lệch SLA.
- **Remediation:** finding về quyền tồn dư, người phụ trách, hành động sửa và kết quả readback.

Không ghi nguyên văn access token, mật khẩu, private key hoặc thông tin cá nhân không cần thiết vào log. Với lỗi authorization, thông báo API nên tránh tiết lộ sự tồn tại của tài nguyên không được phép, tùy thiết kế bảo mật.

Bộ kiểm thử đạt khi các quyết định và enforcement cùng phản ánh policy, có cả ca dương/âm, kiểm soát được JML trong SLA, phát hiện quyền thừa từ các hệ thống đích và có chứng cứ audit. Không coi một bản ghi group trong IAM là bằng chứng đủ cho việc quyền tại ứng dụng đã bị thu hồi.

## 13. Bài thực hành

Giả lập nhân viên `test-person-720` thuộc Sales VN có quyền đọc CRM VN; sau đó chuyển Finance và nghỉ việc. Hệ thống gồm HRIS, IdP, CRM hỗ trợ SCIM và ứng dụng Finance.

1. Viết policy matrix cho `customer.read`, `customer.export.all`, `finance.report.read` và `finance.payment.approve`.
2. Tạo testcase RBAC/ABAC với tài nguyên cùng vùng, khác vùng, thuộc tenant khác, attribute thiếu và role không được duyệt.
3. Kiểm thử Joiner chưa có hiệu lực, rồi Joiner active; ghi kết quả ALLOW/DENY.
4. Gửi sự kiện Mover, đo thời điểm quyền Finance được cấp và CRM bị thu hồi.
5. Giữ một quyền CRM trực tiếp và một session cũ để chứng minh reconciliation và API test phát hiện quyền tồn dư.
6. Gửi Leaver và sau đó replay Mover cũ; xác minh quyền Finance không được khôi phục.
7. Xuất bảng `caseId, subject, action, resource, context, policyVersion, expected, actual, observedAt, evidence, outcome`.

Mỗi sai lệch phải gắn với tầng nguồn dữ liệu, policy decision, provisioning hay enforcement để xử lý đúng nguyên nhân. Giá trị của **test authorization policy** nằm ở khả năng chứng minh **đúng người được phép đúng hành động trên đúng tài nguyên, trong đúng điều kiện và đúng giai đoạn vòng đời**, đồng thời ngăn quyền truy cập tồn dư.
