# Escalation quá hạn trong Access Recertification: chuyển cấp đúng người, xử lý đúng rủi ro và xác minh thu hồi

**Escalation quá hạn (overdue escalation)** trong **Access Recertification** là quy trình **phát hiện, nhắc nhở, chuyển cấp, can thiệp và theo dõi xử lý** những hạng mục rà soát quyền truy cập **không có quyết định hợp lệ hoặc chưa được khắc phục trước thời hạn cam kết**. Mục tiêu không chỉ là thúc đẩy người review bấm một nút trong hệ thống mà là bảo đảm **quyền có rủi ro không bị giữ vô thời hạn vì thiếu phản hồi**, các quyết định được đưa ra **đúng thẩm quyền** và những yêu cầu thu hồi **được thực thi thực sự**.

Một chiến dịch recertification có thể gửi 2.000 mục cho các manager và application owner. Nếu 150 mục đã quá hạn, hệ thống cần biết **mục nào rủi ro cao, ai đang chịu trách nhiệm, nguyên nhân chậm, phải thông báo ai tiếp theo, có cần biện pháp hạn chế tạm thời không** và **khi nào được kết luận đã xử lý xong**. Những câu hỏi đó là phạm vi của overdue escalation.

Bài thuộc chương **Access recertification** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Ngữ cảnh lớn hơn là **quản lý vòng đời danh tính (IAM) theo Joiner–Mover–Leaver (JML)**: xác minh danh tính, tạo account, cấp quyền, rà soát khi thay đổi nhiệm vụ và thu hồi khi kết thúc quan hệ làm việc. Escalation phải nối dữ liệu từ **HR/VMS, IAM/IGA, IdP/SSO, SCIM, RBAC/ABAC, PAM/PIM, service account và kiểm toán** để tránh **quyền truy cập tồn dư**.

**Nguyên tắc cốt lõi:** **Quá hạn không tự đồng nghĩa “được giữ quyền”, cũng không luôn đồng nghĩa “xóa ngay quyền”**. Quyết định phụ thuộc **chính sách, rủi ro, loại quyền, trạng thái JML, khả năng xác minh và tác động vận hành**. Với quyền đặc quyền hoặc chủ thể đã Leaver, sự chậm trễ phải được xử lý như một vấn đề bảo mật có thời hạn; với hệ thống production phụ thuộc service account, cần kiểm soát bù trừ và kế hoạch thay đổi an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **escalation quá hạn** và phân biệt nó với **reminder, reviewer reassignment, access certification, remediation và incident response**.
2. Xác định các loại quá hạn: **chưa review, thiếu thông tin, chưa được phê duyệt, chưa thu hồi, chưa readback, ngoại lệ quá hạn**.
3. Thiết kế **deadline, SLA/SLO nội bộ, timer, ngưỡng rủi ro, tuyến escalation và tiêu chí đóng** có thể kiểm toán.
4. Tránh hai sai lầm: **auto-KEEP khi không ai phản hồi** và **auto-REVOKE mù quáng gây gián đoạn hệ thống quan trọng**.
5. Chọn reviewer dự phòng, owner và cấp quản lý phù hợp; kiểm tra **ủy quyền, xung đột lợi ích/SoD** khi chuyển cấp.
6. Phân biệt **review decision completion** với **remediation completion** và **verified effective access**.
7. Liên hệ các sự kiện **Joiner–Mover–Leaver**, contractor, federated subject và workload/service account với ưu tiên escalation.
8. Thiết kế thông báo, workflow, bảng điều khiển, log, bằng chứng và các phép đo chất lượng.
9. Áp dụng quy trình escalation cho quyền **privileged, data export, token, session, direct grant và entitlement đa ứng dụng**.

## 2. Access recertification là gì và escalation nằm ở đâu?

**Access recertification** là quá trình một người hoặc bộ phận **có thẩm quyền** xác nhận lại những quyền đang được cấp: **còn cần, đúng phạm vi, phù hợp nhiệm vụ và chính sách hay không**. Nó thường là một loại access review được tổ chức theo chiến dịch, theo rủi ro hoặc theo sự kiện.

Một item minh họa:

~~~text
Review item: RI-904
Subject:      P-2048
Account:      crm-P-2048
Entitlement:  customer.export@tenant-A
Grant source: direct ACL
Reviewer:     Customer Data Owner
Due:          2026-12-10 17:00 +07:00
Status:       PENDING_REVIEW
Risk:         HIGH
~~~

Nếu hết hạn mà chưa có quyết định KEEP/REVOKE/MODIFY hợp lệ, item trở thành **review overdue**. Nếu reviewer đã chọn REVOKE nhưng target CRM vẫn cho export sau hạn xử lý, item là **remediation overdue**. Chúng đều cần escalation nhưng **không dùng cùng một kịch bản xử lý**.

### 2.1. Phân biệt các hoạt động

| Hoạt động | Mục đích | Có thay thế escalation không? |
|---|---|---|
| **Reminder** | Nhắc người chịu trách nhiệm trước/gần hạn | Không; chỉ là bước giao tiếp |
| **Escalation** | Chuyển trách nhiệm hoặc mức ưu tiên đến người có thẩm quyền cao/phù hợp hơn | Chính là cơ chế xử lý tồn đọng |
| **Reassignment** | Chuyển item tới reviewer thay thế đủ thẩm quyền | Có thể là một hành động escalation |
| **Certification decision** | KEEP, REVOKE, MODIFY, ESCALATE... | Chưa chứng minh quyền đã thay đổi |
| **Remediation** | Gỡ hoặc giảm quyền theo quyết định | Có thể bị quá hạn riêng |
| **Readback/verification** | Chứng minh target thực sự áp trạng thái mong muốn | Điều kiện đóng của nhiều item |
| **Security incident** | Ứng phó khi có nghi vấn lạm dụng/compromise hoặc nguy cơ cấp bách | Có thể chạy đồng thời, không chờ campaign |
| **Exception management** | Quản lý trường hợp chưa thể khắc phục ngay với risk owner và expiry | Không phải cách đóng item giả tạo |

**“Đã gửi email nhắc” không phải “đã escalation thành công”.** Phải biết người được chuyển cấp đã nhận trách nhiệm, đưa ra hành động, và kết quả có được xác minh hay không.

## 3. Bốn đồng hồ thời hạn cần tách biệt

Một hệ thống có thể gắn một mục recertification với nhiều thời điểm:

1. **Review due time**: Hạn reviewer phải đưa ra quyết định hợp lệ.
2. **Remediation due time**: Hạn áp quyết định REVOKE/MODIFY vào target.
3. **Verification due time**: Hạn thu thập readback hoặc negative test theo chính sách.
4. **Access expiry / JML effective time**: Mốc mà quyền **không còn được phép tồn tại**, độc lập với lịch campaign.

Ví dụ:

~~~text
03/12    Campaign giao item cho reviewer
08/12    Hạn reviewer quyết định
09/12    Reviewer chọn REVOKE (đã trễ 1 ngày)
10/12    Hạn connector gỡ quyền
11/12    Target vẫn cho phép -> remediation overdue
12/12    Hạn readback -> verification overdue

Nhưng:
07/12    Contractor đã hết engagement.
         Quyền contractor phải được xử lý theo
         chính sách Leaver ngay từ 07/12,
         KHÔNG đợi tới hạn campaign 08–12/12.
~~~

**Mốc sự kiện bảo mật có thể đến trước hạn review.** Một hệ thống escalation tốt không dùng deadline campaign để hợp thức hóa cửa sổ quyền sai sau Leaver.

### 3.1. SLA, SLO và policy deadline

- **Deadline:** Mốc cụ thể của item/campaign.
- **SLA nội bộ:** Cam kết trách nhiệm và thời gian giữa các nhóm, nếu tổ chức thiết lập.
- **SLO vận hành:** Mục tiêu đo chất lượng xử lý, có thể khác nghĩa vụ bắt buộc.
- **Policy enforcement deadline:** Thời điểm quyền phải mất hiệu lực theo chính sách.

Không có quy tắc quốc tế chung rằng mọi item phải escalation sau “ba ngày”. Các khoảng xử lý phải được **business owner, IAM governance và security** thiết kế theo rủi ro và yêu cầu thực tế.

## 4. Các trạng thái quá hạn cần được phân loại

| Loại quá hạn | Biểu hiện | Owner thường liên quan | Hành động ưu tiên |
|---|---|---|---|
| **Assignment overdue** | Item chưa có reviewer đủ thẩm quyền | Campaign owner, manager hierarchy | Chỉ định reviewer đúng |
| **Decision overdue** | Reviewer chưa chọn KEEP/REVOKE/MODIFY | Reviewer, reviewer manager, resource owner | Nhắc, chuyển cấp, đánh giá rủi ro |
| **Information overdue** | Thiếu bằng chứng, không rõ permission | App owner, IAM data steward | Bổ sung dữ liệu, không quyết định bừa |
| **Approval overdue** | Đã đề nghị ngoại lệ nhưng người duyệt không trả lời | Risk owner, approver delegate | Escalate phê duyệt độc lập |
| **Remediation overdue** | REVOKE/MODIFY chưa áp được | IAM provisioning, target owner | Sửa connector/target, bù trừ |
| **Verification overdue** | Đã thao tác nhưng không xác minh quyền hiệu dụng | Target owner, verification team | Readback, negative test phù hợp |
| **Exception expiry overdue** | Ngoại lệ hết TTL vẫn chưa đóng/đánh giá | Risk owner, security | Rà soát hoặc chặn theo policy |
| **Ownership overdue** | Reviewer hoặc service owner đã Leaver | HR/VMS, service catalog owner | Reassign, ngăn quyền mồ côi |

**Không gộp các loại này thành một nhãn “PENDING”.** Nếu không có reason code, đội vận hành dễ gửi email nhầm người và bỏ lỡ quyền rủi ro cao đang còn hiệu lực.

## 5. Tại sao escalation quá hạn là một kiểm soát bảo mật?

Recertification thường có nhiều đơn vị tham gia: manager hiểu nhiệm vụ, app owner hiểu permission, security hiểu SoD, IAM vận hành connector. Việc review bị tồn đọng có thể do người duyệt bận, rời công ty, không hiểu quyền hoặc dữ liệu nguồn sai.

Không có escalation, những item này sẽ:

- Tiếp tục được xem như **quyền hợp lệ do chưa ai bác bỏ**.
- Tạo **privilege creep** sau Mover và khi dự án kết thúc.
- Duy trì các quyền **admin/export/delete** không ai xác nhận.
- Che giấu **account không còn owner**, service principal bỏ dùng.
- Khiến campaign báo “đã xong” trong khi **REVOKE chưa áp**.
- Tăng thời gian hệ thống chấp nhận **token/session/grant cũ**.
- Để nguy cơ **SoD conflict, cross-tenant access** và ngoại lệ kéo dài.

**Escalation tạo cơ chế trách nhiệm và xử lý**, nhưng chỉ hiệu quả nếu nó có **đầu ra xác minh được**. Gửi thông báo hàng ngày không tự làm tăng an toàn khi không ai có quyền giải quyết.

## 6. Phân tầng rủi ro để chọn đường escalation

Cùng quá hạn một ngày, quyền `wiki.read` và `production.admin` không nên được xử lý như nhau.

| Nhóm rủi ro minh họa | Ví dụ | Hướng escalation |
|---|---|---|
| **Thấp** | Đọc tài liệu nội bộ không nhạy cảm | Nhắc reviewer, chuyển owner theo lịch |
| **Trung bình** | Sửa ticket/dữ liệu dự án có giới hạn | Escalate manager/app owner nếu thiếu quyết định |
| **Cao** | Export dữ liệu nhạy cảm, access cross-project | Security/data owner phối hợp, hạn chế tạm thời khi cần |
| **Rất cao/đặc quyền** | Cloud admin, IdP admin, signing key, production secret | Ưu tiên xử lý; có thể hạn chế/thu hồi trước theo policy |
| **Đã mất eligibility** | Leaver, contractor hết hạn, compromised identity | Trigger JML/incident ngay; campaign không trì hoãn revoke |

### 6.1. Những yếu tố cần chấm rủi ro

- **Action:** read, write, export, approve, delete, administer.
- **Resource:** production/staging, tenant, dự án, phân loại dữ liệu.
- **Privilege reach:** Có thể cấp quyền cho người khác, sửa policy hoặc credential không?
- **Subject:** Human, contractor, guest, service account, privileged persona.
- **Identity state:** Active, suspended, Mover, engagement ended, unknown.
- **Grant provenance:** Role chuẩn, direct grant, JIT, ngoại lệ, quyền không có owner.
- **Authentication/session:** Có token/credential/phiên dài hạn không?
- **Data confidence:** Snapshot, đồng bộ IdP/SCIM/target có đáng tin không?
- **Remediation feasibility:** Gỡ an toàn được ngay hay cần phụ thuộc production?
- **Threat intelligence:** Có dấu hiệu abuse/compromise đang diễn ra không?

**Risk tier không do requester/reviewer tự khai một cách tùy ý.** Nên dựa trên entitlement catalog, resource classification, chính sách, source-of-truth và security signals.

## 7. Ma trận escalation minh họa theo thời gian

Một ma trận vận hành có thể thiết kế theo **T = hạn ra quyết định**, với các khoảng **chỉ là ví dụ cho bài học**:

| Mốc minh họa | Trạng thái | Đối tượng nhận | Hành động |
|---|---|---|---|
| **T−5 ngày làm việc** | Sắp đến hạn | Reviewer | Nhắc nhiệm vụ, danh sách item cần review |
| **T−1 ngày** | Gần hạn | Reviewer và delegate đã đăng ký | Nêu mức ưu tiên và cách escalation |
| **T** | Đến hạn | Reviewer/campaign owner | Xác nhận item chưa có quyết định |
| **T+1 ngày** | Quá hạn mức 1 | Reviewer manager + app/data owner | Yêu cầu xử lý hoặc reassign có lý do |
| **T+3 ngày** | Quá hạn mức 2 | IAM governance + risk owner | Quyết định hạn chế quyền/ngoại lệ theo rủi ro |
| **T+5 ngày** | Quá hạn mức 3 | Security lead/đơn vị điều hành thích hợp | Kích hoạt quy trình xử lý tồn đọng nghiêm trọng |
| **Sau quyết định REVOKE** | Remediation timer riêng | Connector/target owner | Áp thay đổi và xác minh trong SLA của loại quyền |

**Các mốc trên không phải khuyến nghị bắt buộc hay con số chuẩn.** Đối với tài khoản Leaver hoặc đặc quyền có dấu hiệu bị lạm dụng, phải xử lý **ngay theo chính sách**, không đợi T+3/T+5. Với quyền thường gắn công việc sống, escalation có thể ưu tiên **reassignment và xác minh nhu cầu** trước khi gián đoạn hệ thống.

### 7.1. Business days hay calendar days?

Nên định nghĩa rõ:

- Hạn tính theo **ngày làm việc** hay **ngày dương lịch**.
- Timezone, giờ kết thúc, ngày nghỉ và múi giờ của reviewer.
- Khi nào timer dừng/tạm dừng hợp lệ: ví dụ chờ sửa dữ liệu nguồn có owner.
- Có quyền gia hạn deadline không, ai phê duyệt và giới hạn bao nhiêu lần.
- Mốc JML/thu hồi quyền theo chính sách **không bị kéo dài** chỉ vì gia hạn review.

Tránh thay đổi `dueAt` trực tiếp để “xóa nợ quá hạn”; phải lưu **originalDueAt, extendedDueAt, extensionReason, approver và audit trail**.

## 8. Escalation cần định tuyến đến đúng người

Tuyến escalations là **chuỗi trách nhiệm**, không chỉ là sơ đồ cấp bậc.

~~~text
Review item
  ├─ Reviewer hiện tại
  ├─ Reviewer delegate / backup reviewer
  ├─ Manager hoặc sponsor có thẩm quyền
  ├─ Application / resource / data owner
  ├─ IAM campaign owner + connector owner
  ├─ Security / privileged access / SoD owner
  └─ Risk owner và leadership theo mức nghiêm trọng
~~~

### 8.1. Những trường hợp phải reassign

- Reviewer đã **Leaver** hoặc engagement của reviewer đã hết.
- Reviewer Mover, không còn phụ trách resource.
- Reviewer đang nghỉ phép dài ngày; delegate được xác minh.
- Reviewer có xung đột lợi ích, đang tự review quyền của mình.
- Reviewer không biết entitlement nghĩa là gì, cần app owner.
- Item không có owner hoặc bị gán nhầm do identity mapping sai.

**Không thay người review bằng một tài khoản generic admin** để đánh dấu KEEP hàng loạt. Reviewer mới phải có căn cứ thẩm quyền, scope và khả năng giải thích quyết định.

### 8.2. Quản lý reviewer delegation

Một delegate có thể xử lý thay khi manager vắng, nhưng cần kiểm:

1. Ai cấp ủy quyền và giới hạn thời gian?
2. Delegate được xem những item/resource nào?
3. Có quyền quyết định quyền nhạy cảm hay chỉ được chuyển tiếp?
4. Có vi phạm SoD hoặc tự chứng nhận không?
5. Audit lưu cả **reviewer ban đầu, delegate và decision actor** không?

Delegation không nên trở thành cách bỏ kiểm soát “four-eyes” đối với đặc quyền.

## 9. Workflow escalation từ phát hiện đến đóng

~~~mermaid
flowchart TD
    A["Campaign / Review item<br/>deadline + scope + owner"] --> B["Scheduler đánh giá<br/>clock + risk + JML state"]
    B --> C{"Item đã có decision<br/>hợp lệ trước due?"}
    C -->|Có| D{"Decision là<br/>KEEP hay REVOKE/MODIFY?"}
    D -->|KEEP| K["Kiểm căn cứ + version<br/>Close review decision"]
    D -->|REVOKE/MODIFY| R["Remediation timer<br/>Target update"]
    C -->|Không| E["OVERDUE_REVIEW<br/>Risk-based escalation"]
    E --> F{"Eligibility/sự cố<br/>đòi chặn khẩn?"}
    F -->|Có| S["JML/Incident/PAM<br/>Xử lý ưu tiên ngay"]
    F -->|Không| G["Reminder -> delegate<br/>manager -> owner/security"]
    G --> H["Decision hoặc<br/>exception có approval"]
    H --> D
    S --> R
    R --> V["Readback role, ACL,<br/>token/session và API"]
    V --> W{"Quyền hiệu dụng<br/>đạt desired state?"}
    W -->|Có| X["VERIFIED_CLOSED<br/>Audit + evidence"]
    W -->|Không / Unknown| Y["OVERDUE_REMEDIATION<br/>Owner + bù trừ + retry"]
    Y --> R
    K --> Z["Theo dõi TTL,<br/>JML và recert tiếp"]
~~~

**Sơ đồ mang tính tham khảo.** Một quyết định KEEP có thể cần đánh giá lại nếu trạng thái JML đổi trong lúc chờ; vì vậy không được “chốt” quyền dài hạn dựa trên dữ liệu cũ mà thiếu kiểm tra hiện hành.

### 9.1. Không đóng vì một email đã được gửi

Trạng thái `ESCALATED` chỉ cho biết đã **bắt đầu chuyển cấp**. Các điều kiện đóng phải gắn với **decision hợp lệ** hoặc **remediation được xác minh**, tùy item và policy.

## 10. Mô hình trạng thái cho item quá hạn

Một state machine minh họa:

~~~text
ASSIGNED
  └── PENDING_REVIEW
       ├── REMINDER_SENT
       ├── OVERDUE_L1
       ├── OVERDUE_L2
       ├── OVERDUE_L3
       ├── NEEDS_INFORMATION (vẫn có owner/SLA)
       ├── REASSIGNED (lưu lịch sử reviewer)
       └── DECISION_RECORDED
             ├── KEEP_VERIFIED_BY_POLICY
             ├── REVOKE_PENDING
             ├── MODIFY_PENDING
             └── EXCEPTION_APPROVAL_PENDING

REVOKE_PENDING / MODIFY_PENDING
  ├── TARGET_CHANGE_IN_PROGRESS
  ├── REMEDIATION_OVERDUE
  ├── READBACK_PENDING
  ├── VERIFICATION_FAILED
  └── CLOSED_VERIFIED

EXCEPTION_APPROVAL_PENDING
  ├── APPROVED_TIME_BOUND_EXCEPTION
  ├── DENIED
  └── ESCALATED_TO_RISK_OWNER
~~~

Các tên state không phải chuẩn của sản phẩm IGA nào. Điều quan trọng là **không mất lịch sử** khi item chuyển reviewer hoặc khi deadline được gia hạn. Một item có thể được gắn **cả decision overdue và high-risk flag**, và một item có thể cần reopen khi phát hiện quyền chưa thực sự biến mất.

## 11. Cách xử lý khi reviewer không phản hồi

Nếu item vẫn `PENDING_REVIEW` sau hạn:

1. **Xác minh tình trạng item:** Có thật đang chờ quyết định không, hay hệ thống chưa nhận callback?
2. **Kiểm trạng thái reviewer:** Vắng mặt, Mover, Leaver, thiếu quyền xem hoặc bị lỗi SSO?
3. **Xác minh dữ liệu đủ:** Reviewer có thấy permission semantics, scope, account mapping không?
4. **Nhắc có ngữ cảnh:** Nêu item/risk/deadline/next action.
5. **Reassign hợp lệ:** Cho delegate, manager hoặc resource owner phù hợp.
6. **Escalate theo risk:** Với quyền cao, security/risk owner cần xem xét hạn chế.
7. **Ghi decision và provenance:** Người thực hiện, thời gian, nguồn/bằng chứng.
8. **Đóng đúng chuẩn:** Decision completion không thay remediation verification.

**Không có phản hồi không phải là một quyết định KEEP.** Nếu tổ chức có chính sách tự động xử lý item quá hạn, nó phải được **định nghĩa minh bạch, kiểm thử theo entitlement/risk và lưu quyết định chính sách**, không giả mạo chữ ký của reviewer.

## 12. Auto-KEEP hay auto-REVOKE sau deadline?

Đây là quyết định thiết kế nhạy cảm.

### 12.1. Vì sao auto-KEEP nguy hiểm?

Nếu mọi item không được duyệt đúng hạn tự chuyển sang KEEP:

- Quyền cũ của Mover vẫn tồn tại.
- Contractor hết dự án có thể giữ quyền.
- Standing admin và direct grants không có owner bị “chứng nhận” mặc định.
- Báo cáo campaign trông hoàn tất dù **không có business validation**.

**Không nên dùng thiếu phản hồi như căn cứ cấp quyền.** Nếu chính sách doanh nghiệp có các trường hợp giữ tạm để tránh gián đoạn, hãy ghi **trạng thái tạm, căn cứ, mức rủi ro, owner, expiry và bù trừ**, không gọi đó là recertification đã được reviewer thực hiện.

### 12.2. Vì sao auto-REVOKE mù quáng cũng nguy hiểm?

Nếu tự gỡ mọi grant quá hạn:

- Service account thanh toán có thể ngừng hoạt động.
- Backup/DR workflow có thể bị vô hiệu.
- Nhân viên y tế/vận hành đang thực hiện nhiệm vụ hợp lệ có thể mất quyền.
- Một role được dùng chung bởi nhiều nguồn có thể bị sửa sai scope.

**Auto-revoke có thể phù hợp** với entitlement tạm đã có `expiresAt`, access không có căn cứ sau Leaver, hoặc policy rõ về quyền đặc biệt. Nhưng cần kiểm:

- Grant đã được phê duyệt có TTL/thời điểm kết thúc không?
- Biện pháp thu hồi có đúng subject/resource và không xóa grant khác hợp lệ không?
- Có bảo vệ dependency và bước triển khai an toàn cho workload không?
- Có rollback/tái cấp **qua quy trình mới** nếu phát hiện sai không?
- Có readback và alert khi target không thu hồi được không?

**Chọn theo risk-based policy, không theo mong muốn làm đẹp tỷ lệ hoàn thành chiến dịch.**

## 13. Phân biệt quá hạn quyết định với quá hạn remediation

Xét hai ví dụ:

**A. Decision overdue**

~~~text
User: P-301
Access: cloud.viewer@project-A
Reviewer: Project owner
Review due: 10/12 17:00
Đến 11/12: Chưa KEEP/REVOKE/MODIFY
Action: Escalate reviewer/delegate, xác minh nhiệm vụ.
~~~

**B. Remediation overdue**

~~~text
User: P-302
Access: cloud.admin@production
Decision: REVOKE (đã phê duyệt)
Remediation due: 10/12 18:00
Đến 11/12: IAM đã gỡ group nhưng target vẫn cho admin
Action: Escalate target/cloud owner + security,
        xử lý token/session/direct grant và readback.
~~~

Đối với B, gửi email cho reviewer để “duyệt lại” **không xử lý nguyên nhân chính**. Cần incident/remediation owner có khả năng chặn quyền ở target.

### 13.1. Ba mức “đã xong”

| Mức hoàn tất | Cần có | Chưa chứng minh |
|---|---|---|
| **Decision completed** | Reviewer hợp lệ chọn action có căn cứ | Target đã thay đổi |
| **Remediation applied** | Lệnh gỡ/sửa quyền được target xác nhận theo contract | Mọi đường truy cập đã đúng |
| **Verified closure** | Readback/kiểm quyền hiệu dụng đạt tiêu chí phạm vi | Không có bất kỳ đường chưa kiểm kê nào nếu inventory thiếu |

Dashboard không nên gom cả ba thành một con số `completed`.

## 14. Quyền đặc quyền quá hạn cần ưu tiên đặc biệt

**Privileged access** gồm cloud admin, IdP/directory admin, quản trị DB, secret access, quyền sửa CI/CD và những permission có khả năng mở quyền gián tiếp.

Một item quá hạn có thể liên quan:

- **PIM eligible role:** Có thể kích hoạt đặc quyền về sau dù chưa ACTIVE.
- **Active JIT grant:** Đang có quyền cao nhưng hết thời gian được duyệt.
- **PAM session:** Phiên đặc quyền vẫn mở sau khi grant bị gỡ.
- **Standing admin:** Không được review theo thời hạn.
- **Break-glass:** Cần xác nhận owner, khả dụng, hạn chế và hậu kiểm.
- **Privileged service principal:** Credential của workload có blast radius lớn.

### 14.1. Ví dụ PIM eligible sau Mover

Một nhân viên đã chuyển khỏi đội Cloud nhưng vẫn eligible cho `subscription-owner`. Campaign review đã quá hạn, reviewer cũ đã nghỉ. Không được mặc định rằng “chưa kích hoạt nên không nguy hiểm”: user có thể kích hoạt sau đó nếu hệ thống cho phép.

**Cần:** Reassign người review, kiểm HR Mover, xác minh eligibility hiện tại, áp policy hạn chế/rút quyền không còn căn cứ, kiểm khả năng kích hoạt và audit.

### 14.2. Không cho escalation bỏ qua SoD

Một reviewer cao hơn trong sơ đồ tổ chức không nhất thiết có quyền **duyệt đặc quyền của chính họ**. Khi escalation tới cấp quản lý hoặc risk owner, vẫn phải kiểm **tách nhiệm vụ, quyền duyệt và dữ liệu chứng cứ**.

## 15. Leaver: sự kiện bắt buộc không được chờ deadline campaign

Nếu HR/VMS báo người dùng hoặc engagement đã **ENDED** vào 09:00, quyền công việc không còn căn cứ theo policy phải được xử lý từ **mốc Leaver**, không đợi reviewer trả lời vào ngày cuối campaign.

### 15.1. Luồng ưu tiên

~~~mermaid
sequenceDiagram
    autonumber
    participant H as HR / VMS
    participant I as IAM / IGA
    participant C as Campaign / Escalation
    participant P as IdP / PIM / SCIM
    participant T as Target API / App
    participant A as Security / Audit

    H->>I: Leaver event + effectiveAt
    I->>C: Flag review item có Leaver risk
    C->>C: Không chờ reviewer thông thường
    I->>P: Disable/revoke account & role theo policy
    I->>T: Remove local ACL + token/session path
    P-->>I: Provisioning response
    T-->>I: Target response
    I->>A: Yêu cầu xác minh quyền thực tế
    A->>T: Readback + negative access check
    T-->>A: DENY hoặc còn residual access
    A-->>C: VERIFIED / ESCALATE_REMEDIATION
~~~

### 15.2. Quyền có thể tồn dư ở đâu?

- IdP disabled nhưng access token JWT còn hạn.
- Local account vẫn active ở ứng dụng không dùng SSO.
- Direct share hoặc ACL nằm ngoài SCIM.
- PIM eligible role chưa bị gỡ.
- PAM session hoặc SSH connection vẫn hoạt động.
- PAT/API key, database credential, certificate hoặc secret đã biết.
- Quyền kế thừa từ nhóm khác hoặc project membership chưa đồng bộ.

**Không báo Leaver hoàn tất chỉ vì item review đã được chọn REVOKE.** Phải có **kết quả thu hồi thực tế** theo phạm vi target bắt buộc; lỗi còn mở cần owner, biện pháp bù trừ và thời hạn xử lý.

## 16. Mover: reviewer có thể quá hạn vì thông tin tổ chức đã thay

**Mover** thay đổi phòng ban, dự án, địa điểm hoặc trách nhiệm, nhưng canonical identity có thể giữ nguyên. Đây là nguyên nhân phổ biến của quyền tồn dư.

Ví dụ:

~~~text
Trước Mover:
  subject=P-412, role=sales_manager@tenant-A

Sau Mover:
  subject=P-412, role=finance_reader@project-B

Campaign snapshot cũ:
  Reviewer=Sales Manager
  Entitlement=quote.approve@tenant-A

Vấn đề:
  Sales Manager cũ có thể không còn trách nhiệm;
  review item chưa được ai xử lý đúng hạn.
~~~

Cách xử lý:

1. Nhận event Mover từ nguồn có thẩm quyền.
2. Cập nhật **reviewer routing** theo cả owner tài nguyên và manager mới.
3. Xác định quyền Sales có còn căn cứ từ engagement khác không.
4. Nếu không còn, REVOKE; nếu có bàn giao được duyệt, tạo ngoại lệ time-bound.
5. Kiểm role mới, quyền cũ, direct ACL, group, token/cache.
6. Readback tại target và sửa nguồn gây cấp lại quyền.

**Không giữ quyền Sales vì reviewer cũ chưa phản hồi**, và cũng không xóa quyền hợp lệ của một engagement khác chỉ vì job title chính thay đổi.

## 17. Joiner và contractor: tránh “hợp thức hóa” quyền sai

**Joiner** có thể được cấp quyền theo **role catalog/birthright policy**; recertification giúp phát hiện cấp sai hoặc ngoại lệ, nhưng không nên dùng review tương lai làm thay kiểm soát ban đầu.

Khi quá hạn review quyền Joiner:

- Xác minh người mới đã identity proofing và có engagement đúng mốc.
- So sánh quyền baseline với role/job assignment được duyệt.
- Nếu target cấp quá scope, remediation theo policy thay vì chờ manager.
- Xác định reviewer đúng sau thay đổi tổ chức.
- Không “cấp như nhân viên cũ” để hoàn thành review nhanh.

Với **contractor/guest/federated identities**, cần kiểm:

- Sponsor/engagement còn hiệu lực?
- IdP issuer và subject mapping có đúng?
- Quyền thuộc tenant/dự án nào?
- Có ngày hết hạn hợp đồng sớm hơn review due date không?
- Guest account/SCIM account có tồn tại sau khi engagement kết thúc không?

**Khi contract hết hạn, thời điểm kết thúc engagement có thể là hạn chặn quyền quan trọng hơn deadline campaign.**

## 18. Escalation cho service account và workload identity

Một **service account** thường không có manager theo mô hình nhân sự. Workflow review phải định tuyến tới **technical owner, service owner, application owner hoặc nhóm chịu trách nhiệm deployment**, không tự gán ngẫu nhiên cho người tạo account.

### 18.1. Câu hỏi bắt buộc khi quá hạn

1. Workload/service còn hoạt động và có mục đích hợp lệ không?
2. Ai sở hữu tài sản kỹ thuật hiện tại?
3. Quyền đang xét là API scope, secret access, cloud role, database grant hay local account?
4. Credential nào đang sử dụng? Có rotation/expiry không?
5. Có liên quan production, thanh toán, backup hoặc quá trình khôi phục không?
6. Có quyền dư thừa hoặc account không còn dependency?
7. Người owner cũ đã Leaver thì ai nhận bàn giao?
8. Có thể tạm hạn chế network/role hoặc thay credential an toàn không?

### 18.2. Tránh hai cực đoan

**Không tự giữ mãi:** Workload không owner có `cloud.admin` không thể được đánh dấu KEEP chỉ vì có thể đang chạy.

**Không tự xóa ngay:** Nếu workload xử lý thanh toán production, revoke mù quáng có thể gây outage. Cần **triage, tìm owner, kiểm dependency, kiểm soát bù trừ và kế hoạch thu hồi/giảm quyền**, với escalation phù hợp mức rủi ro.

### 18.3. Owner Leaver không đồng nghĩa workload Leaver

Người triển khai service đã nghỉ nhưng workload vẫn hợp lệ thì cần **đổi ownership, xem lại secret từng được biết, rotate/revoke khi cần và đánh giá lại quyền**. Escalation nhắm vào việc **khôi phục trách nhiệm quản trị**, không tự suy ra xóa toàn bộ production identity.

## 19. Escalation khi dữ liệu và connector bị lỗi

Một campaign có thể quá hạn vì reviewer **không thể đưa quyết định có căn cứ**: connector chưa lấy được permission, nested group chưa phân giải, account mapping không chắc hoặc entitlement name không có mô tả.

| Lỗi | Không nên làm | Cách xử lý |
|---|---|---|
| Không đọc được local ACL | Coi user không có direct grant | Đánh dấu incomplete; giao app owner lấy dữ liệu |
| Không biết account thuộc ai | Gán ngẫu nhiên theo email | Correlation qua identity source, điều tra owner |
| Group `APP_GRP_07` khó hiểu | Yêu cầu manager bấm KEEP | Bổ sung entitlement dictionary, app owner review |
| SCIM connector timeout | Đóng REVOKE vì lệnh đã gửi | Retry an toàn, readback, mở remediation escalation |
| PDP/PEP lỗi | Cho PERMIT để khỏi gián đoạn | Fail-safe/degraded mode đã phê duyệt |
| HR/VMS chưa đồng bộ Mover | Giữ policy cũ vô hạn | Kiểm effectiveAt, nguồn chính thức và reconciliation |
| Session/token đã phát từ trước | Chỉ gỡ group IdP | Đánh giá token/phiên và quyền hiệu dụng ở RS |

**Thiếu dữ liệu không phải một quyết định KEEP.** Cần tách **data remediation SLA** khỏi **decision SLA**, nhưng không được dùng chờ sửa dữ liệu để trì hoãn một biện pháp thu hồi bắt buộc theo sự kiện Leaver/sự cố.

## 20. Escalation phối hợp với IdP, SSO, SCIM và RBAC/ABAC

Các lớp kỹ thuật thực hiện nhiệm vụ khác nhau:

| Thành phần | Vai trò trong overdue escalation | Giới hạn |
|---|---|---|
| **HR/VMS** | Trạng thái person/engagement, mốc JML | Không biết mọi local entitlement |
| **IAM/IGA** | Campaign, reviewer routing, policy, grant provenance, remediation | Không tự chứng minh target đã áp quyền |
| **IdP/SSO** | Authentication/session, group/claim | SSO login không chứng minh role ứng dụng đúng |
| **Directory** | Account và group/nested membership | Replica/cache có thể chậm cập nhật |
| **SCIM/API connector** | Provision/deprovision users/groups/roles khi hỗ trợ | Không tự thu hồi mọi ACL/token |
| **RBAC** | Role–permission assignment | Role name không đủ giải thích resource scope |
| **ABAC/PBAC** | Policy theo subject/resource/action/context | Cần attribute đúng và đủ mới |
| **PIM/PAM** | Eligibility, JIT activation, credential/session đặc quyền | Revoke eligible không tự chấm dứt mọi session |
| **Target/PEP/RS** | Quyết định hiệu dụng tại hành động/tài nguyên | Cần kiểm mọi đường truy cập |
| **Audit/monitoring** | Dấu vết escalation, quyết định và hiệu quả | Không thay kiểm soát phòng ngừa |

### 20.1. Khi đã có quyết định REVOKE

~~~text
Decision: REVOKE customer.export@tenant-A
  |
  +-> IGA cập nhật desired state
  +-> SCIM/API/gateway/target gỡ quyền
  +-> IdP/Directory gỡ nhóm nếu là nguồn grant
  +-> PAM/PIM xử lý privileged eligibility/grant nếu có
  +-> Token/session/ACL được đánh giá theo policy
  +-> Resource Server từ chối action ngoài căn cứ
  +-> Readback + audit kết luận VERIFIED hoặc FAILED
~~~

Nếu một bước không hoàn tất, **escalation phải hướng tới owner của bước đó**, không gửi lại cùng một yêu cầu cho người đã hoàn thành quyết định nghiệp vụ.

## 21. Thiết kế chính sách escalation có cấu trúc

Một policy cần trả lời:

- Item nào thuộc phạm vi?
- Deadline được xác định từ đâu?
- Khi nào gửi reminder và khi nào thực sự escalation?
- Risk tier/subject kind nào được ưu tiên?
- Tuyến reviewer/owner/delegate là ai?
- Ai có quyền gia hạn, ngoại lệ và quyết định hạn chế tạm?
- Tình huống nào bắt buộc gọi quy trình security incident hoặc Leaver?
- Khi nào escalation lên cấp mới?
- Khi nào item được tạm dừng hợp lệ và bằng chứng?
- Khi nào được đóng là **DECISION_COMPLETE** hay **VERIFIED_CLOSED**?

### 21.1. Mẫu YAML minh họa

~~~yaml
# Mẫu mô tả chính sách; KHÔNG phải schema chuẩn của một sản phẩm.
policyId: access-recert-overdue-v1
scope: corporate-access-recertification
timezone: Asia/Ho_Chi_Minh
timeBasis: business-days
defaultActionOnNoResponse: ESCALATE_NOT_AUTO_KEEP
decisionEscalation:
  - level: 0
    trigger: before-due
    offsetBusinessDays: -2
    notify: [reviewer]
  - level: 1
    trigger: after-due
    offsetBusinessDays: 1
    notify: [reviewer, reviewerManager, campaignOwner]
  - level: 2
    trigger: after-due
    offsetBusinessDays: 3
    notify: [resourceOwner, iamGovernance]
  - level: 3
    trigger: after-due
    offsetBusinessDays: 5
    notify: [securityRiskOwner]
riskOverrides:
  - condition: SUBJECT_ENGAGEMENT_ENDED
    action: INITIATE_LEAVER_CONTROL_IMMEDIATELY
  - condition: PRIVILEGED_HIGH_RISK
    action: EVALUATE_TEMPORARY_RESTRICTION_BY_POLICY
remediation:
  separateDeadline: true
  requiresTargetReadback: true
  onVerificationFailure: OPEN_REMEDIATION_ESCALATION
exception:
  ownerRequired: true
  expiryRequired: true
  compensationRequiredByRisk: true
audit:
  preserveOriginalDueAt: true
  preserveReassignmentHistory: true
  preserveDecisionAndVerification: true
~~~

**Chú ý:** Những mốc -2/+1/+3/+5 chỉ là dữ liệu giả lập phục vụ học tập. Cần chuyển thành policy thật theo giờ làm việc, lịch ngày nghỉ, mức rủi ro và yêu cầu vận hành của tổ chức.

## 22. Dữ liệu một item escalation: tách decision và remediation

Ví dụ JSON:

~~~json
{
  "campaignId": "RECERT-2026-Q4",
  "reviewItemId": "RI-904",
  "subject": {
    "kind": "HUMAN",
    "canonicalId": "P-2048",
    "engagementId": "ENG-712"
  },
  "entitlement": {
    "applicationId": "crm",
    "permission": "customer.export",
    "tenantId": "tenant-A",
    "grantSource": "direct-acl",
    "riskTier": "HIGH"
  },
  "review": {
    "assignedReviewer": "DATA_OWNER_A",
    "originalDueAt": "2026-12-10T17:00:00+07:00",
    "currentDueAt": "2026-12-10T17:00:00+07:00",
    "decision": null,
    "decisionAt": null,
    "status": "OVERDUE_L1"
  },
  "escalation": {
    "level": 1,
    "reason": "DECISION_OVERDUE",
    "assignedActionOwner": "IAM_CAMPAIGN_OWNER",
    "lastNotifiedAt": "2026-12-11T09:05:00+07:00",
    "nextActionAt": "2026-12-12T09:00:00+07:00"
  },
  "remediation": {
    "required": false,
    "status": "NOT_STARTED",
    "verifiedAt": null
  },
  "auditRef": "ESC-2026-4401"
}
~~~

**Dữ liệu chỉ minh họa.** Giá trị `decision=null` nghĩa là **chưa có quyết định**, không được diễn giải thành KEEP. `remediation.required=false` trong ví dụ phản ánh **chưa biết action**; khi reviewer chọn REVOKE/MODIFY cần tạo remediation item và timer riêng.

### 22.1. Thông tin cần bổ sung ở hệ thống thực

- Reviewer/owner routing version, delegation approval.
- SnapshotAt, data freshness và entitlement semantics.
- Policy version và source của risk tier.
- Lịch sử nhắc/escalation, phản hồi, reassignment và deadline extension.
- JML event/effectiveAt và identity state được kiểm chứng.
- SoD, security incident, exception reason và compensating controls.
- Target state, connector response, quyền hiệu dụng, evidence ref.
- Retention và quyền truy cập báo cáo theo chính sách.

**Không lưu password, API token, private key hoặc hồ sơ nhân sự đầy đủ trong item.**

## 23. Mã giả xử lý overdue escalation an toàn

Ví dụ Python sau thể hiện **cách suy nghĩ về trạng thái và rủi ro**, không tự thao tác IAM/SCIM/PAM thật.

~~~python
from datetime import datetime

FINAL_STATES = {
    "CLOSED_VERIFIED",
    "CANCELLED_WITH_AUDIT"
}

def evaluate_overdue(item, now: datetime, sources):
    """
    Pseudocode:
    - sources cung cấp identity, engagement, risk,
      reviewer routing và readback có thẩm quyền.
    - Mọi hành động chỉ tạo task, không tự cấp/thu hồi.
    """
    if item["status"] in FINAL_STATES:
        return {"action": "NONE", "reason": "ALREADY_FINAL"}

    subject = sources.current_subject(item["subjectId"])
    if subject is None:
        return {
            "action": "ESCALATE_SECURITY_AND_IDENTITY_OWNER",
            "reason": "UNKNOWN_SUBJECT"
        }

    if not subject.eligible_for(item["resourceId"]):
        return {
            "action": "INITIATE_JML_OR_SECURITY_REMEDIATION",
            "reason": "CURRENT_ELIGIBILITY_INVALID"
        }

    if item["decision"] in ("REVOKE", "MODIFY"):
        readback = sources.target_readback(item)

        if readback is not None and readback.matches_desired_state:
            return {"action": "CLOSE_VERIFIED"}

        if now > item["remediationDueAt"]:
            return {
                "action": "ESCALATE_REMEDIATION_OWNER",
                "reason": "REMEDIATION_OR_VERIFICATION_OVERDUE"
            }

        return {"action": "WAIT_AND_MONITOR_REMEDIATION"}

    if item["decision"] == "KEEP":
        # KEEP chỉ hợp lệ nếu người duyệt và trạng thái
        # được xác nhận theo policy hiện hành.
        if sources.keep_decision_is_valid(item, subject):
            return {"action": "CLOSE_REVIEW_DECISION"}
        return {
            "action": "REOPEN_REVIEW",
            "reason": "INVALID_OR_STALE_KEEP"
        }

    if now <= item["reviewDueAt"]:
        return {"action": "REMIND_IF_POLICY_REQUIRES"}

    reviewer = sources.resolve_authorized_reviewer(item)
    if reviewer is None:
        return {
            "action": "ESCALATE_OWNER_ASSIGNMENT",
            "reason": "NO_AUTHORIZED_REVIEWER"
        }

    risk = sources.current_risk(item)
    if risk.is_high_or_privileged:
        return {
            "action": "RISK_ESCALATION_AND_CONTROL_EVALUATION",
            "reviewer": reviewer.id
        }

    return {
        "action": "ESCALATE_REVIEWER_CHAIN",
        "reviewer": reviewer.id
    }


# Thiết kế production còn cần:
# timezone/business-calendar, idempotency, concurrency,
# retries, RBAC/SoD, signed evidence, audit và tests.
# Mọi auto-revoke/temporary deny phải được policy phê duyệt,
# không suy trực tiếp từ đoạn pseudocode này.
~~~

### 23.1. Hạn chế của mã minh họa

- Không xử lý calendar ngày nghỉ/timezone cụ thể.
- Không kết nối thực với HR/VMS, IdP, SCIM hoặc target.
- Không mô hình hóa mọi loại grant/source và phiên/token.
- Không kiểm race condition khi reviewer vừa quyết định cùng lúc scheduler chạy.
- Không thực thi điều kiện phê duyệt ngoại lệ hay giới hạn production.

**Đặc biệt:** Đoạn mã không dùng để “auto-REVOKE vì quá hạn”. Nó chỉ **chọn luồng xử lý**, còn thay đổi quyền phải qua chính sách và công cụ có thẩm quyền.

## 24. Timezone, lịch làm việc và tính đúng hạn

Thời gian là nguồn lỗi khó thấy khi nhiều nhóm ở các múi giờ khác nhau.

Giả sử:

~~~text
dueAt UTC:     2026-12-10T10:00:00Z
dueAt tại VN:  2026-12-10T17:00:00+07:00

Nếu chỉ so chuỗi ngày "2026-12-10":
  Có thể không biết item trễ từ 17:01.
~~~

Thiết kế phù hợp:

1. Lưu timestamp có **offset/UTC rõ ràng**, hiển thị theo múi giờ của reviewer.
2. Nếu dùng ngày làm việc, có **business calendar** được cấu hình và version.
3. So sánh thời điểm hiện tại với deadline theo **instant**, không chỉ chuỗi ngày.
4. Có độ trễ scheduler/idempotency để không bắn nhiều escalation trùng.
5. Truy vết thay đổi deadline; không ghi đè original due.
6. Nếu review đã hoàn tất ngay trước hạn nhưng event queue chậm, đối chiếu `decisionAt` đáng tin trước khi đánh dấu overdue.

**Không kéo dài mốc Leaver hoặc expiry của đặc quyền chỉ vì reviewer ở múi giờ khác hoặc nghỉ lễ.** Các hạn bảo mật theo chính sách có thể yêu cầu xử lý xuyên ngày nghỉ.

## 25. Chống race condition và thông báo lặp

Một hệ thống có thể gặp:

- Reviewer chọn REVOKE lúc 17:00:00.
- Scheduler đọc trạng thái cũ lúc 17:00:01.
- Escalation được gửi tới cấp trên dù quyết định đã tồn tại.
- Connector đang gỡ quyền nhưng một job khác ghi KEEP từ snapshot cũ.

Cần các cơ chế:

- **Optimistic concurrency/version** cho review item.
- **Idempotency key** cho notification, escalation và remediation.
- Kiểm lại trạng thái **ngay trước hành động nhạy cảm**.
- **Outbox/event processing** hoặc transactional boundary phù hợp.
- Ngăn một quyết định KEEP từ snapshot cũ **reprovision** quyền đã thu hồi do Leaver.
- Lưu event history và reason khi bỏ qua escalation đã lỗi thời.

**Trạng thái an toàn mới nhất phải thắng snapshot cũ**, đặc biệt với Leaver, security hold và policy deny bắt buộc.

## 26. Nội dung một thông báo escalation hữu ích

Thông báo phải **giúp người nhận hành động**, không chỉ gây áp lực.

### Nên có

- Campaign và review item/reference.
- Tài nguyên/ứng dụng, permission và **phạm vi đủ để hiểu**.
- Hạn gốc, số ngày/giờ trễ theo calendar đã chọn.
- Mức rủi ro và trạng thái hiện tại.
- Lý do chuyển cấp: reviewer không phản hồi, owner mất hiệu lực, connector fail...
- Người chịu trách nhiệm và **hành động tiếp theo**.
- Link nội bộ đến workflow có kiểm soát.
- Deadline kế tiếp và kênh hỗ trợ/escalation.
- Mã correlation và policy/version nếu cần cho audit.

### Không nên có

- Access token, password, key hoặc secret.
- Toàn bộ dữ liệu nhân sự/hợp đồng.
- Thông tin khách hàng nhạy cảm không cần để đưa quyết định.
- Link thực hiện “approve all” không có kiểm tra quyền.
- Câu khẳng định “quyền đã bị thu hồi” khi chưa có readback.

### 26.1. Hai tình huống phải có thông báo khác nhau

**Decision overdue:** “Cần xác nhận quyền này còn có căn cứ không; nếu thiếu hiểu biết về role, chọn chuyển app owner.”

**Remediation overdue:** “Đã có quyết định thu hồi nhưng target vẫn còn quyền; đội connector/ứng dụng cần can thiệp, security đang giám sát biện pháp bù trừ.”

Nếu cả hai dùng cùng một mẫu “Bạn chưa duyệt”, remediation sẽ không được xử lý đúng người.

## 27. Gia hạn deadline có kiểm soát

Gia hạn đôi khi hợp lý: reviewer bị thiếu dữ liệu target, owner đang thay đổi hoặc phụ thuộc business workflow chưa thể xác minh. Nhưng gia hạn có thể bị lạm dụng để che giấu quá hạn.

### Điều kiện tối thiểu

- **Lý do cụ thể** và bằng chứng thiếu dữ liệu/phụ thuộc.
- **Người có thẩm quyền** cho phép gia hạn.
- **Mốc hạn mới**, giới hạn số lần hoặc tổng thời gian theo policy.
- **Rủi ro và kiểm soát tạm thời** trong thời gian chờ.
- **Lịch sử bất biến**: original due, previous due, new due, approver, reason.
- **Trigger theo JML/incident** tiếp tục hoạt động dù deadline review đổi.
- Không chuyển trạng thái thành “đã recertified” do gia hạn.

### 27.1. Gia hạn không phải risk acceptance tự động

Ví dụ review quyền export customer data quá hạn do data owner đang nghỉ, manager xin thêm 14 ngày. Gia hạn **không tự chứng minh quyền export hợp lệ trong 14 ngày đó**. Cần chính sách rủi ro quyết định có **giới hạn tạm thời, chuyển reviewer hoặc chặn thao tác nhạy cảm** hay không.

## 28. Ngoại lệ có thời hạn và kiểm soát bù trừ

Khi chưa thể thu hồi ngay, có thể cần **exception management** do risk owner chấp thuận.

Ví dụ production service account còn quyền đọc secret rộng; muốn giảm quyền nhưng cần thay deployment trước.

Một ngoại lệ tối thiểu cần:

| Trường | Ví dụ |
|---|---|
| **Exception ID** | EX-PRIV-2026-41 |
| **Linked item** | RI-904 hoặc target remediation |
| **Rủi ro** | Quyền secret vượt nhu cầu, có blast radius |
| **Lý do chưa khắc phục** | Ứng dụng legacy cần thay config |
| **Owner/risk approver** | Service owner + security risk owner |
| **Biện pháp bù trừ** | Network restriction, monitoring, limited credential use |
| **Kế hoạch xử lý** | Migration managed identity và policy hẹp |
| **Expiry/review date** | Mốc đã phê duyệt |
| **Evidence** | Ticket change, test, readback khi đóng |

**Ngoại lệ không đồng nghĩa rủi ro được xóa.** Dashboard nên hiển thị hạng mục chưa giải quyết và thời hạn ngoại lệ, không đưa vào mục VERIFIED_CLOSED.

### 28.1. Khi ngoại lệ cũng quá hạn

Escalation mới cần được kích hoạt tới **risk owner và security**, kiểm lại tác động, biện pháp bù trừ và việc có cần chặn phần quyền rủi ro. Không gia hạn tự động không giới hạn.

## 29. Escalation và bảo vệ quyền riêng tư

Danh sách recertification thường tiết lộ ai có quyền ở hệ thống nào. Với quyền cao, bản thân metadata đã nhạy cảm.

Nên:

- Giới hạn người xem theo **reviewer assignment, resource ownership và need-to-know**.
- Hiển thị **mức đủ để đưa quyết định**, không gửi mọi account ra email.
- Dùng reference/link có kiểm soát thay vì đính kèm danh sách entitlement đầy đủ.
- Không đưa mật khẩu, SSH key, token, secret vào notification, ticket hoặc log.
- Bảo vệ access audit, retention, data minimization.
- Khi reassign, rà soát lại người được quyền xem item.
- Ghi cả **actor thực hiện decision** và reviewer được ủy quyền.
- Tránh đưa toàn bộ thông tin vào công cụ hỗ trợ không có thẩm quyền xử lý.

**Escalation không phải lý do nới rộng truy cập vào báo cáo IAM** cho mọi cấp quản lý không phụ trách tài nguyên.

## 30. Kiểm toán escalation: chứng minh ai đã làm gì

Một audit record đủ tốt có thể trả lời:

1. Quyền nào quá hạn, tại subject/account/target nào?
2. Deadline gốc và deadline sửa đổi là gì?
3. Vì sao bị coi là overdue và risk level nào áp dụng?
4. Có bao nhiêu reminder/escalation; gửi tới ai, lúc nào?
5. Reviewer/delegate nào thực sự ra quyết định và dựa vào dữ liệu nào?
6. Có escalation lên security/risk owner không và quyết định thế nào?
7. Nếu REVOKE/MODIFY, connector/target nhận lệnh gì?
8. Quyền hiệu dụng đã mất hoặc được giảm scope khi nào?
9. Ngoại lệ nào còn mở, owner và expiry là gì?
10. Có Mover/Leaver xảy ra trong thời gian review khiến quyết định cũ không còn hiệu lực không?

### 30.1. Ví dụ sự kiện audit

~~~json
{
  "eventType": "RECERT_ESCALATION",
  "eventId": "EVT-2026-4105",
  "time": "2026-12-11T09:05:00+07:00",
  "campaignId": "RECERT-2026-Q4",
  "reviewItemId": "RI-904",
  "subjectRef": "P-2048",
  "resourceRef": "crm/tenant-A",
  "entitlementRef": "customer.export",
  "overdueKind": "DECISION_OVERDUE",
  "originalDueAt": "2026-12-10T17:00:00+07:00",
  "escalationLevel": 1,
  "fromOwnerRole": "DATA_OWNER",
  "toOwnerRole": "IAM_CAMPAIGN_OWNER",
  "riskTier": "HIGH",
  "policyVersion": "access-recert-overdue-v1",
  "action": "ROUTE_FOR_DECISION",
  "decisionStatus": "PENDING",
  "remediationStatus": "NOT_STARTED",
  "effectiveAccessVerified": false,
  "correlationId": "IAM-ESC-904"
}
~~~

Đây là dữ liệu minh họa; không phải log của hệ thống thực. Trường `effectiveAccessVerified=false` không nói quyền **chắc chắn đang tồn tại** nếu readback chưa chạy; nó nói **chưa có bằng chứng xác minh**. Nên tách **unknown** khỏi **definitely still permitted** khi đánh giá rủi ro.

## 31. Đo lường hiệu quả escalation quá hạn

| Chỉ số | Định nghĩa gợi ý | Bẫy cần tránh |
|---|---|---|
| **Decision overdue rate** | Item chưa có decision hợp lệ sau hạn / item đến hạn | Không tính item giả/duplicate |
| **Risk-weighted overdue backlog** | Item quá hạn phân theo mức rủi ro | Không chỉ đếm số lượng thấp rủi ro |
| **Average overdue age** | Thời gian từ hạn gốc đến hiện tại/quyết định | Average che mất tail rất trễ |
| **P95 overdue age** | Phân vị 95 của thời gian trễ | Cần báo riêng rất cao rủi ro |
| **Escalation acknowledgment time** | Từ chuyển cấp đến khi owner xác nhận | Acknowledge không bằng remediation |
| **Reassignment completion** | Item thiếu reviewer được gán đúng | Reviewer mới phải có thẩm quyền |
| **Decision completion** | Item có decision hợp lệ | Không chứng minh target đã sửa |
| **Remediation overdue rate** | Item REVOKE/MODIFY chưa áp trước hạn | Tách loại error: connector/target/policy |
| **Verified closure rate** | Item đã có readback phù hợp | Không tính auto-close thiếu evidence |
| **Leaver residual access time** | Từ effectiveAt Leaver tới khi quyền trái policy được chặn | Không dùng campaign due date thay mốc |
| **Privileged overdue exposure** | Số/tuổi privileged rights chờ decision/remediation | Cần xét eligibility và session |
| **Extension frequency** | Số lần/giai đoạn gia hạn của item | Gia hạn để che nợ vẫn phải bị phát hiện |
| **Exception aging** | Ngoại lệ chưa được đóng và quá hạn | Không coi approved exception là fixed |
| **Repeat overdue by owner** | Tồn đọng lặp theo team/ứng dụng | Phân tích workflow, data quality thay vì chỉ đổ lỗi |
| **Notification noise** | Số thông báo trùng/không hành động | Thông báo nhiều chưa chắc nhanh hơn |
| **Coverage gap** | Ứng dụng/direct grants/workload chưa có review | Không công bố 100% nếu inventory thiếu |

### 31.1. Công thức kiểm tra một chỉ số

~~~text
DecisionOverdueRate =
  Count(items due, no valid decision after dueAt)
  / Count(items in review population whose dueAt has passed)

VerifiedRemediationRate =
  Count(REVOKE/MODIFY items with verified desired target state)
  / Count(REVOKE/MODIFY items requiring target change)
~~~

Cần xác định mẫu số: item đã hủy đúng quy trình, duplicate, thiếu dữ liệu hoặc out-of-scope có được tính không? **Không được xóa item khỏi mẫu chỉ để làm tỷ lệ tốt hơn**; phải lưu lý do loại trừ có audit.

### 31.2. Báo cáo theo tuổi và rủi ro

Một dashboard nên chia backlog như:

~~~text
                   0-1d     2-3d      4-7d      >7d
LOW                  45        22        10         4
MEDIUM               11         9         5         2
HIGH                  3         4         3         2
PRIVILEGED            1         1         1         0

Đây là số giả lập. Trọng tâm hành động:
  1 privileged item ở mức 4-7d có thể cấp bách
  hơn 45 low-risk items trễ một ngày.
~~~

Nếu biểu đồ chỉ xếp theo số lượng, đội vận hành dễ ưu tiên “làm đẹp” nhiều item ít rủi ro thay vì xử lý đặc quyền tồn dư.

## 32. Runbook cho decision overdue

Một runbook ngắn:

1. **Đọc item và deadline** từ nguồn IGA; xác nhận snapshot, policy và risk.
2. **Kiểm JML/incident**: Nếu Leaver, compromise hoặc quyền đặc quyền hết hạn, chuyển tuyến xử lý cấp bách.
3. **Kiểm reviewer assignment**: Còn nhiệm vụ và thẩm quyền không?
4. **Xác nhận dữ liệu**: Role, scope, grant provenance và owner có đủ để quyết định?
5. **Thông báo đúng tuyến**: Nhắc, reassign hoặc escalation theo policy.
6. **Ghi trạng thái**: Escalation level, reason, action owner, next action deadline.
7. **Theo dõi**: Có decision hợp lệ, có phải review lại vì dữ liệu thay đổi không?
8. **Kết thúc phần decision**: Chỉ khi KEEP/REVOKE/MODIFY có căn cứ; nếu cần remediation, mở bước tiếp theo.
9. **Đối soát**: Tránh stale decision phục hồi quyền bị thu hồi theo Leaver.

### 32.1. Nếu reviewer trả lời “không biết quyền này là gì”

Chuyển item tới app/data owner hoặc bổ sung catalog entitlement; **không yêu cầu reviewer bấm KEEP để hết hạn**. Đối với quyền cao chưa xác minh, risk owner cần quyết định biện pháp tạm thời.

## 33. Runbook cho remediation overdue

Nếu đã có quyết định REVOKE/MODIFY:

1. Xác minh **decision, scope và target account mapping** chính xác.
2. Kiểm lệnh đã gửi, request ID, retry và phản hồi của connector/target.
3. Đọc quyền thực tế: role, group, direct ACL, inherited permission và target account.
4. Nếu quyền vẫn còn, xác định nguồn: role khác, cache, local account, token, session, credential.
5. Escalate tới **application/platform owner có quyền sửa**, security nếu rủi ro cao.
6. Cân nhắc **compensating control**: chặn ở gateway/PEP, network restriction, session termination, risk hold theo policy.
7. Thực thi thay đổi đúng scope, có idempotency và tránh gỡ grant khác hợp lệ.
8. Readback/negative test, xác minh target đã đạt desired state.
9. Lưu bằng chứng, close remediation; nếu chưa đạt, giữ **EXCEPTION_OPEN** với owner và hạn xử lý.
10. Kiểm nguồn cấp để quyền không **tái xuất hiện** do sync từ directory/IdP hoặc automation.

**Không gửi lại request cho business reviewer chỉ vì connector fail.** Cần owner có quyền can thiệp kỹ thuật, giữ nguyên audit của decision đã được phê duyệt.

## 34. Tình huống A: manager nghỉ phép, campaign chậm

**Bối cảnh:** Một manager phải chứng nhận 250 quyền dự án. Đến deadline, còn 60 item chưa xử lý; manager nghỉ phép và không có delegate đăng ký. Phần lớn là quyền đọc thấp rủi ro, nhưng trong 60 item có hai quyền `customer.export`.

**Cách phân tích:**

- Không tự auto-KEEP toàn bộ 60 quyền.
- Chuyển hai quyền export cho data owner/security theo risk, cân nhắc hạn chế tạm nếu cần.
- Manager hierarchy hoặc campaign owner xác nhận delegate có thẩm quyền review các quyền còn lại.
- Bổ sung context/entitlement explanation để người review mới không bị buộc đoán.
- Lưu original due và lịch sử reassign, không reset deadline để hết quá hạn trên dashboard.
- Theo dõi decision + remediation riêng.

**Bài học:** **Escalation thay đổi người chịu trách nhiệm, không thay thế quyết định có căn cứ.**

## 35. Tình huống B: reviewer đã chọn REVOKE nhưng SCIM timeout

**Bối cảnh:** Reviewer xác nhận contractor không còn cần tài khoản CRM. IAM gửi SCIM PATCH để gỡ nhóm. Connector báo timeout, campaign tự hiển thị “decision complete”. Contractor vẫn có local ACL và API chấp nhận access token cũ.

**Cách xử lý:**

1. Giữ decision REVOKE là hợp lệ nhưng **remediation chưa verified**.
2. Xác định kết quả thực tế của PATCH, tránh retry gây thay đổi nhầm resource.
3. Kiểm local ACL và application role không qua SCIM.
4. Escalate application owner + connector owner; security tham gia theo mức rủi ro.
5. Nếu engagement đã ENDED, chặn quyền theo luồng Leaver, không chờ campaign.
6. Xử lý token/session và readback API sau thay đổi.
7. Chỉ đóng khi kết quả thu hồi đạt policy hoặc ngoại lệ được ghi nhận và xử lý theo quy định.

**Bài học:** **Quá hạn remediation là một loại sự cố riêng**, không được che bằng tỷ lệ review decision cao.

## 36. Tình huống C: PIM eligible admin sau Mover

**Bối cảnh:** Kỹ sư Linh chuyển khỏi Cloud Operations nhưng còn `PIM eligible: subscription-owner`. Reviewer Cloud Manager đã Mover nên không trả lời; item quá hạn ba ngày. Linh chưa sử dụng role trong nhiều tháng.

**Rủi ro:** Dù không active, Linh có thể **kích hoạt đặc quyền** nếu điều kiện khác cho phép.

**Cách xử lý:**

- Kiểm Mover event và role eligibility hiện tại.
- Phân loại quyền privileged risk thay vì coi unused là low risk.
- Reassign đúng cloud/security owner, kiểm SoD.
- Theo policy, tạm hạn chế/rút eligibility không còn căn cứ.
- Xác minh không còn khả năng kích hoạt lại quyền, kiểm các active sessions/grants.
- Lưu decision và verified readback.

**Bài học:** **Rủi ro không chỉ là quyền đang dùng mà còn là quyền có thể kích hoạt trong tương lai.**

## 37. Tình huống D: service account production không có owner

**Bối cảnh:** `svc-invoice-batch` có quyền đọc secret ở production. Chủ sở hữu cũ đã Leaver, application catalog chưa cập nhật. Reviewer assignment thất bại và item quá hạn. Job vẫn chạy hàng đêm.

**Cách xử lý:**

1. Tìm service/workload qua deployment metadata, scheduler, logs và CMDB.
2. Chỉ định owner mới có thẩm quyền, không ngẫu nhiên gán cho người tạo account.
3. Phân tích blast radius của secret access; hạn chế và bảo vệ khi chờ.
4. Xây kế hoạch credential rotation/scope reduction phù hợp dependency.
5. Nếu workload đã ngừng, deprovision an toàn; nếu còn, chứng nhận quyền cần thiết với owner mới.
6. Readback job và quyền, ghi ngoại lệ/risk trong thời gian chưa xử lý.

**Bài học:** **Escalation với non-human identity cần governance và vận hành**, không chỉ email manager của người đã nghỉ.

## 38. Tình huống E: quá hạn và yêu cầu gia hạn giả tạo

**Bối cảnh:** Reviewer liên tục yêu cầu đổi `dueAt` sang cuối tháng vì “chưa có thời gian”. Hệ thống cho phép đổi hạn không lưu lý do; dashboard luôn báo 0 item overdue. Một quyền `billing.admin` tồn tại cả quý mà không có quyết định.

**Cách xử lý:**

- Bảo vệ `originalDueAt` và mọi lịch sử extension.
- Cần approval/owner để gia hạn theo policy.
- Risk-based escalation khi vượt ngưỡng tổng thời gian hoặc số lần.
- Quyền admin phải được đánh giá ngay, không dùng gia hạn review để kéo dài quyền đặc biệt.
- Đo **age since original due**, không chỉ age từ deadline mới.
- Audit dữ liệu đã sửa và cải tiến kiểm soát workflow.

**Bài học:** **Gia hạn deadline không được biến một khoản nợ bảo mật thành “đúng hạn” trên giấy.**

## 39. Tình huống F: một user có hai engagement

**Bối cảnh:** Contractor Hưng có dự án A và B. A kết thúc; quyền repo A quá hạn review. User vẫn đăng nhập SSO vì engagement B active. Reviewer của A không phản hồi, và hệ thống định disable toàn bộ account để “giải quyết quá hạn”.

**Vấn đề:** Có thể làm gián đoạn engagement B hợp lệ; ngược lại, giữ account active không phải lý do giữ quyền A.

**Cách xử lý:**

1. Xác minh từng engagement và grant provenance.
2. Thu hồi `repo.write@A`, các token/ACL liên quan đến A theo policy.
3. Giữ `repo.read@B` nếu B còn căn cứ và scope đúng.
4. Chuyển review quyền A tới app/data owner của A.
5. Readback API A từ chối thao tác, B vẫn hoạt động hợp lệ.
6. Lưu bằng chứng tách phạm vi và nguyên nhân escalation.

**Bài học:** Escalation cần nhắm **entitlement đúng nguồn**, không xử lý account theo kiểu tất cả hoặc không gì.

## 40. Tình huống G: quyền đã gỡ nhưng tái xuất hiện sau đồng bộ

**Bối cảnh:** Reviewer chọn REVOKE nhóm `finance-exporter`. IAM gỡ ở target, readback PASS. Sau một đêm, đồng bộ từ một nhóm directory cũ cấp lại role vì rule provisioning chưa sửa.

**Phân tích:** Readback tại một thời điểm chưa đủ nếu **nguồn cấp quyền vẫn tiếp tục sinh grant**.

**Cách xử lý:**

- Truy grant provenance, role mapping và source-of-truth.
- Sửa rule/assignment sai hoặc gỡ group ở nguồn có thẩm quyền.
- Bổ sung reconciliation theo thời gian để phát hiện regrant.
- Đảm bảo không phục hồi quyền đã bị thu hồi bởi event Mover/Leaver.
- Gắn incident/problem record với item review và owner xử lý.
- Xác minh lại target trong cửa sổ phù hợp rủi ro.

**Bài học:** **Escalation nên xử lý nguyên nhân quyền tồn dư**, không chỉ đóng một lần sau PATCH thành công.

## 41. Tình huống H: hết hạn review nhưng phát hiện truy cập bất thường

**Bối cảnh:** Một quyền `data.export@all-tenants` đang overdue review. Monitoring báo subject thực hiện export bất thường ngoài giờ; risk owner nhận escalation.

**Hành động:**

- Không chờ quyết định campaign định kỳ nếu có tín hiệu compromise.
- Chuyển sang **security incident response** theo quy trình tổ chức.
- Xác minh danh tính, token/session và phạm vi ảnh hưởng.
- Có thể chặn tạm truy cập hoặc thu hồi quyền/credential theo policy.
- Bảo toàn log và bằng chứng, tránh làm mất thông tin điều tra.
- Tiếp tục review/remediation sau khi tình trạng an toàn được xác lập.

**Bài học:** Escalation là cơ chế **phát hiện và chuyển trách nhiệm**, không phải trần giới hạn của xử lý sự cố bảo mật.

## 42. Kiểm thử workflow escalation

Trước khi triển khai, cần test cả tình huống bình thường lẫn edge cases:

| Test case | Kỳ vọng |
|---|---|
| Reviewer hoàn tất trước dueAt | Không gửi overdue escalation |
| Reviewer quyết định sát hạn, event đến chậm | Scheduler đối chiếu decisionAt, tránh escalation sai |
| Item quá hạn, reviewer vẫn active | Nhắc/chuyển cấp theo policy |
| Reviewer đã Leaver | Reassign đúng thẩm quyền, ghi audit |
| Reviewer tự duyệt đặc quyền của mình | Chặn/đưa tới reviewer độc lập nếu policy quy định |
| Chưa có owner của resource | Escalate ownership, không auto-KEEP |
| Privileged entitlement quá hạn | Risk path, đánh giá hạn chế thích hợp |
| Contractor đã ENDED trước due | JML revoke ưu tiên, không chờ review |
| Service account production thiếu owner | Tìm dependency, risk owner, tránh revoke mù |
| SCIM trả 200 nhưng local ACL còn | Remediation chưa verified |
| Grant gỡ nhưng token cũ còn dùng được | Đánh giá session/token và quyền hiệu dụng |
| Một user có hai engagement | Thu hồi đúng grant hết căn cứ, giữ phần hợp lệ |
| Hai scheduler chạy đồng thời | Một escalation logic duy nhất với idempotency |
| Deadline gia hạn | Lưu originalDueAt và approval, không mất history |
| Policy exception hết hạn | Mở escalation mới, không auto-renew |
| Campaign snapshot cũ chọn KEEP sau Leaver | Chặn/reopen, không tái cấp quyền |
| Timezone UTC và Asia/Ho_Chi_Minh | So sánh đúng thời điểm thực |
| Một target offline trong lúc readback | Giữ PENDING/UNKNOWN và owner, không đóng giả |

**Kiểm thử phải xét trạng thái quyền tại API/target**, không chỉ thông báo có hiển thị đúng hay không.

## 43. Câu hỏi tự kiểm tra

**Câu 1.** Một item chưa có reviewer decision sau `dueAt`. Đây là loại quá hạn nào?

**Gợi ý:** **Decision overdue**, cần xác minh reviewer/owner và escalation theo rủi ro.

**Câu 2.** Reviewer đã chọn REVOKE, nhưng target vẫn cho truy cập. Có thể đóng campaign item không?

**Gợi ý:** Không nếu mục tiêu yêu cầu mất quyền. Đây là **remediation/verification overdue**, cần xử lý tại target và readback.

**Câu 3.** Không ai trả lời nên hệ thống tự chọn KEEP. Vì sao nguy hiểm?

**Gợi ý:** Thiếu phản hồi không chứng minh business necessity, dễ duy trì quyền sau Mover/Leaver hoặc quyền đặc biệt sai.

**Câu 4.** Có nên auto-revoke mọi service account quá hạn review?

**Gợi ý:** Không mù quáng. Cần đánh giá workload, dependency, owner, rủi ro, biện pháp bù trừ và chính sách.

**Câu 5.** Nhân viên đã Leaver nhưng review due sau 10 ngày. Có thể đợi hết hạn campaign?

**Gợi ý:** Không. Leaver event và mốc thu hồi theo policy có ưu tiên riêng.

**Câu 6.** Reviewer cũ cũng đã nghỉ việc. Escalation lên ai?

**Gợi ý:** Reviewer delegate có thẩm quyền, resource/application owner hoặc tuyến quản trị IAM phù hợp; kiểm SoD, không gán ngẫu nhiên.

**Câu 7.** Một user Mover vẫn có PIM eligible role. Dù chưa kích hoạt lần nào, có cần review khẩn không?

**Gợi ý:** Có thể cần, vì khả năng kích hoạt đặc quyền vẫn tồn tại và có thể không còn căn cứ.

**Câu 8.** Quyền gỡ khỏi IdP nhưng JWT cũ còn được API chấp nhận. Escalation thuộc loại gì?

**Gợi ý:** Remediation/verification chưa hoàn tất theo yêu cầu policy; phải kiểm token/session và Resource Server.

**Câu 9.** Gia hạn deadline có làm mất trạng thái overdue trong lịch sử không?

**Gợi ý:** Không. Giữ originalDueAt, reason, approver, thời gian và số lần gia hạn để kiểm toán.

**Câu 10.** Vì sao cần phân biệt reviewer escalation và technical owner escalation?

**Gợi ý:** Reviewer ra quyết định; technical owner sửa target/connector. Đã REVOKE rồi thì email reviewer không sửa lỗi SCIM.

**Câu 11.** Tại sao item vừa được readback PASS vẫn có thể cần reconciliation sau đó?

**Gợi ý:** Directory group/rule provisioning hoặc automation có thể tái cấp quyền.

**Câu 12.** Những quyền export high risk và wiki read low risk cùng quá hạn hai ngày; có xử lý cùng thứ tự không?

**Gợi ý:** Phân tầng risk và tác động; quyền export có thể cần ưu tiên cao hơn.

**Câu 13.** Tại sao missing connector data không được đánh dấu “no access”?

**Gợi ý:** Unknown ≠ absent; cần sửa nguồn và không tạo chứng nhận giả.

**Câu 14.** Một contractor hết A nhưng còn B, escalation có nên disable toàn bộ account để hết overdue?

**Gợi ý:** Không tự động. Thu hồi quyền A, giữ B nếu còn căn cứ, readback đúng scope.

## 44. Checklist triển khai Escalation quá hạn

- [ ] **Định nghĩa:** Phân biệt review overdue, remediation overdue, verification overdue và exception overdue?
- [ ] **Deadline:** Có originalDueAt, currentDueAt, timezone, calendar và nguồn chính sách?
- [ ] **Risk:** Ưu tiên theo permission, subject, resource, tenant, environment, SoD và JML?
- [ ] **Nhắc vs chuyển cấp:** Định nghĩa ngưỡng reminder và escalation khác nhau?
- [ ] **Owner:** Mọi item có reviewer và target owner còn thẩm quyền?
- [ ] **Delegation:** Reassignment có approval/scope và không vi phạm SoD?
- [ ] **Thông tin:** Reviewer thấy permission semantics, grant provenance, resource và risk?
- [ ] **Không auto-KEEP:** Thiếu phản hồi không được giả là business certification?
- [ ] **Auto-revoke:** Nếu áp dụng, có căn cứ policy, scope, kiểm dependency và xác minh target?
- [ ] **Privileged:** Standing admin, PIM eligible, active JIT, PAM sessions được triage riêng?
- [ ] **Joiner:** Role baseline sai không chờ recertification để sửa?
- [ ] **Mover:** Quyền cũ và reviewer cũ được rà soát; token/cache được đánh giá?
- [ ] **Leaver:** Revocation theo event không bị campaign deadline làm chậm?
- [ ] **External:** Guest/contractor có sponsor, tenant và engagement hiệu lực?
- [ ] **Workload:** Service account có service owner, credential và dependency được kiểm?
- [ ] **IdP/SSO:** Authentication không bị nhầm với quyền effective tại ứng dụng?
- [ ] **SCIM:** Provisioning response không bị nhầm với complete revoke?
- [ ] **RBAC/ABAC:** Role và resource scope được kiểm tại PEP/RS?
- [ ] **Data quality:** Unknown/missing data được xử lý bằng tuyến escalation riêng?
- [ ] **JML precedence:** Stale KEEP không khôi phục quyền sau Leaver/security revoke?
- [ ] **Extension:** Gia hạn có risk owner, reason, mốc mới và lịch sử bất biến?
- [ ] **Exception:** Có owner, expiry, bù trừ và escalation khi quá hạn?
- [ ] **Remediation:** Có task/change ID, retry an toàn, partial failure handling?
- [ ] **Readback:** Kiểm role, group, direct ACL, credential, session/token theo phạm vi?
- [ ] **Regrant:** Theo dõi quyền đã revoke có tái xuất hiện từ source khác?
- [ ] **Audit:** Có item, deadlines, policy, actor/reviewer, escalation level và quyết định?
- [ ] **Privacy:** Thông báo không chứa bí mật và chỉ gửi người có need-to-know?
- [ ] **Metrics:** Tách decision completion, remediation completion, verified closure và tuổi backlog?
- [ ] **Test:** Có unit/integration test cho timezone, concurrency, JML, SoD và target fail?
- [ ] **Đóng item:** Chỉ kết luận VERIFIED khi đủ bằng chứng theo chính sách?

## 45. Kết luận

**Escalation quá hạn trong Access Recertification là cơ chế xử lý những quyền đang chờ xác nhận hoặc chờ khắc phục vượt thời hạn**, bằng cách phân loại rủi ro, chuyển đúng người chịu trách nhiệm, đặt hành động và kiểm chứng kết quả. Nó không phải “gửi thêm email nhắc” và càng không phải thủ thuật làm đẹp báo cáo bằng cách **auto-KEEP hoặc tự xóa hàng loạt**.

Trong thực hành, phải **tách hạn ra quyết định của reviewer khỏi hạn remediation và verified closure**, giữ lịch sử deadline, chống quyết định từ snapshot cũ và có tuyến ưu tiên cho **privileged access, Mover, Leaver, contractor và non-human identities**. **IAM/IGA** điều phối workflow; **HR/VMS** cung cấp trạng thái danh tính; **IdP/SSO, SCIM, PAM/PIM** phối hợp thay đổi quyền; **RBAC/ABAC/PEP/Resource Server** kiểm hành động thực tế; **audit và readback** chứng minh trạng thái cuối.

**Một escalation được giải quyết đúng không chỉ là “đã có người trả lời”, mà là “quyền được quyết định hợp lệ, hành động cần thiết đã được thực thi và quyền hiệu dụng đã được xác minh trong phạm vi bắt buộc”**. Đó là cách Access Recertification góp phần **cấp đúng quyền, xử lý trách nhiệm quá hạn và giảm quyền truy cập tồn dư trong vòng đời Joiner–Mover–Leaver**.
