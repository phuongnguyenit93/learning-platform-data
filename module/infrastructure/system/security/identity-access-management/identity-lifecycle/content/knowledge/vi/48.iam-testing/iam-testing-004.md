# Kiểm thử Leaver trong vòng đời danh tính IAM

## 1. Leaver là gì và mục tiêu kiểm thử

**Leaver** là giai đoạn danh tính kết thúc quan hệ làm việc, hợp đồng hoặc quyền sử dụng một dịch vụ. Trong vòng đời **Joiner–Mover–Leaver**, Leaver là thời điểm hệ thống cần chặn truy cập, thu hồi quyền và kiểm soát mọi đường truy cập tồn dư. Việc nhân viên rời tổ chức, nhà thầu hết hợp đồng hoặc người dùng bị chấm dứt quyền vì sự cố đều cần quy trình phù hợp.

Trong module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`, kiểm thử Leaver phải bao quát IAM, nguồn nhân sự HRIS, Identity Provider (IdP), đăng nhập một lần SSO, SCIM, RBAC/ABAC, ứng dụng SaaS, quyền truy cập tài nguyên, tài khoản dịch vụ và kiểm toán. **Tắt một tài khoản tại IdP là một bước cần thiết trong nhiều kiến trúc nhưng không đủ chứng minh người rời tổ chức không còn truy cập được.** Token chưa hết hạn, phiên cũ, tài khoản cục bộ, API key và quyền chia sẻ trực tiếp đều có thể tạo đường truy cập khác.

Mục tiêu kiểm thử:

- Chỉ xử lý yêu cầu Leaver hợp lệ, đúng người, đúng thời điểm và mức độ khẩn cấp.
- Chặn đăng nhập mới và vô hiệu hóa những quyền không còn được cho phép.
- Thu hồi phiên và credentials theo khả năng kỹ thuật, chính sách rủi ro và SLA của từng ứng dụng.
- Gỡ quyền kế thừa và quyền trực tiếp, không để lại account mồ côi hoặc quyền tồn dư.
- Chuyển giao tài sản, tác vụ và quyền sở hữu service account mà không gây gián đoạn ngoài kế hoạch.
- Lưu đủ chứng cứ về hành động, kết quả từng đích, lỗi, retry và xác minh trạng thái cuối.

## 2. Phân loại Leaver và chính sách thời gian

Không có một trình tự thu hồi duy nhất phù hợp mọi tình huống. Ví dụ:

| Tình huống | Đặc điểm | Câu hỏi kiểm thử |
|---|---|---|
| Nghỉ việc theo kế hoạch | Biết trước ngày kết thúc | Quyền còn hợp lệ trước mốc kết thúc và bị thu hồi đúng thời điểm? |
| Chấm dứt khẩn cấp | Cần chặn truy cập ngay theo chính sách | Đăng nhập mới và những đường truy cập ưu tiên cao bị chặn trong deadline nghiêm ngặt? |
| Hết hạn hợp đồng | Có `contractEndAt` | Không kéo dài quyền vì đồng bộ chậm hoặc múi giờ sai? |
| Tạm đình chỉ | Có thể khôi phục sau xem xét | Cơ chế suspend có chặn đúng phạm vi mà không xóa nhầm dữ liệu? |
| Nhà thầu hết dự án | Có thể làm việc ở dự án khác | Thu hồi entitlement theo phạm vi dự án, đúng định nghĩa Leaver của tổ chức? |
| Rehire sau Leaver | Người cũ quay lại với phê duyệt mới | Không khôi phục quyền lịch sử ngoài chính sách hiện tại? |

Nên định nghĩa rõ `effectiveAt`, `receivedAt`, `processedAt`, `verifiedAt` và đồng hồ tham chiếu. Mốc **đã nhận yêu cầu** không đồng nghĩa **đã chặn quyền thực tế**. SLA không được suy đoán: phải lấy từ yêu cầu tổ chức, đặc biệt với ứng dụng chỉ hỗ trợ token tự mang thông tin (self-contained) hoặc đồng bộ bất đồng bộ.

## 3. Mô hình dữ liệu và oracle kiểm thử

Ví dụ sự kiện giả lập:

~~~yaml
eventId: leaver-302-v21
eventVersion: 21
eventType: LEAVER
personId: test-person-302
employmentStatus: TERMINATED
terminationType: PLANNED
effectiveAt: 2026-12-20T18:00:00+07:00
approvedBy: test-hr-01
sourceSystem: HRIS
~~~

Các tên trường chỉ mang tính minh họa. Định danh `personId` cần ổn định; không suy người cần khóa bằng email hoặc tên hiển thị. Kiểm tra sự kiện giả mạo, thiếu xác minh, phiên bản cũ, trùng `eventId`, sai múi giờ và những thay đổi trạng thái mâu thuẫn.

Oracle cho một Leaver đã có hiệu lực có thể được định nghĩa như sau:

~~~text
effectiveAt <= now
identity.status = TERMINATED
newInteractiveSignIn = DENY
approvedInteractiveGrants = {}
allUnapprovedEffectiveGrants = {}
existingSessions comply with revocation policy and SLA
ownedServiceAccounts have valid replacement owner or approved disposition
audit and reconciliation evidence are complete
~~~

Điều kiện trên cần điều chỉnh cho danh tính dùng chung, nghĩa vụ lưu trữ, quyền truy cập dữ liệu còn được phép theo quy trình pháp lý và cấu hình dịch vụ. Không xóa dữ liệu công việc chỉ vì tài khoản bị vô hiệu; nội dung lưu trữ và quyền truy cập là hai vấn đề khác nhau.

## 4. Luồng Leaver và điểm xác minh

~~~mermaid
flowchart TD
    H[HRIS / nguồn được ủy quyền] --> V[Kiểm tra identity, version, effectiveAt]
    V --> P[Đánh giá mức độ khẩn cấp]
    P --> B[Chặn đăng nhập mới tại IdP]
    B --> S[Thu hồi / giới hạn session và token]
    S --> D[SCIM / connector deprovision ứng dụng]
    D --> G[Gỡ nhóm, role, direct grants và credentials]
    G --> O[Bàn giao service account, dữ liệu và tài sản]
    O --> R[Readback trạng thái và thử truy cập]
    R --> Q{Còn đường truy cập?}
    Q -->|Không| A[Đóng workflow với audit]
    Q -->|Có| E[Alert, remediation, retry]
~~~

Một số bước có thể chạy song song, hoặc chặn truy cập khẩn cấp trước các bước nghiệp vụ. Khi thiết kế kiểm thử, tách **lệnh thu hồi đã phát đi** khỏi **quyền thực tế đã hết hiệu lực**. Phải xác minh tại điểm kiểm soát truy cập, không chỉ trên màn hình trạng thái người dùng.

| Lớp | Phép thử | Kết quả kỳ vọng |
|---|---|---|
| HRIS / IAM | Sự kiện hợp lệ, đúng ID, version | Không xử lý nhầm người hoặc sự kiện cũ |
| IdP | Đăng nhập mới bằng credentials cũ | Bị từ chối sau hiệu lực theo SLA |
| SSO | Session trước khi nghỉ, refresh token | Tuân thủ chính sách revoke/expiry |
| SCIM | Trạng thái active và group tại ứng dụng | Người dùng bị vô hiệu và không còn entitlement |
| Local account | Đăng nhập không qua SSO | Bị chặn nếu tài khoản thuộc phạm vi thu hồi |
| API / PAT | Dùng token hoặc API key đã phát | Không được phép tiếp tục vượt deadline |
| SSH / VPN | Đăng nhập từ xa, thiết bị, chứng chỉ | Credential và phiên được xử lý theo chính sách |
| RBAC / ABAC | Role, nhóm lồng nhau, attribute cache | Không còn effective access không hợp lệ |
| Service account | Owner, secret, automation | Quyền người cũ bị gỡ, owner được chuyển giao |
| Audit | Correlation ID và kết quả từng connector | Có bằng chứng và phát hiện lỗi từng phần |

## 5. Ma trận test case Leaver

| ID | Tình huống | Kỳ vọng | Ưu tiên |
|---|---|---|---|
| L01 | Nghỉ việc bình thường đúng ngày | Đăng nhập bị chặn, entitlement bị gỡ đúng hạn | Rất cao |
| L02 | Leaver khẩn cấp | Chặn quyền trọng yếu theo SLA khẩn cấp | Rất cao |
| L03 | Hết hạn hợp đồng | Không còn quyền sau ngày kết thúc | Rất cao |
| L04 | Đang có session SSO | Session không tiếp tục truy cập ngoài deadline | Rất cao |
| L05 | Access/refresh token đang tồn tại | Revoke/expiry đúng thiết kế, không cấp refresh mới | Rất cao |
| L06 | Local account ở ứng dụng | Không còn đường đăng nhập độc lập | Rất cao |
| L07 | API key, PAT hoặc SSH key | Thu hồi hoặc luân chuyển credential theo policy | Rất cao |
| L08 | Group IdP đã gỡ, role cục bộ vẫn còn | Phát hiện và khắc phục quyền tồn dư | Rất cao |
| L09 | SCIM timeout sau khi đã cập nhật | Retry idempotent, trạng thái cuối đúng | Cao |
| L10 | Event Leaver bị replay | Không nhân đôi thao tác gây hại hoặc mở quyền lại | Cao |
| L11 | Mover/Joiner cũ đến muộn | Không kích hoạt lại identity đã chấm dứt | Rất cao |
| L12 | Thay đổi email hoặc trùng tên | Không khóa nhầm người, không bỏ sót account | Rất cao |
| L13 | Chủ sở hữu service principal rời đi | Bàn giao owner, quyền và secret đúng chính sách | Cao |
| L14 | Người nghỉ được tuyển lại | Chỉ cấp quyền mới sau xác minh và phê duyệt | Cao |
| L15 | Connector đích không hoạt động | Có cảnh báo, trạng thái chưa hoàn tất và remediation | Rất cao |
| L16 | Dữ liệu cần lưu trữ sau nghỉ việc | Giữ bằng chứng và bàn giao đúng policy | Cao |

Mỗi test case cần có precondition, đầu vào, trạng thái kỳ vọng, deadline, trạng thái thực tế, kết quả thử truy cập và bằng chứng. Cần **negative assertions**: một sự kiện Leaver chỉ đạt khi người dùng thực sự không còn thực hiện được các hành động bị cấm.

## 6. Kiểm thử IdP, SSO, phiên và token

Đây là nhóm kiểm thử rất dễ bị đánh giá thiếu. Khi account bị disable tại IdP, người dùng có thể không đăng nhập mới được nhưng vẫn có cookie phiên tại ứng dụng hoặc JWT access token được kiểm offline.

Thử riêng:

1. **Đăng nhập mới:** sử dụng username/password hoặc phương thức đăng nhập hợp lệ trước đây; phải bị từ chối sau khi deactivation có hiệu lực.
2. **Refresh token:** refresh token cũ không được phát access token mới sau khi bị thu hồi theo chính sách.
3. **Access token hiện hữu:** dùng token phát trước sự kiện để gọi API; quan sát thời điểm endpoint ngừng chấp nhận. Nếu resource server chỉ kiểm chữ ký và expiry, token có thể tồn tại đến hạn; hệ thống phải có SLA và cơ chế phù hợp như token ngắn hạn, introspection, revocation list hoặc event-driven session invalidation.
4. **SSO và session cục bộ:** đăng nhập ứng dụng trước Leaver, sau đó thử tải trang nhạy cảm và thực hiện thao tác ghi. Kiểm tra logout toàn cục nếu kiến trúc hỗ trợ; ứng dụng phải chặn theo deadline.
5. **Thiết bị và remote access:** thử VPN, SSH, VDI, cached credentials và cert theo danh mục có ràng buộc.
6. **Tài khoản break-glass hoặc đặc quyền:** không vô tình coi mọi admin role là quyền nhân sự; phải kiểm tra chủ thể, phê duyệt và kênh truy cập được quản lý riêng.

Không giả định `HTTP 401` luôn là kết quả duy nhất: một endpoint có thể trả `403` do người dùng xác thực được nhưng không còn quyền. Điều quan trọng là hành động bị ngăn tại điểm thực thi và không làm lộ tài nguyên.

## 7. Kiểm thử SCIM, nhóm và quyền trực tiếp

Với ứng dụng hỗ trợ SCIM, một cách deprovision phổ biến là đặt `active=false` cho User và điều chỉnh membership. Ví dụ minh họa:

~~~http
PATCH /scim/v2/Users/user-302
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    { "op": "replace", "path": "active", "value": false }
  ]
}
~~~

Cách ứng dụng xử lý `active=false`, khóa API và session phụ thuộc implementation; phải đọc lại trạng thái rồi thử quyền thực tế. Có ứng dụng không tự gỡ role khi account bị inactive, vì vậy reconciliation phải phân biệt *account state* và *effective access*.

Kiểm thử thêm:

- SCIM server trả `429`, `500`, mất kết nối hoặc timeout sau khi đã thay đổi: retry có backoff, lookup, không tạo lại account hoặc ghi thành công sai.
- Mapping `externalId` sai hoặc email đổi: không thao tác nhầm người.
- IdP gỡ nhóm nhưng ứng dụng còn quyền trực tiếp: rà soát role nội bộ, chia sẻ tài liệu và membership dự án.
- Nhiều ứng dụng cùng đồng bộ: một ứng dụng thất bại phải xuất hiện trạng thái partial failure.
- Connector không hỗ trợ deactivate: có luồng thay thế qua API/ticket và bằng chứng readback; không chỉ đóng ticket là PASS.

## 8. Credentials và các đường truy cập ngoài IdP

Leaver phải kiểm thử cả thông tin xác thực độc lập:

| Loại | Nguy cơ | Phép thử |
|---|---|---|
| Personal access token | Token truy cập Git hoặc SaaS sau nghỉ | Gọi API với PAT cũ sau thu hồi |
| API key | Khóa tồn tại ngoài SSO | Thực hiện request bằng khóa cũ |
| SSH key | Truy cập máy chủ/repository | Kết nối xác thực bằng khóa cũ |
| Client certificate | Thiết bị hoặc VPN còn xác thực được | Thử kết nối với chứng chỉ cũ |
| Mật khẩu local | Ứng dụng bỏ qua IdP | Đăng nhập trực tiếp sau disable |
| Shared credential | Bí mật từng được người rời biết | Xác minh rotation và quyền đọc secret |
| Long-lived session | Session sống lâu hơn trạng thái IAM | Thử thao tác đọc/ghi bằng cookie cũ |

Việc rotation secret có thể cần triển khai an toàn để tránh làm gián đoạn dịch vụ. Kiểm thử chứng minh credential cũ không còn được chấp nhận sau khi triển khai khóa mới và các consumer hợp lệ vẫn hoạt động.

## 9. Xử lý bất đồng bộ, idempotency và sự kiện cũ

Trong hệ thống event-driven, Leaver phải an toàn khi sự kiện đến muộn, gửi trùng hoặc xử lý một phần. Một tình huống nguy hiểm:

~~~text
t1: LEAVER(person-302, version=21) được thực thi.
t2: IdP và SaaS đã khóa quyền truy cập.
t3: MOVER(person-302, version=20) đến muộn.

Kỳ vọng: MOVER v20 không được khôi phục quyền.
~~~

Sử dụng version/sequence đáng tin cậy hoặc đối chiếu nguồn trạng thái chuẩn trước khi cấp quyền. Không suy thứ tự nghiệp vụ từ thứ tự giao message. Khi replay cùng Leaver, trạng thái cuối cần idempotent; việc gỡ quyền nhiều lần không gây lỗi nghiệp vụ nghiêm trọng và không làm phát sinh account mới.

~~~mermaid
sequenceDiagram
    participant H as HRIS
    participant I as IAM
    participant D as IdP
    participant A as Application
    H->>I: LEAVER v21
    I->>D: Disable account
    D-->>I: Success
    I->>A: SCIM deactivate
    A--xI: Timeout
    I->>A: Lookup current state
    A-->>I: active=false, role remains
    I->>A: Remove residual grants
    A-->>I: Success
    I->>A: Test access and readback
    A-->>I: DENY
~~~

Kiểm thử hàng đợi lỗi (dead-letter queue), retry có giới hạn, cảnh báo SLA và reconciliation định kỳ. Nếu một ứng dụng chưa thể xử lý, workflow phải báo trạng thái chưa hoàn tất và định tuyến xử lý; tránh tuyên bố thành công toàn bộ.

## 10. Kiểm thử tài khoản dịch vụ và bàn giao

Một nhân sự nghỉ việc có thể là owner của service account, bot CI/CD, API integration, repository, nhóm vận hành hoặc lịch chạy công việc. Các đối tượng đó có thể cần tiếp tục hoạt động sau Leaver. Test phải chứng minh quyền cá nhân bị thu hồi, ownership được chuyển giao cho người/nhóm hợp lệ, credential được xem xét rotation, và không còn quyền quản trị bí mật từ nhân sự cũ.

Ví dụ nhân viên `person-302` sở hữu bot triển khai: sau Leaver, nhóm Platform trở thành owner hợp lệ, nhân viên cũ không còn xem secret hoặc trigger deploy; bot vẫn triển khai bình thường dưới quyền máy riêng. Không xóa tài khoản dịch vụ tự động chỉ vì owner nghỉ mà chưa đánh giá phụ thuộc và kế hoạch bàn giao.

Kiểm tra cả account không còn owner: reconciliation phải phát hiện và tạo finding có mức độ ưu tiên. Với quyền đặc quyền lâu dài, yêu cầu xác thực cấp duyệt và thời hạn phù hợp.

## 11. Ví dụ mã giả kiểm thử tích hợp

Mã giả sau minh họa cách gửi sự kiện và xác minh quyền thực tế. Các client, chính sách và hàm `eventually` là abstraction của test harness, không phải API chuẩn có sẵn:

~~~python
def test_leaver_revokes_effective_access(hris, idp, crm, iam, policy):
    user_id = "test-person-302"
    old_session = crm.create_test_session(user_id)
    old_token = crm.issue_test_access_token(user_id)
    event = {
        "eventId": "leaver-302-v21",
        "personId": user_id,
        "type": "LEAVER",
        "version": 21,
        "effectiveAt": policy.test_effective_at,
    }
    hris.publish(event)

    eventually(
        lambda: idp.is_disabled(user_id),
        timeout_seconds=policy.disable_sla_seconds,
    )
    eventually(
        lambda: crm.effective_permissions(user_id) == set(),
        timeout_seconds=policy.deprovision_sla_seconds,
    )
    assert idp.try_new_sign_in(user_id).denied
    eventually(
        lambda: crm.request_with_session(old_session, "sensitive-report").denied,
        timeout_seconds=policy.session_revoke_sla_seconds,
    )
    eventually(
        lambda: crm.request_with_token(old_token, "sensitive-report").denied,
        timeout_seconds=policy.token_revoke_sla_seconds,
    )
    assert iam.audit_contains(event_id=event["eventId"])

    hris.publish(event)  # Replay cùng sự kiện.
    assert idp.count_by_person_id(user_id) == 1
~~~

Test harness cần tính thời điểm `effectiveAt` trước khi đánh giá SLA, kiểm tra session/token với API thực tế và tránh log giá trị secret/token. Với ứng dụng không hỗ trợ revoke access token ngay, `token_revoke_sla_seconds` cần phản ánh giới hạn thực tế được phê duyệt, đồng thời hệ thống phải giảm rủi ro thích hợp.

## 12. Audit, reconciliation và điều kiện PASS

Một hồ sơ Leaver kiểm thử cần liên kết:

1. **Intent:** nguồn yêu cầu, person ID, căn cứ chấm dứt, thời điểm hiệu lực, phê duyệt.
2. **Execution:** correlation ID, từng lệnh disable/revoke, phản hồi, lỗi, retry, actor.
3. **Observed access:** account state, groups, direct grants, session/token, API checks tại từng ứng dụng.
4. **Timeliness:** thời điểm chặn đăng nhập mới, hội tụ quyền và kết thúc phiên so với SLA.
5. **Handover:** account/service ownership, dữ liệu cần lưu, thay đổi credential và bằng chứng vận hành.

Đối soát định kỳ có thể mô tả:

~~~text
expectedActiveIdentities = sourceOfTruth.activeIdentities()
observedIdentities       = enumerateIdentities(allApplications)
orphanAccounts = observedIdentities - expectedActiveIdentities
residualGrants = actualEffectiveGrants - approvedEffectiveGrants
~~~

Không phải mọi `orphanAccount` đều có thể xóa ngay vì dữ liệu phải được lưu theo quy định; test cần phân loại account còn hiệu lực truy cập, account đã khóa nhưng giữ dữ liệu, account cần điều tra. Một Leaver đạt PASS khi **đúng chủ thể bị thu hồi đúng hạn, không còn đường truy cập bị cấm, tất cả ngoại lệ và lỗi có xử lý, dữ liệu được bàn giao hợp lệ, audit và readback đầy đủ**.

## 13. Bài thực hành

Giả lập nhân viên `test-person-302` nghỉ việc lúc 18:00 ngày 20/12/2026, trước đó có SSO, CRM, VPN, PAT Git và quyền đọc secret của bot deploy. Thực hiện:

1. Tạo một phiên CRM và một token trước sự kiện Leaver; ghi nhận thời hạn.
2. Gửi Leaver hợp lệ và xác minh không có đăng nhập SSO mới sau thời điểm hiệu lực.
3. Thử lại bằng session, token, PAT và VPN, đo thời gian đến khi quyền bị từ chối.
4. Giả lập SCIM timeout sau khi ứng dụng đã vô hiệu account; xác minh retry không tạo bản ghi mới và readback quyền bằng rỗng.
5. Gửi Mover phiên bản cũ sau Leaver; xác minh tài khoản không được kích hoạt lại.
6. Bàn giao owner bot deploy, luân chuyển secret nếu cần, thử quyền của người cũ và vận hành của bot.
7. Sinh báo cáo đối soát với `caseId, expected, actual, observedAt, deadline, evidence, outcome, remediation`.

Khi một ứng dụng vẫn chấp nhận phiên cũ hoặc credential độc lập, cần ghi nhận lỗi thu hồi quyền thực tế dù IdP đã báo disabled. Đây là tiêu chí quan trọng để giảm **quyền truy cập tồn dư** và kết thúc vòng đời danh tính an toàn.
