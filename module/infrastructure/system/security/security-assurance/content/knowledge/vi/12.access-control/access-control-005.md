# Role Review (Rà soát vai trò) trong kiểm soát truy cập và Security Assurance

## 1. Tại sao phải rà soát vai trò?

Một nền tảng SaaS quản lý hóa đơn có các vai trò **Viewer**, **Accountant**, **Billing Admin** và **Platform Admin**. Ban đầu, Viewer chỉ được xem hóa đơn thuộc tenant của mình. Sau vài đợt phát triển, nhóm kỹ thuật thêm quyền xuất báo cáo vào Viewer để triển khai nhanh. Một người dùng cũ có Viewer nhưng không còn phụ trách nghiệp vụ vẫn có thể tải dữ liệu số lượng lớn. Cùng lúc, tài khoản hỗ trợ kỹ thuật nhận quyền Billing Admin tạm thời nhưng không ai thu hồi.

Hệ thống vẫn có thể báo “100% người dùng đã được gán role”. Tuy nhiên, cách định nghĩa vai trò, quyền nằm trong vai trò và việc gán vai trò đều có thể không còn phù hợp.

**Role review (rà soát vai trò)** là hoạt động đánh giá có hệ thống xem các **vai trò truy cập**, **quyền mà vai trò cho phép** và **việc sử dụng/gán vai trò** có còn phù hợp với nhiệm vụ, nguyên tắc đặc quyền tối thiểu, phân tách trách nhiệm, phân loại dữ liệu và rủi ro hiện tại hay không.

Trong chương **Kiểm soát truy cập** của module **SECURITY_SECURITY_ASSURANCE**, role review phải được xem như một **security control có bằng chứng**. Mục tiêu của module là đánh giá có căn cứ rằng hệ thống đáp ứng mục tiêu bảo mật qua phân tích rủi ro, yêu cầu, controls, kiểm thử, audit, khắc phục và theo dõi liên tục. Vì vậy, một đợt role review không được đánh giá chỉ bằng việc “đã gửi email yêu cầu các trưởng nhóm xác nhận”.

Đợt review đáng tin cần trả lời:

1. **Role có còn cần thiết?** Mục đích nghiệp vụ, owner và phạm vi còn chính xác không?
2. **Role đang cấp quyền gì?** Kể cả quyền kế thừa, nhóm lồng nhau, quyền trực tiếp và các đường truy cập ngoài RBAC.
3. **Quyền có quá rộng không?** Có cho phép thao tác trái yêu cầu hoặc tạo xung đột nhiệm vụ không?
4. **Ai đang giữ role?** Người, tài khoản dịch vụ, vendor, tài khoản khẩn cấp và các định danh khác có phù hợp không?
5. **Bằng chứng nào cho thấy quyết định review đã được thực thi?** Quyền bị thu hồi, cấu hình hiệu lực, test và giám sát thay đổi đã được xác minh chưa?

> **Role review không chỉ là ký xác nhận danh sách tên vai trò.** Đó là đánh giá quan hệ **nhiệm vụ → vai trò → quyền hiệu lực → người/tài khoản sở hữu**, kèm quyết định, hành động và bằng chứng sau hành động.

## 2. Phân biệt các thuật ngữ quan trọng

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Identity / principal** | Danh tính của người hoặc thực thể được hệ thống xác thực. | Người dùng, service account, workload identity. |
| **Role** | Tập quyền hoặc khả năng truy cập được gom theo chức năng, tùy mô hình sản phẩm. | InvoiceViewer, TenantBillingAdmin. |
| **Permission / entitlement** | Khả năng thực hiện hành động lên tài nguyên hoặc tập tài nguyên. | READ_INVOICE, EXPORT_INVOICES, MODIFY_REFUND. |
| **Role assignment / membership** | Quan hệ giữa một identity và role, có thể qua nhóm. | Người dùng A thuộc nhóm kế toán được gán InvoiceEditor. |
| **Effective access** | Quyền **thực sự có hiệu lực** sau khi tính các đường cấp, kế thừa, điều kiện, giới hạn và deny. | A có quyền xuất do cả role và temporary grant. |
| **Role definition review** | Rà thiết kế role và tập quyền của nó có đúng mục tiêu/nguyên tắc không. | Viewer không được phép hoàn tiền. |
| **Access recertification / user access review** | Rà ai nên tiếp tục giữ quyền hoặc role trong kỳ. | Người chuyển bộ phận không còn cần BillingAdmin. |
| **Role mining / role engineering** | Phân tích quyền và nhiệm vụ để đề xuất, thiết kế hoặc tinh chỉnh role. | Tách BillingAdmin thành InvoiceEditor và RefundApprover. |
| **SoD – Separation of Duties** | Phân tách nhiệm vụ/đặc quyền có nguy cơ xung đột. | Người tạo hoàn tiền không đồng thời phê duyệt chính giao dịch đó. |
| **JML – Joiner, Mover, Leaver** | Quản lý quyền khi nhân sự vào, chuyển vị trí hoặc nghỉ việc. | Khi chuyển từ kế toán sang hỗ trợ, thu hồi quyền cũ. |
| **PAM / JIT / break-glass** | Quản lý truy cập đặc quyền, quyền được cấp đúng lúc, đường khẩn cấp. | Cấp quyền quản trị 30 phút sau phê duyệt, ghi audit. |

**Role review có hai phạm vi bổ trợ nhưng không giống nhau:**

- **Review role-to-permission:** role này **được quyền làm gì**, trên tài sản nào, theo điều kiện nào?
- **Review identity-to-role:** **ai được cấp role đó**, qua đường nào, còn lý do hợp lệ không?

Tổ chức có thể thực hiện các đợt khác nhau cho hai mục tiêu, nhưng nếu chỉ làm một phía sẽ để lại khoảng trống. Role được thiết kế tối thiểu nhưng cấp cho mọi người vẫn rủi ro; role gán đúng người nhưng bản thân role chứa quyền quá rộng cũng rủi ro.

## 3. Role review nằm ở đâu trong mô hình kiểm soát truy cập?

### Authentication không phải authorization

**Authentication** xác minh danh tính theo cơ chế tin cậy. **Authorization** quyết định danh tính ấy được thực hiện hành động nào đối với tài nguyên nào. Role là một trong các đầu vào cho authorization, không phải bằng chứng cuối cùng về quyền hợp lệ.

Ví dụ token hợp lệ mang role InvoiceViewer chưa đủ chứng minh người dùng được đọc **một hóa đơn bất kỳ**: Invoice Service còn phải kiểm tra tenant, chủ sở hữu dữ liệu, trạng thái đối tượng hoặc các điều kiện khác.

### RBAC, ABAC, ReBAC và quyền trực tiếp

| Mô hình | Cách quyết định quyền | Điều role review cần nhớ |
| --- | --- | --- |
| **RBAC – Role-Based Access Control** | Quyền được gắn với role; identity nhận role. | Phải rà role definition, membership, role hierarchy và tác động permission mới. |
| **ABAC – Attribute-Based Access Control** | Chính sách dựa trên thuộc tính principal, tài nguyên, hành động và ngữ cảnh. | Chỉ review role là chưa đủ; phải xét thuộc tính và policy conditions. |
| **ReBAC – Relationship-Based Access Control** | Quyền dựa trên quan hệ giữa identity và đối tượng/nhóm. | Rà các đường quan hệ, kế thừa và phạm vi object. |
| **Direct grants / ACL** | Cấp quyền trực tiếp cho identity hoặc object. | Quyền này có thể tồn tại dù mọi role assignment đều được duyệt. |
| **PAM/JIT** | Quyền có điều kiện, tạm thời hoặc được nâng khi có nhu cầu. | Rà quyền nền, khả năng kích hoạt, phê duyệt, thời hạn và audit. |

Một hệ thống thường **kết hợp nhiều mô hình**. Ví dụ role BillingOperator cho phép chức năng sửa hóa đơn, nhưng ABAC giới hạn hóa đơn thuộc tenant và trạng thái đang xử lý, trong khi database dùng service account có quyền SQL rộng. Nếu chỉ review role trên giao diện IAM, sẽ không đánh giá đầy đủ quyền của luồng dữ liệu.

### Nguyên tắc thiết kế

- **Least privilege:** chỉ cấp quyền cần để thực hiện nhiệm vụ đã được xác định.
- **Need-to-know / purpose limitation:** chỉ tiếp cận dữ liệu phù hợp mục đích và nhiệm vụ, khi được áp dụng.
- **Default deny:** khi thiếu căn cứ cấp quyền, quyết định an toàn mặc định là từ chối.
- **Separation of duties:** giảm nguy cơ một chủ thể thực hiện trọn chuỗi hành vi có xung đột.
- **Accountability:** biết ai được cấp, ai duyệt, khi nào, tại sao và quyền thực tế đã thay đổi thế nào.
- **Time-bound access:** quyền tạm nên có điều kiện hết hạn, gia hạn và review rõ ràng.

## 4. Vẽ quan hệ quyền trước khi review

Trong hệ thống đa dịch vụ, quyền thực tế thường đến từ nhiều lớp:

~~~mermaid
flowchart TD
    A["Identity: nhân sự / service / đối tác"] --> B["IdP group / direct assignment"]
    B --> C["Ứng dụng role / cloud role"]
    C --> D["Permission / entitlement"]
    D --> E["Authorization policy + tenant/object context"]
    E --> F["Effective action trên tài nguyên"]
    G["Temporary grant / PAM / break-glass"] --> C
    H["Direct ACL / delegation / nested group"] --> D
    I["Deny rules / conditions / policy changes"] --> E
    J["Evidence: inventory, tests, logs"] -. "Đối chiếu" .-> F
~~~

Sơ đồ cho thấy một bảng chứa cột “user_id, role_name” có thể không phản ánh toàn bộ quyền. Khi chuẩn bị review, cần xác định rõ:

1. **Nguồn định danh:** IdP, HR, local account, workload identity hoặc bên thứ ba.
2. **Nguồn role:** role database ứng dụng, group trong IdP, cloud IAM, PAM, Kubernetes RBAC hoặc hệ thống khác.
3. **Nguồn permission:** danh mục API, chính sách IAM, quyền SQL, object ACL, resource policy và quan hệ.
4. **Cách kế thừa:** nested groups, role hierarchy, role mapping, delegation, direct grants.
5. **Điều kiện hiệu lực:** tenant, môi trường, thời gian, thiết bị, mục đích, trạng thái giao dịch và chính sách deny.
6. **Đường truy cập thay thế:** export, batch, admin API, webhook, job nền, break-glass, tài khoản máy.

**Điểm mấu chốt:** cần hiểu **effective access** bằng cách phân tích các đường cấp quyền tương ứng với hệ thống thật. Không có một phép hợp nhất quyền đơn giản áp dụng mọi engine; có thể tồn tại **explicit deny, permission boundaries, session policy hoặc điều kiện đối tượng** khiến quyền cuối cùng khác với tổng quyền trên các role.

## 5. Thiết lập inventory các vai trò

Role inventory là điểm bắt đầu để tránh bỏ sót role cũ, quyền kế thừa và nhóm không có người quản lý. Mỗi role nên có metadata:

| Trường | Vai trò |
| --- | --- |
| **role_id / name** | ID ổn định; tên theo nghiệp vụ/công nghệ có quy ước. |
| **business purpose** | Tại sao role cần tồn tại, hoạt động hợp lệ nào được hỗ trợ. |
| **business owner / role owner** | Ai xác nhận nhu cầu và chịu trách nhiệm về quyền được thiết kế. |
| **system/control owner** | Ai duy trì kỹ thuật và chịu trách nhiệm vận hành kiểm soát. |
| **data classification / scope** | Mức độ nhạy cảm tài sản, tenant, vùng, môi trường liên quan. |
| **permissions / effective boundaries** | Tập quyền, resource scope, hierarchy, direct grants và điều kiện. |
| **assigned principals** | Danh tính người, hệ thống, vendor hoặc nhóm nhận role. |
| **privilege tier** | Vai trò thông thường, nhạy cảm, đặc quyền hay khẩn cấp theo rubric tổ chức. |
| **SoD constraints** | Cặp role/quyền không được đồng thời có, hoặc điều kiện kiểm soát bù đắp. |
| **approval rule** | Ai được cấp mới, gia hạn hoặc thay đổi quyền. |
| **expiry / review frequency** | Khi nào hết hạn, cần kiểm tra lại hoặc kích hoạt review. |
| **version / last reviewed** | Phiên bản role definition, lần review, kết quả và evidence. |

### Trạng thái cần xử lý trong inventory

- **Orphan role:** không có owner rõ, nhưng vẫn chứa permission hoặc có người dùng.
- **Unused role:** chưa thấy active assignments/use trong phạm vi đo; cần xác minh trước khi xóa.
- **Duplicate/overlapping roles:** hai role có tập quyền gần giống nhau nhưng owner và mục đích khác.
- **Overprivileged role:** chứa quyền không cần cho nhiệm vụ của đa số người được gán.
- **Role with stale purpose:** role được tạo cho dự án đã kết thúc, hệ thống đã thay đổi.
- **Role with toxic combination:** quyền tạo và duyệt một giao dịch nhạy cảm trong cùng ngữ cảnh.
- **Shadow grants:** quyền direct, inherited hoặc bypass không xuất hiện trong danh sách gán role chính.

**Không tự xóa một role chỉ vì 90 ngày không có sự kiện sử dụng**: log có thể thiếu, một chức năng có thể được dùng theo mùa hoặc role chỉ dành cho khẩn cấp. Cần xác minh mục đích, ảnh hưởng và phương án khôi phục trước khi vô hiệu hóa.

## 6. Rà soát role-to-permission: quyền có còn đúng không?

Đối với mỗi role, reviewer phải hiểu **tập thao tác và phạm vi tài nguyên được cho phép**, sau đó so với nhu cầu nghiệp vụ thực tế.

### Ma trận quyền minh họa cho hệ thống hóa đơn

Giả sử một hệ thống quản lý hóa đơn có các thao tác sau:

| Role | Xem hóa đơn tenant | Sửa nháp | Xuất báo cáo | Tạo yêu cầu hoàn tiền | Duyệt hoàn tiền | Quản lý quyền |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| **InvoiceViewer** | Có | Không | Không | Không | Không | Không |
| **InvoiceEditor** | Có | Có | Không | Không | Không | Không |
| **InvoiceAnalyst** | Có | Không | Có, có giới hạn | Không | Không | Không |
| **RefundRequester** | Có, theo phạm vi | Không | Không | Có | Không | Không |
| **RefundApprover** | Có, theo phạm vi | Không | Không | Không | Có | Không |
| **TenantAccessAdmin** | Theo nhiệm vụ quản trị | Không mặc định | Không mặc định | Không | Không | Có, giới hạn tenant |

Ma trận này **là thiết kế giả định để giảng dạy**, không phải tiêu chuẩn chuẩn hóa cho mọi ứng dụng. Các cột “Có” vẫn cần giới hạn tenant, đối tượng, điều kiện nghiệp vụ và loại dữ liệu; role không được mặc nhiên thao tác trên tài nguyên của mọi khách hàng.

### Các câu hỏi khi review tập quyền

1. Quyền có **trực tiếp phục vụ nhiệm vụ đã được duyệt** không?
2. Có quyền mới được thêm sau lần review trước mà owner chưa chấp thuận?
3. Quyền có quá rộng về **read/write/delete/export/admin**, môi trường hoặc dữ liệu?
4. Có quyền hiếm gặp nên tách thành **JIT elevation** thay vì cấp vĩnh viễn?
5. Có thể tách role quá rộng thành các role chuyên biệt?
6. Role có tạo hoặc cho phép **SoD conflict** khi kết hợp với role khác?
7. Có đường batch/job, service account hoặc export làm quyền hiệu lực lớn hơn ma trận?
8. Có quy tắc quyền chỉ dựa vào hiển thị UI mà không được kiểm tra ở server?

### Chỉ review permission name là chưa đủ

Một quyền EXPORT_REPORT nghe ít nguy hiểm, nhưng có thể cho phép tải **toàn bộ dữ liệu khách hàng của nhiều tenant** nếu không có kiểm soát phạm vi. Reviewer cần biết **permission semantics**: action, resource types, object-level constraints, volume, delegations, effects và điều kiện nghiệp vụ. Mức độ nhạy cảm của quyền phải dựa vào hậu quả thực tế chứ không chỉ nhãn.

## 7. Rà soát identity-to-role: ai còn cần giữ vai trò?

Sau khi xác nhận role definition, tổ chức cần kiểm tra các identity đang nhận role, gồm:

- Nhân viên đang làm đúng chức năng.
- Nhân viên đã **chuyển nhóm, đổi chức vụ hoặc nghỉ việc**.
- Nhà thầu, đối tác hoặc vendor có hợp đồng và thời hạn truy cập.
- Tài khoản kỹ thuật và service account có owner, nhiệm vụ và vòng đời rõ ràng.
- Tài khoản break-glass, tài khoản hỗ trợ và các quyền tạm.
- Nhóm IAM/IdP lồng nhau và quyền cấp trực tiếp ngoài hệ thống cấp role chuẩn.

### Một quyết định review phải có lý do

| Decision | Khi nào dùng | Evidence cần có |
| --- | --- | --- |
| **Keep** | Identity tiếp tục cần role đúng phạm vi. | Business justification, owner/approver, ngày review, effective access. |
| **Revoke** | Không còn nhu cầu hoặc quyền không phù hợp. | Ticket/approval, hành động thu hồi và kiểm tra quyền không còn hiệu lực. |
| **Modify** | Cần quyền hẹp hơn hoặc đổi role. | Ma trận quyền mới, change record, verification. |
| **Suspend pending investigation** | Chưa rõ chủ thể hoặc có nguy cơ nghiêm trọng cần kiểm tra. | Hồ sơ điều tra, biện pháp tạm, người quyết định và thời hạn. |
| **Exception** | Chấp nhận tạm theo quy trình và điều kiện hợp lệ. | Risk decision, biện pháp bù đắp, scope, expiry, owner. |
| **Needs information / pending** | Chưa đủ bằng chứng để duyệt hoặc từ chối. | Vấn đề cần làm rõ, deadline và escalation. |

Không nên có nút mặc định “Approve All” mà không yêu cầu reviewer xem quyền hoặc lý do: dễ hình thành **rubber-stamp review**. Các quyết định hàng loạt có thể hợp lệ khi có tiêu chí rõ, bằng chứng tổng hợp đầy đủ và điều kiện kiểm tra được, nhưng không được bỏ các tài khoản đặc quyền hoặc ngoại lệ vì tiện thao tác.

### Quyền gián tiếp vẫn cần rà soát

Một người không được gán trực tiếp BillingAdmin nhưng thuộc group FinanceOps; group này được gắn BillingAdmin tại ứng dụng. Nếu chỉ xuất bảng direct role assignments sẽ bỏ sót quyền thực tế. Inventory phải giải quyết **nested group expansion và role mapping**, đồng thời ghi đường cấp quyền để reviewer biết cần thu hồi ở đâu.

## 8. Separation of Duties (SoD) và tổ hợp quyền độc hại

**SoD** nhằm giảm nguy cơ một người hoặc một nhóm liên quan có thể **tạo, phê duyệt và hoàn tất** một hành động nhạy cảm mà không có đối soát độc lập. SoD có thể dựa trên role, permission, giao dịch hoặc ngữ cảnh.

### Hai dạng xung đột thường gặp

**Static SoD:** các role không được cấp đồng thời cho cùng một principal trong một phạm vi, ví dụ vai trò quản trị quyền và vai trò tự phê duyệt quyền của chính mình.

**Dynamic SoD:** principal có thể có nhiều khả năng theo công việc nhưng **không được thực hiện các bước xung đột trên cùng giao dịch**, ví dụ không được duyệt một yêu cầu hoàn tiền do chính mình tạo.

### Ví dụ nghiệp vụ hoàn tiền

~~~mermaid
flowchart LR
    A["Refund request"] --> B["Requester identity"]
    B --> C["Validate transaction and limit"]
    C --> D["Approver identity"]
    D --> E{"Approver khác requester và đủ quyền?"}
    E -- "Không" --> F["Reject / escalate / alternate workflow"]
    E -- "Có" --> G["Approve + audit decision"]
    G --> H["Execute refund"]
    H --> I["Reconciliation / monitoring"]
~~~

Nếu role RefundRequester và RefundApprover đều được gán cho cùng một người, hệ thống cần xét **static policy** đã cấm điều đó hay chưa. Ngay cả khi có hai role riêng, vẫn cần **transaction-level check** nếu quy tắc yêu cầu không cho cùng người duyệt chính giao dịch mình tạo.

### SoD không chỉ là hai cột trong bảng role

Các tình huống có thể gây xung đột:

- Người **phê duyệt quyền** có khả năng tự cấp role đặc quyền.
- Người **tạo vendor** đồng thời có quyền thay tài khoản nhận tiền và phê duyệt thanh toán.
- Người **triển khai mã** có quyền tắt toàn bộ kiểm thử/monitoring và thay audit log.
- Một service account có cả quyền **đọc dữ liệu nhạy cảm và cấp quyền public** cho nơi lưu.

Biện pháp có thể gồm tách vai trò, xác nhận độc lập, kiểm tra trên từng giao dịch, approval cấp cao, giới hạn JIT và monitoring. Tuy nhiên, **monitoring không tự loại bỏ xung đột**; nếu phải dùng compensating control cần đánh giá và phê duyệt phù hợp.

## 9. Quy trình role review end-to-end

Một đợt review nên có **scope, population, reviewer, phương pháp, thời hạn, dấu vết quyết định và phép kiểm tra sau thay đổi**.

~~~mermaid
flowchart TD
    A["Risk + policy + review trigger"] --> B["Chốt scope, criteria, owner"]
    B --> C["Thu inventory: identities, roles, permissions, groups"]
    C --> D["Đối chiếu HR, hệ thống, effective access"]
    D --> E["Role definition + SoD review"]
    E --> F["Membership / access recertification"]
    F --> G{"Quyết định"}
    G -- "Keep" --> H["Ghi reason và approval"]
    G -- "Modify / Revoke" --> I["Thực thi thay đổi"]
    G -- "Exception / Pending" --> J["Escalation + risk decision + deadline"]
    I --> K["Re-query effective access + negative tests"]
    H --> L["Evidence review và closure"]
    K --> L
    J --> L
    L --> M["Monitor drift, JML, expiry, change"]
    M --> C
~~~

### Bước 1 — Chốt phạm vi và tiêu chí

Ghi hệ thống, môi trường, tenant, loại role, mức đặc quyền, kỳ review và nghĩa vụ. Có thể ưu tiên các role quản trị, xuất dữ liệu nhạy cảm, phê duyệt giao dịch, thay IAM hoặc tắt security controls. **Review theo rủi ro**, không mặc định cùng chu kỳ cho mọi quyền.

### Bước 2 — Thu thập population đáng tin

Xuất identity/role/group/permission từ các nguồn hiệu lực. Đối chiếu HR, IAM, tài khoản local, vendor registry, service identity inventory và dấu vết JIT. Kiểm tra phân trang API, tài khoản không hoạt động, nguồn không kết nối và nhóm có quan hệ lồng nhau.

### Bước 3 — Đánh giá thiết kế của role

Business/role owner xác nhận mục đích, tập quyền, yêu cầu SoD, độ nhạy dữ liệu và điều kiện cấp mới. Security review các role đặc quyền hoặc bất thường. Ghi những role phải tách, thu hẹp, ngừng sử dụng hoặc đổi owner.

### Bước 4 — Rà identity-to-role

Manager hoặc chủ sở hữu chức năng xác nhận ai cần role; người phụ trách dữ liệu/hệ thống tham vấn khi quyền liên quan dữ liệu nhạy cảm. Reviewer phải nhìn thấy **quyền thực tế, lý do cấp, ngày cuối sử dụng có ngữ cảnh và đường gán**, không chỉ tên người.

### Bước 5 — Quyết định có thẩm quyền

Với từng dòng, ghi Keep/Modify/Revoke/Exception/Pending, lý do, người quyết định và thời điểm. Xung đột SoD và quyền đặc biệt cần xử lý theo mức rủi ro và quy trình approval tương ứng. Không để một người **tự duyệt quyền của mình** nếu chính sách yêu cầu người phê duyệt độc lập.

### Bước 6 — Thực thi và xác minh

Đội IAM/service thực hiện thay đổi, có ticket và record. **Re-query effective access** sau khi quyền bị thu hồi; thử các đường bị rủi ro nếu có thể. Chú ý session/token còn sống, group sync chậm, cache quyền, credentials tĩnh, quyền ở SaaS phụ và service accounts.

### Bước 7 — Đóng và theo dõi

Assessor đối chiếu population ban đầu với decisions và trạng thái cuối; giữ danh sách exception còn hiệu lực, remediation quá hạn và phần chưa thể xác minh. Đánh giá residual risk; thiết lập triggers khi role definition, người dùng, hệ thống hoặc dữ liệu thay đổi.

## 10. Phân quyền thực tế: nested groups, thừa kế và đường bypass

Một hệ thống có thể có các đường gán:

~~~text
Employee A
   ├─ HR job = Finance Analyst
   ├─ IdP group: Finance
   │     └─ Nested group: BillingOps
   │           └─ App role: BillingAdmin
   ├─ Direct grant: EXPORT_INVOICES
   └─ Temporary PAM grant: CloudReadOnly (time-bound)

App role: BillingAdmin
   ├─ READ_INVOICES
   ├─ EDIT_INVOICES
   └─ APPROVE_REFUND (unexpected)
~~~

Nếu bảng IAM trực tiếp chỉ liệt kê “Employee A → Finance”, reviewer có thể bỏ sót **BillingAdmin qua nhóm lồng nhau**, quyền export trực tiếp và PAM. Cần truy ra cả **đường tới permission** để biết sửa chỗ nào.

### Thứ tự ưu tiên của policy engine

Không được giả định “quyền cuối cùng bằng hợp của mọi role”. Tùy công nghệ, explicit deny, permission boundary, resource policy, điều kiện thời gian, session scope, tenant và authorization ở tầng ứng dụng có thể tạo kết quả khác. Một role có quyền ghi ở database nhưng API có thể chỉ đọc; ngược lại một endpoint nội bộ bỏ kiểm tra role có thể dùng service account rộng và tạo đường bypass.

Để đánh giá thực tế:

1. **Inspect policy/config:** nhận diện mọi nguồn cấp quyền và điều kiện.
2. **Resolve identities and mappings:** group nesting, role hierarchy, delegation, direct grants.
3. **Evaluate effective policy:** theo engine và resource scope tương ứng.
4. **Verify behavior:** positive/negative tests trên các thao tác quan trọng.
5. **Compare expected vs observed:** ghi sai lệch, owner và phương án khắc phục.

### Token và cache sau thu hồi

Thu hồi membership trong IdP không bảo đảm mọi token/session đang tồn tại lập tức mất hiệu lực. Hiệu lực tùy kiến trúc: ứng dụng có tra cứu trực tuyến, access token sống bao lâu, có cơ chế revocation, cache policy và thời điểm đồng bộ. **Tiêu chí của review cần xác định thời hạn vô hiệu hóa quyền** phù hợp với rủi ro, rồi kiểm tra thực tế.

## 11. Tài khoản đặc quyền, workload và break-glass

Role review không được chỉ tập trung vào nhân viên có giao diện đăng nhập. Nhiều quyền nhạy cảm nằm ở **service account, workload identity, automation, integration key, cluster role và tài khoản vận hành khẩn cấp**.

| Loại danh tính | Câu hỏi review trọng tâm | Evidence hữu ích |
| --- | --- | --- |
| **Human privileged account** | Còn cần quyền admin? Có JIT, MFA, quản lý phiên, SoD theo chính sách? | Assignment, approval, PAM logs, sign-in tests, access review. |
| **Service account** | Chức năng còn tồn tại? Tài nguyên và hành động có quá rộng? Có owner? | Workload inventory, IAM policy, usage logs, negative permission tests. |
| **Cloud workload identity** | Role ở account/project/region nào, cross-account trust ra sao? | Effective policy, trust configuration, service deployment identity. |
| **CI/CD identity** | Có quyền deploy, thay secret, tắt controls hoặc phát hành sang production? | Pipeline permissions, OIDC/workload trust, audit deploy. |
| **Third-party/vendor account** | Hợp đồng, mục đích, dữ liệu, hạn truy cập còn hiệu lực? | Vendor ownership, approval, expiry, access logs. |
| **Break-glass account** | Ai có quyền dùng, giữ thông tin xác thực thế nào, có log/hậu kiểm không? | Vault/PAM config, review quyền, test theo quy trình an toàn. |

### Hai sai lầm đặc biệt nguy hiểm

**Đếm tài khoản không còn sử dụng rồi xóa hàng loạt:** Một workload chạy theo tháng/quý có thể chỉ phát sinh hoạt động hiếm. Phải xác nhận owner, dependency và kế hoạch chuyển quyền.

**Cho rằng tài khoản máy không cần review:** Service account có thể đọc hàng triệu bản ghi, vượt qua role cấp người dùng hoặc thực hiện thay đổi control plane. Nó cần review **theo rủi ro và quyền hiệu lực**, dù không có người đăng nhập tương tác.

## 12. Role design anti-patterns và cách xử lý

| Anti-pattern | Hậu quả có thể gặp | Hướng khắc phục có bằng chứng |
| --- | --- | --- |
| **Super-role** gom quyền đọc, sửa, export, admin. | Blast radius lớn khi tài khoản bị chiếm. | Tách theo nhiệm vụ, test quyền được phép/cấm và review assignments. |
| **Role explosion** tạo quá nhiều role gần giống nhau. | Khó hiểu, review mơ hồ, dễ chồng quyền. | Role engineering, chuẩn hóa naming/purpose, vẫn giữ khác biệt nghiệp vụ cần thiết. |
| **Role không owner** | Không ai duyệt thay đổi hoặc quyết định giữ/xóa. | Chỉ định owner theo governance; rà lại tập quyền và người dùng. |
| **Default broad access** cho người mới. | Quyền vượt nhu cầu ngay sau onboarding. | Role mặc định tối thiểu, cấp thêm theo yêu cầu được duyệt. |
| **Permanent emergency privilege** | Quyền tạm trở thành đặc quyền lâu dài. | Thời hạn rõ, JIT/PAM, giám sát và review sau sử dụng. |
| **UI-only authorization** | API/batch có thể bỏ qua hạn chế của giao diện. | Enforcement phía server, integration tests theo hành động và object. |
| **Hard-coded role names** trong nhiều dịch vụ. | Đổi role ở IAM không phản ánh đúng logic nghiệp vụ. | Chuẩn hóa permission contracts và test integration; tránh logic role rời rạc. |
| **Nested group không kiểm soát** | Người review không biết permission nhận gián tiếp. | Expand membership, cảnh báo thay đổi role/group có ảnh hưởng lớn. |
| **Role review trên snapshot duy nhất** | Bỏ qua quyền tạm, tài khoản bị cấp rồi thu hồi giữa kỳ. | Kết hợp snapshot với grant/revoke history và JML audit. |
| **Approval by same requestor** | Thiếu độc lập; nguy cơ tự cấp quyền. | SoD trong workflow, người duyệt theo thẩm quyền. |
| **Không kiểm tra hoàn tất sau revoke** | Token, cache, SaaS phụ vẫn có quyền. | Effective access recheck và negative tests. |

### Khi nào cần tái thiết kế role?

Nếu vai trò có số permission không sử dụng lớn, quyền thường xuyên phải cấp ngoại lệ, xung đột SoD lặp lại hoặc người dùng khó xác nhận nhu cầu, nên làm **role engineering**: quan sát nhiệm vụ thực, xây permission catalog, nhóm quyền hợp lý, đối chiếu SoD, thử với các nhóm người dùng và lập kế hoạch migration/rollback.

**Không để thuật toán role mining tự quyết định quyền được phép.** Mẫu quyền hiện tại có thể phản ánh sai lệch lịch sử; các role được đề xuất vẫn cần owner và security review.

## 13. Ví dụ thực hành: rà soát roles trong Invoice SaaS đa tenant

### Bối cảnh

Ứng dụng có 30 doanh nghiệp sử dụng, mỗi doanh nghiệp là tenant độc lập. Một số thành viên thuộc nhóm hỗ trợ nội bộ có quyền hỗ trợ khách hàng. Đội kỹ thuật thêm tính năng export hóa đơn và nâng cấp phân quyền mà chưa kiểm tra lại các roles cũ.

**Security objective:** quyền đọc, sửa và xuất hóa đơn phải phù hợp chức năng, tenant và dữ liệu được phép; vai trò không được tạo đường cập nhật hoặc phê duyệt giao dịch vượt thẩm quyền.

### Bước 1 — Thu inventory

Đội review thu:

- Role definitions ở Invoice Service theo release và tenant.
- Bảng identity-to-role assignments, IdP group mappings và direct grants.
- Danh sách entitlement/API actions, export jobs và quyền worker.
- Role owners, business justifications, lịch sử cấp quyền và dữ liệu chuyển bộ phận.
- Kết quả kiểm thử authz gần nhất, access/audit log trong phạm vi và các ngoại lệ.

### Bước 2 — Phát hiện

| Finding | Dấu hiệu | Đánh giá ban đầu |
| --- | --- | --- |
| **RR-01** | Role InvoiceViewer mới được thêm EXPORT_ALL nhưng owner chưa duyệt. | Role definition drift; có nguy cơ disclosure diện rộng. |
| **RR-02** | Nhân viên support đã chuyển dự án vẫn giữ TenantBillingAdmin qua nested group. | Stale indirect assignment; cần kiểm tra quyền hiệu lực. |
| **RR-03** | RefundRequester và RefundApprover cùng gán cho một identity ở một tenant. | SoD conflict; cần xét kiểm tra trên từng giao dịch. |
| **RR-04** | Service account export có quyền đọc toàn bộ tenant từ database. | Quyền kỹ thuật vượt nhu cầu; cần thiết kế phân quyền job/tenant. |
| **RR-05** | Reviewer có screenshot roles nhưng không có lịch sử cấp/thu hồi trong quý. | Evidence gap về operating effectiveness theo thời kỳ. |

### Bước 3 — Quyết định xử lý

Role owner cân nhắc tách chức năng export khỏi Viewer. IAM owner thu hồi assignment không còn nhu cầu ở **đúng nguồn nhóm cấp quyền**; nhóm ứng dụng kiểm tra quyền trên endpoint. Product/business owner định nghĩa SoD cho refund theo workflow. Đội platform đánh giá giới hạn service account; data owner xác định hậu quả nếu xuất dữ liệu sai tenant.

### Bước 4 — Xác minh thay đổi

| Kịch bản test | Kỳ vọng |
| --- | --- |
| Viewer chỉ đọc hóa đơn đúng tenant. | Read hợp lệ, không xuất/sửa nếu không có quyền bổ sung. |
| Viewer cố export nhiều hóa đơn. | Bị từ chối theo policy; không tạo file hoặc job trái phép. |
| Tenant A cố truy cập hóa đơn tenant B. | Bị từ chối trên API và đường export/worker trong phạm vi. |
| Nhân viên support đã bị thu hồi role thử mở chức năng quản trị. | Không còn effective access; kiểm tra token/session theo yêu cầu. |
| Người yêu cầu hoàn tiền tự phê duyệt giao dịch mình tạo. | Bị từ chối nếu transaction-level SoD yêu cầu. |
| Service account nhận job thiếu tenant context. | Không đọc/xuất dữ liệu không được cấp theo chính sách. |

### Bước 5 — Kết luận giới hạn

Chỉ khi role definitions được điều chỉnh, assignments được thu hồi và tests đạt trên đúng release/môi trường, mới có cơ sở nói **các sai lệch đã xử lý trong phạm vi kiểm tra**. Việc role review hoàn tất không chứng minh toàn bộ ứng dụng không còn lỗ hổng phân quyền ở các đường chưa kiểm tra.

## 14. Ví dụ kiểm thử Java/Spring Security theo role và object

Trong Java/Spring Security, role có thể là cách biểu diễn một nhóm quyền, nhưng **method security hay annotation ở controller không thay thế kiểm tra ownership/tenant** nếu chính sách yêu cầu theo đối tượng.

### Ví dụ logic theo quyền và tenant

Đoạn code sau là minh họa, các interface và repository phụ thuộc vào ứng dụng thực:

~~~java
@Service
public class InvoiceAccessService {
    private final InvoiceRepository repository;

    public InvoiceAccessService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('INVOICE_READ')")
    public InvoiceView read(UUID id, VerifiedPrincipal principal) {
        String verifiedTenant = principal.tenantId();
        if (verifiedTenant == null) {
            throw new AccessDeniedException("Tenant required");
        }

        Invoice entity = repository
                .findByIdAndTenantId(id, verifiedTenant)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));
        return InvoiceView.fromAuthorized(entity);
    }
}
~~~

**Điều kiện an toàn quan trọng:** VerifiedPrincipal phải được ràng buộc với **authentication được xác minh trong security context**, không phải một đối tượng do request body/header của client tùy ý tạo. Với thiết kế thực tế, nên tránh để caller có thể tự truyền principal không đáng tin; có thể lấy principal từ SecurityContext hoặc lớp adapter được kiểm chứng.

Đoạn minh họa yêu cầu method security thực sự được bật và được gọi qua proxy/cơ chế áp dụng Spring Security; self-invocation và cấu hình sai có thể khiến annotation không có tác dụng mong muốn. Cần kiểm thử cả enforcement ở API và tầng service.

### Bảng test cho role review

| Test ID | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| **ROLE-01** | User có INVOICE_READ, tenant A, đọc invoice A. | Có dữ liệu A trong phạm vi cho phép. |
| **ROLE-02** | User có INVOICE_READ, tenant A, đọc invoice B. | Không trả dữ liệu B dù biết ID. |
| **ROLE-03** | User bị thu hồi INVOICE_READ, gọi read. | Bị từ chối sau khoảng propagation được quy định. |
| **ROLE-04** | User có role Viewer nhưng không có quyền export, gọi export. | Bị từ chối; không tạo export job. |
| **ROLE-05** | User tự đặt tên role admin trong request. | Không làm thay đổi principal/permission tin cậy. |
| **ROLE-06** | User có role qua nested group, group bị thu hồi. | Quyền hiệu lực được cập nhật đúng phạm vi. |
| **ROLE-07** | Service account không có tenant context gọi batch. | Không được truy cập dữ liệu tenant ngoài quyền. |
| **ROLE-08** | Role definition thêm permission mới. | Review/gate và regression tests phát hiện thay đổi ngoài policy. |

Test bằng principal giả lập giúp kiểm tra **authorization logic**, nhưng không tự chứng minh token validation, chữ ký hay propagation của IAM thực tế. Đối với assurance, phải ghép test logic với **integration test danh tính và cấu hình production** khi phù hợp.

## 15. Thiết kế quy trình review theo rủi ro và chu kỳ

Không có một mốc “mọi role phải review đúng 90 ngày” phù hợp với mọi tổ chức. Chu kỳ phải được xác định bởi **mức đặc quyền, loại dữ liệu, thay đổi, nghĩa vụ và tốc độ biến động**.

### Risk-based cadence

| Nhóm quyền | Cơ chế review cần cân nhắc | Trigger ngoài chu kỳ |
| --- | --- | --- |
| **Quyền thông thường, phạm vi hẹp** | Review định kỳ theo tiêu chí tổ chức; tích hợp với thay đổi HR. | Chuyển bộ phận, đổi role definition, phát hiện lạm dụng. |
| **Quyền truy cập dữ liệu nhạy cảm / export hàng loạt** | Review có sự tham gia data owner, kiểm tra SoD và effective scope. | Thay dữ liệu, khách hàng, đối tác hoặc mục đích xử lý. |
| **Privileged admin / control-plane** | Chu kỳ chặt hơn theo rủi ro, ưu tiên JIT/PAM và log hành động. | Cấp quyền đặc biệt, đăng nhập bất thường, đổi IAM policy. |
| **Service accounts / workload identities** | Review owner, permission scope và dependency; quan sát sử dụng có ngữ cảnh. | Deploy mới, workload chuyển hệ thống, credential/role thay đổi. |
| **Break-glass** | Review cấu hình/khả năng sử dụng khẩn cấp và hậu kiểm mọi lần dùng theo quy trình. | Một lần dùng, thay người giữ, thay mô hình xác thực. |

Mốc 30, 90 hoặc 180 ngày nếu được tổ chức chọn phải được ghi trong policy/standard với lý do, không phải “best practice” áp tự động không xét rủi ro. Những quyền rất nhạy cảm có thể cần **event-driven verification** ngay khi cấp, ngoài review định kỳ.

### Trigger đánh giá lại ngay

- Thêm quyền mới vào role hoặc sửa role hierarchy.
- Thay Identity Provider, group mapping, cơ chế session/token.
- Thêm endpoint export/batch/admin hoặc đổi data classification.
- M&A, đổi nhóm tổ chức, onboarding/offboarding nhà cung cấp.
- Phát hiện SoD conflict, privilege escalation hoặc security incident.
- Audit phát hiện owner thiếu, role quá rộng, exception hết hạn.
- Một service account mất owner hoặc hệ thống phụ thuộc không còn hoạt động.

## 16. Population, sampling và review completeness

**Population** của một cuộc role review có thể là:

- Toàn bộ roles thuộc một application/environment.
- Toàn bộ role-to-permission edges và role hierarchy trong kỳ.
- Toàn bộ principal-to-role assignments, gồm grants gián tiếp.
- Các sự kiện cấp, nâng, giảm và thu hồi quyền trong một khoảng thời gian.
- Tập các service accounts, admin accounts và temporary grants trong scope.

Phải xác định **mẫu số trước khi công bố coverage**. Nếu report thiếu tài khoản local ngoài IdP, việc “100% role assignments đã được duyệt” chỉ đúng cho **report chưa đầy đủ**, không phải mọi quyền thực tế.

### Kiểm tra completeness

1. Đối chiếu identity inventory với HR, vendor registry và workload registry.
2. Đối chiếu role inventory với ứng dụng, IAM, cloud account, nhóm lồng và direct grants.
3. Kiểm tra pagination, lỗi export, giới hạn API, timestamp và các thành phần chưa kết nối.
4. Lấy mẫu ngược từ action/audit log để tìm principal có quyền nhưng không có trong danh sách.
5. Kiểm tra quyền cấp rồi thu hồi **giữa hai snapshot** nếu claim liên quan cả kỳ.

### Khi nào có thể lấy mẫu?

Nếu tổ chức cần đánh giá hàng nghìn assignments, reviewer có thể chọn mẫu theo phương pháp kiểm toán phù hợp, đặc biệt với thao tác thường xuyên; nhưng **role definitions đặc quyền và SoD trọng yếu** có thể cần kiểm tra toàn bộ theo chính sách. Sample phải ghi:

- Population gốc và cách xác minh đầy đủ.
- Cách chọn mẫu, quy mô, tiêu chí mức rủi ro.
- Từng thuộc tính đã xét (role purpose, approval, actual access, SoD).
- Kết quả, ngoại lệ và việc mở rộng đánh giá khi phát hiện lỗi.
- Giới hạn suy luận.

Ví dụ kiểm tra 25/500 assignments và phát hiện 2 trường hợp không có approval không cho phép kết luận chính xác rằng chỉ 8% toàn bộ quyền sai. Đó là **2 lỗi trong mẫu**, cần phân tích nguyên nhân, phương pháp chọn và phạm vi hệ thống.

## 17. Evidences cho role review và đánh giá control effectiveness

### Design effectiveness

Một role review control được thiết kế phù hợp khi:

- Có scope rõ ràng và inventory nguồn đáng tin.
- Tách biệt review role definition với identity membership.
- Reviewer có đủ thông tin hiểu permission, dữ liệu và mục đích.
- Có rule SoD, role owner, decision types, ngoại lệ và escalation.
- Có cơ chế xử lý action, kiểm tra quyền thực tế sau thay đổi và lịch review.
- Có quản lý provenance, integrity, retention cho hồ sơ.

### Operating effectiveness

Đánh giá vận hành cần xem control đã **thực hiện trong kỳ**:

- Các roles/assignments thuộc population đã được cung cấp đúng người duyệt.
- Reviewer quyết định có lý do, đúng thời hạn và quyền hạn.
- Quyền cần thu hồi/sửa được thực thi và xác minh.
- Các SoD conflicts, pending hoặc exceptions được theo dõi.
- Các thay đổi role sau lần review được trigger đúng quy trình.
- Các sự cố/quyền cấp sai có được phát hiện và khắc phục kịp không.

### Ma trận claim – test – evidence

| Claim | Test/hoạt động | Bằng chứng có giá trị |
| --- | --- | --- |
| Roles có owner và mục đích hợp lệ. | Đối chiếu role inventory với owner registry; review mục đích. | Role catalog phiên bản, approval và danh sách orphan roles. |
| Role không cấp quyền ngoài nhiệm vụ. | So quyền thực tế với role-permission matrix được duyệt. | Policy export, code/service mapping, kết quả kiểm tra và findings. |
| Quyền người dùng phù hợp chức năng. | Đối chiếu HR/job/tenant và role assignment, reviewer quyết định. | Population, JML records, quyết định Keep/Revoke/Modify. |
| Role có xung đột SoD được xử lý. | Rà cặp quyền/role và test workflow giao dịch. | SoD rulebook, conflict report, test chống tự duyệt. |
| Revocation thực sự có hiệu lực. | Re-query role/group và negative test trên ứng dụng. | IAM events, state before/after, test session propagation. |
| Các identity kỹ thuật cũng được kiểm soát. | Đối chiếu service accounts, secrets, cloud roles và owners. | Workload inventory, IAM config, usage logs và access review. |
| Quy trình review đã hoạt động trong kỳ. | Xem population, timestamps, coverage, approvals, SLA và exception. | Review campaign report, original decisions, audit trail, overdue list. |

### Claim – Argument – Evidence (CAE)

**Claim:** “Các vai trò có quyền xuất dữ liệu khách hàng thuộc Invoice SaaS production đã được rà soát về tập quyền và assignment theo tiêu chí tổ chức trong kỳ được xác định; các quyết định thu hồi đã được xác minh.”

**Argument:** “Inventory bao gồm các direct/nested assignments; data owner xác nhận độ nhạy và mục đích; role owners kiểm tra permissions; IAM operators thực hiện action; assessor đối chiếu trạng thái sau sửa và ghi ngoại lệ.”

**Evidence:** inventory trước/sau review, role matrix, HR/vendor owner data, IAM exports có timestamp, role-change history, review decisions, test hiệu lực và tickets/retest.

Khi thiếu một SaaS local account hoặc không xác minh được nested groups, phải **giới hạn claim** hoặc mở evidence gap. Không mặc định đánh dấu toàn bộ chương trình PASS.

## 18. Mẫu YAML lưu một kỳ role review

Ví dụ dưới đây là **mẫu học tập**, không phải định dạng bắt buộc của công cụ IAM:

~~~yaml
review_id: RR-INVOICE-PROD-2026-Q4
review_type:
  - role_definition
  - role_assignment
system: invoice-saas
environment: production
assessment_period:
  from: "2026-10-01"
  to: "2026-12-31"
scope:
  role_ids:
    - InvoiceViewer
    - InvoiceEditor
    - InvoiceAnalyst
    - TenantBillingAdmin
  include:
    - direct_assignments
    - nested_group_assignments
    - service_accounts
    - temporary_privileged_access
  known_exclusions:
    - "Legacy partner portal pending separate assessment"
population:
  source:
    - "application role registry"
    - "identity-provider group export"
    - "workload identity inventory"
  completeness: "Pending review of local portal accounts"
role_definition_findings:
  - id: RR-01
    role_id: InvoiceViewer
    issue: "Unexpected bulk export entitlement"
    decision: "REMOVE_PERMISSION_PENDING_DEPLOYMENT"
    owner_role: "Invoice Product Owner"
assignment_findings:
  - id: RR-02
    principal_ref: "redacted-principal-id"
    role_id: TenantBillingAdmin
    grant_path: "nested-group"
    decision: "REVOKE"
    verification: "Effective access retest required"
sod_findings:
  - id: RR-03
    conflict: "refund requester and approver"
    status: "OPEN"
decisions:
  approved_by_role: "Authorized Business and Risk Owners"
  approval_state: "PARTIAL"
assurance:
  design_evidence: "restricted://role-review/design-example"
  operating_evidence: "restricted://role-review/campaign-example"
  result: "PARTIAL - evidence and remediation open"
reassessment_triggers:
  - "Role permission changed"
  - "Tenant/data classification changed"
  - "New privileged identity or workload"
~~~

Các role, ID, ngày, đường dẫn và kết quả đều là **giả định minh họa**, không phản ánh một cuộc review thực. Trong hồ sơ thật, cần quản lý quyền truy cập do dữ liệu có thể tiết lộ danh tính người dùng, hệ thống, SoD conflicts và đặc quyền nhạy cảm.

### Những trường không nên thiếu

**Scope, population source, completeness check, role definition version, decisions, reviewer authority, action status, post-change verification, exceptions và limitations**. Không chỉ lưu dòng “Role review completed” vì nó không giúp tái dựng điều gì đã được kiểm tra hoặc ai chịu trách nhiệm.

## 19. RACI và quản trị quyết định

| Vai trò | Trách nhiệm trong review |
| --- | --- |
| **Role/business owner** | Xác nhận mục đích role, mức quyền hợp lý, phạm vi và người nên được cấp. |
| **Data owner** | Đánh giá quyền truy cập dữ liệu theo độ nhạy, mục đích và hậu quả. |
| **Application/system owner** | Cung cấp permission semantics, các đường truy cập và khả năng triển khai thay đổi. |
| **IAM/PAM owner và operator** | Cung cấp effective assignments, group/role hierarchy, xử lý cấp/thu hồi, bằng chứng. |
| **HR/vendor management** | Xác nhận quan hệ lao động, vai trò công việc, ngày vào/chuyển/nghỉ. |
| **Security governance** | Định nghĩa tiêu chí, tần suất, SoD policies, quy trình exception và escalation. |
| **Security assurance / assessor** | Kiểm tra population, bằng chứng thiết kế/vận hành và kết quả khắc phục. |
| **Risk owner** | Quyết định phần rủi ro còn lại hoặc ngoại lệ trong thẩm quyền; không thay thế người review nghiệp vụ. |
| **Privacy/legal/compliance** | Xác định nghĩa vụ và ranh giới phê duyệt liên quan dữ liệu/quyền khi cần. |

### RACI minh họa

**R = thực hiện; A = chịu trách nhiệm cuối cùng; C = tham vấn; I = thông báo.**

| Công việc | Role owner | IAM operator | Assurance | Data owner | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Xác định role purpose và permissions được duyệt | **A/R** | C | C | C | I |
| Xuất population, effective grants và role hierarchy | C | **A/R** | C | I | I |
| Quyết định Keep/Modify/Revoke membership theo nhiệm vụ | **A/R** | C | C | C | I |
| Thực hiện thay đổi quyền và kiểm tra trạng thái | C | **A/R** | C | I | I |
| Đánh giá độc lập tính đầy đủ và bằng chứng | C | C | **A/R** | C | I |
| Quyết định acceptance của rủi ro còn lại | C | I | C | C | **A/R** |

Với role quản trị tổ chức hoặc những quyền tài chính trọng yếu, **người phê duyệt thật** có thể là cấp khác do governance quy định. Không phải mọi công ty có role owner cũng có quyền tự duyệt mọi khoản SoD exception.

## 20. Evidence protection, audit trail và retention

Role review evidence có thể chứa nhiều thông tin nhạy cảm hơn các báo cáo security scan thông thường: danh tính quản trị, hệ thống có quyền cao, sơ đồ nhóm, đường cấp quyền, dữ liệu khách hàng, tên vendor và khả năng vượt kiểm soát.

### Các biện pháp bảo vệ

- Lưu evidence ở kho có **RBAC, retention, versioning, audit truy cập và bảo vệ khỏi sửa/xóa trái phép**.
- Tách bản đầy đủ cho reviewer đủ quyền và bản đã redacted khi chia sẻ rộng.
- Không đưa token, password, private key hoặc session cookie vào export.
- Ghi **timestamp, môi trường, source, query/report version và người thu thập**.
- Bảo vệ nguồn role/group mapping và các snapshot trước/sau; tránh ghi đè bản gốc sau khi khắc phục.
- Có quy trình khi tài liệu là một phần của điều tra sự cố hoặc audit đang mở.

### Tính toàn vẹn và nguồn gốc

Hash của file có thể hỗ trợ phát hiện thay đổi nếu tham chiếu được bảo vệ, nhưng **hash không tự chứng minh population đầy đủ, kết quả đúng hay dữ liệu đến từ nguồn hợp pháp**. Cần đối chiếu logic thu thập, quyền API, filter, pagination và cách tính effective access.

### Retention có căn cứ

Thời hạn giữ evidence phải theo loại control, nghĩa vụ, mục đích kiểm toán và rủi ro chứa dữ liệu nhạy cảm. Không mặc định lưu mọi export role vĩnh viễn. Khi cần giữ do incident/legal hold, phải có quyết định theo thẩm quyền và quản lý các bản sao.

## 21. Các chỉ số đo Role Review Control

Một dashboard không nên chỉ hiển thị “100% campaigns completed” vì có thể mọi reviewer đã nhấn Approve mà không kiểm tra.

| Chỉ số | Ý nghĩa | Giới hạn cần nêu |
| --- | --- | --- |
| **Role inventory completeness** | Tỷ lệ roles/tài khoản thuộc scope đã được đối chiếu nguồn thực tế. | Inventory thiếu nguồn sẽ khiến mẫu số sai. |
| **Reviewed role definitions** | Số role có purpose, owner và quyền được đánh giá trong kỳ. | Review tập quyền không thay cho review membership. |
| **Assignment decision coverage** | Tỷ lệ identity-role relationships có quyết định hợp lệ. | Phải bao gồm nested/direct/temporary grants. |
| **Privileged roles with valid owner** | Phần roles quyền cao có owner rõ. | Có owner không chứng minh owner đã duyệt đúng. |
| **SoD conflicts open/aged** | Xung đột còn tồn tại, độ nghiêm trọng và thời gian. | Conflict count không phản ánh hậu quả nếu không xét phạm vi và controls. |
| **Revocation verified rate** | Tỷ lệ yêu cầu thu hồi đã kiểm tra quyền hiệu lực thật. | Ticket closed chưa đủ. |
| **Overdue/exception count** | Các quyết định pending, ngoại lệ hết hạn hoặc kế hoạch quá hạn. | Chấp nhận rủi ro không đồng nghĩa đạt kiểm soát. |
| **Time to revoke** | Thời gian từ trigger hoặc quyết định tới trạng thái thu hồi đã xác minh. | Phải ghi mốc bắt đầu/kết thúc và propagation. |
| **Role drift detection** | Số thay đổi tập quyền ngoài quy trình được phát hiện. | Không có drift detected chưa chứng minh không có drift nếu nguồn không đầy đủ. |
| **Review quality and reopens** | Số quyết định bị mở lại do thiếu căn cứ hoặc quyền còn hiệu lực. | Không đếm nhiều approvals như bằng chứng chất lượng tốt. |

### Ví dụ tính toán có giới hạn

Một đợt review báo có 120 assignments; 110 Keep, 6 Revoke, 4 Pending. Trong 6 yêu cầu Revoke, mới có 5 lần thu hồi được xác minh ở ứng dụng đích.

Kết luận:

- **116/120** đã có quyết định Keep hoặc Revoke ban đầu, nhưng 4 Pending chưa có quyết định cuối.
- **5/6** yêu cầu Revoke đã được xác minh thực thi, còn 1 cần xử lý.
- Không thể công bố “100% role review hoàn tất” nếu tiêu chí closure yêu cầu xử lý xong Pending và thu hồi.

Đây là số liệu **minh họa**, chưa tính completeness của population. Nếu danh sách gốc bỏ sót nhóm nested, các tỷ lệ trên không đại diện cho toàn bộ effective access.

## 22. Ngoại lệ và residual risk trong role review

Một role quá rộng đôi khi chưa thể tách ngay vì giới hạn hệ thống legacy hoặc phụ thuộc của bên thứ ba. Tổ chức có thể cần biện pháp tạm, nhưng **kế hoạch sửa không làm current residual risk tự giảm**.

Một hồ sơ exception nên có:

1. **Role/permission/identity và data asset** bị ảnh hưởng, phạm vi và thời gian.
2. **Risk scenario**: điều gì có thể xảy ra, likelihood và impact theo phương pháp tổ chức.
3. **Current controls và evidence**: những gì đã vận hành thực tế; tránh tính control chưa triển khai.
4. **SoD, regulatory hoặc contractual constraints** nếu có; không mặc nhiên có thể miễn trừ.
5. **Compensating measures** có hiệu quả được kiểm chứng, ví dụ JIT, giám sát đặc quyền và xác nhận giao dịch độc lập.
6. **Owner, deadline, kế hoạch tách role/thu hồi và kiểm thử**.
7. **Risk owner có thẩm quyền** phê duyệt, lý do, điều kiện, expiry và trigger xem lại.

**Current residual risk** phản ánh trạng thái quyền đang có và controls có hiệu lực. **Target residual risk** là ước lượng sau khi role được sửa, direct grants bị thu hồi và tests đạt. Review completion không đồng nghĩa risk acceptance.

## 23. Continuous Role Review trong SDLC và vận hành

Role review không nên là một chiến dịch thủ công mỗi năm nếu role và permissions thay đổi hằng tuần. Tổ chức cần kết hợp:

| Thời điểm | Kiểm soát thích hợp | Bằng chứng |
| --- | --- | --- |
| **Thiết kế chức năng** | Phân tích roles, permission matrix, SoD và tenant boundary. | Requirements, access matrix được duyệt, threat model. |
| **Phát triển** | Code review authorization, test role/permission/object. | Unit/integration tests, negative cases, change mapping. |
| **CI/CD** | Gate khi role definition hoặc IAM policy đổi ngoài tiêu chí. | Policy-as-code results, diff và approval. |
| **Cấp quyền** | Manager/role owner approval, thời hạn, least privilege. | Request, reason, approver, effective grant log. |
| **JML events** | Thu hồi hoặc đổi quyền khi chuyển/nghỉ việc. | HR trigger, IAM action, verification. |
| **Production** | Giám sát role drift, SoD, quyền bỏ quên và privileged use. | Telemetry, effective access checks, alerts. |
| **Periodic review** | Review definitions và memberships theo rủi ro. | Population, decisions, exceptions, post-action tests. |
| **Audit/incident** | Xác minh hành động, phân tích nguyên nhân và ngăn tái diễn. | Findings, incident timeline, retest, risk decision. |

### Tự động hóa: hữu ích nhưng không quyết định thay nghiệp vụ

Tự động hóa có thể phát hiện roles không owner, privilege expansion, memberships bất thường, người nghỉ còn quyền, exception hết hạn và SoD conflicts. Nhưng máy không tự biết một kế toán viên **có thật sự cần quyền duyệt hoàn tiền** trong quy trình mới hay không. Role owner và business/data owner vẫn phải chịu trách nhiệm cho **lý do và quyết định**.

### Một luồng kiểm tra sau role definition change

~~~text
Role/permission changed
    -> Detect diff + identify affected principals
    -> Evaluate sensitivity and SoD implications
    -> Require authorized role owner review
    -> Run permission and object authorization tests
    -> Deploy with change evidence
    -> Reconcile effective access in production
    -> Update risk/control evidence and trigger review
~~~

Một đổi permission nhỏ về tên có thể kéo theo truy cập dữ liệu nhạy cảm nhiều tenant. Vì vậy mức độ ảnh hưởng dựa trên **quyền và tài nguyên thực tế**, không chỉ số dòng IaC thay đổi.

## 24. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Đã review danh sách user là đã review roles.” | Phải kiểm tra cả **role definitions và permissions**; role quá rộng vẫn nguy hiểm khi cấp đúng người. |
| “Role gán đúng người thì chắc chắn đúng quyền.” | Quyền role có thể drift, mở rộng dữ liệu hoặc có đường bypass. |
| “Mọi role đều phải review cùng tần suất.” | Tần suất theo rủi ro, mức đặc quyền, dữ liệu, nghĩa vụ và thay đổi. |
| “Không ai dùng role trong 30 ngày nên cứ xóa.” | Có thể là vai trò mùa vụ, emergency hoặc logging thiếu; cần xác minh dependency. |
| “Xóa group membership là thu hồi ngay lập tức.” | Token/session/cache và SaaS sync có thể còn hiệu lực; cần kiểm tra propagation. |
| “IAM export thể hiện toàn bộ effective permissions.” | Có thể thiếu nested groups, direct grants, resource policies, local roles và điều kiện. |
| “Cấp hai role khác nhau luôn đáp ứng SoD.” | Có thể cần **dynamic SoD** trên từng giao dịch và phê duyệt độc lập. |
| “Người quản trị IAM có thể tự duyệt tất cả quyền.” | Approval phải theo thẩm quyền và nguyên tắc tách nhiệm vụ. |
| “Service accounts không phải người nên không cần review.” | Workload identities có thể mang quyền lớn, owner và vòng đời phải rõ. |
| “Approve All là evidence review đầy đủ.” | Cần lý do, quyền hiển thị đúng scope, phương pháp và xử lý ngoại lệ. |
| “Chỉ cần role name là biết được rủi ro.” | Cần semantics permission, dữ liệu, tenant và blast radius. |
| “Ticket revoke đã đóng nghĩa là quyền biến mất.” | Phải xác minh effective access và đường truy cập đích. |
| “Không còn SoD conflict trên dashboard nghĩa là an toàn.” | Có thể thiếu nguồn, conflict rules hoặc transaction-level checks. |
| “Không có bằng chứng sai nghĩa là PASS.” | Evidence gap phải được phân loại và xử lý rõ. |

## 25. Checklist thực thi role review

Khi chuẩn bị một đợt role review có thể dùng danh sách kiểm tra sau:

1. **Mục tiêu và scope:** hệ thống, môi trường, dữ liệu, thời kỳ và nhóm quyền nào được xét?
2. **Population:** đã đối chiếu IdP, ứng dụng, cloud, vendor, HR, service accounts và direct grants?
3. **Role definitions:** có role ID, business purpose, owner, permission semantics, phân loại nhạy cảm và version?
4. **Effective access:** quyền kế thừa/nested groups, conditions, deny, session, object scope đã được xem xét?
5. **Least privilege:** permissions có còn cần thiết cho từng nhiệm vụ và dữ liệu?
6. **SoD:** có static/dynamic conflicts, compensating controls, người duyệt độc lập?
7. **Identity lifecycle:** người vào/chuyển/nghỉ, vendor và temporary grants được xét?
8. **Review decisions:** Keep/Revoke/Modify/Pending/Exception có reason, approver, time và authority?
9. **Remediation:** action đã triển khai đúng nguồn cấp quyền và có ticket/truy vết?
10. **Post-action verification:** effective access đã được đọc lại, negative tests đã đạt, token/cache xử lý đúng SLA?
11. **Evidence quality:** có provenance, integrity, completeness, version, period, limits và reviewer?
12. **Risk closure:** findings, SoD, evidence gaps, residual risk và review triggers đã được xử lý hoặc chuyển owner đúng?

## 26. Bài tập và gợi ý giải

### Bài tập A — Role Viewer có quyền export

Role InvoiceViewer được gán cho đúng nhân viên, nhưng release mới thêm EXPORT_ALL_INVOICES cho role mà không có approval. Một báo cáo access review vẫn hiển thị 100% assignments đã xác nhận.

**Gợi ý:** Identity-to-role review có thể đã hoàn thành nhưng **role definition review thất bại**. Cần so permission diff với ma trận được duyệt, xem hậu quả data disclosure, sửa role/tách export, test negative access và đánh giá rủi ro trong khoảng role quá rộng.

### Bài tập B — Xung đột SoD qua role khác nhau

Nhân viên A có cả RefundRequester và RefundApprover. Nhóm giải thích đây là hai role khác nhau nên đã đáp ứng SoD.

**Gợi ý:** Role khác tên không tự chứng minh tách trách nhiệm. Phải kiểm tra policy static SoD, dynamic SoD trên cùng refund, quyền phê duyệt và khả năng tự duyệt. Cần test transaction-level denial cùng log; review owner và ngoại lệ nếu có.

### Bài tập C — Thu hồi group nhưng session vẫn hợp lệ

Nhân viên support đã nghỉ, IdP group bị thu hồi. Một access token còn sống cho phép gọi API quản trị thêm 45 phút.

**Gợi ý:** Phải đánh giá propagation/revocation yêu cầu trong chính sách; kiểm tra độ dài phiên, token validation và khả năng vô hiệu hóa phiên. Thu hồi membership chỉ là một bước; kết luận dựa trên **effective access và thời điểm mất quyền thực sự**.

### Bài tập D — Service account dùng chung với quyền cao

Một worker xuất hóa đơn dùng một service account có quyền đọc database mọi tenant và cập nhật chính sách bucket. Tài khoản không có người đăng nhập trực tiếp nên bị bỏ khỏi role review.

**Gợi ý:** Identity kỹ thuật vẫn thuộc scope. Cần owner, nhu cầu nghiệp vụ, role-to-permission review, boundary của job/tenant, quyền lưu trữ, SoD và thử thao tác không được phép. Xem xét chia workload identities và giảm quyền; có kế hoạch thay đổi an toàn.

### Bài tập E — Snapshot thiếu nested groups

Báo cáo tháng này chứa 60 role assignments và tất cả được duyệt. Một nhân viên nhận quyền admin qua group lồng không xuất hiện trong export.

**Gợi ý:** Population thiếu nên tỷ lệ 100% không thể áp cho effective access. Cần expand group hierarchy, kiểm tra direct grants, đối chiếu tài khoản/quyền thực tế, cập nhật scope và đánh giá lại các quyết định liên quan.

### Bài tập F — Một role không sử dụng

Một role quản trị dữ liệu đã không có audit event sử dụng trong sáu tháng. Người phụ trách đề nghị xóa ngay để giảm số role.

**Gợi ý:** Cần xác minh log completeness, owner, ứng dụng theo mùa, emergency use và dependency. Sau review có thể deprecate role với phương án migration/rollback và test, nhưng **không kết luận quyền không cần thiết chỉ từ việc thiếu event**.

### Bài tập G — Kết quả review vẫn còn Pending

Một chiến dịch review có 120 assignments, trong đó 110 Keep, 6 Revoke và 4 Pending. Chỉ 5/6 Revoke đã xác minh ở ứng dụng. Nhóm báo “Campaign completed”.

**Gợi ý:** Nếu closure yêu cầu quyết định và hành động đầy đủ, báo cáo này **chưa đạt**. Cần xử lý 4 Pending, xác minh 1 revoke còn lại, ghi tình trạng và risk owner/escalation theo chính sách. Không nhầm hoàn thành thao tác gửi biểu mẫu với hiệu lực control.

## Kết luận

**Role review** là một security control quan trọng để bảo đảm **định nghĩa vai trò, quyền được cấp và danh tính sử dụng quyền** tiếp tục phù hợp với nhu cầu nghiệp vụ, dữ liệu và rủi ro. Một chương trình role review đáng tin phải xét **role-to-permission** cùng **identity-to-role**, phân biệt quyền được khai báo với **effective access**, xem xét nhóm lồng, quyền trực tiếp, tài khoản đặc quyền/kỹ thuật, JML, giới hạn tenant và xung đột SoD. Trong **SECURITY_SECURITY_ASSURANCE**, review chỉ thật sự có giá trị khi có **population đầy đủ, quyết định có lý do, owner có thẩm quyền, bằng chứng thay đổi đã triển khai và kiểm chứng quyền sau thu hồi**, cùng quản lý ngoại lệ và residual risk. Đánh giá định kỳ cần kết hợp kiểm tra theo sự kiện thay đổi trong SDLC và vận hành, để bảo mật truy cập được duy trì bằng **chứng cứ có thể kiểm tra**, thay vì các lần ký duyệt hình thức.
