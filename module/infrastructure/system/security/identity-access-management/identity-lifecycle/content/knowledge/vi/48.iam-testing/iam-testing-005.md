# Kiểm thử provisioning trong vòng đời danh tính IAM

## 1. Provisioning là gì và vì sao phải kiểm thử?

**Provisioning** là quá trình biến quyết định quản lý danh tính thành tài khoản, thuộc tính, nhóm và quyền truy cập thực tế tại các hệ thống đích. Trong Identity and Access Management (IAM), quá trình này thường bắt đầu từ nguồn dữ liệu nhân sự (HRIS), hệ thống quản lý đối tác hoặc yêu cầu đã được phê duyệt, đi qua bộ điều phối IAM, Identity Provider (IdP), directory, giao thức SCIM và các connector ứng dụng. **Deprovisioning** là quá trình vô hiệu hóa tài khoản hoặc thu hồi quyền khi điều kiện được cấp không còn hợp lệ.

Trong mô hình **Joiner–Mover–Leaver (JML)**, provisioning không chỉ tạo tài khoản lúc Joiner: khi Mover, hệ thống phải cập nhật thuộc tính, thêm quyền mới và gỡ quyền cũ; khi Leaver, hệ thống phải chặn truy cập và thu hồi các entitlement liên quan. Kiểm thử provisioning vì vậy phải chứng minh cả **trạng thái mong muốn**, **thao tác đã thực thi** và **quyền có hiệu lực tại ứng dụng đích**.

Các kết quả quan trọng:

- Đúng danh tính: ánh xạ `personId` hoặc `externalId` ổn định, không nhầm người khi đổi email hay trùng tên.
- Đúng quyền: chỉ cấp entitlement thỏa RBAC/ABAC, approval, least privilege và Separation of Duties (SoD).
- Đúng thời điểm: tôn trọng ngày bắt đầu, thời gian chuyển vai trò, ngày chấm dứt và SLA đồng bộ.
- Đúng trạng thái cuối: quyền trong IdP và ứng dụng phản ánh yêu cầu mới nhất, kể cả khi có retry và sự kiện ngoài thứ tự.
- Có bằng chứng: truy vết yêu cầu, phê duyệt, quyết định chính sách, phản hồi connector, lỗi và đối soát.

Một workflow báo `SUCCESS` khi gửi xong lệnh HTTP nhưng ứng dụng chưa tạo tài khoản là lỗi kiểm thử. Ngược lại, provisioning nhầm người hoặc cấp thừa quyền cũng phải bị phát hiện dù API trả `201 Created`.

## 2. Kiến trúc và ranh giới hệ thống cần quan sát

~~~mermaid
flowchart LR
    H[HRIS / nguồn danh tính] --> E[Event / Request]
    E --> I[IAM Orchestrator]
    P[Policy RBAC / ABAC] --> I
    A[Approval / SoD] --> I
    I --> D[IdP / Directory]
    D --> S[SSO claims]
    I --> C[SCIM / API Connector]
    C --> T[Ứng dụng đích]
    D --> R[Reconciliation]
    T --> R
    R --> Q{Khớp desired state?}
    Q -->|Có| L[Audit hoàn tất]
    Q -->|Không| F[Alert / Retry / Remediation]
~~~

Phân biệt những ranh giới có ý nghĩa khi thiết kế test:

| Ranh giới | Đầu vào/đầu ra | Rủi ro cần kiểm thử |
|---|---|---|
| Nguồn → IAM | Người, trạng thái, version, effectiveAt | Thiếu dữ liệu, trùng ID, sai thời điểm |
| IAM → Policy | Vai trò, phòng ban, thuộc tính, exception | Tính quyền sai, SoD không được chặn |
| IAM → IdP | Account, nhóm, thuộc tính, trạng thái | Tạo nhầm tenant, group mapping sai |
| IAM → SCIM/API | Create, update, deactivate, membership | Lỗi một phần, timeout, rate limit |
| IdP → SSO → App | Subject, claim, token và session | Claim cũ, cache quyền, app vẫn cho phép |
| App → Readback | Trạng thái người dùng và quyền thực tế | Báo thành công giả, tồn dư quyền |
| Audit → Monitoring | Correlation ID, outcome, SLA | Lỗi không được cảnh báo hoặc không truy vết |

Hệ thống có thể xử lý theo queue và eventual consistency. Kiểm thử phải xác định deadline theo chính sách thay vì đòi tất cả đích cập nhật ngay trong cùng một transaction.

## 3. Xây dựng dữ liệu thử và trạng thái mong muốn

Dùng định danh giả trong môi trường kiểm thử. Một bộ dữ liệu provisioning tối thiểu nên có: người mới đúng điều kiện, người đổi vai trò, người nghỉ việc, nhà thầu có ngày hết hạn, người được cấp quyền đặc biệt, người có email thay đổi, tài khoản đã tồn tại, ứng dụng không hỗ trợ SCIM và connector đang lỗi.

Ví dụ yêu cầu:

~~~yaml
requestId: req-7001
eventId: join-7001-v1
version: 1
personId: test-person-7001
action: JOINER
effectiveAt: 2026-12-01T09:00:00+07:00
attributes:
  department: SALES
  region: VN
  workerType: EMPLOYEE
approvedEntitlements:
  - crm.customer.read.vn
  - sales.dashboard.read
targets:
  - idp
  - crm
  - analytics
~~~

Đây là schema minh họa, không phải hợp đồng API cố định. Mỗi testcase nên có ba ảnh chụp logic:

1. **Desired state:** trạng thái và quyền được phép theo policy/phê duyệt tại thời điểm hiệu lực.
2. **Reported state:** hệ thống IAM và connector tuyên bố đã thực thi những gì.
3. **Observed state:** tài khoản, nhóm, quyền trực tiếp và khả năng truy cập thực tế tại từng đích.

Điều kiện quan trọng là `observed effective grants == approved desired grants` tại thời điểm sau deadline hội tụ, có tính ngoại lệ và quyền được kế thừa hợp lệ. Trước deadline, trạng thái `PENDING` có thể hợp lệ; quá hạn mà vẫn không đúng phải báo lỗi.

## 4. Kiểm thử tạo tài khoản (Create / Joiner)

Đối với luồng tạo mới, xác minh:

- Yêu cầu chưa xác minh hoặc chưa có approval bắt buộc không dẫn tới tài khoản hoạt động với quyền truy cập.
- Tài khoản được tạo ở đúng tenant/organization và liên kết bằng khóa bất biến, không chỉ theo email.
- Username, name, `externalId`, manager, department và region được mapping chính xác sang ứng dụng.
- Nhóm hoặc role được cấp theo chính sách, không tự động có quyền quản trị mặc định.
- Quyền chưa tới ngày hiệu lực được xử lý theo chính sách (có thể chuẩn bị tài khoản trước nhưng chưa cho phép truy cập).
- Connector tạo user thành công nhưng bước thêm nhóm thất bại phải báo trạng thái không hoàn tất.
- Khi phát lại yêu cầu, không có thêm account thứ hai hoặc duplicate entitlement.

Ví dụ: nhân viên Sales tại VN phải xem được hồ sơ CRM vùng VN và bị từ chối khi truy cập CRM vùng khác, xuất toàn bộ dữ liệu hoặc phê duyệt thanh toán. Đăng nhập SSO thành công chỉ là một bằng chứng, cần thử API cho cả thao tác hợp lệ và bị cấm.

## 5. Kiểm thử cập nhật thuộc tính và quyền (Update / Mover)

Mover có thể đồng thời thay đổi `department`, `region`, `manager`, vai trò và thời hạn hợp đồng. Kiểm thử cả cập nhật một trường lẫn nhiều trường cùng lúc. Đầu tiên tính tập quyền trước/sau:

~~~text
before = {crm.read.vn, crm.export.limited, sales.dashboard}
desired_after = {finance.report.read, finance.dashboard}

to_add = desired_after - before
to_remove = before - desired_after

unexpected = actual_after - desired_after
missing = desired_after - actual_after

PASS khi unexpected và missing đều rỗng
~~~

Trong thực tế, quyền có thể đến từ nhiều nguồn: nhóm động, nhóm lồng nhau, RBAC, điều kiện ABAC hoặc quyền cấp trực tiếp ở ứng dụng. Kiểm thử cần bao phủ mọi đường dẫn đến **effective permissions**. Nếu người dùng chuyển vai trò nhưng token SSO vẫn mang claim cũ, phải kiểm tra khả năng truy cập qua session cũ trong SLA được phê duyệt.

Khi role mới tạo xung đột SoD, chẳng hạn có cả `payment.create` và `payment.approve`, hệ thống phải từ chối hoặc yêu cầu ngoại lệ được phê duyệt. Cần xác minh quy tắc đó tại policy engine và tại điểm thực thi ứng dụng.

## 6. Kiểm thử vô hiệu hóa và thu hồi (Deactivate / Leaver)

Luồng Leaver thường phải ngừng đăng nhập mới, vô hiệu tài khoản đích, gỡ entitlement và xử lý token/session. Phạm vi xác minh:

| Tầng | Phép thử | Điều kiện đạt |
|---|---|---|
| IdP | Đăng nhập mới sau Leaver | Bị từ chối theo SLA |
| SCIM | `active=false` và trạng thái account | Được readback đúng |
| Nhóm và role | Gỡ membership, direct grants | Không còn effective permission bị cấm |
| SSO | Cookie/session đã phát hành | Không tiếp tục truy cập ngoài deadline |
| Access/refresh token | Thử dùng lại token cũ | Tuân theo cơ chế revoke/expiry và SLA |
| Local account | Đăng nhập bỏ qua SSO | Bị chặn theo phạm vi thu hồi |
| API key / PAT / SSH key | Gọi API hoặc kết nối bằng credential cũ | Credential bị thu hồi/rotation phù hợp |
| Service account ownership | Chủ sở hữu cá nhân nghỉ việc | Có bàn giao, không còn quyền owner cũ |

Một access token JWT tự chứa có thể còn hợp lệ tới `exp` khi ứng dụng chỉ xác minh chữ ký. Kiểm thử phải phản ánh chính sách và kiến trúc thực tế; không mặc định disable IdP lập tức vô hiệu mọi token. Nếu không thể revoke sớm, hệ thống cần đánh giá thời hạn sống token, điều kiện chặn tại ứng dụng và rủi ro tồn dư.

## 7. Kiểm thử giao thức SCIM 2.0

SCIM thường cung cấp tài nguyên `Users`, `Groups` và các thao tác tạo, đọc, sửa, tìm kiếm, thay đổi membership. Ví dụ tạo tài khoản:

~~~http
POST /scim/v2/Users
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "externalId": "test-person-7001",
  "userName": "test7001@example.test",
  "active": true,
  "name": {"givenName": "An", "familyName": "Nguyen"}
}
~~~

Ví dụ vô hiệu hóa tài khoản:

~~~http
PATCH /scim/v2/Users/user-7001
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {"op": "replace", "path": "active", "value": false}
  ]
}
~~~

Đây là ví dụ minh họa, cần điều chỉnh theo schema, cách định danh và khả năng PATCH của SCIM server. Không suy rằng phản hồi thành công đảm bảo ứng dụng đã hủy session; phải GET/readback và thử truy cập.

Nhóm ca kiểm thử SCIM quan trọng:

1. Create user mới, GET đúng id/attributes, gán group và readback.
2. Update chỉ một thuộc tính và kiểm tra các thuộc tính còn lại không bị ghi đè ngoài ý muốn.
3. PATCH group thêm/gỡ thành viên, kiểm tra tránh member trùng.
4. Deactivate user, xác minh ứng dụng chặn truy cập tương ứng.
5. Search/filter/pagination trả đúng user; mapping `externalId` không lệch người.
6. Retry sau timeout khi server đã tạo tài khoản: client phải lookup trước khi cố tạo thêm, xử lý `409 Conflict` phù hợp.
7. `429 Too Many Requests`, `5xx`, mất kết nối: backoff có giới hạn, ghi nhận lỗi khi hết retry.
8. `404 Not Found`: kiểm tra liệu tài khoản đã bị xóa hợp lệ hay mapping bị lỗi; không tự kết luận deprovision thành công nếu chưa xác minh quyền thực tế.

## 8. Idempotency, thứ tự sự kiện và trạng thái cuối

Provisioning thường nhận webhook hoặc event từ hệ thống upstream. Nguồn có thể gửi trùng, event đến không theo thứ tự hoặc consumer bị restart. Mỗi yêu cầu nên có ID ổn định và phiên bản/sequence đáng tin cậy để tránh phục hồi quyền cũ.

~~~text
v10 JOINER: SALES
v11 MOVER: SALES -> FINANCE
v12 LEAVER: TERMINATED

Queue nhận theo thứ tự: v10, v12, v11
Kỳ vọng cuối: TERMINATED; không phục hồi quyền FINANCE từ v11.
~~~

Kiểm thử **idempotency** không chỉ đếm số user; còn phải kiểm tra role/group membership, audit và các side effect như lời mời email, yêu cầu phê duyệt hoặc ticket. Một event được xử lý lại có thể phát sinh log bổ sung nhưng không được tạo grant hay identity dư.

Khi phát hiện event stale, processor cần bỏ qua hoặc tái tính theo trạng thái nguồn mới nhất. Test phải xác minh kết quả cuối tại ứng dụng chứ không chỉ trạng thái hàng đợi.

## 9. Lỗi từng phần, retry và compensation

Giả sử IdP tạo account thành công nhưng CRM trả `500`. IAM cần ghi được trạng thái mỗi target, retry an toàn hoặc tạo yêu cầu khắc phục. Nếu rollback được áp dụng, phải kiểm tra rollback không làm mất các quyền hợp lệ đã tồn tại từ trước.

~~~mermaid
sequenceDiagram
    participant H as HRIS
    participant I as IAM
    participant D as IdP
    participant A as CRM qua SCIM
    H->>I: JOINER v1
    I->>D: Create identity
    D-->>I: Success
    I->>A: Create user
    A--xI: Timeout
    I->>A: Lookup by externalId
    A-->>I: User exists, missing group
    I->>A: Reconcile desired groups
    A-->>I: Success
    I->>A: Readback and authorization test
    A-->>I: Expected grants
~~~

Các lỗi cần thử gồm mất phản hồi sau khi server đã xử lý, rate limit, connector mất mạng, hàng đợi bị nghẽn, dead-letter queue, sự kiện trùng, dữ liệu mapping sai, xung đột cập nhật đồng thời và hệ thống đích chỉ hỗ trợ thao tác thủ công. Kiểm thử phải xác minh:

- Retry có backoff, giới hạn và không bỏ qua phê duyệt.
- Trạng thái `PENDING`, `PARTIAL_FAILURE`, `FAILED` hay tương đương hiển thị trung thực.
- Có cảnh báo và owner xử lý khi quá SLA hoặc hết ngân sách retry.
- Reconciliation đưa trạng thái cuối về đúng policy; không tự cấp quyền bị cấm khi replay.
- Nếu có compensation, hành động bù trừ không vô tình thu hồi entitlement độc lập đang hợp lệ.

## 10. Ma trận test case provisioning

| ID | Tình huống | Kỳ vọng | Ưu tiên |
|---|---|---|---|
| P01 | Joiner hợp lệ và đủ approval | Tạo user và đúng grant | Rất cao |
| P02 | Joiner chưa xác minh | Không cấp quyền hoạt động | Rất cao |
| P03 | Tạo user với email trùng | Không liên kết nhầm danh tính | Rất cao |
| P04 | Event Create gửi lặp | Một account logic, không duplicate grant | Rất cao |
| P05 | Mover đổi vai trò | Cấp quyền mới, gỡ quyền cũ | Rất cao |
| P06 | Thuộc tính ABAC đổi | Không còn truy cập vượt region/department | Rất cao |
| P07 | Role tạo xung đột SoD | Từ chối hoặc yêu cầu ngoại lệ duyệt | Rất cao |
| P08 | Leaver có hiệu lực | Chặn login, deactivate và revoke trong SLA | Rất cao |
| P09 | Token/session cũ còn tồn tại | Hết quyền theo chính sách revoke/expiry | Rất cao |
| P10 | Timeout sau khi server đã tạo user | Lookup và reconcile, không tạo bản sao | Cao |
| P11 | Một ứng dụng lỗi | Báo partial failure và khắc phục | Cao |
| P12 | Event ngoài thứ tự | Không khôi phục trạng thái lỗi thời | Rất cao |
| P13 | Group lồng nhau còn quyền | Phát hiện grant tồn dư | Rất cao |
| P14 | Connector không hỗ trợ SCIM | Xác minh qua API/ticket và access test | Cao |
| P15 | Owner service account thay đổi | Bàn giao owner và secret đúng chính sách | Cao |
| P16 | Reconciliation thấy quyền thừa | Tạo finding, sửa và đọc lại | Rất cao |

Mỗi testcase cần ghi `caseId`, trạng thái ban đầu, request/event, policy version, trạng thái kỳ vọng, target systems, timeout/SLA, actual result, evidence và remediation. Với những quyền nhạy cảm, đặt trọng tâm vào **negative assertion**: người dùng không được làm những hành động đã bị cấm.

## 11. Ví dụ tự động hóa kiểm thử end-to-end

Mã giả Python dùng client thử nghiệm và hàm `eventually` để chờ hội tụ. Những abstraction này phải do test harness cung cấp:

~~~python
def test_provisioning_joiner_idempotent(hris, idp, crm, iam, policy):
    person_id = "test-person-7001"
    event = {
        "eventId": "join-7001-v1",
        "version": 1,
        "type": "JOINER",
        "personId": person_id,
        "verified": True,
        "approved": True,
        "department": "SALES",
        "region": "VN",
        "effectiveAt": policy.test_effective_at,
    }
    hris.publish(event)

    eventually(
        lambda: idp.count_by_external_id(person_id) == 1,
        timeout_seconds=policy.provisioning_sla_seconds,
    )
    expected = {"crm.customer.read.vn", "sales.dashboard.read"}
    eventually(
        lambda: crm.effective_permissions(person_id) == expected,
        timeout_seconds=policy.provisioning_sla_seconds,
    )
    assert crm.authorize(person_id, "crm.customer.read.vn") == "ALLOW"
    assert crm.authorize(person_id, "crm.export.all") == "DENY"

    hris.publish(event)  # Replay cùng event.
    eventually(
        lambda: idp.count_by_external_id(person_id) == 1,
        timeout_seconds=policy.provisioning_sla_seconds,
    )
    assert iam.audit_contains(event_id=event["eventId"])
~~~

Ngoài kết quả trên, cần viết test tương đương cho Mover (đối chiếu tập quyền trước/sau) và Leaver (kiểm login mới, quyền đích, session và credentials cũ). Hàm `authorize` cần kiểm qua điểm thực thi hoặc API thật; một mock chỉ thể hiện tính toán chính sách chưa chứng minh quyền tại ứng dụng.

## 12. Kiểm thử tài khoản dịch vụ, secret và quyền sở hữu

Không phải mọi principal đều là nhân sự HRIS. Service account hoặc machine identity cần nguồn quản lý owner riêng, mục đích, entitlement, quy trình phê duyệt, thời hạn rà soát và chính sách luân chuyển secret. Khi owner chuyển vai trò hoặc nghỉ việc, kiểm thử rằng:

1. Owner mới được gán hợp lệ, tránh orphaned service principal.
2. Người cũ không còn xem hoặc quản lý secret, khóa API hay quyền triển khai.
3. Quyền của bot được giữ đúng nhu cầu nghiệp vụ; không tự xóa tài khoản dịch vụ đang chạy công việc quan trọng.
4. Rotation credential được thực hiện nếu chính sách yêu cầu; consumer hợp lệ tiếp tục hoạt động và khóa cũ bị từ chối.
5. Quyền máy không bị vô tình cấp cho danh tính người dùng chỉ vì cùng nhóm tổ chức.

## 13. Audit, reconciliation và tiêu chí chấp nhận

Với mỗi lệnh provisioning, gom bằng chứng từ **intent** (nguồn yêu cầu, phê duyệt, policy), **execution** (hành động, connector, retry) và **observed state** (readback tại IdP/ứng dụng, kết quả authorization). Correlation ID giúp liên kết các bước bất đồng bộ; log phải tránh lưu mật khẩu, access token, private key và dữ liệu cá nhân không cần thiết.

Đối soát có thể tính:

~~~text
expected = policy.calculate(sourceIdentities, approvedExceptions)
actual = inventory.effectiveAccess(idp, directories, applications)

unexpected = actual.grants - expected.grants
missing = expected.requiredGrants - actual.grants
orphanAccounts = actual.activeAccounts - expected.activeAccounts
~~~

Đối với sai lệch, tạo finding/ticket có owner, mức độ ưu tiên, deadline và readback sau sửa. Cần phân biệt tài khoản đã khóa nhưng còn dữ liệu cần giữ với tài khoản thực sự còn truy cập; không tự động xóa dữ liệu lưu trữ vì không xuất hiện trong danh sách active HRIS.

Một bộ kiểm thử provisioning được chấp nhận khi bao phủ đủ create/update/deactivate, quyền và thuộc tính, ứng dụng quan trọng, lỗi tích hợp, retry/idempotency, xử lý event ngoài thứ tự, token/session, account cục bộ, service identity và reconciliation. Kết luận PASS phải dựa vào **quyền có hiệu lực đúng chính sách tại các hệ thống đích trong SLA**, không chỉ mã trạng thái HTTP.

## 14. Bài thực hành tổng hợp

Giả lập một nhân viên `test-person-7001` thuộc Sales VN, sau đó chuyển sang Finance và cuối cùng rời công ty. Hệ thống gồm HRIS, IdP, CRM hỗ trợ SCIM và công cụ báo cáo dùng API riêng. Hãy xây dựng ba event Joiner v1, Mover v2 và Leaver v3, sau đó thực hiện:

1. Joiner: tạo đúng identity, cấp quyền CRM VN và từ chối xuất dữ liệu.
2. Mover: cấp quyền Finance, gỡ quyền CRM; kiểm tra cả role cục bộ và claim token cũ.
3. Leaver: chặn login mới, gỡ grants, thử lại bằng session, token và API key cũ.
4. Gửi sự kiện v2 sau khi v3 hoàn tất; khẳng định quyền Finance không được hồi sinh.
5. Gây timeout SCIM sau thao tác thành công; xác minh retry và reconciliation.
6. Tắt connector ứng dụng báo cáo; kiểm tra partial failure, cảnh báo, xử lý và readback.
7. Xuất báo cáo theo `caseId, desired, observed, timestamp, deadline, evidence, outcome, remediation`.

Điểm cần đạt là chứng minh **đúng người, đúng tài khoản, đúng quyền, đúng thời điểm và không có quyền tồn dư sau thay đổi trạng thái**, với bằng chứng ở chính ứng dụng thực thi quyền.
