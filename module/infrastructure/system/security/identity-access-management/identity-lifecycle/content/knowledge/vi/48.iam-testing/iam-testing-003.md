# Kiểm thử Mover trong vòng đời danh tính IAM

## 1. Mover là gì?

Trong mô hình **Joiner–Mover–Leaver (JML)**, **Mover** là sự kiện một danh tính đang hoạt động thay đổi vai trò, phòng ban, đơn vị, địa điểm làm việc, loại hợp đồng, người quản lý hoặc trách nhiệm. Kiểm thử Mover xác minh quá trình cập nhật quyền khi các thuộc tính danh tính thay đổi, đặc biệt là **thu hồi quyền không còn hợp lệ**. Một người chuyển từ Sales sang Finance có thể nhận quyền báo cáo tài chính mới nhưng phải mất những quyền Sales không còn cần thiết.

Trong module quản lý vòng đời danh tính IAM, việc thay đổi có thể đi qua nguồn dữ liệu nhân sự (HRIS), IAM, Identity Provider (IdP), SSO, SCIM và ứng dụng nội bộ. Quyết định truy cập có thể được tính bằng RBAC (vai trò) hoặc ABAC (thuộc tính). Mục tiêu kiểm thử là chứng minh danh tính được cập nhật đúng, quyền mới cấp đúng hạn và không tồn tại quyền truy cập dư do giữ nhóm cũ, session cũ, quyền trực tiếp hay quyền kế thừa.

Một luồng Mover chỉ đạt khi ba điều kiện cùng đúng:

1. **Danh tính liên tục:** cùng một con người giữ được identity ổn định, không vô tình tạo tài khoản mới.
2. **Quyền sau thay đổi đúng chính sách:** quyền cần thiết được cấp, quyền cũ không còn cần được gỡ theo thời hạn cho phép.
3. **Quyền thực tế được xác minh:** IdP, ứng dụng, API, phiên SSO và các thành phần thực thi không còn cho phép hành động đã bị thu hồi.

## 2. Mô hình sự kiện Mover và tập quyền kỳ vọng

Ví dụ nhân viên mã `person-204` đang làm Sales tại Việt Nam chuyển sang Finance:

~~~yaml
eventId: mover-204-v12
eventVersion: 12
eventType: MOVER
personId: person-204
effectiveAt: 2026-12-10T09:00:00+07:00
previous:
  department: SALES
  region: VN
  managerId: manager-1
current:
  department: FINANCE
  region: VN
  managerId: manager-2
approvalId: approval-finance-204
~~~

Đây là dữ liệu minh họa; tên trường và trạng thái có thể khác trong hệ thống thực tế. `personId` cần được giữ ổn định khi thay đổi email hoặc tên hiển thị. Dùng `eventVersion` hoặc cơ chế thứ tự khác để loại bỏ sự kiện đã lỗi thời.

Ví dụ tập quyền:

~~~text
before = {
  "crm.customer.read.vn",
  "crm.export.limited",
  "sales.dashboard.read"
}
after_expected = {
  "finance.report.read",
  "finance.dashboard.read"
}

add    = after_expected - before
remove = before - after_expected
unexpected_after = after_actual - after_expected
missing_after    = after_expected - after_actual

PASS khi unexpected_after và missing_after đều rỗng
~~~

Trong trường hợp có quyền dùng chung hoặc quyền ngoại lệ được duyệt, tập `after_expected` phải bao gồm chúng cùng thời hạn hiệu lực. **Không mặc định rằng mọi quyền cũ đều phải mất**: quyền giữ lại phải có căn cứ từ chính sách hiện hành, không phải do hệ thống vô tình bỏ qua bước thu hồi.

## 3. Luồng Mover cần kiểm thử

~~~mermaid
flowchart TD
    H[HRIS / nguồn thay đổi] --> V[Kiểm tra sự kiện và version]
    V --> P[Tính entitlement mới từ RBAC / ABAC]
    P --> S{SoD / phê duyệt đặc quyền}
    S -->|Được phép| C[Plan cấp và thu hồi quyền]
    S -->|Chưa duyệt| B[Giữ trạng thái có kiểm soát]
    C --> I[Thay đổi tại IAM / IdP]
    I --> A[SCIM / API ứng dụng]
    A --> R[Readback trạng thái cuối]
    R --> T[Kiểm tra quyền ALLOW và DENY]
    T --> Q{Khớp policy?}
    Q -->|Có| L[Audit thành công]
    Q -->|Không| F[Alert, retry, remediation]
~~~

Hệ thống có thể cập nhật quyền theo kiểu transaction, workflow hoặc eventual consistency. Bài kiểm thử phải ghi rõ thời điểm sự kiện có hiệu lực, deadline cấp quyền mới và deadline thu hồi quyền cũ. Với quyền nhạy cảm, mức ưu tiên nên nghiêng về thu hồi trước khi cấp quyền xung đột, theo chính sách vận hành và yêu cầu không gián đoạn công việc.

| Thành phần | Cần quan sát | Nguy cơ |
|---|---|---|
| HRIS / nguồn chuẩn | Mã người, vai trò mới, ngày hiệu lực, phiên bản | Sự kiện thiếu, chậm, trùng hoặc ngoài thứ tự |
| IAM policy | Tập quyền theo role/attribute, ngoại lệ | Chính sách cũ hoặc tính toán sai |
| Approval / SoD | Người duyệt, quyền xung đột, expiry | Cấp đặc quyền khi chưa được duyệt |
| IdP / Directory | Group, account state, claim | Giữ membership cũ |
| SCIM / connector | Update user, PATCH group, provision/deprovision | Lỗi từng phần, retry trùng, mapping sai |
| SSO / token | Claim và phiên đã phát hành | Claim cũ tiếp tục có hiệu lực |
| Ứng dụng | Quyền trực tiếp, role nội bộ, API authorization | Quyền tồn dư dù IdP đã cập nhật |
| Audit / reconciliation | Event, quyết định, kết quả, actual/expected | Không phát hiện hoặc không truy vết được sai lệch |

## 4. Ma trận kiểm thử Mover

| ID | Tình huống | Kết quả kỳ vọng | Ưu tiên |
|---|---|---|---|
| M01 | Chuyển Sales sang Finance | Có quyền Finance, không còn quyền Sales ngoài ngoại lệ | Rất cao |
| M02 | Chuyển Finance trở lại Sales | Không giữ quyền Finance | Rất cao |
| M03 | Chỉ đổi manager, không đổi policy | Không gây cấp/thu hồi quyền không cần thiết | Trung bình |
| M04 | Đổi vùng VN sang SG theo ABAC | Không còn xem dữ liệu VN nếu policy không cho phép | Rất cao |
| M05 | Thăng lên vị trí có đặc quyền | Chỉ cấp sau phê duyệt hợp lệ | Rất cao |
| M06 | Hạ vai trò / hết quyền tạm thời | Thu hồi đặc quyền đúng hạn | Rất cao |
| M07 | Vai trò mới tạo xung đột SoD | Chặn hoặc yêu cầu ngoại lệ phê duyệt | Rất cao |
| M08 | Event Mover bị replay | Không nhân đôi nhóm hoặc workflow | Cao |
| M09 | Event version cũ đến muộn | Không phục hồi quyền cũ | Rất cao |
| M10 | Mover và Leaver gần đồng thời | Leaver ưu tiên chặn truy cập theo chính sách | Rất cao |
| M11 | SCIM lỗi ở một ứng dụng | Báo partial failure, retry và readback | Cao |
| M12 | IdP đã gỡ nhóm, API còn cho phép | Phát hiện truy cập tồn dư | Rất cao |
| M13 | Người dùng đổi email trong lúc Mover | Giữ đúng identity, không tạo tài khoản trùng | Cao |
| M14 | Contractor đổi owner / loại hợp đồng | Áp dụng entitlement và thời hạn mới | Cao |
| M15 | Người mới giữ ownership service account | Chuyển giao có phê duyệt, không mở rộng secret ngoài phạm vi | Cao |

Mỗi ca có ít nhất một khẳng định dương tính (quyền mới hoạt động) và một khẳng định âm tính (quyền đã thu hồi không còn truy cập được). Chỉ đọc danh sách nhóm là chưa đủ.

## 5. Kiểm thử cấp quyền mới và thu hồi quyền cũ

Với Mover có cả quyền cần thêm và cần bớt, kiểm thử hai nhánh độc lập:

**Cấp quyền mới**

- Tính đúng role hoặc thuộc tính mới, đúng policy phiên bản hiện hành.
- Chỉ cấp quyền nhạy cảm khi yêu cầu phê duyệt và SoD đã hoàn tất.
- Đẩy thay đổi qua IdP và các ứng dụng; readback quyền tại đích.
- Dùng phiên đăng nhập mới hoặc API thực tế để chứng minh chức năng mới hoạt động.

**Thu hồi quyền cũ**

- Gỡ role và group không còn hợp lệ, bao gồm nhóm lồng nhau.
- Gỡ quyền trực tiếp tại ứng dụng nếu trước đó được gán ngoài IAM.
- Kiểm tra cache quyền, token SSO có claim cũ và phiên đang hoạt động theo thời hạn chính sách.
- Dùng phiên cũ để thử thao tác đã bị thu hồi; kết quả phải bị từ chối trong deadline.
- Đối soát entitlement sau khi các connector hoàn thành để phát hiện grant tồn dư.

Ví dụ nhân viên được gỡ group `sales-admin` tại IdP nhưng một ứng dụng vẫn cấp quyền `crm.export.all` qua role cục bộ. Kiểm thử API xuất dữ liệu phải phát hiện thất bại của việc thu hồi. Nếu test chỉ kiểm group tại IdP, lỗi này dễ bị bỏ sót.

## 6. Kiểm thử RBAC, ABAC, nhóm kế thừa và SoD

### RBAC

Role mới cần tương ứng nhiệm vụ mới. Kiểm thử quyền được thừa kế từ role cha, group động và group lồng nhau. Một group có thể bị gỡ trực tiếp nhưng người dùng vẫn nhận quyền qua group khác; test cần tính **effective grants**, không chỉ membership trực tiếp.

### ABAC

Với ABAC, quyền phụ thuộc thuộc tính như `department`, `region`, `contractType`, `deviceTrust` hoặc `resourceOwner`. Kiểm thử thay đổi riêng từng thuộc tính và thay đổi đồng thời. Trường hợp attribute thiếu, null, sai kiểu hoặc chưa được IdP đồng bộ cần xử lý theo policy an toàn, thường là deny-by-default. Thử cả token đã phát hành có claim cũ trước khi cập nhật.

### Separation of Duties

Một nhân viên chuyển sang Finance có thể đã giữ quyền `payment.create` từ role cũ và được yêu cầu `payment.approve`. Nếu chính sách cấm sở hữu hai quyền đồng thời, luồng Mover phải phát hiện và từ chối cấp phần xung đột hoặc yêu cầu ngoại lệ có thời hạn. Test cần kiểm tra cả trạng thái policy engine và khả năng thực thi tại ứng dụng.

## 7. Kiểm thử SSO, SCIM và ứng dụng đích

**IdP/SSO:** xác minh group/role sau thay đổi, mapping claim mới, thời điểm refresh token và khả năng invalidate session. Một access token dạng JWT có thể tiếp tục được chấp nhận đến khi hết hạn nếu ứng dụng chỉ kiểm chữ ký; không giả định việc gỡ group tự vô hiệu mọi token. Đặt ngưỡng thu hồi theo kiến trúc và SLA thực tế.

**SCIM:** kiểm tra thay đổi thuộc tính người dùng, group membership và trạng thái các ứng dụng. SCIM có thể dùng PATCH/PUT tùy khả năng máy chủ. Ví dụ minh họa gỡ một thành viên khỏi group bằng SCIM PATCH:

~~~http
PATCH /scim/v2/Groups/group-sales
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"user-204\"]"
    }
  ]
}
~~~

Payload minh họa phụ thuộc khả năng SCIM của ứng dụng; cần xác nhận server hỗ trợ filter trong PATCH path. Sau thay đổi, gọi GET group và kiểm quyền tại ứng dụng. Nếu server trả timeout sau khi đã áp dụng thay đổi, retry phải idempotent hoặc có bước lookup/reconcile để tránh kết quả sai.

**Ứng dụng cục bộ:** một số ứng dụng dùng role nội bộ, không đồng bộ hoàn toàn từ SCIM. Kiểm thử qua API hoặc giao diện admin và thử thao tác thực tế; nếu phải dùng ticket vận hành, xác minh trạng thái đích thay vì chỉ dựa vào trạng thái ticket.

## 8. Mover bất đồng bộ, đảo thứ tự và khả năng phục hồi

Sự kiện có thể bị giao trùng, đến sai thứ tự hoặc bị kẹt ở một connector. Một chuỗi nguy hiểm:

~~~text
t1: MOVER(version=12, SALES -> FINANCE) được xử lý
t2: LEAVER(version=13) đã vô hiệu hóa truy cập
t3: MOVER(version=11) đến muộn và cố cấp lại SALES

Kỳ vọng: trạng thái LEAVER vẫn chi phối; không được cấp lại SALES.
~~~

Kiểm thử trạng thái cuối cùng dựa trên version/sequence tin cậy hoặc cơ chế kiểm tra dữ liệu nguồn tại thời điểm thực thi. Không dùng thứ tự nhận event trong queue làm bằng chứng duy nhất cho thứ tự nghiệp vụ.

Khi một connector lỗi, hệ thống cần thể hiện phần nào đã áp dụng, phần nào chưa, retry bao nhiêu lần và ai chịu trách nhiệm khắc phục. Nếu lỗi thu hồi quyền nhạy cảm kéo dài, kiểm thử cảnh báo và cơ chế chặn bổ sung theo chính sách. Sau replay hay sửa lỗi, đối soát toàn bộ tập quyền để chắc chắn không còn grant dư.

~~~mermaid
sequenceDiagram
    participant H as HRIS
    participant I as IAM
    participant D as IdP
    participant A as Application
    H->>I: MOVER v12 (Sales -> Finance)
    I->>D: Remove Sales / Add Finance
    D-->>I: Updated
    I->>A: Synchronize changes
    A--xI: Timeout
    I->>A: Read current roles
    A-->>I: Sales still present
    I->>A: Retry removal and add
    A-->>I: Success
    I->>A: Verify effective access
    A-->>I: Finance allowed, Sales denied
~~~

## 9. Ví dụ tự động hóa kiểm thử Mover

Mã giả Python sau mô tả một integration test. Các client và `eventually` là abstraction trong test harness, không phải API tích hợp sẵn:

~~~python
def test_sales_to_finance_revokes_old_access(hris, iam, idp, crm, finance, policy):
    person_id = "person-204"
    before = crm.effective_permissions(person_id)
    assert "crm.customer.read.vn" in before

    event = {
        "eventId": "mover-204-v12",
        "personId": person_id,
        "type": "MOVER",
        "version": 12,
        "department": "FINANCE",
        "effectiveAt": policy.test_effective_at,
        "approved": True,
    }
    hris.publish(event)

    eventually(
        lambda: finance.authorize(person_id, "finance.report.read") == "ALLOW",
        timeout_seconds=policy.mover_grant_sla_seconds,
    )
    eventually(
        lambda: crm.authorize(person_id, "crm.customer.read.vn") == "DENY",
        timeout_seconds=policy.mover_revoke_sla_seconds,
    )
    assert crm.authorize(person_id, "crm.export.all") == "DENY"
    assert iam.audit_contains(event_id=event["eventId"])

    hris.publish(event)  # Kiểm thử idempotency.
    eventually(
        lambda: idp.count_by_person_id(person_id) == 1,
        timeout_seconds=policy.mover_grant_sla_seconds,
    )
~~~

Trong test thực tế, cần dùng API với phiên người dùng hoặc token thật để xác minh authorization. Nếu quyền được cache, thực hiện thêm một test qua session phát hành trước Mover; test chỉ tạo session mới có thể bỏ sót quyền tồn dư.

## 10. Kiểm thử chuyển giao quyền sở hữu tài khoản dịch vụ

Khi Mover thay đổi người chịu trách nhiệm hệ thống, kiểm tra account owner, quyền truy cập secret, quyền quản lý automation và cơ chế bàn giao. Tài khoản dịch vụ không nhất thiết phải bị xóa khi một nhân viên chuyển vai trò; nhưng người cũ phải mất quyền điều khiển nếu không còn nhiệm vụ, người mới chỉ nhận quyền đã được duyệt.

Ví dụ một kỹ sư chuyển khỏi nhóm Platform: quyền đọc secret của bot deploy phải được thu hồi, owner mới được gán, credential có thể cần rotation theo chính sách. Thử lại quyền đọc secret và API deploy bằng thông tin đăng nhập cũ để phát hiện đường truy cập còn tồn tại. Bảo đảm công việc tự động vẫn vận hành theo ownership và phân quyền mới.

## 11. Audit, reconciliation và tiêu chí PASS

Đối với mỗi Mover, cần giữ các chứng cứ:

1. **Intent:** sự kiện nguồn, người dùng, thời điểm hiệu lực, trạng thái cũ/mới, version và phê duyệt.
2. **Policy:** tập quyền kỳ vọng trước/sau, căn cứ role/attribute và ngoại lệ đã duyệt.
3. **Execution:** correlation ID, log IdP/SCIM, lỗi, retry và kết quả tại từng đích.
4. **Observed access:** readback membership, quyền ứng dụng, kết quả thử ALLOW/DENY và session còn tồn tại.
5. **Timeliness:** thời điểm cấp quyền mới, thu hồi quyền cũ và thời gian hội tụ so với SLA.

~~~text
unexpected = actual_effective_grants - approved_effective_grants
missing    = approved_required_grants - actual_effective_grants

PASS nếu unexpected = {} và missing = {}
     đồng thời mọi thử truy cập bị cấm đều DENY trong SLA.
~~~

Chú ý không ghi access token, password, secret và dữ liệu cá nhân không cần thiết vào log. Khi đối soát phát hiện quyền tồn dư, cần tạo finding, chỉ định owner xử lý và readback sau khi sửa; không đánh dấu test PASS chỉ vì workflow provisioning trả thành công.

## 12. Bài thực hành

Giả lập nhân viên `person-204` chuyển Sales VN sang Finance ngày 10/12/2026. Trước Mover người dùng được xem CRM VN; sau Mover được xem báo cáo Finance và không được đọc CRM VN. Hãy:

1. Xây dựng tập quyền trước/sau, bao gồm quyền trực tiếp, nhóm lồng nhau và thuộc tính ABAC.
2. Thực hiện Mover hợp lệ, kiểm tra quyền Finance ALLOW và CRM DENY tại API thật.
3. Cố tình giữ một role Sales cục bộ trong CRM, xác minh reconciliation phát hiện grant dư.
4. Phát lại sự kiện Mover, gửi event phiên bản cũ sau phiên bản mới và kiểm tra idempotency.
5. Giả lập Leaver xảy ra trước khi Mover cũ được xử lý; chứng minh sự kiện cũ không kích hoạt lại tài khoản.
6. Thử một session SSO tạo trước Mover; đo thời gian đến khi quyền cũ bị từ chối theo SLA.

Đưa kết quả vào bảng `caseId, expected, actual, observedAt, evidence, outcome, remediation`. Phân tích sai lệch theo nguồn HRIS, bộ tính entitlement, IdP, SCIM hoặc ứng dụng. Kiểm thử Mover đạt mục tiêu khi **quyền mới đủ dùng, quyền cũ không còn hiệu lực và không xuất hiện tích lũy quyền qua các lần thay đổi vai trò**.
