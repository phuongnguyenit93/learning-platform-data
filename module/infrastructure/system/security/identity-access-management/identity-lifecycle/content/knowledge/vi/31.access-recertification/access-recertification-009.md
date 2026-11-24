# Đo tỷ lệ hoàn tất trong Access Recertification

> **Chương:** Access recertification
>
> **Bài:** Đo tỷ lệ hoàn tất
>
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE
>
> **Bối cảnh:** Quản lý vòng đời danh tính trong IAM theo mô hình **Joiner–Mover–Leaver (JML)**, kết nối HRIS, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán để giảm quyền truy cập tồn dư.

## 1. Tại sao phải đo tỷ lệ hoàn tất?

Doanh nghiệp mở một chiến dịch **Access Recertification** để rà soát 120 quyền truy cập. Cuối kỳ, hệ thống hiển thị 100 quyền đã có quyết định của người duyệt. Dashboard ghi “83,3% hoàn tất”.

Con số này có thể **đúng nhưng chưa đủ**. Nếu 26 quyết định yêu cầu thu hồi hoặc điều chỉnh quyền mà chỉ 19 trường hợp được thực thi và xác minh ở hệ thống đích, việc người duyệt đã bấm nút không đồng nghĩa rủi ro đã được giải quyết.

**Đo tỷ lệ hoàn tất (completion rate measurement)** trong Access Recertification là thiết kế và tính toán các chỉ số cho biết **bao nhiêu đối tượng rà soát đã đạt từng trạng thái cần thiết**, so với phạm vi phải hoàn tất, tại một thời điểm đo xác định.

Cần tách ít nhất ba câu hỏi:

1. **Review completion:** Người có thẩm quyền đã đưa ra quyết định trên bao nhiêu quyền?
2. **Timeliness:** Bao nhiêu quyết định đã được đưa ra trước hạn?
3. **End-to-end closure:** Bao nhiêu quyền đã được quyết định, xử lý và kiểm chứng đúng theo quyết định, kể cả thu hồi hoặc sửa quyền ở target?

Ngoài ra cần đánh giá **coverage**, mức độ ưu tiên quyền rủi ro cao và các trường hợp chưa thể xác minh.

### 1.1. Ví dụ ngắn

| Kết quả chiến dịch | Số lượng |
|---|---:|
| Quyền thuộc phạm vi phải review | 120 |
| Quyền có quyết định hợp lệ | 100 |
| Quyết định hợp lệ trước deadline | 90 |
| Quyết định KEEP/RETAIN | 74 |
| Quyết định REVOKE | 16 |
| Quyết định MODIFY | 10 |
| REVOKE/MODIFY đã xác minh xử lý | 19 |

Nếu 74 quyết định giữ quyền có approval hợp lệ và không yêu cầu sửa target, ta có:

- **Tỷ lệ hoàn tất quyết định:** 100 / 120 = **83,33%**.
- **Tỷ lệ quyết định đúng hạn trên toàn phạm vi:** 90 / 120 = **75%**.
- **Tỷ lệ xử lý hậu quyết định:** 19 / (16 + 10) = **73,08%**.
- **Tỷ lệ đóng vòng đầy đủ:** (74 + 19) / 120 = **77,5%**, với điều kiện 74 KEEP đã đạt các bước xác minh cần thiết.

Các con số minh họa được tính theo **cùng một snapshot và cùng quy tắc đếm**, không phải số liệu thật của một tổ chức.

## 2. Access Recertification là gì?

**Access Recertification** là hoạt động định kỳ hoặc theo sự kiện nhằm xác nhận rằng **các quyền hiện đang tồn tại vẫn cần thiết, đúng chủ thể, đúng phạm vi và phù hợp chính sách**.

Một chiến dịch có thể yêu cầu manager, application owner, data owner hoặc role owner quyết định về:

- Role RBAC, group membership và direct entitlement.
- Quyền trên ứng dụng SaaS, cloud IAM, repository hoặc database.
- Resource scope, tenant, project, region và data classification.
- Tài khoản đặc quyền và service principal.
- Quyền của contractor, guest, external partner.
- Quyền còn lại sau Mover/Leaver hoặc khi hợp đồng hết hạn.
- Các ngoại lệ và grant tạm có thời hạn.

### 2.1. “Reviewed” không nhất thiết “Remediated”

Nếu một entitlement được đánh dấu **REVOKE**, reviewer đã hoàn tất **quyết định**, nhưng hệ thống đích có thể vẫn cho phép truy cập. Đó là khác biệt giữa hoàn tất thao tác quản trị và hoàn tất mục tiêu an ninh.

### 2.2. Mục tiêu cuối cùng

Access recertification phải giúp phát hiện **quyền không còn căn cứ**, quyền quá rộng, xung đột SoD, orphan accounts và residual access. Tỷ lệ completion là một tín hiệu vận hành; nó không tự chứng minh toàn bộ quyền còn lại đều đúng.

## 3. Đơn vị đếm: review item là gì?

Muốn có tỷ lệ đáng tin, phải xác định **mỗi “1” trong tử số/mẫu số đại diện cho điều gì**.

Một **review item** có thể là:

- Một cặp **subject–entitlement** tại ứng dụng/tenant.
- Một grant trên resource instance cụ thể.
- Một role assignment tại cloud project.
- Một direct ACL được cấp cho tài liệu.
- Một service principal có role trên API/resource.
- Một tập entitlement được nhóm lại có kiểm soát.

**Không tự đồng nhất:** số nhân viên, số reviewer, số access requests, số account và số entitlement. Một người có thể có 15 quyền cần xét; một quyết định của reviewer có thể ảnh hưởng nhiều quyền nếu hệ thống hỗ trợ group review.

### 3.1. Khóa định danh review item

Ví dụ một khóa logic:

~~~text
campaignId
snapshotId
reviewItemId
principalId / principalType
targetSystemId
tenantId
entitlementId
resourceScopeId
grantSource
~~~

Có thể dùng ID riêng thay cho khóa ghép dài; các trường ngữ nghĩa giúp xác minh **không đếm trùng** khi cùng quyền xuất hiện qua nhiều nguồn.

### 3.2. Một quyền qua nhiều đường cấp

Một subject có thể được đọc tài liệu qua group A và direct ACL B. Nếu chỉ rà soát group A, user vẫn có thể đọc qua B. Tùy mục tiêu chiến dịch, cần định nghĩa:

- **Assignment-level review:** rà soát từng grant source riêng.
- **Effective-access review:** rà soát khả năng thực tế truy cập resource.
- **Role/group ownership review:** rà soát thiết kế/owner của role.

Không cộng các loại đơn vị khác nhau vào một tỷ lệ nếu chưa quy đổi và công bố cách đếm.

### 3.3. Reviewer task khác review item

Một reviewer được giao một task chứa 20 entitlement. Reviewer bấm “hoàn tất task” khi mới xử lý 18 item là tình huống hệ thống phải kiểm tra. **Task completion rate** và **item decision completion rate** cần tách biệt.

## 4. Thiết kế trạng thái vòng đời một review item

Một state model minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> IN_SCOPE
    IN_SCOPE --> ASSIGNED: Phân công reviewer
    ASSIGNED --> IN_REVIEW: Đang đánh giá
    IN_REVIEW --> DECIDED_KEEP: Giữ quyền
    IN_REVIEW --> DECIDED_REVOKE: Thu hồi
    IN_REVIEW --> DECIDED_MODIFY: Điều chỉnh
    IN_REVIEW --> ESCALATED: Thiếu căn cứ hoặc xung đột
    DECIDED_KEEP --> VERIFIED_CLOSED: Kiểm tra đủ điều kiện
    DECIDED_REVOKE --> REMEDIATING: Gửi xử lý ở target
    DECIDED_MODIFY --> REMEDIATING: Sửa scope/quyền
    REMEDIATING --> VERIFYING: Readback
    VERIFYING --> VERIFIED_CLOSED: Đúng trạng thái mong muốn
    VERIFYING --> PARTIAL: Còn quyền hoặc lỗi xác minh
    PARTIAL --> REMEDIATING: Khắc phục
    ESCALATED --> IN_REVIEW: Có quyết định hợp lệ
    VERIFIED_CLOSED --> [*]
~~~

Tên trạng thái là **ví dụ học tập**, không phải chuẩn API của sản phẩm IAM. Mỗi workflow cần công bố rõ trạng thái nào được tính là:

- **Decision completed**.
- **Remediation required**.
- **Remediation verified**.
- **End-to-end closed**.
- **Blocked/escalated**.

### 4.1. Không để auto-close che quyết định thiếu

Nếu sau deadline hệ thống tự đánh dấu tất cả request là APPROVED/KEEP mà không có người có thẩm quyền xác nhận, không nên gọi đó là “100% reviewer completion”. Phải phân biệt **auto-decision theo rule được quản trị** với **reviewer decision thực tế** và ghi rõ provenance.

### 4.2. “Không áp dụng” cần bằng chứng

Review item có thể bị đánh dấu NOT_APPLICABLE khi grant đã bị xóa hợp lệ hoặc snapshot ban đầu sai. Không loại khỏi mẫu số âm thầm; cần reason, owner, time và policy về điều chỉnh phạm vi.

## 5. Mẫu số: tổng số gì cần hoàn tất?

Công thức đơn giản:

~~~text
Completion rate (%) = Numerator / Denominator * 100
~~~

**Mẫu số (denominator)** phải là **số đơn vị rà soát nằm trong phạm vi được xác định theo quy tắc rõ ràng**, không phải “những item còn hiển thị trên màn hình hôm nay”.

Một chiến dịch có thể chọn:

- **Frozen cohort:** chụp snapshot quyền tại ngày bắt đầu và giữ tập item làm mẫu số lịch sử.
- **Rolling cohort:** cập nhật khi quyền/user/target mới xuất hiện, có định nghĩa ngày cutoff và cohort.
- **Hybrid:** giữ cohort gốc để báo cáo cam kết, đồng thời có cohort bổ sung cho grant mới xuất hiện.

### 5.1. Vì sao cần frozen denominator?

Nếu chiến dịch mở với 120 item, 20 item quá hạn bị ẩn/xóa khỏi queue, dashboard chỉ còn 100 item và tuyên bố 100/100 = 100%, đó là **mẫu số bị co để làm đẹp tỷ lệ**.

Một cách an toàn:

- Cố định cohort ban đầu với snapshot ID.
- Ghi rõ trường hợp invalid/cancelled/excluded, **không xóa dấu vết**.
- Theo dõi baseline và adjusted denominator song song nếu cho phép điều chỉnh.
- Báo cáo số item được bổ sung sau snapshot trong cohort riêng.

### 5.2. Entitlement biến mất trước khi reviewer xét

Nếu SCIM/Leaver đã gỡ một grant sau snapshot:

- Không chỉ xóa item khỏi dashboard.
- Có thể ghi resolution loại PREEMPTIVE_REVOKE theo policy.
- Xác minh grant thực sự đã mất tại target.
- Công bố item đó được tính vào chỉ số nào, có cần reviewer xác nhận hay không.

Nếu không có chứng cứ, “quyền không còn trong feed” chưa đủ để coi review hoàn tất.

### 5.3. Item invalid thật sự

Ví dụ một entitlement record bị tạo trùng do lỗi import. Policy có thể cho loại khỏi adjusted denominator sau khi được kiểm chứng. Báo cáo nên hiển thị:

~~~text
Original snapshot items = 120
Verified duplicate exclusions = 2
Approved adjusted denominator = 118
Open exclusions needing validation = 1 (vẫn tính vào phạm vi tạm thời)
~~~

Không chuyển pending exclusion thành đã loại chỉ vì người dùng chọn một reason trong UI.

## 6. Chỉ số 1: Decision Completion Rate

**Decision Completion Rate** đo tỷ lệ các review item thuộc phạm vi đã có **quyết định hợp lệ theo policy**, bất kể việc thực thi quyết định ở target đã xong hay chưa.

~~~text
Decision Completion Rate (%) =
    Validly Decided Review Items
    / In-Scope Review Items
    * 100
~~~

Ví dụ:

~~~text
In-scope = 120
Valid decisions = 100

Decision Completion Rate = 100 / 120 * 100 = 83.33%
~~~

### 6.1. Quyết định hợp lệ cần điều kiện gì?

Có thể cần:

1. Reviewer có thẩm quyền trên item tại thời điểm đưa ra quyết định.
2. Decision thuộc tập trạng thái được hỗ trợ: KEEP, REVOKE, MODIFY hoặc loại khác có ngữ nghĩa rõ.
3. Scope và beneficiary được xác định.
4. Đáp ứng SoD: người review không tự chứng nhận quyền nhạy cảm của chính mình nếu policy cấm.
5. Có timestamp, policy version, reason khi bắt buộc.
6. Quyết định không bị hủy/superseded chưa được xử lý.

Một click “Save draft” hoặc một reviewer mở item xem không nên tính là valid decision.

### 6.2. Chỉ số theo số reviewer khác theo số item

Ba reviewer phụ trách lần lượt 100, 10 và 10 items. Hai reviewer xử lý xong toàn bộ nhưng reviewer phụ trách 100 items chưa xử lý:

- Tỷ lệ reviewer đã hoàn thành task: 2/3 = 66,67%.
- Tỷ lệ item hoàn tất: 20/120 = 16,67%.

Cả hai có thể hữu ích, nhưng phải ghi rõ khác đơn vị.

### 6.3. Chỉ số phản hồi reviewer

Có thể theo dõi response rate riêng: số review item đã được reviewer chạm tới hoặc task đã được mở. Response không đồng nghĩa valid decision; đừng dùng “seen/opened” làm completion.

## 7. Chỉ số 2: On-Time Decision Completion Rate

**On-time** là chỉ số về **đúng hạn ra quyết định**, không chỉ về số quyết định đã có.

Hai mẫu số thông dụng có ý nghĩa khác:

~~~text
On-time vs scope (%) =
    Valid decisions made by dueAt
    / In-scope review items
    * 100

On-time among decided (%) =
    Valid decisions made by dueAt
    / All valid decisions made
    * 100
~~~

Ví dụ với 120 item, 100 valid decisions, 90 đúng hạn:

- On-time vs scope = 90/120 = **75%**.
- On-time among decided = 90/100 = **90%**.

**Không nên chỉ hiển thị 90%** nếu 20 item chưa có quyết định, vì chỉ số đó che phần backlog chưa review.

### 7.1. Deadline chung và deadline riêng

Một campaign có dueAt cuối tháng; item nhạy cảm có thể yêu cầu deadline riêng ngắn hơn. Để tính on-time phải so với **deadline áp dụng cho item đó**, không dùng một thời điểm tùy ý.

### 7.2. Gia hạn deadline

Nếu campaign được gia hạn, cần lưu originalDueAt và currentDueAt, approval của thay đổi và báo cáo cả kết quả theo hạn gốc khi cần. Không được chỉnh dueAt ngược về sau rồi tuyên bố toàn bộ quyết định luôn đúng hạn.

### 7.3. Không đánh đồng late-completed và uncompleted

Một review item hoàn tất muộn vẫn có thể làm tăng decision completion nhưng **không được tính on-time** so với deadline ban đầu, trừ khi chính sách đã định nghĩa rõ cách gia hạn hợp lệ.

## 8. Chỉ số 3: Remediation Completion Rate

Một review item có quyết định REVOKE hoặc MODIFY thường cần thực thi thay đổi ở target.

~~~text
Remediation Completion Rate (%) =
    Remediation-required Items Verified at Target
    / All Remediation-required Items
    * 100
~~~

Ví dụ:

~~~text
REVOKE = 16
MODIFY = 10
Total needing remediation = 26

Verified remediation = 19
Remediation Completion = 19 / 26 * 100 = 73.08%
~~~

### 8.1. Đừng dùng “lệnh gửi thành công” làm đã xử lý

Một SCIM PATCH trả 200 nhưng role local còn hiệu lực không được coi là verified. Cần đọc lại effective grants hoặc dùng test hành vi có kiểm soát.

### 8.2. MODIFY có thể gồm nhiều thay đổi

Quyết định MODIFY từ global-admin xuống project-viewer chỉ hoàn tất khi **quyền cũ rộng đã bị thu hồi** và **quyền mới đúng scope** đã được kiểm chứng. Cấp viewer mới thành công nhưng global-admin vẫn còn là PARTIAL.

### 8.3. Không chia cho toàn bộ campaign khi đo remediation

Nếu mẫu số là 120 mà chỉ 26 item cần thay đổi, lấy 19/120 không phản ánh hiệu quả thực thi những việc được giao. Chỉ số này phải có mẫu số **số item bắt buộc remediation**.

### 8.4. Không có việc cần sửa

Khi không có item nào cần remediation, mẫu số bằng 0. Chỉ số **không áp dụng (N/A)** thay vì ghi 100% một cách máy móc. Có thể ghi “0/0 — no remediation required”.

## 9. Chỉ số 4: End-to-End Verified Closure Rate

Đây là chỉ số phản ánh **quyền đã đi hết vòng recertification**, không chỉ được reviewer quyết định.

Một item được coi **verified closed** khi:

- Nếu KEEP: quyết định hợp lệ và các kiểm tra bắt buộc (nếu có) đã đạt; quyền hiện hữu phù hợp policy.
- Nếu REVOKE: quyền cần thu hồi không còn hiệu lực tại target theo bằng chứng.
- Nếu MODIFY: quyền cũ được gỡ/sửa đúng và quyền mục tiêu được xác minh.
- Nếu disposition khác: thỏa quy trình đóng tương ứng, không chỉ đổi status.

~~~text
End-to-End Verified Closure Rate (%) =
    Verified Closed In-Scope Review Items
    / In-Scope Review Items
    * 100
~~~

Theo ví dụ đầu bài, giả sử 74 KEEP đáp ứng các bước xác minh cần thiết và 19 trong 26 thay đổi đã verified:

~~~text
Verified closed = 74 + 19 = 93
Denominator = 120

End-to-end closure = 93 / 120 * 100 = 77.50%
~~~

### 9.1. Vì sao khác decision completion?

- 100 item đã có quyết định.
- 93 item đã hoàn tất vòng đời end-to-end.
- 7 item đã quyết định nhưng chờ remediation/verification.
- 20 item chưa có quyết định hợp lệ.

Đó là thông tin hành động cụ thể hơn một dòng “83,3% completed”.

### 9.2. KEEP vẫn có điều kiện

Không coi mọi KEEP là verified chỉ vì bấm nút. Với quyền nhạy cảm, có thể cần reviewer authority, SoD, owner, data classification và kiểm tra status của identity hoặc grant.

## 10. Không cộng hoặc trộn những tỷ lệ khác đơn vị

Có một số chỉ số dễ bị gộp nhầm:

| Tên | Tử số | Mẫu số |
|---|---|---|
| Decision completion | Item có quyết định hợp lệ | Review item in-scope |
| On-time completion vs scope | Item quyết định đúng hạn | Review item in-scope |
| Reviewer task completion | Task reviewer hoàn tất | Reviewer tasks được giao |
| Remediation completion | Item cần remediation đã verified | Item cần remediation |
| End-to-end closure | Item đã đóng vòng đầy đủ | Review item in-scope |
| Coverage | Access assignments được đưa vào phạm vi kiểm soát | Assignments có thể review trong inventory |
| Exception resolution | Exception đã xử lý/được duyệt đúng | Exception cần xử lý |
| High-risk closure | High-risk item verified closed | High-risk item in-scope |

Không lấy trung bình số học các tỷ lệ trên rồi gọi “overall completion” nếu không có mô hình tổng hợp rõ ràng; chúng đo **những giai đoạn hoặc tập đối tượng khác nhau**.

### 10.1. Completion khác correctness

Một reviewer có thể giữ lại tất cả quyền trong thời gian kịp hạn, đạt 100% decision completion, nhưng vẫn bỏ sót quyền quá rộng. Completion đo **tiến độ quy trình**, không tự đo chất lượng quyết định.

### 10.2. Recertification không thay continuous IAM

Access reviews định kỳ không thể thay thu hồi ngay khi Leaver, incident, mất thiết bị hoặc contract end. Completion cao không chứng minh độ trễ thu hồi theo JML đã đáp ứng SLA.

## 11. Phân tầng theo rủi ro và quyền đặc quyền

Một tỷ lệ 95% toàn chiến dịch có thể gây hiểu nhầm nếu 5% chưa hoàn tất lại gồm **mọi quyền production-admin, payment-approver hoặc truy cập dữ liệu nhạy cảm**.

Vì vậy nên báo cáo song song:

- Completion cho **high-risk** và **critical-risk** items.
- Completion theo privileged roles và tài khoản dịch vụ.
- Completion theo target system, tenant, business unit, data classification.
- Số item critical chưa quyết định và số remediation chưa verified.
- Tuổi của các item quá hạn; item nào tạo rủi ro lớn nhất.

### 11.1. High-Risk Decision Completion

~~~text
High-Risk Decision Completion (%) =
    High-Risk Items with Valid Decisions
    / All High-Risk In-Scope Items
    * 100
~~~

Ví dụ 30 item high-risk, 24 đã có quyết định hợp lệ:

~~~text
24 / 30 * 100 = 80%
~~~

### 11.2. High-Risk End-to-End Closure

Giả sử trong 24 quyết định của high-risk cohort có 18 KEEP hợp lệ và 6 cần remediation. Đã xác minh 4 trong 6 trường hợp remediation:

~~~text
High-risk verified closed = 18 + 4 = 22
High-risk closure = 22 / 30 = 73.33%
~~~

Tỷ lệ 73,33% high-risk closure quan trọng hơn việc toàn chiến dịch có 90% quyết định. Các nhóm cần áp dụng cùng quy tắc trạng thái và mẫu số.

### 11.3. Tỷ lệ có trọng số rủi ro

Nếu tổ chức muốn một chỉ số phụ, có thể định nghĩa **risk-weighted completion**:

~~~text
Weighted Completion (%) =
    SUM(weight(item) * completedIndicator(item))
    / SUM(weight(item))
    * 100
~~~

Trong đó indicator là 1 khi item đạt **một trạng thái cụ thể** (ví dụ verified closed), ngược lại là 0.

Ví dụ trọng số do tổ chức tự quản trị:

| Risk tier | Trọng số minh họa |
|---|---:|
| Critical | 8 |
| High | 4 |
| Medium | 2 |
| Low | 1 |

**Đây không phải bộ trọng số chuẩn của IAM.** Trọng số phải có chủ sở hữu, phiên bản, căn cứ rủi ro và không được thay lén giữa các chiến dịch. Luôn hiển thị tỷ lệ thô và số lượng pending song song.

### 11.4. Không dùng weighted rate để che số tuyệt đối

Weighted completion 97% có thể vẫn chứa hai credential production-admin chưa thu hồi. Dashboard cần hiển thị **số lượng và danh sách ngoại lệ critical** ngoài tỷ lệ.

## 12. Coverage: có đưa đủ quyền vào đợt rà soát không?

Một campaign đạt 100% completion trên 50 quyền nhưng inventory thực có 500 quyền thì vẫn bỏ sót phần lớn bề mặt truy cập.

**Review Coverage Rate** là một KPI độc lập:

~~~text
Coverage (%) =
    Distinct Reviewable Grants Represented in Campaign
    / All Eligible Reviewable Grants in Defined Inventory
    * 100
~~~

Ví dụ inventory có 500 assignments trong phạm vi đã công bố, campaign chỉ chứa 450 assignment hợp lệ:

~~~text
Coverage = 450 / 500 * 100 = 90%
~~~

Khi 450 item đều đã reviewed, decision completion trong campaign = 100%, nhưng **coverage chỉ 90%**. Không nên kết luận “tất cả quyền trong công ty đã được rà soát”.

### 12.1. Inventory và blind spots

Nguồn quyền có thể gồm:

- IdP group, nested groups, SaaS role mapping.
- SCIM User/Group tại target.
- Local account và direct role ngoài IdP.
- Cloud IAM binding, resource policies, database grants.
- ACL cấp trực tiếp, share links, delegated rights.
- Accounts của guest, contractor, service principal, workload.
- Privileged accounts và break-glass entitlements.
- Legacy access không có owner hoặc connector.

Không có một SCIM feed nào tự chứng minh inventory toàn diện nếu ứng dụng còn quyền local hoặc API keys riêng.

### 12.2. Phân biệt account và entitlement

Một account chưa có entitlement thuộc loại cần review có thể không tạo review item tương ứng, nhưng vẫn nằm trong account inventory. Vì vậy coverage phải nói rõ là **coverage quyền**, **coverage tài khoản** hay **coverage hệ thống**.

### 12.3. Quyền kế thừa

Nếu quyền cấp qua parent group hoặc folder, cần biết campaign review grant source hay effective access. Không đếm cùng một quyền hai lần hoặc bỏ qua một đường grant chỉ vì quyền đã được nhìn thấy qua đường khác.

## 13. Phân công reviewer và trách nhiệm hoàn tất

Không có quyết định hợp lệ nếu người đưa ra quyết định không có thẩm quyền hoặc không hiểu tài nguyên.

Các vai trò thường gặp:

| Reviewer | Điểm mạnh | Điểm cần cảnh giác |
|---|---|---|
| Manager | Biết nhu cầu công việc của nhân viên | Có thể không biết chi tiết app role |
| Application owner | Biết chức năng của ứng dụng | Không luôn biết nhu cầu cá nhân |
| Data owner | Biết độ nhạy cảm và phạm vi dữ liệu | Có thể không nắm mọi group mapping |
| Role owner | Hiểu role và quyền kế thừa | Cần đối chiếu business justification |
| Privileged access owner | Biết rủi ro admin | Cần SoD và chứng cứ bổ sung |
| Workload owner | Biết job/production dependencies | Có thể đã chuyển team hoặc Leaver |

### 13.1. Unassigned reviewer không phải item ngoài mẫu số

Nếu một entitlement thiếu owner nên không biết giao ai, đó là vấn đề quản trị. Item vẫn cần có trạng thái **UNASSIGNED** hoặc **BLOCKED_OWNER_MISSING**, không bị xóa khỏi denominator để cải thiện completion.

### 13.2. Delegation của reviewer

Khi reviewer nghỉ phép, workflow có thể chỉ định người thay theo quy tắc có thẩm quyền và thời hạn. Phải lưu original reviewer, delegate, lý do và thời điểm. Không đồng nghĩa delegate được nhận quyền mà họ đang review.

### 13.3. SoD khi tự review quyền của bản thân

Nếu policy cấm self-certification đối với admin, một quyết định KEEP do chính người nhận role thực hiện không được tính valid. Chuyển cho reviewer độc lập; giữ lịch sử thay đổi, không âm thầm overwrite.

### 13.4. Escalation khi quá hạn

Mỗi task cần dueAt, owner, cấp escalation và cách reassign. Có thể báo cáo:

- Reviewer nào còn backlog.
- Item nào có risk cao và sắp đến hạn.
- Quyết định nào thiếu justification.
- Remediation nào vượt SLA.
- Blocker nào do thiếu reviewer, thiếu hệ thống đích hoặc dữ liệu không chính xác.

Không thay chất lượng review bằng việc gửi nhiều email nhắc.

## 14. Joiner–Mover–Leaver ảnh hưởng mẫu số và completion

JML tạo thay đổi ngay trong lúc chiến dịch đang chạy. Cần chính sách rõ về item biến động sau snapshot.

### 14.1. Joiner

Nhân viên mới vào trong kỳ campaign:

- Nếu campaign là **frozen cohort**, grant mới thường nằm trong **new-grant delta** hoặc đợt sau theo policy.
- Nếu là **rolling cohort**, item mới có thể được thêm vào denominator kèm thời gian gia nhập.
- Grant mới phải có approval/provisioning phù hợp; không dùng recertification thay cơ chế cấp quyền ban đầu.
- Không đưa quyền chưa có hiệu lực vào cùng mẫu số active assignments nếu metric định nghĩa chỉ quyền active.

### 14.2. Mover

Nhân viên đổi phòng ban, role, chi nhánh hoặc tenant trong kỳ:

1. IAM xử lý Mover theo thời điểm có thẩm quyền, không chờ chiến dịch kết thúc.
2. Grant cũ có thể bị revoke trước khi reviewer quyết định.
3. Review item snapshot cần có resolution minh bạch: quyết định của reviewer, auto-revocation theo policy hoặc cần xác minh.
4. Nếu có quyền mới, xác định chúng thuộc cohort hiện tại hay delta.
5. Không để Mover event cũ tái kích hoạt quyền đã bị thu hồi.

### 14.3. Leaver

Một user nghỉ giữa campaign:

- Leaver workflow phải xử lý account, group, role, session/token theo chính sách **ngay**.
- Review item thuộc người nghỉ không được xóa âm thầm khỏi báo cáo.
- Có thể coi item đã **verified revoked by lifecycle** nếu policy cho phép, bằng chứng target đủ; không tự biến thành KEEP của reviewer.
- Khi revoke chưa hoàn tất, trạng thái phải là PARTIAL/PENDING, không “resolved” chỉ vì HRIS ghi TERMINATED.

### 14.4. JML cutoff không chờ recertification

Access review là kiểm soát rà soát định kỳ. Leaver/Mover là sự kiện cần phản ứng theo SLA riêng; đạt 100% recertification không có nghĩa đã xử lý JML kịp thời.

## 15. Đối chiếu IdP, SSO, SCIM và quyền hiệu lực

Kiến trúc thường gặp:

~~~mermaid
flowchart TD
    HR[HRIS / JML Source] --> IAM[IAM / IGA Review Campaign]
    IDP[IdP: Identity and Groups] --> IAM
    IAM --> REVIEW[Reviewer Decisions]
    REVIEW --> QUEUE[Remediation Queue]
    QUEUE --> SCIM[SCIM / Target APIs]
    SCIM --> SAAS[SaaS Roles and Membership]
    IAM --> AUDIT[Audit / Metrics Store]
    SAAS --> VERIFY[Target Readback / Effective Access]
    VERIFY --> AUDIT
    IDP --> SSO[SSO / Authorization Server]
    SSO --> API[Resource API / Enforcement]
    API --> VERIFY
    AUDIT --> DASH[Completion Dashboard]
~~~

### 15.1. IdP group ≠ quyền thực tế trên SaaS

Đôi khi user bị gỡ khỏi group ở IdP nhưng vẫn có:

- Local role cấp trực tiếp.
- Nhóm khác cấp cùng role.
- Session/cookie hoặc token đã phát.
- API key hoặc delegated access.
- Direct ACL ở resource.

Khi review quyết định REVOKE, phải xác định điều kiện verified closure **theo đường cấp và action/resource cần thu hồi**.

### 15.2. SSO không thay quyết định recertification

Đăng nhập SSO thành công chỉ chứng minh điều kiện authentication theo hợp đồng. User vẫn có thể không đủ quyền trên resource sau khi reviewer yêu cầu revoke.

### 15.3. SCIM success ≠ closure

SCIM có thể cập nhật User/Group, nhưng không mặc định thu hồi mọi local grants, browser sessions hoặc token. HTTP success là bằng chứng **operation**, còn completion thực sự cần chứng cứ target phù hợp.

### 15.4. RBAC và ABAC trong review

- **RBAC:** reviewer có thể thấy role và group, nhưng cần hiểu role cấp những action nào.
- **ABAC:** quyết định còn phụ thuộc thuộc tính subject/resource/context, ví dụ department, region, classification, ownership.
- **Recertification:** cần biết role/grant có còn phù hợp và dữ liệu dùng quyết định có đủ mới.

Một role không đổi nhưng subject chuyển region vẫn có thể khiến effective access phải bị hạn chế.

## 16. Tài khoản dịch vụ, workload và guest trong chỉ số

Không nên chỉ tính employee accounts rồi tuyên bố chiến dịch đã hoàn tất cho **mọi identity**.

### 16.1. Service principals và workload identities

Một non-human identity có thể dùng:

- Cloud IAM role/binding.
- Client credentials và workload federation.
- mTLS certificate hoặc API keys.
- Secrets với quyền trên database/API.
- CI/CD runner hoặc batch service account.

Khi tính completion, mỗi principal/grant cần **owner chịu trách nhiệm review**, runtime dependencies và trạng thái vòng đời.

### 16.2. Owner nghỉ việc hoặc đổi đội

Nếu owner của service principal là nhân viên đã Leaver, item không được mặc định “N/A”. Cần **gán owner mới hoặc quyết định deprovision principal**, và xử lý grant không còn hợp lệ.

### 16.3. Credential TTL khác entitlement lifetime

Token workload sống 5 phút vẫn có thể liên tục được cấp mới nếu service principal còn role dài hạn. Review phải kiểm tra **grant và trust binding**, không chỉ thời hạn token.

### 16.4. Guest/contractor

Guest có thể được cấp quyền qua invitation, group, direct sharing. Cần tách:

- Ngày kết thúc hợp đồng/partnership.
- Thời hạn guest account.
- Thời hạn resource grant.
- Trạng thái của external IdP và session.

Một lời mời đã hết hạn không chứng minh quyền guest đã chấp nhận lời mời trước đó cũng hết.

### 16.5. Metric phân theo identity type

Dashboard nên có employee, contractor, guest, privileged và service/workload cohorts. Một nhóm 100% completion không bù được nhóm còn orphan-admin grants.

## 17. Chất lượng dữ liệu: đo gì khi trạng thái không chắc chắn?

Các nguồn có thể lệch nhau:

- IAM đánh dấu REVOKED nhưng target vẫn ACTIVE.
- Reviewer đã quyết định nhưng approval thiếu người có thẩm quyền.
- Snapshot có entitlement trùng.
- Subject ID bị tái sử dụng do mapping email.
- Group lồng không được expand đúng.
- SaaS API readback timeout.
- Policy/access catalog không ghi resource owner.
- Event Leaver đến muộn hoặc out-of-order.

### 17.1. Unknown không được tính như Success

Nếu target không trả dữ liệu, item ở trạng thái **UNKNOWN/PENDING_VERIFICATION**. Không tự gán VERIFIED chỉ vì không quan sát thấy quyền trong một response lỗi.

### 17.2. Dữ liệu thiếu reviewer

Item thiếu reviewer owner vẫn ở denominator hoặc được xử lý qua quy trình điều chỉnh phạm vi có kiểm chứng. Đây là **exception cần giải quyết**, không phải lý do để dashboard tự giảm total.

### 17.3. Bằng chứng từ cache có thể stale

Một lần đọc IAM cache mới không chứng minh SaaS target vừa cập nhật. Readback phải ghi **source, observedAt, sourceVersion** và cách kiểm tra hiệu lực, nhất là với tài nguyên nhạy cảm.

### 17.4. Không dùng email làm khóa identity bất biến

Email có thể đổi hoặc được tái cấp. Dùng immutable subject IDs và target resource IDs để tránh gán quyết định của người này sang người khác.

## 18. Snapshot, cohort và khả năng so sánh giữa các kỳ

Một chiến dịch nên công bố:

- Campaign ID, kỳ review, owner và target systems.
- SnapshotAt, scope rules, inventory source version.
- Original cohort size và adjusted cohort size.
- Quy tắc thêm/bớt item sau snapshot.
- DueAt, grace/extension rules và timezone.
- Định nghĩa states và outcome categories.
- Metric specification version.
- Data freshness và thời điểm dashboard as-of.

### 18.1. Frozen và rolling cohort có thể báo khác

Ví dụ:

~~~text
Ngày đầu: 120 item
Trong kỳ: 10 new grants, 5 grants đã revoke theo Leaver

Frozen cohort:
  vẫn theo 120 item ban đầu với resolution của 5 Leaver items

Rolling cohort:
  có thể trở thành 130 item nếu 10 new grants được đưa vào scope
  không đơn giản giảm mẫu số 5 item đã revoke
~~~

Cả hai có thể hợp lệ nếu định nghĩa và công bố rõ. Không so sánh hai campaign một cách vô điều kiện khi cohort/rule khác nhau.

### 18.2. Adjusted denominator phải có lịch sử

Nếu loại item trùng hoặc ngoài scope sau khi xác minh:

- Lưu original snapshot và exclusion event.
- Xác nhận lý do bởi authority.
- Ghi adjusted denominator.
- Không xóa audit trail của item.
- Không tính một yêu cầu exclusion chưa phê duyệt như đã loại.

### 18.3. Snapshot của dashboard khác snapshot inventory

Dashboard lúc 10:00 có thể gồm quyết định mới nhưng inventory chụp từ đầu tháng. Cần ghi rõ **as-of timestamp của trạng thái quyết định** và **snapshotAt của mẫu số**, tránh hiểu sai “dữ liệu mới nhất”.

## 19. Quyền tồn dư và việc xác minh REMEDIATION

**Remediation** là thực thi quyết định sửa hoặc thu hồi quyền; **verified remediation** là có bằng chứng target đã đạt trạng thái cần thiết.

Với quyết định REVOKE:

1. Gửi yêu cầu thu hồi cho đúng principal/tenant/entitlement.
2. Nhận operation response.
3. Readback actual grant/role/ACL ở hệ thống đích.
4. Nếu cần, thực hiện negative access test hợp lệ, có kiểm soát.
5. Kiểm tra phiên/token hoặc đường grant khác theo policy.
6. Ghi VERIFIED_CLOSED khi đủ, nếu không giữ PARTIAL.
7. Thực hiện retry/escalation nhưng không làm mất audit trail.

### 19.1. MODIFY cần kiểm tra hai phía

Thay đổi từ toàn bộ tenant sang chỉ một project:

- Quyền rộng cũ đã mất?
- Quyền hẹp mới đã được cấp?
- Đường access khác có còn quyền rộng?
- Những thay đổi phát sinh trong quá trình sửa có tác động ngoài scope không?

Chỉ khi đáp ứng expected state mới tính remediation completion.

### 19.2. Quyền tồn dư của Leaver

Account IdP disable không mặc định kết thúc local SaaS session. Một recertification item của Leaver có thể cần thêm xác minh app-specific revocation; đừng tính closed chỉ từ HRIS employmentStatus.

### 19.3. Đường cấp khác không phải lúc nào là lỗi

Nếu một quyền được cấp đồng thời bởi grant A và grant B hợp lệ, revoke A có thể hoàn tất mà user vẫn truy cập được nhờ B. Verification phải đánh giá **kỳ vọng permission tổng thể** và biết grant nào được rà soát, tránh báo false failure hoặc false success.

## 20. Dashboard và điều hành chiến dịch

Một dashboard hữu ích không chỉ có một vòng tròn phần trăm. Nó cần hiển thị **phạm vi, tiến độ, quá hạn, rủi ro và khả năng hoàn tất đóng vòng**.

| Hạng mục | Hiển thị đề xuất |
|---|---|
| Scope | Original/adjusted item count, coverage, as-of |
| Reviewer progress | Valid decisions, undecided, due/overdue |
| On-time | On-time vs scope, late decisions |
| Outcomes | KEEP, REVOKE, MODIFY, escalated |
| Remediation | Required, pending, verified, failed |
| End-to-end | Verified closed / in-scope |
| High-risk | Critical/high undecided và pending remediation |
| Ownership | Reviewer backlog, unassigned tasks |
| Data quality | Duplicate, unknown, stale source, target outage |
| JML | Mover/Leaver delta, premature active grants |
| Workloads | Orphan principal, missing owner, credential/grant drift |

### 20.1. Actionable backlog

Một bảng hành động nên có item ID, reviewer owner, target, risk tier, dueAt, state, blocker, next action và escalation owner. Số phần trăm chỉ có giá trị nếu người vận hành biết **cần xử lý cụ thể gì tiếp theo**.

### 20.2. Quyền rủi ro cao cần ưu tiên

Không ưu tiên chỉ theo số lượng. Một quyền admin production quá hạn có thể cần xử lý trước hàng chục viewer tasks ít rủi ro.

### 20.3. Theo dõi xu hướng nhưng không đổi định nghĩa lén

Muốn so sánh qua tháng/quý, cần giữ hoặc công bố thay đổi trong denominator, risk weights, completion state, target inventory và deadline rules. Không gọi tăng từ 80% lên 95% là cải thiện thực nếu kỳ mới bỏ bớt ứng dụng khó rà soát.

## 21. Thiết kế dữ liệu để tính tỷ lệ hoàn tất

Một bộ dữ liệu báo cáo có thể chứa:

| Thuộc tính | Mục đích |
|---|---|
| campaignId, snapshotId, reviewItemId | Định danh cohort và item |
| principalId, principalType, tenantId | Chủ thể hưởng quyền |
| targetSystemId, entitlementId, resourceScope | Quyền đang xét |
| reviewerId, reviewerAuthorityRef | Kiểm tra quyền quyết định |
| inScope, exclusionReason, exclusionApprovedAt | Quản trị mẫu số |
| snapshotAt, dueAt, validDecisionAt | Mốc báo cáo và đúng hạn |
| decisionType, decisionValidity | KEEP/REVOKE/MODIFY và hiệu lực |
| requiresRemediation | Có cần thay đổi target không |
| remediationRequestedAt, remediationVerifiedAt | Gửi lệnh và bằng chứng |
| verifiedClosedAt | Đã đóng vòng đầy đủ |
| riskTier, classification, privileged | Phân tầng rủi ro |
| sourceVersion, evidenceRef, policyVersion | Nguồn, audit và tái hiện |

### 21.1. Lưu cả event history

Một item có thể được KEEP, rồi phát hiện self-review vi phạm SoD, chuyển ESCALATED, được quyết định REVOKE và sau hai retry mới verified. Nếu chỉ lưu trạng thái cuối, khó kiểm toán ai quyết định gì, lúc nào và có đúng hạn hay không.

### 21.2. Tái hiện một bản báo cáo

KPI phải gắn với snapshot ID, metric definition version, timestamp as-of, deadline, exclusion rules, decision validity rules và nguồn dữ liệu. Báo cáo của hôm qua không được tự thay khi event mới đến nếu mục tiêu là tái hiện tại thời điểm đã chốt.

### 21.3. Quyền xem dữ liệu báo cáo

Danh sách privileged assignments là thông tin nhạy cảm. Dashboard cần được bảo vệ bởi RBAC/ABAC; audit không lưu token, password, secret hoặc dữ liệu cá nhân không cần thiết.

## 22. SQL mẫu cho bốn tỷ lệ chính

Ví dụ **PostgreSQL**, giả định bảng mỗi reviewItemId xuất hiện đúng một lần trong snapshot và các trường về quyết định/verification đã được xác minh upstream.

~~~sql
WITH scoped AS (
    SELECT
        review_item_id,
        due_at,
        valid_decision_at,
        requires_remediation,
        remediation_verified_at,
        verified_closed_at,
        risk_tier
    FROM recertification_items
    WHERE campaign_id = :campaignId
      AND snapshot_id = :snapshotId
      AND in_scope = TRUE
),
stats AS (
    SELECT
        COUNT(*) AS total_items,
        COUNT(*) FILTER (
            WHERE valid_decision_at IS NOT NULL
        ) AS decided_items,
        COUNT(*) FILTER (
            WHERE valid_decision_at IS NOT NULL
              AND valid_decision_at <= due_at
        ) AS ontime_items,
        COUNT(*) FILTER (
            WHERE requires_remediation = TRUE
        ) AS remediation_required,
        COUNT(*) FILTER (
            WHERE requires_remediation = TRUE
              AND remediation_verified_at IS NOT NULL
        ) AS remediation_verified,
        COUNT(*) FILTER (
            WHERE verified_closed_at IS NOT NULL
        ) AS verified_closed
    FROM scoped
)
SELECT
    total_items,
    decided_items,
    ontime_items,
    remediation_required,
    remediation_verified,
    verified_closed,
    ROUND(100.0 * decided_items
          / NULLIF(total_items, 0), 2) AS decision_pct,
    ROUND(100.0 * ontime_items
          / NULLIF(total_items, 0), 2) AS ontime_vs_scope_pct,
    ROUND(100.0 * remediation_verified
          / NULLIF(remediation_required, 0), 2) AS remediation_pct,
    ROUND(100.0 * verified_closed
          / NULLIF(total_items, 0), 2) AS verified_closure_pct
FROM stats;
~~~

**Giới hạn:** SQL không tự chứng minh reviewer đủ authority, readback thật sự xác minh target hoặc quyết định không bị superseded. Các trạng thái đã xác minh phải đến từ pipeline tin cậy.

### 22.1. Tránh đếm trùng do join

Một review item có thể có ba approval events và bốn remediation attempts. JOIN thẳng sẽ nhân số hàng, làm COUNT(*) sai. Cần lấy bản ghi hợp lệ duy nhất theo reviewItemId/snapshot, hoặc xác định đúng event version trước khi tổng hợp.

### 22.2. Mẫu số bằng 0

NULLIF trả NULL thay vì chia cho 0. Dashboard nên hiển thị N/A, không tự giả định 100% khi không có item trong phạm vi.

### 22.3. Phân nhóm rủi ro

~~~sql
SELECT
    risk_tier,
    COUNT(*) AS total_items,
    COUNT(*) FILTER (
        WHERE valid_decision_at IS NOT NULL
    ) AS decided_items,
    COUNT(*) FILTER (
        WHERE verified_closed_at IS NOT NULL
    ) AS closed_items
FROM recertification_items
WHERE campaign_id = :campaignId
  AND snapshot_id = :snapshotId
  AND in_scope = TRUE
GROUP BY risk_tier;
~~~

Risk tier ordering phải lấy từ risk catalog, không mặc định sort chữ cái là thứ tự mức độ rủi ro.

### 22.4. Lưu trạng thái as-of

Nếu báo cáo ở thời điểm 10:00, không được tính verification từ 10:05. Bảng chuẩn hóa cần xây dựng theo event-time cutoff hoặc snapshot phù hợp để đảm bảo kết quả tái hiện.

## 23. Pseudocode đo tiến độ đáng tin cậy

~~~text
function measureCampaign(campaignId, snapshotId, asOf):
    items = loadInScopeItems(campaignId, snapshotId, asOf)

    if items unavailable or scope unresolved:
        return METRIC_UNAVAILABLE_WITH_REASON

    total = uniqueCount(items.reviewItemId)
    decided = 0
    ontime = 0
    needsFix = 0
    fixVerified = 0
    closed = 0

    for item in items:
        if item.hasValidDecisionBy(asOf):
            decided += 1
            if item.validDecisionAt <= item.applicableDueAt:
                ontime += 1

        if item.requiresRemediationBy(asOf):
            needsFix += 1
            if item.hasTrustedTargetVerificationBy(asOf):
                fixVerified += 1

        if item.hasTrustedClosureBy(asOf):
            closed += 1

    return {
        decisionRate: ratioOrNA(decided, total),
        ontimeVsScope: ratioOrNA(ontime, total),
        remediationRate: ratioOrNA(fixVerified, needsFix),
        verifiedClosureRate: ratioOrNA(closed, total)
    }
~~~

Đây là mã giả. Một hệ thống thật cần xử lý quyết định bị thay thế, lifecycle auto-revocation, exclusions, nhiều grants và concurrency.

### 23.1. Bất biến đơn giản để phát hiện lỗi

Khi policy định nghĩa closed chỉ sau valid reviewer decision:

~~~text
0 <= closed <= decided <= total
0 <= ontime <= decided <= total
0 <= fixVerified <= needsFix
~~~

Nếu campaign có disposition lifecycle auto-revoked được phép đóng mà không cần reviewer decision, phải ghi **định nghĩa ngoại lệ** và điều chỉnh invariant công khai, không âm thầm gọi auto-revoke là reviewer response.

### 23.2. Event đến muộn

Một decision được thực hiện lúc 09:59, deadline 10:00 nhưng data warehouse nhận lúc 10:10. Policy phải xác định on-time dựa trên **decision timestamp đáng tin ở source** hay ingestion time. Không tin timestamp browser tự backdate.

## 24. Case study: chiến dịch rà soát 120 quyền

### 24.1. Dữ liệu chiến dịch

Một công ty rà soát CRM, SaaS tài chính và cloud roles. Snapshot gồm 120 review items:

| Kết quả | Số item |
|---|---:|
| KEEP có quyết định hợp lệ | 74 |
| REVOKE có quyết định hợp lệ | 16 |
| MODIFY có quyết định hợp lệ | 10 |
| Chưa có quyết định hợp lệ | 20 |
| **Tổng** | **120** |

Trong 100 quyết định, **90 quyết định đúng hạn**. Trong 26 item cần remediation, **19 đã verified**, 4 chờ target cập nhật và 3 gặp lỗi cần escalation.

### 24.2. Bốn KPI chính và backlog

| KPI | Công thức | Kết quả |
|---|---|---:|
| Decision completion | 100 / 120 | **83,33%** |
| On-time vs scope | 90 / 120 | **75,00%** |
| On-time among decided | 90 / 100 | **90,00%** |
| Remediation completion | 19 / 26 | **73,08%** |
| End-to-end closure | (74 + 19) / 120 | **77,50%** |
| Item chưa được quyết định | 20 / 120 | **16,67%** |
| Remediation chưa verified | 7 / 26 | **26,92%** |

Giả định của ví dụ: 74 KEEP đã đạt các bước authority/SoD và xác minh cần thiết. Nếu có KEEP không hợp lệ, end-to-end closure phải thấp hơn.

### 24.3. Phân tích high-risk

Giả sử 30 item là high-risk, 24 đã quyết định, gồm 18 KEEP hợp lệ và 6 REVOKE/MODIFY; 4 trong 6 đã verified.

~~~text
High-risk decision completion = 24 / 30 = 80%
High-risk end-to-end closure = (18 + 4) / 30 = 73.33%
~~~

Một dashboard chỉ hiển thị tổng số có thể che quyền production-admin chưa xử lý. Cần thấy số lượng cụ thể và owner chịu trách nhiệm từng item high-risk.

### 24.4. Hành động tiếp theo

1. Escalate **20 item thiếu quyết định**, ưu tiên critical/high-risk.
2. Đối soát **4 remediation đang chờ** với target.
3. Khắc phục **3 remediation lỗi** và áp dụng containment theo mức rủi ro.
4. Xác minh coverage của group, local grants, direct ACL, workload và guest.
5. Đối chiếu những quyền của Leaver/Mover trong kỳ với actual access.
6. Công bố cùng snapshot, deadline, as-of và metric version.

**Kết luận:** 100 reviewer decisions trên 120 items không phải 100% completion; 19 verified remediation trên 26 actions càng không phải 100% closure.

## 25. Anti-pattern đo lường thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Xóa item chưa review khỏi dashboard | Mẫu số bị co | Frozen cohort và audit exclusions |
| Reviewer mở task được tính completed | Không có quyết định | Chỉ đếm valid decisions |
| REVOKE click được tính verified | Target có thể còn quyền | Readback remediation |
| Chỉ báo overall completion | Che nguy cơ critical | Breakdown theo risk |
| Mẫu số 0 nhưng hiển thị 100% | KPI vô nghĩa | N/A và số lượng 0/0 |
| Dùng email thay immutable ID | Nhầm account | ID và target namespace |
| SCIM 200 được coi đã thu hồi | Còn role/session | Effective access evidence |
| Auto-KEEP khi quá hạn | Che thiếu reviewer | Escalation/default rule công khai |
| Chỉnh dueAt sau chiến dịch | On-time bị thổi phồng | Giữ original/current deadline |
| Không đo coverage | Bỏ sót hệ thống khó | Inventory và scope gap |
| Không có workload owner | Orphan grants | Owner-based recertification |
| Self-review admin không SoD | Quyết định thiếu hợp lệ | Reviewer độc lập |
| Cộng KPI khác mẫu số | Kết quả không có nghĩa | Ghi rõ tử số/mẫu số |
| Dashboard không có quyền đọc | Lộ quyền nhạy cảm | RBAC/ABAC trên báo cáo |

### 25.1. Completion không phải correctness

Một reviewer KEEP toàn bộ quyền trong thời hạn có thể đạt 100% quyết định nhưng chưa chắc đúng. Cần kiểm tra quyền quá rộng, SoD, owner, classification và chất lượng quyết định.

### 25.2. Không tối ưu con số bằng cách giảm scope

Tăng completion bằng việc bỏ cloud IAM hoặc service principals khỏi kỳ mới không chứng minh rủi ro giảm. So sánh phải tính đến coverage, cohort, risk profile và quy tắc tính.

## 26. Ma trận kiểm thử cách đo tỷ lệ hoàn tất

| Tình huống | Kết quả |
|---|---|
| 120 item, 100 valid decisions | 83,33% decision |
| 90/120 quyết định đúng hạn | 75% on-time vs scope |
| 90/100 quyết định đúng hạn | 90% among decided |
| 19/26 remediation verified | 73,08% |
| 74 KEEP hợp lệ, 19 remediation verified | 77,5% end-to-end |
| Mẫu số toàn chiến dịch 0 | N/A, không tự 100% |
| Không item nào cần remediation | Remediation N/A |
| Một item có nhiều attempt events | Không nhân item |
| Reviewer chỉ mở task | Không tính valid decision |
| Reviewer thiếu thẩm quyền | Không tính valid decision |
| Self-review vi phạm SoD | Escalate, không đếm valid |
| Quyết định REVOKE nhưng target vẫn ACTIVE | Decision có thể hoàn tất; closure chưa |
| Group đã gỡ nhưng role local còn | Chưa verified theo expected state |
| KEEP thiếu approval evidence | Không tự tính verified |
| Item quá hạn bị ẩn UI | Vẫn có trong denominator |
| Exclusion chưa duyệt | Không tự giảm scope |
| Duplicate được xác minh | Điều chỉnh có audit |
| Leaver revoke trước review | Có disposition lifecycle riêng |
| Joiner thêm quyền vào rolling cohort | Cập nhật theo cohort rule |
| Joiner thêm quyền vào frozen cohort | Delta riêng, không sửa baseline lén |
| Reviewer task chứa 20 entitlements | Đếm đúng item granularity |
| Decision event đến muộn | Dựa trên trusted time policy |
| Deadline được gia hạn | Lưu original và revised dueAt |
| Critical chưa reviewed | Hiển thị critical backlog |
| Reviewer thiếu owner | Không loại âm thầm khỏi scope |
| Source outage | UNKNOWN không tự VERIFIED |
| Hai tenant có cùng local ID | Namespace đúng |
| Service principal thiếu owner | Blocked/escalated |
| Report as-of 10:00 | Không dùng event 10:05 |
| Metric definition đổi | Version hóa, không trộn |
| Nhiều grants cấp cùng quyền | Xem effective access và source grants |

### 26.1. Test bằng dữ liệu giả lập

Tạo fixtures có KEEP, REVOKE, MODIFY, missing reviewer, invalid decision, pending remediation, exclusions, auto-revoked lifecycle items và nguồn lỗi. Đối chiếu tính tay với SQL và metric service để kiểm tra nhất quán.

### 26.2. Boundary của deadline

Phân biệt decision đúng lúc dueAt, sau dueAt một giây, và decision event đến muộn. Timezone và nguồn timestamp phải được định nghĩa nhất quán; không sửa đồng hồ production khi test.

### 26.3. Bảo mật dashboard

Một reviewer của tenant A không được xem danh sách admin/credential của tenant B. Kiểm tra authorization và scope của API báo cáo, không chỉ của trang UI.

## 27. Checklist vận hành đo completion

1. **Đơn vị:** item là entitlement/grant hay reviewer task?
2. **Campaign:** ID, owner, dueAt và scope có rõ?
3. **Inventory:** có bao phủ SaaS local roles, cloud, ACL, service principals?
4. **Snapshot:** original cohort và snapshot ID cố định?
5. **Denominator:** exclusions có approval và audit?
6. **Cohort delta:** Joiner/Mover/Leaver được xử lý công khai?
7. **Reviewer:** authority và SoD được kiểm tra?
8. **Decision validity:** KEEP/REVOKE/MODIFY có điều kiện đủ?
9. **Timeliness:** original/current deadline và trusted decision timestamp?
10. **Remediation:** đã xác định đúng những item cần xử lý target?
11. **Verification:** không tính API success thay readback?
12. **Closure:** KEEP, REVOKE, MODIFY được đóng theo từng rule?
13. **Coverage:** không nhầm 100% campaign với 100% inventory?
14. **High-risk:** critical item pending được ưu tiên?
15. **Risk weights:** nếu có thì công khai và version hóa?
16. **Unknown:** source outage/stale data không biến thành success?
17. **IdP/SSO:** login thành công không thay authorization?
18. **SCIM:** Group/User updates không thay kiểm tra local grants?
19. **RBAC/ABAC:** role/attribute/resource scope và quyền kế thừa được xét?
20. **Workload:** non-human principals có owner/entitlement review?
21. **JML:** không chờ campaign mới thu hồi Leaver/Mover?
22. **Audit:** decision time, actor, evidence, sourceVersion và correlation?
23. **SQL:** không nhân bản item khi join events?
24. **Reporting:** có as-of timestamp và metric definition version?
25. **Metrics:** ghi cả numerator/denominator, N/A đúng ngữ nghĩa?
26. **Dashboard:** số item open, overdue, remediation error và verified?
27. **Escalation:** reviewer/target owner chịu trách nhiệm backlog?
28. **Testing:** có duplicate, exclusion, deadline, stale token và drift?
29. **Security:** quyền xem báo cáo theo tenant/classification?
30. **Governance:** thay đổi công thức/scope có approval và công bố?

## 28. Tổng kết

**Đo tỷ lệ hoàn tất trong Access Recertification** phải bắt đầu từ định nghĩa **đơn vị đếm, phạm vi và mẫu số**, không bắt đầu từ hình tròn phần trăm. Một chiến dịch nên báo cáo riêng:

- **Decision Completion Rate:** tỷ lệ item đã có quyết định hợp lệ.
- **On-Time Completion Rate:** tỷ lệ quyết định đúng hạn theo denominator công bố.
- **Remediation Completion Rate:** tỷ lệ quyết định cần xử lý đã được thực thi và verified.
- **End-to-End Verified Closure Rate:** tỷ lệ item đã đóng toàn bộ vòng review theo policy.
- **Coverage và Risk Breakdown:** phần quyền đã được đưa vào campaign và các quyền quan trọng còn tồn đọng.

Sự kết nối **JML, IdP, SSO, SCIM, RBAC/ABAC, owner của tài khoản dịch vụ và target reconciliation** giúp số liệu phản ánh **quyền truy cập thực tế**, không chỉ thao tác trên một cổng phê duyệt.

**Ghi nhớ:** Completion cao chưa chắc quyền còn lại hợp lệ. Cần **đúng mẫu số, đúng quyết định, đúng deadline và bằng chứng thu hồi/điều chỉnh ở hệ thống đích**. Không đồng nhất **reviewer đã nhấn nút** với **quyền truy cập tồn dư đã biến mất**.




