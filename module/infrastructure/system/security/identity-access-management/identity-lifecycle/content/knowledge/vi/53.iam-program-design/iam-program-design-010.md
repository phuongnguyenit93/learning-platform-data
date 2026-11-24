# Ghi lại quyết định khi thiết kế chương trình IAM

Một chương trình **Identity and Access Management (IAM)** luôn phải đưa ra những lựa chọn có tác động lâu dài: hệ thống nào là nguồn danh tính có thẩm quyền; tài khoản nào được quản lý; role và policy được định nghĩa ra sao; quyền nào cấp tự động; ai phê duyệt; khi nào phải review; chứng cứ nào đủ để tuyên bố Leaver đã được thu hồi quyền. Nếu các quyết định đó chỉ nằm trong cuộc họp, tin nhắn hoặc trí nhớ của một kỹ sư, tổ chức sẽ khó giải thích tại sao hệ thống hoạt động như hiện tại và càng khó thay đổi an toàn.

**Ghi lại quyết định** là tạo một hồ sơ có cấu trúc, đủ bối cảnh và trách nhiệm giải trình để người khác biết: **đã quyết định điều gì, vì sao, dựa trên căn cứ nào, ai có thẩm quyền, những phương án nào bị loại bỏ, tác động và rủi ro ra sao, khi nào áp dụng, cần kiểm chứng gì và điều kiện nào buộc phải xem xét lại**.

Ví dụ, công ty chọn **HRIS là nguồn thẩm quyền của trạng thái nhân viên** và chọn **VMS là nguồn của ngày hết hạn hợp đồng nhà thầu**. Một năm sau, hệ thống được thêm tính năng HRIS ghi nhận nhà thầu. Nếu không có hồ sơ quyết định cũ, đội tích hợp có thể dùng quy tắc “giá trị cập nhật gần nhất thắng”, làm một event HRIS không phù hợp tự gia hạn quyền nhà thầu vốn đã hết hiệu lực theo VMS.

Bài này thuộc chương **Thiết kế chương trình IAM**, module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`. Nội dung áp dụng cho vòng đời **Joiner–Mover–Leaver (JML)** từ xác minh danh tính, tạo account và cấp quyền đến rà soát, thu hồi, kiểm toán; đồng thời liên kết IdP, SSO, SCIM, RBAC/ABAC, đặc quyền và tài khoản dịch vụ. Trọng tâm ở đây là **hồ sơ ra quyết định và quản trị quyết định**, không chỉ ghi log thao tác hệ thống.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **decision record**, **decision log/register**, **Architecture Decision Record (ADR)**, policy, approval, audit trail và biên bản họp.
2. Xác định những quyết định IAM **phải được ghi lại** vì ảnh hưởng tới identity source, scope, role, policy, lifecycle event, phê duyệt, review, audit, metric và vận hành.
3. Viết hồ sơ quyết định có **vấn đề, bối cảnh, giả định, lựa chọn thay thế, tiêu chí, lựa chọn được duyệt, hệ quả, owner, bằng chứng và trigger xem xét lại**.
4. Thiết kế **trạng thái, ID, version, hiệu lực, thời hạn, supersession và thay đổi quyết định** không làm mất lịch sử.
5. Gắn hồ sơ thiết kế với quyền thực tế: source event → policy/approval → provisioning IdP/SCIM/PAM → target readback → reconciliation.
6. Ghi các ngoại lệ, vấn đề chưa giải quyết và rủi ro được chấp nhận **có người chịu trách nhiệm, biện pháp bù trừ và thời hạn**.
7. Kiểm tra chất lượng hồ sơ quyết định và xây dựng decision register phục vụ bàn giao, triển khai, kiểm toán và cải tiến.

## 2. Vì sao quyết định IAM cần được lưu bền vững?

Khác với một thay đổi giao diện, quyết định IAM có thể làm hàng nghìn danh tính được cấp hoặc mất quyền. Một thay đổi tưởng như nhỏ — ví dụ sửa mapping `FINANCE_ANALYST → report:export` — có thể cho phép toàn bộ người đang giữ role xuất dữ liệu nhạy cảm.

Quyết định được ghi rõ giúp giải quyết năm vấn đề:

| Vấn đề | Khi không ghi lại | Khi có hồ sơ quyết định |
|---|---|---|
| **Mất bối cảnh** | Không biết vì sao HRIS được ưu tiên hơn directory trong một thuộc tính. | Có lý do, phạm vi, nguồn thẩm quyền và điều kiện thay đổi. |
| **Mâu thuẫn chính sách** | Mỗi đội hiểu khác nhau về thời điểm Leaver phải bị khóa. | Có một quyết định được duyệt, mốc thời gian và nghĩa vụ kiểm chứng. |
| **Rủi ro ẩn** | Phương án được chọn chỉ vì connector dễ làm, không đánh giá quyền local còn tồn tại. | Ghi các phương án, rủi ro chưa giải quyết và kế hoạch bù trừ. |
| **Thay đổi thiếu kiểm soát** | Người mới thay cấu hình mà không biết các phụ thuộc. | Có impact map, owner, version, rollback và trigger review. |
| **Không đủ căn cứ kiểm toán** | Log chỉ cho thấy ai đã sửa file, không giải thích tại sao được phép. | Hồ sơ lý do, quyết định có thẩm quyền và liên kết với bằng chứng thực thi. |

**Mục tiêu không phải tăng số lượng tài liệu.** Mục tiêu là giảm các quyết định vô hình, đặc biệt quyết định có ảnh hưởng đến nguyên tắc *least privilege*, *Separation of Duties (SoD)*, thời điểm hiệu lực, tính sẵn sàng và quyền truy cập tồn dư.

## 3. Phân biệt decision record với những tài liệu gần giống

| Thành phần | Nội dung cốt lõi | Ví dụ | Giới hạn |
|---|---|---|---|
| **Decision record / ADR** | Lựa chọn và lý do, phương án khác, rủi ro, hệ quả, owner, trạng thái | Chọn nguồn thẩm quyền `employmentStatus` | Không tự thay thế việc thực thi policy. |
| **Decision register** | Danh mục liên kết các record, trạng thái, trách nhiệm và phụ thuộc | Danh sách IAM-DEC-001...010 | Không thể thay nội dung chi tiết bằng một dòng tiêu đề. |
| **Policy catalog** | Quy tắc đang có hiệu lực, điều kiện Permit/Deny, assignment, thời hạn | Leaver phải thu hồi role production | Chỉ nói *phải làm gì*; không nhất thiết ghi đủ *vì sao chọn*. |
| **Approval record** | Ai có thẩm quyền đã duyệt yêu cầu cụ thể | Data owner duyệt xuất báo cáo trong 7 ngày | Không phải mọi approval cá nhân đều là ADR kiến trúc. |
| **Access review record** | Owner chứng nhận hoặc quyết định thu hồi quyền hiện hữu | Revoke role cũ sau Mover | Không tự mô tả rationale của toàn mô hình quản trị. |
| **Audit event** | Một sự kiện/hoạt động đã xảy ra, actor, target, outcome, timestamp | `ACCOUNT_DISABLE_REQUESTED` | Không đủ để giải thích lựa chọn thiết kế nếu chỉ có log kỹ thuật. |
| **Runbook** | Cách vận hành hoặc khắc phục sự cố theo các bước | Xử lý connector SCIM lỗi | Phải bám chính sách đã duyệt; không tự tạo quyền mới. |
| **Meeting minutes** | Người tham dự, ý kiến và kết luận cuộc họp | Thảo luận chọn IdP | Có thể chứa ý kiến chưa chốt; cần record chính thức cho quyết định có hiệu lực. |
| **Risk/exception register** | Rủi ro hoặc sai lệch được chấp nhận có điều kiện | Tạm giữ tài khoản local legacy 30 ngày | Phải liên kết quyết định chính nhưng có vòng đời riêng. |

**Lưu ý:** tên **ADR** thường dùng cho quyết định kiến trúc, nhưng mẫu ADR cũng hữu ích cho các lựa chọn thiết kế quản trị IAM. Không cần tạo ADR cho từng lần nhân viên gửi yêu cầu cấp quyền; những request đó nên ở **approval/audit system**. ADR phù hợp khi lựa chọn có tính hệ thống hoặc tạo tiền lệ.

## 4. Quyết định nào cần ghi lại?

Một cách thực tế là chia quyết định thành ba cấp:

1. **Program/architecture decision:** thay đổi cách tổ chức vận hành IAM. Cần decision record đầy đủ.
2. **Policy/control decision:** xác định điều kiện kiểm soát có hiệu lực trên nhiều đối tượng. Cần owner, version, rationale và quyết định phê duyệt.
3. **Individual transaction decision:** phê duyệt/thu hồi quyền cho một người hoặc service cụ thể. Cần bản ghi giao dịch có audit, liên kết tới policy/ADR, nhưng không nhất thiết tạo ADR riêng.

### Danh mục quyết định theo các cấu phần chương trình

| Miền thiết kế | Ví dụ quyết định phải lưu | Nếu bỏ qua sẽ xảy ra |
|---|---|---|
| **Identity source** | Thuộc tính nào lấy từ HRIS, VMS, service catalog, SOC; quy tắc xung đột | Nguồn phụ ghi đè trạng thái có thẩm quyền. |
| **Account scope** | SaaS, cloud, ERP local, shared/service accounts nào nằm trong scope và pha triển khai | Tuyên bố Leaver hoàn tất dù bỏ sót hệ thống. |
| **Identity correlation** | Khóa nguồn ổn định, xử lý tài khoản trùng, rehire và nhiều quan hệ | Ghép sai account, cấp/thu hồi quyền sai người. |
| **Role model** | Business/technical roles, birthright, role ownership, cách xử lý role explosion | Quyền không thể giải thích hoặc review. |
| **Policy model** | RBAC/ABAC, default deny, SoD, thiếu thuộc tính, rule priority | Một hệ thống cho phép còn hệ thống khác từ chối cùng tình huống. |
| **Lifecycle event** | Ngữ nghĩa Joiner/Mover/Leaver, effectiveAt, ordering, replay, retry | Cấp sớm, thu hồi muộn hoặc áp sự kiện sai thứ tự. |
| **Approval** | Quyền nào auto-grant, ai có authority, phê duyệt độc lập khi nào | Tự duyệt hoặc cấp quyền nhạy cảm không đúng thẩm quyền. |
| **Review** | Tần suất theo rủi ro, reviewer, bằng chứng và remediation | Review hình thức, không giải quyết quyền tồn dư. |
| **Audit** | Event bắt buộc, correlation, retention, target evidence, phân quyền log | Không tái dựng được quyết định hoặc thiếu chứng cứ. |
| **Metric** | Đơn vị, mẫu số, KPI/SLO, mốc thời gian, account scope version | Dashboard đẹp nhưng không phản ánh quyền thực tế. |
| **Privileged access** | JIT/PAM, break-glass, điều kiện MFA, session expiry | Đặc quyền lâu dài hoặc kênh khẩn cấp không có kiểm soát. |
| **Non-human identities** | Workload owner, credential rotation, vòng đời service account | Service account không ai chịu trách nhiệm. |
| **Resilience** | Khi HRIS/IdP/connector lỗi thì fail closed hay chế độ suy giảm nào | Quyền mới được cấp không kiểm chứng hoặc ngừng hệ thống không cần thiết. |

Một quyết định đủ lớn để ghi riêng thường thỏa **một hoặc nhiều** tiêu chí: tác động nhiều hệ thống, ảnh hưởng quyền nhạy cảm, phụ thuộc vào giả định có thể thay đổi, khó đảo ngược, tạo ngoại lệ lâu dài hoặc có thể bị chất vấn trong kiểm toán/sự cố.

### Quyết định chưa có kết luận cũng phải được quản lý

Nếu chưa biết ERP legacy có hỗ trợ đọc lại entitlement, đừng ghi “đã quyết định xác nhận readback”. Hãy tạo record `PROPOSED` hoặc `OPEN_ISSUE`, nêu **giả định đang chờ xác minh**, người chịu trách nhiệm, hạn ra quyết định và tác động tới scope. Không biến giả định thành sự thật chỉ để hoàn thành biểu mẫu.

## 5. Cấu trúc một hồ sơ quyết định tốt

Một record nên có các thành phần:

| Phần | Nội dung bắt buộc | Câu hỏi kiểm tra |
|---|---|---|
| **Decision ID** | Mã ổn định, không tái sử dụng | Có truy vết được trong policy/config/ticket không? |
| **Title** | Tên ngắn, thể hiện lựa chọn | Có hiểu đúng việc đã chốt không? |
| **Status** | Proposed, Accepted, Rejected, Superseded... | Đây là đề xuất hay quy tắc có hiệu lực? |
| **Context/problem** | Vấn đề, môi trường, yêu cầu nghiệp vụ | Tại sao phải ra quyết định lúc này? |
| **Scope** | Identity types, systems, tenants, environments, actions | Quyết định áp dụng ở đâu và không áp dụng ở đâu? |
| **Constraints** | Bảo mật, khả dụng, kỹ thuật, nghĩa vụ, ngân sách | Điều gì không được vi phạm? |
| **Options** | Các phương án có thể triển khai | Có xem xét lựa chọn thực tế khác không? |
| **Decision criteria** | Tiêu chí ưu tiên, mức rủi ro, dữ liệu | Vì sao chọn phương án này? |
| **Chosen decision** | Nguyên tắc/quy tắc cụ thể, không mơ hồ | Đội kỹ thuật có biết phải triển khai gì? |
| **Rationale** | Căn cứ và trade-off | Nếu điều kiện thay đổi, có thể xét lại không? |
| **Consequences** | Hệ quả tích cực, tiêu cực, phụ thuộc | Có nêu việc khó và chi phí không? |
| **Risk/mitigations** | Rủi ro tồn dư, owner, biện pháp bù trừ | Ai chịu trách nhiệm phần chưa giải quyết? |
| **Authority** | Author, accountable owner, approver(s) và SoD | Ai có thẩm quyền chấp thuận? |
| **Effective window** | AcceptedAt, effectiveFrom, reviewAt, expiry nếu cần | Khi nào áp dụng và khi nào xem lại? |
| **Implementation map** | Policy, connector, IdP/SCIM, workflow, ticket | Quyết định đã trở thành thay đổi ở đâu? |
| **Validation/evidence** | Tests, target readback, metric, audit references | Làm sao biết triển khai đúng? |
| **Supersedes/dependsOn** | Record bị thay thế và phụ thuộc | Lịch sử có liên tục và không mâu thuẫn không? |
| **Revision history** | Ai sửa, thay đổi gì, lý do gì | Có thể tái dựng lịch sử quyết định không? |

**Không phải mọi trường đều dài.** Một quyết định nhỏ có thể chỉ vài đoạn; một lựa chọn nguồn danh tính cho toàn tổ chức có thể cần nhiều bảng, mô hình dữ liệu và test. Điểm chung là các câu hỏi quan trọng có câu trả lời rõ ràng.

## 6. Mẫu ADR cho thiết kế IAM

Mẫu sau dùng Markdown để nhóm thiết kế và Security có thể kiểm tra trước khi phê duyệt. Đây là **mẫu tự xây dựng**, không phụ thuộc hệ thống ticket hoặc công cụ quản lý kiến trúc.

~~~markdown
# IAM-DEC-014: Chọn nguồn có thẩm quyền cho contractorEndAt

Status: PROPOSED
Decision owner: Identity Governance Lead
Approvers: Contract Process Owner, Security Owner
Scope: Contractor identities; các account trong IAM account scope v3
Proposed at: 2026-11-20
Effective from: Chỉ sau khi được APPROVED và triển khai đủ kiểm soát
Review trigger: VMS được thay thế hoặc nguồn có thẩm quyền thay đổi

## Bối cảnh
HRIS và VMS đều có trường "ngày kết thúc"; hai giá trị có thể khác nhau.
Quyền nhà thầu phải chấm dứt theo quan hệ hợp đồng có hiệu lực.

## Mục tiêu và ràng buộc
- Không tự gia hạn quyền dựa vào dữ liệu không có thẩm quyền.
- Hỗ trợ sự kiện kết thúc sớm hoặc gia hạn có source version.
- Có cảnh báo nếu nguồn không sẵn sàng hoặc thiếu dữ liệu.

## Phương án
A. Ưu tiên VMS cho contractEndAt.
B. Ưu tiên HRIS.
C. Giá trị cập nhật gần nhất thắng.

## Đề xuất
Chọn A; HRIS chỉ cung cấp thuộc tính thuộc phạm vi nhân sự.
Nếu VMS không xác minh được, chặn cấp quyền mới vượt thời hạn được xác nhận;
chuyển yêu cầu gia hạn sang workflow kiểm tra có thẩm quyền.

## Lý do
VMS là hệ thống được owner hợp đồng ủy quyền quản lý end date.
Last-write-wins không thể phân biệt dữ liệu sai và dữ liệu mới.

## Rủi ro và biện pháp
Mất kết nối VMS: quản lý freshness, alert, retry và chính sách xử lý
không chắc chắn theo mức rủi ro của hành động.

## Thực thi và kiểm chứng
- Event contract end / extension có sourceVersion và effectiveAt.
- Test event trễ, duplicate, gia hạn, chấm dứt sớm.
- Readback xác nhận thu hồi tại các SaaS và account local.

## Phụ thuộc
Account scope v3; contractor lifecycle policy; event contract.

## Chữ ký và ngày duyệt
Chưa phê duyệt.
~~~

Mẫu trên thể hiện rõ **đề xuất** chứ chưa phải cấu hình có hiệu lực. Không được xem việc lưu một file `PROPOSED` như quyết định đã được phê duyệt.

## 7. Từ thảo luận đến quyết định có hiệu lực

Một workflow cơ bản:

~~~mermaid
flowchart TD
    A["Vấn đề / thay đổi được phát hiện"] --> B["Tạo record PROPOSED<br/>bối cảnh và owner"]
    B --> C["Lựa chọn thay thế<br/>impact, risk, constraints"]
    C --> D["Thẩm định Security / Business / Architecture"]
    D --> E{"Decision gate"}
    E -- "Cần bổ sung" --> B
    E -- "Không chấp nhận" --> F["REJECTED<br/>giữ lý do"]
    E -- "Được duyệt" --> G["ACCEPTED<br/>decision ID + approval"]
    G --> H["Implementation plan<br/>mapping + rollout + rollback"]
    H --> I["Thực thi policy / workflow / connector"]
    I --> J["Validation<br/>tests + readback + metrics"]
    J --> K{"Đạt tiêu chí?"}
    K -- "Chưa" --> L["Remediation / rollback / reopen"]
    L --> H
    K -- "Đạt" --> M["IMPLEMENTED / VERIFIED<br/>gắn evidence"]
    M --> N["Periodic/event-triggered review"]
    N --> O{"Cần thay đổi?"}
    O -- "Có" --> P["New decision supersedes old"]
    O -- "Không" --> N
~~~

### Tách trạng thái quyết định và trạng thái triển khai

Một quyết định có thể **đã được phê duyệt nhưng chưa triển khai**. Ngược lại một cấu hình có thể đang chạy nhưng chưa được tổ chức chấp thuận, cần xử lý như ngoại lệ hoặc drift.

| Decision status | Implementation status | Diễn giải |
|---|---|---|
| `PROPOSED` | `NOT_STARTED` | Đang phân tích, chưa có quyền triển khai thay đổi nhạy cảm. |
| `ACCEPTED` | `PLANNED` | Đã duyệt nhưng chưa tạo thay đổi. |
| `ACCEPTED` | `IN_PROGRESS` | Đang rollout; cần kiểm soát tác động từng phần. |
| `ACCEPTED` | `VERIFIED` | Đã có bằng chứng tiêu chí nghiệm thu đạt trong scope. |
| `ACCEPTED` | `FAILED` | Đã duyệt nhưng kiểm thử hoặc readback không đạt; phải khắc phục. |
| `SUPERSEDED` | `MIGRATING` | Quyết định mới thay thế; những đích còn bản cũ cần theo dõi. |
| `REJECTED` | `NOT_STARTED` | Không được lấy proposal này làm căn cứ cấp quyền. |
| `RETIRED` | `RETIRED` | Quy tắc không còn áp dụng và đã xác nhận gỡ phụ thuộc. |

Tên trạng thái là gợi ý, nhưng **ngữ nghĩa phải chính xác và nhất quán**. Đừng đặt một cờ `done=true` cho cả “đã đồng ý” và “đã kiểm chứng triển khai xong”.

## 8. Ai phải tham gia và có quyền chốt quyết định?

IAM tác động nhiều miền trách nhiệm. Không nên để người triển khai connector đơn phương quyết định dữ liệu nào được tin cậy hoặc quyền dữ liệu nào được tự động cấp.

| Loại quyết định | Người phụ trách nội dung | Người cần tham vấn/phê duyệt tùy rủi ro |
|---|---|---|
| Nguồn `employmentStatus` | HR data owner / IAM governance | HR operations, security, architecture. |
| Nguồn `contractEndAt` | Contract/VMS owner | Sponsor, IAM governance, security. |
| Role và birthright | Business process owner | Application owner, security, IAM. |
| RBAC/ABAC và SoD | Security policy owner | Data owner, business owner, architecture. |
| Quyền xuất dữ liệu nhạy cảm | Data owner | Privacy/security và application owner. |
| JML event effective time | HR/VMS owner và IAM lifecycle owner | Platform, owner ứng dụng, risk. |
| IdP/SSO/SCIM integration | Identity platform owner | Application owner, security, operations. |
| PAM/JIT/break-glass | Privileged access/security owner | Infrastructure owner, incident response. |
| Workload identity | Service owner | Resource owner, platform security. |
| Audit evidence/retention | IAM audit owner | Security, privacy, compliance theo nghĩa vụ thực tế. |
| KPI/SLO | Program owner | IAM operations, security/risk và các owner đích. |

### RACI và giới hạn quyền quyết định

RACI có thể xác định ai **Responsible** (soạn/triển khai), **Accountable** (chịu trách nhiệm kết luận), **Consulted** (tham vấn) và **Informed** (nhận thông tin). Nhưng RACI không thay thế cơ chế ủy quyền thực tế: owner dữ liệu cần có authority đối với đúng dữ liệu, reviewer không tự chứng nhận đặc quyền của chính mình và người duyệt ngoại lệ phải có trách nhiệm chấp nhận rủi ro.

**Nếu approver không có authority hoặc có xung đột lợi ích, không tự chuyển proposal thành `ACCEPTED`.** Cần chuyển cấp hoặc chọn người có thẩm quyền theo quy trình đã duyệt.

### Ghi bất đồng thay vì xóa khỏi hồ sơ

Khi Security khuyến nghị `default deny` nhưng một ứng dụng legacy cần chế độ suy giảm, record nên lưu:

- quan điểm và căn cứ của các bên;
- phạm vi tác động và những điều kiện không thể đáp ứng;
- biện pháp bù trừ, expiry, owner nhận rủi ro và thời điểm phải xử lý;
- kết luận ai đã phê duyệt và giới hạn của kết luận đó.

Không nên biến bất đồng chưa giải quyết thành “đồng thuận” bằng cách xóa ý kiến phản biện.

## 9. Phân tích và so sánh các phương án

Viết “chọn phương án A vì đơn giản” chưa đủ nếu nó có thể tạo đường truy cập tồn dư. Nên so các phương án theo **tiêu chí đã thống nhất trước**.

Ví dụ tổ chức cần quyết định cách provision ứng dụng SaaS:

| Tiêu chí | SCIM tự động + readback | API custom + readback | Ticket thủ công |
|---|---|---|---|
| Tốc độ xử lý JML | Có thể nhanh khi tích hợp ổn định | Phụ thuộc API và logic custom | Phụ thuộc người xử lý. |
| Khả năng xác nhận tại đích | Cần kiểm tra SCIM read/search hỗ trợ đến đâu | Có thể thiết kế, tùy API | Cần bằng chứng thao tác/đối soát. |
| Xử lý retry/idempotency | Vẫn phải thiết kế rõ | Phải tự kiểm soát nhiều hơn | Phải chống thao tác lặp và lỗi con người. |
| Chi phí ban đầu | Tích hợp chuẩn nếu ứng dụng hỗ trợ đủ | Cao hơn nếu hành vi đặc thù | Thấp ở quy mô nhỏ, chi phí vận hành dài hạn. |
| Nguy cơ cấp/thu hồi ngoài luồng | Vẫn có nếu app cho direct grants | Tùy phạm vi discovery và quản trị | Có thể lớn nếu thiếu đối soát. |
| Kiểm toán | Có thể liên kết event–action–readback | Có thể thiết kế đầy đủ | Cần evidence và owner thủ công. |
| Khả năng mở rộng | Tùy giới hạn connector/nhà cung cấp | Tùy chất lượng triển khai | Thường khó khi số lượng tăng. |

Quyết định cuối cùng cần dựa trên **năng lực thực tế của target**. “SCIM có hỗ trợ” không đồng nghĩa có endpoint đọc lại mọi entitlement, khả năng ngắt session hoặc token. Các giả định phải được kiểm chứng bằng thiết kế tích hợp và kiểm thử.

### Trade-off nên được ghi bằng ngôn ngữ có thể kiểm chứng

Chẳng hạn: “Chọn SCIM để giảm độ trễ thu hồi so với ticket thủ công; ứng dụng chưa hỗ trợ thu hồi session đang hoạt động, vì vậy cần token/session TTL phù hợp hoặc kiểm soát bổ sung, có owner và kế hoạch xử lý.” Đây là một quyết định có **giới hạn rõ**, không phải tuyên bố quá mức “SCIM giải quyết hoàn toàn Leaver”.

## 10. Ghi lại quyết định về nguồn và phạm vi danh tính

### 10.1. Quyết định nguồn thẩm quyền theo thuộc tính

Không nên ghi chung “HRIS là nguồn sự thật duy nhất cho IAM” nếu nhà thầu, tài khoản dịch vụ, security hold và phân loại tài nguyên đến từ các nguồn khác.

| Thuộc tính | Nguồn đề xuất | Điều cần ghi trong decision record |
|---|---|---|
| `employmentStatus` | HRIS | Phạm vi nhân viên, mã trạng thái, mốc hiệu lực, tần suất cập nhật. |
| `contractEndAt` | VMS | Định nghĩa thời điểm kết thúc, contract ID, gia hạn, điều kiện không có dữ liệu. |
| `securityHold` | Quy trình SOC/IdP có thẩm quyền | Ai được đặt/gỡ, ưu tiên trước policy cấp quyền thông thường. |
| `departmentId` | HRIS | Cách xử lý chuyển phòng ban tương lai hoặc thay đổi trễ. |
| `serviceOwnerId` | Service catalog | Owner còn hợp lệ, chuyển owner khi nhân viên nghỉ. |
| `resourceClassification` | Data/resource owner | Giới hạn quyền ABAC, cập nhật khi độ nhạy thay đổi. |

Hồ sơ cần mô tả **xung đột thẩm quyền**, freshness, trường thiếu, danh tính nhiều quan hệ và cách dùng version. Không áp “giá trị ghi cuối cùng thắng” tùy tiện khi nguồn khác nhau quản lý các ý nghĩa khác nhau.

### 10.2. Quyết định account scope và ngoại lệ legacy

Ví dụ một ứng dụng ERP có account local không hỗ trợ SCIM. Decision record phải nêu:

1. Ứng dụng có nằm trong phạm vi IAM không? Nếu có, từ khi nào?
2. Cách discovery, liên kết native account ID, chặn đăng nhập, thu hồi quyền trực tiếp là gì?
3. Bằng chứng nào đủ xác nhận tại đích khi không có read API?
4. Người nào xử lý ticket thủ công, SLA và escalation?
5. Đây là mục tiêu cuối hay ngoại lệ tạm thời? Khi nào phải thay thế?
6. KPI báo cáo có bao gồm ERP và đánh dấu những thao tác chưa thể xác minh không?

Không được làm đẹp tỷ lệ Leaver bằng cách lặng lẽ loại ứng dụng khó tích hợp ra khỏi mẫu số mà không có **quyết định scope có owner và lịch chuyển tiếp**.

## 11. Ghi lại quyết định về role, policy, approval và review

### Role model

Quyết định role phải nêu business role nào đại diện công việc, technical entitlement nào được map, phạm vi tenant/resource và quy tắc khi nhiều role cùng cấp một quyền. Nếu role `FINANCE_ANALYST` có thêm `report:export`, hồ sơ thay đổi cần xác định **những người đã giữ role cũng bị ảnh hưởng**, không chỉ request mới.

### Policy model

Ghi rõ:

- nơi áp dụng default deny và khi dữ liệu thuộc tính bị thiếu;
- cách kết hợp quy tắc Permit/Deny, SoD và security hold;
- phân chia chính sách provisioning với runtime authorization tại API;
- nguồn, độ mới và tính đáng tin của attribute ABAC;
- policy version có hiệu lực theo thời gian và cách rollback.

Ví dụ quyết định “API tài chính luôn kiểm tra tenant hiện hành từ nguồn đáng tin cậy, không chỉ từ claim client gửi” cần liên kết tới policy, PEP, test sai tenant và log truy cập bị từ chối.

### Approval và access review

Quyết định phê duyệt phải nêu quyền nào được auto-grant theo policy birthright, quyền nào cần manager/data owner/privileged owner và điều kiện không cho tự duyệt. Quyết định review phải nêu scope, tần suất theo rủi ro, reviewer authority, quyền cấp trực tiếp và trạng thái khắc phục sau khi chọn Revoke.

**Chính sách thu hồi bắt buộc sau Leaver không được phụ thuộc một review/approval tùy ý.** Hồ sơ thiết kế phải thể hiện rõ những hành động IAM buộc thực thi vì quan hệ đã hết hiệu lực, khác với quyết định cấp quyền nhạy cảm mới.

## 12. Ghi lại quyết định về lifecycle event và thời gian hiệu lực

Các event JML dễ gây lỗi vì thời gian phát hành khác thời điểm hiệu lực. Hồ sơ quyết định cần ghi:

| Khía cạnh | Câu hỏi phải chốt |
|---|---|
| **Event taxonomy** | Joiner/Mover/Leaver là event nghiệp vụ hay thay đổi thuộc tính? |
| **Authority** | HRIS, VMS hoặc service catalog được phép phát event nào? |
| **Identity correlation** | Event liên kết với relationship/identity nào bằng khóa nguồn ổn định? |
| **Timing** | `occurredAt`, `publishedAt`, `receivedAt`, `effectiveAt` khác gì nhau? |
| **Future event** | Nếu lịch bắt đầu/chuyển việc/nghỉ việc thay đổi, hủy kế hoạch cũ ra sao? |
| **Ordering** | Sử dụng source version/sequence nào để chống event đến sai thứ tự? |
| **Replay/idempotency** | Event lặp và lệnh retry có tạo tác dụng ngoài ý muốn không? |
| **State transition** | Trạng thái nghiệp vụ, trạng thái account và trạng thái fulfillment được tách thế nào? |
| **Verification** | Bằng chứng nào xác nhận quyền ở đích đã đổi? |
| **Failure mode** | Nếu connector lỗi, ai bị cảnh báo, có biện pháp cô lập nào? |

### Tình huống Mover có lịch tương lai

Ngày 01/06 HRIS xác nhận nhân viên chuyển Finance → Engineering vào 15/06. Ngày 10/06, HRIS hoãn sang 01/07.

Một quyết định tốt cần nêu:

1. **Event nguồn có version**, ví dụ `18` và `19`, liên kết cùng relationship.
2. Lệnh cấp/thu hồi quyền bị lập lịch theo **version cụ thể**.
3. Khi version `19` đến, lịch version `18` bị vô hiệu hóa.
4. Đến 15/06, scheduler không được thực thi lịch cũ.
5. Đến 01/07, hệ thống xác minh lại điều kiện và thực thi đúng thứ tự SoD.
6. Bằng chứng test cho trường hợp thay lịch và event trễ được gắn vào decision record.

Nếu thiếu quyết định về hiệu lực tương lai, mỗi đội có thể tự giải thích khác nhau, gây cấp quyền quá sớm hoặc kéo dài quyền cũ.

### Tình huống Leaver có nhiều hệ thống đích

Quyết định “Leaver hoàn tất” phải nêu **đơn vị được xác nhận**: chỉ account IdP, mọi account trong scope, hay mọi entitlement/credential có đường xác minh. Định nghĩa này là cơ sở cho vận hành, kiểm toán và metric. Không thể tuyên bố Leaver đã hoàn tất chỉ vì `DisableAccount` đã được gửi và connector trả ACK.

## 13. Ghi lại quyết định về danh tính phi con người

Service account và workload identity không có cùng vòng đời với nhân viên, nên quyết định thiết kế phải tránh quy tắc máy móc “người tạo nghỉ việc thì xóa robot”.

Một decision record cho workload cần xác định:

- Nguồn `serviceId`/`workloadId`, deployment/environment và owner có thẩm quyền;
- sự kiện tạo, đổi phạm vi, đổi owner, ngừng triển khai hoặc lộ credential;
- cơ chế xác thực ưu tiên (ví dụ workload federation khi được hỗ trợ) và lý do dùng credential dài hạn nếu cần;
- quyền tối thiểu theo service/resource, quy trình phê duyệt và review;
- điều kiện rotation, revoke credential và xác nhận ở đích;
- trách nhiệm xử lý khi owner nghỉ hoặc dịch vụ được retired.

### Ví dụ decision trade-off cho CI/CD bot

| Phương án | Lợi ích | Rủi ro/công việc cần làm |
|---|---|---|
| Dùng khóa tĩnh lưu trong pipeline | Dễ tích hợp hệ thống legacy | Nguy cơ rò rỉ, rotation, owner và expiry khó quản trị. |
| Dùng workload federation/token ngắn hạn | Giảm secret tĩnh, dễ ràng scope/audience | Phụ thuộc tính năng IdP/cloud, cấu hình trust và vận hành. |
| Dùng tài khoản cá nhân của kỹ sư | Có thể nhanh ban đầu | Phụ thuộc vòng đời nhân viên, khó tách trách nhiệm và truy vết; thường không phù hợp. |

Quyết định cuối cùng phải theo năng lực thực tế và threat model; không giả định mọi nền tảng hỗ trợ cùng công nghệ. Nếu dùng khóa dài hạn tạm thời, record phải nêu owner, expiry/mốc thay thế, kiểm soát bù trừ và dấu vết rà soát.

## 14. Ghi nhận ngoại lệ và rủi ro được chấp nhận

Nhiều chương trình IAM phải hỗ trợ ứng dụng legacy hoặc một đường break-glass tồn tại ngoài IdP chính. Không nên che những hạn chế đó bằng câu “đã đạt chuẩn”. Cần **exception record liên kết với decision**, có vòng đời rõ:

| Trường | Ý nghĩa |
|---|---|
| `exceptionId`, `parentDecisionId` | Liên kết ngoại lệ với chính sách/quyết định gốc. |
| `riskStatement` | Sự kiện xấu nào có thể xảy ra, tác động tới ai? |
| `scope` | Account, target, tenant, action và môi trường nào được ngoại lệ? |
| `reason` | Vì sao chưa thể tuân thủ quyết định bình thường? |
| `riskOwner` | Ai có thẩm quyền chấp nhận rủi ro còn lại? |
| `compensatingControls` | Biện pháp bù trừ: giám sát, giới hạn mạng, manual readback, PAM... |
| `effectiveFrom`, `expiresAt` | Ngoại lệ chỉ có hiệu lực trong khoảng được duyệt. |
| `reviewAt` | Ngày phải rà soát lại tiến độ xử lý. |
| `remediationPlan` | Ai sẽ loại bỏ ngoại lệ và điều kiện đóng. |
| `evidence` | Bằng chứng kiểm soát đang vận hành và đã khắc phục. |

**Ngoại lệ không tự động cho phép mọi hành động trái policy.** Một số yêu cầu là kiểm soát bắt buộc không thể được miễn theo ý chí của bất kỳ cá nhân nào. Khi chưa đủ authority hoặc thiếu biện pháp bù trừ, phải từ chối hoặc escalated theo quy trình.

### Ví dụ: Leaver trên ERP legacy

Giả sử ERP chưa hỗ trợ disable qua API. Đội IAM chọn ticket thủ công trong thời gian chuyển đổi. Record phải chỉ ra đây là giải pháp tạm thời, ai nhận ticket, mức ưu tiên Leaver, quy tắc xác minh thao tác, tần suất đối soát, kênh xử lý khẩn cấp và ngày bắt buộc xem lại phương án. Nếu ERP không thể xác minh quyền thực tế, KPI và audit phải thể hiện **giới hạn bằng chứng**, không ghi `VERIFIED` tùy tiện.

## 15. Quyết định có version, hiệu lực và khả năng thay thế

Không xóa quyết định cũ chỉ vì có phương án tốt hơn. Một record cũ là **bằng chứng vì sao hệ thống từng hoạt động theo cách đó**.

### Mô hình vòng đời của decision record

~~~mermaid
stateDiagram-v2
    [*] --> PROPOSED
    PROPOSED --> ACCEPTED: Approved
    PROPOSED --> REJECTED: Not accepted
    PROPOSED --> WITHDRAWN: Cancel proposal
    ACCEPTED --> SUPERSEDED: New decision accepted
    ACCEPTED --> RETIRED: Scope no longer applies
    REJECTED --> [*]
    WITHDRAWN --> [*]
    SUPERSEDED --> [*]
    RETIRED --> [*]
~~~

Sơ đồ thể hiện vòng đời **decision**, chưa bao gồm rollout kỹ thuật. Nếu record cần chỉnh vì lỗi chính tả, tổ chức có thể giữ cùng ID và revision; nếu thay đổi **ngữ nghĩa lựa chọn**, nên tạo quyết định/revision được phê duyệt mới theo quy ước đã ban hành.

### Quy tắc quản trị khi thay quyết định

1. Mã decision cũ không được tái sử dụng cho lựa chọn khác.
2. Quyết định mới ghi `supersedes` hoặc liên kết đến bản cũ.
3. Chỉ rõ **effectiveFrom** của quyết định mới và thời gian chuyển tiếp.
4. Kiểm kê các policy, role mapping, connector, runbook, test, dashboard và tài khoản bị tác động.
5. Có kế hoạch rollout/rollback, readback và xử lý khi một phần hệ thống chưa chuyển.
6. Không sửa lịch sử audit/approval để làm như thể quyết định mới luôn có hiệu lực.

Ví dụ thay nguồn `contractEndAt` từ VMS sang hệ thống hợp đồng mới. Trong giai đoạn chuyển tiếp, các nguồn có thể không đồng bộ. Decision phải nêu **thời điểm bàn giao thẩm quyền**, cơ chế kiểm tra sai lệch, đường xử lý sự kiện trễ và cách chứng minh không phát sinh quyền nhà thầu tồn dư.

## 16. Một mẫu quyết định có cấu trúc để máy và người cùng đọc

~~~yaml
# Cấu trúc minh họa cho decision register; không phải schema của công cụ cụ thể.
decision:
  id: IAM-DEC-021
  revision: 2
  title: Xác nhận thu hồi quyền Leaver bằng target readback
  category: LIFECYCLE_CONTROL
  status: ACCEPTED
  ownerTeam: IdentityGovernance
  approvedBy:
    - role: IAM_PROGRAM_OWNER
      decisionRef: approval-7101
    - role: SECURITY_OWNER
      decisionRef: approval-7102
  acceptedAt: "2026-11-20T09:30:00+07:00"
  effectiveFrom: "2026-12-01T00:00:00+07:00"
  scope:
    relationshipTypes: [EMPLOYEE, CONTRACTOR]
    accountScopeVersion: 3
    targets:
      - idp-corp
      - finance-saas
      - cloud-prod
  problem: Không thể chứng minh Leaver hoàn tất chỉ bằng ACK của connector
  options:
    - id: ACK_ONLY
      disposition: REJECTED
      reason: Không chứng minh được quyền thực tế
    - id: TARGET_READBACK
      disposition: SELECTED
      reason: Có bằng chứng đối soát quyền tại đích
    - id: MANUAL_ALL_TARGETS
      disposition: REJECTED
      reason: Khó mở rộng và tăng độ trễ trong target có API
  rules:
    desiredState: NO_ACTIVE_REQUIRED_ACCESS
    completionCondition: ALL_REQUIRED_REVOCATIONS_VERIFIED
    missingEvidence: INCOMPLETE_AND_ESCALATE
  dependencies:
    - account-scope-v3
    - leaver-policy-v8
    - target-reconciliation-contract-v2
  implementation:
    status: IN_PROGRESS
    rolloutRef: change-155
    rollbackRef: rollback-155
  validation:
    requiredTests:
      - scim-ack-but-target-still-active
      - target-readback-unavailable
      - multiple-accounts-per-identity
      - local-account-drift
    evidenceRefs: []
  review:
    trigger:
      - ACCOUNT_SCOPE_CHANGED
      - TARGET_API_BEHAVIOR_CHANGED
      - CONTROL_FAILURE_FOUND
    owner: IdentityGovernance
~~~

**Điểm cần chú ý:** `status: ACCEPTED` nói **quyết định đã được duyệt**, trong khi `implementation.status: IN_PROGRESS` nói **chưa triển khai hoàn tất**. Trường `validation.evidenceRefs: []` không thể bị diễn giải là có đủ bằng chứng chỉ vì quyết định đã được phê duyệt.

### Quy tắc dữ liệu của decision record

- `id` ổn định; `revision` tăng theo thay đổi nội dung và có history.
- `title`, `scope`, `status`, `ownerTeam`, `rationale` và `approvedBy` phải có ngữ nghĩa rõ.
- ID bên ngoài như ticket, policy hoặc evidence phải trỏ tới đối tượng cụ thể; không dùng link mơ hồ chỉ tới trang chủ hệ thống.
- `effectiveFrom` khác với `acceptedAt`: quyết định được chấp nhận hôm nay nhưng có thể chỉ áp dụng sau rollout.
- Gắn record với **phiên bản account scope và policy** giúp biết các đối tượng được tính vào kết luận.
- Không nhét credential, password, bearer token hoặc dữ liệu nhân sự nhạy cảm không cần thiết vào record.

## 17. Decision register và đồ thị phụ thuộc

Một decision register không chỉ là bảng `id – title – status`; nó phải giúp thấy **quyết định nào phụ thuộc vào quyết định nào** và những thay đổi nào phải được đánh giá lại.

| ID | Quyết định | Status | Owner | Phụ thuộc | Đầu ra kỹ thuật |
|---|---|---|---|---|---|
| `IAM-DEC-001` | HRIS là nguồn `employmentStatus` của employee | ACCEPTED | HR Data Owner | Không | Identity attribute mapping. |
| `IAM-DEC-002` | VMS là nguồn `contractEndAt` của contractor | ACCEPTED | Contract Owner | Identity correlation | Contractor lifecycle ingestion. |
| `IAM-DEC-003` | Account scope gồm IdP, SaaS, ERP local, cloud production | ACCEPTED | IAM Program Owner | Inventory | Connector/discovery plan. |
| `IAM-DEC-004` | Role baseline theo bộ phận và trạng thái quan hệ | ACCEPTED | Business Role Owner | 001, 003 | Role catalog/policy. |
| `IAM-DEC-005` | Runtime API kiểm tra tenant bằng ABAC | ACCEPTED | Security/Data Owner | 004 | PDP/PEP policy. |
| `IAM-DEC-006` | Leaver hoàn tất sau readback ở mọi đích bắt buộc | ACCEPTED | IAM/Security | 001, 002, 003 | Reconciliation control. |
| `IAM-DEC-007` | Role privileged chỉ nâng tạm qua PAM/JIT | PROPOSED | Security | 003, 005 | PAM policy và workflow. |
| `IAM-DEC-008` | Metric Leaver theo identity, không chỉ action | ACCEPTED | Program Owner | 003, 006 | KPI definition v1. |

~~~mermaid
flowchart LR
    SRC["Identity source decisions"] --> JML["Lifecycle event decisions"]
    SCOPE["Account scope decisions"] --> JML
    SRC --> ROLE["Role / Policy decisions"]
    SCOPE --> ROLE
    ROLE --> AP["Approval / Review decisions"]
    JML --> PROV["Provisioning / Verification decisions"]
    AP --> PROV
    PROV --> AUDIT["Audit / Evidence decisions"]
    AUDIT --> METRIC["Metric / SLO decisions"]
    SCOPE --> METRIC
~~~

Nếu account scope mở rộng thêm một cloud project, phải đánh giá lại ít nhất **readback/Leaver completion**, audit coverage và KPI mẫu số. Nếu chỉ sửa inventory mà không đánh giá phụ thuộc, các quyết định cũ có thể không còn đúng trên phạm vi mới.

### Theo dõi quyết định đang mở

Register nên có trường `nextAction`, `dueAt`, `blocker` và `owner` đối với `PROPOSED` hoặc `IN_REVIEW`. Các quyết định chưa chốt cần được xem là **rủi ro triển khai** nếu đang chặn một control quan trọng; không tự diễn giải thành đã được chấp thuận do hết hạn cuộc họp.

## 18. Liên kết quyết định với triển khai và bằng chứng JML

Một decision record hữu ích phải **truy vết hai chiều**:

1. **Từ quyết định ra hệ thống:** record → policy/version → configuration/connector → test → rollout → audit/evidence.
2. **Từ một quyền cụ thể về quyết định:** account/entitlement → source event/approval → policy/role → decision ID → rationale/owner.

~~~mermaid
flowchart TD
    DEC["Decision record<br/>IAM-DEC-021"] --> POL["Policy version<br/>leaver-policy-v8"]
    DEC --> SCOPE["Account scope v3"]
    DEC --> TEST["Test cases / rollout"]
    EV["HRIS/VMS event<br/>sourceEventId + effectiveAt"] --> PDP["IAM evaluates desired state"]
    POL --> PDP
    SCOPE --> PDP
    PDP --> CMD["Provisioning actions<br/>actionId"]
    CMD --> IDP["IdP / SCIM / PAM / legacy"]
    IDP --> OBS["Target readback<br/>evidenceId"]
    OBS --> AUDIT["Audit trail / reconciliation"]
    AUDIT --> MET["Verified completion metric"]
    DEC --> MET
~~~

### Ví dụ chi tiết: quyết định Leaver completion

**Decision:** Chỉ kết luận Leaver đã hoàn tất khi mọi account/entitlement bắt buộc trong scope đã được xác minh thu hồi; nếu không đọc được đích thì để `INCOMPLETE` và escalation.

**Các liên kết phải tồn tại:**

- HRIS/VMS event có `sourceEventId`, source version và `effectiveAt`;
- identity correlation tới `identityId`, source relationship và account inventory;
- `policyId` / `policyVersion` áp dụng tại thời điểm xử lý;
- các `actionId` riêng cho IdP, SaaS, local account, cloud role và credential thuộc scope;
- kết quả từng attempt và `targetEvidenceId` cho trạng thái đọc lại;
- drift/ticket và owner nếu còn quyền;
- metric dùng đúng định nghĩa identity-level completion và latency.

**Cách diễn giải:** Một Leaver có ba target được xác minh và một target vẫn active **không phải `COMPLETED`**. Tỷ lệ action-level có thể cao, nhưng decision record đã quy định nghĩa của “hoàn tất theo identity”.

### Record quyết định không phải log từng sự kiện

Không đưa hàng triệu sự kiện SCIM vào một file ADR. Quyết định ghi **quy tắc và lý do**; audit pipeline ghi **những việc thật sự xảy ra**; evidence store lưu **trạng thái được xác minh**. Các nguồn liên kết bằng mã, version và quyền truy cập phù hợp. Điều này giúp hồ sơ thiết kế ổn định trong khi vẫn truy vết được hoạt động vận hành.

## 19. Quyết định về fail-open, fail-closed và vận hành suy giảm

Một số lựa chọn IAM đòi hỏi đánh giá rủi ro và tính sẵn sàng, đặc biệt khi HRIS, IdP, PDP, PIP hoặc connector không hoạt động.

| Tình huống | Lựa chọn cần ghi | Rủi ro nếu không có quyết định |
|---|---|---|
| Không lấy được trạng thái hợp đồng | Chặn cấp quyền mới; dùng dữ liệu cuối còn tin cậy trong giới hạn được duyệt; escalation | Tự gia hạn quyền nhà thầu đã hết hợp đồng. |
| IdP không hoạt động | Hạn chế đăng nhập thông thường; đường khôi phục/break-glass riêng có kiểm soát | Không thể phục hồi production hoặc mở đường bypass vĩnh viễn. |
| PIP thiếu thuộc tính ABAC nhạy cảm | Default deny/chờ xác minh theo loại tài nguyên và risk tier | Cho truy cập cross-tenant vì không biết tenant. |
| Connector SCIM timeout | Retry idempotent + readback, giữ trạng thái chưa xác nhận | Báo Leaver hoàn tất khi SaaS vẫn active. |
| Audit collector bị lỗi | Queue bền vững, cảnh báo, giới hạn thao tác đặc quyền theo policy | Thay đổi quyền quan trọng không có chứng cứ. |
| Service catalog không còn owner | Ngăn cấp quyền mới, tạo case chuyển ownership theo rủi ro | Tài khoản dịch vụ nhận thêm quyền không ai chịu trách nhiệm. |

Không có một quy tắc fail-open/fail-closed áp dụng cho toàn tổ chức. Quyết định cần dựa trên **loại thao tác, mức nhạy cảm, thời gian dữ liệu còn đáng tin, sự phụ thuộc vận hành và biện pháp khôi phục**, đồng thời phải được người có thẩm quyền duyệt.

### Ghi giả định và tiêu chí kích hoạt review

Ví dụ “token IdP có tuổi tối đa 15 phút nên quyền bị thu hồi sẽ hết hiệu lực chậm nhất theo đường token này”. Giả định chỉ có ý nghĩa khi **không tồn tại token riêng khác, local login, refresh session hoặc cache ứng dụng chưa kiểm soát**. Nếu phát hiện một đường mới, decision phải được xem xét lại, không tiếp tục khẳng định tính đầy đủ trên cơ sở giả định cũ.

## 20. Kiểm chứng chất lượng quyết định trước khi phê duyệt

Một hồ sơ không nên được chấp thuận chỉ vì đã điền đủ biểu mẫu. Cần xem nội dung có thể dẫn tới hành động đúng và kiểm tra được không.

### Checklist phản biện

1. **Vấn đề có thực và scope rõ?** Nêu identity types, target, tenant, environment và action bị ảnh hưởng.
2. **Nguồn sự thật xác định?** Owner của thuộc tính và quyết định có đúng thẩm quyền?
3. **Các phương án có công bằng?** Có nêu phương án khả thi và lý do loại bỏ, không dựng phương án giả?
4. **Tiêu chí ra quyết định nhất quán?** Rủi ro, least privilege, vận hành, khả dụng, chi phí và bằng chứng.
5. **Có điều kiện ngoại lệ?** Trường hợp thiếu dữ liệu, lỗi tích hợp, quyền local và break-glass được xử lý.
6. **Có SoD và approval phù hợp?** Không cho người hưởng lợi tự mở rộng quyền mà thiếu kiểm soát.
7. **Có mốc hiệu lực và rollback?** Biết khi nào thay đổi tác động, ai có quyền dừng rollout.
8. **Có thể đo và kiểm chứng?** Test âm tính, readback và audit evidence gắn mục tiêu.
9. **Có owner và review trigger?** Ai xử lý khi giả định sai, nền tảng thay đổi hoặc rủi ro mới xuất hiện?
10. **Không mâu thuẫn quyết định đang hiệu lực?** Nếu mâu thuẫn, phải giải thích record nào được thay thế.

### Decision readiness gates

| Gate | Điều kiện phải đạt | Nếu thiếu |
|---|---|---|
| **Review-ready** | Có context, scope, options, tiêu chí và owner | Yêu cầu bổ sung. |
| **Approval-ready** | Có đánh giá rủi ro, thẩm quyền, SoD và phương án kiểm chứng | Chưa chấp thuận. |
| **Implementation-ready** | Có mapping policy/config, target scope, test và rollback | Không rollout thay đổi nhạy cảm. |
| **Verification-ready** | Có nguồn dữ liệu readback, audit và điều kiện pass/fail | Không tuyên bố hoàn tất triển khai. |
| **Retirement-ready** | Phụ thuộc đã chuyển, ngoại lệ được đóng, hệ thống đích xác nhận | Không xóa hồ sơ cũ hoặc ngừng kiểm soát sớm. |

**STEP 4 ở đây là soạn tài liệu học tập**, không phải chạy các gate hoặc Content QA cho hệ thống thật. Các gate là mô hình áp dụng khi triển khai chương trình IAM.

## 21. Ghi quyết định khi xảy ra bất đồng hoặc sự cố

### Tình huống A — Mover và xung đột SoD

Nhân viên từ người phê duyệt chi chuyển sang người thực hiện thanh toán. Đội nghiệp vụ muốn cấp quyền mới ngay để không gián đoạn công việc; Security yêu cầu tránh giữ hai quyền xung đột.

**Decision record cần thể hiện:** quy tắc SoD bắt buộc; phương án thu hồi quyền duyệt trước rồi cấp quyền thanh toán, hoặc cơ chế cách ly nguyên tử tương đương; mức độ gián đoạn cho phép; kết quả readback; và phương án nếu target không phản hồi. Chỉ nói “cấp quyền sau khi manager duyệt” là chưa đủ để giải quyết xung đột.

### Tình huống B — Leaver qua IdP nhưng còn account local

Ứng dụng ERP local thiếu API. Đội triển khai đề xuất coi IdP disable là hoàn tất Leaver vì số liệu đẹp hơn.

**Decision record cần thể hiện:** account local nằm trong scope; bằng chứng thao tác thủ công và đối soát; trách nhiệm owner; kế hoạch tích hợp; trạng thái `INCOMPLETE` khi ERP chưa xác nhận; metric báo cáo theo đúng phạm vi. Không được thay đổi ý nghĩa “hoàn tất” chỉ để đạt KPI.

### Tình huống C — Service owner nghỉ việc

Kỹ sư quản lý robot CI/CD nghỉ việc, nhưng workload đang chạy pipeline production.

**Decision record cần thể hiện:** HRIS Leaver kích hoạt thu hồi quyền cá nhân và review quyền/credential của workload; service catalog chịu trách nhiệm xác nhận workload còn hoạt động; owner mới có thẩm quyền; tiêu chí rotation và ngày phải hoàn tất. Không tự kết luận robot phải bị xóa hoặc tiếp tục vô hạn.

### Tình huống D — Đường break-glass

Nhóm vận hành muốn một account admin dùng được khi IdP lỗi. Security lo ngại đây trở thành tài khoản đặc quyền không giám sát.

**Decision record cần thể hiện:** lý do cần độc lập với IdP, phương án bảo vệ credential, người có thể sử dụng, điều kiện khẩn cấp, giới hạn quyền, giám sát ngoại tuyến/đồng bộ hậu sự cố và diễn tập. Phải có người chấp nhận rủi ro còn lại và quy tắc hậu kiểm.

### Tình huống E — Đổi chiến lược review định kỳ

Tổ chức muốn thay review tất cả quyền mỗi quý bằng **review theo rủi ro và theo sự kiện**.

**Decision record cần thể hiện:** quyền nào tiếp tục review định kỳ, trigger Mover/Leaver/owner-change, owner của từng lớp, cách chứng minh quyền đặc biệt được rà soát, những trường hợp chưa có dữ liệu và kế hoạch đo hiệu quả. Không ghi “review tự động” nếu thực tế chỉ gửi email mà không thực hiện remediation.

## 22. Bảo vệ decision record và dữ liệu nhạy cảm

Decision record có thể chứa thông tin hệ thống, cấu trúc quyền, điểm yếu connector hoặc rủi ro được chấp nhận. Nó cần **chính sách lưu, phân quyền và bảo vệ tính toàn vẹn** tương ứng:

- **Version control:** giữ lịch sử, người sửa, thời điểm và nội dung thay đổi; nội dung đã duyệt không bị âm thầm sửa thành nghĩa mới.
- **Approval integrity:** bản được phê duyệt gắn với nội dung/version cụ thể; không dùng chữ ký/approval cũ cho phiên bản khác.
- **Least privilege:** người soạn/nhận xét không mặc nhiên được chấp thuận quyết định hoặc thay policy production.
- **Audit của chính decision register:** ai xem, sửa, publish, supersede hoặc xóa bản ghi nhạy cảm.
- **Data minimization:** lưu ID tham chiếu thay vì password, token, secret, hồ sơ nhân sự cá nhân hoặc thông tin điều tra không cần thiết.
- **Backup và phục hồi:** có thể truy xuất quyết định lịch sử khi hệ thống lưu trữ chính gặp sự cố.
- **Retention:** thời gian lưu dựa trên yêu cầu nghiệp vụ, kiểm toán, hợp đồng và pháp lý áp dụng; không tự đặt một thời hạn chung.
- **Liên kết có quyền:** evidence link không làm lộ dữ liệu của hệ thống khác cho người không có thẩm quyền.

Nếu dùng một repository Markdown, có thể áp code review/branch protection và phân quyền publish. Nếu dùng hệ thống GRC hoặc ticket, cần điều khiển tương đương: approval authority, versioned content, trạng thái và khả năng xuất lịch sử. Công cụ không quan trọng bằng kiểm soát.

## 23. Chỉ số đánh giá chất lượng hệ thống ghi quyết định

Không tối ưu để viết thật nhiều ADR; cần đánh giá **quyết định trọng yếu đã có hồ sơ tốt và được liên kết với kiểm soát thật hay chưa**.

| Metric | Cách hiểu | Lưu ý |
|---|---|---|
| **Decision coverage** | Quyết định IAM thuộc danh mục bắt buộc đã có record hợp lệ / tổng quyết định bắt buộc được inventory | Cần danh sách phạm vi chuẩn, không đếm tùy hứng. |
| **Owner/authority coverage** | Record active có accountable owner và approval phù hợp / tổng record active | Tránh self-approval và owner đã Leaver. |
| **Implementation traceability** | Record accepted có link tới policy/config/test/rollout phù hợp | Không ngụ ý đã verified chỉ vì có link. |
| **Verified implementation rate** | Quyết định cần triển khai có bằng chứng pass theo scope / số quyết định đã đến hạn triển khai | Tách accepted và verified. |
| **Open decision aging** | Thời gian các proposal hoặc blocker chưa có kết luận | Ưu tiên quyết định ảnh hưởng Leaver/privileged. |
| **Superseded dependency drift** | Policy/connector vẫn dựa trên record đã bị thay thế | Phát hiện rollout chưa hoàn tất. |
| **Decision review timeliness** | Record được xem lại khi đến hạn hoặc trigger theo chính sách | Nên xét rủi ro; không đợi lịch với sự cố critical. |
| **Exception expiry compliance** | Ngoại lệ hết hạn được thu hồi/đóng bằng chứng / tổng ngoại lệ đến hạn | Không tự gia hạn để cải thiện số. |
| **Decision-to-audit traceability** | Luồng quan trọng có thể truy tới decision/policy ID và evidence / luồng thuộc scope kiểm tra | Phải nêu hệ thống thiếu nguồn. |
| **Policy contradiction findings** | Số quy tắc active mâu thuẫn với decision đang hiệu lực | Đo khả năng kiểm soát thay đổi. |

Metric catalog nên có owner, mẫu số, nguồn dữ liệu, thời điểm tính, đơn vị, phân loại risk và xử lý thiếu dữ liệu. Ví dụ **90% record được approved** có thể che giấu record Leaver quan trọng chưa triển khai; vì vậy cần drill-down và ưu tiên theo rủi ro, không chỉ tổng tỷ lệ.

## 24. Quy trình thực hành xây dựng decision log IAM

Một dự án thiết kế IAM có thể triển khai theo trình tự sau:

1. **Liệt kê miền quyết định:** identity source, account scope, correlation, role, policy, event, approval, review, audit, metric, privileged và workload.
2. **Xác định owner:** phân công người chịu trách nhiệm kết luận, bên tham vấn và approver phù hợp với từng miền.
3. **Thống nhất mẫu record:** ID, status, scope, problem, options, rationale, risk, effectiveFrom, review trigger, evidence và links.
4. **Lập decision register:** đánh số ổn định, hiện trạng, phụ thuộc và những đề xuất đang chờ.
5. **Ưu tiên quyết định rủi ro cao:** Leaver completion, privileged access, source authority, SoD và break-glass.
6. **Viết và phản biện:** đưa ra lựa chọn thực tế, ghi căn cứ và phản biện chưa giải quyết; bảo đảm độc lập người xét khi cần.
7. **Chốt và giao triển khai:** ký nhận decision/version, mapping xuống policy/connector, phân công rollout và kế hoạch rollback.
8. **Đối soát bằng chứng:** chạy test phù hợp, đọc trạng thái đích, ghi nhận những mục chưa được xác nhận.
9. **Theo dõi ngoại lệ:** owner, expiry, mitigation, alert và điều kiện kết thúc.
10. **Xem lại khi ngữ cảnh thay đổi:** thêm SaaS, đổi HRIS, đổi chủ dữ liệu, chính sách SoD mới, connector failure hoặc metric cho thấy quyền tồn dư.

### Các đầu ra cần bàn giao

| Artifact | Mục đích |
|---|---|
| **Decision register** | Danh sách các quyết định và trạng thái, owner, phụ thuộc. |
| **ADR/decision record** | Bối cảnh, phương án, lựa chọn, rủi ro, lý do và thẩm quyền. |
| **Policy/role mapping** | Quy tắc nào cụ thể hóa quyết định; phiên bản đang chạy. |
| **Implementation plan** | Đội/target chịu trách nhiệm, rollout, rollback, thời điểm hiệu lực. |
| **Validation matrix** | Test positive/negative, readback và phạm vi cần chứng minh. |
| **Exception/risk register** | Rủi ro chưa giải quyết, owner, mitigation, expiry. |
| **Audit/evidence links** | Chuỗi sự kiện và kết quả vận hành có thể truy ngược về quyết định. |
| **Review trigger list** | Điều kiện nào làm quyết định cần xem lại, thay thế hoặc nghỉ áp dụng. |

## 25. Các lỗi thường gặp khi ghi quyết định

1. **Chỉ viết kết luận:** “Dùng SCIM” nhưng không có lý do, scope, giới hạn và phương án nếu connector lỗi.
2. **Nhầm proposal với quyết định:** tài liệu đang `PROPOSED` bị đội triển khai dùng như policy đã được phê duyệt.
3. **Nhầm quyết định được duyệt với triển khai hoàn tất:** không có test/readback nhưng `status=done`.
4. **Không nêu phương án bị loại:** người mới không biết vì sao trước đây không chọn ticket, API custom hoặc group synchronization.
5. **Không có owner/authority:** không ai chịu trách nhiệm khi giả định sai hoặc decision đã lỗi thời.
6. **Không ghi hệ quả tiêu cực:** che độ trễ Leaver, rủi ro session/token cũ hoặc khó xử lý account local.
7. **Phạm vi mơ hồ:** “Mọi account” trong khi thực tế chỉ IdP và hai SaaS được tích hợp.
8. **Không liên kết với role/policy version:** khó xác định một quyền được cấp theo quyết định nào tại thời điểm lịch sử.
9. **Không quản lý supersession:** quyết định mới xuất hiện nhưng các team vẫn làm theo file cũ.
10. **Chỉ chọn vì dễ triển khai:** quyết định bỏ qua SoD, dữ liệu nhạy cảm hoặc đường break-glass mà không đánh giá rủi ro.
11. **Không ghi nguồn thuộc tính và độ mới:** ABAC có thể dùng dữ liệu tenant/hợp đồng đã hết hạn.
12. **Dùng approval cá nhân thay cho quyết định hệ thống:** quyền đặc biệt được cấp hàng loạt theo yêu cầu riêng lẻ, không có rule quản trị chung.
13. **Đưa bí mật vào decision record:** token, password hoặc thông tin nhân sự nhạy cảm có thể bị phát tán cùng tài liệu.
14. **Không xác định trigger review:** ADR sống mãi dù hệ thống, owner và yêu cầu bảo mật đã thay đổi.
15. **Không xem mức độ bao phủ của audit/metric:** quyết định “Leaver đã được xác minh” không hề bao gồm target legacy.

## 26. Bài tập thực hành: tạo decision register cho chương trình IAM

Một doanh nghiệp có HRIS, VMS, IdP hỗ trợ SSO, hai SaaS có SCIM, một ERP local, cloud production, PAM và robot CI/CD. Doanh nghiệp đang chuẩn hóa Joiner–Mover–Leaver. Các tình huống xuất hiện:

1. HRIS và VMS đều lưu ngày kết thúc hợp đồng nhà thầu nhưng giá trị không đồng nhất.
2. SaaS hỗ trợ SCIM để disable account, nhưng không cho đọc lại đủ entitlement; ERP chỉ có tài khoản local.
3. Finance yêu cầu role `EXPENSE_APPROVER` và `PAYMENT_EXECUTOR` có thể cùng tồn tại để công việc không gián đoạn; Security phản đối theo SoD.
4. Người quản trị cần quyền cloud production trong thời gian ngắn; PAM/JIT có thể tích hợp nhưng một số account cũ có quyền direct.
5. Owner robot CI/CD nghỉ việc; workload vẫn chạy; một credential tĩnh chưa được luân chuyển.
6. Chương trình muốn báo KPI “Leaver hoàn tất trong 5 phút” nhưng dashboard hiện chỉ đếm lệnh được gửi.

**Yêu cầu:**

1. Lập decision register có ít nhất **sáu record**, ghi ID, title, status, owner, approver, phụ thuộc, ngày review và kế hoạch thực thi.
2. Viết **một ADR đầy đủ** về nguồn `contractEndAt`: so sánh HRIS, VMS và last-write-wins; xác định cách xử lý khi nguồn không sẵn sàng.
3. Viết ADR về **Leaver completion**: phân biệt ACK với target readback; xác định những gì phải báo `INCOMPLETE`.
4. Lập ma trận risk/mitigation cho ERP local không có API, với owner, hạn xử lý, evidence và metric coverage.
5. Nêu quyết định SoD của Finance và cách xử lý Mover để không tồn tại giai đoạn giữ hai quyền xung đột trái policy.
6. Đề xuất policy PAM/JIT và decision record cho quyền cloud, gồm hiệu lực, expiry, break-glass và điều kiện hậu kiểm.
7. Với robot CI/CD, quyết định cách chuyển owner, credential rotation và điều kiện ngừng dịch vụ; giải thích vì sao Leaver cá nhân không tự đồng nghĩa retired workload.
8. Vẽ đồ thị phụ thuộc giữa nguồn danh tính, account scope, policy JML, audit evidence và KPI completion.
9. Xác định **năm kiểm thử âm tính**, gồm event đến trễ, role gán trực tiếp, sai tenant, target không readback và security hold.
10. Mô tả quy trình **supersede** khi tương lai ERP bổ sung API và hệ thống hợp đồng mới thay thế VMS.

### Tiêu chí nghiệm thu

Một bộ hồ sơ quyết định đủ tốt cần chứng minh:

- Có **decision ID, status, scope, owner, authority, effectiveFrom và review trigger**.
- Mỗi lựa chọn có bối cảnh, ít nhất một phương án khác, lý do và hệ quả, không chỉ câu kết luận.
- Rủi ro còn tồn tại có owner, biện pháp bù trừ, hạn và điều kiện đóng; không bị che giấu trong status `ACCEPTED`.
- **Approval** của record gắn với đúng nội dung/version và thẩm quyền phê duyệt.
- **Implementation** được theo dõi riêng; tiêu chí `VERIFIED` dựa trên test và bằng chứng phù hợp, không dựa trên việc gửi lệnh.
- Quyết định JML phản ánh **nguồn có thẩm quyền, thời điểm hiệu lực, IdP/SCIM/PAM và account local**.
- Quyền theo RBAC/ABAC, SoD, approval, review và non-human identity có logic nhất quán với các quyết định khác.
- Mọi quyết định có thể truy vết tới policy/config/runbook/metric/audit mà không đưa secret vào tài liệu.
- Khi thay đổi hệ thống/nguồn/role/scope, bản cũ được **superseded** có dấu vết và có kế hoạch chuyển tiếp.

**Ghi lại quyết định là giữ cho chương trình IAM có bộ nhớ tổ chức và khả năng giải trình.** Một hồ sơ tốt không chỉ cho biết “đã chọn gì” mà còn giúp người vận hành biết tại sao lựa chọn ấy còn đúng, rủi ro nào phải theo dõi, phải triển khai những gì và bằng chứng nào xác nhận quyền truy cập đã được quản trị đúng trong suốt Joiner–Mover–Leaver.
