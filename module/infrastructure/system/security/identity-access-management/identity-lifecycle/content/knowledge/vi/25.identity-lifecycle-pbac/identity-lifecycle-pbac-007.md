# Policy conflict trong PBAC: phát hiện, phân giải và kiểm soát xung đột chính sách IAM

> **Chương: PBAC (Policy-Based Access Control).** **Policy conflict** là tình huống hai hoặc nhiều quy tắc/chính sách có ảnh hưởng tới cùng một yêu cầu truy cập nhưng đưa ra kết quả, điều kiện hoặc nghĩa vụ không tương thích. Ví dụ, một chính sách cho phép nhân viên Tài chính đọc báo cáo, trong khi chính sách khác từ chối mọi truy cập của người đã nghỉ việc. Nếu hệ thống chọn Permit chỉ vì còn vai trò Tài chính, đó là lỗi nguy hiểm trong **quản lý vòng đời danh tính (IAM Identity Lifecycle)**. Bài học tập trung vào cách nhận diện xung đột, xác định thứ tự ưu tiên và ngữ nghĩa kết hợp chính sách, áp dụng **Joiner–Mover–Leaver**, đồng thời kiểm chứng quyền thực tế ở IdP, SSO, SCIM và ứng dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **policy conflict** trong PBAC và phân biệt xung đột chính sách với chồng lấn, dư thừa, khoảng trống chính sách và dữ liệu nguồn mâu thuẫn.
2. Mô hình hóa một yêu cầu gồm **subject, action, resource, context**, xác định các policy đồng thời áp dụng và hiệu lực **Permit/Deny**.
3. Hiểu các chiến lược **deny-overrides**, **permit-overrides**, **first-applicable**, **only-one-applicable**, hard guard và giới hạn của từng cách.
4. Xử lý thận trọng **NotApplicable, Indeterminate**, thuộc tính thiếu, policy lỗi, cache cũ và khi Policy Decision Point (PDP) không khả dụng.
5. Phân tích xung đột do **Joiner–Mover–Leaver**, quyền theo **RBAC/ABAC**, điều kiện SSO/MFA, Group qua SCIM và nhiều nguồn quản trị quyền.
6. Xây dựng quy trình rà soát, giải quyết, kiểm thử hồi quy, phát hành policy có phiên bản và lưu bằng chứng kiểm toán.
7. Tránh nhầm giữa **PDP quyết định Deny** với **PEP thực sự chặn truy cập**, qua đó giảm quyền truy cập tồn dư.

## 1. Bài toán mở đầu: hai chính sách cùng đúng nhưng kết quả khác nhau

Giả sử nhân viên Lan thuộc bộ phận Tài chính và từng có quyền xem báo cáo doanh thu. Hệ thống có:

- **Policy P1 — Role grant:** Permit report.read nếu subject có vai trò FinanceReader.
- **Policy P2 — Lifecycle restriction:** Deny các hành động nghiệp vụ nếu subject đã TERMINATED.
- **Policy P3 — Tenant isolation:** Deny nếu subject và báo cáo không thuộc cùng tenant hợp lệ.

Lúc 08:00, Lan còn ACTIVE, có FinanceReader và thuộc đúng tenant; P1 Permit, P2/P3 không áp dụng. Lúc 17:00, sự kiện **Leaver** có hiệu lực, nhưng Role FinanceReader vẫn còn trong một access token cấp trước đó. Nếu ứng dụng chỉ đọc P1 và không thực thi P2, Lan vẫn có thể xem báo cáo.

| Thời điểm | Role/claim đã cấp | Trạng thái vòng đời | Kết quả mong muốn |
| --- | --- | --- | --- |
| 08:00, trước Leaver | FinanceReader | ACTIVE | Permit nếu đủ các điều kiện khác. |
| 17:01, sau Leaver | FinanceReader còn trong JWT cũ | TERMINATED | Deny theo chính sách truy cập sau nghỉ việc. |
| 17:02, IdP đã khóa nhưng app còn cookie | App-local role vẫn tồn tại | TERMINATED | Deny ở ứng dụng; không chỉ ở IdP. |
| 17:03, PDP chưa đọc được lifecycle state | FinanceReader còn hiện diện | UNKNOWN | Không tự Permit khi điều kiện bắt buộc chưa xác minh. |

**Điểm cốt lõi:** xung đột phải được giải quyết bằng **ngữ nghĩa chính sách đã được phê duyệt**, không phụ thuộc vào thứ tự ngẫu nhiên của API, thứ tự Group được trả về hoặc rule nào tình cờ chạy trước.

## 2. Policy conflict là gì và khác những vấn đề lân cận ra sao?

**Policy conflict** là sự không tương thích trong các quy tắc tác động tới cùng một không gian yêu cầu. Có thể đó là **Permit và Deny cùng áp dụng**, hai nghĩa vụ thực thi không thể đồng thời đáp ứng, hoặc hai quy tắc tạo ra yêu cầu vận hành trái ngược.

Tuy nhiên, không phải mọi chính sách chồng lấn đều là lỗi.

| Hiện tượng | Ví dụ | Có nhất thiết là lỗi? |
| --- | --- | --- |
| **Permit/Deny conflict** | Policy role Permit, policy Leaver Deny cùng action/resource. | Phải có cách kết hợp minh bạch; trở thành lỗi nếu kết quả trái yêu cầu bảo mật. |
| **Overlap** | Hai policy đều Permit đọc báo cáo của cùng nhóm hợp lệ. | Không nhất thiết; có thể dự kiến. |
| **Redundancy** | Hai rule cùng điều kiện và kết quả, không tạo thêm khác biệt. | Có thể gây khó bảo trì, nhưng chưa chắc gây cấp quyền sai. |
| **Shadowing** | Rule có phạm vi rộng chạy trước che rule hẹp hơn. | Nguy hiểm nếu rule hẹp bắt buộc không được xét. |
| **Policy gap** | Không có rule nào áp dụng cho API export mới. | Cần default deny; không tự gọi là conflict. |
| **Attribute conflict** | HR nói department=FINANCE, ứng dụng nói SUPPORT. | Tranh chấp dữ liệu nguồn; có thể dẫn đến policy decision khác nhau. |
| **Provisioning drift** | IAM desired deny nhưng SaaS còn Group Admin. | Quyền thực tế lệch desired; không nhất thiết là xung đột giữa hai rule. |
| **Enforcement gap** | PDP trả Deny nhưng endpoint vẫn ghi dữ liệu. | Lỗi thực thi PEP, dù policy có thể hoàn toàn đúng. |
| **Exception conflict** | Quyền ngoại lệ tạm cho phép export nhưng hard guard cấm dữ liệu bị phong tỏa. | Cần làm rõ ngoại lệ có được vượt guard đó hay không. |

Vì vậy, khi báo lỗi phải nêu đúng **lớp xảy ra vấn đề**: định nghĩa policy, dữ liệu thuộc tính, thuật toán kết hợp, quá trình đồng bộ hay điểm thực thi.

### Một request được biểu diễn thế nào?

Các rule chỉ thực sự xung đột nếu **đồng thời liên quan** tới một request có thể tồn tại:

~~~text
request = {
    subject:  identity/role/department/lifecycle,
    action:   report.read,
    resource: report-id, tenant, classification,
    context:  time, session assurance, device, environment
}
~~~

Nếu P1 chỉ áp dụng **report.read** còn P2 chỉ áp dụng **report.export**, hai policy chưa mâu thuẫn cho cùng action. Nếu P1 áp dụng tenant A và P2 chỉ tenant B, cần kiểm tra vùng giao nhau thực sự trước khi báo conflict.

## 3. PBAC đặt policy ở đâu trong kiến trúc IAM?

**Policy-Based Access Control (PBAC)** tổ chức quyết định quyền thông qua các chính sách có thể quản trị, kết hợp, triển khai và kiểm toán. Một chính sách PBAC có thể dùng **role (RBAC)**, **thuộc tính (ABAC)**, quan hệ tài nguyên, thời điểm hoặc điều kiện rủi ro. PBAC là cách quản trị và đánh giá chính sách, không bắt buộc là một giao thức hay một sản phẩm riêng.

| Thành phần | Vai trò đối với xung đột |
| --- | --- |
| **PAP — Policy Administration Point** | Quản lý policy, owner, priority, version, phê duyệt và thử nghiệm trước triển khai. |
| **PDP — Policy Decision Point** | Đánh giá rule áp dụng và thuật toán kết hợp để đưa ra quyết định. |
| **PIP — Policy Information Point** | Cung cấp thuộc tính đáng tin như lifecycle, role, tenant, approval và metadata resource. |
| **PEP — Policy Enforcement Point** | Cưỡng chế kết quả tại API, service, dữ liệu hoặc resource boundary. |
| **IAM/IGA** | Xác định desired access, cấp/thu hồi entitlement, đối soát và chủ thể có thẩm quyền. |
| **IdP/SSO** | Xác thực người dùng, duy trì session hoặc phát kết quả xác thực; không tự quyết định mọi quyền tài nguyên. |
| **SCIM/connector** | Đồng bộ User và Group ở đích; không tự áp dụng mọi policy nghiệp vụ. |

~~~mermaid
sequenceDiagram
    actor U as Chủ thể / client
    participant PEP as API / PEP
    participant PDP as Policy Decision Point
    participant PIP as Thuộc tính IAM / PIP
    participant PAP as Policy Administration
    participant DB as Resource Store
    PAP-->>PDP: Policy set + combining rules + version
    U->>PEP: subject, action, resource request
    PEP->>DB: Đọc metadata resource đáng tin
    DB-->>PEP: tenant, owner, classification
    PEP->>PDP: Yêu cầu authorization
    PDP->>PIP: Lifecycle, role, approval, assurance
    PIP-->>PDP: Thuộc tính + sourceVersion + freshness
    PDP->>PDP: Match rules, combine effects, obligations
    PDP-->>PEP: Final decision + reason + policy version
    alt Permit và điều kiện thực thi đạt
        PEP->>DB: Thực hiện đúng action trên resource
        PEP-->>U: Kết quả hợp lệ
    else Deny / chưa đủ cơ sở Permit
        PEP-->>U: Không thực hiện thao tác bảo vệ
    end
~~~

**Quan trọng:** một quyết định Deny có thể đúng hoàn toàn nhưng không hiệu quả nếu API, batch job hoặc service vẫn cho thao tác mà không đi qua PEP. Khi điều tra policy conflict, phải xác minh cả quyết định **và** kết quả thực thi.

## 4. Các kết quả đánh giá và ý nghĩa của chúng

Nhiều policy engine hỗ trợ các trạng thái như:

| Kết quả | Diễn giải | Điều PEP cần làm |
| --- | --- | --- |
| **Permit** | Một rule hoặc policy set đã xác định điều kiện cho phép. | Cho phép **chỉ khi** decision còn hợp lệ và các obligation bắt buộc được đáp ứng. |
| **Deny** | Có một rule hoặc policy set trả hiệu lực từ chối. | Chặn action. |
| **NotApplicable** | Không rule nào thuộc phạm vi đánh giá áp dụng. | Không được tự cấp quyền; chuyển sang default deny hoặc policy fallback đã duyệt. |
| **Indeterminate** | Không thể đánh giá đáng tin vì lỗi, dữ liệu thiếu, kiểu dữ liệu sai hoặc không xác định được trạng thái. | Không tự biến thành Permit; báo lỗi/deny theo chính sách rủi ro. |

Các thuật ngữ **NotApplicable** và **Indeterminate** gắn với những mô hình policy như XACML; không phải mọi nền tảng dùng đúng bốn giá trị. Một thư viện chỉ trả boolean vẫn nên **phân biệt nguyên nhân nội bộ** để phát hiện và xử lý conflict.

### Explicit deny không đồng nghĩa default deny

- **Explicit Deny:** một rule áp dụng và chủ động cấm, ví dụ Deny nếu lifecycle=TERMINATED.
- **Default deny:** không có Permit đủ điều kiện; hệ thống từ chối vì không được cấp quyền.
- **Indeterminate:** chưa biết có Permit hay Deny do lỗi đánh giá; phải giữ tín hiệu lỗi thay vì âm thầm coi là default deny sạch.

Ở lớp thực thi, cả ba tình huống có thể cùng **không cho thực hiện action**. Ở lớp phân tích policy, chúng là những nguyên nhân khác nhau.

### Kiểm tra obligations và advice

Một quyết định Permit có thể đi kèm **obligation** như ghi audit bắt buộc, giới hạn dữ liệu trả về hoặc yêu cầu tạo phiên có thời hạn. Nếu hệ thống không thể đáp ứng obligation bắt buộc, **không được tự bỏ qua và thực hiện**.

Một conflict có thể xảy ra ngay cả khi hai rule cùng Permit nhưng đưa ra **hai obligation không tương thích**. Ví dụ policy A yêu cầu xuất dữ liệu dưới dạng chỉ đọc và policy B yêu cầu cho phép chỉnh sửa trực tiếp trong cùng hành động. Cần thiết kế rõ nghĩa vụ ở bước thực thi, không chỉ đếm số lần Permit.

## 5. Các thuật toán kết hợp chính sách

Khi nhiều policy trả kết quả khác nhau, hệ thống cần một **combining algorithm**. Việc chọn thuật toán phải phù hợp rủi ro và ý định nghiệp vụ; không có một quy tắc gộp mặc định dùng an toàn cho mọi loại policy.

### Deny-overrides

Ý tưởng: **Deny của một rule áp dụng được ưu tiên trước Permit**, theo ngữ nghĩa của engine. Đây là một lựa chọn thường phù hợp với hard guard như Leaver, tenant isolation và SoD.

~~~text
Rule A: Permit report.read khi role = FinanceReader
Rule B: Deny report.read khi lifecycle = TERMINATED

Request: role=FinanceReader, lifecycle=TERMINATED
Combining: deny-overrides
Final: Deny
~~~

Điểm lưu ý: cách xử lý **Indeterminate** của các biến thể deny-overrides trong một chuẩn như XACML **phức tạp hơn** “có Deny thì Deny, còn lại Permit”. Khi triển khai, phải tuân theo ngữ nghĩa chính xác của engine và viết test đầy đủ, bao gồm lỗi đánh giá.

### Permit-overrides

Ý tưởng: **một Permit có thể được ưu tiên** khi các rule cùng áp dụng theo thuật toán tương ứng.

Chiến lược này có thể phù hợp trong một số bài toán gộp các nguồn **cho phép độc lập**, nhưng nguy hiểm nếu đặt chung chính sách cho phép rộng với hard Deny về Leaver hoặc tenant.

~~~text
P1: Permit tất cả FinanceReader đọc report
P2: Deny người TERMINATED đọc report

Nếu chọn permit-overrides không phù hợp:
    User TERMINATED còn FinanceReader có thể nhận Permit
~~~

Không dùng permit-overrides trong một tập chính sách có ràng buộc an ninh bắt buộc nếu nó có thể làm mất hiệu lực các ràng buộc đó.

### First-applicable

Engine chọn rule **đầu tiên áp dụng** theo thứ tự đã định:

~~~text
1) Permit nếu role = FinanceReader
2) Deny nếu lifecycle = TERMINATED
~~~

Với User đã Leaver nhưng vẫn có role, rule 1 có thể che rule 2. Nếu đổi thứ tự, kết quả thay đổi. Vì vậy **thứ tự rule là một phần của chính sách**, phải được review và test như code.

### Only-one-applicable

Ý tưởng: chỉ kỳ vọng **một policy áp dụng** trong phạm vi được thiết kế. Nhiều policy cùng áp dụng có thể được xem là tình huống xung đột/không quyết định được theo semantics của engine.

Phù hợp hơn khi các domain chính sách cần **loại trừ nhau**, không phù hợp nếu mô hình cố tình ghép nhiều điều kiện RBAC, ABAC và lifecycle cùng lúc.

### Kết hợp theo tầng bảo vệ

Một thiết kế dễ giải thích:

~~~text
TẦNG 1: Guard bắt buộc
    - Lifecycle ACTIVE?
    - Subject và resource có tenant relationship hợp lệ?
    - Có vi phạm SoD hoặc legal hold?
    - Authentication assurance đã đạt?
    - Có dữ liệu bắt buộc đủ tin cậy?

    Nếu guard không đạt -> không Permit.

TẦNG 2: Quyền nghiệp vụ
    - Role, entitlement, group, approvedProject
    - Resource owner, action, scope, thời hạn

    Nếu quyền và các điều kiện đạt -> Permit.
    Ngược lại -> Deny.
~~~

Đây là **thiết kế khái niệm**; không phải semantics bắt buộc của PBAC. Có thể triển khai thông qua rule sets, PDP library, policy namespaces hoặc một policy kết hợp rõ ràng. Lợi ích là không để một role Permit vô tình bỏ qua guard bắt buộc.

### Bảng định hướng chọn cách kết hợp

| Đặc tính policy set | Gợi ý thiết kế | Rủi ro cần test |
| --- | --- | --- |
| Có hard Deny cho Leaver/tenant/SoD. | Deny-overrides hoặc hard guard rõ ràng. | Permit khác không được vượt guard. |
| Các nguồn cho phép độc lập và không có hard guard tại cùng tầng. | Có thể xét permit-overrides trong phạm vi được giới hạn. | Không để policy mở rộng lan sang domain nhạy cảm. |
| Rule có thứ tự kinh doanh chặt chẽ. | First-applicable với thứ tự versioned và test. | Rule rộng che rule hẹp, đổi thứ tự gây thay đổi quyền. |
| Mỗi domain chỉ được một policy áp dụng. | Only-one-applicable khi engine hỗ trợ. | Overlap bất ngờ dẫn tới lỗi quyết định. |
| Nhiều lớp kiểm soát độc lập. | Guard bắt buộc rồi mới xét business grant. | Guard bị thiếu tại endpoint/batch/async path. |

## 6. Phân loại xung đột cần phát hiện

### 6.1. Xung đột Permit/Deny trực tiếp

Một rule cho phép hành động, rule khác từ chối **cùng subject/action/resource/context**. Ví dụ role FinanceReader Permit, nhưng dữ liệu đang bị phong tỏa theo legal hold Deny export.

### 6.2. Xung đột do phạm vi policy chồng lấn

Policy A Permit trên **mọi tài liệu trong tenant B**; policy B Deny tài liệu **RESTRICTED**. Giao nhau là tài liệu RESTRICTED của tenant B. Tìm giao nhau này quan trọng hơn việc phát hiện hai policy có từ khóa Permit/Deny khác nhau.

### 6.3. Xung đột do thứ tự và shadowing

Rule tổng quát chạy trước rule đặc biệt theo first-applicable. Ví dụ:

~~~text
Rule 1: Permit API.* cho Department=IT
Rule 2: Deny API.admin.delete nếu chưa có JIT approval
~~~

Nếu Rule 1 chặn việc xét Rule 2, tài khoản IT có thể làm thao tác admin trái chính sách.

### 6.4. Xung đột do thuộc tính cùng tên khác nguồn

HRIS ghi department=FINANCE; IdP token cũ ghi SUPPORT. PIP chọn theo thời điểm/nguồn không rõ ràng, dẫn tới các request giống nhau có kết quả khác.

Đây là **attribute conflict**. Cần quy tắc **field ownership, source precedence, effectiveAt và freshness**, không giải bằng cách luôn chọn giá trị “cho phép nhiều quyền hơn”.

### 6.5. Xung đột giữa role nghiệp vụ và điều kiện ABAC

Role SupportAgent cho phép ticket.read, nhưng ticket thuộc project mà User không được phân công. RBAC Permit theo role trong khi ABAC Deny theo project/resource relationship.

Giải pháp là diễn đạt rõ role như **điều kiện cần nhưng chưa đủ**, hoặc chọn cách kết hợp phù hợp với policy mục tiêu.

### 6.6. Xung đột giữa nguồn cấp quyền

IGA thu hồi entitlement, nhưng ứng dụng quản trị viên gán trực tiếp lại role, hoặc một IdP Group được sync vào SaaS còn chứa User cũ. Xung đột **desired vs observed access** có thể xuất hiện dù PDP trung tâm không có hai rule trái nhau.

Cần tách lỗi **policy source ownership** với lỗi **provisioning drift**.

### 6.7. Xung đột do phiên, token, cache lỗi thời

PDP xét lifecycle=TERMINATED và Deny, nhưng API chỉ kiểm JWT cũ có scope=report.read và cho qua. Đây là **enforcement/data freshness conflict** ở hệ thống phân tán; cần xử lý tại Resource Server và token/session controls.

### 6.8. Xung đột nghĩa vụ và yêu cầu pháp lý

Một policy cho phép xuất bản dữ liệu khi có vai trò Editor, policy khác yêu cầu **data retention/legal hold** và cấm xóa. Không được tùy tiện biến một approval kinh doanh thành ngoại lệ vượt ràng buộc pháp lý.

Nếu thực sự có ngoại lệ, phải do policy owner phù hợp phê duyệt, giới hạn action/resource/time và có audit rõ.

## 7. Dữ liệu có thẩm quyền và ưu tiên thuộc tính

Giải quyết conflict phải dựa trên **dữ liệu đúng nguồn**, không chỉ trên **thuật toán gộp rule**.

| Thuộc tính | Nguồn có thẩm quyền thường gặp | Cách dùng trong PBAC |
| --- | --- | --- |
| Employment status, startAt, endAt | HRIS hoặc nguồn hợp đồng. | Xác định Joiner/Leaver có hiệu lực. |
| Department, jobCode, manager | HR/nguồn tổ chức được ủy quyền. | Điều kiện role/birthright và đánh giá Mover. |
| Identity ID, account correlation | IAM registry. | Liên kết cùng một người qua IdP, SaaS và tenant. |
| Business role, entitlement approval | IGA, resource owner hoặc workflow được phê duyệt. | Căn cứ Permit theo chức năng và phạm vi. |
| Authentication method/assurance | IdP/session validation đáng tin. | Step-up/MFA cho action nhạy cảm. |
| Resource tenant, owner, classification | Hệ thống sở hữu tài nguyên. | Tenant isolation, object-level ABAC. |
| Workload identity, environment, owner | Workload platform/service registry. | Policy cho service principal. |
| Policy version, exception owner | PAP/policy registry. | Xác định chính sách nào đang hiệu lực. |

### Không dùng email làm khóa so khớp duy nhất

Một người có thể có HR employeeId, IAM identityId, IdP subject và SCIM User ID khác nhau. Khi đánh giá policy:

~~~text
HR person       = HRIS:EMP-2041
IAM identity    = ID-2041
IdP subject     = issuer-A / sub-77
SaaS SCIM user  = tenant-b / scim-user-190
~~~

Cần correlation được xác minh, vì email/username có thể đổi, trùng hoặc bị tái sử dụng. Nếu mapping không chắc chắn, không được lấy role từ User A rồi áp vào session của User B.

### Quy tắc chọn nguồn không phải “mới nhất luôn thắng”

Một IdP claim có timestamp mới hơn HR projection nhưng vẫn có thể không phải nguồn có thẩm quyền cho department. Ngược lại, dữ liệu HR chính xác nhưng được phát sau hiệu lực nghiệp vụ cần có cơ chế bù.

Nên xét **authority**, **sourceVersion**, **effectiveAt**, **observedAt**, phạm vi dữ liệu và **độ mới được yêu cầu theo rủi ro**. Nếu vẫn mâu thuẫn, chuyển sang **DATA_CONFLICT/REVIEW**, không tự chọn nguồn có quyền rộng hơn.

## 8. Thiết kế phát hiện conflict trước khi đưa policy vào production

Nên kiểm tra policy conflict ngay ở giai đoạn thiết kế/CI, thay vì chỉ chờ người dùng nhận quyền sai.

### Bước 1 — Chuẩn hóa mô hình request

Chuẩn hóa subject, action, resource và context:

~~~text
subject:
    identityId, lifecycleStatus, roles, tenantId, approvedProjects
action:
    invoice.read / invoice.approve / invoice.export
resource:
    invoiceId, tenantId, createdBy, classification, status
context:
    authenticatedSession, assurance, requestedAt, environment
~~~

Phải xác định **kiểu dữ liệu** và ngữ nghĩa của từng trường. Ví dụ tenantId là định danh chính xác, không phải nhãn display; authentication assurance là kiểm tra theo profile, không nhất thiết là số thứ tự.

### Bước 2 — Liệt kê các rule cùng có thể áp dụng

Ví dụ:

| Rule | Target | Condition | Effect |
| --- | --- | --- | --- |
| P-ROLE | invoice.approve | role=FinanceApprover | Permit |
| P-TENANT | invoice.* | subject.tenantId khác resource.tenantId | Deny |
| P-SOD | invoice.approve | subject.identityId=invoice.createdBy | Deny |
| P-JML | business.* | lifecycleStatus=TERMINATED | Deny |
| P-MFA | invoice.approve | assurance không đạt policy | Deny |

Tìm **miền giao nhau** của target và condition. Một request FinanceApprover tự duyệt hóa đơn có thể khớp P-ROLE và P-SOD; đó là **conflict có chủ đích**, được bảo vệ bằng cách kết hợp policy phù hợp.

### Bước 3 — Phân loại: conflict hợp lệ hay không mong muốn?

- **Expected conflict:** RBAC Permit nhưng SoD Deny; mong muốn kết quả Deny.
- **Unexpected conflict:** hai nhóm quản trị đều sở hữu policy của cùng API nhưng định nghĩa cấp quyền trái nhau, chưa có ưu tiên.
- **Policy gap:** chưa có policy cho invoice.export; phải default deny.
- **Attribute ambiguity:** manager/tenant/resource owner không xác định được; phải chặn và điều tra.

Không xóa mọi rule Deny chỉ để hết cảnh báo conflict. **Nhiều conflict là biểu hiện của defense-in-depth**, cần được kiểm chứng hơn là triệt tiêu.

### Bước 4 — Xác định ngữ nghĩa giải quyết

Quy định ở **PAP**:

1. Tầng chính sách hoặc policy set nào đang áp dụng.
2. Thuật toán kết hợp nào là có thẩm quyền.
3. Hard guard nào không được vượt qua.
4. Exception nào được phép, ai phê duyệt, phạm vi và thời hạn.
5. Hành vi nếu thiếu thuộc tính hoặc PDP/PIP lỗi.
6. Cách đưa policy version đến tất cả PEP/PDP.

### Bước 5 — Tạo test cho vùng giao nhau

Không chỉ test mỗi rule riêng lẻ. Phải tạo request **đồng thời thỏa điều kiện của ít nhất hai rule** để chứng minh kết quả cuối đúng.

Ví dụ test role=FinanceApprover, lifecycle=TERMINATED, tenant đúng, invoice hợp lệ: expected **Deny**. Nếu test chỉ dùng User ACTIVE, sẽ không phát hiện một số lỗi kết hợp.

## 9. Công cụ tư duy: ma trận xung đột và đồ thị chính sách

Một ma trận giúp thấy quan hệ:

| Rule A / Rule B | Role Permit | Leaver Deny | Tenant Deny | SoD Deny | MFA guard |
| --- | --- | --- | --- | --- | --- |
| **Role Permit** | Overlap/redundancy có thể có | Xung đột có chủ đích | Xung đột có chủ đích | Xung đột có chủ đích | Cần xác định yêu cầu assurance |
| **Leaver Deny** | Bảo đảm Deny thắng | Có thể trùng bảo vệ | Đồng thời Deny | Đồng thời Deny | Đồng thời Deny |
| **Tenant Deny** | Bảo vệ tenant | Đồng thời Deny | Có thể trùng | Đồng thời Deny | Đồng thời Deny |
| **SoD Deny** | Ngăn tự phê duyệt | Đồng thời Deny | Đồng thời Deny | Có thể trùng | Đồng thời Deny |

Ma trận chỉ giúp **đặt câu hỏi**, không chứng minh mọi cặp rule thực sự giao nhau. Để kết luận conflict, cần đánh giá target và điều kiện trong **không gian yêu cầu có thể tồn tại**.

### Đồ thị phụ thuộc minh họa

~~~mermaid
flowchart TD
    R["Request<br/>subject/action/resource/context"] --> G["Mandatory guard set<br/>Lifecycle, Tenant, SoD, Assurance"]
    G --> Q{"Mọi guard cần thiết đạt<br/>và dữ liệu đủ tin cậy?"}
    Q -->|Không| D["Không Permit<br/>Deny hoặc xử lý lỗi"]
    Q -->|Có| P["Business policies<br/>RBAC, ABAC, grants, exceptions"]
    P --> C["Policy combining<br/>theo quy tắc được duyệt"]
    C --> F{"Final decision?"}
    F -->|Permit| E["PEP kiểm tra obligations<br/>và thực thi đúng phạm vi"]
    F -->|Không Permit| D
    E --> V["Audit và verify outcome"]
    D --> V
~~~

Thiết kế tầng trong sơ đồ là một lựa chọn kiến trúc để học; các engine có thể kết hợp policy bằng cấu trúc khác. Điều không thay đổi là **các điều kiện bắt buộc không được bị bypass**.

## 10. Joiner: conflict giữa pre-provisioning và ngày kích hoạt

**Tình huống:** Nhân viên mới có IdP User và SaaS account được tạo trước ngày bắt đầu để chuẩn bị thiết bị. SCIM Group cấp quyền đọc tài liệu đã được đồng bộ. Một policy Permit vì role Employee; policy lifecycle từ chối truy cập nghiệp vụ trước ngày làm.

### Vì sao có conflict?

- Provisioning nói **account/group đã tồn tại**.
- Business role policy nói **Employee được phép**.
- Lifecycle policy nói **PENDING_ACTIVATION chưa được dùng nghiệp vụ**.

Nếu ứng dụng chỉ dùng Group ở token hoặc role cục bộ, nó có thể Permit sớm.

### Thiết kế mong muốn

~~~text
PERMIT onboarding.registerMfa KHI
    subject.lifecycleStatus == PENDING_ACTIVATION
    AND identityBindingVerified
    AND onboardingWindowApproved

PERMIT business.report.read KHI
    subject.lifecycleStatus == ACTIVE
    AND currentTime >= subject.startAt
    AND subject.hasApprovedPermission("report.read")
    AND resourceConditionsHold
~~~

Phải **tách phạm vi onboarding và business**, tránh một Deny quá rộng làm hỏng onboarding hợp lệ hoặc một Permit onboarding vô tình mở tài nguyên nghiệp vụ.

### Kiểm chứng

Thử đăng nhập và truy cập tài nguyên thực khi User đang chờ kích hoạt. Chỉ kiểm tra trạng thái PENDING trong IAM hoặc việc đã thêm Group không đủ. Bằng chứng quan trọng là **PEP tại ứng dụng không cho business access trước effectiveAt**.

## 11. Mover: conflict giữa role cũ, role mới và thuộc tính thay đổi

**Tình huống:** Lan chuyển từ Support sang Finance. IAM đã tính lại quyền, nhưng IdP token cũ vẫn chứa SupportAdmin, Group tại SaaS chưa gỡ và FinanceReader mới đã được cấp.

| Nguồn/điều kiện | Giá trị sau Mover | Rủi ro |
| --- | --- | --- |
| HR/IAM lifecycle | department=FINANCE, ACTIVE | Căn cứ mong muốn theo ngày hiệu lực. |
| IdP session/token cũ | department=SUPPORT, role=SupportAdmin | Claim cũ có thể tiếp tục Permit. |
| SaaS SCIM Group | SupportAdmin và FinanceReader | Quyền tích lũy, có thể vi phạm SoD. |
| Policy mới | Không còn SupportAdmin | Cần từ chối thao tác chỉ dành cho Support. |
| Resource local role | Admin được cấp thủ công | Không nằm trong kiểm soát SCIM nếu chưa tích hợp. |

### Quy trình xử lý

1. Tính **desired access mới** từ nguồn HR, approval và policy.
2. Xác định chính sách nào dùng thuộc tính cũ, nguồn nào chưa cập nhật và độ trễ được chấp nhận.
3. Thu hồi role/Group không hợp lệ, cập nhật attribute qua IdP/SCIM hoặc nguồn PDP.
4. Kiểm soát cache và phiên/token cũ khi có nguy cơ tiếp tục Permit ngoài thời hạn.
5. Kiểm tra SoD trước khi cấp Finance role nhạy cảm.
6. Kiểm chứng effective permission ở ứng dụng, không chỉ lệnh provisioning thành công.

**Mover không nhất thiết phải vô hiệu hóa mọi phiên** nếu hệ thống có authorization lookup đủ mới. Nhưng không được cho phép role cũ tồn dư vượt chính sách.

### Ví dụ conflict không được giải bằng union tất cả quyền

~~~text
oldRoles = { SupportAdmin }
newRoles = { FinanceReader }

SAI: effectiveRoles = union(oldRoles, newRoles)

ĐÚNG VỀ MỤC TIÊU:
    effectiveRoles = currentlyApprovedRolesAt(effectiveAt)
    + các ngoại lệ còn hiệu lực, có owner/approval riêng
~~~

Một số quyền được giữ hợp lệ qua Mover; những quyền này phải có **căn cứ và thời hạn rõ**, không phải được giữ vì connector quên gỡ.

## 12. Leaver: hard Deny phải thắng quyền còn tồn dư

**Tình huống:** HR phát Leaver có hiệu lực lúc 17:00. IdP chặn login mới, nhưng người dùng có:

- Role FinanceReader trong JWT access token còn hạn.
- Cookie session ở CRM.
- Refresh token của ứng dụng native.
- Personal access token (PAT) của công cụ phát triển.
- Quyền Group/role được quản lý trực tiếp trong một SaaS.

**Policy conflict** thường thấy: policy role Permit trong một hệ thống trong khi lifecycle policy Deny tại IAM. Nhưng nguyên nhân thực tế có thể là ứng dụng **không nhận hoặc không thực thi Deny**.

~~~mermaid
sequenceDiagram
    participant HR as HR / nguồn có thẩm quyền
    participant IAM as IAM/IGA
    participant AS as IdP/Authorization Server
    participant APP as SaaS / API PEP
    participant V as Verification
    HR->>IAM: Leaver + effectiveAt + sourceVersion
    IAM->>AS: Disable login, revoke theo khả năng
    IAM->>APP: SCIM/API disable, remove entitlements
    IAM->>APP: Session/token revocation event (khi hỗ trợ)
    APP->>APP: Áp lifecycle guard / policy mới
    V->>AS: Thử login/token refresh trong phạm vi test
    V->>APP: Thử resource với session/token cũ
    AS-->>V: Kết quả thực tế
    APP-->>V: Kết quả thực tế
    V-->>IAM: Verified / residual / unknown theo đích
~~~

### Hai điều không được suy luận

1. **SCIM active=false** không có nghĩa mọi app-local session, PAT và access token đã bị chặn ngay.
2. **Refresh token bị revoke** không có nghĩa mọi JWT access token tự chứa đã phát đều bị Resource Server từ chối tức thời nếu server chỉ kiểm chữ ký và thời hạn offline.

Nếu chính sách yêu cầu thu hồi ngay, phải có cơ chế phù hợp ở **điểm sử dụng**; nếu chỉ hỗ trợ TTL hoặc eventual consistency, phải đo và quản trị **thời gian truy cập tồn dư** thay vì đánh dấu VERIFIED tuyệt đối.

### Xung đột sự kiện JML sai thứ tự

~~~text
sourceVersion=81: JOINER -> grant Employee
sourceVersion=82: MOVER  -> grant FinanceReader, revoke Support
sourceVersion=83: LEAVER -> revoke all employee access

Delivery order:
    v83 arrives and is applied
    v81 retries after network timeout

EXPECTED:
    v81 must not re-grant Employee or create a new Permit path
~~~

**SourceVersion/effectiveAt là điều kiện bảo vệ** để job cấp quyền lỗi thời không ghi đè kết quả Leaver. Tùy nguồn, phiên bản có thể không tăng toàn cục; hệ thống phải định nghĩa thứ tự và quan hệ sự kiện trong **phạm vi nguồn/identity** một cách đáng tin.

## 13. SSO, IdP, SCIM và policy conflict

Các thành phần IAM có thể dùng **những ảnh chụp quyền khác nhau**:

| Lớp | Thông tin thường có | Vì sao phát sinh conflict? |
| --- | --- | --- |
| HR/IGA | Employment status, business role, approval, effectiveAt. | Nguồn nghiệp vụ thay đổi nhưng đích nhận chậm. |
| IdP/SSO | Subject, nhóm, authentication context, token claims. | Token/SSO session được phát trước Mover/Leaver. |
| SCIM | User.active, Group.members, account mapping. | Provisioning chưa hội tụ hoặc đích có quyền cục bộ. |
| PDP/PIP | Policy và thuộc tính được đọc tại thời điểm đánh giá. | Cache, nguồn dữ liệu thiếu, policy version khác. |
| Ứng dụng/API | Local role, app session, resource owner, tenant. | Local policy hoặc role trực tiếp Permit trái desired state. |
| PAM/JIT | Grant đặc quyền và thời hạn truy cập. | Session cũ tiếp tục dùng sau khi JIT grant hết hạn. |

### OIDC và SAML không tự giải quyết policy conflict

OIDC ID token hoặc SAML Assertion giúp ứng dụng xác thực danh tính theo giao thức; **không chứng minh mọi thuộc tính quyền đang hiện hành**. OAuth access token có thể chứa scope, nhưng API còn phải xác minh audience, loại token, quyền hiện hành và resource policy.

Một claim `groups=[FinanceReader]` được ký hợp lệ vẫn có thể là **dữ liệu cũ**. Giải pháp là áp chính sách nguồn tin cậy, hạn token/cache, cơ chế invalidation/revocation và policy evaluation ở nơi sử dụng, không phải bỏ qua chữ ký hoặc chấp nhận mọi claim tùy ý.

### SCIM Group là một đường thực thi entitlement

SCIM Group.members có thể giúp một SaaS cấp role, nhưng **Group ID, local User ID và role mapping** thuộc namespace của đích. Nếu IAM gỡ User khỏi Group nhưng ứng dụng có direct role grant, kết quả vẫn có thể Permit. Đối soát phải gồm **effective permissions**, không chỉ danh sách Group.

## 14. Xung đột giữa tenant isolation, SoD và nhóm đặc quyền

### Tenant isolation là một guard độc lập

Giả sử User có role GlobalReader từ một nhóm IdP nhưng chỉ được truy cập tenant B. Một policy Permit đọc mọi báo cáo của GlobalReader trong khi policy tenant Deny truy cập tenant A.

Nếu RBAC Permit được ưu tiên tùy tiện, một role rộng có thể phá cách ly tenant.

~~~text
PERMIT report.read nếu subject.role == GlobalReader
DENY   report.read nếu subject.tenantId != report.tenantId

EXPECTED:
    role hợp lệ không bỏ qua tenant guard,
    trừ khi có chính sách cross-tenant rõ, được phê duyệt và thực thi riêng.
~~~

Lấy **report.tenantId** từ resource store ở server; không tin tham số tenantId do client tự điền.

### Separation of Duties (SoD)

**SoD** ngăn một người kiểm soát toàn bộ các bước rủi ro cao, ví dụ tạo và phê duyệt cùng hóa đơn.

~~~text
PERMIT invoice.approve nếu subject.role == FinanceApprover
DENY invoice.approve nếu invoice.createdByIdentityId == subject.identityId
~~~

Trong tập policy này, kết quả mong muốn khi chính người tạo hóa đơn xin duyệt là **Deny**. Combining và PEP phải bảo vệ SoD dù User đã có role FinanceApprover.

### Privileged access và PAM/JIT

Một policy admin có thể cho phép thao tác khi User có role Operator; policy khác yêu cầu:

- Quyền đặc quyền được **phê duyệt** và còn trong JIT window.
- Session đáp ứng **MFA/step-up** theo chính sách.
- Resource đúng môi trường và tenant được cấp.
- Không vi phạm policy về thay đổi production.

**Có role Operator không tự đồng nghĩa Permit production.restart.** Các điều kiện đặc quyền phải được ghép đúng và kiểm thử trong tình huống có role nhưng thiếu JIT approval.

## 15. Ngoại lệ, break-glass và thứ tự ưu tiên

Các tổ chức đôi khi có **exception** cho công việc khẩn cấp, nhưng exception không được biến thành lối tắt làm mất ý nghĩa của hard guard.

### Một ngoại lệ nên chứa gì?

| Thuộc tính | Ví dụ |
| --- | --- |
| Subject | Một identity hoặc nhóm chủ thể xác định. |
| Action | report.export, không phải wildcard mọi thao tác. |
| Resource | Một project/tenant/tập tài liệu cụ thể. |
| Owner/approver | Người chịu trách nhiệm và cấp phê duyệt có thẩm quyền. |
| Reason | Mục đích nghiệp vụ/sự cố đã ghi nhận. |
| StartAt/EndAt | Thời điểm hiệu lực và hết hạn. |
| Required assurance | Step-up/MFA, PAM session khi cần. |
| Guard không được vượt | Leaver, tenant boundary, SoD hoặc legal constraints tùy chính sách. |
| Audit reference | Ticket, approval, correlation ID. |

### Break-glass khi hệ thống policy lỗi

**Break-glass** là cơ chế cứu hộ được thiết kế trước, có phạm vi nhỏ, xác thực mạnh, kiểm toán và hậu kiểm. Nó không phải:

~~~text
if PDP unavailable:
    return PERMIT_ALL
~~~

Một mô hình an toàn hơn:

~~~text
if PDP unavailable:
    block protected action
    if specifically pre-approved breakGlassPolicy applies:
        use dedicated restricted workflow
        enforce strong authentication, scope, expiry, independent audit
~~~

Cần đánh giá yêu cầu tính sẵn sàng và rủi ro hệ thống. Một **false deny** có thể ảnh hưởng vận hành, nhưng giải pháp không phải bỏ hết kiểm soát khi gặp lỗi.

### Exception không được hồi sinh grant cũ

Khi Leaver có hiệu lực, một exception đã hết hạn hoặc do tài khoản cũ sở hữu không được tự kéo dài sang lần tuyển lại. **Rehire phải tính quyền và ngoại lệ từ công việc hiện tại**, không tự kích hoạt toàn bộ history.

## 16. Xung đột do cache, propagation và eventual consistency

Trong hệ thống phân tán, cùng một policy version có thể được phát hành tới nhiều PDP/PEP không đồng thời. Ngoài ra, claim hoặc thuộc tính từ IdP, SCIM và resource database có thể được cập nhật theo nhịp khác nhau.

### Những trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| **POLICY_CONFLICT** | Các rule/condition tạo kết quả trái nhau trên cùng request. | Kiểm tra combining, ưu tiên và ý định policy. |
| **ATTRIBUTE_CONFLICT** | Hai nguồn về cùng attribute không thống nhất. | Kiểm tra field ownership, source version, effectiveAt. |
| **POLICY_VERSION_MISMATCH** | PEP/PDP chưa dùng cùng policy version yêu cầu. | Đồng bộ có kiểm chứng; kiểm soát action rủi ro cao. |
| **PROVISIONING_DRIFT** | Đích còn Group/role không đúng desired. | SCIM/API reconciliation và readback. |
| **SESSION_TOKEN_STALE** | Session/token cũ vẫn chứa quyền trước thay đổi. | Revocation/invalidation hoặc policy lookup theo mức rủi ro. |
| **UNVERIFIABLE** | Không đọc/kiểm tra được effective access. | Không đánh dấu VERIFIED; tạo owner/case. |
| **ENFORCEMENT_GAP** | PEP không chặn thao tác dù final decision là Deny. | Ưu tiên sửa điểm thực thi và kiểm tra side effect. |

Tên trạng thái là **taxonomy vận hành minh họa**, không phải enum chuẩn PBAC.

### Không lấy Permit từ cache cũ để chữa timeout

Một Permit được tính trước Mover/Leaver có thể không còn hợp lệ. Nếu PDP mất kết nối lúc 17:01, ứng dụng không nên mở quyền dựa trên Permit lúc 16:00 nếu điều đó vượt **freshness/revocation boundary** của tài nguyên.

Giải pháp thường gồm:

1. TTL policy decision phù hợp từng nhóm action.
2. Cache key bao gồm subject, action, resource, tenant và các context quyết định.
3. Invalidation khi thay đổi lifecycle, grant, resource owner, classification hoặc policy.
4. Gắn policyVersion/sourceVersion và giới hạn tuổi thuộc tính.
5. Hành vi khi source unavailable được phê duyệt trước, tránh privilege escalation.
6. Readback quyền thực tế sau các sự kiện JML có rủi ro cao.

### Lỗi thời điểm kiểm tra và thời điểm sử dụng

**TOCTOU (time-of-check to time-of-use)** xảy ra khi một resource đổi owner/tenant sau khi PDP Permit nhưng trước khi thao tác ghi. Với hành động nhạy cảm, cần bảo đảm authorization và update nhất quán theo mô hình transaction/conditional write phù hợp.

## 17. Quy trình phân giải policy conflict end-to-end

~~~mermaid
flowchart TD
    A["Phát hiện conflict<br/>CI test / runtime / audit / JML drift"] --> B["Đóng băng ngữ cảnh<br/>subject, action, resource, time"]
    B --> C["Thu policy ID/version<br/>rules, combining, guard, owner"]
    C --> D["Thu thuộc tính và nguồn<br/>sourceVersion, effectiveAt, freshness"]
    D --> E{"Mapping và dữ liệu<br/>đáng tin?"}
    E -->|Không| X["DATA_CONFLICT/INDETERMINATE<br/>không cấp quyền, review"]
    E -->|Có| F["Xác định rule áp dụng<br/>và miền giao nhau"]
    F --> G{"Conflict có chủ đích?"}
    G -->|Có| H["Kiểm tra precedence & hard guards"]
    G -->|Không| J["Policy owner sửa rule/target/<br/>combining/exception"]
    J --> H
    H --> K["Unit + contract + JML regression tests"]
    K --> L{"Đạt cả decision<br/>và enforcement?"}
    L -->|Không| J
    L -->|Có| M["Phê duyệt + triển khai policy version"]
    M --> N["Readback PEP/PDP và observed access"]
    N --> O{"Đã hội tụ trong giới hạn?"}
    O -->|Có| P["VERIFIED + audit"]
    O -->|Không| Q["PARTIAL_FAILURE<br/>owner, retry, compensation"]
~~~

### Vai trò sở hữu khi xử lý

| Bên liên quan | Trách nhiệm |
| --- | --- |
| **Resource owner** | Xác định hành động/tài nguyên và quyền nghiệp vụ nào cần có. |
| **IAM/IGA owner** | Xác định nguồn lifecycle, role, approval, desired access và mapping. |
| **Security policy owner** | Bảo vệ hard guard, SoD, tenant isolation, privilege boundaries. |
| **Application owner** | Đảm bảo PEP thực thi đúng trong API, job nền và resource store. |
| **IdP/SCIM connector owner** | Quản trị đồng bộ User/Group và kiểm soát token/session liên quan. |
| **Audit/Compliance** | Kiểm chứng bằng chứng, exception và trách nhiệm theo quy định. |

Không nên để một nhóm tự ý xóa một Deny bắt buộc chỉ vì ticket của người dùng báo “không truy cập được”.

## 18. Pseudocode phát hiện xung đột và đánh giá an toàn

### Đánh giá tập policy

~~~text
evaluateAccess(request):
    subject = resolveTrustedSubject(request.authn)
    resource = loadTrustedResource(request.resourceId)
    if subject unresolved or resource unresolved:
        return NO_ACCESS_WITH_ERROR

    attributes = resolvePolicyInputs(
        subject, resource, request.context,
        trustedSourcesAndFreshnessRules
    )
    if attributes incomplete or untrusted:
        audit("ATTRIBUTE_INDETERMINATE")
        return NO_ACCESS_WITH_ERROR

    lifecycle = attributes.currentLifecycle
    if lifecycle disallows request.action:
        audit("LIFECYCLE_GUARD_DENY")
        return DENY

    if tenantBoundaryDisallows(subject, resource):
        return DENY
    if mandatorySoDOrAssuranceGuardFails(request, attributes):
        return DENY

    applicable = matchApprovedPolicies(
        request, attributes, currentPolicyVersion
    )
    conflicts = analyzeOverlappingEffectsAndObligations(applicable)
    recordConflictDiagnosticsWithoutSecrets(conflicts)

    decision = combineAccordingToApprovedSemantics(applicable)
    if decision != PERMIT:
        return NO_ACCESS
    if mandatoryObligationsCannotBeEnforced(decision):
        return NO_ACCESS

    return PERMIT_FOR_EXACT_ACTION_AND_RESOURCE
~~~

**Pseudocode không phải triển khai chuẩn XACML/Cedar/Rego hay của một hãng cụ thể.** Xử lý Indeterminate, các loại obligations và combining algorithm phải theo engine đang sử dụng. Trong production, không nhất thiết phải chạy bộ phân tích conflict đầy đủ **trên mọi request**; phần lớn phân tích tĩnh/overlap có thể làm tại CI, còn runtime tập trung vào đánh giá chính sách được phê duyệt và quan sát quyết định.

### Bộ phát hiện conflict khi thay đổi policy

~~~text
onPolicyProposal(candidatePolicy):
    impacted = findPotentiallyOverlappingPolicies(candidatePolicy)
    witnesses = generateRepresentativeRequests(
        candidatePolicy, impacted,
        lifecycleStates = [PENDING, ACTIVE, SUSPENDED, TERMINATED],
        tenants = representativeCrossTenantCases,
        actions = representativeBusinessAndAdminActions
    )

    for request in witnesses:
        before = evaluateWithCurrentPolicySet(request)
        after = evaluateWithCandidatePolicySet(request)
        if after violates mandatorySecurityInvariants:
            blockReleaseAndOpenReview(request, before, after)
        else if policyEffectsConflictOrChangeUnexpectedly:
            requireOwnerReview(request, before, after)

    publishOnlyAfterApprovalAndRegressionPass()
~~~

Với hệ thống policy phức tạp, việc **tìm hết mọi giao nhau** có thể khó hoặc không khả thi bằng tập test mẫu. Có thể kết hợp phân tích cấu trúc, symbolic/constraint reasoning khi phù hợp và test đại diện; cần công bố giới hạn bao phủ thay vì tuyên bố đã chứng minh không còn conflict.

## 19. Ma trận kiểm thử policy conflict

Kiểm thử phải kiểm tra **decision cuối** và **hành vi thực tế tại PEP**, gồm trường hợp có hai rule cùng áp dụng và trường hợp dữ liệu không chắc chắn.

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| PBAC-C01 | Role Permit, Leaver Deny cùng áp dụng. | Deny thắng theo hard guard/combining đã duyệt. |
| PBAC-C02 | FinanceReader Permit nhưng tài nguyên khác tenant. | Deny; không lộ dữ liệu. |
| PBAC-C03 | FinanceApprover Permit nhưng tự duyệt hóa đơn. | Deny theo SoD. |
| PBAC-C04 | Permit đọc nhưng action là export. | Không Permit export nếu thiếu grant riêng. |
| PBAC-C05 | Không rule nào áp dụng. | Default deny. |
| PBAC-C06 | PIP lỗi, không đọc được lifecycle. | Indeterminate/no access; không tự Permit. |
| PBAC-C07 | Hai policy Permit nhưng obligations xung đột. | Không bỏ qua nghĩa vụ; chặn/review theo policy. |
| PBAC-C08 | First-applicable có rule rộng trước hard Deny. | Test phát hiện và từ chối thay đổi nguy hiểm. |
| PBAC-C09 | Candidate policy đổi permit-overrides. | Không làm hard guard bị bypass. |
| PBAC-C10 | Joiner có account/Group nhưng chưa đến activation. | Không truy cập nghiệp vụ sớm. |
| PBAC-C11 | Mover gỡ SupportAdmin, token cũ còn claim. | Không dùng quyền Support vượt thời hạn. |
| PBAC-C12 | Mover cấp role mới nhưng thiếu approval/SoD. | Deny quyền mới chưa được duyệt. |
| PBAC-C13 | Leaver có app cookie/PAT còn hạn. | Không truy cập trái chính sách; đo residual paths. |
| PBAC-C14 | Retry Joiner phiên bản cũ sau Leaver. | Không cấp lại entitlement hoặc Permit path. |
| PBAC-C15 | IdP claim department khác nguồn HR. | Phân loại attribute conflict, không chọn Permit rộng. |
| PBAC-C16 | Policy version cũ ở một ứng dụng. | Phát hiện version mismatch và kiểm soát tác động. |
| PBAC-C17 | PEP API không áp rule Deny trung tâm. | Test FAIL nếu thao tác trái phép thành công. |
| PBAC-C18 | Resource đổi owner trong lúc update. | Không có TOCTOU bypass. |
| PBAC-C19 | Ngoại lệ còn hạn, đúng resource/action/owner. | Permit nếu không vi phạm guard bắt buộc. |
| PBAC-C20 | Ngoại lệ đã hết hạn hoặc User Leaver. | Deny; không tự tái kích hoạt. |
| PBAC-C21 | Service account staging gọi production. | Deny theo workload identity/environment. |
| PBAC-C22 | Role admin có nhưng không có JIT/phishing-resistant MFA theo policy. | Không Permit privileged action. |
| PBAC-C23 | Batch API gồm một resource khác tenant. | Không bỏ qua authorization ở từng object. |
| PBAC-C24 | PDP timeout, break-glass không được duyệt. | Không thực hiện hành động. |

### Given–When–Then

~~~gherkin
Feature: PBAC conflict resolution protects identity lifecycle

  Scenario: Leaver denial overrides a stale role grant
    Given a FinanceReader identity has an old valid app session
    And an authoritative Leaver event is effective
    And the role policy would otherwise permit report.read
    When the user requests a protected report
    Then the final access decision is Deny
    And the PEP does not return protected report data

  Scenario: SoD denial wins over finance approval role
    Given a user has FinanceApprover
    And the invoice was created by that user
    When the user requests invoice.approve
    Then the effective decision is Deny
    And the invoice status remains unchanged

  Scenario: Missing tenant data cannot become a permit
    Given the Resource PIP cannot verify resource tenant
    When a user requests a confidential resource
    Then no protected action is performed
    And the evaluation failure is audited distinctly
~~~

### Kiểm tra hệ quả thật

Một status HTTP 403 chưa chứng minh thao tác đã bị chặn **trước khi có side effect**. Với update/delete/approve phải đọc lại trạng thái tài nguyên. Với export/read cần kiểm tra không trả dữ liệu nhạy cảm. Với token/session cần thử đường truy cập thật trong môi trường cho phép.

## 20. Audit, khả năng giải thích và chỉ số conflict

### Bản ghi quyết định nên chứa gì?

| Thuộc tính | Mục đích |
| --- | --- |
| Decision ID, correlation ID | Liên kết request với PDP, PEP và sự kiện IAM. |
| Identity/subject, issuer, tenant | Tránh nhầm người hoặc namespace. |
| Action/resource reference | Biết phạm vi quyết định. |
| Policy IDs, versions, combining algorithm | Giải thích tại sao chọn Permit/Deny. |
| Applicable rule IDs/effects | Truy vết rule Permit và Deny đồng thời áp dụng. |
| Attribute source, version, freshness | Phát hiện dữ liệu nguồn xung đột/stale. |
| JML event, effectiveAt, sourceVersion | Chứng minh xử lý đúng thời điểm. |
| Final decision, reason code | Phân biệt conflict hợp lệ, error và default deny. |
| Enforcement outcome, verifiedAt | Chứng minh PEP đã chặn/cho phép đúng. |
| Exception/approval/owner | Kiểm toán quyền ngoại lệ có thời hạn. |

Ví dụ JSON audit nội bộ:

~~~json
{
  "eventType": "PBAC_POLICY_CONFLICT_EVALUATED",
  "decisionId": "dec-pbac-3301",
  "identityId": "ID-LAN-2041",
  "action": "report.read",
  "resourceRef": "REPORT-105",
  "policyVersion": "pbac-v18",
  "applicablePolicies": [
    { "id": "finance-reader-grant", "effect": "Permit" },
    { "id": "leaver-hard-guard", "effect": "Deny" }
  ],
  "combiningSemantics": "deny-overrides",
  "lifecycleState": "TERMINATED",
  "sourceVersion": 83,
  "finalDecision": "Deny",
  "enforcement": "BLOCKED_VERIFIED",
  "evaluatedAt": "2026-12-01T17:01:00+07:00",
  "correlationId": "leaver-2041-v83"
}
~~~

Đây là **schema minh họa**, không phải chuẩn PBAC/XACML/OIDC/SCIM. Không ghi mật khẩu, session cookie, ID/access/refresh token nguyên vẹn, seed MFA, private key hay dữ liệu nhạy cảm không cần thiết. Hạn chế quyền đọc log và có chính sách lưu giữ phù hợp.

### Chỉ số vận hành

| Chỉ số | Điều cần đánh giá |
| --- | --- |
| **Permit/Deny conflict count** | Số xung đột có chủ đích và không mong muốn theo action/resource. |
| **High-risk conflict rate** | Tỷ lệ conflict liên quan Leaver, SoD, tenant hoặc quyền admin. |
| **Indeterminate rate** | Nguồn thuộc tính/policy thiếu hoặc lỗi đến mức nào. |
| **Policy version drift** | Có bao nhiêu PDP/PEP vẫn chạy policy cũ. |
| **Attribute conflict incidents** | HR/IdP/app có dữ liệu cùng nghĩa nhưng khác nhau bao nhiêu. |
| **Unauthorized Permit incidents** | Yêu cầu đáng lẽ Deny nhưng ứng dụng thực thi thành công. |
| **Unexpected Deny incidents** | Policy mới chặn người hợp lệ hoặc hành động nghiệp vụ. |
| **Residual access after Leaver** | Có còn session/token/role dùng được sau mốc chấm dứt không. |
| **Exception expiry violations** | Quyền ngoại lệ còn hoạt động sau EndAt. |
| **Mean time to resolve conflict** | Độ trễ xử lý từ phát hiện tới verified remediation. |
| **Conflict regression coverage** | Bao nhiêu nhóm giao nhau có test được tự động hóa. |

Không dùng **số lượng conflict bằng 0** làm mục tiêu duy nhất: hard Deny và business Permit cùng áp dụng có thể là thiết kế phòng vệ đúng. Mục tiêu là **không có xung đột không kiểm soát dẫn tới quyết định hoặc thực thi sai**.

## 21. Quản trị thay đổi policy để tránh conflict mới

Mỗi thay đổi policy có thể ảnh hưởng nhiều team, tenant và ứng dụng. Nên coi policy như một hiện vật có **owner, version, review và rollback**.

### Quy trình thay đổi được khuyến nghị

1. **Định danh policy:** tên, mục đích, phạm vi action/resource, owner và nguồn dữ liệu.
2. **Định nghĩa kết quả mong muốn:** nêu rõ khi nào Permit, khi nào Deny, điều kiện nào là guard bắt buộc.
3. **So sánh với policy hiện hành:** phát hiện overlap, shadowing, data ownership conflict và quyền bị mở rộng.
4. **Chạy conflict tests:** gồm Joiner chưa active, Mover bỏ role, Leaver còn token, cross-tenant, SoD và PDP outage.
5. **Review ngoại lệ và phạm vi ưu tiên:** không đưa wildcard Permit hoặc permit-overrides làm mất hard guard.
6. **Phê duyệt bởi chủ thể có thẩm quyền:** Resource owner, IAM và Security tùy mức rủi ro.
7. **Triển khai có versioning:** kiểm tra policy version ở PDP/PEP/ứng dụng liên quan.
8. **Quan sát sau phát hành:** so Permit/Deny distribution, lỗi Indeterminate và access thực tế.
9. **Rollback có kiểm soát:** không vô tình phục hồi policy từng cho quyền rộng trái thay đổi JML mới.
10. **Đối soát định kỳ:** phát hiện drift do SCIM, local role, token/session và quyền ngoại lệ còn tồn.

### Khi nào phải dừng phát hành?

Chặn triển khai khi test cho thấy **User Leaver được Permit**, **cross-tenant access**, **bypass SoD**, **thao tác admin thiếu approval/assurance**, hoặc **PEP thực thi action sau Deny**. Các tình huống không đủ dữ liệu/không thể kiểm chứng cần được phân loại rủi ro rõ, có owner và không được báo PASS giả.

## 22. Tình huống thực hành

### Tình huống A — Hai chính sách trái nhau sau Leaver

**Bối cảnh:** Policy FinanceReader Permit report.read. Policy Leaver Deny mọi business read. Ứng dụng vẫn có role FinanceReader được lưu trong JWT cũ.

**Câu hỏi:** Cần làm gì ngoài việc thêm deny-overrides?

**Gợi ý:** Cần xác minh API/PEP thực thi lifecycle guard, token/session được kiểm soát, role/Group được gỡ qua SCIM và quyền thực tế đã bị chặn trong giới hạn quy định. Thứ tự policy đúng ở PDP trung tâm chưa đủ nếu ứng dụng không hỏi PDP.

### Tình huống B — Permit-overrides làm mất SoD

**Bối cảnh:** Một kỹ sư chọn permit-overrides để giảm ticket “không đủ quyền”. Nhân viên vừa là FinanceApprover vừa là người tạo hóa đơn, nhưng hệ thống trả Permit.

**Câu hỏi:** Lỗi nằm ở đâu?

**Gợi ý:** Combining semantics không tương thích với hard SoD Deny. Thiết kế lại policy set/guard bắt buộc, thêm test giao nhau và yêu cầu Security review.

### Tình huống C — Mover giữ cả Group cũ và mới

**Bối cảnh:** Lan từ Support sang Finance. IdP Group FinanceReader đã thêm, nhưng Group SupportAdmin ở SaaS chưa gỡ, do một connector báo timeout.

**Câu hỏi:** Đây là rule conflict hay provisioning drift?

**Gợi ý:** Trước hết là **provisioning drift** giữa desired và observed; có thể tạo Permit trái policy. Cần readback target, gỡ quyền cũ, kiểm tra cache/token và retry idempotent với sourceVersion.

### Tình huống D — Source attribute mâu thuẫn

**Bối cảnh:** HR xác nhận department=FINANCE hiệu lực 09:00. IdP token phát lúc 08:00 còn department=SUPPORT; API lấy token claim làm nguồn duy nhất.

**Câu hỏi:** Nên chọn thuộc tính nào?

**Gợi ý:** Áp field ownership và freshness theo policy; không tự chọn giá trị tạo nhiều quyền hơn. Có thể cần kiểm tra IAM/PIP hiện hành, invalidate cache/token hoặc từ chối action nhạy cảm khi dữ liệu không đủ.

### Tình huống E — First-applicable che hard guard

**Bối cảnh:** Rule đầu Permit department=IT được đặt trước Deny production.delete nếu thiếu JIT approval.

**Câu hỏi:** Một thay đổi thứ tự rule ảnh hưởng gì?

**Gợi ý:** Với first-applicable, thứ tự có thể đổi kết quả. Tránh thiết kế guard quan trọng bị che; kiểm thử cả điều kiện IT và thiếu approval, quản lý thứ tự bằng policy version.

### Tình huống F — Break-glass khi PDP lỗi

**Bối cảnh:** Sự cố production, PDP timeout. Một đề xuất cho phép mọi admin API khi PDP không phản hồi.

**Câu hỏi:** Phương án nào an toàn?

**Gợi ý:** Không dùng Permit All. Thiết kế workflow break-glass hẹp, có định danh được phê duyệt, xác thực mạnh, thời hạn, chỉ action cần thiết và audit độc lập.

### Tình huống G — Policy đúng nhưng HTTP 403 đến quá muộn

**Bối cảnh:** API đã xóa một tài liệu rồi mới kiểm tra PEP và trả 403.

**Câu hỏi:** Có thể đánh dấu test policy conflict PASS không?

**Gợi ý:** Không. Enforcement bị lỗi. Cần kiểm tra quyền trước side effect, transaction/TOCTOU và test đọc lại datastore.

### Tình huống H — Rehire dùng lại ngoại lệ cũ

**Bối cảnh:** Nhân viên nghỉ việc, sau đó được tuyển lại ở vai trò khác. Một exception export được phê duyệt ở lần làm việc trước còn trong policy store.

**Câu hỏi:** Exception có được tự kích hoạt lại không?

**Gợi ý:** Không. Phải tính lại approval, vai trò, resource và thời hạn theo công việc mới; historical grant không tự trở thành current authorization.

## 23. Câu hỏi tự kiểm tra

**1. Policy conflict luôn là lỗi thiết kế cần xóa một rule không?**

Không. Một rule Permit theo vai trò và một hard Deny theo Leaver/SoD có thể cùng áp dụng **có chủ đích** để bảo vệ quyền. Điều quan trọng là combining và enforcement đúng.

**2. Chồng lấn giữa hai rule cùng Permit có nhất thiết gây conflict không?**

Không. Nó có thể là redundancy hoặc overlap hợp lệ; cần xem target, condition và obligations.

**3. NotApplicable khác Indeterminate như thế nào?**

NotApplicable là không rule nào áp dụng; Indeterminate là không đánh giá được đáng tin do thiếu dữ liệu/lỗi. Cả hai không được tự biến thành Permit.

**4. Khi nào deny-overrides thường phù hợp?**

Khi tập policy cần bảo vệ hard Deny như Leaver, SoD và tenant isolation; nhưng phải tuân thủ semantics chính xác của engine với các trạng thái lỗi.

**5. Vì sao first-applicable có thể nguy hiểm?**

Một Permit rộng chạy trước có thể che Deny đặc biệt; đổi thứ tự rule có thể thay đổi quyền.

**6. Nếu HR và IdP đưa giá trị department khác nhau, có nên chọn giá trị mới hơn theo timestamp không?**

Không tự động. Cần field ownership, sourceVersion, effectiveAt, freshness và mapping đáng tin.

**7. SCIM đã gỡ Group sau Mover thì mọi API có tự Deny quyền cũ ngay không?**

Không mặc định. App có thể có local role, cache hoặc token cũ; phải kiểm tra effective access và thời gian hội tụ.

**8. Leaver đã bị IdP chặn login mới nhưng còn app session. Việc policy trung tâm Deny đã đủ chưa?**

Chưa nếu app PEP không kiểm tra hoặc không nhận event thu hồi. Cần xác minh đường thực thi và session/token thực tế.

**9. Policy exception phải quản trị những gì?**

Chủ thể, action, resource, scope, owner/approval, thời hạn, guard không được vượt và bằng chứng kiểm toán.

**10. Có thể dùng Permit cache cũ vô hạn khi PDP mất kết nối không?**

Không. Cần TTL, phiên bản, invalidation, quy tắc fail-closed theo rủi ro và đường break-glass riêng nếu được duyệt.

**11. Vì sao test cần kiểm tra database sau response 403?**

Vì API có thể đã tạo side effect trước khi từ chối; chính sách chỉ có ý nghĩa nếu PEP chặn hành động thực tế.

**12. Khi một policy mới chặn nhầm người dùng hợp lệ, có nên xóa mọi Deny để khắc phục nhanh không?**

Không. Cần phân loại false deny, kiểm tra dữ liệu nguồn/rule/combining, sửa trong phạm vi hẹp và chạy regression tránh mở đặc quyền.

## Ghi nhớ

- **Policy conflict trong PBAC** xuất hiện khi những rule có ảnh hưởng tới cùng yêu cầu đưa ra effect hoặc nghĩa vụ không tương thích; **overlap, redundancy, gap, attribute conflict và provisioning drift** cần được phân biệt.
- **Permit/Deny, NotApplicable và Indeterminate** phải được hiểu đúng; **default deny** và kiểm soát lỗi giúp ngăn cấp quyền khi thiếu căn cứ.
- **Deny-overrides, permit-overrides, first-applicable, only-one-applicable và hard guard** có ngữ nghĩa khác nhau; lựa chọn phải phù hợp policy và được kiểm thử, không áp một cách máy móc.
- **Joiner** có thể được pre-provision nhưng chưa có quyền nghiệp vụ; **Mover** phải bỏ quyền cũ và cấp quyền mới đúng phê duyệt; **Leaver** cần bị chặn dù token/phiên cũ vẫn tồn tại.
- **IdP/SSO, SCIM, RBAC/ABAC, PAM, PDP/PIP và PEP** có trách nhiệm khác nhau. Quyết định Deny chỉ bảo vệ hệ thống nếu ứng dụng thực sự cưỡng chế tại resource.
- **Nguồn thuộc tính có thẩm quyền, sourceVersion/effectiveAt, độ mới cache và policy version** giúp phân giải xung đột đúng và ngăn event lỗi thời tái cấp quyền.
- **Kiểm thử miền giao nhau, audit, readback quyền thực tế, quản trị ngoại lệ và đo residual access** giúp xử lý policy conflict có căn cứ, giảm quyền truy cập tồn dư trong toàn bộ vòng đời danh tính.
