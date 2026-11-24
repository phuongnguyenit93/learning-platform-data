# Kiểm thử Joiner trong vòng đời danh tính IAM

## 1. Mục tiêu

**Joiner** là giai đoạn một cá nhân bắt đầu có quan hệ hợp lệ với tổ chức: nhân viên mới, nhà thầu, thực tập sinh hoặc đối tác. Kiểm thử Joiner xác minh chuỗi **xác thực nguồn danh tính → tạo identity → phê duyệt → cấp tài khoản → gán quyền → kiểm tra truy cập → kiểm toán**. Mục tiêu là giúp đúng người có đủ quyền đúng thời điểm, đồng thời không mở đường truy cập ngoài phạm vi đã duyệt.

Trong quản lý vòng đời danh tính IAM, Joiner phải kết nối nguồn HRIS hoặc hệ thống quản lý nhà thầu, IAM, IdP, SSO, SCIM, RBAC/ABAC và các ứng dụng đích. Một phản hồi tạo tài khoản thành công tại IdP chưa đủ chứng minh người dùng có quyền phù hợp ở ứng dụng. Ngược lại, cấp thừa quyền dù đăng nhập hoạt động bình thường vẫn là lỗi bảo mật nghiêm trọng.

Yêu cầu kiểm thử gồm:

- **Identity integrity:** một cá nhân gắn với một định danh ổn định, tránh gắn nhầm người do trùng tên hoặc email.
- **Eligibility:** chỉ cấp quyền khi điều kiện xác minh, trạng thái hợp đồng, thời điểm hiệu lực và phê duyệt thỏa mãn.
- **Least privilege:** entitlement đúng vai trò và thuộc tính, không mở quyền mặc định ngoài chính sách.
- **End-to-end provisioning:** IdP và mọi ứng dụng nhận trạng thái đúng, kể cả khi đồng bộ bất đồng bộ hoặc gặp lỗi.
- **Auditability:** có chứng cứ cho yêu cầu, người duyệt, hành động, retry, kết quả và trạng thái thực tế.

## 2. Luồng Joiner và các điểm kiểm tra

~~~mermaid
flowchart TD
    H[HRIS / nguồn danh tính] --> V[Xác minh và ngày hiệu lực]
    V --> I[Tạo identity ID ổn định]
    I --> P[Tính quyền RBAC / ABAC]
    P --> A{Cần phê duyệt?}
    A -->|Có| G[Chờ quyết định]
    A -->|Không| D[Provision IdP]
    G -->|Đồng ý| D
    G -->|Từ chối| X[Không cấp quyền]
    D --> S[SSO / SCIM / ứng dụng]
    S --> R[Readback tài khoản và quyền]
    R --> T[Thử ALLOW và DENY]
    T --> L[Audit / reconciliation]
~~~

| Bước | Dữ liệu cần quan sát | Điều kiện đạt |
|---|---|---|
| Nhận sự kiện | Person ID, event ID, version, effectiveAt | Sự kiện hợp lệ, đúng chủ thể |
| Xác minh | Trạng thái HR/nhà thầu, danh tính | Người chưa đủ điều kiện không có quyền |
| Tính entitlement | Bộ phận, vùng, nhiệm vụ, thời hạn | Kết quả đúng chính sách phiên bản hiện tại |
| Phê duyệt | Approver, SoD, quyền nhạy cảm | Không cấp đặc quyền khi chưa được duyệt |
| Provisioning | IdP user, SCIM externalId, nhóm | Một account logic đúng mapping |
| Readback | Trạng thái tại từng hệ thống | Quyền thực tế khớp quyền được duyệt |
| Enforcement | Đăng nhập SSO, gọi API | Cho phép đúng và từ chối đúng |
| Audit | Correlation ID, thời điểm, actor, outcome | Truy vết được toàn bộ tiến trình |

Phân biệt ba trạng thái: **đã nhận sự kiện**, **đã thực thi provisioning** và **đã xác minh quyền tại đích**. Một hàng đợi chấp nhận message hoặc API trả HTTP 200 không đồng nghĩa Joiner hoàn tất.

## 3. Chuẩn bị dữ liệu và oracle kiểm thử

Trong môi trường thử nghiệm tách biệt, tạo danh tính giả có person ID cố định, event ID duy nhất, ngày hiệu lực, trạng thái xác minh, loại hợp đồng, bộ phận, vùng và người quản lý. Nên có các nhóm nhân viên chính thức, contractor, nhân sự quyền cao, người trở lại làm việc và trường hợp tên/email trùng.

Ví dụ một bản ghi sự kiện thử:

~~~yaml
eventId: join-1042-v1
eventVersion: 1
eventType: JOINER
personId: test-person-1042
verified: true
employmentStatus: PRE_HIRE
department: SALES
region: VN
workerType: EMPLOYEE
effectiveAt: 2026-12-01T09:00:00+07:00
requestedRoles:
  - sales-reader-vn
~~~

Đây là schema minh họa; hệ thống thực tế có thể dùng tên trường và trạng thái khác. Test oracle phải xuất phát từ **chính sách được phê duyệt**, ví dụ:

~~~text
if not verified or not approved or now < effectiveAt:
    effectiveAccess = {}
else:
    requiredAccess ⊆ effectiveAccess
    effectiveAccess ⊆ permittedByPolicy
    forbiddenAccess ∩ effectiveAccess = {}
~~~

Không chỉ kiểm tra danh sách role: phải xác minh quyền kế thừa qua nhóm, quyền gán trực tiếp, nhóm lồng nhau, quy tắc ABAC và claim SSO còn nằm trong token/cache. Với các hệ thống hỗ trợ eventual consistency, xác định SLA hội tụ trước khi viết điều kiện timeout.

## 4. Ma trận test case Joiner

| ID | Điều kiện kiểm thử | Kết quả kỳ vọng | Ưu tiên |
|---|---|---|---|
| J01 | Người hợp lệ, được duyệt, đến ngày bắt đầu | Tạo đúng tài khoản, quyền tối thiểu | Rất cao |
| J02 | Chưa được xác minh từ nguồn | Không kích hoạt truy cập | Rất cao |
| J03 | Ngày bắt đầu ở tương lai | Không được truy cập dữ liệu sớm | Cao |
| J04 | Quyền đặc biệt chưa duyệt | Không có đặc quyền | Rất cao |
| J05 | Phê duyệt bị từ chối | Không cấp quyền, có audit | Cao |
| J06 | Cùng event ID gửi nhiều lần | Không tạo account/entitlement trùng | Rất cao |
| J07 | Email trùng với một người khác | Không liên kết nhầm danh tính | Rất cao |
| J08 | SCIM trả 429/5xx/timeout | Retry có kiểm soát, theo dõi trạng thái lỗi | Cao |
| J09 | IdP thành công, ứng dụng đích lỗi | Không đánh dấu hoàn tất toàn bộ | Cao |
| J10 | Claim SSO sai vùng hoặc bộ phận | Không mở truy cập ngoài chính sách | Rất cao |
| J11 | Contractor có thời hạn | Thiết lập hiệu lực và ngày hết hạn đúng | Cao |
| J12 | Role tạo xung đột SoD | Chặn hoặc yêu cầu ngoại lệ có duyệt | Rất cao |
| J13 | Dữ liệu nguồn đổi trong khi xử lý | Trạng thái cuối theo phiên bản hợp lệ mới nhất | Cao |
| J14 | Ứng dụng chỉ có tài khoản cục bộ | Có readback và kiểm thử quyền tương đương | Cao |

Với từng test case, ghi trạng thái trước, dữ liệu sự kiện, hệ thống quan sát, hành động, quyền kỳ vọng, quyền thực tế, deadline và bằng chứng. Một test dương tính cần đi kèm test âm tính. Ví dụ: nhân viên Sales được xem khách hàng vùng VN nhưng không được xem khách hàng vùng khác hoặc xuất toàn bộ dữ liệu.

## 5. Kiểm thử xác minh và chống gắn nhầm danh tính

Không dùng duy nhất email hoặc tên hiển thị làm khóa danh tính vì có thể thay đổi hoặc được tái sử dụng. Nên liên kết theo ID bất biến từ nguồn tin cậy khi có sẵn. Các tình huống quan trọng:

1. Thiếu thông tin xác minh, mã bộ phận không hợp lệ, ngày hiệu lực sai, trạng thái HR không đủ điều kiện: hệ thống từ chối hoặc đưa vào hàng chờ có lý do.
2. Cùng người đổi email trước khi hoàn tất Joiner: cập nhật identity đúng, không sinh account thứ hai.
3. Hai người trùng tên hoặc email gần giống: không gộp nhầm quyền và credentials.
4. Retry sau timeout mạng: tra cứu bằng stable external ID trước khi tạo mới, tránh duplicate.
5. Event phiên bản cũ đến sau phiên bản mới: không ghi đè thuộc tính hiện tại bằng dữ liệu lỗi thời.
6. Rehire sau một lần Leaver: chỉ kích hoạt quyền mới đã được xét duyệt; không phục hồi quyền cũ mặc định.

Nếu thông tin nguồn bất nhất, hành vi an toàn là dừng bước cấp quyền chịu ảnh hưởng và phát cảnh báo xử lý. Không tự suy đoán danh tính bằng tên/email.

## 6. Kiểm thử least privilege với RBAC và ABAC

Giả sử role Sales Reader VN chỉ có quyền xem thông tin khách hàng vùng VN và dashboard doanh số. Các phép thử truy cập:

| Yêu cầu | Quyết định kỳ vọng |
|---|---|
| Đọc hồ sơ khách hàng thuộc VN | ALLOW |
| Đọc khách hàng ngoài VN | DENY |
| Xuất toàn bộ danh sách khách hàng | DENY |
| Xem sales dashboard | ALLOW |
| Phê duyệt thanh toán | DENY |
| Quản trị người dùng IAM | DENY |

Kiểm tra ba lớp: **policy decision** từ engine RBAC/ABAC, **provisioned entitlement** từ IdP/ứng dụng, và **effective authorization** từ API tài nguyên thật. Với ABAC, thử region thiếu, null, sai kiểu, giá trị không nằm trong danh mục và token có claim cũ. Trong chính sách deny-by-default, thiếu thuộc tính phải bị từ chối.

Với Separation of Duties (SoD), thử cấp hai vai trò xung đột, ví dụ tạo và duyệt cùng khoản thanh toán. Đảm bảo cả cơ chế tính quyền lẫn điểm thực thi chặn tổ hợp không hợp lệ. Nếu có quyền ngoại lệ, cần có người phê duyệt, mục đích, thời hạn và audit.

## 7. Kiểm thử IdP, SSO và SCIM

**IdP:** xác minh đúng directory/tenant, trạng thái account, group membership, yêu cầu MFA và chính sách đăng nhập. Trường hợp tài khoản được chuẩn bị trước ngày vào làm cần phân biệt account tồn tại với quyền đăng nhập và truy cập dữ liệu; chưa tới ngày hiệu lực thì không được vượt chính sách.

**SSO:** sau đăng nhập, kiểm tra subject ID, group, role và attribute claim; gọi các API được phép/bị cấm bằng phiên thực. Việc trang SSO hiện thành công không chứng minh authorization của ứng dụng đúng.

**SCIM:** kiểm tra Create User, mapping externalId, active, thuộc tính, nhóm và khả năng readback:

~~~http
POST /scim/v2/Users
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "externalId": "test-person-1042",
  "userName": "joiner1042@example.test",
  "active": true,
  "name": {"givenName": "An", "familyName": "Nguyen"}
}
~~~

Ví dụ này dùng cấu trúc SCIM 2.0 minh họa; các trường bắt buộc cụ thể và nhóm phụ thuộc triển khai. Sau phản hồi tạo thành công, GET/readback account và nhóm. Với lỗi 429, 5xx hoặc timeout, xác minh retry/backoff, lookup account đã tồn tại và ngăn tài khoản trùng. Nếu ứng dụng không hỗ trợ SCIM, cần test cơ chế API/ticket thay thế và kiểm tra quyền thực tế, không dừng ở trạng thái ticket đã đóng.

## 8. Kiểm thử xử lý bất đồng bộ và lỗi từng phần

Joiner có thể đi qua HRIS, message broker, IAM, IdP, SCIM và nhiều SaaS. Cần đo thời điểm hội tụ của mỗi ứng dụng và so sánh với SLA. Không giả định các hệ thống cập nhật tức thì.

~~~mermaid
sequenceDiagram
    participant H as HRIS
    participant I as IAM
    participant D as IdP
    participant A as SCIM App
    H->>I: JOINER(eventId, version)
    I->>D: Create identity
    D-->>I: Success
    I->>A: Provision account
    A--xI: Timeout
    I->>A: Lookup externalId
    A-->>I: Account exists
    I->>A: Reconcile groups and attributes
    A-->>I: Success
    I->>A: Readback effective access
    A-->>I: Expected permissions
~~~

Tạo lỗi ở những ranh giới sau: server đã tạo account nhưng client mất response; consumer nhận message trùng; queue tắc nghẽn; sự kiện đến không theo thứ tự; đích không cập nhật nhóm; ứng dụng trả lỗi kéo dài; tiến trình restart giữa thao tác. Test cần xác minh idempotency, retry có giới hạn, dead-letter queue/cảnh báo và reconciliation. Lỗi ở một ứng dụng phải được báo là **partial failure**, không được đánh dấu toàn bộ Joiner thành công.

Đặc biệt kiểm tra trường hợp sự kiện Joiner cũ đến sau Leaver: dữ liệu cũ không được phép kích hoạt lại quyền đã thu hồi. Khi xác minh hoặc phê duyệt bị từ chối, retry tự động không được tự ý bỏ qua điều kiện bảo mật.

## 9. Ví dụ mã kiểm thử tích hợp

Mã giả Python dưới đây mô tả cách kiểm tra một Joiner hợp lệ ở ứng dụng CRM. Các client, chính sách và hàm eventually là abstraction của test harness, không phải API tiêu chuẩn có sẵn:

~~~python
def test_joiner_least_privilege(hris, idp, crm, iam, policy):
    person_id = "test-person-1042"
    event = {
        "eventId": "join-1042-v1",
        "type": "JOINER",
        "personId": person_id,
        "version": 1,
        "verified": True,
        "approved": True,
        "department": "SALES",
        "region": "VN",
        "effectiveAt": policy.test_effective_at,
    }

    hris.publish(event)
    eventually(
        lambda: idp.count_by_external_id(person_id) == 1,
        timeout_seconds=policy.joiner_sla_seconds,
    )
    expected = {"crm.customer.read.vn", "sales.dashboard.read"}
    eventually(
        lambda: crm.effective_permissions(person_id) == expected,
        timeout_seconds=policy.joiner_sla_seconds,
    )
    assert crm.authorize(person_id, "crm.customer.read.vn") == "ALLOW"
    assert crm.authorize(person_id, "crm.customer.export.all") == "DENY"
    assert crm.authorize(person_id, "iam.users.manage") == "DENY"
    hris.publish(event)  # replay
    eventually(
        lambda: idp.count_by_external_id(person_id) == 1,
        timeout_seconds=policy.joiner_sla_seconds,
    )
    assert iam.audit_contains(event_id=event["eventId"])
~~~

Trong triển khai thực, hàm authorize phải gọi đúng điểm thực thi hoặc API với phiên người dùng; chỉ xem policy mô phỏng không thay được test thực tế. Dùng polling có deadline thay cho sleep cố định khi đánh giá đồng bộ bất đồng bộ.

## 10. Kiểm thử tài khoản dịch vụ liên quan Joiner

Một nhân viên mới có thể được giao quản lý tài khoản dịch vụ, bot triển khai hoặc application identity. Việc gia nhập tổ chức không có nghĩa phải cấp sẵn mọi secret hoặc quyền quản trị máy. Kiểm thử owner, business purpose, phạm vi quyền, phê duyệt, ngày rà soát, cơ chế rotation và quyền đọc credential.

Ví dụ nhân viên DevOps chịu trách nhiệm bot deploy một dịch vụ: chỉ nên nhận quyền triển khai và đọc secret trong môi trường được duyệt. Kiểm tra rằng danh tính người dùng và service principal có lifecycle tách biệt, để khi nhân viên chuyển vai trò hoặc rời tổ chức, quyền ownership và credential được xử lý mà không làm gián đoạn dịch vụ ngoài kế hoạch.

## 11. Audit, reconciliation và tiêu chí hoàn thành

Mỗi testcase phải có bằng chứng từ ba nguồn: **intent** (sự kiện và quyền kỳ vọng), **execution** (log provisioning, phê duyệt, retry) và **observed state** (tài khoản, nhóm, quyền và API thực tế). Ghi correlation ID, actor, subject ID, timestamp, decision, trạng thái từng ứng dụng và phiên bản policy. Không đưa password, access token, private key hoặc thông tin cá nhân không cần thiết vào log.

Đối soát quyền cuối cùng bằng cách lấy tập entitlement kỳ vọng theo chính sách rồi so với quyền thực tế từ IdP, application group, quyền trực tiếp và nested group. Sai lệch phải được ghi thành finding có chủ sở hữu xử lý, cảnh báo và readback sau khắc phục.

Các điều kiện PASS chủ yếu: xác minh người dùng hợp lệ; xử lý ngày hiệu lực; cấp đúng quyền tối thiểu; deny đối với quyền ngoài phạm vi; không tạo account trùng khi retry; không gắn nhầm người; xử lý lỗi từng phần; các ứng dụng trọng yếu hội tụ trong SLA; có dấu vết kiểm toán đủ để truy vết. Bài này tập trung vào Joiner nhưng phải thiết lập ownership, expiry và dữ liệu audit để những bước Mover–Leaver sau có thể thu hồi quyền tồn dư.

## 12. Bài thực hành

Tạo một Joiner giả thuộc Sales VN, bắt đầu lúc 09:00 ngày 01/12/2026. Thiết lập cho phép xem CRM VN và sales dashboard, từ chối xuất dữ liệu CRM hoặc đọc dữ liệu vùng khác. Sau đó thực hiện:

1. Thử truy cập trước ngày hiệu lực và khi HR chưa xác minh.
2. Cho phép Joiner hợp lệ và kiểm tra cả hai nhóm quyền ALLOW/DENY tại API thực.
3. Phát lại sự kiện ba lần, giả lập timeout sau khi ứng dụng đã tạo tài khoản, rồi xác minh không có account hoặc role dư.
4. Đổi region trong lúc provisioning, phát sự kiện cũ sau sự kiện mới và đối soát tập quyền cuối.
5. Thu thập event ID, correlation ID, chính sách, approval, readback và thời điểm hội tụ để kết luận từng case.

Tạo bảng kết quả với các cột caseId, precondition, expected, actual, observedAt, evidence, status và remediation. Giải thích ở lớp nào sai lệch xảy ra (nguồn danh tính, IAM, IdP hay ứng dụng) và chứng minh bằng readback sau khi sửa.
