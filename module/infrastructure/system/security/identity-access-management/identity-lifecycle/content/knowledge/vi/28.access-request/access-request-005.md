# Lý do yêu cầu trong Access Request: chứng minh nhu cầu truy cập, giới hạn quyền và tạo bằng chứng kiểm toán

**Lý do yêu cầu (access request justification, business justification)** là phần giải thích **vì sao một chủ thể cần một quyền truy cập cụ thể** để thực hiện **nhiệm vụ hợp lệ**, tại **tài nguyên và phạm vi xác định**, trong **khoảng thời gian thích hợp**. Đây là đầu vào giúp người phê duyệt, hệ thống Identity Governance and Administration (IGA) và các cơ chế kiểm soát truy cập quyết định **có cơ sở để cấp quyền hay không**.

Lý do yêu cầu không phải một câu văn mang tính hình thức để “điền cho đủ ô”. Nó phải giúp người đọc trả lời: **Ai cần quyền gì? Để làm việc nào? Trên dữ liệu/hệ thống nào? Vì sao quyền sẵn có chưa đủ? Cần trong bao lâu? Ai xác nhận nhu cầu và bằng chứng nào hỗ trợ?**

Trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, chủ đề này nằm ở chương **Access request**, liên quan đến **quản lý vòng đời danh tính IAM theo Joiner–Mover–Leaver (JML)**: xác minh danh tính, tạo tài khoản và cấp quyền khi gia nhập; tính lại quyền khi đổi nhiệm vụ; rà soát và thu hồi khi quan hệ làm việc kết thúc. Một lời giải thích có chất lượng giúp **IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, PAM/PIM, kiểm toán** phối hợp cấp **đúng quyền**, đồng thời ngăn các yêu cầu thiếu căn cứ trở thành **quyền truy cập tồn dư**.

**Nguyên tắc quan trọng:** **“Có lý do” không đồng nghĩa “được phép”.** Một request có lý do rõ ràng vẫn phải qua kiểm tra **identity, eligibility, least privilege, chính sách dữ liệu, Separation of Duties (SoD), mức rủi ro, phê duyệt và khả năng thu hồi**. Ngược lại, một yêu cầu từ chối không phải vì người gửi không biết viết hay, mà vì **thiếu căn cứ có thể kiểm chứng hoặc vượt quyền chính sách**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa **lý do yêu cầu** và phân biệt nó với **mô tả quyền, nhiệm vụ được giao, bằng chứng, chấp thuận, phê duyệt và quyết định cấp quyền**.
2. Viết justification đủ thông tin cho yêu cầu **Joiner, Mover, dự án, truy cập tạm thời, quyền đặc quyền và workload/service account**.
3. Sử dụng mô hình **nhiệm vụ – hành động – tài nguyên – phạm vi – thời hạn – căn cứ xác nhận – tiêu chí hoàn tất**.
4. Nhận diện lý do không đạt như **“cần gấp”, “giống đồng nghiệp”, “manager bảo”, “để tiện”, “toàn quyền cho chắc”**.
5. Đánh giá tính hợp lệ của dữ liệu: **nguồn có thẩm quyền**, trạng thái engagement, owner dự án, risk tier, lịch sử approval và bằng chứng.
6. Thiết kế workflow **request → validation → review → approve/deny → provisioning → readback → expiry/revoke**.
7. Liên kết justification với **RBAC/ABAC, scope tenant/project, SoD, JIT/PAM, SCIM và session/token lifecycle**.
8. Thiết kế ghi nhận và chỉ số kiểm toán mà không thu thập quá nhiều **dữ liệu cá nhân hoặc bí mật**.
9. Xử lý ngoại lệ, khẩn cấp và Mover/Leaver sao cho **lý do hết hiệu lực thì quyền cũng được rà soát hoặc thu hồi**.

## 2. Lý do yêu cầu thực chất là gì?

**Access request** là một **đề nghị** được cấp hoặc thay đổi quyền. **Lý do yêu cầu** mô tả **mục đích nghiệp vụ** của đề nghị đó, giúp các bên đánh giá mức cần thiết và tính hợp lệ.

Ví dụ:

> “Tôi cần quyền đọc báo cáo ngân sách dự án A trong kỳ đối soát tháng 12 để kiểm tra chênh lệch theo nhiệm vụ tài chính đã được giao; chỉ cần xem, không cần xuất dữ liệu hoặc chỉnh sửa. Quyền cần từ 02/12 đến 06/12. Đầu việc tham chiếu: FIN-218; owner dự án xác nhận phạm vi báo cáo.”

Đoạn này có thể kiểm tra được: nhiệm vụ, dữ liệu, hành động, thời hạn, giới hạn và nơi tìm bằng chứng. Nhưng nó **chưa tự chứng minh** người gửi thật sự được giao FIN-218 hay owner đã đồng ý: hệ thống/người duyệt phải **đối chiếu nguồn đáng tin**.

### 2.1. Những khái niệm cần phân biệt

| Khái niệm | Trả lời câu hỏi | Có thể thay thế justification không? |
|---|---|---|
| **Business justification** | Vì sao quyền này cần cho công việc? | Là nội dung chính cần thẩm định |
| **Permission/role description** | Quyền này cho phép làm gì? | Không: mô tả tính năng chứ không nói ai cần |
| **Requested scope** | Đến tài nguyên, tenant, môi trường nào? | Không: scope là giới hạn cần gắn với lý do |
| **Request evidence** | Có nguồn nào chứng minh công việc được giao? | Không: cần nối bằng chứng với lý do và quyền |
| **Manager endorsement** | Quản lý có xác nhận nhu cầu không? | Không: quản lý có thể không là data owner |
| **Approval decision** | Bên có thẩm quyền đồng ý cấp không? | Không: quyết định đến sau validation |
| **Eligibility** | Chủ thể có đủ điều kiện nhận quyền không? | Không: account active chưa đủ lý do nghiệp vụ |
| **Provisioning result** | Quyền đã được áp ở ứng dụng chưa? | Không: request được duyệt chưa chắc đã cấp thành công |
| **Access certification** | Quyền đang có còn hợp lệ không? | Cần justification gốc và căn cứ hiện hành |

**Không nhầm sự rõ ràng của văn bản với xác thực sự thật.** Một lý do có cấu trúc rất tốt nhưng dẫn đến ticket giả hoặc resource không thuộc dự án vẫn có thể phải bị từ chối.

## 3. Vì sao IAM cần lý do yêu cầu có thể kiểm chứng?

Một hệ thống cấp quyền theo ticket nhưng không hỏi “vì sao” dễ gặp **privilege creep**: quyền được cộng dồn, thiếu ngày hết hạn và không ai biết nguồn căn cứ.

Lý do yêu cầu có ích ở ba thời điểm:

**Trước cấp quyền:** Xác định task thật, scope tối thiểu, chủ thể đủ điều kiện và người phê duyệt có thẩm quyền. Đánh giá có cần tạo account mới hay quyền hiện tại đã đủ.

**Trong thời gian sử dụng:** Liên kết grant với công việc, dự án, hợp đồng hoặc change đã được duyệt. Khi nhiệm vụ kết thúc sớm, có thể rà soát hoặc thu hồi dựa trên **căn cứ không còn tồn tại**.

**Sau khi sử dụng:** Trong access review, audit hoặc điều tra, truy vết **vì sao quyền tồn tại** và liệu nó còn hợp lệ tại thời điểm Mover/Leaver hay không.

### 3.1. Justification bảo vệ cả người yêu cầu lẫn tổ chức

- Người yêu cầu không phải suy đoán nên xin “admin” hay “read-only”; hệ thống có thể gợi ý quyền tương ứng nhiệm vụ.
- Người phê duyệt không phải đồng ý dựa trên cảm tính hoặc quan hệ cá nhân.
- Application owner thấy được **tài nguyên, mức nhạy cảm và tác động** của grant.
- IAM/IGA biết mốc hết hạn, owner và nguồn quyết định để tự động rà soát.
- Security/Audit biết ai phê duyệt, tại sao và trạng thái quyền thực tế.

**Không nên dùng justification như công cụ đánh giá văn phong của nhân viên.** Cần chấm **tính đầy đủ, liên quan và khả năng xác minh**, không phải độ dài hay mức độ “thuyết phục”.

## 4. Khung bảy yếu tố của một justification tốt

Một mô hình thực hành dễ dùng là:

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| **1. Business objective** | Mục tiêu nghiệp vụ cụ thể là gì? | Đối soát hóa đơn dự án A cho kỳ tháng 12 |
| **2. Assigned task** | Người này được giao việc nào? | FIN-218, nhiệm vụ reviewer |
| **3. Necessary action** | Cần làm thao tác nào? | `invoice.read`; không cần `invoice.export` |
| **4. Resource boundary** | Với đối tượng/tenant/environment nào? | Hóa đơn thuộc project-A, tenant-vn, production |
| **5. Time boundary** | Bắt đầu/kết thúc khi nào? | Từ 02/12 đến 06/12 hoặc khi nhiệm vụ đóng |
| **6. Evidence/owner** | Ai xác nhận và ở nguồn nào? | Project owner + ticket FIN-218 |
| **7. Success/revocation condition** | Khi nào hết nhu cầu? | Đối soát được phê duyệt và gửi báo cáo |

Mỗi trường có thể do **form**, **role catalog** hoặc **nguồn có thẩm quyền** điền một phần. Không cần ép người dùng viết tất cả thành một đoạn dài nếu workflow đã lưu thông tin rõ trong các trường riêng.

### 4.1. Công thức diễn đạt ngắn

~~~text
Để [nhiệm vụ/mục tiêu được giao],
tôi/công việc [chủ thể] cần [action/role cụ thể]
trên [ứng dụng/tài nguyên + phạm vi],
trong [thời gian hoặc điều kiện kết thúc].
Quyền hiện tại chưa đáp ứng vì [khoảng thiếu].
Căn cứ: [ticket/project/owner],
và không yêu cầu [quyền/phạm vi không cần].
~~~

Đây là **khung nội dung**, không phải chuỗi cần sao chép nguyên xi. Nếu có dữ liệu từ ticket/HR/VMS, hệ thống nên **liên kết ID và lấy bằng chứng từ nguồn** thay vì yêu cầu người dùng chép nội dung nhạy cảm vào justification.

## 5. So sánh lý do yếu và lý do đủ rõ

| Câu trả lời chưa đạt | Vì sao chưa đủ | Ví dụ làm rõ |
|---|---|---|
| “Cần để làm việc.” | Không có nhiệm vụ, resource, scope | “Cần xem ticket PRJ-17 được phân công trong đợt nghiệm thu này.” |
| “Sếp bảo cấp.” | Không chỉ ra quyền được duyệt và chủ sở hữu dữ liệu | “Manager xác nhận nhiệm vụ; data owner của CRM cần xác nhận quyền xem nhóm khách hàng dự án.” |
| “Cấp như bạn An.” | Có thể clone cả quyền dư thừa của An | “Cần role `crm_lead_reader` cho dự án B; quyền không gồm export.” |
| “Càng rộng càng dễ xử lý.” | Trái least privilege | “Chỉ cần khởi động lại service X ở staging trong cửa sổ bảo trì.” |
| “Khẩn cấp.” | Thiếu sự kiện, mốc, tác động | “Sự cố INC-204 làm gián đoạn thanh toán; cần JIT restart service trong 30 phút.” |
| “Phục vụ dự án.” | Không biết dự án nào và hết hạn lúc nào | “PRJ-17, read-only repo, từ 04/12 đến hết nghiệm thu 12/12.” |
| “Cần quyền vĩnh viễn.” | Không có căn cứ giữ lâu | “Vai trò cơ bản theo job code đã duyệt; review khi Mover và định kỳ.” |
| “Tôi được tin tưởng.” | Độ tin tưởng cá nhân không mô tả rủi ro | “Nhiệm vụ, hành động và data owner xác nhận bằng request ID.” |
| “Cần admin để đọc log.” | Role không tương xứng action | “Chỉ cần `logs.read` cho dịch vụ đã phân công.” |

### 5.1. Viết dài chưa chắc tốt

Một đoạn dài gồm tên nhiều người, thông tin nội bộ không liên quan và lời cam kết “tôi chịu trách nhiệm” **không thay thế** scope, thời hạn hoặc approval. Ví dụ tốt có thể rất ngắn nếu các trường có cấu trúc đã nêu rõ nhiệm vụ và mức rủi ro.

### 5.2. “Cần gấp” là thuộc tính ưu tiên, không phải căn cứ quyền

Độ khẩn cấp có thể quyết định **thứ tự xử lý**, nhưng không tự chứng minh quyền được phép. Quyền admin khẩn cấp thường cần **nhiều kiểm soát hơn**: xác minh sự cố, scope/time-bound, audit và hậu kiểm.

## 6. Từ mục đích nghiệp vụ đến permission cụ thể

Người dùng thường nghĩ bằng **nhiệm vụ**, còn IAM và ứng dụng biểu diễn bằng **permission, role, entitlement, API scope hoặc nhóm**. Bản lý do phải nối hai lớp này.

Ví dụ:

~~~text
Nhu cầu: Đối chiếu hóa đơn thuộc dự án A
  ├─ Cần: invoice.read@project-A
  ├─ Có thể cần: report.generate@project-A
  ├─ Không mặc định cần: invoice.export@all-projects
  ├─ Không cần: invoice.delete
  └─ Không cần: tenant.admin

Đầu ra: role/permission nhỏ nhất đáp ứng nhiệm vụ,
        không nhất thiết chọn vai trò rộng nhất có tên gần đúng.
~~~

### 6.1. Role request khác permission request

- **Role request:** Xin một role được thiết kế sẵn như `finance_reader`. Cần chứng minh **nhiệm vụ người dùng phù hợp vai trò**.
- **Permission request:** Xin action rất cụ thể, ví dụ `invoice.export`. Cần chứng minh **vì sao role cơ bản không đủ**.
- **Access package:** Xin gói đa ứng dụng đã được định nghĩa. Cần kiểm **những quyền nào trong gói thật sự cần** và ràng buộc phạm vi.
- **Exception request:** Xin quyền nằm ngoài chính sách mặc định. Cần căn cứ và kiểm soát rủi ro bổ sung.

Một lời giải thích “cần quyền làm báo cáo” chưa đủ để cấp **tất cả** permission trong một role nếu role đó chứa `admin` hoặc `export` nhạy cảm.

### 6.2. Không suy ra quyền từ chức danh một cách tuyệt đối

Chức danh “Kế toán”, “SRE” hoặc “Team Lead” có thể là tín hiệu để gợi ý role, nhưng **nhiệm vụ, tenant, dự án, chức năng cụ thể và trạng thái engagement** mới quyết định quyền mong muốn.

Với yêu cầu nhạy cảm, hệ thống có thể hỏi thêm: *Tại sao quyền có sẵn theo role hiện tại chưa đáp ứng nhiệm vụ?*

## 7. Scope là một phần của lý do, không phải thông số kỹ thuật phụ

Cùng một action có thể có mức rủi ro rất khác nhau tùy phạm vi.

| Khía cạnh scope | Phạm vi hẹp | Phạm vi rộng rủi ro hơn |
|---|---|---|
| **Tenant** | tenant-A | tất cả tenant |
| **Project** | project-17 | toàn bộ portfolio |
| **Environment** | staging | production |
| **Resource** | một database/view | cả cluster hoặc mọi database |
| **Data class** | dữ liệu tổng hợp | thông tin định danh/nhạy cảm thô |
| **Action** | read | export/delete/admin |
| **Duration** | một ca bảo trì | standing access không hạn |
| **Delegation** | tự thực hiện | được hành động thay mặt nhiều chủ thể |

Một justification đủ mạnh cho `log.read@staging` **không tự hợp lệ** khi đổi request thành `log.delete@production`. Nếu scope thay đổi, phải đánh giá lại lý do và mức phê duyệt.

### 7.1. Tránh sao chép quyền của người khác

Một người có cùng công việc có thể giữ nhiều grant ngoài role cơ bản: quyền khẩn cấp, direct ACL, dự án trước hoặc quyền đã hết căn cứ. **“Cấp giống người X”** chỉ nên là một **gợi ý để phân tích mẫu**, không phải quyết định clone toàn bộ.

### 7.2. Đúng scope phải được thực thi ở Resource Server

Nếu request ghi `project=A` nhưng API chỉ kiểm `role=reader` mà không kiểm project, việc ghi scope trong justification **không ngăn được truy cập ngoài dự án**. Cần RBAC/ABAC hoặc authorization theo resource tại PEP/API.

## 8. Thời hạn: quyền cần đến khi nào?

**Thời hạn truy cập** cần tương xứng với thời gian của nhiệm vụ. Tuy nhiên, không nên bắt mọi role cơ bản có TTL ngắn một cách cơ học.

| Trường hợp | Cách nghĩ về thời hạn |
|---|---|
| Role cơ bản theo công việc | Có hiệu lực khi engagement/role còn hợp lệ, được rà soát khi Mover và định kỳ |
| Truy cập dự án | Theo mốc dự án/assignment, có expiry hoặc event-driven revoke |
| Quyền đặc quyền bảo trì | JIT với cửa sổ thao tác và TTL ngắn theo chính sách |
| Nhà thầu ngoài | Không vượt mốc hợp đồng/engagement được xác minh |
| Truy cập sự cố | Theo incident và mốc khôi phục; có hậu kiểm |
| Workload dài hạn | Quyền theo vòng đời workload, owner và credential policy |
| Ngoại lệ SoD/risk | Thường cần thời hạn rõ, người chấp nhận rủi ro và điều kiện bù trừ |

### 8.1. Expiry theo đồng hồ và expiry theo sự kiện

Một grant có thể hết hiệu lực khi:

- Đến `expiresAt`.
- Ticket/dự án đóng sớm.
- Người dùng đổi nhóm hoặc thôi tham gia nhiệm vụ.
- Nhà thầu hết engagement.
- Approval bị rút.
- Security đánh dấu tài khoản rủi ro cao.
- Role hoặc policy bị thay thế theo quản trị.

**Thiết kế tốt thường kết hợp time-bound với event-driven revocation.** Không giữ quyền cho tới ngày hết hạn nếu lý do đã biến mất trước đó.

### 8.2. TTL của grant khác TTL của token/phiên

PIM có thể báo quyền JIT hết hạn nhưng một phiên database đã mở vẫn còn quyền admin. Vì vậy phải xác định **khi nào quyền hiệu dụng ở target phải dừng**, không chỉ lúc nào workflow đánh dấu grant hết hạn.

## 9. Bằng chứng: liên kết lý do với nguồn có thẩm quyền

Lý do là **khẳng định của người yêu cầu**; bằng chứng giúp tổ chức **kiểm chứng khẳng định đó**.

| Nhóm bằng chứng | Nguồn thích hợp | Cần xác minh |
|---|---|---|
| Nhiệm vụ/dự án | Project system, issue/change ticket | Project còn active, user có assignment |
| Quan hệ nhân sự | HR hoặc VMS | Engagement đúng identity và mốc hiệu lực |
| Chủ sở hữu tài nguyên | Application/data catalog | Owner thực sự có thẩm quyền duyệt |
| Role eligibility | IAM/IGA role catalog | Role phù hợp job/assignment |
| Quyền đang có | Target app/directory/IdP | Có thiếu quyền thật hay lỗi mapping? |
| Phê duyệt thay đổi | Workflow có xác thực approver | Người duyệt đúng cấp, không bị tự duyệt |
| Incident khẩn cấp | Incident management | Mức độ, phạm vi và người chỉ huy sự cố |
| Workload purpose | Service catalog/CMDB/deployment registry | Workload có owner và nhiệm vụ còn hiệu lực |

**Một đường dẫn hoặc mã ticket do người dùng gõ không tự chứng minh dữ liệu.** Workflow phải tra nguồn có thẩm quyền hoặc yêu cầu người duyệt đủ quyền xác nhận.

### 9.1. Không yêu cầu dán toàn bộ hồ sơ

Để chứng minh contractor còn hợp đồng, request thường chỉ cần **engagement ID**, mốc hoặc tín hiệu status được xác nhận từ VMS. Không cần dán hộ chiếu, số giấy tờ, hợp đồng đầy đủ hoặc dữ liệu cá nhân ngoài phạm vi.

### 9.2. Bằng chứng có thể thay đổi

Ticket có thể bị hủy, người dùng không còn là assignee, sponsor bị thay hoặc dự án đóng. Justification tốt phải **liên kết đến căn cứ sống** hoặc có cơ chế tái kiểm tra, không chỉ lưu ảnh chụp đã hết hiệu lực.

## 10. Ai được gửi yêu cầu và gửi thay ai?

Trong IAM, cần phân biệt:

- **Requester:** Người gửi form/ticket.
- **Beneficiary/subject:** Người hoặc workload sẽ nhận quyền.
- **Manager/sponsor:** Người xác nhận quan hệ công việc hoặc nhu cầu.
- **Resource/data owner:** Người có thẩm quyền với tài nguyên.
- **Approver:** Người thực hiện quyết định approval ở bước thích hợp.
- **Provisioning operator/system:** Bên triển khai grant.
- **Auditor/reviewer:** Bên đối soát và kiểm chứng sau cấp.

**Requester không phải lúc nào cũng là beneficiary.** Manager có thể yêu cầu quyền cho Joiner, helpdesk có thể mở ticket thay người dùng, automation có thể xin quyền cho service principal. Bản lý do cần chỉ rõ **ai thực sự được cấp quyền**, không suy từ người nhấn nút “Submit”.

### 10.1. Tránh tự yêu cầu rồi tự duyệt

Với quyền nhạy cảm, người đề nghị hoặc beneficiary không nên có khả năng vừa **tự mô tả lý do, tự phê duyệt, tự cấp và tự xác nhận hoàn tất** nếu chính sách yêu cầu tách nhiệm vụ.

### 10.2. Sponsor khác data owner

Manager có thể xác nhận rằng nhân viên được giao làm dự án A, nhưng quyền xuất dữ liệu khách hàng có thể cần **data owner hoặc application owner** riêng phê duyệt. Một lý do nêu “manager đồng ý” chưa thay sự chấp thuận của owner dữ liệu khi policy bắt buộc.

## 11. Approval không phải bước kiểm tra duy nhất

Một request đi qua các tầng kiểm tra khác nhau:

1. **Request completeness:** Có mô tả, resource, scope, thời hạn, căn cứ?
2. **Identity/eligibility:** Beneficiary có đúng identity, account, engagement và loại subject không?
3. **Policy validation:** Quyền được xin có tương thích role, action, tenant và dữ liệu không?
4. **Risk/SoD:** Có xung đột chức năng hoặc mở đặc quyền quá rộng không?
5. **Business approval:** Nhiệm vụ có thật, có cần quyền đó không?
6. **Resource owner approval:** Tài nguyên có cho phép loại thao tác đó không?
7. **Provisioning:** Hệ thống đích cấp chính xác quyền đã phê duyệt.
8. **Readback:** Quyền thực tế và thời hạn có khớp không?
9. **Review/revocation:** Khi lý do không còn, grant có được xử lý không?

Một approver bấm **APPROVED** chỉ xác nhận bước quyết định theo thẩm quyền, **không bảo đảm connector SCIM đã áp role, cũng không bảo đảm role không cho quyền rộng hơn mô tả**.

### 11.1. Decision có thể là yêu cầu sửa, không chỉ approve/deny

Nếu thiếu thời hạn hoặc scope, hệ thống nên có lựa chọn **RETURN_FOR_INFORMATION** với câu hỏi cụ thể thay vì buộc người dùng gửi lại hoàn toàn hoặc tự đoán.

Nếu request xin `admin` để xem log, reviewer có thể **đề xuất role `logs.read`** và yêu cầu người gửi xác nhận; **không tự ý cấp một quyền khác** nếu quy trình cần sự đồng ý/approval mới.

## 12. Mô hình dữ liệu Access Request với justification riêng

Ví dụ JSON minh họa một yêu cầu có cấu trúc:

~~~json
{
  "requestId": "AR-2026-1248",
  "requesterId": "P-2048",
  "beneficiary": {
    "kind": "HUMAN",
    "canonicalId": "P-2048",
    "engagementId": "ENG-713"
  },
  "requestedAccess": {
    "applicationId": "invoice-app",
    "permission": "invoice.read",
    "tenantId": "tenant-vn",
    "resourceScope": {
      "projectIds": ["PRJ-17"]
    },
    "environment": "production",
    "validFrom": "2026-12-02T09:00:00+07:00",
    "validUntil": "2026-12-06T18:00:00+07:00"
  },
  "businessJustification": {
    "purpose": "Doi soat hoa don cho ky thang 12",
    "assignedTaskRef": "FIN-218",
    "whyExistingAccessInsufficient": "Role hien tai chi xem duoc dashboard",
    "successCondition": "Bao cao doi soat da duoc owner xac nhan",
    "exclusions": ["invoice.export", "invoice.delete", "tenant.admin"]
  },
  "evidenceRefs": ["FIN-218", "PRJ-17-OWNER-ASSIGNMENT"],
  "requestedRiskTier": "SYSTEM_CALCULATED",
  "approvalState": "PENDING_REVIEW"
}
~~~

**Các giá trị là giả lập.** Schema không phải chuẩn của OAuth, SCIM hay một sản phẩm IGA cụ thể. Trong sản phẩm thật:

- **Subject, engagement, assignment và tenant membership** phải được lấy/xác minh ở nguồn đáng tin.
- `requestedRiskTier` không được client quyết định nếu rủi ro dùng để cấp approval.
- `approvalState` không được người gửi tùy ý đổi sang `APPROVED`.
- Quyền thực tế còn phụ thuộc policy tại ứng dụng.
- Không dùng `exclusions` làm bằng chứng tự động rằng API đã chặn các permission ấy.

### 12.1. Có nhất thiết lưu justification dạng văn bản tự do?

Không. Một hệ thống có thể kết hợp **dropdown có cấu trúc** (mục đích, ticket, scope, expiry) và **mô tả ngắn bằng ngôn ngữ tự nhiên**. Ưu tiên cấu trúc giúp kiểm chứng và đối soát; vẫn cần chỗ giải thích khi nhiệm vụ không phù hợp mẫu chuẩn.

**Không bắt người dùng chọn một giá trị “other” rồi mất toàn bộ bối cảnh.** Có thể định nghĩa validation theo loại request và mức rủi ro.

## 13. Workflow từ lý do đến quyền hiệu dụng

~~~mermaid
flowchart TD
    A["Requester: nhiệm vụ + lý do<br/>resource, action, scope, time"] --> B["Validation<br/>đủ dữ liệu, đúng subject"]
    B --> C["IAM/IGA kiểm eligibility<br/>HR/VMS, role catalog"]
    C --> D["Policy + risk + SoD<br/>least privilege"]
    D --> E{"Cần bổ sung căn cứ?"}
    E -->|Có| F["Trả về câu hỏi cụ thể<br/>không tự nâng quyền"]
    F --> A
    E -->|Không| G["Approver phù hợp<br/>manager/data owner/security"]
    G --> H{"Approval?"}
    H -->|Từ chối| I["DENIED: lưu reason code<br/>và thông báo tối thiểu"]
    H -->|Đồng ý| J["Provision role/grant<br/>đúng scope + expiry"]
    J --> K["Readback tại target<br/>role, ACL và effective access"]
    K --> L{"Kết quả đạt policy?"}
    L -->|Không| M["PENDING_VERIFICATION<br/>exception + owner"]
    L -->|Có| N["ACTIVE / READY<br/>audit + lifecycle triggers"]
    N --> O["Revalidate/Expire/Revoke<br/>Mover/Leaver/project close"]
    O --> P["Readback thu hồi<br/>phiên/token/quyền khi cần"]
~~~

### 13.1. Các trạng thái request cần hiểu đúng

| Trạng thái minh họa | Ý nghĩa | Không nên nhầm với |
|---|---|---|
| `DRAFT` | Người gửi đang soạn | Yêu cầu đã vào quy trình |
| `SUBMITTED` | Request đã được nhận | Đã phê duyệt |
| `NEEDS_INFORMATION` | Thiếu căn cứ hoặc scope | Người dùng không đủ quyền vĩnh viễn |
| `UNDER_REVIEW` | Đang đánh giá policy/owner | Đã cấp quyền |
| `APPROVED` | Đã có quyết định cấp có điều kiện | Target đã áp quyền |
| `DENIED` | Không được cấp theo căn cứ hiện tại | Account bị disable |
| `PROVISIONING` | Đang gửi lệnh đến hệ thống đích | Quyền hiệu dụng đã đúng |
| `ACTIVE_VERIFIED` | Readback xác minh grant được áp | Quyền sẽ tồn tại mãi |
| `REVOKE_PENDING` | Đã đến lúc thu hồi/chưa xác minh | Đã thu hồi hoàn toàn |
| `CLOSED_VERIFIED` | Hoàn tất theo tiêu chí của workflow | Tất cả đường truy cập toàn doanh nghiệp đều đã được kiểm nếu scope không bao phủ |

Đây là **mô hình tham khảo**, không phải enum chuẩn. Hệ thống cần định nghĩa rõ khi nào được chuyển trạng thái, ai có quyền và bằng chứng kèm theo.

## 14. Một justification tốt phải phù hợp với RBAC và ABAC

**RBAC** gán permission theo vai trò; **ABAC** xét thêm thuộc tính của subject, resource, action và context. Lý do yêu cầu phải tương ứng với **điều kiện quyền thực sự sẽ áp dụng**.

Ví dụ:

~~~text
Subject:
  role: finance_reader
  engagement: ACTIVE
  allowedProjects: [PRJ-17]
  tenant: tenant-vn

Request:
  invoice.read@PRJ-17
  02/12 -> 06/12
  reason: FIN-218

Policy:
  PERMIT nếu subject active
  AND role hợp lệ
  AND tenant và project khớp
  AND grant active trong thời hạn
  AND không có deny policy khác.
~~~

**Justification không tự cấp `finance_reader`.** Role phải được phê duyệt/cấp đúng. **Scope trong request phải gắn với policy tại API**; nếu backend không kiểm `projectId`, quyền có thể bị mở ngoài phạm vi đã duyệt.

### 14.1. Cảnh báo overgrant

Nếu catalog chỉ có role `finance_admin` gồm đọc, xóa, export và quản lý user, trong khi người dùng chỉ cần xem hóa đơn, một justification dù rất rõ cũng **không biến role rộng thành hợp lệ**.

Hệ thống nên tìm role/permission nhỏ hơn, yêu cầu application owner điều chỉnh role catalog hoặc đưa yêu cầu vào quản trị ngoại lệ có thời hạn.

## 15. Separation of Duties: lý do hợp lệ vẫn có thể bị từ chối

**SoD** ngăn một người nắm kết hợp quyền tạo điều kiện gian lận hoặc thiếu kiểm soát.

Ví dụ:

~~~text
User đang có:
  invoice.create

User xin:
  invoice.approve

Lý do:
  "Tôi làm thay đồng nghiệp đang nghỉ."

Vấn đề:
  Quyền mới có thể cho phép tự phê duyệt hóa đơn do mình tạo.
~~~

Lý do “đang thiếu người” có thể là sự kiện thật, nhưng không tự vượt chính sách SoD. Cần xem:

- Có thể giao quyền cho **approver độc lập** khác không?
- Có thể giới hạn role cho giao dịch không phải do người đó tạo?
- Có cần **kiểm soát bù trừ, approval rủi ro, ghi log và expiry** không?
- Nếu ngoại lệ không được phép, có phải **DENY** dù nhu cầu công việc gấp không?

**Đừng sửa bằng cách đổi tên permission** để che xung đột. Ràng buộc phải xét **quyền hiệu dụng** và quan hệ giữa subject với resource/giao dịch.

### 15.1. Không để một người duyệt yêu cầu của chính họ khi chính sách cấm

Đặc biệt với quyền admin, thay đổi policy và export dữ liệu nhạy cảm, workflow cần kiểm người gửi, beneficiary, approver và owner, tránh xung đột lợi ích.

## 16. Lý do yêu cầu đặc quyền: cần mạnh hơn lý do thường

Khi xin quyền **PAM/PIM, cloud admin, database admin, production deploy hoặc secret access**, justification cần nêu:

1. **Change/incident/tác vụ cụ thể** có thể kiểm chứng.
2. **Hành động bắt buộc**, tránh “full admin cho chắc”.
3. **Target/environment**: đúng server, database, cluster, tenant.
4. **Khung thời gian**: mốc bắt đầu, TTL, điều kiện kết thúc sớm.
5. **Người chịu trách nhiệm** và quy trình approval/SoD.
6. **Mức xác thực/step-up** nếu policy yêu cầu.
7. **Audit/session controls** và cách kiểm tra kết quả sau khi quyền hết hạn.

Ví dụ đủ rõ:

> “Thực hiện thay đổi CHG-9812: restart service thanh toán `payment-worker-prod-1` sau cập nhật cấu hình, từ 20:00–20:30 ngày 05/12. Cần `service.restart` trên một service, không cần shell root/global admin. Service owner xác nhận change và giám sát kết quả.”

### 16.1. JIT là công cụ giới hạn thời gian, không tự xác nhận lý do

Một role global admin cấp 15 phút vẫn có thể quá rộng cho nhiệm vụ restart service. Cần kết hợp **Just-in-Time** với **Just-Enough Access** và policy theo resource.

### 16.2. Break-glass không phải lựa chọn “khỏi viết lý do”

Trong tình huống khẩn cấp không có thời gian chờ approval thường, có thể dùng **break-glass theo quy trình được thiết kế**. Vẫn cần **incident ID, người sử dụng, mục đích, thời điểm, phạm vi, ghi log và hậu kiểm** theo chính sách. Không bật một cơ chế `emergency=true` do client tự gửi để bỏ qua mọi kiểm soát.

## 17. Lý do yêu cầu cho nhà thầu và đối tác liên kết

Nhà thầu có thể đăng nhập qua **IdP đối tác** hoặc account nội bộ. Justification cần gắn với **engagement/sponsor và tài nguyên do tổ chức nhận quản lý**, không chỉ dựa trên việc đối tác đã xác thực người dùng.

Ví dụ:

~~~text
Beneficiary: Contractor C-901, engagement ENG-77
Sponsor:     Project owner của PRJ-17
Purpose:     Kiểm thử luồng thanh toán phiên bản mới
Action:      test-result.read
Resource:    PRJ-17 / staging
Window:      Từ 04/12 đến hết nghiệm thu 10/12
Evidence:    Project task QA-312 + engagement active
Excluded:    production, export dữ liệu khách hàng, role admin
~~~

### 17.1. Đủ quyền đăng nhập SSO không đồng nghĩa được truy cập dự án

Federation metadata/SSO giúp xác thực danh tính, không tự tạo permission. IAM có thể phải ánh xạ `(iss, sub)` hoặc subject định danh tương đương, tạo account qua SCIM/API và cấp role theo project.

### 17.2. Nhiều engagement, nhiều lý do riêng

Nếu contractor có hai hợp đồng A và B, yêu cầu vào A cần có **lý do và hạn A**. Khi A kết thúc, không thể giữ grant A chỉ vì account vẫn active phục vụ B.

## 18. Lý do yêu cầu cho service account và workload

Một **workload** có thể cần cấp thêm scope OAuth, truy cập secret, chạy job hay gọi API. Nó không có “sếp trực tiếp” hoặc “công việc cá nhân”, nhưng vẫn cần **business/technical justification có owner**.

| Trường | Ví dụ |
|---|---|
| **Workload identity** | `svc-report-sync` |
| **Owner kỹ thuật** | Data Platform Team |
| **Mục đích** | Đồng bộ số liệu báo cáo đã phê duyệt |
| **Requested action** | `reports.read` |
| **Resource/audience** | Reporting API, tenant-vn, production |
| **Credential** | Managed identity hoặc cơ chế client authentication được duyệt |
| **Thời hạn** | Theo lifecycle của workload; rà soát định kỳ và khi decommission |
| **Change reference** | DEP-414 |
| **Giới hạn** | Không `reports.delete`, không quyền IAM admin |
| **Verification** | Workload gọi API đúng scope và bị từ chối ngoài scope |

### 18.1. Không coi người tạo service account là chủ thể hưởng quyền

Một nhà phát triển tạo service principal không có nghĩa quyền cấp cho principal là **quyền của người đó**; hai identity khác nhau. Tuy nhiên người có thể sửa pipeline hoặc đọc secret có thể tác động **gián tiếp** bằng quyền của workload, nên cần đánh giá đặc quyền theo chuỗi.

### 18.2. Khi owner Mover hoặc Leaver

Lý do “đồng bộ báo cáo mỗi đêm” có thể vẫn còn khi owner nghỉ việc. Phải **chuyển owner, xác nhận workload còn cần hoạt động, rà soát credential từng bị biết và thu hồi quyền dư thừa**, không tự xóa service account gây gián đoạn hoặc giữ account mồ côi vô hạn.

## 19. Không coi nội dung lý do là dữ liệu bảo mật đã được xác minh

Justification thường là **văn bản do requester nhập**. Hệ thống phải coi nó là **untrusted input**, kể cả khi biểu mẫu chỉ dành cho nhân viên.

Các rủi ro gồm:

- Khai sai dự án, quyền hoặc thời hạn để xin quyền rộng.
- Dẫn ticket/owner giả nhằm đánh lừa approver.
- Chèn yêu cầu “bỏ qua chính sách” trong phần mô tả.
- Dán dữ liệu nhạy cảm hoặc secret vào trường tự do.
- Lạm dụng Markdown/HTML hoặc nội dung đặc biệt để tấn công giao diện review/log nếu render không an toàn.
- Sử dụng lời lẽ khẩn cấp gây áp lực thay vì bằng chứng.
- Cố thay đổi `approvalStatus` hoặc `riskLevel` qua API client.

### 19.1. Cần kiểm tra ở backend

Một kiểm soát đầy đủ không chỉ là nút trên giao diện:

- Xác thực requester và quyền request thay beneficiary.
- Kiểm canonical ID, tenant, engagement, target và loại chủ thể.
- Đối chiếu scope và entitlement hợp lệ trong catalog.
- Bảo vệ field chỉ server/approver được chỉnh.
- Giới hạn kích thước, sanitize/encode khi hiển thị văn bản.
- Kiểm ticket/evidence qua kết nối có thẩm quyền.
- Không tự thực thi mệnh lệnh nằm trong free text.
- Audit thay đổi justification sau khi request được phê duyệt.

### 19.2. Trợ lý AI có thể hỗ trợ viết nhưng không được duyệt thay người

Công cụ hỗ trợ có thể gợi ý cách diễn đạt nhiệm vụ rõ ràng, nhận diện thiếu resource/expiry hoặc phân loại nguy cơ **sơ bộ**. Tuy nhiên:

- AI không tự xác nhận người dùng được giao nhiệm vụ thật.
- Không tự điền approval, giả mạo owner hoặc thêm bằng chứng không tồn tại.
- Không tự cấp role chỉ vì câu văn nghe đáng tin.
- Không khuyến khích đưa thông tin nhạy cảm vào prompt/log.
- Các quyết định cấp quyền thực tế phải tuân workflow và policy có thẩm quyền.

## 20. Kiểm tra chất lượng justification bằng quy tắc có cấu trúc

Một validation layer có thể kiểm **tính đầy đủ và sự phù hợp hình thức**, trước khi chuyển request sang người duyệt. Ví dụ mã giả Python:

~~~python
# Pseudocode: kiểm dữ liệu có đủ và nhất quán về cấu trúc,
# không phải bộ máy quyết định APPROVE hay cấp quyền.
def validate_justification(request, authoritative):
    issues = []

    if not request.get("businessPurpose"):
        issues.append("MISSING_BUSINESS_PURPOSE")

    if not request.get("requestedPermission"):
        issues.append("MISSING_PERMISSION")

    if not request.get("applicationId"):
        issues.append("MISSING_APPLICATION")

    if not request.get("resourceScope"):
        issues.append("MISSING_RESOURCE_SCOPE")

    if not request.get("taskRef"):
        issues.append("MISSING_TASK_REFERENCE")

    start = request.get("validFrom")
    end = request.get("validUntil")
    if start is not None and end is not None and end <= start:
        issues.append("INVALID_TIME_WINDOW")

    # Không dựa vào trạng thái do requester tự khai.
    beneficiary_id = request.get("beneficiaryId")
    actual_engagement = authoritative.lookup_engagement(beneficiary_id)

    if actual_engagement is None:
        issues.append("UNKNOWN_BENEFICIARY")
    elif not actual_engagement.is_eligible_for_request():
        issues.append("INELIGIBLE_ENGAGEMENT")

    # Kết quả chỉ cho biết vấn đề cần xem lại.
    # Approved/Denied phải đến từ engine và workflow có thẩm quyền.
    return {
        "readyForReview": len(issues) == 0,
        "issues": issues
    }
~~~

**Giới hạn:** Đây là pseudocode, không phải mã dùng ngay trong production. Việc so sánh thời gian thật cần parse định dạng, timezone và xử lý null; xác minh task/evidence, SoD, role catalog, scope, risk và policy phải được thực hiện bởi hệ thống/nhân sự có thẩm quyền.

### 20.1. Đừng chấm điểm chỉ theo độ dài

Một câu 30 từ kèm ticket, scope, TTL có thể đủ. Một đoạn 500 từ có thể hoàn toàn thiếu resource hoặc bằng chứng. Điểm chất lượng nên phản ánh **mức đủ thông tin để quyết định**, không phải số ký tự.

### 20.2. Không tự động từ chối mọi yêu cầu “khác mẫu”

Một nhiệm vụ mới chưa có role template có thể hợp lệ. Hệ thống nên chuyển sang review chi tiết để **thiết kế quyền phù hợp**, thay vì bắt người dùng chọn role rộng do catalog thiếu lựa chọn.

## 21. Phân loại request và yêu cầu lý do theo mức rủi ro

Một bộ câu hỏi áp dụng cho mọi quyền có thể khiến **quyền đọc ít nhạy cảm** quá phức tạp, trong khi **quyền xóa production** lại thiếu kiểm soát. Nên điều chỉnh theo rủi ro.

| Nhóm request | Ví dụ | Những yếu tố cần nhấn mạnh |
|---|---|---|
| **Baseline access** | Role chuẩn khi Joiner | Job/engagement và role eligibility từ HR/IAM |
| **Standard additional access** | Quyền đọc dự án | Task, project, owner và expiry |
| **Sensitive data access** | Export thông tin khách hàng | Data purpose, classification, phạm vi, DLP/approval |
| **Privileged access** | Admin production | Change/incident, action, target, JIT, step-up, SoD |
| **High-risk exception** | Vượt role catalog hoặc SoD | Giải pháp thay thế, risk owner, compensation, TTL |
| **External contractor** | Hệ thống dự án | Engagement, sponsor, resource, mốc hợp đồng |
| **Non-human access** | Service client scope/API | Workload owner, mục đích, audience, credential |
| **Emergency break-glass** | Khôi phục sự cố | Incident, mục đích khẩn cấp, logging, hậu kiểm |

**Risk tier không nên được quyết định bởi requester đơn thuần.** Nó cần đến từ resource classification, permission catalog, môi trường, loại subject và risk policy.

### 21.1. Mô hình xử lý tự động có kiểm soát

Đối với role chuẩn có điều kiện xác minh rõ, tổ chức có thể dùng **policy-based auto-approval**. Lý do có thể được suy từ **nhiệm vụ/role đã được quản trị**, thay vì bắt người dùng nhập đoạn văn lặp lại.

**Auto-approval không có nghĩa không cần căn cứ:** Hệ thống phải lưu **quy tắc, dữ liệu, thời điểm và phiên bản policy** làm lý do quyết định, để vẫn kiểm toán được.

## 22. Lý do yêu cầu trong Joiner lifecycle

**Joiner** gồm xác minh danh tính, tạo account và cấp quyền để người mới thực hiện công việc. Với role cơ bản được quy định trong **role catalog**, một số quyền có thể xuất phát từ quy tắc **birthright access**.

Ví dụ:

~~~text
Joiner: nhân viên Finance mới
Source: HR event với personId, position, department, effectiveAt
Role catalog: finance_reader theo job assignment đã duyệt
Justification provenance:
  "Baseline access theo Finance role policy"
  Policy reference: ROLE-FIN-READ-v4
  Authoritative event: HR-JOIN-902
  Effective window: theo engagement còn hợp lệ
~~~

### 22.1. Có phải từng permission cần người mới viết lý do?

Không nhất thiết. Với **quyền baseline**, nghiệp vụ có thể đã xác định từ role engineering và HR/IGA policy. Khi đó **policy rule + authoritative assignment** đóng vai trò căn cứ, có thể tự động cấp khi đủ điều kiện.

Nhưng **ngoại lệ, scope khác thường hoặc quyền đặc quyền** cần lý do cụ thể và approval bổ sung theo rủi ro.

### 22.2. Không sao chép quyền từ người tiền nhiệm

Người trước có thể từng được thêm nhóm, làm dự án khác hoặc giữ quyền tạm chưa thu hồi. “Người mới thay anh A nên cấp y hệt A” là lời giải thích nguy hiểm. Cần kiểm **nhiệm vụ hiện tại và catalog đã duyệt**, không sao chép direct grants cũ.

### 22.3. Quyền không có hiệu lực trước mốc cho phép

Việc chuẩn bị account trước ngày làm việc không có nghĩa được cấp quyền công việc trước `effectiveAt`. Justification cần gắn với **mốc engagement**, đặc biệt khi có dữ liệu nhạy cảm hoặc account contractor.

## 23. Lý do yêu cầu trong Mover lifecycle

Khi một nhân viên **chuyển phòng ban, vai trò, địa điểm hoặc dự án**, nhu cầu truy cập thay đổi. Lời giải thích cho quyền mới cần được đánh giá cùng **quyền cũ phải gỡ**.

Ví dụ:

~~~text
Mover event: P-2048
Old assignment: Sales / Project-A
New assignment: Finance / Project-B

Request:
  invoice.read@Project-B
  Justification: Được giao đối soát B theo FIN-218
  Effective: từ ngày chuyển vai trò

Phải đồng thời rà soát:
  lead.export@Project-A
  quote.approve@Project-A
  direct ACL và role cũ ở ứng dụng
~~~

### 23.1. “Cần quyền mới” không phải lý do giữ quyền cũ

Một lỗi phổ biến là workflow **chỉ cấp thêm** quyền Finance mà bỏ qua role Sales đã hết căn cứ. Trong Mover, IAM cần tính **desired vs effective access** và xét nguồn grant của từng quyền.

### 23.2. Trường hợp chuyển giao hợp lệ

Người chuyển nhóm có thể cần **giữ một quyền cũ trong ba ngày để bàn giao**. Đây là justification **riêng**, có:

- Nhiệm vụ bàn giao được xác nhận.
- Người chịu trách nhiệm ở đội cũ và mới.
- Quyền tối thiểu trên đúng tài nguyên.
- Thời hạn kết thúc.
- Kiểm soát nếu có SoD hoặc dữ liệu nhạy cảm.
- Lệnh và readback thu hồi sau bàn giao.

Không giữ mọi role cũ vô thời hạn chỉ vì “có thể còn việc”.

### 23.3. Một chủ thể có nhiều engagement

Khi engagement A kết thúc nhưng B còn active, IAM phải thu hồi grant gắn **lý do của A** mà không xóa quyền B vẫn có căn cứ. Cần lưu **grant provenance**: request, engagement, role, sponsor, resource và thời gian.

## 24. Lý do yêu cầu trong Leaver lifecycle

**Leaver** làm mất hoặc thu hẹp căn cứ cho những quyền từng hợp lệ. Một request đã được duyệt năm trước **không tiếp tục hợp lệ chỉ vì ticket vẫn còn trạng thái APPROVED**.

Quy trình nên:

1. Nhận biến cố Leaver từ HR/VMS với **identity và mốc hiệu lực**.
2. Xác định tất cả request/grants, role, account và direct ACL có liên quan.
3. Đánh giá entitlement nào thuộc engagement đã kết thúc.
4. Thu hồi nhóm/role và account ở IdP/directory/SCIM/app theo chính sách.
5. Xử lý session, refresh/access token, PAT, SSH key, API key và secret có liên quan.
6. **Readback** quyền thực tế tại target/API bắt buộc.
7. Giữ ngoại lệ chưa hoàn tất ở trạng thái có owner và thời hạn xử lý.
8. Lưu bằng chứng vì sao quyền đã bị chấm dứt.

### 24.1. Không tiếp tục gia hạn một grant khi beneficiary đã Leaver

Nếu hệ thống nhận yêu cầu “extend project access thêm một tuần” nhưng HR/VMS cho thấy engagement đã ENDED, request phải được **đối chiếu eligibility**. Không để người gửi viện dẫn ticket cũ để vượt trạng thái có thẩm quyền.

### 24.2. Lý do cũ vẫn quan trọng cho audit, không phải để duy trì quyền

Sau khi thu hồi, lý do lịch sử có thể được giữ trong audit theo retention policy để giải thích quyền **đã được cấp vì sao**. Nhưng nó không được dùng như căn cứ **tự khôi phục role** khi Rejoiner xuất hiện.

## 25. Gia hạn, tái yêu cầu và rà soát justification

Một yêu cầu hết hạn có thể cần **extension**. Gia hạn không nên chỉ thay ngày kết thúc trong database mà bỏ kiểm tra điều kiện.

### 25.1. Câu hỏi trước gia hạn

- Nhiệm vụ cũ đã hoàn tất chưa? Nếu chưa, vì sao?
- Beneficiary còn đúng role, team, tenant và engagement không?
- Owner dự án có xác nhận yêu cầu tiếp tục?
- Quyền đang dùng có thể giảm scope không?
- Có phát sinh SoD hoặc rủi ro mới không?
- Có cần refresh MFA/approval khi quyền đặc quyền hoặc dữ liệu nhạy cảm?
- Token/session và grant cũ sẽ được xử lý ra sao?
- Có giới hạn số lần gia hạn hoặc thời gian tối đa không?

**Không tự gia hạn vô hạn** cho các quyền ngoại lệ chỉ vì user bấm “extend”. Nếu nhu cầu trở thành **thường trực**, nên xem lại **role engineering và role catalog**; không để quyền tạm biến thành standing privilege thiếu quản trị.

### 25.2. Review theo rủi ro

Quyền có rủi ro cao cần lịch rà soát chặt hơn; quyền cơ bản có thể xét khi Mover hoặc review định kỳ theo chính sách. Tất cả review vẫn phải xác định **lý do còn tồn tại hay không**, không chỉ hỏi manager một câu chung “giữ hết”.

## 26. Gắn justification vào grant provenance và quyền thực tế

**Grant provenance** là dấu vết giải thích một quyền được hình thành từ đâu và vì sao:

~~~text
Grant: invoice.read@Project-A
  Beneficiary: P-2048
  Requested via: AR-2026-1248
  Business task: FIN-218
  Approved by: Finance Data Owner
  Effective window: 02/12–06/12
  Provisioned to: Invoice app / group G-41
  Verified at: target role + resource-level deny tests
  Revoked because: task completed
  Final readback: access denied after 06/12
~~~

Nếu cùng một permission được cấp từ **hai nguồn khác nhau**, gỡ một grant có thể vẫn để quyền hiệu dụng tồn tại qua nguồn kia. Ví dụ role Finance Reader và direct ACL đều chứa `invoice.read`. Vì vậy, **đóng request ≠ hết quyền** nếu quyền còn từ căn cứ khác.

### 26.1. Desired vs effective

~~~text
Desired access:
  Những entitlement còn được phép theo JML + policy

Effective access:
  Những action mà target/API thực sự cho phép

ToGrant:
  Desired - Effective (sau khi xét mọi nguồn grant)

ToRevoke:
  Effective - Desired

Hoàn tất:
  Kiểm bằng readback/negative test phù hợp phạm vi.
~~~

Đây là mô hình tư duy; môi trường thật có nested groups, deny rules, ABAC, nhiều engagement và cache. Không xóa một grant hợp lệ của engagement B khi chỉ yêu cầu A hết hạn.

## 27. Liên kết Request → Approval → Provisioning → Verification

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Requester / Beneficiary
    participant R as Access Request / IGA
    participant H as HR/VMS + Task system
    participant O as Manager / Data owner
    participant S as IdP / SCIM Connector
    participant A as Application / API
    participant V as Audit / Verification

    U->>R: Lý do, task, scope và thời hạn
    R->>H: Kiểm identity, engagement, assignment
    H-->>R: Trạng thái nguồn có thẩm quyền
    R->>R: Kiểm risk, policy, SoD, least privilege
    R->>O: Chuyển yêu cầu có bằng chứng
    O-->>R: Approve / Deny / Need more info
    R->>S: Provision theo scope và hiệu lực nếu approved
    S->>A: Create/update grant
    A-->>R: Phản hồi thao tác
    R->>V: Yêu cầu readback
    V->>A: Kiểm role/ACL và quyền hiệu dụng
    A-->>V: Kết quả thực tế
    V-->>R: Verified hoặc exception
    R->>R: Theo dõi expiry/Mover/Leaver
    R->>S: Revoke khi lý do hết hiệu lực
    R->>V: Đối soát thu hồi và lưu audit
~~~

**Trình tự thật có thể khác** tùy role catalog, SCIM support và sản phẩm. Nhưng các trách nhiệm phải rõ: **request là đề nghị**, **approval là quyết định**, **provisioning là thao tác**, **verification là bằng chứng quyền đã/không còn hiệu lực**.

## 28. Rủi ro thường gặp khi xử lý lý do yêu cầu

| Rủi ro | Ví dụ | Kiểm soát phù hợp |
|---|---|---|
| **Generic justification** | “Cần để làm việc.” | Form có nhiệm vụ, resource, scope, evidence |
| **Copy privilege creep** | “Cấp như người cũ.” | Role catalog, least privilege, review direct grants |
| **False task reference** | Dẫn ticket không thuộc beneficiary | Kiểm nguồn task/assignment có thẩm quyền |
| **Approval confusion** | Manager duyệt thay data owner | Routing theo permission/resource owner |
| **Urgency pressure** | “Khẩn cấp, duyệt ngay, không hỏi.” | Incident validation, JIT và hậu kiểm |
| **SoD bypass** | Xin quyền tạo + phê duyệt | Policy conflict detection, independent review |
| **Excessive scope** | Xin `global.admin` cho việc đọc log | Giới hạn action/target/TTL |
| **Cross-tenant access** | Role A dùng vào dữ liệu B | Tenant-bound grant và API authorization |
| **Stale justification** | Dự án đã đóng nhưng quyền còn active | Trigger theo event, review và auto-expire |
| **Hidden local permission** | SCIM gỡ group nhưng ACL còn | Effective access reconciliation |
| **Token/session residual** | Grant hết hạn nhưng phiên còn quyền | Session/token lifecycle và readback |
| **Service owner departed** | Workload còn admin nhưng không ai quản lý | Owner reassignment, secret review |
| **Secret disclosure in form** | Dán mật khẩu/API key vào ô lý do | Warning, minimization, secret scanning và xử lý lộ |
| **Free-text injection** | Nội dung cố điều khiển workflow hoặc review UI | Treat as data, encode, backend policy |
| **Unbounded extension** | Gia hạn mãi quyền tạm | Expiry policy, approval refresh, role redesign |
| **Incomplete audit** | Không biết ai duyệt hay vì sao | Versioned reason, decision và readback trail |

### 28.1. Chống social engineering của approver

Một lời nhắn “CEO yêu cầu” hoặc “có nguy cơ mất khách hàng nếu chậm” **không đủ để vượt chính sách**. Approver cần xác minh người phát yêu cầu và sự kiện qua **kênh tin cậy**; hệ thống nên có phương án escalation khẩn cấp được thiết kế trước, không phụ thuộc sự quen biết.

### 28.2. Bảo vệ dữ liệu tự do (free-text)

Justification có thể chứa tên khách hàng, mã dự án hoặc tình trạng nội bộ. Hạn chế truy cập theo vai trò, kiểm soát retention, encode khi hiển thị và **không sao chép token, mật khẩu hay dữ liệu đặc biệt nhạy cảm** vào log/ticket.

## 29. Kiểm toán: lưu lý do nào và lưu ra sao?

Một bản ghi audit nên giúp trả lời **vì sao một quyền được yêu cầu, ai đánh giá, quyết định nào được đưa ra và hiệu quả cuối cùng**.

~~~json
{
  "requestId": "AR-2026-1248",
  "beneficiaryId": "P-2048",
  "requesterId": "P-2048",
  "requestedEntitlement": "invoice.read@PRJ-17",
  "businessPurposeCode": "PROJECT_RECONCILIATION",
  "justificationVersion": 2,
  "taskRef": "FIN-218",
  "evidenceStatus": "VERIFIED",
  "riskTier": "SYSTEM_ASSESSED_STANDARD",
  "policyVersion": "access-request-v7",
  "approval": {
    "decision": "APPROVED",
    "approverRole": "finance-data-owner",
    "decisionTime": "2026-12-01T16:00:00+07:00"
  },
  "grant": {
    "target": "invoice-app",
    "validUntil": "2026-12-06T18:00:00+07:00",
    "effectiveAccessVerified": true
  },
  "correlationId": "IAM-REQ-1248"
}
~~~

Đây là **dữ liệu minh họa**, không phải bằng chứng đã phát sinh. Phải ghi đủ **reason/evidence references**, nhưng tránh lưu token, password, OTP, secret, toàn bộ hồ sơ HR hoặc dữ liệu cá nhân ngoài mục đích.

### 29.1. Vì sao cần version justification?

Nếu người dùng sửa lý do sau khi approver đã duyệt, quyết định có thể không còn dựa trên nội dung hiện tại. Cần lưu:

- Nội dung/phiên bản được approver xem.
- Thời điểm sửa, ai sửa và các trường thay đổi.
- Lý do phải phê duyệt lại khi scope, TTL hoặc nhiệm vụ đổi.
- Decision gắn với **version cụ thể**, không gắn vào một văn bản luôn bị ghi đè.

### 29.2. Không biến justification thành nơi lưu bí mật

Một kỹ sư có thể định viết “mật khẩu DB hiện là …” để chứng minh đang vận hành. Đó không phải business justification hợp lệ và tạo nguy cơ lộ credential. Cần **chặn/giảm thiểu và xử lý lộ** theo quy trình bảo mật, đồng thời chuyển nội dung mô tả sang tham chiếu nhiệm vụ không chứa bí mật.

## 30. Chỉ số chất lượng quá trình Access Request

| Chỉ số | Cần đo gì? | Tránh hiểu nhầm |
|---|---|---|
| **Justification completeness** | Tỷ lệ request có task/action/resource/scope/time/evidence cần thiết | Đầy đủ trường không chứng minh sự thật |
| **Evidence verification rate** | Tỷ lệ tham chiếu task/owner/engagement được đối chiếu | Chỉ có ID ticket không đồng nghĩa đã xác minh |
| **Least-privilege correction** | Request được giảm scope/role trước cấp | Không coi sửa request là thất bại của requester |
| **Return-for-info rate** | Tỷ lệ cần làm rõ và nguyên nhân | Quá cao có thể do UI khó hiểu |
| **Approval correctness** | Người duyệt có đúng thẩm quyền và SoD? | Approval nhanh chưa chắc an toàn |
| **Time-to-verified-access** | Từ request hợp lệ đến grant được xác minh | Không đồng nhất với thời gian approve |
| **Overgrant after approval** | Quyền thực tế vượt scope được duyệt | Cần kiểm ở target/API |
| **Expired-justification access** | Grant còn active dù nhiệm vụ/TTL hết | Ưu tiên xử lý quyền tồn dư |
| **Extension frequency** | Quyền tạm được gia hạn bao nhiêu lần | Có thể cần cải tiến role catalog |
| **Missing-owner requests** | Request không có chủ nguồn xác minh | Tránh quyền “không ai chịu trách nhiệm” |
| **SoD violations** | Quyền mới xung đột với grant đang có | Xét mọi nguồn quyền hiệu dụng |
| **Mover/Leaver convergence** | Từ event tới lúc quyền được thu hồi có bằng chứng | Lệnh revoke gửi đi chưa phải hoàn tất |
| **Privileged exception aging** | Quyền đặc biệt chờ hết hạn/thu hồi bao lâu | Không để ngoại lệ vĩnh viễn |
| **User experience** | Request hợp lệ có dễ diễn đạt và xử lý? | Không nới bảo mật chỉ để giảm thời gian |

**Không có SLA chung cho mọi quyền.** Mục tiêu cần được điều chỉnh theo dữ liệu, rủi ro, nghiệp vụ, loại chủ thể và khả năng provisioning/thu hồi của từng ứng dụng.

## 31. Tình huống thực hành A: “Cấp giống đồng nghiệp”

**Bối cảnh:** An là Joiner vào phòng Sales, gửi request “cấp toàn bộ quyền như Bình vì làm cùng vị trí”. Bình đã làm việc lâu năm, có thêm `customer.export` và quyền quản trị project cũ.

**Sai lầm nếu duyệt trực tiếp:** Clone account của Bình khiến An nhận quyền ngoài nhiệm vụ.

**Cách xử lý:**

1. Xác minh An đã có engagement active và job assignment.
2. Tìm role `sales_representative` trong catalog đã duyệt.
3. Xác định project, tenant và hành động An thực sự cần.
4. Đưa quyền ngoài role tiêu chuẩn vào review riêng có business evidence.
5. Provision scope đúng và kiểm API không cho export/admin.
6. Lưu rationale dựa trên role/assignment, không dựa trên danh tính Bình.

**Bài học:** Người đồng nghiệp là **tín hiệu tham khảo**, không phải **nguồn quyền chuẩn**.

## 32. Tình huống thực hành B: Mover xin giữ quyền cũ để bàn giao

**Bối cảnh:** Mai chuyển từ Finance sang Operations vào 10/12, nhưng muốn giữ `invoice.export` đến cuối tháng “phòng khi cần bàn giao”.

**Điểm cần làm rõ:**

- Có nhiệm vụ bàn giao cụ thể nào cần **export**, hay chỉ cần người Finance cung cấp báo cáo?
- Tài nguyên/tenant nào liên quan, giới hạn dữ liệu ra sao?
- Ai là owner chấp nhận tiếp tục cấp quyền?
- Mốc bàn giao kết thúc khi nào?
- Việc giữ quyền có vi phạm SoD với role mới không?

**Một phương án hợp lệ nếu được duyệt:** Grant ngoại lệ hạn rất hẹp cho một tác vụ xác định, với TTL, log, quyền export tối thiểu và readback sau expiry. Nếu không có căn cứ đủ, từ chối và đề xuất workflow bàn giao do đội cũ thực hiện.

**Bài học:** **Chuyển vai trò không tạo quyền giữ lại toàn bộ đặc quyền lịch sử.**

## 33. Tình huống thực hành C: Sự cố cần production admin

**Bối cảnh:** Thanh toán lỗi nghiêm trọng, kỹ sư trực ca gửi request “admin toàn hệ thống ngay”.

**Đánh giá:**

1. Incident có ID và đang được xác nhận không?
2. Dịch vụ/cluster nào thực sự cần thao tác?
3. Có thể dùng `service.restart` hoặc `deployment.rollback` thay global admin không?
4. Có cần JIT/PAM, approval hoặc break-glass theo quy trình?
5. Cần quyền trong bao lâu và ai nhận trách nhiệm?
6. Mọi thao tác có log và khả năng readback/thu hồi không?

Một justification tốt phải gắn với **incident, action, target, TTL và bằng chứng**, không đơn thuần với cảm giác cấp bách.

**Bài học:** Khẩn cấp có thể làm thay đổi **luồng approval**, nhưng không xóa nhu cầu kiểm soát và hậu kiểm.

## 34. Tình huống thực hành D: service account xin quyền xóa dữ liệu

**Bối cảnh:** Job tổng hợp số liệu xin `storage.delete@production` với lý do “dọn dữ liệu cũ”. Người tạo job đã Leaver, account vẫn chạy.

**Vấn đề:**

- Không có owner hiện hành.
- Không xác định dữ liệu nào được xóa.
- Chưa có retention policy hoặc chứng cứ được phép dọn.
- `delete@production` có thể tác động lớn hơn nghiệp vụ.

**Cách giải quyết:**

1. Xác định workload ID, owner mới và mục đích còn hiệu lực.
2. Kiểm retention policy và resource classification.
3. Giới hạn action tới bucket/prefix được phép, tránh quyền cloud admin.
4. Kiểm cơ chế backup/restore hoặc approval dữ liệu khi cần.
5. Đặt thời hạn hoặc rule theo lifecycle workload, credential có bảo vệ.
6. Thử cho phép vùng đúng và từ chối vùng ngoài scope.
7. Ghi evidence, reviewer và kết quả thu hồi khi job nghỉ.

**Bài học:** **Lý do của workload phải kiểm chứng được**, không “được thừa kế” từ người viết script đã nghỉ.

## 35. Tình huống thực hành E: approver đã đồng ý nhưng app cấp quyền rộng hơn

**Bối cảnh:** Data owner duyệt cho Lan `report.read@PRJ-17` trong 5 ngày. Connector SCIM chỉ map yêu cầu đó sang role `report_admin` của ứng dụng, cho quyền export/delete mọi dự án.

**Nhận định:** **Approval không hợp thức hóa overgrant** do mapping sai. Dù user có business justification đúng, quyền thực tế vượt điều đã duyệt.

**Cách xử lý:**

1. Không đánh dấu request `ACTIVE_VERIFIED` khi role target vượt scope.
2. Kiểm role mapping giữa IAM, group, SCIM và app.
3. Đề nghị quyền nhỏ hơn hoặc điều chỉnh app authorization theo phạm vi.
4. Nếu chưa thể bảo đảm least privilege, không cấp quyền rộng thay thế trái policy.
5. Thử negative cases ở dự án khác và chức năng export/delete.
6. Audit thay đổi mapping, owner và quyết định bảo mật.

**Bài học:** **Lý do rõ ràng + approval hợp lệ** vẫn chưa đủ nếu **target không thể thực thi giới hạn đó**.

## 36. Tình huống thực hành F: Leaver và yêu cầu gia hạn tự động

**Bối cảnh:** Contractor Bình có quyền `repo.write@PRJ-17` đến 15/12. Ngày 12/12, VMS kết thúc engagement trước hạn. Một workflow tự động gia hạn request vì ticket dự án chưa đóng.

**Sai lầm:** Workflow ưu tiên ticket cũ hơn **nguồn trạng thái engagement có thẩm quyền**.

**Cách xử lý:**

- Ngừng/không phê duyệt gia hạn khi beneficiary không còn eligible.
- Gỡ group/role ở target và chặn phiên/token theo chính sách.
- Nếu account còn phục vụ engagement khác, thu hồi riêng quyền PRJ-17.
- Kiểm negative access ở repository/API, không chỉ trạng thái ticket.
- Ghi lý do thu hồi là **engagement ended**, dù justification lịch sử từng hợp lệ.

**Bài học:** **Lý do yêu cầu có vòng đời**, không phải một tấm vé cho phép truy cập vĩnh viễn.

## 37. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao “Tôi cần quyền này để làm việc” chưa phải justification đủ tốt?

**Gợi ý:** Thiếu nhiệm vụ, action, resource, scope, thời hạn và căn cứ có thể kiểm chứng.

**Câu 2.** Manager đồng ý cấp quyền export dữ liệu nhạy cảm; có cần data owner duyệt nữa không?

**Gợi ý:** Tùy policy. Manager xác nhận nhiệm vụ chưa chắc có thẩm quyền với tài nguyên; cần kiểm approval matrix.

**Câu 3.** Lý do hợp lệ có cho phép bỏ qua SoD không?

**Gợi ý:** Không. SoD và policy có thể bắt buộc DENY hoặc yêu cầu kiểm soát bù trừ/approval riêng.

**Câu 4.** “Cần gấp” có phải lý do đủ để xin global admin không?

**Gợi ý:** Không. Cần incident/change, action, target, TTL, xác minh và audit theo luồng khẩn cấp.

**Câu 5.** Tại sao không nên cấp quyền cho Joiner bằng cách sao chép account người tiền nhiệm?

**Gợi ý:** Người cũ có thể tích lũy ngoại lệ/direct grants hoặc quyền đã hết căn cứ.

**Câu 6.** Cùng một permission đã được cấp từ hai role. Hết hạn request của một role có chắc làm mất permission không?

**Gợi ý:** Không. Cần xét grant provenance và quyền hiệu dụng từ role/ACL khác.

**Câu 7.** Một service account có cần justification dù không có người đăng nhập không?

**Gợi ý:** Có. Phải ghi workload identity, owner, mục đích, action, audience/resource và lifecycle.

**Câu 8.** Có nên yêu cầu người dùng dán toàn bộ hợp đồng vào phần lý do?

**Gợi ý:** Không nếu ID engagement và trạng thái từ VMS đã đủ; giảm dữ liệu cá nhân không cần thiết.

**Câu 9.** Một request được APPROVED nhưng ứng dụng chưa cấp quyền. Có thể thông báo đã hoàn tất không?

**Gợi ý:** Chưa. Cần provisioning và readback.

**Câu 10.** Grant vừa hết TTL nhưng phiên database admin vẫn chạy. Đã thu hồi hoàn toàn chưa?

**Gợi ý:** Chưa nếu quyền thực tế còn được sử dụng trái policy; phải xử lý session/token tại target.

**Câu 11.** Một người Mover xin giữ quyền cũ “để tiện bàn giao”. Cần những gì?

**Gợi ý:** Task bàn giao, giới hạn action/resource, owner, TTL, SoD và readback sau hết hạn.

**Câu 12.** Cần làm gì nếu free-text justification chứa mật khẩu hoặc API key?

**Gợi ý:** Hạn chế lộ, xử lý theo quy trình bảo mật/secret incident, không lan truyền vào log; thay bằng tham chiếu công việc.

## 38. Checklist đánh giá một Access Request justification

- [ ] **Nhiệm vụ:** Đã mô tả mục tiêu nghiệp vụ có thể kiểm chứng?
- [ ] **Đúng chủ thể:** Requester và beneficiary được xác định; account mapping đáng tin?
- [ ] **Eligibility:** HR/VMS/role catalog xác nhận engagement, vị trí và mốc hiệu lực?
- [ ] **Permission:** Action/role cần xin rõ ràng và phù hợp nhiệm vụ?
- [ ] **Resource:** Có ứng dụng, tenant, project/environment và dữ liệu trong phạm vi?
- [ ] **Least privilege:** Không yêu cầu export/delete/admin nếu chỉ cần read?
- [ ] **Gap:** Đã nêu vì sao quyền sẵn có chưa đủ?
- [ ] **Time:** Có khoảng hiệu lực hoặc điều kiện kết thúc/thu hồi rõ?
- [ ] **Evidence:** Ticket, assignment, owner hoặc change được đối chiếu nguồn đáng tin?
- [ ] **Approval:** Manager/data owner/security đúng thẩm quyền và không tự duyệt trái policy?
- [ ] **SoD:** Có kiểm xung đột quyền hiện hữu, cả direct grant và role kế thừa?
- [ ] **Risk:** Mức dữ liệu/đặc quyền được đánh giá bởi hệ thống/owner, không do người gửi tự chọn?
- [ ] **JIT:** Nếu quyền đặc quyền/tạm thời, đã giới hạn TTL, session và hành động?
- [ ] **RBAC/ABAC:** Role/attribute/resource scoping có thể thực thi ở target/API?
- [ ] **Joiner:** Không clone quyền người cũ và không cấp trước mốc hiệu lực?
- [ ] **Mover:** Có kế hoạch gỡ quyền cũ, xử lý ngoại lệ bàn giao và nhiều engagement?
- [ ] **Leaver:** Lý do cũ không được dùng để kéo dài quyền sau khi engagement kết thúc?
- [ ] **Service account:** Workload có owner, mục đích, credential lifecycle và scope độc lập với nhân viên?
- [ ] **Privacy:** Không dán mật khẩu, token, hồ sơ HR/hợp đồng hoặc dữ liệu nhạy cảm thừa?
- [ ] **Workflow integrity:** Free-text không được tự điều khiển approval/risk/grant state?
- [ ] **Provisioning:** SCIM/API hoặc connector có khả năng cấp đúng scope được duyệt?
- [ ] **Readback:** Đã kiểm target role, ACL và quyền hiệu dụng, cả negative cases?
- [ ] **Audit:** Lưu lý do theo version, nguồn bằng chứng, approver, policy và mốc?
- [ ] **Expiry/review:** Có trigger theo thời gian, dự án, Mover/Leaver hoặc revoke approval?
- [ ] **Exceptions:** Mọi phần chưa xác minh có owner, hạn xử lý và biện pháp bù trừ?
- [ ] **Không đánh đồng:** APPROVED ≠ PROVISIONED ≠ ACTIVE_VERIFIED ≠ REVOKED_VERIFIED?

## 39. Kết luận

**Lý do yêu cầu là cầu nối giữa công việc thực tế và quyết định cấp quyền trong IAM.** Một justification tốt không nhất thiết dài, nhưng phải nêu **nhiệm vụ hợp lệ, hành động cần thiết, tài nguyên/phạm vi cụ thể, thời hạn, nguồn xác minh và điều kiện kết thúc**, để người duyệt và hệ thống có thể đánh giá theo **least privilege, SoD và policy**.

Trong thực hành, justification **không tự tạo quyền**. **IdP/SSO** xác lập danh tính; **IAM/IGA** quản trị role và vòng đời; **SCIM/API** chuyển thay đổi đến ứng dụng; **RBAC/ABAC** quyết định quyền trên tài nguyên; **PAM/PIM** kiểm soát đặc quyền; **kiểm toán và readback** xác minh kết quả. Với **Joiner**, lý do gắn với nhiệm vụ ban đầu; **Mover**, lý do mới phải đi cùng thu hồi quyền cũ; **Leaver**, lý do trước đây không còn đủ căn cứ để giữ quyền; **service account** cần owner và mục đích kỹ thuật riêng.

**Chỉ khi lý do được kiểm chứng, grant được cấp đúng scope và thời hạn, rồi được thu hồi có bằng chứng khi nhu cầu hết hiệu lực, Access Request mới thật sự hỗ trợ “đúng người, đúng quyền, đúng lúc” và giảm quyền truy cập tồn dư.**
