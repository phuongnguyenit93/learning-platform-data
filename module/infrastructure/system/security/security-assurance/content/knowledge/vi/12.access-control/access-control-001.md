# Access control assurance

**Access control assurance** là hoạt động xây dựng và kiểm tra bằng chứng để có cơ sở tin rằng **chỉ những chủ thể được cấp quyền hợp lệ mới có thể thực hiện những hành động được phép trên đúng tài nguyên, trong đúng ngữ cảnh và thời gian**, đồng thời các trường hợp truy cập không hợp lệ được ngăn chặn, phát hiện và xử lý theo mục tiêu bảo mật.

Trong chương **Kiểm soát truy cập**, điều quan trọng không chỉ là biết **authentication** (xác thực) và **authorization** (ủy quyền/phân quyền), mà còn biết trả lời: **Cơ chế kiểm soát quyền đã được thiết kế đúng chưa? Có thật sự áp dụng cho mọi đường truy cập không? Có còn hoạt động sau khi hệ thống thay đổi? Bằng chứng nào đủ để đưa ra kết luận?**

Ví dụ, nền tảng học trực tuyến có thể dùng SSO, MFA và cơ chế vai trò TEACHER, STUDENT, ADMIN. Tuy nhiên, một giảng viên đã đăng nhập vẫn không được tự ý tải điểm của lớp khác. Nếu API chỉ kiểm tra vai trò TEACHER mà bỏ qua quyền đối với từng lớp, tổ chức vẫn có nguy cơ lộ dữ liệu dù phần xác thực có vẻ hoàn chỉnh.

Trong module **SECURITY_SECURITY_ASSURANCE**, access control assurance kết nối **phân tích rủi ro → yêu cầu bảo mật → access controls → kiểm thử → bằng chứng → đánh giá → finding và khắc phục → rủi ro còn lại**. Việc kết luận một control đạt phải dựa trên bằng chứng phù hợp với hệ thống, tài khoản, chức năng, dữ liệu và kỳ đánh giá; không chỉ dựa vào một chính sách, màn hình cấu hình hay kết quả test đơn lẻ.

## 1. Kết quả học tập

Sau khi hoàn thành bài, bạn có thể:

1. Phân biệt **access control**, **access control assurance**, authentication, authorization, accounting/audit và identity governance.
2. Xác định subject, object, action, context, trust boundary, policy và điểm thực thi quyền trong hệ thống phân tán.
3. Hiểu vai trò của DAC, MAC, RBAC, ABAC, ReBAC và các cơ chế kết hợp mà không nhầm tên mô hình với bảo đảm thực thi.
4. Xây dựng security invariants và tiêu chí đạt cho quyền truy cập người dùng, tài khoản dịch vụ, quản trị và bên thứ ba.
5. Thiết kế test cho **object-level**, **function-level**, **tenant-level** và **workflow-level authorization**, bao gồm side effects bất đồng bộ.
6. Kiểm chứng cấp, sửa, rà soát, thu hồi quyền và các trường hợp quyền biến động trong vòng đời truy cập.
7. Thu thập và đánh giá evidence về **design effectiveness**, **implementation effectiveness** và **operating effectiveness**.
8. Diễn đạt Claim–Argument–Evidence, quản lý evidence gaps, finding, remediation, retest và residual risk.
9. Thiết kế continuous assurance cho cloud IAM, API, session, token, worker, storage và quyền đặc biệt.
10. Đọc hoặc xây dựng một control record và báo cáo assurance đủ để risk owner ra quyết định có cơ sở.

## 2. Phạm vi của access control assurance

### 2.1. Access control là gì?

**Access control** là tập hợp các chính sách, quy tắc và biện pháp kỹ thuật/quản trị nhằm quyết định và thực thi việc một **chủ thể** được thực hiện **hành động** nào trên **tài nguyên** nào, dưới **điều kiện** nào.

Một quyết định quyền có thể mô tả ở mức khái niệm:

~~~text
Decision = Authorize(
    subject = "teacher-42",
    action  = "export-learners",
    object  = "class-43",
    context = {time, tenant, session, purpose, policy-version}
)
~~~

Đây là mô hình ý niệm, không phải giao diện lập trình chuẩn bắt buộc. Trong thực tế, quyền có thể phụ thuộc thông tin được kiểm chứng từ identity provider, cơ sở dữ liệu nghiệp vụ, nhóm vai trò, quan hệ sở hữu, trạng thái tài nguyên, thời điểm, thiết bị hoặc nghĩa vụ nghiệp vụ.

Một hệ thống **có** access control chưa chắc **có assurance phù hợp**. Assurance đòi hỏi bằng chứng cho thấy chính sách được **dịch thành control đúng, được thực thi tại mọi đường quan trọng và còn hiệu lực trong phạm vi đánh giá**.

### 2.2. Những thành phần cần phân biệt

| Khái niệm | Câu hỏi trả lời | Ví dụ trên nền tảng học |
|---|---|---|
| **Identity** | Chủ thể được định danh là ai? | teacher-42, learner-17, report-worker |
| **Authentication (AuthN)** | Hệ thống xác nhận danh tính/phiên theo cơ chế nào? | SSO, MFA, xác thực workload |
| **Authorization (AuthZ)** | Chủ thể được phép làm gì với đối tượng này? | Giảng viên có quyền sửa điểm lớp 42 không? |
| **Policy** | Điều kiện cấp/từ chối quyền được định nghĩa ra sao? | Chỉ giảng viên đang được phân công mới được xuất danh sách |
| **Policy Decision Point (PDP)** | Thành phần nào quyết định allow/deny? | Authorization service/policy engine |
| **Policy Enforcement Point (PEP)** | Thành phần nào thực thi quyết định? | API handler, service, gateway, worker, storage |
| **Provisioning** | Ai/cơ chế nào cấp quyền và theo phê duyệt nào? | Giao lớp cho giảng viên, gán cloud role |
| **Review/recertification** | Quyền hiện tại có còn cần và hợp lệ? | Chủ sở hữu lớp và quản trị rà soát quyền |
| **Revocation** | Khi mất điều kiện, quyền bị thu hồi như thế nào? | Thu hồi phân công lớp, vô hiệu hóa session phù hợp |
| **Accounting/audit** | Có thể truy vết quyết định và hành động nhạy cảm? | Ai xuất file, lúc nào, cho lớp nào |
| **Assurance** | Căn cứ nào chứng minh các yêu cầu đó đang được đáp ứng? | Test, log, policy export, approval, deployment evidence |

**AuthN không thay thế AuthZ**: người dùng có tài khoản hợp lệ vẫn có thể là actor của hành vi lạm dụng quyền. **Log không thay thế phòng ngừa**: phát hiện một file đã bị lấy không tự lấy lại được dữ liệu đã lộ.

### 2.3. Phạm vi nào được kiểm tra?

Access control assurance phải nhìn qua các lớp:

- **Nghiệp vụ:** học viên, giảng viên, quản trị viên, nhân sự hỗ trợ và các trạng thái lớp học.
- **Ứng dụng:** web/mobile, API, chức năng đọc/sửa/xóa/xuất, cache, batch job.
- **Dữ liệu:** record, hàng dữ liệu, file, object storage, cơ sở dữ liệu, backup.
- **Hạ tầng:** IAM role, cloud resource, mạng, secret, pipeline và quyền production.
- **Tài khoản không phải con người:** service/workload identity, job runner, automation.
- **Nhà cung cấp:** SSO, SaaS, OAuth application, API key, remote support.
- **Vòng đời:** cấp, thay đổi, dùng, rà soát, thu hồi, sự cố và chấm dứt quan hệ.

Một đánh giá chỉ xem IAM console mà không kiểm tra authorization nghiệp vụ của ứng dụng là **đánh giá chưa đầy đủ** nếu claim bao gồm quyền truy cập dữ liệu học viên.

## 3. Các nguyên tắc kiểm soát quyền cần được chứng minh

### 3.1. Least privilege

Chủ thể chỉ có những quyền cần thiết cho nhiệm vụ đã được phê duyệt, trong phạm vi và thời gian phù hợp. Cần xét **quyền thực tế có thể sử dụng**, không chỉ tên role.

Ví dụ, report-worker chỉ cần đọc dữ liệu của một pipeline nhưng được cấp quyền ghi/xóa toàn bộ database là một dấu hiệu quyền dư. Assurance cần so sánh quyền **được cấp**, quyền **thực tế có thể thực thi** và nhiệm vụ **được phê duyệt**.

### 3.2. Deny by default và fail closed

Khi chưa có chính sách cho phép hợp lệ, hành động cần bị từ chối theo quy tắc đã xác định. Nếu một thành phần authorization không sẵn sàng, hệ thống không được vô tình **cho phép tất cả**. Quyết định về cách xử lý khi lỗi phải tính đến khả năng phục hồi và tính sẵn sàng, nhưng không thể tự biến lỗi kiểm tra thành quyền rộng.

**Test quan trọng:** policy service lỗi, thông tin quyền thiếu, tenant không tìm thấy, token không hợp lệ hoặc quyết định quyền không xác định thì hành vi có đúng chính sách không?

### 3.3. Complete mediation

Mọi đường thực hiện một hành động cần được kiểm tra quyền tại nơi thích hợp, thay vì chỉ kiểm tra lần đầu trong giao diện. Đường truy cập có thể gồm controller, GraphQL resolver, queue consumer, batch job, storage URL và admin endpoint.

Không có nghĩa mọi thành phần phải gọi một service authorization giống hệt trong mọi trường hợp; nhưng toàn bộ đường đi phải **bảo toàn bất biến quyền** và không tạo ra đường bypass.

### 3.4. Separation of duties

Một người/tài khoản không nên đơn phương thực hiện chuỗi thao tác nhạy cảm khi chính sách yêu cầu phân tách: ví dụ người đề nghị thay đổi quyền production không tự phê duyệt mọi thay đổi của mình, hoặc người sửa điểm ngoài kỳ không tự xóa audit trail.

Assurance phải xem **khả năng phối hợp role/quyền thực tế**, kể cả role tích lũy và tài khoản dự phòng, chứ không chỉ thiết kế sơ đồ RACI đẹp.

### 3.5. Need-to-know, minimization và time-bounded access

Quyền theo nhu cầu truy cập dữ liệu, mục đích, trạng thái và thời gian; giảm phạm vi dữ liệu được lấy hoặc xuất để giảm impact. Quyền tạm thời nên có thời hạn theo chính sách, và quá trình gia hạn cần được kiểm soát.

Không nên mặc định mọi quyền đều phải hết hạn sau một khoảng cố định cho mọi hệ thống. Thời hạn phải phản ánh rủi ro, quy trình công việc và nghĩa vụ áp dụng.

### 3.6. Accountability và traceability

Có thể xác định chủ thể, hành động, tài nguyên, thời điểm, kết quả và nguồn phê duyệt khi cần điều tra. Log phải **đủ hữu ích và được bảo vệ**, không đưa token hay nội dung dữ liệu nhạy cảm không cần thiết vào hệ thống theo dõi.

## 4. Các mô hình phân quyền và giới hạn của chúng

| Mô hình | Cơ sở quyết định | Ví dụ | Rủi ro cần kiểm tra |
|---|---|---|---|
| **DAC – Discretionary Access Control** | Chủ sở hữu tài nguyên có thể phân quyền theo quy tắc | Giảng viên chia sẻ tài liệu được phép | Chia sẻ quá rộng, quyền lan truyền, owner không còn hợp lệ |
| **MAC – Mandatory Access Control** | Quy tắc gắn mức phân loại/nhãn được quản trị tập trung | Truy cập dữ liệu theo nhãn/phạm vi | Nhãn sai, bypass, dữ liệu chuyển mức không được kiểm soát |
| **RBAC – Role-Based Access Control** | Role và tập quyền gắn với role | STUDENT, TEACHER, SUPPORT | Role quá rộng, role tích lũy, không xét đối tượng |
| **ABAC – Attribute-Based Access Control** | Thuộc tính subject, object, action, environment | Chỉ được tải khi có quan hệ lớp và trạng thái phù hợp | Thuộc tính sai/cũ, nguồn attribute không đáng tin |
| **ReBAC – Relationship-Based Access Control** | Quan hệ giữa chủ thể và đối tượng | Giảng viên đang được phân công lớp 42 | Quan hệ lỗi thời, đường quan hệ gián tiếp không mong muốn |
| **Policy-based/combined approach** | Chính sách phối hợp nhiều điều kiện | Role TEACHER + lớp được giao + hành động export được phép | Không nhất quán giữa PEP, policy cache và nguồn dữ liệu |

Không có mô hình nào tự bảo đảm an toàn. **Role TEACHER** thường chưa đủ để xác định giảng viên có được xem **lớp 42** hay không. Một ABAC engine có khả năng biểu đạt tốt vẫn có thể đưa quyết định sai nếu dữ liệu “teacherOfClass” không đúng hoặc không được cập nhật khi thu hồi quyền.

### 4.1. Từ role đến permission theo đối tượng

Quy tắc:

> “TEACHER được xuất dữ liệu học viên”

rất dễ bị diễn giải thành có quyền với mọi lớp. Một quy tắc phù hợp hơn là:

> “Chủ thể có quyền TEACHER và đang có phân công hợp lệ tới lớp được yêu cầu, trong đúng tổ chức/tenant, được phép xuất những trường dữ liệu mà chính sách cho phép.”

Nhiều hệ thống cần kết hợp **RBAC để giới hạn chức năng** và **ReBAC/ABAC để quyết định phạm vi đối tượng**. Framework yêu cầu của tổ chức cần đặc tả chính xác điều kiện, không dừng ở tên mô hình.

### 4.2. Phân quyền ở nhiều lớp

~~~mermaid
flowchart TD
    U["Người dùng hoặc workload"] --> A["Authentication / session"]
    A --> G["Gateway hoặc edge checks"]
    G --> P["PEP tại API/service"]
    P --> D{"PDP: policy + attributes + relationships"}
    D -->|"Deny"| X["Từ chối, không tạo side effect trái quyền"]
    D -->|"Allow"| S["Service logic giới hạn đúng scope"]
    S --> W["Queue / worker / downstream"]
    W --> O["DB / file / object storage"]
    D --> L["Policy decision telemetry"]
    S --> L
    W --> L
~~~

Sơ đồ minh họa một luồng, không phải yêu cầu bắt buộc phải có PDP tách riêng. Với hệ thống nhỏ, quyết định quyền có thể nằm trong service. Điều cần đảm bảo là **điểm thực thi quyền phù hợp với từng trust boundary**, policy thống nhất và dữ liệu đầu vào đáng tin.

## 5. Chuyển rủi ro thành yêu cầu access control kiểm chứng được

### 5.1. Risk scenario

**Tài sản:** hồ sơ học viên, điểm, bài nộp, file export và token truy cập.

**Mục tiêu:** mỗi học viên chỉ xem dữ liệu thuộc phạm vi của mình, giảng viên chỉ quản lý lớp được giao, admin chỉ thao tác trong nhiệm vụ có thẩm quyền.

**Kịch bản:** một người dùng đã xác thực thay classId/learnerId trong API để lấy dữ liệu ngoài quyền; hệ thống có thể bỏ sót object-level authorization.

### 5.2. Viết security invariant

**Security invariant** là điều phải luôn đúng đối với hành động thuộc phạm vi:

> Mọi lượt đọc hoặc xuất hồ sơ học viên phải kiểm tra quyền theo **chủ thể, hành động, đối tượng, tenant và trạng thái quyền** tại điểm thực thi phù hợp; yêu cầu ngoài quyền không được trả dữ liệu hoặc tạo side effect phát sinh file/job có thể truy cập trái phép.

Điều này có thể dẫn đến nhiều requirements:

| Requirement ID | Tiêu chí yêu cầu | Control liên quan | Test/evidence chính |
|---|---|---|---|
| AC-REQ-01 | Chủ thể được xác thực bằng cơ chế tin cậy trước khi truy cập dữ liệu bảo vệ | Session/token validation | Login/session tests, config, audit |
| AC-REQ-02 | Hành động và đối tượng được kiểm tra quyền phía server | Object-level authorization | Negative tests cho lớp/học viên ngoài quyền |
| AC-REQ-03 | Dữ liệu tenant A không được lộ cho actor của tenant B | Tenant isolation | Cross-tenant test, query/worker review |
| AC-REQ-04 | Quyền đã bị thu hồi phải được phản ánh theo chính sách vòng đời | Revocation/invalidation | Test thu hồi quyền, session/cache tests |
| AC-REQ-05 | Batch/worker/export không vượt scope đã xác nhận | Async job authorization | Queue/job/file side-effect tests |
| AC-REQ-06 | Quyền hỗ trợ/admin được cấp, kiểm soát và review theo thẩm quyền | Privileged access management | Approval, role export, access review |
| AC-REQ-07 | Hoạt động nhạy cảm có audit trail hữu ích và được bảo vệ | Audit/monitoring | Synthetic event, log pipeline, alert test |
| AC-REQ-08 | Quyền của workload và vendor được giới hạn theo mục đích | Least privilege và supplier controls | IAM export, secret/scope review, negative test |

Một requirement phải có **scope và tiêu chí rõ ràng**. “Bảo vệ toàn bộ dữ liệu” là mục tiêu; muốn kiểm thử cần biết **ai, thao tác gì, đối tượng nào và điều kiện nào**.

## 6. Access control assurance theo ba lớp effectiveness

Một control có thể được đánh giá ở ba lớp:

| Lớp | Câu hỏi | Bằng chứng minh họa | Giới hạn |
|---|---|---|---|
| **Design effectiveness** | Chính sách/quy tắc được thiết kế có ngăn đúng lạm dụng và đường bypass? | Threat model, use/abuse cases, policy design, architecture review | Chưa chứng minh code/config thực tế đã đúng |
| **Implementation effectiveness** | Quy tắc đã được triển khai đúng ở mọi điểm và môi trường trong scope? | Code/config thực tế, API tests, IAM policies, deploy mapping | Một test snapshot chưa chứng minh cả kỳ vận hành |
| **Operating effectiveness** | Quyền được cấp/thu hồi, giám sát và thực thi nhất quán trong thời kỳ đánh giá? | Access review, joiner–mover–leaver records, audit logs, định kỳ retest, drift history | Không tự suy rộng ra tài sản, thời kỳ chưa kiểm tra |

Ví dụ, một chính sách yêu cầu MFA cho admin là bằng chứng về **yêu cầu**, screenshot MFA bật là một phần bằng chứng triển khai tại thời điểm, còn kết luận “mọi tài khoản admin production được MFA bảo vệ trong quý” cần **population đầy đủ, đường đăng nhập, ngoại lệ và dữ liệu lịch sử liên quan**.

### 6.1. Đặt claim đúng phạm vi

**Claim quá rộng:** “Tất cả tài khoản trong công ty đã an toàn.”

**Claim tốt hơn:** “Trong kỳ đánh giá đã xác định, các tài khoản con người thuộc danh sách có quyền quản trị production được đối chiếu với yêu cầu cấp/thu hồi quyền và phương thức xác thực áp dụng; những đường chưa được kiểm chứng và ngoại lệ được báo riêng.”

**Giới hạn:** Claim không tự bao phủ workload identities, nhà cung cấp hoặc môi trường khác nếu không có evidence. Điều kiện để kết luận phải được định nghĩa trước khi thu thập.

## 7. Kiểm chứng toàn bộ vòng đời danh tính và quyền

### 7.1. Joiner – Mover – Leaver

Một phần lớn rủi ro access control nằm ngoài mã ứng dụng: **quyền được cấp sai hoặc không thu hồi đúng lúc**.

| Giai đoạn | Kịch bản kiểm soát | Evidence nên xem |
|---|---|---|
| **Joiner – gia nhập** | Tạo danh tính, xác minh owner, cấp vai trò theo yêu cầu hợp lệ | Request, approval, role mapping, thời điểm cấp |
| **Mover – thay đổi vai trò** | Chuyển lớp, phòng ban, dự án; bỏ quyền cũ không còn cần | Trạng thái phân công trước/sau, access review, test quyền |
| **Leaver – rời hệ thống** | Thu hồi quyền, session, khóa/API, VPN, tài khoản thuộc phạm vi | Deprovision log, IdP/IAM export, revoke test |
| **Periodic recertification** | Chủ sở hữu xác nhận quyền còn đúng mục đích | Population, quyết định review, action và retest |
| **Emergency/break-glass** | Cấp quyền khẩn theo điều kiện, hạn dùng, audit và hậu kiểm | Approval hoặc căn cứ khẩn cấp, session log, review hậu kiểm |
| **Non-human identities** | Tạo/luân chuyển/thu hồi workload identity và secret | Service inventory, IAM scopes, owner, usage và rotation evidence |

### 7.2. Định nghĩa population trước khi kiểm tra

Muốn chứng minh “mọi admin có quyền hợp lệ”, phải xác định **mẫu số**:

- IdP accounts; local accounts; cloud IAM principals.
- Privileged groups và inherited permissions.
- Quyền phát sinh từ tạm quyền hoặc role chaining.
- Tài khoản support của nhà cung cấp và tài khoản khẩn cấp.
- API keys, service accounts hoặc machine identities có quyền tương đương, nhưng được đánh giá theo cơ chế riêng.
- Những môi trường production ở nhiều account, project hoặc region.

Một danh sách xuất từ **một hệ thống IAM** có thể bỏ sót quyền tồn tại ở ứng dụng cũ hoặc cloud account khác. Cần đối chiếu inventory và các nguồn liên quan, ghi rõ loại trừ có căn cứ.

### 7.3. Quyền thường là kết quả của nhiều đường cấp

Ví dụ người dùng có thể là ADMIN do gán trực tiếp, là thành viên group, do role kế thừa hoặc qua hệ thống support. Phép đánh giá phải quan tâm **effective permissions**, không chỉ một hàng trong bảng role.

Một entitlement review tốt hỏi:

1. Quyền có owner không?
2. Phạm vi và mục đích còn hợp lệ không?
3. Có approval hoặc quyết định tương ứng không?
4. Có quyền thừa hoặc quyền mâu thuẫn separation of duties không?
5. Nếu phải thu hồi, thay đổi đã được thực thi và kiểm chứng chưa?

### 7.4. Thu hồi phải đúng với cache và session

Thu hồi một role trong database có thể chưa làm mất quyền ngay nếu token chứa claim cũ, decision cache còn lưu, worker có job chờ hoặc signed download link chưa hết hạn.

Chuẩn assurance phải xác định **mức trễ thu hồi cho phép theo rủi ro và chính sách**, rồi kiểm tra với luồng thực. Không mặc định mọi hệ thống phải có khả năng thu hồi mọi quyền trong 0 giây; cũng không nên xem token còn hợp lệ là bằng chứng quyền nghiệp vụ vẫn hợp lệ nếu chính sách yêu cầu kiểm tra lại theo thời điểm.

## 8. Authorization trong API và nghiệp vụ

### 8.1. Function-level authorization

Hệ thống có kiểm tra actor được **gọi chức năng** không? Ví dụ STUDENT không được gọi API thay đổi điểm, dù biết đúng URL và request schema.

Cần kiểm thử cả **HTTP method, alternate routes, GraphQL operations, bulk APIs, admin endpoints và giao diện mobile** trong phạm vi. Ẩn nút trên UI không phải access control phía server.

### 8.2. Object-level authorization

Người dùng được phép gọi chức năng chung nhưng không nhất thiết được truy cập mọi đối tượng.

Ví dụ giảng viên lớp 42 gọi export với classId 43; kiểm tra role TEACHER đơn thuần là không đủ. Backend phải ràng buộc quyền với đúng đối tượng/tập dữ liệu.

**Phép thử âm:** actor không được phân công vẫn thử thao tác với ID có thật thuộc actor khác. Cần xác nhận dữ liệu không lộ ra response, file, cache hoặc job.

### 8.3. Property-level authorization và dữ liệu tối thiểu

Một actor có quyền xem hồ sơ học viên có thể chỉ được xem tên và tiến độ, không được xem thông tin nhạy cảm hoặc dữ liệu hỗ trợ riêng tư. Access control cần xét **trường dữ liệu** và hành động xuất hàng loạt, không chỉ quyền tới object.

**Kiểm chứng:** test response serialization, các trường ẩn, export CSV/PDF, log và event payload. Dữ liệu không xuất hiện trên UI chưa chứng minh backend không gửi trường đó.

### 8.4. Tenant isolation

Ứng dụng đa tenant cần xem ranh giới:

- Actor thuộc tenant nào theo nguồn đáng tin?
- Tài nguyên có tenant owner được xác minh không?
- Mọi truy vấn, cache key, job message, object storage path có giữ tenant scope?
- Quyền quản trị xuyên tenant có quy trình và audit riêng?
- Có đường đồng bộ/analytics/batch làm gộp dữ liệu nhiều tenant không?

Không nên chỉ kiểm thử vài màn hình. Một lỗi WHERE theo tenant hoặc job bị thay tenantId có thể gây dữ liệu bị lẫn dù API frontend đúng.

### 8.5. Workflow và business-logic authorization

Quyền có thể thay theo **trạng thái tài nguyên**: chỉ sửa điểm trước khi khóa sổ; chỉ người phụ trách lớp còn hoạt động được duyệt; hoàn tiền cần đúng quy trình và phân tách nhiệm vụ.

Test phải kiểm tra:

- Hành động đúng/sai thứ tự.
- Tài nguyên ở trạng thái đã đóng, lưu trữ, thu hồi hoặc chuyển owner.
- Actor có nhiều role và quan hệ thay đổi.
- Request cạnh tranh hoặc retry khi điều kiện quyền thay đổi.
- Thao tác đặc quyền với cơ chế phê duyệt riêng.

Một kỹ thuật authorization đúng về vai trò nhưng sai **business policy** vẫn có thể tạo security finding.

## 9. Đường bất đồng bộ, worker và file download

### 9.1. Vì sao một HTTP 403 chưa đủ?

Luồng export điển hình:

~~~mermaid
flowchart LR
    A["Giảng viên"] --> B["API export"]
    B --> C["Authorization decision"]
    C --> D["Queue job có scope"]
    D --> E["Worker đọc dữ liệu"]
    E --> F[("Private file storage")]
    F --> G["Download authorization"]
    G --> H["Người được phép nhận file"]
~~~

Có thể xảy ra lỗi: API trả 403 sau khi đã đẩy job, worker chỉ tin classId trong message, hoặc file được lưu private nhưng link tải bị dùng lại không theo quyền.

**Assurance phải xem cả side effects**:

- Request bị từ chối có vẫn tạo job không?
- Job payload có được tạo từ scope tin cậy và bảo vệ integrity không?
- Worker có dùng quyền quá rộng hoặc bỏ qua ràng buộc nghiệp vụ không?
- Khi quyền actor thay đổi giữa lúc xếp hàng và lúc chạy, hệ thống thực hiện policy nào?
- File có thể bị đọc bằng URL/reference không hợp lệ hoặc đã hết điều kiện không?
- Dữ liệu được cleanup/expiry đúng chính sách không?
- Log có thể đối chiếu request → job → file → download không?

### 9.2. TOCTOU: quyền đổi giữa kiểm tra và sử dụng

**Time-of-check to time-of-use (TOCTOU)** trong authorization xuất hiện khi điều kiện quyền thay đổi giữa thời điểm kiểm tra và lúc dùng tài nguyên. Điều này đặc biệt quan trọng với batch export, job chạy lâu, signed URL và cache.

Thiết kế có thể chọn **kiểm tra lại ở thời điểm sử dụng**, hoặc bảo toàn một **ủy quyền bị giới hạn chặt** cho job đã được phê duyệt theo chính sách. Sự lựa chọn phải rõ mục tiêu và tình huống cần thu hồi, không mặc định có một giải pháp đúng cho mọi nghiệp vụ.

### 9.3. Signed URL và object storage

Signed URL có thể là cơ chế phân phối file có thời hạn, nhưng **không tự thay authorization đối với người nhận** nếu URL có thể bị chia sẻ/đánh cắp và vẫn sử dụng trong thời hạn. Cần xem:

- Ai được phát URL và gắn với file nào?
- TTL/phạm vi sử dụng theo chính sách?
- Hành vi khi user bị thu hồi quyền?
- Bucket/object ACL và quyền workload liên quan?
- Có hạn chế loại file, scope và thông tin nhạy cảm trong URL/log không?
- Có khả năng thu hồi hoặc ngắt đường tải khi cần?

Kết luận assurance phải nói rõ thuộc tính nào được bảo đảm bởi URL, thuộc tính nào cần control khác.

## 10. IAM và quyền truy cập hạ tầng/cloud

### 10.1. Human privileged access

Các quyền cloud admin, database admin, deployment admin, secret manager và IAM policy modification thường có impact lớn nếu bị lạm dụng.

Control được xem xét có thể gồm:

- Xác thực phù hợp, MFA và session controls theo baseline.
- Tài khoản cá nhân có owner, tránh dùng shared admin ngoài ngoại lệ có kiểm soát.
- Cấp quyền tối thiểu, tách nhiệm vụ, quyền nâng cao tạm thời khi phù hợp.
- Phê duyệt theo thẩm quyền trước khi cấp hoặc thay đặc quyền.
- Review quyền theo kỳ và khi có chuyển vai trò.
- Logging/alert cho hành động quan trọng, quy trình phản ứng.
- Kiểm soát đường break-glass và hậu kiểm.
- Rà soát tác động của group, inherited role, wildcard permission.

### 10.2. Workload identities và service accounts

Một service account không đăng nhập bằng MFA như người dùng con người, nhưng vẫn cần assurance về:

- Owner và purpose có định nghĩa.
- Identity thực thi từ workload hoặc service đúng nguồn.
- Quyền chỉ đủ dùng và phân tách môi trường.
- Credential được bảo vệ, luân chuyển/thu hồi và giám sát khi thích hợp.
- Không sử dụng secret tĩnh hoặc chia sẻ không cần thiết nếu có cơ chế mạnh hơn phù hợp.
- Quyền được review khi workload/nghiệp vụ thay đổi.
- Hành vi ngoài scope bị từ chối và có thể phát hiện.

**Đừng chấm service account “MFA fail” chỉ vì không thể chạy luồng đăng nhập người dùng.** Hãy áp dụng requirement tương ứng với workload identities và kiểm tra loại credential/quyền thực tế. Ngược lại, cũng không bỏ qua service accounts khỏi inventory chỉ vì không phải tài khoản con người.

### 10.3. Quyền từ vendor và CI/CD

Một token của vendor được cấp read toàn bộ dữ liệu học viên hoặc CI/CD runner có quyền thay IAM policy đều là chủ thể có thể tạo ảnh hưởng lớn. Cần đánh giá shared responsibility, OAuth scope, secret storage, hợp đồng/owner, xác thực webhook, quyền tạm và khả năng revoke khi sự cố.

Chứng nhận của vendor hoặc việc pipeline có chức năng RBAC **không tự chứng minh** cấu hình tenant và quyền của bên sử dụng là đúng.

## 11. Xây access-control assurance plan

Một kế hoạch kiểm chứng nên liên kết từ claim đến test và evidence.

### 11.1. Những trường tối thiểu

| Trường | Nội dung cần xác định |
|---|---|
| **Claim ID và security objective** | Điều gì được cho là đã được bảo đảm? |
| **Risk scenarios** | Những cách lạm dụng nào đang được kiểm soát? |
| **Scope** | Ứng dụng, API, tenant, account, user group, region, environment, kỳ |
| **Population** | Tổng thể tài khoản/quyền/đường truy cập cần kiểm tra |
| **Access policy** | Quy tắc allow/deny và các exception hợp lệ |
| **Control owner** | Ai chịu trách nhiệm vận hành và sửa control? |
| **Evidence owner/reviewer** | Ai thu thập, ai kiểm tra độc lập theo vai trò? |
| **Methods** | Inspection, test, observation, sampling, automated checks |
| **Expected outcomes** | Điều kiện pass, fail, insufficient evidence, N/A |
| **Evidence** | Nguồn, build, config, role export, log, approval, timestamp |
| **Frequency/triggers** | Khi nào phải thu thập/đánh giá lại? |
| **Findings và risk owner** | Cách mở issue, khắc phục, retest và quyết định residual risk |

### 11.2. Kế hoạch mẫu theo control

| Control | Design evidence | Implementation evidence | Operating evidence |
|---|---|---|---|
| Authorization theo lớp | Chính sách role–class và threat model | Code review, endpoint/worker tests | Regression results theo release, audit/log và review quyền |
| Cloud admin access | IAM baseline, phân nhiệm vụ | Config export, role & MFA policy | Access review, cấp/thu hồi, break-glass records |
| Tenant isolation | Data flow và logical isolation design | Query/config checks, cross-tenant tests | Drift/history, incidents, repeated tests |
| Workload least privilege | Data/access requirement và IAM design | Runtime policy, negative permissions tests | Review quyền, key/role usage, changes |
| File download | Data classification và sharing policy | Storage ACL/URL controls, test | Download audit, incident/revocation review |
| Logging sensitive access | Audit schema và detection use case | Log configuration và event tests | Pipeline health, alert routing, triage records |

## 12. Test matrix: không chỉ có trường hợp được phép

Một **authorization test matrix** kết hợp actor, hành động, đối tượng, trạng thái và kỳ vọng.

| Test ID | Actor | Object và trạng thái | Hành động | Kỳ vọng |
|---|---|---|---|---|
| AUTHZ-01 | Giảng viên lớp 42 | Lớp 42, quyền còn hiệu lực | Xuất học viên | Allow trong phạm vi và audit theo policy |
| AUTHZ-02 | Giảng viên lớp 42 | Lớp 43, không có phân công | Xuất học viên | Deny; không tạo file/job lộ dữ liệu |
| AUTHZ-03 | Học viên lớp 42 | Điểm của học viên khác | Xem điểm | Deny theo quyền đối tượng |
| AUTHZ-04 | Giảng viên đã bị thu hồi quyền | Lớp 42 | Xuất học viên | Deny theo chính sách thu hồi |
| AUTHZ-05 | Actor tenant A | Dữ liệu tenant B | Đọc hoặc cập nhật | Deny trên mọi tuyến thuộc scope |
| AUTHZ-06 | Người chưa đăng nhập | Endpoint bảo vệ | Đọc dữ liệu | Từ chối theo cơ chế AuthN/AuthZ |
| AUTHZ-07 | Nhân sự hỗ trợ không có approval | Chức năng thay điểm | Thực hiện ngoại lệ | Deny hoặc yêu cầu quy trình đúng |
| AUTHZ-08 | Job sai scope | Message/export task | Xử lý job | Không tạo dữ liệu ngoài quyền |
| AUTHZ-09 | Actor có role hợp lệ nhưng resource đã lưu trữ | Lớp hết hạn theo policy | Sửa điểm | Deny nếu không có ngoại lệ hợp lệ |
| AUTHZ-10 | Tài khoản service chỉ đọc | API/DB write | Cập nhật | Deny; có evidence quyền tối thiểu |
| AUTHZ-11 | Admin có quyền đặc biệt | Thao tác trong scope được duyệt | Quản trị | Cho phép và ghi dấu vết theo policy |
| AUTHZ-12 | Người dùng không còn quyền tải | File xuất trước đó | Tải file | Hành vi đúng chính sách revocation/URL |

**Test matrix chỉ có giá trị khi các fixtures và quyền được tạo đúng**. Nếu “actor không có quyền” thực tế vẫn có role kế thừa quyền lớp 43, test trả 200 không thể tự kết luận code lỗi; phải xác minh effective permissions.

### 12.1. Kiểm thử âm, dương và hậu điều kiện

- **Positive tests:** actor hợp lệ hoàn thành chức năng được cấp, không khiến policy chặn sai.
- **Negative tests:** actor thiếu quyền bị từ chối dù biết URL, ID hoặc format request.
- **Boundary tests:** chuyển role, hết hạn, thay tenant, trạng thái tài nguyên, cấp quyền đúng lúc.
- **Side-effect tests:** request bị deny không sửa DB, tạo file, queue job hoặc gửi thông báo trái quyền.
- **Cross-channel tests:** web/mobile, API, batch, GraphQL, worker và download phù hợp scope.
- **Failure tests:** policy source không sẵn sàng, quyết định quyền thiếu dữ liệu, cache không cập nhật.
- **Audit tests:** log sự kiện cần thiết mà không lộ token hoặc toàn bộ dữ liệu.

### 12.2. Kết quả 401, 403 và ý nghĩa thực tế

Một API HTTP có thể dùng **401 Unauthorized** khi cần xác thực hợp lệ và **403 Forbidden** khi chủ thể đã được nhận diện nhưng không được cấp quyền; cách sử dụng phải theo protocol/API contract và chính sách thiết kế. Không nên coi một status code tự nó là đủ bằng chứng về authorization, vì bên trong hệ thống có thể đã tạo side effects hoặc phản hồi có nội dung nhạy cảm.

### 12.3. Khi nào cần test toàn population?

Kiểm thử tất cả các đối tượng/đường có thể có chi phí lớn. Có thể kết hợp:

- **Automated coverage** cho mọi route/role/resource mẫu có thể kiểm tra theo framework.
- **Risk-based test** cho tuyến trọng yếu và tài khoản đặc quyền.
- **Sampling** cho review quyền, thay đổi và hồ sơ approval theo phương pháp rõ population.
- **Runtime monitoring** để phát hiện drift và đường mới.
- **Focused retest** khi incident hoặc finding xuất hiện.

Không có tỷ lệ mẫu chung như 10% luôn đủ. Cần nêu phương pháp, exclusions và phạm vi kết luận; nếu kiểm thử thiếu một tuyến export cũ, không được tuyên bố toàn bộ export đã an toàn.

## 13. Ví dụ Java: điểm thực thi phân quyền có kiểm chứng

### 13.1. Anti-pattern: chỉ kiểm tra role chung

Một cách viết có vấn đề về thiết kế là:

~~~java
// Anti-pattern: kiểm tra role TEACHER nhưng bỏ qua classId.
public ExportJobId createExport(User actor, long classId) {
    if (!actor.hasRole("TEACHER")) {
        throw new AccessDeniedException("Forbidden");
    }
    return exportJobs.submit(actor.id(), classId);
}
~~~

Đoạn code có thể cho phép giảng viên A xuất lớp của giảng viên B nếu không có lớp control nào khác ngăn chặn. **Role hợp lệ không đồng nghĩa có quyền với mọi đối tượng**.

### 13.2. Phác thảo kiểm soát phía server

~~~java
// Minh họa nguyên tắc. Các kiểu dữ liệu/service tùy hệ thống.
public ExportJobId createExport(
        AuthenticatedPrincipal actor,
        long classId) {

    if (!accessPolicy.canExportLearners(actor.userId(), classId)) {
        throw new AccessDeniedException("Export not permitted");
    }

    // Tạo yêu cầu từ identity đã xác thực, không lấy actorId từ client.
    // Worker và đường tải phải tiếp tục bảo toàn giới hạn quyền.
    return exportJobs.submitAuthorizedScope(actor.userId(), classId);
}
~~~

Điều này hỗ trợ object-level authorization tại điểm tạo job, nhưng **chưa đủ để kết luận end-to-end an toàn**. Cần xét:

- **Nguồn quan hệ:** accessPolicy lấy thông tin quyền từ đâu và cache có thể cũ không?
- **Tenant:** classId có thuộc tenant actor đang hoạt động không?
- **Race/revocation:** giữa lúc kiểm tra và job hoàn thành, quyền thay đổi thì sao?
- **Worker:** có xác minh scope từ nguồn tin cậy hay tin tùy tiện vào message?
- **Storage/download:** file có thể được tải ngoài quyền không?
- **Audit:** request và job có thể đối chiếu ai làm gì, trong kỳ nào?
- **Error path:** lỗi tạo job hoặc deny có phát sinh side effects không?

### 13.3. Ví dụ giả mã kiểm thử Java

Đoạn dưới biểu đạt **ý đồ test**, không phải bài test đầy đủ có thể chạy nguyên xi; tên fixture và service cần thay theo dự án.

~~~java
@Test
void teacherCannotExportAnotherClass() {
    // Given: giảng viên A quản lý class 42, không quản lý class 43.
    var actor = fixtures.teacherAssignedOnlyTo(42L);

    // When/Then: yêu cầu export lớp 43 phải bị từ chối.
    assertThrows(
        AccessDeniedException.class,
        () -> exportApi.createExport(actor, 43L)
    );

    // Hậu điều kiện: không có job/file dữ liệu lớp 43.
    assertFalse(exportJobs.existsFor(actor.userId(), 43L));
    assertFalse(exportFiles.wasCreatedFor(actor.userId(), 43L));
}
~~~

**Cảnh báo về giới hạn bằng chứng:** mock trong unit test có thể đã được cấu hình trả deny nên test vẫn pass khi policy production sai. Cần bổ sung **integration/e2e tests dùng policy và dữ liệu quyền thực tế tương đương**, xác minh artifact đã deploy và side effects ngoài service.

### 13.4. Policy test cũng phải có positive case

Nếu mọi request bị deny vì policy service hỏng, negative tests có thể pass nhưng ứng dụng không đáp ứng chức năng hợp lệ. Hãy kiểm tra cả trường hợp giảng viên được phân quyền có thể xuất **đúng dữ liệu**. Assurance cần chứng minh **kiểm soát đúng**, không chỉ hệ thống luôn từ chối.

## 14. Evidence standard cho access control

### 14.1. Bằng chứng có những thuộc tính nào?

| Thuộc tính | Câu hỏi | Ví dụ sai |
|---|---|---|
| **Relevance** | Artifact có chứng minh đúng policy/requirement nào? | Dùng screenshot MFA để chứng minh object-level authorization |
| **Scope** | Có bao phủ tài khoản, role, resource, environment và route liên quan không? | Chỉ test web, bỏ mobile/API |
| **Completeness** | Population có đủ, có lọt tài khoản local, emergency, service không? | IAM export chỉ từ một account |
| **Freshness/period** | Evidence phản ánh thời điểm/kỳ được kết luận không? | Ảnh config cũ sau đổi IdP |
| **Provenance** | Ai/cái gì tạo, từ hệ thống nào, bằng method và version nào? | File tên “audit-final” không biết nguồn |
| **Integrity** | Bản lưu có bị chỉnh sửa trái phép, có đối chiếu nguồn được? | Sửa tay số dòng để khớp tỷ lệ |
| **Reliability** | Tool, log pipeline và test có hoạt động đúng không? | Scanner không đủ quyền nhưng báo không thấy lỗi |
| **Representativeness** | Mẫu có phù hợp population và rủi ro không? | Chỉ chọn vài access review đẹp |
| **Repeatability** | Người khác có thể kiểm tra lại phương pháp/nguồn không? | “Đã check bằng mắt” không có chi tiết |

Một câu trả lời “Access controls configured: Yes” trong bảng hỏi chỉ hỗ trợ **lời xác nhận**; chưa tự chứng minh runtime. Cần chọn bằng chứng theo claim, impact và độ bất định.

### 14.2. Metadata tối thiểu

Một evidence record nên chứa:

1. **Evidence ID** và claim/control/requirement IDs.
2. Asset, environment, tenant, application và đường truy cập được xét.
3. Population, dữ liệu test, số lượng mẫu, exclusions.
4. Event time, collection time, assessment period, timezone.
5. Nguồn hệ thống, extraction query/script, tool/test version.
6. Commit/build/artifact/deployment nếu test liên quan release.
7. Owner, người thu thập, reviewer và thẩm quyền kết luận.
8. Expected result, actual result, negative/positive outcome.
9. Links tới log, audit trail, bản ghi quyền, approval, finding/retest.
10. Data classification, nơi lưu, integrity checks, retention.
11. Assumptions, limitations và confidence của kết luận.

Không nhất thiết nhập thủ công mọi trường. CI/CD, IAM và log platform có thể tự xuất dữ liệu, nhưng **đường tự động hóa cũng cần kiểm tra chất lượng**.

### 14.3. Mẫu evidence record YAML

Mẫu dưới đây chỉ dùng ID, kỳ và giá trị minh họa; **không phải bằng chứng đã chạy trên hệ thống thật**.

~~~yaml
evidence_id: EVD-AC-LEARNING-EXPORT-001
claim_id: CLAIM-AC-EXPORT-01
requirement_ids: ["AC-REQ-02", "AC-REQ-03", "AC-REQ-05"]
control_id: CTRL-APP-AUTHZ-01
scope:
  service: "Learning Platform API"
  environment: "production"
  paths: ["export-api", "export-worker", "file-download"]
  tenant_groups: ["Tenants included in approved assessment"]
  excluded: ["Legacy batch path pending separate assessment"]
assessment_period: "Kỳ đánh giá nội bộ đã được xác định"
source:
  test_suite: "authorization-integration-tests"
  build_reference: "actual-build-id-when-executed"
  deployment_reference: "actual-deploy-record-when-verified"
  method: "Positive/negative and side-effect checks"
owner:
  control: "Backend API Team"
  evidence: "QA/Platform"
  reviewer: "Security Assurance"
expected:
  - "Actor ngoài quyền không thể tạo export"
  - "Denied request không tạo dữ liệu hoặc file ngoài quyền"
  - "Job và file access bảo toàn scope"
observed:
  - "Điền kết quả thực tế sau kiểm thử"
limitations:
  - "Không kết luận cho đường batch chưa kiểm tra"
quality:
  provenance: "Needs verification"
  completeness: "Needs verification"
status: "Pending assessment"
retest_after_change: "Required when authorization path changes"
~~~

**Chú ý:** Không được điền một test PASS giả hoặc ghi “production safe” trước khi kiểm tra source và deployment. Nếu batch export chưa được test, phải **thu hẹp claim hoặc ghi insufficient evidence**.

## 15. Claim–Argument–Evidence cho access control

### 15.1. Một assurance claim mẫu

**Claim:** “Trong phạm vi các tuyến xuất dữ liệu học viên production được xác định, chỉ actor có quyền đối với đúng lớp/tập dữ liệu mới có thể tạo và tải file export theo chính sách”.

**Argument:**

1. Danh mục tuyến export và trust boundaries đã được kiểm tra.
2. API thực thi object-level authorization từ nguồn quyền đáng tin.
3. Export job được gắn scope được phê duyệt và worker không vượt qua scope.
4. Đường tải file thực thi quyền/chính sách vòng đời phù hợp.
5. Negative tests cho actor ngoài quyền và side effects được chạy theo build có liên kết production.
6. Runtime logging hỗ trợ giám sát, truy vết và đánh giá ngoại lệ.

**Evidence:**

- Data flow, inventory endpoint, policy specification.
- Code review và kết quả integration/end-to-end test.
- Token/role/relationship fixtures, expected/actual.
- Queue/job/file traces và download authorization tests.
- Deployment record, IAM/storage runtime config.
- Audit log/alert checks, access review, incident/finding history.
- Báo cáo exception và những đường chưa được test.

**Limitations:** Nếu đường batch, admin support hoặc tenant đặc biệt chưa được kiểm tra, kết luận không được mở rộng tới chúng. Một claim có phạm vi thật và giới hạn rõ thường đáng tin hơn một câu “100% an toàn” không có cơ sở.

### 15.2. Chuỗi truy vết

~~~mermaid
flowchart TD
    A["Objective: chỉ truy cập đúng quyền"] --> B["Risk: truy cập sai lớp/tenant"]
    B --> C["Requirement: object + tenant authorization"]
    C --> D["Policy/PEP/PDP và control owners"]
    D --> E["Test design: allow, deny, state change, side effects"]
    E --> F["Evidence: code, config, build, job, log"]
    F --> G{"Assessment đủ và đạt?"}
    G -->|"Có"| H["Claim theo scope/kỳ, residual risk"]
    G -->|"Không đạt"| I["Finding, remediation, retest"]
    G -->|"Thiếu"| J["Evidence gap / bổ sung test"]
    I --> E
    J --> E
    H --> K["Monitoring, access review, reassessment"]
    K --> B
~~~

Một requirement có thể được hỗ trợ bởi nhiều controls; một control có thể đáp ứng nhiều requirements. Mục tiêu là **truy vết mối quan hệ có thể kiểm chứng**, không phải lấp một bảng mapping bằng mã ID không có test.

## 16. Continuous access control assurance

### 16.1. Một lần kiểm thử chưa đủ cho cả vòng đời

Quyền và policy thay đổi khi nhân sự nghỉ việc, giảng viên chuyển lớp, tenant mới được tạo, token hết hạn, API mới được phát hành, cache/worker thay cách xử lý hoặc nhà cung cấp đổi tích hợp.

Một chương trình assurance liên tục có thể kết hợp:

| Tín hiệu | Cách kiểm soát | Bằng chứng hữu ích |
|---|---|---|
| Joiner/mover/leaver | Tự động đối chiếu hệ thống nhân sự và IAM theo scope | Approval, assignment, deprovision/revoke |
| IAM role drift | Diff quyền thực tế với baseline | Runtime policy export, drift alert/ticket |
| Ứng dụng đổi API hoặc endpoint | Authorization tests trong CI/CD theo scope | Test result theo build và coverage inventory |
| Thêm tenant, role hoặc business rule | Threat modeling, policy test và reviewer | Risk assessment, negative tests |
| Đường worker/batch đổi | Test end-to-end quyền và side effects | Job trace, file access, deployment mapping |
| Quyền đặc biệt được sử dụng | Privileged access review, log/alert | Session/action logs và review hậu kiểm |
| Sự kiện bị từ chối bất thường | Detection theo ngữ cảnh và điều tra | Log integrity/health, alert case |
| Vendor app đổi OAuth scopes | Reauthorization review, token inventory | Consent records, API scope export |
| Incident hoặc finding | Phân tích control failure và retest | Incident report, fix, test, residual risk |

**Continuous** là duy trì khả năng biết control đang hoạt động khi có biến động, không nhất thiết chạy mọi phép thử từng phút. Một quyền API critical có thể được kiểm thử theo release và giám sát liên tục; một review về thẩm quyền cấp quyền có thể theo kỳ, miễn phù hợp rủi ro và nghĩa vụ.

### 16.2. Kiểm tra sức khỏe telemetry

Nếu mọi audit log đều thiếu từ tối hôm trước, dashboard “0 truy cập trái phép” **không chứng minh** rủi ro thấp. Cần xem:

- Nguồn sự kiện trong inventory có đang gửi log?
- Ingest latency, mất dữ liệu, lỗi schema hoặc timezone?
- Alert rule/routing có được kiểm thử bằng sự kiện có kiểm soát?
- Người trực có nhận, xác định mức độ và phản ứng được không?
- Log có bị thay/xóa trái quyền; retention có đáp ứng nhu cầu?

Không thu thập tràn lan nội dung hồ sơ học viên trong log để “tăng bằng chứng”. Log phải đủ cho điều tra mà bảo vệ dữ liệu nhạy cảm theo chính sách.

### 16.3. Phát hiện quyền thừa bằng phân tích lịch sử

Một tài khoản không sử dụng quyền admin 90 ngày có thể là tín hiệu cần rà soát, nhưng **không tự chứng minh** quyền chắc chắn thừa: tài khoản khẩn cấp có thể được dự định ít dùng. Cần đánh giá **purpose, owner, nghĩa vụ, mức impact, điều kiện kích hoạt và phương án giới hạn**.

Dữ liệu sử dụng hỗ trợ quyết định, không thay access review được phê duyệt.

## 17. Quy trình đánh giá và xử lý sai lệch

### 17.1. Các trạng thái assessment

| Trạng thái | Điều kiện | Bước tiếp theo |
|---|---|---|
| **Pass / supported** | Control đáp ứng tiêu chí trong scope/kỳ, evidence đủ | Báo cáo claim có giới hạn và tiếp tục monitoring |
| **Fail / unsupported** | Có bằng chứng control cho phép hành động trái chính sách hoặc không đáp ứng yêu cầu | Ghi finding, đánh giá impact, containment, remediation |
| **Insufficient evidence** | Không xác định được trạng thái do thiếu population/test/log hoặc nguồn không tin cậy | Bổ sung evidence, thu hẹp claim, cân nhắc giảm phơi bày |
| **Not applicable** | Control/tiêu chí không áp dụng với scope có căn cứ | Ghi reason, owner, review trigger |
| **Exception / risk acceptance** | Sai lệch nội bộ được phê duyệt với điều kiện/thời hạn trong thẩm quyền | Giám sát riêng; không tự chuyển test fail thành pass |

Trạng thái nội bộ là **mô hình minh họa**; audit và chương trình compliance có thể có từ ngữ/tiêu chí bắt buộc riêng.

### 17.2. Ví dụ finding về truy cập chéo lớp

**Finding:** Khi actor của lớp 42 gửi yêu cầu export lớp 43, backend trả lỗi nhưng worker vẫn tạo file từ dữ liệu lớp 43 và lưu vào storage có đường truy cập chưa được ràng buộc đúng.

**Bằng chứng:** request/test fixture, job trace, file metadata, kiểm tra quyền lưu trữ, phiên bản ứng dụng và thời điểm phát hiện.

**Tác động:** nguy cơ lộ dữ liệu học viên. Cần xác minh liệu đã có ai truy cập file thật hay chưa; không được tự kết luận đã có breach hoặc ngược lại không có sự cố nếu thiếu log.

**Hành động:**

1. Giới hạn hoặc tạm dừng luồng export theo thẩm quyền và mức risk.
2. Bảo vệ evidence, điều tra phạm vi ảnh hưởng và nghĩa vụ xử lý sự cố nếu cần.
3. Sửa logic: kiểm soát scope trước khi tạo job, validation ở worker, bảo vệ storage/download.
4. Bổ sung positive/negative test và side effects cho các đường export tương tự.
5. Deploy qua quy trình có kiểm soát và retest trên bản/môi trường phù hợp.
6. Đánh giá residual risk và cập nhật kết luận assurance.
7. Duy trì regression tests và trigger khi thay data flow.

### 17.3. Chấp nhận rủi ro không làm thay đổi kết quả kiểm thử

Nếu một control không đạt nhưng tổ chức tạm giới hạn quyền và phê duyệt rủi ro còn lại trong thẩm quyền, bản ghi control vẫn cần **phản ánh sai lệch kỹ thuật**; acceptance/exception lưu riêng với owner, điều kiện, thời hạn, monitoring và remediation. Quyết định nội bộ không tự miễn nghĩa vụ pháp lý hoặc điều khoản bắt buộc.

## 18. Case study tổng hợp: assurance cho hệ thống export điểm

### 18.1. Bối cảnh

Nền tảng học trực tuyến dùng backend Java, PostgreSQL, queue và object storage. Một giảng viên có thể xuất danh sách điểm của lớp mình; dữ liệu chứa thông tin cá nhân và kết quả học tập. Quy trình gồm:

1. Frontend gửi yêu cầu export theo classId.
2. API xác thực session và kiểm tra quyền.
3. Backend đưa job vào queue.
4. Worker truy vấn database và ghi file.
5. Người yêu cầu tải file qua một đường được kiểm soát.
6. Audit log ghi hoạt động xuất dữ liệu.

Security owner muốn có bằng chứng rằng **actor ngoài quyền không thể lấy file**, kể cả qua worker và download. Đây là một **assurance claim**, không chỉ là yêu cầu chức năng.

### 18.2. Risk scenarios

| Risk ID | Kịch bản | Impact |
|---|---|---|
| R-AC-01 | Actor TEACHER xuất lớp khác do API chỉ kiểm tra role | Lộ điểm và hồ sơ học viên |
| R-AC-02 | Job payload có classId không được ràng buộc đúng quyền | Worker trích xuất ngoài phạm vi |
| R-AC-03 | File đã xuất có thể tải qua URL bị chia sẻ hoặc tham chiếu ngoài quyền | Lộ dữ liệu sau bước tạo file |
| R-AC-04 | Quyền bị thu hồi nhưng cache/token/job vẫn được dùng theo cách không phù hợp policy | Truy cập kéo dài ngoài điều kiện |
| R-AC-05 | Tài khoản support/service có quyền rộng không được review | Lạm dụng đặc quyền hoặc phạm vi ảnh hưởng lớn |
| R-AC-06 | Log thiếu hoặc không truy vết được export | Khó phát hiện/điều tra sự kiện |

### 18.3. Kiểm soát và trách nhiệm

| Control | Owner | Evidence cần có |
|---|---|---|
| Authorization theo role và lớp | Backend | Policy definition, negative tests, effective relationship |
| Scope cho job/worker | Backend + Worker | Job schema, integrity constraints, side-effect tests |
| Storage/download access | Platform | Runtime ACL, URL/access tests, expiry behavior |
| Access lifecycle | IAM + Product | Phân công lớp, thay quyền, revoke tests |
| Privileged/vendor access | Platform + Vendor owner | IAM export, approval, review, break-glass |
| Audit/detection | SecOps | Event schema, log health, synthetic event và triage |
| CI/CD release assurance | DevOps | Build, security tests, deployment mapping |

### 18.4. Quy trình đánh giá theo phiên bản

**Bước A — Scope:** lập danh sách endpoint web/mobile, queue/worker, storage, tenant, account, environment và kỳ. Ghi tuyến batch cũ nếu chưa kiểm tra.

**Bước B — Policy:** viết bảng quyết định allow/deny cho TEACHER, STUDENT, ADMIN, support, actor bị thu hồi, actor khác tenant và job sai scope. Xác nhận owner nghiệp vụ phê duyệt quy tắc.

**Bước C — Design review:** vẽ trust boundaries, xác định PEP/PDP và nguồn quan hệ lớp học; xem đường bypass, quyền worker và storage.

**Bước D — Implementation tests:** chạy test âm/dương, side effects, permission errors, scope validation, file download và chuyển trạng thái quyền.

**Bước E — Evidence:** lưu kết quả test theo build, runtime config, IAM policies, deploy mapping, job/file trace, audit pipeline và các ngoại lệ.

**Bước F — Operating review:** đối chiếu access review, role changes, log, incidents và kết quả kiểm thử theo kỳ.

**Bước G — Kết luận:** pass/fail/insufficient theo scope. Không đưa cả hệ thống vào “pass” nếu batch cũ chưa được chứng minh.

**Bước H — Residual risk:** risk owner quyết định hành động, giới hạn hoặc acceptance trong thẩm quyền; remediation có retest.

### 18.5. Một claim không đủ bằng chứng

Giả sử 20 negative tests đều pass nhưng API mới cho phép admin tạo export thay người khác qua một batch worker chưa nằm trong inventory. Không nên viết “mọi export an toàn”. Kết luận phù hợp là **“những đường đã kiểm thử đáp ứng tiêu chí; chưa đủ bằng chứng về batch admin, cần test và đánh giá quyền đặc biệt”**.

Tương tự, nếu test ở staging pass nhưng production chạy bản khác, phải có deployment/config evidence trước khi suy rộng claim.

## 19. Đo chất lượng access control assurance

| Chỉ số | Mục đích | Giới hạn khi diễn giải |
|---|---|---|
| % hệ thống/tuyến trọng yếu có access-control owner | Độ rõ trách nhiệm | Có owner chưa chứng minh control chạy đúng |
| % privileged identities có inventory và review hợp lệ | Bao phủ quyền đặc biệt | Population thiếu local/service account khiến tỷ lệ sai |
| % quyền mới được phê duyệt theo tiêu chí | Chất lượng cấp quyền | Quy trình approval có thể bị bypass ở đường khác |
| Thời gian thu hồi quyền sau trigger | Năng lực lifecycle | Phải so với SLA/risk policy, xem cache/session |
| % sensitive APIs có negative authorization tests | Độ phủ kiểm thử | Số test không chứng minh đúng các đường bypass |
| % release có authz regression và deploy evidence | Sự gắn kết với CI/CD | Test skip/bản deploy khác làm claim yếu |
| % access controls có operating evidence hợp lệ | Chất lượng assurance | Bằng chứng cũ hoặc sai scope không đủ |
| Số finding truy cập trái phép đang mở/quá hạn | Rủi ro tồn đọng | Không được đóng ticket chỉ để cải thiện số liệu |
| Số ngoại lệ admin/break-glass quá hạn | Kiểm soát quyền khẩn | Ít ngoại lệ có thể do chưa được ghi nhận |
| Thời gian từ phát hiện anomalous access đến triage | Hiệu quả monitoring/response | Không đo được sự kiện mà logging bỏ sót |
| Tỷ lệ remediation có retest end-to-end | Khả năng tránh tái diễn | Test chỉ ở controller có thể bỏ side effects |
| % cloud/vendor grants được rà soát đúng hạn | Bao phủ tích hợp bên ngoài | Chỉ review danh sách chưa kiểm tra effective permissions |

**Đừng đánh đồng số lượng test pass với xác suất an toàn.** Một lỗ hổng cross-tenant có tác động lớn có thể quan trọng hơn hàng trăm quyền đọc tài liệu công khai đang được kiểm tra đúng.

### 19.1. Báo cáo cấp quản trị nên có gì?

Một báo cáo cho CISO/risk owner cần tóm tắt:

- Mục tiêu và các access controls trọng yếu.
- Scope và kỳ: môi trường, tài sản, người dùng và đường kiểm tra.
- Tỷ lệ control pass/fail/insufficient theo **risk criticality**.
- Các finding lớn, thời hạn, remediation và retest.
- Các quyền đặc biệt, vendor, service accounts cần chú ý.
- Evidence gaps, assumptions và rủi ro thay đổi.
- Residual risk và quyết định cần thẩm quyền.
- Những trigger sẽ khiến kết luận phải đánh giá lại.

Báo cáo không nên chỉ có một ô màu xanh “access control compliant” không giải thích phương pháp.

## 20. Những sai lầm thường gặp

**“Đăng nhập bằng SSO/MFA thì dữ liệu đã được phân quyền đúng.”** Sai. AuthN không quyết định quyền đối với classId, learnerId hoặc tenant.

**“Chỉ cần role TEACHER để xuất dữ liệu.”** Có thể quá rộng. Cần quyền với đối tượng, hành động và trạng thái nghiệp vụ.

**“Ẩn nút trên frontend là đủ.”** Không. Actor có thể gọi API trực tiếp hoặc đi qua đường worker/mobile.

**“API trả 403 nghĩa là không có dữ liệu bị lộ.”** Chưa chắc. Phải xem side effects, async job, storage và log.

**“RBAC/ABAC là tên mô hình nên không cần test.”** Mô hình giúp diễn đạt policy; dữ liệu thuộc tính, quyền thực tế và điểm thực thi vẫn có thể sai.

**“Mọi quyền phải được thu hồi tức thời bất kể thiết kế.”** Mục tiêu thu hồi cần được xác định theo rủi ro và business policy; phải test propagation, token/session/cache theo cam kết, không tự giả định.

**“Không có incident chứng minh access control hoạt động.”** Không nếu logging/detection không được xác minh.

**“Một screenshot của IAM console đủ cho cả quý.”** Chưa chứng minh lịch sử quyền, đường khác, tài khoản đặc biệt và operating effectiveness.

**“Service accounts không cần review vì không phải người.”** Workload có thể có quyền rất rộng và secret tồn tại lâu, nên cần owner, purpose, least privilege và evidence tương ứng.

**“Có tool IAM tự động là không còn quyền dư.”** Tool cần inventory đầy đủ, logic đúng, nguồn dữ liệu đáng tin và quy trình xử lý exception.

**“Pass unit test là production pass.”** Cần kiểm tra test design, policy thực, config, deploy mapping, route coverage và side effects.

**“Risk accepted nghĩa là không còn finding.”** Acceptance không thay đổi kết quả sai lệch kỹ thuật và không tự miễn nghĩa vụ bắt buộc.

**“Càng nhiều log càng có assurance.”** Log chứa PII/token không cần thiết gây rủi ro mới. Cần dữ liệu đủ, có nguồn, integrity và bảo vệ phù hợp.

**“Assurance là hoạt động một lần trước go-live.”** Quyền và chính sách thay đổi liên tục; cần kiểm chứng theo thay đổi và kỳ đánh giá.

## 21. Triển khai chương trình access control assurance

### Giai đoạn 1 — Xác định scope và control owners

Liệt kê các tài sản, API, user roles, workload identities, tenant, cloud accounts, admin paths, vendor connections và loại dữ liệu. Xác định business/risk owner, control owner, evidence owner và reviewer.

**Đầu ra:** inventory được đối chiếu, data flow, trust boundaries, danh sách tài khoản/quyền quan trọng.

### Giai đoạn 2 — Viết policy và security invariants

Tạo access matrix theo actor, action, object, context; xác định deny/allow, ngoại lệ, quyền tạm và điều kiện thu hồi. Thống nhất với product/business owner và rủi ro cần kiểm soát.

**Đầu ra:** requirements có testability, policy design, control register.

### Giai đoạn 3 — Kiểm tra đường thực thi và độ phủ

Đánh giá API, worker, file, database, cloud/IAM, CI/CD và nhà cung cấp; chạy positive/negative tests, kiểm tra side effects, quyền biến động và các đường bypass.

**Đầu ra:** test matrix, code/config review, evidence gaps và các finding đầu tiên.

### Giai đoạn 4 — Thiết lập evidence standard

Mô tả nguồn, metadata, build/deploy mapping, population, kỳ, owner, retention, integrity, cách lấy mẫu và người đánh giá. Tự động hóa khi có nguồn đáng tin.

**Đầu ra:** evidence catalog, reporting format và assessor review.

### Giai đoạn 5 — Khắc phục và quyết định rủi ro

Tạo finding có impact và root cause; thực hiện containment, remediation và retest; phân biệt fail với insufficient evidence. Risk owner quyết định residual risk theo thẩm quyền.

**Đầu ra:** remediation history, retest evidence, risk decision và assurance claim có scope.

### Giai đoạn 6 — Duy trì continuous assurance

Tích hợp access review, IAM diff, CI/CD authorization tests, logging health, break-glass review, vendor scope review và trigger khi đổi vai trò hoặc tenant.

**Đầu ra:** cadence theo rủi ro, dashboards có mẫu số rõ, cập nhật control register và báo cáo giới hạn.

## 22. Bài tập thực hành

### Bài tập A — Phân biệt AuthN và AuthZ

Một lập trình viên nói: “API đã dùng JWT hợp lệ và role TEACHER nên an toàn”. Tuy nhiên, endpoint đọc điểm nhận learnerId và classId từ request.

Hãy trả lời:

1. Điều gì đã được AuthN chứng minh, điều gì chưa được AuthZ chứng minh?
2. Những nguồn tin cậy nào phải được dùng để kiểm tra class/tenant ownership?
3. Viết security invariant cho API đọc điểm.
4. Tạo ba negative tests và một positive test.
5. Kiểm tra side effects và log nào cần có?
6. Nếu test ở staging pass nhưng production khác config, kết luận nên viết thế nào?

**Gợi ý:** Token hợp lệ không chứng minh được quyền đối với learnerId do client gửi. Phải kiểm tra quyền thực tế theo actor, action, object và tenant tại backend.

### Bài tập B — Thu hồi quyền và async export

Giảng viên A đang được phân công lớp 42, đã tạo job export. Một phút sau, quyền lớp 42 bị thu hồi; worker chưa chạy và file chưa có.

Hãy thiết kế hai phương án chính sách (ví dụ: kiểm tra lại lúc xử lý hoặc cho phép một quyền job có giới hạn theo thời điểm tạo), rồi phân tích:

- Mức rủi ro và ảnh hưởng nghiệp vụ.
- Đường cần kiểm soát từ API đến worker và download.
- Cách biểu diễn policy, hạn và revocation.
- Test case trước/sau đổi quyền.
- Evidence cho kết luận và những giả định cần nêu.

**Gợi ý:** Không có một quy tắc bắt buộc duy nhất cho mọi nghiệp vụ. Điều bắt buộc là chính sách phải rõ, đường đi thực thi nhất quán và rủi ro còn lại được xem xét.

### Bài tập C — Audit quyền admin cloud

CISO cần bằng chứng rằng tài khoản con người có quyền quản trị production được phê duyệt và bảo vệ bằng cơ chế xác thực theo baseline trong quý vừa qua. IAM team gửi screenshot MFA từ một IdP.

Hãy lập assurance plan gồm:

1. Claim có scope và period cụ thể.
2. Population đầy đủ: IdP, cloud, local/emergency, accounts từ vendor.
3. Design, implementation và operating evidence.
4. Cách đối chiếu quyền phê duyệt, cấp/thu hồi và effective permissions.
5. Test đường đăng nhập ngoài policy, quản lý break-glass.
6. Cách xác định Pass/Fail/Insufficient evidence.
7. Cách báo rủi ro khi inventory thiếu.

**Gợi ý:** Screenshot không chứng minh toàn bộ population và lịch sử cả kỳ; cần xác minh nguồn và đường bypass.

### Bài tập D — Tạo test matrix cho đa tenant

Một hệ thống Java có hai tenant A và B, trong mỗi tenant có STUDENT, TEACHER và ADMIN. Backend cung cấp API xem điểm, sửa điểm và xuất danh sách.

Hãy thiết kế test matrix ít nhất mười trường hợp, bao phủ:

- Role đúng/sai, object khác chủ, tenant khác.
- Đường chức năng admin, thay trạng thái lớp, quyền bị thu hồi.
- Bulk export, queue, object storage.
- Positive tests và negative tests.
- Expected response, side effects và log.
- Môi trường, build và fixture cần lưu để có thể tái kiểm chứng.

**Gợi ý:** Cần test cả functional permissions và object/tenant relationships, không chỉ role.

### Bài tập E — Kết luận một finding

Kiểm thử phát hiện controller từ chối request ngoài quyền, nhưng file export vẫn được tạo trong object storage. Team đã merge fix và đánh dấu ticket Done.

Viết một báo cáo ngắn:

- Finding và attack path ban đầu.
- Tác động, điều chưa biết về dữ liệu đã bị truy cập.
- Biện pháp containment và owner.
- Test/retest ở API, worker, storage/download.
- Build/deployment evidence và operating evidence.
- Điều kiện đóng finding và cập nhật residual risk.
- Claim nào có thể xác nhận, claim nào chưa đủ evidence.

**Gợi ý:** Merge code không chứng minh production đã được sửa. Cần retest cho artifact đang chạy và side effects end-to-end.

## 23. Checklist đánh giá access control assurance

Checklist giúp rà soát độ hoàn chỉnh của chương trình, **không tự chứng minh mọi control đã đạt**:

- [ ] Đã xác định tài sản, dữ liệu, user types, service identities và môi trường cần bảo vệ.
- [ ] Có risk scenarios cho truy cập sai vai trò, đối tượng, tenant, trạng thái và đặc quyền.
- [ ] Access policy và security invariants có owner và tiêu chí kiểm thử.
- [ ] Đã phân biệt AuthN, AuthZ, policy decision, enforcement và audit.
- [ ] Có inventory quyền, effective permissions và các đường cấp quyền.
- [ ] RBAC/ABAC/ReBAC hoặc mô hình kết hợp được mô tả đúng với thực tế.
- [ ] API/worker/batch/storage/download đều có coverage phù hợp hoặc evidence gap được ghi.
- [ ] Đã kiểm tra least privilege, deny by default, complete mediation và segregation of duties.
- [ ] Có test function-, object-, tenant-, property- và workflow-level authorization.
- [ ] Có test positive, negative, boundary, policy failure, revoke và side effects.
- [ ] Có phương pháp kiểm chứng JML, periodic review, break-glass và vendor access.
- [ ] Non-human identities có owner, purpose, scope, secret lifecycle và test.
- [ ] Test evidence có đúng build/config/deployment mapping, expected/actual và period.
- [ ] Có design, implementation và operating effectiveness evidence theo risk.
- [ ] Có log/audit và kiểm tra sức khỏe telemetry, không ghi lộ dữ liệu nhạy cảm.
- [ ] Evidence có provenance, scope, integrity, freshness và phương pháp sampling rõ.
- [ ] Assessment phân biệt Pass, Fail, Insufficient evidence và N/A.
- [ ] Finding có owner, impact, remediation, retest và quyết định residual risk.
- [ ] Exception/acceptance có thẩm quyền, điều kiện và không che lấp control failure.
- [ ] Có trigger để đánh giá lại sau thay đổi quyền, API, tenant, vendor hoặc incident.
- [ ] Báo cáo cho risk owner nêu phạm vi, kỳ, giới hạn và rủi ro chưa thể chứng minh.

## 24. Ghi nhớ

- **Access control assurance là quá trình tạo bằng chứng có thể kiểm chứng rằng chính sách quyền thực sự được áp dụng đúng**, không chỉ sự tồn tại của MFA, role hay công cụ IAM.
- **Authentication xác minh chủ thể; authorization quyết định quyền trên đúng hành động và đối tượng**. Đã đăng nhập không đồng nghĩa được phép đọc mọi dữ liệu.
- Cần kiểm tra **toàn bộ đường truy cập**, từ frontend/API đến queue/worker, dữ liệu, object storage, admin và vendor integration.
- Access control phải được xem theo **identity lifecycle**, effective permissions, trạng thái quyền, session/cache và service/workload identities.
- Một claim đáng tin cần **mục tiêu, scope, period, tiêu chí, test và evidence**, đồng thời nêu những đường chưa kiểm chứng.
- **Design**, **implementation** và **operating effectiveness** là ba tầng khác nhau; một snapshot cấu hình hoặc test pass không tự chứng minh hiệu quả suốt kỳ.
- **Control failure** và **evidence gap** khác nhau; cả hai đều không được báo Pass khi chưa có cơ sở.
- Finding, remediation/retest và residual risk phải gắn với **owner và quyết định đúng thẩm quyền**, không được dùng risk acceptance để che sai lệch.
- Chương trình assurance trưởng thành tạo vòng lặp **risk → requirement → control → tests/evidence → assessment → decision → monitoring/reassessment** khi hệ thống phát triển và vận hành.

