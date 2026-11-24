# Ngoại lệ SoD trong IAM: phê duyệt, kiểm soát bù trừ và thu hồi quyền xung đột

## 1. Ngoại lệ SoD là gì?

**Segregation of Duties (SoD)**, hay **phân tách nhiệm vụ**, là nguyên tắc không để một chủ thể đơn lẻ có thể thực hiện trọn vẹn những bước nhạy cảm mà lẽ ra phải được kiểm tra độc lập. Mục tiêu không chỉ là hạn chế quyền truy cập, mà còn **giảm khả năng tự phê duyệt, tự sửa kết quả, che giấu sai phạm hoặc vượt qua một lớp kiểm soát nghiệp vụ**.

**Ngoại lệ SoD** (*SoD exception*) là trường hợp tổ chức **xem xét cho phép một sự kết hợp quyền hoặc nhiệm vụ có xung đột theo quy tắc SoD thông thường**, vì có nhu cầu nghiệp vụ được chứng minh và có **quyết định chấp nhận rủi ro bởi người có thẩm quyền**, đi cùng **biện pháp kiểm soát bù trừ, phạm vi và thời hạn rõ ràng**.

Ví dụ, bộ phận tài chính quy định người **tạo nhà cung cấp** không được là người **phê duyệt thanh toán cho nhà cung cấp đó**. Một doanh nghiệp nhỏ thiếu nhân sự có thể cần một nhân viên kiêm hai trách nhiệm trong thời gian ngắn. Đây là **xung đột SoD**; nếu muốn tiếp tục, tổ chức phải quyết định xem có một cơ chế **kiểm tra độc lập ở từng giao dịch** đủ để giảm rủi ro hay không. Không thể chỉ thêm nhãn “ngoại lệ” rồi cho người đó tự tạo và tự duyệt mọi khoản thanh toán.

Nguyên tắc trung tâm:

> **Ngoại lệ SoD không phải là quyền miễn trừ mọi kiểm soát.** Đó là một quyết định quản trị rủi ro có chủ sở hữu, điều kiện, thời hạn, bằng chứng thực thi và kế hoạch chấm dứt.

Trong vòng đời **Identity and Access Management (IAM)** theo **Joiner–Mover–Leaver (JML)**, ngoại lệ có thể phát sinh lúc cấp quyền cho nhân viên mới, chuyển vị trí kiêm nhiệm, bàn giao công việc hoặc xử lý sự cố khẩn cấp. Việc quản lý ngoại lệ phải kết nối **HRIS, IAM/IGA, IdP/SSO, SCIM, RBAC/ABAC/PBAC, workload identity, audit và account reconciliation** để ngăn xung đột bị giữ vô thời hạn.

## 2. Tại sao SoD cần ngoại lệ mà không thể chỉ từ chối tất cả?

Trong thiết kế chuẩn, nhiệm vụ có xung đột nên được phân công cho những chủ thể khác nhau. Nhưng thực tế có những giới hạn vận hành:

- Đội nhỏ không đủ người để chia mọi bước nghiệp vụ.
- Nhân viên đang **kiêm nhiệm có phê duyệt** trong giai đoạn chuyển giao dự án.
- Người phụ trách chính nghỉ phép, cần người thay thế trong thời gian xác định.
- Quy trình phục hồi sự cố yêu cầu thao tác nhanh ở môi trường production.
- Hệ thống cũ có role quá thô, chưa tách được permission theo nhiệm vụ.
- Tình huống đặc biệt cần một người vừa có quyền vận hành vừa kiểm tra tính toàn vẹn của một số kết quả.

**Nhu cầu không tự tạo quyền**. Trước khi dùng ngoại lệ, phải kiểm tra liệu có phương án tốt hơn như phân công người độc lập, thay đổi quy trình, role hẹp hơn, **Just-in-Time (JIT)**, **Privileged Access Management (PAM)** hoặc kiểm soát SoD tại cấp giao dịch hay không.

Ngoại lệ có thể cần thiết nhưng luôn tạo **rủi ro tồn dư**. Không phải mọi xung đột đều được phép có ngoại lệ: chính sách nội bộ, nghĩa vụ hợp đồng hoặc quy định áp dụng có thể quy định một số cặp nhiệm vụ **không thể miễn trừ**. Bài này không mặc định mọi SoD rule đều có thể được vượt qua.

## 3. Phân biệt SoD violation, SoD exception và compensating control

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **SoD rule** | Quy tắc phân tách nhiệm vụ đã được phê duyệt | Người tạo thanh toán không được tự duyệt thanh toán đó |
| **SoD conflict** | Hai quyền hoặc trách nhiệm có thể xung đột | Một người giữ CreatePayment và ApprovePayment |
| **SoD violation** | Điều kiện bị cấm thực sự xảy ra hoặc tổ hợp quyền trái policy | Người tự duyệt giao dịch mình tạo khi policy cấm |
| **SoD exception request** | Đề nghị xử lý xung đột theo cách khác thông thường | Xin quyền kiêm nhiệm một tháng |
| **Approved SoD exception** | Ngoại lệ được chủ thể có thẩm quyền chấp thuận, có điều kiện | Được giữ hai role, nhưng giao dịch phải có kiểm tra độc lập |
| **Compensating control** | Kiểm soát thay thế/bù trừ nhằm giảm rủi ro | Reviewer độc lập kiểm tra giao dịch trước khi giải ngân |
| **Residual risk** | Rủi ro còn lại sau khi áp dụng biện pháp | Vẫn có khả năng thông đồng hoặc kiểm soát thất bại |
| **Unauthorized override** | Bỏ qua quy tắc không có căn cứ hợp lệ | Tự sửa policy để cấp quyền admin |

**Xung đột được phát hiện chưa chắc đã là một vi phạm giao dịch thực tế**. Ví dụ một người giữ cả hai role có thể vi phạm **static SoD** dù chưa dùng quyền; trong khi với **dynamic SoD**, việc giữ hai role có thể được cho phép nhưng **không được thực hiện hai bước xung đột trên cùng một giao dịch**.

**Một ngoại lệ được phê duyệt cũng không chứng minh biện pháp bù trừ đã hoạt động**. Cần kiểm tra ở workflow/PDP/PEP và có bằng chứng kiểm soát, không chỉ có một ticket phê duyệt.

## 4. Static SoD và Dynamic SoD: ngoại lệ áp dụng ở đâu?

| Mô hình | Quy tắc | Ví dụ | Ý nghĩa khi xin ngoại lệ |
| --- | --- | --- | --- |
| **Static Separation of Duties (SSD)** | Không được đồng thời nắm một tổ hợp role xung đột trong phạm vi đã định | Một user không được có cả UserCreator và PrivilegeApprover trên cùng tenant | Cần xem có thể tách role, dùng thời điểm luân phiên, thu hẹp scope hoặc có ngoại lệ được phép không |
| **Dynamic Separation of Duties (DSD)** | Có thể có các role, nhưng không được kích hoạt/sử dụng đồng thời theo điều kiện hoặc trên cùng giao dịch | Một nhân viên có thể tạo và duyệt, nhưng không được duyệt chính phiếu mình tạo | Kiểm soát ở lúc thực hiện hành động và theo transaction context |
| **Workflow/four-eyes control** | Một hành động có bước kiểm tra độc lập | Thay đổi limit thanh toán cần người thứ hai xác nhận | Ngoại lệ phải chỉ rõ ai kiểm tra, khi nào và bằng chứng |
| **Conflict-of-interest policy** | Không để người có lợi ích liên quan quyết định việc của mình | Chủ thể không duyệt request cấp admin cho chính mình | Không thể chỉ chuyển button approve sang cùng danh tính qua tài khoản khác |

**Static conflict** kiểm tra thông qua **tập quyền có thể sở hữu**. **Dynamic conflict** cần biết **ai đã thực hiện hành động trước đó, trên đối tượng nào, dưới quan hệ nào**, nên chỉ kiểm tra membership của nhóm IdP thường là không đủ.

Ví dụ, hai quyền **CREATE_INVOICE** và **APPROVE_INVOICE** có thể nằm ở một tài khoản, nhưng policy DSD cấm **approve(invoice)** nếu **invoice.createdBy == subject**. Đây là kiểm soát gắn với **đối tượng giao dịch**; một ngoại lệ trong role catalog không được vô hiệu hóa logic đó nếu chưa có phê duyệt rủi ro và thiết kế kiểm soát thay thế phù hợp.

## 5. Các ví dụ SoD conflict trong IAM và nghiệp vụ

| Quyền A | Quyền B | Rủi ro khi kết hợp | Kiểm soát thường áp dụng |
| --- | --- | --- | --- |
| CreateVendor | ApproveVendorPayment | Tạo đối tượng thụ hưởng rồi tự chuyển tiền | Hai người khác nhau hoặc duyệt độc lập giao dịch |
| CreateInvoice | ApproveInvoice | Tự tạo và tự phê duyệt hóa đơn | Kiểm tra creator != approver |
| CreateIdentity | GrantPrivilegedRole | Tự tạo danh tính rồi cấp admin | Tách provisioning và privileged approval |
| RequestPrivilegedAccess | ApprovePrivilegedAccess | Self-approval | Approver độc lập theo policy |
| DevelopCode | ApproveCodeAndDeploy | Bỏ qua kiểm tra thay đổi | Code review độc lập, deployment gate |
| ManageSecrets | AlterAuditLogs | Dùng credential rồi sửa dấu vết | Tách quyền và log bất biến/giám sát độc lập |
| ChangeFinancialLimits | AuthorizeTransactions | Tự tăng hạn mức rồi giao dịch | Approval bổ sung, hạn mức và hậu kiểm |
| ModifyIAMPolicy | DisableSecurityDetection | Mở quyền rồi che cảnh báo | PAM/JIT, giới hạn scope, audit độc lập |

Danh sách chỉ mang tính minh họa. Một SoD conflict phải có **mã rule, mục tiêu kiểm soát, phạm vi tenant/resource, điều kiện và nguồn thẩm quyền**. Không dùng một tên role toàn cục như Admin để kết luận mọi tổ hợp đều xung đột giống nhau.

**Tổ hợp quyền có thể xung đột chỉ trong cùng tenant hoặc cùng tài nguyên**. Người tạo hóa đơn của org-a không tự nhiên vi phạm rule duyệt hóa đơn ở org-b nếu hai phạm vi hoàn toàn độc lập và policy không đặt hạn chế xuyên tổ chức.

## 6. Cặp quyền xung đột khác quyền thừa

**Least Privilege** hỏi liệu mỗi quyền có cần thiết không. **SoD** hỏi liệu **kết hợp các quyền hoặc cách thực hiện nhiệm vụ** có tạo cơ hội vượt qua sự kiểm tra độc lập không.

Một nhân viên có thể thực sự cần cả quyền **ManageInventory** và **ApprovePurchase** cho hai nhiệm vụ hợp lệ, nhưng tổ hợp quyền vẫn nguy hiểm nếu người đó có thể **đặt hàng, sửa tồn kho và duyệt cùng một giao dịch**. Ngược lại, một role **OrganizationAdministrator** chỉ một mình đã có thể quá rộng so với nhiệm vụ, ngay cả khi không xung đột với role nào khác.

Khi xem ngoại lệ:

1. Xác định **tập quyền thực tế (effective permissions)** chứ không chỉ tên role.
2. Phân tích **đường tạo rủi ro**: có thể thực hiện những bước nào trên tài nguyên nào?
3. Kiểm tra **SoD static, dynamic, workflow** và các quyền gián tiếp.
4. So sánh với **quyền tối thiểu** để xem có cần giữ cả hai hay không.
5. Chỉ xét ngoại lệ cho phần xung đột **thật sự không thể tránh bằng thiết kế tốt hơn**.

Một yêu cầu ngoại lệ không phải giấy phép **tự thêm quyền ngoài nhiệm vụ**. Phải tách **căn cứ cấp entitlement** và **căn cứ chấp nhận xung đột SoD** thành hai quyết định có thể truy vết.

## 7. Điều kiện tiên quyết trước khi đề nghị ngoại lệ

Một yêu cầu nên chứng minh:

- **Nhu cầu nghiệp vụ cụ thể**: nhiệm vụ, kết quả, thời điểm cần và ảnh hưởng nếu không được thực hiện.
- **Danh tính đúng**: beneficiary, requester, employment relation hoặc workloadId đã xác minh.
- **Phạm vi rõ**: role/permission, action, application, resource, tenant và môi trường.
- **Xung đột xác định**: mã SoD rule, hai hay nhiều đường quyền gây xung đột.
- **Phương án thay thế đã cân nhắc**: phân công người khác, phân quyền hẹp, JIT/PAM, thay workflow.
- **Rủi ro và kiểm soát bù trừ**: những điều kiện nào giảm khả năng lạm dụng/phát hiện sai phạm.
- **Owner và approver độc lập**: người chịu trách nhiệm về quyền và người có thẩm quyền chấp nhận rủi ro.
- **Thời hạn kết thúc**: endAt hoặc điều kiện kết thúc gắn với dự án/incident.
- **Kế hoạch thu hồi** và **cách chứng minh thu hồi** tại hệ thống đích.

Nếu requester không chỉ rõ tài nguyên hoặc xin **Admin mọi tenant không thời hạn** để “phòng khi cần”, thông tin không đủ để đánh giá một ngoại lệ hợp lý. Cần thu hẹp yêu cầu hoặc từ chối theo policy.

## 8. Quy trình xử lý ngoại lệ SoD từ đầu đến cuối

~~~mermaid
flowchart TD
    A["Access request / Recertification / Phát hiện conflict"] --> B["Identity correlation và SoD rule matching"]
    B --> C{"Conflict có thật và nằm trong scope?"}
    C -->|"Không / dữ liệu mơ hồ"| D["Sửa dữ liệu hoặc điều tra; không tự grant"]
    C -->|"Có"| E["Xem phương án không cần ngoại lệ"]
    E --> F{"Có thể loại conflict bằng cách hẹp hơn?"}
    F -->|"Có"| G["Chọn role/quan hệ/phạm vi không xung đột"]
    F -->|"Không"| H["Đánh giá risk và compensating controls"]
    H --> I{"Rule có cho phép ngoại lệ?"}
    I -->|"Cấm miễn trừ"| J["REJECT / thiết kế lại quy trình"]
    I -->|"Có điều kiện"| K["Phê duyệt độc lập, scope, expiry và owner"]
    K --> L{"Approved?"}
    L -->|"Không / timeout"| J
    L -->|"Có"| M["Revalidate JML + role + policy trước cấp"]
    M --> N["Provision/Activate ngoại lệ theo policy"]
    N --> O["PEP/workflow thực thi kiểm soát bù trừ"]
    O --> P["Giám sát, audit, review và incident response"]
    P --> Q["Hết hạn / Mover / Leaver / thu hồi khẩn"]
    Q --> R["Revoke grant và exception, readback target"]
    R --> S{"Đã chứng minh Deny đúng phạm vi?"}
    S -->|"Có"| T["VERIFIED_CLOSED"]
    S -->|"Chưa/UNKNOWN"| U["BLOCKED/UNVERIFIED, owner và SLA"]
    U --> R
~~~

Quy trình không kết thúc tại nút **Approve**. Với quyền nguy hiểm, tổ chức phải xác nhận **compensating control thực sự được thực thi** và **quyền chấm dứt đúng lúc**. Nếu reviewer từ chối, API/connector không được dùng nhánh khác để âm thầm cấp role.

## 9. Phân biệt người yêu cầu, người hưởng quyền và người duyệt

| Vai trò | Trách nhiệm | Không được mặc định |
| --- | --- | --- |
| **Requester** | Đề nghị ngoại lệ và cung cấp lý do | Tự duyệt chính yêu cầu của mình |
| **Beneficiary** | Người/workload nhận quyền hoặc khả năng thực hiện hành động | Tự chấp nhận rủi ro không có thẩm quyền |
| **Line manager/sponsor** | Xác nhận công việc và nhu cầu của chủ thể | Thay data/resource owner duyệt mọi quyền |
| **Resource/business owner** | Đánh giá tác động và phê duyệt trong phạm vi tài nguyên | Tự bỏ hard security control |
| **Risk/security/IGA owner** | Kiểm tra SoD, residual risk và quyền cấp ngoại lệ | Cấp mọi quyền ngoài phạm vi governance |
| **Control owner** | Thiết kế/xác minh kiểm soát bù trừ | Chỉ mô tả kiểm soát mà không vận hành |
| **Provisioning actor** | Áp dụng quyết định đã được duyệt | Tự sửa role/scope/expiry khác approval |
| **Independent monitor/auditor** | Theo dõi, kiểm tra bằng chứng và tác động | Trở thành bên duy nhất tự tạo và tự kiểm tra quyền |

Một request có thể do manager tạo cho nhân viên hoặc chủ service tạo cho workload. **Requester không nhất thiết là beneficiary**, và người duyệt không được suy từ trường email của requester.

**Phê duyệt độc lập** cần được kiểm tra trên danh tính thật, không chỉ tài khoản hiển thị. Một người không thể vượt kiểm soát self-approval bằng cách đăng nhập qua account phụ có cùng person identity.

## 10. Quyền phê duyệt ngoại lệ không mặc định giống quyền phê duyệt access request

Với role bình thường, một resource owner có thể duyệt nhu cầu truy cập. Nhưng **chấp nhận xung đột SoD** là quyết định rủi ro bổ sung. Tổ chức có thể yêu cầu:

1. **Business owner** xác nhận không có phương án thay thế hợp lý.
2. **Resource/data owner** đánh giá tài nguyên và scope.
3. **Security/IAM governance** xác nhận rule cho phép ngoại lệ và các biện pháp bù trừ.
4. **Risk owner** có thẩm quyền chấp nhận residual risk theo ngưỡng đã định.
5. Với giao dịch nhạy cảm, **một reviewer độc lập** phải thực thi kiểm soát ở cấp giao dịch.

Không mặc định mọi yêu cầu cần đúng năm bước; tuyến phê duyệt phải được định nghĩa trong **policy và risk tier**. Điều quan trọng là **không để người xung đột lợi ích tự chấp nhận rủi ro của chính mình**, và không dùng manager approval thông thường làm bằng chứng được miễn SoD.

Nếu người có thẩm quyền **timeout, Leaver hoặc mất role approver**, hệ thống phải **escalate/reassign hợp lệ** hoặc giữ **PENDING/BLOCKED**, không coi im lặng là chấp thuận.

## 11. Những trường hợp nên từ chối ngoại lệ

Ngoại lệ cần bị từ chối hoặc chuyển thiết kế lại khi:

- Rule được chính sách/quy định xác định là **không thể miễn trừ**.
- Không có căn cứ nhiệm vụ hoặc rủi ro không thể chấp nhận.
- Có phương án tách nhiệm vụ khả thi mà không gây tác động bất hợp lý.
- Quyền yêu cầu quá rộng so với nhiệm vụ hoặc không giới hạn tenant/resource.
- Không có **owner chịu trách nhiệm**, không có người duyệt độc lập hợp lệ.
- Không xác định được identity/account mapping chắc chắn.
- Không có biện pháp bù trừ đủ hiệu lực đối với đường rủi ro chính.
- Không có expiration hoặc kế hoạch thu hồi khi policy yêu cầu có hạn.
- Beneficiary đã Leaver hoặc không còn quan hệ bảo trợ hợp lệ.
- Ngoại lệ yêu cầu vô hiệu hóa log, che dấu kiểm toán hoặc tự phê duyệt không có kiểm tra độc lập.

**Đặc quyền không thể kiểm chứng ở hệ thống đích** là một yếu tố rủi ro, không được che bằng nhãn “APPROVED” mà bỏ qua giới hạn observability.

## 12. Compensating control là gì?

**Compensating control (kiểm soát bù trừ)** là cơ chế được áp dụng khi không thể thực thi nguyên tắc phân tách nhiệm vụ theo cách thông thường, nhằm **ngăn, giới hạn hoặc kịp thời phát hiện** hành vi mà SoD muốn phòng tránh.

Ví dụ, nếu cùng người được phép nhập dữ liệu và đề nghị phê duyệt chi phí, một kiểm soát bù trừ có thể yêu cầu **người khác kiểm tra độc lập bằng chứng, số tiền và bên nhận trước khi thanh toán được thực hiện**.

Các loại cơ chế:

| Loại | Ví dụ | Giới hạn |
| --- | --- | --- |
| **Preventive** — phòng ngừa | API chặn user duyệt giao dịch do chính user tạo | Phải được thực thi ở backend trên cùng object |
| **Detective** — phát hiện | Đối soát giao dịch hàng ngày bởi người độc lập | Không ngăn giao dịch ngay; cần SLA xử lý sự kiện |
| **Corrective** — khắc phục | Hoàn tác thay đổi sai, thu hồi credential và điều tra | Một số tác động có thể không đảo ngược được |
| **Limiting** — giới hạn | Trần giá trị, scope dự án, TTL ngắn, JIT activation | Giảm phạm vi tác động, không loại bỏ toàn bộ rủi ro |
| **Oversight** — giám sát | Session recording, alert cho owner và hậu kiểm | Cần bảo đảm log không bị người bị giám sát sửa/xóa |

**Một biện pháp phát hiện sau sự kiện không mặc nhiên tương đương một kiểm soát phòng ngừa**. Với giao dịch không thể hoàn tác hoặc dữ liệu nhạy cảm, chỉ log rồi xem cuối tháng có thể không đủ để chấp nhận rủi ro.

## 13. Thiết kế kiểm soát bù trừ đáp ứng mục tiêu SoD

Một biện pháp bù trừ chất lượng cần chỉ rõ:

1. **Control objective:** rủi ro nào đang được xử lý? Ví dụ ngăn tự chuyển tiền.
2. **Control owner:** ai chịu trách nhiệm vận hành, không trùng lợi ích với beneficiary?
3. **Trigger và population:** những giao dịch/tài nguyên nào được kiểm tra, có bỏ sót đường batch/API không?
4. **Frequency và timing:** trước khi quyết định có hiệu lực hay sau, độ trễ chấp nhận được bao nhiêu?
5. **Independence:** người kiểm tra không chính là người tạo hành động bị kiểm soát.
6. **Evidence:** log, chữ ký/phê duyệt, case ID, immutable event và kết quả đối soát.
7. **Failure handling:** khi kiểm soát không chạy, hệ thống chặn hay tạo incident theo risk policy?
8. **Testing:** có negative test chứng minh không thể đi vòng kiểm soát không?
9. **Sunset:** khi ngoại lệ hết hạn, cơ chế này kết thúc hoặc được điều chỉnh ra sao?

Ví dụ, nếu kiểm soát bù trừ yêu cầu **review tất cả các giao dịch được tạo bởi người có ngoại lệ trong ngày**, cần chứng minh hệ thống không bỏ qua giao dịch **qua API, import hàng loạt, batch job và giao diện mobile**.

Không nên ghi “log đã bật” là kiểm soát đầy đủ khi người có ngoại lệ đồng thời được phép **xóa hoặc sửa log**, hoặc không ai được giao nhiệm vụ xem log.

## 14. SoD exception ở cấp role khác exception ở cấp giao dịch

Một chính sách có thể cho phép **ngoại lệ ở cấp gán role** mà vẫn **bắt buộc SoD ở cấp giao dịch**.

Ví dụ:

~~~text
Subject: accountant-482
Roles:
    InvoiceCreator
    InvoiceApprover

Approved role-level exception:
    Có thể giữ cả hai role từ 01/12 đến 15/12
    Chỉ áp dụng org-a, cost-center C7

Transaction-level rule:
    invoice.createdBy != currentApprover.identityId
    invoice.organizationId == currentApprover.authorizedOrganizationId
    invoice.amount <= approvedLimit

Decision:
    Dù giữ hai role, không được tự duyệt invoice mình tạo.
~~~

Điều này thường giảm rủi ro hơn ngoại lệ cho phép **người đó tự hoàn thành mọi bước**. Nếu nghiệp vụ thật sự yêu cầu **cùng một người thực hiện cả hai bước trên cùng giao dịch**, đó là mức rủi ro khác và cần phê duyệt/kiểm soát bù trừ mạnh hơn — thậm chí có thể không được phép.

**Quyền role không chứng minh việc thực thi nghiệp vụ đã tuân thủ SoD.** Phải theo dõi lịch sử actor, giao dịch và decision tại PEP/workflow.

## 15. Ví dụ nghiệp vụ: tạo và duyệt nhà cung cấp

Một công ty có quy tắc:

| Bước | Role | Chủ thể cần tách |
| --- | --- | --- |
| Tạo hồ sơ vendor | VendorCreator | Người A |
| Xác minh thông tin vendor | VendorVerifier | Người B |
| Phê duyệt thanh toán | PaymentApprover | Người C hoặc người độc lập theo policy |

Nếu công ty thiếu người trong tuần cao điểm và muốn A kiêm role VendorVerifier, hãy xác định:

- A có được **tự xác minh hồ sơ do chính A tạo** không?
- Nếu không, có workflow enforce **creator != verifier** không?
- Nếu A chỉ được xác minh hồ sơ do người khác tạo, xung đột ở cấp role có thể được giải quyết bằng **dynamic SoD** thay vì miễn trừ giao dịch.
- Nếu buộc phải tự xác minh, có **người thứ ba kiểm tra độc lập trước thanh toán** và giới hạn số tiền hoặc số vendor không?
- Exception có **khoảng thời gian, danh sách tài nguyên và người owner** rõ không?

Kịch bản ngoại lệ nên ưu tiên **ràng buộc đối tượng giao dịch**. Không nên dùng câu “được cấp cả hai role nên được phép làm mọi bước” làm bằng chứng kiểm soát.

## 16. Ngoại lệ SoD trong quản trị IAM: ai tạo account, ai cấp admin?

Một tổ hợp xung đột điển hình:

| Role | Năng lực |
| --- | --- |
| **IdentityProvisioner** | Tạo và cập nhật tài khoản |
| **PrivilegedAccessApprover** | Phê duyệt cấp role đặc quyền |
| **RoleGrantOperator** | Thực thi grant đã được duyệt |
| **AuditLogAdministrator** | Cấu hình/quan sát một số nhật ký |

Nếu một người có thể **tự tạo tài khoản, tự duyệt cấp admin rồi xóa dấu vết**, họ có thể tạo đường truy cập ngoài kiểm soát. Một ngoại lệ vận hành IAM phải:

1. Tách **ý định yêu cầu** khỏi **phê duyệt quyền** và **lệnh cấp quyền**.
2. Giới hạn role, target tenant và thời gian nếu buộc phải kiêm nhiệm.
3. **Cấm self-approval** tại workflow theo verified person identity.
4. Bảo đảm **audit độc lập** mà người thao tác không thể sửa.
5. Kiểm tra **grant được duyệt thực sự trùng role/scope/expiry được áp dụng**.
6. Theo dõi những tài khoản/nhóm mới được tạo trong khoảng ngoại lệ.
7. Thu hồi role tạm và session/token cần thiết, sau đó đối soát.

**Một tài khoản phụ hoặc service account không được dùng để che cùng người thật kiểm soát toàn bộ chuỗi công việc**. Cần xem owner và actor ở từng bước, không chỉ username khác nhau.

## 17. Đánh giá rủi ro trước khi duyệt ngoại lệ

Không phải mọi xung đột có mức nghiêm trọng giống nhau. Các chiều cần đánh giá:

| Chiều | Câu hỏi |
| --- | --- |
| **Business impact** | Nếu quy trình dừng vì không có ngoại lệ, thiệt hại gì? |
| **Fraud/abuse opportunity** | Chủ thể có thể tự khởi tạo và hoàn tất giao dịch nhạy cảm không? |
| **Resource sensitivity** | Dữ liệu/tài nguyên là production, tài chính hay thông tin cá nhân? |
| **Privilege breadth** | Action/resource scope một dự án hay toàn tổ chức? |
| **Duration** | Một ca trực, hai tuần hay không giới hạn? |
| **Number of affected users** | Một chủ thể hay cả nhóm? |
| **Detection quality** | Kiểm soát độc lập có phát hiện đủ loại hành vi không? |
| **Reversibility** | Có thể đảo ngược một thay đổi hay lệnh thanh toán không? |
| **Compensating strength** | Kiểm soát phòng ngừa hay chỉ hậu kiểm? |
| **Residual risk appetite** | Ai có thẩm quyền chấp nhận mức rủi ro còn lại? |

### Risk statement minh họa

~~~text
Risk:
    Employee có thể tạo và duyệt cùng một giao dịch,
    dẫn tới bỏ qua kiểm tra độc lập.

Likelihood drivers:
    Tập quyền xung đột, quyền thường trực, giám sát không đầy đủ.

Impact drivers:
    Hạn mức giao dịch, khả năng chuyển tiền, dữ liệu liên quan.

Proposed controls:
    Cấm tự duyệt ở backend; người thứ hai xác nhận trước giải ngân;
    giới hạn cost-center và số tiền; JIT trong ca trực; audit độc lập.

Residual risk:
    Do risk owner có thẩm quyền đánh giá/chấp nhận,
    không tự coi là bằng 0 khi đã thêm một số kiểm soát.
~~~

Không có một công thức điểm số chung cho mọi tổ chức. **Risk score** giúp ưu tiên review, không thay quyết định của người có thẩm quyền hoặc những hard deny không được miễn trừ.

## 18. Scope và duration: ngoại lệ càng hẹp càng tốt

Một exception nên định nghĩa ít nhất:

~~~text
subject            = iam-482
employmentRelation = emp-org-a-01
ruleId             = SOD-AP-007
conflictingRoles   = [InvoiceCreator, InvoiceApprover]
targetSystem       = finance-saas
targetTenant       = org-a
resourceScope      = cost-center-C7
actions            = [CREATE_INVOICE, APPROVE_OTHER_USER_INVOICE]
effectiveFrom      = 2026-12-01T09:00:00+07:00
effectiveUntil     = 2026-12-15T18:00:00+07:00
condition          = actor != creator of the same invoice
controlOwner       = independent-finance-controller
~~~

Đây là dữ liệu minh họa, không phải rule engine chính thức. Điều kiện **actor != creator** phải dùng **stable identity IDs** và dữ liệu giao dịch tin cậy, không so tên hiển thị hay email.

Nếu exception chỉ cần cho một batch, nên giới hạn vào **batch, repository, project, environment hoặc giao dịch cụ thể**. Nếu chỉ cần trong lúc xử lý incident, có thể dùng **JIT activation** với tự hết hạn. Không vì tiện cấu hình mà cấp **global admin vô thời hạn**.

**Time-bound grant chưa đủ nếu sau expiresAt API vẫn chấp nhận token đã cấp**. Cần chính sách thu hồi/recheck phù hợp với resource server và thời hạn yêu cầu.

## 19. Quyết định phê duyệt: approval cho quyền khác approval cho ngoại lệ

Khi một người yêu cầu giữ hai role xung đột, thường có **ít nhất hai câu hỏi riêng**:

1. Có căn cứ hợp lệ để cấp từng role theo **least privilege** không?
2. Có được chấp nhận **rủi ro kết hợp hai role** dưới các kiểm soát bổ sung không?

Manager có thể duyệt nhiệm vụ, nhưng chưa chắc được phép chấp nhận rủi ro SoD. Resource owner có thể cấp quyền trên tài nguyên nhưng cần security/risk owner đồng ý với một số ngoại lệ.

Ví dụ:

| Phê duyệt | Mục đích | Bằng chứng |
| --- | --- | --- |
| Access approval | Có được cấp role cho nhiệm vụ và scope không? | Business justification, target, duration |
| SoD exception approval | Có chấp nhận xung đột với điều kiện nào không? | Rule, residual risk, compensating controls |
| Control owner acceptance | Biện pháp bù trừ có khả thi và được vận hành không? | Quy trình, người kiểm tra, tần suất, test |
| Privileged/PAM approval | Có được activate role nhạy cảm tại một thời điểm không? | Incident/ticket, JIT window, authentication assurance |

**APPROVED_SOD_EXCEPTION không đồng nghĩa role đã được cấp**. IAM/IGA còn phải kiểm tra quyền, identity, tenant và approval khi gửi provisioning.

## 20. Dữ liệu một bản ghi SoD exception

Một bản ghi nên giúp giải thích chính xác **ai được phép làm gì, tại sao, ai chấp nhận rủi ro và khi nào hết hiệu lực**.

~~~json
{
  "exceptionId": "sod-ex-2026-019",
  "ruleId": "SOD-AP-007",
  "ruleVersion": "v5",
  "requesterIdentityId": "iam-manager-17",
  "beneficiaryIdentityId": "iam-482",
  "employmentRelationId": "emp-org-a-01",
  "identityType": "EMPLOYEE",
  "targetSystem": "finance-saas",
  "tenantId": "org-a",
  "resourceScope": "cost-center-C7",
  "conflictingEntitlements": [
    "InvoiceCreator",
    "InvoiceApprover"
  ],
  "exceptionReason": "Temporary staffing gap",
  "compensatingControlIds": [
    "INVOICE_CREATOR_NOT_APPROVER",
    "INDEPENDENT_PRE_RELEASE_CHECK"
  ],
  "riskRating": "HIGH",
  "residualRiskDecision": "ACCEPTED_WITH_CONDITIONS",
  "riskOwnerRef": "finance-risk-owner",
  "approvedByRefs": [
    "finance-resource-owner",
    "security-sod-approver"
  ],
  "validFrom": "2026-12-01T09:00:00+07:00",
  "validUntil": "2026-12-15T18:00:00+07:00",
  "status": "APPROVED_NOT_ACTIVATED",
  "verifiedEffectiveAccess": "UNKNOWN"
}
~~~

Đây là **schema minh họa**; không phải SCIM/OIDC hay chuẩn luật định. Các trường **ruleVersion, beneficiary, tenant, scope, controls, approver, expiry** phải được ràng buộc với nhau. Nếu role hoặc SoD rule đổi nội dung sau approval, cần đánh giá lại, không tự áp dụng ngoại lệ cũ cho permission rộng hơn.

Không lưu mật khẩu, OAuth token, client secret hay private key trong bản ghi exception.

## 21. State machine quản lý vòng đời ngoại lệ

~~~mermaid
stateDiagram-v2
    [*] --> DETECTED_CONFLICT
    DETECTED_CONFLICT --> REQUESTED: Có lý do xin ngoại lệ
    DETECTED_CONFLICT --> RESOLVED_WITHOUT_EXCEPTION: Thu hẹp/tách role
    REQUESTED --> RISK_REVIEW
    RISK_REVIEW --> REJECTED: Rule cấm hoặc rủi ro không chấp nhận
    RISK_REVIEW --> NEEDS_INFO: Thiếu căn cứ/control
    NEEDS_INFO --> RISK_REVIEW: Bổ sung thông tin
    RISK_REVIEW --> APPROVED_NOT_ACTIVATED: Có đủ approval độc lập
    APPROVED_NOT_ACTIVATED --> ACTIVE_CONTROLLED: Revalidate và activate
    APPROVED_NOT_ACTIVATED --> CANCELLED: Mất eligibility hoặc hủy
    ACTIVE_CONTROLLED --> SUSPENDED: Control thất bại hoặc incident
    SUSPENDED --> ACTIVE_CONTROLLED: Phê duyệt tái kích hoạt hợp lệ
    ACTIVE_CONTROLLED --> EXPIRING: Gần đến hạn
    EXPIRING --> REVOKING: Hết hạn/không gia hạn
    ACTIVE_CONTROLLED --> REVOKING: Mover/Leaver hoặc revoke khẩn
    SUSPENDED --> REVOKING: Yêu cầu thu hồi
    REVOKING --> UNVERIFIED: Đã gửi revoke, chưa đủ readback
    UNVERIFIED --> VERIFIED_CLOSED: Quyền và exception đã bị chặn đúng
    UNVERIFIED --> BLOCKED: Target còn quyền hoặc lỗi connector
    BLOCKED --> UNVERIFIED: Khắc phục và thử lại
    REJECTED --> [*]
    CANCELLED --> [*]
    RESOLVED_WITHOUT_EXCEPTION --> [*]
    VERIFIED_CLOSED --> [*]
~~~

**Hết hạn một exception không đồng nghĩa mọi role thành viên đều phải bị xóa** nếu có role vẫn được phê duyệt độc lập. Cần thu hồi **phần quyền hoặc tổ hợp xung đột được cấp trên căn cứ ngoại lệ**, và giữ quyền hợp lệ không xung đột.

**Đóng ticket không phải bằng chứng quyền đã mất**. Trạng thái **UNVERIFIED/BLOCKED** phải có owner và deadline khi connector hoặc hệ thống đích không xác nhận được.

## 22. Quản lý ngoại lệ theo Joiner lifecycle

Khi một người mới tham gia tổ chức, hệ thống thường tính **birthright access** từ job, department hoặc organization. Một role mapping sơ suất có thể tự cấp **tổ hợp quyền xung đột** ngay lúc Joiner.

Quy trình an toàn:

1. **HRIS/nguồn bảo trợ** xác minh person, employment, start date và job.
2. **IAM/IGA** tạo hoặc liên kết identity và tính tập quyền mục tiêu.
3. **SoD engine** kiểm tra xung đột **trước khi grant**, bao gồm role kế thừa và quyền trực tiếp ở target.
4. Với xung đột, thử **role ít quyền hơn** hoặc chia nhiệm vụ.
5. Nếu thật sự cần ngoại lệ, lấy **approval và compensating controls** trước khi activate.
6. **IdP/SCIM/API provisioning** chỉ cấp quyền đúng phạm vi đã duyệt.
7. **PDP/PEP/workflow** kiểm tra dynamic SoD và mọi điều kiện còn hiệu lực.
8. Đọc lại role/ACL và kiểm thử đường **được phép/bị từ chối**.

**Người mới có thể được tạo account trước ngày bắt đầu nhưng không được tự nhận quyền xung đột sớm**, trừ một chính sách onboarding độc lập có phạm vi hợp lệ. Không dùng ngoại lệ SoD để che sai role baseline.

## 23. Quản lý ngoại lệ theo Mover lifecycle

**Mover** thường là nguyên nhân của **privilege accumulation**: quyền từ dự án/nhóm trước còn lại trong khi quyền mới được cấp.

Ví dụ nhân viên Hà chuyển từ vai trò **InvoiceCreator** sang **InvoiceApprover**:

| Quyền | Trước Mover | Sau Mover mong muốn | Rủi ro |
| --- | --- | --- | --- |
| InvoiceCreator | Có | Thu hồi nếu không còn nhiệm vụ | Vẫn có thể tự tạo |
| InvoiceApprover | Chưa có | Cấp sau phê duyệt | Có thể tự duyệt cùng giao dịch |
| Direct ACL tạo hóa đơn | Có ở SaaS | Cần kiểm tra/gỡ | SoD conflict dù đã xóa group |
| OAuth PAT ghi dữ liệu | Có thể còn | Cần xem token và grant | Đường quyền tồn dư ngoài IdP |

Nếu cần bàn giao hai vai trò trong **một tuần**, ngoại lệ có thể được đề nghị, nhưng phải:

- Chỉ rõ **hạn, scope, role và những giao dịch áp dụng**.
- Áp dụng **dynamic SoD** để Hà không tự duyệt hóa đơn mình tạo, nếu policy yêu cầu.
- Có reviewer độc lập cho nghiệp vụ nhạy cảm.
- Thu hồi **InvoiceCreator và các đường quyền liên quan** sau bàn giao.
- Đối soát quyền còn hiệu lực tại API, không chỉ nhóm IdP.

**Một SoD exception được phê duyệt ở vị trí cũ không tự đi theo nhân viên sang vị trí mới**. Khi nhiệm vụ/tenant/risk context thay đổi materially, cần đánh giá lại eligibility và phạm vi ngoại lệ.

## 24. Leaver: kết thúc quan hệ không được giữ ngoại lệ tồn dư

Khi **Leaver** được xác nhận từ nguồn có thẩm quyền, quyền và ngoại lệ phát sinh từ quan hệ đó phải được xử lý theo mốc cắt quyền. Không chờ đến chiến dịch recertification mới thu hồi.

Các bước:

1. Liên kết đúng **employmentRelationId** với exception và role/grant.
2. Đóng hoặc hủy những **request ngoại lệ đang chờ** của quan hệ đã kết thúc.
3. Ngăn callback approval cũ hoặc job retry **tái cấp role**.
4. Thu hồi role, nhóm, direct ACL, ownership, session, PAT/API key và OAuth grant liên quan theo hệ thống.
5. Nếu IdP account disabled, vẫn kiểm tra **SaaS local account/token/phiên riêng**.
6. Readback ở target, đánh giá **effective access** và ghi bằng chứng.

**SCIM deactivate không bảo đảm JWT access token đã cấp mất hiệu lực ngay**. API chỉ xác minh chữ ký và exp có thể còn chấp nhận token đến hạn nếu không có denylist, introspection, security epoch hoặc policy recheck. Với quyền xung đột nhạy cảm, thời gian cắt thực tế cần phù hợp yêu cầu bảo mật.

Nếu person còn một hợp đồng hợp lệ ở **org-b** dù đã Leaver **org-a**, thu hồi đúng exception/role của org-a. Không tự xóa quyền org-b nếu được phê duyệt độc lập.

## 25. Workload/service account và ngoại lệ SoD

**Service account, service principal, CI/CD job và workload identity** cũng có thể tạo xung đột SoD:

- Một pipeline có thể **build, approve và deploy** production mà không có người kiểm tra độc lập.
- Một bot có thể vừa **tạo giao dịch** vừa **xác nhận giao dịch**.
- Một service principal có thể **cấp role IAM** và **thay đổi log/monitoring**.
- Một automation có thể quản lý **secret** đồng thời sửa cơ chế phát hiện sự cố.

| Thuộc tính workload | Cần xác minh |
| --- | --- |
| **serviceId/issuer** | Workload nào thật sự gọi API? |
| **ownerTeam/sponsor** | Ai chịu trách nhiệm, còn active không? |
| **deployment/environment** | Dev, staging hay production? |
| **source repository/pipeline** | Ai được sửa code/config điều khiển workload? |
| **permittedActions/resources** | Scope role/credential có đúng nhiệm vụ? |
| **approval chain** | Có người độc lập xem xét thay đổi nhạy cảm không? |
| **credential lifecycle** | Secret, certificate, federation, token có hạn/rotate không? |
| **SoD control** | Có tách build, review, deploy và audit khi cần không? |

Nếu workload cần tạm thời kiêm hai bước vì incident, ngoại lệ phải gắn với **serviceId, phiên bản deployment, môi trường và task/incident**, có **owner đủ thẩm quyền** và log phù hợp.

**Không dùng một nhân viên bấm MFA push thay cho mọi call máy–máy**. Workload cần chứng thực máy, quyền tối thiểu, policy về môi trường và kiểm soát change approval; việc con người duyệt một lần không làm mọi hành động sau đó mặc nhiên hợp lệ.

## 26. Emergency access và break-glass: trường hợp đặc biệt

**Break-glass** là quy trình truy cập khẩn cấp khi các cơ chế thông thường không thể đáp ứng yêu cầu phục hồi hoặc an toàn. Nó có thể liên quan SoD nhưng **không đồng nghĩa ngoại lệ SoD thông thường**.

Một đường break-glass nên được **thiết kế, chấp thuận và thử nghiệm trước**, với:

- Điều kiện kích hoạt sự cố rõ ràng.
- Identity/account/cơ chế chứng thực đã được quản lý.
- Scope và thời hạn quyền tối thiểu có thể.
- Tín hiệu khẩn cấp/ticket incident và người chịu trách nhiệm.
- Audit độc lập và cảnh báo gần thời gian thực.
- Kiểm tra sau sự kiện bởi người không thực hiện thao tác.
- Thu hồi session/credential/role và review lại nguyên nhân.

Nếu có **hard SoD rule không được miễn trừ**, break-glass không tự tạo quyền vi phạm. Tùy nghĩa vụ áp dụng, có thể cần quy trình sự cố khác mà vẫn giữ kiểm soát độc lập ở giao dịch không thể đảo ngược.

**Tránh đường “cứ ghi incidentId thì được phép tất cả”**. IncidentId do client nhập chỉ là tham chiếu, phải được xác minh với hệ thống sự cố/approval đáng tin.

## 27. IdP/SSO/MFA: xác thực mạnh không tự giải quyết SoD

**IdP/SSO** giúp xác minh chủ thể và phát hành kết quả authentication. **MFA/phishing-resistant authentication** giảm khả năng mạo danh, nhưng không ngăn một người **đã xác thực hợp lệ** tự duyệt công việc của mình.

| Điều kiện | Bảo vệ gì? | Không tự bảo vệ gì? |
| --- | --- | --- |
| IdP login thành công | Nhận dạng/đăng nhập theo trust | Không chứng minh được role xung đột là hợp lệ |
| MFA đầy đủ | Nâng assurance của phiên | Không chứng minh SoD độc lập |
| SSO tại SaaS | Dùng kết quả xác thực chung | Không tự thu hồi direct ACL hoặc PAT |
| IdP group update | Thay một đường quyền | Không bảo đảm session/JWT/role cục bộ đã đổi |
| Reauthentication/step-up | Xác minh lại chủ thể khi thao tác nhạy cảm | Không thay yêu cầu người thứ hai phê duyệt |

Một ngoại lệ SoD cho **role quản trị IAM** có thể yêu cầu MFA chống phishing và phiên mới, nhưng vẫn phải có **approval độc lập và kiểm soát giới hạn nhiệm vụ**.

Trong OIDC, các claim như **acr, amr và auth_time** chỉ hữu ích khi ứng dụng và IdP thống nhất ngữ nghĩa. Không tự suy một chuỗi amr bất kỳ đã đáp ứng quy định về step-up.

## 28. RBAC, ABAC và PBAC thực thi ngoại lệ thế nào?

**RBAC** quản lý role và quan hệ kế thừa; **ABAC** thêm điều kiện thuộc tính subject/resource/action/environment; **PBAC (Policy-Based Access Control)** tổ chức chính sách được **PDP** đánh giá và **PEP** thực thi.

Ngoại lệ SoD không nhất thiết phải cấp một role siêu quyền. Có thể giữ role nghiệp vụ nhưng thêm điều kiện ở authorization:

~~~text
ALLOW APPROVE_INVOICE(invoice) IF
    subject.hasRole("InvoiceApprover", invoice.organizationId)
    AND subject.employmentStatus == ACTIVE
    AND subject.organizationId == invoice.organizationId
    AND invoice.createdByIdentityId != subject.identityId
    AND invoice.amount <= subject.approvedLimit
    AND noPriorityDeny

OTHERWISE DENY
~~~

Nếu công ty cho phép người dùng kiêm role InvoiceCreator, điều kiện **creator != approver** vẫn được thực thi tại cấp giao dịch. Đây là **dynamic SoD** hiệu quả hơn việc chỉ ẩn nút Approve khi người dùng tạo invoice trên UI.

Đối với một ngoại lệ thay đổi điều kiện SoD, policy nên kiểm tra:

~~~text
exception = trustedExceptionStore.findActive(
    subjectId,
    conflictRuleId,
    tenantId,
    resourceScope,
    evaluationTime
)

if exception.valid
   AND exception.approvalsVerified
   AND exception.compensatingControlsOperational
   AND exception.residualRiskAccepted:
       evaluateOnlyExplicitlyAllowedExceptionPath()
else:
       enforceNormalSoDRule()
~~~

Đây là **mã giả**, không phải quy tắc ngôn ngữ XACML, OPA/Rego hay Spring Security. **Một record ngoại lệ tồn tại không đủ để Permit**; cần đúng subject, scope, thời hạn, policy và tình trạng kiểm soát bù trừ.

## 29. Đừng tin scope hoặc role do client tự khai

Ví dụ request HTTP:

~~~http
POST /api/org-a/invoices/inv-77/approve HTTP/1.1
Host: finance.example.invalid
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
X-SOD-Exception: sod-ex-2026-019
X-Role: FinanceAdmin
~~~

**Header X-SOD-Exception và X-Role không phải bằng chứng có quyền**. Client có thể tự đặt chúng. API/PEP phải:

1. Xác minh token/session đúng issuer, audience, hạn, scope và trạng thái thu hồi.
2. Xác định **identity ổn định**, không tin userId do request body tự khai.
3. Tải **invoice metadata, createdBy và organization** từ backend tin cậy.
4. Truy vấn exception từ kho có thẩm quyền, kiểm tra trạng thái/version/time/scope.
5. Áp dụng SoD rule, workflow obligations và compensating controls.
6. Chặn khi policy Deny, NotApplicable hoặc không thể xác minh điều kiện bắt buộc.
7. Ghi decision và enforcement với correlation ID, không log token.

**ID token OIDC không dùng thay access token ở API**. OAuth scope **invoices:approve** chỉ là một điều kiện của token/client, không miễn SoD ở giao dịch.

## 30. Kết hợp quyền, role hierarchy và SoD conflict gián tiếp

Một người có thể không được cấp hai role xung đột dưới tên chính thức, nhưng vẫn có quyền thông qua:

- Group lồng nhau hoặc kế thừa role.
- **Direct ACL** bên ngoài IdP.
- Quản lý ownership của tài nguyên.
- OAuth token/PAT có scope thao tác tương đương.
- Cloud IAM permission cho phép **tự cấp role, impersonate hoặc giả lập service principal**.
- Permission thay đổi policy/workflow, từ đó tạo đường vượt SoD.
- Workload do cùng người điều khiển thực hiện bước thứ hai.

Ví dụ:

~~~text
User roles:
    DataEntryOperator
    ProjectSupport

Nested role:
    ProjectSupport -> FinanceApprover

Direct SaaS ACL:
    InvoiceEditor

Effective:
    CREATE_INVOICE + APPROVE_INVOICE + EDIT_INVOICE
~~~

Nếu chỉ kiểm tra tên role cấp trực tiếp, hệ thống có thể **không phát hiện conflict**. SoD engine hoặc quá trình review cần tính **effective permissions và actor capability**, bao gồm đường delegation/impersonation có thể liên quan.

Tuy nhiên **khả năng thực thi thật** còn phụ thuộc explicit deny, ABAC, resource scope và workflow gates. Một role có wildcard là tín hiệu rủi ro nhưng không tự chứng minh mọi action đều được ALLOW.

## 31. Phát hiện ngoại lệ SoD hợp lệ và bất hợp lệ

Nên phân biệt:

| Tình huống | Phân loại |
| --- | --- |
| Conflict có approval ngoại lệ hợp lệ, control đang hoạt động, còn hạn | **APPROVED_CONTROLLED_EXCEPTION** |
| Conflict có approval nhưng control không hoạt động | **CONTROL_FAILURE / SUSPEND_REVIEW** |
| Conflict có ngoại lệ đã hết hạn | **EXPIRED_EXCEPTION / REMEDIATION_REQUIRED** |
| Conflict có role thực tế nhưng không thấy exception | **UNAPPROVED_CONFLICT** hoặc cần điều tra nguồn dữ liệu |
| Chỉ thấy hai role có tên tương tự nhưng không cùng resource scope | **POSSIBLE_FALSE_POSITIVE**, cần phân tích effective |
| Identity/account mapping không chắc chắn | **UNVERIFIED_IDENTITY_LINK** |
| Target không thể đọc ACL/token hoặc PEP decision | **UNVERIFIED_EFFECTIVE_ACCESS** |
| Ngoại lệ dành cho org-a bị dùng tại org-b | **OUT_OF_SCOPE_EXCEPTION** |
| Ngoại lệ từng hợp lệ nhưng beneficiary đã Mover/Leaver | **REVALIDATION_REQUIRED / REVOKE** |

**Ngoại lệ đã được phê duyệt không xóa sự tồn tại của rủi ro**. Trong dashboard, nên phân biệt xung đột **được xử lý bằng ngoại lệ có điều kiện** với xung đột **đã được loại bỏ hoàn toàn**.

Không coi **Không tìm thấy log sử dụng** là bằng chứng không có conflict. Một quyền ít dùng hoặc chưa dùng vẫn có thể tạo khả năng gian lận hoặc leo thang quyền.

## 32. Quản lý thời hạn, gia hạn và recertification ngoại lệ

SoD exception thường nên có **expiresAt**, kỳ review và điều kiện mất hiệu lực. Mốc review được định nghĩa theo mức rủi ro, không có một khoảng 30/60/90 ngày phù hợp cho mọi tổ chức.

Trước khi gia hạn:

1. **Nhu cầu** còn tồn tại không? Dự án hoặc ca trực đã kết thúc chưa?
2. **Role và SoD rule** có thay đổi phiên bản hoặc phạm vi không?
3. **Reviewer/owner** còn có thẩm quyền và độc lập không?
4. **Compensating controls** có được thực thi và có bằng chứng hiệu quả không?
5. Có **vi phạm SoD giao dịch**, incident hoặc điều tra chưa đóng không?
6. Có thể thay thế bằng **role hẹp hơn hoặc JIT** không?
7. Scope, thời hạn mới và residual risk có được duyệt lại không?

**Không tự gia hạn khi approver im lặng hoặc recertification timeout**. Một exception hết hạn mà chưa có phê duyệt mới cần được xử lý theo policy an toàn, không mặc định tiếp tục Permit.

Với các ngoại lệ đã cấp quyền tồn tại ở nhiều đích, **cần thu hồi tại đích và đọc lại**, không chỉ thay nhãn trạng thái exception từ ACTIVE sang EXPIRED.

## 33. Nguyên tắc khi mất kiểm soát bù trừ

Giả sử một ngoại lệ cho phép operator xử lý giao dịch với điều kiện **reviewer độc lập phải kiểm tra trước giải ngân**. Nếu hệ thống review bị lỗi:

- Không được tự động cho phép giao dịch vì “đã có ngoại lệ”.
- PEP/workflow phải tuân theo **fail-closed hoặc đường vận hành dự phòng được phê duyệt**, đặc biệt với thao tác không thể hoàn tác.
- Hệ thống cần phân biệt **DENY vì policy** với **INDETERMINATE/ERROR vì thiếu bằng chứng kiểm soát**.
- Phải cảnh báo control owner và record sự cố.
- Nếu policy cho phép fallback, cơ chế dự phòng phải bảo đảm **tính độc lập và bằng chứng tương đương đã được chấp thuận**, không phải một người tự xác nhận hai lần.

Ví dụ:

~~~text
Control status:
    INDEPENDENT_PRE_RELEASE_CHECK = UNAVAILABLE

Decision:
    Do not release payment under the SoD exception.
    Mark operation BLOCKED/CONTROL_UNAVAILABLE.
    Route to approved alternative control or incident process.
~~~

**Sự tồn tại của log không tự là cơ chế bù trừ hợp lệ khi chẳng ai giám sát và không có quy trình xử lý ngoại lệ.**

## 34. Audit: ngoại lệ cần lưu những bằng chứng nào?

Một bản ghi audit phải giúp trả lời:

- SoD rule nào bị xung đột, **phiên bản** nào, phạm vi nào?
- Chủ thể nào yêu cầu, beneficiary là ai, account/workload nào thực thi?
- Tại sao không thể giải quyết bằng cách tách nhiệm vụ hoặc thu hẹp role?
- Ai chấp thuận **access entitlement**, ai chấp nhận **residual risk**?
- Kiểm soát bù trừ là gì, ai vận hành, bằng chứng ở đâu?
- Ngoại lệ được kích hoạt khi nào, hết hạn khi nào, có bị sửa giữa chừng không?
- Có giao dịch thực tế nào thuộc exception, có vi phạm dynamic SoD không?
- Có incident/control failure/break-glass nào liên quan không?
- Khi thu hồi, **quyền đã bị chặn thật ở hệ thống đích** chưa?

Ví dụ JSON audit metadata:

~~~json
{
  "eventId": "sod-audit-2026-0081",
  "exceptionId": "sod-ex-2026-019",
  "ruleId": "SOD-AP-007",
  "ruleVersion": "v5",
  "identityRef": "iam-482",
  "employmentRef": "emp-org-a-01",
  "targetSystem": "finance-saas",
  "tenantId": "org-a",
  "resourceScope": "cost-center-C7",
  "eventType": "EXCEPTION_ACTIVATED",
  "approvedByRefs": [
    "finance-resource-owner",
    "security-sod-approver"
  ],
  "compensatingControlStatus": "VERIFIED_ACTIVE",
  "policyVersion": "sod-policy-v12",
  "effectiveFrom": "2026-12-01T09:00:00+07:00",
  "effectiveUntil": "2026-12-15T18:00:00+07:00",
  "enforcementState": "CONDITIONAL",
  "occurredAt": "2026-12-01T09:00:01+07:00",
  "correlationId": "exception-task-119"
}
~~~

Đây là **schema minh họa**, không phải định dạng chuẩn của một sản phẩm. Không lưu **bearer token, refresh token, password, private key, OTP seed hoặc toàn bộ hồ sơ HR**. Audit quyền nhạy cảm cần có **phân quyền đọc và bảo vệ chống sửa đổi trái phép**.

**Log approval và log enforcement là hai loại bằng chứng khác nhau**. Người có ngoại lệ được duyệt không có nghĩa API đã thực thi đúng kiểm soát khi thực hiện hành động.

## 35. Mã giả xử lý quyết định cấp SoD exception

Đây là mã giả nghiệp vụ, không phải API trực tiếp của một IGA hay policy engine cụ thể:

~~~text
activateSoDException(exceptionId, actor, now):
    ex = exceptionStore.loadWithVersion(exceptionId)

    if ex.status != APPROVED_NOT_ACTIVATED:
        return CONFLICT_STALE_EXCEPTION

    if now < ex.validFrom or now >= ex.validUntil:
        return OUTSIDE_APPROVED_WINDOW

    if not verifyApproverChain(ex.approvals, ex.rule, ex.scope):
        return MISSING_VALID_APPROVAL

    if ex.rule.prohibitsAnyException:
        return HARD_DENY

    identity = resolveTrustedSubject(ex.beneficiaryIdentityId)
    if identity.isUnverified:
        return BLOCKED_IDENTITY_LINK

    relation = getCurrentRelation(identity, ex.employmentRelationId)
    if not relation.isActiveFor(ex.tenantId, now):
        return INELIGIBLE

    currentRule = loadCurrentSoDRule(ex.ruleId)
    if currentRule.versionRequiresReapproval(ex.ruleVersion):
        return REVALIDATION_REQUIRED

    controls = evaluateRequiredCompensatingControls(ex)
    if not controls.areOperationalAndIndependent:
        return CONTROL_UNAVAILABLE_NO_GRANT

    if not entitlementApprovalStillValid(ex):
        return MISSING_ACCESS_APPROVAL

    markActivationAuthorizedAtomically(ex, expectedVersion=ex.version)
    enqueueIdempotentScopedGrant(ex)
    audit("EXCEPTION_ACTIVATION_AUTHORIZED", ex, actor)
    return ACTIVATION_PENDING_TARGET_VERIFICATION
~~~

**Hàm chỉ đánh dấu đã được phép kích hoạt**, chưa tuyên bố quyền đã có tại target. Kết quả provisioning và quyền thực thi cần **readback/kiểm chứng**. Khi hệ thống hoạt động bất đồng bộ, phải tránh worker retry hoặc event cũ làm cấp lại role sau khi exception đã hết hạn.

## 36. Mã giả thực thi Dynamic SoD tại giao dịch

~~~text
approveInvoice(actorSession, invoiceId, exceptionReference):
    actor = requireVerifiedIdentity(actorSession)
    invoice = invoiceRepository.loadAuthoritative(invoiceId)

    requireValidAccessTokenAndScopeIfApplicable(actorSession, "invoice:approve")
    requireRole(actor, "InvoiceApprover", invoice.organizationId)

    if invoice.createdByIdentityId == actor.identityId:
        return DENY_SELF_APPROVAL

    if not actor.hasCurrentAuthorizedRelation(invoice.organizationId):
        return DENY_TENANT_OR_EMPLOYMENT

    if actor.hasStaticRoleConflict:
        ex = loadTrustedActiveException(actor, exceptionReference)
        if not ex.matches(invoice.organizationId, invoice.costCenter, now()):
            return DENY_SOD_CONFLICT
        if not requiredControlsAreOperational(ex, invoice):
            return DENY_CONTROL_UNAVAILABLE

    if violatesOtherPolicy(actor, invoice):
        return DENY

    return executeApprovalAtomicallyWithAudit(invoice, actor)
~~~

Đây là ví dụ **bảo thủ**: ngay cả khi có exception cấp role, **self-approval vẫn bị cấm**. Nếu có chính sách khác cho một tình huống đặc biệt, cần thiết kế kiểm soát độc lập có căn cứ rõ; không thay điều kiện bằng **exceptionReference != null**.

Với thao tác giao dịch, có nguy cơ **Time-of-Check-to-Time-of-Use (TOCTOU)**: invoice có thể đổi người tạo, tổ chức, số tiền hoặc trạng thái giữa lúc kiểm tra và lúc phê duyệt. Cần **transaction/locking/version check** hoặc cơ chế nhất quán tương đương để đảm bảo quyết định dựa trên dữ liệu được áp dụng.

## 37. Phê duyệt đến muộn, phiên bản và race condition

Một exception có thể bị ảnh hưởng bởi nhiều sự kiện cùng lúc:

~~~text
09:00  User xin exception cho quyền Atlas
09:02  Risk owner Approve
09:03  HRIS ghi sự kiện Mover Atlas -> Nova
09:04  Job cấp role nhận approval event đến trễ
09:05  Job thu hồi Atlas cũng đang chạy
09:06  Nếu không revalidate, role Atlas có thể bị cấp lại
~~~

Các kiểm soát:

1. Lưu **exceptionId, version, grantId, sourceEventId và effectiveAt**.
2. **Atomic state transition/optimistic locking** ngăn vừa APPROVED vừa EXPIRED trái quy tắc.
3. Mọi worker trước khi cấp phải kiểm tra **employment/assignment, approval, rule version và thời hạn hiện hành**.
4. Dùng **idempotency key** để retry không tạo grant trùng hoặc mở rộng expiry.
5. Nếu connector timeout, **readback target trước khi retry**, không giả định lệnh chưa áp dụng.
6. Khi có Leaver/emergency revoke, ưu tiên trạng thái thu hồi theo chính sách và **không cho event cũ ghi đè**.
7. Nếu exception đổi scope/role/control, phải **re-review delta** trước khi áp dụng.

**Một approval hợp lệ ở thời điểm phát hành không tự động còn hợp lệ tại lúc cấp** nếu căn cứ nghiệp vụ đã thay đổi.

## 38. Reconciliation: chứng minh ngoại lệ đã chấm dứt thật

Khi đến **validUntil**, cần:

| Bước | Mục tiêu |
| --- | --- |
| **Stop new activation** | Không phát sinh phiên/quyền mới dựa trên exception hết hạn |
| **Revoke scoped grant** | Gỡ role/group/ACL được cấp trên căn cứ exception |
| **Invalidate decision cache** | Không dùng Permit từ policy/PIP snapshot cũ |
| **Handle token/session** | Chặn đường access token/PAT/session theo yêu cầu từng ứng dụng |
| **Read back target** | Xác nhận grant, direct role, nhóm, ACL thực tế |
| **Test effective access** | Những action bị cấm phải DENY trong scope |
| **Preserve other legitimate access** | Không vô tình xóa role độc lập không xung đột |
| **Audit and close** | Lưu evidence và trạng thái VERIFIED_CLOSED |

Một quyết định **REVOKE** chỉ là **ý định thu hồi**. SCIM Update/PATCH thành công chỉ cho biết connector/Service Provider xử lý theo contract, **không tự chứng minh local role, JWT hoặc PAT đã hết hiệu lực**.

Nếu không kiểm tra được quyền tại target vì API thiếu khả năng đọc hoặc phiên giám sát không có quyền, trạng thái nên là **UNVERIFIED**, có owner, hạn và biện pháp giảm rủi ro phù hợp.

## 39. Phát hiện vi phạm ngoại lệ trong vận hành

Các tín hiệu giám sát quan trọng:

| Tín hiệu | Ý nghĩa | Hành động |
| --- | --- | --- |
| Self-approval được hệ thống cho phép | Dynamic SoD bypass | Điều tra bảo mật, chặn đường sai |
| Role xung đột tồn tại không có exception | Unapproved conflict | Kiểm tra mapping và thu hồi theo risk |
| Exception ACTIVE sau validUntil | Residual exception | Revoke/reconciliation khẩn theo mức rủi ro |
| Compensating control không có log hoạt động | Có thể không được thực thi | Kiểm tra coverage, không suy control đạt |
| Người reviewer đồng nhất beneficiary | SoD của approval bị phá | Kiểm tra stable identity, sửa tuyến duyệt |
| Ngoại lệ org-a được dùng ở org-b | Cross-tenant misuse | PEP check đúng tenant/resource |
| Access token cũ còn Permit sau revoke | Stale authorization | Token/session/cache remediation |
| Workload đổi owner nhưng exception vẫn giữ owner cũ | Governance drift | Reassign, revalidate risk approval |
| Audit log bị sửa bởi beneficiary | Control independence failure | Bảo vệ log và quyền của monitor |
| Rule version đổi, exception không re-review | Policy drift | Require renewed authorization |

**Không có alert không chứng minh không có vi phạm**, đặc biệt khi dữ liệu giao dịch không đầy đủ hoặc API phụ không ghi audit. Cần đo tỷ lệ endpoint/control coverage và khả năng giải thích từng decision.

## 40. KPI chương trình ngoại lệ SoD

| KPI | Mục tiêu | Lưu ý |
| --- | --- | --- |
| **Open SoD conflicts** | Số xung đột chưa được xử lý | Phân loại theo severity và nguồn |
| **Approved controlled exceptions** | Số ngoại lệ còn hiệu lực có điều kiện | Không coi bằng 0 rủi ro |
| **Expired exceptions still effective** | Quyền xung đột sau hạn | Phân biệt pending vs verified removal |
| **Exceptions without owner** | Phát hiện thiếu trách nhiệm | Owner đổi vai trò cần cập nhật |
| **Compensating control failure rate** | Đánh giá tính vận hành của control | Ghi coverage và tần suất test |
| **Self-approval blocked rate** | Khả năng chặn quyết định trái SoD | Nhiều block không tự bằng nhiều gian lận |
| **Time to verified revocation** | Tốc độ chặn quyền sau expiry/Mover/Leaver | Dựa trên target effective access |
| **Standing vs JIT exception usage** | Mức hạn chế thời gian quyền | Không làm giảm sẵn sàng ngoài kiểm soát |
| **Cross-tenant conflict exposure** | Nguy cơ vượt phạm vi pháp nhân | Dựa trên quyền thực, không chỉ role name |
| **Unverified exception ratio** | Độ đầy đủ của bằng chứng | UNKNOWN khác an toàn |
| **Recurring exception rate** | Tìm vấn đề thiết kế role/quy trình gốc | Đề xuất remediation lâu dài |
| **Independent review completion** | Hậu kiểm bởi người độc lập | Không chỉ đếm checkbox |

Không có một ngưỡng KPI chung phù hợp mọi tổ chức. Số lượng ngoại lệ giảm không tự chứng minh an toàn hơn nếu quy trình **ẩn xung đột hoặc ngừng thu thập quyền thực tế**.

## 41. Bộ kiểm thử ngoại lệ SoD

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| T01 | User thiếu role nghiệp vụ, nhưng có exception | Không tự grant role |
| T02 | Hai role xung đột, chưa có exception | Deny/hold theo policy |
| T03 | Exception có đủ approval, đúng tenant và còn hạn | Chỉ cho trong giới hạn đã duyệt |
| T04 | Beneficiary tự duyệt exception | Chặn nếu vi phạm SoD |
| T05 | Người tạo invoice tự duyệt chính invoice | DENY theo dynamic SoD |
| T06 | Người có hai role duyệt invoice của người khác | Có thể ALLOW nếu đủ điều kiện và exception |
| T07 | Compensating control bị timeout | Không tự cho phép đường rủi ro |
| T08 | Exception của org-a được dùng trên resource org-b | DENY |
| T09 | Scope cho cost-center C7, request C8 | DENY |
| T10 | Ngoại lệ hết hạn, token cũ còn claim role | Chặn theo policy thu hồi |
| T11 | User Mover sang project khác | Revalidate/thu hồi exception cũ |
| T12 | User Leaver đúng employment | Hủy pending exception và revoke |
| T13 | Person còn employment hợp lệ tại org-b | Không xóa nhầm quyền org-b |
| T14 | Workload owner nghỉ việc | Reassign owner và rà soát secret/grant |
| T15 | Role kế thừa tạo conflict không thấy ở direct role | Detector phải phát hiện effective conflict |
| T16 | Callback approval muộn sau EXPIRED | Không re-activate exception |
| T17 | Retry provisioning chạy hai lần | Idempotent, không mở rộng duration |
| T18 | Target SCIM báo success nhưng ACL vẫn ALLOW | Không VERIFIED_CLOSED |
| T19 | Reviewer không đủ quyền với classification | Không được phê duyệt rủi ro |
| T20 | Control audit chỉ tồn tại trên UI, API bypass | Integration test phát hiện |
| T21 | Rule version thay đổi permission materially | Re-review trước khi dùng exception cũ |
| T22 | SoD rule không cho phép miễn trừ | Hard deny dù có requester/manager approval |

**Unit test policy không thay integration test tại API/PEP**. Một rule có thể đúng nhưng endpoint batch, export hoặc service-to-service không gọi decision engine, dẫn tới bypass. Nên dùng dữ liệu kiểm thử đã được cho phép và kiểm tra đường **ALLOW** lẫn **DENY**.

## 42. Tình huống thực hành: ngoại lệ SoD do thiếu người khi kết sổ

**Bối cảnh:** Bộ phận kế toán của **org-a** cần xử lý hóa đơn cuối tháng cho **cost-center C7**. Nhân viên An đang giữ role **InvoiceCreator**. Người có role **InvoiceApprover** dự kiến nghỉ phép một tuần, nên manager đề nghị cấp thêm role Approver cho An từ **01/12 đến 07/12**.

Rule SoD hiện hành:

~~~text
SOD-AP-007:
    Một identity không được tự tạo và tự phê duyệt
    cùng một invoice trong cùng organization.

Review for static role conflict:
    Nếu có InvoiceCreator và InvoiceApprover,
    yêu cầu exception được kiểm soát theo policy.
~~~

### Bước 1 — Nhận diện xung đột và lựa chọn thay thế

IAM tính **effective access** của An tại SaaS, không chỉ xem nhóm IdP. Hệ thống phát hiện An đã có quyền CREATE và yêu cầu thêm APPROVE. Đội tài chính thử tìm reviewer dự phòng khác; không có người phù hợp trong ca trực, nên đề nghị **ngoại lệ role-level có thời hạn**, nhưng giữ **dynamic SoD ở cấp invoice**.

### Bước 2 — Đánh giá và phê duyệt

Resource owner xác nhận nhu cầu với cost-center C7. Risk/security owner xác nhận rule cho phép ngoại lệ có điều kiện. Kiểm soát bù trừ yêu cầu:

- Chỉ dùng role tại **org-a / cost-center C7**.
- An **không được duyệt invoice do An tạo**.
- Những invoice do An phê duyệt phải qua **kiểm tra độc lập** theo mức tiền đã quy định.
- Role Approver hoạt động trong **khoảng hạn đã duyệt** và được giám sát.
- Không dùng role để thay đổi SoD policy hoặc quyền log.

### Bước 3 — Provision và thực thi

IAM/IGA ghi exception, kiểm tra lại employment ACTIVE, resource scope, approval và risk decision. SCIM/API cấp role theo mapping của sản phẩm; resource server có PDP/PEP kiểm tra creatorId, organizationId và điều kiện control.

### Bước 4 — Kiểm thử

| Tình huống | Expected |
| --- | --- |
| An tạo invoice ở C7 | ALLOW nếu có quyền CREATE hợp lệ |
| An tự duyệt invoice An đã tạo | **DENY** |
| An duyệt invoice do người khác tạo ở C7, control đầy đủ | ALLOW khi đạt mọi điều kiện |
| An duyệt invoice ở C8 | **DENY** |
| An dùng exception tại org-b | **DENY** |
| Independent control không hoạt động | Không cho phép bước nhạy cảm |
| Đến 08/12, role Approver còn dùng được | **Không được**; phải thu hồi và kiểm chứng |

### Bước 5 — Hết hạn và đối soát

Ngày kết thúc, hệ thống ngăn activate mới, revoke role Approver được cấp theo exception, xử lý session/token/cached policy và kiểm tra API. Role **InvoiceCreator** của An có thể được giữ nếu còn công việc độc lập hợp lệ. Không xóa cả account hoặc toàn bộ quyền chỉ vì exception hết hạn.

### Biến thể: An chuyển bộ phận giữa thời gian hiệu lực

Nếu HRIS xác nhận An **Mover** sang Nova ngày 04/12, IAM phải tính lại nhu cầu của exception ngay lúc sự kiện có hiệu lực. Approval tới ngày 07/12 không tự cho phép giữ role nếu An không còn nhiệm vụ tại C7.

## 43. Câu hỏi tự kiểm tra

**Câu 1: Ngoại lệ SoD có phải là cho phép bỏ kiểm soát SoD không?**

**Trả lời:** Không. Đây là quyết định chấp nhận rủi ro có điều kiện, thường kèm kiểm soát bù trừ, scope, hạn, người owner và kiểm toán. Một số rule không cho ngoại lệ.

**Câu 2: Nếu An giữ cả Creator và Approver nhưng không được tự duyệt invoice do mình tạo, tổ chức đang dựa vào dạng SoD nào?**

**Trả lời:** Dynamic SoD ở cấp giao dịch, có thể kết hợp ngoại lệ cấp role nếu static conflict cần được xét riêng.

**Câu 3: Manager duyệt role Approver có đủ để chấp nhận SoD exception?**

**Trả lời:** Không nhất thiết. Tùy policy, cần resource owner và risk/security owner xác nhận rủi ro và kiểm soát bù trừ.

**Câu 4: Phê duyệt ngoại lệ đã có nhưng API vẫn cho An duyệt invoice của mình thì có đạt kiểm soát không?**

**Trả lời:** Không. Đây là lỗi enforcement hoặc workflow control cần được chặn/điều tra.

**Câu 5: Nếu ngoại lệ hết hạn nhưng SCIM đã gỡ group còn PAT vẫn có thể thao tác thì đã hoàn tất chưa?**

**Trả lời:** Chưa. Phải đánh giá quyền hiệu lực từ mọi đường liên quan và ghi trạng thái chưa xác minh nếu thiếu bằng chứng.

**Câu 6: Một service account có được xin ngoại lệ SoD không?**

**Trả lời:** Có thể theo chính sách với serviceId, owner, purpose, scope và kiểm soát độc lập; không tự cho phép máy tự tạo–tự duyệt chỉ vì không có người dùng đăng nhập.

**Câu 7: Tại sao exception của org-a không được dùng tại org-b?**

**Trả lời:** Vì approval, resource owner, rủi ro và quan hệ làm việc được xét trong phạm vi org-a; quyền không tự lan sang tổ chức khác.

**Câu 8: Có thể tự gia hạn ngoại lệ nếu reviewer quên phản hồi không?**

**Trả lời:** Không. Hết hạn phải xử lý theo chính sách thu hồi/chặn; gia hạn cần revalidation và phê duyệt hợp lệ.

## 44. Checklist quản lý ngoại lệ SoD

| Câu hỏi | Bằng chứng hoặc kiểm soát cần có |
| --- | --- |
| SoD rule có định danh và version rõ? | RuleId, static/dynamic scope, policy owner |
| Rule có cho phép ngoại lệ? | Danh sách hard deny và điều kiện miễn trừ |
| Có chứng minh nhu cầu công việc? | Business justification, incident/project/task |
| Đã xét phương án không cần exception? | Tách nhiệm vụ, role hẹp, JIT, alternate approver |
| Beneficiary được xác minh đúng? | Stable identity, person/employment/account mapping |
| Có phân biệt requester/approver/beneficiary? | Phê duyệt độc lập và SoD của approval |
| Các role/entitlement thực sự xung đột? | Effective permissions, hierarchy, direct ACL |
| Tenant và tài nguyên có giới hạn? | App, org, project, cost-center, action |
| Có thời hạn và mốc hiệu lực? | validFrom, validUntil, timezone/effectiveAt |
| Access approval và risk approval đủ? | Resource owner, risk/security authority theo tier |
| Biện pháp bù trừ có owner? | Control objective, trigger, independent reviewer |
| Kiểm soát bù trừ có hoạt động được? | Test, evidence, xử lý khi control lỗi |
| Static/dynamic SoD có phân biệt? | Role assignment và transaction-level enforcement |
| Có bảo đảm không tự duyệt cùng giao dịch? | Backend comparison theo stable actor/creator ID |
| Có giới hạn quyền admin/secret? | Least privilege, PAM/JIT, MFA assurance |
| Có giám sát cross-tenant/batch/API? | PEP checks và integration tests |
| Joiner có ngăn cấp tổ hợp xung đột mặc định? | SoD checks trước provisioning |
| Mover có đánh giá lại exception? | Expected access mới, revoke old access |
| Leaver có vô hiệu exception và pending jobs? | Source version, effective cutoff, token/session revoke |
| Workload có owner và policy riêng? | serviceId, environment, secret lifecycle |
| Có chống callback/event cũ? | State/version, idempotency, revalidation |
| Có recertification và gia hạn rõ? | Review cadence, new approval, không auto-renew |
| Có readback quyền sau khi thu hồi? | Assigned/effective rights ở target |
| Có audit và metric? | Decision, control evidence, expiry, exception status |
| Có cơ chế xử lý thiếu bằng chứng? | UNKNOWN/UNVERIFIED, owner và deadline |

## 45. Tổng kết

**Ngoại lệ SoD** là một cơ chế quản trị rủi ro có điều kiện khi **phân tách nhiệm vụ thông thường không thể áp dụng đầy đủ** cho một nhu cầu hợp lệ. Nó không xóa bản chất xung đột, không cho phép tự duyệt trái policy và không thay thế **least privilege, static/dynamic SoD, approval độc lập hoặc kiểm soát tại giao dịch**. Ngoại lệ đúng phải có **phạm vi hẹp, thời hạn rõ, người chấp nhận rủi ro đủ thẩm quyền, biện pháp bù trừ được thực thi và bằng chứng kiểm toán**.

Trong mô hình **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** xác nhận quan hệ lao động; **IAM/IGA** tính quyền mục tiêu, kiểm tra SoD và quản lý exception; **IdP/SSO/MFA** xác thực chủ thể; **SCIM/API** cấp hoặc thu hồi group/role; **RBAC/ABAC/PBAC với PDP/PEP** kiểm soát quyền hiệu lực theo role, thuộc tính, hành động, tài nguyên và ngữ cảnh. **Service/workload identities** cần owner và kiểm soát xung đột riêng. Tổ chức chỉ quản lý ngoại lệ đáng tin cậy khi **quyết định cấp quyền và quyết định chấp nhận rủi ro được tách bạch, quyền được giám sát trong suốt thời hạn, và trạng thái thu hồi thật sự được xác minh tại hệ thống đích** — từ đó hạn chế **quyền truy cập tồn dư** mà không làm mất những nhiệm vụ nghiệp vụ hợp lệ.
